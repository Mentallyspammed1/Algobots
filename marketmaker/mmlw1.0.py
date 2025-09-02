import argparse
import hashlib
import hmac
import json
import logging
import math
import os
import signal
import subprocess
import sys
import threading
import time
from collections import deque, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, getcontext
from enum import Enum
from functools import wraps
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import warnings

# Ignore common warnings from libraries
warnings.filterwarnings('ignore')

# region: Dependency and Environment Setup
# ==============================================================================
try:
    import ccxt
    import numpy as np
    import pandas as pd
    import requests
    import websocket
    from colorama import Fore, Style, init
    from pydantic import (
        BaseModel,
        ConfigDict,
        Field,
        NonNegativeFloat,
        NonNegativeInt,
        PositiveFloat,
        PositiveInt,
        ValidationError,
    )
    try:
        from dotenv import load_dotenv
        DOTENV_AVAILABLE = True
    except ImportError:
        DOTENV_AVAILABLE = False

    EXTERNAL_LIBS_AVAILABLE = True
except ImportError as e:
    print(f"Error: Missing required library: {e}. Please install it using pip.")
    print("Install all dependencies with: pip install ccxt pandas numpy requests websocket-client pydantic colorama python-dotenv")
    EXTERNAL_LIBS_AVAILABLE = False
    sys.exit(1)

if EXTERNAL_LIBS_AVAILABLE:
    init(autoreset=True)
    getcontext().prec = 38

if DOTENV_AVAILABLE:
    load_dotenv()
    print(f"{Fore.CYAN}# Environment variables loaded successfully.{Style.RESET_ALL}")

# Enhanced color scheme for logging
class Colors:
    CYAN = Fore.CYAN + Style.BRIGHT
    MAGENTA = Fore.MAGENTA + Style.BRIGHT
    YELLOW = Fore.YELLOW + Style.BRIGHT
    RESET = Style.RESET_ALL
    NEON_GREEN = Fore.GREEN + Style.BRIGHT
    NEON_BLUE = Fore.BLUE + Style.BRIGHT
    NEON_RED = Fore.RED + Style.BRIGHT
    NEON_ORANGE = Fore.LIGHTRED_EX + Style.BRIGHT
    WHITE = Fore.WHITE + Style.BRIGHT
    DARK_GRAY = Fore.LIGHTBLACK_EX

# Environment variables
BYBIT_API_KEY: Optional[str] = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET: Optional[str] = os.getenv("BYBIT_API_SECRET")

# Directory setup
BASE_DIR = Path(os.getenv("HOME", "."))
LOG_DIR: Path = BASE_DIR / "bot_logs"
STATE_DIR: Path = BASE_DIR / ".bot_state"
LOG_DIR.mkdir(parents=True, exist_ok=True)
STATE_DIR.mkdir(parents=True, exist_ok=True)


# Exchange configuration
EXCHANGE_CONFIG = {
    "id": "bybit",
    "apiKey": BYBIT_API_KEY,
    "secret": BYBIT_API_SECRET,
    "enableRateLimit": True,
    "timeout": 30000,  # Set timeout to 30 seconds (in milliseconds)
    "options": {
        "defaultType": "linear",
        "verbose": False,
        "adjustForTimeDifference": True, # Explicitly enable time adjustment
        "v5": True,
        "recvWindow": 10000
    },
}
# Constants
API_RETRY_ATTEMPTS = 5
RETRY_BACKOFF_FACTOR = 0.5
WS_RECONNECT_INTERVAL = 5
SYMBOL_INFO_REFRESH_INTERVAL = 24 * 60 * 60
STATUS_UPDATE_INTERVAL = 30
MAIN_LOOP_SLEEP_INTERVAL = 1
DECIMAL_ZERO = Decimal("0")
MIN_TRADE_PNL_PERCENT = Decimal("-0.0005")

class TradingBias(Enum):
    STRONG_BULLISH = "STRONG_BULLISH"
    WEAK_BULLISH = "WEAK_BULLISH"
    NEUTRAL = "NEUTRAL"
    WEAK_BEARISH = "WEAK_BEARISH"
    STRONG_BEARISH = "STRONG_BEARISH"
# endregion

# region: Utility Functions and Classes
# ==============================================================================
class JsonDecimalEncoder(json.JSONEncoder):
    """Enhanced JSON encoder for Decimal types."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)

def json_loads_decimal(s: str) -> Any:
    """Enhanced JSON decoder for Decimal types."""
    try:
        return json.loads(s, parse_float=Decimal, parse_int=Decimal)
    except (json.JSONDecodeError, InvalidOperation) as e:
        logging.error(f"Error decoding JSON with Decimal: {e}")
        raise ValueError(f"Invalid JSON or Decimal format: {e}") from e
# endregion

# region: Pydantic Models for Configuration and Data
# ==============================================================================
class Trade(BaseModel):
    side: str
    qty: Decimal
    price: Decimal
    profit: Decimal = DECIMAL_ZERO
    timestamp: int
    fee: Decimal
    trade_id: str
    entry_price: Optional[Decimal] = None
    exit_price: Optional[Decimal] = None
    pnl_percent: Optional[Decimal] = None
    market_condition: Optional[str] = None
    signal_strength: Optional[Decimal] = None
    
    model_config = ConfigDict(
        json_dumps=lambda v: json.dumps(v, cls=JsonDecimalEncoder),
        json_loads=json_loads_decimal,
        validate_assignment=True
    )

class DynamicSpreadConfig(BaseModel):
    enabled: bool = True
    volatility_multiplier: PositiveFloat = 0.5
    atr_update_interval: NonNegativeInt = 300
    min_spread_pct: PositiveFloat = 0.0005
    max_spread_pct: PositiveFloat = 0.01
    use_bollinger_bands: bool = True
    bb_period: PositiveInt = 20
    bb_std_dev: PositiveFloat = 2.0

class InventorySkewConfig(BaseModel):
    enabled: bool = True
    skew_factor: PositiveFloat = 0.1
    max_skew: Optional[PositiveFloat] = 0.002
    aggressive_rebalance: bool = False
    rebalance_threshold: PositiveFloat = 0.7

class OrderLayer(BaseModel):
    spread_offset: NonNegativeFloat = 0.0
    quantity_multiplier: PositiveFloat = 1.0
    cancel_threshold_pct: PositiveFloat = 0.01
    aggressiveness: PositiveFloat = 1.0
    use_iceberg: bool = False
    iceberg_qty_pct: PositiveFloat = 0.3

class MarketMicrostructure(BaseModel):
    enabled: bool = True
    tick_size_multiplier: PositiveFloat = 1.0
    queue_position_factor: PositiveFloat = 0.5
    adverse_selection_threshold: PositiveFloat = 0.001
    flow_toxicity_window: PositiveInt = 100

class SignalConfig(BaseModel):
    use_rsi: bool = True
    rsi_period: PositiveInt = 14
    rsi_overbought: PositiveFloat = 70.0
    rsi_oversold: PositiveFloat = 30.0
    use_macd: bool = True
    macd_fast: PositiveInt = 12
    macd_slow: PositiveInt = 26
    macd_signal: PositiveInt = 9
    signal_bias_strength: PositiveFloat = 0.5 # How much signal skews quotes
    use_volume_profile: bool = True
    volume_lookback: PositiveInt = 100
    use_order_flow: bool = True
    flow_imbalance_threshold: PositiveFloat = 0.6

class OrderbookAnalysisConfig(BaseModel):
    enabled: bool = True
    obi_depth: PositiveInt = 20
    obi_impact_factor: NonNegativeFloat = 0.4
    cliff_depth: PositiveInt = 5
    cliff_factor: PositiveFloat = 5.0
    toxic_spread_widener: PositiveFloat = 2.0
    wap_instead_of_mid: bool = True

class RiskManagement(BaseModel):
    max_drawdown_pct: PositiveFloat = 0.1
    var_confidence: PositiveFloat = 0.95
    position_sizing_kelly: bool = True
    kelly_fraction: PositiveFloat = 0.25
    use_circuit_breaker: bool = True
    circuit_breaker_threshold: PositiveFloat = 0.05
    max_order_retry: PositiveInt = 3
    anti_spoofing_detection: bool = True

class SymbolConfig(BaseModel):
    symbol: str
    trade_enabled: bool = True
    base_spread: PositiveFloat = 0.001
    order_amount: PositiveFloat = 0.001
    leverage: PositiveFloat = 10.0
    order_refresh_time: NonNegativeInt = 5
    max_spread: PositiveFloat = 0.005
    inventory_limit: PositiveFloat = 0.01
    
    dynamic_spread: DynamicSpreadConfig = Field(default_factory=DynamicSpreadConfig)
    inventory_skew: InventorySkewConfig = Field(default_factory=InventorySkewConfig)
    market_microstructure: MarketMicrostructure = Field(default_factory=MarketMicrostructure)
    signal_config: SignalConfig = Field(default_factory=SignalConfig)
    orderbook_analysis: OrderbookAnalysisConfig = Field(default_factory=OrderbookAnalysisConfig)
    risk_management: RiskManagement = Field(default_factory=RiskManagement)
    
    order_layers: List[OrderLayer] = Field(default_factory=lambda: [
        OrderLayer(spread_offset=0.0, quantity_multiplier=1.0)
    ])
    
    min_qty: Optional[Decimal] = None
    max_qty: Optional[Decimal] = None
    qty_precision: Optional[int] = None
    price_precision: Optional[int] = None
    min_notional: Optional[Decimal] = None
    tick_size: Optional[Decimal] = None
    kline_interval: str = "1m"
    market_data_stale_timeout_seconds: NonNegativeInt = 30
    use_batch_orders_for_refresh: bool = True
    
    model_config = ConfigDict(
        json_dumps=lambda v: json.dumps(v, cls=JsonDecimalEncoder),
        json_loads=json_loads_decimal,
        validate_assignment=True
    )

class GlobalConfig(BaseModel):
    category: str = "linear"
    api_max_retries: PositiveInt = 5
    api_retry_delay: PositiveInt = 1
    log_level: str = "INFO"
    log_file: str = "market_maker_live.log"
    state_file: str = "state.json"
    symbol_config_file: str = "symbols.json"
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    
    model_config = ConfigDict(
        json_dumps=lambda v: json.dumps(v, cls=JsonDecimalEncoder),
        json_loads=json_loads_decimal,
        validate_assignment=True
    )
# endregion

# region: Configuration Management
# ==============================================================================
class ConfigManager:
    _global_config: Optional[GlobalConfig] = None
    _symbol_configs: List[SymbolConfig] = []
    
    @classmethod
    def load_config(cls, prompt_for_symbol: bool = False, input_symbol: Optional[str] = None) -> Tuple[GlobalConfig, List[SymbolConfig]]:
        global_data = {
            "category": os.getenv("BYBIT_CATEGORY", "linear"),
            "api_max_retries": int(os.getenv("API_MAX_RETRIES", "5")),
            "api_retry_delay": int(os.getenv("API_RETRY_DELAY", "1")),
            "log_level": os.getenv("LOG_LEVEL", "INFO"),
            "log_file": os.getenv("LOG_FILE", "market_maker_live.log"),
            "state_file": os.getenv("STATE_FILE", "state.json"),
            "symbol_config_file": os.getenv("SYMBOL_CONFIG_FILE", "symbols.json"),
            "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN"),
            "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID"),
        }
        
        try:
            cls._global_config = GlobalConfig(**global_data)
        except ValidationError as e:
            logging.critical(f"Global configuration validation error: {e}")
            sys.exit(1)
        
        cls._symbol_configs = []
        if prompt_for_symbol and input_symbol:
            single_symbol_data = { "symbol": input_symbol }
            try:
                cls._symbol_configs.append(SymbolConfig(**single_symbol_data))
                logging.info(f"Using single symbol mode for {input_symbol}.")
            except ValidationError as e:
                logging.critical(f"Symbol configuration validation error: {e}")
                sys.exit(1)
        else:
            try:
                symbol_config_path = Path(cls._global_config.symbol_config_file)
                if symbol_config_path.exists():
                    with open(symbol_config_path) as f:
                        raw_symbol_configs = json.load(f)
                    
                    for s_cfg in raw_symbol_configs:
                        try:
                            cls._symbol_configs.append(SymbolConfig(**s_cfg))
                        except ValidationError as e:
                            logging.warning(f"Symbol config validation error for {s_cfg.get('symbol', 'N/A')}: {e}")
                else:
                    logging.warning(f"Symbol config file not found: {symbol_config_path}")
            except Exception as e:
                logging.error(f"Error loading symbol configs: {e}")
        
        return cls._global_config, cls._symbol_configs

GLOBAL_CONFIG: Optional[GlobalConfig] = None
SYMBOL_CONFIGS: List[SymbolConfig] = []
# endregion

# region: Core Infrastructure (Logging, Notifications, Exchange)
# ==============================================================================
def setup_logger(name_suffix: str) -> logging.Logger:
    logger_name = f"market_maker_{name_suffix}"
    logger = logging.getLogger(logger_name)
    
    if logger.hasHandlers():
        return logger
    
    log_level_str = GLOBAL_CONFIG.log_level.upper() if GLOBAL_CONFIG else "INFO"
    logger.setLevel(getattr(logging, log_level_str, logging.INFO))
    
    log_file_path = LOG_DIR / (GLOBAL_CONFIG.log_file if GLOBAL_CONFIG else "market_maker_live.log")
    
    file_handler = RotatingFileHandler(log_file_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
    file_formatter = logging.Formatter("%(asctime)s - %(levelname)s - [%(name)s:%(lineno)d] - %(message)s")
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_formatter = logging.Formatter(
        f"{Colors.NEON_BLUE}%(asctime)s{Colors.RESET} - {Colors.YELLOW}%(levelname)-8s{Colors.RESET} - {Colors.MAGENTA}[%(name)s]{Colors.RESET} - %(message)s",
        datefmt="%H:%M:%S",
    )
    stream_handler.setFormatter(stream_formatter)
    logger.addHandler(stream_handler)
    
    logger.propagate = False
    return logger

main_logger = logging.getLogger("market_maker_main")

class TelegramNotifier:
    def __init__(self, token: Optional[str], chat_id: Optional[str], logger: logging.Logger):
        self.token = token
        self.chat_id = chat_id
        self.logger = logger
        self.is_configured = bool(token and chat_id)
        if self.is_configured:
            self.logger.info("Telegram notifier configured.")

    def send_message(self, message: str):
        if not self.is_configured: return
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": message, "parse_mode": "Markdown"}
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            self.logger.error(f"Failed to send Telegram message: {e}")

def initialize_exchange(logger: logging.Logger) -> Optional[Any]:
    if not BYBIT_API_KEY or not BYBIT_API_SECRET:
        logger.critical("API Key and/or Secret not found. Cannot initialize exchange.")
        return None
    try:
        exchange = getattr(ccxt, EXCHANGE_CONFIG["id"])(EXCHANGE_CONFIG)
        exchange.set_sandbox_mode(False)
        exchange.load_markets()
        logger.info(f"Exchange '{EXCHANGE_CONFIG['id']}' initialized successfully.")
        return exchange
    except Exception as e:
        logger.critical(f"Failed to initialize exchange: {e}", exc_info=True)
        return None
# endregion

# region: Technical Analysis Functions
# ==============================================================================
def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).fillna(0)
    loss = -delta.where(delta < 0, 0).fillna(0)
    avg_gain = gain.rolling(window=period, min_periods=1).mean()
    avg_loss = loss.rolling(window=period, min_periods=1).mean()
    rs = avg_gain / avg_loss.replace(0, 1)
    return 100 - (100 / (1 + rs))

def calculate_macd(prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = prices.ewm(span=fast, adjust=False).mean()
    ema_slow = prices.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def calculate_bollinger_bands(prices: pd.Series, period: int = 20, std_dev: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
    middle = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std()
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    return upper, middle, lower

def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr = pd.DataFrame()
    tr['h_l'] = high - low
    tr['h_pc'] = (high - close.shift(1)).abs()
    tr['l_pc'] = (low - close.shift(1)).abs()
    tr['tr'] = tr[['h_l', 'h_pc', 'l_pc']].max(axis=1)
    return tr['tr'].ewm(alpha=1/period, adjust=False).mean()
# endregion

# region: API Call Decorator
# ==============================================================================
def retry_api_call(
    attempts: int = API_RETRY_ATTEMPTS,
    backoff_factor: float = RETRY_BACKOFF_FACTOR,
    fatal_exceptions: Tuple[type, ...] = (ccxt.AuthenticationError, ccxt.ArgumentsRequired)
):
    def decorator(func: Callable[..., Any]):
        @wraps(func)
        def wrapper(self, *args: Any, **kwargs: Any) -> Any:
            logger = self.logger if hasattr(self, "logger") else main_logger
            last_exception = None
            
            for i in range(attempts):
                try:
                    return func(self, *args, **kwargs)
                except fatal_exceptions as e:
                    logger.critical(f"Fatal API error in {func.__name__}: {e}")
                    raise
                except (ccxt.NetworkError, ccxt.ExchangeError, ccxt.DDoSProtection) as e:
                    last_exception = e
                    sleep_time = backoff_factor * (2 ** i)
                    logger.warning(f"API call {func.__name__} failed (attempt {i+1}/{attempts}): {e}. Retrying in {sleep_time:.2f}s...")
                    time.sleep(sleep_time)
                except ccxt.BadRequest as e:
                    error_str = str(e)
                    if any(code in error_str for code in ["110043", "110025", "110047"]): # Already cancelled, order not found etc.
                        logger.debug(f"Ignorable BadRequest in {func.__name__}: {e}")
                        return None
                    logger.error(f"BadRequest in {func.__name__}: {e}")
                    last_exception = e
                    break # Do not retry on most bad requests
            
            logger.error(f"API call {func.__name__} failed after {attempts} attempts.")
            if last_exception:
                raise last_exception
        return wrapper
    return decorator
# endregion

# region: WebSocket Client
# ==============================================================================
class BybitWebsocketClient:
    """Handles Bybit V5 WebSocket connections for real-time market data."""
    WS_URL = "wss://stream.bybit.com/v5/public/linear"

    def __init__(self, symbols: List[str], logger: logging.Logger, message_queue: deque):
        self.ws: Optional[websocket.WebSocketApp] = None
        self.thread: Optional[threading.Thread] = None
        self.logger = logger
        self.symbols = symbols
        self.message_queue = message_queue
        self.is_running = False

    def _on_message(self, ws, message):
        self.message_queue.append(json.loads(message))

    def _on_error(self, ws, error):
        self.logger.error(f"WebSocket error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        self.logger.warning(f"WebSocket closed. Code: {close_status_code}, Msg: {close_msg}")
        self.is_running = False

    def _on_open(self, ws):
        self.logger.info("WebSocket connection opened.")
        topics = []
        for symbol in self.symbols:
            topics.append(f"orderbook.50.{symbol}")
            topics.append(f"publicTrade.{symbol}")
        
        op_data = {"op": "subscribe", "args": topics}
        ws.send(json.dumps(op_data))
        self.logger.info(f"Subscribed to topics: {topics}")

    def _run(self):
        while True:
            self.logger.info("Starting WebSocket client...")
            self.ws = websocket.WebSocketApp(
                self.WS_URL,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close
            )
            self.is_running = True
            self.ws.run_forever(ping_interval=20, ping_timeout=10)
            
            self.logger.info(f"WebSocket disconnected. Reconnecting in {WS_RECONNECT_INTERVAL} seconds...")
            time.sleep(WS_RECONNECT_INTERVAL)

    def start(self):
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
            self.logger.info("WebSocket client thread started.")

    def stop(self):
        if self.ws:
            self.ws.close()
        self.is_running = False
        self.logger.info("WebSocket client stopped.")
# endregion

# region: Main Strategy Class
# ==============================================================================
class EnhancedMarketMakerStrategy:
    """The core market making and directional strategy logic."""

    def __init__(self, global_config: GlobalConfig, symbol_configs: List[SymbolConfig], exchange: Any):
        self.logger = setup_logger("strategy")
        self.global_config = global_config
        self.symbol_configs = {cfg.symbol: cfg for cfg in symbol_configs}
        self.exchange = exchange
        self.running = True
        self.state_file_path = STATE_DIR / global_config.state_file
        
        self.notifier = TelegramNotifier(
            global_config.telegram_bot_token,
            global_config.telegram_chat_id,
            self.logger
        )

        # Data structures
        self.orderbooks = {s: {} for s in self.symbol_configs}
        self.prev_orderbooks = {s: None for s in self.symbol_configs}
        self.positions = {s: DECIMAL_ZERO for s in self.symbol_configs}
        self.open_orders = {s: [] for s in self.symbol_configs}
        self.kline_data = {s: pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']) for s in self.symbol_configs}
        self.signals = {s: {} for s in self.symbol_configs}
        self.last_market_data_time = {s: 0 for s in self.symbol_configs}
        
        # State and performance
        self.total_pnl = DECIMAL_ZERO
        self.daily_pnl = DECIMAL_ZERO
        self.last_daily_reset = datetime.now(timezone.utc).date()
        
        # WebSocket
        self.ws_message_queue = deque(maxlen=1000)
        self.ws_client = BybitWebsocketClient(
            list(self.symbol_configs.keys()),
            setup_logger("websocket"),
            self.ws_message_queue
        )

    def _setup_signal_handler(self):
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame):
        self.logger.warning(f"Shutdown signal {signum} received. Exiting gracefully...")
        self.running = False

    def _load_state(self):
        if self.state_file_path.exists():
            try:
                with open(self.state_file_path, 'r') as f:
                    state = json_loads_decimal(f.read())
                self.total_pnl = state.get('total_pnl', DECIMAL_ZERO)
                self.daily_pnl = state.get('daily_pnl', DECIMAL_ZERO)
                self.logger.info(f"Successfully loaded state from {self.state_file_path}")
            except Exception as e:
                self.logger.error(f"Could not load state: {e}")

    def _save_state(self):
        state = {
            'total_pnl': self.total_pnl,
            'daily_pnl': self.daily_pnl,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        try:
            with open(self.state_file_path, 'w') as f:
                json.dump(state, f, cls=JsonDecimalEncoder, indent=4)
            self.logger.debug("Successfully saved state.")
        except Exception as e:
            self.logger.error(f"Could not save state: {e}")

    @retry_api_call()
    def _update_symbol_info(self):
        self.logger.info("Refreshing symbol information...")
        markets = self.exchange.fetch_markets()
        for market in markets:
            symbol = market['symbol']
            if symbol in self.symbol_configs:
                s_cfg = self.symbol_configs[symbol]
                s_cfg.min_qty = Decimal(str(market['limits']['amount']['min']))
                s_cfg.qty_precision = int(market['precision']['amount'])
                s_cfg.price_precision = int(market['precision']['price'])
                s_cfg.tick_size = Decimal(str(market['precision']['price']))
                s_cfg.min_notional = Decimal(str(market['limits']['cost']['min']))
                self.logger.info(f"Updated info for {symbol}: Min Qty {s_cfg.min_qty}, Price Precision {s_cfg.price_precision}")

    def _process_ws_messages(self):
        while self.ws_message_queue:
            msg = self.ws_message_queue.popleft()
            topic = msg.get('topic', '')
            
            if 'orderbook' in topic:
                symbol = msg['data']['s']
                self.orderbooks[symbol] = {
                    'bids': [(Decimal(p), Decimal(q)) for p, q in msg['data']['b']],
                    'asks': [(Decimal(p), Decimal(q)) for p, q in msg['data']['a']],
                    'timestamp': msg['ts']
                }
                self.last_market_data_time[symbol] = time.time()

    # region: Orderbook Analysis Methods
    def _get_mid_price(self, symbol: str) -> Optional[Decimal]:
        ob = self.orderbooks.get(symbol)
        if not ob or not ob.get('bids') or not ob.get('asks'): return None
        return (ob['bids'][0][0] + ob['asks'][0][0]) / 2

    def _get_weighted_average_price(self, symbol: str) -> Optional[Decimal]:
        ob = self.orderbooks.get(symbol)
        if not ob or not ob.get('bids') or not ob.get('asks'): return None
        best_bid_price, best_bid_qty = ob['bids'][0]
        best_ask_price, best_ask_qty = ob['asks'][0]
        if best_bid_qty + best_ask_qty == 0: return (best_bid_price + best_ask_price) / 2
        return (best_bid_price * best_ask_qty + best_ask_price * best_bid_qty) / (best_bid_qty + best_ask_qty)

    def _calculate_orderbook_imbalance(self, symbol: str) -> Optional[Decimal]:
        s_cfg = self.symbol_configs[symbol]
        ob = self.orderbooks.get(symbol)
        if not ob or not ob.get('bids') or not ob.get('asks'): return None
        depth = s_cfg.orderbook_analysis.obi_depth
        bid_volume = sum(q for p, q in ob['bids'][:depth])
        ask_volume = sum(q for p, q in ob['asks'][:depth])
        if bid_volume + ask_volume == 0: return Decimal('0.5')
        return bid_volume / (bid_volume + ask_volume)

    def _get_market_spread(self, symbol: str) -> Optional[Tuple[Decimal, Decimal]]:
        ob = self.orderbooks.get(symbol)
        if not ob or not ob.get('bids') or not ob.get('asks'): return None
        best_bid, best_ask = ob['bids'][0][0], ob['asks'][0][0]
        if best_bid <= 0: return None
        return (best_ask - best_bid) / best_bid, best_ask - best_bid

    def _analyze_liquidity_cliffs(self, symbol: str) -> Tuple[bool, bool]:
        s_cfg = self.symbol_configs[symbol]
        ob = self.orderbooks.get(symbol)
        depth = s_cfg.orderbook_analysis.cliff_depth
        factor = Decimal(str(s_cfg.orderbook_analysis.cliff_factor))
        if not ob or len(ob.get('bids', [])) < depth or len(ob.get('asks', [])) < depth:
            return False, False
        
        top_bid_qty = ob['bids'][0][1]
        next_bids_avg_qty = sum(q for p, q in ob['bids'][1:depth]) / (depth - 1)
        is_bid_cliff = next_bids_avg_qty > 0 and (top_bid_qty / next_bids_avg_qty) < (1/factor)

        top_ask_qty = ob['asks'][0][1]
        next_asks_avg_qty = sum(q for p, q in ob['asks'][1:depth]) / (depth - 1)
        is_ask_cliff = next_asks_avg_qty > 0 and (top_ask_qty / next_asks_avg_qty) < (1/factor)

        if is_bid_cliff: self.logger.debug(f"Liquidity cliff detected on BID side for {symbol}")
        if is_ask_cliff: self.logger.debug(f"Liquidity cliff detected on ASK side for {symbol}")
        return is_bid_cliff, is_ask_cliff

    def _detect_toxic_flow(self, symbol: str) -> Tuple[bool, bool]:
        is_toxic_on_bid, is_toxic_on_ask = False, False
        prev_ob, curr_ob = self.prev_orderbooks.get(symbol), self.orderbooks.get(symbol)
        if not prev_ob or not curr_ob:
            self.prev_orderbooks[symbol] = curr_ob
            return is_toxic_on_bid, is_toxic_on_ask

        if curr_ob['bids'][0][0] < prev_ob['bids'][0][0]: is_toxic_on_bid = True
        if curr_ob['asks'][0][0] > prev_ob['asks'][0][0]: is_toxic_on_ask = True
        
        if is_toxic_on_bid: self.logger.warning(f"Potential toxic flow on BID side for {symbol}")
        if is_toxic_on_ask: self.logger.warning(f"Potential toxic flow on ASK side for {symbol}")
        
        self.prev_orderbooks[symbol] = curr_ob
        return is_toxic_on_bid, is_toxic_on_ask
    # endregion

    # region: Signal and Bias Calculation
    def _update_technical_signals(self, symbol: str):
        s_cfg = self.symbol_configs[symbol]
        klines = self.kline_data.get(symbol)
        if klines is None or klines.empty: return

        if s_cfg.signal_config.use_rsi:
            self.signals[symbol]['rsi'] = calculate_rsi(klines['close'], s_cfg.signal_config.rsi_period).iloc[-1]
        
        if s_cfg.signal_config.use_macd:
            _, _, macd_hist = calculate_macd(klines['close'], s_cfg.signal_config.macd_fast, s_cfg.signal_config.macd_slow, s_cfg.signal_config.macd_signal)
            self.signals[symbol]['macd_hist'] = macd_hist.iloc[-1]

    def _get_directional_bias(self, symbol: str) -> TradingBias:
        s_cfg = self.symbol_configs[symbol]
        signals = self.signals.get(symbol, {})
        score = 0

        if s_cfg.signal_config.use_rsi and 'rsi' in signals:
            rsi = signals['rsi']
            if rsi < s_cfg.signal_config.rsi_oversold: score += 1
            if rsi > s_cfg.signal_config.rsi_overbought: score -= 1
        
        if s_cfg.signal_config.use_macd and 'macd_hist' in signals:
            if signals['macd_hist'] > 0: score += 1
            if signals['macd_hist'] < 0: score -= 1
        
        if score >= 2: return TradingBias.STRONG_BULLISH
        if score == 1: return TradingBias.WEAK_BULLISH
        if score == -1: return TradingBias.WEAK_BEARISH
        if score <= -2: return TradingBias.STRONG_BEARISH
        return TradingBias.NEUTRAL
    # endregion

    def _calculate_quotes(self, symbol: str) -> Tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
        s_cfg = self.symbol_configs[symbol]
        
        # 1. Get Reference Price
        if s_cfg.orderbook_analysis.wap_instead_of_mid:
            ref_price = self._get_weighted_average_price(symbol)
        else:
            ref_price = self._get_mid_price(symbol)
        
        if ref_price is None: return None, None, None, None

        # 2. Determine Trading Bias
        bias = self._get_directional_bias(symbol)
        self.logger.debug(f"{symbol} bias: {bias.value}")

        # 3. Calculate Quantities
        base_qty = Decimal(str(s_cfg.order_amount))
        is_bid_cliff, is_ask_cliff = self._analyze_liquidity_cliffs(symbol)
        if is_bid_cliff: base_qty *= Decimal('0.5')
        if is_ask_cliff: base_qty *= Decimal('0.5')
        
        bid_qty = self.round_quantity(symbol, base_qty)
        ask_qty = self.round_quantity(symbol, base_qty)

        # 4. Directional "Taker" Logic
        if bias == TradingBias.STRONG_BULLISH:
            self.logger.info(f"STRONG BULLISH signal for {symbol}. Placing aggressive bid.")
            bid_price = self.round_price(symbol, ref_price * Decimal('1.0001')) # Slightly above WAP
            return bid_price, None, bid_qty, None
        
        if bias == TradingBias.STRONG_BEARISH:
            self.logger.info(f"STRONG BEARISH signal for {symbol}. Placing aggressive ask.")
            ask_price = self.round_price(symbol, ref_price * Decimal('0.9999')) # Slightly below WAP
            return None, ask_price, None, ask_qty

        # 5. Market-Making Logic (for NEUTRAL or WEAK bias)
        # Base Spread
        spread = Decimal(str(s_cfg.base_spread))
        
        # Adjust spread for market conditions
        market_spread_pct, _ = self._get_market_spread(symbol)
        if market_spread_pct:
            spread = max(spread, market_spread_pct * Decimal('0.8'))
        
        is_toxic_on_bid, is_toxic_on_ask = self._detect_toxic_flow(symbol)
        if is_toxic_on_bid or is_toxic_on_ask:
            spread *= Decimal(str(s_cfg.orderbook_analysis.toxic_spread_widener))
        
        spread = min(spread, Decimal(str(s_cfg.max_spread)))
        half_spread = spread / 2

        # Calculate Skews
        # Inventory Skew
        inventory_pct = self.positions[symbol] / Decimal(str(s_cfg.inventory_limit))
        inventory_skew = (Decimal(str(s_cfg.inventory_skew.skew_factor)) * inventory_pct) * spread
        
        # Orderbook Imbalance Skew
        imbalance = self._calculate_orderbook_imbalance(symbol)
        imbalance_skew = DECIMAL_ZERO
        if imbalance:
            normalized_imbalance = imbalance - Decimal('0.5')
            imbalance_skew = spread * normalized_imbalance * Decimal(str(s_cfg.orderbook_analysis.obi_impact_factor))

        # Directional Signal Skew (for WEAK bias)
        directional_skew = DECIMAL_ZERO
        if bias == TradingBias.WEAK_BULLISH:
            directional_skew = -spread * Decimal(str(s_cfg.signal_config.signal_bias_strength))
        elif bias == TradingBias.WEAK_BEARISH:
            directional_skew = spread * Decimal(str(s_cfg.signal_config.signal_bias_strength))

        # Total Skew
        total_skew = inventory_skew + imbalance_skew + directional_skew

        # Final Prices
        bid_price = ref_price * (Decimal('1') - half_spread) + total_skew
        ask_price = ref_price * (Decimal('1') + half_spread) + total_skew

        return self.round_price(symbol, bid_price), self.round_price(symbol, ask_price), bid_qty, ask_qty

    @retry_api_call()
    def _fetch_data(self):
        # Positions
        positions_data = self.exchange.fetch_positions(params={'category': self.global_config.category})
        current_positions = {p['info']['symbol']: Decimal(p['contracts']) for p in positions_data if Decimal(p.get('contracts', 0)) != 0}
        for symbol in self.symbol_configs:
            self.positions[symbol] = current_positions.get(symbol, DECIMAL_ZERO)

        # Open Orders
        for symbol in self.symbol_configs:
            self.open_orders[symbol] = self.exchange.fetch_open_orders(symbol)

        # Kline data
        for symbol, s_cfg in self.symbol_configs.items():
            limit = max(s_cfg.dynamic_spread.bb_period, s_cfg.signal_config.rsi_period, s_cfg.signal_config.macd_slow) + 5
            klines = self.exchange.fetch_ohlcv(symbol, timeframe=s_cfg.kline_interval, limit=limit)
            df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col])
            self.kline_data[symbol] = df

    def _update_status(self):
        self._process_ws_messages()
        
        for symbol, s_cfg in self.symbol_configs.items():
            if not s_cfg.trade_enabled: continue

            if time.time() - self.last_market_data_time[symbol] > s_cfg.market_data_stale_timeout_seconds:
                self.logger.warning(f"Market data for {symbol} is stale. Skipping cycle.")
                continue
            
            self._update_technical_signals(symbol)
            quotes = self._calculate_quotes(symbol)
            self._reconcile_orders(symbol, *quotes)

    def _reconcile_orders(self, symbol: str, bid_price: Optional[Decimal], ask_price: Optional[Decimal], bid_qty: Optional[Decimal], ask_qty: Optional[Decimal]):
        s_cfg = self.symbol_configs[symbol]
        
        if self.open_orders[symbol]:
            try:
                self.exchange.cancel_all_orders(symbol)
                self.logger.debug(f"Cancelled {len(self.open_orders[symbol])} open orders for {symbol}.")
            except Exception as e:
                self.logger.error(f"Failed to cancel orders for {symbol}: {e}")

        orders_to_place = []
        if bid_price and bid_qty and bid_qty > s_cfg.min_qty:
            orders_to_place.append({'symbol': symbol, 'type': 'limit', 'side': 'buy', 'amount': float(bid_qty), 'price': float(bid_price)})
        
        if ask_price and ask_qty and ask_qty > s_cfg.min_qty:
            orders_to_place.append({'symbol': symbol, 'type': 'limit', 'side': 'sell', 'amount': float(ask_qty), 'price': float(ask_price)})

        if orders_to_place:
            self.logger.info(f"Placing new orders for {symbol}: {orders_to_place}")
            try:
                if s_cfg.use_batch_orders_for_refresh and len(orders_to_place) > 1:
                    self.exchange.create_orders(orders_to_place)
                else:
                    for order in orders_to_place:
                        self.exchange.create_order(**order)
            except Exception as e:
                self.logger.error(f"Failed to place new orders for {symbol}: {e}")

    def round_price(self, symbol: str, price: Decimal) -> Decimal:
        s_cfg = self.symbol_configs[symbol]
        return (price / s_cfg.tick_size).quantize(DECIMAL_ZERO, rounding=ROUND_HALF_UP) * s_cfg.tick_size

    def round_quantity(self, symbol: str, quantity: Decimal) -> Decimal:
        s_cfg = self.symbol_configs[symbol]
        return quantity.quantize(Decimal(str(10 ** -s_cfg.qty_precision)), rounding=ROUND_HALF_UP)

    def run(self):
        self._setup_signal_handler()
        self.logger.info("Starting Hybrid Market Maker Bot...")
        self.notifier.send_message("🚀 Hybrid Market Maker Bot Started")
        
        self._load_state()
        self._update_symbol_info()
        self.ws_client.start()

        last_status_update = 0
        last_symbol_info_update = time.time()

        while self.running:
            try:
                now = time.time()

                if now - last_status_update > STATUS_UPDATE_INTERVAL:
                    self._fetch_data()
                    last_status_update = now
                
                self._update_status()

                if now - last_symbol_info_update > SYMBOL_INFO_REFRESH_INTERVAL:
                    self._update_symbol_info()
                    last_symbol_info_update = now

                time.sleep(MAIN_LOOP_SLEEP_INTERVAL)

            except KeyboardInterrupt:
                self.running = False
            except Exception as e:
                self.logger.critical(f"An unhandled error occurred in the main loop: {e}", exc_info=True)
                self.notifier.send_message(f"CRITICAL ERROR: {e}")
                time.sleep(10)

        self.logger.info("Shutting down... Cancelling all open orders.")
        self.ws_client.stop()
        for symbol in self.symbol_configs:
            try:
                self.exchange.cancel_all_orders(symbol)
                self.logger.info(f"Cancelled all orders for {symbol}.")
            except Exception as e:
                self.logger.error(f"Error cancelling orders for {symbol} on shutdown: {e}")
        
        self._save_state()
        self.logger.info("Bot has been shut down.")
        self.notifier.send_message("🛑 Hybrid Market Maker Bot Stopped")
# endregion

# region: Main Execution Block
# ==============================================================================
def main():
    """Main function to run the bot."""
    parser = argparse.ArgumentParser(description="Hybrid Bybit Market Maker Bot")
    parser.add_argument("--symbol", type=str, help="Run the bot for a single symbol, ignoring the config file.")
    args = parser.parse_args()

    global GLOBAL_CONFIG, SYMBOL_CONFIGS
    GLOBAL_CONFIG, SYMBOL_CONFIGS = ConfigManager.load_config(
        prompt_for_symbol=bool(args.symbol),
        input_symbol=args.symbol
    )

    global main_logger
    main_logger = setup_logger("main")

    if not SYMBOL_CONFIGS:
        main_logger.critical("No symbols configured. Please add symbols to your symbols.json or use the --symbol flag. Exiting.")
        sys.exit(1)

    exchange = initialize_exchange(main_logger)
    if not exchange:
        sys.exit(1)

    strategy = EnhancedMarketMakerStrategy(GLOBAL_CONFIG, SYMBOL_CONFIGS, exchange)
    strategy.run()

if __name__ == "__main__":
    if not EXTERNAL_LIBS_AVAILABLE:
        sys.exit(1)
    main()
# endregion
