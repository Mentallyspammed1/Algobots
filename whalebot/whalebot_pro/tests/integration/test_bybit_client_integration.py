import logging
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from pybit.unified_trading import HTTP, WebSocket
from whalebot_pro.api.bybit_client import BybitClient
from whalebot_pro.config import Config


@pytest.fixture
def mock_logger():
    return MagicMock(spec=logging.Logger)


@pytest.fixture
def mock_config():
    cfg = MagicMock(spec=Config)
    cfg.BYBIT_API_KEY = "test_key"
    cfg.BYBIT_API_SECRET = "test_secret"
    cfg.testnet = True
    cfg.symbol = "BTCUSDT"
    cfg.interval = "15m"
    cfg.orderbook_limit = 50
    cfg.timezone = "America/Chicago"
    cfg.get_config.return_value = {
        "symbol": "BTCUSDT",
        "interval": "15m",
        "orderbook_limit": 50,
        "testnet": True,
        "timezone": "America/Chicago",
        "trade_management": {"trading_fee_percent": 0.0005},
    }
    return cfg


@pytest.fixture
def bybit_client(mock_config, mock_logger):
    client = BybitClient(
        mock_config.BYBIT_API_KEY,
        mock_config.BYBIT_API_SECRET,
        mock_config.get_config(),
        mock_logger,
    )
    # Mock the actual pybit HTTP and WebSocket sessions
    client.http_session = AsyncMock(spec=HTTP)
    client.ws_public = AsyncMock(spec=WebSocket)
    client.ws_private = AsyncMock(spec=WebSocket)
    return client


@pytest.mark.asyncio
async def test_bybit_client_initialize(bybit_client):
    bybit_client.precision_manager.load_instrument_info = AsyncMock(return_value=None)
    await bybit_client.initialize()
    bybit_client.precision_manager.load_instrument_info.assert_called_once_with(
        bybit_client.symbol
    )


@pytest.mark.asyncio
async def test_fetch_current_price_ws_preferred(bybit_client):
    bybit_client.latest_ticker = {"symbol": "BTCUSDT", "lastPrice": Decimal("40000.50")}
    price = await bybit_client.fetch_current_price()
    assert price == Decimal("40000.50")
    bybit_client.http_session.get_tickers.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_current_price_rest_fallback(bybit_client):
    bybit_client.latest_ticker = {}
    bybit_client.http_session.get_tickers.return_value = {
        "retCode": 0,
        "result": {"list": [{"lastPrice": "39999.75"}]},
    }
    price = await bybit_client.fetch_current_price()
    assert price == Decimal("39999.75")
    bybit_client.http_session.get_tickers.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_klines_ws_preferred(bybit_client):
    mock_df = pd.DataFrame(
        {"close": [1, 2, 3]},
        index=pd.to_datetime(["2023-01-01", "2023-01-02", "2023-01-03"]),
    )
    bybit_client.latest_klines = mock_df
    df = await bybit_client.fetch_klines("15m", 3)
    pd.testing.assert_frame_equal(df, mock_df)
    bybit_client.http_session.get_kline.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_klines_rest_fallback(bybit_client):
    bybit_client.latest_klines = pd.DataFrame()  # Empty
    bybit_client.http_session.get_kline.return_value = {
        "retCode": 0,
        "result": {"list": [["1672531200000", "10", "12", "9", "11", "100", "1000"]]},
    }
    df = await bybit_client.fetch_klines("15m", 1)
    assert not df.empty
    assert df.iloc[0]["close"] == 11.0
    bybit_client.http_session.get_kline.assert_called_once()


@pytest.mark.asyncio
async def test_place_order_success(bybit_client):
    bybit_client.precision_manager.round_qty.return_value = Decimal("0.001")
    bybit_client.precision_manager.round_price.return_value = Decimal("40000.00")
    bybit_client.http_session.place_order.return_value = {
        "retCode": 0,
        "result": {"orderId": "123"},
    }

    result = await bybit_client.place_order("Buy", Decimal("0.001"), "Market")
    assert result["orderId"] == "123"
    bybit_client.http_session.place_order.assert_called_once()


@pytest.mark.asyncio
async def test_set_trading_stop_success(bybit_client):
    bybit_client.precision_manager.round_price.return_value = Decimal("39000.00")
    bybit_client.http_session.set_trading_stop.return_value = {
        "retCode": 0,
        "result": {},
    }

    result = await bybit_client.set_trading_stop(stop_loss=Decimal("39000"))
    assert result is True
    bybit_client.http_session.set_trading_stop.assert_called_once()


@pytest.mark.asyncio
async def test_get_wallet_balance_success(bybit_client):
    bybit_client.http_session.get_wallet_balance.return_value = {
        "retCode": 0,
        "result": {"list": [{"coin": [{"coin": "USDT", "walletBalance": "1000.50"}]}]},
    }
    balance = await bybit_client.get_wallet_balance()
    assert balance == Decimal("1000.50")
    bybit_client.http_session.get_wallet_balance.assert_called_once()


@pytest.mark.asyncio
async def test_get_positions_success(bybit_client):
    bybit_client.http_session.get_positions.return_value = {
        "retCode": 0,
        "result": {"list": [{"symbol": "BTCUSDT", "size": "0.001"}]},
    }
    positions = await bybit_client.get_positions()
    assert len(positions) == 1
    assert positions[0]["symbol"] == "BTCUSDT"
    bybit_client.http_session.get_positions.assert_called_once()


@pytest.mark.asyncio
async def test_ws_kline_message_processing(bybit_client):
    message = {
        "topic": "kline.15m.BTCUSDT",
        "data": [
            {
                "start": "1672531200000",
                "open": "10",
                "high": "12",
                "low": "9",
                "close": "11",
                "volume": "100",
                "turnover": "1000",
            }
        ],
    }
    await bybit_client._on_kline_ws_message(message)
    assert not bybit_client.latest_klines.empty
    assert bybit_client.latest_klines.iloc[-1]["close"] == Decimal("11")


@pytest.mark.asyncio
async def test_ws_ticker_message_processing(bybit_client):
    message = {
        "topic": "tickers.BTCUSDT",
        "data": {
            "symbol": "BTCUSDT",
            "lastPrice": "40000.10",
            "bid1Price": "40000",
            "ask1Price": "40000.20",
        },
    }
    await bybit_client._on_ticker_ws_message(message)
    assert bybit_client.latest_ticker["lastPrice"] == Decimal("40000.10")


@pytest.mark.asyncio
async def test_ws_orderbook_message_processing(bybit_client):
    bybit_client.orderbook_manager.update_snapshot = AsyncMock()
    bybit_client.orderbook_manager.update_delta = AsyncMock()

    snapshot_message = {
        "type": "snapshot",
        "topic": "orderbook.50.BTCUSDT",
        "data": {"b": [], "a": [], "u": 1},
    }
    await bybit_client._on_orderbook_ws_message(snapshot_message)
    bybit_client.orderbook_manager.update_snapshot.assert_called_once()

    delta_message = {
        "type": "delta",
        "topic": "orderbook.50.BTCUSDT",
        "data": {"b": [], "a": [], "u": 2},
    }
    await bybit_client._on_orderbook_ws_message(delta_message)
    bybit_client.orderbook_manager.update_delta.assert_called_once()
