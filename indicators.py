import pandas as pd
import logging
from typing import List, Dict, Any, Tuple
from decimal import Decimal, getcontext, ROUND_HALF_UP
import math
from colorama import init, Fore, Style

from bot_logger import setup_logging

# Initialize colorama for vibrant terminal output
init()

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
        indicators_logger.error(Fore.RED + "DataFrame must contain 'high', 'low', 'close' columns for ATR." + Style.RESET_ALL)
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
    atr = tr.rolling(window=length).mean().apply(Decimal)
    indicators_logger.debug(Fore.CYAN + f"ATR calculated with length={length}." + Style.RESET_ALL)
    return atr

def calculate_fibonacci_pivot_points(df: pd.DataFrame, fib_ratios: List[float] = [0.382, 0.618, 1.000], atr_length: int = 14) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Calculates Fibonacci Pivot Points with customizable ratios and ATR-based adjustments.
    Returns resistance and support levels as lists of dictionaries.
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        indicators_logger.error(Fore.RED + "DataFrame index must be a DatetimeIndex for pivot calculation." + Style.RESET_ALL)
        return [], []
    resistance_levels = []
    support_levels = []

    # Validate input DataFrame
    required_columns = ['high', 'low', 'close']
    if not all(col in df.columns for col in required_columns):
        indicators_logger.error(Fore.RED + f"DataFrame missing required columns: {', '.join(required_columns)}." + Style.RESET_ALL)
        return resistance_levels, support_levels

    if df.empty or len(df) < 2:
        indicators_logger.warning(Fore.YELLOW + "DataFrame is empty or insufficient for Fibonacci pivot calculation." + Style.RESET_ALL)
        return resistance_levels, support_levels

    # Use the last complete candle for calculation
    last_candle = df.iloc[-1]
    high = Decimal(str(last_candle['high']))
    low = Decimal(str(last_candle['low']))
    close = Decimal(str(last_candle['close']))

    indicators_logger.debug(Fore.BLUE + f"Summoning Fibonacci inputs: High={high:.8f}, Low={low:.8f}, Close={close:.8f}" + Style.RESET_ALL)

    # Calculate Pivot Point (PP)
    pp = (high + low + close) / Decimal('3')

    # Calculate Range
    price_range = high - low

    # Calculate ATR for volatility adjustment
    atr = calculate_atr(df, atr_length).iloc[-1] if atr_length > 0 else Decimal('0')
    atr = Decimal(str(atr)) if pd.notna(atr) else Decimal('0')
    volatility_adjustment = atr * Decimal('0.5')  # Adjust levels by half the ATR
    indicators_logger.debug(Fore.CYAN + f"Pivot Point: {pp:.8f}, Range: {price_range:.8f}, ATR Adjustment: {volatility_adjustment:.8f}" + Style.RESET_ALL)

    # Calculate and store levels
    for i, ratio in enumerate(fib_ratios, 1):
        fib_ratio = Decimal(str(ratio))
        # Resistance level with volatility adjustment
        r_unrounded = pp + (price_range * fib_ratio) + volatility_adjustment
        r = r_unrounded.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        resistance_levels.append({'price': r, 'type': f'R{i}', 'ratio': float(fib_ratio)})

        # Support level with volatility adjustment
        s_unrounded = pp - (price_range * fib_ratio) - volatility_adjustment
        s = s_unrounded.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        support_levels.append({'price': s, 'type': f'S{i}', 'ratio': float(fib_ratio)})

        indicators_logger.debug(Fore.YELLOW + f"Level R{i}: {r:.2f}, S{i}: {s:.2f} (Ratio: {fib_ratio})" + Style.RESET_ALL)

    # Include Pivot Point in the output for reference
    resistance_levels.append({'price': pp.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), 'type': 'PP', 'ratio': 0.0})
    indicators_logger.info(Fore.GREEN + f"Fibonacci Pivot Points conjured: PP={pp:.2f}" + Style.RESET_ALL)
    return resistance_levels, support_levels

def calculate_stochrsi(df: pd.DataFrame, rsi_period: int = 14, stoch_k_period: int = 14, stoch_d_period: int = 3) -> pd.DataFrame:
    """
    Calculates the Stochastic RSI (StochRSI) for a given DataFrame using Decimal.
    """
    if 'close' not in df.columns:
        indicators_logger.error(Fore.RED + "DataFrame must contain a 'close' column for StochRSI calculation." + Style.RESET_ALL)
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

    indicators_logger.debug(Fore.CYAN + f"StochRSI calculated with rsi_period={rsi_period}, stoch_k_period={stoch_k_period}, stoch_d_period={stoch_d_period}." + Style.RESET_ALL)
    return df

def calculate_sma(df: pd.DataFrame, length: int) -> pd.Series:
    """
    Calculates the Simple Moving Average (SMA) for the 'close' prices.
    """
    if 'close' not in df.columns:
        indicators_logger.error(Fore.RED + "DataFrame must contain a 'close' column for SMA calculation." + Style.RESET_ALL)
        return pd.Series(dtype='object')
    
    # Ensure 'close' column is Decimal type
    close_prices = df['close'].apply(Decimal)
    sma = close_prices.rolling(window=length).mean()
    indicators_logger.debug(Fore.CYAN + f"SMA calculated with length={length}." + Style.RESET_ALL)
    return sma

def calculate_ehlers_fisher_transform(df: pd.DataFrame, length: int = 9, signal_length: int = 1) -> Tuple[pd.Series, pd.Series]:
    """
    Calculates the Ehlers Fisher Transform and its signal line.
    """
    if 'high' not in df.columns or 'low' not in df.columns:
        indicators_logger.error(Fore.RED + "DataFrame must contain 'high' and 'low' columns for Fisher Transform." + Style.RESET_ALL)
        return pd.Series(dtype='object'), pd.Series(dtype='object')

    high = df['high'].apply(Decimal)
    low = df['low'].apply(Decimal)

    # Calculate the median price
    median_price = (high + low) / Decimal('2')

    # Normalize the price to a range of -1 to +1
    min_val = median_price.rolling(window=length).min().apply(lambda x: Decimal(str(x)) if pd.notna(x) else Decimal('NaN'))
    max_val = median_price.rolling(window=length).max().apply(lambda x: Decimal(str(x)) if pd.notna(x) else Decimal('NaN'))

    # Avoid division by zero and handle NaN propagation
    range_val = max_val - min_val
    range_val = range_val.replace(Decimal('0'), Decimal('1e-38'))

    x = (median_price - min_val) / range_val
    x = x.apply(lambda val: Decimal('2') * (val - Decimal('0.5')) if not val.is_nan() else Decimal('NaN'))

    # Ensure x is within (-0.999, 0.999) to avoid issues with log
    x = x.apply(lambda val: Decimal('NaN') if val.is_nan() else (Decimal('0.999') if val >= Decimal('1') else (Decimal('-0.999') if val <= Decimal('-1') else val)))

    # Fisher Transform formula
    fisher_transform = x.apply(lambda val: Decimal('NaN') if val.is_nan() else Decimal('0.5') * Decimal(str(math.log((1 + float(val)) / (1 - float(val))))))
    
    # Calculate Fisher Signal
    fisher_signal = fisher_transform.rolling(window=signal_length).mean()

    indicators_logger.debug(Fore.CYAN + f"Fisher Transform calculated with length={length}, signal_length={signal_length}." + Style.RESET_ALL)
    return fisher_transform, fisher_signal

def calculate_ehlers_super_smoother(df: pd.DataFrame, length: int = 10) -> pd.Series:
    """
    Calculates the Ehlers 2-pole Super Smoother Filter.
    """
    if 'close' not in df.columns:
        indicators_logger.error(Fore.RED + "DataFrame must contain a 'close' column for Super Smoother." + Style.RESET_ALL)
        return pd.Series(dtype='object')

    close_prices = df['close'].apply(Decimal)

    # Convert length to float for math functions
    float_length = float(length)

    # Calculate coefficients
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
    
    indicators_logger.debug(Fore.CYAN + f"Super Smoother calculated with length={length}." + Style.RESET_ALL)
    return filtered_values

def find_pivots(df: pd.DataFrame, left: int, right: int, use_wicks: bool) -> Tuple[pd.Series, pd.Series]:
    """
    Identifies Pivot Highs and Lows based on lookback periods.
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        indicators_logger.error(Fore.RED + "DataFrame index must be a DatetimeIndex for pivot calculation." + Style.RESET_ALL)
        return pd.Series(dtype='bool'), pd.Series(dtype='bool')

    if 'high' not in df.columns or 'low' not in df.columns:
        indicators_logger.error(Fore.RED + "DataFrame must contain 'high' and 'low' columns for pivot identification." + Style.RESET_ALL)
        return pd.Series(dtype='bool'), pd.Series(dtype='bool')

    high_prices = df['high'].apply(Decimal)
    low_prices = df['low'].apply(Decimal)

    pivot_highs = pd.Series(False, index=df.index)
    pivot_lows = pd.Series(False, index=df.index)

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

    indicators_logger.debug(Fore.CYAN + f"Pivots identified with left={left}, right={right}, use_wicks={use_wicks}." + Style.RESET_ALL)
    return pivot_highs, pivot_lows

def handle_websocket_kline_data(df: pd.DataFrame, message: Dict[str, Any]) -> pd.DataFrame:
    """
    Processes a single kline data message from a WebSocket stream.
    """
    if not isinstance(message, dict) or 'data' not in message or not message['data']:
        indicators_logger.error(Fore.RED + f"Invalid kline WebSocket message received: {message}" + Style.RESET_ALL)
        return df

    kline_data = message['data'][0]

    # Extract and format the new kline data
    new_kline = {
        'timestamp': pd.to_datetime(int(kline_data['start']), unit='ms'),
        'open': Decimal(kline_data['open']),
        'high': Decimal(kline_data['high']),
        'low': Decimal(kline_data['low']),
        'close': Decimal(kline_data['close']),
        'volume': Decimal(kline_data['volume']),
    }
    
    # Set the timestamp as the index for the new kline
    new_kline_df = pd.DataFrame([new_kline]).set_index('timestamp')

    if df.empty:
        indicators_logger.info(Fore.GREEN + "DataFrame is empty, initializing with new kline data." + Style.RESET_ALL)
        return new_kline_df

    # If the new kline's timestamp matches the last one in the DataFrame, update it
    if new_kline_df.index[0] == df.index[-1]:
        for col in new_kline_df.columns:
            if col in df.columns:
                df.loc[new_kline_df.index[0], col] = new_kline_df.loc[new_kline_df.index[0], col]
        indicators_logger.debug(Fore.CYAN + f"Updated last kline at {new_kline_df.index[0]}" + Style.RESET_ALL)
    # Otherwise, append it as a new row
    else:
        df = pd.concat([df, new_kline_df])
        indicators_logger.debug(Fore.CYAN + f"Appended new kline at {new_kline_df.index[0]}" + Style.RESET_ALL)

    return df

def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """
    Calculates the Volume Weighted Average Price (VWAP).
    """
    if not all(col in df.columns for col in ['high', 'low', 'close', 'volume']):
        indicators_logger.error("DataFrame must contain 'high', 'low', 'close', and 'volume' columns for VWAP.")
        return pd.Series(dtype='object')

    typical_price = (df['high'].apply(Decimal) + df['low'].apply(Decimal) + df['close'].apply(Decimal)) / Decimal('3')
    volume = df['volume'].apply(Decimal)
    
    # Calculate cumulative typical price * volume and cumulative volume
    cumulative_tpv = (typical_price * volume).cumsum()
    cumulative_volume = volume.cumsum()
    
    # Avoid division by zero
    vwap = cumulative_tpv / cumulative_volume.replace(Decimal('0'), Decimal('1e-38'))
    
    indicators_logger.debug("VWAP calculated.")
    return vwap

def calculate_order_book_imbalance(order_book: Dict[str, List[List[str]]]) -> Tuple[Decimal, Decimal]:
    """
    Calculates the order book imbalance from the raw order book data.
    Returns the imbalance ratio and the total volume.
    """
    bids = order_book.get('b', [])
    asks = order_book.get('a', [])

    if not bids or not asks:
        return Decimal('0'), Decimal('0')

    bid_volume = sum(Decimal(price) * Decimal(qty) for price, qty in bids)
    ask_volume = sum(Decimal(price) * Decimal(qty) for price, qty in asks)

    total_volume = bid_volume + ask_volume

    if total_volume == 0:
        return Decimal('0'), total_volume

    imbalance = (bid_volume - ask_volume) / total_volume
    indicators_logger.debug(f"Order book imbalance calculated: {imbalance:.4f}")
    return imbalance, total_volume

def calculate_ehlers_fisher_strategy(df: pd.DataFrame, length: int = 10) -> pd.DataFrame:
    """Calculates the Ehlers Fisher Transform as per the strategy's logic."""
    df['min_low_ehlers'] = df['low'].rolling(window=length).min()
    df['max_high_ehlers'] = df['high'].rolling(window=length).max()

    ehlers_value1 = [Decimal(0.0)] * len(df)
    ehlers_fisher = [Decimal(0.0)] * len(df)
    
    prev_val1 = Decimal(0.0)

    for i in range(len(df)):
        if i >= length - 1:
            min_low_val = df['min_low_ehlers'].iloc[i]
            max_high_val = df['max_high_ehlers'].iloc[i]
            close_val = df['close'].iloc[i]

            if pd.isna(min_low_val) or pd.isna(max_high_val) or pd.isna(close_val):
                continue

            range_val = max_high_val - min_low_val
            raw_norm_price = (close_val - min_low_val) / range_val if range_val > 0 else Decimal('0.5')
            
            current_val1 = Decimal('0.33') * (Decimal('2') * raw_norm_price - Decimal('1')) + Decimal('0.67') * prev_val1
            current_val1 = max(Decimal('-0.999'), min(Decimal('0.999'), current_val1))
            
            ehlers_value1[i] = current_val1
            prev_val1 = current_val1

            fisher_val = Decimal('0.5') * Decimal(math.log((1 + float(current_val1)) / (1 - float(current_val1))))
            ehlers_fisher[i] = fisher_val
    
    df['ehlers_fisher'] = ehlers_fisher
    df['ehlers_signal'] = df['ehlers_fisher'].shift(1)
    df.drop(columns=['min_low_ehlers', 'max_high_ehlers'], inplace=True)
    return df

def calculate_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    """Calculates Supertrend indicator."""
    df['tr1'] = df['high'] - df['low']
    df['tr2'] = abs(df['high'] - df['close'].shift(1))
    df['tr3'] = abs(df['low'] - df['close'].shift(1))
    df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
    df['atr'] = df['tr'].ewm(span=period, adjust=False).mean()
    df['hl2'] = (df['high'] + df['low']) / 2

    final_upper_band = [Decimal(0.0)] * len(df)
    final_lower_band = [Decimal(0.0)] * len(df)
    supertrend_values = [Decimal(0.0)] * len(df)
    direction = [1] * len(df)

    for i in range(1, len(df)):
        if pd.isna(df['atr'].iloc[i]):
            continue

        curr_upper_basic = df['hl2'].iloc[i] + Decimal(multiplier) * df['atr'].iloc[i]
        curr_lower_basic = df['hl2'].iloc[i] - Decimal(multiplier) * df['atr'].iloc[i]

        prev_final_upper = final_upper_band[i-1] if final_upper_band[i-1] != 0 else curr_upper_basic
        prev_final_lower = final_lower_band[i-1] if final_lower_band[i-1] != 0 else curr_lower_basic
        prev_direction = direction[i-1]

        current_close = df['close'].iloc[i]
        prev_close = df['close'].iloc[i-1]

        if curr_upper_basic < prev_final_upper or prev_close > prev_final_upper:
            final_upper_band[i] = curr_upper_basic
        else:
            final_upper_band[i] = prev_final_upper

        if curr_lower_basic > prev_final_lower or prev_close < prev_final_lower:
            final_lower_band[i] = curr_lower_basic
        else:
            final_lower_band[i] = prev_final_lower

        if prev_direction == 1:
            if current_close < final_upper_band[i]:
                direction[i] = -1
                supertrend_values[i] = final_upper_band[i]
            else:
                direction[i] = 1
                supertrend_values[i] = final_lower_band[i]
        else:
            if current_close > final_lower_band[i]:
                direction[i] = 1
                supertrend_values[i] = final_lower_band[i]
            else:
                direction[i] = -1
                supertrend_values[i] = final_upper_band[i]

    df['supertrend'] = supertrend_values
    df['supertrend_direction'] = direction
    df.drop(columns=['tr1', 'tr2', 'tr3', 'tr', 'atr', 'hl2'], inplace=True, errors='ignore')
    return df
