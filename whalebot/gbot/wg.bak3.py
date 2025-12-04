#!/usr/bin/env python3
import asyncio
import logging
import re
import time
from datetime import datetime

import aiohttp
import google.generativeai as genai
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


# --- Configuration ---
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gemini_api_key: str = Field(..., alias="GEMINI_API_KEY")
    bybit_base_url: str = "https://api.bybit.com"
    gemini_model_name: str = "gemini-2.5-flash-lite"

    symbols: list[str] = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT",
        "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "SUIUSDT",
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
    handlers=[logging.FileHandler("whalebot_debug.log", mode="w")],
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
    entry_zone: str | None = None
    stop_loss: float | None = None
    take_profit: float | None = None

    @field_validator("signal", mode="before")
    def normalize_signal(cls, v):
        return v.upper().strip()

class MarketSnapshot(BaseModel):
    symbol: str
    price: float = 0.0
    timestamp: datetime
    indicators: IndicatorData
    analysis: SignalAnalysis | None = None
    error: str | None = None
    last_updated: float = 0.0
    latency_ms: float = 0.0

# --- API Client ---

class BybitPublicClient:
    def __init__(self):
        self.base_url = settings.bybit_base_url
        self.session: aiohttp.ClientSession | None = None
        self.timeout = aiohttp.ClientTimeout(total=10)

    async def start(self):
        if not self.session:
            # Disable SSL verify for slight speed bump if safe, else keep default
            connector = aiohttp.TCPConnector(limit=20, ssl=False)
            self.session = aiohttp.ClientSession(
                headers={"User-Agent": "WhaleBot/2.1"},
                timeout=self.timeout,
                connector=connector,
            )

    async def close(self):
        if self.session:
            await self.session.close()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=4), retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)))
    async def fetch_data(self, symbol: str) -> tuple[pd.DataFrame, dict, dict, float]:
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
    def calculate(df: pd.DataFrame, orderbook: dict) -> IndicatorData:
        if df.empty or len(df) < 200:
            # Fail if we don't have enough data for EMA200
            return IndicatorData()

        # Helper to safely get scalar float
        def safe_float(val):
            return float(val) if np.isfinite(val) else 0.0

        close = df["close"].values
        high = df["high"].values
        low = df["low"].values
        volume = df["volume"].values

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
            bids = np.array(orderbook.get("b", []), dtype=float)
            asks = np.array(orderbook.get("a", []), dtype=float)
            if len(bids) > 0 and len(asks) > 0:
                bid_vol = np.sum(bids[:, 1])
                ask_vol = np.sum(asks[:, 1])
                total = bid_vol + ask_vol
                ind.flow_ob_imbalance = safe_float((bid_vol - ask_vol) / total) if total > 0 else 0.0

        opens = df["open"].values
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
        self.snapshots: dict[str, MarketSnapshot] = {
            s: MarketSnapshot(symbol=s, timestamp=datetime.now(), indicators=IndicatorData())
            for s in settings.symbols
        }

    def generate_table(self) -> Table:
        table = Table(
            show_header=True, header_style="bold white", box=box.ROUNDED,
            title=f"[bold cyan]WhaleBot AI[/bold cyan] | {settings.interval}m Interval",
            expand=True,
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
                f"{age:.0f}s",
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
            except Exception:
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
                latency_ms=latency,
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
                        style="white on blue",
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
