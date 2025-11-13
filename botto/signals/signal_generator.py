# signals/signal_generator.py
from abc import ABC
from abc import abstractmethod
from datetime import datetime
from typing import Any

import pandas as pd


class Signal:
    """Trading signal data structure."""

    def __init__(
        self,
        signal_type: str,
        strength: float,
        price: float,
        timestamp: datetime,
        reasons: list[str],
        indicators: dict[str, Any],
        symbol: str,
        strategy: str,
        confidence: float = 0.0,
    ):
        """Initialize signal."""
        self.type = signal_type
        self.strength = strength
        self.price = price
        self.timestamp = timestamp
        self.reasons = reasons
        self.indicators = indicators
        self.symbol = symbol
        self.strategy = strategy
        self.confidence = confidence

    def to_dict(self) -> dict:
        """Convert signal to dictionary."""
        return {
            "type": self.type,
            "strength": self.strength,
            "price": self.price,
            "timestamp": self.timestamp.isoformat(),
            "reasons": self.reasons,
            "indicators": self.indicators,
            "symbol": self.symbol,
            "strategy": self.strategy,
            "confidence": self.confidence,
        }


class SignalGenerator(ABC):
    """Abstract base class for signal generators."""

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame, symbol: str) -> list[Signal]:
        """Generate trading signals."""
        pass


class ChandelierEhlersSignalGenerator(SignalGenerator):
    """Signal generator for Chandelier Exit Ehlers SuperTrend crossover strategy.

    Generates buy and sell signals based on crossovers between the Chandelier Exit
    and Ehlers SuperTrend indicators.
    """

    def __init__(self, min_strength=0.5, min_confidence=0.6):
        """Initialize signal generator."""
        self.min_strength = min_strength
        self.min_confidence = min_confidence

    def generate_signals(self, df: pd.DataFrame, symbol: str) -> list[Signal]:
        """Generate trading signals based on indicator crossovers.

        Args:
            df: DataFrame with OHLCV and indicator data
            symbol: Trading symbol

        Returns:
            List of Signal objects

        """
        if df.empty or len(df) < 3:
            return []

        signals = []

        try:
            last_row = df.iloc[-1]
            prev_row = df.iloc[-2]

            current_price = last_row["close"]
            current_supertrend = last_row["supertrend"]
            prev_supertrend = prev_row["supertrend"]
            current_chandelier = last_row["chandelier_exit"]

            # Buy signal conditions:
            # 1. Price crosses above SuperTrend
            # 2. SuperTrend is below Chandelier Exit (confirming the trend)
            # 3. Previous candle was below SuperTrend (confirming crossover)

            if (
                current_price > current_supertrend
                and prev_row["close"] <= prev_supertrend
                and current_supertrend < current_chandelier
            ):
                # Calculate signal strength based on distance between indicators
                strength = min(
                    1.0,
                    abs(current_supertrend - current_chandelier) / current_price * 10,
                )

                # Skip if strength is below minimum threshold
                if strength < self.min_strength:
                    return signals

                # Calculate confidence based on recent trend consistency
                trend_consistency = 0
                for i in range(min(5, len(df) - 1)):
                    if df.iloc[-(i + 1)]["close"] > df.iloc[-(i + 1)]["supertrend"]:
                        trend_consistency += 1

                confidence = min(1.0, trend_consistency / 5)

                # Skip if confidence is below minimum threshold
                if confidence < self.min_confidence:
                    return signals

                signal = Signal(
                    signal_type="BUY",
                    strength=strength,
                    price=current_price,
                    timestamp=datetime.now(),
                    reasons=[
                        "Price crossed above SuperTrend",
                        "SuperTrend below Chandelier Exit (trend confirmation)",
                    ],
                    indicators={
                        "supertrend": current_supertrend,
                        "chandelier_exit": current_chandelier,
                        "atr": last_row["atr"],
                        "price": current_price,
                    },
                    symbol=symbol,
                    strategy="ChandelierEhlersSuperTrend",
                    confidence=confidence,
                )
                signals.append(signal)

            # Sell signal conditions:
            # 1. Price crosses below SuperTrend
            # 2. SuperTrend is above Chandelier Exit (confirming the trend)
            # 3. Previous candle was above SuperTrend (confirming crossover)

            elif (
                current_price < current_supertrend
                and prev_row["close"] >= prev_supertrend
                and current_supertrend > current_chandelier
            ):
                # Calculate signal strength based on distance between indicators
                strength = min(
                    1.0,
                    abs(current_supertrend - current_chandelier) / current_price * 10,
                )

                # Skip if strength is below minimum threshold
                if strength < self.min_strength:
                    return signals

                # Calculate confidence based on recent trend consistency
                trend_consistency = 0
                for i in range(min(5, len(df) - 1)):
                    if df.iloc[-(i + 1)]["close"] < df.iloc[-(i + 1)]["supertrend"]:
                        trend_consistency += 1

                confidence = min(1.0, trend_consistency / 5)

                # Skip if confidence is below minimum threshold
                if confidence < self.min_confidence:
                    return signals

                signal = Signal(
                    signal_type="SELL",
                    strength=strength,
                    price=current_price,
                    timestamp=datetime.now(),
                    reasons=[
                        "Price crossed below SuperTrend",
                        "SuperTrend above Chandelier Exit (trend confirmation)",
                    ],
                    indicators={
                        "supertrend": current_supertrend,
                        "chandelier_exit": current_chandelier,
                        "atr": last_row["atr"],
                        "price": current_price,
                    },
                    symbol=symbol,
                    strategy="ChandelierEhlersSuperTrend",
                    confidence=confidence,
                )
                signals.append(signal)

            return signals

        except Exception as e:
            print(f"Error generating signals: {e!s}")
            return []
