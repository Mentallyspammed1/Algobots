#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BCH Sentinel v3.1 - The Awakened TUI
Forged by Pyrmethus: Fixed KeyError, proper session cleanup, and stream resilience.
"""

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
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.live import Live
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
ENTRY_THRESHOLD = 1.8
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
        
        self.prices = deque(maxlen=100)
        self.smoothed = deque(maxlen=100)
        self.logs = deque(maxlen=8)
        self.is_ready = False
        self.is_connected = False

state = SentinelState()

# --- Alchemy: Technical Indicators ---
def super_smoother(prices: deque, smoothed: deque) -> float:
    if len(prices) < 2: return float(prices[-1])
    a1 = np.exp(-1.414 * np.pi / 10.0)
    b1 = 2 * a1 * np.cos(1.414 * np.pi / 10.0)
    c2, c3 = b1, -a1 * a1
    c1 = 1 - c2 - c3
    val = (prices[-1] + prices[-2]) / 2.0
    prev = smoothed[-1] if smoothed else prices[-1]
    prev2 = smoothed[-2] if len(smoothed) > 1 else prices[-1]
    return c1 * val + c2 * prev - c3 * prev2

def fisher_transform(values: deque) -> float:
    if len(values) < FISHER_PERIOD: return 0.0
    arr = list(values)[-FISHER_PERIOD:]
    mx, mn = max(arr), min(arr)
    if mx == mn: return 0.0
    raw = 2 * ((arr[-1] - mn) / (mx - mn + 1e-9) - 0.5) # Epsilon ward
    val = np.clip(raw, -0.999, 0.999)
    return 0.5 * np.log((1 + val) / (1 - val))

# --- The Forge: API Client ---
class BybitForge:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.base = "https://api-testnet.bybit.com" if IS_TESTNET else "https://api.bybit.com"

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def _sign(self, ts: str, payload: str) -> str:
        return hmac.new(API_SECRET.encode(), (ts + API_KEY + "5000" + payload).encode(), hashlib.sha256).hexdigest()

    async def call(self, method: str, path: str, params: dict = None, signed: bool = False):
        if not self.session: return {"retCode": -1, "retMsg": "Session Closed"}
        ts = str(int(time.time() * 1000))
        req_params = params or {}
        param_str = urllib.parse.urlencode(req_params) if method == "GET" else json.dumps(req_params)
        
        headers = {"Content-Type": "application/json"}
        if signed:
            headers.update({
                "X-BAPI-API-KEY": API_KEY,
                "X-BAPI-SIGN": self._sign(ts, param_str),
                "X-BAPI-TIMESTAMP": ts,
                "X-BAPI-RECV-WINDOW": "5000"
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
    
    risk_amt = state.balance * (RISK_PERCENT / 100) * LEVERAGE
    if state.price == 0: return
    raw_qty = risk_amt / state.price
    qty = (raw_qty // state.qty_step) * state.qty_step
    
    if qty <= 0: return

    tp = (state.price * Decimal("1.006")) if side == "Buy" else (state.price * Decimal("0.994"))
    sl = (state.price * Decimal("0.995")) if side == "Buy" else (state.price * Decimal("1.005"))

    order = {
        "category": CATEGORY, "symbol": SYMBOL, "side": side,
        "orderType": "Market", "qty": str(qty),
        "takeProfit": f"{tp:.{state.price_prec}f}", "stopLoss": f"{sl:.{state.price_prec}f}"
    }
    
    res = await forge.call("POST", "/v5/order/create", order, signed=True)
    if res.get('retCode') == 0:
        state.last_ritual = time.time()
        state.logs.append(f"[bold green]⚔️ Ritual Bound: {side} {qty} @ {state.price}")

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
    layout["header"].update(Panel(Text(f"BCH SENTINEL v3.1 | Oracle Ready: {state.is_ready} | {time.strftime('%X')}", justify="center", style="bold cyan"), border_style="magenta"))
    oracle_text = Text()
    oracle_text.append(f"\nPrice:  {state.price} USDT\n", style="white")
    oracle_text.append(f"Fisher: {state.fisher:+.4f}\n", style="bold yellow")
    oracle_text.append(f"Trig:   {state.trigger:+.4f}\n", style="dim yellow")
    layout["oracle"].update(Panel(oracle_text, title="[bold]Ehlers Fisher Oracle", border_style="blue"))
    
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
                    
                    # Safe Key Verification Ward
                    if data.get("topic") == f"tickers.{SYMBOL}" and "data" in data:
                        tick = data["data"]
                        if "lastPrice" in tick:
                            state.price = Decimal(tick["lastPrice"])
                            state.prices.append(float(state.price))
                            
                            if state.is_ready:
                                state.trigger = state.fisher
                                state.smoothed.append(super_smoother(state.prices, state.smoothed))
                                state.fisher = fisher_transform(state.smoothed)
                                
                                if not state.trade_active and (time.time() - state.last_ritual > COOLDOWN_SECONDS):
                                    if state.fisher > state.trigger and state.fisher < -ENTRY_THRESHOLD:
                                        await execute_trade(forge, "Buy")
                                    elif state.fisher < state.trigger and state.fisher > ENTRY_THRESHOLD:
                                        await execute_trade(forge, "Sell")
        except Exception as e:
            state.is_connected = False
            state.logs.append(f"[red]Public Stream severed: {str(e)[:40]}... Reconnecting.")
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
        except Exception as e:
            await asyncio.sleep(5)

async def main():
    async with BybitForge() as forge:
        # Initial Divinity: Specs & Historical Data
        res = await forge.call("GET", "/v5/market/instruments-info", {"category": CATEGORY, "symbol": SYMBOL})
        if res.get('retCode') == 0:
            specs = res['result']['list'][0]
            state.price_prec = abs(Decimal(specs['priceFilter']['tickSize']).normalize().as_tuple().exponent)
            state.qty_step = Decimal(specs['lotSizeFilter']['qtyStep'])

        state.logs.append("[cyan]Fetching historical memory...")
        k_res = await forge.call("GET", "/v5/market/kline", {"category": CATEGORY, "symbol": SYMBOL, "interval": "1", "limit": 50})
        if k_res.get('retCode') == 0:
            for k in k_res['result']['list'][::-1]:
                state.prices.append(float(k[4]))
                state.smoothed.append(super_smoother(state.prices, state.smoothed))
            state.is_ready = True
            state.logs.append("[green]Historical memory absorbed.")

        pub_url = "wss://stream.bybit.com/v5/public/linear" if not IS_TESTNET else "wss://stream-testnet.bybit.com/v5/public/linear"
        priv_url = "wss://stream.bybit.com/v5/private" if not IS_TESTNET else "wss://stream-testnet.bybit.com/v5/private"

        layout = create_layout()
        with Live(layout, refresh_per_second=4, screen=True):
            # TUI Refresh Task
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
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[!] The Sentinel ritual has concluded gracefully.")