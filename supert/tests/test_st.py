import logging
import os

# Import classes and enums from st.py
# Assuming st.py is in the parent directory
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from st import (
    Category,
    Config,
    InstrumentSpecs,
    OrderSizingCalculator,
    OrderType,
    PrecisionManager,
    Signal,
    SupertrendBot,
    TrailingStopManager,
    setup_logger,
)


# Mock the HTTP session for Bybit API calls
@pytest.fixture
def mock_bybit_session():
    """Fixture to provide a mocked Bybit HTTP session."""
    session = MagicMock()
    return session

@pytest.fixture
def mock_logger():
    """Fixture to provide a mocked logger."""
    logger = MagicMock(spec=logging.Logger)
    logger.handlers = [] # Ensure no actual handlers are added during tests
    return logger

@pytest.fixture
def default_config():
    """Fixture to provide a default Config instance."""
    return Config()

# =====================================================================
# Unit Tests for setup_logger
# =====================================================================

def test_setup_logger_initialization(default_config):
    logger = setup_logger(default_config)
    assert isinstance(logger, logging.Logger)
    assert logger.name == 'SupertrendBot'
    assert logger.level == logging.INFO # Default log level
    assert len(logger.handlers) == 2 # FileHandler and StreamHandler

def test_setup_logger_prevents_duplicate_handlers(default_config):
    # Call once to add handlers
    logger1 = setup_logger(default_config)
    initial_handlers_count = len(logger1.handlers)

    # Call again, should not add more handlers
    logger2 = setup_logger(default_config)
    assert len(logger2.handlers) == initial_handlers_count

# =====================================================================
# Unit Tests for PrecisionManager
# =====================================================================

@pytest.fixture
def precision_manager_instance(mock_bybit_session, mock_logger):
    """Fixture for PrecisionManager instance with mocked session."""
    # Mock load_all_instruments to prevent actual API calls during init
    with patch.object(PrecisionManager, 'load_all_instruments', return_value=None):
        pm = PrecisionManager(mock_bybit_session, mock_logger)
        # Manually set some instrument specs for testing
        pm.instruments['BTCUSDT'] = InstrumentSpecs(
            symbol='BTCUSDT', category='linear', base_currency='BTC', quote_currency='USDT', status='Trading',
            min_price=Decimal('0.01'), max_price=Decimal('1000000'), tick_size=Decimal('0.01'),
            min_order_qty=Decimal('0.001'), max_order_qty=Decimal('100'), qty_step=Decimal('0.001'),
            min_leverage=Decimal('1'), max_leverage=Decimal('100'), leverage_step=Decimal('1'),
            max_position_value=Decimal('10000000'), min_position_value=Decimal('1'),
            contract_value=Decimal('1'), is_inverse=False, maker_fee=Decimal('0.0001'), taker_fee=Decimal('0.0006')
        )
        pm.instruments['TRUMPUSDT'] = InstrumentSpecs(
            symbol='TRUMPUSDT', category='linear', base_currency='TRUMP', quote_currency='USDT', status='Trading',
            min_price=Decimal('0.00001'), max_price=Decimal('1000'), tick_size=Decimal('0.00001'),
            min_order_qty=Decimal('1'), max_order_qty=Decimal('1000000'), qty_step=Decimal('1'),
            min_leverage=Decimal('1'), max_leverage=Decimal('50'), leverage_step=Decimal('1'),
            max_position_value=Decimal('5000000'), min_position_value=Decimal('1'),
            contract_value=Decimal('1'), is_inverse=False, maker_fee=Decimal('0.0001'), taker_fee=Decimal('0.0006')
        )
        return pm

def test_precision_manager_parse_instrument_specs(mock_bybit_session, mock_logger):
    pm = PrecisionManager(mock_bybit_session, mock_logger)

    # Sample instrument info from Bybit API
    inst_info = {
        'symbol': 'BTCUSDT',
        'baseCoin': 'BTC',
        'quoteCoin': 'USDT',
        'status': 'Trading',
        'lotSizeFilter': {
            'minOrderQty': '0.001',
            'maxOrderQty': '100',
            'qtyStep': '0.001',
            'maxMktOrderQty': '10000000'
        },
        'priceFilter': {
            'minPrice': '0.01',
            'maxPrice': '1000000',
            'tickSize': '0.01'
        },
        'leverageFilter': {
            'minLeverage': '1',
            'maxLeverage': '100',
            'leverageStep': '1'
        },
        'makerFeeRate': '0.0001',
        'takerFeeRate': '0.0006',
        'contractValue': '1'
    }

    specs = pm._parse_instrument_specs(inst_info, 'linear')

    assert specs.symbol == 'BTCUSDT'
    assert specs.category == 'linear'
    assert specs.min_price == Decimal('0.01')
    assert specs.tick_size == Decimal('0.01')
    assert specs.min_order_qty == Decimal('0.001')
    assert specs.qty_step == Decimal('0.001')
    assert specs.maker_fee == Decimal('0.0001')

def test_precision_manager_parse_instrument_specs_missing_filters(mock_bybit_session, mock_logger):
    pm = PrecisionManager(mock_bybit_session, mock_logger)

    # Sample instrument info with missing filters
    inst_info = {
        'symbol': 'ETHUSDT',
        'baseCoin': 'ETH',
        'quoteCoin': 'USDT',
        'status': 'Trading',
        # Missing lotSizeFilter, priceFilter, leverageFilter
    }

    specs = pm._parse_instrument_specs(inst_info, 'linear')

    assert specs.symbol == 'ETHUSDT'
    assert specs.min_price == Decimal('0') # Should use default '0'
    assert specs.tick_size == Decimal('0.01') # Should use default '0.01'
    assert specs.min_order_qty == Decimal('0') # Should use default '0'

def test_precision_manager_round_price(precision_manager_instance):
    pm = precision_manager_instance


    # Test with BTCUSDT (tick_size=0.01)
    assert pm.round_price('BTCUSDT', 45000.123) == Decimal('45000.12')
    assert pm.round_price('BTCUSDT', 45000.129) == Decimal('45000.12') # Should round down
    assert pm.round_price('BTCUSDT', 45000.00) == Decimal('45000.00')

    # Test with TRUMPUSDT (tick_size=0.00001)
    assert pm.round_price('TRUMPUSDT', 0.512345) == Decimal('0.51234')
    assert pm.round_price('TRUMPUSDT', 0.512349) == Decimal('0.51234')

def test_precision_manager_round_quantity(precision_manager_instance):
    pm = precision_manager_instance


    # Test with BTCUSDT (qty_step=0.001)
    assert pm.round_quantity('BTCUSDT', 0.00123) == Decimal('0.001')
    assert pm.round_quantity('BTCUSDT', 0.00199) == Decimal('0.001') # Should round down
    assert pm.round_quantity('BTCUSDT', 1.000) == Decimal('1.000')

    # Test with TRUMPUSDT (qty_step=1)
    assert pm.round_quantity('TRUMPUSDT', 123.45) == Decimal('123')
    assert pm.round_quantity('TRUMPUSDT', 123.99) == Decimal('123')

# =====================================================================
# Unit Tests for OrderSizingCalculator
# =====================================================================

@pytest.fixture
def order_sizer_instance(precision_manager_instance, mock_logger):
    """Fixture for OrderSizingCalculator instance."""
    return OrderSizingCalculator(precision_manager_instance, mock_logger)

def test_calculate_position_size_fixed_risk_buy(order_sizer_instance, precision_manager_instance):
    osc = order_sizer_instance


    symbol = 'BTCUSDT'
    account_balance = 10000.0
    risk_percent = 1.0 # 1% risk
    entry_price = 50000.0
    stop_loss_price = 49500.0 # 1% below entry
    leverage = 10.0

    # Expected risk amount: 10000 * 0.01 = 100 USDT
    # Stop distance: 500 USDT
    # Stop distance pct: 500 / 50000 = 0.01 (1%)
    # Position value needed: 100 / 0.01 = 10000 USDT
    # Quantity: 10000 / 50000 = 0.2 BTC
    # Rounded quantity (qty_step=0.001): 0.200 BTC

    calculated_qty = osc.calculate_position_size_fixed_risk(
        symbol, account_balance, risk_percent, entry_price, stop_loss_price, leverage
    )

    assert calculated_qty == Decimal('0.200')

def test_calculate_position_size_fixed_risk_sell(order_sizer_instance, precision_manager_instance):
    osc = order_sizer_instance


    symbol = 'BTCUSDT'
    account_balance = 10000.0
    risk_percent = 1.0 # 1% risk
    entry_price = 50000.0
    stop_loss_price = 50500.0 # 1% above entry for short
    leverage = 10.0

    # Expected risk amount: 100 USDT
    # Stop distance: 500 USDT
    # Stop distance pct: 0.01 (1%)
    # Position value needed: 100 / 0.01 = 10000 USDT
    # Quantity: 10000 / 50000 = 0.2 BTC
    # Rounded quantity (qty_step=0.001): 0.200 BTC

    calculated_qty = osc.calculate_position_size_fixed_risk(
        symbol, account_balance, risk_percent, entry_price, stop_loss_price, leverage
    )

    assert calculated_qty == Decimal('0.200')

def test_calculate_position_size_fixed_risk_zero_stop_distance(order_sizer_instance, mock_logger):
    osc = order_sizer_instance

    symbol = 'BTCUSDT'
    account_balance = 10000.0
    risk_percent = 1.0
    entry_price = 50000.0
    stop_loss_price = 50000.0 # Zero stop distance
    leverage = 10.0

    calculated_qty = osc.calculate_position_size_fixed_risk(
        symbol, account_balance, risk_percent, entry_price, stop_loss_price, leverage
    )

    assert calculated_qty is None
    mock_logger.warning.assert_called_with(f"Stop loss distance is zero for {symbol}. Cannot calculate size.")

def test_calculate_position_size_fixed_risk_below_min_qty(order_sizer_instance, precision_manager_instance, mock_logger):
    osc = order_sizer_instance
    pm = precision_manager_instance


    symbol = 'BTCUSDT'
    account_balance = 0.1 # Very small balance to ensure quantity is below min_order_qty
    risk_percent = 0.1 # Very low risk
    entry_price = 50000.0
    stop_loss_price = 49999.0 # Tiny stop loss
    leverage = 1.0

    # This should result in a very small quantity, below min_order_qty (0.001)
    calculated_qty = osc.calculate_position_size_fixed_risk(
        symbol, account_balance, risk_percent, entry_price, stop_loss_price, leverage
    )

    # Should be rounded up to min_order_qty
    assert calculated_qty == pm.instruments[symbol].min_order_qty
    mock_logger.warning.assert_called_with(f"Calculated quantity {calculated_qty} for {symbol} is below minimum {pm.instruments[symbol].min_order_qty}.")

# =====================================================================
# Unit Tests for SupertrendBot - Indicator Calculation
# =====================================================================

@pytest.fixture
def supertrend_bot_instance(default_config, mock_bybit_session, mock_logger):
    """Fixture for SupertrendBot instance with mocked dependencies."""
    # Mock dependencies during SupertrendBot init
    with patch.object(PrecisionManager, 'load_all_instruments', return_value=None), \
         patch('st.PrecisionManager', return_value=MagicMock(spec=PrecisionManager)), \
         patch('st.OrderSizingCalculator', return_value=MagicMock(spec=OrderSizingCalculator)), \
         patch('st.TrailingStopManager', return_value=MagicMock(spec=TrailingStopManager)):

        bot = SupertrendBot(default_config)
        bot.session = mock_bybit_session # Ensure the session is the mocked one
        bot.logger = mock_logger # Ensure the logger is the mocked one

        # Manually set some instrument specs for testing in PrecisionManager mock
        bot.precision_manager.get_specs.return_value = InstrumentSpecs(
            symbol='BTCUSDT', category='linear', base_currency='BTC', quote_currency='USDT', status='Trading',
            min_price=Decimal('0.01'), max_price=Decimal('1000000'), tick_size=Decimal('0.01'),
            min_order_qty=Decimal('0.001'), max_order_qty=Decimal('100'), qty_step=Decimal('0.001'),
            min_leverage=Decimal('1'), max_leverage=Decimal('100'), leverage_step=Decimal('1'),
            max_position_value=Decimal('10000000'), min_position_value=Decimal('1'),
            contract_value=Decimal('1'), is_inverse=False, maker_fee=Decimal('0.0001'), taker_fee=Decimal('0.0006')
        )
        return bot

def test_calculate_indicators(supertrend_bot_instance):
    bot = supertrend_bot_instance

    # Sample DataFrame for testing indicators
    data = {
        'timestamp': [datetime(2023, 1, 1, 0, i) for i in range(50)],
        'open': [10 + i for i in range(25)] + [34 - i for i in range(25)],
        'high': [10.5 + i for i in range(25)] + [34.5 - i for i in range(25)],
        'low': [9.5 + i for i in range(25)] + [33.5 - i for i in range(25)],
        'close': [10 + i for i in range(25)] + [34 - i for i in range(25)],
        'volume': [100] * 50,
        'turnover': [1000] * 50
    }
    df = pd.DataFrame(data).set_index('timestamp')

    processed_df = bot.calculate_indicators(df.copy())

    assert 'atr' in processed_df.columns
    assert 'supertrend' in processed_df.columns
    assert 'supertrend_direction' in processed_df.columns
    assert not processed_df.isnull().values.any() # No NaNs after ffill and fillna

def test_generate_signal_strong_buy(supertrend_bot_instance):
    bot = supertrend_bot_instance

    # Scenario: Trend flips from down to up
    data = {
        'timestamp': [datetime(2023, 1, 1, 0, 0), datetime(2023, 1, 1, 0, 1)],
        'open': [10, 11], 'high': [10, 11], 'low': [10, 11], 'close': [10, 11], 'volume': [1, 1], 'turnover': [1, 1],
        'supertrend': [10.5, 10.5], # Supertrend line
        'supertrend_direction': [-1, 1] # Flip from downtrend to uptrend
    }
    df = pd.DataFrame(data).set_index('timestamp')

    signal = bot.generate_signal(df)
    assert signal == Signal.STRONG_BUY

def test_generate_signal_buy(supertrend_bot_instance):
    bot = supertrend_bot_instance

    # Scenario: Already in uptrend, price above ST line
    data = {
        'timestamp': [datetime(2023, 1, 1, 0, 0), datetime(2023, 1, 1, 0, 1)],
        'open': [10, 11], 'high': [10, 11], 'low': [10, 11], 'close': [10, 11], 'volume': [1, 1], 'turnover': [1, 1],
        'supertrend': [9.5, 9.5], # Supertrend line
        'supertrend_direction': [1, 1] # Already in uptrend
    }
    df = pd.DataFrame(data).set_index('timestamp')

    signal = bot.generate_signal(df)
    assert signal == Signal.BUY

def test_generate_signal_strong_sell(supertrend_bot_instance):
    bot = supertrend_bot_instance

    # Scenario: Trend flips from up to down
    data = {
        'timestamp': [datetime(2023, 1, 1, 0, 0), datetime(2023, 1, 1, 0, 1)],
        'open': [11, 10], 'high': [11, 10], 'low': [11, 10], 'close': [11, 10], 'volume': [1, 1], 'turnover': [1, 1],
        'supertrend': [10.5, 10.5], # Supertrend line
        'supertrend_direction': [1, -1] # Flip from uptrend to downtrend
    }
    df = pd.DataFrame(data).set_index('timestamp')

    signal = bot.generate_signal(df)
    assert signal == Signal.STRONG_SELL

def test_generate_signal_sell(supertrend_bot_instance):
    bot = supertrend_bot_instance

    # Scenario: Already in downtrend, price below ST line
    data = {
        'timestamp': [datetime(2023, 1, 1, 0, 0), datetime(2023, 1, 1, 0, 1)],
        'open': [11, 10], 'high': [11, 10], 'low': [11, 10], 'close': [11, 10], 'volume': [1, 1], 'turnover': [1, 1],
        'supertrend': [10.5, 10.5], # Supertrend line
        'supertrend_direction': [-1, -1] # Already in downtrend
    }
    df = pd.DataFrame(data).set_index('timestamp')

    signal = bot.generate_signal(df)
    assert signal == Signal.SELL

def test_generate_signal_neutral_empty_df(supertrend_bot_instance):
    bot = supertrend_bot_instance
    df = pd.DataFrame()
    signal = bot.generate_signal(df)
    assert signal == Signal.NEUTRAL

def test_generate_signal_neutral_insufficient_data(supertrend_bot_instance):
    bot = supertrend_bot_instance
    data = {
        'timestamp': [datetime(2023, 1, 1, 0, 0)],
        'open': [10], 'high': [10], 'low': [10], 'close': [10], 'volume': [1], 'turnover': [1],
        'supertrend': [10], 'supertrend_direction': [1]
    }
    df = pd.DataFrame(data).set_index('timestamp')
    signal = bot.generate_signal(df)
    assert signal == Signal.NEUTRAL
