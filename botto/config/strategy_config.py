# config/strategy_config.py
from dataclasses import dataclass
from dataclasses import field
from typing import Any


@dataclass
class ChandelierEhlersConfig:
    """Configuration for Chandelier Exit Ehlers SuperTrend strategy."""

    # Indicator parameters
    chandelier_period: int = 22
    chandelier_multiplier: float = 3.0
    supertrend_period: int = 10
    supertrend_multiplier: float = 3.0

    # Signal parameters
    min_signal_strength: float = 0.5
    min_signal_confidence: float = 0.6

    # Data parameters
    timeframe: str = "15"  # Default 15 minutes
    data_limit: int = 200

    # Trading parameters
    symbols: list[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])

    @classmethod
    def from_dict(cls, config_dict: dict[str, Any]) -> "ChandelierEhlersConfig":
        """Create config from dictionary."""
        return cls(
            chandelier_period=config_dict.get("chandelier_period", 22),
            chandelier_multiplier=config_dict.get("chandelier_multiplier", 3.0),
            supertrend_period=config_dict.get("supertrend_period", 10),
            supertrend_multiplier=config_dict.get("supertrend_multiplier", 3.0),
            min_signal_strength=config_dict.get("min_signal_strength", 0.5),
            min_signal_confidence=config_dict.get("min_signal_confidence", 0.6),
            timeframe=config_dict.get("timeframe", "15"),
            data_limit=config_dict.get("data_limit", 200),
            symbols=config_dict.get("symbols", ["BTCUSDT", "ETHUSDT"]),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "chandelier_period": self.chandelier_period,
            "chandelier_multiplier": self.chandelier_multiplier,
            "supertrend_period": self.supertrend_period,
            "supertrend_multiplier": self.supertrend_multiplier,
            "min_signal_strength": self.min_signal_strength,
            "min_signal_confidence": self.min_signal_confidence,
            "timeframe": self.timeframe,
            "data_limit": self.data_limit,
            "symbols": self.symbols,
        }
