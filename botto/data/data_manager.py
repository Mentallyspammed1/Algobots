import logging
from abc import ABC
from abc import abstractmethod
from datetime import datetime

import pandas as pd

logger = logging.getLogger(__name__)


class DataProvider(ABC):
    """Abstract base class for data providers."""

    @abstractmethod
    def get_historical_data(
        self, symbol: str, timeframe: str, limit: int
    ) -> pd.DataFrame:
        """Get historical market data."""
        pass


class BybitDataProvider(DataProvider):
    """Data provider for Bybit exchange."""

    def __init__(self, session):
        """Initialize data provider."""
        self.session = session

    def get_historical_data(
        self, symbol: str, timeframe: str, limit: int
    ) -> pd.DataFrame:
        """Get historical kline data from Bybit.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe (e.g., '15' for 15 minutes)
            limit: Number of candles to retrieve

        Returns:
            DataFrame with OHLCV data. Returns empty DataFrame on error.

        """
        if not self.session:
            logger.error("API session is not initialized.")
            return pd.DataFrame()

        try:
            response = self.session.get_kline(
                category="linear",  # Assuming linear for now, could be made configurable
                symbol=symbol,
                interval=timeframe,
                limit=limit,
            )

            if response["retCode"] != 0:
                logger.error(
                    f"Error fetching kline data for {symbol}: "
                    f"{response.get('retMsg', 'Unknown error')}"
                )
                return pd.DataFrame()

            kline_data = response["result"].get("list")
            if not kline_data:
                logger.warning(f"No kline data received for {symbol}.")
                return pd.DataFrame()

            # Convert to DataFrame
            df = pd.DataFrame(
                kline_data,
                columns=[
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "turnover",
                ],
            )

            # Convert to numeric types and timestamp
            try:
                df["timestamp"] = pd.to_datetime(
                    df["timestamp"].astype(float), unit="ms"
                )
                for col in ["open", "high", "low", "close", "volume", "turnover"]:
                    df[col] = pd.to_numeric(df[col])
            except Exception as e:
                logger.error(f"Error converting data types for {symbol}: {e!s}")
                return pd.DataFrame()

            # Sort by timestamp
            df = df.sort_values("timestamp").reset_index(drop=True)

            return df

        except AttributeError:
            logger.error(
                "API session object does not have 'get_kline' method or "
                "is not properly initialized."
            )
            return pd.DataFrame()
        except Exception as e:
            logger.error(
                f"An unexpected error occurred fetching historical data for "
                f"{symbol}: {e!s}"
            )
            return pd.DataFrame()


class Trade:
    """Represents a single trade with its PnL."""

    def __init__(
        self,
        symbol: str,
        entry_price: float,
        exit_price: float,
        pnl: float,
        timestamp: datetime,
    ):
        self.symbol = symbol
        self.entry_price = entry_price
        self.exit_price = exit_price
        self.pnl = pnl
        self.timestamp = timestamp

    def __repr__(self):
        return (
            f"Trade(symbol='{self.symbol}', entry={self.entry_price}, "
            f"exit={self.exit_price}, pnl={self.pnl:.4f}, "
            f"ts={self.timestamp.isoformat()})"
        )


class DataManager:
    """Manages historical trade data in memory."""

    def __init__(self, max_trades_per_symbol=1000):
        self.trades: list[Trade] = []
        self.max_trades_per_symbol = (
            max_trades_per_symbol  # Limit the number of stored trades
        )

    def add_trade(self, trade: Trade):
        """Adds a trade to the manager and maintains the list size."""
        self.trades.append(trade)
        # Keep trades sorted by timestamp for efficient retrieval
        # Sorting on every add can be slow for very large lists.
        # Consider alternative data structures or sorting only when needed if
        # performance is an issue.
        self.trades.sort(key=lambda t: t.timestamp)

        # Limit the number of stored trades to prevent memory issues
        if len(self.trades) > self.max_trades_per_symbol:
            self.trades = self.trades[-self.max_trades_per_symbol :]
            logger.debug(f"Trimmed trades list to {self.max_trades_per_symbol} trades.")

    def get_trades(self, symbol: str, limit: int) -> list[Trade]:
        """Retrieves the last 'limit' trades for a given symbol.

        Args:
            symbol: The trading symbol.
            limit: The maximum number of trades to return.

        Returns:
            A list of Trade objects. Returns empty list if no trades found or
            symbol is invalid.

        """
        if not symbol:
            logger.warning("Cannot get trades: symbol is empty.")
            return []

        # Filter trades for the specific symbol
        symbol_trades = [trade for trade in self.trades if trade.symbol == symbol]

        # Return the last 'limit' trades
        return symbol_trades[-limit:]
