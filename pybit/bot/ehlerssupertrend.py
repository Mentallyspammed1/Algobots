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
import yaml  # Pyrmethus's touch: Import the YAML grimoire reader
from typing import Optional, Tuple, Dict, Any, List

# Import from pybit
from pybit.unified_trading import HTTP

# --- Custom Colored Logging Formatter ---
from colorama import init, Fore, Style

init(autoreset=True)

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
        logging.INFO: WHITE + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + RESET,
        logging.WARNING: YELLOW + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + RESET,
        logging.ERROR: RED + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + RESET,
        logging.CRITICAL: BOLD + RED + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + RESET
    }

    def format(self, record):
        if sys.stdout.isatty():
            log_fmt = self.FORMATS.get(record.levelno)
        else:
            log_fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        
        formatter = logging.Formatter(log_fmt, datefmt='%Y-%m-%d %H:%M:%S')
        return formatter.format(record)

# --- YAML Configuration Loading ---
def load_config(config_path="config.yaml") -> Dict[str, Any]:
    """
    # Summons the settings from the YAML grimoire, merging them with secrets from the environment.
    """
    try:
        with open(config_path, 'r') as file:
            config = yaml.safe_load(file)
            logging.info(f"{Fore.GREEN}Successfully summoned configuration from {config_path}.{Style.RESET_ALL}")
    except FileNotFoundError:
        logging.error(f"{Fore.RED}The arcane grimoire 'config.yaml' was not found. The ritual cannot proceed.{Style.RESET_ALL}")
        sys.exit(1)
    except yaml.YAMLError as e:
        logging.error(f"{Fore.RED}The 'config.yaml' grimoire is corrupted: {e}. The ritual is halted.{Style.RESET_ALL}")
        sys.exit(1)

    # Sourcing secrets from the ether (environment variables)
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")

    if not api_key or not api_secret:
        logging.warning(f"{Fore.YELLOW}BYBIT_API_KEY or BYBIT_API_SECRET not found in the environment. Dry run is enforced.{Style.RESET_ALL}")
        config['api']['dry_run'] = True # Enforce dry_run if keys are missing
    
    config['api']['key'] = api_key
    config['api']['secret'] = api_secret
    
    return config

# --- Logging Setup ---
root_logger = logging.getLogger()
if root_logger.hasHandlers():
    root_logger.handlers.clear()

handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter())
root_logger.addHandler(handler)

# Load config and set log level immediately
CONFIG = load_config()
root_logger.setLevel(getattr(logging, CONFIG['bot']['log_level'].upper(), "INFO"))


# --- Bybit Client Class ---
class Bybit:
    """
    # The Bybit Oracle: A conduit to the exchange's data and execution realms.
    # Now allows live data fetching in dry run mode for realistic paper trading.
    """
    def __init__(self, api: str, secret: str, testnet: bool = False, dry_run: bool = False):
        self.api = api
        self.secret = secret
        self.testnet = testnet
        self.dry_run = dry_run
        self.session = None
        self._dry_run_positions = {}

        # Initialize session for data fetching even in dry_run, if keys are provided
        if self.api and self.secret:
            self.session = HTTP(api_key=self.api, api_secret=self.secret, testnet=self.testnet)
            logging.info(f"{Fore.CYAN}HTTP session initialized for data fetching.{Style.RESET_ALL}")
        else:
            logging.warning(f"{Fore.YELLOW}API keys not found. Live data fetching is disabled.{Style.RESET_ALL}")

        logging.info(f"{Fore.CYAN}Bybit client configured. Testnet: {self.testnet}, Dry Run: {self.dry_run}{Style.RESET_ALL}")

    def get_balance(self, coin: str = "USDT") -> Optional[float]:
        """Fetches wallet balance. In dry run, returns a fixed amount if no session, otherwise fetches real balance."""
        if not self.session:
            logging.debug(f"{Fore.BLUE}[DRY RUN] No API session. Simulated balance: 10000.00 USDT.{Style.RESET_ALL}")
            return 10000.00
        try:
            resp = self.session.get_wallet_balance(accountType="UNIFIED", coin=coin)
            if resp['retCode'] == 0 and resp['result']['list']:
                balance_data_list = resp['result']['list'][0]['coin']
                for coin_data in balance_data_list:
                    if coin_data['coin'] == coin:
                        balance = float(coin_data['walletBalance'])
                        logging.debug(f"{Fore.BLUE}Fetched balance: {balance} {coin}{Style.RESET_ALL}")
                        return balance
                logging.warning(f"{Fore.YELLOW}No balance data found for coin {coin}.{Style.RESET_ALL}")
                return 0.0
            else:
                logging.error(f"{Fore.RED}Error getting balance: {resp.get('retMsg', 'Unknown error')}{Style.RESET_ALL}")
                return None
        except Exception as err:
            logging.error(f"{Fore.RED}Exception getting balance: {err}{Style.RESET_ALL}")
            return None

    def get_positions(self, settleCoin: str = "USDT") -> List[str]:
        """Returns a list of symbols with open positions. Uses internal tracker for dry run."""
        if self.dry_run:
            open_symbols = list(self._dry_run_positions.keys())
            logging.debug(f"{Fore.BLUE}[DRY RUN] Fetched open positions from internal tracker: {open_symbols}{Style.RESET_ALL}")
            return open_symbols
        if not self.session: return []
        try:
            resp = self.session.get_positions(category='linear', settleCoin=settleCoin)
            if resp['retCode'] == 0:
                return [elem['symbol'] for elem in resp['result']['list'] if float(elem.get('size', 0)) > 0]
            else:
                logging.error(f"{Fore.RED}Error getting positions: {resp.get('retMsg', 'Unknown error')}{Style.RESET_ALL}")
                return []
        except Exception as err:
            logging.error(f"{Fore.RED}Exception getting positions: {err}{Style.RESET_ALL}")
            return []

    def get_tickers(self) -> Optional[List[str]]:
        """Retrieves all USDT perpetual linear symbols from the derivatives market."""
        if not self.session:
            logging.debug(f"{Fore.BLUE}[DRY RUN] No API session. Returning symbols from config.{Style.RESET_ALL}")
            return CONFIG['trading']['trading_symbols']
        try:
            resp = self.session.get_tickers(category="linear")
            if resp['retCode'] == 0:
                return [elem['symbol'] for elem in resp['result']['list'] if 'USDT' in elem['symbol'] and 'USDC' not in elem['symbol']]
            else:
                logging.error(f"{Fore.RED}Error getting tickers: {resp.get('retMsg', 'Unknown error')}{Style.RESET_ALL}")
                return None
        except Exception as err:
            logging.error(f"{Fore.RED}Exception getting tickers: {err}{Style.RESET_ALL}")
            return None

    def klines(self, symbol: str, timeframe: int, limit: int = 500) -> pd.DataFrame:
        """Fetches klines (candlestick data). Fetches real data regardless of dry_run mode if session is available."""
        if not self.session:
            logging.error(f"{Fore.RED}Cannot fetch klines for {symbol}. No API session available.{Style.RESET_ALL}")
            return pd.DataFrame()
        try:
            resp = self.session.get_kline(category='linear', symbol=symbol, interval=str(timeframe), limit=limit)
            if resp['retCode'] == 0 and resp['result']['list']:
                klines_dtypes = {'Time': 'int64', 'Open': 'float64', 'High': 'float64', 'Low': 'float64', 'Close': 'float64', 'Volume': 'float64', 'Turnover': 'float64'}
                df = pd.DataFrame(resp['result']['list'], columns=klines_dtypes.keys()).astype(klines_dtypes)
                df['Time'] = pd.to_datetime(df['Time'], unit='ms')
                df = df.set_index('Time').sort_index()
                if df[['Open', 'High', 'Low', 'Close']].isnull().values.any():
                    logging.warning(f"{Fore.YELLOW}NaN values found in OHLC for {symbol}. Discarding klines.{Style.RESET_ALL}")
                    return pd.DataFrame()
                logging.debug(f"{Fore.BLUE}Fetched {len(df)} klines for {symbol} ({timeframe}min).{Style.RESET_ALL}")
                return df
            else:
                logging.error(f"{Fore.RED}Error getting klines for {symbol}: {resp.get('retMsg', 'No data')}{Style.RESET_ALL}")
                return pd.DataFrame()
        except Exception as err:
            logging.error(f"{Fore.RED}Exception getting klines for {symbol}: {err}{Style.RESET_ALL}")
            return pd.DataFrame()

    def get_orderbook_levels(self, symbol: str, limit: int = 50) -> Tuple[Optional[float], Optional[float]]:
        """Analyzes the order book to find strong support and resistance levels."""
        if not self.session: return None, None
        try:
            resp = self.session.get_orderbook(category='linear', symbol=symbol, limit=limit)
            if resp['retCode'] == 0 and resp['result']:
                bids = pd.DataFrame(resp['result'].get('b', []), columns=['price', 'volume']).astype(float)
                asks = pd.DataFrame(resp['result'].get('a', []), columns=['price', 'volume']).astype(float)
                strong_support = bids.loc[bids['volume'].idxmax()]['price'] if not bids.empty else None
                strong_resistance = asks.loc[asks['volume'].idxmax()]['price'] if not asks.empty else None
                return strong_support, strong_resistance
            else:
                logging.error(f"{Fore.RED}Error getting orderbook for {symbol}: {resp.get('retMsg', 'Unknown error')}{Style.RESET_ALL}")
                return None, None
        except Exception as err:
            logging.error(f"{Fore.RED}Exception getting orderbook for {symbol}: {err}{Style.RESET_ALL}")
            return None, None

    def get_precisions(self, symbol: str) -> Tuple[int, int]:
        """Retrieves the decimal precision for price and quantity."""
        if not self.session: return 2, 3 # Default precisions if no session
        try:
            resp = self.session.get_instruments_info(category='linear', symbol=symbol)
            if resp['retCode'] == 0 and resp['result']['list']:
                info = resp['result']['list'][0]
                price_precision = len(info['priceFilter']['tickSize'].split('.')[1]) if '.' in info['priceFilter']['tickSize'] else 0
                qty_precision = len(info['lotSizeFilter']['qtyStep'].split('.')[1]) if '.' in info['lotSizeFilter']['qtyStep'] else 0
                return price_precision, qty_precision
            else:
                logging.error(f"{Fore.RED}Error getting precisions for {symbol}: {resp.get('retMsg', 'Unknown error')}{Style.RESET_ALL}")
                return 2, 3
        except Exception as err:
            logging.error(f"{Fore.RED}Exception getting precisions for {symbol}: {err}{Style.RESET_ALL}")
            return 2, 3

    def set_margin_mode_and_leverage(self, symbol: str, mode: int, leverage: int) -> None:
        if self.dry_run:
            logging.info(f"{Fore.MAGENTA}[DRY RUN] Would set margin mode to {'Isolated' if mode==1 else 'Cross'} and leverage to {leverage}x for {symbol}.{Style.RESET_ALL}")
            return
        try:
            resp = self.session.switch_margin_mode(category='linear', symbol=symbol, tradeMode=str(mode), buyLeverage=str(leverage), sellLeverage=str(leverage))
            if resp['retCode'] == 0:
                logging.info(f"{Fore.GREEN}Margin mode set and leverage set to {leverage}x for {symbol}.{Style.RESET_ALL}")
            elif resp['retCode'] in [110026, 110043]:
                logging.debug(f"{Fore.YELLOW}Margin mode or leverage already set for {symbol}.{Style.RESET_ALL}")
            else:
                logging.warning(f"{Fore.YELLOW}Failed to set margin mode/leverage for {symbol}: {resp.get('retMsg', 'Unknown error')}{Style.RESET_ALL}")
        except Exception as err:
            logging.error(f"{Fore.RED}Exception setting margin mode/leverage for {symbol}: {err}{Style.RESET_ALL}")

    def place_order_common(self, symbol: str, side: str, order_type: str, qty: float, price: Optional[float] = None, trigger_price: Optional[float] = None, tp_price: Optional[float] = None, sl_price: Optional[float] = None, time_in_force: str = 'GTC') -> Optional[str]:
        if self.dry_run:
            dummy_order_id = f"DRY_RUN_ORDER_{uuid.uuid4()}"
            log_msg = f"{Fore.MAGENTA}[DRY RUN] Would place order for {symbol} ({order_type} {side} {qty:.6f})"
            if price is not None: log_msg += f" at price {price:.6f}"
            if tp_price is not None: log_msg += f" with TP {tp_price:.6f}"
            if sl_price is not None: log_msg += f" and SL {sl_price:.6f}"
            logging.info(f"{log_msg}. Simulated Order ID: {dummy_order_id}{Style.RESET_ALL}")
            self._dry_run_positions[symbol] = {'side': side, 'size': qty}
            return dummy_order_id
        try:
            price_precision, qty_precision = self.get_precisions(symbol)
            params = {'category': 'linear', 'symbol': symbol, 'side': side, 'orderType': order_type, 'qty': f"{qty:.{qty_precision}f}", 'timeInForce': time_in_force}
            if price is not None: params['price'] = f"{price:.{price_precision}f}"
            if trigger_price is not None: params['triggerPrice'] = f"{trigger_price:.{price_precision}f}"; params['triggerBy'] = 'MarkPrice'
            if tp_price is not None: params['takeProfit'] = f"{tp_price:.{price_precision}f}"; params['tpTriggerBy'] = 'Market'
            if sl_price is not None: params['stopLoss'] = f"{sl_price:.{price_precision}f}"; params['slTriggerBy'] = 'Market'
            response = self.session.place_order(**params)
            if response['retCode'] == 0:
                order_id = response['result']['orderId']
                logging.info(f"{Fore.GREEN}Order placed for {symbol}. Order ID: {order_id}{Style.RESET_ALL}")
                return order_id
            else:
                logging.error(f"{Fore.RED}Failed to place order for {symbol}: {response.get('retMsg', 'Unknown error')}{Style.RESET_ALL}")
                return None
        except Exception as err:
            logging.error(f"{Fore.RED}Exception placing order for {symbol}: {err}{Style.RESET_ALL}")
            return None

    def place_market_order(self, symbol: str, side: str, qty: float, tp_price: Optional[float] = None, sl_price: Optional[float] = None) -> Optional[str]:
        return self.place_order_common(symbol, side, 'Market', qty, tp_price=tp_price, sl_price=sl_price)

    def place_limit_order(self, symbol: str, side: str, price: float, qty: float, tp_price: Optional[float] = None, sl_price: Optional[float] = None, time_in_force: str = 'GTC') -> Optional[str]:
        return self.place_order_common(symbol, side, 'Limit', qty, price=price, tp_price=tp_price, sl_price=sl_price, time_in_force=time_in_force)

    def place_conditional_order(self, symbol: str, side: str, qty: float, trigger_price: float, order_type: str = 'Market', price: Optional[float] = None, tp_price: Optional[float] = None, sl_price: Optional[float] = None) -> Optional[str]:
        if order_type == 'Limit' and price is None:
            price = trigger_price
            logging.warning(f"{Fore.YELLOW}Conditional limit order for {symbol} using trigger_price as limit price.{Style.RESET_ALL}")
        return self.place_order_common(symbol, side, order_type, qty, price=price, trigger_price=trigger_price, tp_price=tp_price, sl_price=sl_price)

    def cancel_all_open_orders(self, symbol: str) -> Dict[str, Any]:
        if self.dry_run:
            logging.info(f"{Fore.MAGENTA}[DRY RUN] Would cancel all open orders for {symbol}.{Style.RESET_ALL}")
            return {'retCode': 0, 'retMsg': 'OK'}
        try:
            response = self.session.cancel_all_orders(category='linear', symbol=symbol)
            if response['retCode'] == 0:
                logging.info(f"{Fore.GREEN}All open orders for {symbol} cancelled.{Style.RESET_ALL}")
            else:
                logging.warning(f"{Fore.YELLOW}Failed to cancel orders for {symbol}: {response.get('retMsg', 'Unknown error')}{Style.RESET_ALL}")
            return response
        except Exception as err:
            logging.error(f"{Fore.RED}Exception cancelling orders for {symbol}: {err}{Style.RESET_ALL}")
            return {'retCode': -1, 'retMsg': str(err)}

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        if self.dry_run:
            return []
        try:
            params = {'category': 'linear'}
            if symbol: params['symbol'] = symbol
            response = self.session.get_open_orders(**params)
            if response['retCode'] == 0:
                return response['result']['list']
            else:
                logging.error(f"{Fore.RED}Error getting open orders: {response.get('retMsg', 'Unknown error')}{Style.RESET_ALL}")
                return []
        except Exception as err:
            logging.error(f"{Fore.RED}Exception getting open orders: {err}{Style.RESET_ALL}")
            return []

    def get_order_status(self, symbol: str, order_id: str) -> Optional[Dict[str, Any]]:
        if self.dry_run:
            logging.info(f"{Fore.MAGENTA}[DRY RUN] Would check status for order ID {order_id}.{Style.RESET_ALL}")
            return {'orderId': order_id, 'status': 'Filled', 'symbol': symbol, 'side': 'Buy', 'execQty': '0.001', 'avgPrice': '30000.00'}
        try:
            response = self.session.get_order_info(category='linear', symbol=symbol, orderId=order_id)
            if response['retCode'] == 0 and 'result' in response and response['result']['list']:
                return response['result']['list'][0]
            else:
                logging.error(f"{Fore.RED}Error getting order status for {order_id}: {response.get('retMsg', 'Unknown error')}{Style.RESET_ALL}")
                return None
        except Exception as err:
            logging.error(f"{Fore.RED}Exception getting order status for {order_id}: {err}{Style.RESET_ALL}")
            return None

    def close_position(self, symbol: str, position_idx: int = 0) -> Optional[str]:
        if self.dry_run:
            logging.info(f"{Fore.MAGENTA}[DRY RUN] Would close position for {symbol}.{Style.RESET_ALL}")
            if symbol in self._dry_run_positions:
                del self._dry_run_positions[symbol]
            return f"DRY_RUN_CLOSE_ORDER_{uuid.uuid4()}"
        try:
            positions_resp = self.session.get_positions(category='linear', symbol=symbol)
            if positions_resp['retCode'] != 0 or not positions_resp['result']['list']:
                logging.warning(f"{Fore.YELLOW}Could not get position details for {symbol} to close.{Style.RESET_ALL}")
                return None
            position_info = next((pos for pos in positions_resp['result']['list'] if float(pos['size']) > 0), None)
            if not position_info:
                logging.info(f"{Fore.CYAN}No open position found for {symbol} to close.{Style.RESET_ALL}")
                return None
            close_side = 'Sell' if position_info['side'] == 'Buy' else 'Buy'
            order_id = self.place_market_order(symbol=symbol, side=close_side, qty=float(position_info['size']))
            if order_id:
                logging.info(f"{Fore.GREEN}Market order placed to close {symbol} position. Order ID: {order_id}{Style.RESET_ALL}")
                return order_id
            else:
                logging.error(f"{Fore.RED}Failed to place market order to close {symbol} position.{Style.RESET_ALL}")
                return None
        except Exception as err:
            logging.error(f"{Fore.RED}Exception closing position for {symbol}: {err}{Style.RESET_ALL}")
            return None

# --- API Session Initialization ---
try:
    bybit_client = Bybit(
        api=CONFIG['api']['key'],
        secret=CONFIG['api']['secret'],
        testnet=CONFIG['api']['testnet'],
        dry_run=CONFIG['api']['dry_run']
    )
    mode_info = f"{Fore.MAGENTA}{Style.BRIGHT}DRY RUN{Style.RESET_ALL}" if CONFIG['api']['dry_run'] else f"{Fore.GREEN}{Style.BRIGHT}LIVE{Style.RESET_ALL}"
    testnet_info = f"{Fore.YELLOW}TESTNET{Style.RESET_ALL}" if CONFIG['api']['testnet'] else f"{Fore.BLUE}MAINNET{Style.RESET_ALL}"
    logging.info(f"{Fore.LIGHTYELLOW_EX}Successfully connected to Bybit API in {mode_info} mode on {testnet_info}.{Style.RESET_ALL}")
    logging.debug(f"{Fore.CYAN}Bot configuration: {CONFIG}{Style.RESET_ALL}")
except Exception as e:
    logging.error(f"{Fore.RED}Failed to connect to Bybit API: {e}{Style.RESET_ALL}")
    sys.exit(1)

# --- Helper Functions ---
def get_current_time(timezone_str: str) -> Tuple[datetime.datetime, datetime.datetime]:
    try:
        tz = pytz.timezone(timezone_str)
        local_time = datetime.datetime.now(tz)
        utc_time = datetime.datetime.now(pytz.utc)
        return local_time, utc_time
    except pytz.UnknownTimeZoneError:
        logging.error(f"{Fore.RED}Unknown timezone: '{timezone_str}'. Defaulting to UTC.{Style.RESET_ALL}")
        return datetime.datetime.now(pytz.utc), datetime.datetime.now(pytz.utc)

def is_market_open(local_time: datetime.datetime, open_hour: int, close_hour: int) -> bool:
    current_hour = local_time.hour
    open_hour_int, close_hour_int = int(open_hour), int(close_hour)
    if open_hour_int < close_hour_int:
        return open_hour_int <= current_hour < close_hour_int
    else:
        return current_hour >= open_hour_int or current_hour < close_hour_int

def send_termux_toast(message: str) -> None:
    if sys.platform.startswith('linux') and os.environ.get('TERMUX_VERSION'):
        try:
            import subprocess
            subprocess.run(['termux-toast', message], check=True)
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            logging.warning(f"{Fore.YELLOW}Could not send Termux toast: {e}{Style.RESET_ALL}")

def calculate_pnl(side: str, entry_price: float, exit_price: float, qty: float) -> float:
    return (exit_price - entry_price) * qty if side == 'Buy' else (entry_price - exit_price) * qty

# --- Strategy Section ---
def calculate_ehl_supertrend_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce').ffill().fillna(0)

    try:
        st_fast = ta.supertrend(high=df['High'], low=df['Low'], close=df['Close'], length=CONFIG['strategy']['est_fast']['length'], multiplier=CONFIG['strategy']['est_fast']['multiplier'])
        df['st_fast_line'] = st_fast[f"SUPERT_{CONFIG['strategy']['est_fast']['length']}_{CONFIG['strategy']['est_fast']['multiplier']}"]
        df['st_fast_direction'] = st_fast[f"SUPERTd_{CONFIG['strategy']['est_fast']['length']}_{CONFIG['strategy']['est_fast']['multiplier']}"]
    except Exception as e:
        logging.error(f"{Fore.RED}Error calculating fast Supertrend: {e}{Style.RESET_ALL}")
        df['st_fast_line'], df['st_fast_direction'] = np.nan, np.nan

    try:
        st_slow = ta.supertrend(high=df['High'], low=df['Low'], close=df['Close'], length=CONFIG['strategy']['est_slow']['length'], multiplier=CONFIG['strategy']['est_slow']['multiplier'])
        df['st_slow_line'] = st_slow[f"SUPERT_{CONFIG['strategy']['est_slow']['length']}_{CONFIG['strategy']['est_slow']['multiplier']}"]
        df['st_slow_direction'] = st_slow[f"SUPERTd_{CONFIG['strategy']['est_slow']['length']}_{CONFIG['strategy']['est_slow']['multiplier']}"]
    except Exception as e:
        logging.error(f"{Fore.RED}Error calculating slow Supertrend: {e}{Style.RESET_ALL}")
        df['st_slow_line'], df['st_slow_direction'] = np.nan, np.nan

    try:
        df['rsi'] = ta.rsi(close=df['Close'], length=CONFIG['strategy']['rsi']['period'])
    except Exception as e:
        logging.error(f"{Fore.RED}Error calculating RSI: {e}{Style.RESET_ALL}")
        df['rsi'] = np.nan

    try:
        volume_ma = ta.sma(close=df['Volume'], length=CONFIG['strategy']['volume']['ma_period'])
        df['volume_ma'] = volume_ma
        df['volume_spike'] = (df['Volume'] / volume_ma) > CONFIG['strategy']['volume']['threshold_multiplier'] if not volume_ma.isnull().all() else False
    except Exception as e:
        logging.error(f"{Fore.RED}Error calculating Volume MA: {e}{Style.RESET_ALL}")
        df['volume_ma'], df['volume_spike'] = np.nan, False

    try:
        fisher = ta.fisher(high=df['High'], low=df['Low'], length=CONFIG['strategy']['ehlers_fisher']['period'])
        df['fisher'] = fisher[f"FISHERT_{CONFIG['strategy']['ehlers_fisher']['period']}_1"]
        df['fisher_signal'] = fisher[f"FISHERTs_{CONFIG['strategy']['ehlers_fisher']['period']}_1"]
    except Exception as e:
        logging.error(f"{Fore.RED}Error calculating Fisher Transform: {e}{Style.RESET_ALL}")
        df['fisher'], df['fisher_signal'] = np.nan, np.nan

    try:
        df['atr'] = ta.atr(high=df['High'], low=df['Low'], close=df['Close'], length=CONFIG['strategy']['atr']['period'])
    except Exception as e:
        logging.error(f"{Fore.RED}Error calculating ATR: {e}{Style.RESET_ALL}")
        df['atr'] = np.nan

    df = df.ffill().fillna(0)
    return df

def generate_ehl_supertrend_signals(df: pd.DataFrame, current_price: float, price_precision: int, qty_precision: int) -> Tuple[str, Optional[float], Optional[float], Optional[float], pd.DataFrame, bool]:
    min_klines = CONFIG['trading']['min_klines_for_strategy']
    if df.empty or len(df) < min_klines:
        return 'none', None, None, None, df, False

    df_with_indicators = calculate_ehl_supertrend_indicators(df)
    if df_with_indicators.empty:
        return 'none', None, None, None, df_with_indicators, False

    last_row, prev_row = df_with_indicators.iloc[-1], df_with_indicators.iloc[-2]
    
    # --- Signal Conditions ---
    long_trend_confirmed = last_row['st_slow_direction'] > 0
    short_trend_confirmed = last_row['st_slow_direction'] < 0
    fast_crosses_above_slow = prev_row['st_fast_line'] <= prev_row['st_slow_line'] and last_row['st_fast_line'] > last_row['st_slow_line']
    fast_crosses_below_slow = prev_row['st_fast_line'] >= prev_row['st_slow_line'] and last_row['st_fast_line'] < last_row['st_slow_line']
    
    fisher_confirm_long = last_row['fisher'] > last_row['fisher_signal']
    rsi_confirm_long = CONFIG['strategy']['rsi']['confirm_long_threshold'] < last_row['rsi'] < CONFIG['strategy']['rsi']['overbought']
    
    fisher_confirm_short = last_row['fisher'] < last_row['fisher_signal']
    rsi_confirm_short = CONFIG['strategy']['rsi']['oversold'] < last_row['rsi'] < CONFIG['strategy']['rsi']['confirm_short_threshold']
    
    volume_confirm = last_row['volume_spike'] or prev_row['volume_spike']
    
    signal, risk_distance, tp_price, sl_price = 'none', None, None, None

    if long_trend_confirmed and fast_crosses_above_slow and (fisher_confirm_long + rsi_confirm_long + volume_confirm >= 2):
        signal = 'Buy'
        sl_price = prev_row['st_slow_line']
        risk_distance = current_price - sl_price
        if risk_distance > 0:
            if CONFIG['order_logic']['use_atr_for_tp_sl']:
                atr_val = last_row['atr']
                tp_price = round(current_price + (atr_val * CONFIG['order_logic']['tp_atr_multiplier']), price_precision)
                sl_price = round(current_price - (atr_val * CONFIG['order_logic']['sl_atr_multiplier']), price_precision)
                risk_distance = current_price - sl_price
            else:
                tp_price = round(current_price + (risk_distance * CONFIG['order_logic']['reward_risk_ratio']), price_precision)
                sl_price = round(sl_price, price_precision)
        else:
            signal = 'none'

    elif short_trend_confirmed and fast_crosses_below_slow and (fisher_confirm_short + rsi_confirm_short + volume_confirm >= 2):
        signal = 'Sell'
        sl_price = prev_row['st_slow_line']
        risk_distance = sl_price - current_price
        if risk_distance > 0:
            if CONFIG['order_logic']['use_atr_for_tp_sl']:
                atr_val = last_row['atr']
                tp_price = round(current_price - (atr_val * CONFIG['order_logic']['tp_atr_multiplier']), price_precision)
                sl_price = round(current_price + (atr_val * CONFIG['order_logic']['sl_atr_multiplier']), price_precision)
                risk_distance = sl_price - current_price
            else:
                tp_price = round(current_price - (risk_distance * CONFIG['order_logic']['reward_risk_ratio']), price_precision)
                sl_price = round(sl_price, price_precision)
        else:
            signal = 'none'
            
    return signal, risk_distance, tp_price, sl_price, df_with_indicators, volume_confirm

# --- Main Bot Loop ---
def main():
    print(f"{Fore.LIGHTYELLOW_EX}{Style.BRIGHT}Pyrmethus awakens the Ehlers Supertrend Cross Strategy!{Style.RESET_ALL}")
    
    symbols = CONFIG['trading']['trading_symbols']
    if not symbols:
        logging.info(f"{Fore.YELLOW}No symbols in config.yaml. Exiting.{Style.RESET_ALL}")
        return

    active_trades: Dict[str, Dict[str, Any]] = {}
    cumulative_pnl: float = 0.0

    while True:
        local_time, utc_time = get_current_time(CONFIG['bot']['timezone'])
        logging.info(f"{Fore.WHITE}Local: {local_time:%Y-%m-%d %H:%M:%S} | UTC: {utc_time:%Y-%m-%d %H:%M:%S}{Style.RESET_ALL}")

        if not is_market_open(local_time, CONFIG['bot']['market_open_hour'], CONFIG['bot']['market_close_hour']):
            logging.info(f"{Fore.YELLOW}Market closed. Waiting...{Style.RESET_ALL}")
            sleep(CONFIG['bot']['loop_wait_time_seconds'])
            continue
            
        balance = bybit_client.get_balance()
        if balance is None:
            logging.error(f'{Fore.RED}Cannot get balance. Retrying...{Style.RESET_ALL}')
            sleep(CONFIG['bot']['loop_wait_time_seconds'])
            continue
        
        logging.info(f'{Fore.LIGHTGREEN_EX}Balance: {balance:.2f} USDT{Style.RESET_ALL}')
        current_positions = bybit_client.get_positions()
        logging.info(f'{Fore.LIGHTCYAN_EX}{len(current_positions)} open positions: {current_positions}{Style.RESET_ALL}')

        # --- New Trade Logic ---
        for symbol in symbols:
            if len(bybit_client.get_positions()) >= CONFIG['trading']['max_positions']:
                logging.info(f"{Fore.YELLOW}Max positions reached. No new trades.{Style.RESET_ALL}")
                break
            if symbol in current_positions or symbol in active_trades:
                continue

            kl = bybit_client.klines(symbol, CONFIG['trading']['timeframe'], limit=CONFIG['trading']['min_klines_for_strategy'] + 5)
            if kl.empty:
                logging.warning(f"{Fore.YELLOW}Not enough kline data for {symbol}. Skipping.{Style.RESET_ALL}")
                continue
            
            current_price = kl['Close'].iloc[-1]
            price_precision, qty_precision = bybit_client.get_precisions(symbol)
            
            signal, risk, tp, sl, df_indicators, vol_confirm = generate_ehl_supertrend_signals(kl, current_price, price_precision, qty_precision)

            # --- Detailed Logging ---
            if not df_indicators.empty:
                last_row = df_indicators.iloc[-1]
                log_msg = (
                    f"[{symbol}] "
                    f"Price: {Fore.WHITE}{current_price:.4f}{Style.RESET_ALL} | "
                    f"SlowST: {Fore.CYAN}{last_row['st_slow_line']:.4f} ({'Up' if last_row['st_slow_direction'] > 0 else 'Down'}){Style.RESET_ALL} | "
                    f"FastST: {Fore.CYAN}{last_row['st_fast_line']:.4f}{Style.RESET_ALL} | "
                    f"RSI: {Fore.YELLOW}{last_row['rsi']:.2f}{Style.RESET_ALL} | "
                    f"Fisher: {Fore.MAGENTA}{last_row['fisher']:.2f} (Sig: {last_row['fisher_signal']:.2f}){Style.RESET_ALL} | "
                    f"VolSpike: {Fore.GREEN if vol_confirm else Fore.RED}{'Yes' if vol_confirm else 'No'}{Style.RESET_ALL}"
                )
                logging.info(log_msg)
            else:
                logging.warning(f"[{symbol}] Could not generate indicator data for logging.")

            if signal != 'none' and risk and risk > 0:
                # --- Detailed Signal Reasoning ---
                reasoning = []
                last_row = df_indicators.iloc[-1]
                if signal == 'Buy':
                    reasoning.append("SlowST is Up")
                    reasoning.append("FastST crossed above SlowST")
                    confirmations = []
                    if last_row['fisher'] > last_row['fisher_signal']: confirmations.append("Fisher")
                    if CONFIG['strategy']['rsi']['confirm_long_threshold'] < last_row['rsi'] < CONFIG['strategy']['rsi']['overbought']: confirmations.append("RSI")
                    if vol_confirm: confirmations.append("Volume")
                    reasoning.append(f"Confirms ({len(confirmations)}/2): {', '.join(confirmations)}")
                else: # Sell
                    reasoning.append("SlowST is Down")
                    reasoning.append("FastST crossed below SlowST")
                    confirmations = []
                    if last_row['fisher'] < last_row['fisher_signal']: confirmations.append("Fisher")
                    if CONFIG['strategy']['rsi']['oversold'] < last_row['rsi'] < CONFIG['strategy']['rsi']['confirm_short_threshold']: confirmations.append("RSI")
                    if vol_confirm: confirmations.append("Volume")
                    reasoning.append(f"Confirms ({len(confirmations)}/2): {', '.join(confirmations)}")

                logging.info(f"{Fore.GREEN if signal == 'Buy' else Fore.RED}{Style.BRIGHT}{signal.upper()} SIGNAL for {symbol} at {current_price:.4f} | TP: {tp:.4f}, SL: {sl:.4f} | Reason: {'; '.join(reasoning)}{Style.RESET_ALL}")
                
                risk_amount_usdt = balance * CONFIG['risk_management']['risk_per_trade_pct']
                order_qty = min(risk_amount_usdt / risk, CONFIG['risk_management']['order_qty_usdt'] / current_price)
                order_qty = round(order_qty, qty_precision)

                if order_qty > 0:
                    bybit_client.set_margin_mode_and_leverage(symbol, CONFIG['risk_management']['margin_mode'], CONFIG['risk_management']['leverage'])
                    sleep(0.5)
                    order_id = bybit_client.place_market_order(symbol=symbol, side=signal, qty=order_qty, tp_price=tp, sl_price=sl)
                    if order_id:
                        active_trades[symbol] = {'entry_time': utc_time, 'order_id': order_id, 'side': signal, 'entry_price': current_price, 'qty': order_qty, 'sl': sl, 'tp': tp}
                        send_termux_toast(f"{signal.upper()} Signal: {symbol}")
                else:
                    logging.warning(f"{Fore.YELLOW}Calculated order quantity for {symbol} is zero. Skipping.{Style.RESET_ALL}")
            else:
                logging.debug(f"[{symbol}] No signal generated on this candle.")

        sleep(CONFIG['bot']['loop_wait_time_seconds'])

if __name__ == "__main__":
    main()