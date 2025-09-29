import logging
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from whalebot_pro.api.bybit_client import BybitClient
from whalebot_pro.config import Config
from whalebot_pro.core.performance_tracker import PerformanceTracker
from whalebot_pro.core.position_manager import PositionManager


@pytest.fixture
def mock_logger():
    return MagicMock(spec=logging.Logger)


@pytest.fixture
def mock_config():
    cfg = MagicMock(spec=Config)
    cfg.get_config.return_value = {
        "symbol": "BTCUSDT",
        "trade_management": {
            "enabled": True,
            "account_balance": 1000.0,
            "risk_per_trade_percent": 1.0,
            "stop_loss_atr_multiple": 1.5,
            "take_profit_atr_multiple": 2.0,
            "max_open_positions": 1,
            "slippage_percent": 0.001,
            "trading_fee_percent": 0.0005,
            "enable_trailing_stop": True,
            "break_even_atr_trigger": 0.5,
            "move_to_breakeven_atr_trigger": 1.0,
            "profit_lock_in_atr_multiple": 0.5,
            "close_on_opposite_signal": True,
            "reverse_position_on_opposite_signal": False,
        },
    }
    cfg.symbol = "BTCUSDT"
    cfg.trade_management = cfg.get_config()["trade_management"]
    return cfg


@pytest.fixture
def mock_bybit_client(mock_config):
    client = AsyncMock(spec=BybitClient)
    client.timezone = UTC
    client.symbol = mock_config.symbol
    client.precision_manager = MagicMock()
    client.precision_manager.round_qty.side_effect = lambda qty, sym: qty.quantize(
        Decimal("0.001")
    )
    client.precision_manager.round_price.side_effect = (
        lambda price, sym: price.quantize(Decimal("0.01"))
    )
    client.precision_manager.get_min_qty.return_value = Decimal("0.001")
    return client


@pytest.fixture
def performance_tracker(mock_logger, mock_config):
    return PerformanceTracker(mock_logger, mock_config.get_config())


@pytest.fixture
def position_manager(mock_config, mock_logger, mock_bybit_client):
    return PositionManager(mock_config.get_config(), mock_logger, mock_bybit_client)


@pytest.mark.asyncio
async def test_sync_positions_from_exchange(position_manager, mock_bybit_client):
    mock_bybit_client.get_positions.return_value = [
        {
            "symbol": "BTCUSDT",
            "side": "Buy",
            "size": "0.01",
            "avgPrice": "40000",
            "stopLoss": "39000",
            "takeProfit": "41000",
            "positionIdx": 0,
        }
    ]
    await position_manager.sync_positions_from_exchange()
    assert len(position_manager.open_positions) == 1
    assert position_manager.open_positions[0]["symbol"] == "BTCUSDT"
    mock_bybit_client.get_positions.assert_called_once()


@pytest.mark.asyncio
async def test_open_position_success(
    position_manager, mock_bybit_client, performance_tracker
):
    mock_bybit_client.get_wallet_balance.return_value = Decimal("1000")
    mock_bybit_client.get_positions.return_value = []  # No open positions
    mock_bybit_client.place_order.return_value = {
        "orderId": "test_order_id",
        "qty": "0.001",
        "avgPrice": "40000",
    }
    mock_bybit_client.set_trading_stop.return_value = True

    new_pos = await position_manager.open_position(
        "Buy", Decimal("40000"), Decimal("100")
    )
    assert new_pos is not None
    assert new_pos["side"] == "Buy"
    assert new_pos["qty"] == Decimal("0.001")
    mock_bybit_client.place_order.assert_called_once()
    mock_bybit_client.set_trading_stop.assert_called_once()


@pytest.mark.asyncio
async def test_close_position_success(
    position_manager, mock_bybit_client, performance_tracker
):
    # Setup an existing position
    existing_pos = {
        "positionIdx": 0,
        "symbol": "BTCUSDT",
        "side": "Buy",
        "entry_price": Decimal("40000"),
        "qty": Decimal("0.001"),
        "stop_loss": Decimal("39000"),
        "take_profit": Decimal("41000"),
        "position_id": "0",
        "order_id": "entry_order_id",
        "entry_time": datetime.now(UTC),
        "initial_stop_loss": Decimal("39000"),
        "trailing_stop_activated": False,
        "trailing_stop_price": None,
        "breakeven_activated": False,
    }
    position_manager.open_positions.append(existing_pos)

    mock_bybit_client.place_order.return_value = {
        "orderId": "close_order_id",
        "qty": "0.001",
        "avgPrice": "40050",
    }
    performance_tracker.record_trade = MagicMock()

    await position_manager.close_position(
        existing_pos, Decimal("40050"), performance_tracker
    )
    assert len(position_manager.open_positions) == 0
    mock_bybit_client.place_order.assert_called_once()
    performance_tracker.record_trade.assert_called_once()


@pytest.mark.asyncio
async def test_manage_positions_breakeven_activated(
    position_manager, mock_bybit_client, performance_tracker
):
    # Setup an existing position that should trigger breakeven
    existing_pos = {
        "positionIdx": 0,
        "symbol": "BTCUSDT",
        "side": "Buy",
        "entry_price": Decimal("40000"),
        "qty": Decimal("0.001"),
        "stop_loss": Decimal("39000"),  # Initial SL
        "take_profit": Decimal("42000"),
        "position_id": "0",
        "order_id": "entry_order_id",
        "entry_time": datetime.now(UTC),
        "initial_stop_loss": Decimal("39000"),
        "trailing_stop_activated": False,
        "trailing_stop_price": None,
        "breakeven_activated": False,
    }
    position_manager.open_positions.append(existing_pos)

    # Mock get_positions to return the current state
    mock_bybit_client.get_positions.return_value = [
        {
            "symbol": "BTCUSDT",
            "side": "Buy",
            "size": "0.001",
            "avgPrice": "40000",
            "stopLoss": "39000",
            "takeProfit": "42000",
            "positionIdx": 0,
        }
    ]
    mock_bybit_client.set_trading_stop.return_value = True

    # Current price moves enough to trigger breakeven (entry + ATR * move_to_breakeven_atr_trigger)
    # Assuming ATR = 100, move_to_breakeven_atr_trigger = 1.0, so price > 40000 + 100 = 40100
    current_price = Decimal("40150")
    atr_value = Decimal("100")

    await position_manager.manage_positions(
        current_price, performance_tracker, atr_value
    )

    # Verify set_trading_stop was called to move SL to breakeven
    mock_bybit_client.set_trading_stop.assert_called_once()
    args, kwargs = mock_bybit_client.set_trading_stop.call_args
    assert kwargs["stop_loss"] == Decimal("40000.00")  # SL moved to entry price
    assert position_manager.open_positions[0]["breakeven_activated"] is True


@pytest.mark.asyncio
async def test_manage_positions_trailing_stop_activated(
    position_manager, mock_bybit_client, performance_tracker
):
    # Setup an existing position that should trigger trailing stop
    existing_pos = {
        "positionIdx": 0,
        "symbol": "BTCUSDT",
        "side": "Buy",
        "entry_price": Decimal("40000"),
        "qty": Decimal("0.001"),
        "stop_loss": Decimal("39000"),  # Initial SL
        "take_profit": Decimal("45000"),
        "position_id": "0",
        "order_id": "entry_order_id",
        "entry_time": datetime.now(UTC),
        "initial_stop_loss": Decimal("39000"),
        "trailing_stop_activated": False,
        "trailing_stop_price": None,
        "breakeven_activated": True,  # Assume breakeven already activated or not configured
    }
    position_manager.open_positions.append(existing_pos)

    mock_bybit_client.get_positions.return_value = [
        {
            "symbol": "BTCUSDT",
            "side": "Buy",
            "size": "0.001",
            "avgPrice": "40000",
            "stopLoss": "39000",
            "takeProfit": "45000",
            "positionIdx": 0,
        }
    ]
    mock_bybit_client.set_trading_stop.return_value = True

    # Current price moves enough to trigger trailing stop (entry + ATR * break_even_atr_trigger)
    # Assuming ATR = 100, break_even_atr_trigger = 0.5, trailing_stop_atr_multiple = 0.8
    # Price > 40000 + 100 * 0.5 = 40050
    # New TSL candidate = 40100 - (100 * 0.8) = 40020
    current_price = Decimal("40100")
    atr_value = Decimal("100")

    await position_manager.manage_positions(
        current_price, performance_tracker, atr_value
    )

    mock_bybit_client.set_trading_stop.assert_called_once()
    args, kwargs = mock_bybit_client.set_trading_stop.call_args
    assert kwargs["stop_loss"] == Decimal("40020.00")  # SL moved up
    assert position_manager.open_positions[0]["trailing_stop_activated"] is True
    assert position_manager.open_positions[0]["trailing_stop_price"] == Decimal(
        "40020.00"
    )
