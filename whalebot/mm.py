#!/usr/bin/env python3
"""
Bybit v5 Market-Making Bot - Arcane Ultimate Edition: The Quintuple Sentinel
(Finalized with Robust State Management, Initialization, and Explicit Trading Logic)

The ultimate market-making system featuring the Quintuple Adaptive Skewing Pentacle:
1. Inventory Skew
2. Order Book Imbalance Skew
3. Momentum Skew
4. RSI Skew

Trading Logic:
- Entry: Passive Limit Buy (BID) at skewed price.
- Exit: Passive Limit Sell (ASK) at skewed price.
- Orders are strictly formatted to SymbolInfo (tickSize, lotSize).
- Robust asynchronous I/O handling and comprehensive risk management.
"""

import os
import time
import json
import asyncio
import aiohttp
import hmac
import hashlib
import urllib.parse
import websockets
from dotenv import load_dotenv
import logging
from datetime import datetime, date
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Set, Any
import signal
import sys
from decimal import Decimal, ROUND_DOWN, ROUND_UP, InvalidOperation
import math
import statistics
import uuid

# --- Colorama Enchantment ---
try:
    from colorama import init, Fore as F, Style
    init(autoreset=True)
except ImportError:
    class DummyColor:
        def __getattr__(self, name): return ""
    F = DummyColor()
    Style = DummyColor()

# --- Configuration ---
load_dotenv()
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
IS_TESTNET = os.getenv("BYBIT_TESTNET", "true").lower() == "true"

if not API_KEY or not API_SECRET:
    try: os.system("termux-toast 'Error: Set BYBIT_API_KEY and BYBIT_API_SECRET in .env'")
    except: pass
    raise ValueError("API credentials missing")

BASE_URL = "https://api-testnet.bybit.com" if IS_TESTNET else "https://api.bybit.com"
WS_PUBLIC = "wss://stream-testnet.bybit.com/v5/public/linear" if IS_TESTNET else "wss://stream.bybit.com/v5/public/linear"
WS_PRIVATE = "wss://stream-testnet.bybit.com/v5/private" if IS_TESTNET else "wss://stream.bybit.com/v5/private"

# --- Centralized Configuration Dataclass ---
@dataclass(frozen=True)
class Config:
    SYMBOLS: List[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    BASE_QTY: Decimal = Decimal("0.001")        # Fixed quantity if dynamic calc fails
    DYNAMIC_QTY_PCT: Decimal = Decimal("0.001") # % of equity to use for one side of quote (0.1%)
    MIN_ORDER_VALUE_USD: Decimal = Decimal("1")
    
    # Skew Factor Magnitudes (Max influence for each)
    SKEW_FACTOR: Decimal = Decimal("0.4")       # Inventory skew max influence
    IMBALANCE_FACTOR: Decimal = Decimal("0.3")  # Book imbalance max influence
    MOMENTUM_FACTOR: Decimal = Decimal("0.35")  # Momentum max influence
    RSI_FACTOR: Decimal = Decimal("0.4")        # RSI max influence
    
    # Spread & Volatility Settings
    TARGET_SPREAD_BPS: Decimal = Decimal("5")   # Base spread in basis points
    VOL_SENSITIVITY: Decimal = Decimal("0.8")
    TARGET_VOL_BPS: Decimal = Decimal("10")
    BOOK_DEPTH: int = 10
    
    # Momentum/RSI Settings
    PRICE_HISTORY_LEN: int = 60
    MOMENTUM_WINDOW: int = 20
    MOMENTUM_MAX_BPS: Decimal = Decimal("100")
    RSI_PERIOD: int = 14
    RSI_INTERVAL: str = "5"
    RSI_INIT_KLINES: int = 50 # Number of klines to fetch for initial RSI calculation

    # Risk Settings
    MAX_INVENTORY: Decimal = Decimal("0.05")
    RISK_MAX_DD_PCT: Decimal = Decimal("10")
    RISK_DAILY_LIMIT_PCT: Decimal = Decimal("5")

# --- Logging ---
def conjure_logging():
    logger = logging.getLogger("MM_BOT")
    logger.setLevel(logging.INFO)
    if logger.handlers: logger.handlers.clear()
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(f'{F.CYAN}%(asctime)s{F.RESET} | {F.GREEN}%(levelname)s{F.RESET} | %(message)s'))
    logger.addHandler(console)
    return logger

logger = conjure_logging()

# --- Data Structures ---
@dataclass
class OrderBookLevel:
    price: Decimal
    qty: Decimal

@dataclass
class Candle:
    close: Decimal
    confirmed: bool = False

@dataclass
class MarketData:
    symbol: str
    bid_levels: List[OrderBookLevel] = field(default_factory=list)
    ask_levels: List[OrderBookLevel] = field(default_factory=list)
    last_price: Decimal = Decimal('0')
    mid: Decimal = Decimal('0')
    imbalance: Decimal = Decimal('0')
    momentum: Decimal = Decimal('0')
    rsi: Decimal = Decimal('50')
    ts: float = field(default_factory=time.time)

@dataclass
class Position:
    size: Decimal = Decimal('0')
    unrealised_pnl: Decimal = Decimal('0')
    mark_price: Decimal = Decimal('0')

@dataclass
class SymbolInfo:
    tick_size: Decimal
    lot_size: Decimal
    min_qty: Decimal
    name: str

# --- RSI Indicator Logic (Improved for clarity) ---
class RSIIndicator:
    def __init__(self, period: int):
        self.period = period
        self.candles: deque[Candle] = deque(maxlen=period * 3) # Sufficient history

    def add_candle(self, close: Decimal, confirmed: bool = False):
        if confirmed:
            self.candles.append(Candle(close=close, confirmed=confirmed))

    def calculate_rsi(self) -> Decimal:
        closes = [c.close for c in self.candles if c.confirmed]
        if len(closes) < self.period + 1:
            return Decimal('50') 

        gains = []
        losses = []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i-1]
            gains.append(max(Decimal('0'), diff))
            losses.append(max(Decimal('0'), -diff))

        # Initial calculation (Simple Average)
        initial_gains = gains[:self.period]
        initial_losses = losses[:self.period]
        
        avg_gain = sum(initial_gains) / Decimal(self.period)
        avg_loss = sum(initial_losses) / Decimal(self.period)

        # Smoothed calculation (Wilder's method)
        for i in range(self.period, len(gains)):
            avg_gain = ((avg_gain * Decimal(self.period - 1)) + gains[i]) / Decimal(self.period)
            avg_loss = ((avg_loss * Decimal(self.period - 1)) + losses[i]) / Decimal(self.period)

        if avg_loss == 0:
            return Decimal('100') if avg_gain > 0 else Decimal('50')
        
        rs = avg_gain / avg_loss
        rsi = Decimal('100') - (Decimal('100') / (Decimal('1') + rs))
        return rsi.quantize(Decimal('0.01'))

# --- State Manager ---
class StateManager:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.market: Dict[str, MarketData] = {s: MarketData(s) for s in cfg.SYMBOLS}
        self.price_history: Dict[str, deque] = {s: deque(maxlen=cfg.PRICE_HISTORY_LEN) for s in cfg.SYMBOLS}
        self.rsi_indicators: Dict[str, RSIIndicator] = {s: RSIIndicator(cfg.RSI_PERIOD) for s in cfg.SYMBOLS}
        self.positions: Dict[str, Position] = {s: Position() for s in cfg.SYMBOLS}
        self.symbol_info: Dict[str, SymbolInfo] = {}
        self.current_equity: Decimal = Decimal('0')
        self.initial_equity: Decimal = Decimal('0')
        self.trading_active: bool = False

    def update_market_derived(self, symbol: str):
        md = self.market[symbol]
        bids = md.bid_levels[:self.cfg.BOOK_DEPTH]
        asks = md.ask_levels[:self.cfg.BOOK_DEPTH]
        
        if bids and asks:
            md.mid = (bids[0].price + asks[0].price) / Decimal('2')
            bid_vol = sum(l.qty for l in bids)
            ask_vol = sum(l.qty for l in asks)
            total = bid_vol + ask_vol
            md.imbalance = (bid_vol - ask_vol) / total if total > 0 else Decimal('0')
        else:
            md.mid = Decimal('0')
            md.imbalance = Decimal('0')

    def calculate_momentum(self, symbol: str) -> Decimal:
        prices = list(self.price_history[symbol])
        if len(prices) < self.cfg.MOMENTUM_WINDOW // 2:
            return Decimal('0')
        
        recent = prices[-1]
        older_index = max(0, len(prices) - self.cfg.MOMENTUM_WINDOW)
        older = prices[older_index]
        
        if older == 0: return Decimal('0')
            
        momentum_bps = (recent / older - 1) * Decimal('10000')
        normalized = momentum_bps / self.cfg.MOMENTUM_MAX_BPS
        
        return max(min(normalized, Decimal('1.0')), Decimal('-1.0'))

# --- Risk Guardian ---
class RiskGuardian:
    def __init__(self, cfg: Config, state: StateManager):
        self.cfg = cfg
        self.state = state
        self.daily_realised_pnl = Decimal('0')
        self.today = date.today()
        self.trading_paused = False

    def update_equity_and_pnl(self, total_unrealised: Decimal, current_wallet_equity: Decimal):
        if date.today() != self.today:
            self.daily_realised_pnl = Decimal('0')
            self.today = date.today()
            
        if self.state.initial_equity == 0 and current_wallet_equity > 0:
             self.state.initial_equity = current_wallet_equity

        self.state.current_equity = self.state.initial_equity + self.daily_realised_pnl + total_unrealised
        if self.state.current_equity <= 0:
             self.state.current_equity = current_wallet_equity # Fallback to wallet balance

    def check_risks(self) -> str:
        if self.trading_paused: return "Trading paused due to prior risk breach"

        positions = self.state.positions
        total_unrealised = sum(pos.unrealised_pnl for pos in positions.values())
        unrealised_dd = -total_unrealised if total_unrealised < 0 else Decimal('0')
        
        equity = self.state.current_equity
        if equity <= 0: return "" # Cannot check risk without equity

        reasons = []
        for symbol, pos in positions.items():
            if abs(pos.size) > self.cfg.MAX_INVENTORY:
                reasons.append(f"Max position exceeded on {symbol}: {abs(pos.size):.5f} > {self.cfg.MAX_INVENTORY:.5f}")

        max_dd_amount = equity * (self.cfg.RISK_MAX_DD_PCT / Decimal('100'))
        if unrealised_dd > max_dd_amount:
            reasons.append(f"Unrealised drawdown {unrealised_dd:.2f} USD > {max_dd_amount:.2f} USD ({self.cfg.RISK_MAX_DD_PCT}%)")

        daily_limit_amount = equity * (self.cfg.RISK_DAILY_LIMIT_PCT / Decimal('100'))
        if abs(self.daily_realised_pnl) > daily_limit_amount:
            reasons.append(f"Daily PnL limit breached: {self.daily_realised_pnl:+.2f} USD > {daily_limit_amount:.2f} USD ({self.cfg.RISK_DAILY_LIMIT_PCT}%)")

        if reasons:
            self.trading_paused = True
            msg = "RISK BREACH: " + "; ".join(reasons)
            logger.critical(f"{F.RED}!!! {msg} !!!{F.RESET}")
            try: os.system(f"termux-toast '{msg}'")
            except: pass
            return msg
        return ""

# --- Bybit Client (Refactored) ---
class BybitClient:
    def __init__(self, cfg: Config, state: StateManager):
        self.cfg = cfg
        self.state = state
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws_private: Optional[websockets.WebSocketClientProtocol] = None
        self.ws_public: Optional[websockets.WebSocketClientProtocol] = None
        self.running = True

    async def __aenter__(self):
        connector = aiohttp.TCPConnector(limit=100, limit_per_host=50)
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        return self

    async def __aexit__(self, *args):
        self.running = False
        if self.ws_private: await self.ws_private.close()
        if self.ws_public: await self.ws_public.close()
        if self.session: await self.session.close()

    async def _sign_request(self, method: str, path: str, params: Dict = None) -> Dict[str, str]:
        ts = str(int(time.time() * 1000))
        recv_window = "5000"
        
        if method == 'GET':
            param_str = urllib.parse.urlencode(sorted((params or {}).items()))
            sign_str = f"{ts}{API_KEY}{recv_window}{param_str}"
            content_type = "application/x-www-form-urlencoded"
        else:
            param_str = json.dumps(params or {})
            sign_str = f"{ts}{API_KEY}{recv_window}{param_str}"
            content_type = "application/json"
            
        signature = hmac.new(API_SECRET.encode(), sign_str.encode(), hashlib.sha256).hexdigest()
        return {
            "X-BAPI-API-KEY": API_KEY,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-RECV-WINDOW": recv_window,
            "Content-Type": content_type
        }

    async def _make_request(self, method: str, path: str, params: Dict = None):
        headers = await self._sign_request(method, path, params)
        url = f"{BASE_URL}{path}"
        
        try:
            if method == 'GET':
                full_url = f"{url}?{urllib.parse.urlencode(params or {})}"
                async with self.session.get(full_url, headers=headers) as resp:
                    return await resp.json()
            else:
                async with self.session.request(method, url, headers=headers, json=params) as resp:
                    return await resp.json()
        except Exception as e:
            logger.error(f"API Request failed ({method} {path}): {e}")
            return {"retCode": -1, "retMsg": str(e)}

    # --- REST API Methods (Initialization) ---
    async def get_symbol_info(self, symbol: str) -> bool:
        params = {"category": "linear", "symbol": symbol}
        data = await self._make_request("GET", "/v5/market/instruments-info", params)
        
        if data.get("retCode") == 0 and data["result"]["list"]:
            info = data["result"]["list"][0]
            self.state.symbol_info[symbol] = SymbolInfo(
                tick_size=Decimal(info["priceFilter"]["tickSize"]),
                lot_size=Decimal(info["lotSizeFilter"]["qtyStep"]),
                min_qty=Decimal(info["lotSizeFilter"]["minQty"]),
                name=symbol
            )
            return True
        logger.error(f"Failed to fetch symbol info for {symbol}: {data.get('retMsg')}")
        return False

    async def get_historical_klines(self, symbol: str) -> bool:
        limit = self.cfg.RSI_INIT_KLINES
        params = {"category": "linear", "symbol": symbol, "interval": self.cfg.RSI_INTERVAL, "limit": limit}
        data = await self._make_request("GET", "/v5/market/kline", params)
        
        if data.get("retCode") == 0:
            # Klines are returned in reverse chronological order
            for kline in reversed(data["result"]["list"]):
                self.state.rsi_indicators[symbol].add_candle(Decimal(kline[4]), confirmed=True)
            
            initial_rsi = self.state.rsi_indicators[symbol].calculate_rsi()
            self.state.market[symbol].rsi = initial_rsi
            logger.info(f"{F.BLUE}Initial RSI for {symbol}: {initial_rsi:.2f}{F.RESET}")
            return True
        logger.error(f"Failed to fetch historical klines for {symbol}: {data.get('retMsg')}")
        return False

    async def get_positions(self):
        data = await self._make_request("GET", "/v5/position/list", {"category": "linear"})
        if data.get("retCode") == 0:
            for pos in data["result"]["list"]:
                symbol = pos["symbol"]
                if symbol in self.state.positions:
                    size = Decimal(pos["size"])
                    side = pos["side"]
                    unrealised = Decimal(pos.get("unrealisedPnl", "0"))
                    mark = Decimal(pos.get("markPrice", "0"))
                    net_size = size if side == "Buy" else -size if side == "Sell" else Decimal('0')
                    self.state.positions[symbol] = Position(net_size, unrealised, mark)
        
        # Calculate total unrealized PnL
        total_unrealised = sum(pos.unrealised_pnl for pos in self.state.positions.values())
        return total_unrealised

    async def get_wallet_balance(self) -> Decimal:
        data = await self._make_request("GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED"})
        if data.get("retCode") == 0:
            for acc in data["result"]["list"]:
                if acc["accountType"] == "UNIFIED":
                    return Decimal(acc.get("totalEquity", "0"))
        return Decimal('0')

    # --- REST API Methods (Trading) ---
    async def place_batch(self, orders: List[Dict]) -> Dict:
        payload = {"category": "linear", "request": orders}
        return await self._make_request("POST", "/v5/order/create-batch", payload)

    async def cancel_all(self, symbol: str):
        payload = {"category": "linear", "symbol": symbol}
        return await self._make_request("POST", "/v5/order/cancel-all", payload)

    # --- WebSocket Handling (Public) ---
    async def connect_public_ws(self):
        while self.running:
            try:
                self.ws_public = await websockets.connect(WS_PUBLIC, ping_interval=20, ping_timeout=10)
                orderbook_topics = [f"orderbook.{self.cfg.BOOK_DEPTH}.{s}" for s in self.cfg.SYMBOLS]
                kline_topics = [f"kline.{self.cfg.RSI_INTERVAL}.{s}" for s in self.cfg.SYMBOLS]
                await self.ws_public.send(json.dumps({"op": "subscribe", "args": orderbook_topics + kline_topics}))
                logger.info(f"{F.GREEN}Public WS connected and subscribed (Orderbook & Kline).{F.RESET}")
                await self._handle_public_messages()
            except Exception as e:
                logger.warning(f"Public WS error: {type(e).__name__}: {e}. Retrying in 10s...")
                if self.ws_public: await self.ws_public.close()
                self.ws_public = None
                await asyncio.sleep(10)

    async def _handle_public_messages(self):
        while self.running and self.ws_public:
            try:
                msg = json.loads(await self.ws_public.recv())
                
                if "data" in msg and "b" in msg["data"] and "a" in msg["data"]:
                    # Orderbook/Market Data Update
                    data = msg["data"]
                    symbol = data["s"]
                    md = self.state.market.get(symbol)
                    if not md: continue

                    md.bid_levels = [OrderBookLevel(Decimal(p), Decimal(q)) for p, q in data["b"]]
                    md.ask_levels = [OrderBookLevel(Decimal(p), Decimal(q)) for p, q in data["a"]]
                    md.last_price = Decimal(data.get("lastPrice", "0")) or (md.bid_levels[0].price if md.bid_levels else md.ask_levels[0].price if md.ask_levels else Decimal('0'))

                    self.state.update_market_derived(symbol)
                    
                    if md.last_price > 0:
                        self.state.price_history[symbol].append(md.last_price)
                        md.momentum = self.state.calculate_momentum(symbol)

                elif msg.get("topic", "").startswith("kline.") and "data" in msg:
                    # Kline/RSI Update
                    for candle_data in msg["data"]:
                        symbol = candle_data["symbol"]
                        close = Decimal(candle_data["close"])
                        confirmed = candle_data.get("confirm", False)
                        
                        if symbol in self.state.rsi_indicators:
                            self.state.rsi_indicators[symbol].add_candle(close=close, confirmed=confirmed)
                            self.state.market[symbol].rsi = self.state.rsi_indicators[symbol].calculate_rsi()
                            
            except websockets.exceptions.ConnectionClosed:
                logger.warning("Public WS connection closed. Reconnecting...")
                break
            except Exception as e:
                logger.error(f"Public feed error: {type(e).__name__}: {e}")

# --- Utility Functions ---

def format_price(price: Decimal, tick_size: Decimal, rounding_mode) -> str:
    """Rounds price to the nearest tick_size with specified rounding mode."""
    if tick_size == Decimal('0'): return str(price)
    
    # Ensure tick_size is positive to use the Decimal quantization feature
    abs_tick_size = abs(tick_size)

    # Calculate the price string with the required number of decimal places
    try:
        quantized_price = price.quantize(abs_tick_size, rounding=rounding_mode)
        # Convert to string ensuring no unnecessary scientific notation
        return f"{quantized_price:f}"
    except InvalidOperation:
        return str(price.quantize(Decimal('0'), rounding=rounding_mode)) # Fallback

def format_qty(qty: Decimal, lot_size: Decimal, min_qty: Decimal) -> Decimal:
    """Rounds quantity to the nearest lot_size and ensures it meets min_qty."""
    if lot_size == Decimal('0'): return qty
    
    qty = max(min_qty, qty)
    # Quantize down to the nearest lot_size
    quantized_qty = qty.quantize(lot_size, rounding=ROUND_DOWN)
    
    return quantized_qty if quantized_qty >= min_qty else Decimal('0')

# --- Market Maker Logic (The Quintuple Weaver) ---
class MarketMaker:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.state = StateManager(cfg)
        self.risk_guardian = RiskGuardian(cfg, self.state)
        self.client: Optional[BybitClient] = None
        self.running = False

    async def initialize_bot(self) -> bool:
        """Fetches all necessary initial data before starting the main loop."""
        logger.info(f"{F.YELLOW}Initializing Quintuple Sentinel...{F.RESET}")
        
        # 1. Fetch Symbol Info
        info_tasks = [self.client.get_symbol_info(s) for s in self.cfg.SYMBOLS]
        if not all(await asyncio.gather(*info_tasks)):
            logger.error(f"{F.RED}Failed to load all symbol information. Cannot proceed.{F.RESET}")
            return False
            
        # 2. Fetch Historical Data for RSI
        kline_tasks = [self.client.get_historical_klines(s) for s in self.cfg.SYMBOLS]
        await asyncio.gather(*kline_tasks)
        
        # 3. Fetch Initial Wallet and Position Data
        wallet_balance = await self.client.get_wallet_balance()
        unrealised_pnl = await self.client.get_positions()
        
        self.risk_guardian.update_equity_and_pnl(unrealised_pnl, wallet_balance)
        logger.info(f"{F.CYAN}Initial Equity: {self.state.current_equity:.2f} USD. Ready.{F.RESET}")
        return True

    def calculate_volatility_bps(self, symbol: str) -> Decimal:
        prices = list(self.state.price_history[symbol])
        if len(prices) < 10: return self.cfg.TARGET_VOL_BPS
        
        # Log return calculation for volatility
        returns = [Decimal(math.log(prices[i] / prices[i-1])) * Decimal('10000') for i in range(1, len(prices))]
        try:
            vol = Decimal(statistics.stdev(returns)) if len(returns) > 1 else Decimal('1')
        except statistics.StatisticsError:
            vol = Decimal('1')
        
        return max(vol, Decimal('1'))

    def rsi_to_skew(self, rsi: Decimal) -> Decimal:
        """High RSI -> Negative Skew (sell), Low RSI -> Positive Skew (buy)"""
        deviation = rsi - Decimal('50')
        normalized = deviation / Decimal('50') 
        return -normalized

    def calculate_dynamic_qty(self, symbol: str, mid_price: Decimal) -> Decimal:
        """Determines the order quantity based on fixed size or equity percentage."""
        if self.state.current_equity <= self.cfg.MIN_ORDER_VALUE_USD:
            return self.cfg.BASE_QTY

        try:
            # Desired order value based on equity percentage
            target_value = self.state.current_equity * self.cfg.DYNAMIC_QTY_PCT
            
            # Convert value to quantity
            dynamic_qty = target_value / mid_price
            
            info = self.state.symbol_info.get(symbol)
            if not info: return self.cfg.BASE_QTY

            # Check if the calculated quantity meets the minimum order value
            if dynamic_qty * mid_price < self.cfg.MIN_ORDER_VALUE_USD:
                 # Use minimum quantity that meets the dollar value, if needed
                 min_qty_value = self.cfg.MIN_ORDER_VALUE_USD / mid_price
                 qty_to_format = max(dynamic_qty, min_qty_value)
            else:
                 qty_to_format = dynamic_qty
                 
            return format_qty(qty_to_format, info.lot_size, info.min_qty)
            
        except Exception as e:
            logger.warning(f"Error calculating dynamic quantity for {symbol}: {e}. Falling back to base quantity.")
            return self.cfg.BASE_QTY
            
    async def start(self):
        self.running = True
        
        async with BybitClient(self.cfg, self.state) as client:
            self.client = client
            
            if not await self.initialize_bot():
                self.running = False
                return

            tasks = [
                asyncio.create_task(self.client.connect_public_ws()),
                # asyncio.create_task(self.client.connect_private_ws()), # Uncomment and implement private WS
                asyncio.create_task(self.rebalance_loop()),
            ]
            
            # Run tasks and wait for at least one to complete (which should be the main loop)
            await asyncio.gather(*tasks)

    async def rebalance_loop(self):
        max_total_skew_magnitude = (
            self.cfg.SKEW_FACTOR + self.cfg.IMBALANCE_FACTOR + 
            self.cfg.MOMENTUM_FACTOR + self.cfg.RSI_FACTOR
        )
        
        while self.running:
            await asyncio.sleep(1) # Base interval check

            risk_msg = self.risk_guardian.check_risks()
            if risk_msg:
                # await self.emergency_flatten() # Uncomment when flatten is implemented
                continue
            
            if not self.state.trading_active:
                if all(md.mid > 0 for md in self.state.market.values()):
                    self.state.trading_active = True
                else:
                    logger.warning("Waiting for all symbols to receive initial market data...")
                    continue
            
            # --- Trading Cycle ---
            
            # 1. Cancel existing orders to prepare for new quotes
            await asyncio.gather(*[self.client.cancel_all(s) for s in self.cfg.SYMBOLS])
            await asyncio.sleep(0.1) # Wait for cancellations to process

            # 2. Prepare new batch orders
            batch = []
            
            for symbol in self.cfg.SYMBOLS:
                md = self.state.market.get(symbol)
                info = self.state.symbol_info.get(symbol)
                pos = self.state.positions.get(symbol, Position())

                if not md or not info or not md.mid > 0: continue

                # --- 2a. Dynamic Quantity and Volatility Adjustment ---
                qty = self.calculate_dynamic_qty(symbol, md.mid)
                if qty == Decimal('0'): continue
                
                current_vol_bps = self.calculate_volatility_bps(symbol)
                vol_ratio = current_vol_bps / self.cfg.TARGET_VOL_BPS
                adjusted_spread_bps = self.cfg.TARGET_SPREAD_BPS * (vol_ratio ** self.cfg.VOL_SENSITIVITY)
                base_spread = md.mid * adjusted_spread_bps / Decimal('10000')

                # --- 2b. The Quintuple Skew Calculation (TS) ---
                
                # Inventory Skew (Negative when long, to favor selling/exit)
                inventory_normalized = pos.size / self.cfg.MAX_INVENTORY if self.cfg.MAX_INVENTORY > 0 else Decimal('0')
                inventory_skew = self.cfg.SKEW_FACTOR * max(min(inventory_normalized, Decimal('1.0')), Decimal('-1.0'))

                # Book Imbalance Skew (+ means bid heavy, favors buying/entry)
                book_imbalance_skew = self.cfg.IMBALANCE_FACTOR * md.imbalance

                # Momentum Skew (+ means bullish, favors buying/entry)
                momentum_skew = self.cfg.MOMENTUM_FACTOR * md.momentum
                
                # RSI Skew (High RSI -> Negative Skew to sell into overbought)
                rsi_skew = self.cfg.RSI_FACTOR * self.rsi_to_skew(md.rsi)

                total_skew = inventory_skew + book_imbalance_skew + momentum_skew + rsi_skew
                
                # Clamp TS by Max Magnitude and normalize to get NTS in [-1.0, 1.0]
                total_skew = max(min(total_skew, max_total_skew_magnitude), -max_total_skew_magnitude)
                normalized_total_skew = total_skew / max_total_skew_magnitude if max_total_skew_magnitude > 0 else Decimal('0')

                # --- 2c. Skew-Adjusted Spread Application (Entry/Exit Pricing) ---
                
                # Positive NTS -> Tighten Buy (ENTRY), Widen Sell (EXIT)
                # Max skew adjustment factor is 0.5 (half the spread can be shifted)
                buy_spread_factor = Decimal('1') - normalized_total_skew * Decimal('0.5')
                sell_spread_factor = Decimal('1') + normalized_total_skew * Decimal('0.5')
                
                # Ensure spread factors are at least 0.5 (prevent crossing mid-price/too tight spread)
                buy_spread_factor = max(buy_spread_factor, Decimal('0.5'))
                sell_spread_factor = max(sell_spread_factor, Decimal('0.5'))

                # Calculate Prices (Entry/Exit Action)
                buy_price = Decimal(format_price(md.mid - base_spread * buy_spread_factor, info.tick_size, ROUND_DOWN))
                sell_price = Decimal(format_price(md.mid + base_spread * sell_spread_factor, info.tick_size, ROUND_UP))
                
                # Log the logic clearly 
                logger.info(f"{F.YELLOW}{symbol}{F.RESET} | Eq:{self.state.current_equity:.0f} Pos:{pos.size:+.4f} | "
                            f"Vol:{current_vol_bps:.0f}bps Spread:{adjusted_spread_bps:.1f}bps | "
                            f"RSI:{md.rsi:.0f} NTS:{normalized_total_skew:+.2f} | "
                            f"{F.GREEN}BID ENTRY:{buy_price:,.2f} {F.RESET}({qty} QTY) | "
                            f"{F.RED}ASK EXIT:{sell_price:,.2f}{F.RESET}")

                # 3. Batch Order Creation
                batch.extend([
                    # ENTRY: Limit Buy order (PostOnly to ensure passive entry)
                    {"symbol": symbol, "side": "Buy",  "orderType": "Limit", "qty": str(qty),
                     "price": str(buy_price),  "timeInForce": "PostOnly", "orderLinkId": str(uuid.uuid4())},
                    # EXIT: Limit Sell order (PostOnly to ensure passive exit)
                    {"symbol": symbol, "side": "Sell", "orderType": "Limit", "qty": str(qty),
                     "price": str(sell_price), "timeInForce": "PostOnly", "orderLinkId": str(uuid.uuid4())}
                ])
                
            # 4. Execute Batch Orders
            if batch and not self.risk_guardian.trading_paused:
                result = await self.client.place_batch(batch)
                if result.get("retCode") == 0:
                    logger.info(f"{F.CYAN}Batch orders ({len(batch)}) conjured and placed.{F.RESET}")
                else:
                    logger.warning(f"Batch failed: {result.get('retMsg')}")


    async def stop(self):
        if not self.running: return
        self.running = False
        logger.info(f"{F.MAGENTA}Commencing graceful shutdown. Cancelling all orders...{F.RESET}")
        
        cancel_tasks = [self.client.cancel_all(s) for s in self.cfg.SYMBOLS]
        await asyncio.gather(*cancel_tasks, return_exceptions=True)
        
        logger.info(f"{F.MAGENTA}Shutdown complete. The Quintuple Sentinel rests.{F.RESET}")

# --- Invocation ---
async def main():
    cfg = Config()
    
    bot = MarketMaker(cfg)

    # Signal handling for clean exit
    loop = asyncio.get_event_loop()
    def signal_handler(sig):
        logger.info(f"Received signal {sig}. Initiating graceful shutdown...")
        # Schedule the coroutine execution safely
        asyncio.create_task(bot.stop()) 
        
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: signal_handler(sig))
        except NotImplementedError: # Handling systems that don't support signal_handler (e.g., Windows)
             pass

    try:
        await bot.start()
    except Exception as e:
        logger.critical(f"{F.RED}Catastrophic failure: {type(e).__name__}: {e}{F.RESET}")
        try: os.system("termux-toast 'Market Maker crashed!'")
        except: pass
    finally:
        if bot.running:
            await bot.stop()

if __name__ == "__main__":
    try:
        # Ensure statistics library is imported successfully before running
        import statistics 
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception:
        # Re-raise catastrophic errors outside of the bot's handling
        raise
