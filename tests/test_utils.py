# tests/test_utils.py
import pytest
from utils import round_decimal, calculate_order_quantity
from decimal import Decimal

def test_round_decimal():
    assert round_decimal(10.12345, 2) == Decimal('10.12')
    assert round_decimal(10.128, 2) == Decimal('10.13')
    assert round_decimal(10.5, 0) == Decimal('11')
    assert round_decimal(10.4, 0) == Decimal('10')
    assert round_decimal(0.000123, 5) == Decimal('0.00012')
    assert round_decimal(0.000128, 5) == Decimal('0.00013')
    assert round_decimal(123, 0) == Decimal('123')

def test_calculate_order_quantity():
    # Test with typical values
    assert calculate_order_quantity(100, 20000, 0.001, 0.0001) == 0.005
    assert calculate_order_quantity(10, 50000, 0.0001, 0.0001) == 0.0002

    # Test with quantity less than min_qty
    assert calculate_order_quantity(1, 20000, 0.001, 0.0001) == 0.001

    # Test with quantity not a perfect multiple of qty_step
    assert calculate_order_quantity(101, 20000, 0.001, 0.0001) == 0.005

    # Test with different qty_step precision
    assert calculate_order_quantity(100, 20000, 0.001, 0.01) == 0.00
    assert calculate_order_quantity(200, 20000, 0.001, 0.01) == 0.01

    # Test edge cases
    with pytest.raises(ValueError):
        calculate_order_quantity(0, 100, 0.001, 0.0001)
    with pytest.raises(ValueError):
        calculate_order_quantity(100, 0, 0.001, 0.0001)
    with pytest.raises(ValueError):
        calculate_order_quantity(100, 100, 0, 0.0001)
    with pytest.raises(ValueError):
        calculate_order_quantity(100, 100, 0.001, 0)
