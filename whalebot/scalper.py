#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BCH Sentinel v4.5 - THE SCALPER
Forged by Pyrmethus: Optimized for high-frequency scalping with dynamic thresholds,
ATR-based risk, and advanced trade management.
"""

import os
import asyncio
import hmac
import hashlib
import json
import time
import urllib.parse
import numpy as np
from collections import deque
from decimal import Decimal, ROUND_DOWN
from typing import Optional, Dict, Any, List, Tuple

import aiohttp
import websockets
from pybit.unified_trading import WebSocket
from dotenv import load_dotenv
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.live import Live
from rich.table import Table
from rich.text import Text

from dataclasses import dataclass

# --- Load the Arcane Sigils ---
load_dotenv()
API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')
IS_TESTNET = os.getenv('BYBIT_TESTNET', 'false').lower() == 'true'

@dataclass
class StrategyConfig:
    symbol: str = "BCHUSDT"
    category: str = "linear"
    leverage: int = 10
    base_risk_percent: Decimal = Decimal("1.5")
    daily_loss_limit: Decimal = Decimal("5.0")
    
    scalping_cooldown_seconds: int = 30
    scalping_dynamic_threshold: float = 0.8
    scalping_trend_strength_min: float = 0.3
    scalping_sl_mult: Decimal = Decimal("1.2")
    scalping_tp_mult: Decimal = Decimal("1.5")

    fisher_period: int = 10
    atr_period: int = 14
    macro_period: int = 50
    long_term_ema_period: int = 200

# Global Constants (will be replaced by config)
# SYMBOL = "BCHUSDT"
# CATEGORY = "linear"
# LEVERAGE = 10
# BASE_RISK_PERCENT = Decimal("1.5")
# DAILY_LOSS_LIMIT = Decimal("5.0") 

# Scalping-specific adjustments (from ehl.py)
# SCALPING_COOLDOWN_SECONDS = 30
# SCALPING_DYNAMIC_THRESHOLD = 0.8
# SCALPING_TREND_STRENGTH_MIN = 0.3
# SCALPING_SL_MULT = Decimal("1.2")
# SCALPING_TP_MULT = Decimal("1.5")

# Indicator Periods
# FISHER_PERIOD = 10
# ATR_PERIOD = 14
# MACRO_PERIOD = 50
# LONG_TERM_EMA_PERIOD = 200

class SentinelState:
    def __init__(self, config: StrategyConfig):
        # Equity & Risk Management
        self.balance = Decimal("0.0")
        self.initial_balance = Decimal("0.0")
        self.high_water_mark_equity = Decimal("0.0")
        self.daily_pnl = Decimal("0.0")
        self.cooldown_seconds = config.scalping_cooldown_seconds
        
        # Market Data
        self.price = Decimal("0.0")
        self.ohlc = deque(maxlen=config.long_term_ema_period) # Maxlen based on longest indicator period
        
        # Oracle Indicators
        self.fisher = 0.0
        self.fisher_series = deque(maxlen=5) # Still fixed for Fisher calculation
        self.atr = 0.0
        self.macro_trend = 0.0
        self.trend_strength = 0.0
        self.velocity = 0.0 
        self.dynamic_threshold = config.scalping_dynamic_threshold
        self.long_term_ema = Decimal("0.0")
        self.vwap = Decimal("0.0")
        
        # Position Logic
        self.trade_active = False
        self.side = "HOLD"
        self.entry_price = Decimal("0.0")
        self.qty = Decimal("0.0")
        self.upnl = Decimal("0.0")
        self.last_ritual = 0
        self.initial_sl_distance = Decimal("0.0")
        self.partial_tp_claimed = False
        self.high_water_mark = Decimal("0.0")
        self.trailing_stop_offset = Decimal("0.0")
        
        # Precision
        self.price_prec = 2
        self.qty_step = Decimal("0.01")
        
        self.logs = deque(maxlen=10)
        self.is_ready = False

# state = SentinelState() # This will be instantiated in main now

# --- Alchemy: Indicators (from ehl.py) ---

def super_smoother(data: List[float], period: int) -> float:
    if len(data) < 3: return data[-1] if data else 0.0
    if any(np.isnan(x) for x in data[-3:]):
        return data[-1] if data else 0.0
    a = np.exp(-1.414 * np.pi / period)
    b = 2 * a * np.cos(1.414 * np.pi / period)
    c2, c3 = b, -a * a
    c1 = 1 - c2 - c3
    return c1 * (data[-1] + data[-2]) / 2 + c2 * data[-2] + c3 * data[-3]

def _calculate_atr(state: SentinelState, closes: List[float], highs: List[float], lows: List[float], config: StrategyConfig):
    if len(closes) < config.atr_period: return
    tr = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])) for i in range(1, len(state.ohlc))]
    state.atr = float(np.mean(tr[-config.atr_period:])) if tr else 0.0

def _calculate_macro_trend(state: SentinelState, closes: List[float], config: StrategyConfig):
    if len(closes) < config.macro_period: return
    state.macro_trend = Decimal(str(super_smoother(closes, config.macro_period)))

def _calculate_fisher_transform(state: SentinelState, closes: List[float], config: StrategyConfig):
    if len(closes) < config.fisher_period: return
    window = closes[-config.fisher_period:]
    hh, ll = max(window), min(window)
    if (hh - ll) == 0:
        raw = 0.0
    else:
        raw = 2 * ((closes[-1] - ll) / (hh - ll) - 0.5)
    raw = np.clip(raw, -0.999, 0.999)
    
    fish = 0.5 * np.log((1 + raw) / (1 - raw)) + 0.5 * (state.fisher_series[-1] if state.fisher_series else 0.0)
    state.fisher = fish
    state.fisher_series.append(fish)

def _calculate_momentum_velocity(state: SentinelState, closes: List[float], config: StrategyConfig):
    if len(closes) < 5: return
    if state.atr > 0:
        state.velocity = (closes[-1] - closes[-5]) / state.atr
    else:
        state.velocity = 0.0

def _calculate_long_term_ema(state: SentinelState, closes: List[float], config: StrategyConfig):
    if len(closes) < config.long_term_ema_period: return
    state.long_term_ema = Decimal(str(super_smoother(closes, config.long_term_ema_period)))

def _calculate_vwap(state: SentinelState):
    if len(state.ohlc) == 0: return
    pv_sum = Decimal("0.0")
    v_sum = Decimal("0.0")
    for high, low, close, volume in state.ohlc:
        typical_price = (Decimal(str(high)) + Decimal(str(low)) + Decimal(str(close))) / Decimal("3.0")
        pv_sum += typical_price * Decimal(str(volume))
        v_sum += Decimal(str(volume))
    
    if v_sum > 0:
        state.vwap = pv_sum / v_sum
    else:
        state.vwap = state.price

def update_oracle(state: SentinelState, config: StrategyConfig):
    if len(state.ohlc) < config.macro_period:
        state.logs.append(f"[bold yellow]Insufficient OHLC data for indicators: {len(state.ohlc)}/{config.macro_period}[/bold yellow]")
        return
    
    clean_ohlc = [candle for candle in state.ohlc if not any(np.isnan(x) for x in candle)]
    
    if len(clean_ohlc) < config.macro_period: return
    
    closes = [x[2] for x in clean_ohlc]
    highs = [x[0] for x in clean_ohlc]
    lows = [x[1] for x in clean_ohlc]
    
    _calculate_atr(state, closes, highs, lows, config)
    _calculate_macro_trend(state, closes, config)
    state.trend_strength = abs(float(state.price) - float(state.macro_trend)) / (state.atr if state.atr > 0 else 1.0)
    _calculate_fisher_transform(state, closes, config)
    _calculate_momentum_velocity(state, closes, config)
    _calculate_long_term_ema(state, closes, config)
    _calculate_vwap(state)

# --- The Forge: API Client (from ehl.py) ---

class BybitForge:
    def __init__(self, state: SentinelState):
        self.session = None
        self.base = "https://api-testnet.bybit.com" if IS_TESTNET else "https://api.bybit.com"
        self.state = state

    async def ignite(self):
        if not self.session: self.session = aiohttp.ClientSession()

    async def __aenter__(self):
        await self.ignite()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session: await self.session.close()

    def _sign(self, ts: str, payload: str) -> str:
        return hmac.new(API_SECRET.encode(), (ts + API_KEY + "5000" + payload).encode(), hashlib.sha256).hexdigest()

    async def call(self, method: str, path: str, params: dict = None, signed: bool = False, retries: int = 3, delay: int = 1) -> Dict[str, Any]:
        if not self.session: await self.ignite()
        ts = str(int(time.time() * 1000))
        req_params = params or {}
        p_str = urllib.parse.urlencode(req_params) if method == "GET" else json.dumps(req_params)
        
        headers = {"Content-Type": "application/json"}
        if signed:
            headers.update({
                "X-BAPI-API-KEY": API_KEY,
                "X-BAPI-SIGN": self._sign(ts, p_str),
                "X-BAPI-TIMESTAMP": ts,
                "X-BAPI-RECV-WINDOW": "5000"
            })
            
        url = self.base + path + (f"?{p_str}" if method == "GET" else "")

        for attempt in range(retries):
            try:
                async with self.session.request(method, url, headers=headers, data=None if method == "GET" else p_str) as r:
                    if r.status == 403:
                        error_text = await r.text()
                        self.state.logs.append(f"[bold red]❌ HTTP 403 Forbidden: Check API key permissions or IP restrictions. Response: {error_text}[/bold red]")
                        return {"retCode": -1, "retMsg": f"HTTP 403 Forbidden: {error_text}"}
                    
                    try:
                        data = await r.json()
                    except aiohttp.ContentTypeError:
                        error_text = await r.text()
                        self.state.logs.append(f"[bold red]❌ Attempt to decode JSON with unexpected mimetype: {r.headers.get('Content-Type')}. Response: {error_text}[/bold red]")
                        return {"retCode": -1, "retMsg": f"Unexpected content type: {r.headers.get('Content-Type')}. Response: {error_text}"}
                    
                    if data is not None and data.get('retCode') == 0:
                        return data
                    elif data is not None and data.get('retCode') == 10001:
                        self.state.logs.append("[bold red]❌ Bybit API Error 10001: accountType only support UNIFIED. Please ensure your Bybit account is upgraded to a Unified Trading Account.[/bold red]")
                        return data
                    elif data is not None and data.get('retCode') != 0:
                        self.state.logs.append(f"[bold yellow]API call failed (attempt {attempt + 1}/{retries}): {data.get('retMsg', 'Unknown error')}. Retrying in {delay}s...[/bold yellow]")
                    else:
                        self.state.logs.append(f"[bold yellow]API call returned null response (attempt {attempt + 1}/{retries}). Retrying in {delay}s...[/bold yellow]")
                
            except aiohttp.ClientError as e:
                self.state.logs.append(f"[bold yellow]Network or HTTP error (attempt {attempt + 1}/{retries}): {e}. Retrying in {delay}s...[/bold red]")
            except json.JSONDecodeError:
                self.state.logs.append(f"[bold yellow]Failed to decode JSON response (attempt {attempt + 1}/{retries}). Retrying in {delay}s...[/bold yellow]")
            except Exception as e:
                self.state.logs.append(f"[bold red]Unhandled error during API call (attempt {attempt + 1}/{retries}): {e}. Not retrying.[/bold red]")
                return {"retCode": -1, "retMsg": str(e)}
            
            await asyncio.sleep(delay)
        
        self.state.logs.append(f"[bold red]❌ API call failed after {retries} attempts for {path}.[/bold red]")
        return {"retCode": -1, "retMsg": f"API call failed after {retries} attempts."}

# --- Tactical Logic (from ehl.py and ehl1.4.py) ---

async def execute_trade(forge: BybitForge, side: str, state: SentinelState, config: StrategyConfig):
    if state.daily_pnl <= -(state.high_water_mark_equity * config.daily_loss_limit / 100):
        state.logs.append("[bold red]❌ Daily loss limit reached. Trade skipped.[/bold red]")
        return

    atr_dec = Decimal(str(round(state.atr, 4)))
    sl_mult = config.scalping_sl_mult
    
    if side == "Buy":
        sl = state.price - (atr_dec * sl_mult)
        sl_dist = state.price - sl
    else:
        sl = state.price + (atr_dec * sl_mult)
        sl_dist = sl - state.price

    if sl_dist <= 0:
        state.logs.append("[bold red]❌ SL distance is zero or negative. Trade skipped.[/bold red]")
        return

    # ATR Risk-Parity Sizing (Capital * Risk% / SL Distance)
    conviction = Decimal(str(np.clip(abs(state.velocity), 0.8, 1.5)))
    risk_usd = state.balance * (config.base_risk_percent / 100) * conviction
    raw_qty = risk_usd / sl_dist
    qty = (raw_qty // state.qty_step) * state.qty_step

    if qty <= 0:
        state.logs.append(f"[bold red]❌ Trade skipped: Calculated quantity ({qty}) is zero or negative.[/bold red]")
        return

    tp_mult = config.scalping_tp_mult * Decimal(str(np.clip(1.0 - (abs(state.velocity) * 0.1), 0.7, 1.2)))
    tp = (state.price + atr_dec * tp_mult) if side == "Buy" else (state.price - atr_dec * tp_mult)
    sl = sl # sl is already calculated

    order = {
        "category": config.category, "symbol": config.symbol, "side": side, "orderType": "Market", "qty": str(qty),
        "takeProfit": f"{tp:.{state.price_prec}f}", "stopLoss": f"{sl:.{state.price_prec}f}",
        "tpTriggerBy": "LastPrice", "slTriggerBy": "LastPrice"
    }
    
    res = await forge.call("POST", "/v5/order/create", order, signed=True)
    if res.get('retCode') == 0:
        state.last_ritual = time.time()
        state.initial_sl_distance = sl_dist
        state.partial_tp_claimed = False
        state.high_water_mark = state.price
        state.trailing_stop_offset = sl_dist # Initialize trailing stop offset
        state.logs.append(f"[bold green]⚔️ {side} Kinetic Entry | Qty: {qty} | Risk: {risk_usd:.2f} USDT[/bold green]")
    else:
        error_msg = res.get('retMsg', 'Unknown error')
        state.logs.append(f"[bold red]❌ Order placement failed ({side}): {error_msg} (Code: {res.get('retCode')})[/bold red]")

async def manage_trade(forge: BybitForge, state: SentinelState, config: StrategyConfig):
    if not state.trade_active: return
    
    atr_dec = Decimal(str(round(state.atr, 4)))
    pullback_limit = atr_dec * Decimal("0.8") # Dynamic Pullback Exit
    
    # 1. Partial TP at 2R Profit
    if not state.partial_tp_claimed and state.initial_sl_distance > 0:
        pnl_dist = abs(state.price - state.entry_price)
        if pnl_dist > (state.initial_sl_distance * Decimal("2.0")):
            state.logs.append("[yellow]🔮 Partial TP (2R) Triggered.[/yellow]")
            exit_side = "Sell" if state.side == "Buy" else "Buy"
            res = await forge.call("POST", "/v5/order/create", {
                "category": config.category, "symbol": config.symbol, "side": exit_side, 
                "orderType": "Market", "qty": str(state.qty * Decimal("0.5")), "reduceOnly": True
            }, signed=True)
            if res.get('retCode') == 0:
                state.partial_tp_claimed = True
                state.logs.append("[bold green]✅ Partial TP order placed successfully.[/bold green]")
            else:
                error_msg = res.get('retMsg', 'Unknown error')
                state.logs.append(f"[bold red]❌ Partial TP order failed: {error_msg} (Code: {res.get('retCode')})[/bold red]")

    # 2. Trailing Stop Loss
    if state.side == "Buy":
        state.high_water_mark = max(state.high_water_mark, state.price)
        trailing_stop_price = state.high_water_mark - state.trailing_stop_offset
        if state.price <= trailing_stop_price:
            state.logs.append("[orange1]DISSOLVE: Trailing Stop Loss (Long)[/orange1]")
            res = await forge.call("POST", "/v5/order/create", {"category": config.category, "symbol": config.symbol, "side": "Sell", "orderType": "Market", "qty": str(state.qty), "reduceOnly": True}, signed=True)
            if res.get('retCode') == 0:
                state.logs.append("[bold green]✅ Trailing Stop Loss exit order placed successfully.[/bold green]")
            else:
                error_msg = res.get('retMsg', 'Unknown error')
                state.logs.append(f"[bold red]❌ Trailing Stop Loss exit order failed: {error_msg} (Code: {res.get('retCode')})[/bold red]")
    else: # Sell
        state.high_water_mark = min(state.high_water_mark, state.price)
        trailing_stop_price = state.high_water_mark + state.trailing_stop_offset
        if state.price >= trailing_stop_price:
            state.logs.append("[orange1]DISSOLVE: Trailing Stop Loss (Short)[/orange1]")
            res = await forge.call("POST", "/v5/order/create", {"category": config.category, "symbol": config.symbol, "side": "Buy", "orderType": "Market", "qty": str(state.qty), "reduceOnly": True}, signed=True)
            if res.get('retCode') == 0:
                state.logs.append("[bold green]✅ Trailing Stop Loss exit order placed successfully.[/bold green]")
            else:
                error_msg = res.get('retMsg', 'Unknown error')
                state.logs.append(f"[bold red]❌ Trailing Stop Loss exit order failed: {error_msg} (Code: {res.get('retCode')})[/bold red]")

# --- Engines (from ehl.py) ---

async def private_manager(forge: BybitForge, state: SentinelState, config: StrategyConfig):
    ws_private = WebSocket(
        testnet=IS_TESTNET,
        api_key=API_KEY,
        api_secret=API_SECRET,
        channel_type=config.category # Use config.category for channel_type
    )

    def handle_wallet_message(message):
        data = message.get('data', [{}])[0]
        wallet_balance = data.get('walletBalance', 0)
        state.balance = Decimal(str(wallet_balance))
        state.high_water_mark_equity = max(state.high_water_mark_equity, state.balance)
        state.daily_pnl = state.balance - state.initial_balance

    def handle_position_message(message):
        for pos in message.get('data', []):
            symbol = pos['symbol']
            size = Decimal(pos['size'])
            side = pos['side']
            avg_price = Decimal(pos['avgPrice'])
            unrealised_pnl = Decimal(pos['unrealisedPnl'])

            if size > 0:
                state.trade_active = True
                state.side = side
                state.entry_price = avg_price
                state.qty = size
                state.upnl = unrealised_pnl
            else:
                if state.trade_active:
                    recent_pnl = state.balance - state.initial_balance - state.daily_pnl
                    state.cooldown_seconds = config.scalping_cooldown_seconds * 2 if recent_pnl < 0 else config.scalping_cooldown_seconds
                    state.logs.append(f"[bold yellow]Cooldown adjusted to {state.cooldown_seconds}s due to recent PnL.[/bold yellow]")
                state.trade_active = False

    ws_private.wallet_stream(callback=handle_wallet_message)
    ws_private.position_stream(callback=handle_position_message)
    state.logs.append(f"[bold green]Subscribed to private streams via pybit private WebSocket.[/bold green]")

    bal = await forge.call("GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED"}, signed=True)
    if bal and bal.get('retCode') == 0:
        try:
            for coin_info in bal['result']['list'][0]['coin']:
                if coin_info['coin'] == 'USDT':
                    state.balance = Decimal(coin_info['walletBalance'])
                    state.initial_balance = state.balance
                    state.high_water_mark_equity = state.balance
                    state.logs.append(f"[bold green]Initial balance synced: {state.balance} USDT[/bold green]")
                    break
            else:
                state.logs.append("[bold red]❌ USDT balance not found in wallet-balance response.[/bold red]")
        except Exception as e:
            state.logs.append(f"[bold red]❌ Error parsing wallet balance: {e}[/bold red]")
    else:
        error_msg = bal.get('retMsg', 'Unknown error') if bal else 'No response'
        state.logs.append(f"[bold red]❌ Failed to fetch wallet balance: {error_msg} (Code: {bal.get('retCode') if bal else 'N/A'})[/bold red]")

    while True:
        await asyncio.sleep(1)

async def public_market_data_manager(forge: BybitForge, state: SentinelState, config: StrategyConfig):
    ws_public = WebSocket(
        testnet=IS_TESTNET,
        channel_type=config.category
    )

    def handle_kline_message(message):
        data = message.get('data', [])
        if not data: return
        
        for candle_data in data:
            high = float(candle_data["high"])
            low = float(candle_data["low"])
            close = float(candle_data["close"])
            volume = float(candle_data["volume"])
            
            state.ohlc.append((high, low, close, volume))
            state.price = Decimal(str(close))
            update_oracle(state, config) # Pass config to update_oracle
            state.is_ready = True

    ws_public.kline_stream(
        callback=handle_kline_message,
        interval=1,
        symbol=config.symbol
    )
    state.logs.append(f"[bold green]Subscribed to kline.1.{config.symbol} via pybit public WebSocket.[/bold green]")

    while True:
        await asyncio.sleep(1)

async def logic_engine(forge: BybitForge, state: SentinelState, config: StrategyConfig):
    while True:
        try:
            if not state.is_ready:
                await asyncio.sleep(1)
                continue
            
            if not state.trade_active and (time.time() - state.last_ritual > state.cooldown_seconds):
                if len(state.fisher_series) >= 2:
                    is_bull = state.price > state.macro_trend
                    is_long_term_bull = state.price > state.long_term_ema
                    is_above_vwap = state.price > state.vwap
                    buy_confirm = state.fisher_series[-1] > state.fisher_series[-2] and state.fisher_series[-2] < -state.dynamic_threshold
                    sell_confirm = state.fisher_series[-1] < state.fisher_series[-2] and state.fisher_series[-2] > state.dynamic_threshold
                    
                    if is_bull and is_long_term_bull and is_above_vwap and buy_confirm and state.trend_strength > config.scalping_trend_strength_min:
                        state.logs.append("[bold blue]SIGNAL: Long entry conditions met.[/bold blue]")
                        await execute_trade(forge, "Buy", state, config)
                    elif not is_bull and not is_long_term_bull and not is_above_vwap and sell_confirm and state.trend_strength > config.scalping_trend_strength_min:
                        state.logs.append("[bold blue]SIGNAL: Short entry conditions met.[/bold blue]")
                        await execute_trade(forge, "Sell", state, config)
            
            await manage_trade(forge, state, config)
            await asyncio.sleep(1)
        except Exception as e:
            state.logs.append(f"[bold red]❌ Unhandled error in logic_engine: {e}[/bold red]")
            await asyncio.sleep(2)

# --- UI Render (from ehl.py) ---

def get_layout():
    l = Layout()
    l.split_column(Layout(name="head", size=3), Layout(name="body", ratio=1), Layout(name="foot", size=10))
    l["body"].split_row(Layout(name="oracle"), Layout(name="pos"))
    return l

def render_ui(layout):
    pnl_style = "bold green" if state.daily_pnl >= 0 else "bold red"
    layout["head"].update(Panel(Text(f"BCH SENTINEL v4.5 | SCALPER | Session PnL: {state.daily_pnl:+.2f} USDT", justify="center", style="bold cyan"), border_style="blue"))
    
    oracle = Text()
    oracle.append(f"Price:  {state.price}\n", style="white")
    oracle.append(f"Fisher: {state.fisher:+.4f}\n", style="bold yellow")
    oracle.append(f"Trend:  {'BULL' if state.price > state.macro_trend else 'BEAR'} ({state.trend_strength:.2f})\n", style="bold magenta")
    oracle.append(f"ATR:    {state.atr:.2f}\n", style="cyan")
    layout["oracle"].update(Panel(oracle, title="INDICATORS", border_style="yellow"))
    
    pos = Table.grid(expand=True)
    pos.add_row("SIDE:", f"[bold]{state.side}[/]")
    pos.add_row("uPNL:", f"[bold {{'green' if state.upnl >= 0 else 'red'}}]{state.upnl:+.2f}[/]")
    pos.add_row("CD:", f"{max(0, int(state.cooldown_seconds - (time.time() - state.last_ritual)))}s")
    layout["pos"].update(Panel(pos, title="POSITION", border_style="green"))
    
    layout["foot"].update(Panel(Text("\n".join(state.logs)), title="LOGS", border_style="dim cyan"))

async def main():
    config = StrategyConfig()
    state = SentinelState(config)

    # Update global SYMBOL and CATEGORY for BybitForge and WebSocket subscriptions
    global SYMBOL, CATEGORY
    SYMBOL = config.symbol
    CATEGORY = config.category

    async with BybitForge(state) as forge:
        res = await forge.call("GET", "/v5/market/instruments-info", {"category": config.category, "symbol": config.symbol})
        if res and res.get('retCode') == 0:
            specs = res['result']['list'][0]
            state.price_prec = abs(Decimal(specs['priceFilter']['tickSize']).normalize().as_tuple().exponent)
            state.qty_step = Decimal(specs['lotSizeFilter']['qtyStep'])
        else:
            error_msg = res.get('retMsg', 'Unknown error') if res else 'No response'
            state.logs.append(f"[bold red]❌ Failed to fetch instrument info: {error_msg} (Code: {res.get('retCode') if res else 'N/A'})[/bold red]")
            state.logs.append("[bold yellow]Using default precision values due to API error.[/bold yellow]")

        layout = get_layout()
        with Live(layout, refresh_per_second=4, screen=True):
            asyncio.create_task(private_manager(forge, state, config))
            asyncio.create_task(public_market_data_manager(forge, state, config))
            asyncio.create_task(logic_engine(forge, state, config))
            while True:
                render_ui(layout)
                await asyncio.sleep(0.5)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
