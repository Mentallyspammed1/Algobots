# tests/test_trade_metrics.py
import pytest
from trade_metrics import TradeMetrics
from decimal import Decimal

def test_calculate_fee():
    metrics = TradeMetrics()
    # Taker fee
    assert metrics.calculate_fee(1, 100, False) == Decimal('0.07')
    assert metrics.calculate_fee(0.001, 20000, False) == Decimal('0.000014')
    # Maker fee
    assert metrics.calculate_fee(1, 100, True) == Decimal('0.02')

def test_record_trade():
    metrics = TradeMetrics()
    # Winning Buy trade
    metrics.record_trade(100, 101, 1, "BUY", Decimal('0.07'), Decimal('0.07'), 12345)
    assert metrics.total_realized_pnl == Decimal('0.86')
    assert metrics.total_trades == 1
    assert metrics.winning_trades == 1
    assert metrics.losing_trades == 0
    assert metrics.get_win_rate() == 100.0

    # Losing Sell trade
    metrics.record_trade(100, 99, 1, "SELL", Decimal('0.07'), Decimal('0.07'), 12346)
    assert metrics.total_realized_pnl == Decimal('0.86') + Decimal('-1.14') # 0.86 - 1.14 = -0.28
    assert metrics.total_trades == 2
    assert metrics.winning_trades == 1
    assert metrics.losing_trades == 1
    assert metrics.get_win_rate() == 50.0

def test_get_trade_statistics():
    metrics = TradeMetrics()
    metrics.record_trade(100, 101, 1, "BUY", Decimal('0.07'), Decimal('0.07'), 12345)
    stats = metrics.get_trade_statistics()
    assert stats['total_realized_pnl'] == Decimal('0.86')
    assert stats['total_trades'] == 1
    assert stats['winning_trades'] == 1
    assert stats['losing_trades'] == 0
    assert stats['win_rate'] == 100.0