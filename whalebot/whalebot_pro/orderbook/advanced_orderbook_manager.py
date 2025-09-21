
import asyncio
import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, Generic, List, Optional, Tuple, TypeVar

# Color Scheme (for logging)
from colorama import Fore, Style
NEON_RED = Fore.LIGHTRED_EX
NEON_YELLOW = Fore.YELLOW
NEON_GREEN = Fore.LIGHTGREEN_EX
NEON_BLUE = Fore.CYAN
RESET = Style.RESET_ALL

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
    """
    Manages the orderbook for a single symbol using either OptimizedSkipList or EnhancedHeap.
    Provides thread-safe (asyncio-safe) operations, snapshot/delta processing,
    and access to best bid/ask.
    """
    def __init__(self, symbol: str, logger: logging.Logger, use_skip_list: bool = True):
        self.symbol = symbol
        self.logger = logger
        self.use_skip_list = use_skip_list
        self._lock = asyncio.Lock()
        
        if use_skip_list:
            self.logger.info(f"OrderbookManager for {symbol}: Using OptimizedSkipList.")
            self.bids_ds = OptimizedSkipList[float, PriceLevel]()
            self.asks_ds = OptimizedSkipList[float, PriceLevel]()
        else:
            self.logger.info(f"OrderbookManager for {symbol}: Using EnhancedHeap.")
            self.bids_ds = EnhancedHeap(is_max_heap=True)
            self.asks_ds = EnhancedHeap(is_max_heap=False)
        
        self.last_update_id: int = 0

from contextlib import asynccontextmanager

from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _lock_context(self):
        async with self._lock:
            yield

    async def _validate_price_quantity(self, price: float, quantity: float) -> bool:
        if not (isinstance(price, (int, float)) and isinstance(quantity, (int, float))):
            self.logger.error(f"Invalid type for price or quantity for {self.symbol}. Price: {type(price)}, Qty: {type(quantity)}")
            return False
        if price < 0 or quantity < 0:
            self.logger.error(f"Negative price or quantity detected for {self.symbol}: price={price}, quantity={quantity}")
            return False
        return True

    async def update_snapshot(self, data: Dict[str, Any]) -> None:
        async with self._lock_context():
            if not isinstance(data, dict) or 'b' not in data or 'a' not in data or 'u' not in data:
                self.logger.error(f"Invalid snapshot data format for {self.symbol}: {data}")
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
                        if self.use_skip_list: self.bids_ds.insert(price, level)
                        else: self.bids_ds.insert(level)
                except (ValueError, TypeError) as e:
                    self.logger.error(f"Failed to parse bid in snapshot for {self.symbol}: {price_str}/{qty_str}, error={e}")

            for price_str, qty_str in data.get('a', []):
                try:
                    price = float(price_str)
                    quantity = float(qty_str)
                    if await self._validate_price_quantity(price, quantity) and quantity > 0:
                        level = PriceLevel(price, quantity, int(time.time() * 1000))
                        if self.use_skip_list: self.asks_ds.insert(price, level)
                        else: self.asks_ds.insert(level)
                except (ValueError, TypeError) as e:
                    self.logger.error(f"Failed to parse ask in snapshot for {self.symbol}: {price_str}/{qty_str}, error={e}")
            
            self.last_update_id = data.get('u', 0)
            self.logger.info(f"Orderbook {self.symbol} snapshot updated. Last Update ID: {self.last_update_id}")

    async def update_delta(self, data: Dict[str, Any]) -> None:
        async with self._lock_context():
            if not isinstance(data, dict) or not ('b' in data or 'a' in data) or 'u' not in data:
                self.logger.error(f"Invalid delta data format for {self.symbol}: {data}")
                return

            current_update_id = data.get('u', 0)
            if current_update_id <= self.last_update_id:
                self.logger.debug(f"Outdated OB update for {self.symbol}: current={current_update_id}, last={self.last_update_id}. Skipping.")
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
                        if self.use_skip_list: self.bids_ds.insert(price, level)
                        else: self.bids_ds.insert(level)
                except (ValueError, TypeError) as e:
                    self.logger.error(f"Failed to parse bid delta for {self.symbol}: {price_str}/{qty_str}, error={e}")

            for price_str, qty_str in data.get('a', []):
                try:
                    price = float(price_str)
                    quantity = float(qty_str)
                    if not await self._validate_price_quantity(price, quantity): continue

                    if quantity == 0.0:
                        self.asks_ds.delete(price) if self.use_skip_list else self.asks_ds.remove(price)
                    else:
                        level = PriceLevel(price, quantity, int(time.time() * 1000))
                        if self.use_skip_list: self.asks_ds.insert(price, level)
                        else: self.asks_ds.insert(level)
                except (ValueError, TypeError) as e:
                    self.logger.error(f"Failed to parse ask delta for {self.symbol}: {price_str}/{qty_str}, error={e}")
            
            self.last_update_id = current_update_id
            self.logger.debug(f"Orderbook {self.symbol} delta applied. Last Update ID: {self.last_update_id}")

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
