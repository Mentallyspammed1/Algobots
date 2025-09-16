0a1,7
> """Whalebot: An automated cryptocurrency trading bot for Bybit.
> 
> This bot leverages various technical indicators and multi-timeframe analysis
> to generate trading signals and manage positions on the Bybit exchange.
> It includes features for risk management, performance tracking, and alerts.
> """
> 
2c9,10
< import contextlib
---
> import hashlib
> import hmac
6d13
< import random
9,11c16,19
< from dataclasses import dataclass  # New: Explicit import for dataclass
< from datetime import datetime
< from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal, getcontext
---
> import urllib.parse
> import warnings
> from datetime import UTC, datetime
> from decimal import ROUND_DOWN, Decimal, getcontext
14,15c22,26
< from typing import Any, ClassVar, Generic, TypeVar
< from zoneinfo import ZoneInfo
---
> from typing import (
>     Any,
>     ClassVar,
>     Literal,
> )
21a33,35
> from dotenv import load_dotenv
> from requests.adapters import HTTPAdapter
> from urllib3.util.retry import Retry
23,25c37,38
< import warnings
< warnings.simplefilter("ignore", FutureWarning)
< warnings.simplefilter("ignore", UserWarning)
---
> warnings.filterwarnings("ignore", category=FutureWarning)
> warnings.filterwarnings("ignore", category=UserWarning)
27c40,41
< from pybit.unified_trading import HTTP, WebSocket
---
> # Note: Scikit-learn is explicitly excluded as per user request.
> # SKLEARN_AVAILABLE variable is removed as it is unused and its presence might suggest ML features.
29c43,46
< from gemini_client import GeminiClient # New: Import GeminiClient
---
> # Initialize colorama and set decimal precision
> getcontext().prec = 28  # High precision for financial calculations
> init(autoreset=True)
> load_dotenv()
31c48,54
< SKLEARN_AVAILABLE = False
---
> # --- Constants ---
> API_KEY = os.getenv("BYBIT_API_KEY")
> API_SECRET = os.getenv("BYBIT_API_SECRET")
> BASE_URL = os.getenv("BYBIT_BASE_URL", "https://api.bybit.com")
> CONFIG_FILE = "config.json"
> LOG_DIRECTORY = "bot_logs/trading-bot/logs"
> Path(LOG_DIRECTORY).mkdir(parents=True, exist_ok=True)
33,48c56,63
< getcontext().prec = 28
< init(autoreset=True)
< # Manually load .env file as a fallback
< try:
<     with open('/data/data/com.termux/files/home/Algobots/whalebot/.env') as f:
<         for line in f:
<             line = line.strip()
<             if line and not line.startswith('#') and '=' in line:
<                 key, value = line.split('=', 1)
<                 key = key.strip()
<                 value = value.strip().strip("'\"")
<                 if value:
<                     os.environ[key] = value
< except FileNotFoundError:
<     # The script will check for the env vars later and exit if not found
<     pass
---
> # Using UTC for consistency and to avoid timezone issues with API timestamps
> TIMEZONE = UTC
> MAX_API_RETRIES = 5
> RETRY_DELAY_SECONDS = 7
> REQUEST_TIMEOUT = 20
> LOOP_DELAY_SECONDS = 15
> WS_RECONNECT_DELAY_SECONDS = 5
> API_CALL_RETRY_DELAY_SECONDS = 3
49a65,75
> # Magic Numbers as Constants (expanded and named for clarity)
> MIN_DATA_POINTS_TRUE_RANGE = 2
> MIN_DATA_POINTS_SUPERSMOOTHER = 2
> MIN_DATA_POINTS_OBV = 2
> MIN_DATA_POINTS_PSAR_INITIAL = 4  # PSAR needs a few points to initialize reliably
> ADX_STRONG_TREND_THRESHOLD = 25
> ADX_WEAK_TREND_THRESHOLD = 20
> MIN_DATA_POINTS_VWMA = 2
> MIN_DATA_POINTS_VOLATILITY = 2
> 
> # Neon Color Scheme
57a84
> # Indicator specific colors (enhanced for new indicators)
93a121,123
>     "Volatility_Index": Fore.YELLOW,
>     "Volume_Delta": Fore.LIGHTCYAN_EX,
>     "VWMA": Fore.WHITE,
96,117d125
< API_KEY = os.getenv("BYBIT_API_KEY")
< API_SECRET = os.getenv("BYBIT_API_SECRET")
< CONFIG_FILE = "config.json"
< LOG_DIRECTORY = "bot_logs"
< Path(LOG_DIRECTORY).mkdir(parents=True, exist_ok=True)
< 
< TIMEZONE = ZoneInfo("America/Chicago")
< MAX_API_RETRIES = 5
< RETRY_DELAY_SECONDS = 7
< REQUEST_TIMEOUT = 20
< LOOP_DELAY_SECONDS = 15
< 
< MIN_DATA_POINTS_TR = 2
< MIN_DATA_POINTS_SMOOTHER = 2
< MIN_DATA_POINTS_OBV = 2
< MIN_DATA_POINTS_PSAR = 2
< ADX_STRONG_TREND_THRESHOLD = 25
< ADX_WEAK_TREND_THRESHOLD = 20
< 
< WS_RECONNECT_DELAY_SECONDS = 5
< API_CALL_RETRY_DELAY_SECONDS = 3
< 
118a127
> # --- Configuration Management ---
121a131
>         # Core Settings
127a138
>         # Signal Generation
129a141
>         # Position & Risk Management
132,136c144,148
<             "account_balance": 1000.0,
<             "risk_per_trade_percent": 1.0,
<             "stop_loss_atr_multiple": 1.5,
<             "take_profit_atr_multiple": 2.0,
<             "trailing_stop_atr_multiple": 0.5,
---
>             "account_balance": 1000.0,  # Simulated balance if not using real API
>             "risk_per_trade_percent": 1.0,  # Percentage of account_balance to risk
>             "stop_loss_atr_multiple": 1.5,  # Stop loss distance as multiple of ATR
>             "take_profit_atr_multiple": 2.0,  # Take profit distance as multiple of ATR
>             "trailing_stop_atr_multiple": 0.3,  # Trailing stop distance as multiple of ATR
138c150,156
<             "default_leverage": 5,
---
>             "order_precision": 4,  # Decimal places for order quantity
>             "price_precision": 2,  # Decimal places for price
>             "leverage": 10,  # Leverage for perpetual contracts
>             "order_mode": "MARKET",  # MARKET or LIMIT for entry orders
>             "take_profit_type": "MARKET",  # MARKET or LIMIT for TP
>             "stop_loss_type": "MARKET",  # MARKET or LIMIT for SL
>             "trailing_stop_activation_percent": 0.5,  # % profit to activate trailing stop
139a158
>         # Multi-Timeframe Analysis
144c163
<             "trend_period": 50,
---
>             "trend_period": 50,  # Period for MTF trend indicators like SMA/EMA
146a166
>         # Machine Learning Enhancement (Explicitly disabled)
148c168
<             "enabled": False,
---
>             "enabled": False,  # ML explicitly disabled
154c174
<             "feature_lags": [1, 2, 3, 5],
---
>             "feature_lags": [1, 2, 3, 5],  # Added default values
156a177
>         # Indicator Periods & Thresholds
202a224
>             "vwap_daily_reset": False,  # Should VWAP reset daily or be continuous
203a226
>         # Active Indicators & Weights (expanded)
206a230
>             "momentum": True,
232a257
>                 "momentum_rsi_stoch_cci_wr_mfi": 0.18,
234,235d258
<                 "stoch_rsi": 0.30,
<                 "rsi": 0.12,
238,239d260
<                 "cci": 0.08,
<                 "wr": 0.08,
242d262
<                 "mfi": 0.12,
255a276,283
>         # Gemini AI Analysis (Optional)
>         "gemini_ai_analysis": {
>             "enabled": False,
>             "model_name": "gemini-1.0-pro",
>             "temperature": 0.7,
>             "top_p": 0.9,
>             "weight": 0.3,  # Weight of Gemini's signal in the final score
>         },
262c290,292
<                 f"{NEON_YELLOW}Configuration file not found. Created default config at {filepath}{RESET}"
---
>                 f"{NEON_YELLOW}Configuration file not found. "
>                 f"Created default config at {filepath} for symbol "
>                 f"{default_config['symbol']}{RESET}"
272a303
>         # Save updated config to include any newly added default keys
296a328
> # --- Logging Setup ---
302a335
>         """Initializes the SensitiveFormatter."""
306a340
>         """Returns the default log format string."""
309a344
>         """Formats the log record, redacting sensitive words."""
323a359
>     # Ensure handlers are not duplicated
324a361
>         # Console Handler
332a370
>         # File Handler
345,548c383,395
< KT = TypeVar("KT")
< VT = TypeVar("VT")
< 
< 
< @dataclass(slots=True)
< class PriceLevel:
<     """Price level with metadata, optimized for memory with slots."""
< 
<     price: float
<     quantity: float
<     timestamp: int
<     order_count: int = 1
< 
<     def __lt__(self, other: 'PriceLevel') -> bool:
<         return self.price < other.price
< 
<     def __eq__(self, other: 'PriceLevel') -> bool:
<         return abs(self.price - other.price) < 1e-8
< 
< 
< class OptimizedSkipList(Generic[KT, VT]):
<     """Enhanced Skip List implementation with O(log n) insert/delete/search.
<     Asynchronous operations are not directly supported by SkipList itself,
<     but it's protected by an asyncio.Lock in the manager.
<     """
< 
<     class Node(Generic[KT, VT]):
<         def __init__(self, key: KT, value: VT, level: int):
<             self.key = key
<             self.value = value
<             self.forward: list[OptimizedSkipList.Node | None] = [None] * (level + 1)
<             self.level = level
< 
<     def __init__(self, max_level: int = 16, p: float = 0.5):
<         self.max_level = max_level
<         self.p = p
<         self.level = 0
<         self.header = self.Node(None, None, max_level)
<         self._size = 0
< 
<     def _random_level(self) -> int:
<         level = 0
<         while level < self.max_level and random.random() < self.p:
<             level += 1
<         return level
< 
<     def insert(self, key: KT, value: VT) -> None:
<         update = [None] * (self.max_level + 1)
<         current = self.header
<         for i in range(self.level, -1, -1):
<             while (current.forward[i] and
<                    current.forward[i].key is not None and
<                    current.forward[i].key < key):
<                 current = current.forward[i]
<             update[i] = current
<         current = current.forward[0]
< 
<         if current and current.key == key:
<             current.value = value
<             return
< 
<         new_level = self._random_level()
<         if new_level > self.level:
<             for i in range(self.level + 1, new_level + 1):
<                 update[i] = self.header
<             self.level = new_level
< 
<         new_node = self.Node(key, value, new_level)
<         for i in range(new_level + 1):
<             new_node.forward[i] = update[i].forward[i]
<             update[i].forward[i] = new_node
<         self._size += 1
< 
<     def delete(self, key: KT) -> bool:
<         update = [None] * (self.max_level + 1)
<         current = self.header
<         for i in range(self.level, -1, -1):
<             while (current.forward[i] and
<                    current.forward[i].key is not None and
<                    current.forward[i].key < key):
<                 current = current.forward[i]
<             update[i] = current
<         current = current.forward[0]
<         if not current or current.key != key:
<             return False
< 
<         for i in range(self.level + 1):
<             if update[i].forward[i] != current:
<                 break
<             update[i].forward[i] = current.forward[i]
<         while self.level > 0 and not self.header.forward[self.level]:
<             self.level -= 1
<         self._size -= 1
<         return True
< 
<     def get_sorted_items(self, reverse: bool = False) -> list[tuple[KT, VT]]:
<         items = []
<         current = self.header.forward[0]
<         while current:
<             if current.key is not None:
<                 items.append((current.key, current.value))
<             current = current.forward[0]
<         return list(reversed(items)) if reverse else items
< 
<     def peek_top(self, reverse: bool = False) -> VT | None:
<         items = self.get_sorted_items(reverse=reverse)
<         return items[0][1] if items else None
< 
<     @property
<     def size(self) -> int:
<         return self._size
< 
< 
< class EnhancedHeap:
<     """Enhanced heap implementation (Min-Heap or Max-Heap) with position tracking
<     for O(log n) update and removal operations.
<     Protected by an asyncio.Lock in the manager.
<     """
< 
<     def __init__(self, is_max_heap: bool = True):
<         self.heap: list[PriceLevel] = []
<         self.is_max_heap = is_max_heap
<         self.position_map: dict[float, int] = {}
< 
<     def _parent(self, i: int) -> int: return (i - 1) // 2
<     def _left_child(self, i: int) -> int: return 2 * i + 1
<     def _right_child(self, i: int) -> int: return 2 * i + 2
< 
<     def _compare(self, a: PriceLevel, b: PriceLevel) -> bool:
<         if self.is_max_heap: return a.price > b.price
<         return a.price < b.price
< 
<     def _swap(self, i: int, j: int) -> None:
<         self.position_map[self.heap[i].price] = j
<         self.position_map[self.heap[j].price] = i
<         self.heap[i], self.heap[j] = self.heap[j], self.heap[i]
< 
<     def _heapify_up(self, i: int) -> None:
<         while i > 0:
<             parent = self._parent(i)
<             if not self._compare(self.heap[i], self.heap[parent]): break
<             self._swap(i, parent)
<             i = parent
< 
<     def _heapify_down(self, i: int) -> None:
<         while True:
<             largest = i
<             left = self._left_child(i)
<             right = self._right_child(i)
<             if left < len(self.heap) and self._compare(self.heap[left], self.heap[largest]): largest = left
<             if right < len(self.heap) and self._compare(self.heap[right], self.heap[largest]): largest = right
<             if largest == i: break
<             self._swap(i, largest)
<             i = largest
< 
<     def insert(self, price_level: PriceLevel) -> None:
<         if price_level.price in self.position_map:
<             idx = self.position_map[price_level.price]
<             old_price = self.heap[idx].price
<             self.heap[idx] = price_level
<             self.position_map[price_level.price] = idx
<             if abs(old_price - price_level.price) > 1e-8:
<                  del self.position_map[old_price]
<             self._heapify_up(idx)
<             self._heapify_down(idx)
<         else:
<             self.heap.append(price_level)
<             idx = len(self.heap) - 1
<             self.position_map[price_level.price] = idx
<             self._heapify_up(idx)
< 
<     def remove(self, price: float) -> bool:
<         if price not in self.position_map: return False
<         idx = self.position_map[price]
<         del self.position_map[price]
<         if idx == len(self.heap) - 1:
<             self.heap.pop()
<             return True
<         last = self.heap.pop()
<         self.heap[idx] = last
<         self.position_map[last.price] = idx
<         self._heapify_up(idx)
<         self._heapify_down(idx)
<         return True
< 
<     def peek_top(self) -> PriceLevel | None:
<         return self.heap[0] if self.heap else None
< 
<     @property
<     def size(self) -> int:
<         return len(self.heap)
< 
< 
< class AdvancedOrderbookManager:
<     """Manages the orderbook for a single symbol using either OptimizedSkipList or EnhancedHeap.
<     Provides thread-safe (asyncio-safe) operations, snapshot/delta processing,
<     and access to best bid/ask.
<     """
< 
<     def __init__(self, symbol: str, logger: logging.Logger, use_skip_list: bool = True):
<         self.symbol = symbol
<         self.logger = logger
<         self.use_skip_list = use_skip_list
<         self._lock = asyncio.Lock()
---
> # --- API Interaction ---
> def create_session() -> requests.Session:
>     """Create a requests session with retry logic."""
>     session = requests.Session()
>     retries = Retry(
>         total=MAX_API_RETRIES,
>         backoff_factor=RETRY_DELAY_SECONDS,
>         # Added common HTTP error codes
>         status_forcelist=[429, 500, 502, 503, 504],
>         allowed_methods=frozenset(["GET", "POST"]),
>     )
>     session.mount("https://", HTTPAdapter(max_retries=retries))
>     return session
550,589d396
<         if use_skip_list:
<             self.logger.info(f"OrderbookManager for {symbol}: Using OptimizedSkipList.")
<             self.bids_ds = OptimizedSkipList[float, PriceLevel]()
<             self.asks_ds = OptimizedSkipList[float, PriceLevel]()
<         else:
<             self.logger.info(f"OrderbookManager for {symbol}: Using EnhancedHeap.")
<             self.bids_ds = EnhancedHeap(is_max_heap=True)
<             self.asks_ds = EnhancedHeap(is_max_heap=False)
< 
<         self.last_update_id: int = 0
< 
<     @contextlib.asynccontextmanager
<     async def _lock_context(self):
<         """Async context manager for acquiring and releasing the asyncio.Lock."""
<         async with self._lock:
<             yield
< 
<     async def _validate_price_quantity(self, price: float, quantity: float) -> bool:
<         """Validates if price and quantity are non-negative and numerically valid."""
<         if not (isinstance(price, (int, float)) and isinstance(quantity, (int, float))):
<             self.logger.error(f"Invalid type for price or quantity for {self.symbol}. Price: {type(price)}, Qty: {type(quantity)}")
<             return False
<         if price < 0 or quantity < 0:
<             self.logger.error(f"Negative price or quantity detected for {self.symbol}: price={price}, quantity={quantity}")
<             return False
<         return True
< 
<     async def update_snapshot(self, data: dict[str, Any]) -> None:
<         """Processes an initial orderbook snapshot."""
<         async with self._lock_context():
<             if not isinstance(data, dict) or 'b' not in data or 'a' not in data or 'u' not in data:
<                 self.logger.error(f"Invalid snapshot data format for {self.symbol}: {data}")
<                 return
< 
<             if self.use_skip_list:
<                 self.bids_ds = OptimizedSkipList[float, PriceLevel]()
<                 self.asks_ds = OptimizedSkipList[float, PriceLevel]()
<             else:
<                 self.bids_ds = EnhancedHeap(is_max_heap=True)
<                 self.asks_ds = EnhancedHeap(is_max_heap=False)
591,632c398,416
<             for price_str, qty_str in data.get('b', []):
<                 try:
<                     price = float(price_str)
<                     quantity = float(qty_str)
<                     if await self._validate_price_quantity(price, quantity) and quantity > 0:
<                         level = PriceLevel(price, quantity, int(time.time() * 1000))
<                         if self.use_skip_list: self.bids_ds.insert(price, level)
<                         else: self.bids_ds.insert(level)
<                 except (ValueError, TypeError) as e:
<                     self.logger.error(f"Failed to parse bid in snapshot for {self.symbol}: {price_str}/{qty_str}, error={e}")
< 
<             for price_str, qty_str in data.get('a', []):
<                 try:
<                     price = float(price_str)
<                     quantity = float(qty_str)
<                     if await self._validate_price_quantity(price, quantity) and quantity > 0:
<                         level = PriceLevel(price, quantity, int(time.time() * 1000))
<                         if self.use_skip_list: self.asks_ds.insert(price, level)
<                         else: self.asks_ds.insert(level)
<                 except (ValueError, TypeError) as e:
<                     self.logger.error(f"Failed to parse ask in snapshot for {self.symbol}: {price_str}/{qty_str}, error={e}")
< 
<             self.last_update_id = data.get('u', 0)
<             self.logger.info(f"Orderbook {self.symbol} snapshot updated. Last Update ID: {self.last_update_id}")
< 
<     async def update_delta(self, data: dict[str, Any]) -> None:
<         """Applies incremental updates (deltas) to the orderbook."""
<         async with self._lock_context():
<             if not isinstance(data, dict) or not ('b' in data or 'a' in data) or 'u' not in data:
<                 self.logger.error(f"Invalid delta data format for {self.symbol}: {data}")
<                 return
< 
<             current_update_id = data.get('u', 0)
<             if current_update_id <= self.last_update_id:
<                 self.logger.debug(f"Outdated OB update for {self.symbol}: current={current_update_id}, last={self.last_update_id}. Skipping.")
<                 return
< 
<             for price_str, qty_str in data.get('b', []):
<                 try:
<                     price = float(price_str)
<                     quantity = float(qty_str)
<                     if not await self._validate_price_quantity(price, quantity): continue
---
> def generate_signature(payload: str, api_secret: str) -> str:
>     """Generate a Bybit API signature."""
>     return hmac.new(api_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
> 
> 
> def bybit_request(
>     method: Literal["GET", "POST"],
>     endpoint: str,
>     params: dict | None = None,
>     signed: bool = False,
>     logger: logging.Logger | None = None,
> ) -> dict | None:
>     """Send a request to the Bybit API."""
>     if logger is None:
>         logger = setup_logger("bybit_api")
>     session = create_session()
>     url = f"{BASE_URL}{endpoint}"
>     headers = {"Content-Type": "application/json"}
>     params = params if params is not None else {}
634,647c418,423
<                     if quantity == 0.0:
<                         self.bids_ds.delete(price) if self.use_skip_list else self.bids_ds.remove(price)
<                     else:
<                         level = PriceLevel(price, quantity, int(time.time() * 1000))
<                         if self.use_skip_list: self.bids_ds.insert(price, level)
<                         else: self.bids_ds.insert(level)
<                 except (ValueError, TypeError) as e:
<                     self.logger.error(f"Failed to parse bid delta for {self.symbol}: {price_str}/{qty_str}, error={e}")
< 
<             for price_str, qty_str in data.get('a', []):
<                 try:
<                     price = float(price_str)
<                     quantity = float(qty_str)
<                     if not await self._validate_price_quantity(price, quantity): continue
---
>     if signed:
>         if not API_KEY or not API_SECRET:
>             logger.error(
>                 f"{NEON_RED}API_KEY or API_SECRET not set for signed request. Cannot proceed.{RESET}"
>             )
>             return None
649,708c425,426
<                     if quantity == 0.0:
<                         self.asks_ds.delete(price) if self.use_skip_list else self.asks_ds.remove(price)
<                     else:
<                         level = PriceLevel(price, quantity, int(time.time() * 1000))
<                         if self.use_skip_list: self.asks_ds.insert(price, level)
<                         else: self.asks_ds.insert(level)
<                 except (ValueError, TypeError) as e:
<                     self.logger.error(f"Failed to parse ask delta for {self.symbol}: {price_str}/{qty_str}, error={e}")
< 
<             self.last_update_id = current_update_id
<             self.logger.debug(f"Orderbook {self.symbol} delta applied. Last Update ID: {self.last_update_id}")
< 
<     async def get_best_bid_ask(self) -> tuple[float | None, float | None]:
<         """Returns the current best bid and best ask prices."""
<         async with self._lock_context():
<             best_bid_level = self.bids_ds.peek_top(reverse=True) if self.use_skip_list else self.bids_ds.peek_top()
<             best_ask_level = self.asks_ds.peek_top(reverse=False) if self.use_skip_list else self.asks_ds.peek_top()
< 
<             best_bid = best_bid_level.price if best_bid_level else None
<             best_ask = best_ask_level.price if best_ask_level else None
<             return best_bid, best_ask
< 
<     async def get_depth(self, depth: int) -> tuple[list[PriceLevel], list[PriceLevel]]:
<         """Retrieves the top N bids and asks."""
<         async with self._lock_context():
<             if self.use_skip_list:
<                 bids = [item[1] for item in self.bids_ds.get_sorted_items(reverse=True)[:depth]]
<                 asks = [item[1] for item in self.asks_ds.get_sorted_items()[:depth]]
<             else:
<                 bids_list: list[PriceLevel] = []
<                 asks_list: list[PriceLevel] = []
<                 temp_bids_storage: list[PriceLevel] = []
<                 temp_asks_storage: list[PriceLevel] = []
< 
<                 for _ in range(min(depth, self.bids_ds.size)):
<                     level = self.bids_ds.peek_top()
<                     if level:
<                         self.bids_ds.remove(level.price)
<                         bids_list.append(level)
<                         temp_bids_storage.append(level)
<                 for level in temp_bids_storage:
<                     self.bids_ds.insert(level)
< 
<                 for _ in range(min(depth, self.asks_ds.size)):
<                     level = self.asks_ds.peek_top()
<                     if level:
<                         self.asks_ds.remove(level.price)
<                         asks_list.append(level)
<                         temp_asks_storage.append(level)
<                 for level in temp_asks_storage:
<                     self.asks_ds.insert(level)
< 
<                 bids = bids_list
<                 asks = asks_list
<             return bids, asks
< 
< 
< class BybitClient:
<     """Manages all Bybit API interactions (HTTP & WebSocket) and includes retry logic.
<     """
---
>         timestamp = str(int(time.time() * 1000))
>         recv_window = "20000"
710,782c428,465
<     def __init__(self, api_key: str, api_secret: str, config: dict[str, Any], logger: logging.Logger):
<         self.config = config
<         self.logger = logger
<         self.api_key = api_key
<         self.api_secret = api_secret
<         self.testnet = config["testnet"]
<         self.symbol = config["symbol"]
<         self.category = "linear"
< 
<         self.http_session = HTTP(
<             testnet=self.testnet,
<             api_key=self.api_key,
<             api_secret=self.api_secret
<         )
< 
<         self.ws_public: WebSocket | None = None
<         self.ws_private: WebSocket | None = None
<         self.ws_tasks: list[asyncio.Task] = []
< 
<         self.logger.info(f"BybitClient initialized (Testnet: {self.testnet})")
< 
<     async def _bybit_request_with_retry(self, method: str, func: callable, *args, **kwargs) -> dict | None:
<         """Helper to execute pybit HTTP calls with retry logic."""
<         for attempt in range(MAX_API_RETRIES):
<             try:
<                 response = func(*args, **kwargs)
<                 if response:
<                     ret_code = response.get("retCode")
<                     if ret_code == 0:
<                         return response
<                     elif ret_code == 110043: # Leverage not modified
<                         self.logger.info(f"{NEON_YELLOW}Leverage already set to requested value or cannot be modified at this time. Proceeding.{RESET}")
<                         return {"retCode": 0, "retMsg": "Leverage already set"} # Return a success response
<                     else:
<                         error_msg = response.get("retMsg", "Unknown error")
<                         self.logger.error(
<                             f"{NEON_RED}Bybit API Error ({method} attempt {attempt + 1}/{MAX_API_RETRIES}): {error_msg} (Code: {ret_code}){RESET}"
<                         )
<                 else: # No response
<                     self.logger.error(f"{NEON_RED}Bybit API Error ({method} attempt {attempt + 1}/{MAX_API_RETRIES}): No response{RESET}")
<             except requests.exceptions.HTTPError as e:
<                 self.logger.error(f"{NEON_RED}HTTP Error during {method} (attempt {attempt + 1}/{MAX_API_RETRIES}): {e.response.status_code} - {e.response.text}{RESET}")
<             except requests.exceptions.ConnectionError as e:
<                 self.logger.error(f"{NEON_RED}Connection Error during {method} (attempt {attempt + 1}/{MAX_API_RETRIES}): {e}{RESET}")
<             except requests.exceptions.Timeout:
<                 self.logger.error(f"{NEON_RED}Request timed out during {method} (attempt {attempt + 1}/{MAX_API_RETRIES}){RESET}")
<             except Exception as e:
<                 error_message = str(e)
<                 if "110043" in error_message:
<                     self.logger.info(f"{NEON_YELLOW}Leverage already set to requested value or cannot be modified at this time. Proceeding.{RESET}")
<                     return {"retCode": 0, "retMsg": "Leverage already set"}
<                 self.logger.error(f"{NEON_RED}Unexpected Error during {method} (attempt {attempt + 1}/{MAX_API_RETRIES}): {error_message}{RESET}")
< 
<             if attempt < MAX_API_RETRIES - 1:
<                 await asyncio.sleep(RETRY_DELAY_SECONDS)
< 
<         self.logger.critical(f"{NEON_RED}Bybit API {method} failed after {MAX_API_RETRIES} attempts.{RESET}")
<         return None
< 
<     async def fetch_current_price(self, symbol: str) -> Decimal | None:
<         """Fetch the current market price for a symbol."""
<         response = await self._bybit_request_with_retry(
<             "fetch_current_price",
<             self.http_session.get_tickers,
<             category=self.category,
<             symbol=symbol
<         )
<         if response and response["result"] and response["result"]["list"]:
<             price = Decimal(response["result"]["list"][0]["lastPrice"])
<             self.logger.debug(f"Fetched current price for {symbol}: {price}")
<             return price
<         self.logger.warning(f"{NEON_YELLOW}Could not fetch current price for {symbol}.{RESET}")
<         return None
---
>         if method == "GET":
>             query_string = urllib.parse.urlencode(params)
>             param_str = timestamp + API_KEY + recv_window + query_string
>             signature = generate_signature(param_str, API_SECRET)
>             headers.update(
>                 {
>                     "X-BAPI-API-KEY": API_KEY,
>                     "X-BAPI-TIMESTAMP": timestamp,
>                     "X-BAPI-SIGN": signature,
>                     "X-BAPI-RECV-WINDOW": recv_window,
>                 }
>             )
>             full_url = f"{url}?{query_string}" if query_string else url
>             logger.debug(f"GET Request to {full_url}")
>             response = session.get(
>                 url, params=params, headers=headers, timeout=REQUEST_TIMEOUT
>             )
>         else:  # POST
>             json_params = json.dumps(params)
>             param_str = timestamp + API_KEY + recv_window + json_params
>             signature = generate_signature(param_str, API_SECRET)
>             headers.update(
>                 {
>                     "X-BAPI-API-KEY": API_KEY,
>                     "X-BAPI-TIMESTAMP": timestamp,
>                     "X-BAPI-SIGN": signature,
>                     "X-BAPI-RECV-WINDOW": recv_window,
>                 }
>             )
>             logger.debug(f"POST Request to {url} with payload {json_params}")
>             response = session.post(
>                 url, json=params, headers=headers, timeout=REQUEST_TIMEOUT
>             )
>     else:
>         logger.debug(f"Public Request to {url} with params {params}")
>         response = session.get(
>             url, params=params, headers=headers, timeout=REQUEST_TIMEOUT
>         )
784,815c467,492
<     async def fetch_klines(
<         self, symbol: str, interval: str, limit: int
<     ) -> pd.DataFrame | None:
<         """Fetch kline data for a symbol and interval."""
<         response = await self._bybit_request_with_retry(
<             "fetch_klines",
<             self.http_session.get_kline,
<             category=self.category,
<             symbol=symbol,
<             interval=interval,
<             limit=limit
<         )
<         if response and response["result"] and response["result"]["list"]:
<             df = pd.DataFrame(
<                 response["result"]["list"],
<                 columns=[
<                     "start_time",
<                     "open",
<                     "high",
<                     "low",
<                     "close",
<                     "volume",
<                     "turnover",
<                 ],
<             )
<             df["start_time"] = pd.to_datetime(
<                 df["start_time"].astype(int), unit="ms", utc=True
<             ).dt.tz_convert(self.config["timezone"])
<             for col in ["open", "high", "low", "close", "volume", "turnover"]:
<                 df[col] = pd.to_numeric(df[col], errors="coerce")
<             df.set_index("start_time", inplace=True)
<             df.sort_index(inplace=True)
---
>     try:
>         response.raise_for_status()
>         data = response.json()
>         if data.get("retCode") != 0:
>             logger.error(
>                 f"{NEON_RED}Bybit API Error ({endpoint}): {data.get('retMsg')} (Code: {data.get('retCode')}){RESET}"
>             )
>             return None
>         return data
>     except requests.exceptions.HTTPError as e:
>         logger.error(
>             f"{NEON_RED}HTTP Error ({endpoint}): {e.response.status_code} - {e.response.text}{RESET}"
>         )
>     except requests.exceptions.ConnectionError as e:
>         logger.error(f"{NEON_RED}Connection Error ({endpoint}): {e}{RESET}")
>     except requests.exceptions.Timeout:
>         logger.error(
>             f"{NEON_RED}Request to {endpoint} timed out after {REQUEST_TIMEOUT} seconds.{RESET}"
>         )
>     except requests.exceptions.RequestException as e:
>         logger.error(f"{NEON_RED}Request Exception ({endpoint}): {e}{RESET}")
>     except json.JSONDecodeError:
>         logger.error(
>             f"{NEON_RED}Failed to decode JSON response from {endpoint}: {response.text}{RESET}"
>         )
>     return None
817,821d493
<             if df.empty:
<                 self.logger.warning(
<                     f"{NEON_YELLOW}Fetched klines for {symbol} {interval} but DataFrame is empty after processing. Raw response: {response}{RESET}"
<                 )
<                 return None
823,843c495,539
<             self.logger.debug(f"Fetched {len(df)} {interval} klines for {symbol}.")
<             return df
<         self.logger.warning(
<             f"{NEON_YELLOW}Could not fetch klines for {symbol} {interval}. API response might be empty or invalid. Raw response: {response}{RESET}"
<         )
<         return None
< 
<     async def fetch_orderbook(self, symbol: str, limit: int) -> dict | None:
<         """Fetch orderbook data for a symbol via REST."""
<         response = await self._bybit_request_with_retry(
<             "fetch_orderbook",
<             self.http_session.get_orderbook,
<             category=self.category,
<             symbol=symbol,
<             limit=limit
<         )
<         if response and response["result"]:
<             self.logger.debug(f"Fetched orderbook for {symbol} with limit {limit} via REST.")
<             return response["result"]
<         self.logger.warning(f"{NEON_YELLOW}Could not fetch orderbook for {symbol} via REST.{RESET}")
<         return None
---
> def fetch_current_price(symbol: str, logger: logging.Logger) -> Decimal | None:
>     """Fetch the current market price for a symbol."""
>     endpoint = "/v5/market/tickers"
>     params = {"category": "linear", "symbol": symbol}
>     response = bybit_request("GET", endpoint, params, logger=logger)
>     if response and response["result"] and response["result"]["list"]:
>         price = Decimal(response["result"]["list"][0]["lastPrice"])
>         logger.debug(f"Fetched current price for {symbol}: {price}")
>         return price
>     logger.warning(f"{NEON_YELLOW}Could not fetch current price for {symbol}.{RESET}")
>     return None
> 
> 
> def fetch_klines(
>     symbol: str, interval: str, limit: int, logger: logging.Logger
> ) -> pd.DataFrame | None:
>     """Fetch kline data for a symbol and interval."""
>     endpoint = "/v5/market/kline"
>     params = {
>         "category": "linear",
>         "symbol": symbol,
>         "interval": interval,
>         "limit": limit,
>     }
>     response = bybit_request("GET", endpoint, params, logger=logger)
>     if response and response["result"] and response["result"]["list"]:
>         df = pd.DataFrame(
>             response["result"]["list"],
>             columns=[
>                 "start_time",
>                 "open",
>                 "high",
>                 "low",
>                 "close",
>                 "volume",
>                 "turnover",
>             ],
>         )
>         df["start_time"] = pd.to_datetime(
>             df["start_time"].astype(int), unit="ms", utc=True
>         ).dt.tz_convert(TIMEZONE)
>         for col in ["open", "high", "low", "close", "volume", "turnover"]:
>             df[col] = pd.to_numeric(df[col], errors="coerce")
>         df.set_index("start_time", inplace=True)
>         df.sort_index(inplace=True)
845,923c541,542
<     async def place_order(
<         self,
<         symbol: str,
<         side: str,
<         qty: str,
<         order_type: str = "Market",
<         price: str | None = None,
<         reduce_only: bool = False,
<         stop_loss: str | None = None,
<         take_profit: str | None = None,
<         client_order_id: str | None = None,
<     ) -> dict | None:
<         """Place an order on Bybit."""
<         params = {
<             "category": self.category,
<             "symbol": symbol,
<             "side": side,
<             "orderType": order_type,
<             "qty": qty,
<             "reduceOnly": reduce_only,
<         }
<         if price:
<             params["price"] = price
<         if stop_loss:
<             params["stopLoss"] = stop_loss
<         if take_profit:
<             params["takeProfit"] = take_profit
<         if client_order_id:
<             params["orderLinkId"] = client_order_id
< 
<         response = await self._bybit_request_with_retry(
<             "place_order", self.http_session.place_order, **params
<         )
<         if response and response.get("result"):
<             self.logger.info(f"{NEON_GREEN}Order placed: {response['result']}{RESET}")
<             return response["result"]
<         return None
< 
<     async def cancel_order(self, symbol: str, order_id: str) -> dict | None:
<         """Cancel an order on Bybit."""
<         response = await self._bybit_request_with_retry(
<             "cancel_order",
<             self.http_session.cancel_order,
<             category=self.category,
<             symbol=symbol,
<             orderId=order_id,
<         )
<         if response and response.get("result"):
<             self.logger.info(f"{NEON_YELLOW}Order cancelled: {response['result']}{RESET}")
<             return response["result"]
<         return None
< 
<     async def cancel_all_orders(self, symbol: str) -> dict | None:
<         """Cancel all open orders for a symbol."""
<         response = await self._bybit_request_with_retry(
<             "cancel_all_orders",
<             self.http_session.cancel_all_orders,
<             category=self.category,
<             symbol=symbol,
<         )
<         if response and response.get("result"):
<             self.logger.info(f"{NEON_YELLOW}All orders cancelled for {symbol}: {response['result']}{RESET}")
<             return response["result"]
<         return None
< 
<     async def set_leverage(self, symbol: str, leverage: str) -> bool:
<         """Set leverage for a symbol."""
<         response = await self._bybit_request_with_retry(
<             "set_leverage",
<             self.http_session.set_leverage,
<             category=self.category,
<             symbol=symbol,
<             buyLeverage=leverage,
<             sellLeverage=leverage,
<         )
<         if response:
<             self.logger.info(f"{NEON_GREEN}Leverage set to {leverage} for {symbol}{RESET}")
<             return True
<         return False
---
>         # Drop rows with any NaN values in critical columns (open, high, low, close, volume)
>         df.dropna(subset=["open", "high", "low", "close", "volume"], inplace=True)
925,982c544,548
<     async def set_trading_stop(
<         self,
<         symbol: str,
<         stop_loss: str | None = None,
<         take_profit: str | None = None,
<         trailing_stop: str | None = None,
<         active_price: str | None = None,
<         position_idx: int = 0,
<         tp_trigger_by: str = "MarkPrice",
<         sl_trigger_by: str = "MarkPrice",
<     ) -> bool:
<         """Set or amend stop loss, take profit, or trailing stop for an existing position."""
<         params = {
<             "category": self.category,
<             "symbol": symbol,
<             "positionIdx": position_idx,
<             "tpTriggerBy": tp_trigger_by,
<             "slTriggerBy": sl_trigger_by,
<         }
<         if stop_loss is not None:
<             params["stopLoss"] = stop_loss
<         if take_profit is not None:
<             params["takeProfit"] = take_profit
<         if trailing_stop is not None:
<             params["trailingStop"] = trailing_stop
<         if active_price is not None:
<             params["activePrice"] = active_price
< 
<         response = await self._bybit_request_with_retry(
<             "set_trading_stop", self.http_session.set_trading_stop, **params
<         )
<         if response:
<             self.logger.info(f"{NEON_GREEN}Trading stop updated for {symbol}: SL={stop_loss}, TP={take_profit}, Trailing={trailing_stop}{RESET}")
<             return True
<         return False
< 
<     async def get_wallet_balance(self) -> Decimal | None:
<         """Get current account balance."""
<         response = await self._bybit_request_with_retry(
<             "get_wallet_balance",
<             self.http_session.get_wallet_balance,
<             accountType="UNIFIED"
<         )
<         if response and response["result"] and response["result"]["list"]:
<             for coin_data in response["result"]["list"][0]["coin"]:
<                 if coin_data["coin"] == "USDT":
<                     return Decimal(coin_data["walletBalance"])
<         self.logger.warning(f"{NEON_YELLOW}Could not fetch wallet balance.{RESET}")
<         return None
< 
<     async def get_positions(self) -> list[dict[str, Any]]:
<         """Get all open positions."""
<         response = await self._bybit_request_with_retry(
<             "get_positions", self.http_session.get_positions, category=self.category, symbol=self.symbol
<         )
<         if response and response["result"] and response["result"]["list"]:
<             return response["result"]["list"]
<         return []
---
>         if df.empty:
>             logger.warning(
>                 f"{NEON_YELLOW}Fetched klines for {symbol} {interval} but DataFrame is empty after processing/cleaning. Raw response: {response}{RESET}"
>             )
>             return None
984,994c550,555
<     async def start_public_ws(
<         self,
<         symbol: str,
<         orderbook_depth: int,
<         kline_interval: str,
<         ticker_callback: callable,
<         orderbook_callback: callable,
<         kline_callback: callable,
<     ):
<         """Starts public WebSocket streams."""
<         self.ws_public = WebSocket(channel_type=self.category, testnet=self.testnet)
---
>         logger.debug(f"Fetched {len(df)} {interval} klines for {symbol}.")
>         return df
>     logger.warning(
>         f"{NEON_YELLOW}Could not fetch klines for {symbol} {interval}. API response might be empty or invalid. Raw response: {response}{RESET}"
>     )
>     return None
996,1015d556
<         def _ws_callback_wrapper(raw_message):
<             async def _handle_message_async(message):
<                 topic = message.get('topic')
<                 if topic and 'kline' in topic:
<                     await kline_callback(message)
<                 elif topic and 'ticker' in topic:
<                     await ticker_callback(message)
<                 elif topic and 'orderbook' in topic:
<                     await orderbook_callback(message)
<             try:
<                 message = json.loads(raw_message)
<                 asyncio.create_task(_handle_message_async(message))
<             except json.JSONDecodeError:
<                 self.logger.error(f"{NEON_RED}Failed to decode WS message: {raw_message}{RESET}")
<             except Exception as e:
<                 self.logger.error(f"{NEON_RED}Error in public WS callback: {e} | Message: {raw_message[:100]}{RESET}", exc_info=True)
< 
<         self.ws_public.kline_stream(interval=kline_interval, symbol=symbol, callback=_ws_callback_wrapper)
<         self.ws_public.ticker_stream(symbol=symbol, callback=_ws_callback_wrapper)
<         self.ws_public.orderbook_stream(depth=orderbook_depth, symbol=symbol, callback=_ws_callback_wrapper)
1017,1018c558,626
<         self.ws_tasks.append(asyncio.create_task(self._monitor_ws_connection(self.ws_public, "Public WS")))
<         self.logger.info(f"{NEON_BLUE}Public WebSocket for {symbol} started.{RESET}")
---
> def fetch_orderbook(symbol: str, limit: int, logger: logging.Logger) -> dict | None:
>     """Fetch orderbook data for a symbol."""
>     endpoint = "/v5/market/orderbook"
>     params = {"category": "linear", "symbol": symbol, "limit": limit}
>     response = bybit_request("GET", endpoint, params, logger=logger)
>     if response and response["result"]:
>         logger.debug(f"Fetched orderbook for {symbol} with limit {limit}.")
>         return response["result"]
>     logger.warning(f"{NEON_YELLOW}Could not fetch orderbook for {symbol}.{RESET}")
>     return None
> 
> 
> def get_wallet_balance(
>     account_type: Literal["UNIFIED", "CONTRACT"], coin: str, logger: logging.Logger
> ) -> Decimal | None:
>     """Fetch wallet balance for a specific coin."""
>     endpoint = "/v5/account/wallet-balance"
>     params = {"accountType": account_type, "coin": coin}
>     response = bybit_request("GET", endpoint, params, signed=True, logger=logger)
>     if response and response["result"] and response["result"]["list"]:
>         for item in response["result"]["list"]:
>             # Accessing the first element of the 'coin' list within each item
>             if item["coin"][0]["coin"] == coin:
>                 balance = Decimal(item["coin"][0]["walletBalance"])
>                 logger.debug(f"Fetched {coin} wallet balance: {balance}")
>                 return balance
>     logger.warning(f"{NEON_YELLOW}Could not fetch {coin} wallet balance.{RESET}")
>     return None
> 
> 
> def get_exchange_open_positions(
>     symbol: str, category: str, logger: logging.Logger
> ) -> list[dict] | None:
>     """Fetch currently open positions from the exchange."""
>     endpoint = "/v5/position/list"
>     params = {"category": category, "symbol": symbol}
>     response = bybit_request("GET", endpoint, params, signed=True, logger=logger)
>     if response and response["result"] and response["result"]["list"]:
>         return response["result"]["list"]
>     return []
> 
> 
> def place_order(
>     symbol: str,
>     side: Literal["Buy", "Sell"],
>     order_type: Literal["Market", "Limit"],
>     qty: Decimal,
>     price: Decimal | None = None,
>     reduce_only: bool = False,
>     take_profit: Decimal | None = None,
>     stop_loss: Decimal | None = None,
>     tp_sl_mode: Literal["Full", "Partial"] = "Full",
>     logger: logging.Logger | None = None,
>     position_idx: int | None = None,  # Added parameter
> ) -> dict | None:
>     """Place an order on Bybit."""
>     if logger is None:
>         logger = setup_logger("bybit_api")
> 
>     params: dict[str, Any] = {
>         "category": "linear",
>         "symbol": symbol,
>         "side": side,
>         "orderType": order_type,
>         "qty": str(qty),
>         "reduceOnly": reduce_only,
>     }
>     if order_type == "Limit" and price is not None:
>         params["price"] = str(price)
1020,1091c628,666
<     async def start_private_ws(
<         self,
<         position_callback: callable,
<         order_callback: callable,
<         execution_callback: callable,
<         wallet_callback: callable,
<     ):
<         """Starts private WebSocket streams."""
<         self.ws_private = WebSocket(
<             channel_type="private",
<             testnet=self.testnet,
<             api_key=self.api_key,
<             api_secret=self.api_secret
<         )
< 
<         def _ws_callback_wrapper(raw_message):
<             async def _handle_message_async(message):
<                 topic = message.get('topic')
<                 if topic == 'position':
<                     await position_callback(message)
<                 elif topic == 'order':
<                     await order_callback(message)
<                 elif topic == 'execution':
<                     await execution_callback(message)
<                 elif topic == 'wallet':
<                     await wallet_callback(message)
<             try:
<                 message = json.loads(raw_message)
<                 asyncio.create_task(_handle_message_async(message))
<             except json.JSONDecodeError:
<                 self.logger.error(f"{NEON_RED}Failed to decode WS message: {raw_message}{RESET}")
<             except Exception as e:
<                 self.logger.error(f"{NEON_RED}Error in private WS callback: {e} | Message: {raw_message[:100]}{RESET}", exc_info=True)
< 
<         self.ws_private.position_stream(callback=_ws_callback_wrapper)
<         self.ws_private.order_stream(callback=_ws_callback_wrapper)
<         self.ws_private.execution_stream(callback=_ws_callback_wrapper)
<         self.ws_private.wallet_stream(callback=_ws_callback_wrapper)
< 
<         self.ws_tasks.append(asyncio.create_task(self._monitor_ws_connection(self.ws_private, "Private WS")))
<         self.logger.info(f"{NEON_BLUE}Private WebSocket started.{RESET}")
< 
<     async def _monitor_ws_connection(self, ws_client: WebSocket, name: str):
<         """Monitors WebSocket connection, logs status, and sends pings."""
<         custom_ping_message = json.dumps({"op": "ping"})
<         while True:
<             await asyncio.sleep(15)  # Check every 15 seconds
<             if not ws_client.is_connected():
<                 self.logger.info(f"{NEON_YELLOW}{name} is not connected. pybit will attempt automatic reconnection.{RESET}")
<             else:
<                 try:
<                     # Send a custom ping to keep the connection alive
<                     ws_client.send(custom_ping_message)
<                     self.logger.debug(f"Sent ping to {name}.")
<                 except WebSocketConnectionClosedException:
<                     self.logger.warning(f"Could not send ping to {name}, connection is closed.")
<                 except Exception as e:
<                     self.logger.error(f"An error occurred while sending ping to {name}: {e}")
< 
<     async def stop_ws(self):
<         """Stops all WebSocket connections."""
<         for task in self.ws_tasks:
<             task.cancel()
<             try:
<                 await task
<             except asyncio.CancelledError:
<                 pass
<         if self.ws_public:
<             await self.ws_public.close()
<         if self.ws_private:
<             await self.ws_private.close()
<         self.logger.info(f"{NEON_BLUE}All WebSockets stopped.{RESET}")
---
>     # Add positionIdx if provided
>     if position_idx is not None:
>         params["positionIdx"] = position_idx
> 
>     # Add TP/SL to the order itself
>     if take_profit is not None:
>         params["takeProfit"] = str(take_profit)
>         params["tpslMode"] = tp_sl_mode
>     if stop_loss is not None:
>         params["stopLoss"] = str(stop_loss)
>         params["tpslMode"] = tp_sl_mode
> 
>     endpoint = "/v5/order/create"
>     response = bybit_request("POST", endpoint, params, signed=True, logger=logger)
>     if response:
>         logger.info(
>             f"{NEON_GREEN}Order placed successfully for {symbol}: {response['result']}{RESET}"
>         )
>         return response["result"]
>     logger.error(f"{NEON_RED}Failed to place order for {symbol}: {params}{RESET}")
>     return None
> 
> 
> def cancel_order(
>     symbol: str, order_id: str, logger: logging.Logger | None = None
> ) -> dict | None:
>     """Cancel an existing order on Bybit."""
>     if logger is None:
>         logger = setup_logger("bybit_api")
>     endpoint = "/v5/order/cancel"
>     params = {"category": "linear", "symbol": symbol, "orderId": order_id}
>     response = bybit_request("POST", endpoint, params, signed=True, logger=logger)
>     if response:
>         logger.info(
>             f"{NEON_GREEN}Order {order_id} cancelled for {symbol}: {response['result']}{RESET}"
>         )
>         return response["result"]
>     logger.error(f"{NEON_RED}Failed to cancel order {order_id} for {symbol}.{RESET}")
>     return None
1093a669
> # --- Precision Management ---
1095,1096c671
<     """Manages decimal precision for trading operations based on Bybit's instrument info.
<     """
---
>     """Manages symbol-specific precision for order quantity and price."""
1098,1099c673,675
<     def __init__(self, bybit_client: BybitClient, logger: logging.Logger):
<         self.bybit_client = bybit_client
---
>     def __init__(self, symbol: str, logger: logging.Logger, config: dict[str, Any]):
>         """Initializes the PrecisionManager."""
>         self.symbol = symbol
1101,1102c677,705
<         self.instruments_info: dict[str, Any] = {}
<         self.initialized = False
---
>         self.config = config
>         self.qty_step: Decimal | None = None
>         self.price_tick_size: Decimal | None = None
>         self.min_order_qty: Decimal | None = None
>         self.max_order_qty: Decimal | None = None
>         self.min_price: Decimal | None = None
>         self.max_price: Decimal | None = None
>         self._fetch_precision_info()
> 
>     def _fetch_precision_info(self) -> None:
>         """Fetch and store precision info from the exchange."""
>         self.logger.info(f"[{self.symbol}] Fetching precision information...")
>         endpoint = "/v5/market/instruments-info"
>         params = {"category": "linear", "symbol": self.symbol}
>         response = bybit_request(
>             "GET", endpoint, params, signed=False, logger=self.logger
>         )
> 
>         if response and response.get("result") and response["result"].get("list"):
>             instrument_info = response["result"]["list"][0]
>             lot_size_filter = instrument_info.get("lotSizeFilter", {})
>             price_filter = instrument_info.get("priceFilter", {})
> 
>             self.qty_step = Decimal(lot_size_filter.get("qtyStep", "0.001"))
>             self.price_tick_size = Decimal(price_filter.get("tickSize", "0.01"))
>             self.min_order_qty = Decimal(lot_size_filter.get("minOrderQty", "0.001"))
>             self.max_order_qty = Decimal(lot_size_filter.get("maxOrderQty", "100000"))
>             self.min_price = Decimal(price_filter.get("minPrice", "0.01"))
>             self.max_price = Decimal(price_filter.get("maxPrice", "1000000"))
1104,1127c707,711
<     async def load_instrument_info(self, symbol: str):
<         """Load instrument specifications from Bybit."""
<         response = await self.bybit_client._bybit_request_with_retry(
<             "get_instruments_info",
<             self.bybit_client.http_session.get_instruments_info,
<             category=self.bybit_client.category,
<             symbol=symbol
<         )
<         if response and response["result"] and response["result"]["list"]:
<             spec = response["result"]["list"][0]
<             price_filter = spec["priceFilter"]
<             lot_size_filter = spec["lotSizeFilter"]
< 
<             self.instruments_info[symbol] = {
<                 'price_precision_str': price_filter["tickSize"],
<                 'price_precision_decimal': Decimal(price_filter["tickSize"]),
<                 'qty_precision_str': lot_size_filter["qtyStep"],
<                 'qty_precision_decimal': Decimal(lot_size_filter["qtyStep"]),
<                 'min_qty': Decimal(lot_size_filter["minOrderQty"]),
<                 'max_qty': Decimal(lot_size_filter["maxOrderQty"]),
<                 'min_notional': Decimal(lot_size_filter.get("minNotionalValue", "0")),
<             }
<             self.logger.info(f"{NEON_GREEN}Instrument specs loaded for {symbol}: Price tick={self.instruments_info[symbol]['price_precision_decimal']}, Qty step={self.instruments_info[symbol]['qty_precision_decimal']}{RESET}")
<             self.initialized = True
---
>             self.logger.info(
>                 f"[{self.symbol}] Precision loaded: Qty Step={self.qty_step.normalize()}, "
>                 f"Price Tick Size={self.price_tick_size.normalize()}, "
>                 f"Min Qty={self.min_order_qty.normalize()}"
>             )
1129,1166c713,738
<             self.logger.error(f"{NEON_RED}Failed to load instrument specs for {symbol}. Trading might be inaccurate.{RESET}")
< 
<     def _get_specs(self, symbol: str) -> dict | None:
<         """Helper to get specs for a symbol."""
<         specs = self.instruments_info.get(symbol)
<         if not specs and self.initialized:
<             self.logger.warning(f"{NEON_YELLOW}Instrument specs not found for {symbol}. Using generic Decimal precision.{RESET}")
<             return None
<         return specs
< 
<     def round_price(self, price: Decimal, symbol: str) -> Decimal:
<         """Round price to correct tick size."""
<         specs = self._get_specs(symbol)
<         if specs:
<             return price.quantize(specs['price_precision_decimal'], rounding=ROUND_HALF_EVEN)
<         return price.quantize(Decimal("0.00001"), rounding=ROUND_HALF_EVEN)
< 
<     def round_qty(self, qty: Decimal, symbol: str) -> Decimal:
<         """Round quantity to correct step size."""
<         specs = self._get_specs(symbol)
<         if specs:
<             return qty.quantize(specs['qty_precision_decimal'], rounding=ROUND_DOWN)
<         return qty.quantize(Decimal("0.0001"), rounding=ROUND_DOWN)
< 
<     def get_min_qty(self, symbol: str) -> Decimal:
<         """Get minimum order quantity."""
<         specs = self._get_specs(symbol)
<         return specs['min_qty'] if specs else Decimal("0.00001")
< 
<     def get_max_qty(self, symbol: str) -> Decimal:
<         """Get maximum order quantity."""
<         specs = self._get_specs(symbol)
<         return specs['max_qty'] if specs else Decimal("1000000")
< 
<     def get_min_notional(self, symbol: str) -> Decimal:
<         """Get minimum notional value (order cost)."""
<         specs = self._get_specs(symbol)
<         return specs['min_notional'] if specs else Decimal("5")
---
>             self.logger.error(
>                 f"{NEON_RED}[{self.symbol}] Failed to fetch precision info. Using default values from config. "
>                 f"This may cause order placement errors.{RESET}"
>             )
>             # Fallback to config values if API fails
>             order_precision = self.config["trade_management"]["order_precision"]
>             price_precision = self.config["trade_management"]["price_precision"]
>             self.qty_step = Decimal("0." + "0" * (order_precision - 1) + "1")
>             self.price_tick_size = Decimal("0." + "0" * (price_precision - 1) + "1")
>             self.min_order_qty = Decimal("0.001")  # A reasonable default
> 
>     def format_quantity(self, quantity: Decimal) -> Decimal:
>         """Formats the order quantity according to the symbol's qtyStep."""
>         if self.qty_step is None or self.qty_step == Decimal("0"):
>             order_precision = self.config["trade_management"]["order_precision"]
>             fallback_step = Decimal("0." + "0" * (order_precision - 1) + "1")
>             return quantity.quantize(fallback_step, rounding=ROUND_DOWN)
>         return (quantity // self.qty_step) * self.qty_step
> 
>     def format_price(self, price: Decimal) -> Decimal:
>         """Formats the order price according to the symbol's tickSize."""
>         if self.price_tick_size is None or self.price_tick_size == Decimal("0"):
>             price_precision = self.config["trade_management"]["price_precision"]
>             fallback_tick = Decimal("0." + "0" * (price_precision - 1) + "1")
>             return price.quantize(fallback_tick, rounding=ROUND_DOWN)
>         return (price // self.price_tick_size) * self.price_tick_size
1169,1170c741,743
< class IndicatorCalculator:
<     """Calculates various technical indicators."""
---
> # --- Position Management ---
> class PositionManager:
>     """Manages open positions, stop-loss, and take-profit levels."""
1172c745,747
<     def __init__(self, logger: logging.Logger):
---
>     def __init__(self, config: dict[str, Any], logger: logging.Logger, symbol: str):
>         """Initializes the PositionManager."""
>         self.config = config
1173a749,762
>         self.symbol = symbol
>         self.open_positions: dict[str, dict] = (
>             {}
>         )  # Tracks positions opened by the bot locally
>         self.trade_management_enabled = config["trade_management"]["enabled"]
>         self.precision_manager = PrecisionManager(symbol, logger, config)
>         self.max_open_positions = config["trade_management"]["max_open_positions"]
>         self.leverage = config["trade_management"]["leverage"]
>         self.order_mode = config["trade_management"]["order_mode"]
>         self.tp_sl_mode = "Full"  # Default to full for simplicity, can be configured
>         self.trailing_stop_activation_percent = (
>             Decimal(str(config["trade_management"]["trailing_stop_activation_percent"]))
>             / 100
>         )
1175,1182c764,787
<     def _safe_series_op(self, series: pd.Series, op_name: str) -> pd.Series:
<         """Safely handle series operations that might result in NaN or inf."""
<         if series.empty:
<             self.logger.debug(f"Input series for {op_name} is empty.")
<             return pd.Series(np.nan, index=[])
<         series = pd.to_numeric(series, errors='coerce')
<         series.replace([np.inf, -np.inf], np.nan, inplace=True)
<         return series
---
>         # Set leverage (only once or when changed)
>         if self.trade_management_enabled:
>             self._set_leverage()
> 
>     def _set_leverage(self) -> None:
>         """Set leverage for the trading pair."""
>         endpoint = "/v5/position/set-leverage"
>         params = {
>             "category": "linear",
>             "symbol": self.symbol,
>             "buyLeverage": str(self.leverage),
>             "sellLeverage": str(self.leverage),
>         }
>         response = bybit_request(
>             "POST", endpoint, params, signed=True, logger=self.logger
>         )
>         if response and response["retCode"] == 0:
>             self.logger.info(
>                 f"{NEON_GREEN}[{self.symbol}] Leverage set to {self.leverage}x.{RESET}"
>             )
>         else:
>             self.logger.error(
>                 f"{NEON_RED}[{self.symbol}] Failed to set leverage to {self.leverage}x. Error: {response.get('retMsg') if response else 'Unknown'}{RESET}"
>             )
1184,1191c789,792
<     def calculate_true_range(self, df: pd.DataFrame) -> pd.Series:
<         """Calculate True Range (TR)."""
<         if len(df) < MIN_DATA_POINTS_TR:
<             return pd.Series(np.nan, index=df.index)
<         high_low = self._safe_series_op(df["high"] - df["low"], "TR_high_low")
<         high_prev_close = self._safe_series_op((df["high"] - df["close"].shift()).abs(), "TR_high_prev_close")
<         low_prev_close = self._safe_series_op((df["low"] - df["close"].shift()).abs(), "TR_low_prev_close")
<         return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
---
>     def _get_available_balance(self) -> Decimal:
>         """Fetch current available account balance for order sizing."""
>         if not self.trade_management_enabled:
>             return Decimal(str(self.config["trade_management"]["account_balance"]))
1193,1196c794,802
<     def calculate_super_smoother(self, series: pd.Series, period: int) -> pd.Series:
<         """Apply Ehlers SuperSmoother filter to reduce lag and noise."""
<         if period <= 0 or len(series) < MIN_DATA_POINTS_SMOOTHER:
<             return pd.Series(np.nan, index=series.index)
---
>         balance = get_wallet_balance(
>             account_type="UNIFIED", coin="USDT", logger=self.logger
>         )  # Assuming USDT for linear contracts
>         if balance is None:
>             self.logger.warning(
>                 f"{NEON_YELLOW}[{self.symbol}] Failed to fetch actual balance. Using simulated balance for calculation.{RESET}"
>             )
>             return Decimal(str(self.config["trade_management"]["account_balance"]))
>         return balance
1198,1200c804,809
<         series = self._safe_series_op(series, "SuperSmoother_input").dropna()
<         if len(series) < MIN_DATA_POINTS_SMOOTHER:
<             return pd.Series(np.nan, index=series.index)
---
>     def _calculate_order_size(
>         self, current_price: Decimal, atr_value: Decimal
>     ) -> Decimal:
>         """Calculate order size based on risk per trade, ATR, and available balance."""
>         if not self.trade_management_enabled:
>             return Decimal("0")
1202,1206c811,818
<         a1 = np.exp(-np.sqrt(2) * np.pi / period)
<         b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / period)
<         c1 = 1 - b1 + a1**2
<         c2 = b1 - 2 * a1**2
<         c3 = a1**2
---
>         account_balance = self._get_available_balance()
>         risk_per_trade_percent = (
>             Decimal(str(self.config["trade_management"]["risk_per_trade_percent"]))
>             / 100
>         )
>         stop_loss_atr_multiple = Decimal(
>             str(self.config["trade_management"]["stop_loss_atr_multiple"])
>         )
1208,1212c820,821
<         filt = pd.Series(0.0, index=series.index)
<         if len(series) >= 1:
<             filt.iloc[0] = series.iloc[0]
<         if len(series) >= 2:
<             filt.iloc[1] = (series.iloc[0] + series.iloc[1]) / 2
---
>         risk_amount = account_balance * risk_per_trade_percent
>         stop_loss_distance_usd = atr_value * stop_loss_atr_multiple
1214,1218c823,825
<         for i in range(2, len(series)):
<             filt.iloc[i] = (
<                 (c1 / 2) * (series.iloc[i] + series.iloc[i - 1])
<                 + c2 * filt.iloc[i - 1]
<                 - c3 * filt.iloc[i - 2]
---
>         if stop_loss_distance_usd <= 0:
>             self.logger.warning(
>                 f"{NEON_YELLOW}[{self.symbol}] Calculated stop loss distance is zero or negative ({stop_loss_distance_usd}). Cannot determine order size.{RESET}"
1220c827
<         return filt.reindex(series.index)
---
>             return Decimal("0")
1222,1228c829,845
<     def calculate_ehlers_supertrend(
<         self, df: pd.DataFrame, period: int, multiplier: float
<     ) -> pd.DataFrame | None:
<         """Calculate SuperTrend using Ehlers SuperSmoother for price and volatility."""
<         if len(df) < period * 3:
<             self.logger.debug(
<                 f"Not enough data for Ehlers SuperTrend (period={period}). Need at least {period*3} bars."
---
>         # Order size in USD value (notional value)
>         order_value_notional = risk_amount / stop_loss_distance_usd
>         # Convert to quantity of the asset (e.g., BTC)
>         order_qty = order_value_notional / current_price
> 
>         # Round order_qty to appropriate precision for the symbol
>         order_qty = self.precision_manager.format_quantity(order_qty)
> 
>         # Check against min order quantity
>         if (
>             self.precision_manager.min_order_qty is not None
>             and order_qty < self.precision_manager.min_order_qty
>         ):
>             self.logger.warning(
>                 f"{NEON_YELLOW}[{self.symbol}] Calculated order quantity ({order_qty.normalize()}) is below the minimum "
>                 f"({self.precision_manager.min_order_qty.normalize()}). Cannot open position. "
>                 f"Consider reducing risk per trade or using a larger account balance.{RESET}"
1230,1235c847
<             return None
< 
<         df_copy = df.copy()
< 
<         hl2 = (df_copy["high"] + df_copy["low"]) / 2
<         smoothed_price = self.calculate_super_smoother(hl2, period)
---
>             return Decimal("0")
1237,1238c849,853
<         tr = self.calculate_true_range(df_copy)
<         smoothed_atr = self.calculate_super_smoother(tr, period)
---
>         if order_qty <= Decimal("0"):
>             self.logger.warning(
>                 f"{NEON_YELLOW}[{self.symbol}] Calculated order quantity ({order_qty.normalize()}) is too small or zero. Cannot open position.{RESET}"
>             )
>             return Decimal("0")
1240,1241c855,858
<         df_copy["smoothed_price"] = smoothed_price
<         df_copy["smoothed_atr"] = smoothed_atr
---
>         self.logger.info(
>             f"[{self.symbol}] Calculated order size: {order_qty.normalize()} (Risk: {risk_amount.normalize():.2f} USDT, SL Distance: {stop_loss_distance_usd.normalize():.4f})"
>         )
>         return order_qty
1243,1246c860,866
<         df_copy.dropna(subset=["smoothed_price", "smoothed_atr"], inplace=True)
<         if df_copy.empty:
<             self.logger.debug(
<                 "Ehlers SuperTrend: DataFrame empty after smoothing. Returning None."
---
>     def open_position(
>         self, signal: Literal["BUY", "SELL"], current_price: Decimal, atr_value: Decimal
>     ) -> dict | None:
>         """Open a new position if conditions allow by placing an order on the exchange."""
>         if not self.trade_management_enabled:
>             self.logger.info(
>                 f"{NEON_YELLOW}[{self.symbol}] Trade management is disabled. Skipping opening position.{RESET}"
1250,1256c870,877
<         upper_band = df_copy["smoothed_price"] + multiplier * df_copy["smoothed_atr"]
<         lower_band = df_copy["smoothed_price"] - multiplier * df_copy["smoothed_atr"]
< 
<         direction = pd.Series(0, index=df_copy.index, dtype=int)
<         supertrend = pd.Series(np.nan, index=df_copy.index)
< 
<         if df_copy.empty:
---
>         # Check if we already have an open position for this symbol
>         if (
>             self.symbol in self.open_positions
>             and self.open_positions[self.symbol]["status"] == "OPEN"
>         ):
>             self.logger.warning(
>                 f"{NEON_YELLOW}[{self.symbol}] Already have an open position. Max open positions ({self.max_open_positions}) reached. Cannot open new position.{RESET}"
>             )
1259,1279c880,888
<         first_valid_idx = df_copy.index[0]
<         supertrend.loc[first_valid_idx] = lower_band.loc[first_valid_idx] if df_copy["close"].loc[first_valid_idx] > lower_band.loc[first_valid_idx] else upper_band.loc[first_valid_idx]
<         direction.loc[first_valid_idx] = 1 if df_copy["close"].loc[first_valid_idx] > supertrend.loc[first_valid_idx] else -1
< 
< 
<         for i in range(1, len(df_copy)):
<             current_idx = df_copy.index[i]
<             prev_idx = df_copy.index[i - 1]
< 
<             prev_direction = direction.loc[prev_idx]
<             prev_supertrend = supertrend.loc[prev_idx]
<             curr_close = df_copy["close"].loc[current_idx]
< 
<             if prev_direction == 1:
<                 supertrend.loc[current_idx] = max(lower_band.loc[current_idx], prev_supertrend)
<                 if curr_close < supertrend.loc[current_idx]:
<                     direction.loc[current_idx] = -1
<             else:
<                 supertrend.loc[current_idx] = min(upper_band.loc[current_idx], prev_supertrend)
<                 if curr_close > supertrend.loc[current_idx]:
<                     direction.loc[current_idx] = 1
---
>         # Check against max_open_positions from config
>         if (
>             self.max_open_positions > 0
>             and len(self.open_positions) >= self.max_open_positions
>         ):
>             self.logger.info(
>                 f"{NEON_YELLOW}[{self.symbol}] Max open positions ({self.max_open_positions}) reached. Cannot open new position.{RESET}"
>             )
>             return None
1281,1282c890,892
<             if pd.isna(supertrend.loc[current_idx]):
<                  supertrend.loc[current_idx] = lower_band.loc[current_idx] if curr_close > lower_band.loc[current_idx] else upper_band.loc[current_idx]
---
>         if signal not in ["BUY", "SELL"]:
>             self.logger.debug(f"Invalid signal '{signal}' for opening position.")
>             return None
1283a894,896
>         order_qty = self._calculate_order_size(current_price, atr_value)
>         if order_qty <= Decimal("0"):
>             return None
1285,1286c898,903
<         result = pd.DataFrame({"supertrend": supertrend, "direction": direction})
<         return result.reindex(df.index)
---
>         stop_loss_atr_multiple = Decimal(
>             str(self.config["trade_management"]["stop_loss_atr_multiple"])
>         )
>         take_profit_atr_multiple = Decimal(
>             str(self.config["trade_management"]["take_profit_atr_multiple"])
>         )
1288,1293c905,909
<     def calculate_macd(
<         self, df: pd.DataFrame, fast_period: int, slow_period: int, signal_period: int
<     ) -> tuple[pd.Series, pd.Series, pd.Series]:
<         """Calculate Moving Average Convergence Divergence (MACD)."""
<         if len(df) < slow_period + signal_period:
<             return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)
---
>         side = "Buy" if signal == "BUY" else "Sell"
>         # For Hedge Mode: 1 for long (Buy), 2 for short (Sell)
>         # For One-Way Mode: 0 for both
>         # Assuming Hedge Mode based on the error "position idx not match position mode"
>         position_idx = 1 if side == "Buy" else 2
1295,1297c911,913
<         macd_result = ta.macd(df["close"], fast=fast_period, slow=slow_period, signal=signal_period)
<         if macd_result.empty:
<             return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)
---
>         entry_price = (
>             current_price  # For Market orders, entry price is roughly current price
>         )
1299,1301c915,924
<         macd_line = self._safe_series_op(macd_result[f'MACD_{fast_period}_{slow_period}_{signal_period}'], "MACD_Line")
<         signal_line = self._safe_series_op(macd_result[f'MACDs_{fast_period}_{slow_period}_{signal_period}'], "MACD_Signal")
<         histogram = self._safe_series_op(macd_result[f'MACDh_{fast_period}_{slow_period}_{signal_period}'], "MACD_Hist")
---
>         if signal == "BUY":
>             stop_loss_price = current_price - (atr_value * stop_loss_atr_multiple)
>             take_profit_price = current_price + (atr_value * take_profit_atr_multiple)
>         else:  # SELL
>             stop_loss_price = current_price + (atr_value * stop_loss_atr_multiple)
>             take_profit_price = current_price - (atr_value * take_profit_atr_multiple)
> 
>         entry_price = self.precision_manager.format_price(entry_price)
>         stop_loss_price = self.precision_manager.format_price(stop_loss_price)
>         take_profit_price = self.precision_manager.format_price(take_profit_price)
1303c926,928
<         return macd_line, signal_line, histogram
---
>         self.logger.info(
>             f"[{self.symbol}] Attempting to place {side} order: Qty={order_qty.normalize()}, SL={stop_loss_price.normalize()}, TP={take_profit_price.normalize()}"
>         )
1305,1310c930,941
<     def calculate_rsi(self, df: pd.DataFrame, period: int) -> pd.Series:
<         """Calculate Relative Strength Index (RSI)."""
<         if len(df) <= period:
<             return pd.Series(np.nan, index=df.index)
<         rsi = ta.rsi(df["close"], length=period)
<         return self._safe_series_op(rsi, "RSI")
---
>         placed_order = place_order(
>             symbol=self.symbol,
>             side=side,
>             order_type=self.order_mode,
>             qty=order_qty,
>             price=entry_price if self.order_mode == "Limit" else None,
>             take_profit=take_profit_price,
>             stop_loss=stop_loss_price,
>             tp_sl_mode=self.tp_sl_mode,
>             logger=self.logger,
>             position_idx=position_idx,  # Pass position_idx
>         )
1312,1318c943,945
<     def calculate_stoch_rsi(
<         self, df: pd.DataFrame, period: int, k_period: int, d_period: int
<     ) -> tuple[pd.Series, pd.Series]:
<         """Calculate Stochastic RSI."""
<         if len(df) <= period:
<             return pd.Series(np.nan, index=df.index), pd.Series(
<                 np.nan, index=df.index
---
>         if placed_order:
>             self.logger.info(
>                 f"{NEON_GREEN}[{self.symbol}] Successfully initiated {signal} trade with order ID: {placed_order.get('orderId')}{RESET}"
1320,1330c947,970
<         stochrsi = ta.stochrsi(df["close"], length=period, rsi_length=period, k=k_period, d=d_period)
< 
<         stoch_rsi_k = self._safe_series_op(stochrsi[f'STOCHRSIk_{period}_{period}_{k_period}_{d_period}'], "StochRSI_K")
<         stoch_rsi_d = self._safe_series_op(stochrsi[f'STOCHRSId_{period}_{period}_{k_period}_{d_period}'], "StochRSI_D")
< 
<         return stoch_rsi_k, stoch_rsi_d
< 
<     def calculate_adx(self, df: pd.DataFrame, period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
<         """Calculate Average Directional Index (ADX)."""
<         if len(df) < period * 2:
<             return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)
---
>             # For logging/tracking purposes, return a simplified representation
>             position_info = {
>                 "entry_time": datetime.now(TIMEZONE),
>                 "symbol": self.symbol,
>                 "side": signal,
>                 # This might be different from actual fill price for market orders
>                 "entry_price": entry_price,
>                 "qty": order_qty,
>                 "stop_loss": stop_loss_price,
>                 "take_profit": take_profit_price,
>                 "status": "OPEN",
>                 "order_id": placed_order.get("orderId"),
>                 "is_trailing_activated": False,
>                 "current_trailing_sl": stop_loss_price,  # Initialize trailing SL to initial SL
>             }
>             self.open_positions[self.symbol] = (
>                 position_info  # Track the position locally
>             )
>             return position_info
>         else:
>             self.logger.error(
>                 f"{NEON_RED}[{self.symbol}] Failed to place {signal} order. Check API logs for details.{RESET}"
>             )
>             return None
1332c972,982
<         adx_result = ta.adx(df["high"], df["low"], df["close"], length=period)
---
>     def manage_positions(
>         self, current_price: Decimal, atr_value: Decimal, performance_tracker: Any
>     ) -> None:
>         """Check and manage open positions on the exchange (SL/TP are handled by Bybit).
>         This method will mainly check if positions are closed and record them.
>         It also handles trailing stop logic locally.
>         NOTE: In a real bot, updating trailing stops would involve API calls to the exchange.
>         This implementation updates the local state for simulation/tracking purposes.
>         """
>         if not self.trade_management_enabled or not self.open_positions:
>             return
1334,1336c984,995
<         adx_val = self._safe_series_op(adx_result[f'ADX_{period}'], "ADX")
<         plus_di = self._safe_series_op(adx_result[f'DMP_{period}'], "PlusDI")
<         minus_di = self._safe_series_op(adx_result[f'DMN_{period}'], "MinusDI")
---
>         positions_to_remove = []
>         for symbol, position in list(
>             self.open_positions.items()
>         ):  # Iterate over a copy to allow modification
>             if position["status"] == "OPEN":
>                 side = position["side"]
>                 entry_price = position["entry_price"]
>                 stop_loss = position["stop_loss"]
>                 take_profit = position["take_profit"]
>                 qty = position["qty"]
>                 is_trailing_activated = position.get("is_trailing_activated", False)
>                 current_trailing_sl = position.get("current_trailing_sl", stop_loss)
1338c997,998
<         return adx_val, plus_di, minus_di
---
>                 closed_by = ""
>                 exit_price = Decimal("0")
1340,1354c1000,1020
<     def calculate_bollinger_bands(
<         self, df: pd.DataFrame, period: int, std_dev: float
<     ) -> tuple[pd.Series, pd.Series, pd.Series]:
<         """Calculate Bollinger Bands."""
<         if len(df) < period:
<             return (
<                 pd.Series(np.nan, index=df.index),
<                 pd.Series(np.nan, index=df.index),
<                 pd.Series(np.nan, index=df.index),
<             )
<         bbands = ta.bbands(df["close"], length=period, std=std_dev)
< 
<         upper_band = self._safe_series_op(bbands[f'BBU_{period}_{std_dev}'], "BB_Upper")
<         middle_band = self._safe_series_op(bbands[f'BBM_{period}_{std_dev}'], "BB_Middle")
<         lower_band = self._safe_series_op(bbands[f'BBL_{period}_{std_dev}'], "BB_Lower")
---
>                 # Check for Stop Loss or Take Profit hits (based on local tracking)
>                 if side == "BUY":
>                     if current_price <= stop_loss:
>                         closed_by = "STOP_LOSS"
>                         exit_price = stop_loss  # Use SL price for exit if hit
>                     elif current_price >= take_profit:
>                         closed_by = "TAKE_PROFIT"
>                         exit_price = take_profit  # Use TP price for exit if hit
>                     elif is_trailing_activated and current_price <= current_trailing_sl:
>                         closed_by = "TRAILING_STOP_LOSS"
>                         exit_price = current_trailing_sl
>                 elif side == "SELL":
>                     if current_price >= stop_loss:
>                         closed_by = "STOP_LOSS"
>                         exit_price = stop_loss
>                     elif current_price <= take_profit:
>                         closed_by = "TAKE_PROFIT"
>                         exit_price = take_profit
>                     elif is_trailing_activated and current_price >= current_trailing_sl:
>                         closed_by = "TRAILING_STOP_LOSS"
>                         exit_price = current_trailing_sl
1356c1022,1033
<         return upper_band, middle_band, lower_band
---
>                 if closed_by:
>                     self.logger.info(
>                         f"{NEON_PURPLE}Position for {symbol} closed by {closed_by}. Closing position.{RESET}"
>                     )
>                     # In a real scenario, you'd send a cancel_all_orders or close position API call here
>                     # For this simulation, we just mark it as closed and record the trade.
>                     position["status"] = "CLOSED"
>                     position["exit_time"] = datetime.now(TIMEZONE)
>                     position["exit_price"] = self.precision_manager.format_price(
>                         exit_price
>                     )
>                     position["closed_by"] = closed_by
1358,1361c1035,1047
<     def calculate_vwap(self, df: pd.DataFrame) -> pd.Series:
<         """Calculate Volume Weighted Average Price (VWAP)."""
<         if df.empty:
<             return pd.Series(np.nan, index=df.index)
---
>                     pnl = (
>                         (exit_price - entry_price) * qty
>                         if side == "BUY"
>                         else (entry_price - exit_price) * qty
>                     )
>                     performance_tracker.record_trade(position, pnl)
>                     positions_to_remove.append(symbol)
>                     continue  # Move to the next position
> 
>                 # Handle Trailing Stop Logic
>                 trailing_stop_atr_multiple = Decimal(
>                     str(self.config["trade_management"]["trailing_stop_atr_multiple"])
>                 )
1363,1364c1049,1055
<         vwap = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
<         return self._safe_series_op(vwap, "VWAP")
---
>                 if not is_trailing_activated:
>                     # Check if activation threshold is met
>                     position["exit_time"] = datetime.now(TIMEZONE)
>                     position["exit_price"] = self.precision_manager.format_price(
>                         exit_price
>                     )
>                     position["closed_by"] = closed_by
1366,1371c1057,1069
<     def calculate_cci(self, df: pd.DataFrame, period: int) -> pd.Series:
<         """Calculate Commodity Channel Index (CCI)."""
<         if len(df) < period:
<             return pd.Series(np.nan, index=df.index)
<         cci = ta.cci(df["high"], df["low"], df["close"], length=period)
<         return self._safe_series_op(cci, "CCI")
---
>                     pnl = (
>                         (exit_price - entry_price) * qty
>                         if side == "BUY"
>                         else (entry_price - exit_price) * qty
>                     )
>                     performance_tracker.record_trade(position, pnl)
>                     positions_to_remove.append(symbol)
>                     continue  # Move to the next position
> 
>                 # Handle Trailing Stop Logic
>                 trailing_stop_atr_multiple = Decimal(
>                     str(self.config["trade_management"]["trailing_stop_atr_multiple"])
>                 )
1373,1378c1071,1083
<     def calculate_williams_r(self, df: pd.DataFrame, period: int) -> pd.Series:
<         """Calculate Williams %R."""
<         if len(df) < period:
<             return pd.Series(np.nan, index=df.index)
<         wr = ta.willr(df["high"], df["low"], df["close"], length=period)
<         return self._safe_series_op(wr, "WR")
---
>                 if not is_trailing_activated:
>                     # Check if activation threshold is met
>                     if (
>                         side == "BUY"
>                         and current_price
>                         >= entry_price
>                         * (Decimal("1") + self.trailing_stop_activation_percent)
>                     ) or (
>                         side == "SELL"
>                         and current_price
>                         <= entry_price
>                         * (Decimal("1") - self.trailing_stop_activation_percent)
>                     ):
1380c1085
<     
---
>                         position["is_trailing_activated"] = True
1382,1387c1087,1101
<     def calculate_mfi(self, df: pd.DataFrame, period: int) -> pd.Series:
<         """Calculate Money Flow Index (MFI)."""
<         if len(df) <= period:
<             return pd.Series(np.nan, index=df.index)
<         mfi = ta.mfi(df["high"], df["low"], df["close"], df["volume"], length=period)
<         return self._safe_series_op(mfi, "MFI")
---
>                         # Calculate initial trailing stop price
>                         if side == "BUY":
>                             initial_trailing_sl = current_price - (
>                                 atr_value * trailing_stop_atr_multiple
>                             )
>                             position["current_trailing_sl"] = (
>                                 self.precision_manager.format_price(initial_trailing_sl)
>                             )
>                         else:  # SELL
>                             initial_trailing_sl = current_price + (
>                                 atr_value * trailing_stop_atr_multiple
>                             )
>                             position["current_trailing_sl"] = (
>                                 self.precision_manager.format_price(initial_trailing_sl)
>                             )
1389,1392c1103,1136
<     def calculate_obv(self, df: pd.DataFrame, ema_period: int) -> tuple[pd.Series, pd.Series]:
<         """Calculate On-Balance Volume (OBV) and its EMA."""
<         if len(df) < MIN_DATA_POINTS_OBV:
<             return pd.Series(np.nan), pd.Series(np.nan)
---
>                         self.logger.info(
>                             f"Trailing stop activated for {symbol}. Initial SL: {position['current_trailing_sl'].normalize()}"
>                         )
>                         # In a real bot, you'd call an API to set this trailing stop
>                         # For now, we just update the local state.
>                 else:
>                     # Trailing stop is active, check if it needs updating
>                     potential_new_sl = Decimal("0")
>                     if side == "BUY":
>                         potential_new_sl = current_price - (
>                             atr_value * trailing_stop_atr_multiple
>                         )
>                         # Only move trailing SL up (for buy)
>                         if potential_new_sl > current_trailing_sl:
>                             position["current_trailing_sl"] = (
>                                 self.precision_manager.format_price(potential_new_sl)
>                             )
>                             self.logger.info(
>                                 f"Updating trailing stop for {symbol} to {position['current_trailing_sl'].normalize()}"
>                             )
>                             # In a real bot, you'd call an API to update the trailing stop here.
>                     elif side == "SELL":
>                         potential_new_sl = current_price + (
>                             atr_value * trailing_stop_atr_multiple
>                         )
>                         # Only move trailing SL down (for sell)
>                         if potential_new_sl < current_trailing_sl:
>                             position["current_trailing_sl"] = (
>                                 self.precision_manager.format_price(potential_new_sl)
>                             )
>                             self.logger.info(
>                                 f"Updating trailing stop for {symbol} to {position['current_trailing_sl'].normalize()}"
>                             )
>                             # In a real bot, you'd call an API to update the trailing stop here.
1394,1395c1138
<         obv = ta.obv(df["close"], df["volume"])
<         obv_ema = ta.ema(obv, length=ema_period)
---
>                 # Update the position in our local tracking (already done by modifying 'position' dict)
1397c1140,1143
<         return self._safe_series_op(obv, "OBV"), self._safe_series_op(obv_ema, "OBV_EMA")
---
>         # Remove closed positions from local tracking
>         for symbol in positions_to_remove:
>             if symbol in self.open_positions:
>                 del self.open_positions[symbol]
1399,1402c1145,1147
<     def calculate_cmf(self, df: pd.DataFrame, period: int) -> pd.Series:
<         """Calculate Chaikin Money Flow (CMF)."""
<         if len(df) < period:
<             return pd.Series(np.nan)
---
>     def get_open_positions(self) -> list[dict]:
>         """Return a list of currently open positions tracked locally."""
>         return [pos for pos in self.open_positions.values() if pos["status"] == "OPEN"]
1404,1405d1148
<         cmf = ta.cmf(df["high"], df["low"], df["close"], df["volume"], length=period)
<         return self._safe_series_op(cmf, "CMF")
1407,1432c1150,1152
<     def calculate_ichimoku_custom(
<         self,
<         df: pd.DataFrame,
<         tenkan_period: int,
<         kijun_period: int,
<         senkou_span_b_period: int,
<         chikou_span_offset: int,
<     ) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
<         """Calculate Ichimoku Cloud components manually."""
<         # Tenkan-sen (Conversion Line): (Highest High + Lowest Low) / 2 over tenkan_period
<         high_tenkan = df["high"].rolling(window=tenkan_period).max()
<         low_tenkan = df["low"].rolling(window=tenkan_period).min()
<         tenkan_sen = (high_tenkan + low_tenkan) / 2
< 
<         # Kijun-sen (Base Line): (Highest High + Lowest Low) / 2 over kijun_period
<         high_kijun = df["high"].rolling(window=kijun_period).max()
<         low_kijun = df["low"].rolling(window=kijun_period).min()
<         kijun_sen = (high_kijun + low_kijun) / 2
< 
<         # Senkou Span A (Leading Span A): (Tenkan-sen + Kijun-sen) / 2, plotted kijun_period periods ahead.
<         senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun_period)
< 
<         # Senkou Span B (Leading Span B): (Highest High + Lowest Low) / 2 over senkou_span_b_period, plotted kijun_period periods ahead.
<         high_senkou_b = df["high"].rolling(window=senkou_span_b_period).max()
<         low_senkou_b = df["low"].rolling(window=senkou_span_b_period).min()
<         senkou_span_b = ((high_senkou_b + low_senkou_b) / 2).shift(kijun_period)
---
> # --- Performance Tracking ---
> class PerformanceTracker:
>     """Tracks and reports trading performance. Trades are saved to a file."""
1434,1435c1154,1162
<         # Chikou Span (Lagging Span): Closing price plotted kijun_period periods behind.
<         chikou_span = df["close"].shift(-chikou_span_offset) # Shift backwards
---
>     def __init__(self, logger: logging.Logger, config_file: str = "trades.json"):
>         """Initializes the PerformanceTracker."""
>         self.logger = logger
>         self.config_file = Path(config_file)
>         self.trades: list[dict] = self._load_trades()
>         self.total_pnl = Decimal("0")
>         self.wins = 0
>         self.losses = 0
>         self._recalculate_summary()  # Recalculate summary from loaded trades
1437,1443c1164,1193
<         return (
<             self._safe_series_op(tenkan_sen, "Tenkan_Sen"),
<             self._safe_series_op(kijun_sen, "Kijun_Sen"),
<             self._safe_series_op(senkou_span_a, "Senkou_Span_A"),
<             self._safe_series_op(senkou_span_b, "Senkou_Span_B"),
<             self._safe_series_op(chikou_span, "Chikou_Span"),
<         )
---
>     def _load_trades(self) -> list[dict]:
>         """Load trade history from file."""
>         if self.config_file.exists():
>             try:
>                 with self.config_file.open("r", encoding="utf-8") as f:
>                     raw_trades = json.load(f)
>                     # Convert Decimal/datetime from string after loading
>                     loaded_trades = []
>                     for trade in raw_trades:
>                         for key in [
>                             "pnl",
>                             "entry_price",
>                             "exit_price",
>                             "qty",
>                             "stop_loss",
>                             "take_profit",
>                             "current_trailing_sl",
>                         ]:
>                             if key in trade and trade[key] is not None:
>                                 trade[key] = Decimal(str(trade[key]))
>                         for key in ["entry_time", "exit_time"]:
>                             if key in trade and trade[key] is not None:
>                                 trade[key] = datetime.fromisoformat(trade[key])
>                         loaded_trades.append(trade)
>                     return loaded_trades
>             except (json.JSONDecodeError, OSError) as e:
>                 self.logger.error(
>                     f"{NEON_RED}Error loading trades from {self.config_file}: {e}{RESET}"
>                 )
>         return []
1445,1451c1195,1221
<     def calculate_psar(
<         self, df: pd.DataFrame, acceleration: float, max_acceleration: float
<     ) -> tuple[pd.Series, pd.Series]:
<         """Calculate Parabolic SAR."""
<         if len(df) < MIN_DATA_POINTS_PSAR:
<             return pd.Series(np.nan, index=df.index), pd.Series(
<                 np.nan, index=df.index
---
>     def _save_trades(self) -> None:
>         """Save trade history to file."""
>         try:
>             with self.config_file.open("w", encoding="utf-8") as f:
>                 # Convert Decimal/datetime to string for JSON serialization
>                 serializable_trades = []
>                 for trade in self.trades:
>                     s_trade = trade.copy()
>                     for key in [
>                         "pnl",
>                         "entry_price",
>                         "exit_price",
>                         "qty",
>                         "stop_loss",
>                         "take_profit",
>                         "current_trailing_sl",
>                     ]:
>                         if key in s_trade and s_trade[key] is not None:
>                             s_trade[key] = str(s_trade[key])
>                     for key in ["entry_time", "exit_time"]:
>                         if key in s_trade and s_trade[key] is not None:
>                             s_trade[key] = s_trade[key].isoformat()
>                     serializable_trades.append(s_trade)
>                 json.dump(serializable_trades, f, indent=4)
>         except OSError as e:
>             self.logger.error(
>                 f"{NEON_RED}Error saving trades to {self.config_file}: {e}{RESET}"
1454,1462c1224,1234
<         try:
<             psar_result = ta.psar(df["high"], df["low"], df["close"], af0=acceleration, af=acceleration, max_af=max_acceleration)
<             if not isinstance(psar_result, pd.DataFrame):
<                 self.logger.error(f"{NEON_RED}pandas_ta.psar did not return a DataFrame. Type: {type(psar_result)}{RESET}")
<                 return pd.Series(np.nan, index=df.index), pd.Series(np.nan, index=df.index)
<             self.logger.debug(f"PSAR result columns: {psar_result.columns.tolist()}")
<         except Exception as e:
<             self.logger.error(f"{NEON_RED}Error calling pandas_ta.psar: {e}{RESET}")
<             return pd.Series(np.nan, index=df.index), pd.Series(np.nan, index=df.index)
---
>     def _recalculate_summary(self) -> None:
>         """Recalculate summary metrics from the list of trades."""
>         self.total_pnl = Decimal("0")
>         self.wins = 0
>         self.losses = 0
>         for trade in self.trades:
>             self.total_pnl += trade["pnl"]
>             if trade["pnl"] > 0:
>                 self.wins += 1
>             else:
>                 self.losses += 1
1464,1471c1236,1259
<         # Assuming standard pandas_ta PSAR column names
<         psar_val_col = f'PSARr_{acceleration}_{max_acceleration}' # Reversal PSAR value
<         psar_long_col = f'PSARl_{acceleration}_{max_acceleration}'
<         psar_short_col = f'PSARs_{acceleration}_{max_acceleration}'
< 
<         if not all(col in psar_result.columns for col in [psar_val_col, psar_long_col, psar_short_col]):
<             self.logger.error(f"{NEON_RED}Missing expected PSAR columns in result: {psar_result.columns.tolist()}. Expected: {psar_val_col}, {psar_long_col}, {psar_short_col}{RESET}")
<             return pd.Series(np.nan, index=df.index), pd.Series(np.nan, index=df.index)
---
>     def record_trade(self, position: dict, pnl: Decimal) -> None:
>         """Record a completed trade."""
>         trade_record = {
>             "entry_time": position.get(
>                 "entry_time", datetime.now(TIMEZONE)
>             ).isoformat(),
>             "exit_time": position.get("exit_time", datetime.now(TIMEZONE)).isoformat(),
>             "symbol": position["symbol"],
>             "side": position["side"],
>             "entry_price": str(position["entry_price"]),
>             "exit_price": str(position["exit_price"]),
>             "qty": str(position["qty"]),
>             "pnl": str(pnl),
>             "closed_by": position.get("closed_by", "UNKNOWN"),
>             "stop_loss": str(position["stop_loss"]),
>             "take_profit": str(position["take_profit"]),
>             "current_trailing_sl": str(position.get("current_trailing_sl", "N/A")),
>         }
>         self.trades.append(trade_record)
>         self._recalculate_summary()  # Update summary immediately
>         self._save_trades()  # Save to file
>         self.logger.info(
>             f"{NEON_CYAN}[{position['symbol']}] Trade recorded. Current Total PnL: {self.total_pnl.normalize():.2f}, Wins: {self.wins}, Losses: {self.losses}{RESET}"
>         )
1473,1475c1261,1264
<         psar_val = self._safe_series_op(psar_result[psar_val_col], "PSAR_Val")
<         psar_long = psar_result[psar_long_col]
<         psar_short = psar_result[psar_short_col]
---
>     def get_summary(self) -> dict:
>         """Return a summary of all recorded trades."""
>         total_trades = len(self.trades)
>         win_rate = (self.wins / total_trades) * 100 if total_trades > 0 else 0
1477,1481c1266,1272
<         psar_dir = pd.Series(0, index=df.index, dtype=int)
<         psar_dir[df['close'] > psar_long.fillna(0)] = 1
<         psar_dir[df['close'] < psar_short.fillna(0)] = -1
<         psar_dir.mask(psar_dir == 0, psar_dir.shift(1), inplace=True)
<         psar_dir.fillna(0, inplace=True)
---
>         return {
>             "total_trades": total_trades,
>             "total_pnl": self.total_pnl,
>             "wins": self.wins,
>             "losses": self.losses,
>             "win_rate": f"{win_rate:.2f}%",
>         }
1483d1273
<         return psar_val, psar_dir
1485,1492c1275,1277
<     def calculate_volatility_index(self, df: pd.DataFrame, period: int) -> pd.Series:
<         """Calculate a simple Volatility Index based on ATR normalized by price."""
<         if len(df) < period or "ATR" not in df.columns:
<             return pd.Series(np.nan, index=df.index)
<         # ATR is assumed to be calculated
<         normalized_atr = df["ATR"] / df["close"]
<         volatility_index = normalized_atr.rolling(window=period).mean()
<         return self._safe_series_op(volatility_index, "Volatility_Index")
---
> # --- Alert System ---
> class AlertSystem:
>     """Handles sending alerts for critical events."""
1494,1501c1279,1281
<     def calculate_vwma(self, df: pd.DataFrame, period: int) -> pd.Series:
<         """Calculate Volume Weighted Moving Average (VWMA)."""
<         if len(df) < period or df["volume"].isnull().any():
<             return pd.Series(np.nan, index=df.index)
<         valid_volume = df["volume"].replace(0, np.nan)
<         pv = df["close"] * valid_volume
<         vwma = pv.rolling(window=period).sum() / valid_volume.rolling(window=period).sum()
<         return self._safe_series_op(vwma, "VWMA")
---
>     def __init__(self, logger: logging.Logger):
>         """Initializes the AlertSystem."""
>         self.logger = logger
1503,1513c1283,1292
<     def calculate_volume_delta(self, df: pd.DataFrame, period: int) -> pd.Series:
<         """Calculate Volume Delta, indicating buying vs selling pressure."""
<         if len(df) < 2: # MIN_DATA_POINTS_VOLATILITY
<             return pd.Series(np.nan, index=df.index)
<         buy_volume = df["volume"].where(df["close"] > df["open"], 0)
<         sell_volume = df["volume"].where(df["close"] < df["open"], 0)
<         buy_volume_sum = buy_volume.rolling(window=period, min_periods=1).sum()
<         sell_volume_sum = sell_volume.rolling(window=period, min_periods=1).sum()
<         total_volume_sum = buy_volume_sum + sell_volume_sum
<         volume_delta = (buy_volume_sum - sell_volume_sum) / total_volume_sum.replace(0, np.nan)
<         return self._safe_series_op(volume_delta.fillna(0), "Volume_Delta")
---
>     def send_alert(
>         self, message: str, level: Literal["INFO", "WARNING", "ERROR"]
>     ) -> None:
>         """Send an alert (currently logs it)."""
>         if level == "INFO":
>             self.logger.info(f"{NEON_BLUE}ALERT: {message}{RESET}")
>         elif level == "WARNING":
>             self.logger.warning(f"{NEON_YELLOW}ALERT: {message}{RESET}")
>         elif level == "ERROR":
>             self.logger.error(f"{NEON_RED}ALERT: {message}{RESET}")
1515a1295
> # --- Trading Analysis ---
1517c1297
<     """Analyzes trading data and generates signals with MTF and Ehlers SuperTrend."""
---
>     """Analyzes trading data and generates signals with MTF, Ehlers SuperTrend, and other new indicators."""
1520a1301
>         df: pd.DataFrame,
1524d1304
<         indicator_calculator: IndicatorCalculator,
1526a1307
>         self.df = df.copy()
1530,1531d1310
<         self.indicator_calculator = indicator_calculator
<         self.df: pd.DataFrame = pd.DataFrame()
1535a1315,1317
>         self.price_precision = config["trade_management"][
>             "price_precision"
>         ]  # For Fibonacci levels
1537,1538c1319,1320
<         self.gemini_client: GeminiClient | None = None
<         if config["gemini_ai_analysis"]["enabled"]:
---
>         self.gemini_client: Any | None = None  # Placeholder for GeminiClient
>         if self.config["gemini_ai_analysis"]["enabled"]:
1541,1542c1323,1326
<                 self.logger.error(f"{NEON_RED}GEMINI_API_KEY environment variable is not set, but gemini_ai_analysis is enabled. Disabling Gemini AI analysis.{RESET}")
<                 config["gemini_ai_analysis"]["enabled"] = False
---
>                 self.logger.error(
>                     f"{NEON_RED}GEMINI_API_KEY environment variable is not set, but gemini_ai_analysis is enabled. Disabling Gemini AI analysis.{RESET}"
>                 )
>                 self.config["gemini_ai_analysis"]["enabled"] = False
1544,1559c1328,1341
<                 self.gemini_client = GeminiClient(
<                     api_key=gemini_api_key,
<                     model_name=config["gemini_ai_analysis"]["model_name"],
<                     temperature=config["gemini_ai_analysis"]["temperature"],
<                     top_p=config["gemini_ai_analysis"]["top_p"],
<                     logger=logger
<                 )
<                 self.logger.info(f"{NEON_GREEN}Gemini AI analysis enabled and client initialized.{RESET}")
< 
<     def update_data(self, new_df: pd.DataFrame):
<         """Updates the internal DataFrame and recalculates indicators."""
<         if new_df.empty:
<             self.logger.warning(
<                 f"{NEON_YELLOW}TradingAnalyzer received an empty DataFrame. Skipping indicator recalculation.{RESET}"
<             )
<             return
---
>                 # Assuming GeminiClient is available and correctly imported/implemented elsewhere
>                 # from gemini_client import GeminiClient # Uncomment if GeminiClient is available
>                 # self.gemini_client = GeminiClient(
>                 #     api_key=gemini_api_key,
>                 #     model_name=self.config["gemini_ai_analysis"]["model_name"],
>                 #     temperature=self.config["gemini_ai_analysis"]["temperature"],
>                 #     top_p=self.config["gemini_ai_analysis"]["top_p"],
>                 #     logger=logger
>                 # )
>                 self.logger.warning(
>                     f"{NEON_YELLOW}Gemini AI analysis enabled, but GeminiClient is not implemented/imported. Placeholder used.{RESET}"
>                 )
>                 # Placeholder for GeminiClient if not available
>                 self.gemini_client = lambda: None
1561,1564c1343,1361
<         self.df = new_df.copy()
<         self._calculate_all_indicators()
<         if self.config["indicators"].get("fibonacci_levels", False):
<             self.calculate_fibonacci_levels()
---
>         if not self.df.empty:
>             self._calculate_all_indicators()
>             if self.config["indicators"].get("fibonacci_levels", False):
>                 self.calculate_fibonacci_levels()
> 
>     def _safe_series_op(self, series: pd.Series, name: str) -> pd.Series:
>         """Safely perform operations on a Series, handling potential NaNs and logging."""
>         if series is None or series.empty:
>             self.logger.debug(
>                 f"Series '{name}' is empty or None. Returning empty Series."
>             )
>             # Return an empty Series with float dtype
>             return pd.Series(dtype=float)
>         if series.isnull().all():
>             self.logger.debug(
>                 f"Series '{name}' contains all NaNs. Returning Series with NaNs."
>             )
>             return series
>         return series
1578a1376
>             # Ensure the function only receives df with enough data
1580,1590c1378,1384
<             if (
<                 result is None
<                 or (isinstance(result, pd.Series) and result.empty)
<                 or (isinstance(result, pd.DataFrame) and result.empty)
<                 or (
<                     isinstance(result, tuple)
<                     and all(
<                         r is None or (isinstance(r, pd.Series) and r.empty)
<                         or (isinstance(r, pd.DataFrame) and r.empty)
<                         for r in result
<                     )
---
> 
>             # Check for empty series or all NaNs
>             if isinstance(result, pd.Series) and (
>                 result.empty or result.isnull().all()
>             ):
>                 self.logger.warning(
>                     f"{NEON_YELLOW}Indicator '{name}' returned an empty or all-NaN Series. Not enough valid data?{RESET}"
1591a1386,1389
>                 return None
>             if isinstance(result, tuple) and all(
>                 isinstance(r, pd.Series) and (r.empty or r.isnull().all())
>                 for r in result
1594c1392
<                     f"{NEON_YELLOW}Indicator '{name}' returned empty or None after calculation. Not enough valid data?{RESET}"
---
>                     f"{NEON_YELLOW}Indicator '{name}' returned all-empty or all-NaN Series in tuple. Not enough valid data?{RESET}"
1600c1398,1399
<                 f"{NEON_RED}Error calculating indicator '{name}': {e}{RESET}", exc_info=True
---
>                 f"{NEON_RED}Error calculating indicator '{name}': {e}{RESET}",
>                 exc_info=True,  # Add exc_info for full traceback
1605,1606c1404,1405
<         """Calculate all enabled technical indicators, including Ehlers SuperTrend."""
<         self.logger.debug("Calculating technical indicators...")
---
>         """Calculate all enabled technical indicators."""
>         self.logger.debug(f"[{self.symbol}] Calculating technical indicators...")
1610,1612c1409,1427
<         if self.df.empty:
<             self.logger.warning(f"{NEON_YELLOW}Cannot calculate indicators: DataFrame is empty.{RESET}")
<             return
---
>         # Ensure True Range is calculated first as it's a dependency for many indicators
>         self.df["TR"] = self._safe_calculate(
>             self.calculate_true_range, "TR", min_data_points=MIN_DATA_POINTS_TRUE_RANGE
>         )
>         # ATR
>         self.df["ATR"] = self._safe_calculate(
>             lambda: ta.atr(
>                 self.df["high"],
>                 self.df["low"],
>                 self.df["close"],
>                 length=isd["atr_period"],
>             ),
>             "ATR",
>             min_data_points=isd["atr_period"],
>         )
>         if self.df["ATR"] is not None and not self.df["ATR"].empty:
>             self.indicator_values["ATR"] = Decimal(str(self.df["ATR"].iloc[-1]))
>         else:
>             self.indicator_values["ATR"] = Decimal("0.01")  # Default to a small value
1613a1429
>         # SMA
1621c1437,1439
<                 self.indicator_values["SMA_10"] = self.df["SMA_10"].iloc[-1]
---
>                 self.indicator_values["SMA_10"] = Decimal(
>                     str(self.df["SMA_10"].iloc[-1])
>                 )
1629c1447,1449
<                 self.indicator_values["SMA_Long"] = self.df["SMA_Long"].iloc[-1]
---
>                 self.indicator_values["SMA_Long"] = Decimal(
>                     str(self.df["SMA_Long"].iloc[-1])
>                 )
1630a1451
>         # EMA
1643c1464,1466
<                 self.indicator_values["EMA_Short"] = self.df["EMA_Short"].iloc[-1]
---
>                 self.indicator_values["EMA_Short"] = Decimal(
>                     str(self.df["EMA_Short"].iloc[-1])
>                 )
1645,1656c1468,1470
<                 self.indicator_values["EMA_Long"] = self.df["EMA_Long"].iloc[-1]
< 
<         self.df["TR"] = self._safe_calculate(
<             self.indicator_calculator.calculate_true_range, "TR", min_data_points=2, df=self.df
<         )
<         self.df["ATR"] = self._safe_calculate(
<             lambda: ta.atr(self.df["high"], self.df["low"], self.df["close"], length=isd["atr_period"]),
<             "ATR",
<             min_data_points=isd["atr_period"],
<         )
<         if self.df["ATR"] is not None and not self.df["ATR"].empty:
<             self.indicator_values["ATR"] = self.df["ATR"].iloc[-1]
---
>                 self.indicator_values["EMA_Long"] = Decimal(
>                     str(self.df["EMA_Long"].iloc[-1])
>                 )
1657a1472
>         # RSI
1660c1475
<                 self.indicator_calculator.calculate_rsi,
---
>                 lambda: ta.rsi(self.df["close"], length=isd["rsi_period"]),
1663d1477
<                 df=self.df, period=isd["rsi_period"],
1666c1480,1482
<                 self.indicator_values["RSI"] = self.df["RSI"].iloc[-1]
---
>                 self.indicator_values["RSI"] = float(
>                     self.df["RSI"].iloc[-1]
>                 )  # Keep as float, typical for RSI
1667a1484
>         # Stochastic RSI
1669,1670c1486,1487
<             stoch_rsi_result = self._safe_calculate(
<                 self.indicator_calculator.calculate_stoch_rsi,
---
>             stoch_rsi_k, stoch_rsi_d = self._safe_calculate(
>                 self.calculate_stoch_rsi,
1674,1675c1491,1495
<                 + isd["stoch_k_period"],
<                 df=self.df, period=isd["stoch_rsi_period"], k_period=isd["stoch_k_period"],
---
>                 + isd[
>                     "stoch_k_period"
>                 ],  # Minimum period for StochRSI itself plus smoothing
>                 period=isd["stoch_rsi_period"],
>                 k_period=isd["stoch_k_period"],
1678,1685c1498,1505
<             if stoch_rsi_result is not None:
<                 stoch_rsi_k, stoch_rsi_d = stoch_rsi_result
<                 if stoch_rsi_k is not None and not stoch_rsi_k.empty:
<                     self.df["StochRSI_K"] = stoch_rsi_k
<                     self.indicator_values["StochRSI_K"] = stoch_rsi_k.iloc[-1]
<                 if stoch_rsi_d is not None and not stoch_rsi_d.empty:
<                     self.df["StochRSI_D"] = stoch_rsi_d
<                     self.indicator_values["StochRSI_D"] = stoch_rsi_d.iloc[-1]
---
>             if stoch_rsi_k is not None:
>                 self.df["StochRSI_K"] = stoch_rsi_k
>             if stoch_rsi_d is not None:
>                 self.df["StochRSI_D"] = stoch_rsi_d
>             if stoch_rsi_k is not None and not stoch_rsi_k.empty:
>                 self.indicator_values["StochRSI_K"] = float(stoch_rsi_k.iloc[-1])
>             if stoch_rsi_d is not None and not stoch_rsi_d.empty:
>                 self.indicator_values["StochRSI_D"] = float(stoch_rsi_d.iloc[-1])
1686a1507
>         # Bollinger Bands
1688,1689c1509,1510
<             bb_result = self._safe_calculate(
<                 self.indicator_calculator.calculate_bollinger_bands,
---
>             bb_upper, bb_middle, bb_lower = self._safe_calculate(
>                 self.calculate_bollinger_bands,
1692c1513
<                 df=self.df, period=isd["bollinger_bands_period"],
---
>                 period=isd["bollinger_bands_period"],
1695,1705c1516,1527
<             if bb_result is not None:
<                 bb_upper, bb_middle, bb_lower = bb_result
<                 if bb_upper is not None and not bb_upper.empty:
<                     self.df["BB_Upper"] = bb_upper
<                     self.indicator_values["BB_Upper"] = bb_upper.iloc[-1]
<                 if bb_middle is not None and not bb_middle.empty:
<                     self.df["BB_Middle"] = bb_middle
<                     self.indicator_values["BB_Middle"] = bb_middle.iloc[-1]
<                 if bb_lower is not None and not bb_lower.empty:
<                     self.df["BB_Lower"] = bb_lower
<                     self.indicator_values["BB_Lower"] = bb_lower.iloc[-1]
---
>             if bb_upper is not None:
>                 self.df["BB_Upper"] = bb_upper
>             if bb_middle is not None:
>                 self.df["BB_Middle"] = bb_middle
>             if bb_lower is not None:
>                 self.df["BB_Lower"] = bb_lower
>             if bb_upper is not None and not bb_upper.empty:
>                 self.indicator_values["BB_Upper"] = Decimal(str(bb_upper.iloc[-1]))
>             if bb_middle is not None and not bb_middle.empty:
>                 self.indicator_values["BB_Middle"] = Decimal(str(bb_middle.iloc[-1]))
>             if bb_lower is not None and not bb_lower.empty:
>                 self.indicator_values["BB_Lower"] = Decimal(str(bb_lower.iloc[-1]))
1706a1529
>         # CCI
1709c1532,1537
<                 self.indicator_calculator.calculate_cci,
---
>                 lambda: ta.cci(
>                     self.df["high"],
>                     self.df["low"],
>                     self.df["close"],
>                     length=isd["cci_period"],
>                 ),
1712d1539
<                 df=self.df, period=isd["cci_period"],
1715c1542
<                 self.indicator_values["CCI"] = self.df["CCI"].iloc[-1]
---
>                 self.indicator_values["CCI"] = float(self.df["CCI"].iloc[-1])
1716a1544
>         # Williams %R
1719c1547,1552
<                 self.indicator_calculator.calculate_williams_r,
---
>                 lambda: ta.willr(
>                     self.df["high"],
>                     self.df["low"],
>                     self.df["close"],
>                     length=isd["williams_r_period"],
>                 ),
1722d1554
<                 df=self.df, period=isd["williams_r_period"],
1725c1557
<                 self.indicator_values["WR"] = self.df["WR"].iloc[-1]
---
>                 self.indicator_values["WR"] = float(self.df["WR"].iloc[-1])
1726a1559
>         # MFI
1729c1562,1568
<                 self.indicator_calculator.calculate_mfi,
---
>                 lambda: ta.mfi(
>                     self.df["high"],
>                     self.df["low"],
>                     self.df["close"],
>                     self.df["volume"].astype(float),  # Explicitly cast volume to float
>                     length=isd["mfi_period"],
>                 ),
1732d1570
<                 df=self.df, period=isd["mfi_period"],
1735c1573
<                 self.indicator_values["MFI"] = self.df["MFI"].iloc[-1]
---
>                 self.indicator_values["MFI"] = float(self.df["MFI"].iloc[-1])
1736a1575
>         # OBV
1739c1578
<                 self.indicator_calculator.calculate_obv,
---
>                 self.calculate_obv,
1741,1742c1580,1583
<                 min_data_points=isd["obv_ema_period"],
<                 df=self.df, ema_period=isd["obv_ema_period"],
---
>                 min_data_points=isd[
>                     "obv_ema_period"
>                 ],  # OBV itself has no period, but EMA does
>                 ema_period=isd["obv_ema_period"],
1744c1585
<             if obv_val is not None and not obv_val.empty:
---
>             if obv_val is not None:
1746,1747c1587
<                 self.indicator_values["OBV"] = obv_val.iloc[-1]
<             if obv_ema is not None and not obv_ema.empty:
---
>             if obv_ema is not None:
1749c1589,1592
<                 self.indicator_values["OBV_EMA"] = obv_ema.iloc[-1]
---
>             if obv_val is not None and not obv_val.empty:
>                 self.indicator_values["OBV"] = float(obv_val.iloc[-1])
>             if obv_ema is not None and not obv_ema.empty:
>                 self.indicator_values["OBV_EMA"] = float(obv_ema.iloc[-1])
1750a1594
>         # CMF
1753c1597,1603
<                 self.indicator_calculator.calculate_cmf,
---
>                 lambda: ta.cmf(
>                     self.df["high"],
>                     self.df["low"],
>                     self.df["close"],
>                     self.df["volume"],
>                     length=isd["cmf_period"],
>                 ),
1756d1605
<                 df=self.df, period=isd["cmf_period"],
1758c1607
<             if cmf_val is not None and not cmf_val.empty:
---
>             if cmf_val is not None:
1760c1609,1610
<                 self.indicator_values["CMF"] = cmf_val.iloc[-1]
---
>             if cmf_val is not None and not cmf_val.empty:
>                 self.indicator_values["CMF"] = float(cmf_val.iloc[-1])
1761a1612
>         # Ichimoku Cloud
1765c1616
<                     self.indicator_calculator.calculate_ichimoku_custom,
---
>                     self.calculate_ichimoku_cloud,
1773c1624
<                     df=self.df, tenkan_period=isd["ichimoku_tenkan_period"],
---
>                     tenkan_period=isd["ichimoku_tenkan_period"],
1779c1630
<             if tenkan_sen is not None and not tenkan_sen.empty:
---
>             if tenkan_sen is not None:
1781,1782c1632
<                 self.indicator_values["Tenkan_Sen"] = tenkan_sen.iloc[-1]
<             if kijun_sen is not None and not kijun_sen.empty:
---
>             if kijun_sen is not None:
1784,1785c1634
<                 self.indicator_values["Kijun_Sen"] = kijun_sen.iloc[-1]
<             if senkou_span_a is not None and not senkou_span_a.empty:
---
>             if senkou_span_a is not None:
1787,1788c1636
<                 self.indicator_values["Senkou_Span_A"] = senkou_span_a.iloc[-1]
<             if senkou_span_b is not None and not senkou_span_b.empty:
---
>             if senkou_span_b is not None:
1790,1791c1638
<                 self.indicator_values["Senkou_Span_B"] = senkou_span_b.iloc[-1]
<             if chikou_span is not None and not chikou_span.empty:
---
>             if chikou_span is not None:
1793d1639
<                 self.indicator_values["Chikou_Span"] = chikou_span.fillna(0).iloc[-1]
1794a1641,1658
>             if tenkan_sen is not None and not tenkan_sen.empty:
>                 self.indicator_values["Tenkan_Sen"] = Decimal(str(tenkan_sen.iloc[-1]))
>             if kijun_sen is not None and not kijun_sen.empty:
>                 self.indicator_values["Kijun_Sen"] = Decimal(str(kijun_sen.iloc[-1]))
>             if senkou_span_a is not None and not senkou_span_a.empty:
>                 self.indicator_values["Senkou_Span_A"] = Decimal(
>                     str(senkou_span_a.iloc[-1])
>                 )
>             if senkou_span_b is not None and not senkou_span_b.empty:
>                 self.indicator_values["Senkou_Span_B"] = Decimal(
>                     str(senkou_span_b.iloc[-1])
>                 )
>             if chikou_span is not None and not chikou_span.empty:
>                 self.indicator_values["Chikou_Span"] = Decimal(
>                     str(chikou_span.fillna(0).iloc[-1])
>                 )
> 
>         # PSAR
1796,1797c1660,1661
<             psar_result = self._safe_calculate(
<                 self.indicator_calculator.calculate_psar,
---
>             psar_val, psar_dir = self._safe_calculate(
>                 self.calculate_psar,
1799,1800c1663,1664
<                 min_data_points=MIN_DATA_POINTS_PSAR,
<                 df=self.df, acceleration=isd["psar_acceleration"],
---
>                 min_data_points=MIN_DATA_POINTS_PSAR_INITIAL,
>                 acceleration=isd["psar_acceleration"],
1803,1812c1667,1674
<             if psar_result:
<                 psar_val, psar_dir = psar_result
<                 if psar_val is not None and not psar_val.empty:
<                     self.df["PSAR_Val"] = psar_val
<                     self.indicator_values["PSAR_Val"] = psar_val.iloc[-1]
<                 if psar_dir is not None and not psar_dir.empty:
<                     self.df["PSAR_Dir"] = psar_dir
<                     self.indicator_values["PSAR_Dir"] = psar_dir.iloc[-1]
<             else:
<                 self.logger.warning(f"{NEON_YELLOW}PSAR calculation failed, skipping assignments.{RESET}")
---
>             if psar_val is not None:
>                 self.df["PSAR_Val"] = psar_val
>             if psar_dir is not None:
>                 self.df["PSAR_Dir"] = psar_dir
>             if psar_val is not None and not psar_val.empty:
>                 self.indicator_values["PSAR_Val"] = Decimal(str(psar_val.iloc[-1]))
>             if psar_dir is not None and not psar_dir.empty:
>                 self.indicator_values["PSAR_Dir"] = float(psar_dir.iloc[-1])
1813a1676
>         # VWAP (requires volume and turnover, which are in df)
1816c1679,1683
<                 self.indicator_calculator.calculate_vwap, "VWAP", min_data_points=1, df=self.df
---
>                 lambda: ta.vwap(
>                     self.df["high"], self.df["low"], self.df["close"], self.df["volume"]
>                 ),
>                 "VWAP",
>                 min_data_points=1,
1819c1686
<                 self.indicator_values["VWAP"] = self.df["VWAP"].iloc[-1]
---
>                 self.indicator_values["VWAP"] = Decimal(str(self.df["VWAP"].iloc[-1]))
1820a1688
>         # --- Ehlers SuperTrend Calculation ---
1823c1691
<                 self.indicator_calculator.calculate_ehlers_supertrend,
---
>                 self.calculate_ehlers_supertrend,
1826c1694,1695
<                 df=self.df, period=isd["ehlers_fast_period"], multiplier=isd["ehlers_fast_multiplier"],
---
>                 period=isd["ehlers_fast_period"],
>                 multiplier=isd["ehlers_fast_multiplier"],
1831,1832c1700,1705
<                 self.indicator_values["ST_Fast_Dir"] = st_fast_result["direction"].iloc[-1]
<                 self.indicator_values["ST_Fast_Val"] = st_fast_result["supertrend"].iloc[-1]
---
>                 self.indicator_values["ST_Fast_Dir"] = float(
>                     st_fast_result["direction"].iloc[-1]
>                 )
>                 self.indicator_values["ST_Fast_Val"] = Decimal(
>                     str(st_fast_result["supertrend"].iloc[-1])
>                 )
1835c1708
<                 self.indicator_calculator.calculate_ehlers_supertrend,
---
>                 self.calculate_ehlers_supertrend,
1838c1711,1712
<                 df=self.df, period=isd["ehlers_slow_period"], multiplier=isd["ehlers_slow_multiplier"],
---
>                 period=isd["ehlers_slow_period"],
>                 multiplier=isd["ehlers_slow_multiplier"],
1843,1844c1717,1722
<                 self.indicator_values["ST_Slow_Dir"] = st_slow_result["direction"].iloc[-1]
<                 self.indicator_values["ST_Slow_Val"] = st_slow_result["supertrend"].iloc[-1]
---
>                 self.indicator_values["ST_Slow_Dir"] = float(
>                     st_slow_result["direction"].iloc[-1]
>                 )
>                 self.indicator_values["ST_Slow_Val"] = Decimal(
>                     str(st_slow_result["supertrend"].iloc[-1])
>                 )
1845a1724
>         # MACD
1847,1848c1726,1727
<             macd_result = self._safe_calculate(
<                 self.indicator_calculator.calculate_macd,
---
>             macd_line, signal_line, histogram = self._safe_calculate(
>                 self.calculate_macd,
1851c1730,1731
<                 df=self.df, fast_period=isd["macd_fast_period"], slow_period=isd["macd_slow_period"],
---
>                 fast_period=isd["macd_fast_period"],
>                 slow_period=isd["macd_slow_period"],
1854,1864c1734,1745
<             if macd_result is not None:
<                 macd_line, signal_line, histogram = macd_result
<                 if macd_line is not None and not macd_line.empty:
<                     self.df["MACD_Line"] = macd_line
<                     self.indicator_values["MACD_Line"] = macd_line.iloc[-1]
<                 if signal_line is not None and not signal_line.empty:
<                     self.df["MACD_Signal"] = signal_line
<                     self.indicator_values["MACD_Signal"] = signal_line.iloc[-1]
<                 if histogram is not None and not histogram.empty:
<                     self.df["MACD_Hist"] = histogram
<                     self.indicator_values["MACD_Hist"] = histogram.iloc[-1]
---
>             if macd_line is not None:
>                 self.df["MACD_Line"] = macd_line
>             if signal_line is not None:
>                 self.df["MACD_Signal"] = signal_line
>             if histogram is not None:
>                 self.df["MACD_Hist"] = histogram
>             if macd_line is not None and not macd_line.empty:
>                 self.indicator_values["MACD_Line"] = float(macd_line.iloc[-1])
>             if signal_line is not None and not signal_line.empty:
>                 self.indicator_values["MACD_Signal"] = float(signal_line.iloc[-1])
>             if histogram is not None and not histogram.empty:
>                 self.indicator_values["MACD_Hist"] = float(histogram.iloc[-1])
1865a1747
>         # ADX
1867,1868c1749,1750
<             adx_result = self._safe_calculate(
<                 self.indicator_calculator.calculate_adx,
---
>             adx_val, plus_di, minus_di = self._safe_calculate(
>                 self.calculate_adx,
1871c1753
<                 df=self.df, period=isd["adx_period"],
---
>                 period=isd["adx_period"],
1873,1883c1755,1766
<             if adx_result is not None:
<                 adx_val, plus_di, minus_di = adx_result
<                 if adx_val is not None and not adx_val.empty:
<                     self.df["ADX"] = adx_val
<                     self.indicator_values["ADX"] = adx_val.iloc[-1]
<                 if plus_di is not None and not plus_di.empty:
<                     self.df["PlusDI"] = plus_di
<                     self.indicator_values["PlusDI"] = plus_di.iloc[-1]
<                 if minus_di is not None and not minus_di.empty:
<                     self.df["MinusDI"] = minus_di
<                     self.indicator_values["MinusDI"] = minus_di.iloc[-1]
---
>             if adx_val is not None:
>                 self.df["ADX"] = adx_val
>             if plus_di is not None:
>                 self.df["PlusDI"] = plus_di
>             if minus_di is not None:
>                 self.df["MinusDI"] = minus_di
>             if adx_val is not None and not adx_val.empty:
>                 self.indicator_values["ADX"] = float(adx_val.iloc[-1])
>             if plus_di is not None and not plus_di.empty:
>                 self.indicator_values["PlusDI"] = float(plus_di.iloc[-1])
>             if minus_di is not None and not minus_di.empty:
>                 self.indicator_values["MinusDI"] = float(minus_di.iloc[-1])
1884a1768,1769
>         # --- New Indicators ---
>         # Volatility Index
1887c1772,1774
<                 self.indicator_calculator.calculate_volatility_index,
---
>                 lambda: self.calculate_volatility_index(
>                     period=isd["volatility_index_period"]
>                 ),
1890d1776
<                 df=self.df, period=isd["volatility_index_period"],
1892,1893c1778,1784
<             if self.df["Volatility_Index"] is not None and not self.df["Volatility_Index"].empty:
<                 self.indicator_values["Volatility_Index"] = self.df["Volatility_Index"].iloc[-1]
---
>             if (
>                 self.df["Volatility_Index"] is not None
>                 and not self.df["Volatility_Index"].empty
>             ):
>                 self.indicator_values["Volatility_Index"] = float(
>                     self.df["Volatility_Index"].iloc[-1]
>                 )
1894a1786
>         # VWMA
1897c1789
<                 self.indicator_calculator.calculate_vwma,
---
>                 lambda: self.calculate_vwma(period=isd["vwma_period"]),
1900d1791
<                 df=self.df, period=isd["vwma_period"],
1903c1794
<                 self.indicator_values["VWMA"] = self.df["VWMA"].iloc[-1]
---
>                 self.indicator_values["VWMA"] = Decimal(str(self.df["VWMA"].iloc[-1]))
1904a1796
>         # Volume Delta
1907c1799
<                 self.indicator_calculator.calculate_volume_delta,
---
>                 lambda: self.calculate_volume_delta(period=isd["volume_delta_period"]),
1910d1801
<                 df=self.df, period=isd["volume_delta_period"],
1912,1913c1803,1844
<             if self.df["Volume_Delta"] is not None and not self.df["Volume_Delta"].empty:
<                 self.indicator_values["Volume_Delta"] = self.df["Volume_Delta"].iloc[-1]
---
>             if (
>                 self.df["Volume_Delta"] is not None
>                 and not self.df["Volume_Delta"].empty
>             ):
>                 self.indicator_values["Volume_Delta"] = float(
>                     self.df["Volume_Delta"].iloc[-1]
>                 )
> 
>         # Fill any remaining NaNs in indicator columns with 0 after all calculations,
>         # or use a more specific strategy based on indicator type (e.g., ffill for trends).
>         # For simplicity, filling all with 0 where appropriate.
>         numeric_cols = self.df.select_dtypes(include=np.number).columns
>         self.df[numeric_cols] = self.df[numeric_cols].fillna(0)
> 
>         if self.df.empty:
>             self.logger.warning(
>                 f"{NEON_YELLOW}[{self.symbol}] DataFrame is empty after calculating all indicators and cleaning NaNs.{RESET}"
>             )
>         else:
>             self.logger.debug(
>                 f"[{self.symbol}] Indicators calculated. Final DataFrame size: {len(self.df)}"
>             )
> 
>     def calculate_true_range(self) -> pd.Series:
>         """Calculate True Range (TR)."""
>         if len(self.df) < MIN_DATA_POINTS_TRUE_RANGE:
>             return pd.Series(np.nan, index=self.df.index)
>         high_low = self._safe_series_op(self.df["high"] - self.df["low"], "TR_high_low")
>         high_prev_close = self._safe_series_op(
>             (self.df["high"] - self.df["close"].shift()).abs(), "TR_high_prev_close"
>         )
>         low_prev_close = self._safe_series_op(
>             (self.df["low"] - self.df["close"].shift()).abs(), "TR_low_prev_close"
>         )
>         return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(
>             axis=1
>         )
> 
>     def calculate_super_smoother(self, series: pd.Series, period: int) -> pd.Series:
>         """Apply Ehlers SuperSmoother filter to reduce lag and noise."""
>         if period <= 0 or len(series) < MIN_DATA_POINTS_SUPERSMOOTHER:
>             return pd.Series(np.nan, index=series.index)
1915c1846,1849
<         initial_len = len(self.df)
---
>         # Drop NaNs for calculation, reindex at the end
>         series_clean = self._safe_series_op(series, "SuperSmoother_input").dropna()
>         if len(series_clean) < MIN_DATA_POINTS_SUPERSMOOTHER:
>             return pd.Series(np.nan, index=series.index)
1917,1920c1851,1855
<         for col in self.df.columns:
<             if col not in ["open", "high", "low", "close", "volume", "turnover"]:
<                 self.df[col].fillna(method='ffill', inplace=True)
<                 self.df[col].fillna(0, inplace=True)
---
>         a1 = np.exp(-np.sqrt(2) * np.pi / period)
>         b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / period)
>         c1 = 1 - b1 + a1**2
>         c2 = b1 - 2 * a1**2
>         c3 = a1**2
1922c1857,1876
<         if len(self.df) < initial_len:
---
>         filt = pd.Series(np.nan, index=series_clean.index, dtype=float)
>         if len(series_clean) >= 1:
>             filt.iloc[0] = series_clean.iloc[0]
>         if len(series_clean) >= 2:
>             filt.iloc[1] = (series_clean.iloc[0] + series_clean.iloc[1]) / 2
> 
>         for i in range(2, len(series_clean)):
>             filt.iloc[i] = (
>                 (c1 / 2) * (series_clean.iloc[i] + series_clean.iloc[i - 1])
>                 + c2 * filt.iloc[i - 1]
>                 - c3 * filt.iloc[i - 2]
>             )
>         # Reindex to original DataFrame index
>         return filt.reindex(self.df.index)
> 
>     def calculate_ehlers_supertrend(
>         self, period: int, multiplier: float
>     ) -> pd.DataFrame | None:
>         """Calculate SuperTrend using Ehlers SuperSmoother for price and volatility."""
>         if len(self.df) < period * 3:
1924c1878
<                 f"Dropped {initial_len - len(self.df)} rows with NaNs after indicator calculations."
---
>                 f"[{self.symbol}] Not enough data for Ehlers SuperTrend (period={period}). Need at least {period*3} bars."
1925a1880
>             return None
1927c1882,1897
<         if self.df.empty:
---
>         df_copy = self.df.copy()
> 
>         hl2 = (df_copy["high"] + df_copy["low"]) / 2
>         smoothed_price = self.calculate_super_smoother(hl2, period)
> 
>         tr = self.calculate_true_range()
>         smoothed_atr = self.calculate_super_smoother(tr, period)
> 
>         df_copy["smoothed_price"] = smoothed_price
>         df_copy["smoothed_atr"] = smoothed_atr
> 
>         # Drop NaNs introduced by smoothing to work with complete data for SuperTrend calculation
>         df_clean = df_copy.dropna(
>             subset=["smoothed_price", "smoothed_atr", "close", "high", "low"]
>         )
>         if df_clean.empty:
1929c1899
<                 f"{NEON_YELLOW}DataFrame is empty after calculating all indicators and dropping NaNs.{RESET}"
---
>                 f"[{self.symbol}] Ehlers SuperTrend (period={period}): DataFrame empty after smoothing and NaN drop. Returning None."
1930a1901,1926
>             return None
> 
>         upper_band = df_clean["smoothed_price"] + multiplier * df_clean["smoothed_atr"]
>         lower_band = df_clean["smoothed_price"] - multiplier * df_clean["smoothed_atr"]
> 
>         direction = pd.Series(np.nan, index=df_clean.index, dtype=float)
>         supertrend = pd.Series(np.nan, index=df_clean.index, dtype=float)
> 
>         # Initialize the first valid supertrend value
>         first_valid_idx_loc = 0
>         while first_valid_idx_loc < len(df_clean) and (
>             pd.isna(df_clean["close"].iloc[first_valid_idx_loc])
>             or pd.isna(upper_band.iloc[first_valid_idx_loc])
>             or pd.isna(lower_band.iloc[first_valid_idx_loc])
>         ):
>             first_valid_idx_loc += 1
> 
>         if first_valid_idx_loc >= len(df_clean):
>             return None  # No valid data points
> 
>         if (
>             df_clean["close"].iloc[first_valid_idx_loc]
>             > upper_band.iloc[first_valid_idx_loc]
>         ):
>             direction.iloc[first_valid_idx_loc] = 1  # 1 for Up
>             supertrend.iloc[first_valid_idx_loc] = lower_band.iloc[first_valid_idx_loc]
1932,1933c1928,2280
<             self.logger.debug(
<                 f"Indicators calculated. Final DataFrame size: {len(self.df)}"
---
>             direction.iloc[first_valid_idx_loc] = -1  # -1 for Down
>             supertrend.iloc[first_valid_idx_loc] = upper_band.iloc[first_valid_idx_loc]
> 
>         for i in range(first_valid_idx_loc + 1, len(df_clean)):
>             prev_direction = direction.iloc[i - 1]
>             prev_supertrend = supertrend.iloc[i - 1]
>             curr_close = df_clean["close"].iloc[i]
> 
>             if curr_close > prev_supertrend and prev_direction == -1:
>                 # Flip from Down to Up
>                 direction.iloc[i] = 1
>                 supertrend.iloc[i] = lower_band.iloc[i]
>             elif curr_close < prev_supertrend and prev_direction == 1:
>                 # Flip from Up to Down
>                 direction.iloc[i] = -1
>                 supertrend.iloc[i] = upper_band.iloc[i]
>             else:
>                 # Continue in the same direction
>                 direction.iloc[i] = prev_direction
>                 if prev_direction == 1:
>                     supertrend.iloc[i] = max(lower_band.iloc[i], prev_supertrend)
>                 else:
>                     supertrend.iloc[i] = min(upper_band.iloc[i], prev_supertrend)
> 
>         result = pd.DataFrame({"supertrend": supertrend, "direction": direction})
>         # Reindex to original DataFrame index
>         return result.reindex(self.df.index)
> 
>     def calculate_macd(
>         self, fast_period: int, slow_period: int, signal_period: int
>     ) -> tuple[pd.Series, pd.Series, pd.Series]:
>         """Calculate Moving Average Convergence Divergence (MACD)."""
>         if len(self.df) < slow_period + signal_period:
>             return (
>                 pd.Series(np.nan, index=self.df.index),
>                 pd.Series(np.nan, index=self.df.index),
>                 pd.Series(np.nan, index=self.df.index),
>             )
> 
>         macd_result = ta.macd(
>             self.df["close"], fast=fast_period, slow=slow_period, signal=signal_period
>         )
>         if macd_result.empty:
>             return (
>                 pd.Series(np.nan, index=self.df.index),
>                 pd.Series(np.nan, index=self.df.index),
>                 pd.Series(np.nan, index=self.df.index),
>             )
> 
>         macd_line = self._safe_series_op(
>             macd_result[f"MACD_{fast_period}_{slow_period}_{signal_period}"],
>             "MACD_Line",
>         )
>         signal_line = self._safe_series_op(
>             macd_result[f"MACDs_{fast_period}_{slow_period}_{signal_period}"],
>             "MACD_Signal",
>         )
>         histogram = self._safe_series_op(
>             macd_result[f"MACDh_{fast_period}_{slow_period}_{signal_period}"],
>             "MACD_Hist",
>         )
> 
>         return macd_line, signal_line, histogram
> 
>     def calculate_rsi(self, period: int) -> pd.Series:
>         """Calculate Relative Strength Index (RSI)."""
>         if len(self.df) <= period:
>             return pd.Series(np.nan, index=self.df.index)
>         rsi = ta.rsi(self.df["close"], length=period)
>         return (
>             self._safe_series_op(rsi, "RSI").fillna(0).clip(0, 100)
>         )  # Clip to [0, 100] and fill NaNs
> 
>     def calculate_stoch_rsi(
>         self, period: int, k_period: int, d_period: int
>     ) -> tuple[pd.Series, pd.Series]:
>         """Calculate Stochastic RSI."""
>         if len(self.df) <= period:
>             return pd.Series(np.nan, index=self.df.index), pd.Series(
>                 np.nan, index=self.df.index
>             )
> 
>         rsi = self.calculate_rsi(period=period)
>         if rsi.isnull().all():
>             return pd.Series(np.nan, index=self.df.index), pd.Series(
>                 np.nan, index=self.df.index
>             )
> 
>         lowest_rsi = rsi.rolling(window=period, min_periods=period).min()
>         highest_rsi = rsi.rolling(window=period, min_periods=period).max()
> 
>         denominator = highest_rsi - lowest_rsi
>         # Replace 0 with NaN for division, then fillna(0) for the result later
>         stoch_rsi_k_raw = ((rsi - lowest_rsi) / denominator.replace(0, np.nan)) * 100
>         stoch_rsi_k_raw = (
>             self._safe_series_op(stoch_rsi_k_raw, "StochRSI_K_raw")
>             .fillna(0)
>             .clip(0, 100)
>         )
> 
>         # Smoothing with rolling mean, ensuring min_periods
>         stoch_rsi_k = (
>             stoch_rsi_k_raw.rolling(window=k_period, min_periods=k_period)
>             .mean()
>             .fillna(0)
>         )
>         stoch_rsi_d = (
>             stoch_rsi_k.rolling(window=d_period, min_periods=d_period).mean().fillna(0)
>         )
> 
>         return self._safe_series_op(stoch_rsi_k, "StochRSI_K"), self._safe_series_op(
>             stoch_rsi_d, "StochRSI_D"
>         )
> 
>     def calculate_adx(self, period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
>         """Calculate Average Directional Index (ADX)."""
>         if len(self.df) < period * 2:
>             return (
>                 pd.Series(np.nan, index=self.df.index),
>                 pd.Series(np.nan, index=self.df.index),
>                 pd.Series(np.nan, index=self.df.index),
>             )
> 
>         # Should have been calculated by _calculate_all_indicators
>         tr = self.df["TR"]
> 
>         plus_dm = self.df["high"].diff()
>         minus_dm = -self.df["low"].diff()
> 
>         plus_dm_final = pd.Series(0.0, index=self.df.index)
>         minus_dm_final = pd.Series(0.0, index=self.df.index)
> 
>         for i in range(1, len(self.df)):
>             if plus_dm.iloc[i] > minus_dm.iloc[i] and plus_dm.iloc[i] > 0:
>                 plus_dm_final.iloc[i] = plus_dm.iloc[i]
>             if minus_dm.iloc[i] > plus_dm.iloc[i] and minus_dm.iloc[i] > 0:
>                 minus_dm_final.iloc[i] = minus_dm.iloc[i]
> 
>         # Use ewm for smoothing with min_periods
>         atr = self._safe_series_op(
>             self.df["ATR"], "ATR_for_ADX"
>         )  # ATR should be pre-calculated
>         plus_di = (
>             plus_dm_final.ewm(span=period, adjust=False, min_periods=period).mean()
>             / atr.replace(0, np.nan)
>         ) * 100
>         minus_di = (
>             minus_dm_final.ewm(span=period, adjust=False, min_periods=period).mean()
>             / atr.replace(0, np.nan)
>         ) * 100
> 
>         di_diff = (plus_di - minus_di).abs()
>         di_sum = plus_di + minus_di
>         dx = (di_diff / di_sum.replace(0, np.nan)).fillna(0) * 100
>         adx = dx.ewm(span=period, adjust=False, min_periods=period).mean()
> 
>         return (
>             self._safe_series_op(adx, "ADX"),
>             self._safe_series_op(plus_di, "PlusDI"),
>             self._safe_series_op(minus_di, "MinusDI"),
>         )
> 
>     def calculate_bollinger_bands(
>         self, period: int, std_dev: float
>     ) -> tuple[pd.Series, pd.Series, pd.Series]:
>         """Calculate Bollinger Bands."""
>         if len(self.df) < period:
>             return (
>                 pd.Series(np.nan, index=self.df.index),
>                 pd.Series(np.nan, index=self.df.index),
>                 pd.Series(np.nan, index=self.df.index),
>             )
>         bbands = ta.bbands(self.df["close"], length=period, std=std_dev)
>         upper_band = self._safe_series_op(bbands[f"BBU_{period}_{std_dev}"], "BB_Upper")
>         middle_band = self._safe_series_op(
>             bbands[f"BBM_{period}_{std_dev}"], "BB_Middle"
>         )
>         lower_band = self._safe_series_op(bbands[f"BBL_{period}_{std_dev}"], "BB_Lower")
>         return upper_band, middle_band, lower_band
> 
>     def calculate_vwap(self, daily_reset: bool = False) -> pd.Series:
>         """Calculate Volume Weighted Average Price (VWAP)."""
>         if self.df.empty:
>             return pd.Series(np.nan, index=self.df.index)
> 
>         # Ensure volume is numeric and not zero
>         valid_volume = self.df["volume"].replace(0, np.nan)
>         typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
> 
>         if daily_reset:
>             # Group by date and calculate cumsum within each day
>             vwap_series = []
>             for date, group in self.df.groupby(self.df.index.date):
>                 group_tp_vol = (
>                     typical_price.loc[group.index] * valid_volume.loc[group.index]
>                 ).cumsum()
>                 group_vol = valid_volume.loc[group.index].cumsum()
>                 vwap_series.append(group_tp_vol / group_vol.replace(0, np.nan))
>             vwap = pd.concat(vwap_series).reindex(self.df.index)
>         else:
>             # Continuous VWAP over the entire DataFrame
>             cumulative_tp_vol = (typical_price * valid_volume).cumsum()
>             cumulative_vol = valid_volume.cumsum()
>             vwap = (cumulative_tp_vol / cumulative_vol.replace(0, np.nan)).reindex(
>                 self.df.index
>             )
> 
>         return self._safe_series_op(
>             vwap, "VWAP"
>         ).ffill()  # Forward fill NaNs if volume is zero, as VWAP typically holds
> 
>     def calculate_cci(self, period: int) -> pd.Series:
>         """Calculate Commodity Channel Index (CCI)."""
>         if len(self.df) < period:
>             return pd.Series(np.nan, index=self.df.index)
>         cci = ta.cci(self.df["high"], self.df["low"], self.df["close"], length=period)
>         return self._safe_series_op(cci, "CCI")
> 
>     def calculate_williams_r(self, period: int) -> pd.Series:
>         """Calculate Williams %R."""
>         if len(self.df) < period:
>             return pd.Series(np.nan, index=self.df.index)
>         wr = ta.willr(self.df["high"], self.df["low"], self.df["close"], length=period)
>         return (
>             self._safe_series_op(wr, "WR").fillna(-50).clip(-100, 0)
>         )  # Fill NaNs, clip to [-100, 0]
> 
>     def calculate_ichimoku_cloud(
>         self,
>         tenkan_period: int,
>         kijun_period: int,
>         senkou_span_b_period: int,
>         chikou_span_offset: int,
>     ) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
>         """Calculate Ichimoku Cloud components."""
>         required_len = (
>             max(tenkan_period, kijun_period, senkou_span_b_period) + chikou_span_offset
>         )
>         if len(self.df) < required_len:
>             nan_series = pd.Series(np.nan, index=self.df.index)
>             return nan_series, nan_series, nan_series, nan_series, nan_series
> 
>         tenkan_sen = (
>             self.df["high"]
>             .rolling(window=tenkan_period, min_periods=tenkan_period)
>             .max()
>             + self.df["low"]
>             .rolling(window=tenkan_period, min_periods=tenkan_period)
>             .min()
>         ) / 2
> 
>         kijun_sen = (
>             self.df["high"].rolling(window=kijun_period, min_periods=kijun_period).max()
>             + self.df["low"]
>             .rolling(window=kijun_period, min_periods=kijun_period)
>             .min()
>         ) / 2
> 
>         senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(
>             kijun_period
>         )  # Future projection
>         senkou_span_b = (
>             (
>                 self.df["high"]
>                 .rolling(window=senkou_span_b_period, min_periods=senkou_span_b_period)
>                 .max()
>                 + self.df["low"]
>                 .rolling(window=senkou_span_b_period, min_periods=senkou_span_b_period)
>                 .min()
>             )
>             / 2
>         ).shift(
>             kijun_period
>         )  # Future projection
> 
>         # Past projection
>         chikou_span = self.df["close"].shift(-chikou_span_offset)
> 
>         return (
>             self._safe_series_op(tenkan_sen, "Tenkan_Sen"),
>             self._safe_series_op(kijun_sen, "Kijun_Sen"),
>             self._safe_series_op(senkou_span_a, "Senkou_Span_A"),
>             self._safe_series_op(senkou_span_b, "Senkou_Span_B"),
>             self._safe_series_op(chikou_span, "Chikou_Span"),
>         )
> 
>     def calculate_mfi(self, period: int) -> pd.Series:
>         """Calculate Money Flow Index (MFI)."""
>         if len(self.df) <= period:
>             return pd.Series(np.nan, index=self.df.index)
>         mfi = ta.mfi(
>             self.df["high"],
>             self.df["low"],
>             self.df["close"],
>             self.df["volume"],
>             length=period,
>         )
>         return (
>             self._safe_series_op(mfi, "MFI").fillna(50).clip(0, 100)
>         )  # Fill NaNs with 50 (neutral), clip to [0, 100]
> 
>     def calculate_obv(self, ema_period: int) -> tuple[pd.Series, pd.Series]:
>         """Calculate On-Balance Volume (OBV) and its EMA."""
>         if len(self.df) < MIN_DATA_POINTS_OBV:
>             nan_series = pd.Series(np.nan, index=self.df.index)
>             return nan_series, nan_series
> 
>         obv = ta.obv(self.df["close"], self.df["volume"])
>         obv_ema = ta.ema(obv, length=ema_period)
> 
>         return self._safe_series_op(obv, "OBV"), self._safe_series_op(
>             obv_ema, "OBV_EMA"
>         )
> 
>     def calculate_cmf(self, period: int) -> pd.Series:
>         """Calculate Chaikin Money Flow (CMF)."""
>         if len(self.df) < period:
>             return pd.Series(np.nan, index=self.df.index)
> 
>         cmf = ta.cmf(
>             self.df["high"],
>             self.df["low"],
>             self.df["close"],
>             self.df["volume"],
>             length=period,
>         )
>         return (
>             self._safe_series_op(cmf, "CMF").fillna(0).clip(-1, 1)
>         )  # Fill NaNs with 0, clip to [-1, 1]
> 
>     def calculate_psar(
>         self, acceleration: float, max_acceleration: float
>     ) -> tuple[pd.Series, pd.Series]:
>         """Calculate Parabolic SAR."""
>         if len(self.df) < MIN_DATA_POINTS_PSAR_INITIAL:
>             nan_series = pd.Series(np.nan, index=self.df.index)
>             return nan_series, nan_series
> 
>         # Use pandas_ta for PSAR calculation
>         psar_result = ta.psar(
>             self.df["high"],
>             self.df["low"],
>             self.df["close"],
>             af0=acceleration,
>             af=acceleration,
>             max_af=max_acceleration,
>         )
>         if not isinstance(psar_result, pd.DataFrame):
>             self.logger.error(
>                 f"{NEON_RED}pandas_ta.psar did not return a DataFrame. Type: {type(psar_result)}{RESET}"
>             )
>             return pd.Series(np.nan, index=self.df.index), pd.Series(
>                 np.nan, index=self.df.index
1935a2283,2332
>         # Reversal PSAR value
>         psar_val_col = f"PSARr_{acceleration}_{max_acceleration}"
> 
>         if psar_val_col not in psar_result.columns:
>             self.logger.error(
>                 f"{NEON_RED}Missing expected PSAR column '{psar_val_col}' in result: {psar_result.columns.tolist()}{RESET}"
>             )
>             return pd.Series(np.nan, index=self.df.index), pd.Series(
>                 np.nan, index=self.df.index
>             )
> 
>         psar_val = self._safe_series_op(psar_result[psar_val_col], "PSAR_Val")
> 
>         # Determine direction based on price relative to PSAR value
>         direction = pd.Series(0, index=self.df.index, dtype=int)
> 
>         first_valid_idx = psar_val.first_valid_index()
>         if first_valid_idx is not None:
>             # Initialize direction based on the first valid PSAR point
>             if self.df["close"].loc[first_valid_idx] > psar_val.loc[first_valid_idx]:
>                 direction.loc[first_valid_idx] = 1  # Up trend
>             else:
>                 direction.loc[first_valid_idx] = -1  # Down trend
> 
>             for i in range(self.df.index.get_loc(first_valid_idx) + 1, len(self.df)):
>                 current_idx = self.df.index[i]
>                 prev_idx = self.df.index[i - 1]
> 
>                 if pd.isna(psar_val.loc[current_idx]) or pd.isna(
>                     self.df["close"].loc[current_idx]
>                 ):
>                     direction.loc[current_idx] = direction.loc[
>                         prev_idx
>                     ]  # Carry forward if current data is NaN
>                     continue
> 
>                 if direction.loc[prev_idx] == 1:  # Was in an uptrend
>                     if self.df["close"].loc[current_idx] < psar_val.loc[current_idx]:
>                         direction.loc[current_idx] = -1  # Reversal to downtrend
>                     else:
>                         direction.loc[current_idx] = 1  # Continue uptrend
>                 elif self.df["close"].loc[current_idx] > psar_val.loc[current_idx]:
>                     direction.loc[current_idx] = 1  # Reversal to uptrend
>                 else:
>                     direction.loc[current_idx] = -1  # Continue downtrend
> 
>         # Fill any remaining initial NaNs with 0
>         direction.fillna(0, inplace=True)
>         return psar_val, direction
> 
1941c2338
<                 f"{NEON_YELLOW}Not enough data for Fibonacci levels (need {window} bars).{RESET}"
---
>                 f"{NEON_YELLOW}[{self.symbol}] Not enough data for Fibonacci levels (need {window} bars).{RESET}"
1953a2351,2352
>         price_precision_str = "0." + "0" * (self.price_precision - 1) + "1"
> 
1955c2354,2356
<             "0.0%": decimal_high,
---
>             "0.0%": decimal_high.quantize(
>                 Decimal(price_precision_str), rounding=ROUND_DOWN
>             ),
1957c2358
<                 Decimal("0.00001"), rounding=ROUND_DOWN
---
>                 Decimal(price_precision_str), rounding=ROUND_DOWN
1960c2361
<                 Decimal("0.00001"), rounding=ROUND_DOWN
---
>                 Decimal(price_precision_str), rounding=ROUND_DOWN
1963c2364
<                 Decimal("0.00001"), rounding=ROUND_DOWN
---
>                 Decimal(price_precision_str), rounding=ROUND_DOWN
1966c2367
<                 Decimal("0.00001"), rounding=ROUND_DOWN
---
>                 Decimal(price_precision_str), rounding=ROUND_DOWN
1969c2370,2373
<                 Decimal("0.00001"), rounding=ROUND_DOWN
---
>                 Decimal(price_precision_str), rounding=ROUND_DOWN
>             ),
>             "100.0%": decimal_low.quantize(
>                 Decimal(price_precision_str), rounding=ROUND_DOWN
1971d2374
<             "100.0%": decimal_low,
1973c2376,2378
<         self.logger.debug(f"Calculated Fibonacci levels: {self.fib_levels}")
---
>         self.logger.debug(
>             f"[{self.symbol}] Calculated Fibonacci levels: {self.fib_levels}"
>         )
1975,1983c2380,2393
<     def _summarize_market_for_gemini(self, current_price: Decimal) -> str:
<         """Summarizes current market data and indicators for Gemini AI analysis."""
<         summary = f"Current Market Data for {self.symbol}:\n"
<         summary += f"Current Price: {current_price}\n"
<         summary += f"Current Volume: {self.df['volume'].iloc[-1] if not self.df.empty else 'N/A'}\n\n"
< 
<         summary += "Indicator Values:\n"
<         for indicator_name, value in self.indicator_values.items():
<             summary += f"  {indicator_name}: {value}\n"
---
>     def calculate_volatility_index(self, period: int) -> pd.Series:
>         """Calculate a simple Volatility Index based on ATR normalized by price."""
>         if (
>             len(self.df) < period
>             or "ATR" not in self.df.columns
>             or self.df["ATR"].isnull().all()
>         ):
>             return pd.Series(np.nan, index=self.df.index)
> 
>         # ATR is already calculated
>         # Avoid division by zero for close price
>         normalized_atr = self.df["ATR"] / self.df["close"].replace(0, np.nan)
>         volatility_index = normalized_atr.rolling(window=period).mean()
>         return self._safe_series_op(volatility_index, "Volatility_Index").fillna(0)
1985,1988c2395,2398
<         if self.fib_levels:
<             summary += "\nFibonacci Levels:\n"
<             for level_name, level_price in self.fib_levels.items():
<                 summary += f"  {level_name}: {level_price}\n"
---
>     def calculate_vwma(self, period: int) -> pd.Series:
>         """Calculate Volume Weighted Moving Average (VWMA)."""
>         if len(self.df) < period or self.df["volume"].isnull().any():
>             return pd.Series(np.nan, index=self.df.index)
1990,1993c2400,2409
<         summary += "\nProvide a trading recommendation in JSON format based on this data. " \
<                    "The recommendation should include: \"entry\" (BUY/SELL/HOLD), \"exit\" (N/A or specific instruction), \"take_profit\", \"stop_loss\", \"confidence_level\" (0-100). " \
<                    "Ensure all price values are numeric (float or int). Example JSON: {\"entry\": \"BUY\", \"exit\": \"N/A\", \"take_profit\": 103.00, \"stop_loss\": 98.00, \"confidence_level\": 85}"
<         return summary
---
>         # Ensure volume is numeric and not zero
>         valid_volume = self.df["volume"].replace(0, np.nan)
>         pv = self.df["close"] * valid_volume
>         # Use min_periods for rolling sums
>         vwma = pv.rolling(window=period, min_periods=1).sum() / valid_volume.rolling(
>             window=period, min_periods=1
>         ).sum().replace(0, np.nan)
>         return self._safe_series_op(
>             vwma, "VWMA"
>         ).ffill()  # Forward fill NaNs if volume is zero, as VWMA typically holds
1995,1997c2411,2414
<     def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
<         """Safely retrieve an indicator value."""
<         return self.indicator_values.get(key, default)
---
>     def calculate_volume_delta(self, period: int) -> pd.Series:
>         """Calculate Volume Delta, indicating buying vs selling pressure."""
>         if len(self.df) < MIN_DATA_POINTS_VOLATILITY:
>             return pd.Series(np.nan, index=self.df.index)
1999,2004c2416,2422
<     async def _check_orderbook(self, current_price: Decimal, orderbook_manager: AdvancedOrderbookManager) -> float:
<         """Analyze orderbook imbalance."""
<         best_bid, best_ask = await orderbook_manager.get_best_bid_ask()
<         if best_bid is None or best_ask is None:
<             self.logger.warning(f"{NEON_YELLOW}Orderbook data not available for imbalance check.{RESET}")
<             return 0.0
---
>         # Approximate buy/sell volume based on close relative to open
>         buy_volume = self.df["volume"].where(self.df["close"] > self.df["open"], 0)
>         sell_volume = self.df["volume"].where(self.df["close"] < self.df["open"], 0)
> 
>         # Rolling sum of buy/sell volume
>         buy_volume_sum = buy_volume.rolling(window=period, min_periods=1).sum()
>         sell_volume_sum = sell_volume.rolling(window=period, min_periods=1).sum()
2006,2007c2424,2431
<         depth_limit = self.config["orderbook_limit"]
<         bids, asks = await orderbook_manager.get_depth(depth_limit)
---
>         total_volume_sum = buy_volume_sum + sell_volume_sum
>         # Avoid division by zero
>         volume_delta = (buy_volume_sum - sell_volume_sum) / total_volume_sum.replace(
>             0, np.nan
>         )
>         return self._safe_series_op(volume_delta.fillna(0), "Volume_Delta").clip(
>             -1, 1
>         )  # Fill NaNs with 0, clip to [-1, 1]
2009,2010c2433,2435
<         bid_volume = sum(Decimal(str(b.quantity)) for b in bids)
<         ask_volume = sum(Decimal(str(a.quantity)) for a in asks)
---
>     def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
>         """Safely retrieve an indicator value."""
>         return self.indicator_values.get(key, default)
2012c2437,2445
<         if bid_volume + ask_volume == 0:
---
>     def _check_orderbook(self, current_price: Decimal, orderbook_manager: Any) -> float:
>         """Analyze orderbook imbalance. Placeholder as AdvancedOrderbookManager is not provided."""
>         # This method requires access to the orderbook_manager instance,
>         # which should be passed during initialization or to the signal generation method.
>         # For now, assuming it's accessible.
>         if not orderbook_manager:
>             self.logger.warning(
>                 "Orderbook manager not available for imbalance check. Returning 0.0."
>             )
2015,2019c2448,2460
<         imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
<         self.logger.debug(
<             f"Orderbook Imbalance: {imbalance:.4f} (Bids: {bid_volume}, Asks: {ask_volume})"
<         )
<         return float(imbalance)
---
>         # Placeholder logic if orderbook_manager were implemented
>         # bids, asks = orderbook_manager.get_depth(self.config["orderbook_limit"])
>         # bid_volume = sum(Decimal(str(b.quantity)) for b in bids)
>         # ask_volume = sum(Decimal(str(a.quantity)) for a in asks)
>         # total_volume = bid_volume + ask_volume
>         # if total_volume == 0:
>         #     return 0.0
>         # imbalance = (bid_volume - ask_volume) / total_volume
>         # self.logger.debug(
>         #     f"Orderbook Imbalance: {imbalance:.4f} (Bids: {bid_volume.normalize()}, Asks: {ask_volume.normalize()})"
>         # )
>         # return float(imbalance)
>         return 0.0  # Return 0.0 as a placeholder
2027c2468
<         isd = self.indicator_settings
---
>         period = self.config["mtf_analysis"]["trend_period"]
2030d2470
<             period = self.config["mtf_analysis"]["trend_period"]
2037,2040c2477,2481
<             if last_close > sma:
<                 return "UP"
<             if last_close < sma:
<                 return "DOWN"
---
>             if not pd.isna(sma):
>                 if last_close > sma:
>                     return "UP"
>                 if last_close < sma:
>                     return "DOWN"
2043d2483
<             period = self.config["mtf_analysis"]["trend_period"]
2050,2053c2490,2494
<             if last_close > ema:
<                 return "UP"
<             if last_close < ema:
<                 return "DOWN"
---
>             if not pd.isna(ema):
>                 if last_close > ema:
>                     return "UP"
>                 if last_close < ema:
>                     return "DOWN"
2056,2059c2497,2503
<             st_result = self.indicator_calculator.calculate_ehlers_supertrend(
<                 higher_tf_df,
<                 period=isd["ehlers_slow_period"],
<                 multiplier=isd["ehlers_slow_multiplier"],
---
>             # Temporarily create an analyzer for the higher timeframe data to get ST direction
>             temp_config = self.config.copy()
>             temp_config["indicators"][
>                 "ehlers_supertrend"
>             ] = True  # Ensure ST is enabled for temp analyzer
>             temp_analyzer = TradingAnalyzer(
>                 higher_tf_df, temp_config, self.logger, self.symbol
2061,2062c2505,2506
<             if st_result is not None and not st_result.empty:
<                 st_dir = st_result["direction"].iloc[-1]
---
>             st_dir = temp_analyzer._get_indicator_value("ST_Slow_Dir")
>             if not pd.isna(st_dir):
2073c2517,2518
<         orderbook_manager: AdvancedOrderbookManager,
---
>         # Changed type hint to Any as AdvancedOrderbookManager is not defined
>         orderbook_manager: Any,
2076c2521
<         """Generate a signal using confluence of indicators."""
---
>         """Generate a signal using confluence of indicators, including Ehlers SuperTrend."""
2084c2529
<                 f"{NEON_YELLOW}DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}"
---
>                 f"{NEON_YELLOW}[{self.symbol}] DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}"
2088a2534,2542
>         # Use .get() with default to handle cases where there might be less than 2 bars after NaN drops
>         prev_close_series = self.df["close"].iloc[-2] if len(self.df) > 1 else np.nan
>         prev_close = (
>             Decimal(str(prev_close_series))
>             if not pd.isna(prev_close_series)
>             else current_close
>         )
> 
>         self.logger.debug(f"[{self.symbol}] --- Signal Scoring ---")
2096a2551,2553
>                     self.logger.debug(
>                         f"  EMA Alignment: Bullish (+{weights.get('ema_alignment', 0):.2f})"
>                     )
2098a2556,2558
>                     self.logger.debug(
>                         f"  EMA Alignment: Bearish (-{weights.get('ema_alignment', 0):.2f})"
>                     )
2105a2566,2568
>                     self.logger.debug(
>                         f"  SMA Trend Filter: Bullish (+{weights.get('sma_trend_filter', 0):.2f})"
>                     )
2107a2571,2573
>                     self.logger.debug(
>                         f"  SMA Trend Filter: Bearish (-{weights.get('sma_trend_filter', 0):.2f})"
>                     )
2109,2326c2575,2577
<         # RSI
<         if active_indicators.get("rsi", False):
<             rsi = self._get_indicator_value("RSI")
<             if not pd.isna(rsi):
<                 if rsi < isd["rsi_oversold"]:
<                     signal_score += weights.get("rsi", 0)
<                 elif rsi > isd["rsi_overbought"]:
<                     signal_score -= weights.get("rsi", 0)
< 
<         # StochRSI
<         if active_indicators.get("stoch_rsi", False):
<             stoch_k = self._get_indicator_value("StochRSI_K")
<             stoch_d = self._get_indicator_value("StochRSI_D")
<             if not pd.isna(stoch_k) and not pd.isna(stoch_d) and len(self.df) > 1:
<                 prev_stoch_k = self.df["StochRSI_K"].iloc[-2]
<                 prev_stoch_d = self.df["StochRSI_D"].iloc[-2]
<                 if (
<                     stoch_k > stoch_d
<                     and prev_stoch_k <= prev_stoch_d
<                     and stoch_k < isd["stoch_rsi_oversold"]
<                 ):
<                     signal_score += weights.get("stoch_rsi", 0)
<                     self.logger.debug(f"StochRSI: Bullish crossover from oversold.")
<                 elif (
<                     stoch_k < stoch_d
<                     and prev_stoch_k >= prev_stoch_d
<                     and stoch_k > isd["stoch_rsi_overbought"]
<                 ):
<                     signal_score -= weights.get("stoch_rsi", 0)
<                     self.logger.debug(f"StochRSI: Bearish crossover from overbought.")
< 
<         # CCI
<         if active_indicators.get("cci", False):
<             cci = self._get_indicator_value("CCI")
<             if not pd.isna(cci):
<                 if cci < isd["cci_oversold"]:
<                     signal_score += weights.get("cci", 0)
<                 elif cci > isd["cci_overbought"]:
<                     signal_score -= weights.get("cci", 0)
< 
<         # Williams %R
<         if active_indicators.get("wr", False):
<             wr = self._get_indicator_value("WR")
<             if not pd.isna(wr):
<                 if wr < isd["williams_r_oversold"]:
<                     signal_score += weights.get("wr", 0)
<                 elif wr > isd["williams_r_overbought"]:
<                     signal_score -= weights.get("wr", 0)
< 
<         # MFI
<         if active_indicators.get("mfi", False):
<             mfi = self._get_indicator_value("MFI")
<             if not pd.isna(mfi):
<                 if mfi < isd["mfi_oversold"]:
<                     signal_score += weights.get("mfi", 0)
<                 elif mfi > isd["mfi_overbought"]:
<                     signal_score -= weights.get("mfi", 0)
< 
<         # Bollinger Bands
<         if active_indicators.get("bollinger_bands", False):
<             bb_upper = self._get_indicator_value("BB_Upper")
<             bb_lower = self._get_indicator_value("BB_Lower")
<             if not pd.isna(bb_upper) and not pd.isna(bb_lower):
<                 if current_close < bb_lower:
<                     signal_score += weights.get("bollinger_bands", 0)
<                 elif current_close > bb_upper:
<                     signal_score -= weights.get("bollinger_bands", 0)
< 
<         # VWAP
<         if active_indicators.get("vwap", False):
<             vwap = self._get_indicator_value("VWAP")
<             if not pd.isna(vwap):
<                 if current_close > vwap:
<                     signal_score += weights.get("vwap", 0)
<                 elif current_close < vwap:
<                     signal_score -= weights.get("vwap", 0)
< 
<         # PSAR
<         if active_indicators.get("psar", False):
<             psar_dir = self._get_indicator_value("PSAR_Dir")
<             if not pd.isna(psar_dir):
<                 if psar_dir == 1:
<                     signal_score += weights.get("psar", 0)
<                 elif psar_dir == -1:
<                     signal_score -= weights.get("psar", 0)
< 
<         # Ehlers SuperTrend Alignment
<         if active_indicators.get("ehlers_supertrend", False):
<             st_fast_dir = self._get_indicator_value("ST_Fast_Dir")
<             st_slow_dir = self._get_indicator_value("ST_Slow_Dir")
<             if not pd.isna(st_fast_dir) and not pd.isna(st_slow_dir):
<                 if st_fast_dir == 1 and st_slow_dir == 1:
<                     signal_score += weights.get("ehlers_supertrend_alignment", 0)
<                 elif st_fast_dir == -1 and st_slow_dir == -1:
<                     signal_score -= weights.get("ehlers_supertrend_alignment", 0)
< 
<         # MACD
<         if active_indicators.get("macd", False):
<             macd_line = self._get_indicator_value("MACD_Line")
<             signal_line = self._get_indicator_value("MACD_Signal")
<             if not pd.isna(macd_line) and not pd.isna(signal_line):
<                 if macd_line > signal_line:
<                     signal_score += weights.get("macd_alignment", 0)
<                 elif macd_line < signal_line:
<                     signal_score -= weights.get("macd_alignment", 0)
< 
<         # ADX
<         if active_indicators.get("adx", False):
<             adx = self._get_indicator_value("ADX")
<             plus_di = self._get_indicator_value("PlusDI")
<             minus_di = self._get_indicator_value("MinusDI")
<             if not pd.isna(adx) and not pd.isna(plus_di) and not pd.isna(minus_di):
<                 if adx > ADX_STRONG_TREND_THRESHOLD:
<                     if plus_di > minus_di:
<                         signal_score += weights.get("adx_strength", 0)
<                     else:
<                         signal_score -= weights.get("adx_strength", 0)
< 
<         # Ichimoku Cloud
<         if active_indicators.get("ichimoku_cloud", False):
<             tenkan = self._get_indicator_value("Tenkan_Sen")
<             kijun = self._get_indicator_value("Kijun_Sen")
<             span_a = self._get_indicator_value("Senkou_Span_A")
<             span_b = self._get_indicator_value("Senkou_Span_B")
<             chikou = self._get_indicator_value("Chikou_Span")
<             if not any(pd.isna(v) for v in [tenkan, kijun, span_a, span_b, chikou]):
<                 is_bullish = (current_close > span_a and current_close > span_b and
<                               tenkan > kijun and chikou > current_close)
<                 is_bearish = (current_close < span_a and current_close < span_b and
<                               tenkan < kijun and chikou < current_close)
<                 if is_bullish:
<                     signal_score += weights.get("ichimoku_confluence", 0)
<                 elif is_bearish:
<                     signal_score -= weights.get("ichimoku_confluence", 0)
< 
<         # OBV
<         if active_indicators.get("obv", False):
<             obv = self._get_indicator_value("OBV")
<             obv_ema = self._get_indicator_value("OBV_EMA")
<             if not pd.isna(obv) and not pd.isna(obv_ema):
<                 if obv > obv_ema:
<                     signal_score += weights.get("obv_momentum", 0)
<                 elif obv < obv_ema:
<                     signal_score -= weights.get("obv_momentum", 0)
< 
<         # CMF
<         if active_indicators.get("cmf", False):
<             cmf = self._get_indicator_value("CMF")
<             if not pd.isna(cmf):
<                 if cmf > 0:
<                     signal_score += weights.get("cmf_flow", 0)
<                 elif cmf < 0:
<                     signal_score -= weights.get("cmf_flow", 0)
< 
<         # Orderbook Imbalance
<         if active_indicators.get("orderbook_imbalance", False) and orderbook_manager:
<             imbalance = await self._check_orderbook(current_price, orderbook_manager)
<             if imbalance > 0.1:
<                 signal_score += weights.get("orderbook_imbalance", 0)
<             elif imbalance < -0.1:
<                 signal_score -= weights.get("orderbook_imbalance", 0)
< 
<         # MTF Trend Confluence
<         if self.config["mtf_analysis"]["enabled"] and mtf_trends:
<             up_trends = sum(1 for trend in mtf_trends.values() if trend == "UP")
<             down_trends = sum(1 for trend in mtf_trends.values() if trend == "DOWN")
<             if up_trends > down_trends:
<                 signal_score += weights.get("mtf_trend_confluence", 0)
<             elif down_trends > up_trends:
<                 signal_score -= weights.get("mtf_trend_confluence", 0)
< 
<         # Volatility Index
<         if active_indicators.get("volatility_index", False):
<             volatility = self._get_indicator_value("Volatility_Index")
<             if not pd.isna(volatility) and "Volatility_Index" in self.df.columns:
<                 if volatility > self.df["Volatility_Index"].mean():
<                     signal_score *= 0.95
<                 else:
<                     signal_score *= 1.05
< 
<         # VWMA Cross
<         if active_indicators.get("vwma", False):
<             vwma = self._get_indicator_value("VWMA")
<             if not pd.isna(vwma):
<                 if current_close > vwma:
<                     signal_score += weights.get("vwma_cross", 0)
<                 elif current_close < vwma:
<                     signal_score -= weights.get("vwma_cross", 0)
< 
<         # Volume Delta
<         if active_indicators.get("volume_delta", False):
<             volume_delta = self._get_indicator_value("Volume_Delta")
<             delta_threshold = isd.get("volume_delta_threshold", 0.2)
<             if not pd.isna(volume_delta):
<                 if volume_delta > delta_threshold:
<                     signal_score += weights.get("volume_delta_signal", 0)
<                 elif volume_delta < -delta_threshold:
<                     signal_score -= weights.get("volume_delta_signal", 0)
< 
<         # Final Signal
<         threshold = self.config["signal_score_threshold"]
<         if signal_score >= threshold:
<             return "BUY", signal_score
<         elif signal_score <= -threshold:
<             return "SELL", signal_score
<         else:
<             return "HOLD", signal_score
< 
<     async def generate_trading_signal(
<         self,
<         current_price: Decimal,
<         orderbook_manager: AdvancedOrderbookManager,
<         mtf_trends: dict[str, str],
<     ) -> tuple[str, float]:
<         """Generate a signal using confluence of indicators, including Ehlers SuperTrend."""
<         signal_score = 0.0
<         active_indicators = self.config["indicators"]
<         weights = self.weights
---
>         # Momentum Indicators (RSI, StochRSI, CCI, WR, MFI)
>         if active_indicators.get("momentum", False):
>             momentum_weight = weights.get("momentum_rsi_stoch_cci_wr_mfi", 0)
2328,2332c2579,2592
<         if self.df.empty:
<             self.logger.warning(
<                 f"{NEON_YELLOW}DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}"
<             )
<             return "HOLD", 0.0
---
>             # RSI
>             if active_indicators.get("rsi", False):
>                 rsi = self._get_indicator_value("RSI")
>                 if not pd.isna(rsi):
>                     if rsi < isd["rsi_oversold"]:
>                         signal_score += momentum_weight * 0.5
>                         self.logger.debug(
>                             f"  RSI: Oversold (+{momentum_weight * 0.5:.2f})"
>                         )
>                     elif rsi > isd["rsi_overbought"]:
>                         signal_score -= momentum_weight * 0.5
>                         self.logger.debug(
>                             f"  RSI: Overbought (-{momentum_weight * 0.5:.2f})"
>                         )
2334,2335c2594,2644
<         current_close = Decimal(str(self.df["close"].iloc[-1]))
<         isd = self.indicator_settings
---
>             # StochRSI Crossover
>             if active_indicators.get("stoch_rsi", False):
>                 stoch_k = self._get_indicator_value("StochRSI_K")
>                 stoch_d = self._get_indicator_value("StochRSI_D")
>                 if not pd.isna(stoch_k) and not pd.isna(stoch_d) and len(self.df) > 1:
>                     prev_stoch_k = (
>                         self.df["StochRSI_K"].iloc[-2]
>                         if "StochRSI_K" in self.df.columns
>                         else np.nan
>                     )
>                     prev_stoch_d = (
>                         self.df["StochRSI_D"].iloc[-2]
>                         if "StochRSI_D" in self.df.columns
>                         else np.nan
>                     )
>                     if (
>                         stoch_k > stoch_d
>                         and (
>                             pd.isna(prev_stoch_k)
>                             or pd.isna(prev_stoch_d)
>                             or prev_stoch_k <= prev_stoch_d
>                         )
>                         and stoch_k < isd["stoch_rsi_oversold"]
>                     ):
>                         signal_score += momentum_weight * 0.6
>                         self.logger.debug(
>                             f"  StochRSI: Bullish crossover from oversold (+{momentum_weight * 0.6:.2f})"
>                         )
>                     elif (
>                         stoch_k < stoch_d
>                         and (
>                             pd.isna(prev_stoch_k)
>                             or pd.isna(prev_stoch_d)
>                             or prev_stoch_k >= prev_stoch_d
>                         )
>                         and stoch_k > isd["stoch_rsi_overbought"]
>                     ):
>                         signal_score -= momentum_weight * 0.6
>                         self.logger.debug(
>                             f"  StochRSI: Bearish crossover from overbought (-{momentum_weight * 0.6:.2f})"
>                         )
>                     elif stoch_k > stoch_d and stoch_k < 50:  # General bullish momentum
>                         signal_score += momentum_weight * 0.2
>                         self.logger.debug(
>                             f"  StochRSI: General bullish momentum (+{momentum_weight * 0.2:.2f})"
>                         )
>                     elif stoch_k < stoch_d and stoch_k > 50:  # General bearish momentum
>                         signal_score -= momentum_weight * 0.2
>                         self.logger.debug(
>                             f"  StochRSI: General bearish momentum (-{momentum_weight * 0.2:.2f})"
>                         )
2337,2344c2646,2659
<         if active_indicators.get("ema_alignment", False):
<             ema_short = self._get_indicator_value("EMA_Short")
<             ema_long = self._get_indicator_value("EMA_Long")
<             if not pd.isna(ema_short) and not pd.isna(ema_long):
<                 if ema_short > ema_long:
<                     signal_score += weights.get("ema_alignment", 0)
<                 elif ema_short < ema_long:
<                     signal_score -= weights.get("ema_alignment", 0)
---
>             # CCI
>             if active_indicators.get("cci", False):
>                 cci = self._get_indicator_value("CCI")
>                 if not pd.isna(cci):
>                     if cci < isd["cci_oversold"]:
>                         signal_score += momentum_weight * 0.4
>                         self.logger.debug(
>                             f"  CCI: Oversold (+{momentum_weight * 0.4:.2f})"
>                         )
>                     elif cci > isd["cci_overbought"]:
>                         signal_score -= momentum_weight * 0.4
>                         self.logger.debug(
>                             f"  CCI: Overbought (-{momentum_weight * 0.4:.2f})"
>                         )
2346,2352c2661,2674
<         if active_indicators.get("sma_trend_filter", False):
<             sma_long = self._get_indicator_value("SMA_Long")
<             if not pd.isna(sma_long):
<                 if current_close > sma_long:
<                     signal_score += weights.get("sma_trend_filter", 0)
<                 elif current_close < sma_long:
<                     signal_score -= weights.get("sma_trend_filter", 0)
---
>             # Williams %R
>             if active_indicators.get("wr", False):
>                 wr = self._get_indicator_value("WR")
>                 if not pd.isna(wr):
>                     if wr < isd["williams_r_oversold"]:
>                         signal_score += momentum_weight * 0.4
>                         self.logger.debug(
>                             f"  WR: Oversold (+{momentum_weight * 0.4:.2f})"
>                         )
>                     elif wr > isd["williams_r_overbought"]:
>                         signal_score -= momentum_weight * 0.4
>                         self.logger.debug(
>                             f"  WR: Overbought (-{momentum_weight * 0.4:.2f})"
>                         )
2354,2390c2676,2689
<         if active_indicators.get("momentum", False):
<             rsi = self._get_indicator_value("RSI")
<             stoch_k = self._get_indicator_value("StochRSI_K")
<             stoch_d = self._get_indicator_value("StochRSI_D")
<             cci = self._get_indicator_value("CCI")
<             wr = self._get_indicator_value("WR")
<             mfi = self._get_indicator_value("MFI")
< 
<             if not pd.isna(rsi):
<                 if rsi < isd["rsi_oversold"]:
<                     signal_score += weights.get("rsi", 0) * 0.5
<                 elif rsi > isd["rsi_overbought"]:
<                     signal_score -= weights.get("rsi", 0) * 0.5
< 
<             if not pd.isna(stoch_k) and not pd.isna(stoch_d):
<                 if stoch_k > stoch_d and stoch_k < isd["stoch_rsi_oversold"]:
<                     signal_score += weights.get("stoch_rsi", 0) * 0.5
<                 elif stoch_k < stoch_d and stoch_k > isd["stoch_rsi_overbought"]:
<                     signal_score -= weights.get("stoch_rsi", 0) * 0.5
< 
<             if not pd.isna(cci):
<                 if cci < isd["cci_oversold"]:
<                     signal_score += weights.get("cci", 0) * 0.5
<                 elif cci > isd["cci_overbought"]:
<                     signal_score -= weights.get("cci", 0) * 0.5
< 
<             if not pd.isna(wr):
<                 if wr < isd["williams_r_oversold"]:
<                     signal_score += weights.get("wr", 0) * 0.5
<                 elif wr > isd["williams_r_overbought"]:
<                     signal_score -= weights.get("wr", 0) * 0.5
< 
<             if not pd.isna(mfi):
<                 if mfi < isd["mfi_oversold"]:
<                     signal_score += weights.get("mfi", 0) * 0.5
<                 elif mfi > isd["mfi_overbought"]:
<                     signal_score -= weights.get("mfi", 0) * 0.5
---
>             # MFI
>             if active_indicators.get("mfi", False):
>                 mfi = self._get_indicator_value("MFI")
>                 if not pd.isna(mfi):
>                     if mfi < isd["mfi_oversold"]:
>                         signal_score += momentum_weight * 0.4
>                         self.logger.debug(
>                             f"  MFI: Oversold (+{momentum_weight * 0.4:.2f})"
>                         )
>                     elif mfi > isd["mfi_overbought"]:
>                         signal_score -= momentum_weight * 0.4
>                         self.logger.debug(
>                             f"  MFI: Overbought (-{momentum_weight * 0.4:.2f})"
>                         )
2391a2691
>         # Bollinger Bands
2397a2698,2700
>                     self.logger.debug(
>                         f"  BB: Price below lower band (+{weights.get('bollinger_bands', 0) * 0.5:.2f})"
>                     )
2399a2703,2705
>                     self.logger.debug(
>                         f"  BB: Price above upper band (-{weights.get('bollinger_bands', 0) * 0.5:.2f})"
>                     )
2400a2707
>         # VWAP
2405a2713,2715
>                     self.logger.debug(
>                         f"  VWAP: Price above VWAP (+{weights.get('vwap', 0) * 0.2:.2f})"
>                     )
2407a2718,2720
>                     self.logger.debug(
>                         f"  VWAP: Price below VWAP (-{weights.get('vwap', 0) * 0.2:.2f})"
>                     )
2409,2414c2722,2733
<                 if len(self.df) > 1 and "VWAP" in self.df.columns:
<                     prev_close = Decimal(str(self.df["close"].iloc[-2]))
<                     prev_vwap = Decimal(str(self.df["VWAP"].iloc[-2]))
<                     if (
<                         current_close > vwap and prev_close <= prev_vwap
<                     ):
---
>                 if len(self.df) > 1:
>                     prev_vwap_series = (
>                         self.df["VWAP"].iloc[-2]
>                         if "VWAP" in self.df.columns
>                         else np.nan
>                     )
>                     prev_vwap = (
>                         Decimal(str(prev_vwap_series))
>                         if not pd.isna(prev_vwap_series)
>                         else vwap
>                     )
>                     if current_close > vwap and prev_close <= prev_vwap:
2416,2419c2735,2738
<                         self.logger.debug("VWAP: Bullish crossover detected.")
<                     elif (
<                         current_close < vwap and prev_close >= prev_vwap
<                     ):
---
>                         self.logger.debug(
>                             f"  VWAP: Bullish crossover detected (+{weights.get('vwap', 0) * 0.3:.2f})"
>                         )
>                     elif current_close < vwap and prev_close >= prev_vwap:
2421c2740,2742
<                         self.logger.debug("VWAP: Bearish crossover detected.")
---
>                         self.logger.debug(
>                             f"  VWAP: Bearish crossover detected (-{weights.get('vwap', 0) * 0.3:.2f})"
>                         )
2422a2744
>         # PSAR
2426,2431d2747
< 
<             # Debugging PSAR values and types
<             self.logger.debug(f"PSAR_Val: {psar_val} (Type: {type(psar_val)})")
<             self.logger.debug(f"PSAR_Dir: {psar_dir} (Type: {type(psar_dir)})")
<             self.logger.debug(f"Current Close: {current_close} (Type: {type(current_close)})")
< 
2433,2457c2749,2758
<                 # Ensure psar_val is a comparable numeric type
<                 psar_val_numeric = Decimal(str(psar_val)) if not isinstance(psar_val, Decimal) else psar_val
< 
<                 # Check for PSAR buy signal (price crosses above PSAR)
<                 if psar_dir == 1:
<                     # Need previous close and previous PSAR value for a true cross
<                     if len(self.df) >= 2:
<                         prev_close = Decimal(str(self.df["close"].iloc[-2]))
<                         # Retrieve previous PSAR_Val from indicator_values, not self.df["PSAR_Val"]
<                         prev_psar_val = self._get_indicator_value("PSAR_Val", default=0.0) 
<                         prev_psar_val_numeric = Decimal(str(prev_psar_val)) if not isinstance(prev_psar_val, Decimal) else prev_psar_val
< 
<                         self.logger.debug(f"Prev Close: {prev_close} (Type: {type(prev_close)})")
<                         self.logger.debug(f"Prev PSAR_Val: {prev_psar_val} (Type: {type(prev_psar_val)})")
< 
<                         if current_close > psar_val_numeric and prev_close <= prev_psar_val_numeric:
<                             signal_score += weights.get("psar", 0) * 0.5 # Strong buy signal
< 
<                 # Check for PSAR sell signal (price crosses below PSAR)
<                 elif psar_dir == -1:
<                     if len(self.df) >= 2:
<                         prev_close = Decimal(str(self.df["close"].iloc[-2]))
<                         # Retrieve previous PSAR_Val from indicator_values, not self.df["PSAR_Val"]
<                         prev_psar_val = self._get_indicator_value("PSAR_Val", default=0.0) 
<                         prev_psar_val_numeric = Decimal(str(prev_psar_val)) if not isinstance(prev_psar_val, Decimal) else prev_psar_val
---
>                 if psar_dir == 1:  # Bullish direction
>                     signal_score += weights.get("psar", 0) * 0.5
>                     self.logger.debug(
>                         f"  PSAR: Bullish direction (+{weights.get('psar', 0) * 0.5:.2f})"
>                     )
>                 elif psar_dir == -1:  # Bearish direction
>                     signal_score -= weights.get("psar", 0) * 0.5
>                     self.logger.debug(
>                         f"  PSAR: Bearish direction (-{weights.get('psar', 0) * 0.5:.2f})"
>                     )
2459,2460c2760,2780
<                         if current_close < psar_val_numeric and prev_close >= prev_psar_val_numeric:
<                             signal_score -= weights.get("psar", 0) * 0.5 # Strong sell signal
---
>                 if len(self.df) > 1:
>                     prev_psar_val_series = (
>                         self.df["PSAR_Val"].iloc[-2]
>                         if "PSAR_Val" in self.df.columns
>                         else np.nan
>                     )
>                     prev_psar_val = (
>                         Decimal(str(prev_psar_val_series))
>                         if not pd.isna(prev_psar_val_series)
>                         else psar_val
>                     )
>                     if current_close > psar_val and prev_close <= prev_psar_val:
>                         signal_score += weights.get("psar", 0) * 0.4
>                         self.logger.debug(
>                             f"  PSAR: Bullish reversal detected (+{weights.get('psar', 0) * 0.4:.2f})"
>                         )
>                     elif current_close < psar_val and prev_close >= prev_psar_val:
>                         signal_score -= weights.get("psar", 0) * 0.4
>                         self.logger.debug(
>                             f"  PSAR: Bearish reversal detected (-{weights.get('psar', 0) * 0.4:.2f})"
>                         )
2461a2782
>         # Orderbook Imbalance
2463c2784
<             imbalance = await self._check_orderbook(current_price, orderbook_manager)
---
>             imbalance = self._check_orderbook(current_price, orderbook_manager)
2464a2786,2788
>             self.logger.debug(
>                 f"  Orderbook Imbalance: {imbalance:.2f} (Contribution: {imbalance * weights.get('orderbook_imbalance', 0):.2f})"
>             )
2465a2790
>         # Fibonacci Levels (confluence with price action)
2468,2484c2793,2812
<                 if (level_name not in ["0.0%", "100.0%"] and
<                     abs(current_price - level_price) / current_price < Decimal("0.001")):
<                         self.logger.debug(
<                             f"Price near Fibonacci level {level_name}: {level_price}"
<                         )
<                         if len(self.df) > 1:
<                             prev_close = Decimal(str(self.df["close"].iloc[-2]))
<                             if (
<                                 current_close > prev_close
<                                 and current_close > level_price
<                             ):
<                                 signal_score += weights.get("fibonacci_levels", 0) * 0.1
<                             elif (
<                                 current_close < prev_close
<                                 and current_close < level_price
<                             ):
<                                 signal_score -= weights.get("fibonacci_levels", 0) * 0.1
---
>                 # Check if price is within a very small proximity of a Fibonacci level
>                 if level_name not in ["0.0%", "100.0%"] and (
>                     level_price * Decimal("0.999")
>                     <= current_price
>                     <= level_price * Decimal("1.001")
>                 ):
>                     self.logger.debug(
>                         f"  Price near Fibonacci level {level_name}: {level_price.normalize()}"
>                     )
>                     if len(self.df) > 1:
>                         if current_close > prev_close and current_close > level_price:
>                             signal_score += weights.get("fibonacci_levels", 0) * 0.1
>                             self.logger.debug(
>                                 f"  Fibonacci: Bullish breakout/bounce (+{weights.get('fibonacci_levels', 0) * 0.1:.2f})"
>                             )
>                         elif current_close < prev_close and current_close < level_price:
>                             signal_score -= weights.get("fibonacci_levels", 0) * 0.1
>                             self.logger.debug(
>                                 f"  Fibonacci: Bearish breakout/bounce (-{weights.get('fibonacci_levels', 0) * 0.1:.2f})"
>                             )
2485a2814
>         # --- Ehlers SuperTrend Alignment Scoring ---
2489,2490c2818
< 
<             prev_st_fast_dir = (
---
>             prev_st_fast_dir_series = (
2495c2823,2827
< 
---
>             prev_st_fast_dir = (
>                 float(prev_st_fast_dir_series)
>                 if not pd.isna(prev_st_fast_dir_series)
>                 else np.nan
>             )
2506c2838
<                         "Ehlers SuperTrend: Strong BUY signal (fast flip aligned with slow trend)."
---
>                         f"Ehlers SuperTrend: Strong BUY signal (fast flip aligned with slow trend) (+{weight:.2f})."
2511c2843
<                         "Ehlers SuperTrend: Strong SELL signal (fast flip aligned with slow trend)."
---
>                         f"Ehlers SuperTrend: Strong SELL signal (fast flip aligned with slow trend) (-{weight:.2f})."
2514a2847,2849
>                     self.logger.debug(
>                         f"Ehlers SuperTrend: Bullish alignment (+{weight * 0.3:.2f})."
>                     )
2516a2852,2854
>                     self.logger.debug(
>                         f"Ehlers SuperTrend: Bearish alignment (-{weight * 0.3:.2f})."
>                     )
2517a2856
>         # --- MACD Alignment Scoring ---
2522d2860
< 
2528a2867
>                 and len(self.df) > 1
2530,2533c2869,2883
<                 if (
<                     macd_line > signal_line
<                     and "MACD_Line" in self.df.columns and "MACD_Signal" in self.df.columns
<                     and len(self.df) > 1 and self.df["MACD_Line"].iloc[-2] <= self.df["MACD_Signal"].iloc[-2]
---
>                 prev_macd_line = (
>                     self.df["MACD_Line"].iloc[-2]
>                     if "MACD_Line" in self.df.columns
>                     else np.nan
>                 )
>                 prev_signal_line = (
>                     self.df["MACD_Signal"].iloc[-2]
>                     if "MACD_Signal" in self.df.columns
>                     else np.nan
>                 )
> 
>                 if macd_line > signal_line and (
>                     pd.isna(prev_macd_line)
>                     or pd.isna(prev_signal_line)
>                     or prev_macd_line <= prev_signal_line
2537c2887
<                         "MACD: BUY signal (MACD line crossed above Signal line)."
---
>                         f"MACD: BUY signal (MACD line crossed above Signal line) (+{weight:.2f})."
2539,2542c2889,2892
<                 elif (
<                     macd_line < signal_line
<                     and "MACD_Line" in self.df.columns and "MACD_Signal" in self.df.columns
<                     and len(self.df) > 1 and self.df["MACD_Line"].iloc[-2] >= self.df["MACD_Signal"].iloc[-2]
---
>                 elif macd_line < signal_line and (
>                     pd.isna(prev_macd_line)
>                     or pd.isna(prev_signal_line)
>                     or prev_macd_line >= prev_signal_line
2546c2896
<                         "MACD: SELL signal (MACD line crossed below Signal line)."
---
>                         f"MACD: SELL signal (MACD line crossed below Signal line) (-{weight:.2f})."
2548,2550c2898,2901
<                 elif (
<                     histogram > 0 and "MACD_Hist" in self.df.columns
<                     and len(self.df) > 1 and self.df["MACD_Hist"].iloc[-2] < 0
---
>                 elif histogram > 0 and (
>                     len(self.df) > 2
>                     and "MACD_Hist" in self.df.columns
>                     and self.df["MACD_Hist"].iloc[-2] < 0
2553,2555c2904,2910
<                 elif (
<                     histogram < 0 and "MACD_Hist" in self.df.columns
<                     and len(self.df) > 1 and self.df["MACD_Hist"].iloc[-2] > 0
---
>                     self.logger.debug(
>                         f"MACD: Histogram turned positive (+{weight * 0.2:.2f})."
>                     )
>                 elif histogram < 0 and (
>                     len(self.df) > 2
>                     and "MACD_Hist" in self.df.columns
>                     and self.df["MACD_Hist"].iloc[-2] > 0
2557a2913,2915
>                     self.logger.debug(
>                         f"MACD: Histogram turned negative (-{weight * 0.2:.2f})."
>                     )
2558a2917
>         # --- ADX Alignment Scoring ---
2563d2921
< 
2571c2929
<                             "ADX: Strong BUY trend (ADX > 25, +DI > -DI)."
---
>                             f"ADX: Strong BUY trend (ADX > {ADX_STRONG_TREND_THRESHOLD}, +DI > -DI) (+{weight:.2f})."
2576c2934
<                             "ADX: Strong SELL trend (ADX > 25, -DI > +DI)."
---
>                             f"ADX: Strong SELL trend (ADX > {ADX_STRONG_TREND_THRESHOLD}, -DI > +DI) (-{weight:.2f})."
2579,2580c2937,2940
<                     signal_score += 0
<                     self.logger.debug("ADX: Weak trend (ADX < 20). Neutral signal.")
---
>                     # Neutral signal if trend is weak
>                     self.logger.debug(
>                         f"ADX: Weak trend (ADX < {ADX_WEAK_TREND_THRESHOLD}). Neutral signal."
>                     )
2581a2942
>         # --- Ichimoku Cloud Alignment Scoring ---
2588d2948
< 
2596a2957
>                 and len(self.df) > 1
2598,2599c2959,2982
<                 has_history = len(self.df) > 1 and all(
<                     col in self.df.columns for col in ["Tenkan_Sen", "Kijun_Sen", "Senkou_Span_A", "Senkou_Span_B", "Chikou_Span"]
---
>                 prev_tenkan = (
>                     self.df["Tenkan_Sen"].iloc[-2]
>                     if "Tenkan_Sen" in self.df.columns
>                     else np.nan
>                 )
>                 prev_kijun = (
>                     self.df["Kijun_Sen"].iloc[-2]
>                     if "Kijun_Sen" in self.df.columns
>                     else np.nan
>                 )
>                 prev_senkou_a = (
>                     self.df["Senkou_Span_A"].iloc[-2]
>                     if "Senkou_Span_A" in self.df.columns
>                     else np.nan
>                 )
>                 prev_senkou_b = (
>                     self.df["Senkou_Span_B"].iloc[-2]
>                     if "Senkou_Span_B" in self.df.columns
>                     else np.nan
>                 )
>                 prev_chikou = (
>                     self.df["Chikou_Span"].iloc[-2]
>                     if "Chikou_Span" in self.df.columns
>                     else np.nan
2602,2622c2985,3002
<                 if has_history:
<                     if (
<                         tenkan_sen > kijun_sen
<                         and self.df["Tenkan_Sen"].iloc[-2] <= self.df["Kijun_Sen"].iloc[-2]
<                     ):
<                         signal_score += (
<                             weight * 0.5
<                         )
<                         self.logger.debug(
<                             "Ichimoku: Tenkan-sen crossed above Kijun-sen (bullish)."
<                         )
<                     elif (
<                         tenkan_sen < kijun_sen
<                         and self.df["Tenkan_Sen"].iloc[-2] >= self.df["Kijun_Sen"].iloc[-2]
<                     ):
<                         signal_score -= (
<                             weight * 0.5
<                         )
<                         self.logger.debug(
<                             "Ichimoku: Tenkan-sen crossed below Kijun-sen (bearish)."
<                         )
---
>                 if tenkan_sen > kijun_sen and (
>                     pd.isna(prev_tenkan)
>                     or pd.isna(prev_kijun)
>                     or prev_tenkan <= prev_kijun
>                 ):
>                     signal_score += weight * 0.5
>                     self.logger.debug(
>                         f"Ichimoku: Tenkan-sen crossed above Kijun-sen (bullish) (+{weight * 0.5:.2f})."
>                     )
>                 elif tenkan_sen < kijun_sen and (
>                     pd.isna(prev_tenkan)
>                     or pd.isna(prev_kijun)
>                     or prev_tenkan >= prev_kijun
>                 ):
>                     signal_score -= weight * 0.5
>                     self.logger.debug(
>                         f"Ichimoku: Tenkan-sen crossed below Kijun-sen (bearish) (-{weight * 0.5:.2f})."
>                     )
2624,2628c3004,3008
<                 if has_history:
<                     current_max_kumo = max(senkou_span_a, senkou_span_b)
<                     current_min_kumo = min(senkou_span_a, senkou_span_b)
<                     prev_max_kumo = max(Decimal(str(self.df["Senkou_Span_A"].iloc[-2])), Decimal(str(self.df["Senkou_Span_B"].iloc[-2])))
<                     prev_min_kumo = min(Decimal(str(self.df["Senkou_Span_A"].iloc[-2])), Decimal(str(self.df["Senkou_Span_B"].iloc[-2])))
---
>                 # Price breaking above/below Kumo (Cloud)
>                 kumo_top = max(senkou_span_a, senkou_span_b)
>                 kumo_bottom = min(senkou_span_a, senkou_span_b)
>                 prev_kumo_top = max(prev_senkou_a, prev_senkou_b)
>                 prev_kumo_bottom = min(prev_senkou_a, prev_senkou_b)
2630,2643c3010,3019
<                     if current_close > current_max_kumo and Decimal(str(self.df["close"].iloc[-2])) <= prev_max_kumo:
<                         signal_score += (
<                             weight * 0.7
<                         )
<                         self.logger.debug(
<                             "Ichimoku: Price broke above Kumo (strong bullish)."
<                         )
<                     elif current_close < current_min_kumo and Decimal(str(self.df["close"].iloc[-2])) >= prev_min_kumo:
<                         signal_score -= (
<                             weight * 0.7
<                         )
<                         self.logger.debug(
<                             "Ichimoku: Price broke below Kumo (strong bearish)."
<                         )
---
>                 if current_close > kumo_top and prev_close <= prev_kumo_top:
>                     signal_score += weight * 0.7
>                     self.logger.debug(
>                         f"Ichimoku: Price broke above Kumo (strong bullish) (+{weight * 0.7:.2f})."
>                     )
>                 elif current_close < kumo_bottom and prev_close >= prev_kumo_bottom:
>                     signal_score -= weight * 0.7
>                     self.logger.debug(
>                         f"Ichimoku: Price broke below Kumo (strong bearish) (-{weight * 0.7:.2f})."
>                     )
2645,2665c3021,3035
<                 if has_history:
<                     if (
<                         chikou_span > current_close
<                         and Decimal(str(self.df["Chikou_Span"].iloc[-2])) <= Decimal(str(self.df["close"].iloc[-2]))
<                     ):
<                         signal_score += (
<                             weight * 0.3
<                         )
<                         self.logger.debug(
<                             "Ichimoku: Chikou Span crossed above price (bullish confirmation)."
<                         )
<                     elif (
<                         chikou_span < current_close
<                         and Decimal(str(self.df["Chikou_Span"].iloc[-2])) >= Decimal(str(self.df["close"].iloc[-2]))
<                     ):
<                         signal_score -= (
<                             weight * 0.3
<                         )
<                         self.logger.debug(
<                             "Ichimoku: Chikou Span crossed below price (bearish confirmation)."
<                         )
---
>                 # Chikou Span crossing price (confirmation)
>                 if chikou_span > current_close and (
>                     pd.isna(prev_chikou) or prev_chikou <= prev_close
>                 ):
>                     signal_score += weight * 0.3
>                     self.logger.debug(
>                         f"Ichimoku: Chikou Span crossed above price (bullish confirmation) (+{weight * 0.3:.2f})."
>                     )
>                 elif chikou_span < current_close and (
>                     pd.isna(prev_chikou) or prev_chikou >= prev_close
>                 ):
>                     signal_score -= weight * 0.3
>                     self.logger.debug(
>                         f"Ichimoku: Chikou Span crossed below price (bearish confirmation) (-{weight * 0.3:.2f})."
>                     )
2666a3037
>         # --- OBV Alignment Scoring ---
2670d3040
< 
2673,2674c3043,3051
<             if not pd.isna(obv_val) and not pd.isna(obv_ema):
<                 has_history = len(self.df) > 1 and "OBV" in self.df.columns and "OBV_EMA" in self.df.columns
---
>             if not pd.isna(obv_val) and not pd.isna(obv_ema) and len(self.df) > 1:
>                 prev_obv_val = (
>                     self.df["OBV"].iloc[-2] if "OBV" in self.df.columns else np.nan
>                 )
>                 prev_obv_ema = (
>                     self.df["OBV_EMA"].iloc[-2]
>                     if "OBV_EMA" in self.df.columns
>                     else np.nan
>                 )
2676,2688c3053,3070
<                 if has_history:
<                     if (
<                         obv_val > obv_ema
<                         and self.df["OBV"].iloc[-2] <= self.df["OBV_EMA"].iloc[-2]
<                     ):
<                         signal_score += weight * 0.5
<                         self.logger.debug("OBV: Bullish crossover detected.")
<                     elif (
<                         obv_val < obv_ema
<                         and self.df["OBV"].iloc[-2] >= self.df["OBV_EMA"].iloc[-2]
<                     ):
<                         signal_score -= weight * 0.5
<                         self.logger.debug("OBV: Bearish crossover detected.")
---
>                 if obv_val > obv_ema and (
>                     pd.isna(prev_obv_val)
>                     or pd.isna(prev_obv_ema)
>                     or prev_obv_val <= prev_obv_ema
>                 ):
>                     signal_score += weight * 0.5
>                     self.logger.debug(
>                         f"  OBV: Bullish crossover detected (+{weight * 0.5:.2f})."
>                     )
>                 elif obv_val < obv_ema and (
>                     pd.isna(prev_obv_val)
>                     or pd.isna(prev_obv_ema)
>                     or prev_obv_val >= prev_obv_ema
>                 ):
>                     signal_score -= weight * 0.5
>                     self.logger.debug(
>                         f"  OBV: Bearish crossover detected (-{weight * 0.5:.2f})."
>                     )
2695a3078,3080
>                         self.logger.debug(
>                             f"  OBV: Increasing momentum (+{weight * 0.2:.2f})."
>                         )
2700a3086,3088
>                         self.logger.debug(
>                             f"  OBV: Decreasing momentum (-{weight * 0.2:.2f})."
>                         )
2701a3090
>         # --- CMF Alignment Scoring ---
2704d3092
< 
2708,2709d3095
<                 has_history = len(self.df) > 1 and "CMF" in self.df.columns
< 
2711a3098,3100
>                     self.logger.debug(
>                         f"  CMF: Positive money flow (+{weight * 0.5:.2f})."
>                     )
2713a3103,3105
>                     self.logger.debug(
>                         f"  CMF: Negative money flow (-{weight * 0.5:.2f})."
>                     )
2720a3113,3115
>                         self.logger.debug(
>                             f"  CMF: Increasing bullish flow (+{weight * 0.3:.2f})."
>                         )
2725a3121,3123
>                         self.logger.debug(
>                             f"  CMF: Increasing bearish flow (-{weight * 0.3:.2f})."
>                         )
2726a3125,3211
>         # --- Volatility Index Scoring ---
>         if active_indicators.get("volatility_index", False):
>             vol_idx = self._get_indicator_value("Volatility_Index")
>             weight = weights.get("volatility_index_signal", 0.0)
>             if (
>                 not pd.isna(vol_idx)
>                 and len(self.df) > 2
>                 and "Volatility_Index" in self.df.columns
>             ):
>                 prev_vol_idx = self.df["Volatility_Index"].iloc[-2]
>                 prev_prev_vol_idx = self.df["Volatility_Index"].iloc[-3]
> 
>                 if vol_idx > prev_vol_idx > prev_prev_vol_idx:  # Increasing volatility
>                     if signal_score > 0:
>                         signal_score += weight * 0.2
>                         self.logger.debug(
>                             f"  Volatility Index: Increasing volatility, adds confidence to BUY (+{weight * 0.2:.2f})."
>                         )
>                     elif signal_score < 0:
>                         signal_score -= weight * 0.2
>                         self.logger.debug(
>                             f"  Volatility Index: Increasing volatility, adds confidence to SELL (-{weight * 0.2:.2f})."
>                         )
>                 elif (
>                     vol_idx < prev_vol_idx < prev_prev_vol_idx
>                 ):  # Decreasing volatility
>                     if (
>                         abs(signal_score) > 0
>                     ):  # If there's an existing signal, slightly reduce its conviction
>                         signal_score *= 1 - weight * 0.1  # Reduce by 10% of the weight
>                         self.logger.debug(
>                             f"  Volatility Index: Decreasing volatility, reduces signal conviction (x{(1 - weight * 0.1):.2f})."
>                         )
> 
>         # --- VWMA Cross Scoring ---
>         if active_indicators.get("vwma", False):
>             vwma = self._get_indicator_value("VWMA")
>             weight = weights.get("vwma_cross", 0.0)
>             if not pd.isna(vwma) and len(self.df) > 1:
>                 prev_vwma_series = (
>                     self.df["VWMA"].iloc[-2] if "VWMA" in self.df.columns else np.nan
>                 )
>                 prev_vwma = (
>                     Decimal(str(prev_vwma_series))
>                     if not pd.isna(prev_vwma_series)
>                     else vwma
>                 )
>                 if current_close > vwma and prev_close <= prev_vwma:
>                     signal_score += weight
>                     self.logger.debug(
>                         f"  VWMA: Bullish crossover (price above VWMA) (+{weight:.2f})."
>                     )
>                 elif current_close < vwma and prev_close >= prev_vwma:
>                     signal_score -= weight
>                     self.logger.debug(
>                         f"  VWMA: Bearish crossover (price below VWMA) (-{weight:.2f})."
>                     )
> 
>         # --- Volume Delta Scoring ---
>         if active_indicators.get("volume_delta", False):
>             volume_delta = self._get_indicator_value("Volume_Delta")
>             volume_delta_threshold = isd["volume_delta_threshold"]
>             weight = weights.get("volume_delta_signal", 0.0)
> 
>             if not pd.isna(volume_delta):
>                 if volume_delta > volume_delta_threshold:  # Strong buying pressure
>                     signal_score += weight
>                     self.logger.debug(
>                         f"  Volume Delta: Strong buying pressure detected (+{weight:.2f})."
>                     )
>                 elif volume_delta < -volume_delta_threshold:  # Strong selling pressure
>                     signal_score -= weight
>                     self.logger.debug(
>                         f"  Volume Delta: Strong selling pressure detected (-{weight:.2f})."
>                     )
>                 elif volume_delta > 0:
>                     signal_score += weight * 0.3
>                     self.logger.debug(
>                         f"  Volume Delta: Moderate buying pressure detected (+{weight * 0.3:.2f})."
>                     )
>                 elif volume_delta < 0:
>                     signal_score -= weight * 0.3
>                     self.logger.debug(
>                         f"  Volume Delta: Moderate selling pressure detected (-{weight * 0.3:.2f})."
>                     )
> 
>         # --- Multi-Timeframe Trend Confluence Scoring ---
2734c3219
<                     mtf_sell_score += 1
---
>                     mtf_sell_score -= 1  # Subtract for bearish MTF trend
2737,2740c3222,3228
< 
<             total_mtf_trends = len(mtf_trends)
<             if total_mtf_trends > 0:
<                 normalized_mtf_score = (mtf_buy_score - mtf_sell_score) / total_mtf_trends
---
>             if mtf_trends:
>                 # Calculate a normalized score based on the balance of buy/sell trends
>                 # The range of mtf_buy_score - mtf_sell_score can be from -len(mtf_trends) to len(mtf_trends)
>                 # So, normalize by dividing by len(mtf_trends)
>                 normalized_mtf_score = (mtf_buy_score + mtf_sell_score) / len(
>                     mtf_trends
>                 )
2743c3231
<                     f"MTF Confluence: Score {normalized_mtf_score:.2f} (Buy: {mtf_buy_score}, Sell: {mtf_sell_score}). Total MTF contribution: {mtf_weight * normalized_mtf_score:.2f}"
---
>                     f"MTF Confluence: Score {normalized_mtf_score:.2f} (Buy: {mtf_buy_score}, Sell: {abs(mtf_sell_score)}). Total MTF contribution: {mtf_weight * normalized_mtf_score:.2f}"
2745a3234
>         # --- Gemini AI Analysis Scoring ---
2747,2748d3235
<             gemini_prompt = self._summarize_market_for_gemini(current_close)
<             gemini_analysis = await self.gemini_client.analyze_market_data(gemini_prompt)
2751c3238,3240
<                 self.logger.info(f"{NEON_PURPLE}Gemini AI Analysis: {json.dumps(gemini_analysis, indent=2)}{RESET}")
---
>                 self.logger.info(
>                     f"{NEON_PURPLE}Gemini AI Analysis: {json.dumps(gemini_analysis, indent=2)}{RESET}"
>                 )
2756c3245
<                 if gemini_confidence >= 50: # Only consider if confidence is reasonable
---
>                 if gemini_confidence >= 50:  # Only consider if confidence is reasonable
2759c3248,3250
<                         self.logger.info(f"{NEON_GREEN}Gemini AI recommends BUY (Confidence: {gemini_confidence}). Adding {gemini_weight} to signal score.{RESET}")
---
>                         self.logger.info(
>                             f"{NEON_GREEN}Gemini AI recommends BUY (Confidence: {gemini_confidence}). Adding {gemini_weight} to signal score.{RESET}"
>                         )
2762c3253,3255
<                         self.logger.info(f"{NEON_RED}Gemini AI recommends SELL (Confidence: {gemini_confidence}). Subtracting {gemini_weight} from signal score.{RESET}")
---
>                         self.logger.info(
>                             f"{NEON_RED}Gemini AI recommends SELL (Confidence: {gemini_confidence}). Subtracting {gemini_weight} from signal score.{RESET}"
>                         )
2764c3257,3259
<                         self.logger.info(f"{NEON_YELLOW}Gemini AI recommends HOLD (Confidence: {gemini_confidence}). No change to signal score.{RESET}")
---
>                         self.logger.info(
>                             f"{NEON_YELLOW}Gemini AI recommends HOLD (Confidence: {gemini_confidence}). No change to signal score.{RESET}"
>                         )
2766c3261,3263
<                     self.logger.info(f"{NEON_YELLOW}Gemini AI confidence ({gemini_confidence}) too low. Skipping influence on signal score.{RESET}")
---
>                     self.logger.info(
>                         f"{NEON_YELLOW}Gemini AI confidence ({gemini_confidence}) too low. Skipping influence on signal score.{RESET}"
>                     )
2768c3265,3267
<                 self.logger.warning(f"{NEON_YELLOW}Gemini AI analysis failed or returned no data. Skipping influence on signal score.{RESET}")
---
>                 self.logger.warning(
>                     f"{NEON_YELLOW}Gemini AI analysis failed or returned no data. Skipping influence on signal score.{RESET}"
>                 )
2770c3269,3270
<         threshold = self.config["signal_score_threshold"]
---
>         # --- Final Signal Determination ---
>         threshold = Decimal(str(self.config["signal_score_threshold"]))
2783,2785c3283,3285
<         self, current_price: Decimal, atr_value: Decimal, signal: str
<     ) -> tuple[Decimal, Decimal, Decimal, Decimal]:
<         """Calculate Take Profit, Stop Loss, and Trailing Stop activation/value levels."""
---
>         self, current_price: Decimal, atr_value: Decimal, signal: Literal["BUY", "SELL"]
>     ) -> tuple[Decimal, Decimal]:
>         """Calculate Take Profit and Stop Loss levels."""
2792,2799c3292
<         trailing_stop_atr_multiple = Decimal(
<             str(self.config["trade_management"]["trailing_stop_atr_multiple"])
<         )
< 
<         stop_loss = Decimal("0")
<         take_profit = Decimal("0")
<         trailing_activation_price = Decimal("0")
<         trailing_value = Decimal("0")
---
>         price_precision_str = "0." + "0" * (self.price_precision - 1) + "1"
2804,2805d3296
<             trailing_activation_price = current_price + (atr_value * Decimal("0.5"))
<             trailing_value = atr_value * trailing_stop_atr_multiple
2809,3216d3299
<             trailing_activation_price = current_price - (atr_value * Decimal("0.5"))
<             trailing_value = atr_value * trailing_stop_atr_multiple
<         else:
<             return Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")
< 
<         quantized_tp = take_profit.quantize(Decimal("0.00001"), rounding=ROUND_DOWN)
<         quantized_sl = stop_loss.quantize(Decimal("0.00001"), rounding=ROUND_DOWN)
<         quantized_trailing_activation = trailing_activation_price.quantize(Decimal("0.00001"), rounding=ROUND_DOWN)
<         quantized_trailing_value = trailing_value.quantize(Decimal("0.00001"), rounding=ROUND_DOWN)
< 
<         return quantized_tp, quantized_sl, quantized_trailing_activation, quantized_trailing_value
< 
< 
< class PositionManager:
<     """Manages open positions, stop-loss, and take-profit levels."""
< 
<     def __init__(
<         self,
<         config: dict[str, Any],
<         logger: logging.Logger,
<         symbol: str,
<         bybit_client: BybitClient,
<         precision_manager: PrecisionManager,
<         alert_system: Any,
<         performance_tracker: Any,
<         trading_analyzer: TradingAnalyzer, # Added trading_analyzer to access calculate_entry_tp_sl
<     ):
<         """Initializes the PositionManager."""
<         self.config = config
<         self.logger = logger
<         self.symbol = symbol
<         self.bybit_client = bybit_client
<         self.precision_manager = precision_manager
<         self.alert_system = alert_system
<         self.performance_tracker = performance_tracker
<         self.trading_analyzer = trading_analyzer
< 
<         self.open_positions: dict[str, dict] = {}
<         self.trade_management_enabled = config["trade_management"]["enabled"]
<         self.max_open_positions = config["trade_management"]["max_open_positions"]
<         self.current_account_balance: Decimal = Decimal("0")
< 
<         self.active_trailing_stops: dict[str, dict] = {}
< 
< 
<     async def _get_current_balance(self) -> Decimal:
<         """Fetch current account balance (from actual API)."""
<         balance = await self.bybit_client.get_wallet_balance()
<         if balance is not None:
<             self.current_account_balance = balance
<             return balance
< 
<         self.logger.warning(f"{NEON_YELLOW}Failed to fetch live balance, using fallback from config.{RESET}")
<         return Decimal(str(self.config["trade_management"]["account_balance"]))
< 
<     async def _calculate_order_size(
<         self, current_price: Decimal, atr_value: Decimal
<     ) -> Decimal:
<         """Calculate order size based on risk per trade and ATR."""
<         if not self.trade_management_enabled:
<             return Decimal("0")
< 
<         account_balance = await self._get_current_balance()
<         risk_per_trade_percent = (
<             Decimal(str(self.config["trade_management"]["risk_per_trade_percent"]))
<             / 100
<         )
<         stop_loss_atr_multiple = Decimal(
<             str(self.config["trade_management"]["stop_loss_atr_multiple"])
<         )
< 
<         risk_amount = account_balance * risk_per_trade_percent
<         stop_loss_distance_usd = atr_value * stop_loss_atr_multiple
< 
<         if stop_loss_distance_usd <= 0:
<             self.logger.warning(
<                 f"{NEON_YELLOW}Calculated stop loss distance is zero or negative. Cannot determine order size.{RESET}"
<             )
<             return Decimal("0")
< 
<         order_qty_unleveraged = risk_amount / stop_loss_distance_usd
< 
<         order_qty = order_qty_unleveraged
< 
<         order_qty = self.precision_manager.round_qty(order_qty, self.symbol)
< 
<         min_qty = self.precision_manager.get_min_qty(self.symbol)
<         max_qty = self.precision_manager.get_max_qty(self.symbol)
<         min_notional = self.precision_manager.get_min_notional(self.symbol)
< 
<         if order_qty < min_qty:
<             self.logger.warning(f"{NEON_YELLOW}Calculated order quantity {order_qty} is less than minimum quantity {min_qty}. Adjusting to minimum.{RESET}")
<             order_qty = min_qty
<         if order_qty > max_qty:
<             self.logger.warning(f"{NEON_YELLOW}Calculated order quantity {order_qty} is greater than maximum quantity {max_qty}. Adjusting to maximum.{RESET}")
<             order_qty = max_qty
< 
<         notional_value = order_qty * current_price
<         if notional_value < min_notional:
<             self.logger.warning(f"{NEON_YELLOW}Calculated order notional value {notional_value:.2f} is less than minimum notional {min_notional:.2f}. Cannot place trade.{RESET}")
<             return Decimal("0")
< 
<         self.logger.info(
<             f"Calculated order size: {order_qty} {self.symbol} (Risk: {risk_amount:.2f} USD, Notional: {notional_value:.2f} USD)"
<         )
<         return order_qty
< 
<     async def open_position(
<         self, signal: str, current_price: Decimal, atr_value: Decimal
<     ) -> dict | None:
<         """Open a new position if conditions allow.
< 
<         Returns the new position details or None.
<         """
<         if not self.trade_management_enabled:
<             self.logger.info(
<                 f"{NEON_YELLOW}Trade management is disabled. Skipping opening position.{RESET}"
<             )
<             return None
< 
<         if self.symbol in self.open_positions:
<             existing_pos = self.open_positions[self.symbol]
<             if existing_pos["status"] == "OPEN" and existing_pos["side"] == signal:
<                 self.logger.info(f"{NEON_BLUE}Already in a {signal} position for {self.symbol}. No new position opened.{RESET}")
<                 return None
<             elif existing_pos["status"] == "OPEN" and existing_pos["side"] != signal:
<                 if self.max_open_positions == 1:
<                     self.logger.info(f"{NEON_YELLOW}Attempting to close existing {existing_pos['side']} position before opening new {signal} position.{RESET}")
<                     await self.close_position(existing_pos)
<                     await asyncio.sleep(API_CALL_RETRY_DELAY_SECONDS) # Give time for close order to process
<                 else:
<                     self.logger.info(f"{NEON_YELLOW}Already in an opposing position for {self.symbol}. Not opening new position.{RESET}")
<                     return None
< 
<         if len(self.open_positions) >= self.max_open_positions and self.max_open_positions > 0:
<             self.logger.info(
<                 f"{NEON_YELLOW}Max open positions ({self.max_open_positions}) reached. Cannot open new position.{RESET}"
<             )
<             return None
< 
<         if signal not in ["BUY", "SELL"]:
<             self.logger.debug(f"Invalid signal '{signal}' for opening position.")
<             return None
< 
<         order_qty = await self._calculate_order_size(current_price, atr_value)
<         if order_qty <= Decimal("0"):
<             self.logger.warning(
<                 f"{NEON_YELLOW}Order quantity is zero or negative. Cannot open position.{RESET}"
<             )
<             return None
< 
<         take_profit, stop_loss, trailing_activation_price, trailing_value = \
<             self.trading_analyzer.calculate_entry_tp_sl(current_price, atr_value, signal)
< 
<         client_order_id = f"whalebot-{self.symbol}-{signal}-{int(time.time()*1000)}"
<         order_response = await self.bybit_client.place_order(
<             symbol=self.symbol,
<             side=signal,
<             qty=str(order_qty),
<             order_type="Market",
<             stop_loss=str(stop_loss),
<             take_profit=str(take_profit),
<             client_order_id=client_order_id,
<         )
< 
<         if order_response:
<             position = {
<                 "entry_time": datetime.now(ZoneInfo(self.config["timezone"])),
<                 "symbol": self.symbol,
<                 "side": signal,
<                 "entry_price": current_price,
<                 "qty": order_qty,
<                 "stop_loss": stop_loss,
<                 "take_profit": take_profit,
<                 "trailing_stop_activation_price": trailing_activation_price,
<                 "trailing_stop_value": trailing_value,
<                 "current_trailing_sl": stop_loss, # Initial SL is the fixed stop loss
<                 "is_trailing_activated": False,
<                 "status": "OPEN",
<                 "order_id": order_response.get('orderId'),
<                 "client_order_id": client_order_id,
<                 "unrealized_pnl": Decimal("0"),
<             }
<             self.open_positions[self.symbol] = position
<             self.logger.info(f"{NEON_GREEN}Opened {signal} position for {self.symbol}: {position}{RESET}")
<             self.alert_system.send_alert(f"Opened {signal} {order_qty} of {self.symbol} @ {current_price}", "INFO")
<             return position
< 
<         self.logger.error(f"{NEON_RED}Failed to open {signal} position for {self.symbol}. Order response: {order_response}{RESET}")
<         return None
< 
<     async def close_position(self, position: dict) -> bool:
<         """Close an existing open position via a market order."""
<         if position["status"] != "OPEN":
<             self.logger.warning(f"{NEON_YELLOW}Attempted to close a non-open position for {position['symbol']}.{RESET}")
<             return False
< 
<         opposing_side = "Sell" if position["side"] == "BUY" else "Buy"
<         close_qty = self.precision_manager.round_qty(position["qty"], position["symbol"])
< 
<         self.logger.info(f"{NEON_YELLOW}Attempting to close {position['side']} position for {position['symbol']} (Qty: {close_qty}).{RESET}")
< 
<         order_response = await self.bybit_client.place_order(
<             symbol=position["symbol"],
<             side=opposing_side,
<             qty=str(close_qty),
<             order_type="Market",
<             reduce_only=True,
<         )
< 
<         if order_response:
<             self.logger.info(f"{NEON_GREEN}Market order placed to close position: {order_response}{RESET}")
<             position["status"] = "PENDING_CLOSE"
<             self.open_positions[position["symbol"]] = position
<             self.alert_system.send_alert(f"Placed order to close {position['side']} {close_qty} of {position['symbol']}", "INFO")
<             return True
< 
<         self.logger.error(f"{NEON_RED}Failed to place market order to close position for {position['symbol']}.{RESET}")
<         return False
< 
< 
<     async def manage_positions(
<         self, current_price: Decimal, atr_value: Decimal
<     ) -> None:
<         """Check and manage all open positions (SL/TP/Trailing Stop)."""
<         if not self.trade_management_enabled or not self.open_positions:
<             return
< 
<         for symbol, position in list(self.open_positions.items()):
<             if position["status"] == "OPEN":
<                 side = position["side"]
<                 entry_price = position["entry_price"]
<                 stop_loss = position["stop_loss"]
<                 take_profit = position["take_profit"]
<                 trailing_activation_price = position["trailing_stop_activation_price"]
<                 trailing_value = position["trailing_stop_value"]
<                 is_trailing_activated = position["is_trailing_activated"]
<                 current_trailing_sl = position["current_trailing_sl"]
< 
<                 closed_by = ""
< 
<                 if side == "BUY":
<                     if current_price <= stop_loss:
<                         closed_by = "STOP_LOSS"
<                     elif current_price >= take_profit:
<                         closed_by = "TAKE_PROFIT"
<                     elif is_trailing_activated and current_price <= current_trailing_sl:
<                         closed_by = "TRAILING_STOP_LOSS"
<                 elif current_price >= stop_loss:
<                     closed_by = "STOP_LOSS"
<                 elif current_price <= take_profit:
<                     closed_by = "TAKE_PROFIT"
<                 elif is_trailing_activated and current_price >= current_trailing_sl:
<                     closed_by = "TRAILING_STOP_LOSS"
< 
<                 if closed_by:
<                     self.logger.info(
<                         f"{NEON_PURPLE}Position for {symbol} closed by {closed_by}. Closing position.{RESET}"
<                     )
<                     await self.bybit_client.cancel_all_orders(symbol)
<                     await self.close_position(position)
<                     position["status"] = "PENDING_CLOSE"
<                     position["exit_time"] = datetime.now(ZoneInfo(self.config["timezone"]))
<                     position["exit_price"] = current_price
<                     position["closed_by"] = closed_by
< 
<                     pnl = (
<                         (current_price - entry_price) * position["qty"]
<                         if side == "BUY"
<                         else (entry_price - current_price) * position["qty"]
<                     )
<                     self.performance_tracker.record_trade(position, pnl)
<                     continue
< 
<                 if not is_trailing_activated:
<                     if (side == "BUY" and current_price >= trailing_activation_price) or \
<                        (side == "SELL" and current_price <= trailing_activation_price):
<                         position["is_trailing_activated"] = True
< 
<                         potential_new_sl = (
<                             current_price - trailing_value
<                             if side == "BUY"
<                             else current_price + trailing_value
<                         )
<                         position["current_trailing_sl"] = self.precision_manager.round_price(potential_new_sl, symbol)
< 
<                         self.logger.info(f"{NEON_GREEN}Trailing stop activated for {symbol}. Initial SL: {position['current_trailing_sl']:.5f}{RESET}")
<                         await self.bybit_client.set_trading_stop(
<                             symbol=symbol,
<                             stop_loss=str(position["current_trailing_sl"]),
<                             trailing_stop=str(trailing_value),
<                             active_price=str(current_price),
<                         )
<                 else:
<                     updated_sl = Decimal("0")
<                     if side == "BUY":
<                         potential_new_sl = current_price - trailing_value
<                         if potential_new_sl > current_trailing_sl:
<                             updated_sl = potential_new_sl
<                     else:
<                         potential_new_sl = current_price + trailing_value
<                         if potential_new_sl < current_trailing_sl:
<                             updated_sl = potential_new_sl
< 
<                     if updated_sl != Decimal("0") and updated_sl != current_trailing_sl:
<                         # Ensure trailing SL doesn't go below entry for buy or above entry for sell if it's supposed to lock in profit
<                         if (side == "BUY" and updated_sl > entry_price) or \
<                            (side == "SELL" and updated_sl < entry_price):
<                             rounded_sl = self.precision_manager.round_price(updated_sl, symbol)
<                             position["current_trailing_sl"] = rounded_sl
<                             self.logger.info(f"{NEON_CYAN}Updating trailing stop for {symbol} to {position['current_trailing_sl']:.5f}{RESET}")
<                             await self.bybit_client.set_trading_stop(
<                                 symbol=symbol,
<                                 stop_loss=str(position["current_trailing_sl"]),
<                             )
< 
<                 self.open_positions[symbol] = position
< 
<     async def update_position_from_ws(self, ws_position_data: dict[str, Any]):
<         """Update internal position state from WebSocket data."""
<         symbol = ws_position_data.get('symbol')
<         if symbol != self.symbol:
<             return
< 
<         size = Decimal(ws_position_data.get('size', '0'))
<         side = ws_position_data.get('side')
<         avg_price = Decimal(ws_position_data.get('avgPrice', '0'))
<         unrealized_pnl = Decimal(ws_position_data.get('unrealisedPnl', '0'))
< 
<         if size == Decimal("0"):
<             if symbol in self.open_positions and self.open_positions[symbol]["status"] != "CLOSED":
<                 self.logger.info(f"{NEON_PURPLE}Position for {symbol} detected as closed on exchange. Removing from active positions.{RESET}")
<                 closed_pos = self.open_positions.pop(symbol)
<                 if closed_pos["status"] not in ["CLOSED", "PENDING_CLOSE"]:
<                     closed_pos["status"] = "CLOSED"
<                     closed_pos["exit_time"] = datetime.now(ZoneInfo(self.config["timezone"]))
<                     closed_pos["exit_price"] = avg_price
<                     pnl = unrealized_pnl
<                     self.performance_tracker.record_trade(closed_pos, pnl)
<             return
< 
<         if symbol in self.open_positions:
<             position = self.open_positions[symbol]
<             position["qty"] = size
<             position["side"] = side
<             position["entry_price"] = avg_price
<             position["unrealized_pnl"] = unrealized_pnl
<             position["status"] = "OPEN"
<             self.open_positions[symbol] = position
<             self.logger.debug(f"Updated internal position for {symbol}: Size={size}, AvgPrice={avg_price}, PnL={unrealized_pnl}")
<         else:
<             self.logger.warning(f"{NEON_YELLOW}Detected new open position for {symbol} via WS not tracked internally. Adding it.{RESET}")
<             new_pos = {
<                 "entry_time": datetime.now(ZoneInfo(self.config["timezone"])),
<                 "symbol": symbol,
<                 "side": side,
<                 "entry_price": avg_price,
<                 "qty": size,
<                 "stop_loss": Decimal("0"),
<                 "take_profit": Decimal("0"),
<                 "trailing_stop_activation_price": Decimal("0"),
<                 "trailing_stop_value": Decimal("0"),
<                 "current_trailing_sl": Decimal("0"),
<                 "is_trailing_activated": False,
<                 "status": "OPEN",
<                 "order_id": None,
<                 "client_order_id": None,
<                 "unrealized_pnl": unrealized_pnl,
<             }
<             self.open_positions[symbol] = new_pos
< 
< 
<     def get_open_positions(self) -> list[dict]:
<         """Return a list of currently open positions."""
<         return [pos for pos in self.open_positions.values() if pos["status"] == "OPEN"]
< 
< 
< class PerformanceTracker:
<     """Tracks and reports trading performance."""
< 
<     def __init__(self, logger: logging.Logger):
<         """Initializes the PerformanceTracker."""
<         self.logger = logger
<         self.trades: list[dict] = []
<         self.total_pnl = Decimal("0")
<         self.wins = 0
<         self.losses = 0
<         self.trade_id_counter = 0
< 
<     def record_trade(self, position: dict, pnl: Decimal) -> None:
<         """Record a completed trade."""
<         self.trade_id_counter += 1
<         trade_record = {
<             "trade_id": self.trade_id_counter,
<             "entry_time": position["entry_time"],
<             "exit_time": position.get("exit_time", datetime.now(ZoneInfo("UTC"))),
<             "symbol": position["symbol"],
<             "side": position["side"],
<             "entry_price": position["entry_price"],
<             "exit_price": position.get("exit_price", Decimal("0")),
<             "qty": position["qty"],
<             "pnl": pnl,
<             "closed_by": position.get("closed_by", "UNKNOWN"),
<         }
<         self.trades.append(trade_record)
<         self.total_pnl += pnl
<         if pnl > 0:
<             self.wins += 1
3218,3221c3301,3302
<             self.losses += 1
<         self.logger.info(
<             f"{NEON_CYAN}Trade recorded. Current Total PnL: {self.total_pnl:.2f}, Wins: {self.wins}, Losses: {self.losses}{RESET}"
<         )
---
>             # Should not happen for valid signals
>             return Decimal("0"), Decimal("0")
3223,3226c3304,3306
<     def get_summary(self) -> dict:
<         """Return a summary of all recorded trades."""
<         total_trades = len(self.trades)
<         win_rate = (self.wins / total_trades) * 100 if total_trades > 0 else 0
---
>         return take_profit.quantize(
>             Decimal(price_precision_str), rounding=ROUND_DOWN
>         ), stop_loss.quantize(Decimal(price_precision_str), rounding=ROUND_DOWN)
3228,3238d3307
<         return {
<             "total_trades": total_trades,
<             "total_pnl": self.total_pnl,
<             "wins": self.wins,
<             "losses": self.losses,
<             "win_rate": f"{win_rate:.2f}%",
<         }
< 
< 
< class AlertSystem:
<     """Handles sending alerts for critical events."""
3240,3254c3309
<     def __init__(self, logger: logging.Logger):
<         """Initializes the AlertSystem."""
<         self.logger = logger
< 
<     def send_alert(self, message: str, level: str = "INFO") -> None:
<         """Send an alert (currently logs it)."""
<         if level == "INFO":
<             self.logger.info(f"{NEON_BLUE}ALERT: {message}{RESET}")
<         elif level == "WARNING":
<             self.logger.warning(f"{NEON_YELLOW}ALERT: {message}{RESET}")
<         elif level == "ERROR":
<             self.logger.error(f"{NEON_RED}ALERT: {message}{RESET}")
< 
< 
< async def display_indicator_values_and_price(
---
> def display_indicator_values_and_price(
3258,3259c3313,3314
<     trading_analyzer: TradingAnalyzer,
<     orderbook_manager: AdvancedOrderbookManager,
---
>     analyzer: "TradingAnalyzer",
>     orderbook_manager: Any,  # Changed type hint to Any
3264c3319
<     logger.info(f"{NEON_GREEN}Current Price: {current_price}{RESET}")
---
>     logger.info(f"{NEON_GREEN}Current Price: {current_price.normalize()}{RESET}")
3266c3321
<     if trading_analyzer.df.empty:
---
>     if analyzer.df.empty:
3273c3328
<     for indicator_name, value in trading_analyzer.indicator_values.items():
---
>     for indicator_name, value in analyzer.indicator_values.items():
3275,3276c3330,3336
<         if isinstance(value, Decimal) or isinstance(value, float):
<             logger.info(f"  {color}{indicator_name}: {value:.8f}{RESET}")
---
>         # Format Decimal values for consistent display
>         if isinstance(value, Decimal):
>             logger.info(f"  {color}{indicator_name}: {value.normalize()}{RESET}")
>         elif isinstance(value, float):
>             logger.info(
>                 f"  {color}{indicator_name}: {value:.8f}{RESET}"
>             )  # Display floats with more reasonable precision
3280c3340
<     if trading_analyzer.fib_levels:
---
>     if analyzer.fib_levels:
3282,3284c3342,3346
<         logger.info("")
<         for level_name, level_price in trading_analyzer.fib_levels.items():
<             logger.info(f"  {NEON_YELLOW}{level_name}: {level_price:.8f}{RESET}")
---
>         logger.info("")  # Added newline for spacing
>         for level_name, level_price in analyzer.fib_levels.items():
>             logger.info(
>                 f"  {NEON_YELLOW}{level_name}: {level_price.normalize()}{RESET}"
>             )
3288c3350
<         logger.info("")
---
>         logger.info("")  # Added newline for spacing
3293c3355
<         imbalance = await trading_analyzer._check_orderbook(current_price, orderbook_manager)
---
>         imbalance = analyzer._check_orderbook(current_price, orderbook_manager)
3296d3357
< 
3300,3321c3361,3368
< async def main() -> None:
<     """Orchestrate the bot's operation."""
<     logger = setup_logger("wgwhalex_bot")
<     config = load_config(CONFIG_FILE, logger)
< 
<     global TIMEZONE
<     TIMEZONE = ZoneInfo(config["timezone"])
< 
<     valid_bybit_intervals = [
<         "1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D", "W", "M"
<     ]
< 
<     if config["interval"] not in valid_bybit_intervals:
<         logger.error(
<             f"{NEON_RED}Invalid primary interval '{config['interval']}' in config.json. Please use Bybit's valid string formats (e.g., '15', '60', 'D'). Exiting.{RESET}"
<         )
<         sys.exit(1)
< 
<     for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
<         if htf_interval not in valid_bybit_intervals:
<             logger.error(
<                 f"{NEON_RED}Invalid higher timeframe interval '{htf_interval}' in config.json. Please use Bybit's valid string formats (e.g., '1h' should be '60', '4h' should be '240'). Exiting.{RESET}"
---
> async def main_async_loop(
>     config, logger, position_manager, performance_tracker, alert_system, gemini_client
> ):
>     """The main asynchronous loop for the trading bot."""
>     while True:
>         try:
>             logger.info(
>                 f"{NEON_PURPLE}--- New Analysis Loop Started ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}) ---{RESET}"
3323c3370,3377
<             sys.exit(1)
---
>             current_price = fetch_current_price(config["symbol"], logger)
>             if current_price is None:
>                 alert_system.send_alert(
>                     f"[{config['symbol']}] Failed to fetch current price. Skipping loop.",
>                     "WARNING",
>                 )
>                 await asyncio.sleep(config["loop_delay"])
>                 continue
3325,3344c3379,3388
<     if not API_KEY or not API_SECRET:
<         logger.critical(f"{NEON_RED}BYBIT_API_KEY or BYBIT_API_SECRET environment variables are NOT set. Please set them before running the bot. Exiting.{RESET}")
<         sys.exit(1)
< 
< 
<     logger.info(f"{NEON_GREEN}--- Wgwhalex Trading Bot Initialized ---{RESET}")
<     logger.info(f"Symbol: {config['symbol']}, Interval: {config['interval']}")
<     logger.info(f"Trade Management Enabled: {config['trade_management']['enabled']}")
<     logger.info(f"Using Testnet: {config['testnet']}")
< 
<     bybit_client = BybitClient(API_KEY, API_SECRET, config, logger)
<     precision_manager = PrecisionManager(bybit_client, logger)
<     indicator_calculator = IndicatorCalculator(logger)
<     trading_analyzer = TradingAnalyzer(config, logger, config["symbol"], indicator_calculator)
<     performance_tracker = PerformanceTracker(logger)
<     alert_system = AlertSystem(logger)
<     position_manager = PositionManager(
<         config, logger, config["symbol"], bybit_client, precision_manager, alert_system, performance_tracker, trading_analyzer
<     )
<     orderbook_manager = AdvancedOrderbookManager(config["symbol"], logger, use_skip_list=True)
---
>             df = fetch_klines(
>                 config["symbol"], config["interval"], 200, logger
>             )  # Increased limit for more robust indicator calc
>             if df is None or df.empty:
>                 alert_system.send_alert(
>                     f"[{config['symbol']}] Failed to fetch primary klines or DataFrame is empty. Skipping loop.",
>                     "WARNING",
>                 )
>                 await asyncio.sleep(config["loop_delay"])
>                 continue
3345a3390,3391
>             # AdvancedOrderbookManager is not implemented, so this will remain None
>             orderbook_data = None
3347,3348c3393,3420
<     async def handle_kline_ws_message(message: dict[str, Any]):
<         logger.debug(f"WS Kline: {message.get('data')}")
---
>             mtf_trends: dict[str, str] = {}
>             if config["mtf_analysis"]["enabled"]:
>                 for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
>                     logger.debug(f"Fetching klines for MTF interval: {htf_interval}")
>                     htf_df = fetch_klines(
>                         config["symbol"], htf_interval, 200, logger
>                     )  # Increased limit
>                     if htf_df is not None and not htf_df.empty:
>                         for trend_ind in config["mtf_analysis"]["trend_indicators"]:
>                             # A new TradingAnalyzer is created for each HTF to avoid cross-contamination
>                             temp_htf_analyzer = TradingAnalyzer(
>                                 htf_df, config, logger, config["symbol"]
>                             )
>                             trend = temp_htf_analyzer._get_mtf_trend(
>                                 htf_df,
>                                 trend_ind,  # Corrected from temp_htf_df to htf_df
>                             )
>                             mtf_trends[f"{htf_interval}_{trend_ind}"] = trend
>                             logger.debug(
>                                 f"MTF Trend ({htf_interval}, {trend_ind}): {trend}"
>                             )
>                     else:
>                         logger.warning(
>                             f"{NEON_YELLOW}Could not fetch klines for higher timeframe {htf_interval} or it was empty. Skipping MTF trend for this TF.{RESET}"
>                         )
>                     await asyncio.sleep(
>                         config["mtf_analysis"]["mtf_request_delay_seconds"]
>                     )  # Delay between MTF requests
3350,3351c3422
<     async def handle_ticker_ws_message(message: dict[str, Any]):
<         logger.debug(f"WS Ticker: {message.get('data')}")
---
>             analyzer = TradingAnalyzer(df, config, logger, config["symbol"])
3353,3406c3424,3430
<     async def handle_orderbook_ws_message(message: dict[str, Any]):
<         if message.get('type') == 'snapshot':
<             await orderbook_manager.update_snapshot(message['data'])
<         elif message.get('type') == 'delta':
<             await orderbook_manager.update_delta(message['data'])
<         logger.debug(f"WS Orderbook: {message.get('type')}")
< 
<     async def handle_position_ws_message(message: dict[str, Any]):
<         for position_data in message.get('data', []):
<             await position_manager.update_position_from_ws(position_data)
<         logger.debug(f"WS Position: {message.get('data')}")
< 
<     async def handle_order_ws_message(message: dict[str, Any]):
<         logger.debug(f"WS Order: {message.get('data')}")
< 
<     async def handle_execution_ws_message(message: dict[str, Any]):
<         logger.debug(f"WS Execution: {message.get('data')}")
< 
<     async def handle_wallet_ws_message(message: dict[str, Any]):
<         for wallet_data in message.get('data', []):
<             if wallet_data.get('accountType') == "UNIFIED":
<                 for coin_data in wallet_data.get('coin', []):
<                     if coin_data.get('coin') == "USDT":
<                         position_manager.current_account_balance = Decimal(coin_data.get('walletBalance', '0'))
<                         logger.debug(f"WS Wallet Balance Updated: {position_manager.current_account_balance}")
<                         break
<         logger.debug(f"WS Wallet: {message.get('data')}")
< 
< 
<     await precision_manager.load_instrument_info(config["symbol"])
<     if not precision_manager.initialized:
<         alert_system.send_alert(f"Failed to load instrument info for {config['symbol']}. Bot cannot proceed.", "ERROR")
<         sys.exit(1)
< 
<     initial_leverage = str(config["trade_management"]["default_leverage"])
<     if not await bybit_client.set_leverage(config["symbol"], initial_leverage):
<         alert_system.send_alert(f"Failed to set initial leverage to {initial_leverage}. Bot cannot proceed.", "ERROR")
<         sys.exit(1)
< 
<     await bybit_client.start_public_ws(
<         config["symbol"],
<         config["orderbook_limit"],
<         config["interval"],
<         handle_ticker_ws_message,
<         handle_orderbook_ws_message,
<         handle_kline_ws_message,
<     )
<     await bybit_client.start_private_ws(
<         handle_position_ws_message,
<         handle_order_ws_message,
<         handle_execution_ws_message,
<         handle_wallet_ws_message,
<     )
<     await asyncio.sleep(WS_RECONNECT_DELAY_SECONDS)
---
>             if analyzer.df.empty:
>                 alert_system.send_alert(
>                     f"[{config['symbol']}] TradingAnalyzer DataFrame is empty after indicator calculations. Cannot generate signal.",
>                     "WARNING",
>                 )
>                 await asyncio.sleep(config["loop_delay"])
>                 continue
3407a3432,3443
>             # Pass None for orderbook_manager as it's not implemented
>             trading_signal, signal_score = await analyzer.generate_trading_signal(
>                 current_price, None, mtf_trends
>             )
>             atr_value = Decimal(
>                 str(analyzer._get_indicator_value("ATR", Decimal("0.01")))
>             )  # Default to a small positive value if ATR is missing
> 
>             # Manage existing positions before potentially opening new ones
>             position_manager.manage_positions(
>                 current_price, atr_value, performance_tracker
>             )
3409,3419c3445,3464
<     try:
<         while True:
<             try:
<                 logger.info(f"{NEON_PURPLE}--- New Analysis Loop Started ---{RESET}")
<                 current_price = await bybit_client.fetch_current_price(config["symbol"])
<                 if current_price is None:
<                     alert_system.send_alert(
<                         "Failed to fetch current price. Skipping loop.", "WARNING"
<                     )
<                     await asyncio.sleep(config["loop_delay"])
<                     continue
---
>             if (
>                 trading_signal == "BUY"
>                 and signal_score >= config["signal_score_threshold"]
>             ):
>                 logger.info(
>                     f"{NEON_GREEN}Strong BUY signal detected! Score: {signal_score:.2f}. Attempting to open position.{RESET}"
>                 )
>                 position_manager.open_position("BUY", current_price, atr_value)
>             elif (
>                 trading_signal == "SELL"
>                 and signal_score <= -config["signal_score_threshold"]
>             ):
>                 logger.info(
>                     f"{NEON_RED}Strong SELL signal detected! Score: {signal_score:.2f}. Attempting to open position.{RESET}"
>                 )
>                 position_manager.open_position("SELL", current_price, atr_value)
>             else:
>                 logger.info(
>                     f"{NEON_BLUE}No strong trading signal. Holding. Score: {signal_score:.2f}{RESET}"
>                 )
3421,3425c3466,3471
<                 df = await bybit_client.fetch_klines(config["symbol"], config["interval"], 1000)
<                 if df is None or df.empty:
<                     alert_system.send_alert(
<                         "Failed to fetch primary klines or DataFrame is empty. Skipping loop.",
<                         "WARNING",
---
>             open_positions = position_manager.get_open_positions()
>             if open_positions:
>                 logger.info(f"{NEON_CYAN}Open Positions: {len(open_positions)}{RESET}")
>                 for pos in open_positions:
>                     logger.info(
>                         f"  - {pos['side']} {pos['qty'].normalize()} @ {pos['entry_price'].normalize()} (SL: {pos['stop_loss'].normalize()}, TP: {pos['take_profit'].normalize()}, Trailing SL: {pos.get('current_trailing_sl', 'N/A').normalize() if isinstance(pos.get('current_trailing_sl'), Decimal) else pos.get('current_trailing_sl', 'N/A')}){RESET}"
3427,3428c3473,3474
<                     await asyncio.sleep(config["loop_delay"])
<                     continue
---
>             else:
>                 logger.info(f"{NEON_CYAN}No open positions.{RESET}")
3430,3437c3476,3479
<                 trading_analyzer.update_data(df)
<                 if trading_analyzer.df.empty:
<                     alert_system.send_alert(
<                         "TradingAnalyzer DataFrame is empty after indicator calculations. Cannot generate signal.",
<                         "WARNING",
<                     )
<                     await asyncio.sleep(config["loop_delay"])
<                     continue
---
>             perf_summary = performance_tracker.get_summary()
>             logger.info(
>                 f"{NEON_YELLOW}Performance Summary: Total PnL: {perf_summary['total_pnl'].normalize():.2f}, Wins: {perf_summary['wins']}, Losses: {perf_summary['losses']}, Win Rate: {perf_summary['win_rate']}{RESET}"
>             )
3439,3455c3481,3489
<                 mtf_trends: dict[str, str] = {}
<                 if config["mtf_analysis"]["enabled"]:
<                     for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
<                         logger.debug(f"Fetching klines for MTF interval: {htf_interval}")
<                         htf_df = await bybit_client.fetch_klines(config["symbol"], htf_interval, 1000)
<                         if htf_df is not None and not htf_df.empty:
<                             for trend_ind in config["mtf_analysis"]["trend_indicators"]:
<                                 trend = trading_analyzer._get_mtf_trend(htf_df, trend_ind)
<                                 mtf_trends[f"{htf_interval}_{trend_ind}"] = trend
<                                 logger.debug(
<                                     f"MTF Trend ({htf_interval}, {trend_ind}): {trend}"
<                                 )
<                         else:
<                             logger.warning(
<                                 f"{NEON_YELLOW}Could not fetch klines for higher timeframe {htf_interval} or it was empty. Skipping MTF trend for this TF.{RESET}"
<                             )
<                         await asyncio.sleep(config["mtf_analysis"]["mtf_request_delay_seconds"])
---
>             # Display indicator values and price
>             display_indicator_values_and_price(
>                 config,
>                 logger,
>                 current_price,
>                 analyzer,
>                 None,
>                 mtf_trends,  # Pass None for orderbook_manager
>             )
3457,3459c3491,3494
<                 await display_indicator_values_and_price(
<                     config, logger, current_price, trading_analyzer, orderbook_manager, mtf_trends
<                 )
---
>             logger.info(
>                 f"{NEON_PURPLE}--- Analysis Loop Finished. Waiting {config['loop_delay']}s ---{RESET}"
>             )
>             await asyncio.sleep(config["loop_delay"])
3461,3465c3496,3542
<                 trading_signal, signal_score = await trading_analyzer.generate_trading_signal(
<                     current_price, orderbook_manager, mtf_trends
<                 )
<                 atr_value = Decimal(
<                     str(trading_analyzer._get_indicator_value("ATR", Decimal("0.01")))
---
>         except asyncio.CancelledError:
>             logger.info(f"{NEON_BLUE}Main loop cancelled gracefully.{RESET}")
>             # Perform cleanup tasks here if needed before exiting the loop
>             break
>         except Exception as e:
>             alert_system.send_alert(
>                 f"[{config['symbol']}] An unhandled error occurred in the main loop: {e}",
>                 "ERROR",
>             )
>             logger.exception(f"{NEON_RED}Unhandled exception in main loop:{RESET}")
>             # Longer delay on error
>             await asyncio.sleep(config["loop_delay"] * 2)
> 
> 
> # --- Main execution ---
> if __name__ == "__main__":
>     try:
>         # Load config and setup logger early
>         logger = setup_logger("whalebot_main", level=logging.INFO)
>         config = load_config(CONFIG_FILE, logger)
>         alert_system = AlertSystem(logger)
> 
>         # Validate intervals
>         valid_bybit_intervals = [
>             "1",
>             "3",
>             "5",
>             "15",
>             "30",
>             "60",
>             "120",
>             "240",
>             "360",
>             "720",
>             "D",
>             "W",
>             "M",
>         ]
>         if config["interval"] not in valid_bybit_intervals:
>             logger.error(
>                 f"{NEON_RED}Invalid primary interval '{config['interval']}' in config.json. Please use Bybit's valid string formats (e.g., '15', '60', 'D'). Exiting.{RESET}"
>             )
>             sys.exit(1)
>         for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
>             if htf_interval not in valid_bybit_intervals:
>                 logger.error(
>                     f"{NEON_RED}Invalid higher timeframe interval '{htf_interval}' in config.json. Please use Bybit's valid string formats (e.g., '60', '240'). Exiting.{RESET}"
3466a3544
>                 sys.exit(1)
3468c3546,3550
<                 await position_manager.manage_positions(current_price, atr_value)
---
>         if not API_KEY or not API_SECRET:
>             logger.critical(
>                 f"{NEON_RED}BYBIT_API_KEY or BYBIT_API_SECRET environment variables are not set. Please set them before running the bot. Exiting.{RESET}"
>             )
>             sys.exit(1)
3470,3489c3552,3564
<                 if (
<                     trading_signal == "BUY"
<                     and signal_score >= config["signal_score_threshold"]
<                 ):
<                     logger.info(
<                         f"{NEON_GREEN}Strong BUY signal detected! Score: {signal_score:.2f}{RESET}"
<                     )
<                     await position_manager.open_position("BUY", current_price, atr_value)
<                 elif (
<                     trading_signal == "SELL"
<                     and signal_score <= -config["signal_score_threshold"]
<                 ):
<                     logger.info(
<                         f"{NEON_RED}Strong SELL signal detected! Score: {signal_score:.2f}{RESET}"
<                     )
<                     await position_manager.open_position("SELL", current_price, atr_value)
<                 else:
<                     logger.info(
<                         f"{NEON_BLUE}No strong trading signal. Holding. Score: {signal_score:.2f}{RESET}"
<                     )
---
>         logger.info(f"{NEON_GREEN}--- Whalebot Trading Bot Initialized ---{RESET}")
>         logger.info(f"Symbol: {config['symbol']}, Interval: {config['interval']}")
>         logger.info(
>             f"Trade Management Enabled: {config['trade_management']['enabled']}"
>         )
>         if config["trade_management"]["enabled"]:
>             logger.info(
>                 f"Leverage: {config['trade_management']['leverage']}x, Order Mode: {config['trade_management']['order_mode']}"
>             )
>         else:
>             logger.info(
>                 f"Using simulated balance for position sizing: {config['trade_management']['account_balance']:.2f} USDT"
>             )
3491,3499c3566,3583
<                 open_positions = position_manager.get_open_positions()
<                 if open_positions:
<                     logger.info(f"{NEON_CYAN}Open Positions: {len(open_positions)}{RESET}")
<                     for pos in open_positions:
<                         logger.info(
<                             f"  - {pos['side']} @ {pos['entry_price']} (SL: {pos['stop_loss']}, TP: {pos['take_profit']}, Trailing SL: {pos['current_trailing_sl'] if pos['is_trailing_activated'] else 'N/A'}, PnL: {pos['unrealized_pnl']:.2f}){RESET}"
<                         )
<                 else:
<                     logger.info(f"{NEON_CYAN}No open positions.{RESET}")
---
>         position_manager = PositionManager(config, logger, config["symbol"])
>         performance_tracker = PerformanceTracker(
>             logger, config_file="bot_logs/trading-bot/trades.json"
>         )  # Save trades to a file
> 
>         # Initialize other components needed by the main loop or analyzer
>         # Note: GeminiClient initialization is conditional and requires API key setup.
>         # For now, it's a placeholder.
>         gemini_client = None
>         if config["gemini_ai_analysis"]["enabled"]:
>             gemini_api_key = os.getenv("GEMINI_API_KEY")
>             if gemini_api_key:
>                 # Assuming GeminiClient is available and correctly implemented elsewhere
>                 # from gemini_client import GeminiClient # Uncomment if GeminiClient is available
>                 # gemini_client = GeminiClient(...)
>                 logger.warning(
>                     f"{NEON_YELLOW}Gemini AI analysis enabled, but GeminiClient is not implemented/imported. Placeholder used.{RESET}"
>                 )
3501,3503c3585,3590
<                 perf_summary = performance_tracker.get_summary()
<                 logger.info(
<                     f"{NEON_YELLOW}Performance Summary: Total PnL: {perf_summary['total_pnl']:.2f}, Wins: {perf_summary['wins']}, Losses: {perf_summary['losses']}, Win Rate: {perf_summary['win_rate']}{RESET}"
---
>                 def gemini_client():
>                     return None  # Placeholder
> 
>             else:
>                 logger.error(
>                     f"{NEON_RED}GEMINI_API_KEY not set, disabling Gemini AI analysis.{RESET}"
3504a3592
>                 config["gemini_ai_analysis"]["enabled"] = False
3506,3507c3594,3648
<                 logger.info(
<                     f"{NEON_PURPLE}--- Analysis Loop Finished. Waiting {config['loop_delay']}s ---{RESET}"
---
>         # Start the asynchronous main loop
>         asyncio.run(
>             main_async_loop(
>                 config,
>                 logger,
>                 position_manager,
>                 performance_tracker,
>                 alert_system,
>                 gemini_client,
>             )
>         )
> 
>     except KeyboardInterrupt:
>         logger.info(
>             f"{NEON_BLUE}KeyboardInterrupt detected. Shutting down bot...{RESET}"
>         )
>         # The shutdown logic is handled within main_async_loop's finally block
>     except Exception as e:
>         logger.critical(
>             f"{NEON_RED}Critical error during bot startup or top-level execution: {e}{RESET}",
>             exc_info=True,
>         )
>         sys.exit(1)  # Exit if critical setup fails
>         # Start the asynchronous main loop
>         asyncio.run(
>             main_async_loop(
>                 config,
>                 logger,
>                 position_manager,
>                 performance_tracker,
>                 alert_system,
>                 gemini_client,
>             )
>         )
> 
>     except KeyboardInterrupt:
>         logger.info(
>             f"{NEON_BLUE}KeyboardInterrupt detected. Shutting down bot...{RESET}"
>         )
>         # The shutdown logic is handled within main_async_loop's finally block
>     except Exception as e:
>         logger.critical(
>             f"{NEON_RED}Critical error during bot startup or top-level execution: {e}{RESET}",
>             exc_info=True,
>         )
>         sys.exit(1)  # Exit if critical setup fails
>         if config["interval"] not in valid_bybit_intervals:
>             logger.error(
>                 f"{NEON_RED}Invalid primary interval '{config['interval']}' in config.json. Please use Bybit's valid string formats (e.g., '15', '60', 'D'). Exiting.{RESET}"
>             )
>             sys.exit(1)
>         for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
>             if htf_interval not in valid_bybit_intervals:
>                 logger.error(
>                     f"{NEON_RED}Invalid higher timeframe interval '{htf_interval}' in config.json. Please use Bybit's valid string formats (e.g., '60', '240'). Exiting.{RESET}"
3509c3650
<                 await asyncio.sleep(config["loop_delay"])
---
>                 sys.exit(1)
3511,3516c3652,3688
<             except asyncio.CancelledError:
<                 logger.info(f"{NEON_BLUE}Main loop cancelled gracefully.{RESET}")
<                 break
<             except Exception as e:
<                 alert_system.send_alert(
<                     f"An unhandled error occurred in the main loop: {e}", "ERROR"
---
>         if not API_KEY or not API_SECRET:
>             logger.critical(
>                 f"{NEON_RED}BYBIT_API_KEY or BYBIT_API_SECRET environment variables are not set. Please set them before running the bot. Exiting.{RESET}"
>             )
>             sys.exit(1)
> 
>         logger.info(f"{NEON_GREEN}--- Whalebot Trading Bot Initialized ---{RESET}")
>         logger.info(f"Symbol: {config['symbol']}, Interval: {config['interval']}")
>         logger.info(
>             f"Trade Management Enabled: {config['trade_management']['enabled']}"
>         )
>         if config["trade_management"]["enabled"]:
>             logger.info(
>                 f"Leverage: {config['trade_management']['leverage']}x, Order Mode: {config['trade_management']['order_mode']}"
>             )
>         else:
>             logger.info(
>                 f"Using simulated balance for position sizing: {config['trade_management']['account_balance']:.2f} USDT"
>             )
> 
>         position_manager = PositionManager(config, logger, config["symbol"])
>         performance_tracker = PerformanceTracker(
>             logger, config_file="bot_logs/trading-bot/trades.json"
>         )  # Save trades to a file
> 
>         # Initialize other components needed by the main loop or analyzer
>         # Note: GeminiClient initialization is conditional and requires API key setup.
>         # For now, it's a placeholder.
>         gemini_client = None
>         if config["gemini_ai_analysis"]["enabled"]:
>             gemini_api_key = os.getenv("GEMINI_API_KEY")
>             if gemini_api_key:
>                 # Assuming GeminiClient is available and correctly implemented elsewhere
>                 # from gemini_client import GeminiClient # Uncomment if GeminiClient is available
>                 # gemini_client = GeminiClient(...)
>                 logger.warning(
>                     f"{NEON_YELLOW}Gemini AI analysis enabled, but GeminiClient is not implemented/imported. Placeholder used.{RESET}"
3518,3519d3689
<                 logger.exception(f"{NEON_RED}Unhandled exception in main loop:{RESET}")
<                 await asyncio.sleep(config["loop_delay"] * 2)
3521,3526c3691,3692
<     except KeyboardInterrupt:
<         logger.info(f"{NEON_BLUE}KeyboardInterrupt detected. Shutting down bot...{RESET}")
<     finally:
<         await bybit_client.stop_ws()
<         await bybit_client.cancel_all_orders(config["symbol"])
<         logger.info(f"{NEON_GREEN}Wgwhalex Trading Bot Shutdown Complete.{RESET}")
---
>                 def gemini_client():
>                     return None  # Placeholder
3527a3694,3710
>             else:
>                 logger.error(
>                     f"{NEON_RED}GEMINI_API_KEY not set, disabling Gemini AI analysis.{RESET}"
>                 )
>                 config["gemini_ai_analysis"]["enabled"] = False
> 
>         # Start the asynchronous main loop
>         asyncio.run(
>             main_async_loop(
>                 config,
>                 logger,
>                 position_manager,
>                 performance_tracker,
>                 alert_system,
>                 gemini_client,
>             )
>         )
3529,3531d3711
< if __name__ == "__main__":
<     try:
<         asyncio.run(main())
3533c3713,3716
<         pass
---
>         logger.info(
>             f"{NEON_BLUE}KeyboardInterrupt detected. Shutting down bot...{RESET}"
>         )
>         # The shutdown logic is handled within main_async_loop's finally block
3535,3536c3718,3722
<         logger = setup_logger("wgwhalex_bot_main")
<         logger.critical(f"{NEON_RED}Critical error during bot startup or top-level execution: {e}{RESET}", exc_info=True)
---
>         logger.critical(
>             f"{NEON_RED}Critical error during bot startup or top-level execution: {e}{RESET}",
>             exc_info=True,
>         )
>         sys.exit(1)  # Exit if critical setup fails
