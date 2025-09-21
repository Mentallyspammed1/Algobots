# data/data_manager.py
import pandas as pd
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class DataProvider(ABC):
    """Abstract base class for data providers."""
    
    @abstractmethod
    def get_historical_data(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        """Get historical market data."""
        pass

class BybitDataProvider(DataProvider):
    """Data provider for Bybit exchange."""
    
    def __init__(self, session):
        """Initialize data provider."""
        self.session = session
    
    def get_historical_data(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        """
        Get historical kline data from Bybit.
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe (e.g., '15' for 15 minutes)
            limit: Number of candles to retrieve
            
        Returns:
            DataFrame with OHLCV data
        """
        try:
            response = self.session.get_kline(
                category="linear",
                symbol=symbol,
                interval=timeframe,
                limit=limit
            )
            
            if response['retCode'] != 0:
                print(f"Error fetching kline data: {response['retMsg']}")
                return pd.DataFrame()
            
            kline_data = response['result']['list']
            
            # Convert to DataFrame
            df = pd.DataFrame(kline_data, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
            ])
            
            # Convert to numeric types
            df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float), unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume', 'turnover']:
                df[col] = df[col].astype(float)
            
            # Sort by timestamp
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            return df
            
        except Exception as e:
            print(f"Error getting historical data: {str(e)}")
            return pd.DataFrame()

class Trade:
    """Represents a single trade with its PnL."""
    def __init__(self, symbol: str, entry_price: float, exit_price: float, pnl: float, timestamp: datetime):
        self.symbol = symbol
        self.entry_price = entry_price
        self.exit_price = exit_price
        self.pnl = pnl
        self.timestamp = timestamp

class DataManager:
    """Manages historical trade data in memory."""
    def __init__(self):
        self.trades: List[Trade] = []

    def add_trade(self, trade: Trade):
        """Adds a trade to the manager."""
        self.trades.append(trade)
        # Optional: Keep trades sorted by timestamp or limit the list size
        self.trades.sort(key=lambda t: t.timestamp)
        # Limit the number of stored trades if memory becomes an issue
        # if len(self.trades) > 1000:
        #     self.trades = self.trades[-1000:]

    def get_trades(self, symbol: str, limit: int) -> List[Trade]:
        """
        Retrieves the last 'limit' trades for a given symbol.
        
        Args:
            symbol: The trading symbol.
            limit: The maximum number of trades to return.
            
        Returns:
            A list of Trade objects.
        """
        symbol_trades = [trade for trade in self.trades if trade.symbol == symbol]
        return symbol_trades[-limit:] # Return the last 'limit' trades