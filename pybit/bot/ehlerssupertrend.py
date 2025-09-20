#!/usr/bin/env python3

# Silence specific warnings
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module='pkg_resources')

import pandas as pd
import pandas_ta as ta
import logging
import os
from time import sleep
import datetime
import pytz
import numpy as np
import uuid
import sys
from typing import Optional, Tuple, Dict, Any, List # Pyrmethus's touch: Type hinting for clarity!

# Import from pybit
from pybit.unified_trading import HTTP

# Import BOT_CONFIG from the new config file
from config import BOT_CONFIG

# --- Custom Colored Logging Formatter ---
from colorama import init, Fore, Style

init(autoreset=True) # Initialize Colorama for automatic reset

class ColoredFormatter(logging.Formatter):
    """
    # A mystical formatter that paints log messages with vibrant neon hues,
    # transforming the terminal into a canvas of digital wisdom.
    """
    GREEN = Fore.GREEN
    RED = Fore.RED
    YELLOW = Fore.YELLOW
    BLUE = Fore.BLUE
    MAGENTA = Fore.MAGENTA
    CYAN = Fore.CYAN
    WHITE = Fore.WHITE
    RESET = Style.RESET_ALL
    BOLD = Style.BRIGHT
    
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

# Add a FileHandler for persistent logs
log_file_path = os.path.join(os.path.dirname(__file__), 'trading_bot.log')
file_handler = logging.FileHandler(log_file_path)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
root_logger.addHandler(file_handler)

# Set root logger level based on config
root_logger.setLevel(getattr(logging, BOT_CONFIG["LOG_LEVEL"]))


# --- Bybit Client Class ---
class Bybit:
    """
    # The Bybit Oracle: A conduit to the exchange's data and execution realms.
    # Enhanced with dry run capabilities and meticulous error handling.
    """
    def __init__(self, api: str, secret: str, testnet: bool = False, dry_run: bool = False):
        if not api or not secret:
            raise ValueError(f"{Fore.RED}API Key and Secret must be provided to awaken the trading spirit.{Style.RESET_ALL}")
        self.api = api
        self.secret = secret
        self.testnet = testnet
        self.dry_run = dry_run # New: Dry run flag
        self.session = HTTP(api_key=self.api, api_secret=self.secret, testnet=self.testnet)
        logging.info(f"{Fore.CYAN}Bybit client initialized. Testnet: {self.testnet}, Dry Run: {self.dry_run}{Style.RESET_ALL}")

    def get_balance(self, coin: str = "USDT") -> Optional[float]:
        """Fetches and returns the wallet balance for a specific coin."""
        try:
            resp = self.session.get_wallet_balance(accountType="UNIFIED", coin=coin)
            if resp['retCode'] == 0 and resp['result']['list']:
                balance_data_list = resp['result']['list'][0]['coin']
                if balance_data_list:
                    for coin_data in balance_data_list:
                        if coin_data['coin'] == coin:
                            balance = float(coin_data['walletBalance'])
                            logging.debug(f"{Fore.BLUE}Fetched balance: {balance} {coin}{Style.RESET_ALL}")
                            return balance
                    logging.warning(f"{Fore.YELLOW}No balance data found for specified coin {coin}.{Style.RESET_ALL}")
                    return 0.0
                else:
                    logging.warning(f"{Fore.YELLOW}No coin data found in balance list for accountType UNIFIED.{Style.RESET_ALL}")
                    return 0.0
            else:
                logging.error(f"{Fore.RED}Error getting balance for {coin}: {resp.get('retMsg', 'Unknown error')} (Code: {resp.get('retCode', 'N/A')}){Style.RESET_ALL}")
                return None
        except Exception as err:
            logging.error(f"{Fore.RED}Exception getting balance for {coin}: {err}{Style.RESET_ALL}")
            return None

    def get_positions(self, settleCoin: str = "USDT") -> List[str]:
        """Returns a list of symbols with open positions."""
        try:
            resp = self.session.get_positions(category='linear', settleCoin=settleCoin)
            if resp['retCode'] == 0:
                open_positions = [elem['symbol'] for elem in resp['result']['list'] if float(elem['leverage']) > 0 and float(elem['size']) > 0]
                logging.debug(f"{Fore.BLUE}Fetched open positions: {open_positions}{Style.RESET_ALL}")
                return open_positions
            else:
                logging.error(f"{Fore.RED}Error getting positions: {resp.get('retMsg', 'Unknown error')} (Code: {resp.get('retCode', 'N/A')}){Style.RESET_ALL}")
                return []
        except Exception as err:
            logging.error(f"{Fore.RED}Exception getting positions: {err}{Style.RESET_ALL}")
            return []

    def get_tickers(self) -> Optional[List[str]]:
        """Retrieves all USDT perpetual linear symbols from the derivatives market."""
        try:
            resp = self.session.get_tickers(category="linear")
            if resp['retCode'] == 0:
                symbols = [elem['symbol'] for elem in resp['result']['list'] if 'USDT' in elem['symbol'] and not 'USDC' in elem['symbol']]
                logging.debug(f"{Fore.BLUE}Fetched {len(symbols)} tickers.{Style.RESET_ALL}")
                return symbols
            else:
                logging.error(f"{Fore.RED}Error getting tickers: {resp.get('retMsg', 'Unknown error')} (Code: {resp.get('retCode', 'N/A')}){Style.RESET_ALL}")
                return None
        except Exception as err:
            logging.error(f"{Fore.RED}Exception getting tickers: {err}{Style.RESET_ALL}")
            return None

    def klines(self, symbol: str, timeframe: int, limit: int = 500) -> pd.DataFrame:
        """Fetches klines (candlestick data) for a given symbol and returns a pandas DataFrame."""
        try:
            resp = self.session.get_kline(
                category='linear',
                symbol=symbol,
                interval=str(timeframe), # Ensure interval is string
                limit=limit
            )
        except Exception as e:
            self.logger.error(f"Error fetching kline data for {symbol}: {e}")
            return pd.DataFrame()
            if resp['retCode'] == 0:
                if not resp['result']['list']:
                    logging.warning(f"{Fore.YELLOW}No kline data returned for {symbol}.{Style.RESET_ALL}")
                    return pd.DataFrame()
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
                    logging.warning(f"{Fore.YELLOW}Critical OHLCV columns are all NaN for {symbol}. Skipping this kline data.{Style.RESET_ALL}")
                    return pd.DataFrame() # Return empty DataFrame if data is bad
                logging.debug(f"{Fore.BLUE}Fetched {len(df)} klines for {symbol} ({timeframe}min).{Style.RESET_ALL}")
                return df
            else:
                logging.error(f"{Fore.RED}Error getting klines for {symbol}: {resp.get('retMsg', 'Unknown error')} (Code: {resp.get('retCode', 'N/A')}){Style.RESET_ALL}")
                return pd.DataFrame()
        except Exception as err:
            logging.error(f"{Fore.RED}Exception getting klines for {symbol}: {err}{Style.RESET_ALL}")
            return pd.DataFrame() # Return empty DataFrame on error

    def get_orderbook_levels(self, symbol: str, limit: int = 50) -> Tuple[Optional[float], Optional[float]]:
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
                
                logging.debug(f"{Fore.BLUE}Orderbook for {symbol}: Support={strong_support_price}, Resistance={strong_resistance_price}{Style.RESET_ALL}")
                return strong_support_price, strong_resistance_price
            else:
                logging.error(f"{Fore.RED}Error getting orderbook for {symbol}: Invalid response format or {resp.get('retMsg', 'Unknown error')} (Code: {resp.get('retCode', 'N/A')}){Style.RESET_ALL}")
                return None, None
        except Exception as err:
            logging.error(f"{Fore.RED}Exception getting orderbook for {symbol}: {err}{Style.RESET_ALL}")
            return None, None

    def get_precisions(self, symbol: str) -> Tuple[int, int]:
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
                
                logging.debug(f"{Fore.BLUE}Precisions for {symbol}: Price={price_precision}, Qty={qty_precision}{Style.RESET_ALL}")
                return price_precision, qty_precision
            else:
                logging.error(f"{Fore.RED}Error getting precisions for {symbol}: {resp.get('retMsg', 'Unknown error')} (Code: {resp.get('retCode', 'N/A')}){Style.RESET_ALL}")
                return 0, 0
        except Exception as err:
            logging.error(f"{Fore.RED}Exception getting precisions for {symbol}: {err}{Style.RESET_ALL}")
            return 0, 0

    def set_margin_mode_and_leverage(self, symbol: str, mode: int = 1, leverage: int = 10) -> None:
        """Sets the margin mode and leverage for a symbol."""
        if self.dry_run:
            logging.info(f"{Fore.MAGENTA}[DRY RUN] Would set margin mode to {'Isolated' if mode==1 else 'Cross'} and leverage to {leverage}x for {symbol}.{Style.RESET_ALL}")
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
                logging.info(f"{Fore.GREEN}Margin mode set to {'Isolated' if mode==1 else 'Cross'} and leverage set to {leverage}x for {symbol}.{Style.RESET_ALL}")
            elif resp['retCode'] == 110026 or resp['retCode'] == 110043: # Already set or in position
                logging.debug(f"{Fore.YELLOW}Margin mode or leverage already set for {symbol} (Code: {resp['retCode']}).{Style.RESET_ALL}")
            else:
                logging.warning(f"{Fore.YELLOW}Failed to set margin mode/leverage for {symbol}: {resp.get('retMsg', 'Unknown error')} (Code: {resp['retCode']}){Style.RESET_ALL}")
        except Exception as err:
            if '110026' in str(err) or '110043' in str(err): # Already set or in position
                logging.debug(f"{Fore.YELLOW}Margin mode or leverage already set for {symbol}.{Style.RESET_ALL}")
            else:
                logging.error(f"{Fore.RED}Exception setting margin mode/leverage for {symbol}: {err}{Style.RESET_ALL}")

    def place_order_common(self, symbol: str, side: str, order_type: str, qty: float, price: Optional[float] = None, trigger_price: Optional[float] = None, tp_price: Optional[float] = None, sl_price: Optional[float] = None, time_in_force: str = 'GTC') -> Optional[str]:
        """Internal common function to place various order types."""
        if self.dry_run:
            dummy_order_id = f"DRY_RUN_ORDER_{uuid.uuid4()}"
            log_msg = f"{Fore.MAGENTA}[DRY RUN] Would place order for {symbol} ({order_type} {side} {qty:.6f})" # Use .6f for quantity precision
            if price is not None: log_msg += f" at price {price:.6f}"
            if trigger_price is not None: log_msg += f" triggered by {trigger_price:.6f}"
            if tp_price is not None: log_msg += f" with TP {tp_price:.6f}"
            if sl_price is not None: log_msg += f" and SL {sl_price:.6f}"
            logging.info(f"{log_msg}. Simulated Order ID: {dummy_order_id}{Style.RESET_ALL}")
            return dummy_order_id # Simulate success
        
        try:
            # Ensure prices and quantities are formatted correctly based on precision
            price_precision, qty_precision = self.get_precisions(symbol)
            if price_precision == 0 and qty_precision == 0:
                logging.error(f"{Fore.RED}Failed to get precisions for {symbol}. Cannot place order.{Style.RESET_ALL}")
                return None
            
            params = {
                'category': 'linear',
                'symbol': symbol,
                'side': side,
                'orderType': order_type,
                'qty': f"{qty:.{qty_precision}f}", # Format quantity
                'timeInForce': time_in_force
            }
            if price is not None:
                params['price'] = f"{price:.{price_precision}f}" # Format price
            if trigger_price is not None:
                params['triggerPrice'] = f"{trigger_price:.{price_precision}f}" # Format trigger price
                params['triggerBy'] = 'MarkPrice' # Default to Mark Price for triggers
            if tp_price is not None:
                params['takeProfit'] = f"{tp_price:.{price_precision}f}"
                params['tpTriggerBy'] = 'Market' # Market price for TP/SL triggers is generally safer
            if sl_price is not None:
                params['stopLoss'] = f"{sl_price:.{price_precision}f}"
                params['slTriggerBy'] = 'Market'

            response = self.session.place_order(**params)
            if response['retCode'] == 0:
                order_id = response['result']['orderId']
                logging.info(f"{Fore.GREEN}Order placed for {symbol} ({order_type} {side} {qty:.{qty_precision}f}). Order ID: {order_id}{Style.RESET_ALL}")
                return order_id
            else:
                logging.error(f"{Fore.RED}Failed to place order for {symbol} ({order_type} {side} {qty:.{qty_precision}f}): {response.get('retMsg', 'Unknown error')} (Code: {response['retCode']}){Style.RESET_ALL}")
                return None
        except Exception as err:
            logging.error(f"{Fore.RED}Exception placing {order_type} order for {symbol}: {err}{Style.RESET_ALL}")
            return None

    def place_market_order(self, symbol: str, side: str, qty: float, tp_price: Optional[float] = None, sl_price: Optional[float] = None) -> Optional[str]:
        """Places a market order with optional TP/SL."""
        return self.place_order_common(symbol, side, 'Market', qty, tp_price=tp_price, sl_price=sl_price)

    def place_limit_order(self, symbol: str, side: str, price: float, qty: float, tp_price: Optional[float] = None, sl_price: Optional[float] = None, time_in_force: str = 'GTC') -> Optional[str]:
        """Places a limit order with optional TP/SL."""
        return self.place_order_common(symbol, side, 'Limit', qty, price=price, tp_price=tp_price, sl_price=sl_price, time_in_force=time_in_force)

    def place_conditional_order(self, symbol: str, side: str, qty: float, trigger_price: float, order_type: str = 'Market', price: Optional[float] = None, tp_price: Optional[float] = None, sl_price: Optional[float] = None) -> Optional[str]:
        """Places a conditional order that becomes active at a trigger price.
        If order_type is 'Limit', a specific `price` must be provided for the limit execution."""
        if order_type == 'Limit' and price is None:
            price = trigger_price # Default to trigger_price if no explicit limit price given
            logging.warning(f"{Fore.YELLOW}Conditional limit order requested for {symbol} without explicit `price`. Using `trigger_price` as limit execution price.{Style.RESET_ALL}")

        return self.place_order_common(symbol, side, order_type, qty, price=price, trigger_price=trigger_price, tp_price=tp_price, sl_price=sl_price)
    
    def cancel_all_open_orders(self, symbol: str) -> Dict[str, Any]:
        """Cancels all active orders for a given symbol."""
        if self.dry_run:
            logging.info(f"{Fore.MAGENTA}[DRY RUN] Would cancel all open orders for {symbol}.{Style.RESET_ALL}")
            return {'retCode': 0, 'retMsg': 'OK'} # Simulate success
        
        try:
            response = self.session.cancel_all_orders(
                category='linear',
                symbol=symbol
            )
            if response['retCode'] == 0:
                logging.info(f"{Fore.GREEN}All open orders for {symbol} cancelled successfully.{Style.RESET_ALL}")
            else:
                logging.warning(f"{Fore.YELLOW}Failed to cancel all orders for {symbol}: {response.get('retMsg', 'Unknown error')} (Code: {response['retCode']}){Style.RESET_ALL}")
            return response
        except Exception as err:
            logging.error(f"{Fore.RED}Exception cancelling all orders for {symbol}: {err}{Style.RESET_ALL}")
            return {'retCode': -1, 'retMsg': str(err)}

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves all active orders for a given symbol, or all symbols if none specified."""
        try:
            params = {'category': 'linear'}
            if symbol:
                params['symbol'] = symbol
            
            response = self.session.get_open_orders(**params)
            if response['retCode'] == 0:
                open_orders = response['result']['list']
                logging.debug(f"{Fore.BLUE}Fetched {len(open_orders)} open orders for {symbol if symbol else 'all symbols'}.{Style.RESET_ALL}")
                return open_orders
            else:
                logging.error(f"{Fore.RED}Error getting open orders for {symbol if symbol else 'all symbols'}: {response.get('retMsg', 'Unknown error')} (Code: {response['retCode']}){Style.RESET_ALL}")
                return []
        except Exception as err:
            logging.error(f"{Fore.RED}Exception getting open orders for {symbol if symbol else 'all symbols'}: {err}{Style.RESET_ALL}")
            return []

    def get_order_status(self, symbol: str, order_id: str) -> Optional[Dict[str, Any]]:
        """Fetches the status of a specific order."""
        if self.dry_run:
            logging.info(f"{Fore.MAGENTA}[DRY RUN] Would check status for order ID {order_id} on {symbol}.{Style.RESET_ALL}")
            # Simulate a filled order for dry run
            return {'orderId': order_id, 'status': 'Filled', 'symbol': symbol, 'side': 'Buy', 'execQty': '0.001', 'avgPrice': '30000.00'}
        
        try:
            response = self.session.get_order_info(
                category='linear',
                symbol=symbol,
                orderId=order_id
            )
            if response['retCode'] == 0 and 'result' in response and response['result']['list']:
                order_info = response['result']['list'][0]
                logging.debug(f"{Fore.BLUE}Order status for {symbol} (ID: {order_id}): {order_info['orderStatus']} (Filled Qty: {order_info.get('execQty', '0')}, Avg Price: {order_info.get('avgPrice', 'N/A')}){Style.RESET_ALL}")
                return order_info
            elif response['retCode'] == 0 and 'result' in response and not response['result']['list']:
                logging.warning(f"{Fore.YELLOW}No order info found for {symbol} (ID: {order_id}). It might have been filled or cancelled.{Style.RESET_ALL}")
                return None
            else:
                logging.error(f"{Fore.RED}Error getting order status for {symbol} (ID: {order_id}): {response.get('retMsg', 'Unknown error')} (Code: {response['retCode']}){Style.RESET_ALL}")
                return None
        except Exception as err:
            logging.error(f"{Fore.RED}Exception getting order status for {symbol} (ID: {order_id}): {err}{Style.RESET_ALL}")
            return None

    def close_position(self, symbol: str, position_idx: int = 0) -> Optional[str]:
        """
        Closes an open position for a given symbol using a market order.
        position_idx: 0 for one-way mode, 1 for buy side, 2 for sell side in hedge mode.
        """
        if self.dry_run:
            logging.info(f"{Fore.MAGENTA}[DRY RUN] Would close position for {symbol} with a market order.{Style.RESET_ALL}")
            return f"DRY_RUN_CLOSE_ORDER_{uuid.uuid4()}" # Simulate success
            
        try:
            # First, get current position details to determine side and size
            positions_resp = self.session.get_positions(category='linear', symbol=symbol)
            if positions_resp['retCode'] != 0:
                logging.error(f"{Fore.RED}Error getting position details for {symbol} to close: {positions_resp.get('retMsg', 'Unknown error')} (Code: {positions_resp['retCode']}){Style.RESET_ALL}")
                return None
            if not positions_resp['result']['list']:
                logging.warning(f"{Fore.YELLOW}No position list found for {symbol} to close. {positions_resp.get('retMsg', 'No position found')}{Style.RESET_ALL}")
                return None

            position_info = None
            for pos in positions_resp['result']['list']:
                if float(pos['size']) > 0: # Found an open position
                    position_info = pos
                    break
            
            if not position_info:
                logging.info(f"{Fore.CYAN}No open position found for {symbol} to close (size is 0).{Style.RESET_ALL}")
                return None

            current_side = position_info['side']
            current_size = float(position_info['size'])
            
            if current_size == 0:
                logging.info(f"{Fore.CYAN}No open position found for {symbol} to close (size is 0).{Style.RESET_ALL}")
                return None

            # Determine the opposite side to close the position
            close_side = 'Sell' if current_side == 'Buy' else 'Buy'

            # Use place_market_order for consistency and potential TP/SL handling if needed (though not typical for closing)
            order_id = self.place_market_order(symbol=symbol, side=close_side, qty=current_size)
            
            if order_id:
                logging.info(f"{Fore.GREEN}Market order placed to close {symbol} position ({current_side} {current_size}). Order ID: {order_id}{Style.RESET_ALL}")
                return order_id
            else:
                logging.error(f"{Fore.RED}Failed to place market order to close {symbol} position.{Style.RESET_ALL}")
                return None
        except Exception as err:
            logging.error(f"{Fore.RED}Exception closing position for {symbol}: {err}{Style.RESET_ALL}")
            return None

# --- API Session Initialization ---
if not BOT_CONFIG["API_KEY"] or not BOT_CONFIG["API_SECRET"]:
    logging.error(f"{Fore.RED}API keys not found. Please check your .env file and ensure BYBIT_API_KEY and BYBIT_API_SECRET are set.{Style.RESET_ALL}")
    sys.exit(1) # Use sys.exit for cleaner termination

try:
    bybit_client = Bybit(
        api=BOT_CONFIG["API_KEY"],
        secret=BOT_CONFIG["API_SECRET"],
        testnet=BOT_CONFIG["TESTNET"],
        dry_run=BOT_CONFIG["DRY_RUN"] # Pass dry_run flag to client
    )
    mode_info = f"{Fore.MAGENTA}{Style.BRIGHT}DRY RUN{Style.RESET_ALL}" if BOT_CONFIG["DRY_RUN"] else f"{Fore.GREEN}{Style.BRIGHT}LIVE{Style.RESET_ALL}"
    testnet_info = f"{Fore.YELLOW}TESTNET{Style.RESET_ALL}" if BOT_CONFIG["TESTNET"] else f"{Fore.BLUE}MAINNET{Style.RESET_ALL}"
    logging.info(f"{Fore.LIGHTYELLOW_EX}Successfully connected to Bybit API in {mode_info} mode on {testnet_info}.{Style.RESET_ALL}")
    logging.debug(f"{Fore.CYAN}Bot configuration: {BOT_CONFIG}{Style.RESET_ALL}") # Log full config at DEBUG level
except Exception as e:
    logging.error(f"{Fore.RED}Failed to connect to Bybit API: {e}. Please ensure your API keys are correct and your system clock is synchronized with NTP.{Style.RESET_ALL}")
    sys.exit(1)

# --- Helper Functions ---
def get_current_time(timezone_str: str) -> Tuple[datetime.datetime, datetime.datetime]:
    """Returns the current local and UTC time objects."""
    try:
        tz = pytz.timezone(timezone_str)
        local_time = datetime.datetime.now(tz)
        utc_time = datetime.datetime.now(pytz.utc)
        return local_time, utc_time
    except pytz.UnknownTimeZoneError:
        logging.error(f"{Fore.RED}Unknown timezone specified: '{timezone_str}'. Please check your config.py.{Style.RESET_ALL}")
        # Fallback to UTC if timezone is invalid
        return datetime.datetime.now(pytz.utc), datetime.datetime.now(pytz.utc)

def is_market_open(local_time: datetime.datetime, open_hour: int, close_hour: int) -> bool:
    """Checks if the market is open based on configured hours, handling overnight closures."""
    current_hour = local_time.hour
    # Handle cases where open/close hours might be strings from config
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

def send_termux_toast(message: str) -> None:
    """Sends a notification toast using Termux:API."""
    # Check if running in Termux and termux-api command is available
    if sys.platform.startswith('linux') and os.environ.get('TERMUX_VERSION'):
        try:
            # Use subprocess for better control and error handling than os.system
            import subprocess
            result = subprocess.run(['command', '-v', 'termux-toast'], capture_output=True, text=True)
            if result.returncode == 0: # Command found
                subprocess.run(['termux-toast', message], check=True)
                logging.debug(f"Sent Termux toast: '{message}'")
            else:
                logging.warning(f"{Fore.YELLOW}Termux:API 'termux-toast' command not found. Install Termux:API app and run 'pkg install termux-api' for notifications.{Style.RESET_ALL}")
        except FileNotFoundError:
             logging.warning(f"{Fore.YELLOW}Termux:API 'termux-toast' command not found (FileNotFoundError). Install Termux:API app and run 'pkg install termux-api' for notifications.{Style.RESET_ALL}")
        except subprocess.CalledProcessError as e:
            logging.error(f"{Fore.RED}Failed to execute termux-toast: {e}{Style.RESET_ALL}")
        except Exception as e:
            logging.error(f"{Fore.RED}An unexpected error occurred while sending Termux toast: {e}{Style.RESET_ALL}")
    else:
        logging.debug(f