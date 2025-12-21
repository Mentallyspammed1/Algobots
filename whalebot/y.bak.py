"""
BCH OMNI-SENTINEL V22.3 – THE RESILIENT QUASAR (Format Preservation Upgrade)
Refactored for improved robustness and resilience while preserving the V22.2 structure.
"""

from __future__ import annotations
import os
import asyncio
import hmac
import hashlib
import json
import time
import urllib.parse
import traceback
import socket
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from collections import deque
from decimal import Decimal, ROUND_DOWN, getcontext, InvalidOperation
from typing import Any, Optional, Deque, Tuple, List, Dict

import aiohttp
import numpy as np
import shutil

try:
    import pandas as pd
except ImportError:
    pd = None

from colorama import Fore, Style
from dotenv import load_dotenv
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.markup import escape

# Initialize the Primal Glow for Colorama
try:
    from colorama import init

    init(autoreset=True)
except ImportError:
    pass

# Set precision for the digital loom
getcontext().prec = 28

# Load Vault Credentials
load_dotenv()
API_KEY = os.getenv("BYBIT_API_KEY", "")
API_SECRET = os.getenv("BYBIT_API_SECRET", "")
IS_TESTNET = os.getenv("BYBIT_TESTNET", "false").lower() == "true"
LOG_FILE = "bot.log"

# =========================
# HELPER INCANTATIONS
# =========================


def safe_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    """Converts a value to Decimal, logs upon failure, for safer numeric operations."""
    if value is None or value == "" or value is False:
        return default
    try:
        return Decimal(str(value))
    except InvalidOperation as e:
        # Log precise conversion failure for debugging
        print(f"[WARN] Decimal conversion failed for value '{value}': {e}")
        return default


def quantize_step(value: Decimal, step: Decimal) -> Decimal:
    """Quantizes a Decimal value to the nearest step, rounding down."""
    if step == Decimal("0"):
        return value
    return (value // step) * step


def safe_div(
    numerator: Decimal, denominator: Decimal, default: Decimal = Decimal("0")
) -> Decimal:
    try:
        if denominator == Decimal("0"):
            raise ZeroDivisionError("Denominator is zero")
        return numerator / denominator
    except ZeroDivisionError as e:
        print(f"[WARN] Safe division failed: {e}")
        return default


def quantize_to_step(value: Decimal, step: Decimal) -> Decimal:
    """
    Quantize value to the nearest multiple of step, rounding down.
    Handles arbitrary step like 0.001, 0.0005 etc safely.
    """
    if step <= 0:
        return value
    # Normalize to integer space, then back
    scaled = (value / step).to_integral_value(rounding=ROUND_DOWN)
    return (scaled * step).normalize()


def calculate_atr(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int
) -> float:
    if len(close) <= period + 1:
        return 0.0
    tr_list = np.maximum.reduce(
        [
            high[1:] - low[1:],
            np.abs(high[1:] - close[:-1]),
            np.abs(low[1:] - close[:-1]),
        ]
    )
    atr = np.empty_like(tr_list)
    atr[0] = np.mean(tr_list[:period])
    for i in range(1, len(tr_list)):
        atr[i] = (atr[i - 1] * (period - 1) + tr_list[i]) / period
    return float(atr[-1])


def calculate_dynamic_qty(
    available: Decimal,
    risk_pct: Decimal,
    atr: float,
    price: Decimal,
    leverage: int,
    qty_step: Decimal,
) -> Decimal:
    """Computes position size based on current volatility (ATR) and risk parameters dynamically."""
    if atr <= 0 or price <= 0:
        return Decimal("0")
    sl_dist = Decimal(str(atr))  # Stop loss distance in price units
    risk_usdt = available * risk_pct
    raw_qty = (risk_usdt / sl_dist) * Decimal(leverage)
    quantized_qty = quantize_to_step(raw_qty, qty_step)
    return quantized_qty


def is_connected(host: str = "8.8.8.8", port: int = 53, timeout: int = 3) -> bool:
    """Checks for active internet connection."""
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except Exception:
        return False


@dataclass(slots=True)
class SmoothedPnL:
    window: int = 5
    values: Deque[Decimal] = field(default_factory=lambda: deque(maxlen=5))

    def push(self, val: Decimal):
        self.values.append(val)

    def average(self) -> Decimal:
        if not self.values:
            return Decimal("0")
        return sum(self.values) / Decimal(len(self.values))


def confirm_signal(state: SentinelState, direction: str, required_candles: int) -> bool:
    """
    Confirm signal only if price movement aligns and volume supports it.
    Also updates a simple signal_strength metric (0–100).
    """
    if required_candles <= 0:
        state.signal_strength = 100
        return True

    if len(state.ohlc) < required_candles:
        state.signal_confirmed_candles = 0
        state.signal_strength = 0
        return False

    last_candle = state.ohlc[-1]
    open_p, close_p, volume = last_candle[0], last_candle[3], last_candle[4]
    recent = list(state.ohlc)[-required_candles:]
    avg_vol = np.mean([c[4] for c in recent])

    progressed = False
    if direction == "BUY" and close_p > open_p and volume > avg_vol:
        state.signal_confirmed_candles += 1
        progressed = True
    elif direction == "SELL" and close_p < open_p and volume > avg_vol:
        state.signal_confirmed_candles += 1
        progressed = True
    else:
        state.signal_confirmed_candles = 0

    # Clamp and compute strength
    state.signal_confirmed_candles = min(
        state.signal_confirmed_candles, required_candles
    )
    state.signal_strength = int(100 * state.signal_confirmed_candles / required_candles)
    return progressed and state.signal_confirmed_candles >= required_candles


def _effective_win_rate(trades: int, wins: int) -> Decimal:
    # Laplace smoothing: prior 50% over 4 trades
    return safe_div(
        Decimal(wins + 2),
        Decimal(trades + 4),
        Decimal("0.5"),
    )


# =========================
# TERMUX NATIVE WARDS
# =========================


class TermuxAPI:
    # ... (TermuxAPI class content remains unchanged) ...
    @staticmethod
    def toast(msg: str, short: bool = True):
        """Casts a transient notification (toast) on the Android device."""
        duration = "short" if short else "long"
        os.system(
            f"termux-toast -b '#00FFFF' -c '#000000' -g top {duration} "
            f"'{msg}' &"
        )

    @staticmethod
    def notify(title: str, msg: str, id: int = 12):
        """Summons a persistent notification in the Android notification shade."""
        # Escape single quotes in title and msg to prevent shell argument parsing issues
        escaped_title = title.replace("'", "'\\''")
        escaped_msg = msg.replace("'", "'\\''")
        os.system(f"termux-notification -t '{escaped_title}' -c '{escaped_msg}' &")

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
    def get_battery_status() -> Dict[str, Any]:
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
    initial_max_leverage: int = 35
    leverage: int = 35

    # --- The Sentinel's Vows (Tighter for Scalping) ---
    max_latency_ms: int = 300
    max_spread_pct: Decimal = Decimal("0.0005")
    max_hold_sec: int = 30

    # --- Capital Management (Adjusted for Scalping) ---
    risk_per_trade_pct: Decimal = Decimal("0.01")
    sl_atr_mult: Decimal = Decimal("0.5")
    tp_partial_atr_mult: Decimal = Decimal("0.2")
    trail_atr_mult: Decimal = Decimal("0.3")

    # --- Confluence Thresholds (Adjusted for Scalping) ---
    min_alpha_score: float = 60.0
    vsi_threshold: float = 1.0
    rsi_period: int = 5

    # --- Circuit Breakers ---
    max_consecutive_losses: int = 3
    stasis_duration_sec: int = 300
    daily_profit_target_pct: Decimal = Decimal("0.25")
    daily_loss_limit_pct: Decimal = Decimal("0.10")
    close_on_daily_limit: bool = True
    max_daily_trades: int = 500

    # --- Temporal Rhythms (Faster for Scalping) ---
    kline_interval: str = "1"
    cooldown_base: int = 0.2
    warmup_candles: int = 100
    ws_heartbeat: int = 20
    daily_reset_hour_utc: int = 0
    leverage_adjust_cooldown_sec: int = 120

    # --- Termux Specific ---
    battery_alert_threshold: int = 20
    critical_battery_level: int = 10

    # --- Entry Confirmation ---
    entry_confirmation_candles: int = 0
    price_ema_proximity_pct: Decimal = Decimal("0.0003")

    # --- Volatility Filter ---
    min_atr_threshold: float = 0.3
    atr_ewma_span: int = 10

    # --- Bollinger Bands Filter ---
    bollinger_band_filter_enabled: bool = True
    bollinger_band_strategy: str = "mean_reversion"
    bollinger_std_dev_mult: float = 2.0
    bollinger_window: int = 20

    # --- Position Sizing ---
    max_position_qty_usdt: Decimal = Decimal("200.0")
    min_dynamic_leverage: int = 5

    # --- Dynamic Risk Adjustment (DRM) ---
    dynamic_risk_win_rate_threshold: float = 0.60
    dynamic_risk_multiplier_high_win_rate: Decimal = Decimal("1.2")
    dynamic_risk_multiplier_low_win_rate: Decimal = Decimal("0.8")

    low_volatility_risk_multiplier: Decimal = Decimal("0.7")
    low_vol_atr_threshold: float = 0.4

    # --- Ehlers Indicators Config (NEW) ---
    superpass_period: int = 10

    @staticmethod
    def load_from_file(filepath: str = "config.json") -> ScalperConfig:
        # ... (load_from_file content remains unchanged) ...
        default_config = ScalperConfig()
        try:
            if os.path.exists(filepath):
                backup_path = filepath + f".backup.{int(time.time())}"
                shutil.copy2(filepath, backup_path)
                print(
                    f"{Fore.GREEN}# Configuration backed up to {backup_path}{Style.RESET_ALL}"
                )

            with open(filepath, "r") as f:
                data = json.load(f)

            filtered_data = {}
            for key, value in data.items():
                default_val = getattr(default_config, key, None)
                if default_val is None:
                    print(
                        f"{Fore.YELLOW}# Warning: Unknown configuration key '{key}' in config.json. Ignoring.{Style.RESET_ALL}"
                    )
                    continue

                if isinstance(default_val, Decimal):
                    filtered_data[key] = safe_decimal(value)
                elif isinstance(default_val, float):
                    filtered_data[key] = (
                        float(value) if value is not None else default_val
                    )
                elif isinstance(default_val, int):
                    filtered_data[key] = (
                        int(value) if value is not None else default_val
                    )
                elif isinstance(default_val, bool):
                    filtered_data[key] = (
                        bool(value) if value is not None else default_val
                    )
                else:  # string
                    filtered_data[key] = str(value)

            if "leverage" in filtered_data:
                filtered_data["initial_max_leverage"] = filtered_data["leverage"]
            else:
                filtered_data["initial_max_leverage"] = default_config.leverage

            return ScalperConfig(**filtered_data)
        except Exception as e:
            print(
                f"{Fore.RED}# Failed loading config with backup: {e}. Using defaults.{Style.RESET_ALL}"
            )
            return default_config


@dataclass
class SentinelState:
    """The repository of the bot's current state and mystical insights."""

    config: ScalperConfig = field()

    # Vault Essence
    equity: Decimal = Decimal("0")
    available: Decimal = Decimal("0")
    initial_equity_session: Decimal = Decimal("0")
    initial_equity_daily: Decimal = Decimal("0")
    last_daily_reset_date: str = ""
    current_session_pnl: Decimal = Decimal("0")
    current_session_pnl_pct: Decimal = Decimal("0")
    daily_pnl: Decimal = Decimal("0")
    daily_pnl_pct: Decimal = Decimal("0")
    daily_profit_reached: bool = False
    daily_loss_reached: bool = False
    total_realized_pnl_session: Decimal = Decimal("0")
    smoothed_realized_pnl: SmoothedPnL = field(default_factory=SmoothedPnL)

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
    fisher: float = 0.0
    fisher_sig: float = 0.0
    alpha_score: float = 0.0
    vsi: float = 1.0
    bollinger_upper: float = 0.0
    bollinger_lower: float = 0.0
    bollinger_width_pct: float = 0.0

    # Ehlers Specific
    superpass_signal: float = 0.0
    trend_signal: float = 0.0  # (0=Down, 1=Up)
    cycle_period: float = 0.0  # (Estimated)

    # Precision Glyphs
    price_prec: int = 2
    qty_step: Decimal = Decimal("0.01")
    min_qty: Decimal = Decimal("0.01")

    # Data Buffers
    ohlc: Deque[Tuple[float, float, float, float, float]] = field(
        default_factory=lambda: deque(maxlen=400)
    )
    ohlc_5m: Deque[Tuple[float, float, float, float, float]] = field(
        default_factory=lambda: deque(maxlen=100)
    )

    # Position Realm
    active: bool = False
    side: str = "HOLD"
    qty: Decimal = Decimal("0")
    entry_p: Decimal = Decimal("0")
    upnl: Decimal = Decimal("0")
    last_trade_pnl: Decimal = Decimal("0")
    entry_ts: float = 0.0
    stage: int = 0
    trailing_sl_value: Decimal = Decimal("0")

    # Ledger & Timing
    trade_count: int = 0
    wins: int = 0
    loss_streak: int = 0
    latency: int = 0
    api_latency: int = 0
    last_trade_ts: float = 0.0
    stasis_until: float = 0.0
    stasis_reason: str = "NONE"
    last_leverage_adjust_ts: float = 0.0

    # Termux Specific
    battery_level: int = -1
    battery_status: str = "UNKNOWN"
    battery_alert_sent: bool = False

    # Entry Confirmation
    signal_confirmed_candles: int = 0
    last_signal_direction: str = "NONE"
    signal_strength: int = 0

    # Configuration Reload
    last_config_mod_time: float = 0.0

    # Chronicles
    chronicles: Deque[str] = field(default_factory=lambda: deque(maxlen=24))
    ready: bool = False

    local_bids: Dict[Decimal, Decimal] = field(default_factory=dict)
    local_asks: Dict[Decimal, Decimal] = field(default_factory=dict)

    def __post_init__(self):
        """Initializes log file after dataclass creation."""
        with open(LOG_FILE, "a") as f:
            f.write(
                f"\n--- Session Started: {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n"
            )
        if os.path.exists("config.json"):
            self.last_config_mod_time = os.path.getmtime("config.json")

    def log(self, msg: str, level: str = "info") -> None:
        """Records a message in the chronicle with a timestamp and style, and writes to file."""
        ts_str = time.strftime("%H:%M:%S")

        styles = {
            "info": "white",
            "entry": "bold green",
            "exit": "bold magenta",
            "warn": "bold yellow",
            "error": "bold red",
            "debug": "dim white",
            "health": "cyan",
        }

        escaped_msg = escape(msg)
        style_name = styles.get(level, "white")

        # Correct rich markup: [style]...[/style]
        colored_msg = f"[{style_name}]{escaped_msg}[/{style_name}]"

        self.chronicles.append(colored_msg)

        clean_msg = (
            f"{ts_str} [{level.upper()}] {msg.replace('[', '<').replace(']', '>')}"
        )
        with open(LOG_FILE, "a") as f:
            f.write(clean_msg + "\n")

    def in_stasis(self) -> bool:
        now = time.time()
        if self.stasis_until > now:
            return True
        return False


from rich.markup import escape

# ...


# =========================
# THE APEX V22 ENGINE
# =========================


class BybitApex:
    def __init__(self, state: SentinelState):
        self.state = state
        self.cfg = state.config
        self.base = (
            "https://api-testnet.bybit.com" if IS_TESTNET else "https://api.bybit.com"
        )
        self.ws_pub = "wss://stream.bybit.com/v5/public/linear"
        self.ws_priv = "wss://stream.bybit.com/v5/private"
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        """Establishes the ethereal connection (aiohttp session)."""
        conn = aiohttp.TCPConnector(limit=15, ttl_dns_cache=360)
        self.session = aiohttp.ClientSession(
            connector=conn, timeout=aiohttp.ClientTimeout(total=15)
        )
        return self

    async def __aexit__(self, *args):
        """Severs the ethereal connection upon exit."""
        if self.session:
            await self.session.close()

    def _sign(self, payload: str, ts: str) -> str:
        """Forges the digital signature for API requests."""
        param_str = ts + API_KEY + "5000" + payload
        return hmac.new(
            API_SECRET.encode(), param_str.encode(), hashlib.sha256
        ).hexdigest()

    async def request(
        self,
        method: str,
        path: str,
        params: dict = None,
        retries: int = 3,
        backoff: int = 2,
    ) -> dict:
        """Sends a request to the Bybit API realm with exponential backoff and rate limit handling."""
        params = params or {}
        ts = str(int(time.time() * 1000))

        TermuxAPI.wake_lock()
        try:
            delay = 1
            for attempt in range(retries):
                start_time = time.time()
                try:
                    if method == "GET":
                        query = urllib.parse.urlencode(sorted(params.items()))
                        payload, url = query, f"{self.base}{path}?{query}"
                    else:
                        payload = json.dumps(params, separators=(",", ":"))
                        url = f"{self.base}{path}"

                    headers = {
                        "X-BAPI-API-KEY": API_KEY,
                        "X-BAPI-SIGN": self._sign(payload, ts),
                        "X-BAPI-TIMESTAMP": ts,
                        "X-BAPI-RECV-WINDOW": "5000",
                        "Content-Type": "application/json",
                    }
                    async with self.session.request(
                        method,
                        url,
                        headers=headers,
                        data=None if method == "GET" else payload,
                    ) as r:
                        self.state.api_latency = int((time.time() - start_time) * 1000)
                        r_json = await r.json()

                        if r_json.get("retCode") == 10001:
                            self.state.log(
                                f"{Fore.YELLOW}API Rate Limit Hit ({method} {path}): "
                                f"Backing off for {delay}s. Attempt {attempt+1}/{retries}"
                                f"{Style.RESET_ALL}",
                                "warn",
                            )
                            TermuxAPI.notify(
                                "API Rate Limit",
                                f"Hit for {path}. Backing off.",
                                id=101,
                            )
                            await asyncio.sleep(delay)
                            delay *= backoff
                            continue

                        r.raise_for_status()
                        self.state.log(
                            f"# API latency: {self.state.api_latency}ms for {path}",
                            "debug",
                        )
                        return r_json
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    self._report_error(
                        f"Network Error on {method} {path}: {e}", "error", 101
                    )
                    await asyncio.sleep(delay)
                    delay *= backoff
                except json.JSONDecodeError:
                    self._report_error(
                        f"Invalid JSON response on {method} {path}", "error", 101
                    )
                    await asyncio.sleep(delay)
                    delay *= backoff
                except Exception as e:
                    self._report_error(
                        f"Unexpected Error on {method} {path}: {e}", "error", 101
                    )
                    await asyncio.sleep(delay)
                    delay *= backoff

            self._report_error(
                f"Max retries exceeded for {method} {path}", "error", 101
            )
            return {"retCode": -1, "retMsg": "Max retries exceeded"}
        finally:
            TermuxAPI.wake_unlock()

    def _report_error(self, msg: str, level: str, notify_id: int):
        """Unified error logging and notification utility (Improvement 13)."""
        self.state.log(f"{Fore.RED}{msg}{Style.RESET_ALL}", level)
        TermuxAPI.notify("Bybit API Error", msg, id=notify_id)

    async def boot_ritual(self):
        """# Performs initial synchronization rituals: instrument info and leverage setting."""
        self.state.log(
            f"{Fore.CYAN}# Syncing Instrument Ritual...{Style.RESET_ALL}", "health"
        )
        r = await self.request(
            "GET",
            "/v5/market/instruments-info",
            {"category": self.cfg.category, "symbol": self.cfg.symbol},
        )
        if r.get("retCode") == 0:
            i = r["result"]["list"][0]
            tick = Decimal(i["priceFilter"]["tickSize"])
            self.state.price_prec = abs(tick.normalize().as_tuple().exponent)

            # Improvement 1: Robust lot filter check
            lot_filter_data = i.get("lotFilter") or i.get("lotSizeFilter")

            if lot_filter_data:
                self.state.qty_step = Decimal(lot_filter_data["qtyStep"])
                self.state.min_qty = Decimal(lot_filter_data["minOrderQty"])
                self.state.log(
                    f"{Fore.GREEN}Instrument info synced. Price prec: "
                    f"{self.state.price_prec}, Qty step: {self.state.qty_step}."
                    f"{Style.RESET_ALL}",
                    "info",
                )
            else:
                self._report_error(
                    "Missing lot filter info in API response.", "error", 102
                )

        else:
            self._report_error(
                f"Failed to sync instrument info: {r.get('retMsg')}", "error", 102
            )

        # Set leverage
        leverage_res = await self.request(
            "POST",
            "/v5/position/set-leverage",
            {
                "category": self.cfg.category,
                "symbol": self.cfg.symbol,
                "buyLeverage": str(self.cfg.initial_max_leverage),
                "sellLeverage": str(self.cfg.initial_max_leverage),
            },
        )
        if leverage_res.get("retCode") == 0:
            self.cfg.leverage = self.cfg.initial_max_leverage
            self.state.log(
                f"{Fore.GREEN}Leverage set to {self.cfg.leverage}x.{Style.RESET_ALL}",
                "info",
            )
        else:
            self._report_error(
                f"Failed to set leverage: {leverage_res.get('retMsg')}", "error", 103
            )

        await self._auto_adjust_leverage()

        # Improvement 5: Retry wallet update on initial boot (Improvement 5)
        for _ in range(3):
            await self.update_wallet()
            if self.state.initial_equity_session > Decimal("0"):
                break
            await asyncio.sleep(1)

    async def fetch_history(self):
        """# Summons ancient kline scrolls to warm up the oracle's vision."""
        self.state.log(
            f"{Fore.CYAN}# Summoning ancient kline scrolls...{Style.RESET_ALL}",
            "health",
        )

        # Fetch main interval history
        limit = max(
            self.cfg.warmup_candles + 20,
            self.cfg.rsi_period + self.cfg.bollinger_window + 20,
        )
        r = await self.request(
            "GET",
            "/v5/market/kline",
            {
                "category": self.cfg.category,
                "symbol": self.cfg.symbol,
                "interval": self.cfg.kline_interval,
                "limit": str(limit),
            },
        )
        if r.get("retCode") == 0:
            for k in reversed(r["result"]["list"]):
                self.state.ohlc.append(
                    (float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5]))
                )
            self.state.log(
                f"{Fore.GREEN}Kline scrolls unveiled: {len(self.state.ohlc)} candles.{Style.RESET_ALL}",
                "info",
            )
            self._update_oracle()

        # Fetch 5m history
        r_5m = await self.request(
            "GET",
            "/v5/market/kline",
            {
                "category": self.cfg.category,
                "symbol": self.cfg.symbol,
                "interval": "5",
                "limit": "50",
            },
        )
        if r_5m.get("retCode") == 0:
            for k_5m in reversed(r_5m["result"]["list"]):
                self.state.ohlc_5m.append(
                    (
                        float(k_5m[1]),
                        float(k_5m[2]),
                        float(k_5m[3]),
                        float(k_5m[4]),
                        float(k_5m[5]),
                    )
                )
            self.state.log(
                f"{Fore.GREEN}5m kline scrolls unveiled: {len(self.state.ohlc_5m)} candles.{Style.RESET_ALL}",
                "info",
            )

    async def update_wallet(self):
        """# Updates wallet, PnL, and handles Daily PnL Reset (Improvement 4)."""
        r = await self.request(
            "GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED"}
        )

        if r.get("retCode") == 0:
            acc = r.get("result", {}).get("list", [{}])[0]

            self.state.equity = safe_decimal(acc.get("totalEquity"))
            self.state.available = safe_decimal(acc.get("totalAvailableBalance"))

            if self.state.initial_equity_session == Decimal("0"):
                self.state.initial_equity_session = self.state.equity

            # Daily PnL Reset (Improvement 4)
            current_utc = datetime.now(timezone.utc)
            reset_hour = self.cfg.daily_reset_hour_utc
            current_reset_time = current_utc.replace(
                hour=reset_hour, minute=0, second=0, microsecond=0
            )
            if current_utc < current_reset_time:
                current_reset_time -= timedelta(days=1)
            reset_date_str = current_reset_time.strftime("%Y-%m-%d")

            if self.state.last_daily_reset_date != reset_date_str:
                self.state.log(
                    f"{Fore.CYAN}# Daily PnL reset initiated for {reset_date_str} (UTC {reset_hour}:00).{Style.RESET_ALL}",
                    "health",
                )
                self.state.initial_equity_daily = self.state.equity
                self.state.daily_profit_reached = False
                self.state.daily_loss_reached = False
                self.state.last_daily_reset_date = reset_date_str
                self.state.trade_count = 0  # Reset trade count daily (Improvement 4)
                self.state.wins = 0  # Reset win count daily (Improvement 4)
            elif self.state.initial_equity_daily == Decimal("0"):
                self.state.initial_equity_daily = self.state.equity

            self.state.current_session_pnl = (
                self.state.equity - self.state.initial_equity_session
            )
            self.state.current_session_pnl_pct = safe_div(
                self.state.current_session_pnl, self.state.initial_equity_session
            )
            self.state.daily_pnl = self.state.equity - self.state.initial_equity_daily
            self.state.daily_pnl_pct = safe_div(
                self.state.daily_pnl, self.state.initial_equity_daily
            )

            self.state.log(
                f"{Fore.GREEN}Wallet synced. Equity: {self.state.equity:.2f} USDT. Daily PnL: {self.state.daily_pnl:+.2f}.{Style.RESET_ALL}",
                "info",
            )
        else:
            self._report_error(
                f"Failed to update wallet: {r.get('retMsg')}", "error", 105
            )

    def _update_oracle(self, live_p: float = None):
        """# Weaves the threads of market data into mystical indicators. (Ehlers Integration)"""
        s, cfg = self.state, self.cfg
        if (
            len(s.ohlc)
            < max(cfg.warmup_candles, cfg.rsi_period, cfg.bollinger_window) + 10
        ):
            return

        c = np.array([x[3] for x in s.ohlc])
        if live_p:
            c[-1] = live_p

        h = np.array([x[1] for x in s.ohlc])
        l = np.array([x[2] for x in s.ohlc])
        v = np.array([x[4] for x in s.ohlc])

        # 1. ATR (Wilder's Smoothing)
        s.atr = calculate_atr(h, l, c, cfg.atr_ewma_span)

        # 2. Fisher Momentum Acceleration (Kept/Clarified)
        win = c[-10:]
        mn, mx = np.min(win), np.max(win) + 1e-9
        norm = np.clip(0.66 * ((c[-1] - mn) / (mx - mn + 1e-9) - 0.5), -0.99, 0.99)
        s.fisher_sig = s.fisher
        s.fisher = 0.5 * np.log((1 + norm) / (1 - norm + 1e-9))

        # 3. RSI (Faster period)
        if len(c) > cfg.rsi_period:
            deltas = np.diff(c)
            gains = np.clip(deltas, 0, None)
            losses = -np.clip(deltas, None, 0)
            avg_gain = np.mean(gains[-cfg.rsi_period :])
            avg_loss = np.mean(losses[-cfg.rsi_period :])
            rs = avg_gain / (avg_loss + 1e-12)
            s.rsi = 100.0 - 100.0 / (1.0 + rs)
        else:
            s.rsi = 50.0  # neutral when not enough data

        # 4. VWAP & EMAs
        if len(c) >= cfg.bollinger_window:
            tp = (h + l + c) / 3.0
            tp_window = tp[-cfg.bollinger_window :]
            vol_window = v[-cfg.bollinger_window :]
            vol_sum = np.sum(vol_window)
            s.vwap = safe_decimal(np.sum(tp_window * vol_window) / (vol_sum + 1e-9))
        else:
            s.vwap = Decimal("0")

        # EMA: fall back to last close if not initialized
        last_price = float(c[-1])
        if s.ema_fast == Decimal("0"):
            s.ema_fast = safe_decimal(last_price)
        if s.ema_macro == Decimal("0"):
            s.ema_macro = safe_decimal(last_price)

        alpha_f = 2.0 / (cfg.rsi_period + 1)
        alpha_m = 2.0 / (cfg.bollinger_window + 1)
        s.ema_fast = safe_decimal(
            alpha_f * last_price + (1.0 - alpha_f) * float(s.ema_fast)
        )
        s.ema_macro = safe_decimal(
            alpha_m * last_price + (1.0 - alpha_m) * float(s.ema_macro)
        )

        # 5. VSI
        if len(v) >= 20:
            avg_v = np.mean(v[-20:])
            s.vsi = v[-1] / avg_v if avg_v > 0 else 1.0
        else:
            s.vsi = 1.0

        # 6. Bollinger Bands (Improvement 11)
        window = cfg.bollinger_window
        if len(c) >= window:
            slice_c = c[-window:]
            sma = float(np.mean(slice_c))
            stddev = float(np.std(slice_c))
            s.bollinger_upper = sma + cfg.bollinger_std_dev_mult * stddev
            s.bollinger_lower = sma - cfg.bollinger_std_dev_mult * stddev
            if sma > 0:
                s.bollinger_width_pct = max(
                    0.0,
                    min(1000.0, (s.bollinger_upper - s.bollinger_lower) / sma * 100.0),
                )
            else:
                s.bollinger_width_pct = 0.0
        else:
            s.bollinger_upper = s.bollinger_lower = s.bollinger_width_pct = 0.0

        # --- Ehlers SuperPass Filter (Trend Proxy - NEW) ---
        if len(c) > cfg.superpass_period + 2:
            smooth_c = c[-cfg.superpass_period :]
            superpass_smooth = np.mean(smooth_c)

            s.superpass_signal = (
                float(s.superpass_signal)
                if s.superpass_signal > 0
                else superpass_smooth
            )

            if superpass_smooth > s.superpass_signal:
                s.trend_signal = 1.0
            elif superpass_smooth < s.superpass_signal:
                s.trend_signal = 0.0
            else:
                s.trend_signal = s.trend_signal

            s.superpass_signal = superpass_smooth
        else:
            s.trend_signal = 0.5

        # --- Ehlers Cycle Period Estimation (Simplified - NEW) ---
        if len(c) > 20:
            peaks = np.where((c[1:-1] > c[2:]) & (c[1:-1] > c[:-2]))[0] + 1
            if len(peaks) >= 2:
                s.cycle_period = float(peaks[-1] - peaks[-2])
            elif s.cycle_period == 0.0:
                s.cycle_period = 15.0

        # --- ALPHA ENGINE (bounded) ---
        score = 0.0

        obi_component = min(1.0, abs(s.obi_score))  # 0–1
        fisher_component = min(3.0, abs(s.fisher)) / 3.0  # 0–1
        rsi_component = min(50.0, abs(s.rsi - 50.0)) / 50.0  # 0–1

        score += 60.0 * obi_component
        score += 20.0 * fisher_component
        score += 20.0 * rsi_component

        if (s.trend_signal == 1.0 and s.fisher > 0) or (
            s.trend_signal == 0.0 and s.fisher < 0
        ):
            score += 5.0

        rsi_confluence = (s.fisher > 0 and s.rsi < 60) or (s.fisher < 0 and s.rsi > 40)
        if rsi_confluence:
            score += 5.0

        if s.vsi > cfg.vsi_threshold:
            volume_boost = min(10.0, (s.vsi - cfg.vsi_threshold) * 5.0)
            score += volume_boost

        s.alpha_score = max(0.0, min(100.0, score))
        s.ready = (
            len(s.ohlc)
            >= max(cfg.warmup_candles, cfg.rsi_period, cfg.bollinger_window) + 10
        )

    async def _auto_adjust_leverage(self):
        """Adjusts leverage dynamically based on market volatility (ATR) and winrate. (Improvement 20)"""
        s, cfg = self.state, self.cfg
        if s.atr == 0 or s.active:
            return
        now = time.time()
        if (now - s.last_leverage_adjust_ts) < cfg.leverage_adjust_cooldown_sec:
            return

        win_rate = safe_div(
            Decimal(s.wins), Decimal(max(1, s.trade_count)), Decimal("0.5")
        )
        base_lev = cfg.initial_max_leverage

        # Adjust leverage only if quality conditions met
        if win_rate > Decimal(str(cfg.dynamic_risk_win_rate_threshold)) and s.atr > 0:
            calculated_lev = int(base_lev / (s.atr + 0.05))
            new_lev = min(base_lev, max(cfg.min_dynamic_leverage, calculated_lev))
        else:
            new_lev = base_lev

        if new_lev != cfg.leverage:
            res = await self.request(
                "POST",
                "/v5/position/set-leverage",
                {
                    "category": cfg.category,
                    "symbol": cfg.symbol,
                    "buyLeverage": str(new_lev),
                    "sellLeverage": str(new_lev),
                },
            )
            if res.get("retCode") == 0:
                cfg.leverage = new_lev
                s.last_leverage_adjust_ts = now
                s.log(
                    f"{Fore.GREEN}# Adjusted leverage to {new_lev}x (from {self.cfg.leverage}x) due to volatility {s.atr:.2f} and win rate {win_rate:.2f}.{Style.RESET_ALL}",
                    "health",
                )
            else:
                self._report_error(
                    f"Failed to adjust leverage: {res.get('retMsg')}", "error", 103
                )

    async def confirm_order_filled(
        self, order_id: str, max_retries: int = 5, delay_sec: float = 0.5
    ) -> bool:
        """Checks order status for fill, retrying up to N times. (Improvement 7)"""
        s, cfg = self.state, self.cfg
        for attempt in range(max_retries):
            res = await self.request(
                "GET",
                "/v5/order/realtime",
                {"orderId": order_id, "category": cfg.category, "symbol": cfg.symbol},
            )
            if res.get("retCode") == 0 and res["result"]:
                order_status = res["result"].get("orderStatus")
                if order_status == "Filled":
                    s.log(f"Order {order_id} confirmed FILLED.", "debug")
                    return True
                elif order_status in ["Cancelled", "Rejected"]:
                    s.log(f"Order {order_id} was {order_status}. Not filled.", "warn")
                    return False
            s.log(
                f"Order {order_id} not yet filled (status: {res['result'].get('orderStatus') if res.get('result') else 'N/A'}). Retrying in {delay_sec}s...",
                "debug",
            )
            await asyncio.sleep(delay_sec)

        self._report_error(
            f"Order {order_id} not confirmed filled after {max_retries} attempts.",
            "error",
            106,
        )
        return False

    async def setup_trailing_stop(
        self,
        state: SentinelState,
        leverage: int,
        atr: float,
        price_prec: int,
        cfg: ScalperConfig,
    ):
        trail_atr = Decimal(str(atr)) * cfg.trail_atr_mult
        qty = state.qty
        pos_side = state.side
        res = await self.request(
            "POST",
            "/v5/position/trading-stop",
            {
                "category": cfg.category,
                "symbol": cfg.symbol,
                "trailingStop": str(trail_atr.quantize(Decimal(f"1e-{price_prec}"))),
                "positionIdx": 0,
            },
        )
        if res.get("retCode") != 0:
            state.log(f"Failed to set trailing stop: {res.get('retMsg')}", "error")
            return False
        else:
            state.trailing_sl_value = trail_atr
            state.log(f"Trailing stop set at {trail_atr:.{price_prec}f}", "info")
            return True

    def bollinger_band_filter(self, state: SentinelState, cfg: ScalperConfig) -> bool:
        price = float(state.price)
        upper = state.bollinger_upper
        lower = state.bollinger_lower
        width = state.bollinger_width_pct
        rsi = state.rsi
        if not cfg.bollinger_band_filter_enabled or upper == 0 or lower == 0:
            return True
        if cfg.bollinger_band_strategy == "filter_extremes":
            # Only allow entries away from extremes
            if (price >= upper * 0.995 and rsi > 70) or (
                price <= lower * 1.005 and rsi < 30
            ):
                return False
        elif cfg.bollinger_band_strategy == "mean_reversion":
            # Require strong contrarian RSI and band proximity
            if not (
                (price <= lower * 1.01 and rsi < 30 and width > 1.0)
                or (price >= upper * 0.99 and rsi > 70 and width > 1.0)
            ):
                return False
        return True

    async def strike(
        self,
        side: str,
        qty: Decimal,
        reduce: bool = False,
        order_type: str = "Limit",
        price: Optional[Decimal] = None,
        take_profit_price: Optional[Decimal] = None,
    ):
        """
        # Executes an order, attempting Limit first, then Market with slippage control. (Improvements 7, 8, 21)
        """
        s, cfg = self.state, self.cfg

        quantized_qty = quantize_to_step(qty, s.qty_step)
        if quantized_qty < s.min_qty:
            s.log(
                f"Calculated quantity {qty} too small ({quantized_qty}). Minimum is {s.min_qty}. Withheld strike.",
                "warn",
            )
            TermuxAPI.toast("Strike withheld: Qty too small!")
            return

        params = {
            "category": cfg.category,
            "symbol": cfg.symbol,
            "side": side,
            "orderType": order_type,
            "qty": str(quantized_qty),
            "reduceOnly": reduce,
        }

        exit_ref_price = s.entry_p if s.active else s.price
        atr_dec = Decimal(str(s.atr))

        price_step = Decimal(f"1e-{s.price_prec}")

        if not reduce and atr_dec > 0:
            sl_raw = (
                exit_ref_price - atr_dec * cfg.sl_atr_mult
                if side == "Buy"
                else exit_ref_price + atr_dec * cfg.sl_atr_mult
            )
            sl_price = max(Decimal("0.01"), sl_raw)
            params["stopLoss"] = str(quantize_to_step(sl_price, price_step))

        if take_profit_price is not None:
            tp_q = max(Decimal("0.01"), take_profit_price)
            params["takeProfit"] = str(quantize_to_step(tp_q, price_step))
        else:
            tp_raw = (
                exit_ref_price + atr_dec * cfg.tp_partial_atr_mult
                if side == "Buy"
                else exit_ref_price - atr_dec * cfg.tp_partial_atr_mult
            )
            tp_q = max(Decimal("0.01"), tp_raw)
            params["takeProfit"] = str(quantize_to_step(tp_q, price_step))

        if order_type == "Limit" and price is not None:
            params["price"] = str(quantize_to_step(price, price_step))

        if not reduce:
            s.log(
                f"{Fore.CYAN}Initiating STRIKE {side} {order_type} with Qty: "
                f"{quantized_qty} and SL: {params.get('stopLoss')}{Style.RESET_ALL}",
                "entry"
            )
        else:
            s.log(
                f"{Fore.YELLOW}Executing HARVEST {side} {order_type} for Qty: {quantized_qty}{Style.RESET_ALL}",
                "exit",
            )

        r = await self.request("POST", "/v5/order/create", params)
        if r.get("retCode") == 0:
            order_id = r["result"].get("orderId")
            s.log(
                f"{Fore.GREEN}{'HARVEST' if reduce else 'STRIKE'} {side} order placed successfully. Order ID: {order_id}{Style.RESET_ALL}",
                "entry" if not reduce else "exit",
            )

            if not reduce:
                is_filled = await self.confirm_order_filled(order_id)
                if is_filled:
                    # optimistic local state update
                    s.active = True
                    s.side = side
                    s.entry_ts = time.time()
                    s.stage = 1
                    await self.update_wallet()
        else:
            self._report_error(f"API Error on strike: {r.get('retMsg')}", "error", 106)
            TermuxAPI.speak("Order failed!")

    async def logic_loop(self, stop: asyncio.Event):
        """# The heart of the oracle, where entry and exit spells are cast."""
        s, cfg = self.state, self.cfg
        s.log(f"{Fore.GREEN}Oracle's logic loop initiated.{Style.RESET_ALL}", "health")
        while not stop.is_set():
            await asyncio.sleep(0.2)  # **MAX FREQUENCY CHANGE: Minimum sleep**

            # Config reload is handled by a separate background task.
            # No need to await it here.

            # **UPGRADE 1: Quick bail on known high API latency**
            if s.api_latency > 1000:
                s.log(
                    f"{Fore.RED}Bailing logic loop due to extreme API latency ({s.api_latency}ms).{Style.RESET_ALL}",
                    "warn",
                )
                await asyncio.sleep(5)
                continue

            if not s.ready or s.price <= 0 or s.atr == 0:
                s.log(
                    f"{Fore.YELLOW}Awaiting readiness (Ready: {s.ready}, Price: {s.price}, ATR: {s.atr:.2f}).{Style.RESET_ALL}",
                    "warn",
                )
                await asyncio.sleep(1)
                continue

            # --- Global Circuit Breakers ---
            if s.in_stasis():
                remaining = int(s.stasis_until - time.time())
                s.log(
                    f"{Fore.YELLOW}Bot in Stasis: {remaining}s remaining. Reason: {s.stasis_reason}.{Style.RESET_ALL}",
                    "warn",
                )
                # **UPGRADE 4: Check network restoration if in Network Stasis**
                if s.stasis_reason == "Network Lost" and is_connected():
                    s.stasis_until = time.time()  # Exit stasis immediately
                    s.log(
                        f"{Fore.GREEN}Network Restored! Exiting Network Stasis early.{Style.RESET_ALL}",
                        "health",
                    )

                await asyncio.sleep(5)
                continue

            limit_hit = False
            if (
                s.daily_loss_reached
                or s.daily_profit_reached
                or (cfg.max_daily_trades > 0 and s.trade_count >= cfg.max_daily_trades)
            ):
                limit_hit = True
                reason = (
                    "Daily Loss Limit Reached"
                    if s.daily_loss_reached
                    else (
                        "Daily Profit Target Reached"
                        if s.daily_profit_reached
                        else "Max Daily Trades Reached"
                    )
                )
                s.log(
                    f"{Fore.RED}Ritual Halted: {reason} ({s.daily_pnl_pct:.2%}).{Style.RESET_ALL}",
                    "error",
                )
                TermuxAPI.notify("Trading Halted", reason, id=107)
                TermuxAPI.speak("Trading halted due to limit.")

            if limit_hit and s.active:
                # Improvement 18: Close position with a Limit order first
                exit_side = "Sell" if s.side == "Buy" else "Buy"
                exit_price = (
                    s.price + (Decimal(str(s.atr)) * Decimal("0.5"))
                    if s.side == "Buy"
                    else s.price - (Decimal(str(s.atr)) * Decimal("0.5"))
                )
                await self.strike(
                    exit_side, s.qty, reduce=True, order_type="Limit", price=exit_price
                )
                await asyncio.sleep(2)
                if s.active:
                    s.log(
                        f"{Fore.RED}Forcing Market Close after Limit failed.{Style.RESET_ALL}",
                        "error",
                    )
                    await self.strike(
                        exit_side, s.qty, reduce=True, order_type="Market"
                    )

            if limit_hit:
                await asyncio.sleep(3600)
                continue

            await self._auto_adjust_leverage()

            if s.active:
                await self._reconcile_position()  # Improvement 1: Reconcile on every loop tick if active
                await self._manage_active_position()
            else:
                await self._evaluate_entry_signals()

    async def _reconcile_position(self):
        s, cfg = self.state, self.cfg
        if not s.active:
            return

        r = await self.request(
            "GET", "/v5/position/list", {"category": cfg.category, "symbol": cfg.symbol}
        )
        if r.get("retCode") != 0:
            self._report_error(
                f"Failed to reconcile position: {r.get('retMsg')}", "error", 118
            )
            return

        pos_list = r.get("result", {}).get("list") or []
        if not pos_list:
            if s.active:
                self._report_error(
                    "Position vanished from API but local state is active. Clearing local position.",
                    "error",
                    118,
                )
                s.active = False
                s.stage = 0
            return

        pos = pos_list[0]
        if pos.get("symbol") != cfg.symbol:
            return

        size = safe_decimal(pos.get("size"))
        if size <= 0:
            if s.active:
                s.active = False
                s.stage = 0
            return

        s.qty = size
        s.side = pos.get("side", s.side)
        s.entry_p = safe_decimal(pos.get("avgPrice"))
        s.upnl = safe_decimal(pos.get("unrealisedPnl"))

        s.log(
            f"Position reconciled via REST. Qty: {s.qty}, Entry: {s.entry_p}.", "health"
        )

    async def _manage_active_position(self):
        """Manages an active position: partial TP, trailing SL, max hold time. (Improvement 6, 20)"""
        s, cfg = self.state, self.cfg
        atr_dec = Decimal(str(s.atr))

        if (
            s.entry_p == Decimal("0")
            or s.qty == Decimal("0")
            or atr_dec == Decimal("0")
        ):
            self._report_error(
                "Zero exit reference price/qty/ATR. Forcing closure.", "error", 118
            )
            await self.strike("Sell" if s.side == "Buy" else "Buy", s.qty, True)
            return

        # 1. Partial TP Harvest (Stage 1 -> Stage 2) (Improvement 6)
        if s.stage == 1:
            target_pnl_usdt = (
                Decimal(str(s.atr * float(cfg.tp_partial_atr_mult))) * s.qty
            )
            current_pnl_usdt = abs(s.upnl)

            if current_pnl_usdt >= target_pnl_usdt:
                s.log(
                    f"{Fore.GREEN}Stage 1 Harvest: {target_pnl_usdt:.2f} USDT Profit Taken. Setting trailing SL.{Style.RESET_ALL}",
                    "exit",
                )
                await self.strike("Sell" if s.side == "Buy" else "Buy", s.qty / 2, True)

                # Set trailing stop for remaining position
                if await self.setup_trailing_stop(
                    s, cfg.leverage, s.atr, s.price_prec, cfg
                ):
                    s.stage = 2
                    TermuxAPI.toast("Partial TP hit!")
                else:
                    self._report_error(
                        f"Failed to set Trailing Stop after partial TP. Manually track.",
                        "error",
                        120,
                    )
                    s.stage = 1  # Keep in stage 1 if trailing stop setup failed

        # 2. Max Hold Time Reaper
        if (time.time() - s.entry_ts) > cfg.max_hold_sec:
            s.log(
                f"{Fore.MAGENTA}Reaper: Max Hold Time Reached ({cfg.max_hold_sec}s). Closing position.{Style.RESET_ALL}",
                "exit",
            )
            await self.strike("Sell" if s.side == "Buy" else "Buy", s.qty, True)
            TermuxAPI.toast("Max hold time reached!")

    async def _evaluate_entry_signals(self):
        """Evaluates market conditions and casts entry spells if signals align. (Hyper-Scalpel & Ehlers)"""
        s, cfg = self.state, self.cfg

        if (
            time.time() - s.last_trade_ts < cfg.cooldown_base
        ):  # **MAX FREQUENCY CHANGE**
            s.log(
                f"{Fore.BLUE}Entry cooldown active: {cfg.cooldown_base - (time.time() - s.last_trade_ts):.1f}s remaining.{Style.RESET_ALL}",
                "debug",
            )
            return

        if s.atr < cfg.min_atr_threshold:
            s.log(
                f"{Fore.YELLOW}ATR ({s.atr:.2f}) below volatility threshold ({cfg.min_atr_threshold}). Skipping entry.{Style.RESET_ALL}",
                "warn",
            )
            return

        # --- Dynamic Risk Adjustment (DRM) (Improvement 2) ---
        win_rate = _effective_win_rate(s.trade_count, s.wins)

        adjusted_risk_pct = cfg.risk_per_trade_pct

        if win_rate > Decimal(str(cfg.dynamic_risk_win_rate_threshold)):
            adjusted_risk_pct *= cfg.dynamic_risk_multiplier_high_win_rate
            s.log(
                f"DRM: High WR ({win_rate:.1%}) -> Risk {adjusted_risk_pct:.3%}.",
                "debug",
            )
        elif win_rate < Decimal("0.4"):
            adjusted_risk_pct *= cfg.dynamic_risk_multiplier_low_win_rate
            s.log(
                f"DRM: Low WR ({win_rate:.1%}) -> Risk {adjusted_risk_pct:.3%}.",
                "debug",
            )

        if s.atr < cfg.low_vol_atr_threshold:
            adjusted_risk_pct *= cfg.low_volatility_risk_multiplier
            s.log(
                f"DRM: Low Vol ({s.atr:.2f}) -> Risk {adjusted_risk_pct:.3%}.", "debug"
            )

        risk_usdt = s.available * adjusted_risk_pct

        # --- Bollinger Bands Filter / Strategy (Improvement 11) ---
        bollinger_strategy_ok = self.bollinger_band_filter(s, cfg)

        if not bollinger_strategy_ok:
            s.signal_confirmed_candles = 0
            s.last_signal_direction = "NONE"
            return

        # --- EMA Cross Confirmation & Signal Generation (Improvement 16 + Ehlers Trend Check) ---
        ema_f, ema_m = s.ema_fast, s.ema_macro

        if ema_f <= 0 or ema_m <= 0 or s.price <= 0:
            return

        ema_proximity = safe_div(abs(s.price - ema_f), ema_f, Decimal("1"))
        ema_proximity_ok = ema_proximity < cfg.price_ema_proximity_pct

        ema_delta = ema_f - ema_m
        ema_cross_long = ema_delta > Decimal("0") and safe_div(
            ema_delta, ema_m, Decimal("0")
        ) > Decimal("0.0001")
        ema_cross_short = ema_delta < Decimal("0") and safe_div(
            -ema_delta, ema_m, Decimal("0")
        ) > Decimal("0.0001")

        current_signal_direction = "NONE"

        if s.alpha_score >= cfg.min_alpha_score and ema_proximity_ok:
            trend_check = (s.trend_signal == 1.0 and s.fisher > 0) or (
                s.trend_signal == 0.0 and s.fisher < 0
            )
            long_condition = (
                s.fisher > s.fisher_sig
                and s.rsi < 60
                and ema_cross_long
                and trend_check
            )
            short_condition = (
                s.fisher < s.fisher_sig
                and s.rsi > 40
                and ema_cross_short
                and trend_check
            )

            if long_condition:
                current_signal_direction = "BUY"
            elif short_condition:
                current_signal_direction = "SELL"

        if current_signal_direction != s.last_signal_direction:
            s.signal_confirmed_candles = 0
            s.last_signal_direction = current_signal_direction
            s.log(
                f"{Fore.YELLOW}Signal direction changed or lost. Resetting confirmation.{Style.RESET_ALL}",
                "debug",
            )
            return

        if current_signal_direction == "NONE":
            s.signal_confirmed_candles = 0
            return

        if not confirm_signal(
            s, current_signal_direction, cfg.entry_confirmation_candles
        ):
            s.log(
                f"{Fore.BLUE}Signal '{current_signal_direction}' strength: {s.signal_strength}% confirmed: {s.signal_confirmed_candles}/{cfg.entry_confirmation_candles} candles. Awaiting further confirmation.{Style.RESET_ALL}",
                "debug",
            )
            return

        # Signal confirmed, proceed with strike
        sl_dist = atr_dec * cfg.sl_atr_mult
        if sl_dist == Decimal("0"):
            self._report_error(
                "ATR is zero, cannot calculate SL distance for entry. Skipping strike.",
                "error",
                119,
            )
            return

        # --- Quantity Calculation (Improvement 22) ---
        qty = calculate_dynamic_qty(
            s.available, adjusted_risk_pct, s.atr, s.price, cfg.leverage, s.qty_step
        )

        # Limit Maximum Position Size
        max_qty_usdt = cfg.max_position_qty_usdt
        if qty * s.price > max_qty_usdt:
            qty = (max_qty_usdt / s.price).quantize(s.qty_step, ROUND_DOWN)
            s.log(
                f"{Fore.YELLOW}Quantity limited to {qty} to respect max position value {max_qty_usdt} USDT.{Style.RESET_ALL}",
                "warn",
            )

        if qty < s.min_qty:
            s.log(
                f"{Fore.YELLOW}Calculated quantity {qty} is below minimum {s.min_qty}. Skipping entry.{Style.RESET_ALL}",
                "warn",
            )
            return

        # Calculate Take Profit Price for initial order (Improvement 6)
        tp_price = None
        if current_signal_direction == "BUY":
            tp_price = s.price + (sl_dist / Decimal(str(cfg.leverage)))
        else:
            tp_price = s.price - (sl_dist / Decimal(str(cfg.leverage)))
        tp_price = max(Decimal("0.01"), tp_price)

        # Execute Strike (Improvement 7)
        if current_signal_direction == "BUY":
            s.log(
                f"{Fore.BLUE}Long entry signal CONFIRMED! Alpha: {s.alpha_score:.1f}. Preparing Limit strike.{Style.RESET_ALL}",
                "info",
            )
            limit_p = s.bid.quantize(Decimal(f"1e-{s.price_prec}"))
            await self.strike(
                side="Buy",
                qty=qty,
                order_type="Limit",
                price=limit_p,
                take_profit_price=tp_price,
            )
        elif current_signal_direction == "SELL":
            s.log(
                f"{Fore.BLUE}Short entry signal CONFIRMED! Alpha: {s.alpha_score:.1f}. Preparing Limit strike.{Style.RESET_ALL}",
                "info",
            )
            limit_p = s.ask.quantize(Decimal(f"1e-{s.price_prec}"))
            await self.strike(
                side="Sell",
                qty=qty,
                order_type="Limit",
                price=limit_p,
                take_profit_price=tp_price,
            )

        # Reset confirmation after striking
        s.signal_confirmed_candles = 0
        s.last_signal_direction = "NONE"

    async def ws_nexus_public(self, stop: asyncio.Event):
        """# Channels public market data streams (tickers, orderbook, kline). (Improvement 25)"""
        self.state.log(
            f"{Fore.BLUE}# Channeling public market data streams...{Style.RESET_ALL}",
            "health",
        )
        reconnect_delay = 1
        while not stop.is_set():
            try:
                async with self.session.ws_connect(
                    self.ws_pub, heartbeat=self.cfg.ws_heartbeat
                ) as ws:
                    self.state.log(
                        f"{Fore.GREEN}Public WebSocket connected.{Style.RESET_ALL}",
                        "info",
                    )
                    reconnect_delay = 1
                    await ws.send_json(
                        {
                            "op": "subscribe",
                            "args": [
                                f"tickers.{self.cfg.symbol}",
                                f"orderbook.50.{self.cfg.symbol}",
                                f"kline.{self.cfg.kline_interval}.{self.cfg.symbol}",
                                f"kline.5.{self.cfg.symbol}",  # Improvement 25: Added 5m kline subscription
                            ],
                        }
                    )
                    async for msg in ws:
                        if stop.is_set():
                            break
                        d = json.loads(msg.data)
                        topic = d.get("topic", "")

                        if "tickers" in topic:
                            res = (
                                d.get("data", [{}])[0]
                                if isinstance(d.get("data"), list)
                                else d.get("data")
                            )
                            if not res:
                                continue

                            received_last_price = res.get("lastPrice")
                            received_bid_price = res.get("bid1Price")
                            received_ask_price = res.get("ask1Price")

                            new_price = safe_decimal(
                                received_last_price, self.state.price
                            )
                            new_bid = safe_decimal(received_bid_price, self.state.bid)
                            new_ask = safe_decimal(received_ask_price, self.state.ask)

                            if new_price == Decimal("0") and (
                                new_bid > Decimal("0") or new_ask > Decimal("0")
                            ):
                                new_price = safe_div(
                                    new_bid + new_ask, Decimal("2"), new_price
                                )
                            elif new_price == Decimal(
                                "0"
                            ) and self.state.price > Decimal("0"):
                                new_price = self.state.price

                            self.state.price = new_price
                            self.state.bid = new_bid
                            self.state.ask = new_ask

                            self.state.latency = max(
                                0,
                                int(time.time() * 1000)
                                - int(res.get("updatedTime", 0)),
                            )

                            if self.state.price > Decimal("0"):
                                self._update_oracle(float(self.state.price))

                        elif "orderbook" in topic:
                            # **UPGRADE 3: Improved Orderbook Data Cleaning**
                            data = d["data"]
                            if d.get("type") == "snapshot":
                                self.state.local_bids.clear()
                                self.state.local_asks.clear()

                            for p, q in data.get("b", []):
                                price_dec = safe_decimal(p)
                                qty_dec = safe_decimal(q)
                                if qty_dec == Decimal("0") or price_dec <= Decimal("0"):
                                    continue
                                self.state.local_bids[price_dec] = qty_dec

                            for p, q in data.get("a", []):
                                price_dec = safe_decimal(p)
                                qty_dec = safe_decimal(q)
                                if qty_dec == Decimal("0") or price_dec <= Decimal("0"):
                                    continue
                                self.state.local_asks[price_dec] = qty_dec

                            bids = sorted(self.state.local_bids.items(), reverse=True)[
                                :15
                            ]
                            asks = sorted(self.state.local_asks.items())[:15]
                            wb = sum(
                                float(q) / ((i + 1) ** 2)
                                for i, (_, q) in enumerate(bids)
                            )
                            wa = sum(
                                float(q) / ((i + 1) ** 2)
                                for i, (_, q) in enumerate(asks)
                            )
                            self.state.obi_score = (wb - wa) / (wb + wa + 1e-9)

                        elif "kline" in topic:
                            k = d["data"][0]
                            if k.get("confirm"):
                                o, h, l, c, v = (
                                    float(k["open"]),
                                    float(k["high"]),
                                    float(k["low"]),
                                    float(k["close"]),
                                    float(k["volume"]),
                                )
                                self.state.ohlc.append((o, h, l, c, v))

                                # Improvement 5: Confirmation based on closed candle
                                if (
                                    not self.state.active
                                    and self.state.last_signal_direction != "NONE"
                                ):
                                    if (
                                        self.state.last_signal_direction == "BUY"
                                        and o < c
                                    ):
                                        self.state.signal_confirmed_candles += 1
                                    elif (
                                        self.state.last_signal_direction == "SELL"
                                        and o > c
                                    ):
                                        self.state.signal_confirmed_candles += 1

                                self._update_oracle()

            except Exception as e:
                self._report_error(f"Public WS lost: {e}", "error", 109)
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60)

    async def ws_nexus_private(self, stop: asyncio.Event):
        """# Establishes a secure channel for private account data (positions, wallet)."""
        self.state.log(
            f"{Fore.MAGENTA}# Establishing secure channel for private account data...{Style.RESET_ALL}",
            "health",
        )
        reconnect_delay = 1
        while not stop.is_set():
            try:
                async with self.session.ws_connect(
                    self.ws_priv, heartbeat=self.cfg.ws_heartbeat
                ) as ws:
                    self.state.log(
                        f"{Fore.GREEN}Private WebSocket connected.{Style.RESET_ALL}",
                        "info",
                    )
                    reconnect_delay = 1
                    ts = str(int(time.time() * 1000 + 10000))
                    sig = hmac.new(
                        API_SECRET.encode(),
                        f"GET/realtime{ts}".encode(),
                        hashlib.sha256,
                    ).hexdigest()
                    await ws.send_json({"op": "auth", "args": [API_KEY, ts, sig]})
                    await ws.send_json(
                        {"op": "subscribe", "args": ["position", "wallet"]}
                    )
                    async for msg in ws:
                        if stop.is_set():
                            break
                        d = json.loads(msg.data)
                        topic = d.get("topic", "")

                        if topic == "position":
                            for p in d.get("data", []):
                                if p["symbol"] != self.cfg.symbol:
                                    continue

                                was_active = self.state.active
                                self.state.qty = safe_decimal(p["size"])
                                self.state.active = self.state.qty > Decimal("0")
                                self.state.side = (
                                    p["side"] if self.state.active else "HOLD"
                                )
                                self.state.entry_p = safe_decimal(p["avgPrice"])
                                self.state.upnl = safe_decimal(p["unrealisedPnl"])

                                if (
                                    not was_active and self.state.active
                                ):  # Position just opened
                                    self.state.entry_ts = time.time()
                                    self.state.stage = 1
                                    self.state.trade_count += 1
                                    self.state.log(
                                        f"{Fore.GREEN}Position opened: {self.state.side} {self.state.qty} at {self.state.entry_p}.{Style.RESET_ALL}",
                                        "entry",
                                    )
                                    TermuxAPI.speak(
                                        f"{self.state.side} position opened!"
                                    )

                                if (
                                    was_active and not self.state.active
                                ):  # Position just closed
                                    self.state.last_trade_pnl = self.state.upnl
                                    self.state.total_realized_pnl_session += (
                                        self.state.last_trade_pnl
                                    )
                                    self.state.smoothed_realized_pnl.push(
                                        self.state.last_trade_pnl
                                    )
                                    if self.state.last_trade_pnl > Decimal("0"):
                                        self.state.wins += 1
                                        self.state.loss_streak = 0
                                        self.state.log(
                                            f"{Fore.GREEN}Trade #{self.state.trade_count} closed with PROFIT: {self.state.last_trade_pnl:+.4f} USDT.{Style.RESET_ALL}",
                                            "exit",
                                        )
                                        TermuxAPI.toast(
                                            f"WIN! {self.state.last_trade_pnl:+.2f} USDT"
                                        )
                                        TermuxAPI.speak("Profit!")
                                    else:
                                        self.state.loss_streak += 1
                                        self.state.log(
                                            f"{Fore.RED}Trade #{self.state.trade_count} closed with LOSS: {self.state.last_trade_pnl:+.4f} USDT. Consecutive: {self.state.loss_streak}{Style.RESET_ALL}",
                                            "exit",
                                        )
                                        TermuxAPI.toast(
                                            f"LOSS! {self.state.last_trade_pnl:+.2f} USDT"
                                        )
                                        TermuxAPI.speak("Loss!")
                                        if (
                                            self.state.loss_streak
                                            >= self.cfg.max_consecutive_losses
                                        ):
                                            self.state.stasis_until = (
                                                time.time()
                                                + self.cfg.stasis_duration_sec
                                            )
                                            self.state.stasis_reason = "Loss Streak"
                                            self.state.log(
                                                f"{Fore.RED}Breaker: Max consecutive losses reached. Entering Stasis for {self.cfg.stasis_duration_sec}s.{Style.RESET_ALL}",
                                                "error",
                                            )
                                            TermuxAPI.notify(
                                                "Stasis Activated",
                                                "Max consecutive losses reached.",
                                                id=110,
                                            )
                                            TermuxAPI.speak("Stasis activated.")

                                    self.state.stage = 0
                                    self.state.last_trade_ts = time.time()
                                    self.state.trailing_sl_value = Decimal("0")
                                    await self.update_wallet()

                        elif topic == "wallet":
                            await self.update_wallet()

            except Exception as e:
                self._report_error(f"Private WS lost: {e}", "error", 113)
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60)

    async def _check_battery_status(self, stop: asyncio.Event):
        """# Periodically checks device battery status and issues alerts, including critical stasis. (Improvement 19)"""
        self.state.log(
            f"{Fore.CYAN}# Initiating battery status vigil...{Style.RESET_ALL}",
            "health",
        )
        while not stop.is_set():
            status = TermuxAPI.get_battery_status()
            self.state.battery_level = status.get("percentage", -1)
            self.state.battery_status = status.get("status", "UNKNOWN")

            if self.state.battery_level != -1:
                if self.state.battery_level <= self.cfg.critical_battery_level:
                    if (
                        not self.state.stasis_until
                        or self.state.stasis_until < time.time()
                    ):
                        self.state.stasis_until = time.time() + 3600  # Pause 1 hour
                        self.state.stasis_reason = "Battery Critical"  # Improvement 19
                        self.state.log(
                            f"{Fore.RED}CRITICAL: Battery level at {self.state.battery_level}%. Entering stasis for 1 hour.{Style.RESET_ALL}",
                            "error",
                        )
                        TermuxAPI.notify(
                            "Battery Critical",
                            f"Trading paused due to {self.state.battery_level}% battery",
                            id=115,
                        )
                        TermuxAPI.speak("Critical battery level. Trading paused.")
                elif (
                    self.state.battery_level <= self.cfg.battery_alert_threshold
                    and not self.state.battery_alert_sent
                ):
                    self.state.log(
                        f"{Fore.RED}WARNING: Battery level critically low ({self.state.battery_level}%). Please charge device!{Style.RESET_ALL}",
                        "error",
                    )
                    TermuxAPI.notify(
                        "LOW BATTERY",
                        f"Battery at {self.state.battery_level}%. Charge device!",
                        id=114,
                    )
                    TermuxAPI.speak("Battery critically low. Please charge device.")
                    self.state.battery_alert_sent = True
                elif (
                    self.state.battery_level > self.cfg.battery_alert_threshold
                    and self.state.battery_alert_sent
                ):
                    self.state.battery_alert_sent = False

            await asyncio.sleep(300)

    async def _check_config_for_reload(self, stop: asyncio.Event):
        """Periodic hot reload of config.json."""
        config_filepath = "config.json"
        while not stop.is_set():
            if os.path.exists(config_filepath):
                current_mod_time = os.path.getmtime(config_filepath)
                if current_mod_time > self.state.last_config_mod_time:
                    self.state.log(
                        "config.json modified. Attempting hot reload...", "warn"
                    )
                    new_config = ScalperConfig.load_from_file(config_filepath)
                    if new_config:
                        old_cfg = self.cfg
                        new_config.initial_max_leverage = old_cfg.initial_max_leverage
                        new_config.leverage = old_cfg.leverage
                        self.state.config = new_config
                        self.cfg = new_config
                        self.state.last_config_mod_time = current_mod_time
                        self.state.log("Configuration successfully reloaded.", "info")
                    else:
                        self.state.log(
                            "Failed to reload config.json. Keeping old config.", "error"
                        )
            await asyncio.sleep(5)


# =========================
# THE NEON DASHBOARD
# =========================


def build_ui(s: SentinelState) -> Layout:
    """
    # Constructs the mystical dashboard for real-time visualization.
    """
    l = Layout()
    l.split_column(
        Layout(name="top", size=3), Layout(name="mid"), Layout(name="bot", size=10)
    )
    l["mid"].split_row(Layout(name="ora"), Layout(name="tac"))

    daily_pnl_c = "bright_green" if s.daily_pnl >= Decimal("0") else "bright_red"
    session_pnl_c = (
        "bright_green" if s.current_session_pnl >= Decimal("0") else "bright_red"
    )
    realized_pnl_c = (
        "bright_green" if s.total_realized_pnl_session >= Decimal("0") else "bright_red"
    )
    wr = (s.wins / max(1, s.trade_count) * 100) if s.trade_count > 0 else 0.0

    battery_color = "green"
    if s.battery_level <= s.config.critical_battery_level:
        battery_color = "red"
    elif s.battery_level <= s.config.battery_alert_threshold:
        battery_color = "yellow"
    else:
        battery_color = "green"

    header = (
        f"[bold cyan]BCH OMNI-SENTINEL V22.3[/bold cyan]"
        f" | [white]Daily PnL[/white]:[{daily_pnl_c}]{s.daily_pnl:+.4f}[/{daily_pnl_c}]"
        f" ([{daily_pnl_c}]{s.daily_pnl_pct:.2%}[/{daily_pnl_c}])"
        f" | [white]Trades:[/white]{s.trade_count}"
        f" | [white]WR:[/white]{wr:.1f}%"
        f" | [white]Lat:[/white]{s.latency}ms"
        f" | [white]API Lat:[/white]{s.api_latency}ms"
        f" | [white]Bat:[/white][{battery_color}]{s.battery_level}%[/{battery_color}]"
        f" | [white]Lev:[/white]{s.config.leverage}x"
    )
    l["top"].update(
        Panel(Text.from_markup(header, justify="center"), border_style="bright_blue")
    )

    ora = Table.grid(expand=True)
    ora.add_row("Price", f"[bold yellow]{s.price:.{s.price_prec}f}[/]")
    ora.add_row("Alpha Score", f"[bold magenta]{s.alpha_score:.1f}%[/]")
    ora.add_row(
        "OBI score", f"[{'green' if s.obi_score > 0 else 'red'}]{s.obi_score:+.2%}[/]"
    )
    ora.add_row("Fisher / Sig", f"{s.fisher:+.3f} / {s.fisher_sig:+.3f}")
    ora.add_row("RSI / VSI", f"{s.rsi:.1f} / {s.vsi:.2f}")
    ora.add_row("ATR / VWAP", f"{s.atr:.2f} / {s.vwap:.{s.price_prec}f}")
    ora.add_row(
        "EMA Fast/Macro",
        f"{s.ema_fast:.{s.price_prec}f} / {s.ema_macro:.{s.price_prec}f}",
    )
    ora.add_row(
        "BBands U/L/W",
        f"{s.bollinger_upper:.{s.price_prec}f} / {s.bollinger_lower:.{s.price_prec}f} / {s.bollinger_width_pct:.2f}%",
    )

    # Ehlers Additions
    ora.add_row(
        "Ehlers Trend",
        f"{'[green]UP[/]' if s.trend_signal == 1.0 else ('[red]DOWN[/]' if s.trend_signal == 0.0 else '[yellow]NEUTRAL[/]')}",
    )
    ora.add_row("Ehlers Cycle", f"{s.cycle_period:.1f} bars")

    l["ora"].update(
        Panel(ora, title="[bold cyan]The Singularity Oracle[/]", border_style="cyan")
    )

    tac = Table.grid(expand=True)
    if s.active:
        tac.add_row(
            "Position",
            f"[bold {'green' if s.side=='Buy' else 'red'}]{s.side} {s.qty}[/]",
        )
        tac.add_row("Entry Price", f"{s.entry_p:.{s.price_prec}f}")
        tac.add_row(
            "uPnL", f"[{'green' if s.upnl > Decimal('0') else 'red'}]{s.upnl:+.4f}[/]"
        )
        tac.add_row("Stage", f"[bold yellow]{s.stage}/2[/]")
        tac.add_row(
            "Life", f"{int(time.time() - s.entry_ts)}s / {s.config.max_hold_sec}s"
        )
        if s.trailing_sl_value > Decimal("0"):
            tac.add_row("Trail SL", f"{s.trailing_sl_value:.{s.price_prec}f}")
    else:
        status_text = "[bold green]SCANNING[/]"
        stasis_rem = 0
        if s.stasis_until > time.time():
            status_text = "[bold red]STASIS[/]"
            stasis_rem = int(s.stasis_until - time.time())
        elif s.daily_loss_reached or s.daily_profit_reached:
            status_text = "[bold red]HALTED[/]"
        elif (
            s.config.max_daily_trades > 0 and s.trade_count >= s.config.max_daily_trades
        ):
            status_text = "[bold red]MAX TRADES[/]"

        tac.add_row("Status", status_text)
        tac.add_row("Available", f"{s.available:.2f} USDT")
        tac.add_row("Loss Streak", f"{s.loss_streak}/{s.config.max_consecutive_losses}")

        if stasis_rem > 0:
            tac.add_row("Recovery", f"{stasis_rem}s ({s.stasis_reason})")
        elif (
            s.daily_loss_reached
            or s.daily_profit_reached
            or (
                s.config.max_daily_trades > 0
                and s.trade_count >= s.config.max_daily_trades
            )
        ):
            tac.add_row("Session Reset", f"{s.last_daily_reset_date} UTC")

        tac.add_row(
            "Last PnL",
            f"[{'green' if s.last_trade_pnl > Decimal('0') else 'red'}]{s.last_trade_pnl:+.4f}[/]",
        )
        tac.add_row(
            "Realized PnL",
            f"[{realized_pnl_c}]{s.smoothed_realized_pnl.average():+.4f}[/]",
        )

        if (
            s.config.entry_confirmation_candles > 0
            and s.last_signal_direction != "NONE"
        ):
            tac.add_row(
                "Confirm",
                f"[{'blue' if s.signal_confirmed_candles < s.config.entry_confirmation_candles else 'green'}]{s.last_signal_direction}: {s.signal_confirmed_candles}/{s.config.entry_confirmation_candles} (Str: {s.signal_strength}%)[/]",
            )
    l["tac"].update(
        Panel(tac, title="[bold magenta]Tactical Nexus[/]", border_style="magenta")
    )

    l["bot"].update(
        Panel("\n".join(list(s.chronicles)), title="[dim]Conquest Chronicles[/]")
    )
    return l


async def main():
    """
    # The grand orchestration of the Bybit Apex Engine.
    """
    TermuxAPI.wake_lock()

    config = ScalperConfig.load_from_file()
    state = SentinelState(config=config)

    async with BybitApex(state) as apex:
        state.log(
            f"{Fore.LIGHTYELLOW_EX + Style.BRIGHT}Pyrmethus, the Termux Coding Wizard, awakens!{Style.RESET_ALL}",
            "info",
        )
        state.log(
            f"{Fore.CYAN}Initializing BCH OMNI-SENTINEL V22.3 (Resilient Hyper-Scalpel Mode)...{Style.RESET_ALL}",
            "health",
        )

        await apex.boot_ritual()
        await apex.fetch_history()
        await apex.update_wallet()

        stop = asyncio.Event()
        console = Console()
        with Live(
            build_ui(state), refresh_per_second=6, screen=True, console=console
        ) as live:
            tasks = [
                asyncio.create_task(apex.ws_nexus_public(stop)),
                asyncio.create_task(apex.ws_nexus_private(stop)),
                asyncio.create_task(apex.logic_loop(stop)),
                asyncio.create_task(apex._check_battery_status(stop)),
                asyncio.create_task(apex._check_config_for_reload(stop)),
            ]

            async def internet_watchdog():
                while not stop.is_set():
                    if not is_connected():
                        if state.stasis_reason not in (
                            "Battery Critical",
                            "Loss Streak",
                        ):
                            state.log(
                                f"{Fore.RED}# Network disconnected - pausing trading and WS connections.{Style.RESET_ALL}",
                                "error",
                            )
                            TermuxAPI.toast("Network lost – halting trades")
                            TermuxAPI.notify(
                                "Network Disconnected",
                                "Trading paused until reconnection.",
                                id=116,
                            )
                            state.stasis_until = time.time() + 120
                            state.stasis_reason = "Network Lost"
                        await asyncio.sleep(10)
                    await asyncio.sleep(5)

            tasks.append(asyncio.create_task(internet_watchdog()))

            try:
                while True:
                    live.update(build_ui(state))
                    await asyncio.sleep(0.16)
            except asyncio.CancelledError:
                state.log(
                    f"{Fore.YELLOW}The arcane threads are being gracefully unwound...{Style.RESET_ALL}",
                    "warn",
                )
            except KeyboardInterrupt:
                state.log(
                    f"{Fore.YELLOW}# The seeker has interrupted the ritual. Peace be upon your terminal.{Style.RESET_ALL}",
                    "warn",
                )
            except Exception as e:
                state.log(
                    f"{Fore.RED}A critical disturbance in the ether: {e}. Traceback:\n{traceback.format_exc()}{Style.RESET_ALL}",
                    "error",
                )
                TermuxAPI.notify(
                    "Critical Error", f"Bot encountered a critical error: {e}", id=100
                )
                TermuxAPI.speak("Critical error!")
            finally:
                stop.set()
                for t in tasks:
                    if not t.done():
                        t.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                state.log(
                    f"{Fore.MAGENTA}Pyrmethus bids you farewell. May your digital journey be ever enlightened.{Style.RESET_ALL}",
                    "info",
                )
                TermuxAPI.wake_unlock()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(
            f"\n{Fore.RED}# An unhandled anomaly occurred in the main realm: {e}. Traceback:\n{traceback.format_exc()}{Style.RESET_ALL}"
        )
        TermuxAPI.notify("Unhandled Error", f"Main process error: {e}", id=99)
        TermuxAPI.speak("Unhandled error in main process!")
