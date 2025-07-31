# algobots_types.py - Defines shared data structures for Algobots
from dataclasses import dataclass, field, asdict
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional, Literal, Dict, Any

@dataclass(frozen=True)
class OrderBlock:
    """
    Represents an Order Block identified on the chart.
    Using a dataclass for immutability, validation, and helper methods.
    """
    id: str
    type: Literal["bull", "bear"]
    timestamp: datetime
    top: Decimal
    bottom: Decimal
    volume: Decimal
    active: bool = True
    violated: bool = False
    violation_ts: Optional[datetime] = None
    extended_to_ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        """Validate fields after initialization."""
        if self.bottom > self.top:
            raise ValueError(f"OrderBlock validation failed: bottom ({self.bottom}) cannot be greater than top ({self.top}).")
        if self.violation_ts and self.violation_ts < self.timestamp:
            raise ValueError("OrderBlock validation failed: violation_ts cannot be earlier than the creation timestamp.")

    def is_price_inside(self, price: Decimal) -> bool:
        """Check if a given price is within the Order Block's boundaries."""
        return self.bottom <= price <= self.top

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the dataclass to a dictionary for broader compatibility."""
        return asdict(self)

    def copy_with(self, **changes) -> 'OrderBlock':
        """
        Creates a new, updated instance of the OrderBlock since this one is immutable.
        """
        current_values = self.to_dict()
        current_values.update(changes)
        # The factory for extended_to_ts will run if not provided in changes
        if 'extended_to_ts' not in changes:
            current_values['extended_to_ts'] = datetime.now(timezone.utc)
        return OrderBlock(**current_values)