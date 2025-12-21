from __future__ import annotations
import os
import asyncio
import hmac
import hashlib
import json
import time
import urllib.parse
from dataclasses import dataclass, field
from collections import deque
from decimal import Decimal, ROUND_DOWN, getcontext, InvalidOperation
from typing import Any, Optional, Deque, Tuple, Dict, List

import aiohttp
import numpy as np
from colorama import init, Fore, Back, Style
from dotenv import load_dotenv
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Initialize the Primal Glow
init(autoreset=True)
getcontext().prec = 28
load_dotenv()

API_KEY = os.getenv("BYBIT_API_KEY", "")
API_SECRET = os.getenv("BYBIT_API_SECRET", "")
IS_TESTNET = os.getenv("BYBIT_TESTNET", "false").lower() == "true"

@dataclass(slots=True)
class ScalperConfig:
    symbol: str = os.getenv("SCALPER_SYMBOL", "BCHUSDT")
    category: str = os.getenv("SCALPER_CATEGORY", "linear")
    leverage: int = int(os.getenv("SCALPER_LEVERAGE", "20"))
    
    # --- Execution guards ---
    max_latency_ms: int = int(os.getenv("SCALPER_MAX_LATENCY_MS", "350"))
    max_spread_pct: Decimal = Decimal(os.getenv("SCALPER_MAX_SPREAD_PCT", "0.0012"))
    max_hold_sec: int = int(os.getenv("SCALPER_MAX_HOLD_SEC", "180"))
    
    # --- Risk Grimoire ---
    risk_per_trade_usdt: Decimal = Decimal(os.getenv("SCALPER_RISK_USDT", "5.0"))
    tp_atr_mult: Decimal = Decimal("2.3")  # Targeting higher alpha
    sl_atr_mult: Decimal = Decimal("1.1")
    be_trigger_mult: Decimal = Decimal("1.0") # Move to BE at 1:1 RR
    stagnation_limit_sec: int = 120           # Reap if no move in 2 mins
    tp_pct: Decimal = Decimal(os.getenv("SCALPER_TP_PCT", "0.013"))
    sl_pct: Decimal = Decimal(os.getenv("SCALPER_SL_PCT", "0.0075"))
    loss_cooldown_multiplier: int = int(os.getenv("SCALPER_LOSS_COOLDOWN_MULT", "3"))
    
    # --- Singularity Thresholds ---
    min_alpha_singularity: float = 75.0
    obi_weight: float = 0.45
    momentum_weight: float = 0.35
    trend_weight: float = 0.20
    min_alpha_standard: float = 70.0
    alpha_ignition_boost: float = 55.0
    vsi_threshold: float = 1.4
    
    # --- Signals ---
    obi_threshold: float = float(os.getenv("SCALPER_OBI_THRESHOLD", "0.28"))
    fisher_momentum_threshold: float = float(os.getenv("SCALPER_FISHER_MOMENTUM", "0.18"))
    min_atr: float = float(os.getenv("SCALPER_MIN_ATR", "3.0"))
    
    # --- Temporal Rhythm ---
    kline_interval: str = os.getenv("SCALPER_KLINE_INTERVAL", "1")
    cooldown_sec: int = int(os.getenv("SCALPER_COOLDOWN_SEC", "6"))
    warmup_candles: int = int(os.getenv("SCALPER_WARMUP_CANDLES", "60"))
    kline_fetch_limit: int = int(os.getenv("SCALPER_KLINE_FETCH_LIMIT", "200"))
    
    # --- WS ---
    ws_heartbeat_sec: int = int(os.getenv("SCALPER_WS_HEARTBEAT_SEC", "20"))
    ws_stale_ticker_sec: int = int(os.getenv("SCALPER_WS_STALE_TICKER_SEC", "4"))

    def validate(self) -> None:
        if not self.symbol:
            raise ValueError("symbol is empty")
        if self.leverage <= 0:
            raise ValueError("leverage must be > 0")
        if self.risk_per_trade_usdt <= 0:
            raise ValueError("risk_per_trade_usdt must be > 0")
        if self.tp_pct <= 0 or self.sl_pct <= 0:
            raise ValueError("tp_pct and sl_pct must be > 0")
        if self.kline_fetch_limit < 50:
            raise ValueError("kline_fetch_limit too small; use >= 50")

@dataclass(slots=True)
class ScalperState:
    config: ScalperConfig
    
    # Vault Stats
    balance: Decimal = Decimal("0")
    equity: Decimal = Decimal("0")
    available: Decimal = Decimal("0")
    initial_balance: Decimal = Decimal("0")
    daily_pnl: Decimal = Decimal("0")
    last_balance_update: float = 0.0
    trade_count: int = 0
    wins: int = 0 # From bch2.0/bch2.3
    profitable_trades: int = 0 # From bchx/bchxx
    
    # The Living Market
    price: Decimal = Decimal("0")
    bid: Decimal = Decimal("0")
    ask: Decimal = Decimal("0")
    obi_score: float = 0.0 # From bch2.4/bch2.3
    obi_raw: float = 0.0 # Renamed from obi in bch2.0/bchx/bchxx
    atr: float = 0.0
    fisher: float = 0.0
    fisher_sig: float = 0.0 # From bch2.4/bch2.3
    fisher_prev: float = 0.0 # From bchx/bchxx
    ema_fast: Decimal = Decimal("0") # From bch2.4/bch2.0
    ema_slow: Decimal = Decimal("0") # From bch2.4/bch2.0
    ema_micro: Decimal = Decimal("0") # From bch2.3
    ema_macro: Decimal = Decimal("0") # From bch2.3
    alpha_singularity: float = 0.0 # From bch2.4
    alpha_raw: float = 0.0 # Renamed from alpha_score in bch2.3
    vsi: float = 1.0 # From bch2.3
    tick_velocity: float = 0.0
    vwap: Decimal = Decimal("0") # From bchx/bchxx
    
    # Position Matrix
    active: bool = False
    side: str = "HOLD"
    qty: Decimal = Decimal("0")
    entry_price: Decimal = Decimal("0") # Renamed from entry_p in bch2.4/bch2.3
    upnl: Decimal = Decimal("0")
    entry_ts: float = 0.0
    be_active: bool = False
    position_open_ts: float = 0.0 # From bchx/bchxx
    
    # Execution state
    last_trade_ts: float = 0.0
    last_was_loss: bool = False # From bchx/bchxx
    ready: bool = False
    warmup_progress: int = 0 # From bchx/bchxx
    
    # Temporal Buffers
    ohlc: Deque[Tuple[float, float, float, float, float]] = field(default_factory=lambda: deque(maxlen=400)) # Standardized to (open, high, low, close, volume)
    tick_history: Deque[float] = field(default_factory=lambda: deque(maxlen=40))
    
    # Metadata
    price_prec: int = 2
    qty_step: Decimal = Decimal("0.01")
    min_qty: Decimal = Decimal("0.01")
    latency_ms: int = 0 # Renamed from latency in bch2.4/bch2.3
    last_ticker_ts: float = 0.0 # From bchx/bchxx
    logs: Deque[str] = field(default_factory=lambda: deque(maxlen=28)) # Maxlen from bchx/bchxx
    
    local_bids: Dict[Decimal, Decimal] = field(default_factory=dict) # From bch2.4/bch2.0
    local_asks: Dict[Decimal, Decimal] = field(default_factory=dict) # From bch2.4/bch2.0

    def log(self, msg: str, style: str = "white"):
        ts = time.strftime("%H:%M:%S")
        self.logs.append(f"[dim]{ts}[/] [{style}]{msg}[/]")

# =========================
# BYBIT APEX V10 SINGULARITY
# =========================

def safe_decimal(val: Any, default: str = "0") -> Decimal:
    if val is None:
        return Decimal(default)
    try:
        return Decimal(str(val).replace(",", "").strip())
    except Exception:
        return Decimal(default)

def clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x

def quantize_step(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return value
    if value <= 0:
        return Decimal("0")
    n = (value / step).to_integral_value(rounding=ROUND_DOWN)
    return (n * step).normalize()

def spread_pct(bid: Decimal, ask: Decimal) -> Decimal:
    if bid <= 0 or ask <= 0:
        return Decimal("999")
    mid = (bid + ask) / 2
    if mid <= 0:
        return Decimal("999")
    return (ask - bid) / mid

class BybitApex:
    def __init__(self, state: ScalperState):
        self.state = state
        self.cfg = state.config
        self.base = "https://api-testnet.bybit.com" if IS_TESTNET else "https://api.bybit.com"
        self.ws_pub = (
            "wss://stream-testnet.bybit.com/v5/public/linear"
            if IS_TESTNET
            else "wss://stream.bybit.com/v5/public/linear"
        )
        self.ws_priv = (
            "wss://stream-testnet.bybit.com/v5/private"
            if IS_TESTNET
            else "wss://stream.bybit.com/v5/private"
        )
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=10, connect=4, sock_read=8)
        connector = aiohttp.TCPConnector(limit=50, enable_cleanup_closed=True, ttl_dns_cache=300)
        self.session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        return self

    async def __aexit__(self, *exc: Any):
        if self.session: await self.session.close()

    @staticmethod
    def _canonical_query(params: Dict[str, Any]) -> str:
        items = []
        for k in sorted(params.keys()):
            v = params[k]
            if v is None:
                continue
            items.append((k, str(v)))
        return urllib.parse.urlencode(items)

    @staticmethod
    def _canonical_json(params: Dict[str, Any]) -> str:
        return json.dumps(params, separators=( ",", ":"), sort_keys=True)

    def _sign_headers(self, payload: str) -> Dict[str, str]:
        ts = str(int(time.time() * 1000))
        recv = "5000"
        prehash = f"{ts}{API_KEY}{recv}{payload}"
        sig = hmac.new(API_SECRET.encode(), prehash.encode(), hashlib.sha256).hexdigest()
        return {
            "X-BAPI-API-KEY": API_KEY,
            "X-BAPI-SIGN": sig,
            "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-RECV-WINDOW": recv,
            "Content-Type": "application/json",
        }

    async def api_call(self, method: str, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        assert self.session is not None
        url = self.base + path
        params = params or {}

        if method.upper() == "GET":
            payload = self._canonical_query(params) if params else ""
            if payload:
                url = f"{url}?{payload}"
            body = None
        else:
            payload = self._canonical_json(params) if params else ""
            body = payload.encode() if payload else b""

        headers = self._sign_headers(payload)

        backoff = 0.35
        for attempt in range(5):
            try:
                async with self.session.request(method.upper(), url, headers=headers, data=body) as resp:
                    data = await resp.json(content_type=None)

                    ret = int(data.get("retCode", -1))
                    if ret == 0:
                        return data

                    msg = data.get("retMsg", "Unknown error")
                    if ret in (10006, 10018):
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 1.8, 3.0)
                        continue

                    return data

            except (aiohttp.ClientError, asyncio.TimeoutError):
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.8, 3.0)

        return {"retCode": -1, "retMsg": "REST retries exhausted"}

    async def fetch_kline_history(self) -> None:
        params = {
            "category": self.cfg.category,
            "symbol": self.cfg.symbol,
            "interval": self.cfg.kline_interval,
            "limit": self.cfg.kline_fetch_limit,
        }
        resp = await self.api_call("GET", "/v5/market/kline", params)
        if resp.get("retCode") != 0:
            self.state.log(f"[red]Failed kline history: {resp.get('retMsg')}[/red]")
            return

        for k in reversed(resp["result"]["list"]):
            self.state.ohlc.append((float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5]))) # (open, high, low, close, volume)
        self._weave_indicators()
        self.state.log("[cyan]Historical candles loaded — oracle warming[/cyan]")

    async def refresh_instrument_filters(self) -> None:
        resp = await self.api_call(
            "GET",
            "/v5/market/instruments-info",
            {"category": self.cfg.category, "symbol": self.cfg.symbol},
        )
        if resp.get("retCode") != 0:
            self.state.log(f"[red]Instrument info failed: {resp.get('retMsg')}[/red]")
            return
        i = resp["result"]["list"][0]
        tick = safe_decimal(i["priceFilter"]["tickSize"])
        self.state.price_prec = abs(tick.normalize().as_tuple().exponent)
        self.state.qty_step = safe_decimal(i["lotSizeFilter"]["qtyStep"])
        self.state.min_qty = safe_decimal(i["lotSizeFilter"]["minOrderQty"])
        self.state.log(
            f"[dim]Filters: tick={tick} qtyStep={self.state.qty_step} minQty={self.state.min_qty}[/dim]"
        )

    async def refresh_wallet_once(self) -> None:
        resp = await self.api_call("GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED"})
        if resp.get("retCode") != 0:
            self.state.log(f"[red]Wallet fetch failed: {resp.get('retMsg')}[/red]")
            return
        for acct in resp["result"]["list"]:
            for coin in acct.get("coin", []):
                if coin.get("coin") == "USDT":
                    self.state.balance = safe_decimal(coin.get("walletBalance"))
                    self.state.available = safe_decimal(coin.get("availableToWithdraw"))
                    if self.state.initial_equity <= 0: # Use initial_equity from state
                        self.state.initial_equity = self.state.equity # Assuming equity is updated elsewhere or initialized
                    self.state.daily_pnl = self.state.equity - self.state.initial_equity
                    self.state.last_balance_update = time.time()

    async def set_leverage(self) -> None:
        resp = await self.api_call(
            "POST",
            "/v5/position/set-leverage",
            {
                "category": self.cfg.category,
                "symbol": self.cfg.symbol,
                "buyLeverage": str(self.cfg.leverage),
                "sellLeverage": str(self.cfg.leverage),
            },
        )
        if resp.get("retCode") == 0:
            self.state.log(f"[green]Leverage set to {self.cfg.leverage}x[/green]")
        else:
            self.state.log(f"[yellow]Leverage set failed: {resp.get('retMsg')}[/yellow]")

    async def scalp_market(self, side: str, qty: Decimal, *, reduce_only: bool = False) -> None:
        s = self.state
        c = self.cfg

        if s.latency_ms > c.max_latency_ms:
            s.log("[dim]Latency storm — withheld[/dim]")
            return

        sp = spread_pct(s.bid, s.ask)
        if sp > c.max_spread_pct:
            s.log(f"[dim]Spread too wide ({sp:.4%}) — withheld[/dim]")
            return

        qty = quantize_step(qty, s.qty_step)
        if qty < s.min_qty:
            s.log("[dim]Qty below min — withheld[/dim]")
            return

        params = {
            "category": c.category,
            "symbol": c.symbol,
            "side": side,
            "orderType": "Market",
            "qty": str(qty),
            "reduceOnly": reduce_only,
        }
        resp = await self.api_call("POST", "/v5/order/create", params)
        if resp.get("retCode") == 0:
            kind = "EXIT" if reduce_only else "ENTRY"
            s.log(f"[bold bright_cyan]⚡ {kind} {side} {qty}[/bold bright_cyan]")
            s.last_trade_ts = time.time()
            s.trade_count += 1
            # Proactive balance refresh after trade
            await asyncio.sleep(0.5)
            await self.refresh_wallet_once()
        else:
            s.log(f"[bold red]Order failed: {resp.get('retMsg')}[/bold red]")

    def _weave_indicators(self, live_p: float = None):
        n = len(self.state.ohlc)
        if n < 50: return
        
        # Extract OHLCV data
        opens = np.array([x[0] for x in self.state.ohlc], dtype=np.float64)
        highs = np.array([x[1] for x in self.state.ohlc], dtype=np.float64)
        lows = np.array([x[2] for x in self.state.ohlc], dtype=np.float64)
        closes = np.array([x[3] for x in self.state.ohlc], dtype=np.float64)
        volumes = np.array([x[4] for x in self.state.ohlc], dtype=np.float64)

        # Update last close with live price if available
        if live_p: closes[-1] = live_p
        
        # 1. High-Precision ATR (from bchx.py)
        tr = np.maximum(highs[1:] - lows[1:], np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1]))
        if tr.size >= 14:
            self.state.atr = float(np.mean(tr[-14:]))
        else:
            self.state.atr = 0.0

        # 2. Fisher Transform Acceleration (combined from bch2.4.py and bchx.py)
        window = closes[-10:]
        mn, mx = np.min(window), np.max(window) + 1e-12
        raw = 2 * ((float(closes[-1]) - mn) / (mx - mn) - 0.5)
        raw = float(np.clip(raw, -0.999, 0.999))
        self.state.fisher_prev = self.state.fisher # Store previous Fisher for momentum
        fish = 0.5 * np.log((1 + raw) / (1 - raw + 1e-12))
        self.state.fisher = float(0.5 * fish + 0.5 * self.state.fisher_prev) # Smoothed Fisher
        self.state.fisher_sig = (0.25 * self.state.fisher) + (0.75 * self.state.fisher_sig) # Fisher Signal

        # 3. Dual-EMA Convergence (Fast and Slow from bch2.4.py/bch2.0.py)
        def ema(data, period):
            if len(data) < period: return Decimal("0")
            alpha = 2 / (period + 1)
            res = data[0]
            for val in data[1:]: res = alpha * val + (1 - alpha) * res
            return Decimal(str(res))
        
        self.state.ema_fast = ema(closes[-12:], 12)
        self.state.ema_slow = ema(closes[-26:], 26)

        # 4. Micro & Macro Trend (from bch2.3.py)
        self.state.ema_micro = ema(closes[-self.cfg.micro_ema_period:], self.cfg.micro_ema_period)
        self.state.ema_macro = ema(closes[-self.cfg.macro_ema_period:], self.cfg.macro_ema_period)

        # 5. Volume Surge Index (VSI) (from bch2.3.py)
        if len(volumes) >= 10:
            avg_v = np.mean(volumes[-10:])
            self.state.vsi = volumes[-1] / avg_v if avg_v > 0 else 1.0
        else:
            self.state.vsi = 1.0

        # 6. VWAP over last 20 candles (from bchx.py)
        if n >= 20:
            typ = (highs[-20:] + lows[-20:] + closes[-20:]) / 3.0
            vol = volumes[-20:]
            vol_sum = float(np.sum(vol)) or 1.0
            vwap_val = float(np.sum(typ * vol) / vol_sum)
            self.state.vwap = safe_decimal(vwap_val)
        else:
            self.state.vwap = Decimal("0")

        # --- SINGULARITY SCORE CALCULATION (from bch2.4.py) ---
        score = 0.0
        # Orderbook Dominance (OBI)
        score += min(100 * self.cfg.obi_weight, abs(self.state.obi_score) * 120 * self.cfg.obi_weight)
        # Momentum Acceleration (Fisher)
        score += min(100 * self.cfg.momentum_weight, abs(self.state.fisher) * 40 * self.cfg.momentum_weight)
        # Trend Confluence
        trend_aligned = (self.state.price > self.state.ema_fast) if self.state.fisher > 0 else (self.state.price < self.state.ema_fast)
        if trend_aligned: score += (100 * self.cfg.trend_weight)
        self.state.alpha_singularity = score
        
        # --- ALPHA CONFLUENCE ENGINE V8 (from bch2.3.py) ---
        alpha_score_raw = 0.0
        alpha_score_raw += min(40, abs(self.state.fisher) * 30)
        alpha_score_raw += min(40, abs(self.state.obi_score) * 60)
        trend_aligned_raw = (self.state.price > self.state.ema_macro and self.state.price > self.state.ema_micro) if self.state.fisher > 0 else \
                        (self.state.price < self.state.ema_macro and self.state.price < self.state.ema_micro)
        if trend_aligned_raw: alpha_score_raw += 20
        if self.state.vsi > self.cfg.vsi_threshold: alpha_score_raw += 10
        self.state.alpha_raw = alpha_score_raw

        # Ready gate and Warmup Progress (from bchx.py)
        warm_target = max(20, self.cfg.warmup_candles)
        self.state.warmup_progress = int(clamp01(n / warm_target) * 100)
        if n >= warm_target and self.state.atr >= self.cfg.min_atr:
            self.state.ready = True
            self.state.warmup_progress = 100

    async def public_ws(self, stop: asyncio.Event) -> None:
        assert self.session is not None
        backoff = 0.5

        while not stop.is_set():
            try:
                async with self.session.ws_connect(
                    self.ws_pub,
                    heartbeat=self.cfg.ws_heartbeat_sec,
                    receive_timeout=self.cfg.ws_heartbeat_sec * 2,
                    max_msg_size=10_000_000,
                ) as ws:
                    backoff = 0.5
                    await ws.send_json(
                        {
                            "op": "subscribe",
                            "args": [
                                f"kline.{self.cfg.kline_interval}.{self.cfg.symbol}",
                                f"tickers.{self.cfg.symbol}",
                                f"orderbook.50.{self.cfg.symbol}",
                            ],
                        }
                    )

                    async for msg in ws:
                        if stop.is_set():
                            break
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            continue

                        data = json.loads(msg.data)
                        topic = data.get("topic", "")

                        if topic.startswith("kline.") and data.get("data"):
                            k = data["data"][0]
                            if k.get("confirm"):
                                self.state.ohlc.append(
                                    (float(k["open"]), float(k["high"]), float(k["low"]), float(k["close"]), float(k["volume"]))
                                )
                                self._weave_indicators(float(k["close"]))

                        elif topic.startswith("orderbook."):
                            ob = data.get("data", {})
                            if data.get("type") == "snapshot":
                                self.state.local_bids.clear(); self.state.local_asks.clear()
                            for p, q in ob.get("b", []):
                                if Decimal(q) == 0: self.state.local_bids.pop(Decimal(p), None)
                                else: self.state.local_bids[Decimal(p)] = Decimal(q)
                            for p, q in ob.get("a", []):
                                if Decimal(q) == 0: self.state.local_asks.pop(Decimal(p), None)
                                else: self.state.local_asks[Decimal(p)] = Decimal(q)
                            
                            # Weighted OBI calculation (from bch2.4.py)
                            bids = sorted(self.state.local_bids.items(), reverse=True)[:20]
                            asks = sorted(self.state.local_asks.items())[:20]
                            w_b = sum(float(q) / (i + 1) for i, (_, q) in enumerate(bids))
                            w_a = sum(float(q) / (i + 1) for i, (_, q) in enumerate(asks))
                            self.state.obi_score = (w_b - w_a) / (w_b + w_a + 1e-9)

                            # Raw OBI calculation (from bchx.py)
                            bids_raw = sum(float(x[1]) for x in (ob.get("b") or [])[:30])
                            asks_raw = sum(float(x[1]) for x in (ob.get("a") or [])[:30])
                            tot_raw = bids_raw + asks_raw or 1.0
                            self.state.obi_raw = (bids_raw - asks_raw) / tot_raw

                        elif topic.startswith("tickers."):
                            t = data.get("data", {})
                            if isinstance(t, list) and t:
                                t = t[0]

                            self.state.price = safe_decimal(t.get("lastPrice"))
                            self.state.bid = safe_decimal(t.get("bid1Price"))
                            self.state.ask = safe_decimal(t.get("ask1Price"))
                            self.state.last_ticker_ts = time.time()

                            self.state.tick_history.append(time.time())
                            if len(self.state.tick_history) > 2:
                                self.state.tick_velocity = len(self.state.tick_history) / (self.state.tick_history[-1] - self.state.tick_history[0])

                            ts = t.get("ts")
                            if ts is not None:
                                try:
                                    self.state.latency_ms = int(time.time() * 1000) - int(ts)
                                except Exception:
                                    pass

            except Exception:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.8, 5.0)

    async def singularity_loop(self, stop: asyncio.Event):
        s = self.state
        c = self.cfg

        while not stop.is_set():
            await asyncio.sleep(0.30) # Faster scan rate

            # Stale ticker guard (avoids trading on dead feed)
            if s.last_ticker_ts and (time.time() - s.last_ticker_ts) > c.ws_stale_ticker_sec:
                s.log("[dim]Stale ticker — waiting[/dim]")
                continue

            if not s.ready or s.price <= 0 or s.atr <= 0:
                continue

            # Cooldown after trades; longer cooldown after a loss
            cooldown = c.cooldown_sec * (c.loss_cooldown_multiplier if s.last_was_loss else 1)
            if (time.time() - s.last_trade_ts) < cooldown:
                continue
            s.last_was_loss = False # Reset loss flag after cooldown

            # Capital guard
            if s.available < (c.risk_per_trade_usdt * Decimal("1.5")):
                if int(time.time()) % 6 == 0: # Log less frequently
                    s.log("[dim]Available balance low — waiting[/dim]")
                continue

            # --- POSITION MANAGEMENT ---
            if s.active:
                # 1. Break-even Shielding (from bch2.4.py)
                pnl_dist = abs(s.price - s.entry_price)
                trigger = Decimal(str(s.atr * float(c.be_trigger_mult)))
                if not s.be_active and pnl_dist >= trigger:
                    # Move SL to Entry + Fees buffer
                    be_price = s.entry_price * Decimal("1.0004") if s.side == "Buy" else s.entry_price * Decimal("0.9996")
                    await self.api_call("POST", "/v5/position/trading-stop", {
                        "category": c.category, "symbol": c.symbol,
                        "stopLoss": f"{be_price:.{s.price_prec}f}", "positionIdx": 0
                    })
                    s.be_active = True
                    s.log("Shields Up: Breakeven Secured", "cyan")

                # 2. Stagnation Reaper (from bch2.4.py)
                if (time.time() - s.entry_ts) > c.stagnation_limit_sec:
                    await self.scalp_market("Sell" if s.side == "Buy" else "Buy", s.qty, reduce_only=True)
                    s.log("Reaper Engaged: Stagnation Exit", "magenta")
                    continue

                # 3. Max Hold Time (from bchx.py)
                if s.position_open_ts and (time.time() - s.position_open_ts) > c.max_hold_sec:
                    await self.scalp_market("Sell" if s.side == "Buy" else "Buy", s.qty, reduce_only=True)
                    s.log("[yellow]⏱ Max-hold exit[/yellow]")
                    continue

                # 4. PnL% based TP/SL (from bchx.py)
                margin_used = (s.entry_price * s.qty) / Decimal(str(c.leverage)) if s.qty > 0 else Decimal("0")
                pnl_pct = (abs(s.upnl) / margin_used) if margin_used > 0 else Decimal("0")

                if pnl_pct >= c.tp_pct:
                    await self.scalp_market("Sell" if s.side == "Buy" else "Buy", s.qty, reduce_only=True)
                    s.log("[bold green]🎯 Profit scalped (TP%)[/bold green]")
                    continue

                # Note: SL is handled by native SL order, but this acts as a secondary safety
                if pnl_pct < -c.sl_pct:
                    await self.scalp_market("Sell" if s.side == "Buy" else "Buy", s.qty, reduce_only=True)
                    s.log("[bold red]🛑 Loss taken (SL%)[/bold red]")
                    s.last_was_loss = True
                    continue

                # 5. Reversal Exit (from bchx.py)
                fisher_delta = s.fisher - s.fisher_prev
                reversal = (
                    (s.side == "Buy" and fisher_delta < -c.fisher_momentum_threshold)
                    or (s.side == "Sell" and fisher_delta > c.fisher_momentum_threshold)
                )
                if reversal:
                    await self.scalp_market("Sell" if s.side == "Buy" else "Buy", s.qty, reduce_only=True)
                    s.log("[yellow]🔄 Reversal exit[/yellow]")
                    continue
                
                continue # Continue to next loop iteration if position is active

            # --- ENTRY LOGIC ---
            # Risk-based sizing: qty ~= (risk * leverage) / (price * sl_pct)
            # (Keeps loss near risk_per_trade when stop triggers, roughly.)
            denom = (s.price * c.sl_pct)
            if denom <= 0:
                continue
            qty_raw = (c.risk_per_trade_usdt * Decimal(str(c.leverage))) / denom
            qty = quantize_step(qty_raw, s.qty_step)
            if qty < s.min_qty:
                continue

            # Combine alpha thresholds and directional filters
            dynamic_alpha_threshold = c.min_alpha_singularity
            # Enhanced ignition from bch2.3.py
            if abs(s.obi_score) > 0.90 and s.vsi > 1.2:
                dynamic_alpha_threshold = c.alpha_ignition_boost
                s.log("Momentum Ignition Detected!", "magenta")

            if s.alpha_singularity >= dynamic_alpha_threshold:
                # Directional Confluence (from bch2.4.py and bch2.3.py)
                if s.fisher > s.fisher_sig and s.obi_score > 0.3:
                    # Micro-Pullback: Check if price is slightly below EMA_FAST for Buy
                    if s.price <= s.ema_fast * Decimal("1.0005"):
                        await self.scalp_market("Buy", qty)
                elif s.fisher < s.fisher_sig and s.obi_score < -0.3:
                    # Micro-Pullback: Check if price is slightly above EMA_FAST for Sell
                    if s.price >= s.ema_fast * Decimal("0.9995"):
                        await self.scalp_market("Sell", qty)
            
            # Additional entry signals from bchx.py/bchxx.py
            fisher_delta = s.fisher - s.fisher_prev
            long_sig_bchx = (s.obi_raw > c.obi_threshold) and (fisher_delta > c.fisher_momentum_threshold) and (s.price > s.vwap)
            short_sig_bchx = (s.obi_raw < -c.obi_threshold) and (fisher_delta < -c.fisher_momentum_threshold) and (s.price < s.vwap)

            if long_sig_bchx:
                await self.scalp_market("Buy", qty)
            elif short_sig_bchx:
                await self.scalp_market("Sell", qty)

        assert self.session is not None
        backoff = 0.7

        while not stop.is_set():
            try:
                async with self.session.ws_connect(
                    self.ws_priv,
                    heartbeat=self.cfg.ws_heartbeat_sec,
                    receive_timeout=self.cfg.ws_heartbeat_sec * 2,
                    max_msg_size=10_000_000,
                ) as ws:
                    backoff = 0.7

                    expires = int(time.time() * 1000) + 10_000
                    sig = hmac.new(
                        API_SECRET.encode(),
                        f"GET/realtime{expires}".encode(),
                        hashlib.sha256,
                    ).hexdigest()
                    await ws.send_json({"op": "auth", "args": [API_KEY, expires, sig]})
                    await ws.send_json({"op": "subscribe", "args": ["position", "wallet"]})

                    async for msg in ws:
                        if stop.is_set():
                            break
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            continue

                        data = json.loads(msg.data)
                        topic = data.get("topic")

                        if topic == "position":
                            for p in data.get("data", []):
                                if p.get("symbol") != self.cfg.symbol:
                                    continue

                                sz = safe_decimal(p.get("size"))
                                was_active = self.state.active

                                self.state.active = sz > 0
                                self.state.side = p.get("side") if sz > 0 else "HOLD"
                                self.state.qty = sz
                                self.state.entry_price = safe_decimal(p.get("avgPrice"))
                                self.state.upnl = safe_decimal(p.get("unrealisedPnl", "0"))

                                if not was_active and self.state.active:
                                    self.state.entry_ts = time.time() # From bch2.4.py
                                    self.state.position_open_ts = time.time() # From bchx.py
                                    self.state.log(f"Scalp Manifested: {self.state.side}", "bold green")
                                    self.state.be_active = False # Reset BE on new position

                                if was_active and not self.state.active:
                                    res_color = "bright_green" if self.state.upnl > 0 else "bright_red"
                                    self.state.log(f"Scalp Resolved. PnL: {self.state.upnl:+.4f}", res_color)
                                    if self.state.upnl > 0:
                                        self.state.wins += 1 # From bch2.0/bch2.3
                                        self.state.profitable_trades += 1 # From bchx/bchxx
                                    else:
                                        self.state.last_was_loss = True # From bchx/bchxx

                        elif topic == "wallet":
                            for acct in data.get("data", []):
                                for coin in acct.get("coin", []):
                                    if coin.get("coin") == "USDT":
                                        self.state.balance = safe_decimal(coin.get("walletBalance"))
                                        self.state.available = safe_decimal(coin.get("availableToWithdraw"))
                                        if self.state.initial_equity <= 0:
                                            self.state.initial_equity = self.state.equity
                                        self.state.daily_pnl = self.state.equity - self.state.initial_equity
                                        self.state.last_balance_update = time.time()

# =========================
# THE NEON SAGE DASHBOARD
# =========================

def build_ui(s: ScalperState) -> Layout:
    l = Layout()
    l.split_column(
        Layout(name="top", size=3),
        Layout(name="mid"),
        Layout(name="bot", size=10),
    )
    l["mid"].split_row(Layout(name="ora"), Layout(name="tac"))
    
    # --- Header ---
    wr = (s.profitable_trades / s.trade_count * 100) if s.trade_count > 0 else 0.0
    pnl_col = "bright_green" if s.daily_pnl >= 0 else "bright_red"
    
    lat = s.latency_ms
    lat_style = "bright_green" if lat < 300 else "yellow" if lat < s.config.max_latency_ms else "bold red"

    sp = spread_pct(s.bid, s.ask)
    sp_style = "bright_green" if sp <= s.config.max_spread_pct else "yellow" if sp <= s.config.max_spread_pct * 2 else "bold red"

    warm_text = f"Warm-Up: {s.warmup_progress}%" if s.warmup_progress < 100 else "READY ⚡"

    header_markup = (
        f"⚡ BCH APEX V10.0  •  "
        f"Equity: {Fore.YELLOW}{s.equity:.2f}{Style.RESET_ALL}  •  "
        f"PnL: [{pnl_col}]{s.daily_pnl:+.2f} USDT[/]  •  "
        f"Trades: {s.trade_count} (Win: {wr:.1f}%)  •  "
        f"{warm_text}  •  "
        f"Lat: [{lat_style}]{lat}ms[/]  •  "
        f"Spread: [{sp_style}]{sp:.3%}[/]")
    l["top"].update(Panel(Text.from_markup(header_markup, justify="center"), border_style="bright_blue"))

    # --- Oracle Panel ---
    ora = Table.grid(expand=True)
    ora.add_row("Price", f"[bold yellow]{s.price:.{s.price_prec}f}[/]") if s.price > 0 else "[dim]—[/dim]")
    ora.add_row("Singularity", f"[bold magenta]{s.alpha_singularity:.1f}%[/] [{'█' * int(s.alpha_singularity/5)}]")
    ora.add_row("OBI Score", f"[{'green' if s.obi_score > 0 else 'red'}]{s.obi_score:+.2%}[/]")
    ora.add_row("OBI Raw", f"[{'green' if s.obi_raw > 0 else 'red'}]{s.obi_raw:+.3f}[/]")
    ora.add_row("Fisher", f"{s.fisher:+.3f} [dim](Sig: {s.fisher_sig:+.3f}, Prev: {s.fisher_prev:+.3f})[/]")
    ora.add_row("Fisher Δ", f"[cyan]{(s.fisher - s.fisher_prev):+.3f}[/]")
    ora.add_row("ATR", f"[white]{s.atr:.2f}[/]")
    ora.add_row("VWAP", f"[cyan]{s.vwap:.{s.price_prec}f}[/]")
    ora.add_row("VSI (Surge)", f"{Fore.CYAN}{s.vsi:.2f}x{Style.RESET_ALL}")
    ora.add_row("Tick Velocity", f"[cyan]{s.tick_velocity:.1f} t/s[/]")
    ora.add_row("Trend (Micro)", f"{Fore.GREEN}BULL" if s.price > s.ema_micro else f"{Fore.RED}BEAR")
    ora.add_row("Trend (Macro)", f"{Fore.GREEN}BULL" if s.price > s.ema_macro else f"{Fore.RED}BEAR")
    l["ora"].update(Panel(ora, title="[bold cyan]Singularity Oracle[/]", border_style="cyan"))

    # --- Tactical Panel ---
    tac = Table.grid(expand=True)
    if s.active:
        side_style = "bright_green" if s.side == "Buy" else "bright_red"
        tac.add_row("State", f"[bold]{'IN POSITION'}[/bold]")
        tac.add_row("Side", f"[bold {side_style}]{s.side}[/]")
        tac.add_row("Qty", f"{s.qty}")
        tac.add_row("Entry", f"{s.entry_price:.{s.price_prec}f}")
        tac.add_row("uPnL", f"[{'bright_green' if s.upnl > 0 else 'bright_red'}]{s.upnl:+.4f}[/]")
        shield = "[bold green]ON[/]" if s.be_active else "[dim]OFF[/]"
        tac.add_row("BE Shield", shield)
        if s.position_open_ts:
            tac.add_row("Held", f"{int(time.time() - s.position_open_ts)}s / {s.config.max_hold_sec}s")
    else:
        tac.add_row("Status", "[green]SCANNING...[/]" if s.ready else "[yellow]WARMING...[/]")
        tac.add_row("Avail", f"{s.available:.2f} USDT")
        tac.add_row("Last Trade", f"{int(time.time() - s.last_trade_ts)}s ago" if s.last_trade_ts > 0 else "N/A")
        tac.add_row("Risk/trade", f"{s.config.risk_per_trade_usdt} USDT")
        tac.add_row("Leverage", f"{s.config.leverage}x")
    l["tac"].update(Panel(tac, title="[bold magenta]Tactical Nexus[/]", border_style="magenta"))

    # --- Footer (Logs) ---
    logs = "\n".join(list(s.logs)) if s.logs else "[dim]Awaiting conquest...[/dim]"
    l["bot"].update(Panel(Text.from_markup(logs), title="[dim]The Conquest Chronicles[/]", border_style="bright_black"))
    return l

async def main() -> None:
    if not API_KEY or not API_SECRET:
        console.print("[bold red]⚠️ BYBIT_API_KEY / BYBIT_API_SECRET missing[/bold red]")
        return

    config = ScalperConfig()
    config.validate()

    state = ScalperState(config=config)

    stop = asyncio.Event()

    async with BybitApex(state) as apex:
        # One-time setup
        await apex.set_leverage()
        await apex.refresh_instrument_filters()
        await apex.fetch_kline_history()
        await apex.refresh_wallet_once()

        # Live UI + tasks
        with Live(build_ui(state), refresh_per_second=8, screen=True) as live:
            tasks = [
                asyncio.create_task(apex.public_ws(stop), name="public_ws"),
                asyncio.create_task(apex.private_ws(stop), name="private_ws"),
                asyncio.create_task(apex.singularity_loop(stop), name="singularity_loop"),
                asyncio.create_task(ui_loop(live, state, stop), name="ui_loop"),
            ]

            try:
                await asyncio.gather(*tasks)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                state.log(f"[bold red]Fatal: {e}[/bold red]")
                stop.set()
            finally:
                stop.set()
                for t in tasks:
                    t.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

async def ui_loop(live: Live, state: ScalperState, stop: asyncio.Event) -> None:
    while not stop.is_set():
        live.update(build_ui(state), refresh=True)
        await asyncio.sleep(0.25)

if __name__ == "__main__":
    console = Console() # Initialize console for main function
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[bold magenta]⚡ Apex fades into the ether...[/bold magenta]")
