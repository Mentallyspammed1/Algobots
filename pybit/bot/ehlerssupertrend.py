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
        self._dry_run_positions = {} # {symbol: {'side': 'Buy'/'Sell', 'size': float}}
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
        if self.dry_run:
            # In dry run, return symbols from our internal tracker
            open_symbols = list(self._dry_run_positions.keys())
            logging.debug(f"{Fore.BLUE}[DRY RUN] Fetched open positions from internal tracker: {open_symbols}{Style.RESET_ALL}")
            return open_symbols

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
            log_msg = f"{Fore.MAGENTA}[DRY RUN] Would place order for {symbol} ({order_type} {side} {qty:.6f})"
            if price is not None: log_msg += f" at price {price:.6f}"
            if trigger_price is not None: log_msg += f" triggered by {trigger_price:.6f}"
            if tp_price is not None: log_msg += f" with TP {tp_price:.6f}"
            if sl_price is not None: log_msg += f" and SL {sl_price:.6f}"
            logging.info(f"{log_msg}. Simulated Order ID: {dummy_order_id}{Style.RESET_ALL}")
            
            # Simulate opening a position in dry run
            self._dry_run_positions[symbol] = {'side': side, 'size': qty}
            logging.debug(f"{Fore.MAGENTA}[DRY RUN] Simulated open position for {symbol}: {self._dry_run_positions[symbol]}{Style.RESET_ALL}")
            return dummy_order_id # Simulate success
        
        try:
            # Ensure prices and quantities are formatted correctly based on precision
            price_precision, qty_precision = self.get_precisions(symbol)
            
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
            if symbol in self._dry_run_positions:
                del self._dry_run_positions[symbol]
                logging.debug(f"{Fore.MAGENTA}[DRY RUN] Simulated closed position for {symbol}. Remaining dry run positions: {self._dry_run_positions}{Style.RESET_ALL}")
            return f"DRY_RUN_CLOSE_ORDER_{uuid.uuid4()}" # Simulate success
            
        try:
            # First, get current position details to determine side and size
            positions_resp = self.session.get_positions(category='linear', symbol=symbol)
            if positions_resp['retCode'] != 0 or not positions_resp['result']['list']:
                logging.warning(f"{Fore.YELLOW}Could not get position details for {symbol} to close. {positions_resp.get('retMsg', 'No position found')}{Style.RESET_ALL}")
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
    logging.error(f"{Fore.RED}Failed to connect to Bybit API: {e}{Style.RESET_ALL}")
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
             logging.warning(f"{Fore.YELLOW}Termux:API 'termux-toast' command not found. Install Termux:API app and run 'pkg install termux-api' for notifications.{Style.RESET_ALL}")
        except subprocess.CalledProcessError as e:
            logging.error(f"{Fore.RED}Failed to execute termux-toast: {e}{Style.RESET_ALL}")
        except Exception as e:
            logging.error(f"{Fore.RED}An unexpected error occurred while sending Termux toast: {e}{Style.RESET_ALL}")
    else:
        logging.debug(f"Not in a Termux environment or termux-api not available. Toast skipped: '{message}'")

def calculate_pnl(side: str, entry_price: float, exit_price: float, qty: float) -> float:
    """Calculates PnL for a trade."""
    if side == 'Buy':
        pnl = (exit_price - entry_price) * qty
    else: # Sell
        pnl = (entry_price - exit_price) * qty
    return pnl


# --- Strategy Section (Ehlers Supertrend Cross Strategy Logic) ---
def calculate_ehl_supertrend_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    # Forging the Ehlers Supertrend, RSI, and Volume indicators.
    # These will guide our path through the market's currents.
    # Enhanced with checks for sufficient data and NaN handling.
    """
    df = df.copy()
    
    # Ensure columns are float and fill NaNs immediately for critical columns
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
        # Fill NaNs with previous valid observation, then with 0 if still NaN
        df[col] = df[col].ffill().fillna(0)

    # Calculate Fast Ehlers Supertrend
    try:
        st_fast = ta.supertrend(
            high=df['High'], low=df['Low'], close=df['Close'],
            length=BOT_CONFIG["EST_FAST_LENGTH"], multiplier=BOT_CONFIG["EST_FAST_MULTIPLIER"]
        )
        # The actual Supertrend line is in the column named 'SUPERT_LENGTH_MULTIPLIER'
        df['st_fast_line'] = st_fast[f'SUPERT_{BOT_CONFIG["EST_FAST_LENGTH"]}_{BOT_CONFIG["EST_FAST_MULTIPLIER"]}']
        df['st_fast_direction'] = st_fast[f'SUPERTd_{BOT_CONFIG["EST_FAST_LENGTH"]}_{BOT_CONFIG["EST_FAST_MULTIPLIER"]}'] # 1 for up, -1 for down
    except Exception as e:
        logging.error(f"{Fore.RED}Error calculating fast Supertrend: {e}{Style.RESET_ALL}")
        df['st_fast_line'] = np.nan
        df['st_fast_direction'] = np.nan

    # Calculate Slow Ehlers Supertrend
    try:
        st_slow = ta.supertrend(
            high=df['High'], low=df['Low'], close=df['Close'],
            length=BOT_CONFIG["EST_SLOW_LENGTH"], multiplier=BOT_CONFIG["EST_SLOW_MULTIPLIER"]
        )
        df['st_slow_line'] = st_slow[f'SUPERT_{BOT_CONFIG["EST_SLOW_LENGTH"]}_{BOT_CONFIG["EST_SLOW_MULTIPLIER"]}']
        df['st_slow_direction'] = st_slow[f'SUPERTd_{BOT_CONFIG["EST_SLOW_LENGTH"]}_{BOT_CONFIG["EST_SLOW_MULTIPLIER"]}'] # 1 for up, -1 for down
    except Exception as e:
        logging.error(f"{Fore.RED}Error calculating slow Supertrend: {e}{Style.RESET_ALL}")
        df['st_slow_line'] = np.nan
        df['st_slow_direction'] = np.nan
    
    # RSI
    try:
        rsi_series = ta.rsi(close=df['Close'], length=BOT_CONFIG["RSI_PERIOD"])
        df['rsi'] = rsi_series
    except Exception as e:
        logging.error(f"{Fore.RED}Error calculating RSI: {e}{Style.RESET_ALL}")
        df['rsi'] = np.nan
    
    # Volume filter
    try:
        volume_ma_period = BOT_CONFIG.get("VOLUME_MA_PERIOD", 20) # Use config for MA period
        volume_ma_series = ta.sma(close=df['Volume'], length=volume_ma_period) 
        df['volume_ma'] = volume_ma_series
        # Avoid division by zero if volume_ma is 0 or NaN
        if volume_ma_series.any() and not volume_ma_series.isnull().all():
             df['volume_spike'] = (df['Volume'] / df['volume_ma']) > BOT_CONFIG["VOLUME_THRESHOLD_MULTIPLIER"]
        else:
             df['volume_spike'] = False
             logging.warning(f"{Fore.YELLOW}Volume MA is zero or NaN, volume spike detection disabled.{Style.RESET_ALL}")
    except Exception as e:
        logging.error(f"{Fore.RED}Error calculating Volume MA and spike: {e}{Style.RESET_ALL}")
        df['volume_ma'] = np.nan
        df['volume_spike'] = False
    
    # Calculate Ehlers Fisher Transform
    try:
        fisher_period = BOT_CONFIG.get("EHLERS_FISHER_PERIOD", 9)
        if len(df) < fisher_period:
            logging.warning(f"{Fore.YELLOW}Not enough data ({len(df)} candles) for Ehlers Fisher Transform (needs {fisher_period}). Setting Fisher to NaN.{Style.RESET_ALL}")
            df['fisher'] = np.nan
            df['fisher_signal'] = np.nan
        else:
            # Fisher Transform typically uses a period of 9 or 10
            fisher_transform = ta.fisher(high=df['High'], low=df['Low'], length=fisher_period)
            df['fisher'] = fisher_transform[f'FISHERT_{fisher_period}_1']
            df['fisher_signal'] = fisher_transform[f'FISHERTs_{fisher_period}_1']
    except Exception as e:
        logging.error(f"{Fore.RED}Error calculating Ehlers Fisher Transform: {e}{Style.RESET_ALL}")
        df['fisher'] = np.nan
        df['fisher_signal'] = np.nan

    # Calculate ATR
    try:
        atr_period = BOT_CONFIG.get("ATR_PERIOD", 14) # Default to 14 if not in config
        if len(df) < atr_period:
            logging.warning(f"{Fore.YELLOW}Not enough data ({len(df)} candles) for ATR calculation (needs {atr_period}). Setting ATR to NaN.{Style.RESET_ALL}")
            df['atr'] = np.nan
        else:
            df['atr'] = ta.atr(high=df['High'], low=df['Low'], close=df['Close'], length=atr_period)
    except Exception as e:
        logging.error(f"{Fore.RED}Error calculating ATR: {e}{Style.RESET_ALL}")
        df['atr'] = np.nan
    
    # Clean up temporary columns and fill NaNs
    df = df.ffill().fillna(0) # Fill NaNs forward, then with 0

    # Final check for critical indicator columns after all calculations and NaNs filling
    critical_indicator_cols = ['st_fast_line', 'st_slow_line', 'rsi', 'volume_ma', 'fisher', 'fisher_signal', 'atr']
    for col in critical_indicator_cols:
        if col not in df.columns or df[col].isnull().all():
            logging.warning(f"{Fore.YELLOW}Critical indicator column '{col}' is missing or all NaNs after calculation for {df.index.name}. Strategy data not fully populated.{Style.RESET_ALL}")
            # Return empty DataFrame if critical data is missing, indicating strategy cannot proceed
            return pd.DataFrame() 

    return df

def generate_ehl_supertrend_signals(df: pd.DataFrame, current_price: float, support: Optional[float], resistance: Optional[float], price_precision: int, qty_precision: int) -> Tuple[str, Optional[float], Optional[float], Optional[float], pd.DataFrame]:
    """
    # Generate explicit long and short signals based on Ehlers Supertrend Cross Strategy.
    # Returns 'Buy', 'Sell', or 'none', along with calculated risk distance, TP, SL, and the full DataFrame with indicators.
    # Enhanced with trend confirmation using st_slow_direction and RSI trend.
    """
    # Ensure enough data for all indicators, including lookback periods for ST, RSI, and Volume MA
    min_required_klines = max(BOT_CONFIG["MIN_KLINES_FOR_STRATEGY"], BOT_CONFIG["EST_SLOW_LENGTH"], 
                              BOT_CONFIG["RSI_PERIOD"], BOT_CONFIG.get("VOLUME_MA_PERIOD", 20), 
                              BOT_CONFIG.get("EHLERS_FISHER_PERIOD", 9), BOT_CONFIG.get("ATR_PERIOD", 14)) # Use config for MA period, Ehlers Fisher, and ATR
    
    if df.empty or len(df) < min_required_klines:
        logging.debug(f"{Fore.BLUE}Not enough data for Ehlers Supertrend strategy indicators (needed >{min_required_klines}, got {len(df)}).{Style.RESET_ALL}")
        return 'none', None, None, None, df # signal, risk, tp, sl, df_with_indicators

    # Ensure all indicators are calculated
    df_with_indicators = calculate_ehl_supertrend_indicators(df)
    
    if df_with_indicators.empty: # Check if calculation failed
        logging.warning(f"{Fore.YELLOW}Indicator calculation failed. Cannot generate signals.{Style.RESET_ALL}")
        return 'none', None, None, None, df_with_indicators

    # Get the last two rows for current and previous candle analysis
    last_row = df_with_indicators.iloc[-1]
    prev_row = df_with_indicators.iloc[-2]

    # Avoid NaN values in critical indicators
    if pd.isna(last_row['st_fast_line']) or pd.isna(last_row['st_slow_line']) or \
       pd.isna(prev_row['st_fast_line']) or pd.isna(prev_row['st_slow_line']) or \
       pd.isna(last_row['rsi']) or pd.isna(last_row['st_slow_direction']):
        logging.warning(f"{Fore.YELLOW}Critical Supertrend or RSI values are NaN. Skipping signal generation.{Style.RESET_ALL}")
        return 'none', None, None, None, df_with_indicators

    signal = 'none'
    tp_price = None
    sl_price = None
    risk_distance = None

    # --- Enhanced Entry Conditions ---
    # 1. Trend Confirmation: Use the slow Supertrend direction as the primary trend filter.
    #    Only take long trades if the slow Supertrend is pointing up, and short trades if down.
    long_trend_confirmed = last_row['st_slow_direction'] > 0
    short_trend_confirmed = last_row['st_slow_direction'] < 0

    # 2. Crossover: Fast Supertrend crosses the Slow Supertrend.
    fast_crosses_above_slow = (prev_row['st_fast_line'] <= prev_row['st_slow_line']) and (last_row['st_fast_line'] > last_row['st_slow_line'])
    fast_crosses_below_slow = (prev_row['st_fast_line'] >= prev_row['st_slow_line']) and (last_row['st_fast_line'] < last_row['st_slow_line'])

    # 3. Confirmation Checks (at least 2 out of 3 needed)
    #    a. Ehlers Fisher Transform Confirmation
    fisher_confirm_long = last_row['fisher'] > last_row['fisher_signal']
    fisher_confirm_short = last_row['fisher'] < last_row['fisher_signal']

    #    b. RSI Confirmation (not overbought/oversold, and trending)
    rsi_confirm_long = last_row['rsi'] > BOT_CONFIG.get("RSI_CONFIRM_LONG_THRESHOLD", 55) and last_row['rsi'] < BOT_CONFIG["RSI_OVERBOUGHT"]
    rsi_confirm_short = last_row['rsi'] < BOT_CONFIG.get("RSI_CONFIRM_SHORT_THRESHOLD", 45) and last_row['rsi'] > BOT_CONFIG["RSI_OVERSOLD"]

    #    c. Volume Confirmation (spike on current or previous candle)
    volume_confirm = last_row['volume_spike'] or prev_row['volume_spike']

    # --- Generate Signals ---
    if long_trend_confirmed and fast_crosses_above_slow:
        confirmations_count = 0
        if fisher_confirm_long:
            confirmations_count += 1
        if rsi_confirm_long:
            confirmations_count += 1
        if volume_confirm:
            confirmations_count += 1

        if confirmations_count >= 2:
            signal = 'Buy'
            # Stop Loss based on the slower Supertrend line from the *previous* candle for stability
            sl_price = prev_row['st_slow_line']
            risk_distance = current_price - sl_price

            if risk_distance <= 0:
                logging.warning(f"{Fore.YELLOW}Calculated risk_distance for Buy signal is zero or negative ({risk_distance:.4f}). SL might be above entry. Skipping TP calculation.{Style.RESET_ALL}")
                tp_price = None # Cannot calculate TP if risk is invalid
            else:
                if BOT_CONFIG.get("USE_ATR_FOR_TP_SL", False):
                    # ATR-based TP/SL
                    atr_value = last_row['atr']
                    if pd.isna(atr_value) or atr_value <= 0:
                        logging.warning(f"{Fore.YELLOW}ATR value is invalid ({atr_value}). Falling back to Reward/Risk Ratio for TP/SL.{Style.RESET_ALL}")
                        tp_price = round(current_price + (risk_distance * BOT_CONFIG["REWARD_RISK_RATIO"]), price_precision)
                        sl_price = round(sl_price, price_precision)
                    else:
                        tp_price = round(current_price + (atr_value * BOT_CONFIG.get("TP_ATR_MULTIPLIER", 1.5)), price_precision)
                        sl_price = round(current_price - (atr_value * BOT_CONFIG.get("SL_ATR_MULTIPLIER", 1.0)), price_precision)
                        # Recalculate risk_distance based on ATR SL for consistency
                        risk_distance = current_price - sl_price
                else:
                    # Reward/Risk Ratio based TP/SL
                    tp_price = round(current_price + (risk_distance * BOT_CONFIG["REWARD_RISK_RATIO"]), price_precision)
                    sl_price = round(sl_price, price_precision)

    elif short_trend_confirmed and fast_crosses_below_slow:
        confirmations_count = 0
        if fisher_confirm_short:
            confirmations_count += 1
        if rsi_confirm_short:
            confirmations_count += 1
        if volume_confirm:
            confirmations_count += 1

        if confirmations_count >= 2:
            signal = 'Sell'
            # Stop Loss based on the slower Supertrend line from the *previous* candle
            sl_price = prev_row['st_slow_line']
            risk_distance = sl_price - current_price

            if risk_distance <= 0:
                logging.warning(f"{Fore.YELLOW}Calculated risk_distance for Sell signal is zero or negative ({risk_distance:.4f}). SL might be below entry. Skipping TP calculation.{Style.RESET_ALL}")
                tp_price = None # Cannot calculate TP if risk is invalid
            else:
                if BOT_CONFIG.get("USE_ATR_FOR_TP_SL", False):
                    # ATR-based TP/SL
                    atr_value = last_row['atr']
                    if pd.isna(atr_value) or atr_value <= 0:
                        logging.warning(f"{Fore.YELLOW}ATR value is invalid ({atr_value}). Falling back to Reward/Risk Ratio for TP/SL.{Style.RESET_ALL}")
                        tp_price = round(current_price - (risk_distance * BOT_CONFIG["REWARD_RISK_RATIO"]), price_precision)
                        sl_price = round(sl_price, price_precision)
                    else:
                        tp_price = round(current_price - (atr_value * BOT_CONFIG.get("TP_ATR_MULTIPLIER", 1.5)), price_precision)
                        sl_price = round(current_price + (atr_value * BOT_CONFIG.get("SL_ATR_MULTIPLIER", 1.0)), price_precision)
                        # Recalculate risk_distance based on ATR SL for consistency
                        risk_distance = sl_price - current_price
                else:
                    # Reward/Risk Ratio based TP/SL
                    tp_price = round(current_price - (risk_distance * BOT_CONFIG["REWARD_RISK_RATIO"]), price_precision)
                    sl_price = round(sl_price, price_precision)
    
    # --- S/R Integration (Optional Entry Adjustment) ---
    # This logic is handled in the main loop after signal generation, based on generated signal and S/R levels.

    return signal, risk_distance, tp_price, sl_price, df_with_indicators, volume_confirm


# --- Main Bot Loop ---
def main():
    print(f"{Fore.LIGHTYELLOW_EX}{Style.BRIGHT}Pyrmethus, the Termux Coding Wizard, is awakening the Ehlers Supertrend Cross Strategy!{Style.RESET_ALL}")
    
    symbols = BOT_CONFIG["TRADING_SYMBOLS"]
    if not symbols:
        logging.info(f"{Fore.YELLOW}No symbols configured in config.py. Exiting the arcane ritual.{Style.RESET_ALL}")
        return

    mode_info = f"{Fore.MAGENTA}{Style.BRIGHT}DRY RUN{Style.RESET_ALL}" if BOT_CONFIG["DRY_RUN"] else f"{Fore.GREEN}{Style.BRIGHT}LIVE{Style.RESET_ALL}"
    testnet_info = f"{Fore.YELLOW}TESTNET{Style.RESET_ALL}" if BOT_CONFIG["TESTNET"] else f"{Fore.BLUE}MAINNET{Style.RESET_ALL}"
    logging.info(f"{Fore.CYAN}Starting trading bot in {mode_info} mode on {testnet_info}. Observing {len(symbols)} symbols.{Style.RESET_ALL}")

    # Dictionary to track active trades for time-based exit and SL/TP management
    # Format: {symbol: {'entry_time': datetime, 'order_id': str, 'side': str, 'entry_price': float, 'entry_qty': float, 'sl': float, 'tp': float}}
    active_trades_tracker: Dict[str, Dict[str, Any]] = {}
    closed_trades_history: List[Dict[str, Any]] = []
    cumulative_pnl: float = 0.0

    while True:
        local_time, utc_time = get_current_time(BOT_CONFIG["TIMEZONE"])
        logging.info(f"{Fore.WHITE}Local Time: {local_time.strftime('%Y-%m-%d %H:%M:%S')} | UTC Time: {utc_time.strftime('%Y-%m-%d %H:%M:%S')}{Style.RESET_ALL}")

        if not is_market_open(local_time, BOT_CONFIG["MARKET_OPEN_HOUR"], BOT_CONFIG["MARKET_CLOSE_HOUR"]):
            logging.info(f"{Fore.YELLOW}Market is closed ({BOT_CONFIG['MARKET_OPEN_HOUR']}:00-{BOT_CONFIG['MARKET_CLOSE_HOUR']}:00 {BOT_CONFIG['TIMEZONE']}). Skipping this cycle. Waiting {BOT_CONFIG['LOOP_WAIT_TIME_SECONDS']} seconds.{Style.RESET_ALL}")
            sleep(BOT_CONFIG['LOOP_WAIT_TIME_SECONDS'])
            continue
            
        balance = bybit_client.get_balance()
        if balance is None:
            logging.error(f'{Fore.RED}Cannot connect to API or get balance. Waiting {BOT_CONFIG["LOOP_WAIT_TIME_SECONDS"]} seconds and retrying.{Style.RESET_ALL}')
            send_termux_toast(f"Trading Bot Error: Cannot get balance. Check logs.")
            sleep(BOT_CONFIG['LOOP_WAIT_TIME_SECONDS'])
            continue
        
        logging.info(f'{Fore.LIGHTGREEN_EX}Current balance: {balance:.2f} USDT{Style.RESET_ALL}')
        
        current_positions = bybit_client.get_positions()
        logging.info(f'{Fore.LIGHTCYAN_EX}You have {len(current_positions)} open positions: {current_positions}{Style.RESET_ALL}')

        # --- Manage existing trades ---
        symbols_to_remove_from_tracker = []
        for symbol, trade_info in active_trades_tracker.items():
            # Check if position still exists (important for live trading)
            if not BOT_CONFIG["DRY_RUN"] and symbol not in current_positions:
                logging.info(f"{Fore.CYAN}Position for {symbol} closed (not in current_positions). Removing from tracker.{Style.RESET_ALL}")
                symbols_to_remove_from_tracker.append(symbol)
                continue

            # Time-based exit
            elapsed_seconds = (utc_time - trade_info['entry_time']).total_seconds()
            elapsed_candles = elapsed_seconds / (BOT_CONFIG["TIMEFRAME"] * 60)

            if elapsed_candles >= BOT_CONFIG["MAX_HOLDING_CANDLES"]:
                logging.info(f"{Fore.YELLOW}Position for {symbol} has exceeded MAX_HOLDING_CANDLES ({BOT_CONFIG['MAX_HOLDING_CANDLES']}). Attempting to close.{Style.RESET_ALL}")
                send_termux_toast(f"Closing {symbol}: Max holding candles reached.")
                bybit_client.cancel_all_open_orders(symbol) # Cancel pending orders first
                sleep(0.5)
                
                # Get current price for PnL calculation
                current_klines = bybit_client.klines(symbol, BOT_CONFIG["TIMEFRAME"], limit=1)
                exit_price = current_klines['Close'].iloc[-1] if not current_klines.empty else trade_info['entry_price'] # Fallback to entry price

                # Calculate PnL
                pnl = calculate_pnl(trade_info['side'], trade_info['entry_price'], exit_price, trade_info['entry_qty'])
                cumulative_pnl += pnl

                logging.info(f"{Fore.MAGENTA}Closed {symbol} due to MAX_HOLDING_CANDLES. PnL: {pnl:.4f} USDT. Cumulative PnL: {cumulative_pnl:.4f} USDT.{Style.RESET_ALL}")
                
                # Record closed trade
                closed_trades_history.append({
                    'symbol': symbol,
                    'side': trade_info['side'],
                    'entry_time': trade_info['entry_time'],
                    'entry_price': trade_info['entry_price'],
                    'entry_qty': trade_info['entry_qty'],
                    'exit_time': utc_time,
                    'exit_price': exit_price,
                    'pnl': pnl
                })

                bybit_client.close_position(symbol)
                symbols_to_remove_from_tracker.append(symbol)
                continue # Move to next trade

            # --- Dynamic Stop Loss and Take Profit Management ---
            # Re-fetch klines to get the latest Supertrend for SL adjustment
            # Fetch enough klines to ensure the latest Supertrend is calculated accurately
            kl_for_sl = bybit_client.klines(symbol, BOT_CONFIG["TIMEFRAME"], limit=BOT_CONFIG["MIN_KLINES_FOR_STRATEGY"] + 5) 
            if not kl_for_sl.empty:
                df_indicators_sl = calculate_ehl_supertrend_indicators(kl_for_sl)
                if not df_indicators_sl.empty:
                    last_row_sl = df_indicators_sl.iloc[-1]
                    current_st_slow_line = last_row_sl['st_slow_line']
                    current_price_for_sl = last_row_sl['Close']

                    if not pd.isna(current_st_slow_line) and not pd.isna(current_price_for_sl):
                        # Adjust SL only if it moves in favor of the trade and is more favorable than current SL
                        if trade_info['side'] == 'Buy' and current_price_for_sl > trade_info['entry_price']: # Ensure price has moved in profit
                            new_sl = current_st_slow_line
                            if new_sl > trade_info['sl']: # Trailing stop: only move SL up
                                new_sl = round(new_sl, price_precision) # Apply precision
                                logging.info(f"{Fore.CYAN}Trailing SL for {symbol} (Buy): Moving SL from {trade_info['sl']:.4f} to {new_sl:.4f}{Style.RESET_ALL}")
                                trade_info['sl'] = new_sl
                                # In a real scenario, you'd modify the order on the exchange here.
                                # For this script, we update the tracker and rely on the check below.
                        elif trade_info['side'] == 'Sell' and current_price_for_sl < trade_info['entry_price']: # Ensure price has moved in profit
                            new_sl = current_st_slow_line
                            if new_sl < trade_info['sl']: # Trailing stop: only move SL down
                                new_sl = round(new_sl, price_precision) # Apply precision
                                logging.info(f"{Fore.CYAN}Trailing SL for {symbol} (Sell): Moving SL from {trade_info['sl']:.4f} to {new_sl:.4f}{Style.RESET_ALL}")
                                trade_info['sl'] = new_sl
                                # Update order on exchange if needed.

                        # Check if current price hit SL or TP based on tracked values
                        # Use a small tolerance for floating point comparisons
                        tolerance = 1e-6 
                        if (trade_info['side'] == 'Buy' and current_price_for_sl <= trade_info['sl'] + tolerance) or \
                           (trade_info['side'] == 'Sell' and current_price_for_sl >= trade_info['sl'] - tolerance):
                            logging.warning(f"{Fore.RED}Position for {symbol} hit Stop Loss at {current_price_for_sl:.4f} (SL: {trade_info['sl']:.4f}).{Style.RESET_ALL}")
                            send_termux_toast(f"Trade Hit SL: {symbol}")
                            
                            # Calculate PnL
                            pnl = calculate_pnl(trade_info['side'], trade_info['entry_price'], current_price_for_sl, trade_info['entry_qty'])
                            cumulative_pnl += pnl
                            logging.info(f"{Fore.MAGENTA}Closed {symbol} due to SL. PnL: {pnl:.4f} USDT. Cumulative PnL: {cumulative_pnl:.4f} USDT.{Style.RESET_ALL}")

                            # Record closed trade
                            closed_trades_history.append({
                                'symbol': symbol,
                                'side': trade_info['side'],
                                'entry_time': trade_info['entry_time'],
                                'entry_price': trade_info['entry_price'],
                                'entry_qty': trade_info['entry_qty'],
                                'exit_time': utc_time,
                                'exit_price': current_price_for_sl,
                                'pnl': pnl
                            })

                            # Ensure position is closed if not already
                            if symbol in bybit_client.get_positions():
                                bybit_client.close_position(symbol)
                            symbols_to_remove_from_tracker.append(symbol)
                            continue
                        elif trade_info['tp'] is not None and \
                             ((trade_info['side'] == 'Buy' and current_price_for_sl >= trade_info['tp'] - tolerance) or \
                              (trade_info['side'] == 'Sell' and current_price_for_sl <= trade_info['tp'] + tolerance)):
                            logging.info(f"{Fore.GREEN}Position for {symbol} hit Take Profit at {current_price_for_sl:.4f} (TP: {trade_info['tp']:.4f}).{Style.RESET_ALL}")
                            send_termux_toast(f"Trade Hit TP: {symbol}")
                            
                            # Calculate PnL
                            pnl = calculate_pnl(trade_info['side'], trade_info['entry_price'], current_price_for_sl, trade_info['entry_qty'])
                            cumulative_pnl += pnl
                            logging.info(f"{Fore.MAGENTA}Closed {symbol} due to TP. PnL: {pnl:.4f} USDT. Cumulative PnL: {cumulative_pnl:.4f} USDT.{Style.RESET_ALL}")

                            # Record closed trade
                            closed_trades_history.append({
                                'symbol': symbol,
                                'side': trade_info['side'],
                                'entry_time': trade_info['entry_time'],
                                'entry_price': trade_info['entry_price'],
                                'entry_qty': trade_info['entry_qty'],
                                'exit_time': utc_time,
                                'exit_price': current_price_for_sl,
                                'pnl': pnl
                            })

                            # Ensure position is closed if not already
                            if symbol in bybit_client.get_positions():
                                bybit_client.close_position(symbol)
                            symbols_to_remove_from_tracker.append(symbol)
                            continue
            else:
                logging.warning(f"{Fore.YELLOW}Could not fetch klines for SL/TP check for {symbol}. Skipping SL/TP management for this cycle.{Style.RESET_ALL}")

        # Remove closed trades from tracker
        for symbol in symbols_to_remove_from_tracker:
            if symbol in active_trades_tracker:
                del active_trades_tracker[symbol]

        # --- Iterate through symbols for new trades ---
        for symbol in symbols:
            # Re-check positions and max_pos inside the loop, as positions can change
            current_positions = bybit_client.get_positions() 
            if len(current_positions) >= BOT_CONFIG["MAX_POSITIONS"]:
                logging.info(f"{Fore.YELLOW}Max positions ({BOT_CONFIG['MAX_POSITIONS']}) reached. Halting new signal checks for this cycle.{Style.RESET_ALL}")
                break # Exit the symbol loop, continue to next main loop iteration

            if symbol in current_positions:
                logging.debug(f"{Fore.BLUE}Skipping {symbol} as there is already an open position.{Style.RESET_ALL}")
                continue

            # Check for open orders for this symbol to avoid duplicate entries
            open_orders_for_symbol = bybit_client.get_open_orders(symbol)
            if len(open_orders_for_symbol) >= BOT_CONFIG["MAX_OPEN_ORDERS_PER_SYMBOL"]:
                logging.debug(f"{Fore.BLUE}Skipping {symbol} as there are {len(open_orders_for_symbol)} open orders (max {BOT_CONFIG['MAX_OPEN_ORDERS_PER_SYMBOL']}).{Style.RESET_ALL}")
                continue

            kl = bybit_client.klines(symbol, BOT_CONFIG["TIMEFRAME"])
            if kl.empty or len(kl) < BOT_CONFIG["MIN_KLINES_FOR_STRATEGY"]: # Ensure enough data for indicators
                logging.warning(f"{Fore.YELLOW}Not enough klines data for {symbol} (needed >{BOT_CONFIG['MIN_KLINES_FOR_STRATEGY']}). Skipping.{Style.RESET_ALL}")
                continue

            support, resistance = bybit_client.get_orderbook_levels(symbol)
            current_price = kl['Close'].iloc[-1]
            
            if support is None or resistance is None:
                logging.warning(f"{Fore.YELLOW}Could not retrieve orderbook levels for {symbol}. Skipping strategy check.{Style.RESET_ALL}")
                continue

            # --- Ehlers Supertrend Cross Strategy Signal Generation ---
            price_precision, qty_precision = bybit_client.get_precisions(symbol)
            final_signal, risk_distance, tp_price, sl_price, df_with_indicators, volume_confirm_from_signals = generate_ehl_supertrend_signals(kl, current_price, support, resistance, price_precision, qty_precision)

            # Extract current indicator values for logging (always display)
            if not df_with_indicators.empty:
                last_row_indicators = df_with_indicators.iloc[-1]
                log_details = (
                    f"Current Price: {Fore.WHITE}{current_price:.4f}{Style.RESET_ALL} | "
                    f"ST Fast ({BOT_CONFIG['EST_FAST_LENGTH']},{BOT_CONFIG['EST_FAST_MULTIPLIER']}): {Fore.CYAN}{last_row_indicators['st_fast_line']:.4f}{Style.RESET_ALL} | "
                    f"ST Slow ({BOT_CONFIG['EST_SLOW_LENGTH']},{BOT_CONFIG['EST_SLOW_MULTIPLIER']}): {Fore.CYAN}{last_row_indicators['st_slow_line']:.4f}{Style.RESET_ALL} | "
                    f"RSI ({BOT_CONFIG['RSI_PERIOD']}): {Fore.YELLOW}{last_row_indicators['rsi']:.2f}{Style.RESET_ALL} | "
                    f"Fisher: {Fore.MAGENTA}{last_row_indicators['fisher']:.2f}{Style.RESET_ALL} | "
                    f"Fisher Signal: {Fore.MAGENTA}{last_row_indicators['fisher_signal']:.2f}{Style.RESET_ALL} | "
                    f"Volume Spike: {Fore.GREEN if last_row_indicators['volume_spike'] else Fore.RED}{'Yes' if last_row_indicators['volume_spike'] else 'No'}{Style.RESET_ALL}"
                )
                logging.info(f"[{symbol}] Indicator Values: {log_details}") # Log for each symbol
            else:
                logging.warning(f"{Fore.YELLOW}[{symbol}] Indicator DataFrame is empty, cannot log current values.{Style.RESET_ALL}")
                continue # Skip if indicators couldn't be calculated

            # --- Order Placement Logic based on Final Signal ---
            # Ensure TP and SL are valid numbers and risk distance is positive
            is_valid_signal = (final_signal != 'none' and 
                               tp_price is not None and 
                               sl_price is not None and 
                               risk_distance is not None and 
                               risk_distance > 0)

            if is_valid_signal:
                # Determine specific reasoning for the signal
                reasoning = []
                if final_signal == 'Buy':
                    reasoning.append(f"Trend Confirmed (Slow ST > 0)")
                    reasoning.append(f"Fast ST ({last_row_indicators['st_fast_line']:.4f}) crossed above Slow ST ({last_row_indicators['st_slow_line']:.4f})")
                    
                    confirmations_list = []
                    if last_row_indicators['fisher'] > last_row_indicators['fisher_signal']:
                        confirmations_list.append("Fisher > Signal")
                    if last_row_indicators['rsi'] > BOT_CONFIG.get("RSI_CONFIRM_LONG_THRESHOLD", 55):
                        confirmations_list.append(f"RSI > {BOT_CONFIG.get("RSI_CONFIRM_LONG_THRESHOLD", 55)}")
                    if volume_confirm_from_signals:
                        confirmations_list.append("Volume Spike")
                    reasoning.append(f"Confirmations ({len(confirmations_list)}/3): {", ".join(confirmations_list)}")
                    
                    logging.info(f'{Fore.GREEN}{Style.BRIGHT}BUY SIGNAL for {symbol} 📈{Style.RESET_ALL}')
                    logging.info(f'{Fore.GREEN}Reasoning: {"; ".join(reasoning)}{Style.RESET_ALL}')
                    logging.info(f'{Fore.GREEN}Calculated TP: {tp_price:.4f}, SL: {sl_price:.4f} (Risk Distance: {risk_distance:.4f}){Style.RESET_ALL}')
                    send_termux_toast(f"BUY Signal: {symbol}")

                    # Calculate position size based on risk per trade
                    capital_for_risk = balance 
                    risk_amount_usdt = capital_for_risk * BOT_CONFIG["RISK_PER_TRADE_PCT"]
                    
                    order_qty_risk_based = risk_amount_usdt / risk_distance
                    order_qty_from_usdt = BOT_CONFIG["ORDER_QTY_USDT"] / current_price
                    
                    order_qty = min(order_qty_risk_based, order_qty_from_usdt)
                    order_qty = round(order_qty, qty_precision) # Ensure final rounding
                    
                    if order_qty <= 0:
                        logging.warning(f"{Fore.YELLOW}Calculated order quantity for {symbol} is zero or negative ({order_qty:.{qty_precision}f}). Skipping order.{Style.RESET_ALL}")
                        continue

                    bybit_client.set_margin_mode_and_leverage(
                        symbol, BOT_CONFIG["MARGIN_MODE"], BOT_CONFIG["LEVERAGE"]
                    )
                    sleep(0.5) # Give API a moment to process

                    order_id = None
                    # --- Order Placement Strategy ---
                    # Prioritize limit orders near support if applicable
                    if support and abs(current_price - support) < (current_price * BOT_CONFIG["PRICE_DETECTION_THRESHOLD_PCT"]):
                        logging.info(f"{Fore.BLUE}Price near support at {support:.4f}. Placing Limit Order to Buy at support.{Style.RESET_ALL}")
                        order_id = bybit_client.place_limit_order(
                            symbol=symbol, side='Buy', price=support, qty=order_qty,
                            tp_price=tp_price, sl_price=sl_price
                        )
                    # Else, consider breakout if price is above resistance (less common for trend following, but possible)
                    elif resistance and current_price > resistance and current_price > last_row_indicators['st_fast_line']: # Ensure price is also above ST
                        logging.info(f"{Fore.BLUE}Price broken above resistance at {resistance:.4f}. Placing Conditional Market Order for breakout.{Style.RESET_ALL}")
                        trigger_price = current_price * (1 + BOT_CONFIG["BREAKOUT_TRIGGER_PCT"]) # Use constant
                        order_id = bybit_client.place_conditional_order(
                            symbol=symbol, side='Buy', qty=order_qty, trigger_price=trigger_price,
                            order_type='Market', tp_price=tp_price, sl_price=sl_price
                        )
                    # Default to Market Order if no S/R condition met or if it's a strong trend signal
                    else:
                        logging.info(f"{Fore.BLUE}No specific S/R condition met or strong trend. Placing Market Order to Buy.{Style.RESET_ALL}")
                        order_id = bybit_client.place_market_order(
                            symbol=symbol, side='Buy', qty=order_qty,
                            tp_price=tp_price, sl_price=sl_price
                        )
                
                elif final_signal == 'Sell':
                    reasoning.append(f"Trend Confirmed (Slow ST < 0)")
                    reasoning.append(f"Fast ST ({last_row_indicators['st_fast_line']:.4f}) crossed below Slow ST ({last_row_indicators['st_slow_line']:.4f})")
                    
                    confirmations_list = []
                    if last_row_indicators['fisher'] < last_row_indicators['fisher_signal']:
                        confirmations_list.append("Fisher < Signal")
                    if last_row_indicators['rsi'] < BOT_CONFIG.get("RSI_CONFIRM_SHORT_THRESHOLD", 45):
                        confirmations_list.append(f"RSI < {BOT_CONFIG.get("RSI_CONFIRM_SHORT_THRESHOLD", 45)}")
                    if volume_confirm_from_signals:
                        confirmations_list.append("Volume Spike")
                    reasoning.append(f"Confirmations ({len(confirmations_list)}/3): {", ".join(confirmations_list)}")

                    logging.info(f'{Fore.RED}{Style.BRIGHT}SELL SIGNAL for {symbol} 📉{Style.RESET_ALL}')
                    logging.info(f'{Fore.RED}Reasoning: {"; ".join(reasoning)}{Style.RESET_ALL}')
                    logging.info(f'{Fore.RED}Calculated TP: {tp_price:.4f}, SL: {sl_price:.4f} (Risk Distance: {risk_distance:.4f}){Style.RESET_ALL}')
                    send_termux_toast(f"SELL Signal: {symbol}")

                    # Calculate position size based on risk per trade
                    capital_for_risk = balance 
                    risk_amount_usdt = capital_for_risk * BOT_CONFIG["RISK_PER_TRADE_PCT"]
                    
                    order_qty_risk_based = risk_amount_usdt / risk_distance
                    order_qty_from_usdt = BOT_CONFIG["ORDER_QTY_USDT"] / current_price
                    
                    order_qty = min(order_qty_risk_based, order_qty_from_usdt)
                    order_qty = round(order_qty, qty_precision) # Ensure final rounding
                    
                    if order_qty <= 0:
                        logging.warning(f"{Fore.YELLOW}Calculated order quantity for {symbol} is zero or negative ({order_qty:.{qty_precision}f}). Skipping order.{Style.RESET_ALL}")
                        continue

                    bybit_client.set_margin_mode_and_leverage(
                        symbol, BOT_CONFIG["MARGIN_MODE"], BOT_CONFIG["LEVERAGE"]
                    )
                    sleep(0.5) # Give API a moment to process

                    order_id = None
                    # --- Order Placement Strategy ---
                    # Prioritize limit orders near resistance if applicable
                    if resistance and abs(current_price - resistance) < (current_price * BOT_CONFIG["PRICE_DETECTION_THRESHOLD_PCT"]):
                        logging.info(f"{Fore.MAGENTA}Price near resistance at {resistance:.4f}. Placing Limit Order to Sell at resistance.{Style.RESET_ALL}")
                        order_id = bybit_client.place_limit_order(
                            symbol=symbol, side='Sell', price=resistance, qty=order_qty,
                            tp_price=tp_price, sl_price=sl_price
                        )
                    # Else, consider breakdown if price is below support
                    elif support and current_price < support and current_price < last_row_indicators['st_fast_line']: # Ensure price is also below ST
                        logging.info(f"{Fore.MAGENTA}Price broken below support at {support:.4f}. Placing Conditional Market Order for breakdown.{Style.RESET_ALL}")
                        trigger_price = current_price * (1 - BOT_CONFIG["BREAKDOWN_TRIGGER_PCT"]) # Use constant
                        order_id = bybit_client.place_conditional_order(
                            symbol=symbol, side='Sell', qty=order_qty, trigger_price=trigger_price,
                            order_type='Market', tp_price=tp_price, sl_price=sl_price
                        )
                    # Default to Market Order if no S/R condition met or if it's a strong trend signal
                    else:
                        logging.info(f"{Fore.MAGENTA}No specific S/R condition met or strong trend. Placing Market Order to Sell.{Style.RESET_ALL}")
                        order_id = bybit_client.place_market_order(
                            symbol=symbol, side='Sell', qty=order_qty,
                            tp_price=tp_price, sl_price=sl_price
                        )
                
                # --- Track the Trade ---
                if order_id:
                    # Attempt to get order details to confirm entry price
                    order_details = bybit_client.get_order_status(symbol, order_id)
                    entry_price = current_price # Default to current price if order not filled/confirmed yet
                    if order_details and order_details.get('orderStatus') == 'Filled':
                        entry_price = float(order_details.get('avgPrice', current_price))
                        logging.info(f"{Fore.GREEN}Order {order_id} filled at {entry_price:.4f}.{Style.RESET_ALL}")
                    elif order_details:
                        logging.warning(f"{Fore.YELLOW}Order {order_id} placed but not yet filled (Status: {order_details.get('orderStatus')}). Using current price {current_price:.4f} as entry estimate.{Style.RESET_ALL}")
                    else:
                        logging.warning(f"{Fore.YELLOW}Could not confirm order {order_id} status immediately. Using current price {current_price:.4f} as entry estimate.{Style.RESET_ALL}")

                    active_trades_tracker[symbol] = {
                        'entry_time': utc_time, # Store UTC time of order placement
                        'order_id': order_id,
                        'side': final_signal,
                        'entry_price': entry_price, # Store estimated entry price
                        'entry_qty': order_qty, # Store entry quantity
                        'sl': sl_price, # Store initial SL
                        'tp': tp_price  # Store initial TP
                    }
            else:
                logging.debug(f"{Fore.BLUE}No strong combined trading signal or invalid TP/SL/Risk for {symbol}.{Style.RESET_ALL}")


        logging.info(f'{Fore.MAGENTA}{Style.BRIGHT}--- Cycle finished. Waiting {BOT_CONFIG["LOOP_WAIT_TIME_SECONDS"]} seconds for next loop. Cumulative PnL: {cumulative_pnl:.4f} USDT ---{Style.RESET_ALL}')
        sleep(BOT_CONFIG['LOOP_WAIT_TIME_SECONDS'])

if __name__ == "__main__":
    # --- Initial Setup and Checks ---
    # Ensure Termux:API is installed if toasts are desired
    if sys.platform.startswith('linux') and os.environ.get('TERMUX_VERSION'):
        try:
            # Check if termux-toast command exists using subprocess
            import subprocess
            result = subprocess.run(['command', '-v', 'termux-toast'], capture_output=True, text=True)
            if result.returncode != 0: # Command not found
                logging.warning(f"{Fore.YELLOW}Termux:API 'termux-toast' command not found. Install Termux:API app and run 'pkg install termux-api' for notifications.{Style.RESET_ALL}")
        except FileNotFoundError:
             logging.warning(f"{Fore.YELLOW}Termux:API 'termux-toast' command not found (FileNotFoundError). Install Termux:API app and run 'pkg install termux-api' for notifications.{Style.RESET_ALL}")
        except Exception as e:
            logging.error(f"{Fore.RED}An unexpected error occurred while checking for termux-toast: {e}{Style.RESET_ALL}")

    main()

