from typing import List, Dict, Any, Tuple
from decimal import Decimal
import pandas as pd
from algobots_types import OrderBlock

class StrategyTemplate:
    """
    Template for a trading strategy. All strategies should inherit from this class
    and implement the generate_signals and generate_exit_signals methods.
    """
    def __init__(self, logger):
        self.logger = logger
        # Initialize any strategy-specific parameters here

    def generate_signals(self, 
                         df: pd.DataFrame, 
                         resistance_levels: List[Dict[str, Any]], 
                         support_levels: List[Dict[str, Any]],
                         active_bull_obs: List[OrderBlock], 
                         active_bear_obs: List[OrderBlock],
                         **kwargs) -> List[Tuple[str, Decimal, Any, Dict[str, Any]]]:
        """
        Generates entry signals based on market data and indicators.

        Args:
            df (pd.DataFrame): DataFrame with kline data and indicators.
            resistance_levels (List[Dict[str, Any]]): Detected resistance levels.
            support_levels (List[Dict[str, Any]]): Detected support levels.
            active_bull_obs (List[OrderBlock]): Active bullish order blocks.
            active_bear_obs (List[OrderBlock]): Active bearish order blocks.
            **kwargs: Additional strategy-specific parameters.

        Returns:
            List[Tuple[str, Decimal, Any, Dict[str, Any]]]: A list of signal tuples.
                Each tuple: (signal_type, price, timestamp, indicator_info).
        """
        # Implement your entry signal logic here
        self.logger.debug("StrategyTemplate: Generating entry signals (placeholder).")
        return []

    def generate_exit_signals(self, 
                              df: pd.DataFrame, 
                              current_position_side: str,
                              active_bull_obs: List[OrderBlock], 
                              active_bear_obs: List[OrderBlock],
                              **kwargs) -> List[Tuple[str, Decimal, Any, Dict[str, Any]]]:
        """
        Generates exit signals based on market data, indicators, and current position.

        Args:
            df (pd.DataFrame): DataFrame with kline data and indicators.
            current_position_side (str): The side of the current open position ('BUY' or 'SELL').
            active_bull_obs (List[OrderBlock]): Active bullish order blocks.
            active_bear_obs (List[OrderBlock]): Active bearish order blocks.
            **kwargs: Additional strategy-specific parameters.

        Returns:
            List[Tuple[str, Decimal, Any, Dict[str, Any]]]: A list of exit signal tuples.
                Each tuple: (exit_type, price, timestamp, indicator_info).
        """
        # Implement your exit signal logic here
        self.logger.debug("StrategyTemplate: Generating exit signals (placeholder).")
        return []
