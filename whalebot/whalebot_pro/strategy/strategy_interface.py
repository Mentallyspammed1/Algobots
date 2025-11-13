import logging
from abc import ABC
from abc import abstractmethod
from enum import Enum
from typing import Any

import pandas as pd


class Signal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class BaseStrategy(ABC):
    """Abstract base class for trading strategies."""

    def __init__(
        self,
        logger: logging.Logger,
        strategy_name: str = "BaseStrategy",
        **kwargs,
    ):
        self.logger = logger
        self.strategy_name = strategy_name
        self.params = kwargs

    @abstractmethod
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculates and adds indicators to the DataFrame."""
        pass

    @abstractmethod
    def generate_signal(
        self,
        df: pd.DataFrame,
        current_price: float,
        orderbook_data: dict[str, Any],
    ) -> Signal:
        """Generates a trading signal based on indicators and market data."""
        pass

    def __str__(self) -> str:
        return self.strategy_name
