# tests/conftest.py
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pandas as pd
import pytest


@pytest.fixture
def mock_bybit_client():
    """Provides a mock BybitClient for testing API interactions."""
    mock_client = Mock()
    # Configure mock kline data
    mock_kline_data = [
        [1678886400000, "20000", "20100", "19900", "20050", "100"], # Example kline
        [1678886460000, "20050", "20150", "20000", "20100", "120"],
        [1678886520000, "20100", "20200", "20050", "20150", "150"],
    ]
    mock_client.fetch_klines.return_value = pd.DataFrame(
        [
            {
                'timestamp': datetime.fromtimestamp(k[0]/1000, tz=timezone.utc),
                'open': float(k[1]),
                'high': float(k[2]),
                'low': float(k[3]),
                'close': float(k[4]),
                'volume': float(k[5]),
            } for k in mock_kline_data
        ]
    ).set_index('timestamp').sort_index()

    # Configure mock position data
    mock_client.get_positions.return_value = {
        'size': '0.01',
        'side': 'Buy',
        'avgPrice': '20000',
        'unrealisedPnl': '0.05',
    }
    mock_client.place_order.return_value = True
    mock_client.get_instrument_info.return_value = {
        'lotSizeFilter': {
            'minOrderQty': '0.001',
            'qtyStep': '0.0001'
        }
    }
    return mock_client

@pytest.fixture
def mock_bot_logger():
    """Provides a mock bot_logger for testing logging calls."""
    with patch('bot_logger.logging.getLogger') as mock_get_logger:
        mock_logger_instance = Mock()
        mock_get_logger.return_value = mock_logger_instance
        yield mock_logger_instance

@pytest.fixture
def mock_trade_metrics():
    """Provides a mock TradeMetrics instance."""
    return Mock()
