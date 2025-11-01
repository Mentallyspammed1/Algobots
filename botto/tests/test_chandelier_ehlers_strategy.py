# tests/test_chandelier_ehlers_strategy.py
import unittest
from datetime import datetime
from datetime import timedelta

import pandas as pd
from indicators.chandelier_exit import ChandelierExit
from indicators.ehlers_supertrend import EhlersSuperTrend
from signals.signal_generator import ChandelierEhlersSignalGenerator


class TestChandelierEhlersStrategy(unittest.TestCase):
    """Test cases for Chandelier Exit Ehlers SuperTrend strategy."""

    def setUp(self):
        """Set up test data."""
        # Create sample OHLCV data
        dates = pd.date_range(
            start=datetime.now() - timedelta(days=30), periods=100, freq="H"
        )
        prices = [100 + i * 0.1 + (i % 5) for i in range(100)]

        self.test_data = pd.DataFrame(
            {
                "timestamp": dates,
                "open": prices,
                "high": [p + 0.5 for p in prices],
                "low": [p - 0.5 for p in prices],
                "close": prices,
                "volume": [1000 for _ in range(100)],
                "turnover": [100000 for _ in range(100)],
            }
        )

    def test_chandelier_exit_calculation(self):
        """Test Chandelier Exit calculation."""
        chandelier = ChandelierExit(period=10, multiplier=3.0)
        result = chandelier.calculate(self.test_data)

        # Check that required columns are present
        self.assertIn("chandelier_long", result.columns)
        self.assertIn("chandelier_short", result.columns)
        self.assertIn("atr", result.columns)

        # Check that values are calculated correctly
        self.assertFalse(result["chandelier_long"].isna().all())
        self.assertFalse(result["chandelier_short"].isna().all())

    def test_ehlers_supertrend_calculation(self):
        """Test Ehlers SuperTrend calculation."""
        supertrend = EhlersSuperTrend(period=10, multiplier=3.0)
        result = supertrend.calculate(self.test_data)

        # Check that required columns are present
        self.assertIn("supertrend", result.columns)
        self.assertIn("typical_price", result.columns)
        self.assertIn("atr", result.columns)

        # Check that values are calculated correctly
        self.assertFalse(result["supertrend"].isna().all())

    def test_signal_generation(self):
        """Test signal generation."""
        # Calculate indicators
        chandelier = ChandelierExit(period=10, multiplier=3.0)
        supertrend = EhlersSuperTrend(period=10, multiplier=3.0)

        df = chandelier.calculate(self.test_data)
        df = supertrend.calculate(df)

        # Determine Chandelier Exit based on trend
        df["chandelier_exit"] = df.apply(
            lambda row: row["chandelier_long"]
            if row["supertrend"] < row["close"]
            else row["chandelier_short"],
            axis=1,
        )

        # Generate signals
        signal_generator = ChandelierEhlersSignalGenerator()
        signals = signal_generator.generate_signals(df, "BTCUSDT")

        # Check that signals are generated
        self.assertIsInstance(signals, list)

        # If signals are generated, check their structure
        if signals:
            signal = signals[0]
            self.assertIn("type", signal.to_dict())
            self.assertIn("strength", signal.to_dict())
            self.assertIn("price", signal.to_dict())
            self.assertIn("reasons", signal.to_dict())
            self.assertIn("indicators", signal.to_dict())


if __name__ == "__main__":
    unittest.main()
