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

def calculate_macd(df: pd.DataFrame, window_fast: int = 12, window_slow: int = 26, window_sign: int = 9, column: str = 'close') -> pd.DataFrame:
    """
    Calculates the Moving Average Convergence Divergence (MACD) for a given DataFrame.

    Args:
        df (pd.DataFrame): Input DataFrame with a 'close' column.
        window_fast (int): The fast period for MACD calculation.
        window_slow (int): The slow period for MACD calculation.
        window_sign (int): The signal line period for MACD calculation.
        column (str): The column to calculate MACD on. Defaults to 'close'.

    Returns:
        pd.DataFrame: DataFrame with MACD, MACD_Signal, and MACD_Diff added as new columns.
    """
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not found in DataFrame.")
    if len(df) < max(window_fast, window_slow, window_sign):
        df[f'macd_{window_fast}_{window_slow}'] = np.nan
        df[f'macd_signal_{window_fast}_{window_slow}_{window_sign}'] = np.nan
        df[f'macd_diff_{window_fast}_{window_slow}_{window_sign}'] = np.nan
        return df

    df[f'macd_{window_fast}_{window_slow}'] = ta.trend.macd(df[column], window_fast=window_fast, window_slow=window_slow, fillna=False)
    df[f'macd_signal_{window_fast}_{window_slow}_{window_sign}'] = ta.trend.macd_signal(df[column], window_fast=window_fast, window_slow=window_slow, window_sign=window_sign, fillna=False)
    df[f'macd_diff_{window_fast}_{window_slow}_{window_sign}'] = ta.trend.macd_diff(df[column], window_fast=window_fast, window_slow=window_slow, window_sign=window_sign, fillna=False)
    return df

def calculate_ehlers_fisher_transform(df: pd.DataFrame, period: int = 9, column: str = 'close') -> pd.DataFrame:
    """
    Calculates the Ehlers Fisher Transform for a given DataFrame.

    Args:
        df (pd.DataFrame): Input DataFrame with a 'close' column.
        period (int): The period for the Fisher Transform calculation.
        column (str): The column to calculate Fisher Transform on. Defaults to 'close'.

    Returns:
        pd.DataFrame: DataFrame with Fisher and Fisher_Signal added as new columns.
    """
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not found in DataFrame.")
    if len(df) < period:
        df[f'fisher_{period}'] = np.nan
        df[f'fisher_signal_{period}'] = np.nan
        return df

    # Calculate highest high and lowest low over the period
    lowest_low = df[column].rolling(window=period).min()
    highest_high = df[column].rolling(window=period).max()

    # Calculate Raw_Fisher
    # Avoid division by zero
    range_hl = highest_high - lowest_low
    range_hl[range_hl == 0] = 0.0001 # Small value to prevent division by zero

    raw_fisher = ((df[column] - lowest_low) / range_hl) * 2 - 1
    raw_fisher = raw_fisher.fillna(0) # Fill NaN from rolling window start

    # Apply Fisher Transform formula
    # Limit raw_fisher values to prevent inf/-inf from arctanh
    raw_fisher = np.clip(raw_fisher, -0.999, 0.999)
    fisher = 0.5 * np.log((1 + raw_fisher) / (1 - raw_fisher))
    fisher = fisher.ewm(span=3, adjust=False).mean() # Apply EMA smoothing as often seen

    # Calculate Fisher Signal
    fisher_signal = fisher.shift(1)

    df[f'fisher_{period}'] = fisher
    df[f'fisher_signal_{period}'] = fisher_signal
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

    # Use ta.trend.supertrend for a more efficient calculation
    # The ta library's supertrend returns multiple columns, we need to select the main line and direction
    st_data = ta.trend.supertrend(
        high=df['high'],
        low=df['low'],
        close=df['close'],
        window=period,
        fillna=False,
        multiplier=multiplier
    )
    
    # The ta library's supertrend returns columns like 'SUPERT_7_3.0', 'SUPERTd_7_3.0', 'SUPERTl_7_3.0', 'SUPERTs_7_3.0'
    # We need 'SUPERT_window_multiplier' for the supertrend line and 'SUPERTd_window_multiplier' for direction
    supertrend_col_name = f'SUPERT_{period}_{multiplier}'
    supertrend_direction_col_name = f'SUPERTd_{period}_{multiplier}'

    df['supertrend'] = st_data[supertrend_col_name]
    # Convert direction to 1 for uptrend, -1 for downtrend (ta uses 1 for up, -1 for down)
    df['supertrend_direction'] = st_data[supertrend_direction_col_name]
    
    return df