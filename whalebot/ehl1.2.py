#!/usr/bin/env python3
"""
BCH Sentinel v3.7 - The Force Alchemist
Forged by Pyrmethus: Harmonic Exits, Sigma-Risk Sizing, and Spread Wards.
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
BASE_RISK_PERCENT = Decimal("1.5")
DAILY_LOSS_LIMIT = Decimal("5.0")
FISHER_PERIOD = 10
ATR_PERIOD = 14
MACRO_PERIOD = 50
ENTRY_THRESHOLD = 2.0
COOLDOWN_SECONDS = 45 # Tightened for scalping

class SentinelState:
    def __init__(self):
        self.price = Decimal("0.0")
        self.best_bid = Decimal("0.0")
        self.best_ask = Decimal("0.0")
        self.fisher = 0.0
        self.trigger = 0.0
        self.atr = 0.0
        self.macro_trend = 0.0
        self.velocity = 0.0
        self.balance = Decimal("0.0")
        self.initial_balance = Decimal("0.0")
        self.daily_pnl = Decimal("0.0")

        self.trade_active = False
        self.side = "HOLD"
        self.entry_price = Decimal("0.0")
        self.upnl = Decimal("0.0")
        self.last_ritual = 0
        self.be_moved = False

        self.price_prec = 2
        self.qty_step = Decimal("0.01")

        self.ohlc = deque(maxlen=100)
        self.value1 = deque(maxlen=100)
        self.fisher_series = deque(maxlen=100)
        self.logs = deque(maxlen=12)

        self.is_ready = False
        self.is_connected = False

state = SentinelState()

# --- Alchemy: Technical Indicators ---

def calculate_super_smoother(data_list: list[float], period: int) -> float:
    if len(data_list) < 3: return data_list[-1] if data_list else 0.0
    a1 = np.exp(-1.414 * np.pi / period)
    b1 = 2 * a1 * np.cos(1.414 * np.pi / period)
    c2, c3 = b1, -a1 * a1
    c1 = 1 - c2 - c3
    return c1 * (data_list[-1] + data_list[-2]) / 2 + c2 * data_list[-2] + c3 * data_list[-3]

def update_oracle_indicators():
    if len(state.ohlc) < MACRO_PERIOD: return
    closes = [x[2] for x in state.ohlc]

    state.macro_trend = calculate_super_smoother(closes, MACRO_PERIOD)

    tr_list = []
    for i in range(1, len(state.ohlc)):
        h, l, c = state.ohlc[i]
        pc = state.ohlc[i-1][2]
        tr_list.append(max(h - l, abs(h - pc), abs(l - pc)))
    state.atr = np.mean(tr_list[-ATR_PERIOD:])

    recent_changes = np.diff(closes[-20:])
    state.velocity = (recent_changes[-1] - np.mean(recent_changes)) / (np.std(recent_changes) + 1e-9)

    window = []
    for i in range(FISHER_PERIOD, 0, -1):
        window.append(calculate_super_smoother(closes[:-i] if i > 0 else closes, 10))

    mx, mn = max(window), min(window)
    raw_val = 2 * ((window[-1] - mn) / (mx - mn + 1e-9) - 0.5)

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

    async def ignite(self):
        if not self.session: self.session = aiohttp.ClientSession()

    async def __aenter__(self):
        await self.ignite()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session: await self.session.close()

    def _sign(self, ts: str, payload: str) -> str:
        return hmac.new(API_SECRET.encode(), (ts + API_KEY + "5000" + payload).encode(), hashlib.sha256).hexdigest()

    async def call(self, method: str, path: str, params: dict = None, signed: bool = False):
        if not self.session: await self.ignite()
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

# --- Tactical Logic ---

async def manage_active_trade(forge):
    if not state.trade_active: return

    curr_f = float(state.price)
    entry_f = float(state.entry_price)
    atr_f = state.atr
    tp_dist = atr_f * 3.5

    # 1. Alchemical Break-Even Move
    if not state.be_moved:
        progress = (curr_f - entry_f) / tp_dist if state.side == "Buy" else (entry_f - curr_f) / tp_dist
        if progress > 0.45: # Move to BE slightly earlier
            be_price = entry_f + (atr_f * 0.1) if state.side == "Buy" else entry_f - (atr_f * 0.1)
            res = await forge.call("POST", "/v5/position/set-trading-stop", {
                "category": CATEGORY, "symbol": SYMBOL, "stopLoss": f"{be_price:.{state.price_prec}f}", "positionIdx": 0
            }, signed=True)
            if res.get('retCode') == 0:
                state.be_moved = True
                state.logs.append("[cyan]SHIELD: SL moved to Break-Even")

    # 2. Harmonic Zero-Cross Exit
    # Exit if Fisher crosses zero against the trade direction
    if state.side == "Buy" and state.fisher < 0 and state.trigger > 0:
        state.logs.append("[orange1]HARMONIC: Zero-Cross Exit (Long)")
        await forge.call("POST", "/v5/order/create", {
            "category": CATEGORY, "symbol": SYMBOL, "side": "Sell", "orderType": "Market", "qty": str(state.qty), "reduceOnly": True
        }, signed=True)
    elif state.side == "Sell" and state.fisher > 0 and state.trigger < 0:
        state.logs.append("[orange1]HARMONIC: Zero-Cross Exit (Short)")
        await forge.call("POST", "/v5/order/create", {
            "category": CATEGORY, "symbol": SYMBOL, "side": "Buy", "orderType": "Market", "qty": str(state.qty), "reduceOnly": True
        }, signed=True)

async def execute_trade(forge, side: str):
    if state.daily_pnl <= -(state.initial_balance * DAILY_LOSS_LIMIT / 100):
        state.logs.append("[bold red]KILL-SWITCH: Loss Limit Active")
        return

    # Spread Ward: Pause if spread is too wide
    spread = state.best_ask - state.best_bid
    if spread > (Decimal(str(state.atr)) * Decimal("0.15")):
        state.logs.append("[yellow]WARD: Spread too wide, skipping.")
        return

    # Sigma-Risk Sizing: Scale risk by velocity force
    conviction_mult = Decimal(str(np.clip(abs(state.velocity), 0.8, 1.5)))
    risk_amt = state.balance * (BASE_RISK_PERCENT / 100) * conviction_mult * LEVERAGE

    if state.price == 0: return
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
        state.be_moved = False
        state.logs.append(f"[bold green]⚔️ {side} Bound (Risk x{conviction_mult:.1f})")

# --- Vision: TUI ---

def update_tui(layout):
    # Kinetic Border Color
    border_col = "lime" if abs(state.velocity) > 1.5 else "cyan"

    layout["header"].update(Panel(Text(f"BCH SENTINEL v3.7 | Force Alchemist | PnL: {state.daily_pnl:+.2f}", justify="center", style="bold white"), border_style="magenta"))

    oracle_text = Text()
    oracle_text.append(f"\nPrice:    {state.price} USDT\n", style="white")

    trend = "BULL" if float(state.price) > state.macro_trend else "BEAR"
    oracle_text.append(f"Trend:    {trend}\n", style="bold lime" if trend == "BULL" else "bold red")

    f_col = "bold lime" if state.fisher > state.trigger else "bold red"
    oracle_text.append(f"Fisher:   {state.fisher:+.4f}\n", style=f_col)

    v_col = "bold gold1" if abs(state.velocity) > 1.5 else "dim white"
    oracle_text.append(f"Velocity: {state.velocity:+.2f} σ", style=v_col)

    layout["oracle"].update(Panel(oracle_text, title="Harmonic Oracle", border_style=border_col))

    pos_table = Table.grid(expand=True)
    pnl_col = "green" if state.upnl >= 0 else "red"
    pos_table.add_row("SIDE:", f"[bold]{state.side}[/]")
    pos_table.add_row("uPnL:", f"[{pnl_col}]{state.upnl:+.2f} USDT[/]")
    pos_table.add_row("BE:", "LOCKED" if state.be_moved else "WAITING")
    pos_table.add_row("BAL:", f"{state.balance:.2f} USDT")
    layout["position"].update(Panel(pos_table, title="Kinetic Position", border_style="purple"))

    layout["footer"].update(Panel(Text.from_markup("\n".join(state.logs)), title="System Logs", border_style="dim cyan"))

# --- Engine ---

async def stream_manager(forge):
    pub_url = "wss://stream.bybit.com/v5/public/linear" if not IS_TESTNET else "wss://stream-testnet.bybit.com/v5/public/linear"
    async with websockets.connect(pub_url) as ws:
        await ws.send(json.dumps({"op": "subscribe", "args": [f"tickers.{SYMBOL}", f"orderbook.1.{SYMBOL}"]}))
        state.is_connected = True
        while True:
            try:
                data = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                topic = data.get("topic", "")

                if "tickers" in topic:
                    state.price = Decimal(data["data"].get("lastPrice", state.price))
                    if state.trade_active: await manage_active_trade(forge)

                if "orderbook" in topic:
                    state.best_bid = Decimal(data["data"]["b"][0][0])
                    state.best_ask = Decimal(data["data"]["a"][0][0])

            except: continue

async def kline_engine(forge):
    """Separate engine for indicator updates to prevent blocking."""
    while True:
        try:
            k_res = await forge.call("GET", "/v5/market/kline", {"category": CATEGORY, "symbol": SYMBOL, "interval": "1", "limit": 60})
            if k_res.get('retCode') == 0:
                state.ohlc.clear()
                for k in k_res['result']['list'][::-1]:
                    state.ohlc.append((float(k[2]), float(k[3]), float(k[4])))
                state.is_ready = True
                update_oracle_indicators()

                if not state.trade_active and (time.time() - state.last_ritual > COOLDOWN_SECONDS):
                    is_bull = float(state.price) > state.macro_trend
                    if abs(state.velocity) > 0.5:
                        if is_bull and state.fisher > state.trigger and state.fisher < -ENTRY_THRESHOLD:
                            await execute_trade(forge, "Buy")
                        elif not is_bull and state.fisher < state.trigger and state.fisher > ENTRY_THRESHOLD:
                            await execute_trade(forge, "Sell")
            await asyncio.sleep(5) # Indicators update every 5s
        except: await asyncio.sleep(2)

async def private_manager(forge):
    priv_url = "wss://stream.bybit.com/v5/private" if not IS_TESTNET else "wss://stream-testnet.bybit.com/v5/private"
    async with websockets.connect(priv_url) as ws:
        expires = int(time.time() * 1000) + 10000
        sig = hmac.new(API_SECRET.encode(), f"GET/realtime{expires}".encode(), hashlib.sha256).hexdigest()
        await ws.send(json.dumps({"op": "auth", "args": [API_KEY, expires, sig]}))
        await ws.send(json.dumps({"op": "subscribe", "args": ["position", "wallet"]}))

        # Initial Force Fetch for Balance
        bal_init = await forge.call("GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED"}, signed=True)
        if bal_init.get('retCode') == 0:
            state.balance = Decimal(bal_init['result']['list'][0]['coin'][0]['walletBalance'])
            state.initial_balance = state.balance

        while True:
            try:
                data = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                topic = data.get("topic")
                if topic == "position" and "data" in data:
                    active = [p for p in data["data"] if p["symbol"] == SYMBOL and Decimal(p["size"]) > 0]
                    if active:
                        p = active[0]
                        state.trade_active, state.side, state.upnl = True, p["side"], Decimal(p["unrealisedPnl"])
                        state.entry_price = Decimal(p["avgPrice"])
                        state.qty = Decimal(p["size"])
                    else:
                        state.trade_active, state.side, state.upnl, state.be_moved = False, "HOLD", Decimal("0"), False
                if topic == "wallet" and "data" in data:
                    state.balance = Decimal(data["data"][0]["coin"][0]["walletBalance"])
                    state.daily_pnl = state.balance - state.initial_balance
            except: continue

async def main():
    async with BybitForge() as forge:
        await forge.ignite()
        res = await forge.call("GET", "/v5/market/instruments-info", {"category": CATEGORY, "symbol": SYMBOL})
        if res.get('retCode') == 0:
            specs = res['result']['list'][0]
            state.price_prec = abs(Decimal(specs['priceFilter']['tickSize']).normalize().as_tuple().exponent)
            state.qty_step = Decimal(specs['lotSizeFilter']['qtyStep'])

        layout = Layout()
        layout.split_column(Layout(name="header", size=3), Layout(name="main", ratio=1), Layout(name="footer", size=14))
        layout["main"].split_row(Layout(name="oracle"), Layout(name="position"))

        with Live(layout, refresh_per_second=5, screen=True):
            async def refresh():
                while True:
                    update_tui(layout)
                    await asyncio.sleep(0.2)
            await asyncio.gather(stream_manager(forge), kline_engine(forge), private_manager(forge), refresh())

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
