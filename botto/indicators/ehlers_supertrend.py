# indicators/ehlers_supertrend.py
import numpy as np
import pandas as pd

class EhlersSuperTrend:
    """
    Ehlers SuperTrend indicator implementation.
    
    A trend-following indicator created by John Ehlers that uses cyclic 
    components of price action to identify trends with less lag than 
    traditional indicators.
    """
    
    def __init__(self, period=10, multiplier=3.0):
        """Initialize Ehlers SuperTrend indicator."""
        self.period = period
        self.multiplier = multiplier
    
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate Ehlers SuperTrend values.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with SuperTrend values added
        """
        if df.empty:
            return df
        
        # Calculate typical price
        df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3
        
        # Calculate True Range for SuperTrend
        df['tr'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift(1)),
                abs(df['low'] - df['close'].shift(1))
            )
        )
        
        # Calculate ATR for SuperTrend
        df['atr'] = df['tr'].rolling(window=self.period).mean()
        
        # Compute Ehlers' cyclic component using a roofing filter
        alpha1 = (np.cos(2 * np.pi / self.period) + np.sin(2 * np.pi / self.period) - 1) / np.cos(2 * np.pi / self.period)
        df['hp'] = 0.0
        
        for i in range(1, len(df)):
            if i == 1:
                df.at[df.index[i], 'hp'] = 0.5 * (1 + alpha1) * (df.at[df.index[i], 'typical_price'] - df.at[df.index[i-1], 'typical_price'])
            else:
                df.at[df.index[i], 'hp'] = 0.5 * (1 + alpha1) * (df.at[df.index[i], 'typical_price'] - df.at[df.index[i-1], 'typical_price']) + alpha1 * df.at[df.index[i-1], 'hp']
        
        # Apply SuperSmoother to the high-pass filter output
        a1 = np.exp(-1.414 * np.pi / self.period)
        b1 = 2 * a1 * np.cos(1.414 * np.pi / self.period)
        c2 = b1
        c3 = -a1 * a1
        c1 = 1 - c2 - c3
        
        df['ss'] = 0.0
        
        for i in range(2, len(df)):
            if i == 2:
                df.at[df.index[i], 'ss'] = c1 * (df.at[df.index[i], 'hp'] + df.at[df.index[i-1], 'hp']) / 2 + c2 * df.at[df.index[i-1], 'ss'] + c3 * df.at[df.index[i-2], 'ss']
            else:
                df.at[df.index[i], 'ss'] = c1 * (df.at[df.index[i], 'hp'] + df.at[df.index[i-1], 'hp']) / 2 + c2 * df.at[df.index[i-1], 'ss'] + c3 * df.at[df.index[i-2], 'ss']
        
        # Calculate SuperTrend
        df['supertrend'] = 0.0
        
        for i in range(self.period, len(df)):
            if df.at[df.index[i], 'typical_price'] > df.at[df.index[i-self.period], 'typical_price']:
                # Uptrend
                df.at[df.index[i], 'supertrend'] = df.at[df.index[i], 'typical_price'] - self.multiplier * df.at[df.index[i], 'atr']
            else:
                # Downtrend
                df.at[df.index[i], 'supertrend'] = df.at[df.index[i], 'typical_price'] + self.multiplier * df.at[df.index[i], 'atr']
        
        return df
