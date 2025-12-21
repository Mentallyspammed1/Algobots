"""
BCH OMNI-SENTINEL V21.4 – THE UNYIELDING SWIFT STRIKER
Reforged by Pyrmethus the Wizard.
Status: Optimized for high-frequency, low-latency scalping with enhanced API compatibility,
        robust WebSocket data handling, and true daily PnL tracking.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import time
import traceback  # Added for detailed error logging
import urllib.parse
from collections import deque
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime  # For true daily PnL reset
from datetime import timezone  # For true daily PnL reset
from decimal import ROUND_DOWN
from decimal import Decimal
from decimal import InvalidOperation
from decimal import getcontext
from typing import Any

import aiohttp
import numpy as np
from colorama import Fore
from colorama import Style
from colorama import init
from dotenv import load_dotenv
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Initialize the Primal Glow for Colorama
init(autoreset=True)

# Set precision for the digital loom
getcontext().prec = 28

# Load Vault Credentials
load_dotenv()
API_KEY = os.getenv("BYBIT_API_KEY", "")
API_SECRET = os.getenv("BYBIT_API_SECRET", "")
IS_TESTNET = os.getenv("BYBIT_TESTNET", "false").lower() == "true"
LOG_FILE = "bot.log" # Chronicle file for persistent logging

# =========================
# HELPER INCANTATIONS
# =========================

def safe_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    """Converts a value to Decimal, handling None or empty strings gracefully."""
    if value is None or value == '':
        return default
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return default

def quantize_step(value: Decimal, step: Decimal) -> Decimal:
    """Quantizes a Decimal value to the nearest step, rounding down."""
    if step == Decimal("0"):
        return value
    return (value // step) * step

def safe_div(numerator: Decimal, denominator: Decimal, default: Decimal = Decimal("0")) -> Decimal:
    """Performs safe division, returning a default if denominator is zero."""
    if denominator == Decimal("0"):
        return default
    return numerator / denominator

# =========================
# TERMUX NATIVE WARDS
# =========================

class TermuxAPI:
    """
    # A conduit to the Android device's native powers via Termux:API.
    # Requires 'pkg install termux-api' and the Termux:API app.
    """
    @staticmethod
    def toast(msg: str, short: bool = True):
        """Casts a transient notification (toast) on the Android device."""
        duration = "short" if short else "long"
        # Using specific colors for better visibility in Termux
        os.system(f"termux-toast -b '#00FFFF' -c '#000000' -g top -r {duration} '{msg}' &")

    @staticmethod
    def notify(title: str, msg: str, id: int = 12):
        """Summons a persistent notification in the Android notification shade."""
        os.system(f"termux-notification -t '{title}' -c '{msg}' --id {id} &")

    @staticmethod
    def speak(text: str):
        """Causes the device to speak the given text aloud."""
        os.system(f"termux-tts-speak '{text}' &")

    @staticmethod
    def wake_lock():
        """Prevents the device from sleeping, maintaining the bot's vigil."""
        os.system("termux-wake-lock")

    @staticmethod
    def wake_unlock():
        """Releases the wake lock, allowing the device to sleep naturally."""
        os.system("termux-wake-unlock")

    @staticmethod
    def get_battery_status() -> dict[str, Any]:
        """Retrieves the device's battery status."""
        try:
            result = os.popen("termux-battery-status").read()
            return json.loads(result)
        except (json.JSONDecodeError, FileNotFoundError):
            return {"percentage": -1, "status": "UNKNOWN"}

# =========================
# CONFIGURATION GRIMOIRE
# =========================

@dataclass(slots=True)
class ScalperConfig:
    """The sacred scrolls of configuration for the scalping ritual."""
    symbol: str = "BCHUSDT"
    category: str = "linear"
    leverage: int = 20

    # --- The Sentinel's Vows (Tighter for Scalping) ---
    max_latency_ms: int = 300 # Reduced latency tolerance
    max_spread_pct: Decimal = Decimal("0.0005") # Very tight spread tolerance
    max_hold_sec: int = 180 # Max 3 minutes hold time

    # --- Capital Management (Adjusted for Scalping) ---
    risk_per_trade_pct: Decimal = Decimal("0.002") # 0.2% of available balance per trade
    sl_atr_mult: Decimal = Decimal("1.0") # Tighter stop loss
    tp_partial_atr_mult: Decimal = Decimal("0.8") # Quicker partial profit taking
    trail_atr_mult: Decimal = Decimal("0.7") # Tighter trailing stop

    # --- Confluence Thresholds (Adjusted for Scalping) ---
    min_alpha_score: float = 80.0 # Higher bar for entry
    vsi_threshold: float = 1.5 # Higher volume conviction needed
    rsi_period: int = 7 # Faster RSI

    # --- Circuit Breakers ---
    max_consecutive_losses: int = 3
    daily_profit_target_pct: Decimal = Decimal("0.10")
    daily_loss_limit_pct: Decimal = Decimal("0.05")
    close_on_daily_limit: bool = True # Close open positions if daily limit hit

    # --- Temporal Rhythms (Faster for Scalping) ---
    kline_interval: str = "1" # 1-minute candles
    cooldown_base: int = 5 # Faster cooldown
    warmup_candles: int = 100
    ws_heartbeat: int = 20

    # --- Termux Specific ---
    battery_alert_threshold: int = 20 # Alert if battery drops below this percentage

    # --- Entry Confirmation (Faster for Scalping) ---
    entry_confirmation_candles: int = 1 # Minimal confirmation for faster entries
    price_ema_proximity_pct: Decimal = Decimal("0.0002") # Price must be within 0.02% of EMA for entry

    @staticmethod
    def load_from_file(filepath: str = "config.json") -> ScalperConfig:
        """Loads configuration from a JSON file, merging with defaults."""
        default_config = ScalperConfig()
        try:
            with open(filepath) as f:
                data = json.load(f)

            config_attrs = {f.name for f in ScalperConfig.__dataclass_fields__.values()}

            filtered_data = {}
            for key, value in data.items():
                if key not in config_attrs:
                    print(f"{Fore.YELLOW}# Warning: Unknown configuration key '{key}' in config.json. Ignoring.{Style.RESET_ALL}")
                    continue

                default_val = getattr(default_config, key)
                if isinstance(default_val, Decimal):
                    filtered_data[key] = safe_decimal(value)
                elif isinstance(default_val, float):
                    try: filtered_data[key] = float(value)
                    except (ValueError, TypeError): filtered_data[key] = default_val
                elif isinstance(default_val, int):
                    try: filtered_data[key] = int(value)
                    except (ValueError, TypeError): filtered_data[key] = default_val
                elif isinstance(default_val, bool):
                    try: filtered_data[key] = bool(value)
                    except (ValueError, TypeError): filtered_data[key] = default_val
                else: # string
                    filtered_data[key] = value

            return ScalperConfig(**filtered_data)
        except FileNotFoundError:
            print(f"{Fore.YELLOW}# Warning: config.json not found. Using default configuration.{Style.RESET_ALL}")
            return default_config
        except json.JSONDecodeError as e:
            print(f"{Fore.RED}# Error: Invalid JSON in config.json: {e}. Using default configuration.{Style.RESET_ALL}")
            return default_config
        except TypeError as e:
            print(f"{Fore.RED}# Error: Configuration type mismatch during loading from config.json: {e}. Using default configuration.{Style.RESET_ALL}")
            return default_config

@dataclass(slots=True)
class SentinelState:
    """The repository of the bot's current state and mystical insights."""
    config: ScalperConfig

    # Vault Essence
    equity: Decimal = Decimal("0")
    available: Decimal = Decimal("0")

    initial_equity_session: Decimal = Decimal("0") # Equity at bot start
    initial_equity_daily: Decimal = Decimal("0")   # Equity at start of current UTC day
    last_daily_reset_date: str = ""                # UTC date string for daily reset check

    current_session_pnl: Decimal = Decimal("0")    # PnL since bot started (equity - initial_equity_session)
    current_session_pnl_pct: Decimal = Decimal("0")

    daily_pnl: Decimal = Decimal("0")              # PnL since start of current UTC day (equity - initial_equity_daily)
    daily_pnl_pct: Decimal = Decimal("0")
    daily_profit_reached: bool = False
    daily_loss_reached: bool = False

    total_realized_pnl_session: Decimal = Decimal("0") # Sum of PnLs from closed trades within this session

    # Market Pulse
    price: Decimal = Decimal("0")
    bid: Decimal = Decimal("0")
    ask: Decimal = Decimal("0")
    obi_score: float = 0.0
    ema_fast: Decimal = Decimal("0")
    ema_macro: Decimal = Decimal("0")
    vwap: Decimal = Decimal("0")
    atr: float = 0.0
    rsi: float = 0.0

    # --- FIXED ATTRIBUTE ANCHORS (Ensured presence for slots=True) ---
    fisher: float = 0.0
    fisher_sig: float = 0.0
    alpha_score: float = 0.0
    vsi: float = 1.0 # Volume Singularity Index

    # Precision Glyphs
    price_prec: int = 2
    qty_step: Decimal = Decimal("0.01")
    min_qty: Decimal = Decimal("0.01")

    ohlc: deque[tuple[float, float, float, float, float]] = field(default_factory=lambda: deque(maxlen=400))

    # Position Realm
    active: bool = False
    side: str = "HOLD"
    qty: Decimal = Decimal("0")
    entry_p: Decimal = Decimal("0")
    upnl: Decimal = Decimal("0")
    last_trade_pnl: Decimal = Decimal("0") # PnL of the last closed trade
    entry_ts: float = 0.0
    stage: int = 0  # 0: No position, 1: Initial entry, 2: Partial TP hit
    trailing_sl_value: Decimal = Decimal("0") # Actual trailing SL value set on exchange

    # Ledger
    trade_count: int = 0
    wins: int = 0
    loss_streak: int = 0
    latency: int = 0
    last_trade_ts: float = 0.0
    stasis_until: float = 0.0 # Time until bot comes out of stasis (cooldown due to consecutive losses)

    # Termux Specific
    battery_level: int = -1
    battery_status: str = "UNKNOWN"
    battery_alert_sent: bool = False

    # Entry Confirmation
    signal_confirmed_candles: int = 0
    last_signal_direction: str = "NONE" # "BUY" or "SELL"

    # Chronicles
    logs: deque[str] = field(default_factory=lambda: deque(maxlen=24))
    ready: bool = False

    local_bids: dict[Decimal, Decimal] = field(default_factory=dict)
    local_asks: dict[Decimal, Decimal] = field(default_factory=dict)

    def __post_init__(self):
        """Initializes log file after dataclass creation."""
        with open(LOG_FILE, "a") as f:
            f.write(f"\n--- Session Started: {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")

    def log(self, msg: str, level: str = "info"):
        """Records a message in the chronicle with a timestamp and style, and writes to file."""
        ts_str = time.strftime("%H:%M:%S")
        styles = {
            "info": "white",
            "entry": "bold green",
            "exit": "bold magenta",
            "warn": "bold yellow",
            "error": "bold red",
            "debug": "dim white"
        }

        # Use rich markup for console, plain text for file
        colored_msg = f"[dim]{ts_str}[/] [{styles.get(level, 'white')}]{msg}[/]"
        self.logs.append(colored_msg)

        clean_msg = f"{ts_str} [{level.upper()}] {msg}"
        with open(LOG_FILE, "a") as f:
            f.write(clean_msg + "\n")

# =========================
# THE APEX V21 ENGINE
# =========================

class BybitApex:
    """The core engine for interacting with Bybit's mystical APIs."""
    def __init__(self, state: SentinelState):
        self.state = state
        self.cfg = state.config
        self.base = "https://api-testnet.bybit.com" if IS_TESTNET else "https://api.bybit.com"
        self.ws_pub = "wss://stream.bybit.com/v5/public/linear"
        self.ws_priv = "wss://stream.bybit.com/v5/private"
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        """Establishes the ethereal connection (aiohttp session)."""
        conn = aiohttp.TCPConnector(limit=15, ttl_dns_cache=360)
        self.session = aiohttp.ClientSession(connector=conn, timeout=aiohttp.ClientTimeout(total=10))
        return self

    async def __aexit__(self, *args):
        """Severs the ethereal connection upon exit."""
        if self.session: await self.session.close()

    def _sign(self, payload: str, ts: str) -> str:
        """Forges the digital signature for API requests."""
        param_str = ts + API_KEY + "5000" + payload # 5000 is the recvWindow
        return hmac.new(API_SECRET.encode(), param_str.encode(), hashlib.sha256).hexdigest()

    async def request(self, method: str, path: str, params: dict = None) -> dict:
        """Sends a request to the Bybit API realm."""
        params = params or {}
        ts = str(int(time.time() * 1000))

        # Acquire wake lock for critical API calls
        TermuxAPI.wake_lock()
        try:
            if method == "GET":
                query = urllib.parse.urlencode(sorted(params.items()))
                payload, url = query, f"{self.base}{path}?{query}"
            else: # POST
                payload = json.dumps(params, separators=(",", ":"))
                url = f"{self.base}{path}"

            headers = {
                "X-BAPI-API-KEY": API_KEY, "X-BAPI-SIGN": self._sign(payload, ts),
                "X-BAPI-TIMESTAMP": ts, "X-BAPI-RECV-WINDOW": "5000", "Content-Type": "application/json"
            }
            async with self.session.request(method, url, headers=headers, data=None if method=="GET" else payload) as r:
                r.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
                return await r.json()
        except aiohttp.ClientError as e:
            self.state.log(f"{Fore.RED}API Request Failed ({method} {path}): Network/HTTP error: {e}{Style.RESET_ALL}", "error")
            TermuxAPI.notify("Bybit API Error", f"Network/HTTP error: {e}", id=101)
            return {"retCode": -1, "retMsg": str(e)}
        except json.JSONDecodeError:
            self.state.log(f"{Fore.RED}API Request Failed ({method} {path}): Invalid JSON response.{Style.RESET_ALL}", "error")
            return {"retCode": -1, "retMsg": "Invalid JSON response"}
        except Exception as e:
            self.state.log(f"{Fore.RED}API Request Failed ({method} {path}): Unexpected error: {e}{Style.RESET_ALL}", "error")
            return {"retCode": -1, "retMsg": str(e)}
        finally:
            TermuxAPI.wake_unlock() # Release wake lock

    async def boot_ritual(self):
        """
        # Performs initial synchronization rituals: instrument info and leverage setting.
        # Now robustly handles 'lotFilter' vs 'lotSizeFilter' API response differences.
        """
        self.state.log(f"{Fore.CYAN}# Syncing Instrument Ritual...{Style.RESET_ALL}", "info")
        r = await self.request("GET", "/v5/market/instruments-info", {"category": self.cfg.category, "symbol": self.cfg.symbol})
        if r.get("retCode") == 0:
            i = r["result"]["list"][0]
            tick = Decimal(i["priceFilter"]["tickSize"])
            self.state.price_prec = abs(tick.normalize().as_tuple().exponent)

            # Robustly check for lotFilter or lotSizeFilter
            lot_filter_data = None
            if "lotFilter" in i:
                lot_filter_data = i["lotFilter"]
                self.state.log(f"{Fore.GREEN}Using 'lotFilter' from API response.{Style.RESET_ALL}", "debug")
            elif "lotSizeFilter" in i: # Fallback for older API versions or testnet quirks
                lot_filter_data = i["lotSizeFilter"]
                self.state.log(f"{Fore.YELLOW}Using 'lotSizeFilter' from API response (fallback).{Style.RESET_ALL}", "warn")

            if lot_filter_data:
                self.state.qty_step = Decimal(lot_filter_data["qtyStep"])
                self.state.min_qty = Decimal(lot_filter_data["minOrderQty"])
                self.state.log(f"{Fore.GREEN}Instrument info synced. Price prec: {self.state.price_prec}, Qty step: {self.state.qty_step}.{Style.RESET_ALL}", "info")
            else:
                self.state.log(f"{Fore.RED}Failed to find 'lotFilter' or 'lotSizeFilter' in API response. Cannot set quantity steps.{Style.RESET_ALL}", "error")
                TermuxAPI.notify("Boot Ritual Failed", "Missing lot filter info.", id=102)

        else:
            self.state.log(f"{Fore.RED}Failed to sync instrument info: {r.get('retMsg')}{Style.RESET_ALL}", "error")
            TermuxAPI.notify("Boot Ritual Failed", f"Instrument info: {r.get('retMsg')}", id=102)

        leverage_res = await self.request("POST", "/v5/position/set-leverage", {
            "category": self.cfg.category, "symbol": self.cfg.symbol,
            "buyLeverage": str(self.cfg.leverage), "sellLeverage": str(self.cfg.leverage)
        })
        if leverage_res.get("retCode") == 0:
            self.state.log(f"{Fore.GREEN}Leverage set to {self.cfg.leverage}x.{Style.RESET_ALL}", "info")
        else:
            self.state.log(f"{Fore.RED}Failed to set leverage: {leverage_res.get('retMsg')}{Style.RESET_ALL}", "error")
            TermuxAPI.notify("Boot Ritual Failed", f"Set leverage: {leverage_res.get('retMsg')}", id=103)


    async def fetch_history(self):
        """# Summons ancient kline scrolls to warm up the oracle's vision."""
        self.state.log(f"{Fore.CYAN}# Summoning ancient kline scrolls...{Style.RESET_ALL}", "info")
        r = await self.request("GET", "/v5/market/kline", {
            "category": self.cfg.category, "symbol": self.cfg.symbol,
            "interval": self.cfg.kline_interval, "limit": "200" # Fetch enough for all indicators
        })
        if r.get("retCode") == 0:
            for k in reversed(r["result"]["list"]):
                self.state.ohlc.append((float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])))
            self.state.log(f"{Fore.GREEN}Ancient kline scrolls unveiled: {len(self.state.ohlc)} candles.{Style.RESET_ALL}", "info")
            self._update_oracle() # Initialize indicators
        else:
            self.state.log(f"{Fore.RED}Failed to fetch kline history: {r.get('retMsg')}{Style.RESET_ALL}", "error")
            TermuxAPI.notify("History Fetch Failed", f"Kline: {r.get('retMsg')}", id=104)

    async def update_wallet(self):
        """# Updates the bot's knowledge of its financial realm, including daily PnL reset."""
        r = await self.request("GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED"})
        if r.get("retCode") == 0:
            acc = r["result"]["list"][0]
            self.state.equity = safe_decimal(acc.get("totalEquity"))
            self.state.available = safe_decimal(acc.get("totalAvailableBalance"))

            # Initialize initial_equity_session if first run
            if self.state.initial_equity_session == Decimal("0"):
                self.state.initial_equity_session = self.state.equity

            # --- Daily PnL Reset Logic ---
            current_utc_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if self.state.last_daily_reset_date != current_utc_date:
                self.state.log(f"{Fore.CYAN}# Daily PnL reset initiated for {current_utc_date}.{Style.RESET_ALL}", "info")
                self.state.initial_equity_daily = self.state.equity
                self.state.daily_profit_reached = False
                self.state.daily_loss_reached = False
                self.state.last_daily_reset_date = current_utc_date
            elif self.state.initial_equity_daily == Decimal("0"): # Ensure it's set on first run of the day
                self.state.initial_equity_daily = self.state.equity

            # Update PnL metrics
            self.state.current_session_pnl = self.state.equity - self.state.initial_equity_session
            self.state.current_session_pnl_pct = safe_div(self.state.current_session_pnl, self.state.initial_equity_session)

            self.state.daily_pnl = self.state.equity - self.state.initial_equity_daily
            self.state.daily_pnl_pct = safe_div(self.state.daily_pnl, self.state.initial_equity_daily)

            self.state.log(f"{Fore.GREEN}Wallet synced. Equity: {self.state.equity:.2f} USDT. Daily PnL: {self.state.daily_pnl:+.2f}.{Style.RESET_ALL}", "info")
        else:
            self.state.log(f"{Fore.RED}Failed to update wallet: {r.get('retMsg')}{Style.RESET_ALL}", "error")
            TermuxAPI.notify("Wallet Update Failed", f"Balance: {r.get('retMsg')}", id=105)

    def _update_oracle(self, live_p: float = None):
        """
        # Weaves the threads of market data into mystical indicators.
        # Now includes ATR, Fisher, RSI, VWAP, EMAs, and VSI.
        """
        s, cfg = self.state, self.cfg
        if len(s.ohlc) < cfg.warmup_candles + cfg.rsi_period + 1: return # Need enough for diff and period

        c = np.array([x[3] for x in s.ohlc]) # Close prices
        if live_p: c[-1] = live_p # Update last close with live price for real-time indicators

        h = np.array([x[1] for x in s.ohlc]) # High prices
        l = np.array([x[2] for x in s.ohlc]) # Low prices
        v = np.array([x[4] for x in s.ohlc]) # Volume

        # 1. ATR (Volatility Flux)
        tr = np.maximum(h[1:] - l[1:], np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1]))
        s.atr = float(np.mean(tr[-14:])) if tr.size >= 14 else 0.0

        # 2. Fisher Momentum Acceleration
        win = c[-10:]
        mn, mx = np.min(win), np.max(win) + 1e-9
        norm = np.clip(0.66 * ((c[-1] - mn) / (mx - mn) - 0.5), -0.99, 0.99)
        s.fisher_sig = s.fisher # Store previous Fisher value
        s.fisher = 0.5 * np.log((1 + norm) / (1 - norm + 1e-9)) # Current Fisher

        # 3. RSI Overextension (SMA-based for simplicity)
        if len(c) > cfg.rsi_period:
            deltas = np.diff(c)
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)

            # Use rolling average for RSI calculation
            avg_gain = np.mean(gains[-cfg.rsi_period:])
            avg_loss = np.mean(losses[-cfg.rsi_period:])

            if avg_loss == 0: s.rsi = 100.0
            elif avg_gain == 0: s.rsi = 0.0
            else:
                rs = avg_gain / avg_loss
                s.rsi = 100 - (100 / (1 + rs))
        else:
            s.rsi = 0.0

        # 4. VWAP & EMAs
        if len(c) >= 30 and len(v) >= 30:
            tp = ((h+l+c)/3)[-30:]
            vol_30 = v[-30:]
            s.vwap = safe_decimal(np.sum(tp * vol_30) / (np.sum(vol_30) + 1e-9))
        else:
            s.vwap = Decimal("0")

        # EMA smoothing factors (5-period fast, 200-period macro)
        alpha_f, alpha_m = 2/(5+1), 2/(200+1)
        s.ema_fast = safe_decimal(alpha_f * c[-1] + (1 - alpha_f) * float(s.ema_fast or c[-1]))
        s.ema_macro = safe_decimal(alpha_m * c[-1] + (1 - alpha_m) * float(s.ema_macro or c[-1]))

        # 5. VSI (Volume Singularity Index)
        if len(v) >= 20:
            avg_v = np.mean(v[-20:])
            s.vsi = v[-1] / avg_v if avg_v > 0 else 1.0
        else:
            s.vsi = 1.0

        # --- ALPHA ENGINE (The Confluence Score - Re-weighted for Scalping) ---
        score = 0.0
        score += min(35, abs(s.obi_score) * 70) # Increased OBI contribution
        score += min(35, abs(s.fisher) * 25) # Slightly increased Fisher contribution

        # Trend alignment (price vs EMA_macro, aligned with Fisher direction)
        trend_aligned = (s.price > s.ema_macro and s.fisher > 0) or \
                        (s.price < s.ema_macro and s.fisher < 0)
        if trend_aligned: score += 15 # Slightly reduced trend weight for faster trades

        # RSI confluence (RSI not overbought/oversold in direction of Fisher)
        # Scalping often means trading within normal RSI ranges, avoiding extremes
        rsi_confluence = (s.fisher > 0 and s.rsi < 60) or \
                         (s.fisher < 0 and s.rsi > 40)
        if rsi_confluence: score += 15 # Increased RSI weight

        # Volume Singularity Index (VSI) for conviction
        if s.vsi > cfg.vsi_threshold: score += 15 # Increased VSI weight for volume conviction

        s.alpha_score = score
        s.ready = len(s.ohlc) >= cfg.warmup_candles + cfg.rsi_period + 1

    async def strike(self, side: str, qty: Decimal, reduce: bool = False):
        """
        # Executes a market strike (order) upon the digital battlefield.
        # Handles latency, spread, and sets initial stop loss/trailing stop.
        """
        s, cfg = self.state, self.cfg

        if not reduce: # Entry order checks
            if (s.ask - s.bid) / s.price > cfg.max_spread_pct:
                s.log(f"{Fore.YELLOW}Spread Guard: {safe_div(s.ask - s.bid, s.price):.4%} - Withheld strike.{Style.RESET_ALL}", "warn")
                TermuxAPI.toast("Strike withheld: High spread!")
                return
            if s.latency > cfg.max_latency_ms:
                s.log(f"{Fore.YELLOW}Latency Storm: {s.latency}ms - Withheld strike.{Style.RESET_ALL}", "warn")
                TermuxAPI.toast("Strike withheld: High latency!")
                return
            TermuxAPI.toast(f"STRIKE {side} {qty}")

        quantized_qty = qty.quantize(s.qty_step, ROUND_DOWN)
        if quantized_qty < s.min_qty:
            s.log(f"{Fore.YELLOW}Calculated quantity {qty} too small ({quantized_qty}). Minimum is {s.min_qty}. Withheld strike.{Style.RESET_ALL}", "warn")
            TermuxAPI.toast("Strike withheld: Qty too small!")
            return

        params = {
            "category": cfg.category, "symbol": cfg.symbol,
            "side": side, "orderType": "Market", "qty": str(quantized_qty),
            "reduceOnly": reduce
        }

        if not reduce: # Set initial SL for entry orders
            if s.atr == 0:
                s.log(f"{Fore.RED}ATR is zero, cannot calculate initial Stop Loss. Withheld strike.{Style.RESET_ALL}", "error")
                TermuxAPI.toast("Strike withheld: ATR zero!")
                return

            sl_price = s.price - (Decimal(str(s.atr)) * cfg.sl_atr_mult) if side == 'Buy' else s.price + (Decimal(str(s.atr)) * cfg.sl_atr_mult)
            sl_price = max(Decimal("0.01"), sl_price) # Ensure SL is positive
            params["stopLoss"] = str(sl_price.quantize(Decimal(f'1e-{s.price_prec}')))
            s.log(f"{Fore.CYAN}Initiating STRIKE {side} with Qty: {quantized_qty} and initial SL: {sl_price:.{s.price_prec}f}{Style.RESET_ALL}", "entry")
        else:
            s.log(f"{Fore.YELLOW}Executing HARVEST {side} for Qty: {quantized_qty}{Style.RESET_ALL}", "exit")

        r = await self.request("POST", "/v5/order/create", params)
        if r.get("retCode") == 0:
            s.log(f"{Fore.GREEN}{'HARVEST' if reduce else 'STRIKE'} {side} order placed successfully. Order ID: {r['result'].get('orderId')}{Style.RESET_ALL}", "entry" if not reduce else "exit")
            # s.trade_count and s.last_trade_ts are updated by private WS on position change
        else:
            s.log(f"{Fore.RED}API Error: {r.get('retMsg')}{Style.RESET_ALL}", "error")
            TermuxAPI.notify("Order Failed", f"Bybit: {r.get('retMsg')}", id=106)
            TermuxAPI.speak("Order failed!")

    async def logic_loop(self, stop: asyncio.Event):
        """
        # The heart of the oracle, where entry and exit spells are cast.
        # Continuously evaluates market conditions and manages active positions.
        """
        s, cfg = self.state, self.cfg
        s.log(f"{Fore.GREEN}Oracle's logic loop initiated.{Style.RESET_ALL}", "info")
        while not stop.is_set():
            await asyncio.sleep(0.2) # Accelerated heartbeat
            if not s.ready or s.price <= 0 or s.atr == 0:
                s.log(f"{Fore.YELLOW}Awaiting full arcane readiness (Ready: {s.ready}, Price: {s.price}, ATR: {s.atr:.2f}).{Style.RESET_ALL}", "warn")
                continue

            # --- Global Circuit Breakers ---
            if time.time() < s.stasis_until:
                s.log(f"{Fore.YELLOW}Bot in Stasis: {int(s.stasis_until - time.time())}s remaining.{Style.RESET_ALL}", "warn")
                continue

            if s.daily_loss_reached:
                s.log(f"{Fore.RED}Ritual Halted: Daily Loss Limit Reached ({s.daily_pnl_pct:.2%}).{Style.RESET_ALL}", "error")
                if cfg.close_on_daily_limit and s.active:
                    s.log(f"{Fore.RED}Closing open position due to daily loss limit.{Style.RESET_ALL}", "error")
                    await self.strike("Sell" if s.side == "Buy" else "Buy", s.qty, True)
                TermuxAPI.notify("Trading Halted", "Daily Loss Limit Reached!", id=107)
                TermuxAPI.speak("Daily loss limit reached. Trading halted.")
                await asyncio.sleep(3600) # Sleep for an hour if loss limit hit
                continue

            if s.daily_profit_reached:
                s.log(f"{Fore.GREEN}Ritual Halted: Daily Profit Target Reached ({s.daily_pnl_pct:.2%}).{Style.RESET_ALL}", "info")
                if cfg.close_on_daily_limit and s.active:
                    s.log(f"{Fore.GREEN}Closing open position due to daily profit target.{Style.RESET_ALL}", "info")
                    await self.strike("Sell" if s.side == "Buy" else "Buy", s.qty, True)
                TermuxAPI.notify("Trading Halted", "Daily Profit Target Reached!", id=108)
                TermuxAPI.speak("Daily profit target reached. Trading halted.")
                await asyncio.sleep(3600) # Sleep for an hour if profit target hit
                continue

            if s.active:
                # --- Position Management ---
                await self._manage_active_position()
            else:
                # --- Entry Logic ---
                await self._evaluate_entry_signals()

    async def _manage_active_position(self):
        """Manages an active position: partial TP, trailing SL, max hold time."""
        s, cfg = self.state, self.cfg
        atr_dec = Decimal(str(s.atr))

        if s.entry_p == Decimal("0") or s.qty == Decimal("0") or atr_dec == Decimal("0"):
            s.log(f"{Fore.RED}Anomaly: Zero entry price/qty/ATR for active position. Forcing closure.{Style.RESET_ALL}", "error")
            await self.strike("Sell" if s.side == "Buy" else "Buy", s.qty, True)
            return

        # 1. Partial TP Harvest (Stage 1 -> Stage 2)
        if s.stage == 1:
            pnl_pct = safe_div(abs(s.upnl), (s.entry_p * s.qty / cfg.leverage))
            if pnl_pct >= cfg.tp_partial_atr_mult:
                s.log(f"{Fore.GREEN}Stage 1 Harvest: 50% Profit Taken at {pnl_pct:.2%}. Setting trailing SL.{Style.RESET_ALL}", "exit")
                await self.strike("Sell" if s.side == "Buy" else "Buy", s.qty / 2, True)

                # Set trailing stop for remaining position
                trail_value = Decimal(str(s.atr * float(cfg.trail_atr_mult))).quantize(Decimal(f'1e-{s.price_prec}'))
                await self.request("POST", "/v5/position/trading-stop", {
                    "category": cfg.category, "symbol": cfg.symbol,
                    "trailingStop": str(trail_value), "positionIdx": 0 # 0 for one-way mode
                })
                s.trailing_sl_value = trail_value # Store the actual value set
                s.stage = 2 # Move to stage 2 (partial TP hit)
                TermuxAPI.toast("Partial TP hit!")

        # 2. Max Hold Time Reaper
        if (time.time() - s.entry_ts) > cfg.max_hold_sec:
            s.log(f"{Fore.MAGENTA}Reaper: Max Hold Time Reached ({cfg.max_hold_sec}s). Closing position.{Style.RESET_ALL}", "exit")
            await self.strike("Sell" if s.side == "Buy" else "Buy", s.qty, True)
            TermuxAPI.toast("Max hold time reached!")

    async def _evaluate_entry_signals(self):
        """Evaluates market conditions and casts entry spells if signals align."""
        s, cfg = self.state, self.cfg

        if time.time() - s.last_trade_ts < cfg.cooldown_base:
            s.log(f"{Fore.BLUE}Entry cooldown active: {int(cfg.cooldown_base - (time.time() - s.last_trade_ts))}s remaining.{Style.RESET_ALL}", "debug")
            return

        # Reset confirmation if signal changes or is lost
        current_signal_direction = "NONE"

        # Check price proximity to EMA_fast for scalping entries
        price_proximity_ok = safe_div(abs(s.price - s.ema_fast), s.ema_fast) < cfg.price_ema_proximity_pct

        if s.alpha_score >= cfg.min_alpha_score and price_proximity_ok:
            long_condition = (s.fisher > s.fisher_sig and s.price <= s.ema_fast * Decimal("1.0005") and s.rsi < 60)
            short_condition = (s.fisher < s.fisher_sig and s.price >= s.ema_fast * Decimal("0.9995") and s.rsi > 40)
            if long_condition: current_signal_direction = "BUY"
            elif short_condition: current_signal_direction = "SELL"

        if current_signal_direction != s.last_signal_direction:
            s.signal_confirmed_candles = 0
            s.last_signal_direction = current_signal_direction
            s.log(f"{Fore.YELLOW}Signal direction changed or lost. Resetting confirmation.{Style.RESET_ALL}", "debug")
            return

        if current_signal_direction == "NONE":
            s.signal_confirmed_candles = 0
            return

        # Increment confirmation if signal persists
        s.signal_confirmed_candles += 1
        s.log(f"{Fore.BLUE}Signal '{current_signal_direction}' confirmed: {s.signal_confirmed_candles}/{cfg.entry_confirmation_candles} candles.{Style.RESET_ALL}", "debug")

        if s.signal_confirmed_candles < cfg.entry_confirmation_candles:
            return # Await further confirmation

        # Signal confirmed, proceed with strike
        sl_dist = Decimal(str(s.atr * float(cfg.sl_atr_mult)))
        if sl_dist == Decimal("0"): return # Should be caught by bybitapex.strike

        # Calculate quantity based on risk per trade percentage of available balance
        risk_usdt = s.available * cfg.risk_per_trade_pct
        qty = safe_div(risk_usdt, sl_dist)
        qty = qty.quantize(s.qty_step, ROUND_DOWN)

        if qty < s.min_qty:
            s.log(f"{Fore.YELLOW}Calculated quantity {qty} is below minimum {s.min_qty}. Skipping entry.{Style.RESET_ALL}", "warn")
            return

        if current_signal_direction == "BUY":
            s.log(f"{Fore.BLUE}Long entry signal CONFIRMED! Alpha: {s.alpha_score:.1f}, Fisher: {s.fisher:.3f}, RSI: {s.rsi:.1f}. Preparing strike.{Style.RESET_ALL}", "info")
            await self.strike("Buy", qty)
        elif current_signal_direction == "SELL":
            s.log(f"{Fore.BLUE}Short entry signal CONFIRMED! Alpha: {s.alpha_score:.1f}, Fisher: {s.fisher:.3f}, RSI: {s.rsi:.1f}. Preparing strike.{Style.RESET_ALL}", "info")
            await self.strike("Sell", qty)

        # Reset confirmation after striking
        s.signal_confirmed_candles = 0
        s.last_signal_direction = "NONE"


    async def ws_nexus_public(self, stop: asyncio.Event):
        """# Channels public market data streams (tickers, orderbook, kline)."""
        self.state.log(f"{Fore.BLUE}# Channeling public market data streams...{Style.RESET_ALL}", "info")
        reconnect_delay = 1
        while not stop.is_set():
            try:
                async with self.session.ws_connect(self.ws_pub, heartbeat=self.cfg.ws_heartbeat) as ws:
                    self.state.log(f"{Fore.GREEN}Public WebSocket connected.{Style.RESET_ALL}", "info")
                    reconnect_delay = 1 # Reset delay on successful connection
                    await ws.send_json({"op": "subscribe", "args": [f"tickers.{self.cfg.symbol}", f"orderbook.50.{self.cfg.symbol}", f"kline.{self.cfg.kline_interval}.{self.cfg.symbol}"]})
                    async for msg in ws:
                        if stop.is_set(): break
                        d = json.loads(msg.data)
                        topic = d.get("topic", "")

                        if "tickers" in topic:
                            res = None
                            if d.get("data"):
                                if isinstance(d["data"], list) and d["data"]:
                                    res = d["data"][0]
                                elif isinstance(d["data"], dict):
                                    res = d["data"]
                                else:
                                    self.state.log(f"{Fore.YELLOW}Unexpected 'tickers' data structure: {d}{Style.RESET_ALL}", "debug")
                                    continue # Skip to next message
                            else:
                                self.state.log(f"{Fore.YELLOW}Received empty 'tickers' data: {d}{Style.RESET_ALL}", "debug")
                                continue # Skip to next message

                            # --- Robust Price Update Logic ---
                            received_last_price = res.get("lastPrice")
                            received_bid_price = res.get("bid1Price")
                            received_ask_price = res.get("ask1Price")

                            # Attempt to update price, using previous state as fallback if current value is problematic
                            new_price = safe_decimal(received_last_price, self.state.price)
                            new_bid = safe_decimal(received_bid_price, self.state.bid)
                            new_ask = safe_decimal(received_ask_price, self.state.ask)

                            if new_price == Decimal("0") and (new_bid > Decimal("0") or new_ask > Decimal("0")):
                                # If lastPrice is 0 but bid/ask are valid, use their midpoint as a fallback for price
                                new_price = safe_div(new_bid + new_ask, Decimal("2"), new_price)
                                self.state.log(f"{Fore.YELLOW}DEBUG: 'lastPrice' was zero, using (bid+ask)/2 as fallback: {new_price:.{self.state.price_prec}f}{Style.RESET_ALL}", "debug")
                            elif new_price == Decimal("0") and self.state.price == Decimal("0"):
                                self.state.log(f"{Fore.RED}DEBUG: 'lastPrice' and fallback (bid/ask) are zero. Raw ticker: {res}{Style.RESET_ALL}", "error")
                                # If price is still 0 and was previously 0, keep it 0 and log. No valid price yet.
                            elif new_price == Decimal("0") and self.state.price > Decimal("0"):
                                self.state.log(f"{Fore.YELLOW}DEBUG: 'lastPrice' was zero, but retaining previous valid price: {self.state.price:.{self.state.price_prec}f}. Raw: {received_last_price}{Style.RESET_ALL}", "debug")
                                # Keep previous non-zero price if new lastPrice is problematic
                                new_price = self.state.price

                            self.state.price = new_price
                            self.state.bid = new_bid
                            self.state.ask = new_ask
                            # --- End Robust Price Update Logic ---

                            self.state.latency = max(0, int(time.time() * 1000) - int(res.get("updatedTime", 0)))

                            if self.state.price > Decimal("0"):
                                self._update_oracle(float(self.state.price))
                            else:
                                self.state.log(f"{Fore.YELLOW}Oracle update skipped: Price is still zero.{Style.RESET_ALL}", "debug")

                        elif "orderbook" in topic:
                            data = d["data"]
                            if d.get("type") == "snapshot":
                                self.state.local_bids.clear(); self.state.local_asks.clear()
                            for p, q in data.get("b", []):
                                if safe_decimal(q) == Decimal("0"): self.state.local_bids.pop(safe_decimal(p), None)
                                else: self.state.local_bids[safe_decimal(p)] = safe_decimal(q)
                            for p, q in data.get("a", []):
                                if safe_decimal(q) == Decimal("0"): self.state.local_asks.pop(safe_decimal(p), None)
                                else: self.state.local_asks[safe_decimal(p)] = safe_decimal(q)

                            bids = sorted(self.state.local_bids.items(), reverse=True)[:15]
                            asks = sorted(self.state.local_asks.items())[:15]
                            wb = sum(float(q) / ((i+1)**2) for i, (_, q) in enumerate(bids))
                            wa = sum(float(q) / ((i+1)**2) for i, (_, q) in enumerate(asks))
                            self.state.obi_score = (wb - wa) / (wb + wa + 1e-9)

                        elif "kline" in topic:
                            k = d["data"][0]
                            if k.get("confirm"):
                                self.state.ohlc.append((float(k["open"]), float(k["high"]), float(k["low"]), float(k["close"]), float(k["volume"])))
                                # _update_oracle is called by tickers, no need to call here again for confirmed candles
            except Exception as e:
                self.state.log(f"{Fore.RED}Public WebSocket connection lost: {e}. Traceback:\n{traceback.format_exc()}{Style.RESET_ALL}", "error")
                TermuxAPI.notify("Public WS Error", f"Connection lost: {e}", id=109)
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60) # Exponential backoff, max 60s

    async def ws_nexus_private(self, stop: asyncio.Event):
        """# Establishes a secure channel for private account data (positions, wallet)."""
        self.state.log(f"{Fore.MAGENTA}# Establishing secure channel for private account data...{Style.RESET_ALL}", "info")
        reconnect_delay = 1
        while not stop.is_set():
            try:
                async with self.session.ws_connect(self.ws_priv, heartbeat=self.cfg.ws_heartbeat) as ws:
                    self.state.log(f"{Fore.GREEN}Private WebSocket connected.{Style.RESET_ALL}", "info")
                    reconnect_delay = 1 # Reset delay on successful connection
                    ts = str(int(time.time() * 1000 + 10000))
                    sig = hmac.new(API_SECRET.encode(), f"GET/realtime{ts}".encode(), hashlib.sha256).hexdigest()
                    await ws.send_json({"op": "auth", "args": [API_KEY, ts, sig]})
                    await ws.send_json({"op": "subscribe", "args": ["position", "wallet"]})
                    async for msg in ws:
                        if stop.is_set(): break
                        d = json.loads(msg.data)
                        topic = d.get("topic", "")

                        if topic == "position":
                            for p in d.get("data", []):
                                if p["symbol"] != self.cfg.symbol: continue

                                was_active = self.state.active
                                self.state.qty = safe_decimal(p["size"])
                                self.state.active = self.state.qty > Decimal("0")
                                self.state.side = p["side"] if self.state.active else "HOLD"
                                self.state.entry_p = safe_decimal(p["avgPrice"])
                                self.state.upnl = safe_decimal(p["unrealisedPnl"])

                                if not was_active and self.state.active: # Position just opened
                                    self.state.entry_ts = time.time()
                                    self.state.stage = 1 # Initial entry stage
                                    self.state.trade_count += 1 # Increment trade count on entry
                                    self.state.log(f"{Fore.GREEN}Position opened: {self.state.side} {self.state.qty} at {self.state.entry_p}.{Style.RESET_ALL}", "entry")
                                    TermuxAPI.speak(f"{self.state.side} position opened!")

                                if was_active and not self.state.active: # Position just closed
                                    self.state.last_trade_pnl = self.state.upnl # Capture PnL from the moment it was active
                                    self.state.total_realized_pnl_session += self.state.last_trade_pnl # Update total realized PnL
                                    if self.state.last_trade_pnl > Decimal("0"):
                                        self.state.wins += 1
                                        self.state.loss_streak = 0
                                        self.state.log(f"{Fore.GREEN}Trade #{self.state.trade_count} closed with PROFIT: {self.state.last_trade_pnl:+.4f} USDT.{Style.RESET_ALL}", "exit")
                                        TermuxAPI.toast(f"WIN! {self.state.last_trade_pnl:+.2f} USDT")
                                        TermuxAPI.speak("Profit!")
                                    else:
                                        self.state.loss_streak += 1
                                        self.state.log(f"{Fore.RED}Trade #{self.state.trade_count} closed with LOSS: {self.state.last_trade_pnl:+.4f} USDT. Consecutive: {self.state.loss_streak}{Style.RESET_ALL}", "exit")
                                        TermuxAPI.toast(f"LOSS! {self.state.last_trade_pnl:+.2f} USDT")
                                        TermuxAPI.speak("Loss!")
                                        if self.state.loss_streak >= self.cfg.max_consecutive_losses:
                                            self.state.stasis_until = time.time() + 600 # 10 minutes stasis
                                            self.state.log(f"{Fore.RED}Breaker: Max consecutive losses ({self.cfg.max_consecutive_losses}) reached. Entering Stasis for 10 minutes.{Style.RESET_ALL}", "error")
                                            TermuxAPI.notify("Stasis Activated", "Max consecutive losses reached.", id=110)
                                            TermuxAPI.speak("Stasis activated.")

                                    self.state.stage = 0 # Reset stage
                                    self.state.last_trade_ts = time.time() # Update last trade timestamp
                                    self.state.trailing_sl_value = Decimal("0") # Reset trailing SL value
                                    await self.update_wallet() # Refresh wallet balance after trade closure

                        elif topic == "wallet":
                            acc = d["data"][0]
                            self.state.equity = safe_decimal(acc.get("totalEquity"))
                            self.state.available = safe_decimal(acc.get("totalAvailableBalance"))

                            # Update PnL metrics
                            self.state.current_session_pnl = self.state.equity - self.state.initial_equity_session
                            self.state.current_session_pnl_pct = safe_div(self.state.current_session_pnl, self.state.initial_equity_session)

                            # Daily PnL logic (will be reset by update_wallet if date changes)
                            self.state.daily_pnl = self.state.equity - self.state.initial_equity_daily
                            self.state.daily_pnl_pct = safe_div(self.state.daily_pnl, self.state.initial_equity_daily)

                            # Check for daily profit/loss limits
                            if not self.state.daily_profit_reached and self.state.daily_pnl_pct >= self.cfg.daily_profit_target_pct:
                                self.state.daily_profit_reached = True
                                self.state.log(f"{Fore.GREEN}Daily Profit Target Reached! ({self.state.daily_pnl_pct:.2%}). Halting trading.{Style.RESET_ALL}", "info")
                                TermuxAPI.notify("Daily Profit Reached", f"Target: {self.cfg.daily_profit_target_pct:.2%}, Actual: {self.state.daily_pnl_pct:.2%}", id=111)
                                TermuxAPI.speak("Daily profit target reached!")

                            if not self.state.daily_loss_reached and self.state.daily_pnl_pct <= -self.cfg.daily_loss_limit_pct:
                                self.state.daily_loss_reached = True
                                self.state.log(f"{Fore.RED}Daily Loss Limit Reached! ({self.state.daily_pnl_pct:.2%}). Halting trading.{Style.RESET_ALL}", "error")
                                TermuxAPI.notify("Daily Loss Reached", f"Limit: {-self.cfg.daily_loss_limit_pct:.2%}, Actual: {self.state.daily_pnl_pct:.2%}", id=112)
                                TermuxAPI.speak("Daily loss limit reached!")

            except Exception as e:
                self.state.log(f"{Fore.RED}Private WebSocket connection lost: {e}. Traceback:\n{traceback.format_exc()}{Style.RESET_ALL}", "error")
                TermuxAPI.notify("Private WS Error", f"Connection lost: {e}", id=113)
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60) # Exponential backoff, max 60s

    async def _check_battery_status(self, stop: asyncio.Event):
        """# Periodically checks device battery status and issues alerts."""
        self.state.log(f"{Fore.CYAN}# Initiating battery status vigil...{Style.RESET_ALL}", "info")
        while not stop.is_set():
            status = TermuxAPI.get_battery_status()
            self.state.battery_level = status.get("percentage", -1)
            self.state.battery_status = status.get("status", "UNKNOWN")

            if self.state.battery_level != -1 and self.state.battery_level <= self.cfg.battery_alert_threshold and not self.state.battery_alert_sent:
                self.state.log(f"{Fore.RED}WARNING: Battery level critically low ({self.state.battery_level}%). Please charge device!{Style.RESET_ALL}", "error")
                TermuxAPI.notify("LOW BATTERY", f"Battery at {self.state.battery_level}%. Charge device!", id=114)
                TermuxAPI.speak("Battery critically low. Please charge device.")
                self.state.battery_alert_sent = True
            elif self.state.battery_level > self.cfg.battery_alert_threshold and self.state.battery_alert_sent:
                self.state.battery_alert_sent = False # Reset alert once battery is above threshold

            await asyncio.sleep(300) # Check every 5 minutes

# =========================
# THE NEON DASHBOARD
# =========================

def build_ui(s: SentinelState) -> Layout:
    """
    # Constructs the mystical dashboard for real-time visualization.
    # Transforms raw data into an easily digestible tapestry of insights.
    """
    l = Layout()
    l.split_column(Layout(name="top", size=3), Layout(name="mid"), Layout(name="bot", size=10))
    l["mid"].split_row(Layout(name="ora"), Layout(name="tac"))

    daily_pnl_c = "bright_green" if s.daily_pnl >= Decimal("0") else "bright_red"
    session_pnl_c = "bright_green" if s.current_session_pnl >= Decimal("0") else "bright_red"
    realized_pnl_c = "bright_green" if s.total_realized_pnl_session >= Decimal("0") else "bright_red"
    wr = (s.wins / max(1, s.trade_count) * 100)

    battery_color = "green"
    if s.battery_level <= s.config.battery_alert_threshold: battery_color = "red"
    elif s.battery_level <= s.config.battery_alert_threshold + 10: battery_color = "yellow"

    header = (
        f"[bold cyan]BCH OMNI-SENTINEL V21.3[/] | [white]Daily PnL:[/][{daily_pnl_c}]{s.daily_pnl:+.4f}[/] ([{daily_pnl_c}]{s.daily_pnl_pct:.2%}[/]) "
        f"| [white]Session PnL:[/][{session_pnl_c}]{s.current_session_pnl:+.4f}[/] | [white]WR:[/]{wr:.1f}% | [white]Lat:[/]{s.latency}ms | [white]Bat:[/][{battery_color}]{s.battery_level}%[/]"
    )
    l["top"].update(Panel(Text.from_markup(header, justify="center"), border_style="bright_blue"))

    ora = Table.grid(expand=True)
    ora.add_row("Price", f"[bold yellow]{s.price:.{s.price_prec}f}[/]")
    ora.add_row("Alpha Score", f"[bold magenta]{s.alpha_score:.1f}%[/]")
    ora.add_row("OBI score", f"[{'green' if s.obi_score > 0 else 'red'}]{s.obi_score:+.2%}[/]")
    ora.add_row("Fisher / Sig", f"{s.fisher:+.3f} / {s.fisher_sig:+.3f}")
    ora.add_row("RSI / VSI", f"{s.rsi:.1f} / {s.vsi:.2f}")
    ora.add_row("ATR / VWAP", f"{s.atr:.2f} / {s.vwap:.{s.price_prec}f}")
    ora.add_row("EMA Fast/Macro", f"{s.ema_fast:.{s.price_prec}f} / {s.ema_macro:.{s.price_prec}f}")
    l["ora"].update(Panel(ora, title="[bold cyan]The Singularity Oracle[/]", border_style="cyan"))

    tac = Table.grid(expand=True)
    if s.active:
        tac.add_row("Position", f"[bold {'green' if s.side=='Buy' else 'red'}]{s.side} {s.qty}[/]")
        tac.add_row("Entry Price", f"{s.entry_p:.{s.price_prec}f}")
        tac.add_row("uPnL", f"[{'green' if s.upnl > Decimal('0') else 'red'}]{s.upnl:+.4f}[/]")
        tac.add_row("Stage", f"[bold yellow]{s.stage}/2[/]")
        tac.add_row("Life", f"{int(time.time() - s.entry_ts)}s / {s.config.max_hold_sec}s")
        if s.trailing_sl_value > Decimal("0"):
            tac.add_row("Trail SL", f"{s.trailing_sl_value:.{s.price_prec}f}")
    else:
        status_text = "[bold green]SCANNING[/]"
        if s.stasis_until > time.time():
            status_text = "[bold red]STASIS[/]"
        elif s.daily_loss_reached or s.daily_profit_reached:
            status_text = "[bold red]HALTED[/]"

        tac.add_row("Status", status_text)
        tac.add_row("Available", f"{s.available:.2f} USDT")
        tac.add_row("Loss Streak", f"{s.loss_streak}/{s.config.max_consecutive_losses}")
        if s.stasis_until > time.time():
            tac.add_row("Recovery", f"{int(s.stasis_until - time.time())}s")
        tac.add_row("Last PnL", f"[{'green' if s.last_trade_pnl > Decimal('0') else 'red'}]{s.last_trade_pnl:+.4f}[/]")
        tac.add_row("Realized PnL", f"[{realized_pnl_c}]{s.total_realized_pnl_session:+.4f}[/]") # Added Realized PnL
        if s.config.entry_confirmation_candles > 0 and s.last_signal_direction != "NONE":
             tac.add_row("Confirm", f"[{'blue' if s.signal_confirmed_candles < s.config.entry_confirmation_candles else 'green'}]{s.last_signal_direction}: {s.signal_confirmed_candles}/{s.config.entry_confirmation_candles}[/]")
    l["tac"].update(Panel(tac, title="[bold magenta]Tactical Nexus[/]", border_style="magenta"))

    l["bot"].update(Panel("\n".join(list(s.logs)), title="[dim]Conquest Chronicles[/]"))
    return l

async def main():
    """
    # The grand orchestration of the Bybit Apex Engine.
    # Initializes components, starts the mystical streams, and manages the lifecycle.
    """
    # Acquire Termux wake lock immediately
    TermuxAPI.wake_lock()

    config = ScalperConfig.load_from_file() # Load configuration from file
    state = SentinelState(config=config)

    async with BybitApex(state) as apex:
        state.log(f"{Fore.LIGHTYELLOW_EX + Style.BRIGHT}Pyrmethus, the Termux Coding Wizard, awakens!{Style.RESET_ALL}", "info")
        state.log(f"{Fore.CYAN}Initializing BCH OMNI-SENTINEL V21.3 (Scalping Mode)...{Style.RESET_ALL}", "info")

        # --- Initial Sync Rituals ---
        await apex.boot_ritual()
        await apex.fetch_history()
        await apex.update_wallet() # This will also set initial_equity_daily and last_daily_reset_date

        stop = asyncio.Event()
        console = Console() # Initialize Rich Console
        with Live(build_ui(state), refresh_per_second=6, screen=True, console=console) as live:
            tasks = [
                asyncio.create_task(apex.ws_nexus_public(stop)),
                asyncio.create_task(apex.ws_nexus_private(stop)),
                asyncio.create_task(apex.logic_loop(stop)),
                asyncio.create_task(apex._check_battery_status(stop)) # Start battery monitoring task
            ]
            try:
                while True:
                    live.update(build_ui(state))
                    await asyncio.sleep(0.16) # ~6 updates per second
            except asyncio.CancelledError:
                state.log(f"{Fore.YELLOW}The arcane threads are being gracefully unwound...{Style.RESET_ALL}", "warn")
            except KeyboardInterrupt:
                state.log(f"{Fore.YELLOW}# The seeker has interrupted the ritual. Peace be upon your terminal.{Style.RESET_ALL}", "warn")
            except Exception as e:
                state.log(f"{Fore.RED}A critical disturbance in the ether: {e}. Traceback:\n{traceback.format_exc()}{Style.RESET_ALL}", "error")
                TermuxAPI.notify("Critical Error", f"Bot encountered a critical error: {e}", id=100)
                TermuxAPI.speak("Critical error!")
            finally:
                stop.set() # Ensure all tasks receive the stop signal
                for t in tasks:
                    if not t.done():
                        t.cancel() # Request cancellation for remaining tasks
                await asyncio.gather(*tasks, return_exceptions=True) # Await cancelled tasks to ensure cleanup
                state.log(f"{Fore.MAGENTA}Pyrmethus bids you farewell. May your digital journey be ever enlightened.{Style.RESET_ALL}", "info")
                TermuxAPI.wake_unlock() # Release Termux wake lock

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Handled within main's finally block
        pass
    except Exception as e:
        print(f"\n{Fore.RED}# An unhandled anomaly occurred in the main realm: {e}. Traceback:\n{traceback.format_exc()}{Style.RESET_ALL}")
        TermuxAPI.notify("Unhandled Error", f"Main process error: {e}", id=99)
        TermuxAPI.speak("Unhandled error in main process!")
