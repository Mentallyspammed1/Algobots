#!/usr/bin/env python3
"""
BCH Sentinel v3.4 - The Resilient Oracle
Forged by Pyrmethus: KeyError wards, optimized calculations, and TUI stability.
"""

import asyncio
import hashlib
import hmac
import json
import os
import time
import urllib.parse
from collections import deque
from decimal import Decimal

import aiohttp
import numpy as np
import websockets
from dotenv import load_dotenv
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# --- Awaken the Sigils ---
load_dotenv()
API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')
IS_TESTNET = os.getenv('BYBIT_TESTNET', 'false').lower() == 'true'

# Arcana Configuration
SYMBOL = "BCHUSDT"
CATEGORY = "linear"
LEVERAGE = 10
RISK_PERCENT = Decimal("5.0")
FISHER_PERIOD = 10
ATR_PERIOD = 14
MACRO_PERIOD = 50
ENTRY_THRESHOLD = 2.0
COOLDOWN_SECONDS = 180

class SentinelState:
    def __init__(self):
        self.price = Decimal("0.0")
        self.fisher = 0.0
        self.trigger = 0.0
        self.atr = 0.0
        self.macro_trend = 0.0
        self.balance = Decimal("0.0")
        self.trade_active = False
        self.side = "HOLD"
        self.upnl = Decimal("0.0")
        self.last_ritual = 0
        self.price_prec = 2
        self.qty_step = Decimal("0.01")

        # Chronological Buffers
        self.ohlc = deque(maxlen=100)
        self.value1 = deque(maxlen=100)
        self.fisher_series = deque(maxlen=100)
        self.logs = deque(maxlen=8)

        self.is_ready = False
        self.is_connected = False

state = SentinelState()

# --- Alchemy: Technical Indicators ---

def calculate_super_smoother(data_list: list[float], period: int) -> float:
    """A 2-pole Butterworth filter for high-fidelity noise reduction."""
    if len(data_list) < 3: return data_list[-1] if data_list else 0.0
    a1 = np.exp(-1.414 * np.pi / period)
    b1 = 2 * a1 * np.cos(1.414 * np.pi / period)
    c2, c3 = b1, -a1 * a1
    c1 = 1 - c2 - c3
    return c1 * (data_list[-1] + data_list[-2]) / 2 + c2 * data_list[-2] + c3 * data_list[-3]

def update_oracle_indicators():
    """Divines the Fisher velocity, ATR volatility, and Macro Trend."""
    if len(state.ohlc) < MACRO_PERIOD: return

    closes = [x[2] for x in state.ohlc]

    # 1. Macro Trend (SuperSmoother 50)
    state.macro_trend = calculate_super_smoother(closes, MACRO_PERIOD)

    # 2. ATR Logic
    tr_list = []
    for i in range(1, len(state.ohlc)):
        h, l, c = state.ohlc[i]
        pc = state.ohlc[i-1][2]
        tr_list.append(max(h - l, abs(h - pc), abs(l - pc)))
    state.atr = np.mean(tr_list[-ATR_PERIOD:])

    # 3. Refined Fisher Logic
    # We smooth the prices using a short SuperSmoother before transformation
    smoothed_input = calculate_super_smoother(closes, 10)

    # Extract window for Min/Max
    # Note: We need a history of smoothed prices for consistent Fisher output
    # Here we use a rolling window of the last 10 smoothed prices
    window = []
    for i in range(FISHER_PERIOD, 0, -1):
        hist_closes = closes[:-i] if i > 0 else closes
        window.append(calculate_super_smoother(hist_closes, 10))

    mx, mn = max(window), min(window)
    raw_val = 0.0
    if (mx - mn) != 0:
        raw_val = 2 * ((window[-1] - mn) / (mx - mn) - 0.5)

    prev_v1 = state.value1[-1] if state.value1 else 0.0
    v1 = 0.33 * raw_val + 0.67 * prev_v1
    v1 = np.clip(v1, -0.999, 0.999)
    state.value1.append(v1)

    prev_fish = state.fisher_series[-1] if state.fisher_series else 0.0
    fish = 0.5 * np.log((1 + v1) / (1 - v1)) + 0.5 * prev_fish

    state.trigger = prev_fish
    state.fisher = fish
    state.fisher_series.append(fish)

# --- The Forge: API Client ---
class BybitForge:
    def __init__(self):
        self.session: aiohttp.ClientSession | None = None
        self.base = "https://api-testnet.bybit.com" if IS_TESTNET else "https://api.bybit.com"

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session: await self.session.close()

    def _sign(self, ts: str, payload: str) -> str:
        return hmac.new(API_SECRET.encode(), (ts + API_KEY + "5000" + payload).encode(), hashlib.sha256).hexdigest()

    async def call(self, method: str, path: str, params: dict = None, signed: bool = False):
        if not self.session: return {"retCode": -1}
        ts = str(int(time.time() * 1000))
        req_params = params or {}
        param_str = urllib.parse.urlencode(req_params) if method == "GET" else json.dumps(req_params)
        headers = {"Content-Type": "application/json"}
        if signed:
            headers.update({"X-BAPI-API-KEY": API_KEY, "X-BAPI-SIGN": self._sign(ts, param_str), "X-BAPI-TIMESTAMP": ts, "X-BAPI-RECV-WINDOW": "5000"})

        url = self.base + path + (f"?{param_str}" if method == "GET" else "")
        try:
            async with self.session.request(method, url, headers=headers, data=None if method == "GET" else param_str, timeout=10) as resp:
                return await resp.json()
        except: return {"retCode": -1}

# --- Tactical Execution ---

async def execute_trade(forge, side: str):
    bal_res = await forge.call("GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED"}, signed=True)
    if bal_res.get('retCode') == 0:
        try: state.balance = Decimal(bal_res['result']['list'][0]['coin'][0]['walletBalance'])
        except: pass

    if state.price == 0 or state.atr == 0: return

    risk_amt = state.balance * (RISK_PERCENT / 100) * LEVERAGE
    qty = ((risk_amt / state.price) // state.qty_step) * state.qty_step
    if qty <= 0: return

    atr_dec = Decimal(str(round(state.atr, 4)))
    tp = (state.price + atr_dec * Decimal("3.5")) if side == "Buy" else (state.price - atr_dec * Decimal("3.5"))
    sl = (state.price - atr_dec * Decimal("2.0")) if side == "Buy" else (state.price + atr_dec * Decimal("2.0"))

    order = {
        "category": CATEGORY, "symbol": SYMBOL, "side": side, "orderType": "Market", "qty": str(qty),
        "takeProfit": f"{tp:.{state.price_prec}f}", "stopLoss": f"{sl:.{state.price_prec}f}",
        "tpTriggerBy": "LastPrice", "slTriggerBy": "LastPrice"
    }
    res = await forge.call("POST", "/v5/order/create", order, signed=True)
    if res.get('retCode') == 0:
        state.last_ritual = time.time()
        state.logs.append(f"[bold green]⚔️ {side} Entry @ {state.price}")

# --- Vision: TUI ---

def render_dashboard(layout: Layout):
    layout["header"].update(Panel(Text(f"BCH SENTINEL v3.4 | {'LIVE' if state.is_connected else 'VOID'} | {time.strftime('%X')}", justify="center", style="bold cyan"), border_style="magenta"))

    oracle_text = Text()
    oracle_text.append(f"\nPrice:  {state.price} USDT\n", style="white")

    trend = "BULL" if float(state.price) > state.macro_trend else "BEAR"
    oracle_text.append(f"Trend:  {trend}\n", style="bold lime" if trend == "BULL" else "bold red")

    f_style = "bold lime" if state.fisher > state.trigger else "bold red"
    oracle_text.append(f"Fisher: {state.fisher:+.4f}\n", style=f_style)
    oracle_text.append(f"ATR:    {state.atr:.4f}\n", style="dim yellow")

    layout["oracle"].update(Panel(oracle_text, title="Harmonic Oracle", border_style="blue"))

    pos_table = Table.grid(expand=True)
    pnl_col = "green" if state.upnl >= 0 else "red"
    pos_table.add_row("SIDE:", f"[bold]{state.side}[/]")
    pos_table.add_row("uPnL:", f"[{pnl_col}]{state.upnl:+.2f} USDT[/]")
    pos_table.add_row("BAL:", f"{state.balance:.2f} USDT")
    layout["position"].update(Panel(pos_table, title="Soul-Bound Pos", border_style="purple"))

    layout["footer"].update(Panel(Text.from_markup("\n".join(state.logs)), title="System Logs", border_style="dim cyan"))

# --- Stream Wards ---

async def stream_manager(forge):
    pub_url = "wss://stream.bybit.com/v5/public/linear" if not IS_TESTNET else "wss://stream-testnet.bybit.com/v5/public/linear"
    async with websockets.connect(pub_url) as ws:
        await ws.send(json.dumps({"op": "subscribe", "args": [f"tickers.{SYMBOL}", f"kline.1.{SYMBOL}"]}))
        state.is_connected = True
        while True:
            try:
                data = json.loads(await ws.recv())

                # --- KEYERROR WARD ---
                if "data" not in data: continue

                # Ticker handling
                if data.get("topic") == f"tickers.{SYMBOL}":
                    # Verify key exists before invocation
                    if "lastPrice" in data["data"]:
                        state.price = Decimal(data["data"]["lastPrice"])

                # Kline handling
                if data.get("topic") == f"kline.1.{SYMBOL}":
                    k = data["data"][0]
                    if k.get("confirm"):
                        state.ohlc.append((float(k["high"]), float(k["low"]), float(k["close"])))
                        if state.is_ready:
                            update_oracle_indicators()
                            # Execution logic
                            if not state.trade_active and (time.time() - state.last_ritual > COOLDOWN_SECONDS):
                                is_bull = float(state.price) > state.macro_trend
                                if is_bull and state.fisher > state.trigger and state.fisher < -ENTRY_THRESHOLD:
                                    await execute_trade(forge, "Buy")
                                elif not is_bull and state.fisher < state.trigger and state.fisher > ENTRY_THRESHOLD:
                                    await execute_trade(forge, "Sell")
            except: continue

async def private_stream():
    priv_url = "wss://stream.bybit.com/v5/private" if not IS_TESTNET else "wss://stream-testnet.bybit.com/v5/private"
    async with websockets.connect(priv_url) as ws:
        expires = int(time.time() * 1000) + 10000
        sig = hmac.new(API_SECRET.encode(), f"GET/realtime{expires}".encode(), hashlib.sha256).hexdigest()
        await ws.send(json.dumps({"op": "auth", "args": [API_KEY, expires, sig]}))
        await ws.send(json.dumps({"op": "subscribe", "args": ["position"]}))
        while True:
            try:
                data = json.loads(await ws.recv())
                if data.get("topic") == "position" and "data" in data:
                    active = [p for p in data["data"] if p["symbol"] == SYMBOL and Decimal(p["size"]) > 0]
                    if active:
                        p = active[0]
                        state.trade_active, state.side, state.upnl = True, p["side"], Decimal(p["unrealisedPnl"])
                    else:
                        state.trade_active, state.side, state.upnl = False, "HOLD", Decimal("0")
            except: continue

async def main():
    async with BybitForge() as forge:
        # Initial Divinity
        res = await forge.call("GET", "/v5/market/instruments-info", {"category": CATEGORY, "symbol": SYMBOL})
        if res.get('retCode') == 0:
            specs = res['result']['list'][0]
            state.price_prec = abs(Decimal(specs['priceFilter']['tickSize']).normalize().as_tuple().exponent)
            state.qty_step = Decimal(specs['lotSizeFilter']['qtyStep'])

        k_res = await forge.call("GET", "/v5/market/kline", {"category": CATEGORY, "symbol": SYMBOL, "interval": "1", "limit": 60})
        if k_res.get('retCode') == 0:
            for k in k_res['result']['list'][::-1]:
                state.ohlc.append((float(k[2]), float(k[3]), float(k[4])))
            state.is_ready = True
            update_oracle_indicators()

        layout = Layout()
        layout.split_column(Layout(name="header", size=3), Layout(name="main", ratio=1), Layout(name="footer", size=10))
        layout["main"].split_row(Layout(name="oracle"), Layout(name="position"))

        with Live(layout, refresh_per_second=4, screen=True):
            async def refresh_loop():
                while True:
                    render_dashboard(layout)
                    await asyncio.sleep(0.2)

            await asyncio.gather(stream_manager(forge), private_stream(), refresh_loop())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
