
import json
import logging
import os
import sys
import threading
import time
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal, InvalidOperation, getcontext
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, ClassVar, Literal

import numpy as np
import pandas as pd
import websocket

# --- Guarded Import for Pybit ---
try:
    import pybit.exceptions
    from pybit.unified_trading import HTTP as PybitHTTP
    PYBIT_AVAILABLE = True
except ImportError:
    PYBIT_AVAILABLE = False

from colorama import Fore, Style, init
from dotenv import load_dotenv

# --- Custom Modules ---
try:
    import indicators
except ImportError:
    logging.basicConfig(level=logging.ERROR)
    logger_mod_err = logging.getLogger(__name__)
    logger_mod_err.error("indicators.py not found. Please ensure it's in the same directory or accessible via PYTHONPATH.")
    sys.exit(1)

try:
    from alert_system import AlertSystem
except ImportError:
    logging.basicConfig(level=logging.ERROR)
    logger_mod_err = logging.getLogger(__name__)
    logger_mod_err.error("alert_system.py not found. Please ensure it's in the same directory or accessible via PYTHONPATH.")
    sys.exit(1)

# --- Initialization ---
getcontext().prec = 28  # Set Decimal precision globally
init(autoreset=True) # Initialize Colorama

# Load environment variables from .env file
script_dir = Path(__file__).resolve().parent
dotenv_path = script_dir / '.env'
load_dotenv(dotenv_path=dotenv_path)

# --- Constants ---
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
CONFIG_FILE = "config.json"
STATE_FILE = "bot_state.json"
LOG_DIRECTORY = "bot_logs/trading-bot/logs"
Path(LOG_DIRECTORY).mkdir(parents=True, exist_ok=True)

TIMEZONE = UTC
MAX_API_RETRIES = 5
RETRY_DELAY_SECONDS = 7
REQUEST_TIMEOUT = 20
LOOP_DELAY_SECONDS = 15
HEARTBEAT_INTERVAL_MS = 5000
EXECUTION_POLL_INTERVAL_MS = 2500

# Magic Numbers for Indicators & Logic
ADX_STRONG_TREND_THRESHOLD = 25
ADX_WEAK_TREND_THRESHOLD = 20
STOCH_RSI_MID_POINT = 50
MIN_CANDLESTICK_PATTERNS_BARS = 2

# Color Palette
NEON_GREEN, NEON_BLUE, NEON_PURPLE, NEON_YELLOW, NEON_RED, NEON_CYAN = Fore.LIGHTGREEN_EX, Fore.CYAN, Fore.MAGENTA, Fore.YELLOW, Fore.LIGHTRED_EX, Fore.CYAN
RESET = Style.RESET_ALL

# Indicator Colors (mapping for display)
INDICATOR_COLORS = {
    "SMA_10": NEON_BLUE, "SMA_Long": Fore.BLUE, "EMA_Short": NEON_PURPLE,
    "EMA_Long": Fore.MAGENTA, "ATR": NEON_YELLOW, "RSI": NEON_GREEN, "StochRSI_K": NEON_CYAN,
    "StochRSI_D": Fore.LIGHTCYAN_EX, "BB_Upper": NEON_RED, "BB_Middle": Fore.WHITE,
    "BB_Lower": NEON_RED, "CCI": NEON_GREEN, "WR": NEON_RED, "MFI": NEON_GREEN,
    "OBV": Fore.BLUE, "OBV_EMA": NEON_BLUE, "CMF": NEON_PURPLE, "Tenkan_Sen": NEON_CYAN,
    "Kijun_Sen": Fore.LIGHTCYAN_EX, "Senkou_Span_A": NEON_GREEN, "Senkou_Span_B": NEON_RED,
    "Chikou_Span": NEON_YELLOW, "PSAR_Val": NEON_PURPLE, "PSAR_Dir": Fore.LIGHTMAGENTA_EX,
    "VWAP": Fore.WHITE, "ST_Fast_Dir": Fore.BLUE, "ST_Fast_Val": NEON_BLUE,
    "ST_Slow_Dir": NEON_PURPLE, "ST_Slow_Val": Fore.LIGHTMAGENTA_EX, "MACD_Line": NEON_GREEN,
    "MACD_Signal": Fore.LIGHTGREEN_EX, "MACD_Hist": NEON_YELLOW, "ADX": NEON_CYAN,
    "PlusDI": Fore.LIGHTCYAN_EX, "MinusDI": NEON_RED, "Volatility_Index": NEON_YELLOW,
    "Volume_Delta": Fore.LIGHTCYAN_EX, "VWMA": Fore.WHITE, "Kaufman_AMA": NEON_GREEN,
    "Relative_Volume": NEON_PURPLE, "Market_Structure_Trend": Fore.LIGHTCYAN_EX,
    "DEMA": Fore.BLUE, "Keltner_Upper": NEON_PURPLE, "Keltner_Middle": Fore.WHITE,
    "Keltner_Lower": NEON_PURPLE, "ROC": NEON_GREEN, "Pivot": Fore.WHITE,
    "R1": NEON_CYAN, "R2": Fore.LIGHTCYAN_EX, "S1": NEON_PURPLE, "S2": Fore.LIGHTMAGENTA_EX,
    "Candlestick_Pattern": Fore.LIGHTYELLOW_EX, "Support_Level": NEON_CYAN,
    "Resistance_Level": NEON_RED,
}

# --- Global Logger Instance ---
global_logger = logging.getLogger("whalebot")

# --- Helper Functions for Precision and Safety ---
def round_qty(qty: Decimal, qty_step: Decimal) -> Decimal:
    if qty_step is None or qty_step.is_zero():
        return qty.quantize(Decimal("1e-6"), rounding=ROUND_DOWN)
    return (qty // qty_step) * qty_step

def round_price(price: Decimal, price_precision: int) -> Decimal:
    if price_precision < 0: price_precision = 0
    return price.quantize(Decimal(f"1e-{price_precision}"), rounding=ROUND_DOWN)

def _safe_divide_decimal(numerator: Decimal, denominator: Decimal, default: Decimal = Decimal("0")) -> Decimal:
    try:
        if denominator.is_zero() or denominator.is_nan() or numerator.is_nan():
            return default
        return numerator / denominator
    except InvalidOperation:
        return default

def _clean_series(series: pd.Series | None, df_index: pd.Index, default_val: Any = np.nan) -> pd.Series:
    if series is None:
        return pd.Series(default_val, index=df_index)
    cleaned = series.reindex(df_index)
    if not pd.isna(default_val):
        cleaned = cleaned.fillna(default_val)
    return cleaned

# --- Configuration Management ---
def load_config(filepath: str, logger: logging.Logger) -> dict[str, Any]:
    """Loads config from JSON, creates default if missing, ensures all keys exist."""
    default_config = {
        "symbol": "BTCUSDT", "interval": "15", "loop_delay": LOOP_DELAY_SECONDS,
        "orderbook_limit": 50, "signal_score_threshold": 2.0, "cooldown_sec": 60,
        "hysteresis_ratio": 0.85, "volume_confirmation_multiplier": 1.5,
        "trade_management": {
            "enabled": True, "account_balance": 1000.0, "risk_per_trade_percent": 1.0,
            "stop_loss_atr_multiple": 1.5, "take_profit_atr_multiple": 2.0,
            "max_open_positions": 1, "order_precision": 5, "price_precision": 3,
            "slippage_percent": 0.001, "trading_fee_percent": 0.0005,
        },
        "risk_guardrails": {
            "enabled": True, "max_day_loss_pct": 3.0, "max_drawdown_pct": 8.0,
            "cooldown_after_kill_min": 120, "spread_filter_bps": 5.0, "ev_filter_enabled": True,
        },
        "session_filter": {
            "enabled": False, "utc_allowed": [["00:00", "08:00"], ["13:00", "20:00"]],
        },
        "pyramiding": {
            "enabled": False, "max_adds": 2, "step_atr": 0.7, "size_pct_of_initial": 0.5,
        },
        "mtf_analysis": {
            "enabled": True, "higher_timeframes": ["60", "240"],
            "trend_indicators": ["ema", "ehlers_supertrend"], "trend_period": 50,
            "mtf_request_delay_seconds": 0.5,
        },
        "ml_enhancement": {"enabled": False},
        "indicator_settings": {
            "atr_period": 14, "ema_short_period": 9, "ema_long_period": 21, "rsi_period": 14,
            "stoch_rsi_period": 14, "stoch_k_period": 3, "stoch_d_period": 3,
            "bollinger_bands_period": 20, "bollinger_bands_std_dev": 2.0, "cci_period": 20,
            "williams_r_period": 14, "mfi_period": 14, "psar_acceleration": 0.02,
            "psar_max_acceleration": 0.2, "sma_short_period": 10, "sma_long_period": 50,
            "fibonacci_window": 60, "ehlers_fast_period": 10, "ehlers_fast_multiplier": 2.0,
            "ehlers_slow_period": 20, "ehlers_slow_multiplier": 3.0, "macd_fast_period": 12,
            "macd_slow_period": 26, "macd_signal_period": 9, "adx_period": 14,
            "ichimoku_tenkan_period": 9, "ichimoku_kijun_period": 26,
            "ichimoku_senkou_span_b_period": 52, "ichimoku_chikou_span_offset": 26,
            "obv_ema_period": 20, "cmf_period": 20, "rsi_oversold": 30, "rsi_overbought": 70,
            "stoch_rsi_oversold": 20, "stoch_rsi_overbought": 80, "cci_oversold": -100,
            "cci_overbought": 100, "williams_r_oversold": -80, "williams_r_overbought": -20,
            "mfi_oversold": 20, "mfi_overbought": 80, "volatility_index_period": 20,
            "vwma_period": 20, "volume_delta_period": 5, "volume_delta_threshold": 0.2,
            "kama_period": 10, "kama_fast_period": 2, "kama_slow_period": 30,
            "relative_volume_period": 20, "relative_volume_threshold": 1.5,
            "market_structure_lookback_period": 20, "dema_period": 14,
            "keltner_period": 20, "keltner_atr_multiplier": 2.0, "roc_period": 12,
            "roc_oversold": -5.0, "roc_overbought": 5.0,
        },
        "indicators": {
            "atr": True, "ema_alignment": True, "sma_trend_filter": True, "momentum": True,
            "volume_confirmation": True, "stoch_rsi": True, "rsi": True, "bollinger_bands": True,
            "vwap": True, "cci": True, "wr": True, "psar": True, "sma_10": True, "mfi": True,
            "orderbook_imbalance": True, "fibonacci_levels": True, "ehlers_supertrend": True,
            "macd": True, "adx": True, "ichimoku_cloud": True, "obv": True, "cmf": True,
            "volatility_index": True, "vwma": True, "volume_delta": True,
            "kaufman_ama": True, "relative_volume": True, "market_structure": True,
            "dema": True, "keltner_channels": True, "roc": True, "candlestick_patterns": True,
            "fibonacci_pivot_points": True,
        },
        "weight_sets": {
            "default_scalping": {
                "ema_alignment": 0.30, "sma_trend_filter": 0.20, "ehlers_supertrend_alignment": 0.40,
                "macd_alignment": 0.30, "adx_strength": 0.25, "ichimoku_confluence": 0.35,
                "psar": 0.15, "vwap": 0.15, "vwma_cross": 0.10, "sma_10": 0.05,
                "bollinger_bands": 0.25, "momentum_rsi_stoch_cci_wr_mfi": 0.35,
                "volume_confirmation": 0.10, "obv_momentum": 0.15, "cmf_flow": 0.10,
                "volume_delta_signal": 0.10, "orderbook_imbalance": 0.10,
                "mtf_trend_confluence": 0.25, "volatility_index_signal": 0.10,
                "kaufman_ama_cross": 0.20, "relative_volume_confirmation": 0.10,
                "market_structure_confluence": 0.25, "dema_crossover": 0.18,
                "keltner_breakout": 0.20, "roc_signal": 0.12, "candlestick_confirmation": 0.15,
                "fibonacci_pivot_points_confluence": 0.20,
            }
        },
        "execution": {
            "use_pybit": False, "testnet": False, "account_type": "UNIFIED", "category": "linear",
            "position_mode": "ONE_WAY", "tpsl_mode": "Partial", "buy_leverage": "3",
            "sell_leverage": "3", "tp_trigger_by": "LastPrice", "sl_trigger_by": "LastPrice",
            "default_time_in_force": "GoodTillCancel", "reduce_only_default": False,
            "post_only_default": False,
            "position_idx_overrides": {"ONE_WAY": 0, "HEDGE_BUY": 1, "HEDGE_SELL": 2},
            "proxies": {
                "enabled": False, "http": "", "https": ""
            },
            "tp_scheme": {
                "mode": "atr_multiples",
                "targets": [
                    {"name": "TP1", "atr_multiple": 1.0, "size_pct": 0.40, "order_type": "Limit", "tif": "PostOnly", "post_only": True},
                    {"name": "TP2", "atr_multiple": 1.5, "size_pct": 0.40, "order_type": "Limit", "tif": "IOC", "post_only": False},
                    {"name": "TP3", "atr_multiple": 2.0, "size_pct": 0.20, "order_type": "Limit", "tif": "GoodTillCancel", "post_only": False},
                ],
            },
            "sl_scheme": {
                "type": "atr_multiple", "atr_multiple": 1.5, "percent": 1.0,
                "use_conditional_stop": True, "stop_order_type": "Market",
            },
            "breakeven_after_tp1": {
                "enabled": True, "offset_type": "atr", "offset_value": 0.10,
                "lock_in_min_percent": 0, "sl_trigger_by": "LastPrice",
            },
            "live_sync": {
                "enabled": True, "poll_ms": 2500, "max_exec_fetch": 200,
                "only_track_linked": True, "heartbeat": {"enabled": True, "interval_ms": 5000},
            },
        },
    }
    if not Path(filepath).exists():
        try:
            with Path(filepath).open("w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)
            logger.warning(f"{NEON_YELLOW}Created default config at {filepath}{RESET}")
            return default_config
        except OSError as e:
            logger.error(f"{NEON_RED}Error creating default config file: {e}{RESET}")
            return default_config
    try:
        with Path(filepath).open(encoding="utf-8") as f:
            config = json.load(f)
        _ensure_config_keys(config, default_config)
        if not validate_config(config):
            logger.error(f"{NEON_RED}Configuration validation failed. Exiting.{RESET}")
            sys.exit(1)
        with Path(filepath).open("w", encoding="utf-8") as f_write:
            json.dump(config, f_write, indent=4)
        return config
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"{NEON_RED}Error loading config: {e}. Using default.{RESET}")
        return default_config

def _ensure_config_keys(config: dict[str, Any], default_config: dict[str, Any]) -> None:
    for key, default_value in default_config.items():
        if key not in config:
            config[key] = default_value
        elif isinstance(default_value, dict) and isinstance(config.get(key), dict):
            _ensure_config_keys(config[key], default_value)

def validate_config(config: dict) -> bool:
    """Validate configuration values."""
    required_sections = ['trade_management', 'indicator_settings', 'indicators']
    if not all(section in config for section in required_sections):
        return False
    
    risk_percent = config['trade_management']['risk_per_trade_percent']
    if risk_percent <= 0 or risk_percent > 100:
        return False
        
    return True

# --- Logging Setup ---
class SensitiveFormatter(logging.Formatter):
    SENSITIVE_WORDS: ClassVar[list[str]] = ["API_KEY", "API_SECRET"]
    def format(self, record):
        original_message = super().format(record)
        for word in self.SENSITIVE_WORDS:
            if word in original_message:
                original_message = original_message.replace(word, "*" * len(word))
        return original_message

def setup_logger(log_name: str, level=logging.INFO) -> logging.Logger:
    logger = logging.getLogger(log_name)
    if not logger.handlers:
        logger.setLevel(level)
        logger.propagate = False
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(SensitiveFormatter(f"{NEON_BLUE}%(asctime)s - %(levelname)s - %(message)s{RESET}"))
        logger.addHandler(console_handler)
        log_file = Path(LOG_DIRECTORY) / f"{log_name}.log"
        file_handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5)
        file_handler.setFormatter(SensitiveFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        logger.addHandler(file_handler)
    return logger

# --- Main Bot Logic ---
def main():
    global global_logger
    global_logger = setup_logger("wbextreme", logging.INFO)
    config = load_config(CONFIG_FILE, global_logger)
    
    global_logger.info("Starting wbextreme bot...")
    # The rest of the logic will be filled in subsequent steps.

if __name__ == "__main__":
    main()
