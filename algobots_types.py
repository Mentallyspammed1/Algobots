# algobots_types.py - Defines shared data structures for Algobots
import datetime
from decimal import Decimal
from typing import TypedDict


class OrderBlock(TypedDict):
    """
    Represents an Order Block identified on the chart.
    """
    id: str  # Unique identifier for the Order Block (e.g., "BULL_OB_timestamp")
    type: str  # 'bull' (bullish/demand block) or 'bear' (bearish/supply block)
    timestamp: datetime # Timestamp of the candle that formed the OB (its close time)
    top: Decimal  # The upper boundary of the Order Block
    bottom: Decimal # The lower boundary of the Order Block
    active: bool  # True if the OB is currently considered active (not violated or mitigated)
    violated: bool # True if the OB's boundary has been breached
    violation_ts: datetime | None # Timestamp when the OB was violated
    extended_to_ts: datetime # The latest timestamp where the OB was still considered relevant/active
