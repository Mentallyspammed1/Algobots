import sys
import time
import json
import re
import logging
import signal
import os
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
                except (requests.RequestException, TimeoutError, ConnectionError, google_exceptions.GoogleAPIError) as e:
                    if x == retries:
                        logger.error(f"Max retries reached for {func.__name__}: {e}")
                        raise e
                    sleep = (backoff_in_seconds * 2 ** x) + random.uniform(0, 1)
                    logger.warning(f"Retry {x+1}/{retries} for {func.__name__} after {sleep:.2f}s due to {type(e).__name__}")
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
        # Ensure price inputs are correctly converted to Decimal from whatever they were passed as
        if not isinstance(self.entry, Decimal): self.entry = Decimal(str(self.entry))
        if not isinstance(self.sl, Decimal): self.sl = Decimal(str(self.sl))
        if not isinstance(self.tp, Decimal): self.tp = Decimal(str(self.tp))
        
        if self.action not in ["BUY", "SELL", "HOLD"]:
            self.action = "HOLD"

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
        "symbol": "BTCUSDT", "interval": "15", "loop_delay": 30,
        "gemini_model": "gemini-1.5-flash-latest", "min_confidence": 0.60,
        "paper_trading": {
            "initial_balance": 1000.0, "risk_per_trade": 1.0, "fee_rate": 0.00055, "slippage": 0.0001
        },
        "indicators": {
            "rsi_period": 14, "stoch_period": 14, "stoch_k": 3, "stoch_d": 3,
            "bb_period": 20, "bb_std": 2.0, "ehlers_period": 10, "ehlers_mult": 3.0, "sr_lookback": 20
        }
    }

    def __init__(self):
        self.data = self._load_config()
        self._validate()

    def _load_config(self) -> Dict:
        if not Path(CONFIG_FILE).exists():
            logger.info(f"Config file not found. Creating with defaults.")
            self._save_defaults()
            return self.DEFAULTS.copy()

        try:
            with open(CONFIG_FILE, 'r') as f:
                user_cfg = json.load(f)
            updated_cfg = self._deep_update(self.DEFAULTS.copy(), user_cfg)
            logger.info(f"Configuration loaded successfully from {CONFIG_FILE}")
            return updated_cfg
        except Exception as e:
            logger.error(f"Config load error: {e}. Using defaults.")
            return self.DEFAULTS.copy()

    def _save_defaults(self):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.DEFAULTS, f, indent=4)
            logger.info(f"Default configuration saved to {CONFIG_FILE}")
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
            logger.critical(f"{NEON_RED}CRITICAL: GEMINI_API_KEY missing in .env file.{RESET}")
            sys.exit(1)

        try:
            genai.configure(api_key=api_key)
            genai.list_models() # Test API key
            logger.info("Gemini API key configured successfully.")
        except Exception as e:
            logger.critical(f"Failed to configure or validate Gemini API: {e}")
            sys.exit(1)

        if not isinstance(self.data['loop_delay'], int) or self.data['loop_delay'] <= 0:
            logger.warning(f"Invalid loop_delay ({self.data['loop_delay']}). Resetting to 30.")
            self.data['loop_delay'] = 30
        
        risk = self.data['paper_trading']['risk_per_trade']
        if not (0 < risk <= 100):
            logger.warning(f"Invalid risk_per_trade ({risk}%). Resetting to 1.0%.")
            self.data['paper_trading']['risk_per_trade'] = 1.0

        if not (0 <= self.data['min_confidence'] <= 1):
             logger.warning(f"Invalid min_confidence ({self.data['min_confidence']}). Resetting to 0.6.")
             self.data['min_confidence'] = 0.6

    def get(self, key: str, default: Optional[T] = None) -> T:
        return self.data.get(key, default)

# --- Market Data Service ---

class MarketDataProvider:
    BASE_URL = "https://api.bybit.com"
    MAX_KLINE_LIMIT = 1000

    def __init__(self):
        self.session = self._create_session()
        self.executor = ThreadPoolExecutor(max_workers=5)

    def _create_session(self, user_agent: str = "WhaleBot/2.7") -> requests.Session:
        s = requests.Session()
        retries = Retry(
            total=5, backoff_factor=0.7, status_forcelist=[500, 502, 503, 504, 429],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        s.mount('https://', HTTPAdapter(max_retries=retries))
        s.headers.update({"User-Agent": user_agent, "Content-Type": "application/json"})
        return s

    @retry_with_backoff(retries=5, backoff_in_seconds=2)
    def _get_price(self, symbol: str) -> Decimal:
        resp = self.session.get(
            f"{self.BASE_URL}/v5/market/tickers",
            params={"category": "linear", "symbol": symbol},
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        price = data['result']['list'][0]['lastPrice']
        return Decimal(str(price))

    @retry_with_backoff(retries=5, backoff_in_seconds=2)
    def _get_klines(self, symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
        limit = min(limit, self.MAX_KLINE_LIMIT)
        resp = self.session.get(
            f"{self.BASE_URL}/v5/market/kline",
            params={"category": "linear", "symbol": symbol, "interval": interval, "limit": limit},
            timeout=10
        )
        resp.raise_for_status()
        raw = resp.json()['result']['list']
        if not raw: return pd.DataFrame()

        df = pd.DataFrame(raw, columns=['startTime', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
        cols = ['open', 'high', 'low', 'close', 'volume', 'turnover']
        df[cols] = df[cols].apply(pd.to_numeric, errors='coerce')

        if df[cols].isnull().any().any():
            logger.warning(f"NaN values found in kline data for {symbol}, dropping rows.")
            df.dropna(subset=cols, inplace=True)

        if df.empty: return pd.DataFrame()

        df['startTime'] = pd.to_datetime(pd.to_numeric(df['startTime']), unit='ms')
        return df.sort_values('startTime').set_index('startTime')

    @retry_with_backoff(retries=3, backoff_in_seconds=1)
    def _get_daily_candle(self, symbol: str) -> Optional[Dict]:
        try:
            df = self._get_klines(symbol, "D", limit=2)
            if len(df) >= 2:
                yesterday = df.iloc[-2]
                return {'high': float(yesterday['high']), 'low': float(yesterday['low']), 'close': float(yesterday['close'])}
            else:
                logger.warning(f"Not enough daily data for pivots ({len(df)} bars).")
                return None
        except Exception as e:
            logger.warning(f"Failed to fetch daily candle for pivots: {e}")
            return None

    @retry_with_backoff(retries=3, backoff_in_seconds=1)
    def _get_ob_imbalance(self, symbol: str) -> float:
        try:
            resp = self.session.get(f"{self.BASE_URL}/v5/market/orderbook", params={"category": "linear", "symbol": symbol, "limit": 50}, timeout=5)
            resp.raise_for_status()
            data = resp.json()['result']
            bids = np.array(data.get('b', []), dtype=float)
            asks = np.array(data.get('a', []), dtype=float)

            if bids.size == 0 or asks.size == 0: return 0.0

            bid_vol = np.sum(bids[:, 1])
            ask_vol = np.sum(asks[:, 1])
            total = bid_vol + ask_vol
            return (bid_vol - ask_vol) / total if total > 0 else 0.0
        except Exception as e:
            logger.warning(f"Failed to get orderbook imbalance: {e}")
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
            logger.error(f"Market data fetch error: {e}")
            return None

        if klines.empty or price is None:
            logger.warning(f"Failed to fetch essential data for {symbol}.")
            return None

        pivots = {}
        if daily_data:
            try:
                h, l, c = Decimal(str(daily_data['high'])), Decimal(str(daily_data['low'])), Decimal(str(daily_data['close']))
                p = (h + l + c) / 3
                range_hl = h - l
                if range_hl > 0:
                    r1 = p + (Decimal("0.382") * range_hl); r2 = p + (Decimal("0.618") * range_hl); r3 = p + range_hl
                    s1 = p - (Decimal("0.382") * range_hl); s2 = p - (Decimal("0.618") * range_hl); s3 = p - range_hl
                    pivots = {"P": float(p), "R1": float(r1), "R2": float(r2), "R3": float(r3), "S1": float(s1), "S2": float(s2), "S3": float(s3)}
            except Exception as e:
                logger.warning(f"Error calculating pivots: {e}")

        return MarketData(
            symbol=symbol, price=price, klines=klines, ob_imbalance=ob,
            pivots=pivots, timestamp=time.time()
        )

# --- Analysis Service ---

class TechnicalAnalysis:
    @staticmethod
    def calculate(df: pd.DataFrame, cfg: Dict) -> pd.DataFrame:
        max_period = max(cfg.get('bb_period', 20), cfg.get('rsi_period', 14), cfg.get('stoch_period', 14), cfg.get('sr_lookback', 20)) + 5
        if df.empty or len(df) < max_period:
            logger.warning(f"Not enough data for full indicator calculation. Need {max_period}, have {len(df)}.")
            return df

        df = df.copy()
        close = df['close']; high = df['high']; low = df['low']

        # 1. RSI & Stochastics
        rsi_period = cfg.get('rsi_period', 14)
        stoch_period = cfg.get('stoch_period', 14)
        stoch_k_smooth = cfg.get('stoch_k', 3)
        stoch_d_smooth = cfg.get('stoch_d', 3)

        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).ewm(alpha=1/rsi_period, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/rsi_period, adjust=False).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        rsi_min = df['RSI'].rolling(stoch_period).min()
        rsi_max = df['RSI'].rolling(stoch_period).max()
        range_rsi = rsi_max - rsi_min
        df['Stoch_K'] = np.where(range_rsi == 0, 0, ((df['RSI'] - rsi_min) / range_rsi) * 100)
        df['Stoch_D'] = df['Stoch_K'].rolling(stoch_d_smooth).mean()

        # 2. Bollinger Bands & MACD
        bb_period = cfg.get('bb_period', 20); bb_std = cfg.get('bb_std', 2.0)
        sma = close.rolling(bb_period).mean()
        std = close.rolling(bb_period).std()
        df['BB_Upper'] = sma + (std * bb_std)
        df['BB_Lower'] = sma - (std * bb_std)

        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        df['MACD'] = ema12 - ema26
        df['MACD_Sig'] = df['MACD'].ewm(span=9, adjust=False).mean()

        # 3. ATR & ADX
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df['ATR'] = tr.ewm(alpha=1/14, adjust=False).mean()

        plus_dm_raw = high.diff(); minus_dm_raw = low.diff()
        plus_dm = pd.Series(0.0, index=df.index)
        minus_dm = pd.Series(0.0, index=df.index)

        mask_plus = (plus_dm_raw > minus_dm_raw) & (plus_dm_raw > 0)
        mask_minus = (minus_dm_raw > plus_dm_raw) & (minus_dm_raw > 0)

        plus_dm[mask_plus] = plus_dm_raw[mask_plus]
        minus_dm[mask_minus] = minus_dm_raw[mask_minus]

        atr_ema_period = 14
        tr_s = tr.ewm(alpha=1/atr_ema_period, adjust=False).mean()
        plus_di = 100 * (plus_dm.ewm(alpha=1/atr_ema_period, adjust=False).mean() / tr_s)
        minus_di = 100 * (minus_dm.ewm(alpha=1/atr_ema_period, adjust=False).mean() / tr_s)

        di_diff_sum = plus_di + minus_di
        dx = np.where(di_diff_sum == 0, 0, (abs(plus_di - minus_di) / di_diff_sum) * 100)
        df['ADX'] = pd.Series(dx, index=df.index).ewm(alpha=1/atr_ema_period, adjust=False).mean()

        # 4. Ehlers Indicator (SuperSmoother + SS Trend Filter)
        ehlers_period = cfg.get('ehlers_period', 10); ehlers_mult = cfg.get('ehlers_mult', 3.0)
        if ehlers_period > 0:
            a1 = np.exp(-np.pi / ehlers_period)
            b1 = 2 * a1 * np.cos(np.pi / ehlers_period)
            c2, c3, c1 = b1, -a1 * a1, 1 - b1 + a1 * a1
            
            filt = np.zeros_like(close.values, dtype=float)
            ss_tr = np.zeros_like(df['ATR'].values, dtype=float)
            trend = np.zeros_like(close.values, dtype=int)

            if len(close.values) > 2:
                filt[0:2] = close.values[0:2]
                ss_tr[0:2] = df['ATR'].values[0:2]

            for i in range(2, len(close.values)):
                filt[i] = c1 * (close.values[i] + close.values[i-1]) / 2 + c2 * filt[i-1] + c3 * filt[i-2]
                ss_tr[i] = c1 * (df['ATR'].values[i] + df['ATR'].values[i-1]) / 2 + c2 * ss_tr[i-1] + c3 * ss_tr[i-2]

            upper = filt + ehlers_mult * ss_tr
            lower = filt - ehlers_mult * ss_tr
            st = np.zeros_like(close.values, dtype=float)
            trend[0] = 1
            st[0] = lower[0]

            for i in range(1, len(close.values)):
                prev_st = st[i-1]
                if trend[i-1] == 1:
                    if close.values[i] < prev_st:
                        trend[i] = -1; st[i] = upper[i]
                    else:
                        trend[i] = 1; st[i] = max(lower[i], prev_st)
                else:
                    if close.values[i] > prev_st:
                        trend[i] = 1; st[i] = lower[i]
                    else:
                        trend[i] = -1; st[i] = min(upper[i], prev_st)

            df['Ehlers_Trend'] = trend
            df['SS_Filter'] = filt
        else:
            df['Ehlers_Trend'] = 0
            df['SS_Filter'] = close.values
            logger.warning("Ehlers period is invalid, skipping Ehlers indicator.")

        # 5. Dynamic S/R
        sr_lookback = cfg.get('sr_lookback', 20)
        if len(df) >= sr_lookback:
            df['Swing_High'] = df['high'].rolling(window=sr_lookback).max()
            df['Swing_Low'] = df['low'].rolling(window=sr_lookback).min()
        else:
            df['Swing_High'] = np.nan
            df['Swing_Low'] = np.nan
        
        # Robust non-finite value cleaning
        df.replace([np.inf, -np.inf], np.nan, inplace=True)
        df.fillna(0, inplace=True) 
        
        return df

    @staticmethod
    def get_nearest_sr(df: pd.DataFrame, current_price: float) -> Dict[str, float]:
        if df.empty: return {}
        last = df.iloc[-1]
        sr_levels = {}
        if 'Swing_High' in last and last['Swing_High'] != 0:
            sr_levels["Dynamic_Res"] = float(last['Swing_High'])
        if 'Swing_Low' in last and last['Swing_Low'] != 0:
             sr_levels["Dynamic_Sup"] = float(last['Swing_Low'])
        return sr_levels

# --- AI Service ---

class GeminiService:
    def __init__(self, model_name: str, min_confidence: float):
        try:
            self.model = genai.GenerativeModel(model_name)
        except Exception as e:
            logger.critical(f"Failed to initialize Gemini model '{model_name}': {e}")
            sys.exit(1)
        self.request_timestamps: Deque[float] = deque()
        self.rate_limit_count = 30
        self.rate_limit_window = 60
        self.min_conf = min_confidence

    def _rate_limit(self):
        now = time.time()
        while self.request_timestamps and now - self.request_timestamps[0] > self.rate_limit_window:
            self.request_timestamps.popleft()

        if len(self.request_timestamps) >= self.rate_limit_count:
            time_since_first_in_window = now - self.request_timestamps[0]
            wait_time = self.rate_limit_window - time_since_first_in_window + 0.5
            logger.warning(f"Rate limit reached. Sleeping for {wait_time:.2f}s.")
            time.sleep(wait_time)
            now = time.time()
            while self.request_timestamps and now - self.request_timestamps[0] > self.rate_limit_window:
                self.request_timestamps.popleft()

        self.request_timestamps.append(now)

    def analyze(self, market: MarketData) -> TradeSignal:
        retries = 0
        max_retries = 3
        while retries < max_retries:
            self._rate_limit()
            try:
                prompt = self._build_prompt(market)
                generation_config = genai.types.GenerationConfig(temperature=0.3, top_p=0.9, top_k=40)
                response = self.model.generate_content(
                    prompt,
                    generation_config=generation_config,
                    safety_settings=[{"category": cat, "threshold": "BLOCK_NONE"} for cat in ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]],
                    request_options={"timeout": 30}
                )

                if not response.candidates:
                    logger.warning(f"No candidates returned from AI for {market.symbol}. Reason: {response.prompt_feedback}")
                    return self._fallback(market, "No AI Candidates")

                return self._parse_response(response.text, market)

            except google_exceptions.ResourceExhausted as e:
                wait_time = 20 * (retries + 1)
                logger.warning(f"Quota exceeded. Sleeping {wait_time}s before retry {retries+1}/{max_retries}...")
                time.sleep(wait_time); retries += 1
            except google_exceptions.GoogleAPIError as e:
                logger.error(f"Google API Error: {e}")
                wait_time = 10 * (retries + 1)
                logger.warning(f"Sleeping {wait_time}s before retry {retries+1}/{max_retries}...")
                time.sleep(wait_time); retries += 1
            except Exception as e:
                logger.error(f"Unexpected Error during AI generation: {e}")
                return self._fallback(market, "Unexpected AI Error")

        logger.error(f"Max retries reached for AI generation for {market.symbol}. Falling back.")
        return self._fallback(market, "Max AI Retries Reached")

    def _build_prompt(self, market: MarketData) -> str:
        last = market.klines.iloc[-1]
        prev = market.klines.iloc[-2] if len(market.klines) > 1 else market.klines.iloc[-1]
        pct_change = ((last['close'] - prev['close']) / prev['close']) * 100 if prev['close'] != 0 else 0

        key_levels = {**market.pivots, **market.sr_levels}
        key_levels = {k: v for k, v in key_levels.items() if v and np.isfinite(v)}

        # --- CRITICAL FIX: Robustly clean values before passing to prompt ---
        def clean_val(v: Any) -> float:
            try:
                # Attempt to convert to float first (handles Decimal, int, float)
                f_val = float(v)
                # Then check finiteness, falling back to 0.0 if inf/nan
                return f_val if np.isfinite(f_val) else 0.0
            except (TypeError, ValueError):
                # If conversion fails (e.g., it's a string or complex object)
                return 0.0
        # ---------------------------------------------------------------------

        context = {
            "symbol": market.symbol,
            "current_price": clean_val(market.price),
            "price_change_24h_pct": clean_val(pct_change),
            "rsi": clean_val(last.get('RSI')),
            "stoch_k": clean_val(last.get('Stoch_K')),
            "stoch_d": clean_val(last.get('Stoch_D')),
            "adx": clean_val(last.get('ADX')),
            "macd_val": clean_val(last.get('MACD')),
            "macd_signal": clean_val(last.get('MACD_Sig')),
            "bb_upper": clean_val(last.get('BB_Upper')),
            "bb_lower": clean_val(last.get('BB_Lower')),
            "atr": clean_val(last.get('ATR')),
            "trend_ehlers": "BULLISH" if last.get('Ehlers_Trend') == 1 else "BEARISH" if last.get('Ehlers_Trend') == -1 else "UNKNOWN",
            "ss_filter": clean_val(last.get('SS_Filter')),
            "ob_imbalance": round(market.ob_imbalance, 3),
            "key_levels": {k: round(float(v), 2) for k, v in key_levels.items() if np.isfinite(v)}
        }

        bb_pos = "INSIDE"
        if context["current_price"] > context["bb_upper"]: bb_pos = "ABOVE_UPPER"
        elif context["current_price"] < context["bb_lower"]: bb_pos = "BELOW_LOWER"
        context["bb_pos"] = bb_pos

        return f"""
        You are an expert AI Crypto Scalper for {market.symbol}. Your goal is to identify high-probability, short-term trading opportunities.
        Analyze the provided market data and generate a trading signal in JSON format.

        Market Data Snapshot:
        {json.dumps(context, indent=2)}

        Trading Strategy Guidelines:
        1.  **Trend Confirmation:** Prioritize trades aligning with the Ehlers Trend and a strong ADX (> 25).
        2.  **Overbought/Oversold:** Use RSI and Stochastics for entry timing. RSI < 30 (oversold) for buys, RSI > 70 (overbought) for sells. Stochastics crossovers can provide finer entry points.
        3.  **Key Levels:** Utilize 'key_levels'. Look for entries near support for buys and near resistance for sells, ONLY if the trend confirms.
        4.  **Bollinger Bands:** Price staying above lower band supports bullishness, below upper band supports bearishness.
        5.  **Order Book Imbalance:** Significant positive imbalance suggests buying pressure.
        6.  **ATR:** Use ATR to set realistic Stop Loss (SL) ~1.5 * ATR, Take Profit (TP) ~2.0 * ATR or higher for 1:1.5 to 1:2 R:R.
        7.  **Scalping Focus:** Aim for quick, small profits.

        Instruction:
        - Output VALID JSON ONLY, strictly adhering to the schema.
        - If no clear opportunity exists or confidence is low, output {{ "action": "HOLD", "entry": 0.0, "sl": 0.0, "tp": 0.0, "confidence": 0.0, "reason": "No clear signal" }}.
        - Only generate BUY/SELL if confidence >= {self.min_conf:.2f}.
        - Reason should be concise (max 15 words).

        JSON Schema:
        {{
            "action": "BUY" | "SELL" | "HOLD",
            "entry": float,
            "sl": float,
            "tp": float,
            "confidence": float,
            "reason": "string (max 15 words)"
        }}
        """

    def _parse_response(self, text: str, market: MarketData) -> TradeSignal:
        cleaned = re.sub(r"(?s)```json\n?|```\n?", "", text).strip()
        if not cleaned:
            logger.warning(f"AI returned empty response for {market.symbol}.")
            return self._fallback(market, "Empty AI Response")

        try:
            data = json.loads(cleaned)
            required_keys = ["action", "entry", "sl", "tp", "confidence", "reason"]
            if not all(key in data for key in required_keys):
                raise ValueError("Missing required keys in AI JSON response.")

            action = data.get('action', 'HOLD').upper()
            confidence = float(data.get('confidence', 0.0))
            
            if action in ["BUY", "SELL"] and confidence < self.min_conf:
                return self._fallback(market, f"AI Confidence ({confidence:.2f}) < Min ({self.min_conf:.2f})")

            if action not in ["BUY", "SELL"]:
                return self._fallback(market, "AI returned HOLD")
            
            entry = Decimal(str(data.get('entry'))); sl = Decimal(str(data.get('sl'))); tp = Decimal(str(data.get('tp')))
            if entry <= 0 or sl <= 0 or tp <= 0:
                 logger.warning(f"Invalid price in AI response for {market.symbol}. Falling back.")
                 return self._fallback(market, "Invalid Prices from AI")

            # Adjust SL/TP using ATR if they are illogical relative to entry
            last_atr = Decimal(str(market.klines.iloc[-1]['ATR'])) if not market.klines.empty else Decimal("0.001")
            
            if action == "BUY":
                if sl >= entry: sl = entry - (last_atr * Decimal("1.5"))
                if tp <= entry: tp = entry + (last_atr * Decimal("2.0"))
            elif action == "SELL":
                if sl <= entry: sl = entry + (last_atr * Decimal("1.5"))
                if tp >= entry: tp = entry - (last_atr * Decimal("2.0"))
            
            confidence = max(self.min_conf, min(confidence, 1.0))
            return TradeSignal(action=action, entry=entry, sl=sl, tp=tp, confidence=confidence, source="AI", reason=data.get('reason', 'AI Analysis'))

        except Exception as e:
            logger.error(f"Error parsing AI response: {e}")
            return self._fallback(market, "Response Parsing Error")

    def _fallback(self, market: MarketData, reason: str) -> TradeSignal:
        if market.klines.empty:
             return TradeSignal(action="HOLD", entry=Decimal(0), sl=Decimal(0), tp=Decimal(0), confidence=0.0, source="TECHNICAL_FALLBACK", reason=f"No klines: {reason}")

        last = market.klines.iloc[-1]
        trend = last.get('Ehlers_Trend', 0)
        rsi = last.get('RSI', 50)
        stoch_k = last.get('Stoch_K', 50)
        adx = last.get('ADX', 0)
        atr = Decimal(str(last.get('ATR', 0.001)))
        
        action, confidence, entry = "HOLD", 0.0, market.price
        sl, tp = Decimal(0), Decimal(0)
        
        STRONG_TREND_THRESHOLD = 25; RSI_OVERSOLD_THRESHOLD = 30; RSI_OVERBOUGHT_THRESHOLD = 70
        STOCH_K_LOW_THRESHOLD = 20; STOCH_K_HIGH_THRESHOLD = 80
        FALLBACK_CONFIDENCE = 0.65

        if trend == 1 and adx > STRONG_TREND_THRESHOLD and RSI_OVERSOLD_THRESHOLD < rsi < RSI_OVERBOUGHT_THRESHOLD and stoch_k < STOCH_K_HIGH_THRESHOLD:
            action = "BUY"
            confidence = FALLBACK_CONFIDENCE
            sl = max(last.get('Swing_Low', entry - atr*1.5), entry - atr*1.5)
            tp = entry + atr*2.0
            reason = f"Bullish Trend, RSI/Stoch OK, ADX>={STRONG_TREND_THRESHOLD}"
        elif trend == -1 and adx > STRONG_TREND_THRESHOLD and RSI_OVERSOLD_THRESHOLD < rsi < RSI_OVERBOUGHT_THRESHOLD and stoch_k > STOCH_K_LOW_THRESHOLD:
            action = "SELL"
            confidence = FALLBACK_CONFIDENCE
            sl = min(last.get('Swing_High', entry + atr*1.5), entry + atr*1.5)
            tp = entry - atr*2.0
            reason = f"Bearish Trend, RSI/Stoch OK, ADX>={STRONG_TREND_THRESHOLD}"
        elif trend == 0 and adx < STRONG_TREND_THRESHOLD:
             if rsi < RSI_OVERSOLD_THRESHOLD and stoch_k < STOCH_K_LOW_THRESHOLD:
                 action = "BUY"; confidence = FALLBACK_CONFIDENCE * 0.8
                 sl = entry - atr * 1.0; tp = entry + atr * 1.5
                 reason = "Ranging Market, Oversold Conditions"
             elif rsi > RSI_OVERBOUGHT_THRESHOLD and stoch_k > STOCH_K_HIGH_THRESHOLD:
                 action = "SELL"; confidence = FALLBACK_CONFIDENCE * 0.8
                 sl = entry + atr * 1.0; tp = entry - atr * 1.5
                 reason = "Ranging Market, Overbought Conditions"

        if action != "HOLD" and atr > Decimal("0.0001"):
            if sl <= 0 or (action == "BUY" and sl >= entry) or (action == "SELL" and sl <= entry):
                sl = entry - atr if action == "BUY" else entry + atr
            if tp <= 0 or (action == "BUY" and tp <= entry) or (action == "SELL" and tp >= entry):
                tp = entry + atr if action == "BUY" else entry - atr
        elif action != "HOLD":
             return TradeSignal(action="HOLD", entry=Decimal(0), sl=Decimal(0), tp=Decimal(0), confidence=0.0, source="TECHNICAL_FALLBACK", reason="ATR too low for fallback trade.")

        return TradeSignal(action=action, entry=entry, sl=sl, tp=tp, confidence=confidence, source="TECHNICAL_FALLBACK", reason=reason)


# --- Execution Service ---

class ExecutionEngine:
    def __init__(self, config: Config):
        self.cfg = config.get("paper_trading")
        self.min_conf = Decimal(str(config.get("min_confidence", 0.6)))
        self.balance = Decimal(str(self.cfg['initial_balance']))
        self.positions: Dict[str, Position] = {}
        self.history: List[Dict] = []
        self.slippage = Decimal(str(self.cfg['slippage']))
        self.fee_rate = Decimal(str(self.cfg['fee_rate']))
        self.min_qty_threshold = Decimal("0.001")
        self.min_trade_value = Decimal("10")

    def _calculate_qty(self, signal: TradeSignal, current_price: Decimal) -> Optional[Decimal]:
        risk_per_trade_pct = Decimal(str(self.cfg['risk_per_trade'])) / Decimal("100")
        risk_amount = self.balance * risk_per_trade_pct
        stop_distance = abs(signal.entry - signal.sl)
        
        if stop_distance <= Decimal("0.000001"):
            logger.warning(f"Stop distance is too small for signal {signal}. Cannot calculate quantity.")
            return None

        qty_risk = risk_amount / stop_distance
        max_leverage = Decimal("10")
        max_qty_leverage = (self.balance * max_leverage) / current_price

        qty = min(qty_risk, max_qty_leverage)
        
        qty = qty.quantize(Decimal("0.00001"), rounding=ROUND_DOWN)

        if qty < self.min_qty_threshold or (qty * current_price) < self.min_trade_value:
            logger.warning(f"Calculated quantity {qty} too small based on min quantity/value. Skipping trade.")
            return None

        return qty

    def execute(self, signal: TradeSignal, current_price: Decimal):
        if signal.action == "HOLD" or signal.confidence < self.min_conf:
            return
        if self.positions:
            logger.info(f"Skipping signal {signal.action}: Position already open.")
            return

        qty = self._calculate_qty(signal, current_price)
        if qty is None or qty == 0:
            logger.warning(f"Skipping signal {signal.action}: Could not calculate valid quantity.")
            return

        slippage_adjustment = self.slippage * signal.entry
        entry_price = signal.entry + slippage_adjustment if signal.action == "BUY" else signal.entry - slippage_adjustment
        entry_price = entry_price.quantize(Decimal("0.01"), rounding=ROUND_DOWN)

        entry_fee = entry_price * qty * self.fee_rate
        self.balance -= entry_fee

        pos_id = str(uuid.uuid4())
        pos = Position(
            id=pos_id, symbol="BTCUSDT", side=signal.action,
            entry_price=entry_price, qty=qty, stop_loss=signal.sl,
            take_profit=signal.tp, entry_time=datetime.now(timezone.utc)
        )

        self.positions[pos_id] = pos

        c = NEON_GREEN if signal.action == "BUY" else NEON_RED
        logger.info(f"{c}OPEN {signal.action} | {signal.symbol} Qty:{qty:.3f} @ {entry_price:.2f} | SL:{signal.sl:.2f} | TP:{signal.tp:.2f} | Conf:{signal.confidence:.2f} | Reason: {signal.reason}{RESET}")
        logger.info(f"Balance after entry fee: ${self.balance:.2f}")


    def update(self, current_price: Decimal):
        if not self.positions: return

        for pid, pos in list(self.positions.items()):
            pos.last_update_time = datetime.now(timezone.utc)
            closed, reason, exit_price = False, "", Decimal(0)

            if pos.side == "BUY":
                if current_price <= pos.stop_loss: exit_price, closed, reason = pos.stop_loss, True, "SL Hit"
                elif current_price >= pos.take_profit: exit_price, closed, reason = pos.take_profit, True, "TP Hit"
            else: # SELL
                if current_price >= pos.stop_loss: exit_price, closed, reason = pos.stop_loss, True, "SL Hit"
                elif current_price <= pos.take_profit: exit_price, closed, reason = pos.take_profit, True, "TP Hit"

            if closed:
                if pos.side == "BUY": pnl_gross = (exit_price - pos.entry_price) * pos.qty
                else: pnl_gross = (pos.entry_price - exit_price) * pos.qty

                exit_fee = exit_price * pos.qty * self.fee_rate
                net_pnl = pnl_gross - exit_fee
                self.balance += net_pnl

                pos.close_price, pos.pnl, pos.status = exit_price, net_pnl, "CLOSED"
                del self.positions[pid]
                self.history.append(pos.__dict__)

                c = NEON_GREEN if net_pnl >= 0 else NEON_RED
                logger.info(f"{c}CLOSE {pos.side} ({reason}) | PnL: ${net_pnl:.2f} | New Balance: ${self.balance:.2f}{RESET}")
                logger.info(f"Position Details: Entry={pos.entry_price}, Exit={exit_price}, Qty={pos.qty}, Fees=${exit_fee:.4f}")


    def close_all_positions(self):
        if not self.positions: return
        logger.warning(f"{NEON_YELLOW}Closing all {len(self.positions)} open positions...{RESET}")
        for pid, pos in list(self.positions.items()):
             logger.warning(f"Force closing {pos.side} {pos.qty} @ {pos.entry_price} (ID: {pid[:8]})")
             del self.positions[pid]
        logger.info("All positions closed.")


# --- Main Bot ---

class WhaleBot:
    def __init__(self):
        self.running = True
        signal.signal(signal.SIGINT, self._stop)
        signal.signal(signal.SIGTERM, self._stop)

        self.cfg = Config()
        min_conf_val = self.cfg.get("min_confidence", 0.60)
        
        self.data_provider = MarketDataProvider()
        self.ai_service = GeminiService(self.cfg.get("gemini_model"), min_conf_val)
        self.execution_engine = ExecutionEngine(self.cfg)

    def _stop(self, sig, frame):
        logger.info(f"Received signal {sig}. Shutting down gracefully...")
        self.running = False
        self.execution_engine.close_all_positions()

    def run(self):
        symbol = self.cfg.get("symbol")
        interval = self.cfg.get("interval")
        delay = self.cfg.get("loop_delay")

        logger.info(f"{NEON_PURPLE}=== WhaleBot Enterprise v1.0 Started ({symbol}) ===")
        logger.info(f"Initial Balance: ${self.execution_engine.balance:.2f} | Min Confidence: {self.cfg.get('min_confidence'):.2f} | Loop Delay: {delay}s")

        while self.running:
            start_time = time.monotonic()
            try:
                # 1. Fetch Market Data
                market_data = self.data_provider.fetch_all(symbol, interval)
                if not market_data:
                    logger.warning("Failed to fetch market data. Retrying after short delay.")
                    time.sleep(min(delay, 10))
                    continue

                # 2. Calculate Technical Indicators
                market_data.klines = TechnicalAnalysis.calculate(market_data.klines, self.cfg.get("indicators"))
                market_data.sr_levels = TechnicalAnalysis.get_nearest_sr(market_data.klines, float(market_data.price))

                # 3. Get AI Signal
                trade_signal = self.ai_service.analyze(market_data)

                # Logging the signal
                action_color = NEON_GREEN if trade_signal.action == "BUY" else NEON_RED if trade_signal.action == "SELL" else NEON_BLUE
                reason_short = (trade_signal.reason[:60] + '...') if len(trade_signal.reason) > 60 else trade_signal.reason
                log_message = (
                    f"Price: {market_data.price:.4f} | "
                    f"{action_color}{trade_signal.action:<4} (Conf: {trade_signal.confidence:.2f}){RESET} | "
                    f"Entry:{trade_signal.entry:.4f} SL:{trade_signal.sl:.4f} TP:{trade_signal.tp:.4f} | "
                    f"Reason: {reason_short}"
                )
                logger.info(log_message)

                # 4. Update Positions and Execute Trades
                try:
                    self.execution_engine.update(market_data.price)
                    self.execution_engine.execute(trade_signal, market_data.price)
                except Exception as e:
                    logger.error(f"Error during execution update/execute: {e}", exc_info=True)

                # 5. Calculate Sleep Time
                elapsed_time = time.monotonic() - start_time
                sleep_duration = max(0, delay - elapsed_time)
                if sleep_duration > 0:
                    time.sleep(sleep_duration)
                else:
                    logger.warning(f"Loop execution time ({elapsed_time:.2f}s) exceeded delay ({delay}s).")

            except requests.exceptions.RequestException as e:
                logger.error(f"Network error during data fetch: {e}. Retrying after 15s.")
                time.sleep(15)
            except KeyboardInterrupt:
                self._stop(signal.SIGINT, None)
                break
            except Exception as e:
                logger.error(f"An unexpected critical error occurred in the main loop: {e}", exc_info=True)
                logger.info("Attempting to recover by sleeping for 30 seconds.")
                time.sleep(30)

        logger.info(f"{NEON_PURPLE}=== WhaleBot Enterprise Stopped ===")

if __name__ == "__main__":
    try:
        bot = WhaleBot()
        bot.run()
    except Exception as e:
        logger.critical(f"Fatal error during bot initialization or runtime: {e}", exc_info=True)
        sys.exit(1)
