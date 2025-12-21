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
from colorama import Fore
from colorama import Style
from colorama import init
from dotenv import load_dotenv
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Initialize Chromatic Essence
init(autoreset=True)
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

    # --- Execution Sorcery ---
    risk_per_trade_usdt: Decimal = Decimal("5.0")
    tp_atr_mult: Decimal = Decimal("2.1")  # Faster take-profits for scalps
    sl_atr_mult: Decimal = Decimal("1.1")
    trailing_activation_atr: Decimal = Decimal("0.8")

    # --- Chronos Weaver Logic ---
    min_alpha_standard: float = 70.0
    alpha_ignition_boost: float = 55.0  # Lower threshold if OBI is extreme (>90%)
    vsi_threshold: float = 1.4         # Volume Surge Index threshold (1.4x normal)
    micro_ema_period: int = 9          # For micro-trend alignment
    macro_ema_period: int = 200

    # --- Technicals ---
    kline_interval: str = "1"
    cooldown_sec: int = 8              # Reduced for high-frequency opportunities

@dataclass(slots=True)
class ScalperState:
    config: ScalperConfig
    # Vault Stats
    equity: Decimal = Decimal("0")
    available: Decimal = Decimal("0")
    initial_equity: Decimal = Decimal("0")
    daily_pnl: Decimal = Decimal("0")

    # Market Pulse
    price: Decimal = Decimal("0")
    bid: Decimal = Decimal("0")
    ask: Decimal = Decimal("0")
    obi_score: float = 0.0
    ema_micro: Decimal = Decimal("0")
    ema_macro: Decimal = Decimal("0")
    atr: float = 0.0
    vsi: float = 1.0                # Volume Surge Index
    fisher: float = 0.0
    fisher_sig: float = 0.0
    alpha_score: float = 0.0
    tick_velocity: float = 0.0      # Ticks per second

    ohlc: deque[tuple[float, float, float, float, float]] = field(default_factory=lambda: deque(maxlen=300))
    tick_history: deque[float] = field(default_factory=lambda: deque(maxlen=20))

    # Position Matrix
    active: bool = False
    side: str = "HOLD"
    qty: Decimal = Decimal("0")
    entry_p: Decimal = Decimal("0")
    upnl: Decimal = Decimal("0")

    # Meta
    price_prec: int = 2
    qty_step: Decimal = Decimal("0.01")
    min_qty: Decimal = Decimal("0.01")
    trade_count: int = 0
    wins: int = 0
    latency: int = 0
    last_trade_ts: float = 0.0
    logs: deque[str] = field(default_factory=lambda: deque(maxlen=18))
    ready: bool = False

    def log(self, msg: str, style: str = "white"):
        ts = time.strftime("%H:%M:%S")
        self.logs.append(f"[dim]{ts}[/] [{style}]{msg}[/]")

class BybitChronos:
    def __init__(self, state: ScalperState):
        self.state = state
        self.cfg = state.config
        self.base = "https://api-testnet.bybit.com" if IS_TESTNET else "https://api.bybit.com"
        self.ws_pub = "wss://stream.bybit.com/v5/public/linear"
        self.ws_priv = "wss://stream.bybit.com/v5/private"
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        # Optimized for Termux / ARM64
        conn = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300, use_dns_cache=True)
        self.session = aiohttp.ClientSession(connector=conn, timeout=aiohttp.ClientTimeout(total=10))
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

    async def boot_ritual(self):
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
        self.state.log(f"Chronos Weaver Resonating: {self.cfg.symbol}", "bold cyan")

    def _channel_indicators(self, live_p: float = None):
        if len(self.state.ohlc) < 20: return

        c_list = [x[3] for x in self.state.ohlc]
        if live_p: c_list[-1] = live_p

        c = np.array(c_list)
        h = np.array([x[1] for x in self.state.ohlc])
        l = np.array([x[2] for x in self.state.ohlc])
        v = np.array([x[4] for x in self.state.ohlc])

        # 1. ATR (Volatility Flux)
        tr = np.maximum(h[1:] - l[1:], np.abs(h[1:] - c[:-1]))
        self.state.atr = float(np.mean(tr[-14:]))

        # 2. Fisher Momentum Pivot
        win = c[-10:]
        mn, mx = np.min(win), np.max(win) + 1e-9
        norm = np.clip(0.66 * ((c[-1] - mn) / (mx - mn) - 0.5), -0.99, 0.99)
        self.state.fisher = 0.5 * np.log((1 + norm) / (1 - norm))
        self.state.fisher_sig = (0.2 * self.state.fisher) + (0.8 * self.state.fisher_sig)

        # 3. Micro & Macro Trend
        def ema(data, period):
            alpha = 2 / (period + 1)
            res = data[0]
            for val in data[1:]: res = alpha * val + (1 - alpha) * res
            return res

        self.state.ema_micro = Decimal(str(ema(c[-self.cfg.micro_ema_period:], self.cfg.micro_ema_period)))
        self.state.ema_macro = Decimal(str(ema(c[-self.cfg.macro_ema_period:], self.cfg.macro_ema_period)))

        # 4. Volume Surge Index (VSI)
        avg_v = np.mean(v[-10:])
        self.state.vsi = v[-1] / avg_v if avg_v > 0 else 1.0

        # --- ALPHA CONFLUENCE ENGINE V8 ---
        score = 0.0
        # Fisher Strength (40%)
        score += min(40, abs(self.state.fisher) * 30)
        # OBI Imbalance (40%) - Weighted toward immediate book
        score += min(40, abs(self.state.obi_score) * 60)
        # Trend Confluence (20%)
        trend_aligned = (self.state.price > self.state.ema_macro and self.state.price > self.state.ema_micro) if self.state.fisher > 0 else \
                        (self.state.price < self.state.ema_macro and self.state.price < self.state.ema_micro)
        if trend_aligned: score += 20

        # Volume Intensity Bonus
        if self.state.vsi > self.cfg.vsi_threshold: score += 10

        self.state.alpha_score = score
        self.state.ready = len(self.state.ohlc) >= 50

    async def strike_fast(self, side: str):
        # Precise Sizing via ATR
        sl_dist = Decimal(str(self.state.atr * float(self.cfg.sl_atr_mult)))
        if sl_dist <= 0: return

        qty = (self.cfg.risk_per_trade_usdt / sl_dist).quantize(self.state.qty_step, rounding=ROUND_DOWN)
        qty = max(qty, self.state.min_qty)

        tp = self.state.price + (sl_dist * self.cfg.tp_atr_mult) if side == "Buy" else self.state.price - (sl_dist * self.cfg.tp_atr_mult)
        sl = self.state.price - sl_dist if side == "Buy" else self.state.price + sl_dist

        self.state.log(f"SUMMONING {side} | Alpha: {self.state.alpha_score:.1f}% | VSI: {self.state.vsi:.2f}", "bold green")

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

    async def weave_strategy(self, stop: asyncio.Event):
        while not stop.is_set():
            await asyncio.sleep(0.3) # Faster scan rate
            if not self.state.ready or self.state.price <= 0: continue
            if self.state.active: continue
            if time.time() - self.state.last_trade_ts < self.cfg.cooldown_sec: continue

            # DETERMINISTIC IGNITION: Lower threshold if OBI is extreme and VSI is high
            dynamic_threshold = self.cfg.min_alpha_standard
            if abs(self.state.obi_score) > 0.90 and self.state.vsi > 1.2:
                dynamic_threshold = self.cfg.alpha_ignition_boost
                self.state.log("Momentum Ignition Detected!", "magenta")

            if self.state.alpha_score >= dynamic_threshold:
                # Directional Filters
                if self.state.fisher > self.state.fisher_sig and self.state.obi_score > 0.25:
                    if self.state.price > self.state.ema_macro: # Trend Filter
                        await self.strike_fast("Buy")
                elif self.state.fisher < self.state.fisher_sig and self.state.obi_score < -0.25:
                    if self.state.price < self.state.ema_macro:
                        await self.strike_fast("Sell")

    async def ws_nexus(self, stop: asyncio.Event):
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

                    self.state.tick_history.append(time.time())
                    if len(self.state.tick_history) > 1:
                        self.state.tick_velocity = len(self.state.tick_history) / (self.state.tick_history[-1] - self.state.tick_history[0])

                    self.state.latency = max(0, int(time.time() * 1000) - data.get("ts", 0))
                    self._channel_indicators(float(self.state.price))

                elif "orderbook" in topic:
                    d = data["data"]
                    # Inverse Distance Linear Decay (V8)
                    bids, asks = d.get("b", [])[:25], d.get("a", [])[:25]
                    w_bid = sum(float(q) * (1 - (i/25)) for i, (_, q) in enumerate(bids))
                    w_ask = sum(float(q) * (1 - (i/25)) for i, (_, q) in enumerate(asks))
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
                            old_active = self.state.active
                            self.state.qty = Decimal(p["size"])
                            self.state.active = self.state.qty > 0
                            self.state.side = p["side"] if self.state.active else "HOLD"
                            self.state.entry_p = Decimal(p["avgPrice"])
                            self.state.upnl = Decimal(p["unrealisedPnl"])
                            if old_active and not self.state.active:
                                res_color = "green" if self.state.upnl > 0 else "red"
                                self.state.log(f"Scalp Sealed. Result: {self.state.upnl:+.4f}", res_color)
                                if self.state.upnl > 0: self.state.wins += 1
                elif topic == "wallet":
                    acc = d["data"][0]
                    self.state.equity = Decimal(acc.get("totalEquity", "0"))
                    self.state.available = Decimal(acc.get("totalAvailableBalance", "0"))
                    if self.state.initial_equity == 0: self.state.initial_equity = self.state.equity
                    self.state.daily_pnl = self.state.equity - self.state.initial_equity

# --- UI WEAVING ---
def build_ui(s: ScalperState) -> Layout:
    l = Layout()
    l.split_column(Layout(name="top", size=3), Layout(name="mid"), Layout(name="bot", size=10))
    l["mid"].split_row(Layout(name="ora"), Layout(name="tac"))

    pnl_s = "bright_green" if s.daily_pnl >= 0 else "bright_red"
    header = f"{Fore.CYAN}⚡ BCH CHRONOS V8.0{Style.RESET_ALL} | Equity: {Fore.YELLOW}{s.equity:.2f}{Style.RESET_ALL} | PnL: [{pnl_s}]{s.daily_pnl:+.2f}[/] | WR: {(s.wins/max(1,s.trade_count)*100):.1f}% | Lat: {s.latency}ms"
    l["top"].update(Panel(Text.from_markup(header, justify="center"), border_style="bright_blue"))

    ora = Table.grid(expand=True)
    ora.add_row("Price", f"{Fore.LIGHTYELLOW_EX}{s.price:.{s.price_prec}f}")
    ora.add_row("Trend", f"{Fore.GREEN}BULL" if s.price > s.ema_macro else f"{Fore.RED}BEAR")
    ora.add_row("Alpha Score", f"{Fore.MAGENTA}{s.alpha_score:.1f}%")
    ora.add_row("VSI (Surge)", f"{Fore.CYAN}{s.vsi:.2f}x")
    ora.add_row("Tick Velocity", f"{s.tick_velocity:.1f} t/s")
    l["ora"].update(Panel(ora, title="[bold cyan]Chronos Oracle[/]", border_style="cyan"))

    tac = Table.grid(expand=True)
    if s.active:
        tac.add_row("Position", f"[bold]{s.side} {s.qty}[/]")
        tac.add_row("uPnL", f"[{pnl_s}]{s.upnl:+.4f}[/]")
        # Visual progress bar for Alpha Score
        tac.add_row("Alpha Confluence", f"[{'magenta' if s.alpha_score > 70 else 'blue'}]{'█' * int(s.alpha_score/5)}[/]")
    else:
        tac.add_row("Status", "[green]SCANNING ETHER[/]" if s.ready else "[yellow]WARMING UP[/]")
        tac.add_row("OBI Imbalance", f"[{'green' if s.obi_score>0 else 'red'}]{s.obi_score:+.2%}[/]")
    l["tac"].update(Panel(tac, title="[bold magenta]Tactical Core[/]", border_style="magenta"))

    l["bot"].update(Panel("\n".join(list(s.logs)), title="[dim]System Chronicles[/]"))
    return l

async def main():
    state = ScalperState(ScalperConfig())
    async with BybitChronos(state) as flux:
        await flux.boot_ritual()

        hist = await flux.api_req("GET", "/v5/market/kline", {"category": "linear", "symbol": state.config.symbol, "interval": "1", "limit": "100"})
        if hist.get("retCode") == 0:
            for k in reversed(hist["result"]["list"]):
                state.ohlc.append((float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])))

        stop = asyncio.Event()
        with Live(build_ui(state), refresh_per_second=6, screen=True) as live:
            tasks = [asyncio.create_task(flux.ws_nexus(stop)), asyncio.create_task(flux.ws_private(stop)), asyncio.create_task(flux.weave_strategy(stop))]
            try:
                while True:
                    live.update(build_ui(state))
                    await asyncio.sleep(0.16) # ~60fps UI refresh
            except KeyboardInterrupt:
                stop.set()
                await asyncio.gather(*tasks, return_exceptions=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"{Fore.MAGENTA}Chronos Weaver enters stasis. Threads preserved.")
