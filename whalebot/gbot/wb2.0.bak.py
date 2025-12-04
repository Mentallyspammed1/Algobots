#!/usr/bin/env python3
# Enhanced WhaleBot AI Trader (v5.0 - Optimized & Refactored)

import asyncio
import json
import logging
import re
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, getcontext
from logging.handlers import RotatingFileHandler
from pathlib import Path

import aiohttp
import google.generativeai as genai
import numpy as np
import pandas as pd
import pandas_ta as ta
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

# --- Global Setup & Constants ---
getcontext().prec = 28
SIGNAL_SEMAPHORE = asyncio.Semaphore(5)
STATE_FILE = Path("whalebot_state.json")
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# --- Configuration ---

class IndicatorSettings(BaseModel):
    rsi_period: int = 14
    atr_period: int = 14
    bb_period: int = 20
    bb_std: float = 2.0
    st_period: int = 10
    st_mult: float = 3.0
    ema_fast: int = 20
    ema_slow: int = 200

class TraderSettings(BaseModel):
    initial_balance: Decimal = Field(Decimal("10000.00"))
    risk_per_trade: Decimal = Field(Decimal("0.01"))
    min_rr: float = Field(1.5)
    min_confidence: float = Field(0.70)
    trading_fee: Decimal = Field(Decimal("0.00055"))
    slippage: Decimal = Field(Decimal("0.0001"))

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gemini_api_key: str = Field(..., alias="GEMINI_API_KEY")
    bybit_base_url: str = "https://api.bybit.com"
    gemini_model_name: str = "gemini-2.0-flash" # Updated to latest efficient model

    symbols: list[str] = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT",
        "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "SUIUSDT",
    ]
    interval: str = "15"
    category: str = "linear"
    kline_limit: int = 300
    refresh_rate: int = 30

    indicators: IndicatorSettings = IndicatorSettings()
    trader: TraderSettings = TraderSettings()
    logging_level: str = "INFO"

settings = Settings()

# --- Logging Setup ---
def setup_logger():
    logger = logging.getLogger("WhaleBot")
    logger.setLevel(getattr(logging, settings.logging_level))
    logger.propagate = False
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S")
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(fmt)
        logger.addHandler(ch)
        fh = RotatingFileHandler(LOG_DIR / "whalebot.log", maxBytes=5*1024*1024, backupCount=3)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    return logger

logger = setup_logger()
console = Console()

# --- Data Models ---

class IndicatorData(BaseModel):
    ema_20: float = 0.0
    ema_200: float = 0.0
    super_trend: str = "NEUTRAL"
    ichimoku_status: str = "NEUTRAL"
    rsi: float = 50.0
    stoch_k: float = 50.0
    macd_hist: float = 0.0
    atr: float = 0.0
    bb_position: str = "INSIDE"
    vwap: float = 0.0
    ob_imbalance: float = 0.0

    @field_validator("*", mode="before")
    def clean_floats(cls, v):
        return float(v) if isinstance(v, (float, int, np.floating)) and np.isfinite(v) else 0.0

class SignalAnalysis(BaseModel):
    trend: str
    signal: str = "HOLD"
    confidence: float
    explanation: str
    entry_price: Decimal = Decimal(0)
    stop_loss: Decimal = Decimal(0)
    take_profit: Decimal = Decimal(0)

    @field_validator("signal", mode="before")
    def normalize_signal(cls, v):
        return v.upper().strip()

    @field_validator("entry_price", "stop_loss", "take_profit", mode="before")
    def convert_decimal(cls, v):
        if v is None: return Decimal(0)
        try:
            return Decimal(str(v)).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
        except:
            return Decimal(0)

class MarketSnapshot(BaseModel):
    symbol: str
    price: Decimal = Decimal(0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    indicators: IndicatorData = Field(default_factory=IndicatorData)
    analysis: SignalAnalysis | None = None
    error: str | None = None
    last_updated: float = 0.0
    latency_ms: float = 0.0

# --- 1. API Client ---

class BybitPublicClient:
    def __init__(self):
        self.session: aiohttp.ClientSession | None = None
        self.timeout = aiohttp.ClientTimeout(total=10)

    async def __aenter__(self):
        if not self.session:
            self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def fetch_data(self, symbol: str) -> tuple[pd.DataFrame, dict, dict, float]:
        t0 = time.perf_counter()
        base = settings.bybit_base_url

        try:
            # Construct URLs
            u_k = f"{base}/v5/market/kline?category={settings.category}&symbol={symbol}&interval={settings.interval}&limit={settings.kline_limit}"
            u_o = f"{base}/v5/market/orderbook?category={settings.category}&symbol={symbol}&limit=50"
            u_t = f"{base}/v5/market/tickers?category={settings.category}&symbol={symbol}"

            async with asyncio.TaskGroup() as tg:
                t_k = tg.create_task(self.session.get(u_k))
                t_o = tg.create_task(self.session.get(u_o))
                t_t = tg.create_task(self.session.get(u_t))

            r_k, r_o, r_t = t_k.result(), t_o.result(), t_t.result()
            d_k, d_o, d_t = await r_k.json(), await r_o.json(), await r_t.json()

            latency = (time.perf_counter() - t0) * 1000

            if d_k.get("retCode") != 0:
                return pd.DataFrame(), {}, {}, latency

            # Process Kline
            raw_list = d_k["result"]["list"]
            if not raw_list: return pd.DataFrame(), {}, {}, latency

            df = pd.DataFrame(raw_list, columns=["startTime", "open", "high", "low", "close", "volume", "turnover"])
            df = df.astype(float)
            df["startTime"] = pd.to_datetime(df["startTime"], unit="ms")
            df = df.sort_values("startTime").set_index("startTime")

            ob = d_o.get("result", {})
            tick = d_t["result"]["list"][0] if d_t.get("result", {}).get("list") else {}

            return df, ob, tick, latency

        except Exception as e:
            logger.debug(f"Fetch error {symbol}: {e}")
            return pd.DataFrame(), {}, {}, 0.0

# --- 2. Technical Analysis ---

class TechnicalAnalyzer:
    @staticmethod
    def calculate(df: pd.DataFrame, orderbook: dict) -> IndicatorData:
        s = settings.indicators
        if len(df) < s.ema_slow + 5:
            return IndicatorData()

        # Calculations
        df.ta.ema(length=s.ema_fast, append=True)
        df.ta.ema(length=s.ema_slow, append=True)
        df.ta.supertrend(length=s.st_period, multiplier=s.st_mult, append=True)
        df.ta.rsi(length=s.rsi_period, append=True)
        df.ta.stoch(append=True)
        df.ta.macd(append=True)
        df.ta.bbands(length=s.bb_period, std=s.bb_std, append=True)
        df.ta.atr(length=s.atr_period, append=True)
        df.ta.vwap(append=True)

        # Ichimoku (custom extraction)
        ichimoku = ta.ichimoku(df["high"], df["low"], df["close"])
        if ichimoku is not None:
            df = pd.concat([df, ichimoku[0]], axis=1)

        last = df.iloc[-1]
        ind = IndicatorData()

        # Extract Values safely
        ind.ema_20 = last.get(f"EMA_{s.ema_fast}", 0)
        ind.ema_200 = last.get(f"EMA_{s.ema_slow}", 0)
        ind.rsi = last.get(f"RSI_{s.rsi_period}", 50)
        ind.atr = last.get(f"ATR_{s.atr_period}", 0)
        ind.vwap = last.get("VWAP_D", last.get("VWAP", 0)) # Handle different pandas_ta versions

        # SuperTrend
        st_col = f"SUPERTd_{s.st_mult:.1f}_{s.st_period}"
        ind.super_trend = "BULLISH" if last.get(st_col, 0) == 1 else "BEARISH"

        # Ichimoku Logic
        span_a = last.get("ISA_9_26_52", 0)
        span_b = last.get("ISB_9_26_52", 0)
        close = last["close"]
        if close > max(span_a, span_b): ind.ichimoku_status = "ABOVE CLOUD"
        elif close < min(span_a, span_b): ind.ichimoku_status = "BELOW CLOUD"
        else: ind.ichimoku_status = "IN CLOUD"

        # Momentum
        ind.stoch_k = last.get("STOCHk_14_3_3", 50)
        ind.macd_hist = last.get("MACDh_12_26_9", 0)

        # Bollinger Bands
        bbu = last.get(f"BBU_{s.bb_period}_{s.bb_std:.1f}", 0)
        bbl = last.get(f"BBL_{s.bb_period}_{s.bb_std:.1f}", 0)
        if close > bbu: ind.bb_position = "UPPER BREAK"
        elif close < bbl: ind.bb_position = "LOWER BREAK"

        # Orderbook Imbalance
        if orderbook:
            bids = np.array(orderbook.get("b", []), dtype=float)
            asks = np.array(orderbook.get("a", []), dtype=float)
            if len(bids) > 0 and len(asks) > 0:
                bv, av = np.sum(bids[:, 1]), np.sum(asks[:, 1])
                ind.ob_imbalance = (bv - av) / (bv + av) if (bv + av) > 0 else 0

        return ind

# --- 3. AI Analyst ---

class GeminiAnalyzer:
    def __init__(self):
        genai.configure(api_key=settings.gemini_api_key)
        self.model = genai.GenerativeModel(settings.gemini_model_name)
        self.min_conf = settings.trader.min_confidence

    def _clean_json(self, text: str) -> str:
        """Removes markdown code blocks and extracts JSON."""
        text = re.sub(r"```json\s*|\s*```", "", text, flags=re.IGNORECASE)
        match = re.search(r"\{.*\}", text, re.DOTALL)
        return match.group(0) if match else ""

    async def analyze(self, symbol: str, price: Decimal, data: IndicatorData) -> SignalAnalysis:
        prompt = f"""
        Analyze {symbol} (Price: {price:.4f}). Technicals:
        Trend: EMA20 {data.ema_20:.2f}, EMA200 {data.ema_200:.2f}, ST {data.super_trend}, Ichi {data.ichimoku_status}.
        Mom: RSI {data.rsi:.1f}, StochK {data.stoch_k:.1f}, MACDh {data.macd_hist:.4f}.
        Vol: ATR {data.atr:.4f}, BB {data.bb_position}. Flow: OB {data.ob_imbalance:.2f}, VWAP {data.vwap:.2f}.
        
        Task: Return JSON ONLY.
        1. Trend: BULLISH/BEARISH/RANGING.
        2. Signal: BUY/SELL/HOLD. Confidence (0.0-1.0).
        3. Entry, SL, TP (Float). SL ~1.5xATR, TP >1.5x Risk.
        
        Schema:
        {{ "trend": "str", "signal": "str", "confidence": float, "explanation": "max 10 words", "entry_price": float, "stop_loss": float, "take_profit": float }}
        """

        async with SIGNAL_SEMAPHORE:
            try:
                resp = await asyncio.to_thread(
                    self.model.generate_content,
                    prompt,
                    generation_config={"temperature": 0.1, "response_mime_type": "application/json"},
                )

                json_str = self._clean_json(resp.text)
                if not json_str: raise ValueError("No JSON found")

                an = SignalAnalysis.model_validate_json(json_str)

                # Logic Validation
                if an.signal == "HOLD" or an.confidence < self.min_conf:
                    return SignalAnalysis(trend=an.trend, signal="HOLD", confidence=an.confidence, explanation=an.explanation)

                # R:R Check
                risk = abs(an.entry_price - an.stop_loss)
                reward = abs(an.take_profit - an.entry_price)
                if risk == 0 or (reward / risk) < settings.trader.min_rr:
                    return SignalAnalysis(trend=an.trend, signal="HOLD", confidence=an.confidence, explanation="Low R:R")

                return an

            except Exception as e:
                logger.error(f"AI Error {symbol}: {e}")
                return SignalAnalysis(trend="ERROR", signal="HOLD", confidence=0, explanation="AI Fail")

# --- 4. Paper Trader ---

class PaperTrader:
    def __init__(self):
        self.balance: Decimal = settings.trader.initial_balance
        self.positions: dict[str, dict] = {}
        self.history: list[dict] = []
        self.executor = ThreadPoolExecutor(max_workers=1)
        self._load_state()

    def _load_state(self):
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE) as f:
                    data = json.load(f)
                    self.balance = Decimal(data["balance"])
                    self.history = data.get("history", [])
                    for sym, pos in data.get("positions", {}).items():
                        pos["entry_price"] = Decimal(pos["entry_price"])
                        pos["stop_loss"] = Decimal(pos["stop_loss"])
                        pos["take_profit"] = Decimal(pos["take_profit"])
                        pos["qty"] = Decimal(pos["qty"])
                        pos["entry_time"] = datetime.fromisoformat(pos["entry_time"])
                        self.positions[sym] = pos
            except Exception as e:
                logger.error(f"State load error: {e}")

    def save_state(self):
        """Non-blocking save."""
        data = {
            "balance": str(self.balance),
            "history": self.history,
            "positions": {
                k: {
                    key: str(val) if isinstance(val, Decimal) else val.isoformat() if isinstance(val, datetime) else val
                    for key, val in v.items()
                } for k, v in self.positions.items()
            },
        }
        self.executor.submit(self._write_file, data)

    def _write_file(self, data):
        with open(STATE_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def execute(self, snap: MarketSnapshot):
        # 1. Check Exits
        if snap.symbol in self.positions:
            self._check_exit(snap)
            return

        # 2. Check Entries
        an = snap.analysis
        if not an or an.signal == "HOLD": return

        risk_amt = self.balance * settings.trader.risk_per_trade
        dist = abs(an.entry_price - an.stop_loss)
        if dist == 0: return

        qty = (risk_amt / dist).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cost = qty * an.entry_price

        if cost > self.balance or cost < 10: return # Min trade $10

        # Apply Slippage
        slip = settings.trader.slippage
        entry = an.entry_price * (1 + slip) if an.signal == "BUY" else an.entry_price * (1 - slip)

        self.balance -= (entry * qty * settings.trader.trading_fee)

        self.positions[snap.symbol] = {
            "symbol": snap.symbol, "side": an.signal, "qty": qty,
            "entry_price": entry, "stop_loss": an.stop_loss, "take_profit": an.take_profit,
            "entry_time": datetime.now(timezone.utc),
        }
        self.save_state()
        logger.info(f"OPEN {an.signal} {snap.symbol} x{qty} @ {entry:.4f}")

    def _check_exit(self, snap: MarketSnapshot):
        pos = self.positions[snap.symbol]
        price = snap.price
        reason = None

        if pos["side"] == "BUY":
            if price <= pos["stop_loss"]: reason = "SL"
            elif price >= pos["take_profit"]: reason = "TP"
        elif price >= pos["stop_loss"]: reason = "SL"
        elif price <= pos["take_profit"]: reason = "TP"

        if reason:
            slip = settings.trader.slippage
            exit_p = price * (1 - slip) if pos["side"] == "BUY" else price * (1 + slip)

            pnl = (exit_p - pos["entry_price"]) * pos["qty"]
            if pos["side"] == "SELL": pnl = -pnl

            fee = exit_p * pos["qty"] * settings.trader.trading_fee
            net_pnl = pnl - fee

            self.balance += net_pnl
            del self.positions[snap.symbol]

            self.history.insert(0, {
                "time": datetime.now().isoformat(), "symbol": snap.symbol,
                "side": pos["side"], "pnl": str(net_pnl), "reason": reason,
            })
            self.history = self.history[:20]
            self.save_state()
            logger.info(f"CLOSE {snap.symbol} {reason} PnL: {net_pnl:.2f}")

# --- 5. UI & Orchestrator ---

class WhaleBot:
    def __init__(self):
        self.running = True
        signal.signal(signal.SIGINT, self._stop)
        self.client = BybitPublicClient()
        self.analyzer = GeminiAnalyzer()
        self.trader = PaperTrader()
        self.snapshots = {s: MarketSnapshot(symbol=s) for s in settings.symbols}

    def _stop(self, *args):
        self.running = False
        self.trader.save_state()
        console.print("[bold red]Stopping...[/]")

    def render_ui(self) -> Layout:
        layout = Layout()
        layout.split_column(Layout(name="header", size=3), Layout(name="body"), Layout(name="footer", size=10))

        # Header
        latencies = [s.latency_ms for s in self.snapshots.values() if s.latency_ms > 0]
        avg_lat = sum(latencies)/len(latencies) if latencies else 0
        layout["header"].update(Panel(
            f"[bold white]WhaleBot AI v5.0[/] | [cyan]Bal: ${self.trader.balance:,.2f}[/] | [magenta]Lat: {avg_lat:.0f}ms[/]",
            style="on blue",
        ))

        # Body: Market Table
        table = Table(expand=True, box=box.SIMPLE_HEAD, header_style="bold cyan")
        table.add_column("Symbol")
        table.add_column("Price")
        table.add_column("Signal")
        table.add_column("Conf")
        table.add_column("Trend")
        table.add_column("Plan (TP/SL)")
        table.add_column("Updated")

        for s in sorted(self.snapshots.values(), key=lambda x: x.analysis.confidence if x.analysis else 0, reverse=True):
            if s.price == 0:
                table.add_row(s.symbol, "Loading...", "", "", "", "", "")
                continue

            # Color logic
            pos = self.trader.positions.get(s.symbol)
            price_str = f"${s.price:.4f}"

            if pos:
                pnl = (s.price - pos["entry_price"]) * pos["qty"]
                if pos["side"] == "SELL": pnl = -pnl
                c = "green" if pnl >= 0 else "red"
                price_str += f"\n[{c}]${pnl:.2f}[/]"
                sig_str = f"[bold {c}]OPEN {pos['side']}[/]"
                conf_str = "---"
                plan_str = f"TP: {pos['take_profit']:.4f}\nSL: {pos['stop_loss']:.4f}"
            else:
                an = s.analysis
                if not an: continue
                c = "green" if an.signal == "BUY" else "red" if an.signal == "SELL" else "yellow"
                sig_str = f"[{c}]{an.signal}[/]"
                conf_str = f"{an.confidence*100:.0f}%"
                plan_str = f"TP: {an.take_profit:.4f}\nSL: {an.stop_loss:.4f}" if an.signal != "HOLD" else f"[dim]{an.explanation}[/]"

            trend_icon = "↗" if s.indicators.super_trend == "BULLISH" else "↘"
            age = time.time() - s.last_updated

            table.add_row(
                f"[bold]{s.symbol}[/]", price_str, sig_str, conf_str,
                f"{trend_icon} {s.indicators.ema_20:.2f}", plan_str, f"{age:.0f}s",
            )

        layout["body"].update(table)

        # Footer: History
        hist_table = Table(show_header=False, box=None, padding=(0, 2))
        for t in self.trader.history[:3]:
            c = "green" if Decimal(t["pnl"]) >= 0 else "red"
            hist_table.add_row(
                f"{t['time'][11:16]}", t["symbol"], t["side"],
                f"[{c}]${Decimal(t['pnl']):.2f}[/]", t["reason"],
            )
        layout["footer"].update(Panel(hist_table, title="Recent Trades", border_style="dim"))

        return layout

    async def run(self):
        async with self.client:
            with Live(self.render_ui(), refresh_per_second=4, screen=True) as live:
                while self.running:
                    # Fetch & Analyze
                    tasks = []
                    for sym in settings.symbols:
                        tasks.append(self.process_symbol(sym))
                    await asyncio.gather(*tasks)

                    # UI Update Loop (wait for next refresh cycle)
                    end_time = time.time() + settings.refresh_rate
                    while time.time() < end_time and self.running:
                        live.update(self.render_ui())
                        await asyncio.sleep(0.25)

    async def process_symbol(self, symbol: str):
        try:
            df, ob, tick, lat = await self.client.fetch_data(symbol)
            snap = self.snapshots[symbol]

            if df.empty:
                snap.error = "No Data"
                return

            price = Decimal(str(tick.get("lastPrice", 0)))
            snap.price = price
            snap.latency_ms = lat

            # TA & AI
            snap.indicators = TechnicalAnalyzer.calculate(df, ob)
            snap.analysis = await self.analyzer.analyze(symbol, price, snap.indicators)
            snap.last_updated = time.time()

            # Trade
            self.trader.execute(snap)

        except Exception as e:
            logger.error(f"Process error {symbol}: {e}")

if __name__ == "__main__":
    if not settings.gemini_api_key:
        print("Error: GEMINI_API_KEY missing in .env")
        sys.exit(1)
    try:
        asyncio.run(WhaleBot().run())
    except KeyboardInterrupt:
        pass
