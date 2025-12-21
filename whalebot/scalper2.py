import asyncio
import hashlib
import hmac
import json
import os
import subprocess
import time
import urllib.parse
from collections import deque
from dataclasses import dataclass
from decimal import ROUND_DOWN
from decimal import Decimal
from typing import Any

import aiohttp
import numpy as np
from dotenv import load_dotenv
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

# --- Arcane Sigils (Configuration) ---
load_dotenv()
API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')
IS_TESTNET = os.getenv('BYBIT_TESTNET', 'false').lower() == 'true'

@dataclass
class ArchonConfig:
    symbol: str = "BCHUSDT"
    category: str = "linear"
    leverage: int = 10
    base_risk_pct: Decimal = Decimal("1.5")

    # Thresholds
    max_latency_ms: int = 450
    base_cooldown: int = 15
    obi_threshold: float = 0.12     # High pressure
    obi_extreme: float = 0.38       # Overwhelming pressure
    max_spread_pct: float = 0.0008  # 0.08% Spread Limit
    fisher_extreme: float = 3.2     # Reversal sensitivity

    # Exit Strategy
    sl_atr_mult: Decimal = Decimal("2.2")
    trail_atr_mult: Decimal = Decimal("1.6")

class SentinelState:
    def __init__(self, config: ArchonConfig):
        self.balance = Decimal("0.0")
        self.available_balance = Decimal("0.0")
        self.initial_balance = Decimal("0.0")
        self.daily_pnl = Decimal("0.0")

        # Market Data
        self.price = Decimal("0.0")
        self.bid = Decimal("0.0")
        self.ask = Decimal("0.0")
        self.obi = 0.0
        self.ohlc = deque(maxlen=200)
        self.latency = 0

        # Indicators
        self.fisher = 0.0
        self.fisher_prev = 0.0
        self.atr = 0.0
        self.adx = 0.0
        self.vwap = Decimal("0.0")

        # System
        self.vessel_temp = "NORMAL"
        self.heartbeat_delay = 0.5
        self.trade_active = False
        self.side = "HOLD"
        self.qty = Decimal("0.0")
        self.entry_price = Decimal("0.0")
        self.last_ritual_time = 0
        self.chandelier_exit = Decimal("0.0")

        self.logs = deque(maxlen=10)
        self.is_ready = False
        self.price_prec = 2
        self.qty_step = Decimal("0.01")
        self.min_qty = Decimal("0.01")

# --- Alchemy: Mathematics & Utilities ---

def safe_decimal(value: Any, default: str = "0.0") -> Decimal:
    if value is None: return Decimal(default)
    try:
        clean = str(value).strip().replace(',', '')
        return Decimal(clean) if clean else Decimal(default)
    except: return Decimal(default)

def get_vessel_status(state: SentinelState):
    """Checks the physical health of the Termux environment."""
    try:
        # Check battery/thermal via termux-api if installed
        res = subprocess.check_output(["termux-battery-status"], stderr=subprocess.STDOUT)
        data = json.loads(res)
        temp = data.get("temperature", 30)
        state.vessel_temp = "HOT" if temp > 42 else "NORMAL"
        state.heartbeat_delay = 0.8 if state.vessel_temp == "HOT" else 0.5
    except:
        state.vessel_temp = "UNKNOWN"

def update_oracle(state: SentinelState, config: ArchonConfig):
    if len(state.ohlc) < 50: return
    h = np.array([x[0] for x in state.ohlc])
    l = np.array([x[1] for x in state.ohlc])
    c = np.array([x[2] for x in state.ohlc])
    v = np.array([x[3] for x in state.ohlc])

    # 1. Fisher Transform (Window 10)
    win = c[-10:]
    mn, mx = np.min(win), np.max(win)
    state.fisher_prev = state.fisher
    raw = np.clip(2 * ((c[-1] - mn) / (mx - mn + 1e-9) - 0.5), -0.999, 0.999)
    state.fisher = 0.5 * np.log((1 + raw) / (1 - raw)) + 0.5 * state.fisher_prev

    # 2. ATR & VWAP
    tr = np.maximum(h[1:]-l[1:], np.maximum(np.abs(h[1:]-c[:-1]), np.abs(l[1:]-c[:-1])))
    state.atr = float(np.mean(tr[-14:]))
    tp = (h[-20:] + l[-20:] + c[-20:]) / 3
    state.vwap = safe_decimal(np.sum(tp * v[-20:]) / (np.sum(v[-20:]) + 1e-9))

    # 3. ADX
    up, dn = h[1:] - h[:-1], l[:-1] - l[1:]
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    atr_sm = np.mean(tr[-14:]) + 1e-9
    pdi = 100 * (np.mean(pdm[-14:]) / atr_sm)
    mdi = 100 * (np.mean(mdm[-14:]) / atr_sm)
    state.adx = 100 * abs(pdi - mdi) / (pdi + mdi + 1e-9)

# --- BybitFlux: The Sovereign Async Client ---

class BybitFlux:
    def __init__(self, config: ArchonConfig, state: SentinelState):
        self.session = None
        self.config, self.state = config, state
        self.base = "https://api-testnet.bybit.com" if IS_TESTNET else "https://api.bybit.com"
        self.ws_pub = "wss://stream-testnet.bybit.com/v5/public/linear" if IS_TESTNET else "wss://stream.bybit.com/v5/public/linear"
        self.ws_priv = "wss://stream-testnet.bybit.com/v5/private" if IS_TESTNET else "wss://stream.bybit.com/v5/private"

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.session.close()

    def _sign(self, payload: str) -> dict:
        ts = str(int(time.time() * 1000))
        sig = hmac.new(API_SECRET.encode(), (ts + API_KEY + "5000" + payload).encode(), hashlib.sha256).hexdigest()
        return {"X-BAPI-API-KEY": API_KEY, "X-BAPI-SIGN": sig, "X-BAPI-TIMESTAMP": ts, "X-BAPI-RECV-WINDOW": "5000", "Content-Type": "application/json"}

    async def call(self, method: str, path: str, params: dict = None):
        url = self.base + path
        p_str = urllib.parse.urlencode(params) if method == "GET" and params else json.dumps(params) if params else ""
        if method == "GET" and p_str: url += f"?{p_str}"
        headers = self._sign(p_str if method != "GET" else urllib.parse.urlencode(params) if params else "")
        try:
            async with self.session.request(method, url, headers=headers, data=None if method == "GET" else p_str) as r:
                return await r.json()
        except: return {"retCode": -1}

    async def ws_pub_loop(self):
        while True:
            try:
                async with self.session.ws_connect(self.ws_pub) as ws:
                    await ws.send_json({"op": "subscribe", "args": [f"kline.1.{self.config.symbol}", f"tickers.{self.config.symbol}", f"orderbook.1.{self.config.symbol}"]})
                    async for msg in ws:
                        data = json.loads(msg.data)
                        topic = data.get("topic", "")
                        if "kline.1" in topic:
                            k = data["data"][0]
                            self.state.ohlc.append((float(k['high']), float(k['low']), float(k['close']), float(k['volume'])))
                            update_oracle(self.state, self.config)
                            self.state.is_ready = True
                        elif "orderbook.1" in topic:
                            d = data["data"]
                            b, a = sum(float(x[1]) for x in d.get("b", [])), sum(float(x[1]) for x in d.get("a", []))
                            if b + a > 0: self.state.obi = (b - a) / (b + a)
                        elif "tickers" in topic:
                            d = data["data"]
                            self.state.price = safe_decimal(d.get("lastPrice", self.state.price))
                            self.state.bid = safe_decimal(d.get("bid1Price", self.state.price))
                            self.state.ask = safe_decimal(d.get("ask1Price", self.state.price))
                            if "ts" in data: self.state.latency = int(time.time() * 1000) - int(data["ts"])
            except: await asyncio.sleep(2)

    async def ws_priv_loop(self):
        while True:
            try:
                async with self.session.ws_connect(self.ws_priv) as ws:
                    expires = int((time.time() + 10) * 1000)
                    sig = hmac.new(API_SECRET.encode(), f"GET/realtime{expires}".encode(), hashlib.sha256).hexdigest()
                    await ws.send_json({"op": "auth", "args": [API_KEY, expires, sig]})
                    await ws.send_json({"op": "subscribe", "args": ["position", "wallet"]})
                    async for msg in ws:
                        data = json.loads(msg.data)
                        if data.get("topic") == "position":
                            for p in data["data"]:
                                if p["symbol"] == self.config.symbol:
                                    sz = safe_decimal(p["size"])
                                    self.state.trade_active = sz > 0
                                    self.state.side, self.state.qty = p["side"], sz
                                    self.state.entry_price = safe_decimal(p["avgPrice"])
                        if data.get("topic") == "wallet":
                            coin = [c for c in data["data"][0]["coin"] if c["coin"] == "USDT"][0]
                            self.state.balance = safe_decimal(coin.get("walletBalance"))
                            self.state.available_balance = safe_decimal(coin.get("availableToWithdraw"))
                            if self.state.initial_balance == 0:
                                self.state.initial_balance = self.state.balance
                                self.save_state()
            except: await asyncio.sleep(5)

    def save_state(self):
        with open(".archon_state", "w") as f:
            json.dump({"initial_balance": str(self.state.initial_balance)}, f)

# --- Tactical Logic ---

async def execute_order(void: BybitFlux, side: str, qty: Decimal, is_close: bool = False):
    if void.state.latency > void.config.max_latency_ms and not is_close:
        void.state.logs.append(f"[red]Lag Abort: {void.state.latency}ms[/red]")
        return

    # Spread Guard
    spread = (void.state.ask - void.state.bid) / (void.state.price + 1e-9)
    if not is_close and spread > void.config.max_spread_pct:
        void.state.logs.append(f"[yellow]Spread Guard: {spread:.4%}[/yellow]")
        return

    params = {"category": void.config.category, "symbol": void.config.symbol, "side": side, "orderType": "Market", "qty": str(qty)}
    if is_close: params["reduceOnly"] = True
    else:
        atr = Decimal(str(void.state.atr))
        sl = void.state.price - (atr*void.config.sl_atr_mult) if side == 'Buy' else void.state.price + (atr*void.config.sl_atr_mult)
        params.update({"stopLoss": f"{sl:.{void.state.price_prec}f}"})
        void.state.chandelier_exit = sl

    res = await void.call("POST", "/v5/order/create", params)
    if res.get("retCode") == 0:
        void.state.logs.append(f"[green]⚔️ ARCHON Strike: {side}[/green]")
        void.state.last_ritual_time = time.time()

async def logic_loop(void: BybitFlux):
    while True:
        await asyncio.sleep(void.state.heartbeat_delay)
        if not void.state.is_ready: continue
        s, c = void.state, void.config
        get_vessel_status(s)

        if s.trade_active:
            atr = Decimal(str(s.atr))
            if s.side == "Buy":
                s.chandelier_exit = max(s.chandelier_exit, s.price - (atr * c.trail_atr_mult))
                if s.price < s.chandelier_exit: await execute_order(void, "Sell", s.qty, True)
            else:
                s.chandelier_exit = min(s.chandelier_exit, s.price + (atr * c.trail_atr_mult))
                if s.price > s.chandelier_exit: await execute_order(void, "Buy", s.qty, True)

        elif (time.time() - s.last_ritual_time > c.base_cooldown):
            # THE V-PIVOT LOGIC (Solves your 8-hour wait)
            # 1. Trend Following
            trend_long = s.price > s.vwap and s.obi > c.obi_threshold and s.fisher > s.fisher_prev
            trend_short = s.price < s.vwap and s.obi < -c.obi_threshold and s.fisher < s.fisher_prev

            # 2. Mean Reversion Snap (The Reversal Hunter)
            # If OBI is dominant AND Fisher is at extreme reversal, strike regardless of VWAP side
            snap_long = s.obi > c.obi_extreme and s.fisher < -c.fisher_extreme and s.fisher > s.fisher_prev
            snap_short = s.obi < -c.obi_extreme and s.fisher > c.fisher_extreme and s.fisher < s.fisher_prev

            if (trend_long or snap_long or trend_short or snap_short) and s.adx > 20:
                side = "Buy" if (trend_long or snap_long) else "Sell"
                qty = (s.available_balance * (c.base_risk_pct / 100) / (Decimal(str(s.atr)) * 2)).quantize(s.qty_step, rounding=ROUND_DOWN)
                if qty >= s.min_qty: await execute_order(void, side, qty)

# --- Visual Nexus ---

def render_ui(layout: Layout, s: SentinelState):
    temp_style = "red" if s.vessel_temp == "HOT" else "green"
    layout["header"].update(Panel(Text(f"BCH ARCHON v12 | PnL: {s.daily_pnl:+.2f} USDT | Vessel: [{temp_style}]{s.vessel_temp}[/{temp_style}] | Lag: {s.latency}ms", justify="center", style="bold white"), style="blue"))

    oracle = Text()
    oracle.append(f"Price : {s.price}\n", style="bold white")
    oracle.append(f"VWAP  : {s.vwap:.2f}\n", style="blue")
    oracle.append(f"ADX   : {s.adx:.1f} {'STRONG' if s.adx > 25 else 'RANGE'}\n", style="magenta")
    oracle.append(f"OBI   : {s.obi:+.3f}\n", style="yellow")
    oracle.append(f"Fisher: {s.fisher:+.3f}\n", style="cyan")
    layout["left"].update(Panel(oracle, title="🔮 Oracle Vision", border_style="cyan"))

    tactical = Text()
    if s.trade_active:
        tactical.append(f"SIDE: {s.side}\nQTY: {s.qty}\n", style="bold yellow")
        tactical.append(f"TRAIL: {s.chandelier_exit:.2f}", style="dim white")
    else:
        tactical.append("🔍 Analyzing Confluence...\n", style="dim white")
        tactical.append(f"CD: {int(max(0, s.current_cooldown - (time.time() - s.last_ritual_time)))}s")
    layout["right"].update(Panel(tactical, title="🛡️ Tactical Stance", border_style="magenta"))
    layout["footer"].update(Panel("\n".join(s.logs), title="📜 Chronicles"))

async def main():
    config = ArchonConfig()
    state = SentinelState(config)
    # Load persistence
    if os.path.exists(".archon_state"):
        with open(".archon_state") as f:
            data = json.load(f)
            state.initial_balance = Decimal(data["initial_balance"])

    layout = Layout()
    layout.split_column(Layout(name="header", size=3), Layout(name="body", ratio=1), Layout(name="footer", size=12))
    layout["body"].split_row(Layout(name="left"), Layout(name="right"))

    async with BybitFlux(config, state) as void:
        # Initial Instrument Sync
        info = await void.call("GET", "/v5/market/instruments-info", {"category": config.category, "symbol": config.symbol})
        if info.get("retCode") == 0:
            f = info["result"]["list"][0]
            state.price_prec = abs(safe_decimal(f["priceFilter"]["tickSize"]).normalize().as_tuple().exponent)
            state.qty_step = safe_decimal(f["lotSizeFilter"]["qtyStep"])
            state.min_qty = safe_decimal(f["lotSizeFilter"]["minOrderQty"])

        with Live(layout, refresh_per_second=4, screen=True):
            await asyncio.gather(void.ws_pub_loop(), void.ws_priv_loop(), logic_loop(void), _ui_tick(layout, state))

async def _ui_tick(l, s):
    while True:
        render_ui(l, s)
        await asyncio.sleep(0.25)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
