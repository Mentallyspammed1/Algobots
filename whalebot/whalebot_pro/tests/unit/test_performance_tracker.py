import logging
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from whalebot_pro.core.performance_tracker import PerformanceTracker


@pytest.fixture
def mock_logger():
    return MagicMock(spec=logging.Logger)


@pytest.fixture
def mock_config():
    return {
        "trade_management": {
            "trading_fee_percent": 0.0005,  # 0.05%
        },
    }


@pytest.fixture
def performance_tracker(mock_logger, mock_config):
    return PerformanceTracker(mock_logger, mock_config)


def test_performance_tracker_initialization(performance_tracker):
    assert performance_tracker.trades == []
    assert performance_tracker.total_pnl == Decimal("0")
    assert performance_tracker.wins == 0
    assert performance_tracker.losses == 0
    assert performance_tracker.trading_fee_percent == Decimal("0.0005")


def test_record_trade_win(performance_tracker, mock_logger):
    position = {
        "entry_time": datetime.now(UTC),
        "exit_time": datetime.now(UTC),
        "symbol": "BTCUSDT",
        "side": "Buy",
        "entry_price": Decimal("10000"),
        "exit_price": Decimal("10100"),
        "qty": Decimal("0.01"),
        "closed_by": "TAKE_PROFIT",
    }
    pnl = (position["exit_price"] - position["entry_price"]) * position["qty"]

    performance_tracker.record_trade(position, pnl)

    assert len(performance_tracker.trades) == 1
    assert performance_tracker.wins == 1
    assert performance_tracker.losses == 0

    # Calculate expected PnL after fees
    expected_pnl = (
        pnl
        - (
            position["entry_price"]
            * position["qty"]
            * performance_tracker.trading_fee_percent
        )
        - (
            position["exit_price"]
            * position["qty"]
            * performance_tracker.trading_fee_percent
        )
    )
    assert performance_tracker.total_pnl == pytest.approx(expected_pnl)
    mock_logger.info.assert_called_once()


def test_record_trade_loss(performance_tracker, mock_logger):
    position = {
        "entry_time": datetime.now(UTC),
        "exit_time": datetime.now(UTC),
        "symbol": "BTCUSDT",
        "side": "Buy",
        "entry_price": Decimal("10000"),
        "exit_price": Decimal("9900"),
        "qty": Decimal("0.01"),
        "closed_by": "STOP_LOSS",
    }
    pnl = (position["exit_price"] - position["entry_price"]) * position["qty"]

    performance_tracker.record_trade(position, pnl)

    assert len(performance_tracker.trades) == 1
    assert performance_tracker.wins == 0
    assert performance_tracker.losses == 1

    # Calculate expected PnL after fees
    expected_pnl = (
        pnl
        - (
            position["entry_price"]
            * position["qty"]
            * performance_tracker.trading_fee_percent
        )
        - (
            position["exit_price"]
            * position["qty"]
            * performance_tracker.trading_fee_percent
        )
    )
    assert performance_tracker.total_pnl == pytest.approx(expected_pnl)
    mock_logger.info.assert_called_once()


def test_get_summary_no_trades(performance_tracker):
    summary = performance_tracker.get_summary()
    assert summary["total_trades"] == 0
    assert summary["total_pnl"] == Decimal("0")
    assert summary["wins"] == 0
    assert summary["losses"] == 0
    assert summary["win_rate"] == "0.00%"


def test_get_summary_with_trades(performance_tracker, mock_logger):
    # Record a win
    win_position = {
        "entry_time": datetime.now(UTC),
        "exit_time": datetime.now(UTC),
        "symbol": "BTCUSDT",
        "side": "Buy",
        "entry_price": Decimal("10000"),
        "exit_price": Decimal("10100"),
        "qty": Decimal("0.01"),
        "closed_by": "TAKE_PROFIT",
    }
    win_pnl = (win_position["exit_price"] - win_position["entry_price"]) * win_position[
        "qty"
    ]
    performance_tracker.record_trade(win_position, win_pnl)

    # Record a loss
    loss_position = {
        "entry_time": datetime.now(UTC),
        "exit_time": datetime.now(UTC),
        "symbol": "BTCUSDT",
        "side": "Sell",
        "entry_price": Decimal("10000"),
        "exit_price": Decimal("10100"),
        "qty": Decimal("0.01"),
        "closed_by": "STOP_LOSS",
    }
    loss_pnl = (
        loss_position["entry_price"] - loss_position["exit_price"]
    ) * loss_position["qty"]
    performance_tracker.record_trade(loss_position, loss_pnl)

    summary = performance_tracker.get_summary()
    assert summary["total_trades"] == 2
    assert summary["wins"] == 1
    assert summary["losses"] == 1
    assert summary["win_rate"] == "50.00%"

    # Check total PnL (approximate due to fees)
    expected_total_pnl = (
        win_pnl
        - (
            win_position["entry_price"]
            * win_position["qty"]
            * performance_tracker.trading_fee_percent
        )
        - (
            win_position["exit_price"]
            * win_position["qty"]
            * performance_tracker.trading_fee_percent
        )
    ) + (
        loss_pnl
        - (
            loss_position["entry_price"]
            * loss_position["qty"]
            * performance_tracker.trading_fee_percent
        )
        - (
            loss_position["exit_price"]
            * loss_position["qty"]
            * performance_tracker.trading_fee_percent
        )
    )
    assert summary["total_pnl"] == pytest.approx(expected_total_pnl)
