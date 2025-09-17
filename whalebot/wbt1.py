# -*- coding: utf-8 -*-
"""
Whalebot: An advanced cryptocurrency trading bot for Bybit.

This bot leverages various technical indicators, multi-timeframe analysis,
order book data, and AI analysis to generate trading signals and manage
positions on the Bybit exchange with robust risk management.
"""

import asyncio
import contextlib
import hashlib
import hmac
import json
import logging
import os
import random
import sys
import threading
import time
import traceback
import urllib.parse
import warnings
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import ROUND_DOWN, Decimal, InvalidOperation, getcontext
from enum import Enum
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional, Tuple, Union, Literal

import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Third-party imports with error handling
try:
    from colorama import Fore, Style, init
    init(autoreset=True)
    COLORAMA_AVAILABLE = True
except ImportError:
    COLORAMA_AVAILABLE = False
    print("Warning: colorama not installed. Install with: pip install colorama")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Warning: python-dotenv not installed. Install with: pip install python-dotenv")

try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
except ImportError:
    PANDAS_TA_AVAILABLE = False
    print("Warning: pandas_ta not installed. Install with: pip install pandas_ta")

try:
    import websocket
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
    print("Warning: websocket-client not installed. Install with: pip install websocket-client")

# Pybit imports with fallback
try:
    import pybit.exceptions
    from pybit.unified_trading import HTTP as PybitHTTP, WebSocket
    PYBIT_AVAILABLE = True
except ImportError:
    PYBIT_AVAILABLE = False
    print("Warning: pybit not installed. Install with: pip install pybit")
    
    # Define dummy classes for development/testing without pybit
    class PybitHTTP:
        def __init__(self, **kwargs): 
            self.session = None
            self.base_url = "https://api.bybit.com"
            
        def get_tickers(self, **kwargs): return {"retCode": -1, "result": None}
        def get_kline(self, **kwargs): return {"retCode": -1, "result": None}
        def get_orderbook(self, **kwargs): return {"retCode": -1, "result": None}
        def place_order(self, **kwargs): return {"retCode": -1, "result": None}
        def cancel_order(self, **kwargs): return {"retCode": -1, "result": None}
        def get_positions(self, **kwargs): return {"retCode": -1, "result": None}
        def get_wallet_balance(self, **kwargs): return {"retCode": -1, "result": None}
        def set_leverage(self, **kwargs): return {"retCode": -1, "result": None}
        def set_trading_stop(self, **kwargs): return {"retCode": -1, "result": None}
        def get_instruments_info(self, **kwargs): return {"retCode": -1, "result": None}
        def get_executions(self, **kwargs): return {"retCode": -1, "result": None}
        def get_open_orders(self, **kwargs): return {"retCode": -1, "result": None}
        def batch_place_order(self, **kwargs): return {"retCode": -1, "result": None}
        def cancel_all_orders(self, **kwargs): return {"retCode": -1, "result": None}

    class WebSocket:
        def __init__(self, **kwargs): pass
        def kline_stream(self, **kwargs): pass
        def ticker_stream(self, **kwargs): pass
        def orderbook_stream(self, **kwargs): pass
        def position_stream(self, **kwargs): pass
        def order_stream(self, **kwargs): pass
        def execution_stream(self, **kwargs): pass
        def wallet_stream(self, **kwargs): pass

# Color constants
if COLORAMA_AVAILABLE:
    NEON_GREEN = Fore.GREEN + Style.BRIGHT
    NEON_RED = Fore.RED + Style.BRIGHT
    NEON_YELLOW = Fore.YELLOW + Style.BRIGHT
    NEON_BLUE = Fore.BLUE + Style.BRIGHT
    NEON_MAGENTA = Fore.MAGENTA + Style.BRIGHT
    NEON_CYAN = Fore.CYAN + Style.BRIGHT
    NEON_PURPLE = Fore.MAGENTA + Style.BRIGHT
    RESET = Style.RESET_ALL
else:
    NEON_GREEN = NEON_RED = NEON_YELLOW = NEON_BLUE = ""
    NEON_MAGENTA = NEON_CYAN = NEON_PURPLE = RESET = ""

# Set decimal precision
getcontext().prec = 28

# Constants
API_KEY = os.getenv("BYBIT_API_KEY", "")
API_SECRET = os.getenv("BYBIT_API_SECRET", "")
CONFIG_FILE = "config.json"
STATE_FILE = "bot_state.json"
LOG_DIRECTORY = "bot_logs"
Path(LOG_DIRECTORY).mkdir(parents=True, exist_ok=True)

# Trading constants
TIMEZONE = timezone.utc
MAX_API_RETRIES = 5
RETRY_DELAY_SECONDS = 7
REQUEST_TIMEOUT = 20
LOOP_DELAY_SECONDS = 15
BASE_URL = "https://api.bybit.com"
WS_RECONNECT_DELAY_SECONDS = 5

# Indicator constants
MIN_DATA_POINTS = 50
ADX_STRONG_TREND_THRESHOLD = 25
ADX_WEAK_TREND_THRESHOLD = 20
MIN_CANDLESTICK_PATTERNS_BARS = 5

class SignalType(Enum):
    """Trading signal types"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

class OrderStatus(Enum):
    """Order status types"""
    NEW = "New"
    PARTIALLY_FILLED = "PartiallyFilled"
    FILLED = "Filled"
    CANCELLED = "Cancelled"
    REJECTED = "Rejected"

# Helper Functions
def round_qty(qty: Decimal, qty_step: Decimal) -> Decimal:
    """Rounds quantity to the nearest valid step."""
    if qty_step is None or qty_step <= 0:
        return qty.quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
    return (qty // qty_step) * qty_step

def round_price(price: Decimal, price_precision: int) -> Decimal:
    """Rounds price to the specified precision."""
    if price_precision < 0:
        price_precision = 0
    return price.quantize(Decimal(f"1e-{price_precision}"), rounding=ROUND_DOWN)

def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safely divides two numbers."""
    try:
        if denominator == 0 or np.isnan(denominator) or np.isnan(numerator):
            return default
        return numerator / denominator
    except (ZeroDivisionError, ValueError):
        return default

def safe_decimal_divide(numerator: Decimal, denominator: Decimal, default: Decimal = Decimal("0")) -> Decimal:
    """Safely divides two Decimals."""
    try:
        if denominator == 0 or denominator.is_nan() or numerator.is_nan():
            return default
        return numerator / denominator
    except InvalidOperation:
        return default

# Configuration Management
def load_config(filepath: str, logger: logging.Logger) -> dict:
    """Loads configuration from JSON file with defaults."""
    default_config = {
        "symbol": "BTCUSDT",
        "interval": "15",
        "loop_delay": LOOP_DELAY_SECONDS,
        "orderbook_limit": 50,
        "signal_score_threshold": 2.0,
        "cooldown_sec": 60,
        "hysteresis_ratio": 0.85,
        "volume_confirmation_multiplier": 1.5,
        "execution": {
            "use_pybit": False,
            "buy_leverage": 10,
            "sell_leverage": 10,
            "tpsl_mode": "Full",
            "sl_scheme": {
                "type": "atr_multiple",
                "atr_multiple": 1.5,
                "percent": 2.0,
                "use_conditional_stop": True,
                "stop_order_type": "Market",
                "sl_trigger_by": "LastPrice"
            },
            "breakeven_after_tp1": {
                "enabled": True,
                "offset_type": "atr",
                "offset_value": 0.5,
                "lock_in_min_percent": 0.1
            },
            "trailing_stop": {
                "enabled": True,
                "activation_profit_atr": 2.0,
                "trail_distance_atr": 1.0
            },
            "live_sync": {
                "enabled": True,
                "only_track_linked": True,
                "max_exec_fetch": 100,
                "heartbeat": {
                    "enabled": True,
                    "interval_ms": 5000
                }
            }
        },
        "trade_management": {
            "enabled": True,
            "account_balance": 1000.0,
            "risk_per_trade_percent": 1.0,
            "stop_loss_atr_multiple": 1.5,
            "take_profit_atr_multiple": 2.0,
            "max_open_positions": 1,
            "order_precision": 5,
            "price_precision": 2,
            "slippage_percent": 0.001,
            "trading_fee_percent": 0.0005
        },
        "risk_guardrails": {
            "enabled": True,
            "max_day_loss_pct": 3.0,
            "max_drawdown_pct": 8.0,
            "cooldown_after_kill_min": 120,
            "spread_filter_bps": 5.0,
            "ev_filter_enabled": True
        },
        "session_filter": {
            "enabled": False,
            "utc_allowed": [["00:00", "08:00"], ["13:00", "20:00"]]
        },
        "pyramiding": {
            "enabled": False,
            "max_adds": 2,
            "step_atr": 0.7,
            "size_pct_of_initial": 0.5
        },
        "mtf_analysis": {
            "enabled": True,
            "higher_timeframes": ["60", "240"],
            "trend_indicators": ["ema", "sma"],
            "trend_period": 50,
            "mtf_request_delay_seconds": 0.5
        },
        "indicator_settings": {
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
            "fibonacci_window": 60,
            "macd_fast_period": 12,
            "macd_slow_period": 26,
            "macd_signal_period": 9,
            "adx_period": 14,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "stoch_rsi_oversold": 20,
            "stoch_rsi_overbought": 80,
            "cci_oversold": -100,
            "cci_overbought": 100,
            "williams_r_oversold": -80,
            "williams_r_overbought": -20,
            "mfi_oversold": 20,
            "mfi_overbought": 80
        },
        "indicators": {
            "atr": True,
            "ema_alignment": True,
            "sma_trend_filter": True,
            "momentum": True,
            "volume_confirmation": True,
            "stoch_rsi": True,
            "rsi": True,
            "bollinger_bands": True,
            "vwap": True,
            "cci": True,
            "wr": True,
            "psar": True,
            "mfi": True,
            "orderbook_imbalance": True,
            "fibonacci_levels": True,
            "macd": True,
            "adx": True,
            "candlestick_patterns": True
        },
        "weight_sets": {
            "default": {
                "ema_alignment": 0.15,
                "sma_trend_filter": 0.10,
                "momentum": 0.20,
                "volume_confirmation": 0.10,
                "bollinger_bands": 0.10,
                "vwap": 0.05,
                "cci": 0.05,
                "wr": 0.05,
                "psar": 0.05,
                "mfi": 0.05,
                "orderbook_imbalance": 0.05,
                "fibonacci_levels": 0.05,
                "macd": 0.10,
                "adx": 0.10,
                "candlestick_patterns": 0.05,
                "mtf_confluence": 0.10
            }
        }
    }
    
    # Try to load existing config
    if Path(filepath).exists():
        try:
            with open(filepath, 'r') as f:
                config = json.load(f)
            # Merge with defaults to ensure all keys exist
            config = deep_merge_dicts(default_config, config)
        except Exception as e:
            logger.error(f"Error loading config: {e}. Using defaults.")
            config = default_config
    else:
        config = default_config
        # Save default config
        try:
            with open(filepath, 'w') as f:
                json.dump(config, f, indent=4)
            logger.info(f"Created default config at {filepath}")
        except Exception as e:
            logger.error(f"Error saving default config: {e}")
    
    return config

def deep_merge_dicts(default: dict, override: dict) -> dict:
    """Deep merges two dictionaries, with override taking precedence."""
    result = default.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_dicts(result[key], value)
        else:
            result[key] = value
    return result

# Logging Setup
class SensitiveFormatter(logging.Formatter):
    """Formatter that redacts sensitive information."""
    SENSITIVE_WORDS = ["API_KEY", "API_SECRET", "password", "token"]
    
    def format(self, record):
        message = super().format(record)
        for word in self.SENSITIVE_WORDS:
            if word.lower() in message.lower():
                message = message.replace(word, "*" * len(word))
        return message

def setup_logger(name: str, level=logging.INFO) -> logging.Logger:
    """Sets up a logger with console and file handlers."""
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        logger.setLevel(level)
        logger.propagate = False
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(
            SensitiveFormatter(f"{NEON_BLUE}%(asctime)s - %(levelname)s - %(message)s{RESET}")
        )
        logger.addHandler(console_handler)
        
        # File handler
        log_file = Path(LOG_DIRECTORY) / f"{name}.log"
        file_handler = RotatingFileHandler(
            log_file, maxBytes=10*1024*1024, backupCount=5
        )
        file_handler.setFormatter(
            SensitiveFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(file_handler)
    
    return logger

# Alert System
class AlertSystem:
    """Handles alerts and notifications."""
    
    def __init__(self, logger: logging.Logger, config: dict = None):
        self.logger = logger
        self.config = config or {}
        self.alert_history = deque(maxlen=100)
        
    def send_alert(self, message: str, level: str = "INFO", force: bool = False):
        """Sends an alert with appropriate logging level."""
        timestamp = datetime.now(TIMEZONE)
        alert_data = {
            "timestamp": timestamp,
            "level": level,
            "message": message
        }
        self.alert_history.append(alert_data)
        
        # Log based on level
        if level == "ERROR":
            self.logger.error(f"{NEON_RED}ALERT: {message}{RESET}")
        elif level == "WARNING":
            self.logger.warning(f"{NEON_YELLOW}ALERT: {message}{RESET}")
        else:
            self.logger.info(f"{NEON_CYAN}ALERT: {message}{RESET}")
        
        # Here you could add email, telegram, discord notifications etc.

# API Client
class PybitTradingClient:
    """Manages Bybit API interactions."""
    
    def __init__(self, config: dict, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.enabled = False
        self.session = None
        self.ws_public = None
        self.ws_private = None
        self.category = "linear"
        
        if not PYBIT_AVAILABLE:
            self.logger.error("Pybit library not available. Live trading disabled.")
            return
            
        if not API_KEY or not API_SECRET:
            self.logger.error("API credentials not set. Live trading disabled.")
            return
        
        try:
            self.session = PybitHTTP(
                api_key=API_KEY,
                api_secret=API_SECRET,
                testnet=False
            )
            self.enabled = True
            self.logger.info("Bybit API client initialized successfully.")
        except Exception as e:
            self.logger.error(f"Failed to initialize Bybit client: {e}")
            self.enabled = False
    
    def fetch_current_price(self, symbol: str) -> Optional[Decimal]:
        """Fetches the current market price."""
        if not self.enabled:
            return None
        
        try:
            response = self.session.get_tickers(
                category=self.category,
                symbol=symbol
            )
            if response["retCode"] == 0 and response["result"]["list"]:
                price = Decimal(response["result"]["list"][0]["lastPrice"])
                self.logger.debug(f"Current price for {symbol}: {price}")
                return price
        except Exception as e:
            self.logger.error(f"Error fetching price: {e}")
        return None
    
    def fetch_klines(self, symbol: str, interval: str, limit: int = 200) -> Optional[pd.DataFrame]:
        """Fetches historical kline data."""
        if not self.enabled:
            return None
        
        try:
            response = self.session.get_kline(
                category=self.category,
                symbol=symbol,
                interval=interval,
                limit=limit
            )
            
            if response["retCode"] == 0 and response["result"]["list"]:
                df = pd.DataFrame(
                    response["result"]["list"],
                    columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"]
                )
                
                # Convert timestamp to datetime
                df["timestamp"] = pd.to_datetime(df["timestamp"].astype(int), unit='ms')
                df.set_index("timestamp", inplace=True)
                
                # Convert to numeric
                for col in ["open", "high", "low", "close", "volume", "turnover"]:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                
                # Sort by time
                df.sort_index(inplace=True)
                
                self.logger.debug(f"Fetched {len(df)} klines for {symbol}")
                return df
        except Exception as e:
            self.logger.error(f"Error fetching klines: {e}")
        return None
    
    def fetch_orderbook(self, symbol: str, limit: int = 50) -> Optional[dict]:
        """Fetches order book data."""
        if not self.enabled:
            return None
        
        try:
            response = self.session.get_orderbook(
                category=self.category,
                symbol=symbol,
                limit=limit
            )
            
            if response["retCode"] == 0:
                return response["result"]
        except Exception as e:
            self.logger.error(f"Error fetching orderbook: {e}")
        return None
    
    def place_order(self, symbol: str, side: str, qty: Decimal, 
                   order_type: str = "Market", price: Optional[Decimal] = None,
                   stop_loss: Optional[Decimal] = None, take_profit: Optional[Decimal] = None,
                   order_link_id: Optional[str] = None) -> Optional[dict]:
        """Places an order on Bybit."""
        if not self.enabled:
            return None
        
        try:
            params = {
                "category": self.category,
                "symbol": symbol,
                "side": side,
                "orderType": order_type,
                "qty": str(qty),
                "timeInForce": "GTC"
            }
            
            if price and order_type == "Limit":
                params["price"] = str(price)
            
            if stop_loss:
                params["stopLoss"] = str(stop_loss)
            
            if take_profit:
                params["takeProfit"] = str(take_profit)
            
            if order_link_id:
                params["orderLinkId"] = order_link_id
            
            response = self.session.place_order(**params)
            
            if response["retCode"] == 0:
                self.logger.info(f"Order placed: {side} {qty} {symbol}")
                return response["result"]
            else:
                self.logger.error(f"Order failed: {response.get('retMsg')}")
        except Exception as e:
            self.logger.error(f"Error placing order: {e}")
        return None
    
    def cancel_order(self, symbol: str, order_id: str = None, 
                    order_link_id: str = None) -> bool:
        """Cancels an order."""
        if not self.enabled:
            return False
        
        try:
            params = {
                "category": self.category,
                "symbol": symbol
            }
            
            if order_id:
                params["orderId"] = order_id
            elif order_link_id:
                params["orderLinkId"] = order_link_id
            else:
                return False
            
            response = self.session.cancel_order(**params)
            
            if response["retCode"] == 0:
                self.logger.info(f"Order cancelled: {order_id or order_link_id}")
                return True
        except Exception as e:
            self.logger.error(f"Error cancelling order: {e}")
        return False
    
    def get_positions(self, symbol: str = None) -> Optional[list]:
        """Gets current positions."""
        if not self.enabled:
            return None
        
        try:
            params = {"category": self.category}
            if symbol:
                params["symbol"] = symbol
            
            response = self.session.get_positions(**params)
            
            if response["retCode"] == 0:
                return response["result"]["list"]
        except Exception as e:
            self.logger.error(f"Error fetching positions: {e}")
        return None
    
    def set_leverage(self, symbol: str, buy_leverage: int, sell_leverage: int) -> bool:
        """Sets leverage for a symbol."""
        if not self.enabled:
            return False
        
        try:
            response = self.session.set_leverage(
                category=self.category,
                symbol=symbol,
                buyLeverage=str(buy_leverage),
                sellLeverage=str(sell_leverage)
            )
            
            if response["retCode"] == 0:
                self.logger.info(f"Leverage set: {symbol} Buy={buy_leverage}x, Sell={sell_leverage}x")
                return True
        except Exception as e:
            self.logger.error(f"Error setting leverage: {e}")
        return False

# Technical Indicators
class TechnicalIndicators:
    """Calculates technical indicators for trading analysis."""
    
    @staticmethod
    def calculate_sma(df: pd.DataFrame, period: int) -> pd.Series:
        """Simple Moving Average"""
        if not PANDAS_TA_AVAILABLE:
            return df['close'].rolling(window=period).mean()
        return ta.sma(df['close'], length=period)
    
    @staticmethod
    def calculate_ema(df: pd.DataFrame, period: int) -> pd.Series:
        """Exponential Moving Average"""
        if not PANDAS_TA_AVAILABLE:
            return df['close'].ewm(span=period, adjust=False).mean()
        return ta.ema(df['close'], length=period)
    
    @staticmethod
    def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Relative Strength Index"""
        if not PANDAS_TA_AVAILABLE:
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = gain / loss
            return 100 - (100 / (1 + rs))
        return ta.rsi(df['close'], length=period)
    
    @staticmethod
    def calculate_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
        """MACD indicator"""
        if not PANDAS_TA_AVAILABLE:
            exp1 = df['close'].ewm(span=fast, adjust=False).mean()
            exp2 = df['close'].ewm(span=slow, adjust=False).mean()
            macd = exp1 - exp2
            signal_line = macd.ewm(span=signal, adjust=False).mean()
            histogram = macd - signal_line
            return pd.DataFrame({'MACD': macd, 'Signal': signal_line, 'Histogram': histogram})
        return ta.macd(df['close'], fast=fast, slow=slow, signal=signal)
    
    @staticmethod
    def calculate_bollinger_bands(df: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> pd.DataFrame:
        """Bollinger Bands"""
        if not PANDAS_TA_AVAILABLE:
            sma = df['close'].rolling(window=period).mean()
            std = df['close'].rolling(window=period).std()
            upper = sma + (std * std_dev)
            lower = sma - (std * std_dev)
            return pd.DataFrame({'BB_Upper': upper, 'BB_Middle': sma, 'BB_Lower': lower})
        return ta.bbands(df['close'], length=period, std=std_dev)
    
    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Average True Range"""
        if not PANDAS_TA_AVAILABLE:
            high_low = df['high'] - df['low']
            high_close = np.abs(df['high'] - df['close'].shift())
            low_close = np.abs(df['low'] - df['close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = np.max(ranges, axis=1)
            return true_range.rolling(period).mean()
        return ta.atr(df['high'], df['low'], df['close'], length=period)
    
    @staticmethod
    def calculate_stochastic_rsi(df: pd.DataFrame, period: int = 14, k_period: int = 3, d_period: int = 3) -> pd.DataFrame:
        """Stochastic RSI"""
        if not PANDAS_TA_AVAILABLE:
            rsi = TechnicalIndicators.calculate_rsi(df, period)
            stoch_rsi_k = ((rsi - rsi.rolling(period).min()) / 
                          (rsi.rolling(period).max() - rsi.rolling(period).min())) * 100
            stoch_rsi_d = stoch_rsi_k.rolling(d_period).mean()
            return pd.DataFrame({'K': stoch_rsi_k, 'D': stoch_rsi_d})
        return ta.stochrsi(df['close'], length=period, rsi_length=period, k=k_period, d=d_period)
    
    @staticmethod
    def calculate_vwap(df: pd.DataFrame) -> pd.Series:
        """Volume Weighted Average Price"""
        if not PANDAS_TA_AVAILABLE:
            return (df['volume'] * (df['high'] + df['low'] + df['close']) / 3).cumsum() / df['volume'].cumsum()
        return ta.vwap(df['high'], df['low'], df['close'], df['volume'])
    
    @staticmethod
    def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """Average Directional Index"""
        if not PANDAS_TA_AVAILABLE:
            # Simplified ADX calculation
            plus_dm = df['high'].diff()
            minus_dm = -df['low'].diff()
            plus_dm[plus_dm < 0] = 0
            minus_dm[minus_dm < 0] = 0
            
            tr = TechnicalIndicators.calculate_atr(df, 1)
            plus_di = 100 * (plus_dm.rolling(period).mean() / tr.rolling(period).mean())
            minus_di = 100 * (minus_dm.rolling(period).mean() / tr.rolling(period).mean())
            
            dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
            adx = dx.rolling(period).mean()
            
            return pd.DataFrame({'ADX': adx, '+DI': plus_di, '-DI': minus_di})
        return ta.adx(df['high'], df['low'], df['close'], length=period)

# Position Manager
class PositionManager:
    """Manages trading positions and orders."""
    
    def __init__(self, config: dict, logger: logging.Logger, client: PybitTradingClient):
        self.config = config
        self.logger = logger
        self.client = client
        self.positions = {}
        self.orders = {}
        self.max_positions = config['trade_management']['max_open_positions']
        self.risk_per_trade = Decimal(str(config['trade_management']['risk_per_trade_percent'])) / 100
        
    def calculate_position_size(self, price: Decimal, stop_loss: Decimal, 
                               account_balance: Decimal) -> Decimal:
        """Calculates position size based on risk management."""
        risk_amount = account_balance * self.risk_per_trade
        price_diff = abs(price - stop_loss)
        
        if price_diff == 0:
            return Decimal("0")
        
        position_size = risk_amount / price_diff
        
        # Apply leverage if configured
        if self.config['execution']['use_pybit']:
            leverage = self.config['execution']['buy_leverage']
            position_size = position_size * Decimal(str(leverage))
        
        return position_size
    
    def open_position(self, signal: str, price: Decimal, atr: Decimal, 
                     conviction: float = 1.0) -> Optional[dict]:
        """Opens a new trading position."""
        if len(self.positions) >= self.max_positions:
            self.logger.warning("Maximum positions reached")
            return None
        
        # Calculate stop loss and take profit
        sl_multiplier = Decimal(str(self.config['trade_management']['stop_loss_atr_multiple']))
        tp_multiplier = Decimal(str(self.config['trade_management']['take_profit_atr_multiple']))
        
        if signal == "BUY":
            stop_loss = price - (atr * sl_multiplier)
            take_profit = price + (atr * tp_multiplier)
        else:
            stop_loss = price + (atr * sl_multiplier)
            take_profit = price - (atr * tp_multiplier)
        
        # Calculate position size
        account_balance = Decimal(str(self.config['trade_management']['account_balance']))
        position_size = self.calculate_position_size(price, stop_loss, account_balance)
        
        # Adjust for conviction
        position_size = position_size * Decimal(str(conviction))
        
        # Round to appropriate precision
        position_size = round_qty(position_size, Decimal("0.001"))
        stop_loss = round_price(stop_loss, self.config['trade_management']['price_precision'])
        take_profit = round_price(take_profit, self.config['trade_management']['price_precision'])
        
        # Create position object
        position = {
            'symbol': self.config['symbol'],
            'side': signal,
            'entry_price': price,
            'current_price': price,
            'size': position_size,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'entry_time': datetime.now(TIMEZONE),
            'pnl': Decimal("0"),
            'status': 'OPEN'
        }
        
        # Execute order if live trading
        if self.config['execution']['use_pybit'] and self.client.enabled:
            order_result = self.client.place_order(
                symbol=position['symbol'],
                side="Buy" if signal == "BUY" else "Sell",
                qty=position_size,
                stop_loss=stop_loss,
                take_profit=take_profit,
                order_link_id=f"pos_{int(time.time()*1000)}"
            )
            
            if order_result:
                position['order_id'] = order_result.get('orderId')
                self.positions[position['order_id']] = position
                self.logger.info(f"Position opened: {signal} {position_size} @ {price}")
            else:
                self.logger.error("Failed to open position")
                return None
        else:
            # Simulated position
            position_id = f"sim_{int(time.time()*1000)}"
            self.positions[position_id] = position
            self.logger.info(f"Simulated position: {signal} {position_size} @ {price}")
        
        return position
    
    def update_positions(self, current_price: Decimal):
        """Updates PnL for all open positions."""
        for pos_id, position in self.positions.items():
            if position['status'] != 'OPEN':
                continue
            
            position['current_price'] = current_price
            
            if position['side'] == 'BUY':
                position['pnl'] = (current_price - position['entry_price']) * position['size']
            else:
                position['pnl'] = (position['entry_price'] - current_price) * position['size']
            
            # Check stop loss
            if position['side'] == 'BUY' and current_price <= position['stop_loss']:
                self.close_position(pos_id, current_price, 'STOP_LOSS')
            elif position['side'] == 'SELL' and current_price >= position['stop_loss']:
                self.close_position(pos_id, current_price, 'STOP_LOSS')
            
            # Check take profit
            elif position['side'] == 'BUY' and current_price >= position['take_profit']:
                self.close_position(pos_id, current_price, 'TAKE_PROFIT')
            elif position['side'] == 'SELL' and current_price <= position['take_profit']:
                self.close_position(pos_id, current_price, 'TAKE_PROFIT')
            
            # Trailing stop logic
            if self.config['execution']['trailing_stop']['enabled']:
                self.update_trailing_stop(position, current_price)
    
    def update_trailing_stop(self, position: dict, current_price: Decimal):
        """Updates trailing stop for a position."""
        trailing_config = self.config['execution']['trailing_stop']
        activation_atr = Decimal(str(trailing_config['activation_profit_atr']))
        trail_distance_atr = Decimal(str(trailing_config['trail_distance_atr']))
        
        # Calculate profit in ATR multiples
        atr = Decimal(str(self.config.get('_last_atr_value', 1.0)))
        
        if position['side'] == 'BUY':
            profit_points = current_price - position['entry_price']
            profit_atr = profit_points / atr if atr > 0 else Decimal("0")
            
            if profit_atr >= activation_atr:
                new_stop = current_price - (atr * trail_distance_atr)
                if new_stop > position['stop_loss']:
                    position['stop_loss'] = new_stop
                    self.logger.debug(f"Trailing stop updated to {new_stop}")
        else:
            profit_points = position['entry_price'] - current_price
            profit_atr = profit_points / atr if atr > 0 else Decimal("0")
            
            if profit_atr >= activation_atr:
                new_stop = current_price + (atr * trail_distance_atr)
                if new_stop < position['stop_loss']:
                    position['stop_loss'] = new_stop
                    self.logger.debug(f"Trailing stop updated to {new_stop}")
    
    def close_position(self, position_id: str, exit_price: Decimal, reason: str):
        """Closes a position."""
        if position_id not in self.positions:
            return
        
        position = self.positions[position_id]
        position['exit_price'] = exit_price
        position['exit_time'] = datetime.now(TIMEZONE)
        position['status'] = 'CLOSED'
        position['close_reason'] = reason
        
        # Calculate final PnL
        if position['side'] == 'BUY':
            position['pnl'] = (exit_price - position['entry_price']) * position['size']
        else:
            position['pnl'] = (position['entry_price'] - exit_price) * position['size']
        
        self.logger.info(f"Position closed: {reason} PnL: {position['pnl']:.2f}")
        
        # Close order if live trading
        if self.config['execution']['use_pybit'] and self.client.enabled:
            if 'order_id' in position:
                self.client.cancel_order(
                    symbol=position['symbol'],
                    order_id=position['order_id']
                )

# Performance Tracker
class PerformanceTracker:
    """Tracks trading performance metrics."""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.trades = []
        self.daily_pnl = Decimal("0")
        self.total_pnl = Decimal("0")
        self.win_count = 0
        self.loss_count = 0
        self.max_drawdown = Decimal("0")
        self.peak_balance = Decimal("0")
        self.start_time = datetime.now(TIMEZONE)
        self.last_reset = datetime.now(TIMEZONE).date()
        
    def record_trade(self, position: dict):
        """Records a completed trade."""
        trade = {
            'timestamp': position.get('exit_time', datetime.now(TIMEZONE)),
            'symbol': position['symbol'],
            'side': position['side'],
            'entry_price': position['entry_price'],
            'exit_price': position.get('exit_price'),
            'size': position['size'],
            'pnl': position['pnl'],
            'reason': position.get('close_reason')
        }
        
        self.trades.append(trade)
        self.total_pnl += position['pnl']
        self.daily_pnl += position['pnl']
        
        if position['pnl'] > 0:
            self.win_count += 1
        else:
            self.loss_count += 1
        
        # Update drawdown
        if self.total_pnl > self.peak_balance:
            self.peak_balance = self.total_pnl
        
        drawdown = self.peak_balance - self.total_pnl
        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown
    
    def reset_daily_stats(self):
        """Resets daily statistics."""
        current_date = datetime.now(TIMEZONE).date()
        if current_date != self.last_reset:
            self.daily_pnl = Decimal("0")
            self.last_reset = current_date
            self.logger.info("Daily stats reset")
    
    def get_stats(self) -> dict:
        """Returns performance statistics."""
        total_trades = len(self.trades)
        win_rate = (self.win_count / total_trades * 100) if total_trades > 0 else 0
        
        return {
            'total_trades': total_trades,
            'win_count': self.win_count,
            'loss_count': self.loss_count,
            'win_rate': win_rate,
            'total_pnl': float(self.total_pnl),
            'daily_pnl': float(self.daily_pnl),
            'max_drawdown': float(self.max_drawdown),
            'running_time': str(datetime.now(TIMEZONE) - self.start_time)
        }

# Trading Analyzer
class TradingAnalyzer:
    """Analyzes market data and generates trading signals."""
    
    def __init__(self, df: pd.DataFrame, config: dict, logger: logging.Logger):
        self.df = df
        self.config = config
        self.logger = logger
        self.indicators = {}
        self.signal_scores = {}
        
        if not df.empty:
            self.calculate_indicators()
    
    def calculate_indicators(self):
        """Calculates all configured indicators."""
        indicator_calc = TechnicalIndicators()
        settings = self.config['indicator_settings']
        
        # ATR (always needed for position sizing)
        self.indicators['ATR'] = indicator_calc.calculate_atr(
            self.df, settings['atr_period']
        )
        
        # Moving Averages
        if self.config['indicators'].get('ema_alignment'):
            self.indicators['EMA_short'] = indicator_calc.calculate_ema(
                self.df, settings['ema_short_period']
            )
            self.indicators['EMA_long'] = indicator_calc.calculate_ema(
                self.df, settings['ema_long_period']
            )
        
        if self.config['indicators'].get('sma_trend_filter'):
            self.indicators['SMA_short'] = indicator_calc.calculate_sma(
                self.df, settings['sma_short_period']
            )
            self.indicators['SMA_long'] = indicator_calc.calculate_sma(
                self.df, settings['sma_long_period']
            )
        
        # Momentum Indicators
        if self.config['indicators'].get('rsi'):
            self.indicators['RSI'] = indicator_calc.calculate_rsi(
                self.df, settings['rsi_period']
            )
        
        if self.config['indicators'].get('stoch_rsi'):
            stoch_rsi = indicator_calc.calculate_stochastic_rsi(
                self.df, settings['stoch_rsi_period'],
                settings['stoch_k_period'], settings['stoch_d_period']
            )
            if isinstance(stoch_rsi, pd.DataFrame):
                self.indicators['StochRSI_K'] = stoch_rsi.iloc[:, 0]
                self.indicators['StochRSI_D'] = stoch_rsi.iloc[:, 1]
        
        # MACD
        if self.config['indicators'].get('macd'):
            macd = indicator_calc.calculate_macd(
                self.df, settings['macd_fast_period'],
                settings['macd_slow_period'], settings['macd_signal_period']
            )
            if isinstance(macd, pd.DataFrame):
                self.indicators['MACD'] = macd.iloc[:, 0]
                self.indicators['MACD_Signal'] = macd.iloc[:, 1]
                self.indicators['MACD_Histogram'] = macd.iloc[:, 2]
        
        # Bollinger Bands
        if self.config['indicators'].get('bollinger_bands'):
            bb = indicator_calc.calculate_bollinger_bands(
                self.df, settings['bollinger_bands_period'],
                settings['bollinger_bands_std_dev']
            )
            if isinstance(bb, pd.DataFrame):
                self.indicators['BB_Upper'] = bb.iloc[:, 0]
                self.indicators['BB_Middle'] = bb.iloc[:, 1]
                self.indicators['BB_Lower'] = bb.iloc[:, 2]
        
        # VWAP
        if self.config['indicators'].get('vwap'):
            self.indicators['VWAP'] = indicator_calc.calculate_vwap(self.df)
        
        # ADX
        if self.config['indicators'].get('adx'):
            adx = indicator_calc.calculate_adx(self.df, settings['adx_period'])
            if isinstance(adx, pd.DataFrame):
                self.indicators['ADX'] = adx.iloc[:, 0]
                self.indicators['Plus_DI'] = adx.iloc[:, 1]
                self.indicators['Minus_DI'] = adx.iloc[:, 2]
    
    def generate_signal(self, current_price: Decimal, 
                       orderbook_data: dict = None,
                       mtf_trends: dict = None) -> Tuple[str, float, dict]:
        """Generates trading signal based on indicators."""
        if self.df.empty or len(self.df) < MIN_DATA_POINTS:
            return "HOLD", 0.0, {}
        
        signal_score = 0.0
        signal_breakdown = {}
        weights = self.config['weight_sets']['default']
        settings = self.config['indicator_settings']
        
        last_close = float(self.df['close'].iloc[-1])
        
        # EMA Alignment
        if self.config['indicators'].get('ema_alignment'):
            ema_short = self.indicators.get('EMA_short')
            ema_long = self.indicators.get('EMA_long')
            
            if ema_short is not None and ema_long is not None:
                if not pd.isna(ema_short.iloc[-1]) and not pd.isna(ema_long.iloc[-1]):
                    if ema_short.iloc[-1] > ema_long.iloc[-1]:
                        score = weights.get('ema_alignment', 0.15)
                        signal_score += score
                        signal_breakdown['EMA_Bullish'] = score
                    else:
                        score = -weights.get('ema_alignment', 0.15)
                        signal_score += score
                        signal_breakdown['EMA_Bearish'] = score
        
        # RSI
        if self.config['indicators'].get('rsi'):
            rsi = self.indicators.get('RSI')
            if rsi is not None and not pd.isna(rsi.iloc[-1]):
                rsi_value = rsi.iloc[-1]
                if rsi_value < settings['rsi_oversold']:
                    score = weights.get('momentum', 0.2) * 0.5
                    signal_score += score
                    signal_breakdown['RSI_Oversold'] = score
                elif rsi_value > settings['rsi_overbought']:
                    score = -weights.get('momentum', 0.2) * 0.5
                    signal_score += score
                    signal_breakdown['RSI_Overbought'] = score
        
        # MACD
        if self.config['indicators'].get('macd'):
            macd = self.indicators.get('MACD')
            macd_signal = self.indicators.get('MACD_Signal')
            
            if macd is not None and macd_signal is not None:
                if not pd.isna(macd.iloc[-1]) and not pd.isna(macd_signal.iloc[-1]):
                    if len(macd) > 1:
                        # Check for crossover
                        if macd.iloc[-1] > macd_signal.iloc[-1] and macd.iloc[-2] <= macd_signal.iloc[-2]:
                            score = weights.get('macd', 0.1)
                            signal_score += score
                            signal_breakdown['MACD_Bullish_Cross'] = score
                        elif macd.iloc[-1] < macd_signal.iloc[-1] and macd.iloc[-2] >= macd_signal.iloc[-2]:
                            score = -weights.get('macd', 0.1)
                            signal_score += score
                            signal_breakdown['MACD_Bearish_Cross'] = score
        
        # Bollinger Bands
        if self.config['indicators'].get('bollinger_bands'):
            bb_upper = self.indicators.get('BB_Upper')
            bb_lower = self.indicators.get('BB_Lower')
            
            if bb_upper is not None and bb_lower is not None:
                if not pd.isna(bb_upper.iloc[-1]) and not pd.isna(bb_lower.iloc[-1]):
                    if last_close < bb_lower.iloc[-1]:
                        score = weights.get('bollinger_bands', 0.1)
                        signal_score += score
                        signal_breakdown['BB_Oversold'] = score
                    elif last_close > bb_upper.iloc[-1]:
                        score = -weights.get('bollinger_bands', 0.1)
                        signal_score += score
                        signal_breakdown['BB_Overbought'] = score
        
        # Orderbook Imbalance
        if orderbook_data and self.config['indicators'].get('orderbook_imbalance'):
            imbalance = self.calculate_orderbook_imbalance(orderbook_data)
            if imbalance != 0:
                score = imbalance * weights.get('orderbook_imbalance', 0.05)
                signal_score += score
                signal_breakdown['Orderbook_Imbalance'] = score
        
        # MTF Confluence
        if mtf_trends and self.config['mtf_analysis']['enabled']:
            mtf_score = self.calculate_mtf_score(mtf_trends)
            weighted_score = mtf_score * weights.get('mtf_confluence', 0.1)
            signal_score += weighted_score
            signal_breakdown['MTF_Confluence'] = weighted_score
        
        # Determine final signal
        threshold = self.config['signal_score_threshold']
        
        if signal_score >= threshold:
            signal = "BUY"
        elif signal_score <= -threshold:
            signal = "SELL"
        else:
            signal = "HOLD"
        
        return signal, signal_score, signal_breakdown
    
    def calculate_orderbook_imbalance(self, orderbook_data: dict) -> float:
        """Calculates order book imbalance."""
        if not orderbook_data:
            return 0.0
        
        bids = orderbook_data.get('b', [])
        asks = orderbook_data.get('a', [])
        
        if not bids or not asks:
            return 0.0
        
        # Calculate total bid and ask volume
        bid_volume = sum(float(bid[1]) for bid in bids[:10])
        ask_volume = sum(float(ask[1]) for ask in asks[:10])
        
        total_volume = bid_volume + ask_volume
        if total_volume == 0:
            return 0.0
        
        # Calculate imbalance (-1 to 1)
        imbalance = (bid_volume - ask_volume) / total_volume
        
        return imbalance
    
    def calculate_mtf_score(self, mtf_trends: dict) -> float:
        """Calculates multi-timeframe trend confluence score."""
        if not mtf_trends:
            return 0.0
        
        bullish_count = sum(1 for trend in mtf_trends.values() if trend == "UP")
        bearish_count = sum(1 for trend in mtf_trends.values() if trend == "DOWN")
        total_count = len(mtf_trends)
        
        if total_count == 0:
            return 0.0
        
        # Calculate score (-1 to 1)
        score = (bullish_count - bearish_count) / total_count
        
        return score

# Helper Functions
def in_allowed_session(config: dict) -> bool:
    """Checks if current time is within allowed trading sessions."""
    if not config['session_filter']['enabled']:
        return True
    
    current_time = datetime.now(TIMEZONE)
    current_hour_min = current_time.strftime("%H:%M")
    
    for session in config['session_filter']['utc_allowed']:
        start_time = session[0]
        end_time = session[1]
        
        if start_time <= current_hour_min <= end_time:
            return True
    
    return False

def display_status(analyzer: TradingAnalyzer, position_manager: PositionManager,
                  performance_tracker: PerformanceTracker, signal: str, 
                  score: float, logger: logging.Logger):
    """Displays current bot status."""
    logger.info(f"{NEON_PURPLE}{'='*60}{RESET}")
    logger.info(f"{NEON_CYAN}Bot Status Update{RESET}")
    logger.info(f"{NEON_PURPLE}{'='*60}{RESET}")
    
    # Current Signal
    signal_color = NEON_GREEN if signal == "BUY" else NEON_RED if signal == "SELL" else NEON_YELLOW
    logger.info(f"Signal: {signal_color}{signal}{RESET} (Score: {score:.2f})")
    
    # Positions
    open_positions = [p for p in position_manager.positions.values() if p['status'] == 'OPEN']
    if open_positions:
        logger.info(f"Open Positions: {len(open_positions)}")
        for pos in open_positions:
            pnl_color = NEON_GREEN if pos['pnl'] >= 0 else NEON_RED
            logger.info(f"  {pos['side']} {pos['size']} @ {pos['entry_price']} | PnL: {pnl_color}{pos['pnl']:.2f}{RESET}")
    else:
        logger.info("No open positions")
    
    # Performance
    stats = performance_tracker.get_stats()
    pnl_color = NEON_GREEN if stats['total_pnl'] >= 0 else NEON_RED
    logger.info(f"Total PnL: {pnl_color}{stats['total_pnl']:.2f}{RESET}")
    logger.info(f"Win Rate: {stats['win_rate']:.1f}% ({stats['win_count']}/{stats['total_trades']})")
    logger.info(f"Max Drawdown: {stats['max_drawdown']:.2f}")
    
    logger.info(f"{NEON_PURPLE}{'='*60}{RESET}")

# Main Bot
async def main():
    """Main bot execution loop."""
    # Setup
    logger = setup_logger("whalebot", logging.INFO)
    logger.info(f"{NEON_GREEN}Whalebot Starting...{RESET}")
    
    # Load configuration
    config = load_config(CONFIG_FILE, logger)
    
    # Validate API credentials
    if config['execution']['use_pybit']:
        if not API_KEY or not API_SECRET:
            logger.error(f"{NEON_RED}API credentials not set. Cannot use live trading.{RESET}")
            config['execution']['use_pybit'] = False
    
    # Initialize components
    alert_system = AlertSystem(logger, config)
    pybit_client = PybitTradingClient(config, logger)
    position_manager = PositionManager(config, logger, pybit_client)
    performance_tracker = PerformanceTracker(logger)
    
    # Set leverage if live trading
    if config['execution']['use_pybit'] and pybit_client.enabled:
        leverage_set = pybit_client.set_leverage(
            config['symbol'],
            config['execution']['buy_leverage'],
            config['execution']['sell_leverage']
        )
        if not leverage_set:
            alert_system.send_alert("Failed to set leverage", "WARNING")
    
    logger.info(f"Trading Symbol: {config['symbol']}")
    logger.info(f"Interval: {config['interval']}")
    logger.info(f"Live Trading: {'Enabled' if config['execution']['use_pybit'] else 'Disabled'}")
    
    # Main loop
    loop_count = 0
    while True:
        try:
            loop_count += 1
            logger.info(f"{NEON_BLUE}Loop #{loop_count} Starting...{RESET}")
            
            # Reset daily stats
            performance_tracker.reset_daily_stats()
            
            # Check risk guardrails
            if config['risk_guardrails']['enabled']:
                stats = performance_tracker.get_stats()
                
                # Check daily loss
                max_daily_loss = float(config['trade_management']['account_balance']) * \
                                config['risk_guardrails']['max_day_loss_pct'] / 100
                
                if stats['daily_pnl'] <= -max_daily_loss:
                    logger.error(f"{NEON_RED}Daily loss limit reached. Stopping trading.{RESET}")
                    alert_system.send_alert("Daily loss limit reached", "ERROR")
                    await asyncio.sleep(config['risk_guardrails']['cooldown_after_kill_min'] * 60)
                    continue
                
                # Check max drawdown
                max_drawdown = float(config['trade_management']['account_balance']) * \
                              config['risk_guardrails']['max_drawdown_pct'] / 100
                
                if stats['max_drawdown'] >= max_drawdown:
                    logger.error(f"{NEON_RED}Max drawdown reached. Stopping trading.{RESET}")
                    alert_system.send_alert("Max drawdown reached", "ERROR")
                    await asyncio.sleep(config['risk_guardrails']['cooldown_after_kill_min'] * 60)
                    continue
            
            # Check trading session
            if not in_allowed_session(config):
                logger.info("Outside trading session. Waiting...")
                await asyncio.sleep(config['loop_delay'])
                continue
            
            # Fetch current price
            current_price = pybit_client.fetch_current_price(config['symbol'])
            if current_price is None:
                # Fallback: use a dummy price for simulation
                current_price = Decimal("50000")
                logger.warning("Using dummy price for simulation")
            
            # Fetch market data
            df = pybit_client.fetch_klines(
                config['symbol'],
                config['interval'],
                limit=200
            )
            
            if df is None or df.empty:
                logger.warning("No market data available. Waiting...")
                await asyncio.sleep(config['loop_delay'])
                continue
            
            # Fetch orderbook
            orderbook_data = None
            if config['indicators'].get('orderbook_imbalance'):
                orderbook_data = pybit_client.fetch_orderbook(
                    config['symbol'],
                    config['orderbook_limit']
                )
            
            # Multi-timeframe analysis
            mtf_trends = {}
            if config['mtf_analysis']['enabled']:
                for htf in config['mtf_analysis']['higher_timeframes']:
                    htf_df = pybit_client.fetch_klines(
                        config['symbol'],
                        htf,
                        limit=100
                    )
                    
                    if htf_df is not None and not htf_df.empty:
                        # Simple trend determination
                        sma = htf_df['close'].rolling(window=config['mtf_analysis']['trend_period']).mean()
                        if not pd.isna(sma.iloc[-1]):
                            if htf_df['close'].iloc[-1] > sma.iloc[-1]:
                                mtf_trends[f"HTF_{htf}"] = "UP"
                            else:
                                mtf_trends[f"HTF_{htf}"] = "DOWN"
                    
                    await asyncio.sleep(config['mtf_analysis']['mtf_request_delay_seconds'])
            
            # Analyze and generate signal
            analyzer = TradingAnalyzer(df, config, logger)
            signal, score, breakdown = analyzer.generate_signal(
                current_price, orderbook_data, mtf_trends
            )
            
            # Store ATR for position sizing
            atr = analyzer.indicators.get('ATR')
            if atr is not None and not pd.isna(atr.iloc[-1]):
                config['_last_atr_value'] = float(atr.iloc[-1])
            
            # Update positions
            position_manager.update_positions(current_price)
            
            # Record closed positions
            for pos in position_manager.positions.values():
                if pos['status'] == 'CLOSED' and 'recorded' not in pos:
                    performance_tracker.record_trade(pos)
                    pos['recorded'] = True
            
            # Display status
            display_status(analyzer, position_manager, performance_tracker, 
                          signal, score, logger)
            
            # Execute signal
            if signal != "HOLD" and abs(score) >= config['signal_score_threshold']:
                # Calculate conviction
                conviction = min(1.0, abs(score) / (config['signal_score_threshold'] * 2))
                
                # Open position
                atr_value = Decimal(str(config.get('_last_atr_value', 1.0)))
                position = position_manager.open_position(
                    signal, current_price, atr_value, conviction
                )
                
                if position:
                    alert_system.send_alert(
                        f"Position opened: {signal} @ {current_price}", 
                        "INFO"
                    )
            
            # Sleep before next iteration
            await asyncio.sleep(config['loop_delay'])
            
        except KeyboardInterrupt:
            logger.info(f"{NEON_YELLOW}Bot stopped by user{RESET}")
            break
        except Exception as e:
            logger.error(f"{NEON_RED}Error in main loop: {e}{RESET}")
            logger.error(traceback.format_exc())
            alert_system.send_alert(f"Error in main loop: {e}", "ERROR")
            await asyncio.sleep(config['loop_delay'] * 2)
    
    # Cleanup
    logger.info(f"{NEON_GREEN}Bot shutdown complete{RESET}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{NEON_YELLOW}Bot stopped by user{RESET}")
    except Exception as e:
        print(f"{NEON_RED}Fatal error: {e}{RESET}")
        print(traceback.format_exc())
