import asyncio
import hashlib
import hmac
import json
import os
import time
import urllib.parse
from collections import deque
from dataclasses import dataclass
from dataclasses import field
from decimal import ROUND_DOWN
from decimal import Decimal
from decimal import InvalidOperation
from decimal import getcontext
from typing import Any

import aiohttp
import numpy as np
from dotenv import load_dotenv
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Arcane precision for financial sorcery
getcontext().prec = 28

# Unveil credentials from the hidden vault
load_dotenv()
API_KEY = os.getenv("BYBIT_API_KEY", "")
API_SECRET = os.getenv("BYBIT_API_SECRET", "")
IS_TESTNET = os.getenv("BYBIT_TESTNET", "false").lower() == "true"

@dataclass(slots=True)
class ScalperConfig:
    symbol: str = "BCHUSDT"
    category: str = "linear"
    leverage: int = 15
    max_latency_ms: int = 400
    risk_per_trade_usdt: Decimal = Decimal("5.0")
    tp_mult: Decimal = Decimal("2.1")
    sl_mult: Decimal = Decimal("1.2")
    ts_distance: Decimal = Decimal("0.8") # Trailing stop distance in ATR units
    cooldown_sec: int = 15
    warmup_candles: int = 60
    kline_interval: str = "1"
    fisher_threshold: float = 1.1
    obi_threshold: float = 0.35

@dataclass(slots=True)
class ScalperState:
    config: ScalperConfig
    balance: Decimal = Decimal("0")
    equity: Decimal = Decimal("0")
    available: Decimal = Decimal("0")
    initial_equity: Decimal = Decimal("0")
    daily_pnl: Decimal = Decimal("0")

    price: Decimal = Decimal("0")
    bid: Decimal = Decimal("0")
    ask: Decimal = Decimal("0")
    obi: float = 0.0
    ema_fast: Decimal = Decimal("0")
    ema_slow: Decimal = Decimal("0")
    atr: float = 0.0
    fisher: float = 0.0
    fisher_signal: float = 0.0
    ohlc: deque[tuple[float, float, float, float, float]] = field(default_factory=lambda: deque(maxlen=300))

    price_prec: int = 2
    qty_step: Decimal = Decimal("0.01")
    min_qty: Decimal = Decimal("0.01")

    trade_count: int = 0
    wins: int = 0
    latency_ms: int = 0
    active: bool = False
    side: str = "HOLD"
    qty: Decimal = Decimal("0")
    entry_price: Decimal = Decimal("0")
    upnl: Decimal = Decimal("0")
    last_trade_ts: float = 0.0

    logs: deque[str] = field(default_factory=lambda: deque(maxlen=25))
    ready: bool = False
    local_bids: dict[Decimal, Decimal] = field(default_factory=dict)
    local_asks: dict[Decimal, Decimal] = field(default_factory=dict)

    def log(self, msg: str, level: str = "info"):
        ts = time.strftime("%H:%M:%S")
        prefix = {
            "debug": "[dim cyan]DEBUG[/]", "info": "[white]INFO[/]",
            "signal": "[bold yellow]SIGNAL[/]", "entry": "[bold green]ENTRY[/]",
            "exit": "[bold magenta]EXIT[/]", "warn": "[bold yellow]WARN[/]", "error": "[bold red]ERROR[/]"
        }.get(level, "[white]INFO[/]")
        self.logs.append(f"[dim]{ts}[/] {prefix} {msg}")

# =========================
# BYBIT V5.7 REINFORCED ENGINE
# =========================

def safe_decimal(value: Any, default: str = "0") -> Decimal:
    if value is None or value == "": return Decimal(default)
    try: return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError): return Decimal(default)

class BybitFlux:
    def __init__(self, state: ScalperState):
        self.state = state
        self.cfg = state.config
        self.base = "https://api-testnet.bybit.com" if IS_TESTNET else "https://api.bybit.com"
        self.ws_pub = "wss://stream.bybit.com/v5/public/linear"
        self.ws_priv = "wss://stream.bybit.com/v5/private"
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12))
        return self

    async def __aexit__(self, *args):
        if self.session: await self.session.close()

    def _sign(self, payload: str, ts: str) -> str:
        param_str = ts + API_KEY + "5000" + payload
        return hmac.new(API_SECRET.encode(), param_str.encode(), hashlib.sha256).hexdigest()

    async def request(self, method: str, path: str, params: dict = None) -> dict:
        params = params or {}
        ts = str(int(time.time() * 1000))
        if method == "GET":
            query = urllib.parse.urlencode(sorted(params.items()))
            payload, url = query, f"{self.base}{path}?{query}"
        else:
            payload = json.dumps(params, separators=(",", ":"))
            url = f"{self.base}{path}"

        headers = {
            "X-BAPI-API-KEY": API_KEY, "X-BAPI-SIGN": self._sign(payload, ts),
            "X-BAPI-TIMESTAMP": ts, "X-BAPI-RECV-WINDOW": "5000", "Content-Type": "application/json"
        }
        try:
            async with self.session.request(method, url, headers=headers, data=None if method=="GET" else payload) as r:
                return await r.json()
        except Exception as e:
            self.state.log(f"Request Error: {e}", "error")
            return {"retCode": -1}

    async def setup_market_data(self):
        self.state.log("Syncing instrument runes...", "info")
        resp = await self.request("GET", "/v5/market/instruments-info", {"category": self.cfg.category, "symbol": self.cfg.symbol})
        if resp.get("retCode") == 0:
            info = resp["result"]["list"][0]
            tick = Decimal(info["priceFilter"]["tickSize"])
            self.state.price_prec = abs(tick.normalize().as_tuple().exponent)
            self.state.qty_step = Decimal(info["lotSizeFilter"]["qtyStep"])
            self.state.min_qty = Decimal(info["lotSizeFilter"]["minOrderQty"])

        # Initial Leverage Lock
        await self.request("POST", "/v5/position/set-leverage", {
            "category": self.cfg.category, "symbol": self.cfg.symbol,
            "buyLeverage": str(self.cfg.leverage), "sellLeverage": str(self.cfg.leverage)
        })

    async def update_wallet(self):
        resp = await self.request("GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED"})
        if resp.get("retCode") == 0:
            acc = resp["result"]["list"][0]
            self.state.equity = safe_decimal(acc.get("totalEquity"))
            self.state.available = safe_decimal(acc.get("totalAvailableBalance"))
            if self.state.initial_equity == 0: self.state.initial_equity = self.state.equity
            self.state.daily_pnl = self.state.equity - self.state.initial_equity

    async def place_order(self, side: str, qty: Decimal, tp: Decimal, sl: Decimal, ts_dist: Decimal) -> bool:
        self.state.log(f"Summoning {side} | Qty: {qty}", "entry")
        params = {
            "category": self.cfg.category, "symbol": self.cfg.symbol,
            "side": side, "orderType": "Market",
            "qty": str(qty.quantize(self.state.qty_step, rounding=ROUND_DOWN)),
            "takeProfit": str(tp), "stopLoss": str(sl),
            "tpTriggerBy": "LastPrice", "slTriggerBy": "LastPrice"
        }
        resp = await self.request("POST", "/v5/order/create", params)
        if resp.get("retCode") == 0:
            # Engaging native trailing stop
            await self.request("POST", "/v5/position/trading-stop", {
                "category": self.cfg.category, "symbol": self.cfg.symbol,
                "trailingStop": str(ts_dist.quantize(Decimal(f"1e-{self.state.price_prec}"), rounding=ROUND_DOWN)),
                "positionIdx": 0
            })
            return True
        return False

    def _calc_obi(self):
        """Enhanced weighted OBI calculation"""
        bids = sorted(self.state.local_bids.items(), reverse=True)[:15]
        asks = sorted(self.state.local_asks.items())[:15]

        weighted_b = sum(float(q) * (1 / (i + 1)) for i, (_, q) in enumerate(bids))
        weighted_a = sum(float(q) * (1 / (i + 1)) for i, (_, q) in enumerate(asks))

        self.state.obi = (weighted_b - weighted_a) / (weighted_b + weighted_a + 1e-9)

    def _update_indicators(self):
        if len(self.state.ohlc) < 20: return
        c = np.array([x[3] for x in self.state.ohlc])
        h, l = np.array([x[1] for x in self.state.ohlc]), np.array([x[2] for x in self.state.ohlc])

        # Trend EMAs
        self.state.ema_fast = Decimal(str(np.mean(c[-20:])))
        self.state.ema_slow = Decimal(str(np.mean(c[-50:])))

        # Fisher Transform Calculation
        # $$y = 0.5 \ln \left( \frac{1 + x}{1 - x} \right)$$
        win = c[-10:]
        mn, mx = np.min(win), np.max(win) + 1e-9
        val = np.clip(0.66 * ((c[-1] - mn) / (mx - mn) - 0.5), -0.99, 0.99)
        fish = 0.5 * np.log((1 + val) / (1 - val))
        self.state.fisher_signal = (0.25 * fish) + (0.75 * self.state.fisher_signal)
        self.state.fisher = fish

        tr = np.maximum(h[1:] - l[1:], np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1]))
        self.state.atr = float(np.mean(tr[-14:]))

        if not self.state.ready and len(self.state.ohlc) >= self.cfg.warmup_candles:
            self.state.ready = True
            self.state.log("Oracles awakened.", "info")

    async def strategy_brain(self):
        while True:
            await asyncio.sleep(0.5)
            if not self.state.ready or self.state.active: continue

            now = time.time()
            if now - self.state.last_trade_ts < self.cfg.cooldown_sec: continue
            if self.state.atr <= 0: continue

            qty = (self.cfg.risk_per_trade_usdt * self.cfg.leverage / self.state.price).quantize(self.state.qty_step, rounding=ROUND_DOWN)
            qty = max(qty, self.state.min_qty)

            # Signal Logic: Fisher Momentum + OBI Pressure + Trend Filter
            long_cond = (self.state.fisher_signal > self.cfg.fisher_threshold and
                         self.state.obi > self.cfg.obi_threshold and
                         self.state.price > self.state.ema_fast)

            short_cond = (self.state.fisher_signal < -self.cfg.fisher_threshold and
                          self.state.obi < -self.cfg.obi_threshold and
                          self.state.price < self.state.ema_fast)

            if long_cond:
                tp = self.state.price + Decimal(str(self.state.atr * float(self.cfg.tp_mult)))
                sl = self.state.price - Decimal(str(self.state.atr * float(self.cfg.sl_mult)))
                ts_dist = Decimal(str(self.state.atr * float(self.cfg.ts_distance)))
                if await self.place_order("Buy", qty, tp, sl, ts_dist):
                    self.state.last_trade_ts, self.state.trade_count = now, self.state.trade_count + 1
            elif short_cond:
                tp = self.state.price - Decimal(str(self.state.atr * float(self.cfg.tp_mult)))
                sl = self.state.price + Decimal(str(self.state.atr * float(self.cfg.sl_mult)))
                ts_dist = Decimal(str(self.state.atr * float(self.cfg.ts_distance)))
                if await self.place_order("Sell", qty, tp, sl, ts_dist):
                    self.state.last_trade_ts, self.state.trade_count = now, self.state.trade_count + 1

    async def run_public_ws(self, stop: asyncio.Event):
        async with self.session.ws_connect(self.ws_pub) as ws:
            await ws.send_json({"op": "subscribe", "args": [f"tickers.{self.cfg.symbol}", f"orderbook.50.{self.cfg.symbol}", f"kline.{self.cfg.kline_interval}.{self.cfg.symbol}"]})
            async for msg in ws:
                if stop.is_set(): break
                d = json.loads(msg.data)
                topic = d.get("topic", "")
                if "tickers" in topic:
                    res = d["data"]
                    if "lastPrice" in res: self.state.price = safe_decimal(res["lastPrice"])
                    if "bid1Price" in res: self.state.bid = safe_decimal(res["bid1Price"])
                    if "ask1Price" in res: self.state.ask = safe_decimal(res["ask1Price"])
                    self.state.latency_ms = int(time.time() * 1000) - d.get("ts", 0)
                elif "orderbook" in topic:
                    data = d["data"]
                    if d["type"] == "snapshot":
                        self.state.local_bids.clear(); self.state.local_asks.clear()
                    for price, qty in data.get("b", []):
                        if Decimal(qty) == 0: self.state.local_bids.pop(Decimal(price), None)
                        else: self.state.local_bids[Decimal(price)] = Decimal(qty)
                    for price, qty in data.get("a", []):
                        if Decimal(qty) == 0: self.state.local_asks.pop(Decimal(price), None)
                        else: self.state.local_asks[Decimal(price)] = Decimal(qty)
                    self._calc_obi()
                elif "kline" in topic:
                    k = d["data"][0]
                    if k.get("confirm"):
                        # WebSocket kline is a DICT
                        self.state.ohlc.append((float(k["open"]), float(k["high"]), float(k["low"]), float(k["close"]), float(k["volume"])))
                        self._update_indicators()

    async def run_private_ws(self, stop: asyncio.Event):
        async with self.session.ws_connect(self.ws_priv) as ws:
            ts = str(int(time.time() * 1000 + 10000))
            sig = hmac.new(API_SECRET.encode(), f"GET/realtime{ts}".encode(), hashlib.sha256).hexdigest()
            await ws.send_json({"op": "auth", "args": [API_KEY, ts, sig]})
            await ws.send_json({"op": "subscribe", "args": ["position", "wallet"]})
            async for msg in ws:
                if stop.is_set(): break
                d = json.loads(msg.data)
                topic = d.get("topic", "")
                if topic == "position":
                    for p in d.get("data", []):
                        if p["symbol"] == self.cfg.symbol:
                            old_active = self.state.active
                            self.state.qty = safe_decimal(p["size"])
                            self.state.active = self.state.qty > 0
                            self.state.side = p["side"] if self.state.active else "HOLD"
                            self.state.entry_price = safe_decimal(p["avgPrice"])
                            self.state.upnl = safe_decimal(p["unrealisedPnl"])
                            if not old_active and self.state.active: self.state.log(f"Position Active: {self.state.side}", "entry")
                            if old_active and not self.state.active:
                                if self.state.upnl > 0: self.state.wins += 1
                                self.state.log("Position Closed.", "exit")
                elif topic == "wallet":
                    acc = d["data"][0]
                    self.state.equity = safe_decimal(acc.get("totalEquity"))
                    self.state.available = safe_decimal(acc.get("totalAvailableBalance"))

# =========================
# ENCHANTED UI REALM
# =========================

def build_ui(s: ScalperState) -> Layout:
    layout = Layout()
    layout.split_column(Layout(name="top", size=3), Layout(name="mid"), Layout(name="bot", size=10))
    layout["mid"].split_row(Layout(name="ora"), Layout(name="tac"))

    pnl_style = "green" if s.daily_pnl >= 0 else "red"
    header = Text.from_markup(f"[bold cyan]BCH ULTRA V5.7[/] | Latency: {s.latency_ms}ms | PnL: [{pnl_style}]{s.daily_pnl:+.2f} USDT[/] | Trades: {s.trade_count}")
    layout["top"].update(Panel(header, border_style="bright_blue"))

    ora = Table.grid(expand=True)
    ora.add_row("Price", f"[bold yellow]{s.price:.{s.price_prec}f}[/]")
    ora.add_row("Trend EMA", f"[cyan]{s.ema_fast:.2f}[/]")
    ora.add_row("Fisher", f"[magenta]{s.fisher_signal:+.3f}[/]")
    ora.add_row("OBI", f"[{'green' if s.obi>0 else 'red'}]{s.obi:+.2%}[/]")
    layout["ora"].update(Panel(ora, title="[bold cyan]Micro-Oracle[/]", border_style="cyan"))

    tac = Table.grid(expand=True)
    if s.active:
        tac.add_row("Position", f"[bold {'green' if s.side=='Buy' else 'red'}]{s.side} {s.qty}[/]")
        tac.add_row("uPnL", f"[{'green' if s.upnl>0 else 'red'}]{s.upnl:+.4f}[/]")
    else:
        tac.add_row("Status", "[dim cyan]Waiting for alignment...[/]")
        tac.add_row("Available", f"[green]{s.available:.2f} USDT[/]")
    layout["tac"].update(Panel(tac, title="[bold magenta]Tactical Realm[/]", border_style="magenta"))

    layout["bot"].update(Panel("\n".join(s.logs), title="[bold white]Chronicles[/]"))
    return layout

async def main():
    state = ScalperState(ScalperConfig())
    async with BybitFlux(state) as flux:
        await flux.setup_market_data()
        await flux.update_wallet()

        # FIX: Corrected historical K-line indexing (REST returns a list of lists)
        hist = await flux.request("GET", "/v5/market/kline", {"category": "linear", "symbol": state.config.symbol, "interval": "1", "limit": "100"})
        if hist.get("retCode") == 0:
            for k in reversed(hist["result"]["list"]):
                # k[1]: Open, k[2]: High, k[3]: Low, k[4]: Close, k[5]: Vol
                state.ohlc.append((float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])))
            flux._update_indicators()

        stop = asyncio.Event()
        with Live(build_ui(state), refresh_per_second=4, screen=True) as live:
            tasks = [asyncio.create_task(flux.run_public_ws(stop)), asyncio.create_task(flux.run_private_ws(stop)), asyncio.create_task(flux.strategy_brain())]
            try:
                while True:
                    live.update(build_ui(state)); await asyncio.sleep(0.25)
            except KeyboardInterrupt:
                stop.set()
                await asyncio.gather(*tasks, return_exceptions=True)

if __name__ == "__main__":
    asyncio.run(main())
