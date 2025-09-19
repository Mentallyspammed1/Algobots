import math  # For rounding
import os
import time

import pandas as pd
import ta  # Technical Analysis library
from pybit.unified_trading import HTTP

# --- Configuration ---
# Ensure these are set as environment variables for security
# Example: export BYBIT_API_KEY="YOUR_API_KEY"
# Example: export BYBIT_API_SECRET="YOUR_API_SECRET"
API_KEY = os.environ.get("BYBIT_API_KEY")
API_SECRET = os.environ.get("BYBIT_API_SECRET")
TESTNET = True  # Set to False for live trading

SYMBOL = "BCHUSDT"  # Trading pair (e.g., BTCUSDT, ETHUSDT)
CATEGORY = "linear" # For USDT perpetuals (futures). Use "spot" for spot trading.

# Strategy Parameters
RISK_PER_TRADE_PERCENT = 0.5  # 0.5% of capital per trade

# Indicator Periods
SUPER_TREND_PERIOD = 8
SUPER_TREND_MULTIPLIER = 1.2
EMA_SHORT_PERIOD = 8
EMA_LONG_PERIOD = 22
VOLUME_MA_PERIOD = 10
RSI_PERIOD = 12
ATR_PERIOD = 14

# Entry Filters (from user suggestions)
VOLUME_SPIKE_MULTIPLIER = 1.0 # Suggestion 1: Current volume > 1.5 * Volume MA(20)
RSI_CONFIRMATION_LEVEL = 50 # Suggestion 2: RSI > 50 and rising for long, < 50 and falling for short

# Exit Strategy Parameters (from user suggestions)
STOP_LOSS_ATR_MULTIPLIER = 0.75 # Suggestion 12: Optimize ATR Multipliers (SL)
TAKE_PROFIT_ATR_MULTIPLIER = 1.0 # Suggestion 12: Optimize ATR Multipliers (TP)
PARTIAL_PROFIT_PERCENT = 0.5 # Suggestion 10: Close 50% of position
PARTIAL_PROFIT_ATR_MULTIPLIER = 1.0 # Target for partial profit (e.g., 1.0 ATR)

MAX_TRADE_DURATION_BARS = 15 # Original strategy: Time-based exit
BREAK_EVEN_PROFIT_ATR = 0.5 # Suggestion 11: Move SL to BE after 0.5 ATR profit
TRAILING_STOP_ACTIVATION_BARS = 10 # Suggestion 13: Activate trailing stop after X bars if in profit
TRAILING_STOP_ATR_MULTIPLIER = 0.5 # For trailing stop after partial profit or activation

# Timeframes
TF_1M = "1"
TF_15M = "15"

# --- Pybit Session ---
if TESTNET:
    session = HTTP(testnet=True, api_key=API_KEY, api_secret=API_SECRET)
else:
    session = HTTP(testnet=False, api_key=API_KEY, api_secret=API_SECRET)

# --- Global Trade State (In-memory, not persistent across restarts) ---
# WARNING: If the bot restarts, it will lose track of the order_id for open positions
# and thus will not be able to dynamically amend SL/TP for those positions.
# For a production bot, this state should be persisted to a file or database.
current_trade_state = {
    'position': None,            # Stores details of the open position from get_open_positions
    'entry_bar_time': None,      # Timestamp of the candle when the trade was entered
    'entry_price': None,         # Price at which the trade was entered
    'initial_sl': None,          # Initial stop loss price set at entry
    'partial_profit_taken': False, # Flag to track if partial profit has been taken
    'order_id': None             # The orderId of the initial market order, crucial for amending SL/TP
}

# --- Logging ---
def log_message(message, level="INFO"):
    """Logs messages to console and a file."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [{level}] {message}"
    print(log_entry)
    with open("supertrendbot.log", "a") as f:
        f.write(log_entry + "\n")

# --- Helper Functions ---
def get_klines(symbol, interval, limit=200):
    """Fetches kline data from Bybit."""
    try:
        response = session.get_kline(
            category=CATEGORY,
            symbol=symbol,
            interval=interval,
            limit=limit
        )
        if response and response['retCode'] == 0:
            data = response['result']['list']
            df = pd.DataFrame(data, columns=[
                'start_time', 'open', 'high', 'low', 'close', 'volume', 'turnover'
            ])
            # Convert to numeric types
            for col in ['start_time', 'open', 'high', 'low', 'close', 'volume', 'turnover']:
                df[col] = pd.to_numeric(df[col])
            df = df.set_index('start_time')
            return df.sort_index() # Ensure ascending order by time
        log_message(f"Error fetching klines for {symbol}, {interval}: {response}", "ERROR")
        return None
    except Exception as e:
        log_message(f"Exception fetching klines: {e}", "ERROR")
        return None

def supertrend(high, low, close, period=7, atr_multiplier=3):
    """
    Calculates the Supertrend indicator.
    """
    high = high.astype(float)
    low = low.astype(float)
    close = close.astype(float)

    # Calculate ATR
    atr = ta.volatility.average_true_range(high, low, close, window=period)

    # Calculate basic upper and lower bands
    basic_upper_band = (high + low) / 2 + atr_multiplier * atr
    basic_lower_band = (high + low) / 2 - atr_multiplier * atr

    # Final upper and lower bands
    final_upper_band = pd.Series(index=high.index, dtype=float)
    final_lower_band = pd.Series(index=high.index, dtype=float)

    for i in range(len(high)):
        if i == 0:
            final_upper_band.iloc[i] = 0
            final_lower_band.iloc[i] = 0
        else:
            # Final Upper Band
            if basic_upper_band.iloc[i] < final_upper_band.iloc[i-1] or close.iloc[i-1] > final_upper_band.iloc[i-1]:
                final_upper_band.iloc[i] = basic_upper_band.iloc[i]
            else:
                final_upper_band.iloc[i] = final_upper_band.iloc[i-1]

            # Final Lower Band
            if basic_lower_band.iloc[i] > final_lower_band.iloc[i-1] or close.iloc[i-1] < final_lower_band.iloc[i-1]:
                final_lower_band.iloc[i] = basic_lower_band.iloc[i]
            else:
                final_lower_band.iloc[i] = final_lower_band.iloc[i-1]

    # Supertrend
    supertrend_series = pd.Series(index=high.index, dtype=float)
    supertrend_direction = pd.Series(index=high.index, dtype=int)

    for i in range(len(high)):
        if i == 0:
            supertrend_series.iloc[i] = 0
            supertrend_direction.iloc[i] = 0
        elif supertrend_series.iloc[i-1] == final_upper_band.iloc[i-1] and close.iloc[i] <= final_upper_band.iloc[i]:
            supertrend_series.iloc[i] = final_upper_band.iloc[i]
            supertrend_direction.iloc[i] = 0 # Downtrend
        elif supertrend_series.iloc[i-1] == final_upper_band.iloc[i-1] and close.iloc[i] > final_upper_band.iloc[i]:
            supertrend_series.iloc[i] = final_lower_band.iloc[i]
            supertrend_direction.iloc[i] = 1 # Uptrend
        elif supertrend_series.iloc[i-1] == final_lower_band.iloc[i-1] and close.iloc[i] >= final_lower_band.iloc[i]:
            supertrend_series.iloc[i] = final_lower_band.iloc[i]
            supertrend_direction.iloc[i] = 1 # Uptrend
        elif supertrend_series.iloc[i-1] == final_lower_band.iloc[i-1] and close.iloc[i] < final_lower_band.iloc[i]:
            supertrend_series.iloc[i] = final_upper_band.iloc[i]
            supertrend_direction.iloc[i] = 0 # Downtrend

    return supertrend_series, supertrend_direction

def calculate_indicators(df):
    """Calculates technical indicators for a given DataFrame."""
    if df is None or df.empty:
        return None

    # EMAs
    df['ema_short'] = ta.trend.ema_indicator(df['close'], window=EMA_SHORT_PERIOD)
    df['ema_long'] = ta.trend.ema_indicator(df['close'], window=EMA_LONG_PERIOD)

    # Supertrend (returns line and direction)
    df['supertrend_line'], df['supertrend_direction'] = supertrend(
        df['high'], df['low'], df['close'],
        period=SUPER_TREND_PERIOD,
        atr_multiplier=SUPER_TREND_MULTIPLIER
    )
    # supertrend_direction: 1 for uptrend, 0 for downtrend.

    # Volume MA
    df['volume_ma'] = df['volume'].rolling(window=VOLUME_MA_PERIOD).mean()

    # RSI
    df['rsi'] = ta.momentum.rsi(df['close'], window=RSI_PERIOD)

    # ATR
    df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=ATR_PERIOD)

    # --- Custom Indicators ---
    # Example 1: Price Rate of Change (ROC)
    # ROC measures the percentage change in price between the current price and a price 'n' periods ago.
    # It can be used to identify momentum.
    ROC_PERIOD = 12
    df['roc'] = ((df['close'] - df['close'].shift(ROC_PERIOD)) / df['close'].shift(ROC_PERIOD)) * 100

    # Example 2: Chaikin Money Flow (CMF)
    # CMF measures the amount of Money Flow Volume over a specific period.
    # Money Flow Volume is a measure of the buying and selling pressure.
    CMF_PERIOD = 20
    mf_multiplier = ((df['close'] - df['low']) - (df['high'] - df['close'])) / (df['high'] - df['low'])
    mf_volume = mf_multiplier * df['volume']
    df['cmf'] = mf_volume.rolling(window=CMF_PERIOD).sum() / df['volume'].rolling(window=CMF_PERIOD).sum()

    # Example 3: Keltner Channel
    # Keltner Channels are volatility-based envelopes that are plotted on either side of an exponential moving average.
    # They are similar to Bollinger Bands but use ATR instead of standard deviation.
    KC_EMA_PERIOD = 20
    KC_ATR_MULTIPLIER = 2.0
    df['kc_ema'] = ta.trend.ema_indicator(df['close'], window=KC_EMA_PERIOD)
    df['kc_upper'] = df['kc_ema'] + (df['atr'] * KC_ATR_MULTIPLIER)
    df['kc_lower'] = df['kc_ema'] - (df['atr'] * KC_ATR_MULTIPLIER)

    # Example 4: Stochastic RSI (StochRSI)
    # StochRSI is an oscillator that measures the level of RSI relative to its high-low range over a set period.
    # It's a "momentum of momentum" indicator.
    STOCHRSI_PERIOD = 14
    STOCHRSI_SMA_PERIOD = 3 # For %K and %D smoothing
    df['stochrsi'] = ta.momentum.stochrsi(df['close'], window=STOCHRSI_PERIOD, fillna=False)
    df['stochrsi_k'] = ta.momentum.stochrsi_k(df['close'], window=STOCHRSI_PERIOD, smooth1=STOCHRSI_SMA_PERIOD, fillna=False)
    df['stochrsi_d'] = ta.momentum.stochrsi_d(df['close'], window=STOCHRSI_PERIOD, smooth1=STOCHRSI_SMA_PERIOD, smooth2=STOCHRSI_SMA_PERIOD, fillna=False)

    return df

def get_account_balance(coin="USDT"):
    """Retrieves the available balance for a specified coin."""
    try:
        response = session.get_wallet_balance(accountType="UNIFIED", coin=coin)
        if response and response['retCode'] == 0:
            for item in response['result']['list']:
                for c in item['coin']:
                    if c['coin'] == coin:
                        # Use availableToWithdraw for capital available for trading
                        return float(c['availableToWithdraw'])
            return 0.0
        log_message(f"Error getting account balance: {response}", "ERROR")
        return 0.0
    except Exception as e:
        log_message(f"Exception getting account balance: {e}", "ERROR")
        return 0.0

def get_current_price(symbol):
    """Fetches the last traded price for a symbol."""
    try:
        response = session.get_tickers(category=CATEGORY, symbol=symbol)
        if response and response['retCode'] == 0:
            return float(response['result']['list'][0]['lastPrice'])
        log_message(f"Error getting current price for {symbol}: {response}", "ERROR")
        return None
    except Exception as e:
        log_message(f"Exception getting current price: {e}", "ERROR")
        return None

def place_order(symbol, side, qty, order_type="Market", stop_loss=None, take_profit=None):
    """Places a market order with optional Stop Loss and Take Profit."""
    try:
        params = {
            "category": CATEGORY,
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": str(qty),
            "isLeverage": 0, # For spot, or use default leverage for futures.
                             # For linear, leverage is often managed separately.
        }
        if stop_loss is not None:
            params["stopLoss"] = str(round(stop_loss, 2)) # Round SL to 2 decimal places
        if take_profit is not None:
            params["takeProfit"] = str(round(take_profit, 2)) # Round TP to 2 decimal places

        response = session.place_order(**params)

        if response and response['retCode'] == 0:
            log_message(f"Order placed successfully: {response['result']}", "INFO")
            return response['result']['orderId']
        log_message(f"Error placing order: {response}", "ERROR")
        return None
    except Exception as e:
        log_message(f"Exception placing order: {e}", "ERROR")
        return None

def close_position(symbol, side, qty):
    """Closes a portion or all of an open position by placing an opposite market order."""
    opposite_side = "Sell" if side == "Buy" else "Buy"
    log_message(f"Closing {qty:.3f} units of {symbol} with a {opposite_side} market order.", "INFO")
    return place_order(symbol, opposite_side, qty, order_type="Market")

def get_open_positions(symbol):
    """Retrieves details of an open position for a given symbol."""
    try:
        response = session.get_positions(category=CATEGORY, symbol=symbol)
        if response and response['retCode'] == 0:
            positions = response['result']['list']
            if positions:
                # Assuming only one position per symbol for simplicity
                pos = positions[0]
                if float(pos['size']) > 0:
                    return {
                        'symbol': pos['symbol'],
                        'side': pos['side'],
                        'size': float(pos['size']),
                        'entry_price': float(pos['avgPrice']),
                        'stop_loss': float(pos['stopLoss']) if pos.get('stopLoss') else None,
                        'take_profit': float(pos['takeProfit']) if pos.get('takeProfit') else None,
                        'position_value': float(pos['positionValue'])
                    }
            return None
        log_message(f"Error getting open positions: {response}", "ERROR")
        return None
    except Exception as e:
        log_message(f"Exception getting open positions: {e}", "ERROR")
        return None

def amend_stop_loss_take_profit(symbol, order_id, stop_loss=None, take_profit=None):
    """Amends the Stop Loss or Take Profit of an existing order."""
    if not order_id:
        log_message("Cannot amend SL/TP: order_id is missing.", "WARNING")
        return False
    try:
        params = {
            "category": CATEGORY,
            "symbol": symbol,
            "orderId": order_id, # Use orderId of the main position order
        }
        if stop_loss is not None:
            params["stopLoss"] = str(round(stop_loss, 2))
        if take_profit is not None:
            params["takeProfit"] = str(round(take_profit, 2))

        response = session.amend_order(**params)

        if response and response['retCode'] == 0:
            log_message(f"SL/TP amended successfully for order {order_id}: {response['result']}", "INFO")
            return True
        log_message(f"Error amending SL/TP for order {order_id}: {response}", "ERROR")
        return False
    except Exception as e:
        log_message(f"Exception amending SL/TP: {e}", "ERROR")
        return False

# --- Main Trading Logic ---
def run_bot():
    """Main function to run the trading bot."""
    global current_trade_state # Declare global to modify the dictionary

    log_message("Starting Supertrend Bot...")

    while True:
        log_message("Fetching market data...")
        df_1m = get_klines(SYMBOL, TF_1M, limit=200)
        df_15m = get_klines(SYMBOL, TF_15M, limit=200)

        if df_1m is None or df_15m is None or df_1m.empty or df_15m.empty:
            log_message("Failed to get klines or klines are empty. Retrying in 60 seconds.", "WARNING")
            time.sleep(60)
            continue

        df_1m = calculate_indicators(df_1m)
        df_15m = calculate_indicators(df_15m)

        # Ensure enough data for indicators
        # +2 for current and previous candle, plus the window size
        required_1m_data = max(EMA_LONG_PERIOD, VOLUME_MA_PERIOD, RSI_PERIOD, ATR_PERIOD, 20) + 2 # 20 for CMF, KC
        required_15m_data = max(EMA_LONG_PERIOD, SUPER_TREND_PERIOD) + 2

        if df_1m is None or df_15m is None or \
           len(df_1m) < required_1m_data or \
           len(df_15m) < required_15m_data:
            log_message(f"Not enough data to calculate all indicators. Need at least {required_1m_data} (1m) and {required_15m_data} (15m) candles. Retrying in 60 seconds.", "WARNING")
            time.sleep(60)
            continue

        # Get latest data
        last_1m_candle = df_1m.iloc[-1]
        prev_1m_candle = df_1m.iloc[-2]
        last_15m_candle = df_15m.iloc[-1]
        prev_15m_candle = df_15m.iloc[-2]

        current_price = get_current_price(SYMBOL)
        if current_price is None:
            log_message("Failed to get current price. Retrying in 60 seconds.", "WARNING")
            time.sleep(60)
            continue

        log_message(f"Current Price: {current_price:.2f}")

        # Check for open position from exchange
        exchange_position = get_open_positions(SYMBOL)

        # --- Sync internal state with exchange state ---
        if exchange_position and not current_trade_state['position']:
            # Bot restarted or just detected a position not tracked internally
            log_message("Detected an open position not tracked internally. Attempting to sync.", "WARNING")
            current_trade_state['position'] = exchange_position
            current_trade_state['entry_price'] = exchange_position['entry_price']
            current_trade_state['initial_sl'] = exchange_position['stop_loss']
            current_trade_state['partial_profit_taken'] = False # Assume not taken if untracked
            current_trade_state['order_id'] = None # Cannot get order_id from get_open_positions, so dynamic SL/TP won't work for this.
            log_message("WARNING: For untracked positions, dynamic SL/TP adjustments will NOT work as order_id is unknown.", "WARNING")
            # We cannot set entry_bar_time accurately here, so time-based exit will be less precise.
            # For simplicity, we'll assume it started now for time-based exit.
            current_trade_state['entry_bar_time'] = last_1m_candle.name

        elif not exchange_position and current_trade_state['position']:
            # Position closed on exchange, clear internal state
            log_message("Detected that position was closed on exchange. Clearing internal state.", "INFO")
            current_trade_state = {
                'position': None, 'entry_bar_time': None, 'entry_price': None,
                'initial_sl': None, 'partial_profit_taken': False, 'order_id': None
            }
        elif exchange_position:
            # Update internal position with latest from exchange (e.g., size, SL/TP if amended externally)
            current_trade_state['position'] = exchange_position


        if current_trade_state['position']:
            pos = current_trade_state['position']
            log_message(f"Open position found: {pos['side']} {pos['size']:.3f} at {pos['entry_price']:.2f}")

            # --- Position Management (Exit Strategies) ---
            current_atr = df_1m['atr'].iloc[-1]
            if pd.isna(current_atr) or current_atr == 0:
                log_message("ATR is not available or zero for position management. Skipping ATR-based dynamic SL/TP.", "WARNING")
                current_atr = 0.00000001 # Prevent division by zero, but effectively disables ATR-based logic

            # 1. Time-based exit (Suggestion 13)
            if current_trade_state['entry_bar_time']:
                bars_in_trade = (last_1m_candle.name - current_trade_state['entry_bar_time']) / (60 * 1000)
                log_message(f"Bars in trade: {bars_in_trade:.0f}")

                if bars_in_trade >= MAX_TRADE_DURATION_BARS:
                    log_message(f"Max trade duration ({MAX_TRADE_DURATION_BARS} bars) reached. Closing position.", "INFO")
                    close_position(SYMBOL, pos['side'], pos['size'])
                    current_trade_state = {
                        'position': None, 'entry_bar_time': None, 'entry_price': None,
                        'initial_sl': None, 'partial_profit_taken': False, 'order_id': None
                    }
                    time.sleep(5) # Give some time for order to process
                    continue # Skip further checks for this bar

            # Only proceed with dynamic SL/TP if we have the order_id
            if current_trade_state['order_id']:
                # 2. Partial Profit Taking (Suggestion 10)
                if not current_trade_state['partial_profit_taken']:
                    profit_target_price = current_trade_state['entry_price'] + (current_atr * PARTIAL_PROFIT_ATR_MULTIPLIER) if pos['side'] == "Buy" else \
                                          current_trade_state['entry_price'] - (current_atr * PARTIAL_PROFIT_ATR_MULTIPLIER)

                    if (pos['side'] == "Buy" and current_price >= profit_target_price) or \
                       (pos['side'] == "Sell" and current_price <= profit_target_price):

                        qty_to_close = pos['size'] * PARTIAL_PROFIT_PERCENT
                        # Ensure qty_to_close is not zero or too small (e.g., minimum trade size for BTCUSDT is 0.001)
                        if qty_to_close >= 0.001:
                            log_message(f"Taking partial profit ({PARTIAL_PROFIT_PERCENT*100}%) on {pos['side']} position. Closing {qty_to_close:.3f} units.", "INFO")
                            close_position(SYMBOL, pos['side'], qty_to_close)
                            current_trade_state['partial_profit_taken'] = True

                            # After partial profit, move SL to break-even for the remaining position
                            new_sl_after_partial = current_trade_state['entry_price']

                            # Only amend if the new SL is better (more protective)
                            if (pos['side'] == "Buy" and (pos['stop_loss'] is None or new_sl_after_partial > pos['stop_loss'])) or \
                               (pos['side'] == "Sell" and (pos['stop_loss'] is None or new_sl_after_partial < pos['stop_loss'])):
                                log_message(f"Amending SL to {new_sl_after_partial:.2f} (from {pos['stop_loss']:.2f}) after partial profit.", "INFO")
                                amend_stop_loss_take_profit(SYMBOL, current_trade_state['order_id'], stop_loss=new_sl_after_partial)
                                time.sleep(5) # Give some time for orders to process
                        else:
                            log_message(f"Calculated partial profit quantity ({qty_to_close:.3f}) is too small. Skipping partial profit.", "WARNING")


                # 3. Adaptive Stop Loss (Break-Even) (Suggestion 11)
                # Only move SL to BE if it hasn't been moved yet (i.e., still at initial_sl or not set)
                # and if partial profit hasn't been taken (as partial profit also moves SL to BE)
                if current_trade_state['entry_price'] and current_trade_state['initial_sl'] and \
                   not current_trade_state['partial_profit_taken'] and \
                   (pos['stop_loss'] == current_trade_state['initial_sl'] or pos['stop_loss'] is None):

                    profit_in_atr = ((current_price - current_trade_state['entry_price']) / current_atr) if pos['side'] == "Buy" else \
                                    ((current_trade_state['entry_price'] - current_price) / current_atr)

                    if profit_in_atr >= BREAK_EVEN_PROFIT_ATR:
                        log_message(f"Profit of {profit_in_atr:.2f} ATR reached. Moving stop loss to break-even.", "INFO")
                        new_sl_breakeven = current_trade_state['entry_price']

                        # Only amend if the new SL is better (more protective)
                        if (pos['side'] == "Buy" and (pos['stop_loss'] is None or new_sl_breakeven > pos['stop_loss'])) or \
                           (pos['side'] == "Sell" and (pos['stop_loss'] is None or new_sl_breakeven < pos['stop_loss'])):
                            log_message(f"Amending SL to {new_sl_breakeven:.2f} (from {pos['stop_loss']:.2f}) due to break-even activation.", "INFO")
                            amend_stop_loss_take_profit(SYMBOL, current_trade_state['order_id'], stop_loss=new_sl_breakeven)
                            time.sleep(5) # Give some time for orders to process

                # 4. Trailing Stop after Partial Profit (or after X bars if in profit)
                # If partial profit taken, or if enough bars passed and in profit, implement a tighter trailing stop.
                if current_trade_state['partial_profit_taken'] or \
                   (current_trade_state['entry_bar_time'] and \
                    (last_1m_candle.name - current_trade_state['entry_bar_time']) / (60 * 1000) >= TRAILING_STOP_ACTIVATION_BARS and \
                    ((pos['side'] == "Buy" and current_price > current_trade_state['entry_price']) or \
                     (pos['side'] == "Sell" and current_price < current_trade_state['entry_price']))):

                    # Calculate a new trailing stop
                    if pos['side'] == "Buy":
                        new_trailing_sl = current_price - (current_atr * TRAILING_STOP_ATR_MULTIPLIER)
                    else: # Sell
                        new_trailing_sl = current_price + (current_atr * TRAILING_STOP_ATR_MULTIPLIER)

                    # Only amend if the new trailing SL is better (more protective) than current SL
                    if (pos['side'] == "Buy" and (pos['stop_loss'] is None or new_trailing_sl > pos['stop_loss'])) or \
                       (pos['side'] == "Sell" and (pos['stop_loss'] is None or new_trailing_sl < pos['stop_loss'])):
                        log_message(f"Amending SL to {new_trailing_sl:.2f} (from {pos['stop_loss']:.2f}) due to trailing stop.", "INFO")
                        amend_stop_loss_take_profit(SYMBOL, current_trade_state['order_id'], stop_loss=new_trailing_sl)
                        time.sleep(5) # Give some time for orders to process
            else:
                log_message("WARNING: order_id is missing for the current position. Dynamic SL/TP adjustments are disabled.", "WARNING")


        else: # No open position, look for entry
            log_message("No open position. Looking for trade opportunities.")

            # --- Entry Conditions ---
            # 1. 15m Supertrend and EMA trend (Suggestion 8)
            is_15m_uptrend = (df_15m['supertrend_direction'].iloc[-1] == 1)
            is_15m_downtrend = (df_15m['supertrend_direction'].iloc[-1] == 0)

            # 15m EMA strength (sloped, not flat)
            is_15m_ema_bullish_sloped = (df_15m['ema_short'].iloc[-1] > df_15m['ema_long'].iloc[-1] and
                                          df_15m['ema_short'].iloc[-1] > prev_15m_candle['ema_short'] and
                                          df_15m['ema_long'].iloc[-1] > prev_15m_candle['ema_long'])
            is_15m_ema_bearish_sloped = (df_15m['ema_short'].iloc[-1] < df_15m['ema_long'].iloc[-1] and
                                          df_15m['ema_short'].iloc[-1] < prev_15m_candle['ema_short'] and
                                          df_15m['ema_long'].iloc[-1] < prev_15m_candle['ema_long'])

            # 2. 1m EMA pullback (price crosses EMA9)
            is_1m_price_at_ema9_long = (prev_1m_candle['close'] < prev_1m_candle['ema_short'] and last_1m_candle['close'] >= last_1m_candle['ema_short'])
            is_1m_price_at_ema9_short = (prev_1m_candle['close'] > prev_1m_candle['ema_short'] and last_1m_candle['close'] <= last_1m_candle['ema_short'])

            # 3. Volume Confirmation (Suggestion 1)
            is_volume_spike = (last_1m_candle['volume'] > VOLUME_SPIKE_MULTIPLIER * last_1m_candle['volume_ma'])

            # 4. RSI Confirmation (Suggestion 2)
            is_rsi_bullish = (last_1m_candle['rsi'] > RSI_CONFIRMATION_LEVEL and last_1m_candle['rsi'] > prev_1m_candle['rsi'])
            is_rsi_bearish = (last_1m_candle['rsi'] < RSI_CONFIRMATION_LEVEL and last_1m_candle['rsi'] < prev_1m_candle['rsi'])


            # --- Long Entry Conditions ---
            long_conditions = (
                is_15m_uptrend and is_15m_ema_bullish_sloped and
                is_1m_price_at_ema9_long and
                is_volume_spike and
                is_rsi_bullish
            )

            # --- Short Entry Conditions ---
            short_conditions = (
                is_15m_downtrend and is_15m_ema_bearish_sloped and
                is_1m_price_at_ema9_short and
                is_volume_spike and
                is_rsi_bearish
            )

            side = None
            if long_conditions:
                side = "Buy"
                log_message("Long entry conditions met.", "INFO")
            elif short_conditions:
                side = "Sell"
                log_message("Short entry conditions met.", "INFO")

            if side:
                account_balance = get_account_balance()
                if account_balance == 0:
                    log_message("Could not get account balance. Cannot place trade.", "ERROR")
                    time.sleep(60)
                    continue

                current_atr = df_1m['atr'].iloc[-1]
                if pd.isna(current_atr) or current_atr == 0:
                    log_message("ATR is not available or zero. Cannot place trade.", "ERROR")
                    time.sleep(60)
                    continue

                if side == "Buy":
                    stop_loss_price = current_price - (current_atr * STOP_LOSS_ATR_MULTIPLIER)
                    take_profit_price = current_price + (current_atr * TAKE_PROFIT_ATR_MULTIPLIER)
                else: # Sell
                    stop_loss_price = current_price + (current_atr * STOP_LOSS_ATR_MULTIPLIER)
                    take_profit_price = current_price - (current_atr * TAKE_PROFIT_ATR_MULTIPLIER)

                risk_amount = account_balance * (RISK_PER_TRADE_PERCENT / 100)
                price_diff = abs(current_price - stop_loss_price)
                if price_diff == 0:
                    log_message("Stop loss price is too close to entry price (price_diff is zero). Cannot place trade.", "ERROR")
                    time.sleep(60)
                    continue

                qty = risk_amount / price_diff
                # Round quantity to a suitable precision (e.g., 3 decimal places for BTCUSDT)
                # Use math.floor to ensure we don't over-risk by rounding up.
                qty = math.floor(qty * 1000) / 1000 # For BTCUSDT, 3 decimal places is common

                if qty <= 0.001: # Ensure quantity is positive and not too small (min trade size)
                    log_message(f"Calculated quantity ({qty:.3f}) is zero or too small. Cannot place trade.", "WARNING")
                    time.sleep(60)
                    continue

                log_message(f"Attempting to place {side} order for {qty:.3f} {SYMBOL} at {current_price:.2f}. SL: {stop_loss_price:.2f}, TP: {take_profit_price:.2f}", "INFO")

                order_id = place_order(SYMBOL, side, qty, stop_loss=stop_loss_price, take_profit=take_profit_price)

                if order_id:
                    log_message(f"Trade entered successfully. Order ID: {order_id}", "SUCCESS")
                    # Update global trade state
                    current_trade_state['position'] = {
                        'symbol': SYMBOL, 'side': side, 'size': qty,
                        'entry_price': current_price, 'stop_loss': stop_loss_price,
                        'take_profit': take_profit_price
                    }
                    current_trade_state['entry_bar_time'] = last_1m_candle.name
                    current_trade_state['entry_price'] = current_price
                    current_trade_state['initial_sl'] = stop_loss_price
                    current_trade_state['partial_profit_taken'] = False
                    current_trade_state['order_id'] = order_id # Store order ID
                else:
                    log_message("Failed to place trade.", "ERROR")

        log_message("Waiting for next candle...", "INFO")
        time.sleep(60) # Wait for the next 1-minute candle

if __name__ == "__main__":
    # Ensure API keys are set
    if not API_KEY or not API_SECRET:
        log_message("BYBIT_API_KEY and BYBIT_API_SECRET environment variables must be set.", "CRITICAL")
        exit(1)
    run_bot()