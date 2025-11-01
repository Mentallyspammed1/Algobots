"""MMPYRM 1.0 - Ultra-Enhanced Bybit Market-Making Bot
--------------------------------------------------
Author: AI Assistant
Original: Pyrmethus
Enhanced with 20+ major improvements and critical bug fixes
"""

import asyncio
import gc
import hashlib
import json
import logging
import logging.handlers
import os
import sys
import time
import uuid
from collections import defaultdict
from collections import deque
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from dataclasses import fields
from datetime import UTC
from datetime import datetime
from decimal import ROUND_DOWN
from decimal import ROUND_UP
from decimal import Decimal
from decimal import DecimalException
from decimal import getcontext
from typing import Any

import psutil

# Optional imports with fallbacks
try:
    import sentry_sdk
except ImportError:
    sentry_sdk = None

try:
    import uvloop

    uvloop.install()  # Install uvloop as the event loop
except ImportError:
    pass

try:
    from plyer import notification

    _HAS_PLYER_NOTIFICATION = True
except ImportError:
    _HAS_PLYER_NOTIFICATION = False
    notification = None  # Ensure notification is None if plyer isn't found


from colorama import Fore
from colorama import Style
from colorama import init
from dotenv import load_dotenv
from pybit.unified_trading import HTTP
from pybit.unified_trading import WebSocket

# Initialize colorama for cross-platform color support
init(autoreset=True)

# High-precision decimals for financial calculations
getcontext().prec = 28  # Increased precision for critical financial calculations

# Enhanced neon color palette (unchanged from v4.0/v5.0)
NC = Style.RESET_ALL
BOLD = Style.BRIGHT
RED = Fore.RED + Style.BRIGHT
GREEN = Fore.GREEN + Style.BRIGHT
YELLOW = Fore.YELLOW + Style.BRIGHT
BLUE = Fore.BLUE + Style.BRIGHT
MAGENTA = Fore.MAGENTA + Style.BRIGHT
CYAN = Fore.CYAN + Style.BRIGHT
WHITE = Style.BRIGHT + Fore.WHITE  # Changed to bright white for consistency
UNDERLINE = Style.BRIGHT + Fore.CYAN

NEON_GREEN = "\033[92m" + Style.BRIGHT
NEON_BLUE = "\033[94m" + Style.BRIGHT
NEON_PINK = "\033[95m" + Style.BRIGHT
NEON_ORANGE = "\033[93m" + Style.BRIGHT
NEON_PURPLE = "\033[35m" + Style.BRIGHT
NEON_CYAN = "\033[96m" + Style.BRIGHT

# Load environment variables
load_dotenv()
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
SENTRY_DSN = os.getenv("SENTRY_DSN")
LOG_AS_JSON = os.getenv("LOG_AS_JSON", "0") == "1"

# Global state management (these will remain global for simplicity of access across modules/functions)
_SHUTDOWN_REQUESTED = False
_HAS_TERMUX_TOAST_CMD = False  # Checked once at startup
BOT_STATE = "INITIALIZING"
CIRCUIT_BREAKER_STATE = "NORMAL"  # NORMAL, MINOR_PAUSE, MAJOR_CANCEL, CRITICAL_SHUTDOWN


# Helper Functions (will access global state where necessary)
# These functions are kept global for convenience and because they interact with global state.
# For a larger project, they might be refactored into a utility class.
def set_bot_state(state: str):
    """Set bot state with enhanced logging"""
    global BOT_STATE
    if state != BOT_STATE:
        log.info(f"Bot state transition: {BOT_STATE} -> {state}")
        BOT_STATE = state
    # Update bot health for state
    state_score = 1.0
    if state == "🚨 CRITICAL_SHUTDOWN" or state == "❌ ERROR":
        state_score = 0.0
    elif state == "🚨 MAJOR_CANCEL":
        state_score = 0.2
    elif state == "🚨 MINOR_PAUSE":
        state_score = 0.5
    elif state == "⏳ WAITING":
        state_score = 0.8
    bot_health.update_component("bot_state", state_score, f"State: {state}")


def calculate_decimal_precision(d: Decimal) -> int:
    """Calculate decimal precision for display"""
    if not isinstance(d, Decimal):
        return 0
    return abs(d.as_tuple().exponent)


def clear_screen() -> None:
    """Clear terminal screen"""
    os.system("cls" if os.name == "nt" else "clear")


def print_neon_header(text: str, color: str = NEON_BLUE, length: int = 80) -> None:
    """Print neon-styled header"""
    if not config.NEON_COLORS_ENABLED:
        color = WHITE

    border_char = "✨"
    max_text_len = length - (len(border_char) * 2 + 4)
    if len(text) > max_text_len:
        text = text[: max_text_len - 3] + "..."
    header_text = f" {border_char}-- {text} --{border_char} "
    padding_total = length - len(header_text)
    padding_left = padding_total // 2
    padding_right = padding_total - padding_left
    full_header_content = f"{' ' * padding_left}{header_text}{' ' * padding_right}"
    print(f"{color}{full_header_content.strip()}{NC}")


def print_neon_separator(
    length: int = 80, char: str = "─", color: str = NEON_BLUE
) -> None:
    """Print neon separator line"""
    if not config.NEON_COLORS_ENABLED:
        color = CYAN
    print(f"{color}{char * length}{NC}")


def format_metric(
    label: str,
    value: Any,
    label_color: str,
    value_color: str | None = None,
    label_width: int = 25,
    value_precision: int | None = None,
    unit: str = "",
    is_pnl: bool = False,
) -> str:
    """Format metric with enhanced neon colors"""
    if not config.NEON_COLORS_ENABLED:
        label_color = WHITE
        value_color = WHITE

    formatted_label = f"{label_color}{label:<{label_width}}{NC}"
    actual_value_color = value_color if value_color else label_color

    if isinstance(value, Decimal):
        current_precision = (
            value_precision
            if value_precision is not None
            else calculate_decimal_precision(value)
        )
        if is_pnl:
            actual_value_color = NEON_GREEN if value >= Decimal("0") else RED
        formatted_value = (
            f"{actual_value_color}{value:,.{current_precision}f}{unit}{NC}"
        )
    elif isinstance(value, (int, float)):
        if is_pnl:
            actual_value_color = NEON_GREEN if value >= 0 else RED
        formatted_value = f"{actual_value_color}{value:,}{unit}{NC}"
    else:
        formatted_value = f"{actual_value_color}{value!s}{unit}{NC}"

    return f"{formatted_label}: {formatted_value}"


def check_termux_toast() -> bool:
    """Check if termux-toast is available"""
    return os.system("command -v termux-toast > /dev/null 2>&1") == 0


# MODIFIED: send_toast function for cross-platform notifications
def send_toast(message: str, color: str = "#336699", text_color: str = "white") -> None:
    """Send toast notification (Termux or Desktop)."""
    if _HAS_TERMUX_TOAST_CMD:
        try:
            os.system(f"termux-toast -b '{color}' -c '{text_color}' '{message}'")
        except Exception as e:
            log.warning(f"Failed to send Termux toast: {e}")
    elif _HAS_PLYER_NOTIFICATION:  # --- NEW: Plyer notification ---
        try:
            notification.notify(
                title="MMXCEL Bot Alert",
                message=message,
                app_name="MMXCEL",
                timeout=5,  # seconds
            )
        except Exception as e:
            log.warning(f"Failed to send Plyer notification: {e}")
    else:
        log.debug(f"Toast notification: {message}")


# --- NEW: Dataclasses for State Management ---
@dataclass
class MarketState:
    """Manages real-time market data and bot's internal state."""

    mid_price: Decimal = Decimal("0")
    best_bid: Decimal = Decimal("0")
    best_ask: Decimal = Decimal("0")

    open_orders: dict[str, dict[str, Any]] = field(
        default_factory=dict
    )  # order_id -> {details}
    positions: dict[str, dict[str, Any]] = field(
        default_factory=dict
    )  # "Long" or "Short" -> {details}

    last_update_time: float = 0.0  # Timestamp of last market data update (WS)
    last_balance_update: float = 0.0  # Timestamp of last balance update (WS or HTTP)
    available_balance: Decimal = Decimal("0")

    price_history: deque[dict[str, Decimal]] = field(
        default_factory=lambda: deque(maxlen=100)
    )  # Stores {'price': Decimal, 'timestamp': float}
    trade_history: deque[dict[str, Any]] = field(
        default_factory=lambda: deque(maxlen=500)
    )  # Stores filled trade details

    data_quality_score: float = 1.0  # Overall score for market data quality

    def update_price_history(self):
        """Adds current mid_price to history."""
        if self.mid_price > Decimal("0"):
            self.price_history.append(
                {"price": self.mid_price, "timestamp": time.time()}
            )

    def add_trade(self, trade_data: dict[str, Any]):
        """Adds a filled trade to history."""
        self.trade_history.append(trade_data)

    def is_data_fresh(self, timeout_seconds: int) -> bool:
        """Checks if market data is fresh and updates health component."""
        current_time = time.time()
        age = current_time - self.last_update_time

        if (
            self.mid_price <= Decimal("0")
            or self.best_bid <= Decimal("0")
            or self.best_ask <= Decimal("0")
        ):
            bot_health.update_component(
                "market_data_freshness", 0.0, "Market data invalid (zero prices)"
            )
            self.data_quality_score = 0.0
            return False

        if age > timeout_seconds:
            bot_health.update_component(
                "market_data_freshness", 0.0, f"Market data stale: {age:.1f}s"
            )
            self.data_quality_score = 0.0
            return False

        # Scale score based on freshness (e.g., 1.0 at 0s, 0.5 at timeout/2, 0.0 at timeout)
        freshness_score = max(0.0, 1.0 - (age / timeout_seconds))
        bot_health.update_component(
            "market_data_freshness",
            float(freshness_score),
            f"Market data age: {age:.1f}s",
        )
        self.data_quality_score = float(freshness_score)
        return True


@dataclass
class SymbolInfo:
    """Stores instrument-specific information like precision and min/max quantities."""

    price_precision: Decimal = Decimal("0.0001")
    qty_precision: Decimal = Decimal("0.001")
    min_price: Decimal = Decimal("0")
    min_qty: Decimal = Decimal("0")
    max_qty: Decimal = Decimal("1000000")  # Default large value
    min_order_value: Decimal = Decimal("10.0")

    bid_levels: list[tuple[Decimal, Decimal]] = field(
        default_factory=list
    )  # (price, quantity)
    ask_levels: list[tuple[Decimal, Decimal]] = field(
        default_factory=list
    )  # (price, quantity)

    def update_orderbook_depth(self, bids: list[list[str]], asks: list[list[str]]):
        """Updates stored orderbook depth levels."""
        self.bid_levels = [(Decimal(p), Decimal(q)) for p, q in bids]
        self.ask_levels = [(Decimal(p), Decimal(q)) for p, q in asks]

    @property
    def total_bid_volume(self) -> Decimal:
        return sum(q for _, q in self.bid_levels)

    @property
    def total_ask_volume(self) -> Decimal:
        return sum(q for _, q in self.ask_levels)

    def get_market_depth_ratio(self, levels: int = 5) -> Decimal:
        """Calculates the ratio of bid volume to ask volume for a given number of levels."""
        bid_vol = sum(q for _, q in self.bid_levels[:levels])
        ask_vol = sum(q for _, q in self.ask_levels[:levels])

        if bid_vol == Decimal("0") and ask_vol == Decimal("0"):
            return Decimal("1")
        if ask_vol == Decimal("0"):
            return Decimal("inf")  # Or a very large number
        if bid_vol == Decimal("0"):
            return Decimal("0")  # Or a very small number

        return bid_vol / ask_vol

    def estimate_slippage(self, side: str, quantity: Decimal) -> Decimal:
        """Estimates slippage for a market order of given quantity."""
        if not self.bid_levels or not self.ask_levels or quantity <= Decimal("0"):
            return Decimal("0")

        filled_qty = Decimal("0")
        cost_sum = Decimal("0")

        levels_to_use = self.ask_levels if side == "Buy" else self.bid_levels

        for price, qty_at_level in levels_to_use:
            if filled_qty + qty_at_level >= quantity:
                remaining_qty = quantity - filled_qty
                cost_sum += remaining_qty * price
                filled_qty += remaining_qty
                break
            cost_sum += qty_at_level * price
            filled_qty += qty_at_level

        if filled_qty == Decimal("0"):
            return Decimal("0")  # Cannot estimate if no liquidity

        avg_fill_price = cost_sum / filled_qty

        # Compare to current best bid/ask
        reference_price = (
            self.ask_levels[0][0] if side == "Buy" else self.bid_levels[0][0]
        )

        if reference_price == Decimal("0"):
            return Decimal("0")

        if side == "Buy":
            slippage = (avg_fill_price - reference_price) / reference_price
        else:  # Sell
            slippage = (reference_price - avg_fill_price) / reference_price

        return max(Decimal("0"), slippage)  # Slippage should be non-negative


@dataclass
class SessionStats:
    """Tracks bot's performance and operational statistics."""

    start_time: float = field(default_factory=time.time)
    orders_placed: int = 0
    orders_filled: int = 0
    orders_cancelled: int = 0
    orders_rejected: int = 0
    rebalances_count: int = 0
    successful_rebalances: int = 0
    circuit_breaker_activations: int = 0
    config_reloads: int = 0
    memory_cleanups: int = 0
    connection_drops: int = 0
    total_volume_traded: Decimal = Decimal("0")
    slippage_events: int = 0  # Count of times high slippage was detected on a fill

    # PnL tracking
    profit_history: deque[tuple[float, Decimal]] = field(
        default_factory=lambda: deque(maxlen=100)
    )  # (timestamp, total_pnl)
    max_drawdown: Decimal = Decimal(
        "0"
    )  # As a percentage of initial capital or peak equity
    peak_pnl: Decimal = Decimal("0")

    api_error_counts: defaultdict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )

    def get_uptime_formatted(self) -> str:
        """Returns formatted uptime string."""
        elapsed = time.time() - self.start_time
        hours, rem = divmod(elapsed, 3600)
        minutes, seconds = divmod(rem, 60)
        return f"{int(hours):02d}h {int(minutes):02d}m {int(seconds):02d}s"

    def get_success_rate(self) -> float:
        """Calculates order success rate (filled / (placed - rejected))."""
        attempted = self.orders_placed - self.orders_rejected
        if attempted <= 0:
            return 0.0
        return (self.orders_filled / attempted) * 100.0

    def record_api_error(self, error_code: str):
        """Records API error by code."""
        self.api_error_counts[error_code] += 1

    def update_pnl(self, current_pnl: Decimal):
        """Updates PnL history and calculates max drawdown."""
        self.profit_history.append((time.time(), current_pnl))

        self.peak_pnl = max(self.peak_pnl, current_pnl)

        # Calculate drawdown as percentage from peak
        if self.peak_pnl > Decimal("0"):
            drawdown = (self.peak_pnl - current_pnl) / self.peak_pnl
            self.max_drawdown = max(self.max_drawdown, drawdown)
        elif current_pnl < Decimal(
            "0"
        ):  # If peak is 0 or negative, and current is negative
            self.max_drawdown = max(
                self.max_drawdown, abs(current_pnl)
            )  # Simple absolute drawdown if no profit yet


@dataclass
class SystemMonitor:
    """Monitors system resources and performs memory cleanup."""

    process: psutil.Process = field(default_factory=psutil.Process)
    _peak_memory_mb: float = 0.0
    _cpu_usage_history: deque[float] = field(
        default_factory=lambda: deque(maxlen=60)
    )  # Last 60 seconds of CPU usage

    def get_memory_usage(self) -> float:
        """Returns current memory usage in MB."""
        try:
            mem_info = self.process.memory_info()
            current_mem_mb = mem_info.rss / (1024 * 1024)  # Resident Set Size
            self._peak_memory_mb = max(self._peak_memory_mb, current_mem_mb)
            return current_mem_mb
        except psutil.NoSuchProcess:
            log.error("Process not found for memory monitoring.")
            return 0.0
        except Exception as e:
            log.error(f"Error getting memory usage: {e}")
            return 0.0

    def get_peak_memory(self) -> float:
        """Returns peak memory usage in MB during bot's runtime."""
        return self._peak_memory_mb

    def get_avg_cpu_usage(self) -> float:
        """Returns average CPU usage over recent history."""
        if not self._cpu_usage_history:
            return 0.0
        return sum(self._cpu_usage_history) / len(self._cpu_usage_history)

    def update_stats(self):
        """Updates CPU and memory stats and health components."""
        current_mem = self.get_memory_usage()
        current_cpu = self.process.cpu_percent(interval=None)  # Non-blocking call
        self._cpu_usage_history.append(current_cpu)

        mem_score = (
            max(0.0, 1.0 - (current_mem / config.CB_HIGH_MEMORY_MB))
            if config.CB_HIGH_MEMORY_MB > 0
            else 1.0
        )
        cpu_score = max(0.0, 1.0 - (current_cpu / 100.0))  # 100% CPU is 0 score

        bot_health.update_component(
            "system_memory", float(mem_score), f"Mem: {current_mem:.1f}MB"
        )
        bot_health.update_component(
            "system_cpu", float(cpu_score), f"CPU: {current_cpu:.1f}%"
        )

    def cleanup_memory(self) -> int:
        """Forces garbage collection and returns number of objects collected."""
        collected = gc.collect()
        log.info(f"Garbage collection: {collected} objects collected.")
        # Update memory health component after cleanup
        current_mem = self.get_memory_usage()
        mem_score = (
            max(0.0, 1.0 - (current_mem / config.CB_HIGH_MEMORY_MB))
            if config.CB_HIGH_MEMORY_MB > 0
            else 1.0
        )
        bot_health.update_component(
            "system_memory_after_cleanup",
            float(mem_score),
            f"Mem after cleanup: {current_mem:.1f}MB",
        )
        return collected


# --- END NEW DATACLASSES ---


# Bot Health Monitoring
class BotHealth:
    """Enhanced health monitoring with weighted components"""

    def __init__(self):
        self.overall_score = 1.0
        self.components = defaultdict(
            lambda: {
                "score": 1.0,
                "last_check": time.time(),
                "message": "OK",
                "weight": 1.0,
            }
        )

        # Set component weights
        self.components["system_memory"]["weight"] = 1.5
        self.components["api_performance"]["weight"] = 1.2
        self.components["market_data_freshness"]["weight"] = 1.3
        self.components["ws_overall_connection"]["weight"] = 2.0  # Critical component
        self.components["bot_state"]["weight"] = 1.0
        self.components["strategy_pnl"]["weight"] = 1.5
        self.components["symbol_info_load"]["weight"] = 1.8
        self.components["api_credentials"]["weight"] = 2.0  # Critical
        self.components["market_spread_quality"]["weight"] = 1.0
        self.components["order_execution_success"]["weight"] = 1.5
        self.components["ws_public_latency"]["weight"] = 1.0
        self.components["ws_private_latency"]["weight"] = 1.0
        self.components["ws_public_data_quality"]["weight"] = 1.0
        self.components["ws_private_data_quality"]["weight"] = 1.0
        self.components["system_cpu"]["weight"] = 1.0
        self.components["system_memory_after_cleanup"]["weight"] = (
            0.5  # Less critical, just informative
        )
        self.components["order_latency_performance"]["weight"] = 1.0

    def update_component(
        self, name: str, score: float, message: str = "OK", weight: float | None = None
    ):
        """Update component with weighted score"""
        current_weight = self.components[name]["weight"] if weight is None else weight
        self.components[name].update(
            {
                "score": max(0.0, min(1.0, score)),
                "last_check": time.time(),
                "message": message,
                "weight": current_weight,  # Use specified weight or existing
            }
        )
        self._calculate_overall_score()

    def _calculate_overall_score(self):
        """Calculate weighted overall score"""
        # Only consider components updated within the last 2 minutes for score calculation
        active_components = [
            c for c in self.components.values() if time.time() - c["last_check"] < 120
        ]

        if not active_components:
            self.overall_score = 1.0
            return

        total_weight = sum(c["weight"] for c in active_components)
        weighted_sum = sum(c["score"] * c["weight"] for c in active_components)
        self.overall_score = weighted_sum / total_weight if total_weight > 0 else 1.0

    def get_status_message(self) -> str:
        """Get health status as human-readable string"""
        if self.overall_score >= 0.9:
            return "EXCELLENT"
        if self.overall_score >= 0.7:
            return "GOOD"
        if self.overall_score >= 0.5:
            return "DEGRADED"
        if self.overall_score >= 0.3:
            return "POOR"
        return "CRITICAL"

    def get_health_report(self) -> dict[str, Any]:
        """Generate comprehensive health report"""
        return {
            "overall_score": self.overall_score,
            "status": self.get_status_message(),
            "components": dict(self.components),
            "timestamp": datetime.now(UTC).isoformat(),
        }


# BotHealth is initialized globally as it's a core dependency for `set_bot_state` and others.
bot_health = BotHealth()


# Enhanced Rate Limiting with Adaptive Backoff
class AdaptiveRateLimiter:
    """Advanced rate limiter with dynamic backoff and token bucket algorithm."""

    def __init__(
        self, config_ref: "BotConfig"
    ):  # Type hint as string for forward reference
        self.config = config_ref  # Store a reference to the config object
        self.tokens = Decimal(str(self.config.RATE_LIMIT_BURST_LIMIT))
        self.last_update = time.time()
        self.lock = asyncio.Lock()
        self.success_rate = deque(maxlen=100)  # Records 1 for success, 0 for failure
        self.current_rate = Decimal(str(self.config.RATE_LIMIT_REQUESTS_PER_SECOND))
        self.backoff_factor = Decimal("1.0")  # Start with no backoff

    async def acquire(self) -> None:
        """Acquire a token, waiting if necessary with adaptive backoff."""
        async with self.lock:
            now = time.time()
            elapsed = Decimal(str(now - self.last_update))

            # Adaptive rate adjustment
            if self.config.RATE_LIMIT_ADAPTIVE_SCALING and len(self.success_rate) > 10:
                recent_success_avg = sum(self.success_rate) / len(self.success_rate)
                if (
                    recent_success_avg > 0.95
                ):  # Very high success, slightly increase rate
                    self.current_rate = min(
                        Decimal(
                            str(self.config.RATE_LIMIT_REQUESTS_PER_SECOND * 1.5)
                        ),  # Cap at 1.5x default
                        self.current_rate * Decimal("1.05"),  # Gentle increase
                    )
                    self.backoff_factor = max(
                        Decimal("1.0"), self.backoff_factor * Decimal("0.9")
                    )  # Reduce backoff
                elif (
                    recent_success_avg < 0.7
                ):  # Low success, significantly decrease rate and increase backoff
                    self.current_rate = max(
                        Decimal(
                            str(self.config.RATE_LIMIT_REQUESTS_PER_SECOND * 0.3)
                        ),  # Min 0.3x default
                        self.current_rate * Decimal("0.9"),  # More aggressive decrease
                    )
                    self.backoff_factor = min(
                        Decimal("5.0"), self.backoff_factor * Decimal("1.2")
                    )  # Max 5x backoff
                else:  # Moderate success, gently adjust towards default and reduce backoff
                    self.current_rate = (
                        self.current_rate
                        + Decimal(str(self.config.RATE_LIMIT_REQUESTS_PER_SECOND))
                    ) / Decimal("2")
                    self.backoff_factor = max(
                        Decimal("1.0"), self.backoff_factor * Decimal("0.95")
                    )

            # Add tokens based on current rate and elapsed time
            tokens_to_add = elapsed * self.current_rate
            self.tokens = min(
                Decimal(str(self.config.RATE_LIMIT_BURST_LIMIT)),
                self.tokens + tokens_to_add,
            )
            self.last_update = now

            # If not enough tokens, calculate wait time and sleep
            if self.tokens < 1:
                wait_time = (Decimal("1") - self.tokens) / self.current_rate
                wait_time *= self.backoff_factor  # Apply adaptive backoff
                await asyncio.sleep(float(wait_time))

                # After sleeping, re-calculate tokens based on *actual* elapsed time
                # to ensure fair consumption for the next token.
                now_after_wait = time.time()
                elapsed_after_wait = Decimal(str(now_after_wait - self.last_update))
                self.tokens += elapsed_after_wait * self.current_rate
                self.last_update = now_after_wait

            # Now we should have at least 1 token (or just enough if we waited)
            self.tokens -= 1

    def record_success(self, success: bool):
        """Record API call success for adaptive adjustment"""
        self.success_rate.append(1 if success else 0)
        # Immediately adjust backoff slightly to react faster to consecutive successes
        if success:
            self.backoff_factor = max(
                Decimal("1.0"), self.backoff_factor * Decimal("0.99")
            )


# Enhanced Configuration with hot reload and validation
@dataclass
class BotConfig:
    """Enhanced configuration with comprehensive validation and new parameters"""

    SYMBOL: str = "BTCUSDT"
    CATEGORY: str = "linear"
    QUANTITY: Decimal = Decimal("0.001")
    SPREAD_PERCENTAGE: Decimal = Decimal("0.0005")
    MAX_OPEN_ORDERS: int = 2
    ORDER_LIFESPAN_SECONDS: int = 30
    REBALANCE_THRESHOLD_QTY: Decimal = Decimal("0.0001")
    PROFIT_PERCENTAGE: Decimal = Decimal("0.001")
    STOP_LOSS_PERCENTAGE: Decimal = Decimal("0.005")
    PRICE_THRESHOLD: Decimal = Decimal("0.0002")  # Used for stale order repricing
    USE_TESTNET: bool = True
    ORDER_REFRESH_INTERVAL: int = (
        5  # How often to refresh open orders (HTTP, if WS down)
    )
    BALANCE_REFRESH_INTERVAL: int = (
        30  # How often to refresh balance (HTTP, if WS down)
    )
    CAPITAL_ALLOCATION_PERCENTAGE: Decimal = Decimal(
        "0.05"
    )  # % of available balance to consider for trade size
    ABNORMAL_SPREAD_THRESHOLD: Decimal = Decimal("0.015")  # For warning/CB
    REBALANCE_ORDER_TYPE: str = "Market"  # "Market" or "Limit"
    REBALANCE_PRICE_OFFSET_PERCENTAGE: Decimal = Decimal(
        "0"
    )  # Offset for Limit rebalance orders
    MAX_POSITION_SIZE: Decimal = Decimal(
        "0.1"
    )  # Max % of available balance for a single position
    VOLATILITY_ADJUSTMENT: bool = True  # Enable dynamic spread adjustment
    MAX_SLIPPAGE_PERCENTAGE: Decimal = Decimal(
        "0.001"
    )  # Max allowed slippage for executed trades (warning)
    ORDERBOOK_DEPTH_LEVELS: int = 25  # Number of levels to subscribe to for orderbook
    HEARTBEAT_INTERVAL: int = 30  # Interval for internal heartbeats and health checks
    MEMORY_CLEANUP_INTERVAL: int = 300  # How often to run garbage collection
    CONFIG_RELOAD_INTERVAL: int = 30  # How often to check config.json for changes

    NEON_COLORS_ENABLED: bool = True
    DASHBOARD_REFRESH_RATE: float = 0.7  # How often to refresh the terminal dashboard

    # NEW IMPROVEMENTS (from v5.0 skeleton and further enhancements)
    PERFORMANCE_LOG_INTERVAL: int = 300  # How often to log detailed performance summary
    MAX_LOG_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB
    TRADE_JOURNAL_FILE_SIZE: int = 20 * 1024 * 1024  # 20MB

    TRADING_HOURS_ENABLED: bool = False
    TRADING_START_HOUR_UTC: int = 0  # 0-23
    TRADING_END_HOUR_UTC: int = 23  # 0-23

    ADAPTIVE_QUANTITY_ENABLED: bool = True
    ADAPTIVE_QUANTITY_PERFORMANCE_FACTOR: Decimal = Decimal(
        "0.1"
    )  # Influence of performance on quantity

    # Circuit Breaker Config (integrated)
    CIRCUIT_BREAKER_ENABLED: bool = True
    CB_PNL_STOP_LOSS_PCT: Decimal = Decimal(
        "0.02"
    )  # PnL loss percentage to trigger critical CB
    CB_ABNORMAL_SPREAD_PCT: Decimal = Decimal(
        "0.015"
    )  # Abnormal spread percentage to trigger minor CB
    CB_STALE_DATA_TIMEOUT_SEC: int = (
        30  # Max seconds for market data freshness before CB
    )
    CB_LOW_CONNECTION_THRESHOLD: float = (
        0.3  # BotHealth.overall_score threshold for connection quality
    )
    CB_LOW_ORDER_SUCCESS_THRESHOLD: float = 0.2  # Order success rate threshold for CB
    CB_HIGH_MEMORY_MB: int = 1000  # Memory usage (MB) to trigger minor CB
    CB_MINOR_PAUSE_THRESHOLD: float = 0.6  # BotHealth.overall_score for MINOR_PAUSE
    CB_MAJOR_CANCEL_THRESHOLD: float = 0.4  # BotHealth.overall_score for MAJOR_CANCEL
    CB_CRITICAL_SHUTDOWN_THRESHOLD: float = (
        0.2  # BotHealth.overall_score for CRITICAL_SHUTDOWN
    )

    # Rate Limiter Config (new section from previous code)
    RATE_LIMIT_REQUESTS_PER_SECOND: int = 10
    RATE_LIMIT_BURST_LIMIT: int = 20
    RATE_LIMIT_ADAPTIVE_SCALING: bool = True

    # Plugin System (new from v5.0 skeleton)
    PLUGIN_FOLDER: str = "plugins"
    ENABLE_PLUGINS: bool = True
    STRATEGY_PLUGIN_NAME: str | None = (
        None  # Name of the specific strategy plugin to use, e.g., "my_custom_strategy"
    )

    def __post_init__(self):
        """Enhanced validation with detailed checks"""
        validations = [
            (self.SPREAD_PERCENTAGE > 0, "SPREAD_PERCENTAGE must be positive"),
            (self.MAX_OPEN_ORDERS > 0, "MAX_OPEN_ORDERS must be positive"),
            (self.SYMBOL, "SYMBOL cannot be empty"),
            (
                Decimal("0") < self.CAPITAL_ALLOCATION_PERCENTAGE <= Decimal("1"),
                "CAPITAL_ALLOCATION_PERCENTAGE must be between 0 and 1",
            ),
            (
                Decimal("0") < self.MAX_POSITION_SIZE <= Decimal("1"),
                "MAX_POSITION_SIZE must be between 0 and 1",
            ),
            (
                self.ORDERBOOK_DEPTH_LEVELS > 0,
                "ORDERBOOK_DEPTH_LEVELS must be positive",
            ),
            (
                self.DASHBOARD_REFRESH_RATE > 0,
                "DASHBOARD_REFRESH_RATE must be positive",
            ),
            (self.HEARTBEAT_INTERVAL > 0, "HEARTBEAT_INTERVAL must be positive"),
            (self.QUANTITY > 0, "QUANTITY must be positive"),
            (
                self.ORDER_LIFESPAN_SECONDS > 0,
                "ORDER_LIFESPAN_SECONDS must be positive",
            ),
            (
                self.REBALANCE_THRESHOLD_QTY >= 0,
                "REBALANCE_THRESHOLD_QTY must be non-negative",
            ),
            (self.PROFIT_PERCENTAGE > 0, "PROFIT_PERCENTAGE must be positive"),
            (self.STOP_LOSS_PERCENTAGE > 0, "STOP_LOSS_PERCENTAGE must be positive"),
            (self.PRICE_THRESHOLD >= 0, "PRICE_THRESHOLD must be non-negative"),
            (
                self.ABNORMAL_SPREAD_THRESHOLD > 0,
                "ABNORMAL_SPREAD_THRESHOLD must be positive",
            ),
            (
                self.MAX_SLIPPAGE_PERCENTAGE >= 0,
                "MAX_SLIPPAGE_PERCENTAGE must be non-negative",
            ),
            (
                self.PERFORMANCE_LOG_INTERVAL > 0,
                "PERFORMANCE_LOG_INTERVAL must be positive",
            ),
            (self.MAX_LOG_FILE_SIZE > 0, "MAX_LOG_FILE_SIZE must be positive"),
            (
                self.TRADE_JOURNAL_FILE_SIZE > 0,
                "TRADE_JOURNAL_FILE_SIZE must be positive",
            ),
            (
                self.MEMORY_CLEANUP_INTERVAL > 0,
                "MEMORY_CLEANUP_INTERVAL must be positive",
            ),
            (
                self.CONFIG_RELOAD_INTERVAL > 0,
                "CONFIG_RELOAD_INTERVAL must be positive",
            ),
            (
                self.RATE_LIMIT_REQUESTS_PER_SECOND > 0,
                "RATE_LIMIT_REQUESTS_PER_SECOND must be positive",
            ),
            (
                self.RATE_LIMIT_BURST_LIMIT > 0,
                "RATE_LIMIT_BURST_LIMIT must be positive",
            ),
        ]

        for condition, message in validations:
            if not condition:
                raise ValueError(f"Configuration validation failed: {message}")

        if not (
            0 <= self.TRADING_START_HOUR_UTC <= 23
            and 0 <= self.TRADING_END_HOUR_UTC <= 23
        ):
            raise ValueError(
                "TRADING_START_HOUR_UTC and TRADING_END_HOUR_UTC must be between 0 and 23"
            )

        if not (
            0
            <= self.CB_CRITICAL_SHUTDOWN_THRESHOLD
            <= self.CB_MAJOR_CANCEL_THRESHOLD
            <= self.CB_MINOR_PAUSE_THRESHOLD
            <= 1.0
        ):
            raise ValueError(
                "Circuit breaker thresholds must be in ascending order for severity (CRITICAL <= MAJOR <= MINOR)."
            )
        if not (
            0 <= self.CB_LOW_CONNECTION_THRESHOLD <= 1.0
            and 0 <= self.CB_LOW_ORDER_SUCCESS_THRESHOLD <= 1.0
        ):
            raise ValueError(
                "Circuit breaker connection/success thresholds must be between 0 and 1."
            )

    def get_hash(self) -> str:
        """Get configuration hash for change detection"""
        # Using asdict() for comprehensive hashing
        config_dict = asdict(self)
        # Convert Decimal objects to string for consistent hashing
        for key, value in config_dict.items():
            if isinstance(value, Decimal):
                config_dict[key] = str(value)
        config_str = json.dumps(config_dict, sort_keys=True)
        return hashlib.md5(config_str.encode()).hexdigest()


# Enhanced configuration manager with better error handling
class ConfigManager:
    """Advanced configuration manager with hot reload and validation"""

    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self.load_errors = 0
        self.max_load_errors = 5
        self.config = self._load_config_safe()
        self.last_hash = self.config.get_hash()
        self.last_check = time.time()
        self.callbacks: list[Callable[[BotConfig], None]] = []

    def _load_config_safe(self) -> BotConfig:
        """Safely load configuration with error handling"""
        try:
            with open(self.config_file) as f:
                config_data = json.load(f)

            # Dynamically convert fields to their correct types based on BotConfig defaults
            default_config_instance = BotConfig()
            for key, default_value in asdict(default_config_instance).items():
                if key in config_data:
                    # Handle Decimal conversion
                    if isinstance(getattr(default_config_instance, key), Decimal):
                        config_data[key] = Decimal(str(config_data[key]))
                    # Handle boolean conversion robustness
                    elif isinstance(getattr(default_config_instance, key), bool):
                        if isinstance(config_data[key], str):
                            config_data[key] = config_data[key].lower() in (
                                "true",
                                "1",
                                "t",
                                "y",
                                "yes",
                            )
                        else:
                            config_data[key] = bool(config_data[key])
                    # Handle int/float for safety
                    elif isinstance(getattr(default_config_instance, key), int):
                        config_data[key] = int(config_data[key])
                    elif isinstance(getattr(default_config_instance, key), float):
                        config_data[key] = float(config_data[key])
                    # String values like SYMBOL are kept as is

            known_fields = {f.name for f in fields(BotConfig)}
            filtered_config_data = {
                k: v for k, v in config_data.items() if k in known_fields
            }
            config = BotConfig(**filtered_config_data)
            self.load_errors = 0  # Reset error count on successful load
            return config

        except FileNotFoundError:
            print("WARNING: config.json not found. Creating default configuration...")
            config = BotConfig()
            self._save_default_config(config)
            return config
        except Exception as e:
            self.load_errors += 1
            print(
                f"ERROR: Error loading configuration (attempt {self.load_errors}): {e}"
            )

            if self.load_errors >= self.max_load_errors:
                print(
                    "CRITICAL: Max configuration load errors reached. Using default config. Please fix config.json immediately."
                )
                return BotConfig()

            # Return current configuration if available, otherwise default
            return getattr(self, "config", BotConfig())

    def _save_default_config(self, config_instance: BotConfig):
        """Save default configuration to file"""
        try:
            config_dict = asdict(config_instance)
            # Convert Decimal objects to string for JSON serialization
            for key, value in config_dict.items():
                if isinstance(value, Decimal):
                    config_dict[key] = str(value)

            with open(self.config_file, "w") as f:
                json.dump(config_dict, f, indent=2)
            print("INFO: Default config.json created successfully")
        except Exception as e:
            print(f"ERROR: Error saving default configuration: {e}")

    async def check_for_updates(self) -> bool:
        """Check for configuration updates with enhanced error handling"""
        if time.time() - self.last_check < self.config.CONFIG_RELOAD_INTERVAL:
            return False

        self.last_check = time.time()

        try:
            new_config = self._load_config_safe()
            new_hash = new_config.get_hash()

            if new_hash != self.last_hash:
                print("INFO: Configuration updated detected, reloading...")
                self.config = new_config
                self.last_hash = new_hash

                # Notify callbacks
                for callback in self.callbacks:
                    try:
                        callback(self.config)
                    except Exception as e:
                        print(f"ERROR: Error in config callback: {e}")

                send_toast("⚙️ Config reloaded", "blue", "white")
                return True
        except Exception as e:
            print(f"ERROR: Error checking config updates: {e}")

        return False

    def add_callback(self, callback: Callable[[BotConfig], None]):
        """Add callback for configuration changes"""
        self.callbacks.append(callback)


# MODIFIED: EnhancedLogger class for dedicated trade journal
class EnhancedLogger:
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        self.trade_logger = logging.getLogger(
            f"{name}.trades"
        )  # Initialize trade_logger here
        self.trade_logger.setLevel(logging.INFO)
        # self.setup_logging() # Call setup in init, but needs config to be ready

    def setup_logging(self):
        # Clear existing handlers to prevent duplicates on config reload
        # For main logger
        if self.logger.handlers:
            for handler in self.logger.handlers[:]:
                self.logger.removeHandler(handler)
                handler.close()
        # For trade logger
        if self.trade_logger.handlers:
            for handler in self.trade_logger.handlers[:]:
                self.trade_logger.removeHandler(handler)
                handler.close()

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        if LOG_AS_JSON:
            formatter = logging.Formatter(
                '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": %(message)s}'
            )
        else:
            formatter = logging.Formatter(
                f"{NEON_CYAN}%(asctime)s{NC} {BOLD}[%(levelname)s]{NC} %(message)s"
            )
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # File handler for general logs
        log_file_path = "mmxcel.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_file_path,
            maxBytes=config.MAX_LOG_FILE_SIZE,  # Use config value
            backupCount=5,
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

        # --- NEW: Dedicated Trade Journal File Handler ---
        trade_journal_path = "mmxcel_trades.log"
        trade_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
            if not LOG_AS_JSON
            else '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "event": "trade_journal", "data": %(message)s}'
        )
        trade_file_handler = logging.handlers.RotatingFileHandler(
            trade_journal_path,
            maxBytes=config.TRADE_JOURNAL_FILE_SIZE,  # Use config value
            backupCount=3,
        )
        trade_file_handler.setFormatter(trade_formatter)
        self.trade_logger.addHandler(trade_file_handler)
        # --- END NEW ---

    # Add a new method for journaling trades
    def journal_trade(self, trade_data: dict):
        """Logs a trade event to the dedicated trade journal."""
        if LOG_AS_JSON:
            self.trade_logger.info(json.dumps(trade_data))
        else:
            self.trade_logger.info(
                f"TRADE: Side={trade_data.get('side')}, Price={trade_data.get('price')}, "
                f"Qty={trade_data.get('quantity')}, OrderID={trade_data.get('order_id')}, "
                f"Slippage={trade_data.get('slippage_pct'):.4f}, Latency={trade_data.get('latency'):.3f}s"
            )

    def info(self, msg, *args, **kwargs):
        exc_info = kwargs.pop("exc_info", None)
        extra_info = " ".join(f"{k}={v}" for k, v in kwargs.items())
        if extra_info:
            msg = f"{msg} {extra_info}"
        self.logger.info(msg, *args, exc_info=exc_info)

    def warning(self, msg, *args, **kwargs):
        exc_info = kwargs.pop("exc_info", None)
        extra_info = " ".join(f"{k}={v}" for k, v in kwargs.items())
        if extra_info:
            msg = f"{msg} {extra_info}"
        self.logger.warning(msg, *args, exc_info=exc_info)

    def error(self, msg, *args, **kwargs):
        exc_info = kwargs.pop("exc_info", None)
        extra_info = " ".join(f"{k}={v}" for k, v in kwargs.items())
        if extra_info:
            msg = f"{msg} {extra_info}"
        self.logger.error(msg, *args, exc_info=exc_info)

    def debug(self, msg, *args, **kwargs):
        exc_info = kwargs.pop("exc_info", None)
        extra_info = " ".join(f"{k}={v}" for k, v in kwargs.items())
        if extra_info:
            msg = f"{msg} {extra_info}"
        self.logger.debug(msg, *args, exc_info=exc_info)

    def critical(self, msg, *args, **kwargs):
        exc_info = kwargs.pop("exc_info", None)
        extra_info = " ".join(f"{k}={v}" for k, v in kwargs.items())
        if extra_info:
            msg = f"{msg} {extra_info}"
        self.logger.critical(msg, *args, exc_info=exc_info)


# Initialize logger first, as other components might use it during their init
log = EnhancedLogger("MMXCEL")

# Initialize config_manager and config globally, as they are needed early by other global objects.
config_manager = ConfigManager()
config = config_manager.config  # This is the initial config instance

# Re-call setup_logging to ensure it uses the loaded config for MAX_LOG_FILE_SIZE etc.
log.setup_logging()  # Re-setup with potentially loaded config values

# Now the other global objects can be initialized, as `config` is available.
symbol_info = SymbolInfo()
market_state = MarketState()
session_stats = SessionStats()
system_monitor = SystemMonitor()
rate_limiter = AdaptiveRateLimiter(
    config
)  # Now `config` is guaranteed to be initialized


# Initialize Sentry if available (moved to after logger setup to ensure logging works)
if sentry_sdk and SENTRY_DSN:
    sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=1.0, release="mmxcel@5.2.0")


# Enhanced Performance Monitoring
class PerformanceMonitor:
    """Enhanced performance monitoring with detailed analytics"""

    def __init__(self):
        self.api_call_times = deque(maxlen=500)
        self.order_latencies = deque(maxlen=200)
        self.websocket_latencies = deque(maxlen=200)
        self.last_performance_log = time.time()
        self.operation_counts = defaultdict(int)
        self.error_counts = defaultdict(int)
        self.slow_operations = deque(maxlen=50)
        self.performance_alerts = 0

    def record_api_call(self, duration: float, operation: str = "unknown"):
        """Record API call with enhanced analysis"""
        self.api_call_times.append(duration)
        self.operation_counts[operation] += 1

        if duration > 5.0:  # Threshold for a "slow" API call
            self.slow_operations.append(
                {"operation": operation, "duration": duration, "timestamp": time.time()}
            )
            self.performance_alerts += 1
            log.warning(
                f"Slow API call detected: {operation}", duration=f"{duration:.3f}s"
            )

        rate_limiter.record_success(
            duration < 10.0
        )  # Assume success if not excessively slow

    def record_order_latency(self, duration: float):
        """Record order latency (time from request to exchange confirmation)"""
        self.order_latencies.append(duration)

        if duration > 3.0:  # Threshold for high order latency
            log.warning("High order latency detected", latency=f"{duration:.3f}s")

    def record_websocket_latency(self, duration: float):
        """Record WebSocket message processing latency"""
        self.websocket_latencies.append(duration)

    def record_error(self, error_type: str):
        """Record error with categorization"""
        self.error_counts[error_type] += 1

    def get_performance_summary(self) -> dict[str, Any]:
        """Get comprehensive performance summary"""
        return {
            "avg_api_time": sum(self.api_call_times) / len(self.api_call_times)
            if self.api_call_times
            else 0,
            "max_api_time": max(self.api_call_times) if self.api_call_times else 0,
            "avg_order_latency": sum(self.order_latencies) / len(self.order_latencies)
            if self.order_latencies
            else 0,
            "avg_ws_latency": sum(self.websocket_latencies)
            / len(self.websocket_latencies)
            if self.websocket_latencies
            else 0,
            "total_operations": sum(self.operation_counts.values()),
            "total_errors": sum(self.error_counts.values()),
            "slow_operations_count": len(self.slow_operations),
            "performance_alerts": self.performance_alerts,
            "operation_breakdown": dict(self.operation_counts),
            "error_breakdown": dict(self.error_counts),
        }

    def should_log_performance(self) -> bool:
        """Check if performance summary should be logged based on interval"""
        if time.time() - self.last_performance_log > config.PERFORMANCE_LOG_INTERVAL:
            self.last_performance_log = time.time()
            return True
        return False


performance_monitor = PerformanceMonitor()


# NEW FEATURE: Plugin System (from v5.0 skeleton)
class PluginManager:
    """Manages loading and interaction with strategy plugins."""

    def __init__(self):
        self.plugins: dict[str, Any] = {}
        self.callbacks: list[
            Callable[[Any], None]
        ] = []  # Callbacks that receive the strategy instance

    def load_plugins(self, folder: str):
        if not (config.ENABLE_PLUGINS and os.path.isdir(folder)):
            log.info("Plugin system disabled or folder not found.")
            return

        sys.path.insert(0, folder)  # Add plugin folder to Python path

        for file in os.listdir(folder):
            if file.endswith(".py") and not file.startswith("_"):
                module_name = file[:-3]
                try:
                    # Dynamically import the module
                    spec = importlib.util.spec_from_file_location(
                        module_name, os.path.join(folder, file)
                    )
                    if spec is None:
                        raise ImportError(f"Could not load spec for {module_name}")
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)

                    if hasattr(module, "register") and callable(module.register):
                        callback = module.register()
                        if callable(callback):
                            self.plugins[module_name] = module  # Store module reference
                            self.callbacks.append(callback)
                            log.info(f"Plugin '{module_name}' loaded successfully.")
                        else:
                            log.warning(
                                f"Plugin '{module_name}' register() did not return a callable."
                            )
                    else:
                        log.debug(f"Plugin '{module_name}' has no 'register' function.")
                except Exception as e:
                    log.error(
                        f"Failed to load plugin '{module_name}': {e}", exc_info=True
                    )

        # If a specific strategy plugin is configured, ensure it exists
        if (
            config.STRATEGY_PLUGIN_NAME
            and config.STRATEGY_PLUGIN_NAME not in self.plugins
        ):
            log.critical(
                f"Configured strategy plugin '{config.STRATEGY_PLUGIN_NAME}' not found or failed to load. Please check plugin folder and config."
            )
            global _SHUTDOWN_REQUESTED  # Explicitly declare global to modify
            _SHUTDOWN_REQUESTED = (
                True  # Force shutdown if main strategy plugin is missing
            )


plugin_manager = PluginManager()
import importlib.util  # Import here to avoid circular dependencies with early logging setup


# Enhanced Bybit Client with better connection management and robust API calls
class EnhancedBybitClient:
    """Enhanced Bybit client with advanced connection management, retry logic, and WS order operations."""

    def __init__(
        self,
        key: str,
        secret: str,
        testnet: bool,
        market_state_ref: "MarketState",
        symbol_info_ref: "SymbolInfo",
        session_stats_ref: "SessionStats",
        performance_monitor_ref: "PerformanceMonitor",
        bot_health_ref: "BotHealth",
        config_ref: "BotConfig",
        log_ref: "EnhancedLogger",
        send_toast_func: Callable[[str, str, str], None],
        loop: asyncio.AbstractEventLoop,
    ):
        self.key = key
        self.secret = secret
        self.testnet = testnet
        self.loop = loop
        self.http = HTTP(
            testnet=testnet, api_key=key, api_secret=secret, recv_window=20000
        )
        self.public_ws: WebSocket | None = None
        self.private_ws: WebSocket | None = None
        self._public_connected = asyncio.Event()
        self._private_connected = asyncio.Event()
        self.connection_attempts = defaultdict(int)
        self.reconnect_delays = [1, 2, 4, 8, 15, 30, 60]  # Max 60s delay
        self._reconnect_tasks = {}  # To keep track of reconnect tasks for proper cancellation

        # For WebSocket command responses
        self._ws_command_futures: dict[str, asyncio.Future] = {}
        self._ws_command_lock = asyncio.Lock()

        # References to global state objects
        self.market_state = market_state_ref
        self.symbol_info = symbol_info_ref
        self.session_stats = session_stats_ref
        self.performance_monitor = performance_monitor_ref
        self.bot_health = bot_health_ref
        self.config = config_ref
        self.log = log_ref
        self.send_toast = send_toast_func

    async def reconnect_ws(self, ws_type: str):
        """Handles the reconnection logic for a given websocket type."""
        # Check shutdown flag immediately upon entering reconnect logic
        if _SHUTDOWN_REQUESTED:
            self.log.info(
                f"Shutdown requested, not attempting to reconnect {ws_type} WS."
            )
            self._reconnect_tasks.pop(ws_type, None)  # Clean up task reference
            return

        attempt = self.connection_attempts[ws_type]
        delay = self.reconnect_delays[min(attempt, len(self.reconnect_delays) - 1)]
        self.log.info(
            f"Attempting to reconnect {ws_type} WS in {delay}s", attempt=attempt + 1
        )

        await asyncio.sleep(delay)

        # Re-check shutdown flag after sleep
        if _SHUTDOWN_REQUESTED:
            self.log.info(
                f"Shutdown requested after reconnect delay, not reconnecting {ws_type} WS."
            )
            self._reconnect_tasks.pop(ws_type, None)
            return

        self.connection_attempts[ws_type] += 1

        if ws_type == "public":
            await self._subscribe_public_topics()
        elif ws_type == "private":
            await self._subscribe_private_topics()

        # Remove the task from tracking only after the reconnection attempt is done
        self._reconnect_tasks.pop(ws_type, None)

    async def connect_websockets(self):
        """Manages WebSocket connections, reconnection, and resubscription."""

        def _on_ws_open(ws_type: str):
            if ws_type == "public":
                self._public_connected.set()
            elif ws_type == "private":
                self._private_connected.set()

            self.log.info(f"🟢 {ws_type.capitalize()} WebSocket connected.")
            self.connection_attempts[ws_type] = 0  # Reset attempts on success
            self.bot_health.update_component(
                f"ws_{ws_type}_connection", 1.0, f"{ws_type.capitalize()} WS Connected"
            )
            self.market_state.last_heartbeat = (
                time.time()
            )  # Update last message received time

        def _on_ws_close(ws_type: str):
            if ws_type == "public":
                self._public_connected.clear()
            elif ws_type == "private":
                self._private_connected.clear()

            self.log.warning(f"🔴 {ws_type.capitalize()} WebSocket disconnected.")
            self.session_stats.connection_drops += 1
            self.bot_health.update_component(
                f"ws_{ws_type}_connection",
                0.0,
                f"{ws_type.capitalize()} WS Disconnected",
            )

            if not _SHUTDOWN_REQUESTED and self.loop.is_running():
                # Ensure only one reconnect task per WS type is active
                if ws_type not in self._reconnect_tasks:
                    future = asyncio.run_coroutine_threadsafe(
                        self.reconnect_ws(ws_type), self.loop
                    )
                    self._reconnect_tasks[ws_type] = future
                else:
                    self.log.debug(f"Reconnect task for {ws_type} already running.")

        def _on_ws_error(ws_type: str, error: Exception):
            self.log.error(
                f"🔥 {ws_type.capitalize()} WebSocket error: {error}",
                error_msg=str(error),
            )
            self.bot_health.update_component(
                f"ws_{ws_type}_connection",
                0.0,
                f"{ws_type.capitalize()} WS Error: {error}",
            )
            self.performance_monitor.record_error(f"websocket_{ws_type}_error")
            if sentry_sdk:
                sentry_sdk.capture_exception(error)
            if ws_type == "public":
                self._public_connected.clear()
            elif ws_type == "private":
                self._private_connected.clear()

            # Trigger reconnect on error, similar to close
            if not _SHUTDOWN_REQUESTED and self.loop.is_running():
                if ws_type not in self._reconnect_tasks:
                    future = asyncio.run_coroutine_threadsafe(
                        self.reconnect_ws(ws_type), self.loop
                    )
                    self._reconnect_tasks[ws_type] = future

        # Initialize WebSocket instances if not already
        if not self.public_ws:
            self.public_ws = WebSocket(
                testnet=self.testnet,
                channel_type="linear",  # Assuming linear for public, adjust if needed
            )
            self.public_ws._on_open = lambda: _on_ws_open("public")
            self.public_ws._on_close = lambda: _on_ws_close("public")
            self.public_ws._on_error = lambda err: _on_ws_error("public", err)
            self.public_ws._on_message = (
                self._on_public_ws_message
            )  # Use internal handler
            self.log.debug("Public WS initialized.")

        if not self.private_ws:
            self.private_ws = WebSocket(
                testnet=self.testnet,
                channel_type="private",
                api_key=self.key,
                api_secret=self.secret,
            )
            self.private_ws._on_open = lambda: _on_ws_open("private")
            self.private_ws._on_close = lambda: _on_ws_close("private")
            self.private_ws._on_error = lambda err: _on_ws_error("private", err)
            self.private_ws._on_message = (
                self._on_private_ws_message
            )  # Use internal handler
            self.log.debug("Private WS initialized.")

        # Initial subscription calls to start the connection
        self.log.debug("Subscribing to public topics...")
        await self._subscribe_public_topics()
        self.log.debug("Subscribing to private topics...")
        await self._subscribe_private_topics()
        self.log.debug("Subscription calls finished.")

    async def _subscribe_public_topics(self):
        """Subscribes to public WebSocket topics."""
        if self.public_ws:
            try:
                self.public_ws.orderbook_stream(
                    self.config.ORDERBOOK_DEPTH_LEVELS,
                    self.config.SYMBOL,
                    self._on_public_ws_message,
                )
                self.log.info(
                    f"Subscribed to public orderbook for {self.config.SYMBOL}",
                    symbol=self.config.SYMBOL,
                )
            except Exception as e:
                self.log.error(f"Failed to subscribe to public topics: {e}")
                if sentry_sdk:
                    sentry_sdk.capture_exception(e)

    async def _subscribe_private_topics(self):
        """Subscribes to private WebSocket topics."""
        if self.private_ws:
            try:
                self.private_ws.order_stream(callback=self._on_private_ws_message)
                self.private_ws.position_stream(callback=self._on_private_ws_message)
                self.private_ws.wallet_stream(callback=self._on_private_ws_message)
                self.private_ws.execution_stream(callback=self._on_private_ws_message)
                self.log.info(
                    "Subscribed to private streams (order, position, wallet, execution)"
                )
            except Exception as e:
                self.log.error(f"Failed to subscribe to private topics: {e}")
                if sentry_sdk:
                    sentry_sdk.capture_exception(e)

    def _on_public_ws_message(self, msg: dict[str, Any] | str) -> None:
        """Handle public WebSocket messages with enhanced processing"""
        message_start_time = time.time()

        if not isinstance(msg, dict):
            try:
                msg = json.loads(msg)
            except json.JSONDecodeError:
                self.log.debug(f"Received non-dict public WS message: {msg}")
                return

        if msg.get("op") == "subscribe":
            if msg.get("success") is False:
                self.log.error(f"Subscription failed: {msg.get('ret_msg')}")
            else:
                self.log.info(f"Subscription successful: {msg}")
            return

        try:
            topic = msg.get("topic", "")
            if msg.get("op") == "ping" or msg.get("ret_msg") == "pong":
                self.log.debug(f"Received WS heartbeat/pong: {msg.get('ret_msg')}")
                self.market_state.last_heartbeat = time.time()
                return

            if "orderbook" in topic:
                data = msg.get("data")
                if data and data.get("b") and data.get("a"):
                    bids = data.get("b", [])
                    asks = data.get("a", [])

                    if bids and asks and len(bids) > 0 and len(asks) > 0:
                        self.market_state.best_bid = Decimal(str(bids[0][0]))
                        self.market_state.best_ask = Decimal(str(asks[0][0]))

                        if (
                            self.market_state.best_bid > 0
                            and self.market_state.best_ask > 0
                        ):
                            self.market_state.mid_price = (
                                self.market_state.best_bid + self.market_state.best_ask
                            ) / Decimal("2")

                            self.symbol_info.update_orderbook_depth(bids, asks)
                            self.market_state.update_price_history()
                        else:
                            self.market_state.mid_price = Decimal("0")  # Invalid prices

                        self.market_state.last_update_time = time.time()
                        self.market_state.last_heartbeat = (
                            time.time()
                        )  # This is the primary heartbeat for market data

                        latency = time.time() - message_start_time
                        self.performance_monitor.record_websocket_latency(latency)

                        self.bot_health.update_component(
                            "ws_public_latency",
                            float(max(0.0, 1.0 - (latency / 0.5))),
                            f"Public WS Latency: {latency:.3f}s",
                        )
                    else:
                        self.log.warning(
                            "Public WS message received with empty bids/asks, skipping update.",
                            msg_payload=msg,
                        )
                        self.bot_health.update_component(
                            "ws_public_data_quality", 0.5, "Public WS Data Incomplete"
                        )  # Partial score

        except (KeyError, IndexError, ValueError, TypeError, DecimalException) as e:
            self.log.error(f"Error processing public WS message: {e}", msg_payload=msg)
            self.performance_monitor.record_error("websocket_public_error")
            self.bot_health.update_component(
                "ws_public_data_quality", 0.0, f"Public WS Data Error: {e}"
            )
            if sentry_sdk:
                sentry_sdk.capture_exception(e)
        except Exception as e:
            self.log.critical(
                f"Critical error in public WS handler: {e}", exc_info=True
            )
            self.performance_monitor.record_error("websocket_public_critical")
            self.bot_health.update_component(
                "ws_public_data_quality", 0.0, f"Public WS Critical Error: {e}"
            )
            if sentry_sdk:
                sentry_sdk.capture_exception(e)

    def _process_execution(self, exec_data: dict[str, Any]):
        """Processes a single trade execution from the WebSocket stream."""
        order_id = exec_data.get("orderId")
        if not order_id:
            return

        # Retrieve original order details for slippage calculation
        order_details = self.market_state.open_orders.get(order_id)
        if not order_details:
            self.log.warning(
                "Execution received for an untracked or already closed order.",
                order_id=order_id,
            )
            # Use execution price as expected price if original order details are not available
            expected_price = Decimal(str(exec_data.get("execPrice", "0")))
            client_order_id = "N/A"
            order_timestamp = time.time()
        else:
            expected_price = order_details.get("price", Decimal("0"))
            client_order_id = order_details.get("client_order_id", "N/A")
            order_timestamp = order_details.get("timestamp", time.time())

        actual_price = Decimal(str(exec_data.get("execPrice", "0")))
        filled_qty = Decimal(str(exec_data.get("execQty", "0")))
        side = exec_data.get("side", "N/A")

        # Calculate slippage
        slippage = Decimal("0")
        if expected_price > 0 and actual_price > 0:
            if side == "Buy":
                slippage = (actual_price - expected_price) / expected_price
            else:  # Sell
                slippage = (expected_price - actual_price) / expected_price

            if abs(slippage) > self.config.MAX_SLIPPAGE_PERCENTAGE:
                self.session_stats.slippage_events += 1
                self.log.warning(
                    f"High slippage detected on fill: {side} order",
                    order_id=order_id,
                    expected=f"{expected_price:.{calculate_decimal_precision(expected_price)}f}",
                    actual=f"{actual_price:.{calculate_decimal_precision(actual_price)}f}",
                    slippage=f"{slippage:.4%}",
                )

        # Create trade data for journaling and history
        trade_data = {
            "timestamp": time.time(),
            "order_id": order_id,
            "client_order_id": client_order_id,
            "symbol": self.config.SYMBOL,
            "side": side,
            "price": actual_price,
            "quantity": filled_qty,
            "slippage_pct": slippage,
            "latency": time.time() - order_timestamp,
            "type": "Execution",
        }
        self.market_state.add_trade(trade_data)
        self.log.journal_trade(trade_data)

        self.session_stats.total_volume_traded += filled_qty

        self.log.info(
            "Trade executed",
            order_id=order_id,
            side=side,
            quantity=float(filled_qty),
            price=float(actual_price),
            slippage=f"{float(slippage):.4f}",
        )
        self.send_toast(
            f"✅ {side} {filled_qty} @ {actual_price:.{calculate_decimal_precision(actual_price)}f}",
            "green",
            "white",
        )

    # MODIFIED: _on_private_ws_message for dedicated trade journal
    def _on_private_ws_message(self, msg: dict[str, Any]) -> None:
        """Handle private WebSocket messages with enhanced processing"""
        message_start_time = time.time()

        if isinstance(msg, str):
            try:
                msg = json.loads(msg)
            except json.JSONDecodeError:
                self.log.error(f"Failed to decode private WS message as JSON: {msg}")
                return

        # Handle command responses first
        if msg.get("op") == "response" and "id" in msg:
            req_id = msg["id"]
            asyncio.create_task(
                self._resolve_ws_command_future(req_id, msg)
            )  # Resolve future in a task to not block WS thread
            return  # This message was a command response, don't process as topic update

        try:
            topic = msg.get("topic")

            if topic == "execution":
                for exec_data in msg.get("data", []):
                    self._process_execution(exec_data)

            elif topic == "order":
                for order_data in msg["data"]:
                    order_id = order_data.get("orderId")
                    if not order_id:
                        continue

                    order_status = order_data.get("orderStatus")

                    if order_status == "Filled":
                        if order_id in self.market_state.open_orders:
                            self.market_state.open_orders.pop(order_id, None)
                            self.session_stats.orders_filled += 1
                            self.log.info(
                                "Order fully filled and closed.", order_id=order_id
                            )
                        # Trade processing is now handled by the 'execution' topic handler

                    elif order_status in ("Canceled", "Deactivated"):
                        if order_id in self.market_state.open_orders:
                            self.market_state.open_orders.pop(order_id, None)
                            self.session_stats.orders_cancelled += 1
                            self.log.info(
                                "Order cancelled by exchange or deactivated",
                                order_id=order_id,
                                status=order_status,
                            )

                    elif order_status == "Rejected":
                        if order_id in self.market_state.open_orders:
                            self.market_state.open_orders.pop(order_id, None)
                        self.session_stats.orders_rejected += 1
                        self.log.warning(
                            "Order rejected",
                            order_id=order_id,
                            reject_reason=order_data.get("rejectReason"),
                        )
                        self.send_toast("❌ Order rejected", "red", "white")

                    elif order_status in ["New", "PartiallyFilled", "PendingNew"]:
                        current_order_entry = self.market_state.open_orders.get(
                            order_id, {}
                        )
                        self.market_state.open_orders[order_id] = {
                            "client_order_id": order_data.get(
                                "orderLinkId",
                                current_order_entry.get("client_order_id", "N/A"),
                            ),
                            "symbol": order_data.get(
                                "symbol", current_order_entry.get("symbol")
                            ),
                            "side": order_data.get(
                                "side", current_order_entry.get("side")
                            ),
                            "price": Decimal(
                                str(
                                    order_data.get(
                                        "price", current_order_entry.get("price", "0")
                                    )
                                )
                            ),
                            "qty": Decimal(str(order_data.get("qty", "0"))),
                            "status": order_status,
                            "timestamp": float(
                                order_data.get(
                                    "createdTime",
                                    current_order_entry.get("timestamp", 0),
                                )
                            )
                            / 1000,
                        }
                        self.log.debug(
                            "Order status update",
                            order_id=order_id,
                            status=order_status,
                        )

            elif topic == "position":
                for pos_data in msg["data"]:
                    if (
                        pos_data.get("symbol") == self.config.SYMBOL
                    ):  # Fixed typo: pos_data.get("symbol")
                        # Bybit sends updates for all position sides (long/short/both)
                        side = "Long" if pos_data.get("side") == "Buy" else "Short"
                        current_size = Decimal(str(pos_data.get("size", "0")))

                        if current_size == Decimal("0"):  # Position closed
                            self.market_state.positions.pop(side, None)
                            self.log.info(
                                f"{side} position closed",
                                position_size=float(current_size),
                            )
                        else:
                            unrealised_pnl = Decimal(
                                str(pos_data.get("unrealisedPnl", "0"))
                            )
                            self.market_state.positions[side] = {
                                "size": current_size,
                                "avg_price": Decimal(
                                    str(pos_data.get("avgPrice", "0"))
                                ),
                                "unrealisedPnl": unrealised_pnl,
                                "leverage": Decimal(str(pos_data.get("leverage", "1"))),
                                "liq_price": Decimal(
                                    str(pos_data.get("liqPrice", "0"))
                                ),
                            }
                            self.log.debug(
                                f"{side} position updated",
                                size=float(current_size),
                                pnl=float(unrealised_pnl),
                            )

                # Calculate total PnL AFTER updating all positions for the symbol
                total_pnl = sum(
                    pos.get("unrealisedPnl", Decimal("0"))
                    for pos in self.market_state.positions.values()
                )
                self.session_stats.update_pnl(total_pnl)

            elif topic == "wallet":
                for wallet_data in msg["data"]:
                    if wallet_data.get("coin") == "USDT":
                        self.market_state.available_balance = Decimal(
                            str(wallet_data.get("availableToWithdraw", "0"))
                        )
                        self.market_state.last_balance_update = time.time()
                        self.log.debug(
                            "Wallet balance updated via WS",
                            balance=float(self.market_state.available_balance),
                        )

            processing_time = time.time() - message_start_time
            latency_score = max(0.0, 1.0 - (processing_time / 0.5))
            self.bot_health.update_component(
                "ws_private_latency",
                float(latency_score),
                f"Private WS Latency: {processing_time:.3f}s",
            )

        except (KeyError, ValueError, TypeError, DecimalException) as e:
            self.log.error(f"Error processing private WS message: {e}", msg_payload=msg)
            self.performance_monitor.record_error("websocket_private_error")
            self.bot_health.update_component(
                "ws_private_data_quality", 0.0, f"Private WS Data Error: {e}"
            )
            if sentry_sdk:
                sentry_sdk.capture_exception(e)
        except Exception as e:
            self.log.critical(
                f"Critical error in private WS handler: {e}", exc_info=True
            )
            self.performance_monitor.record_error("websocket_private_critical")
            self.bot_health.update_component(
                "ws_private_data_quality", 0.0, f"Private WS Critical Error: {e}"
            )
            if sentry_sdk:
                sentry_sdk.capture_exception(e)

    async def _resolve_ws_command_future(self, req_id: str, msg: dict[str, Any]):
        """Resolves an asyncio.Future associated with a WebSocket command response."""
        async with self._ws_command_lock:
            future = self._ws_command_futures.get(req_id)
            if future and not future.done():
                future.set_result(msg)
                self.log.debug(f"Resolved WS command future for req_id: {req_id}")
            else:
                self.log.debug(
                    f"No active future found for req_id: {req_id} or already done."
                )

    async def _send_ws_command(
        self, op: str, args: list[Any], timeout: int = 10
    ) -> dict | None:
        """Sends a WebSocket command and waits for its response."""
        if not self.private_ws or not self._private_connected.is_set():
            self.log.warning(
                f"Cannot send WS command '{op}': Private WS not connected."
            )
            return {"retCode": -1, "retMsg": "Private WS not connected."}

        req_id = str(uuid.uuid4())
        message = {"id": req_id, "op": op, "args": args}

        async with self._ws_command_lock:
            future = asyncio.get_event_loop().create_future()
            self._ws_command_futures[req_id] = future

        try:
            self.log.debug(f"Sending WS command: {op}", req_id=req_id, args=args)
            self.private_ws.send(json.dumps(message))

            response = await asyncio.wait_for(future, timeout=timeout)
            self.log.debug(
                f"Received WS command response for {op}",
                req_id=req_id,
                response=response,
            )
            return response
        except TimeoutError:
            self.log.error(
                f"WS command '{op}' timed out after {timeout}s", req_id=req_id
            )
            return {"retCode": -1, "retMsg": "WS Command Timeout"}
        except Exception as e:
            self.log.error(
                f"Error sending WS command '{op}': {e}", req_id=req_id, exc_info=True
            )
            return {"retCode": -1, "retMsg": f"WS Command Error: {e}"}
        finally:
            async with self._ws_command_lock:
                self._ws_command_futures.pop(req_id, None)

    @asynccontextmanager
    async def api_call_context(self, method_name: str):
        """Enhanced API call context manager for rate limiting and performance monitoring"""
        start_time = time.time()
        try:
            await rate_limiter.acquire()  # Acquire token from rate limiter
            yield
        finally:
            duration = time.time() - start_time
            self.performance_monitor.record_api_call(duration, method_name)

    async def api_call_with_retry(
        self, api_method: Callable, *args, **kwargs
    ) -> dict | None:
        """Enhanced API call with robust retry logic and error handling."""
        method_name = getattr(api_method, "__name__", str(api_method))

        async with self.api_call_context(method_name):
            for attempt in range(1, 6):  # Max 5 attempts
                try:
                    response = api_method(*args, **kwargs)

                    if response and response.get("retCode") == 0:
                        rate_limiter.record_success(True)
                        self.bot_health.update_component(
                            f"api_status_{method_name}", 1.0, "API Call OK"
                        )
                        return response

                    ret_code = response.get("retCode") if response else None
                    ret_msg = (
                        response.get("retMsg", "Unknown error")
                        if response
                        else "No response"
                    )

                    self.session_stats.record_api_error(str(ret_code))
                    rate_limiter.record_success(False)

                    self.log.warning(
                        f"API call failed: {method_name}",
                        attempt=attempt,
                        error_code=ret_code,
                        error_msg=ret_msg,
                    )

                    self.bot_health.update_component(
                        f"api_status_{method_name}",
                        0.5,
                        f"API Error {ret_code}: {ret_msg}",
                    )

                    # Retryable errors (e.g., rate limit, system error, service unavailable)
                    if ret_code in [10001, 10006, 30034, 30035, 10018, 10005]:
                        if attempt < 5:
                            delay = min(
                                30, 2 * (2 ** (attempt - 1))
                            )  # Exponential backoff, max 30s
                            self.log.debug(
                                f"Retrying API call {method_name} in {delay}s..."
                            )
                            await asyncio.sleep(delay)
                            continue
                    # Non-retryable errors (e.g., invalid signature, param error)
                    elif ret_code in [10007, 10002]:
                        self.log.error(
                            f"Non-retryable API error: {ret_msg}", error_code=ret_code
                        )
                        self.bot_health.update_component(
                            f"api_status_{method_name}",
                            0.0,
                            f"Non-retryable API Error: {ret_msg}",
                        )
                        if sentry_sdk:
                            sentry_sdk.capture_message(
                                f"Non-retryable API error {ret_code}: {ret_msg}"
                            )
                        return None
                    else:  # Unhandled errors
                        self.log.error(
                            f"Unhandled API error {ret_code}: {ret_msg}",
                            error_code=ret_code,
                        )
                        self.bot_health.update_component(
                            f"api_status_{method_name}",
                            0.0,
                            f"Unhandled API Error: {ret_msg}",
                        )
                        if sentry_sdk:
                            sentry_sdk.capture_message(
                                f"Unhandled API error {ret_code}: {ret_msg}"
                            )
                        return None

                except Exception as e:
                    self.log.error(
                        f"API call exception: {method_name}",
                        attempt=attempt,
                        error=str(e),
                        exc_info=True,
                    )
                    self.performance_monitor.record_error(
                        f"api_exception_{method_name}"
                    )
                    rate_limiter.record_success(False)
                    self.bot_health.update_component(
                        f"api_status_{method_name}", 0.0, f"API Exception: {e}"
                    )
                    if sentry_sdk:
                        sentry_sdk.capture_exception(e)

                    if attempt < 5:
                        delay = min(30, 2 * (2 ** (attempt - 1)))
                        self.log.debug(
                            f"Retrying API call {method_name} in {delay}s due to exception..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        self.log.critical(
                            f"API call failed after all retries: {method_name} - {e}"
                        )
                        return None

            return None  # All retries exhausted

    async def monitor_heartbeats(self):
        """Sends internal heartbeat and updates connection health."""
        last_heartbeat_sent = time.time()
        while not _SHUTDOWN_REQUESTED:
            try:
                current_time = time.time()
                if current_time - last_heartbeat_sent > self.config.HEARTBEAT_INTERVAL:
                    last_heartbeat_sent = current_time
                    self.log.debug("💓 Internal heartbeat signal")

                # Aggregate WS connection health
                public_ws_ok = self._public_connected.is_set()
                private_ws_ok = self._private_connected.is_set()
                overall_ws_score = 1.0 if public_ws_ok and private_ws_ok else 0.0

                self.bot_health.update_component(
                    "ws_overall_connection",
                    float(overall_ws_score),
                    f"Public: {'OK' if public_ws_ok else 'DISC'}, Private: {'OK' if private_ws_ok else 'DISC'}",
                )

                # Check for data freshness using market_state's method
                self.market_state.is_data_fresh(
                    self.config.CB_STALE_DATA_TIMEOUT_SEC
                )  # This updates health component internally

                await asyncio.sleep(
                    self.config.HEARTBEAT_INTERVAL / 2
                )  # Check more frequently than full interval
            except Exception as e:
                self.log.error(f"Error in connection monitoring: {e}", exc_info=True)
                if sentry_sdk:
                    sentry_sdk.capture_exception(e)
                await asyncio.sleep(5)

    async def get_symbol_info(self) -> bool:
        """Fetches and updates symbol information."""
        response = await self.api_call_with_retry(
            self.http.get_instruments_info,
            category=self.config.CATEGORY,
            symbol=self.config.SYMBOL,
        )

        if response and response.get("retCode") == 0:
            instruments = response.get("result", {}).get("list")
            if instruments:
                instrument = instruments[0]
                price_filter = instrument.get("priceFilter", {})
                lot_size_filter = instrument.get("lotSizeFilter", {})

                self.symbol_info.price_precision = Decimal(
                    str(price_filter.get("tickSize", "0.0001"))
                )
                self.symbol_info.qty_precision = Decimal(
                    str(lot_size_filter.get("qtyStep", "0.001"))
                )
                self.symbol_info.min_price = Decimal(
                    str(price_filter.get("minPrice", "0"))
                )
                self.symbol_info.min_qty = Decimal(
                    str(lot_size_filter.get("minQty", "0"))
                )
                self.symbol_info.max_qty = Decimal(
                    str(lot_size_filter.get("maxOrderQty", "1000000"))
                )
                self.symbol_info.min_order_value = Decimal(
                    str(lot_size_filter.get("minOrderAmt", "10.0"))
                )

                self.log.info(
                    "📊 Symbol info loaded successfully", symbol=self.config.SYMBOL
                )
                self.bot_health.update_component(
                    "symbol_info_load", 1.0, "Symbol info loaded"
                )
                return True

        self.log.error("❌ Failed to fetch symbol info", symbol=self.config.SYMBOL)
        self.bot_health.update_component(
            "symbol_info_load", 0.0, "Failed to load symbol info"
        )
        return False

    async def test_credentials(self) -> bool:
        """Tests API credentials by attempting to get wallet balance."""
        response = await self.api_call_with_retry(
            self.http.get_wallet_balance,
            accountType="UNIFIED",  # Use UNIFIED for Unified Trading Account
        )

        if response and response.get("retCode") == 0:
            self.log.info("✅ API credentials validated successfully")
            self.bot_health.update_component("api_credentials", 1.0, "Credentials OK")
            return True

        self.log.critical(
            "❌ API credentials validation failed. Check API key/secret and permissions."
        )
        self.bot_health.update_component("api_credentials", 0.0, "Credentials FAILED")
        if sentry_sdk:
            sentry_sdk.capture_message("API credentials validation failed.")
        return False

    async def get_wallet_balance(self) -> bool:
        """Fetches and updates wallet balance."""
        response = await self.api_call_with_retry(
            self.http.get_wallet_balance, accountType="UNIFIED"
        )

        if response and response.get("retCode") == 0:
            balance_list = response.get("result", {}).get("list", [])
            for balance in balance_list:
                for coin in balance.get("coin", []):
                    if coin.get("coin") == "USDT":
                        available_to_withdraw = coin.get("availableToWithdraw")
                        if available_to_withdraw:
                            self.market_state.available_balance = Decimal(
                                str(available_to_withdraw)
                            )
                        else:
                            self.market_state.available_balance = Decimal("0")
                        self.market_state.last_balance_update = time.time()
                        self.log.debug(
                            "Wallet balance updated via HTTP",
                            balance=float(self.market_state.available_balance),
                        )
                        return True
        self.log.warning("Failed to fetch wallet balance via HTTP")
        return False

    async def get_open_orders(self) -> bool:
        """Fetches and updates current open orders."""
        response = await self.api_call_with_retry(
            self.http.get_open_orders,
            category=self.config.CATEGORY,
            symbol=self.config.SYMBOL,
        )

        if response and response.get("retCode") == 0:
            orders = response.get("result", {}).get("list", [])
            self.market_state.open_orders.clear()  # Clear existing before populating

            for order in orders:
                order_id = order.get("orderId")
                if order_id:
                    self.market_state.open_orders[order_id] = {
                        "client_order_id": order.get("orderLinkId", "N/A"),
                        "symbol": order.get("symbol"),
                        "side": order.get("side"),
                        "price": Decimal(str(order.get("price", "0"))),
                        "qty": Decimal(str(order.get("qty", "0"))),
                        "status": order.get("orderStatus"),
                        "timestamp": float(order.get("createdTime", 0)) / 1000,
                    }
            self.log.debug(
                f"Fetched {len(self.market_state.open_orders)} open orders via HTTP"
            )
            return True
        self.log.warning("Failed to fetch open orders via HTTP")
        return False

    async def get_positions(self) -> bool:
        """Fetches and updates current positions."""
        response = await self.api_call_with_retry(
            self.http.get_positions,
            category=self.config.CATEGORY,
            symbol=self.config.SYMBOL,
        )

        if response and response.get("retCode") == 0:
            positions = response.get("result", {}).get("list", [])
            self.market_state.positions.clear()  # Clear existing before populating

            for pos in positions:
                if (
                    pos.get("symbol") == self.config.SYMBOL
                    and Decimal(str(pos.get("size", "0"))) > 0
                ):
                    side = "Long" if pos.get("side") == "Buy" else "Short"
                    self.market_state.positions[side] = {
                        "size": Decimal(str(pos.get("size", "0"))),
                        "avg_price": Decimal(str(pos.get("avgPrice", "0"))),
                        "unrealisedPnl": Decimal(str(pos.get("unrealisedPnl", "0"))),
                        "leverage": Decimal(str(pos.get("leverage", "1"))),
                        "liq_price": Decimal(str(pos.get("liqPrice", "0"))),
                    }
            self.log.debug(
                f"Fetched {len(self.market_state.positions)} positions via HTTP"
            )
            # Recalculate PnL after position sync
            total_pnl = sum(
                pos.get("unrealisedPnl", Decimal("0"))
                for pos in self.market_state.positions.values()
            )
            self.session_stats.update_pnl(total_pnl)
            return True
        self.log.warning("Failed to fetch positions via HTTP")
        return False

    # MODIFIED: place_order to include post_only
    async def place_order(
        self,
        side: str,
        order_type: str,
        qty: Decimal,
        price: Decimal | None = None,
        post_only: bool = False,
    ) -> dict | None:
        """Places an order with comprehensive validation and monitoring, prioritizing WS then HTTP."""
        start_time = time.time()

        try:
            quantized_qty = qty.quantize(
                self.symbol_info.qty_precision, rounding=ROUND_DOWN
            )
            if quantized_qty <= 0 or quantized_qty < self.symbol_info.min_qty:
                self.log.warning(
                    "Invalid quantity rejected",
                    original_qty=float(qty),
                    quantized_qty=float(quantized_qty),
                    min_qty=float(self.symbol_info.min_qty),
                )
                return None

            if quantized_qty > self.symbol_info.max_qty:
                self.log.warning(
                    "Quantity exceeds maximum allowed by exchange",
                    quantity=float(quantized_qty),
                    max_qty=float(self.symbol_info.max_qty),
                )
                return None

            order_params = {
                "category": self.config.CATEGORY,
                "symbol": self.config.SYMBOL,
                "side": side,
                "orderType": order_type,
                "qty": str(quantized_qty),
                "orderLinkId": f"mmxcel-{uuid.uuid4()}",  # Unique client order ID
                "timeInForce": "GTC"
                if order_type == "Limit"
                else "IOC",  # IOC for market orders is standard
            }

            if order_type == "Limit":
                if price is None:
                    self.log.error("Limit order requires a price.")
                    return None
                rounding = ROUND_DOWN if side == "Buy" else ROUND_UP
                quantized_price = price.quantize(
                    self.symbol_info.price_precision, rounding=rounding
                )

                if quantized_price <= 0 or quantized_price < self.symbol_info.min_price:
                    self.log.warning(
                        "Price below minimum allowed by exchange rejected",
                        price=float(quantized_price),
                        min_price=float(self.symbol_info.min_price),
                    )
                    return None

                # Check if limit price is too far from mid_price (potential for adverse fill/slippage)
                if (
                    self.market_state.mid_price > 0
                    and self.config.MAX_SLIPPAGE_PERCENTAGE > 0
                ):
                    price_deviation = (
                        abs(quantized_price - self.market_state.mid_price)
                        / self.market_state.mid_price
                    )
                    if price_deviation > self.config.MAX_SLIPPAGE_PERCENTAGE:
                        self.log.warning(
                            f"Limit price ({float(quantized_price):.{calculate_decimal_precision(quantized_price)}f}) too far from mid price ({float(self.market_state.mid_price):.{calculate_decimal_precision(self.market_state.mid_price)}f}). Potential for non-fill or adverse fill if market moves.",
                            expected_slippage=f"{float(price_deviation):.4f}",
                            max_allowed=f"{float(self.config.MAX_SLIPPAGE_PERCENTAGE):.4f}",
                        )

                order_params["price"] = str(quantized_price)

                order_value = quantized_qty * quantized_price
                if order_value < self.symbol_info.min_order_value:
                    self.log.warning(
                        "Order value below minimum required by exchange",
                        order_value=float(order_value),
                        min_value=float(self.symbol_info.min_order_value),
                    )
                    return None

                if post_only:
                    order_params["postOnly"] = "true"

            # --- Attempt WS order placement first ---
            response = await self._send_ws_command("order.create", [order_params])

            if response and response.get("retCode") == 0:
                self.session_stats.orders_placed += 1
                order_latency = time.time() - start_time
                self.performance_monitor.record_order_latency(order_latency)

                # Store the order with its client_order_id and creation timestamp locally for tracking
                order_id = response["result"].get("orderId")
                if order_id:
                    self.market_state.open_orders[order_id] = {
                        "client_order_id": order_params["orderLinkId"],
                        "symbol": self.config.SYMBOL,
                        "side": side,
                        "price": price
                        if price
                        else self.market_state.mid_price,  # Estimate market order price for tracking
                        "qty": quantized_qty,
                        "status": "New",  # Assume new until WS confirms
                        "timestamp": time.time(),  # Use current time for creation
                    }

                self.log.info(
                    "🎯 Order placed successfully via WS",
                    order_id=order_id,
                    side=side,
                    quantity=float(quantized_qty),
                    price=float(price) if price else "Market",
                    latency=f"{order_latency:.3f}s",
                )
                self.send_toast(
                    f"📝 {side} {quantized_qty} @ {float(price):.{calculate_decimal_precision(price)}f}"
                    if price
                    else f"📝 {side} {quantized_qty} Market",
                    "blue",
                    "white",
                )
                return response.get("result", {})

            # --- Fallback to HTTP if WS fails ---
            self.log.warning(
                f"WS order.create failed ({response.get('retMsg', 'Unknown')}), attempting HTTP fallback."
            )
            http_response = await self.api_call_with_retry(
                self.http.place_order, **order_params
            )

            if http_response and http_response.get("retCode") == 0:
                self.session_stats.orders_placed += 1
                order_latency = time.time() - start_time
                self.performance_monitor.record_order_latency(order_latency)
                order_id = http_response["result"].get("orderId")
                if order_id:
                    self.market_state.open_orders[order_id] = {
                        "client_order_id": order_params["orderLinkId"],
                        "symbol": self.config.SYMBOL,
                        "side": side,
                        "price": price if price else self.market_state.mid_price,
                        "qty": quantized_qty,
                        "status": "New",
                        "timestamp": time.time(),
                    }
                self.log.info(
                    "🎯 Order placed successfully via HTTP (WS fallback)",
                    order_id=order_id,
                    side=side,
                    quantity=float(quantized_qty),
                    price=float(price) if price else "Market",
                    latency=f"{order_latency:.3f}s",
                )
                self.send_toast(
                    f"📝 {side} {quantized_qty} @ {float(price):.{calculate_decimal_precision(price)}f}"
                    if price
                    else f"📝 {side} {quantized_qty} Market (HTTP)",
                    "blue",
                    "white",
                )
                return http_response.get("result", {})

            self.log.error(
                "Order placement failed via both WS and HTTP.",
                response=response,
                http_response=http_response,
            )
            return None

        except Exception as e:
            self.log.error(f"Error placing order: {e}", exc_info=True)
            self.performance_monitor.record_error("order_placement_error")
            if sentry_sdk:
                sentry_sdk.capture_exception(e)
            return None

    # NEW: amend_order method
    async def amend_order(
        self,
        order_id: str | None = None,
        client_order_id: str | None = None,
        new_price: Decimal | None = None,
        new_qty: Decimal | None = None,
    ) -> bool:
        """Amends an existing order, prioritizing WS then HTTP."""
        if not order_id and not client_order_id:
            self.log.error(
                "Either order_id or client_order_id must be provided for amendment."
            )
            return False

        amend_params = {
            "category": self.config.CATEGORY,
            "symbol": self.config.SYMBOL,
        }

        if order_id:
            amend_params["orderId"] = order_id
        elif client_order_id:
            amend_params["orderLinkId"] = client_order_id
        if new_price is not None:
            amend_params["price"] = str(
                new_price.quantize(self.symbol_info.price_precision)
            )
        if new_qty is not None:
            amend_params["qty"] = str(new_qty.quantize(self.symbol_info.qty_precision))

        if not amend_params.get("price") and not amend_params.get("qty"):
            self.log.warning(
                f"No new price or quantity provided for amendment of order {order_id}."
            )
            return False

        # --- Attempt WS amendment first ---
        response = await self._send_ws_command("order.amend", [amend_params])

        if response and response.get("retCode") == 0:
            self.log.info(
                "✏️ Order amended successfully via WS",
                order_id=order_id,
                new_price=new_price,
                new_qty=new_qty,
            )
            # Update local state immediately, WS will confirm later
            if order_id in self.market_state.open_orders:
                if new_price is not None:
                    self.market_state.open_orders[order_id]["price"] = new_price
                if new_qty is not None:
                    self.market_state.open_orders[order_id]["qty"] = new_qty
                self.market_state.open_orders[order_id]["timestamp"] = (
                    time.time()
                )  # Reset age
            return True
        if (
            response and response.get("retCode") == 110001
        ):  # Order does not exist (already cancelled or filled)
            self.log.info(
                f"Order {order_id} already non-existent/cancelled. Treating as successful amendment (WS).",
                order_id=order_id,
            )
            self.market_state.open_orders.pop(order_id, None)
            return True

        # --- Fallback to HTTP if WS fails ---
        self.log.warning(
            f"WS order.amend failed ({response.get('retMsg', 'Unknown')}), attempting HTTP fallback."
        )
        http_response = await self.api_call_with_retry(
            self.http.amend_order, **amend_params
        )

        if http_response and http_response.get("retCode") == 0:
            self.log.info(
                "✏️ Order amended successfully via HTTP (WS fallback)",
                order_id=order_id,
                new_price=new_price,
                new_qty=new_qty,
            )
            if order_id in self.market_state.open_orders:
                if new_price is not None:
                    self.market_state.open_orders[order_id]["price"] = new_price
                if new_qty is not None:
                    self.market_state.open_orders[order_id]["qty"] = new_qty
                self.market_state.open_orders[order_id]["timestamp"] = time.time()
            return True
        if http_response and http_response.get("retCode") == 110001:
            self.log.info(
                f"Order {order_id} already non-existent/cancelled. Treating as successful amendment (HTTP).",
                order_id=order_id,
            )
            self.market_state.open_orders.pop(order_id, None)
            return True

        self.log.error(
            "Order amendment failed via both WS and HTTP.",
            order_id=order_id,
            response=response,
            http_response=http_response,
        )
        return False

    async def cancel_order(
        self, order_id: str | None = None, client_order_id: str | None = None
    ) -> bool:
        """Cancels a specific order, prioritizing WS then HTTP."""
        if not order_id and not client_order_id:
            self.log.error(
                "Either order_id or client_order_id must be provided for cancellation."
            )
            return False

        cancel_params = {
            "category": self.config.CATEGORY,
            "symbol": self.config.SYMBOL,
        }

        if order_id:
            cancel_params["orderId"] = order_id
        elif client_order_id:
            cancel_params["orderLinkId"] = client_order_id

        # --- Attempt WS cancel first ---
        response = await self._send_ws_command("order.cancel", [cancel_params])

        if response and response.get("retCode") == 0:
            self.log.info("🗑️ Order cancelled successfully via WS", order_id=order_id)
            self.market_state.open_orders.pop(order_id, None)  # Remove from local state
            self.session_stats.orders_cancelled += 1
            return True
        if (
            response and response.get("retCode") == 110001
        ):  # Order does not exist (already cancelled or filled)
            self.log.info(
                f"Order {order_id} already non-existent/cancelled. Treating as successful cancellation (WS).",
                order_id=order_id,
            )
            self.market_state.open_orders.pop(
                order_id, None
            )  # Ensure removal from local state
            return True

        # --- Fallback to HTTP if WS fails ---
        self.log.warning(
            f"WS order.cancel failed ({response.get('retMsg', 'Unknown')}), attempting HTTP fallback."
        )
        http_response = await self.api_call_with_retry(
            self.http.cancel_order, **cancel_params
        )

        if http_response and http_response.get("retCode") == 0:
            self.log.info(
                "🗑️ Order cancelled successfully via HTTP (WS fallback)",
                order_id=order_id,
            )
            self.market_state.open_orders.pop(order_id, None)
            self.session_stats.orders_cancelled += 1
            return True

        # 110001: Order does not exist (already cancelled or filled) - treat as success for idempotency
        if http_response and http_response.get("retCode") == 110001:
            self.log.info(
                f"Order {order_id} already non-existent/cancelled. Treating as successful cancellation (HTTP).",
                order_id=order_id,
            )
            self.market_state.open_orders.pop(order_id, None)
            return True

        self.log.error(
            "Order cancellation failed via both WS and HTTP.",
            order_id=order_id,
            response=response,
            http_response=http_response,
        )
        return False

    async def cancel_all_orders(self) -> bool:
        """Cancels all active orders for the symbol, prioritizing WS then HTTP."""
        # --- Attempt WS cancel-all first ---
        response = await self._send_ws_command(
            "order.cancel-all",
            [{"category": self.config.CATEGORY, "symbol": self.config.SYMBOL}],
        )

        if response and response.get("retCode") == 0:
            order_count = len(self.market_state.open_orders)
            self.log.info("🧹 All orders cancelled via WS", count=order_count)
            self.market_state.open_orders.clear()
            self.session_stats.orders_cancelled += (
                order_count  # Assuming all were cancelled
            )
            self.send_toast(f"🧹 {order_count} orders cancelled", "orange", "white")
            return True

        # --- Fallback to HTTP if WS fails ---
        self.log.warning(
            f"WS order.cancel-all failed ({response.get('retMsg', 'Unknown')}), attempting HTTP fallback."
        )
        http_response = await self.api_call_with_retry(
            self.http.cancel_all_orders,
            category=self.config.CATEGORY,
            symbol=self.config.SYMBOL,
        )

        if http_response and http_response.get("retCode") == 0:
            order_count = len(self.market_state.open_orders)
            self.log.info(
                "🧹 All orders cancelled via HTTP (WS fallback)", count=order_count
            )
            self.market_state.open_orders.clear()
            self.session_stats.orders_cancelled += order_count
            self.send_toast(
                f"🧹 {order_count} orders cancelled (HTTP)", "orange", "white"
            )
            return True

        self.log.error(
            "Cancellation of all orders failed via both WS and HTTP.",
            response=response,
            http_response=http_response,
        )
        return False
