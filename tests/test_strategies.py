import sys
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd

# Ensure the root directory is in the Python path for imports
sys.path.insert(0, "/data/data/com.termux/files/home/Algobots")

# Mock setup_logging to prevent actual log file creation during tests
with patch("bot_logger.setup_logging"):
    # Import the centralized indicator functions

    from strategies.ehlerssupertrendstrategy import EhlersSupertrendStrategy


# Helper function to create a sample DataFrame
def create_sample_kline_df(rows=100, start_timestamp_ms=None, has_tz=True):
    if start_timestamp_ms is None:
        start_timestamp_ms = int(pd.Timestamp.now().timestamp() * 1000) - (
            rows * 60 * 1000
        )

    timestamps = pd.to_datetime(
        range(start_timestamp_ms, start_timestamp_ms + rows * 60 * 1000, 60 * 1000),
        unit="ms",
    )
    if has_tz:
        timestamps = timestamps = timestamps.tz_localize("UTC")

    data = {
        "open": [Decimal(str(100 + i * 0.1)) for i in range(rows)],
        "high": [Decimal(str(101 + i * 0.1)) for i in range(rows)],
        "low": [Decimal(str(99 + i * 0.1)) for i in range(rows)],
        "close": [Decimal(str(100.5 + i * 0.1)) for i in range(rows)],
        "volume": [Decimal(str(1000 + i * 10)) for i in range(rows)],
    }
    df = pd.DataFrame(data, index=timestamps)
    # Ensure Decimal types for all relevant columns
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].apply(Decimal)
    return df


class TestEhlersSupertrendStrategy(unittest.TestCase):
    def setUp(self):
        self.mock_logger = MagicMock()
        self.strategy = EhlersSupertrendStrategy(self.mock_logger)
        self.df = create_sample_kline_df(rows=200)
        # Ensure enough data for indicator calculations
        self.min_required_bars = (
            max(
                self.strategy.ehlers_period,
                self.strategy.supertrend_period,
                self.strategy.sma_period,
            )
            + 2
        )
        if len(self.df) < self.min_required_bars:
            self.df = create_sample_kline_df(
                rows=self.min_required_bars + 10
            )  # Ensure enough rows

    @patch("indicators.calculate_ehlers_fisher_strategy")
    @patch("indicators.calculate_supertrend")
    @patch("indicators.calculate_sma")
    def test_calculate_indicators(
        self,
        mock_calculate_sma,
        mock_calculate_supertrend,
        mock_calculate_ehlers_fisher_strategy,
    ):
        # Mock return values for the indicator functions
        mock_calculate_ehlers_fisher_strategy.return_value = self.df.copy()
        mock_calculate_supertrend.return_value = self.df.copy()
        mock_calculate_sma.return_value = pd.Series(
            [Decimal("100")] * len(self.df), index=self.df.index
        )

        result_df = self.strategy._calculate_indicators(self.df.copy())

        mock_calculate_ehlers_fisher_strategy.assert_called_once_with(
            self.df.copy(), length=self.strategy.ehlers_period
        )
        mock_calculate_supertrend.assert_called_once_with(
            self.df.copy(),
            period=self.strategy.supertrend_period,
            multiplier=self.strategy.supertrend_multiplier,
        )
        mock_calculate_sma.assert_called_once_with(
            self.df.copy(), length=self.strategy.sma_period
        )
        self.assertIn("sma", result_df.columns)

    @patch(
        "strategies.ehlerssupertrendstrategy.EhlersSupertrendStrategy._calculate_indicators"
    )
    def test_generate_signals_buy(self, mock_calculate_indicators):
        # Setup mock DataFrame with specific indicator values for a BUY signal
        mock_df = self.df.copy()
        mock_df["supertrend_direction"] = [Decimal("-1")] * (len(mock_df) - 2) + [
            Decimal("1"),
            Decimal("1"),
        ]
        mock_df["ehlers_fisher"] = [Decimal("0")] * (len(mock_df) - 2) + [
            Decimal("0.5"),
            Decimal("1.0"),
        ]
        mock_df["ehlers_signal"] = [Decimal("0")] * (len(mock_df) - 2) + [
            Decimal("0.6"),
            Decimal("0.5"),
        ]
        mock_df["sma"] = [Decimal("90")] * len(mock_df)
        mock_df["close"] = [Decimal("100")] * (len(mock_df) - 2) + [
            Decimal("100"),
            Decimal("100"),
        ]
        mock_calculate_indicators.return_value = mock_df

        signals = self.strategy.generate_signals(self.df, [], [], [], [])
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0][0], "BUY")
        self.assertEqual(signals[0][1], mock_df["close"].iloc[-1])

    @patch(
        "strategies.ehlerssupertrendstrategy.EhlersSupertrendStrategy._calculate_indicators"
    )
    def test_generate_signals_sell(self, mock_calculate_indicators):
        # Setup mock DataFrame with specific indicator values for a SELL signal
        mock_df = self.df.copy()
        mock_df["supertrend_direction"] = [Decimal("1")] * (len(mock_df) - 2) + [
            Decimal("-1"),
            Decimal("-1"),
        ]
        mock_df["ehlers_fisher"] = [Decimal("0")] * (len(mock_df) - 2) + [
            Decimal("-0.5"),
            Decimal("-1.0"),
        ]
        mock_df["ehlers_signal"] = [Decimal("0")] * (len(mock_df) - 2) + [
            Decimal("-0.6"),
            Decimal("-0.5"),
        ]
        mock_df["sma"] = [Decimal("110")] * len(mock_df)
        mock_df["close"] = [Decimal("100")] * (len(mock_df) - 2) + [
            Decimal("100"),
            Decimal("100"),
        ]
        mock_calculate_indicators.return_value = mock_df

        signals = self.strategy.generate_signals(self.df, [], [], [], [])
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0][0], "SELL")
        self.assertEqual(signals[0][1], mock_df["close"].iloc[-1])

    @patch(
        "strategies.ehlerssupertrendstrategy.EhlersSupertrendStrategy._calculate_indicators"
    )
    def test_generate_exit_signals_long_position(self, mock_calculate_indicators):
        # Setup mock DataFrame for exiting a long position
        mock_df = self.df.copy()
        mock_df["supertrend_direction"] = [Decimal("1")] * (len(mock_df) - 2) + [
            Decimal("-1"),
            Decimal("-1"),
        ]
        mock_df["ehlers_fisher"] = [Decimal("0")] * (len(mock_df) - 2) + [
            Decimal("0.5"),
            Decimal("0.0"),
        ]
        mock_df["ehlers_signal"] = [Decimal("0")] * (len(mock_df) - 2) + [
            Decimal("0.0"),
            Decimal("0.5"),
        ]
        mock_df["close"] = [Decimal("100")] * len(mock_df)
        mock_calculate_indicators.return_value = mock_df

        exit_signals = self.strategy.generate_exit_signals(self.df, "BUY", [], [])
        self.assertEqual(len(exit_signals), 1)
        self.assertEqual(exit_signals[0][0], "SELL_TO_CLOSE")

    @patch(
        "strategies.ehlerssupertrendstrategy.EhlersSupertrendStrategy._calculate_indicators"
    )
    def test_generate_exit_signals_short_position(self, mock_calculate_indicators):
        # Setup mock DataFrame for exiting a short position
        mock_df = self.df.copy()
        mock_df["supertrend_direction"] = [Decimal("-1")] * (len(mock_df) - 2) + [
            Decimal("1"),
            Decimal("1"),
        ]
        mock_df["ehlers_fisher"] = [Decimal("0")] * (len(mock_df) - 2) + [
            Decimal("-0.5"),
            Decimal("0.0"),
        ]
        mock_df["ehlers_signal"] = [Decimal("0")] * (len(mock_df) - 2) + [
            Decimal("0.0"),
            Decimal("-0.5"),
        ]
        mock_df["close"] = [Decimal("100")] * len(mock_df)
        mock_calculate_indicators.return_value = mock_df

        exit_signals = self.strategy.generate_exit_signals(self.df, "SELL", [], [])
        self.assertEqual(len(exit_signals), 1)
        self.assertEqual(exit_signals[0][0], "BUY_TO_CLOSE")


if __name__ == "__main__":
    unittest.main()
