# strategies/chandelier_ehlers_strategy.py
from typing import List, Dict, Any
import pandas as pd
from datetime import datetime

from indicators.chandelier_exit import ChandelierExit
from indicators.ehlers_supertrend import EhlersSuperTrend
from signals.signal_generator import ChandelierEhlersSignalGenerator, Signal
from data.data_manager import BybitDataProvider

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
