The following is a unified, enhanced, and debugged Python script, incorporating features and improvements from all the provided files (`alert_system.py`, `wblive.py`, `wbtemp.py`, `wblive1.0.0.py`, `wblive1.0.1.py`, `indicators.py`, `whalebot.py`).

**Key Improvements and Merges:**

1.  **Unified API Client:** Standardized on `pybit.unified_trading.HTTP` (the official Pybit library) for all API interactions, incorporating proxy support and a 403 Forbidden error handler from `wblive1.0.1.py`. The custom `requests`-based `BybitClient` from `whalebot.py` has been removed.
2.  **Centralized Indicator Logic:** All technical indicator calculations are now exclusively handled by the `indicators.py` module. The `TradingAnalyzer` class has been refactored to call these external functions, eliminating redundant internal implementations from `wbtemp.py` and `whalebot.py`.
3.  **Advanced `TradingAnalyzer`:**
    *   Adopted the modular signal scoring system (`_score_adx`, `_score_ema_alignment`, etc.) from `whalebot.py` for better readability, maintainability, and extensibility.
    *   Integrated all indicators (Kaufman AMA, Relative Volume, Market Structure, DEMA, Keltner Channels, ROC, Candlestick Patterns, Fibonacci Pivot Points) from `whalebot.py` and `wbtemp.py` into the main analysis pipeline, ensuring they utilize the `indicators.py` functions.
    *   Includes dynamic signal thresholds, hysteresis, and cooldown logic from `wblive1.0.1.py` for more robust signal generation.
    *   Enhanced MTF trend logic to use the `indicators._get_mtf_trend` helper.
4.  **Comprehensive `PositionManager`:** Merged advanced features from `wblive1.0.1.py` (live Pybit integration, dynamic precision updates from exchange, partial TP/SL schemes, conditional stops, pyramiding) with the simulation logic and slippage handling from `whalebot.py`.
5.  **Robust Live Trading Sync:** Included `ExchangeExecutionSync` and `PositionHeartbeat` classes from `wblive1.0.1.py` for real-time reconciliation of local position state with the exchange, crucial for live trading.
6.  **Detailed `PerformanceTracker`:** Used the more comprehensive `PerformanceTracker` from `wblive1.0.1.py` (which includes drawdown, profit factor, avg win/loss) and added fee deduction from `whalebot.py`.
7.  **Enhanced Logging & Display:** Utilized the detailed `display_indicator_values_and_price` function and concise trend summary from `whalebot.py` for richer console output.
8.  **Risk Management & Guardrails:** Incorporated risk guardrails (max daily loss, max drawdown, spread filter, EV filter) and session filtering from `wblive1.0.1.py`.
9.  **Configuration Management:** Consolidated to a single `load_config` and `_ensure_config_keys` implementation, ensuring all new and existing settings are properly loaded and default values are applied.
10. **Termux Integration:** Kept the `AlertSystem` with `termux-toast` functionality, ensuring its compatibility.
11. **Code Organization:** Maintained a modular structure where `indicators.py` and `alert_system.py` remain as separate, imported modules. The main bot logic is in a single file.

---

### `unified_whalebot.py` (Main Script)

```python
import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal, getcontext
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, ClassVar, Literal, Optional, Tuple

import numpy as np
import pandas as pd
# Guarded import for the live trading client
try:
    from pybit.unified_trading import HTTP as PybitHTTP
    import pybit.exceptions
    PYBIT_AVAILABLE = True
except ImportError:
    PYBIT_AVAILABLE = False

from colorama import Fore, Style, init
from dotenv import load_dotenv

# --- Custom Modules ---
# Ensure these are in the same directory or accessible via PYTHONPATH
import indicators  # Contains all technical indicator calculation functions
from alert_system import AlertSystem # For Termux toast notifications

# Initialize colorama and set decimal precision
getcontext().prec = 28
init(autoreset=True)

# Explicitly load .env values from the script's directory for robustness
script_dir = Path(__file__).resolve().parent
dotenv_path = script_dir / '.env'
load_dotenv(dotenv_path=dotenv_path)

# --- Constants ---
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
BASE_URL = os.getenv("BYBIT_BASE_URL", "https://api.bybit.com")
CONFIG_FILE = "config.json"
LOG_DIRECTORY = "bot_logs/trading-bot/logs"
Path(LOG_DIRECTORY).mkdir(parents=True, exist_ok=True)

TIMEZONE = timezone.utc
MAX_API_RETRIES = 5
RETRY_DELAY_SECONDS = 7
REQUEST_TIMEOUT = 20
LOOP_DELAY_SECONDS = 15

# Magic Numbers as Constants
ADX_STRONG_TREND_THRESHOLD = 25
ADX_WEAK_TREND_THRESHOLD = 20
STOCH_RSI_MID_POINT = 50
MIN_CANDLESTICK_PATTERNS_BARS = 2 # For pattern detection

# Neon Color Scheme
NEON_GREEN = Fore.LIGHTGREEN_EX
NEON_BLUE = Fore.CYAN
NEON_PURPLE = Fore.MAGENTA
NEON_YELLOW = Fore.YELLOW
NEON_RED = Fore.LIGHTRED_EX
NEON_CYAN = Fore.CYAN
RESET = Style.RESET_ALL

# Indicator specific colors
INDICATOR_COLORS = {
    "SMA_10": Fore.LIGHTBLUE_EX, "SMA_Long": Fore.BLUE, "EMA_Short": Fore.LIGHTMAGENTA_EX,
    "EMA_Long": Fore.MAGENTA, "ATR": Fore.YELLOW, "RSI": Fore.GREEN, "StochRSI_K": Fore.CYAN,
    "StochRSI_D": Fore.LIGHTCYAN_EX, "BB_Upper": Fore.RED, "BB_Middle": Fore.WHITE,
    "BB_Lower": Fore.RED, "CCI": Fore.LIGHTGREEN_EX, "WR": Fore.LIGHTRED_EX, "MFI": Fore.GREEN,
    "OBV": Fore.BLUE, "OBV_EMA": Fore.LIGHTBLUE_EX, "CMF": Fore.MAGENTA, "Tenkan_Sen": Fore.CYAN,
    "Kijun_Sen": Fore.LIGHTCYAN_EX, "Senkou_Span_A": Fore.GREEN, "Senkou_Span_B": Fore.RED,
    "Chikou_Span": Fore.YELLOW, "PSAR_Val": Fore.MAGENTA, "PSAR_Dir": Fore.LIGHTMAGENTA_EX,
    "VWAP": Fore.WHITE, "ST_Fast_Dir": Fore.BLUE, "ST_Fast_Val": Fore.LIGHTBLUE_EX,
    "ST_Slow_Dir": Fore.MAGENTA, "ST_Slow_Val": Fore.LIGHTMAGENTA_EX, "MACD_Line": Fore.GREEN,
    "MACD_Signal": Fore.LIGHTGREEN_EX, "MACD_Hist": Fore.YELLOW, "ADX": Fore.CYAN,
    "PlusDI": Fore.LIGHTCYAN_EX, "MinusDI": Fore.RED, "Volatility_Index": Fore.YELLOW,
    "Volume_Delta": Fore.LIGHTCYAN_EX, "VWMA": Fore.WHITE, "Kaufman_AMA": Fore.GREEN,
    "Relative_Volume": Fore.LIGHTMAGENTA_EX, "Market_Structure_Trend": Fore.LIGHTCYAN_EX,
    "DEMA": Fore.BLUE, "Keltner_Upper": Fore.LIGHTMAGENTA_EX, "Keltner_Middle": Fore.WHITE,
    "Keltner_Lower": Fore.MAGENTA, "ROC": Fore.LIGHTGREEN_EX, "Pivot": Fore.WHITE,
    "R1": Fore.CYAN, "R2": Fore.LIGHTCYAN_EX, "S1": Fore.MAGENTA, "S2": Fore.LIGHTMAGENTA_EX,
    "Candlestick_Pattern": Fore.LIGHTYELLOW_EX, "Support_Level": Fore.LIGHTCYAN_EX,
    "Resistance_Level": Fore.RED,
}


# --- Helper Functions for Precision ---
def round_qty(qty: Decimal, qty_step: Decimal) -> Decimal:
    """Rounds the quantity down to the nearest multiple of qty_step."""
    if qty_step is None or qty_step.is_zero():
        # Fallback for safety, though it should be set from exchange info.
        return qty.quantize(Decimal("1.000000"), rounding=ROUND_DOWN)
    return (qty // qty_step) * qty_step


def round_price(price: Decimal, price_precision: int) -> Decimal:
    """Rounds the price to the correct number of decimal places."""
    if price_precision < 0:
        price_precision = 0
    return price.quantize(Decimal(f"1e-{price_precision}"), rounding=ROUND_DOWN)


# --- Configuration Management ---
def load_config(filepath: str, logger: logging.Logger) -> dict[str, Any]:
    """Load configuration from JSON file, creating a default if not found."""
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
        "ml_enhancement": {"enabled": False}, # ML explicitly disabled as per history
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
            "ema_alignment": True, "sma_trend_filter": True, "momentum": True,
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
                "enabled": False,
                "http": "",
                "https": ""
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
        with Path(filepath).open("w", encoding="utf-8") as f_write:
            json.dump(config, f_write, indent=4)
        return config
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"{NEON_RED}Error loading config: {e}. Using default.{RESET}")
        return default_config


def _ensure_config_keys(config: dict[str, Any], default_config: dict[str, Any]) -> None:
    """Recursively ensure all keys from default_config are in config."""
    for key, default_value in default_config.items():
        if key not in config:
            config[key] = default_value
        elif isinstance(default_value, dict) and isinstance(config.get(key), dict):
            _ensure_config_keys(config[key], default_value)


# --- Logging Setup ---
class SensitiveFormatter(logging.Formatter):
    """Formatter that redacts API keys from log records."""
    SENSITIVE_WORDS: ClassVar[list[str]] = ["API_KEY", "API_SECRET"]

    def format(self, record):
        original_message = super().format(record)
        for word in self.SENSITIVE_WORDS:
            if word in original_message:
                original_message = original_message.replace(word, "*" * len(word))
        return original_message


def setup_logger(log_name: str, level=logging.INFO) -> logging.Logger:
    """Configure and return a logger with file and console handlers."""
    logger = logging.getLogger(log_name)
    logger.setLevel(level)
    logger.propagate = False
    if not logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(SensitiveFormatter(f"{NEON_BLUE}%(asctime)s - %(levelname)s - %(message)s{RESET}"))
        logger.addHandler(console_handler)
        log_file = Path(LOG_DIRECTORY) / f"{log_name}.log"
        file_handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5)
        file_handler.setFormatter(SensitiveFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        logger.addHandler(file_handler)
    return logger


# --- API Interaction & Live Trading ---
class PybitTradingClient:
    """Thin wrapper around pybit.unified_trading.HTTP for Bybit v5 order/position ops."""
    def __init__(self, config: dict[str, Any], logger: logging.Logger):
        self.cfg = config
        self.logger = logger
        self.enabled = bool(config.get("execution", {}).get("use_pybit", False))
        self.category = config.get("execution", {}).get("category", "linear")
        self.testnet = bool(config.get("execution", {}).get("testnet", False))
        if not self.enabled:
            self.session = None
            self.logger.info(f"{NEON_YELLOW}PyBit execution disabled.{RESET}")
            return
        if not PYBIT_AVAILABLE:
            self.enabled = False
            self.session = None
            self.logger.error(f"{NEON_RED}PyBit not installed. Please run 'pip install pybit'.{RESET}")
            return
        if not API_KEY or not API_SECRET:
            self.enabled = False
            self.session = None
            self.logger.error(f"{NEON_RED}API keys (BYBIT_API_KEY, BYBIT_API_SECRET) not found in .env for PyBit.{RESET}")
            return

        proxies = {}
        if self.cfg.get("execution", {}).get("proxies", {}).get("enabled", False):
            proxy_http = self.cfg["execution"]["proxies"].get("http")
            proxy_https = self.cfg["execution"]["proxies"].get("https")
            if proxy_http:
                proxies["http"] = proxy_http
            if proxy_https:
                proxies["https"] = proxy_https
            if proxies:
                self.logger.info(f"{NEON_BLUE}Proxy enabled.{RESET}")
            else:
                self.logger.warning(f"{NEON_YELLOW}Proxy enabled in config, but no proxy URLs provided.{RESET}")

        try:
            self.session = PybitHTTP(
                api_key=API_KEY,
                api_secret=API_SECRET,
                testnet=self.testnet,
                timeout=REQUEST_TIMEOUT,
                proxies=proxies if proxies else None
            )
            self.logger.info(f"{NEON_GREEN}PyBit client initialized. Testnet={self.testnet}{RESET}")
        except (pybit.exceptions.FailedRequestError, Exception) as e:
            self.enabled = False
            self.session = None
            self.logger.error(f"{NEON_RED}Failed to init PyBit client: {e}{RESET}")

    def _handle_403_error(self, e):
        """Specific handling for 403 Forbidden errors, often due to IP rate limits."""
        if "403" in str(e):
            self.logger.error(f"{NEON_RED}Encountered a 403 Forbidden error. This may be due to an IP rate limit or a geographical restriction (e.g., from the USA). The bot will pause for 60 seconds.{RESET}")
            time.sleep(60)

    def _pos_idx(self, side: Literal["BUY", "SELL"]) -> int:
        pmode = self.cfg["execution"].get("position_mode", "ONE_WAY").upper()
        overrides = self.cfg["execution"].get("position_idx_overrides", {})
        if pmode == "ONE_WAY":
            return int(overrides.get("ONE_WAY", 0))
        return int(overrides.get("HEDGE_BUY" if side == "BUY" else "HEDGE_SELL", 1 if side == "BUY" else 2))

    def _side_to_bybit(self, side: Literal["BUY", "SELL"]) -> str:
        return "Buy" if side == "BUY" else "Sell"

    def _q(self, x: Any) -> str:
        """Helper to convert value to string for Pybit API."""
        return str(x)

    def _ok(self, resp: dict | None) -> bool:
        """Checks if API response indicates success."""
        return bool(resp and resp.get("retCode") == 0)

    def _log_api(self, action: str, resp: dict | None):
        """Logs API response status."""
        if not resp:
            self.logger.error(f"{NEON_RED}{action}: No response.{RESET}")
            return
        if not self._ok(resp):
            self.logger.error(f"{NEON_RED}{action}: Error {resp.get('retCode')} - {resp.get('retMsg')}{RESET}")

    def set_leverage(self, symbol: str, buy: str, sell: str) -> bool:
        if not self.enabled: return False
        try:
            resp = self.session.set_leverage(category=self.category, symbol=symbol, buyLeverage=self._q(buy), sellLeverage=self._q(sell))
            self._log_api("set_leverage", resp)
            return self._ok(resp)
        except (pybit.exceptions.InvalidRequestError, pybit.exceptions.PybitHTTPException) as e:
            self.logger.error(f"{NEON_RED}set_leverage failed: {e}. Please check symbol, leverage, and account status.{RESET}")
            self._handle_403_error(e)
            return False

    def get_positions(self, symbol: str | None = None) -> dict | None:
        if not self.enabled: return None
        try:
            params = {"category": self.category}
            if symbol: params["symbol"] = symbol
            return self.session.get_positions(**params)
        except pybit.exceptions.FailedRequestError as e:
            self.logger.error(f"{NEON_RED}get_positions exception: {e}{RESET}")
            self._handle_403_error(e)
            return None

    def get_wallet_balance(self, coin: str = "USDT") -> dict | None:
        if not self.enabled: return None
        try:
            return self.session.get_wallet_balance(accountType=self.cfg["execution"].get("account_type", "UNIFIED"), coin=coin)
        except pybit.exceptions.FailedRequestError as e:
            self.logger.error(f"{NEON_RED}get_wallet_balance exception: {e}{RESET}")
            self._handle_403_error(e)
            return None

    def place_order(self, **kwargs) -> dict | None:
        if not self.enabled: return None
        try:
            resp = self.session.place_order(**kwargs)
            self._log_api("place_order", resp)
            return resp
        except pybit.exceptions.FailedRequestError as e:
            self.logger.error(f"{NEON_RED}place_order exception: {e}{RESET}")
            self._handle_403_error(e)
            return None

    def batch_place_orders(self, requests: list[dict]) -> dict | None:
        if not self.enabled: return None
        if not requests: return None
        try:
            resp = self.session.batch_place_order(category=self.category, request=requests)
            self._log_api("batch_place_order", resp)
            return resp
        except pybit.exceptions.FailedRequestError as e:
            self.logger.error(f"{NEON_RED}batch_place_orders exception: {e}{RESET}")
            self._handle_403_error(e)
            return None

    def cancel_by_link_id(self, symbol: str, order_link_id: str) -> dict | None:
        if not self.enabled: return None
        try:
            resp = self.session.cancel_order(
                category=self.category, symbol=symbol, orderLinkId=order_link_id
            )
            self._log_api("cancel_by_link_id", resp)
            return resp
        except pybit.exceptions.FailedRequestError as e:
            self.logger.error(f"{NEON_RED}cancel_by_link_id exception: {e}{RESET}")
            self._handle_403_error(e)
            return None

    def get_executions(self, symbol: str, start_time_ms: int, limit: int) -> dict | None:
        if not self.enabled: return None
        try:
            return self.session.get_executions(
                category=self.category, symbol=symbol, startTime=start_time_ms, limit=limit
            )
        except pybit.exceptions.FailedRequestError as e:
            self.logger.error(f"{NEON_RED}get_executions exception: {e}{RESET}")
            self._handle_403_error(e)
            return None

    def fetch_current_price(self, symbol: str) -> Decimal | None:
        if not self.enabled: return None
        try:
            response = self.session.get_tickers(category="linear", symbol=symbol)
            if response and response.get("retCode") == 0 and response.get("result", {}).get("list"):
                return Decimal(response["result"]["list"][0]["lastPrice"])
            self.logger.warning(f"{NEON_YELLOW}Could not fetch current price for {symbol}.{RESET}")
            return None
        except pybit.exceptions.FailedRequestError as e:
            self.logger.error(f"{NEON_RED}fetch_current_price exception: {e}{RESET}")
            self._handle_403_error(e)
            return None

    def fetch_instrument_info(self, symbol: str) -> dict | None:
        if not self.enabled: return None
        try:
            response = self.session.get_instruments_info(category="linear", symbol=symbol)
            if response and response.get("retCode") == 0 and response.get("result", {}).get("list"):
                return response["result"]["list"][0]
            self.logger.warning(f"{NEON_YELLOW}Could not fetch instrument info for {symbol}.{RESET}")
            return None
        except pybit.exceptions.FailedRequestError as e:
            self.logger.error(f"{NEON_RED}fetch_instrument_info exception: {e}{RESET}")
            self._handle_403_error(e)
            return None

    def fetch_klines(self, symbol: str, interval: str, limit: int) -> pd.DataFrame | None:
        if not self.enabled: return None
        try:
            params = {"category": "linear", "symbol": symbol, "interval": interval, "limit": limit}
            response = self.session.get_kline(**params)
            if response and response.get("result", {}).get("list"):
                df = pd.DataFrame(response["result"]["list"], columns=["start_time", "open", "high", "low", "close", "volume", "turnover"])
                df["start_time"] = pd.to_datetime(df["start_time"].astype(int), unit="ms", utc=True).dt.tz_convert(TIMEZONE)
                for col in ["open", "high", "low", "close", "volume", "turnover"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df.set_index("start_time", inplace=True)
                df.sort_index(inplace=True)
                return df if not df.empty else None
            self.logger.warning(f"{NEON_YELLOW}Could not fetch klines for {symbol} {interval}.{RESET}")
            return None
        except pybit.exceptions.FailedRequestError as e:
            self.logger.error(f"{NEON_RED}fetch_klines exception: {e}{RESET}")
            self._handle_403_error(e)
            return None

    def fetch_orderbook(self, symbol: str, limit: int) -> dict | None:
        if not self.enabled: return None
        try:
            response = self.session.get_orderbook(category="linear", symbol=symbol, limit=limit)
            if response and response.get("result"):
                return response["result"]
            self.logger.warning(f"{NEON_YELLOW}Could not fetch orderbook for {symbol}.{RESET}")
            return None
        except pybit.exceptions.FailedRequestError as e:
            self.logger.error(f"{NEON_RED}fetch_orderbook exception: {e}{RESET}")
            self._handle_403_error(e)
            return None


# --- Position Management ---
class PositionManager:
    """Manages open positions, including simulated and live trading operations."""
    def __init__(self, config: dict[str, Any], logger: logging.Logger, symbol: str, pybit_client: Optional[PybitTradingClient] = None):
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.open_positions: list[dict] = []
        self.trade_management_enabled = config["trade_management"]["enabled"]
        self.max_open_positions = config["trade_management"]["max_open_positions"]

        # Initialize with config values, will be updated from exchange if live
        self.order_precision = config["trade_management"]["order_precision"]
        self.price_precision = config["trade_management"]["price_precision"]
        self.qty_step = Decimal("0.000001") # Default small value, expected to be updated

        self.pybit = pybit_client
        self.live = bool(config.get("execution", {}).get("use_pybit", False))
        self.slippage_percent = Decimal(str(config["trade_management"].get("slippage_percent", 0.0)))

        self._update_precision_from_exchange()

    def _update_precision_from_exchange(self):
        """Fetch and set precision settings from the exchange."""
        if not self.live or not self.pybit or not self.pybit.enabled:
            self.logger.warning(f"{NEON_YELLOW}Pybit client not enabled or not live. Cannot fetch precision for {self.symbol}. Using config values.{RESET}")
            return
        self.logger.info(f"{NEON_BLUE}Fetching precision for {self.symbol} from exchange...{RESET}")
        info = self.pybit.fetch_instrument_info(self.symbol)
        if info:
            if "lotSizeFilter" in info:
                lot_size_filter = info["lotSizeFilter"]
                self.qty_step = Decimal(str(lot_size_filter.get("qtyStep")))
                if not self.qty_step.is_zero():
                    # Calculate actual decimal places from qtyStep
                    self.order_precision = abs(self.qty_step.as_tuple().exponent)
                self.logger.info(f"{NEON_BLUE}Updated qty_step: {self.qty_step}, order_precision: {self.order_precision}{RESET}")
            else:
                self.logger.warning(f"{NEON_YELLOW}Could not find lotSizeFilter for {self.symbol}. Using config values.{RESET}")

            if "priceFilter" in info:
                price_filter = info["priceFilter"]
                tick_size = Decimal(str(price_filter.get("tickSize")))
                if not tick_size.is_zero():
                    self.price_precision = abs(tick_size.as_tuple().exponent)
                self.logger.info(f"{NEON_BLUE}Updated price_precision: {self.price_precision}{RESET}")
            else:
                self.logger.warning(f"{NEON_YELLOW}Could not find priceFilter for {self.symbol}. Using config values.{RESET}")
        else:
            self.logger.warning(f"{NEON_YELLOW}Could not fetch instrument info for {self.symbol}. Using config values.{RESET}")

    def _get_current_balance(self) -> Decimal:
        """Fetch current account balance from exchange if live, else use config."""
        if self.live and self.pybit and self.pybit.enabled:
            resp = self.pybit.get_wallet_balance(coin="USDT")
            if resp and self.pybit._ok(resp) and resp.get("result", {}).get("list"):
                for coin_balance in resp["result"]["list"][0]["coin"]:
                    if coin_balance["coin"] == "USDT":
                        return Decimal(coin_balance["walletBalance"])
        return Decimal(str(self.config["trade_management"]["account_balance"]))

    def _calculate_order_size(self, current_price: Decimal, atr_value: Decimal, conviction: float = 1.0) -> Decimal:
        """Calculate order size based on risk per trade, ATR, and conviction."""
        if not self.trade_management_enabled: return Decimal("0")
        account_balance = self._get_current_balance()
        base_risk_pct = Decimal(str(self.config["trade_management"]["risk_per_trade_percent"])) / 100
        
        # Scale risk by conviction (e.g., 0.5x to 1.5x of base risk)
        # conviction is typically between 0 and 1, so scale it to a multiplier range
        risk_multiplier = Decimal(str(np.clip(0.5 + conviction, 0.5, 1.5)))
        risk_pct = base_risk_pct * risk_multiplier

        stop_loss_atr_multiple = Decimal(str(self.config["trade_management"]["stop_loss_atr_multiple"]))
        risk_amount = account_balance * risk_pct
        stop_loss_distance = atr_value * stop_loss_atr_multiple
        
        if stop_loss_distance <= 0:
            self.logger.warning(f"{NEON_YELLOW}Stop loss distance is zero or negative. Cannot calculate order size.{RESET}")
            return Decimal("0")
        
        order_value = risk_amount / stop_loss_distance # This is the USD value risked
        order_qty = order_value / current_price # Convert to quantity of the asset

        return round_qty(order_qty, self.qty_step)

    def _compute_stop_loss_price(self, side: Literal["BUY", "SELL"], entry_price: Decimal, atr_value: Decimal) -> Decimal:
        """Compute Stop Loss price based on ATR multiple or percentage."""
        sl_cfg = self.config["execution"]["sl_scheme"]
        price_prec = self.config["trade_management"]["price_precision"]
        
        sl = Decimal("0")
        if sl_cfg["type"] == "atr_multiple":
            sl_mult = Decimal(str(sl_cfg["atr_multiple"]))
            sl = (entry_price - atr_value * sl_mult) if side == "BUY" else (entry_price + atr_value * sl_mult)
        elif sl_cfg["type"] == "percent":
            sl_pct = Decimal(str(sl_cfg["percent"])) / 100
            sl = (entry_price * (1 - sl_pct)) if side == "BUY" else (entry_price * (1 + sl_pct))
        
        return round_price(sl, price_prec)

    def _calculate_take_profit_price(self, signal: Literal["BUY", "SELL"], current_price: Decimal, atr_value: Decimal) -> Decimal:
        """Calculate Take Profit price based on ATR multiple."""
        tp_mult = Decimal(str(self.config["trade_management"]["take_profit_atr_multiple"]))
        tp = (current_price + (atr_value * tp_mult)) if signal == "BUY" else (current_price - (atr_value * tp_mult))
        return round_price(tp, self.price_precision)

    def open_position(self, signal: Literal["BUY", "SELL"], current_price: Decimal, atr_value: Decimal, conviction: float) -> dict | None:
        """Opens a new position, either simulated or live via Pybit."""
        if not self.trade_management_enabled or len(self.open_positions) >= self.max_open_positions:
            self.logger.info(f"{NEON_YELLOW}Cannot open new position (max reached or disabled).{RESET}")
            return None
        
        order_qty = self._calculate_order_size(current_price, atr_value, conviction)
        if order_qty <= 0:
            self.logger.warning(f"{NEON_YELLOW}Order quantity is zero. Cannot open position.{RESET}")
            return None
        
        stop_loss = self._compute_stop_loss_price(signal, current_price, atr_value)
        take_profit = self._calculate_take_profit_price(signal, current_price, atr_value)

        # Apply slippage for initial entry in simulation
        adjusted_entry_price_sim = current_price
        if not self.live:
            if signal == "BUY":
                adjusted_entry_price_sim = current_price * (Decimal("1") + self.slippage_percent)
            else: # SELL
                adjusted_entry_price_sim = current_price * (Decimal("1") - self.slippage_percent)

        position = {
            "entry_time": datetime.now(TIMEZONE), "symbol": self.symbol, "side": signal,
            "entry_price": round_price(adjusted_entry_price_sim, self.price_precision), "qty": order_qty,
            "stop_loss": stop_loss, "take_profit": round_price(take_profit, self.price_precision),
            "status": "OPEN", "link_prefix": f"wgx_{int(time.time()*1000)}", "adds": 0,
            "order_id": None, "stop_loss_order_id": None, "take_profit_order_ids": []
        }

        if self.live and self.pybit and self.pybit.enabled:
            entry_link_id = f"{position['link_prefix']}_entry"
            try:
                self.logger.info(f"{NEON_BLUE}Placing live market order for {signal} {order_qty} {self.symbol} at {current_price}...{RESET}")
                resp = self.pybit.place_order(
                    category=self.pybit.category,
                    symbol=self.symbol,
                    side=self.pybit._side_to_bybit(signal),
                    orderType="Market",
                    qty=self.pybit._q(order_qty),
                    orderLinkId=entry_link_id,
                    isLeverage=1, # Ensure leverage is applied
                    # tpSlMode="Full" # Can be set here or via set_trading_stop
                )
                if self.pybit._ok(resp):
                    position["order_id"] = resp["result"]["orderId"]
                    self.logger.info(f"{NEON_GREEN}Live entry submitted (Order ID: {position['order_id']}). Now setting TP/SL.{RESET}")
                    
                    # Set TP/SL immediately after entry
                    self.set_tpsl_for_position(position, current_price, atr_value)
                else:
                    self.logger.error(f"{NEON_RED}Live entry failed. Simulating only. Response: {resp}{RESET}")
            except Exception as e:
                self.logger.error(f"{NEON_RED}Exception during live entry: {e}. Simulating only.{RESET}")

        self.open_positions.append(position)
        self.logger.info(f"{NEON_GREEN}Opened {signal} position (local/simulated): {position}{RESET}")
        return position

    def set_tpsl_for_position(self, position: dict, current_price: Decimal, atr_value: Decimal):
        """Sets Take Profit and Stop Loss orders for a live position."""
        if not self.live or not self.pybit or not self.pybit.enabled: return

        sl_scheme = self.config["execution"]["sl_scheme"]
        tp_scheme = self.config["execution"]["tp_scheme"]

        # Ensure correct positionIdx for setting SL/TP
        pos_idx = self.pybit._pos_idx(position["side"])

        # --- Place Stop Loss ---
        if sl_scheme["use_conditional_stop"]:
            sl_price = self._compute_stop_loss_price(position["side"], position["entry_price"], atr_value)
            sl_link_id = f"{position['link_prefix']}_sl"
            
            self.logger.info(f"{NEON_BLUE}Placing conditional SL for {self.symbol} at {sl_price}...{RESET}")
            sl_resp = self.pybit.place_order(
                category=self.pybit.category,
                symbol=self.symbol,
                side=self.pybit._side_to_bybit("SELL" if position["side"] == "BUY" else "BUY"),
                orderType=sl_scheme["stop_order_type"], # e.g., "Market"
                qty=self.pybit._q(position["qty"]),
                reduceOnly=True,
                orderLinkId=sl_link_id,
                triggerPrice=self.pybit._q(sl_price),
                triggerDirection=(2 if position["side"] == "BUY" else 1), # 2 for falling price (BUY SL), 1 for rising price (SELL SL)
                orderFilter="Stop",
                # slTriggerBy=sl_scheme["sl_trigger_by"], # This can be part of place_order for conditional
            )
            if self.pybit._ok(sl_resp):
                position["stop_loss_order_id"] = sl_resp["result"]["orderId"]
                self.logger.info(f"{NEON_GREEN}Conditional SL placed successfully at {sl_price} (Order ID: {position['stop_loss_order_id']}).{RESET}")
            else:
                self.logger.error(f"{NEON_RED}Failed to place conditional SL: {sl_resp.get('retMsg')}{RESET}")

        # --- Place Take Profits (Partial) ---
        if tp_scheme["mode"] == "atr_multiples" and tp_scheme.get("targets"):
            tp_requests = build_partial_tp_targets(
                position["side"], position["entry_price"], atr_value, position["qty"],
                self.config, self.qty_step, self.price_precision, position["link_prefix"]
            )
            
            batch_orders = []
            for target_detail in tp_requests:
                payload = {
                    "symbol": self.symbol,
                    "side": self.pybit._side_to_bybit("SELL" if position["side"] == "BUY" else "BUY"),
                    "orderType": target_detail["order_type"],
                    "qty": self.pybit._q(target_detail["qty"]),
                    "price": self.pybit._q(target_detail["price"]),
                    "timeInForce": target_detail["tif"],
                    "reduceOnly": True,
                    "positionIdx": pos_idx,
                    "orderLinkId": target_detail["order_link_id"],
                    "isPostOnly": target_detail["post_only"],
                    # tpTriggerBy=self.config["execution"]["tp_trigger_by"], # For full TP, not for individual orders
                }
                batch_orders.append(payload)

            if batch_orders:
                self.logger.info(f"{NEON_BLUE}Placing {len(batch_orders)} partial TP orders for {self.symbol}...{RESET}")
                batch_resp = self.pybit.batch_place_orders(batch_orders)
                if self.pybit._ok(batch_resp):
                    for res in batch_resp["result"]["list"]:
                        if res.get("orderId"):
                            position["take_profit_order_ids"].append(res["orderId"])
                            self.logger.info(f"{NEON_GREEN}Partial TP placed successfully (Order ID: {res['orderId']}).{RESET}")
                        else:
                            self.logger.warning(f"{NEON_YELLOW}Failed to place one partial TP: {res.get('retMsg')}{RESET}")
                else:
                    self.logger.error(f"{NEON_RED}Batch TP placement failed: {batch_resp.get('retMsg')}{RESET}")
            else:
                self.logger.info(f"{NEON_YELLOW}No valid partial TP targets to place.{RESET}")

    def manage_positions(self, current_price: Decimal, performance_tracker: Any):
        """Manages simulated positions (for backtesting/simulation mode).
           Live positions are managed by ExchangeExecutionSync/PositionHeartbeat.
        """
        if self.live or not self.trade_management_enabled or not self.open_positions:
            return
        
        positions_to_close = []
        for i, pos in enumerate(self.open_positions):
            if pos["status"] == "OPEN":
                closed_by = ""
                # Apply slippage for simulated exit
                adjusted_exit_price_sim = current_price
                if pos["side"] == "BUY":
                    if current_price <= pos["stop_loss"]: closed_by = "STOP_LOSS"
                    elif current_price >= pos["take_profit"]: closed_by = "TAKE_PROFIT"
                    adjusted_exit_price_sim = current_price * (Decimal("1") - self.slippage_percent)
                elif pos["side"] == "SELL":
                    if current_price >= pos["stop_loss"]: closed_by = "STOP_LOSS"
                    elif current_price <= pos["take_profit"]: closed_by = "TAKE_PROFIT"
                    adjusted_exit_price_sim = current_price * (Decimal("1") + self.slippage_percent)

                if closed_by:
                    pos.update(
                        {
                            "status": "CLOSED",
                            "exit_time": datetime.now(TIMEZONE),
                            "exit_price": round_price(adjusted_exit_price_sim, self.price_precision),
                            "closed_by": closed_by,
                        }
                    )
                    pnl = (
                        (pos["exit_price"] - pos["entry_price"]) * pos["qty"]
                        if pos["side"] == "BUY"
                        else (pos["entry_price"] - pos["exit_price"]) * pos["qty"]
                    )
                    performance_tracker.record_trade(pos, pnl)
                    self.logger.info(
                        f"{NEON_PURPLE}Closed {pos['side']} by {closed_by}. PnL: {pnl:.2f}{RESET}"
                    )
                    positions_to_close.append(i)
        
        # Remove closed positions
        self.open_positions = [
            p for i, p in enumerate(self.open_positions) if i not in positions_to_close
        ]

    def get_open_positions(self) -> list[dict]:
        return [pos for pos in self.open_positions if pos["status"] == "OPEN"]
    
    def trail_stop(self, pos: dict, current_price: Decimal, atr_value: Decimal):
        """Adjusts trailing stop loss for a simulated position."""
        if pos.get('status') != 'OPEN' or self.live: return
        atr_mult = Decimal(str(self.config["trade_management"]["stop_loss_atr_multiple"]))
        side = pos["side"]
        pos["best_price"] = pos.get("best_price", pos["entry_price"]) # Track best price reached
        
        new_sl = pos["stop_loss"] # Initialize with current SL

        if side == "BUY":
            # Update best price if current price is higher
            pos["best_price"] = max(pos["best_price"], current_price)
            # New SL is (best price - ATR multiple * ATR)
            calculated_sl = pos["best_price"] - atr_mult * atr_value
            # Only raise SL, never lower it
            if calculated_sl > new_sl:
                new_sl = calculated_sl
                self.logger.debug(f"{NEON_BLUE}Trailing BUY SL to {new_sl:.2f}{RESET}")
        else: # SELL
            # Update best price if current price is lower
            pos["best_price"] = min(pos["best_price"], current_price)
            # New SL is (best price + ATR multiple * ATR)
            calculated_sl = pos["best_price"] + atr_mult * atr_value
            # Only lower SL, never raise it
            if calculated_sl < new_sl:
                new_sl = calculated_sl
                self.logger.debug(f"{NEON_BLUE}Trailing SELL SL to {new_sl:.2f}{RESET}")

        pos["stop_loss"] = round_price(new_sl, self.price_precision)

    def try_pyramid(self, current_price: Decimal, atr_value: Decimal):
        """Attempts to add to an existing position (pyramiding)."""
        if not self.trade_management_enabled or not self.open_positions or self.live: return
        py_cfg = self.config.get("pyramiding", {})
        if not py_cfg.get("enabled", False): return

        for pos in self.open_positions:
            if pos.get("status") != "OPEN": continue
            adds = pos.get("adds", 0)
            if adds >= int(py_cfg.get("max_adds", 0)): continue

            step_atr_mult = Decimal(str(py_cfg.get("step_atr", 0.7)))
            step_distance = step_atr_mult * atr_value # Distance for each pyramiding step

            # Calculate target price for the next add
            target_price = Decimal("0")
            if pos["side"] == "BUY":
                target_price = pos["entry_price"] + step_distance * (adds + 1)
            else: # SELL
                target_price = pos["entry_price"] - step_distance * (adds + 1)
            
            # Check if current price has reached the target for an add
            should_add = False
            if pos["side"] == "BUY" and current_price >= target_price:
                should_add = True
            elif pos["side"] == "SELL" and current_price <= target_price:
                should_add = True
            
            if should_add:
                size_pct_of_initial = Decimal(str(py_cfg.get("size_pct_of_initial", 0.5)))
                # Calculate add quantity based on initial position size
                add_qty = round_qty(pos['qty'] * size_pct_of_initial, self.qty_step)
                
                if add_qty > 0:
                    # Update average entry price and total quantity
                    total_cost = (pos['qty'] * pos['entry_price']) + (add_qty * current_price)
                    pos['qty'] += add_qty
                    pos['entry_price'] = total_cost / pos['qty'] # New average entry price
                    pos["adds"] = adds + 1 # Increment add count
                    self.logger.info(f"{NEON_GREEN}Pyramiding add #{pos['adds']} qty={add_qty.normalize()}. New avg price: {pos['entry_price'].normalize():.2f}{RESET}")

# --- Performance Tracking & Sync ---
class PerformanceTracker:
    """Tracks and reports trading performance."""
    def __init__(self, logger: logging.Logger, config: dict[str, Any]):
        self.logger = logger
        self.config = config
        self.trades: list[dict] = []
        self.total_pnl = Decimal("0")
        self.gross_profit = Decimal("0")
        self.gross_loss = Decimal("0")
        self.wins = 0
        self.losses = 0
        self.peak_pnl = Decimal("0") # For drawdown calculation
        self.max_drawdown = Decimal("0")
        self.trading_fee_percent = Decimal(
            str(config["trade_management"].get("trading_fee_percent", 0.0))
        )

    def record_trade(self, position: dict, pnl: Decimal):
        """Records a completed trade, deducting fees and updating performance metrics."""
        trade_record = {
            "entry_time": position["entry_time"],
            "exit_time": position["exit_time"],
            "symbol": position["symbol"],
            "side": position["side"],
            "entry_price": position["entry_price"],
            "exit_price": position["exit_price"],
            "qty": position["qty"],
            "pnl_gross": pnl, # PnL before fees
            "closed_by": position["closed_by"],
        }
        
        # Deduct fees for both entry and exit (simplified model)
        entry_fee_amount = position["entry_price"] * position["qty"] * self.trading_fee_percent
        exit_fee_amount = position["exit_price"] * position["qty"] * self.trading_fee_percent
        total_fees = entry_fee_amount + exit_fee_amount
        
        pnl_net = pnl - total_fees
        trade_record["fees"] = total_fees
        trade_record["pnl_net"] = pnl_net
        
        self.trades.append(trade_record)
        self.total_pnl += pnl_net

        if pnl_net > 0:
            self.wins += 1
            self.gross_profit += pnl_net
        else:
            self.losses += 1
            self.gross_loss += abs(pnl_net)
        
        # Update peak PnL and max drawdown
        if self.total_pnl > self.peak_pnl: self.peak_pnl = self.total_pnl
        drawdown = self.peak_pnl - self.total_pnl
        if drawdown > self.max_drawdown: self.max_drawdown = drawdown

        self.logger.info(
            f"{NEON_CYAN}Trade recorded. Gross PnL: {pnl.normalize():.4f}, Fees: {total_fees.normalize():.4f}, Net PnL: {pnl_net.normalize():.4f}. "
            f"Total PnL: {self.total_pnl.normalize():.4f}{RESET}"
        )

    def day_pnl(self) -> Decimal:
        """Calculates net PnL for the current trading day (UTC)."""
        if not self.trades: return Decimal("0")
        today = datetime.now(TIMEZONE).date()
        pnl_for_day = Decimal("0")
        for t in self.trades:
            et = t.get("exit_time") or t.get("entry_time")
            if et and et.date() == today:
                pnl_for_day += Decimal(str(t.get("pnl_net", "0")))
        return pnl_for_day

    def get_summary(self) -> dict:
        """Returns a summary of all recorded trades and performance metrics."""
        total_trades = len(self.trades)
        win_rate = (self.wins / total_trades) * 100 if total_trades > 0 else 0
        profit_factor = self.gross_profit / self.gross_loss if self.gross_loss > 0 else Decimal("inf")
        avg_win = self.gross_profit / self.wins if self.wins > 0 else Decimal("0")
        avg_loss = self.gross_loss / self.losses if self.losses > 0 else Decimal("0")
        return {
            "total_trades": total_trades, "total_pnl": f"{self.total_pnl:.4f}",
            "gross_profit": f"{self.gross_profit:.4f}", "gross_loss": f"{self.gross_loss:.4f}",
            "profit_factor": f"{profit_factor:.2f}", "max_drawdown": f"{self.max_drawdown:.4f}",
            "wins": self.wins, "losses": self.losses, "win_rate": f"{win_rate:.2f}%",
            "avg_win": f"{avg_win:.4f}", "avg_loss": f"{avg_loss:.4f}",
        }


class ExchangeExecutionSync:
    """Polls exchange for trade fills, records PnL, and triggers breakeven stops for live trading."""
    def __init__(
        self,
        symbol: str,
        pybit_client: PybitTradingClient,
        logger: logging.Logger,
        cfg: dict,
        position_manager: PositionManager,
        performance_tracker: PerformanceTracker,
    ):
        self.symbol = symbol
        self.pybit = pybit_client
        self.logger = logger
        self.cfg = cfg
        self.pm = position_manager
        self.pt = performance_tracker
        # Start fetching executions from 5 minutes ago to catch any missed ones on startup
        self.last_exec_time_ms = int(time.time() * 1000) - 5 * 60 * 1000

    def _is_ours(self, link_id: str | None) -> bool:
        """Checks if an orderLinkId belongs to our bot."""
        if not link_id: return False
        if not self.cfg["execution"]["live_sync"]["only_track_linked"]: return True
        return link_id.startswith("wgx_")

    def _compute_breakeven_price(
        self, side: str, entry_price: Decimal, atr_value: Decimal
    ) -> Decimal:
        """Calculates the breakeven price with an optional offset for SL adjustment."""
        be_cfg = self.cfg["execution"]["breakeven_after_tp1"]
        offset_type = str(be_cfg.get("offset_type", "atr")).lower()
        offset_value = Decimal(str(be_cfg.get("offset_value", 0)))
        lock_in_min_percent = Decimal(str(be_cfg.get("lock_in_min_percent", 0))) / Decimal("100")

        # Calculate base offset
        offset_amount = Decimal("0")
        if offset_type == "atr":
            offset_amount = atr_value * offset_value
        elif offset_type == "percent":
            offset_amount = entry_price * offset_value
        else: # absolute or ticks
            offset_amount = offset_value

        # Calculate guaranteed minimum profit if enabled
        min_profit_amount = entry_price * lock_in_min_percent
        
        # Determine actual adjustment for breakeven
        # For BUY, SL moves UP (entry + offset). For SELL, SL moves DOWN (entry - offset).
        # Also ensure at least min_profit_amount is locked in.
        if side == "BUY":
            adjustment = max(offset_amount, min_profit_amount)
            be_price = entry_price + adjustment
        else: # SELL
            adjustment = max(offset_amount, min_profit_amount)
            be_price = entry_price - adjustment
        
        return round_price(be_price, self.pm.price_precision)

    def _move_stop_to_breakeven(self, open_pos: dict, atr_value: Decimal):
        """Modifies the stop loss order to breakeven after TP1 is hit."""
        if not self.cfg["execution"]["breakeven_after_tp1"].get("enabled", False): return
        if open_pos.get("breakeven_set", False):
            self.logger.debug(f"{NEON_BLUE}Breakeven already set for {self.symbol}. Skipping.{RESET}")
            return

        try:
            entry = Decimal(str(open_pos["entry_price"]))
            side = open_pos["side"]
            new_sl_price = self._compute_breakeven_price(side, entry, atr_value)

            # Cancel existing SL order
            old_sl_link = f"{open_pos.get('link_prefix')}_sl"
            if open_pos.get("stop_loss_order_id"):
                self.pybit.cancel_order(
                    category=self.pybit.category,
                    symbol=self.symbol,
                    orderId=open_pos["stop_loss_order_id"]
                )
                self.logger.info(f"{NEON_BLUE}Cancelled old SL order {open_pos['stop_loss_order_id']} for {self.symbol}.{RESET}")
            else:
                # Attempt to cancel by link ID if orderId wasn't stored or initial SL was by link
                self.pybit.cancel_by_link_id(self.symbol, old_sl_link)
                self.logger.info(f"{NEON_BLUE}Attempted to cancel old SL by link {old_sl_link} for {self.symbol}.{RESET}")

            # Place new breakeven SL order
            new_sl_link_id = f"{open_pos['link_prefix']}_sl_be"
            sresp = self.pybit.place_order(
                category=self.pybit.category,
                symbol=self.symbol,
                side=self.pybit._side_to_bybit("SELL" if side == "BUY" else "BUY"),
                orderType=self.cfg["execution"]["sl_scheme"]["stop_order_type"],
                qty=self.pybit._q(open_pos["qty"]), # Use remaining qty
                reduceOnly=True,
                orderLinkId=new_sl_link_id,
                triggerPrice=self.pybit._q(new_sl_price),
                triggerDirection=(2 if side == "BUY" else 1),
                orderFilter="Stop",
                slTriggerBy=self.cfg["execution"]["breakeven_after_tp1"]["sl_trigger_by"],
            )
            if self.pybit._ok(sresp):
                open_pos["stop_loss"] = new_sl_price # Update local SL
                open_pos["stop_loss_order_id"] = sresp["result"]["orderId"]
                open_pos["breakeven_set"] = True
                self.logger.info(f"{NEON_GREEN}Moved SL to breakeven at {new_sl_price} (Order ID: {open_pos['stop_loss_order_id']}).{RESET}")
            else:
                self.logger.error(f"{NEON_RED}Failed to place breakeven SL: {sresp.get('retMsg')}{RESET}")

        except (pybit.exceptions.FailedRequestError, Exception) as e:
            self.logger.error(f"{NEON_RED}Breakeven move exception for {self.symbol}: {e}{RESET}")

    def poll(self):
        """Polls for recent trade executions and updates local positions/performance."""
        if not (self.pybit and self.pybit.enabled): return

        try:
            resp = self.pybit.get_executions(
                self.symbol,
                self.last_exec_time_ms,
                self.cfg["execution"]["live_sync"]["max_exec_fetch"],
            )
            if not self.pybit._ok(resp): return

            rows = resp.get("result", {}).get("list", [])
            # Sort by execution time to process chronologically
            rows.sort(key=lambda r: int(r.get("execTime", 0)))

            for r in rows:
                link = r.get("orderLinkId")
                # Skip if not our order, or already processed (though `last_exec_time_ms` should handle this)
                if not self._is_ours(link) or int(r.get("execTime", 0)) < self.last_exec_time_ms:
                    continue
                
                # Update last execution timestamp
                self.last_exec_time_ms = int(r.get("execTime", 0)) + 1 # +1 ms to avoid re-fetching same exec

                tag = "UNKNOWN"
                if link and link.endswith("_entry"): tag = "ENTRY"
                elif link and "_sl" in link: tag = "SL"
                elif link and "_tp" in link: tag = "TP"

                # Find the relevant open position
                open_pos = next(
                    (p for p in self.pm.open_positions if p.get("status") == "OPEN" and p.get("link_prefix") == link.split('_')[0] + '_' + link.split('_')[1]),
                    None
                )
                
                # If it's an execution that closes/reduces a position
                if tag in ("TP", "SL") and open_pos:
                    is_reduce = (
                        (open_pos["side"] == "BUY" and r.get("side") == "Sell")
                        or (open_pos["side"] == "SELL" and r.get("side") == "Buy")
                    )
                    
                    if is_reduce:
                        exec_qty = Decimal(str(r.get("execQty", "0")))
                        exec_price = Decimal(str(r.get("execPrice", "0")))

                        # Calculate PnL for this partial/full execution
                        pnl = (
                            (exec_price - open_pos["entry_price"]) * exec_qty
                            if open_pos["side"] == "BUY"
                            else (open_pos["entry_price"] - exec_price) * exec_qty
                        )
                        
                        # Record the trade part
                        self.pt.record_trade(
                            {
                                **open_pos, # Copy existing position details
                                "exit_time": datetime.fromtimestamp(int(r.get("execTime", 0)) / 1000, tz=TIMEZONE),
                                "exit_price": exec_price,
                                "qty": exec_qty, # This qty is for the executed part only
                                "closed_by": tag,
                            },
                            pnl,
                        )
                        
                        # Update remaining quantity of the open position
                        remaining_qty = open_pos["qty"] - exec_qty
                        open_pos["qty"] = max(remaining_qty, Decimal("0"))
                        
                        if remaining_qty <= 0:
                            # Position is fully closed
                            open_pos.update(
                                {
                                    "status": "CLOSED",
                                    "exit_time": datetime.fromtimestamp(int(r.get("execTime", 0)) / 1000, tz=TIMEZONE),
                                    "exit_price": exec_price,
                                    "closed_by": tag,
                                }
                            )
                            self.logger.info(f"{NEON_PURPLE}Position for {self.symbol} fully closed by {tag}. Remaining Qty: {open_pos['qty'].normalize()}{RESET}")
                        else:
                            self.logger.info(f"{NEON_PURPLE}Partial execution for {self.symbol} by {tag}. Remaining Qty: {open_pos['qty'].normalize()}{RESET}")
                    
                    # If TP1 was hit, trigger breakeven stop (if not already set)
                    if tag == "TP" and link.endswith("_tp1") and open_pos.get("status") == "OPEN":
                        atr_val = Decimal(str(self.cfg.get("_last_atr_value", "0.1"))) # Retrieve last ATR
                        self._move_stop_to_breakeven(open_pos, atr_val)
                        
            # Clean up fully closed positions from the manager's list
            self.pm.open_positions = [
                p for p in self.pm.open_positions if p.get("status") == "OPEN"
            ]
        
        except (pybit.exceptions.FailedRequestError, Exception) as e:
            self.logger.error(f"{NEON_RED}Execution sync error for {self.symbol}: {e}{RESET}")


class PositionHeartbeat:
    """Periodically reconciles local position state with the exchange for live trading."""
    def __init__(
        self,
        symbol: str,
        pybit_client: PybitTradingClient,
        logger: logging.Logger,
        cfg: dict,
        position_manager: PositionManager,
    ):
        self.symbol = symbol
        self.pybit = pybit_client
        self.logger = logger
        self.cfg = cfg
        self.pm = position_manager
        self._last_heartbeat_ms = 0

    def tick(self):
        """Performs a heartbeat check if the interval has passed."""
        hb_cfg = self.cfg["execution"]["live_sync"]["heartbeat"]
        if not (hb_cfg.get("enabled", True) and self.pybit and self.pybit.enabled):
            return
        
        now_ms = int(time.time() * 1000)
        if now_ms - self._last_heartbeat_ms < int(hb_cfg.get("interval_ms", 5000)):
            return # Not time for next heartbeat yet
        
        self._last_heartbeat_ms = now_ms
        self.logger.debug(f"{NEON_BLUE}Performing position heartbeat for {self.symbol}...{RESET}")

        try:
            resp = self.pybit.get_positions(self.symbol)
            if not self.pybit._ok(resp):
                self.logger.warning(f"{NEON_YELLOW}Heartbeat: Failed to fetch positions for {self.symbol}.{RESET}")
                return

            exchange_positions = (resp.get("result", {}) or {}).get("list", [])
            
            # Sum up net quantity from exchange (longs positive, shorts negative)
            net_qty_exchange = Decimal("0")
            avg_price_exchange = Decimal("0")
            if exchange_positions:
                for p in exchange_positions:
                    pos_size = Decimal(p.get("size", "0"))
                    if pos_size > 0: # Only consider open positions
                        if p.get("side") == "Buy":
                            net_qty_exchange += pos_size
                            avg_price_exchange = Decimal(p.get("avgPrice", "0")) # Simplified, assumes single position
                        elif p.get("side") == "Sell":
                            net_qty_exchange -= pos_size
                            avg_price_exchange = Decimal(p.get("avgPrice", "0")) # Simplified, assumes single position
            
            # Find local open position
            local_open_pos = next(
                (p for p in self.pm.open_positions if p.get("status") == "OPEN"), None
            )

            # Scenario 1: Exchange is flat, but local position exists
            if net_qty_exchange == 0 and local_open_pos:
                local_open_pos.update({"status": "CLOSED", "closed_by": "HEARTBEAT_SYNC"})
                self.logger.info(f"{NEON_PURPLE}Heartbeat: Closed local position for {self.symbol} (exchange is flat).{RESET}")
                self.pm.open_positions = [p for p in self.pm.open_positions if p.get("status") == "OPEN"] # Clean up

            # Scenario 2: Exchange has a position, but no local position
            elif net_qty_exchange != 0 and not local_open_pos:
                side_exchange = "BUY" if net_qty_exchange > 0 else "SELL"
                
                # Create a synthetic local position to match exchange
                synthetic_pos = {
                    "entry_time": datetime.now(TIMEZONE),
                    "symbol": self.symbol,
                    "side": side_exchange,
                    "entry_price": round_price(avg_price_exchange, self.pm.price_precision),
                    "qty": round_qty(abs(net_qty_exchange), self.pm.qty_step),
                    "stop_loss": Decimal("0"), # Needs to be updated manually or by sync
                    "take_profit": Decimal("0"), # Needs to be updated manually or by sync
                    "status": "OPEN",
                    "link_prefix": f"hb_{int(time.time()*1000)}", # Mark as heartbeat-synced
                    "adds": 0,
                    "order_id": None, "stop_loss_order_id": None, "take_profit_order_ids": []
                }
                self.pm.open_positions.append(synthetic_pos)
                self.logger.warning(f"{NEON_YELLOW}Heartbeat: Created synthetic local position for {self.symbol} to match exchange state.{RESET}")
            
            # Scenario 3: Both exist, compare and log (for more advanced reconciliation)
            elif net_qty_exchange != 0 and local_open_pos:
                # Basic check: compare quantities
                if abs(net_qty_exchange) != local_open_pos["qty"]:
                    self.logger.warning(f"{NEON_YELLOW}Heartbeat: Quantity mismatch for {self.symbol}. Local: {local_open_pos['qty'].normalize()}, Exchange: {abs(net_qty_exchange).normalize()}.{RESET}")
                # More checks could be added here (e.g., avg price, SL/TP levels)

        except (pybit.exceptions.FailedRequestError, Exception) as e:
            self.logger.error(f"{NEON_RED}Heartbeat error for {self.symbol}: {e}{RESET}")


# --- Trading Analysis ---
class TradingAnalyzer:
    """Analyzes trading data and generates signals using a confluence of indicators."""

    def __init__(
        self,
        df: pd.DataFrame,
        config: dict[str, Any],
        logger: logging.Logger,
        symbol: str,
    ):
        self.df = df.copy()
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.indicator_values: dict[str, float | str | Decimal] = {}
        self.fib_levels: dict[str, Decimal] = {} # For Fibonacci retracement levels
        self.weights = config["weight_sets"]["default_scalping"]
        self.indicator_settings = config["indicator_settings"]

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}TradingAnalyzer initialized with an empty DataFrame. Indicators will not be calculated.{RESET}"
            )
            return

        self._calculate_all_indicators()
        if self.config["indicators"].get("fibonacci_levels", False):
            self.calculate_fibonacci_levels()
        if self.config["indicators"].get("fibonacci_pivot_points", False):
            self.calculate_fibonacci_pivot_points()

    def _safe_calculate(
        self, func: callable, name: str, min_data_points: int = 0, *args, **kwargs
    ) -> Any | None:
        """Safely calculate indicators from the 'indicators' module and log errors."""
        if len(self.df) < min_data_points:
            self.logger.debug(
                f"[{self.symbol}] Skipping indicator '{name}': Not enough data. Need {min_data_points}, have {len(self.df)}."
            )
            return None
        try:
            # All indicator functions from 'indicators.py' expect df as first arg
            result = func(self.df, *args, **kwargs)
            
            is_empty = (
                result is None
                or (isinstance(result, pd.Series) and result.empty)
                or (
                    isinstance(result, pd.DataFrame) and result.empty
                )
                or (
                    isinstance(result, tuple)
                    and all(
                        r is None or (isinstance(r, pd.Series) and r.empty)
                        or (isinstance(r, pd.DataFrame) and r.empty) for r in result
                    )
                )
            )
            if is_empty:
                self.logger.warning(
                    f"{NEON_YELLOW}[{self.symbol}] Indicator '{name}' returned empty or None after calculation. Not enough valid data?{RESET}"
                )
            return result if not is_empty else None
        except Exception as e:
            self.logger.error(
                f"{NEON_RED}[{self.symbol}] Error calculating indicator '{name}': {e}{RESET}"
            )
            return None

    def _calculate_all_indicators(self) -> None:
        """Calculate all enabled technical indicators using the 'indicators' module."""
        self.logger.debug(f"[{self.symbol}] Calculating all technical indicators...\n")
        cfg = self.config
        isd = self.indicator_settings
        
        # --- SMA ---
        if cfg["indicators"].get("sma_10", False):
            self.df["SMA_10"] = self._safe_calculate(indicators.calculate_sma, "SMA_10", isd["sma_short_period"], period=isd["sma_short_period"])
            if self.df["SMA_10"] is not None: self.indicator_values["SMA_10"] = self.df["SMA_10"].iloc[-1]
        if cfg["indicators"].get("sma_trend_filter", False):
            self.df["SMA_Long"] = self._safe_calculate(indicators.calculate_sma, "SMA_Long", isd["sma_long_period"], period=isd["sma_long_period"])
            if self.df["SMA_Long"] is not None: self.indicator_values["SMA_Long"] = self.df["SMA_Long"].iloc[-1]

        # --- EMA ---
        if cfg["indicators"].get("ema_alignment", False):
            self.df["EMA_Short"] = self._safe_calculate(indicators.calculate_ema, "EMA_Short", isd["ema_short_period"], period=isd["ema_short_period"])
            self.df["EMA_Long"] = self._safe_calculate(indicators.calculate_ema, "EMA_Long", isd["ema_long_period"], period=isd["ema_long_period"])
            if self.df["EMA_Short"] is not None: self.indicator_values["EMA_Short"] = self.df["EMA_Short"].iloc[-1]
            if self.df["EMA_Long"] is not None: self.indicator_values["EMA_Long"] = self.df["EMA_Long"].iloc[-1]

        # --- ATR ---
        # TR is a prerequisite for ATR
        self.df["TR"] = self._safe_calculate(indicators.calculate_true_range, "TR", indicators.MIN_DATA_POINTS_TR)
        self.df["ATR"] = self._safe_calculate(indicators.calculate_atr, "ATR", isd["atr_period"], period=isd["atr_period"])
        if self.df["ATR"] is not None: self.indicator_values["ATR"] = self.df["ATR"].iloc[-1]

        # --- RSI ---
        if cfg["indicators"].get("rsi", False):
            self.df["RSI"] = self._safe_calculate(indicators.calculate_rsi, "RSI", isd["rsi_period"] + 1, period=isd["rsi_period"])
            if self.df["RSI"] is not None: self.indicator_values["RSI"] = self.df["RSI"].iloc[-1]

        # --- Stochastic RSI ---
        if cfg["indicators"].get("stoch_rsi", False):
            stoch_rsi_k, stoch_rsi_d = self._safe_calculate(indicators.calculate_stoch_rsi, "StochRSI", 
                                                            isd["stoch_rsi_period"] + isd["stoch_d_period"] + isd["stoch_k_period"],
                                                            period=isd["stoch_rsi_period"], k_period=isd["stoch_k_period"], d_period=isd["stoch_d_period"])
            if stoch_rsi_k is not None: self.df["StochRSI_K"] = stoch_rsi_k; self.indicator_values["StochRSI_K"] = stoch_rsi_k.iloc[-1]
            if stoch_rsi_d is not None: self.df["StochRSI_D"] = stoch_rsi_d; self.indicator_values["StochRSI_D"] = stoch_rsi_d.iloc[-1]

        # --- Bollinger Bands ---
        if cfg["indicators"].get("bollinger_bands", False):
            bb_upper, bb_middle, bb_lower = self._safe_calculate(indicators.calculate_bollinger_bands, "BollingerBands", 
                                                                  isd["bollinger_bands_period"],
                                                                  period=isd["bollinger_bands_period"], std_dev=isd["bollinger_bands_std_dev"])
            if bb_upper is not None: self.df["BB_Upper"] = bb_upper; self.indicator_values["BB_Upper"] = bb_upper.iloc[-1]
            if bb_middle is not None: self.df["BB_Middle"] = bb_middle; self.indicator_values["BB_Middle"] = bb_middle.iloc[-1]
            if bb_lower is not None: self.df["BB_Lower"] = bb_lower; self.indicator_values["BB_Lower"] = bb_lower.iloc[-1]

        # --- CCI ---
        if cfg["indicators"].get("cci", False):
            self.df["CCI"] = self._safe_calculate(indicators.calculate_cci, "CCI", isd["cci_period"], period=isd["cci_period"])
            if self.df["CCI"] is not None: self.indicator_values["CCI"] = self.df["CCI"].iloc[-1]

        # --- Williams %R ---
        if cfg["indicators"].get("wr", False):
            self.df["WR"] = self._safe_calculate(indicators.calculate_williams_r, "WR", isd["williams_r_period"], period=isd["williams_r_period"])
            if self.df["WR"] is not None: self.indicator_values["WR"] = self.df["WR"].iloc[-1]

        # --- MFI ---
        if cfg["indicators"].get("mfi", False):
            self.df["MFI"] = self._safe_calculate(indicators.calculate_mfi, "MFI", isd["mfi_period"] + 1, period=isd["mfi_period"])
            if self.df["MFI"] is not None: self.indicator_values["MFI"] = self.df["MFI"].iloc[-1]

        # --- OBV ---
        if cfg["indicators"].get("obv", False):
            obv_val, obv_ema = self._safe_calculate(indicators.calculate_obv, "OBV", indicators.MIN_DATA_POINTS_OBV, ema_period=isd["obv_ema_period"])
            if obv_val is not None: self.df["OBV"] = obv_val; self.indicator_values["OBV"] = obv_val.iloc[-1]
            if obv_ema is not None: self.df["OBV_EMA"] = obv_ema; self.indicator_values["OBV_EMA"] = obv_ema.iloc[-1]

        # --- CMF ---
        if cfg["indicators"].get("cmf", False):
            cmf_val = self._safe_calculate(indicators.calculate_cmf, "CMF", isd["cmf_period"], period=isd["cmf_period"])
            if cmf_val is not None: self.df["CMF"] = cmf_val; self.indicator_values["CMF"] = cmf_val.iloc[-1]

        # --- Ichimoku Cloud ---
        if cfg["indicators"].get("ichimoku_cloud", False):
            tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span = self._safe_calculate(indicators.calculate_ichimoku_cloud, "IchimokuCloud", 
                                                                                                    max(isd["ichimoku_tenkan_period"], isd["ichimoku_kijun_period"], isd["ichimoku_senkou_span_b_period"]) + isd["ichimoku_chikou_span_offset"],
                                                                                                    tenkan_period=isd["ichimoku_tenkan_period"], kijun_period=isd["ichimoku_kijun_period"],
                                                                                                    senkou_span_b_period=isd["ichimoku_senkou_span_b_period"], chikou_span_offset=isd["ichimoku_chikou_span_offset"])
            if tenkan_sen is not None: self.df["Tenkan_Sen"] = tenkan_sen; self.indicator_values["Tenkan_Sen"] = tenkan_sen.iloc[-1]
            if kijun_sen is not None: self.df["Kijun_Sen"] = kijun_sen; self.indicator_values["Kijun_Sen"] = kijun_sen.iloc[-1]
            if senkou_span_a is not None: self.df["Senkou_Span_A"] = senkou_span_a; self.indicator_values["Senkou_Span_A"] = senkou_span_a.iloc[-1]
            if senkou_span_b is not None: self.df["Senkou_Span_B"] = senkou_span_b; self.indicator_values["Senkou_Span_B"] = senkou_span_b.iloc[-1]
            if chikou_span is not None: self.df["Chikou_Span"] = chikou_span; self.indicator_values["Chikou_Span"] = chikou_span.fillna(0).iloc[-1]

        # --- PSAR ---
        if cfg["indicators"].get("psar", False):
            psar_val, psar_dir = self._safe_calculate(indicators.calculate_psar, "PSAR", indicators.MIN_DATA_POINTS_PSAR,
                                                      acceleration=isd["psar_acceleration"], max_acceleration=isd["psar_max_acceleration"])
            if psar_val is not None: self.df["PSAR_Val"] = psar_val; self.indicator_values["PSAR_Val"] = psar_val.iloc[-1]
            if psar_dir is not None: self.df["PSAR_Dir"] = psar_dir; self.indicator_values["PSAR_Dir"] = psar_dir.iloc[-1]

        # --- VWAP ---
        if cfg["indicators"].get("vwap", False):
            self.df["VWAP"] = self._safe_calculate(indicators.calculate_vwap, "VWAP", 1) # VWAP needs at least 1 bar
            if self.df["VWAP"] is not None: self.indicator_values["VWAP"] = self.df["VWAP"].iloc[-1]

        # --- Ehlers SuperTrend ---
        if cfg["indicators"].get("ehlers_supertrend", False):
            st_fast_result = self._safe_calculate(indicators.calculate_ehlers_supertrend, "EhlersSuperTrendFast",
                                                  isd["ehlers_fast_period"] * 3, period=isd["ehlers_fast_period"], multiplier=isd["ehlers_fast_multiplier"])
            if st_fast_result is not None and not st_fast_result.empty:
                self.df["ST_Fast_Dir"] = st_fast_result["direction"]
                self.df["ST_Fast_Val"] = st_fast_result["supertrend"]
                self.indicator_values["ST_Fast_Dir"] = st_fast_result["direction"].iloc[-1]
                self.indicator_values["ST_Fast_Val"] = st_fast_result["supertrend"].iloc[-1]
            st_slow_result = self._safe_calculate(indicators.calculate_ehlers_supertrend, "EhlersSuperTrendSlow",
                                                  isd["ehlers_slow_period"] * 3, period=isd["ehlers_slow_period"], multiplier=isd["ehlers_slow_multiplier"])
            if st_slow_result is not None and not st_slow_result.empty:
                self.df["ST_Slow_Dir"] = st_slow_result["direction"]
                self.df["ST_Slow_Val"] = st_slow_result["supertrend"]
                self.indicator_values["ST_Slow_Dir"] = st_slow_result["direction"].iloc[-1]
                self.indicator_values["ST_Slow_Val"] = st_slow_result["supertrend"].iloc[-1]

        # --- MACD ---
        if cfg["indicators"].get("macd", False):
            macd_line, signal_line, histogram = self._safe_calculate(indicators.calculate_macd, "MACD",
                                                                      isd["macd_slow_period"] + isd["macd_signal_period"],
                                                                      fast_period=isd["macd_fast_period"], slow_period=isd["macd_slow_period"], signal_period=isd["macd_signal_period"])
            if macd_line is not None: self.df["MACD_Line"] = macd_line; self.indicator_values["MACD_Line"] = macd_line.iloc[-1]
            if signal_line is not None: self.df["MACD_Signal"] = signal_line; self.indicator_values["MACD_Signal"] = signal_line.iloc[-1]
            if histogram is not None: self.df["MACD_Hist"] = histogram; self.indicator_values["MACD_Hist"] = histogram.iloc[-1]

        # --- ADX ---
        if cfg["indicators"].get("adx", False):
            adx_val, plus_di, minus_di = self._safe_calculate(indicators.calculate_adx, "ADX", isd["adx_period"] * 2, period=isd["adx_period"])
            if adx_val is not None: self.df["ADX"] = adx_val; self.indicator_values["ADX"] = adx_val.iloc[-1]
            if plus_di is not None: self.df["PlusDI"] = plus_di; self.indicator_values["PlusDI"] = plus_di.iloc[-1]
            if minus_di is not None: self.df["MinusDI"] = minus_di; self.indicator_values["MinusDI"] = minus_di.iloc[-1]

        # --- Volatility Index ---
        if cfg["indicators"].get("volatility_index", False):
            self.df["Volatility_Index"] = self._safe_calculate(indicators.calculate_volatility_index, "Volatility_Index", isd["volatility_index_period"], period=isd["volatility_index_period"])
            if self.df["Volatility_Index"] is not None: self.indicator_values["Volatility_Index"] = self.df["Volatility_Index"].iloc[-1]

        # --- VWMA ---
        if cfg["indicators"].get("vwma", False):
            self.df["VWMA"] = self._safe_calculate(indicators.calculate_vwma, "VWMA", isd["vwma_period"], period=isd["vwma_period"])
            if self.df["VWMA"] is not None: self.indicator_values["VWMA"] = self.df["VWMA"].iloc[-1]

        # --- Volume Delta ---
        if cfg["indicators"].get("volume_delta", False):
            self.df["Volume_Delta"] = self._safe_calculate(indicators.calculate_volume_delta, "Volume_Delta", isd["volume_delta_period"], period=isd["volume_delta_period"])
            if self.df["Volume_Delta"] is not None: self.indicator_values["Volume_Delta"] = self.df["Volume_Delta"].iloc[-1]

        # --- Kaufman AMA ---
        if cfg["indicators"].get("kaufman_ama", False):
            self.df["Kaufman_AMA"] = self._safe_calculate(indicators.calculate_kaufman_ama, "Kaufman_AMA",
                                                          isd["kama_period"] + isd["kama_slow_period"],
                                                          period=isd["kama_period"], fast_period=isd["kama_fast_period"], slow_period=isd["kama_slow_period"])
            if self.df["Kaufman_AMA"] is not None: self.indicator_values["Kaufman_AMA"] = self.df["Kaufman_AMA"].iloc[-1]

        # --- Relative Volume ---
        if cfg["indicators"].get("relative_volume", False):
            self.df["Relative_Volume"] = self._safe_calculate(indicators.calculate_relative_volume, "Relative_Volume", isd["relative_volume_period"], period=isd["relative_volume_period"])
            if self.df["Relative_Volume"] is not None: self.indicator_values["Relative_Volume"] = self.df["Relative_Volume"].iloc[-1]

        # --- Market Structure ---
        if cfg["indicators"].get("market_structure", False):
            ms_trend = self._safe_calculate(indicators.calculate_market_structure, "Market_Structure",
                                            isd["market_structure_lookback_period"] * 2, lookback_period=isd["market_structure_lookback_period"])
            if ms_trend is not None: self.df["Market_Structure_Trend"] = ms_trend; self.indicator_values["Market_Structure_Trend"] = ms_trend.iloc[-1]

        # --- DEMA ---
        if cfg["indicators"].get("dema", False):
            self.df["DEMA"] = self._safe_calculate(indicators.calculate_dema, "DEMA", 2 * isd["dema_period"], series=self.df["close"], period=isd["dema_period"])
            if self.df["DEMA"] is not None: self.indicator_values["DEMA"] = self.df["DEMA"].iloc[-1]

        # --- Keltner Channels ---
        if cfg["indicators"].get("keltner_channels", False):
            kc_upper, kc_middle, kc_lower = self._safe_calculate(indicators.calculate_keltner_channels, "KeltnerChannels",
                                                                  isd["keltner_period"] + isd["atr_period"],
                                                                  period=isd["keltner_period"], atr_multiplier=isd["keltner_atr_multiplier"], atr_period=isd["atr_period"])
            if kc_upper is not None: self.df["Keltner_Upper"] = kc_upper; self.indicator_values["Keltner_Upper"] = kc_upper.iloc[-1]
            if kc_middle is not None: self.df["Keltner_Middle"] = kc_middle; self.indicator_values["Keltner_Middle"] = kc_middle.iloc[-1]
            if kc_lower is not None: self.df["Keltner_Lower"] = kc_lower; self.indicator_values["Keltner_Lower"] = kc_lower.iloc[-1]

        # --- ROC ---
        if cfg["indicators"].get("roc", False):
            self.df["ROC"] = self._safe_calculate(indicators.calculate_roc, "ROC", isd["roc_period"] + 1, period=isd["roc_period"])
            if self.df["ROC"] is not None: self.indicator_values["ROC"] = self.df["ROC"].iloc[-1]

        # --- Candlestick Patterns ---
        if cfg["indicators"].get("candlestick_patterns", False):
            patterns = self._safe_calculate(indicators.detect_candlestick_patterns, "Candlestick_Patterns", MIN_CANDLESTICK_PATTERNS_BARS)
            if patterns is not None: self.df["Candlestick_Pattern"] = patterns; self.indicator_values["Candlestick_Pattern"] = patterns.iloc[-1]

        # Final cleanup after all indicators are calculated
        initial_len = len(self.df)
        self.df.dropna(subset=["close"], inplace=True)
        self.df.fillna(0, inplace=True) # Fill any remaining NaNs, e.g. for start of series

        if len(self.df) < initial_len:
            self.logger.debug(f"Dropped {initial_len - len(self.df)} rows with NaNs after indicator calculations.")
        if self.df.empty:
            self.logger.warning(f"{NEON_YELLOW}[{self.symbol}] DataFrame is empty after calculating all indicators and dropping NaNs.{RESET}")
        else:
            self.logger.debug(f"[{self.symbol}] Indicators calculated. Final DataFrame size: {len(self.df)}")

    def calculate_fibonacci_levels(self) -> None:
        """Calculates Fibonacci retracement levels and stores them in self.fib_levels."""
        window = self.config["indicator_settings"]["fibonacci_window"]
        fib_levels = indicators.calculate_fibonacci_levels(self.df, window)
        if fib_levels:
            self.fib_levels = fib_levels
        else:
            self.logger.warning(f"{NEON_YELLOW}[{self.symbol}] Fibonacci retracement levels could not be calculated.{RESET}")

    def calculate_fibonacci_pivot_points(self) -> None:
        """Calculates Fibonacci Pivot Points and stores them in self.indicator_values."""
        # Fibonacci Pivot Points need previous day's OHLC, so need at least 2 bars for 'current' and 'previous'
        if self.df.empty or len(self.df) < 2:
            self.logger.warning(f"{NEON_YELLOW}[{self.symbol}] DataFrame is too short for Fibonacci Pivot Points calculation. Need at least 2 bars.{RESET}")
            return

        # Pass in relevant data from df for calculation, then update indicator_values
        pivot_data = indicators.calculate_fibonacci_pivot_points(self.df)
        if pivot_data:
            price_precision_str = "0." + "0" * (self.config["trade_management"]["price_precision"] - 1) + "1"
            self.indicator_values["Pivot"] = Decimal(str(pivot_data["pivot"])).quantize(Decimal(price_precision_str), rounding=ROUND_DOWN)
            self.indicator_values["R1"] = Decimal(str(pivot_data["r1"])).quantize(Decimal(price_precision_str), rounding=ROUND_DOWN)
            self.indicator_values["R2"] = Decimal(str(pivot_data["r2"])).quantize(Decimal(price_precision_str), rounding=ROUND_DOWN)
            self.indicator_values["S1"] = Decimal(str(pivot_data["s1"])).quantize(Decimal(price_precision_str), rounding=ROUND_DOWN)
            self.indicator_values["S2"] = Decimal(str(pivot_data["s2"])).quantize(Decimal(price_precision_str), rounding=ROUND_DOWN)
            self.logger.debug(f"[{self.symbol}] Calculated Fibonacci Pivot Points.")
        else:
            self.logger.warning(f"{NEON_YELLOW}[{self.symbol}] Fibonacci Pivot Points could not be calculated.{RESET}")


    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        """Safely retrieve an indicator value from self.indicator_values."""
        return self.indicator_values.get(key, default)

    def _check_orderbook(self, orderbook_data: dict) -> float:
        """Analyze orderbook imbalance."""
        bids = orderbook_data.get("b", [])
        asks = orderbook_data.get("a", [])

        bid_volume = sum(Decimal(b[1]) for b in bids)
        ask_volume = sum(Decimal(a[1]) for a in asks)

        if bid_volume + ask_volume == 0: return 0.0

        imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
        self.logger.debug(f"[{self.symbol}] Orderbook Imbalance: {imbalance:.4f} (Bids: {bid_volume}, Asks: {ask_volume})")
        return float(imbalance)

    def calculate_support_resistance_from_orderbook(self, orderbook_data: dict) -> None:
        """Calculates support and resistance levels from orderbook data based on volume concentration."""
        bids = orderbook_data.get("b", [])
        asks = orderbook_data.get("a", [])

        max_bid_volume = Decimal("0")
        support_level = Decimal("0")
        for bid_price_str, bid_volume_str in bids:
            bid_volume_decimal = Decimal(bid_volume_str)
            if bid_volume_decimal > max_bid_volume:
                max_bid_volume = bid_volume_decimal
                support_level = Decimal(bid_price_str)

        max_ask_volume = Decimal("0")
        resistance_level = Decimal("0")
        for ask_price_str, ask_volume_str in asks:
            ask_volume_decimal = Decimal(ask_volume_str)
            if ask_volume_decimal > max_ask_volume:
                max_ask_volume = ask_volume_decimal
                resistance_level = Decimal(ask_price_str)

        price_precision_str = "0." + "0" * (self.config["trade_management"]["price_precision"] - 1) + "1"
        if support_level > 0:
            self.indicator_values["Support_Level"] = support_level.quantize(Decimal(price_precision_str), rounding=ROUND_DOWN)
            self.logger.debug(f"[{self.symbol}] Identified Support Level: {support_level} (Volume: {max_bid_volume})")
        if resistance_level > 0:
            self.indicator_values["Resistance_Level"] = resistance_level.quantize(Decimal(price_precision_str), rounding=ROUND_DOWN)
            self.logger.debug(f"[{self.symbol}] Identified Resistance Level: {resistance_level} (Volume: {max_ask_volume})")
    
    # --- Signal Generation Helper Methods (Modular Scoring) ---
    # These methods encapsulate the logic for scoring individual indicator contributions.
    # They should return a tuple: (contribution_to_score, dict_for_signal_breakdown)

    def _score_adx(self, trend_strength_multiplier_in: float) -> Tuple[float, dict]:
        adx_contrib = 0.0
        signal_breakdown_contrib = {}
        trend_strength_multiplier_out = trend_strength_multiplier_in
        if self.config["indicators"].get("adx", False):
            adx_val = self._get_indicator_value("ADX")
            plus_di = self._get_indicator_value("PlusDI")
            minus_di = self._get_indicator_value("MinusDI")
            adx_weight = self.weights.get("adx_strength", 0.0)

            if not pd.isna(adx_val) and not pd.isna(plus_di) and not pd.isna(minus_di):
                if adx_val > ADX_STRONG_TREND_THRESHOLD:
                    if plus_di > minus_di:
                        adx_contrib = adx_weight
                        self.logger.debug(f"ADX: Strong BUY trend (ADX > {ADX_STRONG_TREND_THRESHOLD}, +DI > -DI).")
                        trend_strength_multiplier_out *= 1.2
                    elif minus_di > plus_di:
                        adx_contrib = -adx_weight
                        self.logger.debug(f"ADX: Strong SELL trend (ADX > {ADX_STRONG_TREND_THRESHOLD}, -DI > +DI).")
                        trend_strength_multiplier_out *= 1.2
                elif adx_val < ADX_WEAK_TREND_THRESHOLD:
                    self.logger.debug(f"ADX: Weak trend (ADX < {ADX_WEAK_TREND_THRESHOLD}). Neutral signal.")
                    trend_strength_multiplier_out *= 0.8
                signal_breakdown_contrib["ADX"] = adx_contrib
        return adx_contrib, {"trend_strength_multiplier": trend_strength_multiplier_out, "breakdown": signal_breakdown_contrib}

    def _score_ema_alignment(self, current_close: Decimal, trend_multiplier: float) -> Tuple[float, dict]:
        ema_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("ema_alignment", False):
            ema_short = self._get_indicator_value("EMA_Short")
            ema_long = self._get_indicator_value("EMA_Long")
            if not pd.isna(ema_short) and not pd.isna(ema_long):
                weight = self.weights.get("ema_alignment", 0) * trend_multiplier
                if ema_short > ema_long:
                    ema_contrib = weight
                elif ema_short < ema_long:
                    ema_contrib = -weight
                signal_breakdown_contrib["EMA Alignment"] = ema_contrib
        return ema_contrib, signal_breakdown_contrib

    def _score_sma_trend_filter(self, current_close: Decimal) -> Tuple[float, dict]:
        sma_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("sma_trend_filter", False):
            sma_long = self._get_indicator_value("SMA_Long")
            if not pd.isna(sma_long):
                weight = self.weights.get("sma_trend_filter", 0)
                if current_close > sma_long:
                    sma_contrib = weight
                elif current_close < sma_long:
                    sma_contrib = -weight
                signal_breakdown_contrib["SMA Trend Filter"] = sma_contrib
        return sma_contrib, signal_breakdown_contrib

    def _score_momentum_indicators(self) -> Tuple[float, dict]:
        momentum_contrib = 0.0
        signal_breakdown_contrib = {}
        active_indicators = self.config["indicators"]
        isd = self.indicator_settings
        momentum_weight = self.weights.get("momentum_rsi_stoch_cci_wr_mfi", 0)

        # RSI
        if active_indicators.get("rsi", False):
            rsi = self._get_indicator_value("RSI")
            if not pd.isna(rsi):
                if rsi < isd["rsi_oversold"]:
                    momentum_contrib += momentum_weight * 0.5
                elif rsi > isd["rsi_overbought"]:
                    momentum_contrib -= momentum_weight * 0.5
                signal_breakdown_contrib["RSI"] = momentum_contrib # This is partial for RSI, combined later
        
        # StochRSI
        if active_indicators.get("stoch_rsi", False):
            stoch_k = self._get_indicator_value("StochRSI_K")
            stoch_d = self._get_indicator_value("StochRSI_D")
            if not pd.isna(stoch_k) and not pd.isna(stoch_d) and len(self.df) > 1:
                prev_stoch_k = self.df["StochRSI_K"].iloc[-2]
                prev_stoch_d = self.df["StochRSI_D"].iloc[-2]
                stoch_contrib = 0.0
                if stoch_k > stoch_d and prev_stoch_k <= prev_stoch_d and stoch_k < isd["stoch_rsi_oversold"]:
                    stoch_contrib = momentum_weight * 0.6
                    self.logger.debug(f"[{self.symbol}] StochRSI: Bullish crossover from oversold.")
                elif stoch_k < stoch_d and prev_stoch_k >= prev_stoch_d and stoch_k > isd["stoch_rsi_overbought"]:
                    stoch_contrib = -momentum_weight * 0.6
                    self.logger.debug(f"[{self.symbol}] StochRSI: Bearish crossover from overbought.")
                elif stoch_k > stoch_d and stoch_k < STOCH_RSI_MID_POINT: # General bullish momentum
                    stoch_contrib = momentum_weight * 0.2
                elif stoch_k < stoch_d and stoch_k > STOCH_RSI_MID_POINT: # General bearish momentum
                    stoch_contrib = -momentum_weight * 0.2
                momentum_contrib += stoch_contrib
                signal_breakdown_contrib["StochRSI Crossover"] = stoch_contrib

        # CCI
        if active_indicators.get("cci", False):
            cci = self._get_indicator_value("CCI")
            if not pd.isna(cci):
                cci_contrib = 0.0
                if cci < isd["cci_oversold"]:
                    cci_contrib = momentum_weight * 0.4
                elif cci > isd["cci_overbought"]:
                    cci_contrib = -momentum_weight * 0.4
                momentum_contrib += cci_contrib
                signal_breakdown_contrib["CCI"] = cci_contrib

        # Williams %R
        if active_indicators.get("wr", False):
            wr = self._get_indicator_value("WR")
            if not pd.isna(wr):
                wr_contrib = 0.0
                if wr < isd["williams_r_oversold"]:
                    wr_contrib = momentum_weight * 0.4
                elif wr > isd["williams_r_overbought"]:
                    wr_contrib = -momentum_weight * 0.4
                momentum_contrib += wr_contrib
                signal_breakdown_contrib["Williams %R"] = wr_contrib

        # MFI
        if active_indicators.get("mfi", False):
            mfi = self._get_indicator_value("MFI")
            if not pd.isna(mfi):
                mfi_contrib = 0.0
                if mfi < isd["mfi_oversold"]:
                    mfi_contrib = momentum_weight * 0.4
                elif mfi > isd["mfi_overbought"]:
                    mfi_contrib = -momentum_weight * 0.4
                momentum_contrib += mfi_contrib
                signal_breakdown_contrib["MFI"] = mfi_contrib

        return momentum_contrib, signal_breakdown_contrib
    
    def _score_bollinger_bands(self, current_close: Decimal) -> Tuple[float, dict]:
        bb_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("bollinger_bands", False):
            bb_upper = self._get_indicator_value("BB_Upper")
            bb_lower = self._get_indicator_value("BB_Lower")
            if not pd.isna(bb_upper) and not pd.isna(bb_lower):
                if current_close < bb_lower:
                    bb_contrib = self.weights.get("bollinger_bands", 0) * 0.5
                elif current_close > bb_upper:
                    bb_contrib = -self.weights.get("bollinger_bands", 0) * 0.5
                signal_breakdown_contrib["Bollinger Bands"] = bb_contrib
        return bb_contrib, signal_breakdown_contrib

    def _score_vwap(self, current_close: Decimal, prev_close: Decimal) -> Tuple[float, dict]:
        vwap_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("vwap", False):
            vwap = self._get_indicator_value("VWAP")
            if not pd.isna(vwap):
                if current_close > vwap:
                    vwap_contrib = self.weights.get("vwap", 0) * 0.2
                elif current_close < vwap:
                    vwap_contrib = -self.weights.get("vwap", 0) * 0.2

                if len(self.df) > 1 and "VWAP" in self.df.columns:
                    prev_vwap = Decimal(str(self.df["VWAP"].iloc[-2]))
                    if current_close > vwap and prev_close <= prev_vwap:
                        vwap_contrib += self.weights.get("vwap", 0) * 0.3
                        self.logger.debug(f"[{self.symbol}] VWAP: Bullish crossover detected.")
                    elif current_close < vwap and prev_close >= prev_vwap:
                        vwap_contrib -= self.weights.get("vwap", 0) * 0.3
                        self.logger.debug(f"[{self.symbol}] VWAP: Bearish crossover detected.")
                signal_breakdown_contrib["VWAP"] = vwap_contrib
        return vwap_contrib, signal_breakdown_contrib

    def _score_psar(self, current_close: Decimal, prev_close: Decimal) -> Tuple[float, dict]:
        psar_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("psar", False):
            psar_val = self._get_indicator_value("PSAR_Val")
            psar_dir = self._get_indicator_value("PSAR_Dir")
            if not pd.isna(psar_val) and not pd.isna(psar_dir):
                if psar_dir == 1:
                    psar_contrib = self.weights.get("psar", 0) * 0.5
                elif psar_dir == -1:
                    psar_contrib = -self.weights.get("psar", 0) * 0.5

                if len(self.df) > 1 and "PSAR_Val" in self.df.columns:
                    prev_psar_val = Decimal(str(self.df["PSAR_Val"].iloc[-2]))
                    if current_close > psar_val and prev_close <= prev_psar_val:
                        psar_contrib += self.weights.get("psar", 0) * 0.4
                        self.logger.debug("PSAR: Bullish reversal detected.")
                    elif current_close < psar_val and prev_close >= prev_psar_val:
                        psar_contrib -= self.weights.get("psar", 0) * 0.4
                        self.logger.debug("PSAR: Bearish reversal detected.")
                signal_breakdown_contrib["PSAR"] = psar_contrib
        return psar_contrib, signal_breakdown_contrib

    def _score_orderbook_imbalance(self, orderbook_data: Optional[dict]) -> Tuple[float, dict]:
        imbalance_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("orderbook_imbalance", False) and orderbook_data:
            current_close_float = float(self.df['close'].iloc[-1]) # Need float for _check_orderbook
            imbalance = self._check_orderbook(orderbook_data)
            imbalance_contrib = imbalance * self.weights.get("orderbook_imbalance", 0)
            signal_breakdown_contrib["Orderbook Imbalance"] = imbalance_contrib
            self.calculate_support_resistance_from_orderbook(orderbook_data) # Populate S/R levels
        return imbalance_contrib, signal_breakdown_contrib

    def _score_fibonacci_levels(self, current_close: Decimal, prev_close: Decimal) -> Tuple[float, dict]:
        fib_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("fibonacci_levels", False) and self.fib_levels:
            for level_name, level_price in self.fib_levels.items():
                if level_name not in ["0.0%", "100.0%"] and current_close > Decimal("0") and abs(
                    (current_close - level_price) / current_close
                ) < Decimal("0.001"): # Price is near a Fib level (within 0.1%)
                    self.logger.debug(f"Price near Fibonacci level {level_name}: {level_price}")
                    if len(self.df) > 1:
                        if current_close > prev_close and current_close > level_price: # Broken above level
                            fib_contrib += self.weights.get("fibonacci_levels", 0) * 0.1
                        elif current_close < prev_close and current_close < level_price: # Broken below level
                            fib_contrib -= self.weights.get("fibonacci_levels", 0) * 0.1
            signal_breakdown_contrib["Fibonacci Levels"] = fib_contrib
        return fib_contrib, signal_breakdown_contrib

    def _score_fibonacci_pivot_points(self, current_close: Decimal, prev_close: Decimal) -> Tuple[float, dict]:
        fib_pivot_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("fibonacci_pivot_points", False):
            pivot = self._get_indicator_value("Pivot")
            r1 = self._get_indicator_value("R1")
            r2 = self._get_indicator_value("R2")
            s1 = self._get_indicator_value("S1")
            s2 = self._get_indicator_value("S2")

            # Ensure all pivot levels are valid Decimal
            if not any(pd.isna(val) for val in [pivot, r1, r2, s1, s2]):
                weight = self.weights.get("fibonacci_pivot_points_confluence", 0)

                # Bullish signals (crossing above resistance/pivot)
                if current_close > r1 and prev_close <= r1:
                    fib_pivot_contrib += weight * 0.5
                    signal_breakdown_contrib["Fibonacci R1 Breakout"] = weight * 0.5
                elif current_close > r2 and prev_close <= r2:
                    fib_pivot_contrib += weight * 1.0
                    signal_breakdown_contrib["Fibonacci R2 Breakout"] = weight * 1.0
                elif current_close > pivot and prev_close <= pivot:
                    fib_pivot_contrib += weight * 0.2
                    signal_breakdown_contrib["Fibonacci Pivot Breakout"] = weight * 0.2

                # Bearish signals (crossing below support/pivot)
                if current_close < s1 and prev_close >= s1:
                    fib_pivot_contrib -= weight * 0.5
                    signal_breakdown_contrib["Fibonacci S1 Breakout"] = -weight * 0.5
                elif current_close < s2 and prev_close >= s2:
                    fib_pivot_contrib -= weight * 1.0
                    signal_breakdown_contrib["Fibonacci S2 Breakout"] = -weight * 1.0
                elif current_close < pivot and prev_close >= pivot:
                    fib_pivot_contrib -= weight * 0.2
                    signal_breakdown_contrib["Fibonacci Pivot Breakdown"] = -weight * 0.2
        return fib_pivot_contrib, signal_breakdown_contrib

    def _score_ehlers_supertrend(self, trend_multiplier: float) -> Tuple[float, dict]:
        st_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("ehlers_supertrend", False):
            st_fast_dir = self._get_indicator_value("ST_Fast_Dir")
            st_slow_dir = self._get_indicator_value("ST_Slow_Dir")
            prev_st_fast_dir = (
                self.df["ST_Fast_Dir"].iloc[-2]
                if "ST_Fast_Dir" in self.df.columns and len(self.df) > 1
                else np.nan
            )
            weight = self.weights.get("ehlers_supertrend_alignment", 0.0) * trend_multiplier

            if not pd.isna(st_fast_dir) and not pd.isna(st_slow_dir) and not pd.isna(prev_st_fast_dir):
                # Strong signal: fast ST flips while slow ST confirms trend
                if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1:
                    st_contrib = weight
                    self.logger.debug("Ehlers SuperTrend: Strong BUY signal (fast flip aligned with slow trend).")
                elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1:
                    st_contrib = -weight
                    self.logger.debug("Ehlers SuperTrend: Strong SELL signal (fast flip aligned with slow trend).")
                # Weaker signal: both STs aligned
                elif st_slow_dir == 1 and st_fast_dir == 1:
                    st_contrib = weight * 0.3
                elif st_slow_dir == -1 and st_fast_dir == -1:
                    st_contrib = -weight * 0.3
                signal_breakdown_contrib["Ehlers SuperTrend"] = st_contrib
        return st_contrib, signal_breakdown_contrib

    def _score_macd(self, trend_multiplier: float) -> Tuple[float, dict]:
        macd_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("macd", False):
            macd_line = self._get_indicator_value("MACD_Line")
            signal_line = self._get_indicator_value("MACD_Signal")
            histogram = self._get_indicator_value("MACD_Hist")
            weight = self.weights.get("macd_alignment", 0.0) * trend_multiplier

            if not pd.isna(macd_line) and not pd.isna(signal_line) and not pd.isna(histogram) and len(self.df) > 1:
                # MACD Line crossover Signal Line
                if macd_line > signal_line and self.df["MACD_Line"].iloc[-2] <= self.df["MACD_Signal"].iloc[-2]:
                    macd_contrib = weight
                    self.logger.debug("MACD: BUY signal (MACD line crossed above Signal line).")
                elif macd_line < signal_line and self.df["MACD_Line"].iloc[-2] >= self.df["MACD_Signal"].iloc[-2]:
                    macd_contrib = -weight
                    self.logger.debug("MACD: SELL signal (MACD line crossed below Signal line).")
                # MACD Histogram crossover zero line (weaker signal)
                elif histogram > 0 and self.df["MACD_Hist"].iloc[-2] < 0:
                    macd_contrib = weight * 0.2
                elif histogram < 0 and self.df["MACD_Hist"].iloc[-2] > 0:
                    macd_contrib = -weight * 0.2
                signal_breakdown_contrib["MACD"] = macd_contrib
        return macd_contrib, signal_breakdown_contrib

    def _score_ichimoku_cloud(self, current_close: Decimal) -> Tuple[float, dict]:
        ichimoku_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("ichimoku_cloud", False):
            tenkan_sen = self._get_indicator_value("Tenkan_Sen")
            kijun_sen = self._get_indicator_value("Kijun_Sen")
            senkou_span_a = self._get_indicator_value("Senkou_Span_A")
            senkou_span_b = self._get_indicator_value("Senkou_Span_B")
            chikou_span = self._get_indicator_value("Chikou_Span")
            weight = self.weights.get("ichimoku_confluence", 0.0)

            if not any(pd.isna(v) for v in [tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span]) and len(self.df) > 1:
                # Tenkan-sen / Kijun-sen crossover
                if tenkan_sen > kijun_sen and self.df["Tenkan_Sen"].iloc[-2] <= self.df["Kijun_Sen"].iloc[-2]:
                    ichimoku_contrib += weight * 0.5
                    self.logger.debug("Ichimoku: Tenkan-sen crossed above Kijun-sen (bullish).")
                elif tenkan_sen < kijun_sen and self.df["Tenkan_Sen"].iloc[-2] >= self.df["Kijun_Sen"].iloc[-2]:
                    ichimoku_contrib -= weight * 0.5
                    self.logger.debug("Ichimoku: Tenkan-sen crossed below Kijun-sen (bearish).")

                # Price breaks above/below Kumo (Cloud)
                if current_close > max(senkou_span_a, senkou_span_b) and self.df["close"].iloc[-2] <= max(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]):
                    ichimoku_contrib += weight * 0.7
                    self.logger.debug("Ichimoku: Price broke above Kumo (strong bullish).")
                elif current_close < min(senkou_span_a, senkou_span_b) and self.df["close"].iloc[-2] >= min(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]):
                    ichimoku_contrib -= weight * 0.7
                    self.logger.debug("Ichimoku: Price broke below Kumo (strong bearish).")

                # Chikou Span crossover price
                if chikou_span > current_close and self.df["Chikou_Span"].iloc[-2] <= self.df["close"].iloc[-2]:
                    ichimoku_contrib += weight * 0.3
                    self.logger.debug("Ichimoku: Chikou Span crossed above price (bullish confirmation).")
                elif chikou_span < current_close and self.df["Chikou_Span"].iloc[-2] >= self.df["close"].iloc[-2]:
                    ichimoku_contrib -= weight * 0.3
                    self.logger.debug("Ichimoku: Chikou Span crossed below price (bearish confirmation).")
                signal_breakdown_contrib["Ichimoku Cloud"] = ichimoku_contrib
        return ichimoku_contrib, signal_breakdown_contrib

    def _score_obv(self) -> Tuple[float, dict]:
        obv_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("obv", False):
            obv_val = self._get_indicator_value("OBV")
            obv_ema = self._get_indicator_value("OBV_EMA")
            weight = self.weights.get("obv_momentum", 0.0)

            if not pd.isna(obv_val) and not pd.isna(obv_ema) and len(self.df) > 1:
                if obv_val > obv_ema and self.df["OBV"].iloc[-2] <= self.df["OBV_EMA"].iloc[-2]:
                    obv_contrib += weight * 0.5
                    self.logger.debug("OBV: Bullish crossover detected.")
                elif obv_val < obv_ema and self.df["OBV"].iloc[-2] >= self.df["OBV_EMA"].iloc[-2]:
                    obv_contrib -= weight * 0.5
                    self.logger.debug("OBV: Bearish crossover detected.")

                if len(self.df) > 2: # Check for momentum in OBV
                    if obv_val > self.df["OBV"].iloc[-2] and obv_val > self.df["OBV"].iloc[-3]:
                        obv_contrib += weight * 0.2
                    elif obv_val < self.df["OBV"].iloc[-2] and obv_val < self.df["OBV"].iloc[-3]:
                        obv_contrib -= weight * 0.2
                signal_breakdown_contrib["OBV"] = obv_contrib
        return obv_contrib, signal_breakdown_contrib

    def _score_cmf(self) -> Tuple[float, dict]:
        cmf_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("cmf", False):
            cmf_val = self._get_indicator_value("CMF")
            weight = self.weights.get("cmf_flow", 0.0)

            if not pd.isna(cmf_val):
                if cmf_val > 0: # CMF above zero indicates buying pressure
                    cmf_contrib = weight * 0.5
                elif cmf_val < 0: # CMF below zero indicates selling pressure
                    cmf_contrib = -weight * 0.5

                if len(self.df) > 2: # Check for momentum in CMF
                    if cmf_val > self.df["CMF"].iloc[-2] and cmf_val > self.df["CMF"].iloc[-3]:
                        cmf_contrib += weight * 0.3
                    elif cmf_val < self.df["CMF"].iloc[-2] and cmf_val < self.df["CMF"].iloc[-3]:
                        cmf_contrib -= weight * 0.3
                signal_breakdown_contrib["CMF"] = cmf_contrib
        return cmf_contrib, signal_breakdown_contrib

    def _score_volatility_index(self, signal_score_current: float) -> Tuple[float, dict]:
        vol_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("volatility_index", False):
            vol_idx = self._get_indicator_value("Volatility_Index")
            weight = self.weights.get("volatility_index_signal", 0.0)
            if not pd.isna(vol_idx):
                if len(self.df) > 2 and "Volatility_Index" in self.df.columns:
                    prev_vol_idx = self.df["Volatility_Index"].iloc[-2]
                    prev_prev_vol_idx = self.df["Volatility_Index"].iloc[-3]

                    if vol_idx > prev_vol_idx > prev_prev_vol_idx: # Increasing volatility
                        self.logger.debug("Volatility Index: Increasing volatility.")
                        if signal_score_current > 0: # Boost existing bullish signals
                            vol_contrib = weight * 0.2
                        elif signal_score_current < 0: # Boost existing bearish signals
                            vol_contrib = -weight * 0.2
                    elif vol_idx < prev_vol_idx < prev_prev_vol_idx: # Decreasing volatility
                        self.logger.debug("Volatility Index: Decreasing volatility.")
                        if abs(signal_score_current) > 0: # Dampen existing signals
                            vol_contrib = signal_score_current * -0.2
                signal_breakdown_contrib["Volatility Index"] = vol_contrib
        return vol_contrib, signal_breakdown_contrib

    def _score_vwma_cross(self, current_close: Decimal, prev_close: Decimal) -> Tuple[float, dict]:
        vwma_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("vwma", False):
            vwma = self._get_indicator_value("VWMA")
            weight = self.weights.get("vwma_cross", 0.0)
            if not pd.isna(vwma) and len(self.df) > 1 and "VWMA" in self.df.columns:
                prev_vwma = self.df["VWMA"].iloc[-2]
                if current_close > vwma and prev_close <= prev_vwma: # Bullish crossover
                    vwma_contrib = weight
                    self.logger.debug("VWMA: Bullish crossover (price above VWMA).")
                elif current_close < vwma and prev_close >= prev_vwma: # Bearish crossover
                    vwma_contrib = -weight
                    self.logger.debug("VWMA: Bearish crossover (price below VWMA).")
                signal_breakdown_contrib["VWMA Cross"] = vwma_contrib
        return vwma_contrib, signal_breakdown_contrib

    def _score_volume_delta(self) -> Tuple[float, dict]:
        vol_delta_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("volume_delta", False):
            volume_delta = self._get_indicator_value("Volume_Delta")
            volume_delta_threshold = self.indicator_settings["volume_delta_threshold"]
            weight = self.weights.get("volume_delta_signal", 0.0)

            if not pd.isna(volume_delta):
                if volume_delta > volume_delta_threshold: # Strong buying pressure
                    vol_delta_contrib = weight
                    self.logger.debug("Volume Delta: Strong buying pressure detected.")
                elif volume_delta < -volume_delta_threshold: # Strong selling pressure
                    vol_delta_contrib = -weight
                    self.logger.debug("Volume Delta: Strong selling pressure detected.")
                elif volume_delta > 0: # Moderate buying pressure
                    vol_delta_contrib = weight * 0.3
                elif volume_delta < 0: # Moderate selling pressure
                    vol_delta_contrib = -weight * 0.3
                signal_breakdown_contrib["Volume Delta"] = vol_delta_contrib
        return vol_delta_contrib, signal_breakdown_contrib

    def _score_kaufman_ama_cross(self, current_close: Decimal, prev_close: Decimal) -> Tuple[float, dict]:
        kama_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("kaufman_ama", False):
            kama = self._get_indicator_value("Kaufman_AMA")
            weight = self.weights.get("kaufman_ama_cross", 0.0)
            if not pd.isna(kama) and len(self.df) > 1 and "Kaufman_AMA" in self.df.columns:
                prev_kama = self.df["Kaufman_AMA"].iloc[-2]
                if current_close > kama and prev_close <= prev_kama: # Bullish crossover
                    kama_contrib = weight
                    self.logger.debug("KAMA: Bullish crossover (price above KAMA).")
                elif current_close < kama and prev_close >= prev_kama: # Bearish crossover
                    kama_contrib = -weight
                    self.logger.debug("KAMA: Bearish crossover (price below KAMA).")
                signal_breakdown_contrib["Kaufman AMA Cross"] = kama_contrib
        return kama_contrib, signal_breakdown_contrib

    def _score_relative_volume(self, current_close: Decimal, prev_close: Decimal) -> Tuple[float, dict]:
        rv_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("relative_volume", False):
            relative_volume = self._get_indicator_value("Relative_Volume")
            volume_threshold = self.indicator_settings["relative_volume_threshold"]
            weight = self.weights.get("relative_volume_confirmation", 0.0)

            if not pd.isna(relative_volume):
                if relative_volume >= volume_threshold: # Significantly higher volume
                    if current_close > prev_close: # Bullish bar with high volume
                        rv_contrib = weight
                        self.logger.debug(f"Volume: High relative bullish volume ({relative_volume:.2f}x average).")
                    elif current_close < prev_close: # Bearish bar with high volume
                        rv_contrib = -weight
                        self.logger.debug(f"Volume: High relative bearish volume ({relative_volume:.2f}x average).")
                signal_breakdown_contrib["Relative Volume"] = rv_contrib
        return rv_contrib, signal_breakdown_contrib

    def _score_market_structure(self) -> Tuple[float, dict]:
        ms_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("market_structure", False):
            ms_trend = self._get_indicator_value("Market_Structure_Trend", "SIDEWAYS")
            weight = self.weights.get("market_structure_confluence", 0.0)

            if ms_trend == "UP":
                ms_contrib = weight
                self.logger.debug("Market Structure: Confirmed Uptrend.")
            elif ms_trend == "DOWN":
                ms_contrib = -weight
                self.logger.debug("Market Structure: Confirmed Downtrend.")
            signal_breakdown_contrib["Market Structure"] = ms_contrib
        return ms_contrib, signal_breakdown_contrib

    def _score_dema_crossover(self) -> Tuple[float, dict]:
        dema_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("dema", False) and self.config["indicators"].get("ema_alignment", False):
            dema = self._get_indicator_value("DEMA")
            ema_short = self._get_indicator_value("EMA_Short")
            weight = self.weights.get("dema_crossover", 0.0)

            if not pd.isna(dema) and not pd.isna(ema_short) and len(self.df) > 1:
                prev_dema = self.df["DEMA"].iloc[-2]
                prev_ema_short = self.df["EMA_Short"].iloc[-2]

                if dema > ema_short and prev_dema <= prev_ema_short:
                    dema_contrib = weight
                    self.logger.debug("DEMA: Bullish crossover (DEMA above EMA_Short).")
                elif dema < ema_short and prev_dema >= prev_ema_short:
                    dema_contrib = -weight
                    self.logger.debug("DEMA: Bearish crossover (DEMA below EMA_Short).")
                signal_breakdown_contrib["DEMA Crossover"] = dema_contrib
        return dema_contrib, signal_breakdown_contrib

    def _score_keltner_channels(self, current_close: Decimal, prev_close: Decimal) -> Tuple[float, dict]:
        kc_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("keltner_channels", False):
            kc_upper = self._get_indicator_value("Keltner_Upper")
            kc_lower = self._get_indicator_value("Keltner_Lower")
            weight = self.weights.get("keltner_breakout", 0.0)

            if not pd.isna(kc_upper) and not pd.isna(kc_lower) and len(self.df) > 1:
                if current_close > kc_upper and prev_close <= self.df["Keltner_Upper"].iloc[-2]:
                    kc_contrib = weight
                    self.logger.debug("Keltner Channels: Bullish breakout above upper channel.")
                elif current_close < kc_lower and prev_close >= self.df["Keltner_Lower"].iloc[-2]:
                    kc_contrib = -weight
                    self.logger.debug("Keltner Channels: Bearish breakout below lower channel.")
                signal_breakdown_contrib["Keltner Channels"] = kc_contrib
        return kc_contrib, signal_breakdown_contrib

    def _score_roc_signals(self) -> Tuple[float, dict]:
        roc_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("roc", False):
            roc = self._get_indicator_value("ROC")
            weight = self.weights.get("roc_signal", 0.0)
            isd = self.indicator_settings

            if not pd.isna(roc):
                if roc < isd["roc_oversold"]: # Bullish signal from oversold
                    roc_contrib += weight * 0.7
                    self.logger.debug(f"ROC: Oversold ({roc:.2f}), potential bounce.")
                elif roc > isd["roc_overbought"]: # Bearish signal from overbought
                    roc_contrib -= weight * 0.7
                    self.logger.debug(f"ROC: Overbought ({roc:.2f}), potential pullback.")

                # Zero-line crossover (simple trend indication)
                if len(self.df) > 1 and "ROC" in self.df.columns:
                    prev_roc = self.df["ROC"].iloc[-2]
                    if roc > 0 and prev_roc <= 0:
                        roc_contrib += weight * 0.3 # Bullish zero-line cross
                        self.logger.debug("ROC: Bullish zero-line crossover.")
                    elif roc < 0 and prev_roc >= 0:
                        roc_contrib -= weight * 0.3 # Bearish zero-line cross
                        self.logger.debug("ROC: Bearish zero-line crossover.")
                signal_breakdown_contrib["ROC"] = roc_contrib
        return roc_contrib, signal_breakdown_contrib

    def _score_candlestick_patterns(self) -> Tuple[float, dict]:
        cp_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("candlestick_patterns", False):
            pattern = self._get_indicator_value("Candlestick_Pattern", "No Pattern")
            weight = self.weights.get("candlestick_confirmation", 0.0)

            if pattern in ["Bullish Engulfing", "Bullish Hammer"]:
                cp_contrib = weight
                self.logger.debug(f"Candlestick: Detected Bullish Pattern ({pattern}).")
            elif pattern in ["Bearish Engulfing", "Bearish Shooting Star"]:
                cp_contrib = -weight
                self.logger.debug(f"Candlestick: Detected Bearish Pattern ({pattern}).")
            signal_breakdown_contrib["Candlestick Pattern"] = cp_contrib
        return cp_contrib, signal_breakdown_contrib
    
    def _score_mtf_confluence(self, mtf_trends: dict[str, str]) -> Tuple[float, dict]:
        mtf_contribution = 0.0
        signal_breakdown_contrib = {}
        if self.config["mtf_analysis"]["enabled"] and mtf_trends:
            mtf_buy_count = 0
            mtf_sell_count = 0
            total_mtf_indicators = len(mtf_trends)

            for _tf_indicator, trend in mtf_trends.items():
                if trend == "UP": mtf_buy_count += 1
                elif trend == "DOWN": mtf_sell_count += 1

            mtf_weight = self.weights.get("mtf_trend_confluence", 0.0)

            if total_mtf_indicators > 0:
                if mtf_buy_count == total_mtf_indicators: # All TFs agree bullish
                    mtf_contribution = mtf_weight * 1.5 # Stronger boost
                    self.logger.debug(f"MTF: All {total_mtf_indicators} higher TFs are UP. Strong bullish confluence.")
                elif mtf_sell_count == total_mtf_indicators: # All TFs agree bearish
                    mtf_contribution = -mtf_weight * 1.5 # Stronger penalty
                    self.logger.debug(f"MTF: All {total_mtf_indicators} higher TFs are DOWN. Strong bearish confluence.")
                else: # Mixed or some agreement
                    normalized_mtf_score = (mtf_buy_count - mtf_sell_count) / total_mtf_indicators
                    mtf_contribution = mtf_weight * normalized_mtf_score # Proportional score

                signal_breakdown_contrib["MTF Confluence"] = mtf_contribution
                self.logger.debug(f"MTF Confluence: Buy: {mtf_buy_count}, Sell: {mtf_sell_count}. MTF contribution: {mtf_contribution:.2f}")
        return mtf_contribution, signal_breakdown_contrib

    def _dynamic_threshold(self, base_threshold: float) -> float:
        """Adjusts the signal threshold based on current market volatility (ATR)."""
        atr_now = self._get_indicator_value("ATR", 0.0) # Using float 0.0 for comparison
        # Ensure ATR Series exists and has enough data for rolling mean
        if "ATR" not in self.df.columns or self.df["ATR"].isnull().all() or len(self.df["ATR"]) < 50:
            return base_threshold
        
        atr_ma_series = self.df["ATR"].rolling(50).mean()
        if atr_ma_series.empty or atr_ma_series.iloc[-1] <= 0: return base_threshold
        
        atr_ma = float(atr_ma_series.iloc[-1]) # Convert to float for calculation
        ratio = float(np.clip(float(atr_now) / atr_ma, 0.9, 1.5)) # Convert to float
        return base_threshold * ratio

    def generate_trading_signal(
        self,
        current_price: Decimal,
        orderbook_data: Optional[dict],
        mtf_trends: dict[str, str],
    ) -> Tuple[str, float, dict]:
        """Generates a trading signal by aggregating scores from multiple indicators."""
        signal_score = 0.0
        signal_breakdown: dict[str, float] = {}

        if self.df.empty:
            self.logger.warning(f"{NEON_YELLOW}[{self.symbol}] DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}")
            return "HOLD", 0.0, {}

        current_close = Decimal(str(self.df["close"].iloc[-1]))
        prev_close = Decimal(str(self.df["close"].iloc[-2]) if len(self.df) > 1 else current_close)
        
        # Initialize trend_strength_multiplier, will be updated by ADX scoring
        trend_strength_multiplier = 1.0

        # ADX is calculated first to determine overall trend strength for other indicators
        adx_score, adx_info = self._score_adx(trend_strength_multiplier)
        signal_score += adx_score
        signal_breakdown.update(adx_info["breakdown"])
        trend_strength_multiplier = adx_info["trend_strength_multiplier"] # Update multiplier

        # --- Aggregate scores from all enabled indicators ---
        scorers_to_run = [
            (self._score_ema_alignment, [current_close, trend_strength_multiplier]),
            (self._score_sma_trend_filter, [current_close]),
            (self._score_momentum_indicators, []),
            (self._score_bollinger_bands, [current_close]),
            (self._score_vwap, [current_close, prev_close]),
            (self._score_psar, [current_close, prev_close]),
            (self._score_fibonacci_levels, [current_close, prev_close]),
            (self._score_fibonacci_pivot_points, [current_close, prev_close]),
            (self._score_ehlers_supertrend, [trend_strength_multiplier]),
            (self._score_macd, [trend_strength_multiplier]),
            (self._score_ichimoku_cloud, [current_close]),
            (self._score_obv, []),
            (self._score_cmf, []),
            (self._score_vwma_cross, [current_close, prev_close]),
            (self._score_volume_delta, []),
            (self._score_kaufman_ama_cross, [current_close, prev_close]),
            (self._score_relative_volume, [current_close, prev_close]),
            (self._score_market_structure, []),
            (self._score_dema_crossover, []),
            (self._score_keltner_channels, [current_close, prev_close]),
            (self._score_roc_signals, []),
            (self._score_candlestick_patterns, []),
        ]

        for scorer_func, args in scorers_to_run:
            contrib, breakdown_dict = scorer_func(*args)
            signal_score += contrib
            signal_breakdown.update(breakdown_dict)

        # Volatility index is scored separately as it depends on the *current* signal score
        vol_contrib, vol_breakdown = self._score_volatility_index(signal_score)
        signal_score += vol_contrib
        signal_breakdown.update(vol_breakdown)

        imbalance_score, imbalance_breakdown = self._score_orderbook_imbalance(orderbook_data)
        signal_score += imbalance_score
        signal_breakdown.update(imbalance_breakdown)

        mtf_score, mtf_breakdown = self._score_mtf_confluence(mtf_trends)
        signal_score += mtf_score
        signal_breakdown.update(mtf_breakdown)

        # --- Final Signal Decision with Dynamic Threshold, Hysteresis, and Cooldown ---
        base_threshold = max(float(self.config.get("signal_score_threshold", 2.0)), 1.0)
        dynamic_threshold = self._dynamic_threshold(base_threshold)
        
        # Hysteresis: prevent rapid flip-flopping around the threshold
        last_score = float(self.config.get("_last_score", 0.0))
        hysteresis_ratio = float(self.config.get("hysteresis_ratio", 0.85))
        
        final_signal = "HOLD"
        # If current score crosses the threshold in opposite direction, but not enough to overcome hysteresis
        if np.sign(signal_score) != np.sign(last_score) and abs(signal_score) < abs(last_score) * hysteresis_ratio:
            final_signal = "HOLD" # Stay in previous state or hold
        else: # Regular threshold check
            if signal_score >= dynamic_threshold: final_signal = "BUY"
            elif signal_score <= -dynamic_threshold: final_signal = "SELL"
        
        # Cooldown period: prevent multiple entries in short succession
        cooldown_sec = int(self.config.get("cooldown_sec", 0))
        now_ts = int(time.time())
        last_signal_ts = int(self.config.get("_last_signal_ts", 0))

        if cooldown_sec > 0 and now_ts - last_signal_ts < cooldown_sec and final_signal != "HOLD":
            # If a new signal is generated but still within cooldown, ignore it
            self.logger.info(f"{NEON_YELLOW}Signal ignored due to cooldown ({cooldown_sec}s). Next signal possible in {cooldown_sec - (now_ts - last_signal_ts)}s.{RESET}")
            final_signal = "HOLD"
        
        # Store current score and timestamp for next loop's hysteresis/cooldown check
        self.config["_last_score"] = float(signal_score)
        if final_signal in ("BUY", "SELL"): self.config["_last_signal_ts"] = now_ts

        self.logger.info(f"{NEON_YELLOW}Regime: {self._market_regime()} | Score: {signal_score:.2f} | DynThresh: {dynamic_threshold:.2f} | Final: {final_signal}{RESET}")
        return final_signal, float(signal_score), signal_breakdown
    
    def _market_regime(self):
        """Determines market regime (trending or ranging) based on ADX and Bollinger Bands."""
        adx = self._get_indicator_value("ADX")
        bb_u = self._get_indicator_value("BB_Upper")
        bb_l = self._get_indicator_value("BB_Lower")
        bb_m = self._get_indicator_value("BB_Middle")
        
        # Check for NaN values before operations
        if pd.isna(adx) or pd.isna(bb_u) or pd.isna(bb_l) or pd.isna(bb_m) or float(bb_m) == 0:
            return "UNKNOWN" # Cannot determine regime without data

        band_width_pct = (float(bb_u) - float(bb_l)) / float(bb_m) if float(bb_m) != 0 else 0

        if float(adx) >= ADX_STRONG_TREND_THRESHOLD or band_width_pct >= 0.03: # 3% band width
            return "TRENDING"
        elif float(adx) <= ADX_WEAK_TREND_THRESHOLD and band_width_pct <= 0.01: # 1% band width
            return "RANGING"
        return "SIDEWAYS"


# --- Display Functions ---
def display_indicator_values_and_price(
    config: dict[str, Any],
    logger: logging.Logger,
    current_price: Decimal,
    analyzer: TradingAnalyzer,
    mtf_trends: dict[str, str],
    signal_breakdown: Optional[dict[str, float]] = None,
) -> None:
    """Displays current market price, indicator values, and a trend summary."""
    logger.info(f"{NEON_BLUE}--- Current Market Data & Indicators ---{RESET}")
    logger.info(f"{NEON_GREEN}Current Price: {current_price.normalize()}{RESET}")

    if analyzer.df.empty:
        logger.warning(f"{NEON_YELLOW}Cannot display indicators: DataFrame is empty after calculations.{RESET}")
        return

    logger.info(f"{NEON_CYAN}--- Indicator Values ---{RESET}")
    for indicator_name, value in analyzer.indicator_values.items():
        color = INDICATOR_COLORS.get(indicator_name, NEON_YELLOW)
        # Format Decimal values for consistent display, other types as is
        if isinstance(value, Decimal):
            logger.info(f"  {color}{indicator_name:<20}: {value.normalize()}{RESET}")
        elif isinstance(value, float):
            logger.info(f"  {color}{indicator_name:<20}: {value:.8f}{RESET}")
        else:
            logger.info(f"  {color}{indicator_name:<20}: {value}{RESET}")

    if analyzer.fib_levels:
        logger.info(f"{NEON_CYAN}--- Fibonacci Retracement Levels ---{RESET}")
        for level_name, level_price in analyzer.fib_levels.items():
            logger.info(f"  {NEON_YELLOW}{level_name:<20}: {level_price.normalize()}{RESET}")

    # Display Fibonacci Pivot Points
    if config["indicators"].get("fibonacci_pivot_points", False):
        if ("Pivot" in analyzer.indicator_values and "R1" in analyzer.indicator_values and "S1" in analyzer.indicator_values):
            logger.info(f"{NEON_CYAN}--- Fibonacci Pivot Points ---{RESET}")
            logger.info(f"  {INDICATOR_COLORS.get('Pivot', NEON_YELLOW)}Pivot              : {analyzer.indicator_values['Pivot'].normalize()}{RESET}")
            logger.info(f"  {INDICATOR_COLORS.get('R1', NEON_GREEN)}R1                 : {analyzer.indicator_values['R1'].normalize()}{RESET}")
            logger.info(f"  {INDICATOR_COLORS.get('R2', NEON_GREEN)}R2                 : {analyzer.indicator_values['R2'].normalize()}{RESET}")
            logger.info(f"  {INDICATOR_COLORS.get('S1', NEON_RED)}S1                 : {analyzer.indicator_values['S1'].normalize()}{RESET}")
            logger.info(f"  {INDICATOR_COLORS.get('S2', NEON_RED)}S2                 : {analyzer.indicator_values['S2'].normalize()}{RESET}")

    # Display Support and Resistance Levels (from orderbook)
    if ("Support_Level" in analyzer.indicator_values or "Resistance_Level" in analyzer.indicator_values):
        logger.info(f"{NEON_CYAN}--- Orderbook S/R Levels ---{RESET}")
        if "Support_Level" in analyzer.indicator_values:
            logger.info(f"  {INDICATOR_COLORS.get('Support_Level', NEON_YELLOW)}Support Level     : {analyzer.indicator_values['Support_Level'].normalize()}{RESET}")
        if "Resistance_Level" in analyzer.indicator_values:
            logger.info(f"  {INDICATOR_COLORS.get('Resistance_Level', NEON_YELLOW)}Resistance Level  : {analyzer.indicator_values['Resistance_Level'].normalize()}{RESET}")

    if mtf_trends:
        logger.info(f"{NEON_CYAN}--- Multi-Timeframe Trends ---{RESET}")
        for tf_indicator, trend in mtf_trends.items():
            logger.info(f"  {NEON_YELLOW}{tf_indicator:<20}: {trend}{RESET}")

    if signal_breakdown: # Display signal breakdown, sorted by absolute contribution
        logger.info(f"{NEON_CYAN}--- Signal Score Breakdown ---{RESET}")
        sorted_breakdown = sorted(signal_breakdown.items(), key=lambda item: abs(item[1]), reverse=True)
        for indicator, contribution in sorted_breakdown:
            color = (Fore.GREEN if contribution > 0 else (Fore.RED if contribution < 0 else Fore.YELLOW))
            logger.info(f"  {color}{indicator:<25}: {contribution: .2f}{RESET}")

    # --- Concise Trend Summary ---
    logger.info(f"{NEON_PURPLE}--- Current Trend Summary ---{RESET}")
    trend_summary_lines = []

    # EMA Alignment
    ema_short = analyzer._get_indicator_value("EMA_Short")
    ema_long = analyzer._get_indicator_value("EMA_Long")
    if not pd.isna(ema_short) and not pd.isna(ema_long):
        if ema_short > ema_long: trend_summary_lines.append(f"{Fore.GREEN}EMA Cross  : ▲ Up{RESET}")
        elif ema_short < ema_long: trend_summary_lines.append(f"{Fore.RED}EMA Cross  : ▼ Down{RESET}")
        else: trend_summary_lines.lines.append(f"{Fore.YELLOW}EMA Cross  : ↔ Sideways{RESET}")

    # Ehlers SuperTrend (Slow)
    st_slow_dir = analyzer._get_indicator_value("ST_Slow_Dir")
    if not pd.isna(st_slow_dir):
        if st_slow_dir == 1: trend_summary_lines.append(f"{Fore.GREEN}SuperTrend : ▲ Up{RESET}")
        elif st_slow_dir == -1: trend_summary_lines.append(f"{Fore.RED}SuperTrend : ▼ Down{RESET}")
        else: trend_summary_lines.append(f"{Fore.YELLOW}SuperTrend : ↔ Sideways{RESET}")

    # MACD Histogram (momentum)
    macd_hist = analyzer._get_indicator_value("MACD_Hist")
    if not pd.isna(macd_hist):
        # Retrieve previous MACD_Hist value safely
        if "MACD_Hist" in analyzer.df.columns and len(analyzer.df) > 1:
            prev_macd_hist = analyzer.df["MACD_Hist"].iloc[-2]
            if macd_hist > 0 and prev_macd_hist <= 0: trend_summary_lines.append(f"{Fore.GREEN}MACD Hist  : ↑ Bullish Cross{RESET}")
            elif macd_hist < 0 and prev_macd_hist >= 0: trend_summary_lines.append(f"{Fore.RED}MACD Hist  : ↓ Bearish Cross{RESET}")
            elif macd_hist > 0: trend_summary_lines.append(f"{Fore.LIGHTGREEN_EX}MACD Hist  : Above 0{RESET}")
            elif macd_hist < 0: trend_summary_lines.append(f"{Fore.LIGHTRED_EX}MACD Hist  : Below 0{RESET}")
        else: trend_summary_lines.append(f"{Fore.YELLOW}MACD Hist  : N/A{RESET}")

    # ADX Strength
    adx_val = analyzer._get_indicator_value("ADX")
    if not pd.isna(adx_val):
        if adx_val > ADX_STRONG_TREND_THRESHOLD:
            plus_di = analyzer._get_indicator_value("PlusDI")
            minus_di = analyzer._get_indicator_value("MinusDI")
            if not pd.isna(plus_di) and not pd.isna(minus_di):
                if plus_di > minus_di: trend_summary_lines.append(f"{Fore.LIGHTGREEN_EX}ADX Trend  : Strong Up ({adx_val:.0f}){RESET}")
                else: trend_summary_lines.append(f"{Fore.LIGHTRED_EX}ADX Trend  : Strong Down ({adx_val:.0f}){RESET}")
        elif adx_val < ADX_WEAK_TREND_THRESHOLD: trend_summary_lines.append(f"{Fore.YELLOW}ADX Trend  : Weak/Ranging ({adx_val:.0f}){RESET}")
        else: trend_summary_lines.append(f"{Fore.CYAN}ADX Trend  : Moderate ({adx_val:.0f}){RESET}")

    # Ichimoku Cloud (Kumo position)
    senkou_span_a = analyzer._get_indicator_value("Senkou_Span_A")
    senkou_span_b = analyzer._get_indicator_value("Senkou_Span_B")
    if not pd.isna(senkou_span_a) and not pd.isna(senkou_span_b):
        kumo_upper = max(senkou_span_a, senkou_span_b)
        kumo_lower = min(senkou_span_a, senkou_span_b)
        if current_price > kumo_upper: trend_summary_lines.append(f"{Fore.GREEN}Ichimoku   : Above Kumo{RESET}")
        elif current_price < kumo_lower: trend_summary_lines.append(f"{Fore.RED}Ichimoku   : Below Kumo{RESET}")
        else: trend_summary_lines.append(f"{Fore.YELLOW}Ichimoku   : Inside Kumo{RESET}")

    # MTF Confluence
    if mtf_trends:
        up_count = sum(1 for t in mtf_trends.values() if t == "UP")
        down_count = sum(1 for t in mtf_trends.values() if t == "DOWN")
        total = len(mtf_trends)
        if total > 0:
            if up_count == total: trend_summary_lines.append(f"{Fore.GREEN}MTF Confl. : All Bullish ({up_count}/{total}){RESET}")
            elif down_count == total: trend_summary_lines.append(f"{Fore.RED}MTF Confl. : All Bearish ({down_count}/{total}){RESET}")
            elif up_count > down_count: trend_summary_lines.append(f"{Fore.LIGHTGREEN_EX}MTF Confl. : Mostly Bullish ({up_count}/{total}){RESET}")
            elif down_count > up_count: trend_summary_lines.append(f"{Fore.LIGHTRED_EX}MTF Confl. : Mostly Bearish ({down_count}/{total}){RESET}")
            else: trend_summary_lines.append(f"{Fore.YELLOW}MTF Confl. : Mixed ({up_count}/{total} Bull, {down_count}/{total} Bear){RESET}")

    for line in trend_summary_lines:
        logger.info(f"  {line}")

    logger.info(f"{NEON_BLUE}--------------------------------------{RESET}")


# --- Main Loop Helper Functions ---
def get_spread_bps(orderbook: dict) -> float:
    """Calculates the bid-ask spread in basis points (bps)."""
    try:
        best_ask = Decimal(orderbook["a"][0][0])
        best_bid = Decimal(orderbook["b"][0][0])
        if best_bid.is_zero() or best_ask.is_zero(): return 0.0 # Avoid division by zero
        mid = (best_ask + best_bid) / 2
        return float((best_ask - best_bid) / mid * 10000)
    except Exception as e:
        # print(f"Error calculating spread: {e}") # Use logger in actual bot
        return 0.0

def expected_value(perf_tracker: PerformanceTracker, n: int = 50, fee_bps: float = 2.0, slip_bps: float = 2.0) -> float:
    """Calculates a simple expected value based on recent trades."""
    trades = perf_tracker.trades[-n:]
    if not trades or len(trades) < 10: return 1.0 # Default to positive if no sufficient history
    
    wins_pnl = [t["pnl_net"] for t in trades if t["pnl_net"] > 0]
    losses_pnl = [abs(t["pnl_net"]) for t in trades if t["pnl_net"] <= 0] # Abs for average loss calc
    
    total_trades_considered = len(trades)
    win_rate = (len(wins_pnl) / total_trades_considered) if total_trades_considered > 0 else 0.0
    
    avg_win = (sum(wins_pnl) / len(wins_pnl)) if wins_pnl else Decimal("0")
    avg_loss = (sum(losses_pnl) / len(losses_pnl)) if losses_pnl else Decimal("0")
    
    # Costs are already factored into pnl_net in PerformanceTracker, so don't double count
    # However, if 'fees' and 'slippage' are conceptual filters, you might re-evaluate.
    # For a clean EV, we'd use raw pnl and apply fees/slippage. But if pt.pnl_net already has it, we just use it.
    
    # A more robust EV might use gross PnL and then apply fees and slippage once for the EV calculation.
    # For now, let's assume `pnl_net` correctly represents post-cost PnL.
    
    # Expected Value = (Win Rate * Average Win) - (Loss Rate * Average Loss)
    ev = (Decimal(str(win_rate)) * avg_win) - (Decimal(str(1.0 - win_rate)) * avg_loss)
    
    return float(ev)

def in_allowed_session(cfg: dict) -> bool:
    """Checks if the current UTC time falls within allowed trading sessions."""
    sess = cfg.get("session_filter", {})
    if not sess.get("enabled", False): return True
    
    now_utc_time = datetime.now(TIMEZONE).time() # Get only the time part
    
    for window_start_str, window_end_str in sess.get("utc_allowed", []):
        start_time = datetime.strptime(window_start_str, "%H:%M").time()
        end_time = datetime.strptime(window_end_str, "%H:%M").time()
        
        # Handle overnight sessions (e.g., 22:00 - 06:00)
        if start_time <= end_time:
            if start_time <= now_utc_time <= end_time:
                return True
        else: # Overnight session
            if now_utc_time >= start_time or now_utc_time <= end_time:
                return True
    return False

def adapt_exit_params(perf_tracker: PerformanceTracker, cfg: dict) -> Tuple[Decimal, Decimal]:
    """Dynamically adapts TP/SL multiples based on recent performance (experimental)."""
    tp_mult = Decimal(str(cfg["trade_management"]["take_profit_atr_multiple"]))
    sl_mult = Decimal(str(cfg["trade_management"]["stop_loss_atr_multiple"]))
    
    recent_trades = perf_tracker.trades[-100:]
    if not recent_trades or len(recent_trades) < 20: # Need sufficient trade history
        return tp_mult, sl_mult
    
    wins = [t for t in recent_trades if t["pnl_net"] > 0]
    losses = [t for t in recent_trades if t["pnl_net"] <= 0]
    
    if wins and losses:
        # Average net PnL for wins and losses
        avg_win_pnl = sum(t["pnl_net"] for t in wins) / len(wins)
        avg_loss_pnl = abs(sum(t["pnl_net"] for t in losses) / len(losses)) # Absolute value for avg loss

        if avg_loss_pnl > 0:
            risk_reward_ratio = avg_win_pnl / avg_loss_pnl
            # Adjust TP/SL based on RR. If RR > 1, favor higher TP/tighter SL. If RR < 1, do opposite.
            # 'tilt' is a factor to adjust multiples.
            tilt = Decimal(min(0.5, max(-0.5, float(risk_reward_ratio - 1.0))))
            
            new_tp_mult = tp_mult + tilt
            new_sl_mult = max(Decimal("1.0"), sl_mult - tilt / 2) # Prevent SL from becoming too small
            
            return new_tp_mult, new_sl_mult
    
    return tp_mult, sl_mult

def random_tune_weights(cfg_path: str = "config.json", k: int = 50, jitter: float = 0.2):
    """
    (Experimental) Randomly perturbs indicator weights to find a potentially better set.
    This is a simplistic optimization and should be used with caution, ideally offline.
    """
    print(f"{NEON_PURPLE}Running random weight tuning (k={k}, jitter={jitter})...{RESET}")
    try:
        with Path(cfg_path).open("r", encoding="utf-8") as f:
            cfg = json.load(f)
        
        base_weights = cfg["weight_sets"]["default_scalping"]
        best_cfg = base_weights.copy()
        best_proxy_score = -float('inf') # Placeholder for a proxy performance metric

        # Simple proxy score: sum of key trend-following weights
        # In a real scenario, this would be an actual backtest performance metric.
        def calculate_proxy_score(weights):
            return sum(weights.get(x, 0) for x in ["ema_alignment", "ehlers_supertrend_alignment", "macd_alignment", "adx_strength", "mtf_trend_confluence"])

        initial_proxy_score = calculate_proxy_score(base_weights)
        best_proxy_score = initial_proxy_score
        
        for iteration in range(k):
            trial_weights = {key: max(0.0, v * (Decimal("1") + Decimal(str(random.uniform(-jitter, jitter))))) for key,v in base_weights.items()}
            trial_proxy_score = calculate_proxy_score(trial_weights)

            if trial_proxy_score > best_proxy_score:
                best_cfg = {k: float(v) for k, v in trial_weights.items()} # Convert Decimals to float for JSON
                best_proxy_score = trial_proxy_score
                print(f"{NEON_BLUE}Iteration {iteration+1}: Found new best proxy score: {best_proxy_score:.2f}{RESET}")

        cfg["weight_sets"]["default_scalping"] = best_cfg
        with Path(cfg_path).open("w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)
        print(f"{NEON_GREEN}New weights (best proxy score: {best_proxy_score:.2f}) saved to {cfg_path}{RESET}")
        return best_cfg
    except Exception as e:
        print(f"{NEON_RED}Error during weight tuning: {e}{RESET}")
        return {}


def build_partial_tp_targets(
    side: Literal["BUY", "SELL"],
    entry_price: Decimal,
    atr_value: Decimal,
    total_qty: Decimal,
    cfg: dict,
    qty_step: Decimal,
    price_precision: int,
    link_prefix: str,
) -> list[dict]:
    """
    Builds a list of partial Take Profit order payloads based on config.
    """
    ex = cfg["execution"]
    tp_scheme = ex["tp_scheme"]
    
    out = []
    current_total_qty_allocated = Decimal("0")

    for i, t in enumerate(tp_scheme["targets"], start=1):
        # Calculate quantity for this target
        target_qty_raw = total_qty * Decimal(str(t["size_pct"]))
        qty = round_qty(target_qty_raw, qty_step)
        
        if qty <= 0:
            continue
        
        # Calculate price for this target
        price = Decimal("0")
        if tp_scheme["mode"] == "atr_multiples":
            price = (
                entry_price + atr_value * Decimal(str(t["atr_multiple"]))
                if side == "BUY"
                else entry_price - atr_value * Decimal(str(t["atr_multiple"]))
            )
        elif tp_scheme["mode"] == "percent":
            price_pct = Decimal(str(t.get("percent", 1))) / 100
            price = (
                entry_price * (Decimal("1") + price_pct)
                if side == "BUY"
                else entry_price * (Decimal("1") - price_pct)
            )
        
        # Ensure price is valid and not crossing entry (for TP)
        if (side == "BUY" and price <= entry_price) or (side == "SELL" and price >= entry_price):
            continue # Invalid TP target (below entry for buy, above for sell)

        final_price = round_price(price, price_precision)
        
        # Adjust TimeInForce to Bybit's API format
        tif = t.get("tif", ex.get("default_time_in_force"))
        if tif == "GoodTillCancel": tif = "GTC"
        elif tif == "ImmediateOrCancel": tif = "IOC"
        elif tif == "FillOrKill": tif = "FOK"
        elif tif == "PostOnly": tif = "PostOnly" # Pybit API often uses this string directly

        out.append(
            {
                "name": t.get("name", f"TP{i}"),
                "price": final_price,
                "qty": qty,
                "order_type": t.get("order_type", "Limit"),
                "tif": tif,
                "post_only": bool(t.get("post_only", ex.get("post_only_default", False))),
                "order_link_id": f"{link_prefix}_tp{i}", # Unique link ID for each TP
            }
        )
        current_total_qty_allocated += qty

    # Optionally, adjust the last TP quantity to absorb any rounding differences
    # if total_qty - current_total_qty_allocated > qty_step:
    #     if out:
    #         out[-1]["qty"] += (total_qty - current_total_qty_allocated)
    #         out[-1]["qty"] = round_qty(out[-1]["qty"], qty_step)

    return out


# --- Main Execution Logic ---
def main() -> None:
    """Orchestrates the bot's operation."""
    logger = setup_logger("wgwhalex_bot")
    config = load_config(CONFIG_FILE, logger)
    alert_system = AlertSystem(logger)

    # Validate interval formats at startup
    valid_bybit_intervals = ["1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D", "W", "M"]
    if config["interval"] not in valid_bybit_intervals:
        logger.error(f"{NEON_RED}Invalid primary interval '{config['interval']}' in config.json. Please use Bybit's valid string formats (e.g., '15', '60', 'D'). Exiting.{RESET}")
        sys.exit(1)
    for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
        if htf_interval not in valid_bybit_intervals:
            logger.error(f"{NEON_RED}Invalid higher timeframe interval '{htf_interval}' in config.json. Please use Bybit's valid string formats (e.g., '60', '240'). Exiting.{RESET}")
            sys.exit(1)

    logger.info(f"{NEON_GREEN}--- Wgwhalex Trading Bot Initialized ---{RESET}")
    logger.info(f"Symbol: {config['symbol']}, Interval: {config['interval']}")
    logger.info(f"Live Trading Enabled: {config['execution']['use_pybit']}")
    logger.info(f"Trade Management Enabled: {config['trade_management']['enabled']}")

    pybit_client = PybitTradingClient(config, logger)
    
    # Set leverage once on startup if live trading is enabled
    if pybit_client.enabled:
        leverage_set = pybit_client.set_leverage(
            config["symbol"],
            config["execution"]["buy_leverage"],
            config["execution"]["sell_leverage"],
        )
        if leverage_set:
            logger.info(f"{NEON_GREEN}Leverage set successfully: Buy {config['execution']['buy_leverage']}x, Sell {config['execution']['sell_leverage']}x{RESET}")
        else:
            logger.error(f"{NEON_RED}Failed to set leverage. Check API permissions or account status.{RESET}")
            if config["execution"]["use_pybit"]: # Critical for live trading
                alert_system.send_alert(f"Failed to set leverage for {config['symbol']}. Check API settings.", "ERROR")
                # Consider exiting or entering a safe mode here. For now, continue but log errors.

    position_manager = PositionManager(config, logger, config["symbol"], pybit_client)
    performance_tracker = PerformanceTracker(logger, config)
    
    # Initialize live sync components if enabled
    exec_sync = None
    heartbeat = None
    if config["execution"]["live_sync"]["enabled"] and pybit_client.enabled:
        exec_sync = ExchangeExecutionSync(
            config["symbol"], pybit_client, logger, config, position_manager, performance_tracker
        )
        heartbeat = PositionHeartbeat(
            config["symbol"], pybit_client, logger, config, position_manager
        )

    while True:
        try:
            logger.info(f"{NEON_PURPLE}--- New Analysis Loop Started ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}) ---{RESET}")
            
            # --- GUARDRAILS & FILTERS ---
            guard = config.get("risk_guardrails", {})
            if guard.get("enabled", False):
                # Using a 'safe' estimate for equity for guardrails, either from actual balance or config
                current_account_balance = position_manager._get_current_balance()
                equity = current_account_balance + performance_tracker.total_pnl # Use total PnL from start of bot
                
                day_loss = performance_tracker.day_pnl()
                max_day_loss = (Decimal(str(guard.get("max_day_loss_pct", 3.0))) / 100) * equity
                max_dd = (Decimal(str(guard.get("max_drawdown_pct", 8.0))) / 100) * equity
                
                if (max_day_loss > 0 and day_loss <= -max_day_loss) or (performance_tracker.max_drawdown >= max_dd):
                    logger.critical(f"{NEON_RED}KILL SWITCH ACTIVATED: Risk limits hit. Day PnL: {day_loss.normalize():.2f}, Max Day Loss: {max_day_loss.normalize():.2f}. Max Drawdown: {performance_tracker.max_drawdown.normalize():.2f}, Max Allowed Drawdown: {max_dd.normalize():.2f}. Cooling down.{RESET}")
                    alert_system.send_alert(f"KILL SWITCH: Risk limits hit for {config['symbol']}. Cooling down.", "ERROR")
                    time.sleep(int(guard.get("cooldown_after_kill_min", 120)) * 60) # Longer cooldown
                    continue # Skip to next loop iteration after cooldown

            if not in_allowed_session(config):
                logger.info(f"{NEON_BLUE}Outside allowed trading session. Holding.{RESET}")
                time.sleep(config["loop_delay"])
                continue

            # --- DATA FETCHING ---
            current_price = pybit_client.fetch_current_price(config["symbol"])
            if current_price is None:
                alert_system.send_alert(f"[{config['symbol']}] Failed to fetch current price. Skipping loop.", "WARNING")
                time.sleep(config["loop_delay"])
                continue
            
            df = pybit_client.fetch_klines(config["symbol"], config["interval"], 1000)
            if df is None or df.empty:
                alert_system.send_alert(f"[{config['symbol']}] Failed to fetch primary klines or DataFrame is empty. Skipping loop.", "WARNING")
                time.sleep(config["loop_delay"])
                continue

            orderbook_data = None
            if config["indicators"].get("orderbook_imbalance", False):
                orderbook_data = pybit_client.fetch_orderbook(config["symbol"], config["orderbook_limit"])
                if orderbook_data is None:
                    logger.warning(f"{NEON_YELLOW}Failed to fetch orderbook data.{RESET}")

            if guard.get("enabled", False) and orderbook_data:
                spread_bps = get_spread_bps(orderbook_data)
                if spread_bps > float(guard.get("spread_filter_bps", 5.0)):
                    logger.warning(f"{NEON_YELLOW}Spread too high ({spread_bps:.1f} bps). Holding.{RESET}")
                    time.sleep(config["loop_delay"])
                    continue
            
            if guard.get("ev_filter_enabled", True):
                current_ev = expected_value(performance_tracker)
                if current_ev <= 0:
                    logger.warning(f"{NEON_YELLOW}Negative Expected Value ({current_ev:.2f}) detected based on recent trades. Holding.{RESET}")
                    time.sleep(config["loop_delay"])
                    continue

            # --- ADAPTIVE PARAMETERS ---
            # Dynamically adjust TP/SL multiples based on recent performance
            tp_mult_adapted, sl_mult_adapted = adapt_exit_params(performance_tracker, config)
            config["trade_management"]["take_profit_atr_multiple"] = float(tp_mult_adapted)
            config["trade_management"]["stop_loss_atr_multiple"] = float(sl_mult_adapted)

            # --- MTF ANALYSIS ---
            mtf_trends: dict[str, str] = {}
            if config["mtf_analysis"]["enabled"]:
                for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
                    logger.debug(f"Fetching klines for MTF interval: {htf_interval}")
                    htf_df = pybit_client.fetch_klines(config["symbol"], htf_interval, 1000)
                    if htf_df is not None and not htf_df.empty:
                        for trend_ind in config["mtf_analysis"]["trend_indicators"]:
                            # Use the shared indicator function
                            trend = indicators._get_mtf_trend(htf_df, config, logger, config["symbol"], trend_ind)
                            mtf_trends[f"{htf_interval}_{trend_ind}"] = trend
                            logger.debug(f"MTF Trend ({htf_interval}, {trend_ind}): {trend}")
                    else:
                        logger.warning(f"{NEON_YELLOW}Could not fetch klines for higher timeframe {htf_interval} or it was empty. Skipping MTF trend for this TF.{RESET}")
                    time.sleep(config["mtf_analysis"]["mtf_request_delay_seconds"]) # Delay between MTF requests

            # --- ANALYSIS & SIGNAL GENERATION ---
            analyzer = TradingAnalyzer(df, config, logger, config["symbol"])
            if analyzer.df.empty:
                alert_system.send_alert(f"[{config['symbol']}] TradingAnalyzer DataFrame is empty after indicator calculations. Cannot generate signal.", "WARNING")
                time.sleep(config["loop_delay"])
                continue
            
            atr_value = Decimal(str(analyzer._get_indicator_value("ATR", Decimal("0.1"))))
            # Store last ATR for breakeven logic in ExchangeExecutionSync
            config["_last_atr_value"] = str(atr_value)

            trading_signal, signal_score, signal_breakdown = analyzer.generate_trading_signal(current_price, orderbook_data, mtf_trends)

            # --- Display Current State ---
            display_indicator_values_and_price(config, logger, current_price, analyzer, orderbook_data, mtf_trends, signal_breakdown)

            # --- POSITION MANAGEMENT ---
            # Update trailing stops for existing simulated positions
            for pos in position_manager.get_open_positions():
                position_manager.trail_stop(pos, current_price, atr_value)
            
            # Manage (close) simulated positions based on SL/TP hits
            position_manager.manage_positions(current_price, performance_tracker)

            # Attempt to pyramid on simulated positions if conditions met
            position_manager.try_pyramid(current_price, atr_value)

            # --- EXECUTION ---
            if trading_signal in ("BUY", "SELL"):
                # Calculate conviction based on signal strength (0 to 1, or scaled)
                # Max conviction = 1 if abs(signal_score) >= threshold * 2
                # Min conviction = 0 if abs(signal_score) == threshold
                conviction = float(min(1.0, max(0.0, (abs(signal_score) - config["signal_score_threshold"]) / config["signal_score_threshold"])))
                if conviction < 0.1: conviction = 0.1 # Ensure a minimum conviction if signal is valid
                
                if abs(signal_score) >= config["signal_score_threshold"]:
                    position_manager.open_position(trading_signal, current_price, atr_value, conviction)
                else:
                    logger.info(f"{NEON_BLUE}Signal below threshold ({config['signal_score_threshold']:.2f}). Holding. Score: {signal_score:.2f}{RESET}")
            else:
                logger.info(f"{NEON_BLUE}No strong trading signal. Holding. Score: {signal_score:.2f}{RESET}")

            # --- LIVE SYNC & HEARTBEAT (if enabled) ---
            if exec_sync:
                exec_sync.poll() # Process recent fills
            if heartbeat:
                heartbeat.tick() # Reconcile local vs exchange positions

            open_positions_summary = position_manager.get_open_positions()
            if open_positions_summary:
                logger.info(f"{NEON_CYAN}Open Positions: {len(open_positions_summary)}{RESET}")
                for pos in open_positions_summary:
                    logger.info(f"  - {pos['side']} {pos['qty'].normalize()} {pos['symbol']} @ {pos['entry_price'].normalize()} (SL: {pos['stop_loss'].normalize()}, TP: {pos['take_profit'].normalize()}, Adds: {pos['adds']}){RESET}")
            else:
                logger.info(f"{NEON_CYAN}No open positions.{RESET}")

            perf_summary = performance_tracker.get_summary()
            logger.info(f"{NEON_YELLOW}Performance Summary: Total Net PnL: {perf_summary['total_pnl']}, Wins: {perf_summary['wins']}, Losses: {perf_summary['losses']}, Win Rate: {perf_summary['win_rate']}, Max Drawdown: {perf_summary['max_drawdown']}{RESET}")

            logger.info(f"{NEON_PURPLE}--- Analysis Loop Finished. Waiting {config['loop_delay']}s ---{RESET}")
            time.sleep(config["loop_delay"])

        except Exception as e:
            alert_system.send_alert(f"[{config['symbol']}] An unhandled error occurred in the main loop: {e}", "ERROR")
            logger.exception(f"{NEON_RED}Unhandled exception in main loop:{RESET}")
            time.sleep(config["loop_delay"] * 2) # Longer wait on error

if __name__ == "__main__":
    # Optional: Run weight tuning once on startup
    # random_tune_weights(CONFIG_FILE) # Uncomment to enable experimental weight tuning
    main()

```

---

### `indicators.py` (Separate Module)

```python
import numpy as np
import pandas as pd
from decimal import Decimal, ROUND_DOWN
from typing import Literal, Tuple, Dict, Any
import logging

# --- Constants for Indicators ---
MIN_DATA_POINTS_TR = 2
MIN_DATA_POINTS_SMOOTHER = 2
MIN_DATA_POINTS_OBV = 2
MIN_DATA_POINTS_PSAR = 2
MIN_DATA_POINTS_VOLATILITY = 2
MIN_DATA_POINTS_KAMA = 2
MIN_DATA_POINTS_SMOOTHER_INIT = 2 # For SuperSmoother initialization
MIN_CANDLESTICK_PATTERNS_BARS = 2 # For pattern detection, usually 2 for simple patterns

# --- Core Indicator Calculations ---

def calculate_sma(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculate Simple Moving Average (SMA)."""
    if len(df) < period:
        return pd.Series(np.nan, index=df.index)
    return df["close"].rolling(window=period).mean()

def calculate_ema(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculate Exponential Moving Average (EMA)."""
    if len(df) < period:
        return pd.Series(np.nan, index=df.index)
    return df["close"].ewm(span=period, adjust=False).mean()

def calculate_true_range(df: pd.DataFrame) -> pd.Series:
    """Calculate True Range (TR)."""
    if len(df) < MIN_DATA_POINTS_TR:
        return pd.Series(np.nan, index=df.index)
    high_low = df["high"] - df["low"]
    high_prev_close = (df["high"] - df["close"].shift()).abs()
    low_prev_close = (df["low"] - df["close"].shift()).abs()
    return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(
        axis=1
    )

def calculate_atr(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculate Average True Range (ATR)."""
    if len(df) < period:
        return pd.Series(np.nan, index=df.index)
    tr = calculate_true_range(df)
    return tr.ewm(span=period, adjust=False).mean()


def calculate_super_smoother(df: pd.DataFrame, series: pd.Series, period: int) -> pd.Series:
    """Apply Ehlers SuperSmoother filter to reduce lag and noise."""
    # Takes df for index alignment, but operates on 'series'
    if period <= 0 or len(series) < MIN_DATA_POINTS_SMOOTHER:
        return pd.Series(np.nan, index=df.index)

    series = pd.to_numeric(series, errors="coerce").dropna()
    if len(series) < MIN_DATA_POINTS_SMOOTHER_INIT:
        return pd.Series(np.nan, index=df.index)

    a1 = np.exp(-np.sqrt(2) * np.pi / period)
    b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / period)
    c1 = 1 - b1 + a1**2
    c2 = b1 - 2 * a1**2
    c3 = a1**2

    filt = pd.Series(0.0, index=series.index)
    if len(series) >= 1:
        filt.iloc[0] = series.iloc[0]
    if len(series) >= 2:
        filt.iloc[1] = (series.iloc[0] + series.iloc[1]) / 2

    for i in range(2, len(series)):
        filt.iloc[i] = (
            (c1 / 2) * (series.iloc[i] + series.iloc[i - 1])
            + c2 * filt.iloc[i - 1]
            - c3 * filt.iloc[i - 2]
        )
    return filt.reindex(df.index)


def calculate_ehlers_supertrend(
    df: pd.DataFrame,
    period: int,
    multiplier: float,
) -> pd.DataFrame | None:
    """Calculate SuperTrend using Ehlers SuperSmoother for price and volatility."""
    if len(df) < period * 3: # Needs sufficient data for smoothing and trend calculation
        return None

    df_copy = df.copy()

    hl2 = (df_copy["high"] + df_copy["low"]) / 2
    # Ensure smoothed_price is passed df for proper reindexing
    smoothed_price = calculate_super_smoother(df_copy, hl2, period)
    if smoothed_price.isnull().all():
        return None

    tr = calculate_true_range(df_copy)
    # Ensure smoothed_atr is passed df for proper reindexing
    smoothed_atr = calculate_super_smoother(df_copy, tr, period)
    if smoothed_atr.isnull().all():
        return None

    df_copy["smoothed_price"] = smoothed_price
    df_copy["smoothed_atr"] = smoothed_atr

    df_copy.dropna(subset=["smoothed_price", "smoothed_atr"], inplace=True)
    if df_copy.empty:
        return None

    upper_band = df_copy["smoothed_price"] + multiplier * df_copy["smoothed_atr"]
    lower_band = df_copy["smoothed_price"] - multiplier * df_copy["smoothed_atr"]

    direction = pd.Series(0, index=df_copy.index, dtype=int)
    supertrend = pd.Series(np.nan, index=df_copy.index)

    # Find the first valid index after smoothing and dropping NaNs
    first_valid_idx_loc = 0
    # Iterate until a non-NaN close price is found
    while first_valid_idx_loc < len(df_copy) and pd.isna(df_copy["close"].iloc[first_valid_idx_loc]):
        first_valid_idx_loc += 1
    
    if first_valid_idx_loc >= len(df_copy): # No valid data points left
        return None

    # Initialize the first valid supertrend value
    if df_copy["close"].iloc[first_valid_idx_loc] > upper_band.iloc[first_valid_idx_loc]:
        direction.iloc[first_valid_idx_loc] = 1
        supertrend.iloc[first_valid_idx_loc] = lower_band.iloc[first_valid_idx_loc]
    elif df_copy["close"].iloc[first_valid_idx_loc] < lower_band.iloc[first_valid_idx_loc]:
        direction.iloc[first_valid_idx_loc] = -1
        supertrend.iloc[first_valid_idx_loc] = upper_band.iloc[first_valid_idx_loc]
    else: # Price is within bands, initialize with lower band, neutral direction
        direction.iloc[first_valid_idx_loc] = 0
        supertrend.iloc[first_valid_idx_loc] = lower_band.iloc[first_valid_idx_loc]

    # Iterate through the rest of the DataFrame
    for i in range(first_valid_idx_loc + 1, len(df_copy)):
        prev_direction = direction.iloc[i - 1]
        prev_supertrend = supertrend.iloc[i - 1]
        curr_close = df_copy["close"].iloc[i]

        if prev_direction == 1:  # Previous was an UP trend
            if curr_close < prev_supertrend: # Price drops below previous ST
                direction.iloc[i] = -1 # Flip to DOWN
                supertrend.iloc[i] = upper_band.iloc[i] # New ST is current upper band
            else: # Continue UP trend
                direction.iloc[i] = 1
                supertrend.iloc[i] = max(lower_band.iloc[i], prev_supertrend) # New ST is max of current lower_band and prev_supertrend
        elif prev_direction == -1:  # Previous was a DOWN trend
            if curr_close > prev_supertrend: # Price rises above previous ST
                direction.iloc[i] = 1 # Flip to UP
                supertrend.iloc[i] = lower_band.iloc[i] # New ST is current lower band
            else: # Continue DOWN trend
                direction.iloc[i] = -1
                supertrend.iloc[i] = min(upper_band.iloc[i], prev_supertrend) # New ST is min of current upper_band and prev_supertrend
        else: # Undecided or initial state, check breakout
            if curr_close > upper_band.iloc[i]:
                direction.iloc[i] = 1
                supertrend.iloc[i] = lower_band.iloc[i]
            elif curr_close < lower_band.iloc[i]:
                direction.iloc[i] = -1
                supertrend.iloc[i] = upper_band.iloc[i]
            else: # Still within bands or no clear breakout
                direction.iloc[i] = prev_direction # Maintain previous direction
                supertrend.iloc[i] = prev_supertrend # Maintain previous supertrend

    result = pd.DataFrame({"supertrend": supertrend, "direction": direction})
    return result.reindex(df.index)


def calculate_macd(
    df: pd.DataFrame,
    fast_period: int,
    slow_period: int,
    signal_period: int,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate Moving Average Convergence Divergence (MACD)."""
    if len(df) < slow_period + signal_period:
        return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

    ema_fast = df["close"].ewm(span=fast_period, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow_period, adjust=False).mean()

    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram


def calculate_rsi(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculate Relative Strength Index (RSI)."""
    if len(df) <= period:
        return pd.Series(np.nan, index=df.index)
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.ewm(span=period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(span=period, adjust=False, min_periods=period).mean()

    # Handle division by zero for rs where avg_loss is 0
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_stoch_rsi(
    df: pd.DataFrame,
    period: int,
    k_period: int,
    d_period: int,
) -> Tuple[pd.Series, pd.Series]:
    """Calculate Stochastic RSI."""
    if len(df) <= period:
        return pd.Series(np.nan, index=df.index), pd.Series(
            np.nan, index=df.index
        )
    rsi = calculate_rsi(df, period)
    if rsi.isnull().all(): # If base RSI is all NaN, StochRSI will also be.
        return pd.Series(np.nan, index=df.index), pd.Series(np.nan, index=df.index)

    lowest_rsi = rsi.rolling(window=period, min_periods=period).min()
    highest_rsi = rsi.rolling(window=period, min_periods=period).max()

    # Avoid division by zero if highest_rsi == lowest_rsi
    denominator = highest_rsi - lowest_rsi
    denominator[denominator == 0] = np.nan
    stoch_rsi_k_raw = ((rsi - lowest_rsi) / denominator) * 100
    stoch_rsi_k_raw = stoch_rsi_k_raw.fillna(0).clip(0, 100) # Clip and fill

    stoch_rsi_k = (
        stoch_rsi_k_raw.rolling(window=k_period, min_periods=k_period)
        .mean()
        .fillna(0)
    )
    stoch_rsi_d = (
        stoch_rsi_k.rolling(window=d_period, min_periods=d_period).mean()
        .fillna(0)
    )

    return stoch_rsi_k, stoch_rsi_d


def calculate_adx(df: pd.DataFrame, period: int) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate Average Directional Index (ADX)."""
    if len(df) < period * 2: # Requires True Range and smoothed DM for two 'period' lengths
        return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

    # True Range
    tr = calculate_true_range(df)
    if tr.isnull().all():
        return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

    # Directional Movement
    plus_dm = df["high"].diff()
    minus_dm = -df["low"].diff()

    plus_dm_final = pd.Series(0.0, index=df.index)
    minus_dm_final = pd.Series(0.0, index=df.index)

    # Apply +DM and -DM logic
    for i in range(1, len(df)):
        if plus_dm.iloc[i] > minus_dm.iloc[i] and plus_dm.iloc[i] > 0:
            plus_dm_final.iloc[i] = plus_dm.iloc[i]
        if minus_dm.iloc[i] > plus_dm.iloc[i] and minus_dm.iloc[i] > 0:
            minus_dm_final.iloc[i] = minus_dm.iloc[i]

    # Smoothed True Range, +DM, -DM
    atr = tr.ewm(span=period, adjust=False).mean()
    # Handle potential division by zero for atr
    plus_di = (plus_dm_final.ewm(span=period, adjust=False).mean() / atr.replace(0, np.nan)) * 100
    minus_di = (minus_dm_final.ewm(span=period, adjust=False).mean() / atr.replace(0, np.nan)) * 100

    # DX
    di_diff = abs(plus_di - minus_di)
    di_sum = plus_di + minus_di
    # Handle division by zero
    dx = (di_diff / di_sum.replace(0, np.nan)).fillna(0) * 100

    # ADX
    adx = dx.ewm(span=period, adjust=False).mean()

    return adx, plus_di, minus_di


def calculate_bollinger_bands(
    df: pd.DataFrame,
    period: int,
    std_dev: float,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate Bollinger Bands."""
    if len(df) < period:
        return (
            pd.Series(np.nan, index=df.index),
            pd.Series(np.nan, index=df.index),
            pd.Series(np.nan, index=df.index),
        )
    middle_band = df["close"].rolling(window=period, min_periods=period).mean()
    std = df["close"].rolling(window=period, min_periods=period).std()
    upper_band = middle_band + (std * std_dev)
    lower_band = middle_band - (std * std_dev)
    return upper_band, middle_band, lower_band


def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """Calculate Volume Weighted Average Price (VWAP)."""
    if df.empty or "volume" not in df.columns or "close" not in df.columns:
        return pd.Series(np.nan, index=df.index)
    
    # Ensure volume is numeric and positive for meaningful calculations
    df_temp = df.copy()
    df_temp["volume"] = pd.to_numeric(df_temp["volume"], errors='coerce').fillna(0)
    df_temp = df_temp[df_temp["volume"] > 0]
    
    if df_temp.empty: # All volume was zero or NaN
        return pd.Series(np.nan, index=df.index)

    typical_price = (df_temp["high"] + df_temp["low"] + df_temp["close"]) / 3
    cumulative_tp_vol = (typical_price * df_temp["volume"]).cumsum()
    cumulative_vol = df_temp["volume"].cumsum()
    vwap = cumulative_tp_vol / cumulative_vol.replace(0, np.nan) # Handle zero cumulative volume
    return vwap.reindex(df.index) # Reindex back to original DataFrame's index


def calculate_cci(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculate Commodity Channel Index (CCI)."""
    if len(df) < period:
        return pd.Series(np.nan, index=df.index)
    tp = (df["high"] + df["low"] + df["close"]) / 3
    sma_tp = tp.rolling(window=period, min_periods=period).mean()
    mad = tp.rolling(window=period, min_periods=period).apply(
        lambda x: np.abs(x - x.mean()).mean(), raw=False
    )
    # Handle potential division by zero for mad
    cci = (tp - sma_tp) / (0.015 * mad.replace(0, np.nan))
    return cci


def calculate_williams_r(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculate Williams %R."""
    if len(df) < period:
        return pd.Series(np.nan, index=df.index)
    highest_high = df["high"].rolling(window=period, min_periods=period).max()
    lowest_low = df["low"].rolling(window=period, min_periods=period).min()
    # Handle division by zero
    denominator = highest_high - lowest_low
    wr = -100 * ((highest_high - df["close"]) / denominator.replace(0, np.nan))
    return wr


def calculate_ichimoku_cloud(
    df: pd.DataFrame,
    tenkan_period: int,
    kijun_period: int,
    senkou_span_b_period: int,
    chikou_span_offset: int,
) -> Tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """Calculate Ichimoku Cloud components."""
    # Requires sufficient lookback for all components and the offset
    required_len = max(tenkan_period, kijun_period, senkou_span_b_period) + chikou_span_offset
    if len(df) < required_len:
        return (
            pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan),
            pd.Series(np.nan), pd.Series(np.nan),
        )

    tenkan_sen = (
        df["high"].rolling(window=tenkan_period).max()
        + df["low"].rolling(window=tenkan_period).min()
    ) / 2

    kijun_sen = (
        df["high"].rolling(window=kijun_period).max()
        + df["low"].rolling(window=kijun_period).min()
    ) / 2

    senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun_period)

    senkou_span_b = (
        (
            df["high"].rolling(window=senkou_span_b_period).max()
            + df["low"].rolling(window=senkou_span_b_period).min()
        )
        / 2
    ).shift(kijun_period)

    chikou_span = df["close"].shift(-chikou_span_offset) # Shifted into the future relative to current candle

    return tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span


def calculate_mfi(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculate Money Flow Index (MFI)."""
    if len(df) <= period:
        return pd.Series(np.nan, index=df.index)
    
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    money_flow = typical_price * df["volume"]

    positive_flow = pd.Series(0.0, index=df.index)
    negative_flow = pd.Series(0.0, index=df.index)

    # Calculate positive and negative money flow using vectorized operations
    price_diff = typical_price.diff()
    positive_flow = money_flow.where(price_diff > 0, 0)
    negative_flow = money_flow.where(price_diff < 0, 0)

    # Rolling sum for period
    positive_mf_sum = positive_flow.rolling(window=period, min_periods=period).sum()
    negative_mf_sum = negative_flow.rolling(window=period, min_periods=period).sum()

    # Avoid division by zero by replacing 0 with NaN
    mf_ratio = positive_mf_sum / negative_mf_sum.replace(0, np.nan)
    mfi = 100 - (100 / (1 + mf_ratio))
    return mfi


def calculate_obv(df: pd.DataFrame, ema_period: int) -> Tuple[pd.Series, pd.Series]:
    """Calculate On-Balance Volume (OBV) and its EMA."""
    if len(df) < MIN_DATA_POINTS_OBV:
        return pd.Series(np.nan), pd.Series(np.nan)

    obv_direction = np.sign(df["close"].diff().fillna(0))
    obv = (obv_direction * df["volume"]).cumsum()

    obv_ema = obv.ewm(span=ema_period, adjust=False).mean()

    return obv, obv_ema


def calculate_cmf(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculate Chaikin Money Flow (CMF)."""
    if len(df) < period:
        return pd.Series(np.nan)

    # Money Flow Multiplier (MFM)
    high_low_range = df["high"] - df["low"]
    # Handle division by zero for high_low_range
    mfm = (
        (df["close"] - df["low"]) - (df["high"] - df["close"])
    ) / high_low_range.replace(0, np.nan)
    mfm = mfm.fillna(0) # Fill NaN from division by zero with 0

    # Money Flow Volume (MFV)
    mfv = mfm * df["volume"]

    # CMF
    volume_sum = df["volume"].rolling(window=period).sum()
    # Handle division by zero for volume_sum
    cmf = mfv.rolling(window=period).sum() / volume_sum.replace(0, np.nan)
    cmf = cmf.fillna(0) # Fill NaN from division by zero with 0

    return cmf


def calculate_psar(
    df: pd.DataFrame,
    acceleration: float,
    max_acceleration: float,
) -> Tuple[pd.Series, pd.Series]:
    """Calculate Parabolic SAR."""
    if len(df) < MIN_DATA_POINTS_PSAR:
        return pd.Series(np.nan, index=df.index), pd.Series(
            np.nan, index=df.index
        )

    psar = df["close"].copy()
    bull = pd.Series(True, index=df.index) # True for bullish trend, False for bearish
    af = acceleration # Acceleration Factor
    
    # Initialize EP (Extreme Point) based on the first two bars to guess initial trend
    if len(df) >= 2:
        if df["close"].iloc[0] < df["close"].iloc[1]: # Price rising, assume bullish start
            ep = df["high"].iloc[0]
            bull.iloc[0] = True
        else: # Price falling, assume bearish start
            ep = df["low"].iloc[0]
            bull.iloc[0] = False
    else: # Not enough data for robust initialization, default to some values
        ep = df["high"].iloc[0] if len(df) > 0 else 0.0 # Fallback
        bull.iloc[0] = True

    # Main PSAR calculation loop
    for i in range(1, len(df)):
        prev_bull = bull.iloc[i - 1]
        prev_psar = psar.iloc[i - 1]

        # Calculate current PSAR value
        if prev_bull:  # Bullish trend
            psar.iloc[i] = prev_psar + af * (ep - prev_psar)
        else:  # Bearish trend
            psar.iloc[i] = prev_psar - af * (prev_psar - ep)

        # Check for reversal conditions
        reverse = False
        if prev_bull and df["low"].iloc[i] < psar.iloc[i]: # Bull trend, but price broke below PSAR
            bull.iloc[i] = False  # Reverse to bearish
            reverse = True
        elif not prev_bull and df["high"].iloc[i] > psar.iloc[i]: # Bear trend, but price broke above PSAR
            bull.iloc[i] = True  # Reverse to bullish
            reverse = True
        else:
            bull.iloc[i] = prev_bull  # Continue previous trend

        # Update AF and EP
        if reverse:
            af = acceleration # Reset acceleration factor on reversal
            ep = df["high"].iloc[i] if bull.iloc[i] else df["low"].iloc[i] # New EP is current High/Low
            
            # Ensure PSAR does not cross price on reversal
            if bull.iloc[i]:  # If reversing to bullish, PSAR should be below current low
                psar.iloc[i] = min(df["low"].iloc[i], df["low"].iloc[i - 1])
            else:  # If reversing to bearish, PSAR should be above current high
                psar.iloc[i] = max(df["high"].iloc[i], df["high"].iloc[i - 1])

        elif bull.iloc[i]:  # Continuing bullish
            if df["high"].iloc[i] > ep: # If new high, update EP and accelerate AF
                ep = df["high"].iloc[i]
                af = min(af + acceleration, max_acceleration)
            # Keep PSAR below the lowest low of the last two bars during bullish trend
            psar.iloc[i] = min(psar.iloc[i], df["low"].iloc[i], df["low"].iloc[i - 1])
        else:  # Continuing bearish
            if df["low"].iloc[i] < ep: # If new low, update EP and accelerate AF
                ep = df["low"].iloc[i]
                af = min(af + acceleration, max_acceleration)
            # Keep PSAR above the highest high of the last two bars during bearish trend
            psar.iloc[i] = max(psar.iloc[i], df["high"].iloc[i], df["high"].iloc[i - 1])

    # Determine PSAR direction (1 for bullish, -1 for bearish)
    direction = pd.Series(0, index=df.index, dtype=int)
    direction[psar < df["close"]] = 1 # PSAR below close = Bullish
    direction[psar > df["close"]] = -1 # PSAR above close = Bearish

    return psar, direction


def calculate_fibonacci_levels(df: pd.DataFrame, window: int) -> Dict[str, Decimal] | None:
    """Calculate Fibonacci retracement levels based on a recent high-low swing."""
    if len(df) < window:
        return None

    recent_high = df["high"].iloc[-window:].max()
    recent_low = df["low"].iloc[-window:].min()

    diff = recent_high - recent_low

    if diff <= 0:  # Handle cases where high and low are the same or inverted
        return None

    fib_levels = {
        "0.0%": Decimal(str(recent_high)),
        "23.6%": Decimal(str(recent_high - 0.236 * diff)).quantize(
            Decimal("0.00001"), rounding=ROUND_DOWN
        ),
        "38.2%": Decimal(str(recent_high - 0.382 * diff)).quantize(
            Decimal("0.00001"), rounding=ROUND_DOWN
        ),
        "50.0%": Decimal(str(recent_high - 0.500 * diff)).quantize(
            Decimal("0.00001"), rounding=ROUND_DOWN
        ),
        "61.8%": Decimal(str(recent_high - 0.618 * diff)).quantize(
            Decimal("0.00001"), rounding=ROUND_DOWN
        ),
        "78.6%": Decimal(str(recent_high - 0.786 * diff)).quantize(
            Decimal("0.00001"), rounding=ROUND_DOWN
        ),
        "100.0%": Decimal(str(recent_low)),
    }
    return fib_levels


def calculate_fibonacci_pivot_points(df: pd.DataFrame) -> Dict[str, float] | None:
    """Calculate Fibonacci Pivot Points (Pivot, R1, R2, S1, S2)."""
    if df.empty or len(df) < 2:  # Need at least previous bar for pivot calculation
        return None

    # Use the previous full bar's High, Low, Close for calculation
    prev_high = df["high"].iloc[-2]
    prev_low = df["low"].iloc[-2]
    prev_close = df["close"].iloc[-2]

    # Ensure previous bar data is valid
    if pd.isna(prev_high) or pd.isna(prev_low) or pd.isna(prev_close):
        return None

    pivot = (prev_high + prev_low + prev_close) / 3

    # Calculate Resistance and Support Levels using Fibonacci ratios
    # These ratios are typically applied to the range (High - Low)
    range_prev = prev_high - prev_low

    # Check for zero range to avoid division/multiplication issues
    if range_prev <= 0:
        return {
            "pivot": pivot, "r1": pivot, "r2": pivot,
            "s1": pivot, "s2": pivot,
        }

    r1 = pivot + (range_prev * 0.382)
    r2 = pivot + (range_prev * 0.618)
    s1 = pivot - (range_prev * 0.382)
    s2 = pivot - (range_prev * 0.618)

    return {
        "pivot": pivot, "r1": r1, "r2": r2,
        "s1": s1, "s2": s2,
    }


def calculate_volatility_index(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculate a simple Volatility Index based on ATR normalized by price."""
    if len(df) < period or "ATR" not in df.columns or df["ATR"].isnull().all():
        # ATR must be pre-calculated
        return pd.Series(np.nan, index=df.index)

    normalized_atr = df["ATR"] / df["close"]
    volatility_index = normalized_atr.rolling(window=period).mean()
    return volatility_index


def calculate_vwma(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculate Volume Weighted Moving Average (VWMA)."""
    if len(df) < period or df["volume"].isnull().any():
        return pd.Series(np.nan, index=df.index)

    # Ensure volume is numeric and not zero for weighting
    valid_volume = pd.to_numeric(df["volume"], errors='coerce').replace(0, np.nan)
    
    # Calculate price * volume
    pv = df["close"] * valid_volume
    
    # Sum (price * volume) / Sum (volume) over the rolling window
    vwma = pv.rolling(window=period).sum() / valid_volume.rolling(window=period).sum()
    return vwma


def calculate_volume_delta(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculate Volume Delta, indicating buying vs selling pressure."""
    if len(df) < MIN_DATA_POINTS_VOLATILITY: # Needs at least 2 bars for open/close diff
        return pd.Series(np.nan, index=df.index)

    # Approximate buy/sell volume based on close relative to open
    buy_volume = df["volume"].where(df["close"] > df["open"], 0)
    sell_volume = df["volume"].where(df["close"] < df["open"], 0)

    # Rolling sum of buy/sell volume
    buy_volume_sum = buy_volume.rolling(window=period, min_periods=1).sum()
    sell_volume_sum = sell_volume.rolling(window=period, min_periods=1).sum()

    total_volume_sum = buy_volume_sum + sell_volume_sum
    # Avoid division by zero
    volume_delta = (buy_volume_sum - sell_volume_sum) / total_volume_sum.replace(0, np.nan)
    return volume_delta.fillna(0) # Fill NaN from division by zero with 0


def calculate_kaufman_ama(
    df: pd.DataFrame, period: int, fast_period: int, slow_period: int
) -> pd.Series:
    """Calculate Kaufman's Adaptive Moving Average (KAMA)."""
    if len(df) < period + slow_period: # Need enough data for initial ER and then smoothing
        return pd.Series(np.nan, index=df.index)

    close_prices = df["close"].values
    kama = np.full_like(close_prices, np.nan)

    # Efficiency Ratio (ER)
    # Price change over the period
    price_change = np.abs(close_prices[period:] - close_prices[:-period])
    # Volatility as sum of absolute differences
    volatility = pd.Series(close_prices).diff().abs().rolling(window=period).sum()
    volatility_values = volatility.values

    er = np.full_like(close_prices, np.nan)
    # Align ER with the corresponding 'current' bar
    er[period:] = np.where(volatility_values[period:] != 0, price_change / volatility_values[period:], 0)
    er = np.clip(er, 0, 1) # ER should be between 0 and 1

    # Smoothing Constant (SC)
    fast_alpha = 2 / (fast_period + 1)
    slow_alpha = 2 / (slow_period + 1)
    sc = (er * (fast_alpha - slow_alpha) + slow_alpha) ** 2

    # KAMA calculation
    # Initialize KAMA with the first valid close price where ER and SC are also valid
    first_valid_idx = period # ER and SC start being valid after 'period' bars
    while first_valid_idx < len(close_prices) and (np.isnan(close_prices[first_valid_idx]) or np.isnan(sc[first_valid_idx])):
        first_valid_idx += 1

    if first_valid_idx >= len(close_prices): # No valid starting point for KAMA
        return pd.Series(np.nan, index=df.index)

    kama[first_valid_idx] = close_prices[first_valid_idx]

    for i in range(first_valid_idx + 1, len(close_prices)):
        if not np.isnan(sc[i]) and not np.isnan(kama[i-1]):
            kama[i] = kama[i - 1] + sc[i] * (close_prices[i] - kama[i - 1])
        else:
            kama[i] = kama[i - 1] if not np.isnan(kama[i-1]) else close_prices[i] # If SC is NaN, hold previous KAMA value or use current close if previous KAMA also NaN

    return pd.Series(kama, index=df.index)


def calculate_relative_volume(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculate Relative Volume, comparing current volume to average volume."""
    if len(df) < period:
        return pd.Series(np.nan, index=df.index)

    avg_volume = df["volume"].rolling(window=period, min_periods=period).mean()
    # Avoid division by zero
    relative_volume = (df["volume"] / avg_volume.replace(0, np.nan)).fillna(1.0) # Default to 1 if no avg volume
    return relative_volume


def calculate_market_structure(df: pd.DataFrame, lookback_period: int) -> pd.Series:
    """Detects higher highs/lows or lower highs/lows over a lookback period. Returns 'UP', 'DOWN', or 'SIDEWAYS'."""
    if len(df) < lookback_period * 2: # Need enough data to compare two segments
        return pd.Series("SIDEWAYS", index=df.index, dtype="object") # Default if not enough data

    # Use only the most recent part of the DataFrame for this calculation
    recent_df = df.iloc[-lookback_period * 2:]

    if len(recent_df) < lookback_period * 2: # Still not enough after slicing
        return pd.Series("SIDEWAYS", index=df.index, dtype="object")

    # Divide into previous and current segments
    prev_segment_df = recent_df.iloc[:-lookback_period]
    current_segment_df = recent_df.iloc[-lookback_period:]

    # Find recent swing high and low within the current segment
    recent_segment_high = current_segment_df["high"].max()
    recent_segment_low = current_segment_df["low"].min()

    # Compare with previous segment's high/low
    prev_segment_high = prev_segment_df["high"].max()
    prev_segment_low = prev_segment_df["low"].min()

    trend = "SIDEWAYS"
    if (
        not pd.isna(recent_segment_high) and not pd.isna(recent_segment_low)
        and not pd.isna(prev_segment_high) and not pd.isna(prev_segment_low)
    ):
        is_higher_high = recent_segment_high > prev_segment_high
        is_higher_low = recent_segment_low > prev_segment_low
        is_lower_high = recent_segment_high < prev_segment_high
        is_lower_low = recent_segment_low < prev_segment_low

        if is_higher_high and is_higher_low:
            trend = "UP"
        elif is_lower_high and is_lower_low:
            trend = "DOWN"

    # Return a series where the last value is the detected trend
    result_series = pd.Series(trend, index=df.index, dtype="object")
    return result_series


def calculate_dema(df: pd.DataFrame, series: pd.Series, period: int) -> pd.Series:
    """Calculate Double Exponential Moving Average (DEMA)."""
    if len(series) < 2 * period:  # DEMA requires more data than simple EMA
        return pd.Series(np.nan, index=df.index)

    ema1 = series.ewm(span=period, adjust=False).mean()
    ema2 = ema1.ewm(span=period, adjust=False).mean()
    dema = 2 * ema1 - ema2
    return dema.reindex(df.index)


def calculate_keltner_channels(
    df: pd.DataFrame, period: int, atr_multiplier: float, atr_period: int
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate Keltner Channels."""
    # ATR is a dependency, ensure it's calculated or available
    if "ATR" not in df.columns or df["ATR"].isnull().all():
        df["ATR"] = calculate_atr(df, atr_period) # Calculate ATR if not present
        if df["ATR"].isnull().all():
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

    if len(df) < period or df["ATR"].isnull().all(): # Check if enough data for EMA/ATR
        return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

    ema = df["close"].ewm(span=period, adjust=False).mean()
    atr = df["ATR"] # Use the calculated ATR

    upper_band = ema + (atr * atr_multiplier)
    lower_band = ema - (atr * atr_multiplier)

    return upper_band, ema, lower_band


def calculate_roc(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculate Rate of Change (ROC)."""
    if len(df) < period + 1: # Need previous 'period' + 1 for current value
        return pd.Series(np.nan, index=df.index)

    # Handle potential division by zero
    roc = (
        (df["close"] - df["close"].shift(period))
        / df["close"].shift(period).replace(0, np.nan)
    ) * 100
    return roc


def detect_candlestick_patterns(df: pd.DataFrame) -> pd.Series:
    """Detects common candlestick patterns for the latest bar."""
    if len(df) < MIN_CANDLESTICK_PATTERNS_BARS: # Need at least two bars for most patterns
        return pd.Series("No Pattern", index=df.index, dtype="object")

    patterns = pd.Series("No Pattern", index=df.index, dtype="object")

    # Focus on the latest bar for efficiency in real-time processing
    i = len(df) - 1
    current_bar = df.iloc[i]
    prev_bar = df.iloc[i - 1]

    # Basic check for NaN values in current/previous bar to avoid errors
    if any(pd.isna(val) for val in [current_bar["open"], current_bar["close"], current_bar["high"], current_bar["low"],
                                    prev_bar["open"], prev_bar["close"], prev_bar["high"], prev_bar["low"]]):
        return patterns # Return default "No Pattern" if data is incomplete

    # Bullish Engulfing: Current bullish candle fully engulfs previous bearish candle
    if (current_bar["open"] < prev_bar["close"] and current_bar["close"] > prev_bar["open"] and
        current_bar["close"] > current_bar["open"] and prev_bar["close"] < prev_bar["open"]):
        patterns.iloc[i] = "Bullish Engulfing"
    # Bearish Engulfing: Current bearish candle fully engulfs previous bullish candle
    elif (current_bar["open"] > prev_bar["close"] and current_bar["close"] < prev_bar["open"] and
          current_bar["close"] < current_bar["open"] and prev_bar["close"] > prev_bar["open"]):
        patterns.iloc[i] = "Bearish Engulfing"
    # Hammer (Bullish): Small body at top, long lower shadow (at least 2x body), little/no upper shadow
    elif (current_bar["close"] > current_bar["open"] and # Bullish candle
          abs(current_bar["close"] - current_bar["open"]) <= (current_bar["high"] - current_bar["low"]) * 0.3 and # Small body (e.g., <30% of total range)
          (current_bar["open"] - current_bar["low"]) >= 2 * abs(current_bar["close"] - current_bar["open"]) and # Long lower shadow
          (current_bar["high"] - current_bar["close"]) <= 0.5 * abs(current_bar["close"] - current_bar["open"])): # Small upper shadow
        patterns.iloc[i] = "Bullish Hammer"
    # Shooting Star (Bearish): Small body at bottom, long upper shadow (at least 2x body), little/no lower shadow
    elif (current_bar["close"] < current_bar["open"] and # Bearish candle
          abs(current_bar["close"] - current_bar["open"]) <= (current_bar["high"] - current_bar["low"]) * 0.3 and # Small body
          (current_bar["high"] - current_bar["open"]) >= 2 * abs(current_bar["close"] - current_bar["open"]) and # Long upper shadow
          (current_bar["close"] - current_bar["low"]) <= 0.5 * abs(current_bar["close"] - current_bar["open"])): # Small lower shadow
        patterns.iloc[i] = "Bearish Shooting Star"

    return patterns


def _get_mtf_trend(higher_tf_df: pd.DataFrame, config: dict, logger: logging.Logger, symbol: str, indicator_type: str) -> str:
    """Determine trend from higher timeframe using specified indicator."""
    if higher_tf_df.empty:
        return "UNKNOWN"

    last_close = higher_tf_df["close"].iloc[-1]
    period = config["mtf_analysis"]["trend_period"]
    indicator_settings = config["indicator_settings"]

    # Use the shared indicator calculation functions
    if indicator_type == "sma":
        if len(higher_tf_df) < period:
            logger.debug(f"[{symbol}] MTF SMA: Not enough data for {period} period. Have {len(higher_tf_df)}.")
            return "UNKNOWN"
        sma = calculate_sma(higher_tf_df, period=period).iloc[-1]
        if last_close > sma: return "UP"
        if last_close < sma: return "DOWN"
        return "SIDEWAYS"
    elif indicator_type == "ema":
        if len(higher_tf_df) < period:
            logger.debug(f"[{symbol}] MTF EMA: Not enough data for {period} period. Have {len(higher_tf_df)}.")
            return "UNKNOWN"
        ema = calculate_ema(higher_tf_df, period=period).iloc[-1]
        if last_close > ema: return "UP"
        if last_close < ema: return "DOWN"
        return "SIDEWAYS"
    elif indicator_type == "ehlers_supertrend":
        st_result = calculate_ehlers_supertrend(
            df=higher_tf_df,
            period=indicator_settings["ehlers_slow_period"],
            multiplier=indicator_settings["ehlers_slow_multiplier"],
        )
        if st_result is not None and not st_result.empty:
            st_dir = st_result["direction"].iloc[-1]
            if st_dir == 1: return "UP"
            if st_dir == -1: return "DOWN"
        return "UNKNOWN"
    return "UNKNOWN"
```

---

### `alert_system.py` (Separate Module)

```python
# alert_system.py

import logging
import subprocess
from colorama import Fore, Style, init
from typing import Literal

# Initialize colorama
init(autoreset=True)

NEON_RED = Fore.LIGHTRED_EX
NEON_YELLOW = Fore.YELLOW
RESET = Style.RESET_ALL # Ensure RESET is defined for local use as well

class AlertSystem:
    """
    Handles sending alerts for critical bot events using Termux toast notifications.
    Requires Termux:API app to be installed and 'pkg install termux-api' to be run.
    """

    def __init__(self, logger: logging.Logger):
        """
        Initializes the AlertSystem.

        Args:
            logger: The logger instance to use for logging.
        """
        self.logger = logger
        self.termux_api_available = self._check_termux_api()

    def _check_termux_api(self) -> bool:
        """Checks if termux-toast command is available."""
        try:
            subprocess.run(['which', 'termux-toast'], check=True, capture_output=True, text=True)
            return True
        except subprocess.CalledProcessError:
            self.logger.warning(
                f"{NEON_YELLOW}The 'termux-toast' command was not found. "
                f"Termux toast notifications will be disabled. Please ensure Termux:API is installed and 'pkg install termux-api' has been run.{RESET}"
            )
            return False
        except FileNotFoundError:
            self.logger.warning(
                f"{NEON_YELLOW}The 'termux-toast' command was not found in PATH. "
                f"Termux toast notifications will be disabled. Please ensure Termux:API is installed and 'pkg install termux-api' has been run.{RESET}"
            )
            return False
        except Exception as e:
            self.logger.error(f"{NEON_RED}Unexpected error checking termux-toast availability: {e}{RESET}")
            return False

    def send_alert(self, message: str, level: Literal["INFO", "WARNING", "ERROR"] = "INFO"):
        """
        Sends an alert using termux-toast if available, and logs it.

        Args:
            message: The alert message to display.
            level: The severity level (e.g., "INFO", "WARNING", "ERROR").
                   This can be used to colorize the toast (if Termux:API supported) or logs.
        """
        # Log the alert message
        if level == "INFO":
            self.logger.info(f"{Fore.CYAN}ALERT [INFO]: {message}{RESET}")
        elif level == "WARNING":
            self.logger.warning(f"{Fore.YELLOW}ALERT [WARNING]: {message}{RESET}")
        elif level == "ERROR":
            self.logger.error(f"{Fore.RED}ALERT [ERROR]: {message}{RESET}")
        else:
            self.logger.info(f"ALERT [{level.upper()}]: {message}")

        # Send Termux toast notification if API is available
        if self.termux_api_available:
            try:
                # Add a prefix to the toast message to indicate severity visually
                toast_message_prefix = {
                    "INFO": "ℹ️ ",
                    "WARNING": "⚠️ ",
                    "ERROR": "⛔ ",
                }.get(level, "")
                
                subprocess.run(
                    ['termux-toast', f"{toast_message_prefix}{message}"],
                    check=False, # Do not raise exception for non-zero exit codes in toast, just log
                    capture_output=True,
                    text=True,
                    timeout=5 # Timeout in case toast hangs
                )
                self.logger.debug("Termux toast alert sent.")
            except subprocess.TimeoutExpired:
                self.logger.error(f"{NEON_RED}Termux toast command timed out.{RESET}")
            except Exception as e:
                self.logger.error(f"{NEON_RED}An error occurred while sending Termux toast: {e}{RESET}")
        else:
            self.logger.debug("Termux toast notifications are disabled.")

```

---

### How to Use:

1.  **Save the files:**
    *   Save the first large block of code as `unified_whalebot.py`.
    *   Save the second block of code as `indicators.py` in the **same directory** as `unified_whalebot.py`.
    *   Save the third block of code as `alert_system.py` in the **same directory** as `unified_whalebot.py`.
2.  **Create `.env` file:** In the same directory, create a file named `.env` and add your Bybit API Key and Secret:
    ```
    BYBIT_API_KEY=YOUR_BYBIT_API_KEY
    BYBIT_API_SECRET=YOUR_BYBIT_API_SECRET
    ```
3.  **Create `config.json` file:** In the same directory, a `config.json` will be created automatically on the first run if it doesn't exist. You can modify its settings directly.
4.  **Install dependencies:**
    ```bash
    pip install pandas numpy pybit-unified-trading colorama python-dotenv
    ```
5.  **For Termux Toast Alerts:**
    *   Install the `Termux:API` app from F-Droid or Play Store.
    *   In your Termux terminal, run: `pkg install termux-api`
6.  **Run the bot:**
    ```bash
    python unified_whalebot.py
    ```
