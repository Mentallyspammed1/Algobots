# strategies/chandelier_ehlers_strategy.py
from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np
from datetime import datetime

from indicators.chandelier_exit import ChandelierExit
from indicators.ehlers_supertrend import EhlersSuperTrend
from signals.signal_generator import ChandelierEhlersSignalGenerator, Signal
from data.data_manager import BybitDataProvider, DataManager # Import DataManager

class ChandelierEhlersSuperTrendStrategy:
    """
    Chandelier Exit Ehlers SuperTrend Cross Strategy.
    
    This strategy combines two powerful indicators:
    1. Chandelier Exit - A volatility-based indicator used for setting trailing stop-loss levels
    2. Ehlers SuperTrend - A trend-following indicator created by John Ehlers
    
    Signals are generated when these indicators cross each other:
    - Buy signal: When price crosses above the SuperTrend and Chandelier Exit confirms the trend
    - Sell signal: When price crosses below the SuperTrend and Chandelier Exit confirms the trend
    """
    
    def __init__(self, config: Dict[str, Any], session):
        """Initialize strategy."""
        self.config = config
        self.session = session
        
        # Initialize components
        self.data_provider = BybitDataProvider(session)
        self.chandelier_exit = ChandelierExit(
            period=config.get('chandelier_period', 22),
            multiplier=config.get('chandelier_multiplier', 3.0)
        )
        self.ehlers_supertrend = EhlersSuperTrend(
            period=config.get('supertrend_period', 10),
            multiplier=config.get('supertrend_multiplier', 3.0)
        )
        self.signal_generator = ChandelierEhlersSignalGenerator(
            min_strength=config.get('min_signal_strength', 0.5),
            min_confidence=config.get('min_signal_confidence', 0.6)
        )
        
        # Data cache
        self.data_cache = {}

        # --- Dependencies for Dynamic Position Sizing ---
        self.db_manager = DataManager() # Initialize DataManager
        
        # Placeholder for current prices, should be updated by market data stream or similar
        self.current_prices: Dict[str, float] = {} 
        
        # Initialize Bybit API client if needed for balance retrieval
        # Assuming 'session' is already an instance of RestClientV5 or similar

    def get_account_balance(self) -> float:
        """
        Fetches the current account balance from Bybit.
        Assumes self.session is a RestClientV5 instance.
        """
        try:
            # Fetch account information
            account_info = self.session.get_account_info(accountType="UNIFIED")
            
            if account_info and account_info['retCode'] == 0:
                # Attempt to find USDT equity
                if 'USDT' in account_info['result']:
                    return float(account_info['result']['USDT'].get('equity', 0.0))
                elif 'list' in account_info['result'] and isinstance(account_info['result']['list'], list):
                    for balance_entry in account_info['result']['list']:
                        if balance_entry.get('coin') == 'USDT':
                            return float(balance_entry.get('equity', 0.0))
                
                print("Warning: Could not find USDT balance in account info. Returning 0.0.")
                return 0.0
            else:
                print(f"Error fetching account balance: {account_info.get('retMsg', 'Unknown error')}")
                return 0.0
                
        except AttributeError:
            print("Error: 'session' object does not have the expected method for fetching account balance (e.g., get_account_info).")
            return 0.0
        except Exception as e:
            print(f"Error fetching account balance: {str(e)}")
            return 0.0

    def calculate_position_size(self, symbol: str, signal_type: str) -> float:
        """
        Calculates dynamic position size using the Kelly Criterion.
        
        Args:
            symbol: The trading symbol.
            signal_type: The type of signal ('BUY' or 'SELL').
            
        Returns:
            The calculated position size in quantity.
        """
        # Get historical performance data
        if not hasattr(self, 'db_manager') or not hasattr(self.db_manager, 'get_trades'):
            print("Error: db_manager or its get_trades method not available. Returning default size.")
            return self.config.get('DEFAULT_POSITION_SIZE', 0.001) # Use config value
            
        trades = self.db_manager.get_trades(symbol=symbol, limit=50)
        
        if not trades:
            # Return default size if no historical trades are available
            return self.config.get('DEFAULT_POSITION_SIZE', 0.001) # Use config value
        
        # Calculate win rate
        winning_trades = sum(1 for trade in trades if trade.pnl > 0)
        win_rate = winning_trades / len(trades)
        
        # Calculate average win/loss ratio
        wins = [trade.pnl for trade in trades if trade.pnl > 0]
        losses = [abs(trade.pnl) for trade in trades if trade.pnl < 0]
        
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 1 # Avoid division by zero
        
        win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 1
        
        # Apply Kelly Criterion formula
        if win_loss_ratio == 0:
            kelly_fraction = 0
        else:
            kelly_fraction = (win_rate * win_loss_ratio - (1 - win_rate)) / win_loss_ratio
        
        # Cap the Kelly fraction to prevent overly aggressive sizing
        kelly_fraction = max(0.01, min(0.25, kelly_fraction))
        
        # Get account balance
        balance = self.get_account_balance()
        
        # Calculate capital to risk based on Kelly fraction and config risk_per_trade multiplier
        capital_to_risk = balance * kelly_fraction * self.config.get('KELLY_RISK_PER_TRADE_MULTIPLIER', 0.02) # Use config value
        
        # Get current price for the symbol
        if not hasattr(self, 'current_prices') or symbol not in self.current_prices:
            print(f"Warning: Could not get valid current price for {symbol}. Using fallback price from config.")
            current_price = self.config.get('fallback_price', 50000) # Use config value for fallback price
        else:
            current_price = self.current_prices[symbol]
            
        if current_price <= 0:
            print(f"Warning: Current price for {symbol} is zero or negative ({current_price}). Using fallback price from config.")
            current_price = self.config.get('fallback_price', 50000) # Use config value for fallback price
            
        # Calculate position size in terms of quantity
        position_size = capital_to_risk / current_price
        
        # Ensure position size is not negative or zero, and respects minimums from config
        position_size = max(position_size, self.config.get('MIN_POSITION_SIZE', 0.0001)) # Use config value
        
        return position_size

    def generate_signals(self, symbols: List[str]) -> List[Signal]:
        """
        Generate trading signals for the specified symbols.
        
        Args:
            symbols: List of trading symbols
            
        Returns:
            List of Signal objects
        """
        signals = []
        
        try:
            for symbol in symbols:
                # Get historical data
                df = self.data_provider.get_historical_data(
                    symbol=symbol,
                    timeframe=self.config.get('timeframe', '15'),
                    limit=self.config.get('data_limit', 200)
                )
                
                if df.empty or len(df) < max(
                    self.config.get('chandelier_period', 22), 
                    self.config.get('supertrend_period', 10)
                ) * 2:
                    continue
                
                # Calculate indicators
                df = self.chandelier_exit.calculate(df)
                df = self.ehlers_supertrend.calculate(df)
                
                # Determine current Chandelier Exit value based on trend direction
                df['chandelier_exit'] = df.apply(
                    lambda row: row['chandelier_long'] if row['supertrend'] < row['close'] else row['chandelier_short'],
                    axis=1
                )
                
                # Generate signals
                symbol_signals = self.signal_generator.generate_signals(df, symbol)
                signals.extend(symbol_signals)
            
            return signals
            
        except Exception as e:
            print(f"Error generating signals: {str(e)}")
            return []
    
    def get_indicator_values(self, symbol: str) -> Dict[str, float]:
        """
        Get current indicator values for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Dictionary with current indicator values
        """
        try:
            # Get historical data
            df = self.data_provider.get_historical_data(
                symbol=symbol,
                timeframe=self.config.get('timeframe', '15'),
                limit=self.config.get('data_limit', 200)
            )
            
            if df.empty:
                return {}
            
            # Calculate indicators
            df = self.chandelier_exit.calculate(df)
            df = self.ehlers_supertrend.calculate(df)
            
            # Determine current Chandelier Exit value based on trend direction
            df['chandelier_exit'] = df.apply(
                lambda row: row['chandelier_long'] if row['supertrend'] < row['close'] else row['chandelier_short'],
                axis=1
            )
            
            # Get latest values
            last_row = df.iloc[-1]
            
            return {
                'supertrend': last_row['supertrend'],
                'chandelier_exit': last_row['chandelier_exit'],
                'atr': last_row['atr'],
                'price': last_row['close']
            }
            
        except Exception as e:
            print(f"Error getting indicator values: {str(e)}")
            return {}