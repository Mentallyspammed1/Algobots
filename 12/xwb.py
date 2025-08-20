import os
import logging
import requests
import pandas as pd
import numpy as np
from datetime import datetime
import hmac
import hashlib
import time
from dotenv import load_dotenv
from typing import Dict, Tuple, List, Union, Any, Optional
from colorama import init, Fore, Style
from zoneinfo import ZoneInfo
from logger_config import setup_custom_logger
from decimal import Decimal, getcontext, InvalidOperation
import json
import sqlite3
from dataclasses import dataclass
from enum import Enum

# Set Decimal precision for financial calculations to avoid floating point errors
getcontext().prec = 10

# Initialize colorama for cross-platform colored terminal output
init(autoreset=True)

# Load environment variables from .env file
load_dotenv()

# --- Enums and Data Classes ---
class SignalType(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"

class MarketState(Enum):
    TRENDING = "trending"
    RANGING = "ranging"
    VOLATILE = "volatile"

@dataclass
class TradingSignal:
    signal_type: SignalType
    confidence: float
    conditions_met: List[str]
    stop_loss: Optional[Decimal]
    take_profit: Optional[Decimal]
    position_size: Optional[float]
    timestamp: datetime

@dataclass
class TradeState:
    entry_price: Decimal
    entry_time: datetime
    stop_loss: Decimal
    take_profit: Decimal
    highest_price: Decimal
    lowest_price: Decimal
    quantity: float
    is_active: bool

# --- Color Codex ---
NEON_GREEN = Fore.LIGHTGREEN_EX
NEON_BLUE = Fore.CYAN
NEON_PURPLE = Fore.MAGENTA
NEON_YELLOW = Fore.YELLOW
NEON_RED = Fore.LIGHTRED_EX
RESET = Style.RESET_ALL

# --- Configuration & Constants ---
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
BASE_URL = os.getenv("BYBIT_BASE_URL", "https://api.bybit.com")
CONFIG_FILE = "config.json"
LOG_DIRECTORY = "bot_logs"
DATABASE_PATH = "trading_bot.db"
TIMEZONE = ZoneInfo("America/Chicago")
MAX_API_RETRIES = 3
RETRY_DELAY_SECONDS = 5
VALID_INTERVALS = ["1", "3", "5", "15", "30", "60", "120", "240", "D", "W", "M"]
RETRY_ERROR_CODES = [429, 500, 502, 503, 504]

# Ensure log directory exists
os.makedirs(LOG_DIRECTORY, exist_ok=True)

# Setup the main application logger
logger = setup_custom_logger('whalebot_main')

def load_config(filepath: str) -> dict:
    """Loads configuration from a JSON file with enhanced validation."""
    default_config = {
        "interval": "15",
        "analysis_interval": 30,
        "retry_delay": 5,
        "momentum_period": 10,
        "momentum_ma_short": 12,
        "momentum_ma_long": 26,
        "volume_ma_period": 20,
        "atr_period": 14,
        "trend_strength_threshold": 0.4,
        "sideways_atr_multiplier": 1.5,
        "signal_score_threshold": 1.0,
        "indicators": {
            "ema_alignment": True,
            "momentum": True,
            "volume_confirmation": True,
            "divergence": True,
            "stoch_rsi": True,
            "rsi": True,
            "macd": True,
            "vwap": False,
            "obv": True,
            "adi": True,
            "cci": True,
            "wr": True,
            "adx": True,
            "psar": True,
            "fve": True,
            "sma_10": False,
            "mfi": True,
            "stochastic_oscillator": True,
        },
        "weight_sets": {
            "low_volatility": {
                "ema_alignment": 0.3,
                "momentum": 0.2,
                "volume_confirmation": 0.2,
                "divergence": 0.1,
                "stoch_rsi": 0.5,
                "rsi": 0.3,
                "macd": 0.3,
                "vwap": 0.0,
                "obv": 0.1,
                "adi": 0.1,
                "cci": 0.1,
                "wr": 0.1,
                "adx": 0.1,
                "psar": 0.1,
                "fve": 0.2,
                "sma_10": 0.0,
                "mfi": 0.3,
                "stochastic_oscillator": 0.4,
            },
            "high_volatility": {
                "ema_alignment": 0.1,
                "momentum": 0.4,
                "volume_confirmation": 0.1,
                "divergence": 0.2,
                "stoch_rsi": 0.4,
                "rsi": 0.4,
                "macd": 0.4,
                "vwap": 0.0,
                "obv": 0.1,
                "adi": 0.1,
                "cci": 0.1,
                "wr": 0.1,
                "adx": 0.1,
                "psar": 0.1,
                "fve": 0.3,
                "sma_10": 0.0,
                "mfi": 0.4,
                "stochastic_oscillator": 0.3,
            }
        },
        "stoch_rsi_oversold_threshold": 20,
        "stoch_rsi_overbought_threshold": 80,
        "stoch_rsi_confidence_boost": 5,
        "stoch_rsi_mandatory": False,
        "rsi_confidence_boost": 2,
        "mfi_confidence_boost": 2,
        "order_book_support_confidence_boost": 3,
        "order_book_resistance_confidence_boost": 3,
        "stop_loss_multiple": 1.5,
        "take_profit_multiple": 1.0,
        "order_book_wall_threshold_multiplier": 2.0,
        "order_book_depth_to_check": 10,
        "price_change_threshold": 0.005,
        "atr_change_threshold": 0.005,
        "signal_cooldown_s": 60,
        "order_book_debounce_s": 10,
        "ema_short_period": 12,
        "ema_long_period": 26,
        "volume_confirmation_multiplier": 1.5,
        "indicator_periods": {
            "rsi": 14,
            "mfi": 14,
            "cci": 20,
            "williams_r": 14,
            "adx": 14,
            "stoch_rsi_period": 14,
            "stoch_rsi_k_period": 3,
            "stoch_rsi_d_period": 3,
            "momentum": 10,
            "momentum_ma_short": 12,
            "momentum_ma_long": 26,
            "volume_ma": 20,
            "atr": 14,
            "sma_10": 10,
            "fve_price_ema": 10,
            "fve_obv_sma": 20,
            "fve_atr_sma": 20,
            "stoch_osc_k": 14,
            "stoch_osc_d": 3,
        },
        "order_book_analysis": {
            "enabled": True,
            "wall_threshold_multiplier": 2.0,
            "depth_to_check": 10,
            "support_boost": 3,
            "resistance_boost": 3,
        },
        "trailing_stop_loss": {
            "enabled": True,
            "initial_activation_percent": 0.5,
            "trailing_stop_multiple_atr": 1.5
        },
        "take_profit_scaling": {
            "enabled": True,
            "targets": [
                {"level": 1.5, "percentage": 0.25},
                {"level": 2.0, "percentage": 0.50}
            ]
        },
        "volatility_filter": {
            "enabled": True,
            "min_atr_percent": 0.5,
            "max_atr_percent": 5.0
        },
        "trend_filter": {
            "enabled": True,
            "long_ema_period": 200
        },
        "account_balance": 10000,
        "risk_per_trade_percent": 1.0,
        "database": {
            "enabled": True,
            "path": DATABASE_PATH
        }
    }
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            config = json.load(f)
            merged_config = {**default_config, **config}
            
            # Enhanced validation
            if merged_config.get("interval") not in VALID_INTERVALS:
                logger.warning(f"{NEON_YELLOW}Invalid 'interval' in config, using default: {default_config['interval']}{RESET}")
                merged_config["interval"] = default_config["interval"]
                
            if not isinstance(merged_config.get("analysis_interval"), int) or merged_config.get("analysis_interval") <= 0:
                logger.warning(f"{NEON_YELLOW}Invalid 'analysis_interval' in config, using default: {default_config['analysis_interval']}{RESET}")
                merged_config["analysis_interval"] = default_config["analysis_interval"]
                
            return merged_config
    except FileNotFoundError:
        logger.warning(f"{NEON_YELLOW}Config file not found, loading defaults and creating {filepath}{RESET}")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=4)
        return default_config
    except json.JSONDecodeError:
        logger.error(f"{NEON_RED}Invalid JSON in config file, loading defaults.{RESET}")
        try:
            os.rename(filepath, f"{filepath}.bak_{int(time.time())}")
            logger.info(f"{NEON_YELLOW}Backed up corrupt config file to {filepath}.bak_{int(time.time())}{RESET}")
        except OSError as e:
            logger.error(f"{NEON_RED}Failed to backup corrupt config file: {e}{RESET}")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=4)
        return default_config

# Load the configuration
CONFIG = load_config(CONFIG_FILE)

# --- Database Manager ---
class DatabaseManager:
    """Manages SQLite database operations for logging signals and trades."""
    def __init__(self, db_path: str, logger: logging.Logger):
        self.db_path = db_path
        self.logger = logger
        self._initialize_database()
    
    def _initialize_database(self):
        """Creates database tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    conditions_met TEXT,
                    stop_loss TEXT,
                    take_profit TEXT,
                    position_size REAL,
                    market_state TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_time TEXT NOT NULL,
                    exit_time TEXT,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_price TEXT NOT NULL,
                    exit_price TEXT,
                    quantity REAL NOT NULL,
                    profit_loss REAL,
                    status TEXT NOT NULL
                )
            """)
            conn.commit()
    
    def log_signal(self, signal: TradingSignal, symbol: str, interval: str, market_state: MarketState):
        """Logs a trading signal to the database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO signals (
                    timestamp, symbol, interval, signal_type, confidence,
                    conditions_met, stop_loss, take_profit, position_size, market_state
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal.timestamp.isoformat(),
                symbol,
                interval,
                signal.signal_type.value,
                signal.confidence,
                json.dumps(signal.conditions_met),
                str(signal.stop_loss) if signal.stop_loss else None,
                str(signal.take_profit) if signal.take_profit else None,
                signal.position_size,
                market_state.value
            ))
            conn.commit()
    
    def log_trade(self, trade: TradeState, symbol: str, exit_price: Optional[Decimal] = None, profit_loss: Optional[float] = None):
        """Logs a trade to the database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trades (
                    entry_time, exit_time, symbol, direction, entry_price,
                    exit_price, quantity, profit_loss, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade.entry_time.isoformat(),
                datetime.now(TIMEZONE).isoformat() if exit_price else None,
                symbol,
                "long" if trade.entry_price < trade.take_profit else "short",
                str(trade.entry_price),
                str(exit_price) if exit_price else None,
                trade.quantity,
                profit_loss,
                "closed" if exit_price else "open"
            ))
            conn.commit()

# --- API and Data Fetching ---
def generate_signature(api_secret: str, params: dict) -> str:
    """Generates the HMAC SHA256 signature for Bybit API requests."""
    param_str = "&".join([f"{key}={value}" for key, value in sorted(params.items())])
    return hmac.new(api_secret.encode(), param_str.encode(), hashlib.sha256).hexdigest()

def handle_api_error(response: requests.Response, logger: logging.Logger) -> None:
    """Logs detailed API error responses."""
    logger.error(f"{NEON_RED}API request failed with status code: {response.status_code}{RESET}")
    try:
        error_json = response.json()
        logger.error(f"{NEON_RED}Error details: {error_json}{RESET}")
    except json.JSONDecodeError:
        logger.error(f"{NEON_RED}Response text: {response.text}{RESET}")

def bybit_request(method: str, endpoint: str, api_key: str, api_secret: str, 
                  params: Dict[str, Any] = None, logger: logging.Logger = None) -> Union[dict, None]:
    """Sends a signed request to the Bybit API with retry logic."""
    params = params or {}
    params['timestamp'] = str(int(time.time() * 1000))
    signature = generate_signature(api_secret, params)
    headers = {
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-SIGN": signature,
        "X-BAPI-TIMESTAMP": params['timestamp'],
        "Content-Type": "application/json"
    }
    url = f"{BASE_URL}{endpoint}"
    
    for retry in range(MAX_API_RETRIES):
        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                params=params if method == "GET" else None,
                json=params if method == "POST" else None,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code in RETRY_ERROR_CODES:
                if logger:
                    logger.warning(f"{NEON_YELLOW}API Error {e.response.status_code} ({e.response.reason}), retrying {retry + 1}/{MAX_API_RETRIES}...{RESET}")
                time.sleep(RETRY_DELAY_SECONDS * (2**retry))
            else:
                if logger:
                    handle_api_error(e.response, logger)
                return None
        except requests.exceptions.RequestException as e:
            if logger:
                logger.error(f"{NEON_RED}Request exception: {e}, retrying {retry + 1}/{MAX_API_RETRIES}...{RESET}")
            time.sleep(RETRY_DELAY_SECONDS * (2**retry))
    
    if logger:
        logger.error(f"{NEON_RED}Max retries reached for {method} {endpoint}{RESET}")
    return None

def fetch_current_price(symbol: str, api_key: str, api_secret: str, logger: logging.Logger) -> Union[Decimal, None]:
    """Fetches the current last traded price for a given symbol."""
    endpoint = "/v5/market/tickers"
    params = {"category": "linear", "symbol": symbol}
    response_data = bybit_request("GET", endpoint, api_key, api_secret, params, logger)
    
    if response_data and response_data.get("retCode") == 0 and response_data.get("result"):
        tickers = response_data["result"].get("list")
        if tickers:
            for ticker in tickers:
                if ticker.get("symbol") == symbol:
                    last_price = ticker.get("lastPrice")
                    return Decimal(last_price) if last_price else None
    
    logger.error(f"{NEON_RED}Could not fetch current price for {symbol}. Response: {response_data}{RESET}")
    return None

def fetch_klines(symbol: str, interval: str, api_key: str, api_secret: str, 
                logger: logging.Logger, limit: int = 200) -> pd.DataFrame:
    """Fetches historical K-line data with enhanced validation."""
    endpoint = "/v5/market/kline"
    params = {"symbol": symbol, "interval": interval, "limit": limit, "category": "linear"}
    response_data = bybit_request("GET", endpoint, api_key, api_secret, params, logger)
    
    if response_data and response_data.get("retCode") == 0 and response_data.get("result") and response_data["result"].get("list"):
        data = response_data["result"]["list"]
        columns = ["start_time", "open", "high", "low", "close", "volume", "turnover"]
        df = pd.DataFrame(data, columns=columns)
        df["start_time"] = pd.to_datetime(pd.to_numeric(df["start_time"]), unit="ms")
        
        # Enhanced data validation
        for col in df.columns[1:]:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Remove rows with NaN values in critical columns
        df.dropna(subset=["open", "high", "low", "close", "volume"], inplace=True)
        
        if df.empty:
            logger.warning(f"{NEON_YELLOW}No valid kline data after cleaning for {symbol}{RESET}")
            return pd.DataFrame()
        
        return df.sort_values(by="start_time", ascending=True).reset_index(drop=True)
    
    logger.error(f"{NEON_RED}Failed to fetch Kline data for {symbol}, interval {interval}. Response: {response_data}{RESET}")
    return pd.DataFrame()

def fetch_order_book(symbol: str, api_key: str, api_secret: str, 
                    logger: logging.Logger, limit: int = 50) -> Union[dict, None]:
    """Fetches the order book with enhanced error handling."""
    endpoint = "/v5/market/orderbook"
    params = {"symbol": symbol, "limit": limit, "category": "linear"}
    response_data = bybit_request("GET", endpoint, api_key, api_secret, params, logger)
    
    if response_data and response_data.get("retCode") == 0 and response_data.get("result"):
        return response_data["result"]
    
    logger.warning(f"{NEON_YELLOW}Could not fetch order book for {symbol}. Response: {response_data}{RESET}")
    return None

# --- Trading Analysis Engine ---
class TradingAnalyzer:
    """Performs comprehensive technical analysis with enhanced features."""
    def __init__(self, df: pd.DataFrame, config: dict, symbol_logger: logging.Logger, 
                 symbol: str, interval: str, db_manager: DatabaseManager):
        self.df = df.copy()
        self.config = config
        self.logger = symbol_logger
        self.symbol = symbol
        self.interval = interval
        self.db_manager = db_manager
        self.levels: Dict[str, Any] = {}
        self.fib_levels: Dict[str, float] = {}
        self.weight_sets = config["weight_sets"]
        self.indicator_values: Dict[str, Any] = {}
        self.atr_value: float = 0.0
        self.market_state: MarketState = MarketState.RANGING
        
        # Pre-calculate common indicators
        self._pre_calculate_indicators()
        self.user_defined_weights = self._select_weight_set()
        
        if self.config["indicators"].get("stoch_rsi"):
            self.indicator_values["stoch_rsi_vals"] = self._calculate_stoch_rsi()
        if self.config["indicators"].get("stochastic_oscillator"):
            self.indicator_values["stoch_osc_vals"] = self._calculate_stochastic_oscillator()
    
    def _pre_calculate_indicators(self):
        """Pre-calculates indicators necessary for analysis."""
        if not self.df.empty:
            atr_series = self._calculate_atr(window=self.config["atr_period"])
            if not atr_series.empty and not pd.isna(atr_series.iloc[-1]):
                self.atr_value = atr_series.iloc[-1]
            else:
                self.atr_value = 0.0
            
            self.indicator_values["atr"] = self.atr_value
            self._calculate_momentum_ma()
            
            # Determine market state
            if self.config["volatility_filter"]["enabled"]:
                atr_percent = (self.atr_value / self.df["close"].iloc[-1]) * 100
                if atr_percent > self.config["volatility_filter"]["max_atr_percent"]:
                    self.market_state = MarketState.VOLATILE
                elif atr_percent < self.config["volatility_filter"]["min_atr_percent"]:
                    self.market_state = MarketState.RANGING
                else:
                    self.market_state = MarketState.TRENDING
            
            # Enhanced trend detection
            if self.config["trend_filter"]["enabled"]:
                long_ema = self._calculate_ema(self.config["trend_filter"]["long_ema_period"])
                if not long_ema.empty:
                    current_price = self.df["close"].iloc[-1]
                    long_ema_val = long_ema.iloc[-1]
                    if current_price > long_ema_val * 1.01:  # 1% above EMA
                        self.market_state = MarketState.TRENDING
                    elif current_price < long_ema_val * 0.99:  # 1% below EMA
                        self.market_state = MarketState.TRENDING
    
    def _select_weight_set(self) -> Dict[str, float]:
        """Selects a weight set based on current market conditions."""
        if self.market_state == MarketState.VOLATILE:
            self.logger.info(f"{NEON_YELLOW}Market detected as VOLATILE. Using 'high_volatility' weights.{RESET}")
            return self.weight_sets.get("high_volatility", self.weight_sets["low_volatility"])
        elif self.market_state == MarketState.TRENDING:
            self.logger.info(f"{NEON_GREEN}Market detected as TRENDING. Using 'low_volatility' weights.{RESET}")
            return self.weight_sets["low_volatility"]
        else:
            self.logger.info(f"{NEON_BLUE}Market detected as RANGING. Using 'low_volatility' weights.{RESET}")
            return self.weight_sets["low_volatility"]
    
    def _safe_series_operation(self, column: str, operation: str, window: int = None, 
                              series: pd.Series = None) -> pd.Series:
        """Safely performs operations on DataFrame columns."""
        if series is not None:
            data_series = series
        elif column in self.df.columns:
            data_series = self.df[column]
        else:
            self.logger.error(f"{NEON_RED}Missing '{column}' column for {operation} calculation.{RESET}")
            return pd.Series(dtype=float)
        
        if data_series.empty:
            return pd.Series(dtype=float)
        
        try:
            if operation == "sma":
                return data_series.rolling(window=window).mean()
            elif operation == "ema":
                return data_series.ewm(span=window, adjust=False).mean()
            elif operation == "max":
                return data_series.rolling(window=window).max()
            elif operation == "min":
                return data_series.rolling(window=window).min()
            elif operation == "diff":
                return data_series.diff(window)
            elif operation == "abs_diff_mean":
                return data_series.rolling(window=window).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
            elif operation == "cumsum":
                return data_series.cumsum()
            else:
                self.logger.error(f"{NEON_RED}Unsupported series operation: {operation}{RESET}")
                return pd.Series(dtype=float)
        except Exception as e:
            self.logger.error(f"{NEON_RED}Error during {operation} calculation on {column}: {e}{RESET}")
            return pd.Series(dtype=float)
    
    # ... (Keep all existing indicator calculation methods: _calculate_sma, _calculate_ema, etc.)
    # ... (Include all methods from the original code here)
    
    def detect_rsi_divergence(self) -> Union[str, None]:
        """Detects bullish or bearish RSI divergence."""
        if 'close' not in self.df.columns or len(self.df) < 30:
            return None
        
        rsi = self._calculate_rsi()
        prices = self.df["close"]
        
        # Check for bullish divergence (price makes lower low, RSI makes higher low)
        if (prices.iloc[-5] > prices.iloc[-1] and 
            rsi.iloc[-5] < rsi.iloc[-1] and 
            prices.iloc[-1] < prices.iloc[-5] * 0.98):  # Price at least 2% lower
            self.logger.info(f"{NEON_GREEN}Detected Bullish RSI Divergence.{RESET}")
            return "bullish"
        
        # Check for bearish divergence (price makes higher high, RSI makes lower high)
        if (prices.iloc[-5] < prices.iloc[-1] and 
            rsi.iloc[-5] > rsi.iloc[-1] and 
            prices.iloc[-1] > prices.iloc[-5] * 1.02):  # Price at least 2% higher
            self.logger.info(f"{NEON_RED}Detected Bearish RSI Divergence.{RESET}")
            return "bearish"
        
        return None
    
    def analyze_order_book_walls(self, order_book: Dict[str, Any]) -> Tuple[bool, bool, Dict[str, Decimal], Dict[str, Decimal], float, float]:
        """Analyzes order book for walls and calculates spread/imbalance."""
        has_bullish_wall = False
        has_bearish_wall = False
        bullish_wall_details: Dict[str, Decimal] = {}
        bearish_wall_details: Dict[str, Decimal] = {}
        spread = 0.0
        imbalance = 0.0
        
        if not self.config["order_book_analysis"]["enabled"]:
            return False, False, {}, {}, 0.0, 0.0
        
        if not order_book or not order_book.get('bids') or not order_book.get('asks'):
            self.logger.warning(f"{NEON_YELLOW}Order book data incomplete for wall analysis.{RESET}")
            return False, False, {}, {}, 0.0, 0.0
        
        bids = [(Decimal(price), Decimal(qty)) for price, qty in order_book['bids'][:self.config["order_book_analysis"]["depth_to_check"]]]
        asks = [(Decimal(price), Decimal(qty)) for price, qty in order_book['asks'][:self.config["order_book_analysis"]["depth_to_check"]]]
        
        # Calculate spread
        if bids and asks:
            best_bid = bids[0][0]
            best_ask = asks[0][0]
            spread = float((best_ask - best_bid) / best_bid * 100)
        
        # Calculate imbalance
        total_bid_qty = sum(qty for _, qty in bids)
        total_ask_qty = sum(qty for _, qty in asks)
        if total_bid_qty + total_ask_qty > 0:
            imbalance = float((total_bid_qty - total_ask_qty) / (total_bid_qty + total_ask_qty) * 100)
        
        # Calculate average quantity
        all_quantities = [qty for _, qty in bids + asks]
        if not all_quantities:
            return False, False, {}, {}, spread, imbalance
        
        avg_qty = Decimal(str(np.mean([float(q) for q in all_quantities])))
        wall_threshold = avg_qty * Decimal(str(self.config["order_book_analysis"]["wall_threshold_multiplier"]))
        
        # Check for bullish walls
        current_price = Decimal(str(self.df["close"].iloc[-1]))
        for bid_price, bid_qty in bids:
            if bid_qty >= wall_threshold and bid_price < current_price:
                has_bullish_wall = True
                bullish_wall_details[f"Bid@{bid_price}"] = bid_qty
                self.logger.info(f"{NEON_GREEN}Detected Bullish Order Book Wall: Bid {bid_qty:.2f} at {bid_price:.2f}{RESET}")
                break
        
        # Check for bearish walls
        for ask_price, ask_qty in asks:
            if ask_qty >= wall_threshold and ask_price > current_price:
                has_bearish_wall = True
                bearish_wall_details[f"Ask@{ask_price}"] = ask_qty
                self.logger.info(f"{NEON_RED}Detected Bearish Order Book Wall: Ask {ask_qty:.2f} at {ask_price:.2f}{RESET}")
                break
        
        return has_bullish_wall, has_bearish_wall, bullish_wall_details, bearish_wall_details, spread, imbalance
    
    def calculate_position_size(self, entry_price: Decimal, stop_loss: Decimal) -> float:
        """Calculates position size based on risk management rules."""
        if not self.config.get("account_balance") or not self.config.get("risk_per_trade_percent"):
            return 0.0
        
        account_balance = Decimal(str(self.config["account_balance"]))
        risk_percent = Decimal(str(self.config["risk_per_trade_percent"])) / 100
        risk_amount = account_balance * risk_percent
        
        # Calculate stop loss distance
        stop_distance = abs(entry_price - stop_loss)
        if stop_distance == 0:
            return 0.0
        
        position_size = float(risk_amount / stop_distance)
        return max(0.0, position_size)
    
    def analyze(self, current_price: Decimal, timestamp: str, order_book: Dict[str, Any]) -> TradingSignal:
        """Performs comprehensive analysis and returns a trading signal."""
        current_price_dec = Decimal(str(current_price))
        high_dec = Decimal(str(self.df["high"].max()))
        low_dec = Decimal(str(self.df["low"].min()))
        close_dec = Decimal(str(self.df["close"].iloc[-1])
        
        # Calculate Support/Resistance Levels
        self.calculate_fibonacci_retracement(high_dec, low_dec, current_price_dec)
        self.calculate_pivot_points(high_dec, low_dec, close_dec)
        nearest_supports, nearest_resistances = self.find_nearest_levels(current_price_dec)
        
        # Calculate indicators
        # ... (Include all indicator calculations from the original code)
        
        # Order Book Analysis
        has_bullish_wall, has_bearish_wall, bullish_wall_details, bearish_wall_details, spread, imbalance = \
            self.analyze_order_book_walls(order_book)
        
        self.indicator_values["order_book_walls"] = {
            "bullish": has_bullish_wall, "bearish": has_bearish_wall,
            "bullish_details": bullish_wall_details, "bearish_details": bearish_wall_details,
            "spread": spread, "imbalance": imbalance
        }
        
        # Prepare output string
        output = f"""
{NEON_BLUE}Exchange:{RESET} Bybit
{NEON_BLUE}Symbol:{RESET} {self.symbol}
{NEON_BLUE}Interval:{RESET} {self.interval}
{NEON_BLUE}Timestamp:{RESET} {timestamp}
{NEON_BLUE}Market State:{RESET} {self.market_state.value.upper()}
{NEON_BLUE}Price History:{RESET} {self.df['close'].iloc[-3]:.2f} | {self.df['close'].iloc[-2]:.2f} | {self.df['close'].iloc[-1]:.2f}
{NEON_BLUE}Volume History:{RESET} {self.df['volume'].iloc[-3]:,.0f} | {self.df['volume'].iloc[-2]:,.0f} | {self.df['volume'].iloc[-1]:,.0f}
{NEON_BLUE}Current Price:{RESET} {current_price_dec:.5f}
{NEON_BLUE}ATR ({self.config['atr_period']}):{RESET} {self.atr_value:.5f}
{NEON_BLUE}Trend:{RESET} {self.indicator_values.get("mom", {}).get("trend", "N/A")} (Strength: {self.indicator_values.get("mom", {}).get("strength", 0.0):.2f})
{NEON_BLUE}Order Book Spread:{RESET} {spread:.4f}%
{NEON_BLUE}Order Book Imbalance:{RESET} {imbalance:.2f}%
"""
        
        # ... (Include all indicator interpretations from the original code)
        
        # Order Book Wall Logging
        output += f"\n{NEON_BLUE}Order Book Walls:{RESET}\n"
        if has_bullish_wall:
            output += f"{NEON_GREEN}  Bullish Walls Found: {', '.join([f'{k}:{v:.2f}' for k,v in bullish_wall_details.items()])}{RESET}\n"
        if has_bearish_wall:
            output += f"{NEON_RED}  Bearish Walls Found: {', '.join([f'{k}:{v:.2f}' for k,v in bearish_wall_details.items()])}{RESET}\n"
        if not has_bullish_wall and not has_bearish_wall:
            output += "  No significant walls detected.\n"
        
        # Support and Resistance Levels
        output += f"\n{NEON_BLUE}Support and Resistance Levels:{RESET}\n"
        for s_label, s_val in nearest_supports:
            output += f"S: {s_label} ${s_val:.5f}\n"
        for r_label, r_val in nearest_resistances:
            output += f"R: {r_label} ${r_val:.5f}\n"
        
        self.logger.info(output)
        
        # Generate trading signal
        return self.generate_trading_signal(current_price_dec)
    
    def generate_trading_signal(self, current_price: Decimal) -> TradingSignal:
        """Generates a trading signal with enhanced logic."""
        signal_score = Decimal('0.0')
        signal_type = SignalType.HOLD
        conditions_met: List[str] = []
        stop_loss = None
        take_profit = None
        position_size = 0.0
        
        # ... (Include all signal generation logic from the original code)
        
        # Calculate position size if we have a valid signal
        if signal_type != SignalType.HOLD and stop_loss:
            position_size = self.calculate_position_size(current_price, stop_loss)
        
        return TradingSignal(
            signal_type=signal_type,
            confidence=float(signal_score),
            conditions_met=conditions_met,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=position_size,
            timestamp=datetime.now(TIMEZONE)
        )

# --- Trade Manager ---
class TradeManager:
    """Manages active trades with trailing stop and take profit scaling."""
    def __init__(self, config: dict, logger: logging.Logger, db_manager: DatabaseManager):
        self.config = config
        self.logger = logger
        self.db_manager = db_manager
        self.active_trades: Dict[str, TradeState] = {}
    
    def add_trade(self, symbol: str, signal: TradingSignal, current_price: Decimal):
        """Adds a new trade to the manager."""
        if signal.signal_type == SignalType.HOLD or not signal.stop_loss or not signal.take_profit:
            return
        
        trade = TradeState(
            entry_price=current_price,
            entry_time=signal.timestamp,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            highest_price=current_price,
            lowest_price=current_price,
            quantity=signal.position_size or 0.0,
            is_active=True
        )
        
        self.active_trades[symbol] = trade
        self.db_manager.log_trade(trade, symbol)
        self.logger.info(f"{NEON_GREEN}New trade opened for {symbol}: Entry={current_price}, SL={signal.stop_loss}, TP={signal.take_profit}{RESET}")
    
    def update_trades(self, symbol: str, current_price: Decimal, atr_value: float):
        """Updates active trades with trailing stop and take profit logic."""
        if symbol not in self.active_trades:
            return
        
        trade = self.active_trades[symbol]
        if not trade.is_active:
            return
        
        # Update highest/lowest prices
        trade.highest_price = max(trade.highest_price, current_price)
        trade.lowest_price = min(trade.lowest_price, current_price)
        
        # Trailing stop logic
        if self.config["trailing_stop_loss"]["enabled"]:
            activation_percent = Decimal(str(self.config["trailing_stop_loss"]["initial_activation_percent"])) / 100
            trailing_multiple = Decimal(str(self.config["trailing_stop_loss"]["trailing_stop_multiple_atr"]))
            
            # Determine if trailing should be activated
            price_progress = (current_price - trade.entry_price) / trade.entry_price
            
            if price_progress >= activation_percent:
                # Calculate new trailing stop
                if trade.entry_price < trade.take_profit:  # Long position
                    new_stop = trade.highest_price - (Decimal(str(atr_value)) * trailing_multiple)
                    if new_stop > trade.stop_loss:
                        trade.stop_loss = new_stop
                        self.logger.info(f"{NEON_YELLOW}Trailing stop updated for {symbol}: {trade.stop_loss}{RESET}")
                else:  # Short position
                    new_stop = trade.lowest_price + (Decimal(str(atr_value)) * trailing_multiple)
                    if new_stop < trade.stop_loss:
                        trade.stop_loss = new_stop
                        self.logger.info(f"{NEON_YELLOW}Trailing stop updated for {symbol}: {trade.stop_loss}{RESET}")
        
        # Take profit scaling
        if self.config["take_profit_scaling"]["enabled"]:
            for target in self.config["take_profit_scaling"]["targets"]:
                level = Decimal(str(target["level"]))
                percentage = target["percentage"]
                
                # Calculate target price
                if trade.entry_price < trade.take_profit:  # Long position
                    target_price = trade.entry_price + (Decimal(str(atr_value)) * level)
                    if current_price >= target_price:
                        # Close portion of position
                        close_qty = trade.quantity * percentage
                        trade.quantity -= close_qty
                        self.logger.info(f"{NEON_GREEN}Take profit triggered for {symbol}: Closed {close_qty} at {target_price}{RESET}")
                        
                        # Update trade in database
                        self.db_manager.log_trade(trade, symbol, target_price, float((target_price - trade.entry_price) * close_qty))
                        
                        # Break after first target hit (can be modified for multiple targets)
                        break
        
        # Check for stop loss or full take profit
        if (trade.entry_price < trade.take_profit and current_price <= trade.stop_loss) or \
           (trade.entry_price > trade.take_profit and current_price >= trade.stop_loss):
            # Stop loss hit
            trade.is_active = False
            profit_loss = float((current_price - trade.entry_price) * trade.quantity)
            self.db_manager.log_trade(trade, symbol, current_price, profit_loss)
            self.logger.info(f"{NEON_RED}Stop loss triggered for {symbol}: Closed at {current_price}, P&L: {profit_loss}{RESET}")
            del self.active_trades[symbol]
        elif (trade.entry_price < trade.take_profit and current_price >= trade.take_profit) or \
             (trade.entry_price > trade.take_profit and current_price <= trade.take_profit):
            # Take profit hit
            trade.is_active = False
            profit_loss = float((current_price - trade.entry_price) * trade.quantity)
            self.db_manager.log_trade(trade, symbol, current_price, profit_loss)
            self.logger.info(f"{NEON_GREEN}Take profit triggered for {symbol}: Closed at {current_price}, P&L: {profit_loss}{RESET}")
            del self.active_trades[symbol]

# --- Main Execution ---
def main():
    """Main function to run the trading analysis bot."""
    if not API_KEY or not API_SECRET:
        logger.error(f"{NEON_RED}BYBIT_API_KEY and BYBIT_API_SECRET must be set in your .env file.{RESET}")
        return
    
    # Initialize components
    db_manager = DatabaseManager(CONFIG["database"]["path"], logger) if CONFIG["database"]["enabled"] else None
    trade_manager = TradeManager(CONFIG, logger, db_manager) if db_manager else None
    
    symbol_input = input(f"{NEON_BLUE}Enter trading symbol (e.g., BTCUSDT): {RESET}").upper().strip()
    symbol = symbol_input if symbol_input else "BTCUSDT"
    
    interval_input = input(f"{NEON_BLUE}Enter timeframe (e.g., {', '.join(VALID_INTERVALS)} or press Enter for default {CONFIG['interval']}): {RESET}").strip()
    interval = interval_input if interval_input and interval_input in VALID_INTERVALS else CONFIG["interval"]
    
    # Setup dedicated logger for this symbol
    symbol_logger = setup_custom_logger(symbol)
    symbol_logger.info(f"{NEON_BLUE}Starting analysis for {symbol} with interval {interval}{RESET}")
    
    last_signal_time = 0.0
    last_order_book_fetch_time = 0.0
    
    while True:
        try:
            current_price = fetch_current_price(symbol, API_KEY, API_SECRET, symbol_logger)
            if current_price is None:
                symbol_logger.error(f"{NEON_RED}Failed to fetch current price for {symbol}. Skipping cycle.{RESET}")
                time.sleep(CONFIG["retry_delay"])
                continue
            
            df = fetch_klines(symbol, interval, API_KEY, API_SECRET, symbol_logger, limit=200)
            if df.empty:
                symbol_logger.error(f"{NEON_RED}Failed to fetch Kline data for {symbol}. Skipping cycle.{RESET}")
                time.sleep(CONFIG["retry_delay"])
                continue
            
            # Debounce order book fetching
            order_book_data = None
            if time.time() - last_order_book_fetch_time >= CONFIG["order_book_debounce_s"]:
                order_book_data = fetch_order_book(symbol, API_KEY, API_SECRET, symbol_logger, limit=CONFIG["order_book_depth_to_check"])
                last_order_book_fetch_time = time.time()
            else:
                symbol_logger.debug(f"{NEON_YELLOW}Order book fetch debounced. Next fetch in {CONFIG['order_book_debounce_s'] - (time.time() - last_order_book_fetch_time):.1f}s{RESET}")
            
            # Perform analysis
            analyzer = TradingAnalyzer(df, CONFIG, symbol_logger, symbol, interval, db_manager)
            timestamp = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S %Z")
            
            # Generate signal
            signal = analyzer.analyze(current_price, timestamp, order_book_data)
            
            # Log signal to database
            if db_manager:
                db_manager.log_signal(signal, symbol, interval, analyzer.market_state)
            
            # Process signal
            current_time_seconds = time.time()
            if signal.signal_type != SignalType.HOLD and (current_time_seconds - last_signal_time >= CONFIG["signal_cooldown_s"]):
                symbol_logger.info(f"\n{NEON_PURPLE}--- TRADING SIGNAL TRIGGERED ---{RESET}")
                symbol_logger.info(f"{NEON_BLUE}Signal:{RESET} {signal.signal_type.value.upper()} (Confidence: {signal.confidence:.2f})")
                symbol_logger.info(f"{NEON_BLUE}Conditions Met:{RESET} {', '.join(signal.conditions_met) if signal.conditions_met else 'None'}")
                symbol_logger.info(f"{NEON_BLUE}Position Size:{RESET} {signal.position_size:.4f}")
                
                if signal.stop_loss:
                    symbol_logger.info(f"{NEON_GREEN}Suggested Stop Loss:{RESET} {signal.stop_loss:.5f}")
                if signal.take_profit:
                    symbol_logger.info(f"{NEON_GREEN}Suggested Take Profit:{RESET} {signal.take_profit:.5f}")
                
                # Add trade to manager if enabled
                if trade_manager:
                    trade_manager.add_trade(symbol, signal, current_price)
                
                last_signal_time = current_time_seconds
            
            # Update active trades
            if trade_manager:
                trade_manager.update_trades(symbol, current_price, analyzer.atr_value)
            
            time.sleep(CONFIG["analysis_interval"])
        
        except requests.exceptions.RequestException as e:
            symbol_logger.error(f"{NEON_RED}Network or API communication error: {e}. Retrying in {CONFIG['retry_delay']} seconds...{RESET}")
            time.sleep(CONFIG["retry_delay"])
        except KeyboardInterrupt:
            symbol_logger.info(f"{NEON_YELLOW}Analysis stopped by user.{RESET}")
            break
        except Exception as e:
            symbol_logger.exception(f"{NEON_RED}An unexpected error occurred: {e}. Retrying in {CONFIG['retry_delay']} seconds...{RESET}")
            time.sleep(CONFIG["retry_delay"])

if __name__ == "__main__":
    main()
