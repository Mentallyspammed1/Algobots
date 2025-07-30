# indicators.py
import pandas as pd
import logging
from typing import List, Dict, Any, Tuple
from decimal import Decimal, getcontext, ROUND_HALF_UP
import math

from bot_logger import setup_logging

# Set precision for Decimal
getcontext().prec = 38

# Initialize logging for indicators
indicators_logger = logging.getLogger('indicators')
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

    indicators_logger.debug(f"Input for Fibonacci: High={high:.8f}, Low={low:.8f}, Close={close:.8f}")

    # Calculate Pivot Point (PP)
    pp = (high + low + close) / Decimal('3')

    # Calculate Range
    price_range = high - low
    indicators_logger.debug(f"Calculated PP: {pp:.8f}, Price Range: {price_range:.8f}")

    # Calculate Resistance Levels
    r1_unrounded = pp + (price_range * Decimal('0.382'))
    r2_unrounded = pp + (price_range * Decimal('0.618'))
    r3_unrounded = pp + (price_range * Decimal('1.000'))

    # Calculate Support Levels
    s1_unrounded = pp - (price_range * Decimal('0.382'))
    s2_unrounded = pp - (price_range * Decimal('0.618'))
    s3_unrounded = pp - (price_range * Decimal('1.000'))

    indicators_logger.debug(f"Unrounded R1: {r1_unrounded:.8f}, R2: {r2_unrounded:.8f}, R3: {r3_unrounded:.8f}")
    indicators_logger.debug(f"Unrounded S1: {s1_unrounded:.8f}, S2: {s2_unrounded:.8f}, S3: {s3_unrounded:.8f}")

    # Round to 2 decimal places for more meaningful values on low-priced assets
    r1 = r1_unrounded.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    r2 = r2_unrounded.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    r3 = r3_unrounded.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    s1 = s1_unrounded.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    s2 = s2_unrounded.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    s3 = s3_unrounded.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

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

def calculate_sma(df: pd.DataFrame, length: int) -> pd.Series:
    """
    Calculates the Simple Moving Average (SMA) for the 'close' prices.
    """
    if 'close' not in df.columns:
        indicators_logger.error("DataFrame must contain a 'close' column for SMA calculation.")
        return pd.Series(dtype='object')
    
    # Ensure 'close' column is Decimal type
    close_prices = df['close'].apply(Decimal)
    sma = close_prices.rolling(window=length).mean()
    return sma

def calculate_ehlers_fisher_transform(df: pd.DataFrame, length: int = 9, signal_length: int = 1) -> Tuple[pd.Series, pd.Series]:
    """
    Calculates the Ehlers Fisher Transform and its signal line.
    """
    if 'high' not in df.columns or 'low' not in df.columns:
        indicators_logger.error("DataFrame must contain 'high' and 'low' columns for Fisher Transform.")
        return pd.Series(dtype='object'), pd.Series(dtype='object')

    high = df['high'].apply(Decimal)
    low = df['low'].apply(Decimal)

    # Calculate the median price
    median_price = (high + low) / Decimal('2')

    # Normalize the price to a range of -1 to +1
    # This is a simplified approach; Ehlers' original might involve more complex normalization
    min_val = median_price.rolling(window=length).min().apply(lambda x: Decimal(str(x)) if pd.notna(x) else Decimal('NaN'))
    max_val = median_price.rolling(window=length).max().apply(lambda x: Decimal(str(x)) if pd.notna(x) else Decimal('NaN'))

    # Avoid division by zero and handle NaN propagation
    range_val = max_val - min_val
    # Replace 0 with a small number only if min_val and max_val are not NaN
    range_val = range_val.replace(Decimal('0'), Decimal('1e-38'))

    x = (median_price - min_val) / range_val
    x = x.apply(lambda val: Decimal('2') * (val - Decimal('0.5')) if not val.is_nan() else Decimal('NaN'))

    # Ensure x is within (-0.999, 0.999) to avoid issues with log
    x = x.apply(lambda val: Decimal('NaN') if val.is_nan() else (Decimal('0.999') if val >= Decimal('1') else (Decimal('-0.999') if val <= Decimal('-1') else val)))

    # Fisher Transform formula
    # Using Decimal for calculations, but math.log requires float, so convert back and forth carefully
    fisher_transform = x.apply(lambda val: Decimal('NaN') if val.is_nan() else Decimal('0.5') * Decimal(str(math.log((1 + float(val)) / (1 - float(val))))))
    
    # Calculate Fisher Signal
    fisher_signal = fisher_transform.rolling(window=signal_length).mean()

    return fisher_transform, fisher_signal

def calculate_ehlers_super_smoother(df: pd.DataFrame, length: int = 10) -> pd.Series:
    """
    Calculates the Ehlers 2-pole Super Smoother Filter.
    """
    if 'close' not in df.columns:
        indicators_logger.error("DataFrame must contain a 'close' column for Super Smoother.")
        return pd.Series(dtype='object')

    close_prices = df['close'].apply(Decimal)

    # Convert length to float for math functions
    float_length = float(length)

    # Calculate coefficients
    # Ensure pi and sqrt(2) are Decimal for intermediate calculations if needed, but math functions take float
    a1 = Decimal(str(math.exp(-math.sqrt(2) * math.pi / float_length)))
    b1 = Decimal(str(2 * a1 * Decimal(str(math.cos(math.sqrt(2) * math.pi / float_length)))))
    c2 = b1
    c3 = -a1 * a1
    c1 = Decimal('1') - c2 - c3

    filtered_values = pd.Series(index=df.index, dtype='object')
    filt1 = Decimal('0')
    filt2 = Decimal('0')

    for i in range(len(close_prices)):
        current_input = close_prices.iloc[i]
        prev_input = close_prices.iloc[i-1] if i > 0 else Decimal('0')

        if i == 0:
            filtered_values.iloc[i] = current_input
        elif i == 1:
            filtered_values.iloc[i] = c1 * (current_input + prev_input) / Decimal('2') + c2 * filtered_values.iloc[i-1]
        else:
            filt = c1 * (current_input + prev_input) / Decimal('2') + c2 * filtered_values.iloc[i-1] + c3 * filtered_values.iloc[i-2]
            filtered_values.iloc[i] = filt
    
    return filtered_values

def find_pivots(df: pd.DataFrame, left: int, right: int, use_wicks: bool) -> Tuple[pd.Series, pd.Series]:
    """
    Identifies Pivot Highs and Lows based on lookback periods.
    A pivot high is a candle whose high is greater than or equal to the highs of 'left' candles to its left
    and 'right' candles to its right.
    A pivot low is a candle whose low is less than or equal to the lows of 'left' candles to its left
    and 'right' candles to its right.
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        indicators_logger.error("DataFrame index must be a DatetimeIndex for pivot calculation.")
        return pd.Series(dtype='bool'), pd.Series(dtype='bool')

    if 'high' not in df.columns or 'low' not in df.columns:
        indicators_logger.error("DataFrame must contain 'high' and 'low' columns for pivot identification.")
        return pd.Series(dtype='bool'), pd.Series(dtype='bool')

    # Ensure high and low columns are Decimal for accurate comparison
    high_prices = df['high'].apply(Decimal)
    low_prices = df['low'].apply(Decimal)

    pivot_highs = pd.Series(False, index=df.index)
    pivot_lows = pd.Series(False, index=df.index)

    # Iterate through the DataFrame to find pivots
    # Start from 'left' index and end at 'len(df) - right'
    for i in range(left, len(df) - right):
        # Check for Pivot High
        is_pivot_high = True
        current_high = high_prices.iloc[i]
        for j in range(1, left + 1):
            if current_high < high_prices.iloc[i - j]:
                is_pivot_high = False
                break
        if is_pivot_high:
            for j in range(1, right + 1):
                if current_high < high_prices.iloc[i + j]:
                    is_pivot_high = False
                    break
        pivot_highs.iloc[i] = is_pivot_high

        # Check for Pivot Low
        is_pivot_low = True
        current_low = low_prices.iloc[i]
        for j in range(1, left + 1):
            if current_low > low_prices.iloc[i - j]:
                is_pivot_low = False
                break
        if is_pivot_low:
            for j in range(1, right + 1):
                if current_low > low_prices.iloc[i + j]:
                    is_pivot_low = False
                    break
        pivot_lows.iloc[i] = is_pivot_low

    indicators_logger.debug(f"Pivots identified with left={left}, right={right}, use_wicks={use_wicks}.")
    return pivot_highs, pivot_lows

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