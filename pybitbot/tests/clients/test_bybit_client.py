import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pybitbot.clients.bybit_client import BybitClient, BybitAPIError, BybitRateLimitError, BybitAccountError
from pybitbot.config.config import Config, APIConfig

@pytest.fixture
def mock_config():
    return Config(api=APIConfig(KEY="test", SECRET="test", TESTNET=True), LOG_LEVEL="DEBUG")

@pytest.fixture
def bybit_client(mock_config):
    with patch('pybit.unified_trading.HTTP') as mock_http_class,
         patch('pybit.unified_trading.WebSocket') as mock_ws_class,
         patch('pybitbot.utils.logger.get_logger') as mock_get_logger:
        
        # Mock the logger to prevent console output during tests
        mock_logger_instance = MagicMock()
        mock_get_logger.return_value = mock_logger_instance

        client = BybitClient(mock_config)
        client.session = mock_http_class.return_value # Ensure session is the mock instance
        client.ws_client = mock_ws_class.return_value # Ensure ws_client is the mock instance
        yield client

@pytest.mark.asyncio
async def test_get_klines_success(bybit_client):
    bybit_client.session.get_kline.return_value = {
        "retCode": 0,
        "retMsg": "OK",
        "result": {"list": [["1678886400000", "30000", "30100", "29900", "30050", "100", "1000"]]}
    }
    klines = await bybit_client.get_klines("BTCUSDT", "1", 1)
    assert len(klines) == 1
    assert klines[0][4] == "30050" # Close price
    bybit_client.session.get_kline.assert_called_once_with(category="linear", symbol="BTCUSDT", interval="1", limit=1)

@pytest.mark.asyncio
async def test_get_klines_rate_limit_error(bybit_client):
    bybit_client.session.get_kline.return_value = {"retCode": 10006, "retMsg": "Too many requests"}
    with pytest.raises(BybitRateLimitError, match="Too many requests"):
        await bybit_client.get_klines("BTCUSDT", "1", 1)
    assert bybit_client.session.get_kline.call_count == 5 # Should retry 5 times

@pytest.mark.asyncio
async def test_get_klines_account_error(bybit_client):
    bybit_client.session.get_kline.return_value = {"retCode": 10001, "retMsg": "accountType only support UNIFIED"}
    with pytest.raises(BybitAccountError, match="accountType only support UNIFIED"):
        await bybit_client.get_klines("BTCUSDT", "1", 1)
    assert bybit_client.session.get_kline.call_count == 1 # Should not retry for this error type

@pytest.mark.asyncio
async def test_place_order_success(bybit_client):
    bybit_client.session.place_order.return_value = {"retCode": 0, "retMsg": "OK", "result": {"orderId": "test_order_id"}}
    order_result = await bybit_client.place_order(symbol="BTCUSDT", side="Buy", qty=0.001, orderType="Market")
    assert order_result["orderId"] == "test_order_id"
    bybit_client.session.place_order.assert_called_once_with(symbol="BTCUSDT", side="Buy", qty=0.001, orderType="Market")

@pytest.mark.asyncio
async def test_get_wallet_balance_success(bybit_client):
    bybit_client.session.get_wallet_balance.return_value = {
        "retCode": 0,
        "retMsg": "OK",
        "result": {"list": [{"coin": [{"coin": "USDT", "walletBalance": "1000.50"}]}]}
    }
    balance = await bybit_client.get_wallet_balance("USDT")
    assert balance == 1000.50

@pytest.mark.asyncio
async def test_connect_websocket(bybit_client):
    await bybit_client.connect_websocket("BTCUSDT", "1")
    bybit_client.ws_client.kline_v5_stream.assert_called_once_with(interval="1", symbol="BTCUSDT", callback=bybit_client.ws_client.kline_v5_stream.call_args[1]['callback'])
    assert bybit_client.ws_connected is True

@pytest.mark.asyncio
async def test_disconnect_websocket(bybit_client):
    bybit_client.ws_connected = True # Simulate connected state
    bybit_client.ws_client = MagicMock() # Ensure ws_client is mocked
    await bybit_client.disconnect_websocket()
    bybit_client.ws_client.exit.assert_called_once()
    assert bybit_client.ws_connected is False
