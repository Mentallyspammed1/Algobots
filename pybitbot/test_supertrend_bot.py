import asyncio
import os

# Add the bot's directory to the Python path
import sys
import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from supertrend_bot import (
    BybitTradingBot,
    Config,
    Position,
    StrategySignal,
    SupertrendStrategy,
)

# --- Test Data Fixtures ---


def create_test_dataframe(rows=50):
    """Creates a sample DataFrame for testing."""
    data = {
        "open": np.random.uniform(30000, 30100, size=rows),
        "high": np.random.uniform(30100, 30200, size=rows),
        "low": np.random.uniform(29900, 30000, size=rows),
        "close": np.random.uniform(30000, 30200, size=rows),
        "volume": np.random.uniform(100, 500, size=rows),
        "turnover": np.random.uniform(3000000, 5000000, size=rows),
    }
    index = pd.to_datetime(pd.date_range(start="2023-01-01", periods=rows, freq="15T"))
    return pd.DataFrame(data, index=index)


# --- Test Cases ---


class TestSupertrendStrategy(unittest.TestCase):
    def setUp(self):
        self.config = Config(
            strategy_params={"supertrend_period": 10, "supertrend_multiplier": 3.0},
        )
        self.strategy = SupertrendStrategy(symbol="BTCUSDT", config=self.config)
        self.test_data = create_test_dataframe()

    def test_calculate_indicators(self):
        """Test that indicators are calculated and added to the DataFrame."""
        market_data = {self.config.timeframe: self.test_data.copy()}

        async def run_test():
            await self.strategy.calculate_indicators(market_data)
            df = self.strategy.indicators[self.config.timeframe]

            self.assertIn("atr", df.columns)
            self.assertIn("supertrend", df.columns)
            self.assertIn("in_uptrend", df.columns)
            self.assertFalse(df[["atr", "supertrend"]].isnull().any().any())

        asyncio.run(run_test())

    def test_generate_buy_signal(self):
        """Test the generation of a BUY signal on trend reversal."""
        df = create_test_dataframe()
        # Manually create a downtrend condition followed by a BUY crossover
        df["supertrend"] = 31000
        df["in_uptrend"] = False
        df.iloc[-1, df.columns.get_loc("close")] = (
            31500  # Price crosses above supertrend
        )

        market_data = {self.config.timeframe: df}

        # Mock calculate_indicators to control the data
        self.strategy.calculate_indicators = AsyncMock()
        self.strategy.indicators = market_data

        async def run_test():
            signal = await self.strategy.generate_signal(market_data)
            self.assertIsNotNone(signal)
            self.assertEqual(signal.action, "BUY")
            self.assertIsNotNone(signal.stop_loss)

        asyncio.run(run_test())

    def test_generate_sell_signal(self):
        """Test the generation of a SELL signal on trend reversal."""
        df = create_test_dataframe()
        # Manually create an uptrend condition followed by a SELL crossover
        df["supertrend"] = 29000
        df["in_uptrend"] = True
        df.iloc[-1, df.columns.get_loc("close")] = (
            28500  # Price crosses below supertrend
        )

        market_data = {self.config.timeframe: df}

        # Mock calculate_indicators
        self.strategy.calculate_indicators = AsyncMock()
        self.strategy.indicators = market_data

        # To make this test work, we need to simulate the state change
        # The logic is `if previous['in_uptrend'] and not current['in_uptrend']`
        # The mock doesn't run the real calculation, so we set the state manually
        df_for_signal = df.copy()
        df_for_signal.iloc[-1, df_for_signal.columns.get_loc("in_uptrend")] = False
        self.strategy.indicators = {self.config.timeframe: df_for_signal}

        async def run_test():
            signal = await self.strategy.generate_signal(market_data)
            self.assertIsNotNone(signal)
            self.assertEqual(signal.action, "SELL")
            self.assertIsNotNone(signal.stop_loss)

        asyncio.run(run_test())


class TestBybitTradingBot(unittest.TestCase):
    def setUp(self):
        """Set up a mock environment for the bot."""
        self.config = Config(testnet=True, symbol="BTCUSDT")
        self.strategy = SupertrendStrategy(
            symbol=self.config.symbol, config=self.config,
        )

        # Mock pybit clients
        self.mock_session = MagicMock()
        self.mock_ws = MagicMock()

        # Configure mock responses
        self.mock_session.get_instruments_info.return_value = {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "priceFilter": {"tickSize": "0.1"},
                        "lotSizeFilter": {"qtyStep": "0.001"},
                    },
                ],
            },
        }
        self.mock_session.get_kline.return_value = {
            "retCode": 0,
            "result": {
                "list": [
                    [
                        pd.Timestamp.now().timestamp() * 1000,
                        30000,
                        31000,
                        29000,
                        30500,
                        100,
                        3000000,
                    ],
                ]
                * 50,
            },
        }
        self.mock_session.get_wallet_balance.return_value = {
            "retCode": 0,
            "result": {"list": [{"totalEquity": "5000"}]},
        }
        self.mock_session.get_positions.return_value = {
            "retCode": 0,
            "result": {"list": [{"symbol": "BTCUSDT", "size": "0"}]},
        }
        self.mock_session.place_order = MagicMock(
            return_value={"retCode": 0, "result": {"orderId": "test-order-id-123"}},
        )

        self.bot = BybitTradingBot(
            config=self.config,
            strategy=self.strategy,
            session=self.mock_session,
            ws=self.mock_ws,
        )

    def test_initialize(self):
        """Test the bot's initialization sequence."""

        async def run_test():
            await self.bot.initialize()
            self.mock_session.get_instruments_info.assert_called_once()
            self.mock_session.get_kline.assert_called_once()
            self.mock_session.get_wallet_balance.assert_called_once()
            self.mock_session.get_positions.assert_called_once()
            self.assertIsNotNone(self.bot.market_info)
            self.assertFalse(self.bot.market_data[self.config.timeframe].empty)
            self.assertEqual(self.bot.balance, Decimal("5000"))

        asyncio.run(run_test())

    def test_calculate_position_size(self):
        """Test the risk management calculation."""
        self.bot.balance = Decimal("10000")  # Set balance for test
        self.config.risk_per_trade = 0.02  # 2%
        self.config.leverage = 10

        size = self.bot._calculate_position_size(current_price=50000)
        # Expected: (10000 * 0.02) / 50000 * 10 = 0.04
        self.assertAlmostEqual(size, 0.04)

    def test_process_signal_opens_new_position(self):
        """Test that a signal correctly places a new order."""

        async def run_test():
            await self.bot.initialize()  # Initialize bot to get market_info etc.
            self.bot.position = None  # Ensure no existing position
            self.bot.market_data[self.config.timeframe] = (
                create_test_dataframe()
            )  # Ensure data exists

            buy_signal = StrategySignal(action="BUY", symbol="BTCUSDT", stop_loss=29000)

            await self.bot.process_signal(buy_signal)

            self.mock_session.place_order.assert_called_once()
            call_args = self.mock_session.place_order.call_args[1]
            self.assertEqual(call_args["side"], "Buy")
            self.assertEqual(call_args["stopLoss"], "29000.0")

        asyncio.run(run_test())

    def test_process_signal_closes_opposite_position(self):
        """Test that a new signal closes an existing opposite position first."""

        async def run_test():
            await self.bot.initialize()
            # Setup existing short position
            self.bot.position = Position(
                symbol="BTCUSDT",
                side="Sell",
                size=Decimal("0.1"),
                avg_price=Decimal(30000),
                unrealized_pnl=Decimal(0),
                mark_price=Decimal(30000),
                leverage=10,
            )
            self.bot.market_data[self.config.timeframe] = create_test_dataframe()

            buy_signal = StrategySignal(action="BUY", symbol="BTCUSDT", stop_loss=29000)

            await self.bot.process_signal(buy_signal)

            # Should be called twice: once to close, once to open
            self.assertEqual(self.mock_session.place_order.call_count, 2)

            # First call is to close the short (i.e., a BUY order)
            first_call_args = self.mock_session.place_order.call_args_list[0].kwargs
            self.assertEqual(first_call_args["side"], "Buy")
            self.assertEqual(first_call_args["qty"], "0.100")  # Closing the exact size

            # Second call is to open the new long position
            second_call_args = self.mock_session.place_order.call_args_list[1].kwargs
            self.assertEqual(second_call_args["side"], "Buy")
            self.assertNotEqual(
                second_call_args["qty"], "0.100",
            )  # Should be a newly calculated size

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
