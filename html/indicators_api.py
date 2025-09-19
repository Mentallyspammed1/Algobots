import pandas as pd
import numpy as np
import ta

def calculate_ema(df: pd.DataFrame, period: int = 14, column: str = 'close') -> pd.DataFrame:
    """
    Calculates the Exponential Moving Average (EMA) for a given DataFrame.

    Args:
        df (pd.DataFrame): Input DataFrame with a 'close' column.
        period (int): The period for the EMA calculation.
        column (str): The column to calculate EMA on. Defaults to 'close'.

    Returns:
        pd.DataFrame: DataFrame with the EMA added as a new column.
    """
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not found in DataFrame.")
    if len(df) < period:
        # Not enough data to calculate EMA for the given period
        df[f'ema_{period}'] = np.nan
        return df
    df[f'ema_{period}'] = ta.trend.ema_indicator(df[column], window=period, fillna=False)
    return df

def calculate_rsi(df: pd.DataFrame, period: int = 14, column: str = 'close') -> pd.DataFrame:
    """
    Calculates the Relative Strength Index (RSI) for a given DataFrame.

    Args:
        df (pd.DataFrame): Input DataFrame with a 'close' column.
        period (int): The period for the RSI calculation.
        column (str): The column to calculate RSI on. Defaults to 'close'.

    Returns:
        pd.DataFrame: DataFrame with the RSI added as a new column.
    """
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not found in DataFrame.")
    if len(df) < period:
        # Not enough data to calculate RSI for the given period
        df[f'rsi_{period}'] = np.nan
        return df
    df[f'rsi_{period}'] = ta.momentum.rsi(df[column], window=period, fillna=False)
    return df

def calculate_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    """
    Calculates the Supertrend indicator for a given DataFrame.

    Args:
        df (pd.DataFrame): Input DataFrame with 'high', 'low', and 'close' columns.
        period (int): The period for the ATR calculation.
        multiplier (float): The multiplier for the ATR.

    Returns:
        pd.DataFrame: DataFrame with Supertrend and Supertrend_Direction added as new columns.
    """
    if not all(col in df.columns for col in ['high', 'low', 'close']):
        raise ValueError("DataFrame must contain 'high', 'low', and 'close' columns for Supertrend calculation.")
    
    # Ensure enough data for ATR calculation
    if len(df) < period:
        df['supertrend'] = np.nan
        df['supertrend_direction'] = np.nan
        return df

    # Calculate ATR
    atr = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=period, fillna=False)

    # Calculate Basic Upper and Lower Bands
    basic_upper_band = ((df['high'] + df['low']) / 2) + (multiplier * atr)
    basic_lower_band = ((df['high'] + df['low']) / 2) - (multiplier * atr)

    # Initialize final bands and supertrend
    final_upper_band = pd.Series(index=df.index, dtype=float)
    final_lower_band = pd.Series(index=df.index, dtype=float)
    supertrend = pd.Series(index=df.index, dtype=float)
    supertrend_direction = pd.Series(index=df.index, dtype=int) # 1 for uptrend, -1 for downtrend

    for i in range(len(df)):
        if i == 0:
            final_upper_band.iloc[i] = basic_upper_band.iloc[i]
            final_lower_band.iloc[i] = basic_lower_band.iloc[i]
            supertrend_direction.iloc[i] = 1 # Assume uptrend initially
        else:
            # Update final upper band
            if basic_upper_band.iloc[i] < final_upper_band.iloc[i-1] or df['close'].iloc[i-1] > final_upper_band.iloc[i-1]:
                final_upper_band.iloc[i] = basic_upper_band.iloc[i]
            else:
                final_upper_band.iloc[i] = final_upper_band.iloc[i-1]

            # Update final lower band
            if basic_lower_band.iloc[i] > final_lower_band.iloc[i-1] or df['close'].iloc[i-1] < final_lower_band.iloc[i-1]:
                final_lower_band.iloc[i] = basic_lower_band.iloc[i]
            else:
                final_lower_band.iloc[i] = final_lower_band.iloc[i-1]

            # Determine trend and Supertrend line
            if supertrend_direction.iloc[i-1] == 1: # Previous trend was up
                if df['close'].iloc[i] <= final_lower_band.iloc[i]:
                    supertrend_direction.iloc[i] = -1 # Trend changed to down
                    supertrend.iloc[i] = final_upper_band.iloc[i]
                else:
                    supertrend_direction.iloc[i] = 1 # Trend remains up
                    supertrend.iloc[i] = final_lower_band.iloc[i]
            else: # Previous trend was down
                if df['close'].iloc[i] >= final_upper_band.iloc[i]:
                    supertrend_direction.iloc[i] = 1 # Trend changed to up
                    supertrend.iloc[i] = final_lower_band.iloc[i]
                else:
                    supertrend_direction.iloc[i] = -1 # Trend remains down
                    supertrend.iloc[i] = final_upper_band.iloc[i]
    
    df['supertrend'] = supertrend
    df['supertrend_direction'] = supertrend_direction
    return df