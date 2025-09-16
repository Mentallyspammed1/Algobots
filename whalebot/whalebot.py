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

SKLEARN_AVAILABLE = False

getcontext().prec = 28
init(autoreset=True)
load_dotenv()

NEON_GREEN = Fore.LIGHTGREEN_EX
NEON_BLUE = Fore.CYAN
NEON_PURPLE = Fore.MAGENTA
NEON_YELLOW = Fore.YELLOW
NEON_RED = Fore.LIGHTRED_EX
NEON_CYAN = Fore.CYAN
RESET = Style.RESET_ALL

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
    "Kaufman_AMA": Fore.GREEN,
    "Relative_Volume": Fore.LIGHTMAGENTA_EX,
    "Market_Structure_Trend": Fore.LIGHTCYAN_EX,
    "DEMA": Fore.BLUE,
    "Keltner_Upper": Fore.LIGHTMAGENTA_EX,
    "Keltner_Middle": Fore.WHITE,
    "Keltner_Lower": Fore.MAGENTA,
    "ROC": Fore.LIGHTGREEN_EX,
    "Pivot": Fore.WHITE,
    "R1": Fore.CYAN,
    "R2": Fore.LIGHTCYAN_EX,
    "S1": Fore.MAGENTA,
    "S2": Fore.LIGHTMAGENTA_EX,
    "Candlestick_Pattern": Fore.LIGHTYELLOW_EX,
    "Support_Level": Fore.LIGHTCYAN_EX,
    "Resistance_Level": Fore.RED,
}

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

MIN_DATA_POINTS_TR = 2
MIN_DATA_POINTS_SMOOTHER = 2
MIN_DATA_POINTS_OBV = 2
MIN_DATA_POINTS_PSAR = 2
ADX_STRONG_TREND_THRESHOLD = 25
ADX_WEAK_TREND_THRESHOLD = 20
MIN_DATA_POINTS_VWMA = 2
MIN_DATA_POINTS_VOLATILITY = 2
MIN_DATA_POINTS_KAMA = 2
MIN_DATA_POINTS_SMOOTHER_INIT = 2
STOCH_RSI_MID_POINT = 50
MIN_CANDLESTICK_PATTERNS_BARS = 2


def load_config(filepath: str, logger: logging.Logger) -> dict[str, Any]:
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
            "slippage_percent": 0.001,
            "trading_fee_percent": 0.0005,
        },
        "mtf_analysis": {
            "enabled": True,
            "higher_timeframes": ["60", "240"],
            "trend_indicators": ["ema", "ehlers_supertrend"],
            "trend_period": 50,
            "mtf_request_delay_seconds": 0.5,
        },
        "ml_enhancement": {
            "enabled": False,
            "model_path": "ml_model.pkl",
            "retrain_on_startup": False,
            "training_data_limit": 5000,
            "prediction_lookahead": 12,
            "profit_target_percent": 0.5,
            "feature_lags": [1, 2, 3, 5],
            "cross_validation_folds": 5,
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
            "kama_period": 10,
            "kama_fast_period": 2,
            "kama_slow_period": 30,
            "relative_volume_period": 20,
            "relative_volume_threshold": 1.5,
            "market_structure_lookback_period": 20,
            "dema_period": 14,
            "keltner_period": 20,
            "keltner_atr_multiplier": 2.0,
            "roc_period": 12,
            "roc_oversold": -5.0,
            "roc_overbought": 5.0,
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
            "kaufman_ama": True,
            "relative_volume": True,
            "market_structure": True,
            "dema": True,
            "keltner_channels": True,
            "roc": True,
            "candlestick_patterns": True,
            "fibonacci_pivot_points": True,
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
                "kaufman_ama_cross": 0.20,
                "relative_volume_confirmation": 0.10,
                "market_structure_confluence": 0.25,
                "dema_crossover": 0.18,
                "keltner_breakout": 0.20,
                "roc_signal": 0.12,
                "candlestick_confirmation": 0.15,
                "fibonacci_pivot_points_confluence": 0.20,
            }
        },
    }
    if not Path(filepath).exists():
        try:
            with Path(filepath).open("w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)
            logger.warning(
                f"{NEON_YELLOW}Configuration file not found. "
                f"Created default config at {filepath} for symbol {default_config['symbol']}{RESET}"
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
            f"{NEON_RED}Error loading config: {e}. "
            f"Using default and attempting to save.{RESET}"
        )
        try:
            with Path(filepath).open("w", encoding="utf-8") as f_default:
                json.dump(default_config, f_default, indent=4)
        except OSError as e_save:
            logger.error(f"{NEON_RED}Could not save default config: {e_save}{RESET}")
        return default_config


def _ensure_config_keys(config: dict[str, Any], default_config: dict[str, Any]) -> None:
    for key, default_value in default_config.items():
        if key not in config:
            config[key] = default_value
        elif isinstance(default_value, dict) and isinstance(config.get(key), dict):
            _ensure_config_keys(config[key], default_value)


from unanimous_logger import setup_logger

# --- Logger Setup ---
# A simple class to adapt the config dict to what setup_logger expects
class UnanimousLoggerConfig:
    def __init__(self, config_dict):
        # Extract log level from config, default to INFO
        self.LOG_LEVEL = config_dict.get("log_level", "INFO").upper()
        
        # Construct log file path from constants defined in the script
        log_filename = config_dict.get("log_filename", "whalebot.log")
        self.LOG_FILE_PATH = os.path.join(LOG_DIRECTORY, log_filename)
        
        # Pass color codes
        self.NEON_BLUE = NEON_BLUE
        self.RESET = RESET

# Create a temporary basic logger for the initial config loading
temp_logger = logging.getLogger("config_loader")
temp_logger.setLevel(logging.INFO)
if not temp_logger.handlers:
    temp_logger.addHandler(logging.StreamHandler(sys.stdout))

# Load the main configuration using the temporary logger
config = load_config(CONFIG_FILE, temp_logger)

# Create the config object for the unanimous logger
logger_config = UnanimousLoggerConfig(config)

# Set up the main application logger using the loaded configuration
logger = setup_logger(logger_config, log_name="whalebot", json_log_file="whalebot.json.log")
# --- End Logger Setup ---




class BybitClient:
    def __init__(self, api_key: str, api_secret: str, base_url: str, logger: logging.Logger):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.logger = logger
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        retries = Retry(
            total=MAX_API_RETRIES,
            backoff_factor=RETRY_DELAY_SECONDS,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=frozenset(["GET", "POST"]),
        )
        session.mount("https://", HTTPAdapter(max_retries=retries))
        return session

    def _generate_signature(self, payload: str) -> str:
        return hmac.new(self.api_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

    def _send_signed_request(
        self,
        method: Literal["GET", "POST"],
        endpoint: str,
        params: dict | None,
    ) -> requests.Response | None:
        if not self.api_key or not self.api_secret:
            self.logger.error(
                f"{NEON_RED}API_KEY or API_SECRET not set for signed request.{RESET}"
            )
            return None

        timestamp = str(int(time.time() * 1000))
        recv_window = "20000"
        headers = {"Content-Type": "application/json"}
        url = f"{self.base_url}{endpoint}"

        if method == "GET":
            query_string = urllib.parse.urlencode(params) if params else ""
            param_str = timestamp + self.api_key + recv_window + query_string
            signature = self._generate_signature(param_str)
            headers.update(
                {
                    "X-BAPI-API-KEY": self.api_key,
                    "X-BAPI-TIMESTAMP": timestamp,
                    "X-BAPI-SIGN": signature,
                    "X-BAPI-RECV-WINDOW": recv_window,
                }
            )
            self.logger.debug(f"GET Request: {url}?{query_string}")
            return self.session.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        else:
            json_params = json.dumps(params) if params else ""
            param_str = timestamp + self.api_key + recv_window + json_params
            signature = self._generate_signature(param_str)
            headers.update(
                {
                    "X-BAPI-API-KEY": self.api_key,
                    "X-BAPI-TIMESTAMP": timestamp,
                    "X-BAPI-SIGN": signature,
                    "X-BAPI-RECV-WINDOW": recv_window,
                }
            )
            self.logger.debug(f"POST Request: {url} with payload {json_params}")
            return self.session.post(url, json=params, headers=headers, timeout=REQUEST_TIMEOUT)

    def _handle_api_response(self, response: requests.Response) -> dict | None:
        try:
            response.raise_for_status()
            data = response.json()
            if data.get("retCode") != 0:
                self.logger.error(
                    f"{NEON_RED}Bybit API Error: {data.get('retMsg')} "
                    f"(Code: {data.get('retCode')}){RESET}"
                )
                return None
            return data
        except requests.exceptions.HTTPError as e:
            self.logger.error(
                f"{NEON_RED}HTTP Error: {e.response.status_code} - {e.response.text}{RESET}"
            )
        except requests.exceptions.ConnectionError as e:
            self.logger.error(f"{NEON_RED}Connection Error: {e}{RESET}")
        except requests.exceptions.Timeout:
            self.logger.error(
                f"{NEON_RED}Request timed out after {REQUEST_TIMEOUT} seconds.{RESET}"
            )
        except requests.exceptions.RequestException as e:
            self.logger.error(f"{NEON_RED}Request Exception: {e}{RESET}")
        except json.JSONDecodeError:
            self.logger.error(
                f"{NEON_RED}Failed to decode JSON response: {response.text}{RESET}"
            )
        return None

    def bybit_request(
        self,
        method: Literal["GET", "POST"],
        endpoint: str,
        params: dict | None = None,
        signed: bool = False,
    ) -> dict | None:
        if signed:
            response = self._send_signed_request(method, endpoint, params)
        else:
            url = f"{self.base_url}{endpoint}"
            self.logger.debug(f"Public Request: {url} with params {params}")
            response = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)

        if response:
            return self._handle_api_response(response)
        return None

    def amend_order(
        self, 
        category: str, 
        symbol: str, 
        order_id: str, 
        new_stop_loss: Decimal | None = None, 
        new_take_profit: Decimal | None = None
    ) -> dict | None:
        endpoint = "/v5/order/amend"
        params = {
            "category": category,
            "symbol": symbol,
            "orderId": order_id,
        }
        if new_stop_loss is not None:
            params["stopLoss"] = str(new_stop_loss)
        if new_take_profit is not None:
            params["takeProfit"] = str(new_take_profit)

        if not new_stop_loss and not new_take_profit:
            self.logger.warning(f"{NEON_YELLOW}No new stop loss or take profit provided for order amendment.{RESET}")
            return None

        self.logger.info(f"{NEON_BLUE}Attempting to amend order {order_id} for {symbol} with SL: {new_stop_loss}, TP: {new_take_profit}{RESET}")
        return self.bybit_request("POST", endpoint, params, signed=True)

    def place_order(
        self,
        category: str,
        symbol: str,
        side: Literal["Buy", "Sell"],
        order_type: Literal["Market", "Limit"],
        qty: Decimal,
        price: Decimal | None = None,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
    ) -> dict | None:
        endpoint = "/v5/order/create"
        params = {
            "category": category,
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": str(qty),
        }
        if price is not None:
            params["price"] = str(price)
        if stop_loss is not None:
            params["stopLoss"] = str(stop_loss)
        if take_profit is not None:
            params["takeProfit"] = str(take_profit)

        self.logger.info(f"{NEON_BLUE}Attempting to place {side} order for {qty} {symbol} (SL: {stop_loss}, TP: {take_profit}){RESET}")
        return self.bybit_request("POST", endpoint, params, signed=True)

    def fetch_current_price(self, symbol: str) -> Decimal | None:
        endpoint = "/v5/market/tickers"
        params = {"category": "linear", "symbol": symbol}
        response = self.bybit_request("GET", endpoint, params)
        if response and response["result"] and response["result"]["list"]:
            price = Decimal(response["result"]["list"][0]["lastPrice"])
            self.logger.debug(f"Fetched current price for {symbol}: {price}")
            return price
        self.logger.warning(f"{NEON_YELLOW}Could not fetch current price for {symbol}.{RESET}")
        return None

    def fetch_klines(
        self, symbol: str, interval: str, limit: int
    ) -> pd.DataFrame | None:
        endpoint = "/v5/market/kline"
        params = {
            "category": "linear",
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        response = self.bybit_request("GET", endpoint, params)
        if response and response["result"] and response["result"]["list"]:
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
                self.logger.warning(
                    f"{NEON_YELLOW}Fetched klines for {symbol} {interval} but DataFrame is empty after processing. Raw response: {response}{RESET}"
                )
                return None

            self.logger.debug(f"Fetched {len(df)} {interval} klines for {symbol}.")
            return df
        self.logger.warning(
            f"{NEON_YELLOW}Could not fetch klines for {symbol} {interval}. API response might be empty or invalid. Raw response: {response}{RESET}"
        )
        return None

    def fetch_orderbook(self, symbol: str, limit: int) -> dict | None:
        endpoint = "/v5/market/orderbook"
        params = {"category": "linear", "symbol": symbol, "limit": limit}
        response = self.bybit_request("GET", endpoint, params)
        if response and response["result"]:
            self.logger.debug(f"Fetched orderbook for {symbol} with limit {limit}.")
            return response["result"]
        self.logger.warning(f"{NEON_YELLOW}Could not fetch orderbook for {symbol}.{RESET}")
        return None


class PositionManager:
    def __init__(self, config: dict[str, Any], logger: logging.Logger, symbol: str, bybit_client: BybitClient):
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.open_positions: list[dict] = []
        self.trade_management_enabled = config["trade_management"]["enabled"]
        self.max_open_positions = config["trade_management"]["max_open_positions"]
        self.order_precision = config["trade_management"]["order_precision"]
        self.price_precision = config["trade_management"]["price_precision"]
        self.slippage_percent = Decimal(
            str(config["trade_management"].get("slippage_percent", 0.0))
        )
        self.account_balance = Decimal(str(config["trade_management"]["account_balance"]))
        self.bybit_client = bybit_client

    def _get_current_balance(self) -> Decimal:
        return self.account_balance

    def _calculate_order_size(
        self, current_price: Decimal, atr_value: Decimal
    ) -> Decimal:
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
            self.logger.warning(
                f"{NEON_YELLOW}Calculated stop loss distance is zero or negative. Cannot determine order size.{RESET}"
            )
            return Decimal("0")

        order_value = risk_amount / stop_loss_distance
        order_qty = order_value / current_price

        precision_str = "0." + "0" * (self.order_precision - 1) + "1"
        order_qty = order_qty.quantize(Decimal(precision_str), rounding=ROUND_DOWN)

        self.logger.info(
            f"[{self.symbol}] Calculated order size: {order_qty.normalize()} (Risk: {risk_amount.normalize():.2f} USD)"
        )
        return order_qty

    def open_position(
        self, signal: Literal["BUY", "SELL"], current_price: Decimal, atr_value: Decimal, order_id: str
    ) -> dict | None:
        if not self.trade_management_enabled:
            self.logger.info(
                f"{NEON_YELLOW}[{self.symbol}] Trade management is disabled. Skipping opening position.{RESET}"
            )
            return None

        if len(self.open_positions) >= self.max_open_positions:
            self.logger.info(
                f"{NEON_YELLOW}[{self.symbol}] Max open positions ({self.max_open_positions}) reached. Cannot open new position.{RESET}"
            )
            return None

        order_qty = self._calculate_order_size(current_price, atr_value)
        if order_qty <= 0:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Order quantity is zero or negative. Cannot open position.{RESET}"
            )
            return None

        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"])
        )
        take_profit_atr_multiple = Decimal(
            str(self.config["trade_management"]["take_profit_atr_multiple"])
        )

        if signal == "BUY":
            adjusted_entry_price = current_price * (
                Decimal("1") + self.slippage_percent
            )
            stop_loss = adjusted_entry_price - (atr_value * stop_loss_atr_multiple)
            take_profit = adjusted_entry_price + (atr_value * take_profit_atr_multiple)
        else:
            adjusted_entry_price = current_price * (
                Decimal("1") - self.slippage_percent
            )
            stop_loss = adjusted_entry_price + (atr_value * stop_loss_atr_multiple)
            take_profit = adjusted_entry_price - (atr_value * take_profit_atr_multiple)

        price_precision_str = "0." + "0" * (self.price_precision - 1) + "1"

        position = {
            "entry_time": datetime.now(TIMEZONE),
            "symbol": self.symbol,
            "side": signal,
            "entry_price": adjusted_entry_price.quantize(
                Decimal(price_precision_str), rounding=ROUND_DOWN
            ),
            "qty": order_qty,
            "stop_loss": stop_loss.quantize(
                Decimal(price_precision_str), rounding=ROUND_DOWN
            ),
            "take_profit": take_profit.quantize(
                Decimal(price_precision_str), rounding=ROUND_DOWN
            ),
            "status": "OPEN",
            "order_id": order_id,
        }
        self.open_positions.append(position)
        self.logger.info(
            f"{NEON_GREEN}[{self.symbol}] Opened {signal} position: {position}{RESET}"
        )
        self.logger.info("Position opened", extra=position)
        return position

    def _check_and_close_position(
        self,
        position: dict,
        current_price: Decimal,
        slippage_percent: Decimal,
        price_precision: int,
        logger: logging.Logger,
    ) -> tuple[bool, Decimal, str]:
        side = position["side"]
        stop_loss = position["stop_loss"]
        take_profit = position["take_profit"]

        closed_by = None
        close_price = Decimal("0")

        if side == "BUY":
            if current_price <= stop_loss:
                closed_by = "STOP_LOSS"
                close_price = current_price * (Decimal("1") - slippage_percent)
            elif current_price >= take_profit:
                closed_by = "TAKE_PROFIT"
                close_price = current_price * (Decimal("1") - slippage_percent)
        elif side == "SELL":
            if current_price >= stop_loss:
                closed_by = "STOP_LOSS"
                close_price = current_price * (Decimal("1") + slippage_percent)
            elif current_price <= take_profit:
                closed_by = "TAKE_PROFIT"
                close_price = current_price * (Decimal("1") + slippage_percent)

        if closed_by:
            price_precision_str = "0." + "0" * (price_precision - 1) + "1"
            adjusted_close_price = close_price.quantize(
                Decimal(price_precision_str), rounding=ROUND_DOWN
            )
            return True, adjusted_close_price, closed_by
        return False, Decimal("0"), ""

    def manage_positions(
        self, current_price: Decimal, performance_tracker: Any
    ) -> None:
        if not self.trade_management_enabled or not self.open_positions:
            return

        positions_to_close = []
        for i, position in enumerate(self.open_positions):
            if position["status"] == "OPEN":
                is_closed, adjusted_close_price, closed_by = (
                    self._check_and_close_position(
                        position,
                        current_price,
                        self.slippage_percent,
                        self.price_precision,
                        self.logger,
                    )
                )

                if closed_by:
                    position["status"] = "CLOSED"
                    position["exit_time"] = datetime.now(TIMEZONE)
                    position["exit_price"] = adjusted_close_price
                    position["closed_by"] = closed_by
                    positions_to_close.append(i)

                    pnl = (
                        (adjusted_close_price - position["entry_price"])
                        * position["qty"]
                        if position["side"] == "BUY"
                        else (position["entry_price"] - adjusted_close_price)
                        * position["qty"]
                    )
                    performance_tracker.record_trade(position, pnl)
                    self.logger.info(
                        f"{NEON_PURPLE}[{self.symbol}] Closed {position['side']} position by {closed_by}: {position}. PnL: {pnl.normalize():.2f}{RESET}"
                    )

        self.open_positions = [
            pos
            for i, pos in enumerate(self.open_positions)
            if i not in positions_to_close
        ]

        # Check for SL/TP amendments (e.g., for trailing stop loss)
        for position in self.open_positions:
            if position["status"] == "OPEN":
                # In a real scenario, you'd compare current SL/TP on exchange with calculated ones.
                # For simplicity, we assume if the position's SL/TP changed, it needs amending.
                # This part would be triggered by a trailing stop loss update, for example.
                # For now, we just demonstrate the call.
                if "order_id" in position and position["order_id"]:
                    # Example: If a trailing stop loss logic updates position["stop_loss"]
                    # or position["take_profit"] dynamically, this would trigger the amendment.
                    # We need to ensure we only amend if the values are actually different from the last sent.
                    # For this example, we'll just call it if the position is open.
                    self.bybit_client.amend_order(
                        category="linear", # Assuming linear for now
                        symbol=self.symbol,
                        order_id=position["order_id"],
                        new_stop_loss=position["stop_loss"],
                        new_take_profit=position["take_profit"],
                    )

    def get_open_positions(self) -> list[dict]:
        return [pos for pos in self.open_positions if pos["status"] == "OPEN"]


class PerformanceTracker:
    def __init__(self, logger: logging.Logger, config: dict[str, Any]):
        self.logger = logger
        self.config = config
        self.trades: list[dict] = []
        self.total_pnl = Decimal("0")
        self.wins = 0
        self.losses = 0
        self.trading_fee_percent = Decimal(
            str(config["trade_management"].get("trading_fee_percent", 0.0))
        )

    def record_trade(self, position: dict, pnl: Decimal) -> None:
        trade_record = {
            "entry_time": position["entry_time"],
            "exit_time": position["exit_time"],
            "symbol": position["symbol"],
            "side": position["side"],
            "entry_price": position["entry_price"],
            "exit_price": position["exit_price"],
            "qty": position["qty"],
            "pnl": pnl,
            "closed_by": position["closed_by"],
        }
        self.trades.append(trade_record)
        self.total_pnl += pnl

        entry_fee = position["entry_price"] * position["qty"] * self.trading_fee_percent
        exit_fee = position["exit_price"] * position["qty"] * self.trading_fee_percent
        total_fees = entry_fee + exit_fee
        self.total_pnl -= total_fees

        if pnl > 0:
            self.wins += 1
        else:
            self.losses += 1
        self.logger.info(
            f"{NEON_CYAN}[{position['symbol']}] Trade recorded. PnL (before fees): {pnl.normalize():.2f}, Total Fees: {total_fees.normalize():.2f}, Current Total PnL (after fees): {self.total_pnl.normalize():.2f}, Wins: {self.wins}, Losses: {self.losses}{RESET}"
        )

    def get_summary(self) -> dict:
        total_trades = len(self.trades)
        win_rate = (self.wins / total_trades) * 100 if total_trades > 0 else 0

        return {
            "total_trades": total_trades,
            "total_pnl": self.total_pnl,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": f"{win_rate:.2f}%",
        }


class AlertSystem:
    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def send_alert(
        self, message: str, level: Literal["INFO", "WARNING", "ERROR"]
    ) -> None:
        if level == "INFO":
            self.logger.info(f"{NEON_BLUE}ALERT: {message}{RESET}")
        elif level == "WARNING":
            self.logger.warning(f"{NEON_YELLOW}ALERT: {message}{RESET}")
        elif level == "ERROR":
            self.logger.error(f"{NEON_RED}ALERT: {message}{RESET}")


class TechnicalIndicators:
    def __init__(self, df: pd.DataFrame, indicator_settings: dict[str, Any], logger: logging.Logger, symbol: str):
        self.df = df
        self.isd = indicator_settings
        self.logger = logger
        self.symbol = symbol

    def _log_insufficient_data(self, indicator_name: str, required: int) -> None:
        self.logger.debug(
            f"[{self.symbol}] Skipping indicator '{indicator_name}': Not enough data. "
            f"Need {required}, have {len(self.df)}."
        )

    def calculate_true_range(self) -> pd.Series:
        if len(self.df) < MIN_DATA_POINTS_TR:
            self._log_insufficient_data("True Range", MIN_DATA_POINTS_TR)
            return pd.Series(np.nan, index=self.df.index)
        high_low = self.df["high"] - self.df["low"]
        high_prev_close = (self.df["high"] - self.df["close"].shift()).abs()
        low_prev_close = (self.df["low"] - self.df["close"].shift()).abs()
        return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(
            axis=1
        )

    def calculate_super_smoother(self, series: pd.Series, period: int) -> pd.Series:
        if period <= 0 or len(series) < MIN_DATA_POINTS_SMOOTHER:
            self._log_insufficient_data("Super Smoother", MIN_DATA_POINTS_SMOOTHER)
            return pd.Series(np.nan, index=series.index)

        series = pd.to_numeric(series, errors="coerce").dropna()
        if len(series) < MIN_DATA_POINTS_SMOOTHER_INIT:
            self._log_insufficient_data(
                "Super Smoother (initialization)", MIN_DATA_POINTS_SMOOTHER_INIT
            )
            return pd.Series(np.nan, index=self.df.index)

        a1 = np.exp(-np.sqrt(2) * np.pi / period)
        b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / period)
        c1 = 1 - b1 + a1**2
        c2 = b1 - 2 * a1**2
        c3 = a1**2

        filt = pd.Series(0.0, index=series.index)
        if len(series) >= 1:
            filt.iloc[0] = series.iloc[0]
        if len(series) >= MIN_DATA_POINTS_SMOOTHER_INIT:
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
        if len(self.df) < period * 3:
            self._log_insufficient_data("Ehlers SuperTrend", period * 3)
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
            self.logger.warning(
                f"[{self.symbol}] Ehlers SuperTrend: DataFrame empty after smoothing. Returning None."
            )
            return None

        upper_band = df_copy["smoothed_price"] + multiplier * df_copy["smoothed_atr"]
        lower_band = df_copy["smoothed_price"] - multiplier * df_copy["smoothed_atr"]

        direction = pd.Series(0, index=df_copy.index, dtype=int)
        supertrend = pd.Series(np.nan, index=df_copy.index)

        first_valid_idx_loc = 0
        while first_valid_idx_loc < len(df_copy) and pd.isna(df_copy["close"].iloc[first_valid_idx_loc]):
            first_valid_idx_loc += 1
        if first_valid_idx_loc >= len(df_copy):
            return None

        if df_copy["close"].iloc[first_valid_idx_loc] > upper_band.iloc[first_valid_idx_loc]:
            direction.iloc[first_valid_idx_loc] = 1
            supertrend.iloc[first_valid_idx_loc] = lower_band.iloc[first_valid_idx_loc]
        elif df_copy["close"].iloc[first_valid_idx_loc] < lower_band.iloc[first_valid_idx_loc]:
            direction.iloc[first_valid_idx_loc] = -1
            supertrend.iloc[first_valid_idx_loc] = upper_band.iloc[first_valid_idx_loc]
        else:
            direction.iloc[first_valid_idx_loc] = 0
            supertrend.iloc[first_valid_idx_loc] = lower_band.iloc[first_valid_idx_loc]

        for i in range(first_valid_idx_loc + 1, len(df_copy)):
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
            elif curr_close > upper_band.iloc[i]:
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
        required_len = slow_period + signal_period
        if len(self.df) < required_len:
            self._log_insufficient_data("MACD", required_len)
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        ema_fast = self.df["close"].ewm(span=fast_period, adjust=False).mean()
        ema_slow = self.df["close"].ewm(span=slow_period, adjust=False).mean()

        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        histogram = macd_line - signal_line

        return macd_line, signal_line, histogram

    def calculate_rsi(self, period: int) -> pd.Series:
        if len(self.df) <= period:
            self._log_insufficient_data("RSI", period + 1)
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
        required_len = period + k_period + d_period
        if len(self.df) <= required_len:
            self._log_insufficient_data("StochRSI", required_len)
            return pd.Series(np.nan), pd.Series(np.nan)

        rsi = self.calculate_rsi(period)
        if rsi.isnull().all():
            return pd.Series(np.nan), pd.Series(np.nan)

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
        required_len = period * 2
        if len(self.df) < required_len:
            self._log_insufficient_data("ADX", required_len)
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        tr = self.calculate_true_range()
        if tr.isnull().all():
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

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
        if len(self.df) < period:
            self._log_insufficient_data("Bollinger Bands", period)
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)
        middle_band = self.df["close"].rolling(window=period, min_periods=period).mean()
        std = self.df["close"].rolling(window=period, min_periods=period).std()
        upper_band = middle_band + (std * std_dev)
        lower_band = middle_band - (std * std_dev)
        return upper_band, middle_band, lower_band

    def calculate_vwap(self) -> pd.Series:
        if self.df.empty:
            return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        cumulative_tp_vol = (typical_price * self.df["volume"]).cumsum()
        cumulative_vol = self.df["volume"].cumsum()
        vwap = cumulative_tp_vol / cumulative_vol
        return vwap.reindex(self.df.index)

    def calculate_cci(self, period: int) -> pd.Series:
        if len(self.df) < period:
            self._log_insufficient_data("CCI", period)
            return pd.Series(np.nan, index=self.df.index)
        tp = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        sma_tp = tp.rolling(window=period, min_periods=period).mean()
        mad = tp.rolling(window=period, min_periods=period).apply(
            lambda x: np.abs(x - x.mean()).mean(), raw=False
        )
        cci = (tp - sma_tp) / (0.015 * mad.replace(0, np.nan))
        return cci

    def calculate_williams_r(self, period: int) -> pd.Series:
        if len(self.df) < period:
            self._log_insufficient_data("Williams %R", period)
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
        required_len = max(tenkan_period, kijun_period, senkou_span_b_period) + chikou_span_offset
        if len(self.df) < required_len:
            self._log_insufficient_data("Ichimoku Cloud", required_len)
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

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
        if len(self.df) <= period:
            self._log_insufficient_data("MFI", period + 1)
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
        if len(self.df) < MIN_DATA_POINTS_OBV:
            self._log_insufficient_data("OBV", MIN_DATA_POINTS_OBV)
            return pd.Series(np.nan), pd.Series(np.nan)

        obv = pd.Series(0.0, index=self.df.index)
        obv_direction = np.sign(self.df["close"].diff().fillna(0))
        obv = (obv_direction * self.df["volume"]).cumsum()

        obv_ema = obv.ewm(span=ema_period, adjust=False).mean()

        return obv, obv_ema

    def calculate_cmf(self, period: int) -> pd.Series:
        if len(self.df) < period:
            self._log_insufficient_data("CMF", period)
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
        if len(self.df) < MIN_DATA_POINTS_PSAR:
            self._log_insufficient_data("PSAR", MIN_DATA_POINTS_PSAR)
            return pd.Series(np.nan, index=self.df.index), pd.Series(np.nan, index=self.df.index)

        psar = self.df["close"].copy()
        bull = pd.Series(True, index=self.df.index)
        af = acceleration

        if self.df["close"].iloc[0] < self.df["close"].iloc[1]:
            ep = self.df["high"].iloc[0]
            bull.iloc[0] = True
        else:
            ep = self.df["low"].iloc[0]
            bull.iloc[0] = False

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
                    psar.iloc[i] = min(
                        self.df["low"].iloc[i], self.df["low"].iloc[i - 1]
                    )
                else:
                    psar.iloc[i] = max(
                        self.df["high"].iloc[i], self.df["high"].iloc[i - 1]
                    )

            elif bull.iloc[i]:
                if self.df["high"].iloc[i] > ep:
                    ep = self.df["high"].iloc[i]
                    af = min(af + acceleration, max_acceleration)
                psar.iloc[i] = min(
                    psar.iloc[i], self.df["low"].iloc[i], self.df["low"].iloc[i - 1]
                )
            else:
                if self.df["low"].iloc[i] < ep:
                    ep = self.df["low"].iloc[i]
                    af = min(af + acceleration, max_acceleration)
                psar.iloc[i] = max(
                    psar.iloc[i], self.df["high"].iloc[i], self.df["high"].iloc[i - 1]
                )

        direction = pd.Series(0, index=self.df.index, dtype=int)
        direction[psar < self.df["close"]] = 1
        direction[psar > self.df["close"]] = -1

        return psar, direction

    def calculate_volatility_index(self, period: int) -> pd.Series:
        if len(self.df) < period or "ATR" not in self.df.columns or self.df["ATR"].isnull().all():
            self._log_insufficient_data("Volatility Index", period)
            return pd.Series(np.nan, index=self.df.index)

        normalized_atr = self.df["ATR"] / self.df["close"]
        volatility_index = normalized_atr.rolling(window=period, min_periods=1).mean()
        return volatility_index

    def calculate_vwma(self, period: int) -> pd.Series:
        if len(self.df) < period or self.df["volume"].isnull().any():
            self._log_insufficient_data("VWMA", period)
            return pd.Series(np.nan, index=self.df.index)

        valid_volume = self.df["volume"].replace(0, np.nan)
        pv = self.df["close"] * valid_volume
        vwma = (
            pv.rolling(window=period).sum() / valid_volume.rolling(window=period).sum()
        )
        return vwma

    def calculate_volume_delta(self, period: int) -> pd.Series:
        if len(self.df) < MIN_DATA_POINTS_VOLATILITY:
            self._log_insufficient_data("Volume Delta", MIN_DATA_POINTS_VOLATILITY)
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

    def calculate_kaufman_ama(
        self, period: int, fast_period: int, slow_period: int
    ) -> pd.Series:
        required_len = period + slow_period
        if len(self.df) < required_len:
            self._log_insufficient_data("Kaufman AMA", required_len)
            return pd.Series(np.nan, index=self.df.index)

        close_prices = self.df["close"].values
        kama = np.full_like(close_prices, np.nan)

        price_change = np.abs(close_prices[period:] - close_prices[:-period])
        volatility = pd.Series(close_prices).diff().abs().rolling(window=period).sum()
        volatility_values = volatility.values

        er = np.full_like(close_prices, np.nan)
        for i in range(period, len(close_prices)):
            if volatility_values[i] == 0:
                er[i] = 0
            else:
                er[i] = price_change[i - period] / volatility_values[i]

        fast_alpha = 2 / (fast_period + 1)
        slow_alpha = 2 / (slow_period + 1)
        sc = (er * (fast_alpha - slow_alpha) + slow_alpha) ** 2

        first_valid_idx = period
        while first_valid_idx < len(close_prices) and (np.isnan(close_prices[first_valid_idx]) or np.isnan(sc[first_valid_idx])):
            first_valid_idx += 1

        if first_valid_idx >= len(close_prices):
            return pd.Series(np.nan, index=self.df.index)

        kama[first_valid_idx] = close_prices[first_valid_idx]

        for i in range(first_valid_idx + 1, len(close_prices)):
            if not np.isnan(sc[i]) and not np.isnan(kama[i-1]):
                kama[i] = kama[i - 1] + sc[i] * (close_prices[i] - kama[i - 1])
            else:
                kama[i] = kama[i - 1] if not np.isnan(kama[i-1]) else close_prices[i]

        return pd.Series(kama, index=self.df.index)

    def calculate_relative_volume(self, period: int) -> pd.Series:
        if len(self.df) < period:
            self._log_insufficient_data("Relative Volume", period)
            return pd.Series(np.nan, index=self.df.index)

        avg_volume = self.df["volume"].rolling(window=period, min_periods=period).mean()
        relative_volume = (self.df["volume"] / avg_volume.replace(0, np.nan)).fillna(
            1.0
        )
        return relative_volume

    def calculate_market_structure(self, lookback_period: int) -> pd.Series:
        required_len = lookback_period * 2
        if len(self.df) < required_len:
            self._log_insufficient_data("Market Structure", required_len)
            return pd.Series("No Pattern", index=self.df.index, dtype="object")

        recent_segment_high = self.df["high"].iloc[-lookback_period:].max()
        recent_segment_low = self.df["low"].iloc[-lookback_period:].min()

        prev_segment_high = (
            self.df["high"].iloc[-2 * lookback_period : -lookback_period].max()
        )
        prev_segment_low = (
            self.df["low"].iloc[-2 * lookback_period : -lookback_period].min()
        )

        trend = "SIDEWAYS"
        if (
            not pd.isna(recent_segment_high)
            and not pd.isna(recent_segment_low)
            and not pd.isna(prev_segment_high)
            and not pd.isna(prev_segment_low)
        ):
            is_higher_high = recent_segment_high > prev_segment_high
            is_higher_low = recent_segment_low > prev_segment_low
            is_lower_high = recent_segment_high < prev_segment_high
            is_lower_low = recent_segment_low < prev_segment_low

            if is_higher_high and is_higher_low:
                trend = "UP"
            elif is_lower_high and is_lower_low:
                trend = "DOWN"

        result_series = pd.Series(trend, index=self.df.index, dtype="object")
        return result_series

    def calculate_dema(self, series: pd.Series, period: int) -> pd.Series:
        required_len = 2 * period
        if len(series) < required_len:
            self._log_insufficient_data("DEMA", required_len)
            return pd.Series(np.nan, index=series.index)

        ema1 = series.ewm(span=period, adjust=False).mean()
        ema2 = ema1.ewm(span=period, adjust=False).mean()
        dema = 2 * ema1 - ema2
        return dema

    def calculate_keltner_channels(
        self, period: int, atr_multiplier: float, atr_period: int
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        if "ATR" not in self.df.columns or self.df["ATR"].isnull().all():
            self.df["ATR"] = self._calculate_atr_internal(atr_period)
            if self.df["ATR"].isnull().all():
                self._log_insufficient_data("Keltner Channels (ATR dependency)", atr_period)
                return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        if len(self.df) < period or self.df["ATR"].isnull().all():
            self._log_insufficient_data("Keltner Channels", period)
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        ema = self.df["close"].ewm(span=period, adjust=False).mean()
        atr = self.df["ATR"]

        upper_band = ema + (atr * atr_multiplier)
        lower_band = ema - (atr * atr_multiplier)

        return upper_band, ema, lower_band
    
    def _calculate_atr_internal(self, atr_period: int) -> pd.Series:
        tr = self.calculate_true_range()
        if tr.isnull().all():
            return pd.Series(np.nan, index=self.df.index)
        atr = tr.ewm(span=atr_period, adjust=False).mean()
        return atr

    def calculate_roc(self, period: int) -> pd.Series:
        if len(self.df) < period + 1:
            self._log_insufficient_data("ROC", period + 1)
            return pd.Series(np.nan, index=self.df.index)

        roc = (
            (self.df["close"] - self.df["close"].shift(period))
            / self.df["close"].shift(period)
        ) * 100
        return roc

    def detect_candlestick_patterns(self) -> pd.Series:
        if len(self.df) < MIN_CANDLESTICK_PATTERNS_BARS:
            self._log_insufficient_data("Candlestick Patterns", MIN_CANDLESTICK_PATTERNS_BARS)
            return pd.Series("No Pattern", index=self.df.index)

        patterns = pd.Series("No Pattern", index=self.df.index, dtype="object")

        i = len(self.df) - 1
        current_bar = self.df.iloc[i]
        prev_bar = self.df.iloc[i - 1]

        if any(pd.isna(val) for val in [current_bar["open"], current_bar["close"], current_bar["high"], current_bar["low"],
                                        prev_bar["open"], prev_bar["close"], prev_bar["high"], prev_bar["low"]]):
            return patterns

        if (
            current_bar["open"] < prev_bar["close"]
            and current_bar["close"] > prev_bar["open"]
            and current_bar["close"] > current_bar["open"]
            and prev_bar["close"] < prev_bar["open"]
        ):
            patterns.iloc[i] = "Bullish Engulfing"
        elif (
            current_bar["open"] > prev_bar["close"]
            and current_bar["close"] < prev_bar["open"]
            and current_bar["close"] < current_bar["open"]
            and prev_bar["close"] > prev_bar["open"]
        ):
            patterns.iloc[i] = "Bearish Engulfing"
        elif (
            current_bar["close"] > current_bar["open"]
            and abs(current_bar["close"] - current_bar["open"])
            <= (current_bar["high"] - current_bar["low"]) * 0.3
            and (current_bar["open"] - current_bar["low"])
            >= 2 * abs(current_bar["close"] - current_bar["open"])
            and (current_bar["high"] - current_bar["close"])
            <= 0.5 * abs(current_bar["close"] - current_bar["open"])
        ):
            patterns.iloc[i] = "Bullish Hammer"
        elif (
            current_bar["close"] < current_bar["open"]
            and abs(current_bar["close"] - current_bar["open"])
            <= (current_bar["high"] - current_bar["low"]) * 0.3
            and (current_bar["high"] - current_bar["open"])
            >= 2 * abs(current_bar["close"] - current_bar["open"])
            and (current_bar["close"] - current_bar["low"])
            <= 0.5 * abs(current_bar["close"] - current_bar["open"])
        ):
            patterns.iloc[i] = "Bearish Shooting Star"

        return patterns


class TradingAnalyzer:
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
        self.fib_levels: dict[str, Decimal] = {}
        self.weights = config["weight_sets"]["default_scalping"]
        self.indicator_settings = config["indicator_settings"]
        self.tech_indicators = TechnicalIndicators(self.df, self.indicator_settings, self.logger, self.symbol)

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
        if len(self.df) < min_data_points:
            self.logger.debug(
                f"[{self.symbol}] Skipping indicator '{name}': Not enough data. Need {min_data_points}, have {len(self.df)}."
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
                    f"{NEON_YELLOW}[{self.symbol}] Indicator '{name}' returned empty or None after calculation. Not enough valid data?{RESET}"
                )
                return None
            return result
        except Exception as e:
            self.logger.error(
                f"{NEON_RED}[{self.symbol}] Error calculating indicator '{name}': {e}{RESET}"
            )
            return None

    def _calculate_all_indicators(self) -> None:
        self.logger.debug(f"[{self.symbol}] Calculating technical indicators...\n")

        isd = self.indicator_settings
        cfg_indicators = self.config["indicators"]

        if cfg_indicators.get("sma_10", False):
            self.df["SMA_10"] = self._safe_calculate(
                lambda: self.df["close"].rolling(window=isd["sma_short_period"]).mean(),
                "SMA_10",
                min_data_points=isd["sma_short_period"],
            )
            if self.df["SMA_10"] is not None: self.indicator_values["SMA_10"] = self.df["SMA_10"].iloc[-1]
        if cfg_indicators.get("sma_trend_filter", False):
            self.df["SMA_Long"] = self._safe_calculate(
                lambda: self.df["close"].rolling(window=isd["sma_long_period"]).mean(),
                "SMA_Long",
                min_data_points=isd["sma_long_period"],
            )
            if self.df["SMA_Long"] is not None: self.indicator_values["SMA_Long"] = self.df["SMA_Long"].iloc[-1]

        if cfg_indicators.get("ema_alignment", False):
            self.df["EMA_Short"] = self._safe_calculate(
                lambda: self.df["close"].ewm(span=isd["ema_short_period"], adjust=False).mean(),
                "EMA_Short", min_data_points=isd["ema_short_period"])
            self.df["EMA_Long"] = self._safe_calculate(
                lambda: self.df["close"].ewm(span=isd["ema_long_period"], adjust=False).mean(),
                "EMA_Long", min_data_points=isd["ema_long_period"])
            if self.df["EMA_Short"] is not None: self.indicator_values["EMA_Short"] = self.df["EMA_Short"].iloc[-1]
            if self.df["EMA_Long"] is not None: self.indicator_values["EMA_Long"] = self.df["EMA_Long"].iloc[-1]

        self.df["TR"] = self._safe_calculate(self.tech_indicators.calculate_true_range, "TR", min_data_points=MIN_DATA_POINTS_TR)
        self.df["ATR"] = self._safe_calculate(
            lambda: self.df["TR"].ewm(span=isd["atr_period"], adjust=False).mean(),
            "ATR", min_data_points=isd["atr_period"])
        if self.df["ATR"] is not None: self.indicator_values["ATR"] = self.df["ATR"].iloc[-1]

        if cfg_indicators.get("rsi", False):
            self.df["RSI"] = self._safe_calculate(self.tech_indicators.calculate_rsi, "RSI",
                min_data_points=isd["rsi_period"] + 1, period=isd["rsi_period"])
            if self.df["RSI"] is not None: self.indicator_values["RSI"] = self.df["RSI"].iloc[-1]

        if cfg_indicators.get("stoch_rsi", False):
            stoch_rsi_k, stoch_rsi_d = self._safe_calculate(self.tech_indicators.calculate_stoch_rsi, "StochRSI",
                min_data_points=isd["stoch_rsi_period"] + isd["stoch_k_period"] + isd["stoch_d_period"],
                period=isd["stoch_rsi_period"], k_period=isd["stoch_k_period"], d_period=isd["stoch_d_period"])
            if stoch_rsi_k is not None: self.df["StochRSI_K"] = stoch_rsi_k; self.indicator_values["StochRSI_K"] = stoch_rsi_k.iloc[-1]
            if stoch_rsi_d is not None: self.df["StochRSI_D"] = stoch_rsi_d; self.indicator_values["StochRSI_D"] = stoch_rsi_d.iloc[-1]

        if cfg_indicators.get("bollinger_bands", False):
            bb_upper, bb_middle, bb_lower = self._safe_calculate(self.tech_indicators.calculate_bollinger_bands, "BollingerBands",
                min_data_points=isd["bollinger_bands_period"], period=isd["bollinger_bands_period"], std_dev=isd["bollinger_bands_std_dev"])
            if bb_upper is not None: self.df["BB_Upper"] = bb_upper; self.indicator_values["BB_Upper"] = bb_upper.iloc[-1]
            if bb_middle is not None: self.df["BB_Middle"] = bb_middle; self.indicator_values["BB_Middle"] = bb_middle.iloc[-1]
            if bb_lower is not None: self.df["BB_Lower"] = bb_lower; self.indicator_values["BB_Lower"] = bb_lower.iloc[-1]

        if cfg_indicators.get("cci", False):
            self.df["CCI"] = self._safe_calculate(self.tech_indicators.calculate_cci, "CCI",
                min_data_points=isd["cci_period"], period=isd["cci_period"])
            if self.df["CCI"] is not None: self.indicator_values["CCI"] = self.df["CCI"].iloc[-1]

        if cfg_indicators.get("wr", False):
            self.df["WR"] = self._safe_calculate(self.tech_indicators.calculate_williams_r, "WR",
                min_data_points=isd["williams_r_period"], period=isd["williams_r_period"])
            if self.df["WR"] is not None: self.indicator_values["WR"] = self.df["WR"].iloc[-1]

        if cfg_indicators.get("mfi", False):
            self.df["MFI"] = self._safe_calculate(self.tech_indicators.calculate_mfi, "MFI",
                min_data_points=isd["mfi_period"] + 1, period=isd["mfi_period"])
            if self.df["MFI"] is not None: self.indicator_values["MFI"] = self.df["MFI"].iloc[-1]

        if cfg_indicators.get("obv", False):
            obv_val, obv_ema = self._safe_calculate(self.tech_indicators.calculate_obv, "OBV",
                min_data_points=isd["obv_ema_period"], ema_period=isd["obv_ema_period"])
            if obv_val is not None: self.df["OBV"] = obv_val; self.indicator_values["OBV"] = obv_val.iloc[-1]
            if obv_ema is not None: self.df["OBV_EMA"] = obv_ema; self.indicator_values["OBV_EMA"] = obv_ema.iloc[-1]

        if cfg_indicators.get("cmf", False):
            cmf_val = self._safe_calculate(self.tech_indicators.calculate_cmf, "CMF",
                min_data_points=isd["cmf_period"], period=isd["cmf_period"])
            if cmf_val is not None: self.df["CMF"] = cmf_val; self.indicator_values["CMF"] = cmf_val.iloc[-1]

        if cfg_indicators.get("ichimoku_cloud", False):
            tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span = self._safe_calculate(
                self.tech_indicators.calculate_ichimoku_cloud, "IchimokuCloud",
                min_data_points=max(isd["ichimoku_tenkan_period"], isd["ichimoku_kijun_period"], isd["ichimoku_senkou_span_b_period"]) + isd["ichimoku_chikou_span_offset"],
                tenkan_period=isd["ichimoku_tenkan_period"], kijun_period=isd["ichimoku_kijun_period"],
                senkou_span_b_period=isd["ichimoku_senkou_span_b_period"], chikou_span_offset=isd["ichimoku_chikou_span_offset"])
            if tenkan_sen is not None: self.df["Tenkan_Sen"] = tenkan_sen; self.indicator_values["Tenkan_Sen"] = tenkan_sen.iloc[-1]
            if kijun_sen is not None: self.df["Kijun_Sen"] = kijun_sen; self.indicator_values["Kijun_Sen"] = kijun_sen.iloc[-1]
            if senkou_span_a is not None: self.df["Senkou_Span_A"] = senkou_span_a; self.indicator_values["Senkou_Span_A"] = senkou_span_a.iloc[-1]
            if senkou_span_b is not None: self.df["Senkou_Span_B"] = senkou_span_b; self.indicator_values["Senkou_Span_B"] = senkou_span_b.iloc[-1]
            if chikou_span is not None: self.df["Chikou_Span"] = chikou_span; self.indicator_values["Chikou_Span"] = chikou_span.fillna(0).iloc[-1]

        if cfg_indicators.get("psar", False):
            psar_val, psar_dir = self._safe_calculate(self.tech_indicators.calculate_psar, "PSAR",
                min_data_points=MIN_DATA_POINTS_PSAR, acceleration=isd["psar_acceleration"], max_acceleration=isd["psar_max_acceleration"])
            if psar_val is not None: self.df["PSAR_Val"] = psar_val; self.indicator_values["PSAR_Val"] = psar_val.iloc[-1]
            if psar_dir is not None: self.df["PSAR_Dir"] = psar_dir; self.indicator_values["PSAR_Dir"] = psar_dir.iloc[-1]

        if cfg_indicators.get("vwap", False):
            self.df["VWAP"] = self._safe_calculate(self.tech_indicators.calculate_vwap, "VWAP", min_data_points=1)
            if self.df["VWAP"] is not None: self.indicator_values["VWAP"] = self.df["VWAP"].iloc[-1]

        if cfg_indicators.get("ehlers_supertrend", False):
            st_fast_result = self._safe_calculate(self.tech_indicators.calculate_ehlers_supertrend, "EhlersSuperTrendFast",
                min_data_points=isd["ehlers_fast_period"] * 3, period=isd["ehlers_fast_period"], multiplier=isd["ehlers_fast_multiplier"])
            if st_fast_result is not None and not st_fast_result.empty:
                self.df["ST_Fast_Dir"] = st_fast_result["direction"]
                self.df["ST_Fast_Val"] = st_fast_result["supertrend"]
                self.indicator_values["ST_Fast_Dir"] = st_fast_result["direction"].iloc[-1]
                self.indicator_values["ST_Fast_Val"] = st_fast_result["supertrend"].iloc[-1]
            st_slow_result = self._safe_calculate(self.tech_indicators.calculate_ehlers_supertrend, "EhlersSuperTrendSlow",
                min_data_points=isd["ehlers_slow_period"] * 3, period=isd["ehlers_slow_period"], multiplier=isd["ehlers_slow_multiplier"])
            if st_slow_result is not None and not st_slow_result.empty:
                self.df["ST_Slow_Dir"] = st_slow_result["direction"]
                self.df["ST_Slow_Val"] = st_slow_result["supertrend"]
                self.indicator_values["ST_Slow_Dir"] = st_slow_result["direction"].iloc[-1]
                self.indicator_values["ST_Slow_Val"] = st_slow_result["supertrend"].iloc[-1]

        if cfg_indicators.get("macd", False):
            macd_line, signal_line, histogram = self._safe_calculate(self.tech_indicators.calculate_macd, "MACD",
                min_data_points=isd["macd_slow_period"] + isd["macd_signal_period"], fast_period=isd["macd_fast_period"],
                slow_period=isd["macd_slow_period"], signal_period=isd["macd_signal_period"])
            if macd_line is not None: self.df["MACD_Line"] = macd_line; self.indicator_values["MACD_Line"] = macd_line.iloc[-1]
            if signal_line is not None: self.df["MACD_Signal"] = signal_line; self.indicator_values["MACD_Signal"] = signal_line.iloc[-1]
            if histogram is not None: self.df["MACD_Hist"] = histogram; self.indicator_values["MACD_Hist"] = histogram.iloc[-1]

        if cfg_indicators.get("adx", False):
            adx_val, plus_di, minus_di = self._safe_calculate(self.tech_indicators.calculate_adx, "ADX",
                min_data_points=isd["adx_period"] * 2, period=isd["adx_period"])
            if adx_val is not None: self.df["ADX"] = adx_val; self.indicator_values["ADX"] = adx_val.iloc[-1]
            if plus_di is not None: self.df["PlusDI"] = plus_di; self.indicator_values["PlusDI"] = plus_di.iloc[-1]
            if minus_di is not None: self.df["MinusDI"] = minus_di; self.indicator_values["MinusDI"] = minus_di.iloc[-1]

        if cfg_indicators.get("volatility_index", False):
            self.df["Volatility_Index"] = self._safe_calculate(self.tech_indicators.calculate_volatility_index, "Volatility_Index",
                min_data_points=isd["volatility_index_period"], period=isd["volatility_index_period"])
            if self.df["Volatility_Index"] is not None: self.indicator_values["Volatility_Index"] = self.df["Volatility_Index"].iloc[-1]

        if cfg_indicators.get("vwma", False):
            self.df["VWMA"] = self._safe_calculate(self.tech_indicators.calculate_vwma, "VWMA",
                min_data_points=isd["vwma_period"], period=isd["vwma_period"])
            if self.df["VWMA"] is not None: self.indicator_values["VWMA"] = self.df["VWMA"].iloc[-1]

        if cfg_indicators.get("volume_delta", False):
            self.df["Volume_Delta"] = self._safe_calculate(self.tech_indicators.calculate_volume_delta, "Volume_Delta",
                min_data_points=isd["volume_delta_period"], period=isd["volume_delta_period"])
            if self.df["Volume_Delta"] is not None: self.indicator_values["Volume_Delta"] = self.df["Volume_Delta"].iloc[-1]

        if cfg_indicators.get("kaufman_ama", False):
            self.df["Kaufman_AMA"] = self._safe_calculate(self.tech_indicators.calculate_kaufman_ama, "Kaufman_AMA",
                min_data_points=isd["kama_period"] + isd["kama_slow_period"], period=isd["kama_period"],
                fast_period=isd["kama_fast_period"], slow_period=isd["kama_slow_period"])
            if self.df["Kaufman_AMA"] is not None: self.indicator_values["Kaufman_AMA"] = self.df["Kaufman_AMA"].iloc[-1]

        if cfg_indicators.get("relative_volume", False):
            self.df["Relative_Volume"] = self._safe_calculate(self.tech_indicators.calculate_relative_volume, "Relative_Volume",
                min_data_points=isd["relative_volume_period"], period=isd["relative_volume_period"])
            if self.df["Relative_Volume"] is not None: self.indicator_values["Relative_Volume"] = self.df["Relative_Volume"].iloc[-1]

        if cfg_indicators.get("market_structure", False):
            ms_trend = self._safe_calculate(self.tech_indicators.calculate_market_structure, "Market_Structure",
                min_data_points=isd["market_structure_lookback_period"] * 2, lookback_period=isd["market_structure_lookback_period"])
            if ms_trend is not None: self.df["Market_Structure_Trend"] = ms_trend; self.indicator_values["Market_Structure_Trend"] = ms_trend.iloc[-1]

        if cfg_indicators.get("dema", False):
            self.df["DEMA"] = self._safe_calculate(self.tech_indicators.calculate_dema, "DEMA",
                min_data_points=2 * isd["dema_period"], series=self.df["close"], period=isd["dema_period"])
            if self.df["DEMA"] is not None: self.indicator_values["DEMA"] = self.df["DEMA"].iloc[-1]

        if cfg_indicators.get("keltner_channels", False):
            kc_upper, kc_middle, kc_lower = self._safe_calculate(self.tech_indicators.calculate_keltner_channels, "KeltnerChannels",
                min_data_points=isd["keltner_period"] + isd["atr_period"], period=isd["keltner_period"],
                atr_multiplier=isd["keltner_atr_multiplier"], atr_period=isd["atr_period"])
            if kc_upper is not None: self.df["Keltner_Upper"] = kc_upper; self.indicator_values["Keltner_Upper"] = kc_upper.iloc[-1]
            if kc_middle is not None: self.df["Keltner_Middle"] = kc_middle; self.indicator_values["Keltner_Middle"] = kc_middle.iloc[-1]
            if kc_lower is not None: self.df["Keltner_Lower"] = kc_lower; self.indicator_values["Keltner_Lower"] = kc_lower.iloc[-1]

        if cfg_indicators.get("roc", False):
            self.df["ROC"] = self._safe_calculate(self.tech_indicators.calculate_roc, "ROC",
                min_data_points=isd["roc_period"] + 1, period=isd["roc_period"])
            if self.df["ROC"] is not None: self.indicator_values["ROC"] = self.df["ROC"].iloc[-1]

        if cfg_indicators.get("candlestick_patterns", False):
            patterns = self._safe_calculate(self.tech_indicators.detect_candlestick_patterns, "Candlestick_Patterns",
                min_data_points=MIN_CANDLESTICK_PATTERNS_BARS)
            if patterns is not None: self.df["Candlestick_Pattern"] = patterns; self.indicator_values["Candlestick_Pattern"] = patterns.iloc[-1]

        initial_len = len(self.df)
        self.df.dropna(subset=["close"], inplace=True)
        self.df.fillna(0, inplace=True)

        if len(self.df) < initial_len:
            self.logger.debug(f"Dropped {initial_len - len(self.df)} rows with NaNs after indicator calculations.")
        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] DataFrame is empty after calculating all indicators and dropping NaNs.{RESET}"
            )
        else:
            self.logger.debug(f"[{self.symbol}] Indicators calculated. Final DataFrame size: {len(self.df)}")

    def calculate_fibonacci_levels(self) -> None:
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
        self.logger.debug(
            f"[{self.symbol}] Calculated Fibonacci levels: {self.fib_levels}"
        )

    def calculate_fibonacci_pivot_points(self) -> None:
        if self.df.empty or len(self.df) < 2:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] DataFrame is too short for Fibonacci Pivot Points calculation.{RESET}"
            )
            return

        prev_high = self.df["high"].iloc[-2]
        prev_low = self.df["low"].iloc[-2]
        prev_close = self.df["close"].iloc[-2]

        pivot = (prev_high + prev_low + prev_close) / 3

        r1 = pivot + (prev_high - prev_low) * 0.382
        r2 = pivot + (prev_high - prev_low) * 0.618
        s1 = pivot - (prev_high - prev_low) * 0.382
        s2 = pivot - (prev_high - prev_low) * 0.618

        price_precision_str = (
            "0." + "0" * (self.config["trade_management"]["price_precision"] - 1) + "1"
        )
        self.indicator_values["Pivot"] = Decimal(str(pivot)).quantize(
            Decimal(price_precision_str), rounding=ROUND_DOWN
        )
        self.indicator_values["R1"] = Decimal(str(r1)).quantize(
            Decimal(price_precision_str), rounding=ROUND_DOWN
        )
        self.indicator_values["R2"] = Decimal(str(r2)).quantize(
            Decimal(price_precision_str), rounding=ROUND_DOWN
        )
        self.indicator_values["S1"] = Decimal(str(s1)).quantize(
            Decimal(price_precision_str), rounding=ROUND_DOWN
        )
        self.indicator_values["S2"] = Decimal(str(s2)).quantize(
            Decimal(price_precision_str), rounding=ROUND_DOWN
        )

        self.logger.debug(f"[{self.symbol}] Calculated Fibonacci Pivot Points.")

    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        return self.indicator_values.get(key, default)

    def _check_orderbook(self, orderbook_data: dict) -> float:
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

    def calculate_support_resistance_from_orderbook(self, orderbook_data: dict) -> None:
        bids = orderbook_data.get("b", [])
        asks = orderbook_data.get("a", [])

        max_bid_volume = Decimal("0")
        support_level = Decimal("0")
        for bid_price, bid_volume in bids:
            bid_volume_decimal = Decimal(bid_volume)
            if bid_volume_decimal > max_bid_volume:
                max_bid_volume = bid_volume_decimal
                support_level = Decimal(bid_price)

        max_ask_volume = Decimal("0")
        resistance_level = Decimal("0")
        for ask_price, ask_volume in asks:
            ask_volume_decimal = Decimal(ask_volume)
            if ask_volume_decimal > max_ask_volume:
                max_ask_volume = ask_volume_decimal
                resistance_level = Decimal(ask_price)

        price_precision_str = (
            "0."
            + "0" * (self.config["trade_management"]["price_precision"] - 1)
            + "1"
        )
        if support_level > 0:
            self.indicator_values["Support_Level"] = support_level.quantize(
                Decimal(price_precision_str), rounding=ROUND_DOWN
            )
            self.logger.debug(
                f"[{self.symbol}] Identified Support Level: {support_level} (Volume: {max_bid_volume})"
            )
        if resistance_level > 0:
            self.indicator_values["Resistance_Level"] = resistance_level.quantize(
                Decimal(price_precision_str), rounding=ROUND_DOWN
            )
            self.logger.debug(
                f"[{self.symbol}] Identified Resistance Level: {resistance_level} (Volume: {max_ask_volume})"
            )

    def _get_mtf_trend(self, higher_tf_df: pd.DataFrame, indicator_type: str) -> str:
        if higher_tf_df.empty:
            return "UNKNOWN"

        last_close = higher_tf_df["close"].iloc[-1]
        period = self.config["mtf_analysis"]["trend_period"]

        temp_tech_indicators = TechnicalIndicators(higher_tf_df, self.indicator_settings, self.logger, self.symbol)

        if indicator_type == "sma":
            if len(higher_tf_df) < period:
                self.logger.debug(f"[{self.symbol}] MTF SMA: Not enough data for {period} period. Have {len(higher_tf_df)}.")
                return "UNKNOWN"
            sma = (higher_tf_df["close"].rolling(window=period, min_periods=period).mean().iloc[-1])
            if last_close > sma: return "UP"
            if last_close < sma: return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ema":
            if len(higher_tf_df) < period:
                self.logger.debug(f"[{self.symbol}] MTF EMA: Not enough data for {period} period. Have {len(higher_tf_df)}.")
                return "UNKNOWN"
            ema = (higher_tf_df["close"].ewm(span=period, adjust=False, min_periods=period).mean().iloc[-1])
            if last_close > ema: return "UP"
            if last_close < ema: return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ehlers_supertrend":
            st_result = temp_tech_indicators.calculate_ehlers_supertrend(
                period=self.indicator_settings["ehlers_slow_period"],
                multiplier=self.indicator_settings["ehlers_slow_multiplier"],
            )
            if st_result is not None and not st_result.empty:
                st_dir = st_result["direction"].iloc[-1]
                if st_dir == 1: return "UP"
                if st_dir == -1: return "DOWN"
            return "UNKNOWN"
        return "UNKNOWN"

    def _score_adx(self, trend_strength_multiplier: float) -> tuple[float, dict]:
        adx_contrib = 0.0
        signal_breakdown_contrib = {}
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
                        trend_strength_multiplier *= 1.2
                    elif minus_di > plus_di:
                        adx_contrib = -adx_weight
                        self.logger.debug(f"ADX: Strong SELL trend (ADX > {ADX_STRONG_TREND_THRESHOLD}, -DI > +DI).")
                        trend_strength_multiplier *= 1.2
                elif adx_val < ADX_WEAK_TREND_THRESHOLD:
                    self.logger.debug(f"ADX: Weak trend (ADX < {ADX_WEAK_TREND_THRESHOLD}). Neutral signal.")
                    trend_strength_multiplier *= 0.8
                signal_breakdown_contrib["ADX"] = adx_contrib
        return adx_contrib, {"trend_strength_multiplier": trend_strength_multiplier, "breakdown": signal_breakdown_contrib}

    def _score_ema_alignment(self, current_close: Decimal, trend_multiplier: float) -> tuple[float, dict]:
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

    def _score_sma_trend_filter(self, current_close: Decimal) -> tuple[float, dict]:
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

    def _score_momentum_indicators(self) -> tuple[float, dict]:
        momentum_contrib = 0.0
        signal_breakdown_contrib = {}
        active_indicators = self.config["indicators"]
        isd = self.indicator_settings
        momentum_weight = self.weights.get("momentum_rsi_stoch_cci_wr_mfi", 0)

        if active_indicators.get("rsi", False):
            rsi = self._get_indicator_value("RSI")
            if not pd.isna(rsi):
                if rsi < isd["rsi_oversold"]:
                    momentum_contrib += momentum_weight * 0.5
                elif rsi > isd["rsi_overbought"]:
                    momentum_contrib -= momentum_weight * 0.5
                signal_breakdown_contrib["RSI"] = momentum_contrib # This is partial for RSI, combined later
        
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
                elif stoch_k > stoch_d and stoch_k < STOCH_RSI_MID_POINT:
                    stoch_contrib = momentum_weight * 0.2
                elif stoch_k < stoch_d and stoch_k > STOCH_RSI_MID_POINT:
                    stoch_contrib = -momentum_weight * 0.2
                momentum_contrib += stoch_contrib
                signal_breakdown_contrib["StochRSI Crossover"] = stoch_contrib

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
    
    def _score_bollinger_bands(self, current_close: Decimal) -> tuple[float, dict]:
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

    def _score_vwap(self, current_close: Decimal, prev_close: Decimal) -> tuple[float, dict]:
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

    def _score_psar(self, current_close: Decimal, prev_close: Decimal) -> tuple[float, dict]:
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

    def _score_orderbook_imbalance(self, current_price: Decimal, orderbook_data: dict | None) -> tuple[float, dict]:
        imbalance_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("orderbook_imbalance", False) and orderbook_data:
            imbalance = self._check_orderbook(orderbook_data)
            imbalance_contrib = imbalance * self.weights.get("orderbook_imbalance", 0)
            signal_breakdown_contrib["Orderbook Imbalance"] = imbalance_contrib
            self.calculate_support_resistance_from_orderbook(orderbook_data)
        return imbalance_contrib, signal_breakdown_contrib

    def _score_fibonacci_levels(self, current_close: Decimal, prev_close: Decimal) -> tuple[float, dict]:
        fib_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("fibonacci_levels", False) and self.fib_levels:
            for level_name, level_price in self.fib_levels.items():
                if level_name not in ["0.0%", "100.0%"] and current_close > Decimal("0") and abs(
                    (current_close - level_price) / current_close
                ) < Decimal("0.001"):
                    self.logger.debug(f"Price near Fibonacci level {level_name}: {level_price}")
                    if len(self.df) > 1:
                        if current_close > prev_close and current_close > level_price:
                            fib_contrib += self.weights.get("fibonacci_levels", 0) * 0.1
                        elif current_close < prev_close and current_close < level_price:
                            fib_contrib -= self.weights.get("fibonacci_levels", 0) * 0.1
            signal_breakdown_contrib["Fibonacci Levels"] = fib_contrib
        return fib_contrib, signal_breakdown_contrib

    def _score_fibonacci_pivot_points(self, current_close: Decimal, prev_close: Decimal) -> tuple[float, dict]:
        fib_pivot_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("fibonacci_pivot_points", False):
            pivot = self._get_indicator_value("Pivot")
            r1 = self._get_indicator_value("R1")
            r2 = self._get_indicator_value("R2")
            s1 = self._get_indicator_value("S1")
            s2 = self._get_indicator_value("S2")

            if not any(pd.isna(val) for val in [pivot, r1, r2, s1, s2]):
                weight = self.weights.get("fibonacci_pivot_points_confluence", 0)

                if current_close > r1 and prev_close <= r1:
                    fib_pivot_contrib += weight * 0.5
                    signal_breakdown_contrib["Fibonacci R1 Breakout"] = weight * 0.5
                elif current_close > r2 and prev_close <= r2:
                    fib_pivot_contrib += weight * 1.0
                    signal_breakdown_contrib["Fibonacci R2 Breakout"] = weight * 1.0
                elif current_close > pivot and prev_close <= pivot:
                    fib_pivot_contrib += weight * 0.2
                    signal_breakdown_contrib["Fibonacci Pivot Breakout"] = weight * 0.2

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

    def _score_ehlers_supertrend(self, trend_multiplier: float) -> tuple[float, dict]:
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
                if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1:
                    st_contrib = weight
                    self.logger.debug("Ehlers SuperTrend: Strong BUY signal (fast flip aligned with slow trend).")
                elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1:
                    st_contrib = -weight
                    self.logger.debug("Ehlers SuperTrend: Strong SELL signal (fast flip aligned with slow trend).")
                elif st_slow_dir == 1 and st_fast_dir == 1:
                    st_contrib = weight * 0.3
                elif st_slow_dir == -1 and st_fast_dir == -1:
                    st_contrib = -weight * 0.3
                signal_breakdown_contrib["Ehlers SuperTrend"] = st_contrib
        return st_contrib, signal_breakdown_contrib

    def _score_macd(self, trend_multiplier: float) -> tuple[float, dict]:
        macd_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("macd", False):
            macd_line = self._get_indicator_value("MACD_Line")
            signal_line = self._get_indicator_value("MACD_Signal")
            histogram = self._get_indicator_value("MACD_Hist")
            weight = self.weights.get("macd_alignment", 0.0) * trend_multiplier

            if not pd.isna(macd_line) and not pd.isna(signal_line) and not pd.isna(histogram) and len(self.df) > 1:
                if macd_line > signal_line and self.df["MACD_Line"].iloc[-2] <= self.df["MACD_Signal"].iloc[-2]:
                    macd_contrib = weight
                    self.logger.debug("MACD: BUY signal (MACD line crossed above Signal line).")
                elif macd_line < signal_line and self.df["MACD_Line"].iloc[-2] >= self.df["MACD_Signal"].iloc[-2]:
                    macd_contrib = -weight
                    self.logger.debug("MACD: SELL signal (MACD line crossed below Signal line).")
                elif histogram > 0 and self.df["MACD_Hist"].iloc[-2] < 0:
                    macd_contrib = weight * 0.2
                elif histogram < 0 and self.df["MACD_Hist"].iloc[-2] > 0:
                    macd_contrib = -weight * 0.2
                signal_breakdown_contrib["MACD"] = macd_contrib
        return macd_contrib, signal_breakdown_contrib

    def _score_ichimoku_cloud(self, current_close: Decimal) -> tuple[float, dict]:
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
                if tenkan_sen > kijun_sen and self.df["Tenkan_Sen"].iloc[-2] <= self.df["Kijun_Sen"].iloc[-2]:
                    ichimoku_contrib += weight * 0.5
                    self.logger.debug("Ichimoku: Tenkan-sen crossed above Kijun-sen (bullish).")
                elif tenkan_sen < kijun_sen and self.df["Tenkan_Sen"].iloc[-2] >= self.df["Kijun_Sen"].iloc[-2]:
                    ichimoku_contrib -= weight * 0.5
                    self.logger.debug("Ichimoku: Tenkan-sen crossed below Kijun-sen (bearish).")

                if current_close > max(senkou_span_a, senkou_span_b) and self.df["close"].iloc[-2] <= max(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]):
                    ichimoku_contrib += weight * 0.7
                    self.logger.debug("Ichimoku: Price broke above Kumo (strong bullish).")
                elif current_close < min(senkou_span_a, senkou_span_b) and self.df["close"].iloc[-2] >= min(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]):
                    ichimoku_contrib -= weight * 0.7
                    self.logger.debug("Ichimoku: Price broke below Kumo (strong bearish).")

                if chikou_span > current_close and self.df["Chikou_Span"].iloc[-2] <= self.df["close"].iloc[-2]:
                    ichimoku_contrib += weight * 0.3
                    self.logger.debug("Ichimoku: Chikou Span crossed above price (bullish confirmation).")
                elif chikou_span < current_close and self.df["Chikou_Span"].iloc[-2] >= self.df["close"].iloc[-2]:
                    ichimoku_contrib -= weight * 0.3
                    self.logger.debug("Ichimoku: Chikou Span crossed below price (bearish confirmation).")
                signal_breakdown_contrib["Ichimoku Cloud"] = ichimoku_contrib
        return ichimoku_contrib, signal_breakdown_contrib

    def _score_obv(self) -> tuple[float, dict]:
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

                if len(self.df) > 2:
                    if obv_val > self.df["OBV"].iloc[-2] and obv_val > self.df["OBV"].iloc[-3]:
                        obv_contrib += weight * 0.2
                    elif obv_val < self.df["OBV"].iloc[-2] and obv_val < self.df["OBV"].iloc[-3]:
                        obv_contrib -= weight * 0.2
                signal_breakdown_contrib["OBV"] = obv_contrib
        return obv_contrib, signal_breakdown_contrib

    def _score_cmf(self) -> tuple[float, dict]:
        cmf_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("cmf", False):
            cmf_val = self._get_indicator_value("CMF")
            weight = self.weights.get("cmf_flow", 0.0)

            if not pd.isna(cmf_val):
                if cmf_val > 0:
                    cmf_contrib = weight * 0.5
                elif cmf_val < 0:
                    cmf_contrib = -weight * 0.5

                if len(self.df) > 2:
                    if cmf_val > self.df["CMF"].iloc[-2] and cmf_val > self.df["CMF"].iloc[-3]:
                        cmf_contrib += weight * 0.3
                    elif cmf_val < self.df["CMF"].iloc[-2] and cmf_val < self.df["CMF"].iloc[-3]:
                        cmf_contrib -= weight * 0.3
                signal_breakdown_contrib["CMF"] = cmf_contrib
        return cmf_contrib, signal_breakdown_contrib

    def _score_volatility_index(self, signal_score_current: float) -> tuple[float, dict]:
        vol_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("volatility_index", False):
            vol_idx = self._get_indicator_value("Volatility_Index")
            weight = self.weights.get("volatility_index_signal", 0.0)
            if not pd.isna(vol_idx):
                if len(self.df) > 2 and "Volatility_Index" in self.df.columns:
                    prev_vol_idx = self.df["Volatility_Index"].iloc[-2]
                    prev_prev_vol_idx = self.df["Volatility_Index"].iloc[-3]

                    if vol_idx > prev_vol_idx > prev_prev_vol_idx:
                        if signal_score_current > 0:
                            vol_contrib = weight * 0.2
                        elif signal_score_current < 0:
                            vol_contrib = -weight * 0.2
                    elif vol_idx < prev_vol_idx < prev_prev_vol_idx:
                        if abs(signal_score_current) > 0:
                            vol_contrib = signal_score_current * -0.2
                signal_breakdown_contrib["Volatility Index"] = vol_contrib
        return vol_contrib, signal_breakdown_contrib

    def _score_vwma_cross(self, current_close: Decimal, prev_close: Decimal) -> tuple[float, dict]:
        vwma_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("vwma", False):
            vwma = self._get_indicator_value("VWMA")
            weight = self.weights.get("vwma_cross", 0.0)
            if not pd.isna(vwma) and len(self.df) > 1 and "VWMA" in self.df.columns:
                prev_vwma = self.df["VWMA"].iloc[-2]
                if current_close > vwma and prev_close <= prev_vwma:
                    vwma_contrib = weight
                    self.logger.debug("VWMA: Bullish crossover (price above VWMA).")
                elif current_close < vwma and prev_close >= prev_vwma:
                    vwma_contrib = -weight
                    self.logger.debug("VWMA: Bearish crossover (price below VWMA).")
                signal_breakdown_contrib["VWMA Cross"] = vwma_contrib
        return vwma_contrib, signal_breakdown_contrib

    def _score_volume_delta(self) -> tuple[float, dict]:
        vol_delta_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("volume_delta", False):
            volume_delta = self._get_indicator_value("Volume_Delta")
            volume_delta_threshold = self.indicator_settings["volume_delta_threshold"]
            weight = self.weights.get("volume_delta_signal", 0.0)

            if not pd.isna(volume_delta):
                if volume_delta > volume_delta_threshold:
                    vol_delta_contrib = weight
                    self.logger.debug("Volume Delta: Strong buying pressure detected.")
                elif volume_delta < -volume_delta_threshold:
                    vol_delta_contrib = -weight
                    self.logger.debug("Volume Delta: Strong selling pressure detected.")
                elif volume_delta > 0:
                    vol_delta_contrib = weight * 0.3
                elif volume_delta < 0:
                    vol_delta_contrib = -weight * 0.3
                signal_breakdown_contrib["Volume Delta"] = vol_delta_contrib
        return vol_delta_contrib, signal_breakdown_contrib

    def _score_kaufman_ama_cross(self, current_close: Decimal, prev_close: Decimal) -> tuple[float, dict]:
        kama_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("kaufman_ama", False):
            kama = self._get_indicator_value("Kaufman_AMA")
            weight = self.weights.get("kaufman_ama_cross", 0.0)
            if not pd.isna(kama) and len(self.df) > 1 and "Kaufman_AMA" in self.df.columns:
                prev_kama = self.df["Kaufman_AMA"].iloc[-2]
                if current_close > kama and prev_close <= prev_kama:
                    kama_contrib = weight
                    self.logger.debug("KAMA: Bullish crossover (price above KAMA).")
                elif current_close < kama and prev_close >= prev_kama:
                    kama_contrib = -weight
                    self.logger.debug("KAMA: Bearish crossover (price below KAMA).")
                signal_breakdown_contrib["Kaufman AMA Cross"] = kama_contrib
        return kama_contrib, signal_breakdown_contrib

    def _score_relative_volume(self, current_close: Decimal, prev_close: Decimal) -> tuple[float, dict]:
        rv_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("relative_volume", False):
            relative_volume = self._get_indicator_value("Relative_Volume")
            volume_threshold = self.indicator_settings["relative_volume_threshold"]
            weight = self.weights.get("relative_volume_confirmation", 0.0)

            if not pd.isna(relative_volume):
                if relative_volume >= volume_threshold:
                    if current_close > prev_close:
                        rv_contrib = weight
                        self.logger.debug(f"Volume: High relative bullish volume ({relative_volume:.2f}x average).")
                    elif current_close < prev_close:
                        rv_contrib = -weight
                        self.logger.debug(f"Volume: High relative bearish volume ({relative_volume:.2f}x average).")
                signal_breakdown_contrib["Relative Volume"] = rv_contrib
        return rv_contrib, signal_breakdown_contrib

    def _score_market_structure(self) -> tuple[float, dict]:
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

    def _score_dema_crossover(self) -> tuple[float, dict]:
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

    def _score_keltner_channels(self, current_close: Decimal, prev_close: Decimal) -> tuple[float, dict]:
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

    def _score_roc_signals(self) -> tuple[float, dict]:
        roc_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("roc", False):
            roc = self._get_indicator_value("ROC")
            weight = self.weights.get("roc_signal", 0.0)
            isd = self.indicator_settings

            if not pd.isna(roc):
                if roc < isd["roc_oversold"]:
                    roc_contrib += weight * 0.7
                    self.logger.debug(f"ROC: Oversold ({roc:.2f}), potential bounce.")
                elif roc > isd["roc_overbought"]:
                    roc_contrib -= weight * 0.7
                    self.logger.debug(f"ROC: Overbought ({roc:.2f}), potential pullback.")

                if len(self.df) > 1 and "ROC" in self.df.columns:
                    prev_roc = self.df["ROC"].iloc[-2]
                    if roc > 0 and prev_roc <= 0:
                        roc_contrib += weight * 0.3
                        self.logger.debug("ROC: Bullish zero-line crossover.")
                    elif roc < 0 and prev_roc >= 0:
                        roc_contrib -= weight * 0.3
                        self.logger.debug("ROC: Bearish zero-line crossover.")
                signal_breakdown_contrib["ROC"] = roc_contrib
        return roc_contrib, signal_breakdown_contrib

    def _score_candlestick_patterns(self) -> tuple[float, dict]:
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

    def _score_mtf_confluence(self, mtf_trends: dict[str, str]) -> tuple[float, dict]:
        mtf_contribution = 0.0
        signal_breakdown_contrib = {}
        if self.config["mtf_analysis"]["enabled"] and mtf_trends:
            mtf_buy_count = sum(1 for t in mtf_trends.values() if t == "UP")
            mtf_sell_count = sum(1 for t in mtf_trends.values() if t == "DOWN")
            total_mtf_indicators = len(mtf_trends)

            mtf_weight = self.weights.get("mtf_trend_confluence", 0.0)

            if total_mtf_indicators > 0:
                if mtf_buy_count == total_mtf_indicators:
                    mtf_contribution = mtf_weight * 1.5
                    self.logger.debug(f"MTF: All {total_mtf_indicators} higher TFs are UP. Strong bullish confluence.")
                elif mtf_sell_count == total_mtf_indicators:
                    mtf_contribution = -mtf_weight * 1.5
                    self.logger.debug(f"MTF: All {total_mtf_indicators} higher TFs are DOWN. Strong bearish confluence.")
                else:
                    normalized_mtf_score = (mtf_buy_count - mtf_sell_count) / total_mtf_indicators
                    mtf_contribution = mtf_weight * normalized_mtf_score

                signal_breakdown_contrib["MTF Confluence"] = mtf_contribution
                self.logger.debug(f"MTF Confluence: Buy: {mtf_buy_count}, Sell: {mtf_sell_count}. MTF contribution: {mtf_contribution:.2f}")
        return mtf_contribution, signal_breakdown_contrib

    def generate_trading_signal(
        self,
        current_price: Decimal,
        orderbook_data: dict | None,
        mtf_trends: dict[str, str],
    ) -> tuple[str, float, dict]:
        signal_score = 0.0
        signal_breakdown: dict[str, float] = {}

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}"
            )
            return "HOLD", 0.0, {}

        current_close = Decimal(str(self.df["close"].iloc[-1]))
        prev_close = Decimal(str(self.df["close"].iloc[-2]) if len(self.df) > 1 else current_close)
        
        trend_strength_multiplier = 1.0

        adx_score, adx_info = self._score_adx(trend_strength_multiplier)
        signal_score += adx_score
        signal_breakdown.update(adx_info["breakdown"])
        trend_strength_multiplier = adx_info["trend_strength_multiplier"]

        # --- Scoring Logic ---
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
            contrib, breakdown = scorer_func(*args)
            signal_score += contrib
            signal_breakdown.update(breakdown)

        # Volatility index is scored separately as it depends on the current score
        vol_contrib, vol_breakdown = self._score_volatility_index(signal_score)
        signal_score += vol_contrib
        signal_breakdown.update(vol_breakdown)

        imbalance_score, imbalance_breakdown = self._score_orderbook_imbalance(current_price, orderbook_data)
        signal_score += imbalance_score
        signal_breakdown.update(imbalance_breakdown)

        mtf_score, mtf_breakdown = self._score_mtf_confluence(mtf_trends)
        signal_score += mtf_score
        signal_breakdown.update(mtf_breakdown)

        threshold = self.config["signal_score_threshold"]
        final_signal = "HOLD"
        if signal_score >= threshold:
            final_signal = "BUY"
        elif signal_score <= -threshold:
            final_signal = "SELL"

        self.logger.info(
            f"{NEON_YELLOW}Raw Signal Score: {signal_score:.2f}, Final Signal: {final_signal}{RESET}"
        )
        return final_signal, signal_score, signal_breakdown

    def calculate_entry_tp_sl(
        self, current_price: Decimal, atr_value: Decimal, signal: Literal["BUY", "SELL"]
    ) -> tuple[Decimal, Decimal]:
        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"])
        )
        take_profit_atr_multiple = Decimal(
            str(self.config["trade_management"]["take_profit_atr_multiple"])
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
            return Decimal("0"), Decimal("0")

        return take_profit.quantize(
            Decimal(price_precision_str), rounding=ROUND_DOWN
        ), stop_loss.quantize(Decimal(price_precision_str), rounding=ROUND_DOWN)


def display_indicator_values_and_price(
    config: dict[str, Any],
    logger: logging.Logger,
    current_price: Decimal,
    analyzer: TradingAnalyzer,
    orderbook_data: dict | None,
    mtf_trends: dict[str, str],
    signal_breakdown: dict[str, float] | None = None,
) -> None:
    logger.info(f"{NEON_BLUE}--- Current Market Data & Indicators ---{RESET}")
    logger.info(f"{NEON_GREEN}Current Price: {current_price.normalize()}{RESET}")

    if analyzer.df.empty:
        logger.warning(
            f"{NEON_YELLOW}Cannot display indicators: DataFrame is empty after calculations.{RESET}"
        )
        return

    logger.info(f"{NEON_CYAN}--- Indicator Values ---{RESET}")
    for indicator_name, value in analyzer.indicator_values.items():
        color = INDICATOR_COLORS.get(indicator_name, NEON_YELLOW)
        if isinstance(value, Decimal):
            logger.info(f"  {color}{indicator_name:<20}: {value.normalize()}{RESET}")
        elif isinstance(value, float):
            logger.info(f"  {color}{indicator_name:<20}: {value:.8f}{RESET}")
        else:
            logger.info(f"  {color}{indicator_name:<20}: {value}{RESET}")

    if analyzer.fib_levels:
        logger.info(f"{NEON_CYAN}--- Fibonacci Retracement Levels ---{RESET}")
        for level_name, level_price in analyzer.fib_levels.items():
            logger.info(
                f"  {NEON_YELLOW}{level_name:<20}: {level_price.normalize()}{RESET}"
            )

    if config["indicators"].get("fibonacci_pivot_points", False):
        if (
            "Pivot" in analyzer.indicator_values
            and "R1" in analyzer.indicator_values
            and "S1" in analyzer.indicator_values
        ):
            logger.info(f"{NEON_CYAN}--- Fibonacci Pivot Points ---{RESET}")
            logger.info(
                f"  {INDICATOR_COLORS.get('Pivot', NEON_YELLOW)}Pivot              : {analyzer.indicator_values['Pivot'].normalize()}{RESET}"
            )
            logger.info(
                f"  {INDICATOR_COLORS.get('R1', NEON_GREEN)}R1                 : {analyzer.indicator_values['R1'].normalize()}{RESET}"
            )
            logger.info(
                f"  {INDICATOR_COLORS.get('R2', NEON_GREEN)}R2                 : {analyzer.indicator_values['R2'].normalize()}{RESET}"
            )
            logger.info(
                f"  {INDICATOR_COLORS.get('S1', NEON_RED)}S1                 : {analyzer.indicator_values['S1'].normalize()}{RESET}"
            )
            logger.info(
                f"  {INDICATOR_COLORS.get('S2', NEON_RED)}S2                 : {analyzer.indicator_values['S2'].normalize()}{RESET}"
            )

    if (
        "Support_Level" in analyzer.indicator_values
        or "Resistance_Level" in analyzer.indicator_values
    ):
        logger.info(f"{NEON_CYAN}--- Orderbook S/R Levels ---{RESET}")
        if "Support_Level" in analyzer.indicator_values:
            logger.info(
                f"  {INDICATOR_COLORS.get('Support_Level', NEON_YELLOW)}Support Level     : {analyzer.indicator_values['Support_Level'].normalize()}{RESET}"
            )
        if "Resistance_Level" in analyzer.indicator_values:
            logger.info(
                f"  {INDICATOR_COLORS.get('Resistance_Level', NEON_YELLOW)}Resistance Level  : {analyzer.indicator_values['Resistance_Level'].normalize()}{RESET}"
            )

    if mtf_trends:
        logger.info(f"{NEON_CYAN}--- Multi-Timeframe Trends ---{RESET}")
        for tf_indicator, trend in mtf_trends.items():
            logger.info(f"  {NEON_YELLOW}{tf_indicator:<20}: {trend}{RESET}")

    if signal_breakdown:
        logger.info(f"{NEON_CYAN}--- Signal Score Breakdown ---{RESET}")
        sorted_breakdown = sorted(
            signal_breakdown.items(), key=lambda item: abs(item[1]), reverse=True
        )
        for indicator, contribution in sorted_breakdown:
            color = (
                Fore.GREEN
                if contribution > 0
                else (Fore.RED if contribution < 0 else Fore.YELLOW)
            )
            logger.info(f"  {color}{indicator:<25}: {contribution: .2f}{RESET}")

    logger.info(f"{NEON_PURPLE}--- Current Trend Summary ---{RESET}")
    trend_summary_lines = []

    ema_short = analyzer._get_indicator_value("EMA_Short")
    ema_long = analyzer._get_indicator_value("EMA_Long")
    if not pd.isna(ema_short) and not pd.isna(ema_long):
        if ema_short > ema_long:
            trend_summary_lines.append(f"{Fore.GREEN}EMA Cross  : ▲ Up{RESET}")
        elif ema_short < ema_long:
            trend_summary_lines.append(f"{Fore.RED}EMA Cross  : ▼ Down{RESET}")
        else:
            trend_summary_lines.append(f"{Fore.YELLOW}EMA Cross  : ↔ Sideways{RESET}")

    st_slow_dir = analyzer._get_indicator_value("ST_Slow_Dir")
    if not pd.isna(st_slow_dir):
        if st_slow_dir == 1:
            trend_summary_lines.append(f"{Fore.GREEN}SuperTrend : ▲ Up{RESET}")
        elif st_slow_dir == -1:
            trend_summary_lines.append(f"{Fore.RED}SuperTrend : ▼ Down{RESET}")
        else:
            trend_summary_lines.append(f"{Fore.YELLOW}SuperTrend : ↔ Sideways{RESET}")

    macd_hist = analyzer._get_indicator_value("MACD_Hist")
    if not pd.isna(macd_hist):
        if "MACD_Hist" in analyzer.df.columns and len(analyzer.df) > 1:
            prev_macd_hist = analyzer.df["MACD_Hist"].iloc[-2]
            if macd_hist > 0 and prev_macd_hist <= 0:
                trend_summary_lines.append(f"{Fore.GREEN}MACD Hist  : ↑ Bullish Cross{RESET}")
            elif macd_hist < 0 and prev_macd_hist >= 0:
                trend_summary_lines.append(f"{Fore.RED}MACD Hist  : ↓ Bearish Cross{RESET}")
            elif macd_hist > 0:
                trend_summary_lines.append(f"{Fore.LIGHTGREEN_EX}MACD Hist  : Above 0{RESET}")
            elif macd_hist < 0:
                trend_summary_lines.append(f"{Fore.LIGHTRED_EX}MACD Hist  : Below 0{RESET}")
        else:
            trend_summary_lines.append(f"{Fore.YELLOW}MACD Hist  : N/A{RESET}")

    adx_val = analyzer._get_indicator_value("ADX")
    if not pd.isna(adx_val):
        if adx_val > ADX_STRONG_TREND_THRESHOLD:
            plus_di = analyzer._get_indicator_value("PlusDI")
            minus_di = analyzer._get_indicator_value("MinusDI")
            if not pd.isna(plus_di) and not pd.isna(minus_di):
                if plus_di > minus_di:
                    trend_summary_lines.append(f"{Fore.LIGHTGREEN_EX}ADX Trend  : Strong Up ({adx_val:.0f}){RESET}")
                else:
                    trend_summary_lines.append(f"{Fore.LIGHTRED_EX}ADX Trend  : Strong Down ({adx_val:.0f}){RESET}")
        elif adx_val < ADX_WEAK_TREND_THRESHOLD:
            trend_summary_lines.append(f"{Fore.YELLOW}ADX Trend  : Weak/Ranging ({adx_val:.0f}){RESET}")
        else:
            trend_summary_lines.append(f"{Fore.CYAN}ADX Trend  : Moderate ({adx_val:.0f}){RESET}")

    senkou_span_a = analyzer._get_indicator_value("Senkou_Span_A")
    senkou_span_b = analyzer._get_indicator_value("Senkou_Span_B")
    if not pd.isna(senkou_span_a) and not pd.isna(senkou_span_b):
        kumo_upper = max(senkou_span_a, senkou_span_b)
        kumo_lower = min(senkou_span_a, senkou_span_b)
        if current_price > kumo_upper:
            trend_summary_lines.append(f"{Fore.GREEN}Ichimoku   : Above Kumo{RESET}")
        elif current_price < kumo_lower:
            trend_summary_lines.append(f"{Fore.RED}Ichimoku   : Below Kumo{RESET}")
        else:
            trend_summary_lines.append(f"{Fore.YELLOW}Ichimoku   : Inside Kumo{RESET}")

    if mtf_trends:
        up_count = sum(1 for t in mtf_trends.values() if t == "UP")
        down_count = sum(1 for t in mtf_trends.values() if t == "DOWN")
        total = len(mtf_trends)
        if total > 0:
            if up_count == total:
                trend_summary_lines.append(f"{Fore.GREEN}MTF Confl. : All Bullish ({up_count}/{total}){RESET}")
            elif down_count == total:
                trend_summary_lines.append(f"{Fore.RED}MTF Confl. : All Bearish ({down_count}/{total}){RESET}")
            elif up_count > down_count:
                trend_summary_lines.append(f"{Fore.LIGHTGREEN_EX}MTF Confl. : Mostly Bullish ({up_count}/{total}){RESET}")
            elif down_count > up_count:
                trend_summary_lines.append(f"{Fore.LIGHTRED_EX}MTF Confl. : Mostly Bearish ({down_count}/{total}){RESET}")
            else:
                trend_summary_lines.append(f"{Fore.YELLOW}MTF Confl. : Mixed ({up_count}/{total} Bull, {down_count}/{total} Bear){RESET}")

    for line in trend_summary_lines:
        logger.info(f"  {line}")

    logger.info(f"{NEON_BLUE}--------------------------------------{RESET}")


def main() -> None:
    config = Config()
    logger = setup_logger(config, log_name="wgwhalex_bot", json_log_file="unanimous.log")
    config_data = load_config(CONFIG_FILE, logger)
    # You might want to update your config object with data from the file if necessary
    # For now, we assume the Config object initialized from env vars is sufficient.

    alert_system = AlertSystem(logger)
    bybit_client = BybitClient(API_KEY, API_SECRET, BASE_URL, logger)

    valid_bybit_intervals = [
        "1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D", "W", "M",
    ]

    if config.KLINES_INTERVAL not in valid_bybit_intervals:
        logger.error(f"{NEON_RED}Invalid primary interval '{config.KLINES_INTERVAL}' in config.json. Please use Bybit's valid string formats (e.g., '15', '60', 'D'). Exiting.{RESET}")
        sys.exit(1)

    for htf_interval in config.MTF_ANALYSIS["higher_timeframes"]:
        if htf_interval not in valid_bybit_intervals:
            logger.error(f"{NEON_RED}Invalid higher timeframe interval '{htf_interval}' in config.json. Please use Bybit's valid string formats (e.g., '60', '240'). Exiting.{RESET}")
            sys.exit(1)

    logger.info(f"{NEON_GREEN}--- Whalebot Trading Bot Initialized ---{RESET}")
    logger.info(f"Symbol: {config.SYMBOL}, Interval: {config.KLINES_INTERVAL}")
    logger.info(f"Trade Management Enabled: {config.TRADE_MANAGEMENT['enabled']}")

    position_manager = PositionManager(config_data, logger, config.SYMBOL, bybit_client)
    performance_tracker = PerformanceTracker(logger, config_data)

    while True:
        try:
            logger.info(f"{NEON_PURPLE}--- New Analysis Loop Started ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}) ---{RESET}")
            current_price = bybit_client.fetch_current_price(config.SYMBOL)

            trading_signal = "HOLD"
            signal_score = 0.0
            signal_breakdown = {}
            if current_price is None:
                alert_system.send_alert(f"[{config.SYMBOL}] Failed to fetch current price. Skipping loop.", "WARNING")
                time.sleep(config.LOOP_DELAY_SECONDS)
                continue

            df = bybit_client.fetch_klines(config.SYMBOL, config.KLINES_INTERVAL, 1000)
            if df is None or df.empty:
                alert_system.send_alert(f"[{config.SYMBOL}] Failed to fetch primary klines or DataFrame is empty. Skipping loop.", "WARNING")
                time.sleep(config.LOOP_DELAY_SECONDS)
                continue

            orderbook_data = None
            if config.INDICATORS.get("orderbook_imbalance", False):
                orderbook_data = bybit_client.fetch_orderbook(config.SYMBOL, config.ORDERBOOK_LIMIT)

            mtf_trends: dict[str, str] = {}
            if config.MTF_ANALYSIS["enabled"]:
                for htf_interval in config.MTF_ANALYSIS["higher_timeframes"]:
                    logger.debug(f"Fetching klines for MTF interval: {htf_interval}")
                    htf_df = bybit_client.fetch_klines(config.SYMBOL, htf_interval, 1000)
                    if htf_df is not None and not htf_df.empty:
                        for trend_ind in config.MTF_ANALYSIS["trend_indicators"]:
                            temp_analyzer = TradingAnalyzer(htf_df, config_data, logger, config.SYMBOL)
                            trend = temp_analyzer._get_mtf_trend(temp_analyzer.df, trend_ind)
                            mtf_trends[f"{htf_interval}_{trend_ind}"] = trend
                            logger.debug(f"MTF Trend ({htf_interval}, {trend_ind}): {trend}")
                    else:
                        logger.warning(f"{NEON_YELLOW}Could not fetch klines for higher timeframe {htf_interval} or it was empty. Skipping MTF trend for this TF.{RESET}")
                    time.sleep(config.MTF_ANALYSIS["mtf_request_delay_seconds"])

            analyzer = TradingAnalyzer(df, config_data, logger, config.SYMBOL)

            if analyzer.df.empty:
                alert_system.send_alert(f"[{config.SYMBOL}] TradingAnalyzer DataFrame is empty after indicator calculations. Cannot generate signal.", "WARNING")
                time.sleep(config.LOOP_DELAY_SECONDS)
                continue

            trading_signal, signal_score, signal_breakdown = analyzer.generate_trading_signal(current_price, orderbook_data, mtf_trends)
            atr_value = Decimal(str(analyzer._get_indicator_value("ATR", Decimal("0.01"))))

            display_indicator_values_and_price(config_data, logger, current_price, analyzer, orderbook_data, mtf_trends, signal_breakdown)

            position_manager.manage_positions(current_price, performance_tracker)

            if trading_signal == "BUY" and signal_score >= config.SIGNAL_SCORE_THRESHOLD:
                logger.info(f"{NEON_GREEN}Strong BUY signal detected! Score: {signal_score:.2f}{RESET}")
                take_profit_price, stop_loss_price = analyzer.calculate_entry_tp_sl(current_price, atr_value, "BUY")
                order_qty = position_manager._calculate_order_size(current_price, atr_value)

                if order_qty > 0:
                    order_response = bybit_client.place_order(
                        category="linear",
                        symbol=config.SYMBOL,
                        side="Buy",
                        order_type="Market",
                        qty=order_qty,
                        stop_loss=stop_loss_price,
                        take_profit=take_profit_price,
                    )
                    if order_response and order_response.get("retCode") == 0:
                        order_id = order_response["result"]["orderId"]
                        position_manager.open_position("BUY", current_price, atr_value, order_id)
                    else:
                        logger.error(f"{NEON_RED}Failed to place BUY order: {order_response}{RESET}")
                else:
                    logger.warning(f"{NEON_YELLOW}Calculated BUY order quantity is zero. Skipping order placement.{RESET}")

            elif trading_signal == "SELL" and signal_score <= -config.SIGNAL_SCORE_THRESHOLD:
                logger.info(f"{NEON_RED}Strong SELL signal detected! Score: {signal_score:.2f}{RESET}")
                take_profit_price, stop_loss_price = analyzer.calculate_entry_tp_sl(current_price, atr_value, "SELL")
                order_qty = position_manager._calculate_order_size(current_price, atr_value)

                if order_qty > 0:
                    order_response = bybit_client.place_order(
                        category="linear",
                        symbol=config.SYMBOL,
                        side="Sell",
                        order_type="Market",
                        qty=order_qty,
                        stop_loss=stop_loss_price,
                        take_profit=take_profit_price,
                    )
                    if order_response and order_response.get("retCode") == 0:
                        order_id = order_response["result"]["orderId"]
                        position_manager.open_position("SELL", current_price, atr_value, order_id)
                    else:
                        logger.error(f"{NEON_RED}Failed to place SELL order: {order_response}{RESET}")
                else:
                    logger.warning(f"{NEON_YELLOW}Calculated SELL order quantity is zero. Skipping order placement.{RESET}")
            else:
                logger.info(f"{NEON_BLUE}No strong trading signal. Holding. Score: {signal_score:.2f}{RESET}")

            open_positions = position_manager.get_open_positions()
            if open_positions:
                logger.info(f"{NEON_CYAN}Open Positions: {len(open_positions)}{RESET}")
                for pos in open_positions:
                    logger.info(f"  - {pos['side']} @ {pos['entry_price'].normalize()} (SL: {pos['stop_loss'].normalize()}, TP: {pos['take_profit'].normalize()}){RESET}")
            else:
                logger.info(f"{NEON_CYAN}No open positions.{RESET}")

            perf_summary = performance_tracker.get_summary()
            logger.info(f"{NEON_YELLOW}Performance Summary: Total PnL: {perf_summary['total_pnl'].normalize():.2f}, Wins: {perf_summary['wins']}, Losses: {perf_summary['losses']}, Win Rate: {perf_summary['win_rate']}{RESET}")

            logger.info(f"{NEON_PURPLE}--- Analysis Loop Finished. Waiting {config.LOOP_DELAY_SECONDS}s ---{RESET}")
            time.sleep(config.LOOP_DELAY_SECONDS)

        except Exception as e:
            alert_system.send_alert(f"[{config.SYMBOL}] An unhandled error occurred in the main loop: {e}", "ERROR")
            logger.exception(f"{NEON_RED}Unhandled exception in main loop:{RESET}")
            time.sleep(config.LOOP_DELAY_SECONDS * 2)


if __name__ == "__main__":
    main()
 "__main__":
    main()
