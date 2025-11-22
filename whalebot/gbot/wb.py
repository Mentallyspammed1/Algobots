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

def sanitize_float(value: Any) -> float:
    """
    Safely convert any value (Decimal, string, int) to a valid float.
    Fixes the 'ufunc isfinite' error by ensuring type is float before checking numpy.
    """
    try:
        if value is None:
            return 0.0
        # Explicitly convert Decimal/String to native float first
        f_val = float(value)
        if np.isfinite(f_val):
            return f_val
        return 0.0
    except (TypeError, ValueError, Exception):
        return 0.0

def retry_with_backoff(retries: int = 3, backoff_in_seconds: int = 1):
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
                    # Only log warnings for the first few retries to reduce noise
                    if x > 0:
                        logger.warning(f"Retry {x+1}/{retries} for {func.__name__}...")
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
        self.entry = Decimal(str(self.entry)) if not isinstance(self.entry, Decimal) else self.entry
        self.sl = Decimal(str(self.sl)) if not isinstance(self.sl, Decimal) else self.sl
        self.tp = Decimal(str(self.tp)) if not isinstance(self.tp, Decimal) else self.tp
        
        if self.action not in ["BUY", "SELL", "HOLD"]:
            self.action = "HOLD"

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
    close_price: Optional[Decimal] = None
    pnl: Decimal = Decimal(0)
    status: Literal["OPEN", "CLOSED"] = "OPEN"
    last_update_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict:
        return {
            "id": self.id, "symbol": self.symbol, "side": self.side,
            "entry": float(self.entry_price), "qty": float(self.qty),
            "pnl": float(self.pnl), "time": self.entry_time.isoformat()
        }

# --- Configuration Service ---

class Config:
    DEFAULTS = {
        "symbol": "BCHUSDT", "interval": "5", "loop_delay": 30,
        # Using the preview identifier for Gemini 2.0 Flash Lite
        "gemini_model": "gemini-2.5-flash-lite", 
        "min_confidence": 0.60,
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
            logger.info("Config file not found. Creating default.")
            self._save_defaults()
            return self.DEFAULTS.copy()
        try:
            with open(CONFIG_FILE, 'r') as f:
                return self._deep_update(self.DEFAULTS.copy(), json.load(f))
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
        if not os.getenv("GEMINI_API_KEY"):
            logger.critical(f"{NEON_RED}CRITICAL: GEMINI_API_KEY missing in .env{RESET}")
            sys.exit(1)
        
        try:
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        except Exception as e:
            logger.critical(f"API Key Configuration failed: {e}")
            sys.exit(1)

        self.data['min_confidence'] = max(0.1, min(self.data.get('min_confidence', 0.6), 0.99))

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        return self.data.get(key, default)

# --- Market Data Service ---

class MarketDataProvider:
    BASE_URL = "https://api.bybit.com"

    def __init__(self):
        self.session = self._create_session()
        self.executor = ThreadPoolExecutor(max_workers=4)

    def _create_session(self) -> requests.Session:
        s = requests.Session()
        retries = Retry(
            total=3, backoff_factor=0.5, 
            status_forcelist=[500, 502, 503, 504, 429],
            allowed_methods=["GET"]
        )
        s.mount('https://', HTTPAdapter(max_retries=retries))
        s.headers.update({"User-Agent": "WhaleBot/3.0", "Content-Type": "application/json"})
        return s

    @retry_with_backoff(retries=3)
    def _get_price(self, symbol: str) -> Decimal:
        resp = self.session.get(
            f"{self.BASE_URL}/v5/market/tickers",
            params={"category": "linear", "symbol": symbol}, timeout=5
        )
        resp.raise_for_status()
        price = resp.json()['result']['list'][0]['lastPrice']
        return Decimal(str(price))

    @retry_with_backoff(retries=3)
    def _get_klines(self, symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
        resp = self.session.get(
            f"{self.BASE_URL}/v5/market/kline",
            params={"category": "linear", "symbol": symbol, "interval": interval, "limit": limit},
            timeout=8
        )
        resp.raise_for_status()
        raw = resp.json().get('result', {}).get('list', [])
        if not raw: return pd.DataFrame()

        df = pd.DataFrame(raw, columns=['startTime', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
        cols = ['open', 'high', 'low', 'close', 'volume']
        df[cols] = df[cols].apply(pd.to_numeric, errors='coerce')
        df['startTime'] = pd.to_datetime(pd.to_numeric(df['startTime']), unit='ms')
        return df.sort_values('startTime').set_index('startTime')

    def _get_pivots(self, symbol: str) -> Dict[str, float]:
        try:
            df = self._get_klines(symbol, "D", limit=2)
            if len(df) < 2: return {}
            
            last = df.iloc[-2] 
            h, l, c = float(last['high']), float(last['low']), float(last['close'])
            p = (h + l + c) / 3
            r1 = p + (0.382 * (h - l))
            s1 = p - (0.382 * (h - l))
            return {"P": p, "R1": r1, "S1": s1}
        except Exception:
            return {}

    def _get_ob_imbalance(self, symbol: str) -> float:
        try:
            resp = self.session.get(
                f"{self.BASE_URL}/v5/market/orderbook", 
                params={"category": "linear", "symbol": symbol, "limit": 50}, timeout=5
            )
            data = resp.json().get('result', {})
            bids = np.array(data.get('b', []), dtype=float)
            asks = np.array(data.get('a', []), dtype=float)
            
            if bids.size == 0 or asks.size == 0: return 0.0
            
            bid_vol = np.sum(bids[:, 1])
            ask_vol = np.sum(asks[:, 1])
            total = bid_vol + ask_vol
            return (bid_vol - ask_vol) / total if total > 0 else 0.0
        except Exception:
            return 0.0

    def fetch_all(self, symbol: str, interval: str) -> Optional[MarketData]:
        futures = {
            self.executor.submit(self._get_price, symbol): 'price',
            self.executor.submit(self._get_klines, symbol, interval): 'klines',
            self.executor.submit(self._get_pivots, symbol): 'pivots',
            self.executor.submit(self._get_ob_imbalance, symbol): 'ob'
        }

        results = {}
        for future, key in futures.items():
            try:
                results[key] = future.result()
            except Exception as e:
                logger.error(f"Fetch failed for {key}: {e}")
                return None

        if results['klines'].empty or results['price'] is None:
            return None

        return MarketData(
            symbol=symbol, price=results['price'], klines=results['klines'],
            ob_imbalance=results['ob'], pivots=results['pivots'], timestamp=time.time()
        )

# --- Analysis Service ---

class TechnicalAnalysis:
    @staticmethod
    def calculate(df: pd.DataFrame, cfg: Dict) -> pd.DataFrame:
        if df.empty: return df
        
        df = df.copy()
        close = df['close']
        
        # RSI
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).ewm(alpha=1/cfg['rsi_period'], adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/cfg['rsi_period'], adjust=False).mean()
        rs = gain / loss.replace(0, 1)
        df['RSI'] = 100 - (100 / (1 + rs))

        # Stochastics
        low_min = df['low'].rolling(cfg['stoch_period']).min()
        high_max = df['high'].rolling(cfg['stoch_period']).max()
        df['Stoch_K'] = 100 * ((close - low_min) / (high_max - low_min).replace(0, 1))
        df['Stoch_D'] = df['Stoch_K'].rolling(cfg['stoch_d']).mean()

        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        df['MACD'] = ema12 - ema26
        df['MACD_Sig'] = df['MACD'].ewm(span=9, adjust=False).mean()

        # Bollinger Bands
        sma20 = close.rolling(cfg['bb_period']).mean()
        std20 = close.rolling(cfg['bb_period']).std()
        df['BB_Upper'] = sma20 + (std20 * cfg['bb_std'])
        df['BB_Lower'] = sma20 - (std20 * cfg['bb_std'])

        # ATR
        tr = np.maximum(df['high'] - df['low'], 
                        np.maximum(abs(df['high'] - close.shift()), abs(df['low'] - close.shift())))
        df['ATR'] = pd.Series(tr).ewm(alpha=1/14, adjust=False).mean()

        # Ehlers Filter
        TechnicalAnalysis._calc_ehlers(df, cfg['ehlers_period'], cfg['ehlers_mult'])

        # Dynamic S/R
        lb = cfg['sr_lookback']
        df['Swing_High'] = df['high'].rolling(window=lb).max()
        df['Swing_Low'] = df['low'].rolling(window=lb).min()
        
        df.fillna(0, inplace=True)
        return df

    @staticmethod
    def _calc_ehlers(df: pd.DataFrame, period: int, mult: float):
        alpha = np.exp(-np.pi / period)
        beta = 2 * alpha * np.cos(np.pi / period)
        c2, c3 = beta, -alpha * alpha
        c1 = 1 - c2 - c3

        prices = df['close'].values
        atrs = df['ATR'].fillna(0).values
        n = len(prices)

        filt = np.zeros(n, dtype=np.float64)
        ss_tr = np.zeros(n, dtype=np.float64)
        trend = np.zeros(n, dtype=np.int32)
        st = np.zeros(n, dtype=np.float64)

        filt[:2] = prices[:2]
        ss_tr[:2] = atrs[:2]
        st[0] = prices[0] - mult * atrs[0]

        for i in range(2, n):
            filt[i] = c1 * (prices[i] + prices[i-1]) * 0.5 + c2 * filt[i-1] + c3 * filt[i-2]
            ss_tr[i] = c1 * (atrs[i] + atrs[i-1]) * 0.5 + c2 * ss_tr[i-1] + c3 * ss_tr[i-2]
            
            upper = filt[i] + mult * ss_tr[i]
            lower = filt[i] - mult * ss_tr[i]
            
            prev_st = st[i-1]
            if trend[i-1] == 1:
                if prices[i] < prev_st:
                    trend[i] = -1; st[i] = upper
                else:
                    trend[i] = 1; st[i] = max(lower, prev_st)
            else:
                if prices[i] > prev_st:
                    trend[i] = 1; st[i] = lower
                else:
                    trend[i] = -1; st[i] = min(upper, prev_st)

        df['Ehlers_Trend'] = trend
        df['SS_Filter'] = filt

    @staticmethod
    def get_sr(df: pd.DataFrame) -> Dict[str, float]:
        if df.empty: return {}
        last = df.iloc[-1]
        return {
            "Res": float(last.get('Swing_High', 0)),
            "Sup": float(last.get('Swing_Low', 0))
        }

# --- AI Service ---

class GeminiService:
    def __init__(self, model: str, min_conf: float):
        self.model = genai.GenerativeModel(model)
        self.min_conf = min_conf
        self.window_reqs = deque(maxlen=15) 

    def _rate_limit(self):
        now = time.time()
        while self.window_reqs and now - self.window_reqs[0] > 60:
            self.window_reqs.popleft()
        
        if len(self.window_reqs) >= 15:
            sleep_t = 61 - (now - self.window_reqs[0])
            logger.warning(f"Rate Limit: Sleeping {sleep_t:.1f}s")
            time.sleep(max(0.5, sleep_t))
        
        self.window_reqs.append(time.time())

    def analyze(self, market: MarketData) -> TradeSignal:
        for attempt in range(3):
            self._rate_limit()
            try:
                prompt = self._build_prompt(market)
                resp = self.model.generate_content(
                    prompt, 
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.2, response_mime_type="application/json"
                    )
                )
                return self._parse(resp.text, market)
            except Exception as e:
                logger.warning(f"AI Attempt {attempt+1} failed: {e}")
                time.sleep(2 * (attempt + 1))
        
        return self._fallback(market, "AI_FAILURE")

    def _build_prompt(self, m: MarketData) -> str:
        row = m.klines.iloc[-1]
        prev = m.klines.iloc[-2]
        
        # The fix: convert all inputs to simple python floats first
        def f(v): return sanitize_float(v)

        # Clean pivots dictionary
        clean_levels = {}
        raw_levels = {**m.pivots, **m.sr_levels}
        for k, v in raw_levels.items():
            fv = f(v)
            if fv > 0: clean_levels[k] = round(fv, 2)

        data = {
            "price": f(m.price),
            "chg_pct": f((row['close'] - prev['close']) / prev['close'] * 100),
            "rsi": f(row['RSI']),
            "macd": f(row['MACD']),
            "atr": f(row['ATR']),
            "trend": "BULL" if row['Ehlers_Trend'] == 1 else "BEAR",
            "bb_pos": "UPPER" if row['close'] > row['BB_Upper'] else "LOWER" if row['close'] < row['BB_Lower'] else "MID",
            "ob_flow": f(m.ob_imbalance),
            "levels": clean_levels
        }

        return f"""
        Act as a Scalping Algo. Asset: {m.symbol}. Data: {json.dumps(data)}
        Strategy: Trend Following + Momentum.
        1. Check Trend (Ehlers) & Momentum (RSI, MACD).
        2. Confirm with Levels/OrderFlow.
        3. STRICT Risk Management: SL/TP based on ATR.
        
        Output JSON ONLY:
        {{
            "action": "BUY|SELL|HOLD",
            "entry": float (current_price),
            "sl": float,
            "tp": float,
            "confidence": float (0.0-1.0),
            "reason": "short string"
        }}
        """

    def _parse(self, text: str, m: MarketData) -> TradeSignal:
        try:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if not match: raise ValueError("No JSON found")
            
            data = json.loads(match.group(0))
            action = data.get("action", "HOLD").upper()
            conf = float(data.get("confidence", 0))
            
            if action in ["BUY", "SELL"] and conf >= self.min_conf:
                entry = Decimal(str(data.get("entry", m.price)))
                sl = Decimal(str(data.get("sl", 0)))
                tp = Decimal(str(data.get("tp", 0)))
                
                atr = Decimal(str(m.klines.iloc[-1]['ATR']))
                if sl <= 0 or tp <= 0:
                    sl = entry - (atr*2) if action == "BUY" else entry + (atr*2)
                    tp = entry + (atr*2) if action == "BUY" else entry - (atr*2)
                
                return TradeSignal(action, entry, sl, tp, conf, "AI", data.get("reason", "AI"))
            
            return TradeSignal("HOLD", Decimal(0), Decimal(0), Decimal(0), conf, "AI", "Low Conf/Hold")

        except Exception as e:
            return self._fallback(m, f"Parse Error: {e}")

    def _fallback(self, m: MarketData, reason: str) -> TradeSignal:
        row = m.klines.iloc[-1]
        trend = row['Ehlers_Trend']
        rsi = row['RSI']
        
        action = "HOLD"
        conf = 0.0
        
        if trend == 1 and rsi < 40:
            action = "BUY"; conf = 0.6
        elif trend == -1 and rsi > 60:
            action = "SELL"; conf = 0.6
            
        price = m.price
        atr = Decimal(str(row['ATR']))
        sl = price - (atr*2) if action == "BUY" else price + (atr*2)
        tp = price + (atr*2) if action == "BUY" else price - (atr*2)
        
        return TradeSignal(action, price, sl, tp, conf, "TECHNICAL_FALLBACK", reason)

# --- Execution Service ---

class ExecutionEngine:
    def __init__(self, cfg: Config):
        self.cfg = cfg.get("paper_trading")
        self.balance = Decimal(str(self.cfg['initial_balance']))
        self.positions: Dict[str, Position] = {}
        self.history: List[Dict] = []
        self.slippage = Decimal(str(self.cfg['slippage']))
        self.fee_rate = Decimal(str(self.cfg['fee_rate']))

    def calculate_size(self, price: Decimal, sl: Decimal) -> Decimal:
        risk_amt = self.balance * (Decimal(str(self.cfg['risk_per_trade'])) / 100)
        dist = abs(price - sl)
        if dist <= Decimal("1e-8"): return Decimal(0)
        
        qty = risk_amt / dist
        max_qty = (self.balance * 5) / price
        return min(qty, max_qty).quantize(Decimal("0.001"), rounding=ROUND_DOWN)

    def execute(self, signal: TradeSignal):
        if signal.action == "HOLD" or self.positions: return
        
        qty = self.calculate_size(signal.entry, signal.sl)
        if qty * signal.entry < 10: 
            logger.info(f"Signal Ignored: Trade value too small (${qty*signal.entry:.2f})")
            return

        entry = signal.entry * (Decimal(1) + self.slippage) if signal.action == "BUY" else signal.entry * (Decimal(1) - self.slippage)
        
        pos = Position(
            id=str(uuid.uuid4())[:8], symbol="BTCUSDT", side=signal.action,
            entry_price=entry, qty=qty, stop_loss=signal.sl, take_profit=signal.tp,
            entry_time=datetime.now(timezone.utc)
        )
        
        cost = entry * qty * self.fee_rate
        self.balance -= cost
        self.positions[pos.id] = pos
        
        color = NEON_GREEN if signal.action == "BUY" else NEON_RED
        logger.info(f"{color}OPEN {signal.action} {qty} @ {entry:.2f} | SL {signal.sl:.2f} | TP {signal.tp:.2f} | {signal.reason}{RESET}")

    def update(self, price: Decimal):
        for pid, pos in list(self.positions.items()):
            close_reason = None
            exit_price = Decimal(0)
            
            if pos.side == "BUY":
                if price <= pos.stop_loss: close_reason, exit_price = "SL", pos.stop_loss
                elif price >= pos.take_profit: close_reason, exit_price = "TP", pos.take_profit
            else:
                if price >= pos.stop_loss: close_reason, exit_price = "SL", pos.stop_loss
                elif price <= pos.take_profit: close_reason, exit_price = "TP", pos.take_profit
            
            if close_reason:
                exit_price = exit_price * (Decimal(1) - self.slippage) if pos.side == "BUY" else exit_price * (Decimal(1) + self.slippage)
                
                pnl = (exit_price - pos.entry_price) * pos.qty if pos.side == "BUY" else (pos.entry_price - exit_price) * pos.qty
                fee = exit_price * pos.qty * self.fee_rate
                net_pnl = pnl - fee
                
                self.balance += net_pnl
                pos.pnl = net_pnl
                pos.close_price = exit_price
                
                self.history.append(pos.to_dict())
                del self.positions[pid]
                
                pnl_color = NEON_GREEN if net_pnl > 0 else NEON_RED
                logger.info(f"{pnl_color}CLOSE {pos.side} ({close_reason}) | PnL ${net_pnl:.2f} | Bal ${self.balance:.2f}{RESET}")

    def shutdown(self):
        if self.positions:
            logger.warning("Closing all positions on shutdown...")
            self.positions.clear()

# --- Main ---

class WhaleBot:
    def __init__(self):
        self.running = True
        signal.signal(signal.SIGINT, self._stop)
        signal.signal(signal.SIGTERM, self._stop)
        
        self.cfg = Config()
        self.market = MarketDataProvider()
        self.ai = GeminiService(self.cfg.get("gemini_model"), self.cfg.get("min_confidence"))
        self.exec = ExecutionEngine(self.cfg)

    def _stop(self, sig, frame):
        logger.info("Stopping WhaleBot...")
        self.running = False
        self.exec.shutdown()

    def run(self):
        sym = self.cfg.get("symbol")
        interval = self.cfg.get("interval")
        delay = self.cfg.get("loop_delay")
        
        logger.info(f"{NEON_PURPLE}=== WhaleBot Enterprise v2.0 Started [{sym}] ==={RESET}")
        logger.info(f"Model: {self.cfg.get('gemini_model')} | Min Conf: {self.cfg.get('min_confidence')}")
        
        while self.running:
            t0 = time.monotonic()
            try:
                data = self.market.fetch_all(sym, interval)
                if not data:
                    time.sleep(10)
                    continue

                data.klines = TechnicalAnalysis.calculate(data.klines, self.cfg.get("indicators"))
                data.sr_levels = TechnicalAnalysis.get_sr(data.klines)
                
                signal = self.ai.analyze(data)
                
                c = NEON_GREEN if "BUY" in signal.action else NEON_RED if "SELL" in signal.action else NEON_BLUE
                logger.info(f"${data.price:.2f} | {c}{signal.action} {signal.confidence:.2f}{RESET} | {signal.reason[:60]}")
                
                self.exec.update(data.price)
                self.exec.execute(signal)

                elapsed = time.monotonic() - t0
                time.sleep(max(1, delay - elapsed))

            except Exception as e:
                logger.error(f"Loop Error: {e}")
                time.sleep(10)

if __name__ == "__main__":
    WhaleBot().run()
