#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Arcane Market Maker v16.0 - THE OMNI-REVENANT
The Final Synthesis: Order Persistence, ATR Volatility, & Vectorized OFI.
"""

import os
import sys
import asyncio
import aiohttp
import hmac
import hashlib
import json
import time
import urllib.parse
import logging
import signal
import statistics
from collections import deque
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from typing import Dict, List, Optional, Tuple

# --- Pre-Flight Check ---
try:
    from colorama import init, Fore, Back, Style
    from dotenv import load_dotenv
    import numpy as np
    import websockets
except ImportError:
    print(Fore.RED + "Required: pip install aiohttp websockets numpy colorama python-dotenv")
    sys.exit(1)

load_dotenv()
init(autoreset=True)

# --- Sacred Keys ---
API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')
IS_TESTNET = os.getenv('BYBIT_TESTNET', 'false').lower() == 'true'

if not API_KEY or not API_SECRET:
    print(Fore.RED + Style.BRIGHT + "\n# FATAL: Sacred keys missing. The Revenant remains in the void.")
    sys.exit(1)

BASE_URL = "https://api-testnet.bybit.com" if IS_TESTNET else "https://api.bybit.com"
WS_PUBLIC = "wss://stream-testnet.bybit.com/v5/public/linear" if IS_TESTNET else "wss://stream.bybit.com/v5/public/linear"
WS_PRIVATE = "wss://stream-testnet.bybit.com/v5/private" if IS_TESTNET else "wss://stream.bybit.com/v5/private"

# --- HUD & Haptics ---

class RevenantUI:
    @staticmethod
    def render_hud(sym, px, pnl, vol, skew, tokens, inv_ratio, latency):
        pnl_col = Fore.GREEN if pnl >= 0 else Fore.RED
        inv_bar_size = 20
        filled_size = int(abs(inv_ratio) * inv_bar_size)
        bar = ("█" * filled_size).ljust(inv_bar_size, "-")
        bar_col = Fore.RED if abs(inv_ratio) > 0.7 else Fore.CYAN
        
        sys.stdout.write("\033[H") # Move to top
        print(f"{Fore.MAGENTA}╔════════ {Fore.WHITE}OMNI-REVENANT v16.0 {Fore.MAGENTA}══════════════════════════════╗")
        print(f"{Fore.MAGENTA}║ {Fore.CYAN}SYM: {sym:<10} {Fore.MAGENTA}| {Fore.WHITE}PRICE: {px:<10.4f} {Fore.MAGENTA}| {pnl_col}PnL: {pnl:+.2f} {Fore.MAGENTA}║")
        print(f"{Fore.MAGENTA}║ {Fore.WHITE}VOL: {vol:.2f}x {Fore.MAGENTA}| {Fore.YELLOW}SKEW: {skew:+.2f} {Fore.MAGENTA}| {Fore.BLUE}LATENCY: {latency}ms {Fore.MAGENTA}| {Fore.WHITE}TOK: {int(tokens)} {Fore.MAGENTA}║")
        print(f"{Fore.MAGENTA}║ {Fore.WHITE}INV: {bar_col}[{bar}] {inv_ratio:+.2f} {Fore.MAGENTA}║")
        print(f"{Fore.MAGENTA}╚══════════════════════════════════════════════════════════════╝")

class ArcaneHardware:
    @staticmethod
    async def vibrate(d=60):
        try:
            p = await asyncio.create_subprocess_exec('termux-vibrate', '-d', str(d), stdout=-3, stderr=-3)
            await p.wait()
        except: pass

# --- Core Modules ---

class TokenBucket:
    def __init__(self, capacity: int, fill_rate: float):
        self.capacity, self.tokens = capacity, float(capacity)
        self.fill_rate, self.last = fill_rate, time.time()

    async def consume(self):
        while self.tokens < 1:
            now = time.time()
            self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.fill_rate)
            self.last = now
            if self.tokens < 1: await asyncio.sleep(0.02)
        self.tokens -= 1

class RevenantBook:
    def __init__(self):
        self.bids, self.asks = {}, {}
        self.ofi_history = deque(maxlen=10)
        self.prev_imb = Decimal('0')

    def update(self, data: Dict, is_snapshot: bool):
        if is_snapshot:
            self.bids = {Decimal(p): Decimal(q) for p, q in data.get('b', [])}
            self.asks = {Decimal(p): Decimal(q) for p, q in data.get('a', [])}
        else:
            for side, target in [('b', self.bids), ('a', self.asks)]:
                for p, q in data.get(side, []):
                    price, qty = Decimal(p), Decimal(q)
                    if qty == 0: target.pop(price, None)
                    else: target[price] = qty
        
        b_vol = sum(list(self.bids.values())[:5])
        a_vol = sum(list(self.asks.values())[:5])
        curr_imb = b_vol - a_vol
        self.ofi_history.append(curr_imb - self.prev_imb)
        self.prev_imb = curr_imb

    def get_fair_value(self) -> Tuple[Decimal, Decimal, Decimal]:
        if not self.bids or not self.asks: return Decimal('0'), Decimal('0'), Decimal('0')
        bb, ba = max(self.bids.keys()), min(self.asks.keys())
        vb, va = self.bids[bb], self.asks[ba]
        micro = (bb * va + ba * vb) / (va + vb)
        # Vectorized OFI: Mean of last 10 changes
        ofi_avg = sum(self.ofi_history) / len(self.ofi_history) if self.ofi_history else 0
        return micro, Decimal(str(ofi_avg)), (ba - bb) / bb * 10000

@dataclass
class SymbolConfig:
    symbol: str
    tick_size: Decimal = Decimal('0')
    qty_step: Decimal = Decimal('0')
    min_qty: Decimal = Decimal('0')
    max_pos_usd: Decimal = Decimal('1000')
    risk_pct: Decimal = Decimal('0.015')
    base_spread_bps: Decimal = Decimal('5.0')
    requote_threshold_ticks: int = 2 # Don't move unless > 2 ticks shift

class OmniRevenant:
    def __init__(self):
        self.symbols = {"XLMUSDT": SymbolConfig("XLMUSDT")}
        self.books = {s: RevenantBook() for s in self.symbols}
        self.positions = {s: {"size": Decimal('0'), "val": Decimal('0')} for s in self.symbols}
        self.active_orders = {s: {"Buy": None, "Sell": None} for s in self.symbols}
        
        self.equity, self.initial_equity = Decimal('0'), Decimal('0')
        self.running = True
        self.bucket = TokenBucket(20, 10)
        self.last_update = {s: 0 for s in self.symbols}
        self.latency = 0

    async def signed_request(self, method, path, params=None):
        await self.bucket.consume()
        start = time.perf_counter()
        ts = str(int(time.time() * 1000))
        query = urllib.parse.urlencode(params) if method == "GET" and params else ""
        body = json.dumps(params) if method == "POST" and params else ""
        raw = ts + API_KEY + "5000" + (query if method == "GET" else body)
        sig = hmac.new(API_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
        
        headers = {"X-BAPI-API-KEY": API_KEY, "X-BAPI-SIGN": sig, "X-BAPI-TIMESTAMP": ts, "X-BAPI-RECV-WINDOW": "5000", "Content-Type": "application/json"}
        try:
            async with self.session.request(method, f"{BASE_URL}{path}{'?' + query if query else ''}", headers=headers, data=body) as r:
                res = await r.json()
                self.latency = int((time.perf_counter() - start) * 1000)
                return res
        except: return None

    async def private_stream(self):
        while self.running:
            try:
                expires = int((time.time() + 30) * 1000)
                sig = hmac.new(API_SECRET.encode(), f"GET/realtime{expires}".encode(), hashlib.sha256).hexdigest()
                async with websockets.connect(f"{WS_PRIVATE}?api_key={API_KEY}&expire={expires}&signature={sig}") as ws:
                    await ws.send(json.dumps({"op": "subscribe", "args": ["position", "wallet", "execution", "order"]}))
                    async for msg in ws:
                        d = json.loads(msg)
                        topic = d.get('topic')
                        if topic == 'execution': await ArcaneHardware.vibrate(40)
                        if topic == 'position':
                            for p in d['data']:
                                if p['symbol'] in self.symbols:
                                    self.positions[p['symbol']] = {"size": Decimal(p['size']), "val": Decimal(p['positionValue'])}
                        if topic == 'wallet':
                            c = next((x for x in d['data'][0]['coin'] if x['coin'] == 'USDT'), None)
                            if c: self.equity = Decimal(c['equity'])
                        if topic == 'order':
                            for o in d['data']:
                                if o['orderStatus'] in ['Filled', 'Cancelled', 'Deactivated']:
                                    self.active_orders[o['symbol']][o['side']] = None
            except: await asyncio.sleep(5)

    async def orchestrate(self, symbol):
        now = time.time()
        cfg = self.symbols[symbol]
        if now - self.last_update[symbol] < 0.6: return
        
        book = self.books[symbol]
        micro, ofi, spread_bps = book.get_fair_value()
        if micro == 0 or self.equity == 0: return

        # 1. ATR-Style Volatility Scaling
        self.prices_hist[symbol].append(float(micro))
        vol_mult = Decimal('1.0')
        if len(self.prices_hist[symbol]) > 15:
            vol_mult += Decimal(str(statistics.stdev(self.prices_hist[symbol]) * 20))

        # 2. Pentacle Skew (Inventory + OFI)
        inv_ratio = self.positions[symbol]['val'] / cfg.max_pos_usd
        inv_skew = -(inv_ratio ** 3)
        ofi_skew = Decimal(str(np.tanh(float(ofi / 500))))
        total_skew = (inv_skew * Decimal('0.6')) + (ofi_skew * Decimal('0.4'))
        total_skew = max(min(total_skew, Decimal('1')), Decimal('-1'))

        # 3. Dynamic Spread
        spread = (micro * cfg.base_spread_bps / 10000) * vol_mult
        bid_target = (micro - (spread * (1 - total_skew))).quantize(cfg.tick_size, ROUND_DOWN)
        ask_target = (micro + (spread * (1 + total_skew))).quantize(cfg.tick_size, ROUND_UP)
        
        qty = (self.equity * cfg.risk_pct / micro).quantize(cfg.qty_step, ROUND_DOWN)
        if qty < cfg.min_qty: qty = cfg.min_qty

        # 4. Ghost-Tick Filter (Amend vs Replace)
        # Only replace if target deviates by > X ticks
        needs_buy = True
        needs_sell = True
        
        # This logic is simplified: In production, use orderId to Amend. 
        # Here we optimize by only triggering Cancel-All/Create if the move is significant.
        current_bid = self.active_orders[symbol]["Buy"]
        if current_bid and abs(bid_target - current_bid) < (cfg.tick_size * cfg.requote_threshold_ticks):
            needs_buy = False
            
        current_sell = self.active_orders[symbol]["Sell"]
        if current_sell and abs(ask_target - current_sell) < (cfg.tick_size * cfg.requote_threshold_ticks):
            needs_sell = False

        if needs_buy or needs_sell:
            asyncio.create_task(self.signed_request("POST", "/v5/order/cancel-all", {"category": "linear", "symbol": symbol}))
            batch = [
                {"symbol": symbol, "side": "Buy", "orderType": "Limit", "qty": str(qty), "price": str(bid_target), "timeInForce": "PostOnly"},
                {"symbol": symbol, "side": "Sell", "orderType": "Limit", "qty": str(qty), "price": str(ask_target), "timeInForce": "PostOnly"}
            ]
            asyncio.create_task(self.signed_request("POST", "/v5/order/create-batch", {"category": "linear", "request": batch}))
            self.active_orders[symbol]["Buy"] = bid_target
            self.active_orders[symbol]["Sell"] = ask_target

        self.last_update[symbol] = now
        RevenantUI.render_hud(symbol, micro, self.equity - self.initial_equity, vol_mult, total_skew, self.bucket.tokens, inv_ratio, self.latency)

    async def run(self):
        print("\033[2J\033[H" + Fore.CYAN + ">>> AWAKENING THE OMNI-REVENANT v16.0")
        async with aiohttp.ClientSession() as session:
            self.session = session
            # Init Data
            inf = await self.signed_request("GET", "/v5/market/instruments-info", {"category": "linear"})
            if inf:
                for i in inf['result']['list']:
                    if i['symbol'] in self.symbols:
                        s = i['symbol']
                        self.symbols[s].tick_size = Decimal(i['priceFilter']['tickSize'])
                        self.symbols[s].qty_step = Decimal(i['lotSizeFilter']['qtyStep'])
                        self.symbols[s].min_qty = Decimal(i['lotSizeFilter']['minOrderQty'])
            
            w = await self.signed_request("GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED"})
            if w:
                c = next((x for x in w['result']['list'][0]['coin'] if x['coin'] == 'USDT'), None)
                if c: self.equity = self.initial_equity = Decimal(c.get('equity', '0'))

            asyncio.create_task(self.private_stream())
            self.prices_hist = {s: deque(maxlen=20) for s in self.symbols}

            while self.running:
                try:
                    async with websockets.connect(WS_PUBLIC) as ws:
                        subs = [f"orderbook.50.{s}" for s in self.symbols]
                        await ws.send(json.dumps({"op": "subscribe", "args": subs}))
                        async for msg in ws:
                            d = json.loads(msg)
                            if 'orderbook' in d.get('topic', ''):
                                sym = d['topic'].split('.')[-1]
                                self.books[sym].update(d['data'], d['type'] == 'snapshot')
                                await self.orchestrate(sym)
                except: await asyncio.sleep(2)

if __name__ == "__main__":
    bot = OmniRevenant()
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    asyncio.run(bot.run())