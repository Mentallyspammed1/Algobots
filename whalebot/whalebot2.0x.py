#!/usr/bin/env python3

"""
Trading Bot – Refactored & Enhanced

This module implements a high-frequency crypto-trading bot that:
* Pulls market data from Bybit
* Calculates a wide range of technical indicators
* Generates a composite signal score
* Manages positions with risk-based sizing
* Tracks performance and sends alerts

All core logic is encapsulated in classes with type hints,
vectorised pandas operations, and robust error handling.
"""

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #
import logging
import os
import sys
import time
import urllib
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal, getcontext
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
import requests
from colorama import Fore, Style, init
from dotenv import load_dotenv
from logger_setup import SensitiveFormatter
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --------------------------------------------------------------------------- #
# Global Settings & Constants
# --------------------------------------------------------------------------- #
load_dotenv()
init(autoreset=True)

# Colour constants
NEON_GREEN = Fore.LIGHTGREEN_EX
NEON_BLUE = Fore.CYAN
NEON_PURPLE = Fore.MAGENTA
NEON_YELLOW = Fore.YELLOW
NEON_RED = Fore.LIGHTRED_EX
NEON_CYAN = Fore.CYAN
RESET = Style.RESET_ALL

# Indicator colour map (used in display)
INDICATOR_COLORS: dict[str, str] = {
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

# Decimal precision
getcontext().prec = 28

# Configuration file path
CONFIG_FILE = "config.json"

# Logging directory
LOG_DIRECTORY = Path("bot_logs/trading-bot/logs")
LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)

# Time zone
TIMEZONE = UTC

# API request settings
MAX_API_RETRIES = 5
RETRY_DELAY_SECONDS = 7
REQUEST_TIMEOUT = 20
LOOP_DELAY_SECONDS = 15

# Minimum data points for various indicators
MIN_DATA_POINTS_TR = 2
MIN_DATA_POINTS_SMOOTHER_INIT = 2
MIN_DATA_POINTS_OBV = 2
MIN_DATA_POINTS_PSAR = 2
ADX_STRONG_TREND_THRESHOLD = 25
ADX_WEAK_TREND_THRESHOLD = 20
STOCH_RSI_MID_POINT = 50
MIN_CANDLESTICK_PATTERNS_BARS = 2


# --------------------------------------------------------------------------- #
# Helper Decorators
# --------------------------------------------------------------------------- #
def retry_on_exception(
    retries: int = MAX_API_RETRIES,
    delay: int = RETRY_DELAY_SECONDS,
    allowed_exceptions: tuple[type, ...] = (requests.exceptions.RequestException,),
):
    """
    Decorator that retries a function on specified exceptions.
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            attempt = 0
            while attempt < retries:
                try:
                    return func(*args, **kwargs)
                except allowed_exceptions:
                    attempt += 1
                    if attempt >= retries:
                        raise
                    time.sleep(delay)

        return wrapper

    return decorator


# --------------------------------------------------------------------------- #
# Data Classes for Configuration
# --------------------------------------------------------------------------- #
from dataclasses import dataclass, field


@dataclass
class IndicatorSettings:
    atr_period: int = 14
    ema_short_period: int = 9
    ema_long_period: int = 21
    rsi_period: int = 14
    stoch_rsi_period: int = 14
    stoch_k_period: int = 3
    stoch_d_period: int = 3
    bollinger_bands_period: int = 20
    bollinger_bands_std_dev: float = 2.0
    cci_period: int = 20
    williams_r_period: int = 14
    mfi_period: int = 14
    psar_acceleration: float = 0.02
    psar_max_acceleration: float = 0.2
    sma_short_period: int = 10
    sma_long_period: int = 50
    fibonacci_window: int = 60
    ehlers_fast_period: int = 10
    ehlers_fast_multiplier: float = 2.0
    ehlers_slow_period: int = 20
    ehlers_slow_multiplier: float = 3.0
    macd_fast_period: int = 12
    macd_slow_period: int = 26
    macd_signal_period: int = 9
    adx_period: int = 14
    ichimoku_tenkan_period: int = 9
    ichimoku_kijun_period: int = 26
    ichimoku_senkou_span_b_period: int = 52
    ichimoku_chikou_span_offset: int = 26
    obv_ema_period: int = 20
    cmf_period: int = 20
    rsi_oversold: int = 30
    rsi_overbought: int = 70
    stoch_rsi_oversold: int = 20
    stoch_rsi_overbought: int = 80
    cci_oversold: int = -100
    cci_overbought: int = 100
    williams_r_oversold: int = -80
    williams_r_overbought: int = -20
    mfi_oversold: int = 20
    mfi_overbought: int = 80
    volatility_index_period: int = 20
    vwma_period: int = 20
    volume_delta_period: int = 5
    volume_delta_threshold: float = 0.2
    kama_period: int = 10
    kama_fast_period: int = 2
    kama_slow_period: int = 30
    relative_volume_period: int = 20
    relative_volume_threshold: float = 1.5
    market_structure_lookback_period: int = 20
    dema_period: int = 14
    keltner_period: int = 20
    keltner_atr_multiplier: float = 2.0
    roc_period: int = 12
    roc_oversold: float = -5.0
    roc_overbought: float = 5.0


@dataclass
class TradeManagement:
    enabled: bool = True
    account_balance: Decimal = Decimal("1000.0")
    risk_per_trade_percent: Decimal = Decimal("1.0")
    stop_loss_atr_multiple: Decimal = Decimal("1.5")
    take_profit_atr_multiple: Decimal = Decimal("2.0")
    max_open_positions: int = 1
    order_precision: int = 5
    price_precision: int = 3
    slippage_percent: Decimal = Decimal("0.001")
    trading_fee_percent: Decimal = Decimal("0.0005")


@dataclass
class MTFAnalysis:
    enabled: bool = True
    higher_timeframes: list[str] = field(default_factory=lambda: ["60", "240"])
    trend_indicators: list[str] = field(default_factory=lambda: ["ema", "ehlers_supertrend"])
    trend_period: int = 50
    mtf_request_delay_seconds: float = 0.5


@dataclass
class WeightSets:
    default_scalping: dict[str, float] = field(default_factory=lambda: {
        "ema_alignment": 0.22,
        "sma_trend_filter": 0.28,
        "momentum_rsi_stoch_cci_wr_mfi": 0.18,
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
    })


@dataclass
class Config:
    symbol: str = "BTCUSDT"
    interval: str = "15"
    loop_delay: int = LOOP_DELAY_SECONDS
    orderbook_limit: int = 50
    signal_score_threshold: float = 2.0
    volume_confirmation_multiplier: float = 1.5
    trade_management: TradeManagement = field(default_factory=TradeManagement)
    mtf_analysis: MTFAnalysis = field(default_factory=MTFAnalysis)
    indicator_settings: IndicatorSettings = field(default_factory=IndicatorSettings)
    indicators: dict[str, bool] = field(
        default_factory=lambda: {
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
    )
    weight_sets: WeightSets = field(default_factory=WeightSets)


# --------------------------------------------------------------------------- #
# Configuration Loader
# --------------------------------------------------------------------------- #
def load_config(filepath: str, logger: logging.Logger) -> Config:
    """
    Load configuration from JSON file or create a default one if missing.
    Returns a Config dataclass instance.
    """
    if not Path(filepath).exists():
        logger.warning(
            f"{NEON_YELLOW}Configuration file not found. Creating default config at {filepath}.{RESET}",
        )
        default_cfg = Config()
        with Path(filepath).open("w", encoding="utf-8") as f:
            json.dump(default_cfg.__dict__, f, indent=4)
        return default_cfg

    try:
        with Path(filepath).open(encoding="utf-8") as f:
            raw = json.load(f)

        # Convert nested dicts to dataclasses
        cfg = Config(
            symbol=raw.get("symbol", "BTCUSDT"),
            interval=raw.get("interval", "15"),
            loop_delay=raw.get("loop_delay", LOOP_DELAY_SECONDS),
            orderbook_limit=raw.get("orderbook_limit", 50),
            signal_score_threshold=raw.get("signal_score_threshold", 2.0),
            volume_confirmation_multiplier=raw.get("volume_confirmation_multiplier", 1.5),
            trade_management=TradeManagement(**raw.get("trade_management", {})),
            mtf_analysis=MTFAnalysis(**raw.get("mtf_analysis", {})),
            indicator_settings=IndicatorSettings(**raw.get("indicator_settings", {})),
            indicators=raw.get("indicators", {}),
            weight_sets=WeightSets(**raw.get("weight_sets", {})),
        )
        logger.info(f"{NEON_GREEN}Configuration loaded successfully.{RESET}")
        return cfg
    except Exception as exc:
        logger.error(
            f"{NEON_RED}Failed to load config: {exc}. Using defaults.{RESET}",
        )
        return Config()


# --------------------------------------------------------------------------- #
# Logger Setup
# --------------------------------------------------------------------------- #
def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Configure a logger with console and rotating file handlers.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    if not logger.handlers:
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(
            SensitiveFormatter(
                f"{NEON_BLUE}%(asctime)s - %(levelname)s - %(message)s{RESET}",
            ),
        )
        logger.addHandler(console_handler)

        # File handler
        log_file = LOG_DIRECTORY / f"{name}.log"
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


# --------------------------------------------------------------------------- #
# Bybit API Client
# --------------------------------------------------------------------------- #
class BybitClient:
    """
    Wrapper around Bybit REST API with retry and signing logic.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str,
        logger: logging.Logger,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.logger = logger
        self.session = self._create_session()

    @retry_on_exception()
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
        return hmac.new(
            self.api_secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

    @retry_on_exception()
    def _send_signed_request(
        self,
        method: Literal["GET", "POST"],
        endpoint: str,
        params: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not self.api_key or not self.api_secret:
            self.logger.error(
                f"{NEON_RED}API_KEY or API_SECRET not set for signed request.{RESET}",
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
                },
            )
            self.logger.debug(f"GET Request: {url}?{query_string}")
            response = self.session.get(
                url,
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
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
                },
            )
            self.logger.debug(f"POST Request: {url} with payload {json_params}")
            response = self.session.post(
                url,
                json=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )

        return self._handle_api_response(response)

    def bybit_request(
        self, method: Literal["GET", "POST"], endpoint: str, params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        # For public endpoints like klines and orderbook, signing is not required.
        # We use _send_signed_request as a general wrapper, but for public data,
        # we can simplify the call if needed, or just ensure signed=False is used.
        # For simplicity here, we'll use a direct request for public data if not signed.
        if method == "GET" and not params:
            params = {}  # Ensure params is not None for urlencode

        timestamp = str(int(time.time() * 1000))
        url = f"{self.base_url}{endpoint}"

        if method == "GET":
            query_string = urllib.parse.urlencode(params) if params else ""
            self.logger.debug(f"GET Request: {url}?{query_string}")
            response = self.session.get(
                url,
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
        else: # POST
            json_params = json.dumps(params) if params else ""
            self.logger.debug(f"POST Request: {url} with payload {json_params}")
            response = self.session.post(
                url,
                json=params,
                timeout=REQUEST_TIMEOUT,
            )

        return self._handle_api_response(response)


    def _handle_api_response(self, response: requests.Response) -> dict[str, Any] | None:
        try:
            response.raise_for_status()
            data = response.json()
            if data.get("retCode") != 0:
                self.logger.error(
                    f"{NEON_RED}Bybit API Error: {data.get('retMsg')} "
                    f"(Code: {data.get('retCode')}){RESET}",
                )
                return None
            return data
        except (requests.exceptions.HTTPError, json.JSONDecodeError) as exc:
            self.logger.error(f"{NEON_RED}API response error: {exc}{RESET}")
            return None

    def fetch_current_price(self, symbol: str) -> Decimal | None:
        endpoint = "/v5/market/tickers"
        params = {"category": "linear", "symbol": symbol}
        response = self.bybit_request("GET", endpoint, params)
        if response and response["result"] and response["result"]["list"]:
            price = Decimal(response["result"]["list"][0]["lastPrice"])
            self.logger.debug(f"Fetched current price for {symbol}: {price}")
            return price
        self.logger.warning(
            f"{NEON_YELLOW}Could not fetch current price for {symbol}.{RESET}",
        )
        return None

    def fetch_klines(
        self,
        symbol: str,
        interval: str,
        limit: int,
    ) -> pd.DataFrame | None:
        endpoint = "/v5/market/kline"
        params = {
            "category": "linear",
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        response = self.bybit_request("GET", endpoint, params)
        if response and response.get("result") and response["result"].get("list"):
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
                df["start_time"].astype(int),
                unit="ms",
                utc=True,
                errors="coerce", # Add this to handle out-of-bounds datetimes
            ).dt.tz_convert(TIMEZONE)
            for col in ["open", "high", "low", "close", "volume", "turnover"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df.set_index("start_time", inplace=True)
            df.sort_index(inplace=True)

            if df.empty:
                self.logger.warning(
                    f"{NEON_YELLOW}Fetched klines for {symbol} {interval} but DataFrame is empty after processing. Raw response: {response}{RESET}",
                )
                return None

            self.logger.debug(f"Fetched {len(df)} {interval} klines for {symbol}.")
            return df
        self.logger.warning(
            f"{NEON_YELLOW}Could not fetch klines for {symbol} {interval}. API response might be empty or invalid. Raw response: {response}{RESET}",
        )
        return None

    def fetch_orderbook(self, symbol: str, limit: int) -> dict[str, Any] | None:
        endpoint = "/v5/market/orderbook"
        params = {"category": "linear", "symbol": symbol, "limit": limit}
        response = self.bybit_request("GET", endpoint, params)
        if response and response.get("result"):
            self.logger.debug(f"Fetched orderbook for {symbol} with limit {limit}.")
            return response["result"]
        self.logger.warning(
            f"{NEON_YELLOW}Could not fetch orderbook for {symbol}.{RESET}",
        )
        return None


# --------------------------------------------------------------------------- #
# Position Management
# --------------------------------------------------------------------------- #
class PositionManager:
    """
    Handles opening, closing and sizing of positions.
    """

    def __init__(self, config: Config, logger: logging.Logger, symbol: str):
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.open_positions: list[dict[str, Any]] = []

        self.trade_management = config.trade_management
        self.max_open_positions = self.trade_management.max_open_positions
        self.order_precision = self.trade_management.order_precision
        self.price_precision = self.trade_management.price_precision
        self.slippage_percent = self.trade_management.slippage_percent
        self.account_balance = self.trade_management.account_balance

    def _order_qty(self, current_price: Decimal, atr_value: Decimal) -> Decimal:
        if not self.trade_management.enabled:
            return Decimal("0")

        risk_pct = Decimal(str(self.trade_management.risk_per_trade_percent)) / 100
        risk_amount = self.account_balance * risk_pct
        sl_atr = Decimal(str(self.trade_management.stop_loss_atr_multiple))
        sl_distance = atr_value * sl_atr

        if sl_distance <= 0:
            self.logger.warning(
                f"{NEON_YELLOW}Calculated stop loss distance is zero or negative. Cannot determine order size.{RESET}",
            )
            return Decimal("0")

        order_value = risk_amount / sl_distance
        qty = order_value / current_price

        precision_str = "0." + "0" * (self.order_precision - 1) + "1"
        qty = qty.quantize(Decimal(precision_str), rounding=ROUND_DOWN)

        self.logger.info(
            f"[{self.symbol}] Order size: {qty.normalize()} (Risk: {risk_amount.normalize():.2f} USD)",
        )
        return qty

    def open_position(
        self,
        side: Literal["BUY", "SELL"],
        current_price: Decimal,
        atr_value: Decimal,
    ) -> dict[str, Any] | None:
        if not self.trade_management.enabled:
            self.logger.info(
                f"{NEON_YELLOW}[{self.symbol}] Trade management disabled. Skipping opening position.{RESET}",
            )
            return None

        if len(self.open_positions) >= self.max_open_positions:
            self.logger.info(
                f"{NEON_YELLOW}[{self.symbol}] Max open positions ({self.max_open_positions}) reached. Cannot open new position.{RESET}",
            )
            return None

        qty = self._order_qty(current_price, atr_value)
        if qty <= 0:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Order quantity is zero or negative. Cannot open position.{RESET}",
            )
            return None

        sl_atr = Decimal(str(self.trade_management.stop_loss_atr_multiple))
        tp_atr = Decimal(str(self.trade_management.take_profit_atr_multiple))

        if side == "BUY":
            entry = current_price * (Decimal("1") + self.slippage_percent)
            sl = entry - (atr_value * sl_atr)
            tp = entry + (atr_value * tp_atr)
        else:
            entry = current_price * (Decimal("1") - self.slippage_percent)
            sl = entry + (atr_value * sl_atr)
            tp = entry - (atr_value * tp_atr)

        precision_str = "0." + "0" * (self.price_precision - 1) + "1"

        position = {
            "entry_time": datetime.now(TIMEZONE),
            "symbol": self.symbol,
            "side": side,
            "entry_price": entry.quantize(
                Decimal(precision_str),
                rounding=ROUND_DOWN,
            ),
            "qty": qty,
            "stop_loss": sl.quantize(
                Decimal(precision_str),
                rounding=ROUND_DOWN,
            ),
            "take_profit": tp.quantize(
                Decimal(precision_str),
                rounding=ROUND_DOWN,
            ),
            "status": "OPEN",
        }
        self.open_positions.append(position)
        self.logger.info(
            f"{NEON_GREEN}[{self.symbol}] Opened {side} position: {position}{RESET}",
        )
        return position

    def _close_position(
        self,
        position: dict[str, Any],
        close_price: Decimal,
        closed_by: str,
    ) -> None:
        position["status"] = "CLOSED"
        position["exit_time"] = datetime.now(TIMEZONE)
        position["exit_price"] = close_price
        position["closed_by"] = closed_by

    def _check_and_close_position(
        self,
        position: dict[str, Any],
        current_price: Decimal,
    ) -> tuple[bool, Decimal, str]:
        side = position["side"]
        sl = position["stop_loss"]
        tp = position["take_profit"]
        slippage = self.slippage_percent

        if side == "BUY":
            if current_price <= sl:
                close_price = current_price * (Decimal("1") - slippage)
                return True, close_price, "STOP_LOSS"
            if current_price >= tp:
                close_price = current_price * (Decimal("1") - slippage)
                return True, close_price, "TAKE_PROFIT"
        else:  # SELL
            if current_price >= sl:
                close_price = current_price * (Decimal("1") + slippage)
                return True, close_price, "STOP_LOSS"
            if current_price <= tp:
                close_price = current_price * (Decimal("1") + slippage)
                return True, close_price, "TAKE_PROFIT"

        return False, Decimal("0"), ""

    def manage_positions(
        self,
        current_price: Decimal,
        performance_tracker: "PerformanceTracker",
    ) -> None:
        if not self.trade_management.enabled or not self.open_positions:
            return

        to_remove: list[int] = []
        for idx, pos in enumerate(self.open_positions):
            if pos["status"] != "OPEN":
                continue

            closed, price, reason = self._check_and_close_position(pos, current_price)
            if closed:
                self._close_position(pos, price, reason)

                # PnL calculation
                if pos["side"] == "BUY":
                    pnl = (price - pos["entry_price"]) * pos["qty"]
                else:
                    pnl = (pos["entry_price"] - price) * pos["qty"]
                performance_tracker.record_trade(pos, pnl)

                self.logger.info(
                    f"{NEON_PURPLE}[{self.symbol}] Closed {pos['side']} position by {reason}: {pos}. PnL: {pnl.normalize():.2f}{RESET}",
                )
                to_remove.append(idx)

        self.open_positions = [
            p for i, p in enumerate(self.open_positions) if i not in to_remove
        ]

    def get_open_positions(self) -> list[dict[str, Any]]:
        return [p for p in self.open_positions if p["status"] == "OPEN"]


# --------------------------------------------------------------------------- #
# Performance Tracker
# --------------------------------------------------------------------------- #
class PerformanceTracker:
    """
    Records trades and calculates aggregate performance metrics.
    """

    def __init__(self, logger: logging.Logger, config: Config):
        self.logger = logger
        self.config = config
        self.trades: list[dict[str, Any]] = []
        self.total_pnl = Decimal("0")
        self.wins = 0
        self.losses = 0
        self.trading_fee_percent = Decimal(str(config.trade_management.trading_fee_percent))

    def record_trade(self, position: dict[str, Any], pnl: Decimal) -> None:
        trade = {
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
        self.trades.append(trade)
        self.total_pnl += pnl

        # Fees
        entry_fee = position["entry_price"] * position["qty"] * self.trading_fee_percent
        exit_fee = position["exit_price"] * position["qty"] * self.trading_fee_percent
        total_fees = entry_fee + exit_fee
        self.total_pnl -= total_fees

        if pnl > 0:
            self.wins += 1
        else:
            self.losses += 1
        self.logger.info(
            f"{NEON_CYAN}[{position['symbol']}] Trade recorded. PnL (before fees): {pnl.normalize():.2f}, Total Fees: {total_fees.normalize():.2f}, Current Total PnL (after fees): {self.total_pnl.normalize():.2f}, Wins: {self.wins}, Losses: {self.losses}{RESET}",
        )

    def get_summary(self) -> dict[str, Any]:
        total_trades = len(self.trades)
        win_rate = (self.wins / total_trades * 100) if total_trades > 0 else 0

        return {
            "total_trades": total_trades,
            "total_pnl": self.total_pnl,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": f"{win_rate:.2f}%",
        }


# --------------------------------------------------------------------------- #
# Alert System
# --------------------------------------------------------------------------- #
class AlertSystem:
    """
    Simple wrapper around logger for alerts.
    """

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def send_alert(self, message: str, level: Literal["INFO", "WARNING", "ERROR"]) -> None:
        if level == "INFO":
            self.logger.info(f"{NEON_BLUE}ALERT: {message}{RESET}")
        elif level == "WARNING":
            self.logger.warning(f"{NEON_YELLOW}ALERT: {message}{RESET}")
        else:
            self.logger.error(f"{NEON_RED}ALERT: {message}{RESET}")


# --------------------------------------------------------------------------- #
# Trading Analyzer
# --------------------------------------------------------------------------- #
class TradingAnalyzer:
    """
    Calculates all configured indicators and generates a composite signal.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        config: Config,
        logger: logging.Logger,
        symbol: str,
    ):
        self.df = df.copy()
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.indicator_values: dict[str, Any] = {}
        self.fib_levels: dict[str, Decimal] = {}
        self.weights = config.weight_sets.default_scalping
        self.isd = config.indicator_settings

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}TradingAnalyzer initialised with an empty DataFrame. Indicators will not be calculated.{RESET}",
            )
            return

        self._calculate_all_indicators()

        if self.config.indicators.get("fibonacci_levels", False):
            self.calculate_fibonacci_levels()
        if self.config.indicators.get("fibonacci_pivot_points", False):
            self.calculate_fibonacci_pivot_points()

    # ----------------------------------------------------------------------- #
    # Indicator Calculations (vectorised)
    # ----------------------------------------------------------------------- #
    def _calculate_all_indicators(self) -> None:
        self.logger.debug(f"[{self.symbol}] Calculating technical indicators...\n")
        isd = self.isd

        # SMA 10 & Long
        self.df["SMA_10"] = self.df["close"].rolling(window=isd.sma_short_period).mean()
        self.df["SMA_Long"] = self.df["close"].rolling(window=isd.sma_long_period).mean()
        self.indicator_values["SMA_10"] = self.df["SMA_10"].iloc[-1]
        self.indicator_values["SMA_Long"] = self.df["SMA_Long"].iloc[-1]

        # EMA Alignment
        ema_short = self.df["close"].ewm(span=isd.ema_short_period, adjust=False).mean()
        ema_long = self.df["close"].ewm(span=isd.ema_long_period, adjust=False).mean()
        self.df["EMA_Short"] = ema_short
        self.df["EMA_Long"] = ema_long
        self.indicator_values["EMA_Short"] = ema_short.iloc[-1]
        self.indicator_values["EMA_Long"] = ema_long.iloc[-1]

        # ATR
        tr = self._calculate_true_range()
        atr = tr.ewm(span=isd.atr_period, adjust=False).mean()
        self.df["ATR"] = atr
        self.indicator_values["ATR"] = atr.iloc[-1]

        # RSI
        rsi = self.calculate_rsi(isd.rsi_period)
        self.df["RSI"] = rsi
        self.indicator_values["RSI"] = rsi.iloc[-1]

        # Stoch RSI
        stoch_k, stoch_d = self.calculate_stoch_rsi(
            period=isd.stoch_rsi_period,
            k_period=isd.stoch_k_period,
            d_period=isd.stoch_d_period,
        )
        self.df["StochRSI_K"] = stoch_k
        self.df["StochRSI_D"] = stoch_d
        self.indicator_values["StochRSI_K"] = stoch_k.iloc[-1]
        self.indicator_values["StochRSI_D"] = stoch_d.iloc[-1]

        # Bollinger Bands
        bb_upper, bb_middle, bb_lower = self.calculate_bollinger_bands(
            period=isd.bollinger_bands_period,
            std_dev=isd.bollinger_bands_std_dev,
        )
        self.df["BB_Upper"] = bb_upper
        self.df["BB_Middle"] = bb_middle
        self.df["BB_Lower"] = bb_lower
        self.indicator_values["BB_Upper"] = bb_upper.iloc[-1]
        self.indicator_values["BB_Middle"] = bb_middle.iloc[-1]
        self.indicator_values["BB_Lower"] = bb_lower.iloc[-1]

        # CCI
        cci = self.calculate_cci(isd.cci_period)
        self.df["CCI"] = cci
        self.indicator_values["CCI"] = cci.iloc[-1]

        # Williams %R
        wr = self.calculate_williams_r(isd.williams_r_period)
        self.df["WR"] = wr
        self.indicator_values["WR"] = wr.iloc[-1]

        # MFI
        mfi = self.calculate_mfi(isd.mfi_period)
        self.df["MFI"] = mfi
        self.indicator_values["MFI"] = mfi.iloc[-1]

        # OBV
        obv, obv_ema = self.calculate_obv(isd.obv_ema_period)
        self.df["OBV"] = obv
        self.df["OBV_EMA"] = obv_ema
        self.indicator_values["OBV"] = obv.iloc[-1]
        self.indicator_values["OBV_EMA"] = obv_ema.iloc[-1]

        # CMF
        cmf = self.calculate_cmf(isd.cmf_period)
        self.df["CMF"] = cmf
        self.indicator_values["CMF"] = cmf.iloc[-1]

        # Ichimoku Cloud
        (
            tenkan,
            kijun,
            senkou_a,
            senkou_b,
            chikou,
        ) = self.calculate_ichimoku_cloud(
            tenkan_period=isd.ichimoku_tenkan_period,
            kijun_period=isd.ichimoku_kijun_period,
            senkou_span_b_period=isd.ichimoku_senkou_span_b_period,
            chikou_span_offset=isd.ichimoku_chikou_span_offset,
        )
        self.df["Tenkan_Sen"] = tenkan
        self.df["Kijun_Sen"] = kijun
        self.df["Senkou_Span_A"] = senkou_a
        self.df["Senkou_Span_B"] = senkou_b
        self.df["Chikou_Span"] = chikou
        self.indicator_values["Tenkan_Sen"] = tenkan.iloc[-1]
        self.indicator_values["Kijun_Sen"] = kijun.iloc[-1]
        self.indicator_values["Senkou_Span_A"] = senkou_a.iloc[-1]
        self.indicator_values["Senkou_Span_B"] = senkou_b.iloc[-1]
        self.indicator_values["Chikou_Span"] = chikou.iloc[-1]

        # Parabolic SAR
        psar_val, psar_dir = self.calculate_psar(
            acceleration=isd.psar_acceleration,
            max_acceleration=isd.psar_max_acceleration,
        )
        self.df["PSAR_Val"] = psar_val
        self.df["PSAR_Dir"] = psar_dir
        self.indicator_values["PSAR_Val"] = psar_val.iloc[-1]
        self.indicator_values["PSAR_Dir"] = psar_dir.iloc[-1]

        # VWAP
        vwap = self.calculate_vwap()
        self.df["VWAP"] = vwap
        self.indicator_values["VWAP"] = vwap.iloc[-1]

        # MACD
        macd_line, macd_signal, macd_hist = self.calculate_macd(
            fast_period=isd.macd_fast_period,
            slow_period=isd.macd_slow_period,
            signal_period=isd.macd_signal_period,
        )
        self.df["MACD_Line"] = macd_line
        self.df["MACD_Signal"] = macd_signal
        self.df["MACD_Hist"] = macd_hist
        self.indicator_values["MACD_Line"] = macd_line.iloc[-1]
        self.indicator_values["MACD_Signal"] = macd_signal.iloc[-1]
        self.indicator_values["MACD_Hist"] = macd_hist.iloc[-1]

        # ADX
        adx, plus_di, minus_di = self.calculate_adx(isd.adx_period)
        self.df["ADX"] = adx
        self.df["PlusDI"] = plus_di
        self.df["MinusDI"] = minus_di
        self.indicator_values["ADX"] = adx.iloc[-1]
        self.indicator_values["PlusDI"] = plus_di.iloc[-1]
        self.indicator_values["MinusDI"] = minus_di.iloc[-1]

        # Volatility Index
        vol_index = self.calculate_volatility_index(isd.volatility_index_period)
        self.df["Volatility_Index"] = vol_index
        self.indicator_values["Volatility_Index"] = vol_index.iloc[-1]

        # VWMA
        vwma = self.calculate_vwma(isd.vwma_period)
        self.df["VWMA"] = vwma
        self.indicator_values["VWMA"] = vwma.iloc[-1]

        # Volume Delta
        vol_delta = self.calculate_volume_delta(isd.volume_delta_period)
        self.df["Volume_Delta"] = vol_delta
        self.indicator_values["Volume_Delta"] = vol_delta.iloc[-1]

        # Kaufman AMA
        kama = self.calculate_kaufman_ama(
            period=isd.kama_period,
            fast_period=isd.kama_fast_period,
            slow_period=isd.kama_slow_period,
        )
        self.df["Kaufman_AMA"] = kama
        self.indicator_values["Kaufman_AMA"] = kama.iloc[-1]

        # Relative Volume
        rel_vol = self.calculate_relative_volume(isd.relative_volume_period)
        self.df["Relative_Volume"] = rel_vol
        self.indicator_values["Relative_Volume"] = rel_vol.iloc[-1]

        # Market Structure
        market_struct = self.calculate_market_structure(isd.market_structure_lookback_period)
        self.df["Market_Structure_Trend"] = market_struct
        self.indicator_values["Market_Structure_Trend"] = market_struct.iloc[-1]

        # DEMA
        dema = self.calculate_dema(self.df["close"], isd.dema_period)
        self.df["DEMA"] = dema
        self.indicator_values["DEMA"] = dema.iloc[-1]

        # Keltner Channels
        keltner_upper, keltner_middle, keltner_lower = self.calculate_keltner_channels(
            period=isd.keltner_period,
            atr_multiplier=isd.keltner_atr_multiplier,
        )
        self.df["Keltner_Upper"] = keltner_upper
        self.df["Keltner_Middle"] = keltner_middle
        self.df["Keltner_Lower"] = keltner_lower
        self.indicator_values["Keltner_Upper"] = keltner_upper.iloc[-1]
        self.indicator_values["Keltner_Middle"] = keltner_middle.iloc[-1]
        self.indicator_values["Keltner_Lower"] = keltner_lower.iloc[-1]

        # ROC
        roc = self.calculate_roc(isd.roc_period)
        self.df["ROC"] = roc
        self.indicator_values["ROC"] = roc.iloc[-1]

        # Candlestick Patterns
        pattern = self.detect_candlestick_patterns()
        self.df["Candlestick_Pattern"] = pattern
        self.indicator_values["Candlestick_Pattern"] = pattern

        # Clean up NaNs
        self.df.dropna(subset=["close"], inplace=True)
        self.df.fillna(0, inplace=True)

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] DataFrame is empty after calculating all indicators and dropping NaNs.{RESET}",
            )
        else:
            self.logger.debug(
                f"[{self.symbol}] Indicators calculated. Final DataFrame size: {len(self.df)}",
            )

    # ----------------------------------------------------------------------- #
    # Individual Indicator Calculations
    # ----------------------------------------------------------------------- #
    def _calculate_true_range(self) -> pd.Series:
        high = self.df["high"]
        low = self.df["low"]
        close = self.df["close"]
        prev_close = close.shift()
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    def calculate_super_smoother(self, series: pd.Series, period: int) -> pd.Series:
        if period <= 0 or len(series) < MIN_DATA_POINTS_SMOOTHER_INIT:
            return pd.Series(np.nan, index=series.index)

        series = pd.to_numeric(series, errors="coerce").dropna()
        if len(series) < MIN_DATA_POINTS_SMOOTHER_INIT:
            return pd.Series(np.nan, index=series.index)

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
        self,
        period: int,
        multiplier: float,
    ) -> pd.DataFrame | None:
        if len(self.df) < period * 3:
            self.logger.debug(
                f"[{self.symbol}] Not enough data for Ehlers SuperTrend (period={period}). Need at least {period * 3} bars.",
            )
            return None

        df_copy = self.df.copy()
        hl2 = (df_copy["high"] + df_copy["low"]) / 2
        smoothed_price = self.calculate_super_smoother(hl2, period)
        tr = self._calculate_true_range()
        smoothed_atr = self.calculate_super_smoother(tr, period)

        df_copy["smoothed_price"] = smoothed_price
        df_copy["smoothed_atr"] = smoothed_atr

        df_copy.dropna(subset=["smoothed_price", "smoothed_atr"], inplace=True)
        if df_copy.empty:
            self.logger.warning(
                f"[{self.symbol}] Ehlers SuperTrend: DataFrame empty after smoothing. Returning None.",
            )
            return None

        upper_band = df_copy["smoothed_price"] + multiplier * df_copy["smoothed_atr"]
        lower_band = df_copy["smoothed_price"] - multiplier * df_copy["smoothed_atr"]

        direction = pd.Series(0, index=df_copy.index, dtype=int)
        supertrend = pd.Series(np.nan, index=df_copy.index)

        first_valid_idx = df_copy["close"].first_valid_index()
        if first_valid_idx is None:
            return None

        if df_copy["close"].iloc[first_valid_idx] > upper_band.iloc[first_valid_idx]:
            direction.iloc[first_valid_idx] = 1
            supertrend.iloc[first_valid_idx] = lower_band.iloc[first_valid_idx]
        elif df_copy["close"].iloc[first_valid_idx] < lower_band.iloc[first_valid_idx]:
            direction.iloc[first_valid_idx] = -1
            supertrend.iloc[first_valid_idx] = upper_band.iloc[first_valid_idx]
        else:
            direction.iloc[first_valid_idx] = 0
            supertrend.iloc[first_valid_idx] = lower_band.iloc[first_valid_idx]

        for i in range(first_valid_idx + 1, len(df_copy)):
            prev_dir = direction.iloc[i - 1]
            prev_st = supertrend.iloc[i - 1]
            cur_close = df_copy["close"].iloc[i]

            if prev_dir == 1:
                if cur_close < prev_st:
                    direction.iloc[i] = -1
                    supertrend.iloc[i] = upper_band.iloc[i]
                else:
                    direction.iloc[i] = 1
                    supertrend.iloc[i] = max(lower_band.iloc[i], prev_st)
            elif prev_dir == -1:
                if cur_close > prev_st:
                    direction.iloc[i] = 1
                    supertrend.iloc[i] = lower_band.iloc[i]
                else:
                    direction.iloc[i] = -1
                    supertrend.iloc[i] = min(upper_band.iloc[i], prev_st)
            elif cur_close > upper_band.iloc[i]:
                direction.iloc[i] = 1
                supertrend.iloc[i] = lower_band.iloc[i]
            elif cur_close < lower_band.iloc[i]:
                direction.iloc[i] = -1
                supertrend.iloc[i] = upper_band.iloc[i]
            else:
                direction.iloc[i] = prev_dir
                supertrend.iloc[i] = prev_st

        result = pd.DataFrame({"supertrend": supertrend, "direction": direction})
        return result.reindex(self.df.index)

    def calculate_macd(
        self,
        fast_period: int,
        slow_period: int,
        signal_period: int,
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        ema_fast = self.df["close"].ewm(span=fast_period, adjust=False).mean()
        ema_slow = self.df["close"].ewm(span=slow_period, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    def calculate_rsi(self, period: int) -> pd.Series:
        delta = self.df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(span=period, adjust=False).mean()
        avg_loss = loss.ewm(span=period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    def calculate_stoch_rsi(
        self,
        period: int,
        k_period: int,
        d_period: int,
    ) -> tuple[pd.Series, pd.Series]:
        rsi = self.calculate_rsi(period)
        lowest = rsi.rolling(window=period, min_periods=period).min()
        highest = rsi.rolling(window=period, min_periods=period).max()
        denom = highest - lowest
        denom[denom == 0] = np.nan
        stoch_k_raw = ((rsi - lowest) / denom) * 100
        stoch_k_raw = stoch_k_raw.fillna(0).clip(0, 100)
        stoch_k = stoch_k_raw.rolling(window=k_period, min_periods=k_period).mean().fillna(0)
        stoch_d = stoch_k.rolling(window=d_period, min_periods=d_period).mean().fillna(0)
        return stoch_k, stoch_d

    def calculate_bollinger_bands(
        self,
        period: int,
        std_dev: float,
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        middle = self.df["close"].rolling(window=period, min_periods=period).mean()
        std = self.df["close"].rolling(window=period, min_periods=period).std()
        upper = middle + std * std_dev
        lower = middle - std * std_dev
        return upper, middle, lower

    def calculate_cci(self, period: int) -> pd.Series:
        tp = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        sma = tp.rolling(window=period, min_periods=period).mean()
        mad = tp.rolling(window=period, min_periods=period).apply(
            lambda x: np.abs(x - x.mean()).mean(),
            raw=False,
        )
        return (tp - sma) / (0.015 * mad.replace(0, np.nan))

    def calculate_williams_r(self, period: int) -> pd.Series:
        highest = self.df["high"].rolling(window=period, min_periods=period).max()
        lowest = self.df["low"].rolling(window=period, min_periods=period).min()
        return -100 * ((highest - self.df["close"]) / (highest - lowest).replace(0, np.nan))

    def calculate_mfi(self, period: int) -> pd.Series:
        tp = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        mfv = tp * self.df["volume"]
        price_diff = tp.diff()
        positive = mfv.where(price_diff > 0, 0)
        negative = mfv.where(price_diff < 0, 0)
        pos_sum = positive.rolling(window=period, min_periods=period).sum()
        neg_sum = negative.rolling(window=period, min_periods=period).sum()
        ratio = pos_sum / neg_sum.replace(0, np.nan)
        return 100 - (100 / (1 + ratio))

    def calculate_obv(self, ema_period: int) -> tuple[pd.Series, pd.Series]:
        direction = np.sign(self.df["close"].diff().fillna(0))
        obv = (direction * self.df["volume"]).cumsum()
        obv_ema = obv.ewm(span=ema_period, adjust=False).mean()
        return obv, obv_ema

    def calculate_cmf(self, period: int) -> pd.Series:
        high_low = self.df["high"] - self.df["low"]
        mfm = (
            (self.df["close"] - self.df["low"])
            - (self.df["high"] - self.df["close"])
        ) / high_low.replace(0, np.nan)
        mfm = mfm.fillna(0)
        mfv = mfm * self.df["volume"]
        volume_sum = self.df["volume"].rolling(window=period).sum()
        cmf = mfv.rolling(window=period).sum() / volume_sum.replace(0, np.nan)
        return cmf.fillna(0)

    def calculate_psar(
        self,
        acceleration: float,
        max_acceleration: float,
    ) -> tuple[pd.Series, pd.Series]:
        if len(self.df) < MIN_DATA_POINTS_PSAR:
            return pd.Series(np.nan, index=self.df.index), pd.Series(np.nan, index=self.df.index)

        close = self.df["close"]
        high = self.df["high"]
        low = self.df["low"]

        psar = close.copy()
        bull = pd.Series(True, index=close.index)
        af = acceleration
        ep = high.iloc[0] if close.iloc[0] < close.iloc[1] else low.iloc[0]
        bull.iloc[0] = close.iloc[0] < close.iloc[1]

        for i in range(1, len(close)):
            prev_bull = bull.iloc[i - 1]
            prev_psar = psar.iloc[i - 1]

            if prev_bull:
                psar.iloc[i] = prev_psar + af * (ep - prev_psar)
            else:
                psar.iloc[i] = prev_psar - af * (prev_psar - ep)

            reverse = False
            if prev_bull and low.iloc[i] < psar.iloc[i]:
                bull.iloc[i] = False
                reverse = True
            elif not prev_bull and high.iloc[i] > psar.iloc[i]:
                bull.iloc[i] = True
                reverse = True

            if reverse:
                af = acceleration
                ep = high.iloc[i] if bull.iloc[i] else low.iloc[i]
                psar.iloc[i] = min(low.iloc[i], low.iloc[i - 1]) if bull.iloc[i] else max(high.iloc[i], high.iloc[i - 1])
            elif bull.iloc[i]:
                if high.iloc[i] > ep:
                    ep = high.iloc[i]
                    af = min(af + acceleration, max_acceleration)
                psar.iloc[i] = min(psar.iloc[i], low.iloc[i], low.iloc[i - 1])
            else:
                if low.iloc[i] < ep:
                    ep = low.iloc[i]
                    af = min(af + acceleration, max_acceleration)
                psar.iloc[i] = max(psar.iloc[i], high.iloc[i], high.iloc[i - 1])

        direction = pd.Series(0, index=close.index, dtype=int)
        direction[psar < close] = 1
        direction[psar > close] = -1

        return psar, direction

    def calculate_vwap(self) -> pd.Series:
        tp = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        vol = self.df["volume"].replace(0, np.nan)
        cum_tp_vol = (tp * vol).cumsum()
        cum_vol = vol.cumsum()
        return cum_tp_vol / cum_vol

    def calculate_volatility_index(self, period: int) -> pd.Series:
        if "ATR" not in self.df.columns:
            return pd.Series(np.nan, index=self.df.index)
        normalized_atr = self.df["ATR"] / self.df["close"]
        return normalized_atr.rolling(window=period).mean()

    def calculate_vwma(self, period: int) -> pd.Series:
        vol = self.df["volume"].replace(0, np.nan)
        pv = self.df["close"] * vol
        return pv.rolling(window=period).sum() / vol.rolling(window=period).sum()

    def calculate_volume_delta(self, period: int) -> pd.Series:
        buy_vol = self.df["volume"].where(self.df["close"] > self.df["open"], 0)
        sell_vol = self.df["volume"].where(self.df["close"] < self.df["open"], 0)
        buy_sum = buy_vol.rolling(window=period, min_periods=1).sum()
        sell_sum = sell_vol.rolling(window=period, min_periods=1).sum()
        total = buy_sum + sell_sum
        delta = (buy_sum - sell_sum) / total.replace(0, np.nan)
        return delta.fillna(0)

    def calculate_kaufman_ama(
        self,
        period: int,
        fast_period: int,
        slow_period: int,
    ) -> pd.Series:
        close = self.df["close"].values
        kama = np.full_like(close, np.nan)

        price_change = np.abs(close - np.roll(close, period))
        price_change[:period] = np.nan

        volatility = pd.Series(close).diff().abs()
        volatility = volatility.rolling(window=period).sum().values
        volatility[:period] = np.nan

        fast_alpha = 2 / (fast_period + 1)
        slow_alpha = 2 / (slow_period + 1)
        sc = (fast_alpha - slow_alpha) * (price_change / volatility) + slow_alpha
        sc = sc ** 2

        first_valid = np.where(~np.isnan(close) & ~np.isnan(sc))[0]
        if first_valid.size == 0:
            return pd.Series(np.nan, index=self.df.index)

        first = first_valid[0]
        kama[first] = close[first]

        for i in range(first + 1, len(close)):
            if not np.isnan(sc[i]):
                kama[i] = kama[i - 1] + sc[i] * (close[i] - kama[i - 1])
            else:
                kama[i] = kama[i - 1]

        return pd.Series(kama, index=self.df.index)

    def calculate_relative_volume(self, period: int) -> pd.Series:
        avg_vol = self.df["volume"].rolling(window=period, min_periods=period).mean()
        return (self.df["volume"] / avg_vol.replace(0, np.nan)).fillna(1.0)

    def calculate_market_structure(self, lookback_period: int) -> pd.Series:
        if len(self.df) < lookback_period * 2:
            return pd.Series("UNKNOWN", index=self.df.index, dtype="object")

        recent_high = self.df["high"].iloc[-lookback_period:].max()
        recent_low = self.df["low"].iloc[-lookback_period:].min()
        prev_high = self.df["high"].iloc[-2 * lookback_period : -lookback_period].max()
        prev_low = self.df["low"].iloc[-2 * lookback_period : -lookback_period].min()

        trend = "SIDEWAYS"
        if recent_high > prev_high and recent_low > prev_low:
            trend = "UP"
        elif recent_high < prev_high and recent_low < prev_low:
            trend = "DOWN"

        return pd.Series(trend, index=self.df.index, dtype="object")

    def calculate_dema(self, series: pd.Series, period: int) -> pd.Series:
        if len(series) < 2 * period:
            return pd.Series(np.nan, index=series.index)

        ema1 = series.ewm(span=period, adjust=False).mean()
        ema2 = ema1.ewm(span=period, adjust=False).mean()
        return 2 * ema1 - ema2

    def calculate_keltner_channels(
        self,
        period: int,
        atr_multiplier: float,
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        if "ATR" not in self.df.columns:
            atr = self._calculate_true_range().ewm(span=period, adjust=False).mean()
            self.df["ATR"] = atr
        else:
            atr = self.df["ATR"]

        ema = self.df["close"].ewm(span=period, adjust=False).mean()
        upper = ema + atr * atr_multiplier
        lower = ema - atr * atr_multiplier
        return upper, ema, lower

    def calculate_roc(self, period: int) -> pd.Series:
        return (
            (self.df["close"] - self.df["close"].shift(period))
            / self.df["close"].shift(period)
        ) * 100

    def detect_candlestick_patterns(self) -> str:
        if len(self.df) < MIN_CANDLESTICK_PATTERNS_BARS:
            return "No Pattern"

        cur = self.df.iloc[-1]
        prev = self.df.iloc[-2]

        # Bullish Engulfing
        if (
            cur["open"] < prev["close"]
            and cur["close"] > prev["open"]
            and cur["close"] > cur["open"]
            and prev["close"] < prev["open"]
        ):
            return "Bullish Engulfing"

        # Bearish Engulfing
        if (
            cur["open"] > prev["close"]
            and cur["close"] < prev["open"]
            and cur["close"] < cur["open"]
            and prev["close"] > prev["open"]
        ):
            return "Bearish Engulfing"

        # Bullish Hammer
        body = abs(cur["close"] - cur["open"])
        range_ = cur["high"] - cur["low"]
        if (
            body <= range_ * 0.3
            and (cur["open"] - cur["low"]) >= 2 * body
            and (cur["high"] - cur["close"]) <= 0.5 * body
        ):
            return "Bullish Hammer"

        # Bearish Shooting Star
        if (
            body <= range_ * 0.3
            and (cur["high"] - cur["close"]) >= 2 * body
            and (cur["open"] - cur["low"]) <= 0.5 * body
        ):
            return "Bearish Shooting Star"

        return "No Pattern"

    # ----------------------------------------------------------------------- #
    # Helper Methods
    # ----------------------------------------------------------------------- #
    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        return self.indicator_values.get(key, default)

    def _check_orderbook(self, current_price: Decimal, orderbook_data: dict[str, Any]) -> float:
        bids = orderbook_data.get("b", [])
        asks = orderbook_data.get("a", [])

        bid_vol = sum(Decimal(b[1]) for b in bids)
        ask_vol = sum(Decimal(a[1]) for a in asks)

        if bid_vol + ask_vol == 0:
            return 0.0

        imbalance = (bid_vol - ask_vol) / (bid_vol + ask_vol)
        self.logger.debug(
            f"[{self.symbol}] Orderbook Imbalance: {imbalance:.4f} (Bids: {bid_vol}, Asks: {ask_vol})",
        )
        return float(imbalance)

    def calculate_support_resistance_from_orderbook(self, orderbook_data: dict[str, Any]) -> None:
        bids = orderbook_data.get("b", [])
        asks = orderbook_data.get("a", [])

        max_bid_vol = Decimal("0")
        support_level = Decimal("0")
        for bid_price_str, bid_volume_str in bids:
            bid_vol = Decimal(bid_volume_str)
            if bid_vol > max_bid_vol:
                max_bid_vol = bid_vol
                support_level = Decimal(bid_price_str)

        max_ask_vol = Decimal("0")
        resistance_level = Decimal("0")
        for ask_price_str, ask_volume_str in asks:
            ask_vol = Decimal(ask_volume_str)
            if ask_vol > max_ask_vol:
                max_ask_vol = ask_vol
                resistance_level = Decimal(ask_price_str)

        price_precision_str = (
            "0." + "0" * (self.config.trade_management.price_precision - 1) + "1"
        )
        if support_level > 0:
            self.indicator_values["Support_Level"] = support_level.quantize(
                Decimal(price_precision_str),
                rounding=ROUND_DOWN,
            )
            self.logger.debug(
                f"[{self.symbol}] Identified Support Level: {support_level} (Volume: {max_bid_vol})",
            )
        if resistance_level > 0:
            self.indicator_values["Resistance_Level"] = resistance_level.quantize(
                Decimal(price_precision_str),
                rounding=ROUND_DOWN,
            )
            self.logger.debug(
                f"[{self.symbol}] Identified Resistance Level: {resistance_level} (Volume: {max_ask_vol})",
            )

    def _get_mtf_trend(self, higher_tf_df: pd.DataFrame, indicator_type: str) -> str:
        if higher_tf_df.empty:
            return "UNKNOWN"

        last_close = higher_tf_df["close"].iloc[-1]
        period = self.config.mtf_analysis.trend_period

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
            temp_analyzer = TradingAnalyzer(
                higher_tf_df,
                self.config,
                self.logger,
                self.symbol,
            )
            st_result = temp_analyzer.calculate_ehlers_supertrend(
                period=self.config.indicator_settings.ehlers_slow_period,
                multiplier=self.config.indicator_settings.ehlers_slow_multiplier,
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
        orderbook_data: dict[str, Any] | None,
        mtf_trends: dict[str, str],
    ) -> tuple[str, float, dict[str, float]]:
        """
        Compute a composite signal score based on enabled indicators.
        Returns (final_signal, signal_score, signal_breakdown).
        """
        signal_score = 0.0
        signal_breakdown: dict[str, float] = {}
        active = self.config.indicators
        weights = self.weights

        # Current close
        current_close = Decimal(str(self.df["close"].iloc[-1]))
        prev_close = Decimal(str(self.df["close"].iloc[-2])) if len(self.df) > 1 else current_close

        # Trend multiplier (adjusted by ADX)
        trend_strength = 1.0
        if active.get("adx", False):
            adx = self._get_indicator_value("ADX")
            plus = self._get_indicator_value("PlusDI")
            minus = self._get_indicator_value("MinusDI")
            if not pd.isna(adx) and not pd.isna(plus) and not pd.isna(minus):
                if adx > ADX_STRONG_TREND_THRESHOLD:
                    trend_strength = 1.2
                elif adx < ADX_WEAK_TREND_THRESHOLD:
                    trend_strength = 0.8

        # EMA Alignment
        if active.get("ema_alignment", False):
            ema_short = self._get_indicator_value("EMA_Short")
            ema_long = self._get_indicator_value("EMA_Long")
            if not pd.isna(ema_short) and not pd.isna(ema_long):
                contrib = weights.get("ema_alignment", 0) * trend_strength
                if ema_short > ema_long:
                    signal_score += contrib
                    signal_breakdown["EMA Alignment"] = contrib
                elif ema_short < ema_long:
                    signal_score -= contrib
                    signal_breakdown["EMA Alignment"] = -contrib

        # SMA Trend Filter
        if active.get("sma_trend_filter", False):
            sma_long = self._get_indicator_value("SMA_Long")
            if not pd.isna(sma_long):
                contrib = weights.get("sma_trend_filter", 0) * trend_strength
                if current_close > sma_long:
                    signal_score += contrib
                    signal_breakdown["SMA Trend Filter"] = contrib
                elif current_close < sma_long:
                    signal_score -= contrib
                    signal_breakdown["SMA Trend Filter"] = -contrib

        # Momentum Indicators
        if active.get("momentum", False):
            # RSI
            if active.get("rsi", False):
                rsi = self._get_indicator_value("RSI")
                if not pd.isna(rsi):
                    if rsi < self.isd.rsi_oversold:
                        contrib = weights.get("momentum_rsi_stoch_cci_wr_mfi", 0) * 0.5
                        signal_score += contrib
                        signal_breakdown["RSI"] = contrib
                    elif rsi > self.isd.rsi_overbought:
                        contrib = -weights.get("momentum_rsi_stoch_cci_wr_mfi", 0) * 0.5
                        signal_score += contrib
                        signal_breakdown["RSI"] = contrib

            # Stoch RSI
            if active.get("stoch_rsi", False):
                k = self._get_indicator_value("StochRSI_K")
                d = self._get_indicator_value("StochRSI_D")
                if not pd.isna(k) and not pd.isna(d):
                    if k > d and k < STOCH_RSI_MID_POINT:
                        contrib = weights.get("momentum_rsi_stoch_cci_wr_mfi", 0) * 0.2
                        signal_score += contrib
                        signal_breakdown["StochRSI Crossover"] = contrib
                    elif k < d and k > STOCH_RSI_MID_POINT:
                        contrib = -weights.get("momentum_rsi_stoch_cci_wr_mfi", 0) * 0.2
                        signal_score += contrib
                        signal_breakdown["StochRSI Crossover"] = contrib

            # CCI
            if active.get("cci", False):
                cci = self._get_indicator_value("CCI")
                if not pd.isna(cci):
                    if cci < self.isd.cci_oversold:
                        contrib = weights.get("momentum_rsi_stoch_cci_wr_mfi", 0) * 0.4
                        signal_score += contrib
                        signal_breakdown["CCI"] = contrib
                    elif cci > self.isd.cci_overbought:
                        contrib = -weights.get("momentum_rsi_stoch_cci_wr_mfi", 0) * 0.4
                        signal_score += contrib
                        signal_breakdown["CCI"] = contrib
                        # Williams %R
            if active.get("wr", False):
                wr = self._get_indicator_value("WR")
                if not pd.isna(wr):
                    if wr < self.isd.williams_r_oversold:
                        contrib = weights.get("momentum_rsi_stoch_cci_wr_mfi", 0) * 0.4
                        signal_score += contrib
                        signal_breakdown["Williams %R"] = contrib
                    elif wr > self.isd.williams_r_overbought:
                        contrib = -weights.get("momentum_rsi_stoch_cci_wr_mfi", 0) * 0.4
                        signal_score += contrib
                        signal_breakdown["Williams %R"] = contrib

            # MFI
            if active.get("mfi", False):
                mfi = self._get_indicator_value("MFI")
                if not pd.isna(mfi):
                    if mfi < self.isd.mfi_oversold:
                        contrib = weights.get("momentum_rsi_stoch_cci_wr_mfi", 0) * 0.4
                        signal_score += contrib
                        signal_breakdown["MFI"] = contrib
                    elif mfi > self.isd.mfi_overbought:
                        contrib = -weights.get("momentum_rsi_stoch_cci_wr_mfi", 0) * 0.4
                        signal_score += contrib
                        signal_breakdown["MFI"] = contrib

        # Bollinger Bands
        if active.get("bollinger_bands", False):
            bb_upper = self._get_indicator_value("BB_Upper")
            bb_lower = self._get_indicator_value("BB_Lower")
            if not pd.isna(bb_upper) and not pd.isna(bb_lower):
                contrib = weights.get("bollinger_bands", 0) * 0.5
                if current_close < bb_lower:
                    signal_score += contrib
                    signal_breakdown["Bollinger Bands"] = contrib
                elif current_close > bb_upper:
                    signal_score -= contrib
                    signal_breakdown["Bollinger Bands"] = -contrib

        # VWAP
        if active.get("vwap", False):
            vwap = self._get_indicator_value("VWAP")
            if not pd.isna(vwap):
                contrib = weights.get("vwap", 0) * 0.2 * trend_strength
                if current_close > vwap:
                    signal_score += contrib
                    signal_breakdown["VWAP"] = contrib
                elif current_close < vwap:
                    signal_score -= contrib
                    signal_breakdown["VWAP"] = -contrib

        # Parabolic SAR
        if active.get("psar", False):
            psar_val = self._get_indicator_value("PSAR_Val")
            psar_dir = self._get_indicator_value("PSAR_Dir")
            if not pd.isna(psar_val) and not pd.isna(psar_dir):
                contrib = weights.get("psar", 0) * 0.5 * trend_strength
                if psar_dir == 1:
                    signal_score += contrib
                    signal_breakdown["PSAR"] = contrib
                elif psar_dir == -1:
                    signal_score -= contrib
                    signal_breakdown["PSAR"] = -contrib

        # MACD
        if active.get("macd", False):
            macd_line = self._get_indicator_value("MACD_Line")
            macd_signal = self._get_indicator_value("MACD_Signal")
            macd_hist = self._get_indicator_value("MACD_Hist")
            if not pd.isna(macd_line) and not pd.isna(macd_signal) and not pd.isna(macd_hist):
                contrib = weights.get("macd_alignment", 0) * trend_strength
                if macd_line > macd_signal and self.df["MACD_Line"].iloc[-2] <= self.df["MACD_Signal"].iloc[-2]:
                    signal_score += contrib
                    signal_breakdown["MACD"] = contrib
                elif macd_line < macd_signal and self.df["MACD_Line"].iloc[-2] >= self.df["MACD_Signal"].iloc[-2]:
                    signal_score -= contrib
                    signal_breakdown["MACD"] = -contrib
                elif macd_hist > 0 and self.df["MACD_Hist"].iloc[-2] < 0:
                    signal_score += contrib * 0.2
                    signal_breakdown["MACD"] = contrib * 0.2
                elif macd_hist < 0 and self.df["MACD_Hist"].iloc[-2] > 0:
                    signal_score -= contrib * 0.2
                    signal_breakdown["MACD"] = -contrib * 0.2

        # Ichimoku Cloud
        if active.get("ichimoku_cloud", False):
            tenkan = self._get_indicator_value("Tenkan_Sen")
            kijun = self._get_indicator_value("Kijun_Sen")
            senkou_a = self._get_indicator_value("Senkou_Span_A")
            senkou_b = self._get_indicator_value("Senkou_Span_B")
            chikou = self._get_indicator_value("Chikou_Span")

            if not any(pd.isna(val) for val in [tenkan, kijun, senkou_a, senkou_b, chikou]):
                contrib = weights.get("ichimoku_confluence", 0) * trend_strength

                # Tenkan/Kijun crossover
                if tenkan > kijun and self.df["Tenkan_Sen"].iloc[-2] <= self.df["Kijun_Sen"].iloc[-2]:
                    signal_score += contrib * 0.5
                    signal_breakdown["Ichimoku Cloud"] = contrib * 0.5
                elif tenkan < kijun and self.df["Tenkan_Sen"].iloc[-2] >= self.df["Kijun_Sen"].iloc[-2]:
                    signal_score -= contrib * 0.5
                    signal_breakdown["Ichimoku Cloud"] = -contrib * 0.5

                # Cloud breakout
                kumo_upper = max(senkou_a, senkou_b)
                kumo_lower = min(senkou_a, senkou_b)

                if current_close > kumo_upper and self.df["close"].iloc[-2] <= max(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]):
                    signal_score += contrib * 0.7
                    signal_breakdown["Ichimoku Cloud"] = contrib * 0.7
                elif current_close < kumo_lower and self.df["close"].iloc[-2] >= min(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]):
                    signal_score -= contrib * 0.7
                    signal_breakdown["Ichimoku Cloud"] = -contrib * 0.7

                # Chikou span confirmation
                if chikou > current_close and self.df["Chikou_Span"].iloc[-2] <= self.df["close"].iloc[-2]:
                    signal_score += contrib * 0.3
                    signal_breakdown["Ichimoku Cloud"] = contrib * 0.3
                elif chikou < current_close and self.df["Chikou_Span"].iloc[-2] >= self.df["close"].iloc[-2]:
                    signal_score -= contrib * 0.3
                    signal_breakdown["Ichimoku Cloud"] = -contrib * 0.3

        # Orderbook Imbalance
        if active.get("orderbook_imbalance", False) and orderbook_data:
            imbalance = self._check_orderbook(current_price, orderbook_data)
            contrib = imbalance * weights.get("orderbook_imbalance", 0)
            signal_score += contrib
            signal_breakdown["Orderbook Imbalance"] = contrib
            self.calculate_support_resistance_from_orderbook(orderbook_data)

        # Fib Levels
        if active.get("fibonacci_levels", False) and self.fib_levels:
            fib_contrib = 0.0
            for level_name, level_price in self.fib_levels.items():
                if level_name not in ["0.0%", "100.0%"] and current_price > 0:
                    price_diff_pct = abs((current_price - level_price) / current_price)
                    if price_diff_pct < Decimal("0.001"):
                        if current_close > prev_close and current_close > level_price:
                            fib_contrib += weights.get("fibonacci_levels", 0) * 0.1
                        elif current_close < prev_close and current_close < level_price:
                            fib_contrib -= weights.get("fibonacci_levels", 0) * 0.1
            signal_score += fib_contrib
            signal_breakdown["Fibonacci Levels"] = fib_contrib

        # Fib Pivot Points
        if active.get("fibonacci_pivot_points", False):
            pivot = self._get_indicator_value("Pivot")
            r1 = self._get_indicator_value("R1")
            r2 = self._get_indicator_value("R2")
            s1 = self._get_indicator_value("S1")
            s2 = self._get_indicator_value("S2")

            if not any(pd.isna(val) for val in [pivot, r1, r2, s1, s2]):
                fib_pivot_contrib = weights.get("fibonacci_pivot_points_confluence", 0)

                if current_close > r1 and prev_close <= r1:
                    signal_score += fib_pivot_contrib * 0.5
                    signal_breakdown["Fibonacci R1 Breakout"] = fib_pivot_contrib * 0.5
                elif current_close > r2 and prev_close <= r2:
                    signal_score += fib_pivot_contrib * 1.0
                    signal_breakdown["Fibonacci R2 Breakout"] = fib_pivot_contrib * 1.0
                elif current_close > pivot and prev_close <= pivot:
                    signal_score += fib_pivot_contrib * 0.2
                    signal_breakdown["Fibonacci Pivot Breakout"] = fib_pivot_contrib * 0.2

                if current_close < s1 and prev_close >= s1:
                    signal_score -= fib_pivot_contrib * 0.5
                    signal_breakdown["Fibonacci S1 Breakout"] = -fib_pivot_contrib * 0.5
                elif current_close < s2 and prev_close >= s2:
                    signal_score -= fib_pivot_contrib * 1.0
                    signal_breakdown["Fibonacci S2 Breakout"] = -fib_pivot_contrib * 0.5
                elif current_close < pivot and prev_close >= pivot:
                    signal_score -= fib_pivot_contrib * 0.2
                    signal_breakdown["Fibonacci Pivot Breakdown"] = -fib_pivot_contrib * 0.2

        # Volume Delta
        if active.get("volume_delta", False):
            vol_delta = self._get_indicator_value("Volume_Delta")
            vol_delta_threshold = self.isd.volume_delta_threshold
            if not pd.isna(vol_delta):
                weight = weights.get("volume_delta_signal", 0)
                if vol_delta > vol_delta_threshold:
                    signal_score += weight
                    signal_breakdown["Volume Delta"] = weight
                elif vol_delta < -vol_delta_threshold:
                    signal_score -= weight
                    signal_breakdown["Volume Delta"] = -weight
                elif vol_delta > 0:
                    signal_score += weight * 0.3
                    signal_breakdown["Volume Delta"] = weight * 0.3
                elif vol_delta < 0:
                    signal_score -= weight * 0.3
                    signal_breakdown["Volume Delta"] = -weight * 0.3

        # ROC
        if active.get("roc", False):
            roc = self._get_indicator_value("ROC")
            if not pd.isna(roc):
                weight = weights.get("roc_signal", 0)
                if roc < self.isd.roc_oversold:
                    signal_score += weight * 0.7
                    signal_breakdown["ROC"] = weight * 0.7
                elif roc > self.isd.roc_overbought:
                    signal_score -= weight * 0.7
                    signal_breakdown["ROC"] = -weight * 0.7

                if len(self.df) > 1 and "ROC" in self.df.columns:
                    prev_roc = self.df["ROC"].iloc[-2]
                    if roc > 0 and prev_roc <= 0:
                        signal_score += weight * 0.3 * trend_strength
                        signal_breakdown["ROC"] = weight * 0.3 * trend_strength
                    elif roc < 0 and prev_roc >= 0:
                        signal_score -= weight * 0.3 * trend_strength
                        signal_breakdown["ROC"] = -weight * 0.3 * trend_strength

        # Candlestick Patterns
        if active.get("candlestick_patterns", False):
            pattern = self._get_indicator_value("Candlestick_Pattern", "No Pattern")
            weight = weights.get("candlestick_confirmation", 0)

            if pattern == "Bullish Engulfing" or pattern == "Bullish Hammer":
                signal_score += weight
                signal_breakdown["Candlestick Pattern"] = weight
            elif pattern == "Bearish Engulfing" or pattern == "Bearish Shooting Star":
                signal_score -= weight
                signal_breakdown["Candlestick Pattern"] = -weight

        # Multi-Timeframe Analysis
        if self.config.mtf_analysis.enabled and mtf_trends:
            mtf_buy_count = sum(1 for trend in mtf_trends.values() if trend == "UP")
            mtf_sell_count = sum(1 for trend in mtf_trends.values() if trend == "DOWN")
            total_mtf_indicators = len(mtf_trends)

            mtf_weight = weights.get("mtf_trend_confluence", 0)

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

                signal_score += mtf_contribution
                signal_breakdown["MTF Confluence"] = mtf_contribution

        # Final signal determination
        threshold = self.config.signal_score_threshold
        final_signal = "HOLD"
        if signal_score >= threshold:
            final_signal = "BUY"
        elif signal_score <= -threshold:
            final_signal = "SELL"

        return final_signal, signal_score, signal_breakdown


    # ----------------------------------------------------------------------- #
    # Indicator Implementation Details
    # ----------------------------------------------------------------------- #
    def calculate_ichimoku_cloud(
        self,
        tenkan_period: int,
        kijun_period: int,
        senkou_span_b_period: int,
        chikou_span_offset: int,
    ) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
        high = self.df["high"]
        low = self.df["low"]
        close = self.df["close"]

        tenkan = (high.rolling(window=tenkan_period).max() + low.rolling(window=tenkan_period).min()) / 2
        kijun = (high.rolling(window=kijun_period).max() + low.rolling(window=kijun_period).min()) / 2

        senkou_a = ((tenkan + kijun) / 2).shift(kijun_period)
        senkou_b = ((high.rolling(window=senkou_span_b_period).max() + low.rolling(window=senkou_span_b_period).min()) / 2).shift(kijun_period)
        chikou = close.shift(-chikou_span_offset)

        return tenkan, kijun, senkou_a, senkou_b, chikou

    def calculate_fibonacci_levels(self) -> None:
        window = self.isd.fibonacci_window
        if len(self.df) < window:
            return

        recent = self.df.tail(window)
        high_val = recent["high"].max()
        low_val = recent["low"].min()
        diff = high_val - low_val

        price_precision_str = "0." + "0" * (self.config.trade_management.price_precision - 1) + "1"

        self.fib_levels = {
            "0.0%": Decimal(str(low_val)).quantize(Decimal(price_precision_str), rounding=ROUND_DOWN),
            "23.6%": Decimal(str(low_val + diff * Decimal("0.236"))).quantize(Decimal(price_precision_str), rounding=ROUND_DOWN),
            "38.2%": Decimal(str(low_val + diff * Decimal("0.382"))).quantize(Decimal(price_precision_str), rounding=ROUND_DOWN),
            "50.0%": Decimal(str(low_val + diff * Decimal("0.5"))).quantize(Decimal(price_precision_str), rounding=ROUND_DOWN),
            "61.8%": Decimal(str(low_val + diff * Decimal("0.618"))).quantize(Decimal(price_precision_str), rounding=ROUND_DOWN),
            "78.6%": Decimal(str(low_val + diff * Decimal("0.786"))).quantize(Decimal(price_precision_str), rounding=ROUND_DOWN),
            "100.0%": Decimal(str(high_val)).quantize(Decimal(price_precision_str), rounding=ROUND_DOWN),
        }

    def calculate_fibonacci_pivot_points(self) -> None:
        if len(self.df) < 2:
            return

        prev = self.df.iloc[-2]
        pivot = (prev["high"] + prev["low"] + prev["close"]) / 3

        price_precision_str = "0." + "0" * (self.config.trade_management.price_precision - 1) + "1"

        self.indicator_values["Pivot"] = pivot.quantize(Decimal(price_precision_str), rounding=ROUND_DOWN)
        self.indicator_values["R1"] = (2 * pivot - prev["low"]).quantize(Decimal(price_precision_str), rounding=ROUND_DOWN)
        self.indicator_values["R2"] = (pivot + (prev["high"] - prev["low"])).quantize(Decimal(price_precision_str), rounding=ROUND_DOWN)
        self.indicator_values["S1"] = (2 * pivot - prev["high"]).quantize(Decimal(price_precision_str), rounding=ROUND_DOWN)
        self.indicator_values["S2"] = (pivot - (prev["high"] - prev["low"])).quantize(Decimal(price_precision_str), rounding=ROUND_DOWN)


# --------------------------------------------------------------------------- #
# Display Functions
# --------------------------------------------------------------------------- #
def display_indicator_values_and_price(
    config: Config,
    logger: logging.Logger,
    current_price: Decimal,
    analyzer: TradingAnalyzer,
    orderbook_data: dict[str, Any] | None,
    mtf_trends: dict[str, str],
    signal_breakdown: dict[str, float] | None = None,
) -> None:
    """Display current market data, indicators, and signal breakdown."""

    logger.info(f"{NEON_BLUE}--- Current Market Data & Indicators ---{RESET}")
    logger.info(f"{NEON_GREEN}Current Price: {current_price.normalize()}{RESET}")

    if analyzer.df.empty:
        logger.warning(f"{NEON_YELLOW}Cannot display indicators: DataFrame is empty.{RESET}")
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
            logger.info(f"  {NEON_YELLOW}{level_name:<20}: {level_price.normalize()}{RESET}")

    if config.indicators.get("fibonacci_pivot_points", False):
        pivot = analyzer._get_indicator_value("Pivot")
        r1 = analyzer._get_indicator_value("R1")
        r2 = analyzer._get_indicator_value("R2")
        s1 = analyzer._get_indicator_value("S1")
        s2 = analyzer._get_indicator_value("S2")

        if all(val is not None for val in [pivot, r1, r2, s1, s2]):
            logger.info(f"{NEON_CYAN}--- Fibonacci Pivot Points ---{RESET}")
            logger.info(f"  {INDICATOR_COLORS.get('Pivot', NEON_YELLOW)}Pivot              : {pivot.normalize()}{RESET}")
            logger.info(f"  {INDICATOR_COLORS.get('R1', NEON_GREEN)}R1                 : {r1.normalize()}{RESET}")
            logger.info(f"  {INDICATOR_COLORS.get('R2', NEON_GREEN)}R2                 : {r2.normalize()}{RESET}")
            logger.info(f"  {INDICATOR_COLORS.get('S1', NEON_RED)}S1                 : {s1.normalize()}{RESET}")
            logger.info(f"  {INDICATOR_COLORS.get('S2', NEON_RED)}S2                 : {s2.normalize()}{RESET}")

    if mtf_trends:
        logger.info(f"{NEON_CYAN}--- Multi-Timeframe Trends ---{RESET}")
        for tf_indicator, trend in mtf_trends.items():
            logger.info(f"  {NEON_YELLOW}{tf_indicator:<20}: {trend}{RESET}")

    if signal_breakdown:
        logger.info(f"{NEON_CYAN}--- Signal Score Breakdown ---{RESET}")
        sorted_breakdown = sorted(
            signal_breakdown.items(),
            key=lambda item: abs(item[1]),
            reverse=True,
        )
        for indicator, contribution in sorted_breakdown:
            color = Fore.GREEN if contribution > 0 else (Fore.RED if contribution < 0 else Fore.YELLOW)
            logger.info(f"  {color}{indicator:<25}: {contribution: .2f}{RESET}")

    logger.info(f"{NEON_PURPLE}--- Current Trend Summary ---{RESET}")
    trend_summary_lines = []

    # EMA Cross
    ema_short = analyzer._get_indicator_value("EMA_Short")
    ema_long = analyzer._get_indicator_value("EMA_Long")
    if not pd.isna(ema_short) and not pd.isna(ema_long):
        if ema_short > ema_long:
            trend_summary_lines.append(f"{Fore.GREEN}EMA Cross  : ▲ Up{RESET}")
        elif ema_short < ema_long:
            trend_summary_lines.append(f"{Fore.RED}EMA Cross  : ▼ Down{RESET}")
        else:
            trend_summary_lines.append(f"{Fore.YELLOW}EMA Cross  : ↔ Sideways{RESET}")

    # ADX Trend
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

    # Ichimoku Position
    senkou_a = analyzer._get_indicator_value("Senkou_Span_A")
    senkou_b = analyzer._get_indicator_value("Senkou_Span_B")
    if not pd.isna(senkou_a) and not pd.isna(senkou_b):
        kumo_upper = max(senkou_a, senkou_b)
        kumo_lower = min(senkou_a, senkou_b)
        if current_price > kumo_upper:
            trend_summary_lines.append(f"{Fore.GREEN}Ichimoku   : Above Kumo{RESET}")
        elif current_price < kumo_lower:
            trend_summary_lines.append(f"{Fore.RED}Ichimoku   : Below Kumo{RESET}")
        else:
            trend_summary_lines.append(f"{Fore.YELLOW}Ichimoku   : Inside Kumo{RESET}")

    # MTF Summary
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


# --------------------------------------------------------------------------- #
# Main Execution
# --------------------------------------------------------------------------- #
def main() -> None:
    """Main trading bot execution loop."""

    # Load environment variables
    API_KEY = os.getenv("BYBIT_API_KEY")
    API_SECRET = os.getenv("BYBIT_API_SECRET")
    BASE_URL = os.getenv("BYBIT_BASE_URL", "https://api.bybit.com")

    if not API_KEY or not API_SECRET:
        print(f"{NEON_RED}Error: BYBIT_API_KEY and BYBIT_API_SECRET must be set in environment variables.{RESET}")
        sys.exit(1)

    # Setup logging and configuration
    logger = setup_logger("wgwhalex_bot")
    config = load_config(CONFIG_FILE, logger)
    alert_system = AlertSystem(logger)
    bybit_client = BybitClient(API_KEY, API_SECRET, BASE_URL, logger)

    # Validate intervals
    valid_intervals = ["1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D", "W", "M"]

    if config.interval not in valid_intervals:
        logger.error(f"{NEON_RED}Invalid primary interval '{config.interval}'. Exiting.{RESET}")
        sys.exit(1)

    for htf_interval in config.mtf_analysis.higher_timeframes:
        if htf_interval not in valid_intervals:
            logger.error(f"{NEON_RED}Invalid higher timeframe '{htf_interval}'. Exiting.{RESET}")
            sys.exit(1)

    logger.info(f"{NEON_GREEN}--- Whalebot Trading Bot Initialized ---{RESET}")
    logger.info(f"Symbol: {config.symbol}, Interval: {config.interval}")
    logger.info(f"Trade Management Enabled: {config.trade_management.enabled}")

    # Initialize managers
    position_manager = PositionManager(config, logger, config.symbol)
    performance_tracker = PerformanceTracker(logger, config)

    # Main trading loop
    while True:
        try:
            logger.info(f"{NEON_PURPLE}--- New Analysis Loop ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}) ---{RESET}")

            # Fetch current price
            current_price = bybit_client.fetch_current_price(config.symbol)
            if current_price is None:
                alert_system.send_alert(f"[{config.symbol}] Failed to fetch current price. Skipping loop.", "WARNING")
                time.sleep(config.loop_delay)
                continue

            # Fetch primary timeframe data
            df = bybit_client.fetch_klines(config.symbol, config.interval, 1000)
            if df is None or df.empty:
                alert_system.send_alert(f"[{config.symbol}] Failed to fetch klines. Skipping loop.", "WARNING")
                time.sleep(config.loop_delay)
                continue

            # Fetch orderbook if enabled
            orderbook_data = None
            if config.indicators.get("orderbook_imbalance", False):
                orderbook_data = bybit_client.fetch_orderbook(config.symbol, config.orderbook_limit)

            # Multi-timeframe analysis
            mtf_trends: dict[str, str] = {}
            if config.mtf_analysis.enabled:
                for htf_interval in config.mtf_analysis.higher_timeframes:
                    logger.debug(f"Fetching klines for MTF interval: {htf_interval}")
                    htf_df = bybit_client.fetch_klines(config.symbol, htf_interval, 1000)

                    if htf_df is not None and not htf_df.empty:
                        for trend_ind in config.mtf_analysis.trend_indicators:
                            temp_analyzer = TradingAnalyzer(
                                htf_df,
                                config,
                                logger,
                                config.symbol,
                            )
                            trend = temp_analyzer._get_mtf_trend(temp_analyzer.df, trend_ind)
                            mtf_trends[f"{htf_interval}_{trend_ind}"] = trend
                            logger.debug(f"MTF Trend ({htf_interval}, {trend_ind}): {trend}")
                    else:
                        logger.warning(f"{NEON_YELLOW}Could not fetch klines for {htf_interval}.{RESET}")

                    time.sleep(config.mtf_analysis.mtf_request_delay_seconds)

            # Initialize analyzer and calculate indicators
            analyzer = TradingAnalyzer(df, config, logger, config.symbol)
            if analyzer.df.empty:
                alert_system.send_alert(f"[{config.symbol}] DataFrame empty after indicator calculations.", "WARNING")
                time.sleep(config.loop_delay)
                continue

            # Generate trading signal
            trading_signal, signal_score, signal_breakdown = analyzer.generate_trading_signal(
                current_price,
                orderbook_data,
                mtf_trends,
            )

            # Get ATR value for position sizing
            atr_value = Decimal(str(analyzer._get_indicator_value("ATR", "0.01")))

            # Display market data and indicators
            display_indicator_values_and_price(
                config,
                logger,
                current_price,
                analyzer,
                orderbook_data,
                mtf_trends,
                signal_breakdown,
            )

            # Manage existing positions
            position_manager.manage_positions(current_price, performance_tracker)

            # Execute trading logic
            if trading_signal == "BUY" and signal_score >= config.signal_score_threshold:
                logger.info(f"{NEON_GREEN}Strong BUY signal detected! Score: {signal_score:.2f}{RESET}")
                position_manager.open_position("BUY", current_price, atr_value)
            elif trading_signal == "SELL" and signal_score <= -config.signal_score_threshold:
                logger.info(f"{NEON_RED}Strong SELL signal detected! Score: {signal_score:.2f}{RESET}")
                position_manager.open_position("SELL", current_price, atr_value)
            else:
                logger.info(f"{NEON_BLUE}No strong trading signal. Holding. Score: {signal_score:.2f}{RESET}")

            # Display open positions
            open_positions = position_manager.get_open_positions()
            if open_positions:
                logger.info(f"{NEON_CYAN}Open Positions: {len(open_positions)}{RESET}")
                for pos in open_positions:
                    logger.info(
                        f"  - {pos['side']} @ {pos['entry_price'].normalize()} "
                        f"(SL: {pos['stop_loss'].normalize()}, TP: {pos['take_profit'].normalize()}){RESET}",
                    )
            else:
                logger.info(f"{NEON_CYAN}No open positions.{RESET}")

            # Performance summary
            perf_summary = performance_tracker.get_summary()
            logger.info(
                f"{NEON_YELLOW}Performance: Total PnL: {perf_summary['total_pnl'].normalize():.2f}, "
                f"Wins: {perf_summary['wins']}, Losses: {perf_summary['losses']}, "
                f"Win Rate: {perf_summary['win_rate']}{RESET}",
            )

            logger.info(f"{NEON_PURPLE}--- Loop Finished. Waiting {config.loop_delay}s ---{RESET}")
            time.sleep(config.loop_delay)

        except Exception as e:
            alert_system.send_alert(f"[{config.symbol}] Main loop error: {e}", "ERROR")
            logger.exception(f"{NEON_RED}Unhandled exception in main loop:{RESET}")
            time.sleep(config.loop_delay * 2)


if __name__ == "__main__":
    main()

