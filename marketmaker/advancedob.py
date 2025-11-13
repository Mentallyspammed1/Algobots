"""
Bybit Orderbook Helper: Integrates Advanced Orderbook Management with pybit WebSocket streams.
Provides real-time, validated, and sorted orderbook data for a given symbol.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cached_property
from typing import Any, Generic, TypeVar

# Import pybit clients for interaction with Bybit API
from pybit.unified_trading import HTTP, WebSocket

# Configure logging for the entire module
logging.basicConfig(
    level=logging.INFO,  # Set to logging.DEBUG for more verbose internal messages
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Type variables for generic data structures
KT = TypeVar("KT")
VT = TypeVar("VT")


@dataclass(slots=True)
class PriceLevel:
    """
    Price level with metadata, optimized for memory with slots.
    Represents an aggregated price level in the orderbook.
    """

    price: float
    quantity: float
    timestamp: int
    order_count: int = (
        1  # Number of individual orders at this price level (optional, for tracking)
    )

    def __lt__(self, other: PriceLevel) -> bool:
        """Compares PriceLevel objects based on price."""
        return self.price < other.price

    def __eq__(self, other: PriceLevel) -> bool:
        """Compares PriceLevel objects for equality, considering float precision."""
        return abs(self.price - other.price) < 1e-8


class OptimizedSkipList(Generic[KT, VT]):
    """
    Enhanced Skip List implementation with O(log n) insert/delete/search operations.
    Maintains sorted order of keys and associated values.
    """

    class Node(Generic[KT, VT]):
        """Node structure for the Skip List."""

        def __init__(self, key: KT, value: VT, level: int):
            self.key = key
            self.value = value
            # forward[i] is pointer to next node in i-th level
            self.forward: list[OptimizedSkipList.Node | None] = [None] * (level + 1)
            self.level = level

    def __init__(self, max_level: int = 16, p: float = 0.5):
        """
        Initializes the Skip List.
        :param max_level: Maximum level for a node in the skip list.
        :param p: Probability of a node having a higher level.
        """
        self.max_level = max_level
        self.p = p
        self.level = 0  # Current level of the skip list
        # Header node acts as the start of all levels
        self.header = self.Node(None, None, max_level)
        self._size = 0  # Current number of elements in the skip list

    def _random_level(self) -> int:
        """
        Generates a random level for a new node based on probability 'p'.
        """
        level = 0
        while level < self.max_level and random.random() < self.p:
            level += 1
        return level

    def insert(self, key: KT, value: VT) -> None:
        """
        Inserts a key-value pair into the Skip List with O(log n) average complexity.
        If the key already exists, its value is updated.
        """
        update = [None] * (self.max_level + 1)
        current = self.header

        # Start from the highest level and work downwards
        for i in range(self.level, -1, -1):
            while (
                current.forward[i]
                and current.forward[i].key is not None
                and current.forward[i].key < key
            ):
                current = current.forward[i]
            update[i] = current  # Store previous node at current level

        # Move to the first level to find the insertion point
        current = current.forward[0]

        # If key already exists, update its value
        if current and current.key == key:
            current.value = value
            return

        # Generate a random level for the new node
        new_level = self._random_level()
        # If new node's level is greater than current skip list level, update header pointers
        if new_level > self.level:
            for i in range(self.level + 1, new_level + 1):
                update[i] = self.header
            self.level = new_level

        # Create new node and insert it into the skip list
        new_node = self.Node(key, value, new_level)
        for i in range(new_level + 1):
            new_node.forward[i] = update[i].forward[i]
            update[i].forward[i] = new_node

        self._size += 1

    def delete(self, key: KT) -> bool:
        """
        Deletes a key-value pair from the Skip List with O(log n) average complexity.
        :return: True if the key was found and deleted, False otherwise.
        """
        update = [None] * (self.max_level + 1)
        current = self.header

        for i in range(self.level, -1, -1):
            while (
                current.forward[i]
                and current.forward[i].key is not None
                and current.forward[i].key < key
            ):
                current = current.forward[i]
            update[i] = current

        current = current.forward[0]
        if not current or current.key != key:
            return False  # Key not found

        # Remove node from all levels it is part of
        for i in range(self.level + 1):
            if update[i].forward[i] != current:
                break  # Node is not present at this level or higher
            update[i].forward[i] = current.forward[i]

        # Decrease level of skip list if no more nodes at current highest level
        while self.level > 0 and not self.header.forward[self.level]:
            self.level -= 1

        self._size -= 1
        return True

    def search(self, key: KT) -> VT | None:
        """
        Searches for a key in the Skip List with O(log n) average complexity.
        :return: The value associated with the key, or None if not found.
        """
        current = self.header
        for i in range(self.level, -1, -1):
            while (
                current.forward[i]
                and current.forward[i].key is not None
                and current.forward[i].key < key
            ):
                current = current.forward[i]

        current = current.forward[0]
        if current and current.key == key:
            return current.value
        return None

    def get_sorted_items(self, reverse: bool = False) -> list[tuple[KT, VT]]:
        """
        Retrieves all items in sorted order (ascending by default).
        :param reverse: If True, returns items in descending order.
        :return: A list of (key, value) tuples.
        """
        items = []
        current = self.header.forward[0]
        while current:
            if current.key is not None:  # Ensure it's not the header node
                items.append((current.key, current.value))
            current = current.forward[0]

        return list(reversed(items)) if reverse else items


class EnhancedHeap:
    """
    Enhanced heap implementation (Min-Heap or Max-Heap) with position tracking
    for O(log n) update and removal operations.

    Note: Using float keys directly in `position_map` can lead to precision issues
    in extreme cases. For robust production systems, consider using `decimal.Decimal`
    or quantizing float values to integers for keys.
    """

    def __init__(self, is_max_heap: bool = True):
        """
        Initializes the Enhanced Heap.
        :param is_max_heap: If True, it's a Max-Heap (largest price on top);
                            If False, it's a Min-Heap (smallest price on top).
        """
        self.heap: list[PriceLevel] = []
        self.is_max_heap = is_max_heap
        # Maps price to its index in the heap for O(1) lookup
        self.position_map: dict[float, int] = {}
        self._size = 0  # Track size for consistency with SkipList

    def _parent(self, i: int) -> int:
        return (i - 1) // 2

    def _left_child(self, i: int) -> int:
        return 2 * i + 1

    def _right_child(self, i: int) -> int:
        return 2 * i + 2

    def _compare(self, a: PriceLevel, b: PriceLevel) -> bool:
        """
        Compares two PriceLevel objects based on heap type (max or min).
        :return: True if 'a' should be higher in the heap than 'b'.
        """
        if self.is_max_heap:
            return a.price > b.price
        return a.price < b.price

    def _swap(self, i: int, j: int) -> None:
        """Swaps two elements in the heap and updates their positions in the map."""
        # Update position map first
        self.position_map[self.heap[i].price] = j
        self.position_map[self.heap[j].price] = i
        # Swap elements in the heap list
        self.heap[i], self.heap[j] = self.heap[j], self.heap[i]

    def _heapify_up(self, i: int) -> None:
        """Maintains heap property by moving element at index 'i' up the heap."""
        while i > 0:
            parent = self._parent(i)
            if not self._compare(self.heap[i], self.heap[parent]):
                break  # Correct position found
            self._swap(i, parent)
            i = parent

    def _heapify_down(self, i: int) -> None:
        """Maintains heap property by moving element at index 'i' down the heap."""
        while True:
            largest = i  # Assume current is the largest/smallest
            left = self._left_child(i)
            right = self._right_child(i)

            # Find the largest/smallest among current, left, and right children
            if left < len(self.heap) and self._compare(
                self.heap[left], self.heap[largest]
            ):
                largest = left

            if right < len(self.heap) and self._compare(
                self.heap[right], self.heap[largest]
            ):
                largest = right

            if largest == i:
                break  # Correct position found

            self._swap(i, largest)
            i = largest

    def insert(self, price_level: PriceLevel) -> None:
        """
        Inserts a new PriceLevel or updates an existing one with O(log n) complexity.
        """
        if price_level.price in self.position_map:
            idx = self.position_map[price_level.price]
            # Store old price to correctly delete from map if price itself changes (unlikely for update, but robust)
            old_price = self.heap[idx].price
            self.heap[idx] = price_level  # Update the PriceLevel object
            self.position_map[price_level.price] = (
                idx  # Ensure map points to current index
            )
            if (
                abs(old_price - price_level.price) > 1e-8
            ):  # If price actually changed (highly unusual for an "update")
                logger.warning(
                    f"Heap: Price changed for existing key {old_price} to {price_level.price}. This usually indicates a logic error or non-stable floating point values."
                )
                del self.position_map[old_price]  # Clean up old entry

            # Re-heapify from the updated position
            self._heapify_up(idx)
            self._heapify_down(idx)
        else:
            self.heap.append(price_level)
            idx = len(self.heap) - 1
            self.position_map[price_level.price] = idx
            self._heapify_up(idx)
            self._size += 1

    def extract_top(self) -> PriceLevel | None:
        """
        Extracts and removes the top element (max for Max-Heap, min for Min-Heap)
        with O(log n) complexity.
        :return: The PriceLevel object from the top of the heap, or None if heap is empty.
        """
        if not self.heap:
            return None

        top = self.heap[0]
        del self.position_map[top.price]

        if len(self.heap) == 1:
            self.heap.pop()
            self._size -= 1
            return top

        # Move the last element to the root and heapify down
        last = self.heap.pop()
        self.heap[0] = last
        self.position_map[last.price] = 0
        self._heapify_down(0)

        self._size -= 1
        return top

    def remove(self, price: float) -> bool:
        """
        Removes a specific price level from the heap with O(log n) complexity.
        :param price: The price of the PriceLevel to remove.
        :return: True if the price level was found and removed, False otherwise.
        """
        if price not in self.position_map:
            return False

        idx = self.position_map[price]
        del self.position_map[price]

        if idx == len(self.heap) - 1:
            self.heap.pop()  # If it's the last element, just remove it
            self._size -= 1
            return True

        # Replace the element to be removed with the last element
        last = self.heap.pop()
        self.heap[idx] = last
        self.position_map[last.price] = idx

        # Re-heapify from the position where the element was removed
        self._heapify_up(idx)
        self._heapify_down(idx)
        self._size -= 1
        return True


class AdvancedOrderbookManager:
    """
    Advanced orderbook manager for a single symbol, supporting both Skip List and
    Enhanced Heap for storing bids and asks. Provides thread-safe operations,
    snapshot and delta processing, and performance metrics.
    """

    def __init__(self, symbol: str, use_skip_list: bool = True, max_depth: int = 100):
        """
        Initializes the AdvancedOrderbookManager.
        :param symbol: The trading symbol (e.g., "BTCUSDT").
        :param use_skip_list: If True, uses OptimizedSkipList; otherwise, uses EnhancedHeap.
        :param max_depth: Maximum number of price levels to maintain in the orderbook.
                          (Currently not actively enforced for performance, but good for design intent).
        """
        self.symbol = symbol
        self.use_skip_list = use_skip_list
        self.max_depth = max_depth  # Limit orderbook depth (design intent, not strictly enforced for every update)
        self._lock = threading.RLock()  # Reentrant lock for thread safety

        # Initialize data structures based on configuration
        if use_skip_list:
            logger.debug(f"OrderbookManager for {symbol}: Using OptimizedSkipList.")
            self.bids = OptimizedSkipList[float, PriceLevel]()  # Bids sorted descending
            self.asks = OptimizedSkipList[float, PriceLevel]()  # Asks sorted ascending
        else:
            logger.debug(f"OrderbookManager for {symbol}: Using EnhancedHeap.")
            self.bids = EnhancedHeap(is_max_heap=True)  # Max-heap for bids
            self.asks = EnhancedHeap(is_max_heap=False)  # Min-heap for asks

        # Orderbook metadata
        self.last_update_id: int = 0
        self.last_sequence: int = 0
        self.timestamp: int = 0  # Timestamp of the last processed update

        # Performance metrics
        self.update_count: int = 0
        self.total_update_time: float = 0.0

        # Cached properties for best bid/ask (invalidated on updates)
        self._cached_best_bid: PriceLevel | None = None
        self._cached_best_ask: PriceLevel | None = None

    @contextmanager
    def _lock_context(self):
        """Context manager for acquiring and releasing the RLock."""
        with self._lock:
            yield

    def _validate_price_quantity(self, price: float, quantity: float) -> bool:
        """
        Validates if price and quantity are non-negative and numerically valid.
        :return: True if valid, False otherwise.
        """
        if not (isinstance(price, (int, float)) and isinstance(quantity, (int, float))):
            logger.error(
                f"[{self.symbol}] Invalid type for price or quantity. Price: {type(price)}, Qty: {type(quantity)}"
            )
            return False
        if price < 0 or quantity < 0:
            logger.error(
                f"[{self.symbol}] Negative price or quantity detected: price={price}, quantity={quantity}"
            )
            return False
        return True

    def _validate_sequence(self, sequence: int) -> bool:
        """
        Validates the incoming sequence number against the last known sequence.
        A return of False indicates an out-of-order or gapped update, which may
        require a full orderbook resync.
        :return: True if sequence is valid, False otherwise.
        """
        if not isinstance(sequence, int):
            logger.error(
                f"[{self.symbol}] Invalid type for sequence number: {type(sequence)}"
            )
            return False
        if sequence <= self.last_sequence:
            logger.warning(
                f"[{self.symbol}] Out-of-order sequence received: received={sequence}, last={self.last_sequence}. Skipping update."
            )
            return False
        # For a more robust check, one might verify if sequence == self.last_sequence + 1
        # If sequence > self.last_sequence + 1, it implies a gap, and a resync might be necessary.
        # Current implementation proceeds with valid sequence numbers > last_sequence.
        return True

    def process_snapshot(self, snapshot_data: dict[str, Any]) -> None:
        """
        Processes an initial orderbook snapshot, clearing existing data and
        rebuilding the orderbook.
        :param snapshot_data: Dictionary containing snapshot information ('b' for bids, 'a' for asks, 'u' for update_id, 'seq' for sequence).
        :raises ValueError: If snapshot data format is invalid or critical data is missing.
        """
        try:
            with self._lock_context():
                start_time = time.perf_counter()

                # Basic validation for snapshot structure
                if (
                    not isinstance(snapshot_data, dict)
                    or "b" not in snapshot_data
                    or "a" not in snapshot_data
                    or "u" not in snapshot_data
                ):
                    logger.error(
                        f"[{self.symbol}] Invalid snapshot data format: {snapshot_data}"
                    )
                    raise ValueError(
                        "Invalid snapshot data format: Missing bids, asks, or update_id."
                    )

                # Clear existing orderbook data by re-initializing data structures
                if self.use_skip_list:
                    self.bids = OptimizedSkipList[float, PriceLevel]()
                    self.asks = OptimizedSkipList[float, PriceLevel]()
                else:
                    self.bids = EnhancedHeap(is_max_heap=True)
                    self.asks = EnhancedHeap(is_max_heap=False)

                # Process bids from snapshot
                for price_str, qty_str in snapshot_data.get("b", []):
                    try:
                        price = float(price_str)
                        quantity = float(qty_str)
                        if not self._validate_price_quantity(price, quantity):
                            logger.warning(
                                f"[{self.symbol}] Invalid bid price/quantity in snapshot: {price_str}/{qty_str}. Skipping."
                            )
                            continue
                        if quantity > 0:  # Only add if quantity is positive
                            level = PriceLevel(price, quantity, int(time.time() * 1000))
                            if self.use_skip_list:
                                self.bids.insert(price, level)
                            else:
                                self.bids.insert(level)
                    except (ValueError, TypeError) as e:
                        logger.error(
                            f"[{self.symbol}] Failed to parse bid data in snapshot: price={price_str}, quantity={qty_str}, error={e}"
                        )

                # Process asks from snapshot
                for price_str, qty_str in snapshot_data.get("a", []):
                    try:
                        price = float(price_str)
                        quantity = float(qty_str)
                        if not self._validate_price_quantity(price, quantity):
                            logger.warning(
                                f"[{self.symbol}] Invalid ask price/quantity in snapshot: {price_str}/{qty_str}. Skipping."
                            )
                            continue
                        if quantity > 0:  # Only add if quantity is positive
                            level = PriceLevel(price, quantity, int(time.time() * 1000))
                            if self.use_skip_list:
                                self.asks.insert(price, level)
                            else:
                                self.asks.insert(level)
                    except (ValueError, TypeError) as e:
                        logger.error(
                            f"[{self.symbol}] Failed to parse ask data in snapshot: price={price_str}, quantity={qty_str}, error={e}"
                        )

                # Update orderbook metadata
                self.last_update_id = snapshot_data.get("u", 0)
                self.last_sequence = snapshot_data.get("seq", 0)
                self.timestamp = snapshot_data.get("ts", int(time.time() * 1000))

                # Invalidate cached best bid/ask as the orderbook has changed significantly
                self._cached_best_bid = None
                self._cached_best_ask = None

                # Update performance metrics
                self.update_count += 1
                self.total_update_time += time.perf_counter() - start_time
                logger.info(
                    f"[{self.symbol}] Processed snapshot. New update_id={self.last_update_id}, sequence={self.last_sequence}."
                )

        except Exception as e:
            logger.critical(
                f"[{self.symbol}] CRITICAL ERROR processing snapshot: {e}",
                exc_info=True,
            )
            raise  # Re-raise to signal a severe issue

    def process_delta(self, delta_data: dict[str, Any]) -> None:
        """
        Processes real-time orderbook delta updates.
        Updates, inserts, or deletes price levels based on quantity.
        :param delta_data: Dictionary containing delta updates ('b' for bids, 'a' for asks, 'u' for update_id, 'seq' for sequence).
        :raises ValueError: If delta data format is invalid or sequence number is out of order.
        """
        try:
            with self._lock_context():
                start_time = time.perf_counter()

                # Basic validation for delta structure
                if not isinstance(delta_data, dict) or not (
                    "b" in delta_data or "a" in delta_data
                ):
                    logger.error(
                        f"[{self.symbol}] Invalid delta data format: {delta_data}"
                    )
                    raise ValueError("Invalid delta data format: Missing bids or asks.")

                # Validate and update sequence number
                sequence = delta_data.get("seq", self.last_sequence + 1)
                if not self._validate_sequence(sequence):
                    # If sequence is invalid, we stop processing this delta.
                    logger.warning(
                        f"[{self.symbol}] Invalid sequence detected. Delta not processed."
                    )
                    return  # Do not process this delta further

                # Batch process bid updates
                for price_str, qty_str in delta_data.get("b", []):
                    try:
                        price = float(price_str)
                        quantity = float(qty_str)
                        if not self._validate_price_quantity(price, quantity):
                            logger.warning(
                                f"[{self.symbol}] Invalid bid price/quantity in delta: {price_str}/{qty_str}. Skipping."
                            )
                            continue

                        if quantity == 0.0:  # Quantity is 0, so delete the price level
                            if self.use_skip_list:
                                self.bids.delete(price)
                            else:
                                self.bids.remove(price)
                        else:  # Quantity is > 0, so insert or update
                            level = PriceLevel(price, quantity, int(time.time() * 1000))
                            if self.use_skip_list:
                                self.bids.insert(price, level)
                            else:
                                self.bids.insert(level)
                    except (ValueError, TypeError) as e:
                        logger.error(
                            f"[{self.symbol}] Failed to parse bid delta data: price={price_str}, quantity={qty_str}, error={e}"
                        )

                # Batch process ask updates
                for price_str, qty_str in delta_data.get("a", []):
                    try:
                        price = float(price_str)
                        quantity = float(qty_str)
                        if not self._validate_price_quantity(price, quantity):
                            logger.warning(
                                f"[{self.symbol}] Invalid ask price/quantity in delta: {price_str}/{qty_str}. Skipping."
                            )
                            continue

                        if quantity == 0.0:  # Quantity is 0, so delete the price level
                            if self.use_skip_list:
                                self.asks.delete(price)
                            else:
                                self.asks.remove(price)
                        else:  # Quantity is > 0, so insert or update
                            level = PriceLevel(price, quantity, int(time.time() * 1000))
                            if self.use_skip_list:
                                self.asks.insert(price, level)
                            else:
                                self.asks.insert(level)
                    except (ValueError, TypeError) as e:
                        logger.error(
                            f"[{self.symbol}] Failed to parse ask delta data: price={price_str}, quantity={qty_str}, error={e}"
                        )

                # Update orderbook metadata
                self.last_update_id = delta_data.get("u", self.last_update_id)
                self.last_sequence = sequence
                self.timestamp = delta_data.get("ts", int(time.time() * 1000))

                # Invalidate cached best bid/ask
                self._cached_best_bid = None
                self._cached_best_ask = None

                # Update performance metrics
                self.update_count += 1
                self.total_update_time += time.perf_counter() - start_time
                logger.info(
                    f"[{self.symbol}] Processed delta. New update_id={self.last_update_id}, sequence={self.last_sequence}."
                )

        except Exception as e:
            logger.error(f"[{self.symbol}] Error processing delta: {e}", exc_info=True)
            raise  # Re-raise for external handling if necessary

    @cached_property
    def best_bid(self) -> PriceLevel | None:
        """
        Gets the best (highest) bid price level.
        Uses cached value if available, recalculates and caches otherwise.
        :return: The best bid PriceLevel, or None if no bids exist.
        """
        with self._lock_context():
            if self.use_skip_list:
                items = self.bids.get_sorted_items(reverse=True)
                if items:
                    self._cached_best_bid = items[0][1]
                else:
                    self._cached_best_bid = None
            else:  # EnhancedHeap
                if (
                    self.bids._size > 0
                ):  # Check if heap is not empty before attempting to extract
                    # Extract top without removing it (peek functionality)
                    # For a heap-based approach, a dedicated `peek_top` method would be more efficient.
                    # For now, we simulate peek by extracting and immediately re-inserting.
                    top_bid = self.bids.extract_top()
                    if top_bid:
                        self.bids.insert(top_bid)  # Re-insert to keep it in the heap
                    self._cached_best_bid = top_bid
                else:
                    self._cached_best_bid = None
            return self._cached_best_bid

    @cached_property
    def best_ask(self) -> PriceLevel | None:
        """
        Gets the best (lowest) ask price level.
        Uses cached value if available, recalculates and caches otherwise.
        :return: The best ask PriceLevel, or None if no asks exist.
        """
        with self._lock_context():
            if self.use_skip_list:
                items = self.asks.get_sorted_items()
                if items:
                    self._cached_best_ask = items[0][1]
                else:
                    self._cached_best_ask = None
            else:  # EnhancedHeap
                if (
                    self.asks._size > 0
                ):  # Check if heap is not empty before attempting to extract
                    top_ask = self.asks.extract_top()
                    if top_ask:
                        self.asks.insert(top_ask)  # Re-insert to keep it in the heap
                    self._cached_best_ask = top_ask
                else:
                    self._cached_best_ask = None
            return self._cached_best_ask

    def get_orderbook_depth(
        self, depth: int = 10
    ) -> tuple[list[PriceLevel], list[PriceLevel]]:
        """
        Retrieves the top N bids and asks from the orderbook.
        :param depth: The number of top price levels to retrieve.
        :return: A tuple containing two lists: (bids_list, asks_list).
        """
        with self._lock_context():
            bids_list: list[PriceLevel] = []
            asks_list: list[PriceLevel] = []

            if self.use_skip_list:
                bids_list = [
                    item[1] for item in self.bids.get_sorted_items(reverse=True)[:depth]
                ]
                asks_list = [item[1] for item in self.asks.get_sorted_items()[:depth]]
            else:  # EnhancedHeap
                # For heaps, extracting top N and then re-inserting them is a common way to get sorted depth
                temp_bids_storage: list[PriceLevel] = []
                # Check actual size before iterating to prevent errors
                for _ in range(min(depth, self.bids._size)):
                    level = self.bids.extract_top()
                    if level:
                        bids_list.append(level)
                        temp_bids_storage.append(level)
                # Re-insert extracted bids back into the heap
                for level in temp_bids_storage:
                    self.bids.insert(level)

                temp_asks_storage: list[PriceLevel] = []
                # Check actual size before iterating to prevent errors
                for _ in range(min(depth, self.asks._size)):
                    level = self.asks.extract_top()
                    if level:
                        asks_list.append(level)
                        temp_asks_storage.append(level)
                # Re-insert extracted asks back into the heap
                for level in temp_asks_storage:
                    self.asks.insert(level)

            logger.debug(f"[{self.symbol}] Retrieved orderbook depth {depth}.")
            return bids_list, asks_list

    def validate_orderbook(self) -> bool:
        """
        Performs an integrity check on the orderbook.
        Checks for:
        1. Duplicate price levels within bids and asks.
        2. Inverted bid-ask spread (best bid should always be less than best ask).
        :return: True if the orderbook is considered valid, False otherwise.
        """
        with self._lock_context():
            is_valid = True

            # Check for empty orderbook scenarios using _size attribute
            if (
                self.use_skip_list and self.bids._size == 0 and self.asks._size == 0
            ) or (
                not self.use_skip_list and self.bids._size == 0 and self.asks._size == 0
            ):
                logger.info(f"[{self.symbol}] Orderbook is empty. Considered valid.")
                return True

            best_bid_level = self.best_bid
            best_ask_level = self.best_ask

            if best_bid_level and best_ask_level:
                if best_bid_level.price >= best_ask_level.price:
                    logger.error(
                        f"[{self.symbol}] Orderbook invalid: Inverted bid-ask spread! Best Bid: {best_bid_level.price}, Best Ask: {best_ask_level.price}"
                    )
                    is_valid = False

            # Additional check for duplicate prices in SkipList (heaps inherently handle this by updating via position_map)
            if self.use_skip_list:
                bids_items = self.bids.get_sorted_items(reverse=True)
                asks_items = self.asks.get_sorted_items()

                bid_prices = {item[0] for item in bids_items}
                ask_prices = {item[0] for item in asks_items}

                if len(bid_prices) != self.bids._size:  # Compare against internal size
                    logger.error(
                        f"[{self.symbol}] Orderbook invalid: Duplicate bid price levels detected (SkipList)."
                    )
                    is_valid = False

                if len(ask_prices) != self.asks._size:  # Compare against internal size
                    logger.error(
                        f"[{self.symbol}] Orderbook invalid: Duplicate ask price levels detected (SkipList)."
                    )
                    is_valid = False

            if is_valid:
                logger.info(f"[{self.symbol}] Orderbook validated successfully.")
            return is_valid


class BybitOrderbookHelper:
    """
    A helper class for managing real-time Bybit orderbook data for a specific symbol,
    integrating with pybit's WebSocket streams and an advanced internal orderbook manager.
    """

    def __init__(
        self,
        symbol: str,
        category: str,
        api_key: str = "",
        api_secret: str = "",
        testnet: bool = False,
        use_skip_list: bool = True,
        max_depth: int = 100,
        orderbook_stream_depth: int = 50,
    ):
        """
        Initializes the BybitOrderbookHelper.

        :param symbol: The trading symbol (e.g., "BTCUSDT").
        :param category: The trading category (e.g., "linear", "spot").
        :param api_key: Bybit API key (optional for public streams, required for HTTP snapshot on private APIs).
        :param api_secret: Bybit API secret (optional for public streams, required for HTTP snapshot on private APIs).
        :param testnet: True if connecting to testnet, False for mainnet.
        :param use_skip_list: If True, uses OptimizedSkipList for internal orderbook, else EnhancedHeap.
        :param max_depth: Max depth for the internal AdvancedOrderbookManager.
        :param orderbook_stream_depth: Depth to subscribe to for the WebSocket orderbook stream (e.g., 1, 25, 50, 100, 200, 500).
        """
        self.symbol = symbol
        self.category = category
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.orderbook_stream_depth = orderbook_stream_depth

        self.orderbook_manager = AdvancedOrderbookManager(
            symbol=self.symbol, use_skip_list=use_skip_list, max_depth=max_depth
        )
        self.websocket_client: WebSocket | None = None

        # Flag to indicate if initial snapshot has been received and processed
        self._is_snapshot_received = threading.Event()
        self._initial_http_snapshot_retrieved = False

        logger.info(
            f"Initialized BybitOrderbookHelper for {self.symbol} ({self.category}). Testnet: {self.testnet}"
        )

    def _get_http_snapshot(self) -> None:
        """
        Retrieves an initial orderbook snapshot via HTTP REST API.
        This is crucial to ensure we have a base state before processing deltas from WebSocket.
        """
        try:
            http_session = HTTP(
                testnet=self.testnet, api_key=self.api_key, api_secret=self.api_secret
            )
            response = http_session.get_orderbook(
                category=self.category,
                symbol=self.symbol,
                limit=self.orderbook_stream_depth,  # Use same limit as WS subscription if possible
            )

            if response and response["retCode"] == 0:
                data = response["result"]
                # Bybit REST API orderbook format: {'s': 'BTCUSDT', 'b': [['price', 'qty']], 'a': [['price', 'qty']], 'ts': 1678886400000, 'u': 12345}
                # The `u` field for update_id and `ts` for timestamp are directly usable.
                # `seq` field (or `last_update_id` for WS) is usually what we align with for deltas.
                # For REST, we use `u` as `last_update_id`.
                snapshot_data = {
                    "b": data["b"],
                    "a": data["a"],
                    "u": data.get("u", 0),  # Update ID from REST
                    "seq": data.get(
                        "u", 0
                    ),  # Using `u` as `seq` for consistency with AdvancedOrderbookManager expects
                    "ts": data.get("ts", int(time.time() * 1000)),
                }
                self.orderbook_manager.process_snapshot(snapshot_data)
                self._initial_http_snapshot_retrieved = True
                logger.info(
                    f"[{self.symbol}] Successfully retrieved initial HTTP orderbook snapshot."
                )
            else:
                logger.error(
                    f"[{self.symbol}] Failed to get HTTP snapshot: {response.get('retMsg', 'Unknown error')}. Response: {response}"
                )
                raise Exception(f"Failed to get HTTP snapshot for {self.symbol}")
        except Exception as e:
            logger.error(
                f"[{self.symbol}] Error fetching initial HTTP snapshot: {e}",
                exc_info=True,
            )
            raise

    def _on_orderbook_update(self, message: dict[str, Any]) -> None:
        """
        Callback function for WebSocket orderbook stream updates.
        Processes incoming snapshot or delta messages.
        """
        if message and message.get("type") == "snapshot":
            logger.debug(f"[{self.symbol}] WebSocket received snapshot.")
            try:
                # Bybit WS snapshot: {'data': [{'b': [], 'a': [], 'u': 123, 'seq': 456}], 'type': 'snapshot'}
                # Need to extract the actual orderbook data from 'data' list.
                # Using 'u' as the update_id and 'seq' as the sequence number.
                data = message["data"][0]  # Assuming single data entry for snapshot
                snapshot_data = {
                    "b": data["b"],
                    "a": data["a"],
                    "u": data.get("u", 0),
                    "seq": data.get("seq", 0),  # Bybit WS provides 'seq' in snapshot
                    "ts": message.get("ts", int(time.time() * 1000)),
                }
                self.orderbook_manager.process_snapshot(snapshot_data)
                self._is_snapshot_received.set()  # Signal that snapshot is ready
                logger.info(
                    f"[{self.symbol}] Internal orderbook updated with WebSocket snapshot. Ready for deltas."
                )
            except Exception as e:
                logger.error(
                    f"[{self.symbol}] Error processing WebSocket snapshot: {e}",
                    exc_info=True,
                )
                self._is_snapshot_received.clear()  # Clear event if processing failed
                # Potentially trigger a resync if snapshot processing fails (e.g. by reconnecting)
        elif message and message.get("type") == "delta":
            if not self._is_snapshot_received.is_set():
                logger.warning(
                    f"[{self.symbol}] Received delta before snapshot. Skipping. (Current manager sequence: {self.orderbook_manager.last_sequence})"
                )
                return

            # Bybit WS delta: {'data': [{'b': [], 'a': [], 'u': 124, 'seq': 457}], 'type': 'delta'}
            data = message["data"][0]  # Assuming single data entry for delta

            delta_data = {
                "b": data["b"],
                "a": data["a"],
                "u": data.get("u", self.orderbook_manager.last_update_id),  # Update ID
                "seq": data.get(
                    "seq", self.orderbook_manager.last_sequence + 1
                ),  # Sequence number from WS
                "ts": message.get("ts", int(time.time() * 1000)),
            }

            try:
                # Only process delta if its sequence number is strictly greater than the last processed sequence
                if delta_data["seq"] > self.orderbook_manager.last_sequence:
                    self.orderbook_manager.process_delta(delta_data)
                else:
                    logger.warning(
                        f"[{self.symbol}] Out-of-order delta received from WebSocket: Message Seq {delta_data['seq']} <= Manager Seq {self.orderbook_manager.last_sequence}. Skipping."
                    )

            except ValueError as ve:
                logger.error(
                    f"[{self.symbol}] Orderbook processing error from delta: {ve}. Attempting to re-sync.",
                    exc_info=True,
                )
                # If delta processing fails due to sequence error, trigger a full resync
                self._is_snapshot_received.clear()
                self.connect_websocket()  # Reconnect to get a new snapshot
            except Exception as e:
                logger.error(
                    f"[{self.symbol}] Generic error processing WebSocket delta: {e}",
                    exc_info=True,
                )

        else:
            logger.debug(f"[{self.symbol}] Unhandled WebSocket message: {message}")

    def start_websocket_stream(self) -> None:
        """
        Starts the WebSocket connection and subscribes to the orderbook stream.
        This method will first fetch an initial HTTP snapshot if it hasn't already.
        """
        if not self._initial_http_snapshot_retrieved:
            logger.info(
                f"[{self.symbol}] Fetching initial HTTP snapshot before starting WebSocket."
            )
            try:
                self._get_http_snapshot()
            except Exception as e:
                logger.error(
                    f"[{self.symbol}] Failed to get initial HTTP snapshot. Cannot start WebSocket stream. Error: {e}"
                )
                return

        # Ensure WebSocket is not already running or stop it cleanly if it is
        if self.websocket_client and self.websocket_client.is_connected():
            logger.warning(
                f"[{self.symbol}] WebSocket client already running. Stopping before restarting."
            )
            self.websocket_client.close()
            time.sleep(1)  # Give time for graceful shutdown

        logger.info(f"[{self.symbol}] Starting WebSocket connection...")
        # For public orderbook streams, channel_type='public' is generally used.
        self.websocket_client = WebSocket(
            testnet=self.testnet,
            channel_type="public",  # Orderbook is a public stream
            api_key=self.api_key,  # Can be empty for public streams, but good practice to pass if defined
            api_secret=self.api_secret,  # Can be empty for public streams, but good practice to pass if defined
        )

        # Subscribe to the orderbook stream
        self.websocket_client.orderbook_stream(
            depth=self.orderbook_stream_depth,
            symbol=self.symbol,
            callback=self._on_orderbook_update,
        )
        logger.info(
            f"[{self.symbol}] Subscribed to orderbook stream (depth {self.orderbook_stream_depth}). Waiting for WebSocket snapshot..."
        )

        # Wait for the initial WebSocket snapshot to be processed
        # This is important to ensure the orderbook manager is fully synced
        # before any consumer relies on its data.
        if not self._is_snapshot_received.wait(timeout=30):  # Wait up to 30 seconds
            logger.error(
                f"[{self.symbol}] Timeout waiting for initial WebSocket orderbook snapshot. Orderbook might be inconsistent. Consider reconnecting."
            )
            # Depending on robustness requirements, may need to reconnect or raise error.
        else:
            logger.info(
                f"[{self.symbol}] Initial WebSocket snapshot received and processed."
            )

    def stop_websocket_stream(self) -> None:
        """
        Stops the WebSocket connection and clears the snapshot received flag.
        """
        if self.websocket_client:
            logger.info(f"[{self.symbol}] Closing WebSocket connection...")
            self.websocket_client.close()
            self.websocket_client = None
            self._is_snapshot_received.clear()  # Reset flag for next start
            self._initial_http_snapshot_retrieved = False  # Also reset HTTP flag
            logger.info(f"[{self.symbol}] WebSocket connection closed.")
        else:
            logger.info(f"[{self.symbol}] WebSocket client not active.")

    def get_best_bid_ask(self) -> tuple[PriceLevel | None, PriceLevel | None]:
        """
        Retrieves the current best bid and best ask from the managed orderbook.
        :return: A tuple of (best_bid_PriceLevel, best_ask_PriceLevel).
                 Returns (None, None) if the orderbook is empty or not yet populated.
        """
        if not self._is_snapshot_received.is_set():
            logger.warning(
                f"[{self.symbol}] Orderbook not yet ready (no snapshot received). Returning None for best bid/ask."
            )
            return None, None

        # Access cached properties from the internal manager
        best_bid = self.orderbook_manager.best_bid
        best_ask = self.orderbook_manager.best_ask
        return best_bid, best_ask

    def get_orderbook_depth(
        self, depth: int = 10
    ) -> tuple[list[PriceLevel], list[PriceLevel]]:
        """
        Retrieves the top N bids and asks from the managed orderbook.
        :param depth: The number of top price levels to retrieve.
        :return: A tuple containing two lists: (bids_list, asks_list).
        """
        if not self._is_snapshot_received.is_set():
            logger.warning(
                f"[{self.symbol}] Orderbook not yet ready (no snapshot received). Returning empty lists for depth."
            )
            return [], []
        return self.orderbook_manager.get_orderbook_depth(depth)

    def validate_orderbook_integrity(self) -> bool:
        """
        Performs an integrity check on the internal orderbook.
        :return: True if the orderbook is considered valid, False otherwise.
        """
        if not self._is_snapshot_received.is_set():
            logger.warning(
                f"[{self.symbol}] Cannot validate orderbook integrity: no snapshot received yet."
            )
            return False
        return self.orderbook_manager.validate_orderbook()

    # Example: A simple method to get instrument info (using HTTP)
    def get_instrument_info(self) -> dict[str, Any]:
        """
        Retrieves instrument information for the trading symbol via HTTP.
        """
        try:
            http_session = HTTP(
                testnet=self.testnet, api_key=self.api_key, api_secret=self.api_secret
            )
            response = http_session.get_instruments_info(
                category=self.category, symbol=self.symbol
            )
            if response and response["retCode"] == 0:
                logger.debug(f"[{self.symbol}] Retrieved instrument info.")
                return (
                    response["result"]["list"][0] if response["result"]["list"] else {}
                )
            else:
                logger.error(
                    f"[{self.symbol}] Failed to get instrument info: {response.get('retMsg', 'Unknown error')}"
                )
                return {}
        except Exception as e:
            logger.error(
                f"[{self.symbol}] Error fetching instrument info: {e}", exc_info=True
            )
            return {}


# Example Usage
if __name__ == "__main__":
    # IMPORTANT: Replace with your actual API key and secret.
    # For public orderbook streams, API key/secret are technically optional,
    # but highly recommended to include them, especially if you plan to extend
    # this helper for private streams or HTTP trading operations.
    # Set USE_TESTNET to False for production (mainnet).
    API_KEY = "YOUR_API_KEY"  # e.g., os.getenv("BYBIT_API_KEY")
    API_SECRET = "YOUR_API_SECRET"  # e.g., os.getenv("BYBIT_API_SECRET")
    USE_TESTNET = True

    # Initialize the helper for BTCUSDT perpetual futures
    ob_helper = BybitOrderbookHelper(
        symbol="BTCUSDT",
        category="linear",  # Can be 'spot', 'inverse', 'option'
        api_key=API_KEY,
        api_secret=API_SECRET,
        testnet=USE_TESTNET,
        use_skip_list=True,  # Set to False to use EnhancedHeap instead
        orderbook_stream_depth=25,  # Bybit supports depths like 1, 25, 50, 100, 200, 500
    )

    try:
        # Start the orderbook stream. This will fetch an HTTP snapshot first,
        # then connect to WebSocket and wait for its initial snapshot.
        ob_helper.start_websocket_stream()

        print(
            "\nWaiting for orderbook to stabilize and receive updates (e.g., 5 seconds)..."
        )
        time.sleep(5)  # Give some time for updates to come in

        # Get current best bid and ask
        best_bid, best_ask = ob_helper.get_best_bid_ask()
        if best_bid and best_ask:
            print(
                f"\nCurrent Best Bid ({ob_helper.symbol}): {best_bid.price} @ {best_bid.quantity}"
            )
            print(
                f"Current Best Ask ({ob_helper.symbol}): {best_ask.price} @ {best_ask.quantity}"
            )
            print(f"Spread: {best_ask.price - best_bid.price:.4f}")
        else:
            print("\nOrderbook is empty or not yet populated.")

        # Get top 5 levels of the orderbook
        bids_depth, asks_depth = ob_helper.get_orderbook_depth(depth=5)
        print("\n--- Top 5 Bids ---")
        for level in bids_depth:
            print(
                f"Price: {level.price}, Quantity: {level.quantity}, Timestamp: {level.timestamp}"
            )

        print("\n--- Top 5 Asks ---")
        for level in asks_depth:
            print(
                f"Price: {level.price}, Quantity: {level.quantity}, Timestamp: {level.timestamp}"
            )

        # Validate orderbook integrity
        print(
            f"\nOrderbook Integrity Valid: {ob_helper.validate_orderbook_integrity()}"
        )

        # Get instrument info for the symbol
        instrument_info = ob_helper.get_instrument_info()
        if instrument_info:
            print(f"\nInstrument Info (symbol={instrument_info.get('symbol')}):")
            print(f"  Price Scale: {instrument_info.get('priceScale')}")
            print(
                f"  Min Order Qty: {instrument_info.get('lotSizeFilter', {}).get('minOrderQty')}"
            )
        else:
            print(f"\nFailed to retrieve instrument info for {ob_helper.symbol}.")

        print("\nKeeping stream open for another 15 seconds to observe updates...")
        time.sleep(15)

    except Exception:
        logger.exception("An error occurred in the main execution block.")
    finally:
        # Ensure WebSocket connection is closed cleanly on exit
        ob_helper.stop_websocket_stream()
        logger.info("Application finished.")
