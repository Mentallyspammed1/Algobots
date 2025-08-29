This updated Bybit trading bot template incorporates a more robust AdvancedOrderbookManager (using Skip Lists or Enhanced Heaps), enhanced error handling, more explicit risk management, and consistent asyncio patterns throughout. It's designed to be a high-performance, resilient, and extensible foundation for sophisticated trading strategies.Bybit Trading Bot Template - Enhanced Version (Ehlers Supertrend Cross Strategy) code Pythondownloadcontent_copyexpand_less    import os
import asyncio
import json
import logging
import time
import uuid # For generating unique client order IDs
import random # For SkipList random level generation
from collections import deque
from typing import Dict, List, Any, Optional, Tuple, Generic, TypeVar
from dataclasses import dataclass
from contextlib import asynccontextmanager

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

# Ehlers Supertrend Cross Strategy Parameters
KLINE_INTERVAL = '15'           # Kline interval (e.g., '1', '5', '15', '60', 'D')
KLINE_LIMIT = 200               # Number of historical klines to fetch (must be > ATR_PERIOD)
ATR_PERIOD = 14                 # Period for Average True Range calculation
SUPERTREND_MULTIPLIER = 3       # Multiplier for ATR in Supertrend calculation

# Risk Management & Order Parameters
MAX_POSITION_SIZE = 0.01        # Max allowed absolute position size for risk management
MAX_OPEN_ENTRY_ORDERS_PER_SIDE = 1 # Max number of entry limit orders on one side
ORDER_REPRICE_THRESHOLD_PCT = 0.0002 # Percentage price change to trigger order repricing (0.02% = 0.0002)

TESTNET = True                  # Set to False for mainnet trading

# WebSocket Reconnection and Retry Delays
RECONNECT_DELAY_SECONDS = 5     # Delay before attempting WebSocket reconnection
API_RETRY_DELAY_SECONDS = 3     # Delay before retrying failed HTTP API calls

# --- Data Structures for Technical Analysis ---

@dataclass(slots=True)
class KlineData:
    """Represents a single kline (candlestick) with essential data."""
    start_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float

# --- Technical Indicator Calculations ---
class TechnicalIndicators:
    """
    Provides methods for calculating common technical indicators.
    All calculations are done on lists of floats (highs, lows, closes).
    """

    @staticmethod
    def calculate_atr(highs: List[float], lows: List[float], closes: List[float], period: int) -> List[float]:
        """Calculates Average True Range (ATR)."""
        if len(highs) < period + 1: # Need previous close for TR
            return []

        trs = []
        for i in range(1, len(closes)):
            high_low = highs[i] - lows[i]
            high_prev_close = abs(highs[i] - closes[i-1])
            low_prev_close = abs(lows[i] - closes[i-1])
            tr = max(high_low, high_prev_close, low_prev_close)
            trs.append(tr)

        if not trs:
            return []
            
        # Initial ATR is the simple average of the first 'period' TRs
        atr_values = [sum(trs[:period]) / period]
        # Subsequent ATRs use Wilder's Smoothing method
        for i in range(period, len(trs)):
            atr_val = (atr_values[-1] * (period - 1) + trs[i]) / period
            atr_values.append(atr_val)
        
        # The returned list has `len(closes) - period` elements, corresponding to closes[period] onwards
        return atr_values

    @staticmethod
    def calculate_supertrend(
        highs: List[float], lows: List[float], closes: List[float],
        atr_period: int, multiplier: float
    ) -> Tuple[List[float], List[str]]:
        """
        Calculates Supertrend indicator values and direction.
        Returns (supertrend_line_values, supertrend_direction_signals).
        Direction signals are 'up' or 'down'.
        """
        # Ensure enough data for ATR calculation + one more candle for initial Supertrend
        if len(closes) < atr_period + 1:
            logger.warning(f"Not enough data for Supertrend calculation. Need {atr_period + 1} closes, got {len(closes)}.")
            return [], []

        atr_values = TechnicalIndicators.calculate_atr(highs, lows, closes, atr_period)
        if not atr_values:
            logger.warning("ATR calculation failed or returned empty. Cannot calculate Supertrend.")
            return [], []
            
        # Supertrend calculation starts after ATR_PERIOD
        # The offset aligns atr_values[0] with closes[atr_period]
        offset = atr_period 

        supertrend_line = [0.0] * len(closes)
        supertrend_direction = [''] * len(closes)
        
        # --- Initialization for the first valid candle (closes[offset]) ---
        hl2 = (highs[offset] + lows[offset]) / 2
        basic_upper_band = hl2 + multiplier * atr_values[0]
        basic_lower_band = hl2 - multiplier * atr_values[0]
        
        # Initial direction and Supertrend line based on first candle
        if closes[offset] > basic_upper_band:
            supertrend_direction[offset] = 'up'
            supertrend_line[offset] = basic_lower_band
        elif closes[offset] < basic_lower_band:
            supertrend_direction[offset] = 'down'
            supertrend_line[offset] = basic_upper_band
        else:
            # If price is within bands, default to 'up' or 'down' based on current close vs midpoint
            supertrend_direction[offset] = 'up' if closes[offset] >= hl2 else 'down'
            supertrend_line[offset] = basic_lower_band if supertrend_direction[offset] == 'up' else basic_upper_band

        # --- Iterative Calculation for subsequent candles ---
        for i in range(offset + 1, len(closes)):
            hl2 = (highs[i] + lows[i]) / 2
            current_atr = atr_values[i - offset] # Corresponding ATR value

            basic_upper_band = hl2 + multiplier * current_atr
            basic_lower_band = hl2 - multiplier * current_atr

            # Determine previous Supertrend line and direction
            prev_supertrend_line = supertrend_line[i-1]
            prev_supertrend_direction = supertrend_direction[i-1]

            # Current Final Upper/Lower Bands, adjusted by previous Supertrend
            current_final_upper_band = basic_upper_band
            current_final_lower_band = basic_lower_band

            if prev_supertrend_direction == 'up':
                current_final_upper_band = min(basic_upper_band, prev_supertrend_line)
                current_final_lower_band = basic_lower_band # Lower band simply tracks basic
            elif prev_supertrend_direction == 'down':
                current_final_lower_band = max(basic_lower_band, prev_supertrend_line)
                current_final_upper_band = basic_upper_band # Upper band simply tracks basic


            # --- Determine current Supertrend direction and line ---
            if closes[i] > current_final_upper_band: # Price breaks above upper band -> trend is UP
                supertrend_direction[i] = 'up'
                supertrend_line[i] = current_final_lower_band
            elif closes[i] < current_final_lower_band: # Price breaks below lower band -> trend is DOWN
                supertrend_direction[i] = 'down'
                supertrend_line[i] = current_final_upper_band
            else: # Price is within the bands or continues previous trend
                supertrend_direction[i] = prev_supertrend_direction
                if supertrend_direction[i] == 'up':
                    supertrend_line[i] = current_final_lower_band
                else: # 'down'
                    supertrend_line[i] = current_final_upper_band
        
        # Supertrend values only valid starting from `offset` index
        return supertrend_line[offset:], supertrend_direction[offset:]

# --- Advanced Orderbook Data Structures (from previous iteration) ---

KT = TypeVar("KT")
VT = TypeVar("VT")

@dataclass(slots=True)
class PriceLevel:
    """Price level with metadata, optimized for memory with slots."""
    price: float
    quantity: float
    timestamp: int
    order_count: int = 1

    def __lt__(self, other: 'PriceLevel') -> bool:
        return self.price < other.price

    def __eq__(self, other: 'PriceLevel') -> bool:
        return abs(self.price - other.price) < 1e-8

class OptimizedSkipList(Generic[KT, VT]):
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
    def __init__(self, is_max_heap: bool = True):
        self.heap: List[PriceLevel] = []
        self.is_max_heap = is_max_heap
        self.position_map: Dict[float, int] = {}

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
            if abs(old_price - price_level.price) > 1e-8:
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
    def __init__(self, symbol: str, use_skip_list: bool = True):
        self.symbol = symbol
        self.use_skip_list = use_skip_list
        self._lock = asyncio.Lock()
        
        if use_skip_list:
            self.bids_ds = OptimizedSkipList[float, PriceLevel]()
            self.asks_ds = OptimizedSkipList[float, PriceLevel]()
        else:
            self.bids_ds = EnhancedHeap(is_max_heap=True)
            self.asks_ds = EnhancedHeap(is_max_heap=False)
        
        self.last_update_id: int = 0

    @asynccontextmanager
    async def _lock_context(self):
        async with self._lock:
            yield

    async def _validate_price_quantity(self, price: float, quantity: float) -> bool:
        if not (isinstance(price, (int, float)) and isinstance(quantity, (int, float))):
            logger.error(f"Invalid type for price or quantity for {self.symbol}. Price: {type(price)}, Qty: {type(quantity)}")
            return False
        if price < 0 or quantity < 0:
            logger.error(f"Negative price or quantity detected for {self.symbol}: price={price}, quantity={quantity}")
            return False
        return True

    async def update_snapshot(self, data: Dict[str, Any]) -> None:
        async with self._lock_context():
            if not isinstance(data, dict) or 'b' not in data or 'a' not in data or 'u' not in data:
                logger.error(f"Invalid snapshot data format for {self.symbol}: {data}")
                return

            if self.use_skip_list:
                self.bids_ds = OptimizedSkipList[float, PriceLevel]()
                self.asks_ds = OptimizedSkipList[float, PriceLevel]()
            else:
                self.bids_ds = EnhancedHeap(is_max_heap=True)
                self.asks_ds = EnhancedHeap(is_max_heap=False)

            for price_str, qty_str in data.get('b', []):
                try:
                    price = float(price_str)
                    quantity = float(qty_str)
                    if await self._validate_price_quantity(price, quantity) and quantity > 0:
                        level = PriceLevel(price, quantity, int(time.time() * 1000))
                        self.bids_ds.insert(price, level)
                except (ValueError, TypeError) as e:
                    logger.error(f"Failed to parse bid in snapshot for {self.symbol}: {price_str}/{qty_str}, error={e}")

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
        async with self._lock_context():
            if not isinstance(data, dict) or not ('b' in data or 'a' in data) or 'u' not in data:
                logger.error(f"Invalid delta data format for {self.symbol}: {data}")
                return

            current_update_id = data.get('u', 0)
            if current_update_id <= self.last_update_id:
                logger.debug(f"Outdated OB update for {self.symbol}: current={current_update_id}, last={self.last_update_id}. Skipping.")
                return

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
        async with self._lock_context():
            best_bid_level = self.bids_ds.peek_top(reverse=True) if self.use_skip_list else self.bids_ds.peek_top()
            best_ask_level = self.asks_ds.peek_top(reverse=False) if self.use_skip_list else self.asks_ds.peek_top()
            
            best_bid = best_bid_level.price if best_bid_level else None
            best_ask = best_ask_level.price if best_ask_level else None
            return best_bid, best_ask

    async def get_depth(self, depth: int) -> Tuple[List[PriceLevel], List[PriceLevel]]:
        async with self._lock_context():
            if self.use_skip_list:
                bids = [item[1] for item in self.bids_ds.get_sorted_items(reverse=True)[:depth]]
                asks = [item[1] for item in self.asks_ds.get_sorted_items()[:depth]]
            else:
                bids_list: List[PriceLevel] = []
                asks_list: List[PriceLevel] = []
                temp_bids_storage: List[PriceLevel] = []
                temp_asks_storage: List[PriceLevel] = []
                
                for _ in range(min(depth, self.bids_ds.size)):
                    level = self.bids_ds.peek_top()
                    if level:
                        self.bids_ds.remove(level.price)
                        bids_list.append(level)
                        temp_bids_storage.append(level)
                for level in temp_bids_storage:
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
                 order_size: float,
                 kline_interval: str, kline_limit: int,
                 atr_period: int, supertrend_multiplier: float,
                 max_position_size: float, max_open_entry_orders_per_side: int,
                 order_reprice_threshold_pct: float, testnet: bool):
        
        self.symbol = symbol
        self.category = category
        self.leverage = leverage
        self.order_size = order_size
        self.kline_interval = kline_interval
        self.kline_limit = kline_limit
        self.atr_period = atr_period
        self.supertrend_multiplier = supertrend_multiplier
        self.max_position_size = max_position_size
        self.max_open_entry_orders_per_side = max_open_entry_orders_per_side
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

        self.orderbook_manager = AdvancedOrderbookManager(self.symbol, use_skip_list=True) # Using SkipList for orderbook
        
        # --- Bot State Variables ---
        self.is_running = True
        self.wallet_balance: float = 0.0
        
        self.current_position_size: float = 0.0 # Absolute size
        self.current_position_side: str = 'None' # 'Buy', 'Sell', or 'None'
        self.current_position_avg_price: float = 0.0

        self.active_orders: Dict[str, Dict[str, Any]] = {} # {orderId: order_details}
        
        # --- Supertrend Strategy State ---
        self.kline_data: deque[KlineData] = deque(maxlen=self.kline_limit)
        self.supertrend_line: Optional[float] = None
        self.supertrend_direction: Optional[str] = None # 'up' or 'down'
        self.last_trading_signal: Optional[str] = None # 'long', 'short' to track last acted signal

        # --- Asyncio Tasks ---
        self.public_ws_task: Optional[asyncio.Task] = None
        self.private_ws_task: Optional[asyncio.Task] = None
        self.kline_fetch_task: Optional[asyncio.Task] = None

        logger.info(f"Bot initialized for {self.symbol} ({self.category}, Leverage: {self.leverage}, Testnet: {self.testnet}).")
        logger.info(f"Supertrend Config: Interval={self.kline_interval}, ATR_Period={self.atr_period}, Multiplier={self.supertrend_multiplier}")

    # --- WebSocket Message Handlers (as per previous iteration) ---
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
            # Ticker/Trade updates can also be processed here if needed for other logic
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
                for pos_entry in data.get('data', []):
                    if pos_entry.get('symbol') == self.symbol:
                        self.current_position_size = float(pos_entry.get('size', 0))
                        self.current_position_avg_price = float(pos_entry.get('avgPrice', 0))
                        if self.current_position_size > 0: self.current_position_side = 'Buy'
                        elif self.current_position_size < 0: self.current_position_side = 'Sell'
                        else: self.current_position_side = 'None'
                        logger.info(f"Position update for {self.symbol}: Side={self.current_position_side}, Size={abs(self.current_position_size):.4f}, AvgPrice={self.current_position_avg_price:.4f}")
                        break
            elif topic == 'order':
                for order_entry in data.get('data', []):
                    if order_entry.get('symbol') == self.symbol:
                        order_id = order_entry.get('orderId')
                        order_status = order_entry.get('orderStatus')
                        if order_id:
                            if order_status in ['New', 'PartiallyFilled', 'Untriggered', 'Created']:
                                self.active_orders[order_id] = order_entry
                            elif order_status in ['Filled', 'Cancelled', 'Rejected']:
                                self.active_orders.pop(order_id, None)
                            logger.info(f"Order {order_id} ({order_entry.get('side')} {order_entry.get('qty')} @ {order_entry.get('price')}) status: {order_status}")
            elif topic == 'wallet':
                for wallet_entry in data.get('data', []):
                    if wallet_entry.get('accountType') == 'UNIFIED':
                        self.wallet_balance = float(wallet_entry.get('totalEquity', 0))
                        logger.info(f"Wallet balance update: {self.wallet_balance:.2f}")
                        break
        except json.JSONDecodeError:
            logger.error(f"Failed to decode private WS message: {message}")
        except Exception as e:
            logger.error(f"Error processing private WS message: {e} | Message: {message[:100]}...", exc_info=True)

    async def _start_websocket_listener(self, ws_client: WebSocket, handler_func):
        """Starts a WebSocket listener for a given pybit client, handling reconnections."""
        while self.is_running:
            try:
                logger.info(f"Attempting to connect and subscribe to {ws_client.channel_type} WebSocket...")
                if ws_client.channel_type == 'private':
                    ws_client.position_stream(callback=handler_func)
                    ws_client.order_stream(callback=handler_func)
                    ws_client.execution_stream(callback=handler_func)
                    ws_client.wallet_stream(callback=handler_func)
                else: # Public streams
                    ws_client.orderbook_stream(depth=25, symbol=self.symbol, callback=handler_func)
                    ws_client.ticker_stream(symbol=self.symbol, callback=handler_func)
                    # No kline stream here, we fetch klines via HTTP for historical data
                
                # Keep the connection alive by waiting as long as the bot is running and WS is connected
                while self.is_running and ws_client.is_connected():
                    await asyncio.sleep(1)
                
                logger.warning(f"{ws_client.channel_type} WebSocket disconnected or connection lost. Attempting reconnect in {RECONNECT_DELAY_SECONDS}s.")
                await asyncio.sleep(RECONNECT_DELAY_SECONDS)

            except Exception as e:
                logger.error(f"Error in {ws_client.channel_type} WebSocket listener: {e}", exc_info=True)
                await asyncio.sleep(RECONNECT_DELAY_SECONDS)

    async def _fetch_kline_data_loop(self):
        """Periodically fetches kline data and updates the bot's state."""
        logger.info(f"Starting kline data fetch loop for {self.symbol} at {self.kline_interval} interval.")
        # Determine appropriate polling frequency based on kline interval
        if self.kline_interval.isdigit():
            # For numerical intervals (e.g., '1', '5', '15', '60'), poll every few seconds
            poll_frequency_seconds = min(int(self.kline_interval) * 60 / 4, 30) # Poll 4 times per candle, max 30s
            if int(self.kline_interval) == 1: poll_frequency_seconds = 5 # More frequent for 1m candle
        else: # For 'D', 'W', 'M'
            poll_frequency_seconds = 300 # Poll every 5 minutes for longer intervals

        while self.is_running:
            try:
                response = self.http_session.get_kline(
                    category=self.category,
                    symbol=self.symbol,
                    interval=self.kline_interval,
                    limit=self.kline_limit
                )

                if response['retCode'] == 0 and response['result']['list']:
                    fetched_klines = [
                        KlineData(
                            start_time=int(k[0]),
                            open=float(k[1]),
                            high=float(k[2]),
                            low=float(k[3]),
                            close=float(k[4]),
                            volume=float(k[5]),
                            turnover=float(k[6])
                        ) for k in reversed(response['result']['list']) # Bybit returns newest first, reverse for chronological
                    ]

                    # Ensure we only add new unique klines and update the latest if it's still forming
                    if not self.kline_data:
                        self.kline_data.extend(fetched_klines)
                        logger.debug(f"Initial kline data fetched: {len(fetched_klines)} klines.")
                    else:
                        for new_kline in fetched_klines:
                            if new_kline.start_time > self.kline_data[-1].start_time:
                                self.kline_data.append(new_kline)
                                logger.debug(f"Added new kline: {new_kline.start_time} - Close: {new_kline.close}")
                            elif new_kline.start_time == self.kline_data[-1].start_time:
                                # Update the last candle if it's the same time (still forming)
                                if new_kline != self.kline_data[-1]: # Only update if data changed
                                    self.kline_data[-1] = new_kline
                                    logger.debug(f"Updated last kline: {new_kline.start_time} - Close: {new_kline.close}")
                    
                    # Trigger indicator calculation after data update
                    await self._calculate_and_update_indicators()
                else:
                    logger.error(f"Failed to fetch kline data: {response['retMsg']}")
                
                await asyncio.sleep(poll_frequency_seconds)

            except asyncio.CancelledError:
                logger.info("Kline fetch task cancelled.")
                break
            except Exception as e:
                logger.error(f"Error in kline fetch loop: {e}", exc_info=True)
                await asyncio.sleep(RECONNECT_DELAY_SECONDS)

    async def _calculate_and_update_indicators(self):
        """Calculates Supertrend and updates bot's indicator state."""
        # Need ATR_PERIOD + 1 klines to calculate first Supertrend value
        if len(self.kline_data) < self.atr_period + 1:
            logger.debug(f"Not enough kline data ({len(self.kline_data)}/{self.atr_period + 1}) for Supertrend calculation.")
            self.supertrend_line = None
            self.supertrend_direction = None
            return

        highs = [k.high for k in self.kline_data]
        lows = [k.low for k in self.kline_data]
        closes = [k.close for k in self.kline_data]

        supertrend_lines, supertrend_directions = TechnicalIndicators.calculate_supertrend(
            highs, lows, closes, self.atr_period, self.supertrend_multiplier
        )

        if supertrend_lines and supertrend_directions:
            self.supertrend_line = supertrend_lines[-1] # Most recent ST value
            self.supertrend_direction = supertrend_directions[-1] # Most recent ST direction
            logger.debug(f"Supertrend calculated: Line={self.supertrend_line:.4f}, Direction={self.supertrend_direction}")
        else:
            self.supertrend_line = None
            self.supertrend_direction = None
            logger.warning("Supertrend calculation failed or returned empty results after data update.")

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

    async def place_order(self, side: str, qty: float, price: Optional[float] = None, order_type: str = 'Limit', client_order_id: Optional[str] = None) -> Optional[str]:
        """Places a new order with retry mechanism."""
        if not client_order_id:
            client_order_id = f"bot-{uuid.uuid4()}"

        retries = 3
        for i in range(retries):
            try:
                order_params: Dict[str, Any] = {
                    "category": self.category, "symbol": self.symbol, "side": side,
                    "orderType": order_type, "qty": str(qty), "orderLinkId": client_order_id
                }
                if price is not None and order_type == 'Limit':
                    order_params["price"] = str(price)
                    order_params["timeInForce"] = "GTC" # Good Till Cancel

                response = self.http_session.place_order(**order_params)
                if response['retCode'] == 0:
                    order_id = response['result']['orderId']
                    logger.info(f"Placed {side} {order_type} order (ID: {order_id}, ClientID: {client_order_id}) for {qty:.4f} @ {price:.4f if price else 'Market'}.")
                    return order_id
                elif response['retCode'] == 10001: # Duplicate orderLinkId, likely a race condition if order was placed but not seen
                    logger.warning(f"Order {client_order_id} already exists or duplicate detected. Will verify via WS.")
                    # A more robust system would query active orders here to confirm if order was successfully placed.
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
                    self.active_orders.pop(order_id, None) # Optimistically remove from local state
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
    
    async def _get_total_active_entry_orders_qty(self, side: str) -> float:
        """Calculates total quantity of active ENTRY orders for a given side."""
        total_qty = 0.0
        for order in self.active_orders.values():
            # Assume all orders placed by the bot are entry orders for simplicity, or add a tag
            if order.get('side') == side and order.get('symbol') == self.symbol:
                total_qty += float(order.get('qty', 0))
        return total_qty

    async def trading_logic(self):
        """
        Implements the Supertrend Cross strategy.
        - Trades on Supertrend flip.
        - Closes existing position with a market order upon flip.
        - Opens a new position in the direction of the new trend with a limit order.
        - Manages limit orders for entry based on orderbook best bid/ask.
        """
        # Ensure sufficient kline data and indicator calculated
        if self.supertrend_line is None or len(self.kline_data) < self.atr_period + 1:
            logger.info("Waiting for Supertrend to be calculated with sufficient kline data...")
            await asyncio.sleep(1)
            return

        current_candle = self.kline_data[-1]
        
        # Get latest Supertrend values
        current_close = current_candle.close
        current_supertrend = self.supertrend_line
        current_supertrend_direction = self.supertrend_direction

        best_bid, best_ask = await self.orderbook_manager.get_best_bid_ask()

        if best_bid is None or best_ask is None:
            logger.warning("Orderbook not fully populated yet (best bid/ask missing). Waiting...")
            await asyncio.sleep(1)
            return

        trading_signal: Optional[str] = None # 'long' or 'short'

        # --- Generate Trading Signal ---
        if current_supertrend_direction == 'up':
            trading_signal = 'long'
        elif current_supertrend_direction == 'down':
            trading_signal = 'short'
        
        # Only act if the signal has changed or if we are not in a position and the signal indicates entry
        if trading_signal and trading_signal != self.last_trading_signal:
            logger.info(f"--- SUPERTREND FLIP DETECTED! NEW SIGNAL: {trading_signal.upper()} ---")
            
            # 1. Cancel all existing entry orders for flexibility
            if self.active_orders:
                logger.info("Cancelling all active entry orders due to signal flip.")
                await self.cancel_all_orders()
                await asyncio.sleep(0.5) # Give some time for cancellations to register

            # 2. Close existing position if on the wrong side
            if trading_signal == 'long' and self.current_position_side == 'Sell':
                logger.info(f"Closing existing SHORT position ({abs(self.current_position_size):.4f}) with Market BUY order.")
                await self.place_order(side='Buy', qty=abs(self.current_position_size), order_type='Market')
                await asyncio.sleep(0.5) # Give exchange time to process market order
            elif trading_signal == 'short' and self.current_position_side == 'Buy':
                logger.info(f"Closing existing LONG position ({self.current_position_size:.4f}) with Market SELL order.")
                await self.place_order(side='Sell', qty=self.current_position_size, order_type='Market')
                await asyncio.sleep(0.5) # Give exchange time to process market order
            
            # 3. Place new limit entry order in the direction of the new trend
            if trading_signal == 'long':
                if self.current_position_side != 'Buy' or abs(self.current_position_size) < self.max_position_size:
                    # Place slightly below best bid to get filled
                    entry_price = best_bid * (1 - self.spread_percentage) 
                    logger.info(f"Placing new LONG entry order for {self.order_size:.4f} @ {entry_price:.4f}.")
                    await self.place_order(side='Buy', qty=self.order_size, price=entry_price)
            elif trading_signal == 'short':
                if self.current_position_side != 'Sell' or abs(self.current_position_size) < self.max_position_size:
                    # Place slightly above best ask to get filled
                    entry_price = best_ask * (1 + self.spread_percentage) 
                    logger.info(f"Placing new SHORT entry order for {self.order_size:.4f} @ {entry_price:.4f}.")
                    await self.place_order(side='Sell', qty=self.order_size, price=entry_price)
            
            self.last_trading_signal = trading_signal
        
        else: # No new signal or already acted on it. Maintain/reprice existing entry orders.
            # --- Reprice / Maintain Entry Orders ---
            if self.last_trading_signal == 'long':
                # Reprice buy orders if market moves significantly or replace if missing
                current_long_entry_orders = [o for o in self.active_orders.values() if o.get('side') == 'Buy' and o.get('symbol') == self.symbol]
                
                if current_long_entry_orders:
                    for order_id, order_details in current_long_entry_orders:
                        existing_price = float(order_details.get('price'))
                        target_entry_price = best_bid * (1 - self.spread_percentage) # Aim to buy slightly below market
                        
                        if abs(existing_price - target_entry_price) / target_entry_price > self.order_reprice_threshold_pct:
                            logger.info(f"Repricing LONG entry order {order_id}: {existing_price:.4f} -> {target_entry_price:.4f}")
                            await self.cancel_order(order_id)
                            await asyncio.sleep(0.1) # Brief pause
                            if await self._get_total_active_entry_orders_qty('Buy') < self.order_size * self.max_open_entry_orders_per_side:
                                await self.place_order(side='Buy', qty=self.order_size, price=target_entry_price)
                            break # Only reprice one order per cycle to avoid API rate limits
                elif (self.current_position_side == 'None' or (self.current_position_side == 'Buy' and abs(self.current_position_size) < self.max_position_size)) and \
                     (await self._get_total_active_entry_orders_qty('Buy') < self.order_size * self.max_open_entry_orders_per_side):
                    # If no active buy orders (after potential fills/cancellations) and still a long signal, place one
                    entry_price = best_bid * (1 - self.spread_percentage)
                    logger.info(f"Replacing missing LONG entry order for {self.order_size:.4f} @ {entry_price:.4f}.")
                    await self.place_order(side='Buy', qty=self.order_size, price=entry_price)

            elif self.last_trading_signal == 'short':
                # Reprice sell orders if market moves significantly or replace if missing
                current_short_entry_orders = [o for o in self.active_orders.values() if o.get('side') == 'Sell' and o.get('symbol') == self.symbol]
                
                if current_short_entry_orders:
                    for order_id, order_details in current_short_entry_orders:
                        existing_price = float(order_details.get('price'))
                        target_entry_price = best_ask * (1 + self.spread_percentage) # Aim to sell slightly above market
                        
                        if abs(existing_price - target_entry_price) / target_entry_price > self.order_reprice_threshold_pct:
                            logger.info(f"Repricing SHORT entry order {order_id}: {existing_price:.4f} -> {target_entry_price:.4f}")
                            await self.cancel_order(order_id)
                            await asyncio.sleep(0.1) # Brief pause
                            if await self._get_total_active_entry_orders_qty('Sell') < self.order_size * self.max_open_entry_orders_per_side:
                                await self.place_order(side='Sell', qty=self.order_size, price=target_entry_price)
                            break # Only reprice one order per cycle
                elif (self.current_position_side == 'None' or (self.current_position_side == 'Sell' and abs(self.current_position_size) < self.max_position_size)) and \
                     (await self._get_total_active_entry_orders_qty('Sell') < self.order_size * self.max_open_entry_orders_per_side):
                    # If no active sell orders and still a short signal, place one
                    entry_price = best_ask * (1 + self.spread_percentage)
                    logger.info(f"Replacing missing SHORT entry order for {self.order_size:.4f} @ {entry_price:.4f}.")
                    await self.place_order(side='Sell', qty=self.order_size, price=entry_price)
            else: # last_trading_signal is None, meaning no clear trend or waiting
                 logger.debug("No active trading signal. Waiting for Supertrend confirmation.")

        # Always check and potentially reduce position if it's too large regardless of signal
        if abs(self.current_position_size) > self.max_position_size + self.order_size * 0.5: # Add a buffer to max position
            logger.warning(f"Position size ({abs(self.current_position_size):.4f}) for {self.symbol} exceeds MAX_POSITION_SIZE. Attempting to reduce.")
            rebalance_qty = abs(self.current_position_size) # Target to reduce entire excess
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
        self.kline_fetch_task = asyncio.create_task(self._fetch_kline_data_loop())

        logger.info("Bot main trading loop started.")
        while self.is_running:
            try:
                await self.trading_logic()
            except asyncio.CancelledError:
                logger.info("Trading logic task cancelled gracefully.")
                break
            except Exception as e:
                logger.error(f"Error in main trading loop: {e}", exc_info=True)
                await asyncio.sleep(API_RETRY_DELAY_SECONDS)

        await self.shutdown()

    async def shutdown(self):
        """Gracefully shuts down the bot, cancelling orders and closing connections."""
        logger.info("Shutting down bot...")
        self.is_running = False # Signal all loops to stop

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

        if self.kline_fetch_task and not self.kline_fetch_task.done():
            self.kline_fetch_task.cancel()
            try: await self.kline_fetch_task
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
        kline_interval=KLINE_INTERVAL,
        kline_limit=KLINE_LIMIT,
        atr_period=ATR_PERIOD,
        supertrend_multiplier=SUPERTREND_MULTIPLIER,
        max_position_size=MAX_POSITION_SIZE,
        max_open_entry_orders_per_side=MAX_OPEN_ENTRY_ORDERS_PER_SIDE,
        order_reprice_threshold_pct=ORDER_REPRICE_THRESHOLD_PCT,
        testnet=TESTNET
    )

    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt detected. Stopping bot gracefully...")
        # shutdown() is called by start() if loop breaks, or explicitly if start() fails quickly
    except Exception as e:
        logger.critical(f"An unhandled exception occurred during bot execution: {e}", exc_info=True)
        # shutdown() is called by start() if loop breaks, or explicitly if start() fails quickly
  
