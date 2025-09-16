# tests/test_market_making_strategy.py
#
# This file will contain the unit tests for the MarketMakingStrategy.
# The tests will verify the strategy's logic under various simulated
# market conditions and bot states.
import logging
import os

# Adjust path to import from the root of the project
import sys
from decimal import Decimal
from typing import Any

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from algobots_types import OrderBlock
from strategies.marketmakingstrategy import MarketMakingStrategy

# A mock logger that can be used in tests
strategy_logger = logging.getLogger('test_market_making_strategy')

@pytest.fixture
def market_scenario_factory():
    """A pytest fixture factory to create configurable market scenarios for testing the strategy.
    This allows tests to easily set up different conditions (e.g., market price,
    bot position, S/R levels) to verify the strategy's behavior.
    """
    def _create_scenario(
        current_price: str = '100.0',
        atr: str = '1.0',
        ehlers_smoother: str = '99.0',
        current_position_side: str = 'NONE',
        current_position_size: str = '0.0',
        entry_price: str = '0.0',
        support_levels: list[dict[str, Any]] = None,
        resistance_levels: list[dict[str, Any]] = None,
        active_bull_obs: list[OrderBlock] = None,
        active_bear_obs: list[OrderBlock] = None
    ):
        """Creates a market scenario dictionary for a test.

        Args:
            current_price (str): The current market price.
            atr (str): The current ATR value.
            ehlers_smoother (str): The current Ehlers Super Smoother value.
            current_position_side (str): 'NONE', 'LONG', or 'SHORT'.
            current_position_size (str): The size of the current position.
            entry_price (str): The entry price of the current position.
            support_levels (List): A list of support level dicts.
            resistance_levels (List): A list of resistance level dicts.
            active_bull_obs (List): A list of bullish OrderBlock dicts.
            active_bear_obs (List): A list of bearish OrderBlock dicts.

        Returns:
            Dict: A dictionary containing all the components needed for a strategy test.
        """
        # Set default values for lists if they are None
        if support_levels is None:
            support_levels = []
        if resistance_levels is None:
            resistance_levels = []
        if active_bull_obs is None:
            active_bull_obs = []
        if active_bear_obs is None:
            active_bear_obs = []

        # 1. Create the mock pandas DataFrame
        data = {
            'timestamp': [pd.to_datetime('2023-01-01 12:00:00', utc=True)],
            'close': [Decimal(current_price)],
            'atr': [Decimal(atr)],
            'ehlers_supersmoother': [Decimal(ehlers_smoother)]
        }
        df = pd.DataFrame(data).set_index('timestamp')

        # 2. Instantiate the strategy with default parameters
        strategy = MarketMakingStrategy(logger=strategy_logger)

        # 3. Prepare the kwargs dictionary with the bot's current state
        kwargs = {
            'current_position_side': current_position_side,
            'current_position_size': Decimal(current_position_size),
            'entry_price': Decimal(entry_price)
        }

        # 4. Return all components in a dictionary
        return {
            "strategy": strategy,
            "df": df,
            "resistance_levels": resistance_levels,
            "support_levels": support_levels,
            "active_bull_obs": active_bull_obs,
            "active_bear_obs": active_bear_obs,
            "kwargs": kwargs
        }
    return _create_scenario


def test_generate_signals_in_neutral_state(market_scenario_factory):
    """Tests the basic signal generation when the bot has no position.
    It should generate one BUY and one SELL limit order symmetrically
    around a skewed mid-price.
    """
    # Arrange
    # Using default factory settings for a neutral state.
    # Price (100) > Smoother (99) implies a slight uptrend, so we expect a slight upward skew.
    scenario = market_scenario_factory()
    strategy = scenario['strategy']

    # Act
    signals = strategy.generate_signals(
        df=scenario['df'],
        resistance_levels=scenario['resistance_levels'],
        support_levels=scenario['support_levels'],
        active_bull_obs=scenario['active_bull_obs'],
        active_bear_obs=scenario['active_bear_obs'],
        **scenario['kwargs']
    )

    # Assert
    # 1. We should have exactly two signals: one buy (bid) and one sell (ask).
    assert len(signals) == 2

    buy_signals = [s for s in signals if s[0] == 'BUY_LIMIT']
    sell_signals = [s for s in signals if s[0] == 'SELL_LIMIT']

    assert len(buy_signals) == 1
    assert len(sell_signals) == 1

    bid_signal = buy_signals[0]
    ask_signal = sell_signals[0]

    # 2. Check the signal structure and content
    assert bid_signal[0] == 'BUY_LIMIT'
    assert bid_signal[3]['order_type'] == 'LIMIT'
    assert bid_signal[3]['strategy_id'] == 'MM_BID'

    assert ask_signal[0] == 'SELL_LIMIT'
    assert ask_signal[3]['order_type'] == 'LIMIT'
    assert ask_signal[3]['strategy_id'] == 'MM_ASK'

    # 3. Verify the calculated prices based on default strategy parameters
    # Manual calculation for verification:
    # current_price = 100, smoother = 99 -> uptrend
    # inventory_skew_intensity = 5 BPS -> trend_skew_factor = 0.0005
    # skewed_mid_price = 100 * (1 + 0.0005) = 100.05
    # atr = 1, atr_spread_multiplier = 0.5 -> atr_spread_adj = (1/100)*0.5*10000 = 50 BPS
    # base_spread = 20 BPS, max_spread = 50 BPS -> dynamic_spread = min(50, 20 + 50) = 50 BPS
    # spread_factor = 50 / 20000 = 0.0025
    # expected_bid = 100.05 * (1 - 0.0025) = 99.799875
    # expected_ask = 100.05 * (1 + 0.0025) = 100.300125

    expected_bid_price = Decimal('99.799875')
    expected_ask_price = Decimal('100.300125')

    assert bid_signal[1] == pytest.approx(expected_bid_price)
    assert ask_signal[1] == pytest.approx(expected_ask_price)

    # 4. Verify the order quantity
    # Default is volatility adjusted. base_qty = 0.01, sensitivity = 0.5
    # normalized_atr = 1 / 100 = 0.01
    # size_multiplier = 1 / (1 + 0.01 * 0.5) = 1 / 1.005 approx 0.995
    # adjusted_size = 0.01 * 0.995 = 0.00995
    # min_order_qty = 0.005, max_order_qty = 0.1
    # So quantity should be ~0.00995
    expected_quantity = Decimal('0.01') / (Decimal('1') + (Decimal('1')/Decimal('100')) * Decimal('0.5'))
    assert bid_signal[3]['quantity'] == pytest.approx(expected_quantity)
    assert ask_signal[3]['quantity'] == pytest.approx(expected_quantity)


def test_generate_signals_with_long_inventory_skew(market_scenario_factory):
    """Tests that when holding a long position, the strategy skews its bid and ask
    prices downwards to encourage selling and discourage further buying.
    This test disables hedging to isolate the skewing logic.
    """
    # Arrange
    # Create a scenario with a significant long position (0.04 out of a max 0.05)
    # Price (100) < Smoother (101) implies a downtrend, which should also skew prices down.
    scenario = market_scenario_factory(
        ehlers_smoother='101.0', # Downtrend
        current_position_side='LONG',
        current_position_size='0.04'
    )

    # Instantiate a strategy with hedging disabled to isolate the skew logic
    strategy = MarketMakingStrategy(logger=strategy_logger, hedge_ratio=Decimal('0'))

    # Act
    signals = strategy.generate_signals(
        df=scenario['df'],
        resistance_levels=scenario['resistance_levels'],
        support_levels=scenario['support_levels'],
        active_bull_obs=scenario['active_bull_obs'],
        active_bear_obs=scenario['active_bear_obs'],
        **scenario['kwargs']
    )

    # Assert
    # With hedging disabled, we expect exactly two signals.
    assert len(signals) == 2
    bid_signal = [s for s in signals if s[0] == 'BUY_LIMIT'][0]
    ask_signal = [s for s in signals if s[0] == 'SELL_LIMIT'][0]

    # Manual calculation for verification:
    # current_price = 100, smoother = 101 -> downtrend -> trend_skew_factor = 0.0005
    # skewed_mid_price_after_trend = 100 * (1 - 0.0005) = 99.95
    # position_size = 0.04, max_size = 0.05 -> inventory_ratio = 0.8
    # inventory_skew_intensity = 5 -> inventory_skew_adj = (100 * 5 / 10000) * 0.8 = 0.04
    # final_skewed_mid_price = 99.95 - 0.04 = 99.91
    # spread_factor = 0.0025 (from previous test, remains the same)
    # expected_bid = 99.91 * (1 - 0.0025) = 99.660225
    # expected_ask = 99.91 * (1 + 0.0025) = 100.159775

    expected_bid_price = Decimal('99.660225')
    expected_ask_price = Decimal('100.159775')

    assert bid_signal[1] == pytest.approx(expected_bid_price)
    assert ask_signal[1] == pytest.approx(expected_ask_price)

    # Also, as a sanity check, assert that these prices are lower than they would be
    # in a neutral inventory scenario with the same downtrend.
    neutral_strategy = MarketMakingStrategy(logger=strategy_logger, hedge_ratio=Decimal('0'))
    neutral_scenario_data = {
        'df': scenario['df'],
        'resistance_levels': [],
        'support_levels': [],
        'active_bull_obs': [],
        'active_bear_obs': [],
        'kwargs': {'current_position_side': 'NONE', 'current_position_size': Decimal('0'), 'entry_price': Decimal('0')}
    }
    neutral_signals = neutral_strategy.generate_signals(**neutral_scenario_data)
    neutral_bid_price = [s for s in neutral_signals if s[0] == 'BUY_LIMIT'][0][1]
    neutral_ask_price = [s for s in neutral_signals if s[0] == 'SELL_LIMIT'][0][1]

    assert bid_signal[1] < neutral_bid_price
    assert ask_signal[1] < neutral_ask_price


def test_exit_signal_for_stop_loss_trigger(market_scenario_factory):
    """Tests that a "panic exit" signal is generated when the price breaches
    the dynamic ATR-based stop-loss for a long position.
    """
    # Arrange
    # Default stop_loss_atr_multiplier is 2.5
    # entry_price = 105, atr = 2.0 -> stop_loss_price = 105 - (2.0 * 2.5) = 100.0
    # We set the current price to 99.9, which is below the stop loss.
    scenario = market_scenario_factory(
        current_price='99.9',
        atr='2.0',
        current_position_side='LONG',
        current_position_size='0.01',
        entry_price='105.0'
    )
    strategy = scenario['strategy']

    # Act
    exit_signals = strategy.generate_exit_signals(
        df=scenario['df'],
        # current_position_side is passed via kwargs, so it's not needed here.
        active_bull_obs=scenario['active_bull_obs'],
        active_bear_obs=scenario['active_bear_obs'],
        **scenario['kwargs']
    )

    # Assert
    # 1. We should get exactly one signal.
    assert len(exit_signals) == 1

    exit_signal = exit_signals[0]

    # 2. It should be a Market Sell order to close the position.
    assert exit_signal[0] == 'SELL_MARKET'

    # 3. The info dict should identify it as a panic exit.
    signal_info = exit_signal[3]
    assert signal_info['order_type'] == 'MARKET'
    assert signal_info['strategy_id'] == 'MM_PANIC_EXIT'

    # 4. The quantity should be the entire position size.
    assert signal_info['quantity'] == scenario['kwargs']['current_position_size']


def test_exit_signal_for_rebalance_trigger(market_scenario_factory):
    """Tests that a rebalance signal is generated when the position size
    exceeds the rebalance_threshold.
    """
    # Arrange
    # The default rebalance_threshold is 0.03. We set the position size
    # just above this to trigger the rebalance logic.
    # We also ensure the price is not near the stop-loss.
    scenario = market_scenario_factory(
        current_price='101.0',
        atr='1.0',
        current_position_side='LONG',
        current_position_size='0.031', # > 0.03 threshold
        entry_price='100.0'
    )
    # The strategy from the scenario has default params, which is what we want.
    strategy = scenario['strategy']

    # Act
    exit_signals = strategy.generate_exit_signals(
        df=scenario['df'],
        active_bull_obs=scenario['active_bull_obs'],
        active_bear_obs=scenario['active_bear_obs'],
        **scenario['kwargs']
    )

    # Assert
    # 1. We should get exactly one signal.
    assert len(exit_signals) == 1

    exit_signal = exit_signals[0]

    # 2. It should be a Market Sell order to close the position.
    assert exit_signal[0] == 'SELL_MARKET'

    # 3. The info dict should identify it as a rebalance.
    signal_info = exit_signal[3]
    assert signal_info['order_type'] == 'MARKET'
    assert signal_info['strategy_id'] == 'MM_REBALANCE'

    # 4. The quantity should be the entire position size.
    assert signal_info['quantity'] == scenario['kwargs']['current_position_size']
