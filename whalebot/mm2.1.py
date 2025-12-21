#!/usr/bin/env python3
"""
Arcane Market Maker v11.0 - THE SINGULARITY
The ultimate high-frequency evolution for Termux & Bybit Mainnet.
"""

import asyncio
import hashlib
import hmac
import json
import os
import signal
import sys
import time
import urllib.parse
from collections import deque
from dataclasses import dataclass
from decimal import ROUND_DOWN
from decimal import ROUND_UP
from decimal import Decimal

import aiohttp

# --- Pre-Flight Check & Dependencies ---
try:
    import numpy as np
    import websockets
    from colorama import Back
    from colorama import Fore
    from colorama import Style
    from colorama import init
    from dotenv import load_dotenv
except ImportError:
    print("Dependencies missing! Run: pip install aiohttp websockets numpy colorama python-dotenv")
    sys.exit(1)

load_dotenv()
init(autoreset=True)

# --- AUTH GATEKEEPER ---
API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')
IS_TESTNET = os.getenv('BYBIT_TESTNET', 'false').lower() == 'true'

if not API_KEY or not API_SECRET:
    print(Fore.RED + Style.BRIGHT + "\n# FATAL: ARCANE KEYS MISSING")
    print(Fore.YELLOW + "Create a '.env' file containing BYBIT_API_KEY and BYBIT_API_SECRET")
    sys.exit(1)

# --- Configuration & Hardware Interface ---
BASE_URL = "https://api-testnet.bybit.com" if IS_TESTNET else "https://api.bybit.com"
WS_PUBLIC = "wss://stream-testnet.bybit.com/v5/public/linear" if IS_TESTNET else "wss://stream.bybit.com/v5/public/linear"
WS_PRIVATE = "wss://stream-testnet.bybit.com/v5/private" if IS_TESTNET else "wss://stream.bybit.com/v5/private"

class ArcaneHardware:
    @staticmethod
    async def vibrate(pattern: str = "60,100,60"):
        try:
            if os.path.exists('/data/data/com.termux/files/usr/bin/termux-vibrate'):
                await asyncio.create_subprocess_exec('termux-vibrate', '-d', pattern)
        except: pass

    @staticmethod
    async def toast(msg: str):
        try:
            if os.path.exists('/data/data/com.termux/files/usr/bin/termux-toast'):
                await asyncio.create_subprocess_exec('termux-toast', '-b', 'magenta', msg)
        except: pass

@dataclass
class SymbolConfig:
    symbol: str
    tick_size: Decimal = Decimal('0')
    qty_step: Decimal = Decimal('0')
    min_qty: Decimal = Decimal('0')
    max_pos_usd: Decimal = Decimal('600')  # Maximum allowed exposure
    risk_pct: Decimal = Decimal('0.015')   # 1.5% of equity per quote
    base_spread_bps: Decimal = Decimal('5.0')
    max_drawdown_usd: Decimal = Decimal('20.0') # Emergency Stop

class OrderFlowEngine:
    def __init__(self):
        self.bids: dict[Decimal, Decimal] = {}
        self.asks: dict[Decimal, Decimal] = {}
        self.prev_imbalance = Decimal('0')
        self.ofi_signal = Decimal('0') # Order Flow Imbalance Signal

    def update(self, data: dict, is_snapshot: bool):
        if is_snapshot:
            self.bids = {Decimal(p): Decimal(q) for p, q in data.get('b', [])}
            self.asks = {Decimal(p): Decimal(q) for p, q in data.get('a', [])}
        else:
            for p, q in data.get('b', []):
                price, qty = Decimal(p), Decimal(q)
                if qty == 0: self.bids.pop(price, None)
                else: self.bids[price] = qty
            for p, q in data.get('a', []):
                price, qty = Decimal(p), Decimal(q)
                if qty == 0: self.asks.pop(price, None)
                else: self.asks[price] = qty

        # Calculate Micro-Imbalance
        b_vol = sum(list(self.bids.values())[:5])
        a_vol = sum(list(self.asks.values())[:5])
        curr_imb = b_vol - a_vol
        self.ofi_signal = curr_imb - self.prev_imbalance
        self.prev_imbalance = curr_imb

    def get_fair_price(self) -> tuple[Decimal, Decimal]:
        if not self.bids or not self.asks: return Decimal('0'), Decimal('0')
        best_bid, best_ask = max(self.bids.keys()), min(self.asks.keys())
        v_bid, v_ask = self.bids[best_bid], self.asks[best_ask]
        # Log-weighted MicroPrice for better pressure sensing
        micro = (best_bid * v_ask + best_ask * v_bid) / (v_bid + v_ask)
        return micro, (v_bid + v_ask) / 2

class ArcaneSingularity:
    def __init__(self):
        self.symbols = {"XLMUSDT": SymbolConfig("XLMUSDT")}
        self.books = {s: OrderFlowEngine() for s in self.symbols}
        self.prices_hist = {s: deque(maxlen=50) for s in self.symbols}
        self.positions = {s: {"size": Decimal('0'), "value": Decimal('0')} for s in self.symbols}
        self.funding_rates = {s: Decimal('0') for s in self.symbols}

        self.equity = Decimal('0')
        self.start_equity = Decimal('0')
        self.running = True
        self.session = None
        self.last_update = dict.fromkeys(self.symbols, 0)

    async def api_call(self, method: str, path: str, params: dict = None):
        ts = str(int(time.time() * 1000))
        query = urllib.parse.urlencode(params) if method == "GET" and params else ""
        body = json.dumps(params) if method == "POST" and params else ""
        raw = ts + str(API_KEY) + "5000" + (query if method == "GET" else body)
        sig = hmac.new(API_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()

        headers = {
            "X-BAPI-API-KEY": API_KEY, "X-BAPI-SIGN": sig,
            "X-BAPI-TIMESTAMP": ts, "X-BAPI-RECV-WINDOW": "5000",
            "Content-Type": "application/json"
        }
        try:
            async with self.session.request(method, f"{BASE_URL}{path}{'?' + query if query else ''}", headers=headers, data=body) as r:
                return await r.json()
        except: return None

    async def initialize(self):
        # Fetch initial context
        info = await self.api_call("GET", "/v5/market/instruments-info", {"category": "linear"})
        if info:
            for i in info['result']['list']:
                if i['symbol'] in self.symbols:
                    s = i['symbol']
                    self.symbols[s].tick_size = Decimal(i['priceFilter']['tickSize'])
                    self.symbols[s].qty_step = Decimal(i['lotSizeFilter']['qtyStep'])
                    self.symbols[s].min_qty = Decimal(i['lotSizeFilter']['minOrderQty'])

        res = await self.api_call("GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED"})
        if res:
            coin = next((c for c in res['result']['list'][0]['coin'] if c['coin'] == 'USDT'), None)
            if coin:
                self.equity = Decimal(coin.get('equity', '0'))
                self.start_equity = self.equity

    async def private_stream(self):
        """High-speed position & balance tracking"""
        while self.running:
            try:
                expires = int((time.time() + 60) * 1000)
                raw = f"GET/realtime{expires}"
                sig = hmac.new(API_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
                url = f"{WS_PRIVATE}?api_key={API_KEY}&expire={expires}&signature={sig}"

                async with websockets.connect(url) as ws:
                    await ws.send(json.dumps({"op": "subscribe", "args": ["position", "wallet"]}))
                    async for msg in ws:
                        d = json.loads(msg)
                        if d.get('topic') == 'position':
                            for p in d['data']:
                                sym = p['symbol']
                                if sym in self.symbols:
                                    self.positions[sym]['size'] = Decimal(p['size'])
                                    self.positions[sym]['value'] = Decimal(p['positionValue'])
                        if d.get('topic') == 'wallet':
                            coin = next((c for c in d['data'][0]['coin'] if c['coin'] == 'USDT'), None)
                            if coin: self.equity = Decimal(coin['equity'])
            except: await asyncio.sleep(5)

    async def execute_singularity(self, symbol: str):
        now = time.time()
        cfg = self.symbols[symbol]
        if now - self.last_update[symbol] < 0.7: return # Throttle

        book = self.books[symbol]
        fair_px, density = book.get_fair_price()
        if fair_px == 0: return

        # 1. DRAWDOWN PROTECTOR
        current_pnl = self.equity - self.start_equity
        if current_pnl < -cfg.max_drawdown_usd:
            print(Fore.RED + "\n!!! RISK BREACH: KILL-SWITCH ACTIVATED !!!")
            self.running = False
            await self.api_call("POST", "/v5/order/cancel-all", {"category": "linear", "symbol": symbol})
            return

        # 2. SKEW CALCULATION
        inv_skew = -(self.positions[symbol]['value'] / cfg.max_pos_usd ** 2)
        ofi_skew = Decimal(str(np.tanh(float(book.ofi_signal / 500))))
        funding_skew = -(self.funding_rates[symbol] * Decimal('15'))

        total_skew = (inv_skew * Decimal('0.5')) + (ofi_skew * Decimal('0.3')) + (funding_skew * Decimal('0.2'))

        # 3. VOLATILITY SCALING
        self.prices_hist[symbol].append(float(fair_px))
        vol = Decimal('1.0')
        if len(self.prices_hist[symbol]) > 10:
            vol = Decimal(str(1 + np.std(list(self.prices_hist[symbol])) * 8))

        # 4. PLACEMENT
        spread = (fair_px * cfg.base_spread_bps / 10000) * vol
        bid_px = (fair_px - (spread * (1 - total_skew))).quantize(cfg.tick_size, ROUND_DOWN)
        ask_px = (fair_px + (spread * (1 + total_skew))).quantize(cfg.tick_size, ROUND_UP)

        qty = (self.equity * cfg.risk_pct / fair_px).quantize(cfg.qty_step, ROUND_DOWN)
        qty = max(qty, cfg.min_qty)

        # 5. API DISPATCH
        asyncio.create_task(self.api_call("POST", "/v5/order/cancel-all", {"category": "linear", "symbol": symbol}))
        batch = [
            {"symbol": symbol, "side": "Buy", "orderType": "Limit", "qty": str(qty), "price": str(bid_px), "timeInForce": "PostOnly"},
            {"symbol": symbol, "side": "Sell", "orderType": "Limit", "qty": str(qty), "price": str(ask_px), "timeInForce": "PostOnly"}
        ]
        await self.api_call("POST", "/v5/order/create-batch", {"category": "linear", "request": batch})

        self.last_update[symbol] = now
        self.render(symbol, fair_px, current_pnl, vol)

    def render(self, symbol, fair, pnl, vol):
        col = Fore.GREEN if pnl >= 0 else Fore.RED
        print(f"\033[K{Fore.MAGENTA}SENTINEL {symbol} | {Fore.WHITE}{fair:.4f} | {Fore.CYAN}Vol:{vol:.1f}x | {col}PnL:{pnl:+.2f}", end="\r")

    async def main(self):
        print(Fore.MAGENTA + Style.BRIGHT + ">>> ARCANE SENTINEL v11.0: THE SINGULARITY")
        async with aiohttp.ClientSession() as session:
            self.session = session
            await self.initialize()
            await ArcaneHardware.vibrate("100,200,100")

            # Start background tasks
            asyncio.create_task(self.private_stream())

            while self.running:
                try:
                    async with websockets.connect(WS_PUBLIC) as ws:
                        subs = [f"orderbook.50.{s}" for s in self.symbols]
                        subs += [f"tickers.{s}" for s in self.symbols]
                        await ws.send(json.dumps({"op": "subscribe", "args": subs}))

                        async for msg in ws:
                            d = json.loads(msg)
                            topic = d.get('topic', '')
                            if 'orderbook' in topic:
                                sym = topic.split('.')[-1]
                                self.books[sym].update(d['data'], d['type'] == 'snapshot')
                                await self.execute_singularity(sym)
                            elif 'tickers' in topic:
                                sym = topic.split('.')[-1]
                                self.funding_rates[sym] = Decimal(d['data'].get('fundingRate', '0'))
                except: await asyncio.sleep(2)

if __name__ == "__main__":
    bot = ArcaneSingularity()
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    asyncio.run(bot.main())
