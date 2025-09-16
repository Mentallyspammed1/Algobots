#!/usr/bin/env python3
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Chandelier-Exit Scalper  –  UPGRADED  2025-06-XX
#  Drop-in replacement for chanexit.py – same API, more alpha, less risk
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
import warnings, os, sys, datetime, pytz, time, uuid, sqlite3, logging
import pandas as pd
import pandas_ta as ta
import numpy as np
from typing import Optional, Tuple

# silence the usual noisy packages
warnings.filterwarnings("ignore", category=UserWarning, module='pkg_resources')

from pybit.unified_trading import HTTP
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
               symbol TEXT,
               side TEXT,
               qty REAL,
               entry_time TEXT,
               entry_price REAL,
               sl REAL,
               tp REAL
           )
        """)
_init_db()

# -------------- Bybit client wrapper (unchanged signatures) --------------
class Bybit:
    def __init__(self, api, secret, testnet=False, dry_run=False):
        if not api or not secret: raise ValueError("API Key and Secret must be provided.")
        self.api, self.secret, self.testnet, self.dry_run = api, secret, testnet, dry_run
        self.session = HTTP(api_key=api, api_secret=secret, testnet=testnet)
        logging.info(f"Bybit client ready – testnet={testnet}  dry_run={dry_run}")

    # ~~~~~~~~~~~~~~ pass-through helpers ~~~~~~~~~~~~~~
    def get_balance(self, coin="USDT") -> float:
        try:
            resp=self.session.get_wallet_balance(accountType="UNIFIED", coin=coin)
            if resp['retCode']==0 and resp['result']['list']:
                for c in resp['result']['list'][0]['coin']:
                    if c['coin']==coin: return float(c['walletBalance'])
            logging.error(f"balance fetch issue: {resp.get('retMsg', 'Unknown error')} (Code: {resp.get('retCode', 'N/A')})")
            return 0.
        except Exception as e: logging.error(f"get_balance error: {e}"); return 0.

    def get_positions(self, settleCoin="USDT") -> list[str]:
        try:
            resp=self.session.get_positions(category='linear', settleCoin=settleCoin)
            if resp['retCode']==0:
                return [p['symbol'] for p in resp['result']['list'] if float(p['size'])>0]
            logging.error(f"Error getting positions: {resp.get('retMsg', 'Unknown error')} (Code: {resp.get('retCode', 'N/A')})")
            return []
        except Exception as e: logging.error(f"get_positions: {e}"); return []

    def get_tickers(self) -> Optional[list[str]]:
        try:
            r=self.session.get_tickers(category="linear")
            if r['retCode']==0: return [t['symbol'] for t in r['result']['list'] if 'USDT' in t['symbol'] and 'USDC' not in t['symbol']]
            logging.error(f"Error getting tickers: {r.get('retMsg', 'Unknown error')} (Code: {r.get('retCode', 'N/A')})")
        except Exception as e: logging.error(f"get_tickers: {e}")
        return None

    def klines(self, symbol: str, timeframe: int, limit: int = 500) -> pd.DataFrame:
        try:
            r=self.session.get_kline(category='linear', symbol=symbol, interval=str(timeframe), limit=limit)
            if r['retCode']==0:
                df=pd.DataFrame(r['result']['list'], columns=['Time','Open','High','Low','Close','Volume','Turnover']).astype(float)
                df['Time']=pd.to_datetime(df['Time'], unit='ms')
                df=df.set_index('Time').sort_index()
                if df[['Open', 'High', 'Low', 'Close']].isnull().all().any():
                    logging.warning(f"Critical OHLCV columns are all NaN for {symbol}. Skipping this kline data.")
                    return pd.DataFrame()
                return df
            logging.error(f"Error getting klines for {symbol}: {r.get('retMsg', 'Unknown error')} (Code: {r.get('retCode', 'N/A')})")
        except Exception as e: logging.error(f"klines error {symbol}: {e}")
        return pd.DataFrame()

    def get_orderbook_levels(self, symbol: str, limit: int = 50) -> Tuple[Optional[float], Optional[float]]:
        try:
            r=self.session.get_orderbook(category='linear', symbol=symbol, limit=limit)
            if r['retCode']==0 and 'result' in r and 'b' in r['result'] and 'a' in r['result']:
                bids=pd.DataFrame(r['result']['b'], columns=['price','volume']).astype(float)
                asks=pd.DataFrame(r['result']['a'], columns=['price','volume']).astype(float)
                return bids.loc[bids['volume'].idxmax(),'price'] if not bids.empty else None, \
                       asks.loc[asks['volume'].idxmax(),'price'] if not asks.empty else None
            logging.error(f"Error getting orderbook for {symbol}: {r.get('retMsg', 'Unknown error')} (Code: {r.get('retCode', 'N/A')})")
        except Exception as e: logging.error(f"orderbook: {e}")
        return None, None

    def get_precisions(self, symbol: str) -> Tuple[int, int]:
        try:
            r=self.session.get_instruments_info(category='linear', symbol=symbol)
            if r['retCode']==0 and r['result']['list']:
                info=r['result']['list'][0]
                price_step=info['priceFilter']['tickSize']; qty_step=info['lotSizeFilter']['qtyStep']
                price_prec=len(price_step.split('.')[1]) if '.' in price_step and len(price_step.split('.')) > 1 else 0
                qty_prec=len(qty_step.split('.')[1]) if '.' in qty_step and len(qty_step.split('.')) > 1 else 0
                return price_prec, qty_prec
            logging.error(f"Error getting precisions for {symbol}: {r.get('retMsg', 'Unknown error')} (Code: {r.get('retCode', 'N/A')})")
        except Exception as e: logging.error(f"precisions: {e}")
        return 0, 0

    def set_margin_mode_and_leverage(self, symbol: str, mode: int = 1, leverage: int = 10):
        if self.dry_run:
            logging.info(f"[DRY RUN] would set {symbol} margin={'Isolated' if mode==1 else 'Cross'} {leverage}x")
            return
        try:
            r=self.session.switch_margin_mode(category='linear', symbol=symbol, tradeMode=str(mode),
                                              buyLeverage=str(leverage), sellLeverage=str(leverage))
            if r['retCode']==0: logging.info(f"{symbol} margin={'Isolated' if mode==1 else 'Cross'} {leverage}x set.")
            elif r['retCode'] in (110026,110043): logging.debug(f"{symbol} margin/leverage already set (Code: {r['retCode']}).")
            else: logging.warning(f"Failed to set margin mode/leverage for {symbol}: {r.get('retMsg', 'Unknown error')} (Code: {r['retCode']})")
        except Exception as e: logging.error(f"margin/lever error for {symbol}: {e}")

    def place_order_common(self, symbol: str, side: str, order_type: str, qty: float, price: Optional[float]=None, trigger_price: Optional[float]=None, tp_price: Optional[float]=None, sl_price: Optional[float]=None, time_in_force: str = 'GTC') -> Optional[str]:
        if self.dry_run:
            oid=f"DRY_{uuid.uuid4()}"
            log_msg = f"[DRY RUN] {order_type} {side} {qty} {symbol}"
            if price: log_msg += f" price={price}"
            if trigger_price: log_msg += f" trigger={trigger_price}"
            if tp_price: log_msg += f" TP={tp_price}"
            if sl_price: log_msg += f" SL={sl_price}"
            logging.info(f"{log_msg}. Simulated Order ID: {oid}")
            return oid
        try:
            params=dict(category='linear', symbol=symbol, side=side, orderType=order_type, qty=str(qty), timeInForce=time_in_force)
            if price is not None: params['price']=str(price)
            if trigger_price is not None: params['triggerPrice']=str(trigger_price); params['triggerBy']='MarkPrice'
            if tp_price is not None: params['takeProfit']=str(tp_price); params['tpTriggerBy']='Market'
            if sl_price is not None: params['stopLoss']=str(sl_price); params['slTriggerBy']='Market'
            r=self.session.place_order(**params)
            if r['retCode']==0:
                logging.info(f"Order placed for {symbol} ({order_type} {side} {qty}). Order ID: {r['result']['orderId']}")
                return r['result']['orderId']
            logging.error(f"Failed to place order for {symbol} ({order_type} {side} {qty}): {r.get('retMsg', 'Unknown error')} (Code: {r['retCode']})")
        except Exception as e: logging.error(f"Exception placing {order_type} order for {symbol}: {e}")
        return None

    def place_market_order(self, symbol: str, side: str, qty: float, tp_price: Optional[float]=None, sl_price: Optional[float]=None) -> Optional[str]:
        return self.place_order_common(symbol, side, 'Market', qty, tp_price=tp_price, sl_price=sl_price)

    def place_limit_order(self, symbol: str, side: str, price: float, qty: float, tp_price: Optional[float]=None, sl_price: Optional[float]=None, time_in_force: str = 'GTC') -> Optional[str]:
        return self.place_order_common(symbol, side, 'Limit', qty, price=price, tp_price=tp_price, sl_price=sl_price, time_in_force=time_in_force)

    def place_conditional_order(self, symbol: str, side: str, qty: float, trigger_price: float, order_type: str='Market', price: Optional[float]=None, tp_price: Optional[float]=None, sl_price: Optional[float]=None) -> Optional[str]:
        if order_type=='Limit' and price is None:
            price=trigger_price
            logging.warning(f"Conditional limit order requested for {symbol} without explicit `price`. Using `trigger_price` as limit execution price.")
        return self.place_order_common(symbol, side, order_type, qty, price=price, trigger_price=trigger_price, tp_price=tp_price, sl_price=sl_price)

    def cancel_all_open_orders(self, symbol: str) -> dict:
        if self.dry_run:
            logging.info(f"[DRY RUN] Would cancel all open orders for {symbol}.")
            return {'retCode':0, 'retMsg':'OK'}
        try:
            r=self.session.cancel_all_orders(category='linear', symbol=symbol)
            if r['retCode']==0: logging.info(f"All open orders for {symbol} cancelled successfully.")
            else: logging.warning(f"Failed to cancel all orders for {symbol}: {r.get('retMsg', 'Unknown error')} (Code: {r['retCode']})")
            return r
        except Exception as e: logging.error(f"Exception cancelling all orders for {symbol}: {e}"); return {'retCode':-1, 'retMsg':str(e)}

    def get_open_orders(self, symbol: Optional[str]=None) -> list[dict]:
        try:
            params={'category':'linear'}
            if symbol: params['symbol']=symbol
            r=self.session.get_open_orders(**params)
            if r['retCode']==0: return r['result']['list']
            logging.error(f"Error getting open orders for {symbol if symbol else 'all symbols'}: {r.get('retMsg', 'Unknown error')} (Code: {r['retCode']})")
        except Exception as e: logging.error(f"Exception getting open orders for {symbol if symbol else 'all symbols'}: {e}")
        return []

    def close_position(self, symbol: str, position_idx: int=0) -> Optional[str]:
        if self.dry_run:
            logging.info(f"[DRY RUN] Would close position for {symbol} with a market order.")
            return f"DRY_CLOSE_{uuid.uuid4()}"
        try:
            pos_resp=self.session.get_positions(category='linear', symbol=symbol)
            if pos_resp['retCode']!=0 or not pos_resp['result']['list']:
                logging.warning(f"Could not get position details for {symbol} to close. {pos_resp.get('retMsg', 'No position found')}")
                return None
            
            position_info = next((p for p in pos_resp['result']['list'] if float(p['size']) > 0), None)
            if not position_info:
                logging.info(f"No open position found for {symbol} to close (size is 0).")
                return None

            side_to_close='Sell' if position_info['side']=='Buy' else 'Buy'
            r=self.session.place_order(category='linear', symbol=symbol, side=side_to_close, orderType='Market',
                                       qty=position_info['size'], reduceOnly=True, positionIdx=position_idx)
            if r['retCode']==0:
                logging.info(f"Market order placed to close {symbol} position ({position_info['side']} {position_info['size']}). Order ID: {r['result']['orderId']}")
                return r['result']['orderId']
            else:
                logging.error(f"Failed to place market order to close {symbol} position: {r.get('retMsg', 'Unknown error')} (Code: {r['retCode']})")
        except Exception as e: logging.error(f"Exception closing position for {symbol}: {e}")
        return None

# -------------- higher TF confirmation --------------
def higher_tf_trend(bybit: Bybit, symbol: str) -> str:
    """Returns 'long' 'short' or 'none' based on 5-min EMA cross"""
    htf = BOT_CONFIG.get("HIGHER_TF_TIMEFRAME", 5)
    short = BOT_CONFIG.get("H_TF_EMA_SHORT_PERIOD", 8)
    long = BOT_CONFIG.get("H_TF_EMA_LONG_PERIOD", 21)
    df = bybit.klines(symbol, htf, limit=long+5)
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
    """Calculates Ehlers Supertrend and returns the trend direction series."""
    # pandas_ta's supertrend returns a DataFrame, with the last column being the trend.
    st = ta.supertrend(df['High'], df['Low'], df['Close'], length=length, multiplier=multiplier)
    if st.empty or st.shape[1] < 3: # Ensure Supertrend_L_M, Supertrend_S_M, Supertrend_D columns exist
        return pd.Series(np.nan, index=df.index)
    return st.iloc[:,-1] # Last column is the trend direction

# -------------- Fisher Transform --------------
def fisher_transform(df: pd.DataFrame, period: int = 8) -> pd.Series:
    """Calculates Fisher Transform and returns the trigger series."""
    # pandas_ta's fisher returns a DataFrame, with the last column being the trigger.
    fisher = ta.fisher(df['High'], df['Low'], length=period)
    if fisher.empty or fisher.shape[1] < 2: # Ensure FISHER_L, FISHER_T columns exist
        return pd.Series(np.nan, index=df.index)
    return fisher.iloc[:,-1] # Last column is the trigger

# -------------- upgraded chandelier + multi-TF --------------
def build_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Returns df with all needed cols + NaNs filled"""
    df=df.copy()
    for c in ['Open','High','Low','Close','Volume']:
        df[c]=pd.to_numeric(df[c], errors='coerce')
        df[c]=df[c].ffill().fillna(0) # Forward fill then fill remaining with 0
    
    # Calculate ATR
    atr_series = ta.atr(df['High'], df['Low'], df['Close'], BOT_CONFIG["ATR_PERIOD"])
    df['atr'] = atr_series.fillna(method='ffill').fillna(0) # Handle initial NaNs
    
    # Highest High / Lowest Low for Chandelier Exit
    df['highest_high'] = df['High'].rolling(BOT_CONFIG["ATR_PERIOD"]).max().fillna(method='ffill').fillna(0)
    df['lowest_low'] = df['Low'].rolling(BOT_CONFIG["ATR_PERIOD"]).min().fillna(method='ffill').fillna(0)

    # Dynamic ATR multiplier
    if len(df) >= 20: # Ensure enough data for 20-period std
        df['volatility'] = df['atr'].rolling(window=20).std()
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

    df['dynamic_multiplier'] = df['dynamic_multiplier'].fillna(method='ffill').fillna(BOT_CONFIG["CHANDELIER_MULTIPLIER"]) # Fill any NaNs after calculation

    # Chandelier Exit levels
    df['ch_long'] = df['highest_high'] - (df['atr'] * df['dynamic_multiplier'])
    df['ch_short'] = df['lowest_low'] + (df['atr'] * df['dynamic_multiplier'])
    
    df['trend_ema'] = ta.ema(df['Close'], BOT_CONFIG["TREND_EMA_PERIOD"]).fillna(method='ffill').fillna(0)
    df['ema_s'] = ta.ema(df['Close'], BOT_CONFIG["EMA_SHORT_PERIOD"]).fillna(method='ffill').fillna(0)
    df['ema_l'] = ta.ema(df['Close'], BOT_CONFIG["EMA_LONG_PERIOD"]).fillna(method='ffill').fillna(0)
    df['rsi'] = ta.rsi(df['Close'], BOT_CONFIG["RSI_PERIOD"]).fillna(method='ffill').fillna(50) # RSI default 50
    
    df['vol_ma'] = ta.sma(df['Volume'], 20).fillna(method='ffill').fillna(0)
    df['vol_spike'] = (df['Volume'] / df['vol_ma']) > BOT_CONFIG["VOLUME_THRESHOLD_MULTIPLIER"]
    
    # Ehlers helpers
    df['est_slow'] = est_supertrend(df, BOT_CONFIG.get("EST_SLOW_LENGTH",8), BOT_CONFIG.get("EST_SLOW_MULTIPLIER",1.2)).fillna(method='ffill').fillna(0)
    df['fisher'] = fisher_transform(df, BOT_CONFIG.get("EHLERS_FISHER_PERIOD",8)).fillna(method='ffill').fillna(0)
    
    return df.ffill().fillna(0) # Final pass to catch any lingering NaNs, filling with 0

# -------------- signal generator --------------
last_signal_bar: dict[str, int] = {}  # symbol -> int(bar timestamp)
def generate_signal(bybit: Bybit, symbol: str, df: pd.DataFrame) -> Tuple[str, float, float, float, str]:
    """
    Returns (signal, current_price, sl, tp, debug_reason)
    signal ∈ ['Buy','Sell','none']
    """
    min_required_klines = max(BOT_CONFIG["MIN_KLINES_FOR_STRATEGY"], BOT_CONFIG["TREND_EMA_PERIOD"], 
                              BOT_CONFIG["EMA_LONG_PERIOD"], BOT_CONFIG["ATR_PERIOD"], 
                              BOT_CONFIG["RSI_PERIOD"], 20, # 20 for Volume MA and volatility std
                              BOT_CONFIG.get("EST_SLOW_LENGTH",8) + 5, BOT_CONFIG.get("EHLERS_FISHER_PERIOD",8) + 5
                             )
    
    if df.empty or len(df) < min_required_klines:
        return 'none', 0, 0, 0, f'not enough bars ({len(df)} < {min_required_klines})'
    
    df = build_indicators(df)
    i = -1 # Current candle
    j = -2 # Previous candle

    # Check for NaN values in critical indicators before proceeding
    critical_indicators_exist = all(col in df.columns and not pd.isna(df[col].iloc[i]) for col in ['Close', 'atr', 'dynamic_multiplier', 'ema_s', 'ema_l', 'trend_ema', 'rsi', 'vol_spike', 'est_slow', 'fisher'])
    if not critical_indicators_exist:
        return 'none', 0, 0, 0, 'critical indicators missing/NaN'

    cp = df['Close'].iloc[i]
    atr = df['atr'].iloc[i]
    dynamic_multiplier = df['dynamic_multiplier'].iloc[i] # This is now always present due to build_indicators
    
    if atr <= 0 or np.isnan(atr) or np.isnan(dynamic_multiplier):
        return 'none', 0, 0, 0, 'bad atr or dynamic multiplier'
    
    risk_distance = atr * dynamic_multiplier
    
    # Multi-TF confirmation
    htf_trend = higher_tf_trend(bybit, symbol)
    if htf_trend == 'none':
        return 'none', 0, 0, 0, 'htf neutral'
    
    # Cool-down period for new signals on the same bar
    current_bar_timestamp = int(df.index[i].timestamp())
    if symbol in last_signal_bar and (current_bar_timestamp - last_signal_bar[symbol]) < (BOT_CONFIG.get("MIN_BARS_BETWEEN_TRADES", 3) * BOT_CONFIG["TIMEFRAME"] * 60):
        return 'none', 0, 0, 0, 'cool-down period active'
    
    # Conditions (with explicit checks for previous candle values if crossover)
    long_cond = (
        df['ema_s'].iloc[i] > df['ema_l'].iloc[i] and
        df['ema_s'].iloc[j] <= df['ema_l'].iloc[j] and # EMA Crossover
        cp > df['trend_ema'].iloc[i] and # Price above long-term trend
        df['rsi'].iloc[i] < BOT_CONFIG["RSI_OVERBOUGHT"] and # RSI not overbought
        df['vol_spike'].iloc[i] and # Volume confirmation
        (htf_trend == 'long') # Higher TF confirmation
    )

    short_cond = (
        df['ema_s'].iloc[i] < df['ema_l'].iloc[i] and
        df['ema_s'].iloc[j] >= df['ema_l'].iloc[j] and # EMA Crossover
        cp < df['trend_ema'].iloc[i] and # Price below long-term trend
        df['rsi'].iloc[i] > BOT_CONFIG["RSI_OVERSOLD"] and # RSI not oversold
        df['vol_spike'].iloc[i] and # Volume confirmation
        (htf_trend == 'short') # Higher TF confirmation
    )

    # Ehlers Supertrend filter
    if BOT_CONFIG.get("USE_EST_SLOW_FILTER", True):
        long_cond = long_cond and (cp > df['est_slow'].iloc[i])
        short_cond = short_cond and (cp < df['est_slow'].iloc[i])
        
    signal = 'none'
    tp_price = None
    sl_price = None
    reason = 'no match'

    if long_cond:
        signal = 'Buy'
        sl_price = cp - risk_distance
        tp_price = cp + (risk_distance * BOT_CONFIG.get("REWARD_RISK_RATIO", 2.2))
        reason = 'EMA cross up, price above trend EMA, RSI not overbought, volume spike, HTF long'
    elif short_cond:
        signal = 'Sell'
        sl_price = cp + risk_distance
        tp_price = cp - (risk_distance * BOT_CONFIG.get("REWARD_RISK_RATIO", 2.2))
        reason = 'EMA cross down, price below trend EMA, RSI not oversold, volume spike, HTF short'
    
    if signal != 'none':
        last_signal_bar[symbol] = current_bar_timestamp # Record the timestamp of the signal bar
    
    return signal, cp, sl_price, tp_price, reason

# -------------- equity guard --------------
equity_reference: Optional[float] = None
def emergency_stop(bybit: Bybit) -> bool:
    global equity_reference
    current_equity = bybit.get_balance()
    if equity_reference is None:
        equity_reference = current_equity
        logging.info(f"Initial equity reference set to {equity_reference:.2f} USDT.")
        return False
    
    if current_equity <= 0: # Avoid division by zero or negative balance
        logging.warning("Current equity is zero or negative. Cannot calculate drawdown.")
        return False
        
    if current_equity < equity_reference:
        drawdown = ((equity_reference - current_equity) / equity_reference) * 100
        if drawdown >= BOT_CONFIG.get("EMERGENCY_STOP_IF_DOWN_PCT", 10):
            logging.critical(f"{ColoredFormatter.BOLD}{ColoredFormatter.RED}!!! EMERGENCY STOP !!! Equity down {drawdown:.1f}%. Shutting down bot.{ColoredFormatter.RESET}")
            return True
    return False

# -------------- main loop --------------
def main():
    symbols = BOT_CONFIG["TRADING_SYMBOLS"]
    if not symbols: logging.info("No symbols configured. Exiting."); return

    bybit = Bybit(BOT_CONFIG["API_KEY"], BOT_CONFIG["API_SECRET"], BOT_CONFIG["TESTNET"], BOT_CONFIG["DRY_RUN"])
    
    mode_info = f"{ColoredFormatter.MAGENTA}{ColoredFormatter.BOLD}DRY RUN{ColoredFormatter.RESET}" if BOT_CONFIG["DRY_RUN"] else f"{ColoredFormatter.GREEN}{ColoredFormatter.BOLD}LIVE{ColoredFormatter.RESET}"
    testnet_info = f"{ColoredFormatter.YELLOW}TESTNET{ColoredFormatter.RESET}" if BOT_CONFIG["TESTNET"] else f"{ColoredFormatter.BLUE}MAINNET{ColoredFormatter.RESET}"
    logging.info(f"Starting trading bot in {mode_info} mode on {testnet_info}. Checking {len(symbols)} symbols.")
    logging.info("Bot started – Press Ctrl+C to stop.")

    while True:
        try:
            local_time, utc_time = get_current_time(BOT_CONFIG["TIMEZONE"])
            logging.info(f"Local Time: {local_time.strftime('%Y-%m-%d %H:%M:%S')} | UTC Time: {utc_time.strftime('%Y-%m-%d %H:%M:%S')}")

            if not is_market_open(local_time, BOT_CONFIG["MARKET_OPEN_HOUR"], BOT_CONFIG["MARKET_CLOSE_HOUR"]):
                logging.info(f"Market is closed ({BOT_CONFIG['MARKET_OPEN_HOUR']}:00-{BOT_CONFIG['MARKET_CLOSE_HOUR']}:00 {BOT_CONFIG['TIMEZONE']}). Skipping this cycle. Waiting {BOT_CONFIG['LOOP_WAIT_TIME_SECONDS']} seconds.")
                time.sleep(BOT_CONFIG['LOOP_WAIT_TIME_SECONDS'])
                continue
                
            if emergency_stop(bybit): break # Exit main loop if emergency stop triggered

            balance = bybit.get_balance()
            if balance is None or balance <= 0:
                logging.error(f'Cannot connect to API or balance is zero/negative ({balance}). Waiting {BOT_CONFIG["LOOP_WAIT_TIME_SECONDS"]} seconds and retrying.')
                time.sleep(BOT_CONFIG['LOOP_WAIT_TIME_SECONDS'])
                continue
            
            logging.info(f'Current balance: {balance:.2f} USDT')
            
            current_positions_api = bybit.get_positions() # Symbols with actual open positions
            logging.info(f'You have {len(current_positions_api)} open positions on exchange: {current_positions_api}')

            # --- Position Exit Manager (Time, Chandelier Exit, Fisher Transform) ---
            active_db_trades = []
            with sqlite3.connect(DB_FILE) as conn:
                cursor = conn.execute("SELECT id, symbol, side, entry_time FROM trades")
                active_db_trades = cursor.fetchall()
            
            for trade_id, symbol, side, entry_time_str in active_db_trades:
                # Check if position still actually exists on exchange
                if not BOT_CONFIG["DRY_RUN"] and symbol not in current_positions_api:
                    logging.info(f"Position for {symbol} not found on exchange. Removing from DB tracker.")
                    with sqlite3.connect(DB_FILE) as conn:
                        conn.execute("DELETE FROM trades WHERE id=?", (trade_id,))
                    continue

                klines_df = bybit.klines(symbol, BOT_CONFIG["TIMEFRAME"], limit=BOT_CONFIG.get("MAX_HOLDING_CANDLES", 50) + 5) # Enough for indicators and time-based check
                if klines_df.empty or len(klines_df) < 2:
                    logging.warning(f"Not enough klines for {symbol} to manage existing trade. Skipping exit check.")
                    continue
                
                df_with_indicators = build_indicators(klines_df)
                last_row = df_with_indicators.iloc[-1]
                current_price = last_row['Close']
                
                reason_to_exit = None

                # Chandelier Exit (Trailing Stop equivalent)
                if side == 'Buy' and current_price < last_row['ch_long']:
                    reason_to_exit = f"Chandelier Exit (current price {current_price:.4f} < ch_long {last_row['ch_long']:.4f})"
                elif side == 'Sell' and current_price > last_row['ch_short']:
                    reason_to_exit = f"Chandelier Exit (current price {current_price:.4f} > ch_short {last_row['ch_short']:.4f})"
                
                # Fisher Transform Flip Early Exit
                if reason_to_exit is None and BOT_CONFIG.get("USE_FISHER_EXIT", True):
                    if side == 'Buy' and last_row['fisher'] < 0: # Fisher flipped to bearish
                        reason_to_exit = f"Fisher Transform (bearish flip: {last_row['fisher']:.2f})"
                    elif side == 'Sell' and last_row['fisher'] > 0: # Fisher flipped to bullish
                        reason_to_exit = f"Fisher Transform (bullish flip: {last_row['fisher']:.2f})"

                # Time-based Exit
                entry_dt = datetime.datetime.fromisoformat(entry_time_str).replace(tzinfo=pytz.utc)
                elapsed_candles = (utc_time - entry_dt).total_seconds() / (BOT_CONFIG["TIMEFRAME"] * 60)
                if reason_to_exit is None and elapsed_candles >= BOT_CONFIG["MAX_HOLDING_CANDLES"]:
                    reason_to_exit = f"Max holding candles ({BOT_CONFIG['MAX_HOLDING_CANDLES']}) exceeded"

                if reason_to_exit:
                    logging.info(f"{ColoredFormatter.MAGENTA}Closing {side} position for {symbol} due to: {reason_to_exit}{ColoredFormatter.RESET}")
                    bybit.cancel_all_open_orders(symbol)
                    time.sleep(0.5) # Allow some time for cancellations
                    bybit.close_position(symbol)
                    
                    with sqlite3.connect(DB_FILE) as conn:
                        conn.execute("DELETE FROM trades WHERE id=?", (trade_id,))
                    logging.info(f"Trade for {symbol} removed from DB tracker.")

            # --- Signal Search and Order Placement ---
            for symbol in symbols:
                current_db_positions = [t[1] for t in active_db_trades] # Symbols currently in DB
                
                if len(current_db_positions) >= BOT_CONFIG["MAX_POSITIONS"]:
                    logging.info(f"Max positions ({BOT_CONFIG['MAX_POSITIONS']}) reached. Halting signal checks for this cycle.")
                    break # Exit the symbol loop, continue to next main loop iteration

                if symbol in current_db_positions:
                    logging.debug(f"Skipping {symbol} as there is already an open position in DB tracker.")
                    continue

                open_orders_for_symbol = bybit.get_open_orders(symbol)
                if len(open_orders_for_symbol) >= BOT_CONFIG["MAX_OPEN_ORDERS_PER_SYMBOL"]:
                    logging.debug(f"Skipping {symbol} as there are {len(open_orders_for_symbol)} open orders (max {BOT_CONFIG['MAX_OPEN_ORDERS_PER_SYMBOL']}).")
                    continue

                klines_df = bybit.klines(symbol, BOT_CONFIG["TIMEFRAME"], limit=200)
                if klines_df.empty or len(klines_df) < BOT_CONFIG["MIN_KLINES_FOR_STRATEGY"]:
                    logging.warning(f"Not enough klines data for {symbol} (needed >{BOT_CONFIG['MIN_KLINES_FOR_STRATEGY']}). Skipping.")
                    continue

                # Generate signal
                signal, current_price, sl_price, tp_price, signal_reason = generate_signal(bybit, symbol, klines_df)
                
                # Log indicator values and signal info regardless
                df_with_indicators = build_indicators(klines_df) # Rebuild to ensure all indicators are available for logging
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
                        f"EST Slow: {last_row_indicators['est_slow']:.4f} | "
                        f"Fisher: {last_row_indicators['fisher']:.2f}"
                    )
                    logging.debug(f"[{symbol}] Indicators: {log_details}")

                if signal == 'none':
                    logging.debug(f"[{symbol}] No trading signal ({signal_reason}).")
                    continue

                # --- Order Calculation and Placement ---
                logging.info(f"{ColoredFormatter.BOLD}{ColoredFormatter.GREEN if signal == 'Buy' else ColoredFormatter.RED}{signal} SIGNAL for {symbol} {('📈' if signal == 'Buy' else '📉')}{ColoredFormatter.RESET}")
                logging.info(f"[{symbol}] Reasoning: {signal_reason}. Calculated TP: {tp_price:.4f}, SL: {sl_price:.4f}")

                price_precision, qty_precision = bybit.get_precisions(symbol)
                
                # Calculate position size based on risk per trade
                capital_for_risk = balance
                risk_amount_usdt = capital_for_risk * BOT_CONFIG["RISK_PER_TRADE_PCT"]
                
                risk_distance = abs(current_price - sl_price) if sl_price is not None else 0
                if risk_distance <= 0:
                    logging.warning(f"[{symbol}] Calculated risk_distance is zero or negative. Skipping order.")
                    continue

                order_qty_risk_based = risk_amount_usdt / risk_distance
                # Ensure we don't exceed a maximum notional value for a single trade
                max_notional_qty = BOT_CONFIG.get("MAX_NOTIONAL_PER_TRADE_USDT", 1e9) / current_price if current_price else 1e9
                order_qty_calculated = min(order_qty_risk_based, max_notional_qty)
                order_qty = round(order_qty_calculated, qty_precision)
                
                if order_qty <= 0:
                    logging.warning(f"[{symbol}] Calculated order quantity is zero or negative ({order_qty}). Skipping order.")
                    continue

                bybit.set_margin_mode_and_leverage(symbol, BOT_CONFIG["MARGIN_MODE"], BOT_CONFIG["LEVERAGE"])
                time.sleep(0.5) # Give API a moment to process

                order_id = None
                order_type_config = BOT_CONFIG.get("ORDER_TYPE", "Market").lower()
                
                # Fetch S/R levels for limit order strategy
                support, resistance = bybit.get_orderbook_levels(symbol)
                
                if order_type_config == 'limit':
                    limit_execution_price = None
                    if signal == 'Buy' and support is not None and abs(current_price - support) < (current_price * BOT_CONFIG["PRICE_DETECTION_THRESHOLD_PCT"]):
                        limit_execution_price = round(support, price_precision)
                        logging.info(f"[{symbol}] Price near support at {support:.4f}. Placing Limit Order to Buy at support.")
                    elif signal == 'Sell' and resistance is not None and abs(current_price - resistance) < (current_price * BOT_CONFIG["PRICE_DETECTION_THRESHOLD_PCT"]):
                        limit_execution_price = round(resistance, price_precision)
                        logging.info(f"[{symbol}] Price near resistance at {resistance:.4f}. Placing Limit Order to Sell at resistance.")
                    else:
                        # Fallback to current price for limit if no strong S/R condition
                        limit_execution_price = round(current_price, price_precision)
                        logging.info(f"[{symbol}] No specific S/R condition for limit. Placing Limit Order at current price {limit_execution_price:.4f}.")
                    
                    order_id = bybit.place_limit_order(
                        symbol=symbol, side=signal, price=limit_execution_price, qty=order_qty,
                        tp_price=round(tp_price, price_precision), sl_price=round(sl_price, price_precision),
                        time_in_force='PostOnly' if BOT_CONFIG.get("POST_ONLY", False) else 'GTC'
                    )
                elif order_type_config == 'conditional':
                    trigger_price = None
                    if signal == 'Buy':
                        trigger_price = current_price * (1 + BOT_CONFIG.get("BREAKOUT_TRIGGER_PERCENT", 0.001)) # e.g., 0.1% above current price for breakout
                    else: # Sell
                        trigger_price = current_price * (1 - BOT_CONFIG.get("BREAKOUT_TRIGGER_PERCENT", 0.001)) # e.g., 0.1% below current price for breakdown
                    
                    trigger_price = round(trigger_price, price_precision)
                    logging.info(f"[{symbol}] Placing Conditional Market Order triggered at {trigger_price:.4f}.")
                    order_id = bybit.place_conditional_order(
                        symbol=symbol, side=signal, qty=order_qty, trigger_price=trigger_price,
                        order_type='Market', tp_price=round(tp_price, price_precision), sl_price=round(sl_price, price_precision)
                    )
                else: # Default to market order
                    logging.info(f"[{symbol}] Placing Market Order.")
                    order_id = bybit.place_market_order(
                        symbol=symbol, side=signal, qty=order_qty,
                        tp_price=round(tp_price, price_precision), sl_price=round(sl_price, price_precision)
                    )
                
                if order_id:
                    with sqlite3.connect(DB_FILE) as conn:
                        conn.execute("INSERT INTO trades(id, symbol, side, qty, entry_time, entry_price, sl, tp) VALUES(?,?,?,?,?,?,?,?)",
                                     (str(uuid.uuid4()), symbol, signal, order_qty, utc_time.isoformat(), current_price, sl_price, tp_price))
                    logging.info(f"New trade logged for {symbol} ({signal} {order_qty}).")

        except Exception as e:
            logging.critical(f"An unhandled error occurred in the main loop: {e}", exc_info=True)
            # Potentially add more robust error handling, e.g., restart loop, send notification

        logging.info(f'--- Cycle finished. Waiting {BOT_CONFIG["LOOP_WAIT_TIME_SECONDS"]} seconds for next loop. ---')
        time.sleep(BOT_CONFIG['LOOP_WAIT_TIME_SECONDS'])

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
    try: main()
    except KeyboardInterrupt: logging.info("Bot stopped by user via KeyboardInterrupt.")
    except Exception as e: logging.critical(f"Bot terminated due to an unexpected error: {e}", exc_info=True)
