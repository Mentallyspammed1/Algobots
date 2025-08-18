"""
Base class for all trading strategies.

This abstract class defines the interface that all strategy classes must implement.
"""
from abc import ABC, abstractmethod
import pandas as pd

class BaseStrategy(ABC):
    """
    Abstract base class for a trading strategy.
    """
    def __init__(self, strategy_name: str):
        self.name = strategy_name

    @abstractmethod
    def generate_signals(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """
        Generates trading signals based on the input data.

        Args:
            dataframe (pd.DataFrame): A DataFrame containing market data (OHLCV).

        Returns:
            pd.DataFrame: A DataFrame with an added 'signal' column.
                          Signal values can be 'buy', 'sell', or 'hold'.
        """
        pass

    def __str__(self):
        return self.name
