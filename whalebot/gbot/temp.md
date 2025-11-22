#!/usr/bin/env python3
import asyncio
import aiohttp
import json
import logging
import re
import time
import numpy as np
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.layout import Layout
from rich import box
from rich.style import Style
from rich.text import Text
import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# --- Configuration ---
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gemini_api_key: str = Field(..., alias="GEMINI_API_KEY")
    bybit_base_url: str = "https://api.bybit.com"
    gemini_model_name: str = "gemini-2.5-flash-lite"

    symbols: List[str] = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", 
        "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "SUIUSDT"
    ]
    interval: str = "15" 
    category: str = "linear"
    kline_limit: int = 300 # Increased for EMA200 stability
    min_confidence: int = 70
    refresh_rate: int = 30
    
    # Technical Settings
    atr_period: int = 14
    rsi_period: int = 14
    ehlers_settings: tuple = (10, 3.0) 
    
    logging_level: str = "WARNING"

settings = Settings()

# Setup Logging
logging.basicConfig(
    level=getattr(logging, settings.logging_level),
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("whalebot_debug.log", mode='w')]
)
logger = logging.getLogger("WhaleBot")

console = Console()

# --- Data Models ---

class IndicatorData(BaseModel):
    trend_ema_20: float = 0.0
    trend_ema_200: float = 0.0
    trend_supertrend: str = "NEUTRAL"
    trend_ichimoku: str = "NEUTRAL"
    
    mom_rsi: float = 50.0
    mom_stoch_k: float = 50.0
    mom_macd_hist: float = 0.0
    
    vol_bb_position: str = "INSIDE"
    vol_atr: float = 0.0
    
    flow_ob_imbalance: float = 0.0
    flow_vwap: float = 0.0
    flow_volume_delta: float = 0.0

class SignalAnalysis(BaseModel):
    trend: str = Field(..., description="BULLISH, BEARISH, or RANGING")
    signal: str = Field(..., description="BUY, SELL, or HOLD")
    confidence: int = Field(..., ge=0, le=100)
    explanation: str = Field(..., description="Short reasoning")
    entry_zone: Optional[str] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    @field_validator('signal', mode='before')
    def normalize_signal(cls, v):
        return v.upper().strip()

class MarketSnapshot(BaseModel):
    symbol: str
    price: float = 0.0
    timestamp: datetime
    indicators: IndicatorData
    analysis: Optional[SignalAnalysis] = None
    error: Optional[str] = None
    last_updated: float = 0.0
    latency_ms: float = 0.0

# --- API Client ---

class BybitPublicClient:
    def __init__(self):
        self.base_url = settings.bybit_base_url
        self.session: Optional[aiohttp.ClientSession] = None
        self.timeout = aiohttp.ClientTimeout(total=10)

    async def start(self):
        if not self.session:
            # Disable SSL verify for slight speed bump if safe, else keep default
            connector = aiohttp.TCPConnector(limit=20, ssl=False)
            self.session = aiohttp.ClientSession(
                headers={"User-Agent": "WhaleBot/2.1"}, 
                timeout=self.timeout,
                connector=connector
            )

    async def close(self):
        if self.session:
            await self.session.close()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=4), retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)))
    async def fetch_data(self, symbol: str) -> tuple[pd.DataFrame, Dict, Dict, float]:
        t0 = time.perf_counter()
        
        url_kline = f"{self.base_url}/v5/market/kline"
        url_ob = f"{self.base_url}/v5/market/orderbook"
        url_tick = f"{self.base_url}/v5/market/tickers"
        
        params_base = {"category": settings.category, "symbol": symbol}
        params_kline = {**params_base, "interval": settings.interval, "limit": settings.kline_limit}
        params_ob = {**params_base, "limit": 50}

        async with asyncio.TaskGroup() as tg:
            task_k = tg.create_task(self.session.get(url_kline, params=params_kline))
            task_o = tg.create_task(self.session.get(url_ob, params=params_ob))
            task_t = tg.create_task(self.session.get(url_tick, params=params_base))

        resp_k, resp_o, resp_t = task_k.result(), task_o.result(), task_t.result()
        
        data_k = await resp_k.json()
        data_o = await resp_o.json()
        data_t = await resp_t.json()
        
        latency = (time.perf_counter() - t0) * 1000
        
        if data_k.get("retCode") != 0: return pd.DataFrame(), {}, {}, latency
        
        # Parse Kline
        df = pd.DataFrame(data_k["result"]["list"], columns=["startTime", "open", "high", "low", "close", "volume", "turnover"])
        df = df.astype(float)
        df["startTime"] = pd.to_datetime(df["startTime"], unit="ms")
        df = df.sort_values("startTime").reset_index(drop=True)

        ob = data_o.get("result", {}) if data_o.get("retCode") == 0 else {}
        tick = data_t["result"]["list"][0] if data_t.get("retCode") == 0 and data_t.get("result", {}).get("list") else {}

        return df, ob, tick, latency

# --- Technical Analysis ---

class TechnicalAnalyzer:
    @staticmethod
    def calculate(df: pd.DataFrame, orderbook: Dict) -> IndicatorData:
        if df.empty or len(df) < 200: 
            # Fail if we don't have enough data for EMA200
            return IndicatorData()
        
        # Helper to safely get scalar float
        def safe_float(val):
            return float(val) if np.isfinite(val) else 0.0

        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        volume = df['volume'].values
        
        ind = IndicatorData()
        
        # -- Helper: EMA --
        def get_ema(values, span):
            return pd.Series(values).ewm(span=span, adjust=False).mean().values

        # 1. Trend
        ind.trend_ema_20 = safe_float(get_ema(close, 20)[-1])
        ind.trend_ema_200 = safe_float(get_ema(close, 200)[-1])

        # ATR
        tr1 = high - low
        tr2 = np.abs(high - np.roll(close, 1))
        tr3 = np.abs(low - np.roll(close, 1))
        tr = np.maximum.reduce([tr1, tr2, tr3])
        atr_series = pd.Series(tr).ewm(alpha=1/settings.atr_period, adjust=False).mean()
        atr = atr_series.values
        ind.vol_atr = safe_float(atr[-1])

        # SuperTrend (Snapshot)
        _, st_mult = settings.ehlers_settings
        hl2 = (high + low) / 2
        upper_band = hl2[-1] + (st_mult * atr[-1])
        lower_band = hl2[-1] - (st_mult * atr[-1])
        curr_close = close[-1]
        
        if curr_close > ind.trend_ema_20 and curr_close > lower_band: 
            ind.trend_supertrend = "BULLISH"
        elif curr_close < ind.trend_ema_20 and curr_close < upper_band:
            ind.trend_supertrend = "BEARISH"
        else:
            ind.trend_supertrend = "NEUTRAL"

        # Ichimoku
        def get_span(h, l, p): return (pd.Series(h).rolling(p).max() + pd.Series(l).rolling(p).min()) / 2
        tenkan = get_span(high, low, 9)
        kijun = get_span(high, low, 26)
        span_a = ((tenkan + kijun) / 2).shift(26)
        span_b = get_span(high, low, 52).shift(26)
        
        # Check if we have valid cloud data
        if not np.isnan(span_a.iloc[-1]):
            cloud_top = max(span_a.iloc[-1], span_b.iloc[-1])
            cloud_bottom = min(span_a.iloc[-1], span_b.iloc[-1])
            if curr_close > cloud_top: ind.trend_ichimoku = "ABOVE CLOUD"
            elif curr_close < cloud_bottom: ind.trend_ichimoku = "BELOW CLOUD"
            else: ind.trend_ichimoku = "IN CLOUD"

        # 2. Momentum
        # RSI
        delta = np.diff(close)
        up, down = delta.copy(), delta.copy()
        up[up < 0] = 0
        down[down > 0] = 0
        roll_up = pd.Series(up).ewm(alpha=1/14, adjust=False).mean()
        roll_down = pd.Series(down).abs().ewm(alpha=1/14, adjust=False).mean()
        
        # Avoid div by zero
        rs = roll_up / roll_down.replace(0, 1)
        rsi = 100.0 - (100.0 / (1.0 + rs))
        ind.mom_rsi = safe_float(rsi.iloc[-1])

        # Stoch RSI
        min_r = rsi.rolling(14).min()
        max_r = rsi.rolling(14).max()
        denom = (max_r - min_r).replace(0, 1)
        stoch_k = ((rsi - min_r) / denom) * 100
        ind.mom_stoch_k = safe_float(stoch_k.rolling(3).mean().iloc[-1])

        # MACD
        ema12 = get_ema(close, 12)
        ema26 = get_ema(close, 26)
        macd = ema12 - ema26
        signal = get_ema(macd, 9)
        ind.mom_macd_hist = safe_float(macd[-1] - signal[-1])

        # 3. Volatility
        sma20 = pd.Series(close).rolling(20).mean().values
        std20 = pd.Series(close).rolling(20).std().values
        bb_up = sma20[-1] + (std20[-1] * 2)
        bb_low = sma20[-1] - (std20[-1] * 2)
        
        if curr_close > bb_up: ind.vol_bb_position = "UPPER BREAK"
        elif curr_close < bb_low: ind.vol_bb_position = "LOWER BREAK"
        else: ind.vol_bb_position = "INSIDE"

        # 4. Flow
        cum_vol = np.cumsum(volume)
        cum_pv = np.cumsum(volume * (high + low + close) / 3)
        ind.flow_vwap = safe_float((cum_pv / cum_vol)[-1])

        if orderbook:
            bids = np.array(orderbook.get('b', []), dtype=float)
            asks = np.array(orderbook.get('a', []), dtype=float)
            if len(bids) > 0 and len(asks) > 0:
                bid_vol = np.sum(bids[:, 1])
                ask_vol = np.sum(asks[:, 1])
                total = bid_vol + ask_vol
                ind.flow_ob_imbalance = safe_float((bid_vol - ask_vol) / total) if total > 0 else 0.0

        opens = df['open'].values
        dirs = np.where(close >= opens, 1, -1)
        ind.flow_volume_delta = safe_float(np.sum(volume[-5:] * dirs[-5:]))

        return ind

# --- AI Analyst ---

class GeminiAnalyzer:
    def __init__(self):
        genai.configure(api_key=settings.gemini_api_key)
        self.model = genai.GenerativeModel(settings.gemini_model_name)

    async def analyze(self, symbol: str, price: float, data: IndicatorData) -> SignalAnalysis:
        prompt = f"""
        Role: Senior Crypto Analyst. Asset: {symbol} | Price: ${price:.4f}
        
        TECHNICALS:
        - Trend: EMA20 ${data.trend_ema_20:.2f} | EMA200 ${data.trend_ema_200:.2f} | SuperTrend {data.trend_supertrend}
        - Momentum: RSI {data.mom_rsi:.1f} | StochK {data.mom_stoch_k:.1f} | MACD {data.mom_macd_hist:.4f}
        - Volatility: ATR {data.vol_atr:.2f} | BB {data.vol_bb_position}
        - Flow: OB Imbalance {data.flow_ob_imbalance:.2f} | VWAP ${data.flow_vwap:.2f}

        INSTRUCTIONS:
        1. Identify trend using EMA structure + SuperTrend.
        2. Check momentum (RSI/Stoch) for entry timing.
        3. Confirm with Flow (Imbalance/VWAP).
        4. Be conservative. Signal HOLD if mixed.
        
        Output strict JSON:
        {{
            "trend": "BULLISH/BEARISH/RANGING",
            "signal": "BUY/SELL/HOLD",
            "confidence": 0-100,
            "explanation": "Max 10 words.",
            "entry_zone": "price",
            "stop_loss": float,
            "take_profit": float
        }}
        """
        
        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, lambda: self.model.generate_content(prompt))
            text = response.text.strip()
            
            # Clean markdown
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                json_str = match.group(0)
                return SignalAnalysis.model_validate_json(json_str)
            raise ValueError("No JSON found")
            
        except Exception as e:
            logger.error(f"AI Error {symbol}: {e}")
            return SignalAnalysis(trend="ERROR", signal="HOLD", confidence=0, explanation="AI Timeout")

# --- Main Application ---

class WhaleBot:
    def __init__(self):
        self.client = BybitPublicClient()
        self.analyzer = GeminiAnalyzer()
        self.snapshots: Dict[str, MarketSnapshot] = {
            s: MarketSnapshot(symbol=s, timestamp=datetime.now(), indicators=IndicatorData()) 
            for s in settings.symbols
        }

    def generate_table(self) -> Table:
        table = Table(
            show_header=True, header_style="bold white", box=box.ROUNDED, 
            title=f"[bold cyan]WhaleBot AI[/bold cyan] | {settings.interval}m Interval",
            expand=True
        )
        table.add_column("Symbol", style="cyan", width=10)
        table.add_column("Price", justify="right", width=10)
        table.add_column("Signal", justify="center", width=8)
        table.add_column("Conf", justify="right", width=6)
        table.add_column("Trend", justify="center", width=10)
        # no_wrap=True and overflow="ellipsis" prevent layout breaking
        table.add_column("Reasoning", style="dim", no_wrap=True, overflow="ellipsis", width=25)
        table.add_column("TP / SL", justify="right", style="magenta", width=18)
        table.add_column("Updated", justify="right", style="green", width=8)

        sorted_snaps = sorted(self.snapshots.values(), key=lambda x: x.analysis.confidence if x.analysis else 0, reverse=True)

        for snap in sorted_snaps:
            if snap.price == 0:
                table.add_row(snap.symbol, "---", "...", "", "", "Initializing...", "", "")
                continue

            if snap.error:
                table.add_row(snap.symbol, f"${snap.price:,.2f}", "[red]ERR[/red]", "", "", snap.error, "", "")
                continue
                
            an = snap.analysis
            if not an: continue

            # Logic Enforcement
            final_signal = an.signal
            final_conf = an.confidence
            
            # Override low confidence
            if final_signal != "HOLD" and final_conf < settings.min_confidence:
                final_signal = "HOLD"
                an.explanation = f"Low conf ({final_conf}%) -> HOLD"

            sig_style = "bold green" if final_signal == "BUY" else "bold red" if final_signal == "SELL" else "yellow"
            conf_color = "green" if final_conf >= settings.min_confidence else "white"
            trend_sym = "↗" if an.trend == "BULLISH" else "↘" if an.trend == "BEARISH" else "→"

            plan = "-"
            if final_signal != "HOLD" and an.take_profit and an.stop_loss:
                risk = abs(snap.price - an.stop_loss)
                reward = abs(an.take_profit - snap.price)
                rr = reward / risk if risk > 0 else 0
                plan = f"TP:{an.take_profit}\nSL:{an.stop_loss} ({rr:.1f}R)"

            age = time.time() - snap.last_updated
            
            table.add_row(
                snap.symbol,
                f"${snap.price:,.2f}",
                f"[{sig_style}]{final_signal}[/{sig_style}]",
                f"[{conf_color}]{final_conf}%[/{conf_color}]",
                f"{trend_sym} {an.trend[:4]}",
                an.explanation,
                plan,
                f"{age:.0f}s"
            )
        return table

    async def process_symbol(self, symbol: str):
        try:
            # Skip if updated recently (debounce)
            if time.time() - self.snapshots[symbol].last_updated < settings.refresh_rate - 5:
                return

            df, ob, ticker, latency = await self.client.fetch_data(symbol)
            
            if df.empty or not ticker:
                self.snapshots[symbol].error = "No Data"
                return

            current_price = float(ticker.get("lastPrice", 0))
            
            # Calc
            try:
                indicators = TechnicalAnalyzer.calculate(df, ob)
            except Exception as e:
                logger.exception(f"Calc failed {symbol}")
                self.snapshots[symbol].error = "Calc Err"
                self.snapshots[symbol].price = current_price
                return

            # AI
            analysis = await self.analyzer.analyze(symbol, current_price, indicators)
            
            self.snapshots[symbol] = MarketSnapshot(
                symbol=symbol,
                price=current_price,
                timestamp=datetime.now(),
                indicators=indicators,
                analysis=analysis,
                last_updated=time.time(),
                latency_ms=latency
            )
            
        except Exception as e:
            logger.error(f"Process {symbol}: {e}")
            self.snapshots[symbol].error = "Net Err"

    async def run(self):
        await self.client.start()
        console.clear()
        
        layout = Layout()
        layout.split_column(Layout(name="header", size=3), Layout(name="body"))

        try:
            with Live(layout, refresh_per_second=4, screen=True) as live:
                next_refresh = time.time()
                
                while True:
                    now = time.time()
                    
                    # Update Data if time
                    if now >= next_refresh:
                        tasks = [self.process_symbol(s) for s in settings.symbols]
                        # Process in background, update UI as they finish
                        for future in asyncio.as_completed(tasks):
                            await future
                            layout["body"].update(self.generate_table())
                        
                        next_refresh = time.time() + settings.refresh_rate
                    
                    # Header Timer
                    wait = max(0, next_refresh - time.time())
                    latencies = [s.latency_ms for s in self.snapshots.values() if s.latency_ms > 0]
                    avg_lat = sum(latencies) / len(latencies) if latencies else 0
                    
                    header = Panel(
                        f"STATUS: [bold green]RUNNING[/bold green] | API Latency: {avg_lat:.0f}ms | Next Scan: [bold yellow]{wait:.0f}s[/bold yellow]",
                        style="white on blue"
                    )
                    layout["header"].update(header)
                    layout["body"].update(self.generate_table())
                    
                    await asyncio.sleep(0.5) # UI Loop Tick

        except KeyboardInterrupt:
            console.print("\n[yellow]Shutting down...[/yellow]")
        finally:
            await self.client.close()

if __name__ == "__main__":
    if not settings.gemini_api_key:
        print("Error: GEMINI_API_KEY not found.")
        exit(1)
    asyncio.run(WhaleBot().run())
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
    """Safely convert any value to a valid float, returning 0.0 for NaN/Inf."""
    try:
        f_val = float(value)
        if np.isfinite(f_val):
            return f_val
        return 0.0
    except (TypeError, ValueError):
        return 0.0

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
        # Ensure strict Decimal conversion
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

T = TypeVar('T')

class Config:
    DEFAULTS = {
        "symbol": "BTCUSDT", "interval": "15", "loop_delay": 30,
        "gemini_model": "gemini-2.5-flash-lite", "min_confidence": 0.65,
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

        # Normalize Values
        self.data['min_confidence'] = max(0.1, min(self.data.get('min_confidence', 0.6), 0.99))
        self.data['loop_delay'] = max(5, self.data.get('loop_delay', 30))

    def get(self, key: str, default: Optional[T] = None) -> T:
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
        # Convert numeric columns efficiently
        cols = ['open', 'high', 'low', 'close', 'volume']
        df[cols] = df[cols].apply(pd.to_numeric, errors='coerce')
        
        df['startTime'] = pd.to_datetime(pd.to_numeric(df['startTime']), unit='ms')
        return df.sort_values('startTime').set_index('startTime')

    def _get_pivots(self, symbol: str) -> Dict[str, float]:
        # Uses independent session call to avoid blocking logic
        try:
            df = self._get_klines(symbol, "D", limit=2)
            if len(df) < 2: return {}
            
            last = df.iloc[-2] # Yesterday's completed candle
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
        # Parallel fetch for speed
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

        # ATR & ADX
        tr = np.maximum(df['high'] - df['low'], 
                        np.maximum(abs(df['high'] - close.shift()), abs(df['low'] - close.shift())))
        df['ATR'] = pd.Series(tr).ewm(alpha=1/14, adjust=False).mean()

        # Ehlers Filter (Optimized Loop)
        TechnicalAnalysis._calc_ehlers(df, cfg['ehlers_period'], cfg['ehlers_mult'])

        # Dynamic S/R
        lb = cfg['sr_lookback']
        df['Swing_High'] = df['high'].rolling(window=lb).max()
        df['Swing_Low'] = df['low'].rolling(window=lb).min()
        
        # Clean
        df.fillna(0, inplace=True)
        return df

    @staticmethod
    def _calc_ehlers(df: pd.DataFrame, period: int, mult: float):
        # Pre-calculate constants
        alpha = np.exp(-np.pi / period)
        beta = 2 * alpha * np.cos(np.pi / period)
        c2, c3 = beta, -alpha * alpha
        c1 = 1 - c2 - c3

        prices = df['close'].values
        atrs = df['ATR'].fillna(0).values
        n = len(prices)

        # Pre-allocate arrays (float64)
        filt = np.zeros(n, dtype=np.float64)
        ss_tr = np.zeros(n, dtype=np.float64)
        trend = np.zeros(n, dtype=np.int32)
        st = np.zeros(n, dtype=np.float64)

        # Initialize first few values
        filt[:2] = prices[:2]
        ss_tr[:2] = atrs[:2]
        st[0] = prices[0] - mult * atrs[0]

        # Numba would be faster, but plain numpy loop is sufficient for <1000 rows
        for i in range(2, n):
            filt[i] = c1 * (prices[i] + prices[i-1]) * 0.5 + c2 * filt[i-1] + c3 * filt[i-2]
            ss_tr[i] = c1 * (atrs[i] + atrs[i-1]) * 0.5 + c2 * ss_tr[i-1] + c3 * ss_tr[i-2]
            
            upper = filt[i] + mult * ss_tr[i]
            lower = filt[i] - mult * ss_tr[i]
            
            prev_st = st[i-1]
            if trend[i-1] == 1:
                if prices[i] < prev_st:
                    trend[i] = -1
                    st[i] = upper
                else:
                    trend[i] = 1
                    st[i] = max(lower, prev_st)
            else:
                if prices[i] > prev_st:
                    trend[i] = 1
                    st[i] = lower
                else:
                    trend[i] = -1
                    st[i] = min(upper, prev_st)

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
        self.last_req = 0
        self.window_reqs = deque(maxlen=15) # 15 reqs per 60s bucket

    def _rate_limit(self):
        now = time.time()
        # Simple token bucket logic
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
        
        def f(v): return sanitize_float(v)

        data = {
            "price": f(m.price),
            "chg_pct": f((row['close'] - prev['close']) / prev['close'] * 100),
            "rsi": f(row['RSI']),
            "macd": f(row['MACD']),
            "atr": f(row['ATR']),
            "trend": "BULL" if row['Ehlers_Trend'] == 1 else "BEAR",
            "bb_pos": "UPPER" if row['close'] > row['BB_Upper'] else "LOWER" if row['close'] < row['BB_Lower'] else "MID",
            "ob_flow": f(m.ob_imbalance),
            "levels": {k: round(v, 2) for k,v in {**m.pivots, **m.sr_levels}.items() if v > 0}
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
            # robust regex to find the json block even if AI chats
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if not match: raise ValueError("No JSON found")
            
            data = json.loads(match.group(0))
            action = data.get("action", "HOLD").upper()
            conf = float(data.get("confidence", 0))
            
            if action in ["BUY", "SELL"] and conf >= self.min_conf:
                entry = Decimal(str(data.get("entry", m.price)))
                sl = Decimal(str(data.get("sl", 0)))
                tp = Decimal(str(data.get("tp", 0)))
                
                # Basic sanity check on AI output prices
                atr = Decimal(str(m.klines.iloc[-1]['ATR']))
                if sl <= 0 or tp <= 0:
                    # Auto-correct bad SL/TP
                    sl = entry - (atr*2) if action == "BUY" else entry + (atr*2)
                    tp = entry + (atr*2) if action == "BUY" else entry - (atr*2)
                
                return TradeSignal(action, entry, sl, tp, conf, "AI", data.get("reason", "AI"))
            
            return TradeSignal("HOLD", Decimal(0), Decimal(0), Decimal(0), conf, "AI", "Low Conf/Hold")

        except Exception as e:
            return self._fallback(m, f"Parse Error: {e}")

    def _fallback(self, m: MarketData, reason: str) -> TradeSignal:
        # Simple logical fallback
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
        # Cap leverage at 5x for safety in paper trading
        max_qty = (self.balance * 5) / price
        return min(qty, max_qty).quantize(Decimal("0.001"), rounding=ROUND_DOWN)

    def execute(self, signal: TradeSignal):
        if signal.action == "HOLD" or self.positions: return
        
        qty = self.calculate_size(signal.entry, signal.sl)
        if qty * signal.entry < 10: # Min trade value $10
            logger.info(f"Signal Ignored: Trade value too small (${qty*signal.entry:.2f})")
            return

        # Apply Slippage
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
                # Apply Slippage to Exit
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
        
        logger.info(f"{NEON_PURPLE}=== WhaleBot Optimized Started [{sym}] ==={RESET}")
        
        while self.running:
            t0 = time.monotonic()
            try:
                data = self.market.fetch_all(sym, interval)
                if not data:
                    time.sleep(10)
                    continue

                # Technicals
                data.klines = TechnicalAnalysis.calculate(data.klines, self.cfg.get("indicators"))
                data.sr_levels = TechnicalAnalysis.get_sr(data.klines)
                
                # AI & Logic
                signal = self.ai.analyze(data)
                
                # Logging
                c = NEON_GREEN if "BUY" in signal.action else NEON_RED if "SELL" in signal.action else NEON_BLUE
                logger.info(f"${data.price:.2f} | {c}{signal.action} {signal.confidence:.2f}{RESET} | {signal.reason[:60]}")
                
                # Execute
                self.exec.update(data.price)
                self.exec.execute(signal)

                # Sleep
                elapsed = time.monotonic() - t0
                time.sleep(max(1, delay - elapsed))

            except Exception as e:
                logger.error(f"Loop Error: {e}")
                time.sleep(10)

if __name__ == "__main__":
    WhaleBot().run()
#!/usr/bin/env python3
import asyncio
import aiohttp
import json
import logging
import math
import os
import time
import re
import numpy as np
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any, Optional, Literal
from uuid import uuid4
from pathlib import Path

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.layout import Layout
from rich.text import Text
from rich import box

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# --- 1. Configuration ---

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gemini_api_key: str = Field(..., alias="GEMINI_API_KEY")
    bybit_base_url: str = "https://api.bybit.com"
    gemini_model_name: str = "gemini-2.5-flash-lite"

    # Reduced symbol list to fit within standard free tier (15 RPM)
    # 6 symbols * 10s delay = 60s loop (Safe)
    symbols: List[str] = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT"
    ]
    interval: str = "5" 
    category: str = "linear"
    kline_limit: int = 200
    
    # Trading Settings
    initial_balance: float = 10000.0
    risk_per_trade: float = 0.02    
    leverage: int = 5
    min_confidence: int = 70
    refresh_rate: int = 60          
    trading_fee: float = 0.00055    
    state_file: str = "whalebot_state.json"
    
    # API Rate Limiting (Seconds to wait between AI calls)
    ai_cooldown: float = 5.0
    
    # Technical Settings
    atr_period: int = 14
    ehlers_settings: tuple = (10, 3.0)
    
    logging_level: str = "INFO"

settings = Settings()

# Setup Logging
logging.basicConfig(
    level=getattr(logging, settings.logging_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("whalebot.log", mode='a', encoding='utf-8')]
)
logger = logging.getLogger("WhaleBot")
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("google.ai").setLevel(logging.WARNING)

console = Console()

# --- 2. Helpers ---

def sanitize_float(value: float) -> float:
    if math.isnan(value) or math.isinf(value):
        return 0.0
    return value

# --- 3. Data Models ---

class IndicatorData(BaseModel):
    trend_ema_20: float = 0.0
    trend_ema_200: float = 0.0
    trend_supertrend: str = "NEUTRAL"
    mom_rsi: float = 50.0
    mom_stoch_k: float = 50.0
    mom_macd_hist: float = 0.0
    vol_bb_position: str = "INSIDE"
    vol_atr: float = 0.0
    flow_ob_imbalance: float = 0.0
    flow_vwap: float = 0.0

class SignalAnalysis(BaseModel):
    trend: str = Field(..., description="BULLISH, BEARISH, or RANGING")
    signal: str = Field(..., description="BUY, SELL, or HOLD")
    confidence: int = Field(..., ge=0, le=100)
    explanation: str = Field(..., description="Short reasoning")
    stop_loss: float
    take_profit: float
    source: str = "AI" # AI or Fallback

    @field_validator('signal', mode='before')
    def normalize_signal(cls, v):
        return v.upper().strip()

class Position(BaseModel):
    id: str
    symbol: str
    side: Literal["LONG", "SHORT"]
    entry_price: float
    size_usd: float
    qty: float
    stop_loss: float
    take_profit: float
    entry_time: datetime
    pnl: float = 0.0

    def to_dict(self):
        d = self.model_dump()
        d['entry_time'] = self.entry_time.isoformat()
        return d

class MarketSnapshot(BaseModel):
    symbol: str
    price: float = 0.0
    timestamp: datetime
    indicators: IndicatorData
    analysis: Optional[SignalAnalysis] = None
    error: Optional[str] = None
    last_updated: float = 0.0
    latency_ms: float = 0.0

# --- 4. State Persistence ---

class StateManager:
    @staticmethod
    def save(balance: float, positions: Dict[str, Position], history: List[Dict]):
        try:
            data = {
                "balance": balance,
                "positions": {k: v.to_dict() for k, v in positions.items()},
                "history": history
            }
            with open(settings.state_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    @staticmethod
    def load() -> tuple[float, Dict[str, Position], List[Dict]]:
        if not os.path.exists(settings.state_file):
            return settings.initial_balance, {}, []
        
        try:
            with open(settings.state_file, "r") as f:
                data = json.load(f)
            
            balance = data.get("balance", settings.initial_balance)
            history = data.get("history", [])
            
            positions = {}
            for k, v in data.get("positions", {}).items():
                v['entry_time'] = datetime.fromisoformat(v['entry_time'])
                positions[k] = Position(**v)
                
            return balance, positions, history
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            return settings.initial_balance, {}, []

# --- 5. Trading Engine ---

class PaperTrader:
    def __init__(self):
        self.balance, self.positions, self.history = StateManager.load()
        self.lock = asyncio.Lock()

    def _save(self):
        StateManager.save(self.balance, self.positions, self.history)

    def calculate_position_size(self, price: float, sl: float) -> float:
        risk_amount = self.balance * settings.risk_per_trade
        if price == 0: return 0.0
        dist_percentage = abs(price - sl) / price
        if dist_percentage < 0.001: dist_percentage = 0.001
        pos_size_usd = risk_amount / dist_percentage
        max_size = self.balance * settings.leverage
        return min(pos_size_usd, max_size)

    async def execute_signal(self, symbol: str, price: float, analysis: SignalAnalysis):
        async with self.lock:
            if symbol in self.positions:
                pos = self.positions[symbol]
                close_reason = None
                
                if pos.side == "LONG":
                    if price <= pos.stop_loss: close_reason = "SL Hit"
                    elif price >= pos.take_profit: close_reason = "TP Hit"
                    elif analysis.signal == "SELL": close_reason = "Signal Flip"
                else: # SHORT
                    if price >= pos.stop_loss: close_reason = "SL Hit"
                    elif price <= pos.take_profit: close_reason = "TP Hit"
                    elif analysis.signal == "BUY": close_reason = "Signal Flip"

                if close_reason:
                    self._close_position(symbol, price, close_reason)

            # Only open if high confidence and no existing position
            if symbol not in self.positions and analysis.confidence >= settings.min_confidence:
                if analysis.signal == "BUY":
                    self._open_position(symbol, "LONG", price, analysis.stop_loss, analysis.take_profit)
                elif analysis.signal == "SELL":
                    self._open_position(symbol, "SHORT", price, analysis.stop_loss, analysis.take_profit)

    def update_pnl_display(self, symbol: str, current_price: float):
        if symbol in self.positions:
            pos = self.positions[symbol]
            if pos.side == "LONG":
                pos.pnl = (current_price - pos.entry_price) * pos.qty
            else:
                pos.pnl = (pos.entry_price - current_price) * pos.qty

    def _open_position(self, symbol: str, side: str, price: float, sl: float, tp: float):
        size_usd = self.calculate_position_size(price, sl)
        if size_usd < 5: return

        qty = size_usd / price
        fee = size_usd * settings.trading_fee
        self.balance -= fee

        self.positions[symbol] = Position(
            id=str(uuid4())[:8], symbol=symbol, side=side, entry_price=price,
            size_usd=size_usd, qty=qty, stop_loss=sl, take_profit=tp,
            entry_time=datetime.now()
        )
        logger.info(f"OPEN {side} {symbol} @ {price}")
        self._save()

    def _close_position(self, symbol: str, price: float, reason: str):
        pos = self.positions.pop(symbol)
        pnl_gross = (price - pos.entry_price) * pos.qty if pos.side == "LONG" else (pos.entry_price - price) * pos.qty
        fee = (price * pos.qty) * settings.trading_fee
        net_pnl = pnl_gross - fee
        
        self.balance += net_pnl
        
        self.history.insert(0, {
            "time": datetime.now().strftime("%H:%M:%S"), "symbol": symbol,
            "side": pos.side, "pnl": net_pnl, "reason": reason
        })
        self.history = self.history[:10]
        logger.info(f"CLOSE {symbol} | PnL: ${net_pnl:.2f} ({reason})")
        self._save()

# --- 6. API Client ---

class BybitPublicClient:
    def __init__(self):
        self.base_url = settings.bybit_base_url
        self.session: Optional[aiohttp.ClientSession] = None

    async def start(self):
        if not self.session:
            self.session = aiohttp.ClientSession(headers={"User-Agent": "WhaleBot/3.0"})

    async def close(self):
        if self.session:
            await self.session.close()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def fetch_data(self, symbol: str) -> tuple[pd.DataFrame, Dict, Dict, float]:
        t0 = time.perf_counter()
        url_kline = f"{self.base_url}/v5/market/kline"
        url_ob = f"{self.base_url}/v5/market/orderbook"
        url_tick = f"{self.base_url}/v5/market/tickers"
        
        params_base = {"category": settings.category, "symbol": symbol}
        params_kline = {**params_base, "interval": settings.interval, "limit": settings.kline_limit}
        params_ob = {**params_base, "limit": 50}

        try:
            async with asyncio.TaskGroup() as tg:
                task_k = tg.create_task(self.session.get(url_kline, params=params_kline))
                task_o = tg.create_task(self.session.get(url_ob, params=params_ob))
                task_t = tg.create_task(self.session.get(url_tick, params=params_base))

            data_k = await task_k.result().json()
            data_o = await task_o.result().json()
            data_t = await task_t.result().json()
            
            latency = (time.perf_counter() - t0) * 1000
            
            if data_k.get("retCode") != 0: return pd.DataFrame(), {}, {}, latency
            
            df = pd.DataFrame(data_k["result"]["list"], columns=["startTime", "open", "high", "low", "close", "volume", "turnover"])
            df = df.astype(float).sort_values("startTime").reset_index(drop=True)
            ob = data_o.get("result", {})
            tick = data_t["result"]["list"][0] if data_t.get("result", {}).get("list") else {}

            return df, ob, tick, latency
        except Exception as e:
            logger.warning(f"API Error {symbol}: {e}")
            return pd.DataFrame(), {}, {}, 0

# --- 7. Technical Analysis ---

class TechnicalAnalyzer:
    @staticmethod
    def calculate(df: pd.DataFrame, orderbook: Dict) -> IndicatorData:
        if df.empty or len(df) < 200: return IndicatorData()
        
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        volume = df['volume'].values
        ind = IndicatorData()
        
        def get_ema(values, span):
            return pd.Series(values).ewm(span=span, adjust=False).mean().values

        ind.trend_ema_20 = sanitize_float(get_ema(close, 20)[-1])
        ind.trend_ema_200 = sanitize_float(get_ema(close, 200)[-1])

        tr = np.maximum(high - low, np.abs(high - np.roll(close, 1)))
        atr = pd.Series(tr).ewm(alpha=1/settings.atr_period, adjust=False).mean().values
        ind.vol_atr = sanitize_float(atr[-1])

        _, st_mult = settings.ehlers_settings
        hl2 = (high + low) / 2
        lower = hl2[-1] - (st_mult * atr[-1])
        upper = hl2[-1] + (st_mult * atr[-1])
        
        if close[-1] > ind.trend_ema_20 and close[-1] > lower: ind.trend_supertrend = "BULLISH"
        elif close[-1] < ind.trend_ema_20 and close[-1] < upper: ind.trend_supertrend = "BEARISH"

        delta = np.diff(close)
        up, down = delta.copy(), delta.copy()
        up[up < 0] = 0; down[down > 0] = 0
        roll_up = pd.Series(up).ewm(alpha=1/14, adjust=False).mean()
        roll_down = pd.Series(down).abs().ewm(alpha=1/14, adjust=False).mean()
        rs = roll_up / roll_down.replace(0, 1)
        rsi = 100.0 - (100.0 / (1.0 + rs))
        ind.mom_rsi = sanitize_float(rsi.iloc[-1])

        min_r = rsi.rolling(14).min(); max_r = rsi.rolling(14).max()
        stoch_k = ((rsi - min_r) / (max_r - min_r).replace(0, 1)) * 100
        ind.mom_stoch_k = sanitize_float(stoch_k.rolling(3).mean().iloc[-1])

        ema12 = get_ema(close, 12); ema26 = get_ema(close, 26)
        macd = ema12 - ema26; signal = get_ema(macd, 9)
        ind.mom_macd_hist = sanitize_float(macd[-1] - signal[-1])

        sma20 = pd.Series(close).rolling(20).mean().values
        std20 = pd.Series(close).rolling(20).std().values
        if close[-1] > sma20[-1] + (std20[-1] * 2): ind.vol_bb_position = "UPPER BREAK"
        elif close[-1] < sma20[-1] - (std20[-1] * 2): ind.vol_bb_position = "LOWER BREAK"

        cum_vol = np.cumsum(volume)
        cum_pv = np.cumsum(volume * (high + low + close) / 3)
        ind.flow_vwap = sanitize_float((cum_pv / cum_vol)[-1])

        if orderbook:
            bids = np.array(orderbook.get('b', []), dtype=float)
            asks = np.array(orderbook.get('a', []), dtype=float)
            if len(bids) > 0 and len(asks) > 0:
                bid_vol = np.sum(bids[:, 1]); ask_vol = np.sum(asks[:, 1])
                ind.flow_ob_imbalance = sanitize_float((bid_vol - ask_vol) / (bid_vol + ask_vol))

        return ind

# --- 8. AI & Fallback Analyst ---

class SmartAnalyzer:
    def __init__(self):
        genai.configure(api_key=settings.gemini_api_key)
        self.model = genai.GenerativeModel(settings.gemini_model_name)

    def _fallback_analysis(self, price: float, data: IndicatorData) -> SignalAnalysis:
        """Pure logic fallback if AI fails/throttles."""
        signal = "HOLD"
        trend = data.trend_supertrend
        confidence = 0
        explanation = "Technical Fallback (Limit Reached)"

        # Robust Fallback Logic
        if data.trend_supertrend == "BULLISH" and data.mom_rsi < 70 and data.mom_macd_hist > 0:
            signal = "BUY"
            confidence = 65
        elif data.trend_supertrend == "BEARISH" and data.mom_rsi > 30 and data.mom_macd_hist < 0:
            signal = "SELL"
            confidence = 65

        sl = price - (data.vol_atr * 2) if signal == "BUY" else price + (data.vol_atr * 2)
        tp = price + (data.vol_atr * 3) if signal == "BUY" else price - (data.vol_atr * 3)

        return SignalAnalysis(
            trend=trend, signal=signal, confidence=confidence,
            explanation=explanation, stop_loss=sl, take_profit=tp, source="Fallback"
        )

    async def analyze(self, symbol: str, price: float, data: IndicatorData) -> SignalAnalysis:
        prompt = f"""
        Analyze {symbol} Price: ${price:.4f}
        Metrics: Trend({data.trend_supertrend}, EMA20={data.trend_ema_20:.2f}), RSI({data.mom_rsi:.1f}), MACD({data.mom_macd_hist:.4f}), BB({data.vol_bb_position}), Flow({data.flow_ob_imbalance:.2f})
        Task: Trade Signal (15m). High confidence only.
        Output JSON: {{ "trend": "BULLISH/BEARISH/RANGING", "signal": "BUY/SELL/HOLD", "confidence": 0-100, "explanation": "reason", "stop_loss": float, "take_profit": float }}
        """
        
        try:
            # Run AI in thread
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: self.model.generate_content(
                    prompt,
                    generation_config={"response_mime_type": "application/json"}
                )
            )
            return SignalAnalysis.model_validate_json(response.text)
            
        except (google_exceptions.ResourceExhausted, google_exceptions.TooManyRequests):
            # 429 Error -> Use Fallback quietly
            return self._fallback_analysis(price, data)
            
        except Exception as e:
            logger.error(f"AI Error {symbol}: {e}")
            return self._fallback_analysis(price, data)

# --- 9. UI & Orchestration ---

class WhaleBot:
    def __init__(self):
        self.client = BybitPublicClient()
        self.analyzer = SmartAnalyzer()
        self.trader = PaperTrader()
        self.snapshots: Dict[str, MarketSnapshot] = {
            s: MarketSnapshot(symbol=s, timestamp=datetime.now(), indicators=IndicatorData()) 
            for s in settings.symbols
        }

    def get_layout(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body", ratio=2),
            Layout(name="portfolio", ratio=1)
        )
        return layout

    def generate_market_table(self) -> Table:
        table = Table(header_style="bold white", box=box.ROUNDED, expand=True)
        table.add_column("Symbol", style="cyan", width=10)
        table.add_column("Price", justify="right")
        table.add_column("Signal", justify="center")
        table.add_column("Conf", justify="right")
        table.add_column("Trend", justify="center")
        table.add_column("Reasoning", style="dim", no_wrap=True, overflow="ellipsis")
        table.add_column("TP / SL", justify="right", style="magenta")

        sorted_snaps = sorted(self.snapshots.values(), key=lambda x: x.analysis.confidence if x.analysis else 0, reverse=True)

        for snap in sorted_snaps:
            if snap.price == 0: continue
            an = snap.analysis
            if not an: continue

            sig = an.signal if an.confidence >= settings.min_confidence else "HOLD"
            sig_style = "bold green" if "BUY" in sig else "bold red" if "SELL" in sig else "dim"
            trend_sym = "↗" if an.trend == "BULLISH" else "↘" if an.trend == "BEARISH" else "→"
            plan = f"{an.take_profit:.2f}/{an.stop_loss:.2f}" if "HOLD" not in sig else "-"
            src = "[AI]" if an.source == "AI" else "[FB]"

            table.add_row(
                f"{snap.symbol} {src}", f"${snap.price:,.2f}", 
                f"[{sig_style}]{sig}[/{sig_style}]", f"{an.confidence}%", 
                f"{trend_sym} {an.trend[:4]}", an.explanation, plan
            )
        return table

    def generate_portfolio_table(self) -> Table:
        table = Table(title="Active Positions (Paper)", box=box.ROUNDED, expand=True)
        table.add_column("Symbol", style="cyan")
        table.add_column("Side", justify="center")
        table.add_column("Size", justify="right")
        table.add_column("Entry", justify="right")
        table.add_column("PnL", justify="right")
        table.add_column("ROI", justify="right")

        unrealized_pnl = 0.0
        for sym, pos in self.trader.positions.items():
            curr_price = self.snapshots[sym].price
            if curr_price == 0: continue
            self.trader.update_pnl_display(sym, curr_price)
            unrealized_pnl += pos.pnl
            
            pnl_color = "green" if pos.pnl >= 0 else "red"
            roi = (pos.pnl / pos.size_usd) * 100 if pos.size_usd > 0 else 0
            
            table.add_row(
                sym, f"[{'green' if pos.side=='LONG' else 'red'}]{pos.side}[/]", 
                f"${pos.size_usd:.0f}", f"{pos.entry_price:.4f}", 
                f"[{pnl_color}]{pos.pnl:+.2f}[/]", f"[{pnl_color}]{roi:+.2f}%[/]"
            )

        last_trade = ""
        if self.trader.history:
            last = self.trader.history[0]
            color = "green" if last['pnl'] > 0 else "red"
            last_trade = f" | Last: [{color}]{last['symbol']} ${last['pnl']:.2f}[/]"

        header = f"Balance: ${self.trader.balance:,.2f} | Equity: ${self.trader.balance + unrealized_pnl:,.2f}{last_trade}"
        return Panel(table, title=header, border_style="blue")

    async def process_symbol(self, symbol: str):
        try:
            df, ob, ticker, latency = await self.client.fetch_data(symbol)
            if df.empty: return

            current_price = float(ticker.get("lastPrice", 0))
            indicators = TechnicalAnalyzer.calculate(df, ob)
            
            # Ensure minimum delay between AI calls to prevent 429
            await asyncio.sleep(settings.ai_cooldown) 
            
            analysis = await self.analyzer.analyze(symbol, current_price, indicators)
            
            self.snapshots[symbol] = MarketSnapshot(
                symbol=symbol, price=current_price, timestamp=datetime.now(),
                indicators=indicators, analysis=analysis, last_updated=time.time(), latency_ms=latency
            )
            
            await self.trader.execute_signal(symbol, current_price, analysis)
        except Exception as e:
            logger.error(f"Err {symbol}: {e}")

    async def run(self):
        await self.client.start()
        console.clear()
        layout = self.get_layout()
        
        try:
            with Live(layout, refresh_per_second=2, screen=True) as live:
                next_scan = 0
                while True:
                    now = time.time()
                    
                    if now >= next_scan:
                        # Sequential processing to ensure we don't spam API even with asyncio.gather
                        for sym in settings.symbols:
                            await self.process_symbol(sym)
                            # Mini UI update per symbol
                            layout["body"].update(self.generate_market_table())
                            layout["portfolio"].update(self.generate_portfolio_table())
                        
                        next_scan = time.time() + settings.refresh_rate

                    wait = max(0, next_scan - time.time())
                    layout["header"].update(Panel(f"WhaleBot AI | Next Scan: {wait:.0f}s | [AI/Fallback] Mode Active", style="bold white on blue"))
                    layout["portfolio"].update(self.generate_portfolio_table())
                    
                    await asyncio.sleep(1)

        except KeyboardInterrupt:
            console.print("[yellow]Shutting down...[/yellow]")
        finally:
            await self.client.close()

if __name__ == "__main__":
    if not settings.gemini_api_key:
        print("Error: GEMINI_API_KEY missing")
        exit(1)
    asyncio.run(WhaleBot().run())
