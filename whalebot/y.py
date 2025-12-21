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

    symbol: str = "BCHUSDT"  # Trading pair symbol
    category: str = "linear"  # Bybit product type (e.g., linear, inverse)
    initial_max_leverage: int = 35  # Initial maximum leverage set for the account
    leverage: int = 35  # Current effective leverage

    # --- The Sentinel's Vows (Tighter for Scalping) ---
    max_latency_ms: int = 300  # Maximum acceptable API latency in milliseconds
    max_spread_pct: Decimal = Decimal("0.0005")  # Maximum allowed spread percentage
    max_hold_sec: int = 30  # Maximum time to hold a position in seconds

    # --- Capital Management (Adjusted for Scalping) ---
    risk_per_trade_pct: Decimal = Decimal("0.01")  # Percentage of available balance to risk per trade
    sl_atr_mult: Decimal = Decimal("0.5")  # Stop Loss multiplier based on ATR
    tp_partial_atr_mult: Decimal = Decimal("0.2")  # Take Profit multiplier for partial TP based on ATR
    trail_atr_mult: Decimal = Decimal("0.3")  # Trailing Stop multiplier based on ATR

    # --- Confluence Thresholds (Adjusted for Scalping) ---
    min_alpha_score: float = 60.0  # Minimum alpha score required for an entry
    vsi_threshold: float = 1.0  # Volume Strength Index threshold
    rsi_period: int = 5  # RSI calculation period

    # --- Circuit Breakers ---
    max_consecutive_losses: int = 3  # Maximum consecutive losses before entering stasis
    stasis_duration_sec: int = 300  # Duration of stasis in seconds
    daily_profit_target_pct: Decimal = Decimal("0.25")  # Daily profit target percentage
    daily_loss_limit_pct: Decimal = Decimal("0.10")  # Daily loss limit percentage
    close_on_daily_limit: bool = True  # Whether to close positions when daily limits are hit
    max_daily_trades: int = 500  # Maximum number of trades allowed per day

    # --- Temporal Rhythms (Faster for Scalping) ---
    kline_interval: str = "1"  # Kline interval for primary analysis (e.g., "1", "5", "60")
    cooldown_base: int = 0.2  # Base cooldown period between trades in seconds
    warmup_candles: int = 100  # Number of historical candles to fetch for indicator warmup
    ws_heartbeat: int = 20  # WebSocket heartbeat interval in seconds
    daily_reset_hour_utc: int = 0  # UTC hour at which daily PnL and trade counts reset
    leverage_adjust_cooldown_sec: int = 120  # Cooldown for dynamic leverage adjustment in seconds

    # --- Termux Specific ---
    battery_alert_threshold: int = 20  # Battery percentage to trigger a low battery alert
    critical_battery_level: int = 10  # Battery percentage to trigger critical stasis

    # --- Entry Confirmation ---
    entry_confirmation_candles: int = 0  # Number of candles required to confirm an entry signal
    price_ema_proximity_pct: Decimal = Decimal("0.0003")  # Maximum price proximity to EMA for entry

    # --- Volatility Filter ---
    min_atr_threshold: float = 0.3  # Minimum ATR required for trading
    atr_ewma_span: int = 10  # EWMA span for ATR calculation

    # --- Bollinger Bands Filter ---
    bollinger_band_filter_enabled: bool = True  # Enable/disable Bollinger Band filter
    bollinger_band_strategy: str = "mean_reversion"  # Bollinger Band strategy (e.g., "filter_extremes", "mean_reversion")
    bollinger_std_dev_mult: float = 2.0  # Bollinger Band standard deviation multiplier
    bollinger_window: int = 20  # Bollinger Band window period

    # --- Position Sizing ---
    max_position_qty_usdt: Decimal = Decimal("200.0")  # Maximum position quantity in USDT
    min_dynamic_leverage: int = 5  # Minimum dynamic leverage

    # --- Dynamic Risk Adjustment (DRM) ---
    dynamic_risk_win_rate_threshold: float = 0.60  # Win rate threshold for dynamic risk adjustment
    dynamic_risk_multiplier_high_win_rate: Decimal = Decimal("1.2")  # Multiplier for risk when win rate is high
    dynamic_risk_multiplier_low_win_rate: Decimal = Decimal("0.8")  # Multiplier for risk when win rate is low

    low_volatility_risk_multiplier: Decimal = Decimal("0.7")  # Multiplier for risk in low volatility
    low_vol_atr_threshold: float = 0.4  # ATR threshold for low volatility

    # --- Ehlers Indicators Config (NEW) ---
    superpass_period: int = 10  # Period for Ehlers SuperPass filter

    # --- Signal Component Weights ---
    OBI_WEIGHT: Decimal = Decimal("0.4")  # Weight for Order Book Imbalance in signal score
    MOMENTUM_WEIGHT: Decimal = Decimal("0.3")  # Weight for Momentum indicators (Fisher) in signal score
    RSI_WEIGHT: Decimal = Decimal("0.2")  # Weight for RSI in signal score
    TREND_WEIGHT: Decimal = Decimal("0.1")  # Weight for Trend (Ehlers) in signal score
    DIR_SCORE_THRESHOLD: Decimal = Decimal("5")  # Directional score threshold for signal
    FISHER_MAG_MULTIPLIER: Decimal = Decimal("40.0")  # Multiplier for Fisher magnitude
    RSI_MAG_CAP: Decimal = Decimal("25.0")  # Cap for RSI magnitude
    RSI_MAG_MULTIPLIER: Decimal = Decimal("2.0")  # Multiplier for RSI magnitude
    TREND_MAG_MULTIPLIER: Decimal = Decimal("100.0")  # Multiplier for Trend magnitude

    # --- Entry Signal Thresholds ---
    DYNAMIC_COOLDOWN_PROFIT_MULTIPLIER: Decimal = Decimal("0.5")  # Multiplier for cooldown after a profitable trade
    STRENGTH_EMA_PROXIMITY_THRESHOLD: Decimal = Decimal("70")  # Signal strength threshold for looser EMA proximity
    STRENGTH_TIERED_ENTRY_THRESHOLD: Decimal = Decimal("80")  # Signal strength threshold for tiered entry

    # --- Risk Multipliers ---
    STRENGTH_FACTOR_MIN: Decimal = Decimal("0.5")  # Minimum strength factor for risk multiplier
    STRENGTH_FACTOR_MAX: Decimal = Decimal("1.5")  # Maximum strength factor for risk multiplier
    WIN_RATE_LOW_THRESHOLD: Decimal = Decimal("0.40")  # Win rate threshold for low risk multiplier
    MAX_RISK_PER_TRADE_PCT: Decimal = Decimal("0.03")  # Hard upper bound on risk percentage per trade
    TP_STRONG_SIGNAL_MULTIPLIER: Decimal = Decimal("1.5")  # TP multiplier for strong signals
    SL_STRONG_SIGNAL_MULTIPLIER: Decimal = Decimal("0.8")  # SL multiplier for strong signals
    MIN_TP_SL_PRICE: Decimal = Decimal("0.01")  # Minimum Take Profit/Stop Loss price

    # --- Hybrid Order Parameters ---
    LIMIT_MAX_BPS_OFFSET: Decimal = Decimal("0.006")  # Maximum basis points offset for limit orders
    LIMIT_MIN_BPS_OFFSET: Decimal = Decimal("0.0005")  # Minimum basis points offset for limit orders
    WAIT_TIME_MIN_SEC: Decimal = Decimal("0.2")  # Minimum wait time for limit order fill in seconds
    WAIT_TIME_MAX_SEC: Decimal = Decimal("1.0")  # Maximum wait time for limit order fill in seconds
    CONFIRM_ORDER_MAX_RETRIES: int = 2  # Maximum retries for confirming order fill
    CONFIRM_ORDER_DELAY_SEC_MULTIPLIER: Decimal = Decimal("0.5")  # Delay multiplier for confirming order fill

    # --- Partial TP ---
    EARLY_TP_ATR_MULTIPLIER: Decimal = Decimal("0.15")  # ATR multiplier for early partial take profit

    # --- Alpha Score Components ---
    ALPHA_OBI_WEIGHT: Decimal = Decimal("60.0")  # Weight for OBI component in alpha score
    ALPHA_FISHER_WEIGHT: Decimal = Decimal("20.0")  # Weight for Fisher component in alpha score
    ALPHA_RSI_WEIGHT: Decimal = Decimal("20.0")  # Weight for RSI component in alpha score
    ALPHA_TREND_CONFLUENCE_BONUS: Decimal = Decimal("5.0")  # Bonus for trend confluence in alpha score
    ALPHA_RSI_CONFLUENCE_BONUS: Decimal = Decimal("5.0")  # Bonus for RSI confluence in alpha score
    ALPHA_VOLUME_BOOST_MULTIPLIER: Decimal = Decimal("5.0")  # Multiplier for volume boost in alpha score
    ALPHA_VOLUME_BOOST_CAP: Decimal = Decimal("10.0")  # Cap for volume boost in alpha score
    RSI_CONFLUENCE_UPPER: Decimal = Decimal("60")  # Upper RSI threshold for confluence
    RSI_CONFLUENCE_LOWER: Decimal = Decimal("40")  # Lower RSI threshold for confluence
    FISHER_COMPONENT_DIVISOR: Decimal = Decimal("3.0")  # Divisor for Fisher component
    RSI_COMPONENT_DIVISOR: Decimal = Decimal("50.0")  # Divisor for RSI component
    MAX_FISHER_COMPONENT: Decimal = Decimal("3.0")  # Max value for Fisher component
    MAX_RSI_COMPONENT: Decimal = Decimal("50.0")  # Max value for RSI component

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

    config: ScalperConfig = field()  # Configuration object for the bot

    # Vault Essence
    equity: Decimal = Decimal("0")  # Current total equity in the account
    available: Decimal = Decimal("0")  # Available balance for trading
    initial_equity_session: Decimal = Decimal("0")  # Equity at the start of the current session
    initial_equity_daily: Decimal = Decimal("0")  # Equity at the start of the current day
    last_daily_reset_date: str = ""  # Date of the last daily PnL reset
    current_session_pnl: Decimal = Decimal("0")  # Profit/Loss for the current session
    current_session_pnl_pct: Decimal = Decimal("0")  # Profit/Loss percentage for the current session
    daily_pnl: Decimal = Decimal("0")  # Daily Profit/Loss
    daily_pnl_pct: Decimal = Decimal("0")  # Daily Profit/Loss percentage
    daily_profit_reached: bool = False  # Flag if daily profit target is reached
    daily_loss_reached: bool = False  # Flag if daily loss limit is reached
    total_realized_pnl_session: Decimal = Decimal("0")  # Total realized PnL for the session
    smoothed_realized_pnl: SmoothedPnL = field(default_factory=SmoothedPnL)  # Smoothed realized PnL for analysis

    # Market Pulse
    price: Decimal = Decimal("0")  # Current market price
    bid: Decimal = Decimal("0")  # Current best bid price
    ask: Decimal = Decimal("0")  # Current best ask price
    obi_score: float = 0.0  # Order Book Imbalance score
    ema_fast: Decimal = Decimal("0")  # Fast Exponential Moving Average
    ema_macro: Decimal = Decimal("0")  # Macro Exponential Moving Average
    vwap: Decimal = Decimal("0")  # Volume Weighted Average Price
    atr: float = 0.0  # Average True Range
    rsi: float = 0.0  # Relative Strength Index
    fisher: float = 0.0  # Fisher Transform value
    fisher_sig: float = 0.0  # Fisher Transform signal line
    alpha_score: float = 0.0  # Composite alpha score for signal strength
    vsi: float = 1.0  # Volume Strength Index
    bollinger_upper: float = 0.0  # Bollinger Band Upper
    bollinger_lower: float = 0.0  # Bollinger Band Lower
    bollinger_width_pct: float = 0.0  # Bollinger Band Width Percentage

    # Ehlers Specific
    superpass_signal: float = 0.0  # Ehlers SuperPass filter signal
    trend_signal: float = 0.0  # Ehlers trend signal (0=Down, 1=Up)
    cycle_period: float = 0.0  # Estimated Ehlers cycle period

    # Precision Glyphs
    price_prec: int = 2  # Price precision (number of decimal places)
    qty_step: Decimal = Decimal("0.01")  # Quantity step for orders
    min_qty: Decimal = Decimal("0.01")  # Minimum order quantity

    # Data Buffers
    ohlc: Deque[Tuple[float, float, float, float, float]] = field(
        default_factory=lambda: deque(maxlen=400)
    )  # OHLC (Open, High, Low, Close, Volume) data for primary interval
    ohlc_5m: Deque[Tuple[float, float, float, float, float]] = field(
        default_factory=lambda: deque(maxlen=100)
    )  # OHLC data for 5-minute interval

    # Position Realm
    active: bool = False  # True if a position is currently active
    side: str = "HOLD"  # Current position side ("Buy", "Sell", "HOLD")
    qty: Decimal = Decimal("0")  # Current position quantity
    entry_p: Decimal = Decimal("0")  # Position entry price
    upnl: Decimal = Decimal("0")  # Unrealized Profit/Loss
    last_trade_pnl: Decimal = Decimal("0")  # PnL of the last closed trade
    entry_ts: float = 0.0  # Timestamp of position entry
    stage: int = 0  # Current stage of position management (e.g., 0=no position, 1=initial, 2=partial TP taken)
    trailing_sl_value: Decimal = Decimal("0")  # Value of the active trailing stop loss

    # Ledger & Timing
    trade_count: int = 0  # Total number of trades in the current day
    wins: int = 0  # Total number of winning trades in the current day
    loss_streak: int = 0  # Current consecutive loss streak
    latency: int = 0  # WebSocket latency in milliseconds
    api_latency: int = 0  # API request latency in milliseconds
    last_trade_ts: float = 0.0  # Timestamp of the last trade
    stasis_until: float = 0.0  # Timestamp until which the bot is in stasis
    stasis_reason: str = "NONE"  # Reason for stasis
    last_leverage_adjust_ts: float = 0.0  # Timestamp of the last leverage adjustment

    # Termux Specific
    battery_level: int = -1  # Current device battery level
    battery_status: str = "UNKNOWN"  # Current device battery status
    battery_alert_sent: bool = False  # Flag if a low battery alert has been sent

    # Entry Confirmation
    signal_confirmed_candles: int = 0  # Number of candles confirming the current signal
    last_signal_direction: str = "NONE"  # Direction of the last confirmed signal
    signal_strength: int = 0  # Strength of the current signal (0-100)
    last_order_id: Optional[str] = None # ID of the last placed order

    # Configuration Reload
    last_config_mod_time: float = 0.0  # Last modification time of the config file

    # Chronicles
    chronicles: Deque[str] = field(default_factory=lambda: deque(maxlen=24))  # Log of recent events
    ready: bool = False  # Flag indicating if the bot is ready to trade

    local_bids: Dict[Decimal, Decimal] = field(default_factory=dict)  # Local order book bids
    local_asks: Dict[Decimal, Decimal] = field(default_factory=dict)  # Local order book asks

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
        params: Optional[Dict[str, Any]] = None,
        retries: int = 3,
        backoff: float = 2.0,
    ) -> Dict[str, Any]:
        """
        Unified Bybit v5 REST request wrapper.
        - Handles signing, retries, rate-limit backoff.
        - Strips None values from params.
        - Returns dict with at least {retCode, retMsg, result?, http_status}.
        """
        params = {k: v for k, v in (params or {}).items() if v is not None}

        ts = str(int(time.time() * 1000))
        TermuxAPI.wake_lock()

        delay = 1.0
        last_error: Optional[str] = None

        try:
            for attempt in range(1, retries + 1):
                if not self.session:
                    conn = aiohttp.TCPConnector(limit=15, ttl_dns_cache=360)
                    self.session = aiohttp.ClientSession(
                        connector=conn,
                        timeout=aiohttp.ClientTimeout(total=15),
                    )

                start_time = time.time()
                try:
                    if method.upper() == "GET":
                        query = urllib.parse.urlencode(sorted(params.items()))
                        payload = query
                        url = f"{self.base}{path}?{query}"
                        data = None
                    else:
                        payload = json.dumps(params, separators=(",", ":"))
                        url = f"{self.base}{path}"
                        data = payload

                    headers = {
                        "X-BAPI-API-KEY": API_KEY,
                        "X-BAPI-SIGN": self._sign(payload, ts),
                        "X-BAPI-TIMESTAMP": ts,
                        "X-BAPI-RECV-WINDOW": "5000",
                        "Content-Type": "application/json",
                    }

                    async with self.session.request(
                        method.upper(), url, headers=headers, data=data
                    ) as r:
                        self.state.api_latency = int((time.time() - start_time) * 1000)
                        http_status = r.status

                        try:
                            r_json = await r.json()
                        except Exception:
                            r_text = await r.text()
                            last_error = f"Invalid JSON (HTTP {http_status}): {r_text[:256]}"
                            self._report_error(last_error, "error", 101)
                            if attempt < retries:
                                await asyncio.sleep(delay)
                                delay *= backoff
                                continue
                            return {"retCode": -1, "retMsg": last_error, "http_status": http_status}

                        ret_code = r_json.get("retCode", -1)
                        ret_msg = r_json.get("retMsg", "Unknown")

                        # HTTP error but JSON parsed
                        if http_status >= 400:
                            last_error = f"HTTP {http_status} {method} {path}: {ret_msg}"
                            self._report_error(last_error, "error", 101)
                            if attempt < retries:
                                await asyncio.sleep(delay)
                                delay *= backoff
                                continue
                            r_json["http_status"] = http_status
                            return r_json

                        # Bybit rate limit or transient errors
                        if ret_code in (10001, 10006, 10016):  # examples: rate limit / server busy
                            last_error = f"Bybit transient error {ret_code} on {method} {path}: {ret_msg}"
                            self.state.log(
                                f"{Fore.YELLOW}{last_error} (retry {attempt}/{retries}, delay {delay:.1f}s){Style.RESET_ALL}",
                                "warn",
                            )
                            TermuxAPI.notify("Bybit Rate/Server", ret_msg, id=101)
                            if attempt < retries:
                                await asyncio.sleep(delay)
                                delay *= backoff
                                continue
                            r_json["http_status"] = http_status
                            return r_json

                        # Success
                        self.state.log(
                            f"# API {method} {path} OK (retCode={ret_code}, {self.state.api_latency}ms)",
                            "debug",
                        )
                        r_json["http_status"] = http_status
                        return r_json

                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    last_error = f"Network error on {method} {path}: {e}"
                    self._report_error(last_error, "error", 101)
                    if attempt < retries:
                        await asyncio.sleep(delay)
                        delay *= backoff
                        continue

                except Exception as e:
                    last_error = f"Unexpected error on {method} {path}: {e}"
                    self._report_error(last_error, "error", 101)
                    if attempt < retries:
                        await asyncio.sleep(delay)
                        delay *= backoff
                        continue

            # If we get here, all retries failed
            msg = last_error or f"Max retries exceeded for {method} {path}"
            self._report_error(msg, "error", 101)
            return {"retCode": -1, "retMsg": msg, "http_status": None}

        finally:
            TermuxAPI.wake_unlock()

    def _report_error(self, msg: str, level: str, notify_id: int):
        """Unified error logging and notification utility (Improvement 13)."""
        self.state.log(f"{Fore.RED}{msg}{Style.RESET_ALL}", level)
        TermuxAPI.notify("Bybit API Error", msg, id=notify_id)

    async def sync_instrument(self) -> None:
        """Sync price/qty filters and validate symbol."""
        self.state.log(
            f"{Fore.CYAN}# Syncing instrument info...{Style.RESET_ALL}",
            "health",
        )

        r = await self.request(
            "GET",
            "/v5/market/instruments-info",
            {"category": self.cfg.category, "symbol": self.cfg.symbol},
            signed=False,
        )

        if r.get("retCode") != 0:
            self._report_error(
                f"Failed to sync instrument info: {r.get('retMsg')}",
                "error",
                102,
            )
            return

        result = r.get("result", {})
        lst = result.get("list") or []
        if not lst:
            self._report_error(
                f"No instrument info returned for {self.cfg.symbol}",
                "error",
                102,
            )
            return

        info = lst[0]
        price_filter = info.get("priceFilter", {})
        tick_size = safe_decimal(price_filter.get("tickSize", "0.01"))

        if tick_size <= 0:
            self._report_error("Invalid tickSize from instrument info.", "error", 102)
            return

        self.state.price_prec = abs(tick_size.normalize().as_tuple().exponent)

        lot_filter = info.get("lotSizeFilter") or info.get("lotFilter") or {}
        qty_step = safe_decimal(lot_filter.get("qtyStep", "0.001"))
        min_qty = safe_decimal(lot_filter.get("minOrderQty", "0.001"))

        if qty_step <= 0 or min_qty <= 0:
            self._report_error("Invalid lot filter in instrument info.", "error", 102)
            return

        self.state.qty_step = qty_step
        self.state.min_qty = min_qty

        self.state.log(
            f"{Fore.GREEN}Instrument synced: tick={tick_size}, qty_step={qty_step}, min_qty={min_qty}.{Style.RESET_ALL}",
            "info",
        )

    async def set_leverage(self, lev: int) -> bool:
        """Set symmetric leverage for symbol; returns success state."""
        cfg = self.cfg
        lev_str = str(lev)

        r = await self.request(
            "POST",
            "/v5/position/set-leverage",
            {
                "category": cfg.category,
                "symbol": cfg.symbol,
                "buyLeverage": lev_str,
                "sellLeverage": lev_str,
            },
        )

        if r.get("retCode") == 0:
            old = cfg.leverage
            cfg.leverage = lev
            self.state.log(
                f"{Fore.GREEN}Leverage set to {lev}x (from {old}x).{Style.RESET_ALL}",
                "info",
            )
            return True

        self._report_error(
            f"Failed to set leverage: {r.get('retMsg')}",
            "error",
            103,
        )
        return False

    async def _set_leverage(self, lev: int) -> None:
        cfg, s = self.cfg, self.state
        res = await self.request(
            "POST",
            "/v5/position/set-leverage",
            {
                "category": cfg.category,
                "symbol": cfg.symbol,
                "buyLeverage": str(lev),
                "sellLeverage": str(lev),
            },
        )
        if res.get("retCode") == 0:
            cfg.leverage = lev
            s.log(f"{Fore.GREEN}Leverage set to {lev}x.{Style.RESET_ALL}", "info")
        else:
            self._report_error(f"Failed to set leverage: {res.get('retMsg')}", "error", 103)

    async def boot_ritual(self) -> None:
        s, cfg = self.state, self.cfg
        s.log(f"{Fore.CYAN}# Syncing Instrument Ritual...{Style.RESET_ALL}", "health")

        r = await self.request(
            "GET",
            "/v5/market/instruments-info",
            {"category": cfg.category, "symbol": cfg.symbol},
        )

        if r.get("retCode") == 0 and r.get("result", {}).get("list"):
            i = r["result"]["list"][0]

            # price precision
            tick = safe_decimal(i.get("priceFilter", {}).get("tickSize"))
            if tick > 0:
                s.price_prec = abs(tick.normalize().as_tuple().exponent)

            # qty filter (lotFilter or lotSizeFilter)
            lf = i.get("lotFilter") or i.get("lotSizeFilter") or {}
            try:
                qty_step = safe_decimal(lf.get("qtyStep"))
                min_qty = safe_decimal(lf.get("minOrderQty"))
                if qty_step > 0 and min_qty > 0:
                    s.qty_step = qty_step
                    s.min_qty = min_qty
                else:
                    raise ValueError("Non‑positive qtyStep/minOrderQty")
            except Exception as e:
                self._report_error(f"Invalid lot filter: {e}", "error", 102)

            s.log(
                f"{Fore.GREEN}Instrument info synced: tick={tick}, qty_step={s.qty_step}, min_qty={s.min_qty}.{Style.RESET_ALL}",
                "info",
            )
        else:
            self._report_error(f"Failed to sync instrument info: {r.get('retMsg')}", "error", 102)

        # set leverage
        await self._set_leverage(cfg.initial_max_leverage)
        await self._auto_adjust_leverage()

        # bootstrap wallet with retries
        for _ in range(3):
            await self.update_wallet()
            if s.initial_equity_session > Decimal("0"):
                break
            await asyncio.sleep(1.0)

    async def fetch_history(self) -> None:
        s, cfg = self.state, self.cfg
        s.log(f"{Fore.CYAN}# Summoning ancient kline scrolls...{Style.RESET_ALL}", "health")

        need = max(cfg.warmup_candles + 20, cfg.rsi_period + cfg.bollinger_window + 20)
        remaining = need
        interval = cfg.kline_interval
        category = cfg.category
        symbol = cfg.symbol

        candles: List[Tuple[float, float, float, float, float]] = []
        cursor: Optional[str] = None

        while remaining > 0:
            limit = min(200, remaining)  # Bybit v5 typical limit; adjust if needed
            params = {
                "category": category,
                "symbol": symbol,
                "interval": interval,
                "limit": str(limit),
            }
            if cursor:
                params["cursor"] = cursor

            r = await self.request("GET", "/v5/market/kline", params)
            if r.get("retCode") != 0:
                self._report_error(f"Kline fetch failed: {r.get('retMsg')}", "error", 104)
                break

            result = r.get("result", {})
            lst = result.get("list") or []
            cursor = result.get("nextPageCursor")
            if not lst:
                break

            # Bybit returns newest first; reverse to chronological
            for k in reversed(lst):
                # kline schema: [startTime, open, high, low, close, volume, ...]
                candles.append((float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])))

            remaining -= len(lst)
            if not cursor:
                break

        # keep only the latest 'need' candles
        candles = candles[-need:]

        for c in candles:
            s.ohlc.append(c)

        s.log(
            f"{Fore.GREEN}Kline scrolls unveiled: {len(s.ohlc)} candles (needed {need}).{Style.RESET_ALL}",
            "info",
        )

        # optional 5m history similar pattern...
        self._update_oracle()

    async def update_wallet(self) -> None:
        """Sync wallet equity & available, with daily PnL accounting."""
        r = await self.request(
            "GET",
            "/v5/account/wallet-balance",
            {"accountType": "UNIFIED"},
        )

        if r.get("retCode") != 0:
            self._report_error(
                f"Failed to update wallet: {r.get('retMsg')}",
                "error",
                105,
            )
            return

        result = r.get("result", {})
        lst = result.get("list") or []
        if not lst:
            self._report_error("Wallet list empty.", "error", 105)
            return

        # For UNIFIED, totalEquity/totalAvailableBalance at account level
        acc = lst[0]
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
            f"{Fore.GREEN}Wallet synced. Equity: {self.state.equity:.2f} USDT. "
            f"Daily PnL: {self.state.daily_pnl:+.2f}.{Style.RESET_ALL}",
            "info",
        )

    def _calculate_obi_component(self) -> Decimal:
        s = self.state
        return min(Decimal("1.0"), abs(s.obi_score))

    def _calculate_fisher_component(self) -> Decimal:
        s, cfg = self.state, self.cfg
        return min(cfg.MAX_FISHER_COMPONENT, abs(s.fisher)) / cfg.FISHER_COMPONENT_DIVISOR

    def _calculate_rsi_component(self) -> Decimal:
        s, cfg = self.state, self.cfg
        return min(cfg.MAX_RSI_COMPONENT, abs(s.rsi - Decimal("50.0"))) / cfg.RSI_COMPONENT_DIVISOR

    def _apply_trend_confluence_bonus(self, score: float) -> float:
        s, cfg = self.state, self.cfg
        if (s.trend_signal == 1.0 and s.fisher > 0) or (s.trend_signal == 0.0 and s.fisher < 0):
            score += float(cfg.ALPHA_TREND_CONFLUENCE_BONUS)
        return score

    def _apply_rsi_confluence_bonus(self, score: float) -> float:
        s, cfg = self.state, self.cfg
        rsi_confluence = (s.fisher > 0 and s.rsi < float(cfg.RSI_CONFLUENCE_UPPER)) or (s.fisher < 0 and s.rsi > float(cfg.RSI_CONFLUENCE_LOWER))
        if rsi_confluence:
            score += float(cfg.ALPHA_RSI_CONFLUENCE_BONUS)
        return score

    def _apply_volume_boost(self, score: float) -> float:
        s, cfg = self.state, self.cfg
        if s.vsi > cfg.vsi_threshold:
            volume_boost = min(float(cfg.ALPHA_VOLUME_BOOST_CAP), (s.vsi - cfg.vsi_threshold) * float(cfg.ALPHA_VOLUME_BOOST_MULTIPLIER))
            score += volume_boost
        return score

    def _update_oracle(self, live_p: float = None):
        """
        Weaves the threads of market data into mystical indicators, including Ehlers indicators and a composite alpha score.
        """
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

        score += float(cfg.ALPHA_OBI_WEIGHT * self._calculate_obi_component())
        score += float(cfg.ALPHA_FISHER_WEIGHT * self._calculate_fisher_component())
        score += float(cfg.ALPHA_RSI_WEIGHT * self._calculate_rsi_component())

        score = self._apply_trend_confluence_bonus(score)
        score = self._apply_rsi_confluence_bonus(score)
        score = self._apply_volume_boost(score)

        s.alpha_score = max(0.0, min(100.0, score))
        s.ready = (
            len(s.ohlc)
            >= max(cfg.warmup_candles, cfg.rsi_period, cfg.bollinger_window) + 10
        )

    def _compute_signal_components(self) -> tuple[str, float]:
        """
        Computes a directional signal (LONG/SHORT/NONE) and its strength (0-100) based on
        weighted contributions from order book imbalance, momentum indicators (Fisher, RSI),
        and Ehlers trend signals.
        """
        s, cfg = self.state, self.cfg

        # Order book direction
        obi_dir = 1 if s.obi_score > 0 else -1 if s.obi_score < 0 else 0
        obi_mag = min(abs(s.obi_score) * 100.0, 100.0)

        # Fisher, RSI as momentum
        mom_dir = 1 if s.fisher > 0 else -1 if s.fisher < 0 else 0
        rsi_dev = s.rsi - 50.0  # >0 overbought, <0 oversold
        rsi_dir = -1 if rsi_dev > 0 else 1 if rsi_dev < 0 else 0
        rsi_mag = min(abs(rsi_dev), 25.0) * 2.0  # cap

        # Trend direction from Ehlers
        trend_dir = 1 if s.trend_signal == 1.0 else -1 if s.trend_signal == 0.0 else 0

        # Weighted directional vote
        obi_component_score = cfg.OBI_WEIGHT * obi_dir * obi_mag
        momentum_component_score = cfg.MOMENTUM_WEIGHT * mom_dir * min(abs(s.fisher) * cfg.FISHER_MAG_MULTIPLIER, cfg.FISHER_MAG_MULTIPLIER)
        rsi_component_score = cfg.RSI_WEIGHT * rsi_dir * min(abs(rsi_dev), cfg.RSI_MAG_CAP) * cfg.RSI_MAG_MULTIPLIER
        trend_component_score = cfg.TREND_WEIGHT * trend_dir * cfg.TREND_MAG_MULTIPLIER

        dir_score = (
            obi_component_score +
            momentum_component_score +
            rsi_component_score +
            trend_component_score
        )

        if dir_score > cfg.DIR_SCORE_THRESHOLD:
            direction = "LONG"
        elif dir_score < -cfg.DIR_SCORE_THRESHOLD:
            direction = "SHORT"
        else:
            direction = "NONE"

        strength = min(abs(dir_score), cfg.TREND_MAG_MULTIPLIER)

        return direction, strength

    async def _auto_adjust_leverage(self):
        """Adjusts leverage dynamically based on market volatility (ATR) and winrate."""
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
            await self._set_leverage(new_lev)
            s.last_leverage_adjust_ts = now
            s.log(
                f"{Fore.GREEN}# Adjusted leverage to {new_lev}x (from {self.cfg.leverage}x) due to volatility {s.atr:.2f} and win rate {win_rate:.2f}.{Style.RESET_ALL}",
                "health",
            )

    async def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        cfg = self.cfg
        r = await self.request(
            "GET",
            "/v5/order/realtime",
            {
                "category": cfg.category,
                "symbol": cfg.symbol,
                "orderId": order_id,
            },
        )

        if r.get("retCode") != 0:
            self._report_error(
                f"Failed to get order {order_id}: {r.get('retMsg')}",
                "error",
                106,
            )
            return None

        result = r.get("result") or {}
        # v5 returns list; unify to first item if present
        if isinstance(result, dict) and "list" in result:
            lst = result.get("list") or []
            return lst[0] if lst else None

        return result

    async def confirm_order_filled(
        self,
        order_id: str,
        max_retries: int = 5,
        delay_sec: float = 0.5,
    ) -> bool:
        s = self.state

        for attempt in range(max_retries):
            order = await self.get_order(order_id)
            if not order:
                await asyncio.sleep(delay_sec)
                continue

            status = order.get("orderStatus")
            if status == "Filled":
                s.log(f"Order {order_id} confirmed FILLED.", "debug")
                return True

            if status in ("Cancelled", "Rejected"):
                s.log(f"Order {order_id} {status}.", "warn")
                return False

            s.log(
                f"Order {order_id} not filled yet (status={status}). Retry {attempt+1}/{max_retries}.",
                "debug",
            )
            await asyncio.sleep(delay_sec)

        self._report_error(
            f"Order {order_id} not filled after {max_retries} checks.",
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
    ) -> bool:
        trail_atr = Decimal(str(atr)) * cfg.trail_atr_mult
        if trail_atr <= 0:
            return False

        price_step = Decimal(f"1e-{price_prec}")
        trailing_stop = quantize_to_step(trail_atr, price_step)

        r = await self.request(
            "POST",
            "/v5/position/trading-stop",
            {
                "category": cfg.category,
                "symbol": cfg.symbol,
                "trailingStop": str(trailing_stop),
                "positionIdx": 0,
            },
        )

        if r.get("retCode") != 0:
            state.log(
                f"Failed to set trailing stop: {r.get('retMsg')}",
                "error",
            )
            return False

        state.trailing_sl_value = trailing_stop
        state.log(
            f"Trailing stop set at {trailing_stop:.{price_prec}f}",
            "info",
        )
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

    async def create_order(
        self,
        side: str,
        qty: Decimal,
        order_type: str = "Limit",
        price: Optional[Decimal] = None,
        reduce_only: bool = False,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None,
        position_idx: int = 0,
    ) -> Tuple[bool, Optional[str], str]:
        """
        Wrapper around /v5/order/create.
        Returns (ok, orderId, retMsg).
        """
        s, cfg = self.state, self.cfg
        qty = quantize_to_step(qty, s.qty_step)

        if qty < s.min_qty:
            msg = f"Qty {qty} < minQty {s.min_qty}"
            s.log(f"{Fore.YELLOW}{msg}{Style.RESET_ALL}", "warn")
            return False, None, msg

        params: Dict[str, Any] = {
            "category": cfg.category,
            "symbol": cfg.symbol,
            "side": side,
            "orderType": order_type,
            "qty": str(qty),
            "reduceOnly": reduce_only,
            "timeInForce": "GoodTillCancel",
            "positionIdx": position_idx,
        }

        price_step = Decimal(f"1e-{s.price_prec}")
        if order_type == "Limit" and price is not None:
            params["price"] = str(quantize_to_step(price, price_step))

        if stop_loss is not None:
            params["stopLoss"] = str(quantize_to_step(stop_loss, price_step))

        if take_profit is not None:
            params["takeProfit"] = str(quantize_to_step(take_profit, price_step))

        r = await self.request("POST", "/v5/order/create", params)
        if r.get("retCode") == 0:
            order_id = (r.get("result") or {}).get("orderId")
            s.last_order_id = order_id
            return True, order_id, "OK"
        else:
            msg = r.get("retMsg", "Unknown")
            self._report_error(f"Order create failed: {msg}", "error", 106)
            return False, None, msg

    async def strike(
        self,
        side: str,
        qty: Decimal,
        reduce: bool = False,
        order_type: str = "Limit",
        price: Optional[Decimal] = None,
        take_profit_price: Optional[Decimal] = None,
        stop_loss_price: Optional[Decimal] = None,
    ) -> Optional[str]:
        """
        Executes an order, attempting Limit first, then Market with slippage control.
        Returns the order_id if successful, None otherwise.
        """
        s, cfg = self.state, self.cfg

        quantized_qty = quantize_to_step(qty, s.qty_step)
        if quantized_qty < s.min_qty:
            s.log(
                f"Calculated quantity {qty} too small ({quantized_qty}). Minimum is {s.min_qty}. Withheld strike.",
                "warn",
            )
            TermuxAPI.toast("Strike withheld: Qty too small!")
            return None

        exit_ref_price = s.entry_p if s.active else s.price
        atr_dec = Decimal(str(s.atr))
        price_step = Decimal(f"1e-{s.price_prec}")

        final_sl_price = None
        if stop_loss_price is not None:
            final_sl_price = quantize_to_step(max(cfg.MIN_TP_SL_PRICE, stop_loss_price), price_step)
        elif not reduce and atr_dec > 0:
            sl_raw = (
                exit_ref_price - atr_dec * cfg.sl_atr_mult
                if side == "Buy"
                else exit_ref_price + atr_dec * cfg.sl_atr_mult
            )
            final_sl_price = quantize_to_step(max(cfg.MIN_TP_SL_PRICE, sl_raw), price_step)

        final_tp_price = None
        if take_profit_price is not None:
            final_tp_price = quantize_to_step(max(cfg.MIN_TP_SL_PRICE, take_profit_price), price_step)
        else:
            tp_raw = (
                exit_ref_price + atr_dec * cfg.tp_partial_atr_mult
                if side == "Buy"
                else exit_ref_price - atr_dec * cfg.tp_partial_atr_mult
            )
            final_tp_price = quantize_to_step(max(cfg.MIN_TP_SL_PRICE, tp_raw), price_step)

        r = await self.create_order(
            side=side,
            qty=quantized_qty,
            order_type=order_type,
            reduce_only=reduce,
            price=price,
            stop_loss=final_sl_price,
            take_profit=final_tp_price,
        )

        if r.get("retCode") == 0:
            order_id = r["result"].get("orderId")
            if not reduce:
                is_filled = await self.confirm_order_filled(order_id)
                if is_filled:
                    s.active = True
                    s.side = side
                    s.entry_ts = time.time()
                    s.stage = 1
                    await self.update_wallet()
            return order_id
        else:
            return None

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
                # Close position with a Limit order first
                exit_side = "Sell" if s.side == "Buy" else "Buy"
                exit_price = s.price # Use current price as anchor for exit limit
                await self._place_order_with_fallback(
                    side=exit_side,
                    qty=s.qty,
                    limit_price=exit_price,
                    sl_price=Decimal("0"), # No SL on exit
                    tp_price=Decimal("0"), # No TP on exit
                    wait_time=float(cfg.WAIT_TIME_MIN_SEC), # Short wait for exit
                    reduce_only=True,
                    log_prefix="LIMIT_HIT_CLOSE",
                    log_level="exit",
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

    async def get_position(self) -> Optional[Dict[str, Any]]:
        """Return first open position for cfg.symbol, or None."""
        cfg = self.cfg
        r = await self.request(
            "GET",
            "/v5/position/list",
            {"category": cfg.category, "symbol": cfg.symbol},
        )

        if r.get("retCode") != 0:
            self._report_error(
                f"Failed to get position: {r.get('retMsg')}",
                "error",
                118,
            )
            return None

        pos_list = r.get("result", {}).get("list") or []
        if not pos_list:
            return None

        # v5 returns per symbol entry; you already filter by symbol
        pos = pos_list[0]
        if pos.get("symbol") != cfg.symbol:
            return None

        return pos

    async def _reconcile_position(self):
        s, cfg = self.state, self.cfg
        if not s.active:
            return

        pos = await self.get_position()
        if not pos:
            if s.active:
                self._report_error(
                    "Position vanished from API; clearing local state.",
                    "error",
                    118,
                )
                s.active = False
                s.stage = 0
            return

        size = safe_decimal(pos.get("size"))
        if size <= 0:
            s.active = False
            s.stage = 0
            return

        s.qty = size
        s.side = pos.get("side", s.side)
        s.entry_p = safe_decimal(pos.get("avgPrice"))
        s.upnl = safe_decimal(pos.get("unrealisedPnl"))

        s.log(
            f"Position reconciled via REST. Qty: {s.qty}, Entry: {s.entry_p}.",
            "health",
        )

    async def _manage_active_position(self):
        """Manages an active position: partial TP, trailing SL, max hold time."""
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
                Decimal(str(s.atr * float(cfg.EARLY_TP_ATR_MULTIPLIER))) * s.qty
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
            exit_side = "Sell" if s.side == "Buy" else "Buy"
            exit_price = s.price # Use current price as anchor for exit limit
            await self._place_order_with_fallback(
                side=exit_side,
                qty=s.qty,
                limit_price=exit_price,
                sl_price=Decimal("0"), # No SL on exit
                tp_price=Decimal("0"), # No TP on exit
                wait_time=float(cfg.WAIT_TIME_MIN_SEC), # Short wait for exit
                reduce_only=True,
                log_prefix="REAPER",
                log_level="exit",
            )
            TermuxAPI.toast("Max hold time reached!")

    async def _check_entry_cooldown(self) -> bool:
        s, cfg = self.state, self.cfg
        dt = time.time() - s.last_trade_ts
        dynamic_cooldown = cfg.cooldown_base
        if s.last_trade_pnl > 0:
            dynamic_cooldown *= cfg.DYNAMIC_COOLDOWN_PROFIT_MULTIPLIER
        return dt < dynamic_cooldown

    def _check_entry_guards(self) -> bool:
        s, cfg = self.state, self.cfg
        return s.atr < cfg.min_atr_threshold or s.price <= 0

    def _check_bollinger_filter(self) -> bool:
        s, cfg = self.state, self.cfg
        if not self.bollinger_band_filter(s, cfg):
            s.signal_confirmed_candles = 0
            s.last_signal_direction = "NONE"
            s.signal_strength = 0
            return False
        return True

    def _check_ema_alignment(self, strength: float) -> bool:
        s, cfg = self.state, self.cfg
        ema_f, ema_m = s.ema_fast, s.ema_macro
        if ema_m == 0:
            return False
        ema_proximity = safe_div(abs(s.price - ema_f), ema_f)
        max_proximity = cfg.price_ema_proximity_pct * (cfg.STRENGTH_FACTOR_MAX if strength >= cfg.STRENGTH_EMA_PROXIMITY_THRESHOLD else Decimal("1.0"))
        return ema_proximity > max_proximity

    def _check_signal_confirmation(self, direction: str, strength: float) -> bool:
        s, cfg = self.state, self.cfg
        required_candles = cfg.entry_confirmation_candles
        side_str = "BUY" if direction == "LONG" else "SELL"
        confirmed = confirm_signal(s, side_str, required_candles)
        return confirmed or strength >= cfg.STRENGTH_TIERED_ENTRY_THRESHOLD

    async def _evaluate_entry_signals(self) -> None:
        s, cfg = self.state, self.cfg

        if await self._check_entry_cooldown():
            return

        if self._check_entry_guards():
            return

        if not self._check_bollinger_filter():
            return

        direction, strength = self._compute_signal_components()
        if direction == "NONE":
            s.signal_confirmed_candles = 0
            s.last_signal_direction = "NONE"
            s.signal_strength = 0
            return

        s.signal_strength = int(strength)

        if self._check_ema_alignment(strength):
            return

        if not self._check_signal_confirmation(direction, strength):
            return

        await self._execute_entry_with_aggression(direction, strength)

    def _calculate_risk_percentage(self, strength: float) -> Decimal:
        s, cfg = self.state, self.cfg
        strength_factor = cfg.STRENGTH_FACTOR_MIN + (strength / 100.0)
        strength_factor = min(max(strength_factor, cfg.STRENGTH_FACTOR_MIN), cfg.STRENGTH_FACTOR_MAX)

        win_rate = safe_div(Decimal(s.wins), Decimal(max(1, s.trade_count)), cfg.STRENGTH_FACTOR_MIN)
        risk_pct = cfg.risk_per_trade_pct

        if win_rate > Decimal(str(cfg.dynamic_risk_win_rate_threshold)):
            risk_pct *= cfg.dynamic_risk_multiplier_high_win_rate
        elif win_rate < cfg.WIN_RATE_LOW_THRESHOLD:
            risk_pct *= cfg.dynamic_risk_multiplier_low_win_rate

        if s.atr < cfg.low_vol_atr_threshold:
            risk_pct *= cfg.low_volatility_risk_multiplier

        risk_pct *= Decimal(str(strength_factor))
        return min(risk_pct, cfg.MAX_RISK_PER_TRADE_PCT)

    def _calculate_position_quantity(self, risk_pct: Decimal) -> Decimal:
        s, cfg = self.state, self.cfg
        qty = calculate_dynamic_qty(
            available=s.available,
            risk_pct=risk_pct,
            atr=s.atr,
            price=s.price,
            leverage=cfg.leverage,
            qty_step=s.qty_step,
        )
        return qty

    def _calculate_tp_sl_prices(self, side: str) -> Tuple[Decimal, Decimal]:
        s, cfg = self.state, self.cfg
        atr_dec = Decimal(str(s.atr))
        price_step = Decimal(f"1e-{s.price_prec}")

        tp_mult = cfg.tp_partial_atr_mult * (Decimal("1.0") if s.signal_strength < cfg.STRENGTH_EMA_PROXIMITY_THRESHOLD else cfg.TP_STRONG_SIGNAL_MULTIPLIER)
        sl_mult = cfg.sl_atr_mult * (Decimal("1.0") if s.signal_strength < cfg.STRENGTH_EMA_PROXIMITY_THRESHOLD else cfg.SL_STRONG_SIGNAL_MULTIPLIER)

        entry_reference_price = s.price
        if side == "Buy":
            sl_price = entry_reference_price - atr_dec * sl_mult
            tp_price = entry_reference_price + atr_dec * tp_mult
        else:
            sl_price = entry_reference_price + atr_dec * sl_mult
            tp_price = entry_reference_price - atr_dec * tp_price

        sl_price = quantize_to_step(max(cfg.MIN_TP_SL_PRICE, sl_price), price_step)
        tp_price = quantize_to_step(max(cfg.MIN_TP_SL_PRICE, tp_price), price_step)
        return sl_price, tp_price

    async def _execute_entry_with_aggression(self, direction: str, strength: float) -> None:
        s, cfg = self.state, self.cfg

        risk_pct = self._calculate_risk_percentage(strength)
        qty = self._calculate_position_quantity(risk_pct)

        if qty < s.min_qty:
            s.log(
                f"{Fore.YELLOW}Entry {direction} withheld: qty {qty} < min {s.min_qty}.{Style.RESET_ALL}",
                "warn",
            )
            return

        side = "Buy" if direction == "LONG" else "Sell"
        sl_price, tp_price = self._calculate_tp_sl_prices(side, strength)

        # Preferred mode: maker‑friendly limit near best price, with fallback market
        await self._hybrid_entry_order(
            side=side,
            qty=qty,
            limit_anchor_price=s.price,
            sl_price=sl_price,
            tp_price=tp_price,
            aggression=strength,
        )

        s.last_trade_ts = time.time()

    async def _place_order_with_fallback(
        self,
        side: str,
        qty: Decimal,
        limit_price: Decimal,
        sl_price: Decimal,
        tp_price: Decimal,
        wait_time: float,
        reduce_only: bool = False,
        log_prefix: str = "STRIKE",
        log_level: str = "entry",
    ) -> Optional[str]:
        s, cfg = self.state, self.cfg

        params = {
            "category": cfg.category,
            "symbol": cfg.symbol,
            "side": side,
            "orderType": "Limit",
            "qty": str(qty),
            "price": str(limit_price),
            "reduceOnly": reduce_only,
            "timeInForce": "PostOnly",
            "stopLoss": str(sl_price),
            "takeProfit": str(tp_price),
        }

        s.log(
            f"{Fore.CYAN}{log_prefix} {side} LIMIT qty={qty} @ {limit_price}{Style.RESET_ALL}",
            log_level,
        )

        order_id = await self.strike(
            side=side,
            qty=qty,
            reduce=reduce_only,
            order_type="Limit",
            price=limit_price,
            take_profit_price=tp_price,
            stop_loss_price=sl_price,
        )

        if not order_id:
            s.log(f"{Fore.YELLOW}Limit order creation failed; switching to MARKET.{Style.RESET_ALL}", "warn")
            await self.strike(side, qty, reduce=reduce_only, order_type="Market")
            return None

        await asyncio.sleep(wait_time)
        filled = await self.confirm_order_filled(order_id, max_retries=cfg.CONFIRM_ORDER_MAX_RETRIES, delay_sec=wait_time * cfg.CONFIRM_ORDER_DELAY_SEC_MULTIPLIER)

        if filled:
            s.log(f"{Fore.GREEN}Limit order filled as MAKER. ID={order_id}{Style.RESET_ALL}", log_level)
            return order_id
        else:
            s.log(f"{Fore.YELLOW}Limit order not filled; switching to MARKET.{Style.RESET_ALL}", "warn")
            await self.request(
                "POST",
                "/v5/order/cancel",
                {"category": cfg.category, "symbol": cfg.symbol, "orderId": order_id},
            )
            await self.strike(side, qty, reduce=reduce_only, order_type="Market")
            return None

    async def _hybrid_entry_order(
        self,
        side: str,
        qty: Decimal,
        limit_anchor_price: Decimal,
        sl_price: Decimal,
        tp_price: Decimal,
        aggression: float,
    ) -> None:
        """
        Place aggressive limit near anchor; if not filled quickly, fall back to market.
        Higher aggression => tighter to current price and shorter wait.
        """
        s, cfg = self.state, self.cfg

        quantized_qty = quantize_to_step(qty, s.qty_step)
        if quantized_qty < s.min_qty:
            return

        # Aggression 0‑100 -> 5‑60 bps offset and 0.2‑1.0s wait
        max_bps = cfg.LIMIT_MAX_BPS_OFFSET
        min_bps = cfg.LIMIT_MIN_BPS_OFFSET
        offset_bps = min_bps + (1.0 - aggression / 100.0) * (max_bps - min_bps)

        wait_min = cfg.WAIT_TIME_MIN_SEC
        wait_max = cfg.WAIT_TIME_MAX_SEC
        wait_time = wait_max - (aggression / 100.0) * (wait_max - wait_min)

        price_step = Decimal(f"1e-{s.price_prec}")
        if side == "Buy":
            limit_price = limit_anchor_price - limit_anchor_price * Decimal(str(offset_bps))
        else:
            limit_price = limit_anchor_price + limit_anchor_price * Decimal(str(offset_bps))
        limit_price = quantize_to_step(limit_price, price_step)

        await self._place_order_with_fallback(
            side=side,
            qty=quantized_qty,
            limit_price=limit_price,
            sl_price=sl_price,
            tp_price=tp_price,
            wait_time=float(wait_time),
            reduce_only=False,
            log_prefix="STRIKE",
            log_level="entry",
        )

    async def ws_nexus_public(self, stop: asyncio.Event):
        """Channels public market data streams (tickers, orderbook, kline)."""
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
        """Periodically checks device battery status and issues alerts, including critical stasis."""
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
