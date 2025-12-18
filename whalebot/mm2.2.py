#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Arcane Market Maker v15.0 - THE AEGIS OF PROVIDENCE
The Definitive High-Frequency Grimoire for Termux.
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
    print("Arcane scripts require: pip install aiohttp websockets numpy colorama python-dotenv")
    sys.exit(1)

load_dotenv()
init(autoreset=True)

# --- Sacred Keys Gatekeeper ---
API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')
IS_TESTNET = os.getenv('BYBIT_TESTNET', 'false').lower() == 'true'

if not API_KEY or not API_SECRET:
    print(Fore.RED + Style.BRIGHT + "\n# FATAL: Sacred .env keys are missing. The Aegis remains unpowered.")
    sys.exit(1)

# --- Endpoints ---
BASE_URL = "https://api-testnet.bybit.com" if IS_TESTNET else "https://api.bybit.com"
WS_PUBLIC = "wss://stream-testnet.bybit.com/v5/public/linear" if IS_TESTNET else "wss://stream.bybit.com/v5/public/linear"
WS_PRIVATE = "wss://stream-testnet.bybit.com/v5/private" if IS_TESTNET else "wss://stream.bybit.com/v5/private"

class ArcaneUI:
    """The Neon Dashboard HUD"""
    @staticmethod
    def clear_line(): sys.stdout.write("\033[K")
    
    @staticmethod
    def move_up(n): sys.stdout.write(f"\033[{n}A")

    @classmethod
    def render_hud(cls, sym, px, pnl, vol, skew, bucket, density):
        pnl_col = Fore.GREEN if pnl >= 0 else Fore.RED
        tox_col = Fore.CYAN if vol < 1.4 else Fore.RED
        skew_col = Fore.YELLOW if abs(skew) < 0.5 else Fore.MAGENTA
        
        # We use a 3-line static dashboard
        sys.stdout.write("\r")
        cls.clear_line()
        print(f"{Fore.MAGENTA}╔═ {Fore.WHITE}AEGIS v15.0 {Fore.MAGENTA}══ {Fore.CYAN}{sym} {Fore.MAGENTA}══════════════════════════════════╗")
        cls.clear_line()
        print(f"{Fore.MAGENTA}║ {Fore.WHITE}PRICE: {px:.4f} {Fore.MAGENTA}| {pnl_col}PnL: {pnl:+.2f} USDT {Fore.MAGENTA}| {tox_col}VOL: {vol:.2f}x {Fore.MAGENTA}| {Fore.WHITE}TOK: {int(bucket)}")
        cls.clear_line()
        print(f"{Fore.MAGENTA}║ {skew_col}SKEW: {skew:+.2f} {Fore.MAGENTA}| {Fore.BLUE}DENSE: {int(density)} {Fore.MAGENTA}| {Fore.WHITE}MODE: PASSIVE-MAK-MKR {Fore.MAGENTA}║")
        cls.clear_line()
        print(f"{Fore.MAGENTA}╚══════════════════════════════════════════════════════════╝")
        cls.move_up(4)

class ArcaneHardware:
    @staticmethod
    async def invoke(cmd: List[str]):
        try:
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=-3, stderr=-3)
            await proc.wait()
        except: pass

    @classmethod
    async def vibrate_fill(cls): await cls.invoke(['termux-vibrate', '-d', '50'])
    @classmethod
    async def vibrate_warn(cls): await cls.invoke(['termux-vibrate', '-d', '500'])
    @classmethod
    async def toast(cls, msg): await cls.invoke(['termux-toast', '-b', 'black', '-c', 'cyan', msg])

# --- Logic Modules ---

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

class AegisOrderbook:
    def __init__(self):
        self.bids: Dict[Decimal, Decimal] = {}
        self.asks: Dict[Decimal, Decimal] = {}
        self.prev_imb = Decimal('0')
        self.ofi = Decimal('0')

    def update(self, data: Dict, is_snapshot: bool):
        if is_snapshot:
            self.bids = {Decimal(p): Decimal(q) for p, q in data.get('b', [])}
            self.asks = {Decimal(p): Decimal(q) for p, q in data.get('a', [])}
        else:
            for side, update in [('b', self.bids), ('a', self.asks)]:
                for p, q in data.get(side, []):
                    price, qty = Decimal(p), Decimal(q)
                    if qty == 0: update.pop(price, None)
                    else: update[price] = qty
        
        b_vol = sum(list(self.bids.values())[:5])
        a_vol = sum(list(self.asks.values())[:5])
        self.ofi = (b_vol - a_vol) - self.prev_imb
        self.prev_imb = b_vol - a_vol

    def divine_fair_value(self) -> Tuple[Decimal, Decimal, Decimal]:
        if not self.bids or not self.asks: return Decimal('0'), Decimal('0'), Decimal('0')
        bb, ba = max(self.bids.keys()), min(self.asks.keys())
        vb, va = self.bids[bb], self.asks[ba]
        micro = (bb * va + ba * vb) / (va + vb)
        density = (vb + va) / 2
        spread_bps = (ba - bb) / bb * 10000
        return micro, density, spread_bps

    def wall_shield(self, side: str, price: Decimal, tick: Decimal) -> Decimal:
        data = self.bids if side == 'Buy' else self.asks
        if not data: return price
        avg_v = sum(list(data.values())[:20]) / 20
        walls = [p for p, v in data.items() if v > avg_v * Decimal('2.8')]
        if not walls: return price
        if side == 'Buy':
            valid = [w for w in walls if w <= price]
            return max(valid) + tick if valid else price
        else:
            valid = [w for w in walls if w >= price]
            return min(valid) - tick if valid else price

@dataclass
class SymbolConfig:
    symbol: str
    tick_size: Decimal = Decimal('0')
    qty_step: Decimal = Decimal('0')
    min_qty: Decimal = Decimal('0')
    max_pos_usd: Decimal = Decimal('800')
    risk_pct: Decimal = Decimal('0.012')
    base_spread_bps: Decimal = Decimal('5.5')
    kill_switch_usd: Decimal = Decimal('30.0')

# --- Main Engine ---

class AegisProvidence:
    def __init__(self):
        self.symbols = {"XLMUSDT": SymbolConfig("XLMUSDT")}
        self.books = {s: AegisOrderbook() for s in self.symbols}
        self.positions = {s: {"size": Decimal('0'), "val": Decimal('0')} for s in self.symbols}
        self.funding = {s: Decimal('0') for s in self.symbols}
        self.prices_hist = {s: deque(maxlen=40) for s in self.symbols}
        
        self.equity = Decimal('0')
        self.initial_equity = Decimal('0')
        self.running = True
        self.session = None
        self.bucket = TokenBucket(15, 8) 
        self.last_update = {s: 0 for s in self.symbols}

    async def conduct_rite(self, method, path, params=None):
        """Unified API Execution Rite"""
        await self.bucket.consume()
        ts = str(int(time.time() * 1000))
        query = urllib.parse.urlencode(params) if method == "GET" and params else ""
        body = json.dumps(params) if method == "POST" and params else ""
        raw = ts + str(API_KEY) + "5000" + (query if method == "GET" else body)
        sig = hmac.new(API_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
        
        headers = {"X-BAPI-API-KEY": API_KEY, "X-BAPI-SIGN": sig, "X-BAPI-TIMESTAMP": ts, "X-BAPI-RECV-WINDOW": "5000", "Content-Type": "application/json"}
        try:
            url = f"{BASE_URL}{path}{'?' + query if query else ''}"
            async with self.session.request(method, url, headers=headers, data=body) as r:
                return await r.json()
        except: return None

    async def private_stream(self):
        while self.running:
            try:
                expires = int((time.time() + 30) * 1000)
                sig = hmac.new(API_SECRET.encode(), f"GET/realtime{expires}".encode(), hashlib.sha256).hexdigest()
                async with websockets.connect(f"{WS_PRIVATE}?api_key={API_KEY}&expire={expires}&signature={sig}") as ws:
                    await ws.send(json.dumps({"op": "subscribe", "args": ["position", "wallet", "execution"]}))
                    async for msg in ws:
                        d = json.loads(msg)
                        if d.get('topic') == 'execution': await ArcaneHardware.vibrate_fill()
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
        micro, density, spread_bps = book.divine_fair_value()
        if micro == 0 or self.equity == 0: return

        # 1. THE KILL-SWITCH Ritual
        session_pnl = self.equity - self.initial_equity
        if session_pnl < -cfg.kill_switch_usd:
            self.running = False
            await self.conduct_rite("POST", "/v5/order/cancel-all", {"category": "linear", "symbol": symbol})
            await ArcaneHardware.vibrate_warn()
            return

        # 2. DIVINATION (Pricing & Skew)
        self.prices_hist[symbol].append(float(micro))
        vol_mult = Decimal('1.0')
        if len(self.prices_hist[symbol]) > 10:
            vol_mult += Decimal(str(np.std(list(self.prices_hist[symbol])) * 14))

        inv_skew = -(self.positions[symbol]['val'] / cfg.max_pos_usd ** 2)
        ofi_skew = Decimal(str(np.tanh(float(book.ofi / 1000))))
        total_skew = (inv_skew * Decimal('0.55')) + (ofi_skew * Decimal('0.25')) - (self.funding[symbol] * Decimal('12'))
        total_skew = max(min(total_skew, Decimal('1')), Decimal('-1'))

        spread = (micro * cfg.base_spread_bps / 10000) * vol_mult
        
        # 3. VISIONS OF ENTRY (PASSIVE ACCRETION)
        raw_bid = micro - (spread * (1 - total_skew))
        final_bid = book.wall_shield('Buy', raw_bid, cfg.tick_size).quantize(cfg.tick_size, ROUND_DOWN)
        
        # 4. VISIONS OF EXIT (STRATEGIC DISTRIBUTION)
        raw_ask = micro + (spread * (1 + total_skew))
        final_ask = book.wall_shield('Sell', raw_ask, cfg.tick_size).quantize(cfg.tick_size, ROUND_UP)
        
        # 5. EXECUTION RITE
        qty = (self.equity * cfg.risk_pct / micro).quantize(cfg.qty_step, ROUND_DOWN)
        if qty < cfg.min_qty: qty = cfg.min_qty

        asyncio.create_task(self.conduct_rite("POST", "/v5/order/cancel-all", {"category": "linear", "symbol": symbol}))
        batch = [
            {"symbol": symbol, "side": "Buy", "orderType": "Limit", "qty": str(qty), "price": str(final_bid), "timeInForce": "PostOnly"},
            {"symbol": symbol, "side": "Sell", "orderType": "Limit", "qty": str(qty), "price": str(final_ask), "timeInForce": "PostOnly"}
        ]
        asyncio.create_task(self.conduct_rite("POST", "/v5/order/create-batch", {"category": "linear", "request": batch}))
        
        self.last_update[symbol] = now
        ArcaneUI.render_hud(symbol, micro, session_pnl, vol_mult, total_skew, self.bucket.tokens, density)

    async def main(self):
        print(Fore.CYAN + Style.BRIGHT + ">>> POWERING THE AEGIS OF PROVIDENCE v15.0")
        async with aiohttp.ClientSession() as session:
            self.session = session
            # Instruments & Wallet
            inf = await self.conduct_rite("GET", "/v5/market/instruments-info", {"category": "linear"})
            if inf:
                for i in inf['result']['list']:
                    if i['symbol'] in self.symbols:
                        s = i['symbol']
                        self.symbols[s].tick_size = Decimal(i['priceFilter']['tickSize'])
                        self.symbols[s].qty_step = Decimal(i['lotSizeFilter']['qtyStep'])
                        self.symbols[s].min_qty = Decimal(i['lotSizeFilter']['minOrderQty'])
            
            w = await self.conduct_rite("GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED"})
            if w:
                c = next((x for x in w['result']['list'][0]['coin'] if x['coin'] == 'USDT'), None)
                if c: self.equity = self.initial_equity = Decimal(c.get('equity', '0'))

            asyncio.create_task(self.private_stream())
            await ArcaneHardware.toast("AEGIS PROVIDENCE ACTIVE")

            while self.running:
                try:
                    async with websockets.connect(WS_PUBLIC) as ws:
                        subs = [f"orderbook.50.{s}" for s in self.symbols] + [f"tickers.{s}" for s in self.symbols]
                        await ws.send(json.dumps({"op": "subscribe", "args": subs}))
                        async for msg in ws:
                            d = json.loads(msg)
                            topic = d.get('topic', '')
                            if 'orderbook' in topic:
                                sym = topic.split('.')[-1]
                                self.books[sym].update(d['data'], d['type'] == 'snapshot')
                                await self.orchestrate(sym)
                            elif 'tickers' in topic:
                                self.funding[topic.split('.')[-1]] = Decimal(d['data'].get('fundingRate', '0'))
                except: await asyncio.sleep(3)

if __name__ == "__main__":
    bot = AegisProvidence()
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    asyncio.run(bot.main())