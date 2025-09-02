
# utilities.py

import logging
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
from pybit.unified_trading import HTTP
from zoneinfo import ZoneInfo

class KlineDataFetcher:
    """Handles fetching historical kline data from Bybit."""
    
    def __init__(self, http_session: HTTP, logger: logging.Logger, config: Any): # Config object for settings
        self.http_session = http_session
        self.logger = logger
        self.config = config

    async def fetch_klines(self, symbol: str, category: str, interval: str, 
                           limit: int, history_window_minutes: int) -> pd.DataFrame:
        """
        Fetches historical kline data, ensuring enough data for indicator lookbacks.
        Automatically calculates start time based on the desired history window.
        """
        try:
            # Calculate start time based on history window
            end_time = datetime.now(ZoneInfo(self.config.BYBIT_TIMEZONE))
            start_time = end_time - timedelta(minutes=history_window_minutes)

            response = self.http_session.get_kline(
                category=category,
                symbol=symbol,
                interval=interval,
                start=int(start_time.timestamp() * 1000), # Bybit expects milliseconds
                end=int(end_time.timestamp() * 1000),
                limit=limit
            )
            
            if response['retCode'] == 0:
                klines_data = response['result']['list']
                
                df = pd.DataFrame(klines_data, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
                ])
                
                # Convert timestamp to timezone-aware datetime and ensure numeric types
                df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float), unit='ms').dt.tz_localize('UTC').dt.tz_convert(ZoneInfo(self.config.BYBIT_TIMEZONE))
                for col in ['open', 'high', 'low', 'close', 'volume', 'turnover']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                
                df = df.sort_values('timestamp').set_index('timestamp')
                df = df.dropna(subset=['close']) # Ensure no NaNs in critical price columns
                
                self.logger.debug(f"Fetched {len(df)} klines for {symbol} (Interval: {interval}, History: {history_window_minutes}min).")
                return df
            else:
                self.logger.error(f"Failed to fetch klines for {symbol}: {response['retMsg']}")
                return pd.DataFrame()
        except Exception as e:
            self.logger.error(f"Exception fetching klines for {symbol}: {e}")
            return pd.DataFrame()


class InMemoryCache:
    """A simple in-memory cache with a Time-To-Live (TTL) and maximum size."""

    def __init__(self, ttl_seconds: int = 60, max_size: int = 100):
        self.cache: Dict[str, Tuple[float, Any]] = {} # {key: (timestamp, value)}
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self.logger = logging.getLogger(__name__)

    def get(self, key: str) -> Optional[Any]:
        """Retrieves an item from the cache if it's not expired."""
        if key in self.cache:
            timestamp, value = self.cache[key]
            if time.time() - timestamp < self.ttl_seconds:
                self.logger.debug(f"Cache hit for key: {key}")
                return value
            else:
                self.logger.debug(f"Cache expired for key: {key}")
                del self.cache[key] # Remove expired item
        self.logger.debug(f"Cache miss for key: {key}")
        return None

    def set(self, key: str, value: Any):
        """Adds an item to the cache, managing its size."""
        if len(self.cache) >= self.max_size:
            # Simple eviction: remove the oldest item
            oldest_key = min(self.cache, key=lambda k: self.cache[k][0])
            self.logger.debug(f"Cache full, evicting oldest item: {oldest_key}")
            del self.cache[oldest_key]
        self.cache[key] = (time.time(), value)
        self.logger.debug(f"Cache set for key: {key}")

    def clear(self):
        """Clears the entire cache."""
        self.cache.clear()
        self.logger.info("Cache cleared.")

    def generate_kline_cache_key(self, symbol: str, category: str, interval: str, limit: int, history_window_minutes: int) -> str:
        """
        Generates a unique cache key for kline data requests.
        The history_window_minutes changes the start time, so it's part of the key.
        This makes the cache key dynamic based on when it's called, but for live bot
        where `datetime.now()` advances, it should effectively create a new key often.
        For a truly stable key, one might use a truncated timestamp or interval-aligned timestamp.
        However, for `fetch_klines` called periodically, the current approach is fine.
        """
        return f"kline_data_{symbol}_{category}_{interval}_{limit}_{history_window_minutes}"
