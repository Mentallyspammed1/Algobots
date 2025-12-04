# integration/strategy_factory.py
from typing import Any

from config.strategy_config import ChandelierEhlersConfig
from strategies.chandelier_ehlers_strategy import ChandelierEhlersSuperTrendStrategy


class StrategyFactory:
    """Factory for creating strategy instances."""

    @staticmethod
    def create_chandelier_ehlers_strategy(
        config: dict[str, Any], session,
    ) -> ChandelierEhlersSuperTrendStrategy:
        """Create a Chandelier Exit Ehlers SuperTrend strategy instance.

        Args:
            config: Strategy configuration dictionary
            session: Bybit API session

        Returns:
            ChandelierEhlersSuperTrendStrategy instance

        """
        strategy_config = ChandelierEhlersConfig.from_dict(config)
        return ChandelierEhlersSuperTrendStrategy(strategy_config, session)
