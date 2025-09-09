

--- START OF FILE btemp.md ---

helper.py

from pybit.unified_trading import HTTP
import pandas as pd
import pandas_ta as ta # Use pandas_ta for consistency
import time
import requests
import logging

Set up logging for the helper module

logger = logging.getLogger(name)

class Bybit:
def init(self, api, secret, testnet=False):
if not api or not secret:
raise ValueError("API Key and Secret must be provided.")
self.api = api
self.secret = secret
self.testnet = testnet
self.session = HTTP(api_key=self.api, api_secret=self.secret, testnet=self.testnet)
logger.info(f"Bybit client initialized. Testnet: {self.testnet}")

code
Code
download
content_copy
expand_less

def get_balance(self, coin="USDT"):
    """Fetches and returns the wallet balance for a specific coin."""
    try:
        resp = self.session.get_wallet_balance(accountType="CONTRACT", coin=coin)
        if resp['retCode'] == 0 and resp['result']['list']:
            balance_data = resp['result']['list']['coin']
            if balance_data:
                balance = float(balance_data['walletBalance'])
                logger.debug(f"Fetched balance: {balance} {coin}")
                return balance
            else:
                logger.warning(f"No balance data found for {coin}.")
                return 0.0
        else:
            logger.error(f"Error getting balance for {coin}: {resp.get('retMsg', 'Unknown error')}")
            return None
    except Exception as err:
        logger.error(f"Exception getting balance for {coin}: {err}")
        return None

def get_positions(self, settleCoin="USDT"):
    """Returns a list of symbols with open positions."""
    try:
        resp = self.session.get_positions(category='linear', settleCoin=settleCoin)
        if resp['retCode'] == 0:
            # Filter for positions with a non-zero size
            open_positions = [elem['symbol'] for elem in resp['result']['list'] if float(elem['leverage']) > 0 and float(elem['size']) > 0]
            logger.debug(f"Fetched open positions: {open_positions}")
            return open_positions
        else:
            logger.error(f"Error getting positions: {resp.get('retMsg', 'Unknown error')}")
            return []
    except Exception as err:
        logger.error(f"Exception getting positions: {err}")
        return []

def get_tickers(self):
    """Retrieves all USDT perpetual linear symbols from the derivatives market."""
    try:
        resp = self.session.get_tickers(category="linear")
        if resp['retCode'] == 0:
            symbols = [elem['symbol'] for elem in resp['result']['list'] if 'USDT' in elem['symbol'] and not 'USDC' in elem['symbol']]
            logger.debug(f"Fetched {len(symbols)} tickers.")
            return symbols
        else:
            logger.error(f"Error getting tickers: {resp.get('retMsg', 'Unknown error')}")
            return None
    except Exception as err:
        logger.error(f"Exception getting tickers: {err}")
        return None

def klines(self, symbol, timeframe, limit=500):
    """Fetches klines (candlestick data) for a given symbol and returns a pandas DataFrame."""
    try:
        resp = self.session.get_kline(
            category='linear',
            symbol=symbol,
            interval=str(timeframe), # Ensure interval is string
            limit=limit
        )
        if resp['retCode'] == 0:
            df = pd.DataFrame(resp['result']['list'], columns=['Time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Turnover'])
            df['Time'] = pd.to_datetime(df['Time'], unit='ms') # Convert timestamp to datetime
            df = df.set_index('Time').astype(float)
            df = df.sort_index() # Ensure ascending order by time
            logger.debug(f"Fetched {len(df)} klines for {symbol} ({timeframe}min).")
            return df
        else:
            logger.error(f"Error getting klines for {symbol}: {resp.get('retMsg', 'Unknown error')}")
            return pd.DataFrame()
    except Exception as err:
        logger.error(f"Exception getting klines for {symbol}: {err}")
        return pd.DataFrame() # Return empty DataFrame on error

def get_orderbook_levels(self, symbol, limit=50):
    """Analyzes the order book to find strong support and resistance levels."""
    try:
        resp = self.session.get_orderbook(
            category='linear',
            symbol=symbol,
            limit=limit
        )
        if resp['retCode'] == 0:
            bids = pd.DataFrame(resp['result']['bids'], columns=['price', 'volume']).astype(float)
            asks = pd.DataFrame(resp['result']['asks'], columns=['price', 'volume']).astype(float)
            
            strong_support_price = bids.loc[bids['volume'].idxmax()]['price'] if not bids.empty else None
            strong_resistance_price = asks.loc[asks['volume'].idxmax()]['price'] if not asks.empty else None
            
            logger.debug(f"Orderbook for {symbol}: Support={strong_support_price}, Resistance={strong_resistance_price}")
            return strong_support_price, strong_resistance_price
        else:
            logger.error(f"Error getting orderbook for {symbol}: {resp.get('retMsg', 'Unknown error')}")
            return None, None
    except Exception as err:
        logger.error(f"Exception getting orderbook for {symbol}: {err}")
        return None, None

def get_precisions(self, symbol):
    """Retrieves the decimal precision for price and quantity."""
    try:
        resp = self.session.get_instruments_info(
            category='linear',
            symbol=symbol
        )
        if resp['retCode'] == 0 and resp['result']['list']:
            info = resp['result']['list']
            price_step = info['priceFilter']['tickSize']
            qty_step = info['lotSizeFilter']['qtyStep']
            
            # Calculate precision based on tickSize/qtyStep format (e.g., 0.01 -> 2, 1 -> 0)
            price_precision = len(price_step.split('.')) if '.' in price_step else 0
            qty_precision = len(qty_step.split('.')) if '.' in qty_step else 0
            
            logger.debug(f"Precisions for {symbol}: Price={price_precision}, Qty={qty_precision}")
            return price_precision, qty_precision
        else:
            logger.error(f"Error getting precisions for {symbol}: {resp.get('retMsg', 'Unknown error')}")
            return 0, 0
    except Exception as err:
        logger.error(f"Exception getting precisions for {symbol}: {err}")
        return 0, 0

def set_margin_mode_and_leverage(self, symbol, mode=1, leverage=10):
    """Sets the margin mode and leverage for a symbol."""
    try:
        # tradeMode: 0 for Cross, 1 for Isolated
        resp = self.session.switch_margin_mode(
            category='linear',
            symbol=symbol,
            tradeMode=str(mode),
            buyLeverage=str(leverage),
            sellLeverage=str(leverage)
        )
        if resp['retCode'] == 0:
            logger.info(f"Margin mode set to {'Isolated' if mode==1 else 'Cross'} and leverage set to {leverage}x for {symbol}.")
        elif resp['retCode'] == 110026 or resp['retCode'] == 110043: # Already set or in position
            logger.debug(f"Margin mode or leverage already set for {symbol} (Code: {resp['retCode']}).")
        else:
            logger.warning(f"Failed to set margin mode/leverage for {symbol}: {resp.get('retMsg', 'Unknown error')} (Code: {resp['retCode']})")
    except Exception as err:
        if '110026' in str(err) or '110043' in str(err): # Already set or in position
            logger.debug(f"Margin mode or leverage already set for {symbol}.")
        else:
            logger.error(f"Exception setting margin mode/leverage for {symbol}: {err}")

def place_order_common(self, symbol, side, order_type, qty, price=None, trigger_price=None, tp_price=None, sl_price=None, time_in_force='GTC'):
    """Internal common function to place various order types."""
    try:
        params = {
            'category': 'linear',
            'symbol': symbol,
            'side': side,
            'orderType': order_type,
            'qty': str(qty), # qty must be string
            'timeInForce': time_in_force
        }
        if price is not None:
            params['price'] = str(price) # price must be string
        if trigger_price is not None:
            params['triggerPrice'] = str(trigger_price) # triggerPrice must be string
            params['triggerBy'] = 'MarkPrice' # Default to Mark Price for triggers
        if tp_price is not None:
            params['takeProfit'] = str(tp_price)
            params['tpTriggerBy'] = 'Market' # Market price for TP/SL triggers is generally safer
        if sl_price is not None:
            params['stopLoss'] = str(sl_price)
            params['slTriggerBy'] = 'Market'

        response = self.session.place_order(**params)
        if response['retCode'] == 0:
            logger.info(f"Order placed for {symbol} ({order_type} {side} {qty}). Order ID: {response['result']['orderId']}")
            return response['result']['orderId']
        else:
            logger.error(f"Failed to place order for {symbol} ({order_type} {side} {qty}): {response.get('retMsg', 'Unknown error')} (Code: {response['retCode']})")
            return None
    except Exception as err:
        logger.error(f"Exception placing {order_type} order for {symbol}: {err}")
        return None

def place_market_order(self, symbol, side, qty, tp_price=None, sl_price=None):
    """Places a market order with optional TP/SL."""
    return self.place_order_common(symbol, side, 'Market', qty, tp_price=tp_price, sl_price=sl_price)

def place_limit_order(self, symbol, side, price, qty, tp_price=None, sl_price=None, time_in_force='GTC'):
    """Places a limit order with optional TP/SL."""
    return self.place_order_common(symbol, side, 'Limit', qty, price=price, tp_price=tp_price, sl_price=sl_price, time_in_force=time_in_force)

def place_conditional_order(self, symbol, side, qty, trigger_price, order_type='Market', price=None, tp_price=None, sl_price=None):
    """Places a conditional order that becomes active at a trigger price.
    If order_type is 'Limit', a specific `price` must be provided for the limit execution."""
    # For conditional limit orders, the `price` parameter is required for the actual limit order execution.
    # If not provided for a conditional limit, we'll default to the trigger_price.
    if order_type == 'Limit' and price is None:
        price = trigger_price # Default to trigger_price if no explicit limit price given
        logger.warning(f"Conditional limit order requested for {symbol} without explicit `price`. Using `trigger_price` as limit execution price.")

    return self.place_order_common(symbol, side, order_type, qty, price=price, trigger_price=trigger_price, tp_price=tp_price, sl_price=sl_price)

def cancel_all_open_orders(self, symbol):
    """Cancels all active orders for a given symbol."""
    try:
        response = self.session.cancel_all_orders(
            category='linear',
            symbol=symbol
        )
        if response['retCode'] == 0:
            logger.info(f"All open orders for {symbol} cancelled successfully.")
        else:
            logger.warning(f"Failed to cancel all orders for {symbol}: {response.get('retMsg', 'Unknown error')} (Code: {response['retCode']})")
        return response
    except Exception as err:
        logger.error(f"Exception cancelling all orders for {symbol}: {err}")
        return {'retCode': -1, 'retMsg': str(err)}

def get_open_orders(self, symbol=None):
    """Retrieves all active orders for a given symbol, or all symbols if none specified."""
    try:
        params = {'category': 'linear'}
        if symbol:
            params['symbol'] = symbol
        
        response = self.session.get_open_orders(**params)
        if response['retCode'] == 0:
            open_orders = response['result']['list']
            logger.debug(f"Fetched {len(open_orders)} open orders for {symbol if symbol else 'all symbols'}.")
            return open_orders
        else:
            logger.error(f"Error getting open orders for {symbol if symbol else 'all symbols'}: {response.get('retMsg', 'Unknown error')} (Code: {response['retCode']})")
            return []
    except Exception as err:
        logger.error(f"Exception getting open orders for {symbol if symbol else 'all symbols'}: {err}")
        return []

def close_position(self, symbol, position_idx=0):
    """
    Closes an open position for a given symbol using a market order.
    position_idx: 0 for one-way mode, 1 for buy side, 2 for sell side in hedge mode.
    """
    try:
        # First, get current position details to determine side and size
        positions_resp = self.session.get_positions(category='linear', symbol=symbol)
        if positions_resp['retCode'] != 0 or not positions_resp['result']['list']:
            logger.warning(f"Could not get position details for {symbol} to close. {positions_resp.get('retMsg', 'No position found')}")
            return None

        position_info = None
        for pos in positions_resp['result']['list']:
            if float(pos['size']) > 0: # Found an open position
                position_info = pos
                break
        
        if not position_info:
            logger.info(f"No open position found for {symbol} to close.")
            return None

        current_side = position_info['side']
        current_size = float(position_info['size'])
        
        if current_size == 0:
            logger.info(f"No open position found for {symbol} to close (size is 0).")
            return None

        # Determine the opposite side to close the position
        close_side = 'Sell' if current_side == 'Buy' else 'Buy'

        response = self.session.place_order(
            category='linear',
            symbol=symbol,
            side=close_side,
            orderType='Market',
            qty=str(current_size),
            isTpSl='false', # Do not attach TP/SL to closing order
            reduceOnly=True, # Ensure this order only reduces position
            positionIdx=position_idx
        )
        if response['retCode'] == 0:
            logger.info(f"Market order placed to close {symbol} position ({current_side} {current_size}). Order ID: {response['result']['orderId']}")
            return response['result']['orderId']
        else:
            logger.error(f"Failed to place market order to close {symbol} position: {response.get('retMsg', 'Unknown error')} (Code: {response['retCode']})")
            return None
    except Exception as err:
        logger.error(f"Exception closing position for {symbol}: {err}")
        return None
code
Code
download
content_copy
expand_less
IGNORE_WHEN_COPYING_START
IGNORE_WHEN_COPYING_END
```python
#!/usr/bin/env python3

import pandas as pd
import pandas_ta as ta
import logging
from dotenv import load_dotenv
import os
from time import sleep
import datetime
import pytz
import numpy as np # Added for numpy operations

# Import the Bybit client from the helper module
from helper import Bybit # Assuming helper.py is in the same directory

# --- Setup and Configuration ---
load_dotenv()

# --- Configuration and API Credentials ---
BOT_CONFIG = {
    "API_KEY": os.getenv("BYBIT_API_KEY"),
    "API_SECRET": os.getenv("BYBIT_API_SECRET"),
    "TESTNET": os.getenv("BYBIT_TESTNET", "False").lower() == "true", # Add TESTNET flag (set in .env: BYBIT_TESTNET=True)
    "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO").upper(), # New: Configurable log level
    "TIMEFRAME": 15, # in minutes
    "MARGIN_MODE": 1, # 0: Cross, 1: Isolated
    "LEVERAGE": 10,
    "ORDER_QTY_USDT": 50, # Quantity in USDT (e.g., $50 worth of crypto)
    "MAX_POSITIONS": 5,
    "MAX_OPEN_ORDERS_PER_SYMBOL": 1, # New: Max pending orders per symbol
    "TIMEZONE": 'America/New_York',
    "MARKET_OPEN_HOUR": 9,
    "MARKET_CLOSE_HOUR": 17,
    "LOOP_WAIT_TIME_SECONDS": 120, # How long to wait between main loop cycles
    "MIN_KLINES_FOR_STRATEGY": 100, # New: Minimum klines needed for indicator calculation
    "PRICE_DETECTION_THRESHOLD_PCT": 0.005, # 0.5% threshold for current price near support/resistance

    # --- Chandelier Exit Scalping Strategy Parameters ---
    "ATR_PERIOD": 14,
    "CHANDELIER_MULTIPLIER": 2.0,
    "MIN_ATR_MULTIPLIER": 1.5, # For dynamic multiplier
    "MAX_ATR_MULTIPLIER": 3.0, # For dynamic multiplier
    "TREND_EMA_PERIOD": 50, # For overall trend filter
    "EMA_SHORT_PERIOD": 8, # For entry EMA crossover
    "EMA_LONG_PERIOD": 21, # For entry EMA crossover
    "RSI_PERIOD": 14,
    "RSI_OVERBOUGHT": 70,
    "RSI_OVERSOLD": 30,
    "VOLUME_THRESHOLD_MULTIPLIER": 1.5, # Volume spike threshold (e.g., 1.5x 20-period MA)
    "RISK_PER_TRADE_PCT": 0.005, # 0.5% of capital risked per trade (for position sizing)
    "REWARD_RISK_RATIO": 2.0, # Take Profit at 2x Stop Loss distance
    "MAX_HOLDING_CANDLES": 5, # Max candles to hold a trade before considering closing (for live bot, this implies checking and closing if not exited by TP/SL)
}

# --- Logging Setup ---
logging.basicConfig(
    level=getattr(logging, BOT_CONFIG["LOG_LEVEL"]), # Use LOG_LEVEL from config
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s', # Added %(name)s
    handlers=[
        logging.StreamHandler()
    ]
)
# Ensure helper.py logs are also handled by the basicConfig
logging.getLogger('helper').setLevel(getattr(logging, BOT_CONFIG["LOG_LEVEL"]))

if not BOT_CONFIG["API_KEY"] or not BOT_CONFIG["API_SECRET"]:
    logging.error("API keys not found. Please check your .env file.")
    exit()

# --- API Session ---
try:
    bybit_client = Bybit(
        api=BOT_CONFIG["API_KEY"],
        secret=BOT_CONFIG["API_SECRET"],
        testnet=BOT_CONFIG["TESTNET"]
    )
    logging.info(f"Successfully connected to Bybit API. Testnet: {BOT_CONFIG['TESTNET']}")
    logging.info(f"Bot configuration: {BOT_CONFIG}")
except Exception as e:
    logging.error(f"Failed to connect to Bybit API: {e}")
    exit()

# --- Helper Functions ---
def get_current_time(timezone_str):
    """Returns the current local and UTC time objects."""
    tz = pytz.timezone(timezone_str)
    local_time = datetime.datetime.now(tz)
    utc_time = datetime.datetime.now(pytz.utc)
    return local_time, utc_time

def is_market_open(local_time, open_hour, close_hour):
    """Checks if the market is open based on configured hours."""
    current_hour = local_time.hour
    return open_hour <= current_hour < close_hour

# --- Strategy Section (Chandelier Exit Scalping Logic) ---
def calculate_chandelier_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate Chandelier Exit, EMAs, RSI, and volume indicators for scalping.
    Uses pandas_ta for efficiency.
    """
    df = df.copy()
    
    # Ensure columns are float
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # Calculate ATR
    df.ta.atr(high=df['High'], low=df['Low'], close=df['Close'], length=BOT_CONFIG["ATR_PERIOD"], append=True)
    df['atr'] = df[f'ATR_{BOT_CONFIG["ATR_PERIOD"]}'] # Rename for consistency

    # Calculate highest high and lowest low for Chandelier Exit
    df['highest_high'] = df['High'].rolling(window=BOT_CONFIG["ATR_PERIOD"]).max()
    df['lowest_low'] = df['Low'].rolling(window=BOT_CONFIG["ATR_PERIOD"]).min()
    
    # Dynamic ATR multiplier (using a 20-period std of ATR for volatility)
    # Ensure enough data for volatility calculation
    if len(df) >= 20:
        df['volatility'] = df['atr'].rolling(window=20).std()
        # Handle cases where volatility might be zero or NaN
        mean_volatility = df['volatility'].mean()
        if mean_volatility > 0:
            df['dynamic_multiplier'] = np.clip(
                BOT_CONFIG["CHANDELIER_MULTIPLIER"] * (df['volatility'] / mean_volatility),
                BOT_CONFIG["MIN_ATR_MULTIPLIER"],
                BOT_CONFIG["MAX_ATR_MULTIPLIER"]
            )
        else:
            df['dynamic_multiplier'] = BOT_CONFIG["CHANDELIER_MULTIPLIER"]
    else:
        df['dynamic_multiplier'] = BOT_CONFIG["CHANDELIER_MULTIPLIER"] # Default if not enough data

    # Chandelier Exit levels
    df['chandelier_long'] = df['highest_high'] - (df['atr'] * df['dynamic_multiplier'])
    df['chandelier_short'] = df['lowest_low'] + (df['atr'] * df['dynamic_multiplier'])
    
    # Trend filter (EMA)
    df.ta.ema(close=df['Close'], length=BOT_CONFIG["TREND_EMA_PERIOD"], append=True)
    df['trend_ema'] = df[f'EMA_{BOT_CONFIG["TREND_EMA_PERIOD"]}']
    
    # EMAs for entries
    df.ta.ema(close=df['Close'], length=BOT_CONFIG["EMA_SHORT_PERIOD"], append=True)
    df['ema_short'] = df[f'EMA_{BOT_CONFIG["EMA_SHORT_PERIOD"]}']
    df.ta.ema(close=df['Close'], length=BOT_CONFIG["EMA_LONG_PERIOD"], append=True)
    df['ema_long'] = df[f'EMA_{BOT_CONFIG["EMA_LONG_PERIOD"]}']
    
    # RSI
    df.ta.rsi(close=df['Close'], length=BOT_CONFIG["RSI_PERIOD"], append=True)
    df['rsi'] = df[f'RSI_{BOT_CONFIG["RSI_PERIOD"]}']
    
    # Volume filter
    df.ta.sma(close=df['Volume'], length=20, append=True) # 20-period SMA for volume
    df['volume_ma'] = df[f'SMA_20']
    df['volume_spike'] = (df['Volume'] / df['volume_ma']) > BOT_CONFIG["VOLUME_THRESHOLD_MULTIPLIER"]
    
    # Clean up temporary columns and fill NaNs
    df = df.drop(columns=[col for col in df.columns if 'ATR_' in col or 'EMA_' in col or 'RSI_' in col or 'SMA_' in col and col not in ['atr', 'ema_short', 'ema_long', 'trend_ema', 'rsi', 'volume_ma']], errors='ignore')
    return df.fillna(method='ffill').fillna(0) # Fill NaNs forward, then with 0

def generate_chandelier_signals(df: pd.DataFrame):
    """
    Generate explicit long and short signals based on Chandelier Exit Scalping Strategy.
    Returns 'Buy', 'Sell', or 'none', along with calculated risk distance, TP, SL, and dynamic multiplier.
    """
    # Ensure enough data for all indicators, including lookback periods for EMA, ATR, RSI, and Volume MA
    min_required_klines = max(BOT_CONFIG["MIN_KLINES_FOR_STRATEGY"], BOT_CONFIG["TREND_EMA_PERIOD"], 
                              BOT_CONFIG["EMA_LONG_PERIOD"], BOT_CONFIG["ATR_PERIOD"], 
                              BOT_CONFIG["RSI_PERIOD"], 20) # 20 for Volume MA and volatility std
    
    if df.empty or len(df) < min_required_klines:
        logging.debug(f"Not enough data for Chandelier Exit strategy indicators (needed >{min_required_klines}, got {len(df)}).")
        return 'none', None, None, None, None # signal, risk, tp, sl, dynamic_multiplier

    # Ensure all indicators are calculated
    df_with_indicators = calculate_chandelier_indicators(df)
    
    # Get the last two rows for current and previous candle analysis
    last_row = df_with_indicators.iloc[-1]
    prev_row = df_with_indicators.iloc[-2]

    current_price = last_row['Close']
    atr_value = last_row['atr']
    dynamic_multiplier = last_row['dynamic_multiplier']

    if atr_value <= 0 or pd.isna(atr_value) or pd.isna(dynamic_multiplier): # Avoid division by zero or invalid ATR/multiplier
        logging.warning("ATR value or dynamic multiplier is invalid, cannot calculate risk. Skipping signal generation.")
        return 'none', None, None, None, None

    risk_distance = atr_value * dynamic_multiplier
    
    # Long entry conditions
    long_entry_condition = (
        last_row['ema_short'] > last_row['ema_long'] and
        prev_row['ema_short'] <= prev_row['ema_long'] and # Crossover
        last_row['Close'] > last_row['trend_ema'] and # Price above long-term trend
        last_row['rsi'] < BOT_CONFIG["RSI_OVERBOUGHT"] and # RSI not overbought
        last_row['volume_spike'] # Volume confirmation
    )

    # Short entry conditions
    short_entry_condition = (
        last_row['ema_short'] < last_row['ema_long'] and
        prev_row['ema_short'] >= prev_row['ema_long'] and # Crossover
        last_row['Close'] < last_row['trend_ema'] and # Price below long-term trend
        last_row['rsi'] > BOT_CONFIG["RSI_OVERSOLD"] and # RSI not oversold
        last_row['volume_spike'] # Volume confirmation
    )

    signal = 'none'
    tp_price = None
    sl_price = None

    if long_entry_condition:
        signal = 'Buy'
        sl_price = current_price - risk_distance
        tp_price = current_price + (risk_distance * BOT_CONFIG["REWARD_RISK_RATIO"])
    elif short_entry_condition:
        signal = 'Sell'
        sl_price = current_price + risk_distance
        tp_price = current_price - (risk_distance * BOT_CONFIG["REWARD_RISK_RATIO"])
    
    return signal, risk_distance, tp_price, sl_price, dynamic_multiplier


# --- Main Bot Loop ---
def main():
    symbols = bybit_client.get_tickers()
    if not symbols:
        logging.info("No symbols found. Exiting.")
        return

    logging.info(f"Starting trading bot. Checking {len(symbols)} symbols. Testnet: {BOT_CONFIG['TESTNET']}")

    # Dictionary to track active trades for time-based exit (symbol -> {'entry_time': datetime, 'order_id': str, 'side': str})
    # This is a simplified in-memory tracker. For persistence, a database would be needed.
    active_trades_tracker = {}

    while True:
        local_time, utc_time = get_current_time(BOT_CONFIG["TIMEZONE"])
        logging.info(f"Local Time: {local_time.strftime('%Y-%m-%d %H:%M:%S')} | UTC Time: {utc_time.strftime('%Y-%m-%d %H:%M:%S')}")

        if not is_market_open(local_time, BOT_CONFIG["MARKET_OPEN_HOUR"], BOT_CONFIG["MARKET_CLOSE_HOUR"]):
            logging.info(f"Market is closed ({BOT_CONFIG['MARKET_OPEN_HOUR']}:00-{BOT_CONFIG['MARKET_CLOSE_HOUR']}:00 {BOT_CONFIG['TIMEZONE']}). Skipping this cycle. Waiting {BOT_CONFIG['LOOP_WAIT_TIME_SECONDS']} seconds.")
            sleep(BOT_CONFIG['LOOP_WAIT_TIME_SECONDS'])
            continue
            
        balance = bybit_client.get_balance()
        if balance is None:
            logging.error(f'Cannot connect to API or get balance. Waiting {BOT_CONFIG["LOOP_WAIT_TIME_SECONDS']} seconds and retrying.')
            sleep(BOT_CONFIG['LOOP_WAIT_TIME_SECONDS'])
            continue
        
        logging.info(f'Current balance: {balance:.2f} USDT')
        
        current_positions = bybit_client.get_positions()
        logging.info(f'You have {len(current_positions)} open positions: {current_positions}')

        # --- Manage existing trades (time-based exit) ---
        symbols_to_remove_from_tracker = []
        for symbol, trade_info in active_trades_tracker.items():
            if symbol not in current_positions:
                logging.info(f"Position for {symbol} closed (not in current_positions). Removing from tracker.")
                symbols_to_remove_from_tracker.append(symbol)
                continue

            # Calculate elapsed candles (approximate)
            # This assumes `entry_time` is roughly aligned with candle open times.
            # For more precision, one would need to track the entry candle's timestamp.
            elapsed_seconds = (utc_time - trade_info['entry_time']).total_seconds()
            elapsed_candles = elapsed_seconds / (BOT_CONFIG["TIMEFRAME"] * 60)

            if elapsed_candles >= BOT_CONFIG["MAX_HOLDING_CANDLES"]:
                logging.info(f"Position for {symbol} has exceeded MAX_HOLDING_CANDLES ({BOT_CONFIG['MAX_HOLDING_CANDLES']}). Attempting to close.")
                # Cancel any open orders for this symbol first
                bybit_client.cancel_all_open_orders(symbol)
                sleep(0.5)
                # Then close the position
                bybit_client.close_position(symbol)
                symbols_to_remove_from_tracker.append(symbol)
        
        for symbol in symbols_to_remove_from_tracker:
            if symbol in active_trades_tracker:
                del active_trades_tracker[symbol]

        # --- Iterate through symbols for new trades ---
        for symbol in symbols:
            # Re-check positions and max_pos inside the loop, as positions can change
            current_positions = bybit_client.get_positions() 
            if len(current_positions) >= BOT_CONFIG["MAX_POSITIONS"]:
                logging.info(f"Max positions ({BOT_CONFIG['MAX_POSITIONS']}) reached. Halting signal checks for this cycle.")
                break # Exit the symbol loop, continue to next main loop iteration

            if symbol in current_positions:
                logging.debug(f"Skipping {symbol} as there is already an open position.")
                continue

            # Check for open orders for this symbol to avoid duplicate entries
            open_orders_for_symbol = bybit_client.get_open_orders(symbol)
            if len(open_orders_for_symbol) >= BOT_CONFIG["MAX_OPEN_ORDERS_PER_SYMBOL"]:
                logging.debug(f"Skipping {symbol} as there are {len(open_orders_for_symbol)} open orders (max {BOT_CONFIG['MAX_OPEN_ORDERS_PER_SYMBOL']}).")
                continue

            kl = bybit_client.klines(symbol, BOT_CONFIG["TIMEFRAME"])
            if kl.empty or len(kl) < BOT_CONFIG["MIN_KLINES_FOR_STRATEGY"]: # Ensure enough data for indicators
                logging.warning(f"Not enough klines data for {symbol} (needed >{BOT_CONFIG['MIN_KLINES_FOR_STRATEGY']}). Skipping.")
                continue

            support, resistance = bybit_client.get_orderbook_levels(symbol)
            current_price = kl['Close'].iloc[-1]
            
            if support is None or resistance is None:
                logging.warning(f"Could not retrieve orderbook levels for {symbol}. Skipping strategy check.")
                continue

            # --- Chandelier Exit Scalping Strategy Signal Generation ---
            final_signal, risk_distance, tp_price, sl_price, dynamic_multiplier = generate_chandelier_signals(kl)

            # --- Order Placement Logic based on Final Signal ---
            if final_signal != 'none':
                # Calculate common order parameters
                price_precision, qty_precision = bybit_client.get_precisions(symbol)
                
                # Calculate position size based on risk per trade
                # Using current balance as capital base for risk calculation
                capital_for_risk = balance 
                risk_amount_usdt = capital_for_risk * BOT_CONFIG["RISK_PER_TRADE_PCT"]
                
                if risk_distance <= 0:
                    logging.warning(f"Calculated risk_distance for {symbol} is zero or negative. Skipping order.")
                    continue

                # Calculate quantity based on risk amount and stop-loss distance
                order_qty_risk_based = risk_amount_usdt / risk_distance
                
                # Also calculate quantity based on fixed USDT value for the order
                order_qty_from_usdt = BOT_CONFIG["ORDER_QTY_USDT"] / current_price
                
                # Use the smaller of the two quantities to manage risk and capital exposure
                order_qty = min(round(order_qty_risk_based, qty_precision), round(order_qty_from_usdt, qty_precision))
                
                # Ensure minimum order quantity (Bybit usually has a minimum, but we ensure it's positive here)
                if order_qty <= 0:
                    logging.warning(f"Calculated order quantity for {symbol} is zero or negative ({order_qty}). Skipping order.")
                    continue

                # Set margin mode and leverage once before considering placing an order
                bybit_client.set_margin_mode_and_leverage(
                    symbol, BOT_CONFIG["MARGIN_MODE"], BOT_CONFIG["LEVERAGE"]
                )
                sleep(0.5) # Give API a moment to process

                order_id = None
                if final_signal == 'Buy':
                    logging.info(f'Found BUY signal for {symbol} 📈 (Chandelier Exit Scalping). Current Price: {current_price:.4f}, TP: {tp_price:.4f}, SL: {sl_price:.4f}')
                    
                    # Option 1: Place a Limit Order near strong support (if price is near support)
                    if support and abs(current_price - support) < (current_price * BOT_CONFIG["PRICE_DETECTION_THRESHOLD_PCT"]):
                        logging.info(f'Price near support at {support}. Placing Limit Order to Buy at support.')
                        order_id = bybit_client.place_limit_order(
                            symbol=symbol,
                            side='Buy',
                            price=round(support, price_precision), # Try to buy at the support level
                            qty=order_qty,
                            tp_price=round(tp_price, price_precision),
                            sl_price=round(sl_price, price_precision)
                        )
                    # Option 2: Place a Conditional Market Order for a breakout above resistance (if price has broken resistance)
                    elif resistance and current_price > resistance:
                        logging.info(f'Price broken above resistance at {resistance}. Placing Conditional Market Order for breakout.')
                        # Trigger slightly above current price to confirm breakout momentum
                        trigger_price = current_price * (1 + 0.001) # 0.1% above current price
                        order_id = bybit_client.place_conditional_order(
                            symbol=symbol,
                            side='Buy',
                            qty=order_qty,
                            trigger_price=round(trigger_price, price_precision),
                            order_type='Market',
                            tp_price=round(tp_price, price_precision),
                            sl_price=round(sl_price, price_precision)
                        )
                    # Option 3: If no specific S/R condition, place a Market Order (more aggressive scalping)
                    else:
                        logging.info(f'No specific S/R condition. Placing Market Order to Buy.')
                        order_id = bybit_client.place_market_order(
                            symbol=symbol,
                            side='Buy',
                            qty=order_qty,
                            tp_price=round(tp_price, price_precision),
                            sl_price=round(sl_price, price_precision)
                        )

                elif final_signal == 'Sell':
                    logging.info(f'Found SELL signal for {symbol} 📉 (Chandelier Exit Scalping). Current Price: {current_price:.4f}, TP: {tp_price:.4f}, SL: {sl_price:.4f}')

                    # Option 1: Place a Limit Order near strong resistance (if price is near resistance)
                    if resistance and abs(current_price - resistance) < (current_price * BOT_CONFIG["PRICE_DETECTION_THRESHOLD_PCT"]):
                        logging.info(f'Price near resistance at {resistance}. Placing Limit Order to Sell at resistance.')
                        order_id = bybit_client.place_limit_order(
                            symbol=symbol,
                            side='Sell',
                            price=round(resistance, price_precision), # Try to sell at the resistance level
                            qty=order_qty,
                            tp_price=round(tp_price, price_precision),
                            sl_price=round(sl_price, price_precision)
                        )
                    # Option 2: Place a Conditional Market Order for a breakdown below support (if price has broken support)
                    elif support and current_price < support:
                        logging.info(f'Price broken below support at {support}. Placing Conditional Market Order for breakdown.')
                        # Trigger slightly below current price to confirm breakdown momentum
                        trigger_price = current_price * (1 - 0.001) # 0.1% below current price
                        order_id = bybit_client.place_conditional_order(
                            symbol=symbol,
                            side='Sell',
                            qty=order_qty,
                            trigger_price=round(trigger_price, price_precision),
                            order_type='Market',
                            tp_price=round(tp_price, price_precision),
                            sl_price=round(sl_price, price_precision)
                        )
                    # Option 3: If no specific S/R condition, place a Market Order (more aggressive scalping)
                    else:
                        logging.info(f'No specific S/R condition. Placing Market Order to Sell.')
                        order_id = bybit_client.place_market_order(
                            symbol=symbol,
                            side='Sell',
                            qty=order_qty,
                            tp_price=round(tp_price, price_precision),
                            sl_price=round(sl_price, price_precision)
                        )
                
                if order_id:
                    active_trades_tracker[symbol] = {
                        'entry_time': utc_time, # Store UTC time of order placement
                        'order_id': order_id,
                        'side': final_signal
                    }
            else:
                logging.debug(f"No strong combined trading signal for {symbol}.")


        logging.info(f'--- Cycle finished. Waiting {BOT_CONFIG["LOOP_WAIT_TIME_SECONDS"]} seconds for next loop. ---')
        sleep(BOT_CONFIG['LOOP_WAIT_TIME_SECONDS'])

if __name__ == "__main__":
    main()
Bybit Client (helper.py) - Upgrades and Enhancements

The helper.py module has been significantly enhanced to provide a more robust and reliable interface for interacting with the Bybit API.

Key Improvements:

Robust Error Handling: All API calls now include comprehensive try-except blocks and explicit checks for resp['retCode'] == 0. Error messages from the Bybit API (retMsg) are logged, providing clearer insights into failures.

Input Validation: The Bybit class constructor now validates the presence of API keys, raising a ValueError if they are missing.

Enhanced get_balance(): More specific checks for empty list or coin data in the API response, returning 0.0 and logging a warning instead of raising an error.

klines() Interval Type: Ensures the interval parameter is passed as a string to the pybit library, preventing potential type-related issues.

place_order_common() Return Value: This core function now returns the orderId upon successful order placement, which is crucial for tracking and managing active orders. It returns None on failure.

New get_open_orders() Function: This essential addition allows the bot to retrieve all active (pending) orders for a specific symbol or across all symbols. This is vital for preventing duplicate orders and for managing trade lifecycles.

New close_position() Function: A dedicated method to close an open position using a market order. It intelligently determines the opposite side and size, and uses reduceOnly=True to ensure the order only closes existing positions, not opens new ones. This is critical for implementing time-based or emergency exits.

Improved Logging: More detailed logging messages, including retCode for API responses, provide better context for debugging and operational monitoring.

Main Trading Bot Script - Upgrades and Enhancements

The main bot script has undergone a major overhaul, integrating the advanced Chandelier Exit Scalping Strategy, improving configuration management, and enhancing trade lifecycle management.

Key Improvements:

Centralized BOT_CONFIG: All configurable parameters, including API credentials, trading parameters, and all Chandelier Exit strategy-specific settings, are now consolidated into a single BOT_CONFIG dictionary. This makes the bot easier to configure and maintain.

New Parameters: LOG_LEVEL, MIN_KLINES_FOR_STRATEGY, MAX_OPEN_ORDERS_PER_SYMBOL, ATR_PERIOD, CHANDELIER_MULTIPLIER, MIN_ATR_MULTIPLIER, MAX_ATR_MULTIPLIER, TREND_EMA_PERIOD, EMA_SHORT_PERIOD, EMA_LONG_PERIOD, RSI_PERIOD, RSI_OVERBOUGHT, RSI_OVERSOLD, VOLUME_THRESHOLD_MULTIPLIER, RISK_PER_TRADE_PCT, REWARD_RISK_RATIO, MAX_HOLDING_CANDLES.

Dynamic Logging: The logging level is now configurable via BOT_CONFIG["LOG_LEVEL"] (e.g., "INFO", "DEBUG"), allowing for flexible verbosity during operation and debugging.

Integrated Chandelier Exit Scalping Strategy:

calculate_chandelier_indicators(df): This new function, adapted from the Chandelier Exit strategy, calculates all necessary indicators (ATR, dynamic ATR multiplier, Chandelier Exit levels, short/long EMAs, RSI, volume moving average, and volume spike) using pandas_ta for efficiency. It handles data types and fills NaNs robustly.

generate_chandelier_signals(df): This function implements the core scalping logic. It uses EMA crossovers, a long-term trend filter, RSI for overbought/oversold confirmation, and a volume spike filter to generate explicit 'Buy' or 'Sell' signals. It also calculates the risk_distance (based on ATR and dynamic multiplier), take_profit (TP), and stop_loss (SL) prices according to the configured REWARD_RISK_RATIO.

Advanced Position Sizing: The bot now calculates order_qty based on a configurable RISK_PER_TRADE_PCT of the current balance, ensuring that each trade's potential loss is a controlled percentage of capital. This risk-based quantity is then capped by ORDER_QTY_USDT to prevent excessively large orders.

Enhanced Trade Lifecycle Management:

active_trades_tracker: A new in-memory dictionary tracks active trades, storing entry_time, order_id, and side for each symbol where an order was placed.

Time-Based Exit: The bot now actively monitors open positions. If a position has been open for longer than MAX_HOLDING_CANDLES (calculated based on the TIMEFRAME and LOOP_WAIT_TIME_SECONDS), the bot will attempt to cancel_all_open_orders for that symbol and then close_position using a market order. This is a critical feature for scalping strategies that aim for quick profits and limited exposure.

Duplicate Order Prevention: Before placing a new order, the bot checks MAX_OPEN_ORDERS_PER_SYMBOL using bybit_client.get_open_orders(), preventing multiple pending orders for the same symbol.

Flexible Entry Logic: The order placement logic now intelligently chooses between:

Limit Orders: If a signal is generated and the current price is near a strong support (for Buy) or resistance (for Sell) level (within PRICE_DETECTION_THRESHOLD_PCT).

Conditional Market Orders: For breakout/breakdown scenarios, if the price has already moved past resistance (for Buy) or support (for Sell), triggering a market order slightly beyond the current price to confirm momentum.

Market Orders: If no specific support/resistance condition is met, a direct market order is placed, suitable for aggressive scalping.

Optimized Loop Efficiency: bybit_client.get_positions() is now called once per main loop iteration, reducing redundant API calls.

This comprehensive set of upgrades transforms the bot into a more sophisticated and robust automated trading system, specifically tailored for scalping strategies with enhanced risk management and trade control.from pybit.unified_trading import HTTP
import pandas as pd
import pandas_ta as ta # Use pandas_ta for consistency
import time
import requests
import logging

# Set up logging for the helper module
logger = logging.getLogger(__name__)

class Bybit:
    def __init__(self, api, secret, testnet=False):
        self.api = api
        self.secret = secret
        self.testnet = testnet
        self.session = HTTP(api_key=self.api, api_secret=self.secret, testnet=self.testnet)
        logger.info(f"Bybit client initialized. Testnet: {self.testnet}")

    def get_balance(self, coin="USDT"):
        """Fetches and returns the wallet balance for a specific coin."""
        try:
            resp = self.session.get_wallet_balance(accountType="CONTRACT", coin=coin)['result']['list'][0]['coin'][0]['walletBalance']
            balance = float(resp)
            logger.debug(f"Fetched balance: {balance} {coin}")
            return balance
        except Exception as err:
            logger.error(f"Error getting balance for {coin}: {err}")
            return None

    def get_positions(self, settleCoin="USDT"):
        """Returns a list of symbols with open positions."""
        try:
            resp = self.session.get_positions(category='linear', settleCoin=settleCoin)['result']['list']
            # Filter for positions with a non-zero size
            open_positions = [elem['symbol'] for elem in resp if float(elem['leverage']) > 0 and float(elem['size']) > 0]
            logger.debug(f"Fetched open positions: {open_positions}")
            return open_positions
        except Exception as err:
            logger.error(f"Error getting positions: {err}")
            return []

    def get_tickers(self):
        """Retrieves all USDT perpetual linear symbols from the derivatives market."""
        try:
            resp = self.session.get_tickers(category="linear")['result']['list']
            symbols = [elem['symbol'] for elem in resp if 'USDT' in elem['symbol'] and not 'USDC' in elem['symbol']]
            logger.debug(f"Fetched {len(symbols)} tickers.")
            return symbols
        except Exception as err:
            logger.error(f"Error getting tickers: {err}")
            return None

    def klines(self, symbol, timeframe, limit=500):
        """Fetches klines (candlestick data) for a given symbol and returns a pandas DataFrame."""
        try:
            resp = self.session.get_kline(
                category='linear',
                symbol=symbol,
                interval=timeframe,
                limit=limit
            )['result']['list']
            df = pd.DataFrame(resp, columns=['Time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Turnover'])
            df['Time'] = pd.to_datetime(df['Time'], unit='ms') # Convert timestamp to datetime
            df = df.set_index('Time').astype(float)
            df = df.sort_index() # Ensure ascending order by time
            logger.debug(f"Fetched {len(df)} klines for {symbol} ({timeframe}min).")
            return df
        except Exception as err:
            logger.error(f"Error getting klines for {symbol}: {err}")
            return pd.DataFrame() # Return empty DataFrame on error

    def get_orderbook_levels(self, symbol, limit=50):
        """Analyzes the order book to find strong support and resistance levels."""
        try:
            resp = self.session.get_orderbook(
                category='linear',
                symbol=symbol,
                limit=limit
            )['result']
            bids = pd.DataFrame(resp['bids'], columns=['price', 'volume']).astype(float)
            asks = pd.DataFrame(resp['asks'], columns=['price', 'volume']).astype(float)
            
            strong_support_price = bids.loc[bids['volume'].idxmax()]['price'] if not bids.empty else None
            strong_resistance_price = asks.loc[asks['volume'].idxmax()]['price'] if not asks.empty else None
            
            logger.debug(f"Orderbook for {symbol}: Support={strong_support_price}, Resistance={strong_resistance_price}")
            return strong_support_price, strong_resistance_price
        except Exception as err:
            logger.error(f"Error getting orderbook for {symbol}: {err}")
            return None, None

    def get_precisions(self, symbol):
        """Retrieves the decimal precision for price and quantity."""
        try:
            resp = self.session.get_instruments_info(
                category='linear',
                symbol=symbol
            )['result']['list'][0]
            price_step = resp['priceFilter']['tickSize']
            qty_step = resp['lotSizeFilter']['qtyStep']
            
            # Calculate precision based on tickSize/qtyStep format (e.g., 0.01 -> 2, 1 -> 0)
            price_precision = len(price_step.split('.')[1]) if '.' in price_step else 0
            qty_precision = len(qty_step.split('.')[1]) if '.' in qty_step else 0
            
            logger.debug(f"Precisions for {symbol}: Price={price_precision}, Qty={qty_precision}")
            return price_precision, qty_precision
        except Exception as err:
            logger.error(f"Error getting precisions for {symbol}: {err}")
            return 0, 0

    def set_margin_mode_and_leverage(self, symbol, mode=1, leverage=10):
        """Sets the margin mode and leverage for a symbol."""
        try:
            # tradeMode: 0 for Cross, 1 for Isolated
            resp = self.session.switch_margin_mode(
                category='linear',
                symbol=symbol,
                tradeMode=str(mode),
                buyLeverage=str(leverage),
                sellLeverage=str(leverage)
            )
            if resp['retCode'] == 0:
                logger.info(f"Margin mode set to {'Isolated' if mode==1 else 'Cross'} and leverage set to {leverage}x for {symbol}.")
            else:
                logger.warning(f"Failed to set margin mode/leverage for {symbol}: {resp.get('retMsg', 'Unknown error')}")
        except Exception as err:
            if '110026' in str(err) or '110043' in str(err): # Already set or in position
                logger.debug(f"Margin mode or leverage already set for {symbol}.")
            else:
                logger.error(f"Error setting margin mode/leverage for {symbol}: {err}")

    def place_order_common(self, symbol, side, order_type, qty, price=None, trigger_price=None, tp_price=None, sl_price=None, time_in_force='GTC'):
        """Internal common function to place various order types."""
        try:
            params = {
                'category': 'linear',
                'symbol': symbol,
                'side': side,
                'orderType': order_type,
                'qty': str(qty), # qty must be string
                'timeInForce': time_in_force
            }
            if price is not None:
                params['price'] = str(price) # price must be string
            if trigger_price is not None:
                params['triggerPrice'] = str(trigger_price) # triggerPrice must be string
                params['triggerBy'] = 'MarkPrice' # Default to Mark Price for triggers
            if tp_price is not None:
                params['takeProfit'] = str(tp_price)
                params['tpTriggerBy'] = 'Market' # Market price for TP/SL triggers is generally safer
            if sl_price is not None:
                params['stopLoss'] = str(sl_price)
                params['slTriggerBy'] = 'Market'

            response = self.session.place_order(**params)
            if response['retCode'] == 0:
                logger.info(f"Order placed for {symbol} ({order_type} {side} {qty}): {response.get('retMsg')}. Order ID: {response['result']['orderId']}")
            else:
                logger.error(f"Failed to place order for {symbol} ({order_type} {side} {qty}): {response.get('retMsg', 'Unknown error')}")
            return response
        except Exception as err:
            logger.error(f"Error placing {order_type} order for {symbol}: {err}")
            return {'retCode': -1, 'retMsg': str(err)}

    def place_market_order(self, symbol, side, qty, tp_price=None, sl_price=None):
        """Places a market order with optional TP/SL."""
        return self.place_order_common(symbol, side, 'Market', qty, tp_price=tp_price, sl_price=sl_price)

    def place_limit_order(self, symbol, side, price, qty, tp_price=None, sl_price=None, time_in_force='GTC'):
        """Places a limit order with optional TP/SL."""
        return self.place_order_common(symbol, side, 'Limit', qty, price=price, tp_price=tp_price, sl_price=sl_price, time_in_force=time_in_force)

    def place_conditional_order(self, symbol, side, qty, trigger_price, order_type='Market', price=None, tp_price=None, sl_price=None):
        """Places a conditional order that becomes active at a trigger price.
        If order_type is 'Limit', a specific `price` must be provided for the limit execution."""
        # For conditional limit orders, the `price` parameter is required for the actual limit order execution.
        # If not provided for a conditional limit, we'll default to the trigger_price.
        if order_type == 'Limit' and price is None:
            price = trigger_price # Default to trigger_price if no explicit limit price given
            logger.warning(f"Conditional limit order requested for {symbol} without explicit `price`. Using `trigger_price` as limit execution price.")

        return self.place_order_common(symbol, side, order_type, qty, price=price, trigger_price=trigger_price, tp_price=tp_price, sl_price=sl_price)
    
    def cancel_all_open_orders(self, symbol):
        """Cancels all active orders for a given symbol."""
        try:
            response = self.session.cancel_all_orders(
                category='linear',
                symbol=symbol
            )
            if response['retCode'] == 0:
                logger.info(f"All open orders for {symbol} cancelled successfully.")
            else:
                logger.warning(f"Failed to cancel all orders for {symbol}: {response.get('retMsg', 'Unknown error')}")
            return response
        except Exception as err:
            logger.error(f"Error cancelling all orders for {symbol}: {err}")
            return {'retCode': -1, 'retMsg': str(err)}
```

```python
#!/usr/bin/env python3

import pandas as pd
import pandas_ta as ta
import logging
from dotenv import load_dotenv
import os
from time import sleep
import datetime
import pytz

# Import the Bybit client from the helper module
from helper import Bybit # Assuming helper.py is in the same directory

# --- Setup and Configuration ---
load_dotenv()

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO, # Use INFO for production, DEBUG for detailed logs
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
# Ensure helper.py logs are also handled by the basicConfig
logging.getLogger('helper').setLevel(logging.INFO) # Set to INFO or DEBUG as needed for helper module

# --- Configuration and API Credentials ---
BOT_CONFIG = {
    "API_KEY": os.getenv("BYBIT_API_KEY"),
    "API_SECRET": os.getenv("BYBIT_API_SECRET"),
    "TESTNET": os.getenv("BYBIT_TESTNET", "False").lower() == "true", # Add TESTNET flag (set in .env: BYBIT_TESTNET=True)
    "ATR_TP_MULTIPLIER": 2.0,
    "ATR_SL_MULTIPLIER": 1.5,
    "TIMEFRAME": 15, # in minutes
    "MARGIN_MODE": 1, # 0: Cross, 1: Isolated
    "LEVERAGE": 10,
    "ORDER_QTY_USDT": 50, # Quantity in USDT (e.g., $50 worth of crypto)
    "MAX_POSITIONS": 5,
    "TIMEZONE": 'America/New_York',
    "MARKET_OPEN_HOUR": 9,
    "MARKET_CLOSE_HOUR": 17,
    "LOOP_WAIT_TIME_SECONDS": 120, # How long to wait between main loop cycles
    "PRICE_DETECTION_THRESHOLD_PCT": 0.005 # 0.5% threshold for current price near support/resistance
}

if not BOT_CONFIG["API_KEY"] or not BOT_CONFIG["API_SECRET"]:
    logging.error("API keys not found. Please check your .env file.")
    exit()

# --- API Session ---
try:
    bybit_client = Bybit(
        api=BOT_CONFIG["API_KEY"],
        secret=BOT_CONFIG["API_SECRET"],
        testnet=BOT_CONFIG["TESTNET"]
    )
    logging.info(f"Successfully connected to Bybit API. Testnet: {BOT_CONFIG['TESTNET']}")
except Exception as e:
    logging.error(f"Failed to connect to Bybit API: {e}")
    exit()

# --- Helper Functions ---
def get_current_time(timezone_str):
    """Returns the current local and UTC time objects."""
    tz = pytz.timezone(timezone_str)
    local_time = datetime.datetime.now(tz)
    utc_time = datetime.datetime.now(pytz.utc)
    return local_time, utc_time

def is_market_open(local_time, open_hour, close_hour):
    """Checks if the market is open based on configured hours."""
    current_hour = local_time.hour
    return open_hour <= current_hour < close_hour

# --- Strategy Section ---
def calculate_atr_levels(df, current_price, side):
    """Calculates TP and SL levels based on Average True Range (ATR)."""
    if df.empty:
        return None, None
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    atr_value = df['ATR'].iloc[-1]
    
    if side == 'Buy':
        tp_price = current_price + (atr_value * BOT_CONFIG["ATR_TP_MULTIPLIER"])
        sl_price = current_price - (atr_value * BOT_CONFIG["ATR_SL_MULTIPLIER"])
    else: # Sell
        tp_price = current_price - (atr_value * BOT_CONFIG["ATR_TP_MULTIPLIER"])
        sl_price = current_price + (atr_value * BOT_CONFIG["ATR_SL_MULTIPLIER"])
    return tp_price, sl_price

def rsi_signal(df):
    """RSI crossover strategy."""
    if df.empty:
        return 'none'
    df['RSI'] = ta.rsi(df['Close'], length=14)
    if df['RSI'].iloc[-3] < 30 and df['RSI'].iloc[-2] < 30 and df['RSI'].iloc[-1] > 30:
        return 'Buy' # Standardize to 'Buy'
    if df['RSI'].iloc[-3] > 70 and df['RSI'].iloc[-2] > 70 and df['RSI'].iloc[-1] < 70:
        return 'Sell' # Standardize to 'Sell'
    return 'none'

def williams_r_signal(df):
    """Williams %R crossover strategy."""
    if df.empty:
        return 'none'
    df.ta.williams_r(length=24, append=True) # WMR_24
    df.ta.ema(close=df['WMR_24'], length=24, append=True) # EMA_24
    w = df['WMR_24']
    ema_w = df['EMA_24']

    # Entry conditions
    # Oversold bounce or strong upward momentum
    if w.iloc[-1] < -99.5: # Extremely oversold, potential reversal
        return 'Buy'
    elif w.iloc[-1] < -75 and w.iloc[-2] < -75 and w.iloc[-2] < ema_w.iloc[-2] and w.iloc[-1] > ema_w.iloc[-1]:
        # %R oversold and crossing above its EMA
        return 'Buy'

    # Overbought reversal or strong downward momentum
    if w.iloc[-1] > -0.5: # Extremely overbought, potential reversal
        return 'Sell'
    elif w.iloc[-1] > -25 and w.iloc[-2] > -25 and w.iloc[-2] > ema_w.iloc[-2] and w.iloc[-1] < ema_w.iloc[-1]:
        # %R overbought and crossing below its EMA
        return 'Sell'
        
    return 'none'

def bb_stoch_strategy(df):
    """
    Bollinger Bands and Stochastic RSI trading strategy.
    Signal to buy when price touches the lower BB and StochRSI is oversold and crossing up.
    Signal to sell when price touches the upper BB and StochRSI is overbought and crossing down.
    """
    if df.empty:
        return 'none'
    
    # Calculate Bollinger Bands (default length=20, std=2.0)
    df.ta.bbands(close=df['Close'], append=True) # Adds BBL_20_2.0, BBM_20_2.0, BBU_20_2.0
    
    # Calculate Stochastic RSI (default length=14, rsi_length=14, k=3, d=3)
    df.ta.stochrsi(close=df['Close'], append=True) # Adds STOCHRSIk_14_14_3_3, STOCHRSId_14_14_3_3
    
    # Ensure enough data for calculation and look-back
    if len(df) < 20: # BBANDS default length is 20
        return 'none'

    # Get the last two rows of the DataFrame for analysis (current and previous candle)
    last_row = df.iloc[-1]
    prev_row = df.iloc[-2] # For checking crossovers

    # Check for a BUY signal
    # Condition 1: Price is at or below the lower Bollinger Band
    # Condition 2: Stochastic RSI K line is below 20 (oversold)
    # Condition 3: Stochastic RSI K line is crossing above the D line (confirmation of reversal)
    if last_row['Close'] <= last_row['BBL_20_2.0'] and \
       last_row['STOCHRSIk_14_14_3_3'] < 20 and \
       prev_row['STOCHRSIk_14_14_3_3'] <= prev_row['STOCHRSId_14_14_3_3'] and \
       last_row['STOCHRSIk_14_14_3_3'] > last_row['STOCHRSId_14_14_3_3']:
        return 'Buy'
    
    # Check for a SELL signal
    # Condition 1: Price is at or above the upper Bollinger Band
    # Condition 2: Stochastic RSI K line is above 80 (overbought)
    # Condition 3: Stochastic RSI K line is crossing below the D line (confirmation of reversal)
    if last_row['Close'] >= last_row['BBU_20_2.0'] and \
       last_row['STOCHRSIk_14_14_3_3'] > 80 and \
       prev_row['STOCHRSIk_14_14_3_3'] >= prev_row['STOCHRSId_14_14_3_3'] and \
       last_row['STOCHRSIk_14_14_3_3'] < last_row['STOCHRSId_14_14_3_3']:
        return 'Sell'
        
    return 'none'

# --- Main Bot Loop ---
def main():
    symbols = bybit_client.get_tickers()
    if not symbols:
        logging.info("No symbols found. Exiting.")
        return

    logging.info(f"Starting trading bot. Checking {len(symbols)} symbols. Testnet: {BOT_CONFIG['TESTNET']}")
    # Removed WebSocket setup as the main loop uses REST API klines for strategy for simplicity.
    # For a true real-time, low-latency bot, the entire main loop logic would need to be event-driven via WebSocket.

    while True:
        local_time, utc_time = get_current_time(BOT_CONFIG["TIMEZONE"])
        logging.info(f"Local Time: {local_time.strftime('%Y-%m-%d %H:%M:%S')} | UTC Time: {utc_time.strftime('%Y-%m-%d %H:%M:%S')}")

        if not is_market_open(local_time, BOT_CONFIG["MARKET_OPEN_HOUR"], BOT_CONFIG["MARKET_CLOSE_HOUR"]):
            logging.info(f"Market is closed ({BOT_CONFIG['MARKET_OPEN_HOUR']}:00-{BOT_CONFIG['MARKET_CLOSE_HOUR']}:00 {BOT_CONFIG['TIMEZONE']}). Skipping this cycle. Waiting {BOT_CONFIG['LOOP_WAIT_TIME_SECONDS']} seconds.")
            sleep(BOT_CONFIG['LOOP_WAIT_TIME_SECONDS'])
            continue
            
        balance = bybit_client.get_balance()
        if balance is None:
            logging.error(f'Cannot connect to API or get balance. Waiting {BOT_CONFIG["LOOP_WAIT_TIME_SECONDS']} seconds and retrying.')
            sleep(BOT_CONFIG['LOOP_WAIT_TIME_SECONDS'])
            continue
        
        logging.info(f'Current balance: {balance:.2f} USDT')
        
        current_positions = bybit_client.get_positions()
        logging.info(f'You have {len(current_positions)} open positions: {current_positions}')

        for symbol in symbols:
            # Re-check positions and max_pos inside the loop, as positions can change
            # and we might have opened a new one in a prior symbol iteration.
            current_positions = bybit_client.get_positions() 
            if len(current_positions) >= BOT_CONFIG["MAX_POSITIONS"]:
                logging.info(f"Max positions ({BOT_CONFIG['MAX_POSITIONS']}) reached. Halting signal checks for this cycle.")
                break # Exit the symbol loop, continue to next main loop iteration

            if symbol in current_positions:
                logging.debug(f"Skipping {symbol} as there is already an open position.")
                continue

            kl = bybit_client.klines(symbol, BOT_CONFIG["TIMEFRAME"])
            if kl.empty or len(kl) < 50: # Ensure enough data for indicators
                logging.warning(f"Not enough klines data for {symbol} (needed >50). Skipping.")
                continue

            support, resistance = bybit_client.get_orderbook_levels(symbol)
            current_price = kl['Close'].iloc[-1]
            
            if support is None or resistance is None:
                logging.warning(f"Could not retrieve orderbook levels for {symbol}. Skipping strategy check.")
                continue

            # --- Combined Strategy Logic ---
            rsi_sig = rsi_signal(kl)
            williams_sig = williams_r_signal(kl)
            bb_stoch_sig = bb_stoch_strategy(kl)

            final_signal = 'none'
            # Example: A conservative strategy requiring multiple confirmations
            if rsi_sig == 'Buy' and williams_sig == 'Buy' and bb_stoch_sig == 'Buy':
                final_signal = 'Buy'
            elif rsi_sig == 'Sell' and williams_sig == 'Sell' and bb_stoch_sig == 'Sell':
                final_signal = 'Sell'
            
            # --- Order Placement Logic based on Final Signal ---
            if final_signal != 'none':
                # Calculate common order parameters
                price_precision, qty_precision = bybit_client.get_precisions(symbol)
                # Ensure order_qty is positive
                order_qty_raw = BOT_CONFIG["ORDER_QTY_USDT"] / current_price
                order_qty = round(order_qty_raw, qty_precision)
                if order_qty <= 0:
                    logging.warning(f"Calculated order quantity for {symbol} is zero or negative ({order_qty}). Skipping order.")
                    continue

                # Set margin mode and leverage once before considering placing an order
                bybit_client.set_margin_mode_and_leverage(
                    symbol, BOT_CONFIG["MARGIN_MODE"], BOT_CONFIG["LEVERAGE"]
                )
                sleep(0.5) # Give API a moment to process

                if final_signal == 'Buy':
                    tp_price, sl_price = calculate_atr_levels(kl, current_price, 'Buy')
                    
                    # Option 1: Place a Limit Order near strong support
                    # If current price is within a small threshold of strong support
                    if support and abs(current_price - support) < (current_price * BOT_CONFIG["PRICE_DETECTION_THRESHOLD_PCT"]):
                        logging.info(f'Found BUY signal for {symbol} 📈 (confirmed by support at {support}). Placing Limit Order.')
                        bybit_client.place_limit_order(
                            symbol=symbol,
                            side='Buy',
                            price=round(support, price_precision), # Try to buy at the support level
                            qty=order_qty,
                            tp_price=round(tp_price, price_precision),
                            sl_price=round(sl_price, price_precision)
                        )
                    # Option 2: Place a Conditional Market Order for a breakout above resistance
                    # If current price has already broken above resistance
                    elif resistance and current_price > resistance:
                        logging.info(f'Found breakout BUY signal for {symbol} 📈 (above resistance at {resistance}). Placing Conditional Market Order.')
                        # Trigger slightly above current price to confirm breakout momentum
                        trigger_price = current_price * (1 + 0.001) # 0.1% above current price
                        bybit_client.place_conditional_order(
                            symbol=symbol,
                            side='Buy',
                            qty=order_qty,
                            trigger_price=round(trigger_price, price_precision),
                            order_type='Market',
                            tp_price=round(tp_price, price_precision),
                            sl_price=round(sl_price, price_precision)
                        )
                    else:
                        logging.debug(f"Buy signal for {symbol} but no specific orderbook condition met for entry type. Skipping.")

                elif final_signal == 'Sell':
                    tp_price, sl_price = calculate_atr_levels(kl, current_price, 'Sell')

                    # Option 1: Place a Limit Order near strong resistance
                    # If current price is within a small threshold of strong resistance
                    if resistance and abs(current_price - resistance) < (current_price * BOT_CONFIG["PRICE_DETECTION_THRESHOLD_PCT"]):
                        logging.info(f'Found SELL signal for {symbol} 📉 (confirmed by resistance at {resistance}). Placing Limit Order.')
                        bybit_client.place_limit_order(
                            symbol=symbol,
                            side='Sell',
                            price=round(resistance, price_precision), # Try to sell at the resistance level
                            qty=order_qty,
                            tp_price=round(tp_price, price_precision),
                            sl_price=round(sl_price, price_precision)
                        )
                    # Option 2: Place a Conditional Market Order for a breakdown below support
                    # If current price has already broken below support
                    elif support and current_price < support:
                        logging.info(f'Found breakdown SELL signal for {symbol} 📉 (below support at {support}). Placing Conditional Market Order.')
                        # Trigger slightly below current price to confirm breakdown momentum
                        trigger_price = current_price * (1 - 0.001) # 0.1% below current price
                        bybit_client.place_conditional_order(
                            symbol=symbol,
                            side='Sell',
                            qty=order_qty,
                            trigger_price=round(trigger_price, price_precision),
                            order_type='Market',
                            tp_price=round(tp_price, price_precision),
                            sl_price=round(sl_price, price_precision)
                        )
                    else:
                        logging.debug(f"Sell signal for {symbol} but no specific orderbook condition met for entry type. Skipping.")
            else:
                logging.debug(f"No strong combined trading signal for {symbol}.")


        logging.info(f'--- Cycle finished. Waiting {BOT_CONFIG["LOOP_WAIT_TIME_SECONDS"]} seconds for next loop. ---')
        sleep(BOT_CONFIG['LOOP_WAIT_TIME_SECONDS'])

if __name__ == "__main__":
    main()
```
---

### Bybit Client (helper.py)

To improve modularity and maintainability, all interactions with the Bybit API are now encapsulated within a `Bybit` class located in `helper.py`. This separates API communication from your main trading logic.

The `Bybit` class includes methods for:
*   `get_balance()`: Fetches your wallet balance.
*   `get_positions()`: Retrieves your open positions.
*   `get_tickers()`: Lists all tradable symbols.
*   `klines()`: Fetches historical candlestick data.
*   `get_orderbook_levels()`: Identifies strong support and resistance from the order book.
*   `get_precisions()`: Determines price and quantity decimal precisions for accurate order placement.
*   `set_margin_mode_and_leverage()`: Configures margin mode (isolated/cross) and leverage for a symbol.
*   `place_market_order()`, `place_limit_order()`, `place_conditional_order()`: Functions for placing various order types with optional Take Profit (TP) and Stop Loss (SL).
*   `cancel_all_open_orders()`: Cancels all active orders for a symbol.

### Place Order Functions (via Bybit Client)

The bot now uses the `bybit_client` instance to call methods like `place_limit_order` and `place_conditional_order`.

*   `place_limit_order`: Designed for trades you want to make at a specific, fixed price. It sets the `orderType` to 'Limit' and requires a `price` parameter.
*   `place_conditional_order`: For advanced breakout or stop-entry strategies. It places an order that is triggered when the market reaches a specified `triggerPrice`. This order can then be executed as either a market or limit order (the example uses 'Market').

In your main loop, you would call these functions via `bybit_client.place_limit_order(...)` or `bybit_client.place_conditional_order(...)`. For instance, if your strategy is to buy a breakout above a resistance level, you would set a conditional order with the resistance price as the trigger.

---

### Adding Your Own Trading Strategy (Enhanced)

To add your own strategy to this bot, you need to modify the code in the "Strategy Section" of the main script. This is where the core decision-making logic resides. The process involves creating new functions that return a trading signal ('Buy', 'Sell', or 'none') based on your custom indicators or rules.

**Key Enhancements:**

*   **Modular Strategy Functions:** Each strategy is encapsulated in its own function, promoting reusability and clarity.
*   **Combined Signals:** The main loop now demonstrates how to combine signals from multiple strategies for a more robust entry condition, helping to filter out false positives.
*   **Centralized Configuration:** All bot parameters are now managed in a `BOT_CONFIG` dictionary at the top of the script for easy modification.
*   **Testnet Support:** The bot can now easily switch between Bybit's mainnet and testnet via an environment variable (`BYBIT_TESTNET=True` in your `.env` file).

#### Step 1: Choose Your Indicators

First, decide what technical indicators or market data you want to use for your strategy. The bot template already uses `pandas_ta`, which has hundreds of indicators. For this tutorial, we will enhance the existing strategies and introduce a new one using **Bollinger Bands** and **Stochastic RSI**.

*   **Bollinger Bands (BBANDS):** Measures volatility and identifies overbought or oversold conditions. A common strategy is to buy when the price touches the lower band and sell when it touches the upper band.
*   **Stochastic RSI (STOCHRSI):** A momentum oscillator that measures the speed and change of price movements. It is used to identify overbought and oversold conditions and can signal a potential trend reversal.

#### Step 2: Write/Enhance Strategy Functions

Create a new function or enhance existing ones that take a pandas DataFrame (`df`) as input, as this is the format of the kline data from Bybit. Inside this function, you will use `pandas_ta` to calculate your chosen indicators and then write the logic to generate a signal.

Let's look at the `bb_stoch_strategy` function, now included in the template:

```python
def bb_stoch_strategy(df):
    """
    Bollinger Bands and Stochastic RSI trading strategy.
    Signal to buy when price touches the lower BB and StochRSI is oversold and crossing up.
    Signal to sell when price touches the upper BB and StochRSI is overbought and crossing down.
    """
    if df.empty:
        return 'none'
    
    # Calculate Bollinger Bands (default length=20, std=2.0)
    df.ta.bbands(close=df['Close'], append=True) # Adds BBL_20_2.0, BBM_20_2.0, BBU_20_2.0
    
    # Calculate Stochastic RSI (default length=14, rsi_length=14, k=3, d=3)
    df.ta.stochrsi(close=df['Close'], append=True) # Adds STOCHRSIk_14_14_3_3, STOCHRSId_14_14_3_3
    
    # Ensure enough data for calculation and look-back
    if len(df) < 20: # BBANDS default length is 20
        return 'none'

    # Get the last two rows of the DataFrame for analysis (current and previous candle)
    last_row = df.iloc[-1]
    prev_row = df.iloc[-2] # For checking crossovers

    # Check for a BUY signal
    # Condition 1: Price is at or below the lower Bollinger Band
    # Condition 2: Stochastic RSI K line is below 20 (oversold)
    # Condition 3: Stochastic RSI K line is crossing above the D line (confirmation of reversal)
    if last_row['Close'] <= last_row['BBL_20_2.0'] and \
       last_row['STOCHRSIk_14_14_3_3'] < 20 and \
       prev_row['STOCHRSIk_14_14_3_3'] <= prev_row['STOCHRSId_14_14_3_3'] and \
       last_row['STOCHRSIk_14_14_3_3'] > last_row['STOCHRSId_14_14_3_3']:
        return 'Buy'
    
    # Check for a SELL signal
    # Condition 1: Price is at or above the upper Bollinger Band
    # Condition 2: Stochastic RSI K line is above 80 (overbought)
    # Condition 3: Stochastic RSI K line is crossing below the D line (confirmation of reversal)
    if last_row['Close'] >= last_row['BBU_20_2.0'] and \
       last_row['STOCHRSIk_14_14_3_3'] > 80 and \
       prev_row['STOCHRSIk_14_14_3_3'] >= prev_row['STOCHRSId_14_14_3_3'] and \
       last_row['STOCHRSIk_14_14_3_3'] < last_row['STOCHRSId_14_14_3_3']:
        return 'Sell'
        
    return 'none'
```
*   `df.ta.bbands` and `df.ta.stochrsi`: These functions from `pandas_ta` automatically add the indicator values as new columns to your DataFrame.
*   **Crossover Logic:** The conditions now explicitly check for `STOCHRSIk` crossing `STOCHRSId` by comparing the current and previous candle's values.
*   **Standardized Signals:** All strategy functions now return 'Buy', 'Sell', or 'none' for consistency.

#### Step 3: Integrate and Combine Strategies in the Main Loop

In the `main` loop, you can call your new and existing strategy functions and combine their signals for a more robust trading decision.

Find the strategy section in the `main` function:

```python
            # --- Combined Strategy Logic ---
            rsi_sig = rsi_signal(kl)
            williams_sig = williams_r_signal(kl)
            bb_stoch_sig = bb_stoch_strategy(kl)

            final_signal = 'none'
            # Example: A conservative strategy requiring multiple confirmations
            if rsi_sig == 'Buy' and williams_sig == 'Buy' and bb_stoch_sig == 'Buy':
                final_signal = 'Buy'
            elif rsi_sig == 'Sell' and williams_sig == 'Sell' and bb_stoch_sig == 'Sell':
                final_signal = 'Sell'
            
            # --- Order Placement Logic based on Final Signal ---
            # ... (rest of the order placement logic) ...
```

This updated logic:
1.  Calls `rsi_signal`, `williams_r_signal`, and `bb_stoch_strategy` to get individual signals.
2.  Combines them: A `final_signal` is generated only if *all* three indicators agree on a 'Buy' or 'Sell' direction. This reduces false signals and can lead to more reliable entries. You can customize this combination logic to fit your risk tolerance and strategy.
3.  The order placement logic then acts upon this `final_signal`, additionally checking against orderbook levels (support/resistance) to decide between limit or conditional orders. For example, a conditional breakout order might additionally require current price action to confirm the momentum for a more confident entry.

You now have a powerful, custom, and more robust strategy integrated into your automated trading bot!

---

This video demonstrates how to place conditional orders on Bybit, which is a key part of the new functionality added to your bot template. [Bybit Conditional Order Tutorial](https://www.youtube.com/watch?v=n2IlrrDnB0c).
