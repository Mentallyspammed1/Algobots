import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal

# Assuming the following structure for imports
# from marketmaker.clients.bybit_rest import BybitRest
# from marketmaker.config import Config, APIConfig, TradingConfig

# To make this test runnable without full project setup, we'll mock the imports
# In a real scenario, you'd import directly:
# from ..clients.bybit_rest import BybitRest
# from ..config import Config, APIConfig, TradingConfig

# Mocking the Config and APIConfig for isolated testing
class MockAPIConfig:
    TESTNET = True
    KEY = "test_key"
    SECRET = "test_secret"

class MockTradingConfig:
    CATEGORY = "linear"

class MockConfig:
    api = MockAPIConfig()
    trading = MockTradingConfig()

# Mock the BybitRest class directly for the test
# In a real scenario, you'd import BybitRest and mock its internal dependencies

# We need to define a mock BybitRest class that uses the mocked HTTP client
class MockBybitRest:
    def __init__(self, config):
        self.config = config
        self.session = MagicMock() # Mock the HTTP session
        self.logger = MagicMock() # Mock the logger

    def get_kline(self, symbol: str, interval: str, limit: int):
        return self._get_kline_mock(symbol, interval, limit)

    def _get_kline_mock(self, symbol: str, interval: str, limit: int):
        # This method will be replaced by the patcher in the test
        pass


@patch('marketmaker.clients.bybit_rest.HTTP')
@patch('marketmaker.clients.bybit_rest.logging')
@patch('marketmaker.clients.bybit_rest.APP_CONFIG', new_callable=MockConfig)
def test_get_kline_success(mock_app_config, mock_logging, mock_http):
    # Arrange
    mock_http_instance = mock_http.return_value
    mock_http_instance.get_kline.return_value = {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "category": "linear",
            "symbol": "BTCUSDT",
            "list": [
                ["1678886400000", "20000", "20100", "19900", "20050", "100", "1000"],
                ["1678886460000", "20050", "20150", "19950", "20100", "120", "1200"]
            ]
        }
    }

    # Use the mock BybitRest class for testing
    from marketmaker.clients.bybit_rest import BybitRest
    client = BybitRest(MockConfig())

    symbol = "BTCUSDT"
    interval = "1"
    limit = 2

    # Act
    result = client.get_kline(symbol, interval, limit)

    # Assert
    mock_http_instance.get_kline.assert_called_once_with(
        category=mock_app_config.trading.CATEGORY,
        symbol=symbol,
        interval=interval,
        limit=limit
    )
    assert len(result) == 2
    assert result[0][4] == "20050" # Close price of first kline
    mock_logging.getLogger.return_value.error.assert_not_called()

@patch('marketmaker.clients.bybit_rest.HTTP')
@patch('marketmaker.clients.bybit_rest.logging')
@patch('marketmaker.clients.bybit_rest.APP_CONFIG', new_callable=MockConfig)
def test_get_kline_api_error(mock_app_config, mock_logging, mock_http):
    # Arrange
    mock_http_instance = mock_http.return_value
    mock_http_instance.get_kline.return_value = {
        "retCode": 10001,
        "retMsg": "accountType only support UNIFIED",
        "result": {}
    }

    from marketmaker.clients.bybit_rest import BybitRest
    client = BybitRest(MockConfig())

    symbol = "BTCUSDT"
    interval = "1"
    limit = 1

    # Act & Assert
    with pytest.raises(ValueError, match="Unsupported account type"):
        client.get_kline(symbol, interval, limit)

    mock_logging.getLogger.return_value.error.assert_called_once_with(
        f"API Error 10001: Account type not supported. Details: accountType only support UNIFIED"
    )

@patch('marketmaker.clients.bybit_rest.HTTP')
@patch('marketmaker.clients.bybit_rest.logging')
@patch('marketmaker.clients.bybit_rest.APP_CONFIG', new_callable=MockConfig)
def test_get_kline_generic_exception(mock_app_config, mock_logging, mock_http):
    # Arrange
    mock_http_instance = mock_http.return_value
    mock_http_instance.get_kline.side_effect = Exception("Network error")

    from marketmaker.clients.bybit_rest import BybitRest
    client = BybitRest(MockConfig())

    symbol = "BTCUSDT"
    interval = "1"
    limit = 1

    # Act & Assert
    with pytest.raises(Exception, match="Network error"):
        client.get_kline(symbol, interval, limit)

    mock_logging.getLogger.return_value.exception.assert_called_once_with(
        f"Exception during get_kline for {symbol}: Network error"
    )
