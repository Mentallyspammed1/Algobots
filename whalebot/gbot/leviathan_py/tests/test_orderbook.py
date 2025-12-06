"""
Tests for the LocalOrderBook class.
"""
import pytest
import numpy as np
from src.orderbook import LocalOrderBook

@pytest.fixture
def sample_snapshot():
    """Provides a sample order book snapshot."""
    return {
        "b": [
            ("100.0", "1.0"),
            ("99.5", "2.0"),
            ("99.0", "5.0"), # bid wall
        ],
        "a": [
            ("100.5", "1.5"),
            ("101.0", "2.5"),
            ("101.5", "6.0"), # ask wall
        ]
    }

def test_orderbook_snapshot(sample_snapshot):
    book = LocalOrderBook()
    assert not book.ready
    
    book.update(sample_snapshot, is_snapshot=True)
    
    assert book.ready
    assert len(book.bids) == 3
    assert len(book.asks) == 3
    assert book.bids[100.0] == 1.0
    assert book.asks[100.5] == 1.5

def test_orderbook_delta_update(sample_snapshot):
    book = LocalOrderBook()
    book.update(sample_snapshot, is_snapshot=True)
    
    # Delta update: new bid, modified ask, removed bid
    delta = {
        "b": [("100.2", "0.5"), ("99.0", "0.0")], # New best bid, remove old wall
        "a": [("100.5", "1.8")] # Modify existing ask
    }
    
    book.update(delta, is_snapshot=False)
    
    assert len(book.bids) == 2
    assert book.bids[100.2] == 0.5
    assert 99.0 not in book.bids
    
    assert len(book.asks) == 3
    assert book.asks[100.5] == 1.8

def test_get_best_bid_ask(sample_snapshot):
    book = LocalOrderBook()
    book.update(sample_snapshot, is_snapshot=True)
    
    best = book.get_best_bid_ask()
    assert best['bid'] == 100.0
    assert best['ask'] == 100.5

def test_calculate_metrics(sample_snapshot):
    book = LocalOrderBook(depth=10)
    book.update(sample_snapshot, is_snapshot=True)
    
    metrics = book.get_analysis()
    
    # Best bid/ask
    best_bid_price, best_bid_size = 100.0, 1.0
    best_ask_price, best_ask_size = 100.5, 1.5
    
    # WMP
    imb_weight = best_bid_size / (best_bid_size + best_ask_size) # 1.0 / 2.5 = 0.4
    expected_wmp = (best_bid_price * (1 - imb_weight)) + (best_ask_price * imb_weight)
    assert np.isclose(metrics['wmp'], expected_wmp)
    
    # Spread
    assert np.isclose(metrics['spread'], 0.5)
    
    # Walls
    assert metrics['bid_wall'] == 5.0 # Max size in bids
    assert metrics['ask_wall'] == 6.0 # Max size in asks
    
    # Skew
    total_bid_vol = 1.0 + 2.0 + 5.0
    total_ask_vol = 1.5 + 2.5 + 6.0
    expected_skew = (total_bid_vol - total_ask_vol) / (total_bid_vol + total_ask_vol)
    assert np.isclose(metrics['skew'], expected_skew)

def test_wall_status_logic():
    book = LocalOrderBook()
    
    # 1. Initial state: Balanced
    book.update({"b": [("100", "10")], "a": [("101", "11")]}, is_snapshot=True)
    assert book.metrics['wall_status'] == 'BALANCED'

    # 2. Bid Support
    book.update({"b": [("100", "20")]}, is_snapshot=False)
    assert book.metrics['wall_status'] == 'BID_SUPPORT'
    assert book.metrics['prev_bid_wall'] == 20

    # 3. Ask Resistance
    book.update({"a": [("101", "40")]}, is_snapshot=False)
    assert book.metrics['wall_status'] == 'ASK_RESISTANCE'

    # 4. Bid Wall Broken
    book.update({"b": [("100", "5")]}, is_snapshot=False) # Drops from 20 to 5 (< 70%)
    assert book.metrics['wall_status'] == 'BID_WALL_BROKEN'

    # 5. Ask Wall Broken
    book.update({"a": [("101", "10")]}, is_snapshot=False) # Drops from 40 to 10 (< 70%)
    assert book.metrics['wall_status'] == 'ASK_WALL_BROKEN'

# Need to import numpy for np.isclose
import numpy as np
