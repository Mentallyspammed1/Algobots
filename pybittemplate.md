import os
import asyncio
import json
import logging
import time
import uuid # For generating unique client order IDs
import random # For SkipList random level generation
from typing import Dict, List, Any, Optional, Tuple, Generic, TypeVar
from dataclasses import dataclass
from contextlib import asynccontextmanager
from collections import defaultdict

# Import pybit clients
from pybit.unified_trading import HTTP, WebSocket

# --- Configuration ---
# Configure logging
logging.basicConfig(
    level=logging.INFO, # Adjust to DEBUG for more verbosity
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load API credentials from environment variables
# IMPORTANT: Never hardcode your API keys directly in the script!
API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')

# Trading Parameters
SYMBOL = 'BTCUSDT'              # The trading pair (e.g., 'BTCUSDT', 'ETHUSDT')
CATEGORY = 'linear'             # 'spot', 'linear', 'inverse', 'option'
LEVERAGE = 10                   # Desired leverage for derivatives (e.g., 5, 10, 25)
ORDER_SIZE = 0.001              # Quantity for each order in base currency (e.g., 0.001 BTC)
SPREAD_PERCENTAGE = 0.0005      # 0.05% spread for market making (e.g., 0.0005 for 0.05%)
MAX_POSITION_SIZE = 0.01        # Max allowed absolute position size for risk management
MAX_OPEN_ORDERS_PER_SIDE = 1    # Maximum number of active limit orders on one side (Buy/Sell)
ORDER_REPRICE_THRESHOLD_PCT = 0.0002 # Percentage price change to trigger order repricing
TESTNET = True                  # Set to False for mainnet trading

# WebSocket Reconnection and Retry Delays
RECONNECT_DELAY_SECONDS = 5     # Delay before attempting WebSocket reconnection
API_RETRY_DELAY_SECONDS = 3     # Delay before retrying failed HTTP API calls

# --- Advanced Orderbook Data Structures ---

# Type variables for generic data structures
KT = TypeVar("KT")
VT = TypeVar("VT")

@dataclass(slots=True)
class PriceLevel:
    """Price level with metadata, optimized for memory with slots."""
    price: float
    quantity: float
    timestamp: int
    order_count: int = 1 # Optional: tracks number of individual orders at this price

    def __lt__(self, other: 'PriceLevel') -> bool:
        return self.price < other.price

    def __eq__(self, other: 'PriceLevel') -> bool:
        # Using a small epsilon for float comparison
        return abs(self.price - other.price) < 1e-8

class OptimizedSkipList(Generic[KT, VT]):
    """
    Enhanced Skip List implementation with O(log n) insert/delete/search.
    Asynchronous operations are not directly supported by SkipList itself,
    but it's protected by an asyncio.Lock in the manager.
    """
    class Node(Generic[KT, VT]):
        def __init__(self, key: KT, value: VT, level: int):
            self.key = key
            self.value = value
            self.forward: List[Optional['OptimizedSkipList.Node']] = [None] * (level + 1)
            self.level = level

    def __init__(self, max_level: int = 16, p: float = 0.5):
        self.max_level = max_level
        self.p = p
        self.level = 0
        self.header = self.Node(None, None, max_level)
        self._size = 0

    def _random_level(self) -> int:
        level = 0
        while level < self.max_level and random.random() < self.p:
            level += 1
        return level

    def insert(self, key: KT, value: VT) -> None:
        update = [None] * (self.max_level + 1)
        current = self.header
        for i in range(self.level, -1, -1):
            while (current.forward[i] and
                   current.forward[i].key is not None and
                   current.forward[i].key < key):
                current = current.forward[i]
            update[i] = current
        current = current.forward[0]

        if current and current.key == key:
            current.value = value
            return

        new_level = self._random_level()
        if new_level > self.level:
            for i in range(self.level + 1, new_level + 1):
                update[i] = self.header
            self.level = new_level

        new_node = self.Node(key, value, new_level)
        for i in range(new_level + 1):
            new_node.forward[i] = update[i].forward[i]
            update[i].forward[i] = new_node
        self._size += 1

    def delete(self, key: KT) -> bool:
        update = [None] * (self.max_level + 1)
        current = self.header
        for i in range(self.level, -1, -1):
            while (current.forward[i] and
                   current.forward[i].key is not None and
                   current.forward[i].key < key):
                current = current.forward[i]
            update[i] = current
        current = current.forward[0]
        if not current or current.key != key:
            return False

        for i in range(self.level + 1):
            if update[i].forward[i] != current:
                break
            update[i].forward[i] = current.forward[i]
        while self.level > 0 and not self.header.forward[self.level]:
            self.level -= 1
        self._size -= 1
        return True

    def get_sorted_items(self, reverse: bool = False) -> List[Tuple[KT, VT]]:
        items = []
        current = self.header.forward[0]
        while current:
            if current.key is not None:
                items.append((current.key, current.value))
            current = current.forward[0]
        return list(reversed(items)) if reverse else items

    def peek_top(self, reverse: bool = False) -> Optional[VT]:
        items = self.get_sorted_items(reverse=reverse)
        return items[0][1] if items else None

    @property
    def size(self) -> int:
        return self._size

class EnhancedHeap:
    """
    Enhanced heap implementation (Min-Heap or Max-Heap) with position tracking
    for O(log n) update and removal operations.
    Protected by an asyncio.Lock in the manager.
    """
    def __init__(self, is_max_heap: bool = True):
        self.heap: List[PriceLevel] = []
        self.is_max_heap = is_max_heap
        self.position_map: Dict[float, int] = {} # Maps price to its index in the heap

    def _parent(self, i: int) -> int: return (i - 1) // 2
    def _left_child(self, i: int) -> int: return 2 * i + 1
    def _right_child(self, i: int) -> int: return 2 * i + 2

    def _compare(self, a: PriceLevel, b: PriceLevel) -> bool:
        if self.is_max_heap: return a.price > b.price
        return a.price < b.price

    def _swap(self, i: int, j: int) -> None:
        self.position_map[self.heap[i].price] = j
        self.position_map[self.heap[j].price] = i
        self.heap[i], self.heap[j] = self.heap[j], self.heap[i]

    def _heapify_up(self, i: int) -> None:
        while i > 0:
            parent = self._parent(i)
            if not self._compare(self.heap[i], self.heap[parent]): break
            self._swap(i, parent)
            i = parent

    def _heapify_down(self, i: int) -> None:
        while True:
            largest = i
            left = self._left_child(i)
            right = self._right_child(i)
            if left < len(self.heap) and self._compare(self.heap[left], self.heap[largest]): largest = left
            if right < len(self.heap) and self._compare(self.heap[right], self.heap[largest]): largest = right
            if largest == i: break
            self._swap(i, largest)
            i = largest

    def insert(self, price_level: PriceLevel) -> None:
        if price_level.price in self.position_map:
            idx = self.position_map[price_level.price]
            old_price = self.heap[idx].price
            self.heap[idx] = price_level
            self.position_map[price_level.price] = idx
            if abs(old_price - price_level.price) > 1e-8: # Price changed, unlikely for update, but robust
                 del self.position_map[old_price]
            self._heapify_up(idx)
            self._heapify_down(idx)
        else:
            self.heap.append(price_level)
            idx = len(self.heap) - 1
            self.position_map[price_level.price] = idx
            self._heapify_up(idx)

    def remove(self, price: float) -> bool:
        if price not in self.position_map: return False
        idx = self.position_map[price]
        del self.position_map[price]
        if idx == len(self.heap) - 1:
            self.heap.pop()
            return True
        last = self.heap.pop()
        self.heap[idx] = last
        self.position_map[last.price] = idx
        self._heapify_up(idx)
        self._heapify_down(idx)
        return True

    def peek_top(self) -> Optional[PriceLevel]:
        return self.heap[0] if self.heap else None
    
    @property
    def size(self) -> int:
        return len(self.heap)

class AdvancedOrderbookManager:
    """
    Manages the orderbook for a single symbol using either OptimizedSkipList or EnhancedHeap.
    Provides thread-safe (asyncio-safe) operations, snapshot/delta processing,
    and access to best bid/ask.
    """
    def __init__(self, symbol: str, use_skip_list: bool = True):
        self.symbol = symbol
        self.use_skip_list = use_skip_list
        self._lock = asyncio.Lock() # Asyncio-native lock for concurrency control
        
        # Initialize data structures for bids and asks
        if use_skip_list:
            logger.info(f"OrderbookManager for {symbol}: Using OptimizedSkipList.")
            self.bids_ds = OptimizedSkipList[float, PriceLevel]() # Bids (descending price logic handled by reverse in get_sorted_items)
            self.asks_ds = OptimizedSkipList[float, PriceLevel]() # Asks (ascending price)
        else:
            logger.info(f"OrderbookManager for {symbol}: Using EnhancedHeap.")
            self.bids_ds = EnhancedHeap(is_max_heap=True)  # Max-heap for bids (highest price on top)
            self.asks_ds = EnhancedHeap(is_max_heap=False) # Min-heap for asks (lowest price on top)
        
        self.last_update_id: int = 0 # To track WebSocket sequence

    @asynccontextmanager
    async def _lock_context(self):
        """Async context manager for acquiring and releasing the asyncio.Lock."""
        async with self._lock:
            yield

    async def _validate_price_quantity(self, price: float, quantity: float) -> bool:
        """Validates if price and quantity are non-negative and numerically valid."""
        if not (isinstance(price, (int, float)) and isinstance(quantity, (int, float))):
            logger.error(f"Invalid type for price or quantity for {self.symbol}. Price: {type(price)}, Qty: {type(quantity)}")
            return False
        if price < 0 or quantity < 0:
            logger.error(f"Negative price or quantity detected for {self.symbol}: price={price}, quantity={quantity}")
            return False
        return True

    async def update_snapshot(self, data: Dict[str, Any]) -> None:
        """Processes an initial orderbook snapshot."""
        async with self._lock_context():
            # Basic validation
            if not isinstance(data, dict) or 'b' not in data or 'a' not in data or 'u' not in data:
                logger.error(f"Invalid snapshot data format for {self.symbol}: {data}")
                return

            # Clear existing data structures
            if self.use_skip_list:
                self.bids_ds = OptimizedSkipList[float, PriceLevel]()
                self.asks_ds = OptimizedSkipList[float, PriceLevel]()
            else:
                self.bids_ds = EnhancedHeap(is_max_heap=True)
                self.asks_ds = EnhancedHeap(is_max_heap=False)

            # Process bids
            for price_str, qty_str in data.get('b', []):
                try:
                    price = float(price_str)
                    quantity = float(qty_str)
                    if await self._validate_price_quantity(price, quantity) and quantity > 0:
                        level = PriceLevel(price, quantity, int(time.time() * 1000))
                        self.bids_ds.insert(price, level)
                except (ValueError, TypeError) as e:
                    logger.error(f"Failed to parse bid in snapshot for {self.symbol}: {price_str}/{qty_str}, error={e}")

            # Process asks
            for price_str, qty_str in data.get('a', []):
                try:
                    price = float(price_str)
                    quantity = float(qty_str)
                    if await self._validate_price_quantity(price, quantity) and quantity > 0:
                        level = PriceLevel(price, quantity, int(time.time() * 1000))
                        self.asks_ds.insert(price, level)
                except (ValueError, TypeError) as e:
                    logger.error(f"Failed to parse ask in snapshot for {self.symbol}: {price_str}/{qty_str}, error={e}")
            
            self.last_update_id = data.get('u', 0)
            logger.info(f"Orderbook {self.symbol} snapshot updated. Last Update ID: {self.last_update_id}")

    async def update_delta(self, data: Dict[str, Any]) -> None:
        """Applies incremental updates (deltas) to the orderbook."""
        async with self._lock_context():
            # Basic validation
            if not isinstance(data, dict) or not ('b' in data or 'a' in data) or 'u' not in data:
                logger.error(f"Invalid delta data format for {self.symbol}: {data}")
                return

            current_update_id = data.get('u', 0)
            if current_update_id <= self.last_update_id:
                # Ignore outdated or duplicate updates
                logger.debug(f"Outdated OB update for {self.symbol}: current={current_update_id}, last={self.last_update_id}. Skipping.")
                return

            # If there's a significant gap, a resync might be necessary.
            # For simplicity, we just apply deltas sequentially after checking update_id.
            # In a production system, you might trigger a full orderbook resync if
            # current_update_id > self.last_update_id + 1.

            # Process bid deltas
            for price_str, qty_str in data.get('b', []):
                try:
                    price = float(price_str)
                    quantity = float(qty_str)
                    if not await self._validate_price_quantity(price, quantity): continue

                    if quantity == 0.0:
                        self.bids_ds.delete(price) if self.use_skip_list else self.bids_ds.remove(price)
                    else:
                        level = PriceLevel(price, quantity, int(time.time() * 1000))
                        self.bids_ds.insert(price, level)
                except (ValueError, TypeError) as e:
                    logger.error(f"Failed to parse bid delta for {self.symbol}: {price_str}/{qty_str}, error={e}")

            # Process ask deltas
            for price_str, qty_str in data.get('a', []):
                try:
                    price = float(price_str)
                    quantity = float(qty_str)
                    if not await self._validate_price_quantity(price, quantity): continue

                    if quantity == 0.0:
                        self.asks_ds.delete(price) if self.use_skip_list else self.asks_ds.remove(price)
                    else:
                        level = PriceLevel(price, quantity, int(time.time() * 1000))
                        self.asks_ds.insert(price, level)
                except (ValueError, TypeError) as e:
                    logger.error(f"Failed to parse ask delta for {self.symbol}: {price_str}/{qty_str}, error={e}")
            
            self.last_update_id = current_update_id
            logger.debug(f"Orderbook {self.symbol} delta applied. Last Update ID: {self.last_update_id}")

    async def get_best_bid_ask(self) -> Tuple[Optional[float], Optional[float]]:
        """Returns the current best bid and best ask prices."""
        async with self._lock_context():
            best_bid_level = self.bids_ds.peek_top(reverse=True) if self.use_skip_list else self.bids_ds.peek_top()
            best_ask_level = self.asks_ds.peek_top(reverse=False) if self.use_skip_list else self.asks_ds.peek_top()
            
            best_bid = best_bid_level.price if best_bid_level else None
            best_ask = best_ask_level.price if best_ask_level else None
            return best_bid, best_ask

    async def get_depth(self, depth: int) -> Tuple[List[PriceLevel], List[PriceLevel]]:
        """Retrieves the top N bids and asks."""
        async with self._lock_context():
            if self.use_skip_list:
                bids = [item[1] for item in self.bids_ds.get_sorted_items(reverse=True)[:depth]]
                asks = [item[1] for item in self.asks_ds.get_sorted_items()[:depth]]
            else: # EnhancedHeap - involves temporary extraction/re-insertion
                bids_list: List[PriceLevel] = []
                asks_list: List[PriceLevel] = []
                temp_bids_storage: List[PriceLevel] = []
                temp_asks_storage: List[PriceLevel] = []
                
                for _ in range(min(depth, self.bids_ds.size)):
                    level = self.bids_ds.peek_top() # Peek, then manually extract/re-insert
                    if level:
                        self.bids_ds.remove(level.price) # Remove
                        bids_list.append(level)
                        temp_bids_storage.append(level)
                for level in temp_bids_storage: # Re-insert
                    self.bids_ds.insert(level)
                
                for _ in range(min(depth, self.asks_ds.size)):
                    level = self.asks_ds.peek_top()
                    if level:
                        self.asks_ds.remove(level.price)
                        asks_list.append(level)
                        temp_asks_storage.append(level)
                for level in temp_asks_storage:
                    self.asks_ds.insert(level)
                
                bids = bids_list
                asks = asks_list
            return bids, asks

# --- Main Trading Bot Class ---
class BybitTradingBot:
    def __init__(self, symbol: str, category: str, leverage: int,
                 order_size: float, spread_percentage: float,
                 max_position_size: float, max_open_orders_per_side: int,
                 order_reprice_threshold_pct: float, testnet: bool):
        
        self.symbol = symbol
        self.category = category
        self.leverage = leverage
        self.order_size = order_size
        self.spread_percentage = spread_percentage
        self.max_position_size = max_position_size
        self.max_open_orders_per_side = max_open_orders_per_side
        self.order_reprice_threshold_pct = order_reprice_threshold_pct
        self.testnet = testnet

        # Validate API keys
        if not API_KEY or not API_SECRET:
            logger.critical("API_KEY or API_SECRET environment variables not set. Exiting.")
            raise ValueError("API credentials missing.")

        # Initialize pybit HTTP client
        self.http_session = HTTP(testnet=self.testnet, api_key=API_KEY, api_secret=API_SECRET)
        
        # Initialize pybit Public WebSocket client for market data
        self.ws_public = WebSocket(channel_type=self.category, testnet=self.testnet)
        
        # Initialize pybit Private WebSocket client for account/order updates
        self.ws_private = WebSocket(channel_type='private', testnet=self.testnet, api_key=API_KEY, api_secret=API_SECRET)

        self.orderbook_manager = AdvancedOrderbookManager(self.symbol, use_skip_list=True) # Use SkipList for orderbook
        
        # Internal state variables, updated via WebSockets
        self.is_running = True
        self.current_position_size: float = 0.0 # Absolute size (e.g., 0.005 for long or short)
        self.current_position_side: str = 'None' # 'Buy', 'Sell', or 'None'
        self.current_position_avg_price: float = 0.0
        self.wallet_balance: float = 0.0
        self.active_orders: Dict[str, Dict[str, Any]] = {} # {orderId: order_details}

        # Asyncio tasks for WebSocket listeners
        self.public_ws_task: Optional[asyncio.Task] = None
        self.private_ws_task: Optional[asyncio.Task] = None

        logger.info(f"Bot initialized for {self.symbol} ({self.category}, Leverage: {self.leverage}, Testnet: {self.testnet}).")

    async def _handle_public_ws_message(self, message: str):
        """Callback for public WebSocket messages (orderbook, ticker, trade)."""
        try:
            data = json.loads(message)
            topic = data.get('topic')

            if topic and 'orderbook' in topic:
                if data.get('type') == 'snapshot':
                    await self.orderbook_manager.update_snapshot(data['data'])
                elif data.get('type') == 'delta':
                    await self.orderbook_manager.update_delta(data['data'])
            elif topic and 'ticker' in topic:
                logger.debug(f"Ticker update: {data['data']}")
            elif topic and 'trade' in topic:
                logger.debug(f"Trade update: {data['data']}")
            else:
                logger.debug(f"Unhandled public WS message: {message}")
        except json.JSONDecodeError:
            logger.error(f"Failed to decode public WS message: {message}")
        except Exception as e:
            logger.error(f"Error processing public WS message: {e} | Message: {message[:100]}...", exc_info=True)

    async def _handle_private_ws_message(self, message: str):
        """Callback for private WebSocket messages (position, order, execution, wallet)."""
        try:
            data = json.loads(message)
            topic = data.get('topic')

            if topic == 'position':
                # Bybit's V5 position stream can send multiple entries for hedge mode.
                # In one-way mode, there should ideally be one entry per symbol.
                for pos_entry in data.get('data', []):
                    if pos_entry.get('symbol') == self.symbol:
                        self.current_position_size = float(pos_entry.get('size', 0))
                        self.current_position_avg_price = float(pos_entry.get('avgPrice', 0))
                        # Determine side based on size
                        if self.current_position_size > 0: self.current_position_side = 'Buy'
                        elif self.current_position_size < 0: self.current_position_side = 'Sell'
                        else: self.current_position_side = 'None'
                        logger.info(f"Position update for {self.symbol}: Side={self.current_position_side}, Size={abs(self.current_position_size):.4f}, AvgPrice={self.current_position_avg_price:.4f}")
                        break # Process only for our symbol
            elif topic == 'order':
                for order_entry in data.get('data', []):
                    if order_entry.get('symbol') == self.symbol:
                        order_id = order_entry.get('orderId')
                        order_status = order_entry.get('orderStatus')
                        if order_id:
                            if order_status in ['New', 'PartiallyFilled', 'Untriggered', 'Created']:
                                self.active_orders[order_id] = order_entry
                            elif order_status in ['Filled', 'Cancelled', 'Rejected']:
                                self.active_orders.pop(order_id, None) # Remove from active orders
                            logger.info(f"Order {order_id} ({order_entry.get('side')} {order_entry.get('qty')} @ {order_entry.get('price')}) status: {order_status}")
            elif topic == 'execution':
                logger.debug(f"Execution update: {data['data']}")
            elif topic == 'wallet':
                for wallet_entry in data.get('data', []):
                    # Assuming we are interested in total equity of the unified account
                    if wallet_entry.get('accountType') == 'UNIFIED':
                        self.wallet_balance = float(wallet_entry.get('totalEquity', 0))
                        logger.info(f"Wallet balance update: {self.wallet_balance:.2f}")
                        break
            else:
                logger.debug(f"Unhandled private WS message: {message}")
        except json.JSONDecodeError:
            logger.error(f"Failed to decode private WS message: {message}")
        except Exception as e:
            logger.error(f"Error processing private WS message: {e} | Message: {message[:100]}...", exc_info=True)

    async def _start_websocket_listener(self, ws_client: WebSocket, handler_func):
        """Starts a WebSocket listener for a given pybit client, handling reconnections."""
        while self.is_running:
            try:
                # pybit WebSocket client automatically handles connection and reconnection.
                # We just need to ensure the subscriptions are set up after a successful connection.
                logger.info(f"Attempting to connect and subscribe to {ws_client.channel_type} WebSocket...")
                
                if ws_client.channel_type == 'private':
                    ws_client.position_stream(callback=handler_func)
                    ws_client.order_stream(callback=handler_func)
                    ws_client.execution_stream(callback=handler_func)
                    ws_client.wallet_stream(callback=handler_func)
                else: # Public streams
                    ws_client.orderbook_stream(depth=25, symbol=self.symbol, callback=handler_func)
                    ws_client.ticker_stream(symbol=self.symbol, callback=handler_func)
                    ws_client.trade_stream(symbol=self.symbol, callback=handler_func)
                
                # Keep the connection alive by waiting as long as the bot is running and WS is connected
                while self.is_running and ws_client.is_connected():
                    await asyncio.sleep(1) # Yield control to the event loop
                
                logger.warning(f"{ws_client.channel_type} WebSocket disconnected or connection lost. Attempting reconnect in {RECONNECT_DELAY_SECONDS}s.")
                await asyncio.sleep(RECONNECT_DELAY_SECONDS)

            except Exception as e:
                logger.error(f"Error in {ws_client.channel_type} WebSocket listener: {e}", exc_info=True)
                await asyncio.sleep(RECONNECT_DELAY_SECONDS) # Wait before retrying

    async def setup_initial_state(self):
        """Performs initial setup, fetches account info, and sets leverage."""
        logger.info("Starting initial bot setup...")
        retries = 3
        for i in range(retries):
            try:
                # 1. Set Leverage
                response = self.http_session.set_leverage(
                    category=self.category, symbol=self.symbol,
                    buyLeverage=str(self.leverage), sellLeverage=str(self.leverage)
                )
                if response['retCode'] == 0:
                    logger.info(f"Leverage set to {self.leverage} for {self.symbol}.")
                else:
                    logger.error(f"Failed to set leverage: {response['retMsg']} (Code: {response['retCode']}). Retrying {i+1}/{retries}...")
                    await asyncio.sleep(API_RETRY_DELAY_SECONDS)
                    continue

                # 2. Get Wallet Balance
                wallet_resp = self.http_session.get_wallet_balance(accountType='UNIFIED')
                if wallet_resp['retCode'] == 0 and wallet_resp['result']['list']:
                    self.wallet_balance = float(wallet_resp['result']['list'][0]['totalEquity'])
                    logger.info(f"Initial Wallet Balance: {self.wallet_balance:.2f}")
                else:
                    logger.error(f"Failed to get wallet balance: {wallet_resp['retMsg']}. Retrying {i+1}/{retries}...")
                    await asyncio.sleep(API_RETRY_DELAY_SECONDS)
                    continue

                # 3. Get Current Position
                position_resp = self.http_session.get_positions(category=self.category, symbol=self.symbol)
                if position_resp['retCode'] == 0 and position_resp['result']['list']:
                    pos_data = position_resp['result']['list'][0]
                    self.current_position_size = float(pos_data.get('size', 0))
                    self.current_position_avg_price = float(pos_data.get('avgPrice', 0))
                    if self.current_position_size > 0: self.current_position_side = 'Buy'
                    elif self.current_position_size < 0: self.current_position_side = 'Sell'
                    else: self.current_position_side = 'None'
                    logger.info(f"Initial Position: Side={self.current_position_side}, Size={abs(self.current_position_size):.4f}, AvgPrice={self.current_position_avg_price:.4f}")
                else:
                    logger.info(f"No initial position found for {self.symbol}.")
                
                # 4. Get Open Orders
                open_orders_resp = self.http_session.get_open_orders(category=self.category, symbol=self.symbol)
                if open_orders_resp['retCode'] == 0 and open_orders_resp['result']['list']:
                    for order in open_orders_resp['result']['list']:
                        self.active_orders[order['orderId']] = order
                    logger.info(f"Found {len(self.active_orders)} active orders on startup.")
                else:
                    logger.info("No initial active orders found.")

                logger.info("Bot initial setup complete.")
                return # Setup successful

            except Exception as e:
                logger.critical(f"Critical error during initial setup (Attempt {i+1}/{retries}): {e}", exc_info=True)
                if i < retries - 1:
                    await asyncio.sleep(API_RETRY_DELAY_SECONDS * (i + 1)) # Exponential backoff
        
        logger.critical("Initial setup failed after multiple retries. Shutting down bot.")
        self.is_running = False # Stop the bot if setup fails completely

    async def place_order(self, side: str, qty: float, price: float, order_type: str = 'Limit', client_order_id: Optional[str] = None) -> Optional[str]:
        """Places a new order with retry mechanism."""
        if not client_order_id:
            client_order_id = f"bot-{uuid.uuid4()}" # Generate unique ID

        retries = 3
        for i in range(retries):
            try:
                order_params = {
                    "category": self.category, "symbol": self.symbol, "side": side,
                    "orderType": order_type, "qty": str(qty), "price": str(price),
                    "timeInForce": "GTC", "orderLinkId": client_order_id
                }
                response = self.http_session.place_order(**order_params)
                if response['retCode'] == 0:
                    order_id = response['result']['orderId']
                    logger.info(f"Placed {side} {order_type} order (ID: {order_id}, ClientID: {client_order_id}) for {qty:.4f} @ {price:.4f}.")
                    return order_id
                elif response['retCode'] == 10001: # Duplicate orderLinkId, likely a race condition if order was placed but not seen
                    logger.warning(f"Order {client_order_id} already exists or duplicate detected. Checking existing orders.")
                    # A more robust system would query active orders here to confirm.
                    return None # Indicate order was not placed *by this call* but might exist
                else:
                    logger.error(f"Failed to place order {client_order_id}: {response['retMsg']} (Code: {response['retCode']}). Retrying {i+1}/{retries}...")
                    await asyncio.sleep(API_RETRY_DELAY_SECONDS)
            except Exception as e:
                logger.error(f"Error placing order {client_order_id}: {e}. Retrying {i+1}/{retries}...", exc_info=True)
                await asyncio.sleep(API_RETRY_DELAY_SECONDS)
        logger.critical(f"Failed to place order {client_order_id} after multiple retries.")
        return None

    async def cancel_order(self, order_id: str) -> bool:
        """Cancels an existing order by its order ID with retry mechanism."""
        retries = 3
        for i in range(retries):
            try:
                response = self.http_session.cancel_order(category=self.category, symbol=self.symbol, orderId=order_id)
                if response['retCode'] == 0:
                    logger.info(f"Cancelled order {order_id}.")
                    return True
                elif response['retCode'] == 110001: # Order already cancelled/filled
                    logger.warning(f"Order {order_id} already in final state (cancelled/filled).")
                    self.active_orders.pop(order_id, None)
                    return True
                else:
                    logger.error(f"Failed to cancel order {order_id}: {response['retMsg']} (Code: {response['retCode']}). Retrying {i+1}/{retries}...")
                    await asyncio.sleep(API_RETRY_DELAY_SECONDS)
            except Exception as e:
                logger.error(f"Error cancelling order {order_id}: {e}. Retrying {i+1}/{retries}...", exc_info=True)
                await asyncio.sleep(API_RETRY_DELAY_SECONDS)
        logger.critical(f"Failed to cancel order {order_id} after multiple retries.")
        return False

    async def cancel_all_orders(self) -> int:
        """Cancels all active orders for the symbol with retry mechanism."""
        retries = 3
        for i in range(retries):
            try:
                response = self.http_session.cancel_all_orders(category=self.category, symbol=self.symbol)
                if response['retCode'] == 0:
                    cancelled_count = len(response['result']['list'])
                    logger.info(f"Cancelled {cancelled_count} all orders for {self.symbol}.")
                    self.active_orders.clear() # Clear local state immediately for fast response
                    return cancelled_count
                else:
                    logger.error(f"Failed to cancel all orders: {response['retMsg']} (Code: {response['retCode']}). Retrying {i+1}/{retries}...")
                    await asyncio.sleep(API_RETRY_DELAY_SECONDS)
            except Exception as e:
                logger.error(f"Error cancelling all orders: {e}. Retrying {i+1}/{retries}...", exc_info=True)
                await asyncio.sleep(API_RETRY_DELAY_SECONDS)
        logger.critical("Failed to cancel all orders after multiple retries.")
        return 0
    
    async def _get_total_active_orders_qty(self, side: str) -> float:
        """Calculates total quantity of active orders for a given side."""
        total_qty = 0.0
        for order in self.active_orders.values():
            if order.get('side') == side and order.get('symbol') == self.symbol:
                total_qty += float(order.get('qty', 0))
        return total_qty

    async def trading_logic(self):
        """
        Implement your core trading strategy here.
        This example implements a simple market making strategy with basic repricing.
        """
        best_bid, best_ask = await self.orderbook_manager.get_best_bid_ask()

        if best_bid is None or best_ask is None:
            logger.warning("Orderbook not fully populated yet (best bid/ask missing). Waiting...")
            await asyncio.sleep(1) # Wait longer if orderbook is empty
            return

        # Calculate target bid and ask prices based on desired spread
        target_bid_price = best_bid * (1 - self.spread_percentage)
        target_ask_price = best_ask * (1 + self.spread_percentage)
        
        # Ensure target prices maintain a valid spread (target_ask_price > target_bid_price)
        if target_bid_price >= target_ask_price:
            logger.warning(f"Calculated target prices overlap or are too close for {self.symbol}. Best Bid:{best_bid:.4f}, Best Ask:{best_ask:.4f}. Adjusting to minimum spread.")
            # Fallback to a minimal viable spread if strategy leads to crossing prices
            target_bid_price = best_bid * (1 - self.spread_percentage / 2)
            target_ask_price = best_ask * (1 + self.spread_percentage / 2)
            if target_bid_price >= target_ask_price: # Last resort if it still crosses, slightly widen
                 target_ask_price = target_bid_price * (1 + 0.0001) # Smallest possible increment

        # Get current active orders for specific side
        current_buy_orders_qty = await self._get_total_active_orders_qty('Buy')
        current_sell_orders_qty = await self._get_total_active_orders_qty('Sell')

        # --- Risk Management: Check Max Position Size ---
        # Don't place new buy orders if we're already too long or at max position
        can_place_buy = (self.current_position_size < self.max_position_size and 
                         current_buy_orders_qty < self.max_open_orders_per_side * self.order_size) # Check against quantity of existing orders
        # Don't place new sell orders if we're already too short or at max position
        can_place_sell = (abs(self.current_position_size) < self.max_position_size and 
                          current_sell_orders_qty < self.max_open_orders_per_side * self.order_size) # Check against quantity of existing orders

        # --- Manage Buy Orders ---
        existing_buy_orders = [o for o in self.active_orders.values() if o.get('side') == 'Buy' and o.get('symbol') == self.symbol]
        
        if existing_buy_orders:
            # Repricing logic for existing buy orders
            for order_id, order_details in existing_buy_orders:
                existing_price = float(order_details.get('price'))
                if abs(existing_price - target_bid_price) / target_bid_price > self.order_reprice_threshold_pct:
                    logger.info(f"Repricing Buy order {order_id}: {existing_price:.4f} -> {target_bid_price:.4f}")
                    await self.cancel_order(order_id)
                    # Give time for cancellation to propagate before placing new order
                    await asyncio.sleep(0.1) 
                    if can_place_buy:
                        await self.place_order(side='Buy', qty=self.order_size, price=target_bid_price)
                    break # Process one order per cycle to avoid API rate limits
        elif can_place_buy:
            # Place new buy order
            logger.info(f"Placing new Buy order for {self.order_size:.4f} @ {target_bid_price:.4f}")
            await self.place_order(side='Buy', qty=self.order_size, price=target_bid_price)


        # --- Manage Sell Orders ---
        existing_sell_orders = [o for o in self.active_orders.values() if o.get('side') == 'Sell' and o.get('symbol') == self.symbol]
        
        if existing_sell_orders:
            # Repricing logic for existing sell orders
            for order_id, order_details in existing_sell_orders:
                existing_price = float(order_details.get('price'))
                if abs(existing_price - target_ask_price) / target_ask_price > self.order_reprice_threshold_pct:
                    logger.info(f"Repricing Sell order {order_id}: {existing_price:.4f} -> {target_ask_price:.4f}")
                    await self.cancel_order(order_id)
                    # Give time for cancellation to propagate before placing new order
                    await asyncio.sleep(0.1) 
                    if can_place_sell:
                        await self.place_order(side='Sell', qty=self.order_size, price=target_ask_price)
                    break # Process one order per cycle to avoid API rate limits
        elif can_place_sell:
            # Place new sell order
            logger.info(f"Placing new Sell order for {self.order_size:.4f} @ {target_ask_price:.4f}")
            await self.place_order(side='Sell', qty=self.order_size, price=target_ask_price)

        # --- Position Rebalancing (Optional) ---
        # If actual position exceeds allowed max, consider placing a market order to reduce
        if abs(self.current_position_size) > self.max_position_size + self.order_size: # Add a buffer
            logger.warning(f"Position size ({abs(self.current_position_size):.4f}) for {self.symbol} exceeds MAX_POSITION_SIZE. Attempting to reduce.")
            rebalance_qty = abs(self.current_position_size) - self.max_position_size
            if rebalance_qty > 0:
                if self.current_position_side == 'Buy': # Long position, sell to reduce
                    logger.info(f"Rebalancing: Placing Market Sell order for {rebalance_qty:.4f}")
                    await self.place_order(side='Sell', qty=rebalance_qty, price=best_bid, order_type='Market')
                elif self.current_position_side == 'Sell': # Short position, buy to reduce
                    logger.info(f"Rebalancing: Placing Market Buy order for {rebalance_qty:.4f}")
                    await self.place_order(side='Buy', qty=rebalance_qty, price=best_ask, order_type='Market')
        
        await asyncio.sleep(0.5) # Control the frequency of trading logic execution

    async def start(self):
        """Starts the bot's main loop and WebSocket listeners."""
        await self.setup_initial_state()

        if not self.is_running:
            logger.critical("Bot setup failed. Exiting.")
            return

        # Start WebSocket listeners concurrently
        self.public_ws_task = asyncio.create_task(self._start_websocket_listener(self.ws_public, self._handle_public_ws_message))
        self.private_ws_task = asyncio.create_task(self._start_websocket_listener(self.ws_private, self._handle_private_ws_message))

        logger.info("Bot main trading loop started.")
        while self.is_running:
            try:
                await self.trading_logic()
            except asyncio.CancelledError:
                logger.info("Trading logic task cancelled gracefully.")
                break
            except Exception as e:
                logger.error(f"Error in main trading loop: {e}", exc_info=True)
                await asyncio.sleep(API_RETRY_DELAY_SECONDS) # Wait before trying again

        await self.shutdown()

    async def shutdown(self):
        """Gracefully shuts down the bot, cancelling orders and closing connections."""
        logger.info("Shutting down bot...")
        self.is_running = False # Signal all loops to stop

        # Cancel all active orders
        if self.active_orders:
            logger.info(f"Cancelling {len(self.active_orders)} active orders...")
            await self.cancel_all_orders()
            await asyncio.sleep(2) # Give some time for cancellations to propagate

        # Cancel WebSocket tasks
        if self.public_ws_task and not self.public_ws_task.done():
            self.public_ws_task.cancel()
            try: await self.public_ws_task
            except asyncio.CancelledError: pass
        
        if self.private_ws_task and not self.private_ws_task.done():
            self.private_ws_task.cancel()
            try: await self.private_ws_task
            except asyncio.CancelledError: pass

        # Close pybit WebSocket connections explicitly (pybit also handles this on task cancellation)
        if self.ws_public.is_connected():
            await self.ws_public.close()
        if self.ws_private.is_connected():
            await self.ws_private.close()
        
        logger.info("Bot shutdown complete.")

# --- Main Execution Block ---
if __name__ == "__main__":
    # Ensure API_KEY and API_SECRET are set as environment variables
    # Example (for testing, run these in your terminal before starting script):
    # export BYBIT_API_KEY="YOUR_API_KEY"
    # export BYBIT_API_SECRET="YOUR_API_SECRET"

    if not API_KEY or not API_SECRET:
        logger.critical("BYBIT_API_KEY or BYBIT_API_SECRET environment variables are NOT set. Please set them before running the bot.")
        exit(1)

    bot = BybitTradingBot(
        symbol=SYMBOL,
        category=CATEGORY,
        leverage=LEVERAGE,
        order_size=ORDER_SIZE,
        spread_percentage=SPREAD_PERCENTAGE,
        max_position_size=MAX_POSITION_SIZE,
        max_open_orders_per_side=MAX_OPEN_ORDERS_PER_SIDE,
        order_reprice_threshold_pct=ORDER_REPRICE_THRESHOLD_PCT,
        testnet=TESTNET
    )

    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt detected. Stopping bot gracefully...")
        # asyncio.run(bot.shutdown()) # shutdown is called within start() or by catching CancelledError
    except Exception as e:
        logger.critical(f"An unhandled exception occurred during bot execution: {e}", exc_info=True)
        # asyncio.run(bot.shutdown()) # shutdown is called within start()
