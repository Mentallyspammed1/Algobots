# Ensure the root directory is in the Python path for imports
import sys
import time
import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd

sys.path.insert(0, "/data/data/com.termux/files/home/Algobots")

# Import the module and classes to be tested
from PSG import PyrmethusBot

import config


# --- Helper function to create sample DataFrame ---
def create_sample_df(rows=100):
    """Creates a sample DataFrame for testing."""
    now_ms = int(time.time() * 1000)
    start_time = now_ms - (rows * 1000)

    timestamps = pd.to_datetime(
        range(start_time, start_time + rows * 1000, 1000), unit="ms"
    )
    timestamps = timestamps.tz_localize("UTC")

    data = {
        "open": [Decimal(str(100 + i * 0.1)) for i in range(rows)],
        "high": [Decimal(str(101 + i * 0.1)) for i in range(rows)],
        "low": [Decimal(str(99 + i * 0.1)) for i in range(rows)],
        "close": [Decimal(str(100.5 + i * 0.1)) for i in range(rows)],
        "volume": [Decimal(str(1000 + i * 10)) for i in range(rows)],
    }
    return pd.DataFrame(data, index=timestamps)


class TestPyrmethusBot(unittest.IsolatedAsyncioTestCase):
    """Unit tests for the PyrmethusBot class."""

    @classmethod
    def setUpClass(cls):
        # Apply patches at the class level and store the mock objects
        cls.mock_setup_logging = patch(
            "PSG.setup_logging", return_value=MagicMock()
        ).start()
        cls.mock_TradeMetrics = patch(
            "PSG.TradeMetrics", return_value=MagicMock()
        ).start()
        cls.MockBybitAPIClass = patch("PSG.BybitContractAPI").start()
        # No need to patch importlib.import_module anymore as strategy is directly imported

    @classmethod
    def tearDownClass(cls):
        # Stop patches at the class level
        patch.stopall()

    async def asyncSetUp(self):
        # Mock the strategy class that gets imported dynamically
        # This part is no longer needed as strategy is directly imported
        # self.MockStrategyClass = MagicMock()
        # self.mock_strategy_instance = MagicMock()
        # self.MockStrategyClass.return_value = self.mock_strategy_instance
        # mock_strategy_module = MagicMock()
        # mock_strategy_module.EhlersSupertrendStrategy = self.MockStrategyClass
        # self.mock_import_module.return_value = mock_strategy_module

        # Create an instance of the mocked BybitContractAPI
        self.mock_bybit_client = AsyncMock()  # Use AsyncMock for the instance
        # Access the patched BybitContractAPI class directly
        self.MockBybitAPIClass.return_value = (
            self.mock_bybit_client
        )  # Make the class return our AsyncMock instance

        self.bot = PyrmethusBot()
        self.bot.bybit_client = self.mock_bybit_client  # Assign the mocked instance
        self.bot.bot_logger = self.mock_setup_logging

        # Reset config values to defaults for isolation
        config.SYMBOL = "TESTUSDT"
        config.CANDLE_FETCH_LIMIT = 100  # Set a reasonable limit for tests
        # config.WARMUP_PERIOD = 50 # No longer used in PSG.py
        config.API_REQUEST_RETRIES = 0  # No retry logic in PSG.py _initial_kline_fetch
        config.API_BACKOFF_FACTOR = 0.0  # No retry logic in PSG.py _initial_kline_fetch

    async def test_initialization(self):
        """Test that the bot initializes with the correct default state."""
        self.assertEqual(self.bot.inventory, Decimal("0"))
        self.assertFalse(self.bot.has_open_position)
        self.assertIsNone(self.bot.current_position_side)
        self.assertIsNone(self.bot.klines_df)
        # self.MockStrategyClass.assert_called_once() # No longer dynamically imported

    async def test_position_properties(self):
        """Test the has_open_position and current_position_side properties."""
        # No position
        self.bot.inventory = Decimal("0")
        self.assertFalse(self.bot.has_open_position)
        self.assertIsNone(self.bot.current_position_side)

        # Long position
        self.bot.inventory = Decimal("1.23")
        self.assertTrue(self.bot.has_open_position)
        self.assertEqual(self.bot.current_position_side, "Buy")

        # Short position
        self.bot.inventory = Decimal("-1.23")
        self.assertTrue(self.bot.has_open_position)
        self.assertEqual(self.bot.current_position_side, "Sell")

    async def test_reset_position_state(self):
        """Test that _reset_position_state clears all relevant variables."""
        # Give the bot a state
        self.bot.inventory = Decimal("10")
        self.bot.entry_price = Decimal("100")
        # self.bot.trailing_stop_active = True # No longer exists

        # Reset the state
        self.bot._reset_position_state()

        # Assert state is cleared
        self.assertEqual(self.bot.inventory, Decimal("0"))
        self.assertEqual(self.bot.entry_price, Decimal("0"))
        # self.assertFalse(self.bot.trailing_stop_active) # No longer exists

    async def test_handle_position_update_new_long(self):
        """Test handling a WebSocket message for a new long position."""
        position_message = {
            "topic": "position",
            "data": [
                {
                    "symbol": "TESTUSDT",
                    "side": "Buy",
                    "size": "1.5",
                    "avgPrice": "50000",
                    "unrealisedPnl": "10.5",
                }
            ],
        }
        self.bot.trade_metrics.calculate_fee = MagicMock(return_value=Decimal("1.2"))

        await self.bot._handle_position_update(position_message)

        self.assertEqual(self.bot.inventory, Decimal("1.5"))
        self.assertEqual(self.bot.entry_price, Decimal("50000"))
        self.assertEqual(self.bot.unrealized_pnl, Decimal("10.5"))
        self.assertEqual(self.bot.current_position_side, "Buy")
        self.bot.bybit_client.set_trading_stop.assert_called()  # Should try to set TP/SL

    async def test_handle_position_update_close(self):
        """Test handling a position close message."""
        # Setup an open position state
        self.bot.inventory = Decimal("1.5")
        self.bot.entry_price = Decimal("50000")
        self.bot.current_price = Decimal("51000")

        close_message = {
            "topic": "position",
            "data": [
                {
                    "symbol": "TESTUSDT",
                    "size": "0",
                }
            ],
        }

        with patch.object(self.bot, "_reset_position_state") as mock_reset:
            await self.bot._handle_position_update(close_message)
            mock_reset.assert_called_once()
            self.bot.trade_metrics.record_trade.assert_called_once()

    async def test_initial_kline_fetch_success(self):
        """Test a successful initial fetch of kline data."""
        sample_klines = [
            [str(int(time.time() * 1000) - i * 1000), "100", "102", "99", "101", "1000"]
            for i in range(100)
        ]
        self.mock_bybit_client.get_kline_rest_fallback.return_value = {
            "retCode": 0,
            "result": {"list": sample_klines},
        }

        result = await self.bot._initial_kline_fetch()

        self.assertTrue(result)
        self.assertIsNotNone(self.bot.klines_df)
        self.assertEqual(len(self.bot.klines_df), 100)
        self.assertEqual(self.bot.current_price, Decimal("101"))

    async def test_initial_kline_fetch_api_failure(self):
        """Test the retry logic on a failed initial kline fetch."""
        self.mock_bybit_client.get_kline_rest_fallback.side_effect = Exception(
            "API is down"
        )

        result = await self.bot._initial_kline_fetch()

        self.assertFalse(result)
        # Expect only one call as retry logic is removed from PSG.py
        self.assertEqual(self.mock_bybit_client.get_kline_rest_fallback.call_count, 1)

    @patch("PSG.handle_websocket_kline_data")
    async def test_handle_kline_update(self, mock_handle_ws_data):
        """Test the kline update handler."""
        # Arrange
        kline_message = {
            "topic": f"kline.{config.INTERVAL}.{config.SYMBOL}",
            "data": [{"start": 123}],
        }
        mock_df = create_sample_df(rows=100)  # Use a fixed number of rows
        mock_df["atr"] = [Decimal("1.2")] * len(mock_df)
        mock_handle_ws_data.return_value = mock_df

        with patch.object(
            self.bot, "_identify_and_manage_order_blocks"
        ) as mock_manage_ob:
            # Act
            await self.bot._handle_kline_update(kline_message)

            # Assert
            mock_handle_ws_data.assert_called_once_with(
                self.bot.klines_df, kline_message
            )
            self.assertIsNotNone(self.bot.klines_df)
            self.assertEqual(self.bot.cached_atr, Decimal("1.2"))
            self.assertTrue(self.bot.current_price > 0)
            mock_manage_ob.assert_called_once()


if __name__ == "__main__":
    # This allows running the tests directly from the file
    unittest.main()
