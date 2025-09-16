<<<<<<< HEAD
"""
Fully-refactored Bybit “WhaleBot” – leaner, faster, clearer
──────────────────────────────────────────────────────────
• ConfigManager……… handles JSON config + validation / backup
• BybitAPI……………..   resilient, signed API wrapper
• TradingAnalyzer…… vectorised indicator engine + signal generator
• main()………………..   orchestrates fetch → analyse → signal loop
"""

# ───────────────────────────── Imports ──────────────────────────────
import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime
from decimal import Decimal, getcontext
from typing import Any
=======
# whalebot_enhanced.py
# A robust, upgraded Bybit-driven trading bot with a modular design,
# enhanced error handling, and improved performance.
# Fully compatible with the original config.json and behavior.
from __future__ import annotations
import os
import json
import time
import hmac
import hashlib
import logging
from datetime import datetime, timezone
from decimal import Decimal, getcontext, InvalidOperation, ROUND_HALF_UP
from functools import wraps # Removed lru_cache import if not used elsewhere, or keep if needed for other methods.
import inspect
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, Callable
import requests
import numpy as np
import pandas as pd
from colorama import Fore, Style, init as colorama_init
from dotenv import load_dotenv
>>>>>>> 1917b20 (WIP)
from zoneinfo import ZoneInfo
from dataclasses import dataclass, field
import warnings

<<<<<<< HEAD
import numpy as np
import pandas as pd
import requests
from colorama import Fore, Style, init
from dotenv import load_dotenv
from logger_config import setup_custom_logger
=======
# --- Conditional TA-Lib Import ---
try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False
    print(f"{Fore.YELLOW}Warning: TA-Lib not found. Falling back to Pandas/Numpy implementations. For better performance, install TA-Lib: pip install TA-Lib{Style.RESET_ALL}")

# ----------------------------------------------------------------------------
# 1. GLOBAL INITIALIZATION & CONSTANTS
# ----------------------------------------------------------------------------
colorama_init(autoreset=True)

# --- Color Palette ---
NEON_GREEN = Fore.LIGHTGREEN_EX
NEON_BLUE = Fore.CYAN
NEON_PURPLE = Fore.MAGENTA
NEON_YELLOW = Fore.YELLOW
NEON_RED = Fore.LIGHTRED_EX
RESET = Style.RESET_ALL

# --- Core Constants ---
VALID_INTERVALS = ["1", "3", "5", "15", "30", "60", "120", "240", "D", "W", "M"]
RETRY_ERROR_CODES = {429, 500, 502, 503, 504}
TIMEZONE = ZoneInfo("America/Chicago")
BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"
LOG_DIR = BASE_DIR / "bot_logs"
LOG_DIR.mkdir(exist_ok=True)

# Set high precision for Decimal math to avoid floating point errors in financial calcs
getcontext().prec = 28
getcontext().rounding = ROUND_HALF_UP # Consistent rounding strategy

# Suppress pandas FutureWarning
warnings.filterwarnings("ignore", category=FutureWarning)

# ----------------------------------------------------------------------------
# 2. ENVIRONMENT & LOGGER SETUP
# ----------------------------------------------------------------------------

class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for different log levels."""
    
    COLORS = {
        'DEBUG': Fore.CYAN,
        'INFO': Fore.LIGHTGREEN_EX,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.LIGHTRED_EX,
        'CRITICAL': Fore.MAGENTA
    }
    
    def format(self, record):
        log_color = self.COLORS.get(record.levelname, Style.RESET_ALL)
        record.levelname = f"{log_color}{record.levelname}{Style.RESET_ALL}"
        return super().format(record)

def setup_logger(name: str) -> logging.Logger:
    """Creates a self-contained, colorized logger with file output."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Prevent duplicate handlers if called multiple times for the same logger name
    if not logger.handlers:
        # Console handler
        console_handler = logging.StreamHandler()
        console_formatter = ColoredFormatter(
            "%(asctime)s │ %(levelname)-8s │ %(message)s",
            datefmt="%H:%M:%S"
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
        
        # File handler (date-stamped)
        log_file_name = f"{name}_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(LOG_DIR / log_file_name)
        file_formatter = logging.Formatter(
            "%(asctime)s │ %(levelname)-8s │ %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
    return logger
>>>>>>> 1917b20 (WIP)

load_dotenv()
API_KEY = os.getenv("BYBIT_API_KEY") or ""
API_SECRET = os.getenv("BYBIT_API_SECRET") or ""
BASE_URL = os.getenv("BYBIT_BASE_URL", "https://api.bybit.com")

LOGGER = setup_logger("whalebot_main")

# ----------------------------------------------------------------------------
# 3. UTILITY DECORATORS & CONFIGURATION
# ----------------------------------------------------------------------------
def retry_api_call(max_attempts: int = 3, delay: int = 5, backoff_factor: float = 2.0):
    """Decorator to retry API calls on specified error codes with exponential backoff."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except requests.exceptions.RequestException as e:
                    status_code = getattr(e.response, 'status_code', None)
                    if status_code in RETRY_ERROR_CODES:
                        wait_time = delay * (backoff_factor**(attempt - 1))
                        LOGGER.warning(f"{NEON_YELLOW}API request failed (Attempt {attempt}/{max_attempts}, Status: {status_code}). Retrying in {wait_time:.1f}s...{RESET}")
                        time.sleep(wait_time)
                    else:
                        LOGGER.error(f"{NEON_RED}Fatal API error: {e}{RESET}")
                        raise # Re-raise for non-retryable errors
            LOGGER.error(f"{NEON_RED}API call failed after {max_attempts} attempts. Aborting.{RESET}")
            return None # Indicate failure after max retries
        return wrapper
    return decorator

@dataclass(slots=True)
class BotConfig:
    """A lightweight, type-safe wrapper around the JSON configuration."""
    raw: Dict[str, Any]
    
    def __getitem__(self, key: str) -> Any:
        return self.raw[key]
    
    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)

    # FIXED: Removed @lru_cache here to resolve TypeError: unhashable type: 'BotConfig'
    def get_nested(self, path: str, default: Any = None) -> Any:
        """Get nested configuration value using dot notation (e.g., "section.key")."""
        keys = path.split('.')
        value = self.raw
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return default
            else:
                return default # Path not a dict at this point
        return value

<<<<<<< HEAD
# Retry tuning
MAX_RETRY            = 3
RETRY_BACKOFF_SEC    = 5
RETRY_CODES          = {429, 500, 502, 503, 504}
VALID_INTERVALS      = ["1","3","5","15","30","60","120","240","D","W","M"]

# ────────────────────────── Config Manager ──────────────────────────
class ConfigManager:
    """Load / validate / auto-heal JSON configuration."""

    DEFAULT: dict[str, Any] = {
=======
def _get_default_config() -> Dict[str, Any]:
    """Returns the default configuration dictionary with all indicators and enhanced settings."""
    return {
>>>>>>> 1917b20 (WIP)
        "interval": "15",
        "analysis_interval": 30,
        "retry_delay": 5,
        "momentum_period": 10,
        "volume_ma_period": 20,
        "atr_period": 14,
        "signal_score_threshold": 1.0,
        "stop_loss_multiple": 1.5,
        "take_profit_multiple": 1.0,
        "order_book_debounce_s": 10,
        "order_book_depth_to_check": 10,
        "atr_change_threshold": 0.005,
        "volume_confirmation_multiplier": 1.5,
        "signal_cooldown_s": 60,
        "ema_short_period": 12,
        "ema_long_period": 26,
        "indicators": { # All indicators
            "ema_alignment": True, "momentum": True, "volume_confirmation": True,
            "divergence": True, "stoch_rsi": True, "rsi": True, "macd": True,
            "vwap": True, "obv": True, "adi": True, "cci": True, "wr": True,
            "adx": True, "psar": True, "fve": True, "sma_10": True, "mfi": True,
            "stochastic_oscillator": True, "cmf": True, "ao": True, "vi": True, "bb": True,
            "keltner_channels": True, "ichimoku": True, "supertrend": True, # New indicators
        },
        "weight_sets": { # Dynamic weight sets based on market conditions
            "low_volatility": { # Fallback / Default
                "ema_alignment": 0.3, "momentum": 0.2, "volume_confirmation": 0.2,
                "divergence": 0.1, "stoch_rsi": 0.5, "rsi": 0.3, "macd": 0.3,
                "vwap": 0.2, "obv": 0.1, "adi": 0.1, "cci": 0.1, "wr": 0.1,
                "adx": 0.1, "psar": 0.1, "fve": 0.2, "sma_10": 0.0, "mfi": 0.3,
                "stochastic_oscillator": 0.4, "cmf": 0.2, "ao": 0.3, "vi": 0.2, "bb": 0.4,
                "keltner_channels": 0.1, "ichimoku": 0.2, "supertrend": 0.2,
            },
            "high_volatility": { # For very choppy markets
                "ema_alignment": 0.1, "momentum": 0.4, "volume_confirmation": 0.1,
                "divergence": 0.2, "stoch_rsi": 0.4, "rsi": 0.4, "macd": 0.4,
                "vwap": 0.1, "obv": 0.1, "adi": 0.1, "cci": 0.1, "wr": 0.1,
                "adx": 0.1, "psar": 0.1, "fve": 0.3, "sma_10": 0.0, "mfi": 0.4,
                "stochastic_oscillator": 0.3, "cmf": 0.3, "ao": 0.5, "vi": 0.4, "bb": 0.1,
                "keltner_channels": 0.2, "ichimoku": 0.1, "supertrend": 0.1,
            },
            "trending_up": { # For strong uptrends
                "ema_alignment": 0.5, "momentum": 0.4, "macd": 0.4,
                "adx": 0.3, "psar": 0.3, "supertrend": 0.5, "ichimoku": 0.4,
            },
            "trending_down": { # For strong downtrends
                "ema_alignment": 0.5, "momentum": 0.4, "macd": 0.4,
                "adx": 0.3, "psar": 0.3, "supertrend": 0.5, "ichimoku": 0.4,
            },
            "ranging": { # For sideways markets
                "rsi": 0.5, "stoch_rsi": 0.5, "bb": 0.4,
                "cci": 0.3, "mfi": 0.3, "stochastic_oscillator": 0.4,
            },
            "volatile": { # For unpredictable, high-swing markets
                "atr": 0.4, "bb": 0.4, "keltner_channels": 0.4,
                "vi": 0.3, "volume_confirmation": 0.3,
            },
            "calm": { # For low volatility, tight range markets
                "vwap": 0.3, "obv": 0.2, "adi": 0.2, "cmf": 0.2,
            }
        },
        "stoch_rsi_oversold_threshold": 20, "stoch_rsi_overbought_threshold": 80,
        "order_book_support_confidence_boost": 3, "order_book_resistance_confidence_boost": 3,
        "indicator_periods": { # All periods, including new indicators
            "rsi": 14, "mfi": 14, "cci": 20, "williams_r": 14, "adx": 14,
            "stoch_rsi_period": 14, "stoch_rsi_k_period": 3, "stoch_rsi_d_period": 3,
            "momentum": 10, "volume_ma": 20, "atr": 14, "sma_10": 10,
            "fve_price_ema": 10, "fve_obv_sma": 20, "fve_atr_sma": 20,
            "stoch_osc_k": 14, "stoch_osc_d": 3, "vwap": 14,
            "cmf": 20, "ao_short": 5, "ao_long": 34, "vi": 14, "bb": 20,
            "keltner_atr_period": 10, "keltner_multiplier": 1.5,
            "ichimoku_tenkan_period": 9, "ichimoku_kijun_period": 26, "ichimoku_senkou_period": 52,
            "ichimoku_chikou_shift": 26,
            "supertrend_atr_period": 10, "supertrend_multiplier": 3,
        },
        "order_book_analysis": {"enabled": True, "wall_threshold_multiplier": 2.0, "depth_to_check": 10},
        "market_condition_detection": {
            "adx_trend_threshold": 25,
            "atr_volatility_threshold_multiplier": 1.5, # Multiplier of average ATR
            "bb_bandwidth_threshold_multiplier": 0.8, # Multiplier of average BB width for ranging
        }
    }

def load_config(fp: Path) -> BotConfig:
    """Loads config from file, creating a default if missing or corrupt, and merges with defaults."""
    defaults = _get_default_config()
    
    # Helper for deep merging dictionaries
    def deep_merge(base: dict, update: dict) -> dict:
        for k, v in update.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                base[k] = deep_merge(base[k], v)
            else:
                base[k] = v
        return base

<<<<<<< HEAD
    # ── helpers
    def load(self) -> dict[str, Any]:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            merged = {**self.DEFAULT, **data}
            self.validate(merged)
            return merged
        except FileNotFoundError:
            logger.warning(f"{C['Y']}Config not found → created default{C['X']}")
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"{C['R']}Corrupt config: {e}{C['X']}")
            backup = f"{self.path}.bak_{int(time.time())}"
            try:
                os.rename(self.path, backup)
                logger.warning(f"{C['Y']}Backed up bad config → {backup}{C['X']}")
            except Exception:
                pass
        self.save(self.DEFAULT)
        return self.DEFAULT

    def save(self, cfg: dict[str, Any]) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)

    @staticmethod
    def validate(cfg: dict[str, Any]) -> None:
        if cfg["interval"] not in VALID_INTERVALS:
            raise ValueError("interval invalid")
        if cfg["analysis_interval"] <= 0:
            raise ValueError("analysis_interval invalid")
=======
    if not fp.exists():
        LOGGER.warning(f"{NEON_YELLOW}Config not found. Creating default at: {fp}{RESET}")
        try:
            fp.write_text(json.dumps(defaults, indent=4))
        except IOError as e:
            LOGGER.error(f"{NEON_RED}Failed to write default config: {e}{RESET}")
            return BotConfig(defaults) # Return defaults if write fails
        return BotConfig(defaults)
    
    try:
        user_cfg = json.loads(fp.read_text())
        merged = deep_merge(defaults, user_cfg) # Deep merge user config onto defaults
    except (json.JSONDecodeError, IOError) as e:
        LOGGER.error(f"{NEON_RED}Error with config file: {e}. Attempting to rebuild default.{RESET}")
        backup_fp = fp.with_name(f"{fp.stem}.bak_{int(time.time())}{fp.suffix}")
        try:
            fp.rename(backup_fp) # Back up corrupt config
            fp.write_text(json.dumps(defaults, indent=4)) # Write fresh default
        except OSError as backup_err:
            LOGGER.error(f"{NEON_RED}Could not back up corrupt config: {backup_err}{RESET}")
        merged = defaults # Use defaults if rebuild fails or is needed
    
    # Validate critical settings
    if merged["interval"] not in VALID_INTERVALS:
        LOGGER.warning(f"{NEON_YELLOW}Invalid interval '{merged['interval']}' in config. Falling back to default '15'.{RESET}")
        merged["interval"] = "15"

    return BotConfig(merged)

CFG = load_config(CONFIG_FILE)
>>>>>>> 1917b20 (WIP)

# ----------------------------------------------------------------------------
# 4. BYBIT API CLIENT
# ----------------------------------------------------------------------------
class BybitClient:
    """A client to interact with the Bybit API."""
    def __init__(self, base_url: str, api_key: str, api_secret: str, log: logging.Logger):
        self.base_url = base_url
        self.api_key = api_key
        self.api_secret = api_secret
        self.log = log
        self.kline_cache: Dict[str, Any] = {} # {f"{symbol}_{interval}_{limit}": {'data': df, 'timestamp': time}}

<<<<<<< HEAD
    def _sign(self, params: dict[str, Any]) -> str:
        q = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        return hmac.new(self.secret.encode(), q.encode(), hashlib.sha256).hexdigest()

    def req(self, method: str, ep: str, params: dict[str, Any] | None = None) -> dict | None:
=======
    def _generate_signature(self, params: dict) -> str:
        """Generates the HMAC SHA256 signature for Bybit API requests."""
        param_str = "&".join([f"{key}={value}" for key, value in sorted(params.items())])
        return hmac.new(self.api_secret.encode(), param_str.encode(), hashlib.sha256).hexdigest()

    @retry_api_call()
    def _bybit_request(self, method: str, endpoint: str, params: Dict[str, Any] = None) -> Union[dict, None]:
        """Sends a signed request to the Bybit API with retry logic."""
>>>>>>> 1917b20 (WIP)
        params = params or {}
        params['timestamp'] = str(int(time.time() * 1000))
        signature = self._generate_signature(params)
        headers = {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": params['timestamp'],
            "Content-Type": "application/json"
        }
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = requests.request(
                method, url, headers=headers,
                params=params if method == "GET" else None,
                json=params if method == "POST" else None,
                timeout=10
            )
            response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
            return response.json()
        except requests.exceptions.RequestException as e:
            # The retry_api_call decorator will catch this, but good to log here too for context
            self.log.error(f"{NEON_RED}Bybit request failed: {e}. Response: {getattr(e.response, 'text', 'N/A')}{RESET}")
            raise # Re-raise to allow decorator to handle retries

    @retry_api_call()
    def fetch_current_price(self, symbol: str) -> Optional[Decimal]:
        """Fetches the latest price for a given symbol."""
        endpoint = "/v5/market/tickers"
        params = {"category": "linear", "symbol": symbol}
        response_data = self._bybit_request("GET", endpoint, params)
        if response_data and response_data.get("retCode") == 0 and response_data.get("result"):
            tickers = response_data["result"].get("list")
            if tickers:
                # Ensure we get the correct symbol's ticker if multiple are returned (unlikely for specific query)
                for ticker in tickers:
                    if ticker.get("symbol") == symbol:
                        last_price = ticker.get("lastPrice")
                        try:
                            return Decimal(str(last_price)) if last_price else None
                        except InvalidOperation:
                            self.log.error(f"{NEON_RED}Invalid price format received for {symbol}: '{last_price}'{RESET}")
                            return None
        self.log.error(f"{NEON_RED}Could not fetch current price for {symbol}. Response: {response_data}{RESET}")
        return None

    @retry_api_call()
    def fetch_klines(self, symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
        """Fetches historical K-line data with caching."""
        kline_key = f"{symbol}_{interval}_{limit}"
        
        # Check cache
        if kline_key in self.kline_cache and (time.time() - self.kline_cache[kline_key]['timestamp'] < CFG['analysis_interval']):
            return self.kline_cache[kline_key]['data'].copy() # Return a copy to prevent external modification

<<<<<<< HEAD
    # Convenience wrappers
    def price(self, symbol: str) -> Decimal | None:
        d = self.req("GET", "/v5/market/tickers", {"category":"linear","symbol":symbol})
        try:
            return Decimal(next(i["lastPrice"] for i in d["result"]["list"] if i["symbol"]==symbol))
        except Exception:
            return None

    def klines(self, symbol: str, interval: str, limit=200) -> pd.DataFrame:
        d = self.req("GET","/v5/market/kline",
                     {"symbol":symbol,"interval":interval,"limit":limit,"category":"linear"})
        if not d or d["retCode"]!=0:
            return pd.DataFrame()
        cols = ["time","open","high","low","close","vol","turn"]
        df = pd.DataFrame(d["result"]["list"], columns=cols)
        df["time"] = pd.to_datetime(df["time"], unit="ms")
        for c in cols[1:]: df[c] = pd.to_numeric(df[c], errors="coerce")
        return df.dropna().sort_values("time").reset_index(drop=True)

    def orderbook(self, symbol: str, depth: int = 50):
        return self.req("GET","/v5/market/orderbook",
                        {"symbol":symbol,"limit":depth,"category":"linear"})

# ─────────────────────── Indicator Utilities ───────────────────────
def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

def atr(df: pd.DataFrame, window: int) -> pd.Series:
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"]  - df["close"].shift()).abs()
    ], axis=1).max(axis=1)
    return ema(tr, window)

# ───────────────────────── Trading Analyzer ─────────────────────────
class TradingAnalyzer:
    def __init__(self, df: pd.DataFrame, cfg: dict[str,Any], log: logging.Logger):
        self.df, self.cfg, self.log = df, cfg, log
        self.ind: dict[str, Any] = {}
        self._prep()

    def _prep(self):
        self.ind["atr"] = atr(self.df, self.cfg["atr_period"])
        self.df["vol_ma"] = self.df["vol"].rolling(self.cfg["volume_ma_period"]).mean()
        # EMA align
        self.df["ema_s"] = ema(self.df["close"], self.cfg["momentum_ma_short"])
        self.df["ema_l"] = ema(self.df["close"], self.cfg["momentum_ma_long"])

    # ── indicator calculations
    def ema_alignment_score(self) -> float:
        s,l = self.df["ema_s"].iloc[-1], self.df["ema_l"].iloc[-1]
        if pd.isna(s) or pd.isna(l): return 0.0
        return 1.0 if s>l else -1.0 if s<l else 0.0

    def volume_confirm(self) -> bool:
        return self.df["vol"].iloc[-1] > self.df["vol_ma"].iloc[-1]*1.5

    def stoch_rsi(self, k_win=3, d_win=3, rsi_win=14, stoch_win=14) -> tuple[float,float]:
        rsi = self._rsi(rsi_win)
        if rsi.isna().all(): return 0.0,0.0
        min_rsi = rsi.rolling(stoch_win).min()
        max_rsi = rsi.rolling(stoch_win).max()
        stoch = 100*(rsi - min_rsi)/(max_rsi - min_rsi).replace(0,np.nan)
        k = stoch.rolling(k_win).mean()
        d = k.rolling(d_win).mean()
        return float(k.iloc[-1]), float(d.iloc[-1])

    def _rsi(self, window:int) -> pd.Series:
        diff = self.df["close"].diff()
        up, down = diff.clip(lower=0), -diff.clip(upper=0)
        ma_up, ma_down = ema(up, window), ema(down, window)
        rs = ma_up/ma_down.replace(0,np.nan)
        return 100 - 100/(1+rs)

    # ── signal
    def signal(self) -> tuple[str | None, float, list[str], dict[str,Decimal]]:
        score = 0.0
        reasons=[]
        weights = self._weights()

        # EMA alignment
        ea = self.ema_alignment_score()
        if self.cfg["indicators"]["ema_alignment"] and ea!=0:
            score += weights["ema_alignment"]*abs(ea)
            reasons.append("EMA Align "+("Bull" if ea>0 else "Bear"))

        # Volume
        if self.cfg["indicators"]["volume_confirmation"] and self.volume_confirm():
            score += weights["volume_confirmation"]
            reasons.append("Volume spike")

        # Stoch RSI
        if self.cfg["indicators"]["stoch_rsi"]:
            k,d = self.stoch_rsi()
            oversold = k<self.cfg["stoch_rsi_oversold_threshold"] and k>d
            overbought = k>self.cfg["stoch_rsi_overbought_threshold"] and k<d
            if oversold:
                score += weights["stoch_rsi"]; reasons.append("StochRSI oversold")
            if overbought:
                score -= weights["stoch_rsi"]; reasons.append("StochRSI overbought")

        # RSI / MFI basic
        if self.cfg["indicators"]["rsi"]:
            r = self._rsi(self.cfg["indicator_periods"]["rsi"]).iloc[-1]
            if r<30: score += weights["rsi"]; reasons.append("RSI oversold")
            elif r>70: score -= weights["rsi"]; reasons.append("RSI overbought")
        if self.cfg["indicators"]["mfi"] and "mfi" in self.ind:
            m = self.ind["mfi"].iloc[-1]
            if m<20: score += weights["mfi"]; reasons.append("MFI oversold")
            elif m>80: score -= weights["mfi"]; reasons.append("MFI overbought")

        # decision
        if abs(score) < self.cfg["signal_score_threshold"]:
            return None, 0.0, [], {}

        side = "buy" if score>0 else "sell"
        price = Decimal(str(self.df["close"].iloc[-1]))
        last_atr = Decimal(str(self.ind["atr"].iloc[-1] or 0))
        tp = price + last_atr*self.cfg["take_profit_multiple"] * (1 if side=="buy" else -1)
        sl = price - last_atr*self.cfg["stop_loss_multiple"] * (1 if side=="buy" else -1)
        levels={"take_profit":tp.quantize(Decimal('0.0001')),
                "stop_loss":sl.quantize(Decimal('0.0001'))}
        return side, score, reasons, levels

    def _weights(self) -> dict[str,float]:
        vol=self.ind["atr"].iloc[-1]
        set_name = "high_volatility" if vol>self.cfg["atr_change_threshold"] else "low_volatility"
        return self.cfg["weight_sets"][set_name]

# ───────────────────────────── main loop ────────────────────────────
def main():
    if not API_KEY or not API_SECRET:
        logger.error(f"{C['R']}API creds missing .env{C['X']}")
        return
    cfg = ConfigManager(CONFIG_FILE).cfg
    api = BybitAPI(API_KEY, API_SECRET, BASE_URL, logger)

    symbol   = (input("Symbol (BTCUSDT): ") or "BTCUSDT").upper()
    interval = input(f"Interval ({cfg['interval']}): ") or cfg["interval"]
    if interval not in VALID_INTERVALS:
        logger.error(f"{C['R']}Bad interval{C['X']}"); return
    slog = setup_custom_logger(symbol)

    last_sig_t = 0.0
    last_ob_t  = 0.0
    order_book = None

    while True:
        try:
            price = api.price(symbol)
            if price is None:
                slog.error("Price fetch fail"); time.sleep(cfg["retry_delay"]); continue
            df = api.klines(symbol, interval, 200)
=======
        self.log.info(f"{NEON_BLUE}Fetching fresh Kline data for {symbol} ({interval})...{RESET}")
        endpoint = "/v5/market/kline"
        params = {"symbol": symbol, "interval": interval, "limit": limit, "category": "linear"}
        response_data = self._bybit_request("GET", endpoint, params)

        if response_data and response_data.get("retCode") == 0 and response_data.get("result") and response_data["result"].get("list"):
            data = response_data["result"]["list"]
            # Bybit kline order: [timestamp, open, high, low, close, volume, turnover]
            columns = ["start_time", "open", "high", "low", "close", "volume", "turnover"]
            df = pd.DataFrame(data, columns=columns)
            
            # Convert timestamp to datetime (coercing errors means invalid times become NaT)
            df["start_time"] = pd.to_datetime(pd.to_numeric(df["start_time"], errors='coerce'), unit="ms")
            
            # Convert financial columns to Decimal safely
            for col in ["open", "high", "low", "close", "volume", "turnover"]:
                # Using apply with _to_decimal ensures Decimal objects for each element
                df[col] = df[col].apply(lambda x: Decimal(str(x)) if pd.notna(x) else Decimal('NaN'))
            
            # Drop rows with any NaN values in critical columns
            df.dropna(subset=df.columns[1:], inplace=True)
            
            # Ensure ascending order by time
            df = df.sort_values(by="start_time", ascending=True).reset_index(drop=True)
            
>>>>>>> 1917b20 (WIP)
            if df.empty:
                self.log.warning(f"{NEON_YELLOW}Fetched Kline data is empty after processing for {symbol}, interval {interval}.{RESET}")
                return pd.DataFrame()
            
            # Cache the processed DataFrame
            self.kline_cache[kline_key] = {'data': df, 'timestamp': time.time()}
            return df
            
        self.log.error(f"{NEON_RED}Failed to fetch Kline data for {symbol}, interval {interval}. Response: {response_data}{RESET}")
        return pd.DataFrame()

    @retry_api_call()
    def fetch_order_book(self, symbol: str, limit: int = 50) -> Optional[dict]:
        """Fetches the order book for a given symbol."""
        endpoint = "/v5/market/orderbook"
        params = {"symbol": symbol, "limit": limit, "category": "linear"}
        response_data = self._bybit_request("GET", endpoint, params)
        if response_data and response_data.get("retCode") == 0 and response_data.get("result"):
            return response_data["result"]
        self.log.warning(f"{NEON_YELLOW}Could not fetch order book for {symbol}. Response: {response_data}{RESET}")
        return None

# ----------------------------------------------------------------------------
# 5. TECHNICAL INDICATORS ENGINE (ALL METHODS ARE DECIMAL-AWARE)
# ----------------------------------------------------------------------------
class Indicators:
    """A collection of static methods for calculating technical indicators.
       Prioritizes TA-Lib for performance if available, else uses Pandas/Numpy with Decimal."""

    @staticmethod
    def _to_decimal_series_safe(series: pd.Series) -> pd.Series:
        """Helper to convert series to Decimal type safely, handling NaN/None."""
        return series.apply(lambda x: Decimal(str(x)) if pd.notna(x) else Decimal('NaN'))

    @staticmethod
    def _convert_series_to_float_np(series: pd.Series) -> np.ndarray:
        """Converts a Decimal Series to float numpy array for TA-Lib, handling NaNs."""
        # Check if the series *actually* contains Decimal objects before casting
        # If it's already numeric (e.g., float64) or mixed, just convert directly
        return series.apply(lambda x: float(x) if isinstance(x, Decimal) and not x.is_nan() else np.nan).to_numpy(dtype=float)

    @staticmethod
    def sma(series: pd.Series, window: int) -> pd.Series:
        """Decimal-safe Simple Moving Average."""
        if TALIB_AVAILABLE:
            np_array = Indicators._convert_series_to_float_np(series)
            result = talib.SMA(np_array, timeperiod=window)
            return Indicators._to_decimal_series_safe(pd.Series(result, index=series.index))
        
        return Indicators._to_decimal_series_safe(series.rolling(window=window, min_periods=1).mean())
    
    @staticmethod
    def ema(series: pd.Series, span: int) -> pd.Series:
        """Decimal-safe Exponential Moving Average."""
        if TALIB_AVAILABLE:
            np_array = Indicators._convert_series_to_float_np(series)
            result = talib.EMA(np_array, timeperiod=span)
            return Indicators._to_decimal_series_safe(pd.Series(result, index=series.index))
            
        return Indicators._to_decimal_series_safe(series.ewm(span=span, adjust=False).mean())
    
    @staticmethod
    def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int) -> pd.Series:
        """Decimal-safe Average True Range."""
        if TALIB_AVAILABLE:
            np_high = Indicators._convert_series_to_float_np(high)
            np_low = Indicators._convert_series_to_float_np(low)
            np_close = Indicators._convert_series_to_float_np(close)
            result = talib.ATR(np_high, np_low, np_close, timeperiod=window)
            return Indicators._to_decimal_series_safe(pd.Series(result, index=high.index))

        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return Indicators.ema(Indicators._to_decimal_series_safe(tr), span=window)
    
    @staticmethod
    def rsi(close: pd.Series, window: int) -> pd.Series:
        """Decimal-safe Relative Strength Index."""
        if TALIB_AVAILABLE:
            np_close = Indicators._convert_series_to_float_np(close)
            result = talib.RSI(np_close, timeperiod=window)
            return Indicators._to_decimal_series_safe(pd.Series(result, index=close.index))

        delta = close.diff()
        gain = delta.where(delta > Decimal('0'), Decimal('0')).fillna(Decimal('0'))
        loss = -delta.where(delta < Decimal('0'), Decimal('0')).fillna(Decimal('0'))
        avg_gain = Indicators.ema(gain, span=window)
        avg_loss = Indicators.ema(loss, span=window)
        rs = avg_gain / avg_loss.replace(Decimal('0'), Decimal('NaN'))
        return (Decimal('100') - (Decimal('100') / (Decimal('1') + rs))).fillna(Decimal('50'))
    
    @staticmethod
    def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
        """Decimal-safe Moving Average Convergence Divergence."""
        if TALIB_AVAILABLE:
            np_close = Indicators._convert_series_to_float_np(close)
            macd_line, signal_line, hist = talib.MACD(np_close, fastperiod=fast, slowperiod=slow, signalperiod=signal)
            return pd.DataFrame({
                "macd": Indicators._to_decimal_series_safe(pd.Series(macd_line, index=close.index)),
                "signal": Indicators._to_decimal_series_safe(pd.Series(signal_line, index=close.index)),
                "histogram": Indicators._to_decimal_series_safe(pd.Series(hist, index=close.index))
            })

        ema_fast = Indicators.ema(close, span=fast)
        ema_slow = Indicators.ema(close, span=slow)
        macd_line = ema_fast - ema_slow
        signal_line = Indicators.ema(macd_line, span=signal)
        histogram = macd_line - signal_line
        return pd.DataFrame({"macd": macd_line, "signal": signal_line, "histogram": histogram})
    
    @staticmethod
    def adx(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.DataFrame:
        """Decimal-safe Average Directional Index."""
        if TALIB_AVAILABLE:
            np_high = Indicators._convert_series_to_float_np(high)
            np_low = Indicators._convert_series_to_float_np(low)
            np_close = Indicators._convert_series_to_float_np(close)
            plus_di, minus_di, adx = talib.ADX(np_high, np_low, np_close, timeperiod=window)
            return pd.DataFrame({
                "+DI": Indicators._to_decimal_series_safe(pd.Series(plus_di, index=high.index)),
                "-DI": Indicators._to_decimal_series_safe(pd.Series(minus_di, index=high.index)),
                "ADX": Indicators._to_decimal_series_safe(pd.Series(adx, index=high.index))
            })

        plus_dm = high.diff()
        minus_dm = low.diff().mul(Decimal('-1'))
        plus_dm_s = Indicators.ema(plus_dm.where((plus_dm > Decimal('0')) & (plus_dm > minus_dm), Decimal('0')), span=window)
        minus_dm_s = Indicators.ema(minus_dm.where((minus_dm > Decimal('0')) & (minus_dm > plus_dm), Decimal('0')), span=window)
        tr_s = Indicators.ema(Indicators.atr(high, low, close, window), span=window)
        plus_di = Decimal('100') * (plus_dm_s / tr_s.replace(Decimal('0'), Decimal('NaN'))).fillna(Decimal('0'))
        minus_di = Decimal('100') * (minus_dm_s / tr_s.replace(Decimal('0'), Decimal('NaN'))).fillna(Decimal('0'))
        dx_denom = (plus_di + minus_di).replace(Decimal('0'), Decimal('NaN'))
        dx = Decimal('100') * (abs(plus_di - minus_di) / dx_denom).fillna(Decimal('0'))
        adx_series = Indicators.ema(dx, span=window)
        return pd.DataFrame({"+DI": plus_di, "-DI": minus_di, "ADX": adx_series})
    
    @staticmethod
    def stochastic_oscillator(close: pd.Series, high: pd.Series, low: pd.Series, k_period: int = 14, d_period: int = 3) -> pd.DataFrame:
        """Decimal-safe Stochastic Oscillator."""
        if TALIB_AVAILABLE:
            np_high = Indicators._convert_series_to_float_np(high)
            np_low = Indicators._convert_series_to_float_np(low)
            np_close = Indicators._convert_series_to_float_np(close)
            slowk, slowd = talib.STOCH(np_high, np_low, np_close,
                                     fastk_period=k_period,
                                     slowk_period=d_period, # In TA-Lib, 'slowk_period' is our K, 'slowd_period' is our D
                                     slowd_period=d_period)
            return pd.DataFrame({
                "k": Indicators._to_decimal_series_safe(pd.Series(slowk, index=close.index)),
                "d": Indicators._to_decimal_series_safe(pd.Series(slowd, index=close.index))
            })

        highest_high = high.rolling(window=k_period).max()
        lowest_low = low.rolling(window=k_period).min()
        denominator = (highest_high - lowest_low).replace(Decimal('0'), Decimal('NaN'))
        k_line = ((close - lowest_low) / denominator * Decimal('100')).fillna(Decimal('0'))
        d_line = Indicators.sma(k_line, window=d_period)
        return pd.DataFrame({"k": k_line, "d": d_line})
    
    @staticmethod
    def stoch_rsi(close: pd.Series, rsi_period: int = 14, k_period: int = 3, d_period: int = 3) -> pd.DataFrame:
        """Decimal-safe Stochastic RSI."""
        if TALIB_AVAILABLE:
            # TA-Lib STOCHRSI returns fastk, fastd based on RSI values.
            # We map fastk to stoch_rsi_k and fastd to stoch_rsi_d
            np_close = Indicators._convert_series_to_float_np(close)
            stochrsi_k, stochrsi_d = talib.STOCHRSI(np_close,
                                                    timeperiod=rsi_period,
                                                    fastk_period=k_period,
                                                    fastd_period=d_period,
                                                    _talib_input_type="float") # Force float input for TA-Lib
            return pd.DataFrame({
                "stoch_rsi_k": Indicators._to_decimal_series_safe(pd.Series(stochrsi_k, index=close.index)),
                "stoch_rsi_d": Indicators._to_decimal_series_safe(pd.Series(stochrsi_d, index=close.index))
            })

        rsi_vals = Indicators.rsi(close, window=rsi_period)
        min_rsi = rsi_vals.rolling(window=k_period).min()
        max_rsi = rsi_vals.rolling(window=k_period).max()
        denominator = (max_rsi - min_rsi).replace(Decimal('0'), Decimal('NaN'))
        stoch_rsi_val = ((rsi_vals - min_rsi) / denominator * Decimal('100')).fillna(Decimal('0'))
        k_line = Indicators.sma(stoch_rsi_val, window=k_period)
        d_line = Indicators.sma(k_line, window=d_period)
        return pd.DataFrame({"stoch_rsi_k": k_line, "stoch_rsi_d": d_line})
    
    @staticmethod
    def psar(high: pd.Series, low: pd.Series, close: pd.Series, acceleration: Decimal = Decimal('0.02'), max_acceleration: Decimal = Decimal('0.2')) -> pd.Series:
        """Decimal-safe Parabolic SAR."""
        if TALIB_AVAILABLE:
            np_high = Indicators._convert_series_to_float_np(high)
            np_low = Indicators._convert_series_to_float_np(low)
            np_close = Indicators._convert_series_to_float_np(close)
            result = talib.SAR(np_high, np_low, 
                               acceleration=float(acceleration),
                               maximum=float(max_acceleration))
            return Indicators._to_decimal_series_safe(pd.Series(result, index=high.index))

        psar = pd.Series([Decimal('NaN')] * len(close), index=close.index, dtype=object)
        if len(close) < 2: return psar
        
        # Ensure input series are Decimal
        high, low, close = Indicators._to_decimal_series_safe(high), Indicators._to_decimal_series_safe(low), Indicators._to_decimal_series_safe(close)

        psar.iloc[0] = close.iloc[0] # Initial PSAR at first close
        
        # Determine initial trend (up=1, down=-1) and EP (extreme point)
        trend = 1 if close.iloc[1] > close.iloc[0] else -1
        ep = high.iloc[0] if trend == 1 else low.iloc[0]
        af = acceleration # Acceleration Factor
        
        for i in range(1, len(close)):
            prev_psar = psar.iloc[i - 1]
            if pd.isna(prev_psar): # Skip if previous was NaN
                psar.iloc[i] = close.iloc[i]
                continue
            
            curr_h, curr_l = high.iloc[i], low.iloc[i]

            if trend == 1: # Uptrend
                new_psar = prev_psar + af * (ep - prev_psar)
                # SAR should not be above current or previous two lows in an uptrend
                psar.iloc[i] = min(new_psar, curr_l, low.iloc[i-1] if i > 1 else curr_l) # Ensure SAR stays below price
                if curr_h > ep: # New extreme point reached
                    ep, af = curr_h, min(af + acceleration, max_acceleration)
                if curr_l < psar.iloc[i]: # Trend reversal: price falls below SAR
                    trend, psar.iloc[i], ep, af = -1, ep, curr_l, acceleration # SAR moves to previous EP, EP becomes new low, reset AF
            else: # Downtrend
                new_psar = prev_psar + af * (ep - prev_psar)
                # SAR should not be below current or previous two highs in a downtrend
                psar.iloc[i] = max(new_psar, curr_h, high.iloc[i-1] if i > 1 else curr_h) # Ensure SAR stays above price
                if curr_l < ep: # New extreme point reached
                    ep, af = curr_l, min(af + acceleration, max_acceleration)
                if curr_h > psar.iloc[i]: # Trend reversal: price rises above SAR
                    trend, psar.iloc[i], ep, af = 1, ep, curr_h, acceleration # SAR moves to previous EP, EP becomes new high, reset AF
        
        return psar.ffill() # Fill any initial NaNs if calculation started later in series
    
    @staticmethod
    def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
        """Decimal-safe On-Balance Volume."""
        if TALIB_AVAILABLE:
            np_close = Indicators._convert_series_to_float_np(close)
            np_volume = Indicators._convert_series_to_float_np(volume)
            result = talib.OBV(np_close, np_volume)
            return Indicators._to_decimal_series_safe(pd.Series(result, index=close.index))

        obv = pd.Series([Decimal('0')] * len(close), index=close.index, dtype=object)
        if not close.empty: # Handle empty series case
            obv.iloc[0] = volume.iloc[0] if not pd.isna(volume.iloc[0]) else Decimal('0')
            for i in range(1, len(close)):
                if pd.isna(close.iloc[i]) or pd.isna(close.iloc[i-1]) or pd.isna(volume.iloc[i]):
                    obv.iloc[i] = obv.iloc[i-1] # Maintain previous OBV on missing data
                elif close.iloc[i] > close.iloc[i-1]: obv.iloc[i] = obv.iloc[i-1] + volume.iloc[i]
                elif close.iloc[i] < close.iloc[i-1]: obv.iloc[i] = obv.iloc[i-1] - volume.iloc[i]
                else: obv.iloc[i] = obv.iloc[i-1]
        return obv
    
    @staticmethod
    def adi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
        """Decimal-safe Accumulation/Distribution Index."""
        if TALIB_AVAILABLE:
            np_high = Indicators._convert_series_to_float_np(high)
            np_low = Indicators._convert_series_to_float_np(low)
            np_close = Indicators._convert_series_to_float_np(close)
            np_volume = Indicators._convert_series_to_float_np(volume)
            result = talib.AD(np_high, np_low, np_close, np_volume)
            return Indicators._to_decimal_series_safe(pd.Series(result, index=high.index))

        mfm_denom = (high - low).replace(Decimal('0'), Decimal('NaN'))
        mfm = (((close - low) - (high - close)) / mfm_denom).fillna(Decimal('0'))
        mfv = mfm * volume
        return mfv.cumsum()
    
    @staticmethod
    def cci(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 20, constant: Decimal = Decimal('0.015')) -> pd.Series:
        """Decimal-safe Commodity Channel Index."""
        if TALIB_AVAILABLE:
            np_high = Indicators._convert_series_to_float_np(high)
            np_low = Indicators._convert_series_to_float_np(low)
            np_close = Indicators._convert_series_to_float_np(close)
            result = talib.CCI(np_high, np_low, np_close, timeperiod=window)
            return Indicators._to_decimal_series_safe(pd.Series(result, index=high.index))

        typical_price = (high + low + close) / Decimal('3')
        sma_tp = Indicators.sma(typical_price, window=window)
        
        def _mean_dev_decimal(x_series: pd.Series) -> Decimal:
            """Calculate mean deviation for a Decimal Series."""
            x_dec = [val for val in x_series if pd.notna(val) and isinstance(val, Decimal)]
            if not x_dec:
                return Decimal('NaN')
            mean_val = sum(x_dec) / Decimal(str(len(x_dec)))
            return sum(abs(val - mean_val) for val in x_dec) / Decimal(str(len(x_dec)))
        
        mean_dev_series = typical_price.rolling(window=window).apply(_mean_dev_decimal, raw=False) # raw=False to pass Series objects
        
        return ((typical_price - sma_tp) / (constant * mean_dev_series.replace(Decimal('0'), Decimal('NaN')))).fillna(Decimal('0'))
    
    @staticmethod
    def williams_r(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
        """Decimal-safe Williams %R."""
        if TALIB_AVAILABLE:
            np_high = Indicators._convert_series_to_float_np(high)
            np_low = Indicators._convert_series_to_float_np(low)
            np_close = Indicators._convert_series_to_float_np(close)
            result = talib.WILLR(np_high, np_low, np_close, timeperiod=window)
            return Indicators._to_decimal_series_safe(pd.Series(result, index=high.index))

        highest_high = high.rolling(window=window).max()
        lowest_low = low.rolling(window=window).min()
        denom = (highest_high - lowest_low).replace(Decimal('0'), Decimal('NaN'))
        return (((highest_high - close) / denom) * Decimal('-100')).fillna(Decimal('0'))
    
    @staticmethod
    def mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, window: int = 14) -> pd.Series:
        """Decimal-safe Money Flow Index."""
        if TALIB_AVAILABLE:
            np_high = Indicators._convert_series_to_float_np(high)
            np_low = Indicators._convert_series_to_float_np(low)
            np_close = Indicators._convert_series_to_float_np(close)
            np_volume = Indicators._convert_series_to_float_np(volume)
            result = talib.MFI(np_high, np_low, np_close, np_volume, timeperiod=window)
            return Indicators._to_decimal_series_safe(pd.Series(result, index=high.index))

        typical_price = (high + low + close) / Decimal('3')
        raw_mf = typical_price * volume
        mf_dir = typical_price.diff()
        pos_mf = raw_mf.where(mf_dir > Decimal('0'), Decimal('0'))
        neg_mf = raw_mf.where(mf_dir < Decimal('0'), Decimal('0'))
        pos_sum = pos_mf.rolling(window=window, min_periods=1).sum().apply(lambda x: Decimal(str(x)))
        neg_sum = neg_mf.rolling(window=window, min_periods=1).sum().apply(lambda x: Decimal(str(x)))
        mf_ratio = pos_sum / neg_sum.replace(Decimal('0'), Decimal('NaN'))
        return (Decimal('100') - (Decimal('100') / (Decimal('1') + mf_ratio))).fillna(Decimal('0'))
    
    @staticmethod
    def momentum(close: pd.Series, period: int = 10) -> pd.Series:
        """Decimal-safe Momentum."""
        if TALIB_AVAILABLE:
            np_close = Indicators._convert_series_to_float_np(close)
            result = talib.MOM(np_close, timeperiod=period)
            return Indicators._to_decimal_series_safe(pd.Series(result, index=close.index))

        return ((close.diff(period) / close.shift(period)) * Decimal('100')).fillna(Decimal('0'))
    
    @staticmethod
    def vwap(close: pd.Series, volume: pd.Series, window: int) -> pd.Series:
        """Decimal-safe Volume Weighted Average Price."""
        if window <= 0: return close # VWAP is typically cumulative or session-based, not windowed in strict sense. Here, window behaves like a rolling average.
        price_vol = close * volume
        cum_pv = price_vol.rolling(window=window, min_periods=1).sum().apply(lambda x: Decimal(str(x)))
        cum_vol = volume.rolling(window=window, min_periods=1).sum().apply(lambda x: Decimal(str(x)))
        return (cum_pv / cum_vol.replace(Decimal('0'), Decimal('NaN'))).fillna(close)
    
    @staticmethod
    def cmf(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, window: int = 20) -> pd.Series:
        """Decimal-safe Chaikin Money Flow (CMF)."""
        mfm_denom = (high - low).replace(Decimal('0'), Decimal('NaN'))
        mfm = (((close - low) - (high - close)) / mfm_denom).fillna(Decimal('0'))
        mfv = mfm * volume
        return (mfv.rolling(window=window).sum() / volume.rolling(window=window).sum().replace(Decimal('0'), Decimal('NaN'))).fillna(Decimal('0'))
    
    @staticmethod
    def ao(close: pd.Series, short_period: int = 5, long_period: int = 34) -> pd.Series:
        """Decimal-safe Awesome Oscillator (AO)."""
        # AO is based on 5-period SMA of (H+L)/2 minus 34-period SMA of (H+L)/2
        # The input close is typically the median price (high+low)/2, but if only close is given, use it.
        # Original script uses (close + close.shift(1)) / 2, which is not standard.
        # Let's use (high+low)/2 for a more standard AO calculation if possible, else stick to close.
        # For compatibility, keeping median_price as (close + close.shift(1)) / 2 based on your prior code structure.
        median_price = (close + close.shift(1)).fillna(close) / Decimal('2') # Use close if shift(1) is NaN
        sma_short = Indicators.sma(median_price, window=short_period)
        sma_long = Indicators.sma(median_price, window=long_period)
        return sma_short - sma_long
    
    @staticmethod
    def vi(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.DataFrame:
        """Decimal-safe Vortex Indicator (VI)."""
        if TALIB_AVAILABLE:
            np_high = Indicators._convert_series_to_float_np(high)
            np_low = Indicators._convert_series_to_float_np(low)
            np_close = Indicators._convert_series_to_float_np(close)
            plus_vi, minus_vi = talib.VORTEX(np_high, np_low, np_close, timeperiod=window)
            return pd.DataFrame({
                "+VI": Indicators._to_decimal_series_safe(pd.Series(plus_vi, index=high.index)),
                "-VI": Indicators._to_decimal_series_safe(pd.Series(minus_vi, index=high.index))
            })

        tr = Indicators.atr(high, low, close, 1).rolling(window=window).sum()
        # +VM = |Current High - Previous Low|
        plus_vm = (high - low.shift(1)).abs()
        # -VM = |Current Low - Previous High|
        minus_vm = (low - high.shift(1)).abs()

        plus_vi = (plus_vm.rolling(window=window, min_periods=1).sum() / tr).fillna(Decimal('0'))
        minus_vi = (minus_vm.rolling(window=window, min_periods=1).sum() / tr).fillna(Decimal('0'))

        return pd.DataFrame({"+VI": plus_vi, "-VI": minus_vi})
    
    @staticmethod
    def bb(close: pd.Series, window: int = 20, std_dev_mult: Decimal = Decimal('2')) -> pd.DataFrame:
        """Decimal-safe Bollinger Bands (BB)."""
        if TALIB_AVAILABLE:
            np_close = Indicators._convert_series_to_float_np(close)
            upper, middle, lower = talib.BBANDS(np_close,
                                                 timeperiod=window,
                                                 nbdevup=float(std_dev_mult),
                                                 nbdevdn=float(std_dev_mult),
                                                 matype=talib.MA_Type.SMA) # Using SMA for middle band by default
            return pd.DataFrame({
                "upper": Indicators._to_decimal_series_safe(pd.Series(upper, index=close.index)),
                "middle": Indicators._to_decimal_series_safe(pd.Series(middle, index=close.index)),
                "lower": Indicators._to_decimal_series_safe(pd.Series(lower, index=close.index))
            })

        sma = Indicators.sma(close, window=window)
        # Calculate standard deviation manually for Decimal Series
        # Use pandas std() and then convert to Decimal for safety
        rolling_std = close.rolling(window=window).std().apply(lambda x: Decimal(str(x)) if pd.notna(x) else Decimal('NaN'))
        
        upper = sma + (rolling_std * std_dev_mult)
        lower = sma - (rolling_std * std_dev_mult)
        return pd.DataFrame({"upper": upper, "middle": sma, "lower": lower})
    
    @staticmethod
    def fve(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, window: int = 10) -> pd.Series:
        """A composite indicator based on price and volume relationship."""
        if len(close) < window: return pd.Series([Decimal('NaN')] * len(close))
        price_ema = Indicators.ema(close, window)
        vol_sma = Indicators.sma(volume, window)
        # Using element-wise multiplication here
        fve_values = (price_ema * vol_sma).rolling(window=window, min_periods=1).sum() # Removed .apply(lambda x: Decimal(str(x))) as rolling().sum() on Decimal Series should maintain Decimal
        return fve_values.apply(lambda x: Decimal(str(x)) if pd.notna(x) else Decimal('NaN')) # Keep apply for final NaN check

    # --- New Indicators ---

    @staticmethod
    def keltner_channels(high: pd.Series, low: pd.Series, close: pd.Series, window: int, atr_period: int, multiplier: Decimal) -> pd.DataFrame:
        """Decimal-safe Keltner Channels."""
        # TA-Lib does not have a direct Keltner Channels function.
        # We implement it by combining EMA and ATR.

        middle_band = Indicators.ema(close, span=window)
        atr_val = Indicators.atr(high, low, close, atr_period)
        
        upper_band = middle_band + (atr_val * multiplier)
        lower_band = middle_band - (atr_val * multiplier)
        
        return pd.DataFrame({
            "upper": Indicators._to_decimal_series_safe(upper_band),
            "middle": Indicators._to_decimal_series_safe(middle_band),
            "lower": Indicators._to_decimal_series_safe(lower_band)
        })

    @staticmethod
    def ichimoku(high: pd.Series, low: pd.Series, close: pd.Series,
                 tenkan_period: int = 9, kijun_period: int = 26, senkou_period: int = 52,
                 chikou_shift: int = 26) -> pd.DataFrame:
        """Decimal-safe Ichimoku Cloud components."""
        
        # Tenkan-sen (Conversion Line): (9-period high + 9-period low) / 2
        tenkan_sen = (high.rolling(window=tenkan_period).max() + low.rolling(window=tenkan_period).min()) / Decimal('2')
        
        # Kijun-sen (Base Line): (26-period high + 26-period low) / 2
        kijun_sen = (high.rolling(window=kijun_period).max() + low.rolling(window=kijun_period).min()) / Decimal('2')
        
        # Senkou Span A (Leading Span A): (Conversion Line + Base Line) / 2, plotted 26 periods ahead
        senkou_span_a = ((tenkan_sen + kijun_sen) / Decimal('2')).shift(kijun_period)
        
        # Senkou Span B (Leading Span B): (52-period high + 52-period low) / 2, plotted 26 periods ahead
        senkou_span_b = ((high.rolling(window=senkou_period).max() + low.rolling(window=senkou_period).min()) / Decimal('2')).shift(kijun_period)
        
        # Chikou Span (Lagging Span): Current closing price, plotted 26 periods behind
        chikou_span = close.shift(-chikou_shift) # Shift backwards means earlier data
        
        return pd.DataFrame({
            "tenkan_sen": Indicators._to_decimal_series_safe(tenkan_sen),
            "kijun_sen": Indicators._to_decimal_series_safe(kijun_sen),
            "senkou_span_a": Indicators._to_decimal_series_safe(senkou_span_a),
            "senkou_span_b": Indicators._to_decimal_series_safe(senkou_span_b),
            "chikou_span": Indicators._to_decimal_series_safe(chikou_span),
        })

    @staticmethod
    def supertrend(high: pd.Series, low: pd.Series, close: pd.Series, atr_period: int, multiplier: Decimal) -> pd.Series:
        """Decimal-safe Supertrend Indicator."""
        # Adapted from typical Supertrend implementation
        
        # Calculate ATR
        atr_series = Indicators.atr(high, low, close, atr_period)
        
        # Calculate Basic Upper Band and Basic Lower Band
        basic_upper_band = ((high + low) / Decimal('2')) + (multiplier * atr_series)
        basic_lower_band = ((high + low) / Decimal('2')) - (multiplier * atr_series)
        
        # Calculate Final Upper Band and Final Lower Band
        final_upper_band = pd.Series([Decimal('NaN')] * len(close), index=close.index, dtype=object)
        final_lower_band = pd.Series([Decimal('NaN')] * len(close), index=close.index, dtype=object)
        
        supertrend_vals = pd.Series([Decimal('NaN')] * len(close), index=close.index, dtype=object)
        
        # Initialize trend
        trend = pd.Series([0] * len(close), index=close.index, dtype=int) # 1 for uptrend, -1 for downtrend, 0 for initial
        
        # Initialize first values if enough data
        if len(close) > 0:
            final_upper_band.iloc[0] = basic_upper_band.iloc[0] if not basic_upper_band.empty and not pd.isna(basic_upper_band.iloc[0]) else Decimal('NaN')
            final_lower_band.iloc[0] = basic_lower_band.iloc[0] if not basic_lower_band.empty and not pd.isna(basic_lower_band.iloc[0]) else Decimal('NaN')
            
            # Decide initial supertrend value and trend direction
            if not final_upper_band.iloc[0].is_nan() and not final_lower_band.iloc[0].is_nan() and not close.iloc[0].is_nan():
                if close.iloc[0] <= final_upper_band.iloc[0]:
                    supertrend_vals.iloc[0] = final_upper_band.iloc[0]
                    trend.iloc[0] = -1 # Initial downtrend
                else:
                    supertrend_vals.iloc[0] = final_lower_band.iloc[0]
                    trend.iloc[0] = 1 # Initial uptrend


        for i in range(1, len(close)):
            if pd.isna(basic_upper_band.iloc[i]) or pd.isna(basic_lower_band.iloc[i]) or \
               pd.isna(final_upper_band.iloc[i-1]) or pd.isna(final_lower_band.iloc[i-1]) or \
               pd.isna(close.iloc[i-1]) or pd.isna(close.iloc[i]):
                # Inherit from previous if current bands or previous final bands/close are NaN
                final_upper_band.iloc[i] = final_upper_band.iloc[i-1]
                final_lower_band.iloc[i] = final_lower_band.iloc[i-1]
                trend.iloc[i] = trend.iloc[i-1]
                supertrend_vals.iloc[i] = supertrend_vals.iloc[i-1]
                continue
            
            # Update final bands
            # If previous close was above previous final upper band, then current final upper band is basic_upper_band
            if close.iloc[i-1] > final_upper_band.iloc[i-1]:
                final_upper_band.iloc[i] = basic_upper_band.iloc[i]
            else:
                final_upper_band.iloc[i] = min(basic_upper_band.iloc[i], final_upper_band.iloc[i-1])

            # If previous close was below previous final lower band, then current final lower band is basic_lower_band
            if close.iloc[i-1] < final_lower_band.iloc[i-1]:
                final_lower_band.iloc[i] = basic_lower_band.iloc[i]
            else:
                final_lower_band.iloc[i] = max(basic_lower_band.iloc[i], final_lower_band.iloc[i-1])
            
            # Determine trend and Supertrend value
            if trend.iloc[i-1] == 1: # Was in uptrend
                if close.iloc[i] < final_lower_band.iloc[i]: # Price broke below final_lower_band -> downtrend
                    trend.iloc[i] = -1
                else: # Price stayed above final_lower_band -> uptrend continues
                    trend.iloc[i] = 1
            else: # Was in downtrend
                if close.iloc[i] > final_upper_band.iloc[i]: # Price broke above final_upper_band -> uptrend
                    trend.iloc[i] = 1
                else: # Price stayed below final_upper_band -> downtrend continues
                    trend.iloc[i] = -1
            
            # Set Supertrend value based on current trend
            if trend.iloc[i] == 1: # Uptrend
                supertrend_vals.iloc[i] = final_lower_band.iloc[i]
            else: # Downtrend
                supertrend_vals.iloc[i] = final_upper_band.iloc[i]
        
        return Indicators._to_decimal_series_safe(supertrend_vals.ffill())


# ----------------------------------------------------------------------------
# 6. DATA STRUCTURES & CORE TRADING ANALYZER
# ----------------------------------------------------------------------------
@dataclass(slots=True)
class TradeSignal:
    """Structured object for a trading signal."""
    signal: Optional[str] # "buy" or "sell"
    confidence: float    # 0.0 to 1.0
    conditions: List[str] = field(default_factory=list) # List of contributing conditions
    levels: Dict[str, Decimal] = field(default_factory=dict) # Calculated SL/TP/other levels

class TradingAnalyzer:
    """Orchestrates technical analysis and signal generation."""
    def __init__(self, df: pd.DataFrame, cfg: BotConfig, log: logging.Logger, symbol: str, interval: str):
        self.df = df.copy()
        self.cfg = cfg
        self.log = log
        self.symbol = symbol
        self.interval = interval
        self.atr_value: Decimal = Decimal('0')
        self.indicator_values: Dict[str, Any] = {}
        self.levels: Dict[str, Any] = {"Support": {}, "Resistance": {}}
        self.fib_levels: Dict[str, Decimal] = {}
        
        self._pre_calculate_indicators() # Calculate ATR and other prerequisites
        self.market_condition = self._detect_market_condition() # Determine market condition
        self.weights = self._select_weight_set() # Select weights based on market condition

    def _pre_calculate_indicators(self):
        """Pre-calculates essential indicators like ATR needed for other logic."""
        atr_period = self.cfg['atr_period']
        if self.df.empty or len(self.df) < atr_period:
            self.log.warning(f"{NEON_YELLOW}Not enough data for ATR ({len(self.df)}/{atr_period} bars). ATR set to 0.{RESET}")
            self.atr_value = Decimal('0')
            return
        
        atr_series = Indicators.atr(self.df.high, self.df.low, self.df.close, atr_period)
        if not atr_series.empty and not pd.isna(atr_series.iloc[-1]):
            self.atr_value = atr_series.iloc[-1].quantize(Decimal('0.00001')) # Quantize for consistent logging/comparison
        else:
            self.atr_value = Decimal('0')
            self.log.warning(f"{NEON_YELLOW}ATR calculation resulted in NaN for {self.symbol}. ATR set to 0.{RESET}")
        self.indicator_values["atr"] = self.atr_value

    def _detect_market_condition(self) -> str:
        """Detects overall market condition (trending, ranging, volatile, calm)."""
        adx_period = self.cfg.get_nested("indicator_periods.adx", 14)
        bb_window = self.cfg.get_nested("indicator_periods.bb", 20)
        ema_long_period = self.cfg.get_nested("ema_long_period", 26)

        required_data = max(adx_period, bb_window, ema_long_period)
        if len(self.df) < required_data + 10: # Add a buffer for robust calculations
            self.log.warning(f"{NEON_YELLOW}Insufficient data to reliably detect market condition ({len(self.df)}/{required_data+10} bars). Defaulting to 'low_volatility'.{RESET}")
            return "low_volatility"

        # Calculate ADX
        adx_data = Indicators.adx(self.df.high, self.df.low, self.df.close, window=adx_period)
        adx_val = adx_data["ADX"].iloc[-1] if not adx_data.empty and not pd.isna(adx_data["ADX"].iloc[-1]) else Decimal('0')

        # Calculate Bollinger Bands
        bb_data = Indicators.bb(self.df.close, window=bb_window, std_dev_mult=Decimal(str(self.cfg.get_nested("indicator_periods.bb_std", 2))))
        bb_upper = bb_data["upper"].iloc[-1] if not bb_data.empty else Decimal('0')
        bb_lower = bb_data["lower"].iloc[-1] if not bb_data.empty else Decimal('0')
        bb_middle = bb_data["middle"].iloc[-1] if not bb_data.empty else Decimal('0')
        
        # Calculate Bollinger Bandwidth and Average Bandwidth for context
        bb_bandwidth = (bb_upper - bb_lower) / bb_middle if bb_middle != Decimal('0') else Decimal('0')
        
        # Recent ATR mean for volatility context
        atr_series = Indicators.atr(self.df.high, self.df.low, self.df.close, self.cfg["atr_period"])
        recent_atr_mean = atr_series.iloc[-min(10, len(atr_series)):].mean() if not atr_series.empty else Decimal('0')

        # Define thresholds from config
        adx_trend_threshold = Decimal(str(self.cfg.get_nested("market_condition_detection.adx_trend_threshold", 25)))
        atr_vol_multiplier = Decimal(str(self.cfg.get_nested("market_condition_detection.atr_volatility_threshold_multiplier", 1.5)))
        bb_range_multiplier = Decimal(str(self.cfg.get_nested("market_condition_detection.bb_bandwidth_threshold_multiplier", 0.8)))

        # Determine conditions
        is_trending_strong = adx_val > adx_trend_threshold
        is_volatile = self.atr_value > (recent_atr_mean * atr_vol_multiplier) if recent_atr_mean > 0 else False
        is_ranging = bb_bandwidth < (self.df['close'].iloc[-min(bb_window, len(self.df)):].std().apply(lambda x: Decimal(str(x)))) * bb_range_multiplier if len(self.df) >= bb_window else False
        
        # Trend direction using EMA
        ema_long = Indicators.ema(self.df.close, span=ema_long_period)
        is_uptrend, is_downtrend = False, False
        if len(ema_long) >= 5: # Need at least 5 periods to check slope
            is_uptrend = self.df.close.iloc[-1] > ema_long.iloc[-1] and ema_long.iloc[-1] > ema_long.iloc[-5] # Price above EMA and EMA sloping up
            is_downtrend = self.df.close.iloc[-1] < ema_long.iloc[-1] and ema_long.iloc[-1] < ema_long.iloc[-5] # Price below EMA and EMA sloping down

        condition = "low_volatility" # Default fallback (original low_volatility)

        if is_trending_strong:
            if is_uptrend:
                condition = "trending_up"
            elif is_downtrend:
                condition = "trending_down"
            else: # Strong ADX but no clear EMA direction indicates potential reversal or exhaustion
                condition = "volatile" # Or "ranging" if BB is narrow
                if is_ranging: condition = "ranging" # Prioritize ranging if true
        elif is_volatile:
            condition = "volatile"
        elif is_ranging:
            condition = "ranging"
        else: # Neither strongly trending nor ranging nor volatile, implies calm or consolidating
            condition = "calm"
        
        self.log.info(f