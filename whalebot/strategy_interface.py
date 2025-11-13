# strategy_interface.py

import logging
from abc import ABC
from abc import abstractmethod
from typing import Any

import pandas as pd


class Signal:
    """Represents a trading signal."""

    def __init__(self, type: str, score: float = 0.0, reasons: list[str] | None = None):
        self.type = type  # 'BUY', 'SELL', or 'HOLD'
        self.score = score
        self.reasons = reasons if reasons is not None else []

    def is_buy(self) -> bool:
        return self.type == "BUY"

    def is_sell(self) -> bool:
        return self.type == "SELL"

    def is_hold(self) -> bool:
        return self.type == "HOLD"


class BaseStrategy(ABC):
    """Abstract base class for all trading strategies."""

    def __init__(self, strategy_name: str, logger: logging.Logger, **kwargs):
        self.strategy_name = strategy_name
        self.logger = logger
        self.update_parameters(**kwargs)

    def update_parameters(self, **kwargs):
        """Update strategy parameters dynamically."""
        for key, value in kwargs.items():
            if hasattr(self, key.lower()):
                setattr(self, key.lower(), value)
        self.logger.info(f"Strategy '{self.strategy_name}' parameters updated.")

    @abstractmethod
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate and add all necessary technical indicators to the DataFrame."""
        pass

    @abstractmethod
    def generate_signal(
        self,
        df: pd.DataFrame,
        current_market_price: float,
        market_conditions: dict[str, Any],
    ) -> Signal:
        """Generate a trading signal based on the provided data."""
        pass

    @abstractmethod
    def get_indicator_values(self, df: pd.DataFrame) -> dict[str, float]:
        """Extract the latest values of key indicators after calculation."""
        pass
