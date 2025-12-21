#!/usr/bin/env python3
"""
BCH Sentinel v3.2 - The Harmonic Rebirth
Forged by Pyrmethus: Enhanced Fisher logic, crossover detection, and persistent sessions.
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

# --- Load the Aether ---
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
ENTRY_THRESHOLD = 2.0  # Increased for higher conviction
COOLDOWN_SECONDS = 300

class SentinelState:
    def __init__(self):
        self.price = Decimal("0")
        self.fisher = 0.0
        self.trigger = 0.0
        self.balance = Decimal("0")
        self.trade_active = False
        self.side = "HOLD"
        self.qty = Decimal("0")
        self.entry = Decimal("0")
        self.upnl = Decimal("0")
        self.last_ritual = 0
        self.price_prec = 2
        self.qty_step = Decimal("0.01")

        # Buffers
        self.prices = deque(maxlen=50)
        self.smoothed = deque(maxlen=50)
        self.value1 = deque(maxlen=50) # Normalized Price Buffer
        self.fisher_series = deque(maxlen=50)

        self.logs = deque(maxlen=8)
        self.is_ready = False
        self.is_connected = False

state = SentinelState()

# --- Alchemy: Technical Indicators ---

def calculate_super_smoother(prices: deque, smoothed_series: deque) -> float:
    """A 2-pole Butterworth filter to eliminate aliasing noise."""
    if len(prices) < 2: return float(prices[-1])
    a1 = np.exp(-1.414 * np.pi / 10.0)
    b1 = 2 * a1 * np.cos(1.414 * np.pi / 10.0)
    c2, c3 = b1, -a1 * a1
    c1 = 1 - c2 - c3

    # Input is the average of current and prior price
    val = (prices[-1] + prices[-2]) / 2.0
    prev1 = smoothed_series[-1] if smoothed_series else val
    prev2 = smoothed_series[-2] if len(smoothed_series) > 1 else val

    return c1 * val + c2 * prev1 + c3 * prev2

def update_fisher_oracle():
    """Refined Ehlers Fisher Transform logic with Signal/Trigger Crossover."""
    if len(state.smoothed) < FISHER_PERIOD:
        return

    # 1. Get Min/Max over the period
    window = list(state.smoothed)[-FISHER_PERIOD:]
    mx, mn = max(window), min(window)

    # 2. Normalize and Smooth 'Value1'
    # Prevents infinite scaling and reduces noise
    raw_val = 0.0
    if (mx - mn) != 0:
        raw_val = 2 * ((window[-1] - mn) / (mx - mn) - 0.5)

    # Ehlers smoothing for the normalized value
    prev_v1 = state.value1[-1] if state.value1 else 0.0
    v1 = 0.33 * raw_val + 0.67 * prev_v1
    v1 = np.clip(v1, -0.999, 0.999)
    state.value1.append(v1)

    # 3. Calculate Fisher Series
    prev_fish = state.fisher_series[-1] if state.fisher_series else 0.0
    fish = 0.5 * np.log((1 + v1) / (1 - v1)) + 0.5 * prev_fish

    # 4. Trigger is the previous bar's Fisher (z^-1)
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
        if not self.session: return {"retCode": -1, "retMsg": "Void Closed"}
        ts = str(int(time.time() * 1000))
        req_params = params or {}
        param_str = urllib.parse.urlencode(req_params) if method == "GET" else json.dumps(req_params)

        headers = {"Content-Type": "application/json"}
        if signed:
            headers.update({
                "X-BAPI-API-KEY": API_KEY, "X-BAPI-SIGN": self._sign(ts, param_str),
                "X-BAPI-TIMESTAMP": ts, "X-BAPI-RECV-WINDOW": "5000"
            })

        url = self.base + path + (f"?{param_str}" if method == "GET" else "")
        try:
            async with self.session.request(method, url, headers=headers, data=None if method == "GET" else param_str, timeout=10) as resp:
                return await resp.json()
        except Exception as e:
            return {"retCode": -1, "retMsg": str(e)}

# --- Rituals: Logic ---
async def execute_trade(forge, side: str):
    bal_res = await forge.call("GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED"}, signed=True)
    if bal_res.get('retCode') == 0:
        try:
            state.balance = Decimal(bal_res['result']['list'][0]['coin'][0]['walletBalance'])
        except (KeyError, IndexError): pass

    if state.price == 0: return
    risk_amt = state.balance * (RISK_PERCENT / 100) * LEVERAGE
    qty = ( (risk_amt / state.price) // state.qty_step) * state.qty_step

    if qty <= 0: return

    # Adaptive Exit Ward: 0.8% TP, 0.5% SL
    tp = (state.price * Decimal("1.008")) if side == "Buy" else (state.price * Decimal("0.992"))
    sl = (state.price * Decimal("0.995")) if side == "Buy" else (state.price * Decimal("1.005"))

    order = {
        "category": CATEGORY, "symbol": SYMBOL, "side": side,
        "orderType": "Market", "qty": str(qty),
        "takeProfit": f"{tp:.{state.price_prec}f}", "stopLoss": f"{sl:.{state.price_prec}f}"
    }

    res = await forge.call("POST", "/v5/order/create", order, signed=True)
    if res.get('retCode') == 0:
        state.last_ritual = time.time()
        state.logs.append(f"[bold green]⚔️ {side} Ritual Bound: {qty} @ {state.price}")

# --- Vision: TUI Layout ---
def create_layout() -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main", ratio=1),
        Layout(name="footer", size=10)
    )
    layout["main"].split_row(Layout(name="oracle"), Layout(name="position"))
    return layout

def update_dashboard(layout: Layout):
    layout["header"].update(Panel(Text(f"BCH SENTINEL v3.2 | Oracle: {'LOCKED' if state.is_ready else 'WARMING'} | {time.strftime('%X')}", justify="center", style="bold cyan"), border_style="magenta"))

    # Oracle Visualization
    oracle_text = Text()
    oracle_text.append(f"\nPrice:  {state.price} USDT\n", style="white")

    # Neon Fisher Crossover Display
    f_style = "bold lime" if state.fisher > state.trigger else "bold red"
    oracle_text.append(f"Fisher: {state.fisher:+.4f}\n", style=f_style)
    oracle_text.append(f"Trigger: {state.trigger:+.4f}\n", style="dim yellow")

    # Hysteresis Meter
    meter_color = "green" if abs(state.fisher) > ENTRY_THRESHOLD else "blue"
    oracle_text.append(f"\nConviction: {abs(state.fisher):.2f} / {ENTRY_THRESHOLD}", style=meter_color)

    layout["oracle"].update(Panel(oracle_text, title="[bold]Ehlers Fisher Oracle", border_style="blue"))

    # Position Info
    pos_table = Table.grid(expand=True)
    pnl_color = "green" if state.upnl >= 0 else "red"
    pos_table.add_row("SIDE:", f"[bold]{state.side}[/]")
    pos_table.add_row("QTY:", str(state.qty))
    pos_table.add_row("uPnL:", f"[{pnl_color}]{state.upnl:+.2f} USDT[/]")
    pos_table.add_row("BAL:", f"{state.balance:.2f} USDT")
    layout["position"].update(Panel(pos_table, title="[bold]Soul-Bound Position", border_style="purple"))

    log_text = Text.from_markup("\n".join(state.logs))
    layout["footer"].update(Panel(log_text, title="Ritual Logs", border_style="dim cyan"))

# --- Stream Wards ---

async def public_stream(ws_url, forge):
    while True:
        try:
            async with websockets.connect(ws_url) as ws:
                await ws.send(json.dumps({"op": "subscribe", "args": [f"tickers.{SYMBOL}"]}))
                state.is_connected = True
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    if data.get("topic") == f"tickers.{SYMBOL}" and "data" in data:
                        tick = data["data"]
                        if "lastPrice" in tick:
                            state.price = Decimal(tick["lastPrice"])
                            state.prices.append(float(state.price))

                            if state.is_ready:
                                # Apply SuperSmoother
                                new_smooth = calculate_super_smoother(state.prices, state.smoothed)
                                state.smoothed.append(new_smooth)

                                # Update Fisher and Signal Trigger
                                update_fisher_oracle()

                                # --- UPGRADED SIGNAL LOGIC ---
                                # Check for crossover + threshold
                                cooldown_expired = (time.time() - state.last_ritual > COOLDOWN_SECONDS)
                                if not state.trade_active and cooldown_expired:
                                    # Bullish Cross: Fisher crosses ABOVE trigger in oversold territory
                                    if state.fisher > state.trigger and state.fisher < -ENTRY_THRESHOLD:
                                        await execute_trade(forge, "Buy")
                                    # Bearish Cross: Fisher crosses BELOW trigger in overbought territory
                                    elif state.fisher < state.trigger and state.fisher > ENTRY_THRESHOLD:
                                        await execute_trade(forge, "Sell")
        except Exception as e:
            state.is_connected = False
            state.logs.append(f"[red]Stream Error: {str(e)[:30]}")
            await asyncio.sleep(5)

async def private_stream(ws_url):
    while True:
        try:
            expires = int(time.time() * 1000) + 10000
            sig = hmac.new(API_SECRET.encode(), f"GET/realtime{expires}".encode(), hashlib.sha256).hexdigest()
            async with websockets.connect(ws_url) as ws:
                await ws.send(json.dumps({"op": "auth", "args": [API_KEY, expires, sig]}))
                await ws.send(json.dumps({"op": "subscribe", "args": ["position"]}))
                while True:
                    data = json.loads(await ws.recv())
                    if data.get("topic") == "position" and "data" in data:
                        active = [p for p in data["data"] if p["symbol"] == SYMBOL and Decimal(p["size"]) > 0]
                        if active:
                            p = active[0]
                            state.trade_active, state.side = True, p["side"]
                            state.qty, state.entry = Decimal(p["size"]), Decimal(p["avgPrice"])
                            state.upnl = Decimal(p["unrealisedPnl"])
                        else:
                            state.trade_active, state.side = False, "HOLD"
                            state.qty, state.upnl = Decimal("0"), Decimal("0")
        except Exception: await asyncio.sleep(5)

async def main():
    async with BybitForge() as forge:
        # Pre-fetch Divinity
        res = await forge.call("GET", "/v5/market/instruments-info", {"category": CATEGORY, "symbol": SYMBOL})
        if res.get('retCode') == 0:
            specs = res['result']['list'][0]
            state.price_prec = abs(Decimal(specs['priceFilter']['tickSize']).normalize().as_tuple().exponent)
            state.qty_step = Decimal(specs['lotSizeFilter']['qtyStep'])

        # Absorbing historical candles to prime the oracle
        k_res = await forge.call("GET", "/v5/market/kline", {"category": CATEGORY, "symbol": SYMBOL, "interval": "1", "limit": 50})
        if k_res.get('retCode') == 0:
            for k in k_res['result']['list'][::-1]:
                state.prices.append(float(k[4]))
                state.smoothed.append(calculate_super_smoother(state.prices, state.smoothed))
                update_fisher_oracle()
            state.is_ready = True

        pub_url = "wss://stream.bybit.com/v5/public/linear" if not IS_TESTNET else "wss://stream-testnet.bybit.com/v5/public/linear"
        priv_url = "wss://stream.bybit.com/v5/private" if not IS_TESTNET else "wss://stream-testnet.bybit.com/v5/private"

        layout = create_layout()
        with Live(layout, refresh_per_second=4, screen=True):
            async def tui_refresh():
                while True:
                    update_dashboard(layout)
                    await asyncio.sleep(0.25)

            await asyncio.gather(
                public_stream(pub_url, forge),
                private_stream(priv_url),
                tui_refresh()
            )

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
