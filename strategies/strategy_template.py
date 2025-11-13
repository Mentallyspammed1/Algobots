"""Strategy Template: A template for creating custom trading strategies.

This file provides a clear structure for implementing your own strategy.
Duplicate this file, rename it, and implement your logic in the
`generate_signals` method.
"""

import pandas as pd
import talib
from strategies.base_strategy import BaseStrategy


class MyAwesomeStrategy(BaseStrategy):
    """An example strategy that uses RSI to generate trading signals."""

    def __init__(self):
        super().__init__("MyAwesomeStrategy")
        self.rsi_period = 14
        self.rsi_oversold = 30
        self.rsi_overbought = 70

    def generate_signals(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """Generates trading signals based on the Relative Strength Index (RSI).

        Args:
            dataframe (pd.DataFrame): DataFrame with OHLCV data.

        Returns:
            pd.DataFrame: DataFrame with 'signal' column.

        """
        if "close" not in dataframe.columns:
            raise ValueError("DataFrame must have a 'close' column.")

        df = dataframe.copy()

        # Calculate RSI
        df["rsi"] = talib.RSI(df["close"], timeperiod=self.rsi_period)

        # Initialize signal column
        df["signal"] = "hold"

        # Generate signals
        # Buy when RSI crosses above the oversold threshold
        df.loc[df["rsi"] > self.rsi_oversold, "signal"] = "buy"

        # Sell when RSI crosses below the overbought threshold
        df.loc[df["rsi"] < self.rsi_overbought, "signal"] = "sell"

        # For simplicity, we take the last signal
        # More complex logic could be implemented here (e.g., state machine)
        last_signal = df["signal"].iloc[-1]
        df["signal"] = "hold"  # Default to hold
        df.loc[df.index[-1], "signal"] = (
            last_signal  # Apply signal only to the last row
        )

        return df
