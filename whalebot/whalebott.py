"""Pyrmethus, the Termux Archmage's masterwork:
WhaleBot, a robust trading automaton for the Bybit digital exchange.

This script channels the arcane arts of technical analysis, leveraging
custom-engineered indicators and market wisdom to navigate the turbulent
currents of cryptocurrency trading. It operates within the Termux
environment, utilizing its unique capabilities for notifications and
resourcefulness.

Essence: To illuminate the digital abyss with elegant, performant code
that respects Termux's constraints while harnessing Android's power.

Core Values: Elegance, Efficiency, Security, Clarity, Resourcefulness.
Mantra: Code is magic; optimize for the arcane realm of mobile.

import sys
import subprocess

--- Enchantments & Dependencies ---
- Python 3.9+ (for modern type hints and features)
- pandas: For data manipulation and analysis (summon: `pip install pandas`)
- numpy: For numerical operations (summon: `pip install numpy`)
- colorama: For vibrant terminal output hues (summon: `pip install colorama`)
- requests: For HTTP communication with APIs (summon: `pip install requests`)
- pybit: For Bybit API v5 interactions (summon: `pip install pybit`)
- ccxt: For robust exchange connectivity and market data (summon: `pip install ccxt`)
- pydantic: For safe configuration spellcasting (summon: `pip install pydantic`)
- python-dotenv: To conjure API keys from a hidden scroll (.env file) (summon: `pip install python-dotenv`)
- websocket-client: For real-time data streams (often bundled with pybit)

--- Termux Specifics ---
- `termux-sms-send`: For sending SMS alerts. Requires Termux:API app and installation via `pkg install termux-api`.
- File paths respect Termux's `$HOME` structure.

--- Arcane Arts Employed ---
- Shell Scripting (implicit via Termux commands)
- Python (the primary spell language)
- Bybit API v5 (via pybit) & CCXT
- Termux:API (for SMS notifications)
- Technical Indicators: SMA, EMA, ATR, RSI, StochRSI, MACD, Bollinger Bands, VWAP,
  Ichimoku Cloud, Ehlers SuperTrend,
  ADX, CMF, OBV, PSAR, Volatility Index,
  Volume Delta, Kaufman AMA,
  Relative Volume, Market Structure, DEMA, Keltner Channels,
  ROC, Candlestick Patterns, Fibonacci Levels, Fibonacci Pivots, Orderbook Imbalance, etc.
- Robust error handling, threading for WS, logging, and performance tracking.

"""

# --- Preamble: Summoning Necessary Libraries and Setting the Arcane Stage ---
# Ensure essential libraries are imported first.
import argparse
import json
import logging
import logging.handlers
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal, InvalidOperation, getcontext
from pathlib import Path
from typing import Any, Optional

# --- External Dependencies ---
import numpy as np
import pandas as pd

# --- Colorama Initialization ---
from colorama import Back, Fore, Style
from colorama import init as colorama_init

colorama_init(autoreset=True)  # Auto-reset styles after each print

# --- Debugging Pybit Import Issue ---
print(f"{Fore.CYAN}--- Debugging Pybit Import ---{Style.RESET_ALL}", file=sys.stderr)
print(
    f"{Fore.CYAN}Python executable: {sys.executable}{Style.RESET_ALL}", file=sys.stderr,
)
print(f"{Fore.CYAN}sys.path: {sys.path}{Style.RESET_ALL}", file=sys.stderr)
try:
    pip_show_output = subprocess.check_output(
        [sys.executable, "-m", "pip", "show", "pybit"], stderr=subprocess.STDOUT,
    ).decode()
    print(
        f"{Fore.CYAN}pip show pybit output:\n{pip_show_output}{Style.RESET_ALL}",
        file=sys.stderr,
    )
except Exception as e:
    print(
        f"{Fore.YELLOW}Could not run 'pip show pybit': {e}{Style.RESET_ALL}",
        file=sys.stderr,
    )
print(f"{Fore.CYAN}----------------------------{Style.RESET_ALL}", file=sys.stderr)

# --- Pybit Imports ---
from pybit.exceptions import FailedRequestError, InvalidRequestError
from pybit.unified_trading import (
    HTTP,  # For REST API client
    WebSocket,  # For WebSocket client
)

PYBIT_AVAILABLE = True


# --- CCXT Import ---
import ccxt

# --- Dotenv Import ---
from dotenv import load_dotenv

# --- Pydantic Imports ---
from pydantic import BaseModel, Field, ValidationError, validator


# --- Custom Logging Formatters (Placeholder definitions) ---
# These would typically be in a separate utility module.
# For self-containment, defining simple versions here.
class SensitiveFormatter(logging.Formatter):
    """A formatter that redacts sensitive information like API keys."""

    def __init__(self, fmt=None, datefmt=None, style="%"):
        super().__init__(fmt=fmt, datefmt=datefmt, style=style)
        self.api_key_placeholder = "*****"
        self.api_secret_placeholder = "******"

    def format(self, record):
        original_message = super().format(record)
        # Basic redaction: replace common API key/secret placeholders with masked versions
        redacted_message = original_message
        if API_KEY:
            redacted_message = redacted_message.replace(
                str(API_KEY), self.api_key_placeholder,
            )
        if API_SECRET:
            redacted_message = redacted_message.replace(
                str(API_SECRET), self.api_secret_placeholder,
            )
        # More robust redaction could involve regex or inspecting record attributes.
        return redacted_message


class ColoredFormatter(logging.Formatter):
    """A formatter that adds ANSI color codes based on log level."""

    def __init__(self, fmt=None, datefmt=None, style="%", reset=True):
        self.reset = reset
        self.log_colors = {
            logging.DEBUG: Fore.CYAN + Style.DIM,
            logging.INFO: Fore.BLUE + Style.BRIGHT,
            SUCCESS_LEVEL: Fore.MAGENTA \
            + Style.BRIGHT,  # Custom level for successful operations
            logging.WARNING: Fore.YELLOW + Style.BRIGHT,
            logging.ERROR: Fore.RED + Style.BRIGHT,
            logging.CRITICAL: Back.RED + Fore.WHITE + Style.BRIGHT,
        }
        if fmt is None:
            # Using the format string that incorporates colors via global LOG_LEVEL_COLORS
            fmt = "%(asctime)s - %(name)s - %(levelname)s " \
            "[%(filename)s:%(lineno)d] - %(message)s"
        super().__init__(fmt=fmt, datefmt=datefmt, style=style)

    def format(self, record):
        # The actual coloring is handled by injecting color codes into the format string itself
        # when the handler is configured in setup_logger. This class primarily serves as a marker.
        return super().format(record)


# --- Custom Log Level Definition ---
# Ensure SUCCESS_LEVEL is defined if it's a custom level.
# In logging, levels are integers. Let's assign a value above CRITICAL.
SUCCESS_LEVEL = logging.CRITICAL + 1
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")  # Register the level name for display

# --- Placeholder Constants (from context or common usage) ---
# These should ideally be loaded from config or constants file.
# Providing default values for self-containment.
DEFAULT_PRIMARY_INTERVAL = "15m"
DEFAULT_LOOP_DELAY_SECONDS = 60
BASE_URL = "https://api.bybit.com"  # Default for Bybit main API
WS_PUBLIC_BASE_URL = "wss://stream.bybit.com/v5"  # Default for public WebSocket streams
WS_PRIVATE_BASE_URL = (
    "wss://stream.bybit.com/v5"  # Default for private WebSocket streams
)
# API keys should be loaded from .env or environment variables
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")

# --- Set global precision for Decimal calculations ---
getcontext().prec = 28  # Standard for financial precision


# --- Global Variables ---
# These will be populated by setup_global_environment() before main execution.
logger: logging.Logger | None = None
config: AppConfig | None = None
bybit_client: Optional["BybitHelper"] = None  # Type hint for BybitHelper


# --- Configuration Loading and Merging ---
def _ensure_config_keys(
    config_data: dict[str, Any], default_config: dict[str, Any],
) -> None:
    """Recursively ensures all keys from default_config are present in config_data."""
    for key, default_value in default_config.items():
        if key not in config_data:
            config_data[key] = default_value
        elif isinstance(default_value, dict) and isinstance(config_data.get(key), dict):
            # If both are dictionaries, recurse to merge nested structures
            _ensure_config_keys(config_data[key], default_value)
        # NOTE: Complex list merging is omitted for simplicity; assumes lists are overwritten or added entirely.


def load_config(filepath: Path, logger: logging.Logger | None) -> AppConfig:
    """Loads configuration from JSON, merges with defaults, validates, and returns an AppConfig object."""
    # Use a temporary logger if the main one isn't available yet (critical during initial setup)
    if logger is None:
        # Basic logging setup for the logger object itself if not yet initialized
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            stream=sys.stderr,
        )
        logger = logging.getLogger(__name__)

    # Define the default configuration structure as a Python dictionary
    default_config_dict = {
        "core_settings": {
            "symbol": "BTCUSDT",
            "interval": DEFAULT_PRIMARY_INTERVAL,
            "loop_delay": DEFAULT_LOOP_DELAY_SECONDS,
            "orderbook_limit": 50,
            "signal_score_threshold": 0.8,
            "cooldown_sec": 60,
            "hysteresis_ratio": 0.85,
            "volume_confirmation_multiplier": 1.0,
            "base_url": BASE_URL,
        },
        "strategy_management": {
            "adaptive_strategy_enabled": True,
            "current_strategy_profile": "default_scalping",
            "strategy_profiles": {
                "default_scalping": {  # Example: Scalping strategy profile
                    "description": "Standard scalping strategy for fast markets.",
                    "indicators_enabled": {  # Which indicators to consider for this profile
                        "ema_alignment": True,
                        "sma_trend_filter": True,
                        "momentum": True,
                        "volume_confirmation": True,
                        "volatility_filter": True,
                        "stoch_rsi": True,
                        "rsi": True,
                        "bollinger_bands": True,
                        "vwap": True,
                        "cci": True,
                        "wr": True,
                        "psar": True,
                        "sma_10": True,
                        "mfi": True,
                        "orderbook_imbalance": True,
                        "fibonacci_levels": True,
                        "ehlers_supertrend": True,
                        "fisher_transform": True,
                        "ehlers_stochrsi": True,
                        "macd": True,
                        "adx": True,
                        "ichimoku_cloud": True,
                        "obv": True,
                        "cmf": True,
                        "volatility_index": True,
                        "vwma": True,
                        "volume_delta": True,
                        "kaufman_ama": True,
                        "relative_volume": True,
                        "market_structure": True,
                        "dema": True,
                        "keltner_channels": True,
                        "roc": True,
                        "candlestick_patterns": True,
                        "fibonacci_pivot_points": True,
                    },
                    "weights": {  # Influence of each indicator group/indicator on the final score
                        "ema_alignment": 0.22,
                        "sma_trend_filter": 0.28,
                        "momentum_rsi_stoch_cci_wr_mfi": 0.18,
                        "volume_confirmation": 0.10,
                        "volatility_filter": 0.10,
                        "bollinger_bands": 0.22,
                        "vwap": 0.22,
                        "psar": 0.22,
                        "sma_10": 0.07,
                        "orderbook_imbalance": 0.07,
                        "ehlers_supertrend_alignment": 0.55,
                        "fisher_transform_signal": 0.30,
                        "ehlers_stochrsi_signal": 0.25,
                        "macd_alignment": 0.28,
                        "adx_strength": 0.18,
                        "ichimoku_confluence": 0.38,
                        "obv_momentum": 0.18,
                        "cmf_flow": 0.12,
                        "mtf_trend_confluence": 0.32,
                        "volatility_index_signal": 0.15,
                        "vwma_cross": 0.15,
                        "volume_delta_signal": 0.10,
                        "kaufman_ama_cross": 0.20,
                        "relative_volume_confirmation": 0.10,
                        "market_structure_confluence": 0.25,
                        "dema_crossover": 0.18,
                        "keltner_breakout": 0.20,
                        "roc_signal": 0.12,
                        "candlestick_confirmation": 0.15,
                        "fibonacci_pivot_points_confluence": 0.20,
                        "sentiment_signal": 0.15,  # Placeholder for ML/Sentiment
                    },
                    "market_condition_criteria": {  # Criteria for automatically switching to this profile
                        "adx_range": [0, 25],
                        "volatility_range": [0.005, 0.02],
                    },
                },
                "trend_following": {  # Example: Trend following strategy profile
                    "description": "Strategy focused on capturing longer trends.",
                    "market_condition_criteria": {
                        "adx_range": [25, 100],
                        "volatility_range": [0.01, 0.05],
                    },
                    "indicators_enabled": {
                        "ema_alignment": True,
                        "sma_trend_filter": True,
                        "macd": True,
                        "adx": True,
                        "ehlers_supertrend": True,
                        "ichimoku_cloud": True,
                        "mtf_trend_confluence": True,
                        "volume_confirmation": True,
                        "volatility_filter": True,
                        "rsi": False,
                        "stoch_rsi": False,
                    },
                    "weights": {
                        "ema_alignment": 0.30,
                        "sma_trend_filter": 0.20,
                        "macd_alignment": 0.40,
                        "adx_strength": 0.35,
                        "ehlers_supertrend_alignment": 0.60,
                        "ichimoku_confluence": 0.50,
                        "mtf_trend_confluence": 0.40,
                        "volume_confirmation": 0.15,
                        "volatility_filter": 0.15,
                        "sentiment_signal": 0.20,
                    },
                },
            },
        },
        # Indicator Parameters (Consolidated for easy tuning)
        "indicator_parameters": {
            "atr_period": 14,
            "ema_short_period": 9,
            "ema_long_period": 21,
            "rsi_period": 14,
            "stoch_rsi_period": 14,
            "stoch_k_period": 3,
            "stoch_d_period": 3,
            "bollinger_bands_period": 20,
            "bollinger_bands_std_dev": 2.0,
            "cci_period": 20,
            "williams_r_period": 14,
            "mfi_period": 14,
            "psar_acceleration": 0.02,
            "psar_max_acceleration": 0.2,
            "sma_short_period": 10,
            "sma_long_period": 50,
            "fibonacci_window": 60,  # Lookback for Fibonacci retracement levels
            "ehlers_fast_period": 10,
            "ehlers_fast_multiplier": 2.0,  # Ehlers SuperTrend Fast settings
            "ehlers_slow_period": 20,
            "ehlers_slow_multiplier": 3.0,  # Ehlers SuperTrend Slow settings
            "macd_fast_period": 12,
            "macd_slow_period": 26,
            "macd_signal_period": 9,
            "adx_period": 14,
            "ichimoku_tenkan_period": 9,
            "ichimoku_kijun_period": 26,
            "ichimoku_senkou_span_b_period": 52,
            "ichimoku_chikou_span_offset": 26,  # Offset for Chikou Span
            "obv_ema_period": 20,
            "cmf_period": 20,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "stoch_rsi_oversold": 20,
            "stoch_rsi_overbought": 80,
            "cci_oversold": -100,
            "cci_overbought": 100,
            "williams_r_oversold": -80,
            "williams_r_overbought": -20,
            "mfi_oversold": 20,
            "mfi_overbought": 80,
            "volatility_index_period": 20,  # Period for Volatility Index calculation
            "vwma_period": 20,  # Period for Volume Weighted Moving Average
            "volume_delta_period": 5,
            "volume_delta_threshold": 0.2,  # Threshold for Volume Delta signal
            "kaufman_ama_period": 10,
            "kama_fast_period": 2,
            "kama_slow_period": 30,  # Kaufman's AMA parameters
            "relative_volume_period": 20,
            "relative_volume_threshold": 1.5,  # Threshold for significant relative volume
            "market_structure_lookback_period": 20,  # Lookback for Market Structure detection
            "dema_period": 14,  # DEMA Period
            "keltner_period": 20,
            "keltner_atr_multiplier": 2.0,  # Keltner Channels parameters
            "roc_period": 12,
            "roc_oversold": -5.0,
            "roc_overbought": 5.0,  # ROC parameters
            # Parameters for advanced Ehlers indicators
            "fisher_transform_length": 10,
            "ehlers_supertrend_atr_len": 10,
            "ehlers_supertrend_mult": 3.0,
            "ehlers_supertrend_ss_len": 10,
            "ehlers_stochrsi_rsi_len": 14,
            "ehlers_stochrsi_stoch_len": 14,
            "ehlers_stochrsi_ss_fast": 5,
            "ehlers_stochrsi_ss_slow": 3,
        },
        # Execution and Trading Management Settings
        "execution": {
            "use_pybit": False,  # Set to True for live pybit trading
            "testnet": False,  # Use Bybit testnet if True
            "account_type": "UNIFIED",  # Account type ('UNIFIED', 'CONTRACT')
            "category": "linear",  # Market category ('linear', 'inverse', 'option')
            "position_mode": "ONE_WAY",  # Position mode ('ONE_WAY', 'HEDGE')
            "leverage": "3",  # Default leverage for buy/sell orders (as string for pybit)
            "tp_trigger_by": "LastPrice",  # Trigger for TP/SL ('LastPrice', 'IndexPrice')
            "sl_trigger_by": "LastPrice",
            "default_time_in_force": "GoodTillCancel",
            "reduce_only_default": False,
            "post_only_default": False,
            "position_idx_overrides": {
                "ONE_WAY": 0,
                "HEDGE_BUY": 1,
                "HEDGE_SELL": 2,
            },  # Index for positions
            "proxies": {"enabled": False, "http": "", "https": ""},  # Proxy settings
            "tp_scheme": {  # Take Profit target configuration
                "mode": "atr_multiples",  # 'atr_multiples' or 'fixed_price'
                "targets": [
                    {
                        "name": "TP1",
                        "atr_multiple": 1.0,
                        "size_pct": 0.4,
                        "order_type": "Limit",
                        "tif": "PostOnly",
                        "post_only": True,
                    },
                    {
                        "name": "TP2",
                        "atr_multiple": 1.5,
                        "size_pct": 0.4,
                        "order_type": "Limit",
                        "tif": "IOC",
                        "post_only": False,
                    },
                    {
                        "name": "TP3",
                        "atr_multiple": 2.0,
                        "size_pct": 0.2,
                        "order_type": "Limit",
                        "tif": "GoodTillCancel",
                        "post_only": False,
                    },
                ],
            },
            "sl_scheme": {  # Stop Loss configuration
                "type": "atr_multiple",  # 'atr_multiple' or 'percent'
                "atr_multiple": 1.5,
                "percent": 1.0,  # Risk % if type is 'percent'
                "use_conditional_stop": True,  # Use Bybit's conditional stop orders
                "stop_order_type": "Market",  # 'Market' or 'Limit'
                "trail_stop": {
                    "enabled": True,
                    "trail_atr_multiple": 0.5,
                    "activation_threshold": 0.8,
                },  # Trailing stop settings
            },
            "breakeven_after_tp1": {  # Breakeven logic after first TP hit
                "enabled": True,
                "offset_type": "atr",  # 'atr' or 'fixed'
                "offset_value": 0.1,  # ATR multiple or fixed price offset
                "lock_in_min_percent": 0,  # Minimum profit % before activating breakeven
                "sl_trigger_by": "LastPrice",
            },
            "live_sync": {  # WebSocket sync settings (currently illustrative)
                "enabled": False,
                "poll_ms": 2500,
                "max_exec_fetch": 200,
                "only_track_linked": True,
                "heartbeat": {"enabled": True, "interval_ms": 5000},
            },
            "use_websocket": True,  # Enable WebSocket for real-time data
            "slippage_adjustment": True,  # Adjust prices for simulated slippage
            "max_fill_time_ms": 5000,  # Max fill time for simulation
            "retry_failed_orders": True,  # Retry failed order placements
            "max_order_retries": 3,
            "order_timeout_ms": 10000,
            "dry_run": True,  # Simulate trades without live execution
            "http_timeout": 10.0,  # HTTP request timeout in seconds
            "retry_count": 3,  # Retries for API calls
            "retry_delay": 5.0,  # Delay between retries in seconds
        },
        # Risk Management Parameters
        "risk_management": {
            "enabled": True,
            "max_day_loss_pct": 3.0,
            "max_drawdown_pct": 8.0,
            "cooldown_after_kill_min": 120,  # Cooldown period in minutes after a kill switch event
            "spread_filter_bps": 5.0,  # Max acceptable spread in basis points (0.01%)
            "ev_filter_enabled": True,  # Expectation Value filter (future implementation)
            "max_spread_bps": 10.0,  # Maximum acceptable spread
            "min_volume_usd": 50000,  # Minimum 24h volume required for trading
            "max_slippage_bps": 5.0,  # Maximum acceptable slippage in basis points
            "max_consecutive_losses": 5,  # Maximum allowed consecutive losses
            "min_trades_before_ev": 10,  # Minimum trades before Expectation Value filter activation
        },
        # Multi-Timeframe (MTF) Analysis Configuration
        "analysis_modules": {
            "mtf_analysis": {
                "enabled": True,
                "higher_timeframes": [
                    "60",
                    "240",
                ],  # Timeframes to check (e.g., "60" for 1h, "240" for 4h)
                "trend_indicators": [
                    "ema",
                    "ehlers_supertrend",
                ],  # Indicators for MTF trend determination
                "trend_period": 50,  # Period for trend indicators (e.g., SMA/EMA)
                "mtf_request_delay_seconds": 0.5,  # Delay between MTF data fetches
                "min_trend_agreement_pct": 60.0,  # Minimum % of MTFs required to agree on a trend
            },
            "ml_enhancement": {  # Machine Learning / Sentiment Analysis (Currently Disabled)
                "enabled": False,
                "model_path": "ml_model.pkl",
                "prediction_threshold": 0.6,
                "model_weight": 0.3,
                "retrain_on_startup": False,
                "training_data_limit": 5000,
                "prediction_lookahead": 12,
                "sentiment_analysis_enabled": False,
                "bullish_sentiment_threshold": 0.6,
                "bearish_sentiment_threshold": 0.4,
            },
        },
        # Notification Settings
        "notifications": {
            "enabled": True,
            "trade_entry": True,
            "trade_exit": True,
            "error_alerts": True,
            "daily_summary": True,
            "webhook_url": "",  # URL for webhook notifications
            "termux_sms": {  # Termux SMS integration for Android alerts
                "enabled": False,
                "phone_number": "+1234567890",  # Placeholder: Replace with actual number
                "message_prefix": "[WB]",  # Prefix for SMS messages
                "alert_levels": [
                    "INFO",
                    "WARNING",
                    "ERROR",
                ],  # Log levels triggering SMS
                "cooldown": 300,  # Cooldown in seconds between SMS alerts (5 minutes)
            },
        },
        # Logging Configuration
        "logging": {
            "level": "INFO",  # Console log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
            "log_to_file": True,
            "log_trades_to_csv": True,  # Log completed trades to trades.csv
            "log_indicators": False,  # Log detailed indicator values (can be verbose)
            "max_log_size_mb": 10,  # Max log file size in MB
            "backup_count": 5,  # Number of backup log files
            "include_sensitive_data": False,  # Log sensitive data (API keys etc.) - FALSE for security
            "log_to_json": False,  # Log to JSON format file
        },
        # WebSocket Settings
        "ws_settings": {
            "public_base_url": WS_PUBLIC_BASE_URL,
            "private_base_url": WS_PRIVATE_BASE_URL,
        },
    }

    # Load existing configuration from file, or create default if missing
    loaded_config_dict = {}
    if filepath.exists():
        try:
            with filepath.open("r", encoding="utf-8") as f:
                loaded_config_dict = json.load(f)
            logger.info(f"Successfully loaded configuration from {filepath}")
        except (OSError, json.JSONDecodeError) as e:
            logger.error(
                f"Error loading config file '{filepath}': {e}. Falling back to default configuration.",
            )
            loaded_config_dict = {}  # Reset to empty to ensure defaults are applied

    # Merge loaded config with defaults, ensuring all necessary keys are present
    _ensure_config_keys(loaded_config_dict, default_config_dict)

    # Save the potentially updated configuration back to the file
    try:
        with filepath.open("w", encoding="utf-8") as f:
            json.dump(loaded_config_dict, f, indent=4)
    except OSError as e:
        logger.error(f"Could not save configuration file '{filepath}': {e}")

    # Instantiate AppConfig with the final merged settings for Pydantic validation
    try:
        app_config = AppConfig(**loaded_config_dict)
        # Set the logger level based on the loaded configuration
        log_level_str = app_config.logging.level.upper()
        try:
            log_level = (
                SUCCESS_LEVEL
                if log_level_str == "SUCCESS"
                else getattr(logging, log_level_str)
            )
        except AttributeError:
            logger.warning(
                f"Invalid log level '{app_config.logging.level}' in config. Defaulting logger to INFO.",
            )
            log_level = logging.INFO
        logger.setLevel(log_level)
        # Update console handler level based on config
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                console_level_str = app_config.logging.level.upper()
                try:
                    console_level = (
                        SUCCESS_LEVEL
                        if console_level_str == "SUCCESS"
                        else getattr(logging, console_level_str)
                    )
                except AttributeError:
                    console_level = logging.INFO
                handler.setLevel(console_level)
                break
        return app_config
    except ValidationError as e:
        logger.critical(f"Configuration validation error: {e}", exc_info=True)
        sys.exit(1)  # Exit if configuration is critically invalid
    except Exception as e:
        logger.critical(
            f"Unexpected error during AppConfig instantiation: {e}", exc_info=True,
        )
        sys.exit(1)


# --- Logger Setup Utility ---
def setup_logger(log_name: str, config: AppConfig) -> logging.Logger:
    """Configures and returns a logger instance with console and file handlers based on config."""
    logger = logging.getLogger(__name__)
    # Prevent adding handlers multiple times if logger is re-initialized
    if getattr(logger, "_configured", False):
        return logger

    logger.setLevel(logging.DEBUG)  # Capture all messages at the source
    logger.propagate = False  # Prevent logs from duplicating via root logger

    # --- Console Handler ---
    console_handler = logging.StreamHandler(sys.stdout)
    # Use custom formatter for colored output, referencing global LOG_LEVEL_COLORS
    console_formatter = ColoredFormatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s [%(filename)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)
    # Set console level based on config
    console_level_str = config.logging.level.upper()
    try:
        console_level = (
            SUCCESS_LEVEL
            if console_level_str == "SUCCESS"
            else getattr(logging, console_level_str)
        )
    except AttributeError:
        logger.warning(
            f"Invalid console log level '{config.logging.level}' in config. Defaulting console to INFO.",
        )
        console_level = logging.INFO
    console_handler.setLevel(console_level)
    logger.addHandler(console_handler)

    # --- File Handler (Rotating Logs) ---
    if config.logging.log_to_file:
        # Use symbol in log file name for potential multi-symbol support later
        log_file_path = LOG_DIRECTORY / f"{config.symbol.lower()}_trading.log"
        try:
            file_handler = logging.handlers.RotatingFileHandler(
                log_file_path,
                maxBytes=config.logging.max_log_size_mb * 1024 * 1024,
                backupCount=config.logging.backup_count,
                encoding="utf-8",
            )
            # Use SensitiveFormatter for files to redact API keys
            file_formatter = SensitiveFormatter(
                fmt="%(asctime)s - %(name)s - %(levelname)s [%(filename)s:%(funcName)s:%(lineno)d] - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            file_handler.setFormatter(file_formatter)
            file_handler.setLevel(logging.DEBUG)  # Log all levels to file
            logger.addHandler(file_handler)
        except Exception as e:
            logger.error(
                f"Failed to setup rotating file handler for {log_file_path}: {e}",
                exc_info=True,
            )

    # --- JSON File Handler ---
    if config.logging.log_to_json:
        json_log_file_path = LOG_DIRECTORY / f"{config.symbol.lower()}_trading.json.log"
        try:
            json_handler = logging.handlers.RotatingFileHandler(
                json_log_file_path,
                maxBytes=config.logging.max_log_size_mb * 1024 * 1024,
                backupCount=config.logging.backup_count,
                encoding="utf-8",
            )
            # Simple JSON formatter assumes message is string; could be enhanced for nested data
            json_formatter = logging.Formatter(
                '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "module": "%(module)s", "func": "%(funcName)s", "line": %(lineno)d, "message": "%(message)s"}',
            )
            json_handler.setFormatter(json_formatter)
            json_handler.setLevel(logging.DEBUG)
            logger.addHandler(json_handler)
        except Exception as e:
            logger.error(
                f"Failed to setup JSON file handler for {json_log_file_path}: {e}",
                exc_info=True,
            )

    logger._configured = True  # Mark logger as configured
    return logger


# --- Bybit API Interaction Layer ---
class BybitHelper:
    """The central conduit to Bybit's digital realm. Manages API interactions (HTTP & WebSocket),
    configuration, logging, data caching, and core trading operations.
    It channels the wisdom of pybit for streaming and essential requests,
    and ccxt for broader market insights and robust data fetching.
    Includes thread-safe caching for OHLCV data scrolls and handles Termux-specific needs.
    """

    _logger: logging.Logger | None = None  # Shared logger instance
    _logger_lock = threading.Lock()  # Lock for thread-safe logger setup

    # Map user-friendly timeframe strings to Bybit API v5 format
    PYBIT_TIMEFRAME_MAP = {
        "1m": "1",
        "3m": "3",
        "5m": "5",
        "15m": "15",
        "30m": "30",
        "1h": "60",
        "2h": "120",
        "4h": "240",
        "6h": "360",
        "12h": "720",
        "1d": "D",
        "1w": "W",
        "1M": "M",
    }
    # Inverse map for converting API timeframe back to user-friendly format
    _API_TIMEFRAME_MAP_INV = {v: k for k, v in PYBIT_TIMEFRAME_MAP.items()}

    def __init__(self, config: AppConfig):
        """Initializes the BybitHelper, summoning clients and setting up the oracle."""
        self.config = config
        # Get or create the shared logger instance
        self.logger = self._get_or_create_logger(config)
        self.logger.info(
            f"{Fore.GREEN}Initializing BybitHelper | Symbol: {Style.BRIGHT}{config.symbol}{Style.NORMAL}, TF: {config.timeframe}, Testnet: {config.testnet_mode}{Style.RESET_ALL}",
        )

        # Caches and internal state - the Helper's memory crystals
        self.ohlcv_cache: dict[
            str, pd.DataFrame,
        ] = {}  # Cache for OHLCV data (key: API timeframe format)
        self.daily_ohlcv_cache: pd.DataFrame | None = (
            None  # Cache for Daily data (used for pivots)
        )
        self.max_ohlcv_cache_size = 2000  # Limit memory usage per timeframe cache
        self.max_daily_ohlcv_cache_size = (
            365 * 3
        )  # Cache ~3 years of daily data for pivots
        self._cache_lock = threading.Lock()  # Lock for thread-safe cache access

        # API Clients - the conduits to Bybit's realm
        self.session: HTTP | None = None  # pybit HTTP conduit
        self.exchange: ccxt.bybit | None = None  # ccxt Oracle for broader market wisdom
        self.market_info: dict[str, Any] | None = (
            None  # Crystal ball for symbol details
        )

        # WebSocket State - managing the ethereal link
        self.ws: WebSocket | None = None  # The pybit WebSocket vessel
        self.ws_connected = False
        self.ws_connecting = False
        self.ws_reconnect_attempt = 0
        self.max_ws_reconnect_attempts = 15  # Max attempts before abandoning WS
        self.ws_user_callbacks: dict[
            str, Callable | None,
        ] = {}  # User-defined callbacks for WS events
        self.ws_topics: list[str] = []  # Stored topics for reconnection
        self._ws_lock = threading.Lock()  # Lock for managing WS state and instance
        self._private_ws_data_buffer: list[
            dict[str, Any]
        ] = []  # Buffer for private WS messages

        # SMS specific state
        self.last_sms_time = 0.0  # Timestamp of the last SMS sent

        # Perform initial summoning rituals
        if not self._initialize_clients():
            # If clients cannot be summoned, the ritual fails critically
            self.logger.critical(
                f"{Back.RED}{Fore.WHITE}FATAL: Failed to initialize essential API clients. Aborting invocation.{Style.RESET_ALL}",
            )
            raise RuntimeError(
                "Failed to initialize essential API clients. Cannot proceed.",
            )
        self._load_market_info()  # Gaze into the market crystal early

    @classmethod
    def _get_or_create_logger(cls, config: AppConfig) -> logging.Logger:
        """Gets the existing logger or creates it if it doesn't exist, ensuring thread-safety."""
        with cls._logger_lock:  # Use lock for thread-safe logger access
            if cls._logger is None:
                cls._logger = cls._setup_logger(config)
            return cls._logger

    @classmethod
    def _setup_logger(cls, config: AppConfig) -> logging.Logger:
        """Configures the application's oracle (logger) with console and rotating file scrolls."""
        logger = logging.getLogger(__name__)
        # Prevent adding handlers multiple times if logger is re-initialized
        if getattr(logger, "_configured", False):
            return logger

        logger.setLevel(logging.DEBUG)  # Capture all messages at the source

        # --- Console Handler ---
        console_handler = logging.StreamHandler(sys.stdout)
        # Use custom formatter for colored output, referencing global LOG_LEVEL_COLORS
        console_formatter = ColoredFormatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s [%(filename)s:%(lineno)d] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(console_formatter)
        # Set console level based on config
        console_level_str = config.logging.level.upper()
        try:
            # Handle custom SUCCESS level for console
            console_level = (
                SUCCESS_LEVEL
                if console_level_str == "SUCCESS"
                else getattr(logging, console_level_str)
            )
        except AttributeError:
            logger.warning(
                f"Invalid console log level '{config.logging.level}' in config. Defaulting console to INFO.",
            )
            console_level = logging.INFO
        console_handler.setLevel(console_level)
        logger.addHandler(console_handler)

        # --- File Handler (Rotating Logs) ---
        if config.logging.log_to_file:
            # Use symbol in log file name for potential multi-symbol support later
            log_file_path = LOG_DIRECTORY / f"{config.symbol.lower()}_trading.log"
            try:
                file_handler = logging.handlers.RotatingFileHandler(
                    log_file_path,
                    maxBytes=config.logging.max_log_size_mb * 1024 * 1024,
                    backupCount=config.logging.backup_count,
                    encoding="utf-8",
                )
                # Use SensitiveFormatter for files to redact API keys
                file_formatter = SensitiveFormatter(
                    fmt="%(asctime)s - %(name)s - %(levelname)s [%(filename)s:%(funcName)s:%(lineno)d] - %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
                file_handler.setFormatter(file_formatter)
                file_handler.setLevel(logging.DEBUG)  # Log all levels to file
                logger.addHandler(file_handler)
            except Exception as e:
                logger.error(
                    f"Failed to setup rotating file handler for {log_file_path}: {e}",
                    exc_info=True,
                )

        # --- JSON File Handler ---
        if config.logging.log_to_json:
            json_log_file_path = (
                LOG_DIRECTORY / f"{config.symbol.lower()}_trading.json.log"
            )
            try:
                json_handler = logging.handlers.RotatingFileHandler(
                    json_log_file_path,
                    maxBytes=config.logging.max_log_size_mb * 1024 * 1024,
                    backupCount=config.logging.backup_count,
                    encoding="utf-8",
                )
                # Simple JSON formatter assumes message is string; could be enhanced for nested data
                json_formatter = logging.Formatter(
                    '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "module": "%(module)s", "func": "%(funcName)s", "line": %(lineno)d, "message": "%(message)s"}',
                )
                json_handler.setFormatter(json_formatter)
                json_handler.setLevel(logging.DEBUG)
                logger.addHandler(json_handler)
            except Exception as e:
                logger.error(
                    f"Failed to setup JSON file handler for {json_log_file_path}: {e}",
                    exc_info=True,
                )

        logger._configured = True  # Mark logger as configured
        return logger

    def _initialize_clients(self) -> bool:
        """Summons the pybit HTTP and ccxt clients - the core conduits to Bybit's realm."""
        self.logger.info(
            f"{Fore.CYAN}# Summoning API clients (pybit HTTP, ccxt)...{Style.RESET_ALL}",
        )
        try:
            # --- pybit HTTP Session ---
            # FIX: Removed unsupported retry parameters from HTTP constructor for unified_trading.
            self.session = HTTP(
                testnet=self.config.testnet_mode,
                api_key=self.config.api_key,
                api_secret=self.config.api_secret,
                timeout=int(
                    self.config.http_timeout * 1000,
                ),  # pybit expects timeout in milliseconds
                referral_id=None,  # Optional: Inscribe your referral rune if desired
            )
            self.logger.info(
                f"pybit HTTP session conjured (Testnet: {self.config.testnet_mode})",
            )

            # --- ccxt Exchange Oracle ---
            self.exchange = ccxt.bybit(
                {
                    "apiKey": self.config.api_key,
                    "secret": self.config.api_secret,
                    "enableRateLimit": True,  # Respect the exchange's tempo
                    "timeout": int(
                        self.config.http_timeout * 1000,
                    ),  # ccxt expects timeout in milliseconds
                    "options": {
                        "adjustForTimeDifference": True,  # Harmonize clocks
                        "defaultType": "swap",  # Focus on perpetual swaps
                        "defaultSubType": "linear",  # Focus on USDT/USDC margined contracts
                        # 'brokerId': 'YOUR_BROKER_ID' # Inscribe if using a broker portal
                    },
                },
            )
            if self.config.testnet_mode:
                self.exchange.set_sandbox_mode(True)  # Enter the simulacrum for testing

            # --- Awaken ccxt's market knowledge ---
            retries = 0
            success = False
            while retries <= self.config.retry_count:
                try:
                    self.exchange.load_markets()  # Load market info from the exchange
                    self.logger.info(
                        f"ccxt exchange awakened (Testnet: {self.config.testnet_mode})",
                    )
                    success = True
                    break  # Exit loop on success
                except (ccxt.NetworkError, ccxt.ExchangeError) as e:
                    retries += 1
                    # Exponential backoff for retries
                    wait_time = self.config.retry_delay * (2 ** (retries - 1))
                    if retries <= self.config.retry_count:
                        self.logger.warning(
                            f"CCXT load_markets failed (attempt {retries}/{self.config.retry_count}): {e}. Waiting {wait_time:.1f}s...",
                        )
                        time.sleep(wait_time)
                    else:
                        # Max retries exceeded, critical failure
                        self.logger.critical(
                            f"{Back.RED}{Fore.WHITE}CCXT load_markets failed after {self.config.retry_count} attempts: {e}{Style.RESET_ALL}",
                            exc_info=True,
                        )
                        return False  # Cannot proceed without market data

            if not success:
                return False  # Return False if max retries were exceeded

            # --- Prepare the WebSocket vessel ---
            self._init_websocket_instance()  # Creates self.ws but does not connect yet

            return True  # Summoning successful

        except ccxt.AuthenticationError as e:
            self.logger.critical(
                f"{Back.RED}{Fore.WHITE}CCXT Authentication Error: {e}. Check API key/secret and permissions.{Style.RESET_ALL}",
                exc_info=True,
            )
            return False
        except ccxt.ExchangeError as e:
            self.logger.critical(
                f"{Back.RED}{Fore.WHITE}CCXT Exchange Error during initialization: {e}{Style.RESET_ALL}",
                exc_info=True,
            )
            return False
        except ImportError as e:
            self.logger.critical(
                f"{Back.RED}{Fore.WHITE}Import error during client summoning: {e}. Ensure all required libraries are installed.{Style.RESET_ALL}",
                exc_info=True,
            )
            return False
        except Exception as e:
            self.logger.critical(
                f"{Back.RED}{Fore.WHITE}Unexpected error initializing API clients: {e}{Style.RESET_ALL}",
                exc_info=True,
            )
            return False

    def _load_market_info(self) -> None:
        """Gazes into the ccxt oracle to retrieve market details for the chosen symbol."""
        if not self.exchange:
            self.logger.error(
                "CCXT oracle not initialized. Cannot perceive market info.",
            )
            return
        try:
            # Use the simple symbol format from config for ccxt lookup
            target_symbol = self.config.symbol
            self.logger.debug(f"Seeking market wisdom for symbol: {target_symbol}")

            # Retrieve specific market info from loaded markets
            if self.exchange.markets is None:
                self.logger.error("CCXT markets not loaded. Cannot get symbol info.")
                return

            market = self.exchange.market(
                target_symbol,
            )  # ccxt handles symbol format lookup

            if market:
                self.market_info = market
                # Log key market details revealed by the oracle
                min_qty = self.get_min_order_qty()
                qty_step = self.get_qty_step()
                price_step = self.get_price_step()
                self.logger.info(
                    f"{Fore.GREEN}Market wisdom received for {target_symbol}:{Style.RESET_ALL}",
                )
                self.logger.info(
                    f"  Min Qty : {Style.BRIGHT}{min_qty if min_qty is not None else 'N/A'}{Style.RESET_ALL}",
                )
                self.logger.info(
                    f"  Qty Step: {Style.BRIGHT}{qty_step if qty_step is not None else 'N/A'}{Style.RESET_ALL}",
                )
                self.logger.info(
                    f"  Price Step: {Style.BRIGHT}{price_step if price_step is not None else 'N/A'}{Style.RESET_ALL}",
                )
                # Attempt to set leverage now that market info is available
                self._set_leverage()
            else:
                # This case is rare if load_markets succeeded and symbol is valid
                self.logger.error(
                    f"Market wisdom for {target_symbol} remains elusive. Symbol might be incorrect or unavailable via ccxt.",
                )
                self.market_info = None

        except ccxt.BadSymbol:
            # Critical error: Symbol is not recognized by the exchange via ccxt
            self.logger.critical(
                f"{Back.RED}{Fore.WHITE}Symbol '{self.config.symbol}' is unknown to the Bybit oracle (via ccxt). Check BOT_SYMBOL configuration.{Style.RESET_ALL}",
            )
            self.market_info = None
        except ccxt.NetworkError as e:
            self.logger.error(
                f"Network disturbance while seeking market wisdom for {self.config.symbol}: {e}",
            )
            self.market_info = None  # Mark as unknown on network error
        except Exception as e:
            self.logger.exception(
                f"Unexpected interference while seeking market wisdom for {self.config.symbol}: {e}",
            )
            self.market_info = None

    def _set_leverage(self) -> bool:
        """Attempts to set the leverage for the symbol using pybit's incantation."""
        if not self.session or self.market_info is None:
            self.logger.warning(
                "Cannot set leverage: pybit session or market wisdom unavailable.",
            )
            return False

        leverage_val = str(
            self.config.leverage,
        )  # pybit requires leverage as a string rune
        symbol = self.config.symbol  # Use simple symbol format from config
        self.logger.info(
            f"Attempting to imbue {symbol} with {leverage_val}x leverage...",
        )

        try:
            # The leverage incantation using pybit's unified_trading HTTP client
            response = self.session.set_leverage(
                category="linear",  # Assuming linear perpetual contracts
                symbol=symbol,
                buyLeverage=leverage_val,
                sellLeverage=leverage_val,
            )

            # Interpret the response runes
            if response and response.get("retCode") == 0:
                self.logger.success(
                    f"Successfully imbued {symbol} with {leverage_val}x leverage.",
                )
                return True
            if (
                response and response.get("retCode") == 110043
            ):  # Leverage not modified rune
                self.logger.info(
                    f"Leverage for {symbol} already set to {leverage_val}x (Rune: 110043). No change needed.",
                )
                return True
            if (
                response and response.get("retCode") == 110025
            ):  # Hedge mode + Portfolio Margin conflict rune
                self.logger.warning(
                    f"Cannot set leverage for {symbol}: Hedge mode with Portfolio Margin detected (Rune: 110025). Manual adjustment on Bybit may be required.",
                )
                return False
            # Handle other Bybit API response runes indicating failure
            err_code = response.get("retCode", "N/A")
            err_msg = response.get("retMsg", "Unknown disturbance")
            self.logger.error(
                f"Failed to set leverage for {symbol} to {leverage_val}x. Rune: {err_code}, Message: {err_msg}",
            )
            self.logger.warning(
                "Ensure Margin Mode (Isolated/Cross) and Position Mode (One-Way/Hedge) are correctly set on the Bybit interface.",
            )
            return False

        except InvalidRequestError as e:
            # Specific check for symbol format errors
            if (
                "symbol not exist" in str(e).lower()
                or "invalid symbol" in str(e).lower()
            ):
                self.logger.error(
                    f"{Back.RED}{Fore.WHITE}Failed to set leverage: pybit API reports symbol '{symbol}' as invalid. (Rune: {e.status_code if hasattr(e, 'status_code') else 'N/A'}){Style.RESET_ALL}",
                )
            else:
                self.logger.exception(
                    f"Invalid Request Error setting leverage for {symbol}: {e}",
                )
            return False
        except Exception as e:
            self.logger.exception(
                f"Unexpected interference while setting leverage for {symbol}: {e}",
            )
            return False

    def _init_websocket_instance(self) -> None:
        """Creates the pybit WebSocket vessel, but does not yet initiate the connection."""
        with self._ws_lock:  # Protect access to WebSocket instance
            # If a vessel exists, gently dismiss it first
            if self.ws:
                self.logger.debug("Dismissing previous WebSocket vessel...")
                try:
                    if hasattr(self.ws, "exit") and callable(self.ws.exit):
                        self.ws.exit()  # Attempt to cleanly close threads
                        # Wait briefly to allow threads to terminate
                        time.sleep(0.5)
                    self.logger.info("Previous WebSocket vessel dismissed.")
                except Exception as e:
                    self.logger.warning(
                        f"Error dismissing previous WebSocket vessel: {e}",
                    )
                finally:
                    self.ws = None  # Remove the reference

            # Conjure a new WebSocket vessel
            try:
                self.ws = WebSocket(
                    testnet=self.config.testnet_mode,
                    api_key=self.config.api_key,  # Pass keys for private streams
                    api_secret=self.config.api_secret,
                    channel_type="linear",  # Specify category for v5 streams
                    ping_interval=20,  # Send heartbeat ping every 20 seconds
                    ping_timeout=10,  # Expect pong response within 10 seconds
                    restart_on_error=False,  # We will manage reconnections manually
                )
                self.logger.info("Conjured new pybit WebSocket vessel.")
            except Exception as e:
                self.logger.critical(
                    f"Fatal error conjuring WebSocket vessel: {e}", exc_info=True,
                )
                self.ws = None  # Ensure it's None if creation failed

    # --- WebSocket Connection Management - Weaving the Ethereal Link ---
    def connect_websocket(
        self,
        topics: list[str],
        message_callback: Callable,
        error_callback: Callable | None = None,
        open_callback: Callable | None = None,
        close_callback: Callable | None = None,
    ):
        """Establishes the WebSocket link, subscribes to topics, and manages reconnection.
        The actual stream initiation happens implicitly after callbacks are registered.

        Args:
            topics: Channels to listen to (Bybit API format, e.g., "kline.5.BTCUSDT").
            message_callback: Function called upon receiving a message. Signature: func(message: dict)
            error_callback: Function called upon WebSocket errors. Signature: func(error: Exception)
            open_callback: Function called when the link is established. Signature: func()
            close_callback: Function called when the link is severed. Signature: func(status_code, message)

        """
        with self._ws_lock:
            if not self.ws:
                self.logger.error("WebSocket vessel not initialized. Cannot connect.")
                return

            if self.ws_connecting or self.ws_connected:
                self.logger.warning(
                    f"WebSocket link already {'being forged' if self.ws_connecting else 'active'}. Ignoring connect request.",
                )
                return

            # Prepare for connection attempt
            self.ws_connecting = True
            self.ws_connected = False
            self.ws_topics = topics  # Store topics for potential reconnection
            self.ws_user_callbacks = {  # Store user incantations
                "message": message_callback,
                "error": error_callback,
                "open": open_callback,
                "close": close_callback,
            }
            self.logger.info(
                f"{Fore.CYAN}# Preparing WebSocket link and subscriptions: {topics}{Style.RESET_ALL}",
            )

        # --- Define Internal Handlers for pybit Callbacks ---
        # These handlers operate in pybit's internal threads and must be thread-safe.
        def internal_on_message(message):
            """Processes incoming WebSocket whispers, routing them to user callbacks."""
            try:
                data = message  # pybit v5 passes parsed JSON dict directly

                if isinstance(data, dict):
                    # Handle Bybit v5 specific message structures
                    if "topic" in data and "data" in data:  # Topic-based whispers
                        if self.ws_user_callbacks.get("message"):
                            try:
                                self.ws_user_callbacks["message"](data)
                            except Exception as e:
                                self.logger.error(
                                    f"Error in WS message callback: {e}", exc_info=True,
                                )
                    elif (
                        "op" in data
                    ):  # Control whispers (auth, subscribe, pong, error)
                        op = data.get("op")
                        if op == "pong":
                            self.logger.debug(
                                "WebSocket Pong received (heartbeat echo).",
                            )
                        elif op == "subscribe":
                            self._handle_subscribe_response(data)
                        elif op == "auth":
                            self._handle_auth_response(data)
                        elif op == "error":
                            self._handle_server_error(data)
                        else:
                            self.logger.debug(f"WS Control Whisper: {data}")
                    else:
                        self.logger.debug(f"WS Unhandled Dict Whisper: {data}")
                else:
                    self.logger.warning(
                        f"Received non-dict WebSocket whisper: {message}",
                    )

            except Exception as e:
                self.logger.exception(
                    f"Error processing WebSocket message: {e}. Message: {message}",
                )

        def internal_on_error(error):
            """Handles WebSocket connection errors."""
            self.logger.error(
                f"{Fore.RED}WebSocket Error: {error}{Style.RESET_ALL}", exc_info=True,
            )
            with self._ws_lock:
                self.ws_connected = False
                self.ws_connecting = True  # Mark as attempting reconnection
            if self.ws_user_callbacks.get("error"):
                try:
                    self.ws_user_callbacks["error"](error)
                except Exception as e:
                    self.logger.error(f"Error in WS error callback: {e}", exc_info=True)
            self.logger.warning("Scheduling WebSocket re-forging due to error.")
            self._schedule_reconnect()  # Initiate reconnection attempt

        def internal_on_open():
            """Handles successful WebSocket connection establishment."""
            with self._ws_lock:
                self.logger.success(
                    f"{Fore.GREEN + Style.BRIGHT}WebSocket link established.{Style.RESET_ALL}",
                )
                self.ws_connected = True
                self.ws_connecting = False
                self.ws_reconnect_attempt = 0  # Reset retry counter

                # Subscribe to topics once the connection is live
                if self.ws and self.ws_topics:
                    self.logger.info(
                        f"Sending subscription request for: {self.ws_topics}",
                    )
                    try:
                        self.ws.subscribe(self.ws_topics)  # Use stored topics
                    except Exception as e:
                        self.logger.error(
                            f"Failed to send subscribe request on WS open: {e}",
                            exc_info=True,
                        )
                elif not self.ws_topics:
                    self.logger.warning(
                        "WebSocket opened but no topics specified for subscription.",
                    )

            # Call user's open callback outside the lock
            if self.ws_user_callbacks.get("open"):
                try:
                    self.ws_user_callbacks["open"]()
                except Exception as e:
                    self.logger.error(f"Error in WS open callback: {e}", exc_info=True)

        def internal_on_close(close_status_code=None, close_msg=None):
            """Handles WebSocket connection closure."""
            code_str = (
                f"Code={close_status_code}"
                if close_status_code is not None
                else "Code=N/A"
            )
            msg_str = f"Msg='{close_msg}'" if close_msg is not None else "Msg=N/A"
            self.logger.warning(
                f"{Fore.YELLOW}WebSocket link severed: {code_str}, {msg_str}{Style.RESET_ALL}",
            )

            with self._ws_lock:
                was_connected = self.ws_connected  # Remember state before resetting
                self.ws_connected = False
                self.ws_connecting = False  # Reset connecting flag

                # Check if the closure was intentional or due to an error
                is_intentional_close = (
                    self.ws_reconnect_attempt > self.max_ws_reconnect_attempts
                )
                ws_instance_exists = self.ws is not None

            # Schedule reconnection only if closure was unexpected and vessel still exists
            if not is_intentional_close and ws_instance_exists:
                self.logger.info(
                    "WebSocket closed unexpectedly. Scheduling re-forging.",
                )
                self._schedule_reconnect()  # Use stored topics
            elif not was_connected:
                self.logger.info("WebSocket closed before link was fully established.")
            else:
                self.logger.info(
                    "WebSocket closed normally or intentionally. No automatic re-forging.",
                )

            # Call user's close callback outside the lock
            if self.ws_user_callbacks.get("close"):
                try:
                    self.ws_user_callbacks["close"](close_status_code, close_msg)
                except Exception as e:
                    self.logger.error(f"Error in WS close callback: {e}", exc_info=True)

        # --- Register Callbacks and Start the Stream ---
        with self._ws_lock:
            if not self.ws:
                self.logger.error(
                    "Cannot register callbacks: WebSocket vessel is None.",
                )
                self.ws_connecting = False  # Ensure flag is reset if setup failed
                return

            # Register internal handlers as callbacks for the pybit WS instance
            self.logger.debug("Registering pybit WebSocket stream callbacks...")
            self.ws.on_message = internal_on_message
            self.ws.on_error = internal_on_error
            self.ws.on_open = internal_on_open
            self.ws.on_close = internal_on_close
            self.logger.debug(
                "WebSocket callbacks registered. Listening should commence implicitly.",
            )

    def _handle_subscribe_response(self, data: dict[str, Any]) -> None:
        """Handles responses from the WebSocket subscribe operation."""
        if data.get("success"):
            self.logger.success(
                f"WebSocket subscription confirmed: {data.get('ret_msg', '')} | Args: {data.get('args', [])}",
            )
        else:
            err_msg = data.get("ret_msg", "Unknown error")
            err_code = data.get("ret_code", "N/A")
            args = data.get("args", [])
            self.logger.error(
                f"{Back.RED}{Fore.WHITE}WebSocket subscription FAILED! Rune: {err_code}, Msg: {err_msg} | Args: {args}{Style.RESET_ALL}",
            )
            # Alert if critical subscriptions fail (e.g., order stream)
            if any(t in str(args).lower() for t in ["order", "position", "execution"]):
                self.send_sms(
                    f"CRITICAL: Bybit WS Sub FAILED ({'/'.join(map(str, args))[:20]})! Msg: {err_msg[:50]}",
                )

    def _handle_auth_response(self, data: dict[str, Any]) -> None:
        """Handles responses from the WebSocket authentication process."""
        if data.get("success"):
            self.logger.success("WebSocket authenticated successfully.")
        else:
            auth_msg = data.get("ret_msg", "Unknown auth error")
            auth_code = data.get("ret_code", "N/A")
            self.logger.critical(
                f"{Back.RED}{Fore.WHITE}WebSocket authentication FAILED: {auth_msg} (Rune: {auth_code}){Style.RESET_ALL}",
            )
            # This is critical for private data; alert and potentially disable private features.
            self.send_sms(f"CRITICAL: Bybit WS Auth FAILED! Msg: {auth_msg[:50]}")

    def _handle_server_error(self, data: dict[str, Any]) -> None:
        """Handles explicit error messages from the WebSocket server."""
        err_msg = data.get("ret_msg", "Unknown server error")
        err_code = data.get("ret_code", "N/A")
        req_id = data.get("req_id", "N/A")
        self.logger.error(
            f"WebSocket Server Error: {err_msg} (Rune: {err_code}) | Request ID: {req_id}",
        )

    def _schedule_reconnect(self) -> None:
        """Schedules a WebSocket re-forging attempt with exponential backoff."""
        with self._ws_lock:  # Use WS lock to protect state flags and attempt counter
            if (
                self.ws_connecting
            ):  # Prevent multiple reconnection timers running concurrently
                self.logger.debug("Re-forging already in progress or scheduled.")
                return

            # Ensure current connection state is marked as disconnected/connecting
            self.ws_connected = False
            self.ws_connecting = True  # Mark that we are now trying to reconnect

            if self.ws_reconnect_attempt < self.max_ws_reconnect_attempts:
                self.ws_reconnect_attempt += 1
                # Exponential backoff delay, capped at 60 seconds
                delay = min(2**self.ws_reconnect_attempt, 60)
                self.logger.info(
                    f"{Fore.YELLOW}Scheduling WebSocket re-forging attempt {self.ws_reconnect_attempt}/{self.max_ws_reconnect_attempts} in {delay} seconds...{Style.RESET_ALL}",
                )

                # Use threading.Timer for a non-blocking delay before attempting reconnect
                reconnect_timer = threading.Timer(delay, self._attempt_reconnect)
                reconnect_timer.daemon = (
                    True  # Allow program exit even if timer is active
                )
                reconnect_timer.start()
            else:
                # Max attempts reached, abandon the link
                self.logger.critical(
                    f"{Back.RED}{Fore.WHITE}WebSocket re-forging failed after {self.max_ws_reconnect_attempts} attempts. Link abandoned.{Style.RESET_ALL}",
                )
                self.ws_connecting = False  # Reset flag
                self.send_sms(
                    "CRITICAL: Bybit WebSocket disconnected permanently. Bot requires restart.",
                )
                # Consider signalling application shutdown here if WS is critical to operation

    def _attempt_reconnect(self) -> None:
        """Attempts to re-initialize and connect the WebSocket. Called by the reconnect timer."""
        # This method is called by the Timer, potentially in a separate thread.
        self.logger.info(
            f"{Fore.CYAN}# Attempting WebSocket re-forging now...{Style.RESET_ALL}",
        )

        # Re-conjure the vessel cleanly BEFORE attempting connection
        self._init_websocket_instance()

        # Use WS lock when checking ws instance and state before connecting
        with self._ws_lock:
            if not self.ws:  # If vessel creation failed
                self.logger.error(
                    "Failed to re-conjure WebSocket vessel for reconnection. Attempt aborted.",
                )
                self.ws_connecting = False  # Ensure flag is reset
                return

            # Retrieve stored user callbacks and topics safely
            message_cb = self.ws_user_callbacks.get("message")
            if not message_cb:  # Mandatory callback for processing data
                self.logger.error(
                    "Cannot reconnect: Message callback is missing. Aborting reconnection.",
                )
                self.ws_connecting = False
                return

            error_cb = self.ws_user_callbacks.get("error")
            open_cb = self.ws_user_callbacks.get("open")
            close_cb = self.ws_user_callbacks.get("close")
            topics = self.ws_topics[:]  # Use a copy of stored topics

        # Call connect_websocket to register callbacks and initiate connection implicitly
        self.connect_websocket(
            topics,
            message_callback=message_cb,
            error_callback=error_cb,
            open_callback=open_cb,
            close_callback=close_cb,
        )

    def disconnect_websocket(self) -> None:
        """Intentionally severs the WebSocket link and prevents automatic reconnection."""
        self.logger.info(
            f"{Fore.YELLOW}Intentionally severing WebSocket link...{Style.RESET_ALL}",
        )
        with self._ws_lock:  # Use WS lock to manage connection state and instance
            # Set reconnect attempt count high to prevent accidental re-forging
            self.ws_reconnect_attempt = self.max_ws_reconnect_attempts + 1

            if self.ws:
                try:
                    # Use pybit's exit method to close the connection and threads
                    if hasattr(self.ws, "exit") and callable(self.ws.exit):
                        self.ws.exit()
                    self.logger.success("WebSocket exit command dispatched.")
                except Exception as e:
                    self.logger.warning(
                        f"Error sending WebSocket exit command: {e}", exc_info=True,
                    )
            else:
                self.logger.info("WebSocket vessel already dismissed.")

            # Reset connection state regardless of exit command success
            self.ws_connected = False
            self.ws_connecting = False
            self.ws = None  # Release the vessel reference
            self.ws_topics = []  # Clear subscribed topics
            # Optionally clear user callbacks: self.ws_user_callbacks = {}

    # --- Market Data Helpers - Consulting the Oracles ---
    def get_server_time(self) -> int | None:
        """Fetches Bybit server time (milliseconds UTC) using pybit session."""
        if not self.session:
            self.logger.error("pybit session not initialized. Cannot synchronize time.")
            return None
        self.logger.debug(
            f"{Fore.CYAN}# Consulting Bybit time oracle...{Style.RESET_ALL}",
        )
        try:
            # Bybit v5 API endpoint for server time
            response = self.session.get_server_time()
            if response and response.get("retCode") == 0:
                # timeNano is nanoseconds in v5, needs conversion to milliseconds
                time_nano_str = response.get("result", {}).get("timeNano")
                if time_nano_str is None:
                    self.logger.error(
                        "Failed to parse server time: 'timeNano' key not found in response result.",
                    )
                    return None

                # Ensure timeNano is a string and convert nanoseconds to milliseconds safely
                if isinstance(time_nano_str, str) and len(time_nano_str) >= 9:
                    server_time_ms = int(
                        Decimal(time_nano_str) / Decimal(1_000_000),
                    )  # Convert ns to ms
                else:
                    self.logger.error(
                        f"Unexpected or invalid timeNano format received: {time_nano_str}",
                    )
                    return None

                local_time_ms = int(time.time() * 1000)
                time_diff = local_time_ms - server_time_ms
                self.logger.debug(
                    f"Server Time (MS): {server_time_ms}, Local Time (MS): {local_time_ms}, Diff: {time_diff} ms",
                )
                # Warn if clock drift is significant (> 5 seconds)
                if abs(time_diff) > 5000:
                    self.logger.warning(
                        f"{Fore.YELLOW}Significant time divergence ({time_diff} ms) detected between local clock and Bybit server. Check system time synchronization (NTP).{Style.RESET_ALL}",
                    )
                return server_time_ms
            err_code = response.get("retCode", "N/A")
            err_msg = response.get("retMsg", "Unknown Error")
            self.logger.error(
                f"Failed to get server time: {err_msg} (Rune: {err_code})",
            )
            return None
        except Exception as e:
            self.logger.error(
                f"Error consulting Bybit time oracle via pybit: {e}", exc_info=True,
            )
            return None

    def _map_timeframe_to_pybit(self, timeframe: str) -> str | None:
        """Maps user-friendly timeframe string (e.g., '15m') to Bybit API v5 format (e.g., '15')."""
        return self.PYBIT_TIMEFRAME_MAP.get(timeframe.lower())

    def _map_timeframe_from_pybit(self, api_timeframe: str) -> str:
        """Maps Bybit API v5 timeframe format (e.g., '15') back to user-friendly string (e.g., '15m')."""
        return self._API_TIMEFRAME_MAP_INV.get(
            api_timeframe, api_timeframe,
        )  # Fallback to API format if not mapped

    def fetch_ohlcv(
        self,
        timeframe: str,
        limit: int = 200,
        symbol: str | None = None,
        since: int | None = None,
        limit_per_request: int = 1000,
    ) -> pd.DataFrame:
        """Fetches OHLCV data using ccxt, handling pagination, retries, and data cleaning.
        Returns a DataFrame scroll with essential columns converted to Decimal. Uses simple symbol format.
        """
        target_symbol = symbol or self.config.symbol  # Symbol from config or argument
        ccxt_timeframe = self._map_timeframe_to_pybit(
            timeframe,
        )  # Convert user timeframe to API format for ccxt

        if not ccxt_timeframe:
            self.logger.error(
                f"Invalid timeframe '{timeframe}' cannot be mapped to API format. Cannot fetch OHLCV.",
            )
            return pd.DataFrame()

        self.logger.debug(
            f"{Fore.CYAN}# Fetching OHLCV data via ccxt oracle | Symbol: {target_symbol}, TF: {timeframe} (API: {ccxt_timeframe}), Limit: {limit}, Since: {pd.to_datetime(since, unit='ms') if since else 'Latest'}{Style.RESET_ALL}",
        )
        if not self.exchange:
            self.logger.error("CCXT oracle not initialized. Cannot fetch OHLCV.")
            return pd.DataFrame()

        all_ohlcv: list[list[Any]] = []  # Accumulator for OHLCV data across pages
        fetch_count = 0
        retries = 0
        max_retries = self.config.retry_count
        retry_delay_secs = self.config.retry_delay
        current_since = since  # Track pagination start time

        # Loop to fetch data in chunks if needed (primarily for historical fetches)
        while fetch_count < limit and retries <= max_retries:
            try:
                # Determine chunk size: use limit_per_request for pagination, otherwise request the full limit
                current_fetch_limit = limit_per_request if since is not None else limit

                self.logger.debug(
                    f"  Fetching chunk {fetch_count // limit_per_request + 1 if since is not None else 1}, Limit: {current_fetch_limit}, Since: {pd.to_datetime(current_since, unit='ms').strftime('%Y-%m-%d %H:%M:%S %Z') if current_since is not None else 'Latest'}",
                )

                # Call ccxt's fetch_ohlcv, specifying category for Bybit v5
                ohlcv_chunk = self.exchange.fetch_ohlcv(
                    target_symbol,
                    ccxt_timeframe,  # ccxt handles internal timeframe mapping
                    since=current_since,  # Pagination start time
                    limit=current_fetch_limit,  # Candles per request
                    params={
                        "category": "linear",
                    },  # Specify 'linear' category for Bybit v5
                )

                # Check if oracle returned any data
                if not ohlcv_chunk:
                    self.logger.info(
                        f"Oracle returned no more data for {target_symbol} ({timeframe}) {'since ' + str(pd.to_datetime(current_since, unit='ms')) if current_since is not None else 'latest'}.",
                    )
                    break  # Exit loop if no data is returned

                # Process the fetched chunk
                if since is not None:
                    # If fetching history, append new data and update 'since' for the next page
                    all_ohlcv.extend(ohlcv_chunk)
                    current_since = (
                        ohlcv_chunk[-1][0] + 1
                    )  # Next 'since' is last candle's timestamp + 1ms
                else:
                    # If fetching latest data without 'since', ccxt handles pagination internally for 'limit'
                    all_ohlcv = ohlcv_chunk
                    fetch_count = len(all_ohlcv)  # Update count for loop condition
                    break  # Exit loop after fetching the latest block

                fetch_count += len(ohlcv_chunk)
                retries = 0  # Reset retries on successful fetch

                # Gentle delay between paginated requests if fetching history
                if since is not None:
                    time.sleep(
                        self.config.retry_delay * 0.5,
                    )  # Shorter delay between successful pages

            # --- Handle Specific CCXT Errors with Retries ---
            except ccxt.RateLimitExceeded as e:
                retries += 1
                wait_time = self.config.retry_delay * (
                    2 ** (retries - 1)
                )  # Exponential backoff
                self.logger.warning(
                    f"{Fore.YELLOW}Rate limit hit fetching OHLCV page (attempt {retries}/{max_retries}): {e}. Waiting {wait_time:.1f}s...{Style.RESET_ALL}",
                )
                time.sleep(wait_time)
            except (
                ccxt.NetworkError,
                ccxt.ExchangeNotAvailable,
                ccxt.RequestTimeout,
                ccxt.DDoSProtection,
            ) as e:
                retries += 1
                wait_time = self.config.retry_delay * (
                    2 ** (retries - 1)
                )  # Exponential backoff
                self.logger.warning(
                    f"{Fore.YELLOW}Network/Exchange disturbance fetching OHLCV page (attempt {retries}/{max_retries}): {e}. Waiting {wait_time:.1f}s...{Style.RESET_ALL}",
                )
                time.sleep(wait_time)
            except ccxt.ExchangeError as e:
                # Most other exchange errors are treated as non-retryable to prevent infinite loops on bad config
                self.logger.error(
                    f"{Fore.RED}Non-retryable CCXT ExchangeError fetching OHLCV for {target_symbol} ({timeframe}): {e}{Style.RESET_ALL}",
                    exc_info=True,
                )
                break  # Stop fetching on non-retryable errors
            except Exception as e:
                # Catch any other unexpected exceptions during fetching
                self.logger.exception(
                    f"Unexpected error during OHLCV fetch pagination: {e}",
                )
                break  # Stop on unexpected errors

        # Report if max retries were exceeded
        if retries > max_retries:
            self.logger.error(
                f"Exceeded max retries ({max_retries}) fetching OHLCV data for {target_symbol} ({timeframe}). Returning partial data if any.",
            )

        # If no data was collected after all attempts
        if not all_ohlcv:
            self.logger.warning(
                f"No OHLCV data collected after all attempts for {target_symbol} ({timeframe}).",
            )
            return pd.DataFrame()

        # --- Data Conversion and Cleaning ---
        # Convert collected data into a DataFrame
        df = pd.DataFrame(
            all_ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"],
        )

        # Convert timestamp column to datetime objects, localized to UTC
        try:
            df["timestamp"] = pd.to_datetime(
                df["timestamp"], unit="ms", utc=True, errors="coerce",
            )
        except Exception as e:
            self.logger.error(
                f"Error converting OHLCV timestamps to datetime: {e}. Raw timestamps: {df['timestamp'].head().tolist()}",
                exc_info=True,
            )
            return pd.DataFrame()  # Return empty if timestamps fail

        # Convert essential numeric columns to Decimal for financial precision
        numeric_cols = ["open", "high", "low", "close", "volume"]
        for col in numeric_cols:
            try:
                # Use errors='coerce' to handle potential non-numeric data gracefully
                df[col] = pd.to_numeric(df[col], errors="coerce").apply(
                    lambda x: Decimal(str(x)) if pd.notna(x) else np.nan,
                )
            except Exception as e:
                self.logger.error(
                    f"Error converting column '{col}' to Decimal: {e}", exc_info=True,
                )
                df[col] = np.nan  # Set column to NaN if conversion fails

        # Drop rows where essential data (like close price) might be NaN after conversion
        df.dropna(subset=["timestamp"] + numeric_cols, inplace=True)

        # Check if DataFrame became empty after cleaning
        if df.empty:
            self.logger.warning(
                f"OHLCV data for {target_symbol} ({timeframe}) became empty after cleaning NaNs/NaTs.",
            )
            return pd.DataFrame()

        # Ensure data is sorted by timestamp and remove any potential duplicates (defensive warding)
        df = (
            df.sort_values(by="timestamp")
            .drop_duplicates(subset=["timestamp"], keep="last")
            .reset_index(drop=True)
        )

        # Limit the final DataFrame to the requested 'limit' if fetching backwards
        if since is None and len(df) > limit:
            self.logger.info(
                f"Fetched {len(df)} candles, trimming to requested limit of {limit}.",
            )
            df = df.tail(limit).reset_index(drop=True)

        self.logger.info(
            f"Successfully fetched and processed {len(df)} OHLCV candles for {target_symbol} ({timeframe}). First: {df['timestamp'].iloc[0].strftime('%Y-%m-%d %H:%M:%S %Z')}, Last: {df['timestamp'].iloc[-1].strftime('%Y-%m-%d %H:%M:%S %Z')}",
        )
        return df

    def get_or_fetch_daily_ohlcv(
        self, symbol: str | None = None, limit: int = 365 * 3,
    ) -> pd.DataFrame:
        """Retrieves Daily OHLCV data, using cache if fresh, otherwise fetching and caching.
        Essential for Daily Pivot Point calculations. Uses simple symbol format.
        """
        target_symbol = symbol or self.config.symbol
        daily_timeframe_api = "D"  # API format for Daily timeframe

        cached_df = None
        # Acquire lock to safely read the daily cache
        with self._cache_lock:
            cached_df = self.daily_ohlcv_cache

        fetch_needed = False
        cache_is_fresh = False
        now_utc = datetime.now(UTC)
        # Define start of the current UTC day for freshness check
        start_of_today_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

        if cached_df is not None and not cached_df.empty:
            try:
                # Check the timestamp of the last candle in the cache
                last_candle_timestamp = cached_df["timestamp"].iloc[-1]
                # Ensure timestamp is timezone-aware (UTC)
                if last_candle_timestamp.tzinfo is None:
                    last_candle_timestamp = last_candle_timestamp.tz_localize("UTC")
                else:
                    last_candle_timestamp = last_candle_timestamp.tz_convert("UTC")

                # If the last candle is from today UTC, the cache is considered fresh
                if last_candle_timestamp >= start_of_today_utc:
                    cache_is_fresh = True
                    self.logger.debug(
                        f"Using cached Daily OHLCV for {target_symbol} (Last candle: {last_candle_timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}).",
                    )
                else:
                    self.logger.info(
                        f"Cached Daily OHLCV for {target_symbol} is stale (Last: {last_candle_timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}, Start Today: {start_of_today_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}). Fetching fresh data.",
                    )
                    fetch_needed = True
            except Exception as e:
                self.logger.warning(
                    f"Error checking Daily cache freshness for {target_symbol}: {e}. Fetching new data.",
                )
                fetch_needed = True
        else:
            self.logger.info(
                f"No cached Daily OHLCV data for {target_symbol}. Fetching initial data.",
            )
            fetch_needed = True

        # Fetch data if needed
        if fetch_needed:
            self.logger.debug(
                f"{Fore.CYAN}# Fetching Daily OHLCV data for {target_symbol}...{Style.RESET_ALL}",
            )
            # Fetch a generous amount of daily data for historical analysis
            df_raw = self.fetch_ohlcv(
                timeframe="1d", limit=max(limit, 300), symbol=target_symbol,
            )  # Use '1d' for daily

            if not df_raw.empty:
                with self._cache_lock:  # Acquire lock to update cache
                    # Cache the fetched daily data, trimmed to max size
                    self.daily_ohlcv_cache = (
                        df_raw.tail(self.max_daily_ohlcv_cache_size)
                        .reset_index(drop=True)
                        .copy()
                    )
                self.logger.info(
                    f"Fetched and cached {len(self.daily_ohlcv_cache)} Daily OHLCV candles for {target_symbol}.",
                )
                cache_is_fresh = True
                with self._cache_lock:  # Re-read cache after update
                    cached_df = (
                        self.daily_ohlcv_cache.copy()
                        if self.daily_ohlcv_cache is not None
                        else pd.DataFrame()
                    )
            else:
                self.logger.error(
                    f"Failed to fetch Daily OHLCV data for {target_symbol}. Daily cache not updated.",
                )
                # If fetching fails but cache exists, use the stale cache with a warning
                if cached_df is not None and not cached_df.empty:
                    self.logger.warning(
                        "Using potentially stale Daily cache due to fetch failure.",
                    )
                    with self._cache_lock:
                        return (
                            self.daily_ohlcv_cache.copy()
                            if self.daily_ohlcv_cache is not None
                            else pd.DataFrame()
                        )
                else:
                    return pd.DataFrame()  # Return empty if no cache and fetch failed

        # Return the cached data if it's fresh
        if cache_is_fresh and cached_df is not None and not cached_df.empty:
            with self._cache_lock:
                return self.daily_ohlcv_cache.copy()  # Return a copy
        else:
            self.logger.warning("Failed to return Daily OHLCV data despite checks.")
            return pd.DataFrame()

    def get_or_fetch_ohlcv(
        self, timeframe: str, limit: int = 500, include_daily_pivots: bool = True,
    ) -> pd.DataFrame:
        """Retrieves OHLCV data for the primary trading timeframe, using cache if recent,
        otherwise fetching, calculating indicators, updating cache, and returning the DataFrame.
        """
        target_timeframe_user = timeframe  # User-friendly format input
        target_timeframe_api = self._map_timeframe_to_pybit(
            target_timeframe_user,
        )  # API format for cache key
        target_symbol = self.config.symbol  # Use simple symbol from config

        if not target_timeframe_api:
            self.logger.error(
                f"Invalid timeframe '{target_timeframe_user}' cannot be mapped to API format. Cannot fetch OHLCV.",
            )
            return pd.DataFrame()

        # Determine minimum history needed for all indicators to function correctly
        min_history_needed = max(
            self.config.initial_candle_history,
            self.config.sma_long + 10,
            self.config.atr_period + 10,
            self.config.adx_period + 10,
            200,
        )

        cached_df = None
        with self._cache_lock:  # Acquire lock to read cache safely
            cached_df = self.ohlcv_cache.get(target_timeframe_api)

        fetch_needed = False
        cache_is_fresh = False
        now_utc = datetime.now(UTC)

        if cached_df is not None and not cached_df.empty:
            try:
                # Check freshness of cache based on the last candle's timestamp
                last_candle_timestamp = cached_df["timestamp"].iloc[-1]
                # Ensure timestamp is timezone-aware (UTC)
                if last_candle_timestamp.tzinfo is None:
                    last_candle_timestamp = last_candle_timestamp.tz_localize("UTC")
                else:
                    last_candle_timestamp = last_candle_timestamp.tz_convert("UTC")

                # Calculate expected start time of the next candle based on timeframe
                timeframe_seconds = (
                    self.exchange.parse_timeframe(target_timeframe_user)
                    if self.exchange
                    else 60
                )
                timeframe_timedelta = pd.Timedelta(seconds=timeframe_seconds)
                expected_next_candle_start = last_candle_timestamp + timeframe_timedelta
                # Add a buffer to account for loop delay and potential timing issues
                staleness_buffer = pd.Timedelta(seconds=self.config.loop_delay + 5)

                # If current time is before the expected next candle + buffer, cache is fresh
                if now_utc < (expected_next_candle_start + staleness_buffer):
                    cache_is_fresh = True
                    self.logger.debug(
                        f"Using cached OHLCV data for {target_timeframe_user} (Last candle: {cached_df['timestamp'].iloc[-1].strftime('%Y-%m-%d %H:%M:%S %Z')}).",
                    )
                else:
                    self.logger.info(
                        f"Cached OHLCV for {target_timeframe_user} is stale. Fetching fresh data.",
                    )
                    fetch_needed = True
            except Exception as e:
                self.logger.warning(
                    f"Error checking cache freshness for {target_timeframe_user}: {e}. Fetching new data.",
                )
                fetch_needed = True
        else:
            self.logger.info(
                f"No cached OHLCV data for {target_timeframe_user}. Fetching initial data.",
            )
            fetch_needed = True

        # --- Fetch Data and Calculate Indicators if Needed ---
        if fetch_needed:
            # Fetch Daily Data for Pivots if analysis modules require it
            daily_df_col = None  # DataFrame with 'timestamp' column for pivots
            if (
                self.config.analysis_modules.mtf_analysis.enabled
                or self.config.indicators.fibonacci_pivot_points
            ):
                daily_df_col = self.get_or_fetch_daily_ohlcv(symbol=target_symbol)
                if daily_df_col is None or daily_df_col.empty:
                    self.logger.debug(
                        "Daily OHLCV data not available for pivot calculation. Pivots and some MTF trends might be unavailable.",
                    )

            # Fetch primary timeframe OHLCV data
            self.logger.debug(
                f"{Fore.CYAN}# Fetching new {target_timeframe_user} OHLCV data...{Style.RESET_ALL}",
            )
            df_raw = self.fetch_ohlcv(
                timeframe=target_timeframe_user,
                limit=min_history_needed,
                symbol=target_symbol,
            )

            if not df_raw.empty:
                self.logger.debug(
                    f"Calculating indicators for freshly fetched {target_timeframe_user} data...",
                )
                try:
                    # Calculate indicators on the fetched raw data, passing daily data for pivots
                    df_with_indicators = calculate_indicators(
                        df_raw.copy(), self.config, daily_df_col,
                    )

                    if df_with_indicators is not None and not df_with_indicators.empty:
                        # Ensure timestamp column is timezone-aware (UTC)
                        if df_with_indicators["timestamp"].dt.tz is None:
                            df_with_indicators["timestamp"] = df_with_indicators[
                                "timestamp"
                            ].dt.tz_localize("UTC")
                        else:
                            df_with_indicators["timestamp"] = df_with_indicators[
                                "timestamp"
                            ].dt.tz_convert("UTC")

                        # Update cache with the new data (acquire lock for thread safety)
                        with self._cache_lock:
                            self.ohlcv_cache[target_timeframe_api] = (
                                df_with_indicators.tail(self.max_ohlcv_cache_size)
                                .reset_index(drop=True)
                                .copy()
                            )
                        self.logger.info(
                            f"Fetched, calculated indicators, and cached {len(self.ohlcv_cache[target_timeframe_api])} {target_timeframe_user} candles.",
                        )
                    else:
                        # Indicator calculation failed; cache raw data only as a fallback
                        self.logger.error(
                            f"Indicator calculation failed for {target_timeframe_user}. Caching raw data only.",
                        )
                        with self._cache_lock:
                            self.ohlcv_cache[target_timeframe_api] = (
                                df_raw.tail(self.max_ohlcv_cache_size)
                                .reset_index(drop=True)
                                .copy()
                            )
                except Exception as e:
                    self.logger.exception(
                        f"Error during indicator calculation for fetched {target_timeframe_user} data: {e}. Caching raw data.",
                    )
                    with self._cache_lock:  # Cache raw data even if indicators fail
                        self.ohlcv_cache[target_timeframe_api] = (
                            df_raw.tail(self.max_ohlcv_cache_size)
                            .reset_index(drop=True)
                            .copy()
                        )
            else:
                self.logger.error(
                    f"Failed to fetch OHLCV data for {target_timeframe_user}. Cache not updated.",
                )
                # If fetch failed, return the old (stale) cache if it exists, otherwise empty
                with self._cache_lock:
                    return (
                        cached_df.tail(limit).copy()
                        if cached_df is not None and not cached_df.empty
                        else pd.DataFrame()
                    )

        # Return the requested number of candles from the cache (acquire lock)
        if cache_is_fresh and cached_df is not None and not cached_df.empty:
            with self._cache_lock:
                # Return a copy of the relevant part of the cache
                return cached_df.tail(limit).copy()
        else:
            self.logger.warning(
                f"Failed to return cached OHLCV data for {target_timeframe_user} despite checks.",
            )
            return pd.DataFrame()  # Return empty DataFrame if all attempts fail

    def update_ohlcv_cache(self, kline_data: dict[str, Any]) -> pd.DataFrame | None:
        """Processes a single Kline whisper from WebSocket, updates indicators incrementally,
        and manages the OHLCV cache scroll. Uses the simple symbol format.
        """
        try:
            # --- Whisper Validation ---
            if (
                not isinstance(kline_data, dict)
                or "data" not in kline_data
                or not kline_data.get("data")
            ):
                self.logger.warning(
                    f"Received invalid kline whisper format: {kline_data}",
                )
                return None

            topic = kline_data.get("topic", "")
            topic_parts = topic.split(".")
            # Expected topic format: kline.<interval>.<symbol>
            if len(topic_parts) < 3 or topic_parts[0] != "kline":
                self.logger.warning(
                    f"Received whisper for unexpected topic format: {topic}",
                )
                return None

            candle_data_list = kline_data.get("data", [])
            if not candle_data_list:
                self.logger.warning(
                    f"Kline whisper data list is empty for topic {topic}.",
                )
                return None

            candle = candle_data_list[0]  # Process the first candle in the update

            # Extract critical info: timeframe (API format), symbol (simple format)
            cache_timeframe_key = topic_parts[1]  # e.g., '5', '60', 'D'
            symbol_from_topic = topic_parts[2]  # e.g., BTCUSDT

            # Ignore whispers for symbols not matching our focus symbol
            if symbol_from_topic != self.config.symbol:
                return None

            # --- Prepare Cache and Data ---
            # Ensure cache exists for this timeframe, fetch initial data if not.
            prev_df = None
            with self._cache_lock:  # Acquire lock to read cache
                prev_df = self.ohlcv_cache.get(cache_timeframe_key)

            if prev_df is None or prev_df.empty:
                self.logger.warning(
                    f"No cache found for {cache_timeframe_key} on WS update. Attempting initial fetch...",
                )
                user_timeframe = self._map_timeframe_from_pybit(cache_timeframe_key)
                if not user_timeframe:
                    self.logger.error(
                        f"Cannot map API timeframe '{cache_timeframe_key}' to user format. Cannot initialize cache.",
                    )
                    return None
                init_df = self.get_or_fetch_ohlcv(
                    user_timeframe,
                    limit=self.config.initial_candle_history,
                    include_daily_pivots=True,
                )
                if init_df is None or init_df.empty:
                    self.logger.error(
                        f"Failed to initialize cache for {cache_timeframe_key}. Cannot process WS update.",
                    )
                    return None
                with self._cache_lock:  # Re-read cache after initialization
                    prev_df = self.ohlcv_cache.get(cache_timeframe_key)
                if prev_df is None or prev_df.empty:  # Final check
                    self.logger.error(
                        f"Cache for {cache_timeframe_key} still empty after initialization attempt.",
                    )
                    return None

            # Fetch Daily Data for Pivots if enabled by analysis modules
            daily_df_col = None
            if (
                self.config.analysis_modules.mtf_analysis.enabled
                or self.config.indicators.fibonacci_pivot_points
            ):
                daily_df_col = self.get_or_fetch_daily_ohlcv(symbol=self.config.symbol)
                if daily_df_col is None or daily_df_col.empty:
                    self.logger.debug(
                        "Daily OHLCV data not available for pivot calculation during WS update.",
                    )

            # --- Process Kline Whisper Data ---
            is_confirmed = candle.get(
                "confirm", False,
            )  # Is this a final confirmed candle?
            timestamp_ms = int(candle["start"])
            timestamp = pd.to_datetime(timestamp_ms, unit="ms", utc=True)

            # Create DataFrame for the new/updated row's raw data, using Decimal for precision
            new_row_data = {}
            try:
                new_row_data = {
                    "timestamp": timestamp,
                    "open": Decimal(str(candle.get("open", "0"))),
                    "high": Decimal(str(candle.get("high", "0"))),
                    "low": Decimal(str(candle.get("low", "0"))),
                    "close": Decimal(str(candle.get("close", "0"))),
                    "volume": Decimal(str(candle.get("volume", "0"))),
                }
                new_raw_df = pd.DataFrame([new_row_data])
            except (InvalidOperation, ValueError, KeyError, TypeError) as e:
                self.logger.error(
                    f"Error parsing kline data to Decimal/dict for {cache_timeframe_key}: {e}. Data: {candle}",
                    exc_info=True,
                )
                return None

            # --- Update Cache Logic ---
            final_processed_row: pd.DataFrame | None = (
                None  # To store the result of recalculation
            )
            with self._cache_lock:  # Critical section for cache modification
                target_cache_df = self.ohlcv_cache.get(cache_timeframe_key)

                if target_cache_df is None:  # Cache vanished unexpectedly
                    self.logger.error(
                        f"Cache for {cache_timeframe_key} disappeared while lock was held.",
                    )
                    return None

                last_cached_timestamp_in_lock = (
                    target_cache_df["timestamp"].iloc[-1]
                    if not target_cache_df.empty
                    else None
                )

                # Check if we are updating the last candle or adding a new one
                if last_cached_timestamp_in_lock == timestamp:
                    # --- Update the Last Candle ---
                    log_prefix = (
                        f"{Fore.GREEN}Confirmed"
                        if is_confirmed
                        else f"{Fore.YELLOW}Updating"
                    )
                    self.logger.debug(
                        f"{log_prefix} candle in cache: {cache_timeframe_key} {symbol_from_topic} @ {timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}",
                    )

                    # Find the index of the candle to update
                    try:
                        idx_to_update = target_cache_df.index[
                            target_cache_df["timestamp"] == timestamp
                        ].tolist()[0]
                    except IndexError:
                        self.logger.error(
                            f"Timestamp {timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')} not found in cache for update. Ignoring.",
                        )
                        return None  # Timestamp mismatch

                    # Prepare a slice of historical data for recalculation
                    # Need enough history for all indicators to calculate correctly
                    min_slice_size = max(
                        self.config.initial_candle_history,
                        self.config.sma_long + 10,
                        self.config.atr_period + 10,
                        self.config.adx_period + 10,
                        200,
                    )
                    slice_start_idx = max(0, idx_to_update - min_slice_size + 1)
                    temp_df_for_calc = target_cache_df.iloc[
                        slice_start_idx : idx_to_update + 1
                    ].copy(deep=True)

                    # Update OHLCV columns in the slice with new data
                    idx_in_slice = (
                        len(temp_df_for_calc) - 1
                    )  # Index of the candle being updated within the slice
                    for col in ["open", "high", "low", "close", "volume"]:
                        if col in temp_df_for_calc.columns:
                            temp_df_for_calc.iloc[
                                idx_in_slice, temp_df_for_calc.columns.get_loc(col),
                            ] = new_raw_df.loc[0, col]
                        else:
                            self.logger.warning(
                                f"Column '{col}' missing in temp_df_for_calc during update.",
                            )

                    # Recalculate indicators on the updated slice
                    updated_slice_df = calculate_indicators(
                        temp_df_for_calc, self.config, daily_df_col,
                    )

                    if updated_slice_df is not None and not updated_slice_df.empty:
                        # Get the last row from the recalculated slice (corresponding to the updated candle)
                        newly_processed_row = updated_slice_df.iloc[-1:].copy()
                        if (
                            not newly_processed_row.empty
                            and newly_processed_row["timestamp"].iloc[0] == timestamp
                        ):
                            # Update the main cache row by row to maintain alignment
                            for col in newly_processed_row.columns:
                                if (
                                    col not in target_cache_df.columns
                                ):  # Add new indicator columns if they appeared
                                    self.logger.debug(
                                        f"Adding new indicator column '{col}' to {cache_timeframe_key} cache during update.",
                                    )
                                    target_cache_df[col] = np.nan  # Initialize with NaN

                            # Ensure columns match before updating the row
                            newly_processed_row = newly_processed_row.reindex(
                                columns=target_cache_df.columns, fill_value=np.nan,
                            )
                            # Update the specific row in the main cache
                            target_cache_df.iloc[idx_to_update] = (
                                newly_processed_row.iloc[0]
                            )
                            final_processed_row = target_cache_df.loc[
                                [idx_to_update]
                            ].copy()  # Store the updated row
                        else:
                            self.logger.error(
                                f"Recalculation for updated candle @ {timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')} returned incorrect timestamp or empty result. Appending raw data as fallback.",
                            )
                            self._append_raw_data_with_nans(
                                target_cache_df, new_raw_df, cache_timeframe_key,
                            )

                    else:
                        self.logger.error(
                            f"Indicator recalculation failed (returned empty) for updated candle @ {timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}. Appending raw data only.",
                        )
                        self._append_raw_data_with_nans(
                            target_cache_df, new_raw_df, cache_timeframe_key,
                        )

                elif (
                    last_cached_timestamp_in_lock is None
                    or timestamp > last_cached_timestamp_in_lock
                ):
                    # --- Adding a New Candle ---
                    self.logger.debug(
                        f"{Fore.BLUE}New candle received: {cache_timeframe_key} {symbol_from_topic} @ {timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}{Style.RESET_ALL}",
                    )

                    # Prepare a slice of historical data plus the new raw row for recalculation
                    min_slice_size = max(
                        self.config.initial_candle_history,
                        self.config.sma_long + 10,
                        self.config.atr_period + 10,
                        self.config.adx_period + 10,
                        200,
                    )
                    # Take enough history from the end of the current cache
                    tail_slice = target_cache_df.tail(min_slice_size - 1).copy(
                        deep=True,
                    )

                    # Combine historical slice with the new raw candle data
                    temp_df_for_calc = pd.concat(
                        [tail_slice, new_raw_df], ignore_index=True,
                    )

                    # Calculate indicators on the combined slice
                    updated_slice_df = calculate_indicators(
                        temp_df_for_calc, self.config, daily_df_col,
                    )

                    if updated_slice_df is not None and not updated_slice_df.empty:
                        # Get the last row from the recalculated slice (representing the new candle with indicators)
                        newly_processed_row = updated_slice_df.iloc[-1:].copy()
                        if (
                            not newly_processed_row.empty
                            and newly_processed_row["timestamp"].iloc[0] == timestamp
                        ):
                            # Append the newly processed row to the main cache
                            for col in newly_processed_row.columns:
                                if (
                                    col not in target_cache_df.columns
                                ):  # Add new indicator columns if they appeared
                                    self.logger.debug(
                                        f"Adding new indicator column '{col}' to {cache_timeframe_key} cache before appending.",
                                    )
                                    target_cache_df[col] = np.nan  # Initialize with NaN

                            # Ensure columns match before concatenating
                            newly_processed_row = newly_processed_row.reindex(
                                columns=target_cache_df.columns, fill_value=np.nan,
                            )
                            # Append the processed row to the main cache
                            self.ohlcv_cache[cache_timeframe_key] = pd.concat(
                                [target_cache_df, newly_processed_row],
                                ignore_index=True,
                            )
                            # Trim the cache to maintain size limit
                            self.ohlcv_cache[cache_timeframe_key] = (
                                self.ohlcv_cache[cache_timeframe_key]
                                .tail(self.max_ohlcv_cache_size)
                                .reset_index(drop=True)
                            )

                            # Retrieve the exact row that was just added for the return value
                            final_processed_row_df = self.ohlcv_cache[
                                cache_timeframe_key
                            ][
                                self.ohlcv_cache[cache_timeframe_key]["timestamp"]
                                == timestamp
                            ]
                            if not final_processed_row_df.empty:
                                final_processed_row = final_processed_row_df.copy()
                            else:
                                self.logger.error(
                                    f"Failed to find newly added row {timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')} in cache after processing.",
                                )

                        else:
                            self.logger.error(
                                f"Recalculation for new candle @ {timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')} returned incorrect timestamp or empty result. Appending raw data as fallback.",
                            )
                            self._append_raw_data_with_nans(
                                target_cache_df, new_raw_df, cache_timeframe_key,
                            )

                    else:
                        self.logger.error(
                            f"Indicator calculation failed (returned empty) for new candle @ {timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}. Appending raw data only.",
                        )
                        self._append_raw_data_with_nans(
                            target_cache_df, new_raw_df, cache_timeframe_key,
                        )

                else:
                    # Received out-of-order data - a temporal anomaly!
                    self.logger.warning(
                        f"{Fore.YELLOW}Received kline update with timestamp {timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')} older than the last cached candle ({last_cached_timestamp_in_lock.strftime('%Y-%m-%d %H:%M:%S %Z') if last_cached_timestamp_in_lock else 'N/A'}). Ignoring anomaly.{Style.RESET_ALL}",
                    )
                    # No change to cache; final_processed_row remains None

            # --- End of critical section (cache lock released) ---

            # --- Return the Processed Row (if successfully generated) ---
            if final_processed_row is not None and not final_processed_row.empty:
                final_ts_str = (
                    final_processed_row["timestamp"]
                    .iloc[0]
                    .strftime("%Y-%m-%d %H:%M:%S %Z")
                )
                with (
                    self._cache_lock
                ):  # Re-acquire lock briefly to check cache size after update
                    cache_size = len(self.ohlcv_cache.get(cache_timeframe_key, []))
                self.logger.debug(
                    f"Processed candle {final_ts_str} for {cache_timeframe_key}. Cache size: {cache_size}.",
                )
                return final_processed_row  # Return the single processed row DataFrame
            # Handle cases where processing failed or returned no usable row
            if (
                last_cached_timestamp_in_lock is not None
                and last_cached_timestamp_in_lock == timestamp
            ):
                self.logger.debug(
                    f"Failed to produce updated processed row for timestamp {timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')} in {cache_timeframe_key}.",
                )
            elif (
                last_cached_timestamp_in_lock is None
                or timestamp > last_cached_timestamp_in_lock
            ):
                self.logger.debug(
                    f"Failed to produce newly added processed row for timestamp {timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')} in {cache_timeframe_key}.",
                )
            return None

        except (IndexError, KeyError, ValueError, TypeError, InvalidOperation) as e:
            self.logger.exception(
                f"Error processing kline whisper data for topic {kline_data.get('topic', 'N/A')}: {e}. Data: {kline_data}",
            )
            return None
        except Exception as e:
            self.logger.exception(
                f"Unexpected error in update_ohlcv_cache for topic {kline_data.get('topic', 'N/A')}: {e}. Data: {kline_data}",
            )
            return None

    def _append_raw_data_with_nans(
        self,
        target_cache_df: pd.DataFrame,
        new_raw_df: pd.DataFrame,
        timeframe_key: str,
    ):
        """Helper to append raw data and add NaNs for missing indicator columns. Assumes cache lock is held."""
        try:
            # Identify columns present in cache but not in new raw data
            cols_to_add = set(target_cache_df.columns) - set(new_raw_df.columns)
            temp_raw_df = new_raw_df.copy()
            # Add missing columns initialized with NaN
            for col in cols_to_add:
                temp_raw_df[col] = np.nan

            # Reindex to match target cache columns exactly, filling new columns with NaN
            temp_raw_df = temp_raw_df.reindex(
                columns=target_cache_df.columns, fill_value=np.nan,
            )
            # Append the raw data (with added NaNs for indicators) to the cache
            self.ohlcv_cache[timeframe_key] = pd.concat(
                [target_cache_df, temp_raw_df], ignore_index=True,
            )
            self.logger.warning(
                f"Appended raw data for {new_raw_df['timestamp'].iloc[0].strftime('%Y-%m-%d %H:%M:%S %Z')} to {timeframe_key} cache due to indicator failure.",
            )

            # Trim cache to maintain size limit
            self.ohlcv_cache[timeframe_key] = (
                self.ohlcv_cache[timeframe_key]
                .tail(self.max_ohlcv_cache_size)
                .reset_index(drop=True)
            )

        except Exception as e:
            self.logger.error(
                f"Error during fallback raw data append for {timeframe_key}: {e}",
                exc_info=True,
            )

    # --- Account & Position Helpers - Peering into the Treasury ---
    def fetch_balance(self, coin: str = "USDT") -> Decimal | None:
        """Fetches the available balance for a specific coin in the UNIFIED account via pybit."""
        self.logger.debug(
            f"{Fore.CYAN}# Fetching available balance for {coin}...{Style.RESET_ALL}",
        )
        if not self.session:
            self.logger.error("pybit session not available for balance fetch.")
            return None
        try:
            # Bybit v5: get_wallet_balance requires accountType. 'UNIFIED' is common.
            response = self.session.get_wallet_balance(
                accountType="UNIFIED", coin=coin,
            )  # Use simple coin format
            if response and response.get("retCode") == 0:
                result = response.get("result", {})
                account_list = result.get("list", [])
                if account_list:
                    account_info = account_list[
                        0
                    ]  # Assuming UNIFIED account is the first entry
                    coin_info_list = account_info.get("coin", [])
                    target_coin_data = None
                    if coin_info_list:
                        # Find the specific coin data
                        target_coin_data = next(
                            (
                                c
                                for c in coin_info_list
                                if c.get("coin", "").lower() == coin.lower()
                            ),
                            None,
                        )

                    if target_coin_data:
                        # Extract available balance for trading
                        balance_str = target_coin_data.get("availableToTrade")
                        if balance_str is None or balance_str == "":
                            balance_str = "0"

                        try:
                            balance = Decimal(
                                str(balance_str),
                            )  # Convert to Decimal for precision
                            self.logger.info(
                                f"Available {coin} balance to trade: {Style.BRIGHT}{balance}{Style.RESET_ALL}",
                            )
                            return balance
                        except (InvalidOperation, ValueError):
                            self.logger.error(
                                f"Could not parse availableToTrade balance '{balance_str}' for {coin}.",
                                exc_info=True,
                            )
                            return Decimal("0")
                    else:
                        self.logger.warning(
                            f"Coin rune '{coin}' not found in wallet balance response list. Assuming zero balance.",
                        )
                        return Decimal("0")
                else:
                    self.logger.warning(
                        f"No account list found in balance response for accountType='UNIFIED'. Response: {response}",
                    )
                    return Decimal("0")
            else:
                err_msg = response.get("retMsg", "Unknown Error")
                err_code = response.get("retCode", "N/A")
                self.logger.error(
                    f"API Error fetching balance: {err_msg} (Rune: {err_code})",
                )
                return None
        except Exception as e:
            self.logger.exception(f"Exception fetching balance: {e}")
            return None

    def get_equity(self) -> Decimal | None:
        """Fetches the total account equity (in USD equivalent) via pybit."""
        self.logger.debug(
            f"{Fore.CYAN}# Fetching total account equity...{Style.RESET_ALL}",
        )
        if not self.session:
            self.logger.error("pybit session not available for equity fetch.")
            return None
        try:
            response = self.session.get_wallet_balance(
                accountType="UNIFIED",
            )  # Fetch balance for UNIFIED account
            if response and response.get("retCode") == 0:
                result = response.get("result", {})
                account_list = result.get("list", [])
                if account_list:
                    account_info = account_list[
                        0
                    ]  # Assuming UNIFIED account is the first entry
                    equity_str = account_info.get(
                        "totalEquity",
                    )  # Get total equity value
                    if equity_str is None or equity_str == "":
                        equity_str = "0"

                    try:
                        equity = Decimal(str(equity_str))  # Convert to Decimal
                        self.logger.info(
                            f"Total Account Equity (reported in USD equivalent): {Style.BRIGHT}{equity}{Style.RESET_ALL}",
                        )
                        return equity
                    except (InvalidOperation, ValueError):
                        self.logger.error(
                            f"Could not parse totalEquity balance '{equity_str}'.",
                            exc_info=True,
                        )
                        return Decimal("0")
                else:
                    self.logger.warning(
                        f"No account list found in equity response: {response}",
                    )
                    return None
            else:
                err_msg = response.get("retMsg", "Unknown Error")
                err_code = response.get("retCode", "N/A")
                self.logger.error(
                    f"API Error fetching equity: {err_msg} (Rune: {err_code})",
                )
                return None
        except Exception as e:
            self.logger.exception(f"Exception fetching equity: {e}")
            return None

    def get_position(self, symbol: str | None = None) -> dict[str, Any] | None:
        """Fetches position details for the specified symbol using pybit.
        Uses the simple symbol format. Returns details of the active position, or None.
        """
        target_symbol = symbol or self.config.symbol
        self.logger.debug(
            f"{Fore.CYAN}# Fetching position for {target_symbol}...{Style.RESET_ALL}",
        )
        if not self.session:
            self.logger.error("pybit session not available for position fetch.")
            return None
        try:
            # Bybit v5: get_positions requires category ('linear' for USDT perpetuals) and symbol (simple format)
            response = self.session.get_positions(
                category="linear", symbol=target_symbol,
            )
            if response and response.get("retCode") == 0:
                result = response.get("result", {})
                position_list = result.get("list", [])
                if position_list:
                    active_position_data = None
                    # Find the active position (non-zero size)
                    for pos_data in position_list:
                        try:
                            pos_size_str = pos_data.get("size", "0")
                            if pos_size_str is None or pos_size_str == "":
                                pos_size_str = "0"
                            pos_size = Decimal(
                                str(pos_size_str),
                            )  # Convert to str first for Decimal

                            if not pos_size.is_zero():
                                active_position_data = pos_data
                                break  # Found the active position, exit loop

                        except (InvalidOperation, ValueError, TypeError) as parse_error:
                            # Log error if position size parsing fails, but continue to check others
                            self.logger.error(
                                f"Error parsing position size for {target_symbol}: {parse_error}. Data: {pos_data}",
                                exc_info=True,
                            )

                    if active_position_data:
                        # Found an active position, transcribe and standardize its details
                        position_info = self._standardize_position_data(
                            active_position_data,
                        )
                        if position_info:  # Check if formatting was successful
                            return (
                                position_info  # Return the standardized position data
                            )
                        self.logger.error(
                            f"Failed to standardize position data for {target_symbol}. Raw data: {active_position_data}",
                        )
                        return None  # Return None if standardization failed

                    # No active position found (all entries had zero size)
                    self.logger.info(
                        f"No active position found for {target_symbol} (all entries had size 0).",
                    )
                    return None
                # API returned success but the list was empty (e.g., no positions ever)
                self.logger.info(
                    f"No position data returned in list for {target_symbol}.",
                )
                return None
            # API returned an error code
            err_msg = response.get("retMsg", "Unknown Error")
            err_code = response.get("retCode", "N/A")
            # Specific check for the "symbol not exist" error related to format
            if err_code == 10001 and (
                "symbol not exist" in err_msg.lower()
                or "invalid symbol" in err_msg.lower()
            ):
                self.logger.error(
                    f"API Error fetching position: Symbol '{target_symbol}' not found by pybit API. (Rune: {err_code})",
                )
            else:
                self.logger.error(
                    f"API Error fetching position: {err_msg} (Rune: {err_code})",
                )
            return None
        # Catch specific pybit request errors
        except InvalidRequestError as e:
            if (
                "symbol not exist" in str(e).lower()
                or "invalid symbol" in str(e).lower()
            ):
                self.logger.error(
                    f"API Error fetching position: Symbol '{target_symbol}' not found by pybit API. (Rune: {e.status_code if hasattr(e, 'status_code') else 'N/A'})",
                )
            else:
                self.logger.exception(
                    f"Invalid Request Error fetching position for {target_symbol}: {e}",
                )
            return None
        except FailedRequestError as e:
            self.logger.exception(
                f"Failed Request Error fetching position for {target_symbol}: {e}",
            )
            return None
        except Exception as e:
            self.logger.exception(
                f"Exception fetching position for {target_symbol}: {e}",
            )
            return None

    def _standardize_position_data(
        self, raw_position_data: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Helper to standardize raw position data into a consistent internal format."""

        # Helper to safely convert string to Decimal, returning None on failure or empty string
        def safe_decimal(value_str: str | None) -> Decimal | None:
            if value_str is None or value_str == "":
                return None
            try:
                return Decimal(str(value_str))  # Convert via string for precision
            except (InvalidOperation, ValueError):
                return None

        # Helper to safely convert ms timestamp string to datetime object
        def safe_datetime_from_ms(ts_str: str | None) -> datetime | None:
            if ts_str is None or not isinstance(ts_str, (str, int)):
                return None
            try:
                return pd.to_datetime(
                    int(ts_str), unit="ms", utc=True,
                ).to_pydatetime()  # Convert ms to datetime
            except (ValueError, TypeError):
                return None

        try:
            # Map raw API fields to standardized internal keys
            standardized_data = {
                "symbol": raw_position_data.get("symbol"),
                "side": raw_position_data.get("side"),  # "Buy", "Sell", or "None"
                "size": safe_decimal(raw_position_data.get("size", "0")),
                "entry_price": safe_decimal(
                    raw_position_data.get("avgPrice"),
                ),  # avgPrice is entry price
                "mark_price": safe_decimal(raw_position_data.get("markPrice")),
                "liq_price": safe_decimal(raw_position_data.get("liqPrice")),
                "unrealised_pnl": safe_decimal(
                    raw_position_data.get("unrealisedPnl", "0"),
                ),
                "leverage": safe_decimal(raw_position_data.get("leverage", "0")),
                "position_value": safe_decimal(raw_position_data.get("positionValue")),
                "take_profit": safe_decimal(raw_position_data.get("takeProfit")),
                "stop_loss": safe_decimal(raw_position_data.get("stopLoss")),
                "trailingStop": safe_decimal(
                    raw_position_data.get("trailingStop"),
                ),  # Key used internally for TSL state
                "createdTime": safe_datetime_from_ms(
                    raw_position_data.get("createdTime"),
                ),
                "updatedTime": safe_datetime_from_ms(
                    raw_position_data.get("updatedTime"),
                ),
                "positionIdx": int(
                    raw_position_data.get("positionIdx", 0),
                ),  # 0=One-Way, 1=Buy Hedge, 2=Sell Hedge
                "riskLimitValue": raw_position_data.get("riskLimitValue"),
            }
            # Basic validation: If size is positive, entry price must be parsed
            if standardized_data["size"] is None or (
                standardized_data["size"] > Decimal("0")
                and standardized_data["entry_price"] is None
            ):
                self.logger.error(
                    f"Failed to parse essential position fields (size/entry) for symbol {standardized_data['symbol']}. Raw data: {raw_position_data}",
                )
                return None

            return standardized_data
        except Exception as format_error:
            self.logger.exception(
                f"Unexpected error formatting position data: {format_error}. Raw data: {raw_position_data}",
            )
            return None

    # FIX: Merged the two definitions of get_open_positions_from_exchange into a single, more robust method.
    # This method prioritizes WebSocket data if available and falls back to REST API.
    # It also standardizes the position data.
    def get_open_positions(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """Fetches open positions for the specified symbol. Prioritizes WebSocket data if available,
        falling back to REST API. Standardizes the output. Uses simple symbol format.
        """
        target_symbol = symbol or self.config.symbol
        self.logger.debug(
            f"{Fore.CYAN}# Fetching open positions for {target_symbol}...{Style.RESET_ALL}",
        )

        # Prefer WebSocket data if available and connected
        if self.ws_connected and self.ws:
            self.logger.debug("Checking WebSocket for open position updates...")
            # A more robust implementation would involve managing a state dictionary of positions
            # and merging updates from the WebSocket stream. Here, we check the WS queue
            # for explicit 'position' updates assuming ws_manager provides them.
            # The reference to `ws_manager` is adjusted to use `self` to access internal WS state.
            if (
                hasattr(self, "ws")
                and self.ws
                and hasattr(self, "_private_ws_data_buffer")
                and isinstance(self._private_ws_data_buffer, list)
            ):  # Check if BybitHelper manages private WS data
                # Assuming _private_ws_data_buffer holds relevant WS messages
                private_updates = self._private_ws_data_buffer
                position_updates = [
                    d
                    for d in private_updates
                    if d.get("topic", "").startswith("position")
                ]

                if position_updates:
                    # For simplicity, take the latest position data. A full implementation might merge deltas.
                    # Ideally, this would involve a dedicated state manager for positions.
                    latest_pos_data = position_updates[-1].get("data", [])
                    open_positions_ws = []
                    for pos in latest_pos_data:
                        try:
                            # If size is > 0, it's considered an open position
                            if Decimal(str(pos.get("size", "0"))) > Decimal("0"):
                                std_pos = self._standardize_position_data(
                                    pos,
                                )  # Standardize data
                                if std_pos:
                                    open_positions_ws.append(std_pos)
                        except Exception as e:
                            self.logger.warning(
                                f"Error processing WS position data: {e}. Data: {pos}",
                                exc_info=True,
                            )
                    if open_positions_ws:
                        self.logger.debug(
                            f"Fetched {len(open_positions_ws)} open positions from WS stream.",
                        )
                        return open_positions_ws
                    self.logger.debug("No open positions found in WS updates.")
                else:
                    self.logger.debug(
                        "No new position updates from WS. Falling back to REST API.",
                    )
            else:
                self.logger.debug(
                    "WS Manager or private data buffer not available. Falling back to REST API.",
                )

        # Fallback to REST API if WebSocket data is not available or insufficient
        # Fetch position details via REST API
        positions_data = self.get_position(
            symbol=target_symbol,
        )  # This method gets the active position details

        if positions_data:
            # get_position returns standardized data for the active position, or None
            # Wrap it in a list for consistency with WS return type
            return [positions_data] if positions_data else []
        # get_position returned None or an empty list (meaning no active position)
        return []  # Return empty list if no positions found via REST

    # --- Order Execution Helpers - Weaving the Trading Spells ---
    def format_quantity(self, quantity: Decimal) -> str:
        """Formats quantity according to the symbol's minimum step size (lot size), rounding down."""
        if quantity <= Decimal("0"):
            self.logger.warning(
                f"Attempted to format non-positive quantity: {quantity}. Returning '0'.",
            )
            return "0"

        qty_step = self.get_qty_step()
        if qty_step is None or qty_step <= Decimal(0):
            self.logger.warning(
                "Quantity step size rune not found or invalid. Using default formatting (8 decimals).",
            )
            # Default to 8 decimal places if step is unavailable
            return (
                f"{quantity.quantize(Decimal('0.00000001'), rounding=ROUND_DOWN):.8f}"
            )

        try:
            # Calculate formatted quantity by dividing by step, rounding down, then formatting
            decimal_places = (
                abs(qty_step.normalize().as_tuple().exponent)
                if "." in str(qty_step)
                else 0
            )
            # Use integer division and multiplication to apply step size and round down
            formatted_qty_dec = (quantity // qty_step) * qty_step
            # Ensure the final string has the correct number of decimal places
            return f"{formatted_qty_dec:.{decimal_places}f}"
        except (ValueError, TypeError, InvalidOperation) as e:
            self.logger.error(
                f"Error formatting quantity {quantity} with step {qty_step}: {e}. Using default formatting.",
                exc_info=True,
            )
            # Fallback to default formatting if error occurs
            return (
                f"{quantity.quantize(Decimal('0.00000001'), rounding=ROUND_DOWN):.8f}"
            )

    def format_price(self, price: Decimal | None) -> str | None:
        """Formats price according to the symbol's minimum step size (tick size), rounding half up."""
        if price is None:
            return None  # Return None if input is None
        if price <= Decimal("0"):
            self.logger.warning(f"Attempted to format non-positive price: {price}")
            return "0"

        price_step = self.get_price_step()
        if price_step is None or price_step <= Decimal(0):
            self.logger.warning(
                "Price step size rune not found or invalid. Using default formatting (2 decimals).",
            )
            # Default to 2 decimal places if step is unavailable
            return f"{price.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"

        try:
            # Quantize price to the step size, rounding half up (common for prices)
            formatted_price_dec = price.quantize(price_step, rounding=ROUND_HALF_UP)
            # Determine decimal places from the price step for accurate formatting
            decimal_places = (
                abs(price_step.normalize().as_tuple().exponent)
                if "." in str(price_step)
                else 0
            )
            # Return formatted string with correct decimal places
            return f"{formatted_price_dec:.{decimal_places}f}"

        except (ValueError, TypeError, InvalidOperation) as e:
            self.logger.error(
                f"Error formatting price {price} with step {price_step}: {e}. Using default formatting.",
                exc_info=True,
            )
            # Fallback to default formatting if error occurs
            return f"{price.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"

    def get_min_order_qty(self) -> Decimal | None:
        """Retrieves the minimum order quantity rune from loaded market wisdom."""
        if self.market_info:
            try:
                # Access nested limits for amount details
                min_qty_val = (
                    self.market_info.get("limits", {}).get("amount", {}).get("min")
                )
                if min_qty_val is not None:
                    return Decimal(str(min_qty_val))  # Convert to Decimal
            except (KeyError, ValueError, TypeError, InvalidOperation) as e:
                self.logger.error(
                    f"Could not parse min order quantity rune from market wisdom: {e}",
                    exc_info=True,
                )
        self.logger.warning("Min order quantity rune not found in market wisdom.")
        return None

    def get_qty_step(self) -> Decimal | None:
        """Retrieves the quantity step size rune (lot size) from loaded market wisdom."""
        if self.market_info:
            try:
                # Access nested precision for quantity step
                step_val = self.market_info.get("precision", {}).get("amount")
                if step_val is not None:
                    return Decimal(str(step_val))  # Convert to Decimal
            except (KeyError, ValueError, TypeError, InvalidOperation) as e:
                self.logger.error(
                    f"Could not parse quantity step size rune from market wisdom: {e}",
                    exc_info=True,
                )
        self.logger.warning("Quantity step size rune not found in market wisdom.")
        return None

    def get_price_step(self) -> Decimal | None:
        """Retrieves the price step size rune (tick size) from loaded market wisdom."""
        if self.market_info:
            try:
                # Access nested precision for price step
                step_val = self.market_info.get("precision", {}).get("price")
                if step_val is not None:
                    return Decimal(str(step_val))  # Convert to Decimal
            except (KeyError, ValueError, TypeError, InvalidOperation) as e:
                self.logger.error(
                    f"Could not parse price step size rune from market wisdom: {e}",
                    exc_info=True,
                )
        self.logger.warning("Price step size rune not found in market wisdom.")
        return None

    def place_order(
        self,
        side: str,
        qty: Decimal,
        order_type: str = "Market",
        price: Decimal | None = None,
        sl: Decimal | None = None,
        tp: Decimal | None = None,
        reduce_only: bool = False,
        time_in_force: str = "GTC",
        position_idx: int = 0,
        trigger_price: Decimal | None = None,
        trigger_direction: int | None = None,
        stop_loss_type: str = "Market",
        take_profit_type: str = "Market",
        order_link_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Weaves an order spell using pybit session, applying formatting, validation,
        and SL/TP wards. Uses simple symbol format for API calls.
        """
        if not self.session or self.market_info is None:
            self.logger.error(
                "Cannot weave order spell: pybit session or market wisdom not initialized.",
            )
            return None

        symbol = self.config.symbol  # Use simple symbol format from config
        category = "linear"  # Default category, usually 'linear' for USDT perpetuals

        # --- Input Validation Wards ---
        side_upper = side.capitalize()
        if side_upper not in ["Buy", "Sell"]:
            self.logger.error(
                f"Invalid order side rune: {side}. Must be 'Buy' or 'Sell'.",
            )
            return None
        if qty <= Decimal("0"):
            self.logger.error(f"Invalid order quantity rune: {qty}. Must be positive.")
            return None

        order_type_upper = order_type.capitalize()
        if order_type_upper not in ["Market", "Limit"]:
            self.logger.error(
                f"Invalid order_type rune: {order_type}. Base type must be Market or Limit. Use trigger_price for conditional.",
            )
            return None
        if order_type_upper == "Limit" and price is None:
            self.logger.error("Price rune is required for Limit spells.")
            return None
        # Validate trigger parameters if provided
        if trigger_price is not None and trigger_direction not in [
            1,
            2,
        ]:  # 1=RISE >=, 2=FALL <=
            self.logger.error(
                "trigger_direction rune (1 or 2) is required when trigger_price is set.",
            )
            return None
        if trigger_price is None and trigger_direction is not None:
            self.logger.warning(
                "trigger_direction provided without trigger_price. Ignoring trigger_direction.",
            )
            trigger_direction = None

        # Validate Time-In-Force (TIF) rune
        valid_tifs = ["GTC", "IOC", "FOK", "PostOnly"]
        tif_upper = time_in_force.upper()
        if tif_upper not in valid_tifs:
            self.logger.warning(
                f"Invalid time_in_force rune '{time_in_force}'. Defaulting based on order type.",
            )
            tif_upper = "IOC" if order_type_upper == "Market" else "GTC"  # Default TIF
        # Enforce TIF rules based on order type
        if order_type_upper == "Market" and tif_upper not in ["IOC", "FOK"]:
            self.logger.warning(
                f"Market spells usually use IOC or FOK. Overriding timeInForce to IOC for type '{order_type}'.",
            )
            tif_upper = "IOC"
        if tif_upper == "POSTONLY" and order_type_upper != "Limit":
            self.logger.warning(
                f"PostOnly TIF is only valid for Limit spells. Using GTC for {order_type}.",
            )
            tif_upper = "GTC"
        if tif_upper == "POSTONLY" and trigger_price is not None:
            self.logger.warning(
                "PostOnly TIF combined with trigger_price might have unexpected behavior. Using GTC.",
            )
            tif_upper = "GTC"

        # Validate Stop Loss / Take Profit types
        stop_loss_type_upper = stop_loss_type.capitalize()
        if stop_loss_type_upper not in ["Market", "Limit"]:
            self.logger.warning(
                f"Invalid stop_loss_type rune '{stop_loss_type}'. Defaulting to 'Market'.",
            )
            stop_loss_type_upper = "Market"
        take_profit_type_upper = take_profit_type.capitalize()
        if take_profit_type_upper not in ["Market", "Limit"]:
            self.logger.warning(
                f"Invalid take_profit_type rune '{take_profit_type}'. Defaulting to 'Market'.",
            )
            take_profit_type_upper = "Market"

        # --- Format Quantity and Price runes ---
        qty_str = self.format_quantity(qty)
        if Decimal(qty_str) <= Decimal(
            "0",
        ):  # Check if quantity became zero after formatting
            self.logger.error(
                f"Formatted quantity {qty_str} is zero or negative. Cannot cast order spell.",
            )
            return None

        min_qty = self.get_min_order_qty()
        if min_qty is not None and Decimal(qty_str) < min_qty:
            self.logger.error(
                f"Formatted quantity {qty_str} is below minimum required {min_qty} for {symbol}. Cannot cast spell.",
            )
            return None

        price_str = self.format_price(price) if order_type_upper == "Limit" else None
        sl_str = self.format_price(sl)
        tp_str = self.format_price(tp)
        trigger_price_str = self.format_price(trigger_price)

        # --- Assemble Order Spell Parameters ---
        params: dict[str, Any] = {
            "category": category,
            "symbol": symbol,  # Use simple symbol format
            "side": side_upper,
            "qty": qty_str,
            "orderType": order_type_upper,
            "reduceOnly": reduce_only,
            "positionIdx": position_idx,
            "timeInForce": tif_upper,
            # Generate a unique client order ID if not provided
            "orderLinkId": order_link_id
            if order_link_id
            else f"enh_{int(time.time() * 1000)}"[
                0:36
            ],  # Ensure unique and within Bybit limits
        }

        # Add price if it's a Limit order
        if order_type_upper == "Limit" and price_str is not None:
            params["price"] = price_str

        # Add trigger parameters if provided
        if trigger_price_str is not None and trigger_direction is not None:
            params["triggerPrice"] = trigger_price_str
            params["triggerDirection"] = trigger_direction
            self.logger.debug(
                f"Conditional parameters added: triggerPrice={trigger_price_str}, triggerDirection={trigger_direction}",
            )

        # Add Stop Loss (SL) and Take Profit (TP) parameters if provided
        sl_provided = sl_str is not None
        tp_provided = tp_str is not None
        if sl_provided or tp_provided:
            params["tpslMode"] = "Full"  # Set TP/SL mode (Full/Partial)
            if sl_provided:
                params["stopLoss"] = sl_str
                params["slOrderType"] = stop_loss_type_upper
                # pybit v5 doesn't directly support limit price for SL/TP in order creation, implies Market by default
                if stop_loss_type_upper == "Limit":
                    self.logger.warning(
                        f"Limit SL requested ({sl_str}) but might not be directly supported in order creation. Check API docs.",
                    )
            if tp_provided:
                params["takeProfit"] = tp_str
                params["tpOrderType"] = take_profit_type_upper
                if take_profit_type_upper == "Limit":
                    self.logger.warning(
                        f"Limit TP requested ({tp_str}) but might not be directly supported in order creation. Check API docs.",
                    )

        # --- Log the Spell Details and Cast ---
        side_color = Fore.GREEN if side_upper == "Buy" else Fore.RED
        log_details = f"{side_color}{side_upper}{Style.RESET_ALL} {Style.BRIGHT}{qty_str}{Style.RESET_ALL} {symbol} {order_type_upper}"
        if price_str:
            log_details += f" @{Fore.YELLOW}{price_str}{Style.RESET_ALL}"
        if trigger_price_str:
            trigger_dir_icon = (
                "↑"
                if trigger_direction == 1
                else "↓"
                if trigger_direction == 2
                else "?"
            )
            log_details += f" Trigger@{Fore.CYAN}{trigger_price_str}{Style.RESET_ALL} ({trigger_dir_icon})"
        if sl_str:
            log_details += f" SL@{Fore.RED}{sl_str}{Style.RESET_ALL} ({params.get('slOrderType', 'N/A')})"
        if tp_str:
            log_details += f" TP@{Fore.GREEN}{tp_str}{Style.RESET_ALL} ({params.get('tpOrderType', 'N/A')})"
        if reduce_only:
            log_details += f" {Fore.MAGENTA}(ReduceOnly){Style.RESET_ALL}"
        log_details += f" TIF:{params['timeInForce']}"
        log_details += f" LinkID:{params['orderLinkId']}"

        self.logger.info(f"Casting Order Spell: {log_details}")
        # Log parameters for debugging, omitting sensitive keys
        params_to_log = {
            k: v
            for k, v in params.items()
            if k.lower() not in ["api_key", "api_secret"]
        }
        self.logger.debug(f"Spell Parameters: {params_to_log}")

        try:
            # Cast the spell via pybit's place_order method
            response = self.session.place_order(**params)

            # --- Interpret the Response Runes ---
            if response and response.get("retCode") == 0:
                order_result = response.get("result", {})
                order_id = order_result.get("orderId")
                order_link_id_resp = order_result.get("orderLinkId")
                self.logger.success(
                    f"{Fore.GREEN}Order spell cast successfully! OrderID: {order_id}. LinkID: {order_link_id_resp}{Style.RESET_ALL}",
                )
                # Send SMS notification whisper on success
                sms_msg = f"ORDER OK: {side_upper} {qty_str} {symbol} {order_type_upper}. ID:{order_id[-6:] if order_id else 'N/A'}"
                self.send_sms(sms_msg)
                return order_result

            # Spell casting failed at API level
            err_code = response.get("retCode", "N/A")
            err_msg = response.get("retMsg", "Unknown disturbance")
            self.logger.error(
                f"{Back.RED}{Fore.WHITE}Order spell FAILED! Rune: {err_code}, Message: {err_msg}{Style.RESET_ALL}",
            )
            # Send SMS alert whisper on failure
            sms_msg = f"ORDER FAIL: {side_upper} {qty_str} {symbol}. Code:{err_code}, Msg:{err_msg[:40]}"
            self.send_sms(sms_msg)

            # Provide specific feedback based on common error codes
            if err_code == 110007:
                self.logger.error("Reason: Insufficient available balance.")
            elif err_code in [130021, 130071, 130072]:
                self.logger.error(
                    f"Reason: Risk limit or position size issue. ({err_msg})",
                )
            elif err_code == 10001:  # Parameter error, often symbol related
                if (
                    "symbol not exist" in err_msg.lower()
                    or "invalid symbol" in err_msg.lower()
                ):
                    self.logger.error(
                        f"Reason: Symbol '{symbol}' not found by API. Check symbol name in config.",
                    )
                else:
                    self.logger.error(
                        f"Reason: Parameter error in request. Check formatting/values. ({err_msg})",
                    )
            elif err_code == 110017:  # Order quantity error (e.g., below min)
                min_qty = self.get_min_order_qty()
                qty_step = self.get_qty_step()
                self.logger.error(
                    f"Reason: Order quantity error. MinQty={min_qty}, Step={qty_step}. ({err_msg})",
                )
            elif err_code == 110014:  # Price error (e.g., too low/high, precision)
                price_step = self.get_price_step()
                self.logger.error(
                    f"Reason: Order price error. PriceStep={price_step}. ({err_msg})",
                )
            elif err_code == 130023:  # Order would cause liquidation
                self.logger.error(
                    f"Reason: Order would cause immediate liquidation. ({err_msg})",
                )

            return None  # Indicate failure

        except Exception as e:
            # Catch unexpected interferences during spell casting
            self.logger.exception(f"Exception during order spell casting: {e}")
            sms_msg = f"ORDER EXCEPTION: {side_upper} {qty_str} {symbol}. {str(e)[:50]}"
            self.send_sms(sms_msg)
            return None

    def cancel_order(
        self,
        order_id: str | None = None,
        order_link_id: str | None = None,
        symbol: str | None = None,
    ) -> bool:
        """Dispels a specific order spell by its Bybit Order ID or Client Order ID (orderLinkId).
        Uses the simple symbol format for API calls. Returns True if dispelled or not found, False on error.
        """
        if not order_id and not order_link_id:
            self.logger.error(
                "Cannot dispel order: Either order_id or order_link_id rune must be provided.",
            )
            return False
        if not self.session:
            self.logger.error("pybit session not available for order dispelling.")
            return False

        target_symbol = symbol or self.config.symbol
        cancel_ref = (
            order_id if order_id else order_link_id
        )  # Use the provided reference
        ref_type = "OrderID" if order_id else "LinkID"
        self.logger.info(
            f"{Fore.YELLOW}Attempting to dispel order '{cancel_ref}' ({ref_type}) for {target_symbol}...{Style.RESET_ALL}",
        )

        # Prepare parameters for the cancel_order API call
        params: dict[str, Any] = {
            "category": "linear",
            "symbol": target_symbol,  # Use simple symbol format
        }
        if order_id:
            params["orderId"] = order_id
        elif order_link_id:
            params["orderLinkId"] = order_link_id

        try:
            response = self.session.cancel_order(**params)

            # Interpret the response runes
            if response and response.get("retCode") == 0:
                # API reported success
                result_data = response.get("result", {})
                result_id = result_data.get("orderId", "N/A")
                result_link_id = result_data.get("orderLinkId", "N/A")
                self.logger.success(
                    f"Order '{cancel_ref}' dispelled successfully (Response ID: {result_id}, LinkID: {result_link_id}).",
                )
                return True
            # API call failed or order not found/cancellable
            err_code = response.get("retCode")
            err_msg = response.get("retMsg", "Unknown disturbance")

            # Check for common "Order not found" runes/messages
            order_not_found_codes = {110001}  # Common code for order not found
            order_not_found_msgs = [
                "order not found",
                "order is not cancellable",
                "order does not exist",
            ]

            is_not_found = err_code in order_not_found_codes or any(
                msg in err_msg.lower() for msg in order_not_found_msgs
            )

            if is_not_found:
                # If order not found or inactive, consider it "dispelled" from our perspective
                self.logger.warning(
                    f"Order '{cancel_ref}' not found or already inactive/non-cancellable (Rune: {err_code}, Msg: {err_msg}). Considered dispelled.",
                )
                return True
            # Check for symbol error
            if err_code == 10001 and (
                "symbol not exist" in err_msg.lower()
                or "invalid symbol" in err_msg.lower()
            ):
                self.logger.error(
                    f"Failed to dispel order '{cancel_ref}': Symbol '{target_symbol}' not found by API. (Rune: {err_code})",
                )
            else:
                self.logger.error(
                    f"Failed to dispel order '{cancel_ref}'. Rune: {err_code}, Message: {err_msg}",
                )
            return False  # Genuine dispelling failure

        except Exception as e:
            # Catch unexpected interferences during the dispelling ritual
            self.logger.exception(f"Exception dispelling order '{cancel_ref}': {e}")
            return False

    def cancel_all_orders(
        self, symbol: str | None = None, order_filter: str | None = None,
    ) -> bool:
        """Dispels all open order spells for the specified symbol, with optional filtering.
        Uses the simple symbol format for API calls.
        """
        target_symbol = symbol or self.config.symbol
        self.logger.info(
            f"{Fore.RED + Style.BRIGHT}Attempting to dispel ALL orders for {target_symbol} (Filter: {order_filter or 'All'})...{Style.RESET_ALL}",
        )
        if not self.session:
            self.logger.error("pybit session not available for mass order dispelling.")
            return False
        try:
            params: dict[str, Any] = {
                "category": "linear",
                "symbol": target_symbol,  # Use simple symbol format
            }
            # Apply filter if provided (e.g., 'Order', 'StopOrder', 'tpslOrder')
            if order_filter:
                valid_filters = ["Order", "StopOrder", "tpslOrder"]
                if order_filter not in valid_filters:
                    self.logger.warning(
                        f"Invalid order_filter '{order_filter}'. Must be one of {valid_filters}. Proceeding without filter.",
                    )
                else:
                    params["orderFilter"] = order_filter

            response = self.session.cancel_all_orders(**params)

            # Interpret the response runes
            if response and response.get("retCode") == 0:
                # API reported success, check result details
                result_data = response.get("result", {})
                cancelled_list = result_data.get(
                    "list", [],
                )  # List of cancelled order IDs
                success_indicator = result_data.get(
                    "success",
                )  # Boolean flag for overall success

                if cancelled_list:
                    count = len(cancelled_list)
                    # Log first few cancelled order IDs for reference
                    ids_short = [
                        str(item.get("orderId", "N/A"))[-6:]
                        for item in cancelled_list[: min(count, 5)]
                    ]
                    self.logger.success(
                        f"Successfully dispelled {count} order(s) for {target_symbol}. Example IDs ending in: {ids_short}...",
                    )
                    return True
                if success_indicator is not None:
                    # If success flag is present, rely on that
                    if success_indicator is True or str(success_indicator) == "1":
                        self.logger.success(
                            f"Mass dispel request acknowledged successfully by API for {target_symbol} (may indicate no matching orders were open).",
                        )
                        return True
                    self.logger.warning(
                        f"Mass dispel request returned success=False/0 but retCode=0 for {target_symbol}. Response: {response}",
                    )
                    return True  # Consider it successful if API reported no error code
                # Success code but no details - likely no orders matched the filter
                self.logger.info(
                    f"Mass dispel request successful (retCode 0), but no specific details returned for {target_symbol}. Likely no matching orders found.",
                )
                return True
            # API call failed
            err_code = response.get("retCode")
            err_msg = response.get("retMsg", "Unknown disturbance")
            # Check for symbol errors first
            if err_code == 10001 and (
                "symbol not exist" in err_msg.lower()
                or "invalid symbol" in err_msg.lower()
            ):
                self.logger.error(
                    f"Failed to dispel all orders: Symbol '{target_symbol}' not found by API. (Rune: {err_code})",
                )
                return False
            # Check for order not found errors
            order_not_found_codes = {110001}
            order_not_found_msgs = [
                "order not found",
                "order is not cancellable",
                "order does not exist",
            ]
            is_not_found = err_code in order_not_found_codes or any(
                msg in err_msg.lower() for msg in order_not_found_msgs
            )

            if is_not_found:
                self.logger.info(
                    f"No matching orders found to cancel for {target_symbol} (Rune: {err_code}, Msg: {err_msg}). Considered dispelled.",
                )
                return True  # If order not found, it's effectively "dispelled" from open state
            # Genuine failure
            self.logger.error(
                f"Failed to dispel all orders for {target_symbol}. Rune: {err_code}, Message: {err_msg}",
            )
            return False

        except Exception as e:
            self.logger.exception(
                f"Exception during mass order dispelling for {target_symbol}: {e}",
            )
            return False

    # --- Utilities - Lesser Incantations ---
    def send_sms(self, message: str) -> bool:
        """Sends an SMS whisper using Termux API, respecting cooldown and length limits."""
        if (
            not self.config.notifications.termux_sms.enabled
            or not self.config.notifications.termux_sms.phone_number
        ):
            # SMS feature is disabled or phone number is not configured
            return False

        current_time = time.time()
        # Check cooldown period
        if (
            current_time - self.last_sms_time
            < self.config.notifications.termux_sms.cooldown
        ):
            self.logger.debug("SMS cooldown active. Skipping send.")
            return False

        # Prepare message: truncate if too long, add prefix
        max_len = 140  # Standard SMS limit, though modern ones are longer
        prefix = self.config.notifications.termux_sms.message_prefix
        truncated_message = (
            message[:max_len] + "..." if len(message) > max_len else message
        )
        full_message = f"{prefix} {truncated_message}"
        phone_number = self.config.notifications.termux_sms.phone_number

        self.logger.debug(f"Attempting to send SMS to {phone_number}...")
        try:
            # Construct the command to execute termux-sms-send
            # Using subprocess.run for better control over output and error handling
            cmd_list = ["termux-sms-send", "-n", phone_number, full_message]
            self.logger.debug(f"Executing SMS command list: {cmd_list}")

            # Execute the command in a background thread to avoid blocking
            def _run_sms_command_thread(cmd: list[str], phone: str, msg: str):
                try:
                    # Execute command with timeout, capture output, check for errors
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=15,
                        check=False,
                        encoding="utf-8",
                    )  # 15 sec timeout

                    if result.returncode == 0:
                        self.last_sms_time = (
                            time.time()
                        )  # Update cooldown timer on success
                        self.logger.info(
                            f"{Fore.GREEN}SMS whisper sent successfully to {phone}: {msg}{Style.RESET_ALL}",
                        )
                    else:
                        # Log errors from termux-sms-send
                        error_output = (
                            result.stderr.strip()
                            if result.stderr
                            else result.stdout.strip()
                        )
                        self.logger.error(
                            f"{Fore.RED}Termux SMS command failed! Return Code: {result.returncode}. Output: {error_output}{Style.RESET_ALL}",
                        )
                        # Provide hints for common issues
                        if (
                            "command not found" in error_output.lower()
                            or "usage: termux-sms-send" in error_output.lower()
                            or "permission denied" in error_output.lower()
                        ):
                            self.logger.error(
                                f"{Fore.RED}Hint: 'termux-sms-send' command not found or permission denied. Ensure Termux:API package is installed and permissions are granted.{Style.RESET_ALL}",
                            )
                except subprocess.TimeoutExpired:
                    self.logger.error(
                        f"{Fore.RED}Termux SMS command timed out after 15 seconds.{Style.RESET_ALL}",
                    )
                except FileNotFoundError:
                    self.logger.error(
                        f"{Fore.RED}'termux-sms-send' command not found. Is Termux:API installed and in PATH?{Style.RESET_ALL}",
                    )
                except Exception as e:
                    self.logger.exception(
                        f"Unexpected error during SMS command execution: {e}",
                    )

            sms_thread = threading.Thread(
                target=_run_sms_command_thread,
                args=(cmd_list, phone_number, full_message),
                daemon=True,
            )
            sms_thread.start()
            return True  # SMS sending initiated

        except Exception as e:
            self.logger.exception(
                f"Unexpected error preparing SMS whisper command: {e}",
            )
            return False

    def diagnose(self) -> bool:
        """Runs diagnostic checks for API connectivity, configuration, and basic functionality."""
        self.logger.info(
            f"\n{Fore.MAGENTA + Style.BRIGHT}--- Running Diagnostics ---{Style.RESET_ALL}",
        )
        passed_checks = 0
        total_checks = 0
        results = []  # Store check results for summary

        # Check 1: Server Time Sync
        total_checks += 1
        check_name = "Server Time Sync"
        server_time = self.get_server_time()
        if server_time is not None:
            results.append((check_name, True, "Server time check successful."))
            passed_checks += 1
        else:
            results.append((check_name, False, "Server time check failed."))

        # Check 2: Market Info Load
        total_checks += 1
        check_name = f"Market Info Load ({self.config.symbol})"
        if not self.market_info:
            self._load_market_info()  # Ensure market info is loaded if missing
        if self.market_info and self.market_info.get("symbol") == self.config.symbol:
            results.append(
                (
                    check_name,
                    True,
                    "Market info loaded successfully. Precision/Limits available.",
                ),
            )
            passed_checks += 1
        else:
            results.append(
                (
                    check_name,
                    False,
                    f"Market info load failed or symbol mismatch. Check BOT_SYMBOL ('{self.config.symbol}' not found?).",
                ),
            )

        # Check 3: Balance Fetch (Tests API authentication and basic access)
        total_checks += 1
        check_name = "Balance Fetch (API Auth)"
        balance = self.fetch_balance()  # Fetches USDT balance by default
        if (
            balance is not None
        ):  # Check if the API call succeeded, not the balance value itself
            results.append((check_name, True, "API call OK. Balance fetch successful."))
            passed_checks += 1
        else:
            results.append(
                (
                    check_name,
                    False,
                    "Balance fetch failed (API call error). Check API keys/permissions.",
                ),
            )

        # Check 4: Leverage Setting (Informational, tests write capability)
        self.logger.info(
            f"{Fore.CYAN}# Checking leverage setting (informational)...{Style.RESET_ALL}",
        )
        leverage_set_ok = self._set_leverage()
        self.logger.info(
            f"Leverage setting check result: {'OK/Already Set' if leverage_set_ok else 'Failed/Warning (see logs)'}",
        )
        # This check's pass/fail isn't critical for overall diagnostics but provides useful feedback.

        # Check 5: WebSocket Instance Creation
        total_checks += 1
        check_name = "WebSocket Instance Creation"
        self._init_websocket_instance()  # Attempt to create the WS instance
        if self.ws:
            results.append(
                (check_name, True, "WebSocket instance created successfully."),
            )
            passed_checks += 1
        else:
            results.append((check_name, False, "WebSocket instance creation failed."))

        # Check 6: Quick WebSocket Connection Test (Simplified)
        # A full connection test is complex due to threading. We focus on confirming the instance can be prepared.
        total_checks += 1
        check_name = "WebSocket Connection Viability"
        self.logger.info(
            f"{Fore.CYAN}# Checking WebSocket connection viability...{Style.RESET_ALL}",
        )
        ws_test_passed = False
        pybit_tf = self._map_timeframe_to_pybit(self.config.timeframe)
        test_topics: list[str] = []
        if pybit_tf:
            # Use simple symbol format for WS topics
            test_topic = f"kline.{pybit_tf}.{self.config.symbol}"
            test_topics = [test_topic]
        else:
            self.logger.error(
                f"Invalid primary timeframe '{self.config.timeframe}' for WS topic.",
            )

        # Temporarily isolate WS state to perform test without affecting main loop state
        original_ws_state = self._isolate_ws_state_for_test()

        test_result = {"passed": False, "error": ""}
        try:
            if self.ws and test_topics:
                # Register minimal handlers for the test connection
                test_message_cb = lambda msg: self.logger.debug(
                    f"WS Test Message: {msg}",
                )
                test_error_cb = lambda err: self.logger.error(f"WS Test Error: {err}")
                # Use dummy callbacks for open/close to simplify test
                self.connect_websocket(
                    test_topics,
                    test_message_cb,
                    error_cb=test_error_cb,
                    open_callback=lambda: setattr(self, "_ws_test_open", True),
                    close_callback=lambda: setattr(self, "_ws_test_closed", True),
                )
                # Wait briefly for connection attempt
                time.sleep(3)  # Small delay to allow connection attempt
                if (
                    self.ws_connected
                ):  # Check if connection was established and callbacks fired
                    test_result["passed"] = True
                    test_result["error"] = "Connection seemed to establish."
                else:
                    test_result["error"] = "Connection attempt did not report success."
            else:
                test_result["error"] = "Skipped: WS instance or topics missing."
        except Exception as e:
            self.logger.exception("Exception during WebSocket test execution.")
            test_result["error"] = f"Exception during test: {e}"
        finally:
            # Restore original WS state using the stored values
            self._restore_ws_state(original_ws_state)
            self.logger.debug("WS Test: Original WS state restored.")

        if test_result["passed"]:
            results.append((check_name, True, test_result["error"]))
            passed_checks += 1
        else:
            results.append(
                (check_name, False, f"WS test failed: {test_result['error']}"),
            )

        # Check 7: Basic OHLCV Fetch
        total_checks += 1
        check_name = f"OHLCV Fetch ({self.config.timeframe})"
        try:
            fetch_limit_ohlcv = max(
                50,
                self.config.sma_long + 5,
                self.config.atr_period + 5,
                self.config.adx_period + 5,
                200,
            )  # Ensure enough history
            test_ohlcv_df = bybit_client.get_or_fetch_ohlcv(
                self.config.timeframe,
                limit=fetch_limit_ohlcv,
                include_daily_pivots=False,
            )  # No pivots needed for this test
            if (
                not test_ohlcv_df.empty
                and len(test_ohlcv_df) >= fetch_limit_ohlcv * 0.8
            ):  # Check if a substantial amount was fetched
                results.append(
                    (
                        check_name,
                        True,
                        f"OHLCV fetch successful ({len(test_ohlcv_df)} candles).",
                    ),
                )
                passed_checks += 1
            else:
                results.append(
                    (
                        check_name,
                        False,
                        f"OHLCV fetch returned empty or insufficient data ({len(test_ohlcv_df)} fetched, expected ~{fetch_limit_ohlcv}).",
                    ),
                )
        except Exception as e:
            self.logger.exception("Exception during OHLCV fetch test.")
            results.append((check_name, False, f"Exception during OHLCV fetch: {e}"))

        # Check 8: Daily OHLCV Fetch (for Pivots)
        total_checks += 1
        check_name = "Daily OHLCV Fetch (Pivots)"
        try:
            # Fetch a small amount of daily data for testing pivots
            test_daily_ohlcv_df = bybit_client.get_or_fetch_daily_ohlcv(limit=5)
            if (
                not test_daily_ohlcv_df.empty and len(test_daily_ohlcv_df) >= 2
            ):  # Need at least 2 days for pivots
                results.append(
                    (
                        check_name,
                        True,
                        f"Daily OHLCV fetch successful ({len(test_daily_ohlcv_df)} candles).",
                    ),
                )
                passed_checks += 1
            else:
                results.append(
                    (
                        check_name,
                        False,
                        f"Daily OHLCV fetch returned empty or insufficient data ({len(test_daily_ohlcv_df)} fetched, need at least 2).",
                    ),
                )
        except Exception as e:
            self.logger.exception("Exception during Daily OHLCV fetch test.")
            results.append(
                (check_name, False, f"Exception during Daily OHLCV fetch: {e}"),
            )

        # Check 9: Indicators Calculation Test
        total_checks += 1
        check_name = "Indicators Calculation"
        try:
            # Need a decent history slice to test indicator calculations
            ohlcv_slice_for_test = None
            daily_df_for_test = None
            with self._cache_lock:  # Access cache safely
                pybit_tf_key = bybit_client._map_timeframe_to_pybit(config.timeframe)
                if pybit_tf_key and bybit_client.ohlcv_cache.get(pybit_tf_key):
                    ohlcv_slice_for_test = bybit_client.ohlcv_cache.get(
                        pybit_tf_key,
                    ).copy()
                daily_cache = bybit_client.daily_ohlcv_cache
                if daily_cache is not None and not daily_cache.empty:
                    daily_df_for_test = daily_cache.copy()

            min_needed_for_indicators = max(
                config.initial_candle_history,
                config.sma_long + 10,
                config.atr_period + 10,
                config.adx_period + 10,
                200,
            )
            # If cache doesn't have enough data, try fetching it
            if (
                ohlcv_slice_for_test is None
                or len(ohlcv_slice_for_test) < min_needed_for_indicators
            ):
                logger.debug(
                    "Not enough cached OHLCV data for indicator test. Refetching...",
                )
                ohlcv_slice_for_test = bybit_client.get_or_fetch_ohlcv(
                    config.timeframe,
                    limit=min_needed_for_indicators,
                    include_daily_pivots=True,
                )
                # Re-fetch daily data if needed for pivots
                if (
                    config.analysis_modules.mtf_analysis.enabled
                    or config.indicators.fibonacci_pivot_points
                ) and (daily_df_for_test is None or daily_df_for_test.empty):
                    daily_df_for_test = bybit_client.get_or_fetch_daily_ohlcv()

            if (
                ohlcv_slice_for_test is not None
                and not ohlcv_slice_for_test.empty
                and len(ohlcv_slice_for_test) >= min_needed_for_indicators
            ):
                # Run the indicator calculation on the data slice
                test_indicators_df = calculate_indicators(
                    ohlcv_slice_for_test.copy(), config, daily_df_for_test,
                )

                if test_indicators_df is not None and not test_indicators_df.empty:
                    # Check if key indicators and structure elements were populated
                    sample_cols_to_check = [
                        "ATR",
                        "SMA_Short",
                        "SMA_Long",
                        "MACD_Line",
                        "RSI",
                        "Fisher_Price",
                        "Pivot",
                        "Resistance",
                        "Support",
                        "Is_Bullish_OB",
                        "Is_Bearish_OB",
                    ]
                    found_valid_indicator = False
                    # Check the last few rows for any non-NaN indicator values
                    check_tail = test_indicators_df.tail(10)
                    for col in sample_cols_to_check:
                        if (
                            col in test_indicators_df.columns
                            and pd.api.types.is_numeric_dtype(test_indicators_df[col])
                        ):
                            if (
                                test_indicators_df[col].notna().any()
                            ):  # Check if any value in the column is not NaN
                                found_valid_indicator = True
                                break
                    if found_valid_indicator:
                        results.append(
                            (
                                check_name,
                                True,
                                "Indicators calculated successfully. Key indicators populated.",
                            ),
                        )
                        passed_checks += 1
                    else:
                        results.append(
                            (
                                check_name,
                                False,
                                "Indicators calculated, but sample results are all NaN. Check data/config.",
                            ),
                        )
                else:
                    results.append(
                        (
                            check_name,
                            False,
                            "calculate_indicators returned empty or None.",
                        ),
                    )
            else:
                results.append(
                    (
                        check_name,
                        False,
                        f"Not enough OHLCV data available/fetched ({len(ohlcv_slice_for_test) if ohlcv_slice_for_test is not None else 0} < {min_needed_for_indicators}) for indicator test.",
                    ),
                )

        except ImportError:
            results.append(
                (
                    check_name,
                    False,
                    "Indicators module (indicators.py) not found or failed to import.",
                ),
            )
        except Exception as e:
            logger.exception("Exception during indicator calculation test.")
            results.append(
                (check_name, False, f"Exception during indicator calculation: {e}"),
            )

        # Check 10: Termux SMS Sending (if enabled)
        if config.notifications.termux_sms.enabled:
            total_checks += 1
            check_name = "Termux SMS Send"
            test_message = f"Bybit Bot Diag Test @ {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S %Z')}"
            logger.info(
                f"{Fore.CYAN}# Attempting test SMS (respects cooldown, runs in background)...{Style.RESET_ALL}",
            )
            sms_initiated = False
            try:
                # Check cooldown first
                current_time = time.time()
                if (
                    current_time - bybit_client.last_sms_time
                    >= bybit_client.config.notifications.termux_sms.cooldown
                ):
                    sms_initiated = bybit_client.send_sms(test_message)  # Send SMS
                else:
                    logger.debug("SMS cooldown active. Skipping test send.")
            except Exception as e:
                logger.warning(f"Error during SMS test attempt: {e}")

            if sms_initiated:
                results.append(
                    (
                        check_name,
                        True,
                        "Test SMS initiated (check phone/logs for outcome).",
                    ),
                )
                passed_checks += 1
            else:
                results.append(
                    (
                        check_name,
                        False,
                        "Test SMS initiation failed or skipped (check config/cooldown/logs).",
                    ),
                )

        # --- Diagnostics Summary ---
        logger.info(
            f"\n{Fore.MAGENTA + Style.BRIGHT}--- Diagnostics Summary ---{Style.RESET_ALL}",
        )
        for name, success, msg in results:
            status_color = Fore.GREEN if success else Fore.RED
            status_icon = "[PASS]" if success else "[FAIL]"
            message_color = Fore.GREEN if success else Fore.RED
            logger.info(
                f"{status_color}{status_icon:<6}{Style.RESET_ALL} {name:<35}:{message_color} {msg}{Style.RESET_ALL}",
            )

        # Define essential checks that must pass for the bot to operate safely
        essential_check_names = {
            "Server Time Sync",
            f"Market Info Load ({config.symbol})",
            "Balance Fetch (API Auth)",
            "WebSocket Instance Creation",
            "WebSocket Connection Viability",
            f"OHLCV Fetch ({config.timeframe})",
            "Daily OHLCV Fetch (Pivots)",
            "Indicators Calculation",
        }
        # Check if all essential checks passed
        essential_results = [
            success for name, success, msg in results if name in essential_check_names
        ]
        essential_passed = (
            all(essential_results) if essential_results else False
        )  # Ensure there were essential checks to pass

        total_passed_count = sum(1 for _, success, _ in results if success)
        total_run_count = len(results)

        if essential_passed:
            failed_non_essential = [
                name
                for name, success, msg in results
                if not success and name not in essential_check_names
            ]
            minor_issues_msg = (
                f" Minor issues detected: {', '.join(failed_non_essential)}."
                if failed_non_essential
                else ""
            )
            logger.success(
                f"\n{Fore.GREEN + Style.BRIGHT}All ESSENTIAL diagnostics PASSED ({total_passed_count}/{total_run_count} total checks).{minor_issues_msg}{Style.RESET_ALL}",
            )
            return True  # Diagnostics passed
        failed_essential = [
            name
            for name, success, msg in results
            if not success and name in essential_check_names
        ]
        logger.error(
            f"\n{Fore.RED + Style.BRIGHT}Diagnostics FAILED. {total_passed_count}/{total_run_count} total checks PASSED.{Style.RESET_ALL}",
        )
        logger.error(
            f"{Fore.RED}Essential checks failed: {', '.join(failed_essential)}{Style.RESET_ALL}",
        )
        logger.error(
            f"{Fore.RED}Review the [FAIL] items above and consult the logs for detailed error messages.{Style.RESET_ALL}",
        )
        return False  # Diagnostics failed

    def _isolate_ws_state_for_test(self) -> dict:
        """Saves current WS state and resets it for a temporary test."""
        with self._ws_lock:
            original_state = {
                "ws": self.ws,
                "ws_connected": self.ws_connected,
                "ws_connecting": self.ws_connecting,
                "ws_topics": self.ws_topics[:],
                "ws_user_callbacks": self.ws_user_callbacks.copy(),
                "ws_reconnect_attempt": self.ws_reconnect_attempt,
            }
            # Reset for test
            self.ws = None
            self.ws_connected = False
            self.ws_connecting = False
            self.ws_topics = []
            self.ws_user_callbacks = {}
            self.ws_reconnect_attempt = 0
            return original_state

    def _restore_ws_state(self, original_state: dict) -> None:
        """Restores the WebSocket state from saved values."""
        with self._ws_lock:
            self.ws = original_state.get("ws")
            self.ws_connected = original_state.get("ws_connected", False)
            self.ws_connecting = original_state.get("ws_connecting", False)
            self.ws_topics = original_state.get("ws_topics", [])
            self.ws_user_callbacks = original_state.get("ws_user_callbacks", {})
            self.ws_reconnect_attempt = original_state.get("ws_reconnect_attempt", 0)

    def _map_timeframe_to_pybit(self, timeframe: str) -> str | None:
        """Maps user-friendly timeframe strings (e.g., '15m') to Bybit API v5 format (e.g., '15')."""
        return self.PYBIT_TIMEFRAME_MAP.get(timeframe.lower())

    def _map_timeframe_from_pybit(self, api_timeframe: str) -> str:
        """Maps Bybit API v5 timeframe format (e.g., '15') back to user-friendly string (e.g., '15m')."""
        return self._API_TIMEFRAME_MAP_INV.get(
            api_timeframe, api_timeframe,
        )  # Fallback to API format if not mapped

    def fetch_ohlcv(
        self,
        timeframe: str,
        limit: int = 200,
        symbol: str | None = None,
        since: int | None = None,
        limit_per_request: int = 1000,
    ) -> pd.DataFrame:
        """Fetches OHLCV data using ccxt, handling pagination, retries, and data cleaning.
        Returns a DataFrame scroll with essential columns converted to Decimal. Uses simple symbol format.
        """
        target_symbol = symbol or self.config.symbol  # Symbol from config or argument
        ccxt_timeframe = self._map_timeframe_to_pybit(
            timeframe,
        )  # Convert user timeframe to API format for ccxt

        if not ccxt_timeframe:
            self.logger.error(
                f"Invalid timeframe '{timeframe}' cannot be mapped to API format. Cannot fetch OHLCV.",
            )
            return pd.DataFrame()

        self.logger.debug(
            f"{Fore.CYAN}# Fetching OHLCV data via ccxt oracle | Symbol: {target_symbol}, TF: {timeframe} (API: {ccxt_timeframe}), Limit: {limit}, Since: {pd.to_datetime(since, unit='ms') if since else 'Latest'}{Style.RESET_ALL}",
        )
        if not self.exchange:
            self.logger.error("CCXT oracle not initialized. Cannot fetch OHLCV.")
            return pd.DataFrame()

        all_ohlcv: list[list[Any]] = []  # Accumulator for OHLCV data across pages
        fetch_count = 0
        retries = 0
        max_retries = self.config.retry_count
        retry_delay_secs = self.config.retry_delay
        current_since = since  # Track pagination start time

        # Loop to fetch data in chunks if needed (primarily for historical fetches)
        while fetch_count < limit and retries <= max_retries:
            try:
                # Determine chunk size: use limit_per_request for pagination, otherwise request the full limit
                current_fetch_limit = limit_per_request if since is not None else limit

                self.logger.debug(
                    f"  Fetching chunk {fetch_count // limit_per_request + 1 if since is not None else 1}, Limit: {current_fetch_limit}, Since: {pd.to_datetime(current_since, unit='ms').strftime('%Y-%m-%d %H:%M:%S %Z') if current_since is not None else 'Latest'}",
                )

                # Call ccxt's fetch_ohlcv, specifying category for Bybit v5
                ohlcv_chunk = self.exchange.fetch_ohlcv(
                    target_symbol,
                    ccxt_timeframe,  # ccxt handles internal timeframe mapping
                    since=current_since,  # Pagination start time
                    limit=current_fetch_limit,  # Candles per request
                    params={
                        "category": "linear",
                    },  # Specify 'linear' category for Bybit v5
                )

                # Check if oracle returned any data
                if not ohlcv_chunk:
                    self.logger.info(
                        f"Oracle returned no more data for {target_symbol} ({timeframe}) {'since ' + str(pd.to_datetime(current_since, unit='ms')) if current_since is not None else 'latest'}.",
                    )
                    break  # Exit loop if no data is returned

                # Process the fetched chunk
                if since is not None:
                    # If fetching history, append new data and update 'since' for the next page
                    all_ohlcv.extend(ohlcv_chunk)
                    current_since = (
                        ohlcv_chunk[-1][0] + 1
                    )  # Next 'since' is last candle's timestamp + 1ms
                else:
                    # If fetching latest data without 'since', ccxt handles pagination internally for 'limit'
                    all_ohlcv = ohlcv_chunk
                    fetch_count = len(all_ohlcv)  # Update count for loop condition
                    break  # Exit loop after fetching the latest block

                fetch_count += len(ohlcv_chunk)
                retries = 0  # Reset retries on successful fetch

                # Gentle delay between paginated requests if fetching history
                if since is not None:
                    time.sleep(
                        self.config.retry_delay * 0.5,
                    )  # Shorter delay between successful pages

            # --- Handle Specific CCXT Errors with Retries ---
            except ccxt.RateLimitExceeded as e:
                retries += 1
                wait_time = self.config.retry_delay * (
                    2 ** (retries - 1)
                )  # Exponential backoff
                self.logger.warning(
                    f"{Fore.YELLOW}Rate limit hit fetching OHLCV page (attempt {retries}/{max_retries}): {e}. Waiting {wait_time:.1f}s...{Style.RESET_ALL}",
                )
                time.sleep(wait_time)
            except (
                ccxt.NetworkError,
                ccxt.ExchangeNotAvailable,
                ccxt.RequestTimeout,
                ccxt.DDoSProtection,
            ) as e:
                retries += 1
                wait_time = self.config.retry_delay * (
                    2 ** (retries - 1)
                )  # Exponential backoff
                self.logger.warning(
                    f"{Fore.YELLOW}Network/Exchange disturbance fetching OHLCV page (attempt {retries}/{max_retries}): {e}. Waiting {wait_time:.1f}s...{Style.RESET_ALL}",
                )
                time.sleep(wait_time)
            except ccxt.ExchangeError as e:
                # Most other exchange errors are treated as non-retryable to prevent infinite loops on bad config
                self.logger.error(
                    f"{Fore.RED}Non-retryable CCXT ExchangeError fetching OHLCV for {target_symbol} ({timeframe}): {e}{Style.RESET_ALL}",
                    exc_info=True,
                )
                break  # Stop fetching on non-retryable errors
            except Exception as e:
                # Catch any other unexpected exceptions during fetching
                self.logger.exception(
                    f"Unexpected error during OHLCV fetch pagination: {e}",
                )
                break  # Stop on unexpected errors

        # Report if max retries were exceeded
        if retries > max_retries:
            self.logger.error(
                f"Exceeded max retries ({max_retries}) fetching OHLCV data for {target_symbol} ({timeframe}). Returning partial data if any.",
            )

        # If no data was collected after all attempts
        if not all_ohlcv:
            self.logger.warning(
                f"No OHLCV data collected after all attempts for {target_symbol} ({timeframe}).",
            )
            return pd.DataFrame()

        # --- Data Conversion and Cleaning ---
        # Convert collected data into a DataFrame
        df = pd.DataFrame(
            all_ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"],
        )

        # Convert timestamp column to datetime objects, localized to UTC
        try:
            df["timestamp"] = pd.to_datetime(
                df["timestamp"], unit="ms", utc=True, errors="coerce",
            )
        except Exception as e:
            self.logger.error(
                f"Error converting OHLCV timestamps to datetime: {e}. Raw timestamps: {df['timestamp'].head().tolist()}",
                exc_info=True,
            )
            return pd.DataFrame()  # Return empty if timestamps fail

        # Convert essential numeric columns to Decimal for financial precision
        numeric_cols = ["open", "high", "low", "close", "volume"]
        for col in numeric_cols:
            try:
                # Use errors='coerce' to handle potential non-numeric data gracefully
                df[col] = pd.to_numeric(df[col], errors="coerce").apply(
                    lambda x: Decimal(str(x)) if pd.notna(x) else np.nan,
                )
            except Exception as e:
                self.logger.error(
                    f"Error converting column '{col}' to Decimal: {e}", exc_info=True,
                )
                df[col] = np.nan  # Set column to NaN if conversion fails

        # Drop rows where essential data (like close price) might be NaN after conversion
        df.dropna(subset=["timestamp"] + numeric_cols, inplace=True)

        # Check if DataFrame became empty after cleaning
        if df.empty:
            self.logger.warning(
                f"OHLCV data for {target_symbol} ({timeframe}) became empty after cleaning NaNs/NaTs.",
            )
            return pd.DataFrame()

        # Ensure data is sorted by timestamp and remove any potential duplicates (defensive warding)
        df = (
            df.sort_values(by="timestamp")
            .drop_duplicates(subset=["timestamp"], keep="last")
            .reset_index(drop=True)
        )

        # Limit the final DataFrame to the requested 'limit' if fetching backwards
        if since is None and len(df) > limit:
            self.logger.info(
                f"Fetched {len(df)} candles, trimming to requested limit of {limit}.",
            )
            df = df.tail(limit).reset_index(drop=True)

        self.logger.info(
            f"Successfully fetched and processed {len(df)} OHLCV candles for {target_symbol} ({timeframe}). First: {df['timestamp'].iloc[0].strftime('%Y-%m-%d %H:%M:%S %Z')}, Last: {df['timestamp'].iloc[-1].strftime('%Y-%m-%d %H:%M:%S %Z')}",
        )
        return df

    def get_or_fetch_daily_ohlcv(
        self, symbol: str | None = None, limit: int = 365 * 3,
    ) -> pd.DataFrame:
        """Retrieves Daily OHLCV data, using cache if fresh, otherwise fetching and caching.
        Essential for Daily Pivot Point calculations. Uses simple symbol format.
        """
        target_symbol = symbol or self.config.symbol
        daily_timeframe_api = "D"  # API format for Daily timeframe

        cached_df = None
        # Acquire lock to safely read the daily cache
        with self._cache_lock:
            cached_df = self.daily_ohlcv_cache

        fetch_needed = False
        cache_is_fresh = False
        now_utc = datetime.now(UTC)
        # Define start of the current UTC day for freshness check
        start_of_today_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

        if cached_df is not None and not cached_df.empty:
            try:
                # Check the timestamp of the last candle in the cache
                last_candle_timestamp = cached_df["timestamp"].iloc[-1]
                # Ensure timestamp is timezone-aware (UTC)
                if last_candle_timestamp.tzinfo is None:
                    last_candle_timestamp = last_candle_timestamp.tz_localize("UTC")
                else:
                    last_candle_timestamp = last_candle_timestamp.tz_convert("UTC")

                # If the last candle is from today UTC, the cache is considered fresh
                if last_candle_timestamp >= start_of_today_utc:
                    cache_is_fresh = True
                    self.logger.debug(
                        f"Using cached Daily OHLCV for {target_symbol} (Last candle: {last_candle_timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}).",
                    )
                else:
                    self.logger.info(
                        f"Cached Daily OHLCV for {target_symbol} is stale (Last: {last_candle_timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}, Start Today: {start_of_today_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}). Fetching fresh data.",
                    )
                    fetch_needed = True
            except Exception as e:
                self.logger.warning(
                    f"Error checking Daily cache freshness for {target_symbol}: {e}. Fetching new data.",
                )
                fetch_needed = True
        else:
            self.logger.info(
                f"No cached Daily OHLCV data for {target_symbol}. Fetching initial data.",
            )
            fetch_needed = True

        # Fetch data if needed
        if fetch_needed:
            self.logger.debug(
                f"{Fore.CYAN}# Fetching Daily OHLCV data for {target_symbol}...{Style.RESET_ALL}",
            )
            # Fetch a generous amount of daily data for historical analysis
            df_raw = self.fetch_ohlcv(
                timeframe="1d", limit=max(limit, 300), symbol=target_symbol,
            )  # Use '1d' for daily

            if not df_raw.empty:
                with self._cache_lock:  # Acquire lock to update cache
                    # Cache the fetched daily data, trimmed to max size
                    self.daily_ohlcv_cache = (
                        df_raw.tail(self.max_daily_ohlcv_cache_size)
                        .reset_index(drop=True)
                        .copy()
                    )
                self.logger.info(
                    f"Fetched and cached {len(self.daily_ohlcv_cache)} Daily OHLCV candles for {target_symbol}.",
                )
                cache_is_fresh = True
                with self._cache_lock:  # Re-read cache after update
                    cached_df = (
                        self.daily_ohlcv_cache.copy()
                        if self.daily_ohlcv_cache is not None
                        else pd.DataFrame()
                    )
            else:
                self.logger.error(
                    f"Failed to fetch Daily OHLCV data for {target_symbol}. Daily cache not updated.",
                )
                # If fetching fails but cache exists, use the stale cache with a warning
                if cached_df is not None and not cached_df.empty:
                    self.logger.warning(
                        "Using potentially stale Daily cache due to fetch failure.",
                    )
                    with self._cache_lock:
                        return (
                            self.daily_ohlcv_cache.copy()
                            if self.daily_ohlcv_cache is not None
                            else pd.DataFrame()
                        )
                else:
                    return pd.DataFrame()  # Return empty if no cache and fetch failed

        # Return the cached data if it's fresh
        if cache_is_fresh and cached_df is not None and not cached_df.empty:
            with self._cache_lock:
                return self.daily_ohlcv_cache.copy()  # Return a copy
        else:
            self.logger.warning("Failed to return Daily OHLCV data despite checks.")
            return pd.DataFrame()

    def get_or_fetch_ohlcv(
        self, timeframe: str, limit: int = 500, include_daily_pivots: bool = True,
    ) -> pd.DataFrame:
        """Retrieves OHLCV data for the primary trading timeframe, using cache if recent,
        otherwise fetching, calculating indicators, updating cache, and returning the DataFrame.
        """
        target_timeframe_user = timeframe  # User-friendly format input
        target_timeframe_api = self._map_timeframe_to_pybit(
            target_timeframe_user,
        )  # API format for cache key
        target_symbol = self.config.symbol  # Use simple symbol from config

        if not target_timeframe_api:
            self.logger.error(
                f"Invalid timeframe '{target_timeframe_user}' cannot be mapped to API format. Cannot fetch OHLCV.",
            )
            return pd.DataFrame()

        # Determine minimum history needed for all indicators to function correctly
        min_history_needed = max(
            self.config.initial_candle_history,
            self.config.sma_long + 10,
            self.config.atr_period + 10,
            self.config.adx_period + 10,
            200,
        )

        cached_df = None
        with self._cache_lock:  # Acquire lock to read cache safely
            cached_df = self.ohlcv_cache.get(target_timeframe_api)

        fetch_needed = False
        cache_is_fresh = False
        now_utc = datetime.now(UTC)

        if cached_df is not None and not cached_df.empty:
            try:
                # Check freshness of cache based on the last candle's timestamp
                last_candle_timestamp = cached_df["timestamp"].iloc[-1]
                # Ensure timestamp is timezone-aware (UTC)
                if last_candle_timestamp.tzinfo is None:
                    last_candle_timestamp = last_candle_timestamp.tz_localize("UTC")
                else:
                    last_candle_timestamp = last_candle_timestamp.tz_convert("UTC")

                # Calculate expected start time of the next candle based on timeframe
                timeframe_seconds = (
                    self.exchange.parse_timeframe(target_timeframe_user)
                    if self.exchange
                    else 60
                )
                timeframe_timedelta = pd.Timedelta(seconds=timeframe_seconds)
                expected_next_candle_start = last_candle_timestamp + timeframe_timedelta
                # Add a buffer to account for loop delay and potential timing issues
                staleness_buffer = pd.Timedelta(seconds=self.config.loop_delay + 5)

                # If current time is before the expected next candle + buffer, cache is fresh
                if now_utc < (expected_next_candle_start + staleness_buffer):
                    cache_is_fresh = True
                    self.logger.debug(
                        f"Using cached OHLCV data for {target_timeframe_user} (Last candle: {cached_df['timestamp'].iloc[-1].strftime('%Y-%m-%d %H:%M:%S %Z')}).",
                    )
                else:
                    self.logger.info(
                        f"Cached OHLCV for {target_timeframe_user} is stale. Fetching fresh data.",
                    )
                    fetch_needed = True
            except Exception as e:
                self.logger.warning(
                    f"Error checking cache freshness for {target_timeframe_user}: {e}. Fetching new data.",
                )
                fetch_needed = True
        else:
            self.logger.info(
                f"No cached OHLCV data for {target_timeframe_user}. Fetching initial data.",
            )
            fetch_needed = True

        # --- Fetch Data and Calculate Indicators if Needed ---
        if fetch_needed:
            # Fetch Daily Data for Pivots if analysis modules require it
            daily_df_col = None  # DataFrame with 'timestamp' column for pivots
            if (
                self.config.analysis_modules.mtf_analysis.enabled
                or self.config.indicators.fibonacci_pivot_points
            ):
                daily_df_col = self.get_or_fetch_daily_ohlcv(symbol=target_symbol)
                if daily_df_col is None or daily_df_col.empty:
                    self.logger.debug(
                        "Daily OHLCV data not available for pivot calculation. Pivots and some MTF trends might be unavailable.",
                    )

            # Fetch primary timeframe OHLCV data
            self.logger.debug(
                f"{Fore.CYAN}# Fetching new {target_timeframe_user} OHLCV data...{Style.RESET_ALL}",
            )
            df_raw = self.fetch_ohlcv(
                timeframe=target_timeframe_user,
                limit=min_history_needed,
                symbol=target_symbol,
            )

            if not df_raw.empty:
                self.logger.debug(
                    f"Calculating indicators for freshly fetched {target_timeframe_user} data...",
                )
                try:
                    # Calculate indicators on the fetched raw data, passing daily data for pivots
                    df_with_indicators = calculate_indicators(
                        df_raw.copy(), self.config, daily_df_col,
                    )

                    if df_with_indicators is not None and not df_with_indicators.empty:
                        # Ensure timestamp column is timezone-aware (UTC)
                        if df_with_indicators["timestamp"].dt.tz is None:
                            df_with_indicators["timestamp"] = df_with_indicators[
                                "timestamp"
                            ].dt.tz_localize("UTC")
                        else:
                            df_with_indicators["timestamp"] = df_with_indicators[
                                "timestamp"
                            ].dt.tz_convert("UTC")

                        # Update cache with the new data (acquire lock for thread safety)
                        with self._cache_lock:
                            self.ohlcv_cache[target_timeframe_api] = (
                                df_with_indicators.tail(self.max_ohlcv_cache_size)
                                .reset_index(drop=True)
                                .copy()
                            )
                        self.logger.info(
                            f"Fetched, calculated indicators, and cached {len(self.ohlcv_cache[target_timeframe_api])} {target_timeframe_user} candles.",
                        )
                    else:
                        # Indicator calculation failed; cache raw data only as a fallback
                        self.logger.error(
                            f"Indicator calculation failed for {target_timeframe_user}. Caching raw data only.",
                        )
                        with self._cache_lock:
                            self.ohlcv_cache[target_timeframe_api] = (
                                df_raw.tail(self.max_ohlcv_cache_size)
                                .reset_index(drop=True)
                                .copy()
                            )
                except Exception as e:
                    self.logger.exception(
                        f"Error during indicator calculation for fetched {target_timeframe_user} data: {e}. Caching raw data.",
                    )
                    with self._cache_lock:  # Cache raw data even if indicators fail
                        self.ohlcv_cache[target_timeframe_api] = (
                            df_raw.tail(self.max_ohlcv_cache_size)
                            .reset_index(drop=True)
                            .copy()
                        )
            else:
                self.logger.error(
                    f"Failed to fetch OHLCV data for {target_timeframe_user}. Cache not updated.",
                )
                # If fetch failed, return the old (stale) cache if it exists, otherwise empty
                with self._cache_lock:
                    return (
                        cached_df.tail(limit).copy()
                        if cached_df is not None and not cached_df.empty
                        else pd.DataFrame()
                    )

        # Return the requested number of candles from the cache (acquire lock)
        if cache_is_fresh and cached_df is not None and not cached_df.empty:
            with self._cache_lock:
                # Return a copy of the relevant part of the cache
                return cached_df.tail(limit).copy()
        else:
            self.logger.warning(
                f"Failed to return cached OHLCV data for {target_timeframe_user} despite checks.",
            )
            return pd.DataFrame()  # Return empty DataFrame if all attempts fail

    def update_ohlcv_cache(self, kline_data: dict[str, Any]) -> pd.DataFrame | None:
        """Processes a single Kline whisper from WebSocket, updates indicators incrementally,
        and manages the OHLCV cache scroll. Uses the simple symbol format.
        """
        try:
            # --- Whisper Validation ---
            if (
                not isinstance(kline_data, dict)
                or "data" not in kline_data
                or not kline_data.get("data")
            ):
                self.logger.warning(
                    f"Received invalid kline whisper format: {kline_data}",
                )
                return None

            topic = kline_data.get("topic", "")
            topic_parts = topic.split(".")
            # Expected topic format: kline.<interval>.<symbol>
            if len(topic_parts) < 3 or topic_parts[0] != "kline":
                self.logger.warning(
                    f"Received whisper for unexpected topic format: {topic}",
                )
                return None

            candle_data_list = kline_data.get("data", [])
            if not candle_data_list:
                self.logger.warning(
                    f"Kline whisper data list is empty for topic {topic}.",
                )
                return None

            candle = candle_data_list[0]  # Process the first candle in the update

            # Extract critical info: timeframe (API format), symbol (simple format)
            cache_timeframe_key = topic_parts[1]  # e.g., '5', '60', 'D'
            symbol_from_topic = topic_parts[2]  # e.g., BTCUSDT

            # Ignore whispers for symbols not matching our focus symbol
            if symbol_from_topic != self.config.symbol:
                return None

            # --- Prepare Cache and Data ---
            # Ensure cache exists for this timeframe, fetch initial data if not.
            prev_df = None
            with self._cache_lock:  # Acquire lock to read cache
                prev_df = self.ohlcv_cache.get(cache_timeframe_key)

            if prev_df is None or prev_df.empty:
                self.logger.warning(
                    f"No cache found for {cache_timeframe_key} on WS update. Attempting initial fetch...",
                )
                user_timeframe = self._map_timeframe_from_pybit(cache_timeframe_key)
                if not user_timeframe:
                    self.logger.error(
                        f"Cannot map API timeframe '{cache_timeframe_key}' to user format. Cannot initialize cache.",
                    )
                    return None
                init_df = self.get_or_fetch_ohlcv(
                    user_timeframe,
                    limit=self.config.initial_candle_history,
                    include_daily_pivots=True,
                )
                if init_df is None or init_df.empty:
                    self.logger.error(
                        f"Failed to initialize cache for {cache_timeframe_key}. Cannot process WS update.",
                    )
                    return None
                with self._cache_lock:  # Re-read cache after initialization
                    prev_df = self.ohlcv_cache.get(cache_timeframe_key)
                if prev_df is None or prev_df.empty:  # Final check
                    self.logger.error(
                        f"Cache for {cache_timeframe_key} still empty after initialization attempt.",
                    )
                    return None

            # Fetch Daily Data for Pivots if enabled by analysis modules
            daily_df_col = None
            if (
                self.config.analysis_modules.mtf_analysis.enabled
                or self.config.indicators.fibonacci_pivot_points
            ):
                daily_df_col = self.get_or_fetch_daily_ohlcv(symbol=self.config.symbol)
                if daily_df_col is None or daily_df_col.empty:
                    self.logger.debug(
                        "Daily OHLCV data not available for pivot calculation during WS update.",
                    )

            # --- Process Kline Whisper Data ---
            is_confirmed = candle.get(
                "confirm", False,
            )  # Is this a final confirmed candle?
            timestamp_ms = int(candle["start"])
            timestamp = pd.to_datetime(timestamp_ms, unit="ms", utc=True)

            # Create DataFrame for the new/updated row's raw data, using Decimal for precision
            new_row_data = {}
            try:
                new_row_data = {
                    "timestamp": timestamp,
                    "open": Decimal(str(candle.get("open", "0"))),
                    "high": Decimal(str(candle.get("high", "0"))),
                    "low": Decimal(str(candle.get("low", "0"))),
                    "close": Decimal(str(candle.get("close", "0"))),
                    "volume": Decimal(str(candle.get("volume", "0"))),
                }
                new_raw_df = pd.DataFrame([new_row_data])
            except (InvalidOperation, ValueError, KeyError, TypeError) as e:
                self.logger.error(
                    f"Error parsing kline data to Decimal/dict for {cache_timeframe_key}: {e}. Data: {candle}",
                    exc_info=True,
                )
                return None

            # --- Update Cache Logic ---
            final_processed_row: pd.DataFrame | None = (
                None  # To store the result of recalculation
            )
            with self._cache_lock:  # Critical section for cache modification
                target_cache_df = self.ohlcv_cache.get(cache_timeframe_key)

                if target_cache_df is None:  # Cache vanished unexpectedly
                    self.logger.error(
                        f"Cache for {cache_timeframe_key} disappeared while lock was held.",
                    )
                    return None

                last_cached_timestamp_in_lock = (
                    target_cache_df["timestamp"].iloc[-1]
                    if not target_cache_df.empty
                    else None
                )

                # Check if we are updating the last candle or adding a new one
                if last_cached_timestamp_in_lock == timestamp:
                    # --- Update the Last Candle ---
                    log_prefix = (
                        f"{Fore.GREEN}Confirmed"
                        if is_confirmed
                        else f"{Fore.YELLOW}Updating"
                    )
                    self.logger.debug(
                        f"{log_prefix} candle in cache: {cache_timeframe_key} {symbol_from_topic} @ {timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}",
                    )

                    # Find the index of the candle to update
                    try:
                        idx_to_update = target_cache_df.index[
                            target_cache_df["timestamp"] == timestamp
                        ].tolist()[0]
                    except IndexError:
                        self.logger.error(
                            f"Timestamp {timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')} not found in cache for update. Ignoring.",
                        )
                        return None  # Timestamp mismatch

                    # Prepare a slice of historical data for recalculation
                    # Need enough history for all indicators to calculate correctly
                    min_slice_size = max(
                        self.config.initial_candle_history,
                        self.config.sma_long + 10,
                        self.config.atr_period + 10,
                        self.config.adx_period + 10,
                        200,
                    )
                    slice_start_idx = max(0, idx_to_update - min_slice_size + 1)
                    temp_df_for_calc = target_cache_df.iloc[
                        slice_start_idx : idx_to_update + 1
                    ].copy(deep=True)

                    # Update OHLCV columns in the slice with new data
                    idx_in_slice = (
                        len(temp_df_for_calc) - 1
                    )  # Index of the candle being updated within the slice
                    for col in ["open", "high", "low", "close", "volume"]:
                        if col in temp_df_for_calc.columns:
                            temp_df_for_calc.iloc[
                                idx_in_slice, temp_df_for_calc.columns.get_loc(col),
                            ] = new_raw_df.loc[0, col]
                        else:
                            self.logger.warning(
                                f"Column '{col}' missing in temp_df_for_calc during update.",
                            )

                    # Recalculate indicators on the updated slice
                    updated_slice_df = calculate_indicators(
                        temp_df_for_calc, self.config, daily_df_col,
                    )

                    if updated_slice_df is not None and not updated_slice_df.empty:
                        # Get the last row from the recalculated slice (corresponding to the updated candle)
                        newly_processed_row = updated_slice_df.iloc[-1:].copy()
                        if (
                            not newly_processed_row.empty
                            and newly_processed_row["timestamp"].iloc[0] == timestamp
                        ):
                            # Update the main cache row by row to maintain alignment
                            for col in newly_processed_row.columns:
                                if (
                                    col not in target_cache_df.columns
                                ):  # Add new indicator columns if they appeared
                                    self.logger.debug(
                                        f"Adding new indicator column '{col}' to {cache_timeframe_key} cache during update.",
                                    )
                                    target_cache_df[col] = np.nan  # Initialize with NaN

                            # Ensure columns match before updating the row
                            newly_processed_row = newly_processed_row.reindex(
                                columns=target_cache_df.columns, fill_value=np.nan,
                            )
                            # Update the specific row in the main cache
                            target_cache_df.iloc[idx_to_update] = (
                                newly_processed_row.iloc[0]
                            )
                            final_processed_row = target_cache_df.loc[
                                [idx_to_update]
                            ].copy()  # Store the updated row
                        else:
                            self.logger.error(
                                f"Recalculation for updated candle @ {timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')} returned incorrect timestamp or empty result. Appending raw data as fallback.",
                            )
                            self._append_raw_data_with_nans(
                                target_cache_df, new_raw_df, cache_timeframe_key,
                            )

                    else:
                        self.logger.error(
                            f"Indicator recalculation failed (returned empty) for updated candle @ {timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}. Appending raw data only.",
                        )
                        self._append_raw_data_with_nans(
                            target_cache_df, new_raw_df, cache_timeframe_key,
                        )

                elif (
                    last_cached_timestamp_in_lock is None
                    or timestamp > last_cached_timestamp_in_lock
                ):
                    # --- Adding a New Candle ---
                    self.logger.debug(
                        f"{Fore.BLUE}New candle received: {cache_timeframe_key} {symbol_from_topic} @ {timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}{Style.RESET_ALL}",
                    )

                    # Prepare a slice of historical data plus the new raw row for recalculation
                    min_slice_size = max(
                        self.config.initial_candle_history,
                        self.config.sma_long + 10,
                        self.config.atr_period + 10,
                        self.config.adx_period + 10,
                        200,
                    )
                    # Take enough history from the end of the current cache
                    tail_slice = target_cache_df.tail(min_slice_size - 1).copy(
                        deep=True,
                    )

                    # Combine historical slice with the new raw candle data
                    temp_df_for_calc = pd.concat(
                        [tail_slice, new_raw_df], ignore_index=True,
                    )

                    # Calculate indicators on the combined slice
                    updated_slice_df = calculate_indicators(
                        temp_df_for_calc, self.config, daily_df_col,
                    )

                    if updated_slice_df is not None and not updated_slice_df.empty:
                        # Get the last row from the recalculated slice (representing the new candle with indicators)
                        newly_processed_row = updated_slice_df.iloc[-1:].copy()
                        if (
                            not newly_processed_row.empty
                            and newly_processed_row["timestamp"].iloc[0] == timestamp
                        ):
                            # Append the newly processed row to the main cache
                            for col in newly_processed_row.columns:
                                if (
                                    col not in target_cache_df.columns
                                ):  # Add new indicator columns if they appeared
                                    self.logger.debug(
                                        f"Adding new indicator column '{col}' to {cache_timeframe_key} cache before appending.",
                                    )
                                    target_cache_df[col] = np.nan  # Initialize with NaN

                            # Ensure columns match before concatenating
                            newly_processed_row = newly_processed_row.reindex(
                                columns=target_cache_df.columns, fill_value=np.nan,
                            )
                            # Append the processed row to the main cache
                            self.ohlcv_cache[cache_timeframe_key] = pd.concat(
                                [target_cache_df, newly_processed_row],
                                ignore_index=True,
                            )
                            # Trim the cache to maintain size limit
                            self.ohlcv_cache[cache_timeframe_key] = (
                                self.ohlcv_cache[cache_timeframe_key]
                                .tail(self.max_ohlcv_cache_size)
                                .reset_index(drop=True)
                            )

                            # Retrieve the exact row that was just added for the return value
                            final_processed_row_df = self.ohlcv_cache[
                                cache_timeframe_key
                            ][
                                self.ohlcv_cache[cache_timeframe_key]["timestamp"]
                                == timestamp
                            ]
                            if not final_processed_row_df.empty:
                                final_processed_row = final_processed_row_df.copy()
                            else:
                                self.logger.error(
                                    f"Failed to find newly added row {timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')} in cache after processing.",
                                )

                        else:
                            self.logger.error(
                                f"Recalculation for new candle @ {timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')} returned incorrect timestamp or empty result. Appending raw data as fallback.",
                            )
                            self._append_raw_data_with_nans(
                                target_cache_df, new_raw_df, cache_timeframe_key,
                            )

                    else:
                        self.logger.error(
                            f"Indicator calculation failed (returned empty) for new candle @ {timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}. Appending raw data only.",
                        )
                        self._append_raw_data_with_nans(
                            target_cache_df, new_raw_df, cache_timeframe_key,
                        )

                else:
                    # Received out-of-order data - a temporal anomaly!
                    self.logger.warning(
                        f"{Fore.YELLOW}Received kline update with timestamp {timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')} older than the last cached candle ({last_cached_timestamp_in_lock.strftime('%Y-%m-%d %H:%M:%S %Z') if last_cached_timestamp_in_lock else 'N/A'}). Ignoring anomaly.{Style.RESET_ALL}",
                    )
                    # No change to cache; final_processed_row remains None

            # --- End of critical section (cache lock released) ---

            # --- Return the Processed Row (if successfully generated) ---
            if final_processed_row is not None and not final_processed_row.empty:
                final_ts_str = (
                    final_processed_row["timestamp"]
                    .iloc[0]
                    .strftime("%Y-%m-%d %H:%M:%S %Z")
                )
                with (
                    self._cache_lock
                ):  # Re-acquire lock briefly to check cache size after update
                    cache_size = len(self.ohlcv_cache.get(cache_timeframe_key, []))
                self.logger.debug(
                    f"Processed candle {final_ts_str} for {cache_timeframe_key}. Cache size: {cache_size}.",
                )
                return final_processed_row  # Return the single processed row DataFrame
            # Handle cases where processing failed or returned no usable row
            if (
                last_cached_timestamp_in_lock is not None
                and last_cached_timestamp_in_lock == timestamp
            ):
                self.logger.debug(
                    f"Failed to produce updated processed row for timestamp {timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')} in {cache_timeframe_key}.",
                )
            elif (
                last_cached_timestamp_in_lock is None
                or timestamp > last_cached_timestamp_in_lock
            ):
                self.logger.debug(
                    f"Failed to produce newly added processed row for timestamp {timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')} in {cache_timeframe_key}.",
                )
            return None

        except (IndexError, KeyError, ValueError, TypeError, InvalidOperation) as e:
            self.logger.exception(
                f"Error processing kline whisper data for topic {kline_data.get('topic', 'N/A')}: {e}. Data: {kline_data}",
            )
            return None
        except Exception as e:
            self.logger.exception(
                f"Unexpected error in update_ohlcv_cache for topic {kline_data.get('topic', 'N/A')}: {e}. Data: {kline_data}",
            )
            return None

    def _append_raw_data_with_nans(
        self,
        target_cache_df: pd.DataFrame,
        new_raw_df: pd.DataFrame,
        timeframe_key: str,
    ):
        """Helper to append raw data and add NaNs for missing indicator columns. Assumes cache lock is held."""
        try:
            # Identify columns present in cache but not in new raw data
            cols_to_add = set(target_cache_df.columns) - set(new_raw_df.columns)
            temp_raw_df = new_raw_df.copy()
            # Add missing columns initialized with NaN
            for col in cols_to_add:
                temp_raw_df[col] = np.nan

            # Reindex to match target cache columns exactly, filling new columns with NaN
            temp_raw_df = temp_raw_df.reindex(
                columns=target_cache_df.columns, fill_value=np.nan,
            )
            # Append the raw data (with added NaNs for indicators) to the cache
            self.ohlcv_cache[timeframe_key] = pd.concat(
                [target_cache_df, temp_raw_df], ignore_index=True,
            )
            self.logger.warning(
                f"Appended raw data for {new_raw_df['timestamp'].iloc[0].strftime('%Y-%m-%d %H:%M:%S %Z')} to {timeframe_key} cache due to indicator failure.",
            )

            # Trim cache to maintain size limit
            self.ohlcv_cache[timeframe_key] = (
                self.ohlcv_cache[timeframe_key]
                .tail(self.max_ohlcv_cache_size)
                .reset_index(drop=True)
            )

        except Exception as e:
            self.logger.error(
                f"Error during fallback raw data append for {timeframe_key}: {e}",
                exc_info=True,
            )

    # --- Account & Position Helpers - Peering into the Treasury ---
    def fetch_balance(self, coin: str = "USDT") -> Decimal | None:
        """Fetches the available balance for a specific coin in the UNIFIED account via pybit."""
        self.logger.debug(
            f"{Fore.CYAN}# Fetching available balance for {coin}...{Style.RESET_ALL}",
        )
        if not self.session:
            self.logger.error("pybit session not available for balance fetch.")
            return None
        try:
            # Bybit v5: get_wallet_balance requires accountType. 'UNIFIED' is common.
            response = self.session.get_wallet_balance(
                accountType="UNIFIED", coin=coin,
            )  # Use simple coin format
            if response and response.get("retCode") == 0:
                result = response.get("result", {})
                account_list = result.get("list", [])
                if account_list:
                    account_info = account_list[
                        0
                    ]  # Assuming UNIFIED account is the first entry
                    coin_info_list = account_info.get("coin", [])
                    target_coin_data = None
                    if coin_info_list:
                        # Find the specific coin data
                        target_coin_data = next(
                            (
                                c
                                for c in coin_info_list
                                if c.get("coin", "").lower() == coin.lower()
                            ),
                            None,
                        )

                    if target_coin_data:
                        # Extract available balance for trading
                        balance_str = target_coin_data.get("availableToTrade")
                        if balance_str is None or balance_str == "":
                            balance_str = "0"

                        try:
                            balance = Decimal(
                                str(balance_str),
                            )  # Convert to Decimal for precision
                            self.logger.info(
                                f"Available {coin} balance to trade: {Style.BRIGHT}{balance}{Style.RESET_ALL}",
                            )
                            return balance
                        except (InvalidOperation, ValueError):
                            self.logger.error(
                                f"Could not parse availableToTrade balance '{balance_str}' for {coin}.",
                                exc_info=True,
                            )
                            return Decimal("0")
                    else:
                        self.logger.warning(
                            f"Coin rune '{coin}' not found in wallet balance response list. Assuming zero balance.",
                        )
                        return Decimal("0")
                else:
                    self.logger.warning(
                        f"No account list found in balance response for accountType='UNIFIED'. Response: {response}",
                    )
                    return Decimal("0")
            else:
                err_msg = response.get("retMsg", "Unknown Error")
                err_code = response.get("retCode", "N/A")
                self.logger.error(
                    f"API Error fetching balance: {err_msg} (Rune: {err_code})",
                )
                return None
        except Exception as e:
            self.logger.exception(f"Exception fetching balance: {e}")
            return None

    def get_equity(self) -> Decimal | None:
        """Fetches the total account equity (in USD equivalent) via pybit."""
        self.logger.debug(
            f"{Fore.CYAN}# Fetching total account equity...{Style.RESET_ALL}",
        )
        if not self.session:
            self.logger.error("pybit session not available for equity fetch.")
            return None
        try:
            response = self.session.get_wallet_balance(
                accountType="UNIFIED",
            )  # Fetch balance for UNIFIED account
            if response and response.get("retCode") == 0:
                result = response.get("result", {})
                account_list = result.get("list", [])
                if account_list:
                    account_info = account_list[
                        0
                    ]  # Assuming UNIFIED account is the first entry
                    equity_str = account_info.get(
                        "totalEquity",
                    )  # Get total equity value
                    if equity_str is None or equity_str == "":
                        equity_str = "0"

                    try:
                        equity = Decimal(str(equity_str))  # Convert to Decimal
                        self.logger.info(
                            f"Total Account Equity (reported in USD equivalent): {Style.BRIGHT}{equity}{Style.RESET_ALL}",
                        )
                        return equity
                    except (InvalidOperation, ValueError):
                        self.logger.error(
                            f"Could not parse totalEquity balance '{equity_str}'.",
                            exc_info=True,
                        )
                        return Decimal("0")
                else:
                    self.logger.warning(
                        f"No account list found in equity response: {response}",
                    )
                    return None
            else:
                err_msg = response.get("retMsg", "Unknown Error")
                err_code = response.get("retCode", "N/A")
                self.logger.error(
                    f"API Error fetching equity: {err_msg} (Rune: {err_code})",
                )
                return None
        except Exception as e:
            self.logger.exception(f"Exception fetching equity: {e}")
            return None

    def get_position(self, symbol: str | None = None) -> dict[str, Any] | None:
        """Fetches position details for the specified symbol using pybit.
        Uses the simple symbol format. Returns details of the active position, or None.
        """
        target_symbol = symbol or self.config.symbol
        self.logger.debug(
            f"{Fore.CYAN}# Fetching position for {target_symbol}...{Style.RESET_ALL}",
        )
        if not self.session:
            self.logger.error("pybit session not available for position fetch.")
            return None
        try:
            # Bybit v5: get_positions requires category ('linear' for USDT perpetuals) and symbol (simple format)
            response = self.session.get_positions(
                category="linear", symbol=target_symbol,
            )
            if response and response.get("retCode") == 0:
                result = response.get("result", {})
                position_list = result.get("list", [])
                if position_list:
                    active_position_data = None
                    # Find the active position (non-zero size)
                    for pos_data in position_list:
                        try:
                            pos_size_str = pos_data.get("size", "0")
                            if pos_size_str is None or pos_size_str == "":
                                pos_size_str = "0"
                            pos_size = Decimal(
                                str(pos_size_str),
                            )  # Convert to str first for Decimal

                            if not pos_size.is_zero():
                                active_position_data = pos_data
                                break  # Found the active position, exit loop

                        except (InvalidOperation, ValueError, TypeError) as parse_error:
                            # Log error if position size parsing fails, but continue to check others
                            self.logger.error(
                                f"Error parsing position size for {target_symbol}: {parse_error}. Data: {pos_data}",
                                exc_info=True,
                            )

                    if active_position_data:
                        # Found an active position, transcribe and standardize its details
                        position_info = self._standardize_position_data(
                            active_position_data,
                        )
                        if position_info:  # Check if formatting was successful
                            return (
                                position_info  # Return the standardized position data
                            )
                        self.logger.error(
                            f"Failed to standardize position data for {target_symbol}. Raw data: {active_position_data}",
                        )
                        return None  # Return None if standardization failed

                    # No active position found (all entries had zero size)
                    self.logger.info(
                        f"No active position found for {target_symbol} (all entries had size 0).",
                    )
                    return None
                # API returned success but the list was empty (e.g., no positions ever)
                self.logger.info(
                    f"No position data returned in list for {target_symbol}.",
                )
                return None
            # API returned an error code
            err_msg = response.get("retMsg", "Unknown Error")
            err_code = response.get("retCode", "N/A")
            # Specific check for the "symbol not exist" error related to format
            if err_code == 10001 and (
                "symbol not exist" in err_msg.lower()
                or "invalid symbol" in err_msg.lower()
            ):
                self.logger.error(
                    f"API Error fetching position: Symbol '{target_symbol}' not found by pybit API. (Rune: {err_code})",
                )
            else:
                self.logger.error(
                    f"API Error fetching position: {err_msg} (Rune: {err_code})",
                )
            return None
        # Catch specific pybit request errors
        except InvalidRequestError as e:
            if (
                "symbol not exist" in str(e).lower()
                or "invalid symbol" in str(e).lower()
            ):
                self.logger.error(
                    f"API Error fetching position: Symbol '{target_symbol}' not found by pybit API. (Rune: {e.status_code if hasattr(e, 'status_code') else 'N/A'})",
                )
            else:
                self.logger.exception(
                    f"Invalid Request Error fetching position for {target_symbol}: {e}",
                )
            return None
        except FailedRequestError as e:
            self.logger.exception(
                f"Failed Request Error fetching position for {target_symbol}: {e}",
            )
            return None
        except Exception as e:
            self.logger.exception(
                f"Exception fetching position for {target_symbol}: {e}",
            )
            return None

    def _standardize_position_data(
        self, raw_position_data: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Helper to standardize raw position data into a consistent internal format."""

        # Helper to safely convert string to Decimal, returning None on failure or empty string
        def safe_decimal(value_str: str | None) -> Decimal | None:
            if value_str is None or value_str == "":
                return None
            try:
                return Decimal(str(value_str))  # Convert via string for precision
            except (InvalidOperation, ValueError):
                return None

        # Helper to safely convert ms timestamp string to datetime object
        def safe_datetime_from_ms(ts_str: str | None) -> datetime | None:
            if ts_str is None or not isinstance(ts_str, (str, int)):
                return None
            try:
                return pd.to_datetime(
                    int(ts_str), unit="ms", utc=True,
                ).to_pydatetime()  # Convert ms to datetime
            except (ValueError, TypeError):
                return None

        try:
            # Map raw API fields to standardized internal keys
            standardized_data = {
                "symbol": raw_position_data.get("symbol"),
                "side": raw_position_data.get("side"),  # "Buy", "Sell", or "None"
                "size": safe_decimal(raw_position_data.get("size", "0")),
                "entry_price": safe_decimal(
                    raw_position_data.get("avgPrice"),
                ),  # avgPrice is entry price
                "mark_price": safe_decimal(raw_position_data.get("markPrice")),
                "liq_price": safe_decimal(raw_position_data.get("liqPrice")),
                "unrealised_pnl": safe_decimal(
                    raw_position_data.get("unrealisedPnl", "0"),
                ),
                "leverage": safe_decimal(raw_position_data.get("leverage", "0")),
                "position_value": safe_decimal(raw_position_data.get("positionValue")),
                "take_profit": safe_decimal(raw_position_data.get("takeProfit")),
                "stop_loss": safe_decimal(raw_position_data.get("stopLoss")),
                "trailingStop": safe_decimal(
                    raw_position_data.get("trailingStop"),
                ),  # Key used internally for TSL state
                "createdTime": safe_datetime_from_ms(
                    raw_position_data.get("createdTime"),
                ),
                "updatedTime": safe_datetime_from_ms(
                    raw_position_data.get("updatedTime"),
                ),
                "positionIdx": int(
                    raw_position_data.get("positionIdx", 0),
                ),  # 0=One-Way, 1=Buy Hedge, 2=Sell Hedge
                "riskLimitValue": raw_position_data.get("riskLimitValue"),
            }
            # Basic validation: If size is positive, entry price must be parsed
            if standardized_data["size"] is None or (
                standardized_data["size"] > Decimal("0")
                and standardized_data["entry_price"] is None
            ):
                self.logger.error(
                    f"Failed to parse essential position fields (size/entry) for symbol {standardized_data['symbol']}. Raw data: {raw_position_data}",
                )
                return None

            return standardized_data
        except Exception as format_error:
            self.logger.exception(
                f"Unexpected error formatting position data: {format_error}. Raw data: {raw_position_data}",
            )
            return None

    # FIX: Merged the two definitions of get_open_positions_from_exchange into a single, more robust method.
    # This method prioritizes WebSocket data if available and falls back to REST API.
    # It also standardizes the position data.
    def get_open_positions(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """Fetches open positions for the specified symbol. Prioritizes WebSocket data if available,
        falling back to REST API. Standardizes the output. Uses simple symbol format.
        """
        target_symbol = symbol or self.config.symbol
        self.logger.debug(
            f"{Fore.CYAN}# Fetching open positions for {target_symbol}...{Style.RESET_ALL}",
        )

        # Prefer WebSocket data if available and connected
        if self.ws_connected and self.ws:
            self.logger.debug("Checking WebSocket for open position updates...")
            # A more robust implementation would involve managing a state dictionary of positions
            # and merging updates from the WebSocket stream. Here, we check the WS queue
            # for explicit 'position' updates assuming ws_manager provides them.
            # The reference to `ws_manager` is adjusted to use `self` to access internal WS state.
            if (
                hasattr(self, "ws")
                and self.ws
                and hasattr(self, "_private_ws_data_buffer")
                and isinstance(self._private_ws_data_buffer, list)
            ):  # Check if BybitHelper manages private WS data
                # Assuming _private_ws_data_buffer holds relevant WS messages
                private_updates = self._private_ws_data_buffer
                position_updates = [
                    d
                    for d in private_updates
                    if d.get("topic", "").startswith("position")
                ]

                if position_updates:
                    # For simplicity, take the latest position data. A full implementation might merge deltas.
                    # Ideally, this would involve a dedicated state manager for positions.
                    latest_pos_data = position_updates[-1].get("data", [])
                    open_positions_ws = []
                    for pos in latest_pos_data:
                        try:
                            # If size is > 0, it's considered an open position
                            if Decimal(str(pos.get("size", "0"))) > Decimal("0"):
                                std_pos = self._standardize_position_data(
                                    pos,
                                )  # Standardize data
                                if std_pos:
                                    open_positions_ws.append(std_pos)
                        except Exception as e:
                            self.logger.warning(
                                f"Error processing WS position data: {e}. Data: {pos}",
                                exc_info=True,
                            )
                    if open_positions_ws:
                        self.logger.debug(
                            f"Fetched {len(open_positions_ws)} open positions from WS stream.",
                        )
                        return open_positions_ws
                    self.logger.debug("No open positions found in WS updates.")
                else:
                    self.logger.debug(
                        "No new position updates from WS. Falling back to REST API.",
                    )
            else:
                self.logger.debug(
                    "WS Manager or private data buffer not available. Falling back to REST API.",
                )

        # Fallback to REST API if WebSocket data is not available or insufficient
        # Fetch position details via REST API
        positions_data = self.get_position(
            symbol=target_symbol,
        )  # This method gets the active position details

        if positions_data:
            # get_position returns standardized data for the active position, or None
            # Wrap it in a list for consistency with WS return type
            return [positions_data] if positions_data else []
        # get_position returned None or an empty list (meaning no active position)
        return []  # Return empty list if no positions found via REST

    # --- Order Execution Helpers - Weaving the Trading Spells ---
    def format_quantity(self, quantity: Decimal) -> str:
        """Formats quantity according to the symbol's minimum step size (lot size), rounding down."""
        if quantity <= Decimal("0"):
            self.logger.warning(
                f"Attempted to format non-positive quantity: {quantity}. Returning '0'.",
            )
            return "0"

        qty_step = self.get_qty_step()
        if qty_step is None or qty_step <= Decimal(0):
            self.logger.warning(
                "Quantity step size rune not found or invalid. Using default formatting (8 decimals).",
            )
            # Default to 8 decimal places if step is unavailable
            return (
                f"{quantity.quantize(Decimal('0.00000001'), rounding=ROUND_DOWN):.8f}"
            )

        try:
            # Calculate formatted quantity by dividing by step, rounding down, then formatting
            decimal_places = (
                abs(qty_step.normalize().as_tuple().exponent)
                if "." in str(qty_step)
                else 0
            )
            # Use integer division and multiplication to apply step size and round down
            formatted_qty_dec = (quantity // qty_step) * qty_step
            # Ensure the final string has the correct number of decimal places
            return f"{formatted_qty_dec:.{decimal_places}f}"
        except (ValueError, TypeError, InvalidOperation) as e:
            self.logger.error(
                f"Error formatting quantity {quantity} with step {qty_step}: {e}. Using default formatting.",
                exc_info=True,
            )
            # Fallback to default formatting if error occurs
            return (
                f"{quantity.quantize(Decimal('0.00000001'), rounding=ROUND_DOWN):.8f}"
            )

    def format_price(self, price: Decimal | None) -> str | None:
        """Formats price according to the symbol's minimum step size (tick size), rounding half up."""
        if price is None:
            return None  # Return None if input is None
        if price <= Decimal("0"):
            self.logger.warning(f"Attempted to format non-positive price: {price}")
            return "0"

        price_step = self.get_price_step()
        if price_step is None or price_step <= Decimal(0):
            self.logger.warning(
                "Price step size rune not found or invalid. Using default formatting (2 decimals).",
            )
            # Default to 2 decimal places if step is unavailable
            return f"{price.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"

        try:
            # Quantize price to the step size, rounding half up (common for prices)
            formatted_price_dec = price.quantize(price_step, rounding=ROUND_HALF_UP)
            # Determine decimal places from the price step for accurate formatting
            decimal_places = (
                abs(price_step.normalize().as_tuple().exponent)
                if "." in str(price_step)
                else 0
            )
            # Return formatted string with correct decimal places
            return f"{formatted_price_dec:.{decimal_places}f}"

        except (ValueError, TypeError, InvalidOperation) as e:
            self.logger.error(
                f"Error formatting price {price} with step {price_step}: {e}. Using default formatting.",
                exc_info=True,
            )
            # Fallback to default formatting if error occurs
            return f"{price.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"

    def get_min_order_qty(self) -> Decimal | None:
        """Retrieves the minimum order quantity rune from loaded market wisdom."""
        if self.market_info:
            try:
                # Access nested limits for amount details
                min_qty_val = (
                    self.market_info.get("limits", {}).get("amount", {}).get("min")
                )
                if min_qty_val is not None:
                    return Decimal(str(min_qty_val))  # Convert to Decimal
            except (KeyError, ValueError, TypeError, InvalidOperation) as e:
                self.logger.error(
                    f"Could not parse min order quantity rune from market wisdom: {e}",
                    exc_info=True,
                )
        self.logger.warning("Min order quantity rune not found in market wisdom.")
        return None

    def get_qty_step(self) -> Decimal | None:
        """Retrieves the quantity step size rune (lot size) from loaded market wisdom."""
        if self.market_info:
            try:
                # Access nested precision for quantity step
                step_val = self.market_info.get("precision", {}).get("amount")
                if step_val is not None:
                    return Decimal(str(step_val))  # Convert to Decimal
            except (KeyError, ValueError, TypeError, InvalidOperation) as e:
                self.logger.error(
                    f"Could not parse quantity step size rune from market wisdom: {e}",
                    exc_info=True,
                )
        self.logger.warning("Quantity step size rune not found in market wisdom.")
        return None

    def get_price_step(self) -> Decimal | None:
        """Retrieves the price step size rune (tick size) from loaded market wisdom."""
        if self.market_info:
            try:
                # Access nested precision for price step
                step_val = self.market_info.get("precision", {}).get("price")
                if step_val is not None:
                    return Decimal(str(step_val))  # Convert to Decimal
            except (KeyError, ValueError, TypeError, InvalidOperation) as e:
                self.logger.error(
                    f"Could not parse price step size rune from market wisdom: {e}",
                    exc_info=True,
                )
        self.logger.warning("Price step size rune not found in market wisdom.")
        return None

    def place_order(
        self,
        side: str,
        qty: Decimal,
        order_type: str = "Market",
        price: Decimal | None = None,
        sl: Decimal | None = None,
        tp: Decimal | None = None,
        reduce_only: bool = False,
        time_in_force: str = "GTC",
        position_idx: int = 0,
        trigger_price: Decimal | None = None,
        trigger_direction: int | None = None,
        stop_loss_type: str = "Market",
        take_profit_type: str = "Market",
        order_link_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Weaves an order spell using pybit session, applying formatting, validation,
        and SL/TP wards. Uses simple symbol format for API calls.
        """
        if not self.session or self.market_info is None:
            self.logger.error(
                "Cannot weave order spell: pybit session or market wisdom not initialized.",
            )
            return None

        symbol = self.config.symbol  # Use simple symbol format from config
        category = "linear"  # Default category, usually 'linear' for USDT perpetuals

        # --- Input Validation Wards ---
        side_upper = side.capitalize()
        if side_upper not in ["Buy", "Sell"]:
            self.logger.error(
                f"Invalid order side rune: {side}. Must be 'Buy' or 'Sell'.",
            )
            return None
        if qty <= Decimal("0"):
            self.logger.error(f"Invalid order quantity rune: {qty}. Must be positive.")
            return None

        order_type_upper = order_type.capitalize()
        if order_type_upper not in ["Market", "Limit"]:
            self.logger.error(
                f"Invalid order_type rune: {order_type}. Base type must be Market or Limit. Use trigger_price for conditional.",
            )
            return None
        if order_type_upper == "Limit" and price is None:
            self.logger.error("Price rune is required for Limit spells.")
            return None
        # Validate trigger parameters if provided
        if trigger_price is not None and trigger_direction not in [
            1,
            2,
        ]:  # 1=RISE >=, 2=FALL <=
            self.logger.error(
                "trigger_direction rune (1 or 2) is required when trigger_price is set.",
            )
            return None
        if trigger_price is None and trigger_direction is not None:
            self.logger.warning(
                "trigger_direction provided without trigger_price. Ignoring trigger_direction.",
            )
            trigger_direction = None

        # Validate Time-In-Force (TIF) rune
        valid_tifs = ["GTC", "IOC", "FOK", "PostOnly"]
        tif_upper = time_in_force.upper()
        if tif_upper not in valid_tifs:
            self.logger.warning(
                f"Invalid time_in_force rune '{time_in_force}'. Defaulting based on order type.",
            )
            tif_upper = "IOC" if order_type_upper == "Market" else "GTC"  # Default TIF
        # Enforce TIF rules based on order type
        if order_type_upper == "Market" and tif_upper not in ["IOC", "FOK"]:
            self.logger.warning(
                f"Market spells usually use IOC or FOK. Overriding timeInForce to IOC for type '{order_type}'.",
            )
            tif_upper = "IOC"
        if tif_upper == "POSTONLY" and order_type_upper != "Limit":
            self.logger.warning(
                f"PostOnly TIF is only valid for Limit spells. Using GTC for {order_type}.",
            )
            tif_upper = "GTC"
        if tif_upper == "POSTONLY" and trigger_price is not None:
            self.logger.warning(
                "PostOnly TIF combined with trigger_price might have unexpected behavior. Using GTC.",
            )
            tif_upper = "GTC"

        # Validate Stop Loss / Take Profit types
        stop_loss_type_upper = stop_loss_type.capitalize()
        if stop_loss_type_upper not in ["Market", "Limit"]:
            self.logger.warning(
                f"Invalid stop_loss_type rune '{stop_loss_type}'. Defaulting to 'Market'.",
            )
            stop_loss_type_upper = "Market"
        take_profit_type_upper = take_profit_type.capitalize()
        if take_profit_type_upper not in ["Market", "Limit"]:
            self.logger.warning(
                f"Invalid take_profit_type rune '{take_profit_type}'. Defaulting to 'Market'.",
            )
            take_profit_type_upper = "Market"

        # --- Format Quantity and Price runes ---
        qty_str = self.format_quantity(qty)
        if Decimal(qty_str) <= Decimal(
            "0",
        ):  # Check if quantity became zero after formatting
            self.logger.error(
                f"Formatted quantity {qty_str} is zero or negative. Cannot cast order spell.",
            )
            return None

        min_qty = self.get_min_order_qty()
        if min_qty is not None and Decimal(qty_str) < min_qty:
            self.logger.error(
                f"Formatted quantity {qty_str} is below minimum required {min_qty} for {symbol}. Cannot cast spell.",
            )
            return None

        price_str = self.format_price(price) if order_type_upper == "Limit" else None
        sl_str = self.format_price(sl)
        tp_str = self.format_price(tp)
        trigger_price_str = self.format_price(trigger_price)

        # --- Assemble Order Spell Parameters ---
        params: dict[str, Any] = {
            "category": category,
            "symbol": symbol,  # Use simple symbol format
            "side": side_upper,
            "qty": qty_str,
            "orderType": order_type_upper,
            "reduceOnly": reduce_only,
            "positionIdx": position_idx,
            "timeInForce": tif_upper,
            # Generate a unique client order ID if not provided
            "orderLinkId": order_link_id
            if order_link_id
            else f"enh_{int(time.time() * 1000)}"[
                0:36
            ],  # Ensure unique and within Bybit limits
        }

        # Add price if it's a Limit order
        if order_type_upper == "Limit" and price_str is not None:
            params["price"] = price_str

        # Add trigger parameters if provided
        if trigger_price_str is not None and trigger_direction is not None:
            params["triggerPrice"] = trigger_price_str
            params["triggerDirection"] = trigger_direction
            self.logger.debug(
                f"Conditional parameters added: triggerPrice={trigger_price_str}, triggerDirection={trigger_direction}",
            )

        # Add Stop Loss (SL) and Take Profit (TP) parameters if provided
        sl_provided = sl_str is not None
        tp_provided = tp_str is not None
        if sl_provided or tp_provided:
            params["tpslMode"] = "Full"  # Set TP/SL mode (Full/Partial)
            if sl_provided:
                params["stopLoss"] = sl_str
                params["slOrderType"] = stop_loss_type_upper
                # pybit v5 doesn't directly support limit price for SL/TP in order creation, implies Market by default
                if stop_loss_type_upper == "Limit":
                    self.logger.warning(
                        f"Limit SL requested ({sl_str}) but might not be directly supported in order creation. Check API docs.",
                    )
            if tp_provided:
                params["takeProfit"] = tp_str
                params["tpOrderType"] = take_profit_type_upper
                if take_profit_type_upper == "Limit":
                    self.logger.warning(
                        f"Limit TP requested ({tp_str}) but might not be directly supported in order creation. Check API docs.",
                    )

        # --- Log the Spell Details and Cast ---
        side_color = Fore.GREEN if side_upper == "Buy" else Fore.RED
        log_details = f"{side_color}{side_upper}{Style.RESET_ALL} {Style.BRIGHT}{qty_str}{Style.RESET_ALL} {symbol} {order_type_upper}"
        if price_str:
            log_details += f" @{Fore.YELLOW}{price_str}{Style.RESET_ALL}"
        if trigger_price_str:
            trigger_dir_icon = (
                "↑"
                if trigger_direction == 1
                else "↓"
                if trigger_direction == 2
                else "?"
            )
            log_details += f" Trigger@{Fore.CYAN}{trigger_price_str}{Style.RESET_ALL} ({trigger_dir_icon})"
        if sl_str:
            log_details += f" SL@{Fore.RED}{sl_str}{Style.RESET_ALL} ({params.get('slOrderType', 'N/A')})"
        if tp_str:
            log_details += f" TP@{Fore.GREEN}{tp_str}{Style.RESET_ALL} ({params.get('tpOrderType', 'N/A')})"
        if reduce_only:
            log_details += f" {Fore.MAGENTA}(ReduceOnly){Style.RESET_ALL}"
        log_details += f" TIF:{params['timeInForce']}"
        log_details += f" LinkID:{params['orderLinkId']}"

        self.logger.info(f"Casting Order Spell: {log_details}")
        # Log parameters for debugging, omitting sensitive keys
        params_to_log = {
            k: v
            for k, v in params.items()
            if k.lower() not in ["api_key", "api_secret"]
        }
        self.logger.debug(f"Spell Parameters: {params_to_log}")

        try:
            # Cast the spell via pybit's place_order method
            response = self.session.place_order(**params)

            # --- Interpret the Response Runes ---
            if response and response.get("retCode") == 0:
                order_result = response.get("result", {})
                order_id = order_result.get("orderId")
                order_link_id_resp = order_result.get("orderLinkId")
                self.logger.success(
                    f"{Fore.GREEN}Order spell cast successfully! OrderID: {order_id}. LinkID: {order_link_id_resp}{Style.RESET_ALL}",
                )
                # Send SMS notification whisper on success
                sms_msg = f"ORDER OK: {side_upper} {qty_str} {symbol} {order_type_upper}. ID:{order_id[-6:] if order_id else 'N/A'}"
                self.send_sms(sms_msg)
                return order_result

            # Spell casting failed at API level
            err_code = response.get("retCode", "N/A")
            err_msg = response.get("retMsg", "Unknown disturbance")
            self.logger.error(
                f"{Back.RED}{Fore.WHITE}Order spell FAILED! Rune: {err_code}, Message: {err_msg}{Style.RESET_ALL}",
            )
            # Send SMS alert whisper on failure
            sms_msg = f"ORDER FAIL: {side_upper} {qty_str} {symbol}. Code:{err_code}, Msg:{err_msg[:40]}"
            self.send_sms(sms_msg)

            # Provide specific feedback based on common error codes
            if err_code == 110007:
                self.logger.error("Reason: Insufficient available balance.")
            elif err_code in [130021, 130071, 130072]:
                self.logger.error(
                    f"Reason: Risk limit or position size issue. ({err_msg})",
                )
            elif err_code == 10001:  # Parameter error, often symbol related
                if (
                    "symbol not exist" in err_msg.lower()
                    or "invalid symbol" in err_msg.lower()
                ):
                    self.logger.error(
                        f"Reason: Symbol '{symbol}' not found by API. Check symbol name in config.",
                    )
                else:
                    self.logger.error(
                        f"Reason: Parameter error in request. Check formatting/values. ({err_msg})",
                    )
            elif err_code == 110017:  # Order quantity error (e.g., below min)
                min_qty = self.get_min_order_qty()
                qty_step = self.get_qty_step()
                self.logger.error(
                    f"Reason: Order quantity error. MinQty={min_qty}, Step={qty_step}. ({err_msg})",
                )
            elif err_code == 110014:  # Price error (e.g., too low/high, precision)
                price_step = self.get_price_step()
                self.logger.error(
                    f"Reason: Order price error. PriceStep={price_step}. ({err_msg})",
                )
            elif err_code == 130023:  # Order would cause liquidation
                self.logger.error(
                    f"Reason: Order would cause immediate liquidation. ({err_msg})",
                )

            return None  # Indicate failure

        except Exception as e:
            # Catch unexpected interferences during spell casting
            self.logger.exception(f"Exception during order spell casting: {e}")
            sms_msg = f"ORDER EXCEPTION: {side_upper} {qty_str} {symbol}. {str(e)[:50]}"
            self.send_sms(sms_msg)
            return None

    def cancel_order(
        self,
        order_id: str | None = None,
        order_link_id: str | None = None,
        symbol: str | None = None,
    ) -> bool:
        """Dispels a specific order spell by its Bybit Order ID or Client Order ID (orderLinkId).
        Uses the simple symbol format for API calls. Returns True if dispelled or not found, False on error.
        """
        if not order_id and not order_link_id:
            self.logger.error(
                "Cannot dispel order: Either order_id or order_link_id rune must be provided.",
            )
            return False
        if not self.session:
            self.logger.error("pybit session not available for order dispelling.")
            return False

        target_symbol = symbol or self.config.symbol
        cancel_ref = (
            order_id if order_id else order_link_id
        )  # Use the provided reference
        ref_type = "OrderID" if order_id else "LinkID"
        self.logger.info(
            f"{Fore.YELLOW}Attempting to dispel order '{cancel_ref}' ({ref_type}) for {target_symbol}...{Style.RESET_ALL}",
        )

        # Prepare parameters for the cancel_order API call
        params: dict[str, Any] = {
            "category": "linear",
            "symbol": target_symbol,  # Use simple symbol format
        }
        if order_id:
            params["orderId"] = order_id
        elif order_link_id:
            params["orderLinkId"] = order_link_id

        try:
            response = self.session.cancel_order(**params)

            # Interpret the response runes
            if response and response.get("retCode") == 0:
                # API reported success
                result_data = response.get("result", {})
                result_id = result_data.get("orderId", "N/A")
                result_link_id = result_data.get("orderLinkId", "N/A")
                self.logger.success(
                    f"Order '{cancel_ref}' dispelled successfully (Response ID: {result_id}, LinkID: {result_link_id}).",
                )
                return True
            # API call failed or order not found/cancellable
            err_code = response.get("retCode")
            err_msg = response.get("retMsg", "Unknown disturbance")

            # Check for common "Order not found" runes/messages
            order_not_found_codes = {110001}  # Common code for order not found
            order_not_found_msgs = [
                "order not found",
                "order is not cancellable",
                "order does not exist",
            ]

            is_not_found = err_code in order_not_found_codes or any(
                msg in err_msg.lower() for msg in order_not_found_msgs
            )

            if is_not_found:
                # If order not found or inactive, consider it "dispelled" from our perspective
                self.logger.warning(
                    f"Order '{cancel_ref}' not found or already inactive/non-cancellable (Rune: {err_code}, Msg: {err_msg}). Considered dispelled.",
                )
                return True
            # Check for symbol error
            if err_code == 10001 and (
                "symbol not exist" in err_msg.lower()
                or "invalid symbol" in err_msg.lower()
            ):
                self.logger.error(
                    f"Failed to dispel order '{cancel_ref}': Symbol '{target_symbol}' not found by API. (Rune: {err_code})",
                )
            else:
                self.logger.error(
                    f"Failed to dispel order '{cancel_ref}'. Rune: {err_code}, Message: {err_msg}",
                )
            return False  # Genuine dispelling failure

        except Exception as e:
            # Catch unexpected interferences during the dispelling ritual
            self.logger.exception(f"Exception dispelling order '{cancel_ref}': {e}")
            return False

    def cancel_all_orders(
        self, symbol: str | None = None, order_filter: str | None = None,
    ) -> bool:
        """Dispels all open order spells for the specified symbol, with optional filtering.
        Uses the simple symbol format for API calls.
        """
        target_symbol = symbol or self.config.symbol
        self.logger.info(
            f"{Fore.RED + Style.BRIGHT}Attempting to dispel ALL orders for {target_symbol} (Filter: {order_filter or 'All'})...{Style.RESET_ALL}",
        )
        if not self.session:
            self.logger.error("pybit session not available for mass order dispelling.")
            return False
        try:
            params: dict[str, Any] = {
                "category": "linear",
                "symbol": target_symbol,  # Use simple symbol format
            }
            # Apply filter if provided (e.g., 'Order', 'StopOrder', 'tpslOrder')
            if order_filter:
                valid_filters = ["Order", "StopOrder", "tpslOrder"]
                if order_filter not in valid_filters:
                    self.logger.warning(
                        f"Invalid order_filter '{order_filter}'. Must be one of {valid_filters}. Proceeding without filter.",
                    )
                else:
                    params["orderFilter"] = order_filter

            response = self.session.cancel_all_orders(**params)

            # Interpret the response runes
            if response and response.get("retCode") == 0:
                # API reported success, check result details
                result_data = response.get("result", {})
                cancelled_list = result_data.get(
                    "list", [],
                )  # List of cancelled order IDs
                success_indicator = result_data.get(
                    "success",
                )  # Boolean flag for overall success

                if cancelled_list:
                    count = len(cancelled_list)
                    # Log first few cancelled order IDs for reference
                    ids_short = [
                        str(item.get("orderId", "N/A"))[-6:]
                        for item in cancelled_list[: min(count, 5)]
                    ]
                    self.logger.success(
                        f"Successfully dispelled {count} order(s) for {target_symbol}. Example IDs ending in: {ids_short}...",
                    )
                    return True
                if success_indicator is not None:
                    # If success flag is present, rely on that
                    if success_indicator is True or str(success_indicator) == "1":
                        self.logger.success(
                            f"Mass dispel request acknowledged successfully by API for {target_symbol} (may indicate no matching orders were open).",
                        )
                        return True
                    self.logger.warning(
                        f"Mass dispel request returned success=False/0 but retCode=0 for {target_symbol}. Response: {response}",
                    )
                    return True  # Consider it successful if API reported no error code
                # Success code but no details - likely no orders matched the filter
                self.logger.info(
                    f"Mass dispel request successful (retCode 0), but no specific details returned for {target_symbol}. Likely no matching orders found.",
                )
                return True
            # API call failed
            err_code = response.get("retCode")
            err_msg = response.get("retMsg", "Unknown disturbance")
            # Check for symbol errors first
            if err_code == 10001 and (
                "symbol not exist" in err_msg.lower()
                or "invalid symbol" in err_msg.lower()
            ):
                self.logger.error(
                    f"Failed to dispel all orders: Symbol '{target_symbol}' not found by API. (Rune: {err_code})",
                )
                return False
            # Check for order not found errors
            order_not_found_codes = {110001}
            order_not_found_msgs = [
                "order not found",
                "order is not cancellable",
                "order does not exist",
            ]
            is_not_found = err_code in order_not_found_codes or any(
                msg in err_msg.lower() for msg in order_not_found_msgs
            )

            if is_not_found:
                self.logger.info(
                    f"No matching orders found to cancel for {target_symbol} (Rune: {err_code}, Msg: {err_msg}). Considered dispelled.",
                )
                return True  # If order not found, it's effectively "dispelled" from open state
            # Genuine failure
            self.logger.error(
                f"Failed to dispel all orders for {target_symbol}. Rune: {err_code}, Message: {err_msg}",
            )
            return False

        except Exception as e:
            self.logger.exception(
                f"Exception during mass order dispelling for {target_symbol}: {e}",
            )
            return False

    # --- Utilities - Lesser Incantations ---
    def send_sms(self, message: str) -> bool:
        """Sends an SMS whisper using Termux API, respecting cooldown and length limits."""
        if (
            not self.config.notifications.termux_sms.enabled
            or not self.config.notifications.termux_sms.phone_number
        ):
            # SMS feature is disabled or phone number is not configured
            return False

        current_time = time.time()
        # Check cooldown period
        if (
            current_time - self.last_sms_time
            < self.config.notifications.termux_sms.cooldown
        ):
            self.logger.debug("SMS cooldown active. Skipping send.")
            return False

        # Prepare message: truncate if too long, add prefix
        max_len = 140  # Standard SMS limit, though modern ones are longer
        prefix = self.config.notifications.termux_sms.message_prefix
        truncated_message = (
            message[:max_len] + "..." if len(message) > max_len else message
        )
        full_message = f"{prefix} {truncated_message}"
        phone_number = self.config.notifications.termux_sms.phone_number

        self.logger.debug(f"Attempting to send SMS to {phone_number}...")
        try:
            # Construct the command to execute termux-sms-send
            # Using subprocess.run for better control over output and error handling
            cmd_list = ["termux-sms-send", "-n", phone_number, full_message]
            self.logger.debug(f"Executing SMS command list: {cmd_list}")

            # Execute the command in a background thread to avoid blocking
            def _run_sms_command_thread(cmd: list[str], phone: str, msg: str):
                try:
                    # Execute command with timeout, capture output, check for errors
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=15,
                        check=False,
                        encoding="utf-8",
                    )  # 15 sec timeout

                    if result.returncode == 0:
                        self.last_sms_time = (
                            time.time()
                        )  # Update cooldown timer on success
                        self.logger.info(
                            f"{Fore.GREEN}SMS whisper sent successfully to {phone}: {msg}{Style.RESET_ALL}",
                        )
                    else:
                        # Log errors from termux-sms-send
                        error_output = (
                            result.stderr.strip()
                            if result.stderr
                            else result.stdout.strip()
                        )
                        self.logger.error(
                            f"{Fore.RED}Termux SMS command failed! Return Code: {result.returncode}. Output: {error_output}{Style.RESET_ALL}",
                        )
                        # Provide hints for common issues
                        if (
                            "command not found" in error_output.lower()
                            or "usage: termux-sms-send" in error_output.lower()
                            or "permission denied" in error_output.lower()
                        ):
                            self.logger.error(
                                f"{Fore.RED}Hint: 'termux-sms-send' command not found or permission denied. Ensure Termux:API package is installed and permissions are granted.{Style.RESET_ALL}",
                            )
                except subprocess.TimeoutExpired:
                    self.logger.error(
                        f"{Fore.RED}Termux SMS command timed out after 15 seconds.{Style.RESET_ALL}",
                    )
                except FileNotFoundError:
                    self.logger.error(
                        f"{Fore.RED}'termux-sms-send' command not found. Is Termux:API installed and in PATH?{Style.RESET_ALL}",
                    )
                except Exception as e:
                    self.logger.exception(
                        f"Unexpected error during SMS command execution: {e}",
                    )

            sms_thread = threading.Thread(
                target=_run_sms_command_thread,
                args=(cmd_list, phone_number, full_message),
                daemon=True,
            )
            sms_thread.start()
            return True  # SMS sending initiated

        except Exception as e:
            self.logger.exception(
                f"Unexpected error preparing SMS whisper command: {e}",
            )
            return False

    def diagnose(self) -> bool:
        """Runs diagnostic checks for API connectivity, configuration, and basic functionality."""
        self.logger.info(
            f"\n{Fore.MAGENTA + Style.BRIGHT}--- Running Diagnostics ---{Style.RESET_ALL}",
        )
        passed_checks = 0
        total_checks = 0
        results = []  # Store check results for summary

        # Check 1: Server Time Sync
        total_checks += 1
        check_name = "Server Time Sync"
        server_time = self.get_server_time()
        if server_time is not None:
            results.append((check_name, True, "Server time check successful."))
            passed_checks += 1
        else:
            results.append((check_name, False, "Server time check failed."))

        # Check 2: Market Info Load
        total_checks += 1
        check_name = f"Market Info Load ({self.config.symbol})"
        if not self.market_info:
            self._load_market_info()  # Ensure market info is loaded if missing
        if self.market_info and self.market_info.get("symbol") == self.config.symbol:
            results.append(
                (
                    check_name,
                    True,
                    "Market info loaded successfully. Precision/Limits available.",
                ),
            )
            passed_checks += 1
        else:
            results.append(
                (
                    check_name,
                    False,
                    f"Market info load failed or symbol mismatch. Check BOT_SYMBOL ('{self.config.symbol}' not found?).",
                ),
            )

        # Check 3: Balance Fetch (Tests API authentication and basic access)
        total_checks += 1
        check_name = "Balance Fetch (API Auth)"
        balance = self.fetch_balance()  # Fetches USDT balance by default
        if (
            balance is not None
        ):  # Check if the API call succeeded, not the balance value itself
            results.append((check_name, True, "API call OK. Balance fetch successful."))
            passed_checks += 1
        else:
            results.append(
                (
                    check_name,
                    False,
                    "Balance fetch failed (API call error). Check API keys/permissions.",
                ),
            )

        # Check 4: Leverage Setting (Informational, tests write capability)
        self.logger.info(
            f"{Fore.CYAN}# Checking leverage setting (informational)...{Style.RESET_ALL}",
        )
        leverage_set_ok = self._set_leverage()
        self.logger.info(
            f"Leverage setting check result: {'OK/Already Set' if leverage_set_ok else 'Failed/Warning (see logs)'}",
        )
        # This check's pass/fail isn't critical for overall diagnostics but provides useful feedback.

        # Check 5: WebSocket Instance Creation
        total_checks += 1
        check_name = "WebSocket Instance Creation"
        self._init_websocket_instance()  # Attempt to create the WS instance
        if self.ws:
            results.append(
                (check_name, True, "WebSocket instance created successfully."),
            )
            passed_checks += 1
        else:
            results.append((check_name, False, "WebSocket instance creation failed."))

        # Check 6: Quick WebSocket Connection Test (Simplified)
        # A full connection test is complex due to threading. We focus on confirming the instance can be prepared.
        total_checks += 1
        check_name = "WebSocket Connection Viability"
        self.logger.info(
            f"{Fore.CYAN}# Checking WebSocket connection viability...{Style.RESET_ALL}",
        )
        ws_test_passed = False
        pybit_tf = self._map_timeframe_to_pybit(self.config.timeframe)
        test_topics: list[str] = []
        if pybit_tf:
            # Use simple symbol format for WS topics
            test_topic = f"kline.{pybit_tf}.{self.config.symbol}"
            test_topics = [test_topic]
        else:
            self.logger.error(
                f"Invalid primary timeframe '{self.config.timeframe}' for WS topic.",
            )

        # Temporarily isolate WS state to perform test without affecting main loop state
        original_ws_state = self._isolate_ws_state_for_test()

        test_result = {"passed": False, "error": ""}
        try:
            if self.ws and test_topics:
                # Register minimal handlers for the test connection
                test_message_cb = lambda msg: self.logger.debug(
                    f"WS Test Message: {msg}",
                )
                test_error_cb = lambda err: self.logger.error(f"WS Test Error: {err}")
                # Use dummy callbacks for open/close to simplify test
                self.connect_websocket(
                    test_topics,
                    test_message_cb,
                    error_cb=test_error_cb,
                    open_callback=lambda: setattr(self, "_ws_test_open", True),
                    close_callback=lambda: setattr(self, "_ws_test_closed", True),
                )
                # Wait briefly for connection attempt
                time.sleep(3)  # Small delay to allow connection attempt
                if (
                    self.ws_connected
                ):  # Check if connection was established and callbacks fired
                    test_result["passed"] = True
                    test_result["error"] = "Connection seemed to establish."
                else:
                    test_result["error"] = "Connection attempt did not report success."
            else:
                test_result["error"] = "Skipped: WS instance or topics missing."
        except Exception as e:
            self.logger.exception("Exception during WebSocket test execution.")
            test_result["error"] = f"Exception during test: {e}"
        finally:
            # Restore original WS state using the stored values
            self._restore_ws_state(original_ws_state)
            self.logger.debug("WS Test: Original WS state restored.")

        if test_result["passed"]:
            results.append((check_name, True, test_result["error"]))
            passed_checks += 1
        else:
            results.append(
                (check_name, False, f"WS test failed: {test_result['error']}"),
            )

        # Check 7: Basic OHLCV Fetch
        total_checks += 1
        check_name = f"OHLCV Fetch ({self.config.timeframe})"
        try:
            fetch_limit_ohlcv = max(
                50,
                self.config.sma_long + 5,
                self.config.atr_period + 5,
                self.config.adx_period + 5,
                200,
            )  # Ensure enough history
            test_ohlcv_df = bybit_client.get_or_fetch_ohlcv(
                self.config.timeframe,
                limit=fetch_limit_ohlcv,
                include_daily_pivots=False,
            )  # No pivots needed for this test
            if (
                not test_ohlcv_df.empty
                and len(test_ohlcv_df) >= fetch_limit_ohlcv * 0.8
            ):  # Check if a substantial amount was fetched
                results.append(
                    (
                        check_name,
                        True,
                        f"OHLCV fetch successful ({len(test_ohlcv_df)} candles).",
                    ),
                )
                passed_checks += 1
            else:
                results.append(
                    (
                        check_name,
                        False,
                        f"OHLCV fetch returned empty or insufficient data ({len(test_ohlcv_df)} fetched, expected ~{fetch_limit_ohlcv}).",
                    ),
                )
        except Exception as e:
            self.logger.exception("Exception during OHLCV fetch test.")
            results.append((check_name, False, f"Exception during OHLCV fetch: {e}"))

        # Check 8: Daily OHLCV Fetch (for Pivots)
        total_checks += 1
        check_name = "Daily OHLCV Fetch (Pivots)"
        try:
            # Fetch a small amount of daily data for testing pivots
            test_daily_ohlcv_df = bybit_client.get_or_fetch_daily_ohlcv(limit=5)
            if (
                not test_daily_ohlcv_df.empty and len(test_daily_ohlcv_df) >= 2
            ):  # Need at least 2 days for pivots
                results.append(
                    (
                        check_name,
                        True,
                        f"Daily OHLCV fetch successful ({len(test_daily_ohlcv_df)} candles).",
                    ),
                )
                passed_checks += 1
            else:
                results.append(
                    (
                        check_name,
                        False,
                        f"Daily OHLCV fetch returned empty or insufficient data ({len(test_daily_ohlcv_df)} fetched, need at least 2).",
                    ),
                )
        except Exception as e:
            self.logger.exception("Exception during Daily OHLCV fetch test.")
            results.append(
                (check_name, False, f"Exception during Daily OHLCV fetch: {e}"),
            )

        # Check 9: Indicators Calculation Test
        total_checks += 1
        check_name = "Indicators Calculation"
        try:
            # Need a decent history slice to test indicator calculations
            ohlcv_slice_for_test = None
            daily_df_for_test = None
            with self._cache_lock:  # Access cache safely
                pybit_tf_key = bybit_client._map_timeframe_to_pybit(config.timeframe)
                if pybit_tf_key and bybit_client.ohlcv_cache.get(pybit_tf_key):
                    ohlcv_slice_for_test = bybit_client.ohlcv_cache.get(
                        pybit_tf_key,
                    ).copy()
                daily_cache = bybit_client.daily_ohlcv_cache
                if daily_cache is not None and not daily_cache.empty:
                    daily_df_for_test = daily_cache.copy()

            min_needed_for_indicators = max(
                config.initial_candle_history,
                config.sma_long + 10,
                config.atr_period + 10,
                config.adx_period + 10,
                200,
            )
            # If cache doesn't have enough data, try fetching it
            if (
                ohlcv_slice_for_test is None
                or len(ohlcv_slice_for_test) < min_needed_for_indicators
            ):
                logger.debug(
                    "Not enough cached OHLCV data for indicator test. Refetching...",
                )
                ohlcv_slice_for_test = bybit_client.get_or_fetch_ohlcv(
                    config.timeframe,
                    limit=min_needed_for_indicators,
                    include_daily_pivots=True,
                )
                # Re-fetch daily data if needed for pivots
                if (
                    config.analysis_modules.mtf_analysis.enabled
                    or config.indicators.fibonacci_pivot_points
                ) and (daily_df_for_test is None or daily_df_for_test.empty):
                    daily_df_for_test = bybit_client.get_or_fetch_daily_ohlcv()

            if (
                ohlcv_slice_for_test is not None
                and not ohlcv_slice_for_test.empty
                and len(ohlcv_slice_for_test) >= min_needed_for_indicators
            ):
                # Run the indicator calculation on the data slice
                test_indicators_df = calculate_indicators(
                    ohlcv_slice_for_test.copy(), config, daily_df_for_test,
                )

                if test_indicators_df is not None and not test_indicators_df.empty:
                    # Check if key indicators and structure elements were populated
                    sample_cols_to_check = [
                        "ATR",
                        "SMA_Short",
                        "SMA_Long",
                        "MACD_Line",
                        "RSI",
                        "Fisher_Price",
                        "Pivot",
                        "Resistance",
                        "Support",
                        "Is_Bullish_OB",
                        "Is_Bearish_OB",
                    ]
                    found_valid_indicator = False
                    # Check the last few rows for any non-NaN indicator values
                    check_tail = test_indicators_df.tail(10)
                    for col in sample_cols_to_check:
                        if (
                            col in test_indicators_df.columns
                            and pd.api.types.is_numeric_dtype(test_indicators_df[col])
                        ):
                            if (
                                test_indicators_df[col].notna().any()
                            ):  # Check if any value in the column is not NaN
                                found_valid_indicator = True
                                break
                    if found_valid_indicator:
                        results.append(
                            (
                                check_name,
                                True,
                                "Indicators calculated successfully. Key indicators populated.",
                            ),
                        )
                        passed_checks += 1
                    else:
                        results.append(
                            (
                                check_name,
                                False,
                                "Indicators calculated, but sample results are all NaN. Check data/config.",
                            ),
                        )
                else:
                    results.append(
                        (
                            check_name,
                            False,
                            "calculate_indicators returned empty or None.",
                        ),
                    )
            else:
                results.append(
                    (
                        check_name,
                        False,
                        f"Not enough OHLCV data available/fetched ({len(ohlcv_slice_for_test) if ohlcv_slice_for_test is not None else 0} < {min_needed_for_indicators}) for indicator test.",
                    ),
                )

        except ImportError:
            results.append(
                (
                    check_name,
                    False,
                    "Indicators module (indicators.py) not found or failed to import.",
                ),
            )
        except Exception as e:
            logger.exception("Exception during indicator calculation test.")
            results.append(
                (check_name, False, f"Exception during indicator calculation: {e}"),
            )

        # Check 10: Termux SMS Sending (if enabled)
        if config.notifications.termux_sms.enabled:
            total_checks += 1
            check_name = "Termux SMS Send"
            test_message = f"Bybit Bot Diag Test @ {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S %Z')}"
            logger.info(
                f"{Fore.CYAN}# Attempting test SMS (respects cooldown, runs in background)...{Style.RESET_ALL}",
            )
            sms_initiated = False
            try:
                # Check cooldown first
                current_time = time.time()
                if (
                    current_time - bybit_client.last_sms_time
                    >= bybit_client.config.notifications.termux_sms.cooldown
                ):
                    sms_initiated = bybit_client.send_sms(test_message)  # Send SMS
                else:
                    logger.debug("SMS cooldown active. Skipping test send.")
            except Exception as e:
                logger.warning(f"Error during SMS test attempt: {e}")

            if sms_initiated:
                results.append(
                    (
                        check_name,
                        True,
                        "Test SMS initiated (check phone/logs for outcome).",
                    ),
                )
                passed_checks += 1
            else:
                results.append(
                    (
                        check_name,
                        False,
                        "Test SMS initiation failed or skipped (check config/cooldown/logs).",
                    ),
                )

        # --- Diagnostics Summary ---
        logger.info(
            f"\n{Fore.MAGENTA + Style.BRIGHT}--- Diagnostics Summary ---{Style.RESET_ALL}",
        )
        for name, success, msg in results:
            status_color = Fore.GREEN if success else Fore.RED
            status_icon = "[PASS]" if success else "[FAIL]"
            message_color = Fore.GREEN if success else Fore.RED
            logger.info(
                f"{status_color}{status_icon:<6}{Style.RESET_ALL} {name:<35}:{message_color} {msg}{Style.RESET_ALL}",
            )

        # Define essential checks that must pass for the bot to operate safely
        essential_check_names = {
            "Server Time Sync",
            f"Market Info Load ({config.symbol})",
            "Balance Fetch (API Auth)",
            "WebSocket Instance Creation",
            "WebSocket Connection Viability",
            f"OHLCV Fetch ({config.timeframe})",
            "Daily OHLCV Fetch (Pivots)",
            "Indicators Calculation",
        }
        # Check if all essential checks passed
        essential_results = [
            success for name, success, msg in results if name in essential_check_names
        ]
        essential_passed = (
            all(essential_results) if essential_results else False
        )  # Ensure there were essential checks to pass

        total_passed_count = sum(1 for _, success, _ in results if success)
        total_run_count = len(results)

        if essential_passed:
            failed_non_essential = [
                name
                for name, success, msg in results
                if not success and name not in essential_check_names
            ]
            minor_issues_msg = (
                f" Minor issues detected: {', '.join(failed_non_essential)}."
                if failed_non_essential
                else ""
            )
            logger.success(
                f"\n{Fore.GREEN + Style.BRIGHT}All ESSENTIAL diagnostics PASSED ({total_passed_count}/{total_run_count} total checks).{minor_issues_msg}{Style.RESET_ALL}",
            )
            return True  # Diagnostics passed
        failed_essential = [
            name
            for name, success, msg in results
            if not success and name in essential_check_names
        ]
        logger.error(
            f"\n{Fore.RED + Style.BRIGHT}Diagnostics FAILED. {total_passed_count}/{total_run_count} total checks PASSED.{Style.RESET_ALL}",
        )
        logger.error(
            f"{Fore.RED}Essential checks failed: {', '.join(failed_essential)}{Style.RESET_ALL}",
        )
        logger.error(
            f"{Fore.RED}Review the [FAIL] items above and consult the logs for detailed error messages.{Style.RESET_ALL}",
        )
        return False  # Diagnostics failed

    def _isolate_ws_state_for_test(self) -> dict:
        """Saves current WS state and resets it for a temporary test."""
        with self._ws_lock:
            original_state = {
                "ws": self.ws,
                "ws_connected": self.ws_connected,
                "ws_connecting": self.ws_connecting,
                "ws_topics": self.ws_topics[:],
                "ws_user_callbacks": self.ws_user_callbacks.copy(),
                "ws_reconnect_attempt": self.ws_reconnect_attempt,
            }
            # Reset for test
            self.ws = None
            self.ws_connected = False
            self.ws_connecting = False
            self.ws_topics = []
            self.ws_user_callbacks = {}
            self.ws_reconnect_attempt = 0
            return original_state

    def _restore_ws_state(self, original_state: dict) -> None:
        """Restores the WebSocket state from saved values."""
        with self._ws_lock:
            self.ws = original_state.get("ws")
            self.ws_connected = original_state.get("ws_connected", False)
            self.ws_connecting = original_state.get("ws_connecting", False)
            self.ws_topics = original_state.get("ws_topics", [])
            self.ws_user_callbacks = original_state.get("ws_user_callbacks", {})
            self.ws_reconnect_attempt = original_state.get("ws_reconnect_attempt", 0)


# --- Global Configuration and Environment Setup ---
# Define the directory for logs and configuration files
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_DIR = SCRIPT_DIR / "config"
LOG_DIRECTORY = SCRIPT_DIR / "logs"

# Create directories if they don't exist
CONFIG_DIR.mkdir(exist_ok=True)
LOG_DIRECTORY.mkdir(exist_ok=True)

# Define the path to the configuration file
CONFIG_FILE_PATH = CONFIG_DIR / "config.json"


# Pydantic Model for Application Configuration
# This structure mirrors the default_config_dict in load_config
class LoggingConfig(BaseModel):
    level: str = "INFO"
    log_to_file: bool = True
    log_trades_to_csv: bool = True
    log_indicators: bool = False
    max_log_size_mb: int = 10
    backup_count: int = 5
    include_sensitive_data: bool = False
    log_to_json: bool = False


class TermuxSMSConfig(BaseModel):
    enabled: bool = False
    phone_number: str = ""
    message_prefix: str = "[WB]"
    alert_levels: list[str] = ["INFO", "WARNING", "ERROR"]
    cooldown: int = 300


class NotificationsConfig(BaseModel):
    enabled: bool = True
    trade_entry: bool = True
    trade_exit: bool = True
    error_alerts: bool = True
    daily_summary: bool = True
    webhook_url: str = ""
    termux_sms: TermuxSMSConfig = Field(default_factory=TermuxSMSConfig)


class MTFAnalysisConfig(BaseModel):
    enabled: bool = True
    higher_timeframes: list[str] = ["60", "240"]
    trend_indicators: list[str] = ["ema", "ehlers_supertrend"]
    trend_period: int = 50
    mtf_request_delay_seconds: float = 0.5
    min_trend_agreement_pct: float = 60.0


class MLEnhancementConfig(BaseModel):
    enabled: bool = False
    model_path: str = "ml_model.pkl"
    prediction_threshold: float = 0.6
    model_weight: float = 0.3
    retrain_on_startup: bool = False
    training_data_limit: int = 5000
    prediction_lookahead: int = 12
    sentiment_analysis_enabled: bool = False
    bullish_sentiment_threshold: float = 0.6
    bearish_sentiment_threshold: float = 0.4


class AnalysisModulesConfig(BaseModel):
    mtf_analysis: MTFAnalysisConfig = Field(default_factory=MTFAnalysisConfig)
    ml_enhancement: MLEnhancementConfig = Field(default_factory=MLEnhancementConfig)


class StrategyProfile(BaseModel):
    description: str = ""
    indicators_enabled: dict[str, bool] = Field(default_factory=dict)
    weights: dict[str, float] = Field(default_factory=dict)
    market_condition_criteria: dict[str, Any] = Field(default_factory=dict)


class StrategyManagementConfig(BaseModel):
    adaptive_strategy_enabled: bool = True
    current_strategy_profile: str = "default_scalping"
    strategy_profiles: dict[str, StrategyProfile] = Field(default_factory=dict)


class IndicatorParameters(BaseModel):
    atr_period: int = 14
    ema_short_period: int = 9
    ema_long_period: int = 21
    rsi_period: int = 14
    stoch_rsi_period: int = 14
    stoch_k_period: int = 3
    stoch_d_period: int = 3
    bollinger_bands_period: int = 20
    bollinger_bands_std_dev: float = 2.0
    cci_period: int = 20
    williams_r_period: int = 14
    mfi_period: int = 14
    psar_acceleration: float = 0.02
    psar_max_acceleration: float = 0.2
    sma_short_period: int = 10
    sma_long_period: int = 50
    fibonacci_window: int = 60
    ehlers_fast_period: int = 10
    ehlers_fast_multiplier: float = 2.0
    ehlers_slow_period: int = 20
    ehlers_slow_multiplier: float = 3.0
    macd_fast_period: int = 12
    macd_slow_period: int = 26
    macd_signal_period: int = 9
    adx_period: int = 14
    ichimoku_tenkan_period: int = 9
    ichimoku_kijun_period: int = 26
    ichimoku_senkou_span_b_period: int = 52
    ichimoku_chikou_span_offset: int = 26
    obv_ema_period: int = 20
    cmf_period: int = 20
    rsi_oversold: int = 30
    rsi_overbought: int = 70
    stoch_rsi_oversold: int = 20
    stoch_rsi_overbought: int = 80
    cci_oversold: int = -100
    cci_overbought: int = 100
    williams_r_oversold: int = -80
    williams_r_overbought: int = -20
    mfi_oversold: int = 20
    mfi_overbought: int = 80
    volatility_index_period: int = 20
    vwma_period: int = 20
    volume_delta_period: int = 5
    volume_delta_threshold: float = 0.2
    kaufman_ama_period: int = 10
    kama_fast_period: int = 2
    kama_slow_period: int = 30
    relative_volume_period: int = 20
    relative_volume_threshold: float = 1.5
    market_structure_lookback_period: int = 20
    dema_period: int = 14
    keltner_period: int = 20
    keltner_atr_multiplier: float = 2.0
    roc_period: int = 12
    roc_oversold: float = -5.0
    roc_overbought: float = 5.0
    fisher_transform_length: int = 10
    ehlers_supertrend_atr_len: int = 10
    ehlers_supertrend_mult: float = 3.0
    ehlers_supertrend_ss_len: int = 10
    ehlers_stochrsi_rsi_len: int = 14
    ehlers_stochrsi_stoch_len: int = 14
    ehlers_stochrsi_ss_fast: int = 5
    ehlers_stochrsi_ss_slow: int = 3


class TPConfig(BaseModel):
    mode: str = "atr_multiples"
    targets: list[dict[str, Any]] = Field(default_factory=list)


class SLConfig(BaseModel):
    type: str = "atr_multiple"
    atr_multiple: float = 1.5
    percent: float = 1.0
    use_conditional_stop: bool = True
    stop_order_type: str = "Market"
    trail_stop: dict[str, Any] = Field(
        default_factory=dict,
    )  # e.g., {"enabled": True, "trail_atr_multiple": 0.5, "activation_threshold": 0.8}


class BreakevenConfig(BaseModel):
    enabled: bool = True
    offset_type: str = "atr"
    offset_value: float = 0.1
    lock_in_min_percent: float = 0.0
    sl_trigger_by: str = "LastPrice"


class LiveSyncConfig(BaseModel):
    enabled: bool = False
    poll_ms: int = 2500
    max_exec_fetch: int = 200
    only_track_linked: bool = True
    heartbeat: dict[str, Any] = Field(
        default_factory=lambda: {"enabled": True, "interval_ms": 5000},
    )


class ExecutionConfig(BaseModel):
    use_pybit: bool = False
    testnet: bool = False
    account_type: str = "UNIFIED"
    category: str = "linear"
    position_mode: str = "ONE_WAY"
    leverage: str = "3"
    tp_trigger_by: str = "LastPrice"
    sl_trigger_by: str = "LastPrice"
    default_time_in_force: str = "GoodTillCancel"
    reduce_only_default: bool = False
    post_only_default: bool = False
    position_idx_overrides: dict[str, int] = Field(
        default_factory=lambda: {"ONE_WAY": 0, "HEDGE_BUY": 1, "HEDGE_SELL": 2},
    )
    proxies: dict[str, Any] = Field(
        default_factory=lambda: {"enabled": False, "http": "", "https": ""},
    )
    tp_scheme: TPConfig = Field(default_factory=TPConfig)
    sl_scheme: SLConfig = Field(default_factory=SLConfig)
    breakeven_after_tp1: BreakevenConfig = Field(default_factory=BreakevenConfig)
    live_sync: LiveSyncConfig = Field(default_factory=LiveSyncConfig)
    use_websocket: bool = True
    slippage_adjustment: bool = True
    max_fill_time_ms: int = 5000
    retry_failed_orders: bool = True
    max_order_retries: int = 3
    order_timeout_ms: int = 10000
    dry_run: bool = True
    http_timeout: float = 10.0
    retry_count: int = 3
    retry_delay: float = 5.0


class RiskManagementConfig(BaseModel):
    enabled: bool = True
    max_day_loss_pct: float = 3.0
    max_drawdown_pct: float = 8.0
    cooldown_after_kill_min: int = 120
    spread_filter_bps: float = 5.0
    ev_filter_enabled: bool = False
    max_spread_bps: float = 10.0
    min_volume_usd: float = 50000.0
    max_slippage_bps: float = 5.0
    max_consecutive_losses: int = 5
    min_trades_before_ev: int = 10


class AppConfig(BaseModel):
    # Core Settings
    symbol: str = "BTCUSDT"
    interval: str = DEFAULT_PRIMARY_INTERVAL
    loop_delay: int = DEFAULT_LOOP_DELAY_SECONDS
    orderbook_limit: int = 50
    signal_score_threshold: float = 0.8
    cooldown_sec: int = 60
    hysteresis_ratio: float = 0.85
    volume_confirmation_multiplier: float = 1.0
    base_url: str = BASE_URL
    api_key: str = Field(default=API_KEY)  # Load from env vars or config
    api_secret: str = Field(default=API_SECRET)  # Load from env vars or config
    testnet_mode: bool = Field(
        alias="execution.testnet", default=False,
    )  # Alias for easy access
    initial_candle_history: int = 1000  # Min candles for indicators to calc

    # Strategy Management
    strategy_management: StrategyManagementConfig = Field(
        default_factory=StrategyManagementConfig,
    )

    # Indicator Parameters
    indicators: IndicatorParameters = Field(default_factory=IndicatorParameters)

    # Execution and Trading
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)

    # Risk Management
    risk_management: RiskManagementConfig = Field(default_factory=RiskManagementConfig)

    # Analysis Modules
    analysis_modules: AnalysisModulesConfig = Field(
        default_factory=AnalysisModulesConfig,
    )

    # Notifications
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)

    # Logging Configuration
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    # WebSocket Settings (used by BybitHelper)
    ws_settings: dict[str, str] = Field(
        default_factory=lambda: {
            "public_base_url": WS_PUBLIC_BASE_URL,
            "private_base_url": WS_PRIVATE_BASE_URL,
        },
    )

    # Custom validator for API keys
    @validator("api_key", "api_secret")
    def check_api_credentials(cls, value):
        if not value:
            # Check if execution.dry_run is False, as keys are needed for live trading
            # NOTE: This validation is crude; a more robust check would involve reading the config structure
            # before this validator is potentially called if dry_run is false. For now, warn if missing.
            logger = logging.getLogger(__name__)  # Get logger if available
            if logger:
                logger.warning(
                    "API Key or Secret is missing. Live trading will fail. Set BYBIT_API_KEY and BYBIT_API_SECRET in .env or config.",
                )
            # Allow the program to proceed if dry_run is enabled, keys are not strictly required.
            # However, for live trading, this will cause immediate failure.
            # If required for any operation, consider raising an error here if dry_run is False.
            return value  # Return the empty value to allow Pydantic to process it further if needed.
        return value

    # Model Config for extra fields and alias handling
    class Config:
        extra = "ignore"  # Ignore extra fields in config file
        validate_assignment = (
            True  # Validate assignments to fields after model creation
        )
        allow_population_by_field_name = True  # Allow using field names or aliases


# --- Function to Load and Initialize Everything ---
def setup_global_environment() -> bool:
    """Sets up the global environment: loads config, initializes logger,
    and creates the BybitHelper instance. Returns True on success, False on critical failure.
    """
    global logger, bybit_client  # Declare globals to modify them

    # Load API keys from .env file if it exists
    if Path(".env").exists():
        load_dotenv()

    # Retrieve API keys from environment variables (takes precedence over .env)
    # If they are still None here, they will be used as defaults in AppConfig,
    # which might be okay if dry_run is True, but will fail for live trading.
    global API_KEY, API_SECRET
    API_KEY = os.getenv("BYBIT_API_KEY", API_KEY)
    API_SECRET = os.getenv("BYBIT_API_SECRET", API_SECRET)

    # Initialize basic logger early for critical config loading messages
    try:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            stream=sys.stderr,
        )
        # Create a temporary logger instance for config loading
        temp_logger = logging.getLogger(__name__)
        temp_logger.info("Initializing global environment...")
    except Exception as e:
        print(f"FATAL: Failed to initialize basic logger: {e}", file=sys.stderr)
        return False  # Cannot proceed without basic logging

    # Load configuration
    try:
        config_instance = load_config(CONFIG_FILE_PATH, temp_logger)
        # Re-configure logger using the loaded config
        logger = setup_logger(__name__, config_instance)
        logger.info(f"{Fore.GREEN}Global environment setup complete.{Style.RESET_ALL}")
    except Exception as e:
        temp_logger.critical(
            f"FATAL: Critical error during configuration loading or logger setup: {e}",
            exc_info=True,
        )
        return False  # Critical failure

    # Assign loaded config to global variable
    config = config_instance
    logger.setLevel(logging.DEBUG)  # Set logger to capture all messages for BybitHelper

    # Instantiate BybitHelper
    try:
        # Pass the validated config instance to BybitHelper
        bybit_client = BybitHelper(config)
        logger.info(f"{Fore.GREEN}BybitHelper summoned successfully.{Style.RESET_ALL}")
        return True  # Successfully set up
    except RuntimeError as e:
        logger.critical(f"FATAL: Failed to initialize BybitHelper: {e}", exc_info=True)
        return False  # Critical failure in BybitHelper initialization
    except Exception as e:
        logger.critical(
            f"FATAL: Unexpected error during BybitHelper initialization: {e}",
            exc_info=True,
        )
        return False


# --- Indicator Calculation Module ---
# This section would ideally be in a separate `indicators.py` file.
# For self-containment, it's included here.


def calculate_indicators(
    df: pd.DataFrame, config: AppConfig, daily_df: pd.DataFrame | None = None,
) -> pd.DataFrame | None:
    """Calculates a comprehensive suite of technical indicators on the provided OHLCV DataFrame,
    based on the application configuration. Returns the DataFrame with new indicator columns.
    """
    if df is None or df.empty:
        logger.warning("Cannot calculate indicators: Input DataFrame is empty.")
        return pd.DataFrame()

    # Ensure DataFrame has necessary columns and data types
    required_cols = ["timestamp", "open", "high", "low", "close", "volume"]
    if not all(col in df.columns for col in required_cols):
        logger.error(
            f"Input DataFrame missing required columns. Found: {df.columns.tolist()}, Required: {required_cols}",
        )
        return None

    # Ensure numeric columns are Decimal, others are appropriate types
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns and not isinstance(df[col].iloc[0], Decimal):
            try:
                df[col] = pd.to_numeric(df[col], errors="coerce").apply(
                    lambda x: Decimal(str(x)) if pd.notna(x) else np.nan,
                )
            except Exception as e:
                logger.error(
                    f"Error converting column '{col}' to Decimal for indicator calculation: {e}",
                    exc_info=True,
                )
                return None  # Fail early if conversion fails

    # Ensure timestamp is datetime and UTC aware
    if df["timestamp"].dtype != "datetime64[ns, UTC]":
        try:
            if df["timestamp"].dt.tz is None:
                df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")
            else:
                df["timestamp"] = df["timestamp"].dt.tz_convert("UTC")
        except Exception as e:
            logger.error(
                f"Error localizing/converting timestamps for indicator calculation: {e}",
                exc_info=True,
            )
            return None

    # --- Indicator Calculations ---
    # Use global logger for indicator-specific logging
    # Add indicator columns directly to the DataFrame, handle NaNs appropriately
    logger.debug("Calculating technical indicators...")

    # --- Moving Averages ---
    if config.indicators.ema_short_period > 0:
        df["EMA_Short"] = calculate_ema(
            df["close"], period=config.indicators.ema_short_period,
        )
    if config.indicators.ema_long_period > 0:
        df["EMA_Long"] = calculate_ema(
            df["close"], period=config.indicators.ema_long_period,
        )
    if config.indicators.sma_short_period > 0:
        df["SMA_Short"] = calculate_sma(
            df["close"], period=config.indicators.sma_short_period,
        )
    if config.indicators.sma_long_period > 0:
        df["SMA_Long"] = calculate_sma(
            df["close"], period=config.indicators.sma_long_period,
        )
    if config.indicators.vwma_period > 0:
        df["VWMA"] = calculate_vwma(
            df["close"], df["volume"], period=config.indicators.vwma_period,
        )
    if config.indicators.dema_period > 0:
        df["DEMA"] = calculate_dema(df["close"], period=config.indicators.dema_period)
    if config.indicators.kaufman_ama_period > 0:
        df["KAMA"] = calculate_kama(
            df["close"],
            period=config.indicators.kaufman_ama_period,
            fast_period=config.indicators.kama_fast_period,
            slow_period=config.indicators.kama_slow_period,
        )

    # --- Momentum Oscillators ---
    if config.indicators.rsi_period > 0:
        rsi_values = calculate_rsi(df["close"], period=config.indicators.rsi_period)
        df["RSI"] = rsi_values
        df["RSI_OB"] = config.indicators.rsi_overbought
        df["RSI_OS"] = config.indicators.rsi_oversold
        # Signals
        df["RSI_Cross_Up"] = (rsi_values < config.indicators.rsi_oversold) & (
            rsi_values.shift(1) < config.indicators.rsi_oversold
        )
        df["RSI_Cross_Down"] = (rsi_values > config.indicators.rsi_overbought) & (
            rsi_values.shift(1) > config.indicators.rsi_overbought
        )

    if config.indicators.stoch_rsi_period > 0:
        stoch_rsi_k, stoch_rsi_d = calculate_stoch_rsi(
            df["close"],
            period=config.indicators.stoch_rsi_period,
            k_period=config.indicators.stoch_k_period,
            d_period=config.indicators.stoch_d_period,
        )
        df["StochRSI_K"] = stoch_rsi_k
        df["StochRSI_D"] = stoch_rsi_d
        df["StochRSI_OB"] = config.indicators.stoch_rsi_overbought
        df["StochRSI_OS"] = config.indicators.stoch_rsi_oversold
        # Signals
        df["StochRSI_Cross_Up"] = (
            stoch_rsi_k < config.indicators.stoch_rsi_oversold
        ) & (stoch_rsi_k.shift(1) < config.indicators.stoch_rsi_oversold)
        df["StochRSI_Cross_Down"] = (
            stoch_rsi_k > config.indicators.stoch_rsi_overbought
        ) & (stoch_rsi_k.shift(1) > config.indicators.stoch_rsi_overbought)

    if config.indicators.cci_period > 0:
        cci_values = calculate_cci(
            df["high"], df["low"], df["close"], period=config.indicators.cci_period,
        )
        df["CCI"] = cci_values
        df["CCI_OB"] = config.indicators.cci_overbought
        df["CCI_OS"] = config.indicators.cci_oversold
        # Signals
        df["CCI_Bullish_Signal"] = (cci_values < config.indicators.cci_oversold) & (
            cci_values.shift(1) < config.indicators.cci_oversold
        )
        df["CCI_Bearish_Signal"] = (cci_values > config.indicators.cci_overbought) & (
            cci_values.shift(1) > config.indicators.cci_overbought
        )

    if config.indicators.williams_r_period > 0:
        wr_values = calculate_williams_r(
            df["high"],
            df["low"],
            df["close"],
            period=config.indicators.williams_r_period,
        )
        df["Williams_R"] = wr_values
        df["Williams_R_OB"] = config.indicators.williams_r_overbought
        df["Williams_R_OS"] = config.indicators.williams_r_oversold
        # Signals
        df["Williams_R_Bullish_Signal"] = (
            wr_values > config.indicators.williams_r_overbought
        ) & (wr_values.shift(1) > config.indicators.williams_r_overbought)
        df["Williams_R_Bearish_Signal"] = (
            wr_values < config.indicators.williams_r_oversold
        ) & (wr_values.shift(1) < config.indicators.williams_r_oversold)

    if config.indicators.mfi_period > 0:
        mfi_values = calculate_mfi(
            df["high"],
            df["low"],
            df["close"],
            df["volume"],
            period=config.indicators.mfi_period,
        )
        df["MFI"] = mfi_values
        df["MFI_OB"] = config.indicators.mfi_overbought
        df["MFI_OS"] = config.indicators.mfi_oversold
        # Signals
        df["MFI_Bullish_Signal"] = (mfi_values < config.indicators.mfi_oversold) & (
            mfi_values.shift(1) < config.indicators.mfi_oversold
        )
        df["MFI_Bearish_Signal"] = (mfi_values > config.indicators.mfi_overbought) & (
            mfi_values.shift(1) > config.indicators.mfi_overbought
        )

    # --- Trend and Volatility Indicators ---
    if config.indicators.atr_period > 0:
        df["ATR"] = calculate_atr(
            df["high"], df["low"], df["close"], period=config.indicators.atr_period,
        )

    if config.indicators.psar_acceleration > 0:
        psar_values = calculate_psar(
            df["high"],
            df["low"],
            df["close"],
            config.indicators.psar_acceleration,
            config.indicators.psar_max_acceleration,
        )
        df["PSAR"] = psar_values
        # Determine bullish/bearish PSAR state
        df["PSAR_Trend"] = np.where(
            df["PSAR"] > df["close"],
            "Bearish",
            np.where(df["PSAR"] < df["close"], "Bullish", "Flat"),
        )
        # Signals: Trend change
        df["PSAR_Bullish_Flip"] = (df["PSAR_Trend"] == "Bullish") & (
            df["PSAR_Trend"].shift(1) == "Bearish"
        )
        df["PSAR_Bearish_Flip"] = (df["PSAR_Trend"] == "Bearish") & (
            df["PSAR_Trend"].shift(1) == "Bullish"
        )

    if (
        config.indicators.bollinger_bands_period > 0
        and config.indicators.bollinger_bands_std_dev > 0
    ):
        basis, upper, lower = calculate_bollinger_bands(
            df["close"],
            period=config.indicators.bollinger_bands_period,
            std_dev=config.indicators.bollinger_bands_std_dev,
        )
        df["Bollinger_Basis"] = basis
        df["Bollinger_Upper"] = upper
        df["Bollinger_Lower"] = lower
        # Signals: Price touching bands
        df["Price_Touches_Upper_BB"] = df["close"] >= upper
        df["Price_Touches_Lower_BB"] = df["close"] <= lower

    if (
        config.indicators.keltner_period > 0
        and config.indicators.keltner_atr_multiplier > 0
    ):
        keltner_basis, keltner_upper, keltner_lower = calculate_keltner_channels(
            df["high"],
            df["low"],
            df["close"],
            period=config.indicators.keltner_period,
            atr_multiplier=config.indicators.keltner_atr_multiplier,
        )
        df["Keltner_Basis"] = keltner_basis
        df["Keltner_Upper"] = keltner_upper
        df["Keltner_Lower"] = keltner_lower
        # Signals: Price touching bands
        df["Price_Touches_Upper_KC"] = df["close"] >= keltner_upper
        df["Price_Touches_Lower_KC"] = df["close"] <= keltner_lower

    if config.indicators.adx_period > 0:
        adx_vals = calculate_adx(
            df["high"], df["low"], df["close"], period=config.indicators.adx_period,
        )
        df["ADX"] = adx_vals["ADX"]
        df["ADX_PlusDI"] = adx_vals["PlusDI"]
        df["ADX_MinusDI"] = adx_vals["MinusDI"]
        # Trend strength indication
        df["ADX_Trend_Strength"] = np.where(
            df["ADX"] > 25, "Strong", np.where(df["ADX"] < 20, "Weak", "Moderate"),
        )
        # Trend direction based on DI crossover
        df["ADX_Bullish_Signal"] = (df["ADX_PlusDI"] > df["ADX_MinusDI"]) & (
            df["ADX_PlusDI"].shift(1) <= df["ADX_MinusDI"].shift(1)
        )
        df["ADX_Bearish_Signal"] = (df["ADX_MinusDI"] > df["ADX_PlusDI"]) & (
            df["ADX_MinusDI"].shift(1) <= df["ADX_PlusDI"].shift(1)
        )

    # --- Volume Indicators ---
    df["Volume"] = df["volume"]  # Ensure Volume column exists and is named consistently
    if config.indicators.volume_delta_period > 0:
        volume_delta_values = calculate_volume_delta(
            df["close"], df["volume"], period=config.indicators.volume_delta_period,
        )
        df["Volume_Delta"] = volume_delta_values
        df["Volume_Delta_Signal"] = (
            df["Volume_Delta"] > config.indicators.volume_delta_threshold
        )  # Simple threshold signal

    if config.indicators.obv_ema_period > 0:
        df["OBV"] = calculate_obv(df["close"], df["volume"])
        df["OBV_EMA"] = calculate_ema(
            df["OBV"], period=config.indicators.obv_ema_period,
        )

    if config.indicators.cmf_period > 0:
        df["CMF"] = calculate_cmf(
            df["high"],
            df["low"],
            df["close"],
            df["volume"],
            period=config.indicators.cmf_period,
        )

    if config.indicators.relative_volume_period > 0:
        df["Relative_Volume"] = calculate_relative_volume(
            df["volume"], period=config.indicators.relative_volume_period,
        )
        df["Relative_Volume_Signal"] = (
            df["Relative_Volume"] > config.indicators.relative_volume_threshold
        )

    # --- MACD ---
    if (
        config.indicators.macd_fast_period > 0
        and config.indicators.macd_slow_period > 0
        and config.indicators.macd_signal_period > 0
    ):
        macd_line, signal_line, macd_hist = calculate_macd(
            df["close"],
            fast_period=config.indicators.macd_fast_period,
            slow_period=config.indicators.macd_slow_period,
            signal_period=config.indicators.macd_signal_period,
        )
        df["MACD_Line"] = macd_line
        df["MACD_Signal"] = signal_line
        df["MACD_Hist"] = macd_hist
        # Signals: Crossovers
        df["MACD_Bullish_Cross"] = (macd_line > signal_line) & (
            macd_line.shift(1) <= signal_line.shift(1)
        )
        df["MACD_Bearish_Cross"] = (macd_line < signal_line) & (
            macd_line.shift(1) >= signal_line.shift(1)
        )

    # --- Ehlers Indicators ---
    if config.indicators.ehlers_supertrend_atr_len > 0:
        # Apply Ehlers SuperTrend (using settings for "Fast" mode as default)
        supertrend_signal, supertrend_line = calculate_ehlers_supertrend(
            df["high"],
            df["low"],
            df["close"],
            atr_len=config.indicators.ehlers_supertrend_atr_len,
            multiplier=config.indicators.ehlers_supertrend_mult,
            ss_len=config.indicators.ehlers_supertrend_ss_len,  # Optional SS length
        )
        df["Ehlers_SuperTrend"] = supertrend_line
        df["Ehlers_SuperTrend_Trend"] = np.where(
            supertrend_line > df["close"],
            "Bearish",
            np.where(supertrend_line < df["close"], "Bullish", "Flat"),
        )
        # Signals: Trend flips
        df["Ehlers_Bullish_Flip"] = (df["Ehlers_SuperTrend_Trend"] == "Bullish") & (
            df["Ehlers_SuperTrend_Trend"].shift(1) == "Bearish"
        )
        df["Ehlers_Bearish_Flip"] = (df["Ehlers_SuperTrend_Trend"] == "Bearish") & (
            df["Ehlers_SuperTrend_Trend"].shift(1) == "Bullish"
        )

    if config.indicators.fisher_transform_length > 0:
        fisher, signal = calculate_fisher_transform(
            df["high"],
            df["low"],
            df["close"],
            length=config.indicators.fisher_transform_length,
        )
        df["Fisher_Transform"] = fisher
        df["Fisher_Signal"] = signal
        # Signals: Crossovers
        df["Fisher_Bullish_Cross"] = (fisher > signal) & (
            fisher.shift(1) <= signal.shift(1)
        )
        df["Fisher_Bearish_Cross"] = (fisher < signal) & (
            fisher.shift(1) >= signal.shift(1)
        )

    if config.indicators.ehlers_stochrsi_rsi_len > 0:
        stoch_rsi_ehlers = calculate_ehlers_stochrsi(
            df["close"],
            rsi_len=config.indicators.ehlers_stochrsi_rsi_len,
            stoch_len=config.indicators.ehlers_stochrsi_stoch_len,
            fast_len=config.indicators.ehlers_stochrsi_ss_fast,
            slow_len=config.indicators.ehlers_stochrsi_ss_slow,
        )
        df["Ehlers_StochRSI"] = stoch_rsi_ehlers
        df["Ehlers_StochRSI_OB"] = 80  # Common overbought level for StochRSI
        df["Ehlers_StochRSI_OS"] = 20  # Common oversold level for StochRSI
        # Signals
        df["Ehlers_StochRSI_Bullish_Signal"] = (
            stoch_rsi_ehlers < df["Ehlers_StochRSI_OS"]
        ) & (stoch_rsi_ehlers.shift(1) < df["Ehlers_StochRSI_OS"])
        df["Ehlers_StochRSI_Bearish_Signal"] = (
            stoch_rsi_ehlers > df["Ehlers_StochRSI_OB"]
        ) & (stoch_rsi_ehlers.shift(1) > df["Ehlers_StochRSI_OB"])

    # --- Ichimoku Cloud ---
    if (
        config.indicators.ichimoku_tenkan_period > 0
        and config.indicators.ichimoku_kijun_period > 0
        and config.indicators.ichimoku_senkou_span_b_period > 0
    ):
        tenkan, kijun, senkou_a, senkou_b, chikou = calculate_ichimoku_cloud(
            df["high"],
            df["low"],
            df["close"],
            tenkan_period=config.indicators.ichimoku_tenkan_period,
            kijun_period=config.indicators.ichimoku_kijun_period,
            senkou_span_b_period=config.indicators.ichimoku_senkou_span_b_period,
            chikou_offset=config.indicators.ichimoku_chikou_span_offset,
        )
        df["Ichimoku_Tenkan"] = tenkan
        df["Ichimoku_Kijun"] = kijun
        df["Ichimoku_Senkou_A"] = senkou_a
        df["Ichimoku_Senkou_B"] = senkou_b
        df["Ichimoku_Chikou"] = chikou
        # Cloud formation (Senkou Spans)
        df["Ichimoku_Cloud_Future"] = senkou_a > senkou_b  # Bullish cloud future
        df["Ichimoku_Cloud_Past"] = senkou_a.shift(
            config.indicators.ichimoku_chikou_span_offset,
        ) > senkou_b.shift(
            config.indicators.ichimoku_chikou_span_offset,
        )  # Bullish cloud past

        # Signals: Crosses
        df["Ichimoku_Tenkan_Kijun_Bullish_Cross"] = (tenkan > kijun) & (
            tenkan.shift(1) <= kijun.shift(1)
        )
        df["Ichimoku_Tenkan_Kijun_Bearish_Cross"] = (tenkan < kijun) & (
            tenkan.shift(1) >= kijun.shift(1)
        )

    # --- Pivot Points (requires Daily OHLCV data) ---
    if (
        config.indicators.fibonacci_window > 0
        and daily_df is not None
        and not daily_df.empty
    ):
        try:
            pivot_points = calculate_pivot_points_fibonacci(
                daily_df, window=config.indicators.fibonacci_window,
            )
            # Merge pivot data into the current DataFrame based on timestamp
            df = pd.merge(df, pivot_points, on="timestamp", how="left")
            # Add placeholder columns if merge didn't add them (e.g., if daily data was sparse)
            for pp_col in ["Pivot", "R1", "R2", "R3", "S1", "S2", "S3", "BC", "BS"]:
                if pp_col not in df.columns:
                    df[pp_col] = np.nan
            # Signals: Price crossing pivots
            df["Price_Crossed_R1"] = (df["close"] >= df["R1"]) & (
                df["close"].shift(1) < df["R1"]
            )
            df["Price_Crossed_S1"] = (df["close"] <= df["S1"]) & (
                df["close"].shift(1) > df["S1"]
            )
            df["Price_Crossed_Pivot"] = (df["close"] >= df["Pivot"]) & (
                df["close"].shift(1) < df["Pivot"]
            )

        except Exception as e:
            logger.warning(
                f"Could not calculate Fibonacci Pivot Points: {e}. Check daily data availability and format.",
                exc_info=True,
            )

    # --- Volatility Index ---
    if config.indicators.volatility_index_period > 0:
        df["Volatility_Index"] = calculate_volatility_index(
            df["high"], df["low"], period=config.indicators.volatility_index_period,
        )

    # --- Market Structure ---
    if config.indicators.market_structure_lookback_period > 0:
        # Detect market structure points (HH, HL, LH, LL)
        market_structure = detect_market_structure(
            df["high"],
            df["low"],
            lookback=config.indicators.market_structure_lookback_period,
        )
        df["Market_Structure"] = (
            market_structure  # Stores 'HH', 'HL', 'LH', 'LL', or None
        )

        # Simplified trend determination based on structure
        df["MS_Trend"] = np.nan
        df.loc[df["Market_Structure"].isin(["HH", "HL"]), "MS_Trend"] = "Bullish"
        df.loc[df["Market_Structure"].isin(["LH", "LL"]), "MS_Trend"] = "Bearish"
        # Fill forward for structure trend if no new point detected
        df["MS_Trend"] = df["MS_Trend"].ffill()

    # --- Candlestick Patterns ---
    if (
        config.indicators.roc_period > 0
    ):  # Using ROC period for a loose lookback for patterns
        df["ROC"] = calculate_roc(df["close"], period=config.indicators.roc_period)
        df["ROC_Bullish_Signal"] = df["ROC"] > config.indicators.roc_oversold
        df["ROC_Bearish_Signal"] = df["ROC"] < config.indicators.roc_overbought

    # Calculate candlestick patterns (more complex, requires specific logic per pattern)
    # Placeholder for candlestick pattern analysis
    df["Candlestick_Pattern"] = detect_candlestick_patterns(
        df,
    )  # This function would need implementation

    # --- Order Book Imbalance (requires order book data, not available from OHLCV) ---
    # Placeholder for Order Book Imbalance calculation if order book data were available
    df["OrderBook_Imbalance"] = np.nan

    # --- Expectation Value (placeholder) ---
    # Placeholder for EV calculation, requires trade execution data or backtesting simulation
    df["Expectation_Value"] = np.nan

    # --- Populate specific signal columns based on common indicator conditions ---
    # These columns are often used by strategy profiles for scoring
    df["Is_Bullish_OB"] = (
        (df["RSI"] < config.indicators.rsi_oversold)
        | (df["StochRSI_K"] < config.indicators.stoch_rsi_oversold)
        | (df["CCI"] < config.indicators.cci_oversold)
        | (df["Williams_R"] > config.indicators.williams_r_overbought)
        | (df["MFI"] < config.indicators.mfi_oversold)
    )
    df["Is_Bearish_OB"] = (
        (df["RSI"] > config.indicators.rsi_overbought)
        | (df["StochRSI_K"] > config.indicators.stoch_rsi_overbought)
        | (df["CCI"] > config.indicators.cci_overbought)
        | (df["Williams_R"] < config.indicators.williams_r_oversold)
        | (df["MFI"] > config.indicators.mfi_overbought)
    )

    # EMA Alignment
    df["EMA_Alignment_Bullish"] = df["EMA_Short"] > df["EMA_Long"]
    df["EMA_Alignment_Bearish"] = df["EMA_Short"] < df["EMA_Long"]

    # SMA Trend Filter
    df["SMA_Trend_Bullish"] = (
        df["SMA_Long"] > df["SMA_Short"]
    )  # Or other logic depending on desired trend filter
    df["SMA_Trend_Bearish"] = df["SMA_Long"] < df["SMA_Short"]

    # Volatility Filter (using ATR as a proxy)
    if "ATR" in df.columns and config.indicators.atr_period > 0:
        # Volatility as a percentage of close price
        avg_volatility_pct = (
            (df["ATR"] / df["close"]) * 100 if df["close"] != 0 else np.nan
        )
        df["Volatility_Pct"] = avg_volatility_pct
        # Example: High volatility if Volatility_Pct > 2%
        df["High_Volatility"] = df["Volatility_Pct"] > 2.0

    logger.debug("Indicator calculations complete.")
    return df


# --- Indicator Calculation Helper Functions ---
# These should be robust and handle NaNs correctly.


def calculate_sma(data: pd.Series, period: int) -> pd.Series:
    """Calculates Simple Moving Average."""
    if period <= 0:
        return pd.Series(np.nan, index=data.index)
    try:
        return data.rolling(window=period).mean()
    except Exception as e:
        logger.warning(f"Error calculating SMA({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=data.index)


def calculate_ema(data: pd.Series, period: int) -> pd.Series:
    """Calculates Exponential Moving Average."""
    if period <= 0:
        return pd.Series(np.nan, index=data.index)
    try:
        return data.ewm(span=period, adjust=False).mean()
    except Exception as e:
        logger.warning(f"Error calculating EMA({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=data.index)


def calculate_vwma(
    close_data: pd.Series, volume_data: pd.Series, period: int,
) -> pd.Series:
    """Calculates Volume Weighted Moving Average."""
    if period <= 0:
        return pd.Series(np.nan, index=close_data.index)
    try:
        # Calculate Typical Price (H+L+C)/3
        typical_price = (
            close_data + close_data.shift(1) + close_data.shift(2)
        ) / 3  # Use close for simplicity if H/L not critical
        if typical_price.isnull().all():
            typical_price = close_data  # Fallback if H/L not available

        # Calculate VWAP for the period
        vwap_series = (typical_price * volume_data).rolling(
            window=period,
        ).sum() / volume_data.rolling(window=period).sum()
        return vwap_series
    except Exception as e:
        logger.warning(f"Error calculating VWMA({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=close_data.index)


def calculate_kama(
    data: pd.Series, period: int, fast_period: int, slow_period: int,
) -> pd.Series:
    """Calculates Kaufman's Adaptive Moving Average (KAMA)."""
    if period <= 0 or fast_period <= 0 or slow_period <= 0:
        return pd.Series(np.nan, index=data.index)
    try:
        # Step 1: Calculate the Efficiency Ratio (ER)
        # ER = ( (Close - Prior Close) / (High - Low) ) * 100
        # Handle potential division by zero or NaN
        price_change = data - data.shift(1)
        h_l_diff = data.rolling(window=period).max() - data.rolling(window=period).min()
        h_l_diff = h_l_diff.replace(0, 1e-9)  # Avoid division by zero
        er = (price_change / h_l_diff) * 100
        er = er.fillna(0)  # Fill initial NaNs

        # Step 2: Calculate the Noise Ratio (NR)
        # NR = 100 - ER
        nr = 100 - er

        # Step 3: Calculate the Smoothing Constant (SC)
        # SC = ER / (period * Noise_Ratio)
        # Use SC_fast = 2 / (fast_period + 1) and SC_slow = 2 / (slow_period + 1) for calculation basis
        sc_fast_base = 2 / (fast_period + 1)
        sc_slow_base = 2 / (slow_period + 1)
        sc = (er / period) * (sc_fast_base - sc_slow_base) + sc_slow_base

        # Step 4: Calculate KAMA
        # KAMA = Prior KAMA + SC * (Close - Prior KAMA)
        kama = pd.Series(np.nan, index=data.index)
        # Initialize with the first valid price as KAMA
        kama.iloc[period - 1] = data.iloc[period - 1]

        for i in range(period, len(data)):
            if pd.isna(kama.iloc[i - 1]):  # If previous KAMA is NaN, re-initialize
                kama.iloc[i] = data.iloc[i]
            else:
                kama.iloc[i] = kama.iloc[i - 1] + sc.iloc[i] * (
                    data.iloc[i] - kama.iloc[i - 1]
                )
        return kama

    except Exception as e:
        logger.warning(
            f"Error calculating KAMA({period}, fast={fast_period}, slow={slow_period}): {e}",
            exc_info=True,
        )
        return pd.Series(np.nan, index=data.index)


def calculate_ema(data: pd.Series, period: int) -> pd.Series:
    """Calculates Exponential Moving Average."""
    if period <= 0:
        return pd.Series(np.nan, index=data.index)
    try:
        return data.ewm(span=period, adjust=False).mean()
    except Exception as e:
        logger.warning(f"Error calculating EMA({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=data.index)


def calculate_rsi(data: pd.Series, period: int) -> pd.Series:
    """Calculates Relative Strength Index."""
    if period <= 0:
        return pd.Series(np.nan, index=data.index)
    try:
        delta = data.diff()
        gain = (delta.where(delta > 0)).fillna(0)
        loss = (-delta.where(delta < 0)).fillna(0)

        avg_gain = gain.ewm(span=period, adjust=False).mean()
        avg_loss = loss.ewm(span=period, adjust=False).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    except Exception as e:
        logger.warning(f"Error calculating RSI({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=data.index)


def calculate_stoch_rsi(
    data: pd.Series, period: int, k_period: int, d_period: int,
) -> tuple[pd.Series, pd.Series]:
    """Calculates Stochastic RSI."""
    if period <= 0 or k_period <= 0 or d_period <= 0:
        return pd.Series(np.nan, index=data.index), pd.Series(np.nan, index=data.index)
    try:
        rsi = calculate_rsi(data, period=period)
        if rsi.isnull().all():
            return pd.Series(np.nan, index=data.index), pd.Series(
                np.nan, index=data.index,
            )

        min_rsi = rsi.rolling(window=period).min()
        max_rsi = rsi.rolling(window=period).max()

        stoch_rsi = 100 * ((rsi - min_rsi) / (max_rsi - min_rsi))
        stoch_rsi = stoch_rsi.fillna(0)  # Fill initial NaNs

        # Calculate %K and %D
        stoch_k = stoch_rsi.rolling(window=k_period).mean()
        stoch_d = stoch_k.rolling(window=d_period).mean()

        return stoch_k, stoch_d
    except Exception as e:
        logger.warning(
            f"Error calculating Stochastic RSI (Period={period}, K={k_period}, D={d_period}): {e}",
            exc_info=True,
        )
        return pd.Series(np.nan, index=data.index), pd.Series(np.nan, index=data.index)


def calculate_cci(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int,
) -> pd.Series:
    """Calculates Commodity Channel Index."""
    if period <= 0:
        return pd.Series(np.nan, index=high.index)
    try:
        typical_price = (high + low + close) / 3
        cci = typical_price.rolling(window=period).apply(
            lambda x: ta.cci(x.iloc[-1], x.iloc[0], x.iloc[period - 1], period=period)
            if len(x) == period
            else np.nan,
            raw=True,
        )  # Use ta-lib for accuracy if available
        # Fallback if ta-lib not available or to implement manually:
        if cci.isnull().all():
            tp_mean = typical_price.rolling(window=period).mean()
            tp_dev = abs(typical_price - tp_mean).rolling(window=period).sum() / period
            cci = (typical_price - tp_mean) / (
                0.015 * tp_dev
            )  # 0.015 is a common constant multiplier
        return cci
    except Exception as e:
        logger.warning(f"Error calculating CCI({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=high.index)


def calculate_williams_r(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int,
) -> pd.Series:
    """Calculates Williams %R."""
    if period <= 0:
        return pd.Series(np.nan, index=high.index)
    try:
        highest_high = high.rolling(window=period).max()
        lowest_low = low.rolling(window=period).min()
        wr = -100 * ((highest_high - close) / (highest_high - lowest_low))
        return wr
    except Exception as e:
        logger.warning(f"Error calculating Williams %R({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=high.index)


def calculate_mfi(
    high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int,
) -> pd.Series:
    """Calculates Money Flow Index."""
    if period <= 0:
        return pd.Series(np.nan, index=high.index)
    try:
        typical_price = (high + low + close) / 3
        money_flow = typical_price * volume
        positive_mf = money_flow.where(typical_price > typical_price.shift(1)).fillna(0)
        negative_mf = money_flow.where(typical_price < typical_price.shift(1)).fillna(0)

        positive_mf_sum = positive_mf.rolling(window=period).sum()
        negative_mf_sum = negative_mf.rolling(window=period).sum()

        money_ratio = positive_mf_sum / negative_mf_sum
        mfi = 100 - (100 / (1 + money_ratio))
        return mfi
    except Exception as e:
        logger.warning(f"Error calculating MFI({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=high.index)


def calculate_atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int,
) -> pd.Series:
    """Calculates Average True Range."""
    if period <= 0:
        return pd.Series(np.nan, index=high.index)
    try:
        # Calculate True Range (TR)
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # Calculate ATR using EMA
        atr = true_range.ewm(span=period, adjust=False).mean()
        return atr
    except Exception as e:
        logger.warning(f"Error calculating ATR({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=high.index)


def calculate_psar(
    high: pd.Series, low: pd.Series, close: pd.Series, af_start: float, af_max: float,
) -> pd.Series:
    """Calculates Parabolic Stop and Reverse (PSAR)."""
    # Using a simplified manual implementation as ta-lib might not be available
    # A full implementation requires careful state management (AF, EP, trend)
    # This is a placeholder and might need refinement or ta-lib integration.
    if af_start <= 0 or af_max <= 0:
        return pd.Series(np.nan, index=high.index)
    try:
        # Placeholder: Return NaNs or a very basic calculation
        # A proper implementation would be much more complex.
        # For now, we return NaNs to signify it's not reliably calculated here.
        logger.warning(
            "Manual PSAR calculation is a placeholder and may not be accurate. Consider using a library like TA-Lib.",
        )
        return pd.Series(np.nan, index=high.index)
    except Exception as e:
        logger.warning(
            f"Error calculating PSAR (AF_Start={af_start}): {e}", exc_info=True,
        )
        return pd.Series(np.nan, index=high.index)


def calculate_bollinger_bands(
    data: pd.Series, period: int, std_dev: float,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Calculates Bollinger Bands (Basis, Upper, Lower)."""
    if period <= 0 or std_dev <= 0:
        return (
            pd.Series(np.nan, index=data.index),
            pd.Series(np.nan, index=data.index),
            pd.Series(np.nan, index=data.index),
        )
    try:
        basis = calculate_sma(data, period=period)
        if basis.isnull().all():
            return (
                pd.Series(np.nan, index=data.index),
                pd.Series(np.nan, index=data.index),
                pd.Series(np.nan, index=data.index),
            )

        std_dev_prices = data.rolling(window=period).std()
        upper = basis + (std_dev_prices * std_dev)
        lower = basis - (std_dev_prices * std_dev)
        return basis, upper, lower
    except Exception as e:
        logger.warning(
            f"Error calculating Bollinger Bands (Period={period}, StdDev={std_dev}): {e}",
            exc_info=True,
        )
        return (
            pd.Series(np.nan, index=data.index),
            pd.Series(np.nan, index=data.index),
            pd.Series(np.nan, index=data.index),
        )


def calculate_keltner_channels(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int,
    atr_multiplier: float,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Calculates Keltner Channels."""
    if period <= 0 or atr_multiplier <= 0:
        return (
            pd.Series(np.nan, index=high.index),
            pd.Series(np.nan, index=high.index),
            pd.Series(np.nan, index=high.index),
        )
    try:
        basis = calculate_ema(close, period=period)  # EMA is common for Keltner basis
        if basis.isnull().all():
            return (
                pd.Series(np.nan, index=high.index),
                pd.Series(np.nan, index=high.index),
                pd.Series(np.nan, index=high.index),
            )

        atr = calculate_atr(high, low, close, period=period)
        upper = basis + (atr * atr_multiplier)
        lower = basis - (atr * atr_multiplier)
        return basis, upper, lower
    except Exception as e:
        logger.warning(
            f"Error calculating Keltner Channels (Period={period}, ATRMult={atr_multiplier}): {e}",
            exc_info=True,
        )
        return (
            pd.Series(np.nan, index=high.index),
            pd.Series(np.nan, index=high.index),
            pd.Series(np.nan, index=high.index),
        )


def calculate_adx(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int,
) -> dict[str, pd.Series]:
    """Calculates ADX, PlusDI, MinusDI."""
    if period <= 0:
        return {
            "ADX": pd.Series(np.nan, index=high.index),
            "PlusDI": pd.Series(np.nan, index=high.index),
            "MinusDI": pd.Series(np.nan, index=high.index),
        }
    try:
        # Calculate Directional Movement (+DM, -DM)
        up_move = high.diff()
        down_move = low.diff()
        plus_dm = pd.Series(np.nan, index=high.index)
        minus_dm = pd.Series(np.nan, index=high.index)

        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), -down_move, 0)

        # Smoothed Directional Indicators (+DI, -DI) using Wilder's smoothing (similar to EMA but different factor)
        # Smoothed value = Prior Smoothed + (Current Value - Prior Smoothed) / Period
        # Or using EMA with period: TR = EMA(TR, period)
        # Using EMA for simplicity here. Wilder's smoothing uses period / (period + 1) instead of 2/(period+1).
        plus_di = plus_dm.ewm(span=period, adjust=False).mean()
        minus_di = minus_dm.ewm(span=period, adjust=False).mean()

        # Calculate Directional Index (DX)
        di_sum = plus_di + minus_di
        di_diff = abs(plus_di - minus_di)
        # Avoid division by zero
        di_sum = di_sum.replace(0, 1e-9)
        dx = (di_diff / di_sum) * 100

        # Calculate ADX from DX using EMA
        adx = dx.ewm(span=period, adjust=False).mean()

        return {"ADX": adx, "PlusDI": plus_di, "MinusDI": minus_di}
    except Exception as e:
        logger.warning(f"Error calculating ADX({period}): {e}", exc_info=True)
        return {
            "ADX": pd.Series(np.nan, index=high.index),
            "PlusDI": pd.Series(np.nan, index=high.index),
            "MinusDI": pd.Series(np.nan, index=high.index),
        }


def calculate_volume_delta(
    close: pd.Series, volume: pd.Series, period: int,
) -> pd.Series:
    """Calculates Volume Delta (Buy Volume - Sell Volume) over a period."""
    if period <= 0:
        return pd.Series(np.nan, index=close.index)
    try:
        # Simple approach: assume volume is buy volume if close > open, sell volume if close < open
        # This is a simplification; actual buy/sell volume requires order book or tick data.
        buy_volume = volume.where(close > close.shift(1)).fillna(0)
        sell_volume = volume.where(close < close.shift(1)).fillna(0)

        volume_delta_per_candle = buy_volume - sell_volume
        # Calculate rolling sum of volume delta
        volume_delta_rolled = volume_delta_per_candle.rolling(window=period).sum()
        return volume_delta_rolled
    except Exception as e:
        logger.warning(f"Error calculating Volume Delta({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=close.index)


def calculate_relative_volume(volume: pd.Series, period: int) -> pd.Series:
    """Calculates Relative Volume (Current Volume / Average Volume)."""
    if period <= 0:
        return pd.Series(np.nan, index=volume.index)
    try:
        avg_volume = volume.rolling(window=period).mean()
        # Avoid division by zero
        avg_volume = avg_volume.replace(0, 1e-9)
        relative_vol = volume / avg_volume
        return relative_vol
    except Exception as e:
        logger.warning(
            f"Error calculating Relative Volume({period}): {e}", exc_info=True,
        )
        return pd.Series(np.nan, index=volume.index)


def calculate_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """Calculates On-Balance Volume."""
    try:
        obv = pd.Series(index=close.index, dtype="float64")
        obv.iloc[0] = 0  # Initialize OBV

        for i in range(1, len(close)):
            if close.iloc[i] > close.iloc[i - 1]:
                obv.iloc[i] = obv.iloc[i - 1] + volume.iloc[i]
            elif close.iloc[i] < close.iloc[i - 1]:
                obv.iloc[i] = obv.iloc[i - 1] - volume.iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i - 1]
        return obv
    except Exception as e:
        logger.warning(f"Error calculating OBV: {e}", exc_info=True)
        return pd.Series(np.nan, index=close.index)


def calculate_cmf(
    high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int,
) -> pd.Series:
    """Calculates Chaikin Money Flow."""
    if period <= 0:
        return pd.Series(np.nan, index=high.index)
    try:
        # Calculate Money Flow Multiplier (MFM)
        mfm = ((close - low) - (high - close)) / (high - low)
        # Avoid division by zero or NaN in (high - low)
        mfm = mfm.replace([np.inf, -np.inf], 0)
        mfm = mfm.fillna(0)

        # Calculate Money Flow (MF)
        mf = mfm * volume

        # Calculate CMF over the period using rolling sum
        cmf = mf.rolling(window=period).sum() / volume.rolling(window=period).sum()
        return cmf
    except Exception as e:
        logger.warning(f"Error calculating CMF({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=high.index)


def calculate_macd(
    close: pd.Series, fast_period: int, slow_period: int, signal_period: int,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Calculates MACD (MACD Line, Signal Line, Histogram)."""
    if (
        fast_period <= 0
        or slow_period <= 0
        or signal_period <= 0
        or fast_period >= slow_period
    ):
        return (
            pd.Series(np.nan, index=close.index),
            pd.Series(np.nan, index=close.index),
            pd.Series(np.nan, index=close.index),
        )
    try:
        ema_fast = calculate_ema(close, period=fast_period)
        ema_slow = calculate_ema(close, period=slow_period)

        macd_line = ema_fast - ema_slow
        signal_line = calculate_ema(macd_line, period=signal_period)
        macd_hist = macd_line - signal_line

        return macd_line, signal_line, macd_hist
    except Exception as e:
        logger.warning(
            f"Error calculating MACD (Fast={fast_period}, Slow={slow_period}, Signal={signal_period}): {e}",
            exc_info=True,
        )
        return (
            pd.Series(np.nan, index=close.index),
            pd.Series(np.nan, index=close.index),
            pd.Series(np.nan, index=close.index),
        )


# Ehlers Indicator Calculations (Simplified placeholders, might require external libraries or detailed implementation)
# These are complex and require precise state management. Using basic logic for demonstration.


def calculate_ehlers_supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    atr_len: int,
    multiplier: float,
    ss_len: int | None = None,
) -> tuple[pd.Series, pd.Series]:
    """Placeholder for Ehlers SuperTrend calculation. Requires precise implementation."""
    # A true SuperTrend implementation involves ATR and trend direction tracking.
    # This placeholder returns NaNs.
    logger.warning(
        "Ehlers SuperTrend calculation is a placeholder. Requires detailed implementation.",
    )
    return pd.Series(np.nan, index=high.index), pd.Series(np.nan, index=high.index)


def calculate_fisher_transform(
    high: pd.Series, low: pd.Series, close: pd.Series, length: int,
) -> tuple[pd.Series, pd.Series]:
    """Placeholder for Ehlers Fisher Transform calculation."""
    # Requires calculation of Highest High and Lowest Low over `length` period.
    logger.warning(
        "Ehlers Fisher Transform calculation is a placeholder. Requires detailed implementation.",
    )
    return pd.Series(np.nan, index=high.index), pd.Series(np.nan, index=high.index)


def calculate_ehlers_stochrsi(
    close: pd.Series, rsi_len: int, stoch_len: int, fast_len: int, slow_len: int,
) -> pd.Series:
    """Placeholder for Ehlers Stochastic RSI calculation."""
    # StochRSI calculation is already implemented above, this function might aim for Ehlers' specific version.
    logger.warning(
        "Ehlers Stochastic RSI calculation is a placeholder. Consider using the standard StochRSI or verify Ehlers' method.",
    )
    # For now, defer to the standard implementation. If Ehlers' version differs significantly,
    # this would need its own logic.
    stoch_k, _ = calculate_stoch_rsi(close, rsi_len, stoch_len, fast_len)
    return stoch_k  # Returning StochRSI %K as a proxy


def calculate_ichimoku_cloud(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    tenkan_period: int,
    kijun_period: int,
    senkou_span_b_period: int,
    chikou_offset: int,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """Calculates Ichimoku Cloud components."""
    if tenkan_period <= 0 or kijun_period <= 0 or senkou_span_b_period <= 0:
        return (
            pd.Series(np.nan, index=high.index),
            pd.Series(np.nan, index=high.index),
            pd.Series(np.nan, index=high.index),
            pd.Series(np.nan, index=high.index),
            pd.Series(np.nan, index=high.index),
        )
    try:
        # Conversion periods
        tenkan_sen = (
            high.rolling(window=tenkan_period).max()
            + low.rolling(window=tenkan_period).min()
        ) / 2
        kijun_sen = (
            high.rolling(window=kijun_period).max()
            + low.rolling(window=kijun_period).min()
        ) / 2

        # Senkou Span A (Leading Span 1)
        senkou_span_a = (tenkan_sen + kijun_sen) / 2

        # Senkou Span B (Leading Span 2)
        senkou_span_b = (
            high.rolling(window=senkou_span_b_period).max()
            + low.rolling(window=senkou_span_b_period).min()
        ) / 2

        # Chikou Span (Lagging Span) - shifted back by kijun_period (common offset)
        # The offset is applied in the data frame itself, so here we just return close series.
        # The dataframe merge/lookup handles the offset.
        chikou_span = close

        return tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span
    except Exception as e:
        logger.warning(f"Error calculating Ichimoku Cloud: {e}", exc_info=True)
        return (
            pd.Series(np.nan, index=high.index),
            pd.Series(np.nan, index=high.index),
            pd.Series(np.nan, index=high.index),
            pd.Series(np.nan, index=high.index),
            pd.Series(np.nan, index=high.index),
        )


def calculate_pivot_points_fibonacci(
    daily_df: pd.DataFrame, window: int,
) -> pd.DataFrame:
    """Calculates Fibonacci Pivot Points based on daily High, Low, Close."""
    if daily_df.empty or window <= 0:
        return pd.DataFrame()
    try:
        # Ensure required columns are present and numeric
        required_cols = ["high", "low", "close"]
        if not all(col in daily_df.columns for col in required_cols):
            logger.error(
                "Daily DataFrame missing required columns for Pivot calculation.",
            )
            return pd.DataFrame()

        # Calculate Standard Pivots (P)
        P = (daily_df["high"] + daily_df["low"] + daily_df["close"]) / 3

        # Calculate Resistance (R) and Support (S) levels
        R1 = (2 * P) - daily_df["low"]
        S1 = (2 * P) - daily_df["high"]

        R2 = P + (daily_df["high"] - daily_df["low"])
        S2 = P - (df["high"] - df["low"])

        R3 = P + 2 * (daily_df["high"] - daily_df["low"])
        S3 = P - 2 * (df["high"] - df["low"])

        # Calculate Camilla Boyer (BC) and Bollinger Support (BS) - often derived from pivots
        # These might need specific definitions; using common interpretations:
        BC = P - (df["high"] - df["low"])  # Simplified BC
        BS = P + (df["high"] - df["low"])  # Simplified BS

        # Create DataFrame for pivot points, ensure timestamp alignment
        pivot_df = pd.DataFrame(
            {
                "timestamp": daily_df["timestamp"],
                "Pivot": P,
                "R1": R1,
                "R2": R2,
                "R3": R3,
                "S1": S1,
                "S2": S2,
                "S3": S3,
                "BC": BC,
                "BS": BS,
            },
        )

        # Apply rolling window to get pivots for the lookback period
        # This calculates pivots based on the last `window` days' data.
        # We need to apply this rolling calculation carefully.
        # A common approach is to calculate pivots for each day based on the previous N days' data.
        # For simplicity here, let's assume `daily_df` is already aligned and we want pivots for each day.
        # If a rolling calculation is needed, it implies calculating pivots N days in the past for each current bar.

        # For real-time, pivots are typically based on the previous day's data.
        # If `daily_df` represents daily data, we might just return it directly for use.
        # Let's assume `daily_df` is suitable for direct use, and the `window` parameter
        # implies how many days of history were used to derive `daily_df` itself.
        # If the intent is to calculate pivots dynamically based on a rolling window of `daily_df`,
        # that requires more complex application.

        # Let's just return the calculated pivots for each day in `daily_df` for now.
        # The `window` parameter might be more relevant if `daily_df` itself was a rolling window.
        return pivot_df

    except Exception as e:
        logger.warning(
            f"Error calculating Fibonacci Pivot Points (Window={window}): {e}",
            exc_info=True,
        )
        return pd.DataFrame()


def calculate_volatility_index(
    high: pd.Series, low: pd.Series, period: int,
) -> pd.Series:
    """Calculates a simple Volatility Index (e.g., based on Average Range)."""
    if period <= 0:
        return pd.Series(np.nan, index=high.index)
    try:
        # Using ATR as a proxy for volatility
        volatility = calculate_atr(
            high, low, high, period=period,
        )  # Using high for close placeholder in ATR
        return volatility
    except Exception as e:
        logger.warning(
            f"Error calculating Volatility Index ({period}): {e}", exc_info=True,
        )
        return pd.Series(np.nan, index=high.index)


def detect_market_structure(
    high: pd.Series, low: pd.Series, lookback: int,
) -> pd.Series:
    """Detects Market Structure points (HH, HL, LH, LL) - simplified logic."""
    if lookback <= 0:
        return pd.Series(np.nan, index=high.index)
    try:
        structure = pd.Series(np.nan, index=high.index)
        # Simplified logic: A high is higher than previous highs, low is higher than previous lows etc.
        # This requires comparing current pivot points to prior ones over the lookback window.
        # A proper implementation involves finding pivot points first.

        # Placeholder: returns NaN, needs significant implementation.
        logger.warning(
            "Market Structure detection is a placeholder. Requires pivot point identification.",
        )
        return structure
    except Exception as e:
        logger.warning(
            f"Error detecting Market Structure (Lookback={lookback}): {e}",
            exc_info=True,
        )
        return pd.Series(np.nan, index=high.index)


def detect_candlestick_patterns(df: pd.DataFrame) -> pd.Series:
    """Detects common candlestick patterns - Placeholder function."""
    # This would involve analyzing Open, High, Low, Close relationships for specific patterns.
    # e.g., Doji, Engulfing, Hammer, etc.
    # Requires significant pattern recognition logic.
    logger.warning(
        "Candlestick pattern detection is a placeholder. Requires specific pattern recognition logic.",
    )
    return pd.Series(np.nan, index=df.index)


def calculate_roc(close: pd.Series, period: int) -> pd.Series:
    """Calculates Rate of Change."""
    if period <= 0:
        return pd.Series(np.nan, index=close.index)
    try:
        roc = ((close - close.shift(period)) / close.shift(period)) * 100
        return roc
    except Exception as e:
        logger.warning(f"Error calculating ROC({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=close.index)


# --- Main Trading Loop and Bot Logic ---


def main_trading_loop():
    """The heart of the WhaleBot: orchestrates data fetching, analysis, and trading decisions."""
    if not bybit_client:
        logger.critical("BybitHelper not initialized. Cannot start trading loop.")
        sys.exit(1)

    logger.info(
        f"{Fore.GREEN + Style.BRIGHT}--- Starting Main Trading Loop ---{Style.RESET_ALL}",
    )
    logger.info(
        f"Symbol: {config.symbol}, Timeframe: {config.interval}, Loop Delay: {config.loop_delay}s",
    )

    # --- WebSocket Subscription ---
    # Define the topics to subscribe to via WebSocket
    # Use simple symbol format from config
    main_ws_topics = [
        f"kline.{bybit_client._map_timeframe_to_pybit(config.interval)}.{config.symbol}",  # Kline data for main timeframe
        # Add other relevant topics like order book updates, account updates etc. if needed
        # f"position.{config.symbol}", # Position updates
        # f"account.{config.account_type}", # Account updates
        # f"execution.{config.symbol}", # Trade execution updates
    ]

    # --- WebSocket Message Handler ---
    # This function will be called by BybitHelper for every incoming message on subscribed topics.
    def handle_ws_message(message: dict[str, Any]):
        """Processes incoming WebSocket messages, updating indicators and triggering actions."""
        if message.get("topic", "").startswith("kline"):
            # Process Kline data update
            processed_row_df = bybit_client.update_ohlcv_cache(message)
            if processed_row_df is not None and not processed_row_df.empty:
                # A new/updated candle with indicators is available.
                # This is where signal generation and trading logic would be triggered.
                latest_candle_data = processed_row_df.iloc[
                    0
                ].to_dict()  # Get the single row as a dict
                # Trigger strategy evaluation with the latest candle data
                evaluate_strategy_signals(latest_candle_data)
        elif message.get("topic", "").startswith("position"):
            # Handle position updates from WebSocket (if subscribed)
            # Update internal position state or trigger related logic
            pass  # Placeholder for position update handling
        elif message.get("topic", "").startswith("account"):
            # Handle account updates from WebSocket
            pass  # Placeholder for account update handling
        elif message.get("topic", "").startswith("execution"):
            # Handle trade execution updates
            pass  # Placeholder for execution update handling
        # else: logger.debug(f"Received WS message for topic: {message.get('topic')}")

    # --- WebSocket Error Handler ---
    def handle_ws_error(error: Exception):
        """Logs WebSocket errors and triggers reconnection."""
        # BybitHelper's internal handlers already log and schedule reconnects.
        # This callback could be used for additional alerting or state management.
        logger.error(f"External WS Error Handler: {error}", exc_info=True)
        # Potentially send an SMS alert here if WS errors are critical.
        # bybit_client.send_sms(f"CRITICAL: Bybit WS Error on {config.symbol}!")

    # --- WebSocket Open Handler ---
    def handle_ws_open():
        """Called when the WebSocket connection is successfully established."""
        logger.info("WebSocket is now open and ready.")
        # Any actions needed upon successful connection (e.g., re-subscribe if needed)
        # Note: `connect_websocket` already handles initial subscriptions.

    # --- WebSocket Close Handler ---
    def handle_ws_close(close_status_code: int | None, close_msg: str | None):
        """Called when the WebSocket connection is closed."""
        logger.warning(
            f"WebSocket connection closed. Status: {close_status_code}, Message: {close_msg}",
        )
        # BybitHelper handles reconnection scheduling internally.

    # --- Connect to WebSocket ---
    # Start the WebSocket connection in the background.
    # It will automatically attempt to subscribe to the defined topics.
    if config.execution.use_websocket:
        logger.info(f"{Fore.CYAN}# Initiating WebSocket connection...{Style.RESET_ALL}")
        try:
            bybit_client.connect_websocket(
                topics=main_ws_topics,
                message_callback=handle_ws_message,
                error_callback=handle_ws_error,
                open_callback=handle_ws_open,
                close_callback=handle_ws_close,
            )
            # Give it a moment to establish connection before the main loop starts polling
            time.sleep(2)
        except Exception:
            logger.exception("Failed to initiate WebSocket connection.")

    # --- Main Loop ---
    trade_cooldown_until = 0.0  # Timestamp until which trading is on cooldown

    while True:
        current_time = time.time()
        try:
            # --- Diagnostics Check (Optional, based on config) ---
            # Run diagnostics periodically or on startup
            if not hasattr(main_trading_loop, "_diagnostics_ran") or (
                current_time - getattr(main_trading_loop, "_last_diag_time", 0)
                > config.core_settings.loop_delay * 5
                and not config.dry_run
            ):  # Run every 5 loops if not dry run
                logger.info(
                    f"{Fore.CYAN}# Running periodic diagnostics...{Style.RESET_ALL}",
                )
                diag_success = bybit_client.diagnose()
                main_trading_loop._diagnostics_ran = True
                main_trading_loop._last_diag_time = current_time
                if not diag_success:
                    logger.critical(
                        f"{Back.RED}{Fore.WHITE}Essential diagnostics failed. Halting trading operations until resolved.{Style.RESET_ALL}",
                    )
                    # Consider disabling trading or taking specific actions here.
                    # For now, we'll just log and continue, but in a real scenario, this could be critical.
                    # sys.exit(1) # Uncomment to halt on critical diagnostic failure

            # --- Fetch OHLCV Data and Indicators ---
            # Get the latest OHLCV data with indicators. This also ensures cache is updated.
            # Pass `include_daily_pivots=True` if strategy depends on them.
            ohlcv_df = bybit_client.get_or_fetch_ohlcv(
                timeframe=config.interval,
                limit=config.initial_candle_history,  # Fetch enough history for indicators
                include_daily_pivots=(
                    config.analysis_modules.mtf_analysis.enabled
                    or config.indicators.fibonacci_pivot_points
                ),
            )

            if ohlcv_df is None or ohlcv_df.empty:
                logger.warning(
                    f"No OHLCV data available for {config.symbol} {config.interval}. Skipping this loop iteration.",
                )
                time.sleep(config.loop_delay)
                continue

            # Get the most recent candle's data for analysis
            latest_candle = ohlcv_df.iloc[-1].to_dict()

            # --- Strategy Evaluation ---
            # This function determines if trading signals are generated based on indicators and strategy rules.
            evaluate_strategy_signals(latest_candle)

            # --- Cooldown and Risk Management Checks ---
            # Check if trading is currently on cooldown
            if current_time < trade_cooldown_until:
                logger.debug(
                    f"Trading cooldown active. Skipping trade execution until {datetime.fromtimestamp(trade_cooldown_until).strftime('%Y-%m-%d %H:%M:%S')}.",
                )
                # Continue to next iteration to fetch new data, but skip trade logic.
            else:
                # Check risk management parameters (e.g., max drawdown, consecutive losses)
                risk_limit_hit = check_risk_limits()
                if risk_limit_hit:
                    logger.error(
                        f"{Back.RED}{Fore.WHITE}Risk limit hit! Halting trading operations.{Style.RESET_ALL}",
                    )
                    # Implement kill switch logic here (e.g., cancel all orders, disable trading)
                    # Set a long cooldown period to prevent further trading
                    trade_cooldown_until = (
                        current_time
                        + config.risk_management.cooldown_after_kill_min * 60
                    )
                    bybit_client.cancel_all_orders(
                        symbol=config.symbol,
                    )  # Cancel all open orders
                    # Optionally send critical SMS alert
                    bybit_client.send_sms(
                        f"CRITICAL: RISK LIMIT HIT on {config.symbol}! Trading halted.",
                    )
                    # Continue loop to monitor, but trading actions are disabled.
                else:
                    # --- Execute Trades based on Signals ---
                    # This part would involve trade execution logic based on signals generated by `evaluate_strategy_signals`
                    # and considering current positions and risk parameters.
                    # For demonstration, this part is left as a placeholder.

                    # Example: If a bullish signal is detected and we have no open position, consider entering long.
                    # if latest_candle.get('Signal_Bullish') and bybit_client.get_open_positions(config.symbol) is None:
                    #     enter_long_position()
                    # elif latest_candle.get('Signal_Bearish') and bybit_client.get_open_positions(config.symbol) is None:
                    #     enter_short_position()
                    # elif bybit_client.get_open_positions(config.symbol) is not None:
                    #     manage_existing_position()
                    pass  # Placeholder for trade execution logic

            # --- Sleep for the configured delay ---
            time.sleep(config.loop_delay)

        except KeyboardInterrupt:
            logger.info(
                f"{Fore.YELLOW}KeyboardInterrupt received. Shutting down gracefully...{Style.RESET_ALL}",
            )
            break  # Exit the loop on Ctrl+C
        except Exception as e:
            # Catch any unexpected errors in the main loop to prevent crashes
            logger.exception(f"Unhandled exception in main trading loop: {e}")
            # Optionally send an alert for critical loop errors
            # bybit_client.send_sms(f"CRITICAL: UNHANDLED EXCEPTION in WhaleBot main loop on {config.symbol}!")
            # Implement a short delay before retrying to avoid rapid error loops
            time.sleep(5)

    # --- Cleanup on Exit ---
    logger.info(
        f"{Fore.GREEN + Style.BRIGHT}--- Trading Loop Terminated ---{Style.RESET_ALL}",
    )
    if config.execution.use_websocket and bybit_client:
        logger.info("Disconnecting WebSocket...")
        bybit_client.disconnect_websocket()  # Gracefully close WS connection

    logger.info("Performing final order cleanup...")
    if bybit_client:
        # Cancel any remaining open orders before exiting
        cleanup_success = bybit_client.cancel_all_orders(symbol=config.symbol)
        if cleanup_success:
            logger.info(
                "All open orders successfully cancelled or confirmed as non-existent.",
            )
        else:
            logger.warning(
                "Failed to cancel all orders during cleanup. Manual intervention may be required.",
            )

    logger.info(
        "WhaleBot has ceased its operations. May your trades be ever in your favor.",
    )
    sys.exit(0)


# --- Strategy Signal Evaluation ---
# This is a critical function that needs to be implemented based on your trading strategy.
# It takes the latest candle data (with indicators) and returns signals (e.g., BUY, SELL, HOLD).


def evaluate_strategy_signals(latest_candle_data: dict[str, Any]) -> None:
    """Evaluates the latest candle data against the configured strategy rules
    to generate trading signals (BUY, SELL, HOLD).
    This is a placeholder and requires a detailed strategy implementation.
    """
    if not latest_candle_data:
        logger.warning("No candle data provided for signal evaluation.")
        return

    # Access configuration for strategy parameters
    current_profile_name = config.strategy_management.current_strategy_profile
    strategy_profile = config.strategy_management.strategy_profiles.get(
        current_profile_name,
    )

    if not strategy_profile:
        logger.error(
            f"Strategy profile '{current_profile_name}' not found. Cannot evaluate signals.",
        )
        return

    # Enable/disable indicators based on the active profile
    indicators_to_use = strategy_profile.indicators_enabled
    weights = strategy_profile.weights

    # --- Signal Generation Logic ---
    # This logic needs to be implemented based on your specific trading strategy.
    # Example: Combine signals from multiple indicators with assigned weights.

    signal_score = 0.0
    buy_signals_count = 0
    sell_signals_count = 0
    total_weight_considered = 0.0

    logger.debug(f"Evaluating strategy signals using profile: '{current_profile_name}'")

    # --- Example Signal Calculation (Illustrative) ---
    # This section demonstrates how you might combine signals.
    # You'll need to define specific conditions for each indicator's bullish/bearish signal.

    # 1. EMA Alignment
    if indicators_to_use.get("ema_alignment", False):
        bullish_ema = latest_candle_data.get("EMA_Alignment_Bullish", False)
        bearish_ema = latest_candle_data.get("EMA_Alignment_Bearish", False)
        weight = weights.get("ema_alignment", 0.0)
        if bullish_ema:
            signal_score += weight
            buy_signals_count += 1
        if bearish_ema:
            signal_score -= weight
            sell_signals_count += 1
        total_weight_considered += weight

    # 2. SMA Trend Filter
    if indicators_to_use.get("sma_trend_filter", False):
        bullish_sma = latest_candle_data.get("SMA_Trend_Bullish", False)
        bearish_sma = latest_candle_data.get("SMA_Trend_Bearish", False)
        weight = weights.get("sma_trend_filter", 0.0)
        if bullish_sma:
            signal_score += weight
            buy_signals_count += 1
        if bearish_sma:
            signal_score -= weight
            sell_signals_count += 1
        total_weight_considered += weight

    # 3. RSI Momentum
    if indicators_to_use.get(
        "momentum_rsi_stoch_cci_wr_mfi", False,
    ):  # Grouping multiple momentum indicators
        # RSI Signals
        rsi_bullish = latest_candle_data.get("RSI_Bullish_Signal", False)
        rsi_bearish = latest_candle_data.get("RSI_Bearish_Signal", False)
        # StochRSI Signals
        stochrsi_bullish = latest_candle_data.get("StochRSI_Bullish_Signal", False)
        stochrsi_bearish = latest_candle_data.get("StochRSI_Bearish_Signal", False)
        # CCI Signals
        cci_bullish = latest_candle_data.get("CCI_Bullish_Signal", False)
        cci_bearish = latest_candle_data.get("CCI_Bearish_Signal", False)
        # Williams R Signals
        wr_bullish = latest_candle_data.get("Williams_R_Bullish_Signal", False)
        wr_bearish = latest_candle_data.get("Williams_R_Bearish_Signal", False)

        # Aggregate signals from this group
        momentum_bullish_count = sum(
            [rsi_bullish, stochrsi_bullish, cci_bullish, wr_bullish],
        )
        momentum_bearish_count = sum(
            [rsi_bearish, stochrsi_bearish, cci_bearish, wr_bearish],
        )

        # Example weighting logic: assign weight to overall momentum group
        group_weight = (
            weights.get("momentum_rsi_stoch_cci_wr_mfi", 0.0) / 4.0
        )  # Distribute weight if needed per indicator

        if momentum_bullish_count > 0:
            signal_score += group_weight * momentum_bullish_count
            buy_signals_count += momentum_bullish_count
        if momentum_bearish_count > 0:
            signal_score -= group_weight * momentum_bearish_count
            sell_signals_count += momentum_bearish_count
        total_weight_considered += weights.get("momentum_rsi_stoch_cci_wr_mfi", 0.0)

    # 4. Bollinger Bands / Keltner Channels
    if indicators_to_use.get("bollinger_bands", False):
        touches_upper_bb = latest_candle_data.get("Price_Touches_Upper_BB", False)
        touches_lower_bb = latest_candle_data.get("Price_Touches_Lower_BB", False)
        weight = weights.get("bollinger_bands", 0.0)
        if (
            touches_upper_bb
        ):  # Price broke above upper band (potential resistance/overbought)
            signal_score -= weight * 0.5  # Slight bearish signal
            sell_signals_count += 0.5
        if (
            touches_lower_bb
        ):  # Price broke below lower band (potential support/oversold)
            signal_score += weight * 0.5  # Slight bullish signal
            buy_signals_count += 0.5
        total_weight_considered += weight

    if indicators_to_use.get(
        "keltner_channels", False,
    ):  # Similar logic for Keltner Channels
        touches_upper_kc = latest_candle_data.get("Price_Touches_Upper_KC", False)
        touches_lower_kc = latest_candle_data.get("Price_Touches_Lower_KC", False)
        weight = weights.get("keltner_channels", 0.0)
        if touches_upper_kc:
            signal_score -= weight * 0.5
            sell_signals_count += 0.5
        if touches_lower_kc:
            signal_score += weight * 0.5
            buy_signals_count += 0.5
        total_weight_considered += weight

    # 5. Ehlers SuperTrend
    if indicators_to_use.get("ehlers_supertrend_alignment", False):
        bullish_flip = latest_candle_data.get("Ehlers_Bullish_Flip", False)
        bearish_flip = latest_candle_data.get("Ehlers_Bearish_Flip", False)
        weight = weights.get("ehlers_supertrend_alignment", 0.0)
        if bullish_flip:
            signal_score += weight
            buy_signals_count += 1
        if bearish_flip:
            signal_score -= weight
            sell_signals_count += 1
        total_weight_considered += weight

    # 6. Fibonacci Pivots (Example: Price crossing R1/S1)
    if indicators_to_use.get("fibonacci_pivot_points_confluence", False):
        crossed_r1 = latest_candle_data.get("Price_Crossed_R1", False)
        crossed_s1 = latest_candle_data.get("Price_Crossed_S1", False)
        weight = weights.get("fibonacci_pivot_points_confluence", 0.0)
        if crossed_r1:  # Breaking resistance might be bullish signal
            signal_score += weight * 0.3
            buy_signals_count += 0.3
        if crossed_s1:  # Breaking support might be bearish signal
            signal_score -= weight * 0.3
            sell_signals_count += 0.3
        total_weight_considered += weight

    # --- Normalize Signal Score ---
    # Normalize score based on total weight considered to get a relative strength
    # This helps in comparing strategies with different weighting schemes.
    normalized_score = 0.0
    if total_weight_considered > 0:
        normalized_score = signal_score / total_weight_considered
    else:
        logger.warning("No indicator weights considered for signal scoring.")

    # --- Determine Final Signal ---
    final_signal = "HOLD"
    threshold = config.core_settings.signal_score_threshold
    hysteresis = config.core_settings.hysteresis_ratio
    cooldown_duration = config.core_settings.cooldown_sec

    if normalized_score >= threshold:
        final_signal = "BUY"
        # Apply hysteresis to prevent rapid entries/exits if score is close to threshold
        if (
            latest_candle_data.get("Signal_Prev") == "BUY"
            and normalized_score < threshold * hysteresis
        ):
            final_signal = "HOLD"  # Maintain position if score dips slightly but stays above hysteresis
        elif (
            latest_candle_data.get("Signal_Prev") == "SELL" and normalized_score > 0
        ):  # If switching from sell, require some positive score
            pass  # Allow transition
    elif normalized_score <= -threshold:
        final_signal = "SELL"
        if (
            latest_candle_data.get("Signal_Prev") == "SELL"
            and normalized_score > -threshold * hysteresis
        ):
            final_signal = "HOLD"  # Maintain position if score rises slightly but stays below -threshold
        elif (
            latest_candle_data.get("Signal_Prev") == "BUY" and normalized_score < 0
        ):  # If switching from buy, require some negative score
            pass  # Allow transition

    # Update previous signal for hysteresis logic
    latest_candle_data["Signal_Prev"] = final_signal
    latest_candle_data["Signal_Score"] = normalized_score

    # Log the generated signal and score
    signal_color = (
        Fore.GREEN
        if final_signal == "BUY"
        else Fore.RED
        if final_signal == "SELL"
        else Fore.WHITE
    )
    logger.info(
        f"Signal Evaluation: Score={normalized_score:.4f} ({final_signal}) | Buy={buy_signals_count}, Sell={sell_signals_count}",
    )

    # --- Trigger Actions Based on Signal ---
    if final_signal == "BUY":
        # Enter Long Position Logic
        pass  # Placeholder: call function to enter long position
    elif final_signal == "SELL":
        # Enter Short Position Logic
        pass  # Placeholder: call function to enter short position

    # --- Manage Existing Positions (if applicable) ---
    # This would involve checking current positions and deciding on exits, stops, etc.
    # based on signals or other criteria.
    # manage_positions(latest_candle_data)


# --- Risk Management Checks ---


def check_risk_limits() -> bool:
    """Checks if any risk management limits have been breached.
    Returns True if a limit is hit (indicating a kill switch event), False otherwise.
    """
    if not config.risk_management.enabled:
        return False

    # Placeholder: Implement checks for max daily loss, max drawdown, etc.
    # These would typically involve tracking PnL and position values.

    # Example: Check for maximum consecutive losses
    # This requires tracking trade results (wins/losses) which is not yet implemented here.
    # You'd need a mechanism to store and count consecutive losses.

    # Example: Check for acceptable spread or slippage (requires real-time quote data)
    # This check might be more relevant during order placement.

    # If any critical risk limit is breached, return True to activate kill switch.
    return False  # Default to no risk limit hit


# --- Trade Execution Logic ---
# These functions would handle the actual placing, managing, and closing of trades.


def enter_long_position(candle_data: dict[str, Any]):
    """Logic to enter a long position based on BUY signal."""
    logger.info(f"{Fore.GREEN}Executing BUY signal...{Style.RESET_ALL}")
    # Fetch necessary data (balance, position)
    available_balance = bybit_client.fetch_balance(coin="USDT")
    current_position = bybit_client.get_open_positions(symbol=config.symbol)

    if available_balance is None:
        logger.error("Cannot enter long: Failed to fetch account balance.")
        return

    # Determine position size based on risk settings and available balance
    # Example: Risk X% of balance per trade
    risk_pct = config.risk_management.max_day_loss_pct / 100.0  # Example risk %
    trade_size_usd = available_balance * risk_pct
    entry_price = candle_data.get("close")  # Use current close price for entry

    if entry_price is None or entry_price <= Decimal("0"):
        logger.error("Cannot enter long: Invalid entry price from candle data.")
        return

    # Calculate quantity based on trade size and entry price
    quantity_usd = trade_size_usd / entry_price
    formatted_qty = bybit_client.format_quantity(quantity_usd)

    if Decimal(formatted_qty) <= Decimal("0"):
        logger.warning(
            f"Calculated quantity is zero or negative ({formatted_qty}). Cannot enter long.",
        )
        return

    # Determine Stop Loss (SL) and Take Profit (TP) targets
    # Use strategy configuration (e.g., ATR multiples)
    atr_value = candle_data.get("ATR")
    sl_price = None
    tp_targets = []

    if atr_value and config.execution.sl_scheme.type == "atr_multiple":
        sl_multiple = config.execution.sl_scheme.atr_multiple
        sl_price = entry_price - (
            atr_value * sl_multiple
        )  # For long, SL is below entry

    if atr_value and config.execution.tp_scheme.mode == "atr_multiples":
        for tp_target in config.execution.tp_scheme.targets:
            tp_multiple = tp_target.get("atr_multiple", 1.0)
            tp_price = entry_price + (
                atr_value * tp_multiple
            )  # For long, TP is above entry
            tp_targets.append(
                {"price": tp_price, "size_pct": tp_target.get("size_pct", 0.4)},
            )  # Store TP price and size

    # Place the entry order (Market or Limit)
    order_result = bybit_client.place_order(
        side="Buy",
        qty=Decimal(formatted_qty),
        order_type="Limit",  # Example: Place a limit order
        price=entry_price,  # Use the entry price
        sl=sl_price,  # Pass calculated stop loss
        tp=tp_targets[0]["price"]
        if tp_targets
        else None,  # Example: Use first TP target
        reduce_only=False,  # Not reducing a position here
        time_in_force=config.execution.default_time_in_force,
        # Add other parameters like position_idx if needed
    )

    if order_result:
        logger.success(
            f"Successfully entered long position for {formatted_qty} {config.symbol}.",
        )
        # Handle TP/SL orders if they are not placed automatically with the entry
        # For Bybit v5, TP/SL can often be set directly with the order.
        # If separate TP/SL orders are needed, call cancel_order and place_order again.
    else:
        logger.error("Failed to enter long position.")


def enter_short_position(candle_data: dict[str, Any]):
    """Logic to enter a short position based on SELL signal."""
    logger.info(f"{Fore.RED}Executing SELL signal...{Style.RESET_ALL}")
    # Similar logic to enter_long_position, but reversed for short entry.
    # Fetch balance, check current position.
    available_balance = bybit_client.fetch_balance(coin="USDT")
    current_position = bybit_client.get_open_positions(symbol=config.symbol)

    if available_balance is None:
        logger.error("Cannot enter short: Failed to fetch account balance.")
        return

    # Determine position size and price
    risk_pct = config.risk_management.max_day_loss_pct / 100.0
    trade_size_usd = available_balance * risk_pct
    entry_price = candle_data.get("close")

    if entry_price is None or entry_price <= Decimal("0"):
        logger.error("Cannot enter short: Invalid entry price from candle data.")
        return

    quantity_usd = trade_size_usd / entry_price
    formatted_qty = bybit_client.format_quantity(quantity_usd)

    if Decimal(formatted_qty) <= Decimal("0"):
        logger.warning(
            f"Calculated quantity is zero or negative ({formatted_qty}). Cannot enter short.",
        )
        return

    # Determine SL/TP
    atr_value = candle_data.get("ATR")
    sl_price = None
    tp_targets = []

    if atr_value and config.execution.sl_scheme.type == "atr_multiple":
        sl_multiple = config.execution.sl_scheme.atr_multiple
        sl_price = entry_price + (
            atr_value * sl_multiple
        )  # For short, SL is above entry

    if atr_value and config.execution.tp_scheme.mode == "atr_multiples":
        for tp_target in config.execution.tp_scheme.targets:
            tp_multiple = tp_target.get("atr_multiple", 1.0)
            tp_price = entry_price - (
                atr_value * tp_multiple
            )  # For short, TP is below entry
            tp_targets.append(
                {"price": tp_price, "size_pct": tp_target.get("size_pct", 0.4)},
            )

    # Place the entry order
    order_result = bybit_client.place_order(
        side="Sell",
        qty=Decimal(formatted_qty),
        order_type="Limit",  # Example: Place a limit order
        price=entry_price,
        sl=sl_price,
        tp=tp_targets[0]["price"] if tp_targets else None,
        reduce_only=False,
        time_in_force=config.execution.default_time_in_force,
    )

    if order_result:
        logger.success(
            f"Successfully entered short position for {formatted_qty} {config.symbol}.",
        )
    else:
        logger.error("Failed to enter short position.")


def manage_positions(candle_data: dict[str, Any]):
    """Manages open positions based on signals, SL/TP, or other conditions."""
    open_positions = bybit_client.get_open_positions(symbol=config.symbol)
    if not open_positions:
        # No open positions to manage.
        return

    # Assuming only one position is managed at a time for simplicity
    position = open_positions[0]
    current_side = position.get("side")
    current_size = position.get("size")
    entry_price = position.get("entry_price")
    current_mark_price = position.get("mark_price")
    unrealized_pnl = position.get("unrealized_pnl")
    stop_loss = position.get("stop_loss")
    take_profit = position.get("take_profit")

    # --- Logic for managing existing positions ---
    # Example: Trailing Stop Loss based on ATR (if enabled in config)
    atr_value = candle_data.get("ATR")
    if (
        config.execution.sl_scheme.get("trail_stop", {}).get("enabled", False)
        and atr_value
    ):
        trail_atr_multiple = config.execution.sl_scheme["trail_stop"].get(
            "trail_atr_multiple", 0.5,
        )
        activation_threshold = config.execution.sl_scheme["trail_stop"].get(
            "activation_threshold", 0.8,
        )  # Profit threshold to activate trailing stop

        current_profit_pct = 0.0
        if entry_price and current_mark_price:
            if current_side == "Buy" and entry_price > 0:
                current_profit_pct = (
                    (current_mark_price - entry_price) / entry_price
                ) * 100
            elif current_side == "Sell" and entry_price > 0:
                current_profit_pct = (
                    (entry_price - current_mark_price) / entry_price
                ) * 100

        # Check if activation threshold is met and trailing stop is needed
        if current_profit_pct >= activation_threshold:
            # Calculate potential new stop loss based on ATR trailing
            atr_trail_stop_value = atr_value * trail_atr_multiple
            new_stop_loss = None

            if current_side == "Buy":
                # For long positions, trailing stop moves up with price
                potential_sl = (
                    entry_price - atr_trail_value
                )  # Assuming entry price is the base
                if potential_sl > stop_loss:  # Only update if it's higher (moves up)
                    new_stop_loss = potential_sl
            elif current_side == "Sell":
                # For short positions, trailing stop moves down with price
                potential_sl = entry_price + atr_trail_value
                if potential_sl < stop_loss:  # Only update if it's lower (moves down)
                    new_stop_loss = potential_sl

            # If a valid new stop loss was calculated and it's better than current SL
            if (
                new_stop_loss
                and stop_loss
                and (
                    (current_side == "Buy" and new_stop_loss > stop_loss)
                    or (current_side == "Sell" and new_stop_loss < stop_loss)
                )
            ):
                logger.info(
                    f"Trailing stop loss needs update for {config.symbol}. New SL: {new_stop_loss}",
                )
                # Call function to update the stop loss order
                # update_stop_loss_order(position['orderId'], new_stop_loss) # Example function call

    # --- Breakeven Logic ---
    # Check if breakeven should be activated (e.g., after TP1 hit)
    # This would require tracking TP hits and adjusting SL to entry price.

    # --- Exit Logic ---
    # Check for exit signals (e.g., opposite signal, indicator divergence, etc.)
    # or if position size needs reduction based on profit targets.

    # Placeholder for position management logic


# --- Entry Point of the Script ---


def parse_arguments():
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(
        description="WhaleBot: A Trading Automaton for Bybit.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=str(CONFIG_FILE_PATH),
        help="Path to the configuration JSON file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (simulate trades, do not execute orders).",
    )
    parser.add_argument(
        "--testnet", action="store_true", help="Use Bybit testnet environment.",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default=None,
        help="Override default symbol from config (e.g., BTCUSDT).",
    )
    parser.add_argument(
        "--interval",
        type=str,
        default=None,
        help="Override default interval from config (e.g., 15m).",
    )
    parser.add_argument(
        "--loop-delay",
        type=int,
        default=None,
        help="Override default loop delay in seconds.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=None,
        help="Override log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).",
    )
    parser.add_argument(
        "--strategy-profile",
        type=str,
        default=None,
        help="Override the current strategy profile name.",
    )

    return parser.parse_args()


def initialize_bot(args):
    """Initializes the bot environment, loads config, and sets up clients."""
    # Load config from args, potentially overriding default path
    global CONFIG_FILE_PATH
    if args.config:
        CONFIG_FILE_PATH = Path(args.config)

    # Attempt to load configuration and setup global environment
    if not setup_global_environment():
        # Critical failure during setup, exit
        sys.exit(1)

    # Apply command-line argument overrides to the config
    global config, logger
    if args.dry_run is not None:
        config.execution.dry_run = args.dry_run
    if args.testnet is not None:
        config.execution.testnet = args.testnet
    if args.symbol:
        config.symbol = args.symbol
    if args.interval:
        config.interval = args.interval
    if args.loop_delay:
        config.loop_delay = args.loop_delay
    if args.log_level:
        # Update logger level and potentially console handler level
        log_level_str = args.log_level.upper()
        try:
            log_level = (
                SUCCESS_LEVEL
                if log_level_str == "SUCCESS"
                else getattr(logging, log_level_str)
            )
            logger.setLevel(log_level)
            # Update console handler level
            for handler in logger.handlers:
                if isinstance(handler, logging.StreamHandler):
                    handler.setLevel(log_level)
                    break
            config.logging.level = log_level_str  # Update config object as well
            logger.info(f"Log level overridden to: {log_level_str}")
        except AttributeError:
            logger.warning(
                f"Invalid log level '{args.log_level}' provided. Using current level: {config.logging.level}",
            )

    if args.strategy_profile:
        config.strategy_management.current_strategy_profile = args.strategy_profile
        logger.info(f"Strategy profile overridden to: '{args.strategy_profile}'")

    # Re-initialize BybitHelper with potentially updated config if critical params changed
    # (e.g., testnet mode). Note: This is a simplified approach; a full config reload might be needed.
    try:
        # Re-instantiate BybitHelper if key parameters like testnet changed.
        # For simplicity, assume BybitHelper's initial setup is sufficient unless testnet changes.
        if config.execution.testnet != bybit_client.config.execution.testnet:
            logger.info(
                f"Testnet mode changed to {config.execution.testnet}. Re-initializing BybitHelper...",
            )
            # Need to re-instantiate to apply testnet change correctly
            bybit_client = BybitHelper(config)
        else:
            # Update config in existing client if other params changed (less common, but for completeness)
            bybit_client.config = config

        logger.info(
            f"Bot Configuration: Symbol={config.symbol}, Interval={config.interval}, Testnet={config.execution.testnet}, DryRun={config.execution.dry_run}",
        )

        # Perform initial diagnostics upon successful initialization
        logger.info(f"{Fore.CYAN}# Running initial diagnostics...{Style.RESET_ALL}")
        initial_diag_success = bybit_client.diagnose()
        if not initial_diag_success:
            logger.critical(
                f"{Back.RED}{Fore.WHITE}Initial diagnostics FAILED. Bot may not function correctly. Review logs.{Style.RESET_ALL}",
            )
            # Decide whether to halt execution based on diagnostic outcome
            # For safety, we might want to exit if critical components fail initially.
            # sys.exit(1) # Uncomment to halt on critical initial failure.

        return True
    except Exception as e:
        logger.critical(
            f"FATAL: Error during bot initialization or post-config update: {e}",
            exc_info=True,
        )
        return False


if __name__ == "__main__":
    # Parse command-line arguments first
    parsed_args = parse_arguments()

    # Initialize the bot environment based on parsed arguments and config files
    if initialize_bot(parsed_args):
        # If initialization is successful, start the main trading loop
        main_trading_loop()
    else:
        # If initialization fails, exit with an error code
        logger.critical("Bot initialization failed. Exiting.")
        sys.exit(1)
