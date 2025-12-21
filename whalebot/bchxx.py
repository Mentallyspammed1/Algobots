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

# ---------- Decimal / numeric defaults ----------
getcontext().prec = 28

# ---------- Env ----------
load_dotenv()
API_KEY = os.getenv("BYBIT_API_KEY", "")
API_SECRET = os.getenv("BYBIT_API_SECRET", "")
IS_TESTNET = os.getenv("BYBIT_TESTNET", "false").lower() == "true"

console = Console()

@dataclass(slots=True)
class ScalperConfig:
    symbol: str = os.getenv("SCALPER_SYMBOL", "BCHUSDT")
    category: str = os.getenv("SCALPER_CATEGORY", "linear")
    leverage: int = int(os.getenv("SCALPER_LEVERAGE", "20"))

    # Execution guards
    max_latency_ms: int = int(os.getenv("SCALPER_MAX_LATENCY_MS", "350"))
    max_spread_pct: Decimal = Decimal(os.getenv("SCALPER_MAX_SPREAD_PCT", "0.0012"))
    max_hold_sec: int = int(os.getenv("SCALPER_MAX_HOLD_SEC", "180"))

    # Signals
    obi_threshold: float = float(os.getenv("SCALPER_OBI_THRESHOLD", "0.28"))
    fisher_momentum_threshold: float = float(os.getenv("SCALPER_FISHER_MOMENTUM", "0.18"))
    min_atr: float = float(os.getenv("SCALPER_MIN_ATR", "3.0"))

    # Risk
    risk_per_trade_usdt: Decimal = Decimal(os.getenv("SCALPER_RISK_USDT", "1.8"))
    tp_pct: Decimal = Decimal(os.getenv("SCALPER_TP_PCT", "0.013"))
    sl_pct: Decimal = Decimal(os.getenv("SCALPER_SL_PCT", "0.0075"))
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
        if not API_KEY or not API_SECRET: raise ValueError("API Keys missing in .env")
        if self.leverage <= 0: raise ValueError("leverage must be > 0")

@dataclass(slots=True)
class ScalperState:
    config: ScalperConfig
    # Wallet
    balance: Decimal = Decimal("0")
    available: Decimal = Decimal("0")
    initial_balance: Decimal = Decimal("0")
    daily_pnl: Decimal = Decimal("0")
    last_balance_update: float = 0.0

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

    # Stats
    trade_count: int = 0
    profitable_trades: int = 0
    active: bool = False
    side: str = "HOLD"
    qty: Decimal = Decimal("0")
    entry_price: Decimal = Decimal("0")
    upnl: Decimal = Decimal("0")
    position_open_ts: float = 0.0

    # Execution
    last_trade_ts: float = 0.0
    last_was_loss: bool = False
    ready: bool = False
    warmup_progress: int = 0

    # Filters
    price_prec: int = 2
    qty_step: Decimal = Decimal("0.01")
    min_qty: Decimal = Decimal("0.01")

    logs: deque[str] = field(default_factory=lambda: deque(maxlen=28))

    def log(self, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self.logs.append(f"[dim]{ts}[/] {msg}")

# =========================
# Utilities
# =========================
def safe_decimal(val: Any, default: str = "0") -> Decimal:
    if val is None or val == "": return Decimal(default)
    try: return Decimal(str(val))
    except: return Decimal(default)

def quantize_step(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0: return value
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step

# =========================
# Bybit Client
# =========================
class BybitFlux:
    def __init__(self, config: ScalperConfig, state: ScalperState):
        self.config = config
        self.state = state
        self.base = "https://api-testnet.bybit.com" if IS_TESTNET else "https://api.bybit.com"
        self.ws_pub = "wss://stream-testnet.bybit.com/v5/public/linear" if IS_TESTNET else "wss://stream.bybit.com/v5/public/linear"
        self.ws_priv = "wss://stream-testnet.bybit.com/v5/private" if IS_TESTNET else "wss://stream.bybit.com/v5/private"
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> BybitFlux:
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return self

    async def __aexit__(self, *args) -> None:
        if self.session: await self.session.close()

    def _sign(self, payload: str) -> dict[str, str]:
        ts = str(int(time.time() * 1000))
        recv = "5000"
        prehash = f"{ts}{API_KEY}{recv}{payload}"
        sig = hmac.new(API_SECRET.encode(), prehash.encode(), hashlib.sha256).hexdigest()
        return {"X-BAPI-API-KEY": API_KEY, "X-BAPI-SIGN": sig, "X-BAPI-TIMESTAMP": ts, "X-BAPI-RECV-WINDOW": recv}

    async def api_call(self, method: str, path: str, params: dict = None) -> dict:
        params = params or {}
        if method == "GET":
            query = urllib.parse.urlencode(sorted(params.items()))
            url = f"{self.base}{path}?{query}"
            headers = self._sign(query)
            body = None
        else:
            url = f"{self.base}{path}"
            body_str = json.dumps(params, separators=(",", ":"), sort_keys=True)
            headers = self._sign(body_str)
            headers["Content-Type"] = "application/json"
            body = body_str.encode()

        try:
            async with self.session.request(method, url, headers=headers, data=body) as r:
                return await r.json()
        except Exception as e:
            return {"retCode": -1, "retMsg": str(e)}

    async def refresh_balance(self) -> None:
        """Explicit REST fetch for balance to fix sync issues."""
        resp = await self.api_call("GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED"})
        if resp.get("retCode") == 0:
            for acct in resp["result"]["list"]:
                for coin in acct.get("coin", []):
                    if coin["coin"] == "USDT":
                        self.state.balance = safe_decimal(coin.get("walletBalance"))
                        # In V5, availableToWithdraw is the most reliable 'free' equity for trading
                        self.state.available = safe_decimal(coin.get("availableToWithdraw"))
                        if self.state.initial_balance <= 0: self.state.initial_balance = self.state.balance
                        self.state.last_balance_update = time.time()

    async def fetch_kline_history(self) -> None:
        resp = await self.api_call("GET", "/v5/market/kline", {
            "category": self.config.category, "symbol": self.config.symbol,
            "interval": self.config.kline_interval, "limit": self.config.kline_fetch_limit
        })
        if resp.get("retCode") == 0:
            for k in reversed(resp["result"]["list"]):
                self.state.ohlc.append((float(k[2]), float(k[3]), float(k[4]), float(k[5])))
            self.state.log("[cyan]History loaded.[/cyan]")

    async def scalp_market(self, side: str, qty: Decimal, reduce_only: bool = False) -> None:
        qty = quantize_step(qty, self.state.qty_step)
        if qty < self.state.min_qty: return

        params = {
            "category": self.config.category, "symbol": self.config.symbol,
            "side": side, "orderType": "Market", "qty": str(qty), "reduceOnly": reduce_only
        }
        resp = await self.api_call("POST", "/v5/order/create", params)
        if resp.get("retCode") == 0:
            self.state.log(f"[bold cyan]Order {side} {qty} Success[/bold cyan]")
            self.state.last_trade_ts = time.time()
            # Proactive balance refresh after trade
            await asyncio.sleep(0.5)
            await self.refresh_balance()
        else:
            self.state.log(f"[red]Order Failed: {resp.get('retMsg')}[/red]")

    async def public_ws(self, stop: asyncio.Event):
        async with self.session.ws_connect(self.ws_pub) as ws:
            await ws.send_json({"op": "subscribe", "args": [
                f"kline.{self.config.kline_interval}.{self.config.symbol}",
                f"tickers.{self.config.symbol}",
                f"orderbook.50.{self.config.symbol}"
            ]})
            async for msg in ws:
                if stop.is_set(): break
                data = json.loads(msg.data)
                topic = data.get("topic", "")

                if "kline" in topic and data.get("data"):
                    k = data["data"][0]
                    if k.get("confirm"):
                        self.state.ohlc.append((float(k["high"]), float(k["low"]), float(k["close"]), float(k["volume"])))
                        self._update_indicators()

                elif "tickers" in topic:
                    t = data["data"]
                    self.state.price = safe_decimal(t.get("lastPrice"))
                    self.state.bid = safe_decimal(t.get("bid1Price"))
                    self.state.ask = safe_decimal(t.get("ask1Price"))
                    self.state.last_ticker_ts = time.time()

                elif "orderbook" in topic:
                    ob = data["data"]
                    b_vol = sum(float(x[1]) for x in ob.get("b", [])[:20])
                    a_vol = sum(float(x[1]) for x in ob.get("a", [])[:20])
                    self.state.obi = (b_vol - a_vol) / (b_vol + a_vol + 1e-9)

    def _update_indicators(self):
        if len(self.state.ohlc) < 20: return
        closes = np.array([c[2] for c in self.state.ohlc])
        # Fisher
        win = closes[-10:]
        mn, mx = np.min(win), np.max(win) + 1e-10
        raw = 2 * ((closes[-1] - mn) / (mx - mn) - 0.5)
        raw = np.clip(raw, -0.999, 0.999)
        self.state.fisher_prev = self.state.fisher
        self.state.fisher = float(0.5 * np.log((1 + raw)/(1 - raw)) + 0.5 * self.state.fisher_prev)
        # ATR
        highs = np.array([c[0] for c in self.state.ohlc])
        lows = np.array([c[1] for c in self.state.ohlc])
        tr = np.maximum(highs[1:]-lows[1:], np.abs(highs[1:]-closes[:-1]))
        self.state.atr = float(np.mean(tr[-14:]))
        self.state.ready = len(self.state.ohlc) >= self.config.warmup_candles

    async def private_ws(self, stop: asyncio.Event):
        async with self.session.ws_connect(self.ws_priv) as ws:
            expires = int(time.time() * 1000) + 10000
            sig = hmac.new(API_SECRET.encode(), f"GET/realtime{expires}".encode(), hashlib.sha256).hexdigest()
            await ws.send_json({"op": "auth", "args": [API_KEY, expires, sig]})
            await ws.send_json({"op": "subscribe", "args": ["position", "wallet"]})

            async for msg in ws:
                if stop.is_set(): break
                data = json.loads(msg.data)
                topic = data.get("topic")

                if topic == "position":
                    for p in data.get("data", []):
                        if p["symbol"] == self.config.symbol:
                            self.state.qty = safe_decimal(p.get("size"))
                            self.state.active = self.state.qty > 0
                            self.state.side = p.get("side", "HOLD") if self.state.active else "HOLD"
                            self.state.entry_price = safe_decimal(p.get("avgPrice"))
                            self.state.upnl = safe_decimal(p.get("unrealisedPnl"))

                elif topic == "wallet":
                    for acct in data.get("data", []):
                        for coin in acct.get("coin", []):
                            if coin["coin"] == "USDT":
                                self.state.balance = safe_decimal(coin.get("walletBalance"))
                                self.state.available = safe_decimal(coin.get("availableToWithdraw"))
                                self.state.last_balance_update = time.time()

# =========================
# Brain & Loop
# =========================
async def strategy_brain(flux: BybitFlux, stop: asyncio.Event):
    s, c = flux.state, flux.config
    while not stop.is_set():
        await asyncio.sleep(0.5)

        # Balance watchdog: If WS is silent > 30s, force REST refresh
        if time.time() - s.last_balance_update > 30:
            await flux.refresh_balance()

        if not s.ready or s.price <= 0: continue

        # Exit Logic
        if s.active:
            # TP/SL based on notional
            notional = s.entry_price * s.qty
            pnl_pct = s.upnl / (notional / c.leverage) if notional > 0 else 0

            if pnl_pct > c.tp_pct or pnl_pct < -c.sl_pct:
                await flux.scalp_market("Sell" if s.side == "Buy" else "Buy", s.qty, True)
            continue

        # Entry Logic
        if (time.time() - s.last_trade_ts) < c.cooldown_sec: continue

        f_delta = s.fisher - s.fisher_prev
        if s.obi > c.obi_threshold and f_delta > c.fisher_momentum_threshold:
            # Sizing: Risk Amount * Leverage / Price
            qty = (c.risk_per_trade_usdt * c.leverage) / s.price
            await flux.scalp_market("Buy", qty)
        elif s.obi < -c.obi_threshold and f_delta < -c.fisher_momentum_threshold:
            qty = (c.risk_per_trade_usdt * c.leverage) / s.price
            await flux.scalp_market("Sell", qty)

# =========================
# UI & Main
# =========================
def render_ui(s: ScalperState) -> Layout:
    l = Layout()
    l.split_column(Layout(name="h", size=3), Layout(name="m"), Layout(name="f", size=10))

    # Header
    status = "[bold green]READY[/]" if s.ready else f"[yellow]WARMING {len(s.ohlc)}[/]"
    l["h"].update(Panel(f"BCH PRIME | PnL: {s.daily_pnl:+.2f} | Bal: {s.balance:.2f} | Avail: {s.available:.2f} | {status}", border_style="cyan"))

    # Body
    t = Table.grid(expand=True)
    t.add_row(f"Price: {s.price}", f"OBI: {s.obi:+.3f}")
    t.add_row(f"Fisher: {s.fisher:+.3f}", f"ATR: {s.atr:.2f}")
    t.add_row(f"Pos: {s.side} {s.qty}", f"uPnL: {s.upnl:+.2f}")
    l["m"].update(Panel(t, title="Market Data"))

    # Logs
    l["f"].update(Panel("\n".join(list(s.logs)[-8:]), title="Logs"))
    return l

async def main():
    cfg = ScalperConfig()
    cfg.validate()
    state = ScalperState(cfg)
    stop = asyncio.Event()

    async with BybitFlux(cfg, state) as flux:
        await flux.refresh_balance()
        await flux.fetch_kline_history()

        with Live(render_ui(state), refresh_per_second=4, screen=True) as live:
            tasks = [
                asyncio.create_task(flux.public_ws(stop)),
                asyncio.create_task(flux.private_ws(stop)),
                asyncio.create_task(strategy_brain(flux, stop)),
            ]

            while not stop.is_set():
                live.update(render_ui(state))
                await asyncio.sleep(0.25)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
