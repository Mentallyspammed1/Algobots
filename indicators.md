# indicators.py
import pandas as pd
import logging
from typing import List, Dict, Any, Tuple

# Assuming bot_logger.py exists and handles centralized logging setup
from bot_logger import setup_logging

# Initialize logging for indicators
indicators_logger = logging.getLogger('indicators')
indicators_logger.setLevel(logging.INFO)
# Ensure handlers are not duplicated if setup_logging is called elsewhere
if not indicators_logger.handlers:
    setup_logging() # Call the centralized setup

def calculate_fibonacci_pivot_points(df: pd.DataFrame) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    <#FFD700>Calculates Fibonacci Pivot Points (Resistance and Support levels).</#FFD700>

    This method uses the traditional Fibonacci pivot point formula based on the
    previous period's high, low, and close prices. The levels are then rounded
    to the nearest 5, a common practice in certain trading strategies for
    specific asset types.

    Args:
        df (pd.DataFrame): DataFrame with 'high', 'low', and 'close' columns.
                           <#87CEEB>It's expected that the DataFrame contains at least one row
                           with these columns.</#87CEEB>

    Returns:
        tuple[list, list]: A tuple containing two lists:
                           - <#98FB98>resistance_levels (list of dicts: {'price': float, 'type': str})</#98FB98>
                           - <#F08080>support_levels (list of dicts: {'price': float, 'type': str})</#F08080>
    """
    resistance_levels = []
    support_levels = []

    if df.empty:
        indicators_logger.warning("<#FFA07A>DataFrame is empty for Fibonacci pivot point calculation. Returning empty lists.</#FFA07A>")
        return resistance_levels, support_levels
    
    if len(df) < 1:
        indicators_logger.warning("<#FFA07A>Not enough data in DataFrame for Fibonacci pivot point calculation. Need at least one candle.</#FFA07A>")
        return resistance_levels, support_levels

    # Use the last complete candle for calculation
    last_candle = df.iloc[-1]
    
    # <#87CEEB>Validate essential columns exist in the last_candle Series</#87CEEB>
    required_cols = ['high', 'low', 'close']
    if not all(col in last_candle for col in required_cols):
        indicators_logger.error(f"<#FF6347>Missing required columns ({', '.join(required_cols)}) in DataFrame for Fibonacci pivot points.</#FF6347>")
        return resistance_levels, support_levels

    high = last_candle['high']
    low = last_candle['low']
    close = last_candle['close']

    # Calculate Pivot Point (PP)
    pp = (high + low + close) / 3

    # Calculate Range
    price_range = high - low

    # Calculate Resistance Levels
    r1 = pp + (price_range * 0.382)
    r2 = pp + (price_range * 0.618)
    r3 = pp + (price_range * 1.000)

    # Calculate Support Levels
    s1 = pp - (price_range * 0.382)
    s2 = pp - (price_range * 0.618)
    s3 = pp - (price_range * 1.000)

    # <#FFFF00>Note: Rounding to nearest 5. This is a specific strategic choice and might not be universally applicable.</#FFFF00>
    r1 = round(r1 / 5) * 5
    r2 = round(r2 / 5) * 5
    r3 = round(r3 / 5) * 5
    s1 = round(s1 / 5) * 5
    s2 = round(s2 / 5) * 5
    s3 = round(s3 / 5) * 5

    resistance_levels.append({'price': r1, 'type': 'R1'})
    resistance_levels.append({'price': r2, 'type': 'R2'})
    resistance_levels.append({'price': r3, 'type': 'R3'})

    support_levels.append({'price': s1, 'type': 'S1'})
    support_levels.append({'price': s2, 'type': 'S2'})
    support_levels.append({'price': s3, 'type': 'S3'})

    indicators_logger.debug(f"<#ADD8E6>Fibonacci Pivot Points calculated: PP={pp:.2f}, R1={r1:.2f}, S1={s1:.2f}</#ADD8E6>")
    return resistance_levels, support_levels

def calculate_stochrsi(df: pd.DataFrame, rsi_period: int = 14, stoch_k_period: int = 14, stoch_d_period: int = 3) -> pd.DataFrame:
    """
    <#FFD700>Calculates the Stochastic RSI (StochRSI) indicator.</#FFD700>

    StochRSI is an oscillator that measures the level of RSI relative to its
    high-low range over a set period of time. It's an indicator of an indicator,
    often used to identify overbought/oversold conditions more clearly than RSI alone.

    Args:
        df (pd.DataFrame): DataFrame with a 'close' price column.
        rsi_period (int): The number of periods to use for the initial RSI calculation.
        stoch_k_period (int): The number of periods to use for the %K calculation on RSI.
        stoch_d_period (int): The number of periods to use for the %D (SMA of %K) calculation.

    Returns:
        pd.DataFrame: The input DataFrame with 'RSI', 'StochRSI_K', and 'StochRSI_D' columns added.
                      Returns an empty DataFrame if input is invalid or insufficient data.
    """
    if df.empty:
        indicators_logger.warning("<#FFA07A>DataFrame is empty for StochRSI calculation. Returning empty DataFrame.</#FFA07A>")
        return pd.DataFrame()

    if 'close' not in df.columns:
        indicators_logger.error("<#FF6347>Missing 'close' column in DataFrame for StochRSI calculation.</#FF6347>")
        return pd.DataFrame()

    # <#87CEEB>Ensure sufficient data for calculations</#87CEEB>
    min_data_points = rsi_period + stoch_k_period + stoch_d_period # A conservative estimate
    if len(df) < min_data_points:
        indicators_logger.warning(f"<#FFA07A>Not enough data ({len(df)} rows) for StochRSI calculation. Need at least {min_data_points} rows. Returning original DataFrame.</#FFA07A>")
        # Return original DF with NaN columns if not enough data to prevent errors downstream
        df['RSI'] = pd.NA
        df['StochRSI_K'] = pd.NA
        df['StochRSI_D'] = pd.NA
        return df

    # <#98FB98>Step 1: Calculate RSI</#98FB98>
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.ewm(com=rsi_period - 1, min_periods=rsi_period).mean()
    avg_loss = loss.ewm(com=rsi_period - 1, min_periods=rsi_period).mean()

    rs = avg_gain / avg_loss
    # Handle division by zero for rs (when avg_loss is 0)
    rs = rs.replace([float('inf'), -float('inf')], pd.NA)
    
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # <#F08080>Step 2: Calculate %K of RSI</#F08080>
    # Apply Stochastic formula to the RSI values
    lowest_rsi = df['RSI'].rolling(window=stoch_k_period, min_periods=stoch_k_period).min()
    highest_rsi = df['RSI'].rolling(window=stoch_k_period, min_periods=stoch_k_period).max()

    # Handle division by zero if highest_rsi == lowest_rsi
    denominator = (highest_rsi - lowest_rsi)
    
    df['StochRSI_K'] = ((df['RSI'] - lowest_rsi) / denominator) * 100
    df['StochRSI_K'] = df['StochRSI_K'].fillna(0) # If denominator is 0, RSI is flat, so %K is 0

    # <#ADD8E6>Step 3: Calculate %D (SMA of %K)</#ADD8E6>
    df['StochRSI_D'] = df['StochRSI_K'].rolling(window=stoch_d_period, min_periods=stoch_d_period).mean()

    indicators_logger.debug(f"<#ADD8E6>StochRSI calculated with RSI period={rsi_period}, K period={stoch_k_period}, D period={stoch_d_period}.</#ADD8E6>")
    return df
