import asyncio
import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
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
    cfg.interval = "1m"
    cfg.orderbook_limit = 1
    cfg.timezone = "America/Chicago"
    cfg.get_config.return_value = {
        "symbol": "BTCUSDT",
        "interval": "1m",
        "orderbook_limit": 1,
        "testnet": True,
        "timezone": "America/Chicago",
        "trade_management": {"trading_fee_percent": 0.0005},
    }
    return cfg


@pytest.fixture
def bybit_client_for_performance(mock_config, mock_logger):
    client = BybitClient(
        mock_config.BYBIT_API_KEY,
        mock_config.BYBIT_API_SECRET,
        mock_config.get_config(),
        mock_logger,
    )
    client.http_session = AsyncMock()  # Mock the actual HTTP session
    client.http_session.get_tickers.return_value = {
        "retCode": 0,
        "result": {"list": [{"lastPrice": "40000"}]},
    }
    client.http_session.get_kline.return_value = {
        "retCode": 0,
        "result": {"list": [["1672531200000", "10", "12", "9", "11", "100", "1000"]]},
    }
    client.http_session.get_orderbook.return_value = {
        "retCode": 0,
        "result": {"b": [["40000", "10"]], "a": [["40001", "10"]]},
    }
    client.http_session.place_order.return_value = {
        "retCode": 0,
        "result": {"orderId": "123"},
    }
    client.http_session.set_trading_stop.return_value = {"retCode": 0, "result": {}}
    client.http_session.get_wallet_balance.return_value = {
        "retCode": 0,
        "result": {"list": [{"coin": [{"coin": "USDT", "walletBalance": "1000"}]}]},
    }
    client.http_session.get_positions.return_value = {
        "retCode": 0,
        "result": {"list": []},
    }

    # Mock precision manager methods to avoid real calculations
    client.precision_manager = MagicMock()
    client.precision_manager.round_qty.side_effect = lambda qty, sym: qty
    client.precision_manager.round_price.side_effect = lambda price, sym: price
    client.precision_manager.get_min_qty.return_value = Decimal("0.001")

    return client


@pytest.mark.asyncio
async def test_concurrent_api_calls_performance(bybit_client_for_performance):
    num_calls = 100  # Number of concurrent calls
    tasks = []

    start_time = time.perf_counter()

    for _ in range(num_calls):
        tasks.append(bybit_client_for_performance.fetch_current_price())
        tasks.append(bybit_client_for_performance.fetch_klines("1m", 1))
        tasks.append(bybit_client_for_performance.fetch_orderbook(1))

    await asyncio.gather(*tasks)

    end_time = time.perf_counter()
    duration = end_time - start_time

    total_mocked_calls = num_calls * 3  # 3 types of calls per iteration
    bybit_client_for_performance.logger.info(
        f"Performed {total_mocked_calls} mocked API calls in {duration:.4f} seconds.",
    )

    # Assert that the mocked HTTP session methods were called the expected number of times
    assert bybit_client_for_performance.http_session.get_tickers.call_count == num_calls
    assert bybit_client_for_performance.http_session.get_kline.call_count == num_calls
    assert (
        bybit_client_for_performance.http_session.get_orderbook.call_count == num_calls
    )

    # Basic performance assertion: should be very fast since calls are mocked and concurrent
    assert duration < 0.1  # Expect very fast execution for mocked calls


@pytest.mark.asyncio
async def test_api_call_retry_delay_simulation(bybit_client_for_performance):
    # Simulate a failing API call that succeeds on retry
    bybit_client_for_performance.http_session.get_tickers.side_effect = [
        {"retCode": 10001, "retMsg": "Error"},  # First call fails
        {
            "retCode": 0,
            "result": {"list": [{"lastPrice": "40000"}]},
        },  # Second call succeeds
    ]

    start_time = time.perf_counter()
    price = await bybit_client_for_performance.fetch_current_price()
    end_time = time.perf_counter()
    duration = end_time - start_time

    assert price == Decimal("40000")
    assert bybit_client_for_performance.http_session.get_tickers.call_count == 2
    # Check that a delay occurred (RETRY_DELAY_SECONDS is 7 in bybit_client.py)
    assert duration >= 7  # Should be at least the retry delay
