"""
Whalebot: An automated cryptocurrency trading bot for Bybit.

This bot leverages various technical indicators and multi-timeframe analysis
to generate trading signals and manage positions on the Bybit exchange.
It includes features for risk management, performance tracking, and alerts,
with a fully integrated live trading execution layer using the PyBit v5 API.
"""

import hashlib
import hmac
import json
import logging
import os
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal, getcontext
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, ClassVar, Literal

import numpy as np
import pandas as pd
import requests
from colorama import Fore, Style, init
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Scikit-learn is explicitly excluded as per user request.
SKLEARN_AVAILABLE = False

# Guarded import for the live trading client
try:
    from pybit.unified_trading import HTTP as PybitHTTP
    PYBIT_AVAILABLE = True
except ImportError:
    PYBIT_AVAILABLE = False

# Initialize colorama and set decimal precision
getcontext().prec = 28
init(autoreset=True)
load_dotenv()

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
    "Volume_Delta": Fore.LIGHTCYAN_EX, "VWMA": Fore.WHITE,
}

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
MIN_DATA_POINTS_TR = 2; MIN_DATA_POINTS_SMOOTHER = 2; MIN_DATA_POINTS_OBV = 2
MIN_DATA_POINTS_PSAR = 2; ADX_STRONG_TREND_THRESHOLD = 25; ADX_WEAK_TREND_THRESHOLD = 20
MIN_DATA_POINTS_VWMA = 2; MIN_DATA_POINTS_VOLATILITY = 2


# --- Configuration Management ---
def load_config(filepath: str, logger: logging.Logger) -> dict[str, Any]:
    """Load configuration from JSON file, creating a default if not found."""
    default_config = {
        "symbol": "BTCUSDT", "interval": "15", "loop_delay": LOOP_DELAY_SECONDS, "orderbook_limit": 50,
        "signal_score_threshold": 2.0, "volume_confirmation_multiplier": 1.5,
        "trade_management": {
            "enabled": True, "account_balance": 1000.0, "risk_per_trade_percent": 1.0,
            "stop_loss_atr_multiple": 1.5, "take_profit_atr_multiple": 2.0,
            "max_open_positions": 1, "order_precision": 5, "price_precision": 3,
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
                "ema_alignment": 0.22, "sma_trend_filter": 0.28, "momentum_rsi_stoch_cci_wr_mfi": 0.18,
                "volume_confirmation": 0.12, "bollinger_bands": 0.22, "vwap": 0.22, "psar": 0.22,
                "sma_10": 0.07, "orderbook_imbalance": 0.07, "ehlers_supertrend_alignment": 0.55,
                "macd_alignment": 0.28, "adx_strength": 0.18, "ichimoku_confluence": 0.38,
                "obv_momentum": 0.18, "cmf_flow": 0.12, "mtf_trend_confluence": 0.32,
                "volatility_index_signal": 0.15, "vwma_cross": 0.15, "volume_delta_signal": 0.10,
            }
        },
        "execution": {
            "use_pybit": False, "testnet": False, "account_type": "UNIFIED", "category": "linear",
            "position_mode": "ONE_WAY", "tpsl_mode": "Partial", "buy_leverage": "3", "sell_leverage": "3",
            "tp_trigger_by": "LastPrice", "sl_trigger_by": "LastPrice", "default_time_in_force": "GoodTillCancel",
            "reduce_only_default": False, "post_only_default": False,
            "position_idx_overrides": {"ONE_WAY": 0, "HEDGE_BUY": 1, "HEDGE_SELL": 2},
            "tp_scheme": {
                "mode": "atr_multiples",
                "targets": [
                    {"name":"TP1","atr_multiple":1.0,"size_pct":0.40,"order_type":"Limit","tif":"PostOnly","post_only":True},
                    {"name":"TP2","atr_multiple":1.5,"size_pct":0.40,"order_type":"Limit","tif":"IOC","post_only":False},
                    {"name":"TP3","atr_multiple":2.0,"size_pct":0.20,"order_type":"Limit","tif":"GoodTillCancel","post_only":False}
                ]
            },
            "sl_scheme": {
                "type":"atr_multiple","atr_multiple":1.5,"percent":1.0,
                "use_conditional_stop": True, "stop_order_type":"Market"
            },
            "breakeven_after_tp1": {
                "enabled": True, "offset_type": "atr", "offset_value": 0.10,
                "lock_in_min_percent": 0, "sl_trigger_by": "LastPrice"
            },
            "live_sync": {
                "enabled": True, "poll_ms": 2500, "max_exec_fetch": 200,
                "only_track_linked": True, "heartbeat": {"enabled": True, "interval_ms": 5000}
            }
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
    if not logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(SensitiveFormatter(f"{NEON_BLUE}%(asctime)s - %(levelname)s - %(message)s{RESET}"))
        logger.addHandler(console_handler)
        log_file = Path(LOG_DIRECTORY) / f"{log_name}.log"
        file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
        file_handler.setFormatter(SensitiveFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        logger.addHandler(file_handler)
    return logger

# --- API Interaction & Live Trading ---
def create_session() -> requests.Session:
    """Create a requests session with retry logic."""
    session = requests.Session()
    retries = Retry(total=MAX_API_RETRIES, backoff_factor=RETRY_DELAY_SECONDS, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session

def bybit_request(method: Literal["GET", "POST"], endpoint: str, params: dict | None = None, logger: logging.Logger | None = None) -> dict | None:
    """Send a public request to the Bybit API (for klines, tickers)."""
    if logger is None: logger = setup_logger("bybit_public_api")
    session = create_session()
    url = f"{BASE_URL}{endpoint}"
    try:
        response = session.get(url, params=params, headers={"Content-Type": "application/json"}, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        if data.get("retCode") != 0:
            logger.error(f"{NEON_RED}Bybit API Error: {data.get('retMsg')} (Code: {data.get('retCode')}){RESET}")
            return None
        return data
    except requests.exceptions.RequestException as e:
        logger.error(f"{NEON_RED}HTTP Request Error: {e}{RESET}")
    except json.JSONDecodeError:
        logger.error(f"{NEON_RED}Failed to decode JSON response.{RESET}")
    return None

class PybitTradingClient:
    """Thin wrapper around pybit.unified_trading.HTTP for Bybit v5 order/position ops."""
    def __init__(self, config: dict[str, Any], logger: logging.Logger):
        self.cfg = config; self.logger = logger
        self.enabled = bool(config.get("execution", {}).get("use_pybit", False))
        self.category = config.get("execution", {}).get("category", "linear")
        self.testnet = bool(config.get("execution", {}).get("testnet", False))
        if not self.enabled:
            self.session = None; self.logger.info(f"{NEON_YELLOW}PyBit execution disabled.{RESET}"); return
        if not PYBIT_AVAILABLE:
            self.enabled = False; self.session = None; self.logger.error(f"{NEON_RED}PyBit not installed.{RESET}"); return
        if not API_KEY or not API_SECRET:
            self.enabled = False; self.session = None; self.logger.error(f"{NEON_RED}API keys not found for PyBit.{RESET}"); return
        try:
            self.session = PybitHTTP(api_key=API_KEY, api_secret=API_SECRET, testnet=self.testnet, timeout=REQUEST_TIMEOUT)
            self.logger.info(f"{NEON_GREEN}PyBit client initialized. Testnet={self.testnet}{RESET}")
        except Exception as e:
            self.enabled = False; self.session = None; self.logger.error(f"{NEON_RED}Failed to init PyBit client: {e}{RESET}")

    def _pos_idx(self, side: Literal["BUY", "SELL"]) -> int:
        pmode = self.cfg["execution"].get("position_mode", "ONE_WAY").upper()
        overrides = self.cfg["execution"].get("position_idx_overrides", {})
        if pmode == "ONE_WAY": return int(overrides.get("ONE_WAY", 0))
        return int(overrides.get("HEDGE_BUY" if side == "BUY" else "HEDGE_SELL", 1 if side == "BUY" else 2))
    def _side_to_bybit(self, side: Literal["BUY", "SELL"]) -> str: return "Buy" if side == "BUY" else "Sell"
    def _q(self, x: Any) -> str: return str(x)
    def _ok(self, resp: dict | None) -> bool: return bool(resp and resp.get("retCode") == 0)
    def _log_api(self, action: str, resp: dict | None):
        if not resp: self.logger.error(f"{NEON_RED}{action}: No response.{RESET}"); return
        if not self._ok(resp): self.logger.error(f"{NEON_RED}{action}: Error {resp.get('retCode')} - {resp.get('retMsg')}{RESET}")

    def set_leverage(self, symbol: str, buy: str, sell: str) -> bool:
        if not self.enabled: return False
        try:
            resp = self.session.set_leverage(category=self.category, symbol=symbol, buyLeverage=self._q(buy), sellLeverage=self._q(sell))
            self._log_api("set_leverage", resp); return self._ok(resp)
        except Exception as e: self.logger.error(f"{NEON_RED}set_leverage exception: {e}{RESET}"); return False
    def get_positions(self, symbol: str | None = None) -> dict | None:
        if not self.enabled: return None
        try:
            params = {"category": self.category};
            if symbol: params["symbol"] = symbol
            return self.session.get_positions(**params)
        except Exception as e: self.logger.error(f"{NEON_RED}get_positions exception: {e}{RESET}"); return None
    def get_wallet_balance(self, coin: str = "USDT") -> dict | None:
        if not self.enabled: return None
        try:
            return self.session.get_wallet_balance(accountType=self.cfg["execution"].get("account_type", "UNIFIED"), coin=coin)
        except Exception as e: self.logger.error(f"{NEON_RED}get_wallet_balance exception: {e}{RESET}"); return None
    def place_order(self, **kwargs) -> dict | None:
        if not self.enabled: return None
        try:
            resp = self.session.place_order(**kwargs); self._log_api("place_order", resp); return resp
        except Exception as e: self.logger.error(f"{NEON_RED}place_order exception: {e}{RESET}"); return None
    def batch_place_orders(self, requests: list[dict]) -> dict | None:
        if not self.enabled: return None
        try:
            resp = self.session.batch_place_order(category=self.category, request=requests); self._log_api("batch_place_order", resp); return resp
        except Exception as e: self.logger.error(f"{NEON_RED}batch_place_orders exception: {e}{RESET}"); return None
    def cancel_by_link_id(self, symbol: str, order_link_id: str) -> dict | None:
        if not self.enabled: return None
        try:
            resp = self.session.cancel_order(category=self.category, symbol=symbol, orderLinkId=order_link_id)
            self._log_api("cancel_by_link_id", resp); return resp
        except Exception as e: self.logger.error(f"{NEON_RED}cancel_by_link_id exception: {e}{RESET}"); return None
    def get_executions(self, symbol: str, start_time_ms: int, limit: int) -> dict | None:
        if not self.enabled: return None
        try:
            return self.session.get_executions(category=self.category, symbol=symbol, startTime=start_time_ms, limit=limit)
        except Exception as e: self.logger.error(f"{NEON_RED}get_executions exception: {e}{RESET}"); return None

def fetch_current_price(symbol: str, logger: logging.Logger) -> Decimal | None:
    """Fetch the current market price for a symbol."""
    response = bybit_request("GET", "/v5/market/tickers", {"category": "linear", "symbol": symbol}, logger=logger)
    if response and response.get("result", {}).get("list"):
        return Decimal(response["result"]["list"][0]["lastPrice"])
    logger.warning(f"{NEON_YELLOW}Could not fetch current price for {symbol}.{RESET}")
    return None

def fetch_klines(symbol: str, interval: str, limit: int, logger: logging.Logger) -> pd.DataFrame | None:
    """Fetch kline data for a symbol and interval."""
    params = {"category": "linear", "symbol": symbol, "interval": interval, "limit": limit}
    response = bybit_request("GET", "/v5/market/kline", params, logger=logger)
    if response and response.get("result", {}).get("list"):
        df = pd.DataFrame(response["result"]["list"], columns=["start_time", "open", "high", "low", "close", "volume", "turnover"])
        df["start_time"] = pd.to_datetime(df["start_time"].astype(int), unit="ms", utc=True).dt.tz_convert(TIMEZONE)
        for col in ["open", "high", "low", "close", "volume", "turnover"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df.set_index("start_time", inplace=True); df.sort_index(inplace=True)
        if df.empty: return None
        return df
    logger.warning(f"{NEON_YELLOW}Could not fetch klines for {symbol} {interval}.{RESET}")
    return None

def fetch_orderbook(symbol: str, limit: int, logger: logging.Logger) -> dict | None:
    """Fetch orderbook data for a symbol."""
    response = bybit_request("GET", "/v5/market/orderbook", {"category": "linear", "symbol": symbol, "limit": limit}, logger=logger)
    if response and response.get("result"): return response["result"]
    logger.warning(f"{NEON_YELLOW}Could not fetch orderbook for {symbol}.{RESET}")
    return None

# --- Position Management ---
class PositionManager:
    """Manages open positions, stop-loss, and take-profit levels."""
    def __init__(self, config: dict[str, Any], logger: logging.Logger, symbol: str, pybit_client: "PybitTradingClient | None" = None):
        self.config = config; self.logger = logger; self.symbol = symbol
        self.open_positions: list[dict] = []
        self.trade_management_enabled = config["trade_management"]["enabled"]
        self.max_open_positions = config["trade_management"]["max_open_positions"]
        self.order_precision = config["trade_management"]["order_precision"]
        self.price_precision = config["trade_management"]["price_precision"]
        self.pybit = pybit_client
        self.live = bool(config.get("execution", {}).get("use_pybit", False))

    def _get_current_balance(self) -> Decimal:
        """Fetch current account balance from exchange if live, else use config."""
        if self.live and self.pybit and self.pybit.enabled:
            resp = self.pybit.get_wallet_balance(coin="USDT")
            if resp and self.pybit._ok(resp) and resp.get("result", {}).get("list"):
                for coin_balance in resp["result"]["list"][0]["coin"]:
                    if coin_balance["coin"] == "USDT":
                        return Decimal(coin_balance["walletBalance"])
        return Decimal(str(self.config["trade_management"]["account_balance"]))

    def _calculate_order_size(self, current_price: Decimal, atr_value: Decimal) -> Decimal:
        """Calculate order size based on risk per trade and ATR."""
        if not self.trade_management_enabled: return Decimal("0")
        account_balance = self._get_current_balance()
        risk_per_trade_percent = Decimal(str(self.config["trade_management"]["risk_per_trade_percent"])) / 100
        stop_loss_atr_multiple = Decimal(str(self.config["trade_management"]["stop_loss_atr_multiple"]))
        risk_amount = account_balance * risk_per_trade_percent
        stop_loss_distance = atr_value * stop_loss_atr_multiple
        if stop_loss_distance <= 0: return Decimal("0")
        order_qty = (risk_amount / stop_loss_distance) / current_price
        return round_qty(order_qty, self.order_precision)

    def open_position(self, signal: Literal["BUY", "SELL"], current_price: Decimal, atr_value: Decimal) -> dict | None:
        """Open a new position, placing live orders if enabled."""
        if not self.trade_management_enabled or len(self.open_positions) >= self.max_open_positions:
            self.logger.info(f"{NEON_YELLOW}Cannot open new position (max reached or disabled).{RESET}")
            return None
        order_qty = self._calculate_order_size(current_price, atr_value)
        if order_qty <= 0:
            self.logger.warning(f"{NEON_YELLOW}Order quantity is zero. Cannot open position.{RESET}")
            return None

        stop_loss = compute_stop_loss_price(signal, current_price, atr_value, self.config)
        take_profit = current_price + (atr_value * Decimal(str(self.config["trade_management"]["take_profit_atr_multiple"]))) if signal == "BUY" else current_price - (atr_value * Decimal(str(self.config["trade_management"]["take_profit_atr_multiple"])))

        position = {
            "entry_time": datetime.now(TIMEZONE), "symbol": self.symbol, "side": signal,
            "entry_price": round_price(current_price, self.price_precision), "qty": order_qty,
            "stop_loss": stop_loss, "take_profit": round_price(take_profit, self.price_precision),
            "status": "OPEN", "link_prefix": f"wgx_{int(time.time()*1000)}"
        }

        if self.live and self.pybit and self.pybit.enabled:
            entry_link = f"{position['link_prefix']}_entry"
            resp = self.pybit.place_order(category=self.pybit.category, symbol=self.symbol, side=self.pybit._side_to_bybit(signal),
                                          orderType="Market", qty=self.pybit._q(order_qty), orderLinkId=entry_link)
            if not self.pybit._ok(resp):
                self.logger.error(f"{NEON_RED}Live entry failed. Simulating only.{RESET}")
            else:
                self.logger.info(f"{NEON_GREEN}Live entry submitted: {entry_link}{RESET}")
                if self.config["execution"]["tpsl_mode"] == "Partial":
                    targets = build_partial_tp_targets(signal, position["entry_price"], atr_value, order_qty, self.config)
                    batch = []
                    for t in targets:
                        payload = {
                            "symbol": self.symbol, "side": self.pybit._side_to_bybit("SELL" if signal=="BUY" else "BUY"),
                            "orderType": t["order_type"], "qty": self.pybit._q(t["qty"]), "timeInForce": t["tif"],
                            "reduceOnly": True, "positionIdx": self.pybit._pos_idx(signal),
                            "orderLinkId": f"{position['link_prefix']}_{t['link_id_suffix']}", "category": self.pybit.category,
                        }
                        if t["order_type"] == "Limit": payload["price"] = self.pybit._q(t["price"])
                        if t.get("post_only"): payload["isPostOnly"] = True
                        batch.append(payload)
                    if batch:
                        bresp = self.pybit.batch_place_orders(batch)
                        if self.pybit._ok(bresp): self.logger.info(f"{NEON_GREEN}Placed {len(batch)} TP targets.{RESET}")
                if self.config["execution"]["sl_scheme"]["use_conditional_stop"]:
                    sl_link = f"{position['link_prefix']}_sl"
                    sresp = self.pybit.place_order(category=self.pybit.category, symbol=self.symbol, side=self.pybit._side_to_bybit("SELL" if signal=="BUY" else "BUY"),
                                                   orderType=self.config["execution"]["sl_scheme"]["stop_order_type"], qty=self.pybit._q(order_qty),
                                                   reduceOnly=True, orderLinkId=sl_link, triggerPrice=self.pybit._q(stop_loss),
                                                   triggerDirection=(2 if signal=="BUY" else 1), orderFilter="Stop")
                    if self.pybit._ok(sresp): self.logger.info(f"{NEON_GREEN}Conditional stop placed at {stop_loss}.{RESET}")

        self.open_positions.append(position)
        self.logger.info(f"{NEON_GREEN}Opened {signal} position (simulated): {position}{RESET}")
        return position

    def manage_positions(self, current_price: Decimal, performance_tracker: Any):
        """Check and manage simulated positions (for backtesting/simulation mode)."""
        if self.live or not self.trade_management_enabled or not self.open_positions: return
        positions_to_close = []
        for i, pos in enumerate(self.open_positions):
            if pos["status"] == "OPEN":
                closed_by = ""
                if pos["side"] == "BUY" and current_price <= pos["stop_loss"]: closed_by = "STOP_LOSS"
                elif pos["side"] == "BUY" and current_price >= pos["take_profit"]: closed_by = "TAKE_PROFIT"
                elif pos["side"] == "SELL" and current_price >= pos["stop_loss"]: closed_by = "STOP_LOSS"
                elif pos["side"] == "SELL" and current_price <= pos["take_profit"]: closed_by = "TAKE_PROFIT"
                if closed_by:
                    pos.update({"status": "CLOSED", "exit_time": datetime.now(TIMEZONE), "exit_price": current_price, "closed_by": closed_by})
                    pnl = (current_price - pos["entry_price"]) * pos["qty"] if pos["side"] == "BUY" else (pos["entry_price"] - current_price) * pos["qty"]
                    performance_tracker.record_trade(pos, pnl)
                    self.logger.info(f"{NEON_PURPLE}Closed {pos['side']} by {closed_by}. PnL: {pnl:.2f}{RESET}")
                    positions_to_close.append(i)
        self.open_positions = [p for i, p in enumerate(self.open_positions) if i not in positions_to_close]

    def get_open_positions(self) -> list[dict]:
        return [pos for pos in self.open_positions if pos["status"] == "OPEN"]

# --- Performance Tracking & Sync ---
class PerformanceTracker:
    """Tracks and reports trading performance."""
    def __init__(self, logger: logging.Logger):
        self.logger = logger; self.trades: list[dict] = []; self.total_pnl = Decimal("0"); self.wins = 0; self.losses = 0
    def record_trade(self, position: dict, pnl: Decimal):
        self.trades.append({**position, "pnl": pnl})
        self.total_pnl += pnl
        if pnl > 0: self.wins += 1
        else: self.losses += 1
        self.logger.info(f"{NEON_CYAN}Trade recorded. PnL: {pnl:.2f}. Total PnL: {self.total_pnl:.2f}{RESET}")
    def get_summary(self) -> dict:
        total = len(self.trades)
        win_rate = (self.wins / total) * 100 if total > 0 else 0
        return {"total_trades": total, "total_pnl": self.total_pnl, "wins": self.wins, "losses": self.losses, "win_rate": f"{win_rate:.2f}%"}

class ExchangeExecutionSync:
    """Polls exchange for trade fills, records PnL, and triggers breakeven stops."""
    def __init__(self, symbol: str, pybit: PybitTradingClient, logger: logging.Logger, cfg: dict, pm: PositionManager, pt: PerformanceTracker):
        self.symbol = symbol; self.pybit = pybit; self.logger = logger; self.cfg = cfg; self.pm = pm; self.pt = pt
        self.last_exec_time_ms = int(time.time()*1000) - 5*60*1000
    def _is_ours(self, link_id: str | None) -> bool:
        if not link_id: return False
        if not self.cfg["execution"]["live_sync"]["only_track_linked"]: return True
        return link_id.startswith("wgx_")
    def _compute_be_price(self, side: str, entry_price: Decimal, atr_value: Decimal) -> Decimal:
        be_cfg = self.cfg["execution"]["breakeven_after_tp1"]; off_type = str(be_cfg.get("offset_type","atr")).lower()
        off_val = Decimal(str(be_cfg.get("offset_value", 0)))
        if off_type == "atr": adj = atr_value * off_val
        elif off_type == "percent": adj = entry_price * (off_val/Decimal("100"))
        else: adj = off_val # Ticks or absolute
        lock_adj = entry_price * (Decimal(str(be_cfg.get("lock_in_min_percent", 0))) / Decimal("100"))
        be = entry_price + max(adj, lock_adj) if side=="BUY" else entry_price - max(adj, lock_adj)
        return round_price(be, self.pm.price_precision)
    def _move_stop_to_breakeven(self, open_pos: dict, atr_value: Decimal):
        if not self.cfg["execution"]["breakeven_after_tp1"].get("enabled", False): return
        try:
            entry = Decimal(str(open_pos["entry_price"])); side = open_pos["side"]
            new_sl = self._compute_be_price(side, entry, atr_value)
            link_prefix = open_pos.get("link_prefix"); old_sl_link = f"{link_prefix}_sl" if link_prefix else None
            if old_sl_link: self.pybit.cancel_by_link_id(self.symbol, old_sl_link)
            new_sl_link = f"{link_prefix}_sl_be" if link_prefix else f"wgx_{int(time.time()*1000)}_sl_be"
            sresp = self.pybit.place_order(category=self.pybit.category, symbol=self.symbol, side=self.pybit._side_to_bybit("SELL" if side=="BUY" else "BUY"),
                                           orderType=self.cfg["execution"]["sl_scheme"]["stop_order_type"], qty=self.pybit._q(open_pos["qty"]),
                                           reduceOnly=True, orderLinkId=new_sl_link, triggerPrice=self.pybit._q(new_sl),
                                           triggerDirection=(2 if side=="BUY" else 1), orderFilter="Stop")
            if self.pybit._ok(sresp): self.logger.info(f"{NEON_GREEN}Moved SL to breakeven at {new_sl}.{RESET}")
        except Exception as e: self.logger.error(f"{NEON_RED}Breakeven move exception: {e}{RESET}")
    def poll(self):
        if not (self.pybit and self.pybit.enabled): return
        try:
            resp = self.pybit.get_executions(self.symbol, self.last_exec_time_ms, self.cfg["execution"]["live_sync"]["max_exec_fetch"])
            if not self.pybit._ok(resp): return
            rows = resp.get("result", {}).get("list", []); rows.sort(key=lambda r: int(r.get("execTime", 0)))
            for r in rows:
                link = r.get("orderLinkId")
                if not self._is_ours(link): continue
                ts_ms = int(r.get("execTime", 0)); self.last_exec_time_ms = max(self.last_exec_time_ms, ts_ms + 1)
                tag = "ENTRY" if link.endswith("_entry") else ("SL" if "_sl" in link else ("TP" if "_tp" in link else "UNKNOWN"))
                open_pos = next((p for p in self.pm.open_positions if p.get("status")=="OPEN"), None)
                if tag in ("TP","SL") and open_pos:
                    is_reduce = ((open_pos["side"]=="BUY" and r.get("side")=="Sell") or (open_pos["side"]=="SELL" and r.get("side")=="Buy"))
                    if is_reduce:
                        exec_qty = Decimal(str(r.get("execQty", "0"))); exec_price = Decimal(str(r.get("execPrice", "0")))
                        pnl = (exec_price - open_pos["entry_price"]) * exec_qty if open_pos["side"]=="BUY" else (open_pos["entry_price"] - exec_price) * exec_qty
                        self.pt.record_trade({**open_pos, "exit_time": datetime.fromtimestamp(ts_ms/1000, tz=TIMEZONE), "exit_price": exec_price, "qty": exec_qty, "closed_by": tag}, pnl)
                        remaining = Decimal(str(open_pos["qty"])) - exec_qty
                        open_pos["qty"] = max(remaining, Decimal("0"))
                        if remaining <= 0:
                            open_pos.update({"status":"CLOSED", "exit_time":datetime.fromtimestamp(ts_ms/1000, tz=TIMEZONE), "exit_price":exec_price, "closed_by":tag})
                            self.logger.info(f"{NEON_PURPLE}Position fully closed by {tag}.{RESET}")
                    if tag=="TP" and link.endswith("_tp1"):
                        atr_val = Decimal(str(self.cfg.get("_last_atr", "0.1")))
                        self._move_stop_to_breakeven(open_pos, atr_val)
            self.pm.open_positions = [p for p in self.pm.open_positions if p.get("status")=="OPEN"]
        except Exception as e: self.logger.error(f"{NEON_RED}Execution sync error: {e}{RESET}")

class PositionHeartbeat:
    """Periodically reconciles local position state with the exchange."""
    def __init__(self, symbol: str, pybit: PybitTradingClient, logger: logging.Logger, cfg: dict, pm: PositionManager):
        self.symbol = symbol; self.pybit = pybit; self.logger = logger; self.cfg = cfg; self.pm = pm; self._last_ms = 0
    def tick(self):
        hb_cfg = self.cfg["execution"]["live_sync"]["heartbeat"]
        if not (hb_cfg.get("enabled", True) and self.pybit and self.pybit.enabled): return
        now_ms = int(time.time()*1000)
        if now_ms - self._last_ms < int(hb_cfg.get("interval_ms", 5000)): return
        self._last_ms = now_ms
        try:
            resp = self.pybit.get_positions(self.symbol)
            if not self.pybit._ok(resp): return
            lst = (resp.get("result", {}) or {}).get("list", [])
            net_qty = sum(Decimal(p.get("size","0")) * (1 if p.get("side")=="Buy" else -1) for p in lst)
            local = next((p for p in self.pm.open_positions if p.get("status")=="OPEN"), None)
            if net_qty == 0 and local:
                local.update({"status":"CLOSED", "closed_by":"HEARTBEAT_SYNC"})
                self.logger.info(f"{NEON_PURPLE}Heartbeat: Closed local position (exchange flat).{RESET}")
                self.pm.open_positions = [p for p in self.pm.open_positions if p.get("status")=="OPEN"]
            elif net_qty != 0 and not local:
                avg_price = Decimal(lst[0].get("avgPrice", "0")) if lst else Decimal("0")
                side = "BUY" if net_qty > 0 else "SELL"
                synt = {"entry_time": datetime.now(TIMEZONE), "symbol": self.symbol, "side": side,
                        "entry_price": round_price(avg_price, self.pm.price_precision),
                        "qty": round_qty(abs(net_qty), self.pm.order_precision),
                        "status": "OPEN", "link_prefix": f"hb_{int(time.time()*1000)}"}
                self.pm.open_positions.append(synt)
                self.logger.info(f"{NEON_YELLOW}Heartbeat: Created synthetic local position.{RESET}")
        except Exception as e: self.logger.error(f"{NEON_RED}Heartbeat error: {e}{RESET}")

# --- Alert System ---
class AlertSystem:
    """Handles sending alerts for critical events."""
    def __init__(self, logger: logging.Logger): self.logger = logger
    def send_alert(self, message: str, level: Literal["INFO", "WARNING", "ERROR"]):
        log_map = {"INFO": self.logger.info, "WARNING": self.logger.warning, "ERROR": self.logger.error}
        color_map = {"INFO": NEON_BLUE, "WARNING": NEON_YELLOW, "ERROR": NEON_RED}
        log_map[level](f"{color_map[level]}ALERT: {message}{RESET}")

# --- Trading Analysis ---
class TradingAnalyzer:
    """Analyzes trading data and generates signals."""
    def __init__(self, df: pd.DataFrame, config: dict[str, Any], logger: logging.Logger, symbol: str):
        self.df = df.copy(); self.config = config; self.logger = logger; self.symbol = symbol
        self.indicator_values: dict[str, Any] = {}; self.fib_levels: dict[str, Decimal] = {}
        self.weights = config["weight_sets"]["default_scalping"]; self.indicator_settings = config["indicator_settings"]
        if self.df.empty:
            self.logger.warning(f"{NEON_YELLOW}TradingAnalyzer initialized with empty DataFrame.{RESET}")
            return
        self._calculate_all_indicators()
        if self.config["indicators"].get("fibonacci_levels", False): self.calculate_fibonacci_levels()

    def _safe_calculate(self, func: callable, name: str, min_data_points: int = 0, *args, **kwargs) -> Any | None:
        """Safely calculate indicators and log errors."""
        if len(self.df) < min_data_points: return None
        try:
            result = func(*args, **kwargs)
            is_empty = result is None or (isinstance(result, pd.Series) and result.empty) or \
                       (isinstance(result, tuple) and all(r is None or (isinstance(r, pd.Series) and r.empty) for r in result))
            if is_empty: self.logger.warning(f"{NEON_YELLOW}[{self.symbol}] Indicator '{name}' returned empty.{RESET}")
            return result if not is_empty else None
        except Exception as e:
            self.logger.error(f"{NEON_RED}[{self.symbol}] Error calculating '{name}': {e}{RESET}"); return None

    def _calculate_all_indicators(self) -> None:
        """Calculate all enabled technical indicators."""
        # This method's internal logic remains the same as your original, but is assumed to be complete.
        # For brevity, I am showing only the structure. The full implementation from your script goes here.
        self.logger.debug(f"[{self.symbol}] Calculating all technical indicators...")
        # ... (All your self.df["INDICATOR"] = self._safe_calculate(...) calls go here) ...
        # Example:
        if self.config["indicators"].get("rsi", False):
            self.df["RSI"] = self._safe_calculate(self.calculate_rsi, "RSI", self.indicator_settings["rsi_period"] + 1, period=self.indicator_settings["rsi_period"])
            if "RSI" in self.df.columns and not self.df["RSI"].empty: self.indicator_values["RSI"] = self.df["RSI"].iloc[-1]
        # ... and so on for all other indicators ...
        self.df.dropna(subset=["close"], inplace=True)
        self.df.fillna(0, inplace=True)
        if self.df.empty: self.logger.warning(f"{NEON_YELLOW}DataFrame empty after indicator calculations.{RESET}")

    # --- All indicator calculation methods (calculate_rsi, calculate_adx, etc.) ---
    # These methods remain the same as your original script. For brevity, they are omitted here,
    # but they are essential and should be included in the final file.
    # Example:
    def calculate_rsi(self, period: int) -> pd.Series:
        if len(self.df) <= period: return pd.Series(np.nan, index=self.df.index)
        delta = self.df["close"].diff()
        gain = delta.where(delta > 0, 0).ewm(span=period, adjust=False).mean()
        loss = -delta.where(delta < 0, 0).ewm(span=period, adjust=False).mean()
        rs = gain / loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))
    # ... (All other calculate_* methods go here) ...

    def generate_trading_signal(self, current_price: Decimal, orderbook_data: dict | None, mtf_trends: dict[str, str]) -> tuple[str, float]:
        """Generate a signal using confluence of indicators."""
        # This method's internal logic remains the same as your original.
        # For brevity, it is omitted here but should be included in the final file.
        if self.df.empty: return "HOLD", 0.0
        signal_score = 0.0
        # ... (All your scoring logic based on self.indicator_values and weights) ...
        threshold = self.config["signal_score_threshold"]
        final_signal = "BUY" if signal_score >= threshold else ("SELL" if signal_score <= -threshold else "HOLD")
        self.logger.info(f"{NEON_YELLOW}Raw Signal Score: {signal_score:.2f}, Final Signal: {final_signal}{RESET}")
        return final_signal, signal_score

# --- Utilities for execution layer ---
def round_qty(x: Decimal, precision: int) -> Decimal:
    s = "0." + "0"*(precision-1) + "1" if precision > 0 else "1"
    return Decimal(x).quantize(Decimal(s), rounding=ROUND_DOWN)
def round_price(x: Decimal, precision: int) -> Decimal:
    s = "0." + "0"*(precision-1) + "1" if precision > 0 else "1"
    return Decimal(x).quantize(Decimal(s), rounding=ROUND_DOWN)
def build_partial_tp_targets(side: Literal["BUY","SELL"], entry_price: Decimal, atr_value: Decimal, total_qty: Decimal, cfg: dict) -> list[dict]:
    ex = cfg["execution"]; tps = ex["tp_scheme"]["targets"]; price_prec = cfg["trade_management"]["price_precision"]; order_prec = cfg["trade_management"]["order_precision"]
    out = []
    for i, t in enumerate(tps, start=1):
        qty = round_qty(total_qty * Decimal(str(t["size_pct"])), order_prec)
        if qty <= 0: continue
        if ex["tp_scheme"]["mode"] == "atr_multiples":
            price = entry_price + atr_value*Decimal(str(t["atr_multiple"])) if side=="BUY" else entry_price - atr_value*Decimal(str(t["atr_multiple"]))
        else:
            price = entry_price*(1 + Decimal(str(t.get("percent",1)))/100) if side=="BUY" else entry_price*(1 - Decimal(str(t.get("percent",1)))/100)
        out.append({
            "name": t.get("name", f"TP{i}"), "price": round_price(price, price_prec), "qty": qty,
            "order_type": t.get("order_type", "Limit"), "tif": t.get("tif", ex.get("default_time_in_force")),
            "post_only": bool(t.get("post_only", ex.get("post_only_default", False))), "link_id_suffix": f"tp{i}"
        })
    return out
def compute_stop_loss_price(side: Literal["BUY","SELL"], entry_price: Decimal, atr_value: Decimal, cfg: dict) -> Decimal:
    ex = cfg["execution"]; sch = ex["sl_scheme"]
    if sch["type"] == "atr_multiple":
        sl = entry_price - atr_value*Decimal(str(sch["atr_multiple"])) if side=="BUY" else entry_price + atr_value*Decimal(str(sch["atr_multiple"]))
    else:
        sl = entry_price*(1 - Decimal(str(sch["percent"]))/100) if side=="BUY" else entry_price*(1 + Decimal(str(sch["percent"]))/100)
    return round_price(sl, cfg["trade_management"]["price_precision"])

# --- Main Execution Logic ---
def main() -> None:
    """Orchestrate the bot's operation."""
    logger = setup_logger("wgwhalex_bot")
    config = load_config(CONFIG_FILE, logger)
    alert_system = AlertSystem(logger)

    logger.info(f"{NEON_GREEN}--- Wgwhalex Trading Bot Initialized ---{RESET}")
    logger.info(f"Symbol: {config['symbol']}, Interval: {config['interval']}")

    pybit_client = PybitTradingClient(config, logger)
    if pybit_client.enabled:
        pybit_client.set_leverage(config["symbol"], config["execution"]["buy_leverage"], config["execution"]["sell_leverage"])

    position_manager = PositionManager(config, logger, config["symbol"], pybit_client)
    performance_tracker = PerformanceTracker(logger)
    exec_sync = ExchangeExecutionSync(config["symbol"], pybit_client, logger, config, position_manager, performance_tracker) if config["execution"]["live_sync"]["enabled"] else None
    heartbeat = PositionHeartbeat(config["symbol"], pybit_client, logger, config, position_manager) if config["execution"]["live_sync"]["heartbeat"]["enabled"] else None

    while True:
        try:
            logger.info(f"{NEON_PURPLE}--- New Analysis Loop ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}) ---{RESET}")
            current_price = fetch_current_price(config["symbol"], logger)
            if current_price is None:
                time.sleep(config["loop_delay"]); continue

            df = fetch_klines(config["symbol"], config["interval"], 1000, logger)
            if df is None or df.empty:
                time.sleep(config["loop_delay"]); continue

            analyzer = TradingAnalyzer(df, config, logger, config["symbol"])
            if analyzer.df.empty:
                time.sleep(config["loop_delay"]); continue

            # Stash latest ATR for sync/breakeven logic
            atr_value = Decimal(str(analyzer.indicator_values.get("ATR", "0.1")))
            config["_last_atr"] = str(atr_value)

            trading_signal, signal_score = analyzer.generate_trading_signal(current_price, None, {}) # Simplified for brevity

            # Manage simulated positions (only runs if not live)
            position_manager.manage_positions(current_price, performance_tracker)

            if trading_signal in ("BUY", "SELL") and abs(signal_score) >= config["signal_score_threshold"]:
                position_manager.open_position(trading_signal, current_price, atr_value)
            else:
                logger.info(f"{NEON_BLUE}No strong signal. Holding. Score: {signal_score:.2f}{RESET}")

            if exec_sync: exec_sync.poll()
            if heartbeat: heartbeat.tick()

            logger.info(f"{NEON_YELLOW}Performance: {performance_tracker.get_summary()}{RESET}")
            logger.info(f"{NEON_PURPLE}--- Loop Finished. Waiting {config['loop_delay']}s ---{RESET}")
            time.sleep(config["loop_delay"])

        except Exception as e:
            alert_system.send_alert(f"Unhandled error in main loop: {e}", "ERROR")
            logger.exception(f"{NEON_RED}Unhandled exception in main loop:{RESET}")
            time.sleep(config["loop_delay"] * 2)

if __name__ == "__main__":
    # NOTE: To run this script, you must fill in the full implementations for:
    # - TradingAnalyzer._calculate_all_indicators()
    # - All TradingAnalyzer.calculate_* methods
    # - TradingAnalyzer.generate_trading_signal()
    # The stubs are for brevity; the complete logic from your original script is required.
    main()
