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
    
    # Using EMA for ATR calculation for smoother, more stable results
    atr = tr.ewm(alpha=1/length, adjust=False).mean().fillna(Decimal('0')).apply(Decimal)
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
        df_copy = df.copy()
        df_copy['rsi'] = pd.Series([Decimal('NaN')] * len(df_copy), index=df_copy.index, dtype=object)
        df_copy['stoch_rsi'] = pd.Series([Decimal('NaN')] * len(df_copy), index=df_copy.index, dtype=object)
        df_copy['stoch_k'] = pd.Series([Decimal('NaN')] * len(df_copy), index=df_copy.index, dtype=object)
        df_copy['stoch_d'] = pd.Series([Decimal('NaN')] * len(df_copy), index=df_copy.index, dtype=object)
        return df_copy

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
    sma = close_prices.rolling(window=length).mean().apply(Decimal)
    indicators_logger.debug(Fore.CYAN + f"SMA calculated with length={length}." + Style.RESET_ALL)
    return sma

def calculate_ehlers_fisher_transform(df: pd.DataFrame, length: int = 9, signal_length: int = 1) -> Tuple[pd.Series, pd.Series]:
    """
    Calculates the Ehlers Fisher Transform and its signal line using Decimal precision.
    """
    if 'high' not in df.columns or 'low' not in df.columns:
        indicators_logger.error(Fore.RED + "DataFrame must contain 'high' and 'low' columns for Fisher Transform." + Style.RESET_ALL)
        return pd.Series(dtype='object'), pd.Series(dtype='object')

    high = df['high'].apply(lambda x: Decimal(str(x)))
    low = df['low'].apply(lambda x: Decimal(str(x)))

    # Calculate the median price
    median_price = (high + low) / Decimal('2')

    # Normalize the price to a range of -1 to +1
    min_val = median_price.rolling(window=length).min().apply(Decimal)
    max_val = median_price.rolling(window=length).max().apply(Decimal)

    # Avoid division by zero and handle NaN propagation
    range_val = max_val - min_val
    range_val = range_val.replace(Decimal('0'), Decimal('1e-38'))

    x = (median_price - min_val) / range_val
    x = x.apply(lambda val: Decimal('2') * (val - Decimal('0.5')) if pd.notna(val) else Decimal('NaN'))

    # Ensure x is within (-1, 1) to avoid issues with ln()
    x = x.apply(lambda val: Decimal('NaN') if pd.isna(val) else (Decimal('0.999999999999999999999999999') if val >= Decimal('1') else (Decimal('-0.999999999999999999999999999') if val <= Decimal('-1') else val)))

    # Fisher Transform formula using Decimal's ln()
    fisher_transform = x.apply(lambda val: Decimal('NaN') if pd.isna(val) else Decimal('0.5') * ((Decimal('1') + val) / (Decimal('1') - val)).ln())
    
    # Calculate Fisher Signal
    fisher_signal = fisher_transform.rolling(window=signal_length).mean().apply(Decimal)

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

    filtered_values = pd.Series(index=df.index, dtype=object)
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
    Processes one or more kline data messages from a WebSocket stream, ensuring robustness.
    """
    if not isinstance(message, dict) or 'data' not in message or not isinstance(message['data'], list):
        indicators_logger.error(Fore.RED + f"Invalid or empty kline WebSocket message received: {message}" + Style.RESET_ALL)
        return df

    # Ensure the DataFrame index is a timezone-aware DatetimeIndex before processing
    if not df.empty and not isinstance(df.index, pd.DatetimeIndex):
        indicators_logger.error(Fore.RED + "DataFrame index must be a DatetimeIndex for kline handling." + Style.RESET_ALL)
        return df
    if not df.empty and df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    elif not df.empty:
        df.index = df.index.tz_convert('UTC')

    all_new_klines = []
    for kline_data in message['data']:
        ts_key = 'timestamp' if 'timestamp' in kline_data else 'start'
        if ts_key not in kline_data:
            indicators_logger.warning(f"Kline data missing timestamp key: {kline_data}")
            continue

        try:
            new_kline = {
                'timestamp': pd.to_datetime(int(kline_data[ts_key]), unit='ms', utc=True),
                'open': Decimal(kline_data['open']),
                'high': Decimal(kline_data['high']),
                'low': Decimal(kline_data['low']),
                'close': Decimal(kline_data['close']),
                'volume': Decimal(kline_data['volume']),
            }
            all_new_klines.append(new_kline)
        except (ValueError, TypeError) as e:
            indicators_logger.error(f"Error parsing kline data {kline_data}: {e}")
            continue

    if not all_new_klines:
        return df

    new_klines_df = pd.DataFrame(all_new_klines).set_index('timestamp')

    # Combine the existing and new dataframes
    # Using combine_first to update existing rows and append new ones
    combined_df = new_klines_df.combine_first(df)
    
    # Sort the index to ensure chronological order after combining
    combined_df.sort_index(inplace=True)
    
    indicators_logger.debug(Fore.CYAN + f"Processed {len(all_new_klines)} kline updates." + Style.RESET_ALL)
    return combined_df

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
    """
    Calculates the Ehlers Fisher Transform as per the strategy's logic, ensuring Decimal precision.
    """
    # Ensure all input columns are of type Decimal
    required_cols = ['high', 'low', 'close']
    for col in required_cols:
        if col not in df.columns:
            indicators_logger.error(Fore.RED + f"DataFrame missing required column: '{col}' for Ehlers Fisher calculation." + Style.RESET_ALL)
            # Return a copy of the original DataFrame with empty ehlers_fisher and ehlers_signal columns
            df_copy = df.copy()
            df_copy['ehlers_fisher'] = pd.Series([Decimal('NaN')] * len(df_copy), index=df_copy.index, dtype=object)
            df_copy['ehlers_signal'] = pd.Series([Decimal('NaN')] * len(df_copy), index=df_copy.index, dtype=object)
            return df_copy
        df[col] = df[col].apply(lambda x: Decimal(str(x)))

    df['min_low_ehlers'] = df['low'].rolling(window=length).min()
    df['max_high_ehlers'] = df['high'].rolling(window=length).max()

    ehlers_value1 = [Decimal("0.0")] * len(df)
    ehlers_fisher = [Decimal("0.0")] * len(df)
    
    prev_val1 = Decimal("0.0")

    for i in range(len(df)):
        if i >= length - 1:
            min_low_val = df['min_low_ehlers'].iloc[i]
            max_high_val = df['max_high_ehlers'].iloc[i]
            close_val = df['close'].iloc[i]  # Already a Decimal

            if pd.isna(min_low_val) or pd.isna(max_high_val) or pd.isna(close_val):
                continue

            # Ensure rolling values are also Decimal
            min_low_val = Decimal(str(min_low_val))
            max_high_val = Decimal(str(max_high_val))

            range_val = max_high_val - min_low_val
            if range_val > Decimal("0"):
                raw_norm_price = (close_val - min_low_val) / range_val
            else:
                raw_norm_price = Decimal("0.5")
            
            current_val1 = Decimal('0.33') * (Decimal('2') * raw_norm_price - Decimal('1')) + Decimal('0.67') * prev_val1
            
            # Clamp value to avoid math domain errors with ln()
            if current_val1 >= Decimal("1"):
                current_val1 = Decimal("0.999999999999999999999999999")
            elif current_val1 <= Decimal("-1"):
                current_val1 = Decimal("-0.999999999999999999999999999")

            ehlers_value1[i] = current_val1
            prev_val1 = current_val1

            # Use Decimal's ln() for the Fisher Transform
            fisher_val = Decimal("0.5") * ((Decimal("1") + current_val1) / (Decimal("1") - current_val1)).ln()
            ehlers_fisher[i] = fisher_val
    
    df['ehlers_fisher'] = ehlers_fisher
    df['ehlers_signal'] = pd.Series(ehlers_fisher).shift(1).fillna(Decimal("0.0")).values
    df.drop(columns=['min_low_ehlers', 'max_high_ehlers'], inplace=True)
    
    indicators_logger.debug(Fore.CYAN + f"Ehlers Fisher Strategy calculated with length={length}." + Style.RESET_ALL)
    return df

def calculate_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    """
    Calculates Supertrend indicator.
    """
    required_cols = ['high', 'low', 'close']
    for col in required_cols:
        if col not in df.columns:
            indicators_logger.error(Fore.RED + f"DataFrame missing required column: '{col}' for Supertrend calculation." + Style.RESET_ALL)
            df_copy = df.copy()
            df_copy['supertrend'] = pd.Series([Decimal('NaN')] * len(df_copy), index=df_copy.index, dtype=object)
            df_copy['supertrend_direction'] = pd.Series([Decimal('NaN')] * len(df_copy), index=df_copy.index, dtype=object)
            return df_copy

    df['tr1'] = df['high'].apply(Decimal) - df['low'].apply(Decimal)
    df['tr2'] = (df['high'].apply(Decimal) - df['close'].shift(1).apply(Decimal)).abs()
    df['tr3'] = (df['low'].apply(Decimal) - df['close'].shift(1).apply(Decimal)).abs()
    df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1).apply(Decimal)
    df['atr'] = df['tr'].ewm(span=period, adjust=False).mean().apply(Decimal)
    df['hl2'] = ((df['high'].apply(Decimal) + df['low'].apply(Decimal)) / Decimal('2')).apply(Decimal)

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
    df.drop(columns=['tr1', 'tr2', 'tr3', 'tr', 'hl2'], inplace=True, errors='ignore')
    return df

# --- Self-contained demonstration block ---
if __name__ == "__main__":
    print(Fore.CYAN + "\n--- Indicators Demonstration ---" + Style.RESET_ALL)
    
    # Create a sample DataFrame for demonstration
    data = {
        'timestamp': pd.to_datetime([
            '2023-01-01 00:00:00', '2023-01-01 00:01:00', '2023-01-01 00:02:00', 
            '2023-01-01 00:03:00', '2023-01-01 00:04:00', '2023-01-01 00:05:00',
            '2023-01-01 00:06:00', '2023-01-01 00:07:00', '2023-01-01 00:08:00',
            '2023-01-01 00:09:00', '2023-01-01 00:10:00', '2023-01-01 00:11:00',
            '2023-01-01 00:12:00', '2023-01-01 00:13:00', '2023-01-01 00:14:00',
            '2023-01-01 00:15:00', '2023-01-01 00:16:00', '2023-01-01 00:17:00',
            '2023-01-01 00:18:00', '2023-01-01 00:19:00', '2023-01-01 00:20:00'
        ]).tz_localize('UTC'),
        'open': [Decimal(str(x)) for x in [100, 101, 100.5, 102, 101.5, 103, 102.5, 104, 103.5, 105, 104.5, 106, 105.5, 107, 106.5, 108, 107.5, 109, 108.5, 110, 109.5]],
        'high': [Decimal(str(x)) for x in [101, 101.5, 101, 102.5, 102, 103.5, 103, 104.5, 104, 105.5, 105, 106.5, 106, 107.5, 107, 108.5, 108, 109.5, 109, 110.5, 110]],
        'low': [Decimal(str(x)) for x in [99, 100, 99.5, 101, 100.5, 102, 101.5, 103, 102.5, 104, 103.5, 105, 104.5, 106, 105.5, 107, 106.5, 108, 107.5, 109, 108.5]],
        'close': [Decimal(str(x)) for x in [100.5, 100.8, 100.2, 101.8, 101.2, 102.8, 102.2, 103.8, 103.2, 104.8, 104.2, 105.8, 105.2, 106.8, 106.2, 107.8, 107.2, 108.8, 108.2, 109.8, 109.2]],
        'volume': [Decimal(str(x)) for x in [1000, 1100, 1050, 1200, 1150, 1300, 1250, 1400, 1350, 1500, 1450, 1600, 1550, 1700, 1650, 1800, 1750, 1900, 1850, 2000, 1950]]
    }
    df = pd.DataFrame(data).set_index('timestamp')

    print(Fore.BLUE + "\nOriginal DataFrame (last 5 rows):" + Style.RESET_ALL)
    print(df.tail())

    # Calculate ATR
    df['atr'] = calculate_atr(df)
    print(Fore.BLUE + "\nATR (last 5 values):" + Style.RESET_ALL)
    print(df['atr'].tail())

    # Calculate StochRSI
    df = calculate_stochrsi(df)
    print(Fore.BLUE + "\nStochRSI (last 5 values):" + Style.RESET_ALL)
    print(df[['stoch_rsi', 'stoch_k', 'stoch_d']].tail())

    # Calculate SMA
    df['sma_10'] = calculate_sma(df, length=10)
    print(Fore.BLUE + "\nSMA (last 5 values):" + Style.RESET_ALL)
    print(df['sma_10'].tail())

    # Calculate Ehlers Fisher Transform
    fisher, signal = calculate_ehlers_fisher_transform(df)
    df['ehlers_fisher'] = fisher
    df['ehlers_signal'] = signal
    print(Fore.BLUE + "\nEhlers Fisher Transform (last 5 values):" + Style.RESET_ALL)
    print(df[['ehlers_fisher', 'ehlers_signal']].tail())

    # Calculate Ehlers Super Smoother
    df['ehlers_supersmoother'] = calculate_ehlers_super_smoother(df)
    print(Fore.BLUE + "\nEhlers Super Smoother (last 5 values):" + Style.RESET_ALL)
    print(df['ehlers_supersmoother'].tail())

    # Calculate Supertrend
    df = calculate_supertrend(df)
    print(Fore.BLUE + "\nSupertrend (last 5 values):" + Style.RESET_ALL)
    print(df[['supertrend', 'supertrend_direction']].tail())

    print(Fore.CYAN + "\n--- Indicators Demonstration Complete ---" + Style.RESET_ALL)