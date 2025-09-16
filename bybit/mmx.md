"""
MMXCEL 5.2 - Ultra-Enhanced Bybit Market-Making Bot
--------------------------------------------------
Author: AI Assistant
Original: Pyrmethus
Enhanced with 20+ major improvements and critical bug fixes
"""

import os
import asyncio
import logging
import logging.handlers
import time
import json
import signal
import sys
import select
import uuid
import psutil
import threading
import weakref
from collections import deque, defaultdict
from decimal import Decimal, getcontext, ROUND_DOWN, ROUND_UP, DecimalException
from typing import Any, Dict, Optional, List, Tuple, Union, Callable
from dataclasses import dataclass, field, asdict, fields
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import gc

# Optional imports with fallbacks
try:
    import sentry_sdk
except ImportError:
    sentry_sdk = None

try:
    import uvloop
    uvloop.install() # Install uvloop as the event loop
except ImportError:
    pass

from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket
from colorama import Fore, Style, init

# Initialize colorama for cross-platform color support
init(autoreset=True)

# High-precision decimals for financial calculations
getcontext().prec = 28 # Increased precision for critical financial calculations

# Enhanced neon color palette (unchanged from v4.0/v5.0)
NC = Style.RESET_ALL
BOLD = Style.BRIGHT
RED = Fore.RED + Style.BRIGHT
GREEN = Fore.GREEN + Style.BRIGHT
YELLOW = Fore.YELLOW + Style.BRIGHT
BLUE = Fore.BLUE + Style.BRIGHT
MAGENTA = Fore.MAGENTA + Style.BRIGHT
CYAN = Fore.CYAN + Style.BRIGHT
WHITE = Fore.WHITE + Style.BRIGHT
UNDERLINE = Style.BRIGHT + Fore.CYAN

NEON_GREEN = '\033[92m' + Style.BRIGHT
NEON_BLUE = '\033[94m' + Style.BRIGHT
NEON_PINK = '\033[95m' + Style.BRIGHT
NEON_ORANGE = '\033[93m' + Style.BRIGHT
NEON_PURPLE = '\033[35m' + Style.BRIGHT
NEON_CYAN = '\033[96m' + Style.BRIGHT

# Load environment variables
load_dotenv()
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
SENTRY_DSN = os.getenv("SENTRY_DSN")
LOG_AS_JSON = os.getenv("LOG_AS_JSON", "0") == "1"

# Global state management
_SHUTDOWN_REQUESTED = False
_HAS_TERMUX_TOAST_CMD = False # Checked once at startup
BOT_STATE = "INITIALIZING"
CIRCUIT_BREAKER_STATE = "NORMAL" # NORMAL, MINOR_PAUSE, MAJOR_CANCEL, CRITICAL_SHUTDOWN

# Helper Functions
def set_bot_state(state: str):
    """Set bot state with enhanced logging"""
    global BOT_STATE
    if BOT_STATE != state:
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
    bot_health.update_component('bot_state', state_score, f"State: {state}")

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
    full_header = f"{' ' * padding_left}{color}{full_header.strip()}{NC}{' ' * padding_right}" # Strip internal header to avoid double-padding calculation issues
    print(full_header)

def print_neon_separator(length: int = 80, char: str = "─", color: str = NEON_BLUE) -> None:
    """Print neon separator line"""
    if not config.NEON_COLORS_ENABLED:
        color = CYAN
    print(f"{color}{char * length}{NC}")

def format_metric(
    label: str,
    value: Any,
    label_color: str,
    value_color: Optional[str] = None,
    label_width: int = 25,
    value_precision: Optional[int] = None,
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
        current_precision = value_precision if value_precision is not None else calculate_decimal_precision(value)
        if is_pnl:
            actual_value_color = NEON_GREEN if value >= Decimal("0") else RED
        formatted_value = f"{actual_value_color}{value:,.{current_precision}f}{unit}{NC}"
    elif isinstance(value, (int, float)):
        if is_pnl:
            actual_value_color = NEON_GREEN if value >= 0 else RED
        formatted_value = f"{actual_value_color}{value:,}{unit}{NC}"
    else:
        formatted_value = f"{actual_value_color}{str(value)}{unit}{NC}"
    
    return f"{formatted_label}: {formatted_value}"

def check_termux_toast() -> bool:
    """Check if termux-toast is available"""
    return os.system("command -v termux-toast > /dev/null 2>&1") == 0

def send_toast(message: str, color: str = "#336699", text_color: str = "white") -> None:
    """Send toast notification"""
    if _HAS_TERMUX_TOAST_CMD:
        try:
            os.system(f"termux-toast -b '{color}' -c '{text_color}' '{message}'")
        except Exception as e:
            log.warning(f"Failed to send Termux toast: {e}")
    else:
        log.debug(f"Toast notification: {message}")


# Bot Health Monitoring
class BotHealth:
    """Enhanced health monitoring with weighted components"""
    
    def __init__(self):
        self.overall_score = 1.0
        self.components = defaultdict(lambda: {
            'score': 1.0, 
            'last_check': time.time(), 
            'message': 'OK',
            'weight': 1.0
        })
        
        # Set component weights
        self.components['system_memory']['weight'] = 1.5
        self.components['api_performance']['weight'] = 1.2
        self.components['market_data_freshness']['weight'] = 1.3
        self.components['ws_overall_connection']['weight'] = 2.0 # Critical component
        self.components['bot_state']['weight'] = 1.0
        self.components['strategy_pnl']['weight'] = 1.5
        self.components['symbol_info_load']['weight'] = 1.8
        self.components['api_credentials']['weight'] = 2.0 # Critical
    
    def update_component(self, name: str, score: float, message: str = 'OK', weight: Optional[float] = None):
        """Update component with weighted score"""
        current_weight = self.components[name]['weight'] if weight is None else weight
        self.components[name].update({
            'score': max(0.0, min(1.0, score)),
            'last_check': time.time(),
            'message': message,
            'weight': current_weight # Use specified weight or existing
        })
        self._calculate_overall_score()
        
    def _calculate_overall_score(self):
        """Calculate weighted overall score"""
        # Only consider components updated within the last 2 minutes for score calculation
        active_components = [c for c in self.components.values() 
                           if time.time() - c['last_check'] < 120] 
        
        if not active_components:
            self.overall_score = 1.0
            return
            
        total_weight = sum(c['weight'] for c in active_components)
        weighted_sum = sum(c['score'] * c['weight'] for c in active_components)
        self.overall_score = weighted_sum / total_weight if total_weight > 0 else 1.0
        
    def get_status_message(self) -> str:
        """Get health status as human-readable string"""
        if self.overall_score >= 0.9: return "EXCELLENT"
        if self.overall_score >= 0.7: return "GOOD"
        if self.overall_score >= 0.5: return "DEGRADED"
        if self.overall_score >= 0.3: return "POOR"
        return "CRITICAL"
    
    def get_health_report(self) -> Dict[str, Any]:
        """Generate comprehensive health report"""
        return {
            'overall_score': self.overall_score,
            'status': self.get_status_message(),
            'components': dict(self.components),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

bot_health = BotHealth()

# Enhanced Rate Limiting with Adaptive Backoff
class AdaptiveRateLimiter:
    """Advanced rate limiter with dynamic backoff and token bucket algorithm."""
    
    def __init__(self, config: 'BotConfig'): # Type hint as string for forward reference
        self.config = config
        self.tokens = Decimal(str(config.RATE_LIMIT_BURST_LIMIT)) # Use config for burst limit
        self.last_update = time.time()
        self.lock = asyncio.Lock()
        self.success_rate = deque(maxlen=100) # Records 1 for success, 0 for failure
        self.current_rate = Decimal(str(config.RATE_LIMIT_REQUESTS_PER_SECOND))
        self.backoff_factor = Decimal("1.0") # Start with no backoff

    async def acquire(self) -> None:
        """Acquire a token, waiting if necessary with adaptive backoff."""
        async with self.lock:
            now = time.time()
            elapsed = Decimal(str(now - self.last_update))
            
            # Adaptive rate adjustment
            if self.config.RATE_LIMIT_ADAPTIVE_SCALING and len(self.success_rate) > 10:
                recent_success_avg = sum(self.success_rate) / len(self.success_rate)
                if recent_success_avg > 0.95:  # Very high success, slightly increase rate
                    self.current_rate = min(
                        Decimal(str(self.config.RATE_LIMIT_REQUESTS_PER_SECOND * 1.5)), # Cap at 1.5x default
                        self.current_rate * Decimal('1.05') # Gentle increase
                    )
                    self.backoff_factor = max(Decimal("1.0"), self.backoff_factor * Decimal('0.9')) # Reduce backoff
                elif recent_success_avg < 0.7:  # Low success, significantly decrease rate and increase backoff
                    self.current_rate = max(
                        Decimal(str(self.config.RATE_LIMIT_REQUESTS_PER_SECOND * 0.3)), # Min 0.3x default
                        self.current_rate * Decimal('0.9') # More aggressive decrease
                    )
                    self.backoff_factor = min(Decimal("5.0"), self.backoff_factor * Decimal('1.2')) # Max 5x backoff
                else: # Moderate success, gently adjust towards default and reduce backoff
                    self.current_rate = (self.current_rate + Decimal(str(self.config.RATE_LIMIT_REQUESTS_PER_SECOND))) / Decimal("2")
                    self.backoff_factor = max(Decimal("1.0"), self.backoff_factor * Decimal('0.95'))

            # Add tokens based on current rate and elapsed time
            tokens_to_add = elapsed * self.current_rate
            self.tokens = min(Decimal(str(self.config.RATE_LIMIT_BURST_LIMIT)), self.tokens + tokens_to_add)
            self.last_update = now
            
            # If not enough tokens, calculate wait time and sleep
            if self.tokens < 1:
                wait_time = (Decimal("1") - self.tokens) / self.current_rate
                wait_time *= self.backoff_factor # Apply adaptive backoff
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
            self.backoff_factor = max(Decimal("1.0"), self.backoff_factor * Decimal('0.99'))


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
    PRICE_THRESHOLD: Decimal = Decimal("0.0002") # Used for stale order repricing
    USE_TESTNET: bool = True
    ORDER_REFRESH_INTERVAL: int = 5 # How often to refresh open orders (HTTP, if WS down)
    BALANCE_REFRESH_INTERVAL: int = 30 # How often to refresh balance (HTTP, if WS down)
    CAPITAL_ALLOCATION_PERCENTAGE: Decimal = Decimal("0.05") # % of available balance to consider for trade size
    ABNORMAL_SPREAD_THRESHOLD: Decimal = Decimal("0.015") # For warning/CB
    REBALANCE_ORDER_TYPE: str = "Market" # "Market" or "Limit"
    REBALANCE_PRICE_OFFSET_PERCENTAGE: Decimal = Decimal("0") # Offset for Limit rebalance orders
    MAX_POSITION_SIZE: Decimal = Decimal("0.1") # Max % of available balance for a single position
    VOLATILITY_ADJUSTMENT: bool = True # Enable dynamic spread adjustment
    MAX_SLIPPAGE_PERCENTAGE: Decimal = Decimal("0.001") # Max allowed slippage for executed trades (warning)
    ORDERBOOK_DEPTH_LEVELS: int = 5 # Number of levels to subscribe to for orderbook
    HEARTBEAT_INTERVAL: int = 30 # Interval for internal heartbeats and health checks
    MEMORY_CLEANUP_INTERVAL: int = 300 # How often to run garbage collection
    CONFIG_RELOAD_INTERVAL: int = 30 # How often to check config.json for changes
    
    NEON_COLORS_ENABLED: bool = True
    DASHBOARD_REFRESH_RATE: float = 0.7 # How often to refresh the terminal dashboard

    # NEW IMPROVEMENTS (from v5.0 skeleton and further enhancements)
    PERFORMANCE_LOG_INTERVAL: int = 300 # How often to log detailed performance summary
    MAX_LOG_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB
    TRADE_JOURNAL_FILE_SIZE: int = 20 * 1024 * 1024 # 20MB
    
    TRADING_HOURS_ENABLED: bool = False
    TRADING_START_HOUR_UTC: int = 0  # 0-23
    TRADING_END_HOUR_UTC: int = 23 # 0-23
    
    ADAPTIVE_QUANTITY_ENABLED: bool = True
    ADAPTIVE_QUANTITY_PERFORMANCE_FACTOR: Decimal = Decimal("0.1") # Influence of performance on quantity
    
    # Circuit Breaker Config (integrated)
    CIRCUIT_BREAKER_ENABLED: bool = True
    CB_PNL_STOP_LOSS_PCT: Decimal = Decimal("0.02") # PnL loss percentage to trigger critical CB
    CB_ABNORMAL_SPREAD_PCT: Decimal = Decimal("0.015") # Abnormal spread percentage to trigger minor CB
    CB_STALE_DATA_TIMEOUT_SEC: int = 30 # Max seconds for market data freshness before CB
    CB_LOW_CONNECTION_THRESHOLD: float = 0.3 # BotHealth.overall_score threshold for connection quality
    CB_LOW_ORDER_SUCCESS_THRESHOLD: float = 0.2 # Order success rate threshold for CB
    CB_HIGH_MEMORY_MB: int = 1000 # Memory usage (MB) to trigger minor CB
    CB_MINOR_PAUSE_THRESHOLD: float = 0.6 # BotHealth.overall_score for MINOR_PAUSE
    CB_MAJOR_CANCEL_THRESHOLD: float = 0.4 # BotHealth.overall_score for MAJOR_CANCEL
    CB_CRITICAL_SHUTDOWN_THRESHOLD: float = 0.2 # BotHealth.overall_score for CRITICAL_SHUTDOWN

    # Rate Limiter Config (new section from previous code)
    RATE_LIMIT_REQUESTS_PER_SECOND: int = 10
    RATE_LIMIT_BURST_LIMIT: int = 20
    RATE_LIMIT_ADAPTIVE_SCALING: bool = True
    
    # Plugin System (new from v5.0 skeleton)
    PLUGIN_FOLDER: str = "plugins"
    ENABLE_PLUGINS: bool = True
    STRATEGY_PLUGIN_NAME: Optional[str] = None # Name of the specific strategy plugin to use, e.g., "my_custom_strategy"

    def __post_init__(self):
        """Enhanced validation with detailed checks"""
        validations = [
            (self.SPREAD_PERCENTAGE > 0, "SPREAD_PERCENTAGE must be positive"),
            (self.MAX_OPEN_ORDERS > 0, "MAX_OPEN_ORDERS must be positive"),
            (self.SYMBOL, "SYMBOL cannot be empty"),
            (Decimal("0") < self.CAPITAL_ALLOCATION_PERCENTAGE <= Decimal("1"), "CAPITAL_ALLOCATION_PERCENTAGE must be between 0 and 1"),
            (Decimal("0") < self.MAX_POSITION_SIZE <= Decimal("1"), "MAX_POSITION_SIZE must be between 0 and 1"),
            (self.ORDERBOOK_DEPTH_LEVELS > 0, "ORDERBOOK_DEPTH_LEVELS must be positive"),
            (self.DASHBOARD_REFRESH_RATE > 0, "DASHBOARD_REFRESH_RATE must be positive"),
            (self.HEARTBEAT_INTERVAL > 0, "HEARTBEAT_INTERVAL must be positive"),
            (self.QUANTITY > 0, "QUANTITY must be positive"),
            (self.ORDER_LIFESPAN_SECONDS > 0, "ORDER_LIFESPAN_SECONDS must be positive"),
            (self.REBALANCE_THRESHOLD_QTY >= 0, "REBALANCE_THRESHOLD_QTY must be non-negative"),
            (self.PROFIT_PERCENTAGE > 0, "PROFIT_PERCENTAGE must be positive"),
            (self.STOP_LOSS_PERCENTAGE > 0, "STOP_LOSS_PERCENTAGE must be positive"),
            (self.PRICE_THRESHOLD >= 0, "PRICE_THRESHOLD must be non-negative"),
            (self.ABNORMAL_SPREAD_THRESHOLD > 0, "ABNORMAL_SPREAD_THRESHOLD must be positive"),
            (self.MAX_SLIPPAGE_PERCENTAGE >= 0, "MAX_SLIPPAGE_PERCENTAGE must be non-negative"),
            (self.PERFORMANCE_LOG_INTERVAL > 0, "PERFORMANCE_LOG_INTERVAL must be positive"),
            (self.MAX_LOG_FILE_SIZE > 0, "MAX_LOG_FILE_SIZE must be positive"),
            (self.TRADE_JOURNAL_FILE_SIZE > 0, "TRADE_JOURNAL_FILE_SIZE must be positive"),
            (self.MEMORY_CLEANUP_INTERVAL > 0, "MEMORY_CLEANUP_INTERVAL must be positive"),
            (self.CONFIG_RELOAD_INTERVAL > 0, "CONFIG_RELOAD_INTERVAL must be positive"),
            (self.RATE_LIMIT_REQUESTS_PER_SECOND > 0, "RATE_LIMIT_REQUESTS_PER_SECOND must be positive"),
            (self.RATE_LIMIT_BURST_LIMIT > 0, "RATE_LIMIT_BURST_LIMIT must be positive"),
        ]
        
        for condition, message in validations:
            if not condition:
                raise ValueError(f"Configuration validation failed: {message}")
        
        if not (0 <= self.TRADING_START_HOUR_UTC <= 23 and 
                0 <= self.TRADING_END_HOUR_UTC <= 23):
            raise ValueError("TRADING_START_HOUR_UTC and TRADING_END_HOUR_UTC must be between 0 and 23")
        
        if not (0 <= self.CB_CRITICAL_SHUTDOWN_THRESHOLD <= self.CB_MAJOR_CANCEL_THRESHOLD <= self.CB_MINOR_PAUSE_THRESHOLD <= 1.0):
            raise ValueError("Circuit breaker thresholds must be in ascending order for severity (CRITICAL <= MAJOR <= MINOR).")
        if not (0 <= self.CB_LOW_CONNECTION_THRESHOLD <= 1.0 and 0 <= self.CB_LOW_ORDER_SUCCESS_THRESHOLD <= 1.0):
            raise ValueError("Circuit breaker connection/success thresholds must be between 0 and 1.")
        
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
        self.callbacks: List[Callable[[BotConfig], None]] = []
    
    def _load_config_safe(self) -> BotConfig:
        """Safely load configuration with error handling"""
        try:
            with open(self.config_file, "r") as f:
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
                            config_data[key] = config_data[key].lower() in ('true', '1', 't', 'y', 'yes')
                        else:
                            config_data[key] = bool(config_data[key])
                    # Handle int/float for safety
                    elif isinstance(getattr(default_config_instance, key), int):
                        config_data[key] = int(config_data[key])
                    elif isinstance(getattr(default_config_instance, key), float):
                        config_data[key] = float(config_data[key])
                    # String values like SYMBOL are kept as is
            
            known_fields = {f.name for f in fields(BotConfig)}
            filtered_config_data = {k: v for k, v in config_data.items() if k in known_fields}
            config = BotConfig(**filtered_config_data)
            self.load_errors = 0  # Reset error count on successful load
            return config
            
        except FileNotFoundError:
            print(f"WARNING: config.json not found. Creating default configuration...")
            config = BotConfig()
            self._save_default_config(config)
            return config
        except Exception as e:
            self.load_errors += 1
            print(f"ERROR: Error loading configuration (attempt {self.load_errors}): {e}")
            
            if self.load_errors >= self.max_load_errors:
                print(f"CRITICAL: Max configuration load errors reached. Using default config. Please fix config.json immediately.")
                return BotConfig()
            
            # Return current configuration if available, otherwise default
            return getattr(self, 'config', BotConfig())
    
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
            print(f"INFO: Default config.json created successfully")
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
                print(f"INFO: Configuration updated detected, reloading...")
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

# Enhanced System Monitoring
class SystemMonitor:
    """Advanced system monitoring with comprehensive metrics"""
    def __init__(self):
        self.process = psutil.Process()
        self.start_time = time.time()
        self.memory_samples = deque(maxlen=200)
        self.cpu_samples = deque(maxlen=200)
        self.network_stats = {'bytes_sent': 0, 'bytes_recv': 0}
        self.last_network_check = time.time()
        self.peak_memory = 0
        self.memory_warnings = 0
        self.cpu_warnings = 0
    
    def update_stats(self):
        """Update system statistics with enhanced monitoring"""
        try:
            # Memory usage
            memory_info = self.process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            self.memory_samples.append(memory_mb)
            
            # Track peak memory
            if memory_mb > self.peak_memory:
                self.peak_memory = memory_mb
            
            # Memory warning threshold (500MB)
            if memory_mb > 500: # General warning threshold, distinct from CB
                self.memory_warnings += 1
                if self.memory_warnings % 10 == 0:
                    log.warning(f"High memory usage warning", memory_mb=f"{memory_mb:.1f}MB")
            
            # CPU usage
            cpu_percent = self.process.cpu_percent()
            self.cpu_samples.append(cpu_percent)
            
            # CPU warning threshold (80%)
            if cpu_percent > 80:
                self.cpu_warnings += 1
                if self.cpu_warnings % 5 == 0:
                    log.warning(f"High CPU usage warning", cpu_percent=f"{cpu_percent:.1f}%")
            
            # Network stats (updates less frequently)
            current_time = time.time()
            if current_time - self.last_network_check > 5:
                try:
                    net_io = psutil.net_io_counters()
                    if net_io:
                        self.network_stats['bytes_sent'] = net_io.bytes_sent
                        self.network_stats['bytes_recv'] = net_io.bytes_recv
                except Exception as e:
                    log.debug(f"Could not retrieve network stats: {e}")
                self.last_network_check = current_time
            
            # Update bot health component
            mem_score = max(0.0, 1.0 - (memory_mb / config.CB_HIGH_MEMORY_MB)) if config.CB_HIGH_MEMORY_MB > 0 else 1.0
            cpu_score = max(0.0, 1.0 - (cpu_percent / 100.0))
            
            bot_health.update_component('system_memory', float(mem_score), f"Mem: {memory_mb:.1f}MB")
            bot_health.update_component('system_cpu', float(cpu_score), f"CPU: {cpu_percent:.1f}%")
                
        except Exception as e:
            log.error(f"Error updating system stats: {e}")
    
    def get_memory_usage(self) -> float:
        """Get current memory usage in MB"""
        return self.memory_samples[-1] if self.memory_samples else 0
    
    def get_avg_cpu_usage(self) -> float:
        """Get average CPU usage"""
        return sum(self.cpu_samples) / len(self.cpu_samples) if self.cpu_samples else 0
    
    def get_peak_memory(self) -> float:
        """Get peak memory usage"""
        return self.peak_memory
    
    def cleanup_memory(self) -> int:
        """Enhanced memory cleanup"""
        try:
            collected = gc.collect()
            # Reduce history if memory is high to free up RAM taken by deques
            if self.get_memory_usage() > 300:
                if len(self.memory_samples) > 50:
                    self.memory_samples = deque(list(self.memory_samples)[-50:], maxlen=200)
                if len(self.cpu_samples) > 50:
                    self.cpu_samples = deque(list(self.cpu_samples)[-50:], maxlen=200)
            
            log.info(f"Memory cleanup completed", objects_collected=collected, current_memory=f"{self.get_memory_usage():.1f}MB")
            return collected
        except Exception as e:
            log.error(f"Error during memory cleanup: {e}")
            return 0

# Enhanced Symbol Information
@dataclass
class SymbolInfo:
    """Enhanced symbol information with comprehensive validation"""
    price_precision: Decimal = Decimal("0.0001")
    qty_precision: Decimal = Decimal("0.001")
    min_order_value: Decimal = Decimal("10.0")
    min_price: Decimal = Decimal("0")
    min_qty: Decimal = Decimal("0")
    max_qty: Decimal = Decimal("1000000")
    
    # Enhanced order book analysis
    bid_levels: List[Tuple[Decimal, Decimal]] = field(default_factory=list)
    ask_levels: List[Tuple[Decimal, Decimal]] = field(default_factory=list)
    total_bid_volume: Decimal = Decimal("0")
    total_ask_volume: Decimal = Decimal("0")
    last_orderbook_update: float = 0
    orderbook_update_count: int = 0
    
    def update_orderbook_depth(self, bids: List[List[str]], asks: List[List[str]]):
        """Update order book depth with enhanced validation"""
        try:
            if not bids or not asks:
                log.warning("Received empty bids/asks for orderbook update.")
                return
            
            valid_bids = []
            valid_asks = []
            
            # Only process up to config.ORDERBOOK_DEPTH_LEVELS to avoid excessive processing
            for price_str, qty_str in bids[:config.ORDERBOOK_DEPTH_LEVELS]:
                try:
                    price = Decimal(price_str)
                    qty = Decimal(qty_str)
                    if price > 0 and qty > 0:
                        valid_bids.append((price, qty))
                except (ValueError, DecimalException) as e:
                    log.debug(f"Invalid bid entry: {price_str}, {qty_str} - {e}")
                    continue
            
            for price_str, qty_str in asks[:config.ORDERBOOK_DEPTH_LEVELS]:
                try:
                    price = Decimal(price_str)
                    qty = Decimal(qty_str)
                    if price > 0 and qty > 0:
                        valid_asks.append((price, qty))
                except (ValueError, DecimalException) as e:
                    log.debug(f"Invalid ask entry: {price_str}, {qty_str} - {e}")
                    continue
            
            if valid_bids and valid_asks:
                self.bid_levels = sorted(valid_bids, key=lambda x: x[0], reverse=True) # Ensure bids sorted high to low
                self.ask_levels = sorted(valid_asks, key=lambda x: x[0]) # Ensure asks sorted low to high
                self.total_bid_volume = sum(qty for _, qty in valid_bids)
                self.total_ask_volume = sum(qty for _, qty in valid_asks)
                self.last_orderbook_update = time.time()
                self.orderbook_update_count += 1
                
        except Exception as e:
            log.error(f"Error updating orderbook depth: {e}")
    
    def get_market_depth_ratio(self) -> float:
        """Calculate market depth ratio (bid/ask volume)"""
        if self.total_ask_volume > 0 and self.total_bid_volume > 0:
            return float(self.total_bid_volume / self.total_ask_volume)
        elif self.total_bid_volume > 0:
            return float('inf') # Only bids, very bullish
        elif self.total_ask_volume > 0:
            return 0.0 # Only asks, very bearish
        return 1.0 # No liquidity, neutral
    
    def estimate_slippage(self, side: str, quantity: Decimal) -> Decimal:
        """Estimates slippage for a given quantity based on current order book depth."""
        if not self.bid_levels or not self.ask_levels:
            return Decimal("0")
        
        levels = self.ask_levels if side == "Buy" else self.bid_levels
        
        if not levels: return Decimal("0")
        
        remaining_qty = quantity
        total_price_qty = Decimal("0")
        filled_qty = Decimal("0")
        
        for price, available_qty in levels:
            if remaining_qty <= 0:
                break
            
            qty_to_take = min(remaining_qty, available_qty)
            total_price_qty += qty_to_take * price
            filled_qty += qty_to_take
            remaining_qty -= qty_to_take
            
        if filled_qty == 0:
            # If no quantity can be filled at all from available levels, implies very high slippage
            # Return a value that indicates severe slippage, e.g., a very high percentage.
            # Max possible slippage for a market order is the spread itself, or more if liquidity is exhausted.
            # Using 1.0 (100%) indicates full exhaustion or impossible fill at current prices.
            return Decimal("1.0") 
            
        avg_fill_price = total_price_qty / filled_qty
        
        # Reference price for slippage calculation (best current BBO)
        reference_price = self.ask_levels[0][0] if side == "Buy" else self.bid_levels[0][0]
        
        if reference_price == Decimal("0"): return Decimal("0")
        
        return abs(avg_fill_price - reference_price) / reference_price

# Enhanced Market State
@dataclass
class MarketState:
    """Enhanced market state with comprehensive tracking"""
    mid_price: Decimal = Decimal("0")
    best_bid: Decimal = Decimal("0")
    best_ask: Decimal = Decimal("0")
    open_orders: Dict[str, Dict] = field(default_factory=dict) # Key: order_id
    positions: Dict[str, Dict] = field(default_factory=dict) # Key: "Long" or "Short"
    last_update_time: float = 0 # Last update from public orderbook WS
    last_balance_update: float = 0 # Last update from private wallet WS/HTTP
    available_balance: Decimal = Decimal("0")
    
    trade_history: deque = field(default_factory=lambda: deque(maxlen=1000))
    price_history: deque = field(default_factory=lambda: deque(maxlen=200))
    spread_history: deque = field(default_factory=lambda: deque(maxlen=200))
    last_heartbeat: float = field(default_factory=time.time) # Last data received from exchange (any WS)
    update_frequency: deque = field(default_factory=lambda: deque(maxlen=100)) # Frequency of market data updates
    data_quality_score: Decimal = Decimal("1.0") # Reflects how frequently and correctly data is received
    
    def is_data_fresh(self, max_age: float = 10) -> bool:
        """Check if market data is fresh and update health component"""
        age = time.time() - self.last_update_time
        is_fresh = age <= max_age and self.mid_price > 0
        
        # Update data quality score (slowly recover, quickly degrade)
        if is_fresh:
            self.data_quality_score = min(Decimal("1.0"), self.data_quality_score + Decimal("0.01"))
        else:
            self.data_quality_score = max(Decimal("0.0"), self.data_quality_score - Decimal("0.05"))
        
        # Update bot health component for data freshness
        freshness_score = max(Decimal("0.0"), Decimal("1.0") - (Decimal(str(age)) / Decimal(str(max_age)))) if max_age > 0 else Decimal("1.0")
        if self.mid_price <= 0: # No valid market data available
            freshness_score = Decimal("0.0")
        
        bot_health.update_component('market_data_freshness', float(freshness_score), f"Data Age: {age:.1f}s")
        
        return is_fresh
    
    def add_trade(self, trade_data: Dict):
        """Add trade to history with validation"""
        try:
            trade_record = {
                'timestamp': trade_data.get('timestamp', time.time()), # Prefer timestamp from data if available
                'side': trade_data.get('side'),
                'price': trade_data.get('price', Decimal('0')),
                'quantity': trade_data.get('quantity', Decimal('0')),
                'order_id': trade_data.get('order_id'),
                'client_order_id': trade_data.get('client_order_id'),
                'slippage': trade_data.get('slippage_pct', Decimal('0')),
                'latency': trade_data.get('latency_ms', 0) / 1000, # Convert ms to seconds
                'type': trade_data.get('type', 'Filled')
            }
            
            if (trade_record['price'] > 0 and 
                trade_record['quantity'] > 0 and 
                trade_record['side'] in ['Buy', 'Sell']):
                self.trade_history.append(trade_record)
            
        except Exception as e:
            log.error(f"Error adding trade to history: {e}")
    
    def update_price_history(self):
        """Update price and spread history with enhanced analysis"""
        if self.mid_price > 0:
            current_time = time.time()
            
            if self.last_update_time > 0: # Ensure previous update exists
                frequency = current_time - self.last_update_time
                self.update_frequency.append(frequency)
            
            price_record = {
                'timestamp': current_time,
                'price': self.mid_price,
                'bid': self.best_bid,
                'ask': self.best_ask,
                'spread': (self.best_ask - self.best_bid) / self.mid_price if self.mid_price > 0 else Decimal('0')
            }
            
            self.price_history.append(price_record)
            
            if self.best_bid > 0 and self.best_ask > 0:
                spread = (self.best_ask - self.best_bid) / self.mid_price
                spread_record = {
                    'timestamp': current_time,
                    'spread': spread,
                    'mid_price': self.mid_price
                }
                self.spread_history.append(spread_record)
    
    def get_avg_update_frequency(self) -> float:
        """Get average market data update frequency"""
        if self.update_frequency:
            return sum(self.update_frequency) / len(self.update_frequency)
        return 0.0

# Enhanced Session Statistics
@dataclass
class SessionStats:
    """Enhanced session statistics with comprehensive tracking"""
    start_time: float = field(default_factory=time.time)
    orders_placed: int = 0
    orders_filled: int = 0
    orders_cancelled: int = 0
    orders_rejected: int = 0
    rebalances_count: int = 0
    circuit_breaker_activations: int = 0
    total_pnl: Decimal = Decimal("0") # Unrealized PnL from open positions
    max_drawdown: Decimal = Decimal("0") # Max percentage drawdown from peak PnL
    peak_balance: Decimal = Decimal("0") # Highest available balance or total capital seen
    
    total_volume_traded: Decimal = Decimal("0")
    slippage_events: int = 0
    api_errors: defaultdict = field(default_factory=lambda: defaultdict(int))
    connection_drops: int = 0
    memory_cleanups: int = 0
    config_reloads: int = 0
    emergency_stops: int = 0 # Now covered by circuit_breaker_activations
    successful_rebalances: int = 0
    
    profit_history: deque = field(default_factory=lambda: deque(maxlen=50)) # Stores (timestamp, PnL) for adaptive strategy
    
    def update_pnl(self, current_pnl: Decimal):
        """Update PnL and track peak/drawdown"""
        self.total_pnl = current_pnl
        
        # Initialize peak_balance or update if new PnL is higher
        if self.peak_balance == Decimal("0") and current_pnl != Decimal("0"):
            self.peak_balance = current_pnl
        elif current_pnl > self.peak_balance:
            self.peak_balance = current_pnl
        
        # Calculate drawdown relative to peak PnL (only if peak is positive)
        if self.peak_balance > 0: 
            drawdown = (self.peak_balance - current_pnl) / self.peak_balance
            if drawdown > self.max_drawdown:
                self.max_drawdown = drawdown
        
        # Record PnL for adaptive strategy (time, PnL value)
        self.profit_history.append((time.time(), current_pnl))
        
        # Update bot health component for PnL
        # Score is 1.0 if PnL is good, degrading to 0.0 if PnL is negative and reaches CB_PNL_STOP_LOSS_PCT
        pnl_score = 1.0 # Default to perfect
        if config.CB_PNL_STOP_LOSS_PCT > 0 and current_pnl < 0 and market_state.available_balance > 0:
            current_pnl_pct = abs(current_pnl) / market_state.available_balance
            pnl_score = max(Decimal("0.0"), Decimal("1.0") - (current_pnl_pct / config.CB_PNL_STOP_LOSS_PCT))
        
        bot_health.update_component('strategy_pnl', float(pnl_score), f"PnL: {current_pnl:.2f}, Drawdown: {self.max_drawdown:.2%}")

    def record_api_error(self, error_code: str):
        """Record API error with categorization"""
        self.api_errors[error_code] += 1
    
    def get_success_rate(self) -> float:
        """Calculate overall success rate of orders attempted vs. filled"""
        total_orders_attempted = self.orders_placed + self.orders_rejected
        if total_orders_attempted > 0:
            # orders_filled / (orders_filled + orders_cancelled + orders_rejected) is more accurate
            return (self.orders_filled / total_orders_attempted) * 100
        return 0.0
    
    def get_uptime_formatted(self) -> str:
        """Get formatted uptime string"""
        uptime = time.time() - self.start_time
        hours, remainder = divmod(uptime, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours):02d}h {int(minutes):02d}m {int(seconds):02d}s"

# Global instances (initialized here as per the v4.0 structure, will be passed to main)
config_manager = ConfigManager()
config = config_manager.config # Global config object, will be updated by config_manager

symbol_info = SymbolInfo()
market_state = MarketState()
session_stats = SessionStats()
system_monitor = SystemMonitor()
rate_limiter = AdaptiveRateLimiter(config) # Uses the global config object

# Initialize Sentry if available
if sentry_sdk and SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=1.0,
        release="mmxcel@5.2.0" # Updated version
    )

# Contextual Logging
class ContextualLogger(logging.LoggerAdapter):
    """A logging adapter that adds contextual information to log records."""
    def process(self, msg, kwargs):
        # Merge adapter's extra with message's extra
        extra_data = {**self.extra, **kwargs.get('extra', {})}
        
        # If LOG_AS_JSON is enabled, store extra_data directly for JSON formatter
        if LOG_AS_JSON:
            kwargs['extra'] = {'json': extra_data}
            return msg, kwargs
        
        # Otherwise, format extra data into message string for plain text logs
        if extra_data:
            extra_str = ", ".join([f"{k}={v}" for k, v in extra_data.items()])
            msg = f"{msg} {NEON_PINK}[{extra_str}]{NC}"
        
        kwargs.pop('extra', None) # Remove 'extra' to prevent default formatter issues
        return msg, kwargs

class CustomFormatter(logging.Formatter):
    """Custom formatter for colored console output and file logging."""
    def format(self, record: logging.LogRecord) -> str:
        # Check if json data is explicitly passed
        if hasattr(record, 'json') and LOG_AS_JSON:
            return json.dumps({
                "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
                "level": record.levelname,
                "message": record.getMessage(),
                **record.json # Include the structured JSON data
            }, default=str) # Convert Decimal to string, etc.

        # Fallback to standard color/text formatting
        log_message = super().format(record)
        
        # Apply neon colors if enabled and not JSON logging
        if config.NEON_COLORS_ENABLED and not LOG_AS_JSON:
            if record.levelname == 'INFO':
                log_message = f"{NEON_GREEN}{log_message}{NC}"
            elif record.levelname == 'WARNING':
                log_message = f"{YELLOW}{log_message}{NC}"
            elif record.levelname == 'ERROR':
                log_message = f"{RED}{log_message}{NC}"
            elif record.levelname == 'CRITICAL':
                log_message = f"{RED}{BOLD}{log_message}{NC}"
            elif record.levelname == 'DEBUG':
                log_message = f"{NEON_CYAN}{log_message}{NC}"
        return log_message

class EnhancedLogger:
    """Enhanced logging with neon colors, structured format, and trade journaling."""
    def __init__(self, name: str):
        self._logger = logging.getLogger(name)
        self.logger = ContextualLogger(self._logger, {})
        self.setup_logging()
    
    def setup_logging(self):
        """Setup enhanced logging configuration."""
        # Clear existing handlers to prevent duplicates on reload if setup is called again
        if self._logger.handlers:
            for handler in self._logger.handlers[:]: # Iterate on a copy
                self._logger.removeHandler(handler)
                handler.close()

        formatter_str = f"%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s"
        date_format = "%Y-%m-%d %H:%M:%S"
        formatter = CustomFormatter(formatter_str, datefmt=date_format)
        
        # File handler with rotation for general logs
        file_handler = logging.handlers.RotatingFileHandler(
            "mmxcel_enhanced.log", 
            maxBytes=config.MAX_LOG_FILE_SIZE, 
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        
        # Trade Journaling handler (JSONL format)
        self.trade_journal_handler = logging.handlers.RotatingFileHandler(
            "mmxcel_trades.jsonl",
            maxBytes=config.TRADE_JOURNAL_FILE_SIZE,
            backupCount=3
        )
        # For JSONL, the formatter should just output the JSON string (handled by custom formatter)
        self.trade_journal_formatter = CustomFormatter(formatter_str, datefmt=date_format)
        self.trade_journal_handler.setFormatter(self.trade_journal_formatter)
        
        # Configure logger
        self._logger.setLevel(logging.INFO) # Default level for main log
        self._logger.addHandler(file_handler)
        self._logger.addHandler(console_handler)
        
        # Filter trade journal messages from main logs
        class TradeFilter(logging.Filter):
            def filter(self, record):
                return not hasattr(record, 'is_trade_journal_entry') or not record.is_trade_journal_entry
        
        file_handler.addFilter(TradeFilter())
        console_handler.addFilter(TradeFilter())

        # Ensure trade journal handler only processes specific trade messages
        self.trade_journal_handler.addFilter(lambda record: hasattr(record, 'is_trade_journal_entry') and record.is_trade_journal_entry)
        self._logger.addHandler(self.trade_journal_handler)

    def set_context(self, **kwargs):
        """Set logging context for the adapter"""
        self.logger.extra = kwargs
    
    def info(self, message: str, **kwargs):
        self.logger.info(message, extra=kwargs)
    
    def warning(self, message: str, **kwargs):
        self.logger.warning(message, extra=kwargs)
    
    def error(self, message: str, **kwargs):
        self.logger.error(message, extra=kwargs)
    
    def debug(self, message: str, **kwargs):
        self.logger.debug(message, extra=kwargs)

    def critical(self, message: str, **kwargs):
        self.logger.critical(message, extra=kwargs)

    def journal_trade(self, trade_data: Dict):
        """Writes a structured trade entry to the trade journal file."""
        # Convert Decimal objects to string for JSON serialization
        def convert_decimal(obj):
            if isinstance(obj, Decimal):
                return str(obj)
            raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

        try:
            # Create a LogRecord marked for the trade journal
            record = self._logger.makeRecord(
                "trade_journal", logging.INFO, __file__, sys._getframe(1).f_lineno,
                "", [], None, None, # msg, args, exc_info, func, sinfo
                extra={'json': trade_data} # Pass structured data via 'json' key
            )
            record.is_trade_journal_entry = True # Custom attribute to identify trade records
            self.trade_journal_handler.emit(record)
        except Exception as e:
            self.error(f"Failed to journal trade: {e}", trade_data=trade_data)

log = EnhancedLogger("MMXCEL")

# Initialize Sentry if available (moved to after logger setup to ensure logging works)
if sentry_sdk and SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=1.0,
        release="mmxcel@5.2.0"
    )

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
        
        if duration > 5.0: # Threshold for a "slow" API call
            self.slow_operations.append({
                'operation': operation,
                'duration': duration,
                'timestamp': time.time()
            })
            self.performance_alerts += 1
            log.warning(f"Slow API call detected: {operation}", duration=f"{duration:.3f}s")
        
        rate_limiter.record_success(duration < 10.0) # Assume success if not excessively slow
    
    def record_order_latency(self, duration: float):
        """Record order latency (time from request to exchange confirmation)"""
        self.order_latencies.append(duration)
        
        if duration > 3.0: # Threshold for high order latency
            log.warning(f"High order latency detected", latency=f"{duration:.3f}s")
    
    def record_websocket_latency(self, duration: float):
        """Record WebSocket message processing latency"""
        self.websocket_latencies.append(duration)
    
    def record_error(self, error_type: str):
        """Record error with categorization"""
        self.error_counts[error_type] += 1
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary"""
        return {
            'avg_api_time': sum(self.api_call_times) / len(self.api_call_times) if self.api_call_times else 0,
            'max_api_time': max(self.api_call_times) if self.api_call_times else 0,
            'avg_order_latency': sum(self.order_latencies) / len(self.order_latencies) if self.order_latencies else 0,
            'avg_ws_latency': sum(self.websocket_latencies) / len(self.websocket_latencies) if self.websocket_latencies else 0,
            'total_operations': sum(self.operation_counts.values()),
            'total_errors': sum(self.error_counts.values()),
            'slow_operations_count': len(self.slow_operations),
            'performance_alerts': self.performance_alerts,
            'operation_breakdown': dict(self.operation_counts),
            'error_breakdown': dict(self.error_counts)
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
        self.plugins: Dict[str, Any] = {}
        self.callbacks: List[Callable[[Any], None]] = [] # Callbacks that receive the strategy instance
    
    def load_plugins(self, folder: str):
        if not (config.ENABLE_PLUGINS and os.path.isdir(folder)):
            log.info("Plugin system disabled or folder not found.")
            return
            
        sys.path.insert(0, folder) # Add plugin folder to Python path
        
        for file in os.listdir(folder):
            if file.endswith(".py") and not file.startswith("_"):
                module_name = file[:-3]
                try:
                    # Dynamically import the module
                    spec = importlib.util.spec_from_file_location(module_name, os.path.join(folder, file))
                    if spec is None:
                        raise ImportError(f"Could not load spec for {module_name}")
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                    
                    if hasattr(module, "register") and callable(module.register):
                        callback = module.register()
                        if callable(callback):
                            self.plugins[module_name] = module # Store module reference
                            self.callbacks.append(callback)
                            log.info(f"Plugin '{module_name}' loaded successfully.")
                        else:
                            log.warning(f"Plugin '{module_name}' register() did not return a callable.")
                    else:
                        log.debug(f"Plugin '{module_name}' has no 'register' function.")
                except Exception as e:
                    log.error(f"Failed to load plugin '{module_name}': {e}", exc_info=True)
        
        # If a specific strategy plugin is configured, ensure it exists
        if config.STRATEGY_PLUGIN_NAME and config.STRATEGY_PLUGIN_NAME not in self.plugins:
            log.critical(f"Configured strategy plugin '{config.STRATEGY_PLUGIN_NAME}' not found or failed to load. Please check plugin folder and config.")
            global _SHUTDOWN_REQUESTED # Explicitly declare global to modify
            _SHUTDOWN_REQUESTED = True # Force shutdown if main strategy plugin is missing

plugin_manager = PluginManager()
import importlib.util # Import here to avoid circular dependencies with early logging setup

# Enhanced WebSocket Callbacks
def on_public_ws_message(msg: Union[Dict[str, Any], str]) -> None:
    """Handle public WebSocket messages with enhanced processing"""
    # Removed pprint for production use, but keeping the raw message print for debugging.
    # print(f"--- RAW PUBLIC WS MESSAGE ---")
    # import pprint
    # pprint.pprint(msg)
    # print(f"--- END RAW PUBLIC WS MESSAGE ---")
    
    message_start_time = time.time()
    
    if not isinstance(msg, dict):
        # This handles non-dict messages like "pong" or simple status strings
        log.debug(f"Received non-dict public WS message: {msg}")
        return

    try:
        topic = msg.get("topic", "")
        # Handle ping/pong responses
        if msg.get("op") == "ping" or msg.get("ret_msg") == "pong":
            log.debug(f"Received WS heartbeat/pong: {msg.get('ret_msg')}")
            # Public WS connection is implicitly alive, nothing more to do than log
            market_state.last_heartbeat = time.time()
            return
            
        if "orderbook" in topic:
            data = msg.get("data")
            if data and data.get("b") and data.get("a"):
                bids = data.get("b", [])
                asks = data.get("a", [])
                
                if bids and asks and len(bids) > 0 and len(asks) > 0:
                    market_state.best_bid = Decimal(str(bids[0][0]))
                    market_state.best_ask = Decimal(str(asks[0][0]))
                    
                    if market_state.best_bid > 0 and market_state.best_ask > 0:
                        market_state.mid_price = (market_state.best_bid + market_state.best_ask) / Decimal("2")
                        
                        symbol_info.update_orderbook_depth(bids, asks)
                        market_state.update_price_history()
                    else:
                        market_state.mid_price = Decimal("0") # Invalid prices
                    
                    market_state.last_update_time = time.time()
                    market_state.last_heartbeat = time.time() # This is the primary heartbeat for market data
                    
                    latency = time.time() - message_start_time
                    performance_monitor.record_websocket_latency(latency)
                    
                    # Update health component for WS latency
                    latency_score = max(0.0, 1.0 - (latency / 0.5)) # 0.5s latency means 0 score for this component
                    bot_health.update_component('ws_public_latency', float(latency_score), f"Public WS Latency: {latency:.3f}s")
                else:
                    log.warning("Public WS message received with empty bids/asks, skipping update.", msg_payload=msg)
                    bot_health.update_component('ws_public_data_quality', 0.5, "Public WS Data Incomplete") # Partial score
                
    except (KeyError, IndexError, ValueError, TypeError, DecimalException) as e:
        log.error(f"Error processing public WS message: {e}", msg_payload=msg)
        performance_monitor.record_error("websocket_public_error")
        bot_health.update_component('ws_public_data_quality', 0.0, f"Public WS Data Error: {e}")
    except Exception as e:
        log.critical(f"Critical error in public WS handler: {e}", exc_info=True)
        performance_monitor.record_error("websocket_public_critical")
        bot_health.update_component('ws_public_data_quality', 0.0, f"Public WS Critical Error: {e}")
        if sentry_sdk: sentry_sdk.capture_exception(e)

def on_private_ws_message(msg: Dict[str, Any]) -> None:
    """Handle private WebSocket messages with enhanced processing"""
    message_start_time = time.time()
    
    try:
        topic = msg.get("topic")
        
        if topic == "order":
            for order_data in msg["data"]:
                order_id = order_data.get("orderId")
                if not order_id:
                    continue
                
                order_status = order_data.get("orderStatus")
                
                if order_status == "Filled":
                    order_details = market_state.open_orders.pop(order_id, None)
                    if order_details:
                        session_stats.orders_filled += 1
                        
                        expected_price = order_details.get('price', Decimal('0'))
                        actual_price = Decimal(str(order_data.get('avgPrice', order_data.get('price', '0')))) # avgPrice preferred
                        filled_qty = Decimal(str(order_data.get('qty', '0')))
                        side = order_data.get('side', 'N/A')
                        
                        slippage = Decimal('0')
                        if expected_price > 0 and actual_price > 0:
                            if side == 'Buy':
                                slippage = (actual_price - expected_price) / expected_price
                            else: # Sell
                                slippage = (expected_price - actual_price) / expected_price
                            
                            if abs(slippage) > config.MAX_SLIPPAGE_PERCENTAGE:
                                session_stats.slippage_events += 1
                                log.warning(f"High slippage detected: {side} order", 
                                             order_id=order_id,
                                             expected=float(expected_price),
                                             actual=float(actual_price),
                                             slippage=f"{float(slippage):.4f}")
                        
                        trade_data = {
                            'timestamp': time.time(),
                            'order_id': order_id,
                            'client_order_id': order_details.get("client_order_id", "N/A"),
                            'symbol': config.SYMBOL,
                            'side': side,
                            'price': actual_price,
                            'quantity': filled_qty,
                            'slippage_pct': slippage,
                            'latency_ms': (time.time() - order_details.get("timestamp", message_start_time)) * 1000,
                            'type': 'Filled'
                        }
                        market_state.add_trade(trade_data)
                        log.journal_trade(trade_data)
                        
                        session_stats.total_volume_traded += filled_qty
                        
                        log.info(f"Order filled successfully", 
                                  order_id=order_id,
                                  side=side, 
                                  quantity=float(filled_qty),
                                  price=float(actual_price),
                                  slippage=f"{float(slippage):.4f}")
                        send_toast(f"✅ {side} {filled_qty} @ {actual_price:.{calculate_decimal_precision(actual_price)}f}", "green", "white")
                
                elif order_status in ("Canceled", "Deactivated"):
                    if order_id in market_state.open_orders:
                        market_state.open_orders.pop(order_id, None)
                        session_stats.orders_cancelled += 1
                        log.info(f"Order cancelled by exchange or deactivated", order_id=order_id, status=order_status)
                
                elif order_status == "Rejected":
                    if order_id in market_state.open_orders:
                        market_state.open_orders.pop(order_id, None)
                    session_stats.orders_rejected += 1
                    log.warning(f"Order rejected", order_id=order_id, reject_reason=order_data.get('rejectReason'))
                    send_toast("❌ Order rejected", "red", "white")
                
                else: # New, PartiallyFilled, PendingNew, etc.
                    if order_status in ["New", "PartiallyFilled", "PendingNew"]:
                        # Ensure we get the latest info for existing orders
                        current_order_entry = market_state.open_orders.get(order_id, {})
                        market_state.open_orders[order_id] = {
                            "client_order_id": order_data.get("orderLinkId", current_order_entry.get("client_order_id", "N/A")),
                            "symbol": order_data.get("symbol", current_order_entry.get("symbol")),
                            "side": order_data.get("side", current_order_entry.get("side")),
                            "price": Decimal(str(order_data.get("price", current_order_entry.get("price", "0")))),
                            "qty": Decimal(str(order_data.get("qty", current_order_entry.get("qty", "0")))),
                            "status": order_status,
                            "timestamp": float(order_data.get("createdTime", current_order_entry.get("timestamp", 0))) / 1000,
                        }
                        log.debug(f"Order status update", order_id=order_id, status=order_status)

        elif topic == "position":
            for pos_data in msg["data"]:
                if pos_data.get("symbol") == config.SYMBOL:
                    # Bybit sends updates for all position sides (long/short/both)
                    side = "Long" if pos_data.get("side") == "Buy" else "Short"
                    current_size = Decimal(str(pos_data.get("size", "0")))
                    
                    if current_size == Decimal("0"): # Position closed
                        market_state.positions.pop(side, None)
                        log.info(f"{side} position closed", position_size=float(current_size))
                    else:
                        unrealised_pnl = Decimal(str(pos_data.get("unrealisedPnl", "0")))
                        market_state.positions[side] = {
                            "size": current_size,
                            "avg_price": Decimal(str(pos_data.get("avgPrice", "0"))),
                            "unrealisedPnl": unrealised_pnl,
                            "leverage": Decimal(str(pos_data.get("leverage", "1"))),
                            "liq_price": Decimal(str(pos_data.get("liqPrice", "0"))),
                        }
                        log.debug(f"{side} position updated", size=float(current_size), pnl=float(unrealised_pnl))
            
            # Calculate total PnL AFTER updating all positions for the symbol
            total_pnl = sum(pos.get("unrealisedPnl", Decimal("0")) 
                          for pos in market_state.positions.values())
            session_stats.update_pnl(total_pnl)
            
        elif topic == "wallet":
            for wallet_data in msg["data"]:
                if wallet_data.get("coin") == 'USDT':
                    market_state.available_balance = Decimal(str(wallet_data.get('availableToWithdraw', '0')))
                    market_state.last_balance_update = time.time()
                    log.debug(f"Wallet balance updated via HTTP", balance=float(market_state.available_balance))
        
        processing_time = time.time() - message_start_time
        # Update health component for WS latency
        latency_score = max(0.0, 1.0 - (processing_time / 0.5))
        bot_health.update_component('ws_private_latency', float(latency_score), f"Private WS Latency: {processing_time:.3f}s")
                    
    except (KeyError, ValueError, TypeError, DecimalException) as e:
        log.error(f"Error processing private WS message: {e}", msg_payload=msg)
        performance_monitor.record_error("websocket_private_error")
        bot_health.update_component('ws_private_data_quality', 0.0, f"Private WS Data Error: {e}")
        if sentry_sdk: sentry_sdk.capture_exception(e)
    except Exception as e:
        log.critical(f"Critical error in private WS handler: {e}", exc_info=True)
        performance_monitor.record_error("websocket_private_critical")
        bot_health.update_component('ws_private_data_quality', 0.0, f"Private WS Critical Error: {e}")
        if sentry_sdk: sentry_sdk.capture_exception(e)


# Enhanced Bybit Client with better connection management and robust API calls
class EnhancedBybitClient:
    """Enhanced Bybit client with advanced connection management and retry logic."""
    
    def __init__(self, key: str, secret: str, testnet: bool):
        self.key = key
        self.secret = secret
        self.testnet = testnet
        self.http = HTTP(testnet=testnet, api_key=key, api_secret=secret, recv_window=10000)
        self.public_ws: Optional[WebSocket] = None
        self.private_ws: Optional[WebSocket] = None
        self._public_connected = asyncio.Event()
        self._private_connected = asyncio.Event()
        self.connection_attempts = defaultdict(int)
        self.reconnect_delays = [1, 2, 4, 8, 15, 30, 60] # Max 60s delay
        self._reconnect_tasks = {} # To keep track of reconnect tasks for proper cancellation

    async def reconnect_ws(self, ws_type: str):
        """Handles the reconnection logic for a given websocket type."""
        # Check shutdown flag immediately upon entering reconnect logic
        if _SHUTDOWN_REQUESTED:
            log.info(f"Shutdown requested, not attempting to reconnect {ws_type} WS.")
            self._reconnect_tasks.pop(ws_type, None) # Clean up task reference
            return
            
        attempt = self.connection_attempts[ws_type]
        delay = self.reconnect_delays[min(attempt, len(self.reconnect_delays) - 1)]
        log.info(f"Attempting to reconnect {ws_type} WS in {delay}s", attempt=attempt + 1)
        
        await asyncio.sleep(delay)

        # Re-check shutdown flag after sleep
        if _SHUTDOWN_REQUESTED:
            log.info(f"Shutdown requested after reconnect delay, not reconnecting {ws_type} WS.")
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
            
            log.info(f"🟢 {ws_type.capitalize()} WebSocket connected.")
            self.connection_attempts[ws_type] = 0 # Reset attempts on success
            bot_health.update_component(f'ws_{ws_type}_connection', 1.0, f"{ws_type.capitalize()} WS Connected")
            market_state.last_heartbeat = time.time() # Update last message received time

        def _on_ws_close(ws_type: str):
            if ws_type == "public": self._public_connected.clear()
            elif ws_type == "private": self._private_connected.clear()
            
            log.warning(f"🔴 {ws_type.capitalize()} WebSocket disconnected.")
            session_stats.connection_drops += 1
            bot_health.update_component(f'ws_{ws_type}_connection', 0.0, f"{ws_type.capitalize()} WS Disconnected")
            
            if not _SHUTDOWN_REQUESTED:
                # Ensure only one reconnect task per WS type is active
                if ws_type not in self._reconnect_tasks:
                    reconnect_task = asyncio.create_task(self.reconnect_ws(ws_type))
                    self._reconnect_tasks[ws_type] = reconnect_task
                else:
                    log.debug(f"Reconnect task for {ws_type} already running.")

        def _on_ws_error(ws_type: str, error: Exception):
            log.error(f"🔥 {ws_type.capitalize()} WebSocket error: {error}", error_msg=str(error))
            bot_health.update_component(f'ws_{ws_type}_connection', 0.0, f"{ws_type.capitalize()} WS Error: {error}")
            performance_monitor.record_error(f"websocket_{ws_type}_error")
            if sentry_sdk: sentry_sdk.capture_exception(error)
            if ws_type == "public": self._public_connected.clear()
            elif ws_type == "private": self._private_connected.clear()
            
            # Trigger reconnect on error, similar to close
            if not _SHUTDOWN_REQUESTED:
                if ws_type not in self._reconnect_tasks:
                    reconnect_task = asyncio.create_task(self.reconnect_ws(ws_type))
                    self._reconnect_tasks[ws_type] = reconnect_task


        # Initialize WebSocket instances if not already
        if not self.public_ws:
            self.public_ws = WebSocket(
                testnet=self.testnet, 
                channel_type="linear"
            )
            # Assign generic callbacks for Pybit's internal handling
            self.public_ws._on_open = lambda: _on_ws_open("public")
            self.public_ws._on_close = lambda: _on_ws_close("public")
            self.public_ws._on_error = lambda err: _on_ws_error("public", err)
            # The _on_message handles all raw messages, it must dispatch to topic specific handlers
            self.public_ws._on_message = on_public_ws_message

        if not self.private_ws:
            self.private_ws = WebSocket(
                testnet=self.testnet, 
                channel_type="private", 
                api_key=self.key, 
                api_secret=self.secret
            )
            self.private_ws._on_open = lambda: _on_ws_open("private")
            self.private_ws._on_close = lambda: _on_ws_close("private")
            self.private_ws._on_error = lambda err: _on_ws_error("private", err)
            # For private, the `order_stream`, `position_stream`, `wallet_stream` already take callbacks.
            # So, `_on_message` for private WS is handled implicitly by the stream methods themselves.
            # We explicitly pass the callback to `_on_message` for private WS connections.
            # This line ensures the raw message is processed if the stream-specific callbacks don't catch it.
            self.private_ws._on_message = on_private_ws_message 

        # Initial subscription calls to start the connection
        # These methods internally start the WS connection if not already started.
        await self._subscribe_public_topics()
        await self._subscribe_private_topics()
        
    async def _subscribe_public_topics(self):
        """Subscribes to public WebSocket topics."""
        if self.public_ws:
            try:
                # FIX: Pass the callback to orderbook_stream as required by pybit
                self.public_ws.orderbook_stream(
                    symbol=config.SYMBOL, 
                    depth=config.ORDERBOOK_DEPTH_LEVELS,
                    callback=on_public_ws_message # THIS WAS THE CRITICAL MISSING PIECE
                )
                log.info(f"Subscribed to public orderbook for {config.SYMBOL}", symbol=config.SYMBOL)
            except Exception as e:
                log.error(f"Failed to subscribe to public topics: {e}")
                if sentry_sdk: sentry_sdk.capture_exception(e)
                
    async def _subscribe_private_topics(self):
        """Subscribes to private WebSocket topics."""
        if self.private_ws:
            try:
                # These already register internal handlers, but ensure they don't block
                # They are designed to manage their own message handling.
                self.private_ws.order_stream(callback=on_private_ws_message)
                self.private_ws.position_stream(callback=on_private_ws_message)
                self.private_ws.wallet_stream(callback=on_private_ws_message)
                log.info(f"Subscribed to private streams")
            except Exception as e:
                log.error(f"Failed to subscribe to private topics: {e}")
                if sentry_sdk: sentry_sdk.capture_exception(e)

    @asynccontextmanager
    async def api_call_context(self, method_name: str):
        """Enhanced API call context manager for rate limiting and performance monitoring"""
        start_time = time.time()
        try:
            await rate_limiter.acquire() # Acquire token from rate limiter
            yield
        finally:
            duration = time.time() - start_time
            performance_monitor.record_api_call(duration, method_name)
    
    async def api_call_with_retry(self, api_method: Callable, *args, **kwargs) -> Optional[Dict]:
        """Enhanced API call with robust retry logic and error handling."""
        method_name = getattr(api_method, '__name__', str(api_method))
        
        async with self.api_call_context(method_name):
            for attempt in range(1, 6): # Max 5 attempts
                try:
                    response = api_method(*args, **kwargs)
                    
                    if response and response.get("retCode") == 0:
                        rate_limiter.record_success(True)
                        bot_health.update_component(f'api_status_{method_name}', 1.0, "API Call OK")
                        return response
                    
                    ret_code = response.get('retCode') if response else None
                    ret_msg = response.get('retMsg', 'Unknown error') if response else 'No response'
                    
                    session_stats.record_api_error(str(ret_code))
                    rate_limiter.record_success(False)
                    
                    log.warning(f"API call failed: {method_name}", 
                                 attempt=attempt,
                                 error_code=ret_code,
                                 error_msg=ret_msg)
                    
                    # Update health component specifically for this API method
                    bot_health.update_component(f'api_status_{method_name}', 0.5, f"API Error {ret_code}: {ret_msg}")
                    
                    # Retryable errors (e.g., rate limit, system error, service unavailable)
                    if ret_code in [10001, 10006, 30034, 30035, 10018, 10005]:
                        if attempt < 5:
                            delay = min(30, 2 * (2 ** (attempt - 1))) # Exponential backoff, max 30s
                            log.debug(f"Retrying API call {method_name} in {delay}s...")
                            await asyncio.sleep(delay)
                            continue
                    # Non-retryable errors (e.g., invalid signature, param error)
                    elif ret_code in [10007, 10002]:
                        log.error(f"Non-retryable API error: {ret_msg}", error_code=ret_code)
                        bot_health.update_component(f'api_status_{method_name}', 0.0, f"Non-retryable API Error: {ret_msg}")
                        if sentry_sdk: sentry_sdk.capture_message(f"Non-retryable API error {ret_code}: {ret_msg}")
                        return None
                    else: # Unhandled errors
                        log.error(f"Unhandled API error {ret_code}: {ret_msg}", error_code=ret_code)
                        bot_health.update_component(f'api_status_{method_name}', 0.0, f"Unhandled API Error: {ret_msg}")
                        if sentry_sdk: sentry_sdk.capture_message(f"Unhandled API error {ret_code}: {ret_msg}")
                        return None
                
                except Exception as e:
                    log.error(f"API call exception: {method_name}", attempt=attempt, error=str(e), exc_info=True)
                    performance_monitor.record_error(f"api_exception_{method_name}")
                    rate_limiter.record_success(False)
                    bot_health.update_component(f'api_status_{method_name}', 0.0, f"API Exception: {e}")
                    if sentry_sdk: sentry_sdk.capture_exception(e)
                    
                    if attempt < 5:
                        delay = min(30, 2 * (2 ** (attempt - 1)))
                        log.debug(f"Retrying API call {method_name} in {delay}s due to exception...")
                        await asyncio.sleep(delay)
                    else:
                        log.critical(f"API call failed after all retries: {method_name} - {e}")
                        return None
            
            return None # All retries exhausted

    async def monitor_heartbeats(self):
        """Sends internal heartbeat and updates connection health."""
        last_heartbeat_sent = time.time()
        while not _SHUTDOWN_REQUESTED:
            try:
                current_time = time.time()
                if current_time - last_heartbeat_sent > config.HEARTBEAT_INTERVAL:
                    last_heartbeat_sent = current_time
                    log.debug(f"💓 Internal heartbeat signal")
                
                # Aggregate WS connection health
                public_ws_ok = self._public_connected.is_set()
                private_ws_ok = self._private_connected.is_set()
                overall_ws_score = 1.0 if public_ws_ok and private_ws_ok else 0.0
                
                bot_health.update_component('ws_overall_connection', float(overall_ws_score), 
                                            f"Public: {'OK' if public_ws_ok else 'DISC'}, Private: {'OK' if private_ws_ok else 'DISC'}")
                
                # Check for data freshness using market_state's method
                market_state.is_data_fresh(config.CB_STALE_DATA_TIMEOUT_SEC) # This updates health component internally
                
                await asyncio.sleep(config.HEARTBEAT_INTERVAL / 2) # Check more frequently than full interval
            except Exception as e:
                log.error(f"Error in connection monitoring: {e}", exc_info=True)
                if sentry_sdk: sentry_sdk.capture_exception(e)
                await asyncio.sleep(5)

    async def get_symbol_info(self) -> bool:
        """Fetches and updates symbol information."""
        response = await self.api_call_with_retry(
            self.http.get_instruments_info,
            category=config.CATEGORY,
            symbol=config.SYMBOL
        )
        
        if response and response.get('retCode') == 0:
            instruments = response.get('result', {}).get('list')
            if instruments:
                instrument = instruments[0]
                price_filter = instrument.get('priceFilter', {})
                lot_size_filter = instrument.get('lotSizeFilter', {})
                
                symbol_info.price_precision = Decimal(str(price_filter.get('tickSize', "0.0001")))
                symbol_info.qty_precision = Decimal(str(lot_size_filter.get('qtyStep', "0.001")))
                symbol_info.min_price = Decimal(str(price_filter.get('minPrice', "0")))
                symbol_info.min_qty = Decimal(str(lot_size_filter.get('minQty', "0")))
                symbol_info.max_qty = Decimal(str(lot_size_filter.get('maxOrderQty', "1000000")))
                symbol_info.min_order_value = Decimal(str(lot_size_filter.get('minOrderAmt', "10.0")))
                
                log.info(f"📊 Symbol info loaded successfully", symbol=config.SYMBOL)
                bot_health.update_component('symbol_info_load', 1.0, "Symbol info loaded")
                return True
        
        log.error(f"❌ Failed to fetch symbol info", symbol=config.SYMBOL)
        bot_health.update_component('symbol_info_load', 0.0, "Failed to load symbol info")
        return False
    
    async def test_credentials(self) -> bool:
        """Tests API credentials by attempting to get wallet balance."""
        response = await self.api_call_with_retry(
            self.http.get_wallet_balance, 
            accountType="UNIFIED" # Use UNIFIED for Unified Trading Account
        )
        
        if response and response.get("retCode") == 0:
            log.info(f"✅ API credentials validated successfully")
            bot_health.update_component('api_credentials', 1.0, "Credentials OK")
            return True
        
        log.critical(f"❌ API credentials validation failed. Check API key/secret and permissions.")
        bot_health.update_component('api_credentials', 0.0, "Credentials FAILED")
        if sentry_sdk: sentry_sdk.capture_message("API credentials validation failed.")
        return False
    
    async def get_wallet_balance(self) -> bool:
        """Fetches and updates wallet balance."""
        response = await self.api_call_with_retry(
            self.http.get_wallet_balance,
            accountType="UNIFIED"
        )
        
        if response and response.get('retCode') == 0:
            balance_list = response.get('result', {}).get('list', [])
            for balance in balance_list:
                for coin in balance.get('coin', []):
                    if coin.get('coin') == 'USDT':
                        market_state.available_balance = Decimal(str(coin.get('availableToWithdraw', '0')))
                        market_state.last_balance_update = time.time()
                        log.debug(f"Wallet balance updated via HTTP", balance=float(market_state.available_balance))
                        return True
        log.warning(f"Failed to fetch wallet balance via HTTP")
        return False
    
    async def get_open_orders(self) -> bool:
        """Fetches and updates current open orders."""
        response = await self.api_call_with_retry(
            self.http.get_open_orders,
            category=config.CATEGORY,
            symbol=config.SYMBOL
        )
        
        if response and response.get('retCode') == 0:
            orders = response.get('result', {}).get('list', [])
            market_state.open_orders.clear() # Clear existing before populating
            
            for order in orders:
                order_id = order.get('orderId')
                if order_id:
                    market_state.open_orders[order_id] = {
                        "client_order_id": order.get("orderLinkId", "N/A"),
                        "symbol": order.get("symbol"),
                        "side": order.get("side"),
                        "price": Decimal(str(order.get("price", "0"))),
                        "qty": Decimal(str(order.get("qty", "0"))),
                        "status": order.get("orderStatus"),
                        "timestamp": float(order.get("createdTime", 0)) / 1000,
                    }
            log.debug(f"Fetched {len(market_state.open_orders)} open orders via HTTP")
            return True
        log.warning(f"Failed to fetch open orders via HTTP")
        return False
    
    async def get_positions(self) -> bool:
        """Fetches and updates current positions."""
        response = await self.api_call_with_retry(
            self.http.get_positions,
            category=config.CATEGORY,
            symbol=config.SYMBOL
        )
        
        if response and response.get('retCode') == 0:
            positions = response.get('result', {}).get('list', [])
            market_state.positions.clear() # Clear existing before populating
            
            for pos in positions:
                if pos.get("symbol") == config.SYMBOL and Decimal(str(pos.get("size", "0"))) > 0:
                    side = "Long" if pos.get("side") == "Buy" else "Short"
                    market_state.positions[side] = {
                        "size": Decimal(str(pos.get("size", "0"))),
                        "avg_price": Decimal(str(pos.get("avgPrice", "0"))),
                        "unrealisedPnl": Decimal(str(pos.get("unrealisedPnl", "0"))),
                        "leverage": Decimal(str(pos.get("leverage", "1"))),
                        "liq_price": Decimal(str(pos.get("liqPrice", "0"))),
                    }
            log.debug(f"Fetched {len(market_state.positions)} positions via HTTP")
            # Recalculate PnL after position sync
            total_pnl = sum(pos.get("unrealisedPnl", Decimal("0")) 
                            for pos in market_state.positions.values())
            session_stats.update_pnl(total_pnl)
            return True
        log.warning(f"Failed to fetch positions via HTTP")
        return False
    
    async def place_order(self, side: str, order_type: str, qty: Decimal, price: Optional[Decimal] = None) -> Optional[Dict]:
        """Places an order with comprehensive validation and monitoring."""
        start_time = time.time()
        
        try:
            quantized_qty = qty.quantize(symbol_info.qty_precision, rounding=ROUND_DOWN)
            if quantized_qty <= 0 or quantized_qty < symbol_info.min_qty:
                log.warning(f"Invalid quantity rejected", 
                             original_qty=float(qty), 
                             quantized_qty=float(quantized_qty),
                             min_qty=float(symbol_info.min_qty))
                return None
            
            if quantized_qty > symbol_info.max_qty:
                log.warning(f"Quantity exceeds maximum allowed by exchange", 
                             quantity=float(quantized_qty),
                             max_qty=float(symbol_info.max_qty))
                return None
            
            order_params = {
                "category": config.CATEGORY,
                "symbol": config.SYMBOL,
                "side": side,
                "orderType": order_type,
                "qty": str(quantized_qty),
                "orderLinkId": f"mmxcel-{uuid.uuid4()}", # Unique client order ID
                "timeInForce": "GTC" if order_type == "Limit" else "IOC", # IOC for market orders is standard
            }
            
            if order_type == "Limit":
                if price is None:
                    log.error("Limit order requires a price.")
                    return None
                rounding = ROUND_DOWN if side == "Buy" else ROUND_UP
                quantized_price = price.quantize(symbol_info.price_precision, rounding=rounding)
                
                if quantized_price <= 0 or quantized_price < symbol_info.min_price:
                    log.warning(f"Price below minimum allowed by exchange rejected", 
                                 price=float(quantized_price),
                                 min_price=float(symbol_info.min_price))
                    return None
                
                # Check if limit price is too far from mid_price (potential for adverse fill/slippage)
                if market_state.mid_price > 0 and config.MAX_SLIPPAGE_PERCENTAGE > 0:
                    price_deviation = abs(quantized_price - market_state.mid_price) / market_state.mid_price
                    if price_deviation > config.MAX_SLIPPAGE_PERCENTAGE:
                        log.warning(f"Limit price ({float(quantized_price):.{calculate_decimal_precision(quantized_price)}f}) too far from mid price ({float(market_state.mid_price):.{calculate_decimal_precision(market_state.mid_price)}f}). Potential for non-fill or adverse fill if market moves.", 
                                     expected_slippage=f"{float(price_deviation):.4f}",
                                     max_allowed=f"{float(config.MAX_SLIPPAGE_PERCENTAGE):.4f}")
                
                order_params["price"] = str(quantized_price)
                
                order_value = quantized_qty * quantized_price
                if order_value < symbol_info.min_order_value:
                    log.warning(f"Order value below minimum required by exchange", 
                                 order_value=float(order_value),
                                 min_value=float(symbol_info.min_order_value))
                    return None
            
            response = await self.api_call_with_retry(self.http.place_order, **order_params)
            
            if response and response.get('retCode') == 0:
                session_stats.orders_placed += 1
                order_latency = time.time() - start_time
                performance_monitor.record_order_latency(order_latency)
                
                # Store the order with its client_order_id and creation timestamp locally for tracking
                order_id = response['result'].get('orderId')
                if order_id:
                     market_state.open_orders[order_id] = {
                        "client_order_id": order_params["orderLinkId"],
                        "symbol": config.SYMBOL,
                        "side": side,
                        "price": price if price else market_state.mid_price, # Estimate market order price for tracking
                        "qty": quantized_qty,
                        "status": "New", # Assume new until WS confirms
                        "timestamp": time.time(), # Use current time for creation
                    }

                log.info(f"🎯 Order placed successfully", 
                          order_id=order_id,
                          side=side, 
                          quantity=float(quantized_qty),
                          price=float(price) if price else "Market",
                          latency=f"{order_latency:.3f}s")
                send_toast(f"📝 {side} order placed", "blue", "white")
                return response.get('result', {})
            
            return None
            
        except Exception as e:
            log.error(f"Error placing order: {e}", exc_info=True)
            performance_monitor.record_error("order_placement_error")
            if sentry_sdk: sentry_sdk.capture_exception(e)
            return None
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancels a specific order."""
        response = await self.api_call_with_retry(
            self.http.cancel_order,
            category=config.CATEGORY,
            symbol=config.SYMBOL,
            orderId=order_id
        )
        
        if response and response.get('retCode') == 0:
            log.info(f"🗑️ Order cancelled successfully", order_id=order_id)
            market_state.open_orders.pop(order_id, None) # Remove from local state
            session_stats.orders_cancelled += 1
            return True
        
        # 110001: Order does not exist (already cancelled or filled) - treat as success for idempotency
        if response and response.get('retCode') == 110001:
            log.info(f"Order {order_id} already non-existent/cancelled. Treating as successful cancellation.", order_id=order_id)
            market_state.open_orders.pop(order_id, None) # Ensure removal from local state
            return True

        return False
    
    async def cancel_all_orders(self) -> bool:
        """Cancels all active orders for the symbol."""
        response = await self.api_call_with_retry(
            self.http.cancel_all_orders,
            category=config.CATEGORY,
            symbol=config.SYMBOL
        )
        
        if response and response.get('retCode') == 0:
            order_count = len(market_state.open_orders)
            log.info(f"🧹 All orders cancelled", count=order_count)
            market_state.open_orders.clear()
            session_stats.orders_cancelled += order_count # Assuming all were cancelled
            send_toast(f"🧹 {order_count} orders cancelled", "orange", "white")
            return True
        
        return False

# Enhanced Market Making Strategy with advanced algorithms
class EnhancedMarketMakingStrategy:
    """Advanced market making strategy with intelligent algorithms and plug-in support."""
    
    def __init__(self, client: EnhancedBybitClient):
        self.client = client
        self.running = False
        self.last_rebalance_time = 0
        self.last_memory_cleanup = time.time()
        self.adaptive_spread_multiplier = Decimal("1.0")
        self.adaptive_quantity_multiplier = Decimal("1.0")
        self.market_impact_history = deque(maxlen=100) # Records of calculated market impact
        self.order_success_rate = deque(maxlen=200) # 1 for success, 0 for failure on order placement

        # Register for config updates
        config_manager.add_callback(self.on_config_update)
        
        # Initialize plugins
        for callback in plugin_manager.callbacks:
            try:
                # Pass the strategy instance to the plugin's register callback
                # This allows plugins to augment or replace strategy methods
                callback(self) 
                log.info(f"Applied plugin callback to strategy.")
            except Exception as e:
                log.error(f"Error applying plugin callback to strategy: {e}", exc_info=True)
                if sentry_sdk: sentry_sdk.capture_exception(e)

    def on_config_update(self, new_config: BotConfig):
        """Handle configuration updates."""
        global config
        config = new_config # Update the global config reference
        log.info(f"🔄 Configuration updated, applying new settings.")
        session_stats.config_reloads += 1
        # Update rate limiter config
        rate_limiter.config = new_config

    def calculate_market_impact(self, side: str, quantity: Decimal) -> Decimal:
        """Uses symbol_info's estimate_slippage for accuracy."""
        impact = symbol_info.estimate_slippage(side, quantity)
        self.market_impact_history.append({'impact': impact, 'timestamp': time.time()})
        return impact
    
    def calculate_dynamic_spread(self) -> Decimal:
        """Enhanced dynamic spread calculation with multiple factors."""
        base_spread = config.SPREAD_PERCENTAGE
        
        if not config.VOLATILITY_ADJUSTMENT:
            return base_spread
        
        try:
            spread_multiplier = Decimal("1.0")
            
            # Factor 1: Recent volatility (using price standard deviation)
            if len(market_state.price_history) >= 20:
                recent_prices = [p['price'] for p in list(market_state.price_history)[-20:] if p['price'] > 0]
                if len(recent_prices) > 1:
                    # Calculate simple standard deviation of price changes
                    price_changes = [recent_prices[i] - recent_prices[i-1] for i in range(1, len(recent_prices))]
                    if price_changes:
                        avg_change = sum(price_changes) / len(price_changes)
                        variance = sum([(x - avg_change)**2 for x in price_changes]) / len(price_changes)
                        std_dev = Decimal(str(variance)).sqrt() if variance >= 0 else Decimal("0")
                        
                        if market_state.mid_price > 0:
                            relative_volatility = std_dev / market_state.mid_price
                            # Higher volatility -> wider spread. Adjust sensitivity.
                            volatility_multiplier = Decimal("1.0") + (relative_volatility * Decimal("500")) 
                            volatility_multiplier = max(Decimal("0.5"), min(Decimal("3.0"), volatility_multiplier))
                            spread_multiplier *= volatility_multiplier
                            log.debug(f"Volatility multiplier: {float(volatility_multiplier):.2f}x", std_dev=float(std_dev))

            # Factor 2: Order book imbalance
            if symbol_info.total_bid_volume > 0 and symbol_info.total_ask_volume > 0:
                total_volume = symbol_info.total_bid_volume + symbol_info.total_ask_volume
                imbalance = abs(symbol_info.total_bid_volume - symbol_info.total_ask_volume) / total_volume
                # Higher imbalance -> wider spread
                imbalance_multiplier = Decimal("1.0") + (imbalance * Decimal("0.8"))
                spread_multiplier *= imbalance_multiplier
                log.debug(f"Imbalance multiplier: {float(imbalance_multiplier):.2f}x", imbalance=float(imbalance))
            
            # Factor 3: Recent order success rate (from rate limiter's general success or explicit order attempts)
            # Use rate_limiter's success rate as a proxy for API/order success
            if len(rate_limiter.success_rate) >= 10:
                recent_success = sum(rate_limiter.success_rate) / len(rate_limiter.success_rate)
                if recent_success < 0.5: # Low success rate, widen spread to reduce fills
                    success_multiplier = Decimal("1.5")
                elif recent_success > 0.8: # High success rate, tighten spread
                    success_multiplier = Decimal("0.8")
                else:
                    success_multiplier = Decimal("1.0")
                spread_multiplier *= success_multiplier
                log.debug(f"Success rate multiplier: {float(success_multiplier):.2f}x", recent_success=float(recent_success))
            
            # Factor 4: Market impact history (reflect past slippage)
            if len(self.market_impact_history) >= 5:
                avg_impact = sum(r['impact'] for r in list(self.market_impact_history)[-5:]) / 5
                # Higher impact -> wider spread
                impact_multiplier = Decimal("1.0") + (avg_impact * Decimal("2.0"))
                spread_multiplier *= impact_multiplier
                log.debug(f"Impact multiplier: {float(impact_multiplier):.2f}x", avg_impact=float(avg_impact))
            
            self.adaptive_spread_multiplier = spread_multiplier
            adjusted_spread = base_spread * spread_multiplier
            
            # Ensure minimum spread (at least one tick size)
            min_spread = symbol_info.price_precision / market_state.mid_price if market_state.mid_price > 0 else base_spread
            final_spread = max(adjusted_spread, min_spread * Decimal("1.5")) # Ensure it's slightly more than tick size
            
            # Store for efficiency analysis
            self.spread_efficiency_history = deque(maxlen=50) # Re-init if not already
            self.spread_efficiency_history.append({
                'spread': final_spread,
                'multiplier': spread_multiplier,
                'timestamp': time.time()
            })
            
            return final_spread
            
        except Exception as e:
            log.error(f"Error calculating dynamic spread: {e}", exc_info=True)
            if sentry_sdk: sentry_sdk.capture_exception(e)
        
        return base_spread # Fallback to base spread

    def calculate_position_size(self) -> Decimal:
        """Enhanced position sizing with risk-adjusted calculations."""
        if market_state.available_balance <= 0 or market_state.mid_price <= 0:
            return config.QUANTITY # Return default if no valid market data/balance
        
        try:
            # Base size calculations based on config and available capital
            max_capital_allocation = market_state.available_balance * config.CAPITAL_ALLOCATION_PERCENTAGE
            size_from_capital = (max_capital_allocation / market_state.mid_price).quantize(
                symbol_info.qty_precision, rounding=ROUND_DOWN
            )
            
            # Max position size as percentage of current balance (expressed in quantity)
            max_position_value_usd = market_state.available_balance * config.MAX_POSITION_SIZE
            max_size_from_limit = (max_position_value_usd / market_state.mid_price).quantize(
                symbol_info.qty_precision, rounding=ROUND_DOWN
            )
            
            # Determine the smallest of the three to be conservative
            base_size = min(config.QUANTITY, size_from_capital, max_size_from_limit)
            
            self.adaptive_quantity_multiplier = Decimal("1.0") # Reset for each calculation
            
            # Adaptive Quantity Adjustment based on PnL history
            if config.ADAPTIVE_QUANTITY_ENABLED and len(session_stats.profit_history) >= 2:
                recent_pnl_changes = []
                for i in range(max(0, len(session_stats.profit_history) - 10), len(session_stats.profit_history)):
                    if i > 0:
                        recent_pnl_changes.append(session_stats.profit_history[i][1] - session_stats.profit_history[i-1][1])
                
                if recent_pnl_changes:
                    avg_pnl_change = sum(recent_pnl_changes) / len(recent_pnl_changes)
                    
                    if market_state.available_balance > 0:
                        relative_pnl_performance = avg_pnl_change / market_state.available_balance
                        # A positive performance increases multiplier, negative decreases.
                        self.adaptive_quantity_multiplier = Decimal("1.0") + (relative_pnl_performance * config.ADAPTIVE_QUANTITY_PERFORMANCE_FACTOR)
                        self.adaptive_quantity_multiplier = max(Decimal("0.5"), min(Decimal("2.0"), self.adaptive_quantity_multiplier)) # Clamp
                        log.debug(f"Adaptive quantity adjusted", 
                                     avg_pnl_change=float(avg_pnl_change), 
                                     relative_pnl_performance=float(relative_pnl_performance),
                                     multiplier=float(self.adaptive_quantity_multiplier))
            
            risk_multiplier = Decimal("1.0") * self.adaptive_quantity_multiplier
            
            # Market impact consideration (pre-trade slippage estimation)
            if market_state.mid_price > 0:
                estimated_slippage_buy = symbol_info.estimate_slippage("Buy", base_size)
                estimated_slippage_sell = symbol_info.estimate_slippage("Sell", base_size)
                avg_estimated_slippage = max(estimated_slippage_buy, estimated_slippage_sell)
                
                if avg_estimated_slippage > config.MAX_SLIPPAGE_PERCENTAGE and config.MAX_SLIPPAGE_PERCENTAGE > 0:
                    # Calculate reduction factor to bring slippage within limits
                    impact_reduction_factor = config.MAX_SLIPPAGE_PERCENTAGE / avg_estimated_slippage
                    risk_multiplier *= impact_reduction_factor
                    log.warning(f"Quantity reduced due to estimated high slippage", 
                                 estimated_slippage=f"{float(avg_estimated_slippage):.4f}", 
                                 reduction_factor=float(impact_reduction_factor))
            
            # Adjustment 2: Connection quality (from BotHealth)
            connection_score = bot_health.components['ws_overall_connection']['score']
            if connection_score < 1.0: # Only adjust if not perfect
                risk_multiplier *= Decimal(str(max(0.2, connection_score)))
                log.warning(f"Quantity reduced due to poor connection quality", quality=float(connection_score))
            
            # Adjustment 3: Recent order success rate (from rate limiter)
            if len(rate_limiter.success_rate) >= 10:
                recent_api_success = sum(rate_limiter.success_rate) / len(rate_limiter.success_rate)
                if recent_api_success < 0.8: # If API success rate is below 80%, reduce quantity
                    performance_reduction_factor = Decimal(str(max(0.5, recent_api_success)))
                    risk_multiplier *= performance_reduction_factor
                    log.warning(f"Quantity reduced due to low API success rate", success_rate=f"{float(recent_api_success):.1%}")
            
            adjusted_size = (base_size * risk_multiplier).quantize(symbol_info.qty_precision, rounding=ROUND_DOWN)
            
            # Ensure adjusted size respects minimum trade requirements
            if adjusted_size < symbol_info.min_qty:
                adjusted_size = symbol_info.min_qty
            
            # Re-check order value after final size adjustment
            if market_state.mid_price > 0:
                order_value = adjusted_size * market_state.mid_price
                if order_value < symbol_info.min_order_value:
                    adjusted_size = (symbol_info.min_order_value / market_state.mid_price).quantize(
                        symbol_info.qty_precision, rounding=ROUND_UP
                    )
            
            return adjusted_size
            
        except Exception as e:
            log.error(f"Error calculating position size: {e}", exc_info=True)
            if sentry_sdk: sentry_sdk.capture_exception(e)
            return config.QUANTITY # Fallback to default config quantity

    async def check_circuit_breaker_conditions(self) -> Tuple[bool, str]:
        """Checks various conditions and updates circuit breaker state."""
        global CIRCUIT_BREAKER_STATE
        
        current_overall_health = bot_health.overall_score
        
        # PnL threshold check (already updates bot_health['strategy_pnl'] in session_stats.update_pnl)
        # We don't force `current_overall_health` lower here if PnL is bad, as `bot_health.overall_score`
        # already incorporates it weighted. The thresholds below trigger based on aggregated score.
                
        # Market conditions (abnormal spread) check
        if market_state.mid_price > 0 and market_state.best_bid > 0 and market_state.best_ask > 0:
            spread_percentage = (market_state.best_ask - market_state.best_bid) / market_state.mid_price
            if spread_percentage > config.CB_ABNORMAL_SPREAD_PCT:
                log.warning(f"Circuit Breaker Trigger: Abnormal spread ({spread_percentage:.2%}) exceeds {config.CB_ABNORMAL_SPREAD_PCT:.2%}")
                # Force health down if spread is too wide - directly influence component score
                bot_health.update_component('market_spread_quality', 0.2, f"Abnormal spread {spread_percentage:.2%}")
        else:
            bot_health.update_component('market_spread_quality', 1.0, "Spread OK")

        # Data freshness check (updated by market_state.is_data_fresh)
        is_data_stale = not market_state.is_data_fresh(config.CB_STALE_DATA_TIMEOUT_SEC)
        if is_data_stale:
            log.warning(f"Circuit Breaker Trigger: Market data stale for {time.time() - market_state.last_update_time:.1f}s")
            # bot_health.update_component('market_data_freshness', 0.0, f"Data stale") (already done by is_data_fresh)

        # Connection quality (updated by EnhancedBybitClient.monitor_heartbeats)
        # bot_health.update_component('ws_overall_connection', ...) (already done by monitor_heartbeats)

        # Order success rate (from performance_monitor / rate_limiter)
        overall_api_success_rate = sum(rate_limiter.success_rate) / len(rate_limiter.success_rate) if rate_limiter.success_rate else 1.0
        if overall_api_success_rate < config.CB_LOW_ORDER_SUCCESS_THRESHOLD:
            log.warning(f"Circuit Breaker Trigger: Low API/Order success rate ({overall_api_success_rate:.1%})")
            bot_health.update_component('order_execution_success', 0.0, f"Low success rate {overall_api_success_rate:.1%}")
        else:
            bot_health.update_component('order_execution_success', 1.0, "Order execution OK")

        # System resources (high memory)
        is_high_memory = system_monitor.get_memory_usage() > config.CB_HIGH_MEMORY_MB
        if is_high_memory:
            log.warning(f"Circuit Breaker Trigger: High memory usage ({system_monitor.get_memory_usage():.0f}MB)")
            # bot_health.update_component('system_memory', ...) (already done by system_monitor.update_stats)
        
        # Re-evaluate overall health after all specific component updates
        current_overall_health = bot_health.overall_score

        # Determine circuit breaker state based on overall bot health score
        if config.CIRCUIT_BREAKER_ENABLED:
            if current_overall_health < config.CB_CRITICAL_SHUTDOWN_THRESHOLD:
                if CIRCUIT_BREAKER_STATE != "CRITICAL_SHUTDOWN":
                    CIRCUIT_BREAKER_STATE = "CRITICAL_SHUTDOWN"
                    log.critical(f"🚨🚨 CRITICAL SHUTDOWN: Bot Health Score {current_overall_health:.2f} below {config.CB_CRITICAL_SHUTDOWN_THRESHOLD:.2f}. Initiating graceful shutdown.")
                    send_toast("🚨 CRITICAL SHUTDOWN", "red", "white")
                    global _SHUTDOWN_REQUESTED # Explicitly declare global to modify
                    _SHUTDOWN_REQUESTED = True
                    if sentry_sdk: sentry_sdk.capture_message("Critical Shutdown Triggered", level="fatal")
                return True, "CRITICAL_SHUTDOWN"
            
            elif current_overall_health < config.CB_MAJOR_CANCEL_THRESHOLD:
                if CIRCUIT_BREAKER_STATE != "MAJOR_CANCEL":
                    CIRCUIT_BREAKER_STATE = "MAJOR_CANCEL"
                    log.error(f"🚨 MAJOR CIRCUIT BREAKER: Bot Health Score {current_overall_health:.2f} below {config.CB_MAJOR_CANCEL_THRESHOLD:.2f}. Cancelling all orders.")
                    send_toast("🚨 Major Circuit Breaker", "orange", "white")
                    await self.client.cancel_all_orders()
                    session_stats.circuit_breaker_activations += 1
                    if sentry_sdk: sentry_sdk.capture_message("Major Circuit Breaker Triggered", level="error")
                return True, "MAJOR_CANCEL"
            
            elif current_overall_health < config.CB_MINOR_PAUSE_THRESHOLD:
                if CIRCUIT_BREAKER_STATE != "MINOR_PAUSE":
                    CIRCUIT_BREAKER_STATE = "MINOR_PAUSE"
                    log.warning(f"⚠️ MINOR CIRCUIT BREAKER: Bot Health Score {current_overall_health:.2f} below {config.CB_MINOR_PAUSE_THRESHOLD:.2f}. Pausing new orders.")
                    send_toast("⚠️ Minor Circuit Breaker", "yellow", "black")
                    if sentry_sdk: sentry_sdk.capture_message("Minor Circuit Breaker Triggered", level="warning")
                return True, "MINOR_PAUSE"
            
            else: # Conditions improved, reset circuit breaker
                if CIRCUIT_BREAKER_STATE != "NORMAL":
                    CIRCUIT_BREAKER_STATE = "NORMAL"
                    log.info(f"✅ Circuit breaker reset. Bot health score: {current_overall_health:.2f}")
                    send_toast("✅ Circuit Breaker Reset", "green", "white")
        
        return False, "NORMAL"
    
    async def place_market_making_orders(self):
        """Places market making orders (buy and sell limits)."""
        if not market_state.is_data_fresh(config.CB_STALE_DATA_TIMEOUT_SEC):
            log.warning("⚠️ Market data not fresh, skipping new order placement.")
            return
        
        emergency, reason = await self.check_circuit_breaker_conditions()
        if emergency and reason != "NORMAL":
            log.info(f"Circuit breaker active ({reason}), skipping new market-making order placement.")
            return
        
        if config.TRADING_HOURS_ENABLED:
            current_hour_utc = datetime.utcnow().hour
            if not (config.TRADING_START_HOUR_UTC <= current_hour_utc <= config.TRADING_END_HOUR_UTC):
                log.info(f"Outside trading hours ({config.TRADING_START_HOUR_UTC:02d}:00-{config.TRADING_END_HOUR_UTC:02d}:00 UTC). Skipping market-making order placement.")
                return

        # Check if max open orders limit reached.
        # Note: If MAX_OPEN_ORDERS is 2, it allows one buy and one sell.
        if len(market_state.open_orders) >= config.MAX_OPEN_ORDERS:
            log.debug(f"Max open orders ({config.MAX_OPEN_ORDERS}) reached, skipping new order placement.")
            return
        
        spread = self.calculate_dynamic_spread()
        position_size = self.calculate_position_size()
        
        if position_size <= 0:
            log.warning("⚠️ Calculated position size is zero or too small, skipping orders.")
            return
        
        # Calculate target prices
        bid_price = market_state.mid_price * (Decimal("1") - spread)
        ask_price = market_state.mid_price * (Decimal("1") + spread)
        
        # Adjust prices based on order book depth to be more competitive
        if symbol_info.bid_levels and symbol_info.ask_levels:
            best_bid_level = symbol_info.bid_levels[0][0]
            best_ask_level = symbol_info.ask_levels[0][0]
            
            # For market making, we usually want to place orders *at or inside* the current BBO.
            # Here, we aim to be one tick better than the current best for a potential fill.
            # For Buy, we want to buy at a higher price (more aggressive) than current best bid.
            # For Sell, we want to sell at a lower price (more aggressive) than current best ask.
            bid_price = max(bid_price, best_bid_level + symbol_info.price_precision)
            ask_price = min(ask_price, best_ask_level - symbol_info.price_precision)
            
            # Critical check: If our adjusted bid_price is higher or equal to ask_price, 
            # it indicates a very tight/inverted spread or a pricing error.
            if bid_price >= ask_price:
                log.warning(f"Calculated bid price ({float(bid_price):.{calculate_decimal_precision(bid_price)}f}) is higher or equal to ask price ({float(ask_price):.{calculate_decimal_precision(ask_price)}f}). Skipping order placement due to invalid spread calculation.")
                return
            
        has_buy_order = any(order['side'] == 'Buy' for order in market_state.open_orders.values())
        has_sell_order = any(order['side'] == 'Sell' for order in market_state.open_orders.values())
        
        orders_to_place_count = 0
        
        # Place buy order if no existing buy order and slots available
        if not has_buy_order and len(market_state.open_orders) < config.MAX_OPEN_ORDERS:
            result = await self.client.place_order("Buy", "Limit", position_size, bid_price)
            success = result is not None
            self.order_success_rate.append(1 if success else 0)
            if success:
                orders_to_place_count += 1
        
        # Place sell order if no existing sell order and slots available
        if not has_sell_order and len(market_state.open_orders) < config.MAX_OPEN_ORDERS:
            result = await self.client.place_order("Sell", "Limit", position_size, ask_price)
            success = result is not None
            self.order_success_rate.append(1 if success else 0)
            if success:
                orders_to_place_count += 1
        
        if orders_to_place_count > 0:
            log.info(f"📝 Placed {orders_to_place_count} market making orders", 
                      spread_pct=f"{float(spread*100):.4f}%",
                      size=float(position_size),
                      adaptive_spread_mult=f"{float(self.adaptive_spread_multiplier):.2f}x",
                      adaptive_qty_mult=f"{float(self.adaptive_quantity_multiplier):.2f}x")
    
    async def manage_positions(self):
        """Manages existing positions, primarily for rebalancing."""
        if not market_state.is_data_fresh(config.CB_STALE_DATA_TIMEOUT_SEC):
            log.warning("⚠️ Market data not fresh for position management, skipping.")
            return
        
        long_size = market_state.positions.get('Long', {}).get('size', Decimal('0'))
        short_size = market_state.positions.get('Short', {}).get('size', Decimal('0'))
        net_position = long_size - short_size
        
        # Trigger rebalance only if net position exceeds threshold
        if abs(net_position) > config.REBALANCE_THRESHOLD_QTY:
            # Cooldown check for rebalancing to prevent rapid oscillations
            if time.time() - self.last_rebalance_time < 30: # 30-second cooldown
                log.debug(f"Rebalance cooldown active. {30 - (time.time() - self.last_rebalance_time):.1f}s remaining.")
                return
            
            log.info(f"⚖️ Rebalancing required", 
                      net_position=float(net_position),
                      threshold=float(config.REBALANCE_THRESHOLD_QTY))
            
            rebalance_side = "Sell" if net_position > 0 else "Buy"
            rebalance_qty = abs(net_position).quantize(symbol_info.qty_precision, rounding=ROUND_DOWN)
            
            if rebalance_qty > 0:
                log.info(f"Cancelling all open orders before rebalancing to avoid interference.")
                await self.client.cancel_all_orders()
                await asyncio.sleep(1) # Small delay after cancelling to allow API to process
                
                # Pre-check estimated market impact for rebalance order
                expected_impact = self.calculate_market_impact(rebalance_side, rebalance_qty)
                if expected_impact > config.MAX_SLIPPAGE_PERCENTAGE:
                    log.warning(f"Rebalance quantity ({float(rebalance_qty)}) might incur high slippage ({float(expected_impact):.4f}). Attempting anyways but monitoring.")
                
                result = None
                if config.REBALANCE_ORDER_TYPE.lower() == "market":
                    result = await self.client.place_order(rebalance_side, "Market", rebalance_qty)
                else: # Limit order with price improvement logic
                    price = Decimal("0")
                    # For Buy rebalance, target best ask or slightly higher for quick fill
                    if rebalance_side == "Buy" and market_state.best_ask > 0:
                        price = market_state.best_ask * (Decimal("1") + config.REBALANCE_PRICE_OFFSET_PERCENTAGE)
                    # For Sell rebalance, target best bid or slightly lower for quick fill
                    elif rebalance_side == "Sell" and market_state.best_bid > 0:
                        price = market_state.best_bid * (Decimal("1") - config.REBALANCE_PRICE_OFFSET_PERCENTAGE)
                    
                    if price > 0:
                        result = await self.client.place_order(rebalance_side, "Limit", rebalance_qty, price)
                    else:
                        log.error(f"Cannot place limit rebalance order: Invalid price for {rebalance_side}. Falling back to Market order if possible.")
                        # Could add a fallback to market order here if limit fails critically
                        result = await self.client.place_order(rebalance_side, "Market", rebalance_qty)
                
                if result:
                    self.last_rebalance_time = time.time()
                    session_stats.rebalances_count += 1
                    session_stats.successful_rebalances += 1
                    log.info(f"✅ Rebalance executed successfully", 
                              side=rebalance_side,
                              quantity=float(rebalance_qty),
                              expected_impact=f"{float(expected_impact):.4f}")
                    send_toast(f"⚖️ Rebalanced {rebalance_qty}", "yellow", "black")
                else:
                    log.warning(f"❌ Rebalance failed", quantity=float(rebalance_qty))
            else:
                log.info(f"Rebalance quantity is zero, skipping rebalance.")
    
    async def cancel_and_reprice_stale_orders(self):
        """Cancels stale orders or orders far from current market price."""
        current_time = time.time()
        orders_to_cancel_ids = []
        
        for order_id, order_data in list(market_state.open_orders.items()):
            order_age = current_time - order_data.get('timestamp', current_time)
            
            is_stale = order_age > config.ORDER_LIFESPAN_SECONDS
            
            is_out_of_market = False
            # Only check for 'out of market' if mid_price is available and price_threshold is active
            if market_state.mid_price > 0 and order_data.get('price', Decimal('0')) > 0 and config.PRICE_THRESHOLD > 0:
                price_deviation = abs(order_data['price'] - market_state.mid_price) / market_state.mid_price
                if price_deviation > config.PRICE_THRESHOLD:
                    is_out_of_market = True
            
            if is_stale or is_out_of_market:
                orders_to_cancel_ids.append(order_id)
                reason = "Stale" if is_stale else "Out of Market"
                log.info(f"Order marked for cancellation", order_id=order_id, reason=reason, 
                            age=f"{order_age:.1f}s", price_deviation=f"{float(price_deviation):.4f}" if 'price_deviation' in locals() else "N/A")

        if orders_to_cancel_ids:
            log.info(f"🗑️ Cancelling {len(orders_to_cancel_ids)} orders (stale/out-of-market)")
            for order_id in orders_to_cancel_ids:
                try:
                    await self.client.cancel_order(order_id)
                except Exception as e:
                    log.error(f"Error cancelling order {order_id}: {e}", exc_info=True)
                    if sentry_sdk: sentry_sdk.capture_exception(e)
    
    async def perform_maintenance(self):
        """Performs scheduled maintenance tasks."""
        current_time = time.time()
        
        # Memory cleanup
        if current_time - self.last_memory_cleanup > config.MEMORY_CLEANUP_INTERVAL:
            collected = system_monitor.cleanup_memory()
            self.last_memory_cleanup = current_time
            session_stats.memory_cleanups += 1
            if collected > 0:
                log.info(f"🧹 Memory cleanup completed", objects_collected=collected)
            
            # Update memory health component after cleanup
            memory_usage = system_monitor.get_memory_usage()
            mem_score = max(0.0, 1.0 - (memory_usage / config.CB_HIGH_MEMORY_MB)) if config.CB_HIGH_MEMORY_MB > 0 else 1.0
            bot_health.update_component('system_memory_after_cleanup', float(mem_score), f"Mem after cleanup: {memory_usage:.1f}MB")
        
        # System monitoring update (system_monitor.update_stats is called at the top of loop for dashboard)
        system_monitor.update_stats()
        
        # Configuration hot reload check
        if await config_manager.check_for_updates(): # Await config check
            log.info(f"⚙️ Configuration hot-reloaded successfully")
            session_stats.config_reloads += 1
        
        # Performance logging
        if performance_monitor.should_log_performance():
            perf_summary = performance_monitor.get_performance_summary()
            log.info(f"📊 Performance summary", **perf_summary)
            # Update performance health component
            api_perf_score = max(0.0, 1.0 - (perf_summary['avg_api_time'] / 3.0)) # 3.0s avg API time is 0 score
            bot_health.update_component('api_performance', float(api_perf_score), f"Avg API: {perf_summary['avg_api_time']:.3f}s")
            
            order_latency_score = max(0.0, 1.0 - (perf_summary['avg_order_latency'] / 5.0)) # 5.0s avg order latency is 0 score
            bot_health.update_component('order_latency_performance', float(order_latency_score), f"Avg Order Latency: {perf_summary['avg_order_latency']:.3f}s")

    async def monitor_pnl(self):
        """Monitors PnL and triggers stop loss/take profit."""
        while self.running and not _SHUTDOWN_REQUESTED:
            try:
                if not market_state.is_data_fresh(config.CB_STALE_DATA_TIMEOUT_SEC):
                    log.debug("PnL monitor: Market data not fresh, waiting.")
                    await asyncio.sleep(5)
                    continue
                
                # Loop through a copy of positions as it might change during order execution
                for side, position in list(market_state.positions.items()): 
                    if position['size'] <= 0 or position['avg_price'] <= 0:
                        continue
                    
                    entry_price = position['avg_price']
                    current_price = market_state.mid_price
                    
                    if entry_price == Decimal("0") or current_price == Decimal("0"):
                        log.warning(f"Invalid price detected for PnL calculation: Entry {entry_price}, Current {current_price}. Skipping PnL check for this position.")
                        continue

                    if side == "Long":
                        pnl_pct = (current_price - entry_price) / entry_price
                    else:  # Short
                        pnl_pct = (entry_price - current_price) / entry_price
                    
                    # Stop loss logic
                    if pnl_pct <= -config.STOP_LOSS_PERCENTAGE:
                        log.error(f"🛑 {side} position stop loss triggered", 
                                   pnl_pct=f"{pnl_pct:.2%}",
                                   entry_price=float(entry_price),
                                   current_price=float(current_price),
                                   position_size=float(position['size']))
                        
                        await self.client.cancel_all_orders()
                        close_side = "Sell" if side == "Long" else "Buy"
                        result = await self.client.place_order(close_side, "Market", position['size'])
                        
                        if result:
                            send_toast(f"🛑 {side} stop: {pnl_pct:.2%}", "red", "white")
                        else:
                            log.critical(f"Failed to execute stop loss for {side} position (Order placement failed). Manual intervention may be needed.")
                            # Force major CB state if stop loss cannot be executed
                            global CIRCUIT_BREAKER_STATE
                            if CIRCUIT_BREAKER_STATE == "NORMAL" or CIRCUIT_BREAKER_STATE == "MINOR_PAUSE":
                                CIRCUIT_BREAKER_STATE = "MAJOR_CANCEL" 
                                log.error("Circuit breaker escalated to MAJOR_CANCEL due to failed stop loss execution.")
                                if sentry_sdk: sentry_sdk.capture_message("Stop loss execution failed, escalated to MAJOR_CANCEL", level="error")
                    
                    # Take profit logic
                    elif pnl_pct >= config.PROFIT_PERCENTAGE:
                        log.info(f"🎯 {side} position take profit triggered", 
                                  pnl_pct=f"{pnl_pct:.2%}",
                                  entry_price=float(entry_price),
                                  current_price=float(current_price),
                                  position_size=float(position['size']))
                        
                        await self.client.cancel_all_orders()
                        close_side = "Sell" if side == "Long" else "Buy"
                        result = await self.client.place_order(close_side, "Market", position['size'])
                        
                        if result:
                            send_toast(f"🎯 {side} profit: {pnl_pct:.2%}", "green", "white")
                        else:
                            log.error(f"Failed to execute take profit for {side} position (Order placement failed).")
                
                await asyncio.sleep(5) # Check PnL every 5 seconds
                
            except Exception as e:
                log.error(f"Error in PnL monitoring: {e}", exc_info=True)
                if sentry_sdk: sentry_sdk.capture_exception(e)
                await asyncio.sleep(5)
    
    async def main_strategy_loop(self):
        """Main strategy loop orchestrating trading operations."""
        last_order_refresh = 0
        last_balance_refresh = 0
        
        while self.running and not _SHUTDOWN_REQUESTED:
            try:
                current_time = time.time()
                
                await self.perform_maintenance()
                
                # Data refresh from HTTP as backup/initial sync if WS is disconnected
                if not self.client._private_connected.is_set():
                    if current_time - last_balance_refresh >= config.BALANCE_REFRESH_INTERVAL:
                        log.info("Private WS disconnected, fetching wallet balance via HTTP...")
                        await self.client.get_wallet_balance()
                        await self.client.get_positions()
                        last_balance_refresh = current_time
                    
                    if current_time - last_order_refresh >= config.ORDER_REFRESH_INTERVAL:
                        log.info("Private WS disconnected, fetching open orders via HTTP...")
                        await self.client.get_open_orders()
                        last_order_refresh = current_time
                
                # Execute strategy components in optimal order
                await self.cancel_and_reprice_stale_orders() # Free up order slots first
                await self.manage_positions() # Rebalance positions
                await self.place_market_making_orders() # Place new orders
                
                # Update bot state based on Circuit Breaker and open orders
                if CIRCUIT_BREAKER_STATE != "NORMAL":
                    set_bot_state(f"🚨 {CIRCUIT_BREAKER_STATE}")
                elif len(market_state.open_orders) > 0:
                    set_bot_state("🎯 ACTIVE_TRADING")
                else:
                    set_bot_state("⏳ WAITING")
                
                await asyncio.sleep(config.DASHBOARD_REFRESH_RATE) # Controls loop speed, also dashboard refresh
                
            except Exception as e:
                log.error(f"Error in strategy loop: {e}", exc_info=True)
                if sentry_sdk: sentry_sdk.capture_exception(e)
                set_bot_state("❌ ERROR")
                await asyncio.sleep(5) # Wait before next attempt on error

# Enhanced Dashboard with neon styling
async def display_dashboard():
    """Enhanced dashboard with comprehensive neon-styled metrics"""
    while not _SHUTDOWN_REQUESTED:
        try:
            clear_screen()
            print_neon_header(f"MMXCEL v5.2 Ultra Enhanced - Neon Market Maker ({config.SYMBOL})", NEON_BLUE)
            
            # Enhanced bot status section
            status_colors = {
                "🎯 ACTIVE_TRADING": NEON_GREEN,
                "⏳ WAITING": NEON_ORANGE,
                "🚨 MINOR_PAUSE": YELLOW,
                "🚨 MAJOR_CANCEL": NEON_ORANGE, # Using bright yellow for 'major' warning
                "🚨 CRITICAL_SHUTDOWN": RED,
                "❌ ERROR": RED,
                "INITIALIZING": NEON_BLUE,
                "🔐 TESTING_CREDENTIALS": NEON_BLUE,
                "📊 LOADING_SYMBOL_INFO": NEON_BLUE,
                "📡 CONNECTING_WEBSOCKETS": NEON_BLUE,
                "🔄 SYNCING_DATA": NEON_BLUE,
                "🛑 SHUTTING_DOWN": RED,
                "🎯 STARTING_STRATEGY": NEON_GREEN,
            }
            status_color = status_colors.get(BOT_STATE, WHITE)
            
            print(format_metric("Bot Status", BOT_STATE, NEON_PINK, status_color))
            print(format_metric("Testnet Mode", "🧪 ON" if config.USE_TESTNET else "🚀 LIVE", 
                              NEON_PINK, NEON_ORANGE if config.USE_TESTNET else NEON_GREEN))
            # Display overall bot health score
            health_color = NEON_GREEN if bot_health.overall_score > 0.8 else NEON_ORANGE if bot_health.overall_score > 0.5 else RED
            print(format_metric("Overall Bot Health", f"{bot_health.overall_score:.2f} ({bot_health.get_status_message()})", 
                                NEON_PINK, health_color))
            
            # Display Circuit Breaker State
            cb_state_color = status_colors.get(f"🚨 {CIRCUIT_BREAKER_STATE}", NEON_GREEN if CIRCUIT_BREAKER_STATE == "NORMAL" else RED)
            print(format_metric("Circuit Breaker", CIRCUIT_BREAKER_STATE, NEON_PINK, cb_state_color))

            print(format_metric("Neon Colors", "✨ ENABLED" if config.NEON_COLORS_ENABLED else "DISABLED", 
                              NEON_PINK, NEON_GREEN if config.NEON_COLORS_ENABLED else WHITE))
            # Display Trading Hours Status
            trading_hours_status = f"{config.TRADING_START_HOUR_UTC:02d}:00-{config.TRADING_END_HOUR_UTC:02d}:00 UTC"
            if config.TRADING_HOURS_ENABLED:
                current_hour_utc = datetime.utcnow().hour
                if config.TRADING_START_HOUR_UTC <= current_hour_utc <= config.TRADING_END_HOUR_UTC:
                    trading_hours_status += " (ACTIVE)"
                    trading_hours_color = NEON_GREEN
                else:
                    trading_hours_status += " (INACTIVE)"
                    trading_hours_color = NEON_ORANGE
            else:
                trading_hours_status += " (DISABLED)"
                trading_hours_color = WHITE
            print(format_metric("Trading Hours", trading_hours_status, NEON_PINK, trading_hours_color))

            print_neon_separator(color=NEON_PURPLE)
            
            # Enhanced market data section
            print(f"{NEON_BLUE}{BOLD}📊 Market Data:{NC}")
            price_precision = calculate_decimal_precision(symbol_info.price_precision)
            print(format_metric("Mid Price", market_state.mid_price, NEON_PINK, NEON_GREEN, value_precision=price_precision))
            print(format_metric("Best Bid", market_state.best_bid, NEON_PINK, NEON_BLUE, value_precision=price_precision))
            print(format_metric("Best Ask", market_state.best_ask, NEON_PINK, NEON_BLUE, value_precision=price_precision))
            
            if market_state.mid_price > 0:
                spread_pct = (market_state.best_ask - market_state.best_bid) / market_state.mid_price * 100
                spread_color = NEON_GREEN if spread_pct < 0.1 else NEON_ORANGE if spread_pct < 0.5 else RED
                print(format_metric("Market Spread", f"{spread_pct:.4f}%", NEON_PINK, spread_color))
                print(format_metric("Adaptive Spread Mult", f"{strategy.adaptive_spread_multiplier:.2f}x", NEON_PINK, NEON_CYAN))

            if symbol_info.bid_levels and symbol_info.ask_levels:
                depth_ratio = symbol_info.get_market_depth_ratio()
                depth_color = NEON_GREEN if 0.8 <= depth_ratio <= 1.2 else NEON_ORANGE
                print(format_metric("Bid Depth", f"{symbol_info.total_bid_volume:.3f}", NEON_PINK, NEON_BLUE))
                print(format_metric("Ask Depth", f"{symbol_info.total_ask_volume:.3f}", NEON_PINK, NEON_BLUE))
                print(format_metric("Depth Ratio", f"{depth_ratio:.2f}", NEON_PINK, depth_color))
            
            data_age = time.time() - market_state.last_update_time
            age_color = NEON_GREEN if data_age < config.CB_STALE_DATA_TIMEOUT_SEC * 0.3 else NEON_ORANGE if data_age < config.CB_STALE_DATA_TIMEOUT_SEC else RED
            print(format_metric("Data Age", f"{data_age:.1f}s", NEON_PINK, age_color))
            print(format_metric("Data Quality", f"{market_state.data_quality_score:.1%}", NEON_PINK, 
                              NEON_GREEN if market_state.data_quality_score > 0.8 else NEON_ORANGE))
            print_neon_separator(color=NEON_PURPLE)
            
            # Enhanced system resources
            print(f"{NEON_BLUE}{BOLD}💻 System Resources:{NC}")
            system_monitor.update_stats() # Ensure stats are fresh for display
            memory_usage = system_monitor.get_memory_usage()
            peak_memory = system_monitor.get_peak_memory()
            cpu_usage = system_monitor.get_avg_cpu_usage()
            
            memory_color = NEON_GREEN if memory_usage < config.CB_HIGH_MEMORY_MB * 0.5 else NEON_ORANGE if memory_usage < config.CB_HIGH_MEMORY_MB else RED
            cpu_color = NEON_GREEN if cpu_usage < 50 else NEON_ORANGE if cpu_usage < 80 else RED
            
            print(format_metric("Memory Usage", f"{memory_usage:.1f} MB", NEON_PINK, memory_color))
            print(format_metric("Peak Memory", f"{peak_memory:.1f} MB", NEON_PINK, NEON_BLUE))
            print(format_metric("CPU Usage", f"{cpu_usage:.1f}%", NEON_PINK, cpu_color))
            print_neon_separator(color=NEON_PURPLE)
            
            # Enhanced account information
            print(f"{NEON_BLUE}{BOLD}💰 Account Information:{NC}")
            balance_color = NEON_GREEN if market_state.available_balance > 100 else NEON_ORANGE
            print(format_metric("Available Balance", f"{market_state.available_balance:.2f} USDT", 
                              NEON_PINK, balance_color))
            
            # Enhanced positions
            print(f"{NEON_BLUE}{BOLD}📈 Positions:{NC}")
            long_pos = market_state.positions.get('Long', {'size': Decimal('0'), 'unrealisedPnl': Decimal('0')})
            short_pos = market_state.positions.get('Short', {'size': Decimal('0'), 'unrealisedPnl': Decimal('0')})
            
            qty_precision = calculate_decimal_precision(symbol_info.qty_precision)
            print(format_metric("Long Position", long_pos['size'], NEON_PINK, NEON_GREEN, value_precision=qty_precision))
            print(format_metric("Long PnL", long_pos['unrealisedPnl'], NEON_PINK, is_pnl=True, value_precision=2))
            print(format_metric("Short Position", short_pos['size'], NEON_PINK, NEON_ORANGE, value_precision=qty_precision))
            print(format_metric("Short PnL", short_pos['unrealisedPnl'], NEON_PINK, is_pnl=True, value_precision=2))
            
            net_position = long_pos['size'] - short_pos['size']
            net_color = NEON_GREEN if abs(net_position) < config.REBALANCE_THRESHOLD_QTY else NEON_ORANGE
            print(format_metric("Net Position", net_position, NEON_PINK, net_color, value_precision=qty_precision))
            # Recalculate size to display potential size for next order cycle
            try:
                display_qty = strategy.calculate_position_size()
            except Exception:
                display_qty = Decimal("0") # Fallback in case of error during calculation for display
            print(format_metric("Calculated Order Qty", display_qty, NEON_PINK, NEON_CYAN, value_precision=qty_precision))

            print_neon_separator(color=NEON_PURPLE)
            
            # Enhanced open orders
            print(f"{NEON_BLUE}{BOLD}📋 Open Orders ({len(market_state.open_orders)}):{NC}")
            if market_state.open_orders:
                for i, (order_id, order) in enumerate(list(market_state.open_orders.items())[:5]): # Show up to 5 orders
                    side_color = NEON_GREEN if order['side'] == 'Buy' else NEON_ORANGE
                    age = time.time() - order['timestamp']
                    age_color = NEON_GREEN if age < config.ORDER_LIFESPAN_SECONDS * 0.5 else NEON_ORANGE if age < config.ORDER_LIFESPAN_SECONDS else RED
                    print(f"  {side_color}{order['side']:<4}{NC} {order['qty']:.{qty_precision}f} @ "
                          f"{order['price']:.{price_precision}f} {age_color}({age:.0f}s){NC}")
            else:
                print(f"  {NEON_ORANGE}⏳ No active orders{NC}")
            print_neon_separator(color=NEON_PURPLE)
            
            # Enhanced performance metrics
            print(f"{NEON_BLUE}{BOLD}⚡ Performance & Statistics:{NC}")
            uptime_str = session_stats.get_uptime_formatted()
            print(format_metric("Uptime", uptime_str, NEON_PINK, NEON_GREEN))
            
            # Trading statistics with enhanced colors
            success_rate = session_stats.get_success_rate()
            success_color = NEON_GREEN if success_rate > 80 else NEON_ORANGE if success_rate > 60 else RED
            
            print(format_metric("Orders Placed", session_stats.orders_placed, NEON_PINK, NEON_BLUE))
            print(format_metric("Orders Filled", session_stats.orders_filled, NEON_PINK, NEON_GREEN))
            print(format_metric("Orders Cancelled", session_stats.orders_cancelled, NEON_PINK, NEON_ORANGE))
            print(format_metric("Orders Rejected", session_stats.orders_rejected, NEON_PINK, 
                              RED if session_stats.orders_rejected > 0 else NEON_GREEN))
            print(format_metric("Success Rate", f"{success_rate:.1f}%", NEON_PINK, success_color))
            print(format_metric("Rebalances", session_stats.rebalances_count, NEON_PINK, NEON_BLUE))
            print(format_metric("CB Activations", session_stats.circuit_breaker_activations, NEON_PINK, 
                              RED if session_stats.circuit_breaker_activations > 0 else NEON_GREEN))
            
            # PnL and risk metrics
            total_pnl = sum(pos.get('unrealisedPnl', Decimal('0')) for pos in market_state.positions.values())
            print(format_metric("Total PnL", total_pnl, NEON_PINK, is_pnl=True, value_precision=2))
            drawdown_color = RED if session_stats.max_drawdown > config.CB_PNL_STOP_LOSS_PCT * Decimal('0.5') else NEON_GREEN
            print(format_metric("Max Drawdown", f"{session_stats.max_drawdown:.2%}", NEON_PINK, drawdown_color)) 
            print(format_metric("Volume Traded", session_stats.total_volume_traded, NEON_PINK, NEON_BLUE, 
                              value_precision=qty_precision))
            
            # System metrics
            perf_summary = performance_monitor.get_performance_summary()
            if perf_summary['avg_api_time'] > 0:
                api_color = NEON_GREEN if perf_summary['avg_api_time'] < 1 else NEON_ORANGE if perf_summary['avg_api_time'] < 3 else RED
                print(format_metric("Avg API Time", f"{perf_summary['avg_api_time']:.3f}s", NEON_PINK, api_color))
            
            if perf_summary['avg_order_latency'] > 0:
                latency_color = NEON_GREEN if perf_summary['avg_order_latency'] < 2 else NEON_ORANGE
                print(format_metric("Avg Order Latency", f"{perf_summary['avg_order_latency']:.3f}s", NEON_PINK, latency_color))
            
            print(format_metric("Memory Cleanups", session_stats.memory_cleanups, NEON_PINK, NEON_BLUE))
            print(format_metric("Config Reloads", session_stats.config_reloads, NEON_PINK, NEON_BLUE))
            print(format_metric("Connection Drops", session_stats.connection_drops, NEON_PINK, 
                              RED if session_stats.connection_drops > 0 else NEON_GREEN))
            
            print_neon_separator(color=NEON_PURPLE)
            # Runtime Config Adjustment commands
            print(f"{NEON_ORANGE}🎮 Commands: 'q' quit | 'c' cancel all | 'r' rebalance | 'k' reset CB | 'i' info | 'm' memory | 's' set spread | 'z' set qty | 't' toggle trading hours{NC}")
            
            await asyncio.sleep(config.DASHBOARD_REFRESH_RATE)
            
        except Exception as e:
            log.error(f"Dashboard error: {e}", exc_info=True)
            if sentry_sdk: sentry_sdk.capture_exception(e)
            await asyncio.sleep(1)

# Enhanced input handling
async def handle_user_input(strategy: EnhancedMarketMakingStrategy):
    """Enhanced user input handling with more commands"""
    global _SHUTDOWN_REQUESTED, CIRCUIT_BREAKER_STATE
    while not _SHUTDOWN_REQUESTED:
        try:
            # Check for input without blocking
            if sys.stdin.isatty(): # Check if running in a real terminal
                # Using select.select to non-blockingly check for stdin.
                # Timeout of 0 means it returns immediately.
                rlist, _, _ = select.select([sys.stdin], [], [], 0)
                if rlist: # If stdin is ready to be read
                    key = sys.stdin.read(1).lower()
                    
                    if key == 'q':
                        log.info("🛑 User requested shutdown")
                        _SHUTDOWN_REQUESTED = True
                        break
                    
                    elif key == 'c':
                        log.info("🗑️ User requested cancel all orders")
                        await strategy.client.cancel_all_orders()
                        send_toast("🗑️ All orders cancelled", "orange", "white")
                    
                    elif key == 'r':
                        log.info("⚖️ User requested manual rebalance")
                        strategy.last_rebalance_time = 0 # Reset cooldown for immediate rebalance
                        await strategy.manage_positions()
                        send_toast("⚖️ Manual rebalance triggered", "blue", "white")
                    
                    elif key == 'k': # Reset Circuit Breaker
                        log.info("🟢 User requested circuit breaker reset")
                        CIRCUIT_BREAKER_STATE = "NORMAL"
                        send_toast("🟢 Circuit Breaker Reset", "green", "white")
                    
                    elif key == 'i':
                        perf_summary = performance_monitor.get_performance_summary()
                        log.info(f"📊 Performance summary logged", **perf_summary)
                        send_toast("📊 Performance info logged", "blue", "white")
                    
                    elif key == 'm':
                        collected = system_monitor.cleanup_memory()
                        log.info(f"🧹 Manual memory cleanup", objects_collected=collected)
                        send_toast(f"🧹 Memory cleaned: {collected} objects", "green", "white")
                    
                    # Runtime Config Adjustment
                    elif key == 's':
                        sys.stdout.write(f"\n{NEON_PINK}Enter new SPREAD_PERCENTAGE (e.g., 0.0005): {NC}")
                        sys.stdout.flush()
                        spread_input = sys.stdin.readline().strip()
                        try:
                            new_spread = Decimal(spread_input)
                            if new_spread > 0:
                                config.SPREAD_PERCENTAGE = new_spread
                                log.info(f"Updated SPREAD_PERCENTAGE", new_spread=float(new_spread))
                                send_toast(f"Spread updated to {new_spread}", "blue", "white")
                            else:
                                log.warning("Invalid spread percentage. Must be > 0.")
                        except DecimalException:
                            log.warning("Invalid input for spread percentage.")
                    
                    elif key == 'z':
                        sys.stdout.write(f"\n{NEON_PINK}Enter new QUANTITY (e.g., 0.001): {NC}")
                        sys.stdout.flush()
                        qty_input = sys.stdin.readline().strip()
                        try:
                            new_qty = Decimal(qty_input)
                            if new_qty > 0:
                                config.QUANTITY = new_qty
                                log.info(f"Updated QUANTITY", new_qty=float(new_qty))
                                send_toast(f"Quantity updated to {new_qty}", "blue", "white")
                            else:
                                log.warning("Invalid quantity. Must be > 0.")
                        except DecimalException:
                            log.warning("Invalid input for quantity.")
                    
                    elif key == 't':
                        config.TRADING_HOURS_ENABLED = not config.TRADING_HOURS_ENABLED
                        log.info(f"TRADING_HOURS_ENABLED toggled", status=config.TRADING_HOURS_ENABLED)
                        send_toast(f"Trading Hours {'ENABLED' if config.TRADING_HOURS_ENABLED else 'DISABLED'}", "blue", "white")
            else:
                await asyncio.sleep(1) # If not a TTY, don't busy-wait on stdin
                
            await asyncio.sleep(0.1) # Small sleep to prevent busy-waiting
            
        except Exception as e:
            log.error(f"Input handling error: {e}", exc_info=True)
            if sentry_sdk: sentry_sdk.capture_exception(e)
            await asyncio.sleep(1)

# Enhanced signal handling
def signal_handler(signum, frame):
    """Enhanced signal handling with proper cleanup"""
    global _SHUTDOWN_REQUESTED
    if not _SHUTDOWN_REQUESTED: # Avoid logging multiple shutdown requests
        log.info(f"🛑 Received signal {signum}, initiating graceful shutdown")
        _SHUTDOWN_REQUESTED = True
        send_toast("🛑 MMXCEL: Shutdown signal received", "red", "white")

# Main execution logic
async def main():
    """Main application entry point with comprehensive initialization and task management."""
    global _HAS_TERMUX_TOAST_CMD
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    _HAS_TERMUX_TOAST_CMD = check_termux_toast()
    
    print_neon_header("MMXCEL v5.2 Ultra Enhanced - Neon Market Maker", NEON_BLUE)
    log.info(f"🚀 Initializing ultra-enhanced trading bot...")
    log.info(f"✨ Neon colors {'enabled' if config.NEON_COLORS_ENABLED else 'disabled'}")
    print_neon_separator(color=NEON_PURPLE)
    
    # Validate API credentials
    if not API_KEY or not API_SECRET:
        log.critical("❌ API credentials not found in environment variables. Please set BYBIT_API_KEY and BYBIT_API_SECRET.")
        sys.exit(1)
    
    # Initialize core components
    client = EnhancedBybitClient(API_KEY, API_SECRET, config.USE_TESTNET)
    
    # Load plugins *before* initializing strategy so plugins can augment it
    plugin_manager.load_plugins(config.PLUGIN_FOLDER)

    strategy = EnhancedMarketMakingStrategy(client) # Strategy initialized after plugins loaded

    # List to hold all background tasks
    all_tasks = []

    try:
        # Step 1: Test API credentials
        set_bot_state("🔐 TESTING_CREDENTIALS")
        if not await client.test_credentials():
            log.critical("❌ API credential validation failed. Exiting.")
            sys.exit(1)
        
        # Step 2: Get symbol information
        set_bot_state("📊 LOADING_SYMBOL_INFO")
        if not await client.get_symbol_info():
            log.critical("❌ Failed to load symbol information. Exiting.")
            sys.exit(1)
        
        # Step 3: Start WebSocket connections in a background task
        set_bot_state("📡 CONNECTING_WEBSOCKETS")
        all_tasks.append(asyncio.create_task(client.connect_websockets(), name='WS_Connector'))
        
        # Wait for WebSocket connections to establish
        connection_timeout = 30 # seconds
        start_time = time.time()
        log.info("Waiting for WebSocket connections to establish...")
        while not (client._public_connected.is_set() and client._private_connected.is_set()):
            if time.time() - start_time > connection_timeout:
                log.critical("⏰ WebSocket connection timeout. Exiting.")
                sys.exit(1)
            await asyncio.sleep(0.5)
        
        log.info("🟢 WebSocket connections established successfully")
        
        # Step 4: Initial data synchronization via HTTP (if WS is not fast enough)
        set_bot_state("🔄 SYNCING_DATA")
        await client.get_wallet_balance()
        await client.get_open_orders()
        await client.get_positions()
        
        if market_state.available_balance <= 0:
            log.warning("💰 No available balance found. Bot might not place orders.")
        
        # Step 5: Start strategy execution and other concurrent tasks
        set_bot_state("🎯 STARTING_STRATEGY")
        strategy.running = True
        
        log.info("🎉 Bot initialization complete. Starting ultra-enhanced trading operations...")
        send_toast("🎉 MMXCEL v5.2 Ultra Enhanced started!", "green", "white")
        
        # Add all other long-running tasks to the list
        all_tasks.append(asyncio.create_task(strategy.main_strategy_loop(), name='Strategy_Loop'))
        all_tasks.append(asyncio.create_task(strategy.monitor_pnl(), name='PnL_Monitor'))
        all_tasks.append(asyncio.create_task(client.monitor_heartbeats(), name='Heartbeat_Monitor'))
        all_tasks.append(asyncio.create_task(display_dashboard(), name='Dashboard'))
        all_tasks.append(asyncio.create_task(handle_user_input(strategy), name='Input_Handler'))
        
        # Wait for _SHUTDOWN_REQUESTED, then cancel all tasks
        while not _SHUTDOWN_REQUESTED:
            await asyncio.sleep(1) # Keep main alive until shutdown is requested

        # Graceful Shutdown Sequence
        log.info("Initiating graceful shutdown sequence...")
        for task in all_tasks:
            if not task.done():
                log.debug(f"Cancelling task: {task.get_name()}")
                task.cancel()
        
        # Wait for all tasks to complete or be cancelled
        await asyncio.gather(*all_tasks, return_exceptions=True) # return_exceptions=True prevents gather from failing on first task exception
        log.info("All tasks cancelled/completed.")

    except Exception as e:
        log.critical(f"💥 Fatal error occurred during main execution: {e}", exc_info=True)
        if sentry_sdk: sentry_sdk.capture_exception(e)
    finally:
        set_bot_state("🛑 SHUTTING_DOWN")
        log.info("Cleaning up resources...")
        if client.public_ws:
            client.public_ws.exit() # Close WebSocket connections
            log.info("Public WebSocket closed.")
        if client.private_ws:
            client.private_ws.exit()
            log.info("Private WebSocket closed.")
        log.info("MMXCEL has shut down gracefully.")
        send_toast("👋 MMXCEL has shut down", "red", "white")

if __name__ == "__main__":
    asyncio.run(main())

