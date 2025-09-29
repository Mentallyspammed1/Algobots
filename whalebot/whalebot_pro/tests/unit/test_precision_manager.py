import logging
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from whalebot_pro.core.precision_manager import PrecisionManager


@pytest.fixture
def mock_logger():
    return MagicMock(spec=logging.Logger)


@pytest.fixture
def mock_bybit_client():
    client = AsyncMock()
    client.category = "linear"
    client.http_session = MagicMock()  # Mock http_session for _bybit_request_with_retry
    return client


@pytest.fixture
def precision_manager(mock_bybit_client, mock_logger):
    return PrecisionManager(mock_bybit_client, mock_logger)


@pytest.mark.asyncio
async def test_load_instrument_info_success(precision_manager, mock_bybit_client):
    mock_bybit_client._bybit_request_with_retry.return_value = {
        "retCode": 0,
        "result": {
            "list": [
                {
                    "symbol": "BTCUSDT",
                    "priceFilter": {"tickSize": "0.01"},
                    "lotSizeFilter": {
                        "qtyStep": "0.001",
                        "minOrderQty": "0.001",
                        "maxOrderQty": "100",
                        "minNotionalValue": "10",
                    },
                }
            ]
        },
    }

    await precision_manager.load_instrument_info("BTCUSDT")

    assert precision_manager.initialized is True
    assert "BTCUSDT" in precision_manager.instruments_info
    assert precision_manager.instruments_info["BTCUSDT"][
        "price_precision_decimal"
    ] == Decimal("0.01")
    assert precision_manager.instruments_info["BTCUSDT"][
        "qty_precision_decimal"
    ] == Decimal("0.001")
    assert precision_manager.instruments_info["BTCUSDT"]["min_qty"] == Decimal("0.001")
    assert precision_manager.instruments_info["BTCUSDT"]["max_qty"] == Decimal("100")
    assert precision_manager.instruments_info["BTCUSDT"]["min_notional"] == Decimal(
        "10"
    )
    precision_manager.logger.info.assert_called_once()


@pytest.mark.asyncio
async def test_load_instrument_info_failure(precision_manager, mock_bybit_client):
    mock_bybit_client._bybit_request_with_retry.return_value = None

    await precision_manager.load_instrument_info("BTCUSDT")

    assert precision_manager.initialized is False
    assert "BTCUSDT" not in precision_manager.instruments_info
    precision_manager.logger.error.assert_called_once()


def test_round_price(precision_manager):
    precision_manager.initialized = True
    precision_manager.instruments_info["BTCUSDT"] = {
        "price_precision_decimal": Decimal("0.01"),
        "qty_precision_decimal": Decimal("0.001"),
        "min_qty": Decimal("0.001"),
        "max_qty": Decimal("100"),
        "min_notional": Decimal("10"),
    }

    assert precision_manager.round_price(Decimal("123.4567"), "BTCUSDT") == Decimal(
        "123.46"
    )
    assert precision_manager.round_price(Decimal("123.453"), "BTCUSDT") == Decimal(
        "123.45"
    )
    assert precision_manager.round_price(Decimal("100"), "BTCUSDT") == Decimal("100.00")


def test_round_qty(precision_manager):
    precision_manager.initialized = True
    precision_manager.instruments_info["BTCUSDT"] = {
        "price_precision_decimal": Decimal("0.01"),
        "qty_precision_decimal": Decimal("0.001"),
        "min_qty": Decimal("0.001"),
        "max_qty": Decimal("100"),
        "min_notional": Decimal("10"),
    }

    assert precision_manager.round_qty(Decimal("0.12345"), "BTCUSDT") == Decimal(
        "0.123"
    )
    assert precision_manager.round_qty(Decimal("0.0009"), "BTCUSDT") == Decimal(
        "0.000"
    )  # Should round down
    assert precision_manager.round_qty(Decimal("1.000"), "BTCUSDT") == Decimal("1.000")


def test_get_min_qty(precision_manager):
    precision_manager.initialized = True
    precision_manager.instruments_info["BTCUSDT"] = {
        "price_precision_decimal": Decimal("0.01"),
        "qty_precision_decimal": Decimal("0.001"),
        "min_qty": Decimal("0.001"),
        "max_qty": Decimal("100"),
        "min_notional": Decimal("10"),
    }
    assert precision_manager.get_min_qty("BTCUSDT") == Decimal("0.001")


def test_get_max_qty(precision_manager):
    precision_manager.initialized = True
    precision_manager.instruments_info["BTCUSDT"] = {
        "price_precision_decimal": Decimal("0.01"),
        "qty_precision_decimal": Decimal("0.001"),
        "min_qty": Decimal("0.001"),
        "max_qty": Decimal("100"),
        "min_notional": Decimal("10"),
    }
    assert precision_manager.get_max_qty("BTCUSDT") == Decimal("100")


def test_get_min_notional(precision_manager):
    precision_manager.initialized = True
    precision_manager.instruments_info["BTCUSDT"] = {
        "price_precision_decimal": Decimal("0.01"),
        "qty_precision_decimal": Decimal("0.001"),
        "min_qty": Decimal("0.001"),
        "max_qty": Decimal("100"),
        "min_notional": Decimal("10"),
    }
    assert precision_manager.get_min_notional("BTCUSDT") == Decimal("10")
