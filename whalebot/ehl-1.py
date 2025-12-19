import os
import asyncio
import hmac
import hashlib
import json
import time
import urllib.parse
import numpy as np
from collections import deque
from decimal import Decimal, ROUND_DOWN
from typing import Optional, Dict, Any, List

import aiohttp
import websockets
from dotenv import load_dotenv
from rich.layout import Layout
from rich.panel import Panel
from rich.live import Live
from rich.table import Table
from rich.text import Text

load_dotenv()
API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')
IS_TESTNET = os.getenv('BYBIT_TESTNET', 'false').lower() == 'true'

SYMBOL = "BCHUSDT"
CATEGORY = "linear"
LEVERAGE = 10
BASE_RISK_PERCENT = Decimal("2.0")
DAILY_LOSS_LIMIT = Decimal("5.0")
FISHER_THRESHOLD = 2.5
ATR_MULT_SL = Decimal("2.0")
ATR_MULT_TP = Decimal("4.0")
COOLDOWN = 60

class SentinelState:
    def __init__(self):
        self.price = Decimal("0.0")
        self.balance = Decimal("0.0")
        self.initial_balance = Decimal("0.0")
        self.daily_pnl = Decimal("0.0")
        self.ohlc = deque(maxlen=200)
        self.fisher = 0.0
        self.fisher_signal = 0.0
        self.atr = 0.0
        self.macro_trend = 0.0
        self.velocity = 0.0
        self.vwap = Decimal("0.0")
        self.trade_active = False
        self.side = "HOLD"
        self.entry_price = Decimal("0.0")
        self.qty = Decimal("0.0")
        self.upnl = Decimal("0.0")
        self.be_active = False
        self.last_ritual = 0
        self.price_prec = 2
        self.qty_step = Decimal("0.01")
        self.logs = deque(maxlen=12)
        self.is_ready = False

state = SentinelState()

def super_smoother(data: List[float], period: int) -> float:
    if len(data) < 3: return data[-1] if data else 0.0
    a = np.exp(-1.414 * np.pi / period)
    b = 2 * a * np.cos(1.414 * np.pi / period)
    c2, c3 = b, -a * a
    c1 = 1 - c2 - c3
    return c1 * (data[-1] + data[-2]) / 2 + c2 * data[-2] + c3 * data[-3]

def update_oracle():
    if len(state.ohlc) < 50: return
    closes = [x[2] for x in state.ohlc]
    highs = [x[0] for x in state.ohlc]
    lows = [x[1] for x in state.ohlc]
    vols = [x[3] for x in state.ohlc]

    state.macro_trend = super_smoother(closes, 50)
    tr = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])) for i in range(1, len(closes))]
    state.atr = float(np.mean(tr[-14:]))

    state.velocity = (closes[-1] - closes[-10]) / (state.atr if state.atr > 0 else 1)

    window = closes[-10:]
    hh, ll = max(window), min(window)
    raw = 2 * ((closes[-1] - ll) / (hh - ll + 1e-9) - 0.5)
    state.fisher_signal = state.fisher
    state.fisher = 0.5 * np.log((1 + np.clip(raw, -0.99, 0.99)) / (1 - np.clip(raw, -0.99, 0.99)))

    pv_sum = sum(Decimal(str((h+l+c)/3)) * Decimal(str(v)) for h, l, c, v in state.ohlc[-20:])
    v_sum = sum(Decimal(str(v)) for _, _, _, v in state.ohlc[-20:])
    state.vwap = pv_sum / v_sum if v_sum > 0 else state.price

class BybitForge:
    def __init__(self):
        self.session = None
        self.base = "https://api-testnet.bybit.com" if IS_TESTNET else "https://api.bybit.com"

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.close()

    def _sign(self, ts: str, payload: str) -> str:
        return hmac.new(API_SECRET.encode(), (ts + API_KEY + "5000" + payload).encode(), hashlib.sha256).hexdigest()

    async def call(self, method: str, path: str, params: dict = None, signed: bool = False):
        ts = str(int(time.time() * 1000))
        p_str = urllib.parse.urlencode(params) if method == "GET" and params else json.dumps(params) if params else ""
        headers = {"Content-Type": "application/json"}
        if signed:
            headers.update({"X-BAPI-API-KEY": API_KEY, "X-BAPI-SIGN": self._sign(ts, p_str), "X-BAPI-TIMESTAMP": ts, "X-BAPI-RECV-WINDOW": "5000"})
        url = self.base + path + (f"?{p_str}" if method == "GET" and p_str else "")
        try:
            async with self.session.request(method, url, headers=headers, data=None if method == "GET" else p_str) as r:
                return await r.json()
        except: return {"retCode": -1}

async def execute_trade(forge: BybitForge, side: str):
    if state.daily_pnl <= -(state.initial_balance * DAILY_LOSS_LIMIT / 100): return

    risk_mult = Decimal(str(np.clip(abs(state.velocity), 0.5, 2.0)))
    risk_usd = state.balance * (BASE_RISK_PERCENT / 100) * risk_mult

    atr_dec = Decimal(str(state.atr))
    qty = ((risk_usd / (atr_dec * ATR_MULT_SL)) // state.qty_step) * state.qty_step
    if qty <= 0: return

    tp = state.price + (atr_dec * ATR_MULT_TP) if side == "Buy" else state.price - (atr_dec * ATR_MULT_TP)
    sl = state.price - (atr_dec * ATR_MULT_SL) if side == "Buy" else state.price + (atr_dec * ATR_MULT_SL)

    res = await forge.call("POST", "/v5/order/create", {
        "category": CATEGORY, "symbol": SYMBOL, "side": side, "orderType": "Market", "qty": str(qty),
        "takeProfit": f"{tp:.{state.price_prec}f}", "stopLoss": f"{sl:.{state.price_prec}f}"
    }, signed=True)

    if res.get('retCode') == 0:
        state.last_ritual = time.time()
        state.logs.append(f"[bold green]⚔️ {side} Entered | Risk x{risk_mult:.1f}[/bold green]")

async def monitor_trade(forge: BybitForge):
    if not state.trade_active or state.be_active: return

    pnl_pct = (state.price - state.entry_price) / state.entry_price if state.side == "Buy" else (state.entry_price - state.price) / state.entry_price
    if pnl_pct > 0.005:
        be_price = state.entry_price * Decimal("1.001") if state.side == "Buy" else state.entry_price * Decimal("0.999")
        res = await forge.call("POST", "/v5/position/set-trading-stop", {
            "category": CATEGORY, "symbol": SYMBOL, "stopLoss": f"{be_price:.{state.price_prec}f}", "positionIdx": 0
        }, signed=True)
        if res.get('retCode') == 0:
            state.be_active = True
            state.logs.append("[bold blue]🛡️ SL Moved to Break-Even[/bold blue]")

async def logic_loop(forge: BybitForge):
    while True:
        if state.is_ready:
            await monitor_trade(forge)

            if not state.trade_active and (time.time() - state.last_ritual > COOLDOWN):
                is_bull = float(state.price) > state.macro_trend and state.price > state.vwap
                is_bear = float(state.price) < state.macro_trend and state.price < state.vwap

                if is_bull and state.fisher < -FISHER_THRESHOLD and state.fisher > state.fisher_signal:
                    await execute_trade(forge, "Buy")
                elif is_bear and state.fisher > FISHER_THRESHOLD and state.fisher < state.fisher_signal:
                    await execute_trade(forge, "Sell")
        await asyncio.sleep(1)

async def stream_data(forge: BybitForge):
    pub_url = "wss://stream.bybit.com/v5/public/linear" if not IS_TESTNET else "wss://stream-testnet.bybit.com/v5/public/linear"
    priv_url = "wss://stream.bybit.com/v5/private" if not IS_TESTNET else "wss://stream-testnet.bybit.com/v5/private"

    async def handle_public():
        async with websockets.connect(pub_url) as ws:
            await ws.send(json.dumps({"op": "subscribe", "args": [f"kline.1.{SYMBOL}", f"tickers.{SYMBOL}"]}))
            while True:
                data = json.loads(await ws.recv())
                if "kline" in data.get("topic", ""):
                    k = data["data"][0]
                    state.ohlc.append((float(k["high"]), float(k["low"]), float(k["close"]), float(k["volume"])))
                    update_oracle()
                    state.is_ready = True
                if "tickers" in data.get("topic", ""):
                    state.price = Decimal(data["data"].get("lastPrice", str(state.price)))

    async def handle_private():
        async with websockets.connect(priv_url) as ws:
            expires = int(time.time() * 1000) + 10000
            sig = hmac.new(API_SECRET.encode(), f"GET/realtime{expires}".encode(), hashlib.sha256).hexdigest()
            await ws.send(json.dumps({"op": "auth", "args": [API_KEY, expires, sig]}))
            await ws.send(json.dumps({"op": "subscribe", "args": ["position", "wallet"]}))
            while True:
                data = json.loads(await ws.recv())
                topic = data.get("topic")
                if topic == "position":
                    pos = [p for p in data["data"] if p["symbol"] == SYMBOL]
                    if pos:
                        p = pos[0]
                        size = Decimal(p["size"])
                        state.trade_active = size > 0
                        state.side = p["side"] if size > 0 else "HOLD"
                        state.entry_price = Decimal(p["avgPrice"])
                        state.upnl = Decimal(p["unrealisedPnl"])
                        state.qty = size
                        if not state.trade_active: state.be_active = False
                if topic == "wallet":
                    state.balance = Decimal(data["data"][0]["coin"][0]["walletBalance"])
                    if state.initial_balance == 0: state.initial_balance = state.balance
                    state.daily_pnl = state.balance - state.initial_balance

    await asyncio.gather(handle_public(), handle_private())

def get_layout():
    l = Layout()
    l.split_column(Layout(name="h", size=3), Layout(name="m", ratio=1), Layout(name="f", size=10))
    l["m"].split_row(Layout(name="l"), Layout(name="r"))
    return l

async def main():
    async with BybitForge() as forge:
        info = await forge.call("GET", "/v5/market/instruments-info", {"category": CATEGORY, "symbol": SYMBOL})
        if info.get('retCode') == 0:
            s = info['result']['list'][0]
            state.price_prec = abs(Decimal(s['priceFilter']['tickSize']).normalize().as_tuple().exponent)
            state.qty_step = Decimal(s['lotSizeFilter']['qtyStep'])

        layout = get_layout()
        with Live(layout, refresh_per_second=4, screen=True):
            asyncio.create_task(stream_data(forge))
            asyncio.create_task(logic_loop(forge))
            while True:
                layout["h"].update(Panel(Text(f"BCH SENTINEL v4.5 | Daily: {state.daily_pnl:+.2f} USDT", justify="center", style="bold white"), border_style="blue"))
                layout["l"].update(Panel(f"Price: {state.price}\nFisher: {state.fisher:+.2f}\nTrend: {'BULL' if float(state.price) > state.macro_trend else 'BEAR'}\nVelocity: {state.velocity:+.2f}", title="Oracle"))
                layout["r"].update(Panel(f"Side: {state.side}\nuPnL: {state.upnl:+.2f}\nQty: {state.qty}\nBE-Shield: {'ON' if state.be_active else 'OFF'}", title="Tactical"))
                layout["f"].update(Panel("\n".join(state.logs), title="Logs"))
                await asyncio.sleep(0.2)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass