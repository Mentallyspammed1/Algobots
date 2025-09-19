import json
import logging
import os
import random
import sys
import time
import threading # Added for WebSocket
from datetime import datetime, timezone
from decimal import ROUND_DOWN, ROUND_UP, Decimal, getcontext
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, ClassVar, Literal, Optional, Dict, List, Tuple, Union

import indicators  # Import the new indicators module
import numpy as np
import pandas as pd
from alert_system import AlertSystem
from colorama import Fore, Style, init
from dotenv import dotenv_values

# Guarded import for the live trading client
try:
    import pybit.exceptions
    from pybit.unified_trading import HTTP as PybitHTTP
    from pybit.unified_trading import WebSocket
    from pybit.unified_trading import HTTP

    PYBIT_AVAILABLE = True
except ImportError:
    PYBIT_AVAILABLE = False
    print("Warning: pybit-unified-trading not installed. Live trading and WebSocket features will be disabled.")


# Initialize colorama and set decimal precision
getcontext().prec = 28
init(autoreset=True)

# --- Environment & API Key Loading ---
# Explicitly load .env values from the script's directory for robustness
script_dir = Path(__file__).resolve().parent
dotenv_path = script_dir / '.env'
config_env = dotenv_values(dotenv_path) if dotenv_path.exists() else {}

# --- Constants ---
API_KEY = config_env.get("BYBIT_API_KEY")
API_SECRET = config_env.get("BYBIT_API_SECRET")
BASE_URL = os.getenv("BYBIT_BASE_URL", "https://api.bybit.com")
CONFIG_FILE = "config.json"
LOG_DIRECTORY = "bot_logs/trading-bot/logs"
Path(LOG_DIRECTORY).mkdir(parents=True, exist_ok=True)

TIMEZONE = timezone.utc
MAX_API_RETRIES = 5
RETRY_DELAY_SECONDS = 7
REQUEST_TIMEOUT = 20
LOOP_DELAY_SECONDS = 15
WS_RECONNECT_DELAY = 10  # WebSocket reconnection delay

# Neon Color Scheme
NEON_GREEN = Fore.LIGHTGREEN_EX
NEON_BLUE = Fore.CYAN
NEON_PURPLE = Fore.MAGENTA
NEON_YELLOW = Fore.YELLOW
NEON_RED = Fore.LIGHTRED_EX
NEON_CYAN = Fore.CYAN
RESET = Style.RESET_ALL

# --- Helper Functions for Precision ---
def round_qty(qty: Decimal, qty_step: Decimal) -> Decimal:
    if qty_step is None or qty_step.is_zero():
        return qty.quantize(Decimal("1.000000"), rounding=ROUND_DOWN)
    return (qty // qty_step) * qty_step

def round_price(price: Decimal, price_precision: int) -> Decimal:
    if price_precision < 0:
        price_precision = 0
    return price.quantize(Decimal(f"1e-{price_precision}"), rounding=ROUND_DOWN)

def round_price_up(price: Decimal, price_precision: int) -> Decimal:
    if price_precision < 0:
        price_precision = 0
    return price.quantize(Decimal(f"1e-{price_precision}"), rounding=ROUND_UP)

# --- Configuration Management ---
def load_config(filepath: str, logger: logging.Logger) -> dict[str, Any]:
    default_config = {
        "symbol": "BTCUSDT", "interval": "15", "loop_delay": LOOP_DELAY_SECONDS,
        "orderbook_limit": 50, "signal_score_threshold": 2.0, "cooldown_sec": 60,
        "hysteresis_ratio": 0.85, "volume_confirmation_multiplier": 1.5,
        "trade_management": {
            "enabled": True, "account_balance": 1000.0, "risk_per_trade_percent": 1.0,
            "stop_loss_atr_multiple": 1.5, "take_profit_atr_multiple": 2.0,
            "max_open_positions": 1, "order_precision": 5, "price_precision": 3,
        },
        "risk_guardrails": {
            "enabled": True, "max_day_loss_pct": 3.0, "max_drawdown_pct": 8.0,
            "cooldown_after_kill_min": 120, "spread_filter_bps": 5.0, "ev_filter_enabled": True,
            "max_spread_bps": 10.0, "min_volume_usd": 50000, "max_slippage_bps": 5.0,
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
        },
        "indicators": {
            "ema_alignment": True, "sma_trend_filter": True, "momentum": True,
            "volume_confirmation": True, "stoch_rsi": True, "rsi": True, "bollinger_bands": True,
            "vwap": True, "cci": True, "wr": True, "psar": True, "sma_10": True, "mfi": True,
            "orderbook_imbalance": True, "fibonacci_levels": True, "ehlers_supertrend": True,
            "macd": True, "adx": True, "ichimoku_cloud": True, "obv": True, "cmf": True,
            "volatility_index": True, "vwma": True, "volume_delta": True,
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
                "fibonacci_confluence": 0.10, # New weight for Fibonacci
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
            "use_websocket": True,  # Enable WebSocket for real-time data
            "slippage_adjustment": True,  # Adjust orders for expected slippage
            "max_fill_time_ms": 5000,  # Max time to wait for order fill
            "dry_run": True, # New: Set to True for simulated trading without real orders
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
    for key, default_value in default_config.items():
        if key not in config:
            config[key] = default_value
        elif isinstance(default_value, dict) and isinstance(config.get(key), dict):
            _ensure_config_keys(config[key], default_value)

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

# --- WebSocket for Real-time Data ---
class BybitWebSocket:
    def __init__(self, symbol: str, category: str, logger: logging.Logger, testnet: bool):
        self.symbol = symbol
        self.category = category
        self.logger = logger
        self.testnet = testnet # Store testnet status
        self.ws = None
        self.connected = False
        self.orderbook_data = None
        self.trades_data = []
        self.last_price = None
        self._ws_thread = None # To hold the WebSocket thread
        self._lock = threading.Lock() # For thread-safe data access
        self.connect()

    def _run_websocket(self):
        try:
            self.logger.info(f"{NEON_BLUE}Starting WebSocket event loop for {self.symbol}...{RESET}")
            self.ws.run_forever()
        except Exception as e:
            self.logger.error(f"{NEON_RED}WebSocket thread error: {e}{RESET}")
        finally:
            with self._lock: # Ensure connected status update is thread-safe
                self.connected = False
            self.logger.warning(f"{NEON_YELLOW}WebSocket event loop stopped for {self.symbol}.{RESET}")

    def connect(self):
        if not PYBIT_AVAILABLE:
            self.logger.error(f"{NEON_RED}PyBit not available. WebSocket disabled.{RESET}")
            return
        if self.connected:
            self.logger.info(f"{NEON_YELLOW}WebSocket already connected, skipping reconnection.{RESET}")
            return

        try:
            self.ws = WebSocket(
                testnet=self.testnet,
                channel_type="public", # For public data streams like orderbook and trades
            )
            
            self.ws.orderbook_stream(
                symbol=self.symbol,
                category=self.category,
                depth=50,
                callback=self.handle_orderbook
            )
            
            self.ws.public_trade_stream(
                symbol=self.symbol,
                category=self.category,
                callback=self.handle_trades
            )
            
            self._ws_thread = threading.Thread(target=self._run_websocket, daemon=True)
            self._ws_thread.start()
            
            # Give a small moment for connection to establish
            time.sleep(1) 
            with self._lock:
                self.connected = True
            self.logger.info(f"{NEON_GREEN}WebSocket connection initiated for {self.symbol}{RESET}")
        except Exception as e:
            self.logger.error(f"{NEON_RED}WebSocket connection error: {e}{RESET}")
            with self._lock:
                self.connected = False

    def stop(self):
        if self.ws:
            self.logger.info(f"{NEON_YELLOW}Stopping WebSocket for {self.symbol}...{RESET}")
            self.ws.stop()
            if self._ws_thread and self._ws_thread.is_alive():
                self._ws_thread.join(timeout=5) # Wait for thread to finish
            with self._lock:
                self.connected = False
            self.logger.info(f"{NEON_YELLOW}WebSocket for {self.symbol} stopped.{RESET}")

    def handle_orderbook(self, message):
        try:
            # Pybit public WebSocket messages for orderbook directly contain 'data'
            # Example: {'topic': 'orderbook.50.BTCUSDT', 'data': {'s': 'BTCUSDT', 'b': [['26000.00', '1.5']], 'a': [['26001.00', '2.0']]}}
            if message and message.get('data'):
                with self._lock:
                    self.orderbook_data = message['data']
        except Exception as e:
            self.logger.error(f"{NEON_RED}Error handling orderbook data: {e}{RESET}")

    def handle_trades(self, message):
        try:
            # Pybit public WebSocket messages for trades directly contain 'data'
            if message and message.get('data'):
                with self._lock:
                    self.trades_data.extend(message['data'])
                    # Keep only the last 100 trades
                    self.trades_data = self.trades_data[-100:]
                    # Update last price from the most recent trade
                    if message['data']: # Ensure there's data before accessing
                        self.last_price = Decimal(str(message['data'][-1].get("p", "0")))
        except Exception as e:
            self.logger.error(f"{NEON_RED}Error handling trades data: {e}{RESET}")

    def reconnect(self):
        with self._lock:
            if not self.connected:
                self.logger.info(f"{NEON_YELLOW}Attempting to reconnect WebSocket...{RESET}")
                self.stop() # Ensure old connection is stopped
                time.sleep(WS_RECONNECT_DELAY)
                self.connect()

    def get_orderbook(self):
        with self._lock:
            if not self.connected:
                self.reconnect()
            return self.orderbook_data

    def get_last_price(self):
        with self._lock:
            if not self.connected:
                self.reconnect()
            return self.last_price

    def get_recent_trades(self, count=10):
        with self._lock:
            if not self.connected:
                self.reconnect()
            return self.trades_data[-count:] if self.trades_data else []

# --- API Interaction & Live Trading ---
class PybitTradingClient:
    def __init__(self, config: dict[str, Any], logger: logging.Logger):
        self.cfg = config
        self.logger = logger
        self.enabled = bool(config.get("execution", {}).get("use_pybit", False))
        self.dry_run = bool(config.get("execution", {}).get("dry_run", True)) # New: Dry run mode
        self.category = config.get("execution", {}).get("category", "linear")
        self.testnet = bool(config.get("execution", {}).get("testnet", False))
        self.session = None
        self.ws = None
        self.last_api_call_time = 0
        self.api_call_counter = 0 # Counter for API calls within a rate limit window
        self.rate_limit_window_start = 0 # Timestamp when current rate limit window started

        if not self.enabled:
            self.logger.info(f"{NEON_YELLOW}PyBit execution disabled.{RESET}")
            return
        
        if self.dry_run:
            self.logger.info(f"{NEON_YELLOW}PyBit client initialized in DRY RUN mode. No real orders will be placed.{RESET}")
        
        if not PYBIT_AVAILABLE:
            self.enabled = False
            self.logger.error(f"{NEON_RED}PyBit not installed. Live trading disabled.{RESET}")
            return
        
        if not API_KEY or not API_SECRET:
            self.enabled = False
            self.logger.error(f"{NEON_RED}API keys not found for PyBit. Live trading disabled.{RESET}")
            return

        proxies = {}
        if self.cfg.get("execution", {}).get("proxies", {}).get("enabled", False):
            proxies = {
                "http": self.cfg["execution"]["proxies"].get("http"),
                "https": self.cfg["execution"]["proxies"].get("https"),
            }
            self.logger.info(f"{NEON_BLUE}Proxy enabled.{RESET}")

        try:
            self.session = HTTP(
                api_key=API_KEY,
                api_secret=API_SECRET,
                testnet=self.testnet,
                timeout=REQUEST_TIMEOUT,
                proxies=proxies if proxies.get("http") or proxies.get("https") else None
            )
            
            # Initialize WebSocket if enabled
            if self.cfg.get("execution", {}).get("use_websocket", False):
                self.ws = BybitWebSocket(
                    symbol=self.cfg.get("symbol", "BTCUSDT"),
                    category=self.category,
                    logger=self.logger,
                    testnet=self.testnet # Pass testnet status
                )
            
            if not self.dry_run:
                self.logger.info(f"{NEON_GREEN}PyBit client initialized. Testnet={self.testnet}{RESET}")
        except (pybit.exceptions.FailedRequestError, Exception) as e:
            self.enabled = False
            self.logger.error(f"{NEON_RED}Failed to init PyBit client: {e}{RESET}")

    def _check_rate_limit(self, max_calls_per_minute=50): # Bybit public endpoints are ~100-200, private ~50-100
        """Check API rate limits and wait if necessary."""
        if self.dry_run: return # No rate limits in dry run

        current_time = time.time()
        
        # Reset counter if a new minute has started
        if current_time - self.rate_limit_window_start >= 60:
            self.api_call_counter = 0
            self.rate_limit_window_start = current_time
        
        # If we've exceeded the limit for the current minute, wait
        if self.api_call_counter >= max_calls_per_minute:
            wait_time = (self.rate_limit_window_start + 60) - current_time + 1 # Wait until next minute + 1s buffer
            self.logger.warning(f"{NEON_YELLOW}Rate limit reached ({self.api_call_counter}/{max_calls_per_minute} calls/min). Waiting {wait_time:.1f} seconds.{RESET}")
            time.sleep(wait_time)
            self.api_call_counter = 0 # Reset after waiting
            self.rate_limit_window_start = time.time() # Start new window

    def _make_api_call(self, func, *args, **kwargs):
        """Wrapper for API calls with rate limiting and retry logic"""
        if self.dry_run:
            self.logger.info(f"{NEON_BLUE}DRY RUN: Simulating API call to {func.__name__} with args={args}, kwargs={kwargs}{RESET}")
            # Simulate a successful response for dry run
            # The structure of the simulated response should match what the caller expects
            if func.__name__ == "get_positions":
                return {"retCode": 0, "retMsg": "Dry run success", "result": {"list": []}}
            elif func.__name__ == "get_wallet_balance":
                return {"retCode": 0, "retMsg": "Dry run success", "result": {"list": [{"coin": [{"coin": "USDT", "walletBalance": str(self.cfg['trade_management']['account_balance'])}]}]}}
            elif func.__name__ == "get_tickers":
                # Simulate a price based on config or a dummy value
                return {"retCode": 0, "retMsg": "Dry run success", "result": {"list": [{"lastPrice": "30000"}]}}
            elif func.__name__ == "get_instruments_info":
                # Simulate instrument info for precision
                return {"retCode": 0, "retMsg": "Dry run success", "result": {"list": [{"lotSizeFilter": {"qtyStep": "0.001"}, "priceFilter": {"tickSize": "0.01"}}]}}
            elif func.__name__ == "get_kline":
                # Return an empty DataFrame for klines in dry run, or a minimal one if needed for indicator calculation
                return {"retCode": 0, "retMsg": "Dry run success", "result": {"list": []}}
            elif func.__name__ == "get_orderbook":
                # Simulate an orderbook for spread calculation
                return {"retCode": 0, "retMsg": "Dry run success", "result": {"b": [["29999.00", "10"]], "a": [["30001.00", "10"]]}}
            else:
                return {"retCode": 0, "retMsg": "Dry run success", "result": {}} 

        for attempt in range(MAX_API_RETRIES):
            self._check_rate_limit() # Check before each actual attempt
            try:
                self.last_api_call_time = time.time()
                
                response = func(*args, **kwargs)
                
                # Increment counter only for successful API calls (or those that hit Bybit's server)
                self.api_call_counter += 1 

                # Check for Bybit specific rate limit error
                if response and response.get("retCode") == 10006:
                    self.logger.warning(f"{NEON_YELLOW}Bybit API rate limit hit (retCode 10006). Retrying in {RETRY_DELAY_SECONDS}s...{RESET}")
                    time.sleep(RETRY_DELAY_SECONDS)
                    continue # Retry immediately
                
                return response
            except pybit.exceptions.FailedRequestError as e:
                self._handle_403_error(e) # Check for 403 specifically
                self.logger.error(f"{NEON_RED}API call failed (attempt {attempt+1}/{MAX_API_RETRIES}): {e}{RESET}")
                if attempt < MAX_API_RETRIES - 1:
                    time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                else:
                    self.logger.error(f"{NEON_RED}Max retries reached. API call failed.{RESET}")
                    return None
            except Exception as e:
                self.logger.error(f"{NEON_RED}Unexpected error in API call: {e}{RESET}")
                return None
        
        return None

    def _handle_403_error(self, e):
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
        return str(x)

    def _ok(self, resp: dict | None) -> bool:
        return bool(resp and resp.get("retCode") == 0)

    def _log_api(self, action: str, resp: dict | None):
        if self.dry_run:
            self.logger.info(f"{NEON_BLUE}DRY RUN: {action} simulated.{RESET}")
            return
        if not resp:
            self.logger.error(f"{NEON_RED}{action}: No response.{RESET}")
            return
        if not self._ok(resp):
            self.logger.error(f"{NEON_RED}{action}: Error {resp.get('retCode')} - {resp.get('retMsg')}{RESET}")

    def set_leverage(self, symbol: str, buy: str, sell: str) -> bool:
        if not self.enabled: return False
        
        def _set_leverage():
            return self.session.set_leverage(
                category=self.category, 
                symbol=symbol, 
                buyLeverage=self._q(buy), 
                sellLeverage=self._q(sell)
            )
        
        resp = self._make_api_call(_set_leverage)
        self._log_api("set_leverage", resp)
        return self._ok(resp)

    def get_positions(self, symbol: str | None = None) -> dict | None:
        if not self.enabled: return None
        
        def _get_positions():
            params = {"category": self.category}
            if symbol: params["symbol"] = symbol
            return self.session.get_positions(**params)
        
        return self._make_api_call(_get_positions)

    def get_wallet_balance(self, coin: str = "USDT") -> dict | None:
        if not self.enabled: return None
        
        def _get_wallet_balance():
            return self.session.get_wallet_balance(
                accountType=self.cfg["execution"].get("account_type", "UNIFIED"), 
                coin=coin
            )
        
        return self._make_api_call(_get_wallet_balance)

    def place_order(self, **kwargs) -> dict | None:
        if not self.enabled: return None
        
        # Add slippage adjustment if enabled
        if self.cfg.get("execution", {}).get("slippage_adjustment", False) and kwargs.get("orderType") == "Limit":
            price = Decimal(str(kwargs.get("price", "0")))
            if kwargs.get("side") == "Buy":
                # For buy orders, increase price slightly to ensure fill
                kwargs["price"] = self._q(price * Decimal("1.0002"))
            else:
                # For sell orders, decrease price slightly to ensure fill
                kwargs["price"] = self._q(price * Decimal("0.9998"))
        
        def _place_order():
            return self.session.place_order(**kwargs)
        
        resp = self._make_api_call(_place_order)
        self._log_api("place_order", resp)
        return resp

    def fetch_current_price(self, symbol: str) -> Decimal | None:
        # Try WebSocket first if available and connected
        if self.ws and self.ws.connected:
            ws_price = self.ws.get_last_price()
            if ws_price:
                return ws_price
        
        # Fall back to REST API
        if not self.enabled: return None
        
        def _fetch_current_price():
            response = self.session.get_tickers(category=self.category, symbol=symbol) # Use self.category
            if response and response.get("retCode") == 0 and response.get("result", {}).get("list"):
                return Decimal(response["result"]["list"][0]["lastPrice"])
            return None
        
        price = self._make_api_call(_fetch_current_price)
        if not price:
            self.logger.warning(f"{NEON_YELLOW}Could not fetch current price for {symbol}.{RESET}")
        return price

    def fetch_instrument_info(self, symbol: str) -> dict | None:
        if not self.enabled: return None
        
        def _fetch_instrument_info():
            response = self.session.get_instruments_info(category=self.category, symbol=symbol) # Use self.category
            if response and response.get("retCode") == 0 and response.get("result", {}).get("list"):
                return response["result"]["list"][0]
            return None
        
        info = self._make_api_call(_fetch_instrument_info)
        if not info:
            self.logger.warning(f"{NEON_YELLOW}Could not fetch instrument info for {symbol}.{RESET}")
        return info

    def fetch_klines(self, symbol: str, interval: str, limit: int) -> pd.DataFrame | None:
        if not self.enabled: return None
        
        def _fetch_klines():
            params = {
                "category": self.category, # Use self.category
                "symbol": symbol, 
                "interval": interval, 
                "limit": limit
            }
            response = self.session.get_kline(**params)
            if response and response.get("result", {}).get("list"):
                df = pd.DataFrame(
                    response["result"]["list"], 
                    columns=["start_time", "open", "high", "low", "close", "volume", "turnover"]
                )
                df["start_time"] = pd.to_datetime(
                    df["start_time"].astype(int), 
                    unit="ms", 
                    utc=True
                ).dt.tz_convert(TIMEZONE)
                for col in ["open", "high", "low", "close", "volume", "turnover"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df.set_index("start_time", inplace=True)
                df.sort_index(inplace=True)
                return df if not df.empty else None
            return None
        
        df = self._make_api_call(_fetch_klines)
        if not df:
            self.logger.warning(f"{NEON_YELLOW}Could not fetch klines for {symbol} {interval}.{RESET}")
        return df

    def fetch_orderbook(self, symbol: str, limit: int) -> dict | None:
        # Try WebSocket first if available and connected
        if self.ws and self.ws.connected:
            ws_orderbook = self.ws.get_orderbook()
            if ws_orderbook:
                return ws_orderbook
        
        # Fall back to REST API
        if not self.enabled: return None
        
        def _fetch_orderbook():
            response = self.session.get_orderbook(category=self.category, symbol=symbol, limit=limit) # Use self.category
            if response and response.get("result"):
                return response["result"]
            return None
        
        orderbook = self._make_api_call(_fetch_orderbook)
        if not orderbook:
            self.logger.warning(f"{NEON_YELLOW}Could not fetch orderbook for {symbol}.{RESET}")
        return orderbook

    def batch_place_orders(self, requests: list[dict]) -> dict | None:
        if not self.enabled: return None
        
        def _batch_place_orders():
            return self.session.batch_place_order(category=self.category, request=requests)
        
        resp = self._make_api_call(_batch_place_orders)
        self._log_api("batch_place_order", resp)
        return resp

    def cancel_by_link_id(self, symbol: str, order_link_id: str) -> dict | None:
        if not self.enabled: return None
        
        def _cancel_by_link_id():
            return self.session.cancel_order(
                category=self.category, 
                symbol=symbol, 
                orderLinkId=order_link_id
            )
        
        resp = self._make_api_call(_cancel_by_link_id)
        self._log_api("cancel_by_link_id", resp)
        return resp

    def get_executions(self, symbol: str, start_time_ms: int, limit: int) -> dict | None:
        if not self.enabled: return None
        
        def _get_executions():
            return self.session.get_executions(
                category=self.category, 
                symbol=symbol, 
                startTime=start_time_ms, 
                limit=limit
            )
        
        return self._make_api_call(_get_executions)

    def get_open_orders(self, symbol: str) -> dict | None:
        if not self.enabled: return None
        
        def _get_open_orders():
            return self.session.get_open_orders(
                category=self.category,
                symbol=symbol
            )
        
        return self._make_api_call(_get_open_orders)

# --- Utilities for execution layer ---
def build_partial_tp_targets(side: Literal["BUY", "SELL"], entry_price: Decimal, atr_value: Decimal, total_qty: Decimal, cfg: dict, qty_step: Decimal) -> list[dict]:
    ex = cfg["execution"]
    tps = ex["tp_scheme"]["targets"]
    price_prec = cfg["trade_management"]["price_precision"]
    out = []
    for i, t in enumerate(tps, start=1):
        qty = round_qty(total_qty * Decimal(str(t["size_pct"])), qty_step)
        if qty <= 0: continue
        if ex["tp_scheme"]["mode"] == "atr_multiples":
            price = (entry_price + atr_value * Decimal(str(t["atr_multiple"]))) if side == "BUY" else (entry_price - atr_value * Decimal(str(t["atr_multiple"])))
        else:
            price = (entry_price * (1 + Decimal(str(t.get("percent", 1))) / 100)) if side == "BUY" else (entry_price * (1 - Decimal(str(t.get("percent", 1))) / 100))
        tif = t.get("tif", ex.get("default_time_in_force"))
        if tif == "GoodTillCancel": tif = "GTC"
        out.append({
            "name": t.get("name", f"TP{i}"), 
            "price": round_price(price, price_prec), 
            "qty": qty,
            "order_type": t.get("order_type", "Limit"), 
            "tif": tif,
            "post_only": bool(t.get("post_only", ex.get("post_only_default", False))),
            "link_id_suffix": f"tp{i}",
        })
    return out

# --- Position Management ---
class PositionManager:
    def __init__(self, config: dict[str, Any], logger: logging.Logger, symbol: str, pybit_client: "PybitTradingClient | None" = None):
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.open_positions: list[dict] = []
        self.trade_management_enabled = config["trade_management"]["enabled"]
        self.max_open_positions = config["trade_management"]["max_open_positions"]
        self.order_precision = config["trade_management"]["order_precision"]
        self.price_precision = config["trade_management"]["price_precision"]
        self.qty_step = None
        self.tick_size = None
        self.pybit = pybit_client
        self.live = bool(config.get("execution", {}).get("use_pybit", False)) and not bool(config.get("execution", {}).get("dry_run", True))
        self._update_precision_from_exchange()
        self.position_history = []
        self.daily_pnl = Decimal("0") # This needs careful daily reset for risk_limits
        self.max_drawdown_pct = Decimal(str(config.get("risk_guardrails", {}).get("max_drawdown_pct", 8.0)))
        self.max_day_loss_pct = Decimal(str(config.get("risk_guardrails", {}).get("max_day_loss_pct", 3.0)))
        self.initial_balance = self._get_current_balance()
        self.peak_balance = self.initial_balance
        
        # New: Sync with exchange positions at startup
        self._sync_positions_on_startup()

    def _update_precision_from_exchange(self):
        if not self.pybit or not self.pybit.enabled:
            self.logger.warning(f"Pybit client not enabled or in dry-run. Using config precision for {self.symbol}.")
            return
        info = self.pybit.fetch_instrument_info(self.symbol)
        if info:
            if "lotSizeFilter" in info:
                self.qty_step = Decimal(str(info["lotSizeFilter"].get("qtyStep"))).normalize() # Normalize to remove trailing zeros
                if not self.qty_step.is_zero():
                    # Calculate precision from qty_step (e.g., 0.001 -> 3)
                    self.order_precision = -self.qty_step.as_tuple().exponent
                self.logger.info(f"Updated qty_step: {self.qty_step}, order_precision: {self.order_precision}")
            if "priceFilter" in info:
                self.tick_size = Decimal(str(info["priceFilter"].get("tickSize"))).normalize() # Normalize
                if not self.tick_size.is_zero():
                    # Calculate precision from tick_size (e.g., 0.01 -> 2)
                    self.price_precision = -self.tick_size.as_tuple().exponent
                self.logger.info(f"Updated tick_size: {self.tick_size}, price_precision: {self.price_precision}")
        else:
            self.logger.warning(f"Could not fetch precision for {self.symbol}. Using config values.")

    def _get_current_balance(self) -> Decimal:
        if self.live and self.pybit and self.pybit.enabled:
            resp = self.pybit.get_wallet_balance(coin="USDT")
            if resp and self.pybit._ok(resp) and resp.get("result", {}).get("list"):
                for coin_balance in resp["result"]["list"][0]["coin"]:
                    if coin_balance["coin"] == "USDT":
                        return Decimal(coin_balance["walletBalance"])
        # In dry_run or if live trading is disabled, use the configured balance
        return Decimal(str(self.config["trade_management"]["account_balance"]))

    def _sync_positions_on_startup(self):
        if not self.live or not self.pybit or not self.pybit.enabled:
            self.logger.info(f"{NEON_BLUE}Not in live mode, skipping position sync on startup.{RESET}")
            return
        
        self.logger.info(f"{NEON_BLUE}Attempting to sync positions from exchange on startup...{RESET}")
        positions_resp = self.pybit.get_positions(self.symbol)
        if positions_resp and self.pybit._ok(positions_resp):
            pos_list = positions_resp.get("result", {}).get("list", [])
            for p in pos_list:
                size = Decimal(p.get("size", "0"))
                if size > 0:
                    side = "BUY" if p.get("side") == "Buy" else "SELL"
                    avg_price = Decimal(p.get("avgPrice", "0"))
                    
                    # Create a synthetic local position for existing exchange positions
                    synthetic_pos = {
                        "entry_time": datetime.now(TIMEZONE), # Use current time as best guess
                        "symbol": self.symbol, 
                        "side": side,
                        "entry_price": round_price(avg_price, self.price_precision), 
                        "qty": round_qty(abs(size), self.qty_step or Decimal("0.0001")),
                        "stop_loss": Decimal("0"), # Placeholder, would need to fetch or calculate
                        "take_profit": Decimal("0"), # Placeholder
                        "status": "OPEN", 
                        "link_prefix": f"sync_{int(time.time()*1000)}", # Mark as synced
                        "adds": 0,
                        "initial_stop_loss": Decimal("0"), # Placeholder
                        "atr_at_entry": Decimal("0"), # Placeholder
                        "best_price": avg_price, # Initialize best price for trailing stop
                    }
                    self.open_positions.append(synthetic_pos)
                    self.logger.warning(f"{NEON_YELLOW}Synced existing exchange position: {side} {size} @ {avg_price}{RESET}")
        else:
            self.logger.warning(f"{NEON_YELLOW}Failed to fetch exchange positions on startup.{RESET}")

    def _calculate_order_size(self, current_price: Decimal, atr_value: Decimal, conviction: float = 1.0) -> Decimal:
        if not self.trade_management_enabled: return Decimal("0")
        
        # Get current balance
        account_balance = self._get_current_balance()
        
        # Calculate risk amount based on account balance and risk percentage
        base_risk_pct = Decimal(str(self.config["trade_management"]["risk_per_trade_percent"])) / 100
        # Scale risk based on conviction (conviction 0-1, so risk_pct can be 0.5x to 1.5x base)
        # conviction is already scaled from 0.5 to 1.0 in main loop, so just multiply
        risk_pct = base_risk_pct * Decimal(str(conviction)) 
        risk_amount = account_balance * risk_pct
        
        # Calculate stop loss distance
        stop_loss_atr_multiple = Decimal(str(self.config["trade_management"]["stop_loss_atr_multiple"]))
        stop_loss_distance = atr_value * stop_loss_atr_multiple
        
        if stop_loss_distance <= 0:
            self.logger.warning(f"{NEON_YELLOW}Stop loss distance is zero. Cannot calculate order size.{RESET}")
            return Decimal("0")
        
        # Calculate order quantity
        order_qty = (risk_amount / stop_loss_distance) / current_price
        
        # Apply position size limits
        max_position_pct = Decimal("0.1")  # Maximum 10% of account in one position
        max_position_value = account_balance * max_position_pct
        max_qty = max_position_value / current_price
        
        # Take the minimum of calculated and max quantity
        final_qty = min(order_qty, max_qty)
        
        return round_qty(final_qty, self.qty_step) if self.qty_step else final_qty.quantize(Decimal(f"1e-{self.order_precision}"), rounding=ROUND_DOWN)

    def open_position(self, signal: Literal["BUY", "SELL"], current_price: Decimal, atr_value: Decimal, conviction: float) -> dict | None:
        # Check if we already have an open position on the exchange (only if live)
        if self.live and self.pybit and self.pybit.enabled:
            positions_resp = self.pybit.get_positions(self.symbol)
            if positions_resp and self.pybit._ok(positions_resp):
                pos_list = positions_resp.get("result", {}).get("list", [])
                if any(p.get("size") and Decimal(p.get("size")) > 0 for p in pos_list):
                    self.logger.warning(f"{NEON_YELLOW}Exchange position exists, aborting new position.{RESET}")
                    return None

        # Check if we can open a new position based on local state
        if not self.trade_management_enabled or len(self.get_open_positions()) >= self.max_open_positions:
            self.logger.info(f"{NEON_YELLOW}Cannot open new position (max reached or disabled).{RESET}")
            return None

        # Calculate order size
        order_qty = self._calculate_order_size(current_price, atr_value, conviction)
        if order_qty <= 0:
            self.logger.warning(f"{NEON_YELLOW}Order quantity is zero. Cannot open position.{RESET}")
            return None

        # Calculate stop loss and take profit prices
        stop_loss = self._compute_stop_loss_price(signal, current_price, atr_value)
        take_profit = self._calculate_take_profit_price(signal, current_price, atr_value)

        # Create position object
        position = {
            "entry_time": datetime.now(TIMEZONE), 
            "symbol": self.symbol, 
            "side": signal,
            "entry_price": round_price(current_price, self.price_precision), 
            "qty": order_qty,
            "stop_loss": stop_loss, 
            "take_profit": round_price(take_profit, self.price_precision),
            "status": "OPEN", 
            "link_prefix": f"wgx_{int(time.time()*1000)}", 
            "adds": 0,
            "initial_stop_loss": stop_loss,
            "atr_at_entry": atr_value,
            "conviction": conviction, # Store conviction for reference
        }

        # Execute live order if enabled and not in dry run
        if self.live and self.pybit and self.pybit.enabled:
            entry_link = f"{position['link_prefix']}_entry"
            
            # Place entry order
            resp = self.pybit.place_order(
                category=self.pybit.category, 
                symbol=self.symbol, 
                side=self.pybit._side_to_bybit(signal),
                orderType="Market", 
                qty=self.pybit._q(order_qty), 
                orderLinkId=entry_link,
            )
            
            if not self.pybit._ok(resp):
                self.logger.error(f"{NEON_RED}Live entry failed. Simulating only.{RESET}")
            else:
                self.logger.info(f"{NEON_GREEN}Live entry submitted: {entry_link}{RESET}")
                
                # Place take profit orders if using partial TPs
                if self.config["execution"]["tpsl_mode"] == "Partial":
                    targets = build_partial_tp_targets(signal, position["entry_price"], atr_value, order_qty, self.config, self.qty_step)
                    for t in targets:
                        payload = {
                            "symbol": self.symbol, 
                            "side": self.pybit._side_to_bybit("SELL" if signal == "BUY" else "BUY"),
                            "orderType": t["order_type"], 
                            "qty": self.pybit._q(t["qty"]), 
                            "timeInForce": t["tif"],
                            "reduceOnly": True, 
                            "positionIdx": self.pybit._pos_idx(signal),
                            "orderLinkId": f"{position['link_prefix']}_{t['link_id_suffix']}", 
                            "category": self.pybit.category,
                        }
                        if t["order_type"] == "Limit": payload["price"] = self.pybit._q(t["price"])
                        if t.get("post_only"): payload["isPostOnly"] = True
                        resp_tp = self.pybit.place_order(**payload)
                        if resp_tp and resp_tp.get("retCode") == 0: 
                            self.logger.info(f"{NEON_GREEN}Placed individual TP target: {payload.get('orderLinkId')}{RESET}")
                        else: 
                            self.logger.error(f"{NEON_RED}Failed to place TP target: {payload.get('orderLinkId')}. Error: {resp_tp.get('retMsg') if resp_tp else 'No response'}{RESET}")

                # Place stop loss order if using conditional stop
                if self.config["execution"]["sl_scheme"]["use_conditional_stop"]:
                    sl_link = f"{position['link_prefix']}_sl"
                    sresp = self.pybit.place_order(
                        category=self.pybit.category, 
                        symbol=self.symbol, 
                        side=self.pybit._side_to_bybit("SELL" if signal == "BUY" else "BUY"),
                        orderType=self.config["execution"]["sl_scheme"]["stop_order_type"], 
                        qty=self.pybit._q(order_qty),
                        reduceOnly=True, 
                        orderLinkId=sl_link, 
                        triggerPrice=self.pybit._q(stop_loss),
                        triggerDirection=(2 if signal == "BUY" else 1), # 1: rise, 2: fall
                        orderFilter="Stop",
                    )
                    if self.pybit._ok(sresp): 
                        self.logger.info(f"{NEON_GREEN}Conditional stop placed at {stop_loss}.{RESET}")

        # Add position to open positions list
        self.open_positions.append(position)
        self.logger.info(f"{NEON_GREEN}Opened {signal} position (simulated/live): {position}{RESET}")
        return position

    def manage_positions(self, current_price: Decimal, performance_tracker: Any):
        if not self.trade_management_enabled or not self.open_positions:
            return
        
        positions_to_close = []
        for i, pos in enumerate(self.open_positions):
            if pos["status"] == "OPEN":
                closed_by = ""
                
                # Check if stop loss is hit
                if pos["side"] == "BUY" and current_price <= pos["stop_loss"]: 
                    closed_by = "STOP_LOSS"
                elif pos["side"] == "SELL" and current_price >= pos["stop_loss"]: 
                    closed_by = "STOP_LOSS"
                
                # Check if take profit is hit
                elif pos["side"] == "BUY" and current_price >= pos["take_profit"]: 
                    closed_by = "TAKE_PROFIT"
                elif pos["side"] == "SELL" and current_price <= pos["take_profit"]: 
                    closed_by = "TAKE_PROFIT"
                
                # Close position if stop loss or take profit is hit
                if closed_by:
                    pos.update({
                        "status": "CLOSED", 
                        "exit_time": datetime.now(TIMEZONE), 
                        "exit_price": current_price, 
                        "closed_by": closed_by
                    })
                    
                    # Calculate PnL
                    pnl = ((current_price - pos["entry_price"]) * pos["qty"]) if pos["side"] == "BUY" else ((pos["entry_price"] - current_price) * pos["qty"])
                    
                    # Record trade
                    performance_tracker.record_trade(pos, pnl)
                    
                    # Update daily PnL
                    self.daily_pnl += pnl
                    
                    # Update peak balance
                    current_balance = self._get_current_balance() + performance_tracker.total_pnl
                    if current_balance > self.peak_balance:
                        self.peak_balance = current_balance
                    
                    # Log position close
                    self.logger.info(f"{NEON_PURPLE}Closed {pos['side']} by {closed_by}. PnL: {pnl:.2f}{RESET}")
                    
                    # Add to position history
                    self.position_history.append(pos)
                    
                    # Mark for removal
                    positions_to_close.append(i)
        
        # Remove closed positions
        self.open_positions = [p for i, p in enumerate(self.open_positions) if i not in positions_to_close]

    def get_open_positions(self) -> list[dict]:
        return [pos for pos in self.open_positions if pos.get("status") == "OPEN"]

    def _compute_stop_loss_price(self, side: Literal["BUY", "SELL"], entry_price: Decimal, atr_value: Decimal) -> Decimal:
        ex = self.config["execution"]
        sch = ex["sl_scheme"]
        price_prec = self.config["trade_management"]["price_precision"]
        tick_size = self.tick_size if self.tick_size else Decimal(f"1e-{price_prec}")
        buffer = tick_size * 5 # Small buffer to avoid immediate re-trigger on price fluctuations
        
        if sch["type"] == "atr_multiple":
            sl = (entry_price - atr_value * Decimal(str(sch["atr_multiple"]))) if side == "BUY" else (entry_price + atr_value * Decimal(str(sch["atr_multiple"])))
        else: # percent based
            sl = (entry_price * (1 - Decimal(str(sch["percent"])) / 100)) if side == "BUY" else (entry_price * (1 + Decimal(str(sch["percent"])) / 100))
        
        sl_with_buffer = sl - buffer if side == "BUY" else sl + buffer
        return round_price(sl_with_buffer, price_prec)

    def _calculate_take_profit_price(self, signal: Literal["BUY", "SELL"], current_price: Decimal, atr_value: Decimal) -> Decimal:
        tp_mult = Decimal(str(self.config["trade_management"]["take_profit_atr_multiple"]))
        tp = (current_price + (atr_value * tp_mult)) if signal == "BUY" else (current_price - (atr_value * tp_mult))
        return round_price(tp, self.price_precision)

    def trail_stop(self, pos: dict, current_price: Decimal, atr_value: Decimal):
        if pos.get('status') != 'OPEN' or self.live: return # Only trail simulated positions or if not live
        atr_mult = Decimal(str(self.config["trade_management"]["stop_loss_atr_multiple"]))
        side = pos["side"]
        pos["best_price"] = pos.get("best_price", pos["entry_price"])
        
        if side == "BUY":
            pos["best_price"] = max(pos["best_price"], current_price)
            new_sl = round_price(pos["best_price"] - atr_mult * atr_value, self.price_precision)
            if new_sl > pos["stop_loss"]: 
                pos["stop_loss"] = new_sl
                self.logger.debug(f"Trailing BUY SL for {pos['symbol']}: {new_sl:.2f}")
        else: # SELL
            pos["best_price"] = min(pos["best_price"], current_price)
            new_sl = round_price(pos["best_price"] + atr_mult * atr_value, self.price_precision)
            if new_sl < pos["stop_loss"]: 
                pos["stop_loss"] = new_sl
                self.logger.debug(f"Trailing SELL SL for {pos['symbol']}: {new_sl:.2f}")

    def try_pyramid(self, current_price: Decimal, atr_value: Decimal):
        if not self.trade_management_enabled or not self.open_positions or self.live: return
        py_cfg = self.config.get("pyramiding", {})
        if not py_cfg.get("enabled", False): return
        
        for pos in self.open_positions:
            if pos.get("status") != "OPEN": continue
            adds = pos.get("adds", 0)
            if adds >= int(py_cfg.get("max_adds", 0)): continue
            
            step = Decimal(str(py_cfg.get("step_atr", 0.7))) * atr_value
            target = pos["entry_price"] + step * (adds + 1) if pos["side"] == "BUY" else pos["entry_price"] - step * (adds + 1)
            
            if (pos["side"] == "BUY" and current_price >= target) or (pos["side"] == "SELL" and current_price <= target):
                add_qty = round_qty(pos['qty'] * Decimal(str(py_cfg.get("size_pct_of_initial", 0.5))), self.qty_step or Decimal("0.0001"))
                if add_qty > 0:
                    total_cost = (pos['qty'] * pos['entry_price']) + (add_qty * current_price)
                    pos['qty'] += add_qty
                    pos['entry_price'] = total_cost / pos['qty']
                    pos["adds"] = adds + 1
                    self.logger.info(f"{NEON_GREEN}Pyramiding add #{pos['adds']} qty={add_qty}. New avg price: {pos['entry_price']:.2f}{RESET}")

    def check_risk_limits(self) -> Tuple[bool, str]:
        """Check if risk limits are breached"""
        if not self.trade_management_enabled:
            return True, ""
        
        # Get current balance
        current_balance = self._get_current_balance()
        
        # Check daily loss limit
        # Note: daily_pnl is accumulated PnL from closed positions for the current day.
        # This needs to be reset daily for accurate "daily loss".
        # For simplicity, this example just checks total daily_pnl.
        if self.daily_pnl < 0:
            # Avoid division by zero if balance is very low
            if self.initial_balance <= 0: 
                return False, "Initial account balance is zero or negative, cannot calculate daily loss percentage."

            daily_loss_pct = abs(self.daily_pnl) / self.initial_balance * 100 # Calculate against initial balance for the day
            if daily_loss_pct > self.max_day_loss_pct:
                return False, f"Daily loss limit breached: {daily_loss_pct:.2f}% > {self.max_day_loss_pct}%"
        
        # Check drawdown limit
        if self.peak_balance > 0:
            drawdown = (self.peak_balance - current_balance) / self.peak_balance * 100
            if drawdown > self.max_drawdown_pct:
                return False, f"Max drawdown limit breached: {drawdown:.2f}% > {self.max_drawdown_pct}%"
        
        return True, ""

# --- Performance Tracking & Sync ---
class PerformanceTracker:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.trades: list[dict] = []
        self.total_pnl = Decimal("0")
        self.gross_profit = Decimal("0")
        self.gross_loss = Decimal("0")
        self.wins = 0
        self.losses = 0
        self.peak_pnl = Decimal("0")
        self.max_drawdown = Decimal("0")
        self.consecutive_losses = 0
        self.max_consecutive_losses = 0
        self.start_time = datetime.now(TIMEZONE)
        self.daily_stats = {}
        self._last_day_reset = self.start_time.date()

    def _reset_daily_stats_if_new_day(self):
        current_date = datetime.now(TIMEZONE).date()
        if current_date > self._last_day_reset:
            self.logger.info(f"{NEON_CYAN}New day detected. Resetting daily PnL statistics.{RESET}")
            # Store previous day's PnL for historical tracking if needed
            if self._last_day_reset in self.daily_stats:
                self.daily_stats[self._last_day_reset]["end_pnl"] = self.daily_stats[self._last_day_reset]["pnl"]
            self.daily_stats[current_date] = {
                "trades": 0, "pnl": Decimal("0"), "wins": 0, "losses": 0, "start_time": datetime.now(TIMEZONE)
            }
            self._last_day_reset = current_date
            # Note: PositionManager's `daily_pnl` would also need to be reset here
            # or its calculation adjusted to truly reflect only today's PnL.

    def record_trade(self, position: dict, pnl: Decimal):
        self._reset_daily_stats_if_new_day() # Check for new day before recording trade
        
        self.trades.append({**position, "pnl": pnl})
        self.total_pnl += pnl
        
        # Update win/loss statistics
        if pnl > 0:
            self.wins += 1
            self.gross_profit += pnl
            self.consecutive_losses = 0  # Reset consecutive losses on a win
        else:
            self.losses += 1
            self.gross_loss += abs(pnl)
            self.consecutive_losses += 1
            if self.consecutive_losses > self.max_consecutive_losses:
                self.max_consecutive_losses = self.consecutive_losses
        
        # Update peak PnL and max drawdown
        if self.total_pnl > self.peak_pnl: 
            self.peak_pnl = self.total_pnl
        drawdown = self.peak_pnl - self.total_pnl
        if drawdown > self.max_drawdown: 
            self.max_drawdown = drawdown
        
        # Update daily statistics
        trade_date = position.get("exit_time", datetime.now(TIMEZONE)).date()
        if trade_date not in self.daily_stats:
            # This should ideally be handled by _reset_daily_stats_if_new_day
            # but as a fallback
            self.daily_stats[trade_date] = {
                "trades": 0, "pnl": Decimal("0"), "wins": 0, "losses": 0, "start_time": datetime.now(TIMEZONE)
            }
        
        self.daily_stats[trade_date]["trades"] += 1
        self.daily_stats[trade_date]["pnl"] += pnl
        if pnl > 0:
            self.daily_stats[trade_date]["wins"] += 1
        else:
            self.daily_stats[trade_date]["losses"] += 1
        
        self.logger.info(f"{NEON_CYAN}Trade recorded. PnL: {pnl:.4f}. Total PnL: {self.total_pnl:.4f}{RESET}")

    def day_pnl(self) -> Decimal:
        today = datetime.now(TIMEZONE).date()
        return self.daily_stats.get(today, {}).get("pnl", Decimal("0"))

    def get_summary(self) -> dict:
        total_trades = len(self.trades)
        win_rate = (self.wins / total_trades) * 100 if total_trades > 0 else 0
        profit_factor = self.gross_profit / self.gross_loss if self.gross_loss > 0 else Decimal("inf")
        avg_win = self.gross_profit / self.wins if self.wins > 0 else Decimal("0")
        avg_loss = self.gross_loss / self.losses if self.losses > 0 else Decimal("0")
        
        # Calculate average holding time
        holding_times = []
        for trade in self.trades:
            if "entry_time" in trade and "exit_time" in trade:
                entry_time = trade["entry_time"]
                exit_time = trade["exit_time"]
                # Ensure times are datetime objects for calculation
                if isinstance(entry_time, str):
                    try: entry_time = datetime.fromisoformat(entry_time)
                    except ValueError: entry_time = None
                if isinstance(exit_time, str):
                    try: exit_time = datetime.fromisoformat(exit_time)
                    except ValueError: exit_time = None
                
                if isinstance(entry_time, datetime) and isinstance(exit_time, datetime):
                    holding_time = (exit_time - entry_time).total_seconds() / 60  # in minutes
                    holding_times.append(holding_time)
        
        avg_holding_time = sum(holding_times) / len(holding_times) if holding_times else 0
        
        return {
            "total_trades": total_trades, 
            "total_pnl": f"{self.total_pnl:.4f}",
            "gross_profit": f"{self.gross_profit:.4f}", 
            "gross_loss": f"{self.gross_loss:.4f}",
            "profit_factor": f"{profit_factor:.2f}", 
            "max_drawdown": f"{self.max_drawdown:.4f}",
            "wins": self.wins, 
            "losses": self.losses, 
            "win_rate": f"{win_rate:.2f}%",
            "avg_win": f"{avg_win:.4f}", 
            "avg_loss": f"{avg_loss:.4f}",
            "avg_holding_time_min": f"{avg_holding_time:.1f}",
            "consecutive_losses": self.consecutive_losses,
            "max_consecutive_losses": self.max_consecutive_losses,
            "days_traded": len(self.daily_stats),
            "start_time": self.start_time.strftime("%Y-%m-%d %H:%M:%S"),
        }

class ExchangeExecutionSync:
    def __init__(self, symbol: str, pybit: PybitTradingClient, logger: logging.Logger, cfg: dict, pm: PositionManager, pt: PerformanceTracker):
        self.symbol = symbol
        self.pybit = pybit
        self.logger = logger
        self.cfg = cfg
        self.pm = pm
        self.pt = pt
        self.last_exec_time_ms = int(time.time() * 1000) - 5 * 60 * 1000 # Look back 5 minutes initially
        self.pending_orders = {}  # Track orders by link ID

    def _is_ours(self, link_id: str | None) -> bool:
        if not link_id: return False
        if not self.cfg["execution"]["live_sync"]["only_track_linked"]: return True
        return link_id.startswith("wgx_") or link_id.startswith("hb_") or link_id.startswith("sync_") # Include heartbeat and synced orders

    def _compute_be_price(self, side: str, entry_price: Decimal, atr_value: Decimal) -> Decimal:
        be_cfg = self.cfg["execution"]["breakeven_after_tp1"]
        off_type = str(be_cfg.get("offset_type", "atr")).lower()
        off_val = Decimal(str(be_cfg.get("offset_value", 0)))
        if off_type == "atr": adj = atr_value * off_val
        elif off_type == "percent": adj = entry_price * (off_val / Decimal("100"))
        else: adj = off_val
        lock_adj = entry_price * (Decimal(str(be_cfg.get("lock_in_min_percent", 0))) / Decimal("100"))
        be = entry_price + max(adj, lock_adj) if side == "BUY" else entry_price - max(adj, lock_adj)
        return round_price(be, self.pm.price_precision)

    def _move_stop_to_breakeven(self, open_pos: dict, atr_value: Decimal):
        if not self.cfg["execution"]["breakeven_after_tp1"].get("enabled", False): return
        if self.pybit.dry_run:
            self.logger.info(f"{NEON_BLUE}DRY RUN: Simulating move SL to breakeven for {open_pos['symbol']}{RESET}")
            return
        
        try:
            entry, side = Decimal(str(open_pos["entry_price"])), open_pos["side"]
            new_sl = self._compute_be_price(side, entry, atr_value)
            
            # Only move if new SL is better (e.g., higher for BUY, lower for SELL)
            if (side == "BUY" and new_sl <= open_pos["stop_loss"]) or \
               (side == "SELL" and new_sl >= open_pos["stop_loss"]):
                self.logger.debug(f"Breakeven SL for {self.symbol} not better than current. Current: {open_pos['stop_loss']:.2f}, New: {new_sl:.2f}")
                return

            link_prefix = open_pos.get("link_prefix")
            old_sl_link = f"{link_prefix}_sl" if link_prefix else None # Initial SL link
            
            # Cancel existing SL order(s)
            if old_sl_link: 
                self.pybit.cancel_by_link_id(self.symbol, old_sl_link)
                self.logger.info(f"{NEON_YELLOW}Cancelled old SL order {old_sl_link}{RESET}")
            
            # Place new breakeven SL order
            new_sl_link = f"{link_prefix}_sl_be" if link_prefix else f"wgx_{int(time.time()*1000)}_sl_be"
            sresp = self.pybit.place_order(
                category=self.pybit.category, 
                symbol=self.symbol, 
                side=self.pybit._side_to_bybit("SELL" if side == "BUY" else "BUY"),
                orderType=self.cfg["execution"]["sl_scheme"]["stop_order_type"], 
                qty=self.pybit._q(open_pos["qty"]),
                reduceOnly=True, 
                orderLinkId=new_sl_link, 
                triggerPrice=self.pybit._q(new_sl),
                triggerDirection=(2 if side == "BUY" else 1), 
                orderFilter="Stop",
            )
            if self.pybit._ok(sresp): 
                open_pos["stop_loss"] = new_sl # Update local stop loss
                self.logger.info(f"{NEON_GREEN}Moved SL to breakeven at {new_sl}. New SL link: {new_sl_link}{RESET}")
            else:
                self.logger.error(f"{NEON_RED}Failed to place breakeven SL: {sresp.get('retMsg') if sresp else 'No response'}{RESET}")

        except (pybit.exceptions.FailedRequestError, Exception) as e:
            self.logger.error(f"{NEON_RED}Breakeven move exception: {e}{RESET}")

    def poll(self):
        if not (self.pybit and self.pybit.enabled): return
        if self.pybit.dry_run:
            self.logger.debug(f"{NEON_BLUE}DRY RUN: Simulating execution sync poll.{RESET}")
            return # No actual polling in dry run
        
        try:
            # Get executions
            resp = self.pybit.get_executions(self.symbol, self.last_exec_time_ms, self.cfg["execution"]["live_sync"]["max_exec_fetch"])
            if not self.pybit._ok(resp): return
            
            rows = resp.get("result", {}).get("list", [])
            rows.sort(key=lambda r: int(r.get("execTime", 0)))
            
            for r in rows:
                link = r.get("orderLinkId")
                if not self._is_ours(link): continue
                
                ts_ms = int(r.get("execTime", 0))
                self.last_exec_time_ms = max(self.last_exec_time_ms, ts_ms + 1)
                
                # Determine if it's an entry, SL, or TP
                tag = "ENTRY"
                if "_sl" in link: tag = "SL"
                elif "_tp" in link: tag = "TP"
                
                # Find the corresponding open position
                # Assuming one open position for simplicity, or find by link_prefix if more complex
                open_pos = next((p for p in self.pm.open_positions if p.get("status") == "OPEN" and link.startswith(p.get("link_prefix", "NO_PREFIX"))), None)
                
                if tag == "ENTRY" and open_pos:
                    # Update entry price and qty if partially filled or average price changes
                    exec_qty = Decimal(str(r.get("execQty", "0")))
                    exec_price = Decimal(str(r.get("execPrice", "0")))
                    
                    # This logic assumes the 'open_position' method creates a simulated position
                    # that needs to be updated by actual exchange fills.
                    # A more robust system would create a pending order and update it on fill.
                    if open_pos.get("entry_price") == open_pos.get("original_entry_price"): # First fill
                        open_pos["entry_price"] = exec_price
                        open_pos["qty"] = exec_qty
                        open_pos["original_entry_price"] = exec_price # Store original to track average
                    else: # Subsequent fills (pyramiding or partial entry)
                        current_total_value = open_pos["entry_price"] * open_pos["qty"]
                        new_total_value = current_total_value + (exec_price * exec_qty)
                        open_pos["qty"] += exec_qty
                        open_pos["entry_price"] = new_total_value / open_pos["qty"]
                    self.logger.info(f"{NEON_GREEN}Entry fill for {link}. Qty: {exec_qty}, Price: {exec_price}. New Avg: {open_pos['entry_price']:.2f}, Total Qty: {open_pos['qty']}{RESET}")

                elif tag in ("TP", "SL") and open_pos:
                    is_reduce = (open_pos["side"] == "BUY" and r.get("side") == "Sell") or (open_pos["side"] == "SELL" and r.get("side") == "Buy")
                    if is_reduce:
                        exec_qty, exec_price = Decimal(str(r.get("execQty", "0"))), Decimal(str(r.get("execPrice", "0")))
                        
                        # Only calculate PnL for the executed quantity
                        pnl_for_exec = ((exec_price - open_pos["entry_price"]) * exec_qty) if open_pos["side"] == "BUY" else ((open_pos["entry_price"] - exec_price) * exec_qty)
                        
                        self.pt.record_trade({
                            "exit_time": datetime.fromtimestamp(ts_ms / 1000, tz=TIMEZONE), 
                            "exit_price": exec_price, 
                            "qty": exec_qty, 
                            "closed_by": tag, 
                            **open_pos # Include all position details
                        }, pnl_for_exec)
                        
                        # Update remaining quantity in the open position
                        remaining = open_pos["qty"] - exec_qty
                        open_pos["qty"] = max(remaining, Decimal("0")) # Ensure qty doesn't go negative
                        
                        if open_pos["qty"] <= 0:
                            open_pos.update({
                                "status": "CLOSED", 
                                "exit_time": datetime.fromtimestamp(ts_ms / 1000, tz=TIMEZONE), 
                                "exit_price": exec_price, 
                                "closed_by": tag
                            })
                            self.logger.info(f"{NEON_PURPLE}Position fully closed by {tag}. Total PnL for this part: {pnl_for_exec:.2f}{RESET}")
                        else:
                            self.logger.info(f"{NEON_PURPLE}Position partially closed by {tag}. Qty: {exec_qty}, PnL: {pnl_for_exec:.2f}. Remaining Qty: {open_pos['qty']}{RESET}")

                        # If TP1 hit and breakeven enabled, move SL
                        if tag == "TP" and link.endswith("_tp1") and self.cfg["execution"]["breakeven_after_tp1"].get("enabled", False):
                            atr_val = Decimal(str(self.cfg.get("_last_atr", "0.1"))) # Get last known ATR
                            self._move_stop_to_breakeven(open_pos, atr_val)
            
            # After processing all executions, clean up fully closed local positions
            self.pm.open_positions = [p for p in self.pm.open_positions if p.get("status") == "OPEN"]
            
            # Check for open orders that might need to be updated (e.g., cancelled TPs/SLs)
            self._check_open_orders()
            
        except (pybit.exceptions.FailedRequestError, Exception) as e:
            self.logger.error(f"{NEON_RED}Execution sync error: {e}{RESET}")

    def _check_open_orders(self):
        """Check and update open orders"""
        if self.pybit.dry_run:
            self.logger.debug(f"{NEON_BLUE}DRY RUN: Simulating check for open orders.{RESET}")
            return # No actual checking in dry run

        try:
            open_orders_resp = self.pybit.get_open_orders(self.symbol)
            if not open_orders_resp or not self.pybit._ok(open_orders_resp):
                return
            
            open_orders = open_orders_resp.get("result", {}).get("list", [])
            
            # Update pending orders status and remove filled/cancelled ones
            current_order_link_ids = {order.get("orderLinkId") for order in open_orders if self._is_ours(order.get("orderLinkId"))}
            
            # Remove orders from pending_orders that are no longer open on exchange
            to_remove = [link_id for link_id in self.pending_orders if link_id not in current_order_link_ids]
            for link_id in to_remove:
                self.logger.debug(f"Order {link_id} no longer open on exchange, removing from tracking.")
                del self.pending_orders[link_id]

            # Add/update orders that are open on exchange
            for order in open_orders:
                order_link_id = order.get("orderLinkId")
                if self._is_ours(order_link_id):
                    self.pending_orders[order_link_id] = {
                        "order_id": order.get("orderId"),
                        "status": order.get("orderStatus"),
                        "qty": Decimal(order.get("qty", "0")),
                        "price": Decimal(order.get("price", "0"))
                    }
        except Exception as e:
            self.logger.error(f"{NEON_RED}Error checking open orders: {e}{RESET}")

class PositionHeartbeat:
    def __init__(self, symbol: str, pybit: PybitTradingClient, logger: logging.Logger, cfg: dict, pm: PositionManager):
        self.symbol = symbol
        self.pybit = pybit
        self.logger = logger
        self.cfg = cfg
        self.pm = pm
        self._last_ms = 0

    def tick(self):
        hb_cfg = self.cfg["execution"]["live_sync"]["heartbeat"]
        if not (hb_cfg.get("enabled", True) and self.pybit and self.pybit.enabled): return
        if self.pybit.dry_run:
            self.logger.debug(f"{NEON_BLUE}DRY RUN: Simulating heartbeat tick.{RESET}")
            return # No actual heartbeat in dry run
        
        now_ms = int(time.time() * 1000)
        if now_ms - self._last_ms < int(hb_cfg.get("interval_ms", 5000)): return
        
        self._last_ms = now_ms
        try:
            resp = self.pybit.get_positions(self.symbol)
            if not self.pybit._ok(resp): return
            
            lst = (resp.get("result", {}) or {}).get("list", [])
            
            # Calculate net quantity from exchange positions
            net_qty = Decimal("0")
            for p in lst:
                size = Decimal(p.get("size", "0"))
                if size > 0: # Only consider open positions
                    net_qty += size if p.get("side") == "Buy" else -size
            
            local_open_pos = next((p for p in self.pm.open_positions if p.get("status") == "OPEN"), None)
            
            # Scenario 1: Exchange flat, but local position exists (local position was not closed by bot logic)
            if net_qty.is_zero() and local_open_pos:
                local_open_pos.update({"status": "CLOSED", "closed_by": "HEARTBEAT_SYNC_EXCHANGE_FLAT"})
                self.logger.info(f"{NEON_PURPLE}Heartbeat: Closed local position (exchange is flat).{RESET}")
                self.pm.open_positions = [p for p in self.pm.open_positions if p.get("status") == "OPEN"]
            
            # Scenario 2: Exchange has position, but no local position (bot restarted or missed an entry)
            elif not net_qty.is_zero() and not local_open_pos:
                # Assuming only one position for simplicity. If multiple, this would need more complex reconciliation.
                if lst:
                    exchange_pos = lst[0] # Take the first one if multiple are returned
                    avg_price = Decimal(exchange_pos.get("avgPrice", "0"))
                    side = "BUY" if net_qty > 0 else "SELL"
                    
                    synt = {
                        "entry_time": datetime.now(TIMEZONE), 
                        "symbol": self.symbol, 
                        "side": side,
                        "entry_price": round_price(avg_price, self.pm.price_precision),
                        "qty": round_qty(abs(net_qty), self.pm.qty_step or Decimal("0.0001")), 
                        "status": "OPEN",
                        "link_prefix": f"hb_{int(time.time()*1000)}", # Mark as heartbeat synthetic
                        "initial_stop_loss": Decimal("0"), # Placeholder, would need to fetch/set
                        "atr_at_entry": Decimal("0"), # Placeholder
                        "best_price": avg_price # Initialize best price for trailing stop
                    }
                    self.pm.open_positions.append(synt)
                    self.logger.warning(f"{NEON_YELLOW}Heartbeat: Created synthetic local position from exchange. {side} {abs(net_qty)} @ {avg_price}{RESET}")
            
            # Scenario 3: Both local and exchange positions exist, but quantities differ (e.g., partial fills missed)
            elif not net_qty.is_zero() and local_open_pos:
                # This is a complex reconciliation. For now, log a warning.
                # A full implementation would try to update local_open_pos.qty to match net_qty
                # and potentially re-evaluate SL/TP orders on exchange.
                if abs(local_open_pos["qty"] - abs(net_qty)) > Decimal("0.0001"): # Tolerance for floating point
                    self.logger.warning(f"{NEON_YELLOW}Heartbeat: Local position qty ({local_open_pos['qty']}) differs from exchange ({abs(net_qty)}). Needs manual check or more robust sync logic.{RESET}")

        except (pybit.exceptions.FailedRequestError, Exception) as e:
            self.logger.error(f"{NEON_RED}Heartbeat error: {e}{RESET}")

# --- Trading Analysis ---
class TradingAnalyzer:
    def __init__(self, df: pd.DataFrame, config: dict[str, Any], logger: logging.Logger, symbol: str):
        self.df = df.copy()
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.indicator_values: dict[str, Any] = {}
        self.weights = config["weight_sets"]["default_scalping"]
        self.indicator_settings = config["indicator_settings"]
        self.market_regime = "UNKNOWN"
        
        if self.df.empty:
            self.logger.warning(f"{NEON_YELLOW}TradingAnalyzer initialized with empty DataFrame for {self.symbol}. Skipping indicator calculations.{RESET}")
            return
        
        self._calculate_all_indicators()

    def _safe_calculate(self, func: callable, name: str, *args, **kwargs) -> Any | None:
        try:
            # Pass self.df as the first argument if the function expects it
            if 'df' in func.__code__.co_varnames and func.__code__.co_varnames[0] == 'df':
                result = func(self.df, *args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            is_empty = (result is None or 
                       (isinstance(result, pd.Series) and result.empty) or
                       (isinstance(result, tuple) and all(r is None or (isinstance(r, pd.Series) and r.empty) for r in result)))
            
            if is_empty:
                self.logger.debug(f"{NEON_YELLOW}[{self.symbol}] Indicator '{name}' returned empty or None.{RESET}")
            
            return result if not is_empty else None
        except Exception as e:
            self.logger.error(f"{NEON_RED}[{self.symbol}] Error calculating '{name}': {e}{RESET}")
            return None

    def _calculate_all_indicators(self) -> None:
        self.logger.debug(f"[{self.symbol}] Calculating all technical indicators...")
        cfg = self.config
        isd = self.indicator_settings

        # Calculate volatility indicators first as ATR is often used
        self.df["TR"] = self._safe_calculate(indicators.calculate_true_range, "TR", df=self.df)
        self.df["ATR"] = self._safe_calculate(indicators.calculate_atr, "ATR", df=self.df, period=isd["atr_period"])
        if self.df["ATR"] is not None and not self.df["ATR"].empty: 
            self.indicator_values["ATR"] = self.df["ATR"].iloc[-1]
        
        # Calculate trend indicators
        if cfg["indicators"].get("sma_10", False):
            self.df["SMA_10"] = self._safe_calculate(indicators.calculate_sma, "SMA_10", df=self.df, period=isd["sma_short_period"])
            if self.df["SMA_10"] is not None and not self.df["SMA_10"].empty: 
                self.indicator_values["SMA_10"] = self.df["SMA_10"].iloc[-1]
        
        if cfg["indicators"].get("sma_trend_filter", False):
            self.df["SMA_Long"] = self._safe_calculate(indicators.calculate_sma, "SMA_Long", df=self.df, period=isd["sma_long_period"])
            if self.df["SMA_Long"] is not None and not self.df["SMA_Long"].empty: 
                self.indicator_values["SMA_Long"] = self.df["SMA_Long"].iloc[-1]
        
        if cfg["indicators"].get("ema_alignment", False):
            self.df["EMA_Short"] = self._safe_calculate(indicators.calculate_ema, "EMA_Short", df=self.df, period=isd["ema_short_period"])
            self.df["EMA_Long"] = self._safe_calculate(indicators.calculate_ema, "EMA_Long", df=self.df, period=isd["ema_long_period"])
            if self.df["EMA_Short"] is not None and not self.df["EMA_Short"].empty: 
                self.indicator_values["EMA_Short"] = self.df["EMA_Short"].iloc[-1]
            if self.df["EMA_Long"] is not None and not self.df["EMA_Long"].empty: 
                self.indicator_values["EMA_Long"] = self.df["EMA_Long"].iloc[-1]
        
        # Calculate momentum indicators
        if cfg["indicators"].get("rsi", False):
            self.df["RSI"] = self._safe_calculate(indicators.calculate_rsi, "RSI", df=self.df, period=isd["rsi_period"])
            if self.df["RSI"] is not None and not self.df["RSI"].empty: 
                self.indicator_values["RSI"] = self.df["RSI"].iloc[-1]
        
        if cfg["indicators"].get("stoch_rsi", False):
            stoch_rsi_k, stoch_rsi_d = self._safe_calculate(
                indicators.calculate_stoch_rsi, "StochRSI", df=self.df,
                period=isd["stoch_rsi_period"], 
                k_period=isd["stoch_k_period"], 
                d_period=isd["stoch_d_period"]
            )
            if stoch_rsi_k is not None and not stoch_rsi_k.empty: 
                self.df["StochRSI_K"] = stoch_rsi_k
                self.indicator_values["StochRSI_K"] = stoch_rsi_k.iloc[-1]
            if stoch_rsi_d is not None and not stoch_rsi_d.empty: 
                self.df["StochRSI_D"] = stoch_rsi_d
                self.indicator_values["StochRSI_D"] = stoch_rsi_d.iloc[-1]
        
        if cfg["indicators"].get("bollinger_bands", False):
            bb_upper, bb_middle, bb_lower = self._safe_calculate(
                indicators.calculate_bollinger_bands, "BollingerBands", df=self.df,
                period=isd["bollinger_bands_period"], 
                std_dev=isd["bollinger_bands_std_dev"]
            )
            if bb_upper is not None and not bb_upper.empty: 
                self.df["BB_Upper"] = bb_upper
                self.indicator_values["BB_Upper"] = bb_upper.iloc[-1]
            if bb_middle is not None and not bb_middle.empty: 
                self.df["BB_Middle"] = bb_middle
                self.indicator_values["BB_Middle"] = bb_middle.iloc[-1]
            if bb_lower is not None and not bb_lower.empty: 
                self.df["BB_Lower"] = bb_lower
                self.indicator_values["BB_Lower"] = bb_lower.iloc[-1]
        
        if cfg["indicators"].get("cci", False):
            self.df["CCI"] = self._safe_calculate(indicators.calculate_cci, "CCI", df=self.df, period=isd["cci_period"])
            if self.df["CCI"] is not None and not self.df["CCI"].empty: 
                self.indicator_values["CCI"] = self.df["CCI"].iloc[-1]
        
        if cfg["indicators"].get("wr", False):
            self.df["WR"] = self._safe_calculate(indicators.calculate_williams_r, "WR", df=self.df, period=isd["williams_r_period"])
            if self.df["WR"] is not None and not self.df["WR"].empty: 
                self.indicator_values["WR"] = self.df["WR"].iloc[-1]
        
        if cfg["indicators"].get("mfi", False):
            self.df["MFI"] = self._safe_calculate(indicators.calculate_mfi, "MFI", df=self.df, period=isd["mfi_period"])
            if self.df["MFI"] is not None and not self.df["MFI"].empty: 
                self.indicator_values["MFI"] = self.df["MFI"].iloc[-1]
        
        # Calculate volume indicators
        if cfg["indicators"].get("obv", False):
            obv_val, obv_ema = self._safe_calculate(
                indicators.calculate_obv, "OBV", df=self.df,
                ema_period=isd["obv_ema_period"]
            )
            if obv_val is not None and not obv_val.empty: 
                self.df["OBV"] = obv_val
                self.indicator_values["OBV"] = obv_val.iloc[-1]
            if obv_ema is not None and not obv_ema.empty: 
                self.df["OBV_EMA"] = obv_ema
                self.indicator_values["OBV_EMA"] = obv_ema.iloc[-1]
        
        if cfg["indicators"].get("cmf", False):
            cmf_val = self._safe_calculate(indicators.calculate_cmf, "CMF", df=self.df, period=isd["cmf_period"])
            if cmf_val is not None and not cmf_val.empty: 
                self.indicator_values["CMF"] = cmf_val
                self.indicator_values["CMF"] = cmf_val.iloc[-1]
        
        # Calculate trend-following indicators
        if cfg["indicators"].get("ichimoku_cloud", False):
            tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span = self._safe_calculate(
                indicators.calculate_ichimoku_cloud, "IchimokuCloud", df=self.df,
                tenkan_period=isd["ichimoku_tenkan_period"], 
                kijun_period=isd["ichimoku_kijun_period"], 
                senkou_span_b_period=isd["ichimoku_senkou_span_b_period"], 
                chikou_span_offset=isd["ichimoku_chikou_span_offset"]
            )
            if tenkan_sen is not None and not tenkan_sen.empty: 
                self.df["Tenkan_Sen"] = tenkan_sen
                self.indicator_values["Tenkan_Sen"] = tenkan_sen.iloc[-1]
            if kijun_sen is not None and not kijun_sen.empty: 
                self.df["Kijun_Sen"] = kijun_sen
                self.indicator_values["Kijun_Sen"] = kijun_sen.iloc[-1]
            if senkou_span_a is not None and not senkou_span_a.empty: 
                self.df["Senkou_Span_A"] = senkou_span_a
                self.indicator_values["Senkou_Span_A"] = senkou_span_a.iloc[-1]
            if senkou_span_b is not None and not senkou_span_b.empty: 
                self.df["Senkou_Span_B"] = senkou_span_b
                self.indicator_values["Senkou_Span_B"] = senkou_span_b.iloc[-1]
            if chikou_span is not None and not chikou_span.empty: 
                self.df["Chikou_Span"] = chikou_span
                self.indicator_values["Chikou_Span"] = chikou_span.fillna(0).iloc[-1]
        
        if cfg["indicators"].get("psar", False):
            psar_val, psar_dir = self._safe_calculate(
                indicators.calculate_psar, "PSAR", df=self.df,
                acceleration=isd["psar_acceleration"], 
                max_acceleration=isd["psar_max_acceleration"]
            )
            if psar_val is not None and not psar_val.empty: 
                self.df["PSAR_Val"] = psar_val
                self.indicator_values["PSAR_Val"] = psar_val.iloc[-1]
            if psar_dir is not None and not psar_dir.empty: 
                self.df["PSAR_Dir"] = psar_dir
                self.indicator_values["PSAR_Dir"] = psar_dir.iloc[-1]
        
        if cfg["indicators"].get("vwap", False):
            self.df["VWAP"] = self._safe_calculate(indicators.calculate_vwap, "VWAP", df=self.df)
            if self.df["VWAP"] is not None and not self.df["VWAP"].empty: 
                self.indicator_values["VWAP"] = self.df["VWAP"].iloc[-1]
        
        if cfg["indicators"].get("ehlers_supertrend", False):
            st_fast_result = self._safe_calculate(
                indicators.calculate_ehlers_supertrend, "EhlersSuperTrendFast", df=self.df,
                period=isd["ehlers_fast_period"], 
                multiplier=isd["ehlers_fast_multiplier"]
            )
            if st_fast_result is not None and not st_fast_result.empty: 
                self.df["st_fast_dir"] = st_fast_result["direction"]
                self.df["st_fast_val"] = st_fast_result["supertrend"]
                self.indicator_values["ST_Fast_Dir"] = st_fast_result["direction"].iloc[-1]
                self.indicator_values["ST_Fast_Val"] = st_fast_result["supertrend"].iloc[-1]
            
            st_slow_result = self._safe_calculate(
                indicators.calculate_ehlers_supertrend, "EhlersSuperTrendSlow", df=self.df,
                period=isd["ehlers_slow_period"], 
                multiplier=isd["ehlers_slow_multiplier"]
            )
            if st_slow_result is not None and not st_slow_result.empty: 
                self.df["st_slow_dir"] = st_slow_result["direction"]
                self.df["st_slow_val"] = st_slow_result["supertrend"]
                self.indicator_values["ST_Slow_Dir"] = st_slow_result["direction"].iloc[-1]
                self.indicator_values["ST_Slow_Val"] = st_slow_result["supertrend"].iloc[-1]
        
        if cfg["indicators"].get("macd", False):
            macd_line, signal_line, histogram = self._safe_calculate(
                indicators.calculate_macd, "MACD", df=self.df,
                fast_period=isd["macd_fast_period"], 
                slow_period=isd["macd_slow_period"], 
                signal_period=isd["macd_signal_period"]
            )
            if macd_line is not None and not macd_line.empty: 
                self.df["MACD_Line"] = macd_line
                self.indicator_values["MACD_Line"] = macd_line.iloc[-1]
            if signal_line is not None and not signal_line.empty: 
                self.df["MACD_Signal"] = signal_line
                self.indicator_values["MACD_Signal"] = signal_line.iloc[-1]
            if histogram is not None and not histogram.empty: 
                self.df["MACD_Hist"] = histogram
                self.indicator_values["MACD_Hist"] = histogram.iloc[-1]
        
        if cfg["indicators"].get("adx", False):
            adx_val, plus_di, minus_di = self._safe_calculate(
                indicators.calculate_adx, "ADX", df=self.df,
                period=isd["adx_period"]
            )
            if adx_val is not None and not adx_val.empty: 
                self.df["ADX"] = adx_val
                self.indicator_values["ADX"] = adx_val.iloc[-1]
            if plus_di is not None and not plus_di.empty: 
                self.df["PlusDI"] = plus_di
                self.indicator_values["PlusDI"] = plus_di.iloc[-1]
            if minus_di is not None and not minus_di.empty: 
                self.df["MinusDI"] = minus_di
                self.indicator_values["MinusDI"] = minus_di.iloc[-1]
        
        # Calculate other indicators
        if cfg["indicators"].get("volatility_index", False):
            self.df["Volatility_Index"] = self._safe_calculate(
                indicators.calculate_volatility_index, "Volatility_Index", df=self.df,
                period=isd["volatility_index_period"]
            )
            if self.df["Volatility_Index"] is not None and not self.df["Volatility_Index"].empty: 
                self.indicator_values["Volatility_Index"] = self.df["Volatility_Index"].iloc[-1]
        
        if cfg["indicators"].get("vwma", False):
            self.df["VWMA"] = self._safe_calculate(
                indicators.calculate_vwma, "VWMA", df=self.df,
                period=isd["vwma_period"]
            )
            if self.df["VWMA"] is not None and not self.df["VWMA"].empty: 
                self.indicator_values["VWMA"] = self.df["VWMA"].iloc[-1]
        
        if cfg["indicators"].get("volume_delta", False):
            self.df["Volume_Delta"] = self._safe_calculate(
                indicators.calculate_volume_delta, "Volume_Delta", df=self.df,
                period=isd["volume_delta_period"]
            )
            if self.df["Volume_Delta"] is not None and not self.df["Volume_Delta"].empty: 
                self.indicator_values["Volume_Delta"] = self.df["Volume_Delta"].iloc[-1]

        if cfg["indicators"].get("fibonacci_levels", False):
            # Assumes indicators.py has a calculate_fibonacci_levels function
            # that returns a dictionary of levels or a DataFrame.
            # Example: {'0.0': price, '0.236': price, ...}
            fib_levels = self._safe_calculate(indicators.calculate_fibonacci_levels, "FibonacciLevels", df=self.df, window=isd["fibonacci_window"])
            if fib_levels:
                self.indicator_values["Fibonacci_Levels"] = fib_levels

        # Clean up data
        self.df.dropna(subset=["close"], inplace=True)
        self.df.fillna(0, inplace=True)
        
        if self.df.empty: 
            self.logger.warning(f"{NEON_YELLOW}DataFrame empty after indicator calculations for {self.symbol}.{RESET}")

    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        return self.indicator_values.get(key, default)

    def _check_orderbook(self, current_price: Decimal, orderbook_data: dict) -> float:
        # Pybit WebSocket orderbook data format is typically {'s': 'symbol', 'b': [[price, qty], ...], 'a': [[price, qty], ...]}
        bids = orderbook_data.get("b", [])
        asks = orderbook_data.get("a", [])
        
        bid_volume = sum(Decimal(b[1]) for b in bids)
        ask_volume = sum(Decimal(a[1]) for a in asks)
        
        if bid_volume + ask_volume == 0: return 0.0
        imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
        return float(imbalance)

    def _nz(self, x, default=np.nan):
        try: return float(x)
        except (ValueError, TypeError): return default

    def _clip(self, x, lo=-1.0, hi=1.0):
        return float(np.clip(x, lo, hi))

    def _safe_prev(self, series_name: str, default=np.nan):
        s = self.df.get(series_name)
        if s is None or len(s) < 2: return default, default
        return float(s.iloc[-1]), float(s.iloc[-2])

    def _market_regime(self):
        adx = self._nz(self._get_indicator_value("ADX"))
        bb_u = self._nz(self._get_indicator_value("BB_Upper"))
        bb_l = self._nz(self._get_indicator_value("BB_Lower"))
        bb_m = self._nz(self._get_indicator_value("BB_Middle"))
        
        # Calculate band width
        band = (bb_u - bb_l) / bb_m if bb_m and bb_m != 0 else 0
        
        # Determine market regime
        # ADX > 23 typically indicates a trending market
        # A wide Bollinger Band (e.g., band > 0.03 for 3%) can also indicate trending
        if adx >= 23 or band >= 0.03: 
            self.market_regime = "TRENDING"
        else: 
            self.market_regime = "RANGING"
        
        return self.market_regime

    def _volume_confirm(self):
        try:
            vol_now = float(self.df["volume"].iloc[-1])
            if len(self.df["volume"]) < 20: # Ensure enough data for rolling mean
                return False
            vol_ma = float(self.df["volume"].rolling(20).mean().iloc[-1])
            mult = float(self.config.get("volume_confirmation_multiplier", 1.5))
            return vol_now > mult * vol_ma if vol_ma > 0 else False
        except Exception: return False

    def _orderbook_score(self, orderbook_data, weight):\
        if not orderbook_data: return 0.0, None
        imb = self._clip(self._check_orderbook(Decimal(str(self.df['close'].iloc[-1])), orderbook_data))
        if abs(imb) < 0.05: return 0.0, None # Filter out negligible imbalance
        return weight * imb, f"OB Imbalance {imb:+.2f}"

    def _mtf_confluence(self, mtf_trends: dict[str, str], weight):\
        if not mtf_trends: return 0.0, None
        bulls = sum(1 for v in mtf_trends.values() if isinstance(v, str) and v.upper().startswith("BULL"))
        bears = sum(1 for v in mtf_trends.values() if isinstance(v, str) and v.upper().startswith("BEAR"))
        total = bulls + bears
        if total == 0: return 0.0, None
        net = (bulls - bears) / total
        return weight * net, f"MTF Confluence {net:+.2f} ({bulls}:{bears})"

    def _dynamic_threshold(self, base_threshold: float) -> float:
        atr_now = self._nz(self._get_indicator_value("ATR"), 0.0)
        # Ensure 'ATR' series exists and has enough data for rolling mean
        if "ATR" not in self.df or len(self.df["ATR"]) < 50 or self.df["ATR"].rolling(50).mean().empty: 
            return base_threshold
        atr_ma = float(self.df["ATR"].rolling(50).mean().iloc[-1])
        if atr_ma <= 0: return base_threshold
        ratio = float(np.clip(atr_now / atr_ma, 0.9, 1.5)) # Clip ratio to prevent extreme thresholds
        return base_threshold * ratio

    def generate_trading_signal(self, current_price: Decimal, orderbook_data: dict | None, mtf_trends: dict[str, str]) -> tuple[str, float]:
        if self.df.empty: return "HOLD", 0.0
        
        active, isd = self.config["indicators"], self.indicator_settings
        score, notes_buy, notes_sell = 0.0, [], []
        close = float(self.df["close"].iloc[-1])
        regime = self._market_regime()

        # --- Contextual Weighting ---
        # Adjust weights based on market regime for a more adaptive strategy
        current_weights = self.weights.copy()
        trend_boost = 0.2 # How much to boost/reduce weights
        
        if regime == "TRENDING":
            self.logger.debug(f"{NEON_BLUE}Applying TRENDING regime weights.{RESET}")
            for k in ["ema_alignment", "sma_trend_filter", "ehlers_supertrend_alignment", "macd_alignment", 
                      "adx_strength", "ichimoku_confluence", "psar", "vwap", "vwma_cross", "sma_10", 
                      "obv_momentum", "cmf_flow", "volume_delta_signal", "mtf_trend_confluence"]:
                current_weights[k] = current_weights.get(k, 0) * (1 + trend_boost)
            current_weights["bollinger_bands"] = current_weights.get("bollinger_bands", 0) * (1 - trend_boost)
            current_weights["momentum_rsi_stoch_cci_wr_mfi"] = current_weights.get("momentum_rsi_stoch_cci_wr_mfi", 0) * (1 + trend_boost/2)
            current_weights["fibonacci_confluence"] = current_weights.get("fibonacci_confluence", 0) * (1 - trend_boost/2) # Less emphasis on fibs in strong trends
        elif regime == "RANGING":
            self.logger.debug(f"{NEON_BLUE}Applying RANGING regime weights.{RESET}")
            for k in ["ema_alignment", "sma_trend_filter", "ehlers_supertrend_alignment", "macd_alignment", 
                      "adx_strength", "ichimoku_confluence", "psar", "vwap", "vwma_cross", "sma_10", 
                      "obv_momentum", "cmf_flow", "volume_delta_signal", "mtf_trend_confluence"]:
                current_weights[k] = current_weights.get(k, 0) * (1 - trend_boost)
            current_weights["bollinger_bands"] = current_weights.get("bollinger_bands", 0) * (1 + trend_boost)
            current_weights["momentum_rsi_stoch_cci_wr_mfi"] = current_weights.get("momentum_rsi_stoch_cci_wr_mfi", 0) * (1 + trend_boost)
            current_weights["fibonacci_confluence"] = current_weights.get("fibonacci_confluence", 0) * (1 + trend_boost) # More emphasis on fibs in ranging markets
        # --- End Contextual Weighting ---

        # Trend indicators
        if active.get("ema_alignment"):
            es, el = self._nz(self._get_indicator_value("EMA_Short")), self._nz(self._get_indicator_value("EMA_Long"))
            if not np.isnan(es) and not np.isnan(el):
                if es > el: 
                    score += current_weights.get("ema_alignment", 0)
                    notes_buy.append(f"EMA Bull +{current_weights.get('ema_alignment',0):.2f}")
                elif es < el: 
                    score -= current_weights.get("ema_alignment", 0)
                    notes_sell.append(f"EMA Bear -{current_weights.get('ema_alignment',0):.2f}")
        
        if active.get("sma_trend_filter"):
            sma_long = self._nz(self._get_indicator_value("SMA_Long"))
            if not np.isnan(sma_long):
                if close > sma_long: 
                    score += current_weights.get("sma_trend_filter", 0)
                    notes_buy.append(f"SMA Trend Bull +{current_weights.get('sma_trend_filter',0):.2f}")
                elif close < sma_long: 
                    score -= current_weights.get("sma_trend_filter", 0)
                    notes_sell.append(f"SMA Trend Bear -{current_weights.get('sma_trend_filter',0):.2f}")
        
        if active.get("ehlers_supertrend"):
            st_fast_dir, st_slow_dir = self._get_indicator_value("ST_Fast_Dir"), self._get_indicator_value("ST_Slow_Dir")
            if st_fast_dir == 1 and st_slow_dir == 1: 
                score += current_weights.get("ehlers_supertrend_alignment", 0)
                notes_buy.append(f"EhlersST Bull +{current_weights.get('ehlers_supertrend_alignment',0):.2f}")
            elif st_fast_dir == -1 and st_slow_dir == -1: 
                score -= current_weights.get("ehlers_supertrend_alignment", 0)
                notes_sell.append(f"EhlersST Bear -{current_weights.get('ehlers_supertrend_alignment',0):.2f}")
        
        if active.get("macd"):
            macd, signal = self._nz(self._get_indicator_value("MACD_Line")), self._nz(self._get_indicator_value("MACD_Signal"))
            hist, prev_hist = self._safe_prev("MACD_Hist")
            if not np.isnan(macd) and not np.isnan(signal) and not np.isnan(hist) and not np.isnan(prev_hist):
                if macd > signal and hist > 0 and prev_hist <= 0: # Bullish crossover and histogram turning positive
                    score += current_weights.get("macd_alignment", 0)
                    notes_buy.append(f"MACD Bull Cross +{current_weights.get('macd_alignment',0):.2f}")
                elif macd < signal and hist < 0 and prev_hist >= 0: # Bearish crossover and histogram turning negative
                    score -= current_weights.get("macd_alignment", 0)
                    notes_sell.append(f"MACD Bear Cross -{current_weights.get('macd_alignment',0):.2f}")
        
        if active.get("adx"):
            adx, pdi, mdi = self._nz(self._get_indicator_value("ADX")), self._nz(self._get_indicator_value("PlusDI")), self._nz(self._get_indicator_value("MinusDI"))
            if not np.isnan(adx) and adx > 20: # ADX > 20 indicates a trend
                if pdi > mdi: 
                    score += current_weights.get("adx_strength", 0) * (adx/50.0) # Scale strength by ADX value
                    notes_buy.append(f"ADX Bull {adx:.1f} +{current_weights.get('adx_strength',0) * (adx/50.0):.2f}\"")
                else: 
                    score -= current_weights.get("adx_strength", 0) * (adx/50.0)
                    notes_sell.append(f"ADX Bear {adx:.1f} -{current_weights.get('adx_strength',0) * (adx/50.0):.2f}\"")
        
        if active.get("ichimoku_cloud"):
            tenkan, kijun, span_a, span_b, chikou = (
                self._nz(self._get_indicator_value("Tenkan_Sen")), 
                self._nz(self._get_indicator_value("Kijun_Sen")), 
                self._nz(self._get_indicator_value("Senkou_Span_A")), 
                self._nz(self._get_indicator_value("Senkou_Span_B")), 
                self._nz(self._get_indicator_value("Chikou_Span"))
            )
            # Check for NaN values before using them
            if not any(np.isnan(x) for x in [tenkan, kijun, span_a, span_b, chikou]):
                if close > span_a and close > span_b and tenkan > kijun and chikou > close: 
                    score += current_weights.get("ichimoku_confluence", 0)
                    notes_buy.append(f"Ichimoku Bull +{current_weights.get('ichimoku_confluence',0):.2f}")
                elif close < span_a and close < span_b and tenkan < kijun and chikou < close: 
                    score -= current_weights.get("ichimoku_confluence", 0)
                    notes_sell.append(f"Ichimoku Bear -{current_weights.get('ichimoku_confluence',0):.2f}")
        
        # Momentum indicators
        if active.get("psar"):
            if self._get_indicator_value("PSAR_Dir") == 1: 
                score += current_weights.get("psar", 0)
                notes_buy.append(f"PSAR Bull +{current_weights.get('psar',0):.2f}")
            elif self._get_indicator_value("PSAR_Dir") == -1: 
                score -= current_weights.get("psar", 0)
                notes_sell.append(f"PSAR Bear -{current_weights.get('psar',0):.2f}")
        
        # Volume indicators
        if active.get("vwap"):
            vwap = self._nz(self._get_indicator_value("VWAP"))
            if not np.isnan(vwap):
                if close > vwap: 
                    score += current_weights.get("vwap", 0)
                    notes_buy.append(f"VWAP Bull +{current_weights.get('vwap',0):.2f}")
                elif close < vwap: 
                    score -= current_weights.get("vwap", 0)
                    notes_sell.append(f"VWAP Bear -{current_weights.get('vwap',0):.2f}")
        
        if active.get("vwma"):
            vwma, sma = self._nz(self._get_indicator_value("VWMA")), self._nz(self._get_indicator_value("SMA_10"))
            if not np.isnan(vwma) and not np.isnan(sma):
                if vwma > sma: 
                    score += current_weights.get("vwma_cross", 0)
                    notes_buy.append(f"VWMA Cross Bull +{current_weights.get('vwma_cross',0):.2f}")
                elif vwma < sma: 
                    score -= current_weights.get("vwma_cross", 0)
                    notes_sell.append(f"VWMA Cross Bear -{current_weights.get('vwma_cross',0):.2f}")
        
        if active.get("sma_10"):
            sma10 = self._nz(self._get_indicator_value("SMA_10"))
            if not np.isnan(sma10):
                if close > sma10: 
                    score += current_weights.get("sma_10", 0)
                    notes_buy.append(f"SMA10 Bull +{current_weights.get('sma_10',0):.2f}")
                elif close < sma10: 
                    score -= current_weights.get("sma_10", 0)
                    notes_sell.append(f"SMA10 Bear -{current_weights.get('sma_10',0):.2f}")
        
        # Oscillator indicators
        if active.get("momentum"):
            mom_score_raw = 0 # sum of individual oscillator signals (-5 to +5)
            
            # RSI
            rsi = self._nz(self._get_indicator_value("RSI"))
            if not np.isnan(rsi):
                if rsi < isd.get("rsi_oversold", 30): mom_score_raw += 1
                elif rsi > isd.get("rsi_overbought", 70): mom_score_raw -= 1
            
            # Stochastic RSI
            stoch_k, stoch_d = self._nz(self._get_indicator_value("StochRSI_K")), self._nz(self._get_indicator_value("StochRSI_D"))
            if not np.isnan(stoch_k) and not np.isnan(stoch_d):
                if stoch_k > stoch_d and stoch_k < isd.get("stoch_rsi_oversold", 20): mom_score_raw += 1
                elif stoch_k < stoch_d and stoch_k > isd.get("stoch_rsi_overbought", 80): mom_score_raw -= 1
            
            # CCI
            cci = self._nz(self._get_indicator_value("CCI"))
            if not np.isnan(cci):
                if cci < isd.get("cci_oversold", -100): mom_score_raw += 1
                elif cci > isd.get("cci_overbought", 100): mom_score_raw -= 1
            
            # Williams %R
            wr = self._nz(self._get_indicator_value("WR"))
            if not np.isnan(wr):
                if wr < isd.get("williams_r_oversold", -80): mom_score_raw += 1
                elif wr > isd.get("williams_r_overbought", -20): mom_score_raw -= 1
            
            # MFI
            mfi = self._nz(self._get_indicator_value("MFI"))
            if not np.isnan(mfi):
                if mfi < isd.get("mfi_oversold", 20): mom_score_raw += 1
                elif mfi > isd.get("mfi_overbought", 80): mom_score_raw -= 1
            
            final_mom_score = current_weights.get("momentum_rsi_stoch_cci_wr_mfi", 0) * self._clip(mom_score_raw / 5.0)
            score += final_mom_score
            if final_mom_score > 0: 
                notes_buy.append(f"Momentum Bull +{final_mom_score:.2f}")
            elif final_mom_score < 0: 
                notes_sell.append(f"Momentum Bear {final_mom_score:.2f}")
        
        # Reversal indicators (only in ranging market)
        if active.get("bollinger_bands") and regime == "RANGING":
            bb_u, bb_l = self._nz(self._get_indicator_value("BB_Upper")), self._nz(self._get_indicator_value("BB_Lower"))
            if not np.isnan(bb_u) and not np.isnan(bb_l):
                if close < bb_l: 
                    score += current_weights.get("bollinger_bands", 0)
                    notes_buy.append(f"BB Reversal Bull +{current_weights.get('bollinger_bands',0):.2f}")
                elif close > bb_u: 
                    score -= current_weights.get("bollinger_bands", 0)
                    notes_sell.append(f"BB Reversal Bear -{current_weights.get('bollinger_bands',0):.2f}")
        
        # Volume confirmation
        if active.get("volume_confirmation") and self._volume_confirm():
            score_change = current_weights.get("volume_confirmation", 0)
            if score > 0: # Only add if current score is positive
                score += score_change
                notes_buy.append(f"Vol Confirm +{score_change:.2f}")
            elif score < 0: # Only subtract if current score is negative
                score -= score_change
                notes_sell.append(f"Vol Confirm -{score_change:.2f}")
        
        # On-Balance Volume
        if active.get("obv"):
            obv, obv_ema = self._nz(self._get_indicator_value("OBV")), self._nz(self._get_indicator_value("OBV_EMA"))
            if not np.isnan(obv) and not np.isnan(obv_ema):
                if obv > obv_ema: 
                    score += current_weights.get("obv_momentum", 0)
                    notes_buy.append(f"OBV Bull +{current_weights.get('obv_momentum',0):.2f}")
                elif obv < obv_ema: 
                    score -= current_weights.get("obv_momentum", 0)
                    notes_sell.append(f"OBV Bear -{current_weights.get('obv_momentum',0):.2f}")
        
        # Chaikin Money Flow
        if active.get("cmf"):
            cmf = self._nz(self._get_indicator_value("CMF"))
            if not np.isnan(cmf) and cmf > 0.05: 
                score += current_weights.get("cmf_flow", 0)
                notes_buy.append(f"CMF Bull +{current_weights.get('cmf_flow',0):.2f}")
            elif not np.isnan(cmf) and cmf < -0.05: 
                score -= current_weights.get("cmf_flow", 0)
                notes_sell.append(f"CMF Bear -{current_weights.get('cmf_flow',0):.2f}")
        
        # Volume Delta
        if active.get("volume_delta"):
            vol_delta = self._nz(self._get_indicator_value("Volume_Delta"))
            delta_thresh = self._nz(isd.get("volume_delta_threshold", 0.2))
            if not np.isnan(vol_delta):
                if vol_delta > delta_thresh: 
                    score += current_weights.get("volume_delta_signal", 0)
                    notes_buy.append(f"VolDelta Bull +{current_weights.get('volume_delta_signal',0):.2f}")
                elif vol_delta < -delta_thresh: 
                    score -= current_weights.get("volume_delta_signal", 0)
                    notes_sell.append(f"VolDelta Bear -{current_weights.get('volume_delta_signal',0):.2f}")
        
        # Volatility Index
        if active.get("volatility_index"):
            vol_idx = self._nz(self._get_indicator_value("Volatility_Index"))
            # Ensure enough data for rolling mean
            if "Volatility_Index" in self.df and len(self.df["Volatility_Index"]) >= 50 and not self.df["Volatility_Index"].rolling(50).mean().empty:
                vol_idx_ma = self.df["Volatility_Index"].rolling(50).mean().iloc[-1]
                if not np.isnan(vol_idx) and not np.isnan(vol_idx_ma) and vol_idx > vol_idx_ma * 1.5:
                    score *= 0.75 # Dampen score in very high volatility
                    notes_buy.append("High Vol Dampen")
                    notes_sell.append("High Vol Dampen")
            
        # Orderbook imbalance
        if active.get("orderbook_imbalance"):
            ob_score, ob_note = self._orderbook_score(orderbook_data, current_weights.get("orderbook_imbalance", 0))
            score += ob_score
            if ob_note:
                if ob_score > 0: notes_buy.append(ob_note)
                else: notes_sell.append(ob_note)
        
        # Multi-timeframe analysis
        if active.get("mtf_analysis"):
            mtf_score, mtf_note = self._mtf_confluence(mtf_trends, current_weights.get("mtf_trend_confluence", 0))
            score += mtf_score
            if mtf_note:
                if mtf_score > 0: notes_buy.append(mtf_note)
                else: notes_sell.append(mtf_note)

        # Fibonacci Levels Confluence (New)
        if active.get("fibonacci_levels"):
            fib_levels = self._get_indicator_value("Fibonacci_Levels")
            if fib_levels and isinstance(fib_levels, dict):
                # Check if current price is near a key Fibonacci level
                # For simplicity, check 0.5 and 0.618 levels
                price_decimal = Decimal(str(close))
                fib_weight = current_weights.get("fibonacci_confluence", 0)
                
                if "0.5" in fib_levels and "0.618" in fib_levels:
                    level_50 = Decimal(str(fib_levels["0.5"]))
                    level_618 = Decimal(str(fib_levels["0.618"]))
                    
                    # Define a tolerance (e.g., 0.1% of price)
                    tolerance = price_decimal * Decimal("0.001")
                    
                    if abs(price_decimal - level_50) < tolerance or abs(price_decimal - level_618) < tolerance:
                        # If price is near a fib level, it might act as support/resistance
                        # This scoring needs to be carefully designed based on strategy
                        if regime == "RANGING": # Fib levels might be more significant in ranging markets
                            # If price is below a fib level (potential support for buy)
                            if price_decimal < level_50 and price_decimal < level_618: 
                                score += fib_weight
                                notes_buy.append(f"Fib Support +{fib_weight:.2f}")
                            # If price is above a fib level (potential resistance for sell)
                            elif price_decimal > level_50 and price_decimal > level_618: 
                                score -= fib_weight
                                notes_sell.append(f"Fib Resistance -{fib_weight:.2f}")
                        # In trending, fibs might be retrace targets, adding complexity
                        
        # --- Basic Liquidity Check (Spread Filter) ---
        # This is a redundant check if already done in main loop, but good to have here for robustness
        if orderbook_data and self.config.get("risk_guardrails", {}).get("enabled", False):
            spread_bps = get_spread_bps(orderbook_data)
            max_spread = float(self.config.get("risk_guardrails", {}).get("max_spread_bps", 10.0))
            if spread_bps > max_spread:
                self.logger.warning(f"{NEON_YELLOW}Signal generation: Spread too high ({spread_bps:.1f} bps > {max_spread:.1f}). Dampening score.{RESET}")
                score *= 0.5 # Halve the score if spread is too wide
                notes_buy.append("High Spread Dampen")
                notes_sell.append("High Spread Dampen")


        # Apply dynamic threshold and hysteresis
        base_th = max(float(self.config.get("signal_score_threshold", 2.0)), 1.0)
        dyn_th = self._dynamic_threshold(base_th)
        last_score = float(self.config.get("_last_score", 0.0))
        hyster = float(self.config.get("hysteresis_ratio", 0.85))
        
        final_signal = "HOLD"
        # Apply hysteresis: if the current signal direction is opposite but not strong enough to overcome hysteresis
        if np.sign(score) != np.sign(last_score) and abs(score) < abs(last_score) * hyster:
            final_signal = "HOLD"
            self.logger.info(f"{NEON_YELLOW}Signal held by hysteresis. Score {score:.2f} vs last {last_score:.2f} * {hyster} (threshold: {abs(last_score) * hyster:.2f}){RESET}")
        else:
            if score >= dyn_th: final_signal = "BUY"
            elif score <= -dyn_th: final_signal = "SELL"
        
        # Apply cooldown
        cooldown = int(self.config.get("cooldown_sec", 0))
        now_ts, last_ts = int(time.time()), int(self.config.get("_last_signal_ts", 0))
        if cooldown > 0 and final_signal != "HOLD" and now_ts - last_ts < cooldown:
            self.logger.info(f"{NEON_YELLOW}Signal {final_signal} ignored due to cooldown ({now_ts - last_ts}s elapsed, {cooldown}s required).{RESET}")
            final_signal = "HOLD"
        
        # Update config state
        self.config["_last_score"] = float(score)
        if final_signal in ("BUY", "SELL"): self.config["_last_signal_ts"] = now_ts
        
        # Log factors
        if notes_buy: self.logger.info(f"{NEON_GREEN}Buy Factors: {', '.join(notes_buy)}{RESET}")
        if notes_sell: self.logger.info(f"{NEON_RED}Sell Factors: {', '.join(notes_sell)}{RESET}")
        self.logger.info(f"{NEON_PURPLE}Regime: {regime} | Score: {score:.2f} | DynThresh: {dyn_th:.2f} | Final: {final_signal}{RESET}")
        
        return final_signal, float(score)

# --- Helper functions for main loop ---
def get_spread_bps(orderbook):\
    try:
        # Pybit WebSocket orderbook data needs to be parsed
        # Example: {'s': 'BTCUSDT', 'b': [['26000.00', '1.5']], 'a': [['26001.00', '2.0']]}
        bids = orderbook.get("b", [])
        asks = orderbook.get("a", [])

        if not bids or not asks: return 0.0 # No bids or asks
        
        best_bid = Decimal(bids[0][0])
        best_ask = Decimal(asks[0][0])

        if best_bid.is_zero() or best_ask.is_zero() or best_bid >= best_ask:
            return 0.0

        mid = (best_ask + best_bid) / 2
        return float((best_ask - best_bid) / mid * 10000)
    except Exception as e: 
        logging.getLogger("wgwhalex_bot").warning(f"{NEON_YELLOW}Error calculating spread: {e}{RESET}")
        return 0.0

def expected_value(perf: PerformanceTracker, n=50, fee_bps=2.0, slip_bps=2.0):\
    trades = perf.trades[-n:]
    if not trades or len(trades) < 10: return 1.0  # Default to positive if not enough history
    
    wins = [Decimal(str(t["pnl"])) for t in trades if Decimal(str(t["pnl"])) > 0]
    losses = [-Decimal(str(t["pnl"])) for t in trades if Decimal(str(t["pnl"])) <= 0]
    
    # If no wins or no losses, EV calculation is skewed.
    # Return a neutral/positive EV to allow trading if there's no losing history yet.
    if not wins: return 1.0 
    if not losses: return 1.0
    
    win_rate = (len(wins) / len(trades))
    avg_win = (sum(wins) / len(wins))
    avg_loss = (sum(losses) / len(losses))
    
    cost_per_trade_factor = Decimal(str(1 + (fee_bps + slip_bps) / 10000.0)) # Assuming fees/slippage apply to both entry/exit
    
    # Simplified EV calculation: (Win Rate * Avg Win) - (Loss Rate * Avg Loss * Cost Factor)
    ev = win_rate * avg_win - (1 - win_rate) * avg_loss * cost_per_trade_factor
    return float(ev)

def in_allowed_session(cfg) -> bool:
    sess = cfg.get("session_filter", {})
    if not sess.get("enabled", False): return True
    
    now = datetime.now(TIMEZONE).strftime("%H:%M")
    for w in sess.get("utc_allowed", []):
        if w[0] <= now <= w[1]: return True
    return False

def adapt_exit_params(pt: PerformanceTracker, cfg: dict) -> tuple[Decimal, Decimal]:
    tp_mult = Decimal(str(cfg["trade_management"]["take_profit_atr_multiple"]))
    sl_mult = Decimal(str(cfg["trade_management"]["stop_loss_atr_multiple"]))
    
    recent = pt.trades[-100:]
    if not recent or len(recent) < 20: return tp_mult, sl_mult # Need sufficient data
    
    wins = [t for t in recent if Decimal(str(t.get("pnl","0"))) > 0]
    losses = [t for t in recent if Decimal(str(t.get("pnl","0"))) <= 0]
    
    if wins and losses:
        avg_win = sum(Decimal(str(t["pnl"])) for t in wins) / len(wins)
        avg_loss = -sum(Decimal(str(t["pnl"])) for t in losses) / len(losses)
        
        if avg_loss > 0:
            rr = (avg_win / avg_loss) # Risk-Reward ratio
            # Adjust TP/SL based on R:R. If R:R is low, try to increase TP or decrease SL.
            # Clamp tilt to prevent extreme adjustments.
            tilt = Decimal(min(0.5, max(-0.5, float(rr - 1.0)))) # If RR=1, tilt=0. If RR=0.5, tilt=-0.5. If RR=1.5, tilt=0.5.
            
            # Increase TP if R:R is good, decrease SL if R:R is bad
            new_tp = tp_mult + tilt
            new_sl = sl_mult - (tilt / 2) # SL adjustment is usually more sensitive
            
            # Ensure sensible minimums for multiples
            new_tp = max(Decimal("0.5"), new_tp)
            new_sl = max(Decimal("1.0"), new_sl)
            
            return new_tp, new_sl
    
    return tp_mult, sl_mult

def random_tune_weights(cfg_path="config.json", k=50, jitter=0.2):\
    print("Running random weight tuning...")
    with open(cfg_path,encoding="utf-8") as f: cfg=json.load(f)
    base = cfg["weight_sets"]["default_scalping"]
    best_cfg, best_score = base, -1e9 # Initialize with a very low score
    
    # A simple proxy score: sum of major trend indicators.
    # In a real scenario, this would involve backtesting or simulation.
    proxy_keys = ["ema_alignment","ehlers_supertrend_alignment","macd_alignment","adx_strength"]

    for _ in range(k):
        trial = {key: max(0.0, v * (1 + random.uniform(-jitter, jitter))) for key,v in base.items()}
        # For this example, we'll just use a simple sum as a proxy for "better"
        current_proxy_score = sum(trial.get(x,0) for x in proxy_keys) 
        
        if current_proxy_score > best_score:
            best_cfg, best_score = trial, current_proxy_score
    
    cfg["weight_sets"]["default_scalping"] = best_cfg
    with open(cfg_path,"w",encoding="utf-8") as f: json.dump(cfg,f,indent=4)
    print(f"New weights saved to {cfg_path}")
    return best_cfg

# --- Main Execution Logic ---
def main() -> None:
    logger = setup_logger("wgwhalex_bot", level=logging.INFO) # Set to logging.DEBUG for more verbose output
    config = load_config(CONFIG_FILE, logger)
    alert_system = AlertSystem(logger)

    logger.info(f"{NEON_GREEN}--- Wgwhalex Trading Bot Initialized ---{RESET}")
    logger.info(f"Symbol: {config['symbol']}, Interval: {config['interval']}")
    if config["execution"]["dry_run"]:
        logger.info(f"{NEON_YELLOW}--- DRY RUN MODE ACTIVE --- No real trades will be placed. ---{RESET}")

    pybit_client = PybitTradingClient(config, logger)
    position_manager = PositionManager(config, logger, config["symbol"], pybit_client)
    performance_tracker = PerformanceTracker(logger)
    
    exec_sync = None
    # Only enable exec_sync if not in dry_run and pybit client is enabled
    if config["execution"]["live_sync"]["enabled"] and pybit_client.enabled and not pybit_client.dry_run:
        exec_sync = ExchangeExecutionSync(
            config["symbol"], 
            pybit_client, 
            logger, 
            config, 
            position_manager, 
            performance_tracker
        )
    
    heartbeat = None
    # Only enable heartbeat if not in dry_run and pybit client is enabled
    if config["execution"]["live_sync"]["heartbeat"]["enabled"] and pybit_client.enabled and not pybit_client.dry_run:
        heartbeat = PositionHeartbeat(
            config["symbol"], 
            pybit_client, 
            logger, 
            config, 
            position_manager
        )

    try: # Wrap main loop in try-finally for graceful WebSocket shutdown
        while True:
            logger.info(f"{NEON_PURPLE}--- New Loop ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}) ---{RESET}")

            # Check risk limits
            risk_ok, risk_msg = position_manager.check_risk_limits()
            if not risk_ok:
                logger.error(f"{NEON_RED}KILL SWITCH: {risk_msg}. Cooling down.{RESET}")
                alert_system.send_alert(f"Bot Kill Switch Activated: {risk_msg}", "CRITICAL")
                time.sleep(int(config.get("risk_guardrails", {}).get("cooldown_after_kill_min", 120)) * 60)
                continue

            # Check session filter
            if not in_allowed_session(config):
                logger.info(f"{NEON_BLUE}Outside allowed session. Holding.{RESET}")
                time.sleep(config["loop_delay"])
                continue

            # Fetch current price
            current_price = pybit_client.fetch_current_price(config["symbol"])
            if current_price is None: 
                logger.warning(f"{NEON_YELLOW}Failed to fetch current price. Retrying in {config['loop_delay']}s.{RESET}")
                time.sleep(config["loop_delay"])
                continue

            # Fetch klines data
            df = pybit_client.fetch_klines(config["symbol"], config["interval"], 200) # Increased limit for more robust indicator calc
            if df is None or df.empty: 
                logger.warning(f"{NEON_YELLOW}Failed to fetch klines. Retrying in {config['loop_delay']}s.{RESET}")
                time.sleep(config["loop_delay"])
                continue

            # Fetch orderbook data
            orderbook_data = None
            if config["indicators"].get("orderbook_imbalance"):
                orderbook_data = pybit_client.fetch_orderbook(config["symbol"], config["orderbook_limit"])
                if orderbook_data is None:
                    logger.warning(f"{NEON_YELLOW}Failed to fetch orderbook data.{RESET}")

            # Check spread filter
            guard = config.get("risk_guardrails", {})
            if guard.get("enabled", False) and orderbook_data:
                spread_bps = get_spread_bps(orderbook_data)
                max_spread = float(guard.get("max_spread_bps", 10.0))
                if spread_bps > max_spread:
                    logger.warning(f"{NEON_YELLOW}Spread too high ({spread_bps:.1f} bps > {max_spread:.1f}). Holding.{RESET}")
                    time.sleep(config["loop_delay"])
                    continue

            # Check expected value filter
            if guard.get("ev_filter_enabled", True) and expected_value(performance_tracker) <= 0:
                logger.warning(f"{NEON_YELLOW}Negative EV detected. Holding.{RESET}")
                time.sleep(config["loop_delay"])
                continue

            # Adapt exit parameters
            tp_mult, sl_mult = adapt_exit_params(performance_tracker, config)
            config["trade_management"]["take_profit_atr_multiple"] = float(tp_mult)
            config["trade_management"]["stop_loss_atr_multiple"] = float(sl_mult)

            # Multi-timeframe analysis
            mtf_trends: dict[str, str] = {}
            if config["mtf_analysis"]["enabled"]:
                for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
                    htf_df = pybit_client.fetch_klines(config["symbol"], htf_interval, 200) # Increased limit
                    if htf_df is not None and not htf_df.empty:
                        for trend_ind in config["mtf_analysis"]["trend_indicators"]:
                            # Assuming indicators._get_mtf_trend exists and returns "BULLISH", "BEARISH", or "NEUTRAL"
                            trend = indicators._get_mtf_trend(htf_df, config, logger, config["symbol"], trend_ind)
                            if trend: # Only add if a valid trend is determined
                                mtf_trends[f"{htf_interval}_{trend_ind}"] = trend
                    time.sleep(config["mtf_analysis"]["mtf_request_delay_seconds"])

            # Analyze market and generate signal
            analyzer = TradingAnalyzer(df, config, logger, config["symbol"])
            if analyzer.df.empty: 
                logger.warning(f"{NEON_YELLOW}Analyzer DataFrame is empty after processing. Retrying in {config['loop_delay']}s.{RESET}")
                time.sleep(config["loop_delay"])
                continue

            atr_value = Decimal(str(analyzer._get_indicator_value("ATR", Decimal("0.1"))))
            if atr_value <= 0: # Prevent division by zero if ATR is invalid
                 logger.warning(f"{NEON_YELLOW}Invalid ATR value ({atr_value}). Skipping signal generation and position management.{RESET}")
                 time.sleep(config["loop_delay"])
                 continue
            config["_last_atr"] = str(atr_value) # Store as string for JSON config

            trading_signal, signal_score = analyzer.generate_trading_signal(current_price, orderbook_data, mtf_trends)

            # Manage existing positions
            for pos in position_manager.get_open_positions():
                position_manager.trail_stop(pos, current_price, atr_value)
            
            position_manager.manage_positions(current_price, performance_tracker)
            position_manager.try_pyramid(current_price, atr_value)

            # Open new position if signal is strong
            if trading_signal in ("BUY", "SELL"):
                # Conviction scales the risk per trade, min 0.5 (half risk), max 1.0 (full risk)
                # tanh scales the ratio (abs(score) / threshold) to a smooth value between 0 and ~1
                # We then map this 0-1 range to 0.5-1.0 for risk scaling.
                conviction_raw = float(np.tanh(abs(signal_score) / max(config["signal_score_threshold"], 0.1))) # Ensure no division by zero
                conviction = max(0.5, min(1.0, conviction_raw)) # Scale risk from 0.5x to 1x based on conviction
                
                position_manager.open_position(trading_signal, current_price, atr_value, conviction)
            else:
                logger.info(f"{NEON_BLUE}No strong signal. Holding. Score: {signal_score:.2f}{RESET}")

            # Sync with exchange
            if exec_sync: exec_sync.poll()
            if heartbeat: heartbeat.tick()

            # Log performance
            logger.info(f"{NEON_YELLOW}Performance: {performance_tracker.get_summary()}{RESET}")
            logger.info(f"{NEON_PURPLE}--- Loop Finished. Waiting {config['loop_delay']}s ---{RESET}")
            time.sleep(config["loop_delay"])

    except Exception as e:
        alert_system.send_alert(f"Unhandled error in main loop: {e}", "ERROR")
        logger.exception(f"{NEON_RED}Unhandled exception in main loop:{RESET}")
        time.sleep(config["loop_delay"] * 2) # Longer delay after an unhandled error
    finally:
        # Ensure WebSocket connection is stopped gracefully
        if pybit_client and pybit_client.ws:
            pybit_client.ws.stop()
        logger.info(f"{NEON_GREEN}--- Wgwhalex Trading Bot Shut Down ---{RESET}")

if __name__ == "__main__":
    # Uncomment the line below to run random weight tuning before starting the bot
    # random_tune_weights(CONFIG_FILE) 
    main()

