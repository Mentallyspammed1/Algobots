import asyncio
import hashlib
import hmac
import json
import os
import time
import urllib.parse
from collections import deque
from decimal import ROUND_DOWN
from decimal import Decimal
from typing import Any

import aiohttp
import numpy as np
from dotenv import load_dotenv
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# --- Invoke Ancient Keys ---
load_dotenv()
API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')
IS_TESTNET = os.getenv('BYBIT_TESTNET', 'false').lower() == 'true'

console = Console()

class ArchonConfig:
    symbol: str = "BCHUSDT"
    category: str = "linear"
    leverage: int = 10
    base_risk_pct: Decimal = Decimal("1.5")

    max_latency_ms: int = 550
    obi_threshold: float = 0.20
    rsi_oversold: float = 32.0
    rsi_overbought: float = 68.0
    fisher_extreme: float = 2.8
    min_atr_for_trade: Decimal = Decimal("3.0")  # Avoid flat markets

    sl_atr_mult: Decimal = Decimal("2.5")
    tp_atr_mult: Decimal = Decimal("4.5")
    trail_atr_mult_initial: Decimal = Decimal("2.2")
    trail_atr_mult_tight: Decimal = Decimal("1.7")

class SentinelState:
    def __init__(self, config: ArchonConfig):
        self.config = config

        self.balance = Decimal("0")
        self.available = Decimal("0")
        self.initial_balance = Decimal("0")
        self.daily_pnl = Decimal("0")

        self.price = Decimal("0")
        self.bid = Decimal("0")
        self.ask = Decimal("0")
        self.obi = 0.0
        self.ohlc = deque(maxlen=320)
        self.latency_ms = 0

        self.fisher = 0.0
        self.fisher_prev = 0.0
        self.atr = 0.0
        self.rsi = 50.0
        self.macd_line = 0.0
        self.macd_signal = 0.0
        self.macd_hist = 0.0
        self.vwap = Decimal("0")

        self.active = False
        self.side = "HOLD"
        self.qty = Decimal("0")
        self.entry_price = Decimal("0")
        self.upnl = Decimal("0")
        self.trailing_stop = Decimal("0")
        self.trail_mult = config.trail_atr_mult_initial

        self.logs = deque(maxlen=16)
        self.ready = False  # Progressive readiness

        self.price_prec = 2
        self.qty_step = Decimal("0.01")
        self.min_qty = Decimal("0.01")

    def log(self, msg: str):
        ts = time.strftime('%H:%M:%S')
        self.logs.append(f"[dim]{ts}[/] {msg}")

# --- Oracle Forging ---
def safe_decimal(val: Any, default: str = "0") -> Decimal:
    if val is None: return Decimal(default)
    try: return Decimal(str(val).replace(',', ''))
    except: return Decimal(default)

def update_oracle(state: SentinelState):
    length = len(state.ohlc)
    if length < 20: return

    highs = np.array([c[0] for c in state.ohlc])
    lows  = np.array([c[1] for c in state.ohlc])
    closes = np.array([c[2] for c in state.ohlc])
    volumes = np.array([c[3] for c in state.ohlc])

    # ATR
    if length >= 15:
        tr = np.maximum(highs[1:] - lows[1:],
                        np.maximum(np.abs(highs[1:] - closes[:-1]),
                                   np.abs(lows[1:] - closes[:-1])))
        state.atr = float(np.mean(tr[-14:])) if len(tr) >= 14 else 0.0

    # Fisher (smoothed)
    window = closes[-10:]
    mn, mx = np.min(window), np.max(window) + 1e-8
    raw = np.clip(2 * ((closes[-1] - mn) / (mx - mn) - 0.5), -0.999, 0.999)
    state.fisher_prev = state.fisher
    state.fisher = 0.5 * np.log((1 + raw) / (1 - raw + 1e-8)) + 0.5 * state.fisher_prev

    # RSI
    if length >= 15:
        deltas = np.diff(closes[-15:])
        up = np.mean(np.where(deltas > 0, deltas, 0))
        down = np.mean(np.where(deltas < 0, -deltas, 0)) or 1e-8
        state.rsi = 100 - (100 / (1 + up / down))

    # MACD (approximated EMA)
    if length >= 26:
        ema12 = np.mean(closes[-12:])
        ema26 = np.mean(closes[-26:])
        state.macd_line = ema12 - ema26
        state.macd_signal = 0.2 * state.macd_line + 0.8 * (state.macd_signal if hasattr(state, 'macd_signal') else state.macd_line)
        state.macd_hist = state.macd_line - state.macd_signal

    # VWAP
    if length >= 20:
        typ = (highs[-20:] + lows[-20:] + closes[-20:]) / 3
        vol_sum = np.sum(volumes[-20:]) or 1
        state.vwap = safe_decimal(np.sum(typ * volumes[-20:]) / vol_sum)

    if length >= 40:
        state.ready = True

# --- Bybit Sovereign Streams ---
class BybitFlux:
    def __init__(self, config: ArchonConfig, state: SentinelState):
        self.config = config
        self.state = state
        self.base = "https://api-testnet.bybit.com" if IS_TESTNET else "https://api.bybit.com"
        self.ws_pub = "wss://stream-testnet.bybit.com/v5/public/linear" if IS_TESTNET else "wss://stream.bybit.com/v5/public/linear"
        self.ws_priv = "wss://stream-testnet.bybit.com/v5/private" if IS_TESTNET else "wss://stream.bybit.com/v5/private"

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *exc):
        await self.session.close()

    def _sign(self, payload: str = "") -> dict:
        ts = str(int(time.time() * 1000))
        sig = hmac.new(API_SECRET.encode(), (ts + API_KEY + "5000" + payload).encode(), hashlib.sha256).hexdigest()
        return {
            "X-BAPI-API-KEY": API_KEY,
            "X-BAPI-SIGN": sig,
            "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-RECV-WINDOW": "5000",
            "Content-Type": "application/json"
        }

    async def api_call(self, method: str, path: str, params: dict = None):
        url = self.base + path
        payload = json.dumps(params) if params and method == "POST" else urllib.parse.urlencode(params) if params else ""
        if method == "GET" and payload: url += f"?{payload}"
        headers = self._sign(payload)
        try:
            async with self.session.request(method, url, headers=headers, data=payload if method == "POST" else None) as resp:
                return await resp.json()
        except Exception as e:
            console.log(f"[red]API Veil Torn: {e}[/red]")
            return {"retCode": -1}

    async def place_market(self, side: str, qty: Decimal, reduce: bool = False):
        if self.state.latency_ms > self.config.max_latency_ms and not reduce:
            self.state.log("[dim italic]Latency storm – strike withheld[/dim italic]")
            return
        params = {
            "category": self.config.category,
            "symbol": self.config.symbol,
            "side": side,
            "orderType": "Market",
            "qty": str(qty.quantize(self.state.qty_step, ROUND_DOWN)),
            "reduceOnly": reduce
        }
        resp = await self.api_call("POST", "/v5/order/create", params)
        if resp.get("retCode") == 0:
            self.state.log(f"[bold bright_green]⚔️ ARCHON {side} {qty} UNLEASHED[/bold bright_green]")
        else:
            self.state.log(f"[bold bright_red]Strike faltered: {resp.get('retMsg', 'Unknown')}[/bold bright_red]")

    async def public_ws(self):
        while True:
            try:
                async with self.session.ws_connect(self.ws_pub) as ws:
                    await ws.send_json({"op": "subscribe", "args": [
                        f"kline.1.{self.config.symbol}",
                        f"tickers.{self.config.symbol}",
                        f"orderbook.50.{self.config.symbol}"
                    ]})
                    async for msg in ws:
                        if msg.type != aiohttp.WSMsgType.TEXT: continue
                        data = json.loads(msg.data)
                        topic = data.get("topic", "")

                        if "kline.1" in topic and data["data"][0].get("confirm"):
                            k = data["data"][0]
                            self.state.ohlc.append((float(k["high"]), float(k["low"]), float(k["close"]), float(k["volume"])))
                            update_oracle(self.state)

                        elif "orderbook.50" in topic:
                            ob = data["data"]
                            bids_vol = sum(float(x[1]) for x in ob.get("b", [])[:15])
                            asks_vol = sum(float(x[1]) for x in ob.get("a", [])[:15])
                            total = bids_vol + asks_vol or 1e-8
                            self.state.obi = (bids_vol - asks_vol) / total

                        elif "tickers" in topic:
                            t = data["data"]
                            self.state.price = safe_decimal(t.get("lastPrice", self.state.price))
                            self.state.bid = safe_decimal(t.get("bid1Price", self.state.bid))
                            self.state.ask = safe_decimal(t.get("ask1Price", self.state.ask))
                            if "ts" in t: self.state.latency_ms = int(time.time()*1000) - int(t["ts"])

            except Exception: await asyncio.sleep(4)

    async def private_ws(self):
        while True:
            try:
                async with self.session.ws_connect(self.ws_priv) as ws:
                    expires = int(time.time()*1000) + 10000
                    sig = hmac.new(API_SECRET.encode(), f"GET/realtime{expires}".encode(), hashlib.sha256).hexdigest()
                    await ws.send_json({"op": "auth", "args": [API_KEY, expires, sig]})
                    await ws.send_json({"op": "subscribe", "args": ["position", "wallet"]})

                    async for msg in ws:
                        if msg.type != aiohttp.WSMsgType.TEXT: continue
                        data = json.loads(msg.data)

                        if data.get("topic") == "position":
                            for p in data["data"]:
                                if p["symbol"] == self.config.symbol:
                                    sz = safe_decimal(p["size"])
                                    self.state.active = sz > 0
                                    self.state.side = p["side"] if sz > 0 else "HOLD"
                                    self.state.qty = sz
                                    self.state.entry_price = safe_decimal(p["avgPrice"])
                                    self.state.upnl = safe_decimal(p.get("unrealisedPnl", "0"))
                                    if not self.state.active:
                                        self.state.trailing_stop = Decimal("0")
                                        self.state.trail_mult = self.config.trail_atr_mult_initial

                        elif data.get("topic") == "wallet":
                            for acct in data["data"]:
                                for coin in acct.get("coin", []):
                                    if coin["coin"] == "USDT":
                                        self.state.balance = safe_decimal(coin["walletBalance"])
                                        self.state.available = safe_decimal(coin["availableToWithdraw"])
                                        if self.state.initial_balance == 0:
                                            self.state.initial_balance = self.state.balance
                                        self.state.daily_pnl = self.state.balance - self.state.initial_balance

            except Exception: await asyncio.sleep(6)

# --- Archon Divine Logic ---
async def archon_logic(flux: BybitFlux):
    s = flux.state
    c = flux.config
    while True:
        await asyncio.sleep(0.8)
        if not s.ready or s.atr < float(c.min_atr_for_trade): continue

        atr_dec = Decimal(str(s.atr))

        # Sizing
        risk_amount = s.available * (c.base_risk_pct / 100)
        qty_raw = risk_amount / (atr_dec * c.sl_atr_mult)
        qty = qty_raw.quantize(s.qty_step, ROUND_DOWN)
        if qty < s.min_qty: qty = Decimal("0")

        if not s.active:
            long_sig = (s.fisher < -c.fisher_extreme and s.rsi < c.rsi_oversold and
                        s.obi > c.obi_threshold and s.price < s.vwap)
            short_sig = (s.fisher > c.fisher_extreme and s.rsi > c.rsi_overbought and
                         s.obi < -c.obi_threshold and s.price > s.vwap)

            if long_sig and qty > 0:
                await flux.place_market("Buy", qty)
                sl = s.price - atr_dec * c.sl_atr_mult
                tp = s.price + atr_dec * c.tp_atr_mult
                await flux.api_call("POST", "/v5/position/trading-stop", {
                    "category": c.category, "symbol": c.symbol,
                    "stopLoss": f"{sl:.{s.price_prec}f}",
                    "takeProfit": f"{tp:.{s.price_prec}f}",
                    "positionIdx": 0
                })
                s.trailing_stop = sl
                s.log("[cyan]🔮 Long Confluence Achieved[/cyan]")

            elif short_sig and qty > 0:
                await flux.place_market("Sell", qty)
                sl = s.price + atr_dec * c.sl_atr_mult
                tp = s.price - atr_dec * c.tp_atr_mult
                await flux.api_call("POST", "/v5/position/trading-stop", {
                    "category": c.category, "symbol": c.symbol,
                    "stopLoss": f"{sl:.{s.price_prec}f}",
                    "takeProfit": f"{tp:.{s.price_prec}f}",
                    "positionIdx": 0
                })
                s.trailing_stop = sl
                s.log("[cyan]🔮 Short Confluence Achieved[/cyan]")

        else:
            # Dynamic Trail Tighten (after ~2R profit)
            profit_dist = abs(s.price - s.entry_price)
            if profit_dist > atr_dec * 2 and s.trail_mult != c.trail_atr_mult_tight:
                s.trail_mult = c.trail_atr_mult_tight
                s.log("[magenta]🛡️ Trail Tightened on Profit[/magenta]")

            trail_dist = atr_dec * s.trail_mult
            if s.side == "Buy":
                new_trail = max(s.trailing_stop or s.entry_price, s.price - trail_dist)
                if s.price <= new_trail:
                    await flux.place_market("Sell", s.qty, reduce=True)
                    s.log("[bold magenta]🛡️ Trailing Stop Claimed[/bold magenta]")
                s.trailing_stop = new_trail
            else:
                new_trail = min(s.trailing_stop or s.entry_price, s.price + trail_dist)
                if s.price >= new_trail:
                    await flux.place_market("Buy", s.qty, reduce=True)
                    s.log("[bold magenta]🛡️ Trailing Stop Claimed[/bold magenta]")
                s.trailing_stop = new_trail

            # Extreme Fisher Reversal
            if (s.side == "Buy" and s.fisher > c.fisher_extreme) or (s.side == "Sell" and s.fisher < -c.fisher_extreme):
                close_side = "Sell" if s.side == "Buy" else "Buy"
                await flux.place_market(close_side, s.qty, reduce=True)
                s.log("[bold yellow]🌀 Fisher Extreme Reversal[/bold yellow]")

# --- Grimoire Visualization ---
def build_dashboard(state: SentinelState) -> Layout:
    layout = Layout()
    layout.split_column(Layout(name="header", size=3), Layout(name="main"), Layout(name="footer", size=16))
    layout["main"].split_row(Layout(name="oracle"), Layout(name="tactical"))

    pnl_style = "bold bright_green" if state.daily_pnl >= 0 else "bold bright_red"
    lat_style = "bright_green" if state.latency_ms < 300 else "yellow" if state.latency_ms < 550 else "bold red"

    layout["header"].update(Panel(
        Text(f"🧙‍♂️ ARCHON PRIME v3.0 • {state.config.symbol} • PnL: [{pnl_style}]{state.daily_pnl:+.2f} USDT[/] • Latency: [{lat_style}]{state.latency_ms}ms[/]",
             justify="center", style="bold white on blue"),
        border_style="bright_blue"
    ))

    oracle = Table.grid(expand=True)
    oracle.add_column()
    oracle.add_column()
    oracle.add_row("Price", f"[bold white]{state.price}[/]")
    oracle.add_row("Bid/Ask", f"[green]{state.bid}[/] / [red]{state.ask}[/]")
    oracle.add_row("VWAP", f"[cyan]{state.vwap}[/]")
    oracle.add_row("OBI", f"[yellow]{state.obi:+.3f}[/]")
    oracle.add_row("Fisher", f"[cyan]{state.fisher:+.3f}[/]")
    oracle.add_row("RSI", f"[magenta]{state.rsi:.1f}[/]")
    oracle.add_row("ATR", f"[white]{state.atr:.2f}[/]")
    oracle.add_row("MACD Hist", f"[blue]{state.macd_hist:+.4f}[/]")
    layout["oracle"].update(Panel(oracle, title="🔮 Oracle Vision", border_style="bright_cyan"))

    tactical = Text()
    if state.active:
        tactical.append(f"Side : [bold bright_yellow]{state.side}[/]\n")
        tactical.append(f"Qty  : {state.qty}\n")
        tactical.append(f"Entry: {state.entry_price}\n")
        tactical.append(f"uPnL : [{'bright_green' if state.upnl > 0 else 'bright_red'}]{state.upnl:+.2f}[/]\n")
        tactical.append(f"Trail: {state.trailing_stop:.2f}")
    else:
        tactical.append("[bold magenta]Seeking Divine Confluence...[/]\n")
        tactical.append(f"[dim]Balance: {state.balance:.2f} USDT | Available: {state.available:.2f}[/]")
    layout["tactical"].update(Panel(tactical, title="🛡️ Tactical Realm", border_style="bright_magenta"))

    logs = "\n".join(state.logs) or "[dim]Grimoire awaits inscription...[/]"
    layout["footer"].update(Panel(logs, title="📜 Eternal Chronicles", border_style="bright_black"))

    return layout

async def ui_refresh(layout: Layout, state: SentinelState):
    while True:
        render_ui(layout, state)
        await asyncio.sleep(0.3)

def render_ui(layout: Layout, state: SentinelState):
    layout.update(build_dashboard(state))

# --- Eternal Summoning ---
async def main():
    if not API_KEY or not API_SECRET:
        console.print("[bold red]⚠️ Sacred keys missing – ritual cannot commence[/bold red]")
        return

    config = ArchonConfig()
    state = SentinelState(config)
    layout = Layout()

    async with BybitFlux(config, state) as flux:
        await flux.api_call("POST", "/v5/position/set-leverage", {
            "category": config.category, "symbol": config.symbol,
            "buyLeverage": str(config.leverage), "sellLeverage": str(config.leverage)
        })

        info = await flux.api_call("GET", "/v5/market/instruments-info", {"category": config.category, "symbol": config.symbol})
        if info.get("retCode") == 0:
            i = info["result"]["list"][0]
            state.price_prec = abs(safe_decimal(i["priceFilter"]["tickSize"]).normalize().as_tuple().exponent)
            state.qty_step = safe_decimal(i["lotSizeFilter"]["qtyStep"])
            state.min_qty = safe_decimal(i["lotSizeFilter"]["minOrderQty"])

        wallet = await flux.api_call("GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED"})
        if wallet.get("retCode") == 0:
            for acct in wallet["result"]["list"]:
                for coin in acct["coin"]:
                    if coin["coin"] == "USDT":
                        state.balance = safe_decimal(coin["walletBalance"])
                        state.available = safe_decimal(coin["availableToWithdraw"])
                        state.initial_balance = state.balance

        with Live(layout, refresh_per_second=4, screen=True):
            await asyncio.gather(
                flux.public_ws(),
                flux.private_ws(),
                archon_logic(flux),
                ui_refresh(layout, state)
            )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[bold cyan]🧙‍♂️ The Archon slumbers once more. Farewell until the next dawn.[/bold cyan]")
