#!/usr/bin/env python3
"""
Arcane Market Maker v10.3 - The Liquid-Eye
Advanced Orderbook Analysis & Strategic Entry/Exit placement.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import sys
import time
import urllib.parse
from dataclasses import dataclass
from decimal import ROUND_DOWN
from decimal import ROUND_UP
from decimal import Decimal

import aiohttp

# Dependencies
try:
    import numpy as np
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

# --- Config ---
API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')
IS_TESTNET = os.getenv('BYBIT_TESTNET', 'false').lower() == 'true'

BASE_URL = "https://api-testnet.bybit.com" if IS_TESTNET else "https://api.bybit.com"
WS_PUBLIC = "wss://stream-testnet.bybit.com/v5/public/linear" if IS_TESTNET else "wss://stream.bybit.com/v5/public/linear"

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger('LiquidEye')

@dataclass
class SymbolConfig:
    symbol: str
    tick_size: Decimal = Decimal('0')
    qty_step: Decimal = Decimal('0')
    min_qty: Decimal = Decimal('0')
    max_pos_usd: Decimal = Decimal('500')
    risk_pct: Decimal = Decimal('0.015')
    base_spread_bps: Decimal = Decimal('5')
    # Throttling & Analysis Settings
    min_update_interval: float = 0.8
    ofi_depth: int = 10  # Levels to analyze for imbalance
    toxicity_mult: Decimal = Decimal('2.0') # Spread multiplier during high toxicity

class AdvancedOrderbook:
    def __init__(self):
        self.bids: dict[Decimal, Decimal] = {}
        self.asks: dict[Decimal, Decimal] = {}
        self.prev_bid_sum = Decimal('0')
        self.prev_ask_sum = Decimal('0')
        self.ofi = Decimal('0') # Order Flow Imbalance

    def update(self, data: dict, is_snapshot: bool):
        # Update Dictionary
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

        # Calculate OFI (Order Flow Imbalance)
        curr_bid_sum = sum(list(self.bids.values())[:10])
        curr_ask_sum = sum(list(self.asks.values())[:10])

        # Delta in liquidity: (New Bids - Old Bids) - (New Asks - Old Asks)
        self.ofi = (curr_bid_sum - self.prev_bid_sum) - (curr_ask_sum - self.prev_ask_sum)
        self.prev_bid_sum = curr_bid_sum
        self.prev_ask_sum = curr_ask_sum

    def get_metrics(self) -> tuple[Decimal, Decimal, Decimal]:
        """Returns (Micro-Price, Volume-Weighted Spread, Toxicity)"""
        if not self.bids or not self.asks: return Decimal('0'), Decimal('0'), Decimal('1')

        sorted_bids = sorted(self.bids.items(), key=lambda x: x[0], reverse=True)
        sorted_asks = sorted(self.asks.items(), key=lambda x: x[0])

        best_bid, b_qty = sorted_bids[0]
        best_ask, a_qty = sorted_asks[0]

        # 1. Micro-Price (VWAP of best levels)
        micro_price = (best_bid * a_qty + best_ask * b_qty) / (b_qty + a_qty)

        # 2. Spread Stability
        spread = best_ask - best_bid

        # 3. Liquidity Density (Toxicity check)
        # Low density = high toxicity = wider spreads
        density = (b_qty + a_qty) / 2

        return micro_price, spread, density

    def find_wall(self, side: str, depth: int = 20) -> Decimal:
        """Finds the largest volume cluster to hide behind"""
        data = self.bids if side == "Buy" else self.asks
        if not data: return Decimal('0')
        # Sort and pick the level with max volume in top X
        sorted_levels = sorted(data.items(), key=lambda x: x[1], reverse=True)[:depth]
        if not sorted_levels: return Decimal('0')
        return sorted_levels[0][0]

class LiquidEyeMM:
    def __init__(self):
        self.symbols: dict[str, SymbolConfig] = {
            "XLMUSDT": SymbolConfig("XLMUSDT"),
        }
        self.books: dict[str, AdvancedOrderbook] = {s: AdvancedOrderbook() for s in self.symbols}
        self.positions: dict[str, dict] = {s: {"size": Decimal('0'), "value": Decimal('0')} for s in self.symbols}
        self.equity: Decimal = Decimal('0')
        self.running = True
        self.session: aiohttp.ClientSession | None = None

        # Throttle logic
        self.last_update = dict.fromkeys(self.symbols, 0)

    async def api_call(self, method: str, path: str, params: dict = None):
        if not self.session: return None
        ts = str(int(time.time() * 1000))
        body = json.dumps(params) if method == "POST" and params else ""
        query = urllib.parse.urlencode(params) if method == "GET" and params else ""

        sign = hmac.new(API_SECRET.encode(), (ts + API_KEY + "5000" + (query if method == "GET" else body)).encode(), hashlib.sha256).hexdigest()
        headers = {"X-BAPI-API-KEY": API_KEY, "X-BAPI-SIGN": sign, "X-BAPI-TIMESTAMP": ts, "X-BAPI-RECV-WINDOW": "5000"}

        url = f"{BASE_URL}{path}" + (f"?{query}" if query else "")
        try:
            async with self.session.request(method, url, headers=headers, data=body) as resp:
                return await resp.json()
        except: return None

    async def update_context(self):
        # Update Wallet
        res = await self.api_call("GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED"})
        if res and 'result' in res:
            for coin in res['result']['list'][0]['coin']:
                if coin['coin'] == 'USDT': self.equity = Decimal(coin.get('equity', '0'))

    def calculate_strategic_skew(self, symbol: str) -> Decimal:
        cfg = self.symbols[symbol]
        book = self.books[symbol]
        pos = self.positions[symbol]

        # 1. Inventory Skew (Same as v10.2)
        inv_ratio = pos['value'] / cfg.max_pos_usd
        inv_skew = -(inv_ratio ** 3)

        # 2. OFI Skew (Order Flow)
        # Normalize OFI: If OFI is positive, buyers are aggressive
        ofi_skew = Decimal(str(np.tanh(float(book.ofi / 1000)))) # Squash to -1 to 1

        total_skew = (inv_skew * Decimal('0.6')) + (ofi_skew * Decimal('0.4'))
        return max(min(total_skew, Decimal('1')), Decimal('-1'))

    async def execute_strategy(self, symbol: str):
        now = time.time()
        cfg = self.symbols[symbol]
        if now - self.last_update[symbol] < cfg.min_update_interval: return

        book = self.books[symbol]
        micro_price, spread, density = book.get_metrics()
        if micro_price == 0: return

        # Advanced Toxicity Check:
        # If density is 50% lower than average (simple check), widen spread
        toxicity_mult = Decimal('1.0')
        if density < 100: # Threshold for "Thin Book"
            toxicity_mult = cfg.toxicity_mult

        skew = self.calculate_strategic_skew(symbol)
        base_spread = (micro_price * cfg.base_spread_bps / 10000) * toxicity_mult

        # Target Prices
        target_bid = micro_price - (base_spread * (1 - skew))
        target_ask = micro_price + (base_spread * (1 + skew))

        # --- Entry/Exit Strategic Logic ---
        # Instead of just quoting target_bid, we check if there's a "Wall"
        # within 2 ticks of our target. If so, hide behind it.
        wall_buy = book.find_wall("Buy")
        wall_sell = book.find_wall("Sell")

        # Optimal Placement: Hide 1 tick in front of the wall for protection
        if wall_buy > 0 and abs(target_bid - wall_buy) / wall_buy < 0.001:
            target_bid = wall_buy + cfg.tick_size

        if wall_sell > 0 and abs(target_ask - wall_sell) / wall_sell < 0.001:
            target_ask = wall_sell - cfg.tick_size

        # Formatting & Quantizing
        bid_px = target_bid.quantize(cfg.tick_size, rounding=ROUND_DOWN)
        ask_px = target_ask.quantize(cfg.tick_size, rounding=ROUND_UP)

        qty = (self.equity * cfg.risk_pct / micro_price).quantize(cfg.qty_step, rounding=ROUND_DOWN)
        qty = max(qty, cfg.min_qty)

        # Execution
        batch = [
            {"symbol": symbol, "side": "Buy", "orderType": "Limit", "qty": str(qty), "price": str(bid_px), "timeInForce": "PostOnly"},
            {"symbol": symbol, "side": "Sell", "orderType": "Limit", "qty": str(qty), "price": str(ask_px), "timeInForce": "PostOnly"}
        ]

        asyncio.create_task(self.submit(symbol, batch))
        self.last_update[symbol] = now

    async def submit(self, symbol, batch):
        await self.api_call("POST", "/v5/order/cancel-all", {"category": "linear", "symbol": symbol})
        await self.api_call("POST", "/v5/order/create-batch", {"category": "linear", "request": batch})
        print(f"\033[K{Fore.GREEN}LIQUID-EYE | {symbol} | Micro: {batch[0]['price']} | Skew: {self.calculate_strategic_skew(symbol):.2f}", end="\r")

    async def run(self):
        import websockets
        async with aiohttp.ClientSession() as session:
            self.session = session
            # Init Precisions
            res = await self.api_call("GET", "/v5/market/instruments-info", {"category": "linear"})
            if res:
                for i in res['result']['list']:
                    if i['symbol'] in self.symbols:
                        s = i['symbol']
                        self.symbols[s].tick_size = Decimal(i['priceFilter']['tickSize'])
                        self.symbols[s].qty_step = Decimal(i['lotSizeFilter']['qtyStep'])
                        self.symbols[s].min_qty = Decimal(i['lotSizeFilter']['minOrderQty'])

            await self.update_context()

            async with websockets.connect(WS_PUBLIC) as ws:
                subs = [f"orderbook.50.{s}" for s in self.symbols]
                await ws.send(json.dumps({"op": "subscribe", "args": subs}))
                async for msg in ws:
                    d = json.loads(msg)
                    if "topic" in d:
                        sym = d['topic'].split('.')[-1]
                        self.books[sym].update(d['data'], d['type'] == 'snapshot')
                        await self.execute_strategy(sym)

if __name__ == "__main__":
    bot = LiquidEyeMM()
    asyncio.run(bot.run())
