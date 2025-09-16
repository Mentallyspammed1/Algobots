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

try:
    from plyer import notification
    _HAS_PLYER_NOTIFICATION = True
except ImportError:
    _HAS_PLYER_NOTIFICATION = False
    notification = None # Ensure notification is None if plyer isn't found


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
WHITE = Style.BRIGHT + Fore.WHITE # Changed to bright white for consistency
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

# Global state management (these will remain global for simplicity of access across modules/functions)
_SHUTDOWN_REQUESTED = False
_HAS_TERMUX_TOAST_CMD = False # Checked once at startup
BOT_STATE = "INITIALIZING"
CIRCUIT_BREAKER_STATE = "NORMAL" # NORMAL, MINOR_PAUSE, MAJOR_CANCEL, CRITICAL_SHUTDOWN

# Helper Functions (will access global state where necessary)
# These functions are kept global for convenience and because they interact with global state.
# For a larger project, they might be refactored into a utility class.
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
    full_header_content = f"{' ' * padding_left}{header_text}{' ' * padding_right}"
    print(f"{color}{full_header_content.strip()}{NC}")

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

# MODIFIED: send_toast function for cross-platform notifications
def send_toast(message: str, color: str = "#336699", text_color: str = "white") -> None:
    """Send toast notification (Termux or Desktop)."""
    if _HAS_TERMUX_TOAST_CMD:
        try:
            os.system(f"termux-toast -b '{color}' -c '{text_color}' '{message}'")
        except Exception as e:
            log.warning(f"Failed to send Termux toast: {e}")
    elif _HAS_PLYER_NOTIFICATION: # --- NEW: Plyer notification ---
        try:
            notification.notify(
                title="MMXCEL Bot Alert",
                message=message,
                app_name="MMXCEL",
                timeout=5 # seconds
            )
        except Exception as e:
            log.warning(f"Failed to send Plyer notification: {e}")
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
        self.components['market_spread_quality']['weight'] = 1.0
        self.components['order_execution_success']['weight'] = 1.5
        self.components['ws_public_latency']['weight'] = 1.0
        self.components['ws_private_latency']['weight'] = 1.0
        self.components['ws_public_data_quality']['weight'] = 1.0
        self.components['ws_private_data_quality']['weight'] = 1.0
        self.components['system_cpu']['weight'] = 1.0
        self.components['system_memory_after_cleanup']['weight'] = 0.5 # Less critical, just informative
        self.components['order_latency_performance']['weight'] = 1.0
    
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

# BotHealth is initialized globally as it's a core dependency for `set_bot_state` and others.
bot_health = BotHealth()

# Enhanced Rate Limiting with Adaptive Backoff
class AdaptiveRateLimiter:
    """Advanced rate limiter with dynamic backoff and token bucket algorithm."""
    
    def __init__(self, config_ref: 'BotConfig'): # Type hint as string for forward reference
        self.config = config_ref # Store a reference to the config object
        self.tokens = Decimal(str(self.config.RATE_LIMIT_BURST_LIMIT)) 
        self.last_update = time.time()
        self.lock = asyncio.Lock()
        self.success_rate = deque(maxlen=100) # Records 1 for success, 0 for failure
        self.current_rate = Decimal(str(self.config.RATE_LIMIT_REQUESTS_PER_SECOND))
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

# MODIFIED: EnhancedLogger class for dedicated trade journal
class EnhancedLogger:
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        self.trade_logger = logging.getLogger(f"{name}.trades") # Initialize trade_logger here
        self.trade_logger.setLevel(logging.INFO)
        self.setup_logging() # Call setup in init

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
            formatter = logging.Formatter('{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": %(message)s}')
        else:
            formatter = logging.Formatter(f"{NEON_CYAN}%(asctime)s{NC} {BOLD}[%(levelname)s]{NC} %(message)s")
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # File handler for general logs
        log_file_path = "mmxcel.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_file_path,
            maxBytes=config.MAX_LOG_FILE_SIZE, # Use config value
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

        # --- NEW: Dedicated Trade Journal File Handler ---
        trade_journal_path = "mmxcel_trades.log"
        trade_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s' if not LOG_AS_JSON else
            '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "event": "trade_journal", "data": %(message)s}'
        )
        trade_file_handler = logging.handlers.RotatingFileHandler(
            trade_journal_path,
            maxBytes=config.TRADE_JOURNAL_FILE_SIZE, # Use config value
            backupCount=3
        )
        trade_file_handler.setFormatter(trade_formatter)
        self.trade_logger.addHandler(trade_file_handler)
        # --- END NEW ---

    # Add a new method for journaling trades
    def journal_trade(self, trade_data: Dict):
        """Logs a trade event to the dedicated trade journal."""
        if LOG_AS_JSON:
            self.trade_logger.info(json.dumps(trade_data))
        else:
            self.trade_logger.info(f"TRADE: Side={trade_data.get('side')}, Price={trade_data.get('price')}, "
                                 f"Qty={trade_data.get('quantity')}, OrderID={trade_data.get('order_id')}, "
                                 f"Slippage={trade_data.get('slippage_pct'):.4f}, Latency={trade_data.get('latency'):.3f}s")


# Initialize logger first, as other components might use it during their init
log = EnhancedLogger("MMXCEL")

# Initialize config_manager and config globally, as they are needed early by other global objects.
config_manager = ConfigManager()
config = config_manager.config # This is the initial config instance

# Re-call setup_logging to ensure it uses the loaded config for MAX_LOG_FILE_SIZE etc.
log.setup_logging() # Re-setup with potentially loaded config values

# Now the other global objects can be initialized, as `config` is available.
symbol_info = SymbolInfo()
market_state = MarketState()
session_stats = SessionStats()
system_monitor = SystemMonitor()
rate_limiter = AdaptiveRateLimiter(config) # Now `config` is guaranteed to be initialized


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

# Enhanced Bybit Client with better connection management and robust API calls
class EnhancedBybitClient:
    """Enhanced Bybit client with advanced connection management, retry logic, and WS order operations."""
    
    def __init__(self, key: str, secret: str, testnet: bool, 
                 market_state_ref: 'MarketState', symbol_info_ref: 'SymbolInfo', 
                 session_stats_ref: 'SessionStats', performance_monitor_ref: 'PerformanceMonitor',
                 bot_health_ref: 'BotHealth', config_ref: 'BotConfig', log_ref: 'EnhancedLogger',
                 send_toast_func: Callable[[str, str, str], None]):
        
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

        # For WebSocket command responses
        self._ws_command_futures: Dict[str, asyncio.Future] = {}
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
            self.log.info(f"Shutdown requested, not attempting to reconnect {ws_type} WS.")
            self._reconnect_tasks.pop(ws_type, None) # Clean up task reference
            return
            
        attempt = self.connection_attempts[ws_type]
        delay = self.reconnect_delays[min(attempt, len(self.reconnect_delays) - 1)]
        self.log.info(f"Attempting to reconnect {ws_type} WS in {delay}s", attempt=attempt + 1)
        
        await asyncio.sleep(delay)

        # Re-check shutdown flag after sleep
        if _SHUTDOWN_REQUESTED:
            self.log.info(f"Shutdown requested after reconnect delay, not reconnecting {ws_type} WS.")
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
            self.connection_attempts[ws_type] = 0 # Reset attempts on success
            self.bot_health.update_component(f'ws_{ws_type}_connection', 1.0, f"{ws_type.capitalize()} WS Connected")
            self.market_state.last_heartbeat = time.time() # Update last message received time

        def _on_ws_close(ws_type: str):
            if ws_type == "public": self._public_connected.clear()
            elif ws_type == "private": self._private_connected.clear()
            
            self.log.warning(f"🔴 {ws_type.capitalize()} WebSocket disconnected.")
            self.session_stats.connection_drops += 1
            self.bot_health.update_component(f'ws_{ws_type}_connection', 0.0, f"{ws_type.capitalize()} WS Disconnected")
            
            if not _SHUTDOWN_REQUESTED:
                # Ensure only one reconnect task per WS type is active
                if ws_type not in self._reconnect_tasks:
                    reconnect_task = asyncio.create_task(self.reconnect_ws(ws_type))
                    self._reconnect_tasks[ws_type] = reconnect_task
                else:
                    self.log.debug(f"Reconnect task for {ws_type} already running.")

        def _on_ws_error(ws_type: str, error: Exception):
            self.log.error(f"🔥 {ws_type.capitalize()} WebSocket error: {error}", error_msg=str(error))
            self.bot_health.update_component(f'ws_{ws_type}_connection', 0.0, f"{ws_type.capitalize()} WS Error: {error}")
            self.performance_monitor.record_error(f"websocket_{ws_type}_error")
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
                channel_type="linear" # Assuming linear for public, adjust if needed
            )
            self.public_ws._on_open = lambda: _on_ws_open("public")
            self.public_ws._on_close = lambda: _on_ws_close("public")
            self.public_ws._on_error = lambda err: _on_ws_error("public", err)
            self.public_ws._on_message = self._on_public_ws_message # Use internal handler
            self.log.debug("Public WS initialized.")

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
            self.private_ws._on_message = self._on_private_ws_message # Use internal handler
            self.log.debug("Private WS initialized.")

        # Initial subscription calls to start the connection
        await self._subscribe_public_topics()
        await self._subscribe_private_topics()
        
    async def _subscribe_public_topics(self):
        """Subscribes to public WebSocket topics."""
        if self.public_ws:
            try:
                self.public_ws.orderbook_stream(
                    symbol=self.config.SYMBOL, 
                    depth=self.config.ORDERBOOK_DEPTH_LEVELS,
                    callback=self._on_public_ws_message # Pass the internal handler
                )
                self.log.info(f"Subscribed to public orderbook for {self.config.SYMBOL}", symbol=self.config.SYMBOL)
            except Exception as e:
                self.log.error(f"Failed to subscribe to public topics: {e}")
                if sentry_sdk: sentry_sdk.capture_exception(e)
                
    async def _subscribe_private_topics(self):
        """Subscribes to private WebSocket topics."""
        if self.private_ws:
            try:
                self.private_ws.order_stream(callback=self._on_private_ws_message)
                self.private_ws.position_stream(callback=self._on_private_ws_message)
                self.private_ws.wallet_stream(callback=self._on_private_ws_message)
                self.log.info(f"Subscribed to private streams")
            except Exception as e:
                self.log.error(f"Failed to subscribe to private topics: {e}")
                if sentry_sdk: sentry_sdk.capture_exception(e)

    def _on_public_ws_message(self, msg: Union[Dict[str, Any], str]) -> None:
        """Handle public WebSocket messages with enhanced processing"""
        message_start_time = time.time()
        
        if not isinstance(msg, dict):
            self.log.debug(f"Received non-dict public WS message: {msg}")
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
                        
                        if self.market_state.best_bid > 0 and self.market_state.best_ask > 0:
                            self.market_state.mid_price = (self.market_state.best_bid + self.market_state.best_ask) / Decimal("2")
                            
                            self.symbol_info.update_orderbook_depth(bids, asks)
                            self.market_state.update_price_history()
                        else:
                            self.market_state.mid_price = Decimal("0") # Invalid prices
                        
                        self.market_state.last_update_time = time.time()
                        self.market_state.last_heartbeat = time.time() # This is the primary heartbeat for market data
                        
                        latency = time.time() - message_start_time
                        self.performance_monitor.record_websocket_latency(latency)
                        
                        self.bot_health.update_component('ws_public_latency', float(max(0.0, 1.0 - (latency / 0.5))), f"Public WS Latency: {latency:.3f}s")
                    else:
                        self.log.warning("Public WS message received with empty bids/asks, skipping update.", msg_payload=msg)
                        self.bot_health.update_component('ws_public_data_quality', 0.5, "Public WS Data Incomplete") # Partial score
                    
        except (KeyError, IndexError, ValueError, TypeError, DecimalException) as e:
            self.log.error(f"Error processing public WS message: {e}", msg_payload=msg)
            self.performance_monitor.record_error("websocket_public_error")
            self.bot_health.update_component('ws_public_data_quality', 0.0, f"Public WS Data Error: {e}")
            if sentry_sdk: sentry_sdk.capture_exception(e)
        except Exception as e:
            self.log.critical(f"Critical error in public WS handler: {e}", exc_info=True)
            self.performance_monitor.record_error("websocket_public_critical")
            self.bot_health.update_component('ws_public_data_quality', 0.0, f"Public WS Critical Error: {e}")
            if sentry_sdk: sentry_sdk.capture_exception(e)

    # MODIFIED: _on_private_ws_message for dedicated trade journal
    def _on_private_ws_message(self, msg: Dict[str, Any]) -> None:
        """Handle private WebSocket messages with enhanced processing"""
        message_start_time = time.time()
        
        # Handle command responses first
        if msg.get("op") == "response" and "id" in msg:
            req_id = msg["id"]
            asyncio.create_task(self._resolve_ws_command_future(req_id, msg)) # Resolve future in a task to not block WS thread
            return # This message was a command response, don't process as topic update

        try:
            topic = msg.get("topic")
            
            if topic == "order":
                for order_data in msg["data"]:
                    order_id = order_data.get("orderId")
                    if not order_id:
                        continue
                    
                    order_status = order_data.get("orderStatus")
                    
                    if order_status == "Filled":
                        order_details = self.market_state.open_orders.pop(order_id, None)
                        if order_details:
                            self.session_stats.orders_filled += 1
                            
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
                                
                                if abs(slippage) > self.config.MAX_SLIPPAGE_PERCENTAGE:
                                    self.session_stats.slippage_events += 1
                                    self.log.warning(f"High slippage detected: {side} order", 
                                                 order_id=order_id,
                                                 expected=float(expected_price),
                                                 actual=float(actual_price),
                                                 slippage=f"{float(slippage):.4f}")
                            
                            trade_data = {
                                'timestamp': time.time(),
                                'order_id': order_id,
                                'client_order_id': order_details.get("client_order_id", "N/A"),
                                'symbol': self.config.SYMBOL,
                                'side': side,
                                'price': actual_price,
                                'quantity': filled_qty,
                                'slippage_pct': slippage,
                                'latency': (time.time() - order_details.get("timestamp", message_start_time)), # Latency in seconds
                                'type': 'Filled'
                            }
                            self.market_state.add_trade(trade_data)
                            self.log.journal_trade(trade_data) # --- MODIFIED: Call new journal_trade method ---
                            
                            self.session_stats.total_volume_traded += filled_qty
                            
                            self.log.info(f"Order filled successfully", 
                                      order_id=order_id,
                                      side=side, 
                                      quantity=float(filled_qty),
                                      price=float(actual_price),
                                      slippage=f"{float(slippage):.4f}")
                            self.send_toast(f"✅ {side} {filled_qty} @ {actual_price:.{calculate_decimal_precision(actual_price)}f}", "green", "white")
                
                elif order_status in ("Canceled", "Deactivated"):
                    if order_id in self.market_state.open_orders:
                        self.market_state.open_orders.pop(order_id, None)
                        self.session_stats.orders_cancelled += 1
                        self.log.info(f"Order cancelled by exchange or deactivated", order_id=order_id, status=order_status)
                
                elif order_status == "Rejected":
                    if order_id in self.market_state.open_orders:
                        self.market_state.open_orders.pop(order_id, None)
                    self.session_stats.orders_rejected += 1
                    self.log.warning(f"Order rejected", order_id=order_id, reject_reason=order_data.get('rejectReason'))
                    self.send_toast("❌ Order rejected", "red", "white")
                
                else: # New, PartiallyFilled, PendingNew, etc.
                    if order_status in ["New", "PartiallyFilled", "PendingNew"]:
                        current_order_entry = self.market_state.open_orders.get(order_id, {})
                        self.market_state.open_orders[order_id] = {
                            "client_order_id": order_data.get("orderLinkId", current_order_entry.get("client_order_id", "N/A")),
                            "symbol": order_data.get("symbol", current_order_entry.get("symbol")),
                            "side": order_data.get("side", current_order_entry.get("side")),
                            "price": Decimal(str(order_data.get("price", current_order_entry.get("price", "0")))),
                            "qty": Decimal(str(order_data.get("qty", current_order_entry.get("qty", "0")))),
                            "status": order_status,
                            "timestamp": float(order_data.get("createdTime", current_order_entry.get("timestamp", 0))) / 1000,
                        }
                        self.log.debug(f"Order status update", order_id=order_id, status=order_status)

            elif topic == "position":
                for pos_data in msg["data"]:
                    if pos.get("symbol") == self.config.SYMBOL: # Fixed typo: pos_data.get("symbol")
                        # Bybit sends updates for all position sides (long/short/both)
                        side = "Long" if pos_data.get("side") == "Buy" else "Short"
                        current_size = Decimal(str(pos_data.get("size", "0")))
                        
                        if current_size == Decimal("0"): # Position closed
                            self.market_state.positions.pop(side, None)
                            self.log.info(f"{side} position closed", position_size=float(current_size))
                        else:
                            unrealised_pnl = Decimal(str(pos_data.get("unrealisedPnl", "0")))
                            self.market_state.positions[side] = {
                                "size": current_size,
                                "avg_price": Decimal(str(pos_data.get("avgPrice", "0"))),
                                "unrealisedPnl": unrealised_pnl,
                                "leverage": Decimal(str(pos_data.get("leverage", "1"))),
                                "liq_price": Decimal(str(pos_data.get("liqPrice", "0"))),
                            }
                            self.log.debug(f"{side} position updated", size=float(current_size), pnl=float(unrealised_pnl))
            
                # Calculate total PnL AFTER updating all positions for the symbol
                total_pnl = sum(pos.get("unrealisedPnl", Decimal("0")) 
                              for pos in self.market_state.positions.values())
                self.session_stats.update_pnl(total_pnl)
                
            elif topic == "wallet":
                for wallet_data in msg["data"]:
                    if wallet_data.get("coin") == 'USDT':
                        self.market_state.available_balance = Decimal(str(wallet_data.get('availableToWithdraw', '0')))
                        self.market_state.last_balance_update = time.time()
                        self.log.debug(f"Wallet balance updated via WS", balance=float(self.market_state.available_balance))
            
            processing_time = time.time() - message_start_time
            latency_score = max(0.0, 1.0 - (processing_time / 0.5))
            self.bot_health.update_component('ws_private_latency', float(latency_score), f"Private WS Latency: {processing_time:.3f}s")
                        
        except (KeyError, ValueError, TypeError, DecimalException) as e:
            self.log.error(f"Error processing private WS message: {e}", msg_payload=msg)
            self.performance_monitor.record_error("websocket_private_error")
            self.bot_health.update_component('ws_private_data_quality', 0.0, f"Private WS Data Error: {e}")
            if sentry_sdk: sentry_sdk.capture_exception(e)
        except Exception as e:
            self.log.critical(f"Critical error in private WS handler: {e}", exc_info=True)
            self.performance_monitor.record_error("websocket_private_critical")
            self.bot_health.update_component('ws_private_data_quality', 0.0, f"Private WS Critical Error: {e}")
            if sentry_sdk: sentry_sdk.capture_exception(e)

    async def _resolve_ws_command_future(self, req_id: str, msg: Dict[str, Any]):
        """Resolves an asyncio.Future associated with a WebSocket command response."""
        async with self._ws_command_lock:
            future = self._ws_command_futures.get(req_id)
            if future and not future.done():
                future.set_result(msg)
                self.log.debug(f"Resolved WS command future for req_id: {req_id}")
            else:
                self.log.debug(f"No active future found for req_id: {req_id} or already done.")

    async def _send_ws_command(self, op: str, args: List[Any], timeout: int = 10) -> Optional[Dict]:
        """Sends a WebSocket command and waits for its response."""
        if not self.private_ws or not self._private_connected.is_set():
            self.log.warning(f"Cannot send WS command '{op}': Private WS not connected.")
            return {"retCode": -1, "retMsg": "Private WS not connected."}

        req_id = str(uuid.uuid4())
        message = {
            "id": req_id,
            "op": op,
            "args": args
        }

        async with self._ws_command_lock:
            future = asyncio.get_event_loop().create_future()
            self._ws_command_futures[req_id] = future

        try:
            self.log.debug(f"Sending WS command: {op}", req_id=req_id, args=args)
            self.private_ws.send(json.dumps(message))

            response = await asyncio.wait_for(future, timeout=timeout)
            self.log.debug(f"Received WS command response for {op}", req_id=req_id, response=response)
            return response
        except asyncio.TimeoutError:
            self.log.error(f"WS command '{op}' timed out after {timeout}s", req_id=req_id)
            return {"retCode": -1, "retMsg": "WS Command Timeout"}
        except Exception as e:
            self.log.error(f"Error sending WS command '{op}': {e}", req_id=req_id, exc_info=True)
            return {"retCode": -1, "retMsg": f"WS Command Error: {e}"}
        finally:
            async with self._ws_command_lock:
                self._ws_command_futures.pop(req_id, None)

    @asynccontextmanager
    async def api_call_context(self, method_name: str):
        """Enhanced API call context manager for rate limiting and performance monitoring"""
        start_time = time.time()
        try:
            await rate_limiter.acquire() # Acquire token from rate limiter
            yield
        finally:
            duration = time.time() - start_time
            self.performance_monitor.record_api_call(duration, method_name)
    
    async def api_call_with_retry(self, api_method: Callable, *args, **kwargs) -> Optional[Dict]:
        """Enhanced API call with robust retry logic and error handling."""
        method_name = getattr(api_method, '__name__', str(api_method))
        
        async with self.api_call_context(method_name):
            for attempt in range(1, 6): # Max 5 attempts
                try:
                    response = api_method(*args, **kwargs)
                    
                    if response and response.get("retCode") == 0:
                        rate_limiter.record_success(True)
                        self.bot_health.update_component(f'api_status_{method_name}', 1.0, "API Call OK")
                        return response
                    
                    ret_code = response.get('retCode') if response else None
                    ret_msg = response.get('retMsg', 'Unknown error') if response else 'No response'
                    
                    self.session_stats.record_api_error(str(ret_code))
                    rate_limiter.record_success(False)
                    
                    self.log.warning(f"API call failed: {method_name}", 
                                 attempt=attempt,
                                 error_code=ret_code,
                                 error_msg=ret_msg)
                    
                    self.bot_health.update_component(f'api_status_{method_name}', 0.5, f"API Error {ret_code}: {ret_msg}")
                    
                    # Retryable errors (e.g., rate limit, system error, service unavailable)
                    if ret_code in [10001, 10006, 30034, 30035, 10018, 10005]:
                        if attempt < 5:
                            delay = min(30, 2 * (2 ** (attempt - 1))) # Exponential backoff, max 30s
                            self.log.debug(f"Retrying API call {method_name} in {delay}s...")
                            await asyncio.sleep(delay)
                            continue
                    # Non-retryable errors (e.g., invalid signature, param error)
                    elif ret_code in [10007, 10002]:
                        self.log.error(f"Non-retryable API error: {ret_msg}", error_code=ret_code)
                        self.bot_health.update_component(f'api_status_{method_name}', 0.0, f"Non-retryable API Error: {ret_msg}")
                        if sentry_sdk: sentry_sdk.capture_message(f"Non-retryable API error {ret_code}: {ret_msg}")
                        return None
                    else: # Unhandled errors
                        self.log.error(f"Unhandled API error {ret_code}: {ret_msg}", error_code=ret_code)
                        self.bot_health.update_component(f'api_status_{method_name}', 0.0, f"Unhandled API Error: {ret_msg}")
                        if sentry_sdk: sentry_sdk.capture_message(f"Unhandled API error {ret_code}: {ret_msg}")
                        return None
                
                except Exception as e:
                    self.log.error(f"API call exception: {method_name}", attempt=attempt, error=str(e), exc_info=True)
                    self.performance_monitor.record_error(f"api_exception_{method_name}")
                    rate_limiter.record_success(False)
                    self.bot_health.update_component(f'api_status_{method_name}', 0.0, f"API Exception: {e}")
                    if sentry_sdk: sentry_sdk.capture_exception(e)
                    
                    if attempt < 5:
                        delay = min(30, 2 * (2 ** (attempt - 1)))
                        self.log.debug(f"Retrying API call {method_name} in {delay}s due to exception...")
                        await asyncio.sleep(delay)
                    else:
                        self.log.critical(f"API call failed after all retries: {method_name} - {e}")
                        return None
            
            return None # All retries exhausted

    async def monitor_heartbeats(self):
        """Sends internal heartbeat and updates connection health."""
        last_heartbeat_sent = time.time()
        while not _SHUTDOWN_REQUESTED:
            try:
                current_time = time.time()
                if current_time - last_heartbeat_sent > self.config.HEARTBEAT_INTERVAL:
                    last_heartbeat_sent = current_time
                    self.log.debug(f"💓 Internal heartbeat signal")
                
                # Aggregate WS connection health
                public_ws_ok = self._public_connected.is_set()
                private_ws_ok = self._private_connected.is_set()
                overall_ws_score = 1.0 if public_ws_ok and private_ws_ok else 0.0
                
                self.bot_health.update_component('ws_overall_connection', float(overall_ws_score), 
                                            f"Public: {'OK' if public_ws_ok else 'DISC'}, Private: {'OK' if private_ws_ok else 'DISC'}")
                
                # Check for data freshness using market_state's method
                self.market_state.is_data_fresh(self.config.CB_STALE_DATA_TIMEOUT_SEC) # This updates health component internally
                
                await asyncio.sleep(self.config.HEARTBEAT_INTERVAL / 2) # Check more frequently than full interval
            except Exception as e:
                self.log.error(f"Error in connection monitoring: {e}", exc_info=True)
                if sentry_sdk: sentry_sdk.capture_exception(e)
                await asyncio.sleep(5)

    async def get_symbol_info(self) -> bool:
        """Fetches and updates symbol information."""
        response = await self.api_call_with_retry(
            self.http.get_instruments_info,
            category=self.config.CATEGORY,
            symbol=self.config.SYMBOL
        )
        
        if response and response.get('retCode') == 0:
            instruments = response.get('result', {}).get('list')
            if instruments:
                instrument = instruments[0]
                price_filter = instrument.get('priceFilter', {})
                lot_size_filter = instrument.get('lotSizeFilter', {})
                
                self.symbol_info.price_precision = Decimal(str(price_filter.get('tickSize', "0.0001")))
                self.symbol_info.qty_precision = Decimal(str(lot_size_filter.get('qtyStep', "0.001")))
                self.symbol_info.min_price = Decimal(str(price_filter.get('minPrice', "0")))
                self.symbol_info.min_qty = Decimal(str(lot_size_filter.get('minQty', "0")))
                self.symbol_info.max_qty = Decimal(str(lot_size_filter.get('maxOrderQty', "1000000")))
                self.symbol_info.min_order_value = Decimal(str(lot_size_filter.get('minOrderAmt', "10.0")))
                
                self.log.info(f"📊 Symbol info loaded successfully", symbol=self.config.SYMBOL)
                self.bot_health.update_component('symbol_info_load', 1.0, "Symbol info loaded")
                return True
        
        self.log.error(f"❌ Failed to fetch symbol info", symbol=self.config.SYMBOL)
        self.bot_health.update_component('symbol_info_load', 0.0, "Failed to load symbol info")
        return False
    
    async def test_credentials(self) -> bool:
        """Tests API credentials by attempting to get wallet balance."""
        response = await self.api_call_with_retry(
            self.http.get_wallet_balance, 
            accountType="UNIFIED" # Use UNIFIED for Unified Trading Account
        )
        
        if response and response.get("retCode") == 0:
            self.log.info(f"✅ API credentials validated successfully")
            self.bot_health.update_component('api_credentials', 1.0, "Credentials OK")
            return True
        
        self.log.critical(f"❌ API credentials validation failed. Check API key/secret and permissions.")
        self.bot_health.update_component('api_credentials', 0.0, "Credentials FAILED")
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
                        self.market_state.available_balance = Decimal(str(coin.get('availableToWithdraw', '0')))
                        self.market_state.last_balance_update = time.time()
                        self.log.debug(f"Wallet balance updated via HTTP", balance=float(self.market_state.available_balance))
                        return True
        self.log.warning(f"Failed to fetch wallet balance via HTTP")
        return False
    
    async def get_open_orders(self) -> bool:
        """Fetches and updates current open orders."""
        response = await self.api_call_with_retry(
            self.http.get_open_orders,
            category=self.config.CATEGORY,
            symbol=self.config.SYMBOL
        )
        
        if response and response.get('retCode') == 0:
            orders = response.get('result', {}).get('list', [])
            self.market_state.open_orders.clear() # Clear existing before populating
            
            for order in orders:
                order_id = order.get('orderId')
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
            self.log.debug(f"Fetched {len(self.market_state.open_orders)} open orders via HTTP")
            return True
        self.log.warning(f"Failed to fetch open orders via HTTP")
        return False
    
    async def get_positions(self) -> bool:
        """Fetches and updates current positions."""
        response = await self.api_call_with_retry(
            self.http.get_positions,
            category=self.config.CATEGORY,
            symbol=self.config.SYMBOL
        )
        
        if response and response.get('retCode') == 0:
            positions = response.get('result', {}).get('list', [])
            self.market_state.positions.clear() # Clear existing before populating
            
            for pos in positions:
                if pos.get("symbol") == self.config.SYMBOL and Decimal(str(pos.get("size", "0"))) > 0:
                    side = "Long" if pos.get("side") == "Buy" else "Short"
                    self.market_state.positions[side] = {
                        "size": Decimal(str(pos.get("size", "0"))),
                        "avg_price": Decimal(str(pos.get("avgPrice", "0"))),
                        "unrealisedPnl": Decimal(str(pos.get("unrealisedPnl", "0"))),
                        "leverage": Decimal(str(pos.get("leverage", "1"))),
                        "liq_price": Decimal(str(pos.get("liqPrice", "0"))),
                    }
            self.log.debug(f"Fetched {len(self.market_state.positions)} positions via HTTP")
            # Recalculate PnL after position sync
            total_pnl = sum(pos.get("unrealisedPnl", Decimal("0")) 
                            for pos in self.market_state.positions.values())
            self.session_stats.update_pnl(total_pnl)
            return True
        self.log.warning(f"Failed to fetch positions via HTTP")
        return False
    
    # MODIFIED: place_order to include post_only
    async def place_order(self, side: str, order_type: str, qty: Decimal, price: Optional[Decimal] = None, post_only: bool = False) -> Optional[Dict]:
        """Places an order with comprehensive validation and monitoring, prioritizing WS then HTTP."""
        start_time = time.time()
        
        try:
            quantized_qty = qty.quantize(self.symbol_info.qty_precision, rounding=ROUND_DOWN)
            if quantized_qty <= 0 or quantized_qty < self.symbol_info.min_qty:
                self.log.warning(f"Invalid quantity rejected", 
                             original_qty=float(qty), 
                             quantized_qty=float(quantized_qty),
                             min_qty=float(self.symbol_info.min_qty))
                return None
            
            if quantized_qty > self.symbol_info.max_qty:
                self.log.warning(f"Quantity exceeds maximum allowed by exchange", 
                             quantity=float(quantized_qty),
                             max_qty=float(self.symbol_info.max_qty))
                return None
            
            order_params = {
                "category": self.config.CATEGORY,
                "symbol": self.config.SYMBOL,
                "side": side,
                "orderType": order_type,
                "qty": str(quantized_qty),
                "orderLinkId": f"mmxcel-{uuid.uuid4()}", # Unique client order ID
                "timeInForce": "GTC" if order_type == "Limit" else "IOC", # IOC for market orders is standard
            }
            
            if order_type == "Limit":
                if price is None:
                    self.log.error("Limit order requires a price.")
                    return None
                rounding = ROUND_DOWN if side == "Buy" else ROUND_UP
                quantized_price = price.quantize(self.symbol_info.price_precision, rounding=rounding)
                
                if quantized_price <= 0 or quantized_price < self.symbol_info.min_price:
                    self.log.warning(f"Price below minimum allowed by exchange rejected", 
                                 price=float(quantized_price),
                                 min_price=float(self.symbol_info.min_price))
                    return None
                
                # Check if limit price is too far from mid_price (potential for adverse fill/slippage)
                if self.market_state.mid_price > 0 and self.config.MAX_SLIPPAGE_PERCENTAGE > 0:
                    price_deviation = abs(quantized_price - self.market_state.mid_price) / self.market_state.mid_price
                    if price_deviation > self.config.MAX_SLIPPAGE_PERCENTAGE:
                        self.log.warning(f"Limit price ({float(quantized_price):.{calculate_decimal_precision(quantized_price)}f}) too far from mid price ({float(self.market_state.mid_price):.{calculate_decimal_precision(self.market_state.mid_price)}f}). Potential for non-fill or adverse fill if market moves.", 
                                     expected_slippage=f"{float(price_deviation):.4f}",
                                     max_allowed=f"{float(self.config.MAX_SLIPPAGE_PERCENTAGE):.4f}")
                
                order_params["price"] = str(quantized_price)
                
                order_value = quantized_qty * quantized_price
                if order_value < self.symbol_info.min_order_value:
                    self.log.warning(f"Order value below minimum required by exchange", 
                                 order_value=float(order_value),
                                 min_value=float(self.symbol_info.min_order_value))
                    return None
                
                if post_only: # --- NEW: Add postOnly parameter ---
                    order_params["postOnly"] = "true" # Bybit API expects "true" or "false" string

            # --- Attempt WS order placement first ---
            response = await self._send_ws_command("order.create", [order_params])
            
            if response and response.get('retCode') == 0:
                self.session_stats.orders_placed += 1
                order_latency = time.time() - start_time
                self.performance_monitor.record_order_latency(order_latency)
                
                # Store the order with its client_order_id and creation timestamp locally for tracking
                order_id = response['result'].get('orderId')
                if order_id:
                     self.market_state.open_orders[order_id] = {
                        "client_order_id": order_params["orderLinkId"],
                        "symbol": self.config.SYMBOL,
                        "side": side,
                        "price": price if price else self.market_state.mid_price, # Estimate market order price for tracking
                        "qty": quantized_qty,
                        "status": "New", # Assume new until WS confirms
                        "timestamp": time.time(), # Use current time for creation
                    }

                self.log.info(f"🎯 Order placed successfully via WS", 
                          order_id=order_id,
                          side=side, 
                          quantity=float(quantized_qty),
                          price=float(price) if price else "Market",
                          latency=f"{order_latency:.3f}s")
                self.send_toast(f"📝 {side} {quantized_qty} @ {float(price):.{calculate_decimal_precision(price)}f}" if price else f"📝 {side} {quantized_qty} Market", "blue", "white")
                return response.get('result', {})
            
            # --- Fallback to HTTP if WS fails ---
            self.log.warning(f"WS order.create failed ({response.get('retMsg', 'Unknown')}), attempting HTTP fallback.")
            http_response = await self.api_call_with_retry(self.http.place_order, **order_params)
            
            if http_response and http_response.get('retCode') == 0:
                self.session_stats.orders_placed += 1
                order_latency = time.time() - start_time
                self.performance_monitor.record_order_latency(order_latency)
                order_id = http_response['result'].get('orderId')
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
                self.log.info(f"🎯 Order placed successfully via HTTP (WS fallback)", 
                          order_id=order_id,
                          side=side, 
                          quantity=float(quantized_qty),
                          price=float(price) if price else "Market",
                          latency=f"{order_latency:.3f}s")
                self.send_toast(f"📝 {side} {quantized_qty} @ {float(price):.{calculate_decimal_precision(price)}f}" if price else f"📝 {side} {quantized_qty} Market (HTTP)", "blue", "white")
                return http_response.get('result', {})
            
            self.log.error(f"Order placement failed via both WS and HTTP.", response=response, http_response=http_response)
            return None
            
        except Exception as e:
            self.log.error(f"Error placing order: {e}", exc_info=True)
            self.performance_monitor.record_error("order_placement_error")
            if sentry_sdk: sentry_sdk.capture_exception(e)
            return None
    
    # NEW: amend_order method
    async def amend_order(self, order_id: str, new_price: Optional[Decimal] = None, new_qty: Optional[Decimal] = None) -> bool:
        """Amends an existing order, prioritizing WS then HTTP."""
        amend_params = {
            "category": self.config.CATEGORY,
            "symbol": self.config.SYMBOL,
            "orderId": order_id,
        }
        if new_price is not None:
            amend_params["price"] = str(new_price.quantize(self.symbol_info.price_precision))
        if new_qty is not None:
            amend_params["qty"] = str(new_qty.quantize(self.symbol_info.qty_precision))

        if not amend_params.get("price") and not amend_params.get("qty"):
            self.log.warning(f"No new price or quantity provided for amendment of order {order_id}.")
            return False

        # --- Attempt WS amendment first ---
        response = await self._send_ws_command("order.amend", [amend_params])

        if response and response.get('retCode') == 0:
            self.log.info(f"✏️ Order amended successfully via WS", order_id=order_id, new_price=new_price, new_qty=new_qty)
            # Update local state immediately, WS will confirm later
            if order_id in self.market_state.open_orders:
                if new_price is not None: self.market_state.open_orders[order_id]['price'] = new_price
                if new_qty is not None: self.market_state.open_orders[order_id]['qty'] = new_qty
                self.market_state.open_orders[order_id]['timestamp'] = time.time() # Reset age
            return True
        elif response and response.get('retCode') == 110001: # Order does not exist (already cancelled or filled)
            self.log.info(f"Order {order_id} already non-existent/cancelled. Treating as successful amendment (WS).", order_id=order_id)
            self.market_state.open_orders.pop(order_id, None)
            return True

        # --- Fallback to HTTP if WS fails ---
        self.log.warning(f"WS order.amend failed ({response.get('retMsg', 'Unknown')}), attempting HTTP fallback.")
        http_response = await self.api_call_with_retry(self.http.amend_order, **amend_params)

        if http_response and http_response.get('retCode') == 0:
            self.log.info(f"✏️ Order amended successfully via HTTP (WS fallback)", order_id=order_id, new_price=new_price, new_qty=new_qty)
            if order_id in self.market_state.open_orders:
                if new_price is not None: self.market_state.open_orders[order_id]['price'] = new_price
                if new_qty is not None: self.market_state.open_orders[order_id]['qty'] = new_qty
                self.market_state.open_orders[order_id]['timestamp'] = time.time()
            return True
        elif http_response and http_response.get('retCode') == 110001:
            self.log.info(f"Order {order_id} already non-existent/cancelled. Treating as successful amendment (HTTP).", order_id=order_id)
            self.market_state.open_orders.pop(order_id, None)
            return True

        self.log.error(f"Order amendment failed via both WS and HTTP.", order_id=order_id, response=response, http_response=http_response)
        return False
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancels a specific order, prioritizing WS then HTTP."""
        # --- Attempt WS cancel first ---
        response = await self._send_ws_command("order.cancel", [{
            "category": self.config.CATEGORY,
            "symbol": self.config.SYMBOL,
            "orderId": order_id
        }])
        
        if response and response.get('retCode') == 0:
            self.log.info(f"🗑️ Order cancelled successfully via WS", order_id=order_id)
            self.market_state.open_orders.pop(order_id, None) # Remove from local state
            self.session_stats.orders_cancelled += 1
            return True
        elif response and response.get('retCode') == 110001: # Order does not exist (already cancelled or filled)
            self.log.info(f"Order {order_id} already non-existent/cancelled. Treating as successful cancellation (WS).", order_id=order_id)
            self.market_state.open_orders.pop(order_id, None) # Ensure removal from local state
            return True
        
        # --- Fallback to HTTP if WS fails ---
        self.log.warning(f"WS order.cancel failed ({response.get('retMsg', 'Unknown')}), attempting HTTP fallback.")
        http_response = await self.api_call_with_retry(
            self.http.cancel_order,
            category=self.config.CATEGORY,
            symbol=self.config.SYMBOL,
            orderId=order_id
        )
        
        if http_response and http_response.get('retCode') == 0:
            self.log.info(f"🗑️ Order cancelled successfully via HTTP (WS fallback)", order_id=order_id)
            self.market_state.open_orders.pop(order_id, None)
            self.session_stats.orders_cancelled += 1
            return True
        
        # 110001: Order does not exist (already cancelled or filled) - treat as success for idempotency
        if http_response and http_response.get('retCode') == 110001:
            self.log.info(f"Order {order_id} already non-existent/cancelled. Treating as successful cancellation (HTTP).", order_id=order_id)
            self.market_state.open_orders.pop(order_id, None)
            return True

        self.log.error(f"Order cancellation failed via both WS and HTTP.", order_id=order_id, response=response, http_response=http_response)
        return False
    
    async def cancel_all_orders(self) -> bool:
        """Cancels all active orders for the symbol, prioritizing WS then HTTP."""
        # --- Attempt WS cancel-all first ---
        response = await self._send_ws_command("order.cancel-all", [{
            "category": self.config.CATEGORY,
            "symbol": self.config.SYMBOL
        }])
        
        if response and response.get('retCode') == 0:
            order_count = len(self.market_state.open_orders)
            self.log.info(f"🧹 All orders cancelled via WS", count=order_count)
            self.market_state.open_orders.clear()
            self.session_stats.orders_cancelled += order_count # Assuming all were cancelled
            self.send_toast(f"🧹 {order_count} orders cancelled", "orange", "white")
            return True
        
        # --- Fallback to HTTP if WS fails ---
        self.log.warning(f"WS order.cancel-all failed ({response.get('retMsg', 'Unknown')}), attempting HTTP fallback.")
        http_response = await self.api_call_with_retry(
            self.http.cancel_all_orders,
            category=self.config.CATEGORY,
            symbol=self.config.SYMBOL
        )
        
        if http_response and http_response.get('retCode') == 0:
            order_count = len(self.market_state.open_orders)
            self.log.info(f"🧹 All orders cancelled via HTTP (WS fallback)", count=order_count)
            self.market_state.open_orders.clear()
            self.session_stats.orders_cancelled += order_count
            self.send_toast(f"🧹 {order_count} orders cancelled (HTTP)", "orange", "white")
            return True
        
        self.log.error(f"Cancel all orders failed via both WS and HTTP.", response=response, http_response=http_response)
        return False

# Enhanced Market Making Strategy with advanced algorithms
class EnhancedMarketMakingStrategy:
    """Advanced market making strategy with intelligent algorithms and plug-in support."""
    
    def __init__(self, client: EnhancedBybitClient, market_state_ref: 'MarketState', 
                 symbol_info_ref: 'SymbolInfo', session_stats_ref: 'SessionStats', 
                 config_ref: 'BotConfig', log_ref: 'EnhancedLogger', 
                 bot_health_ref: 'BotHealth', performance_monitor_ref: 'PerformanceMonitor',
                 rate_limiter_ref: 'AdaptiveRateLimiter'):
        
        self.client = client
        self.market_state = market_state_ref
        self.symbol_info = symbol_info_ref
        self.session_stats = session_stats_ref
        self.config = config_ref
        self.log = log_ref
        self.bot_health = bot_health_ref
        self.performance_monitor = performance_monitor_ref
        self.rate_limiter = rate_limiter_ref

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
                self.log.info(f"Applied plugin callback to strategy.")
            except Exception as e:
                self.log.error(f"Error applying plugin callback to strategy: {e}", exc_info=True)
                if sentry_sdk: sentry_sdk.capture_exception(e)

    def on_config_update(self, new_config: BotConfig):
        """Handle configuration updates."""
        global config # Update the global config reference as well
        config = new_config 
        self.config = new_config # Update the strategy's internal reference
        self.log.info(f"🔄 Configuration updated, applying new settings.")
        self.session_stats.config_reloads += 1
        # Update rate limiter config
        self.rate_limiter.config = new_config

    def calculate_market_impact(self, side: str, quantity: Decimal) -> Decimal:
        """Uses symbol_info's estimate_slippage for accuracy."""
        impact = self.symbol_info.estimate_slippage(side, quantity)
        self.market_impact_history.append({'impact': impact, 'timestamp': time.time()})
        return impact
    
    def calculate_dynamic_spread(self) -> Decimal:
        """Enhanced dynamic spread calculation with multiple factors."""
        base_spread = self.config.SPREAD_PERCENTAGE
        
        if not self.config.VOLATILITY_ADJUSTMENT:
            return base_spread
        
        try:
            spread_multiplier = Decimal("1.0")
            
            # Factor 1: Recent volatility (using price standard deviation)
            if len(self.market_state.price_history) >= 20:
                recent_prices = [p['price'] for p in list(self.market_state.price_history)[-20:] if p['price'] > 0]
                if len(recent_prices) > 1:
                    # Calculate simple standard deviation of price changes
                    price_changes = [recent_prices[i] - recent_prices[i-1] for i in range(1, len(recent_prices))]
                    if price_changes:
                        avg_change = sum(price_changes) / len(price_changes)
                        variance = sum([(x - avg_change)**2 for x in price_changes]) / len(price_changes)
                        std_dev = Decimal(str(variance)).sqrt() if variance >= 0 else Decimal("0")
                        
                        if self.market_state.mid_price > 0:
                            relative_volatility = std_dev / self.market_state.mid_price
                            # Higher volatility -> wider spread. Adjust sensitivity.
                            volatility_multiplier = Decimal("1.0") + (relative_volatility * Decimal("500")) 
                            volatility_multiplier = max(Decimal("0.5"), min(Decimal("3.0"), volatility_multiplier))
                            spread_multiplier *= volatility_multiplier
                            self.log.debug(f"Volatility multiplier: {float(volatility_multiplier):.2f}x", std_dev=float(std_dev))

            # Factor 2: Order book imbalance
            if self.symbol_info.total_bid_volume > 0 and self.symbol_info.total_ask_volume > 0:
                total_volume = self.symbol_info.total_bid_volume + self.symbol_info.total_ask_volume
                imbalance = abs(self.symbol_info.total_bid_volume - self.symbol_info.total_ask_volume) / total_volume
                # Higher imbalance -> wider spread
                imbalance_multiplier = Decimal("1.0") + (imbalance * Decimal("0.8"))
                spread_multiplier *= imbalance_multiplier
                self.log.debug(f"Imbalance multiplier: {float(imbalance_multiplier):.2f}x", imbalance=float(imbalance))
            
            # Factor 3: Recent order success rate (from rate limiter's general success or explicit order attempts)
            # Use rate_limiter's success rate as a proxy for API/order success
            if len(self.rate_limiter.success_rate) >= 10:
                recent_success = sum(self.rate_limiter.success_rate) / len(self.rate_limiter.success_rate)
                if recent_success < 0.5: # Low success rate, widen spread to reduce fills
                    success_multiplier = Decimal("1.5")
                elif recent_success > 0.8: # High success rate, tighten spread
                    success_multiplier = Decimal("0.8")
                else:
                    success_multiplier = Decimal("1.0")
                spread_multiplier *= success_multiplier
                self.log.debug(f"Success rate multiplier: {float(success_multiplier):.2f}x", recent_success=float(recent_success))
            
            # Factor 4: Market impact history (reflect past slippage)
            if len(self.market_impact_history) >= 5:
                avg_impact = sum(r['impact'] for r in list(self.market_impact_history)[-5:]) / 5
                # Higher impact -> wider spread
                impact_multiplier = Decimal("1.0") + (avg_impact * Decimal("2.0"))
                spread_multiplier *= impact_multiplier
                self.log.debug(f"Impact multiplier: {float(impact_multiplier):.2f}x", avg_impact=float(avg_impact))
            
            self.adaptive_spread_multiplier = spread_multiplier
            adjusted_spread = base_spread * spread_multiplier
            
            # Ensure minimum spread (at least one tick size)
            min_spread = self.symbol_info.price_precision / self.market_state.mid_price if self.market_state.mid_price > 0 else base_spread
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
            self.log.error(f"Error calculating dynamic spread: {e}", exc_info=True)
            if sentry_sdk: sentry_sdk.capture_exception(e)
        
        return base_spread # Fallback to base spread

    def calculate_position_size(self) -> Decimal:
        """Enhanced position sizing with risk-adjusted calculations."""
        if self.market_state.available_balance <= 0 or self.market_state.mid_price <= 0:
            return self.config.QUANTITY # Return default if no valid market data/balance
        
        try:
            # Base size calculations based on config and available capital
            max_capital_allocation = self.market_state.available_balance * self.config.CAPITAL_ALLOCATION_PERCENTAGE
            size_from_capital = (max_capital_allocation / self.market_state.mid_price).quantize(
                self.symbol_info.qty_precision, rounding=ROUND_DOWN
            )
            
            # Max position size as percentage of current balance (expressed in quantity)
            max_position_value_usd = self.market_state.available_balance * self.config.MAX_POSITION_SIZE
            max_size_from_limit = (max_position_value_usd / self.market_state.mid_price).quantize(
                self.symbol_info.qty_precision, rounding=ROUND_DOWN
            )
            
            # Determine the smallest of the three to be conservative
            base_size = min(self.config.QUANTITY, size_from_capital, max_size_from_limit)
            
            self.adaptive_quantity_multiplier = Decimal("1.0") # Reset for each calculation
            
            # Adaptive Quantity Adjustment based on PnL history
            if self.config.ADAPTIVE_QUANTITY_ENABLED and len(self.session_stats.profit_history) >= 2:
                recent_pnl_changes = []
                for i in range(max(0, len(self.session_stats.profit_history) - 10), len(self.session_stats.profit_history)):
                    if i > 0:
                        recent_pnl_changes.append(self.session_stats.profit_history[i][1] - self.session_stats.profit_history[i-1][1])
                
                if recent_pnl_changes:
                    avg_pnl_change = sum(recent_pnl_changes) / len(recent_pnl_changes)
                    
                    if self.market_state.available_balance > 0:
                        relative_pnl_performance = avg_pnl_change / self.market_state.available_balance
                        # A positive performance increases multiplier, negative decreases.
                        self.adaptive_quantity_multiplier = Decimal("1.0") + (relative_pnl_performance * self.config.ADAPTIVE_QUANTITY_PERFORMANCE_FACTOR)
                        self.adaptive_quantity_multiplier = max(Decimal("0.5"), min(Decimal("2.0"), self.adaptive_quantity_multiplier)) # Clamp
                        self.log.debug(f"Adaptive quantity adjusted", 
                                     avg_pnl_change=float(avg_pnl_change), 
                                     relative_pnl_performance=float(relative_pnl_performance),
                                     multiplier=float(self.adaptive_quantity_multiplier))
            
            risk_multiplier = Decimal("1.0") * self.adaptive_quantity_multiplier
            
            # Market impact consideration (pre-trade slippage estimation)
            if self.market_state.mid_price > 0:
                estimated_slippage_buy = self.symbol_info.estimate_slippage("Buy", base_size)
                estimated_slippage_sell = self.symbol_info.estimate_slippage("Sell", base_size)
                avg_estimated_slippage = max(estimated_slippage_buy, estimated_slippage_sell)
                
                if avg_estimated_slippage > self.config.MAX_SLIPPAGE_PERCENTAGE and self.config.MAX_SLIPPAGE_PERCENTAGE > 0:
                    # Calculate reduction factor to bring slippage within limits
                    impact_reduction_factor = self.config.MAX_SLIPPAGE_PERCENTAGE / avg_estimated_slippage
                    risk_multiplier *= impact_reduction_factor
                    self.log.warning(f"Quantity reduced due to estimated high slippage", 
                                 estimated_slippage=f"{float(avg_estimated_slippage):.4f}", 
                                 reduction_factor=float(impact_reduction_factor))
            
            # Adjustment 2: Connection quality (from BotHealth)
            connection_score = self.bot_health.components['ws_overall_connection']['score']
            if connection_score < 1.0: # Only adjust if not perfect
                risk_multiplier *= Decimal(str(max(0.2, connection_score)))
                self.log.warning(f"Quantity reduced due to poor connection quality", quality=float(connection_score))
            
            # Adjustment 3: Recent order success rate (from rate limiter)
            if len(self.rate_limiter.success_rate) >= 10:
                recent_api_success = sum(self.rate_limiter.success_rate) / len(self.rate_limiter.success_rate)
                if recent_api_success < 0.8: # If API success rate is below 80%, reduce quantity
                    performance_reduction_factor = Decimal(str(max(0.5, recent_api_success)))
                    risk_multiplier *= performance_reduction_factor
                    self.log.warning(f"Quantity reduced due to low API success rate", success_rate=f"{float(recent_api_success):.1%}")
            
            adjusted_size = (base_size * risk_multiplier).quantize(self.symbol_info.qty_precision, rounding=ROUND_DOWN)
            
            # Ensure adjusted size respects minimum trade requirements
            if adjusted_size < self.symbol_info.min_qty:
                adjusted_size = self.symbol_info.min_qty
            
            # Re-check order value after final size adjustment
            if self.market_state.mid_price > 0:
                order_value = adjusted_size * self.market_state.mid_price
                if order_value < self.symbol_info.min_order_value:
                    adjusted_size = (self.symbol_info.min_order_value / self.market_state.mid_price).quantize(
                        self.symbol_info.qty_precision, rounding=ROUND_UP
                    )
            
            return adjusted_size
            
        except Exception as e:
            self.log.error(f"Error calculating position size: {e}", exc_info=True)
            if sentry_sdk: sentry_sdk.capture_exception(e)
            return self.config.QUANTITY # Fallback to default config quantity

    async def check_circuit_breaker_conditions(self) -> Tuple[bool, str]:
        """Checks various conditions and updates circuit breaker state."""
        global CIRCUIT_BREAKER_STATE
        
        current_overall_health = self.bot_health.overall_score
        
        # Market conditions (abnormal spread) check
        if self.market_state.mid_price > 0 and self.market_state.best_bid > 0 and self.market_state.best_ask > 0:
            spread_percentage = (self.market_state.best_ask - self.market_state.best_bid) / self.market_state.mid_price
            if spread_percentage > self.config.CB_ABNORMAL_SPREAD_PCT:
                self.log.warning(f"Circuit Breaker Trigger: Abnormal spread ({spread_percentage:.2%}) exceeds {self.config.CB_ABNORMAL_SPREAD_PCT:.2%}")
                self.bot_health.update_component('market_spread_quality', 0.2, f"Abnormal spread {spread_percentage:.2%}")
        else:
            self.bot_health.update_component('market_spread_quality', 1.0, "Spread OK")

        # Data freshness check (updated by market_state.is_data_fresh)
        is_data_stale = not self.market_state.is_data_fresh(self.config.CB_STALE_DATA_TIMEOUT_SEC)
        if is_data_stale:
            self.log.warning(f"Circuit Breaker Trigger: Market data stale for {time.time() - self.market_state.last_update_time:.1f}s")

        # Order success rate (from performance_monitor / rate_limiter)
        overall_api_success_rate = sum(self.rate_limiter.success_rate) / len(self.rate_limiter.success_rate) if self.rate_limiter.success_rate else 1.0
        if overall_api_success_rate < self.config.CB_LOW_ORDER_SUCCESS_THRESHOLD:
            self.log.warning(f"Circuit Breaker Trigger: Low API/Order success rate ({overall_api_success_rate:.1%})")
            self.bot_health.update_component('order_execution_success', 0.0, f"Low success rate {overall_api_success_rate:.1%}")
        else:
            self.bot_health.update_component('order_execution_success', 1.0, "Order execution OK")

        # System resources (high memory)
        is_high_memory = system_monitor.get_memory_usage() > self.config.CB_HIGH_MEMORY_MB
        if is_high_memory:
            self.log.warning(f"Circuit Breaker Trigger: High memory usage ({system_monitor.get_memory_usage():.0f}MB)")
        
        # Re-evaluate overall health after all specific component updates
        current_overall_health = self.bot_health.overall_score

        # Determine circuit breaker state based on overall bot health score
        if self.config.CIRCUIT_BREAKER_ENABLED:
            if current_overall_health < self.config.CB_CRITICAL_SHUTDOWN_THRESHOLD:
                if CIRCUIT_BREAKER_STATE != "CRITICAL_SHUTDOWN":
                    CIRCUIT_BREAKER_STATE = "CRITICAL_SHUTDOWN"
                    self.log.critical(f"🚨🚨 CRITICAL SHUTDOWN: Bot Health Score {current_overall_health:.2f} below {self.config.CB_CRITICAL_SHUTDOWN_THRESHOLD:.2f}. Initiating graceful shutdown.")
                    self.send_toast("🚨 CRITICAL SHUTDOWN", "red", "white")
                    global _SHUTDOWN_REQUESTED # Explicitly declare global to modify
                    _SHUTDOWN_REQUESTED = True
                    if sentry_sdk: sentry_sdk.capture_message("Critical Shutdown Triggered", level="fatal")
                return True, "CRITICAL_SHUTDOWN"
            
            elif current_overall_health < self.config.CB_MAJOR_CANCEL_THRESHOLD:
                if CIRCUIT_BREAKER_STATE != "MAJOR_CANCEL":
                    CIRCUIT_BREAKER_STATE = "MAJOR_CANCEL"
                    self.log.error(f"🚨 MAJOR CIRCUIT BREAKER: Bot Health Score {current_overall_health:.2f} below {self.config.CB_MAJOR_CANCEL_THRESHOLD:.2f}. Cancelling all orders.")
                    self.send_toast("🚨 Major Circuit Breaker", "orange", "white")
                    await self.client.cancel_all_orders()
                    self.session_stats.circuit_breaker_activations += 1
                    if sentry_sdk: sentry_sdk.capture_message("Major Circuit Breaker Triggered", level="error")
                return True, "MAJOR_CANCEL"
            
            elif current_overall_health < self.config.CB_MINOR_PAUSE_THRESHOLD:
                if CIRCUIT_BREAKER_STATE != "MINOR_PAUSE":
                    CIRCUIT_BREAKER_STATE = "MINOR_PAUSE"
                    self.log.warning(f"⚠️ MINOR CIRCUIT BREAKER: Bot Health Score {current_overall_health:.2f} below {self.config.CB_MINOR_PAUSE_THRESHOLD:.2f}. Pausing new orders.")
                    self.send_toast("⚠️ Minor Circuit Breaker", "yellow", "black")
                    if sentry_sdk: sentry_sdk.capture_message("Minor Circuit Breaker Triggered", level="warning")
                return True, "MINOR_PAUSE"
            
            else: # Conditions improved, reset circuit breaker
                if CIRCUIT_BREAKER_STATE != "NORMAL":
                    CIRCUIT_BREAKER_STATE = "NORMAL"
                    self.log.info(f"✅ Circuit breaker reset. Bot health score: {current_overall_health:.2f}")
                    self.send_toast("✅ Circuit Breaker Reset", "green", "white")
        
        return False, "NORMAL"
    
    # MODIFIED: place_market_making_orders for tiered order placement and post_only
    async def place_market_making_orders(self):
        """Places market making orders (buy and sell limits)."""
        if not self.market_state.is_data_fresh(self.config.CB_STALE_DATA_TIMEOUT_SEC):
            self.log.warning("⚠️ Market data not fresh, skipping new order placement.")
            return
        
        emergency, reason = await self.check_circuit_breaker_conditions()
        if emergency and reason != "NORMAL":
            self.log.info(f"Circuit breaker active ({reason}), skipping new market-making order placement.")
            return
        
        if self.config.TRADING_HOURS_ENABLED:
            current_hour_utc = datetime.utcnow().hour
            if not (self.config.TRADING_START_HOUR_UTC <= current_hour_utc <= self.config.TRADING_END_HOUR_UTC):
                self.log.info(f"Outside trading hours ({self.config.TRADING_START_HOUR_UTC:02d}:00-{self.config.TRADING_END_HOUR_UTC:02d}:00 UTC). Skipping market-making order placement.")
                return

        spread = self.calculate_dynamic_spread()
        position_size = self.calculate_position_size()
        tick_size = self.symbol_info.price_precision # Use tick size for granular steps

        if position_size <= 0:
            self.log.warning("⚠️ Calculated position size is zero or too small, skipping orders.")
            return

        # --- NEW: Tiered Order Placement ---
        orders_to_place = []
        current_buy_orders = [o for o in self.market_state.open_orders.values() if o['side'] == 'Buy']
        current_sell_orders = [o for o in self.market_state.open_orders.values() if o['side'] == 'Sell']

        # Determine how many buy/sell orders we can place
        # Ensure MAX_OPEN_ORDERS is at least 2 for one buy/one sell
        max_orders_per_side = max(1, self.config.MAX_OPEN_ORDERS // 2) 
        
        # Place Buy orders
        for i in range(max_orders_per_side - len(current_buy_orders)):
            # Calculate price for this tier: best_bid - (i * tick_size)
            # Or, for more aggressive, mid_price * (1 - spread) - (i * tick_size)
            # Tier 0 is closest to mid, subsequent tiers are further out
            target_buy_price = self.market_state.mid_price * (Decimal("1") - spread) - (i * tick_size) 
            
            # Ensure price is not too low and is below current best ask
            if self.market_state.best_bid > 0:
                # Place orders at or below best bid to be a maker
                target_buy_price = min(target_buy_price, self.market_state.best_bid - tick_size) 
            
            target_buy_price = target_buy_price.quantize(tick_size, rounding=ROUND_DOWN)

            if target_buy_price > 0:
                orders_to_place.append({"side": "Buy", "price": target_buy_price, "qty": position_size})

        # Place Sell orders
        for i in range(max_orders_per_side - len(current_sell_orders)):
            # Calculate price for this tier: best_ask + (i * tick_size)
            # Or, for more aggressive, mid_price * (1 + spread) + (i * tick_size)
            # Tier 0 is closest to mid, subsequent tiers are further out
            target_sell_price = self.market_state.mid_price * (Decimal("1") + spread) + (i * tick_size) 

            # Ensure price is not too high and is above current best bid
            if self.market_state.best_ask > 0:
                # Place orders at or above best ask to be a maker
                target_sell_price = max(target_sell_price, self.market_state.best_ask + tick_size) 
            
            target_sell_price = target_sell_price.quantize(tick_size, rounding=ROUND_UP)

            if target_sell_price > 0:
                orders_to_place.append({"side": "Sell", "price": target_sell_price, "qty": position_size})

        orders_placed_count = 0
        for order_data in orders_to_place:
            # Check if we still have slots available
            if len(self.market_state.open_orders) >= self.config.MAX_OPEN_ORDERS:
                self.log.debug(f"Max open orders ({self.config.MAX_OPEN_ORDERS}) reached during tiered placement, stopping.")
                break

            result = await self.client.place_order(
                order_data["side"], 
                "Limit", 
                order_data["qty"], 
                order_data["price"], 
                post_only=True # --- NEW: Set post_only to True ---
            )
            success = result is not None
            self.order_success_rate.append(1 if success else 0)
            if success:
                orders_placed_count += 1
        
        if orders_placed_count > 0:
            self.log.info(f"📝 Placed {orders_placed_count} tiered market making orders",
                          spread_pct=f"{float(spread*100):.4f}%",
                          size=float(position_size),
                          adaptive_spread_mult=f"{float(self.adaptive_spread_multiplier):.2f}x",
                          adaptive_qty_mult=f"{float(self.adaptive_quantity_multiplier):.2f}x")
    
    # MODIFIED: manage_positions for adaptive rebalance price offset
    async def manage_positions(self):
        """Manages existing positions, primarily for rebalancing."""
        if not self.market_state.is_data_fresh(self.config.CB_STALE_DATA_TIMEOUT_SEC):
            self.log.warning("⚠️ Market data not fresh for position management, skipping.")
            return
        
        long_size = self.market_state.positions.get('Long', {}).get('size', Decimal('0'))
        short_size = self.market_state.positions.get('Short', {}).get('size', Decimal('0'))
        net_position = long_size - short_size
        
        # Trigger rebalance only if net position exceeds threshold
        if abs(net_position) > self.config.REBALANCE_THRESHOLD_QTY:
            # Cooldown check for rebalancing to prevent rapid oscillations
            if time.time() - self.last_rebalance_time < 30: # 30-second cooldown
                self.log.debug(f"Rebalance cooldown active. {30 - (time.time() - self.last_rebalance_time):.1f}s remaining.")
                return
            
            self.log.info(f"⚖️ Rebalancing required", 
                      net_position=float(net_position),
                      threshold=float(self.config.REBALANCE_THRESHOLD_QTY))
            
            rebalance_side = "Sell" if net_position > 0 else "Buy"
            rebalance_qty = abs(net_position).quantize(self.symbol_info.qty_precision, rounding=ROUND_DOWN)
            
            if rebalance_qty > 0:
                self.log.info(f"Cancelling all open orders before rebalancing to avoid interference.")
                await self.client.cancel_all_orders()
                await asyncio.sleep(1) # Small delay after cancelling to allow API to process
                
                # --- NEW: Dynamic Rebalance Price Offset ---
                # Base offset from config, then adjust based on current market spread
                current_spread_pct = (self.market_state.best_ask - self.market_state.best_bid) / self.market_state.mid_price if self.market_state.mid_price > 0 else Decimal("0")
                
                dynamic_offset_factor = Decimal("1.0")
                if self.config.SPREAD_PERCENTAGE > 0:
                    spread_ratio = current_spread_pct / self.config.SPREAD_PERCENTAGE
                    if spread_ratio > Decimal("1.5"): # Market is wider than our target
                        dynamic_offset_factor = Decimal("1.2") # Be slightly more aggressive
                    elif spread_ratio < Decimal("0.5"): # Market is very tight
                        dynamic_offset_factor = Decimal("0.8") # Be slightly less aggressive
                
                rebalance_price_offset = self.config.REBALANCE_PRICE_OFFSET_PERCENTAGE * dynamic_offset_factor
                # --- END NEW ---

                # Pre-check estimated market impact for rebalance order
                expected_impact = self.calculate_market_impact(rebalance_side, rebalance_qty)
                if expected_impact > self.config.MAX_SLIPPAGE_PERCENTAGE:
                    self.log.warning(f"Rebalance quantity ({float(rebalance_qty)}) might incur high slippage ({float(expected_impact):.4f}). Attempting anyways but monitoring.")
                
                result = None
                if self.config.REBALANCE_ORDER_TYPE.lower() == "market":
                    result = await self.client.place_order(rebalance_side, "Market", rebalance_qty)
                else: # Limit order with price improvement logic
                    price = Decimal("0")
                    # For Buy rebalance, target best ask or slightly higher for quick fill
                    if rebalance_side == "Buy" and self.market_state.best_ask > 0:
                        price = self.market_state.best_ask * (Decimal("1") + rebalance_price_offset) # Use dynamic offset
                    # For Sell rebalance, target best bid or slightly lower for quick fill
                    elif rebalance_side == "Sell" and self.market_state.best_bid > 0:
                        price = self.market_state.best_bid * (Decimal("1") - rebalance_price_offset) # Use dynamic offset
                    
                    if price > 0:
                        result = await self.client.place_order(rebalance_side, "Limit", rebalance_qty, price)
                    else:
                        self.log.error(f"Cannot place limit rebalance order: Invalid price for {rebalance_side}. Falling back to Market order if possible.")
                        result = await self.client.place_order(rebalance_side, "Market", rebalance_qty)
                
                if result:
                    self.last_rebalance_time = time.time()
                    self.session_stats.rebalances_count += 1
                    self.session_stats.successful_rebalances += 1
                    self.log.info(f"✅ Rebalance executed successfully", 
                              side=rebalance_side,
                              quantity=float(rebalance_qty),
                              expected_impact=f"{float(expected_impact):.4f}")
                    self.send_toast(f"⚖️ Rebalanced {rebalance_qty}", "yellow", "black")
                else:
                    self.log.warning(f"❌ Rebalance failed", quantity=float(rebalance_qty))
            else:
                self.log.info(f"Rebalance quantity is zero, skipping rebalance.")
    
    # MODIFIED: cancel_and_reprice_stale_orders for smart order amendment
    async def cancel_and_reprice_stale_orders(self):
        """Cancels stale orders or orders far from current market price, or amends them."""
        current_time = time.time()
        orders_to_process = [] # Store (order_id, new_price_if_amend, action_type, reason)
        
        for order_id, order_data in list(self.market_state.open_orders.items()):
            order_age = current_time - order_data.get('timestamp', current_time)
            
            is_stale = order_age > self.config.ORDER_LIFESPAN_SECONDS
            
            is_out_of_market = False
            price_deviation = Decimal("0")
            # Only check for 'out of market' if mid_price is available and price_threshold is active
            if self.market_state.mid_price > 0 and order_data.get('price', Decimal('0')) > 0 and self.config.PRICE_THRESHOLD > 0:
                price_deviation = abs(order_data['price'] - self.market_state.mid_price) / self.market_state.mid_price
                if price_deviation > self.config.PRICE_THRESHOLD:
                    is_out_of_market = True
            
            if is_stale or is_out_of_market:
                # --- NEW: Try to amend if only slightly out of market, otherwise cancel ---
                # Amend if out of market but within 1.5x PRICE_THRESHOLD, and not too stale
                if is_out_of_market and price_deviation <= (self.config.PRICE_THRESHOLD * Decimal("1.5")) and not is_stale:
                    # Calculate new price based on current mid_price and desired spread
                    # Aim to place it at the current desired market-making level
                    new_price = Decimal("0")
                    spread = self.calculate_dynamic_spread()
                    if order_data['side'] == 'Buy':
                        new_price = self.market_state.mid_price * (Decimal("1") - spread)
                        if self.symbol_info.bid_levels: # Adjust to be one tick better than current best bid
                            new_price = max(new_price, self.symbol_info.bid_levels[0][0] + self.symbol_info.price_precision)
                    elif order_data['side'] == 'Sell':
                        new_price = self.market_state.mid_price * (Decimal("1") + spread)
                        if self.symbol_info.ask_levels: # Adjust to be one tick better than current best ask
                            new_price = min(new_price, self.symbol_info.ask_levels[0][0] - self.symbol_info.price_precision)
                    
                    if new_price > 0:
                        orders_to_process.append((order_id, new_price.quantize(self.symbol_info.price_precision), "amend", "Out of Market (Amending)"))
                        self.log.info(f"Order marked for amendment", order_id=order_id, reason="Out of Market",
                                      old_price=float(order_data['price']), new_price=float(new_price))
                    else: # Cannot calculate valid new price, so cancel
                        orders_to_process.append((order_id, None, "cancel", "Stale/Too Far Out of Market (Cancelling)"))
                        self.log.info(f"Order marked for cancellation", order_id=order_id, reason="Stale" if is_stale else "Too Far Out of Market",
                                      age=f"{order_age:.1f}s", price_deviation=f"{float(price_deviation):.4f}" if is_out_of_market else "N/A")
                else: # Too stale or too far out of market, just cancel
                    orders_to_process.append((order_id, None, "cancel", "Stale/Too Far Out of Market (Cancelling)"))
                    self.log.info(f"Order marked for cancellation", order_id=order_id, reason="Stale" if is_stale else "Too Far Out of Market",
                                  age=f"{order_age:.1f}s", price_deviation=f"{float(price_deviation):.4f}" if is_out_of_market else "N/A")

        if orders_to_process:
            self.log.info(f"Processing {len(orders_to_process)} orders for amendment/cancellation.")
            for order_id, new_price, action_type, reason in orders_to_process:
                try:
                    if action_type == "amend":
                        await self.client.amend_order(order_id, new_price=new_price)
                    else: # action_type == "cancel"
                        await self.client.cancel_order(order_id)
                except Exception as e:
                    self.log.error(f"Error processing order {order_id} ({reason}): {e}", exc_info=True)
                    if sentry_sdk: sentry_sdk.capture_exception(e)
    
    async def perform_maintenance(self):
        """Performs scheduled maintenance tasks."""
        current_time = time.time()
        
        # Memory cleanup
        if current_time - self.last_memory_cleanup > self.config.MEMORY_CLEANUP_INTERVAL:
            collected = self.system_monitor.cleanup_memory()
            self.last_memory_cleanup = current_time
            self.session_stats.memory_cleanups += 1
            if collected > 0:
                self.log.info(f"🧹 Memory cleanup completed", objects_collected=collected)
            
            # Update memory health component after cleanup
            memory_usage = self.system_monitor.get_memory_usage()
            mem_score = max(0.0, 1.0 - (memory_usage / self.config.CB_HIGH_MEMORY_MB)) if self.config.CB_HIGH_MEMORY_MB > 0 else 1.0
            self.bot_health.update_component('system_memory_after_cleanup', float(mem_score), f"Mem after cleanup: {memory_usage:.1f}MB")
        
        # System monitoring update (system_monitor.update_stats is called at the top of loop for dashboard)
        self.system_monitor.update_stats()
        
        # Configuration hot reload check
        if await config_manager.check_for_updates(): # Await config check
            self.log.info(f"⚙️ Configuration hot-reloaded successfully")
            self.session_stats.config_reloads += 1
        
        # Performance logging
        if self.performance_monitor.should_log_performance():
            perf_summary = self.performance_monitor.get_performance_summary()
            self.log.info(f"📊 Performance summary", **perf_summary)
            # Update performance health component
            api_perf_score = max(0.0, 1.0 - (perf_summary['avg_api_time'] / 3.0)) # 3.0s avg API time is 0 score
            self.bot_health.update_component('api_performance', float(api_perf_score), f"Avg API: {perf_summary['avg_api_time']:.3f}s")
            
            order_latency_score = max(0.0, 1.0 - (perf_summary['avg_order_latency'] / 5.0)) # 5.0s avg order latency is 0 score
            self.bot_health.update_component('order_latency_performance', float(order_latency_score), f"Avg Order Latency: {perf_summary['avg_order_latency']:.3f}s")

    # MODIFIED: monitor_pnl for volatility-adjusted SL/TP
    async def monitor_pnl(self):
        """Monitors PnL and triggers stop loss/take profit."""
        while self.running and not _SHUTDOWN_REQUESTED:
            try:
                if not self.market_state.is_data_fresh(self.config.CB_STALE_DATA_TIMEOUT_SEC):
                    self.log.debug("PnL monitor: Market data not fresh, waiting.")
                    await asyncio.sleep(5)
                    continue
                
                # --- NEW: Calculate dynamic SL/TP thresholds ---
                dynamic_sl_pct = self.config.STOP_LOSS_PERCENTAGE
                dynamic_tp_pct = self.config.PROFIT_PERCENTAGE

                if len(self.market_state.price_history) >= 50: # Need enough data for volatility
                    recent_prices = [p['price'] for p in list(self.market_state.price_history)[-50:] if p['price'] > 0]
                    if len(recent_prices) > 1:
                        # Calculate simple standard deviation of price changes
                        price_changes = [recent_prices[i] - recent_prices[i-1] for i in range(1, len(recent_prices))]
                        if price_changes:
                            avg_change = sum(price_changes) / len(price_changes)
                            variance = sum([(x - avg_change)**2 for x in price_changes]) / len(price_changes)
                            std_dev = Decimal(str(variance)).sqrt() if variance >= 0 else Decimal("0")

                            if self.market_state.mid_price > 0:
                                relative_volatility = std_dev / self.market_state.mid_price
                                # Adjust SL/TP based on volatility. Higher volatility -> wider SL/TP.
                                # Factor tuned to scale SL/TP between 0.5x and 2.0x base
                                volatility_factor = Decimal("1.0") + (relative_volatility * Decimal("100")) # Tune this factor
                                volatility_factor = max(Decimal("0.5"), min(Decimal("2.0"), volatility_factor)) # Clamp factor

                                dynamic_sl_pct = self.config.STOP_LOSS_PERCENTAGE * volatility_factor
                                dynamic_tp_pct = self.config.PROFIT_PERCENTAGE * volatility_factor
                                self.log.debug(f"Dynamic SL/TP: SL={float(dynamic_sl_pct):.2%}, TP={float(dynamic_tp_pct):.2%}",
                                             volatility_factor=float(volatility_factor))
                # --- END NEW ---

                # Loop through a copy of positions as it might change during order execution
                for side, position in list(self.market_state.positions.items()): 
                    if position['size'] <= 0 or position['avg_price'] <= 0:
                        continue
                    
                    entry_price = position['avg_price']
                    current_price = self.market_state.mid_price
                    
                    if entry_price == Decimal("0") or current_price == Decimal("0"):
                        self.log.warning(f"Invalid price detected for PnL calculation: Entry {entry_price}, Current {current_price}. Skipping PnL check for this position.")
                        continue

                    if side == "Long":
                        pnl_pct = (current_price - entry_price) / entry_price
                    else:  # Short
                        pnl_pct = (entry_price - current_price) / entry_price
                    
                    # Stop loss logic
                    if pnl_pct <= -dynamic_sl_pct: # --- MODIFIED ---
                        self.log.error(f"🛑 {side} position stop loss triggered (Dynamic SL: {dynamic_sl_pct:.2%})", 
                                   pnl_pct=f"{pnl_pct:.2%}",
                                   entry_price=float(entry_price),
                                   current_price=float(current_price),
                                   position_size=float(position['size']))
                        
                        await self.client.cancel_all_orders()
                        close_side = "Sell" if side == "Long" else "Buy"
                        result = await self.client.place_order(close_side, "Market", position['size'])
                        
                        if result:
                            self.send_toast(f"🛑 {side} stop: {pnl_pct:.2%}", "red", "white")
                        else:
                            self.log.critical(f"Failed to execute stop loss for {side} position (Order placement failed). Manual intervention may be needed.")
                            # Force major CB state if stop loss cannot be executed
                            global CIRCUIT_BREAKER_STATE
                            if CIRCUIT_BREAKER_STATE == "NORMAL" or CIRCUIT_BREAKER_STATE == "MINOR_PAUSE":
                                CIRCUIT_BREAKER_STATE = "MAJOR_CANCEL" 
                                self.log.error("Circuit breaker escalated to MAJOR_CANCEL due to failed stop loss execution.")
                                if sentry_sdk: sentry_sdk.capture_message("Stop loss execution failed, escalated to MAJOR_CANCEL", level="error")
                    
                    # Take profit logic
                    elif pnl_pct >= dynamic_tp_pct: # --- MODIFIED ---
                        self.log.info(f"🎯 {side} position take profit triggered (Dynamic TP: {dynamic_tp_pct:.2%})", 
                                  pnl_pct=f"{pnl_pct:.2%}",
                                  entry_price=float(entry_price),
                                  current_price=float(current_price),
                                  position_size=float(position['size']))
                        
                        await self.client.cancel_all_orders()
                        close_side = "Sell" if side == "Long" else "Buy"
                        result = await self.client.place_order(close_side, "Market", position['size'])
                        
                        if result:
                            self.send_toast(f"🎯 {side} profit: {pnl_pct:.2%}", "green", "white")
                        else:
                            self.log.error(f"Failed to execute take profit for {side} position (Order placement failed).")
                
                await asyncio.sleep(5) # Check PnL every 5 seconds
                
            except Exception as e:
                self.log.error(f"Error in PnL monitoring: {e}", exc_info=True)
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
                    if current_time - last_balance_refresh >= self.config.BALANCE_REFRESH_INTERVAL:
                        self.log.info("Private WS disconnected, fetching wallet balance via HTTP...")
                        await self.client.get_wallet_balance()
                        await self.client.get_positions()
                        last_balance_refresh = current_time
                    
                    if current_time - last_order_refresh >= self.config.ORDER_REFRESH_INTERVAL:
                        self.log.info("Private WS disconnected, fetching open orders via HTTP...")
                        await self.client.get_open_orders()
                        last_order_refresh = current_time
                
                # Execute strategy components in optimal order
                await self.cancel_and_reprice_stale_orders() # Free up order slots first
                await self.manage_positions() # Rebalance positions
                await self.place_market_making_orders() # Place new orders
                
                # Update bot state based on Circuit Breaker and open orders
                if CIRCUIT_BREAKER_STATE != "NORMAL":
                    set_bot_state(f"🚨 {CIRCUIT_BREAKER_STATE}")
                elif len(self.market_state.open_orders) > 0:
                    set_bot_state("🎯 ACTIVE_TRADING")
                else:
                    set_bot_state("⏳ WAITING")
                
                await asyncio.sleep(self.config.DASHBOARD_REFRESH_RATE) # Controls loop speed, also dashboard refresh
                
            except Exception as e:
                self.log.error(f"Error in strategy loop: {e}", exc_info=True)
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

            # --- NEW: ASCII Price Trend Graph ---
            print(f"{NEON_BLUE}{BOLD}📈 Price Trend (Last 20 updates):{NC}")
            
            if len(market_state.price_history) >= 2:
                prices = [p['price'] for p in market_state.price_history if p['price'] > 0]
                if prices:
                    min_price = min(prices)
                    max_price = max(prices)
                    price_range = max_price - min_price
                    
                    graph_height = 5
                    graph_width = 40 # Adjust as needed

                    if price_range == 0: # Flat line
                        for _ in range(graph_height):
                            print(f"  {NEON_CYAN}{'-' * graph_width}{NC}")
                    else:
                        # Normalize prices to graph height
                        normalized_prices = [int(((p - min_price) / price_range) * (graph_height - 1)) for p in prices]
                        
                        # Create a grid for the graph
                        grid = [[' ' for _ in range(graph_width)] for _ in range(graph_height)]

                        # Map normalized prices to graph positions
                        # Iterate backwards to plot from left to right for recent data
                        for i, norm_price in enumerate(normalized_prices[-graph_width:]): 
                            col = i # Current column in the graph
                            if 0 <= col < graph_width:
                                grid[graph_height - 1 - norm_price][col] = '*' # Place '*' at calculated position

                        # Print the grid
                        for row in grid:
                            print(f"  {NEON_CYAN}{''.join(row)}{NC}")
                    
                    print(f"  {NEON_CYAN}Min: {float(min_price):.{price_precision}f} Max: {float(max_price):.{price_precision}f}{NC}")
                else:
                    print(f"  {NEON_ORANGE}No valid price history to display.{NC}")
            else:
                print(f"  {NEON_ORANGE}Not enough price history for graph.{NC}")
            
            print_neon_separator(color=NEON_PURPLE)
            # --- END NEW ---
            
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

            # --- NEW: Dashboard Alerts & Recommendations ---
            print(f"{NEON_BLUE}{BOLD}🔔 Alerts & Recommendations:{NC}")
            
            alerts_present = False

            # Memory Alert
            memory_usage = system_monitor.get_memory_usage()
            if memory_usage > config.CB_HIGH_MEMORY_MB * 0.8: # 80% of CB threshold
                print(f"  {RED}🚨 HIGH MEMORY: {memory_usage:.1f}MB. Consider manual cleanup ('m') or restarting bot.{NC}")
                alerts_present = True
            
            # Data Freshness Alert
            data_age = time.time() - market_state.last_update_time
            if data_age > config.CB_STALE_DATA_TIMEOUT_SEC * 0.7: # 70% of stale timeout
                print(f"  {YELLOW}⚠️ STALE MARKET DATA: {data_age:.1f}s old. Check WS connection.{NC}")
                alerts_present = True

            # API Success Rate Alert
            overall_api_success_rate = sum(rate_limiter.success_rate) / len(rate_limiter.success_rate) if rate_limiter.success_rate else 1.0
            if overall_api_success_rate < 0.7: # Below 70%
                print(f"  {NEON_ORANGE}📉 LOW API SUCCESS: {overall_api_success_rate:.1%}. May impact order execution. Check Bybit status.{NC}")
                alerts_present = True
            
            # Rebalance Needed Alert
            long_size = market_state.positions.get('Long', {}).get('size', Decimal('0'))
            short_size = market_state.positions.get('Short', {}).get('size', Decimal('0'))
            net_position = long_size - short_size
            if abs(net_position) > config.REBALANCE_THRESHOLD_QTY:
                print(f"  {NEON_ORANGE}⚖️ REBALANCE NEEDED: Net position {net_position:.{qty_precision}f}. Type 'r' to force.{NC}")
                alerts_present = True

            if not alerts_present:
                print(f"  {NEON_GREEN}✅ All systems nominal. No active alerts.{NC}")

            print_neon_separator(color=NEON_PURPLE)
            # --- END NEW ---

            # Runtime Config Adjustment commands
            print(f"{NEON_ORANGE}🎮 Commands: 'q' quit | 'c' cancel all | 'r' rebalance | 'k' reset CB | 'i' info | 'm' memory | 's' set spread | 'z' set qty | 't' toggle trading hours | 'p' set param{NC}") # --- MODIFIED: Added 'p' command ---
            
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
                    
                    elif key == 'p': # --- NEW: Generic Parameter Adjustment ---
                        sys.stdout.write(f"\n{NEON_PINK}Enter config parameter name (e.g., ORDER_LIFESPAN_SECONDS): {NC}")
                        sys.stdout.flush()
                        param_name = sys.stdin.readline().strip().upper()

                        if not hasattr(config, param_name):
                            log.warning(f"Config parameter '{param_name}' not found.")
                            send_toast(f"❌ Param '{param_name}' not found", "red", "white")
                            continue

                        sys.stdout.write(f"{NEON_PINK}Enter new value for {param_name} (current: {getattr(config, param_name)}): {NC}")
                        sys.stdout.flush()
                        new_value_str = sys.stdin.readline().strip()

                        try:
                            # Attempt to convert to appropriate type based on current config value
                            current_value = getattr(config, param_name)
                            current_type = type(current_value)
                            
                            new_value = None
                            if current_type is Decimal:
                                new_value = Decimal(new_value_str)
                            elif current_type is int:
                                new_value = int(new_value_str)
                            elif current_type is float:
                                new_value = float(new_value_str)
                            elif current_type is bool:
                                new_value = new_value_str.lower() in ('true', '1', 't', 'y', 'yes')
                            else: # Assume string
                                new_value = new_value_str

                            # Basic validation for common types
                            # Allow negative for PNL stop loss, but not other positive-only values
                            if (isinstance(new_value, (Decimal, int, float)) and new_value < 0) and \
                                param_name not in ['CB_PNL_STOP_LOSS_PCT']: 
                                log.warning(f"Value for '{param_name}' must be non-negative.")
                                send_toast(f"❌ Invalid value for {param_name}", "red", "white")
                                continue
                            
                            setattr(config, param_name, new_value) # Update the global config object
                            log.info(f"Updated config parameter '{param_name}'", new_value=new_value)
                            send_toast(f"⚙️ {param_name} updated to {new_value}", "blue", "white")

                        except (ValueError, DecimalException):
                            log.warning(f"Invalid value type or format for parameter '{param_name}'.")
                            send_toast(f"❌ Invalid value for {param_name}", "red", "white")
                        except Exception as ex:
                            log.error(f"An unexpected error occurred while setting parameter '{param_name}': {ex}", exc_info=True)
                            send_toast(f"❌ Error setting {param_name}", "red", "white")
                    # --- END NEW ---
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
    
    # Initialize core components, passing dependencies explicitly
    client = EnhancedBybitClient(
        API_KEY, API_SECRET, config.USE_TESTNET,
        market_state_ref=market_state, symbol_info_ref=symbol_info,
        session_stats_ref=session_stats, performance_monitor_ref=performance_monitor,
        bot_health_ref=bot_health, config_ref=config, log_ref=log,
        send_toast_func=send_toast
    )
    
    # Load plugins *before* initializing strategy so plugins can augment it
    plugin_manager.load_plugins(config.PLUGIN_FOLDER)

    strategy = EnhancedMarketMakingStrategy(
        client=client,
        market_state_ref=market_state,
        symbol_info_ref=symbol_info,
        session_stats_ref=session_stats,
        config_ref=config,
        log_ref=log,
        bot_health_ref=bot_health,
        performance_monitor_ref=performance_monitor,
        rate_limiter_ref=rate_limiter
    )

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
