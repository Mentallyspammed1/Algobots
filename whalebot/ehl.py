#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BCH Sentinel v4.1 - THE ASTRAL LINK
Forged by Pyrmethus: Context Protocol Fixed, ATR-Risk Parity, & Fisher Reversal.
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
from typing import Optional, Dict, Any, List, Tuple

import aiohttp
import websockets
from dotenv import load_dotenv
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.live import Live
from rich.table import Table
from rich.text import Text

# --- Load the Arcane Sigils ---
load_dotenv()
API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')
IS_TESTNET = os.getenv('BYBIT_TESTNET', 'false').lower() == 'true'

# Global Constants
SYMBOL = "BCHUSDT"
CATEGORY = "linear"
LEVERAGE = 10
BASE_RISK_PERCENT = Decimal("1.5")
DAILY_LOSS_LIMIT = Decimal("5.0") 
COOLDOWN_SECONDS = 60

class SentinelState:
    def __init__(self):
        # Equity & Risk Management
        self.balance = Decimal("0.0")
        self.initial_balance = Decimal("0.0")
        self.high_water_mark_equity = Decimal("0.0")
        self.daily_pnl = Decimal("0.0")
        self.cooldown_seconds = COOLDOWN_SECONDS
        
        # Market Data
        self.price = Decimal("0.0")
        self.ohlc = deque(maxlen=100)
        
        # Oracle Indicators
        self.fisher = 0.0
        self.fisher_series = deque(maxlen=5)
        self.atr = 0.0
        self.macro_trend = 0.0
        self.trend_strength = 0.0
        self.velocity = 0.0 
        self.dynamic_threshold = 1.5
        
        # Position Logic
        self.trade_active = False
        self.side = "HOLD"
        self.entry_price = Decimal("0.0")
        self.qty = Decimal("0.0")
        self.upnl = Decimal("0.0")
        self.last_ritual = 0
        self.initial_sl_distance = Decimal("0.0")
        self.partial_tp_claimed = False
        self.high_water_mark = Decimal("0.0")
        
        # Precision
        self.price_prec = 2
        self.qty_step = Decimal("0.01")
        
        self.logs = deque(maxlen=10)
        self.is_ready = False

state = SentinelState()

# --- Alchemy: Indicators ---

def super_smoother(data: List[float], period: int) -> float:
    if len(data) < 3: return data[-1] if data else 0.0
    a = np.exp(-1.414 * 3.14159 / period)
    b = 2 * a * np.cos(1.414 * 3.14159 / period)
    c2, c3 = b, -a * a
    c1 = 1 - c2 - c3
    return c1 * (data[-1] + data[-2]) / 2 + c2 * data[-2] + c3 * data[-3]

def update_oracle():
    if len(state.ohlc) < 50: return
    closes = [x[2] for x in state.ohlc]
    highs = [x[0] for x in state.ohlc]
    lows = [x[1] for x in state.ohlc]
    
    # ATR (Volatility)
    tr = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])) for i in range(1, len(state.ohlc))]
    state.atr = float(np.mean(tr[-14:]))
    
    # Macro Trend
    state.macro_trend = super_smoother(closes, 50)
    state.trend_strength = abs(float(state.price) - state.macro_trend) / (state.atr if state.atr > 0 else 1.0)
    
    # Fisher Transform Reversal Logic
    window = closes[-10:]
    hh, ll = max(window), min(window)
    raw = 2 * ((closes[-1] - ll) / (hh - ll + 1e-9) - 0.5)
    raw = np.clip(raw, -0.999, 0.999)
    
    fish = 0.5 * np.log((1 + raw) / (1 - raw))
    state.fisher = fish
    state.fisher_series.append(fish)
    
    # Momentum Velocity
    state.velocity = (closes[-1] - closes[-5]) / (state.atr + 1e-9)

# --- The Forge: API Client ---

class BybitForge:
    def __init__(self):
        self.session = None
        self.base = "https://api-testnet.bybit.com" if IS_TESTNET else "https://api.bybit.com"

    async def ignite(self):
        if not self.session: self.session = aiohttp.ClientSession()

    async def __aenter__(self):
        """Asynchronous Context Manager Protocol Start"""
        await self.ignite()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Asynchronous Context Manager Protocol Exit"""
        if self.session: await self.session.close()

    def _sign(self, ts: str, payload: str) -> str:
        return hmac.new(API_SECRET.encode(), (ts + API_KEY + "5000" + payload).encode(), hashlib.sha256).hexdigest()

    async def call(self, method: str, path: str, params: dict = None, signed: bool = False) -> Dict[str, Any]:
        if not self.session: await self.ignite()
        ts = str(int(time.time() * 1000))
        req_params = params or {}
        p_str = urllib.parse.urlencode(req_params) if method == "GET" else json.dumps(req_params)
        
        headers = {"Content-Type": "application/json"}
        if signed:
            headers.update({
                "X-BAPI-API-KEY": API_KEY,
                "X-BAPI-SIGN": self._sign(ts, p_str),
                "X-BAPI-TIMESTAMP": ts,
                "X-BAPI-RECV-WINDOW": "5000"
            })
            
        url = self.base + path + (f"?{p_str}" if method == "GET" else "")
        try:
            async with self.session.request(method, url, headers=headers, data=None if method == "GET" else p_str) as r:
                data = await r.json()
                return data if data is not None else {"retCode": -1, "retMsg": "Null Response"}
        except Exception as e:
            return {"retCode": -1, "retMsg": str(e)}

# --- Tactical Logic ---

async def execute_trade(forge: BybitForge, side: str):
    if state.daily_pnl <= -(state.high_water_mark_equity * DAILY_LOSS_LIMIT / 100):
        return

    atr_dec = Decimal(str(round(state.atr, 4)))
    sl_mult = Decimal("2.0")
    
    if side == "Buy":
        sl = state.price - (atr_dec * sl_mult)
        sl_dist = state.price - sl
    else:
        sl = state.price + (atr_dec * sl_mult)
        sl_dist = sl - state.price

    if sl_dist <= 0: return

    # ATR Risk-Parity Sizing (Capital * Risk% / SL Distance)
    conviction = Decimal(str(np.clip(abs(state.velocity), 0.8, 1.5)))
    risk_usd = state.balance * (BASE_RISK_PERCENT / 100) * conviction
    raw_qty = risk_usd / sl_dist
    qty = (raw_qty // state.qty_step) * state.qty_step

    if qty <= 0: return

    tp_mult = Decimal("3.5") * Decimal(str(np.clip(1.0 - (abs(state.velocity) * 0.1), 0.7, 1.2)))
    tp = (state.price + atr_dec * tp_mult) if side == "Buy" else (state.price - atr_dec * tp_mult)

    order = {
        "category": CATEGORY, "symbol": SYMBOL, "side": side, "orderType": "Market", "qty": str(qty),
        "takeProfit": f"{tp:.{state.price_prec}f}", "stopLoss": f"{sl:.{state.price_prec}f}",
        "tpTriggerBy": "LastPrice", "slTriggerBy": "LastPrice"
    }
    
    res = await forge.call("POST", "/v5/order/create", order, signed=True)
    if res.get('retCode') == 0:
        state.last_ritual = time.time()
        state.initial_sl_distance = sl_dist
        state.partial_tp_claimed = False
        state.high_water_mark = state.price
        state.logs.append(f"[bold green]⚔️ {side} Kinetic Entry | Risk: {risk_usd:.2f} USDT")

async def manage_trade(forge: BybitForge):
    if not state.trade_active: return
    
    atr_dec = Decimal(str(round(state.atr, 4)))
    pullback_limit = atr_dec * Decimal("0.8") # Dynamic Pullback Exit
    
    # 1. Partial TP at 2R Profit
    if not state.partial_tp_claimed and state.initial_sl_distance > 0:
        pnl_dist = abs(state.price - state.entry_price)
        if pnl_dist > (state.initial_sl_distance * Decimal("2.0")):
            state.logs.append("[yellow]🔮 Partial TP (2R) Triggered.")
            exit_side = "Sell" if state.side == "Buy" else "Buy"
            await forge.call("POST", "/v5/order/create", {
                "category": CATEGORY, "symbol": SYMBOL, "side": exit_side,
                "orderType": "Market", "qty": str(state.qty * Decimal("0.5")), "reduceOnly": True
            }, signed=True)
            state.partial_tp_claimed = True

    # 2. Volatility Pullback Exit
    if state.side == "Buy":
        state.high_water_mark = max(state.high_water_mark, state.price)
        if (state.high_water_mark - state.price) > pullback_limit:
            state.logs.append("[orange1]DISSOLVE: ATR Pullback (Long)")
            await forge.call("POST", "/v5/order/create", {"category": CATEGORY, "symbol": SYMBOL, "side": "Sell", "orderType": "Market", "qty": str(state.qty), "reduceOnly": True}, signed=True)
    else:
        state.high_water_mark = min(state.high_water_mark, state.price)
        if (state.price - state.high_water_mark) > pullback_limit:
            state.logs.append("[orange1]DISSOLVE: ATR Pullback (Short)")
            await forge.call("POST", "/v5/order/create", {"category": CATEGORY, "symbol": SYMBOL, "side": "Buy", "orderType": "Market", "qty": str(state.qty), "reduceOnly": True}, signed=True)

# --- Engines ---

async def private_manager(forge: BybitForge):
    priv_url = "wss://stream.bybit.com/v5/private" if not IS_TESTNET else "wss://stream-testnet.bybit.com/v5/private"
    async with websockets.connect(priv_url) as ws:
        # Auth Ritual
        expires = int(time.time() * 1000) + 10000
        sig = hmac.new(API_SECRET.encode(), f"GET/realtime{expires}".encode(), hashlib.sha256).hexdigest()
        await ws.send(json.dumps({"op": "auth", "args": [API_KEY, expires, sig]}))
        await ws.send(json.dumps({"op": "subscribe", "args": ["position", "wallet"]}))
        
        # Safe Balance Sync
        bal = await forge.call("GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED"}, signed=True)
        if bal and bal.get('retCode') == 0:
            try:
                state.balance = Decimal(bal['result']['list'][0]['coin'][0]['walletBalance'])
                state.initial_balance = state.balance
                state.high_water_mark_equity = state.balance
            except: pass

        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=20)
                data = json.loads(msg)
                topic = data.get("topic")
                
                if topic == "position":
                    pos_data = [p for p in data["data"] if p["symbol"] == SYMBOL]
                    if pos_data and Decimal(pos_data[0]["size"]) > 0:
                        p = pos_data[0]
                        state.trade_active, state.side = True, p["side"]
                        state.entry_price, state.qty = Decimal(p["avgPrice"]), Decimal(p["size"])
                        state.upnl = Decimal(p["unrealisedPnl"])
                    else:
                        if state.trade_active:
                            # Dynamic Cooldown adjustment
                            recent_pnl = state.balance - state.initial_balance - state.daily_pnl
                            state.cooldown_seconds = COOLDOWN_SECONDS * 2 if recent_pnl < 0 else COOLDOWN_SECONDS
                        state.trade_active = False
                        
                if topic == "wallet":
                    w = data["data"][0]["coin"][0]
                    state.balance = Decimal(w["walletBalance"])
                    state.high_water_mark_equity = max(state.high_water_mark_equity, state.balance)
                    state.daily_pnl = state.balance - state.high_water_mark_equity
            except: continue

async def logic_engine(forge: BybitForge):
    while True:
        try:
            k = await forge.call("GET", "/v5/market/kline", {"category": CATEGORY, "symbol": SYMBOL, "interval": "1", "limit": 60})
            if k and k.get('retCode') == 0:
                state.ohlc.clear()
                for candle in k['result']['list'][::-1]:
                    state.ohlc.append((float(candle[2]), float(candle[3]), float(candle[4])))
                state.price = Decimal(k['result']['list'][0][4])
                update_oracle()
                state.is_ready = True
                
                if not state.trade_active and (time.time() - state.last_ritual > state.cooldown_seconds):
                    # Fisher Reversal logic (Snippet 1)
                    if len(state.fisher_series) >= 2:
                        is_bull = state.price > Decimal(str(state.macro_trend))
                        buy_confirm = state.fisher_series[-1] > state.fisher_series[-2] and state.fisher_series[-2] < -state.dynamic_threshold
                        sell_confirm = state.fisher_series[-1] < state.fisher_series[-2] and state.fisher_series[-2] > state.dynamic_threshold
                        
                        if is_bull and buy_confirm and state.trend_strength > 0.5:
                            await execute_trade(forge, "Buy")
                        elif not is_bull and sell_confirm and state.trend_strength > 0.5:
                            await execute_trade(forge, "Sell")
                
                await manage_trade(forge)
            await asyncio.sleep(5)
        except: await asyncio.sleep(2)

# --- UI Render ---

def get_layout():
    l = Layout()
    l.split_column(Layout(name="head", size=3), Layout(name="body", ratio=1), Layout(name="foot", size=10))
    l["body"].split_row(Layout(name="oracle"), Layout(name="pos"))
    return l

def render_ui(layout):
    pnl_style = "bold green" if state.daily_pnl >= 0 else "bold red"
    layout["head"].update(Panel(Text(f"BCH SENTINEL v4.1 | ASTRAL LINK | Session PnL: {state.daily_pnl:+.2f} USDT", justify="center", style="bold cyan"), border_style="blue"))
    
    oracle = Text()
    oracle.append(f"Price:  {state.price}\n", style="white")
    oracle.append(f"Fisher: {state.fisher:+.4f}\n", style="bold yellow")
    oracle.append(f"Trend:  {'BULL' if state.price > Decimal(str(state.macro_trend)) else 'BEAR'} ({state.trend_strength:.2f})\n", style="bold magenta")
    oracle.append(f"ATR:    {state.atr:.2f}\n", style="cyan")
    layout["oracle"].update(Panel(oracle, title="INDICATORS", border_style="yellow"))
    
    pos = Table.grid(expand=True)
    pos.add_row("SIDE:", f"[bold]{state.side}[/]")
    pos.add_row("uPNL:", f"[bold {'green' if state.upnl >= 0 else 'red'}]{state.upnl:+.2f}[/]")
    pos.add_row("CD:", f"{max(0, int(state.cooldown_seconds - (time.time() - state.last_ritual)))}s")
    layout["pos"].update(Panel(pos, title="POSITION", border_style="green"))
    
    layout["foot"].update(Panel(Text("\n".join(state.logs)), title="LOGS", border_style="dim cyan"))

async def main():
    async with BybitForge() as forge:
        # Precision Ritual
        res = await forge.call("GET", "/v5/market/instruments-info", {"category": CATEGORY, "symbol": SYMBOL})
        if res and res.get('retCode') == 0:
            specs = res['result']['list'][0]
            state.price_prec = abs(Decimal(specs['priceFilter']['tickSize']).normalize().as_tuple().exponent)
            state.qty_step = Decimal(specs['lotSizeFilter']['qtyStep'])

        layout = get_layout()
        with Live(layout, refresh_per_second=4, screen=True):
            asyncio.create_task(private_manager(forge))
            asyncio.create_task(logic_engine(forge))
            while True:
                render_ui(layout)
                await asyncio.sleep(0.5)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass