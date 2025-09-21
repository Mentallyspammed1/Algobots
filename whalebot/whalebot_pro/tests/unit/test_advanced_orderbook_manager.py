
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal
import time

from whalebot_pro.orderbook.advanced_orderbook_manager import PriceLevel, OptimizedSkipList, EnhancedHeap, AdvancedOrderbookManager

@pytest.fixture
def mock_logger():
    return MagicMock(spec=logging.Logger)

@pytest.fixture
def price_level_data():
    return PriceLevel(price=100.0, quantity=10.0, timestamp=int(time.time() * 1000))

# --- PriceLevel Tests ---
def test_price_level_creation(price_level_data):
    assert price_level_data.price == 100.0
    assert price_level_data.quantity == 10.0

def test_price_level_comparison():
    pl1 = PriceLevel(price=100.0, quantity=10.0, timestamp=1)
    pl2 = PriceLevel(price=101.0, quantity=5.0, timestamp=2)
    pl3 = PriceLevel(price=100.0, quantity=20.0, timestamp=3) # Same price, different qty/ts

    assert pl1 < pl2
    assert pl2 > pl1
    assert pl1 == pl3 # Equality based only on price

# --- OptimizedSkipList Tests ---
def test_skip_list_insert_and_get(mock_logger):
    sl = OptimizedSkipList[float, PriceLevel]()
    pl1 = PriceLevel(price=100.0, quantity=10.0, timestamp=1)
    pl2 = PriceLevel(price=90.0, quantity=20.0, timestamp=2)
    pl3 = PriceLevel(price=110.0, quantity=5.0, timestamp=3)

    sl.insert(pl1.price, pl1)
    sl.insert(pl2.price, pl2)
    sl.insert(pl3.price, pl3)

    assert sl.size == 3
    sorted_items = sl.get_sorted_items()
    assert [item[0] for item in sorted_items] == [90.0, 100.0, 110.0]
    assert sl.peek_top() == pl3 # Highest price
    assert sl.peek_top(reverse=True) == pl2 # Lowest price

def test_skip_list_delete(mock_logger):
    sl = OptimizedSkipList[float, PriceLevel]()
    pl1 = PriceLevel(price=100.0, quantity=10.0, timestamp=1)
    sl.insert(pl1.price, pl1)
    assert sl.size == 1

    sl.delete(pl1.price)
    assert sl.size == 0
    assert sl.get_sorted_items() == []

    # Test deleting non-existent key
    assert sl.delete(100.0) is False

# --- EnhancedHeap Tests ---
def test_enhanced_heap_insert_and_peek():
    max_heap = EnhancedHeap(is_max_heap=True)
    min_heap = EnhancedHeap(is_max_heap=False)

    pl1 = PriceLevel(price=100.0, quantity=10.0, timestamp=1)
    pl2 = PriceLevel(price=90.0, quantity=20.0, timestamp=2)
    pl3 = PriceLevel(price=110.0, quantity=5.0, timestamp=3)

    max_heap.insert(pl1)
    max_heap.insert(pl2)
    max_heap.insert(pl3)

    min_heap.insert(pl1)
    min_heap.insert(pl2)
    min_heap.insert(pl3)

    assert max_heap.size == 3
    assert max_heap.peek_top() == pl3 # Max heap should have highest price on top

    assert min_heap.size == 3
    assert min_heap.peek_top() == pl2 # Min heap should have lowest price on top

def test_enhanced_heap_remove():
    max_heap = EnhancedHeap(is_max_heap=True)
    pl1 = PriceLevel(price=100.0, quantity=10.0, timestamp=1)
    pl2 = PriceLevel(price=90.0, quantity=20.0, timestamp=2)
    max_heap.insert(pl1)
    max_heap.insert(pl2)

    assert max_heap.size == 2
    assert max_heap.remove(100.0) is True
    assert max_heap.size == 1
    assert max_heap.peek_top() == pl2

    assert max_heap.remove(90.0) is True
    assert max_heap.size == 0
    assert max_heap.peek_top() is None

    assert max_heap.remove(50.0) is False # Test removing non-existent

# --- AdvancedOrderbookManager Tests ---
@pytest.mark.asyncio
async def test_orderbook_manager_snapshot_update(mock_logger):
    ob_manager = AdvancedOrderbookManager(symbol="BTCUSDT", logger=mock_logger, use_skip_list=True)
    
    snapshot_data = {
        "b": [["100.0", "10.0"], ["99.0", "5.0"]],
        "a": [["101.0", "8.0"], ["102.0", "12.0"]],
        "u": 12345
    }
    await ob_manager.update_snapshot(snapshot_data)

    best_bid, best_ask = await ob_manager.get_best_bid_ask()
    assert best_bid == 100.0
    assert best_ask == 101.0
    assert ob_manager.last_update_id == 12345
    assert ob_manager.bids_ds.size == 2
    assert ob_manager.asks_ds.size == 2

@pytest.mark.asyncio
async def test_orderbook_manager_delta_update(mock_logger):
    ob_manager = AdvancedOrderbookManager(symbol="BTCUSDT", logger=mock_logger, use_skip_list=True)
    
    # Initial snapshot
    snapshot_data = {
        "b": [["100.0", "10.0"], ["99.0", "5.0"]],
        "a": [["101.0", "8.0"], ["102.0", "12.0"]],
        "u": 100
    }
    await ob_manager.update_snapshot(snapshot_data)

    # Delta update: modify bid, add bid, remove ask, modify ask
    delta_data = {
        "b": [["100.0", "15.0"], ["98.0", "7.0"]],
        "a": [["101.0", "0.0"], ["103.0", "9.0"]],
        "u": 101
    }
    await ob_manager.update_delta(delta_data)

    best_bid, best_ask = await ob_manager.get_best_bid_ask()
    assert best_bid == 100.0 # 100.0 modified to 15.0
    assert best_ask == 102.0 # 101.0 removed, 102.0 is next best
    assert ob_manager.last_update_id == 101
    assert ob_manager.bids_ds.size == 3 # 99, 98, 100
    assert ob_manager.asks_ds.size == 2 # 102, 103

@pytest.mark.asyncio
async def test_orderbook_manager_get_depth(mock_logger):
    ob_manager = AdvancedOrderbookManager(symbol="BTCUSDT", logger=mock_logger, use_skip_list=True)
    snapshot_data = {
        "b": [["100.0", "10.0"], ["99.0", "5.0"], ["98.0", "15.0"]],
        "a": [["101.0", "8.0"], ["102.0", "12.0"], ["103.0", "7.0"]],
        "u": 100
    }
    await ob_manager.update_snapshot(snapshot_data)

    bids, asks = await ob_manager.get_depth(2)
    assert len(bids) == 2
    assert bids[0].price == 100.0
    assert bids[1].price == 99.0
    assert len(asks) == 2
    assert asks[0].price == 101.0
    assert asks[1].price == 102.0
