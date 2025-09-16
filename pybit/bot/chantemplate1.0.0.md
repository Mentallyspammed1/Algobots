#!/usr/bin/env python3

# Silence specific warnings
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module='pkg_resources')

import pandas as pd
import pandas_ta as ta
import logging
import os # Still needed for os.getenv in config.py, but not directly here
from time import sleep
import datetime
import pytz
import numpy as np
import uuid
import sys

# Import from pybit
from pybit.unified_trading import HTTP

# Import BOT_CONFIG from the new config file
from config import BOT_CONFIG

# --- Custom Colored Logging Formatter ---
class ColoredFormatter(logging.Formatter):
    # Define your neon colors
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    RESET = "\033[0m"
    BOLD = "\033[1m"
    
    FORMATS = {
        logging.DEBUG: CYAN + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + RESET,
        logging.INFO: WHITE + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + RESET, # Default INFO white
        logging.WARNING: YELLOW + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + RESET,
        logging.ERROR: RED + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + RESET,
        logging.CRITICAL: BOLD + RED + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + RESET
    }

    def format(self, record):
        # Check if stdout is a TTY (supports colors)
        if sys.stdout.isatty():
            log_fmt = self.FORMATS.get(record.levelno)
        else: # No colors if not a TTY (e.g., redirected to a file)
            log_fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        
        formatter = logging.Formatter(log_fmt, datefmt='%Y-%m-%d %H:%M:%S')
        return formatter.format(record)

# --- Logging Setup ---
# This setup needs to happen before any loggers are created or used.
root_logger = logging.getLogger()
# Clear existing handlers to prevent duplicate output if basicConfig was called elsewhere
if root_logger.hasHandlers():
    root_logger.handlers.clear()

handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter())
root_logger.addHandler(handler)

# Set root logger level based on config
root_logger.setLevel(getattr(logging, BOT_CONFIG["LOG_LEVEL"]))


# --- Bybit Client Class ---
class Bybit:
    def __init__(self, api, secret, testnet=False, dry_run=False):
        if not api or not secret:
            raise ValueError("API Key and Secret must be provided.")
        self.api = api
        self.secret = secret
        self.testnet = testnet
        self.dry_run = dry_run # New: Dry run flag
        self.session = HTTP(api_key=self.api, api_secret=self.secret, testnet=self.testnet)
        logging.info(f"Bybit client initialized. Testnet: {self.testnet}, Dry Run: {self.dry_run}")

    def get_balance(self, coin="USDT"):
        """Fetches and returns the wallet balance for a specific coin."""
        try:
            resp = self.session.get_wallet_balance(accountType="UNIFIED", coin=coin)
            if resp['retCode'] == 0 and resp['result']['list']:
                balance_data_list = resp['result']['list'][0]['coin']
                if balance_data_list:
                    for coin_data in balance_data_list:
                        if coin_data['coin'] == coin:
                            balance = float(coin_data['walletBalance'])
                            logging.debug(f"Fetched balance: {balance} {coin}")
                            return balance
                    logging.warning(f"No balance data found for specified coin {coin}.")
                    return 0.0
                else:
                    logging.warning(f"No coin data found in balance list for accountType CONTRACT.")
                    return 0.0
            else:
                logging.error(f"Error getting balance for {coin}: {resp.get('retMsg', 'Unknown error')} (Code: {resp.get('retCode', 'N/A')})")
                return None
        except Exception as err:
            logging.error(f"Exception getting balance for {coin}: {err}")
            return None

    def get_positions(self, settleCoin="USDT"):
        """Returns a list of symbols with open positions."""
        try:
            resp = self.session.get_positions(category='linear', settleCoin=settleCoin)
            if resp['retCode'] == 0:
                open_positions = [elem['symbol'] for elem in resp['result']['list'] if float(elem['leverage']) > 0 and float(elem['size']) > 0]
                logging.debug(f"Fetched open positions: {open_positions}")
                return open_positions
            else:
                logging.error(f"Error getting positions: {resp.get('retMsg', 'Unknown error')} (Code: {resp.get('retCode', 'N/A')})")
                return []
        except Exception as err:
            logging.error(f"Exception getting positions: {err}")
            return []

    def get_tickers(self):
        """Retrieves all USDT perpetual linear symbols from the derivatives market."""
        try:
            resp = self.session.get_tickers(category="linear")
            if resp['retCode'] == 0:
                symbols = [elem['symbol'] for elem in resp['result']['list'] if 'USDT' in elem['symbol'] and not 'USDC' in elem['symbol']]
                logging.debug(f"Fetched {len(symbols)} tickers.")
                return symbols
            else:
                logging.error(f"Error getting tickers: {resp.get('retMsg', 'Unknown error')} (Code: {resp.get('retCode', 'N/A')})")
                return None
        except Exception as err:
            logging.error(f"Exception getting tickers: {err}")
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
                # Define dtypes for efficiency and clarity
                klines_dtypes = {
                    'Time': 'int64', # Timestamp is int before conversion
                    'Open': 'float64',
                    'High': 'float64',
                    'Low': 'float64',
                    'Close': 'float64',
                    'Volume': 'float64',
                    'Turnover': 'float64'
                }
                df = pd.DataFrame(resp['result']['list'], columns=klines_dtypes.keys()).astype(klines_dtypes)
                df['Time'] = pd.to_datetime(df['Time'], unit='ms') # Convert timestamp to datetime
                df = df.set_index('Time')
                df = df.sort_index() # Ensure ascending order by time
                
                # Check for critical NaN values after conversion
                if df[['Open', 'High', 'Low', 'Close']].isnull().all().any():
                    logging.warning(f"Critical OHLCV columns are all NaN for {symbol}. Skipping this kline data.")
                    return pd.DataFrame() # Return empty DataFrame if data is bad
                logging.debug(f"Fetched {len(df)} klines for {symbol} ({timeframe}min).")
                return df
            else:
                logging.error(f"Error getting klines for {symbol}: {resp.get('retMsg', 'Unknown error')} (Code: {resp.get('retCode', 'N/A')})")
                return pd.DataFrame()
        except Exception as err:
            logging.error(f"Exception getting klines for {symbol}: {err}")
            return pd.DataFrame() # Return empty DataFrame on error

    def get_orderbook_levels(self, symbol, limit=50):
        """Analyzes the order book to find strong support and resistance levels."""
        try:
            resp = self.session.get_orderbook(
                category='linear',
                symbol=symbol,
                limit=limit
            )
            if resp['retCode'] == 0 and 'result' in resp and 'b' in resp['result'] and 'a' in resp['result']:
                bids = pd.DataFrame(resp['result']['b'], columns=['price', 'volume']).astype(float)
                asks = pd.DataFrame(resp['result']['a'], columns=['price', 'volume']).astype(float)
                
                strong_support_price = bids.loc[bids['volume'].idxmax()]['price'] if not bids.empty else None
                strong_resistance_price = asks.loc[asks['volume'].idxmax()]['price'] if not asks.empty else None
                
                logging.debug(f"Orderbook for {symbol}: Support={strong_support_price}, Resistance={strong_resistance_price}")
                return strong_support_price, strong_resistance_price
            else:
                logging.error(f"Error getting orderbook for {symbol}: Invalid response format or {resp.get('retMsg', 'Unknown error')} (Code: {resp.get('retCode', 'N/A')})")
                return None, None
        except Exception as err:
            logging.error(f"Exception getting orderbook for {symbol}: {err}")
            return None, None

    def get_precisions(self, symbol):
        """Retrieves the decimal precision for price and quantity."""
        try:
            resp = self.session.get_instruments_info(
                category='linear',
                symbol=symbol
            )
            if resp['retCode'] == 0 and resp['result']['list']:
                info = resp['result']['list'][0] # Access the first element of the list
                price_step = info['priceFilter']['tickSize']
                qty_step = info['lotSizeFilter']['qtyStep']
                
                # Calculate precision based on tickSize/qtyStep format (e.g., 0.01 -> 2, 1 -> 0)
                price_precision = len(price_step.split('.')[1]) if '.' in price_step and len(price_step.split('.')) > 1 else 0
                qty_precision = len(qty_step.split('.')[1]) if '.' in qty_step and len(qty_step.split('.')) > 1 else 0
                
                logging.debug(f"Precisions for {symbol}: Price={price_precision}, Qty={qty_precision}")
                return price_precision, qty_precision
            else:
                logging.error(f"Error getting precisions for {symbol}: {resp.get('retMsg', 'Unknown error')} (Code: {resp.get('retCode', 'N/A')})")
                return 0, 0
        except Exception as err:
            logging.error(f"Exception getting precisions for {symbol}: {err}")
            return 0, 0

    def set_margin_mode_and_leverage(self, symbol, mode=1, leverage=10):
        """Sets the margin mode and leverage for a symbol."""
        if self.dry_run:
            logging.info(f"[DRY RUN] Would set margin mode to {'Isolated' if mode==1 else 'Cross'} and leverage to {leverage}x for {symbol}.")
            return
        
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
                logging.info(f"Margin mode set to {'Isolated' if mode==1 else 'Cross'} and leverage set to {leverage}x for {symbol}.")
            elif resp['retCode'] == 110026 or resp['retCode'] == 110043: # Already set or in position
                logging.debug(f"Margin mode or leverage already set for {symbol} (Code: {resp['retCode']}).")
            else:
                logging.warning(f"Failed to set margin mode/leverage for {symbol}: {resp.get('retMsg', 'Unknown error')} (Code: {resp['retCode']})")
        except Exception as err:
            if '110026' in str(err) or '110043' in str(err): # Already set or in position
                logging.debug(f"Margin mode or leverage already set for {symbol}.")
            else:
                logging.error(f"Exception setting margin mode/leverage for {symbol}: {err}")

    def place_order_common(self, symbol, side, order_type, qty, price=None, trigger_price=None, tp_price=None, sl_price=None, time_in_force='GTC'):
        """Internal common function to place various order types."""
        if self.dry_run:
            dummy_order_id = f"DRY_RUN_ORDER_{uuid.uuid4()}"
            log_msg = f"[DRY RUN] Would place order for {symbol} ({order_type} {side} {qty})"
            if price: log_msg += f" at price {price}"
            if trigger_price: log_msg += f" triggered by {trigger_price}"
            if tp_price: log_msg += f" with TP {tp_price}"
            if sl_price: log_msg += f" and SL {sl_price}"
            logging.info(f"{log_msg}. Simulated Order ID: {dummy_order_id}")
            return dummy_order_id # Simulate success
        
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
                logging.info(f"Order placed for {symbol} ({order_type} {side} {qty}). Order ID: {response['result']['orderId']}")
                return response['result']['orderId']
            else:
                logging.error(f"Failed to place order for {symbol} ({order_type} {side} {qty}): {response.get('retMsg', 'Unknown error')} (Code: {response['retCode']})")
                return None
        except Exception as err:
            logging.error(f"Exception placing {order_type} order for {symbol}: {err}")
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
        if order_type == 'Limit' and price is None:
            price = trigger_price # Default to trigger_price if no explicit limit price given
            logging.warning(f"Conditional limit order requested for {symbol} without explicit `price`. Using `trigger_price` as limit execution price.")

        return self.place_order_common(symbol, side, order_type, qty, price=price, trigger_price=trigger_price, tp_price=tp_price, sl_price=sl_price)
    
    def cancel_all_open_orders(self, symbol):
        """Cancels all active orders for a given symbol."""
        if self.dry_run:
            logging.info(f"[DRY RUN] Would cancel all open orders for {symbol}.")
            return {'retCode': 0, 'retMsg': 'OK'} # Simulate success
        
        try:
            response = self.session.cancel_all_orders(
                category='linear',
                symbol=symbol
            )
            if response['retCode'] == 0:
                logging.info(f"All open orders for {symbol} cancelled successfully.")
            else:
                logging.warning(f"Failed to cancel all orders for {symbol}: {response.get('retMsg', 'Unknown error')} (Code: {response['retCode']})")
            return response
        except Exception as err:
            logging.error(f"Exception cancelling all orders for {symbol}: {err}")
            return {'retCode': -1, 'retMsg': str(err)}

    def get_open_orders(self, symbol=None):
        """Retrieves all active orders for a given symbol, or all symbols if none specified."""
        # This method should still function in dry run to get a realistic view of "open" orders
        # if the dry run logic needs to simulate them. For now, it will always query the API.
        try:
            params = {'category': 'linear'}
            if symbol:
                params['symbol'] = symbol
            
            response = self.session.get_open_orders(**params)
            if response['retCode'] == 0:
                open_orders = response['result']['list']
                logging.debug(f"Fetched {len(open_orders)} open orders for {symbol if symbol else 'all symbols'}.")
                return open_orders
            else:
                logging.error(f"Error getting open orders for {symbol if symbol else 'all symbols'}: {response.get('retMsg', 'Unknown error')} (Code: {response['retCode']})")
                return []
        except Exception as err:
            logging.error(f"Exception getting open orders for {symbol if symbol else 'all symbols'}: {err}")
            return []

    def close_position(self, symbol, position_idx=0):
        """
        Closes an open position for a given symbol using a market order.
        position_idx: 0 for one-way mode, 1 for buy side, 2 for sell side in hedge mode.
        """
        if self.dry_run:
            logging.info(f"[DRY RUN] Would close position for {symbol} with a market order.")
            return f"DRY_RUN_CLOSE_ORDER_{uuid.uuid4()}" # Simulate success
            
        try:
            # First, get current position details to determine side and size
            positions_resp = self.session.get_positions(category='linear', symbol=symbol)
            if positions_resp['retCode'] != 0 or not positions_resp['result']['list']:
                logging.warning(f"Could not get position details for {symbol} to close. {positions_resp.get('retMsg', 'No position found')}")
                return None

            position_info = None
            for pos in positions_resp['result']['list']:
                if float(pos['size']) > 0: # Found an open position
                    position_info = pos
                    break
            
            if not position_info:
                logging.info(f"No open position found for {symbol} to close (size is 0).")
                return None

            current_side = position_info['side']
            current_size = float(position_info['size'])
            
            if current_size == 0:
                logging.info(f"No open position found for {symbol} to close (size is 0).")
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
                logging.info(f"Market order placed to close {symbol} position ({current_side} {current_size}). Order ID: {response['result']['orderId']}")
                return response['result']['orderId']
            else:
                logging.error(f"Failed to place market order to close {symbol} position: {response.get('retMsg', 'Unknown error')} (Code: {response['retCode']})")
                return None
        except Exception as err:
            logging.error(f"Exception closing position for {symbol}: {err}")
            return None


# --- API Session ---
# Check for API keys from BOT_CONFIG, which now gets them from .env
if not BOT_CONFIG["API_KEY"] or not BOT_CONFIG["API_SECRET"]:
    logging.error("API keys not found. Please check your .env file.")
    exit()

try:
    bybit_client = Bybit(
        api=BOT_CONFIG["API_KEY"],
        secret=BOT_CONFIG["API_SECRET"],
        testnet=BOT_CONFIG["TESTNET"],
        dry_run=BOT_CONFIG["DRY_RUN"] # Pass dry_run flag to client
    )
    mode_info = f"{ColoredFormatter.MAGENTA}{ColoredFormatter.BOLD}DRY RUN{ColoredFormatter.RESET}" if BOT_CONFIG["DRY_RUN"] else f"{ColoredFormatter.GREEN}{ColoredFormatter.BOLD}LIVE{ColoredFormatter.RESET}"
    testnet_info = f"{ColoredFormatter.YELLOW}TESTNET{ColoredFormatter.RESET}" if BOT_CONFIG["TESTNET"] else f"{ColoredFormatter.BLUE}MAINNET{ColoredFormatter.RESET}"
    logging.info(f"Successfully connected to Bybit API in {mode_info} mode on {testnet_info}.")
    logging.debug(f"Bot configuration: {BOT_CONFIG}") # Log full config at DEBUG level
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
    """Checks if the market is open based on configured hours, handling overnight closures."""
    current_hour = local_time.hour
    # Convert to int to ensure proper comparison
    open_hour_int = int(open_hour)
    close_hour_int = int(close_hour)

    # Handle overnight market closure (e.g., open 22:00, close 06:00 next day)
    if open_hour_int < close_hour_int:
        # Normal daily closure (e.g., open 09:00, close 17:00)
        return open_hour_int <= current_hour < close_hour_int
    else:
        # Overnight closure (e.g., open 04:00, close 03:00 next day, meaning closed from 03:00 to 04:00)
        # Market is open if current_hour is >= open_hour_int OR current_hour is < close_hour_int
        return current_hour >= open_hour_int or current_hour < close_hour_int

# --- Strategy Section (Chandelier Exit Scalping Logic) ---
def calculate_chandelier_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate Chandelier Exit, EMAs, RSI, and volume indicators for scalping.
    Uses pandas_ta for efficiency.
    """
    df = df.copy()
    
    # Ensure columns are float and fill NaNs immediately for critical columns
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
        # Fill NaNs with previous valid observation, then with 0 if still NaN
        df[col] = df[col].ffill().fillna(0)

    # Calculate ATR
    atr_series = ta.atr(high=df['High'], low=df['Low'], close=df['Close'], length=BOT_CONFIG["ATR_PERIOD"])
    df['atr'] = atr_series.rename(f'ATR_{BOT_CONFIG["ATR_PERIOD"]}') # Ensure consistent naming, though pandas_ta usually does this
    # Handle cases where ATR might be all NaNs due to insufficient data or other issues
    if df['atr'].isnull().all():
        logging.warning(f"ATR_14 column is all NaNs for {df.index.name}. This might indicate insufficient data or problematic input.")
        # Optionally, you could return an empty DataFrame or raise an error here if ATR is critical.
        # For now, we'll let the subsequent checks handle invalid ATR values.

    # Calculate highest high and lowest low for Chandelier Exit
    df['highest_high'] = df['High'].rolling(window=BOT_CONFIG["ATR_PERIOD"]).max()
    df['lowest_low'] = df['Low'].rolling(window=BOT_CONFIG["ATR_PERIOD"]).min()
    
    # Dynamic ATR multiplier (using a 20-period std of ATR for volatility)
    # Ensure enough data for volatility calculation
    if len(df) >= 20:
        df['volatility'] = df['atr'].rolling(window=20).std()
        # Handle cases where volatility might be zero or NaN
        mean_volatility = df['volatility'].mean()
        if mean_volatility > 0 and not pd.isna(mean_volatility):
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
    trend_ema_series = ta.ema(close=df['Close'], length=BOT_CONFIG["TREND_EMA_PERIOD"])
    df['trend_ema'] = trend_ema_series
    
    # EMAs for entries
    ema_short_series = ta.ema(close=df['Close'], length=BOT_CONFIG["EMA_SHORT_PERIOD"])
    df['ema_short'] = ema_short_series
    ema_long_series = ta.ema(close=df['Close'], length=BOT_CONFIG["EMA_LONG_PERIOD"])
    df['ema_long'] = ema_long_series
    
    # RSI
    rsi_series = ta.rsi(close=df['Close'], length=BOT_CONFIG["RSI_PERIOD"])
    df['rsi'] = rsi_series
    
    # Volume filter
    volume_ma_series = ta.sma(close=df['Volume'], length=20) # 20-period SMA for volume
    df['volume_ma'] = volume_ma_series
    df['volume_spike'] = (df['Volume'] / df['volume_ma']) > BOT_CONFIG["VOLUME_THRESHOLD_MULTIPLIER"]
    
    # Clean up temporary columns and fill NaNs
    df = df.drop(columns=[col for col in df.columns if ('ATR_' in col or 'EMA_' in col or 'RSI_' in col or 'SMA_' in col) and col not in ['atr', 'ema_short', 'ema_long', 'trend_ema', 'rsi', 'volume_ma']], errors='ignore')
    df = df.ffill().fillna(0) # Fill NaNs forward, then with 0

    # Final check for critical indicator columns after all calculations and NaNs filling
    critical_indicator_cols = ['atr', 'dynamic_multiplier', 'chandelier_long', 'chandelier_short', 'trend_ema', 'ema_short', 'ema_long', 'rsi', 'volume_ma']
    for col in critical_indicator_cols:
        if col not in df.columns or df[col].isnull().all():
            logging.warning(f"Critical indicator column '{col}' is missing or all NaNs after calculation for {df.index.name}. Strategy data not fully populated.")
            return pd.DataFrame() # Return empty DataFrame if critical data is missing

    return df

def generate_chandelier_signals(df: pd.DataFrame):
    """
    Generate explicit long and short signals based on Chandelier Exit Scalping Strategy.
    Returns 'Buy', 'Sell', or 'none', along with calculated risk distance, TP, SL, dynamic multiplier, and the full DataFrame with indicators.
    """
    # Ensure enough data for all indicators, including lookback periods for EMA, ATR, RSI, and Volume MA
    min_required_klines = max(BOT_CONFIG["MIN_KLINES_FOR_STRATEGY"], BOT_CONFIG["TREND_EMA_PERIOD"], 
                              BOT_CONFIG["EMA_LONG_PERIOD"], BOT_CONFIG["ATR_PERIOD"], 
                              BOT_CONFIG["RSI_PERIOD"], 20) # 20 for Volume MA and volatility std
    
    if df.empty or len(df) < min_required_klines:
        logging.debug(f"Not enough data for Chandelier Exit strategy indicators (needed >{min_required_klines}, got {len(df)}).")
        return 'none', None, None, None, None, df # signal, risk, tp, sl, dynamic_multiplier, df_with_indicators

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
        return 'none', None, None, None, None, df_with_indicators

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
    
    return signal, risk_distance, tp_price, sl_price, dynamic_multiplier, df_with_indicators


# --- Main Bot Loop ---
def main():
    symbols = BOT_CONFIG["TRADING_SYMBOLS"]
    if not symbols:
        logging.info("No symbols configured. Exiting.")
        return

    mode_info = f"{ColoredFormatter.MAGENTA}{ColoredFormatter.BOLD}DRY RUN{ColoredFormatter.RESET}" if BOT_CONFIG["DRY_RUN"] else f"{ColoredFormatter.GREEN}{ColoredFormatter.BOLD}LIVE{ColoredFormatter.RESET}"
    testnet_info = f"{ColoredFormatter.YELLOW}TESTNET{ColoredFormatter.RESET}" if BOT_CONFIG["TESTNET"] else f"{ColoredFormatter.BLUE}MAINNET{ColoredFormatter.RESET}"
    logging.info(f"Starting trading bot in {mode_info} mode on {testnet_info}. Checking {len(symbols)} symbols.")

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
            logging.error(f'Cannot connect to API or get balance. Waiting {BOT_CONFIG["LOOP_WAIT_TIME_SECONDS"]} seconds and retrying.')
            sleep(BOT_CONFIG['LOOP_WAIT_TIME_SECONDS'])
            continue
        
        logging.info(f'Current balance: {balance:.2f} USDT')
        
        current_positions = bybit_client.get_positions()
        logging.info(f'You have {len(current_positions)} open positions: {current_positions}')

        # --- Manage existing trades (time-based exit) ---
        symbols_to_remove_from_tracker = []
        for symbol, trade_info in active_trades_tracker.items():
            # In dry run, we simulate positions being open. In live, we check actual positions.
            if not BOT_CONFIG["DRY_RUN"] and symbol not in current_positions:
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
            final_signal, risk_distance, tp_price, sl_price, dynamic_multiplier, df_with_indicators = generate_chandelier_signals(kl) # Capture df_with_indicators

            # Extract current indicator values for logging (always display)
            last_row_indicators = df_with_indicators.iloc[-1]
            log_details = (
                f"Current Price: {ColoredFormatter.WHITE}{current_price:.4f}{ColoredFormatter.RESET} | "
                f"ATR ({BOT_CONFIG['ATR_PERIOD']}): {ColoredFormatter.CYAN}{last_row_indicators['atr']:.4f}{ColoredFormatter.RESET} | "
                f"Dynamic Multiplier: {ColoredFormatter.CYAN}{last_row_indicators['dynamic_multiplier']:.2f}{ColoredFormatter.RESET} | "
                f"EMA Short ({BOT_CONFIG['EMA_SHORT_PERIOD']}): {ColoredFormatter.BLUE}{last_row_indicators['ema_short']:.4f}{ColoredFormatter.RESET} | "
                f"EMA Long ({BOT_CONFIG['EMA_LONG_PERIOD']}): {ColoredFormatter.BLUE}{last_row_indicators['ema_long']:.4f}{ColoredFormatter.RESET} | "
                f"Trend EMA ({BOT_CONFIG['TREND_EMA_PERIOD']}): {ColoredFormatter.BLUE}{last_row_indicators['trend_ema']:.4f}{ColoredFormatter.RESET} | "
                f"RSI ({BOT_CONFIG['RSI_PERIOD']}): {ColoredFormatter.YELLOW}{last_row_indicators['rsi']:.2f}{ColoredFormatter.RESET} | "
                f"Volume Spike: {ColoredFormatter.GREEN if last_row_indicators['volume_spike'] else ColoredFormatter.RED}{'Yes' if last_row_indicators['volume_spike'] else 'No'}{ColoredFormatter.RESET}"
            )
            logging.info(f"[{symbol}] Indicator Values: {log_details}") # Log for each symbol

            # --- Order Placement Logic based on Final Signal ---
            if final_signal != 'none':
                # Determine specific reasoning for the signal
                reasoning = []
                if final_signal == 'Buy':
                    reasoning.append(f"EMA Short ({last_row_indicators['ema_short']:.4f}) crossed above EMA Long ({last_row_indicators['ema_long']:.4f})")
                    reasoning.append(f"Price ({current_price:.4f}) is above Trend EMA ({last_row_indicators['trend_ema']:.4f})")
                    reasoning.append(f"RSI ({last_row_indicators['rsi']:.2f}) is below Overbought ({BOT_CONFIG['RSI_OVERBOUGHT']})")
                    if last_row_indicators['volume_spike']:
                        reasoning.append("Volume spike detected")
                    
                    logging.info(f'{ColoredFormatter.GREEN}{ColoredFormatter.BOLD}BUY SIGNAL for {symbol} 📈{ColoredFormatter.RESET}')
                    logging.info(f'{ColoredFormatter.GREEN}Reasoning: {"; ".join(reasoning)}{ColoredFormatter.RESET}')
                    logging.info(f'{ColoredFormatter.GREEN}Calculated TP: {tp_price:.4f}, SL: {sl_price:.4f}{ColoredFormatter.RESET}')

                    # Calculate common order parameters
                    price_precision, qty_precision = bybit_client.get_precisions(symbol)
                    
                    # Calculate position size based on risk per trade
                    capital_for_risk = balance 
                    risk_amount_usdt = capital_for_risk * BOT_CONFIG["RISK_PER_TRADE_PCT"]
                    
                    if risk_distance <= 0:
                        logging.warning(f"Calculated risk_distance for {symbol} is zero or negative. Skipping order.")
                        continue

                    order_qty_risk_based = risk_amount_usdt / risk_distance
                    order_qty_from_usdt = BOT_CONFIG["ORDER_QTY_USDT"] / current_price
                    order_qty = min(round(order_qty_risk_based, qty_precision), round(order_qty_from_usdt, qty_precision))
                    
                    if order_qty <= 0:
                        logging.warning(f"Calculated order quantity for {symbol} is zero or negative ({order_qty}). Skipping order.")
                        continue

                    bybit_client.set_margin_mode_and_leverage(
                        symbol, BOT_CONFIG["MARGIN_MODE"], BOT_CONFIG["LEVERAGE"]
                    )
                    sleep(0.5) # Give API a moment to process

                    order_id = None
                    if support and abs(current_price - support) < (current_price * BOT_CONFIG["PRICE_DETECTION_THRESHOLD_PCT"]):
                        logging.info(f"{ColoredFormatter.BLUE}Price near support at {support:.4f}. Placing Limit Order to Buy at support.{ColoredFormatter.RESET}")
                        order_id = bybit_client.place_limit_order(
                            symbol=symbol, side='Buy', price=round(support, price_precision), qty=order_qty,
                            tp_price=round(tp_price, price_precision), sl_price=round(sl_price, price_precision)
                        )
                    elif resistance and current_price > resistance:
                        logging.info(f"{ColoredFormatter.BLUE}Price broken above resistance at {resistance:.4f}. Placing Conditional Market Order for breakout.{ColoredFormatter.RESET}")
                        trigger_price = current_price * (1 + 0.001) # 0.1% above current price
                        order_id = bybit_client.place_conditional_order(
                            symbol=symbol, side='Buy', qty=order_qty, trigger_price=round(trigger_price, price_precision),
                            order_type='Market', tp_price=round(tp_price, price_precision), sl_price=round(sl_price, price_precision)
                        )
                    else:
                        logging.info(f"{ColoredFormatter.BLUE}No specific S/R condition. Placing Market Order to Buy.{ColoredFormatter.RESET}")
                        order_id = bybit_client.place_market_order(
                            symbol=symbol, side='Buy', qty=order_qty,
                            tp_price=round(tp_price, price_precision), sl_price=round(sl_price, price_precision)
                        )

                elif final_signal == 'Sell':
                    reasoning.append(f"EMA Short ({last_row_indicators['ema_short']:.4f}) crossed below EMA Long ({last_row_indicators['ema_long']:.4f})")
                    reasoning.append(f"Price ({current_price:.4f}) is below Trend EMA ({last_row_indicators['trend_ema']:.4f})")
                    reasoning.append(f"RSI ({last_row_indicators['rsi']:.2f}) is above Oversold ({BOT_CONFIG['RSI_OVERSOLD']})")
                    if last_row_indicators['volume_spike']:
                        reasoning.append("Volume spike detected")

                    logging.info(f'{ColoredFormatter.RED}{ColoredFormatter.BOLD}SELL SIGNAL for {symbol} 📉{ColoredFormatter.RESET}')
                    logging.info(f'{ColoredFormatter.RED}Reasoning: {"; ".join(reasoning)}{ColoredFormatter.RESET}')
                    logging.info(f'{ColoredFormatter.RED}Calculated TP: {tp_price:.4f}, SL: {sl_price:.4f}{ColoredFormatter.RESET}')

                    # Calculate common order parameters
                    price_precision, qty_precision = bybit_client.get_precisions(symbol)
                    
                    # Calculate position size based on risk per trade
                    capital_for_risk = balance 
                    risk_amount_usdt = capital_for_risk * BOT_CONFIG["RISK_PER_TRADE_PCT"]
                    
                    if risk_distance <= 0:
                        logging.warning(f"Calculated risk_distance for {symbol} is zero or negative. Skipping order.")
                        continue

                    order_qty_risk_based = risk_amount_usdt / risk_distance
                    order_qty_from_usdt = BOT_CONFIG["ORDER_QTY_USDT"] / current_price
                    order_qty = min(round(order_qty_risk_based, qty_precision), round(order_qty_from_usdt, qty_precision))
                    
                    if order_qty <= 0:
                        logging.warning(f"Calculated order quantity for {symbol} is zero or negative ({order_qty}). Skipping order.")
                        continue

                    bybit_client.set_margin_mode_and_leverage(
                        symbol, BOT_CONFIG["MARGIN_MODE"], BOT_CONFIG["LEVERAGE"]
                    )
                    sleep(0.5) # Give API a moment to process

                    order_id = None
                    if resistance and abs(current_price - resistance) < (current_price * BOT_CONFIG["PRICE_DETECTION_THRESHOLD_PCT"]):
                        logging.info(f"{ColoredFormatter.MAGENTA}Price near resistance at {resistance:.4f}. Placing Limit Order to Sell at resistance.{ColoredFormatter.RESET}")
                        order_id = bybit_client.place_limit_order(
                            symbol=symbol, side='Sell', price=round(resistance, price_precision), qty=order_qty,
                            tp_price=round(tp_price, price_precision), sl_price=round(sl_price, price_precision)
                        )
                    elif support and current_price < support:
                        logging.info(f"{ColoredFormatter.MAGENTA}Price broken below support at {support:.4f}. Placing Conditional Market Order for breakdown.{ColoredFormatter.RESET}")
                        trigger_price = current_price * (1 - 0.001) # 0.1% below current price
                        order_id = bybit_client.place_conditional_order(
                            symbol=symbol, side='Sell', qty=order_qty, trigger_price=round(trigger_price, price_precision),
                            order_type='Market', tp_price=round(tp_price, price_precision), sl_price=round(sl_price, price_precision)
                        )
                    else:
                        logging.info(f"{ColoredFormatter.MAGENTA}No specific S/R condition. Placing Market Order to Sell.{ColoredFormatter.RESET}")
                        order_id = bybit_client.place_market_order(
                            symbol=symbol, side='Sell', qty=order_qty,
                            tp_price=round(tp_price, price_precision), sl_price=round(sl_price, price_precision)
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
