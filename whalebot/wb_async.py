import asyncio
import hashlib
import hmac
import json
import logging
import os
import sys
import time
import urllib.parse
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal, getcontext
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, ClassVar, Literal

import httpx
import numpy as np
import pandas as pd
import websockets
from colorama import Fore, Style, init
from dotenv import load_dotenv

# --- Initial Setup ---
getcontext().prec = 28
init(autoreset=True)
load_dotenv()

# --- Neon Color Scheme ---
NEON_GREEN = Fore.LIGHTGREEN_EX
NEON_BLUE = Fore.CYAN
NEON_PURPLE = Fore.MAGENTA
NEON_YELLOW = Fore.YELLOW
NEON_RED = Fore.LIGHTRED_EX
NEON_CYAN = Fore.CYAN
RESET = Style.RESET_ALL

# --- Constants ---
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
BASE_URL = os.getenv("BYBIT_BASE_URL", "https://api.bybit.com")
WS_BASE_URL = "wss://stream.bybit.com/v5/public/linear"
CONFIG_FILE = "config.json"
LOG_DIRECTORY = "bot_logs/trading-bot/logs"
Path(LOG_DIRECTORY).mkdir(parents=True, exist_ok=True)

TIMEZONE = UTC
REQUEST_TIMEOUT = 20
MIN_DATA_POINTS_TR = 2
MIN_DATA_POINTS_SMOOTHER = 2
MIN_DATA_POINTS_OBV = 2
MIN_DATA_POINTS_PSAR = 2
ADX_STRONG_TREND_THRESHOLD = 25
ADX_WEAK_TREND_THRESHOLD = 20
MIN_DATA_POINTS_VWMA = 2
MIN_DATA_POINTS_VOLATILITY = 2
MIN_DATA_POINTS_KAMA = 2


# --- Configuration Management ---
def load_config(filepath: str, logger: logging.Logger) -> dict[str, Any]:
    default_config = {
        "symbol": "BTCUSDT",
        "interval": "15",
        "loop_delay": 15,
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
            "kama_period": 10,
            "kama_fast_period": 2,
            "kama_slow_period": 30,
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
            },
        },
    }
    if not Path(filepath).exists():
        try:
            with Path(filepath).open("w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)
            logger.warning(
                f"{NEON_YELLOW}Configuration file not found. Created default config at {filepath}{RESET}",
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
        logger.error(f"{NEON_RED}Error loading config: {e}. Using default.{RESET}")
        return default_config


def _ensure_config_keys(config: dict, default_config: dict) -> None:
    for key, default_value in default_config.items():
        if key not in config:
            config[key] = default_value
        elif isinstance(default_value, dict) and isinstance(config.get(key), dict):
            _ensure_config_keys(config[key], default_value)


class SensitiveFormatter(logging.Formatter):
    SENSITIVE_WORDS: ClassVar[list[str]] = ["API_KEY", "API_SECRET"]

    def __init__(self, fmt=None, datefmt=None, style="%"):
        super().__init__(fmt, datefmt, style)

    def format(self, record):
        msg = super().format(record)
        for word in self.SENSITIVE_WORDS:
            msg = msg.replace(word, "*" * len(word))
        return msg


def setup_logger(log_name: str, level=logging.INFO) -> logging.Logger:
    logger = logging.getLogger(log_name)
    logger.setLevel(level)
    logger.propagate = False
    if not logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(
            SensitiveFormatter(
                f"{NEON_BLUE}%(asctime)s - %(levelname)s - %(message)s{RESET}",
            ),
        )
        logger.addHandler(console_handler)
        log_file = Path(LOG_DIRECTORY) / f"{log_name}_async.log"
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


class PositionManager:
    def __init__(self, config: dict[str, Any], logger: logging.Logger, symbol: str):
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.open_positions: list[dict] = []
        self.trade_management_enabled = config["trade_management"]["enabled"]
        self.max_open_positions = config["trade_management"]["max_open_positions"]
        self.order_precision = config["trade_management"]["order_precision"]
        self.price_precision = config["trade_management"]["price_precision"]
        self.slippage_percent = Decimal(
            str(config["trade_management"].get("slippage_percent", 0.0)),
        )

    def _get_current_balance(self) -> Decimal:
        return Decimal(str(self.config["trade_management"]["account_balance"]))

    def _calculate_order_size(
        self,
        current_price: Decimal,
        atr_value: Decimal,
    ) -> Decimal:
        if not self.trade_management_enabled or atr_value <= 0:
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
            return Decimal("0")
        order_value = risk_amount / stop_loss_distance
        order_qty = order_value / current_price
        precision_str = "0." + "0" * (self.order_precision - 1) + "1"
        return order_qty.quantize(Decimal(precision_str), rounding=ROUND_DOWN)

    def open_position(
        self,
        signal: Literal["BUY", "SELL"],
        current_price: Decimal,
        atr_value: Decimal,
    ) -> dict | None:
        if (
            not self.trade_management_enabled
            or len(self.open_positions) >= self.max_open_positions
        ):
            return None
        order_qty = self._calculate_order_size(current_price, atr_value)
        if order_qty <= 0:
            return None
        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"]),
        )
        take_profit_atr_multiple = Decimal(
            str(self.config["trade_management"]["take_profit_atr_multiple"]),
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
                Decimal(price_precision_str),
                rounding=ROUND_DOWN,
            ),
            "qty": order_qty,
            "stop_loss": stop_loss.quantize(
                Decimal(price_precision_str),
                rounding=ROUND_DOWN,
            ),
            "take_profit": take_profit.quantize(
                Decimal(price_precision_str),
                rounding=ROUND_DOWN,
            ),
            "status": "OPEN",
        }
        self.open_positions.append(position)
        self.logger.info(
            f"{NEON_GREEN}[{self.symbol}] Opened {signal} position: {position}{RESET}",
        )
        return position

    def manage_positions(
        self,
        current_price: Decimal,
        performance_tracker: Any,
    ) -> None:
        if not self.trade_management_enabled or not self.open_positions:
            return
        positions_to_close = []
        for i, position in enumerate(self.open_positions):
            if position["status"] == "OPEN":
                closed_by = ""
                if position["side"] == "BUY":
                    if current_price <= position["stop_loss"]:
                        closed_by = "STOP_LOSS"
                    elif current_price >= position["take_profit"]:
                        closed_by = "TAKE_PROFIT"
                elif position["side"] == "SELL":
                    if current_price >= position["stop_loss"]:
                        closed_by = "STOP_LOSS"
                    elif current_price <= position["take_profit"]:
                        closed_by = "TAKE_PROFIT"
                if closed_by:
                    position["status"] = "CLOSED"
                    position["exit_time"] = datetime.now(TIMEZONE)
                    position["exit_price"] = current_price
                    position["closed_by"] = closed_by
                    positions_to_close.append(i)
                    pnl = (
                        (position["exit_price"] - position["entry_price"])
                        * position["qty"]
                        if position["side"] == "BUY"
                        else (position["entry_price"] - position["exit_price"])
                        * position["qty"]
                    )
                    performance_tracker.record_trade(position, pnl)
                    self.logger.info(
                        f"{NEON_PURPLE}[{self.symbol}] Closed {position['side']} by {closed_by}. PnL: {pnl:.2f}{RESET}",
                    )
        self.open_positions = [
            p for i, p in enumerate(self.open_positions) if i not in positions_to_close
        ]

    def get_open_positions(self) -> list[dict]:
        return [p for p in self.open_positions if p["status"] == "OPEN"]


class PerformanceTracker:
    def __init__(self, logger: logging.Logger, config: dict[str, Any]):
        self.logger = logger
        self.config = config
        self.trades: list[dict] = []
        self.total_pnl = Decimal("0")
        self.wins = 0
        self.losses = 0

    def record_trade(self, position: dict, pnl: Decimal) -> None:
        self.trades.append(position)
        self.total_pnl += pnl
        if pnl > 0:
            self.wins += 1
        else:
            self.losses += 1
        self.logger.info(
            f"{NEON_CYAN}Trade recorded. Total PnL: {self.total_pnl:.2f}, Wins: {self.wins}, Losses: {self.losses}{RESET}",
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
        self,
        message: str,
        level: Literal["INFO", "WARNING", "ERROR"],
    ) -> None:
        log_func = getattr(self.logger, level.lower(), self.logger.info)
        log_func(f"ALERT: {message}")


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
        self.indicator_values: dict[str, Any] = {}
        self.weights = config["weight_sets"]["default_scalping"]
        self.indicator_settings = config["indicator_settings"]
        if not self.df.empty:
            self._calculate_all_indicators()

    def _safe_calculate(
        self,
        func: callable,
        name: str,
        min_data_points: int = 0,
        *args,
        **kwargs,
    ) -> Any | None:
        if len(self.df) < min_data_points:
            return None
        try:
            return func(*args, **kwargs)
        except Exception as e:
            self.logger.error(
                f"{NEON_RED}[{self.symbol}] Error calculating '{name}': {e}{RESET}",
            )
            return None

    def _calculate_all_indicators(self) -> None:
        cfg = self.config
        isd = self.indicator_settings
        if cfg["indicators"].get("sma_10", False):
            self.df["SMA_10"] = self._safe_calculate(
                lambda: self.df["close"].rolling(window=isd["sma_short_period"]).mean(),
                "SMA_10",
                min_data_points=isd["sma_short_period"],
            )
        if cfg["indicators"].get("sma_trend_filter", False):
            self.df["SMA_Long"] = self._safe_calculate(
                lambda: self.df["close"].rolling(window=isd["sma_long_period"]).mean(),
                "SMA_Long",
                min_data_points=isd["sma_long_period"],
            )
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

    def calculate_true_range(self) -> pd.Series:
        high_low = self.df["high"] - self.df["low"]
        high_prev_close = (self.df["high"] - self.df["close"].shift()).abs()
        low_prev_close = (self.df["low"] - self.df["close"].shift()).abs()
        return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(
            axis=1,
        )

    def generate_trading_signal(
        self,
        current_price: Decimal,
        orderbook_data: dict,
        mtf_trends: dict,
    ) -> tuple[str, float]:
        signal_score = 0.0
        active_indicators = self.config["indicators"]
        weights = self.weights
        isd = self.indicator_settings
        if self.df.empty:
            return "HOLD", 0.0
        threshold = self.config["signal_score_threshold"]
        if signal_score >= threshold:
            return "BUY", signal_score
        if signal_score <= -threshold:
            return "SELL", signal_score
        return "HOLD", signal_score

    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        return self.indicator_values.get(key, default)


def generate_signature(payload: str, api_secret: str) -> str:
    return hmac.new(api_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


async def bybit_request(
    client: httpx.AsyncClient,
    method: Literal["GET", "POST"],
    endpoint: str,
    params: dict | None = None,
    signed: bool = False,
    logger: logging.Logger | None = None,
) -> dict | None:
    if logger is None:
        logger = setup_logger("bybit_api_async")
    url = f"{BASE_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}
    if signed:
        if not API_KEY or not API_SECRET:
            logger.error(f"{NEON_RED}API keys not set.{RESET}")
            return None
        timestamp = str(int(time.time() * 1000))
        recv_window = "20000"
        if method == "GET":
            query_string = urllib.parse.urlencode(params) if params else ""
            param_str = timestamp + API_KEY + recv_window + query_string
            headers.update(
                {
                    "X-BAPI-API-KEY": API_KEY,
                    "X-BAPI-TIMESTAMP": timestamp,
                    "X-BAPI-SIGN": generate_signature(param_str, API_SECRET),
                    "X-BAPI-RECV-WINDOW": recv_window,
                },
            )
            req = client.build_request(
                "GET",
                url,
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
        else:
            json_params = json.dumps(params) if params else ""
            param_str = timestamp + API_KEY + recv_window + json_params
            headers.update(
                {
                    "X-BAPI-API-KEY": API_KEY,
                    "X-BAPI-TIMESTAMP": timestamp,
                    "X-BAPI-SIGN": generate_signature(param_str, API_SECRET),
                    "X-BAPI-RECV-WINDOW": recv_window,
                },
            )
            req = client.build_request(
                "POST",
                url,
                json=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
    else:
        req = client.build_request(
            "GET",
            url,
            params=params,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
    try:
        response = await client.send(req)
        response.raise_for_status()
        data = response.json()
        if data.get("retCode") != 0:
            logger.error(f"{NEON_RED}Bybit API Error: {data.get('retMsg')}{RESET}")
            return None
        return data
    except (httpx.HTTPStatusError, httpx.RequestError, json.JSONDecodeError) as e:
        logger.error(f"{NEON_RED}Request failed: {e}{RESET}")
        return None


async def fetch_klines(
    client: httpx.AsyncClient,
    symbol: str,
    interval: str,
    limit: int,
    logger: logging.Logger,
) -> pd.DataFrame | None:
    endpoint = "/v5/market/kline"
    params = {
        "category": "linear",
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }
    response = await bybit_request(client, "GET", endpoint, params, logger=logger)
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
            df["start_time"].astype(int),
            unit="ms",
            utc=True,
        )
        for col in ["open", "high", "low", "close", "volume", "turnover"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df.set_index("start_time", inplace=True)
        df.sort_index(inplace=True)
        logger.info(f"Fetched {len(df)} initial klines for {symbol}.")
        return df
    logger.warning(f"{NEON_YELLOW}Could not fetch initial klines for {symbol}.{RESET}")
    return None


def update_kline_data(
    klines_df: pd.DataFrame,
    kline_data: dict,
) -> tuple[pd.DataFrame, bool]:
    new_kline_time = pd.to_datetime(int(kline_data["start"]), unit="ms", utc=True)
    is_new_candle = new_kline_time not in klines_df.index
    new_data = {
        "open": float(kline_data["open"]),
        "high": float(kline_data["high"]),
        "low": float(kline_data["low"]),
        "close": float(kline_data["close"]),
        "volume": float(kline_data["volume"]),
        "turnover": float(kline_data["turnover"]),
    }
    klines_df.loc[new_kline_time] = new_data
    if is_new_candle:
        klines_df.sort_index(inplace=True)
        if len(klines_df) > 1000:
            klines_df = klines_df.iloc[-1000:]
    return klines_df, is_new_candle


class TradingBot:
    def __init__(self, config: dict, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.symbol = config["symbol"]
        self.klines_df = pd.DataFrame()
        self.is_processing = False
        self.position_manager = PositionManager(config, logger, self.symbol)
        self.performance_tracker = PerformanceTracker(logger, config)
        self.alert_system = AlertSystem(logger)

    async def initialize(self, client: httpx.AsyncClient):
        self.klines_df = await fetch_klines(
            client,
            self.symbol,
            self.config["interval"],
            1000,
            self.logger,
        )
        return self.klines_df is not None and not self.klines_df.empty

    async def process_kline(self, kline_data: dict):
        if self.is_processing:
            return
        self.is_processing = True
        try:
            self.klines_df, is_new_candle = update_kline_data(
                self.klines_df.copy(),
                kline_data,
            )
            if not is_new_candle and not kline_data["confirm"]:
                return
            self.logger.info(
                f"Processing candle for {self.symbol} at {pd.to_datetime(int(kline_data['start']), unit='ms', utc=True)}",
            )
            analyzer = TradingAnalyzer(
                self.klines_df,
                self.config,
                self.logger,
                self.symbol,
            )
            signal, score = analyzer.generate_trading_signal(
                current_price=Decimal(kline_data["close"]),
                orderbook_data={},
                mtf_trends={},
            )
            self.logger.info(f"Signal: {signal}, Score: {score:.2f}")
            current_price = Decimal(kline_data["close"])
            self.position_manager.manage_positions(
                current_price,
                self.performance_tracker,
            )
            if (
                signal in ["BUY", "SELL"]
                and score >= self.config["signal_score_threshold"]
            ):
                atr_value = analyzer._get_indicator_value("ATR", default=Decimal("0"))
                if atr_value > 0:
                    self.position_manager.open_position(
                        signal,
                        current_price,
                        atr_value,
                    )
            self.logger.info(f"Performance: {self.performance_tracker.get_summary()}")
        finally:
            self.is_processing = False


async def websocket_handler(bot: TradingBot):
    logger = bot.logger
    symbol = bot.symbol
    interval = bot.config["interval"]
    topic = f"kline.{interval}.{symbol}"
    while True:
        try:
            async with websockets.connect(WS_BASE_URL) as websocket:
                await websocket.send(
                    json.dumps(
                        {
                            "op": "subscribe",
                            "req_id": f"kline_{symbol}_{interval}",
                            "args": [topic],
                        },
                    ),
                )
                while True:
                    data = json.loads(await websocket.recv())
                    if "topic" in data and "kline" in data["topic"]:
                        for kline in data["data"]:
                            await bot.process_kline(kline)
                    elif (
                        "op" in data
                        and data["op"] == "subscribe"
                        and data.get("success")
                    ):
                        logger.info(
                            f"{NEON_GREEN}Subscribed to {data['req_id']}{RESET}",
                        )
        except Exception as e:
            logger.error(f"{NEON_RED}WebSocket error: {e}. Reconnecting...{RESET}")
            await asyncio.sleep(10)


async def main():
    logger = setup_logger("whalebot_async")
    logger.info("Starting bot...")
    config = load_config(CONFIG_FILE, logger)
    if not config:
        return
    bot = TradingBot(config, logger)
    async with httpx.AsyncClient() as client:
        if not await bot.initialize(client):
            return
    await websocket_handler(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
