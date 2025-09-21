
import time
import pandas as pd
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
import logging

# Import from local modules
from whalebot_pro.api.bybit_client import BybitClient

class KlineDataFetcher:
    """Fetches kline data from Bybit using the BybitClient."""

    def __init__(self, bybit_client: BybitClient, logger: logging.Logger, config: Dict[str, Any]):
        self.bybit_client = bybit_client
        self.logger = logger
        self.config = config

    async def fetch_klines(
        self, symbol: str, category: str, interval: str, limit: int, history_window_minutes: int
    ) -> pd.DataFrame:
        """Fetches kline data, ensuring enough history for indicators."""
        # Calculate required limit based on history_window_minutes and interval
        # Assuming interval is in minutes for simplicity (e.g., "1", "15", "60")
        # For "D", "W", "M" intervals, this logic would need adjustment.
        if interval.isdigit():
            interval_minutes = int(interval)
            # Ensure we fetch enough bars to cover the history window plus the lookback limit
            # A safe buffer is to fetch 2-3 times the lookback limit, or enough for the history window
            required_bars_for_history = (history_window_minutes // interval_minutes) + 1
            actual_limit = max(limit, required_bars_for_history) # Fetch at least 'limit' bars, or more if needed for history
        else:
            # For D, W, M intervals, a fixed large limit is often used or adjusted based on strategy needs
            actual_limit = limit # Use the provided limit for non-minute intervals
            self.logger.warning(f"Non-minute interval '{interval}' detected. History window calculation might be inaccurate.")

        df = await self.bybit_client.fetch_klines(interval, actual_limit)
        if df is None or df.empty:
            self.logger.warning(f"No kline data fetched for {symbol}-{interval}.")
            return pd.DataFrame()
        return df

class InMemoryCache:
    """A simple in-memory cache with a time-to-live (TTL)."""

    def __init__(self, ttl_seconds: int = 60, max_size: int = 100):
        self.cache: Dict[str, Any] = {}
        self.timestamps: Dict[str, float] = {}
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size

    def set(self, key: str, value: Any) -> None:
        self._clean_expired()
        if len(self.cache) >= self.max_size:
            self._evict_oldest()
        self.cache[key] = value
        self.timestamps[key] = time.time()

    def get(self, key: str) -> Optional[Any]:
        self._clean_expired()
        if key in self.cache:
            return self.cache[key]
        return None

    def _clean_expired(self) -> None:
        current_time = time.time()
        expired_keys = [key for key, ts in self.timestamps.items() if current_time - ts > self.ttl_seconds]
        for key in expired_keys:
            self.cache.pop(key, None)
            self.timestamps.pop(key, None)

    def _evict_oldest(self) -> None:
        if not self.timestamps:
            return
        oldest_key = min(self.timestamps, key=self.timestamps.get)
        self.cache.pop(oldest_key, None)
        self.timestamps.pop(oldest_key, None)

    def generate_kline_cache_key(self, symbol: str, category: str, interval: str, limit: int, history_window_minutes: int) -> str:
        """Generates a unique cache key for kline data based on parameters."""
        return f"kline_{symbol}_{category}_{interval}_{limit}_{history_window_minutes}"
