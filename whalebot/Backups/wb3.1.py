import json
import logging
import os
import queue
import sys
import threading
import time
from collections import defaultdict
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal, getcontext
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, ClassVar, Literal

import numpy as np
import pandas as pd
from colorama import Fore, Style, init
from dotenv import load_dotenv

# Pybit specific imports
from pybit.exceptions import FailedRequestError, InvalidRequestError
from pybit.unified_trading import HTTP
from pybit.unified_trading import WebSocket as UnifiedWebSocket

# Scikit-learn is explicitly excluded as per user request.
SKLEARN_AVAILABLE = False

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

# Indicator specific colors (enhanced for new indicators)
INDICATOR_COLORS = {
    "SMA_10": Fore.LIGHTBLUE_EX,
    "SMA_Long": Fore.BLUE,
    "EMA_Short": Fore.LIGHTMAGENTA_EX,
    "EMA_Long": Fore.MAGENTA,
    "ATR": Fore.YELLOW,
    "RSI": Fore.GREEN,
    "StochRSI_K": Fore.CYAN,
    "StochRSI_D": Fore.LIGHTCYAN_EX,
    "BB_Upper": Fore.RED,
    "BB_Middle": Fore.WHITE,
    "BB_Lower": Fore.RED,
    "CCI": Fore.LIGHTGREEN_EX,
    "WR": Fore.LIGHTRED_EX,
    "MFI": Fore.GREEN,
    "OBV": Fore.BLUE,
    "OBV_EMA": Fore.LIGHTBLUE_EX,
    "CMF": Fore.MAGENTA,
    "Tenkan_Sen": Fore.CYAN,
    "Kijun_Sen": Fore.LIGHTCYAN_EX,
    "Senkou_Span_A": Fore.GREEN,
    "Senkou_Span_B": Fore.RED,
    "Chikou_Span": Fore.YELLOW,
    "PSAR_Val": Fore.MAGENTA,
    "PSAR_Dir": Fore.LIGHTMAGENTA_EX,
    "VWAP": Fore.WHITE,
    "ST_Fast_Dir": Fore.BLUE,
    "ST_Fast_Val": Fore.LIGHTBLUE_EX,
    "ST_Slow_Dir": Fore.MAGENTA,
    "ST_Slow_Val": Fore.LIGHTMAGENTA_EX,
    "MACD_Line": Fore.GREEN,
    "MACD_Signal": Fore.LIGHTGREEN_EX,
    "MACD_Hist": Fore.YELLOW,
    "ADX": Fore.CYAN,
    "PlusDI": Fore.LIGHTCYAN_EX,
    "MinusDI": Fore.RED,
    "Volatility_Index": Fore.YELLOW,
    "Volume_Delta": Fore.LIGHTCYAN_EX,
    "VWMA": Fore.WHITE,
}

# --- Constants ---
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
CONFIG_FILE = "config.json"
LOG_DIRECTORY = "bot_logs/trading-bot/logs"
Path(LOG_DIRECTORY).mkdir(parents=True, exist_ok=True)

# Using UTC for consistency and to avoid timezone issues with API timestamps
TIMEZONE = UTC
LOOP_DELAY_SECONDS = 15

# Magic Numbers as Constants (expanded)
MIN_DATA_POINTS_TR = 2
MIN_DATA_POINTS_SMOOTHER = 2
MIN_DATA_POINTS_OBV = 2
MIN_DATA_POINTS_PSAR = 2
ADX_STRONG_TREND_THRESHOLD = 25
ADX_WEAK_TREND_THRESHOLD = 20
MIN_DATA_POINTS_VWMA = 2
MIN_DATA_POINTS_VOLATILITY = 2


# --- Configuration Management ---
def load_config(filepath: str, logger: logging.Logger) -> dict[str, Any]:
    """Load configuration from JSON file, creating a default if not found."""
    default_config = {
        # Core Settings
        "symbol": "BTCUSDT",
        "interval": "15",  # Changed "15m" to "15" to match Bybit API requirement
        "loop_delay": LOOP_DELAY_SECONDS,
        "orderbook_limit": 50,
        # Signal Generation
        "signal_score_threshold": 2.0,
        "volume_confirmation_multiplier": 1.5,
        # Position & Risk Management
        "trade_management": {
            "enabled": True,
            "account_balance": 1000.0,
            "risk_per_trade_percent": 1.0,
            "stop_loss_atr_multiple": 1.5,
            "take_profit_atr_multiple": 2.0,
            "max_open_positions": 1,
            "order_precision": 5,  # New: Decimal places for order quantity
            "price_precision": 3,  # New: Decimal places for price
        },
        # Multi-Timeframe Analysis
        "mtf_analysis": {
            "enabled": True,
            "higher_timeframes": ["60", "240"],  # Changed "1h", "4h" to "60", "240"
            "trend_indicators": ["ema", "ehlers_supertrend"],
            "trend_period": 50,
            "mtf_request_delay_seconds": 0.5,
        },
        # Machine Learning Enhancement (Explicitly disabled)
        "ml_enhancement": {
            "enabled": False,  # ML explicitly disabled
            "model_path": "ml_model.pkl",
            "retrain_on_startup": False,
            "training_data_limit": 5000,
            "prediction_lookahead": 12,
            "profit_target_percent": 0.5,
            "feature_lags": [1, 2, 3, 5],
            "cross_validation_folds": 5,
        },
        # Indicator Periods & Thresholds
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
            "ehlers_fast_period": 10,
            "ehlers_fast_multiplier": 2.0,
            "ehlers_slow_period": 20,
            "ehlers_slow_multiplier": 3.0,
            "macd_fast_period": 12,
            "macd_slow_period": 26,
            "macd_signal_period": 9,
            "adx_period": 14,
            "ichimoku_tenkan_period": 9,
            "ichimoku_kijun_period": 26,
            "ichimoku_senkou_span_b_period": 52,
            "ichimoku_chikou_span_offset": 26,
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
            "volatility_index_period": 20,  # New: Volatility Index Period
            "vwma_period": 20,  # New: VWMA Period
            "volume_delta_period": 5,  # New: Volume Delta Period
            "volume_delta_threshold": 0.2,  # New: Volume Delta Threshold for signals
        },
        # Active Indicators & Weights (expanded)
        "indicators": {
            "ema_alignment": True,
            "sma_trend_filter": True,
            "momentum": True,  # Now a general category, individual momentum indicators are sub-checked
            "volume_confirmation": True,
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
            "macd": True,
            "adx": True,
            "ichimoku_cloud": True,
            "obv": True,
            "cmf": True,
            "volatility_index": True,  # New
            "vwma": True,  # New
            "volume_delta": True,  # New
        },
        "weight_sets": {
            "default_scalping": {
                "ema_alignment": 0.22,
                "sma_trend_filter": 0.28,
                "momentum_rsi_stoch_cci_wr_mfi": 0.18,  # Combined weight for momentum
                "volume_confirmation": 0.12,
                "bollinger_bands": 0.22,
                "vwap": 0.22,
                "psar": 0.22,
                "sma_10": 0.07,
                "orderbook_imbalance": 0.07,
                "ehlers_supertrend_alignment": 0.55,
                "macd_alignment": 0.28,
                "adx_strength": 0.18,
                "ichimoku_confluence": 0.38,
                "obv_momentum": 0.18,
                "cmf_flow": 0.12,
                "mtf_trend_confluence": 0.32,
                "volatility_index_signal": 0.15,  # New
                "vwma_cross": 0.15,  # New
                "volume_delta_signal": 0.10,  # New
            },
        },
    }
    if not Path(filepath).exists():
        try:
            with Path(filepath).open("w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)
            logger.warning(
                f"{NEON_YELLOW}Configuration file not found. Created default config at {filepath} for symbol {default_config['symbol']}{RESET}",
            )
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
    except (OSError, FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(
            f"{NEON_RED}Error loading config: {e}. Using default and attempting to save.{RESET}",
        )
        try:
            with Path(filepath).open("w", encoding="utf-8") as f_default:
                json.dump(default_config, f_default, indent=4)
        except OSError as e_save:
            logger.error(f"{NEON_RED}Could not save default config: {e_save}{RESET}")
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

    def __init__(self, fmt=None, datefmt=None, style="%"):
        """Initializes the SensitiveFormatter."""
        super().__init__(fmt, datefmt, style)
        self._fmt = fmt if fmt else self.default_fmt()

    def default_fmt(self):
        """Returns the default log format string."""
        return "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    def format(self, record):
        """Formats the log record, redacting sensitive words."""
        original_message = super().format(record)
        redacted_message = original_message
        for word in self.SENSITIVE_WORDS:
            if word in redacted_message:
                redacted_message = redacted_message.replace(word, "*" * len(word))
        return redacted_message


def setup_logger(log_name: str, level=logging.INFO) -> logging.Logger:
    """Configure and return a logger with file and console handlers."""
    logger = logging.getLogger(log_name)
    logger.setLevel(level)
    logger.propagate = False

    # Ensure handlers are not duplicated
    if not logger.handlers:
        # Console Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(
            SensitiveFormatter(
                f"{NEON_BLUE}%(asctime)s - %(levelname)s - %(message)s{RESET}",
            ),
        )
        logger.addHandler(console_handler)

        # File Handler
        log_file = Path(LOG_DIRECTORY) / f"{log_name}.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
        )
        file_handler.setFormatter(
            SensitiveFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
        )
        logger.addHandler(file_handler)

    return logger


# --- Pybit API Helper Functions ---
def create_pybit_client(testnet: bool = False) -> HTTP:
    """Creates a pybit HTTP client with API credentials."""
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    if not api_key or not api_secret:
        logger = logging.getLogger("WgwhalexTradingBot")
        logger.error("API_KEY and API_SECRET must be set in environment variables.")
        raise ValueError("API_KEY and API_SECRET must be set in environment variables.")
    return HTTP(testnet=testnet, api_key=api_key, api_secret=api_secret)


def get_account_balance_pybit(
    client: HTTP,
    coin: str,
    logger: logging.Logger,
) -> Decimal | None:
    """Fetches current account balance for a specific coin using pybit."""
    try:
        response = client.get_wallet_balance(accountType="UNIFIED", coin=coin)
        if response["retCode"] == 0 and response["result"]["list"]:
            for item in response["result"]["list"]:
                for c in item["coin"]:
                    if c["coin"] == coin:
                        balance = Decimal(c["walletBalance"])
                        logger.debug(f"Fetched {coin} balance: {balance}")
                        return balance
        logger.warning(f"{NEON_YELLOW}Could not fetch {coin} balance.{RESET}")
        return None
    except (FailedRequestError, InvalidRequestError) as e:
        logger.error(f"{NEON_RED}Pybit error fetching balance: {e}{RESET}")
        return None
    except Exception as e:
        logger.error(f"{NEON_RED}Error fetching balance: {e}{RESET}")
        return None


def get_positions_pybit(
    client: HTTP,
    symbol: str,
    logger: logging.Logger,
) -> list[dict]:
    """Fetches open positions for a symbol using pybit."""
    try:
        response = client.get_positions(category="linear", symbol=symbol)
        if response["retCode"] == 0 and response["result"]["list"]:
            positions = response["result"]["list"]
            logger.debug(f"Fetched {len(positions)} positions for {symbol}.")
            return positions
        logger.debug(f"No open positions found for {symbol}.")
        return []
    except (FailedRequestError, InvalidRequestError) as e:
        logger.error(f"{NEON_RED}Pybit error fetching positions: {e}{RESET}")
        return []
    except Exception as e:
        logger.error(f"{NEON_RED}Error fetching positions: {e}{RESET}")
        return []


def place_order_with_sl_tp_pybit(
    client: HTTP,
    symbol: str,
    side: Literal["Buy", "Sell"],
    qty: Decimal,
    stop_loss: Decimal,
    take_profit: Decimal,
    logger: logging.Logger,
) -> dict | None:
    """Places a market order with Stop Loss and Take Profit using pybit."""
    try:
        response = client.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            orderType="Market",
            qty=str(qty.normalize()),
            setTpSlMode="Full",  # TP/SL applies to the entire position
            stopLoss=str(stop_loss.normalize()),
            takeProfit=str(take_profit.normalize()),
            isLeverage=1,  # Use leverage
            timeInForce="GTC",
        )
        if response["retCode"] == 0:
            logger.info(
                f"{NEON_GREEN}Order placed: {side} {qty.normalize()} {symbol} "
                f"SL: {stop_loss.normalize()}, TP: {take_profit.normalize()}{RESET}",
            )
            return response["result"]
        logger.error(
            f"{NEON_RED}Failed to place order: {response.get('retMsg')} (Code: {response.get('retCode')}){RESET}",
        )
        return None
    except (FailedRequestError, InvalidRequestError) as e:
        logger.error(f"{NEON_RED}Pybit error placing order: {e}{RESET}")
        return None
    except Exception as e:
        logger.error(f"{NEON_RED}Error placing order: {e}{RESET}")
        return None


def cancel_all_orders_pybit(
    client: HTTP,
    symbol: str | None,
    logger: logging.Logger,
) -> bool:
    """Cancels all open orders for a symbol using pybit."""
    try:
        params = {"category": "linear"}
        if symbol:
            params["symbol"] = symbol

        response = client.cancel_all_orders(**params)

        if response["retCode"] == 0:
            logger.info(
                f"All orders cancelled for {symbol if symbol else 'all symbols'}",
            )
            return True
        logger.error(f"Failed to cancel all orders: {response['retMsg']}")
        return False

    except (FailedRequestError, InvalidRequestError) as e:
        logger.error(f"Pybit error cancelling orders: {e}")
        return False
    except Exception as e:
        logger.error(f"Error cancelling orders: {e}")
        return False


# --- Alert System ---
class AlertSystem:
    """Handles sending alerts for critical events."""

    def __init__(self, config: dict[str, Any], logger: logging.Logger):
        """Initializes the AlertSystem."""
        self.logger = logger
        self.config = config  # Keep config for potential future integrations (e.g., Telegram API keys)

    def send_alert(
        self,
        message: str,
        level: Literal["INFO", "WARNING", "ERROR"],
    ) -> None:
        """Send an alert (currently logs it)."""
        if level == "INFO":
            self.logger.info(f"{NEON_BLUE}ALERT: {message}{RESET}")
        elif level == "WARNING":
            self.logger.warning(f"{NEON_YELLOW}ALERT: {message}{RESET}")
        elif level == "ERROR":
            self.logger.error(f"{NEON_RED}ALERT: {message}{RESET}")
        # In a real bot, integrate with Telegram, Discord, Email etc.


# --- Performance Tracking ---
class PerformanceTracker:
    """Tracks and reports trading performance."""

    def __init__(self, logger: logging.Logger):
        """Initializes the PerformanceTracker."""
        self.logger = logger
        self.trades: list[dict] = []
        self.total_pnl = Decimal("0")
        self.wins = 0
        self.losses = 0

    def record_trade(self, position: dict, pnl: Decimal) -> None:
        """Record a completed trade.
        Note: In a real Pybit integration, this would be called by WebSocket
        execution updates or by polling trade history, not directly by PositionManager.
        """
        trade_record = {
            "entry_time": position.get("entry_time", datetime.now(TIMEZONE)),
            "exit_time": position.get("exit_time", datetime.now(TIMEZONE)),
            "symbol": position["symbol"],
            "side": position["side"],
            "entry_price": position["entry_price"],
            "exit_price": position["exit_price"],
            "qty": position["qty"],
            "pnl": pnl,
            "closed_by": position.get("closed_by", "UNKNOWN"),
        }
        self.trades.append(trade_record)
        self.total_pnl += pnl
        if pnl > 0:
            self.wins += 1
        else:
            self.losses += 1
        self.logger.info(
            f"{NEON_CYAN}[{position['symbol']}] Trade recorded. Current Total PnL: {self.total_pnl.normalize():.2f}, Wins: {self.wins}, Losses: {self.losses}{RESET}",
        )

    def get_summary(self) -> dict:
        """Return a summary of all recorded trades."""
        total_trades = len(self.trades)
        win_rate = (self.wins / total_trades) * 100 if total_trades > 0 else 0

        return {
            "total_trades": total_trades,
            "total_pnl": self.total_pnl,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": f"{win_rate:.2f}%",
        }


# --- WebSocket Management ---
class BybitWebSocketManager:
    """Manages WebSocket connections for real-time data and order updates."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = False,
        logger=None,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.logger = logger if logger else setup_logger("ws_manager")
        self.ws_public = None
        self.ws_private = None
        self.data_queue = queue.Queue()
        self.kline_buffer: dict[str, list[dict]] = defaultdict(
            list,
        )  # {symbol_interval: [kline_data]}
        self.orderbook_snapshot: dict[str, dict] = {}  # {symbol: {bids: [], asks: []}}
        self.ticker_data: dict[
            str,
            dict,
        ] = {}  # {symbol: {last_price: Decimal, bid: Decimal, ask: Decimal}}

    def start_public_websocket_thread(self, symbol: str, interval: str):
        """Starts a thread for public WebSocket connection."""
        self.logger.info(
            f"Starting public WebSocket thread for {symbol} interval {interval}",
        )
        thread = threading.Thread(
            target=self._connect_public_websocket_loop,
            args=(symbol, interval),
            daemon=True,
        )
        thread.start()
        return thread

    def start_private_websocket_thread(self, position_tracker_callbacks: dict):
        """Starts a thread for private WebSocket connection."""
        self.logger.info("Starting private WebSocket thread.")
        thread = threading.Thread(
            target=self._connect_private_websocket_loop,
            args=(position_tracker_callbacks,),
            daemon=True,
        )
        thread.start()
        return thread

    def _connect_public_websocket_loop(self, symbol: str, interval: str):
        """Internal method to run public WebSocket connection in a thread."""
        while True:
            try:
                self.ws_public = UnifiedWebSocket(
                    testnet=self.testnet,
                    channel_type="linear",
                )

                # Subscribe to multiple public topics
                self.ws_public.kline_stream(
                    interval=interval,  # Use configured interval
                    symbol=symbol,
                    callback=self.handle_kline,
                )

                self.ws_public.orderbook_stream(
                    depth=50,
                    symbol=symbol,
                    callback=self.handle_orderbook,
                )

                self.ws_public.ticker_stream(symbol=symbol, callback=self.handle_ticker)
                self.logger.info(
                    f"Public WebSocket connected for {symbol} interval {interval}",
                )
                while True:
                    time.sleep(1)
            except Exception as e:
                self.logger.error(f"Public WebSocket error: {e}. Reconnecting in 5s...")
                time.sleep(5)

    def _connect_private_websocket_loop(self, position_tracker_callbacks: dict):
        """Internal method to run private WebSocket connection in a thread."""
        while True:
            try:
                self.ws_private = UnifiedWebSocket(
                    testnet=self.testnet,
                    channel_type="private",
                    api_key=self.api_key,
                    api_secret=self.api_secret,
                )

                # Subscribe to private topics, passing tracker's methods as callbacks
                self.ws_private.position_stream(
                    callback=position_tracker_callbacks["position_update"],
                )
                self.ws_private.order_stream(
                    callback=position_tracker_callbacks["order_update"],
                )
                self.ws_private.execution_stream(
                    callback=position_tracker_callbacks["execution_update"],
                )
                self.ws_private.wallet_stream(
                    callback=position_tracker_callbacks["wallet_update"],
                )
                self.logger.info("Private WebSocket connected.")
                while True:
                    time.sleep(1)
            except Exception as e:
                self.logger.error(
                    f"Private WebSocket error: {e}. Reconnecting in 5s...",
                )
                time.sleep(5)

    def handle_kline(self, message):
        """Process incoming kline data."""
        if message.get("topic", "").startswith("kline"):
            for data_item in message.get("data", []):
                # Buffer all klines (in-progress and confirmed) for real-time analysis
                kline_data = {
                    "type": "kline",
                    "timestamp": int(
                        data_item.get("start"),
                    ),  # 'start' is the timestamp
                    "open": Decimal(str(data_item.get("open", 0))),
                    "high": Decimal(str(data_item.get("high", 0))),
                    "low": Decimal(str(data_item.get("low", 0))),
                    "close": Decimal(str(data_item.get("close", 0))),
                    "volume": Decimal(str(data_item.get("volume", 0))),
                    "turnover": Decimal(str(data_item.get("turnover", 0))),
                    "interval": message["topic"].split(".")[
                        -1
                    ],  # e.g., "15" from "kline.15.BTCUSDT"
                    "symbol": message["topic"].split(".")[
                        -2
                    ],  # e.g., "BTCUSDT" from "kline.15.BTCUSDT"
                    "confirm": data_item.get(
                        "confirm",
                    ),  # True for finished, False for in-progress
                }
                key = f"{kline_data['symbol']}_{kline_data['interval']}"
                self.kline_buffer[key].append(kline_data)
                # Trim buffer to maintain a reasonable size for indicator calculation
                if len(self.kline_buffer[key]) > 1500:  # Keep more data for indicators
                    self.kline_buffer[key].pop(0)
                self.data_queue.put(kline_data)  # Also put in general queue if needed

    def handle_orderbook(self, message):
        """Process orderbook updates."""
        if message.get("topic", "").startswith("orderbook"):
            data = message.get("data")
            symbol = message["topic"].split(".")[-1]  # Extract symbol from topic
            if data and symbol:
                # Pybit WS handles orderbook deltas internally to provide a full snapshot to the callback
                orderbook_data = {
                    "type": "orderbook",
                    "bids": data.get("b", []),
                    "asks": data.get("a", []),
                    "timestamp": message.get("ts"),
                    "symbol": symbol,
                }
                self.orderbook_snapshot[symbol] = orderbook_data
                self.data_queue.put(orderbook_data)

    def handle_ticker(self, message):
        """Process ticker updates for real-time price."""
        if message.get("topic", "").startswith("tickers"):
            data = message.get("data")
            symbol = message["topic"].split(".")[-1]  # Extract symbol from topic
            if data and symbol:
                ticker_data = {
                    "type": "ticker",
                    "last_price": Decimal(str(data.get("lastPrice", 0))),
                    "bid": Decimal(str(data.get("bid1Price", 0))),
                    "ask": Decimal(str(data.get("ask1Price", 0))),
                    "volume_24h": Decimal(str(data.get("volume24h", 0))),
                    "symbol": symbol,
                }
                self.ticker_data[symbol] = ticker_data
                self.data_queue.put(ticker_data)

    def get_kline_df(self, symbol: str, interval: str) -> pd.DataFrame | None:
        """Convert kline buffer to DataFrame."""
        key = f"{symbol}_{interval}"
        buffer = self.kline_buffer.get(key)
        if not buffer:
            return None
        df = pd.DataFrame(buffer)
        df["start_time"] = pd.to_datetime(
            df["timestamp"].astype(int),
            unit="ms",
            utc=True,
        ).dt.tz_convert(TIMEZONE)
        for col in ["open", "high", "low", "close", "volume", "turnover"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df.set_index("start_time", inplace=True)
        df.sort_index(inplace=True)
        return df

    def get_current_price(self, symbol: str) -> Decimal | None:
        """Get current price from ticker data."""
        ticker = self.ticker_data.get(symbol)
        return ticker.get("last_price") if ticker else None

    def get_orderbook(self, symbol: str) -> dict | None:
        """Get current orderbook snapshot."""
        return self.orderbook_snapshot.get(symbol)


class RealTimePositionTracker:
    """Tracks positions in real-time using WebSocket updates and HTTP for initial/fallback."""

    def __init__(self, ws_manager: BybitWebSocketManager, session: HTTP, logger):
        self.ws_manager = ws_manager
        self.session = session
        self.logger = logger
        self.positions: dict[str, dict] = {}  # {symbol: position_details}
        self.orders: dict[str, dict] = {}  # {order_id: order_details}
        self.wallet_balance: Decimal = Decimal("0")
        self.update_lock = threading.Lock()  # To prevent race conditions on shared data

    def get_account_balance(self, coin: str = "USDT") -> Decimal:
        """Get current account balance for specified coin using HTTP, or cached if available."""
        # Prioritize cached balance from WebSocket if recent enough, otherwise use HTTP.
        # For simplicity, we'll just use HTTP here as a direct call.
        return get_account_balance_pybit(self.session, coin, self.logger)

    def get_open_positions(self, symbol: str = None) -> list[dict]:
        """Get current open positions using HTTP, or cached if available."""
        # For simplicity, we'll just use HTTP here as a direct call.
        return get_positions_pybit(self.session, symbol, self.logger)

    def cancel_all_orders(self, symbol: str = None) -> bool:
        """Cancel all open orders for a symbol."""
        return cancel_all_orders_pybit(self.session, symbol, self.logger)

    # WebSocket callback handlers
    def handle_position_update(self, message):
        """Process incoming position updates from WebSocket."""
        with self.update_lock:
            for data in message.get("data", []):
                symbol = data.get("symbol")
                size = Decimal(data.get("size", "0"))
                if symbol:
                    if size > 0:  # Position open or updated
                        self.positions[symbol] = {
                            "symbol": symbol,
                            "side": data.get("side"),
                            "size": size,
                            "avg_price": Decimal(data.get("avgPrice", "0")),
                            "unrealized_pnl": Decimal(data.get("unrealisedPnl", "0")),
                            "leverage": Decimal(data.get("leverage", "1")),
                        }
                        self.logger.debug(
                            f"WS Position update for {symbol}: {self.positions[symbol]}",
                        )
                    elif symbol in self.positions:  # Position closed
                        self.logger.info(
                            f"WS Position for {symbol} closed. Old data: {self.positions.pop(symbol)}",
                        )

    def handle_order_update(self, message):
        """Process incoming order updates from WebSocket."""
        with self.update_lock:
            for data in message.get("data", []):
                order_id = data.get("orderId")
                self.orders[order_id] = data  # Store full order details
                self.logger.debug(f"WS Order update for {order_id}: {data}")

    def handle_execution(self, message):
        """Process incoming execution (trade) updates from WebSocket."""
        with self.update_lock:
            for data in message.get("data", []):
                self.logger.info(f"WS Execution update: {data}")
                # This is where you would link trades to your performance tracker
                # e.g., performance_tracker.record_trade(...)
                # For this example, we'll keep performance_tracker separate and manually updated.

    def handle_wallet_update(self, message):
        """Process incoming wallet balance updates from WebSocket."""
        with self.update_lock:
            for data in message.get("data", []):
                for coin_data in data.get("coin", []):
                    if coin_data.get("coin") == "USDT":
                        self.wallet_balance = Decimal(
                            coin_data.get("walletBalance", "0"),
                        )
                        self.logger.debug(
                            f"WS Wallet balance updated to {self.wallet_balance} USDT",
                        )
                        break


class PositionManagerPybit:
    """Manages positions using pybit API."""

    def __init__(self, config: dict[str, Any], logger: logging.Logger, symbol: str):
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.client = create_pybit_client(testnet=False)  # Set to True for testnet
        self.trade_management_enabled = config["trade_management"]["enabled"]
        self.max_open_positions = config["trade_management"]["max_open_positions"]
        self.order_precision = config["trade_management"]["order_precision"]
        self.price_precision = config["trade_management"]["price_precision"]

    def _get_current_balance(self) -> Decimal:
        """Fetch current account balance using pybit."""
        balance = get_account_balance_pybit(self.client, "USDT", self.logger)
        if balance:
            return balance
        # Fallback to config value if API fails
        return Decimal(str(self.config["trade_management"]["account_balance"]))

    def _calculate_order_size(
        self,
        current_price: Decimal,
        atr_value: Decimal,
    ) -> Decimal:
        """Calculate order size based on risk per trade and ATR."""
        if not self.trade_management_enabled:
            return Decimal("0")

        account_balance = self._get_current_balance()
        risk_per_trade_percent = (
            Decimal(str(self.config["trade_management"]["risk_per_trade_percent"]))
            / 100
        )
        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"]),
        )

        risk_amount = account_balance * risk_per_trade_percent
        stop_loss_distance = atr_value * stop_loss_atr_multiple

        if stop_loss_distance <= 0:
            self.logger.warning(
                f"{NEON_YELLOW}Invalid stop loss distance. Cannot determine order size.{RESET}",
            )
            return Decimal("0")

        order_value = risk_amount / stop_loss_distance
        order_qty = order_value / current_price

        # Round to appropriate precision
        precision_str = "0." + "0" * (self.order_precision - 1) + "1"
        order_qty = order_qty.quantize(Decimal(precision_str), rounding=ROUND_DOWN)

        self.logger.info(
            f"[{self.symbol}] Calculated order size: {order_qty.normalize()} "
            f"(Risk: {risk_amount.normalize():.2f} USD)",
        )
        return order_qty

    def open_position(
        self,
        signal: str,
        current_price: Decimal,
        atr_value: Decimal,
    ) -> dict | None:
        """Open a new position using pybit."""
        if not self.trade_management_enabled:
            self.logger.info(
                f"{NEON_YELLOW}[{self.symbol}] Trade management disabled.{RESET}",
            )
            return None

        # Check current positions
        positions = get_positions_pybit(self.client, self.symbol, self.logger)
        open_positions = [p for p in positions if Decimal(p["size"]) > 0]
        if len(open_positions) >= self.max_open_positions:
            self.logger.info(
                f"{NEON_YELLOW}[{self.symbol}] Max open positions ({self.max_open_positions}) reached. Cannot open new position.{RESET}",
            )
            return None

        order_qty = self._calculate_order_size(current_price, atr_value)
        if order_qty <= 0:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Invalid order quantity. Cannot open position.{RESET}",
            )
            return None

        # Calculate SL/TP
        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"]),
        )
        take_profit_atr_multiple = Decimal(
            str(self.config["trade_management"]["take_profit_atr_multiple"]),
        )

        if signal == "BUY":
            side = "Buy"
            stop_loss = current_price - (atr_value * stop_loss_atr_multiple)
            take_profit = current_price + (atr_value * take_profit_atr_multiple)
        else:  # SELL
            side = "Sell"
            stop_loss = current_price + (atr_value * stop_loss_atr_multiple)
            take_profit = current_price - (atr_value * take_profit_atr_multiple)

        # Apply price precision
        price_precision_str = "0." + "0" * (self.price_precision - 1) + "1"
        stop_loss = stop_loss.quantize(
            Decimal(price_precision_str),
            rounding=ROUND_DOWN,
        )
        take_profit = take_profit.quantize(
            Decimal(price_precision_str),
            rounding=ROUND_DOWN,
        )

        # Place order with SL/TP
        result = place_order_with_sl_tp_pybit(
            self.client,
            self.symbol,
            side,
            order_qty,
            stop_loss=stop_loss,
            take_profit=take_profit,
            logger=self.logger,
        )

        if result:
            self.logger.info(
                f"{NEON_GREEN}[{self.symbol}] Opened {signal} position via pybit{RESET}",
            )

        return result

    def manage_positions(
        self,
        current_price: Decimal,
        performance_tracker: Any,
    ) -> None:
        """Check and manage open positions using pybit.
        Note: This function primarily monitors positions. SL/TP are managed by Bybit.
        Performance tracking for real trades should be integrated with WebSocket execution stream.
        """
        if not self.trade_management_enabled:
            return

        # Fetch positions to get latest status (though WS is more real-time)
        positions = get_positions_pybit(self.client, self.symbol, self.logger)
        open_positions = [p for p in positions if Decimal(p["size"]) > 0]

        for position in open_positions:
            side = position["side"]
            entry_price = Decimal(position["avgPrice"])
            unrealized_pnl = Decimal(position["unrealisedPnl"])
            size = Decimal(position["size"])

            self.logger.debug(
                f"[{self.symbol}] Open Position: {side} {size} @ {entry_price}, "
                f"Unrealized PnL: {unrealized_pnl}",
            )
            # No explicit closure logic here, as SL/TP are managed by Bybit if set on order.
            # This function would mainly monitor status or apply dynamic adjustments (e.g., trailing stops)
            # For real performance tracking, hook into WebSocket execution updates.


class TradingAnalyzer:
    """Analyzes trading data and generates signals with MTF, Ehlers SuperTrend, and other new indicators."""

    def __init__(
        self,
        df: pd.DataFrame,
        config: dict[str, Any],
        logger: logging.Logger,
        symbol: str,
    ):
        """Initializes the TradingAnalyzer."""
        self.df = df.copy()
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.indicator_values: dict[str, float | str | Decimal] = {}
        self.fib_levels: dict[str, Decimal] = {}
        self.weights = config["weight_sets"]["default_scalping"]
        self.indicator_settings = config["indicator_settings"]

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}TradingAnalyzer initialized with an empty DataFrame. Indicators will not be calculated.{RESET}",
            )
            return

        self._calculate_all_indicators()
        if self.config["indicators"].get("fibonacci_levels", False):
            self.calculate_fibonacci_levels()

    def _safe_calculate(
        self,
        func: callable,
        name: str,
        min_data_points: int = 0,
        *args,
        **kwargs,
    ) -> Any | None:
        """Safely calculate indicators and log errors, with min_data_points check."""
        if len(self.df) < min_data_points:
            self.logger.debug(
                f"[{self.symbol}] Skipping indicator '{name}': Not enough data. Need {min_data_points}, have {len(self.df)}.",
            )
            return None
        try:
            result = func(*args, **kwargs)
            if (
                result is None
                or (isinstance(result, pd.Series) and result.empty)
                or (
                    isinstance(result, tuple)
                    and all(
                        r is None or (isinstance(r, pd.Series) and r.empty)
                        for r in result
                    )
                )
            ):
                self.logger.warning(
                    f"{NEON_YELLOW}[{self.symbol}] Indicator '{name}' returned empty or None after calculation. Not enough valid data?{RESET}",
                )
                return None
            return result
        except Exception as e:
            self.logger.error(
                f"{NEON_RED}[{self.symbol}] Error calculating indicator '{name}': {e}{RESET}",
            )
            return None

    def _calculate_all_indicators(self) -> None:
        """Calculate all enabled technical indicators, including Ehlers SuperTrend."""
        self.logger.debug(f"[{self.symbol}] Calculating technical indicators...")
        cfg = self.config
        isd = self.indicator_settings

        # SMA
        if cfg["indicators"].get("sma_10", False):
            self.df["SMA_10"] = self._safe_calculate(
                lambda: self.df["close"].rolling(window=isd["sma_short_period"]).mean(),
                "SMA_10",
                min_data_points=isd["sma_short_period"],
            )
            if self.df["SMA_10"] is not None:
                self.indicator_values["SMA_10"] = self.df["SMA_10"].iloc[-1]
        if cfg["indicators"].get("sma_trend_filter", False):
            self.df["SMA_Long"] = self._safe_calculate(
                lambda: self.df["close"].rolling(window=isd["sma_long_period"]).mean(),
                "SMA_Long",
                min_data_points=isd["sma_long_period"],
            )
            if self.df["SMA_Long"] is not None:
                self.indicator_values["SMA_Long"] = self.df["SMA_Long"].iloc[-1]

        # EMA
        if cfg["indicators"].get("ema_alignment", False):
            self.df["EMA_Short"] = self._safe_calculate(
                lambda: self.df["close"]
                .ewm(span=isd["ema_short_period"], adjust=False)
                .mean(),
                "EMA_Short",
                min_data_points=isd["ema_short_period"],
            )
            self.df["EMA_Long"] = self._safe_calculate(
                lambda: self.df["close"]
                .ewm(span=isd["ema_long_period"], adjust=False)
                .mean(),
                "EMA_Long",
                min_data_points=isd["ema_long_period"],
            )
            if self.df["EMA_Short"] is not None:
                self.indicator_values["EMA_Short"] = self.df["EMA_Short"].iloc[-1]
            if self.df["EMA_Long"] is not None:
                self.indicator_values["EMA_Long"] = self.df["EMA_Long"].iloc[-1]

        # ATR
        self.df["TR"] = self._safe_calculate(
            self.calculate_true_range,
            "TR",
            min_data_points=MIN_DATA_POINTS_TR,
        )
        self.df["ATR"] = self._safe_calculate(
            lambda: self.df["TR"].ewm(span=isd["atr_period"], adjust=False).mean(),
            "ATR",
            min_data_points=isd["atr_period"],
        )
        if self.df["ATR"] is not None:
            self.indicator_values["ATR"] = self.df["ATR"].iloc[-1]

        # RSI
        if cfg["indicators"].get("rsi", False):
            self.df["RSI"] = self._safe_calculate(
                self.calculate_rsi,
                "RSI",
                min_data_points=isd["rsi_period"] + 1,
                period=isd["rsi_period"],
            )
            if self.df["RSI"] is not None:
                self.indicator_values["RSI"] = self.df["RSI"].iloc[-1]

        # Stochastic RSI
        if cfg["indicators"].get("stoch_rsi", False):
            stoch_rsi_k, stoch_rsi_d = self._safe_calculate(
                self.calculate_stoch_rsi,
                "StochRSI",
                min_data_points=isd["stoch_rsi_period"]
                + isd["stoch_d_period"]
                + isd["stoch_k_period"],
                period=isd["stoch_rsi_period"],
                k_period=isd["stoch_k_period"],
                d_period=isd["stoch_d_period"],
            )
            if stoch_rsi_k is not None:
                self.df["StochRSI_K"] = stoch_rsi_k
            if stoch_rsi_d is not None:
                self.df["StochRSI_D"] = stoch_rsi_d
            if stoch_rsi_k is not None:
                self.indicator_values["StochRSI_K"] = stoch_rsi_k.iloc[-1]
            if stoch_rsi_d is not None:
                self.indicator_values["StochRSI_D"] = stoch_rsi_d.iloc[-1]

        # Bollinger Bands
        if cfg["indicators"].get("bollinger_bands", False):
            bb_upper, bb_middle, bb_lower = self._safe_calculate(
                self.calculate_bollinger_bands,
                "BollingerBands",
                min_data_points=isd["bollinger_bands_period"],
                period=isd["bollinger_bands_period"],
                std_dev=isd["bollinger_bands_std_dev"],
            )
            if bb_upper is not None:
                self.df["BB_Upper"] = bb_upper
            if bb_middle is not None:
                self.df["BB_Middle"] = bb_middle
            if bb_lower is not None:
                self.df["BB_Lower"] = bb_lower
            if bb_upper is not None:
                self.indicator_values["BB_Upper"] = bb_upper.iloc[-1]
            if bb_middle is not None:
                self.indicator_values["BB_Middle"] = bb_middle.iloc[-1]
            if bb_lower is not None:
                self.indicator_values["BB_Lower"] = bb_lower.iloc[-1]

        # CCI
        if cfg["indicators"].get("cci", False):
            self.df["CCI"] = self._safe_calculate(
                self.calculate_cci,
                "CCI",
                min_data_points=isd["cci_period"],
                period=isd["cci_period"],
            )
            if self.df["CCI"] is not None:
                self.indicator_values["CCI"] = self.df["CCI"].iloc[-1]

        # Williams %R
        if cfg["indicators"].get("wr", False):
            self.df["WR"] = self._safe_calculate(
                self.calculate_williams_r,
                "WR",
                min_data_points=isd["williams_r_period"],
                period=isd["williams_r_period"],
            )
            if self.df["WR"] is not None:
                self.indicator_values["WR"] = self.df["WR"].iloc[-1]

        # MFI
        if cfg["indicators"].get("mfi", False):
            self.df["MFI"] = self._safe_calculate(
                self.calculate_mfi,
                "MFI",
                min_data_points=isd["mfi_period"] + 1,
                period=isd["mfi_period"],
            )
            if self.df["MFI"] is not None:
                self.indicator_values["MFI"] = self.df["MFI"].iloc[-1]

        # OBV
        if cfg["indicators"].get("obv", False):
            obv_val, obv_ema = self._safe_calculate(
                self.calculate_obv,
                "OBV",
                min_data_points=isd["obv_ema_period"],
                ema_period=isd["obv_ema_period"],
            )
            if obv_val is not None:
                self.df["OBV"] = obv_val
            if obv_ema is not None:
                self.df["OBV_EMA"] = obv_ema
            if obv_val is not None:
                self.indicator_values["OBV"] = obv_val.iloc[-1]
            if obv_ema is not None:
                self.indicator_values["OBV_EMA"] = obv_ema.iloc[-1]

        # CMF
        if cfg["indicators"].get("cmf", False):
            cmf_val = self._safe_calculate(
                self.calculate_cmf,
                "CMF",
                min_data_points=isd["cmf_period"],
                period=isd["cmf_period"],
            )
            if cmf_val is not None:
                self.df["CMF"] = cmf_val
            if cmf_val is not None:
                self.indicator_values["CMF"] = cmf_val.iloc[-1]

        # Ichimoku Cloud
        if cfg["indicators"].get("ichimoku_cloud", False):
            tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span = (
                self._safe_calculate(
                    self.calculate_ichimoku_cloud,
                    "IchimokuCloud",
                    min_data_points=max(
                        isd["ichimoku_tenkan_period"],
                        isd["ichimoku_kijun_period"],
                        isd["ichimoku_senkou_span_b_period"],
                    )
                    + isd["ichimoku_chikou_span_offset"],
                    tenkan_period=isd["ichimoku_tenkan_period"],
                    kijun_period=isd["ichimoku_kijun_period"],
                    senkou_span_b_period=isd["ichimoku_senkou_span_b_period"],
                    chikou_span_offset=isd["ichimoku_chikou_span_offset"],
                )
            )
            if tenkan_sen is not None:
                self.df["Tenkan_Sen"] = tenkan_sen
            if kijun_sen is not None:
                self.df["Kijun_Sen"] = kijun_sen
            if senkou_span_a is not None:
                self.df["Senkou_Span_A"] = senkou_span_a
            if senkou_span_b is not None:
                self.df["Senkou_Span_B"] = senkou_span_b
            if chikou_span is not None:
                self.df["Chikou_Span"] = chikou_span

            if tenkan_sen is not None:
                self.indicator_values["Tenkan_Sen"] = tenkan_sen.iloc[-1]
            if kijun_sen is not None:
                self.indicator_values["Kijun_Sen"] = kijun_sen.iloc[-1]
            if senkou_span_a is not None:
                self.indicator_values["Senkou_Span_A"] = senkou_span_a.iloc[-1]
            if senkou_span_b is not None:
                self.indicator_values["Senkou_Span_B"] = senkou_span_b.iloc[-1]
            if chikou_span is not None:
                self.indicator_values["Chikou_Span"] = chikou_span.fillna(0).iloc[-1]

        # PSAR
        if cfg["indicators"].get("psar", False):
            psar_val, psar_dir = self._safe_calculate(
                self.calculate_psar,
                "PSAR",
                min_data_points=MIN_DATA_POINTS_PSAR,
                acceleration=isd["psar_acceleration"],
                max_acceleration=isd["psar_max_acceleration"],
            )
            if psar_val is not None:
                self.df["PSAR_Val"] = psar_val
            if psar_dir is not None:
                self.df["PSAR_Dir"] = psar_dir
            if psar_val is not None:
                self.indicator_values["PSAR_Val"] = psar_val.iloc[-1]
            if psar_dir is not None:
                self.indicator_values["PSAR_Dir"] = psar_dir.iloc[-1]

        # VWAP (requires volume and turnover, which are in df)
        if cfg["indicators"].get("vwap", False):
            self.df["VWAP"] = self._safe_calculate(
                self.calculate_vwap,
                "VWAP",
                min_data_points=1,
            )
            if self.df["VWAP"] is not None:
                self.indicator_values["VWAP"] = self.df["VWAP"].iloc[-1]

        # --- Ehlers SuperTrend Calculation ---
        if cfg["indicators"].get("ehlers_supertrend", False):
            st_fast_result = self._safe_calculate(
                self.calculate_ehlers_supertrend,
                "EhlersSuperTrendFast",
                min_data_points=isd["ehlers_fast_period"] * 3,
                period=isd["ehlers_fast_period"],
                multiplier=isd["ehlers_fast_multiplier"],
            )
            if st_fast_result is not None and not st_fast_result.empty:
                self.df["st_fast_dir"] = st_fast_result["direction"]
                self.df["st_fast_val"] = st_fast_result["supertrend"]
                self.indicator_values["ST_Fast_Dir"] = st_fast_result["direction"].iloc[
                    -1
                ]
                self.indicator_values["ST_Fast_Val"] = st_fast_result[
                    "supertrend"
                ].iloc[-1]

            st_slow_result = self._safe_calculate(
                self.calculate_ehlers_supertrend,
                "EhlersSuperTrendSlow",
                min_data_points=isd["ehlers_slow_period"] * 3,
                period=isd["ehlers_slow_period"],
                multiplier=isd["ehlers_slow_multiplier"],
            )
            if st_slow_result is not None and not st_slow_result.empty:
                self.df["st_slow_dir"] = st_slow_result["direction"]
                self.df["st_slow_val"] = st_slow_result["supertrend"]
                self.indicator_values["ST_Slow_Dir"] = st_slow_result["direction"].iloc[
                    -1
                ]
                self.indicator_values["ST_Slow_Val"] = st_slow_result[
                    "supertrend"
                ].iloc[-1]

        # MACD
        if cfg["indicators"].get("macd", False):
            macd_line, signal_line, histogram = self._safe_calculate(
                self.calculate_macd,
                "MACD",
                min_data_points=isd["macd_slow_period"] + isd["macd_signal_period"],
                fast_period=isd["macd_fast_period"],
                slow_period=isd["macd_slow_period"],
                signal_period=isd["macd_signal_period"],
            )
            if macd_line is not None:
                self.df["MACD_Line"] = macd_line
            if signal_line is not None:
                self.df["MACD_Signal"] = signal_line
            if histogram is not None:
                self.df["MACD_Hist"] = histogram
            if macd_line is not None:
                self.indicator_values["MACD_Line"] = macd_line.iloc[-1]
            if signal_line is not None:
                self.indicator_values["MACD_Signal"] = signal_line.iloc[-1]
            if histogram is not None:
                self.indicator_values["MACD_Hist"] = histogram.iloc[-1]

        # ADX
        if cfg["indicators"].get("adx", False):
            adx_val, plus_di, minus_di = self._safe_calculate(
                self.calculate_adx,
                "ADX",
                min_data_points=isd["adx_period"] * 2,
                period=isd["adx_period"],
            )
            if adx_val is not None:
                self.df["ADX"] = adx_val
            if plus_di is not None:
                self.df["PlusDI"] = plus_di
            if minus_di is not None:
                self.df["MinusDI"] = minus_di
            if adx_val is not None:
                self.indicator_values["ADX"] = adx_val.iloc[-1]
            if plus_di is not None:
                self.indicator_values["PlusDI"] = plus_di.iloc[-1]
            if minus_di is not None:
                self.indicator_values["MinusDI"] = minus_di.iloc[-1]

        # --- New Indicators ---
        # Volatility Index
        if cfg["indicators"].get("volatility_index", False):
            self.df["Volatility_Index"] = self._safe_calculate(
                self.calculate_volatility_index,
                "Volatility_Index",
                min_data_points=isd["volatility_index_period"],
                period=isd["volatility_index_period"],
            )
            if self.df["Volatility_Index"] is not None:
                self.indicator_values["Volatility_Index"] = self.df[
                    "Volatility_Index"
                ].iloc[-1]

        # VWMA
        if cfg["indicators"].get("vwma", False):
            self.df["VWMA"] = self._safe_calculate(
                self.calculate_vwma,
                "VWMA",
                min_data_points=isd["vwma_period"],
                period=isd["vwma_period"],
            )
            if self.df["VWMA"] is not None:
                self.indicator_values["VWMA"] = self.df["VWMA"].iloc[-1]

        # Volume Delta
        if cfg["indicators"].get("volume_delta", False):
            self.df["Volume_Delta"] = self._safe_calculate(
                self.calculate_volume_delta,
                "Volume_Delta",
                min_data_points=isd["volume_delta_period"],
                period=isd["volume_delta_period"],
            )
            if self.df["Volume_Delta"] is not None:
                self.indicator_values["Volume_Delta"] = self.df["Volume_Delta"].iloc[-1]

        # Final dropna after all indicators are calculated
        initial_len = len(self.df)
        self.df.dropna(subset=["close"], inplace=True)
        self.df.fillna(0, inplace=True)  # Fill any remaining NaNs in indicator columns

        if len(self.df) < initial_len:
            self.logger.debug(
                f"Dropped {initial_len - len(self.df)} rows with NaNs after indicator calculations.",
            )

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] DataFrame is empty after calculating all indicators and dropping NaNs.{RESET}",
            )
        else:
            self.logger.debug(
                f"[{self.symbol}] Indicators calculated. Final DataFrame size: {len(self.df)}",
            )

    def calculate_true_range(self) -> pd.Series:
        """Calculate True Range (TR)."""
        if len(self.df) < MIN_DATA_POINTS_TR:
            return pd.Series(np.nan, index=self.df.index)
        high_low = self.df["high"] - self.df["low"]
        high_prev_close = (self.df["high"] - self.df["close"].shift()).abs()
        low_prev_close = (self.df["low"] - self.df["close"].shift()).abs()
        return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(
            axis=1,
        )

    def calculate_super_smoother(self, series: pd.Series, period: int) -> pd.Series:
        """Apply Ehlers SuperSmoother filter to reduce lag and noise."""
        if period <= 0 or len(series) < MIN_DATA_POINTS_SMOOTHER:
            return pd.Series(np.nan, index=series.index)

        series = pd.to_numeric(series, errors="coerce").dropna()
        if len(series) < MIN_DATA_POINTS_SMOOTHER:
            return pd.Series(np.nan, index=series.index)

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
        return filt.reindex(self.df.index)

    def calculate_ehlers_supertrend(
        self,
        period: int,
        multiplier: float,
    ) -> pd.DataFrame | None:
        """Calculate SuperTrend using Ehlers SuperSmoother for price and volatility."""
        if len(self.df) < period * 3:
            self.logger.debug(
                f"[{self.symbol}] Not enough data for Ehlers SuperTrend (period={period}). Need at least {period * 3} bars.",
            )
            return None

        df_copy = self.df.copy()

        hl2 = (df_copy["high"] + df_copy["low"]) / 2
        smoothed_price = self.calculate_super_smoother(hl2, period)

        tr = self.calculate_true_range()
        smoothed_atr = self.calculate_super_smoother(tr, period)

        df_copy["smoothed_price"] = smoothed_price
        df_copy["smoothed_atr"] = smoothed_atr

        if df_copy.empty:
            self.logger.debug(
                f"[{self.symbol}] Ehlers SuperTrend: DataFrame empty after smoothing. Returning None.",
            )
            return None

        upper_band = df_copy["smoothed_price"] + multiplier * df_copy["smoothed_atr"]
        lower_band = df_copy["smoothed_price"] - multiplier * df_copy["smoothed_atr"]

        direction = pd.Series(0, index=df_copy.index, dtype=int)
        supertrend = pd.Series(np.nan, index=df_copy.index)

        # Find the first valid index after smoothing
        first_valid_idx_val = smoothed_price.first_valid_index()
        if first_valid_idx_val is None:
            return None
        first_valid_idx = df_copy.index.get_loc(first_valid_idx_val)
        if first_valid_idx >= len(df_copy):
            return None

        # Initialize the first valid supertrend value based on the first valid close price relative to bands
        if df_copy["close"].iloc[first_valid_idx] > upper_band.iloc[first_valid_idx]:
            direction.iloc[first_valid_idx] = 1
            supertrend.iloc[first_valid_idx] = lower_band.iloc[first_valid_idx]
        elif df_copy["close"].iloc[first_valid_idx] < lower_band.iloc[first_valid_idx]:
            direction.iloc[first_valid_idx] = -1
            supertrend.iloc[first_valid_idx] = upper_band.iloc[first_valid_idx]
        else:  # Price is within bands, initialize with lower band, neutral direction
            direction.iloc[first_valid_idx] = 0
            supertrend.iloc[first_valid_idx] = lower_band.iloc[first_valid_idx]

        for i in range(first_valid_idx + 1, len(df_copy)):
            prev_direction = direction.iloc[i - 1]
            prev_supertrend = supertrend.iloc[i - 1]
            curr_close = df_copy["close"].iloc[i]

            if prev_direction == 1:  # Previous was an UP trend
                # If current close drops below the prev_supertrend, flip to DOWN
                if curr_close < prev_supertrend:
                    direction.iloc[i] = -1
                    supertrend.iloc[i] = upper_band.iloc[i]  # New ST is upper band
                else:  # Continue UP trend
                    direction.iloc[i] = 1
                    # New ST is max of current lower_band and prev_supertrend
                    supertrend.iloc[i] = max(lower_band.iloc[i], prev_supertrend)
            elif prev_direction == -1:  # Previous was a DOWN trend
                # If current close rises above the prev_supertrend, flip to UP
                if curr_close > prev_supertrend:
                    direction.iloc[i] = 1
                    supertrend.iloc[i] = lower_band.iloc[i]  # New ST is lower band
                else:  # Continue DOWN trend
                    direction.iloc[i] = -1
                    # New ST is min of current upper_band and prev_supertrend
                    supertrend.iloc[i] = min(upper_band.iloc[i], prev_supertrend)
            elif curr_close > upper_band.iloc[i]:
                direction.iloc[i] = 1
                supertrend.iloc[i] = lower_band.iloc[i]
            elif curr_close < lower_band.iloc[i]:
                direction.iloc[i] = -1
                supertrend.iloc[i] = upper_band.iloc[i]
            else:  # Still within bands or undecided, stick to previous or default
                direction.iloc[i] = prev_direction  # Maintain previous direction
                supertrend.iloc[i] = prev_supertrend  # Maintain previous supertrend

        result = pd.DataFrame({"supertrend": supertrend, "direction": direction})
        return result.reindex(self.df.index)

    def calculate_macd(
        self,
        fast_period: int,
        slow_period: int,
        signal_period: int,
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Moving Average Convergence Divergence (MACD)."""
        if len(self.df) < slow_period + signal_period:
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        ema_fast = self.df["close"].ewm(span=fast_period, adjust=False).mean()
        ema_slow = self.df["close"].ewm(span=slow_period, adjust=False).mean()

        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        histogram = macd_line - signal_line

        return macd_line, signal_line, histogram

    def calculate_rsi(self, period: int) -> pd.Series:
        """Calculate Relative Strength Index (RSI)."""
        if len(self.df) <= period:
            return pd.Series(np.nan, index=self.df.index)
        delta = self.df["close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.ewm(span=period, adjust=False, min_periods=period).mean()
        avg_loss = loss.ewm(span=period, adjust=False, min_periods=period).mean()

        # Handle division by zero for rs where avg_loss is 0
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_stoch_rsi(
        self,
        period: int,
        k_period: int,
        d_period: int,
    ) -> tuple[pd.Series, pd.Series]:
        """Calculate Stochastic RSI."""
        if len(self.df) <= period:
            return pd.Series(np.nan, index=self.df.index), pd.Series(
                np.nan,
                index=self.df.index,
            )
        rsi = self.calculate_rsi(period)

        lowest_rsi = rsi.rolling(window=period, min_periods=period).min()
        highest_rsi = rsi.rolling(window=period, min_periods=period).max()

        # Avoid division by zero if highest_rsi == lowest_rsi
        denominator = highest_rsi - lowest_rsi
        denominator[denominator == 0] = np.nan  # Replace 0 with NaN for division
        stoch_rsi_k_raw = ((rsi - lowest_rsi) / denominator) * 100
        stoch_rsi_k_raw = stoch_rsi_k_raw.fillna(0).clip(
            0,
            100,
        )  # Clip to [0, 100] and fill remaining NaNs with 0

        stoch_rsi_k = (
            stoch_rsi_k_raw.rolling(window=k_period, min_periods=k_period)
            .mean()
            .fillna(0)
        )
        stoch_rsi_d = (
            stoch_rsi_k.rolling(window=d_period, min_periods=d_period).mean().fillna(0)
        )

        return stoch_rsi_k, stoch_rsi_d

    def calculate_adx(self, period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Average Directional Index (ADX)."""
        if len(self.df) < period * 2:
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        # True Range
        tr = self.calculate_true_range()

        # Directional Movement
        plus_dm = self.df["high"].diff()
        minus_dm = -self.df["low"].diff()

        plus_dm_final = pd.Series(0.0, index=self.df.index)
        minus_dm_final = pd.Series(0.0, index=self.df.index)

        # Apply +DM and -DM logic
        for i in range(1, len(self.df)):
            if plus_dm.iloc[i] > minus_dm.iloc[i] and plus_dm.iloc[i] > 0:
                plus_dm_final.iloc[i] = plus_dm.iloc[i]
            if minus_dm.iloc[i] > plus_dm.iloc[i] and minus_dm.iloc[i] > 0:
                minus_dm_final.iloc[i] = minus_dm.iloc[i]

        # Smoothed True Range, +DM, -DM
        atr = tr.ewm(span=period, adjust=False).mean()
        plus_di = (plus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100
        minus_di = (minus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100

        # DX
        di_diff = abs(plus_di - minus_di)
        di_sum = plus_di + minus_di
        # Handle division by zero
        dx = (di_diff / di_sum.replace(0, np.nan)).fillna(0) * 100

        # ADX
        adx = dx.ewm(span=period, adjust=False).mean()

        return adx, plus_di, minus_di

    def calculate_bollinger_bands(
        self,
        period: int,
        std_dev: float,
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands."""
        if len(self.df) < period:
            return (
                pd.Series(np.nan, index=self.df.index),
                pd.Series(np.nan, index=self.df.index),
                pd.Series(np.nan, index=self.df.index),
            )
        middle_band = self.df["close"].rolling(window=period, min_periods=period).mean()
        std = self.df["close"].rolling(window=period, min_periods=period).std()
        upper_band = middle_band + (std * std_dev)
        lower_band = middle_band - (std * std_dev)
        return upper_band, middle_band, lower_band

    def calculate_vwap(self) -> pd.Series:
        """Calculate Volume Weighted Average Price (VWAP)."""
        if self.df.empty:
            return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        # Ensure cumulative sum starts from valid data, reindex to original df index
        cumulative_tp_vol = (typical_price * self.df["volume"]).cumsum()
        cumulative_vol = self.df["volume"].cumsum()
        vwap = cumulative_tp_vol / cumulative_vol
        return vwap.reindex(self.df.index)

    def calculate_cci(self, period: int) -> pd.Series:
        """Calculate Commodity Channel Index (CCI)."""
        if len(self.df) < period:
            return pd.Series(np.nan, index=self.df.index)
        tp = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        sma_tp = tp.rolling(window=period, min_periods=period).mean()
        mad = tp.rolling(window=period, min_periods=period).apply(
            lambda x: np.abs(x - x.mean()).mean(),
            raw=False,
        )
        # Handle potential division by zero for mad
        cci = (tp - sma_tp) / (0.015 * mad.replace(0, np.nan))
        return cci

    def calculate_williams_r(self, period: int) -> pd.Series:
        """Calculate Williams %R."""
        if len(self.df) < period:
            return pd.Series(np.nan, index=self.df.index)
        highest_high = self.df["high"].rolling(window=period, min_periods=period).max()
        lowest_low = self.df["low"].rolling(window=period, min_periods=period).min()
        # Handle division by zero
        denominator = highest_high - lowest_low
        wr = -100 * ((highest_high - self.df["close"]) / denominator.replace(0, np.nan))
        return wr

    def calculate_ichimoku_cloud(
        self,
        tenkan_period: int,
        kijun_period: int,
        senkou_span_b_period: int,
        chikou_span_offset: int,
    ) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
        """Calculate Ichimoku Cloud components."""
        if (
            len(self.df)
            < max(tenkan_period, kijun_period, senkou_span_b_period)
            + chikou_span_offset
        ):
            return (
                pd.Series(np.nan),
                pd.Series(np.nan),
                pd.Series(np.nan),
                pd.Series(np.nan),
                pd.Series(np.nan),
            )

        tenkan_sen = (
            self.df["high"].rolling(window=tenkan_period).max()
            + self.df["low"].rolling(window=tenkan_period).min()
        ) / 2

        kijun_sen = (
            self.df["high"].rolling(window=kijun_period).max()
            + self.df["low"].rolling(window=kijun_period).min()
        ) / 2

        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun_period)

        senkou_span_b = (
            (
                self.df["high"].rolling(window=senkou_span_b_period).max()
                + self.df["low"].rolling(window=senkou_span_b_period).min()
            )
            / 2
        ).shift(kijun_period)

        chikou_span = self.df["close"].shift(-chikou_span_offset)

        return tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span

    def calculate_mfi(self, period: int) -> pd.Series:
        """Calculate Money Flow Index (MFI)."""
        if len(self.df) <= period:
            return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        money_flow = typical_price * self.df["volume"]

        positive_flow = pd.Series(0.0, index=self.df.index)
        negative_flow = pd.Series(0.0, index=self.df.index)

        # Calculate positive and negative money flow
        # Use vectorized operations where possible
        price_diff = typical_price.diff()
        positive_flow = money_flow.where(price_diff > 0, 0)
        negative_flow = money_flow.where(price_diff < 0, 0)

        # Rolling sum for period
        positive_mf_sum = positive_flow.rolling(window=period, min_periods=period).sum()
        negative_mf_sum = negative_flow.rolling(window=period, min_periods=period).sum()

        # Avoid division by zero
        mf_ratio = positive_mf_sum / negative_mf_sum.replace(0, np.nan)
        mfi = 100 - (100 / (1 + mf_ratio))
        return mfi

    def calculate_obv(self, ema_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate On-Balance Volume (OBV) and its EMA."""
        if len(self.df) < MIN_DATA_POINTS_OBV:
            return pd.Series(np.nan), pd.Series(np.nan)

        obv = pd.Series(0.0, index=self.df.index)
        obv_direction = np.sign(self.df["close"].diff().fillna(0))
        obv = (obv_direction * self.df["volume"]).cumsum()

        obv_ema = obv.ewm(span=ema_period, adjust=False).mean()

        return obv, obv_ema

    def calculate_cmf(self, period: int) -> pd.Series:
        """Calculate Chaikin Money Flow (CMF)."""
        if len(self.df) < period:
            return pd.Series(np.nan)

        # Money Flow Multiplier (MFM)
        high_low_range = self.df["high"] - self.df["low"]
        # Handle division by zero for high_low_range
        mfm = (
            (self.df["close"] - self.df["low"]) - (self.df["high"] - self.df["close"])
        ) / high_low_range.replace(0, np.nan)
        mfm = mfm.fillna(0)

        # Money Flow Volume (MFV)
        mfv = mfm * self.df["volume"]

        # CMF
        volume_sum = self.df["volume"].rolling(window=period).sum()
        # Handle division by zero for volume_sum
        cmf = mfv.rolling(window=period).sum() / volume_sum.replace(0, np.nan)
        cmf = cmf.fillna(0)

        return cmf

    def calculate_psar(
        self,
        acceleration: float,
        max_acceleration: float,
    ) -> tuple[pd.Series, pd.Series]:
        """Calculate Parabolic SAR."""
        if len(self.df) < MIN_DATA_POINTS_PSAR:
            return pd.Series(np.nan, index=self.df.index), pd.Series(
                np.nan,
                index=self.df.index,
            )

        psar = self.df["close"].copy()
        bull = pd.Series(True, index=self.df.index)
        af = acceleration
        ep = (
            self.df["low"].iloc[0]
            if self.df["close"].iloc[0] < self.df["close"].iloc[1]
            else self.df["high"].iloc[0]
        )  # Initial EP depends on first two bars' direction

        for i in range(1, len(self.df)):
            prev_bull = bull.iloc[i - 1]
            prev_psar = psar.iloc[i - 1]

            # Calculate current PSAR value
            if prev_bull:  # Bullish trend
                psar.iloc[i] = prev_psar + af * (ep - prev_psar)
            else:  # Bearish trend
                psar.iloc[i] = prev_psar - af * (prev_psar - ep)

            # Check for reversal conditions
            reverse = False
            if prev_bull and self.df["low"].iloc[i] < psar.iloc[i]:
                bull.iloc[i] = False  # Reverse to bearish
                reverse = True
            elif not prev_bull and self.df["high"].iloc[i] > psar.iloc[i]:
                bull.iloc[i] = True  # Reverse to bullish
                reverse = True
            else:
                bull.iloc[i] = prev_bull  # Continue previous trend

            # Update AF and EP
            if reverse:
                af = acceleration
                ep = self.df["high"].iloc[i] if bull.iloc[i] else self.df["low"].iloc[i]
                # Ensure PSAR does not cross price on reversal
                if bull.iloc[
                    i
                ]:  # if reversing to bullish, PSAR should be below current low
                    psar.iloc[i] = min(
                        self.df["low"].iloc[i],
                        self.df["low"].iloc[i - 1],
                    )
                else:  # if reversing to bearish, PSAR should be above current high
                    psar.iloc[i] = max(
                        self.df["high"].iloc[i],
                        self.df["high"].iloc[i - 1],
                    )

            elif bull.iloc[i]:  # Continuing bullish
                if self.df["high"].iloc[i] > ep:
                    ep = self.df["high"].iloc[i]
                    af = min(af + acceleration, max_acceleration)
                # Keep PSAR below the lowest low of the last two bars
                psar.iloc[i] = min(
                    psar.iloc[i],
                    self.df["low"].iloc[i],
                    self.df["low"].iloc[i - 1],
                )
            else:  # Continuing bearish
                if self.df["low"].iloc[i] < ep:
                    ep = self.df["low"].iloc[i]
                    af = min(af + acceleration, max_acceleration)
                # Keep PSAR above the highest high of the last two bars
                psar.iloc[i] = max(
                    psar.iloc[i],
                    self.df["high"].iloc[i],
                    self.df["high"].iloc[i - 1],
                )

        direction = pd.Series(0, index=self.df.index, dtype=int)
        direction[psar < self.df["close"]] = 1  # Bullish
        direction[psar > self.df["close"]] = -1  # Bearish

        return psar, direction

    def calculate_fibonacci_levels(self) -> None:
        """Calculate Fibonacci retracement levels based on a recent high-low swing."""
        window = self.config["indicator_settings"]["fibonacci_window"]
        if len(self.df) < window:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Not enough data for Fibonacci levels (need {window} bars).{RESET}",
            )
            return

        recent_high = self.df["high"].iloc[-window:].max()
        recent_low = self.df["low"].iloc[-window:].min()

        diff = recent_high - recent_low

        if diff <= 0:  # Handle cases where high and low are the same or inverted
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Invalid high-low range for Fibonacci calculation. Diff: {diff}{RESET}",
            )
            return

        self.fib_levels = {
            "0.0%": Decimal(str(recent_high)),
            "23.6%": Decimal(str(recent_high - 0.236 * diff)).quantize(
                Decimal("0.00001"),
                rounding=ROUND_DOWN,
            ),
            "38.2%": Decimal(str(recent_high - 0.382 * diff)).quantize(
                Decimal("0.00001"),
                rounding=ROUND_DOWN,
            ),
            "50.0%": Decimal(str(recent_high - 0.500 * diff)).quantize(
                Decimal("0.00001"),
                rounding=ROUND_DOWN,
            ),
            "61.8%": Decimal(str(recent_high - 0.618 * diff)).quantize(
                Decimal("0.00001"),
                rounding=ROUND_DOWN,
            ),
            "78.6%": Decimal(str(recent_high - 0.786 * diff)).quantize(
                Decimal("0.00001"),
                rounding=ROUND_DOWN,
            ),
            "100.0%": Decimal(str(recent_low)),
        }
        self.logger.debug(
            f"[{self.symbol}] Calculated Fibonacci levels: {self.fib_levels}",
        )

    def calculate_volatility_index(self, period: int) -> pd.Series:
        """Calculate a simple Volatility Index based on ATR normalized by price."""
        if len(self.df) < period or "ATR" not in self.df.columns:
            return pd.Series(np.nan, index=self.df.index)

        # ATR is already calculated in _calculate_all_indicators
        normalized_atr = self.df["ATR"] / self.df["close"]
        volatility_index = normalized_atr.rolling(window=period).mean()
        return volatility_index

    def calculate_vwma(self, period: int) -> pd.Series:
        """Calculate Volume Weighted Moving Average (VWMA)."""
        if len(self.df) < period or self.df["volume"].isnull().any():
            return pd.Series(np.nan, index=self.df.index)

        # Ensure volume is numeric and not zero
        valid_volume = self.df["volume"].replace(0, np.nan)
        pv = self.df["close"] * valid_volume
        vwma = (
            pv.rolling(window=period).sum() / valid_volume.rolling(window=period).sum()
        )
        return vwma

    def calculate_volume_delta(self, period: int) -> pd.Series:
        """Calculate Volume Delta, indicating buying vs selling pressure."""
        if len(self.df) < MIN_DATA_POINTS_VOLATILITY:
            return pd.Series(np.nan, index=self.df.index)

        # Approximate buy/sell volume based on close relative to open
        buy_volume = self.df["volume"].where(self.df["close"] > self.df["open"], 0)
        sell_volume = self.df["volume"].where(self.df["close"] < self.df["open"], 0)

        # Rolling sum of buy/sell volume
        buy_volume_sum = buy_volume.rolling(window=period, min_periods=1).sum()
        sell_volume_sum = sell_volume.rolling(window=period, min_periods=1).sum()

        total_volume_sum = buy_volume_sum + sell_volume_sum
        # Avoid division by zero
        volume_delta = (buy_volume_sum - sell_volume_sum) / total_volume_sum.replace(
            0,
            np.nan,
        )
        return volume_delta.fillna(0)

    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        """Safely retrieve an indicator value."""
        return self.indicator_values.get(key, default)

    def _check_orderbook(self, current_price: Decimal, orderbook_data: dict) -> float:
        """Analyze orderbook imbalance."""
        bids = orderbook_data.get("bids", [])  # Changed from 'b' to 'bids'
        asks = orderbook_data.get("asks", [])  # Changed from 'a' to 'asks'

        bid_volume = sum(Decimal(b[1]) for b in bids)
        ask_volume = sum(Decimal(a[1]) for a in asks)

        if bid_volume + ask_volume == 0:
            return 0.0

        imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
        self.logger.debug(
            f"[{self.symbol}] Orderbook Imbalance: {imbalance:.4f} (Bids: {bid_volume}, Asks: {ask_volume})",
        )
        return float(imbalance)

    def _get_mtf_trend(self, higher_tf_df: pd.DataFrame, indicator_type: str) -> str:
        """Determine trend from higher timeframe using specified indicator."""
        if higher_tf_df.empty:
            return "UNKNOWN"

        last_close = higher_tf_df["close"].iloc[-1]
        period = self.config["mtf_analysis"]["trend_period"]

        if indicator_type == "sma":
            if len(higher_tf_df) < period:
                self.logger.debug(
                    f"[{self.symbol}] MTF SMA: Not enough data for {period} period. Have {len(higher_tf_df)}.",
                )
                return "UNKNOWN"
            sma = (
                higher_tf_df["close"]
                .rolling(window=period, min_periods=period)
                .mean()
                .iloc[-1]
            )
            if last_close > sma:
                return "UP"
            if last_close < sma:
                return "DOWN"
            return "SIDEWAYS"
        if indicator_type == "ema":
            if len(higher_tf_df) < period:
                self.logger.debug(
                    f"[{self.symbol}] MTF EMA: Not enough data for {period} period. Have {len(higher_tf_df)}.",
                )
                return "UNKNOWN"
            ema = (
                higher_tf_df["close"]
                .ewm(span=period, adjust=False, min_periods=period)
                .mean()
                .iloc[-1]
            )
            if last_close > ema:
                return "UP"
            if last_close < ema:
                return "DOWN"
            return "SIDEWAYS"
        if indicator_type == "ehlers_supertrend":
            # For MTF, we need to ensure the TradingAnalyzer can be initialized correctly with the MTF df
            # This creates a temporary analyzer instance just for this purpose.
            temp_analyzer = TradingAnalyzer(
                higher_tf_df,
                self.config,
                self.logger,
                self.symbol,
            )
            st_result = temp_analyzer._safe_calculate(
                temp_analyzer.calculate_ehlers_supertrend,
                "EhlersSuperTrend",
                min_data_points=self.indicator_settings["ehlers_slow_period"] * 3,
                period=self.indicator_settings["ehlers_slow_period"],
                multiplier=self.indicator_settings["ehlers_slow_multiplier"],
            )

            if st_result is not None and not st_result.empty:
                st_dir = st_result["direction"].iloc[-1]
                if st_dir == 1:
                    return "UP"
                if st_dir == -1:
                    return "DOWN"
            return "UNKNOWN"
        return "UNKNOWN"

    def generate_trading_signal(
        self,
        current_price: Decimal,
        orderbook_data: dict | None,
        mtf_trends: dict[str, str],
    ) -> tuple[str, float]:
        """Generate a signal using confluence of indicators, including Ehlers SuperTrend."""
        signal_score = 0.0
        reasons = []
        active_indicators = self.config["indicators"]
        weights = self.weights
        isd = self.indicator_settings

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}",
            )
            return "HOLD", 0.0

        current_close = Decimal(str(self.df["close"].iloc[-1]))
        prev_close = Decimal(
            str(self.df["close"].iloc[-2]) if len(self.df) > 1 else current_close,
        )

        # EMA Alignment
        if active_indicators.get("ema_alignment", False):
            ema_short = self._get_indicator_value("EMA_Short")
            ema_long = self._get_indicator_value("EMA_Long")
            if not pd.isna(ema_short) and not pd.isna(ema_long):
                if ema_short > ema_long:
                    score_contribution = weights.get("ema_alignment", 0)
                    signal_score += score_contribution
                    reasons.append(
                        f"EMA Alignment: Bullish (Score +{score_contribution:.2f})",
                    )
                elif ema_short < ema_long:
                    score_contribution = -weights.get("ema_alignment", 0)
                    signal_score += score_contribution
                    reasons.append(
                        f"EMA Alignment: Bearish (Score {score_contribution:.2f})",
                    )

        # SMA Trend Filter
        if active_indicators.get("sma_trend_filter", False):
            sma_long = self._get_indicator_value("SMA_Long")
            if not pd.isna(sma_long):
                if current_close > sma_long:
                    score_contribution = weights.get("sma_trend_filter", 0)
                    signal_score += score_contribution
                    reasons.append(
                        f"SMA Trend Filter: Bullish (Score +{score_contribution:.2f})",
                    )
                elif current_close < sma_long:
                    score_contribution = -weights.get("sma_trend_filter", 0)
                    signal_score += score_contribution
                    reasons.append(
                        f"SMA Trend Filter: Bearish (Score {score_contribution:.2f})",
                    )

        # Momentum Indicators (RSI, StochRSI, CCI, WR, MFI)
        if active_indicators.get("momentum", False):
            momentum_weight = weights.get("momentum_rsi_stoch_cci_wr_mfi", 0)

            # RSI
            if active_indicators.get("rsi", False):
                rsi = self._get_indicator_value("RSI")
                if not pd.isna(rsi):
                    if rsi < isd["rsi_oversold"]:
                        score_contribution = momentum_weight * 0.5
                        signal_score += score_contribution
                        reasons.append(
                            f"RSI: Oversold (Score +{score_contribution:.2f})",
                        )
                    elif rsi > isd["rsi_overbought"]:
                        score_contribution = -momentum_weight * 0.5
                        signal_score += score_contribution
                        reasons.append(
                            f"RSI: Overbought (Score {score_contribution:.2f})",
                        )

            # StochRSI Crossover
            if active_indicators.get("stoch_rsi", False):
                stoch_k = self._get_indicator_value("StochRSI_K")
                stoch_d = self._get_indicator_value("StochRSI_D")
                if not pd.isna(stoch_k) and not pd.isna(stoch_d) and len(self.df) > 1:
                    prev_stoch_k = self.df["StochRSI_K"].iloc[-2]
                    prev_stoch_d = self.df["StochRSI_D"].iloc[-2]
                    if (
                        stoch_k > stoch_d
                        and prev_stoch_k <= prev_stoch_d
                        and stoch_k < isd["stoch_rsi_oversold"]
                    ):
                        score_contribution = momentum_weight * 0.6
                        signal_score += score_contribution
                        reasons.append(
                            f"StochRSI: Bullish Crossover (Score +{score_contribution:.2f})",
                        )
                    elif (
                        stoch_k < stoch_d
                        and prev_stoch_k >= prev_stoch_d
                        and stoch_k > isd["stoch_rsi_overbought"]
                    ):
                        score_contribution = -momentum_weight * 0.6
                        signal_score += score_contribution
                        reasons.append(
                            f"StochRSI: Bearish Crossover (Score {score_contribution:.2f})",
                        )
                    elif stoch_k > stoch_d and stoch_k < 50:  # General bullish momentum
                        score_contribution = momentum_weight * 0.2
                        signal_score += score_contribution
                        reasons.append(
                            f"StochRSI: Bullish Momentum (Score +{score_contribution:.2f})",
                        )
                    elif stoch_k < stoch_d and stoch_k > 50:  # General bearish momentum
                        score_contribution = -momentum_weight * 0.2
                        signal_score += score_contribution
                        reasons.append(
                            f"StochRSI: Bearish Momentum (Score {score_contribution:.2f})",
                        )

            # CCI
            if active_indicators.get("cci", False):
                cci = self._get_indicator_value("CCI")
                if not pd.isna(cci):
                    if cci < isd["cci_oversold"]:
                        score_contribution = momentum_weight * 0.4
                        signal_score += score_contribution
                        reasons.append(
                            f"CCI: Oversold (Score +{score_contribution:.2f})",
                        )
                    elif cci > isd["cci_overbought"]:
                        score_contribution = -momentum_weight * 0.4
                        signal_score += score_contribution
                        reasons.append(
                            f"CCI: Overbought (Score {score_contribution:.2f})",
                        )

            # Williams %R
            if active_indicators.get("wr", False):
                wr = self._get_indicator_value("WR")
                if not pd.isna(wr):
                    if wr < isd["williams_r_oversold"]:
                        score_contribution = momentum_weight * 0.4
                        signal_score += score_contribution
                        reasons.append(
                            f"Williams %R: Oversold (Score +{score_contribution:.2f})",
                        )
                    elif wr > isd["williams_r_overbought"]:
                        score_contribution = -momentum_weight * 0.4
                        signal_score += score_contribution
                        reasons.append(
                            f"Williams %R: Overbought (Score {score_contribution:.2f})",
                        )

            # MFI
            if active_indicators.get("mfi", False):
                mfi = self._get_indicator_value("MFI")
                if not pd.isna(mfi):
                    if mfi < isd["mfi_oversold"]:
                        score_contribution = momentum_weight * 0.4
                        signal_score += score_contribution
                        reasons.append(
                            f"MFI: Oversold (Score +{score_contribution:.2f})",
                        )
                    elif mfi > isd["mfi_overbought"]:
                        score_contribution = -momentum_weight * 0.4
                        signal_score += score_contribution
                        reasons.append(
                            f"MFI: Overbought (Score {score_contribution:.2f})",
                        )

        # Bollinger Bands
        if active_indicators.get("bollinger_bands", False):
            bb_upper = self._get_indicator_value("BB_Upper")
            bb_lower = self._get_indicator_value("BB_Lower")
            if not pd.isna(bb_upper) and not pd.isna(bb_lower):
                if current_close < bb_lower:
                    score_contribution = weights.get("bollinger_bands", 0) * 0.5
                    signal_score += score_contribution
                    reasons.append(
                        f"Bollinger Bands: Price below lower band (Score +{score_contribution:.2f})",
                    )
                elif current_close > bb_upper:
                    score_contribution = -weights.get("bollinger_bands", 0) * 0.5
                    signal_score += score_contribution
                    reasons.append(
                        f"Bollinger Bands: Price above upper band (Score {score_contribution:.2f})",
                    )

        # VWAP
        if active_indicators.get("vwap", False):
            vwap = self._get_indicator_value("VWAP")
            if not pd.isna(vwap):
                if current_close > vwap:
                    score_contribution = weights.get("vwap", 0) * 0.2
                    signal_score += score_contribution
                    reasons.append(
                        f"VWAP: Price above VWAP (Score +{score_contribution:.2f})",
                    )
                elif current_close < vwap:
                    score_contribution = -weights.get("vwap", 0) * 0.2
                    signal_score += score_contribution
                    reasons.append(
                        f"VWAP: Price below VWAP (Score {score_contribution:.2f})",
                    )

                if len(self.df) > 1:
                    prev_vwap = Decimal(str(self.df["VWAP"].iloc[-2]))
                    if current_close > vwap and prev_close <= prev_vwap:
                        score_contribution = weights.get("vwap", 0) * 0.3
                        signal_score += score_contribution
                        reasons.append(
                            f"VWAP: Bullish crossover detected (Score +{score_contribution:.2f})",
                        )
                    elif current_close < vwap and prev_close >= prev_vwap:
                        score_contribution = -weights.get("vwap", 0) * 0.3
                        signal_score += score_contribution
                        reasons.append(
                            f"VWAP: Bearish crossover detected (Score {score_contribution:.2f})",
                        )

        # PSAR
        if active_indicators.get("psar", False):
            psar_val = self._get_indicator_value("PSAR_Val")
            psar_dir = self._get_indicator_value("PSAR_Dir")
            if not pd.isna(psar_val) and not pd.isna(psar_dir):
                if psar_dir == 1:
                    score_contribution = weights.get("psar", 0) * 0.5
                    signal_score += score_contribution
                    reasons.append(
                        f"PSAR: Bullish trend (Score +{score_contribution:.2f})",
                    )
                elif psar_dir == -1:
                    score_contribution = -weights.get("psar", 0) * 0.5
                    signal_score += score_contribution
                    reasons.append(
                        f"PSAR: Bearish trend (Score {score_contribution:.2f})",
                    )

                if len(self.df) > 1:
                    prev_psar_val = Decimal(str(self.df["PSAR_Val"].iloc[-2]))
                    if current_close > psar_val and prev_close <= prev_psar_val:
                        score_contribution = weights.get("psar", 0) * 0.4
                        signal_score += score_contribution
                        reasons.append(
                            f"PSAR: Bullish reversal detected (Score +{score_contribution:.2f})",
                        )
                    elif current_close < psar_val and prev_close >= prev_psar_val:
                        score_contribution = -weights.get("psar", 0) * 0.4
                        signal_score += score_contribution
                        reasons.append(
                            f"PSAR: Bearish reversal detected (Score {score_contribution:.2f})",
                        )

        # Orderbook Imbalance
        if active_indicators.get("orderbook_imbalance", False) and orderbook_data:
            imbalance = self._check_orderbook(current_price, orderbook_data)
            score_contribution = imbalance * weights.get("orderbook_imbalance", 0)
            signal_score += score_contribution
            reasons.append(
                f"Orderbook Imbalance: {imbalance:.2f} (Score {score_contribution:.2f})",
            )

        # Fibonacci Levels (confluence with price action)
        if active_indicators.get("fibonacci_levels", False) and self.fib_levels:
            for level_name, level_price in self.fib_levels.items():
                if level_name not in ["0.0%", "100.0%"] and abs(
                    current_price - level_price,
                ) / current_price < Decimal("0.001"):
                    self.logger.debug(
                        f"Price near Fibonacci level {level_name}: {level_price}",
                    )
                    if len(self.df) > 1:
                        if current_close > prev_close and current_close > level_price:
                            score_contribution = (
                                weights.get("fibonacci_levels", 0) * 0.1
                            )
                            signal_score += score_contribution
                            reasons.append(
                                f"Fibonacci: Bullish bounce from {level_name} (Score +{score_contribution:.2f})",
                            )
                        elif current_close < prev_close and current_close < level_price:
                            score_contribution = (
                                -weights.get("fibonacci_levels", 0) * 0.1
                            )
                            signal_score += score_contribution
                            reasons.append(
                                f"Fibonacci: Bearish rejection from {level_name} (Score {score_contribution:.2f})",
                            )

        # --- Ehlers SuperTrend Alignment Scoring ---
        if active_indicators.get("ehlers_supertrend", False):
            st_fast_dir = self._get_indicator_value("ST_Fast_Dir")
            st_slow_dir = self._get_indicator_value("ST_Slow_Dir")
            prev_st_fast_dir = (
                self.df["st_fast_dir"].iloc[-2]
                if "st_fast_dir" in self.df.columns and len(self.df) > 1
                else np.nan
            )
            weight = weights.get("ehlers_supertrend_alignment", 0.0)

            if (
                not pd.isna(st_fast_dir)
                and not pd.isna(st_slow_dir)
                and not pd.isna(prev_st_fast_dir)
            ):
                if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1:
                    score_contribution = weight
                    signal_score += score_contribution
                    reasons.append(
                        f"Ehlers SuperTrend: Strong BUY (fast flip aligned with slow trend) (Score +{score_contribution:.2f})",
                    )
                elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1:
                    score_contribution = -weight
                    signal_score += score_contribution
                    reasons.append(
                        f"Ehlers SuperTrend: Strong SELL (fast flip aligned with slow trend) (Score {score_contribution:.2f})",
                    )
                elif st_slow_dir == 1 and st_fast_dir == 1:
                    score_contribution = weight * 0.3
                    signal_score += score_contribution
                    reasons.append(
                        f"Ehlers SuperTrend: Bullish alignment (Score +{score_contribution:.2f})",
                    )
                elif st_slow_dir == -1 and st_fast_dir == -1:
                    score_contribution = -weight * 0.3
                    signal_score += score_contribution
                    reasons.append(
                        f"Ehlers SuperTrend: Bearish alignment (Score {score_contribution:.2f})",
                    )

        # --- MACD Alignment Scoring ---
        if active_indicators.get("macd", False):
            macd_line = self._get_indicator_value("MACD_Line")
            signal_line = self._get_indicator_value("MACD_Signal")
            histogram = self._get_indicator_value("MACD_Hist")
            weight = weights.get("macd_alignment", 0.0)

            if (
                not pd.isna(macd_line)
                and not pd.isna(signal_line)
                and not pd.isna(histogram)
                and len(self.df) > 1
            ):
                if (
                    macd_line > signal_line
                    and self.df["MACD_Line"].iloc[-2] <= self.df["MACD_Signal"].iloc[-2]
                ):
                    score_contribution = weight
                    signal_score += score_contribution
                    reasons.append(
                        f"MACD: Bullish crossover (Score +{score_contribution:.2f})",
                    )
                elif (
                    macd_line < signal_line
                    and self.df["MACD_Line"].iloc[-2] >= self.df["MACD_Signal"].iloc[-2]
                ):
                    score_contribution = -weight
                    signal_score += score_contribution
                    reasons.append(
                        f"MACD: Bearish crossover (Score {score_contribution:.2f})",
                    )
                elif histogram > 0 and self.df["MACD_Hist"].iloc[-2] < 0:
                    score_contribution = weight * 0.2
                    signal_score += score_contribution
                    reasons.append(
                        f"MACD: Bullish histogram flip (Score +{score_contribution:.2f})",
                    )
                elif histogram < 0 and self.df["MACD_Hist"].iloc[-2] > 0:
                    score_contribution = -weight * 0.2
                    signal_score += score_contribution
                    reasons.append(
                        f"MACD: Bearish histogram flip (Score {score_contribution:.2f})",
                    )

        # --- ADX Alignment Scoring ---
        if active_indicators.get("adx", False):
            adx_val = self._get_indicator_value("ADX")
            plus_di = self._get_indicator_value("PlusDI")
            minus_di = self._get_indicator_value("MinusDI")
            weight = weights.get("adx_strength", 0.0)

            if not pd.isna(adx_val) and not pd.isna(plus_di) and not pd.isna(minus_di):
                if adx_val > ADX_STRONG_TREND_THRESHOLD:
                    if plus_di > minus_di:
                        score_contribution = weight
                        signal_score += score_contribution
                        reasons.append(
                            f"ADX: Strong BUY trend (ADX > 25, +DI > -DI) (Score +{score_contribution:.2f})",
                        )
                    elif minus_di > plus_di:
                        score_contribution = -weight
                        signal_score += score_contribution
                        reasons.append(
                            f"ADX: Strong SELL trend (ADX > 25, -DI > +DI) (Score {score_contribution:.2f})",
                        )
                elif adx_val < ADX_WEAK_TREND_THRESHOLD:
                    reasons.append("ADX: Weak trend (ADX < 20). Neutral signal.")

        # --- Ichimoku Cloud Alignment Scoring ---
        if active_indicators.get("ichimoku_cloud", False):
            tenkan_sen = self._get_indicator_value("Tenkan_Sen")
            kijun_sen = self._get_indicator_value("Kijun_Sen")
            senkou_span_a = self._get_indicator_value("Senkou_Span_A")
            senkou_span_b = self._get_indicator_value("Senkou_Span_B")
            chikou_span = self._get_indicator_value("Chikou_Span")
            weight = weights.get("ichimoku_confluence", 0.0)

            if (
                not pd.isna(tenkan_sen)
                and not pd.isna(kijun_sen)
                and not pd.isna(senkou_span_a)
                and not pd.isna(senkou_span_b)
                and not pd.isna(chikou_span)
                and len(self.df) > 1
            ):
                if (
                    tenkan_sen > kijun_sen
                    and self.df["Tenkan_Sen"].iloc[-2] <= self.df["Kijun_Sen"].iloc[-2]
                ):
                    score_contribution = weight * 0.5
                    signal_score += score_contribution
                    reasons.append(
                        f"Ichimoku: Tenkan-sen crossed above Kijun-sen (bullish) (Score +{score_contribution:.2f})",
                    )
                elif (
                    tenkan_sen < kijun_sen
                    and self.df["Tenkan_Sen"].iloc[-2] >= self.df["Kijun_Sen"].iloc[-2]
                ):
                    score_contribution = -weight * 0.5
                    signal_score += score_contribution
                    reasons.append(
                        f"Ichimoku: Tenkan-sen crossed below Kijun-sen (bearish) (Score {score_contribution:.2f})",
                    )

                if current_close > max(senkou_span_a, senkou_span_b) and self.df[
                    "close"
                ].iloc[-2] <= max(
                    self.df["Senkou_Span_A"].iloc[-2],
                    self.df["Senkou_Span_B"].iloc[-2],
                ):
                    score_contribution = weight * 0.7
                    signal_score += score_contribution
                    reasons.append(
                        f"Ichimoku: Price broke above Kumo (strong bullish) (Score +{score_contribution:.2f})",
                    )
                elif current_close < min(senkou_span_a, senkou_span_b) and self.df[
                    "close"
                ].iloc[-2] >= min(
                    self.df["Senkou_Span_A"].iloc[-2],
                    self.df["Senkou_Span_B"].iloc[-2],
                ):
                    score_contribution = -weight * 0.7
                    signal_score += score_contribution
                    reasons.append(
                        f"Ichimoku: Price broke below Kumo (strong bearish) (Score {score_contribution:.2f})",
                    )

                if (
                    chikou_span > current_close
                    and self.df["Chikou_Span"].iloc[-2] <= self.df["close"].iloc[-2]
                ):
                    score_contribution = weight * 0.3
                    signal_score += score_contribution
                    reasons.append(
                        f"Ichimoku: Chikou Span crossed above price (bullish confirmation) (Score +{score_contribution:.2f})",
                    )
                elif (
                    chikou_span < current_close
                    and self.df["Chikou_Span"].iloc[-2] >= self.df["close"].iloc[-2]
                ):
                    score_contribution = -weight * 0.3
                    signal_score += score_contribution
                    reasons.append(
                        f"Ichimoku: Chikou Span crossed below price (bearish confirmation) (Score {score_contribution:.2f})",
                    )

        # --- OBV Alignment Scoring ---
        if active_indicators.get("obv", False):
            obv_val = self._get_indicator_value("OBV")
            obv_ema = self._get_indicator_value("OBV_EMA")
            weight = weights.get("obv_momentum", 0.0)

            if not pd.isna(obv_val) and not pd.isna(obv_ema) and len(self.df) > 1:
                if (
                    obv_val > obv_ema
                    and self.df["OBV"].iloc[-2] <= self.df["OBV_EMA"].iloc[-2]
                ):
                    score_contribution = weight * 0.5
                    signal_score += score_contribution
                    reasons.append(
                        f"OBV: Bullish crossover (Score +{score_contribution:.2f})",
                    )
                elif (
                    obv_val < obv_ema
                    and self.df["OBV"].iloc[-2] >= self.df["OBV_EMA"].iloc[-2]
                ):
                    score_contribution = -weight * 0.5
                    signal_score += score_contribution
                    reasons.append(
                        f"OBV: Bearish crossover (Score {score_contribution:.2f})",
                    )

                if len(self.df) > 2:
                    if (
                        obv_val > self.df["OBV"].iloc[-2]
                        and obv_val > self.df["OBV"].iloc[-3]
                    ):
                        score_contribution = weight * 0.2
                        signal_score += score_contribution
                        reasons.append(
                            f"OBV: Increasing momentum (Score +{score_contribution:.2f})",
                        )
                    elif (
                        obv_val < self.df["OBV"].iloc[-2]
                        and obv_val < self.df["OBV"].iloc[-3]
                    ):
                        score_contribution = -weight * 0.2
                        signal_score += score_contribution
                        reasons.append(
                            f"OBV: Decreasing momentum (Score {score_contribution:.2f})",
                        )

        # --- CMF Alignment Scoring ---
        if active_indicators.get("cmf", False):
            cmf_val = self._get_indicator_value("CMF")
            weight = weights.get("cmf_flow", 0.0)

            if not pd.isna(cmf_val):
                if cmf_val > 0:
                    score_contribution = weight * 0.5
                    signal_score += score_contribution
                    reasons.append(
                        f"CMF: Positive money flow (Score +{score_contribution:.2f})",
                    )
                elif cmf_val < 0:
                    score_contribution = -weight * 0.5
                    signal_score += score_contribution
                    reasons.append(
                        f"CMF: Negative money flow (Score {score_contribution:.2f})",
                    )

                if len(self.df) > 2:
                    if (
                        cmf_val > self.df["CMF"].iloc[-2]
                        and cmf_val > self.df["CMF"].iloc[-3]
                    ):
                        score_contribution = weight * 0.3
                        signal_score += score_contribution
                        reasons.append(
                            f"CMF: Increasing money flow (Score +{score_contribution:.2f})",
                        )
                    elif (
                        cmf_val < self.df["CMF"].iloc[-2]
                        and cmf_val < self.df["CMF"].iloc[-3]
                    ):
                        score_contribution = -weight * 0.3
                        signal_score += score_contribution
                        reasons.append(
                            f"CMF: Decreasing money flow (Score {score_contribution:.2f})",
                        )

        # --- Volatility Index Scoring ---
        if active_indicators.get("volatility_index", False):
            vol_idx = self._get_indicator_value("Volatility_Index")
            weight = weights.get("volatility_index_signal", 0.0)
            if not pd.isna(vol_idx):
                if len(self.df) > 2 and "Volatility_Index" in self.df.columns:
                    prev_vol_idx = self.df["Volatility_Index"].iloc[-2]
                    prev_prev_vol_idx = self.df["Volatility_Index"].iloc[-3]

                    if (
                        vol_idx > prev_vol_idx > prev_prev_vol_idx
                    ):  # Increasing volatility
                        if signal_score > 0:
                            score_contribution = weight * 0.2
                            signal_score += score_contribution
                            reasons.append(
                                f"Volatility Index: Increasing volatility, reinforcing BUY (Score +{score_contribution:.2f})",
                            )
                        elif signal_score < 0:
                            score_contribution = -weight * 0.2
                            signal_score += score_contribution
                            reasons.append(
                                f"Volatility Index: Increasing volatility, reinforcing SELL (Score {score_contribution:.2f})",
                            )
                    elif (
                        vol_idx < prev_vol_idx < prev_prev_vol_idx
                    ):  # Decreasing volatility
                        if (
                            abs(signal_score) > 0
                        ):  # If there's an existing signal, slightly reduce it
                            signal_score *= Decimal("0.8")
                            reasons.append(
                                "Volatility Index: Decreasing volatility, reducing signal conviction.",
                            )

        # --- VWMA Cross Scoring ---
        if active_indicators.get("vwma", False):
            vwma = self._get_indicator_value("VWMA")
            weight = weights.get("vwma_cross", 0.0)
            if not pd.isna(vwma) and len(self.df) > 1:
                prev_vwma = self.df["VWMA"].iloc[-2]
                if current_close > vwma and prev_close <= prev_vwma:
                    score_contribution = weight
                    signal_score += score_contribution
                    reasons.append(
                        f"VWMA: Bullish crossover (price above VWMA) (Score +{score_contribution:.2f})",
                    )
                elif current_close < vwma and prev_close >= prev_vwma:
                    score_contribution = -weight
                    signal_score += score_contribution
                    reasons.append(
                        f"VWMA: Bearish crossover (price below VWMA) (Score {score_contribution:.2f})",
                    )

        # --- Volume Delta Scoring ---
        if active_indicators.get("volume_delta", False):
            volume_delta = self._get_indicator_value("Volume_Delta")
            volume_delta_threshold = isd["volume_delta_threshold"]
            weight = weights.get("volume_delta_signal", 0.0)

            if not pd.isna(volume_delta):
                if volume_delta > volume_delta_threshold:  # Strong buying pressure
                    score_contribution = weight
                    signal_score += score_contribution
                    reasons.append(
                        f"Volume Delta: Strong buying pressure (Score +{score_contribution:.2f})",
                    )
                elif volume_delta < -volume_delta_threshold:  # Strong selling pressure
                    score_contribution = -weight
                    signal_score += score_contribution
                    reasons.append(
                        f"Volume Delta: Strong selling pressure (Score {score_contribution:.2f})",
                    )
                elif volume_delta > 0:
                    score_contribution = weight * 0.3
                    signal_score += score_contribution
                    reasons.append(
                        f"Volume Delta: Moderate buying pressure (Score +{score_contribution:.2f})",
                    )
                elif volume_delta < 0:
                    score_contribution = -weight * 0.3
                    signal_score += score_contribution
                    reasons.append(
                        f"Volume Delta: Moderate selling pressure (Score {score_contribution:.2f})",
                    )

        # --- Multi-Timeframe Trend Confluence Scoring ---
        if self.config["mtf_analysis"]["enabled"] and mtf_trends:
            mtf_buy_score = 0
            mtf_sell_score = 0
            for _tf_indicator, trend in mtf_trends.items():
                if trend == "UP":
                    mtf_buy_score += 1
                elif trend == "DOWN":
                    mtf_sell_score += 1

            mtf_weight = weights.get("mtf_trend_confluence", 0.0)
            if mtf_trends:
                # Calculate a normalized score based on the balance of buy/sell trends
                normalized_mtf_score = (mtf_buy_score - mtf_sell_score) / len(
                    mtf_trends,
                )
                score_contribution = mtf_weight * normalized_mtf_score
                signal_score += score_contribution
                reasons.append(
                    f"MTF Confluence: Score {normalized_mtf_score:.2f} (Buy: {mtf_buy_score}, Sell: {mtf_sell_score}). Total MTF contribution: {score_contribution:.2f}",
                )

        # --- Final Signal Determination ---
        threshold = self.config["signal_score_threshold"]
        final_signal = "HOLD"
        if signal_score >= threshold:
            final_signal = "BUY"
        elif signal_score <= -threshold:
            final_signal = "SELL"

        self.logger.info(f"{NEON_YELLOW}--- Trade Reasoning ---{RESET}")
        for reason in reasons:
            self.logger.info(f"  - {reason}")
        self.logger.info(
            f"{NEON_YELLOW}Raw Signal Score: {signal_score:.2f}, Final Signal: {final_signal}{RESET}",
        )
        return final_signal, signal_score

    def calculate_entry_tp_sl(
        self,
        current_price: Decimal,
        atr_value: Decimal,
        signal: Literal["BUY", "SELL"],
    ) -> tuple[Decimal, Decimal]:
        """Calculate Take Profit and Stop Loss levels."""
        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"]),
        )
        take_profit_atr_multiple = Decimal(
            str(self.config["trade_management"]["take_profit_atr_multiple"]),
        )
        price_precision_str = (
            "0." + "0" * (self.config["trade_management"]["price_precision"] - 1) + "1"
        )

        if signal == "BUY":
            stop_loss = current_price - (atr_value * stop_loss_atr_multiple)
            take_profit = current_price + (atr_value * take_profit_atr_multiple)
        elif signal == "SELL":
            stop_loss = current_price + (atr_value * stop_loss_atr_multiple)
            take_profit = current_price - (atr_value * take_profit_atr_multiple)
        else:
            return Decimal("0"), Decimal("0")  # Should not happen for valid signals

        return take_profit.quantize(
            Decimal(price_precision_str),
            rounding=ROUND_DOWN,
        ), stop_loss.quantize(Decimal(price_precision_str), rounding=ROUND_DOWN)


def display_indicator_values_and_price(
    config: dict[str, Any],
    logger: logging.Logger,
    current_price: Decimal,
    df: pd.DataFrame,
    orderbook_data: dict | None,
    mtf_trends: dict[str, str],
) -> None:
    """Display current price and calculated indicator values."""
    logger.info(f"{NEON_BLUE}--- Current Market Data & Indicators ---{RESET}")
    logger.info(f"{NEON_GREEN}Current Price: {current_price.normalize()}{RESET}")

    analyzer = TradingAnalyzer(df, config, logger, config["symbol"])

    if analyzer.df.empty:
        logger.warning(
            f"{NEON_YELLOW}Cannot display indicators: DataFrame is empty after calculations.{RESET}",
        )
        return

    logger.info(f"{NEON_CYAN}--- Indicator Values ---{RESET}")
    for indicator_name, value in analyzer.indicator_values.items():
        color = INDICATOR_COLORS.get(indicator_name, NEON_YELLOW)
        # Format Decimal values for consistent display
        if isinstance(value, Decimal):
            logger.info(f"  {color}{indicator_name}: {value.normalize()}{RESET}")
        elif isinstance(value, float):
            logger.info(f"  {color}{indicator_name}: {value:.8f}{RESET}")
        else:
            logger.info(f"  {color}{indicator_name}: {value}{RESET}")

    if analyzer.fib_levels:
        logger.info(f"{NEON_CYAN}--- Fibonacci Levels ---{RESET}")
        logger.info("")  # Added newline for spacing
        for level_name, level_price in analyzer.fib_levels.items():
            logger.info(
                f"  {NEON_YELLOW}{level_name}: {level_price.normalize()}{RESET}",
            )

    if mtf_trends:
        logger.info(f"{NEON_CYAN}--- Multi-Timeframe Trends ---{RESET}")
        logger.info("")  # Added newline for spacing
        for tf_indicator, trend in mtf_trends.items():
            logger.info(f"  {NEON_YELLOW}{tf_indicator}: {trend}{RESET}")

    logger.info(f"{NEON_BLUE}--------------------------------------{RESET}")


# --- Main Execution Logic ---
def main() -> None:
    """Orchestrate the bot's operation."""
    logger = setup_logger("wgwhalex_bot")
    config = load_config(CONFIG_FILE, logger)
    alert_system = AlertSystem(config, logger)

    # Validate interval format at startup
    valid_bybit_intervals = [
        "1",
        "3",
        "5",
        "15",
        "30",
        "60",
        "120",
        "240",
        "360",
        "720",
        "D",
        "W",
        "M",
    ]

    if config["interval"] not in valid_bybit_intervals:
        logger.error(
            f"{NEON_RED}Invalid primary interval '{config['interval']}' in config.json. Please use Bybit's valid string formats (e.g., '15', '60', 'D'). Exiting.{RESET}",
        )
        sys.exit(1)

    for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
        if htf_interval not in valid_bybit_intervals:
            logger.error(
                f"{NEON_RED}Invalid higher timeframe interval '{htf_interval}' in config.json. Please use Bybit's valid string formats (e.g., '60', '240'). Exiting.{RESET}",
            )
            sys.exit(1)

    logger.info(f"{NEON_GREEN}--- Wgwhalex Trading Bot Initialized ---{RESET}")
    logger.info(f"Symbol: {config['symbol']}, Interval: {config['interval']}")
    logger.info(f"Trade Management Enabled: {config['trade_management']['enabled']}")

    pybit_http_client = create_pybit_client(testnet=False)  # Main HTTP client
    position_manager = PositionManagerPybit(config, logger, config["symbol"])
    performance_tracker = PerformanceTracker(logger)

    # Setup WebSocket Manager
    ws_manager = BybitWebSocketManager(
        API_KEY,
        API_SECRET,
        testnet=False,
        logger=logger,
    )

    # Callbacks for RealTimePositionTracker
    position_tracker_instance = RealTimePositionTracker(
        ws_manager,
        pybit_http_client,
        logger,
    )
    private_ws_callbacks = {
        "position_update": position_tracker_instance.handle_position_update,
        "order_update": position_tracker_instance.handle_order_update,
        "execution_update": position_tracker_instance.handle_execution,
        "wallet_update": position_tracker_instance.handle_wallet_update,
    }

    # Start WebSocket threads
    ws_manager.start_public_websocket_thread(config["symbol"], config["interval"])
    # Start WS for higher timeframes as well
    for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
        ws_manager.start_public_websocket_thread(config["symbol"], htf_interval)

    ws_manager.start_private_websocket_thread(private_ws_callbacks)

    # Give some time for WS connections to establish and initial data to be received
    logger.info(f"{NEON_BLUE}Waiting for WebSocket data to populate...{RESET}")
    time.sleep(10)  # Adjust as needed based on network/API speed

    while True:
        try:
            logger.info(
                f"{NEON_PURPLE}--- New Analysis Loop Started ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}) ---{RESET}",
            )

            # --- Fetch data from WebSocket buffers ---
            current_price = ws_manager.get_current_price(config["symbol"])
            if current_price is None:
                alert_system.send_alert(
                    f"[{config['symbol']}] Failed to get current price from WebSocket. Skipping loop.",
                    "WARNING",
                )
                time.sleep(config["loop_delay"])
                continue

            # Get primary timeframe klines from WS buffer
            df = ws_manager.get_kline_df(config["symbol"], config["interval"])
            if (
                df is None or df.empty or len(df) < 200
            ):  # Ensure enough data for indicators
                alert_system.send_alert(
                    f"[{config['symbol']}] Not enough primary kline data from WebSocket buffer ({len(df) if df is not None else 0} bars). Skipping loop.",
                    "WARNING",
                )
                time.sleep(config["loop_delay"])
                continue

            # Get orderbook data from WS snapshot
            orderbook_data = None
            if config["indicators"].get("orderbook_imbalance", False):
                orderbook_data = ws_manager.get_orderbook(config["symbol"])
                if orderbook_data is None:
                    logger.warning(
                        f"{NEON_YELLOW}Orderbook data not yet available from WebSocket.{RESET}",
                    )

            mtf_trends: dict[str, str] = {}
            if config["mtf_analysis"]["enabled"]:
                for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
                    logger.debug(
                        f"Fetching klines for MTF interval from WS buffer: {htf_interval}",
                    )
                    htf_df = ws_manager.get_kline_df(config["symbol"], htf_interval)
                    if (
                        htf_df is not None
                        and not htf_df.empty
                        and len(htf_df) >= config["mtf_analysis"]["trend_period"] * 3
                    ):
                        for trend_ind in config["mtf_analysis"]["trend_indicators"]:
                            temp_htf_analyzer = TradingAnalyzer(
                                htf_df,
                                config,
                                logger,
                                config["symbol"],
                            )
                            trend = temp_htf_analyzer._get_mtf_trend(
                                temp_htf_analyzer.df,
                                trend_ind,
                            )
                            mtf_trends[f"{htf_interval}_{trend_ind}"] = trend
                            logger.debug(
                                f"MTF Trend ({htf_interval}, {trend_ind}): {trend}",
                            )
                    else:
                        logger.warning(
                            f"{NEON_YELLOW}Not enough klines for higher timeframe {htf_interval} from WS buffer or it was empty. Skipping MTF trend for this TF.{RESET}",
                        )
                    # No explicit sleep here for MTF requests, as WS provides async updates.
                    # The `ws_manager.kline_buffer` is updated by the WS threads.

            display_indicator_values_and_price(
                config,
                logger,
                current_price,
                df,
                orderbook_data,
                mtf_trends,
            )

            analyzer = TradingAnalyzer(df, config, logger, config["symbol"])

            if analyzer.df.empty:
                alert_system.send_alert(
                    f"[{config['symbol']}] TradingAnalyzer DataFrame is empty after indicator calculations. Cannot generate signal.",
                    "WARNING",
                )
                time.sleep(config["loop_delay"])
                continue

            trading_signal, signal_score = analyzer.generate_trading_signal(
                current_price,
                orderbook_data,
                mtf_trends,
            )
            atr_value = Decimal(
                str(analyzer._get_indicator_value("ATR", Decimal("0.01"))),
            )  # Default to a small positive value if ATR is missing

            # Use pybit-specific position manager
            position_manager.manage_positions(current_price, performance_tracker)

            if (
                trading_signal == "BUY"
                and signal_score >= config["signal_score_threshold"]
            ):
                logger.info(
                    f"{NEON_GREEN}Strong BUY signal detected! Score: {signal_score:.2f}{RESET}",
                )
                position_manager.open_position("BUY", current_price, atr_value)
            elif (
                trading_signal == "SELL"
                and signal_score <= -config["signal_score_threshold"]
            ):
                logger.info(
                    f"{NEON_RED}Strong SELL signal detected! Score: {signal_score:.2f}{RESET}",
                )
                position_manager.open_position("SELL", current_price, atr_value)
            else:
                logger.info(
                    f"{NEON_BLUE}No strong trading signal. Holding. Score: {signal_score:.2f}{RESET}",
                )

            # Fetch actual open positions from exchange via HTTP client (or use WS cache)
            # For this example, we'll fetch from HTTP as position_manager uses it
            open_positions_raw = get_positions_pybit(
                pybit_http_client,
                config["symbol"],
                logger,
            )
            open_positions = [
                p for p in open_positions_raw if Decimal(p["size"]) > 0
            ]  # Filter for actually open positions

            if open_positions:
                logger.info(f"{NEON_CYAN}Open Positions: {len(open_positions)}{RESET}")
                for pos in open_positions:
                    logger.info(
                        f"  - {pos['side']} {pos['size']} @ {pos['avgPrice']} (Liq. Price: {pos['liqPrice']}){RESET}",
                    )
            else:
                logger.info(f"{NEON_CYAN}No open positions.{RESET}")

            # Note: PerformanceTracker here still relies on simulated trades for the example,
            # for a real bot you'd hook it up to actual exchange trade executions/history.
            # The `RealTimePositionTracker.handle_execution` is the place to integrate
            # `performance_tracker.record_trade` with real exchange trade data.
            # For now, the summary will only reflect manually recorded trades if any.
            perf_summary = performance_tracker.get_summary()
            logger.info(
                f"{NEON_YELLOW}Performance Summary: Total PnL: {perf_summary['total_pnl'].normalize():.2f}, Wins: {perf_summary['wins']}, Losses: {perf_summary['losses']}, Win Rate: {perf_summary['win_rate']}{RESET}",
            )

            logger.info(
                f"{NEON_PURPLE}--- Analysis Loop Finished. Waiting {config['loop_delay']}s ---{RESET}",
            )
            time.sleep(config["loop_delay"])

        except Exception as e:
            alert_system.send_alert(
                f"[{config['symbol']}] An unhandled error occurred in the main loop: {e}",
                "ERROR",
            )
            logger.exception(f"{NEON_RED}Unhandled exception in main loop:{RESET}")
            time.sleep(config["loop_delay"] * 2)


if __name__ == "__main__":
    main()
