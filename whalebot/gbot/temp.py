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
