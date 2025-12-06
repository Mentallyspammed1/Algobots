"""
Tests for the LeviathanEngine class.
This requires significant mocking of external services (Bybit) and internal components.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from decimal import Decimal

# Set dummy env vars before importing the engine
import os
os.environ['BYBIT_API_KEY'] = 'test'
os.environ['BYBIT_API_SECRET'] = 'test'
os.environ['GEMINI_API_KEY'] = 'test'

from src.engine import LeviathanEngine

@pytest.fixture
def mock_clients():
    """Mocks the HTTP and WebSocket clients."""
    with patch('src.engine.HTTP', new=AsyncMock()) as mock_http_class, \
         patch('src.engine.Websocket', new=MagicMock()) as mock_ws_class:
        
        # Mock HTTP responses
        mock_http = mock_http_class.return_value
        mock_http.get_wallet_balance.return_value = {"result": {"list": [{"totalEquity": "10000"}]}}
        mock_http.get_kline.return_value = {"result": {"list": [
            ["1", "100", "102", "98", "101", "1000", "1"],
            ["2", "101", "103", "99", "102", "1100", "1"],
        ]}}
        mock_http.get_orderbook.return_value = {"result": {"b": [["101", "10"]], "a": [["102", "12"]]}}
        mock_http.get_positions.return_value = {"result": {"list": [{"size": "0"}]}}
        
        # Mock WebSocket instance
        mock_ws = mock_ws_class.return_value
        
        yield mock_http, mock_ws

@pytest.fixture
def mock_components():
    """Mocks the Oracle and OrderBook."""
    with patch('src.engine.OracleBrain', new=AsyncMock()) as mock_oracle_class, \
         patch('src.engine.LocalOrderBook', new=MagicMock()) as mock_book_class:
        
        mock_oracle = mock_oracle_class.return_value
        mock_oracle.divine.return_value = {"action": "HOLD"} # Default to HOLD
        
        mock_book = mock_book_class.return_value
        mock_book.get_analysis.return_value = {"skew": 0, "wall_status": "BALANCED"}
        mock_book.get_best_bid_ask.return_value = {"bid": "101", "ask": "102"}

        yield mock_oracle, mock_book

@pytest.mark.asyncio
async def test_engine_init(mock_clients, mock_components):
    """Test engine initialization."""
    engine = LeviathanEngine()
    assert engine is not None
    assert engine.state['equity'] == Decimal("0") # Initial state

@pytest.mark.asyncio
async def test_warm_up(mock_clients, mock_components):
    """Test the warm-up sequence."""
    mock_http, _ = mock_clients
    engine = LeviathanEngine()
    
    await engine._warm_up()
    
    assert mock_http.get_wallet_balance.call_count == 1
    assert mock_http.get_kline.call_count == 2 # Main and MTF
    assert mock_http.get_orderbook.call_count == 1
    
    assert engine.state['equity'] == Decimal("10000")
    assert engine.state['price'] == Decimal("102") # From last kline
    assert len(engine.oracle.klines) == 2
    assert len(engine.oracle.mtf_klines) == 2

@pytest.mark.asyncio
async def test_place_maker_order_buy(mock_clients, mock_components):
    """Test the logic for placing a BUY order."""
    mock_http, _ = mock_clients
    mock_oracle, _ = mock_components
    
    engine = LeviathanEngine()
    engine.state['equity'] = Decimal("10000")
    engine.state['price'] = Decimal("102")

    # Setup a BUY signal from the oracle
    buy_signal = {"action": "BUY", "confidence": 0.95, "sl": "100", "tp": "105"}
    mock_oracle.divine.return_value = buy_signal

    await engine._place_maker_order(buy_signal)
    
    # Check that submit_order was called
    mock_http.submit_order.assert_called()
    
    # Check some args of the call
    call_args = mock_http.submit_order.call_args[1]
    assert call_args['side'] == 'Buy'
    assert call_args['orderType'] == 'Limit'
    assert Decimal(call_args['qty']) > 0

@pytest.mark.asyncio
async def test_place_maker_order_skip_on_active_position(mock_clients, mock_components):
    """Test that no order is placed if a position is already open."""
    mock_http, _ = mock_clients
    mock_oracle, _ = mock_components
    
    # Mock an active position
    mock_http.get_positions.return_value = {"result": {"list": [{"size": "0.1"}]}}

    engine = LeviathanEngine()
    buy_signal = {"action": "BUY", "confidence": 0.95, "sl": "100", "tp": "105"}
    mock_oracle.divine.return_value = buy_signal

    await engine._place_maker_order(buy_signal)
    
    # submit_order should not have been called
    mock_http.submit_order.assert_not_called()

def test_handle_execution_message(mock_clients, mock_components):
    """Test PnL tracking from execution messages."""
    engine = LeviathanEngine()
    
    win_message = {
        "topic": "execution",
        "data": [{
            "execType": "Trade",
            "closedSize": "0.1",
            "execPnl": "50.50"
        }]
    }
    
    engine._handle_message(win_message)
    
    assert engine.state['stats']['trades'] == 1
    assert engine.state['stats']['wins'] == 1
    assert engine.state['stats']['total_pnl'] == Decimal("50.50")
    assert engine.state['consecutive_losses'] == 0

    loss_message = {
        "topic": "execution",
        "data": [{
            "execType": "Trade",
            "closedSize": "0.1",
            "execPnl": "-20.10"
        }]
    }

    engine._handle_message(loss_message)

    assert engine.state['stats']['trades'] == 2
    assert engine.state['stats']['wins'] == 1
    assert engine.state['stats']['total_pnl'] == Decimal("30.40")
    assert engine.state['consecutive_losses'] == 1
