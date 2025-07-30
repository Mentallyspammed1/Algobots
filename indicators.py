# indicators.py
import pandas as pd
import logging
from typing import List, Dict, Any, Tuple
from decimal import Decimal, getcontext

from bot_logger import setup_logging

# Set precision for Decimal
getcontext().prec = 38

# Initialize logging for indicators
indicators_logger = logging.getLogger('indicators')
indicators_logger.setLevel(logging.INFO)
# Ensure handlers are not duplicated if setup_logging is called elsewhere
if not indicators_logger.handlers:
    setup_logging() # Call the centralized setup

def calculate_atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    """
    Calculates the Average True Range (ATR), a measure of market volatility.
    """
    if not all(col in df.columns for col in ['high', 'low', 'close']):
        indicators_logger.error("DataFrame must contain 'high', 'low', 'close' columns for ATR.")
        return pd.Series(dtype='object')

    high = df['high'].apply(Decimal)
    low = df['low'].apply(Decimal)
    close = df['close'].apply(Decimal)

    tr_df = pd.DataFrame(index=df.index)
    tr_df['h_l'] = high - low
    tr_df['h_pc'] = (high - close.shift(1)).abs()
    tr_df['l_pc'] = (low - close.shift(1)).abs()

    # Use a custom apply for max because pandas max() can be tricky with Decimals
    tr = tr_df[['h_l', 'h_pc', 'l_pc']].apply(lambda row: max(row.dropna()), axis=1)
    
    # Using SMA for ATR calculation with Decimals
    atr = tr.rolling(window=length).mean()
    return atr

def calculate_fibonacci_pivot_points(df: pd.DataFrame) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Calculates Fibonacci Pivot Points (Resistance and Support levels) using Decimal.
    """
    resistance_levels = []
    support_levels = []

    if df.empty:
        indicators_logger.warning("DataFrame is empty for Fibonacci pivot point calculation.")
        return resistance_levels, support_levels

    # Use the last complete candle for calculation
    last_candle = df.iloc[-1]
    high = Decimal(str(last_candle['high']))
    low = Decimal(str(last_candle['low']))
    close = Decimal(str(last_candle['close']))

    # Calculate Pivot Point (PP)
    pp = (high + low + close) / Decimal('3')

    # Calculate Range
    price_range = high - low

    # Calculate Resistance Levels
    r1 = pp + (price_range * Decimal('0.382'))
    r2 = pp + (price_range * Decimal('0.618'))
    r3 = pp + (price_range * Decimal('1.000'))

    # Calculate Support Levels
    s1 = pp - (price_range * Decimal('0.382'))
    s2 = pp - (price_range * Decimal('0.618'))
    s3 = pp - (price_range * Decimal('1.000'))

    # Round to nearest 5
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

    indicators_logger.debug(f"Fibonacci Pivot Points calculated: PP={pp:.2f}, R1={r1:.2f}, S1={s1:.2f}")
    return resistance_levels, support_levels

def calculate_stochrsi(df: pd.DataFrame, rsi_period: int = 14, stoch_k_period: int = 14, stoch_d_period: int = 3) -> pd.DataFrame:
    """
    Calculates the Stochastic RSI (StochRSI) for a given DataFrame using Decimal.
    """
    if 'close' not in df.columns:
        indicators_logger.error("DataFrame must contain a 'close' column for StochRSI calculation.")
        return df

    # Convert to Decimal
    df['close'] = df['close'].apply(lambda x: Decimal(str(x)))

    # Calculate RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, Decimal('0'))
    loss = -delta.where(delta < 0, Decimal('0'))

    avg_gain = gain.ewm(com=rsi_period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=rsi_period - 1, adjust=False).mean()

    # Ensure avg_loss does not contain zero before division
    rs = avg_gain / avg_loss.replace(Decimal('0'), Decimal('1e-38'))
    # Convert the pandas Series to Decimal before performing arithmetic with a Decimal scalar
    df['rsi'] = rs.apply(lambda x: Decimal('100') - (Decimal('100') / (Decimal('1') + Decimal(str(x)))))

    # Calculate StochRSI
    lowest_rsi = df['rsi'].rolling(window=stoch_k_period).min().apply(Decimal)
    highest_rsi = df['rsi'].rolling(window=stoch_k_period).max().apply(Decimal)
    rsi_range = highest_rsi - lowest_rsi

    # Ensure rsi_range does not contain zero before division
    stoch_rsi_val = (df['rsi'] - lowest_rsi) / rsi_range.replace(Decimal('0'), Decimal('1e-38'))
    df['stoch_rsi'] = stoch_rsi_val.apply(lambda x: Decimal('100') * Decimal(str(x)))
    df['stoch_rsi'] = df['stoch_rsi'].fillna(Decimal('0'))

    # Calculate %K (Stoch_K)
    df['stoch_k'] = df['stoch_rsi'].rolling(window=stoch_k_period).mean()
    df['stoch_k'] = df['stoch_k'].fillna(Decimal('0'))

    # Calculate %D (Stoch_D)
    df['stoch_d'] = df['stoch_k'].rolling(window=stoch_d_period).mean()
    df['stoch_d'] = df['stoch_d'].fillna(Decimal('0'))

    indicators_logger.debug(f"StochRSI calculated with rsi_period={rsi_period}, stoch_k_period={stoch_k_period}, stoch_d_period={stoch_d_period}.")
    return df

def handle_websocket_kline_data(df: pd.DataFrame, message: Dict[str, Any]) -> pd.DataFrame:
    """
    Processes a single kline data message from a WebSocket stream.
    It updates the last row if the candle is not confirmed, or appends a new row if it is.
    """
    if not isinstance(message, dict) or 'data' not in message or not message['data']:
        indicators_logger.error(f"Invalid kline WebSocket message received: {message}")
        return df

    kline_data = message['data'][0] # Extract the kline object from the 'data' list

    # Extract and format the new kline data
    new_kline = {
        'timestamp': pd.to_datetime(kline_data['start'], unit='ms'),
        'open': Decimal(kline_data['open']),
        'high': Decimal(kline_data['high']),
        'low': Decimal(kline_data['low']),
        'close': Decimal(kline_data['close']),
        'volume': Decimal(kline_data['volume']),
    }
    
    # Set the timestamp as the index for the new kline
    new_kline_df = pd.DataFrame([new_kline]).set_index('timestamp')

    if df.empty:
        indicators_logger.info("DataFrame is empty, initializing with new kline data.")
        return new_kline_df

    # If the new kline's timestamp matches the last one in the DataFrame, update it
    if new_kline_df.index[0] == df.index[-1]:
        df.iloc[-1] = new_kline_df.iloc[0]
        indicators_logger.debug(f"Updated last kline at {new_kline_df.index[0]}")
    # Otherwise, append it as a new row
    else:
        df = pd.concat([df, new_kline_df])
        indicators_logger.debug(f"Appended new kline at {new_kline_df.index[0]}")

    return df
