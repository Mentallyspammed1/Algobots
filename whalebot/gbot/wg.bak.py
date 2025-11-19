import os
import sys
import time
import json
import re
import logging
import signal
import requests
import random
import uuid
import numpy as np
import pandas as pd
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN, getcontext
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, Literal, Optional, List, Any, Callable, TypeVar, Deque
from collections import deque
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from colorama import Fore, Style, init
from functools import wraps

# --- Global Setup ---
getcontext().prec = 28
init(autoreset=True)
load_dotenv()

# --- Constants & Visuals ---
NEON_GREEN = Fore.LIGHTGREEN_EX
NEON_RED = Fore.LIGHTRED_EX
NEON_BLUE = Fore.CYAN
NEON_YELLOW = Fore.YELLOW
NEON_PURPLE = Fore.MAGENTA
RESET = Style.RESET_ALL

LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = "config.json"

# --- Logging Service ---
def setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False 

    if not logger.handlers:
        fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
        
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(fmt)
        logger.addHandler(ch)
        
        fh = RotatingFileHandler(LOG_DIR / "bot.log", maxBytes=5*1024*1024, backupCount=3)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    return logger

logger = setup_logger("WhaleBot")

# --- Utilities ---

def retry_with_backoff(retries: int = 3, backoff_in_seconds: int = 1):
    """Lightweight retry decorator with exponential backoff."""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            x = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except (requests.RequestException, TimeoutError, ConnectionError) as e:
                    if x == retries:
                        logger.error(f"Max retries reached for {func.__name__}: {e}")
                        raise e
                    sleep = (backoff_in_seconds * 2 ** x) + random.uniform(0, 1)
                    time.sleep(sleep)
                    x += 1
        return wrapper
    return decorator

# --- Data Models ---

@dataclass
class MarketData:
    symbol: str
    price: Decimal
    klines: pd.DataFrame
    timestamp: float
    ob_imbalance: float = 0.0
    pivots: Dict[str, float] = field(default_factory=dict)
    sr_levels: Dict[str, float] = field(default_factory=dict)

    def __repr__(self):
        return f"MarketData(symbol='{self.symbol}', price={self.price}, klines={len(self.klines)}, ob={self.ob_imbalance:.2f})"

@dataclass
class TradeSignal:
    action: Literal["BUY", "SELL", "HOLD"]
    entry: Decimal
    sl: Decimal
    tp: Decimal
    confidence: float
    source: Literal["AI", "TECHNICAL_FALLBACK"]
    reason: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        if self.action not in ["BUY", "SELL", "HOLD"]:
            self.action = "HOLD"
        self.entry = Decimal(str(self.entry))
        self.sl = Decimal(str(self.sl))
        self.tp = Decimal(str(self.tp))

    def __repr__(self):
        return f"Signal({self.action}, Conf={self.confidence:.2f}, Src={self.source})"

@dataclass
class Position:
    id: str
    symbol: str
    side: Literal["BUY", "SELL"]
    entry_price: Decimal
    qty: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    entry_time: datetime
    open_price: Decimal = field(init=False)
    close_price: Optional[Decimal] = field(default=None)
    pnl: Decimal = field(default=Decimal(0))
    status: Literal["OPEN", "CLOSED"] = "OPEN"
    last_update_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        self.open_price = self.entry_price

    def __repr__(self):
        return f"Pos({self.id[:8]}, {self.side}, {self.qty} @ {self.entry_price}, PnL={self.pnl})"

# --- Configuration Service ---

T = TypeVar('T')

class Config:
    DEFAULTS = {
        "symbol": "BTCUSDT",
        "interval": "15",
        "loop_delay": 30,
        "gemini_model": "gemini-1.5-flash", # Changed to 1.5-flash for better stability/quota
        "min_confidence": 0.60,
        "paper_trading": {
            "initial_balance": 1000.0,
            "risk_per_trade": 1.0,
            "fee_rate": 0.00055,
            "slippage": 0.0001
        },
        "indicators": {
            "rsi_period": 14,
            "stoch_period": 14,
            "stoch_k": 3,
            "stoch_d": 3,
            "bb_period": 20,
            "bb_std": 2.0,
            "ehlers_period": 10,
            "ehlers_mult": 3.0,
            "sr_lookback": 20
        }
    }

    def __init__(self):
        self.data = self._load_config()
        self._validate()

    def _load_config(self) -> Dict:
        if not Path(CONFIG_FILE).exists():
            self._save_defaults()
            return self.DEFAULTS.copy()
        
        try:
            with open(CONFIG_FILE, 'r') as f:
                user_cfg = json.load(f)
            return self._deep_update(self.DEFAULTS.copy(), user_cfg)
        except FileNotFoundError:
            logger.warning(f"Config file not found. Using defaults.")
            return self.DEFAULTS.copy()
        except json.JSONDecodeError:
            logger.error(f"Config JSON invalid. Using defaults.")
            return self.DEFAULTS.copy()
        except Exception as e:
            logger.error(f"Config load error: {e}. Using defaults.")
            return self.DEFAULTS.copy()

    def _save_defaults(self):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.DEFAULTS, f, indent=4)
        except IOError as e:
            logger.error(f"Failed to write config: {e}")

    def _deep_update(self, target: Dict, source: Dict) -> Dict:
        for k, v in source.items():
            if isinstance(v, dict) and k in target and isinstance(target[k], dict):
                self._deep_update(target[k], v)
            else:
                target[k] = v
        return target

    def _validate(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.critical(f"{NEON_RED}CRITICAL: GEMINI_API_KEY missing in .env{RESET}")
            sys.exit(1)
        
        try:
            genai.configure(api_key=api_key)
        except Exception as e:
            logger.critical(f"Failed to configure Gemini API: {e}")
            sys.exit(1)
            
        if not isinstance(self.data['loop_delay'], int) or self.data['loop_delay'] <= 0:
            logger.warning(f"Invalid loop_delay. Resetting to 30.")
            self.data['loop_delay'] = 30
            
        risk = self.data['paper_trading']['risk_per_trade']
        if not (0 < risk <= 100):
            logger.warning(f"Invalid risk_per_trade. Resetting to 1.0%.")
            self.data['paper_trading']['risk_per_trade'] = 1.0

    def get(self, key: str, default: Optional[T] = None) -> T:
        return self.data.get(key, default)

# --- Market Data Service ---

class MarketDataProvider:
    BASE_URL = "https://api.bybit.com"

    def __init__(self):
        self.session = self._create_session()
        self.executor = ThreadPoolExecutor(max_workers=4)

    def _create_session(self, user_agent: str = "WhaleBot/2.5") -> requests.Session:
        s = requests.Session()
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        s.mount('https://', HTTPAdapter(max_retries=retries))
        s.headers.update({
            "User-Agent": user_agent,
            "Content-Type": "application/json"
        })
        return s

    @retry_with_backoff(retries=3)
    def _get_price(self, symbol: str) -> Decimal:
        resp = self.session.get(
            f"{self.BASE_URL}/v5/market/tickers", 
            params={"category": "linear", "symbol": symbol}, 
            timeout=5
        )
        try:
            resp.raise_for_status()
            price = resp.json()['result']['list'][0]['lastPrice']
            return Decimal(str(price))
        except Exception as e:
            logger.error(f"Price fetch error: {e}")
            raise

    @retry_with_backoff(retries=3)
    def _get_klines(self, symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
        resp = self.session.get(
            f"{self.BASE_URL}/v5/market/kline",
            params={"category": "linear", "symbol": symbol, "interval": interval, "limit": limit},
            timeout=5
        )
        try:
            resp.raise_for_status()
            raw = resp.json()['result']['list']
        except KeyError:
            return pd.DataFrame()

        df = pd.DataFrame(raw, columns=['startTime', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
        cols = ['open', 'high', 'low', 'close', 'volume']
        df[cols] = df[cols].apply(pd.to_numeric, errors='coerce')
        
        if df[cols].isnull().any().any():
            df.dropna(subset=cols, inplace=True)

        if df.empty:
            return pd.DataFrame()

        df['startTime'] = pd.to_datetime(pd.to_numeric(df['startTime']), unit='ms')
        return df.sort_values('startTime').set_index('startTime')

    @retry_with_backoff(retries=3)
    def _get_daily_candle(self, symbol: str) -> Optional[Dict]:
        try:
            df = self._get_klines(symbol, "D", limit=2)
            if len(df) >= 2:
                yesterday = df.iloc[-2]
                return {
                    'high': float(yesterday['high']),
                    'low': float(yesterday['low']),
                    'close': float(yesterday['close'])
                }
        except Exception as e:
            logger.warning(f"Failed to fetch daily candle for pivots: {e}")
        return None

    def _get_ob_imbalance(self, symbol: str) -> float:
        try:
            resp = self.session.get(
                f"{self.BASE_URL}/v5/market/orderbook",
                params={"category": "linear", "symbol": symbol, "limit": 50},
                timeout=3
            )
            data = resp.json()['result']
            bids = np.array(data['b'], dtype=float)
            asks = np.array(data['a'], dtype=float)
            if len(bids) == 0 or len(asks) == 0: return 0.0
            bid_vol = np.sum(bids[:, 1])
            ask_vol = np.sum(asks[:, 1])
            total = bid_vol + ask_vol
            return (bid_vol - ask_vol) / total if total > 0 else 0.0
        except Exception:
            return 0.0

    def fetch_all(self, symbol: str, interval: str) -> Optional[MarketData]:
        f_price = self.executor.submit(self._get_price, symbol)
        f_klines = self.executor.submit(self._get_klines, symbol, interval)
        f_daily = self.executor.submit(self._get_daily_candle, symbol)
        f_ob = self.executor.submit(self._get_ob_imbalance, symbol)

        try:
            price = f_price.result()
            klines = f_klines.result()
            daily_data = f_daily.result()
            ob = f_ob.result()
        except Exception as e:
            logger.error(f"Fetch error: {e}")
            return None

        if klines.empty or price is None:
            return None

        pivots = {}
        if daily_data:
            h, l, c = daily_data['high'], daily_data['low'], daily_data['close']
            p = (h + l + c) / 3
            r1 = p + (0.382 * (h - l))
            r2 = p + (0.618 * (h - l))
            r3 = p + (1.000 * (h - l))
            s1 = p - (0.382 * (h - l))
            s2 = p - (0.618 * (h - l))
            s3 = p - (1.000 * (h - l))
            pivots = {"P": p, "R1": r1, "R2": r2, "R3": r3, "S1": s1, "S2": s2, "S3": s3}

        return MarketData(
            symbol=symbol,
            price=price,
            klines=klines,
            ob_imbalance=ob,
            pivots=pivots,
            timestamp=time.time()
        )

# --- Analysis Service ---

class TechnicalAnalysis:
    @staticmethod
    def calculate(df: pd.DataFrame, cfg: Dict) -> pd.DataFrame:
        max_period = max(cfg['bb_period'], 26, cfg['rsi_period']) + 5
        if df.empty or len(df) < max_period: 
            return df
            
        df = df.copy()
        close = df['close']
        high = df['high']
        low = df['low']
        
        # 1. RSI & Stochastics
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).ewm(alpha=1/cfg['rsi_period'], adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/cfg['rsi_period'], adjust=False).mean()
        df['RSI'] = 100 - (100 / (1 + gain/loss))
        rsi_min = df['RSI'].rolling(cfg['stoch_period']).min()
        rsi_max = df['RSI'].rolling(cfg['stoch_period']).max()
        df['Stoch_K'] = ((df['RSI'] - rsi_min) / (rsi_max - rsi_min)) * 100
        df['Stoch_D'] = df['Stoch_K'].rolling(cfg['stoch_d']).mean()
        
        # 2. Bollinger Bands & MACD
        sma = close.rolling(cfg['bb_period']).mean()
        std = close.rolling(cfg['bb_period']).std()
        df['BB_Upper'] = sma + (std * cfg['bb_std'])
        df['BB_Lower'] = sma - (std * cfg['bb_std'])
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        df['MACD'] = ema12 - ema26
        df['MACD_Sig'] = df['MACD'].ewm(span=9, adjust=False).mean()
        
        # 3. ATR & ADX (FIXED Logic)
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df['ATR'] = tr.ewm(alpha=1/14, adjust=False).mean()
        
        plus_dm_raw = high.diff()
        minus_dm_raw = low.diff()
        plus_dm = pd.Series(0.0, index=df.index)
        minus_dm = pd.Series(0.0, index=df.index)
        
        mask_plus = (plus_dm_raw > minus_dm_raw) & (plus_dm_raw > 0)
        mask_minus = (minus_dm_raw > plus_dm_raw) & (minus_dm_raw > 0)
        
        plus_dm[mask_plus] = plus_dm_raw[mask_plus]
        minus_dm[mask_minus] = minus_dm_raw[mask_minus]
        
        tr_s = tr.ewm(alpha=1/14, adjust=False).mean()
        plus_di = 100 * (plus_dm.ewm(alpha=1/14, adjust=False).mean() / tr_s)
        minus_di = 100 * (minus_dm.ewm(alpha=1/14, adjust=False).mean() / tr_s)
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
        df['ADX'] = dx.ewm(alpha=1/14, adjust=False).mean()

        # 4. Ehlers
        atr_values = df['ATR'].fillna(0).values
        if not np.all(atr_values == 0):
            TechnicalAnalysis._add_ehlers(df, close.values, atr_values, cfg)
        else:
            df['Ehlers_Trend'] = 0
            df['SS_Filter'] = close.values

        # 5. Dynamic S/R
        lookback = cfg.get('sr_lookback', 20)
        df['Swing_High'] = df['high'].rolling(window=lookback).max()
        df['Swing_Low'] = df['low'].rolling(window=lookback).min()
        
        df.fillna(0, inplace=True)
        return df

    @staticmethod
    def get_nearest_sr(df: pd.DataFrame, current_price: float) -> Dict[str, float]:
        if df.empty: return {}
        last = df.iloc[-1]
        return {
            "Dynamic_Res": float(last['Swing_High']),
            "Dynamic_Sup": float(last['Swing_Low'])
        }

    @staticmethod
    def _add_ehlers(df, price, atr, cfg):
        period = cfg['ehlers_period']
        mult = cfg['ehlers_mult']
        a1 = np.exp(-np.pi / period)
        b1 = 2 * a1 * np.cos(np.pi / period)
        c2 = b1
        c3 = -a1 * a1
        c1 = 1 - c2 - c3
        
        filt = np.zeros_like(price)
        ss_tr = np.zeros_like(atr)
        trend = np.zeros_like(price)
        
        if len(price) > 2:
            filt[0:2] = price[0:2]
            ss_tr[0:2] = atr[0:2]

        for i in range(2, len(price)):
            filt[i] = c1 * (price[i] + price[i-1]) / 2 + c2 * filt[i-1] + c3 * filt[i-2]
            ss_tr[i] = c1 * (atr[i] + atr[i-1]) / 2 + c2 * ss_tr[i-1] + c3 * ss_tr[i-2]
            
        upper = filt + mult * ss_tr
        lower = filt - mult * ss_tr
        st = np.zeros_like(price)
        trend[0] = 1
        st[0] = lower[0]

        for i in range(1, len(price)):
            prev_st = st[i-1]
            if trend[i-1] == 1:
                if price[i] < prev_st:
                    trend[i] = -1; st[i] = upper[i]
                else:
                    trend[i] = 1; st[i] = max(lower[i], prev_st)
            else:
                if price[i] > prev_st:
                    trend[i] = 1; st[i] = lower[i]
                else:
                    trend[i] = -1; st[i] = min(upper[i], prev_st)

        df['Ehlers_Trend'] = trend
        df['SS_Filter'] = filt

# --- AI Service ---

class GeminiService:
    def __init__(self, model_name: str):
        self.model = genai.GenerativeModel(model_name)
        self.request_timestamps: Deque[float] = deque()
        self.rate_limit_count = 10 # Reduced for safety on free tier
        self.rate_limit_window = 60

    def _rate_limit(self):
        now = time.time()
        while self.request_timestamps and now - self.request_timestamps[0] > self.rate_limit_window:
            self.request_timestamps.popleft()
        if len(self.request_timestamps) >= self.rate_limit_count:
            wait_time = self.rate_limit_window - (now - self.request_timestamps[0]) + 0.5
            if wait_time > 0:
                logger.warning(f"Rate limit reached. Sleeping {wait_time:.2f}s")
                time.sleep(wait_time)
            now = time.time()
            while self.request_timestamps and now - self.request_timestamps[0] > self.rate_limit_window:
                self.request_timestamps.popleft()
        self.request_timestamps.append(time.time())

    def analyze(self, market: MarketData) -> TradeSignal:
        retries = 0
        max_retries = 3
        
        while retries < max_retries:
            self._rate_limit()
            try:
                prompt = self._build_prompt(market)
                response = self.model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
                return self._parse_response(response.text, market)
            except google_exceptions.ResourceExhausted:
                wait = 20 * (retries + 1)
                logger.warning(f"Quota exceeded (429). Sleeping {wait}s before retry {retries+1}/{max_retries}...")
                time.sleep(wait)
                retries += 1
            except Exception as e:
                logger.error(f"AI Generation Error: {e}")
                return self._fallback(market, "AI Error")
        
        return self._fallback(market, "Quota Exhausted")

    def _build_prompt(self, market: MarketData) -> str:
        last = market.klines.iloc[-1]
        prev = market.klines.iloc[-2]
        pct_change = ((last['close'] - prev['close']) / prev['close']) * 100
        
        key_levels = {**market.pivots, **market.sr_levels}
        
        def clean_val(v):
            if pd.isna(v) or v is None: return 0.0
            return round(float(v), 4)

        context = {
            "price": float(market.price),
            "price_change_24h_pct": clean_val(pct_change),
            "rsi": clean_val(last['RSI']),
            "stoch_k": clean_val(last.get('Stoch_K', 50)),
            "adx": clean_val(last.get('ADX', 0)),
            "macd_val": clean_val(last['MACD']),
            "bb_pos": "ABOVE_UP" if market.price > last['BB_Upper'] else "BELOW_LOW" if market.price < last['BB_Lower'] else "INSIDE",
            "atr": clean_val(last['ATR']),
            "trend_ehlers": "BULLISH" if last['Ehlers_Trend'] == 1 else "BEARISH",
            "ob_imbalance": round(market.ob_imbalance, 3),
            "key_levels": {k: round(v, 2) for k, v in key_levels.items()}
        }

        return f"""
        Act as an aggressive Crypto Scalper. Symbol: {market.symbol}.
        Market Data: {json.dumps(context)}
        
        Key Levels Strategy:
        - Use 'key_levels' (Pivots/Dynamic SR).
        - BUY near Support if trend matches.
        - SELL near Resistance if trend matches.
        
        Indicators:
        - Ehlers Trend + ADX > 25 = Strong Trend.
        - RSI/Stochastics for timing.
        
        Instruction:
        - Output Valid JSON ONLY.
        - Confidence > 0.6: Trade.
        - SL/TP MUST use Key Levels or ATR.
        
        Schema:
        {{
            "action": "BUY|SELL|HOLD",
            "entry": float,
            "sl": float,
            "tp": float,
            "confidence": float,
            "reason": "string (max 15 words)"
        }}
        """

    def _parse_response(self, text: str, market: MarketData) -> TradeSignal:
        cleaned = re.sub(r"```json|```", "", text).strip()
        if not cleaned: return self._fallback(market, "Empty AI Response")

        try:
            data = json.loads(cleaned)
            def get_dec(key, default):
                val = data.get(key)
                return Decimal(str(val)) if val else default

            action = data.get('action', 'HOLD').upper()
            current_price = market.price if isinstance(market.price, Decimal) else Decimal(str(market.price))
            entry = get_dec('entry', current_price)
            last_atr = Decimal(str(market.klines.iloc[-1]['ATR'])) if not market.klines.empty else Decimal(100)
            
            if action == "BUY":
                sl = get_dec('sl', entry - (last_atr * Decimal("1.5")))
                tp = get_dec('tp', entry + (last_atr * Decimal("2.0")))
                if sl >= entry: sl = entry - last_atr
            elif action == "SELL":
                sl = get_dec('sl', entry + (last_atr * Decimal("1.5")))
                tp = get_dec('tp', entry - (last_atr * Decimal("2.0")))
                if sl <= entry: sl = entry + last_atr
            else:
                sl, tp = Decimal(0), Decimal(0)

            return TradeSignal(
                action=action, entry=entry, sl=sl, tp=tp,
                confidence=float(data.get('confidence', 0)),
                source="AI", reason=data.get('reason', 'AI Analysis')
            )
        except Exception as e:
            logger.warning(f"Parse Error: {e}")
            return self._fallback(market, "Parse Error")

    def _fallback(self, market: MarketData, reason: str) -> TradeSignal:
        last = market.klines.iloc[-1]
        trend = last['Ehlers_Trend']
        rsi = last['RSI']
        stoch_k = last.get('Stoch_K', 50)
        
        action = "HOLD"
        conf = 0.0
        
        if trend == 1 and rsi < 45 and stoch_k < 30:
            action = "BUY"; conf = 0.65
        elif trend == -1 and rsi > 55 and stoch_k > 70:
            action = "SELL"; conf = 0.65
        
        price = market.price
        atr = Decimal(str(last['ATR']))
        sl = price - (atr * 2) if action == "BUY" else price + (atr * 2)
        tp = price + (atr * 3) if action == "BUY" else price - (atr * 3)
        
        return TradeSignal(
            action=action, entry=price, sl=sl, tp=tp,
            confidence=conf, source="TECHNICAL_FALLBACK", reason=reason
        )

# --- Execution Service ---

class ExecutionEngine:
    def __init__(self, config: Config):
        self.cfg = config.get("paper_trading")
        self.min_conf = config.get("min_confidence", 0.6)
        self.balance = Decimal(str(self.cfg['initial_balance']))
        self.positions: Dict[str, Position] = {}
        self.history: List[Dict] = []
        self.slippage = Decimal(str(self.cfg['slippage']))
        self.fee_rate = Decimal(str(self.cfg['fee_rate']))

    def execute(self, signal: TradeSignal):
        if signal.action == "HOLD" or signal.confidence < self.min_conf: return
        if self.positions: return
        if signal.entry <= 0: return

        try:
            risk_pct = Decimal(str(self.cfg['risk_per_trade'])) / Decimal("100")
            risk_amt = self.balance * risk_pct
            dist = abs(signal.entry - signal.sl)
            if dist == 0: return

            qty = risk_amt / dist
            max_qty = (self.balance * 5) / signal.entry
            qty = min(qty, max_qty).quantize(Decimal("0.001"), rounding=ROUND_DOWN)
            if qty * signal.entry < 10: return

            entry_price = signal.entry * (Decimal(1) + self.slippage) if signal.action == "BUY" else signal.entry * (Decimal(1) - self.slippage)

            pos_id = str(uuid.uuid4())
            pos = Position(
                id=pos_id, symbol="BTCUSDT", side=signal.action,
                entry_price=entry_price, qty=qty, stop_loss=signal.sl,
                take_profit=signal.tp, entry_time=datetime.now(timezone.utc)
            )
            
            self.balance -= (entry_price * qty * self.fee_rate)
            self.positions[pos_id] = pos
            
            c = NEON_GREEN if signal.action == "BUY" else NEON_RED
            logger.info(f"{c}OPEN {signal.action} | Qty: {qty} | Entry: {entry_price:.2f} | SL: {signal.sl:.2f} | Conf: {signal.confidence:.2f} | Reason: {signal.reason}{RESET}")

        except Exception as e:
            logger.error(f"Execution Logic Error: {e}")

    def update(self, current_price: Decimal):
        for pid, pos in list(self.positions.items()):
            pos.last_update_time = datetime.now(timezone.utc)
            closed = False
            reason = ""
            exit_price = Decimal(0)

            if pos.side == "BUY":
                if current_price <= pos.stop_loss:
                    exit_price = pos.stop_loss * (1 - self.slippage); closed = True; reason = "SL"
                elif current_price >= pos.take_profit:
                    exit_price = pos.take_profit; closed = True; reason = "TP"
            else:
                if current_price >= pos.stop_loss:
                    exit_price = pos.stop_loss * (1 + self.slippage); closed = True; reason = "SL"
                elif current_price <= pos.take_profit:
                    exit_price = pos.take_profit; closed = True; reason = "TP"

            if closed:
                pnl = (exit_price - pos.entry_price) * pos.qty if pos.side == "BUY" else (pos.entry_price - exit_price) * pos.qty
                fee = exit_price * pos.qty * self.fee_rate
                net_pnl = pnl - fee
                self.balance += net_pnl
                del self.positions[pid]
                self.history.append({"pnl": float(net_pnl), "reason": reason})
                
                c = NEON_GREEN if net_pnl > 0 else NEON_RED
                logger.info(f"{c}CLOSE {pos.side} ({reason}) | PnL: ${net_pnl:.2f} | Bal: ${self.balance:.2f}{RESET}")

    def close_all_positions(self):
        if not self.positions: return
        logger.warning(f"{NEON_YELLOW}Closing all {len(self.positions)} positions...{RESET}")
        self.positions.clear()

# --- Main Bot ---

class WhaleBot:
    def __init__(self):
        self.running = True
        signal.signal(signal.SIGINT, self._stop)
        self.cfg = Config()
        self.data = MarketDataProvider()
        self.ai = GeminiService(self.cfg.get("gemini_model"))
        self.exec = ExecutionEngine(self.cfg)

    def _stop(self, sig, frame):
        logger.info("Shutting down...")
        self.exec.close_all_positions()
        self.running = False

    def run(self):
        symbol = self.cfg.get("symbol")
        interval = self.cfg.get("interval")
        delay = self.cfg.get("loop_delay")

        logger.info(f"{NEON_PURPLE}=== WhaleBot Enterprise Started ({symbol}) ==={RESET}")
        logger.info(f"Balance: ${self.exec.balance} | Min Conf: {self.cfg.get('min_confidence')}")

        while self.running:
            try:
                t0 = time.monotonic()
                market = self.data.fetch_all(symbol, interval)
                if not market:
                    logger.warning("Data fetch incomplete. Retrying...")
                    time.sleep(5)
                    continue

                market.klines = TechnicalAnalysis.calculate(market.klines, self.cfg.get("indicators"))
                market.sr_levels = TechnicalAnalysis.get_nearest_sr(market.klines, float(market.price))
                
                sig = self.ai.analyze(market)

                c = NEON_GREEN if sig.action == "BUY" else NEON_RED if sig.action == "SELL" else NEON_BLUE
                reason_short = (sig.reason[:50] + '..') if len(sig.reason) > 50 else sig.reason
                logger.info(f"Price: {market.price:.2f} | {c}{sig.action:<4} ({sig.confidence:.2f}){RESET} | {reason_short}")

                try:
                    self.exec.update(market.price)
                    self.exec.execute(sig)
                except Exception as e:
                    logger.error(f"Error updating positions: {e}")

                elapsed = time.monotonic() - t0
                time.sleep(max(0, delay - elapsed))

            except requests.exceptions.RequestException as e:
                logger.error(f"API Request Error: {e}")
                time.sleep(10)
            except Exception as e:
                logger.error(f"Critical Loop Error: {e}")
                time.sleep(10)

if __name__ == "__main__":
    try:
        bot = WhaleBot()
        bot.run()
    except Exception as e:
        print(f"Fatal Error: {e}")
