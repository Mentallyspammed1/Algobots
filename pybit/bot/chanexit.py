
import warnings
import socket

# --- Pyrmethus's DNS Bypass Incantation ---
# We scribe this spell to teach the script the true IP of api.bybit.com,
# bypassing the fickle DNS spirits within the Python environment.
try:
    _original_getaddrinfo = socket.getaddrinfo
    _bybit_ip = '143.204.194.59' 

    def _patched_getaddrinfo(host, *args, **kwargs):
        if host == 'api.bybit.com':
            return _original_getaddrinfo(_bybit_ip, *args, **kwargs)
        return _original_getaddrinfo(host, *args, **kwargs)

    socket.getaddrinfo = _patched_getaddrinfo
except Exception:
    pass # If the spell fails, proceed with the original magic.
# --- End of Incantation ---
import os
import sys
import datetime
import pytz
import time
import uuid
import sqlite3
import logging
import asyncio
import numpy as np
import pandas as pd
import pandas_ta as ta
from typing import Optional, Tuple, Dict, Any, List
from bybit import BybitAsync

# silence the usual noisy packages
warnings.filterwarnings("ignore", category=UserWarning, module='pkg_resources')

# --- IMPORT BOT CONFIGURATION ---
from config import BOT_CONFIG

# -------------- coloured logging (unchanged) --------------
class ColoredFormatter(logging.Formatter):
    GREEN = "\033[92m"; RED = "\033[91m"; YELLOW = "\033[93m"; BLUE = "\033[94m"
    MAGENTA = "\033[95m"; CYAN = "\033[96m"; WHITE = "\033[97m"; RESET = "\033[0m"; BOLD = "\033[1m"
    FORMATS = {
        logging.DEBUG:    CYAN + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + RESET,
        logging.INFO:     WHITE + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + RESET,
        logging.WARNING:  YELLOW + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + RESET,
        logging.ERROR:    RED + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + RESET,
        logging.CRITICAL: BOLD + RED + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + RESET
    }
    def format(self, record):
        return logging.Formatter(
            self.FORMATS.get(record.levelno) if sys.stdout.isatty() else "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt='%Y-%m-%d %H:%M:%S'
        ).format(record)

root_logger = logging.getLogger()
if root_logger.hasHandlers(): root_logger.handlers.clear()
handler = logging.StreamHandler(); handler.setFormatter(ColoredFormatter())
root_logger.addHandler(handler); root_logger.setLevel(getattr(logging, BOT_CONFIG.get("LOG_LEVEL","INFO")))

# -------------- SQLite position tracker --------------
DB_FILE = "scalper_positions.sqlite"
def _init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
           CREATE TABLE IF NOT EXISTS trades(
               id TEXT PRIMARY KEY,
               order_id TEXT, -- Bybit order ID for tracking
               symbol TEXT,
               side TEXT,
               qty REAL,
               entry_time TEXT,
               entry_price REAL,
               sl REAL,
               tp REAL,
               status TEXT DEFAULT 'OPEN', -- OPEN, CLOSED, UNKNOWN, RECONCILED
               exit_time TEXT,
               exit_price REAL,
               pnl REAL
           )
        """)
_init_db()

# -------------- Bybit client wrapper (async) --------------
class Bybit:
    def __init__(self, api: str, secret: str, testnet: bool = False, dry_run: bool = False):
        if not api or not secret: raise ValueError("API Key and Secret must be provided.")
        self.api, self.secret, self.testnet, self.dry_run = api, secret, testnet, dry_run
        
        config = {
            'apiKey': api,
            'secret': secret,
            'options': {
                'defaultType': 'linear',  # Specify linear perpetuals
            },
            'loadMarkets': False, # Disable auto-loading markets
        }
        if testnet:
            config['urls'] = {'api': 'https://api-testnet.bybit.com'}

        self.session = BybitAsync(config)
        logging.info(f"Bybit client ready – testnet={testnet}  dry_run={dry_run}")

    async def close_session(self):
        await self.session.close()

    async def get_balance(self, coin="USDT") -> float:
        for attempt in range(BOT_CONFIG["ORDER_RETRY_ATTEMPTS"]):
            try:
                # Using fetch_balance(), common in CCXT-like libraries
                resp = await self.session.fetch_balance()
                if coin in resp:
                    return float(resp[coin].get('total', 0))
                logging.error(f"Balance for {coin} not found in response.")
                await asyncio.sleep(BOT_CONFIG["ORDER_RETRY_DELAY_SECONDS"])
            except Exception as e:
                logging.error(f"get_balance error (attempt {attempt+1}/{BOT_CONFIG['ORDER_RETRY_ATTEMPTS']}): {e}")
                await asyncio.sleep(BOT_CONFIG["ORDER_RETRY_DELAY_SECONDS"])
        return 0.

    async def get_positions(self, settleCoin="USDT") -> List[Dict[str, Any]]:
        for attempt in range(BOT_CONFIG["ORDER_RETRY_ATTEMPTS"]):
            try:
                resp = await self.session.get_positions(category='linear', settleCoin=settleCoin)
                if resp['retCode'] == 0:
                    return [p for p in resp['result']['list'] if float(p['size']) > 0]
                logging.error(f"Error getting positions (attempt {attempt+1}/{BOT_CONFIG['ORDER_RETRY_ATTEMPTS']}): {resp.get('retMsg', 'Unknown error')} (Code: {resp.get('retCode', 'N/A')})")
                await asyncio.sleep(BOT_CONFIG["ORDER_RETRY_DELAY_SECONDS"])
            except Exception as e:
                logging.error(f"get_positions error (attempt {attempt+1}/{BOT_CONFIG['ORDER_RETRY_ATTEMPTS']}): {e}")
                await asyncio.sleep(BOT_CONFIG["ORDER_RETRY_DELAY_SECONDS"])
        return []

    async def get_tickers(self) -> Optional[List[str]]:
        for attempt in range(BOT_CONFIG["ORDER_RETRY_ATTEMPTS"]):
            try:
                r = await self.session.get_tickers(category="linear")
                if r['retCode'] == 0: return [t['symbol'] for t in r['result']['list'] if 'USDT' in t['symbol'] and 'USDC' not in t['symbol']]
                logging.error(f"Error getting tickers (attempt {attempt+1}/{BOT_CONFIG['ORDER_RETRY_ATTEMPTS']}): {r.get('retMsg', 'Unknown error')} (Code: {r.get('retCode', 'N/A')})")
                await asyncio.sleep(BOT_CONFIG["ORDER_RETRY_DELAY_SECONDS"])
            except Exception as e:
                logging.error(f"get_tickers error (attempt {attempt+1}/{BOT_CONFIG['ORDER_RETRY_ATTEMPTS']}): {e}")
                await asyncio.sleep(BOT_CONFIG["ORDER_RETRY_DELAY_SECONDS"])
        return None

    async def klines(self, symbol: str, timeframe: int, limit: int = 500) -> pd.DataFrame:
        for attempt in range(BOT_CONFIG["ORDER_RETRY_ATTEMPTS"]):
            try:
                r = await self.session.get_kline(category='linear', symbol=symbol, interval=str(timeframe), limit=limit)
                if r['retCode'] == 0:
                    df = pd.DataFrame(r['result']['list'], columns=['Time','Open','High','Low','Close','Volume','Turnover']).astype(float)
                    df['Time'] = pd.to_datetime(df['Time'], unit='ms')
                    df = df.set_index('Time').sort_index()
                    if df[['Open', 'High', 'Low', 'Close']].isnull().all().any():
                        logging.warning(f"Critical OHLCV columns are all NaN for {symbol}. Skipping this kline data.")
                        return pd.DataFrame()
                    return df
                logging.error(f"Error getting klines for {symbol} (attempt {attempt+1}/{BOT_CONFIG['ORDER_RETRY_ATTEMPTS']}): {r.get('retMsg', 'Unknown error')} (Code: {r.get('retCode', 'N/A')})")
                await asyncio.sleep(BOT_CONFIG["ORDER_RETRY_DELAY_SECONDS"])
            except Exception as e:
                logging.error(f"klines error {symbol} (attempt {attempt+1}/{BOT_CONFIG['ORDER_RETRY_ATTEMPTS']}): {e}")
                await asyncio.sleep(BOT_CONFIG["ORDER_RETRY_DELAY_SECONDS"])
        return pd.DataFrame()

    async def get_current_price(self, symbol: str) -> Optional[float]:
        try:
            r = await self.session.get_tickers(category='linear', symbol=symbol)
            if r['retCode'] == 0 and r['result']['list']:
                return float(r['result']['list'][0]['lastPrice'])
        except Exception as e:
            logging.error(f"Error getting current price for {symbol}: {e}")
        return None

    async def get_orderbook_levels(self, symbol: str, limit: int = 50) -> Tuple[Optional[float], Optional[float]]:
        for attempt in range(BOT_CONFIG["ORDER_RETRY_ATTEMPTS"]):
            try:
                r = await self.session.fetch_order_book(symbol=symbol, limit=limit)
                if r['retCode'] == 0 and 'result' in r and 'b' in r['result'] and 'a' in r['result']:
                    best_bid = float(r['result']['b'][0][0]) if r['result']['b'] else None
                    best_ask = float(r['result']['a'][0][0]) if r['result']['a'] else None
                    return best_bid, best_ask
                logging.error(f"Error getting orderbook for {symbol} (attempt {attempt+1}/{BOT_CONFIG['ORDER_RETRY_ATTEMPTS']}): {r.get('retMsg', 'Unknown error')} (Code: {r.get('retCode', 'N/A')})")
                await asyncio.sleep(BOT_CONFIG["ORDER_RETRY_DELAY_SECONDS"])
            except Exception as e:
                logging.error(f"orderbook error {symbol} (attempt {attempt+1}/{BOT_CONFIG['ORDER_RETRY_ATTEMPTS']}): {e}")
                await asyncio.sleep(BOT_CONFIG["ORDER_RETRY_DELAY_SECONDS"])
        return None, None

    async def get_precisions(self, symbol: str) -> Tuple[int, int]:
        for attempt in range(BOT_CONFIG["ORDER_RETRY_ATTEMPTS"]):
            try:
                r = await self.session.get_instruments_info(category='linear', symbol=symbol)
                if r['retCode'] == 0 and r['result']['list']:
                    info = r['result']['list'][0]
                    price_step = info['priceFilter']['tickSize']; qty_step = info['lotSizeFilter']['qtyStep']
                    price_prec = len(price_step.split('.')[1]) if '.' in price_step and len(price_step.split('.')) > 1 else 0
                    qty_prec = len(qty_step.split('.')[1]) if '.' in qty_step and len(qty_step.split('.')) > 1 else 0
                    return price_prec, qty_prec
                logging.error(f"Error getting precisions for {symbol} (attempt {attempt+1}/{BOT_CONFIG['ORDER_RETRY_ATTEMPTS']}): {r.get('retMsg', 'Unknown error')} (Code: {r.get('retCode', 'N/A')})")
                await asyncio.sleep(BOT_CONFIG["ORDER_RETRY_DELAY_SECONDS"])
            except Exception as e:
                logging.error(f"precisions error {symbol} (attempt {attempt+1}/{BOT_CONFIG['ORDER_RETRY_ATTEMPTS']}): {e}")
                await asyncio.sleep(BOT_CONFIG["ORDER_RETRY_DELAY_SECONDS"])
        return 0, 0

    async def set_margin_mode_and_leverage(self, symbol: str, mode: int = 1, leverage: int = 10):
        if self.dry_run:
            logging.info(f"[DRY RUN] would set {symbol} margin={'Isolated' if mode==1 else 'Cross'} {leverage}x")
            return
        for attempt in range(BOT_CONFIG["ORDER_RETRY_ATTEMPTS"]):
            try:
                r = await self.session.switch_margin_mode(category='linear', symbol=symbol, tradeMode=str(mode),
                                                          buyLeverage=str(leverage), sellLeverage=str(leverage))
                if r['retCode'] == 0:
                    logging.info(f"{symbol} margin={'Isolated' if mode==1 else 'Cross'} {leverage}x set.")
                    return
                elif r['retCode'] in (110026, 110043): # Already set
                    logging.debug(f"{symbol} margin/leverage already set (Code: {r['retCode']}).")
                    return
                logging.warning(f"Failed to set margin mode/leverage for {symbol} (attempt {attempt+1}/{BOT_CONFIG['ORDER_RETRY_ATTEMPTS']}): {r.get('retMsg', 'Unknown error')} (Code: {r['retCode']})")
                await asyncio.sleep(BOT_CONFIG["ORDER_RETRY_DELAY_SECONDS"])
            except Exception as e:
                logging.error(f"margin/lever error for {symbol} (attempt {attempt+1}/{BOT_CONFIG['ORDER_RETRY_ATTEMPTS']}): {e}")
                await asyncio.sleep(BOT_CONFIG["ORDER_RETRY_DELAY_SECONDS"])

    async def place_order_common(self, symbol: str, side: str, order_type: str, qty: float, price: Optional[float]=None, trigger_price: Optional[float]=None, tp_price: Optional[float]=None, sl_price: Optional[float]=None, time_in_force: str = 'GTC', reduce_only: bool = False) -> Optional[str]:
        if self.dry_run:
            oid = f"DRY_{uuid.uuid4()}"
            log_msg = f"[DRY RUN] {order_type} {side} {qty} {symbol}"
            if price: log_msg += f" price={price}"
            if trigger_price: log_msg += f" trigger={trigger_price}"
            if tp_price: log_msg += f" TP={tp_price}"
            if sl_price: log_msg += f" SL={sl_price}"
            if reduce_only: log_msg += f" ReduceOnly"
            logging.info(f"{log_msg}. Simulated Order ID: {oid}")
            return oid
        
        for attempt in range(BOT_CONFIG["ORDER_RETRY_ATTEMPTS"]):
            try:
                params = dict(category='linear', symbol=symbol, side=side, orderType=order_type, qty=str(qty), timeInForce=time_in_force, reduceOnly=1 if reduce_only else 0)
                if price is not None: params['price'] = str(price)
                if trigger_price is not None: params['triggerPrice'] = str(trigger_price); params['triggerBy'] = 'MarkPrice'
                if tp_price is not None: params['takeProfit'] = str(tp_price); params['tpTriggerBy'] = 'Market'
                if sl_price is not None: params['stopLoss'] = str(sl_price); params['slTriggerBy'] = 'Market'
                
                r = await self.session.place_order(**params)
                if r['retCode'] == 0:
                    logging.info(f"Order placed for {symbol} ({order_type} {side} {qty}). Order ID: {r['result']['orderId']}")
                    return r['result']['orderId']
                
                # Handle common order errors (e.g., insufficient balance, invalid price)
                if r['retCode'] == 10001: # order fails due to insufficient balance, etc.
                    logging.error(f"Order placement failed for {symbol} due to API error {r['retCode']}: {r.get('retMsg', 'Unknown API error')}")
                    return None # Do not retry immediately for specific critical errors
                
                logging.error(f"Failed to place order for {symbol} ({order_type} {side} {qty}) (attempt {attempt+1}/{BOT_CONFIG['ORDER_RETRY_ATTEMPTS']}): {r.get('retMsg', 'Unknown error')} (Code: {r['retCode']})")
                await asyncio.sleep(BOT_CONFIG["ORDER_RETRY_DELAY_SECONDS"])
            except Exception as e:
                logging.error(f"Exception placing {order_type} order for {symbol} (attempt {attempt+1}/{BOT_CONFIG['ORDER_RETRY_ATTEMPTS']}): {e}")
                await asyncio.sleep(BOT_CONFIG["ORDER_RETRY_DELAY_SECONDS"])
        return None

    async def place_market_order(self, symbol: str, side: str, qty: float, tp_price: Optional[float]=None, sl_price: Optional[float]=None, reduce_only: bool = False) -> Optional[str]:
        return await self.place_order_common(symbol, side, 'Market', qty, tp_price=tp_price, sl_price=sl_price, reduce_only=reduce_only)

    async def place_limit_order(self, symbol: str, side: str, price: float, qty: float, tp_price: Optional[float]=None, sl_price: Optional[float]=None, time_in_force: str = 'GTC', reduce_only: bool = False) -> Optional[str]:
        return await self.place_order_common(symbol, side, 'Limit', qty, price=price, tp_price=tp_price, sl_price=sl_price, time_in_force=time_in_force, reduce_only=reduce_only)

    async def place_conditional_order(self, symbol: str, side: str, qty: float, trigger_price: float, order_type: str = 'Market', price: Optional[float]=None, tp_price: Optional[float]=None, sl_price: Optional[float]=None, reduce_only: bool = False) -> Optional[str]:
        if order_type == 'Limit' and price is None:
            price = trigger_price
            logging.warning(f"Conditional limit order requested for {symbol} without explicit `price`. Using `trigger_price` as limit execution price.")
        return await self.place_order_common(symbol, side, order_type, qty, price=price, trigger_price=trigger_price, tp_price=tp_price, sl_price=sl_price, reduce_only=reduce_only)

    async def cancel_all_open_orders(self, symbol: str) -> bool:
        if self.dry_run:
            logging.info(f"[DRY RUN] Would cancel all open orders for {symbol}.")
            return True
        for attempt in range(BOT_CONFIG["ORDER_RETRY_ATTEMPTS"]):
            try:
                r = await self.session.cancel_all_orders(category='linear', symbol=symbol)
                if r['retCode'] == 0:
                    logging.info(f"All open orders for {symbol} cancelled successfully.")
                    return True
                logging.warning(f"Failed to cancel all orders for {symbol} (attempt {attempt+1}/{BOT_CONFIG['ORDER_RETRY_ATTEMPTS']}): {r.get('retMsg', 'Unknown error')} (Code: {r['retCode']})")
                await asyncio.sleep(BOT_CONFIG["ORDER_RETRY_DELAY_SECONDS"])
            except Exception as e:
                logging.error(f"Exception cancelling all orders for {symbol} (attempt {attempt+1}/{BOT_CONFIG['ORDER_RETRY_ATTEMPTS']}): {e}")
                await asyncio.sleep(BOT_CONFIG["ORDER_RETRY_DELAY_SECONDS"])
        return False

    async def modify_position_tpsl(self, symbol: str, tp_price: Optional[float], sl_price: Optional[float], position_idx: int = 0) -> bool:
        if self.dry_run:
            logging.info(f"[DRY RUN] Would modify TP/SL for {symbol}. TP:{tp_price}, SL:{sl_price}")
            return True
        
        for attempt in range(BOT_CONFIG["ORDER_RETRY_ATTEMPTS"]):
            try:
                params = {'category': 'linear', 'symbol': symbol, 'positionIdx': position_idx}
                if tp_price is not None: params['takeProfit'] = str(tp_price)
                if sl_price is not None: params['stopLoss'] = str(sl_price)
                params['tpTriggerBy'] = 'Market'
                params['slTriggerBy'] = 'Market'

                r = await self.session.set_trading_stop(**params)
                if r['retCode'] == 0:
                    logging.debug(f"Modified TP/SL for {symbol}. TP:{tp_price}, SL:{sl_price}")
                    return True
                elif r['retCode'] == 110026: # No position to modify
                    logging.warning(f"No active position for {symbol} to modify TP/SL.")
                    return False
                logging.warning(f"Failed to modify TP/SL for {symbol} (attempt {attempt+1}/{BOT_CONFIG['ORDER_RETRY_ATTEMPTS']}): {r.get('retMsg', 'Unknown error')} (Code: {r['retCode']})")
                await asyncio.sleep(BOT_CONFIG["ORDER_RETRY_DELAY_SECONDS"])
            except Exception as e:
                logging.error(f"Exception modifying TP/SL for {symbol} (attempt {attempt+1}/{BOT_CONFIG['ORDER_RETRY_ATTEMPTS']}): {e}")
                await asyncio.sleep(BOT_CONFIG["ORDER_RETRY_DELAY_SECONDS"])
        return False

    async def get_open_orders(self, symbol: Optional[str]=None) -> List[Dict[str, Any]]:
        for attempt in range(BOT_CONFIG["ORDER_RETRY_ATTEMPTS"]):
            try:
                params={'category':'linear'}
                if symbol: params['symbol']=symbol
                r = await self.session.get_open_orders(**params)
                if r['retCode'] == 0: return r['result']['list']
                logging.error(f"Error getting open orders for {symbol if symbol else 'all symbols'} (attempt {attempt+1}/{BOT_CONFIG['ORDER_RETRY_ATTEMPTS']}): {r.get('retMsg', 'Unknown error')} (Code: {r.get('retCode', 'N/A')})")
                await asyncio.sleep(BOT_CONFIG["ORDER_RETRY_DELAY_SECONDS"])
            except Exception as e:
                logging.error(f"Exception getting open orders for {symbol if symbol else 'all symbols'} (attempt {attempt+1}/{BOT_CONFIG['ORDER_RETRY_ATTEMPTS']}): {e}")
                await asyncio.sleep(BOT_CONFIG["ORDER_RETRY_DELAY_SECONDS"])
        return []

    async def close_position(self, symbol: str) -> Optional[str]:
        if self.dry_run:
            logging.info(f"[DRY RUN] Would close position for {symbol} with a market order.")
            return f"DRY_CLOSE_{uuid.uuid4()}"
        for attempt in range(BOT_CONFIG["ORDER_RETRY_ATTEMPTS"]):
            try:
                pos_resp = await self.session.get_positions(category='linear', symbol=symbol)
                if pos_resp['retCode'] != 0 or not pos_resp['result']['list']:
                    logging.warning(f"Could not get position details for {symbol} to close (attempt {attempt+1}/{BOT_CONFIG['ORDER_RETRY_ATTEMPTS']}). {pos_resp.get('retMsg', 'No position found')}")
                    await asyncio.sleep(BOT_CONFIG["ORDER_RETRY_DELAY_SECONDS"])
                    continue
                
                position_info = next((p for p in pos_resp['result']['list'] if float(p['size']) > 0), None)
                if not position_info:
                    logging.info(f"No open position found for {symbol} to close (size is 0).")
                    return None

                side_to_close = 'Sell' if position_info['side'] == 'Buy' else 'Buy'
                order_id = await self.place_market_order(
                    symbol=symbol,
                    side=side_to_close,
                    qty=float(position_info['size']),
                    reduce_only=True
                )
                return order_id
            except Exception as e:
                logging.error(f"Exception closing position for {symbol} (attempt {attempt+1}/{BOT_CONFIG['ORDER_RETRY_ATTEMPTS']}): {e}")
                await asyncio.sleep(BOT_CONFIG["ORDER_RETRY_DELAY_SECONDS"])
        return None

# -------------- higher TF confirmation --------------
async def higher_tf_trend(bybit: Bybit, symbol: str) -> str:
    htf = BOT_CONFIG.get("HIGHER_TF_TIMEFRAME", 5)
    short = BOT_CONFIG.get("H_TF_EMA_SHORT_PERIOD", 8)
    long = BOT_CONFIG.get("H_TF_EMA_LONG_PERIOD", 21)
    df = await bybit.klines(symbol, htf, limit=long+5)
    if df.empty or len(df) < max(short, long) + 1:
        logging.debug(f"Not enough data for HTF trend for {symbol}.")
        return 'none'
    ema_s = ta.ema(df['Close'], short).iloc[-1]
    ema_l = ta.ema(df['Close'], long).iloc[-1]
    if ema_s > ema_l: return 'long'
    if ema_s < ema_l: return 'short'
    return 'none'

# -------------- Ehlers Supertrend (pandas-ta) --------------
def est_supertrend(df: pd.DataFrame, length: int = 8, multiplier: float = 1.2) -> pd.Series:
    st = ta.supertrend(df['High'], df['Low'], df['Close'], length=length, multiplier=multiplier)
    if st.empty or st.shape[1] < 3:
        return pd.Series(np.nan, index=df.index)
    trend_col = [col for col in st.columns if '_D_' in col]
    if trend_col:
        return st[trend_col[0]]
    return pd.Series(np.nan, index=df.index)

# -------------- Fisher Transform --------------
def fisher_transform(df: pd.DataFrame, period: int = 8) -> pd.Series:
    fisher = ta.fisher(df['High'], df['Low'], length=period)
    if fisher.empty or fisher.shape[1] < 2:
        return pd.Series(np.nan, index=df.index)
    trigger_col = [col for col in fisher.columns if '_T_' in col]
    if trigger_col:
        return fisher[trigger_col[0]]
    return pd.Series(np.nan, index=df.index)

# -------------- Stochastic Oscillator (New) --------------
def stochastic_oscillator(df: pd.DataFrame, k_period: int = 14, d_period: int = 3, smoothing: int = 3) -> Tuple[pd.Series, pd.Series]:
    stoch = ta.stoch(df['High'], df['Low'], df['Close'], k=k_period, d=d_period, smooth_k=smoothing)
    if stoch.empty or stoch.shape[1] < 2:
        return pd.Series(np.nan, index=df.index), pd.Series(np.nan, index=df.index)
    
    k_col = [col for col in stoch.columns if '_K_' in col]
    d_col = [col for col in stoch.columns if '_D_' in col]
    
    if k_col and d_col:
        return stoch[k_col[0]], stoch[d_col[0]]
    return pd.Series(np.nan, index=df.index), pd.Series(np.nan, index=df.index)

# -------------- MACD (New) --------------
def macd_indicator(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    macd = ta.macd(df['Close'], fast=fast, slow=slow, signal=signal)
    if macd.empty or macd.shape[1] < 3:
        return pd.Series(np.nan, index=df.index), pd.Series(np.nan, index=df.index), pd.Series(np.nan, index=df.index)
    
    macd_col = [col for col in macd.columns if 'MACD_' in col]
    hist_col = [col for col in macd.columns if 'HIST_' in col]
    signal_col = [col for col in macd.columns if 'SIGNAL_' in col]

    if macd_col and hist_col and signal_col:
        return macd[macd_col[0]], macd[signal_col[0]], macd[hist_col[0]]
    return pd.Series(np.nan, index=df.index), pd.Series(np.nan, index=df.index), pd.Series(np.nan, index=df.index)

# -------------- ADX (New) --------------
def adx_indicator(df: pd.DataFrame, period: int = 14) -> pd.Series:
    adx = ta.adx(df['High'], df['Low'], df['Close'], length=period)
    if adx.empty or adx.shape[1] < 3:
        return pd.Series(np.nan, index=df.index)
    
    adx_col = [col for col in adx.columns if 'ADX_' in col]
    if adx_col:
        return adx[adx_col[0]]
    return pd.Series(np.nan, index=df.index)


# -------------- upgraded chandelier + multi-TF --------------
def build_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in ['Open','High','Low','Close','Volume']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
        df[c] = df[c].ffill().fillna(0)
    
    atr_series = ta.atr(df['High'], df['Low'], df['Close'], BOT_CONFIG["ATR_PERIOD"])
    df['atr'] = atr_series.fillna(method='ffill').fillna(0)
    
    df['highest_high'] = df['High'].rolling(BOT_CONFIG["ATR_PERIOD"], min_periods=1).max().fillna(method='ffill').fillna(0)
    df['lowest_low'] = df['Low'].rolling(BOT_CONFIG["ATR_PERIOD"], min_periods=1).min().fillna(method='ffill').fillna(0)

    if len(df) >= BOT_CONFIG.get("VOLATILITY_LOOKBACK", 20):
        price_std = df['Close'].pct_change().rolling(window=BOT_CONFIG.get("VOLATILITY_LOOKBACK", 20), min_periods=1).std()
        if price_std.mean() > 0 and not pd.isna(price_std.mean()):
            df['dynamic_multiplier'] = np.clip(
                BOT_CONFIG["CHANDELIER_MULTIPLIER"] * (price_std / price_std.mean()),
                BOT_CONFIG["MIN_ATR_MULTIPLIER"],
                BOT_CONFIG["MAX_ATR_MULTIPLIER"]
            )
        else:
            df['dynamic_multiplier'] = BOT_CONFIG["CHANDELIER_MULTIPLIER"]
    else:
        df['dynamic_multiplier'] = BOT_CONFIG["CHANDELIER_MULTIPLIER"]

    df['dynamic_multiplier'] = df['dynamic_multiplier'].fillna(method='ffill').fillna(BOT_CONFIG["CHANDELIER_MULTIPLIER"])

    df['ch_long'] = df['highest_high'] - (df['atr'] * df['dynamic_multiplier'])
    df['ch_short'] = df['lowest_low'] + (df['atr'] * df['dynamic_multiplier'])
    
    df['trend_ema'] = ta.ema(df['Close'], BOT_CONFIG["TREND_EMA_PERIOD"]).fillna(method='ffill').fillna(0)
    df['ema_s'] = ta.ema(df['Close'], BOT_CONFIG["EMA_SHORT_PERIOD"]).fillna(method='ffill').fillna(0)
    df['ema_l'] = ta.ema(df['Close'], BOT_CONFIG["EMA_LONG_PERIOD"]).fillna(method='ffill').fillna(0)
    df['rsi'] = ta.rsi(df['Close'], BOT_CONFIG["RSI_PERIOD"]).fillna(method='ffill').fillna(50)
    
    df['vol_ma'] = ta.sma(df['Volume'], BOT_CONFIG.get("VOLUME_MA_PERIOD", 20)).fillna(method='ffill').fillna(0)
    df['vol_spike'] = (df['Volume'] / df['vol_ma'].replace(0, np.nan)) > BOT_CONFIG["VOLUME_THRESHOLD_MULTIPLIER"]
    df['vol_spike'] = df['vol_spike'].fillna(False)

    df['est_slow'] = est_supertrend(df, BOT_CONFIG.get("EST_SLOW_LENGTH", 8), BOT_CONFIG.get("EST_SLOW_MULTIPLIER", 1.2)).fillna(method='ffill').fillna(0)
    df['fisher'] = fisher_transform(df, BOT_CONFIG.get("EHLERS_FISHER_PERIOD", 8)).fillna(method='ffill').fillna(0)

    if BOT_CONFIG.get("USE_STOCH_FILTER", False):
        df['stoch_k'], df['stoch_d'] = stochastic_oscillator(df, BOT_CONFIG["STOCH_K_PERIOD"], BOT_CONFIG["STOCH_D_PERIOD"], BOT_CONFIG["STOCH_SMOOTHING"])
        df['stoch_k'] = df['stoch_k'].fillna(method='ffill').fillna(50)
        df['stoch_d'] = df['stoch_d'].fillna(method='ffill').fillna(50)
    
    if BOT_CONFIG.get("USE_MACD_FILTER", False):
        df['macd_line'], df['macd_signal'], df['macd_hist'] = macd_indicator(df, BOT_CONFIG["MACD_FAST_PERIOD"], BOT_CONFIG["MACD_SLOW_PERIOD"], BOT_CONFIG["MACD_SIGNAL_PERIOD"])
        df['macd_line'] = df['macd_line'].fillna(method='ffill').fillna(0)
        df['macd_signal'] = df['macd_signal'].fillna(method='ffill').fillna(0)
        df['macd_hist'] = df['macd_hist'].fillna(method='ffill').fillna(0)

    if BOT_CONFIG.get("USE_ADX_FILTER", False):
        df['adx'] = adx_indicator(df, BOT_CONFIG["ADX_PERIOD"])
        df['adx'] = df['adx'].fillna(method='ffill').fillna(0)

    return df.ffill().fillna(0)

# -------------- signal generator --------------
last_signal_bar: Dict[str, int] = {}
async def generate_signal(bybit: Bybit, symbol: str, df: pd.DataFrame) -> Tuple[str, float, float, float, str]:
    min_required_klines = max(
        BOT_CONFIG["MIN_KLINES_FOR_STRATEGY"], BOT_CONFIG["TREND_EMA_PERIOD"], 
        BOT_CONFIG["EMA_LONG_PERIOD"], BOT_CONFIG["ATR_PERIOD"], 
        BOT_CONFIG["RSI_PERIOD"], BOT_CONFIG.get("VOLUME_MA_PERIOD", 20),
        BOT_CONFIG.get("VOLATILITY_LOOKBACK", 20),
        BOT_CONFIG.get("EST_SLOW_LENGTH", 8) + 5, BOT_CONFIG.get("EHLERS_FISHER_PERIOD", 8) + 5
    )
    if BOT_CONFIG.get("USE_STOCH_FILTER", False): min_required_klines = max(min_required_klines, BOT_CONFIG["STOCH_K_PERIOD"] + BOT_CONFIG["STOCH_SMOOTHING"] + 5)
    if BOT_CONFIG.get("USE_MACD_FILTER", False): min_required_klines = max(min_required_klines, BOT_CONFIG["MACD_SLOW_PERIOD"] + BOT_CONFIG["MACD_SIGNAL_PERIOD"] + 5)
    if BOT_CONFIG.get("USE_ADX_FILTER", False): min_required_klines = max(min_required_klines, BOT_CONFIG["ADX_PERIOD"] + 5)
    
    if df.empty or len(df) < min_required_klines:
        return 'none', 0, 0, 0, f'not enough bars ({len(df)} < {min_required_klines})'
    
    df = build_indicators(df)
    i = -1
    j = -2

    critical_indicators = ['Close', 'atr', 'dynamic_multiplier', 'ema_s', 'ema_l', 'trend_ema', 'rsi', 'vol_spike', 'est_slow', 'fisher']
    if BOT_CONFIG.get("USE_STOCH_FILTER", False): critical_indicators.extend(['stoch_k', 'stoch_d'])
    if BOT_CONFIG.get("USE_MACD_FILTER", False): critical_indicators.extend(['macd_line', 'macd_signal'])
    if BOT_CONFIG.get("USE_ADX_FILTER", False): critical_indicators.append('adx')

    critical_indicators_exist = all(col in df.columns and not pd.isna(df[col].iloc[i]) for col in critical_indicators)
    if not critical_indicators_exist:
        return 'none', 0, 0, 0, 'critical indicators missing/NaN'

    cp = df['Close'].iloc[i]
    atr = df['atr'].iloc[i]
    dynamic_multiplier = df['dynamic_multiplier'].iloc[i]
    
    if atr <= 0 or np.isnan(atr) or np.isnan(dynamic_multiplier):
        return 'none', 0, 0, 0, 'bad atr or dynamic multiplier'
    
    risk_distance = atr * dynamic_multiplier
    
    htf_trend = await higher_tf_trend(bybit, symbol)
    if htf_trend == 'none':
        return 'none', 0, 0, 0, 'htf neutral'
    
    current_bar_timestamp = int(df.index[i].timestamp())
    if symbol in last_signal_bar and (current_bar_timestamp - last_signal_bar[symbol]) < (BOT_CONFIG.get("MIN_BARS_BETWEEN_TRADES", 3) * BOT_CONFIG["TIMEFRAME"] * 60):
        return 'none', 0, 0, 0, 'cool-down period active'
    
    if len(df) < 2:
        return 'none', 0, 0, 0, 'not enough candles for crossover check'

    # Base conditions
    long_cond = (
        df['ema_s'].iloc[i] > df['ema_l'].iloc[i] and
        df['ema_s'].iloc[j] <= df['ema_l'].iloc[j] and
        cp > df['trend_ema'].iloc[i] and
        df['rsi'].iloc[i] < BOT_CONFIG["RSI_OVERBOUGHT"] and
        df['vol_spike'].iloc[i] and
        (htf_trend == 'long')
    )

    short_cond = (
        df['ema_s'].iloc[i] < df['ema_l'].iloc[i] and
        df['ema_s'].iloc[j] >= df['ema_l'].iloc[j] and
        cp < df['trend_ema'].iloc[i] and
        df['rsi'].iloc[i] > BOT_CONFIG["RSI_OVERSOLD"] and
        df['vol_spike'].iloc[i] and
        (htf_trend == 'short')
    )

    # Ehlers Supertrend filter
    if BOT_CONFIG.get("USE_EST_SLOW_FILTER", True):
        long_cond = long_cond and (df['est_slow'].iloc[i] == 1)
        short_cond = short_cond and (df['est_slow'].iloc[i] == -1)
    
    # Stochastic filter
    if BOT_CONFIG.get("USE_STOCH_FILTER", False) and 'stoch_k' in df.columns and 'stoch_d' in df.columns:
        stoch_k_curr, stoch_d_curr = df['stoch_k'].iloc[i], df['stoch_d'].iloc[i]
        stoch_k_prev, stoch_d_prev = df['stoch_k'].iloc[j], df['stoch_d'].iloc[j]

        long_stoch_cond = (stoch_k_curr > stoch_d_curr and stoch_k_prev <= stoch_d_prev and stoch_k_curr < BOT_CONFIG["STOCH_OVERBOUGHT"])
        short_stoch_cond = (stoch_k_curr < stoch_d_curr and stoch_k_prev >= stoch_d_prev and stoch_k_curr > BOT_CONFIG["STOCH_OVERSOLD"])

        long_cond = long_cond and long_stoch_cond
        short_cond = short_cond and short_stoch_cond

    # MACD filter
    if BOT_CONFIG.get("USE_MACD_FILTER", False) and 'macd_line' in df.columns and 'macd_signal' in df.columns:
        macd_line_curr, macd_signal_curr = df['macd_line'].iloc[i], df['macd_signal'].iloc[i]
        macd_line_prev, macd_signal_prev = df['macd_line'].iloc[j], df['macd_signal'].iloc[j]

        long_macd_cond = (macd_line_curr > macd_signal_curr and macd_line_prev <= macd_signal_prev and macd_line_curr > 0)
        short_macd_cond = (macd_line_curr < macd_signal_curr and macd_line_prev >= macd_signal_prev and macd_line_curr < 0)

        long_cond = long_cond and long_macd_cond
        short_cond = short_cond and short_macd_cond

    # ADX filter
    if BOT_CONFIG.get("USE_ADX_FILTER", False) and 'adx' in df.columns:
        adx_curr = df['adx'].iloc[i]
        long_adx_cond = (adx_curr > BOT_CONFIG["ADX_THRESHOLD"])
        short_adx_cond = (adx_curr > BOT_CONFIG["ADX_THRESHOLD"])

        long_cond = long_cond and long_adx_cond
        short_cond = short_cond and short_adx_cond
        
    signal = 'none'
    tp_price = None
    sl_price = None
    reason = 'no match'

    if long_cond:
        signal = 'Buy'
        sl_price = cp - risk_distance
        tp_price = cp + (risk_distance * BOT_CONFIG.get("REWARD_RISK_RATIO", 2.5))
        reason = 'EMA cross up, price above trend EMA, RSI not overbought, volume spike, HTF long'
    elif short_cond:
        signal = 'Sell'
        sl_price = cp + risk_distance
        tp_price = cp - (risk_distance * BOT_CONFIG.get("REWARD_RISK_RATIO", 2.5))
        reason = 'EMA cross down, price below trend EMA, RSI not oversold, volume spike, HTF short'
    
    if signal != 'none':
        last_signal_bar[symbol] = current_bar_timestamp
    
    return signal, cp, sl_price, tp_price, reason

# -------------- equity guard --------------
equity_reference: Optional[float] = None
async def emergency_stop(bybit: Bybit) -> bool:
    global equity_reference
    current_equity = await bybit.get_balance()
    if equity_reference is None:
        equity_reference = current_equity
        logging.info(f"Initial equity reference set to {equity_reference:.2f} USDT.")
        return False
    
    if current_equity <= 0:
        logging.warning("Current equity is zero or negative. Cannot calculate drawdown.")
        return False
        
    if current_equity < equity_reference:
        drawdown = ((equity_reference - current_equity) / equity_reference) * 100
        if drawdown >= BOT_CONFIG.get("EMERGENCY_STOP_IF_DOWN_PCT", 15):
            logging.critical(f"{ColoredFormatter.BOLD}{ColoredFormatter.RED}!!! EMERGENCY STOP !!! Equity down {drawdown:.1f}%. Shutting down bot.{ColoredFormatter.RESET}")
            return True
    return False

# -------------- main loop --------------
async def main():
    symbols = BOT_CONFIG["TRADING_SYMBOLS"]
    if not symbols: logging.info("No symbols configured. Exiting."); return

    bybit = Bybit(BOT_CONFIG["API_KEY"], BOT_CONFIG["API_SECRET"], BOT_CONFIG["TESTNET"], BOT_CONFIG["DRY_RUN"])
    
    mode_info = f"{ColoredFormatter.MAGENTA}{ColoredFormatter.BOLD}DRY RUN{ColoredFormatter.RESET}" if BOT_CONFIG["DRY_RUN"] else f"{ColoredFormatter.GREEN}{ColoredFormatter.BOLD}LIVE{ColoredFormatter.RESET}"
    testnet_info = f"{ColoredFormatter.YELLOW}TESTNET{ColoredFormatter.RESET}" if BOT_CONFIG["TESTNET"] else f"{ColoredFormatter.BLUE}MAINNET{ColoredFormatter.RESET}"
    logging.info(f"Starting trading bot in {mode_info} mode on {testnet_info}. Checking {len(symbols)} symbols.")
    logging.info("Bot started – Press Ctrl+C to stop.")

    last_reconciliation_time = datetime.datetime.now(pytz.utc)

    try:
        while True:
            local_time, utc_time = get_current_time(BOT_CONFIG["TIMEZONE"])
            logging.info(f"Local Time: {local_time.strftime('%Y-%m-%d %H:%M:%S')} | UTC Time: {utc_time.strftime('%Y-%m-%d %H:%M:%S')}")

            if not is_market_open(local_time, BOT_CONFIG["MARKET_OPEN_HOUR"], BOT_CONFIG["MARKET_CLOSE_HOUR"]):
                logging.info(f"Market is closed ({BOT_CONFIG['MARKET_OPEN_HOUR']}:00-{BOT_CONFIG['MARKET_CLOSE_HOUR']}:00 {BOT_CONFIG['TIMEZONE']}). Skipping this cycle. Waiting {BOT_CONFIG['LOOP_WAIT_TIME_SECONDS']} seconds.")
                await asyncio.sleep(BOT_CONFIG['LOOP_WAIT_TIME_SECONDS'])
                continue
                
            if await emergency_stop(bybit): break

            balance = await bybit.get_balance()
            if balance is None or balance <= 0:
                logging.error(f'Cannot connect to API or balance is zero/negative ({balance}). Waiting {BOT_CONFIG["LOOP_WAIT_TIME_SECONDS"]} seconds and retrying.')
                await asyncio.sleep(BOT_CONFIG['LOOP_WAIT_TIME_SECONDS'])
                continue
            
            logging.info(f'Current balance: {balance:.2f} USDT')
            
            current_positions_on_exchange = await bybit.get_positions()
            current_positions_symbols_on_exchange = {p['symbol']: p for p in current_positions_on_exchange} # Map for easy lookup
            logging.info(f'You have {len(current_positions_on_exchange)} open positions on exchange: {list(current_positions_symbols_on_exchange.keys())}')

            # --- Position Reconciliation (Exchange vs. DB) ---
            if (utc_time - last_reconciliation_time).total_seconds() / 60 >= BOT_CONFIG["POSITION_RECONCILIATION_INTERVAL_MINUTES"]:
                logging.info(f"{ColoredFormatter.CYAN}Performing position reconciliation...{ColoredFormatter.RESET}")
                await reconcile_positions(bybit, current_positions_symbols_on_exchange, utc_time)
                last_reconciliation_time = utc_time

            # --- Position Exit Manager (Time, Chandelier Exit, Fisher Transform, Fixed Profit, Trailing Stop) ---
            active_db_trades = []
            with sqlite3.connect(DB_FILE) as conn:
                cursor = conn.execute("SELECT id, symbol, side, entry_time, entry_price, sl, tp, order_id FROM trades WHERE status = 'OPEN'")
                active_db_trades = cursor.fetchall()
            
            exit_tasks = []
            for trade_id, symbol, side, entry_time_str, entry_price, sl, tp, order_id in active_db_trades:
                position_info = current_positions_symbols_on_exchange.get(symbol)
                exit_tasks.append(manage_trade_exit(bybit, trade_id, symbol, side, entry_time_str, entry_price, sl, tp, position_info, utc_time))
            await asyncio.gather(*exit_tasks)

            # Refresh active_db_trades after exits
            active_db_trades = []
            with sqlite3.connect(DB_FILE) as conn:
                cursor = conn.execute("SELECT id, symbol, side FROM trades WHERE status = 'OPEN'")
                active_db_trades = cursor.fetchall()
            current_db_positions_symbols = [t[1] for t in active_db_trades]

            # --- Signal Search and Order Placement ---
            signal_tasks = []
            for symbol in symbols:
                if len(current_db_positions_symbols) >= BOT_CONFIG["MAX_POSITIONS"]:
                    logging.info(f"Max positions ({BOT_CONFIG['MAX_POSITIONS']}) reached. Halting signal checks for this cycle.")
                    break
                
                if symbol in current_db_positions_symbols:
                    logging.debug(f"Skipping {symbol} as there is already an open position in DB tracker.")
                    continue

                open_orders_for_symbol = await bybit.get_open_orders(symbol)
                if len(open_orders_for_symbol) >= BOT_CONFIG["MAX_OPEN_ORDERS_PER_SYMBOL"]:
                    logging.debug(f"Skipping {symbol} as there are {len(open_orders_for_symbol)} open orders (max {BOT_CONFIG['MAX_OPEN_ORDERS_PER_SYMBOL']}).")
                    continue

                signal_tasks.append(process_symbol_for_signal(bybit, symbol, balance, utc_time))

            await asyncio.gather(*signal_tasks)

            logging.info(f'--- Cycle finished. Waiting {BOT_CONFIG["LOOP_WAIT_TIME_SECONDS"]} seconds for next loop. ---')
            await asyncio.sleep(BOT_CONFIG['LOOP_WAIT_TIME_SECONDS'])
    finally:
        await bybit.close_session()

async def reconcile_positions(bybit: Bybit, exchange_positions: Dict[str, Dict[str, Any]], utc_time: datetime.datetime):
    """Reconciles database tracked positions with actual exchange positions."""
    db_positions = {}
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.execute("SELECT id, order_id, symbol, side, status, entry_price FROM trades WHERE status = 'OPEN'")
        for row in cursor.fetchall():
            db_positions[row[2]] = {'db_id': row[0], 'order_id': row[1], 'side': row[3], 'status': row[4], 'entry_price': row[5]}
    
    # 1. Mark DB positions as CLOSED if not found on exchange
    for symbol, db_info in db_positions.items():
        if symbol not in exchange_positions:
            logging.warning(f"Position for {symbol} found in DB (ID: {db_info['db_id']}) but not on exchange. Marking as CLOSED.")
            current_price = await bybit.get_current_price(symbol)
            pnl = (current_price - db_info['entry_price']) * (1 if db_info['side'] == 'Buy' else -1) if current_price else 0
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute("UPDATE trades SET status = ?, exit_time = ?, exit_price = ?, pnl = ? WHERE id = ?",
                             ('CLOSED', utc_time.isoformat(), current_price, pnl, db_info['db_id']))

    # 2. Add exchange positions to DB if not found in DB
    for symbol, ex_info in exchange_positions.items():
        if symbol not in db_positions:
            logging.warning(f"Position for {symbol} found on exchange but not in DB. Adding as RECONCILED.")
            # Assume entry price is mark price if original entry isn't available
            entry_price = float(ex_info['avgPrice']) if float(ex_info['avgPrice']) > 0 else float(ex_info['markPrice'])
            p_uuid = str(uuid.uuid4())
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute("INSERT INTO trades(id, order_id, symbol, side, qty, entry_time, entry_price, sl, tp, status, exit_time, exit_price, pnl) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             (p_uuid, ex_info.get('orderId', 'N/A'), symbol, ex_info['side'], float(ex_info['size']), 
                              utc_time.isoformat(), entry_price, 
                              float(ex_info['stopLoss']), float(ex_info['takeProfit']), # Use current SL/TP from exchange
                              'RECONCILED', None, None, None)) # Mark as reconciled, no exit details yet

async def manage_trade_exit(bybit: Bybit, trade_id: str, symbol: str, side: str, entry_time_str: str, entry_price: float, sl_db: float, tp_db: float, position_info: Optional[Dict[str, Any]], utc_time: datetime.datetime):
    """Handles exiting an open trade based on various conditions."""
    if not position_info:
        logging.info(f"Position for {symbol} not found on exchange while managing trade {trade_id}. Marking as CLOSED in DB tracker.")
        current_price = await bybit.get_current_price(symbol)
        pnl = (current_price - entry_price) * (1 if side == 'Buy' else -1) if current_price else 0
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("UPDATE trades SET status = ?, exit_time = ?, exit_price = ?, pnl = ? WHERE id=?",
                         ('CLOSED', utc_time.isoformat(), current_price, pnl, trade_id))
        return

    klines_df = await bybit.klines(symbol, BOT_CONFIG["TIMEFRAME"], limit=BOT_CONFIG.get("MAX_HOLDING_CANDLES", 50) + 5)
    if klines_df.empty or len(klines_df) < 2:
        logging.warning(f"Not enough klines for {symbol} to manage existing trade. Skipping exit check.")
        return
    
    df_with_indicators = build_indicators(klines_df)
    last_row = df_with_indicators.iloc[-1]
    current_price = last_row['Close']
    
    reason_to_exit = None

    # Calculate PNL for fixed profit target
    current_pnl_percentage = 0.0
    if entry_price > 0:
        if side == 'Buy':
            current_pnl_percentage = (current_price - entry_price) / entry_price
        else: # Sell
            current_pnl_percentage = (entry_price - current_price) / entry_price

    # Fixed Profit Target Exit
    if BOT_CONFIG.get("FIXED_PROFIT_TARGET_PCT", 0) > 0 and current_pnl_percentage >= BOT_CONFIG["FIXED_PROFIT_TARGET_PCT"]:
        reason_to_exit = f"Fixed Profit Target ({BOT_CONFIG['FIXED_PROFIT_TARGET_PCT'] * 100:.1f}%) reached (Current PnL: {current_pnl_percentage * 100:.1f}%)"

    # Chandelier Exit (Trailing Stop equivalent, dynamic update if active)
    new_sl_price = sl_db # Start with current SL in DB
    if BOT_CONFIG.get("TRAILING_STOP_ACTIVE", True):
        if side == 'Buy':
            ch_sl = last_row['ch_long']
            if ch_sl > new_sl_price: # Only trail SL upwards
                new_sl_price = ch_sl
        elif side == 'Sell':
            ch_sl = last_row['ch_short']
            if ch_sl < new_sl_price: # Only trail SL downwards
                new_sl_price = ch_sl
        
        price_prec, _ = await bybit.get_precisions(symbol)
        new_sl_price = round(new_sl_price, price_prec)

        if abs(new_sl_price - sl_db) / sl_db > 0.0001: # Only modify if SL moved significantly
            await bybit.modify_position_tpsl(symbol, tp_price=round(tp_db, price_prec), sl_price=new_sl_price)
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute("UPDATE trades SET sl = ? WHERE id=?", (new_sl_price, trade_id))
            logging.debug(f"[{symbol}] Trailing Stop Loss updated to {new_sl_price:.4f}.")
            sl_db = new_sl_price # Update for current check

        # Check if price hit the *current* effective stop loss (either initial or trailed)
        if side == 'Buy' and current_price <= sl_db:
            reason_to_exit = f"Stop Loss hit (current price {current_price:.4f} <= SL {sl_db:.4f})"
        elif side == 'Sell' and current_price >= sl_db:
            reason_to_exit = f"Stop Loss hit (current price {current_price:.4f} >= SL {sl_db:.4f})"
            
    # Fisher Transform Flip Early Exit
    if reason_to_exit is None and BOT_CONFIG.get("USE_FISHER_EXIT", True):
        if side == 'Buy' and last_row['fisher'] < 0 and df_with_indicators['fisher'].iloc[-2] >= 0:
            reason_to_exit = f"Fisher Transform (bearish flip: {last_row['fisher']:.2f})"
        elif side == 'Sell' and last_row['fisher'] > 0 and df_with_indicators['fisher'].iloc[-2] <= 0:
            reason_to_exit = f"Fisher Transform (bullish flip: {last_row['fisher']:.2f})"

    # Time-based Exit
    entry_dt = datetime.datetime.fromisoformat(entry_time_str).replace(tzinfo=pytz.utc)
    elapsed_candles = (utc_time - entry_dt).total_seconds() / (BOT_CONFIG["TIMEFRAME"] * 60)
    if reason_to_exit is None and elapsed_candles >= BOT_CONFIG["MAX_HOLDING_CANDLES"]:
        reason_to_exit = f"Max holding candles ({BOT_CONFIG['MAX_HOLDING_CANDLES']}) exceeded"

    if reason_to_exit:
        logging.info(f"{ColoredFormatter.MAGENTA}Closing {side} position for {symbol} due to: {reason_to_exit}{ColoredFormatter.RESET}")
        await bybit.cancel_all_open_orders(symbol)
        await asyncio.sleep(0.5)
        await bybit.close_position(symbol)
        
        pnl = (current_price - entry_price) * (1 if side == 'Buy' else -1)
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("UPDATE trades SET status = ?, exit_time = ?, exit_price = ?, pnl = ? WHERE id=?",
                         ('CLOSED', utc_time.isoformat(), current_price, pnl, trade_id))
        logging.info(f"Trade {trade_id} for {symbol} marked as CLOSED in DB tracker. PNL: {pnl:.2f} USDT")

async def process_symbol_for_signal(bybit: Bybit, symbol: str, balance: float, utc_time: datetime.datetime):
    """Processes a single symbol for signal generation and order placement."""
    klines_df = await bybit.klines(symbol, BOT_CONFIG["TIMEFRAME"], limit=200)
    if klines_df.empty or len(klines_df) < BOT_CONFIG["MIN_KLINES_FOR_STRATEGY"]:
        logging.warning(f"Not enough klines data for {symbol} (needed >{BOT_CONFIG['MIN_KLINES_FOR_STRATEGY']}). Skipping.")
        return

    signal, current_price, sl_price, tp_price, signal_reason = await generate_signal(bybit, symbol, klines_df)
    
    df_with_indicators = build_indicators(klines_df)
    if not df_with_indicators.empty:
        last_row_indicators = df_with_indicators.iloc[-1]
        log_details = (
            f"Price: {current_price:.4f} | "
            f"ATR ({BOT_CONFIG['ATR_PERIOD']}): {last_row_indicators['atr']:.4f} | "
            f"Dyn Mult: {last_row_indicators['dynamic_multiplier']:.2f} | "
            f"EMA S({BOT_CONFIG['EMA_SHORT_PERIOD']}): {last_row_indicators['ema_s']:.4f} | "
            f"EMA L({BOT_CONFIG['EMA_LONG_PERIOD']}): {last_row_indicators['ema_l']:.4f} | "
            f"Trend EMA({BOT_CONFIG['TREND_EMA_PERIOD']}): {last_row_indicators['trend_ema']:.4f} | "
            f"RSI({BOT_CONFIG['RSI_PERIOD']}): {last_row_indicators['rsi']:.2f} | "
            f"Vol Spike: {'Yes' if last_row_indicators['vol_spike'] else 'No'} | "
            f"EST Slow: {last_row_indicators['est_slow']:.2f} | "
            f"Fisher: {last_row_indicators['fisher']:.2f}"
        )
        if BOT_CONFIG.get("USE_STOCH_FILTER", False):
             log_details += f" | Stoch K/D: {last_row_indicators['stoch_k']:.2f}/{last_row_indicators['stoch_d']:.2f}"
        if BOT_CONFIG.get("USE_MACD_FILTER", False):
             log_details += f" | MACD Line/Sig: {last_row_indicators['macd_line']:.2f}/{last_row_indicators['macd_signal']:.2f}"
        if BOT_CONFIG.get("USE_ADX_FILTER", False):
             log_details += f" | ADX: {last_row_indicators['adx']:.2f}"
        logging.debug(f"[{symbol}] Indicators: {log_details}")

    if signal == 'none':
        logging.debug(f"[{symbol}] No trading signal ({signal_reason}).")
        return

    logging.info(f"{ColoredFormatter.BOLD}{ColoredFormatter.GREEN if signal == 'Buy' else ColoredFormatter.RED}{signal} SIGNAL for {symbol} {('📈' if signal == 'Buy' else '📉')}{ColoredFormatter.RESET}")
    logging.info(f"[{symbol}] Reasoning: {signal_reason}. Calculated TP: {tp_price:.4f}, SL: {sl_price:.4f}")

    price_precision, qty_precision = await bybit.get_precisions(symbol)
    
    capital_for_risk = balance
    risk_amount_usdt = capital_for_risk * BOT_CONFIG["RISK_PER_TRADE_PCT"]
    
    risk_distance = abs(current_price - sl_price) if sl_price is not None else 0
    if risk_distance <= 0:
        logging.warning(f"[{symbol}] Calculated risk_distance is zero or negative. Skipping order.")
        return

    order_qty_risk_based = risk_amount_usdt / risk_distance
    max_notional_qty = BOT_CONFIG.get("MAX_NOTIONAL_PER_TRADE_USDT", 1e9) / current_price if current_price else 1e9
    order_qty_calculated = min(order_qty_risk_based, max_notional_qty)
    order_qty = round(order_qty_calculated, qty_precision)
    
    if order_qty <= 0:
        logging.warning(f"[{symbol}] Calculated order quantity is zero or negative ({order_qty}). Skipping order.")
        return

    await bybit.set_margin_mode_and_leverage(symbol, BOT_CONFIG["MARGIN_MODE"], BOT_CONFIG["LEVERAGE"])
    await asyncio.sleep(0.5)

    order_id = None
    order_type_config = BOT_CONFIG.get("ORDER_TYPE", "Market").lower()
    
    best_bid, best_ask = await bybit.get_orderbook_levels(symbol)
    
    if order_type_config == 'limit':
        limit_execution_price = None
        if signal == 'Buy' and best_bid is not None and (current_price - best_bid) < (current_price * BOT_CONFIG["PRICE_DETECTION_THRESHOLD_PCT"]):
            limit_execution_price = round(best_bid, price_precision)
            logging.info(f"[{symbol}] Price near best bid at {best_bid:.4f}. Placing Limit Order to Buy at bid.")
        elif signal == 'Sell' and best_ask is not None and (best_ask - current_price) < (current_price * BOT_CONFIG["PRICE_DETECTION_THRESHOLD_PCT"]):
            limit_execution_price = round(best_ask, price_precision)
            logging.info(f"[{symbol}] Price near best ask at {best_ask:.4f}. Placing Limit Order to Sell at ask.")
        else:
            limit_execution_price = round(current_price, price_precision)
            logging.info(f"[{symbol}] No specific S/R condition for limit. Placing Limit Order at current price {limit_execution_price:.4f}.")
        
        if limit_execution_price:
            order_id = await bybit.place_limit_order(
                symbol=symbol, side=signal, price=limit_execution_price, qty=order_qty,
                tp_price=round(tp_price, price_precision), sl_price=round(sl_price, price_precision),
                time_in_force='PostOnly' if BOT_CONFIG.get("POST_ONLY", False) else 'GTC'
            )
    elif order_type_config == 'conditional':
        trigger_price = None
        if signal == 'Buy':
            trigger_price = current_price * (1 + BOT_CONFIG.get("BREAKOUT_TRIGGER_PERCENT", 0.001))
        else:
            trigger_price = current_price * (1 - BOT_CONFIG.get("BREAKOUT_TRIGGER_PERCENT", 0.001))
        
        trigger_price = round(trigger_price, price_precision)
        logging.info(f"[{symbol}] Placing Conditional Market Order triggered at {trigger_price:.4f}.")
        order_id = await bybit.place_conditional_order(
            symbol=symbol, side=signal, qty=order_qty, trigger_price=trigger_price,
            order_type='Market', tp_price=round(tp_price, price_precision), sl_price=round(sl_price, price_precision)
        )
    else:
        logging.info(f"[{symbol}] Placing Market Order.")
        order_id = await bybit.place_market_order(
            symbol=symbol, side=signal, qty=order_qty,
            tp_price=round(tp_price, price_precision), sl_price=round(sl_price, price_precision)
        )
    
    if order_id:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("INSERT INTO trades(id, order_id, symbol, side, qty, entry_time, entry_price, sl, tp, status, exit_time, exit_price, pnl) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (str(uuid.uuid4()), order_id, symbol, signal, order_qty, utc_time.isoformat(), current_price, sl_price, tp_price, 'OPEN', None, None, None))
        logging.info(f"New trade logged for {symbol} ({signal} {order_qty}). Order ID: {order_id}")


# -------------- tiny helpers --------------
def get_current_time(tz_str: str) -> Tuple[datetime.datetime, datetime.datetime]:
    t = pytz.timezone(tz_str)
    return datetime.datetime.now(t), datetime.datetime.now(pytz.utc)

def is_market_open(local_time: datetime.datetime, open_hour: int, close_hour: int) -> bool:
    current_hour = local_time.hour
    if open_hour < close_hour:
        return open_hour <= current_hour < close_hour
    return current_hour >= open_hour or current_hour < close_hour

# -------------- start --------------
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt: logging.info("Bot stopped by user via KeyboardInterrupt.")
    except Exception as e: logging.critical(f"Bot terminated due to an unexpected error: {e}", exc_info=True)
