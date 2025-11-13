import asyncio
import json
import logging
import os
import sys
import warnings
from datetime import UTC
from datetime import datetime
from decimal import Decimal
from decimal import getcontext
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from typing import ClassVar
from typing import Literal

# Import async CCXT
import ccxt.async_support as ccxt
import numpy as np
import pandas as pd
import pandas_ta as ta
from colorama import Fore
from colorama import Style
from colorama import init
from dotenv import load_dotenv
from pytz import UTC  # Assuming pytz for UTC, common in financial applications

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# Initialize colorama and set decimal precision
getcontext().prec = 28  # High precision for financial calculations
init(autoreset=True)
load_dotenv()

# --- Constants ---
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
# BASE_URL is now managed by CCXT
CONFIG_FILE = "config.json"
LOG_DIRECTORY = "bot_logs/trading-bot/logs"
Path(LOG_DIRECTORY).mkdir(parents=True, exist_ok=True)

# Using UTC for consistency and to avoid timezone issues with API timestamps
TIMEZONE = UTC
# CCXT handles rate limiting and retries, but a global timeout is still good
REQUEST_TIMEOUT = 30
LOOP_DELAY_SECONDS = 15
WS_RECONNECT_DELAY_SECONDS = 5
API_CALL_RETRY_DELAY_SECONDS = (
    3  # Used for individual CCXT calls if specific retries are needed
)

# Magic Numbers as Constants (expanded and named for clarity)
MIN_DATA_POINTS_TRUE_RANGE = 2
MIN_DATA_POINTS_SUPERSMOOTHER = 2
MIN_DATA_POINTS_OBV = 2
MIN_DATA_POINTS_PSAR_INITIAL = 4  # PSAR needs a few points to initialize reliably
ADX_STRONG_TREND_THRESHOLD = 25
ADX_WEAK_TREND_THRESHOLD = 20
MIN_DATA_POINTS_VWMA = 2
MIN_DATA_POINTS_VOLATILITY = 2
MIN_DATA_POINTS_VOLUME_DELTA = 2  # Volume Delta requires at least 2 bars for comparison

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


# --- Configuration Management ---
def load_config(filepath: str, logger: logging.Logger) -> dict[str, Any]:
    """Load configuration from JSON file, creating a default if not found."""
    default_config = {
        # Core Settings
        "symbol": "BTCUSDT",
        "interval": "15m",  # Bybit CCXT uses '15m', '1h', '4h', '1d', etc.
        "loop_delay": LOOP_DELAY_SECONDS,
        "orderbook_limit": 50,
        "testnet": True,
        "timezone": "America/Chicago",
        # Signal Generation
        "signal_score_threshold": 2.0,
        "volume_confirmation_multiplier": 1.5,
        # Position & Risk Management
        "trade_management": {
            "enabled": True,
            "account_balance": 1000.0,  # Simulated balance if not using real API
            "risk_per_trade_percent": 1.0,  # Percentage of account_balance to risk
            "stop_loss_atr_multiple": 1.5,  # Stop loss distance as multiple of ATR
            "take_profit_atr_multiple": 2.0,  # Take profit distance as multiple of ATR
            "trailing_stop_atr_multiple": 0.3,  # Trailing stop distance as multiple of ATR
            "max_open_positions": 1,
            "order_precision": 4,  # Decimal places for order quantity (fallback, CCXT will fetch live)
            "price_precision": 2,  # Decimal places for price (fallback, CCXT will fetch live)
            "leverage": 10,  # Leverage for perpetual contracts
            "order_mode": "MARKET",  # MARKET or LIMIT for entry orders
            "take_profit_type": "MARKET",  # MARKET or LIMIT for TP
            "stop_loss_type": "MARKET",  # MARKET or LIMIT for SL
            "trailing_stop_activation_percent": 0.5,  # % profit to activate trailing stop
        },
        # Multi-Timeframe Analysis
        "mtf_analysis": {
            "enabled": True,
            "higher_timeframes": ["1h", "4h"],  # Bybit CCXT intervals
            "trend_indicators": ["ema", "ehlers_supertrend"],
            "trend_period": 50,  # Period for MTF trend indicators like SMA/EMA
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
            "feature_lags": [1, 2, 3, 5],  # Added default values
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
            "volatility_index_period": 20,
            "vwma_period": 20,
            "volume_delta_period": 5,
            "volume_delta_threshold": 0.2,
            "vwap_daily_reset": False,  # Should VWAP reset daily or be continuous
        },
        # Active Indicators & Weights (expanded)
        "indicators": {
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
            "volatility_index": True,
            "vwma": True,
            "volume_delta": True,
        },
        "weight_sets": {
            "default_scalping": {
                "ema_alignment": 0.22,
                "sma_trend_filter": 0.28,
                "momentum_rsi_stoch_cci_wr_mfi": 0.18,
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
                "volatility_index_signal": 0.15,
                "vwma_cross": 0.15,
                "volume_delta_signal": 0.10,
            },
        },
        # Gemini AI Analysis (Optional)
        "gemini_ai_analysis": {
            "enabled": False,
            "model_name": "gemini-1.0-pro",
            "temperature": 0.7,
            "top_p": 0.9,
            "weight": 0.3,  # Weight of Gemini's signal in the final score
        },
    }
    if not Path(filepath).exists():
        try:
            with Path(filepath).open("w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)
            logger.warning(
                f"{NEON_YELLOW}Configuration file not found. "
                f"Created default config at {filepath} for symbol "
                f"{default_config['symbol']}{RESET}",
            )
            return default_config
        except OSError as e:
            logger.error(f"{NEON_RED}Error creating default config file: {e}{RESET}")
            return default_config

    try:
        with Path(filepath).open(encoding="utf-8") as f:
            config = json.load(f)
        _ensure_config_keys(config, default_config)
        # Save updated config to include any newly added default keys
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


# --- CCXT Exchange Wrapper ---
class ExchangeClient:
    """Wrapper for CCXT exchange functionalities."""

    def __init__(
        self,
        exchange_id: str,
        api_key: str,
        api_secret: str,
        testnet: bool,
        logger: logging.Logger,
    ):
        """Initializes the ExchangeClient with CCXT."""
        self.logger = logger
        self.exchange_id = exchange_id
        self.symbol_to_ccxt = {}  # Cache for CCXT symbol conversion
        self.markets_loaded = False

        try:
            exchange_class = getattr(ccxt, exchange_id)
            self.exchange = exchange_class(
                {
                    "apiKey": api_key,
                    "secret": api_secret,
                    "enableRateLimit": True,
                    "options": {
                        "defaultType": "linear",  # Assuming perpetual futures
                        "adjustForTimeDifference": True,
                    },
                    "timeout": REQUEST_TIMEOUT * 1000,  # CCXT timeout is in ms
                },
            )
            if testnet:
                self.exchange.set_sandbox_mode(True)
                self.logger.info(
                    f"{NEON_YELLOW}CCXT {exchange_id} set to sandbox mode.{RESET}",
                )

            self.logger.info(
                f"{NEON_GREEN}CCXT {exchange_id} client initialized.{RESET}",
            )
        except Exception as e:
            self.logger.critical(
                f"{NEON_RED}Failed to initialize CCXT exchange client: {e}{RESET}",
            )
            sys.exit(1)

    async def load_markets(self) -> None:
        """Loads market data from the exchange."""
        if not self.markets_loaded:
            try:
                await self.exchange.load_markets()
                self.markets_loaded = True
                self.logger.info(
                    f"{NEON_GREEN}Markets loaded for {self.exchange_id}.{RESET}",
                )

                # Pre-build a mapping for common symbols like BTCUSDT -> BTC/USDT
                for market_id, market_data in self.exchange.markets_by_id.items():
                    if market_id.endswith("USDT"):  # Common pattern for perp markets
                        self.symbol_to_ccxt[market_id] = market_data["symbol"]

            except Exception as e:
                self.logger.error(f"{NEON_RED}Failed to load markets: {e}{RESET}")
                # Markets not loaded, might need to retry or stop
                self.markets_loaded = False

    def get_ccxt_symbol(self, bybit_symbol: str) -> str:
        """Converts a Bybit symbol (e.g., BTCUSDT) to a CCXT symbol (e.g., BTC/USDT)."""
        if not self.markets_loaded:
            self.logger.warning(
                f"Markets not loaded, cannot convert symbol {bybit_symbol}.",
            )
            return bybit_symbol  # Return original, hope it works or fails later

        # Check cache first
        if bybit_symbol in self.symbol_to_ccxt:
            return self.symbol_to_ccxt[bybit_symbol]

        # Attempt to find it
        for market in self.exchange.markets.values():
            if market["id"] == bybit_symbol:
                self.symbol_to_ccxt[bybit_symbol] = market["symbol"]
                return market["symbol"]

            # For futures, sometimes CCXT symbol is different, e.g., BTC/USDT:USDT
            # Bybit often just uses BTCUSDT (ID) for perpetual.
            # Let's assume for now Bybit symbol is the market ID.
            # Example: bybit_symbol = 'BTCUSDT' (market ID) -> market['symbol'] = 'BTC/USDT'
            if market["symbol"].replace("/", "") == bybit_symbol:  # crude heuristic
                self.symbol_to_ccxt[bybit_symbol] = market["symbol"]
                return market["symbol"]

        self.logger.warning(
            f"{NEON_YELLOW}Could not find CCXT symbol for Bybit symbol: {bybit_symbol}. Using as is.{RESET}",
        )
        return bybit_symbol  # Fallback to using the Bybit symbol directly

    async def fetch_current_price(self, symbol: str) -> Decimal | None:
        """Fetch the current market price for a symbol using CCXT."""
        ccxt_symbol = self.get_ccxt_symbol(symbol)
        try:
            ticker = await self.exchange.fetch_ticker(ccxt_symbol)
            price = Decimal(str(ticker["last"]))
            self.logger.debug(f"Fetched current price for {symbol}: {price}")
            return price
        except ccxt.ExchangeError as e:
            self.logger.error(
                f"{NEON_RED}CCXT Exchange Error fetching ticker for {symbol}: {e}{RESET}",
            )
        except Exception as e:
            self.logger.error(
                f"{NEON_RED}Error fetching ticker for {symbol}: {e}{RESET}",
            )
        return None

    async def fetch_klines(
        self,
        symbol: str,
        interval: str,
        limit: int,
    ) -> pd.DataFrame | None:
        """Fetch kline data for a symbol and interval using CCXT."""
        ccxt_symbol = self.get_ccxt_symbol(symbol)
        try:
            ohlcv = await self.exchange.fetch_ohlcv(ccxt_symbol, interval, limit=limit)
            if not ohlcv:
                self.logger.warning(
                    f"{NEON_YELLOW}Fetched klines for {symbol} {interval} but received empty list.{RESET}",
                )
                return None

            df = pd.DataFrame(
                ohlcv,
                columns=["timestamp", "open", "high", "low", "close", "volume"],
            )
            df["start_time"] = pd.to_datetime(
                df["timestamp"],
                unit="ms",
                utc=True,
            ).dt.tz_convert(TIMEZONE)

            # Ensure volume is float for calculations
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            df.set_index("start_time", inplace=True)
            df.sort_index(inplace=True)

            # Drop rows with any NaN values in critical columns
            df.dropna(subset=["open", "high", "low", "close", "volume"], inplace=True)

            if df.empty:
                self.logger.warning(
                    f"{NEON_YELLOW}Fetched klines for {symbol} {interval} but DataFrame is empty after processing/cleaning.{RESET}",
                )
                return None

            self.logger.debug(f"Fetched {len(df)} {interval} klines for {symbol}.")
            return df
        except ccxt.ExchangeError as e:
            self.logger.error(
                f"{NEON_RED}CCXT Exchange Error fetching klines for {symbol} {interval}: {e}{RESET}",
            )
        except Exception as e:
            self.logger.error(
                f"{NEON_RED}Error fetching klines for {symbol} {interval}: {e}{RESET}",
            )
        return None

    async def fetch_orderbook(self, symbol: str, limit: int) -> dict | None:
        """Fetch orderbook data for a symbol using CCXT."""
        ccxt_symbol = self.get_ccxt_symbol(symbol)
        try:
            orderbook = await self.exchange.fetch_order_book(ccxt_symbol, limit=limit)
            self.logger.debug(f"Fetched orderbook for {symbol} with limit {limit}.")
            return orderbook
        except ccxt.ExchangeError as e:
            self.logger.error(
                f"{NEON_RED}CCXT Exchange Error fetching orderbook for {symbol}: {e}{RESET}",
            )
        except Exception as e:
            self.logger.error(
                f"{NEON_RED}Error fetching orderbook for {symbol}: {e}{RESET}",
            )
        return None

    async def get_wallet_balance(self, coin: str) -> Decimal | None:
        """Fetch wallet balance for a specific coin using CCXT."""
        try:
            balance = await self.exchange.fetch_balance()
            if coin in balance["free"]:
                coin_balance = Decimal(str(balance["free"][coin]))
                self.logger.debug(f"Fetched {coin} wallet balance: {coin_balance}")
                return coin_balance
            self.logger.warning(
                f"{NEON_YELLOW}Coin {coin} not found in balance.{RESET}",
            )
        except ccxt.ExchangeError as e:
            self.logger.error(
                f"{NEON_RED}CCXT Exchange Error fetching balance for {coin}: {e}{RESET}",
            )
        except Exception as e:
            self.logger.error(
                f"{NEON_RED}Error fetching balance for {coin}: {e}{RESET}",
            )
        return None

    async def get_exchange_open_positions(self, symbol: str) -> list[dict] | None:
        """Fetch currently open positions from the exchange using CCXT."""
        ccxt_symbol = self.get_ccxt_symbol(symbol)
        try:
            # Bybit positions might need specific params for linear/inverse
            positions = await self.exchange.fetch_positions(symbols=[ccxt_symbol])
            # Filter for non-zero size positions
            open_positions = [
                p for p in positions if Decimal(str(p["info"]["size"])) > 0
            ]
            return open_positions
        except ccxt.ExchangeError as e:
            self.logger.error(
                f"{NEON_RED}CCXT Exchange Error fetching positions for {symbol}: {e}{RESET}",
            )
        except Exception as e:
            self.logger.error(
                f"{NEON_RED}Error fetching positions for {symbol}: {e}{RESET}",
            )
        return []

    async def place_order(
        self,
        symbol: str,
        side: Literal["Buy", "Sell"],
        order_type: Literal["Market", "Limit"],
        qty: Decimal,
        price: Decimal | None = None,
        reduce_only: bool = False,
        take_profit: Decimal | None = None,
        stop_loss: Decimal | None = None,
        # tp_sl_mode: Literal["Full", "Partial"] = "Full", # CCXT handles this internally generally
        position_idx: int | None = None,
    ) -> dict | None:
        """Place an order on Bybit using CCXT."""
        ccxt_symbol = self.get_ccxt_symbol(symbol)
        ccxt_side = "buy" if side == "Buy" else "sell"
        ccxt_order_type = order_type.lower()

        params = {}
        if reduce_only:
            params["reduceOnly"] = True
        if take_profit is not None:
            params["takeProfit"] = float(take_profit)
        if stop_loss is not None:
            params["stopLoss"] = float(stop_loss)

        # Bybit v5 specific parameter for position mode (Hedge vs One-Way)
        # 1 for long (Buy), 2 for short (Sell) in Hedge Mode. 0 in One-Way.
        # This needs to align with the account's actual position mode setting.
        # CCXT tries to abstract this, but sometimes explicit parameters are needed.
        # For 'linear' default type, CCXT typically handles this if the account is in Hedge Mode.
        # params['positionIdx'] = position_idx # Only if explicit control is needed and not handled by CCXT

        try:
            if ccxt_order_type == "market":
                order = await self.exchange.create_order(
                    ccxt_symbol,
                    ccxt_order_type,
                    ccxt_side,
                    float(qty),  # CCXT expects float
                    price=None,
                    params=params,
                )
            else:  # Limit order
                if price is None:
                    self.logger.error(f"{NEON_RED}Limit order requires a price.{RESET}")
                    return None
                order = await self.exchange.create_order(
                    ccxt_symbol,
                    ccxt_order_type,
                    ccxt_side,
                    float(qty),
                    float(price),  # CCXT expects float
                    params=params,
                )
            self.logger.info(
                f"{NEON_GREEN}Order placed successfully for {symbol}: {order}{RESET}",
            )
            return order
        except ccxt.InsufficientFunds as e:
            self.logger.error(
                f"{NEON_RED}Insufficient funds to place order for {symbol}: {e}{RESET}",
            )
        except ccxt.InvalidOrder as e:
            self.logger.error(
                f"{NEON_RED}Invalid order parameters for {symbol}: {e}{RESET}",
            )
        except ccxt.NetworkError as e:
            self.logger.error(
                f"{NEON_RED}Network error placing order for {symbol}: {e}{RESET}",
            )
        except ccxt.ExchangeError as e:
            self.logger.error(
                f"{NEON_RED}CCXT Exchange Error placing order for {symbol}: {e}{RESET}",
            )
        except Exception as e:
            self.logger.error(f"{NEON_RED}Error placing order for {symbol}: {e}{RESET}")
        return None

    async def cancel_order(self, symbol: str, order_id: str) -> dict | None:
        """Cancel an existing order on Bybit using CCXT."""
        ccxt_symbol = self.get_ccxt_symbol(symbol)
        try:
            response = await self.exchange.cancel_order(order_id, ccxt_symbol)
            self.logger.info(
                f"{NEON_GREEN}Order {order_id} cancelled for {symbol}: {response}{RESET}",
            )
            return response
        except ccxt.OrderNotFound as e:
            self.logger.warning(
                f"{NEON_YELLOW}Order {order_id} not found for {symbol}: {e}{RESET}",
            )
        except ccxt.NetworkError as e:
            self.logger.error(
                f"{NEON_RED}Network error canceling order {order_id} for {symbol}: {e}{RESET}",
            )
        except ccxt.ExchangeError as e:
            self.logger.error(
                f"{NEON_RED}CCXT Exchange Error canceling order {order_id} for {symbol}: {e}{RESET}",
            )
        except Exception as e:
            self.logger.error(
                f"{NEON_RED}Error canceling order {order_id} for {symbol}: {e}{RESET}",
            )
        return None

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage for the trading pair using CCXT."""
        ccxt_symbol = self.get_ccxt_symbol(symbol)
        try:
            # Bybit v5 set_leverage requires buyLeverage and sellLeverage separately
            response = await self.exchange.set_leverage(
                leverage=leverage,
                symbol=ccxt_symbol,
                params={"buyLeverage": leverage, "sellLeverage": leverage},
            )
            self.logger.info(
                f"{NEON_GREEN}[{symbol}] Leverage set to {leverage}x.{RESET}",
            )
            return True
        except ccxt.ExchangeError as e:
            self.logger.error(
                f"{NEON_RED}[{symbol}] Failed to set leverage to {leverage}x. Error: {e}{RESET}",
            )
            return False
        except Exception as e:
            self.logger.error(
                f"{NEON_RED}Error setting leverage for {symbol}: {e}{RESET}",
            )
            return False


# --- Precision Management ---
class PrecisionManager:
    """Manages symbol-specific precision for order quantity and price using CCXT."""

    def __init__(
        self,
        symbol: str,
        logger: logging.Logger,
        config: dict[str, Any],
        exchange_client: ExchangeClient,
    ):
        """Initializes the PrecisionManager."""
        self.symbol = symbol
        self.logger = logger
        self.config = config
        self.exchange_client = exchange_client
        self.ccxt_symbol = self.exchange_client.get_ccxt_symbol(symbol)
        self.market_info: dict | None = None

        # Fallback values from config if market info cannot be fetched
        self.qty_step: Decimal = Decimal("1") / (
            Decimal("10") ** config["trade_management"]["order_precision"]
        )
        self.price_tick_size: Decimal = Decimal("1") / (
            Decimal("10") ** config["trade_management"]["price_precision"]
        )
        self.min_order_qty: Decimal = Decimal("0.0001")  # Reasonable default

        asyncio.create_task(self._fetch_precision_info())  # Fetch asynchronously

    async def _fetch_precision_info(self) -> None:
        """Fetch and store precision info from the exchange using CCXT."""
        self.logger.info(f"[{self.symbol}] Fetching precision information...")
        try:
            # Ensure markets are loaded
            if not self.exchange_client.markets_loaded:
                await self.exchange_client.load_markets()  # Load if not already
                if not self.exchange_client.markets_loaded:
                    self.logger.error(
                        f"{NEON_RED}[{self.symbol}] Markets not loaded, cannot fetch precision info.{RESET}",
                    )
                    return

            # CCXT stores market info after load_markets()
            self.market_info = self.exchange_client.exchange.market(self.ccxt_symbol)

            if self.market_info:
                # Use CCXT's standardized precision fields
                self.qty_step = (
                    Decimal(str(self.market_info["limits"]["amount"]["min"]))
                    if self.market_info["limits"]["amount"]["min"]
                    else self.qty_step
                )
                self.min_order_qty = (
                    Decimal(str(self.market_info["limits"]["amount"]["min"]))
                    if self.market_info["limits"]["amount"]["min"]
                    else self.min_order_qty
                )

                # For Bybit, tickSize and lotSizeFilter are usually in 'info' dict
                if (
                    "info" in self.market_info
                    and "priceFilter" in self.market_info["info"]
                ):
                    self.price_tick_size = Decimal(
                        str(
                            self.market_info["info"]["priceFilter"].get(
                                "tickSize",
                                self.price_tick_size,
                            ),
                        ),
                    )
                if (
                    "info" in self.market_info
                    and "lotSizeFilter" in self.market_info["info"]
                ):
                    # qtyStep is sometimes more granular than minOrderQty
                    # Take max of default config and market's 'qtyStep'
                    self.qty_step = max(
                        self.qty_step,
                        Decimal(
                            str(
                                self.market_info["info"]["lotSizeFilter"].get(
                                    "qtyStep",
                                    self.qty_step,
                                ),
                            ),
                        ),
                    )

                self.logger.info(
                    f"[{self.symbol}] Precision loaded: Qty Step={self.qty_step.normalize()}, "
                    f"Price Tick Size={self.price_tick_size.normalize()}, "
                    f"Min Qty={self.min_order_qty.normalize()}",
                )
            else:
                self.logger.error(
                    f"{NEON_RED}[{self.symbol}] Failed to fetch precision info from CCXT. Using config defaults. "
                    f"This may cause order placement errors.{RESET}",
                )
        except Exception as e:
            self.logger.error(
                f"{NEON_RED}[{self.symbol}] Error fetching precision info via CCXT: {e}. Using config defaults.{RESET}",
            )

    def format_quantity(self, quantity: Decimal) -> Decimal:
        """Formats the order quantity according to the symbol's qtyStep."""
        if self.market_info:
            return Decimal(
                str(
                    self.exchange_client.exchange.amount_to_precision(
                        self.ccxt_symbol,
                        float(quantity),
                    ),
                ),
            )
        return (quantity // self.qty_step) * self.qty_step

    def format_price(self, price: Decimal) -> Decimal:
        """Formats the order price according to the symbol's tickSize."""
        if self.market_info:
            return Decimal(
                str(
                    self.exchange_client.exchange.price_to_precision(
                        self.ccxt_symbol,
                        float(price),
                    ),
                ),
            )
        return (price // self.price_tick_size) * self.price_tick_size


# --- Position Management ---
class PositionManager:
    """Manages open positions, stop-loss, and take-profit levels."""

    def __init__(
        self,
        config: dict[str, Any],
        logger: logging.Logger,
        symbol: str,
        exchange_client: ExchangeClient,
    ):
        """Initializes the PositionManager."""
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.exchange_client = exchange_client
        self.ccxt_symbol = self.exchange_client.get_ccxt_symbol(symbol)

        self.open_positions: dict[
            str,
            dict,
        ] = {}  # Tracks positions opened by the bot locally
        self.trade_management_enabled = config["trade_management"]["enabled"]
        self.precision_manager = PrecisionManager(
            symbol,
            logger,
            config,
            exchange_client,
        )
        self.max_open_positions = config["trade_management"]["max_open_positions"]
        self.leverage = config["trade_management"]["leverage"]
        self.order_mode = config["trade_management"]["order_mode"]

        # Bybit v5 supports TP/SL directly on order creation, usually as 'full' by default
        self.trailing_stop_activation_percent = (
            Decimal(str(config["trade_management"]["trailing_stop_activation_percent"]))
            / 100
        )

        # Set leverage (only once or when changed)
        if self.trade_management_enabled:
            asyncio.create_task(self._set_leverage_on_startup())

    async def _set_leverage_on_startup(self) -> None:
        """Set leverage for the trading pair on startup."""
        await self.exchange_client.set_leverage(self.symbol, self.leverage)

    async def _get_available_balance(self) -> Decimal:
        """Fetch current available account balance for order sizing using CCXT."""
        if not self.trade_management_enabled:
            return Decimal(str(self.config["trade_management"]["account_balance"]))

        # Assuming USDT for linear contracts
        balance = await self.exchange_client.get_wallet_balance("USDT")
        if balance is None:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Failed to fetch actual balance. Using simulated balance for calculation.{RESET}",
            )
            return Decimal(str(self.config["trade_management"]["account_balance"]))
        return balance

    def _calculate_order_size(
        self,
        current_price: Decimal,
        atr_value: Decimal,
    ) -> Decimal:
        """Calculate order size based on risk per trade, ATR, and available balance."""
        if not self.trade_management_enabled:
            return Decimal("0")

        account_balance = (
            self._get_available_balance()
        )  # This would be an async call, needs await

        # For a synchronous function like this, we'd need to assume balance is available or pass it in.
        # Let's make this method async and await the balance.
        # However, for consistency with `open_position` being async, we'll keep it as a private helper
        # but acknowledge that `_get_available_balance` itself would typically be awaited.
        # For now, we'll call it within `open_position` directly.

        risk_per_trade_percent = (
            Decimal(str(self.config["trade_management"]["risk_per_trade_percent"]))
            / 100
        )
        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"]),
        )

        risk_amount = account_balance * risk_per_trade_percent
        stop_loss_distance_usd = atr_value * stop_loss_atr_multiple

        if stop_loss_distance_usd <= 0:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Calculated stop loss distance is zero or negative ({stop_loss_distance_usd.normalize()}). Cannot determine order size.{RESET}",
            )
            return Decimal("0")

        # Order size in USD value (notional value)
        order_value_notional = risk_amount / stop_loss_distance_usd
        # Convert to quantity of the asset (e.g., BTC)
        order_qty_unleveraged = order_value_notional / current_price

        # Apply leverage for the actual order quantity (buying power)
        order_qty = order_qty_unleveraged * self.leverage

        # Round order_qty to appropriate precision for the symbol
        order_qty = self.precision_manager.format_quantity(order_qty)

        # Check against min order quantity
        if (
            self.precision_manager.min_order_qty is not None
            and order_qty < self.precision_manager.min_order_qty
        ):
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Calculated order quantity ({order_qty.normalize()}) is below the minimum "
                f"({self.precision_manager.min_order_qty.normalize()}). Cannot open position. "
                f"Consider reducing risk per trade or using a larger account balance.{RESET}",
            )
            return Decimal("0")

        if order_qty <= Decimal("0"):
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Calculated order quantity ({order_qty.normalize()}) is too small or zero. Cannot open position.{RESET}",
            )
            return Decimal("0")

        self.logger.info(
            f"[{self.symbol}] Calculated order size: {order_qty.normalize()} (Risk: {risk_amount.normalize():.2f} USDT, SL Distance: {stop_loss_distance_usd.normalize():.4f}, Leveraged Qty: {order_qty.normalize()})",
        )
        return order_qty

    async def open_position(
        self,
        signal: Literal["BUY", "SELL"],
        current_price: Decimal,
        atr_value: Decimal,
    ) -> dict | None:
        """Open a new position if conditions allow by placing an order on the exchange."""
        if not self.trade_management_enabled:
            self.logger.info(
                f"{NEON_YELLOW}[{self.symbol}] Trade management is disabled. Skipping opening position.{RESET}",
            )
            return None

        # Fetch actual open positions from the exchange to check limits
        exchange_open_positions = (
            await self.exchange_client.get_exchange_open_positions(self.symbol)
        )

        if (
            exchange_open_positions
            and len(exchange_open_positions) >= self.max_open_positions
        ):
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Max open positions ({self.max_open_positions}) reached on exchange. Cannot open new position.{RESET}",
            )
            return None

        # Check for existing positions locally and their status
        if (
            self.symbol in self.open_positions
            and self.open_positions[self.symbol]["status"] == "OPEN"
        ):
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Locally tracked position for {self.symbol} is already open. Skipping.{RESET}",
            )
            # This could indicate a mismatch if the exchange_open_positions check passed
            # In a robust system, we might reconcile local state with exchange state here.
            return None

        if signal not in ["BUY", "SELL"]:
            self.logger.debug(f"Invalid signal '{signal}' for opening position.")
            return None

        # Calculate order size using the async balance fetch
        available_balance = await self._get_available_balance()
        order_qty = self._calculate_order_size(
            current_price,
            atr_value,
        )  # This needs available_balance passed or refactored

        # Refactor _calculate_order_size to take balance explicitly to avoid recursive async calls/complexity
        # For now, let's simplify and make _calculate_order_size assume a direct balance input
        order_qty = self._calculate_order_size_with_balance(
            current_price,
            atr_value,
            available_balance,
        )

        if order_qty <= Decimal("0"):
            return None

        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"]),
        )
        take_profit_atr_multiple = Decimal(
            str(self.config["trade_management"]["take_profit_atr_multiple"]),
        )

        side = "Buy" if signal == "BUY" else "Sell"

        # Entry price for limit orders or estimation for market orders
        entry_price = current_price

        if signal == "BUY":
            stop_loss_price = current_price - (atr_value * stop_loss_atr_multiple)
            take_profit_price = current_price + (atr_value * take_profit_atr_multiple)
        else:  # SELL
            stop_loss_price = current_price + (atr_value * stop_loss_atr_multiple)
            take_profit_price = current_price - (atr_value * take_profit_atr_multiple)

        entry_price = self.precision_manager.format_price(entry_price)
        stop_loss_price = self.precision_manager.format_price(stop_loss_price)
        take_profit_price = self.precision_manager.format_price(take_profit_price)

        self.logger.info(
            f"[{self.symbol}] Attempting to place {side} order: Qty={order_qty.normalize()}, SL={stop_loss_price.normalize()}, TP={take_profit_price.normalize()}",
        )

        placed_order = await self.exchange_client.place_order(
            symbol=self.symbol,
            side=side,
            order_type=self.order_mode,
            qty=order_qty,
            price=entry_price if self.order_mode == "LIMIT" else None,
            take_profit=take_profit_price,
            stop_loss=stop_loss_price,
            # tp_sl_mode is generally handled by CCXT parameters now
            position_idx=None,  # CCXT abstracts this for 'linear' defaultType
        )

        if placed_order:
            self.logger.info(
                f"{NEON_GREEN}[{self.symbol}] Successfully initiated {signal} trade with order ID: {placed_order.get('id')}{RESET}",
            )
            # For logging/tracking purposes, return a simplified representation
            position_info = {
                "entry_time": datetime.now(TIMEZONE),
                "symbol": self.symbol,
                "side": signal,
                "entry_price": entry_price,  # This is target entry, actual fill price might differ for market orders
                "qty": order_qty,
                "stop_loss": stop_loss_price,
                "take_profit": take_profit_price,
                "status": "OPEN",
                "order_id": placed_order.get("id"),
                "is_trailing_activated": False,
                "current_trailing_sl": stop_loss_price,  # Initialize trailing SL to initial SL
            }
            self.open_positions[self.symbol] = (
                position_info  # Track the position locally
            )
            return position_info
        self.logger.error(
            f"{NEON_RED}[{self.symbol}] Failed to place {signal} order. Check API logs for details.{RESET}",
        )
        return None

    # Helper to calculate order size if balance is passed explicitly
    def _calculate_order_size_with_balance(
        self,
        current_price: Decimal,
        atr_value: Decimal,
        account_balance: Decimal,
    ) -> Decimal:
        if not self.trade_management_enabled:
            return Decimal("0")

        risk_per_trade_percent = (
            Decimal(str(self.config["trade_management"]["risk_per_trade_percent"]))
            / 100
        )
        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"]),
        )

        risk_amount = account_balance * risk_per_trade_percent
        stop_loss_distance_usd = atr_value * stop_loss_atr_multiple

        if stop_loss_distance_usd <= 0:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Calculated stop loss distance is zero or negative ({stop_loss_distance_usd.normalize()}). Cannot determine order size.{RESET}",
            )
            return Decimal("0")

        order_value_notional = risk_amount / stop_loss_distance_usd
        order_qty_unleveraged = order_value_notional / current_price
        order_qty = order_qty_unleveraged * self.leverage
        order_qty = self.precision_manager.format_quantity(order_qty)

        if (
            self.precision_manager.min_order_qty is not None
            and order_qty < self.precision_manager.min_order_qty
        ):
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Calculated order quantity ({order_qty.normalize()}) is below the minimum "
                f"({self.precision_manager.min_order_qty.normalize()}). Cannot open position. "
                f"Consider reducing risk per trade or using a larger account balance.{RESET}",
            )
            return Decimal("0")
        if order_qty <= Decimal("0"):
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Calculated order quantity ({order_qty.normalize()}) is too small or zero. Cannot open position.{RESET}",
            )
            return Decimal("0")

        self.logger.info(
            f"[{self.symbol}] Calculated order size: {order_qty.normalize()} (Risk: {risk_amount.normalize():.2f} USDT, SL Distance: {stop_loss_distance_usd.normalize():.4f}, Leveraged Qty: {order_qty.normalize()})",
        )
        return order_qty

    async def manage_positions(
        self,
        current_price: Decimal,
        atr_value: Decimal,
        performance_tracker: Any,
    ) -> None:
        """Fetch and manage open positions on the exchange. Update local state and record trades."""
        if not self.trade_management_enabled:
            return

        exchange_positions = await self.exchange_client.get_exchange_open_positions(
            self.symbol,
        )

        # Convert exchange positions to a dictionary for easier lookup
        exchange_positions_map = {}
        for pos in exchange_positions:
            # CCXT 'side' can be 'long' or 'short', convert to 'BUY'/'SELL'
            ccxt_side = pos.get("side")
            bot_side = (
                "BUY"
                if ccxt_side == "long"
                else "SELL"
                if ccxt_side == "short"
                else "UNKNOWN"
            )

            # Position key might need to be unique, e.g., by symbol and side for hedge mode
            pos_key = f"{self.symbol}_{bot_side}"
            exchange_positions_map[pos_key] = pos

        # Update local open_positions based on exchange data and manage trailing stops
        positions_to_remove = []
        for pos_key, local_position in list(self.open_positions.items()):
            bot_side = local_position["side"]

            # Check if this local position still exists on the exchange
            if pos_key in exchange_positions_map:
                exchange_pos_data = exchange_positions_map[pos_key]
                # Ensure it's truly an open position (size > 0)
                if (
                    Decimal(str(exchange_pos_data.get("contracts", 0))) > 0
                ):  # 'contracts' is CCXT's standardized size field
                    # Position is still open on exchange. Update local info and manage trailing stop.

                    # Update local entry price with actual entry price from exchange if available
                    if (
                        "entryPrice" in exchange_pos_data
                        and exchange_pos_data["entryPrice"] is not None
                    ):
                        local_position["entry_price"] = Decimal(
                            str(exchange_pos_data["entryPrice"]),
                        )

                    # --- Trailing Stop Logic ---
                    trailing_stop_atr_multiple = Decimal(
                        str(
                            self.config["trade_management"][
                                "trailing_stop_atr_multiple"
                            ],
                        ),
                    )

                    is_trailing_activated = local_position.get(
                        "is_trailing_activated",
                        False,
                    )
                    entry_price = local_position["entry_price"]

                    if not is_trailing_activated:
                        # Check if activation threshold is met
                        profit_percent = Decimal("0")
                        if bot_side == "BUY":
                            profit_percent = (current_price - entry_price) / entry_price
                        elif bot_side == "SELL":
                            profit_percent = (entry_price - current_price) / entry_price

                        if profit_percent >= self.trailing_stop_activation_percent:
                            local_position["is_trailing_activated"] = True

                            # Calculate initial trailing stop price
                            if bot_side == "BUY":
                                initial_trailing_sl = current_price - (
                                    atr_value * trailing_stop_atr_multiple
                                )
                            else:  # SELL
                                initial_trailing_sl = current_price + (
                                    atr_value * trailing_stop_atr_multiple
                                )

                            local_position["current_trailing_sl"] = (
                                self.precision_manager.format_price(initial_trailing_sl)
                            )
                            self.logger.info(
                                f"[{self.symbol}] Trailing stop activated. Initial SL: {local_position['current_trailing_sl'].normalize()}",
                            )
                            # In a real bot, you'd call CCXT to update the stop loss here.
                            # Example:
                            # await self.exchange_client.exchange.edit_order(
                            #    order_id=None, # Needs to be the existing SL order ID if separate
                            #    symbol=self.ccxt_symbol,
                            #    type='stop_loss',
                            #    side='sell' if bot_side == 'BUY' else 'buy',
                            #    amount=float(local_position['qty']),
                            #    price=None, # or current_price for market SL
                            #    params={'stopLoss': float(local_position['current_trailing_sl'])}
                            # )

                    elif is_trailing_activated:
                        # Trailing stop is active, check if it needs updating
                        potential_new_sl = Decimal("0")
                        current_trailing_sl = local_position["current_trailing_sl"]

                        if bot_side == "BUY":
                            potential_new_sl = current_price - (
                                atr_value * trailing_stop_atr_multiple
                            )
                            # Only move trailing SL up (for buy)
                            if potential_new_sl > current_trailing_sl:
                                local_position["current_trailing_sl"] = (
                                    self.precision_manager.format_price(
                                        potential_new_sl,
                                    )
                                )
                                self.logger.info(
                                    f"[{self.symbol}] Updating trailing stop to {local_position['current_trailing_sl'].normalize()}",
                                )
                                # Call CCXT to update the trailing stop on the exchange
                        elif bot_side == "SELL":
                            potential_new_sl = current_price + (
                                atr_value * trailing_stop_atr_multiple
                            )
                            # Only move trailing SL down (for sell)
                            if potential_new_sl < current_trailing_sl:
                                local_position["current_trailing_sl"] = (
                                    self.precision_manager.format_price(
                                        potential_new_sl,
                                    )
                                )
                                self.logger.info(
                                    f"[{self.symbol}] Updating trailing stop to {local_position['current_trailing_sl'].normalize()}",
                                )
                                # Call CCXT to update the trailing stop on the exchange
                else:
                    # Position not found or closed on exchange (size 0), record and remove
                    self.logger.info(
                        f"{NEON_PURPLE}Position for {self.symbol} ({bot_side}) is closed on exchange. Recording trade.{RESET}",
                    )
                    local_position["status"] = "CLOSED"
                    local_position["exit_time"] = datetime.now(TIMEZONE)
                    # Attempt to get exit price from exchange data or assume current price for simulation
                    local_position["exit_price"] = self.precision_manager.format_price(
                        Decimal(
                            str(exchange_pos_data.get("markPrice", current_price)),
                        ),  # Use markPrice or current
                    )
                    local_position["closed_by"] = (
                        "EXCHANGE_CLOSURE"  # Or based on actual order status
                    )

                    pnl = (
                        (local_position["exit_price"] - local_position["entry_price"])
                        * local_position["qty"]
                        if bot_side == "BUY"
                        else (
                            local_position["entry_price"] - local_position["exit_price"]
                        )
                        * local_position["qty"]
                    )
                    performance_tracker.record_trade(local_position, pnl)
                    positions_to_remove.append(pos_key)
            else:
                # Local position not found on exchange, assume it was closed externally
                self.logger.warning(
                    f"{NEON_YELLOW}Local position for {self.symbol} ({bot_side}) not found on exchange. Assuming external closure and recording.{RESET}",
                )
                local_position["status"] = "CLOSED"
                local_position["exit_time"] = datetime.now(TIMEZONE)
                local_position["exit_price"] = self.precision_manager.format_price(
                    current_price,
                )
                local_position["closed_by"] = "EXTERNAL_CLOSURE"

                pnl = (
                    (local_position["exit_price"] - local_position["entry_price"])
                    * local_position["qty"]
                    if bot_side == "BUY"
                    else (local_position["entry_price"] - local_position["exit_price"])
                    * local_position["qty"]
                )
                performance_tracker.record_trade(local_position, pnl)
                positions_to_remove.append(pos_key)

        # Remove closed positions from local tracking
        for pos_key in positions_to_remove:
            if pos_key in self.open_positions:
                del self.open_positions[pos_key]

    def get_open_positions(self) -> list[dict]:
        """Return a list of currently open positions tracked locally."""
        return [pos for pos in self.open_positions.values() if pos["status"] == "OPEN"]


# --- Performance Tracking ---
class PerformanceTracker:
    """Tracks and reports trading performance. Trades are saved to a file."""

    def __init__(self, logger: logging.Logger, config_file: str = "trades.json"):
        """Initializes the PerformanceTracker."""
        self.logger = logger
        self.config_file = Path(config_file)
        self.trades: list[dict] = self._load_trades()
        self.total_pnl = Decimal("0")
        self.wins = 0
        self.losses = 0
        self._recalculate_summary()  # Recalculate summary from loaded trades

    def _load_trades(self) -> list[dict]:
        """Load trade history from file."""
        if self.config_file.exists():
            try:
                with self.config_file.open("r", encoding="utf-8") as f:
                    raw_trades = json.load(f)
                    # Convert Decimal/datetime from string after loading
                    loaded_trades = []
                    for trade in raw_trades:
                        for key in [
                            "pnl",
                            "entry_price",
                            "exit_price",
                            "qty",
                            "stop_loss",
                            "take_profit",
                            "current_trailing_sl",
                        ]:
                            if key in trade and trade[key] is not None:
                                try:
                                    trade[key] = Decimal(str(trade[key]))
                                except Exception:
                                    trade[key] = None  # Or Decimal("0") if preferred
                        for key in ["entry_time", "exit_time"]:
                            if key in trade and trade[key] is not None:
                                try:
                                    trade[key] = datetime.fromisoformat(trade[key])
                                except Exception:
                                    trade[key] = None  # Or datetime.now(TIMEZONE)
                        loaded_trades.append(trade)
                    return loaded_trades
            except (json.JSONDecodeError, OSError) as e:
                self.logger.error(
                    f"{NEON_RED}Error loading trades from {self.config_file}: {e}{RESET}",
                )
        return []

    def _save_trades(self) -> None:
        """Save trade history to file."""
        try:
            with self.config_file.open("w", encoding="utf-8") as f:
                # Convert Decimal/datetime to string for JSON serialization
                serializable_trades = []
                for trade in self.trades:
                    s_trade = trade.copy()
                    for key in [
                        "pnl",
                        "entry_price",
                        "exit_price",
                        "qty",
                        "stop_loss",
                        "take_profit",
                        "current_trailing_sl",
                    ]:
                        if key in s_trade and s_trade[key] is not None:
                            s_trade[key] = str(s_trade[key])
                    for key in ["entry_time", "exit_time"]:
                        if key in s_trade and s_trade[key] is not None:
                            s_trade[key] = s_trade[key].isoformat()
                    serializable_trades.append(s_trade)
                json.dump(serializable_trades, f, indent=4)
        except OSError as e:
            self.logger.error(
                f"{NEON_RED}Error saving trades to {self.config_file}: {e}{RESET}",
            )

    def _recalculate_summary(self) -> None:
        """Recalculate summary metrics from the list of trades."""
        self.total_pnl = Decimal("0")
        self.wins = 0
        self.losses = 0
        for trade in self.trades:
            pnl = Decimal(str(trade.get("pnl", "0")))  # Ensure pnl is Decimal
            self.total_pnl += pnl
            if pnl > 0:
                self.wins += 1
            else:
                self.losses += 1

    def record_trade(self, position: dict, pnl: Decimal) -> None:
        """Record a completed trade."""
        trade_record = {
            "entry_time": position.get(
                "entry_time",
                datetime.now(TIMEZONE),
            ).isoformat(),
            "exit_time": position.get("exit_time", datetime.now(TIMEZONE)).isoformat(),
            "symbol": position["symbol"],
            "side": position["side"],
            "entry_price": str(position["entry_price"]),
            "exit_price": str(position["exit_price"]),
            "qty": str(position["qty"]),
            "pnl": str(pnl),
            "closed_by": position.get("closed_by", "UNKNOWN"),
            "stop_loss": str(position["stop_loss"]),
            "take_profit": str(position["take_profit"]),
            "current_trailing_sl": str(position.get("current_trailing_sl", "N/A")),
        }
        self.trades.append(trade_record)
        self._recalculate_summary()  # Update summary immediately
        self._save_trades()  # Save to file
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


# --- Alert System ---
class AlertSystem:
    """Handles sending alerts for critical events."""

    def __init__(self, logger: logging.Logger):
        """Initializes the AlertSystem."""
        self.logger = logger

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


# --- Trading Analysis ---
class TradingAnalyzer:
    """Analyzes trading data and generates signals with MTF, Ehlers SuperTrend, and other new indicators."""

    def __init__(
        self,
        df: pd.DataFrame,
        config: dict[str, Any],
        logger: logging.Logger,
        symbol: str,
        exchange_client: ExchangeClient,
    ):
        """Initializes the TradingAnalyzer."""
        self.df = df.copy()
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.exchange_client = exchange_client
        self.indicator_values: dict[str, float | str | Decimal] = {}
        self.fib_levels: dict[str, Decimal] = {}
        self.weights = config["weight_sets"]["default_scalping"]
        self.indicator_settings = config["indicator_settings"]
        self.price_precision = config["trade_management"][
            "price_precision"
        ]  # For Fibonacci levels

        self.gemini_client: Any | None = None  # Placeholder for GeminiClient
        if self.config["gemini_ai_analysis"]["enabled"]:
            gemini_api_key = os.getenv("GEMINI_API_KEY")
            if not gemini_api_key:
                self.logger.error(
                    f"{NEON_RED}GEMINI_API_KEY environment variable is not set, but gemini_ai_analysis is enabled. Disabling Gemini AI analysis.{RESET}",
                )
                self.config["gemini_ai_analysis"]["enabled"] = False
            else:
                # Placeholder for GeminiClient if not available
                # In a real scenario, you'd instantiate your GeminiClient here
                self.logger.warning(
                    f"{NEON_YELLOW}Gemini AI analysis enabled, but GeminiClient is a placeholder (not implemented).{RESET}",
                )
                self.gemini_client = lambda: None  # Simple callable placeholder

        if not self.df.empty:
            self._calculate_all_indicators()
            if self.config["indicators"].get("fibonacci_levels", False):
                self.calculate_fibonacci_levels()

    def _safe_series_op(self, series: pd.Series, name: str) -> pd.Series:
        """Safely perform operations on a Series, handling potential NaNs and logging."""
        if series is None or series.empty:
            self.logger.debug(
                f"Series '{name}' is empty or None. Returning empty Series.",
            )
            # Return an empty Series with float dtype
            return pd.Series(dtype=float, index=self.df.index)
        if series.isnull().all():
            self.logger.debug(
                f"Series '{name}' contains all NaNs. Returning Series with NaNs.",
            )
            return pd.Series(
                np.nan,
                index=self.df.index,
            )  # Ensure index matches main DF
        return series

    def _safe_calculate(
        self,
        func: callable,
        name: str,
        min_data_points: int = 0,
        *args,
        **kwargs,
    ) -> Any | None:
        """Safely calculate indicators and log errors, with min_data_points check."""
        if self.df.empty:
            self.logger.debug(f"Skipping indicator '{name}': DataFrame is empty.")
            return None
        if len(self.df) < min_data_points:
            self.logger.debug(
                f"Skipping indicator '{name}': Not enough data. Need {min_data_points}, have {len(self.df)}.",
            )
            return None
        try:
            result = func(*args, **kwargs)

            # Check for empty series or all NaNs
            if isinstance(result, pd.Series) and (
                result.empty or result.isnull().all()
            ):
                self.logger.warning(
                    f"{NEON_YELLOW}Indicator '{name}' returned an empty or all-NaN Series. Not enough valid data?{RESET}",
                )
                return None
            if isinstance(result, tuple):
                processed_results = []
                all_empty_or_nan = True
                for r in result:
                    if isinstance(r, pd.Series) and (r.empty or r.isnull().all()):
                        processed_results.append(pd.Series(np.nan, index=self.df.index))
                    else:
                        processed_results.append(r)
                        all_empty_or_nan = False
                if all_empty_or_nan:
                    self.logger.warning(
                        f"{NEON_YELLOW}Indicator '{name}' returned all-empty or all-NaN Series in tuple. Not enough valid data?{RESET}",
                    )
                    return (pd.Series(np.nan, index=self.df.index),) * len(result)
                return tuple(processed_results)
            return result
        except Exception as e:
            self.logger.error(
                f"{NEON_RED}Error calculating indicator '{name}': {e}{RESET}",
                exc_info=True,
            )
            return None

    def _calculate_all_indicators(self) -> None:
        """Calculate all enabled technical indicators."""
        self.logger.debug(f"[{self.symbol}] Calculating technical indicators...")
        cfg = self.config
        isd = self.indicator_settings

        # Ensure True Range is calculated first as it's a dependency for many indicators
        self.df["TR"] = self._safe_calculate(
            self.calculate_true_range,
            "TR",
            min_data_points=MIN_DATA_POINTS_TRUE_RANGE,
        )
        # ATR (requires TR)
        self.df["ATR"] = self._safe_calculate(
            lambda: ta.atr(
                self.df["high"],
                self.df["low"],
                self.df["close"],
                length=isd["atr_period"],
            ),
            "ATR",
            min_data_points=isd["atr_period"],
        )
        if self.df["ATR"] is not None and not self.df["ATR"].empty:
            self.indicator_values["ATR"] = Decimal(str(self.df["ATR"].iloc[-1]))
        else:
            self.indicator_values["ATR"] = Decimal("0.01")  # Default to a small value

        # SMA
        if cfg["indicators"].get("sma_10", False):
            self.df["SMA_10"] = self._safe_calculate(
                lambda: ta.sma(self.df["close"], length=isd["sma_short_period"]),
                "SMA_10",
                min_data_points=isd["sma_short_period"],
            )
            if self.df["SMA_10"] is not None and not self.df["SMA_10"].empty:
                self.indicator_values["SMA_10"] = Decimal(
                    str(self.df["SMA_10"].iloc[-1]),
                )
        if cfg["indicators"].get("sma_trend_filter", False):
            self.df["SMA_Long"] = self._safe_calculate(
                lambda: ta.sma(self.df["close"], length=isd["sma_long_period"]),
                "SMA_Long",
                min_data_points=isd["sma_long_period"],
            )
            if self.df["SMA_Long"] is not None and not self.df["SMA_Long"].empty:
                self.indicator_values["SMA_Long"] = Decimal(
                    str(self.df["SMA_Long"].iloc[-1]),
                )

        # EMA
        if cfg["indicators"].get("ema_alignment", False):
            self.df["EMA_Short"] = self._safe_calculate(
                lambda: ta.ema(self.df["close"], length=isd["ema_short_period"]),
                "EMA_Short",
                min_data_points=isd["ema_short_period"],
            )
            self.df["EMA_Long"] = self._safe_calculate(
                lambda: ta.ema(self.df["close"], length=isd["ema_long_period"]),
                "EMA_Long",
                min_data_points=isd["ema_long_period"],
            )
            if self.df["EMA_Short"] is not None and not self.df["EMA_Short"].empty:
                self.indicator_values["EMA_Short"] = Decimal(
                    str(self.df["EMA_Short"].iloc[-1]),
                )
            if self.df["EMA_Long"] is not None and not self.df["EMA_Long"].empty:
                self.indicator_values["EMA_Long"] = Decimal(
                    str(self.df["EMA_Long"].iloc[-1]),
                )

        # RSI
        if cfg["indicators"].get("rsi", False):
            self.df["RSI"] = self._safe_calculate(
                lambda: ta.rsi(self.df["close"], length=isd["rsi_period"]),
                "RSI",
                min_data_points=isd["rsi_period"] + 1,
            )
            if self.df["RSI"] is not None and not self.df["RSI"].empty:
                self.indicator_values["RSI"] = float(self.df["RSI"].iloc[-1])

        # Stochastic RSI
        if cfg["indicators"].get("stoch_rsi", False):
            stoch_rsi_k, stoch_rsi_d = self._safe_calculate(
                self.calculate_stoch_rsi,
                "StochRSI",
                min_data_points=isd["stoch_rsi_period"]
                + isd["stoch_k_period"]
                + isd["stoch_d_period"],
                period=isd["stoch_rsi_period"],
                k_period=isd["stoch_k_period"],
                d_period=isd["stoch_d_period"],
            )
            if stoch_rsi_k is not None:
                self.df["StochRSI_K"] = stoch_rsi_k
            if stoch_rsi_d is not None:
                self.df["StochRSI_D"] = stoch_rsi_d
            if stoch_rsi_k is not None and not stoch_rsi_k.empty:
                self.indicator_values["StochRSI_K"] = float(stoch_rsi_k.iloc[-1])
            if stoch_rsi_d is not None and not stoch_rsi_d.empty:
                self.indicator_values["StochRSI_D"] = float(stoch_rsi_d.iloc[-1])

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
            if bb_upper is not None and not bb_upper.empty:
                self.indicator_values["BB_Upper"] = Decimal(str(bb_upper.iloc[-1]))
            if bb_middle is not None and not bb_middle.empty:
                self.indicator_values["BB_Middle"] = Decimal(str(bb_middle.iloc[-1]))
            if bb_lower is not None and not bb_lower.empty:
                self.indicator_values["BB_Lower"] = Decimal(str(bb_lower.iloc[-1]))

        # CCI
        if cfg["indicators"].get("cci", False):
            self.df["CCI"] = self._safe_calculate(
                lambda: ta.cci(
                    self.df["high"],
                    self.df["low"],
                    self.df["close"],
                    length=isd["cci_period"],
                ),
                "CCI",
                min_data_points=isd["cci_period"],
            )
            if self.df["CCI"] is not None and not self.df["CCI"].empty:
                self.indicator_values["CCI"] = float(self.df["CCI"].iloc[-1])

        # Williams %R
        if cfg["indicators"].get("wr", False):
            self.df["WR"] = self._safe_calculate(
                lambda: ta.willr(
                    self.df["high"],
                    self.df["low"],
                    self.df["close"],
                    length=isd["williams_r_period"],
                ),
                "WR",
                min_data_points=isd["williams_r_period"],
            )
            if self.df["WR"] is not None and not self.df["WR"].empty:
                self.indicator_values["WR"] = float(self.df["WR"].iloc[-1])

        # MFI
        if cfg["indicators"].get("mfi", False):
            self.df["MFI"] = self._safe_calculate(
                lambda: ta.mfi(
                    self.df["high"],
                    self.df["low"],
                    self.df["close"],
                    self.df["volume"].astype(float),  # Explicitly cast volume to float
                    length=isd["mfi_period"],
                ),
                "MFI",
                min_data_points=isd["mfi_period"] + 1,
            )
            if self.df["MFI"] is not None and not self.df["MFI"].empty:
                self.indicator_values["MFI"] = float(self.df["MFI"].iloc[-1])

        # OBV
        if cfg["indicators"].get("obv", False):
            obv_val, obv_ema = self._safe_calculate(
                self.calculate_obv,
                "OBV",
                min_data_points=isd["obv_ema_period"]
                + 1,  # OBV itself has no period, but EMA needs data
                ema_period=isd["obv_ema_period"],
            )
            if obv_val is not None:
                self.df["OBV"] = obv_val
            if obv_ema is not None:
                self.df["OBV_EMA"] = obv_ema
            if obv_val is not None and not obv_val.empty:
                self.indicator_values["OBV"] = float(obv_val.iloc[-1])
            if obv_ema is not None and not obv_ema.empty:
                self.indicator_values["OBV_EMA"] = float(obv_ema.iloc[-1])

        # CMF
        if cfg["indicators"].get("cmf", False):
            cmf_val = self._safe_calculate(
                lambda: ta.cmf(
                    self.df["high"],
                    self.df["low"],
                    self.df["close"],
                    self.df["volume"],
                    length=isd["cmf_period"],
                ),
                "CMF",
                min_data_points=isd["cmf_period"],
            )
            if cmf_val is not None:
                self.df["CMF"] = cmf_val
            if cmf_val is not None and not cmf_val.empty:
                self.indicator_values["CMF"] = float(cmf_val.iloc[-1])

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
                    + isd["ichimoku_chikou_span_offset"]
                    + 1,
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

            if tenkan_sen is not None and not tenkan_sen.empty:
                self.indicator_values["Tenkan_Sen"] = Decimal(str(tenkan_sen.iloc[-1]))
            if kijun_sen is not None and not kijun_sen.empty:
                self.indicator_values["Kijun_Sen"] = Decimal(str(kijun_sen.iloc[-1]))
            if senkou_span_a is not None and not senkou_span_a.empty:
                self.indicator_values["Senkou_Span_A"] = Decimal(
                    str(senkou_span_a.iloc[-1]),
                )
            if senkou_span_b is not None and not senkou_span_b.empty:
                self.indicator_values["Senkou_Span_B"] = Decimal(
                    str(senkou_span_b.iloc[-1]),
                )
            if chikou_span is not None and not chikou_span.empty:
                self.indicator_values["Chikou_Span"] = Decimal(
                    str(chikou_span.fillna(0).iloc[-1]),
                )

        # PSAR
        if cfg["indicators"].get("psar", False):
            psar_val, psar_dir = self._safe_calculate(
                self.calculate_psar,
                "PSAR",
                min_data_points=MIN_DATA_POINTS_PSAR_INITIAL,
                acceleration=isd["psar_acceleration"],
                max_acceleration=isd["psar_max_acceleration"],
            )
            if psar_val is not None:
                self.df["PSAR_Val"] = psar_val
            if psar_dir is not None:
                self.df["PSAR_Dir"] = psar_dir
            if psar_val is not None and not psar_val.empty:
                self.indicator_values["PSAR_Val"] = Decimal(str(psar_val.iloc[-1]))
            if psar_dir is not None and not psar_dir.empty:
                self.indicator_values["PSAR_Dir"] = float(psar_dir.iloc[-1])

        # VWAP (requires volume and turnover, which are in df)
        if cfg["indicators"].get("vwap", False):
            self.df["VWAP"] = self._safe_calculate(
                lambda: self.calculate_vwap(daily_reset=isd["vwap_daily_reset"]),
                "VWAP",
                min_data_points=1,
            )
            if self.df["VWAP"] is not None and not self.df["VWAP"].empty:
                self.indicator_values["VWAP"] = Decimal(str(self.df["VWAP"].iloc[-1]))

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
                self.indicator_values["ST_Fast_Dir"] = float(
                    st_fast_result["direction"].iloc[-1],
                )
                self.indicator_values["ST_Fast_Val"] = Decimal(
                    str(st_fast_result["supertrend"].iloc[-1]),
                )

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
                self.indicator_values["ST_Slow_Dir"] = float(
                    st_slow_result["direction"].iloc[-1],
                )
                self.indicator_values["ST_Slow_Val"] = Decimal(
                    str(st_slow_result["supertrend"].iloc[-1]),
                )

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
            if macd_line is not None and not macd_line.empty:
                self.indicator_values["MACD_Line"] = float(macd_line.iloc[-1])
            if signal_line is not None and not signal_line.empty:
                self.indicator_values["MACD_Signal"] = float(signal_line.iloc[-1])
            if histogram is not None and not histogram.empty:
                self.indicator_values["MACD_Hist"] = float(histogram.iloc[-1])

        # ADX
        if cfg["indicators"].get("adx", False):
            adx_val, plus_di, minus_di = self._safe_calculate(
                self.calculate_adx,
                "ADX",
                min_data_points=isd["adx_period"]
                * 2,  # ATR is dependency and needs period, ADX needs another period for smoothing
                period=isd["adx_period"],
            )
            if adx_val is not None:
                self.df["ADX"] = adx_val
            if plus_di is not None:
                self.df["PlusDI"] = plus_di
            if minus_di is not None:
                self.df["MinusDI"] = minus_di
            if adx_val is not None and not adx_val.empty:
                self.indicator_values["ADX"] = float(adx_val.iloc[-1])
            if plus_di is not None and not plus_di.empty:
                self.indicator_values["PlusDI"] = float(plus_di.iloc[-1])
            if minus_di is not None and not minus_di.empty:
                self.indicator_values["MinusDI"] = float(minus_di.iloc[-1])

        # --- New Indicators ---
        # Volatility Index
        if cfg["indicators"].get("volatility_index", False):
            self.df["Volatility_Index"] = self._safe_calculate(
                lambda: self.calculate_volatility_index(
                    period=isd["volatility_index_period"],
                ),
                "Volatility_Index",
                min_data_points=isd["volatility_index_period"],
            )
            if (
                self.df["Volatility_Index"] is not None
                and not self.df["Volatility_Index"].empty
            ):
                self.indicator_values["Volatility_Index"] = float(
                    self.df["Volatility_Index"].iloc[-1],
                )

        # VWMA
        if cfg["indicators"].get("vwma", False):
            self.df["VWMA"] = self._safe_calculate(
                lambda: self.calculate_vwma(period=isd["vwma_period"]),
                "VWMA",
                min_data_points=isd["vwma_period"],
            )
            if self.df["VWMA"] is not None and not self.df["VWMA"].empty:
                self.indicator_values["VWMA"] = Decimal(str(self.df["VWMA"].iloc[-1]))

        # Volume Delta
        if cfg["indicators"].get("volume_delta", False):
            self.df["Volume_Delta"] = self._safe_calculate(
                lambda: self.calculate_volume_delta(period=isd["volume_delta_period"]),
                "Volume_Delta",
                min_data_points=MIN_DATA_POINTS_VOLUME_DELTA,
            )
            if (
                self.df["Volume_Delta"] is not None
                and not self.df["Volume_Delta"].empty
            ):
                self.indicator_values["Volume_Delta"] = float(
                    self.df["Volume_Delta"].iloc[-1],
                )

        # Fill any remaining NaNs in indicator columns with 0 after all calculations,
        numeric_cols = self.df.select_dtypes(include=np.number).columns
        self.df[numeric_cols] = self.df[numeric_cols].fillna(0)

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] DataFrame is empty after calculating all indicators and cleaning NaNs.{RESET}",
            )
        else:
            self.logger.debug(
                f"[{self.symbol}] Indicators calculated. Final DataFrame size: {len(self.df)}",
            )

    def calculate_true_range(self) -> pd.Series:
        """Calculate True Range (TR)."""
        if len(self.df) < MIN_DATA_POINTS_TRUE_RANGE:
            return pd.Series(np.nan, index=self.df.index)
        high_low = self.df["high"] - self.df["low"]
        high_prev_close = (self.df["high"] - self.df["close"].shift()).abs()
        low_prev_close = (self.df["low"] - self.df["close"].shift()).abs()
        return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(
            axis=1,
        )

    def calculate_super_smoother(self, series: pd.Series, period: int) -> pd.Series:
        """Apply Ehlers SuperSmoother filter to reduce lag and noise."""
        if period <= 0 or len(series) < MIN_DATA_POINTS_SUPERSMOOTHER:
            return pd.Series(np.nan, index=series.index)

        # Drop NaNs for calculation, reindex at the end
        series_clean = series.dropna()
        if len(series_clean) < MIN_DATA_POINTS_SUPERSMOOTHER:
            return pd.Series(np.nan, index=series.index)

        # Avoid division by zero for period in numpy calculations
        period_safe = max(period, 1e-9)  # Use a very small number if period is zero

        a1 = np.exp(-np.sqrt(2) * np.pi / period_safe)
        b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / period_safe)
        c1 = 1 - b1 + a1**2
        c2 = b1 - 2 * a1**2
        c3 = a1**2

        filt = pd.Series(np.nan, index=series_clean.index, dtype=float)
        if len(series_clean) >= 1:
            filt.iloc[0] = series_clean.iloc[0]
        if len(series_clean) >= 2:
            filt.iloc[1] = (series_clean.iloc[0] + series_clean.iloc[1]) / 2

        for i in range(2, len(series_clean)):
            filt.iloc[i] = (
                (c1 / 2) * (series_clean.iloc[i] + series_clean.iloc[i - 1])
                + c2 * filt.iloc[i - 1]
                - c3 * filt.iloc[i - 2]
            )
        # Reindex to original DataFrame index
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

        df_clean = df_copy.dropna(
            subset=["smoothed_price", "smoothed_atr", "close", "high", "low"],
        )
        if df_clean.empty:
            self.logger.warning(
                f"[{self.symbol}] Ehlers SuperTrend (period={period}): DataFrame empty after smoothing and NaN drop. Returning None.",
            )
            return None

        upper_band = df_clean["smoothed_price"] + multiplier * df_clean["smoothed_atr"]
        lower_band = df_clean["smoothed_price"] - multiplier * df_clean["smoothed_atr"]

        direction = pd.Series(np.nan, index=df_clean.index, dtype=float)
        supertrend = pd.Series(np.nan, index=df_clean.index, dtype=float)

        first_valid_loc = df_clean["close"].first_valid_index()
        if first_valid_loc is None:
            return None

        first_valid_idx_loc = df_clean.index.get_loc(first_valid_loc)

        if df_clean["close"].loc[first_valid_loc] > upper_band.loc[first_valid_loc]:
            direction.loc[first_valid_loc] = 1  # 1 for Up
            supertrend.loc[first_valid_loc] = lower_band.loc[first_valid_loc]
        else:
            direction.loc[first_valid_loc] = -1  # -1 for Down
            supertrend.loc[first_valid_loc] = upper_band.loc[first_valid_loc]

        for i in range(first_valid_idx_loc + 1, len(df_clean)):
            current_index = df_clean.index[i]
            prev_index = df_clean.index[i - 1]
            prev_direction = direction.loc[prev_index]
            prev_supertrend = supertrend.loc[prev_index]
            curr_close = df_clean["close"].loc[current_index]

            if curr_close > prev_supertrend and prev_direction == -1:
                # Flip from Down to Up
                direction.loc[current_index] = 1
                supertrend.loc[current_index] = lower_band.loc[current_index]
            elif curr_close < prev_supertrend and prev_direction == 1:
                # Flip from Up to Down
                direction.loc[current_index] = -1
                supertrend.loc[current_index] = upper_band.loc[current_index]
            else:
                # Continue in the same direction
                direction.loc[current_index] = prev_direction
                if prev_direction == 1:
                    supertrend.loc[current_index] = max(
                        lower_band.loc[current_index],
                        prev_supertrend,
                    )
                else:
                    supertrend.loc[current_index] = min(
                        upper_band.loc[current_index],
                        prev_supertrend,
                    )

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
            nan_series = pd.Series(np.nan, index=self.df.index)
            return nan_series, nan_series, nan_series

        macd_result = ta.macd(
            self.df["close"],
            fast=fast_period,
            slow=slow_period,
            signal=signal_period,
        )
        if macd_result.empty or macd_result.isnull().all().all():
            nan_series = pd.Series(np.nan, index=self.df.index)
            return nan_series, nan_series, nan_series

        # Ensure column names are correct as per pandas_ta conventions
        macd_line = macd_result[f"MACD_{fast_period}_{slow_period}_{signal_period}"]
        signal_line = macd_result[f"MACDs_{fast_period}_{slow_period}_{signal_period}"]
        histogram = macd_result[f"MACDh_{fast_period}_{slow_period}_{signal_period}"]

        return (
            self._safe_series_op(macd_line, "MACD_Line"),
            self._safe_series_op(signal_line, "MACD_Signal"),
            self._safe_series_op(histogram, "MACD_Hist"),
        )

    def calculate_rsi(self, period: int) -> pd.Series:
        """Calculate Relative Strength Index (RSI)."""
        if len(self.df) <= period:
            return pd.Series(np.nan, index=self.df.index)
        rsi = ta.rsi(self.df["close"], length=period)
        return (
            self._safe_series_op(rsi, "RSI").fillna(0).clip(0, 100)
        )  # Clip to [0, 100] and fill NaNs

    def calculate_stoch_rsi(
        self,
        period: int,
        k_period: int,
        d_period: int,
    ) -> tuple[pd.Series, pd.Series]:
        """Calculate Stochastic RSI."""
        if len(self.df) <= period:
            nan_series = pd.Series(np.nan, index=self.df.index)
            return nan_series, nan_series

        rsi = self.calculate_rsi(period=period)
        if rsi.isnull().all():
            nan_series = pd.Series(np.nan, index=self.df.index)
            return nan_series, nan_series

        lowest_rsi = rsi.rolling(window=period, min_periods=period).min()
        highest_rsi = rsi.rolling(window=period, min_periods=period).max()

        denominator = highest_rsi - lowest_rsi
        # Replace 0 with NaN for division, then fillna(0) for the result later
        stoch_rsi_k_raw = ((rsi - lowest_rsi) / denominator.replace(0, np.nan)) * 100
        stoch_rsi_k_raw = (
            self._safe_series_op(stoch_rsi_k_raw, "StochRSI_K_raw")
            .fillna(0)
            .clip(0, 100)
        )

        stoch_rsi_k = (
            stoch_rsi_k_raw.rolling(window=k_period, min_periods=k_period)
            .mean()
            .fillna(0)
        )
        stoch_rsi_d = (
            stoch_rsi_k.rolling(window=d_period, min_periods=d_period).mean().fillna(0)
        )

        return self._safe_series_op(stoch_rsi_k, "StochRSI_K"), self._safe_series_op(
            stoch_rsi_d,
            "StochRSI_D",
        )

    def calculate_adx(self, period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Average Directional Index (ADX)."""
        if len(self.df) < period * 2:  # Requires ATR (period) and then ADX (period)
            nan_series = pd.Series(np.nan, index=self.df.index)
            return nan_series, nan_series, nan_series

        tr_series = self.df[
            "TR"
        ]  # Should have been calculated by _calculate_all_indicators
        if tr_series.isnull().all():
            nan_series = pd.Series(np.nan, index=self.df.index)
            return nan_series, nan_series, nan_series

        plus_dm = self.df["high"].diff().fillna(0)
        minus_dm = -self.df["low"].diff().fillna(0)

        # Calculate directional movement: +DM only if positive and greater than -DM
        # -DM only if positive and greater than +DM
        pos_dm = pd.Series(0.0, index=self.df.index)
        neg_dm = pd.Series(0.0, index=self.df.index)

        # vectorized comparison
        pos_dm[(plus_dm > minus_dm) & (plus_dm > 0)] = plus_dm
        neg_dm[(minus_dm > plus_dm) & (minus_dm > 0)] = minus_dm

        # Smooth +DM, -DM, and TR using EMA (wilder smoothing)
        # EWM with adjust=False approximates Wilder's Smoothing
        # Min_periods ensures that calculation only starts when enough data is available
        exp_plus_dm = pos_dm.ewm(span=period, adjust=False, min_periods=period).mean()
        exp_minus_dm = neg_dm.ewm(span=period, adjust=False, min_periods=period).mean()
        exp_tr = tr_series.ewm(span=period, adjust=False, min_periods=period).mean()

        # Avoid division by zero
        exp_tr_safe = exp_tr.replace(0, np.nan)

        plus_di = (exp_plus_dm / exp_tr_safe) * 100
        minus_di = (exp_minus_dm / exp_tr_safe) * 100

        di_diff = (plus_di - minus_di).abs()
        di_sum = plus_di + minus_di

        # Avoid division by zero
        di_sum_safe = di_sum.replace(0, np.nan)
        dx = (di_diff / di_sum_safe) * 100

        adx = dx.ewm(span=period, adjust=False, min_periods=period).mean()

        return (
            self._safe_series_op(adx, "ADX").fillna(0).clip(0, 100),
            self._safe_series_op(plus_di, "PlusDI").fillna(0).clip(0, 100),
            self._safe_series_op(minus_di, "MinusDI").fillna(0).clip(0, 100),
        )

    def calculate_bollinger_bands(
        self,
        period: int,
        std_dev: float,
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands."""
        if len(self.df) < period:
            nan_series = pd.Series(np.nan, index=self.df.index)
            return nan_series, nan_series, nan_series
        bbands = ta.bbands(self.df["close"], length=period, std=std_dev)

        # Adjust column names as pandas_ta can return them with prefixes
        upper_col = f"BBU_{period}_{std_dev}"
        middle_col = f"BBM_{period}_{std_dev}"
        lower_col = f"BBL_{period}_{std_dev}"

        if (
            upper_col not in bbands.columns
        ):  # Fallback if specific column name not found
            upper_col = bbands.columns[bbands.columns.str.startswith("BBU_")][0]
            middle_col = bbands.columns[bbands.columns.str.startswith("BBM_")][0]
            lower_col = bbands.columns[bbands.columns.str.startswith("BBL_")][0]

        upper_band = self._safe_series_op(bbands[upper_col], "BB_Upper")
        middle_band = self._safe_series_op(bbands[middle_col], "BB_Middle")
        lower_band = self._safe_series_op(bbands[lower_col], "BB_Lower")
        return upper_band, middle_band, lower_band

    def calculate_vwap(self, daily_reset: bool = False) -> pd.Series:
        """Calculate Volume Weighted Average Price (VWAP)."""
        if self.df.empty:
            return pd.Series(np.nan, index=self.df.index)

        # Ensure volume is numeric and not zero
        valid_volume = self.df["volume"].replace(0, np.nan).astype(float)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3

        if daily_reset:
            # Group by date and calculate cumsum within each day
            vwap_series = []
            for date, group in self.df.groupby(self.df.index.date):
                # Ensure indexing is correct for each group
                group_typical_price = typical_price.loc[group.index]
                group_valid_volume = valid_volume.loc[group.index]

                group_tp_vol = (group_typical_price * group_valid_volume).cumsum()
                group_vol = group_valid_volume.cumsum()

                # Avoid division by zero
                vwap_series.append(group_tp_vol / group_vol.replace(0, np.nan))

            if not vwap_series:
                return pd.Series(np.nan, index=self.df.index)

            vwap = pd.concat(vwap_series).reindex(self.df.index)
        else:
            # Continuous VWAP over the entire DataFrame
            cumulative_tp_vol = (typical_price * valid_volume).cumsum()
            cumulative_vol = valid_volume.cumsum()
            vwap = (cumulative_tp_vol / cumulative_vol.replace(0, np.nan)).reindex(
                self.df.index,
            )

        return self._safe_series_op(
            vwap,
            "VWAP",
        ).ffill()  # Forward fill NaNs if volume is zero, as VWAP typically holds

    def calculate_cci(self, period: int) -> pd.Series:
        """Calculate Commodity Channel Index (CCI)."""
        if len(self.df) < period:
            return pd.Series(np.nan, index=self.df.index)
        cci = ta.cci(self.df["high"], self.df["low"], self.df["close"], length=period)
        return self._safe_series_op(cci, "CCI")

    def calculate_williams_r(self, period: int) -> pd.Series:
        """Calculate Williams %R."""
        if len(self.df) < period:
            return pd.Series(np.nan, index=self.df.index)
        wr = ta.willr(self.df["high"], self.df["low"], self.df["close"], length=period)
        return (
            self._safe_series_op(wr, "WR").fillna(-50).clip(-100, 0)
        )  # Fill NaNs, clip to [-100, 0]

    def calculate_ichimoku_cloud(
        self,
        tenkan_period: int,
        kijun_period: int,
        senkou_span_b_period: int,
        chikou_span_offset: int,
    ) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
        """Calculate Ichimoku Cloud components."""
        required_len = (
            max(tenkan_period, kijun_period, senkou_span_b_period) + chikou_span_offset
        )
        if len(self.df) < required_len:
            nan_series = pd.Series(np.nan, index=self.df.index)
            return nan_series, nan_series, nan_series, nan_series, nan_series

        # Calculate Tenkan-sen and Kijun-sen
        tenkan_sen = (
            self.df["high"]
            .rolling(window=tenkan_period, min_periods=tenkan_period)
            .max()
            + self.df["low"]
            .rolling(window=tenkan_period, min_periods=tenkan_period)
            .min()
        ) / 2

        kijun_sen = (
            self.df["high"].rolling(window=kijun_period, min_periods=kijun_period).max()
            + self.df["low"]
            .rolling(window=kijun_period, min_periods=kijun_period)
            .min()
        ) / 2

        # Calculate Senkou Span A (Future Kumo boundary)
        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(
            kijun_period,
        )  # Future projection

        # Calculate Senkou Span B (Future Kumo boundary)
        senkou_span_b = (
            (
                self.df["high"]
                .rolling(window=senkou_span_b_period, min_periods=senkou_span_b_period)
                .max()
                + self.df["low"]
                .rolling(window=senkou_span_b_period, min_periods=senkou_span_b_period)
                .min()
            )
            / 2
        ).shift(kijun_period)  # Future projection

        # Calculate Chikou Span (Past price projection)
        chikou_span = self.df["close"].shift(-chikou_span_offset)

        return (
            self._safe_series_op(tenkan_sen, "Tenkan_Sen"),
            self._safe_series_op(kijun_sen, "Kijun_Sen"),
            self._safe_series_op(senkou_span_a, "Senkou_Span_A"),
            self._safe_series_op(senkou_span_b, "Senkou_Span_B"),
            self._safe_series_op(chikou_span, "Chikou_Span"),
        )

    def calculate_mfi(self, period: int) -> pd.Series:
        """Calculate Money Flow Index (MFI)."""
        if len(self.df) <= period:
            return pd.Series(np.nan, index=self.df.index)
        mfi = ta.mfi(
            self.df["high"],
            self.df["low"],
            self.df["close"],
            self.df["volume"],
            length=period,
        )
        return (
            self._safe_series_op(mfi, "MFI").fillna(50).clip(0, 100)
        )  # Fill NaNs with 50 (neutral), clip to [0, 100]

    def calculate_obv(self, ema_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate On-Balance Volume (OBV) and its EMA."""
        if len(self.df) < MIN_DATA_POINTS_OBV:
            nan_series = pd.Series(np.nan, index=self.df.index)
            return nan_series, nan_series

        obv = ta.obv(self.df["close"], self.df["volume"])
        obv_ema = ta.ema(obv, length=ema_period)

        return self._safe_series_op(obv, "OBV"), self._safe_series_op(
            obv_ema,
            "OBV_EMA",
        )

    def calculate_cmf(self, period: int) -> pd.Series:
        """Calculate Chaikin Money Flow (CMF)."""
        if len(self.df) < period:
            return pd.Series(np.nan, index=self.df.index)

        cmf = ta.cmf(
            self.df["high"],
            self.df["low"],
            self.df["close"],
            self.df["volume"],
            length=period,
        )
        return (
            self._safe_series_op(cmf, "CMF").fillna(0).clip(-1, 1)
        )  # Fill NaNs with 0, clip to [-1, 1]

    def calculate_psar(
        self,
        acceleration: float,
        max_acceleration: float,
    ) -> tuple[pd.Series, pd.Series]:
        """Calculate Parabolic SAR."""
        if len(self.df) < MIN_DATA_POINTS_PSAR_INITIAL:
            nan_series = pd.Series(np.nan, index=self.df.index)
            return nan_series, nan_series

        psar_result = ta.psar(
            self.df["high"],
            self.df["low"],
            self.df["close"],
            af0=acceleration,
            af=acceleration,
            max_af=max_acceleration,
        )

        if not isinstance(psar_result, pd.DataFrame):
            self.logger.error(
                f"{NEON_RED}pandas_ta.psar did not return a DataFrame. Type: {type(psar_result)}{RESET}",
            )
            nan_series = pd.Series(np.nan, index=self.df.index)
            return nan_series, nan_series

        # Pandas_ta PSAR columns for reversal, long, short
        psar_val_col_r = f"PSARr_{acceleration}_{max_acceleration}"
        psar_val_col_l = f"PSARl_{acceleration}_{max_acceleration}"
        psar_val_col_s = f"PSARs_{acceleration}_{max_acceleration}"

        # Combine PSARr (reversal) with PSARl (long trend) or PSARs (short trend)
        # PSARr is the actual SAR value to use
        psar_val = self._safe_series_op(psar_result.get(psar_val_col_r), "PSAR_Val_Raw")

        # Determine direction based on price relative to PSAR value.
        # 1 for uptrend, -1 for downtrend.
        direction = pd.Series(0, index=self.df.index, dtype=int)

        first_valid_idx = psar_val.first_valid_index()
        if first_valid_idx is None:
            return pd.Series(np.nan, index=self.df.index), pd.Series(
                np.nan,
                index=self.df.index,
            )

        # Initial direction based on first valid PSAR point
        if self.df["close"].loc[first_valid_idx] > psar_val.loc[first_valid_idx]:
            direction.loc[first_valid_idx] = 1  # Up trend
        else:
            direction.loc[first_valid_idx] = -1  # Down trend

        for i in range(self.df.index.get_loc(first_valid_idx) + 1, len(self.df)):
            current_idx = self.df.index[i]
            prev_idx = self.df.index[i - 1]

            if pd.isna(psar_val.loc[current_idx]) or pd.isna(
                self.df["close"].loc[current_idx],
            ):
                direction.loc[current_idx] = direction.loc[
                    prev_idx
                ]  # Carry forward if current data is NaN
                continue

            # If previous direction was up, and price falls below PSAR, reverse
            if (
                direction.loc[prev_idx] == 1
                and self.df["close"].loc[current_idx] < psar_val.loc[current_idx]
            ):
                direction.loc[current_idx] = -1
            # If previous direction was down, and price rises above PSAR, reverse
            elif (
                direction.loc[prev_idx] == -1
                and self.df["close"].loc[current_idx] > psar_val.loc[current_idx]
            ):
                direction.loc[current_idx] = 1
            else:
                direction.loc[current_idx] = direction.loc[
                    prev_idx
                ]  # Continue current direction

        psar_val = self._safe_series_op(
            psar_val,
            "PSAR_Val",
        ).ffill()  # Forward fill any gaps for PSAR value
        direction = self._safe_series_op(direction, "PSAR_Dir")

        return psar_val, direction

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

        decimal_high = Decimal(str(recent_high))
        decimal_low = Decimal(str(recent_low))
        decimal_diff = Decimal(str(diff))

        # Use precision manager to format prices
        def format_fib_level(price: Decimal) -> Decimal:
            return self.precision_manager.format_price(price)

        self.fib_levels = {
            "0.0%": format_fib_level(decimal_high),
            "23.6%": format_fib_level(decimal_high - Decimal("0.236") * decimal_diff),
            "38.2%": format_fib_level(decimal_high - Decimal("0.382") * decimal_diff),
            "50.0%": format_fib_level(decimal_high - Decimal("0.500") * decimal_diff),
            "61.8%": format_fib_level(decimal_high - Decimal("0.618") * decimal_diff),
            "78.6%": format_fib_level(decimal_high - Decimal("0.786") * decimal_diff),
            "100.0%": format_fib_level(decimal_low),
        }
        self.logger.debug(
            f"[{self.symbol}] Calculated Fibonacci levels: {self.fib_levels}",
        )

    def calculate_volatility_index(self, period: int) -> pd.Series:
        """Calculate a simple Volatility Index based on ATR normalized by price."""
        if (
            len(self.df) < period
            or "ATR" not in self.df.columns
            or self.df["ATR"].isnull().all()
        ):
            return pd.Series(np.nan, index=self.df.index)

        # ATR is already calculated
        # Avoid division by zero for close price
        normalized_atr = self.df["ATR"] / self.df["close"].replace(0, np.nan)
        volatility_index = normalized_atr.rolling(
            window=period,
            min_periods=period,
        ).mean()
        return self._safe_series_op(volatility_index, "Volatility_Index").fillna(0)

    def calculate_vwma(self, period: int) -> pd.Series:
        """Calculate Volume Weighted Moving Average (VWMA)."""
        if len(self.df) < period or self.df["volume"].isnull().any():
            return pd.Series(np.nan, index=self.df.index)

        # Ensure volume is numeric and not zero
        valid_volume = self.df["volume"].replace(0, np.nan).astype(float)
        pv = self.df["close"] * valid_volume
        # Use min_periods for rolling sums
        vwma = pv.rolling(window=period, min_periods=1).sum() / valid_volume.rolling(
            window=period,
            min_periods=1,
        ).sum().replace(0, np.nan)
        return self._safe_series_op(
            vwma,
            "VWMA",
        ).ffill()  # Forward fill NaNs if volume is zero, as VWMA typically holds

    def calculate_volume_delta(self, period: int) -> pd.Series:
        """Calculate Volume Delta, indicating buying vs selling pressure."""
        if len(self.df) < MIN_DATA_POINTS_VOLUME_DELTA:
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
        return self._safe_series_op(volume_delta.fillna(0), "Volume_Delta").clip(
            -1,
            1,
        )  # Fill NaNs with 0, clip to [-1, 1]

    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        """Safely retrieve an indicator value."""
        return self.indicator_values.get(key, default)

    async def _check_orderbook(
        self,
        current_price: Decimal,
        orderbook_manager: Any,
    ) -> float:
        """Analyze orderbook imbalance. Placeholder as AdvancedOrderbookManager is not provided."""
        # The original code's orderbook_manager was passed, but it's not implemented.
        # For now, this will return 0.0. If a real orderbook_manager were provided,
        # it would fetch real-time bids/asks and calculate imbalance.
        # bids, asks = await self.exchange_client.fetch_orderbook(self.symbol, self.config["orderbook_limit"])
        # if bids and asks:
        #    bid_volume = sum(Decimal(str(b[1])) for b in bids) # Assuming [[price, qty], ...]
        #    ask_volume = sum(Decimal(str(a[1])) for a in asks)
        #    total_volume = bid_volume + ask_volume
        #    if total_volume == 0:
        #        return 0.0
        #    imbalance = (bid_volume - ask_volume) / total_volume
        #    return float(imbalance)
        self.logger.debug("Orderbook imbalance check is a placeholder, returning 0.0.")
        return 0.0

    def _get_mtf_trend(self, higher_tf_df: pd.DataFrame, indicator_type: str) -> str:
        """Determine trend from higher timeframe using specified indicator."""
        if higher_tf_df.empty:
            return "UNKNOWN"

        last_close = higher_tf_df["close"].iloc[-1]
        period = self.config["mtf_analysis"]["trend_period"]

        if indicator_type == "sma":
            if len(higher_tf_df) < period:
                self.logger.debug(
                    f"MTF SMA: Not enough data for {period} period. Have {len(higher_tf_df)}.",
                )
                return "UNKNOWN"
            sma = ta.sma(higher_tf_df["close"], length=period).iloc[-1]
            if not pd.isna(sma):
                if last_close > sma:
                    return "UP"
                if last_close < sma:
                    return "DOWN"
            return "SIDEWAYS"
        if indicator_type == "ema":
            if len(higher_tf_df) < period:
                self.logger.debug(
                    f"MTF EMA: Not enough data for {period} period. Have {len(higher_tf_df)}.",
                )
                return "UNKNOWN"
            ema = ta.ema(higher_tf_df["close"], length=period).iloc[-1]
            if not pd.isna(ema):
                if last_close > ema:
                    return "UP"
                if last_close < ema:
                    return "DOWN"
            return "SIDEWAYS"
        if indicator_type == "ehlers_supertrend":
            # Temporarily create an analyzer for the higher timeframe data to get ST direction
            temp_config = self.config.copy()
            temp_config["indicators"]["ehlers_supertrend"] = (
                True  # Ensure ST is enabled for temp analyzer
            )

            # Pass the same exchange client to the temporary analyzer
            temp_analyzer = TradingAnalyzer(
                higher_tf_df,
                temp_config,
                self.logger,
                self.symbol,
                self.exchange_client,
            )
            st_dir = temp_analyzer._get_indicator_value("ST_Slow_Dir")
            if not pd.isna(st_dir):
                if st_dir == 1:
                    return "UP"
                if st_dir == -1:
                    return "DOWN"
            return "UNKNOWN"
        return "UNKNOWN"

    async def generate_trading_signal(
        self,
        current_price: Decimal,
        orderbook_manager: Any,  # This remains Any as it's a placeholder
        mtf_trends: dict[str, str],
        gemini_analysis: dict | None = None,  # Added Gemini AI analysis parameter
    ) -> tuple[str, float]:
        """Generate a signal using confluence of indicators, including Ehlers SuperTrend."""
        signal_score = 0.0
        active_indicators = self.config["indicators"]
        weights = self.weights
        isd = self.indicator_settings

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}",
            )
            return "HOLD", 0.0

        current_close = Decimal(str(self.df["close"].iloc[-1]))
        prev_close_series = self.df["close"].iloc[-2] if len(self.df) > 1 else np.nan
        prev_close = (
            Decimal(str(prev_close_series))
            if not pd.isna(prev_close_series)
            else current_close
        )

        self.logger.debug(f"[{self.symbol}] --- Signal Scoring ---")

        # EMA Alignment
        if active_indicators.get("ema_alignment", False):
            ema_short = self._get_indicator_value("EMA_Short")
            ema_long = self._get_indicator_value("EMA_Long")
            if not pd.isna(ema_short) and not pd.isna(ema_long):
                if ema_short > ema_long:
                    signal_score += weights.get("ema_alignment", 0)
                    self.logger.debug(
                        f"  EMA Alignment: Bullish (+{weights.get('ema_alignment', 0):.2f})",
                    )
                elif ema_short < ema_long:
                    signal_score -= weights.get("ema_alignment", 0)
                    self.logger.debug(
                        f"  EMA Alignment: Bearish (-{weights.get('ema_alignment', 0):.2f})",
                    )

        # SMA Trend Filter
        if active_indicators.get("sma_trend_filter", False):
            sma_long = self._get_indicator_value("SMA_Long")
            if not pd.isna(sma_long):
                if current_close > sma_long:
                    signal_score += weights.get("sma_trend_filter", 0)
                    self.logger.debug(
                        f"  SMA Trend Filter: Bullish (+{weights.get('sma_trend_filter', 0):.2f})",
                    )
                elif current_close < sma_long:
                    signal_score -= weights.get("sma_trend_filter", 0)
                    self.logger.debug(
                        f"  SMA Trend Filter: Bearish (-{weights.get('sma_trend_filter', 0):.2f})",
                    )

        # Momentum Indicators (RSI, StochRSI, CCI, WR, MFI)
        if active_indicators.get("momentum", False):
            momentum_weight = weights.get("momentum_rsi_stoch_cci_wr_mfi", 0)

            # RSI
            if active_indicators.get("rsi", False):
                rsi = self._get_indicator_value("RSI")
                if not pd.isna(rsi):
                    if rsi < isd["rsi_oversold"]:
                        signal_score += momentum_weight * 0.5
                        self.logger.debug(
                            f"  RSI: Oversold (+{momentum_weight * 0.5:.2f})",
                        )
                    elif rsi > isd["rsi_overbought"]:
                        signal_score -= momentum_weight * 0.5
                        self.logger.debug(
                            f"  RSI: Overbought (-{momentum_weight * 0.5:.2f})",
                        )

            # StochRSI Crossover
            if active_indicators.get("stoch_rsi", False):
                stoch_k = self._get_indicator_value("StochRSI_K")
                stoch_d = self._get_indicator_value("StochRSI_D")
                if not pd.isna(stoch_k) and not pd.isna(stoch_d) and len(self.df) > 1:
                    prev_stoch_k = (
                        self.df["StochRSI_K"].iloc[-2]
                        if "StochRSI_K" in self.df.columns
                        else np.nan
                    )
                    prev_stoch_d = (
                        self.df["StochRSI_D"].iloc[-2]
                        if "StochRSI_D" in self.df.columns
                        else np.nan
                    )
                    if (
                        stoch_k > stoch_d
                        and (
                            pd.isna(prev_stoch_k)
                            or pd.isna(prev_stoch_d)
                            or prev_stoch_k <= prev_stoch_d
                        )
                        and stoch_k < isd["stoch_rsi_oversold"]
                    ):
                        signal_score += momentum_weight * 0.6
                        self.logger.debug(
                            f"  StochRSI: Bullish crossover from oversold (+{momentum_weight * 0.6:.2f})",
                        )
                    elif (
                        stoch_k < stoch_d
                        and (
                            pd.isna(prev_stoch_k)
                            or pd.isna(prev_stoch_d)
                            or prev_stoch_k >= prev_stoch_d
                        )
                        and stoch_k > isd["stoch_rsi_overbought"]
                    ):
                        signal_score -= momentum_weight * 0.6
                        self.logger.debug(
                            f"  StochRSI: Bearish crossover from overbought (-{momentum_weight * 0.6:.2f})",
                        )
                    elif stoch_k > stoch_d and stoch_k < 50:  # General bullish momentum
                        signal_score += momentum_weight * 0.2
                        self.logger.debug(
                            f"  StochRSI: General bullish momentum (+{momentum_weight * 0.2:.2f})",
                        )
                    elif stoch_k < stoch_d and stoch_k > 50:  # General bearish momentum
                        signal_score -= momentum_weight * 0.2
                        self.logger.debug(
                            f"  StochRSI: General bearish momentum (-{momentum_weight * 0.2:.2f})",
                        )

            # CCI
            if active_indicators.get("cci", False):
                cci = self._get_indicator_value("CCI")
                if not pd.isna(cci):
                    if cci < isd["cci_oversold"]:
                        signal_score += momentum_weight * 0.4
                        self.logger.debug(
                            f"  CCI: Oversold (+{momentum_weight * 0.4:.2f})",
                        )
                    elif cci > isd["cci_overbought"]:
                        signal_score -= momentum_weight * 0.4
                        self.logger.debug(
                            f"  CCI: Overbought (-{momentum_weight * 0.4:.2f})",
                        )

            # Williams %R
            if active_indicators.get("wr", False):
                wr = self._get_indicator_value("WR")
                if not pd.isna(wr):
                    if wr < isd["williams_r_oversold"]:
                        signal_score += momentum_weight * 0.4
                        self.logger.debug(
                            f"  WR: Oversold (+{momentum_weight * 0.4:.2f})",
                        )
                    elif wr > isd["williams_r_overbought"]:
                        signal_score -= momentum_weight * 0.4
                        self.logger.debug(
                            f"  WR: Overbought (-{momentum_weight * 0.4:.2f})",
                        )

            # MFI
            if active_indicators.get("mfi", False):
                mfi = self._get_indicator_value("MFI")
                if not pd.isna(mfi):
                    if mfi < isd["mfi_oversold"]:
                        signal_score += momentum_weight * 0.4
                        self.logger.debug(
                            f"  MFI: Oversold (+{momentum_weight * 0.4:.2f})",
                        )
                    elif mfi > isd["mfi_overbought"]:
                        signal_score -= momentum_weight * 0.4
                        self.logger.debug(
                            f"  MFI: Overbought (-{momentum_weight * 0.4:.2f})",
                        )

        # Bollinger Bands
        if active_indicators.get("bollinger_bands", False):
            bb_upper = self._get_indicator_value("BB_Upper")
            bb_lower = self._get_indicator_value("BB_Lower")
            if not pd.isna(bb_upper) and not pd.isna(bb_lower):
                if current_close < bb_lower:
                    signal_score += weights.get("bollinger_bands", 0) * 0.5
                    self.logger.debug(
                        f"  BB: Price below lower band (+{weights.get('bollinger_bands', 0) * 0.5:.2f})",
                    )
                elif current_close > bb_upper:
                    signal_score -= weights.get("bollinger_bands", 0) * 0.5
                    self.logger.debug(
                        f"  BB: Price above upper band (-{weights.get('bollinger_bands', 0) * 0.5:.2f})",
                    )

        # VWAP
        if active_indicators.get("vwap", False):
            vwap = self._get_indicator_value("VWAP")
            if not pd.isna(vwap):
                if current_close > vwap:
                    signal_score += weights.get("vwap", 0) * 0.2
                    self.logger.debug(
                        f"  VWAP: Price above VWAP (+{weights.get('vwap', 0) * 0.2:.2f})",
                    )
                elif current_close < vwap:
                    signal_score -= weights.get("vwap", 0) * 0.2
                    self.logger.debug(
                        f"  VWAP: Price below VWAP (-{weights.get('vwap', 0) * 0.2:.2f})",
                    )

                if len(self.df) > 1:
                    prev_vwap_series = (
                        self.df["VWAP"].iloc[-2]
                        if "VWAP" in self.df.columns
                        else np.nan
                    )
                    prev_vwap = (
                        Decimal(str(prev_vwap_series))
                        if not pd.isna(prev_vwap_series)
                        else vwap
                    )
                    if current_close > vwap and prev_close <= prev_vwap:
                        signal_score += weights.get("vwap", 0) * 0.3
                        self.logger.debug(
                            f"  VWAP: Bullish crossover detected (+{weights.get('vwap', 0) * 0.3:.2f})",
                        )
                    elif current_close < vwap and prev_close >= prev_vwap:
                        signal_score -= weights.get("vwap", 0) * 0.3
                        self.logger.debug(
                            f"  VWAP: Bearish crossover detected (-{weights.get('vwap', 0) * 0.3:.2f})",
                        )

        # PSAR
        if active_indicators.get("psar", False):
            psar_val = self._get_indicator_value("PSAR_Val")
            psar_dir = self._get_indicator_value("PSAR_Dir")
            if not pd.isna(psar_val) and not pd.isna(psar_dir):
                if psar_dir == 1:  # Bullish direction
                    signal_score += weights.get("psar", 0) * 0.5
                    self.logger.debug(
                        f"  PSAR: Bullish direction (+{weights.get('psar', 0) * 0.5:.2f})",
                    )
                elif psar_dir == -1:  # Bearish direction
                    signal_score -= weights.get("psar", 0) * 0.5
                    self.logger.debug(
                        f"  PSAR: Bearish direction (-{weights.get('psar', 0) * 0.5:.2f})",
                    )

                if len(self.df) > 1:
                    prev_psar_val_series = (
                        self.df["PSAR_Val"].iloc[-2]
                        if "PSAR_Val" in self.df.columns
                        else np.nan
                    )
                    prev_psar_val = (
                        Decimal(str(prev_psar_val_series))
                        if not pd.isna(prev_psar_val_series)
                        else psar_val
                    )
                    if current_close > psar_val and prev_close <= prev_psar_val:
                        signal_score += weights.get("psar", 0) * 0.4
                        self.logger.debug(
                            f"  PSAR: Bullish reversal detected (+{weights.get('psar', 0) * 0.4:.2f})",
                        )
                    elif current_close < psar_val and prev_close >= prev_psar_val:
                        signal_score -= weights.get("psar", 0) * 0.4
                        self.logger.debug(
                            f"  PSAR: Bearish reversal detected (-{weights.get('psar', 0) * 0.4:.2f})",
                        )

        # Orderbook Imbalance
        if active_indicators.get("orderbook_imbalance", False) and orderbook_manager:
            imbalance = await self._check_orderbook(current_price, orderbook_manager)
            signal_score += imbalance * weights.get("orderbook_imbalance", 0)
            self.logger.debug(
                f"  Orderbook Imbalance: {imbalance:.2f} (Contribution: {imbalance * weights.get('orderbook_imbalance', 0):.2f})",
            )

        # Fibonacci Levels (confluence with price action)
        if active_indicators.get("fibonacci_levels", False) and self.fib_levels:
            for level_name, level_price in self.fib_levels.items():
                # Check if price is within a very small proximity of a Fibonacci level
                if level_name not in ["0.0%", "100.0%"] and (
                    level_price * Decimal("0.999")
                    <= current_price
                    <= level_price * Decimal("1.001")
                ):
                    self.logger.debug(
                        f"  Price near Fibonacci level {level_name}: {level_price.normalize()}",
                    )
                    if len(self.df) > 1:
                        if current_close > prev_close and current_close > level_price:
                            signal_score += weights.get("fibonacci_levels", 0) * 0.1
                            self.logger.debug(
                                f"  Fibonacci: Bullish breakout/bounce (+{weights.get('fibonacci_levels', 0) * 0.1:.2f})",
                            )
                        elif current_close < prev_close and current_close < level_price:
                            signal_score -= weights.get("fibonacci_levels", 0) * 0.1
                            self.logger.debug(
                                f"  Fibonacci: Bearish breakout/bounce (-{weights.get('fibonacci_levels', 0) * 0.1:.2f})",
                            )

        # --- Ehlers SuperTrend Alignment Scoring ---
        if active_indicators.get("ehlers_supertrend", False):
            st_fast_dir = self._get_indicator_value("ST_Fast_Dir")
            st_slow_dir = self._get_indicator_value("ST_Slow_Dir")
            prev_st_fast_dir_series = (
                self.df["st_fast_dir"].iloc[-2]
                if "st_fast_dir" in self.df.columns and len(self.df) > 1
                else np.nan
            )
            prev_st_fast_dir = (
                float(prev_st_fast_dir_series)
                if not pd.isna(prev_st_fast_dir_series)
                else np.nan
            )
            weight = weights.get("ehlers_supertrend_alignment", 0.0)

            if (
                not pd.isna(st_fast_dir)
                and not pd.isna(st_slow_dir)
                and not pd.isna(prev_st_fast_dir)
            ):
                if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1:
                    signal_score += weight
                    self.logger.debug(
                        f"Ehlers SuperTrend: Strong BUY signal (fast flip aligned with slow trend) (+{weight:.2f}).",
                    )
                elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1:
                    signal_score -= weight
                    self.logger.debug(
                        f"Ehlers SuperTrend: Strong SELL signal (fast flip aligned with slow trend) (-{weight:.2f}).",
                    )
                elif st_slow_dir == 1 and st_fast_dir == 1:
                    signal_score += weight * 0.3
                    self.logger.debug(
                        f"Ehlers SuperTrend: Bullish alignment (+{weight * 0.3:.2f}).",
                    )
                elif st_slow_dir == -1 and st_fast_dir == -1:
                    signal_score -= weight * 0.3
                    self.logger.debug(
                        f"Ehlers SuperTrend: Bearish alignment (-{weight * 0.3:.2f}).",
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
                prev_macd_line = (
                    self.df["MACD_Line"].iloc[-2]
                    if "MACD_Line" in self.df.columns
                    else np.nan
                )
                prev_signal_line = (
                    self.df["MACD_Signal"].iloc[-2]
                    if "MACD_Signal" in self.df.columns
                    else np.nan
                )

                if macd_line > signal_line and (
                    pd.isna(prev_macd_line)
                    or pd.isna(prev_signal_line)
                    or prev_macd_line <= prev_signal_line
                ):
                    signal_score += weight
                    self.logger.debug(
                        f"MACD: BUY signal (MACD line crossed above Signal line) (+{weight:.2f}).",
                    )
                elif macd_line < signal_line and (
                    pd.isna(prev_macd_line)
                    or pd.isna(prev_signal_line)
                    or prev_macd_line >= prev_signal_line
                ):
                    signal_score -= weight
                    self.logger.debug(
                        f"MACD: SELL signal (MACD line crossed below Signal line) (-{weight:.2f}).",
                    )
                elif histogram > 0 and (
                    len(self.df) > 2
                    and "MACD_Hist" in self.df.columns
                    and self.df["MACD_Hist"].iloc[-2] < 0
                ):
                    signal_score += weight * 0.2
                    self.logger.debug(
                        f"MACD: Histogram turned positive (+{weight * 0.2:.2f}).",
                    )
                elif histogram < 0 and (
                    len(self.df) > 2
                    and "MACD_Hist" in self.df.columns
                    and self.df["MACD_Hist"].iloc[-2] > 0
                ):
                    signal_score -= weight * 0.2
                    self.logger.debug(
                        f"MACD: Histogram turned negative (-{weight * 0.2:.2f}).",
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
                        signal_score += weight
                        self.logger.debug(
                            f"ADX: Strong BUY trend (ADX > {ADX_STRONG_TREND_THRESHOLD}, +DI > -DI) (+{weight:.2f}).",
                        )
                    elif minus_di > plus_di:
                        signal_score -= weight
                        self.logger.debug(
                            f"ADX: Strong SELL trend (ADX > {ADX_STRONG_TREND_THRESHOLD}, -DI > +DI) (-{weight:.2f}).",
                        )
                elif adx_val < ADX_WEAK_TREND_THRESHOLD:
                    # Neutral signal if trend is weak
                    self.logger.debug(
                        f"ADX: Weak trend (ADX < {ADX_WEAK_TREND_THRESHOLD}). Neutral signal.",
                    )

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
                prev_tenkan = (
                    self.df["Tenkan_Sen"].iloc[-2]
                    if "Tenkan_Sen" in self.df.columns
                    else np.nan
                )
                prev_kijun = (
                    self.df["Kijun_Sen"].iloc[-2]
                    if "Kijun_Sen" in self.df.columns
                    else np.nan
                )
                prev_senkou_a = (
                    self.df["Senkou_Span_A"].iloc[-2]
                    if "Senkou_Span_A" in self.df.columns
                    else np.nan
                )
                prev_senkou_b = (
                    self.df["Senkou_Span_B"].iloc[-2]
                    if "Senkou_Span_B" in self.df.columns
                    else np.nan
                )
                prev_chikou = (
                    self.df["Chikou_Span"].iloc[-2]
                    if "Chikou_Span" in self.df.columns
                    else np.nan
                )

                if tenkan_sen > kijun_sen and (
                    pd.isna(prev_tenkan)
                    or pd.isna(prev_kijun)
                    or prev_tenkan <= prev_kijun
                ):
                    signal_score += weight * 0.5
                    self.logger.debug(
                        f"Ichimoku: Tenkan-sen crossed above Kijun-sen (bullish) (+{weight * 0.5:.2f}).",
                    )
                elif tenkan_sen < kijun_sen and (
                    pd.isna(prev_tenkan)
                    or pd.isna(prev_kijun)
                    or prev_tenkan >= prev_kijun
                ):
                    signal_score -= weight * 0.5
                    self.logger.debug(
                        f"Ichimoku: Tenkan-sen crossed below Kijun-sen (bearish) (-{weight * 0.5:.2f}).",
                    )

                # Price breaking above/below Kumo (Cloud)
                kumo_top = max(senkou_span_a, senkou_span_b)
                kumo_bottom = min(senkou_span_a, senkou_span_b)
                prev_kumo_top = max(prev_senkou_a, prev_senkou_b)
                prev_kumo_bottom = min(prev_senkou_a, prev_senkou_b)

                if current_close > kumo_top and prev_close <= prev_kumo_top:
                    signal_score += weight * 0.7
                    self.logger.debug(
                        f"Ichimoku: Price broke above Kumo (strong bullish) (+{weight * 0.7:.2f}).",
                    )
                elif current_close < kumo_bottom and prev_close >= prev_kumo_bottom:
                    signal_score -= weight * 0.7
                    self.logger.debug(
                        f"Ichimoku: Price broke below Kumo (strong bearish) (-{weight * 0.7:.2f}).",
                    )

                # Chikou Span crossing price (confirmation)
                if chikou_span > current_close and (
                    pd.isna(prev_chikou) or prev_chikou <= prev_close
                ):
                    signal_score += weight * 0.3
                    self.logger.debug(
                        f"Ichimoku: Chikou Span crossed above price (bullish confirmation) (+{weight * 0.3:.2f}).",
                    )
                elif chikou_span < current_close and (
                    pd.isna(prev_chikou) or prev_chikou >= prev_close
                ):
                    signal_score -= weight * 0.3
                    self.logger.debug(
                        f"Ichimoku: Chikou Span crossed below price (bearish confirmation) (-{weight * 0.3:.2f}).",
                    )

        # --- OBV Alignment Scoring ---
        if active_indicators.get("obv", False):
            obv_val = self._get_indicator_value("OBV")
            obv_ema = self._get_indicator_value("OBV_EMA")
            weight = weights.get("obv_momentum", 0.0)

            if not pd.isna(obv_val) and not pd.isna(obv_ema) and len(self.df) > 1:
                prev_obv_val = (
                    self.df["OBV"].iloc[-2] if "OBV" in self.df.columns else np.nan
                )
                prev_obv_ema = (
                    self.df["OBV_EMA"].iloc[-2]
                    if "OBV_EMA" in self.df.columns
                    else np.nan
                )

                if obv_val > obv_ema and (
                    pd.isna(prev_obv_val)
                    or pd.isna(prev_obv_ema)
                    or prev_obv_val <= prev_obv_ema
                ):
                    signal_score += weight * 0.5
                    self.logger.debug(
                        f"  OBV: Bullish crossover detected (+{weight * 0.5:.2f}).",
                    )
                elif obv_val < obv_ema and (
                    pd.isna(prev_obv_val)
                    or pd.isna(prev_obv_ema)
                    or prev_obv_val >= prev_obv_ema
                ):
                    signal_score -= weight * 0.5
                    self.logger.debug(
                        f"  OBV: Bearish crossover detected (-{weight * 0.5:.2f}).",
                    )

                if len(self.df) > 2 and "OBV" in self.df.columns:
                    if (
                        obv_val > self.df["OBV"].iloc[-2]
                        and obv_val > self.df["OBV"].iloc[-3]
                    ):
                        signal_score += weight * 0.2
                        self.logger.debug(
                            f"  OBV: Increasing momentum (+{weight * 0.2:.2f}).",
                        )
                    elif (
                        obv_val < self.df["OBV"].iloc[-2]
                        and obv_val < self.df["OBV"].iloc[-3]
                    ):
                        signal_score -= weight * 0.2
                        self.logger.debug(
                            f"  OBV: Decreasing momentum (-{weight * 0.2:.2f}).",
                        )

        # --- CMF Alignment Scoring ---
        if active_indicators.get("cmf", False):
            cmf_val = self._get_indicator_value("CMF")
            weight = weights.get("cmf_flow", 0.0)

            if not pd.isna(cmf_val):
                if cmf_val > 0:
                    signal_score += weight * 0.5
                    self.logger.debug(
                        f"  CMF: Positive money flow (+{weight * 0.5:.2f}).",
                    )
                elif cmf_val < 0:
                    signal_score -= weight * 0.5
                    self.logger.debug(
                        f"  CMF: Negative money flow (-{weight * 0.5:.2f}).",
                    )

                if len(self.df) > 2 and "CMF" in self.df.columns:
                    if (
                        cmf_val > self.df["CMF"].iloc[-2]
                        and cmf_val > self.df["CMF"].iloc[-3]
                    ):
                        signal_score += weight * 0.3
                        self.logger.debug(
                            f"  CMF: Increasing bullish flow (+{weight * 0.3:.2f}).",
                        )
                    elif (
                        cmf_val < self.df["CMF"].iloc[-2]
                        and cmf_val < self.df["CMF"].iloc[-3]
                    ):
                        signal_score -= weight * 0.3
                        self.logger.debug(
                            f"  CMF: Increasing bearish flow (-{weight * 0.3:.2f}).",
                        )

        # --- Volatility Index Scoring ---
        if active_indicators.get("volatility_index", False):
            vol_idx = self._get_indicator_value("Volatility_Index")
            weight = weights.get("volatility_index_signal", 0.0)
            if (
                not pd.isna(vol_idx)
                and len(self.df) > 2
                and "Volatility_Index" in self.df.columns
            ):
                prev_vol_idx = self.df["Volatility_Index"].iloc[-2]
                prev_prev_vol_idx = self.df["Volatility_Index"].iloc[-3]

                if vol_idx > prev_vol_idx > prev_prev_vol_idx:  # Increasing volatility
                    if signal_score > 0:
                        signal_score += weight * 0.2
                        self.logger.debug(
                            f"  Volatility Index: Increasing volatility, adds confidence to BUY (+{weight * 0.2:.2f}).",
                        )
                    elif signal_score < 0:
                        signal_score -= weight * 0.2
                        self.logger.debug(
                            f"  Volatility Index: Increasing volatility, adds confidence to SELL (-{weight * 0.2:.2f}).",
                        )
                elif (
                    vol_idx < prev_vol_idx < prev_prev_vol_idx
                ):  # Decreasing volatility
                    if (
                        abs(signal_score) > 0
                    ):  # If there's an existing signal, slightly reduce its conviction
                        signal_score *= 1 - weight * 0.1  # Reduce by 10% of the weight
                        self.logger.debug(
                            f"  Volatility Index: Decreasing volatility, reduces signal conviction (x{(1 - weight * 0.1):.2f}).",
                        )

        # --- VWMA Cross Scoring ---
        if active_indicators.get("vwma", False):
            vwma = self._get_indicator_value("VWMA")
            weight = weights.get("vwma_cross", 0.0)
            if not pd.isna(vwma) and len(self.df) > 1:
                prev_vwma_series = (
                    self.df["VWMA"].iloc[-2] if "VWMA" in self.df.columns else np.nan
                )
                prev_vwma = (
                    Decimal(str(prev_vwma_series))
                    if not pd.isna(prev_vwma_series)
                    else vwma
                )
                if current_close > vwma and prev_close <= prev_vwma:
                    signal_score += weight
                    self.logger.debug(
                        f"  VWMA: Bullish crossover (price above VWMA) (+{weight:.2f}).",
                    )
                elif current_close < vwma and prev_close >= prev_vwma:
                    signal_score -= weight
                    self.logger.debug(
                        f"  VWMA: Bearish crossover (price below VWMA) (-{weight:.2f}).",
                    )

        # --- Volume Delta Scoring ---
        if active_indicators.get("volume_delta", False):
            volume_delta = self._get_indicator_value("Volume_Delta")
            volume_delta_threshold = isd["volume_delta_threshold"]
            weight = weights.get("volume_delta_signal", 0.0)

            if not pd.isna(volume_delta):
                if volume_delta > volume_delta_threshold:  # Strong buying pressure
                    signal_score += weight
                    self.logger.debug(
                        f"  Volume Delta: Strong buying pressure detected (+{weight:.2f}).",
                    )
                elif volume_delta < -volume_delta_threshold:  # Strong selling pressure
                    signal_score -= weight
                    self.logger.debug(
                        f"  Volume Delta: Strong selling pressure detected (-{weight:.2f}).",
                    )
                elif volume_delta > 0:
                    signal_score += weight * 0.3
                    self.logger.debug(
                        f"  Volume Delta: Moderate buying pressure detected (+{weight * 0.3:.2f}).",
                    )
                elif volume_delta < 0:
                    signal_score -= weight * 0.3
                    self.logger.debug(
                        f"  Volume Delta: Moderate selling pressure detected (-{weight * 0.3:.2f}).",
                    )

        # --- Multi-Timeframe Trend Confluence Scoring ---
        if self.config["mtf_analysis"]["enabled"] and mtf_trends:
            mtf_buy_score = 0
            mtf_sell_score = 0
            for _tf_indicator, trend in mtf_trends.items():
                if trend == "UP":
                    mtf_buy_score += 1
                elif trend == "DOWN":
                    mtf_sell_score += (
                        1  # Add for bearish MTF trend (for absolute comparison)
                    )

            mtf_weight = weights.get("mtf_trend_confluence", 0.0)
            if mtf_trends:
                total_mtf_indicators = len(mtf_trends)
                # Normalize the difference between bullish and bearish trends
                normalized_mtf_score = (
                    mtf_buy_score - mtf_sell_score
                ) / total_mtf_indicators

                signal_score += mtf_weight * normalized_mtf_score
                self.logger.debug(
                    f"MTF Confluence: Normalized Score {normalized_mtf_score:.2f} (Buy: {mtf_buy_score}, Sell: {mtf_sell_score}). Total MTF contribution: {mtf_weight * normalized_mtf_score:.2f}",
                )

        # --- Gemini AI Analysis Scoring ---
        if (
            self.config["gemini_ai_analysis"]["enabled"]
            and self.gemini_client
            and gemini_analysis
        ):
            self.logger.info(
                f"{NEON_PURPLE}Gemini AI Analysis: {json.dumps(gemini_analysis, indent=2)}{RESET}",
            )
            gemini_entry = gemini_analysis.get("entry")
            gemini_confidence = gemini_analysis.get("confidence_level", 0)
            gemini_weight = self.config["gemini_ai_analysis"]["weight"]

            if gemini_confidence >= 50:  # Only consider if confidence is reasonable
                if gemini_entry == "BUY":
                    signal_score += gemini_weight
                    self.logger.info(
                        f"{NEON_GREEN}Gemini AI recommends BUY (Confidence: {gemini_confidence}). Adding {gemini_weight} to signal score.{RESET}",
                    )
                elif gemini_entry == "SELL":
                    signal_score -= gemini_weight
                    self.logger.info(
                        f"{NEON_RED}Gemini AI recommends SELL (Confidence: {gemini_confidence}). Subtracting {gemini_weight} from signal score.{RESET}",
                    )
                else:
                    self.logger.info(
                        f"{NEON_YELLOW}Gemini AI recommends HOLD (Confidence: {gemini_confidence}). No change to signal score.{RESET}",
                    )
            else:
                self.logger.info(
                    f"{NEON_YELLOW}Gemini AI confidence ({gemini_confidence}) too low. Skipping influence on signal score.{RESET}",
                )
        elif self.config["gemini_ai_analysis"]["enabled"] and not gemini_analysis:
            self.logger.warning(
                f"{NEON_YELLOW}Gemini AI analysis enabled but no analysis data provided/returned. Skipping influence on signal score.{RESET}",
            )

        # --- Final Signal Determination ---
        threshold = Decimal(str(self.config["signal_score_threshold"]))
        final_signal = "HOLD"
        if signal_score >= threshold:
            final_signal = "BUY"
        elif signal_score <= -threshold:
            final_signal = "SELL"

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

        if signal == "BUY":
            stop_loss = current_price - (atr_value * stop_loss_atr_multiple)
            take_profit = current_price + (atr_value * take_profit_atr_multiple)
        elif signal == "SELL":
            stop_loss = current_price + (atr_value * stop_loss_atr_multiple)
            take_profit = current_price - (atr_value * take_profit_atr_multiple)
        else:
            return Decimal("0"), Decimal("0")

        return self.precision_manager.format_price(
            take_profit,
        ), self.precision_manager.format_price(stop_loss)


async def display_indicator_values_and_price(
    config: dict[str, Any],
    logger: logging.Logger,
    current_price: Decimal,
    analyzer: "TradingAnalyzer",
    orderbook_manager: Any,
    mtf_trends: dict[str, str],
) -> None:
    """Display current price and calculated indicator values."""
    logger.info(f"{NEON_BLUE}--- Current Market Data & Indicators ---{RESET}")
    logger.info(f"{NEON_GREEN}Current Price: {current_price.normalize()}{RESET}")

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
            logger.info(
                f"  {color}{indicator_name}: {value:.8f}{RESET}",
            )  # Display floats with more reasonable precision
        else:
            logger.info(f"  {color}{indicator_name}: {value}{RESET}")

    if analyzer.fib_levels:
        logger.info(f"{NEON_CYAN}\n--- Fibonacci Levels ---{RESET}")
        for level_name, level_price in analyzer.fib_levels.items():
            logger.info(
                f"  {NEON_YELLOW}{level_name}: {level_price.normalize()}{RESET}",
            )

    if mtf_trends:
        logger.info(f"{NEON_CYAN}\n--- Multi-Timeframe Trends ---{RESET}")
        for tf_indicator, trend in mtf_trends.items():
            logger.info(f"  {NEON_YELLOW}{tf_indicator}: {trend}{RESET}")

    if config["indicators"].get("orderbook_imbalance", False):
        imbalance = await analyzer._check_orderbook(current_price, orderbook_manager)
        logger.info(f"{NEON_CYAN}Orderbook Imbalance: {imbalance:.4f}{RESET}")

    logger.info(f"{NEON_BLUE}--------------------------------------{RESET}")


async def main_async_loop(
    config: dict[str, Any],
    logger: logging.Logger,
    exchange_client: ExchangeClient,
    position_manager: PositionManager,
    performance_tracker: PerformanceTracker,
    alert_system: AlertSystem,
    gemini_client: Any,
) -> None:
    """The main asynchronous loop for the trading bot."""
    while True:
        try:
            logger.info(
                f"{NEON_PURPLE}--- New Analysis Loop Started ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}) ---{RESET}",
            )
            current_price = await exchange_client.fetch_current_price(config["symbol"])
            if current_price is None:
                alert_system.send_alert(
                    f"[{config['symbol']}] Failed to fetch current price. Skipping loop.",
                    "WARNING",
                )
                await asyncio.sleep(config["loop_delay"])
                continue

            df = await exchange_client.fetch_klines(
                config["symbol"],
                config["interval"],
                200,
            )  # Increased limit for more robust indicator calc
            if df is None or df.empty:
                alert_system.send_alert(
                    f"[{config['symbol']}] Failed to fetch primary klines or DataFrame is empty. Skipping loop.",
                    "WARNING",
                )
                await asyncio.sleep(config["loop_delay"])
                continue

            # AdvancedOrderbookManager is not implemented, so this will remain None
            orderbook_data = None  # Or await exchange_client.fetch_orderbook(config["symbol"], config["orderbook_limit"])

            mtf_trends: dict[str, str] = {}
            if config["mtf_analysis"]["enabled"]:
                for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
                    logger.debug(f"Fetching klines for MTF interval: {htf_interval}")
                    htf_df = await exchange_client.fetch_klines(
                        config["symbol"],
                        htf_interval,
                        200,
                    )  # Increased limit
                    if htf_df is not None and not htf_df.empty:
                        for trend_ind in config["mtf_analysis"]["trend_indicators"]:
                            # A new TradingAnalyzer is created for each HTF to avoid cross-contamination
                            temp_htf_analyzer = TradingAnalyzer(
                                htf_df,
                                config,
                                logger,
                                config["symbol"],
                                exchange_client,
                            )
                            trend = temp_htf_analyzer._get_mtf_trend(
                                htf_df,
                                trend_ind,
                            )
                            mtf_trends[f"{htf_interval}_{trend_ind}"] = trend
                            logger.debug(
                                f"MTF Trend ({htf_interval}, {trend_ind}): {trend}",
                            )
                    else:
                        logger.warning(
                            f"{NEON_YELLOW}Could not fetch klines for higher timeframe {htf_interval} or it was empty. Skipping MTF trend for this TF.{RESET}",
                        )
                    await asyncio.sleep(
                        config["mtf_analysis"]["mtf_request_delay_seconds"],
                    )  # Delay between MTF requests

            analyzer = TradingAnalyzer(
                df,
                config,
                logger,
                config["symbol"],
                exchange_client,
            )

            if analyzer.df.empty:
                alert_system.send_alert(
                    f"[{config['symbol']}] TradingAnalyzer DataFrame is empty after indicator calculations. Cannot generate signal.",
                    "WARNING",
                )
                await asyncio.sleep(config["loop_delay"])
                continue

            # Placeholder for Gemini AI analysis call
            gemini_ai_result = None
            if config["gemini_ai_analysis"]["enabled"] and gemini_client:
                # In a real scenario, this would involve sending data to GeminiClient
                # gemini_ai_result = await gemini_client.analyze_market(current_price, analyzer.indicator_values, mtf_trends)
                logger.debug(
                    f"Gemini AI analysis placeholder triggered for {config['symbol']}.",
                )

            trading_signal, signal_score = await analyzer.generate_trading_signal(
                current_price,
                orderbook_data,
                mtf_trends,
                gemini_ai_result,
            )
            atr_value = Decimal(
                str(analyzer._get_indicator_value("ATR", Decimal("0.01"))),
            )  # Default to a small positive value if ATR is missing

            # Manage existing positions before potentially opening new ones
            await position_manager.manage_positions(
                current_price,
                atr_value,
                performance_tracker,
            )

            if (
                trading_signal == "BUY"
                and signal_score >= config["signal_score_threshold"]
            ):
                logger.info(
                    f"{NEON_GREEN}Strong BUY signal detected! Score: {signal_score:.2f}. Attempting to open position.{RESET}",
                )
                await position_manager.open_position("BUY", current_price, atr_value)
            elif (
                trading_signal == "SELL"
                and signal_score <= -config["signal_score_threshold"]
            ):
                logger.info(
                    f"{NEON_RED}Strong SELL signal detected! Score: {signal_score:.2f}. Attempting to open position.{RESET}",
                )
                await position_manager.open_position("SELL", current_price, atr_value)
            else:
                logger.info(
                    f"{NEON_BLUE}No strong trading signal. Holding. Score: {signal_score:.2f}{RESET}",
                )

            open_positions = position_manager.get_open_positions()
            if open_positions:
                logger.info(f"{NEON_CYAN}Open Positions: {len(open_positions)}{RESET}")
                for pos in open_positions:
                    current_trailing_sl_display = (
                        pos.get("current_trailing_sl").normalize()
                        if isinstance(pos.get("current_trailing_sl"), Decimal)
                        else pos.get("current_trailing_sl", "N/A")
                    )
                    logger.info(
                        f"  - {pos['side']} {pos['qty'].normalize()} @ {pos['entry_price'].normalize()} (SL: {pos['stop_loss'].normalize()}, TP: {pos['take_profit'].normalize()}, Trailing SL: {current_trailing_sl_display}){RESET}",
                    )
            else:
                logger.info(f"{NEON_CYAN}No open positions.{RESET}")

            perf_summary = performance_tracker.get_summary()
            logger.info(
                f"{NEON_YELLOW}Performance Summary: Total PnL: {perf_summary['total_pnl'].normalize():.2f}, Wins: {perf_summary['wins']}, Losses: {perf_summary['losses']}, Win Rate: {perf_summary['win_rate']}{RESET}",
            )

            # Display indicator values and price
            await display_indicator_values_and_price(
                config,
                logger,
                current_price,
                analyzer,
                orderbook_data,  # Pass orderbook_data (could be None)
                mtf_trends,
            )

            logger.info(
                f"{NEON_PURPLE}--- Analysis Loop Finished. Waiting {config['loop_delay']}s ---{RESET}",
            )
            await asyncio.sleep(config["loop_delay"])

        except asyncio.CancelledError:
            logger.info(f"{NEON_BLUE}Main loop cancelled gracefully.{RESET}")
            # Perform cleanup tasks here if needed before exiting the loop
            break
        except Exception as e:
            alert_system.send_alert(
                f"[{config['symbol']}] An unhandled error occurred in the main loop: {e}",
                "ERROR",
            )
            logger.exception(f"{NEON_RED}Unhandled exception in main loop:{RESET}")
            # Longer delay on error
            await asyncio.sleep(config["loop_delay"] * 2)


# --- Main execution ---
async def start_bot():
    """Main function to initialize and start the bot."""
    logger = setup_logger("whalebot_main", level=logging.INFO)
    config = load_config(CONFIG_FILE, logger)
    alert_system = AlertSystem(logger)

    # Validate intervals
    # Bybit CCXT intervals: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d, 1w, 1M
    valid_ccxt_bybit_intervals = [
        "1m",
        "3m",
        "5m",
        "15m",
        "30m",
        "1h",
        "2h",
        "4h",
        "6h",
        "12h",
        "1d",
        "1w",
        "1M",
    ]
    if config["interval"] not in valid_ccxt_bybit_intervals:
        logger.error(
            f"{NEON_RED}Invalid primary interval '{config['interval']}' in config.json. "
            f"Please use Bybit's valid CCXT string formats (e.g., '15m', '1h', '1d'). Exiting.{RESET}",
        )
        sys.exit(1)
    for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
        if htf_interval not in valid_ccxt_bybit_intervals:
            logger.error(
                f"{NEON_RED}Invalid higher timeframe interval '{htf_interval}' in config.json. "
                f"Please use Bybit's valid CCXT string formats (e.g., '1h', '4h'). Exiting.{RESET}",
            )
            sys.exit(1)

    if not API_KEY or not API_SECRET:
        logger.critical(
            f"{NEON_RED}BYBIT_API_KEY or BYBIT_API_SECRET environment variables are not set. Please set them before running the bot. Exiting.{RESET}",
        )
        sys.exit(1)

    logger.info(f"{NEON_GREEN}--- Whalebot Trading Bot Initialized ---{RESET}")
    logger.info(f"Symbol: {config['symbol']}, Interval: {config['interval']}")
    logger.info(f"Trade Management Enabled: {config['trade_management']['enabled']}")
    if config["trade_management"]["enabled"]:
        logger.info(
            f"Leverage: {config['trade_management']['leverage']}x, Order Mode: {config['trade_management']['order_mode']}",
        )
    else:
        logger.info(
            f"Using simulated balance for position sizing: {config['trade_management']['account_balance']:.2f} USDT",
        )

    # Initialize Exchange Client (CCXT)
    exchange_client = ExchangeClient(
        exchange_id="bybit",
        api_key=API_KEY,
        api_secret=API_SECRET,
        testnet=config["testnet"],
        logger=logger,
    )
    await exchange_client.load_markets()

    position_manager = PositionManager(
        config,
        logger,
        config["symbol"],
        exchange_client,
    )
    performance_tracker = PerformanceTracker(
        logger,
        config_file="bot_logs/trading-bot/trades.json",
    )

    gemini_client = None
    if config["gemini_ai_analysis"]["enabled"]:
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if gemini_api_key:
            # Placeholder for GeminiClient. In a real implementation, you'd
            # instantiate your GeminiClient class here, e.g.:
            # from your_gemini_module import GeminiClient
            # gemini_client = GeminiClient(
            #     api_key=gemini_api_key,
            #     model_name=config["gemini_ai_analysis"]["model_name"],
            #     temperature=config["gemini_ai_analysis"]["temperature"],
            #     top_p=config["gemini_ai_analysis"]["top_p"],
            #     logger=logger
            # )
            logger.warning(
                f"{NEON_YELLOW}Gemini AI analysis enabled, but GeminiClient is a placeholder (not implemented).{RESET}",
            )

            class MockGeminiClient:
                async def analyze_market(self, *args, **kwargs):
                    logger.warning("Mock GeminiClient.analyze_market called.")
                    # Simulate a response or return None
                    return {"entry": "HOLD", "confidence_level": 50}

            gemini_client = MockGeminiClient()
        else:
            logger.error(
                f"{NEON_RED}GEMINI_API_KEY not set, disabling Gemini AI analysis.{RESET}",
            )
            config["gemini_ai_analysis"]["enabled"] = False

    # Start the asynchronous main loop
    await main_async_loop(
        config,
        logger,
        exchange_client,
        position_manager,
        performance_tracker,
        alert_system,
        gemini_client,
    )


if __name__ == "__main__":
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        logger = setup_logger("whalebot_main")  # Get logger again for shutdown message
        logger.info(
            f"{NEON_BLUE}KeyboardInterrupt detected. Shutting down bot...{RESET}",
        )
    except Exception as e:
        logger = setup_logger("whalebot_main")  # Get logger again for critical errors
        logger.critical(
            f"{NEON_RED}Critical error during bot startup or top-level execution: {e}{RESET}",
            exc_info=True,
        )
        sys.exit(1)
