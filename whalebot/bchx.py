"""
BCH SCALPER PRIME — upgraded & hardened

Key upgrades vs your original:
- Safer config/state (dataclasses, validation, Decimal helpers, step-quantize that won’t explode)
- Robust REST layer (timeouts, retries w/ backoff, canonical signing payloads)
- WebSocket resilience (heartbeat, exponential reconnect, better parsing, stale-data guards)
- Safer execution (reduceOnly exits, spread/latency guards, max-hold safety)
- UI fixes (Rich markup was being treated as literal text; now renders correctly + warmup bar)
- Graceful shutdown (single stop_event, proper task cancellation)
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import time
import urllib.parse
from collections import deque
from dataclasses import dataclass
from dataclasses import field
from decimal import ROUND_DOWN
from decimal import Decimal
from decimal import getcontext
from typing import Any

import aiohttp
import numpy as np
from dotenv import load_dotenv
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# ---------- Decimal / numeric defaults ----------
getcontext().prec = 28

# ---------- Env ----------
load_dotenv()
API_KEY = os.getenv("BYBIT_API_KEY", "") or ""
API_SECRET = os.getenv("BYBIT_API_SECRET", "") or ""
IS_TESTNET = os.getenv("BYBIT_TESTNET", "false").lower() == "true"

console = Console()


# =========================
# Config + State
# =========================

@dataclass(slots=True)
class ScalperConfig:
    # Market
    symbol: str = os.getenv("SCALPER_SYMBOL", "BCHUSDT")
    category: str = os.getenv("SCALPER_CATEGORY", "linear")  # v5: linear/inverse/spot/option
    leverage: int = int(os.getenv("SCALPER_LEVERAGE", "20"))

    # Execution guards
    max_latency_ms: int = int(os.getenv("SCALPER_MAX_LATENCY_MS", "350"))
    max_spread_pct: Decimal = Decimal(os.getenv("SCALPER_MAX_SPREAD_PCT", "0.0012"))  # 0.12%
    max_hold_sec: int = int(os.getenv("SCALPER_MAX_HOLD_SEC", "180"))  # safety exit

    # Signals
    obi_threshold: float = float(os.getenv("SCALPER_OBI_THRESHOLD", "0.28"))
    fisher_momentum_threshold: float = float(os.getenv("SCALPER_FISHER_MOMENTUM", "0.18"))
    min_atr: float = float(os.getenv("SCALPER_MIN_ATR", "3.0"))

    # Risk
    risk_per_trade_usdt: Decimal = Decimal(os.getenv("SCALPER_RISK_USDT", "1.8"))
    tp_pct: Decimal = Decimal(os.getenv("SCALPER_TP_PCT", "0.013"))     # profit on margin used (approx)
    sl_pct: Decimal = Decimal(os.getenv("SCALPER_SL_PCT", "0.0075"))    # loss on margin used (approx)
    cooldown_sec: int = int(os.getenv("SCALPER_COOLDOWN_SEC", "15"))
    loss_cooldown_multiplier: int = int(os.getenv("SCALPER_LOSS_COOLDOWN_MULT", "3"))

    # Warmup
    warmup_candles: int = int(os.getenv("SCALPER_WARMUP_CANDLES", "60"))
    kline_interval: str = os.getenv("SCALPER_KLINE_INTERVAL", "1")
    kline_fetch_limit: int = int(os.getenv("SCALPER_KLINE_FETCH_LIMIT", "200"))

    # WS
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

    # Wallet / stats
    balance: Decimal = Decimal("0")
    available: Decimal = Decimal("0")
    initial_balance: Decimal = Decimal("0")
    daily_pnl: Decimal = Decimal("0")
    trade_count: int = 0
    profitable_trades: int = 0

    # Market
    price: Decimal = Decimal("0")
    bid: Decimal = Decimal("0")
    ask: Decimal = Decimal("0")
    obi: float = 0.0
    vwap: Decimal = Decimal("0")
    ohlc: deque[tuple[float, float, float, float]] = field(default_factory=lambda: deque(maxlen=400))
    atr: float = 0.0
    fisher: float = 0.0
    fisher_prev: float = 0.0

    latency_ms: int = 0
    last_ticker_ts: float = 0.0

    # Position
    active: bool = False
    side: str = "HOLD"  # Buy/Sell/HOLD
    qty: Decimal = Decimal("0")
    entry_price: Decimal = Decimal("0")
    upnl: Decimal = Decimal("0")
    position_open_ts: float = 0.0

    # Execution state
    last_trade_ts: float = 0.0
    last_was_loss: bool = False
    ready: bool = False
    warmup_progress: int = 0

    # Instrument filters
    price_prec: int = 2
    qty_step: Decimal = Decimal("0.01")
    min_qty: Decimal = Decimal("0.01")

    # UI logs
    logs: deque[str] = field(default_factory=lambda: deque(maxlen=28))

    def log(self, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self.logs.append(f"[dim]{ts}[/] {msg}")


# =========================
# Helpers
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
    """
    Safer than Decimal.quantize(step) for arbitrary step sizes.
    Floors to the nearest multiple of `step`.
    """
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


# =========================
# Indicators / Warmup
# =========================

def update_oracle(state: ScalperState) -> None:
    n = len(state.ohlc)
    warm_target = max(20, state.config.warmup_candles)

    # Warmup progress is simple, predictable
    state.warmup_progress = int(clamp01(n / warm_target) * 100)

    if n < 15:
        return

    highs = np.array([c[0] for c in state.ohlc], dtype=np.float64)
    lows = np.array([c[1] for c in state.ohlc], dtype=np.float64)
    closes = np.array([c[2] for c in state.ohlc], dtype=np.float64)
    volumes = np.array([c[3] for c in state.ohlc], dtype=np.float64)

    # Fisher transform (smoothed)
    window = closes[-10:]
    mn = float(np.min(window))
    mx = float(np.max(window)) + 1e-12
    raw = 2 * ((float(closes[-1]) - mn) / (mx - mn) - 0.5)
    raw = float(np.clip(raw, -0.999, 0.999))
    state.fisher_prev = state.fisher
    fish = 0.5 * np.log((1 + raw) / (1 - raw + 1e-12))
    state.fisher = float(0.5 * fish + 0.5 * state.fisher_prev)

    # ATR(14) simple mean of TR
    tr = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])),
    )
    if tr.size >= 14:
        state.atr = float(np.mean(tr[-14:]))

    # VWAP over last 20 candles
    if n >= 20:
        typ = (highs[-20:] + lows[-20:] + closes[-20:]) / 3.0
        vol = volumes[-20:]
        vol_sum = float(np.sum(vol)) or 1.0
        vwap_val = float(np.sum(typ * vol) / vol_sum)
        state.vwap = safe_decimal(vwap_val)

    # Ready gate
    if n >= warm_target and state.atr >= state.config.min_atr:
        state.ready = True
        state.warmup_progress = 100


# =========================
# Bybit client (REST + WS)
# =========================

class BybitFlux:
    def __init__(self, config: ScalperConfig, state: ScalperState):
        self.config = config
        self.state = state

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

        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> BybitFlux:
        timeout = aiohttp.ClientTimeout(total=10, connect=4, sock_read=8)
        connector = aiohttp.TCPConnector(limit=50, enable_cleanup_closed=True, ttl_dns_cache=300)
        self.session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self.session:
            await self.session.close()

    # ---- Signing ----
    @staticmethod
    def _canonical_query(params: dict[str, Any]) -> str:
        # Stable ordering prevents signature mismatch across Python versions / dict ordering edge cases.
        items = []
        for k in sorted(params.keys()):
            v = params[k]
            if v is None:
                continue
            items.append((k, str(v)))
        return urllib.parse.urlencode(items)

    @staticmethod
    def _canonical_json(params: dict[str, Any]) -> str:
        # Stable JSON string; Bybit expects the exact payload string used in the signature.
        return json.dumps(params, separators=(",", ":"), sort_keys=True)

    def _sign_headers(self, payload: str) -> dict[str, str]:
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

    # ---- REST with retry ----
    async def api_call(self, method: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
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

        # retry transient network errors
        backoff = 0.35
        for attempt in range(5):
            try:
                async with self.session.request(method.upper(), url, headers=headers, data=body) as resp:
                    data = await resp.json(content_type=None)

                    # Bybit-style errors still return 200; retCode != 0 is the signal.
                    # For rate limits / transient issues, backoff a bit.
                    ret = int(data.get("retCode", -1))
                    if ret == 0:
                        return data

                    msg = data.get("retMsg", "Unknown error")
                    if ret in (10006, 10018):  # common rate-limit / too frequent codes
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 1.8, 3.0)
                        continue

                    return data

            except (aiohttp.ClientError, asyncio.TimeoutError):
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.8, 3.0)

        return {"retCode": -1, "retMsg": "REST retries exhausted"}

    # ---- Convenience ----
    async def fetch_kline_history(self) -> None:
        params = {
            "category": self.config.category,
            "symbol": self.config.symbol,
            "interval": self.config.kline_interval,
            "limit": self.config.kline_fetch_limit,
        }
        resp = await self.api_call("GET", "/v5/market/kline", params)
        if resp.get("retCode") != 0:
            self.state.log(f"[red]Failed kline history: {resp.get('retMsg')}[/red]")
            return

        # v5 list entries: [startTime, open, high, low, close, volume, turnover]
        for k in reversed(resp["result"]["list"]):
            self.state.ohlc.append((float(k[2]), float(k[3]), float(k[4]), float(k[5])))
        update_oracle(self.state)
        self.state.log("[cyan]Historical candles loaded — oracle warming[/cyan]")

    async def refresh_instrument_filters(self) -> None:
        resp = await self.api_call(
            "GET",
            "/v5/market/instruments-info",
            {"category": self.config.category, "symbol": self.config.symbol},
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
                    if self.state.initial_balance <= 0:
                        self.state.initial_balance = self.state.balance
                    self.state.daily_pnl = self.state.balance - self.state.initial_balance

    async def set_leverage(self) -> None:
        resp = await self.api_call(
            "POST",
            "/v5/position/set-leverage",
            {
                "category": self.config.category,
                "symbol": self.config.symbol,
                "buyLeverage": str(self.config.leverage),
                "sellLeverage": str(self.config.leverage),
            },
        )
        if resp.get("retCode") == 0:
            self.state.log(f"[green]Leverage set to {self.config.leverage}x[/green]")
        else:
            self.state.log(f"[yellow]Leverage set failed: {resp.get('retMsg')}[/yellow]")

    # ---- Execution ----
    async def scalp_market(self, side: str, qty: Decimal, *, reduce_only: bool = False) -> None:
        s = self.state
        c = self.config

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
            "side": side,           # Buy / Sell
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
        else:
            s.log(f"[bold red]Order failed: {resp.get('retMsg')}[/bold red]")

    # ---- WS loops ----
    async def public_ws(self, stop: asyncio.Event) -> None:
        assert self.session is not None
        backoff = 0.5

        while not stop.is_set():
            try:
                async with self.session.ws_connect(
                    self.ws_pub,
                    heartbeat=self.config.ws_heartbeat_sec,
                    receive_timeout=self.config.ws_heartbeat_sec * 2,
                    max_msg_size=10_000_000,
                ) as ws:
                    backoff = 0.5
                    await ws.send_json(
                        {
                            "op": "subscribe",
                            "args": [
                                f"kline.{self.config.kline_interval}.{self.config.symbol}",
                                f"tickers.{self.config.symbol}",
                                f"orderbook.50.{self.config.symbol}",
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

                        # Kline: use only confirmed candle close
                        if topic.startswith("kline.") and data.get("data"):
                            k = data["data"][0]
                            if k.get("confirm"):
                                self.state.ohlc.append(
                                    (float(k["high"]), float(k["low"]), float(k["close"]), float(k["volume"]))
                                )
                                update_oracle(self.state)

                        # Orderbook imbalance
                        elif topic.startswith("orderbook."):
                            ob = data.get("data", {})
                            bids = sum(float(x[1]) for x in (ob.get("b") or [])[:30])
                            asks = sum(float(x[1]) for x in (ob.get("a") or [])[:30])
                            tot = bids + asks or 1.0
                            self.state.obi = (bids - asks) / tot

                        # Tickers
                        elif topic.startswith("tickers."):
                            t = data.get("data", {})
                            # sometimes it’s a list; normalize
                            if isinstance(t, list) and t:
                                t = t[0]

                            self.state.price = safe_decimal(t.get("lastPrice"))
                            self.state.bid = safe_decimal(t.get("bid1Price"))
                            self.state.ask = safe_decimal(t.get("ask1Price"))
                            self.state.last_ticker_ts = time.time()

                            # latency estimate: server ts vs local
                            ts = t.get("ts")
                            if ts is not None:
                                try:
                                    self.state.latency_ms = int(time.time() * 1000) - int(ts)
                                except Exception:
                                    pass

            except Exception:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.8, 5.0)

    async def private_ws(self, stop: asyncio.Event) -> None:
        assert self.session is not None
        backoff = 0.7

        while not stop.is_set():
            try:
                async with self.session.ws_connect(
                    self.ws_priv,
                    heartbeat=self.config.ws_heartbeat_sec,
                    receive_timeout=self.config.ws_heartbeat_sec * 2,
                    max_msg_size=10_000_000,
                ) as ws:
                    backoff = 0.7

                    # Auth (kept compatible with your original approach)
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

                        # Position updates
                        if topic == "position":
                            for p in data.get("data", []):
                                if p.get("symbol") != self.config.symbol:
                                    continue

                                sz = safe_decimal(p.get("size"))
                                was_active = self.state.active

                                self.state.active = sz > 0
                                self.state.side = p.get("side") if sz > 0 else "HOLD"
                                self.state.qty = sz
                                self.state.entry_price = safe_decimal(p.get("avgPrice"))
                                self.state.upnl = safe_decimal(p.get("unrealisedPnl", "0"))

                                # Track open timestamp for max-hold safety
                                if not was_active and self.state.active:
                                    self.state.position_open_ts = time.time()

                                if was_active and not self.state.active:
                                    if self.state.upnl > 0:
                                        self.state.profitable_trades += 1
                                        self.state.log("[bold green]🎯 Profit scalped[/bold green]")
                                    else:
                                        self.state.log("[bold red]🛑 Loss taken[/bold red]")
                                        self.state.last_was_loss = True

                        # Wallet updates
                        elif topic == "wallet":
                            for acct in data.get("data", []):
                                for coin in acct.get("coin", []):
                                    if coin.get("coin") == "USDT":
                                        self.state.balance = safe_decimal(coin.get("walletBalance"))
                                        self.state.available = safe_decimal(coin.get("availableToWithdraw"))
                                        if self.state.initial_balance <= 0:
                                            self.state.initial_balance = self.state.balance
                                        self.state.daily_pnl = self.state.balance - self.state.initial_balance

            except Exception:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.8, 6.0)


# =========================
# Strategy loop
# =========================

async def scalp_brain(flux: BybitFlux, stop: asyncio.Event) -> None:
    s = flux.state
    c = flux.config

    while not stop.is_set():
        await asyncio.sleep(0.30)

        # Stale ticker guard (avoids trading on dead feed)
        if s.last_ticker_ts and (time.time() - s.last_ticker_ts) > c.ws_stale_ticker_sec:
            continue

        if not s.ready or s.atr < c.min_atr or s.price <= 0:
            continue

        # Cooldown after trades; longer cooldown after a loss
        cooldown = c.cooldown_sec * (c.loss_cooldown_multiplier if s.last_was_loss else 1)
        if (time.time() - s.last_trade_ts) < cooldown:
            continue
        s.last_was_loss = False

        # Capital guard
        if s.available < (c.risk_per_trade_usdt * Decimal("1.5")):
            if int(time.time()) % 6 == 0:
                s.log("[dim]Available low — waiting[/dim]")
            continue

        # Position management
        if s.active:
            # Safety: max hold time
            if s.position_open_ts and (time.time() - s.position_open_ts) > c.max_hold_sec:
                await flux.scalp_market("Sell" if s.side == "Buy" else "Buy", s.qty, reduce_only=True)
                s.log("[yellow]⏱ Max-hold exit[/yellow]")
                continue

            # PnL% approximation using margin used (notional/leverage)
            margin_used = (s.entry_price * s.qty) / Decimal(str(c.leverage)) if s.qty > 0 else Decimal("0")
            pnl_pct = (abs(s.upnl) / margin_used) if margin_used > 0 else Decimal("0")

            if pnl_pct >= c.tp_pct:
                await flux.scalp_market("Sell" if s.side == "Buy" else "Buy", s.qty, reduce_only=True)
                continue

            if pnl_pct >= c.sl_pct:
                await flux.scalp_market("Sell" if s.side == "Buy" else "Buy", s.qty, reduce_only=True)
                continue

            # Reversal exit
            reversal = (
                (s.side == "Buy" and s.fisher < s.fisher_prev - c.fisher_momentum_threshold)
                or (s.side == "Sell" and s.fisher > s.fisher_prev + c.fisher_momentum_threshold)
            )
            if reversal:
                await flux.scalp_market("Sell" if s.side == "Buy" else "Buy", s.qty, reduce_only=True)
                s.log("[yellow]🔄 Reversal exit[/yellow]")

            continue

        # Entry logic
        fisher_delta = s.fisher - s.fisher_prev
        long_sig = (s.obi > c.obi_threshold) and (fisher_delta > c.fisher_momentum_threshold) and (s.price > s.vwap)
        short_sig = (s.obi < -c.obi_threshold) and (fisher_delta < -c.fisher_momentum_threshold) and (s.price < s.vwap)

        # Risk-based sizing:
        # qty ~= (risk * leverage) / (price * sl_pct)
        # (Keeps loss near risk_per_trade when stop triggers, roughly.)
        denom = (s.price * c.sl_pct)
        if denom <= 0:
            continue
        qty_raw = (c.risk_per_trade_usdt * Decimal(str(c.leverage))) / denom
        qty = quantize_step(qty_raw, s.qty_step)
        if qty < s.min_qty:
            continue

        if long_sig:
            await flux.scalp_market("Buy", qty, reduce_only=False)
        elif short_sig:
            await flux.scalp_market("Sell", qty, reduce_only=False)


# =========================
# UI
# =========================

def build_ui(state: ScalperState) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main"),
        Layout(name="footer", size=18),
    )
    layout["main"].split_row(Layout(name="oracle"), Layout(name="tactical"))

    win_rate = (state.profitable_trades / state.trade_count * 100) if state.trade_count else 0.0
    pnl_style = "bold bright_green" if state.daily_pnl >= 0 else "bold bright_red"

    lat = state.latency_ms
    lat_style = "bright_green" if lat < 300 else "yellow" if lat < state.config.max_latency_ms else "bold red"

    sp = spread_pct(state.bid, state.ask)
    sp_style = "bright_green" if sp <= state.config.max_spread_pct else "yellow" if sp <= state.config.max_spread_pct * 2 else "bold red"

    warm_text = f"Warm-Up: {state.warmup_progress}%" if state.warmup_progress < 100 else "READY ⚡"

    header_markup = (
        f"⚡ BCH SCALPER PRIME v4  •  "
        f"PnL: [{pnl_style}]{state.daily_pnl:+.2f} USDT[/]  •  "
        f"Trades: {state.trade_count} (Win: {win_rate:.1f}%)  •  "
        f"{warm_text}  •  "
        f"Lat: [{lat_style}]{lat}ms[/]  •  "
        f"Spread: [{sp_style}]{sp:.3%}[/]"
    )
    layout["header"].update(
        Panel(Text.from_markup(header_markup, justify="center"), border_style="bright_magenta")
    )

    # Oracle panel
    oracle = Table.grid(expand=True)
    oracle.add_row("Price", f"[bold white]{state.price:.{state.price_prec}f}[/]" if state.price > 0 else "[dim]—[/dim]")
    oracle.add_row("Bid / Ask", f"[green]{state.bid}[/] / [red]{state.ask}[/]")
    oracle.add_row("VWAP", f"[cyan]{state.vwap}[/]")
    oracle.add_row("OBI", f"[yellow]{state.obi:+.3f}[/]")
    oracle.add_row("Fisher Δ", f"[cyan]{(state.fisher - state.fisher_prev):+.3f}[/]")
    oracle.add_row("ATR", f"[white]{state.atr:.2f}[/]")
    oracle.add_row("Ready", "[bold green]YES[/bold green]" if state.ready else "[yellow]NO[/yellow]")
    layout["oracle"].update(Panel(oracle, title="🔮 Micro Oracle", border_style="bright_cyan"))

    # Tactical panel
    tactical = Table.grid(expand=True)
    if state.active:
        side_style = "bright_green" if state.side == "Buy" else "bright_red"
        tactical.add_row("State", f"[bold]{'IN POSITION'}[/bold]")
        tactical.add_row("Side", f"[bold {side_style}]{state.side}[/]")
        tactical.add_row("Qty", f"{state.qty}")
        tactical.add_row("Entry", f"{state.entry_price}")
        tactical.add_row("uPnL", f"[{'bright_green' if state.upnl > 0 else 'bright_red'}]{state.upnl:+.2f} USDT[/]")
        if state.position_open_ts:
            tactical.add_row("Held", f"{int(time.time() - state.position_open_ts)}s / {state.config.max_hold_sec}s")
    else:
        tactical.add_row("State", "[bold magenta]Hunting edges...[/bold magenta]")
        tactical.add_row("Balance", f"{state.balance:.2f} USDT")
        tactical.add_row("Available", f"{state.available:.2f} USDT")
        tactical.add_row("Risk/trade", f"{state.config.risk_per_trade_usdt} USDT")
        tactical.add_row("Leverage", f"{state.config.leverage}x")

    layout["tactical"].update(Panel(tactical, title="⚡ Scalp Realm", border_style="bright_magenta"))

    logs = "\n".join(state.logs) if state.logs else "[dim]Awaiting conquest...[/dim]"
    layout["footer"].update(Panel(Text.from_markup(logs), title="📜 Conquest Chronicles", border_style="bright_black"))

    return layout


async def ui_loop(live: Live, state: ScalperState, stop: asyncio.Event) -> None:
    while not stop.is_set():
        live.update(build_ui(state), refresh=True)
        await asyncio.sleep(0.25)


# =========================
# Main
# =========================

async def main() -> None:
    if not API_KEY or not API_SECRET:
        console.print("[bold red]⚠️ BYBIT_API_KEY / BYBIT_API_SECRET missing[/bold red]")
        return

    config = ScalperConfig()
    config.validate()

    state = ScalperState(config=config)

    stop = asyncio.Event()

    async with BybitFlux(config, state) as flux:
        # One-time setup
        await flux.set_leverage()
        await flux.refresh_instrument_filters()
        await flux.fetch_kline_history()
        await flux.refresh_wallet_once()

        # Live UI + tasks
        with Live(build_ui(state), refresh_per_second=8, screen=True) as live:
            tasks = [
                asyncio.create_task(flux.public_ws(stop), name="public_ws"),
                asyncio.create_task(flux.private_ws(stop), name="private_ws"),
                asyncio.create_task(scalp_brain(flux, stop), name="scalp_brain"),
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


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[bold magenta]⚡ Scalper Prime rests. Edges eternal.[/bold magenta]")
