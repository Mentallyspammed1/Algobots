Okay, this is a significant upgrade! To make the bot interchangable with different strategies, we'll implement a Strategy Pattern.Here's the breakdown of how we'll achieve this:config.py: Centralized configuration, including which strategy to use and its specific parameters.interfaces.py: Defines a BaseStrategy Abstract Base Class (ABC). All concrete strategies must inherit from this and implement its abstract methods. This ensures a consistent interface for the main bot.indicators.py: Houses generic technical indicator calculations (like ATR and Supertrend) and the KlineData dataclass.data_structures.py: Contains the PriceLevel dataclass and the AdvancedOrderbookManager (with OptimizedSkipList and EnhancedHeap), as these are generic components needed by any strategy interacting with orderbook data.strategies/ directory:__init__.py: Makes strategies a Python package.ehlers_supertrend.py: Implements the Ehlers Supertrend strategy, adhering to BaseStrategy.market_making.py: Implements a simple market making strategy, adhering to BaseStrategy.main.py: The core BybitTradingBot class. It will load the chosen strategy dynamically, feed it data, and execute its commands. The trading_logic becomes generic, calling the currently active strategy's methods.Step 1: Create config.py code Pythondownloadcontent_copyexpand_less    # config.py
import os
import logging

# --- General Bot Configuration ---
# Set to True for testing on Bybit Testnet, False for Mainnet trading.
# IMPORTANT: Use separate API keys for Testnet and Mainnet.
TESTNET = True

# Logging Level: Adjust for verbosity.
# Options: logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL
LOG_LEVEL = logging.INFO 

# --- API Credentials ---
# IMPORTANT: Load API keys from environment variables for security.
# DO NOT hardcode them directly in this file for production use.
# Example: export BYBIT_API_KEY="YOUR_API_KEY"
#          export BYBIT_API_SECRET="YOUR_API_SECRET"
API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')

# --- Trading Pair & Account Type ---
SYMBOL = 'BTCUSDT'              # The trading pair (e.g., 'BTCUSDT', 'ETHUSDT')
CATEGORY = 'linear'             # Account category: 'spot', 'linear', 'inverse', 'option'

# --- Order & Position Sizing (Common to many strategies) ---
LEVERAGE = 10                   # Desired leverage for derivatives (e.g., 5, 10, 25)
ORDER_SIZE = 0.001              # Quantity for each entry/exit order in base currency (e.g., 0.001 BTC)
MAX_POSITION_SIZE = 0.01        # Max allowed absolute position size. Bot will try to reduce if exceeded.

# --- Delays & Retry Settings ---
RECONNECT_DELAY_SECONDS = 5     # Delay before attempting WebSocket reconnection
API_RETRY_DELAY_SECONDS = 3     # Delay before retrying failed HTTP API calls
TRADE_LOGIC_INTERVAL_SECONDS = 1 # How often the bot's main trading logic runs

# --- Advanced Orderbook Manager Settings ---
USE_SKIP_LIST_FOR_ORDERBOOK = True # True for OptimizedSkipList, False for EnhancedHeap

# --- Strategy Selection ---
# Choose which strategy to activate.
# Options: 'EhlersSupertrendStrategy', 'MarketMakingStrategy' (ensure class name matches file name in strategies folder)
ACTIVE_STRATEGY_NAME = 'EhlersSupertrendStrategy' # Or 'MarketMakingStrategy'

# --- Strategy-Specific Parameters ---
# Parameters for EhlersSupertrendStrategy
SUPERTREND_KLINE_INTERVAL = '15' # Kline interval for Supertrend (e.g., '1', '5', '15', '60', 'D')
SUPERTREND_KLINE_LIMIT = 200    # Number of historical klines (must be > ATR_PERIOD)
SUPERTREND_ATR_PERIOD = 14      # Period for ATR calculation
SUPERTREND_MULTIPLIER = 3       # Multiplier for ATR in Supertrend calculation
SUPERTREND_ORDER_REPRICE_THRESHOLD_PCT = 0.0002 # % price change to reprice limit orders
SUPERTREND_MAX_OPEN_ENTRY_ORDERS_PER_SIDE = 1 # Max entry limit orders on one side

# Parameters for MarketMakingStrategy
MM_SPREAD_PERCENTAGE = 0.0005   # 0.05% spread (0.0005) for market making
MM_ORDER_REPRICE_THRESHOLD_PCT = 0.0002 # % price change to reprice limit orders
MM_MAX_OPEN_ORDERS_PER_SIDE = 1 # Max buy/sell limit orders for MM
  Step 2: Create interfaces.py code Pythondownloadcontent_copyexpand_lessIGNORE_WHEN_COPYING_STARTIGNORE_WHEN_COPYING_END    # interfaces.py
from abc import ABC, abstractmethod
from collections import deque
from typing import Dict, List, Any, Optional, Tuple

# Forward declarations for type hinting circular dependencies
from pybit.unified_trading import HTTP
# from data_structures import AdvancedOrderbookManager # Actual import later
# from indicators import KlineData # Actual import later

class BaseStrategy(ABC):
    """
    Abstract Base Class for all trading strategies.
    Defines the interface that all concrete strategies must implement.
    The main bot will interact with strategies through this interface.
    """
    def __init__(self, bot_instance: Any, http_session: HTTP, orderbook_manager: Any, kline_data_deque: deque, config: Any):
        self.bot = bot_instance  # Reference to the main bot for API calls
        self.http_session = http_session
        self.orderbook_manager = orderbook_manager
        self.kline_data = kline_data_deque # Live kline data deque, shared with bot
        self.config = config

        self.symbol = config.SYMBOL
        self.category = config.CATEGORY
        self.order_size = config.ORDER_SIZE
        self.max_position_size = config.MAX_POSITION_SIZE
        
        self.active_orders: Dict[str, Dict[str, Any]] = {} # Updated by bot, read by strategy
        self.current_position_size: float = 0.0
        self.current_position_side: str = 'None' # 'Buy', 'Sell', or 'None'
        self.current_position_avg_price: float = 0.0
        self.wallet_balance: float = 0.0

    @abstractmethod
    async def initialize(self):
        """
        Perform any one-time setup or data fetching required by the strategy.
        Called once when the bot starts.
        """
        pass

    @abstractmethod
    async def update_bot_state(self,
                               active_orders: Dict[str, Dict[str, Any]],
                               current_position_size: float,
                               current_position_side: str,
                               current_position_avg_price: float,
                               wallet_balance: float):
        """
        Update the strategy's internal state with the latest information from the bot.
        This is how the strategy receives updates about orders, positions, and balance.
        """
        self.active_orders = active_orders
        self.current_position_size = current_position_size
        self.current_position_side = current_position_side
        self.current_position_avg_price = current_position_avg_price
        self.wallet_balance = wallet_balance

    @abstractmethod
    async def execute_trading_logic(self, current_best_bid: Optional[float], current_best_ask: Optional[float]):
        """
        This is the main method where the strategy's core trading logic resides.
        It should analyze market conditions and bot state, then call the bot's
        order placement/cancellation methods.
        """
        pass

    @abstractmethod
    async def get_strategy_specific_kline_interval(self) -> Optional[str]:
        """
        Return the kline interval required by this strategy, or None if not applicable.
        """
        pass

    @abstractmethod
    async def get_strategy_specific_kline_limit(self) -> Optional[int]:
        """
        Return the kline limit required by this strategy, or None if not applicable.
        """
        pass

    # Helper methods that strategies can use (these will delegate to bot's methods)
    async def place_order(self, side: str, qty: float, price: Optional[float] = None, order_type: str = 'Limit', client_order_id: Optional[str] = None) -> Optional[str]:
        return await self.bot.place_order(side, qty, price, order_type, client_order_id)

    async def cancel_order(self, order_id: str) -> bool:
        return await self.bot.cancel_order(order_id)

    async def cancel_all_orders(self) -> int:
        return await self.bot.cancel_all_orders()
        
    async def get_total_active_entry_orders_qty(self, side: str) -> float:
        """Helper to get total qty of active entry orders for this strategy."""
        total_qty = 0.0
        for order in self.active_orders.values():
            # Customize this filter if your strategy places different types of orders
            # and you only want to count 'entry' orders here.
            if order.get('side') == side and order.get('symbol') == self.symbol and order.get('orderType') == 'Limit':
                total_qty += float(order.get('qty', 0))
        return total_qty
  Step 3: Create indicators.py code Pythondownloadcontent_copyexpand_lessIGNORE_WHEN_COPYING_STARTIGNORE_WHEN_COPYING_END    # indicators.py
from collections import deque
from dataclasses import dataclass
from typing import List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

@dataclass(slots=True)
class KlineData:
    """Represents a single kline (candlestick) with essential data."""
    start_time: int    # Unix timestamp in milliseconds
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float

class TechnicalIndicators:
    """
    Provides static methods for calculating common technical indicators.
    """

    @staticmethod
    def calculate_atr(highs: List[float], lows: List[float], closes: List[float], period: int) -> List[float]:
        """
        Calculates Average True Range (ATR).
        Returns a list of ATR values. The first 'period' elements will be empty or correspond
        to the data points *after* the initial period.
        """
        if len(highs) < period + 1:
            logger.debug(f"Not enough data for ATR calculation. Need {period + 1} data points, got {len(highs)}.")
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
            
        # Initial ATR is the simple average of the first 'period' True Ranges
        atr_values_raw = [sum(trs[:period]) / period]
        # Subsequent ATRs use Wilder's Smoothing method
        for i in range(period, len(trs)):
            atr_val = (atr_values_raw[-1] * (period - 1) + trs[i]) / period
            atr_values_raw.append(atr_val)
        
        # The returned list's index 0 corresponds to the ATR for closes[period]
        return atr_values_raw

    @staticmethod
    def calculate_supertrend(
        highs: List[float], lows: List[float], closes: List[float],
        atr_period: int, multiplier: float
    ) -> Tuple[List[float], List[str]]:
        """
        Calculates Supertrend indicator values and direction.
        Returns a tuple: (supertrend_line_values, supertrend_direction_signals).
        Direction signals are 'up' or 'down'.
        The returned lists will have `len(closes) - atr_period` elements,
        corresponding to the candles from `closes[atr_period]` onwards.
        """
        if len(closes) < atr_period + 1:
            logger.debug(f"Not enough data for Supertrend calculation. Need {atr_period + 1} closes, got {len(closes)}.")
            return [], []

        atr_values = TechnicalIndicators.calculate_atr(highs, lows, closes, atr_period)
        if not atr_values:
            logger.warning("ATR calculation failed or returned empty. Cannot calculate Supertrend.")
            return [], []
            
        # Supertrend calculation starts after ATR_PERIOD.
        # `offset` helps align ATR values (which start from `atr_period`th candle) with kline data.
        offset = atr_period 

        supertrend_line = [0.0] * len(closes)
        supertrend_direction = [''] * len(closes)
        
        # --- Initialization for the first valid candle (closes[offset]) ---
        # The first ATR value in atr_values corresponds to closes[offset]
        current_atr_for_first_st = atr_values[0] 
        
        hl2 = (highs[offset] + lows[offset]) / 2
        basic_upper_band = hl2 + multiplier * current_atr_for_first_st
        basic_lower_band = hl2 - multiplier * current_atr_for_first_st
        
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
            current_atr = atr_values[i - offset] # Corresponding ATR value from the atr_values list

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
  Step 4: Create data_structures.py code Pythondownloadcontent_copyexpand_lessIGNORE_WHEN_COPYING_STARTIGNORE_WHEN_COPYING_END    # data_structures.py
import asyncio
import random
import time
from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Tuple, Generic, TypeVar
from contextlib import asynccontextmanager
import logging

logger = logging.getLogger(__name__)

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
  Step 5: Create strategies/ directory and filesFirst, create the strategies directory:mkdir strategiesThen, create an empty __init__.py inside it:touch strategies/__init__.pystrategies/ehlers_supertrend.py code Pythondownloadcontent_copyexpand_lessIGNORE_WHEN_COPYING_STARTIGNORE_WHEN_COPYING_END    # strategies/ehlers_supertrend.py
from collections import deque
from typing import Dict, List, Any, Optional
import asyncio
import logging

# Import from parent directories
from interfaces import BaseStrategy
from indicators import TechnicalIndicators, KlineData
# from data_structures import AdvancedOrderbookManager # For type hinting, not direct import in strategy

logger = logging.getLogger(__name__)

class EhlersSupertrendStrategy(BaseStrategy):
    """
    Implements the Ehlers Supertrend Cross trading strategy.
    - Trades on Supertrend flip.
    - Closes existing position with a market order upon flip.
    - Opens a new position in the direction of the new trend with a limit order.
    - Manages limit orders for entry based on orderbook best bid/ask.
    """
    def __init__(self, bot_instance: Any, http_session: Any, orderbook_manager: Any, kline_data_deque: deque, config: Any):
        super().__init__(bot_instance, http_session, orderbook_manager, kline_data_deque, config)
        
        # Strategy-specific parameters from config
        self.kline_interval = config.SUPERTREND_KLINE_INTERVAL
        self.kline_limit = config.SUPERTREND_KLINE_LIMIT
        self.atr_period = config.SUPERTREND_ATR_PERIOD
        self.supertrend_multiplier = config.SUPERTREND_MULTIPLIER
        self.order_reprice_threshold_pct = config.SUPERTREND_ORDER_REPRICE_THRESHOLD_PCT
        self.max_open_entry_orders_per_side = config.SUPERTREND_MAX_OPEN_ENTRY_ORDERS_PER_SIDE

        # Supertrend State
        self.supertrend_line: Optional[float] = None
        self.supertrend_direction: Optional[str] = None # 'up' or 'down'
        self.last_trading_signal: Optional[str] = None # 'long', 'short' to track last acted signal

        logger.info(f"EhlersSupertrendStrategy initialized for {self.symbol}.")
        logger.info(f"Supertrend Config: Interval={self.kline_interval}, ATR_Period={self.atr_period}, Multiplier={self.supertrend_multiplier}")

    async def initialize(self):
        """
        Initializes the strategy by calculating initial Supertrend.
        This will be called after initial kline data is fetched by the bot.
        """
        logger.info("EhlersSupertrendStrategy performing initial setup...")
        await self._calculate_and_update_supertrend()
        if self.supertrend_direction:
            self.last_trading_signal = 'long' if self.supertrend_direction == 'up' else 'short'
            logger.info(f"Initial Supertrend direction: {self.supertrend_direction.upper()}. Setting last_trading_signal to {self.last_trading_signal}.")
        else:
            logger.warning("Could not calculate initial Supertrend direction.")

    async def _calculate_and_update_supertrend(self):
        """Calculates Supertrend and updates strategy's indicator state."""
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

    async def execute_trading_logic(self, current_best_bid: Optional[float], current_best_ask: Optional[float]):
        """
        Implements the Supertrend Cross strategy trading logic.
        """
        await self._calculate_and_update_supertrend() # Recalculate indicators with latest kline data

        # Ensure sufficient kline data and indicator calculated
        if self.supertrend_line is None or len(self.kline_data) < self.atr_period + 1:
            logger.info("Waiting for Supertrend to be calculated with sufficient kline data...")
            return

        current_candle_close = self.kline_data[-1].close
        
        # Get latest Supertrend values
        current_supertrend = self.supertrend_line
        current_supertrend_direction = self.supertrend_direction

        if current_best_bid is None or current_best_ask is None:
            logger.warning("Orderbook not fully populated yet (best bid/ask missing). Waiting...")
            return

        trading_signal: Optional[str] = None # 'long' or 'short'

        # --- Generate Trading Signal ---
        if current_supertrend_direction == 'up':
            trading_signal = 'long'
        elif current_supertrend_direction == 'down':
            trading_signal = 'short'
        
        # Only act if the signal has changed
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
                # Only if not already long (or too long) and not already placing entry orders
                if self.current_position_side != 'Buy' and self.current_position_side != 'None' and abs(self.current_position_size) > 0:
                    logger.warning("Supertrend wants to go long, but bot is still in an opposing position or partially closing. Waiting for position to clear.")
                    return # Wait for position to fully close
                if (abs(self.current_position_size) < self.max_position_size) and \
                   (await self.get_total_active_entry_orders_qty('Buy') < self.order_size * self.max_open_entry_orders_per_side):
                    
                    entry_price = current_best_bid # Try to get filled at best bid, or slightly aggressive if needed
                    logger.info(f"Placing new LONG entry order for {self.order_size:.4f} @ {entry_price:.4f}.")
                    await self.place_order(side='Buy', qty=self.order_size, price=entry_price)

            elif trading_signal == 'short':
                if self.current_position_side != 'Sell' and self.current_position_side != 'None' and abs(self.current_position_size) > 0:
                    logger.warning("Supertrend wants to go short, but bot is still in an opposing position or partially closing. Waiting for position to clear.")
                    return # Wait for position to fully close
                if (abs(self.current_position_size) < self.max_position_size) and \
                   (await self.get_total_active_entry_orders_qty('Sell') < self.order_size * self.max_open_entry_orders_per_side):
                    
                    entry_price = current_best_ask # Try to get filled at best ask, or slightly aggressive if needed
                    logger.info(f"Placing new SHORT entry order for {self.order_size:.4f} @ {entry_price:.4f}.")
                    await self.place_order(side='Sell', qty=self.order_size, price=entry_price)
            
            self.last_trading_signal = trading_signal
        
        else: # No new signal or already acted on it. Maintain/reprice existing entry orders.
            # Only manage entry orders if we don't have a full position in the trend direction
            if self.current_position_side == 'None' or \
               (self.current_position_side == 'Buy' and self.last_trading_signal == 'long' and abs(self.current_position_size) < self.max_position_size) or \
               (self.current_position_side == 'Sell' and self.last_trading_signal == 'short' and abs(self.current_position_size) < self.max_position_size):

                if self.last_trading_signal == 'long':
                    # Reprice buy orders if market moves significantly or replace if missing
                    current_long_entry_orders = [o for o in self.active_orders.values() if o.get('side') == 'Buy' and o.get('symbol') == self.symbol]
                    
                    if current_long_entry_orders:
                        for order_id, order_details in current_long_entry_orders:
                            existing_price = float(order_details.get('price'))
                            target_entry_price = current_best_bid # Aim to buy at best bid
                            
                            if abs(existing_price - target_entry_price) / target_entry_price > self.order_reprice_threshold_pct:
                                logger.info(f"Repricing LONG entry order {order_id}: {existing_price:.4f} -> {target_entry_price:.4f}")
                                await self.cancel_order(order_id)
                                await asyncio.sleep(0.1) # Brief pause
                                if await self.get_total_active_entry_orders_qty('Buy') < self.order_size * self.max_open_entry_orders_per_side:
                                    await self.place_order(side='Buy', qty=self.order_size, price=target_entry_price)
                                break # Only reprice one order per cycle to avoid API rate limits
                    elif (await self.get_total_active_entry_orders_qty('Buy') < self.order_size * self.max_open_entry_orders_per_side):
                        # If no active buy orders (after potential fills/cancellations) and still a long signal, place one
                        entry_price = current_best_bid
                        logger.info(f"Replacing missing LONG entry order for {self.order_size:.4f} @ {entry_price:.4f}.")
                        await self.place_order(side='Buy', qty=self.order_size, price=entry_price)

                elif self.last_trading_signal == 'short':
                    # Reprice sell orders if market moves significantly or replace if missing
                    current_short_entry_orders = [o for o in self.active_orders.values() if o.get('side') == 'Sell' and o.get('symbol') == self.symbol]
                    
                    if current_short_entry_orders:
                        for order_id, order_details in current_short_entry_orders:
                            existing_price = float(order_details.get('price'))
                            target_entry_price = current_best_ask # Aim to sell at best ask
                            
                            if abs(existing_price - target_entry_price) / target_entry_price > self.order_reprice_threshold_pct:
                                logger.info(f"Repricing SHORT entry order {order_id}: {existing_price:.4f} -> {target_entry_price:.4f}")
                                await self.cancel_order(order_id)
                                await asyncio.sleep(0.1) # Brief pause
                                if await self.get_total_active_entry_orders_qty('Sell') < self.order_size * self.max_open_entry_orders_per_side:
                                    await self.place_order(side='Sell', qty=self.order_size, price=target_entry_price)
                                break # Only reprice one order per cycle
                    elif (await self.get_total_active_entry_orders_qty('Sell') < self.order_size * self.max_open_entry_orders_per_side):
                        # If no active sell orders and still a short signal, place one
                        entry_price = current_best_ask
                        logger.info(f"Replacing missing SHORT entry order for {self.order_size:.4f} @ {entry_price:.4f}.")
                        await self.place_order(side='Sell', qty=self.order_size, price=entry_price)
            else:
                logger.debug(f"Position at {self.current_position_side} {abs(self.current_position_size):.4f}. Not placing new entry orders.")

        # Always check and potentially reduce position if it's too large regardless of signal
        # This acts as a hard stop for excessive position building
        if abs(self.current_position_size) > self.max_position_size + self.order_size * 0.5: # Add a buffer to max position
            logger.warning(f"Position size ({abs(self.current_position_size):.4f}) for {self.symbol} exceeds MAX_POSITION_SIZE. Attempting to reduce.")
            rebalance_qty = abs(self.current_position_size) # Target to reduce entire excess
            if rebalance_qty > 0:
                if self.current_position_side == 'Buy': # Long position, sell to reduce
                    logger.info(f"Rebalancing: Placing Market Sell order for {rebalance_qty:.4f}")
                    await self.place_order(side='Sell', qty=rebalance_qty, price=current_best_bid, order_type='Market')
                elif self.current_position_side == 'Sell': # Short position, buy to reduce
                    logger.info(f"Rebalancing: Placing Market Buy order for {rebalance_qty:.4f}")
                    await self.place_order(side='Buy', qty=rebalance_qty, price=current_best_ask, order_type='Market')
            
    async def get_strategy_specific_kline_interval(self) -> Optional[str]:
        return self.kline_interval

    async def get_strategy_specific_kline_limit(self) -> Optional[int]:
        return self.kline_limit
  strategies/market_making.py code Pythondownloadcontent_copyexpand_lessIGNORE_WHEN_COPYING_STARTIGNORE_WHEN_COPYING_END    # strategies/market_making.py
from collections import deque
from typing import Dict, List, Any, Optional
import asyncio
import logging

# Import from parent directories
from interfaces import BaseStrategy
# from indicators import KlineData # Not needed for this strategy
# from data_structures import AdvancedOrderbookManager # For type hinting

logger = logging.getLogger(__name__)

class MarketMakingStrategy(BaseStrategy):
    """
    Implements a simple Market Making strategy.
    - Places bid and ask limit orders around the current best bid/ask.
    - Reprices orders if the market moves significantly.
    - Manages position size to stay within limits.
    """
    def __init__(self, bot_instance: Any, http_session: Any, orderbook_manager: Any, kline_data_deque: deque, config: Any):
        super().__init__(bot_instance, http_session, orderbook_manager, kline_data_deque, config)
        
        # Strategy-specific parameters from config
        self.spread_percentage = config.MM_SPREAD_PERCENTAGE
        self.order_reprice_threshold_pct = config.MM_ORDER_REPRICE_THRESHOLD_PCT
        self.max_open_orders_per_side = config.MM_MAX_OPEN_ORDERS_PER_SIDE

        logger.info(f"MarketMakingStrategy initialized for {self.symbol}.")
        logger.info(f"MM Config: Spread={self.spread_percentage*100:.2f}%, Reprice Threshold={self.order_reprice_threshold_pct*100:.2f}%")

    async def initialize(self):
        """
        No specific initialization needed for this simple market making strategy.
        Orders will be placed on the first `execute_trading_logic` call.
        """
        logger.info("MarketMakingStrategy ready.")

    async def execute_trading_logic(self, current_best_bid: Optional[float], current_best_ask: Optional[float]):
        """
        Implements the Market Making trading logic.
        """
        if current_best_bid is None or current_best_ask is None:
            logger.warning("Orderbook not fully populated yet (best bid/ask missing). Waiting...")
            return

        # Calculate target bid and ask prices based on desired spread
        target_bid_price = current_best_bid * (1 - self.spread_percentage)
        target_ask_price = current_best_ask * (1 + self.spread_percentage)
        
        # Ensure target prices maintain a valid spread (target_ask_price > target_bid_price)
        if target_bid_price >= target_ask_price:
            logger.warning(f"Calculated target prices ({target_bid_price:.4f} / {target_ask_price:.4f}) overlap or are too close for {self.symbol}. Best Bid:{current_best_bid:.4f}, Best Ask:{current_best_ask:.4f}. Adjusting to ensure separation.")
            # Fallback to a minimal viable spread if strategy leads to crossing prices
            target_bid_price = current_best_bid * (1 - self.spread_percentage / 2)
            target_ask_price = current_best_ask * (1 + self.spread_percentage / 2)
            if target_bid_price >= target_ask_price: # Last resort if it still crosses, slightly widen
                 target_ask_price = target_bid_price * (1 + 0.0001) # Smallest possible increment

        # Get current active orders for specific side
        current_buy_orders_qty = await self.get_total_active_entry_orders_qty('Buy')
        current_sell_orders_qty = await self.get_total_active_entry_orders_qty('Sell')

        # --- Risk Management: Check Max Position Size ---
        # Don't place new buy orders if we're already too long or at max position
        can_place_buy = (abs(self.current_position_size) < self.max_position_size + self.order_size * 0.5) and \
                         (current_buy_orders_qty < self.order_size * self.max_open_orders_per_side)
                         
        # Don't place new sell orders if we're already too short or at max position
        can_place_sell = (abs(self.current_position_size) < self.max_position_size + self.order_size * 0.5) and \
                          (current_sell_orders_qty < self.order_size * self.max_open_orders_per_side)


        # --- Manage Buy Orders ---
        existing_buy_orders = [o for o in self.active_orders.values() if o.get('side') == 'Buy' and o.get('symbol') == self.symbol]
        
        if existing_buy_orders:
            # Repricing logic for existing buy orders
            for order_id, order_details in existing_buy_orders:
                existing_price = float(order_details.get('price'))
                if abs(existing_price - target_bid_price) / target_bid_price > self.order_reprice_threshold_pct:
                    logger.info(f"MM Repricing Buy order {order_id}: {existing_price:.4f} -> {target_bid_price:.4f}")
                    await self.cancel_order(order_id)
                    await asyncio.sleep(0.1) # Give time for cancellation to propagate
                    if can_place_buy:
                        await self.place_order(side='Buy', qty=self.order_size, price=target_bid_price)
                    break # Process one order per cycle to avoid API rate limits
        elif can_place_buy:
            # Place new buy order
            logger.info(f"MM Placing new Buy order for {self.order_size:.4f} @ {target_bid_price:.4f}")
            await self.place_order(side='Buy', qty=self.order_size, price=target_bid_price)


        # --- Manage Sell Orders ---
        existing_sell_orders = [o for o in self.active_orders.values() if o.get('side') == 'Sell' and o.get('symbol') == self.symbol]
        
        if existing_sell_orders:
            # Repricing logic for existing sell orders
            for order_id, order_details in existing_sell_orders:
                existing_price = float(order_details.get('price'))
                if abs(existing_price - target_ask_price) / target_ask_price > self.order_reprice_threshold_pct:
                    logger.info(f"MM Repricing Sell order {order_id}: {existing_price:.4f} -> {target_ask_price:.4f}")
                    await self.cancel_order(order_id)
                    await asyncio.sleep(0.1) # Give time for cancellation to propagate
                    if can_place_sell:
                        await self.place_order(side='Sell', qty=self.order_size, price=target_ask_price)
                    break # Process one order per cycle
        elif can_place_sell:
            # Place new sell order
            logger.info(f"MM Placing new Sell order for {self.order_size:.4f} @ {target_ask_price:.4f}")
            await self.place_order(side='Sell', qty=self.order_size, price=target_ask_price)

        # --- Position Rebalancing (Optional, acts as a hard limit) ---
        if abs(self.current_position_size) > self.max_position_size + self.order_size * 0.5: # Add a buffer to max position
            logger.warning(f"MM Position size ({abs(self.current_position_size):.4f}) for {self.symbol} exceeds MAX_POSITION_SIZE. Attempting to reduce.")
            rebalance_qty = abs(self.current_position_size) # Target to reduce entire excess
            if rebalance_qty > 0:
                if self.current_position_side == 'Buy': # Long position, sell to reduce
                    logger.info(f"MM Rebalancing: Placing Market Sell order for {rebalance_qty:.4f}")
                    await self.place_order(side='Sell', qty=rebalance_qty, price=current_best_bid, order_type='Market')
                elif self.current_position_side == 'Sell': # Short position, buy to reduce
                    logger.info(f"MM Rebalancing: Placing Market Buy order for {rebalance_qty:.4f}")
                    await self.place_order(side='Buy', qty=rebalance_qty, price=current_best_ask, order_type='Market')
            
    async def get_strategy_specific_kline_interval(self) -> Optional[str]:
        # This strategy doesn't strictly need klines for its primary logic,
        # but could return an interval if it wanted to use kline-based filters etc.
        return None

    async def get_strategy_specific_kline_limit(self) -> Optional[int]:
        return None
  Step 6: Create main.py (The Core Bot) code Pythondownloadcontent_copyexpand_lessIGNORE_WHEN_COPYING_STARTIGNORE_WHEN_COPYING_END    # main.py
import os
import asyncio
import json
import logging
import uuid # For generating unique client order IDs
from collections import deque
import importlib
import sys

# Import pybit clients
from pybit.unified_trading import HTTP, WebSocket

# Import configuration settings
import config

# Set up logging using config's log level
logging.basicConfig(
    level=config.LOG_LEVEL,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import shared data structures and indicators
from data_structures import AdvancedOrderbookManager, PriceLevel
from indicators import KlineData # Used for deque

# Import strategy interface
from interfaces import BaseStrategy

# --- Main Trading Bot Class ---
class BybitTradingBot:
    def __init__(self):
        # Validate API keys (still from environment variables for security)
        if not config.API_KEY or not config.API_SECRET:
            logger.critical("BYBIT_API_KEY or BYBIT_API_SECRET environment variables not set. Exiting.")
            raise ValueError("API credentials missing.")

        # Initialize pybit HTTP client
        self.http_session = HTTP(
            testnet=config.TESTNET,
            api_key=config.API_KEY,
            api_secret=config.API_SECRET
        )
        
        # Initialize pybit Public WebSocket client for market data
        self.ws_public = WebSocket(
            channel_type=config.CATEGORY,
            testnet=config.TESTNET
        )
        
        # Initialize pybit Private WebSocket client for account/order updates
        self.ws_private = WebSocket(
            channel_type='private',
            testnet=config.TESTNET,
            api_key=config.API_KEY,
            api_secret=config.API_SECRET
        )

        self.orderbook_manager = AdvancedOrderbookManager(config.SYMBOL, use_skip_list=config.USE_SKIP_LIST_FOR_ORDERBOOK)
        
        # --- Bot State Variables (Managed by Bot, Shared with Strategy) ---
        self.is_running = True
        self.wallet_balance: float = 0.0
        
        self.current_position_size: float = 0.0 # Absolute size
        self.current_position_side: str = 'None' # 'Buy', 'Sell', or 'None'
        self.current_position_avg_price: float = 0.0

        self.active_orders: Dict[str, Dict[str, Any]] = {} # {orderId: order_details}
        
        # --- Kline Data (Managed by Bot, Shared with Strategy) ---
        self.kline_data: deque[KlineData] = deque(maxlen=config.SUPERTREND_KLINE_LIMIT) # Maxlen from strategy that needs most
        
        # --- Strategy Instance ---
        self.strategy: BaseStrategy = self._load_strategy(config.ACTIVE_STRATEGY_NAME)

        # --- Asyncio Tasks ---
        self.public_ws_task: Optional[asyncio.Task] = None
        self.private_ws_task: Optional[asyncio.Task] = None
        self.kline_fetch_task: Optional[asyncio.Task] = None

        logger.info(f"Bot initialized for {config.SYMBOL} ({config.CATEGORY}, Leverage: {config.LEVERAGE}, Testnet: {config.TESTNET}).")
        logger.info(f"Active Strategy: {config.ACTIVE_STRATEGY_NAME}")

    def _load_strategy(self, strategy_name: str) -> BaseStrategy:
        """Dynamically loads and instantiates the chosen strategy."""
        try:
            # Add the strategies directory to the Python path
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'strategies'))
            
            # Import the module
            strategy_module = importlib.import_module(strategy_name.lower()) # e.g., 'ehlers_supertrend'
            
            # Get the class from the module
            strategy_class = getattr(strategy_module, strategy_name) # e.g., EhlersSupertrendStrategy
            
            # Instantiate the strategy
            strategy_instance = strategy_class(
                bot_instance=self, # Pass self (the bot) as the bot_instance
                http_session=self.http_session,
                orderbook_manager=self.orderbook_manager,
                kline_data_deque=self.kline_data,
                config=config
            )
            if not isinstance(strategy_instance, BaseStrategy):
                raise TypeError(f"Loaded strategy {strategy_name} does not inherit from BaseStrategy.")
            
            return strategy_instance
        except (ImportError, AttributeError, TypeError) as e:
            logger.critical(f"Failed to load strategy '{strategy_name}': {e}", exc_info=True)
            raise

    # --- WebSocket Message Handlers ---
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
                    if pos_entry.get('symbol') == config.SYMBOL:
                        self.current_position_size = float(pos_entry.get('size', 0))
                        self.current_position_avg_price = float(pos_entry.get('avgPrice', 0))
                        if self.current_position_size > 0: self.current_position_side = 'Buy'
                        elif self.current_position_size < 0: self.current_position_side = 'Sell'
                        else: self.current_position_side = 'None'
                        logger.info(f"Position update for {config.SYMBOL}: Side={self.current_position_side}, Size={abs(self.current_position_size):.4f}, AvgPrice={self.current_position_avg_price:.4f}")
                        await self.strategy.update_bot_state(
                            self.active_orders, self.current_position_size, self.current_position_side, self.current_position_avg_price, self.wallet_balance
                        )
                        break
            elif topic == 'order':
                for order_entry in data.get('data', []):
                    if order_entry.get('symbol') == config.SYMBOL:
                        order_id = order_entry.get('orderId')
                        order_status = order_entry.get('orderStatus')
                        if order_id:
                            if order_status in ['New', 'PartiallyFilled', 'Untriggered', 'Created']:
                                self.active_orders[order_id] = order_entry
                            elif order_status in ['Filled', 'Cancelled', 'Rejected']:
                                self.active_orders.pop(order_id, None)
                            logger.info(f"Order {order_id} ({order_entry.get('side')} {order_entry.get('qty')} @ {order_entry.get('price')}) status: {order_status}")
                            await self.strategy.update_bot_state(
                                self.active_orders, self.current_position_size, self.current_position_side, self.current_position_avg_price, self.wallet_balance
                            )
            elif topic == 'wallet':
                for wallet_entry in data.get('data', []):
                    if wallet_entry.get('accountType') == 'UNIFIED':
                        self.wallet_balance = float(wallet_entry.get('totalEquity', 0))
                        logger.info(f"Wallet balance update: {self.wallet_balance:.2f}")
                        await self.strategy.update_bot_state(
                            self.active_orders, self.current_position_size, self.current_position_side, self.current_position_avg_price, self.wallet_balance
                        )
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
                    ws_client.orderbook_stream(depth=25, symbol=config.SYMBOL, callback=handler_func)
                    ws_client.ticker_stream(symbol=config.SYMBOL, callback=handler_func)
                    # No kline stream here, we fetch klines via HTTP for historical data
                
                while self.is_running and ws_client.is_connected():
                    await asyncio.sleep(1)
                
                logger.warning(f"{ws_client.channel_type} WebSocket disconnected or connection lost. Attempting reconnect in {config.RECONNECT_DELAY_SECONDS}s.")
                await asyncio.sleep(config.RECONNECT_DELAY_SECONDS)

            except Exception as e:
                logger.error(f"Error in {ws_client.channel_type} WebSocket listener: {e}", exc_info=True)
                await asyncio.sleep(config.RECONNECT_DELAY_SECONDS)

    async def _fetch_kline_data_loop(self):
        """Periodically fetches kline data and updates the bot's state."""
        kline_interval = await self.strategy.get_strategy_specific_kline_interval()
        kline_limit = await self.strategy.get_strategy_specific_kline_limit()

        if kline_interval is None or kline_limit is None:
            logger.info("Current strategy does not require kline data. Skipping kline fetch loop.")
            return

        logger.info(f"Starting kline data fetch loop for {config.SYMBOL} at {kline_interval} interval with limit {kline_limit}.")
        
        # Determine appropriate polling frequency based on kline interval
        if kline_interval.isdigit():
            poll_frequency_seconds = min(int(kline_interval) * 60 / 4, 30) # Poll 4 times per candle, max 30s
            if int(kline_interval) == 1: poll_frequency_seconds = 5 # More frequent for 1m candle
        else: # For 'D', 'W', 'M'
            poll_frequency_seconds = 300 # Poll every 5 minutes for longer intervals

        while self.is_running:
            try:
                response = self.http_session.get_kline(
                    category=config.CATEGORY,
                    symbol=config.SYMBOL,
                    interval=kline_interval,
                    limit=kline_limit
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
                        ) for k in reversed(response['result']['list'])
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
                                if new_kline != self.kline_data[-1]:
                                    self.kline_data[-1] = new_kline
                                    logger.debug(f"Updated last kline: {new_kline.start_time} - Close: {new_kline.close}")
                else:
                    logger.error(f"Failed to fetch kline data: {response['retMsg']}")
                
                await asyncio.sleep(poll_frequency_seconds)

            except asyncio.CancelledError:
                logger.info("Kline fetch task cancelled.")
                break
            except Exception as e:
                logger.error(f"Error in kline fetch loop: {e}", exc_info=True)
                await asyncio.sleep(config.RECONNECT_DELAY_SECONDS)

    async def setup_initial_state(self):
        """Performs initial setup, fetches account info, and sets leverage."""
        logger.info("Starting initial bot setup...")
        retries = 3
        for i in range(retries):
            try:
                # 1. Set Leverage
                response = self.http_session.set_leverage(
                    category=config.CATEGORY, symbol=config.SYMBOL,
                    buyLeverage=str(config.LEVERAGE), sellLeverage=str(config.LEVERAGE)
                )
                if response['retCode'] == 0:
                    logger.info(f"Leverage set to {config.LEVERAGE} for {config.SYMBOL}.")
                else:
                    logger.error(f"Failed to set leverage: {response['retMsg']} (Code: {response['retCode']}). Retrying {i+1}/{retries}...")
                    await asyncio.sleep(config.API_RETRY_DELAY_SECONDS)
                    continue

                # 2. Get Wallet Balance
                wallet_resp = self.http_session.get_wallet_balance(accountType='UNIFIED')
                if wallet_resp['retCode'] == 0 and wallet_resp['result']['list']:
                    self.wallet_balance = float(wallet_resp['result']['list'][0]['totalEquity'])
                    logger.info(f"Initial Wallet Balance: {self.wallet_balance:.2f}")
                else:
                    logger.error(f"Failed to get wallet balance: {wallet_resp['retMsg']}. Retrying {i+1}/{retries}...")
                    await asyncio.sleep(config.API_RETRY_DELAY_SECONDS)
                    continue

                # 3. Get Current Position
                position_resp = self.http_session.get_positions(category=config.CATEGORY, symbol=config.SYMBOL)
                if position_resp['retCode'] == 0 and position_resp['result']['list']:
                    pos_data = position_resp['result']['list'][0]
                    self.current_position_size = float(pos_data.get('size', 0))
                    self.current_position_avg_price = float(pos_data.get('avgPrice', 0))
                    if self.current_position_size > 0: self.current_position_side = 'Buy'
                    elif self.current_position_size < 0: self.current_position_side = 'Sell'
                    else: self.current_position_side = 'None'
                    logger.info(f"Initial Position: Side={self.current_position_side}, Size={abs(self.current_position_size):.4f}, AvgPrice={self.current_position_avg_price:.4f}")
                else:
                    logger.info(f"No initial position found for {config.SYMBOL}.")
                
                # 4. Get Open Orders
                open_orders_resp = self.http_session.get_open_orders(category=config.CATEGORY, symbol=config.SYMBOL)
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
                    await asyncio.sleep(config.API_RETRY_DELAY_SECONDS * (i + 1)) # Exponential backoff
        
        logger.critical("Initial setup failed after multiple retries. Shutting down bot.")
        self.is_running = False # Stop the bot if setup fails completely

    # --- API Interaction Methods (Used by Strategies) ---
    async def place_order(self, side: str, qty: float, price: Optional[float] = None, order_type: str = 'Limit', client_order_id: Optional[str] = None) -> Optional[str]:
        """Places a new order with retry mechanism."""
        if not client_order_id:
            client_order_id = f"bot-{uuid.uuid4()}"

        retries = 3
        for i in range(retries):
            try:
                order_params: Dict[str, Any] = {
                    "category": config.CATEGORY, "symbol": config.SYMBOL, "side": side,
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
                    return None
                else:
                    logger.error(f"Failed to place order {client_order_id}: {response['retMsg']} (Code: {response['retCode']}). Retrying {i+1}/{retries}...")
                    await asyncio.sleep(config.API_RETRY_DELAY_SECONDS)
            except Exception as e:
                logger.error(f"Error placing order {client_order_id}: {e}. Retrying {i+1}/{retries}...", exc_info=True)
                await asyncio.sleep(config.API_RETRY_DELAY_SECONDS)
        logger.critical(f"Failed to place order {client_order_id} after multiple retries.")
        return None

    async def cancel_order(self, order_id: str) -> bool:
        """Cancels an existing order by its order ID with retry mechanism."""
        retries = 3
        for i in range(retries):
            try:
                response = self.http_session.cancel_order(category=config.CATEGORY, symbol=config.SYMBOL, orderId=order_id)
                if response['retCode'] == 0:
                    logger.info(f"Cancelled order {order_id}.")
                    return True
                elif response['retCode'] == 110001: # Order already cancelled/filled
                    logger.warning(f"Order {order_id} already in final state (cancelled/filled).")
                    self.active_orders.pop(order_id, None)
                    return True
                else:
                    logger.error(f"Failed to cancel order {order_id}: {response['retMsg']} (Code: {response['retCode']}). Retrying {i+1}/{retries}...")
                    await asyncio.sleep(config.API_RETRY_DELAY_SECONDS)
            except Exception as e:
                logger.error(f"Error cancelling order {order_id}: {e}. Retrying {i+1}/{retries}...", exc_info=True)
                await asyncio.sleep(config.API_RETRY_DELAY_SECONDS)
        logger.critical(f"Failed to cancel order {order_id} after multiple retries.")
        return False

    async def cancel_all_orders(self) -> int:
        """Cancels all active orders for the symbol with retry mechanism."""
        retries = 3
        for i in range(retries):
            try:
                response = self.http_session.cancel_all_orders(category=config.CATEGORY, symbol=config.SYMBOL)
                if response['retCode'] == 0:
                    cancelled_count = len(response['result']['list'])
                    logger.info(f"Cancelled {cancelled_count} all orders for {config.SYMBOL}.")
                    self.active_orders.clear()
                    return cancelled_count
                else:
                    logger.error(f"Failed to cancel all orders: {response['retMsg']} (Code: {response['retCode']}). Retrying {i+1}/{retries}...")
                    await asyncio.sleep(config.API_RETRY_DELAY_SECONDS)
            except Exception as e:
                logger.error(f"Error cancelling all orders: {e}. Retrying {i+1}/{retries}...", exc_info=True)
                await asyncio.sleep(config.API_RETRY_DELAY_SECONDS)
        logger.critical("Failed to cancel all orders after multiple retries.")
        return 0

    async def start(self):
        """Starts the bot's main loop and WebSocket listeners."""
        await self.setup_initial_state()

        if not self.is_running:
            logger.critical("Bot setup failed. Exiting.")
            return

        # Initialize the strategy after bot state is set up
        await self.strategy.initialize()
        # Update strategy with current bot state
        await self.strategy.update_bot_state(
            self.active_orders, self.current_position_size, self.current_position_side, self.current_position_avg_price, self.wallet_balance
        )


        # Start WebSocket listeners concurrently
        self.public_ws_task = asyncio.create_task(self._start_websocket_listener(self.ws_public, self._handle_public_ws_message))
        self.private_ws_task = asyncio.create_task(self._start_websocket_listener(self.ws_private, self._handle_private_ws_message))
        self.kline_fetch_task = asyncio.create_task(self._fetch_kline_data_loop())

        logger.info("Bot main trading loop started.")
        while self.is_running:
            try:
                current_best_bid, current_best_ask = await self.orderbook_manager.get_best_bid_ask()
                await self.strategy.execute_trading_logic(current_best_bid, current_best_ask)
            except asyncio.CancelledError:
                logger.info("Trading logic task cancelled gracefully.")
                break
            except Exception as e:
                logger.error(f"Error in main trading loop: {e}", exc_info=True)
                await asyncio.sleep(config.API_RETRY_DELAY_SECONDS)

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
    if not config.API_KEY or not config.API_SECRET:
        logger.critical("BYBIT_API_KEY or BYBIT_API_SECRET environment variables are NOT set. Please set them before running the bot.")
        exit(1)

    bot = BybitTradingBot()

    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt detected. Stopping bot gracefully...")
    except Exception as e:
        logger.critical(f"An unhandled exception occurred during bot execution: {e}", exc_info=True)
  How to Set Up and Run This Interchangeable Bot:File Structure: Create the following directory and file structure: code Codedownloadcontent_copyexpand_lessIGNORE_WHEN_COPYING_STARTIGNORE_WHEN_COPYING_END    bybit_interchangeable_bot/
├── config.py
├── main.py
├── interfaces.py
├── indicators.py
├── data_structures.py
└── strategies/
    ├── __init__.py
    ├── ehlers_supertrend.py
    └── market_making.py
  config.py Customization:Crucially, set ACTIVE_STRATEGY_NAME to either 'EhlersSupertrendStrategy' or 'MarketMakingStrategy' (or any other strategy you implement following the BaseStrategy interface).Fill in your API_KEY and API_SECRET (from environment variables!).Adjust SYMBOL, CATEGORY, LEVERAGE, ORDER_SIZE, MAX_POSITION_SIZE, and any strategy-specific parameters as needed.Install pybit: code Bashdownloadcontent_copyexpand_lessIGNORE_WHEN_COPYING_STARTIGNORE_WHEN_COPYING_END    pip install pybit
  Run the Bot: code Bashdownloadcontent_copyexpand_lessIGNORE_WHEN_COPYING_STARTIGNORE_WHEN_COPYING_END    python main.py
  Analysis of the Upgraded and Enhanced Code:Key Design Principles:Strategy Pattern Implementation:BaseStrategy (in interfaces.py): An abstract base class defining the contract for all strategies. This forces all strategies to implement essential methods like initialize(), update_bot_state(), execute_trading_logic(), and methods to declare their kline data needs.Concrete Strategies (in strategies/): EhlersSupertrendStrategy and MarketMakingStrategy inherit from BaseStrategy and implement these methods. They contain only their specific logic and parameters, making them self-contained.Dynamic Loading: The BybitTradingBot dynamically loads the strategy specified in config.ACTIVE_STRATEGY_NAME using importlib.Separation of Concerns:config.py: Pure configuration. No logic.interfaces.py: Defines contracts. No implementation.indicators.py: Pure technical analysis calculation logic. No trading decisions.data_structures.py: Pure data management (orderbook). No trading decisions.strategies/: Pure trading logic based on received data. No direct API calls or WebSocket management.main.py: Manages API clients, WebSockets, bot state, feeds data to the strategy, and executes strategy commands.Centralized Bot State Management:The BybitTradingBot maintains the canonical state for active_orders, current_position_size, current_position_side, current_position_avg_price, and wallet_balance.This state is passed to the active strategy via strategy.update_bot_state() whenever it changes (from WebSocket updates). Strategies read this state but do not modify it directly.Generic Data Flow:Orderbook Data: main.py's AdvancedOrderbookManager handles public WebSocket orderbook updates and main.py passes best_bid and best_ask to strategy.execute_trading_logic().Kline Data: main.py's _fetch_kline_data_loop fetches kline data (using http_session and kline_interval/kline_limit requested by the strategy), populates self.kline_data (a shared deque), and strategies can then access this deque directly (as self.kline_data in BaseStrategy).Account/Order Data: main.py's private WebSocket handler updates the bot's state variables and then calls strategy.update_bot_state() to synchronize the strategy.Specific Enhancements Applied:_load_strategy Method: Handles dynamic import and instantiation of the strategy class. Includes robust error handling for ImportError, AttributeError, and TypeError if the strategy name is wrong or the class doesn't implement BaseStrategy.Strategy-Specific Kline Fetching: The bot now queries the active strategy (strategy.get_strategy_specific_kline_interval() and get_strategy_specific_kline_limit()) to determine if it needs kline data and what parameters to use. This makes strategies that don't need klines more efficient.Decoupled Trading Logic: The trading_logic in main.py is removed, replaced by a simple call to self.strategy.execute_trading_logic().Strategy-Owned Parameters: Strategy-specific parameters (like ATR_PERIOD, SUPERTREND_MULTIPLIER, MM_SPREAD_PERCENTAGE) are now accessed by the strategy directly from the config object passed to its __init__.API Client Reusability: The http_session and orderbook_manager are passed to the strategy's __init__, so strategies can perform their own lookups if necessary (e.g., initial get_kline for Supertrend calculation).Helper Methods for Strategies: BaseStrategy provides wrapper methods (place_order, cancel_order, cancel_all_orders) that simply delegate to the bot's methods. This allows strategies to command the bot without knowing its internal implementation details.Robustness: Continued use of asyncio.Lock for data structures, retry mechanisms for API calls, and comprehensive logging.This template is a robust framework for building and interchanging complex trading strategies on Bybit, providing a clean separation of concerns and high extensibility.
  ///////////
  This is an excellent request! To make the bot truly interchangeable and robust, we'll implement several key architectural improvements:Centralized Strategy Configuration: All strategy-specific parameters will be grouped under a StrategyConfig dictionary in config.py, making it cleaner to switch strategies and manage their settings.Bot State Dataclass: All core bot state (wallet, position, active orders) will be encapsulated in a BotState dataclass. This BotState object will be passed to strategies, providing a single, consistent source of truth.Enhanced BaseStrategy Interface:initialize(): For one-time strategy setup.on_kline_update(): To allow strategies to react specifically to new kline data being available.on_orderbook_update(): To allow strategies to react specifically to orderbook updates.execute_trading_logic(): The main trading decision-making loop.Generic API Retry Decorator: A reusable asynchronous retry decorator to make API calls more resilient.Improved Orderbook Manager: Add methods for mid-price and spread calculation.Refactored main.py: The bot will become an orchestrator, handling data flow and API interactions, while delegating all trading decisions to the active strategy.Strategy Adaptations: Both EhlersSupertrendStrategy and MarketMakingStrategy will be updated to leverage these new interfaces and data structures.Step 1: Create config.py code Pythondownloadcontent_copyexpand_less    # config.py
import os
import logging
from typing import Dict, Any

# --- General Bot Configuration ---
# Set to True for testing on Bybit Testnet, False for Mainnet trading.
# IMPORTANT: Use separate API keys for Testnet and Mainnet.
TESTNET = True

# Logging Level: Adjust for verbosity.
# Options: logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL
LOG_LEVEL = logging.INFO 

# --- API Credentials ---
# IMPORTANT: Load API keys from environment variables for security.
# DO NOT hardcode them directly in this file for production use.
# Example (for Linux/macOS): export BYBIT_API_KEY="YOUR_API_KEY"
#          export BYBIT_API_SECRET="YOUR_API_SECRET"
# Example (for Windows PowerShell): $env:BYBIT_API_KEY="YOUR_API_KEY"
#                                  $env:BYBIT_API_SECRET="YOUR_API_SECRET"
API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')

# --- Trading Pair & Account Type ---
SYMBOL = 'BTCUSDT'              # The trading pair (e.g., 'BTCUSDT', 'ETHUSDT')
CATEGORY = 'linear'             # Account category: 'spot', 'linear', 'inverse', 'option'

# --- Order & Position Sizing (Common to many strategies) ---
LEVERAGE = 10                   # Desired leverage for derivatives (e.g., 5, 10, 25)
ORDER_SIZE = 0.001              # Quantity for each entry/exit order in base currency (e.g., 0.001 BTC)
MAX_POSITION_SIZE = 0.01        # Max allowed absolute position size. Bot will try to reduce if exceeded.
POSITION_REBALANCE_BUFFER = 0.0005 # Buffer amount before rebalancing position (e.g., 0.0005 BTC)

# --- Delays & Retry Settings ---
RECONNECT_DELAY_SECONDS = 5     # Delay before attempting WebSocket reconnection
API_RETRY_DELAY_SECONDS = 3     # Delay before retrying failed HTTP API calls
TRADE_LOGIC_INTERVAL_SECONDS = 1 # How often the bot's main trading logic runs
KLINE_FETCH_POLL_RATE = 5       # Seconds between polling for new kline data (adjusted dynamically by kline interval)

# --- Advanced Orderbook Manager Settings ---
USE_SKIP_LIST_FOR_ORDERBOOK = True # True for OptimizedSkipList, False for EnhancedHeap

# --- Strategy Selection ---
# Choose which strategy to activate.
# The string must match the class name in the strategies/ directory.
ACTIVE_STRATEGY_NAME = 'EhlersSupertrendStrategy' # Options: 'EhlersSupertrendStrategy', 'MarketMakingStrategy'

# --- Strategy-Specific Parameters ---
# Parameters are grouped by strategy name for clarity.
# Access them in your strategy using self.strategy_params['YOUR_PARAM']
STRATEGY_CONFIG: Dict[str, Dict[str, Any]] = {
    'EhlersSupertrendStrategy': {
        'KLINE_INTERVAL': '15',         # Kline interval for Supertrend (e.g., '1', '5', '15', '60', 'D')
        'KLINE_LIMIT': 200,             # Number of historical klines (must be > ATR_PERIOD)
        'ATR_PERIOD': 14,               # Period for ATR calculation
        'SUPERTREND_MULTIPLIER': 3,     # Multiplier for ATR in Supertrend calculation
        'ORDER_REPRICE_THRESHOLD_PCT': 0.0002, # % price change to reprice limit orders (0.02%)
        'MAX_OPEN_ENTRY_ORDERS_PER_SIDE': 1 # Max entry limit orders on one side
    },
    'MarketMakingStrategy': {
        'SPREAD_PERCENTAGE': 0.0005,    # 0.05% spread (0.0005) for market making
        'ORDER_REPRICE_THRESHOLD_PCT': 0.0002, # % price change to reprice limit orders (0.02%)
        'MAX_OPEN_ORDERS_PER_SIDE': 1   # Max buy/sell limit orders for MM
    },
    # Add new strategies here
}

# General Risk Management (Can be extended)
MAX_ACCOUNT_DRAWDOWN_PCT = 0.10 # Max 10% drawdown on total equity
  Step 2: Create interfaces.py code Pythondownloadcontent_copyexpand_lessIGNORE_WHEN_COPYING_STARTIGNORE_WHEN_COPYING_END    # interfaces.py
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple

# Forward declarations for type hinting circular dependencies
# from main import BybitTradingBot # Actual import later
# from data_structures import AdvancedOrderbookManager, PriceLevel # Actual import later
# from indicators import KlineData # Actual import later

@dataclass
class BotState:
    """
    Centralized dataclass to hold the current state of the bot.
    Strategies will read from this object.
    """
    wallet_balance: float = 0.0
    
    current_position_size: float = 0.0
    current_position_side: str = 'None' # 'Buy', 'Sell', or 'None'
    current_position_avg_price: float = 0.0

    active_orders: Dict[str, Dict[str, Any]] = field(default_factory=dict) # {orderId: order_details}

class BaseStrategy(ABC):
    """
    Abstract Base Class for all trading strategies.
    Defines the interface that all concrete strategies must implement.
    The main bot will interact with strategies through this interface.
    """
    def __init__(self, bot_instance: Any, http_session: Any, orderbook_manager: Any, kline_data_deque: deque, bot_state: BotState, strategy_params: Dict[str, Any], config: Any):
        self.bot = bot_instance  # Reference to the main bot for API calls
        self.http_session = http_session
        self.orderbook_manager = orderbook_manager
        self.kline_data = kline_data_deque # Live kline data deque, shared with bot
        self.bot_state = bot_state # The shared BotState object
        self.strategy_params = strategy_params # Strategy-specific parameters
        self.config = config # Reference to the global config module

        # Common parameters from global config for convenience
        self.symbol = config.SYMBOL
        self.category = config.CATEGORY
        self.order_size = config.ORDER_SIZE
        self.max_position_size = config.MAX_POSITION_SIZE
        self.position_rebalance_buffer = config.POSITION_REBALANCE_BUFFER

    @abstractmethod
    async def initialize(self):
        """
        Perform any one-time setup or data fetching required by the strategy.
        Called once when the bot starts, after initial bot state is set.
        """
        pass

    @abstractmethod
    async def on_kline_update(self):
        """
        Called by the bot when new kline data is fetched or updated.
        Strategies should use this to recalculate indicators.
        """
        pass
    
    @abstractmethod
    async def on_orderbook_update(self, best_bid: Optional[float], best_ask: Optional[float]):
        """
        Called by the bot when the orderbook is updated (snapshot or delta applied).
        Strategies can use this for real-time orderbook-driven decisions.
        """
        pass

    @abstractmethod
    async def execute_trading_logic(self):
        """
        This is the main method where the strategy's core trading logic resides.
        It should analyze market conditions and bot state, then call the bot's
        order placement/cancellation methods. This is called periodically by the bot.
        """
        pass

    @abstractmethod
    async def get_strategy_specific_kline_interval(self) -> Optional[str]:
        """
        Return the kline interval required by this strategy, or None if not applicable.
        """
        pass

    @abstractmethod
    async def get_strategy_specific_kline_limit(self) -> Optional[int]:
        """
        Return the kline limit required by this strategy, or None if not applicable.
        """
        pass

    # Helper methods that strategies can use (these will delegate to bot's methods)
    async def place_order(self, side: str, qty: float, price: Optional[float] = None, order_type: str = 'Limit', client_order_id: Optional[str] = None) -> Optional[str]:
        """Delegate to bot's place_order method."""
        return await self.bot.place_order(side, qty, price, order_type, client_order_id)

    async def cancel_order(self, order_id: str) -> bool:
        """Delegate to bot's cancel_order method."""
        return await self.bot.cancel_order(order_id)

    async def cancel_all_orders(self) -> int:
        """Delegate to bot's cancel_all_orders method."""
        return await self.bot.cancel_all_orders()
        
    async def get_total_active_entry_orders_qty(self, side: str) -> float:
        """Helper to get total qty of active entry orders for this strategy."""
        total_qty = 0.0
        for order in self.bot_state.active_orders.values():
            if order.get('side') == side and order.get('symbol') == self.symbol and order.get('orderType') == 'Limit':
                total_qty += float(order.get('qty', 0))
        return total_qty
  Step 3: Create indicators.py code Pythondownloadcontent_copyexpand_lessIGNORE_WHEN_COPYING_STARTIGNORE_WHEN_COPYING_END    # indicators.py
from collections import deque
from dataclasses import dataclass
from typing import List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

@dataclass(slots=True)
class KlineData:
    """Represents a single kline (candlestick) with essential data."""
    start_time: int    # Unix timestamp in milliseconds
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float

class TechnicalIndicators:
    """
    Provides static methods for calculating common technical indicators.
    """

    @staticmethod
    def calculate_atr(highs: List[float], lows: List[float], closes: List[float], period: int) -> List[float]:
        """
        Calculates Average True Range (ATR).
        Returns a list of ATR values. The first 'period' elements will be empty or correspond
        to the data points *after* the initial period.
        """
        if len(highs) < period + 1:
            logger.debug(f"Not enough data for ATR calculation. Need {period + 1} data points, got {len(highs)}.")
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
            
        # Initial ATR is the simple average of the first 'period' True Ranges
        atr_values_raw = [sum(trs[:period]) / period]
        # Subsequent ATRs use Wilder's Smoothing method
        for i in range(period, len(trs)):
            atr_val = (atr_values_raw[-1] * (period - 1) + trs[i]) / period
            atr_values_raw.append(atr_val)
        
        # The returned list's index 0 corresponds to the ATR for closes[period]
        return atr_values_raw

    @staticmethod
    def calculate_supertrend(
        highs: List[float], lows: List[float], closes: List[float],
        atr_period: int, multiplier: float
    ) -> Tuple[List[float], List[str]]:
        """
        Calculates Supertrend indicator values and direction.
        Returns a tuple: (supertrend_line_values, supertrend_direction_signals).
        Direction signals are 'up' or 'down'.
        The returned lists will have `len(closes) - atr_period` elements,
        corresponding to the candles from `closes[atr_period]` onwards.
        """
        if len(closes) < atr_period + 1:
            logger.debug(f"Not enough data for Supertrend calculation. Need {atr_period + 1} closes, got {len(closes)}.")
            return [], []

        atr_values = TechnicalIndicators.calculate_atr(highs, lows, closes, atr_period)
        if not atr_values:
            logger.warning("ATR calculation failed or returned empty. Cannot calculate Supertrend.")
            return [], []
            
        # Supertrend calculation starts after ATR_PERIOD.
        # `offset` helps align ATR values (which start from `atr_period`th candle) with kline data.
        offset = atr_period 

        supertrend_line = [0.0] * len(closes)
        supertrend_direction = [''] * len(closes)
        
        # --- Initialization for the first valid candle (closes[offset]) ---
        # The first ATR value in atr_values corresponds to closes[offset]
        current_atr_for_first_st = atr_values[0] 
        
        hl2 = (highs[offset] + lows[offset]) / 2
        basic_upper_band = hl2 + multiplier * current_atr_for_first_st
        basic_lower_band = hl2 - multiplier * current_atr_for_first_st
        
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
            current_atr = atr_values[i - offset] # Corresponding ATR value from the atr_values list

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
  Step 4: Create data_structures.py code Pythondownloadcontent_copyexpand_lessIGNORE_WHEN_COPYING_STARTIGNORE_WHEN_COPYING_END    # data_structures.py
import asyncio
import random
import time
from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Tuple, Generic, TypeVar
from contextlib import asynccontextmanager
import logging

logger = logging.getLogger(__name__)

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
            self.bids_ds: OptimizedSkipList[float, PriceLevel] = OptimizedSkipList()
            self.asks_ds: OptimizedSkipList[float, PriceLevel] = OptimizedSkipList()
        else:
            logger.info(f"OrderbookManager for {symbol}: Using EnhancedHeap.")
            self.bids_ds: EnhancedHeap = EnhancedHeap(is_max_heap=True)
            self.asks_ds: EnhancedHeap = EnhancedHeap(is_max_heap=False)
        
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
                self.bids_ds = OptimizedSkipList()
                self.asks_ds = OptimizedSkipList()
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

    async def get_mid_price(self) -> Optional[float]:
        """Calculates the mid-price from the best bid and best ask."""
        best_bid, best_ask = await self.get_best_bid_ask()
        if best_bid is not None and best_ask is not None:
            return (best_bid + best_ask) / 2
        return None

    async def get_spread_percentage(self) -> Optional[float]:
        """Calculates the spread percentage."""
        best_bid, best_ask = await self.get_best_bid_ask()
        if best_bid is not None and best_ask is not None and best_bid > 0:
            return (best_ask - best_bid) / best_bid
        return None

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
  Step 5: Create strategies/ directory and filesFirst, create the strategies directory:mkdir strategiesThen, create an empty __init__.py inside it:touch strategies/__init__.pystrategies/ehlers_supertrend.py code Pythondownloadcontent_copyexpand_lessIGNORE_WHEN_COPYING_STARTIGNORE_WHEN_COPYING_END    # strategies/ehlers_supertrend.py
from collections import deque
from typing import Dict, List, Any, Optional
import asyncio
import logging

# Import from parent directories
import config
from interfaces import BaseStrategy, BotState
from indicators import TechnicalIndicators, KlineData
# from data_structures import AdvancedOrderbookManager # For type hinting, not direct import in strategy

logger = logging.getLogger(__name__)

class EhlersSupertrendStrategy(BaseStrategy):
    """
    Implements the Ehlers Supertrend Cross trading strategy.
    - Trades on Supertrend flip.
    - Closes existing position with a market order upon flip.
    - Opens a new position in the direction of the new trend with a limit order.
    - Manages limit orders for entry based on orderbook best bid/ask.
    """
    def __init__(self, bot_instance: Any, http_session: Any, orderbook_manager: Any, kline_data_deque: deque, bot_state: BotState, strategy_params: Dict[str, Any], config: Any):
        super().__init__(bot_instance, http_session, orderbook_manager, kline_data_deque, bot_state, strategy_params, config)
        
        # Strategy-specific parameters from config
        self.kline_interval = strategy_params['KLINE_INTERVAL']
        self.kline_limit = strategy_params['KLINE_LIMIT']
        self.atr_period = strategy_params['ATR_PERIOD']
        self.supertrend_multiplier = strategy_params['SUPERTREND_MULTIPLIER']
        self.order_reprice_threshold_pct = strategy_params['ORDER_REPRICE_THRESHOLD_PCT']
        self.max_open_entry_orders_per_side = strategy_params['MAX_OPEN_ENTRY_ORDERS_PER_SIDE']

        # Supertrend State
        self.supertrend_line: Optional[float] = None
        self.supertrend_direction: Optional[str] = None # 'up' or 'down'
        self.last_trading_signal: Optional[str] = None # 'long', 'short' to track last acted signal

        logger.info(f"EhlersSupertrendStrategy initialized for {self.symbol}.")
        logger.info(f"Supertrend Config: Interval={self.kline_interval}, ATR_Period={self.atr_period}, Multiplier={self.supertrend_multiplier}")

    async def initialize(self):
        """
        Initializes the strategy by calculating initial Supertrend.
        This will be called after initial kline data is fetched by the bot.
        """
        logger.info("EhlersSupertrendStrategy performing initial setup...")
        # Recalculate indicators here, as kline_data should be pre-populated by now
        await self.on_kline_update() 
        if self.supertrend_direction:
            self.last_trading_signal = 'long' if self.supertrend_direction == 'up' else 'short'
            logger.info(f"Initial Supertrend direction: {self.supertrend_direction.upper()}. Setting last_trading_signal to {self.last_trading_signal}.")
        else:
            logger.warning("Could not calculate initial Supertrend direction.")

    async def on_kline_update(self):
        """Calculates Supertrend and updates strategy's indicator state."""
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

    async def on_orderbook_update(self, best_bid: Optional[float], best_ask: Optional[float]):
        """
        For Supertrend strategy, real-time orderbook updates are mostly for order repricing,
        which is handled within execute_trading_logic.
        """
        pass # No immediate action on orderbook update for this strategy

    async def execute_trading_logic(self):
        """
        Implements the Supertrend Cross strategy trading logic.
        """
        # --- Check for indicator readiness ---
        if self.supertrend_line is None or len(self.kline_data) < self.atr_period + 1:
            logger.info("Waiting for Supertrend to be calculated with sufficient kline data...")
            return

        # --- Get latest market data ---
        current_best_bid, current_best_ask = await self.orderbook_manager.get_best_bid_ask()
        if current_best_bid is None or current_best_ask is None:
            logger.warning("Orderbook not fully populated yet (best bid/ask missing). Waiting...")
            return

        # --- Get latest strategy indicators ---
        current_supertrend = self.supertrend_line
        current_supertrend_direction = self.supertrend_direction

        trading_signal: Optional[str] = None # 'long' or 'short'

        # --- Generate Trading Signal ---
        if current_supertrend_direction == 'up':
            trading_signal = 'long'
        elif current_supertrend_direction == 'down':
            trading_signal = 'short'
        
        # Only act if the signal has changed
        if trading_signal and trading_signal != self.last_trading_signal:
            logger.info(f"--- SUPERTREND FLIP DETECTED! NEW SIGNAL: {trading_signal.upper()} ---")
            
            # 1. Cancel all existing entry orders for flexibility
            if self.bot_state.active_orders:
                logger.info("Cancelling all active entry orders due to signal flip.")
                await self.cancel_all_orders()
                await asyncio.sleep(0.5) # Give some time for cancellations to register

            # 2. Close existing position if on the wrong side
            if trading_signal == 'long' and self.bot_state.current_position_side == 'Sell':
                logger.info(f"Closing existing SHORT position ({abs(self.bot_state.current_position_size):.4f}) with Market BUY order.")
                await self.place_order(side='Buy', qty=abs(self.bot_state.current_position_size), order_type='Market')
                await asyncio.sleep(0.5) # Give exchange time to process market order
            elif trading_signal == 'short' and self.bot_state.current_position_side == 'Buy':
                logger.info(f"Closing existing LONG position ({self.bot_state.current_position_size:.4f}) with Market SELL order.")
                await self.place_order(side='Sell', qty=self.bot_state.current_position_size, order_type='Market')
                await asyncio.sleep(0.5) # Give exchange time to process market order
            
            # 3. Place new limit entry order in the direction of the new trend
            # Only if not already in a position in the new direction and not at max size
            if trading_signal == 'long':
                if self.bot_state.current_position_side != 'Buy' and self.bot_state.current_position_side != 'None' and abs(self.bot_state.current_position_size) > 0:
                    logger.warning("Supertrend wants to go long, but bot is still in an opposing position or partially closing. Waiting for position to clear.")
                    return # Wait for position to fully close
                if (abs(self.bot_state.current_position_size) < self.max_position_size) and \
                   (await self.get_total_active_entry_orders_qty('Buy') < self.order_size * self.max_open_entry_orders_per_side):
                    
                    entry_price = current_best_bid # Try to get filled at best bid, or slightly aggressive if needed
                    logger.info(f"Placing new LONG entry order for {self.order_size:.4f} @ {entry_price:.4f}.")
                    await self.place_order(side='Buy', qty=self.order_size, price=entry_price)

            elif trading_signal == 'short':
                if self.bot_state.current_position_side != 'Sell' and self.bot_state.current_position_side != 'None' and abs(self.bot_state.current_position_size) > 0:
                    logger.warning("Supertrend wants to go short, but bot is still in an opposing position or partially closing. Waiting for position to clear.")
                    return # Wait for position to fully close
                if (abs(self.bot_state.current_position_size) < self.max_position_size) and \
                   (await self.get_total_active_entry_orders_qty('Sell') < self.order_size * self.max_open_entry_orders_per_side):
                    
                    entry_price = current_best_ask # Try to get filled at best ask, or slightly aggressive if needed
                    logger.info(f"Placing new SHORT entry order for {self.order_size:.4f} @ {entry_price:.4f}.")
                    await self.place_order(side='Sell', qty=self.order_size, price=entry_price)
            
            self.last_trading_signal = trading_signal
        
        else: # No new signal or already acted on it. Maintain/reprice existing entry orders.
            # Only manage entry orders if we don't have a full position in the trend direction
            if self.bot_state.current_position_side == 'None' or \
               (self.bot_state.current_position_side == 'Buy' and self.last_trading_signal == 'long' and abs(self.bot_state.current_position_size) < self.max_position_size) or \
               (self.bot_state.current_position_side == 'Sell' and self.last_trading_signal == 'short' and abs(self.bot_state.current_position_size) < self.max_position_size):

                if self.last_trading_signal == 'long':
                    # Reprice buy orders if market moves significantly or replace if missing
                    current_long_entry_orders = [o for o in self.bot_state.active_orders.values() if o.get('side') == 'Buy' and o.get('symbol') == self.symbol]
                    
                    if current_long_entry_orders:
                        for order_id, order_details in current_long_entry_orders:
                            existing_price = float(order_details.get('price'))
                            target_entry_price = current_best_bid # Aim to buy at best bid
                            
                            if abs(existing_price - target_entry_price) / target_entry_price > self.order_reprice_threshold_pct:
                                logger.info(f"Repricing LONG entry order {order_id}: {existing_price:.4f} -> {target_entry_price:.4f}")
                                await self.cancel_order(order_id)
                                await asyncio.sleep(0.1) # Brief pause
                                if await self.get_total_active_entry_orders_qty('Buy') < self.order_size * self.max_open_entry_orders_per_side:
                                    await self.place_order(side='Buy', qty=self.order_size, price=target_entry_price)
                                break # Only reprice one order per cycle to avoid API rate limits
                    elif (await self.get_total_active_entry_orders_qty('Buy') < self.order_size * self.max_open_entry_orders_per_side):
                        # If no active buy orders (after potential fills/cancellations) and still a long signal, place one
                        entry_price = current_best_bid
                        logger.info(f"Replacing missing LONG entry order for {self.order_size:.4f} @ {entry_price:.4f}.")
                        await self.place_order(side='Buy', qty=self.order_size, price=entry_price)

                elif self.last_trading_signal == 'short':
                    # Reprice sell orders if market moves significantly or replace if missing
                    current_short_entry_orders = [o for o in self.bot_state.active_orders.values() if o.get('side') == 'Sell' and o.get('symbol') == self.symbol]
                    
                    if current_short_entry_orders:
                        for order_id, order_details in current_short_entry_orders:
                            existing_price = float(order_details.get('price'))
                            target_entry_price = current_best_ask # Aim to sell at best ask
                            
                            if abs(existing_price - target_entry_price) / target_entry_price > self.order_reprice_threshold_pct:
                                logger.info(f"Repricing SHORT entry order {order_id}: {existing_price:.4f} -> {target_entry_price:.4f}")
                                await self.cancel_order(order_id)
                                await asyncio.sleep(0.1) # Brief pause
                                if await self.get_total_active_entry_orders_qty('Sell') < self.order_size * self.max_open_entry_orders_per_side:
                                    await self.place_order(side='Sell', qty=self.order_size, price=target_entry_price)
                                break # Only reprice one order per cycle
                    elif (await self.get_total_active_entry_orders_qty('Sell') < self.order_size * self.max_open_entry_orders_per_side):
                        # If no active sell orders and still a short signal, place one
                        entry_price = current_best_ask
                        logger.info(f"Replacing missing SHORT entry order for {self.order_size:.4f} @ {entry_price:.4f}.")
                        await self.place_order(side='Sell', qty=self.order_size, price=entry_price)
            else:
                logger.debug(f"Position at {self.bot_state.current_position_side} {abs(self.bot_state.current_position_size):.4f}. Not placing new entry orders.")

        # Always check and potentially reduce position if it's too large regardless of signal
        # This acts as a hard stop for excessive position building
        if abs(self.bot_state.current_position_size) > self.max_position_size + self.position_rebalance_buffer:
            logger.warning(f"Position size ({abs(self.bot_state.current_position_size):.4f}) for {self.symbol} exceeds MAX_POSITION_SIZE. Attempting to reduce.")
            rebalance_qty = abs(self.bot_state.current_position_size) # Target to reduce entire excess
            if rebalance_qty > 0:
                if self.bot_state.current_position_side == 'Buy': # Long position, sell to reduce
                    logger.info(f"Rebalancing: Placing Market Sell order for {rebalance_qty:.4f}")
                    await self.place_order(side='Sell', qty=rebalance_qty, price=current_best_bid, order_type='Market')
                elif self.bot_state.current_position_side == 'Sell': # Short position, buy to reduce
                    logger.info(f"Rebalancing: Placing Market Buy order for {rebalance_qty:.4f}")
                    await self.place_order(side='Buy', qty=rebalance_qty, price=current_best_ask, order_type='Market')
            
    async def get_strategy_specific_kline_interval(self) -> Optional[str]:
        return self.kline_interval

    async def get_strategy_specific_kline_limit(self) -> Optional[int]:
        return self.kline_limit
  strategies/market_making.py code Pythondownloadcontent_copyexpand_lessIGNORE_WHEN_COPYING_STARTIGNORE_WHEN_COPYING_END    # strategies/market_making.py
from collections import deque
from typing import Dict, List, Any, Optional
import asyncio
import logging

# Import from parent directories
import config
from interfaces import BaseStrategy, BotState
# from indicators import KlineData # Not needed for this strategy
# from data_structures import AdvancedOrderbookManager # For type hinting

logger = logging.getLogger(__name__)

class MarketMakingStrategy(BaseStrategy):
    """
    Implements a simple Market Making strategy.
    - Places bid and ask limit orders around the current best bid/ask.
    - Reprices orders if the market moves significantly.
    - Manages position size to stay within limits.
    """
    def __init__(self, bot_instance: Any, http_session: Any, orderbook_manager: Any, kline_data_deque: deque, bot_state: BotState, strategy_params: Dict[str, Any], config: Any):
        super().__init__(bot_instance, http_session, orderbook_manager, kline_data_deque, bot_state, strategy_params, config)
        
        # Strategy-specific parameters from config
        self.spread_percentage = strategy_params['SPREAD_PERCENTAGE']
        self.order_reprice_threshold_pct = strategy_params['ORDER_REPRICE_THRESHOLD_PCT']
        self.max_open_orders_per_side = strategy_params['MAX_OPEN_ORDERS_PER_SIDE']

        logger.info(f"MarketMakingStrategy initialized for {self.symbol}.")
        logger.info(f"MM Config: Spread={self.spread_percentage*100:.2f}%, Reprice Threshold={self.order_reprice_threshold_pct*100:.2f}%")

    async def initialize(self):
        """
        No specific initialization needed for this simple market making strategy.
        Orders will be placed on the first `execute_trading_logic` call.
        """
        logger.info("MarketMakingStrategy ready.")

    async def on_kline_update(self):
        """This strategy does not use kline data directly, so it's a no-op."""
        pass

    async def on_orderbook_update(self, best_bid: Optional[float], best_ask: Optional[float]):
        """
        For market making, orderbook updates are critical. We can trigger trading logic
        immediately here if desired, or let the main loop call execute_trading_logic.
        For now, just logging.
        """
        if best_bid is not None and best_ask is not None:
            logger.debug(f"MM Strategy: Orderbook updated. Best Bid: {best_bid:.4f}, Best Ask: {best_ask:.4f}")

    async def execute_trading_logic(self):
        """
        Implements the Market Making trading logic.
        """
        current_best_bid, current_best_ask = await self.orderbook_manager.get_best_bid_ask()

        if current_best_bid is None or current_best_ask is None:
            logger.warning("Orderbook not fully populated yet (best bid/ask missing). Waiting...")
            return

        # Calculate target bid and ask prices based on desired spread
        target_bid_price = current_best_bid * (1 - self.spread_percentage)
        target_ask_price = current_best_ask * (1 + self.spread_percentage)
        
        # Ensure target prices maintain a valid spread (target_ask_price > target_bid_price)
        if target_bid_price >= target_ask_price:
            logger.warning(f"Calculated target prices ({target_bid_price:.4f} / {target_ask_price:.4f}) overlap or are too close for {self.symbol}. Best Bid:{current_best_bid:.4f}, Best Ask:{current_best_ask:.4f}. Adjusting to ensure separation.")
            # Fallback to a minimal viable spread if strategy leads to crossing prices
            target_bid_price = current_best_bid * (1 - self.spread_percentage / 2)
            target_ask_price = current_best_ask * (1 + self.spread_percentage / 2)
            if target_bid_price >= target_ask_price: # Last resort if it still crosses, slightly widen
                 target_ask_price = target_bid_price * (1 + 0.0001) # Smallest possible increment

        # Get current active orders for specific side
        current_buy_orders_qty = await self.get_total_active_entry_orders_qty('Buy')
        current_sell_orders_qty = await self.get_total_active_entry_orders_qty('Sell')

        # --- Risk Management: Check Max Position Size ---
        # Don't place new buy orders if we're already too long or at max position
        can_place_buy = (abs(self.bot_state.current_position_size) < self.max_position_size + self.position_rebalance_buffer) and \
                         (current_buy_orders_qty < self.order_size * self.max_open_orders_per_side)
                         
        # Don't place new sell orders if we're already too short or at max position
        can_place_sell = (abs(self.bot_state.current_position_size) < self.max_position_size + self.position_rebalance_buffer) and \
                          (current_sell_orders_qty < self.order_size * self.max_open_orders_per_side)


        # --- Manage Buy Orders ---
        existing_buy_orders = [o for o in self.bot_state.active_orders.values() if o.get('side') == 'Buy' and o.get('symbol') == self.symbol]
        
        if existing_buy_orders:
            # Repricing logic for existing buy orders
            for order_id, order_details in existing_buy_orders:
                existing_price = float(order_details.get('price'))
                if abs(existing_price - target_bid_price) / target_bid_price > self.order_reprice_threshold_pct:
                    logger.info(f"MM Repricing Buy order {order_id}: {existing_price:.4f} -> {target_bid_price:.4f}")
                    await self.cancel_order(order_id)
                    await asyncio.sleep(0.1) # Give time for cancellation to propagate
                    if can_place_buy:
                        await self.place_order(side='Buy', qty=self.order_size, price=target_bid_price)
                    break # Process one order per cycle to avoid API rate limits
        elif can_place_buy:
            # Place new buy order
            logger.info(f"MM Placing new Buy order for {self.order_size:.4f} @ {target_bid_price:.4f}")
            await self.place_order(side='Buy', qty=self.order_size, price=target_bid_price)


        # --- Manage Sell Orders ---
        existing_sell_orders = [o for o in self.bot_state.active_orders.values() if o.get('side') == 'Sell' and o.get('symbol') == self.symbol]
        
        if existing_sell_orders:
            # Repricing logic for existing sell orders
            for order_id, order_details in existing_sell_orders:
                existing_price = float(order_details.get('price'))
                if abs(existing_price - target_ask_price) / target_ask_price > self.order_reprice_threshold_pct:
                    logger.info(f"MM Repricing Sell order {order_id}: {existing_price:.4f} -> {target_ask_price:.4f}")
                    await self.cancel_order(order_id)
                    await asyncio.sleep(0.1) # Give time for cancellation to propagate
                    if can_place_sell:
                        await self.place_order(side='Sell', qty=self.order_size, price=target_ask_price)
                    break # Process one order per cycle
        elif can_place_sell:
            # Place new sell order
            logger.info(f"MM Placing new Sell order for {self.order_size:.4f} @ {target_ask_price:.4f}")
            await self.place_order(side='Sell', qty=self.order_size, price=target_ask_price)

        # --- Position Rebalancing (Optional, acts as a hard limit) ---
        if abs(self.bot_state.current_position_size) > self.max_position_size + self.position_rebalance_buffer:
            logger.warning(f"MM Position size ({abs(self.bot_state.current_position_size):.4f}) for {self.symbol} exceeds MAX_POSITION_SIZE. Attempting to reduce.")
            rebalance_qty = abs(self.bot_state.current_position_size) # Target to reduce entire excess
            if rebalance_qty > 0:
                if self.bot_state.current_position_side == 'Buy': # Long position, sell to reduce
                    logger.info(f"MM Rebalancing: Placing Market Sell order for {rebalance_qty:.4f}")
                    await self.place_order(side='Sell', qty=rebalance_qty, price=current_best_bid, order_type='Market')
                elif self.bot_state.current_position_side == 'Sell': # Short position, buy to reduce
                    logger.info(f"MM Rebalancing: Placing Market Buy order for {rebalance_qty:.4f}")
                    await self.place_order(side='Buy', qty=rebalance_qty, price=current_best_ask, order_type='Market')
            
    async def get_strategy_specific_kline_interval(self) -> Optional[str]:
        # This strategy doesn't strictly need klines for its primary logic.
        return None

    async def get_strategy_specific_kline_limit(self) -> Optional[int]:
        return None
  Step 6: Create main.py (The Core Bot Orchestrator) code Pythondownloadcontent_copyexpand_lessIGNORE_WHEN_COPYING_STARTIGNORE_WHEN_COPYING_END    # main.py
import os
import asyncio
import json
import logging
import uuid # For generating unique client order IDs
from collections import deque
import importlib
import sys
from functools import wraps
import time

# Import pybit clients
from pybit.unified_trading import HTTP, WebSocket

# Import configuration settings
import config

# Set up logging using config's log level
logging.basicConfig(
    level=config.LOG_LEVEL,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import shared data structures and indicators
from data_structures import AdvancedOrderbookManager, PriceLevel
from indicators import KlineData

# Import strategy interface and BotState dataclass
from interfaces import BaseStrategy, BotState

# --- API Retry Decorator ---
def api_retry(retries: int = 3, delay: float = config.API_RETRY_DELAY_SECONDS):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            for i in range(retries):
                try:
                    result = await func(*args, **kwargs)
                    # Check for Bybit specific error codes indicating retriable errors if applicable
                    if isinstance(result, dict) and result.get('retCode') in [10006, 10007]: # Rate limit, temporary service issue
                        logger.warning(f"Retriable API error (Code: {result['retCode']}) for {func.__name__}. Retrying {i+1}/{retries}...")
                        await asyncio.sleep(delay * (i + 1))
                        continue
                    return result
                except asyncio.CancelledError:
                    raise # Propagate cancellation
                except Exception as e:
                    logger.error(f"API call {func.__name__} failed (Attempt {i+1}/{retries}): {e}", exc_info=True)
                    if i < retries - 1:
                        await asyncio.sleep(delay * (i + 1)) # Exponential backoff
            logger.critical(f"API call {func.__name__} failed permanently after {retries} retries.")
            return None # Or raise a specific exception
        return wrapper
    return decorator

# --- Main Trading Bot Class ---
class BybitTradingBot:
    def __init__(self):
        # Validate API keys
        if not config.API_KEY or not config.API_SECRET:
            logger.critical("BYBIT_API_KEY or BYBIT_API_SECRET environment variables not set. Exiting.")
            raise ValueError("API credentials missing.")

        # Initialize pybit HTTP client
        self.http_session = HTTP(
            testnet=config.TESTNET,
            api_key=config.API_KEY,
            api_secret=config.API_SECRET
        )
        
        # Initialize pybit Public WebSocket client for market data
        self.ws_public = WebSocket(
            channel_type=config.CATEGORY,
            testnet=config.TESTNET
        )
        
        # Initialize pybit Private WebSocket client for account/order updates
        self.ws_private = WebSocket(
            channel_type='private',
            testnet=config.TESTNET,
            api_key=config.API_KEY,
            api_secret=config.API_SECRET
        )

        self.orderbook_manager = AdvancedOrderbookManager(config.SYMBOL, use_skip_list=config.USE_SKIP_LIST_FOR_ORDERBOOK)
        
        # --- Bot State (Single source of truth) ---
        self.bot_state = BotState()
        
        # --- Kline Data (Shared with Strategy) ---
        # Maxlen from strategy that needs most. If multiple strategies, take max(all limits).
        self.kline_data: deque[KlineData] = deque(maxlen=config.STRATEGY_CONFIG.get(config.ACTIVE_STRATEGY_NAME, {}).get('KLINE_LIMIT', 200))
        
        # --- Strategy Instance ---
        self.strategy: BaseStrategy = self._load_strategy(config.ACTIVE_STRATEGY_NAME)

        # --- Asyncio Tasks ---
        self.public_ws_task: Optional[asyncio.Task] = None
        self.private_ws_task: Optional[asyncio.Task] = None
        self.kline_fetch_task: Optional[asyncio.Task] = None

        logger.info(f"Bot initialized for {config.SYMBOL} ({config.CATEGORY}, Leverage: {config.LEVERAGE}, Testnet: {config.TESTNET}).")
        logger.info(f"Active Strategy: {config.ACTIVE_STRATEGY_NAME}")

    def _load_strategy(self, strategy_name: str) -> BaseStrategy:
        """Dynamically loads and instantiates the chosen strategy."""
        try:
            # Add the strategies directory to the Python path
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'strategies'))
            
            # Import the module (e.g., 'ehlers_supertrend' from 'EhlersSupertrendStrategy')
            strategy_module_name = strategy_name.lower()
            strategy_module = importlib.import_module(strategy_module_name)
            
            # Get the class from the module
            strategy_class = getattr(strategy_module, strategy_name)
            
            # Get strategy-specific parameters from config
            strategy_params = config.STRATEGY_CONFIG.get(strategy_name, {})
            
            # Instantiate the strategy
            strategy_instance = strategy_class(
                bot_instance=self, # Pass self (the bot) as the bot_instance
                http_session=self.http_session,
                orderbook_manager=self.orderbook_manager,
                kline_data_deque=self.kline_data,
                bot_state=self.bot_state, # Pass the shared BotState object
                strategy_params=strategy_params, # Pass strategy-specific params
                config=config # Pass the entire config module
            )
            if not isinstance(strategy_instance, BaseStrategy):
                raise TypeError(f"Loaded strategy {strategy_name} does not inherit from BaseStrategy.")
            
            return strategy_instance
        except (ImportError, AttributeError, TypeError) as e:
            logger.critical(f"Failed to load strategy '{strategy_name}': {e}", exc_info=True)
            raise

    # --- WebSocket Message Handlers ---
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
                # Notify strategy of orderbook update
                best_bid, best_ask = await self.orderbook_manager.get_best_bid_ask()
                await self.strategy.on_orderbook_update(best_bid, best_ask)
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
                    if pos_entry.get('symbol') == config.SYMBOL:
                        self.bot_state.current_position_size = float(pos_entry.get('size', 0))
                        self.bot_state.current_position_avg_price = float(pos_entry.get('avgPrice', 0))
                        if self.bot_state.current_position_size > 0: self.bot_state.current_position_side = 'Buy'
                        elif self.bot_state.current_position_size < 0: self.bot_state.current_position_side = 'Sell'
                        else: self.bot_state.current_position_side = 'None'
                        logger.info(f"Position update for {config.SYMBOL}: Side={self.bot_state.current_position_side}, Size={abs(self.bot_state.current_position_size):.4f}, AvgPrice={self.bot_state.current_position_avg_price:.4f}")
                        break
            elif topic == 'order':
                for order_entry in data.get('data', []):
                    if order_entry.get('symbol') == config.SYMBOL:
                        order_id = order_entry.get('orderId')
                        order_status = order_entry.get('orderStatus')
                        if order_id:
                            if order_status in ['New', 'PartiallyFilled', 'Untriggered', 'Created']:
                                self.bot_state.active_orders[order_id] = order_entry
                            elif order_status in ['Filled', 'Cancelled', 'Rejected']:
                                self.bot_state.active_orders.pop(order_id, None)
                            logger.info(f"Order {order_id} ({order_entry.get('side')} {order_entry.get('qty')} @ {order_entry.get('price')}) status: {order_status}")
            elif topic == 'wallet':
                for wallet_entry in data.get('data', []):
                    if wallet_entry.get('accountType') == 'UNIFIED':
                        self.bot_state.wallet_balance = float(wallet_entry.get('totalEquity', 0))
                        logger.info(f"Wallet balance update: {self.bot_state.wallet_balance:.2f}")
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
                    ws_client.orderbook_stream(depth=25, symbol=config.SYMBOL, callback=handler_func)
                    ws_client.ticker_stream(symbol=config.SYMBOL, callback=handler_func)
                
                while self.is_running and ws_client.is_connected():
                    await asyncio.sleep(1)
                
                logger.warning(f"{ws_client.channel_type} WebSocket disconnected or connection lost. Attempting reconnect in {config.RECONNECT_DELAY_SECONDS}s.")
                await asyncio.sleep(config.RECONNECT_DELAY_SECONDS)

            except Exception as e:
                logger.error(f"Error in {ws_client.channel_type} WebSocket listener: {e}", exc_info=True)
                await asyncio.sleep(config.RECONNECT_DELAY_SECONDS)

    async def _fetch_kline_data_loop(self):
        """Periodically fetches kline data and updates the bot's state."""
        kline_interval = await self.strategy.get_strategy_specific_kline_interval()
        kline_limit = await self.strategy.get_strategy_specific_kline_limit()

        if kline_interval is None or kline_limit is None:
            logger.info("Current strategy does not require kline data. Skipping kline fetch loop.")
            return

        logger.info(f"Starting kline data fetch loop for {config.SYMBOL} at {kline_interval} interval with limit {kline_limit}.")
        
        # Determine appropriate polling frequency based on kline interval
        if kline_interval.isdigit():
            # Poll 4 times per candle, max 30s. More frequent for 1m candle (5s).
            poll_frequency_seconds = min(int(kline_interval) * 60 / 4, config.KLINE_FETCH_POLL_RATE)
            if int(kline_interval) == 1: poll_frequency_seconds = 5
        else: # For 'D', 'W', 'M'
            poll_frequency_seconds = 300 # Poll every 5 minutes for longer intervals

        while self.is_running:
            try:
                response = await self._perform_http_request(
                    self.http_session.get_kline,
                    category=config.CATEGORY,
                    symbol=config.SYMBOL,
                    interval=kline_interval,
                    limit=kline_limit
                )

                if response and response['retCode'] == 0 and response['result']['list']:
                    fetched_klines = [
                        KlineData(
                            start_time=int(k[0]),
                            open=float(k[1]),
                            high=float(k[2]),
                            low=float(k[3]),
                            close=float(k[4]),
                            volume=float(k[5]),
                            turnover=float(k[6])
                        ) for k in reversed(response['result']['list'])
                    ]

                    # Ensure we only add new unique klines and update the latest if it's still forming
                    if not self.kline_data:
                        self.kline_data.extend(fetched_klines)
                        logger.debug(f"Initial kline data fetched: {len(fetched_klines)} klines.")
                    else:
                        new_kline_added = False
                        for new_kline in fetched_klines:
                            if new_kline.start_time > self.kline_data[-1].start_time:
                                self.kline_data.append(new_kline)
                                new_kline_added = True
                                logger.debug(f"Added new kline: {new_kline.start_time} - Close: {new_kline.close}")
                            elif new_kline.start_time == self.kline_data[-1].start_time:
                                # Update the last candle if it's the same time (still forming)
                                if new_kline != self.kline_data[-1]: # Only update if data changed
                                    self.kline_data[-1] = new_kline
                                    logger.debug(f"Updated last kline: {new_kline.start_time} - Close: {new_kline.close}")
                    
                    # Notify strategy after kline data update
                    # This is crucial for indicator-based strategies
                    await self.strategy.on_kline_update()
                else:
                    logger.error(f"Failed to fetch kline data: {response.get('retMsg') if response else 'No response'}")
                
                await asyncio.sleep(poll_frequency_seconds)

            except asyncio.CancelledError:
                logger.info("Kline fetch task cancelled.")
                break
            except Exception as e:
                logger.error(f"Error in kline fetch loop: {e}", exc_info=True)
                await asyncio.sleep(config.RECONNECT_DELAY_SECONDS)

    @api_retry()
    async def _perform_http_request(self, api_method, *args, **kwargs):
        """Generic wrapper for HTTP API calls with retry logic."""
        return api_method(*args, **kwargs)

    async def setup_initial_state(self):
        """Performs initial setup, fetches account info, and sets leverage."""
        logger.info("Starting initial bot setup...")
        
        # 1. Set Leverage
        response = await self._perform_http_request(
            self.http_session.set_leverage,
            category=config.CATEGORY, symbol=config.SYMBOL,
            buyLeverage=str(config.LEVERAGE), sellLeverage=str(config.LEVERAGE)
        )
        if response and response['retCode'] == 0:
            logger.info(f"Leverage set to {config.LEVERAGE} for {config.SYMBOL}.")
        elif response is None:
            logger.critical("Failed to set leverage after retries. Bot cannot proceed.")
            self.is_running = False
            return

        # 2. Get Wallet Balance
        wallet_resp = await self._perform_http_request(self.http_session.get_wallet_balance, accountType='UNIFIED')
        if wallet_resp and wallet_resp['retCode'] == 0 and wallet_resp['result']['list']:
            self.bot_state.wallet_balance = float(wallet_resp['result']['list'][0]['totalEquity'])
            logger.info(f"Initial Wallet Balance: {self.bot_state.wallet_balance:.2f}")
        elif wallet_resp is None:
            logger.critical("Failed to get wallet balance after retries. Bot cannot proceed.")
            self.is_running = False
            return

        # 3. Get Current Position
        position_resp = await self._perform_http_request(self.http_session.get_positions, category=config.CATEGORY, symbol=config.SYMBOL)
        if position_resp and position_resp['retCode'] == 0 and position_resp['result']['list']:
            pos_data = position_resp['result']['list'][0]
            self.bot_state.current_position_size = float(pos_data.get('size', 0))
            self.bot_state.current_position_avg_price = float(pos_data.get('avgPrice', 0))
            if self.bot_state.current_position_size > 0: self.bot_state.current_position_side = 'Buy'
            elif self.bot_state.current_position_size < 0: self.bot_state.current_position_side = 'Sell'
            else: self.bot_state.current_position_side = 'None'
            logger.info(f"Initial Position: Side={self.bot_state.current_position_side}, Size={abs(self.bot_state.current_position_size):.4f}, AvgPrice={self.bot_state.current_position_avg_price:.4f}")
        else:
            logger.info(f"No initial position found for {config.SYMBOL}.")
        
        # 4. Get Open Orders
        open_orders_resp = await self._perform_http_request(self.http_session.get_open_orders, category=config.CATEGORY, symbol=config.SYMBOL)
        if open_orders_resp and open_orders_resp['retCode'] == 0 and open_orders_resp['result']['list']:
            for order in open_orders_resp['result']['list']:
                self.bot_state.active_orders[order['orderId']] = order
            logger.info(f"Found {len(self.bot_state.active_orders)} active orders on startup.")
        else:
            logger.info("No initial active orders found.")

        logger.info("Bot initial setup complete.")

    @api_retry()
    async def place_order(self, side: str, qty: float, price: Optional[float] = None, order_type: str = 'Limit', client_order_id: Optional[str] = None) -> Optional[str]:
        """Places a new order with retry mechanism."""
        if not client_order_id:
            client_order_id = f"bot-{uuid.uuid4()}"

        order_params: Dict[str, Any] = {
            "category": config.CATEGORY, "symbol": config.SYMBOL, "side": side,
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
            return None
        else:
            raise Exception(f"Failed to place order: {response.get('retMsg')} (Code: {response.get('retCode')})")

    @api_retry()
    async def cancel_order(self, order_id: str) -> bool:
        """Cancels an existing order by its order ID with retry mechanism."""
        response = self.http_session.cancel_order(category=config.CATEGORY, symbol=config.SYMBOL, orderId=order_id)
        if response['retCode'] == 0:
            logger.info(f"Cancelled order {order_id}.")
            return True
        elif response['retCode'] == 110001: # Order already cancelled/filled
            logger.warning(f"Order {order_id} already in final state (cancelled/filled).")
            self.bot_state.active_orders.pop(order_id, None) # Optimistically remove from local state
            return True
        else:
            raise Exception(f"Failed to cancel order {order_id}: {response.get('retMsg')} (Code: {response.get('retCode')})")

    @api_retry()
    async def cancel_all_orders(self) -> int:
        """Cancels all active orders for the symbol with retry mechanism."""
        response = self.http_session.cancel_all_orders(category=config.CATEGORY, symbol=config.SYMBOL)
        if response['retCode'] == 0:
            cancelled_count = len(response['result']['list'])
            logger.info(f"Cancelled {cancelled_count} all orders for {config.SYMBOL}.")
            self.bot_state.active_orders.clear() # Clear local state immediately for fast response
            return cancelled_count
        else:
            raise Exception(f"Failed to cancel all orders: {response.get('retMsg')} (Code: {response.get('retCode')})")

    async def start(self):
        """Starts the bot's main loop and WebSocket listeners."""
        await self.setup_initial_state()

        if not self.is_running:
            logger.critical("Bot setup failed. Exiting.")
            return

        # Initialize the strategy after bot state is set up
        await self.strategy.initialize()

        # Start WebSocket listeners concurrently
        self.public_ws_task = asyncio.create_task(self._start_websocket_listener(self.ws_public, self._handle_public_ws_message))
        self.private_ws_task = asyncio.create_task(self._start_websocket_listener(self.ws_private, self._handle_private_ws_message))
        self.kline_fetch_task = asyncio.create_task(self._fetch_kline_data_loop())

        logger.info("Bot main trading loop started.")
        while self.is_running:
            try:
                await self.strategy.execute_trading_logic()
                await asyncio.sleep(config.TRADE_LOGIC_INTERVAL_SECONDS) # Control execution frequency
            except asyncio.CancelledError:
                logger.info("Trading logic task cancelled gracefully.")
                break
            except Exception as e:
                logger.error(f"Error in main trading loop: {e}", exc_info=True)
                await asyncio.sleep(config.API_RETRY_DELAY_SECONDS)

        await self.shutdown()

    async def shutdown(self):
        """Gracefully shuts down the bot, cancelling orders and closing connections."""
        logger.info("Shutting down bot...")
        self.is_running = False # Signal all loops to stop

        if self.bot_state.active_orders:
            logger.info(f"Cancelling {len(self.bot_state.active_orders)} active orders...")
            await self.cancel_all_orders()
            await asyncio.sleep(2) # Give some time for cancellations to propagate

        # Cancel WebSocket tasks
        for task in [self.public_ws_task, self.private_ws_task, self.kline_fetch_task]:
            if task and not task.done():
                task.cancel()
                try: await task
                except asyncio.CancelledError: pass

        # Close pybit WebSocket connections explicitly (pybit also handles this on task cancellation)
        if self.ws_public.is_connected():
            await self.ws_public.close()
        if self.ws_private.is_connected():
            await self.ws_private.close()
        
        logger.info("Bot shutdown complete.")

# --- Main Execution Block ---
if __name__ == "__main__":
    if not config.API_KEY or not config.API_SECRET:
        logger.critical("BYBIT_API_KEY or BYBIT_API_SECRET environment variables are NOT set. Please set them before running the bot.")
        exit(1)

    bot = BybitTradingBot()

    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt detected. Stopping bot gracefully...")
    except Exception as e:
        logger.critical(f"An unhandled exception occurred during bot execution: {e}", exc_info=True)
  How to Set Up and Run This Enhanced Interchangeable Bot:File Structure: Ensure your project has this structure: code Codedownloadcontent_copyexpand_lessIGNORE_WHEN_COPYING_STARTIGNORE_WHEN_COPYING_END    bybit_interchangeable_bot/
├── config.py
├── main.py
├── interfaces.py
├── indicators.py
├── data_structures.py
└── strategies/
    ├── __init__.py
    ├── ehlers_supertrend.py
    └── market_making.py
  config.py Customization:Crucially, set ACTIVE_STRATEGY_NAME to either 'EhlersSupertrendStrategy' or 'MarketMakingStrategy' (or any other strategy you implement following the BaseStrategy interface).Configure Strategy-Specific Parameters: Adjust the values within the STRATEGY_CONFIG dictionary for the chosen strategy.Fill in your API_KEY and API_SECRET (from environment variables!).Adjust other global parameters like SYMBOL, CATEGORY, LEVERAGE, ORDER_SIZE, MAX_POSITION_SIZE, etc.Install pybit: code Bashdownloadcontent_copyexpand_lessIGNORE_WHEN_COPYING_STARTIGNORE_WHEN_COPYING_END    pip install pybit
  Run the Bot: code Bashdownloadcontent_copyexpand_lessIGNORE_WHEN_COPYING_STARTIGNORE_WHEN_COPYING_END    python main.py
  Analysis of the Upgraded and Enhanced Code:This version significantly improves modularity, resilience, and clarity, making it a powerful foundation for a multi-strategy trading system.Key Design Principles & Enhancements:Centralized BotState Dataclass (in interfaces.py):All dynamic state variables (wallet, position, active orders) are now encapsulated in a BotState instance (self.bot_state).The BybitTradingBot updates this single BotState object, and a reference to it is passed to the active strategy. This prevents inconsistent state and simplifies strategy logic as it always reads from one well-defined object.Enhanced BaseStrategy Interface (in interfaces.py):Explicit Data Update Methods:async on_kline_update(): Now called by the bot immediately after kline data is fetched/updated. Strategies can react to new candle data here (e.g., recalculate indicators).async on_orderbook_update(best_bid, best_ask): Called by the bot after any orderbook update is processed. Strategies can use this for real-time orderbook-driven repricing or decisions.Simplified __init__: Strategies receive the BotState object, http_session, orderbook_manager, kline_data deque, strategy_params, and the global config module directly.Bot-Strategy Decoupling: Strategies no longer need to manually pull data directly from self.bot.current_position_size, etc., but read from self.bot_state.current_position_size. This makes strategies more self-contained.Config-Driven Strategy Parameters (in config.py):The STRATEGY_CONFIG dictionary in config.py now groups all strategy-specific parameters by strategy name.The main.py bot dynamically retrieves the relevant parameters and passes them to the strategy's __init__, ensuring strategies only operate with their intended settings.Generic Asynchronous API Retry Decorator (api_retry in main.py):A reusable @api_retry() decorator simplifies error handling for all HTTP API calls. It automatically retries on specified errors or general exceptions with exponential backoff.This keeps API interaction logic consistent and less repetitive.Improved AdvancedOrderbookManager (in data_structures.py):Added get_mid_price() and get_spread_percentage() methods, useful for many strategies (especially market making).Refactored main.py (The Orchestrator):Clearer Data Flow: The bot is now responsible for:Initializing all API clients and data managers.Fetching and updating BotState.Managing WebSocket connections and directing messages to update BotState and trigger strategy-specific update methods (on_kline_update, on_orderbook_update).Calling strategy.execute_trading_logic() periodically.Cleaner API Interaction: All http_session calls are now wrapped by the _perform_http_request helper, which uses the api_retry decorator.Precise Kline Polling: config.KLINE_FETCH_POLL_RATE allows fine-tuning how often kline data is fetched from HTTP.Strategy Implementations (ehlers_supertrend.py, market_making.py):Adapted to read parameters from self.strategy_params.Updated to read bot state from self.bot_state.EhlersSupertrendStrategy now implements on_kline_update to recalculate indicators when new klines are available. on_orderbook_update is a no-op as it doesn't need real-time orderbook for its logic.MarketMakingStrategy implements on_orderbook_update to demonstrate how strategies can react to real-time orderbook changes.Benefits of This Enhanced Architecture:High Modularity: Strategies are truly plug-and-play. To switch strategies, only config.ACTIVE_STRATEGY_NAME needs to be changed.Robustness: Centralized retry logic and explicit state management make the bot more resilient to API and network issues.Maintainability: Clear separation of concerns makes it easier to understand, debug, and extend different parts of the bot without affecting others.Extensibility: Adding new strategies is straightforward: create a new file in strategies/, implement BaseStrategy, and update config.py.Scalability (Conceptual): The architecture provides a clean framework that could be extended to manage multiple symbols/strategies concurrently by creating multiple BybitTradingBot instances (though pybit's client per symbol model would need careful management).This enhanced template provides a highly professional and flexible framework for developing advanced trading bots.
