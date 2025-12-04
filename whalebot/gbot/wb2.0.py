#!/usr/bin/env python3
import asyncio
import json
import logging
import re
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, getcontext
from pathlib import Path
from typing import Literal

import aiohttp
import google.generativeai as genai
import numpy as np
import pandas as pd
from colorama import init
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# --- Global Setup ---
load_dotenv()
init(autoreset=True)
warnings.filterwarnings("ignore", category=UserWarning, module="pandas_ta")
warnings.filterwarnings("ignore", category=FutureWarning)
getcontext().prec = 28

# --- Logging Configuration ---
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
STATE_FILE = Path("whalebot_state.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "whalebot.log", mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),  # Log to stdout for Docker/Systemd compatibility
    ],
)
# Silence noisy libraries
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("google.ai").setLevel(logging.WARNING)
logger = logging.getLogger("WhaleBot")

# --- Configuration (Pydantic) ---

class TraderSettings(BaseModel):
    initial_balance: Decimal = Field(Decimal("10000.00"), gt=0)
    risk_per_trade: Decimal = Field(Decimal("0.02"), ge=0.01, le=1.0)  # 2% risk
    leverage: int = Field(5, ge=1, le=20)
    min_confidence: float = Field(0.70, ge=0.1, le=1.0)
    min_rr: float = Field(1.5, ge=1.0)  # Min Risk/Reward ratio
    trading_fee: Decimal = Field(Decimal("0.00055"), ge=0)
    slippage: Decimal = Field(Decimal("0.0001"), ge=0)
    use_trailing_stop: bool = True
    trailing_callback: Decimal = Field(Decimal("0.005"), ge=0)  # 0.5% trail

class TechnicalSettings(BaseModel):
    rsi_period: int = 14
    ema_fast: int = 9
    ema_slow: int = 21
    atr_period: int = 14
    bb_period: int = 20
    bb_std: float = 2.0

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gemini_api_key: str = Field(..., alias="GEMINI_API_KEY")
    bybit_base_url: str = "https://api.bybit.com"
    gemini_model_name: str = "gemini-2.5-flash-lite"

    symbols: list[str] = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "BNBUSDT"]
    interval: str = "15"  # 15m timeframe
    category: str = "linear"
    kline_limit: int = 200
    refresh_rate: int = 10  # UI Refresh rate (data fetch is decoupled)

    trader: TraderSettings = TraderSettings()
    tech: TechnicalSettings = TechnicalSettings()

    # AI Rate Limiting
    ai_cooldown_seconds: int = 15

settings = Settings()

# --- Utilities ---

def clean_json_response(text: str) -> str:
    """Extracts and cleans JSON from LLM markdown response."""
    try:
        # Find the JSON block
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            json_str = match.group(0)
            return json_str
        # Fallback: Strip markdown code fences
        text = re.sub(r"^```json\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
        return text.strip()
    except Exception:
        return "{}"

# --- Data Models ---

class SignalAnalysis(BaseModel):
    action: Literal["BUY", "SELL", "HOLD"]
    confidence: float
    reason: str
    entry_price: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("entry_price", "stop_loss", "take_profit", mode="before")
    def float_to_decimal(cls, v):
        return Decimal(str(v)) if isinstance(v, (float, int, str)) else v

class IndicatorData(BaseModel):
    rsi: float = 50.0
    macd_hist: float = 0.0
    trend: Literal["BULL", "BEAR", "NEUTRAL"] = "NEUTRAL"
    atr: float = 0.0
    ob_imbalance: float = 0.0
    nearest_support: float = 0.0
    nearest_resistance: float = 0.0
    price: Decimal = Decimal(0)

class MarketSnapshot(BaseModel):
    symbol: str
    price: Decimal = Decimal(0)
    indicators: IndicatorData = Field(default_factory=IndicatorData)
    analysis: SignalAnalysis | None = None
    last_updated: float = 0.0
    error: str | None = None
    latency_ms: float = 0.0
    last_ai_trigger: float = 0.0

# --- Rate Limiter ---

class TokenBucket:
    def __init__(self, capacity: int, fill_rate: float):
        self.capacity = capacity
        self._tokens = capacity
        self.fill_rate = fill_rate
        self.last_time = time.time()

    def consume(self) -> bool:
        now = time.time()
        # Refill
        delta = now - self.last_time
        self._tokens = min(self.capacity, self._tokens + delta * self.fill_rate)
        self.last_time = now

        if self._tokens >= 1:
            self._tokens -= 1
            return True
        return False

# Rate limit: 15 requests per minute (0.25 per second) for free tier safety
ai_limiter = TokenBucket(capacity=2, fill_rate=15.0/60.0)

# --- Core Classes ---

class BybitClient:
    def __init__(self):
        self.session: aiohttp.ClientSession | None = None

    async def start(self):
        if not self.session:
            conn = aiohttp.TCPConnector(limit=20, ssl=False)
            self.session = aiohttp.ClientSession(connector=conn, headers={"User-Agent": "WhaleBot/Pro"})

    async def stop(self):
        if self.session:
            await self.session.close()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5),
           retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)))
    async def _fetch(self, url: str, params: dict) -> dict:
        async with self.session.get(url, params=params, timeout=10) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def get_market_data(self, symbol: str) -> tuple[pd.DataFrame, dict, dict, float]:
        """Fetches Kline, Ticker, and Orderbook data concurrently."""
        t0 = time.perf_counter()

        kline_params = {"category": settings.category, "symbol": symbol, "interval": settings.interval, "limit": settings.kline_limit}
        ob_params = {"category": settings.category, "symbol": symbol, "limit": 50}
        tick_params = {"category": settings.category, "symbol": symbol}

        try:
            async with asyncio.TaskGroup() as tg:
                kline_task = tg.create_task(self._fetch(f"{settings.bybit_base_url}/v5/market/kline", kline_params))
                ob_task = tg.create_task(self._fetch(f"{settings.bybit_base_url}/v5/market/orderbook", ob_params))
                tick_task = tg.create_task(self._fetch(f"{settings.bybit_base_url}/v5/market/tickers", tick_params))

            kline_data = await kline_task
            ob_data = await ob_task
            tick_data = await tick_task

            latency = (time.perf_counter() - t0) * 1000

            # Process Klines
            if kline_data["retCode"] != 0: raise ValueError("Bybit API Error: Kline")
            df = pd.DataFrame(kline_data["result"]["list"], columns=["startTime", "open", "high", "low", "close", "volume", "turnover"])
            df = df.astype(float).sort_values("startTime").reset_index(drop=True)

            return df, ob_data.get("result", {}), tick_data["result"]["list"][0], latency

        except Exception as e:
            logger.debug(f"Fetch failed for {symbol}: {e}")
            return pd.DataFrame(), {}, {}, 0.0

class TechnicalAnalyzer:
    """Runs strictly in a ThreadPool to avoid blocking the async loop."""

    @staticmethod
    def compute(df: pd.DataFrame, ob: dict) -> IndicatorData:
        if df.empty or len(df) < 50:
            return IndicatorData()

        # Use Pandas TA
        # EMA
        df.ta.ema(length=settings.tech.ema_fast, append=True)
        df.ta.ema(length=settings.tech.ema_slow, append=True)
        # RSI
        df.ta.rsi(length=settings.tech.rsi_period, append=True)
        # MACD
        df.ta.macd(append=True)
        # ATR
        df.ta.atr(length=settings.tech.atr_period, append=True)

        last = df.iloc[-1]

        # Trend Logic
        ema_f = last.get(f"EMA_{settings.tech.ema_fast}")
        ema_s = last.get(f"EMA_{settings.tech.ema_slow}")
        trend = "BULL" if ema_f > ema_s else "BEAR"

        # Orderbook Imbalance
        imbalance = 0.0
        if ob and "b" in ob and "a" in ob:
            bids = np.array(ob["b"], dtype=float)
            asks = np.array(ob["a"], dtype=float)
            if bids.size > 0 and asks.size > 0:
                bid_vol = np.sum(bids[:, 1])
                ask_vol = np.sum(asks[:, 1])
                total = bid_vol + ask_vol
                if total > 0:
                    imbalance = (bid_vol - ask_vol) / total

        # Support/Resistance (Simple swing detection on last 20 candles)
        recent_high = df["high"].tail(20).max()
        recent_low = df["low"].tail(20).min()

        return IndicatorData(
            rsi=last.get(f"RSI_{settings.tech.rsi_period}", 50),
            macd_hist=last.get("MACDh_12_26_9", 0),
            trend=trend,
            atr=last.get(f"ATR_{settings.tech.atr_period}", 0),
            ob_imbalance=imbalance,
            nearest_resistance=recent_high,
            nearest_support=recent_low,
            price=Decimal(str(last["close"])),
        )

class GeminiAnalyst:
    def __init__(self):
        genai.configure(api_key=settings.gemini_api_key)
        self.model = genai.GenerativeModel(
            settings.gemini_model_name,
            generation_config={"response_mime_type": "application/json"},
        )

    async def analyze(self, symbol: str, data: IndicatorData) -> SignalAnalysis:
        if not ai_limiter.consume():
            return self._fallback(data)

        prompt = f"""
        Analyze {symbol} for a SCALPING trade (15m timeframe).
        
        Data:
        - Price: {data.price}
        - Trend: {data.trend}
        - RSI: {data.rsi:.2f}
        - MACD Hist: {data.macd_hist:.4f}
        - OB Imbalance: {data.ob_imbalance:.2f} (positive=buy pressure)
        - ATR: {data.atr:.4f}
        - Support: {data.nearest_support} | Resistance: {data.nearest_resistance}

        Strict Rules:
        1. Only BUY if Trend=BULL, RSI < 70, Imbalance > -0.2.
        2. Only SELL if Trend=BEAR, RSI > 30, Imbalance < 0.2.
        3. Risk/Reward must be > {settings.trader.min_rr}.
        4. SL/TP must be realistic based on ATR ({data.atr}).
        
        Output valid JSON:
        {{
            "action": "BUY" | "SELL" | "HOLD",
            "confidence": 0.0 to 1.0,
            "reason": "Concise reason",
            "entry_price": float,
            "stop_loss": float,
            "take_profit": float
        }}
        """

        try:
            # Offload blocking network call
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, lambda: self.model.generate_content(prompt))

            clean_text = clean_json_response(response.text)
            signal_dict = json.loads(clean_text)

            # Validation
            signal = SignalAnalysis(**signal_dict)

            # Logic Check (AI sometimes hallucinates prices)
            if signal.action == "BUY" and signal.stop_loss >= signal.entry_price:
                return self._fallback(data, "Invalid AI SL")
            if signal.action == "SELL" and signal.stop_loss <= signal.entry_price:
                return self._fallback(data, "Invalid AI SL")

            return signal

        except (ValidationError, json.JSONDecodeError):
            return self._fallback(data, "Parse Error")
        except Exception as e:
            logger.error(f"AI Error: {e}")
            return self._fallback(data, "AI Exception")

    def _fallback(self, data: IndicatorData, reason="Fallback") -> SignalAnalysis:
        """Deterministic logic when AI is throttled or fails."""
        action = "HOLD"
        conf = 0.0

        # Simple Strategy
        if data.trend == "BULL" and data.rsi < 40 and data.macd_hist > 0:
            action = "BUY"
            conf = 0.65
        elif data.trend == "BEAR" and data.rsi > 60 and data.macd_hist < 0:
            action = "SELL"
            conf = 0.65

        sl_dist = Decimal(str(data.atr)) * Decimal("1.5")
        tp_dist = Decimal(str(data.atr)) * Decimal("2.5")

        entry = data.price
        if action == "BUY":
            sl = entry - sl_dist
            tp = entry + tp_dist
        else:
            sl = entry + sl_dist
            tp = entry - tp_dist

        return SignalAnalysis(
            action=action, confidence=conf, reason=reason,
            entry_price=entry, stop_loss=sl, take_profit=tp,
        )

class StateManager:
    """Handles atomic state persistence."""
    def __init__(self):
        self.lock = asyncio.Lock()
        self.executor = ThreadPoolExecutor(max_workers=1)

    async def save(self, data: dict):
        async with self.lock:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(self.executor, self._write_atomic, data)

    def _write_atomic(self, data: dict):
        try:
            # Convert decimals to str for JSON
            serialized = json.dumps(data, default=str, indent=2)
            temp_path = STATE_FILE.with_suffix(".tmp")
            with open(temp_path, "w") as f:
                f.write(serialized)
            temp_path.replace(STATE_FILE)
        except Exception as e:
            logger.error(f"State save failed: {e}")

    def load(self) -> dict:
        if not STATE_FILE.exists():
            return {}
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            return {}

class PaperTrader:
    def __init__(self, state_manager: StateManager):
        self.state_mgr = state_manager
        self.balance = settings.trader.initial_balance
        self.positions: dict[str, dict] = {}
        self.history: list[dict] = []
        self._load()

    def _load(self):
        data = self.state_mgr.load()
        if data:
            self.balance = Decimal(data.get("balance", str(settings.trader.initial_balance)))
            self.positions = {k: self._parse_pos(v) for k, v in data.get("positions", {}).items()}
            self.history = data.get("history", [])

    def _parse_pos(self, data: dict) -> dict:
        """Convert stored strings back to Decimals."""
        for k in ["entry_price", "stop_loss", "take_profit", "qty", "highest_price"]:
            if k in data: data[k] = Decimal(data[k])
        return data

    async def save(self):
        data = {
            "balance": self.balance,
            "positions": self.positions,
            "history": self.history[-50:],  # Keep last 50
        }
        await self.state_mgr.save(data)

    async def process_signal(self, snapshot: MarketSnapshot):
        symbol = snapshot.symbol
        price = snapshot.price
        signal = snapshot.analysis

        # 1. Manage Existing Position
        if symbol in self.positions:
            await self._manage_position(symbol, price)
            return

        # 2. Open New Position
        if signal and signal.action != "HOLD" and signal.confidence >= settings.trader.min_confidence:
            self._open_position(symbol, price, signal)
            await self.save()

    def _open_position(self, symbol: str, price: Decimal, signal: SignalAnalysis):
        # Risk Calculation
        risk_amt = self.balance * settings.trader.risk_per_trade
        dist = abs(signal.entry_price - signal.stop_loss)
        if dist == 0: return

        qty = risk_amt / dist
        # Leverage cap
        max_qty = (self.balance * settings.trader.leverage) / price
        qty = min(qty, max_qty).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

        if qty * price < 10: return # Minimum trade size

        # Fee Deduction
        cost = qty * price
        self.balance -= cost * settings.trader.trading_fee

        self.positions[symbol] = {
            "symbol": symbol,
            "side": signal.action,
            "qty": qty,
            "entry_price": price,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "highest_price": price, # For trailing stop
            "entry_time": datetime.now().isoformat(),
        }
        logger.info(f"OPEN {signal.action} {symbol} @ {price:.2f}")

    async def _manage_position(self, symbol: str, price: Decimal):
        pos = self.positions[symbol]
        side = pos["side"]
        closed = False
        reason = ""
        pnl = Decimal(0)

        # Trailing Stop Update
        if settings.trader.use_trailing_stop:
            if side == "BUY":
                if price > pos["highest_price"]:
                    pos["highest_price"] = price
                    # Move SL up if trail allows
                    new_sl = price * (1 - settings.trader.trailing_callback)
                    pos["stop_loss"] = max(pos["stop_loss"], new_sl)
            elif side == "SELL":
                if price < pos["highest_price"]:
                    pos["highest_price"] = price
                    new_sl = price * (1 + settings.trader.trailing_callback)
                    pos["stop_loss"] = min(pos["stop_loss"], new_sl)

        # Check Exit
        if side == "BUY":
            if price <= pos["stop_loss"]:
                closed = True; reason = "SL"
            elif price >= pos["take_profit"]:
                closed = True; reason = "TP"
        elif side == "SELL":
            if price >= pos["stop_loss"]:
                closed = True; reason = "SL"
            elif price <= pos["take_profit"]:
                closed = True; reason = "TP"

        if closed:
            # PnL Calculation
            diff = (price - pos["entry_price"]) if side == "BUY" else (pos["entry_price"] - price)
            pnl = diff * pos["qty"]
            fee = price * pos["qty"] * settings.trader.trading_fee
            net_pnl = pnl - fee

            self.balance += net_pnl

            self.history.append({
                "symbol": symbol, "side": side, "pnl": net_pnl, "reason": reason,
                "time": datetime.now().strftime("%H:%M"),
            })
            del self.positions[symbol]
            await self.save()
            logger.info(f"CLOSE {symbol} {reason} | PnL: {net_pnl:.2f}")

# --- Main Application ---

class WhaleBotPro:
    def __init__(self):
        self.client = BybitClient()
        self.ta_pool = ThreadPoolExecutor(max_workers=4)
        self.analyst = GeminiAnalyst()
        self.state_mgr = StateManager()
        self.trader = PaperTrader(self.state_mgr)
        self.console = Console()
        self.snapshots: dict[str, MarketSnapshot] = {
            s: MarketSnapshot(symbol=s) for s in settings.symbols
        }

    def render(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body", ratio=2),
            Layout(name="footer", size=10),
        )

        # Header
        eq_color = "green" if self.trader.balance >= settings.trader.initial_balance else "red"
        header_content = f"[bold white]WhaleBot Pro[/] | [cyan]Model: {settings.gemini_model_name}[/] | Balance: [{eq_color}]${self.trader.balance:,.2f}[/]"
        layout["header"].update(Panel(header_content, style="blue"))

        # Market Table
        table = Table(expand=True, box=box.SIMPLE_HEAD)
        table.add_column("Sym")
        table.add_column("Price", justify="right")
        table.add_column("Trend", justify="center")
        table.add_column("RSI/Imb")
        table.add_column("AI Signal")
        table.add_column("Latency")

        for s in settings.symbols:
            snap = self.snapshots[s]
            if snap.price == 0:
                table.add_row(s, "Loading...", "", "", "", "")
                continue

            ind = snap.indicators
            trend_c = "green" if ind.trend == "BULL" else "red" if ind.trend == "BEAR" else "yellow"

            sig_str = "-"
            if snap.analysis and snap.analysis.action != "HOLD":
                ac_color = "green" if snap.analysis.action == "BUY" else "red"
                sig_str = f"[{ac_color}]{snap.analysis.action} ({snap.analysis.confidence*100:.0f}%)[/]"

            table.add_row(
                f"[bold]{s}[/]",
                f"${snap.price:,.2f}",
                f"[{trend_c}]{ind.trend}[/]",
                f"{ind.rsi:.0f} / {ind.ob_imbalance:+.2f}",
                sig_str,
                f"{snap.latency_ms:.0f}ms",
            )
        layout["body"].update(Panel(table, title="Market Watch"))

        # Portfolio/History
        pos_text = Text()
        if not self.trader.positions:
            pos_text.append("No open positions.", style="dim")
        else:
            for s, p in self.trader.positions.items():
                snap = self.snapshots[s]
                # Approx unrealized PnL
                curr_price = snap.price
                if curr_price > 0:
                    diff = (curr_price - p["entry_price"]) if p["side"] == "BUY" else (p["entry_price"] - curr_price)
                    upnl = diff * p["qty"]
                    c = "green" if upnl >= 0 else "red"
                    pos_text.append(f"{s} {p['side']} | PnL: ")
                    pos_text.append(f"${upnl:.2f}\n", style=c)

        layout["footer"].update(Panel(pos_text, title="Portfolio"))
        return layout

    async def cycle(self):
        """Main data processing cycle."""
        await self.client.start()

        while True:
            try:
                # 1. Fetch Data (Concurrent)
                tasks = [self.client.get_market_data(s) for s in settings.symbols]
                results = await asyncio.gather(*tasks)

                loop = asyncio.get_running_loop()

                for symbol, res in zip(settings.symbols, results):
                    df, ob, tick, lat = res
                    if df.empty: continue

                    # 2. Technical Analysis (Offloaded)
                    # We use run_in_executor to prevent Pandas TA from blocking the async loop
                    indicators = await loop.run_in_executor(self.ta_pool, TechnicalAnalyzer.compute, df, ob)

                    snap = self.snapshots[symbol]
                    snap.price = Decimal(str(tick.get("lastPrice", 0)))
                    snap.indicators = indicators
                    snap.latency_ms = lat
                    snap.last_updated = time.time()

                    # 3. AI Analysis (Rate Limited & Conditional)
                    # Trigger AI if technicals look interesting or enough time passed
                    is_interesting = (indicators.rsi < 30 or indicators.rsi > 70) and abs(indicators.ob_imbalance) > 0.15
                    time_passed = (time.time() - snap.last_ai_trigger) > settings.ai_cooldown_seconds

                    if is_interesting and time_passed:
                        snap.analysis = await self.analyst.analyze(symbol, indicators)
                        snap.last_ai_trigger = time.time()

                    # 4. Trading Logic
                    await self.trader.process_signal(snap)

                # Sleep slightly to prevent loop burning CPU
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Cycle Error: {e}")
                await asyncio.sleep(5)

    async def ui_loop(self, live: Live):
        """Decoupled UI updater."""
        while True:
            live.update(self.render())
            await asyncio.sleep(0.5)

    async def run(self):
        console.clear()

        # Create the Live context
        with Live(self.render(), refresh_per_second=4, screen=True) as live:
            # Run logic and UI concurrently
            await asyncio.gather(
                self.cycle(),
                self.ui_loop(live),
            )

    async def shutdown(self):
        await self.client.stop()
        self.ta_pool.shutdown(wait=False)
        logger.info("Shutdown complete.")

if __name__ == "__main__":
    bot = WhaleBotPro()
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        asyncio.run(bot.shutdown())
        print("Exited cleanly.")
    except Exception as e:
        print(f"Fatal Error: {e}")
