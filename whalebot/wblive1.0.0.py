import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal, getcontext
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, ClassVar, Literal

import numpy as np
import pandas as pd
from colorama import Fore, Style, init
from dotenv import load_dotenv

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
MIN_DATA_POINTS_TR = 2
MIN_DATA_POINTS_SMOOTHER = 2
MIN_DATA_POINTS_OBV = 2
MIN_DATA_POINTS_PSAR = 2
ADX_STRONG_TREND_THRESHOLD = 25
ADX_WEAK_TREND_THRESHOLD = 20
MIN_DATA_POINTS_VWMA = 2
MIN_DATA_POINTS_VOLATILITY = 2


# --- Helper Functions for Precision ---
def round_qty(qty: Decimal, qty_step: Decimal) -> Decimal:
    """Rounds the quantity down to the nearest multiple of qty_step."""
    if qty_step is None or qty_step.is_zero():
        # Fallback for safety, though it should be set.
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
        "symbol": "BTCUSDT",
        "interval": "15",
        "loop_delay": LOOP_DELAY_SECONDS,
        "orderbook_limit": 50,
        "signal_score_threshold": 2.0,
        "volume_confirmation_multiplier": 1.5,
        "trade_management": {
            "enabled": True,
            "account_balance": 1000.0,
            "risk_per_trade_percent": 1.0,
            "stop_loss_atr_multiple": 1.5,
            "take_profit_atr_multiple": 2.0,
            "max_open_positions": 1,
            "order_precision": 5,
            "price_precision": 3,
        },
        "mtf_analysis": {
            "enabled": True,
            "higher_timeframes": ["60", "240"],
            "trend_indicators": ["ema", "ehlers_supertrend"],
            "trend_period": 50,
            "mtf_request_delay_seconds": 0.5,
        },
        "ml_enhancement": {"enabled": False},
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
        },
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
            }
        },
        "execution": {
            "use_pybit": False,
            "testnet": False,
            "account_type": "UNIFIED",
            "category": "linear",
            "position_mode": "ONE_WAY",
            "tpsl_mode": "Partial",
            "buy_leverage": "3",
            "sell_leverage": "3",
            "tp_trigger_by": "LastPrice",
            "sl_trigger_by": "LastPrice",
            "default_time_in_force": "GoodTillCancel",
            "reduce_only_default": False,
            "post_only_default": False,
            "position_idx_overrides": {"ONE_WAY": 0, "HEDGE_BUY": 1, "HEDGE_SELL": 2},
            "tp_scheme": {
                "mode": "atr_multiples",
                "targets": [
                    {
                        "name": "TP1",
                        "atr_multiple": 1.0,
                        "size_pct": 0.40,
                        "order_type": "Limit",
                        "tif": "PostOnly",
                        "post_only": True,
                    },
                    {
                        "name": "TP2",
                        "atr_multiple": 1.5,
                        "size_pct": 0.40,
                        "order_type": "Limit",
                        "tif": "IOC",
                        "post_only": False,
                    },
                    {
                        "name": "TP3",
                        "atr_multiple": 2.0,
                        "size_pct": 0.20,
                        "order_type": "Limit",
                        "tif": "GoodTillCancel",
                        "post_only": False,
                    },
                ],
            },
            "sl_scheme": {
                "type": "atr_multiple",
                "atr_multiple": 1.5,
                "percent": 1.0,
                "use_conditional_stop": True,
                "stop_order_type": "Market",
            },
            "breakeven_after_tp1": {
                "enabled": True,
                "offset_type": "atr",
                "offset_value": 0.10,
                "lock_in_min_percent": 0,
                "sl_trigger_by": "LastPrice",
            },
            "live_sync": {
                "enabled": True,
                "poll_ms": 2500,
                "max_exec_fetch": 200,
                "only_track_linked": True,
                "heartbeat": {"enabled": True, "interval_ms": 5000},
            },
        },
    }
    if not Path(filepath).exists():
        try:
            with Path(filepath).open("w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)
            logger.warning(
                f"{NEON_YELLOW}Created default config at {filepath}{RESET}"
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
        console_handler.setFormatter(
            SensitiveFormatter(
                f"{NEON_BLUE}%(asctime)s - %(levelname)s - %(message)s{RESET}"
            )
        )
        logger.addHandler(console_handler)
        log_file = Path(LOG_DIRECTORY) / f"{log_name}.log"
        file_handler = RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5
        )
        file_handler.setFormatter(
            SensitiveFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
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
            self.logger.error(f"{NEON_RED}PyBit not installed.{RESET}")
            return
        if not API_KEY or not API_SECRET:
            self.enabled = False
            self.session = None
            self.logger.error(f"{NEON_RED}API keys not found for PyBit.{RESET}")
            return
        try:
            self.session = PybitHTTP(
                api_key=API_KEY, api_secret=API_SECRET, testnet=self.testnet, timeout=REQUEST_TIMEOUT
            )
            self.logger.info(
                f"{NEON_GREEN}PyBit client initialized. Testnet={self.testnet}{RESET}"
            )
        except Exception as e:
            self.enabled = False
            self.session = None
            self.logger.error(f"{NEON_RED}Failed to init PyBit client: {e}{RESET}")

    def _pos_idx(self, side: Literal["BUY", "SELL"]) -> int:
        pmode = self.cfg["execution"].get("position_mode", "ONE_WAY").upper()
        overrides = self.cfg["execution"].get("position_idx_overrides", {})
        if pmode == "ONE_WAY":
            return int(overrides.get("ONE_WAY", 0))
        return int(
            overrides.get("HEDGE_BUY" if side == "BUY" else "HEDGE_SELL", 1 if side == "BUY" else 2)
        )

    def _side_to_bybit(self, side: Literal["BUY", "SELL"]) -> str:
        return "Buy" if side == "BUY" else "Sell"

    def _q(self, x: Any) -> str:
        return str(x)

    def _ok(self, resp: dict | None) -> bool:
        return bool(resp and resp.get("retCode") == 0)

    def _log_api(self, action: str, resp: dict | None):
        if not resp:
            self.logger.error(f"{NEON_RED}{action}: No response.{RESET}")
            return
        if not self._ok(resp):
            self.logger.error(
                f"{NEON_RED}{action}: Error {resp.get('retCode')} - {resp.get('retMsg')}{RESET}"
            )

    def set_leverage(self, symbol: str, buy: str, sell: str) -> bool:
        if not self.enabled:
            return False
        try:
            resp = self.session.set_leverage(
                category=self.category,
                symbol=symbol,
                buyLeverage=self._q(buy),
                sellLeverage=self._q(sell),
            )
            self._log_api("set_leverage", resp)
            return self._ok(resp)
        except Exception as e:
            self.logger.error(f"{NEON_RED}set_leverage exception: {e}{RESET}")
            return False

    def get_positions(self, symbol: str | None = None) -> dict | None:
        if not self.enabled:
            return None
        try:
            params = {"category": self.category}
            if symbol:
                params["symbol"] = symbol
            return self.session.get_positions(**params)
        except Exception as e:
            self.logger.error(f"{NEON_RED}get_positions exception: {e}{RESET}")
            return None

    def get_wallet_balance(self, coin: str = "USDT") -> dict | None:
        if not self.enabled:
            return None
        try:
            return self.session.get_wallet_balance(
                accountType=self.cfg["execution"].get("account_type", "UNIFIED"),
                coin=coin,
            )
        except Exception as e:
            self.logger.error(f"{NEON_RED}get_wallet_balance exception: {e}{RESET}")
            return None

    def place_order(self, **kwargs) -> dict | None:
        if not self.enabled:
            return None
        try:
            resp = self.session.place_order(**kwargs)
            self._log_api("place_order", resp)
            return resp
        except Exception as e:
            self.logger.error(f"{NEON_RED}place_order exception: {e}{RESET}")
            return None

    def batch_place_orders(self, requests: list[dict]) -> dict | None:
        if not self.enabled:
            return None
        try:
            resp = self.session.batch_place_order(
                category=self.category, request=requests
            )
            self._log_api("batch_place_order", resp)
            return resp
        except Exception as e:
            self.logger.error(f"{NEON_RED}batch_place_orders exception: {e}{RESET}")
            return None

    def cancel_by_link_id(self, symbol: str, order_link_id: str) -> dict | None:
        if not self.enabled:
            return None
        try:
            resp = self.session.cancel_order(
                category=self.category, symbol=symbol, orderLinkId=order_link_id
            )
            self._log_api("cancel_by_link_id", resp)
            return resp
        except Exception as e:
            self.logger.error(f"{NEON_RED}cancel_by_link_id exception: {e}{RESET}")
            return None

    def get_executions(self, symbol: str, start_time_ms: int, limit: int) -> dict | None:
        if not self.enabled:
            return None
        try:
            return self.session.get_executions(
                category=self.category, symbol=symbol, startTime=start_time_ms, limit=limit
            )
        except Exception as e:
            self.logger.error(f"{NEON_RED}get_executions exception: {e}{RESET}")
            return None


def fetch_current_price(symbol: str, pybit_client: "PybitTradingClient", logger: logging.Logger) -> Decimal | None:
    """Fetch the current market price for a symbol using PybitTradingClient."""
    response = pybit_client.session.get_tickers(
        category="linear", symbol=symbol
    )
    if response and response.get("retCode") == 0 and response.get("result", {}).get("list"):
        return Decimal(response["result"]["list"][0]["lastPrice"])
    logger.warning(f"{NEON_YELLOW}Could not fetch current price for {symbol}.{RESET}")
    return None


def fetch_instrument_info(symbol: str, pybit_client: "PybitTradingClient", logger: logging.Logger) -> dict | None:
    """Fetch instrument info for a symbol using PybitTradingClient."""
    response = pybit_client.session.get_instruments_info(
        category="linear", symbol=symbol
    )
    if response and response.get("retCode") == 0 and response.get("result", {}).get("list"):
        return response["result"]["list"][0]
    logger.warning(f"{NEON_YELLOW}Could not fetch instrument info for {symbol}.{RESET}")
    return None


def fetch_klines(
    symbol: str,
    interval: str,
    limit: int,
    pybit_client: "PybitTradingClient",
    logger: logging.Logger,
) -> pd.DataFrame | None:
    """Fetch kline data for a symbol and interval."""
    params = {"category": "linear", "symbol": symbol, "interval": interval, "limit": limit}
    response = pybit_client.session.get_kline(**params)
    if response and response.get("result", {}).get("list"):
        df = pd.DataFrame(
            response["result"]["list"],
            columns=[
                "start_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "turnover",
            ],
        )
        df["start_time"] = pd.to_datetime(
            df["start_time"].astype(int), unit="ms", utc=True
        ).dt.tz_convert(TIMEZONE)
        for col in ["open", "high", "low", "close", "volume", "turnover"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df.set_index("start_time", inplace=True)
        df.sort_index(inplace=True)
        if df.empty:
            return None
        return df
    logger.warning(
        f"{NEON_YELLOW}Could not fetch klines for {symbol} {interval}.{RESET}"
    )
    return None


def fetch_orderbook(
    symbol: str, limit: int, pybit_client: "PybitTradingClient", logger: logging.Logger
) -> dict | None:
    """Fetch orderbook data for a symbol."""
    response = pybit_client.session.get_orderbook(
        category="linear", symbol=symbol, limit=limit
    )
    if response and response.get("result"):
        return response["result"]
    logger.warning(f"{NEON_YELLOW}Could not fetch orderbook for {symbol}.{RESET}")
    return None


# --- Position Management ---
class PositionManager:
    """Manages open positions, stop-loss, and take-profit levels."""

    def __init__(
        self,
        config: dict[str, Any],
        logger: logging.Logger,
        symbol: str,
        pybit_client: "PybitTradingClient | None" = None,
    ):
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.open_positions: list[dict] = []
        self.trade_management_enabled = config["trade_management"]["enabled"]
        self.max_open_positions = config["trade_management"]["max_open_positions"]

        # Initialize with config values, will be updated from exchange
        self.order_precision = config["trade_management"]["order_precision"]
        self.price_precision = config["trade_management"]["price_precision"]
        self.qty_step = None

        self.pybit = pybit_client
        self.live = bool(config.get("execution", {}).get("use_pybit", False))
        self._update_precision_from_exchange()

    def _update_precision_from_exchange(self):
        """Fetch and set precision settings from the exchange."""
        self.logger.info(f"Fetching precision for {self.symbol}...")
        info = fetch_instrument_info(self.symbol, self.pybit, self.logger)
        if info:
            if "lotSizeFilter" in info:
                lot_size_filter = info["lotSizeFilter"]
                self.qty_step = Decimal(str(lot_size_filter.get("qtyStep")))
                if not self.qty_step.is_zero():
                    self.order_precision = abs(self.qty_step.as_tuple().exponent)
                self.logger.info(f"Updated qty_step: {self.qty_step}, order_precision: {self.order_precision}")
            else:
                self.logger.warning(f"Could not find lotSizeFilter for {self.symbol}.")

            if "priceFilter" in info:
                price_filter = info["priceFilter"]
                tick_size = Decimal(str(price_filter.get("tickSize")))
                if not tick_size.is_zero():
                    self.price_precision = abs(tick_size.as_tuple().exponent)
                self.logger.info(f"Updated price_precision: {self.price_precision}")
            else:
                self.logger.warning(f"Could not find priceFilter for {self.symbol}.")
        else:
            self.logger.warning(f"Could not fetch precision for {self.symbol}. Using config values.")

    def _get_current_balance(self) -> Decimal:
        """Fetch current account balance from exchange if live, else use config."""
        if self.live and self.pybit and self.pybit.enabled:
            resp = self.pybit.get_wallet_balance(coin="USDT")
            if resp and self.pybit._ok(resp) and resp.get("result", {}).get("list"):
                for coin_balance in resp["result"]["list"][0]["coin"]:
                    if coin_balance["coin"] == "USDT":
                        return Decimal(coin_balance["walletBalance"])
        return Decimal(str(self.config["trade_management"]["account_balance"]))

    def _calculate_order_size(
        self, current_price: Decimal, atr_value: Decimal
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
            str(self.config["trade_management"]["stop_loss_atr_multiple"])
        )
        risk_amount = account_balance * risk_per_trade_percent
        stop_loss_distance = atr_value * stop_loss_atr_multiple
        if stop_loss_distance <= 0:
            self.logger.warning(f"{NEON_YELLOW}Stop loss distance is zero or negative. Cannot calculate order size.{RESET}")
            return Decimal("0")
        order_qty = (risk_amount / stop_loss_distance) / current_price

        if self.qty_step and self.qty_step > Decimal(0):
            return round_qty(order_qty, self.qty_step)

        # Fallback to old logic if qty_step is not available
        self.logger.warning(f"{NEON_YELLOW}qty_step not available. Using legacy precision rounding.{RESET}")
        return order_qty.quantize(
            Decimal("1e-" + str(self.order_precision)), rounding=ROUND_DOWN
        )

    def open_position(
        self, signal: Literal["BUY", "SELL"], current_price: Decimal, atr_value: Decimal
    ) -> dict | None:
        """Open a new position, placing live orders if enabled."""
        if self.live and self.pybit and self.pybit.enabled:
            positions_resp = self.pybit.get_positions(self.symbol)
            if positions_resp and self.pybit._ok(positions_resp):
                pos_list = positions_resp.get("result", {}).get("list", [])
                if any(p.get("size") and Decimal(p.get("size")) > 0 for p in pos_list):
                    self.logger.warning(f"{NEON_YELLOW}Exchange position exists, aborting new position.{RESET}")
                    return None

        if not self.trade_management_enabled or len(self.open_positions) >= self.max_open_positions:
            self.logger.info(
                f"{NEON_YELLOW}Cannot open new position (max reached or disabled).{RESET}"
            )
            return None
        order_qty = self._calculate_order_size(current_price, atr_value)
        if order_qty <= 0:
            self.logger.warning(
                f"{NEON_YELLOW}Order quantity is zero. Cannot open position.{RESET}"
            )
            return None

        stop_loss = compute_stop_loss_price(signal, current_price, atr_value, self.config)
        take_profit = (
            current_price
            + (
                atr_value
                * Decimal(str(self.config["trade_management"]["take_profit_atr_multiple"]))
            )
            if signal == "BUY"
            else current_price
            - (
                atr_value
                * Decimal(str(self.config["trade_management"]["take_profit_atr_multiple"]))
            )
        )

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
        }

        if self.live and self.pybit and self.pybit.enabled:
            entry_link = f"{position['link_prefix']}_entry"
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
                if self.config["execution"]["tpsl_mode"] == "Partial":
                    targets = build_partial_tp_targets(
                        signal, position["entry_price"], atr_value, order_qty, self.config, self.qty_step
                    )
                    batch = []
                    for t in targets:
                        payload = {
                            "symbol": self.symbol,
                            "side": self.pybit._side_to_bybit(
                                "SELL" if signal == "BUY" else "BUY"
                            ),
                            "orderType": t["order_type"],
                            "qty": self.pybit._q(t["qty"]),
                            "timeInForce": t["tif"],
                            "reduceOnly": True,
                            "positionIdx": self.pybit._pos_idx(signal),
                            "orderLinkId": f"{position['link_prefix']}_{t['link_id_suffix']}",
                            "category": self.pybit.category,
                        }
                        if t["order_type"] == "Limit":
                            payload["price"] = self.pybit._q(t["price"])
                        if t.get("post_only"):
                            payload["isPostOnly"] = True
                        batch.append(payload)
                    if batch:
                        for p in batch:
                            resp_tp = self.pybit.place_order(**p)
                            if resp_tp and resp_tp.get("retCode") == 0:
                                self.logger.info(f"{NEON_GREEN}Placed individual TP target: {p.get('orderLinkId')}{RESET}")
                            else:
                                self.logger.error(f"{NEON_RED}Failed to place individual TP target: {p.get('orderLinkId')}. Error: {resp_tp.get('retMsg') if resp_tp else 'No response'}{RESET}")
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
                        triggerDirection=(2 if signal == "BUY" else 1),
                        orderFilter="Stop",
                    )
                    if self.pybit._ok(sresp):
                        self.logger.info(f"{NEON_GREEN}Conditional stop placed at {stop_loss}.{RESET}")

        self.open_positions.append(position)
        self.logger.info(
            f"{NEON_GREEN}Opened {signal} position (simulated): {position}{RESET}"
        )
        return position

    def manage_positions(self, current_price: Decimal, performance_tracker: Any):
        """Check and manage simulated positions (for backtesting/simulation mode)."""
        if self.live or not self.trade_management_enabled or not self.open_positions:
            return
        positions_to_close = []
        for i, pos in enumerate(self.open_positions):
            if pos["status"] == "OPEN":
                closed_by = ""
                if pos["side"] == "BUY" and current_price <= pos["stop_loss"]:
                    closed_by = "STOP_LOSS"
                elif pos["side"] == "BUY" and current_price >= pos["take_profit"]:
                    closed_by = "TAKE_PROFIT"
                elif pos["side"] == "SELL" and current_price >= pos["stop_loss"]:
                    closed_by = "STOP_LOSS"
                elif pos["side"] == "SELL" and current_price <= pos["take_profit"]:
                    closed_by = "TAKE_PROFIT"
                if closed_by:
                    pos.update(
                        {
                            "status": "CLOSED",
                            "exit_time": datetime.now(TIMEZONE),
                            "exit_price": current_price,
                            "closed_by": closed_by,
                        }
                    )
                    pnl = (
                        (current_price - pos["entry_price"]) * pos["qty"]
                        if pos["side"] == "BUY"
                        else (pos["entry_price"] - current_price) * pos["qty"]
                    )
                    performance_tracker.record_trade(pos, pnl)
                    self.logger.info(
                        f"{NEON_PURPLE}Closed {pos['side']} by {closed_by}. PnL: {pnl:.2f}{RESET}"
                    )
                    positions_to_close.append(i)
        self.open_positions = [
            p for i, p in enumerate(self.open_positions) if i not in positions_to_close
        ]

    def get_open_positions(self) -> list[dict]:
        return [pos for pos in self.open_positions if pos["status"] == "OPEN"]


# --- Performance Tracking & Sync ---
class PerformanceTracker:
    """Tracks and reports trading performance."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.trades: list[dict] = []
        self.total_pnl = Decimal("0")
        self.wins = 0
        self.losses = 0

    def record_trade(self, position: dict, pnl: Decimal):
        self.trades.append({**position, "pnl": pnl})
        self.total_pnl += pnl
        if pnl > 0:
            self.wins += 1
        else:
            self.losses += 1
        self.logger.info(
            f"{NEON_CYAN}Trade recorded. PnL: {pnl:.2f}. Total PnL: {self.total_pnl:.2f}{RESET}"
        )

    def get_summary(self) -> dict:
        total = len(self.trades)
        win_rate = (self.wins / total) * 100 if total > 0 else 0
        return {
            "total_trades": total,
            "total_pnl": self.total_pnl,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": f"{win_rate:.2f}%",
        }


class ExchangeExecutionSync:
    """Polls exchange for trade fills, records PnL, and triggers breakeven stops."""

    def __init__(
        self,
        symbol: str,
        pybit: PybitTradingClient,
        logger: logging.Logger,
        cfg: dict,
        pm: PositionManager,
        pt: PerformanceTracker,
    ):
        self.symbol = symbol
        self.pybit = pybit
        self.logger = logger
        self.cfg = cfg
        self.pm = pm
        self.pt = pt
        self.last_exec_time_ms = int(time.time() * 1000) - 5 * 60 * 1000

    def _is_ours(self, link_id: str | None) -> bool:
        if not link_id:
            return False
        if not self.cfg["execution"]["live_sync"]["only_track_linked"]:
            return True
        return link_id.startswith("wgx_")

    def _compute_be_price(
        self, side: str, entry_price: Decimal, atr_value: Decimal
    ) -> Decimal:
        be_cfg = self.cfg["execution"]["breakeven_after_tp1"]
        off_type = str(be_cfg.get("offset_type", "atr")).lower()
        off_val = Decimal(str(be_cfg.get("offset_value", 0)))
        if off_type == "atr":
            adj = atr_value * off_val
        elif off_type == "percent":
            adj = entry_price * (off_val / Decimal("100"))
        else:
            adj = off_val  # Ticks or absolute
        lock_adj = entry_price * (
            Decimal(str(be_cfg.get("lock_in_min_percent", 0))) / Decimal("100")
        )
        be = entry_price + max(adj, lock_adj) if side == "BUY" else entry_price - max(adj, lock_adj)
        return round_price(be, self.pm.price_precision)

    def _move_stop_to_breakeven(self, open_pos: dict, atr_value: Decimal):
        if not self.cfg["execution"]["breakeven_after_tp1"].get("enabled", False):
            return
        try:
            entry = Decimal(str(open_pos["entry_price"]))
            side = open_pos["side"]
            new_sl = self._compute_be_price(side, entry, atr_value)
            link_prefix = open_pos.get("link_prefix")
            old_sl_link = f"{link_prefix}_sl" if link_prefix else None
            if old_sl_link:
                self.pybit.cancel_by_link_id(self.symbol, old_sl_link)
            new_sl_link = (
                f"{link_prefix}_sl_be" if link_prefix else f"wgx_{int(time.time()*1000)}_sl_be"
            )
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
                self.logger.info(f"{NEON_GREEN}Moved SL to breakeven at {new_sl}.{RESET}")
        except Exception as e:
            self.logger.error(f"{NEON_RED}Breakeven move exception: {e}{RESET}")

    def poll(self):
        if not (self.pybit and self.pybit.enabled):
            return
        try:
            resp = self.pybit.get_executions(
                self.symbol,
                self.last_exec_time_ms,
                self.cfg["execution"]["live_sync"]["max_exec_fetch"],
            )
            if not self.pybit._ok(resp):
                return
            rows = resp.get("result", {}).get("list", [])
            rows.sort(key=lambda r: int(r.get("execTime", 0)))
            for r in rows:
                link = r.get("orderLinkId")
                if not self._is_ours(link):
                    continue
                ts_ms = int(r.get("execTime", 0))
                self.last_exec_time_ms = max(self.last_exec_time_ms, ts_ms + 1)
                tag = (
                    "ENTRY"
                    if link.endswith("_entry")
                    else ("SL" if "_sl" in link else ("TP" if "_tp" in link else "UNKNOWN"))
                )
                open_pos = next(
                    (p for p in self.pm.open_positions if p.get("status") == "OPEN"), None
                )
                if tag in ("TP", "SL") and open_pos:
                    is_reduce = (
                        (open_pos["side"] == "BUY" and r.get("side") == "Sell")
                        or (open_pos["side"] == "SELL" and r.get("side") == "Buy")
                    )
                    if is_reduce:
                        exec_qty = Decimal(str(r.get("execQty", "0")))
                        exec_price = Decimal(str(r.get("execPrice", "0")))
                        pnl = (
                            (exec_price - open_pos["entry_price"]) * exec_qty
                            if open_pos["side"] == "BUY"
                            else (open_pos["entry_price"] - exec_price) * exec_qty
                        )
                        self.pt.record_trade(
                            {
                                **open_pos,
                                "exit_time": datetime.fromtimestamp(ts_ms / 1000, tz=TIMEZONE),
                                "exit_price": exec_price,
                                "qty": exec_qty,
                                "closed_by": tag,
                            },
                            pnl,
                        )
                        remaining = Decimal(str(open_pos["qty"])) - exec_qty
                        open_pos["qty"] = max(remaining, Decimal("0"))
                        if remaining <= 0:
                            open_pos.update(
                                {
                                    "status": "CLOSED",
                                    "exit_time": datetime.fromtimestamp(
                                        ts_ms / 1000, tz=TIMEZONE
                                    ),
                                    "exit_price": exec_price,
                                    "closed_by": tag,
                                }
                            )
                            self.logger.info(f"{NEON_PURPLE}Position fully closed by {tag}.{RESET}")
                    if tag == "TP" and link.endswith("_tp1"):
                        atr_val = Decimal(str(self.cfg.get("_last_atr", "0.1")))
                        self._move_stop_to_breakeven(open_pos, atr_val)
            self.pm.open_positions = [
                p for p in self.pm.open_positions if p.get("status") == "OPEN"
            ]
        except Exception as e:
            self.logger.error(f"{NEON_RED}Execution sync error: {e}{RESET}")


class PositionHeartbeat:
    """Periodically reconciles local position state with the exchange."""

    def __init__(
        self,
        symbol: str,
        pybit: PybitTradingClient,
        logger: logging.Logger,
        cfg: dict,
        pm: PositionManager,
    ):
        self.symbol = symbol
        self.pybit = pybit
        self.logger = logger
        self.cfg = cfg
        self.pm = pm
        self._last_ms = 0

    def tick(self):
        hb_cfg = self.cfg["execution"]["live_sync"]["heartbeat"]
        if not (hb_cfg.get("enabled", True) and self.pybit and self.pybit.enabled):
            return
        now_ms = int(time.time() * 1000)
        if now_ms - self._last_ms < int(hb_cfg.get("interval_ms", 5000)):
            return
        self._last_ms = now_ms
        try:
            resp = self.pybit.get_positions(self.symbol)
            if not self.pybit._ok(resp):
                return
            lst = (resp.get("result", {}) or {}).get("list", [])
            net_qty = sum(
                Decimal(p.get("size", "0")) * (1 if p.get("side") == "Buy" else -1)
                for p in lst
            )
            local = next(
                (p for p in self.pm.open_positions if p.get("status") == "OPEN"), None
            )
            if net_qty == 0 and local:
                local.update({"status": "CLOSED", "closed_by": "HEARTBEAT_SYNC"})
                self.logger.info(
                    f"{NEON_PURPLE}Heartbeat: Closed local position (exchange flat).{RESET}"
                )
                self.pm.open_positions = [
                    p for p in self.pm.open_positions if p.get("status") == "OPEN"
                ]
            elif net_qty != 0 and not local:
                avg_price = Decimal(lst[0].get("avgPrice", "0")) if lst else Decimal("0")
                side = "BUY" if net_qty > 0 else "SELL"
                synt = {
                    "entry_time": datetime.now(TIMEZONE),
                    "symbol": self.symbol,
                    "side": side,
                    "entry_price": round_price(avg_price, self.pm.price_precision),
                    "qty": round_qty(abs(net_qty), self.pm.order_precision),
                    "status": "OPEN",
                    "link_prefix": f"hb_{int(time.time()*1000)}",
                }
                self.pm.open_positions.append(synt)
                self.logger.info(
                    f"{NEON_YELLOW}Heartbeat: Created synthetic local position.{RESET}"
                )
        except Exception as e:
            self.logger.error(f"{NEON_RED}Heartbeat error: {e}{RESET}")


# --- Alert System ---
class AlertSystem:
    """Handles sending alerts for critical events."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def send_alert(self, message: str, level: Literal["INFO", "WARNING", "ERROR"]):
        log_map = {"INFO": self.logger.info, "WARNING": self.logger.warning, "ERROR": self.logger.error}
        color_map = {"INFO": NEON_BLUE, "WARNING": NEON_YELLOW, "ERROR": NEON_RED}
        log_map[level](f"{color_map[level]}ALERT: {message}{RESET}")


# --- Trading Analysis ---
class TradingAnalyzer:
    """Analyzes trading data and generates signals."""

    def __init__(
        self, df: pd.DataFrame, config: dict[str, Any], logger: logging.Logger, symbol: str
    ):
        self.df = df.copy()
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.indicator_values: dict[str, Any] = {}
        self.fib_levels: dict[str, Decimal] = {}
        self.weights = config["weight_sets"]["default_scalping"]
        self.indicator_settings = config["indicator_settings"]
        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}TradingAnalyzer initialized with empty DataFrame.{RESET}"
            )
            return
        self._calculate_all_indicators()
        if self.config["indicators"].get("fibonacci_levels", False):
            self.calculate_fibonacci_levels()

    def _safe_calculate(
        self, func: callable, name: str, min_data_points: int = 0, *args, **kwargs
    ) -> Any | None:
        """Safely calculate indicators and log errors."""
        if len(self.df) < min_data_points:
            return None
        try:
            result = func(*args, **kwargs)
            is_empty = (
                result is None
                or (isinstance(result, pd.Series) and result.empty)
                or (
                    isinstance(result, tuple)
                    and all(
                        r is None or (isinstance(r, pd.Series) and r.empty) for r in result
                    )
                )
            )
            if is_empty:
                self.logger.warning(
                    f"{NEON_YELLOW}[{self.symbol}] Indicator '{name}' returned empty.{RESET}"
                )
            return result if not is_empty else None
        except Exception as e:
            self.logger.error(
                f"{NEON_RED}[{self.symbol}] Error calculating '{name}': {e}{RESET}"
            )
            return None

    def _calculate_all_indicators(self) -> None:
        """Calculate all enabled technical indicators."""
        self.logger.debug(f"[{self.symbol}] Calculating all technical indicators...")
        cfg = self.config
        isd = self.indicator_settings

        # SMA
        if cfg["indicators"].get("sma_10", False):
            self.df["SMA_10"] = self._safe_calculate(
                lambda: self.df["close"].rolling(window=isd["sma_short_period"]).mean(),
                "SMA_10",
                min_data_points=isd["sma_short_period"],
            )
            if self.df["SMA_10"] is not None and not self.df["SMA_10"].empty:
                self.indicator_values["SMA_10"] = self.df["SMA_10"].iloc[-1]
        if cfg["indicators"].get("sma_trend_filter", False):
            self.df["SMA_Long"] = self._safe_calculate(
                lambda: self.df["close"].rolling(window=isd["sma_long_period"]).mean(),
                "SMA_Long",
                min_data_points=isd["sma_long_period"],
            )
            if self.df["SMA_Long"] is not None and not self.df["SMA_Long"].empty:
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
            if self.df["EMA_Short"] is not None and not self.df["EMA_Short"].empty:
                self.indicator_values["EMA_Short"] = self.df["EMA_Short"].iloc[-1]
            if self.df["EMA_Long"] is not None and not self.df["EMA_Long"].empty:
                self.indicator_values["EMA_Long"] = self.df["EMA_Long"].iloc[-1]

        # ATR
        self.df["TR"] = self._safe_calculate(
            self.calculate_true_range, "TR", min_data_points=MIN_DATA_POINTS_TR
        )
        self.df["ATR"] = self._safe_calculate(
            lambda: self.df["TR"].ewm(span=isd["atr_period"], adjust=False).mean(),
            "ATR",
            min_data_points=isd["atr_period"],
        )
        if self.df["ATR"] is not None and not self.df["ATR"].empty:
            self.indicator_values["ATR"] = self.df["ATR"].iloc[-1]

        # RSI
        if cfg["indicators"].get("rsi", False):
            self.df["RSI"] = self._safe_calculate(
                self.calculate_rsi,
                "RSI",
                min_data_points=isd["rsi_period"] + 1,
                period=isd["rsi_period"],
            )
            if self.df["RSI"] is not None and not self.df["RSI"].empty:
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
            if stoch_rsi_k is not None and not stoch_rsi_k.empty:
                self.df["StochRSI_K"] = stoch_rsi_k
                self.indicator_values["StochRSI_K"] = stoch_rsi_k.iloc[-1]
            if stoch_rsi_d is not None and not stoch_rsi_d.empty:
                self.df["StochRSI_D"] = stoch_rsi_d
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
            if bb_upper is not None and not bb_upper.empty:
                self.df["BB_Upper"] = bb_upper
                self.indicator_values["BB_Upper"] = bb_upper.iloc[-1]
            if bb_middle is not None and not bb_middle.empty:
                self.df["BB_Middle"] = bb_middle
                self.indicator_values["BB_Middle"] = bb_middle.iloc[-1]
            if bb_lower is not None and not bb_lower.empty:
                self.df["BB_Lower"] = bb_lower
                self.indicator_values["BB_Lower"] = bb_lower.iloc[-1]

        # CCI
        if cfg["indicators"].get("cci", False):
            self.df["CCI"] = self._safe_calculate(
                self.calculate_cci,
                "CCI",
                min_data_points=isd["cci_period"],
                period=isd["cci_period"],
            )
            if self.df["CCI"] is not None and not self.df["CCI"].empty:
                self.indicator_values["CCI"] = self.df["CCI"].iloc[-1]

        # Williams %R
        if cfg["indicators"].get("wr", False):
            self.df["WR"] = self._safe_calculate(
                self.calculate_williams_r,
                "WR",
                min_data_points=isd["williams_r_period"],
                period=isd["williams_r_period"],
            )
            if self.df["WR"] is not None and not self.df["WR"].empty:
                self.indicator_values["WR"] = self.df["WR"].iloc[-1]

        # MFI
        if cfg["indicators"].get("mfi", False):
            self.df["MFI"] = self._safe_calculate(
                self.calculate_mfi,
                "MFI",
                min_data_points=isd["mfi_period"] + 1,
                period=isd["mfi_period"],
            )
            if self.df["MFI"] is not None and not self.df["MFI"].empty:
                self.indicator_values["MFI"] = self.df["MFI"].iloc[-1]

        # OBV
        if cfg["indicators"].get("obv", False):
            obv_val, obv_ema = self._safe_calculate(
                self.calculate_obv,
                "OBV",
                min_data_points=isd["obv_ema_period"],
                ema_period=isd["obv_ema_period"],
            )
            if obv_val is not None and not obv_val.empty:
                self.df["OBV"] = obv_val
                self.indicator_values["OBV"] = obv_val.iloc[-1]
            if obv_ema is not None and not obv_ema.empty:
                self.df["OBV_EMA"] = obv_ema
                self.indicator_values["OBV_EMA"] = obv_ema.iloc[-1]

        # CMF
        if cfg["indicators"].get("cmf", False):
            cmf_val = self._safe_calculate(
                self.calculate_cmf,
                "CMF",
                min_data_points=isd["cmf_period"],
                period=isd["cmf_period"],
            )
            if cmf_val is not None and not cmf_val.empty:
                self.df["CMF"] = cmf_val
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

        # PSAR
        if cfg["indicators"].get("psar", False):
            psar_val, psar_dir = self._safe_calculate(
                self.calculate_psar,
                "PSAR",
                min_data_points=MIN_DATA_POINTS_PSAR,
                acceleration=isd["psar_acceleration"],
                max_acceleration=isd["psar_max_acceleration"],
            )
            if psar_val is not None and not psar_val.empty:
                self.df["PSAR_Val"] = psar_val
                self.indicator_values["PSAR_Val"] = psar_val.iloc[-1]
            if psar_dir is not None and not psar_dir.empty:
                self.df["PSAR_Dir"] = psar_dir
                self.indicator_values["PSAR_Dir"] = psar_dir.iloc[-1]

        # VWAP (requires volume and turnover, which are in df)
        if cfg["indicators"].get("vwap", False):
            self.df["VWAP"] = self._safe_calculate(
                self.calculate_vwap, "VWAP", min_data_points=1
            )
            if self.df["VWAP"] is not None and not self.df["VWAP"].empty:
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
            if macd_line is not None and not macd_line.empty:
                self.df["MACD_Line"] = macd_line
                self.indicator_values["MACD_Line"] = macd_line.iloc[-1]
            if signal_line is not None and not signal_line.empty:
                self.df["MACD_Signal"] = signal_line
                self.indicator_values["MACD_Signal"] = signal_line.iloc[-1]
            if histogram is not None and not histogram.empty:
                self.df["MACD_Hist"] = histogram
                self.indicator_values["MACD_Hist"] = histogram.iloc[-1]

        # ADX
        if cfg["indicators"].get("adx", False):
            adx_val, plus_di, minus_di = self._safe_calculate(
                self.calculate_adx,
                "ADX",
                min_data_points=isd["adx_period"] * 2,
                period=isd["adx_period"],
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

        # --- New Indicators ---
        # Volatility Index
        if cfg["indicators"].get("volatility_index", False):
            self.df["Volatility_Index"] = self._safe_calculate(
                self.calculate_volatility_index,
                "Volatility_Index",
                min_data_points=isd["volatility_index_period"],
                period=isd["volatility_index_period"],
            )
            if self.df["Volatility_Index"] is not None and not self.df["Volatility_Index"].empty:
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
            if self.df["VWMA"] is not None and not self.df["VWMA"].empty:
                self.indicator_values["VWMA"] = self.df["VWMA"].iloc[-1]

        # Volume Delta
        if cfg["indicators"].get("volume_delta", False):
            self.df["Volume_Delta"] = self._safe_calculate(
                self.calculate_volume_delta,
                "Volume_Delta",
                min_data_points=isd["volume_delta_period"],
                period=isd["volume_delta_period"],
            )
            if self.df["Volume_Delta"] is not None and not self.df["Volume_Delta"].empty:
                self.indicator_values["Volume_Delta"] = self.df["Volume_Delta"].iloc[-1]

        self.df.dropna(subset=["close"], inplace=True)
        self.df.fillna(0, inplace=True)
        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}DataFrame empty after indicator calculations.{RESET}"
            )

    def calculate_true_range(self) -> pd.Series:
        """Calculate True Range (TR)."""
        if len(self.df) < MIN_DATA_POINTS_TR:
            return pd.Series(np.nan, index=self.df.index)
        high_low = self.df["high"] - self.df["low"]
        high_prev_close = (self.df["high"] - self.df["close"].shift()).abs()
        low_prev_close = (self.df["low"] - self.df["close"].shift()).abs()
        return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(
            axis=1
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
        self, period: int, multiplier: float
    ) -> pd.DataFrame | None:
        """Calculate SuperTrend using Ehlers SuperSmoother for price and volatility."""
        if len(self.df) < period * 3:
            return None

        df_copy = self.df.copy()

        hl2 = (df_copy["high"] + df_copy["low"]) / 2
        smoothed_price = self.calculate_super_smoother(hl2, period)

        tr = self.calculate_true_range()
        smoothed_atr = self.calculate_super_smoother(tr, period)

        df_copy["smoothed_price"] = smoothed_price
        df_copy["smoothed_atr"] = smoothed_atr

        df_copy.dropna(subset=["smoothed_price", "smoothed_atr"], inplace=True)
        if df_copy.empty:
            return None

        upper_band = df_copy["smoothed_price"] + multiplier * df_copy["smoothed_atr"]
        lower_band = df_copy["smoothed_price"] - multiplier * df_copy["smoothed_atr"]

        direction = pd.Series(0, index=df_copy.index, dtype=int)
        supertrend = pd.Series(np.nan, index=df_copy.index)

        first_valid_idx_val = smoothed_price.first_valid_index()
        if first_valid_idx_val is None:
            return None
        first_valid_idx = df_copy.index.get_loc(first_valid_idx_val)
        if first_valid_idx >= len(df_copy):
            return None

        if df_copy["close"].iloc[first_valid_idx] > upper_band.iloc[first_valid_idx]:
            direction.iloc[first_valid_idx] = 1
            supertrend.iloc[first_valid_idx] = lower_band.iloc[first_valid_idx]
        elif (
            df_copy["close"].iloc[first_valid_idx] < lower_band.iloc[first_valid_idx]
        ):
            direction.iloc[first_valid_idx] = -1
            supertrend.iloc[first_valid_idx] = upper_band.iloc[first_valid_idx]
        else:
            direction.iloc[first_valid_idx] = 0
            supertrend.iloc[first_valid_idx] = lower_band.iloc[first_valid_idx]

        for i in range(first_valid_idx + 1, len(df_copy)):
            prev_direction = direction.iloc[i - 1]
            prev_supertrend = supertrend.iloc[i - 1]
            curr_close = df_copy["close"].iloc[i]

            if prev_direction == 1:
                if curr_close < prev_supertrend:
                    direction.iloc[i] = -1
                    supertrend.iloc[i] = upper_band.iloc[i]
                else:
                    direction.iloc[i] = 1
                    supertrend.iloc[i] = max(lower_band.iloc[i], prev_supertrend)
            elif prev_direction == -1:
                if curr_close > prev_supertrend:
                    direction.iloc[i] = 1
                    supertrend.iloc[i] = lower_band.iloc[i]
                else:
                    direction.iloc[i] = -1
                    supertrend.iloc[i] = min(upper_band.iloc[i], prev_supertrend)
            else:
                if curr_close > upper_band.iloc[i]:
                    direction.iloc[i] = 1
                    supertrend.iloc[i] = lower_band.iloc[i]
                elif curr_close < lower_band.iloc[i]:
                    direction.iloc[i] = -1
                    supertrend.iloc[i] = upper_band.iloc[i]
                else:
                    direction.iloc[i] = prev_direction
                    supertrend.iloc[i] = prev_supertrend

        result = pd.DataFrame({"supertrend": supertrend, "direction": direction})
        return result.reindex(self.df.index)

    def calculate_macd(
        self, fast_period: int, slow_period: int, signal_period: int
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

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_stoch_rsi(
        self, period: int, k_period: int, d_period: int
    ) -> tuple[pd.Series, pd.Series]:
        """Calculate Stochastic RSI."""
        if len(self.df) <= period:
            return pd.Series(np.nan, index=self.df.index), pd.Series(
                np.nan, index=self.df.index
            )
        rsi = self.calculate_rsi(period)

        lowest_rsi = rsi.rolling(window=period, min_periods=period).min()
        highest_rsi = rsi.rolling(window=period, min_periods=period).max()

        denominator = highest_rsi - lowest_rsi
        denominator[denominator == 0] = np.nan
        stoch_rsi_k_raw = ((rsi - lowest_rsi) / denominator) * 100
        stoch_rsi_k_raw = stoch_rsi_k_raw.fillna(0).clip(0, 100)

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

        tr = self.calculate_true_range()

        plus_dm = self.df["high"].diff()
        minus_dm = -self.df["low"].diff()

        plus_dm_final = pd.Series(0.0, index=self.df.index)
        minus_dm_final = pd.Series(0.0, index=self.df.index)

        for i in range(1, len(self.df)):
            if plus_dm.iloc[i] > minus_dm.iloc[i] and plus_dm.iloc[i] > 0:
                plus_dm_final.iloc[i] = plus_dm.iloc[i]
            if minus_dm.iloc[i] > plus_dm.iloc[i] and minus_dm.iloc[i] > 0:
                minus_dm_final.iloc[i] = minus_dm.iloc[i]

        atr = tr.ewm(span=period, adjust=False).mean()
        plus_di = (plus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100
        minus_di = (minus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100

        di_diff = abs(plus_di - minus_di)
        di_sum = plus_di + minus_di
        dx = (di_diff / di_sum.replace(0, np.nan)).fillna(0) * 100

        adx = dx.ewm(span=period, adjust=False).mean()

        return adx, plus_di, minus_di

    def calculate_bollinger_bands(
        self, period: int, std_dev: float
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
            lambda x: np.abs(x - x.mean()).mean(), raw=False
        )
        cci = (tp - sma_tp) / (0.015 * mad.replace(0, np.nan))
        return cci

    def calculate_williams_r(self, period: int) -> pd.Series:
        """Calculate Williams %R."""
        if len(self.df) < period:
            return pd.Series(np.nan, index=self.df.index)
        highest_high = self.df["high"].rolling(window=period, min_periods=period).max()
        lowest_low = self.df["low"].rolling(window=period, min_periods=period).min()
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

        price_diff = typical_price.diff()
        positive_flow = money_flow.where(price_diff > 0, 0)
        negative_flow = money_flow.where(price_diff < 0, 0)

        positive_mf_sum = positive_flow.rolling(window=period, min_periods=period).sum()
        negative_mf_sum = negative_flow.rolling(window=period, min_periods=period).sum()

        mf_ratio = positive_mf_sum / negative_mf_sum.replace(0, np.nan)
        mfi = 100 - (100 / (1 + mf_ratio))
        return mfi

    def calculate_obv(self, ema_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate On-Balance Volume (OBV) and its EMA."""
        if len(self.df) < MIN_DATA_POINTS_OBV:
            return pd.Series(np.nan), pd.Series(np.nan)

        obv_direction = np.sign(self.df["close"].diff().fillna(0))
        obv = (obv_direction * self.df["volume"]).cumsum()

        obv_ema = obv.ewm(span=ema_period, adjust=False).mean()

        return obv, obv_ema

    def calculate_cmf(self, period: int) -> pd.Series:
        """Calculate Chaikin Money Flow (CMF)."""
        if len(self.df) < period:
            return pd.Series(np.nan)

        high_low_range = self.df["high"] - self.df["low"]
        mfm = (
            (self.df["close"] - self.df["low"]) - (self.df["high"] - self.df["close"])
        ) / high_low_range.replace(0, np.nan)
        mfm = mfm.fillna(0)

        mfv = mfm * self.df["volume"]

        volume_sum = self.df["volume"].rolling(window=period).sum()
        cmf = mfv.rolling(window=period).sum() / volume_sum.replace(0, np.nan)
        cmf = cmf.fillna(0)

        return cmf

    def calculate_psar(
        self, acceleration: float, max_acceleration: float
    ) -> tuple[pd.Series, pd.Series]:
        """Calculate Parabolic SAR."""
        if len(self.df) < MIN_DATA_POINTS_PSAR:
            return pd.Series(np.nan, index=self.df.index), pd.Series(
                np.nan, index=self.df.index
            )

        psar = self.df["close"].copy()
        bull = pd.Series(True, index=self.df.index)
        af = acceleration
        ep = (
            self.df["low"].iloc[0]
            if self.df["close"].iloc[0] < self.df["close"].iloc[1]
            else self.df["high"].iloc[0]
        )

        for i in range(1, len(self.df)):
            prev_bull = bull.iloc[i - 1]
            prev_psar = psar.iloc[i - 1]

            if prev_bull:
                psar.iloc[i] = prev_psar + af * (ep - prev_psar)
            else:
                psar.iloc[i] = prev_psar - af * (prev_psar - ep)

            reverse = False
            if prev_bull and self.df["low"].iloc[i] < psar.iloc[i]:
                bull.iloc[i] = False
                reverse = True
            elif not prev_bull and self.df["high"].iloc[i] > psar.iloc[i]:
                bull.iloc[i] = True
                reverse = True
            else:
                bull.iloc[i] = prev_bull

            if reverse:
                af = acceleration
                ep = self.df["high"].iloc[i] if bull.iloc[i] else self.df["low"].iloc[i]
                if bull.iloc[i]:
                    psar.iloc[i] = min(self.df["low"].iloc[i], self.df["low"].iloc[i - 1])
                else:
                    psar.iloc[i] = max(self.df["high"].iloc[i], self.df["high"].iloc[i - 1])

            elif bull.iloc[i]:
                if self.df["high"].iloc[i] > ep:
                    ep = self.df["high"].iloc[i]
                    af = min(af + acceleration, max_acceleration)
                psar.iloc[i] = min(psar.iloc[i], self.df["low"].iloc[i], self.df["low"].iloc[i - 1])
            else:
                if self.df["low"].iloc[i] < ep:
                    ep = self.df["low"].iloc[i]
                    af = min(af + acceleration, max_acceleration)
                psar.iloc[i] = max(psar.iloc[i], self.df["high"].iloc[i], self.df["high"].iloc[i - 1])

        direction = pd.Series(0, index=self.df.index, dtype=int)
        direction[psar < self.df["close"]] = 1
        direction[psar > self.df["close"]] = -1

        return psar, direction

    def calculate_fibonacci_levels(self) -> None:
        """Calculate Fibonacci retracement levels based on a recent high-low swing."""
        window = self.config["indicator_settings"]["fibonacci_window"]
        if len(self.df) < window:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Not enough data for Fibonacci levels (need {window} bars).{RESET}"
            )
            return

        recent_high = self.df["high"].iloc[-window:].max()
        recent_low = self.df["low"].iloc[-window:].min()

        diff = recent_high - recent_low

        if diff <= 0:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Invalid high-low range for Fibonacci calculation. Diff: {diff}{RESET}"
            )
            return

        self.fib_levels = {
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
        self.logger.debug(f"[{self.symbol}] Calculated Fibonacci levels: {self.fib_levels}")

    def calculate_volatility_index(self, period: int) -> pd.Series:
        """Calculate a simple Volatility Index based on ATR normalized by price."""
        if len(self.df) < period or "ATR" not in self.df.columns:
            return pd.Series(np.nan, index=self.df.index)

        normalized_atr = self.df["ATR"] / self.df["close"]
        volatility_index = normalized_atr.rolling(window=period).mean()
        return volatility_index

    def calculate_vwma(self, period: int) -> pd.Series:
        """Calculate Volume Weighted Moving Average (VWMA)."""
        if len(self.df) < period or self.df["volume"].isnull().any():
            return pd.Series(np.nan, index=self.df.index)

        valid_volume = self.df["volume"].replace(0, np.nan)
        pv = self.df["close"] * valid_volume
        vwma = pv.rolling(window=period).sum() / valid_volume.rolling(
            window=period
        ).sum()
        return vwma

    def calculate_volume_delta(self, period: int) -> pd.Series:
        """Calculate Volume Delta, indicating buying vs selling pressure."""
        if len(self.df) < MIN_DATA_POINTS_VOLATILITY:
            return pd.Series(np.nan, index=self.df.index)

        buy_volume = self.df["volume"].where(self.df["close"] > self.df["open"], 0)
        sell_volume = self.df["volume"].where(self.df["close"] < self.df["open"], 0)

        buy_volume_sum = buy_volume.rolling(window=period, min_periods=1).sum()
        sell_volume_sum = sell_volume.rolling(window=period, min_periods=1).sum()

        total_volume_sum = buy_volume_sum + sell_volume_sum
        volume_delta = (buy_volume_sum - sell_volume_sum) / total_volume_sum.replace(
            0, np.nan
        )
        return volume_delta.fillna(0)

    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        """Safely retrieve an indicator value."""
        return self.indicator_values.get(key, default)

    def _check_orderbook(self, current_price: Decimal, orderbook_data: dict) -> float:
        """Analyze orderbook imbalance."""
        bids = orderbook_data.get("b", [])
        asks = orderbook_data.get("a", [])

        bid_volume = sum(Decimal(b[1]) for b in bids)
        ask_volume = sum(Decimal(a[1]) for a in asks)

        if bid_volume + ask_volume == 0:
            return 0.0

        imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
        self.logger.debug(
            f"[{self.symbol}] Orderbook Imbalance: {imbalance:.4f} (Bids: {bid_volume}, Asks: {ask_volume})"
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
        elif indicator_type == "ema":
            if len(higher_tf_df) < period:
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
        elif indicator_type == "ehlers_supertrend":
            temp_analyzer = TradingAnalyzer(
                higher_tf_df, self.config, self.logger, self.symbol
            )
            st_result = temp_analyzer.calculate_ehlers_supertrend(
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
        """Generate a signal using confluence of indicators."""
        signal_score = 0.0
        active_indicators = self.config["indicators"]
        weights = self.weights
        isd = self.indicator_settings

        if self.df.empty:
            return "HOLD", 0.0

        current_close = Decimal(str(self.df["close"].iloc[-1]))
        prev_close = Decimal(
            str(self.df["close"].iloc[-2]) if len(self.df) > 1 else current_close
        )

        # EMA Alignment
        if active_indicators.get("ema_alignment", False):
            ema_short = self._get_indicator_value("EMA_Short")
            ema_long = self._get_indicator_value("EMA_Long")
            if not pd.isna(ema_short) and not pd.isna(ema_long):
                if ema_short > ema_long:
                    signal_score += weights.get("ema_alignment", 0)
                elif ema_short < ema_long:
                    signal_score -= weights.get("ema_alignment", 0)

        # SMA Trend Filter
        if active_indicators.get("sma_trend_filter", False):
            sma_long = self._get_indicator_value("SMA_Long")
            if not pd.isna(sma_long):
                if current_close > sma_long:
                    signal_score += weights.get("sma_trend_filter", 0)
                elif current_close < sma_long:
                    signal_score -= weights.get("sma_trend_filter", 0)

        # Momentum Indicators (RSI, StochRSI, CCI, WR, MFI)
        if active_indicators.get("momentum", False):
            momentum_weight = weights.get("momentum_rsi_stoch_cci_wr_mfi", 0)

            if active_indicators.get("rsi", False):
                rsi = self._get_indicator_value("RSI")
                if not pd.isna(rsi):
                    if rsi < isd["rsi_oversold"]:
                        signal_score += momentum_weight * 0.5
                    elif rsi > isd["rsi_overbought"]:
                        signal_score -= momentum_weight * 0.5

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
                        signal_score += momentum_weight * 0.6
                    elif (
                        stoch_k < stoch_d
                        and prev_stoch_k >= prev_stoch_d
                        and stoch_k > isd["stoch_rsi_overbought"]
                    ):
                        signal_score -= momentum_weight * 0.6
                    elif stoch_k > stoch_d and stoch_k < 50:
                        signal_score += momentum_weight * 0.2
                    elif stoch_k < stoch_d and stoch_k > 50:
                        signal_score -= momentum_weight * 0.2

            if active_indicators.get("cci", False):
                cci = self._get_indicator_value("CCI")
                if not pd.isna(cci):
                    if cci < isd["cci_oversold"]:
                        signal_score += momentum_weight * 0.4
                    elif cci > isd["cci_overbought"]:
                        signal_score -= momentum_weight * 0.4

            if active_indicators.get("wr", False):
                wr = self._get_indicator_value("WR")
                if not pd.isna(wr):
                    if wr < isd["williams_r_oversold"]:
                        signal_score += momentum_weight * 0.4
                    elif wr > isd["williams_r_overbought"]:
                        signal_score -= momentum_weight * 0.4

            if active_indicators.get("mfi", False):
                mfi = self._get_indicator_value("MFI")
                if not pd.isna(mfi):
                    if mfi < isd["mfi_oversold"]:
                        signal_score += momentum_weight * 0.4
                    elif mfi > isd["mfi_overbought"]:
                        signal_score -= momentum_weight * 0.4

        # Bollinger Bands
        if active_indicators.get("bollinger_bands", False):
            bb_upper = self._get_indicator_value("BB_Upper")
            bb_lower = self._get_indicator_value("BB_Lower")
            if not pd.isna(bb_upper) and not pd.isna(bb_lower):
                if current_close < bb_lower:
                    signal_score += weights.get("bollinger_bands", 0) * 0.5
                elif current_close > bb_upper:
                    signal_score -= weights.get("bollinger_bands", 0) * 0.5

        # VWAP
        if active_indicators.get("vwap", False):
            vwap = self._get_indicator_value("VWAP")
            if not pd.isna(vwap):
                if current_close > vwap:
                    signal_score += weights.get("vwap", 0) * 0.2
                elif current_close < vwap:
                    signal_score -= weights.get("vwap", 0) * 0.2

                if len(self.df) > 1 and "VWAP" in self.df.columns:
                    prev_vwap = Decimal(str(self.df["VWAP"].iloc[-2]))
                    if current_close > vwap and prev_close <= prev_vwap:
                        signal_score += weights.get("vwap", 0) * 0.3
                    elif current_close < vwap and prev_close >= prev_vwap:
                        signal_score -= weights.get("vwap", 0) * 0.3

        # PSAR
        if active_indicators.get("psar", False):
            psar_val = self._get_indicator_value("PSAR_Val")
            psar_dir = self._get_indicator_value("PSAR_Dir")
            if not pd.isna(psar_val) and not pd.isna(psar_dir):
                if psar_dir == 1:
                    signal_score += weights.get("psar", 0) * 0.5
                elif psar_dir == -1:
                    signal_score -= weights.get("psar", 0) * 0.5

                if len(self.df) > 1 and "PSAR_Val" in self.df.columns:
                    prev_psar_val = Decimal(str(self.df["PSAR_Val"].iloc[-2]))
                    if current_close > psar_val and prev_close <= prev_psar_val:
                        signal_score += weights.get("psar", 0) * 0.4
                    elif current_close < psar_val and prev_close >= prev_psar_val:
                        signal_score -= weights.get("psar", 0) * 0.4

        # Orderbook Imbalance
        if active_indicators.get("orderbook_imbalance", False) and orderbook_data:
            imbalance = self._check_orderbook(current_price, orderbook_data)
            signal_score += imbalance * weights.get("orderbook_imbalance", 0)

        # Fibonacci Levels (confluence with price action)
        if active_indicators.get("fibonacci_levels", False) and self.fib_levels:
            for level_name, level_price in self.fib_levels.items():
                if (
                    level_name not in ["0.0%", "100.0%"]
                    and abs(current_price - level_price) / current_price
                    < Decimal("0.001")
                    and len(self.df) > 1
                ):
                        if current_close > prev_close and current_close > level_price:
                            signal_score += weights.get("fibonacci_levels", 0) * 0.1
                        elif current_close < prev_close and current_close < level_price:
                            signal_score -= weights.get("fibonacci_levels", 0) * 0.1

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
                    signal_score += weight
                elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1:
                    signal_score -= weight
                elif st_slow_dir == 1 and st_fast_dir == 1:
                    signal_score += weight * 0.3
                elif st_slow_dir == -1 and st_fast_dir == -1:
                    signal_score -= weight * 0.3

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
                    signal_score += weight
                elif (
                    macd_line < signal_line
                    and self.df["MACD_Line"].iloc[-2] >= self.df["MACD_Signal"].iloc[-2]
                ):
                    signal_score -= weight
                elif histogram > 0 and self.df["MACD_Hist"].iloc[-2] < 0:
                    signal_score += weight * 0.2
                elif histogram < 0 and self.df["MACD_Hist"].iloc[-2] > 0:
                    signal_score -= weight * 0.2

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
                    elif minus_di > plus_di:
                        signal_score -= weight
                elif adx_val < ADX_WEAK_TREND_THRESHOLD:
                    signal_score += 0

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
                    signal_score += weight * 0.5
                elif (
                    tenkan_sen < kijun_sen
                    and self.df["Tenkan_Sen"].iloc[-2] >= self.df["Kijun_Sen"].iloc[-2]
                ):
                    signal_score -= weight * 0.5

                if current_close > max(senkou_span_a, senkou_span_b) and self.df[
                    "close"
                ].iloc[-2] <= max(
                    self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]
                ):
                    signal_score += weight * 0.7
                elif current_close < min(senkou_span_a, senkou_span_b) and self.df[
                    "close"
                ].iloc[-2] >= min(
                    self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]
                ):
                    signal_score -= weight * 0.7

                if (
                    chikou_span > current_close
                    and self.df["Chikou_Span"].iloc[-2] <= self.df["close"].iloc[-2]
                ):
                    signal_score += weight * 0.3
                elif (
                    chikou_span < current_close
                    and self.df["Chikou_Span"].iloc[-2] >= self.df["close"].iloc[-2]
                ):
                    signal_score -= weight * 0.3

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
                    signal_score += weight * 0.5
                elif (
                    obv_val < obv_ema
                    and self.df["OBV"].iloc[-2] >= self.df["OBV_EMA"].iloc[-2]
                ):
                    signal_score -= weight * 0.5

                if len(self.df) > 2:
                    if (
                        obv_val > self.df["OBV"].iloc[-2]
                        and obv_val > self.df["OBV"].iloc[-3]
                    ):
                        signal_score += weight * 0.2
                    elif (
                        obv_val < self.df["OBV"].iloc[-2]
                        and obv_val < self.df["OBV"].iloc[-3]
                    ):
                        signal_score -= weight * 0.2

        # --- CMF Alignment Scoring ---
        if active_indicators.get("cmf", False):
            cmf_val = self._get_indicator_value("CMF")
            weight = weights.get("cmf_flow", 0.0)

            if not pd.isna(cmf_val):
                if cmf_val > 0:
                    signal_score += weight * 0.5
                elif cmf_val < 0:
                    signal_score -= weight * 0.5

                if len(self.df) > 2:
                    if (
                        cmf_val > self.df["CMF"].iloc[-2]
                        and cmf_val > self.df["CMF"].iloc[-3]
                    ):
                        signal_score += weight * 0.3
                    elif (
                        cmf_val < self.df["CMF"].iloc[-2]
                        and cmf_val < self.df["CMF"].iloc[-3]
                    ):
                        signal_score -= weight * 0.3

        # --- Volatility Index Scoring ---
        if active_indicators.get("volatility_index", False):
            vol_idx = self._get_indicator_value("Volatility_Index")
            weight = weights.get("volatility_index_signal", 0.0)
            if not pd.isna(vol_idx) and len(self.df) > 2 and "Volatility_Index" in self.df.columns:
                    prev_vol_idx = self.df["Volatility_Index"].iloc[-2]
                    prev_prev_vol_idx = self.df["Volatility_Index"].iloc[-3]

                    if vol_idx > prev_vol_idx > prev_prev_vol_idx:
                        if signal_score > 0:
                            signal_score += weight * 0.2
                        elif signal_score < 0:
                            signal_score -= weight * 0.2
                    elif vol_idx < prev_vol_idx < prev_prev_vol_idx and abs(signal_score) > 0:
                            signal_score *= 0.8

        # --- VWMA Cross Scoring ---
        if active_indicators.get("vwma", False):
            vwma = self._get_indicator_value("VWMA")
            weight = weights.get("vwma_cross", 0.0)
            if not pd.isna(vwma) and len(self.df) > 1:
                prev_vwma = self.df["VWMA"].iloc[-2]
                if current_close > vwma and prev_close <= prev_vwma:
                    signal_score += weight
                elif current_close < vwma and prev_close >= prev_vwma:
                    signal_score -= weight

        # --- Volume Delta Scoring ---
        if active_indicators.get("volume_delta", False):
            volume_delta = self._get_indicator_value("Volume_Delta")
            volume_delta_threshold = isd["volume_delta_threshold"]
            weight = weights.get("volume_delta_signal", 0.0)

            if not pd.isna(volume_delta):
                if volume_delta > volume_delta_threshold:
                    signal_score += weight
                elif volume_delta < -volume_delta_threshold:
                    signal_score -= weight
                elif volume_delta > 0:
                    signal_score += weight * 0.3
                elif volume_delta < 0:
                    signal_score -= weight * 0.3

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
                normalized_mtf_score = (mtf_buy_score - mtf_sell_score) / len(
                    mtf_trends
                )
                signal_score += mtf_weight * normalized_mtf_score

        # --- Final Signal Determination ---
        threshold = max(self.config["signal_score_threshold"], 2.5) # Enforce higher threshold for profitability
        final_signal = "HOLD"
        if signal_score >= threshold:
            final_signal = "BUY"
        elif signal_score <= -threshold:
            final_signal = "SELL"

        self.logger.info(
            f"{NEON_YELLOW}Raw Signal Score: {signal_score:.2f}, Final Signal: {final_signal}{RESET}"
        )
        return final_signal, signal_score


# --- Utilities for execution layer ---


def build_partial_tp_targets(
    side: Literal["BUY", "SELL"],
    entry_price: Decimal,
    atr_value: Decimal,
    total_qty: Decimal,
    cfg: dict,
    qty_step: Decimal,
) -> list[dict]:
    ex = cfg["execution"]
    tps = ex["tp_scheme"]["targets"]
    price_prec = cfg["trade_management"]["price_precision"]
    out = []
    for i, t in enumerate(tps, start=1):
        qty = round_qty(total_qty * Decimal(str(t["size_pct"])), qty_step)
        if qty <= 0:
            continue
        if ex["tp_scheme"]["mode"] == "atr_multiples":
            price = (
                entry_price + atr_value * Decimal(str(t["atr_multiple"]))
                if side == "BUY"
                else entry_price - atr_value * Decimal(str(t["atr_multiple"]))
            )
        else:
            price = (
                entry_price * (1 + Decimal(str(t.get("percent", 1))) / 100)
                if side == "BUY"
                else entry_price * (1 - Decimal(str(t.get("percent", 1))) / 100)
            )
        tif = t.get("tif", ex.get("default_time_in_force"))
        if tif == "GoodTillCancel":
            tif = "GTC"
        out.append(
            {
                "name": t.get("name", f"TP{i}"),
                "price": round_price(price, price_prec),
                "qty": qty,
                "order_type": t.get("order_type", "Limit"),
                "tif": tif,
                "post_only": bool(t.get("post_only", ex.get("post_only_default", False))),
                "link_id_suffix": f"tp{i}",
            }
        )
    return out


def compute_stop_loss_price(
    side: Literal["BUY", "SELL"], entry_price: Decimal, atr_value: Decimal, cfg: dict
) -> Decimal:
    ex = cfg["execution"]
    sch = ex["sl_scheme"]
    price_prec = cfg["trade_management"]["price_precision"]
    tick_size = Decimal(f"1e-{price_prec}")
    buffer = tick_size * 5  # 5 ticks buffer

    if sch["type"] == "atr_multiple":
        sl = (
            entry_price - atr_value * Decimal(str(sch["atr_multiple"]))
            if side == "BUY"
            else entry_price + atr_value * Decimal(str(sch["atr_multiple"]))
        )
    else:
        sl = (
            entry_price * (1 - Decimal(str(sch["percent"])) / 100)
            if side == "BUY"
            else entry_price * (1 + Decimal(str(sch["percent"])) / 100)
        )

    sl_with_buffer = sl - buffer if side == "BUY" else sl + buffer
    return round_price(sl_with_buffer, price_prec)


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
        pybit_client.set_leverage(
            config["symbol"],
            config["execution"]["buy_leverage"],
            config["execution"]["sell_leverage"],
        )

    position_manager = PositionManager(config, logger, config["symbol"], pybit_client)
    performance_tracker = PerformanceTracker(logger)
    exec_sync = (
        ExchangeExecutionSync(
            config["symbol"], pybit_client, logger, config, position_manager, performance_tracker
        )
        if config["execution"]["live_sync"]["enabled"]
        else None
    )
    heartbeat = (
        PositionHeartbeat(config["symbol"], pybit_client, logger, config, position_manager)
        if config["execution"]["live_sync"]["heartbeat"]["enabled"]
        else None
    )

    while True:
        try:
            logger.info(
                f"{NEON_PURPLE}--- New Analysis Loop ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}) ---{RESET}"
            )
            current_price = fetch_current_price(config["symbol"], pybit_client, logger)
            if current_price is None:
                time.sleep(config["loop_delay"])
                continue

            df = fetch_klines(config["symbol"], config["interval"], 1000, pybit_client, logger)
            if df is None or df.empty:
                time.sleep(config["loop_delay"])
                continue

            orderbook_data = None
            if config["indicators"].get("orderbook_imbalance", False):
                orderbook_data = fetch_orderbook(
                    config["symbol"], config["orderbook_limit"], pybit_client, logger
                )

            mtf_trends: dict[str, str] = {}
            if config["mtf_analysis"]["enabled"]:
                for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
                    htf_df = fetch_klines(config["symbol"], htf_interval, 1000, pybit_client, logger)
                    if htf_df is not None and not htf_df.empty:
                        for trend_ind in config["mtf_analysis"]["trend_indicators"]:
                            temp_htf_analyzer = TradingAnalyzer(
                                htf_df, config, logger, config["symbol"]
                            )
                            trend = temp_htf_analyzer._get_mtf_trend(
                                temp_htf_analyzer.df, trend_ind
                            )
                            mtf_trends[f"{htf_interval}_{trend_ind}"] = trend
                    else:
                        logger.warning(
                            f"{NEON_YELLOW}Could not fetch klines for higher timeframe {htf_interval} or it was empty. Skipping MTF trend for this TF.{RESET}"
                        )
                    time.sleep(
                        config["mtf_analysis"]["mtf_request_delay_seconds"]
                    )  # Delay between MTF requests

            analyzer = TradingAnalyzer(df, config, logger, config["symbol"])
            if analyzer.df.empty:
                time.sleep(config["loop_delay"])
                continue

            atr_value = Decimal(
                str(analyzer._get_indicator_value("ATR", Decimal("0.1")))
            )
            config["_last_atr"] = str(atr_value)

            trading_signal, signal_score = analyzer.generate_trading_signal(
                current_price, orderbook_data, mtf_trends
            )

            # Manage simulated positions (only runs if not live)
            position_manager.manage_positions(current_price, performance_tracker)

            if (
                trading_signal in ("BUY", "SELL")
                and abs(signal_score) >= config["signal_score_threshold"]
            ):
                position_manager.open_position(trading_signal, current_price, atr_value)
            else:
                logger.info(
                    f"{NEON_BLUE}No strong signal. Holding. Score: {signal_score:.2f}{RESET}"
                )

            if exec_sync:
                exec_sync.poll()
            if heartbeat:
                heartbeat.tick()

            logger.info(f"{NEON_YELLOW}Performance: {performance_tracker.get_summary()}{RESET}")
            logger.info(
                f"{NEON_PURPLE}--- Loop Finished. Waiting {config['loop_delay']}s ---{RESET}"
            )
            time.sleep(config["loop_delay"])

        except Exception as e:
            alert_system.send_alert(f"Unhandled error in main loop: {e}", "ERROR")
            logger.exception(f"{NEON_RED}Unhandled exception in main loop:{RESET}")
            time.sleep(config["loop_delay"] * 2)


if __name__ == "__main__":
    main()
