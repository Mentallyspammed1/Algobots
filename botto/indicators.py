# indicators/ehlers_supertrend.py
import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)

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
        if self.period <= 0:
            raise ValueError("Period must be positive.")
        if self.multiplier <= 0:
            raise ValueError("Multiplier must be positive.")
    
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate Ehlers SuperTrend values using vectorized operations.
        
        Args:
            df: DataFrame with OHLCV data. Must contain 'high', 'low', 'close'.
            
        Returns:
            DataFrame with SuperTrend values added. Returns original df if insufficient data or missing columns.
        """
        if df.empty:
            logger.warning("Input DataFrame is empty.")
            return df
        
        if not all(col in df.columns for col in ['high', 'low', 'close']):
            logger.error("DataFrame must contain 'high', 'low', 'close' columns for EhlersSuperTrend.")
            return df
            
        if len(df) < self.period:
            logger.warning(f"Not enough data ({len(df)} rows) to calculate EhlersSuperTrend with period={self.period}.")
            df['supertrend'] = np.nan
            df['supertrend_direction'] = np.nan
            return df

        # Calculate True Range (TR)
        high_low = df['high'] - df['low']
        high_prev_close = np.abs(df['high'] - df['close'].shift(1))
        low_prev_close = np.abs(df['low'] - df['close'].shift(1))
        
        # Use pd.concat and .max(axis=1) for vectorized TR calculation
        true_range = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
        
        # Calculate Average True Range (ATR) using EMA
        # Use .ewm() for efficient EMA calculation
        atr = true_range.ewm(span=self.period, adjust=False).mean()

        # Calculate Typical Price
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        
        # --- Ehlers' Cyclic Component (High-Pass Filter) ---
        # Calculate alpha for the filter
        # Ensure period is not zero to avoid division by zero
        if self.period == 0:
            logger.error("Ehlers Filter period cannot be zero.")
            df['hp'] = np.nan
        else:
            angle = 2 * np.pi / self.period
            alpha1 = (np.cos(angle) + np.sin(angle) - 1) / np.cos(angle)
            
            # Calculate HP using vectorized operations where possible
            # The recursive nature of HP makes full vectorization tricky without stateful operations.
            # We'll use .apply() for the recursive part, which is better than a raw loop.
            # Note: For extreme performance, a custom Cython or Numba implementation might be needed.
            
            hp_series = pd.Series(np.nan, index=df.index)
            
            # Calculate the first HP value manually if possible
            if len(df) > 1:
                hp_series.iloc[1] = 0.5 * (1 + alpha1) * (typical_price.iloc[1] - typical_price.iloc[0]) + alpha1 * 0 # Assuming previous hp was 0
            
            # Use .apply() for the recursive calculation
            # This is more efficient than a Python loop but less so than pure vectorization.
            # We need to pass previous 'hp' value, which .apply can handle with a lambda.
            # However, .apply() on a Series with a stateful lambda is not truly vectorized.
            # A more robust approach would be to use numba or a custom C extension.
            # For now, we'll stick to a loop for clarity, acknowledging the performance implication.
            # If performance is critical, this section needs optimization.
            
            # Reverting to loop for clarity of Ehlers' recursive formula, but flagging as performance bottleneck.
            # A truly vectorized solution for recursive filters is complex.
            df['hp'] = 0.0 # Initialize column
            for i in range(1, len(df)):
                if i == 1:
                    df.at[df.index[i], 'hp'] = 0.5 * (1 + alpha1) * (typical_price.iloc[i] - typical_price.iloc[i-1])
                else:
                    df.at[df.index[i], 'hp'] = 0.5 * (1 + alpha1) * (typical_price.iloc[i] - typical_price.iloc[i-1]) + alpha1 * df.at[df.index[i-1], 'hp']
        
        # --- SuperSmoother ---
        # Coefficients for SuperSmoother
        a1 = np.exp(-1.414 * np.pi / self.period)
        b1 = 2 * a1 * np.cos(1.414 * np.pi / self.period)
        c2 = b1
        c3 = -a1 * a1
        c1 = 1 - c2 - c3
        
        df['ss'] = 0.0 # Initialize column
        
        # SuperSmoother calculation is also recursive, using a loop for clarity.
        # This is another potential performance bottleneck.
        for i in range(2, len(df)):
            if i == 2:
                # Ensure previous hp values are not NaN
                hp_prev_sum = (df.at[df.index[i], 'hp'] + df.at[df.index[i-1], 'hp']) / 2
                if pd.isna(hp_prev_sum): hp_prev_sum = 0.0
                
                df.at[df.index[i], 'ss'] = c1 * hp_prev_sum + c2 * df.at[df.index[i-1], 'ss'] + c3 * df.at[df.index[i-2], 'ss']
            else:
                hp_prev_sum = (df.at[df.index[i], 'hp'] + df.at[df.index[i-1], 'hp']) / 2
                if pd.isna(hp_prev_sum): hp_prev_sum = 0.0
                
                df.at[df.index[i], 'ss'] = c1 * hp_prev_sum + c2 * df.at[df.index[i-1], 'ss'] + c3 * df.at[df.index[i-2], 'ss']
        
        # --- SuperTrend Calculation ---
        # This part is also stateful and iterative.
        # A truly vectorized SuperTrend implementation would track the trend direction and flip bands.
        # The original logic used typical_price vs its shifted value to determine trend,
        # and then applied multiplier*atr. We'll replicate that logic with a loop for clarity.
        
        df['supertrend'] = np.nan
        df['supertrend_direction'] = np.nan # 1 for uptrend, -1 for downtrend
        
        # Initialize first valid values
        # Find the first index where atr is not NaN
        first_atr_valid_idx = atr.first_valid_index()
        
        if first_atr_valid_idx is not None:
            # Start calculations from the first index where atr is valid
            start_calc_idx = df.index.get_loc(first_atr_valid_idx)
            
            # Initialize first bands and direction based on first valid close price
            if start_calc_idx < len(df) -1: # Ensure there's at least one more point for comparison
                # Initial direction based on first valid close vs midpoint
                # Use the 'ss' value as the primary trend indicator for SuperTrend
                initial_direction = 1 if df.iloc[start_calc_idx]['ss'] > 0 else -1
                
                if initial_direction == 1:
                    # Uptrend: SuperTrend is lower band
                    df.at[df.index[start_calc_idx], 'supertrend'] = mid_point.iloc[start_calc_idx] - self.multiplier * atr.iloc[start_calc_idx]
                    df.at[df.index[start_calc_idx], 'supertrend_direction'] = 1
                else:
                    # Downtrend: SuperTrend is upper band
                    df.at[df.index[start_calc_idx], 'supertrend'] = mid_point.iloc[start_calc_idx] + self.multiplier * atr.iloc[start_calc_idx]
                    df.at[df.index[start_calc_idx], 'supertrend_direction'] = -1

                # Loop for stateful SuperTrend calculation
                # This is a critical area for performance optimization if needed.
                for i in range(start_calc_idx + 1, len(df)):
                    current_close = df.iloc[i]['close']
                    current_mid_point = mid_point.iloc[i]
                    current_atr = atr.iloc[i]
                    prev_supertrend_dir = df.iloc[i-1]['supertrend_direction']
                    
                    # Calculate potential upper and lower bands for the current step
                    potential_upper_band = current_mid_point + self.multiplier * current_atr
                    potential_lower_band = current_mid_point - self.multiplier * current_atr
                    
                    # Determine SuperTrend and direction
                    if prev_supertrend_dir == 1: # Previous was uptrend
                        # If current close drops below the previous lower band, flip trend
                        if current_close < df.iloc[i-1]['supertrend']: # Check against previous supertrend value
                            df.at[df.index[i], 'supertrend'] = potential_upper_band
                            df.at[df.index[i], 'supertrend_direction'] = -1 # Downtrend
                        else:
                            df.at[df.index[i], 'supertrend'] = potential_lower_band
                            df.at[df.index[i], 'supertrend_direction'] = 1 # Uptrend
                    else: # Previous was downtrend
                        # If current close rises above the previous upper band, flip trend
                        if current_close > df.iloc[i-1]['supertrend']: # Check against previous supertrend value
                            df.at[df.index[i], 'supertrend'] = potential_lower_band
                            df.at[df.index[i], 'supertrend_direction'] = 1 # Uptrend
                        else:
                            df.at[df.index[i], 'supertrend'] = potential_upper_band
                            df.at[df.index[i], 'supertrend_direction'] = -1 # Downtrend
        
        # Clean up intermediate columns if desired
        # df = df.drop(columns=['tr', 'atr', 'typical_price'])
        
        return df
