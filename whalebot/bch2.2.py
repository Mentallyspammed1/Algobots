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
from decimal import getcontext

import aiohttp
import numpy as np
from dotenv import load_dotenv
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Global Precision
getcontext().prec = 28
load_dotenv()

API_KEY = os.getenv("BYBIT_API_KEY", "")
API_SECRET = os.getenv("BYBIT_API_SECRET", "")
IS_TESTNET = os.getenv("BYBIT_TESTNET", "false").lower() == "true"

@dataclass(slots=True)
class ScalperConfig:
    symbol: str = "BCHUSDT"
    category: str = "linear"
    leverage: int = 20

    # --- Risk Profile ---
    risk_per_trade_usdt: Decimal = Decimal("5.0")
    tp_atr_mult: Decimal = Decimal("2.5")
    sl_atr_mult: Decimal = Decimal("1.2")
    be_trigger_mult: Decimal = Decimal("1.0") # Move to Break-Even at 1:1 R/R

    # --- Scoring Thresholds ---
    min_alpha_score: float = 75.0   # Score required to enter (0-100)
    trend_ema_period: int = 200
    vol_lookback: int = 30

    # --- WebSocket / Timing ---
    cooldown_sec: int = 10
    ws_heartbeat: int = 20
    kline_interval: str = "1"

@dataclass(slots=True)
class ScalperState:
    config: ScalperConfig
    # Financials
    equity: Decimal = Decimal("0")
    available: Decimal = Decimal("0")
    initial_equity: Decimal = Decimal("0")
    daily_pnl: Decimal = Decimal("0")

    # Market Flux
    price: Decimal = Decimal("0")
    bid: Decimal = Decimal("0")
    ask: Decimal = Decimal("0")
    obi_score: float = 0.0          # Weighted Imbalance
    ema_trend: Decimal = Decimal("0")
    atr: float = 0.0
    vol_ratio: float = 0.0          # Current Vol / Avg Vol
    fisher: float = 0.0
    fisher_sig: float = 0.0
    alpha_score: float = 0.0        # Combined Signal Strength

    ohlc: deque[tuple[float, float, float, float, float]] = field(default_factory=lambda: deque(maxlen=300))

    # Position
    active: bool = False
    side: str = "HOLD"
    qty: Decimal = Decimal("0")
    entry_p: Decimal = Decimal("0")
    upnl: Decimal = Decimal("0")
    be_active: bool = False         # Has break-even been set?

    # Meta
    price_prec: int = 2
    qty_step: Decimal = Decimal("0.01")
    min_qty: Decimal = Decimal("0.01")
    trade_count: int = 0
    wins: int = 0
    latency: int = 0
    last_trade_ts: float = 0.0
    logs: deque[str] = field(default_factory=lambda: deque(maxlen=20))
    ready: bool = False

    def log(self, msg: str, style: str = "white"):
        ts = time.strftime("%H:%M:%S")
        self.logs.append(f"[dim]{ts}[/] [{style}]{msg}[/]")

class BybitApex:
    def __init__(self, state: ScalperState):
        self.state = state
        self.cfg = state.config
        self.base = "https://api-testnet.bybit.com" if IS_TESTNET else "https://api.bybit.com"
        self.ws_pub = "wss://stream.bybit.com/v5/public/linear"
        self.ws_priv = "wss://stream.bybit.com/v5/private"
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return self

    async def __aexit__(self, *args):
        if self.session: await self.session.close()

    async def api_req(self, method: str, path: str, params: dict = None) -> dict:
        params = params or {}
        ts = str(int(time.time() * 1000))
        payload = urllib.parse.urlencode(sorted(params.items())) if method == "GET" else json.dumps(params)
        sign = hmac.new(API_SECRET.encode(), (ts + API_KEY + "5000" + payload).encode(), hashlib.sha256).hexdigest()

        headers = {"X-BAPI-API-KEY": API_KEY, "X-BAPI-SIGN": sign, "X-BAPI-TIMESTAMP": ts, "X-BAPI-RECV-WINDOW": "5000", "Content-Type": "application/json"}
        url = f"{self.base}{path}{'?' + payload if method == 'GET' else ''}"

        try:
            async with self.session.request(method, url, headers=headers, data=None if method=="GET" else payload) as r:
                return await r.json()
        except: return {"retCode": -1}

    async def bootstrap(self):
        r = await self.api_req("GET", "/v5/market/instruments-info", {"category": self.cfg.category, "symbol": self.cfg.symbol})
        if r.get("retCode") == 0:
            i = r["result"]["list"][0]
            self.state.price_prec = abs(Decimal(i["priceFilter"]["tickSize"]).normalize().as_tuple().exponent)
            self.state.qty_step = Decimal(i["lotSizeFilter"]["qtyStep"])
            self.state.min_qty = Decimal(i["lotSizeFilter"]["minOrderQty"])

        await self.api_req("POST", "/v5/position/set-leverage", {
            "category": self.cfg.category, "symbol": self.cfg.symbol,
            "buyLeverage": str(self.cfg.leverage), "sellLeverage": str(self.cfg.leverage)
        })
        self.state.log(f"Apex System Primed: {self.cfg.symbol}", "bold green")

    def _update_indicators(self, live_p: float = None):
        if len(self.state.ohlc) < 50: return

        c_list = [x[3] for x in self.state.ohlc]
        if live_p: c_list[-1] = live_p

        c = np.array(c_list)
        h = np.array([x[1] for x in self.state.ohlc])
        l = np.array([x[2] for x in self.state.ohlc])
        v = np.array([x[4] for x in self.state.ohlc])

        # 1. ATR (Volatility)
        tr = np.maximum(h[1:] - l[1:], np.abs(h[1:] - c[:-1]))
        self.state.atr = float(np.mean(tr[-14:]))

        # 2. Fisher Momentum
        win = c[-10:]
        mn, mx = np.min(win), np.max(win) + 1e-9
        norm = np.clip(0.66 * ((c[-1] - mn) / (mx - mn) - 0.5), -0.99, 0.99)
        self.state.fisher = 0.5 * np.log((1 + norm) / (1 - norm))
        self.state.fisher_sig = (0.15 * self.state.fisher) + (0.85 * self.state.fisher_sig)

        # 3. EMA Trend
        alpha = 2 / (self.cfg.trend_ema_period + 1)
        if self.state.ema_trend == 0: self.state.ema_trend = Decimal(str(c.mean()))
        self.state.ema_trend = Decimal(str(alpha * c[-1] + (1 - alpha) * float(self.state.ema_trend)))

        # 4. Volume Profile
        avg_v = np.mean(v[-self.cfg.vol_lookback:])
        self.state.vol_ratio = v[-1] / avg_v if avg_v > 0 else 1.0

        # --- ALPHA SCORING ENGINE ---
        score = 0.0
        # Fisher Momentum Component (max 40 pts)
        score += min(40, abs(self.state.fisher) * 25)
        # Trend Alignment Component (max 30 pts)
        trend_align = (self.state.price > self.state.ema_trend and self.state.fisher > 0) or \
                      (self.state.price < self.state.ema_trend and self.state.fisher < 0)
        if trend_align: score += 30
        # OBI Imbalance Component (max 30 pts)
        score += min(30, abs(self.state.obi_score) * 50)

        self.state.alpha_score = score
        self.state.ready = len(self.state.ohlc) >= 50

    async def strike(self, side: str):
        sl_dist = Decimal(str(self.state.atr * float(self.cfg.sl_atr_mult)))
        if sl_dist <= 0: return

        qty = (self.cfg.risk_per_trade_usdt / sl_dist).quantize(self.state.qty_step, rounding=ROUND_DOWN)
        qty = max(qty, self.state.min_qty)

        tp = self.state.price + (sl_dist * self.cfg.tp_atr_mult) if side == "Buy" else self.state.price - (sl_dist * self.cfg.tp_atr_mult)
        sl = self.state.price - sl_dist if side == "Buy" else self.state.price + sl_dist

        self.state.log(f"Striking {side} | Alpha: {self.state.alpha_score:.1f}", "bold cyan")

        res = await self.api_req("POST", "/v5/order/create", {
            "category": self.cfg.category, "symbol": self.cfg.symbol,
            "side": side, "orderType": "Market", "qty": str(qty),
            "takeProfit": f"{tp:.{self.state.price_prec}f}",
            "stopLoss": f"{sl:.{self.state.price_prec}f}",
            "tpTriggerBy": "LastPrice", "slTriggerBy": "LastPrice"
        })

        if res.get("retCode") == 0:
            self.state.last_trade_ts = time.time()
            self.state.trade_count += 1
            self.state.be_active = False

    async def brain_loop(self, stop: asyncio.Event):
        while not stop.is_set():
            await asyncio.sleep(0.4)
            if not self.state.ready or self.state.price <= 0: continue

            # 1. Manage Active Position (Break-even Logic)
            if self.state.active and not self.state.be_active:
                pnl_dist = abs(self.state.price - self.state.entry_p)
                trigger_dist = Decimal(str(self.state.atr * float(self.cfg.be_trigger_mult)))

                if pnl_dist >= trigger_dist:
                    # Move SL to Entry + tiny offset for fees
                    be_price = self.state.entry_p * Decimal("1.0005") if self.state.side == "Buy" else self.state.entry_p * Decimal("0.9995")
                    res = await self.api_req("POST", "/v5/position/trading-stop", {
                        "category": self.cfg.category, "symbol": self.cfg.symbol,
                        "stopLoss": f"{be_price:.{self.state.price_prec}f}", "positionIdx": 0
                    })
                    if res.get("retCode") == 0:
                        self.state.be_active = True
                        self.state.log("Shields Up: SL moved to Break-even", "yellow")

            # 2. Hunt for Entry
            if not self.state.active and (time.time() - self.state.last_trade_ts > self.cfg.cooldown_sec):
                if self.state.alpha_score >= self.cfg.min_alpha_score:
                    # Direction check
                    if self.state.fisher > self.state.fisher_sig:
                        if self.state.price > self.state.ema_trend and self.state.obi_score > 0.2:
                            await self.strike("Buy")
                    elif self.state.fisher < self.state.fisher_sig:
                        if self.state.price < self.state.ema_trend and self.state.obi_score < -0.2:
                            await self.strike("Sell")

    async def ws_public(self, stop: asyncio.Event):
        async with self.session.ws_connect(self.ws_pub) as ws:
            await ws.send_json({"op": "subscribe", "args": [f"tickers.{self.cfg.symbol}", f"orderbook.50.{self.cfg.symbol}", f"kline.{self.cfg.kline_interval}.{self.cfg.symbol}"]})
            async for msg in ws:
                if stop.is_set(): break
                data = json.loads(msg.data)
                topic = data.get("topic", "")

                if "tickers" in topic:
                    d = data["data"]
                    if "lastPrice" in d: self.state.price = Decimal(d["lastPrice"])
                    if "bid1Price" in d: self.state.bid = Decimal(d["bid1Price"])
                    if "ask1Price" in d: self.state.ask = Decimal(d["ask1Price"])
                    self.state.latency = max(0, int(time.time() * 1000) - data.get("ts", 0))
                    self._update_indicators(float(self.state.price))

                elif "orderbook" in topic:
                    d = data["data"]
                    # Inverse Distance Weighting: Closer to spread = More weight
                    bids = d.get("b", [])[:20]
                    asks = d.get("a", [])[:20]

                    w_bid = sum(float(q) / (i + 1) for i, (_, q) in enumerate(bids))
                    w_ask = sum(float(q) / (i + 1) for i, (_, q) in enumerate(asks))
                    self.state.obi_score = (w_bid - w_ask) / (w_bid + w_ask + 1e-9)

                elif "kline" in topic:
                    k = data["data"][0]
                    if k.get("confirm"):
                        self.state.ohlc.append((float(k["open"]), float(k["high"]), float(k["low"]), float(k["close"]), float(k["volume"])))

    async def ws_private(self, stop: asyncio.Event):
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
                            was_active = self.state.active
                            self.state.qty = Decimal(p["size"])
                            self.state.active = self.state.qty > 0
                            self.state.side = p["side"] if self.state.active else "HOLD"
                            self.state.entry_p = Decimal(p["avgPrice"])
                            self.state.upnl = Decimal(p["unrealisedPnl"])
                            if was_active and not self.state.active:
                                self.state.log(f"Trade Closed. Result: {self.state.upnl:+.2f}", "green" if self.state.upnl>0 else "red")
                                if self.state.upnl > 0: self.state.wins += 1
                elif topic == "wallet":
                    acc = d["data"][0]
                    self.state.equity = Decimal(acc.get("totalEquity", "0"))
                    self.state.available = Decimal(acc.get("totalAvailableBalance", "0"))
                    if self.state.initial_equity == 0: self.state.initial_equity = self.state.equity
                    self.state.daily_pnl = self.state.equity - self.state.initial_equity

# --- UI DASHBOARD ---
def build_ui(s: ScalperState) -> Layout:
    l = Layout()
    l.split_column(Layout(name="top", size=3), Layout(name="mid"), Layout(name="bot", size=10))
    l["mid"].split_row(Layout(name="ora"), Layout(name="tac"))

    pnl_s = "bright_green" if s.daily_pnl >= 0 else "bright_red"
    header = f"[bold cyan]BCH APEX V7.0[/] | [white]Equity:[/][yellow]{s.equity:.2f}[/] | [white]PnL:[/][{pnl_s}]{s.daily_pnl:+.2f}[/] | [white]WR:[/]{(s.wins/max(1,s.trade_count)*100):.1f}% | [white]Lat:[/]{s.latency}ms"
    l["top"].update(Panel(Text.from_markup(header, justify="center"), border_style="bright_blue"))

    ora = Table.grid(expand=True)
    ora.add_row("Price", f"[bold yellow]{s.price:.{s.price_prec}f}[/]")
    ora.add_row("Trend", "[green]BULL[/]" if s.price > s.ema_trend else "[red]BEAR[/]")
    ora.add_row("Alpha Score", f"[bold magenta]{s.alpha_score:.1f}[/]")
    ora.add_row("Fisher", f"{s.fisher:+.2f}")
    ora.add_row("OBI Imbal", f"[{'green' if s.obi_score>0 else 'red'}]{s.obi_score:+.2%}[/]")
    l["ora"].update(Panel(ora, title="Alpha Oracle", border_style="cyan"))

    tac = Table.grid(expand=True)
    if s.active:
        tac.add_row("Position", f"[bold]{s.side} {s.qty}[/]")
        tac.add_row("uPnL", f"[{pnl_s}]{s.upnl:+.4f}[/]")
        tac.add_row("BreakEven", "[green]ACTIVE[/]" if s.be_active else "[dim]PENDING[/]")
    else:
        tac.add_row("Status", "[green]SEARCHING[/]" if s.ready else "[yellow]WARMING[/]")
        tac.add_row("Signals", f"Alpha at {int(s.alpha_score)}%")
    l["tac"].update(Panel(tac, title="Tactical Realm", border_style="magenta"))

    l["bot"].update(Panel("\n".join(list(s.logs)), title="System Log"))
    return l

async def main():
    state = ScalperState(ScalperConfig())
    async with BybitApex(state) as flux:
        await flux.bootstrap()

        hist = await flux.api_req("GET", "/v5/market/kline", {"category": "linear", "symbol": state.config.symbol, "interval": "1", "limit": "100"})
        if hist.get("retCode") == 0:
            for k in reversed(hist["result"]["list"]):
                state.ohlc.append((float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])))

        stop = asyncio.Event()
        with Live(build_ui(state), refresh_per_second=4, screen=True) as live:
            tasks = [asyncio.create_task(flux.ws_public(stop)), asyncio.create_task(flux.ws_private(stop)), asyncio.create_task(flux.brain_loop(stop))]
            try:
                while True:
                    live.update(build_ui(state))
                    await asyncio.sleep(0.25)
            except KeyboardInterrupt:
                stop.set()
                await asyncio.gather(*tasks, return_exceptions=True)

if __name__ == "__main__":
    asyncio.run(main())
