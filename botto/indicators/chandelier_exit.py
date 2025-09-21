# indicators/chandelier_exit.py
import numpy as np
import pandas as pd


class ChandelierExit:
    """
    Chandelier Exit indicator implementation.

    A volatility-based indicator used for setting trailing stop-loss levels.
    It's calculated using the highest high or lowest low over a period,
    adjusted by a multiple of the Average True Range (ATR).
    """

    def __init__(self, period=22, multiplier=3.0):
        """Initialize Chandelier Exit indicator."""
        self.period = period
        self.multiplier = multiplier

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate Chandelier Exit values.

        Args:
            df: DataFrame with OHLCV data

        Returns:
            DataFrame with Chandelier Exit values added
        """
        if df.empty:
            return df

        # Calculate True Range
        df['tr'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift(1)),
                abs(df['low'] - df['close'].shift(1))
            )
        )

        # Calculate Average True Range
        df['atr'] = df['tr'].rolling(window=self.period).mean()

        # Calculate Chandelier Exit long and short
        df['chandelier_long'] = (df['high'].rolling(window=self.period).max() -
                                 self.multiplier * df['atr'])
        df['chandelier_short'] = (df['low'].rolling(window=self.period).min() +
                                  self.multiplier * df['atr'])

        return df