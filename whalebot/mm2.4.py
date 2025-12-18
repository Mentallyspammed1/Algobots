#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Arcane Market Maker v16.2 - THE ETHEREAL RESILIENCE
Finalized Termux Optimization | Adaptive Requote Gating | Latency Protection
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

# --- Arcane Dependency Check ---
try:
    from colorama import init, Fore, Back, Style
    from dotenv import load_dotenv
    import numpy as np
    import websockets
except ImportError:
    print(Fore.RED + "# FAULT: Missing scrolls. Run: pip install aiohttp websockets numpy colorama python-dotenv")
    sys.exit(1)

load_dotenv()
init(autoreset=True)

# --- Sacred Keys Gatekeeper ---
API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')
IS_TESTNET = os.getenv('BYBIT_TESTNET', 'false').lower() == 'true'

if not API_KEY or not API_SECRET:
    print(Fore.RED + Style.BRIGHT + "\n# FATAL: Sacred keys missing. The ritual cannot commence.")
    sys.exit(1)

BASE_URL = "https://api-testnet.bybit.com" if IS_TESTNET else "https://api.bybit.com"
WS_PUBLIC = "wss://stream-testnet.bybit.com/v5/public/linear" if IS_TESTNET else "wss://stream.bybit.com/v5/public/linear"
WS_PRIVATE = "wss://stream-testnet.bybit.com/v5/private" if IS_TESTNET else "wss://stream.bybit.com/v5/private"

# --- HUD & Haptics ---

class RevenantUI:
    @staticmethod
    def render_hud(sym, px, pnl, vol, skew, tokens, inv_ratio, latency, heartbeat):
        pnl_col = Fore.GREEN if pnl >= 0 else Fore.RED
        inv_bar_size = 15
        filled_size = int(abs(inv_ratio) * inv_bar_size)
        bar = ("█" * filled_size).ljust(inv_bar_size, "-")
        bar_col = Fore.RED if abs(inv_ratio) > 0.8 else Fore.CYAN
        hb_char = "⚡" if heartbeat % 2 == 0 else " "
        
        sys.stdout.write("\033[H") 
        print(f"{Fore.MAGENTA}╔════════ {Fore.WHITE}ETHEREAL RESILIENCE v16.2 {Fore.MAGENTA}════════════════════════╗")
        print(f"{Fore.MAGENTA}║ {Fore.CYAN}SYMBOL: {sym:<10} {Fore.MAGENTA}| {Fore.WHITE}PRICE: {px:<10.5f} {Fore.MAGENTA}| {pnl_col}PNL: {pnl:+.2f} {Fore.MAGENTA}║")
        print(f"{Fore.MAGENTA}║ {Fore.WHITE}VOLAT: {vol:.2f}x {Fore.MAGENTA}| {Fore.YELLOW}SKEW: {skew:+.2f} {Fore.MAGENTA}| {Fore.BLUE}LATENCY: {latency:>3}ms {Fore.MAGENTA}| {Fore.WHITE}TOK: {int(tokens)} {Fore.MAGENTA}║")
        print(f"{Fore.MAGENTA}║ {Fore.WHITE}INVENTORY: {bar_col}[{bar}] {inv_ratio:+.2f} {Fore.MAGENTA}| {Fore.GREEN}PULSE: {hb_char} {Fore.MAGENTA}║")
        print(f"{Fore.MAGENTA}╚══════════════════════════════════════════════════════════════╝")

class ArcaneHardware:
    @staticmethod
    async def vibrate(pattern="60"):
        try:
            p = await asyncio.create_subprocess_exec('termux-vibrate', '-d', pattern, stdout=-3, stderr=-3)
            await p.wait()
        except: pass

# --- Core Grimoires ---

class TokenBucket:
    def __init__(self, capacity: int, fill_rate: float):
        self.capacity, self.tokens = capacity, float(capacity)
        self.fill_rate, self.last = fill_rate, time.time()

    async def consume(self):
        while self.tokens < 1:
            now = time.time()
            self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.fill_rate)
            self.last = now
            if self.tokens < 1: await asyncio.sleep(0.05)
        self.tokens -= 1

class RevenantBook:
    def __init__(self):
        self.bids, self.asks = {}, {}
        self.ofi_history = deque(maxlen=20)
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
        
        b_vol = sum(list(self.bids.values())[:10])
        a_vol = sum(list(self.asks.values())[:10])
        curr_imb = b_vol - a_vol
        self.ofi_history.append(curr_imb - self.prev_imb)
        self.prev_imb = curr_imb

    def get_market_state(self) -> Tuple[Decimal, Decimal, Decimal]:
        if not self.bids or not self.asks: return Decimal('0'), Decimal('0'), Decimal('0')
        bb, ba = max(self.bids.keys()), min(self.asks.keys())
        vb, va = self.bids[bb], self.asks[ba]
        micro = (bb * va + ba * vb) / (va + vb)
        # Weighted OFI Decay (Exponential focus on recent)
        weights = np.linspace(0.1, 1.0, len(self.ofi_history))
        ofi_avg = np.average(self.ofi_history, weights=weights) if self.ofi_history else 0
        return micro, Decimal(str(ofi_avg)), (ba - bb) / bb * 10000

@dataclass
class SymbolConfig:
    symbol: str
    tick_size: Decimal = Decimal('0')
    qty_step: Decimal = Decimal('0')
    min_qty: Decimal = Decimal('0')
    max_pos_usd: Decimal = Decimal('800')
    risk_pct: Decimal = Decimal('0.012')
    base_spread_bps: Decimal = Decimal('6.0')
    latency_threshold: int = 250 # ms

# --- Main Engine ---

class OmniRevenant:
    def __init__(self):
        self.symbols = {"XLMUSDT": SymbolConfig("XLMUSDT")}
        self.books = {s: RevenantBook() for s in self.symbols}
        self.positions = {s: {"size": Decimal('0'), "val": Decimal('0')} for s in self.symbols}
        self.active_orders = {s: {"Buy": None, "Sell": None} for s in self.symbols}
        self.prices_hist = {s: deque(maxlen=40) for s in self.symbols}
        
        self.equity, self.initial_equity = Decimal('0'), Decimal('0')
        self.running = True
        self.session = None
        self.bucket = TokenBucket(15, 7)
        self.last_update = {s: 0 for s in self.symbols}
        self.latency = 0
        self.pulse_count = 0

    async def summon_request(self, method, path, params=None):
        await self.bucket.consume()
        start = time.perf_counter()
        ts = str(int(time.time() * 1000))
        query = urllib.parse.urlencode(params) if method == "GET" and params else ""
        body = json.dumps(params) if method == "POST" and params else ""
        raw = ts + API_KEY + "5000" + (query if method == "GET" else body)
        sig = hmac.new(API_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
        
        headers = {"X-BAPI-API-KEY": API_KEY, "X-BAPI-SIGN": signature, "X-BAPI-TIMESTAMP": ts, "X-BAPI-RECV-WINDOW": "5000", "Content-Type": "application/json"}
        # Correction: sig used instead of placeholder signature
        headers["X-BAPI-SIGN"] = sig
        
        try:
            url = f"{BASE_URL}{path}{'?' + query if query else ''}"
            async with self.session.request(method, url, headers=headers, data=body) as r:
                res = await r.json()
                self.latency = int((time.perf_counter() - start) * 1000)
                return res
        except: return None

    async def private_resonance(self):
        while self.running:
            try:
                expires = int((time.time() + 30) * 1000)
                sig = hmac.new(API_SECRET.encode(), f"GET/realtime{expires}".encode(), hashlib.sha256).hexdigest()
                async with websockets.connect(f"{WS_PRIVATE}?api_key={API_KEY}&expire={expires}&signature={sig}") as ws:
                    await ws.send(json.dumps({"op": "subscribe", "args": ["position", "wallet", "execution"]}))
                    async for msg in ws:
                        d = json.loads(msg)
                        if d.get('topic') == 'execution': await ArcaneHardware.vibrate("40")
                        if d.get('topic') == 'position':
                            for p in d['data']:
                                if p['symbol'] in self.symbols:
                                    self.positions[p['symbol']] = {"size": Decimal(p['size']), "val": Decimal(p['positionValue'])}
                        if d.get('topic') == 'wallet':
                            c = next((x for x in d['data'][0]['coin'] if x['coin'] == 'USDT'), None)
                            if c: self.equity = Decimal(c['equity'])
            except: await asyncio.sleep(5)

    async def orchestrate(self, symbol):
        now = time.time()
        cfg = self.symbols[symbol]
        if now - self.last_update[symbol] < 0.8: return 
        
        book = self.books[symbol]
        micro, ofi, spread_bps = book.get_market_state()
        if micro == 0 or self.equity == 0: return

        # 1. Volatility & Latency Protection
        self.prices_hist[symbol].append(float(micro))
        vol_mult = Decimal('1.0')
        if len(self.prices_hist[symbol]) > 10:
            vol_mult += Decimal(str(statistics.stdev(self.prices_hist[symbol]) * 18))
        
        # Expand spread if Termux network is laggy
        if self.latency > cfg.latency_threshold:
            vol_mult *= Decimal('1.5')

        # 2. Pentacle Skew (Inventory + Decaying OFI)
        inv_ratio = self.positions[symbol]['val'] / cfg.max_pos_usd
        inv_skew = -(inv_ratio ** 3)
        ofi_skew = Decimal(str(np.tanh(float(ofi / 600))))
        total_skew = (inv_skew * Decimal('0.6')) + (ofi_skew * Decimal('0.4'))
        total_skew = max(min(total_skew, Decimal('1')), Decimal('-1'))

        # 3. Dynamic Calculation
        spread = (micro * cfg.base_spread_bps / 10000) * vol_mult
        bid_px = (micro - (spread * (1 - total_skew))).quantize(cfg.tick_size, ROUND_DOWN)
        ask_px = (micro + (spread * (1 + total_skew))).quantize(cfg.tick_size, ROUND_UP)
        
        qty = (self.equity * cfg.risk_pct / micro).quantize(cfg.qty_step, ROUND_DOWN)
        if qty < cfg.min_qty: qty = cfg.min_qty

        # 4. Adaptive Requote Gate
        needs_update = True
        requote_threshold = int(2 * float(vol_mult)) # Move less often in high vol
        
        curr_bid = self.active_orders[symbol]["Buy"]
        curr_ask = self.active_orders[symbol]["Sell"]
        if curr_bid and curr_ask:
            if abs(bid_px - curr_bid) < (cfg.tick_size * requote_threshold) and \
               abs(ask_px - curr_ask) < (cfg.tick_size * requote_threshold):
                needs_update = False

        if needs_update:
            asyncio.create_task(self.summon_request("POST", "/v5/order/cancel-all", {"category": "linear", "symbol": symbol}))
            orders = []
            if inv_ratio < 0.9:
                orders.append({"symbol": symbol, "side": "Buy", "orderType": "Limit", "qty": str(qty), "price": str(bid_px), "timeInForce": "PostOnly"})
            if inv_ratio > -0.9:
                orders.append({"symbol": symbol, "side": "Sell", "orderType": "Limit", "qty": str(qty), "price": str(ask_px), "timeInForce": "PostOnly"})
            
            if orders:
                asyncio.create_task(self.summon_request("POST", "/v5/order/create-batch", {"category": "linear", "request": orders}))
            
            self.active_orders[symbol]["Buy"] = bid_px
            self.active_orders[symbol]["Sell"] = ask_px

        self.last_update[symbol] = now
        self.pulse_count += 1
        RevenantUI.render_hud(symbol, micro, self.equity - self.initial_equity, vol_mult, total_skew, self.bucket.tokens, inv_ratio, self.latency, self.pulse_count)

    async def run(self):
        print("\033[2J\033[H" + Fore.CYAN + ">>> AWAKENING THE ETHEREAL RESILIENCE v16.2")
        async with aiohttp.ClientSession() as session:
            self.session = session
            # Init Precisions
            inf = await self.summon_request("GET", "/v5/market/instruments-info", {"category": "linear"})
            if inf:
                for i in inf['result']['list']:
                    if i['symbol'] in self.symbols:
                        s = i['symbol']
                        self.symbols[s].tick_size = Decimal(i['priceFilter']['tickSize'])
                        self.symbols[s].qty_step = Decimal(i['lotSizeFilter']['qtyStep'])
                        self.symbols[s].min_qty = Decimal(i['lotSizeFilter']['minOrderQty'])
            
            w = await self.summon_request("GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED"})
            if w:
                c = next((x for x in w['result']['list'][0]['coin'] if x['coin'] == 'USDT'), None)
                if c: self.equity = self.initial_equity = Decimal(c.get('equity', '0'))

            asyncio.create_task(self.private_resonance())
            await ArcaneHardware.vibrate("80,150,80")

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