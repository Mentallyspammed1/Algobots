"""
BCH OMNI-SENTINEL V21.5 – THE UNYIELDING SWIFT STRIKER
Reforged by Pyrmethus the Wizard.
Status: Optimized for high-frequency, low-latency scalping with enhanced API compatibility,
        robust WebSocket data handling, true daily PnL tracking, and advanced risk controls.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import shutil  # For config backup
import socket  # For internet connection check
import time
import traceback  # Added for detailed error logging
import urllib.parse
from collections import deque
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime  # For true daily PnL reset
from datetime import timedelta  # For true daily PnL reset
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

def is_connected(host: str = "8.8.8.8", port: int = 53, timeout: int = 3) -> bool:
    """Checks for active internet connection."""
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except Exception:
        return False

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
    initial_max_leverage: int = 20 # User's configured maximum leverage
    leverage: int = 20 # Current active leverage, adjusted dynamically

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
    daily_reset_hour_utc: int = 0  # Reset daily PnL at this UTC hour (default midnight)
    leverage_adjust_cooldown_sec: int = 300 # Cooldown for dynamic leverage adjustment

    # --- Termux Specific ---
    battery_alert_threshold: int = 20 # Alert if battery drops below this percentage
    critical_battery_level: int = 10 # Enter stasis if battery drops below this

    # --- Entry Confirmation (Faster for Scalping) ---
    entry_confirmation_candles: int = 1 # Minimal confirmation for faster entries
    price_ema_proximity_pct: Decimal = Decimal("0.0002") # Price must be within 0.02% of EMA for entry

    # --- Volatility Filter ---
    min_atr_threshold: float = 0.5 # Minimum ATR to allow entries, avoid choppy markets

    # --- Bollinger Bands Filter ---
    bollinger_band_filter_enabled: bool = True # Enable/disable BBands filter for entries

    # --- Position Sizing ---
    max_position_qty_usdt: Decimal = Decimal("50.0") # Max position value in USDT to avoid overexposure

    @staticmethod
    def load_from_file(filepath: str = "config.json") -> ScalperConfig:
        """Loads configuration from a JSON file, merging with defaults and creating a backup."""
        default_config = ScalperConfig()
        try:
            if os.path.exists(filepath):
                backup_path = filepath + f".backup.{int(time.time())}"
                shutil.copy2(filepath, backup_path)
                print(f"{Fore.GREEN}# Configuration backed up to {backup_path}{Style.RESET_ALL}")

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

            # Special handling for initial_max_leverage and leverage
            if 'leverage' in filtered_data:
                filtered_data['initial_max_leverage'] = filtered_data['leverage']
            else:
                filtered_data['initial_max_leverage'] = default_config.leverage # Use default if not in file

            return ScalperConfig(**filtered_data)
        except Exception as e: # Catch all exceptions during loading and backup
            print(f"{Fore.RED}# Failed loading config with backup: {e}. Using defaults.{Style.RESET_ALL}")
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
    bollinger_upper: float = 0.0 # Added: Bollinger Bands
    bollinger_lower: float = 0.0 # Added: Bollinger Bands

    # Precision Glyphs
    price_prec: int = 2
    qty_step: Decimal = Decimal("0.01")
    min_qty: Decimal = Decimal("0.01")

    ohlc: deque[tuple[float, float, float, float, float]] = field(default_factory=lambda: deque(maxlen=400))
    ohlc_5m: deque[tuple[float, float, float, float, float]] = field(default_factory=lambda: deque(maxlen=100)) # Placeholder for 5m data

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
    api_latency: int = 0 # Added: API request latency
    last_trade_ts: float = 0.0
    stasis_until: float = 0.0 # Time until bot comes out of stasis (cooldown due to consecutive losses)
    last_leverage_adjust_ts: float = 0.0 # Cooldown for dynamic leverage adjustment

    # Termux Specific
    battery_level: int = -1
    battery_status: str = "UNKNOWN"
    battery_alert_sent: bool = False

    # Entry Confirmation
    signal_confirmed_candles: int = 0
    last_signal_direction: str = "NONE" # "BUY" or "SELL"
    signal_strength: int = 0 # Added: Signal strength for logging

    # Configuration Reload
    last_config_mod_time: float = 0.0 # For hot reloading config

    # Chronicles
    logs: deque[str] = field(default_factory=lambda: deque(maxlen=24))
    ready: bool = False

    local_bids: dict[Decimal, Decimal] = field(default_factory=dict)
    local_asks: dict[Decimal, Decimal] = field(default_factory=dict)

    def __post_init__(self):
        """Initializes log file after dataclass creation."""
        with open(LOG_FILE, "a") as f:
            f.write(f"\n--- Session Started: {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        if os.path.exists("config.json"):
            self.last_config_mod_time = os.path.getmtime("config.json")

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

    async def request(self, method: str, path: str, params: dict = None, retries: int = 3, backoff: int = 2) -> dict:
        """Sends a request to the Bybit API realm with exponential backoff and rate limit handling."""
        params = params or {}
        ts = str(int(time.time() * 1000))

        TermuxAPI.wake_lock()
        try: # Outer try block for the entire retry logic
            delay = 1
            for attempt in range(retries):
                start_time = time.time()
                try: # Inner try block for the actual request attempt
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
                        self.state.api_latency = int((time.time() - start_time) * 1000)
                        r_json = await r.json()

                        if r_json.get("retCode") == 10001: # Bybit rate limit error
                            self.state.log(f"{Fore.YELLOW}API Rate Limit Hit ({method} {path}): Backing off for {delay}s. Attempt {attempt+1}/{retries}{Style.RESET_ALL}", "warn")
                            TermuxAPI.notify("API Rate Limit", f"Hit for {path}. Backing off.", id=101)
                            await asyncio.sleep(delay)
                            delay *= backoff
                            continue # Retry

                        r.raise_for_status() # Raise for HTTP errors (4xx, 5xx)
                        self.state.log(f"# API latency: {self.state.api_latency}ms for {path}", "debug")
                        return r_json
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    self.state.log(f"{Fore.RED}API Request Failed ({method} {path}): Attempt {attempt+1}/{retries} Network error: {e}. Retrying in {delay}s.{Style.RESET_ALL}", "error")
                    await asyncio.sleep(delay)
                    delay *= backoff
                except json.JSONDecodeError:
                    self.state.log(f"{Fore.RED}API Request Failed ({method} {path}): Attempt {attempt+1}/{retries} Invalid JSON response. Retrying in {delay}s.{Style.RESET_ALL}", "error")
                    await asyncio.sleep(delay)
                    delay *= backoff
                except Exception as e:
                    self.state.log(f"{Fore.RED}API Request Failed ({method} {path}): Attempt {attempt+1}/{retries} Unexpected error: {e}. Retrying in {delay}s.{Style.RESET_ALL}", "error")
                    await asyncio.sleep(delay)
                    delay *= backoff

            self.state.log(f"{Fore.RED}API Request Failed ({method} {path}): Max retries exceeded.{Style.RESET_ALL}", "error")
            TermuxAPI.notify("Bybit API Error", f"Failed after {retries} attempts for {method} {path}", id=101)
            return {"retCode": -1, "retMsg": "Max retries exceeded"}
        finally: # This finally block is correctly associated with the outer try block
            TermuxAPI.wake_unlock()

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
            "buyLeverage": str(self.cfg.initial_max_leverage), "sellLeverage": str(self.cfg.initial_max_leverage)
        })
        if leverage_res.get("retCode") == 0:
            self.cfg.leverage = self.cfg.initial_max_leverage # Set current leverage to initial max
            self.state.log(f"{Fore.GREEN}Leverage set to {self.cfg.leverage}x.{Style.RESET_ALL}", "info")
        else:
            self.state.log(f"{Fore.RED}Failed to set leverage: {leverage_res.get('retMsg')}{Style.RESET_ALL}", "error")
            TermuxAPI.notify("Boot Ritual Failed", f"Set leverage: {leverage_res.get('retMsg')}", id=103)

        # Auto-Adjust Leverage Based on Market Volatility (Initial check)
        await self._auto_adjust_leverage()

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

        # Placeholder for 5m history (Multi-Timeframe Confluence)
        # r_5m = await self.request("GET", "/v5/market/kline", {
        #     "category": self.cfg.category, "symbol": self.cfg.symbol,
        #     "interval": "5", "limit": "50" # Example: Fetch 50 5-minute candles
        # })
        # if r_5m.get("retCode") == 0:
        #     for k_5m in reversed(r_5m["result"]["list"]):
        #         self.state.ohlc_5m.append((float(k_5m[1]), float(k_5m[2]), float(k_5m[3]), float(k_5m[4]), float(k_5m[5])))
        #     self.state.log(f"{Fore.GREEN}5m kline scrolls unveiled: {len(self.state.ohlc_5m)} candles.{Style.RESET_ALL}", "info")


    async def update_wallet(self):
        """# Updates the bot's knowledge of its financial realm, including daily PnL reset."""
        r = await self.request("GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED"})

        if r.get("retCode") == 0:
            result_data = r.get("result")
            if not result_data or not result_data.get("list") or not result_data["list"]:
                self.state.log(f"{Fore.RED}Failed to update wallet: 'result' or 'list' is empty/missing in API response. Response: {r}{Style.RESET_ALL}", "error")
                TermuxAPI.notify("Wallet Update Failed", "Empty/missing wallet data.", id=105)
                return

            acc = result_data["list"][0] # Assuming the first item in list is the unified account summary

            self.state.equity = safe_decimal(acc.get("totalEquity"))
            self.state.available = safe_decimal(acc.get("totalAvailableBalance"))

            # Initialize initial_equity_session if first run
            if self.state.initial_equity_session == Decimal("0"):
                self.state.initial_equity_session = self.state.equity

            # --- Daily PnL Reset Logic (Configurable UTC hour) ---
            current_utc = datetime.now(timezone.utc)
            current_reset_time = current_utc.replace(hour=self.cfg.daily_reset_hour_utc, minute=0, second=0, microsecond=0)

            # If current_utc is before today's reset time, the reset time should be yesterday
            if current_utc < current_reset_time:
                current_reset_time -= timedelta(days=1)

            reset_date_str = current_reset_time.strftime("%Y-%m-%d")

            if self.state.last_daily_reset_date != reset_date_str:
                self.state.log(f"{Fore.CYAN}# Daily PnL reset initiated for {reset_date_str} (UTC {self.cfg.daily_reset_hour_utc}:00).{Style.RESET_ALL}", "info")
                self.state.initial_equity_daily = self.state.equity
                self.state.daily_profit_reached = False
                self.state.daily_loss_reached = False
                self.state.last_daily_reset_date = reset_date_str
            elif self.state.initial_equity_daily == Decimal("0"): # Ensure it's set on first run of the day if not reset
                self.state.initial_equity_daily = self.state.equity

            # Update PnL metrics
            self.state.current_session_pnl = self.state.equity - self.state.initial_equity_session
            self.state.current_session_pnl_pct = safe_div(self.state.current_session_pnl, self.state.initial_equity_session)

            self.state.daily_pnl = self.state.equity - self.state.initial_equity_daily
            self.state.daily_pnl_pct = safe_div(self.state.daily_pnl, self.state.initial_equity_daily)

            self.state.log(f"{Fore.GREEN}Wallet synced. Equity: {self.state.equity:.2f} USDT. Daily PnL: {self.state.daily_pnl:+.2f}.{Style.RESET_ALL}", "info")
        else:
            self.state.log(f"{Fore.RED}Failed to update wallet: {r.get('retMsg', 'Unknown error')}. Full response: {r}{Style.RESET_ALL}", "error")
            TermuxAPI.notify("Wallet Update Failed", f"Balance: {r.get('retMsg', 'Unknown error')}", id=105)

    def _update_oracle(self, live_p: float = None):
        """
        # Weaves the threads of market data into mystical indicators.
        # Now includes ATR, Fisher, RSI, VWAP, EMAs, VSI, and Bollinger Bands.
        """
        s, cfg = self.state, self.cfg
        if len(s.ohlc) < cfg.warmup_candles + cfg.rsi_period + 20: return # Need enough for BBands (20) + RSI + 1 for diff

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

        # 6. Bollinger Bands
        window = 20
        if len(c) >= window:
            sma = np.mean(c[-window:])
            stddev = np.std(c[-window:])
            s.bollinger_upper = sma + 2 * stddev
            s.bollinger_lower = sma - 2 * stddev
        else:
            s.bollinger_upper = 0.0
            s.bollinger_lower = 0.0

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
        s.ready = len(s.ohlc) >= cfg.warmup_candles + cfg.rsi_period + 20 # Ensure enough for all indicators

    async def _auto_adjust_leverage(self):
        """Adjusts leverage dynamically based on market volatility (ATR)."""
        s, cfg = self.state, self.cfg
        if s.atr == 0: return # Cannot adjust if ATR is zero
        if (time.time() - s.last_leverage_adjust_ts) < cfg.leverage_adjust_cooldown_sec:
            return # Respect cooldown

        volatility = s.atr
        max_leverage_allowed = cfg.initial_max_leverage
        min_leverage = 5 # Minimum sensible leverage

        # Prevent too low volatility from causing huge leverage, and ensure ATR is positive
        effective_volatility = max(0.5, volatility)

        # Calculate new leverage inversely proportional to volatility
        calculated_leverage = int(max_leverage_allowed / effective_volatility)

        # Clamp between min_leverage and max_leverage_allowed
        new_lev = max(min_leverage, min(max_leverage_allowed, calculated_leverage))

        # Only send request if calculated leverage is different from the *currently applied* leverage
        if new_lev != cfg.leverage:
            res = await self.request("POST", "/v5/position/set-leverage", {
                "category": cfg.category, "symbol": cfg.symbol,
                "buyLeverage": str(new_lev), "sellLeverage": str(new_lev)
            })
            if res.get("retCode") == 0:
                cfg.leverage = new_lev # Update config's *current* leverage if successful
                s.last_leverage_adjust_ts = time.time()
                s.log(f"{Fore.GREEN}# Adjusted leverage to {new_lev}x (from {cfg.leverage}x) due to volatility {volatility:.2f}.{Style.RESET_ALL}", "info")
            else:
                s.log(f"{Fore.RED}Failed to adjust leverage: {res.get('retMsg')}{Style.RESET_ALL}", "error")

    async def confirm_order_filled(self, order_id: str, max_retries: int = 5, delay_sec: float = 0.5) -> bool:
        """Checks order status for fill, retrying up to N times."""
        s, cfg = self.state, self.cfg
        for attempt in range(max_retries):
            res = await self.request("GET", "/v5/order/realtime", {"orderId": order_id, "category": cfg.category, "symbol": cfg.symbol})
            if res.get("retCode") == 0 and res["result"]:
                order_status = res["result"].get("orderStatus")
                if order_status == "Filled":
                    s.log(f"{Fore.GREEN}Order {order_id} confirmed FILLED.{Style.RESET_ALL}", "debug")
                    return True
                if order_status in ["Cancelled", "Rejected"]:
                    s.log(f"{Fore.RED}Order {order_id} was {order_status}. Not filled.{Style.RESET_ALL}", "warn")
                    return False
            s.log(f"{Fore.YELLOW}Order {order_id} not yet filled (status: {res['result'].get('orderStatus') if res.get('result') else 'N/A'}). Retrying in {delay_sec}s...{Style.RESET_ALL}", "debug")
            await asyncio.sleep(delay_sec)
        s.log(f"{Fore.RED}Order {order_id} not confirmed filled after {max_retries} attempts.{Style.RESET_ALL}", "error")
        TermuxAPI.notify("Order Not Filled", f"Order {order_id} not confirmed filled.", id=106)
        return False

    async def strike(self, side: str, qty: Decimal, reduce: bool = False, order_type: str = "Market", price: Decimal | None = None, take_profit_price: Decimal | None = None):
        """
        # Executes a market strike (order) upon the digital battlefield.
        # Handles latency, spread, and sets initial stop loss/trailing stop.
        # Now supports Limit orders and initial Take Profit.
        """
        s, cfg = self.state, self.cfg

        if not reduce: # Entry order checks
            if order_type == "Market": # Only check for market orders
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
            "side": side, "orderType": order_type, "qty": str(quantized_qty),
            "reduceOnly": reduce
        }

        if order_type == "Limit" and price is not None:
            params["price"] = str(price.quantize(Decimal(f'1e-{s.price_prec}')))

        if not reduce: # Set initial SL and TP for entry orders
            if s.atr == 0:
                s.log(f"{Fore.RED}ATR is zero, cannot calculate initial Stop Loss. Withheld strike.{Style.RESET_ALL}", "error")
                TermuxAPI.toast("Strike withheld: ATR zero!")
                return

            sl_price = s.price - (Decimal(str(s.atr)) * cfg.sl_atr_mult) if side == 'Buy' else s.price + (Decimal(str(s.atr)) * cfg.sl_atr_mult)
            sl_price = max(Decimal("0.01"), sl_price) # Ensure SL is positive
            params["stopLoss"] = str(sl_price.quantize(Decimal(f'1e-{s.price_prec}')))

            if take_profit_price is not None:
                params["takeProfit"] = str(take_profit_price.quantize(Decimal(f'1e-{s.price_prec}')))
                s.log(f"{Fore.CYAN}# Take Profit set at {take_profit_price:.{s.price_prec}f}{Style.RESET_ALL}", "debug")

            s.log(f"{Fore.CYAN}Initiating STRIKE {side} {order_type} with Qty: {quantized_qty} and initial SL: {sl_price:.{s.price_prec}f}{Style.RESET_ALL}", "entry")
        else:
            s.log(f"{Fore.YELLOW}Executing HARVEST {side} {order_type} for Qty: {quantized_qty}{Style.RESET_ALL}", "exit")

        r = await self.request("POST", "/v5/order/create", params)
        if r.get("retCode") == 0:
            order_id = r["result"].get("orderId")
            s.log(f"{Fore.GREEN}{'HARVEST' if reduce else 'STRIKE'} {side} order placed successfully. Order ID: {order_id}{Style.RESET_ALL}", "entry" if not reduce else "exit")
            if not reduce: # For entry orders, confirm fill
                if not await self.confirm_order_filled(order_id):
                    s.log(f"{Fore.RED}Entry order {order_id} not confirmed filled. Consider manual intervention.{Style.RESET_ALL}", "error")
                    TermuxAPI.notify("Order Not Filled", f"Entry {order_id} not filled!", id=106)
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

            # Check for config reload
            await self._check_config_for_reload()

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

            # Auto-Adjust Leverage Based on Market Volatility (Periodic check)
            await self._auto_adjust_leverage()

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

        # --- Volatility Filter ---
        if s.atr < cfg.min_atr_threshold:
            s.log(f"{Fore.YELLOW}ATR ({s.atr:.2f}) below volatility threshold ({cfg.min_atr_threshold}). Skipping entry.{Style.RESET_ALL}", "warn")
            return

        # Reset confirmation if signal changes or is lost
        current_signal_direction = "NONE"

        # Check price proximity to EMA_fast for scalping entries
        price_proximity_ok = safe_div(abs(s.price - s.ema_fast), s.ema_fast) < cfg.price_ema_proximity_pct

        # --- Bollinger Bands Filter (Prevent entries near bands extremes) ---
        bollinger_filter_ok = True
        if cfg.bollinger_band_filter_enabled and s.bollinger_upper > 0 and s.bollinger_lower > 0:
            if s.price > s.bollinger_upper * 0.999 and s.fisher > 0: # Price near upper band for long signal
                bollinger_filter_ok = False
                s.log(f"{Fore.YELLOW}Price near upper Bollinger Band ({s.bollinger_upper:.2f}) for long signal. Filtering.{Style.RESET_ALL}", "debug")
            elif s.price < s.bollinger_lower * 1.001 and s.fisher < 0: # Price near lower band for short signal
                bollinger_filter_ok = False
                s.log(f"{Fore.YELLOW}Price near lower Bollinger Band ({s.bollinger_lower:.2f}) for short signal. Filtering.{Style.RESET_ALL}", "debug")

        if not bollinger_filter_ok:
            s.signal_confirmed_candles = 0 # Reset confirmation if BBands filter active
            s.last_signal_direction = "NONE"
            return

        # --- EMA Cross Confirmation ---
        ema_cross_long = s.ema_fast > s.ema_macro and safe_div(s.ema_fast - s.ema_macro, s.ema_macro) > Decimal("0.0001")
        ema_cross_short = s.ema_fast < s.ema_macro and safe_div(s.ema_macro - s.ema_fast, s.ema_macro) > Decimal("0.0001")

        if s.alpha_score >= cfg.min_alpha_score and price_proximity_ok:
            long_condition = (s.fisher > s.fisher_sig and s.price <= s.ema_fast * Decimal("1.0005") and s.rsi < 60 and ema_cross_long)
            short_condition = (s.fisher < s.fisher_sig and s.price >= s.ema_fast * Decimal("0.9995") and s.rsi > 40 and ema_cross_short)
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
        s.signal_strength = min(100, int(s.alpha_score)) # Capped to 100% for display
        s.log(f"{Fore.BLUE}Signal '{current_signal_direction}' strength: {s.signal_strength}% confirmed: {s.signal_confirmed_candles}/{cfg.entry_confirmation_candles} candles.{Style.RESET_ALL}", "debug")

        if s.signal_confirmed_candles < cfg.entry_confirmation_candles:
            return # Await further confirmation

        # Signal confirmed, proceed with strike
        sl_dist = Decimal(str(s.atr * float(cfg.sl_atr_mult)))
        if sl_dist == Decimal("0"):
            s.log(f"{Fore.RED}ATR is zero, cannot calculate SL distance for entry. Skipping strike.{Style.RESET_ALL}", "error")
            return

        # --- Dynamic Risk Adjustment Based on Recent Win Rate ---
        win_rate = safe_div(Decimal(s.wins), Decimal(s.trade_count), Decimal("0.5")) # Default to 50% if no trades
        adjusted_risk_pct = cfg.risk_per_trade_pct
        if win_rate > Decimal("0.7"): # Example: increase risk if win rate > 70%
            adjusted_risk_pct = cfg.risk_per_trade_pct * Decimal("1.5")
            s.log(f"{Fore.GREEN}Win rate high ({win_rate:.1%}), adjusting risk to {adjusted_risk_pct:.3%}.{Style.RESET_ALL}", "debug")
        elif win_rate < Decimal("0.4"): # Example: decrease risk if win rate < 40%
            adjusted_risk_pct = cfg.risk_per_trade_pct * Decimal("0.7")
            s.log(f"{Fore.YELLOW}Win rate low ({win_rate:.1%}), adjusting risk to {adjusted_risk_pct:.3%}.{Style.RESET_ALL}", "debug")

        # Calculate quantity based on adjusted risk percentage of available balance
        risk_usdt = s.available * adjusted_risk_pct
        qty = safe_div(risk_usdt, sl_dist) * Decimal(str(cfg.leverage)) # Factor in leverage for position size
        qty = qty.quantize(s.qty_step, ROUND_DOWN)

        # --- Limit Maximum Position Size ---
        max_qty_usdt = cfg.max_position_qty_usdt
        current_position_value = qty * s.price
        if current_position_value > max_qty_usdt:
            qty = (max_qty_usdt / s.price).quantize(s.qty_step, ROUND_DOWN)
            s.log(f"{Fore.YELLOW}Quantity limited to {qty} to respect max position value {max_qty_usdt} USDT.{Style.RESET_ALL}", "warn")

        if qty < s.min_qty:
            s.log(f"{Fore.YELLOW}Calculated quantity {qty} is below minimum {s.min_qty}. Skipping entry.{Style.RESET_ALL}", "warn")
            return

        # Calculate Take Profit Price for initial order
        tp_price = None
        if current_signal_direction == "BUY":
            tp_price = s.price + (Decimal(str(s.atr)) * cfg.tp_partial_atr_mult)
        else: # SELL
            tp_price = s.price - (Decimal(str(s.atr)) * cfg.tp_partial_atr_mult)
        tp_price = max(Decimal("0.01"), tp_price) # Ensure TP is positive

        if current_signal_direction == "BUY":
            s.log(f"{Fore.BLUE}Long entry signal CONFIRMED! Alpha: {s.alpha_score:.1f}, Fisher: {s.fisher:.3f}, RSI: {s.rsi:.1f}. Preparing strike.{Style.RESET_ALL}", "info")
            await self.strike("Buy", qty, order_type="Market", take_profit_price=tp_price)
        elif current_signal_direction == "SELL":
            s.log(f"{Fore.BLUE}Short entry signal CONFIRMED! Alpha: {s.alpha_score:.1f}, Fisher: {s.fisher:.3f}, RSI: {s.rsi:.1f}. Preparing strike.{Style.RESET_ALL}", "info")
            await self.strike("Sell", qty, order_type="Market", take_profit_price=tp_price)

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
                                elif isinstance(d["data"], dict): # Handle direct dict for 'data'
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
        """# Periodically checks device battery status and issues alerts, including critical stasis."""
        self.state.log(f"{Fore.CYAN}# Initiating battery status vigil...{Style.RESET_ALL}", "info")
        while not stop.is_set():
            status = TermuxAPI.get_battery_status()
            self.state.battery_level = status.get("percentage", -1)
            self.state.battery_status = status.get("status", "UNKNOWN")

            if self.state.battery_level != -1:
                if self.state.battery_level <= self.cfg.critical_battery_level:
                    if not self.state.stasis_until or self.state.stasis_until < time.time():
                        self.state.stasis_until = time.time() + 3600 # Pause 1 hour
                        self.state.log(f"{Fore.RED}CRITICAL: Battery level at {self.state.battery_level}%. Entering stasis for 1 hour.{Style.RESET_ALL}", "error")
                        TermuxAPI.notify("Battery Critical", f"Trading paused due to {self.state.battery_level}% battery", id=115)
                        TermuxAPI.speak("Critical battery level. Trading paused.")
                elif self.state.battery_level <= self.cfg.battery_alert_threshold and not self.state.battery_alert_sent:
                    self.state.log(f"{Fore.RED}WARNING: Battery level critically low ({self.state.battery_level}%). Please charge device!{Style.RESET_ALL}", "error")
                    TermuxAPI.notify("LOW BATTERY", f"Battery at {self.state.battery_level}%. Charge device!", id=114)
                    TermuxAPI.speak("Battery critically low. Please charge device.")
                    self.state.battery_alert_sent = True
                elif self.state.battery_level > self.cfg.battery_alert_threshold and self.state.battery_alert_sent:
                    self.state.battery_alert_sent = False # Reset alert once battery is above threshold

            await asyncio.sleep(300) # Check every 5 minutes

    async def _check_config_for_reload(self):
        """# Periodically checks if config.json has been modified and reloads it."""
        config_filepath = "config.json"
        if os.path.exists(config_filepath):
            current_mod_time = os.path.getmtime(config_filepath)
            if current_mod_time > self.state.last_config_mod_time:
                self.state.log(f"{Fore.YELLOW}# config.json modified. Attempting hot reload...{Style.RESET_ALL}", "warn")
                new_config = ScalperConfig.load_from_file(config_filepath)
                if new_config:
                    # Preserve initial_max_leverage from original config
                    new_config.initial_max_leverage = self.cfg.initial_max_leverage
                    self.state.config = new_config
                    self.state.last_config_mod_time = current_mod_time
                    self.state.log(f"{Fore.GREEN}# Configuration successfully reloaded.{Style.RESET_ALL}", "info")
                    # Re-apply leverage if it changed
                    if new_config.leverage != self.cfg.leverage:
                        await self.request("POST", "/v5/position/set-leverage", {
                            "category": new_config.category, "symbol": new_config.symbol,
                            "buyLeverage": str(new_config.leverage), "sellLeverage": str(new_config.leverage)
                        })
                        self.state.log(f"{Fore.GREEN}Leverage updated to {new_config.leverage}x via hot reload.{Style.RESET_ALL}", "info")
                else:
                    self.state.log(f"{Fore.RED}# Failed to reload config.json. Continuing with old config.{Style.RESET_ALL}", "error")
        await asyncio.sleep(10) # Check every 10 seconds

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
    if s.battery_level <= s.config.critical_battery_level: battery_color = "red"
    elif s.battery_level <= s.config.battery_alert_threshold: battery_color = "yellow"
    else: battery_color = "green"

    header = (
        f"[bold cyan]BCH OMNI-SENTINEL V21.5[/] | [white]Daily PnL:[/][{daily_pnl_c}]{s.daily_pnl:+.4f}[/] ([{daily_pnl_c}]{s.daily_pnl_pct:.2%}[/]) "
        f"| [white]Session PnL:[/][{session_pnl_c}]{s.current_session_pnl:+.4f}[/] | [white]WR:[/]{wr:.1f}% | [white]Lat:[/]{s.latency}ms | [white]API Lat:[/]{s.api_latency}ms | [white]Bat:[/][{battery_color}]{s.battery_level}%[/] | [white]Lev:[/]{s.config.leverage}x"
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
    ora.add_row("BBands Upper/Lower", f"{s.bollinger_upper:.{s.price_prec}f} / {s.bollinger_lower:.{s.price_prec}f}")
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
             tac.add_row("Confirm", f"[{'blue' if s.signal_confirmed_candles < s.config.entry_confirmation_candles else 'green'}]{s.last_signal_direction}: {s.signal_confirmed_candles}/{s.config.entry_confirmation_candles} (Str: {s.signal_strength}%)[/]")
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
        state.log(f"{Fore.CYAN}Initializing BCH OMNI-SENTINEL V21.5 (Scalping Mode)...{Style.RESET_ALL}", "info")

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
                asyncio.create_task(apex._check_battery_status(stop)), # Start battery monitoring task
                asyncio.create_task(apex._check_config_for_reload()) # Start config hot reload task
            ]

            # Watchdog for internet connection
            async def internet_watchdog():
                while not stop.is_set():
                    if not is_connected():
                        state.log(f"{Fore.RED}# Network disconnected - pausing trading and WS connections.{Style.RESET_ALL}", "error")
                        TermuxAPI.toast("Network lost – halting trades")
                        TermuxAPI.notify("Network Disconnected", "Trading paused until reconnection.", id=116)
                        # Attempt to gracefully close WS connections if possible
                        # For now, just pause and let WS tasks handle their own reconnect logic
                        await asyncio.sleep(10) # Wait before re-checking
                    await asyncio.sleep(5) # Check every 5 seconds
            tasks.append(asyncio.create_task(internet_watchdog()))

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
