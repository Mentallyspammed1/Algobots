#!/usr/bin/env python3
"""
Arcane Market Maker v17.0 - THE RESOLUTE ORACLE
Forged with ATR-Risk Parity, Fisher Reversal, and Partial Profit Siphoning.
"""

import asyncio
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse
from collections import deque
from decimal import Decimal

import aiohttp
import numpy as np
import websockets
from colorama import Fore
from colorama import init

# --- Arcane Initialization ---
init(autoreset=True)
load_dotenv = lambda: None # Placeholder for environment loading

# --- Sacred Configuration ---
SYMBOL = "XLMUSDT"
CATEGORY = "linear"
LEVERAGE = 10
BASE_RISK_PERCENT = 1.5   # Risk 1.5% of equity per SL
DAILY_LOSS_LIMIT = 5.0    # 5% Daily Stop
COOLDOWN_SECONDS = 300    # Base Cooldown
IS_TESTNET = False

# Summoning Keys from the .env
API_KEY = os.getenv('BYBIT_API_KEY', 'YOUR_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET', 'YOUR_SECRET')
BASE_URL = "https://api.bybit.com" if not IS_TESTNET else "https://api-testnet.bybit.com"

# --- HUD & Hardware Haptics ---
class OracleUI:
    @staticmethod
    def log(msg, color=Fore.CYAN):
        timestamp = time.strftime("%H:%M:%S")
        print(f"{Fore.MAGENTA}[{timestamp}] {color}{msg}")

    @staticmethod
    async def termux_ritual(msg, pattern="60"):
        try:
            # Vibrate and Toast for Android awareness
            await asyncio.create_subprocess_exec('termux-vibrate', '-d', pattern, stdout=-3, stderr=-3)
            await asyncio.create_subprocess_exec('termux-toast', '-b', 'black', '-c', 'cyan', msg, stdout=-3, stderr=-3)
        except: pass

# --- The Sentinel State ---
class SentinelState:
    def __init__(self):
        self.balance = Decimal("0")
        self.initial_balance = Decimal("0")
        self.high_water_mark_equity = Decimal("0.0")
        self.daily_pnl = Decimal("0")
        self.trade_active = False
        self.side = "HOLD"
        self.qty = Decimal("0")
        self.entry_price = Decimal("0")
        self.price = Decimal("0")
        self.price_prec = 4
        self.qty_step = Decimal("0.1")

        # Oracle Indicators
        self.ohlc = deque(maxlen=100)
        self.fisher_series = deque(maxlen=5)
        self.fisher = 0.0
        self.trigger = 0.0
        self.atr = 0.0
        self.macro_trend = 0.0
        self.trend_strength = 0.0
        self.velocity = 0.0
        self.dynamic_threshold = 1.5

        # Ritual Management
        self.last_ritual = 0
        self.cooldown_seconds = COOLDOWN_SECONDS
        self.high_water_mark = Decimal("0")
        self.initial_sl_distance = Decimal("0")
        self.is_ready = False
        self.logs = deque(maxlen=5)

# Initialize the State
state = SentinelState()

# --- Mathematical Grimoire (Indicators) ---
def update_oracle_indicators():
    """Channeling market data into indicators."""
    if len(state.ohlc) < 30: return

    closes = np.array([x[2] for x in state.ohlc])
    highs = np.array([x[0] for x in state.ohlc])
    lows = np.array([x[1] for x in state.ohlc])

    # 1. ATR (Volatility)
    tr = np.maximum(highs[1:] - lows[1:], np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1]))
    state.atr = np.mean(tr[-14:])

    # 2. Fisher Transform (Momentum Reversal)
    # Simplified high/low mapping to -0.99, 0.99
    hh = highs[-10:].max()
    ll = lows[-10:].min()
    val = 0.66 * ((closes[-1] - ll) / (hh - ll + 0.00001) - 0.5) + 0.67 * 0.0 # simplified
    val = np.clip(val, -0.999, 0.999)
    fish = 0.5 * np.log((1 + val) / (1 - val))
    state.fisher_series.append(fish)
    state.fisher = fish

    # 3. Trend Oracle
    state.macro_trend = np.mean(closes[-30:])
    state.trend_strength = abs(closes[-1] - state.macro_trend) / state.atr if state.atr > 0 else 0
    state.velocity = (closes[-1] - closes[-5]) / state.atr if state.atr > 0 else 0

# --- The Ritual of Execution ---
class Forge:
    def __init__(self, session):
        self.session = session

    async def call(self, method, path, params=None, signed=False):
        ts = str(int(time.time() * 1000))
        recv_window = "5000"
        query = urllib.parse.urlencode(params) if method == "GET" and params else ""
        body = json.dumps(params) if method == "POST" and params else ""

        sign_payload = ts + API_KEY + recv_window + (query if method == "GET" else body)
        signature = hmac.new(API_SECRET.encode(), sign_payload.encode(), hashlib.sha256).hexdigest()

        headers = {
            "X-BAPI-API-KEY": API_KEY, "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": ts, "X-BAPI-RECV-WINDOW": recv_window,
            "Content-Type": "application/json"
        }

        url = f"{BASE_URL}{path}{'?' + query if query else ''}"
        async with self.session.request(method, url, headers=headers, data=body) as r:
            return await r.json()

async def execute_trade(forge, side: str):
    """Snippet 2: ATR-Based Risk Sizing."""
    if state.daily_pnl <= -(state.initial_balance * DAILY_LOSS_LIMIT / 100):
        OracleUI.log("Daily Loss Limit Breached. Aegis active.", Fore.RED)
        return

    atr_dec = Decimal(str(round(state.atr, 4)))
    velocity_adj = Decimal(str(np.clip(1.0 - (abs(state.velocity) * 0.1), 0.7, 1.2)))
    sl_mult = Decimal("2.0") # 2 ATR Stop Loss

    # Calculate Stop Loss
    if side == "Buy":
        sl = state.price - (atr_dec * sl_mult)
        sl_dist = state.price - sl
    else:
        sl = state.price + (atr_dec * sl_mult)
        sl_dist = sl - state.price

    if sl_dist <= 0: return

    # Sizing Logic
    conviction = Decimal(str(np.clip(abs(state.velocity), 0.8, 1.5)))
    total_risk = state.balance * (Decimal(str(BASE_RISK_PERCENT)) / 100) * conviction
    raw_qty = total_risk / sl_dist
    qty = (raw_qty // state.qty_step) * state.qty_step

    if qty <= 0: return

    # Take Profit (Snippet 2)
    tp_mult = Decimal("3.5") * velocity_adj
    tp = (state.price + atr_dec * tp_mult) if side == "Buy" else (state.price - atr_dec * tp_mult)

    order = {
        "category": CATEGORY, "symbol": SYMBOL, "side": side, "orderType": "Market", "qty": str(qty),
        "takeProfit": f"{tp:.{state.price_prec}f}", "stopLoss": f"{sl:.{state.price_prec}f}",
        "tpTriggerBy": "LastPrice", "slTriggerBy": "LastPrice"
    }

    res = await forge.call("POST", "/v5/order/create", order, signed=True)
    if res.get('retCode') == 0:
        state.last_ritual = time.time()
        state.high_water_mark = state.price
        state.initial_sl_distance = sl_dist
        await OracleUI.termux_ritual(f"{side} {SYMBOL} ENTERED", "100,50,100")
        OracleUI.log(f"⚔️ {side} Kinetic Entry | Risk: {total_risk:.2f} USDT", Fore.GREEN)

# --- Management Engines ---
async def manage_active_trade(forge):
    """Snippet 3 & 4: Partial TP and ATR-Pullback."""
    if not state.trade_active: return

    atr_dec = Decimal(str(round(state.atr, 4)))
    pullback_amount = atr_dec * Decimal("1.2")

    # --- Partial Profit Siphoning (Snippet 3) ---
    if state.initial_sl_distance > 0:
        reached_2r = False
        if (state.side == "Buy" and (state.price - state.entry_price) > (state.initial_sl_distance * Decimal("2.0"))) or (state.side == "Sell" and (state.entry_price - state.price) > (state.initial_sl_distance * Decimal("2.0"))):
            reached_2r = True

        if reached_2r:
            OracleUI.log("🔮 Partial TP: 2R threshold reached. Closing 50%.", Fore.YELLOW)
            close_side = "Sell" if state.side == "Buy" else "Buy"
            await forge.call("POST", "/v5/order/create", {
                "category": CATEGORY, "symbol": SYMBOL, "side": close_side,
                "orderType": "Market", "qty": str(state.qty * Decimal("0.5")), "reduceOnly": True
            }, signed=True)
            state.initial_sl_distance = Decimal("0") # Disable partial TP for this trade

    # --- ATR Pullback Exit (Snippet 4) ---
    if state.side == "Buy":
        state.high_water_mark = max(state.high_water_mark, state.price)
        if (state.high_water_mark - state.price) > pullback_amount:
            OracleUI.log("🌪 Pullback Exit: Volatility-adjusted drop.", Fore.RED)
            await forge.call("POST", "/v5/order/create", {
                "category": CATEGORY, "symbol": SYMBOL, "side": "Sell",
                "orderType": "Market", "qty": str(state.qty), "reduceOnly": True
            }, signed=True)
    elif state.side == "Sell":
        state.high_water_mark = min(state.high_water_mark, state.price)
        if (state.price - state.high_water_mark) > pullback_amount:
            OracleUI.log("🌪 Pullback Exit: Volatility-adjusted rise.", Fore.RED)
            await forge.call("POST", "/v5/order/create", {
                "category": CATEGORY, "symbol": SYMBOL, "side": "Buy",
                "orderType": "Market", "qty": str(state.qty), "reduceOnly": True
            }, signed=True)

# --- The Engines ---
async def kline_engine(forge):
    """Snippet 1: Fisher Reversal Entry."""
    while True:
        try:
            k_res = await forge.call("GET", "/v5/market/kline", {"category": CATEGORY, "symbol": SYMBOL, "interval": "1", "limit": 60})
            if k_res.get('retCode') == 0:
                state.ohlc.clear()
                for k in k_res['result']['list'][::-1]:
                    state.ohlc.append((float(k[2]), float(k[3]), float(k[4]))) # H, L, C
                state.price = Decimal(k_res['result']['list'][0][4])
                update_oracle_indicators()

                if not state.trade_active and (time.time() - state.last_ritual > state.cooldown_seconds):
                    is_bull = state.price > state.macro_trend
                    is_strong = state.trend_strength > 0.5

                    if len(state.fisher_series) >= 2 and is_strong:
                        # Reversal Logic (Snippet 1)
                        buy_reversal = state.fisher_series[-1] > state.fisher_series[-2] and state.fisher_series[-2] < -state.dynamic_threshold
                        sell_reversal = state.fisher_series[-1] < state.fisher_series[-2] and state.fisher_series[-2] > state.dynamic_threshold

                        if is_bull and buy_reversal:
                            await execute_trade(forge, "Buy")
                        elif not is_bull and sell_reversal:
                            await execute_trade(forge, "Sell")

                await manage_active_trade(forge)
            await asyncio.sleep(5)
        except Exception as e:
            OracleUI.log(f"Oracle Error: {e}", Fore.RED)
            await asyncio.sleep(5)

async def private_manager(forge):
    """Snippet 5: Dynamic Cooldown & High-Water Mark Equity."""
    priv_url = "wss://stream.bybit.com/v5/private"
    async with websockets.connect(priv_url) as ws:
        # Authentication Ritual
        expires = str(int(time.time() * 1000) + 10000)
        signature = hmac.new(API_SECRET.encode(), f"GET/realtime{expires}".encode(), hashlib.sha256).hexdigest()
        await ws.send(json.dumps({"op": "auth", "args": [API_KEY, expires, signature]}))
        await ws.send(json.dumps({"op": "subscribe", "args": ["position", "wallet"]}))

        # Initial Balance Sync
        bal = await forge.call("GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED"}, signed=True)
        if bal.get('retCode') == 0:
            state.balance = Decimal(bal['result']['list'][0]['coin'][0]['walletBalance'])
            state.initial_balance = state.balance
            state.high_water_mark_equity = state.balance

        while True:
            data = json.loads(await ws.recv())
            topic = data.get("topic")

            if topic == "position" and "data" in data:
                pos = [p for p in data["data"] if p["symbol"] == SYMBOL]
                if pos and Decimal(pos[0]["size"]) > 0:
                    p = pos[0]
                    state.trade_active, state.side = True, p["side"]
                    state.entry_price, state.qty = Decimal(p["avgPrice"]), Decimal(p["size"])
                else:
                    # Snippet 5: Dynamic Cooldown Adjustment
                    if state.trade_active:
                        pnl_result = state.balance - state.initial_balance - state.daily_pnl
                        if pnl_result < 0:
                            state.cooldown_seconds = COOLDOWN_SECONDS * 2
                            OracleUI.log(f"Trade Loss. Cooldown increased to {state.cooldown_seconds}s", Fore.RED)
                        else:
                            state.cooldown_seconds = COOLDOWN_SECONDS
                    state.trade_active = False

            if topic == "wallet" and "data" in data:
                new_bal = Decimal(data["data"][0]["coin"][0]["walletBalance"])
                state.high_water_mark_equity = max(state.high_water_mark_equity, new_bal)
                state.balance = new_bal
                # PNL calculated from the high point of the day
                state.daily_pnl = state.balance - state.high_water_mark_equity

# --- Summoning the Loop ---
async def main():
    async with aiohttp.ClientSession() as session:
        forge = Forge(session)
        OracleUI.log("Summoning the Resolute Oracle v17.0...", Fore.CYAN)
        await asyncio.gather(kline_engine(forge), private_manager(forge))

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
