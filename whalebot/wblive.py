import json
import logging
import os
import random
import sys
import time
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal, getcontext
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, ClassVar, Literal

import indicators  # Import the new indicators module
import numpy as np
import pandas as pd
from alert_system import AlertSystem
from colorama import Fore, Style, init
from dotenv import dotenv_values

# Guarded import for the live trading client
try:
    import pybit.exceptions
    from pybit.unified_trading import HTTP as PybitHTTP

    PYBIT_AVAILABLE = True
except ImportError:
    PYBIT_AVAILABLE = False

# Initialize colorama and set decimal precision
getcontext().prec = 28
init(autoreset=True)

# --- Environment & API Key Loading ---
# Explicitly load .env values from the script's directory for robustness
script_dir = Path(__file__).resolve().parent
dotenv_path = script_dir / ".env"
config_env = dotenv_values(dotenv_path) if dotenv_path.exists() else {}

# --- Constants ---
API_KEY = config_env.get("BYBIT_API_KEY")
API_SECRET = config_env.get("BYBIT_API_SECRET")
BASE_URL = os.getenv("BYBIT_BASE_URL", "https://api.bybit.com")
CONFIG_FILE = "config.json"
BOT_STATE_FILE = "bot_state.json"  # New constant for bot state file
LOG_DIRECTORY = "bot_logs/trading-bot/logs"
Path(LOG_DIRECTORY).mkdir(parents=True, exist_ok=True)

TIMEZONE = UTC
MAX_API_RETRIES = 5
RETRY_DELAY_SECONDS = 7
REQUEST_TIMEOUT = 20
LOOP_DELAY_SECONDS = 15

# Neon Color Scheme
NEON_GREEN = Fore.LIGHTGREEN_EX
NEON_BLUE = Fore.CYAN
NEON_PURPLE = Fore.MAGENTA
NEON_YELLOW = Fore.YELLOW
NEON_RED = Fore.LIGHTRED_EX
NEON_CYAN = Fore.CYAN
RESET = Style.RESET_ALL


# --- Helper Functions for Precision ---
def round_qty(qty: Decimal, qty_step: Decimal) -> Decimal:
    if qty_step is None or qty_step.is_zero():
        return qty.quantize(Decimal("1.000000"), rounding=ROUND_DOWN)
    return (qty // qty_step) * qty_step


def round_price(price: Decimal, price_precision: int) -> Decimal:
    price_precision = max(price_precision, 0)
    return price.quantize(Decimal(f"1e-{price_precision}"), rounding=ROUND_DOWN)


# --- Bot State Management ---
def save_bot_state(
    config: dict,
    position_manager: Any,
    performance_tracker: Any,
    logger: logging.Logger,
):
    try:
        state_data = {
            "timestamp": datetime.now(TIMEZONE).isoformat(),
            "config_summary": {
                "symbol": config.get("symbol"),
                "interval": config.get("interval"),
                "loop_delay": config.get("loop_delay"),
                "use_pybit": config.get("execution", {}).get("use_pybit", False),
                "testnet": config.get("execution", {}).get("testnet", False),
            },
            "performance_summary": performance_tracker.get_summary(),
            "open_positions": [
                {
                    "entry_time": pos["entry_time"].isoformat()
                    if isinstance(pos["entry_time"], datetime)
                    else pos["entry_time"],
                    "symbol": pos["symbol"],
                    "side": pos["side"],
                    "entry_price": str(pos["entry_price"]),
                    "qty": str(pos["qty"]),
                    "stop_loss": str(pos["stop_loss"]),
                    "take_profit": str(pos["take_profit"]),
                    "status": pos["status"],
                }
                for pos in position_manager.get_open_positions()
            ],
            "current_price": str(config.get("_last_price", "---")),
            "last_signal": config.get("_last_signal", "HOLD"),
            "last_signal_score": config.get("_last_score", 0.0),
        }
        with open(BOT_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state_data, f, indent=4)
    except Exception as e:
        logger.error(f"{NEON_RED}Error saving bot state: {e}{RESET}")


# --- Configuration Management ---
def load_config(filepath: str, logger: logging.Logger) -> dict[str, Any]:
    default_config = {
        "symbol": "BTCUSDT",
        "interval": "15",
        "loop_delay": LOOP_DELAY_SECONDS,
        "orderbook_limit": 50,
        "signal_score_threshold": 2.0,
        "cooldown_sec": 60,
        "hysteresis_ratio": 0.85,
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
        "risk_guardrails": {
            "enabled": True,
            "max_day_loss_pct": 3.0,
            "max_drawdown_pct": 8.0,
            "cooldown_after_kill_min": 120,
            "spread_filter_bps": 5.0,
            "ev_filter_enabled": True,
        },
        "session_filter": {
            "enabled": False,
            "utc_allowed": [["00:00", "08:00"], ["13:00", "20:00"]],
        },
        "pyramiding": {
            "enabled": False,
            "max_adds": 2,
            "step_atr": 0.7,
            "size_pct_of_initial": 0.5,
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
                "ema_alignment": 0.30,
                "sma_trend_filter": 0.20,
                "ehlers_supertrend_alignment": 0.40,
                "macd_alignment": 0.30,
                "adx_strength": 0.25,
                "ichimoku_confluence": 0.35,
                "psar": 0.15,
                "vwap": 0.15,
                "vwma_cross": 0.10,
                "sma_10": 0.05,
                "bollinger_bands": 0.25,
                "momentum_rsi_stoch_cci_wr_mfi": 0.35,
                "volume_confirmation": 0.10,
                "obv_momentum": 0.15,
                "cmf_flow": 0.10,
                "volume_delta_signal": 0.10,
                "orderbook_imbalance": 0.10,
                "mtf_trend_confluence": 0.25,
                "volatility_index_signal": 0.10,
            },
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
            "proxies": {"enabled": False, "http": "", "https": ""},
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
            logger.warning(f"{NEON_YELLOW}Created default config at {filepath}{RESET}")
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
    for key, default_value in default_config.items():
        if key not in config:
            config[key] = default_value
        elif isinstance(default_value, dict) and isinstance(config.get(key), dict):
            _ensure_config_keys(config[key], default_value)


# --- Logging Setup ---
class SensitiveFormatter(logging.Formatter):
    SENSITIVE_WORDS: ClassVar[list[str]] = ["API_KEY", "API_SECRET"]

    def format(self, record):
        original_message = super().format(record)
        for word in self.SENSITIVE_WORDS:
            if word in original_message:
                original_message = original_message.replace(word, "*" * len(word))
        return original_message


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


# --- API Interaction & Live Trading ---
class PybitTradingClient:
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

        proxies = {}
        if self.cfg.get("execution", {}).get("proxies", {}).get("enabled", False):
            proxies = {
                "http": self.cfg["execution"]["proxies"].get("http"),
                "https": self.cfg["execution"]["proxies"].get("https"),
            }
            self.logger.info(f"{NEON_BLUE}Proxy enabled.{RESET}")

        try:
            self.session = PybitHTTP(
                api_key=API_KEY,
                api_secret=API_SECRET,
                testnet=self.testnet,
                timeout=REQUEST_TIMEOUT,
                proxies=proxies
                if proxies.get("http") or proxies.get("https")
                else None,
            )
            self.logger.info(
                f"{NEON_GREEN}PyBit client initialized. Testnet={self.testnet}{RESET}",
            )
        except (pybit.exceptions.FailedRequestError, Exception) as e:
            self.enabled = False
            self.session = None
            self.logger.error(f"{NEON_RED}Failed to init PyBit client: {e}{RESET}")

    def _handle_403_error(self, e):
        if "403" in str(e):
            self.logger.error(
                f"{NEON_RED}Encountered a 403 Forbidden error. This may be due to an IP rate limit or a geographical restriction (e.g., from the USA). The bot will pause for 60 seconds.{RESET}",
            )
            time.sleep(60)

    def _pos_idx(self, side: Literal["BUY", "SELL"]) -> int:
        pmode = self.cfg["execution"].get("position_mode", "ONE_WAY").upper()
        overrides = self.cfg["execution"].get("position_idx_overrides", {})
        if pmode == "ONE_WAY":
            return int(overrides.get("ONE_WAY", 0))
        return int(
            overrides.get(
                "HEDGE_BUY" if side == "BUY" else "HEDGE_SELL",
                1 if side == "BUY" else 2,
            ),
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
                f"{NEON_RED}{action}: Error {resp.get('retCode')} - {resp.get('retMsg')}{RESET}",
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
        except (
            pybit.exceptions.InvalidRequestError,
            pybit.exceptions.PybitHTTPException,
        ) as e:
            self.logger.error(
                f"{NEON_RED}set_leverage failed: {e}. Please check symbol, leverage, and account status.{RESET}",
            )
            self._handle_403_error(e)
            return False

    def get_positions(self, symbol: str | None = None) -> dict | None:
        if not self.enabled:
            return None
        try:
            params = {"category": self.category}
            if symbol:
                params["symbol"] = symbol
            return self.session.get_positions(**params)
        except pybit.exceptions.FailedRequestError as e:
            self.logger.error(f"{NEON_RED}get_positions exception: {e}{RESET}")
            self._handle_403_error(e)
            return None

    def get_wallet_balance(self, coin: str = "USDT") -> dict | None:
        if not self.enabled:
            return None
        try:
            return self.session.get_wallet_balance(
                accountType=self.cfg["execution"].get("account_type", "UNIFIED"),
                coin=coin,
            )
        except pybit.exceptions.FailedRequestError as e:
            self.logger.error(f"{NEON_RED}get_wallet_balance exception: {e}{RESET}")
            self._handle_403_error(e)
            return None

    def place_order(self, **kwargs) -> dict | None:
        if not self.enabled:
            return None
        try:
            resp = self.session.place_order(**kwargs)
            self._log_api("place_order", resp)
            return resp
        except pybit.exceptions.FailedRequestError as e:
            self.logger.error(f"{NEON_RED}place_order exception: {e}{RESET}")
            self._handle_403_error(e)
            return None

    def fetch_current_price(self, symbol: str) -> Decimal | None:
        if not self.enabled:
            return None
        try:
            response = self.session.get_tickers(category="linear", symbol=symbol)
            if (
                response
                and response.get("retCode") == 0
                and response.get("result", {}).get("list")
            ):
                return Decimal(response["result"]["list"][0]["lastPrice"])
            self.logger.warning(
                f"{NEON_YELLOW}Could not fetch current price for {symbol}.{RESET}",
            )
            return None
        except pybit.exceptions.FailedRequestError as e:
            self.logger.error(f"{NEON_RED}fetch_current_price exception: {e}{RESET}")
            self._handle_403_error(e)
            return None

    def fetch_instrument_info(self, symbol: str) -> dict | None:
        if not self.enabled:
            return None
        try:
            response = self.session.get_instruments_info(
                category="linear",
                symbol=symbol,
            )
            if (
                response
                and response.get("retCode") == 0
                and response.get("result", {}).get("list")
            ):
                return response["result"]["list"][0]
            self.logger.warning(
                f"{NEON_YELLOW}Could not fetch instrument info for {symbol}.{RESET}",
            )
            return None
        except pybit.exceptions.FailedRequestError as e:
            self.logger.error(f"{NEON_RED}fetch_instrument_info exception: {e}{RESET}")
            self._handle_403_error(e)
            return None

    def fetch_klines(
        self,
        symbol: str,
        interval: str,
        limit: int,
    ) -> pd.DataFrame | None:
        if not self.enabled:
            return None
        try:
            params = {
                "category": "linear",
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
            }
            response = self.session.get_kline(**params)
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
                ).dt.tz_convert(TIMEZONE)
                for col in ["open", "high", "low", "close", "volume", "turnover"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df.set_index("start_time", inplace=True)
                df.sort_index(inplace=True)
                return df if not df.empty else None
            self.logger.warning(
                f"{NEON_YELLOW}Could not fetch klines for {symbol} {interval}.{RESET}",
            )
            return None
        except pybit.exceptions.FailedRequestError as e:
            self.logger.error(f"{NEON_RED}fetch_klines exception: {e}{RESET}")
            self._handle_403_error(e)
            return None

    def fetch_orderbook(self, symbol: str, limit: int) -> dict | None:
        if not self.enabled:
            return None
        try:
            response = self.session.get_orderbook(
                category="linear",
                symbol=symbol,
                limit=limit,
            )
            if response and response.get("result"):
                return response["result"]
            self.logger.warning(
                f"{NEON_YELLOW}Could not fetch orderbook for {symbol}.{RESET}",
            )
            return None
        except pybit.exceptions.FailedRequestError as e:
            self.logger.error(f"{NEON_RED}fetch_orderbook exception: {e}{RESET}")
            self._handle_403_error(e)
            return None

    def batch_place_orders(self, requests: list[dict]) -> dict | None:
        if not self.enabled:
            return None
        try:
            resp = self.session.batch_place_order(
                category=self.category,
                request=requests,
            )
            self._log_api("batch_place_order", resp)
            return resp
        except pybit.exceptions.FailedRequestError as e:
            self.logger.error(f"{NEON_RED}batch_place_orders exception: {e}{RESET}")
            return None

    def cancel_by_link_id(self, symbol: str, order_link_id: str) -> dict | None:
        if not self.enabled:
            return None
        try:
            resp = self.session.cancel_order(
                category=self.category,
                symbol=symbol,
                orderLinkId=order_link_id,
            )
            self._log_api("cancel_by_link_id", resp)
            return resp
        except pybit.exceptions.FailedRequestError as e:
            self.logger.error(f"{NEON_RED}cancel_by_link_id exception: {e}{RESET}")
            return None

    def get_executions(
        self,
        symbol: str,
        start_time_ms: int,
        limit: int,
    ) -> dict | None:
        if not self.enabled:
            return None
        try:
            return self.session.get_executions(
                category=self.category,
                symbol=symbol,
                startTime=start_time_ms,
                limit=limit,
            )
        except pybit.exceptions.FailedRequestError as e:
            self.logger.error(f"{NEON_RED}get_executions exception: {e}{RESET}")
            return None


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
                (entry_price + atr_value * Decimal(str(t["atr_multiple"])))
                if side == "BUY"
                else (entry_price - atr_value * Decimal(str(t["atr_multiple"])))
            )
        else:
            price = (
                (entry_price * (1 + Decimal(str(t.get("percent", 1))) / 100))
                if side == "BUY"
                else (entry_price * (1 - Decimal(str(t.get("percent", 1))) / 100))
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
                "post_only": bool(
                    t.get("post_only", ex.get("post_only_default", False)),
                ),
                "link_id_suffix": f"tp{i}",
            },
        )
    return out


# --- Position Management ---
class PositionManager:
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
        self.order_precision = config["trade_management"]["order_precision"]
        self.price_precision = config["trade_management"]["price_precision"]
        self.qty_step = None
        self.pybit = pybit_client
        self.live = bool(config.get("execution", {}).get("use_pybit", False))
        self._update_precision_from_exchange()

    def _update_precision_from_exchange(self):
        if not self.pybit or not self.pybit.enabled:
            self.logger.warning(
                f"Pybit client not enabled. Using config precision for {self.symbol}.",
            )
            return
        info = self.pybit.fetch_instrument_info(self.symbol)
        if info:
            if "lotSizeFilter" in info:
                self.qty_step = Decimal(str(info["lotSizeFilter"].get("qtyStep")))
                if not self.qty_step.is_zero():
                    self.order_precision = abs(self.qty_step.as_tuple().exponent)
                self.logger.info(
                    f"Updated qty_step: {self.qty_step}, order_precision: {self.order_precision}",
                )
            if "priceFilter" in info:
                tick_size = Decimal(str(info["priceFilter"].get("tickSize")))
                if not tick_size.is_zero():
                    self.price_precision = abs(tick_size.as_tuple().exponent)
                self.logger.info(f"Updated price_precision: {self.price_precision}")
        else:
            self.logger.warning(
                f"Could not fetch precision for {self.symbol}. Using config values.",
            )

    def _get_current_balance(self) -> Decimal:
        if self.live and self.pybit and self.pybit.enabled:
            resp = self.pybit.get_wallet_balance(coin="USDT")
            if resp and self.pybit._ok(resp) and resp.get("result", {}).get("list"):
                for coin_balance in resp["result"]["list"][0]["coin"]:
                    if coin_balance["coin"] == "USDT":
                        return Decimal(coin_balance["walletBalance"])
        return Decimal(str(self.config["trade_management"]["account_balance"]))

    def _calculate_order_size(
        self,
        current_price: Decimal,
        atr_value: Decimal,
        conviction: float = 1.0,
    ) -> Decimal:
        if not self.trade_management_enabled:
            return Decimal("0")
        account_balance = self._get_current_balance()
        base_risk_pct = (
            Decimal(str(self.config["trade_management"]["risk_per_trade_percent"]))
            / 100
        )
        risk_pct = base_risk_pct * Decimal(str(np.clip(0.5 + conviction, 0.5, 1.5)))
        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"]),
        )
        risk_amount = account_balance * risk_pct
        stop_loss_distance = atr_value * stop_loss_atr_multiple
        if stop_loss_distance <= 0:
            self.logger.warning(
                f"{NEON_YELLOW}Stop loss distance is zero. Cannot calculate order size.{RESET}",
            )
            return Decimal("0")
        order_qty = (risk_amount / stop_loss_distance) / current_price
        return (
            round_qty(order_qty, self.qty_step)
            if self.qty_step
            else order_qty.quantize(
                Decimal(f"1e-{self.order_precision}"),
                rounding=ROUND_DOWN,
            )
        )

    def open_position(
        self,
        signal: Literal["BUY", "SELL"],
        current_price: Decimal,
        atr_value: Decimal,
        conviction: float,
    ) -> dict | None:
        if self.live and self.pybit and self.pybit.enabled:
            positions_resp = self.pybit.get_positions(self.symbol)
            if positions_resp and self.pybit._ok(positions_resp):
                pos_list = positions_resp.get("result", {}).get("list", [])
                if any(p.get("size") and Decimal(p.get("size")) > 0 for p in pos_list):
                    self.logger.warning(
                        f"{NEON_YELLOW}Exchange position exists, aborting new position.{RESET}",
                    )
                    return None

        if (
            not self.trade_management_enabled
            or len(self.open_positions) >= self.max_open_positions
        ):
            self.logger.info(
                f"{NEON_YELLOW}Cannot open new position (max reached or disabled).{RESET}",
            )
            return None

        order_qty = self._calculate_order_size(current_price, atr_value, conviction)
        if order_qty <= 0:
            self.logger.warning(
                f"{NEON_YELLOW}Order quantity is zero. Cannot open position.{RESET}",
            )
            return None

        stop_loss = self._compute_stop_loss_price(signal, current_price, atr_value)
        take_profit = self._calculate_take_profit_price(
            signal,
            current_price,
            atr_value,
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
            "link_prefix": f"wgx_{int(time.time() * 1000)}",
            "adds": 0,
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
                self.logger.error(
                    f"{NEON_RED}Live entry failed. Simulating only.{RESET}",
                )
            else:
                self.logger.info(
                    f"{NEON_GREEN}Live entry submitted: {entry_link}{RESET}",
                )
                if self.config["execution"]["tpsl_mode"] == "Partial":
                    targets = build_partial_tp_targets(
                        signal,
                        position["entry_price"],
                        atr_value,
                        order_qty,
                        self.config,
                        self.qty_step,
                    )
                    for t in targets:
                        payload = {
                            "symbol": self.symbol,
                            "side": self.pybit._side_to_bybit(
                                "SELL" if signal == "BUY" else "BUY",
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
                        resp_tp = self.pybit.place_order(**payload)
                        if resp_tp and resp_tp.get("retCode") == 0:
                            self.logger.info(
                                f"{NEON_GREEN}Placed individual TP target: {payload.get('orderLinkId')}{RESET}",
                            )
                        else:
                            self.logger.error(
                                f"{NEON_RED}Failed to place TP target: {payload.get('orderLinkId')}. Error: {resp_tp.get('retMsg') if resp_tp else 'No response'}{RESET}",
                            )

                if self.config["execution"]["sl_scheme"]["use_conditional_stop"]:
                    sl_link = f"{position['link_prefix']}_sl"
                    sresp = self.pybit.place_order(
                        category=self.pybit.category,
                        symbol=self.symbol,
                        side=self.pybit._side_to_bybit(
                            "SELL" if signal == "BUY" else "BUY",
                        ),
                        orderType=self.config["execution"]["sl_scheme"][
                            "stop_order_type"
                        ],
                        qty=self.pybit._q(order_qty),
                        reduceOnly=True,
                        orderLinkId=sl_link,
                        triggerPrice=self.pybit._q(stop_loss),
                        triggerDirection=(2 if signal == "BUY" else 1),
                        orderFilter="Stop",
                    )
                    if self.pybit._ok(sresp):
                        self.logger.info(
                            f"{NEON_GREEN}Conditional stop placed at {stop_loss}.{RESET}",
                        )

        self.open_positions.append(position)
        self.logger.info(
            f"{NEON_GREEN}Opened {signal} position (simulated): {position}{RESET}",
        )
        return position

    def manage_positions(self, current_price: Decimal, performance_tracker: Any):
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
                        },
                    )
                    pnl = (
                        ((current_price - pos["entry_price"]) * pos["qty"])
                        if pos["side"] == "BUY"
                        else ((pos["entry_price"] - current_price) * pos["qty"])
                    )
                    performance_tracker.record_trade(pos, pnl)
                    self.logger.info(
                        f"{NEON_PURPLE}Closed {pos['side']} by {closed_by}. PnL: {pnl:.2f}{RESET}",
                    )
                    positions_to_close.append(i)
        self.open_positions = [
            p for i, p in enumerate(self.open_positions) if i not in positions_to_close
        ]

    def get_open_positions(self) -> list[dict]:
        return [pos for pos in self.open_positions if pos["status"] == "OPEN"]

    def _compute_stop_loss_price(
        self,
        side: Literal["BUY", "SELL"],
        entry_price: Decimal,
        atr_value: Decimal,
    ) -> Decimal:
        ex = self.config["execution"]
        sch = ex["sl_scheme"]
        price_prec = self.config["trade_management"]["price_precision"]
        tick_size = Decimal(f"1e-{price_prec}")
        buffer = tick_size * 5
        if sch["type"] == "atr_multiple":
            sl = (
                (entry_price - atr_value * Decimal(str(sch["atr_multiple"])))
                if side == "BUY"
                else (entry_price + atr_value * Decimal(str(sch["atr_multiple"])))
            )
        else:
            sl = (
                (entry_price * (1 - Decimal(str(sch["percent"])) / 100))
                if side == "BUY"
                else (entry_price * (1 + Decimal(str(sch["percent"])) / 100))
            )
        sl_with_buffer = sl - buffer if side == "BUY" else sl + buffer
        return round_price(sl_with_buffer, price_prec)

    def _calculate_take_profit_price(
        self,
        signal: Literal["BUY", "SELL"],
        current_price: Decimal,
        atr_value: Decimal,
    ) -> Decimal:
        tp_mult = Decimal(
            str(self.config["trade_management"]["take_profit_atr_multiple"]),
        )
        tp = (
            (current_price + (atr_value * tp_mult))
            if signal == "BUY"
            else (current_price - (atr_value * tp_mult))
        )
        return round_price(tp, self.price_precision)

    def trail_stop(self, pos: dict, current_price: Decimal, atr_value: Decimal):
        if pos.get("status") != "OPEN" or self.live:
            return
        atr_mult = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"]),
        )
        side = pos["side"]
        pos["best_price"] = pos.get("best_price", pos["entry_price"])
        if side == "BUY":
            pos["best_price"] = max(pos["best_price"], current_price)
            new_sl = round_price(
                pos["best_price"] - atr_mult * atr_value,
                self.price_precision,
            )
            pos["stop_loss"] = max(pos["stop_loss"], new_sl)
        else:  # SELL
            pos["best_price"] = min(pos["best_price"], current_price)
            new_sl = round_price(
                pos["best_price"] + atr_mult * atr_value,
                self.price_precision,
            )
            pos["stop_loss"] = min(pos["stop_loss"], new_sl)

    def try_pyramid(self, current_price: Decimal, atr_value: Decimal):
        if not self.trade_management_enabled or not self.open_positions or self.live:
            return
        py_cfg = self.config.get("pyramiding", {})
        if not py_cfg.get("enabled", False):
            return
        for pos in self.open_positions:
            if pos.get("status") != "OPEN":
                continue
            adds = pos.get("adds", 0)
            if adds >= int(py_cfg.get("max_adds", 0)):
                continue
            step = Decimal(str(py_cfg.get("step_atr", 0.7))) * atr_value
            target = (
                pos["entry_price"] + step * (adds + 1)
                if pos["side"] == "BUY"
                else pos["entry_price"] - step * (adds + 1)
            )
            if (pos["side"] == "BUY" and current_price >= target) or (
                pos["side"] == "SELL" and current_price <= target
            ):
                add_qty = round_qty(
                    pos["qty"] * Decimal(str(py_cfg.get("size_pct_of_initial", 0.5))),
                    self.qty_step or Decimal("0.0001"),
                )
                if add_qty > 0:
                    total_cost = (pos["qty"] * pos["entry_price"]) + (
                        add_qty * current_price
                    )
                    pos["qty"] += add_qty
                    pos["entry_price"] = total_cost / pos["qty"]
                    pos["adds"] = adds + 1
                    self.logger.info(
                        f"{NEON_GREEN}Pyramiding add #{pos['adds']} qty={add_qty}. New avg price: {pos['entry_price']:.2f}{RESET}",
                    )


# --- Performance Tracking & Sync ---
class PerformanceTracker:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.trades: list[dict] = []
        self.total_pnl = Decimal("0")
        self.gross_profit = Decimal("0")
        self.gross_loss = Decimal("0")
        self.wins = 0
        self.losses = 0
        self.peak_pnl = Decimal("0")
        self.max_drawdown = Decimal("0")

    def record_trade(self, position: dict, pnl: Decimal):
        self.trades.append({**position, "pnl": pnl})
        self.total_pnl += pnl
        if pnl > 0:
            self.wins += 1
            self.gross_profit += pnl
        else:
            self.losses += 1
            self.gross_loss += abs(pnl)
        self.peak_pnl = max(self.peak_pnl, self.total_pnl)
        drawdown = self.peak_pnl - self.total_pnl
        self.max_drawdown = max(self.max_drawdown, drawdown)
        self.logger.info(
            f"{NEON_CYAN}Trade recorded. PnL: {pnl:.4f}. Total PnL: {self.total_pnl:.4f}{RESET}",
        )

    def day_pnl(self) -> Decimal:
        if not self.trades:
            return Decimal("0")
        today = datetime.now(TIMEZONE).date()
        pnl = Decimal("0")
        for t in self.trades:
            et = t.get("exit_time") or t.get("entry_time")
            if et and et.date() == today:
                pnl += Decimal(str(t.get("pnl", "0")))
        return pnl

    def get_summary(self) -> dict:
        total_trades = len(self.trades)
        win_rate = (self.wins / total_trades) * 100 if total_trades > 0 else 0
        profit_factor = (
            self.gross_profit / self.gross_loss
            if self.gross_loss > 0
            else Decimal("inf")
        )
        avg_win = self.gross_profit / self.wins if self.wins > 0 else Decimal("0")
        avg_loss = self.gross_loss / self.losses if self.losses > 0 else Decimal("0")
        return {
            "total_trades": total_trades,
            "total_pnl": f"{self.total_pnl:.4f}",
            "gross_profit": f"{self.gross_profit:.4f}",
            "gross_loss": f"{self.gross_loss:.4f}",
            "profit_factor": f"{profit_factor:.2f}",
            "max_drawdown": f"{self.max_drawdown:.4f}",
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": f"{win_rate:.2f}%",
            "avg_win": f"{avg_win:.4f}",
            "avg_loss": f"{avg_loss:.4f}",
        }


class ExchangeExecutionSync:
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
        self,
        side: str,
        entry_price: Decimal,
        atr_value: Decimal,
    ) -> Decimal:
        be_cfg = self.cfg["execution"]["breakeven_after_tp1"]
        off_type = str(be_cfg.get("offset_type", "atr")).lower()
        off_val = Decimal(str(be_cfg.get("offset_value", 0)))
        if off_type == "atr":
            adj = atr_value * off_val
        elif off_type == "percent":
            adj = entry_price * (off_val / Decimal("100"))
        else:
            adj = off_val
        lock_adj = entry_price * (
            Decimal(str(be_cfg.get("lock_in_min_percent", 0))) / Decimal("100")
        )
        be = (
            entry_price + max(adj, lock_adj)
            if side == "BUY"
            else entry_price - max(adj, lock_adj)
        )
        return round_price(be, self.pm.price_precision)

    def _move_stop_to_breakeven(self, open_pos: dict, atr_value: Decimal):
        if not self.cfg["execution"]["breakeven_after_tp1"].get("enabled", False):
            return
        try:
            entry, side = Decimal(str(open_pos["entry_price"])), open_pos["side"]
            new_sl = self._compute_be_price(side, entry, atr_value)
            link_prefix = open_pos.get("link_prefix")
            old_sl_link = f"{link_prefix}_sl" if link_prefix else None
            if old_sl_link:
                self.pybit.cancel_by_link_id(self.symbol, old_sl_link)
            new_sl_link = (
                f"{link_prefix}_sl_be"
                if link_prefix
                else f"wgx_{int(time.time() * 1000)}_sl_be"
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
                self.logger.info(
                    f"{NEON_GREEN}Moved SL to breakeven at {new_sl}.{RESET}",
                )
        except (pybit.exceptions.FailedRequestError, Exception) as e:
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
                    else (
                        "SL"
                        if "_sl" in link
                        else ("TP" if "_tp" in link else "UNKNOWN")
                    )
                )
                open_pos = next(
                    (p for p in self.pm.open_positions if p.get("status") == "OPEN"),
                    None,
                )
                if tag in ("TP", "SL") and open_pos:
                    is_reduce = (
                        open_pos["side"] == "BUY" and r.get("side") == "Sell"
                    ) or (open_pos["side"] == "SELL" and r.get("side") == "Buy")
                    if is_reduce:
                        exec_qty, exec_price = (
                            Decimal(str(r.get("execQty", "0"))),
                            Decimal(str(r.get("execPrice", "0"))),
                        )
                        pnl = (
                            ((exec_price - open_pos["entry_price"]) * exec_qty)
                            if open_pos["side"] == "BUY"
                            else ((open_pos["entry_price"] - exec_price) * exec_qty)
                        )
                        self.pt.record_trade(
                            {
                                "exit_time": datetime.fromtimestamp(
                                    ts_ms / 1000,
                                    tz=TIMEZONE,
                                ),
                                "exit_price": exec_price,
                                "qty": exec_qty,
                                "closed_by": tag,
                                **open_pos,
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
                                        ts_ms / 1000,
                                        tz=TIMEZONE,
                                    ),
                                    "exit_price": exec_price,
                                    "closed_by": tag,
                                },
                            )
                            self.logger.info(
                                f"{NEON_PURPLE}Position fully closed by {tag}.{RESET}",
                            )
                    if tag == "TP" and link.endswith("_tp1"):
                        atr_val = Decimal(str(self.cfg.get("_last_atr", "0.1")))
                        self._move_stop_to_breakeven(open_pos, atr_val)
            self.pm.open_positions = [
                p for p in self.pm.open_positions if p.get("status") == "OPEN"
            ]
        except (pybit.exceptions.FailedRequestError, Exception) as e:
            self.logger.error(f"{NEON_RED}Execution sync error: {e}{RESET}")


class PositionHeartbeat:
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
                (p for p in self.pm.open_positions if p.get("status") == "OPEN"),
                None,
            )
            if net_qty == 0 and local:
                local.update({"status": "CLOSED", "closed_by": "HEARTBEAT_SYNC"})
                self.logger.info(
                    f"{NEON_PURPLE}Heartbeat: Closed local position (exchange flat).{RESET}",
                )
                self.pm.open_positions = [
                    p for p in self.pm.open_positions if p.get("status") == "OPEN"
                ]
            elif net_qty != 0 and not local:
                avg_price = (
                    Decimal(lst[0].get("avgPrice", "0")) if lst else Decimal("0")
                )
                side = "BUY" if net_qty > 0 else "SELL"
                synt = {
                    "entry_time": datetime.now(TIMEZONE),
                    "symbol": self.symbol,
                    "side": side,
                    "entry_price": round_price(avg_price, self.pm.price_precision),
                    "qty": round_qty(abs(net_qty), self.pm.qty_step),
                    "status": "OPEN",
                    "link_prefix": f"hb_{int(time.time() * 1000)}",
                }
                self.pm.open_positions.append(synt)
                self.logger.info(
                    f"{NEON_YELLOW}Heartbeat: Created synthetic local position.{RESET}",
                )
        except (pybit.exceptions.FailedRequestError, Exception) as e:
            self.logger.error(f"{NEON_RED}Heartbeat error: {e}{RESET}")


# --- Trading Analysis ---
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
        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}TradingAnalyzer initialized with empty DataFrame.{RESET}",
            )
            return
        self._calculate_all_indicators()

    def _safe_calculate(self, func: callable, name: str, *args, **kwargs) -> Any | None:
        try:
            if (
                "df" in func.__code__.co_varnames
                and func.__code__.co_varnames[0] == "df"
            ):
                result = func(self.df, *args, **kwargs)
            else:
                result = func(*args, **kwargs)
            is_empty = (
                result is None
                or (isinstance(result, pd.Series) and result.empty)
                or (
                    isinstance(result, tuple)
                    and all(
                        r is None or (isinstance(r, pd.Series) and r.empty)
                        for r in result
                    )
                )
            )
            if is_empty:
                self.logger.warning(
                    f"{NEON_YELLOW}[{self.symbol}] Indicator '{name}' returned empty.{RESET}",
                )
            return result if not is_empty else None
        except Exception as e:
            self.logger.error(
                f"{NEON_RED}[{self.symbol}] Error calculating '{name}': {e}{RESET}",
            )
            return None

    def _calculate_all_indicators(self) -> None:
        self.logger.debug(f"[{self.symbol}] Calculating all technical indicators...")
        cfg = self.config
        isd = self.indicator_settings

        if cfg["indicators"].get("sma_10", False):
            self.df["SMA_10"] = self._safe_calculate(
                indicators.calculate_sma,
                "SMA_10",
                period=isd["sma_short_period"],
            )
            if self.df["SMA_10"] is not None and not self.df["SMA_10"].empty:
                self.indicator_values["SMA_10"] = self.df["SMA_10"].iloc[-1]
        if cfg["indicators"].get("sma_trend_filter", False):
            self.df["SMA_Long"] = self._safe_calculate(
                indicators.calculate_sma,
                "SMA_Long",
                period=isd["sma_long_period"],
            )
            if self.df["SMA_Long"] is not None and not self.df["SMA_Long"].empty:
                self.indicator_values["SMA_Long"] = self.df["SMA_Long"].iloc[-1]
        if cfg["indicators"].get("ema_alignment", False):
            self.df["EMA_Short"] = self._safe_calculate(
                indicators.calculate_ema,
                "EMA_Short",
                period=isd["ema_short_period"],
            )
            self.df["EMA_Long"] = self._safe_calculate(
                indicators.calculate_ema,
                "EMA_Long",
                period=isd["ema_long_period"],
            )
            if self.df["EMA_Short"] is not None and not self.df["EMA_Short"].empty:
                self.indicator_values["EMA_Short"] = self.df["EMA_Short"].iloc[-1]
            if self.df["EMA_Long"] is not None and not self.df["EMA_Long"].empty:
                self.indicator_values["EMA_Long"] = self.df["EMA_Long"].iloc[-1]
        self.df["TR"] = self._safe_calculate(indicators.calculate_true_range, "TR")
        self.df["ATR"] = self._safe_calculate(
            indicators.calculate_atr,
            "ATR",
            period=isd["atr_period"],
        )
        if self.df["ATR"] is not None and not self.df["ATR"].empty:
            self.indicator_values["ATR"] = self.df["ATR"].iloc[-1]
        if cfg["indicators"].get("rsi", False):
            self.df["RSI"] = self._safe_calculate(
                indicators.calculate_rsi,
                "RSI",
                period=isd["rsi_period"],
            )
            if self.df["RSI"] is not None and not self.df["RSI"].empty:
                self.indicator_values["RSI"] = self.df["RSI"].iloc[-1]
        if cfg["indicators"].get("stoch_rsi", False):
            stoch_rsi_k, stoch_rsi_d = self._safe_calculate(
                indicators.calculate_stoch_rsi,
                "StochRSI",
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
        if cfg["indicators"].get("bollinger_bands", False):
            bb_upper, bb_middle, bb_lower = self._safe_calculate(
                indicators.calculate_bollinger_bands,
                "BollingerBands",
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
        if cfg["indicators"].get("cci", False):
            self.df["CCI"] = self._safe_calculate(
                indicators.calculate_cci,
                "CCI",
                period=isd["cci_period"],
            )
            if self.df["CCI"] is not None and not self.df["CCI"].empty:
                self.indicator_values["CCI"] = self.df["CCI"].iloc[-1]
        if cfg["indicators"].get("wr", False):
            self.df["WR"] = self._safe_calculate(
                indicators.calculate_williams_r,
                "WR",
                period=isd["williams_r_period"],
            )
            if self.df["WR"] is not None and not self.df["WR"].empty:
                self.indicator_values["WR"] = self.df["WR"].iloc[-1]
        if cfg["indicators"].get("mfi", False):
            self.df["MFI"] = self._safe_calculate(
                indicators.calculate_mfi,
                "MFI",
                period=isd["mfi_period"],
            )
            if self.df["MFI"] is not None and not self.df["MFI"].empty:
                self.indicator_values["MFI"] = self.df["MFI"].iloc[-1]
        if cfg["indicators"].get("obv", False):
            obv_val, obv_ema = self._safe_calculate(
                indicators.calculate_obv,
                "OBV",
                ema_period=isd["obv_ema_period"],
            )
            if obv_val is not None and not obv_val.empty:
                self.df["OBV"] = obv_val
                self.indicator_values["OBV"] = obv_val.iloc[-1]
            if obv_ema is not None and not obv_ema.empty:
                self.df["OBV_EMA"] = obv_ema
                self.indicator_values["OBV_EMA"] = obv_ema.iloc[-1]
        if cfg["indicators"].get("cmf", False):
            cmf_val = self._safe_calculate(
                indicators.calculate_cmf,
                "CMF",
                period=isd["cmf_period"],
            )
            if cmf_val is not None and not cmf_val.empty:
                self.df["CMF"] = cmf_val
                self.indicator_values["CMF"] = cmf_val.iloc[-1]
        if cfg["indicators"].get("ichimoku_cloud", False):
            tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span = (
                self._safe_calculate(
                    indicators.calculate_ichimoku_cloud,
                    "IchimokuCloud",
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
        if cfg["indicators"].get("psar", False):
            psar_val, psar_dir = self._safe_calculate(
                indicators.calculate_psar,
                "PSAR",
                acceleration=isd["psar_acceleration"],
                max_acceleration=isd["psar_max_acceleration"],
            )
            if psar_val is not None and not psar_val.empty:
                self.df["PSAR_Val"] = psar_val
                self.indicator_values["PSAR_Val"] = psar_val.iloc[-1]
            if psar_dir is not None and not psar_dir.empty:
                self.df["PSAR_Dir"] = psar_dir
                self.indicator_values["PSAR_Dir"] = psar_dir.iloc[-1]
        if cfg["indicators"].get("vwap", False):
            self.df["VWAP"] = self._safe_calculate(indicators.calculate_vwap, "VWAP")
            if self.df["VWAP"] is not None and not self.df["VWAP"].empty:
                self.indicator_values["VWAP"] = self.df["VWAP"].iloc[-1]
        if cfg["indicators"].get("ehlers_supertrend", False):
            st_fast_result = self._safe_calculate(
                indicators.calculate_ehlers_supertrend,
                "EhlersSuperTrendFast",
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
                indicators.calculate_ehlers_supertrend,
                "EhlersSuperTrendSlow",
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
        if cfg["indicators"].get("macd", False):
            macd_line, signal_line, histogram = self._safe_calculate(
                indicators.calculate_macd,
                "MACD",
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
        if cfg["indicators"].get("adx", False):
            adx_val, plus_di, minus_di = self._safe_calculate(
                indicators.calculate_adx,
                "ADX",
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
        if cfg["indicators"].get("volatility_index", False):
            self.df["Volatility_Index"] = self._safe_calculate(
                indicators.calculate_volatility_index,
                "Volatility_Index",
                period=isd["volatility_index_period"],
            )
            if (
                self.df["Volatility_Index"] is not None
                and not self.df["Volatility_Index"].empty
            ):
                self.indicator_values["Volatility_Index"] = self.df[
                    "Volatility_Index"
                ].iloc[-1]
        if cfg["indicators"].get("vwma", False):
            self.df["VWMA"] = self._safe_calculate(
                indicators.calculate_vwma,
                "VWMA",
                period=isd["vwma_period"],
            )
            if self.df["VWMA"] is not None and not self.df["VWMA"].empty:
                self.indicator_values["VWMA"] = self.df["VWMA"].iloc[-1]
        if cfg["indicators"].get("volume_delta", False):
            self.df["Volume_Delta"] = self._safe_calculate(
                indicators.calculate_volume_delta,
                "Volume_Delta",
                period=isd["volume_delta_period"],
            )
            if (
                self.df["Volume_Delta"] is not None
                and not self.df["Volume_Delta"].empty
            ):
                self.indicator_values["Volume_Delta"] = self.df["Volume_Delta"].iloc[-1]

        self.df.dropna(subset=["close"], inplace=True)
        self.df.fillna(0, inplace=True)
        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}DataFrame empty after indicator calculations.{RESET}",
            )

    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        return self.indicator_values.get(key, default)

    def _check_orderbook(self, current_price: Decimal, orderbook_data: dict) -> float:
        bids = orderbook_data.get("b", [])
        asks = orderbook_data.get("a", [])
        bid_volume = sum(Decimal(b[1]) for b in bids)
        ask_volume = sum(Decimal(a[1]) for a in asks)
        if bid_volume + ask_volume == 0:
            return 0.0
        imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
        return float(imbalance)

    def _nz(self, x, default=np.nan):
        try:
            return float(x)
        except Exception:
            return default

    def _clip(self, x, lo=-1.0, hi=1.0):
        return float(np.clip(x, lo, hi))

    def _safe_prev(self, series_name: str, default=np.nan):
        s = self.df.get(series_name)
        if s is None or len(s) < 2:
            return default, default
        return float(s.iloc[-1]), float(s.iloc[-2])

    def _market_regime(self):
        adx = self._nz(self._get_indicator_value("ADX"))
        bb_u = self._nz(self._get_indicator_value("BB_Upper"))
        bb_l = self._nz(self._get_indicator_value("BB_Lower"))
        bb_m = self._nz(self._get_indicator_value("BB_Middle"))
        band = (bb_u - bb_l) / bb_m if bb_m and bb_m != 0 else 0
        if adx >= 23 or band >= 0.03:
            return "TRENDING"
        return "RANGING"

    def _volume_confirm(self):
        try:
            vol_now = float(self.df["volume"].iloc[-1])
            vol_ma = float(self.df["volume"].rolling(20).mean().iloc[-1])
            mult = float(self.config.get("volume_confirmation_multiplier", 1.5))
            return vol_now > mult * vol_ma if vol_ma > 0 else False
        except Exception:
            return False

    def _orderbook_score(self, orderbook_data, weight):
        if not orderbook_data:
            return 0.0, None
        imb = self._clip(
            self._check_orderbook(
                Decimal(str(self.df["close"].iloc[-1])),
                orderbook_data,
            ),
        )
        if abs(imb) < 0.05:
            return 0.0, None
        return weight * imb, f"OB Imbalance {imb:+.2f}"

    def _mtf_confluence(self, mtf_trends: dict[str, str], weight):
        if not mtf_trends:
            return 0.0, None
        bulls = sum(
            1
            for v in mtf_trends.values()
            if isinstance(v, str) and v.upper().startswith("BULL")
        )
        bears = sum(
            1
            for v in mtf_trends.values()
            if isinstance(v, str) and v.upper().startswith("BEAR")
        )
        total = bulls + bears
        if total == 0:
            return 0.0, None
        net = (bulls - bears) / total
        return weight * net, f"MTF Confluence {net:+.2f} ({bulls}:{bears})"

    def _dynamic_threshold(self, base_threshold: float) -> float:
        atr_now = self._nz(self._get_indicator_value("ATR"), 0.0)
        if "ATR" not in self.df or self.df["ATR"].rolling(50).mean().empty:
            return base_threshold
        atr_ma = float(self.df["ATR"].rolling(50).mean().iloc[-1])
        if atr_ma <= 0:
            return base_threshold
        ratio = float(np.clip(atr_now / atr_ma, 0.9, 1.5))
        return base_threshold * ratio

    def generate_trading_signal(
        self,
        current_price: Decimal,
        orderbook_data: dict | None,
        mtf_trends: dict[str, str],
    ) -> tuple[str, float]:
        if self.df.empty:
            return "HOLD", 0.0
        w, active, isd = (
            self.weights,
            self.config["indicators"],
            self.indicator_settings,
        )
        score, notes_buy, notes_sell = 0.0, [], []
        close = float(self.df["close"].iloc[-1])
        regime = self._market_regime()

        if active.get("ema_alignment"):
            es, el = (
                self._nz(self._get_indicator_value("EMA_Short")),
                self._nz(self._get_indicator_value("EMA_Long")),
            )
            if not np.isnan(es) and not np.isnan(el):
                if es > el:
                    score += w.get("ema_alignment", 0)
                    notes_buy.append(f"EMA Bull +{w.get('ema_alignment', 0):.2f}")
                elif es < el:
                    score -= w.get("ema_alignment", 0)
                    notes_sell.append(f"EMA Bear -{w.get('ema_alignment', 0):.2f}")
        if active.get("sma_trend_filter"):
            sma_long = self._nz(self._get_indicator_value("SMA_Long"))
            if not np.isnan(sma_long):
                if close > sma_long:
                    score += w.get("sma_trend_filter", 0)
                    notes_buy.append(
                        f"SMA Trend Bull +{w.get('sma_trend_filter', 0):.2f}",
                    )
                elif close < sma_long:
                    score -= w.get("sma_trend_filter", 0)
                    notes_sell.append(
                        f"SMA Trend Bear -{w.get('sma_trend_filter', 0):.2f}",
                    )
        if active.get("ehlers_supertrend"):
            st_fast_dir, st_slow_dir = (
                self._get_indicator_value("ST_Fast_Dir"),
                self._get_indicator_value("ST_Slow_Dir"),
            )
            if st_fast_dir == 1 and st_slow_dir == 1:
                score += w.get("ehlers_supertrend_alignment", 0)
                notes_buy.append(
                    f"EhlersST Bull +{w.get('ehlers_supertrend_alignment', 0):.2f}",
                )
            elif st_fast_dir == -1 and st_slow_dir == -1:
                score -= w.get("ehlers_supertrend_alignment", 0)
                notes_sell.append(
                    f"EhlersST Bear -{w.get('ehlers_supertrend_alignment', 0):.2f}",
                )
        if active.get("macd"):
            macd, signal = (
                self._nz(self._get_indicator_value("MACD_Line")),
                self._nz(self._get_indicator_value("MACD_Signal")),
            )
            hist, prev_hist = self._safe_prev("MACD_Hist")
            if not np.isnan(macd) and not np.isnan(signal):
                if macd > signal and hist > 0 and prev_hist <= 0:
                    score += w.get("macd_alignment", 0)
                    notes_buy.append(
                        f"MACD Bull Cross +{w.get('macd_alignment', 0):.2f}",
                    )
                elif macd < signal and hist < 0 and prev_hist >= 0:
                    score -= w.get("macd_alignment", 0)
                    notes_sell.append(
                        f"MACD Bear Cross -{w.get('macd_alignment', 0):.2f}",
                    )
        if active.get("adx"):
            adx, pdi, mdi = (
                self._nz(self._get_indicator_value("ADX")),
                self._nz(self._get_indicator_value("PlusDI")),
                self._nz(self._get_indicator_value("MinusDI")),
            )
            if not np.isnan(adx) and adx > 20:
                if pdi > mdi:
                    score += w.get("adx_strength", 0) * (adx / 50.0)
                    notes_buy.append(
                        f"ADX Bull {adx:.1f} +{w.get('adx_strength', 0) * (adx / 50.0):.2f}",
                    )
                else:
                    score -= w.get("adx_strength", 0) * (adx / 50.0)
                    notes_sell.append(
                        f"ADX Bear {adx:.1f} -{w.get('adx_strength', 0) * (adx / 50.0):.2f}",
                    )
        if active.get("ichimoku_cloud"):
            tenkan, kijun, span_a, span_b, chikou = (
                self._nz(self._get_indicator_value("Tenkan_Sen")),
                self._nz(self._get_indicator_value("Kijun_Sen")),
                self._nz(self._get_indicator_value("Senkou_Span_A")),
                self._nz(self._get_indicator_value("Senkou_Span_B")),
                self._nz(self._get_indicator_value("Chikou_Span")),
            )
            if (
                not np.isnan(tenkan)
                and not np.isnan(kijun)
                and not np.isnan(span_a)
                and not np.isnan(span_b)
                and not np.isnan(chikou)
            ):
                if (
                    close > span_a
                    and close > span_b
                    and tenkan > kijun
                    and chikou > close
                ):
                    score += w.get("ichimoku_confluence", 0)
                    notes_buy.append(
                        f"Ichimoku Bull +{w.get('ichimoku_confluence', 0):.2f}",
                    )
                elif (
                    close < span_a
                    and close < span_b
                    and tenkan < kijun
                    and chikou < close
                ):
                    score -= w.get("ichimoku_confluence", 0)
                    notes_sell.append(
                        f"Ichimoku Bear -{w.get('ichimoku_confluence', 0):.2f}",
                    )
        if active.get("psar"):
            if self._get_indicator_value("PSAR_Dir") == 1:
                score += w.get("psar", 0)
                notes_buy.append(f"PSAR Bull +{w.get('psar', 0):.2f}")
            elif self._get_indicator_value("PSAR_Dir") == -1:
                score -= w.get("psar", 0)
                notes_sell.append(f"PSAR Bear -{w.get('psar', 0):.2f}")
        if active.get("vwap"):
            vwap = self._nz(self._get_indicator_value("VWAP"))
            if not np.isnan(vwap):
                if close > vwap:
                    score += w.get("vwap", 0)
                    notes_buy.append(f"VWAP Bull +{w.get('vwap', 0):.2f}")
                elif close < vwap:
                    score -= w.get("vwap", 0)
                    notes_sell.append(f"VWAP Bear -{w.get('vwap', 0):.2f}")
        if active.get("vwma"):
            vwma, sma = (
                self._nz(self._get_indicator_value("VWMA")),
                self._nz(self._get_indicator_value("SMA_10")),
            )
            if not np.isnan(vwma) and not np.isnan(sma):
                if vwma > sma:
                    score += w.get("vwma_cross", 0)
                    notes_buy.append(f"VWMA Cross Bull +{w.get('vwma_cross', 0):.2f}")
                elif vwma < sma:
                    score -= w.get("vwma_cross", 0)
                    notes_sell.append(f"VWMA Cross Bear -{w.get('vwma_cross', 0):.2f}")
        if active.get("sma_10"):
            sma10 = self._nz(self._get_indicator_value("SMA_10"))
            if not np.isnan(sma10):
                if close > sma10:
                    score += w.get("sma_10", 0)
                    notes_buy.append(f"SMA10 Bull +{w.get('sma_10', 0):.2f}")
                elif close < sma10:
                    score -= w.get("sma_10", 0)
                    notes_sell.append(f"SMA10 Bear -{w.get('sma_10', 0):.2f}")
        if active.get("momentum"):
            mom_score = 0.0
            if not np.isnan(
                self._get_indicator_value("RSI"),
            ) and self._get_indicator_value("RSI") < isd.get("rsi_oversold", 30):
                mom_score += 1
            elif not np.isnan(
                self._get_indicator_value("RSI"),
            ) and self._get_indicator_value("RSI") > isd.get("rsi_overbought", 70):
                mom_score -= 1
            stoch_k, stoch_d = (
                self._nz(self._get_indicator_value("StochRSI_K")),
                self._nz(self._get_indicator_value("StochRSI_D")),
            )
            if not np.isnan(stoch_k) and not np.isnan(stoch_d):
                if stoch_k > stoch_d and stoch_k < isd.get("stoch_rsi_oversold", 20):
                    mom_score += 1
                elif stoch_k < stoch_d and stoch_k > isd.get(
                    "stoch_rsi_overbought",
                    80,
                ):
                    mom_score -= 1
            if not np.isnan(
                self._get_indicator_value("CCI"),
            ) and self._get_indicator_value("CCI") < isd.get("cci_oversold", -100):
                mom_score += 1
            elif not np.isnan(
                self._get_indicator_value("CCI"),
            ) and self._get_indicator_value("CCI") > isd.get("cci_overbought", 100):
                mom_score -= 1
            if not np.isnan(
                self._get_indicator_value("WR"),
            ) and self._get_indicator_value("WR") < isd.get("williams_r_oversold", -80):
                mom_score += 1
            elif not np.isnan(
                self._get_indicator_value("WR"),
            ) and self._get_indicator_value("WR") > isd.get(
                "williams_r_overbought",
                -20,
            ):
                mom_score -= 1
            if not np.isnan(
                self._get_indicator_value("MFI"),
            ) and self._get_indicator_value("MFI") < isd.get("mfi_oversold", 20):
                mom_score += 1
            elif not np.isnan(
                self._get_indicator_value("MFI"),
            ) and self._get_indicator_value("MFI") > isd.get("mfi_overbought", 80):
                mom_score -= 1
            final_mom_score = w.get("momentum_rsi_stoch_cci_wr_mfi", 0) * self._clip(
                mom_score / 5.0,
            )
            score += final_mom_score
            if final_mom_score > 0:
                notes_buy.append(f"Momentum Bull +{final_mom_score:.2f}")
            elif final_mom_score < 0:
                notes_sell.append(f"Momentum Bear {final_mom_score:.2f}")
        if active.get("bollinger_bands") and regime == "RANGING":
            bb_u, bb_l = (
                self._nz(self._get_indicator_value("BB_Upper")),
                self._nz(self._get_indicator_value("BB_Lower")),
            )
            if not np.isnan(bb_u) and not np.isnan(bb_l):
                if close < bb_l:
                    score += w.get("bollinger_bands", 0)
                    notes_buy.append(
                        f"BB Reversal Bull +{w.get('bollinger_bands', 0):.2f}",
                    )
                elif close > bb_u:
                    score -= w.get("bollinger_bands", 0)
                    notes_sell.append(
                        f"BB Reversal Bear -{w.get('bollinger_bands', 0):.2f}",
                    )
        if active.get("volume_confirmation") and self._volume_confirm():
            score_change = w.get("volume_confirmation", 0)
            if score > 0:
                score += score_change
                notes_buy.append(f"Vol Confirm +{score_change:.2f}")
            elif score < 0:
                score -= score_change
                notes_sell.append(f"Vol Confirm -{score_change:.2f}")
        if active.get("obv"):
            obv, obv_ema = (
                self._nz(self._get_indicator_value("OBV")),
                self._nz(self._get_indicator_value("OBV_EMA")),
            )
            if not np.isnan(obv) and not np.isnan(obv_ema):
                if obv > obv_ema:
                    score += w.get("obv_momentum", 0)
                    notes_buy.append(f"OBV Bull +{w.get('obv_momentum', 0):.2f}")
                elif obv < obv_ema:
                    score -= w.get("obv_momentum", 0)
                    notes_sell.append(f"OBV Bear -{w.get('obv_momentum', 0):.2f}")
        if active.get("cmf"):
            cmf = self._nz(self._get_indicator_value("CMF"))
            if not np.isnan(cmf) and cmf > 0.05:
                score += w.get("cmf_flow", 0)
                notes_buy.append(f"CMF Bull +{w.get('cmf_flow', 0):.2f}")
            elif not np.isnan(cmf) and cmf < -0.05:
                score -= w.get("cmf_flow", 0)
                notes_sell.append(f"CMF Bear -{w.get('cmf_flow', 0):.2f}")
        if active.get("volume_delta"):
            vol_delta = self._nz(self._get_indicator_value("Volume_Delta"))
            delta_thresh = self._nz(isd.get("volume_delta_threshold", 0.2))
            if not np.isnan(vol_delta):
                if vol_delta > delta_thresh:
                    score += w.get("volume_delta_signal", 0)
                    notes_buy.append(
                        f"VolDelta Bull +{w.get('volume_delta_signal', 0):.2f}",
                    )
                elif vol_delta < -delta_thresh:
                    score -= w.get("volume_delta_signal", 0)
                    notes_sell.append(
                        f"VolDelta Bear -{w.get('volume_delta_signal', 0):.2f}",
                    )
        if active.get("volatility_index"):
            vol_idx = self._nz(self._get_indicator_value("Volatility_Index"))
            if (
                not np.isnan(vol_idx)
                and vol_idx
                > self.df["Volatility_Index"].rolling(50).mean().iloc[-1] * 1.5
            ):
                score *= 0.75
                notes_buy.append("High Vol Dampen")
                notes_sell.append("High Vol Dampen")
        if active.get("orderbook_imbalance"):
            ob_score, ob_note = self._orderbook_score(
                orderbook_data,
                w.get("orderbook_imbalance", 0),
            )
            score += ob_score
            if ob_note:
                if ob_score > 0:
                    notes_buy.append(ob_note)
                else:
                    notes_sell.append(ob_note)
        if active.get("mtf_analysis"):
            mtf_score, mtf_note = self._mtf_confluence(
                mtf_trends,
                w.get("mtf_trend_confluence", 0),
            )
            score += mtf_score
            if mtf_note:
                if mtf_score > 0:
                    notes_buy.append(mtf_note)
                else:
                    notes_sell.append(mtf_note)

        base_th = max(float(self.config.get("signal_score_threshold", 2.0)), 1.0)
        dyn_th = self._dynamic_threshold(base_th)
        last_score = float(self.config.get("_last_score", 0.0))
        hyster = float(self.config.get("hysteresis_ratio", 0.85))
        final_signal = "HOLD"
        if (
            np.sign(score) != np.sign(last_score)
            and abs(score) < abs(last_score) * hyster
        ):
            final_signal = "HOLD"
            self.logger.info(
                f"{NEON_YELLOW}Signal held by hysteresis. Score {score:.2f} vs last {last_score:.2f}{RESET}",
            )
        elif score >= dyn_th:
            final_signal = "BUY"
        elif score <= -dyn_th:
            final_signal = "SELL"
        cooldown = int(self.config.get("cooldown_sec", 0))
        now_ts, last_ts = int(time.time()), int(self.config.get("_last_signal_ts", 0))
        if cooldown > 0 and now_ts - last_ts < cooldown and final_signal != "HOLD":
            final_signal = "HOLD"
            self.logger.info(f"{NEON_YELLOW}Signal ignored due to cooldown.{RESET}")
        self.config["_last_score"] = float(score)
        if final_signal in ("BUY", "SELL"):
            self.config["_last_signal_ts"] = now_ts
        if notes_buy:
            self.logger.info(f"{NEON_GREEN}Buy Factors: {', '.join(notes_buy)}{RESET}")
        if notes_sell:
            self.logger.info(f"{NEON_RED}Sell Factors: {', '.join(notes_sell)}{RESET}")
        self.logger.info(
            f"{NEON_PURPLE}Regime: {regime} | Score: {score:.2f} | DynThresh: {dyn_th:.2f} | Final: {final_signal}{RESET}",
        )
        return final_signal, float(score)


# --- NEW: Helper functions for main loop ---
def get_spread_bps(orderbook):
    try:
        best_ask, best_bid = (
            Decimal(orderbook["a"][0][0]),
            Decimal(orderbook["b"][0][0]),
        )
        mid = (best_ask + best_bid) / 2
        return float((best_ask - best_bid) / mid * 10000)
    except Exception:
        return 0.0


def expected_value(perf: PerformanceTracker, n=50, fee_bps=2.0, slip_bps=2.0):
    trades = perf.trades[-n:]
    if not trades:
        return 1.0  # Default to positive if no history
    wins = [Decimal(str(t["pnl"])) for t in trades if Decimal(str(t["pnl"])) > 0]
    losses = [-Decimal(str(t["pnl"])) for t in trades if Decimal(str(t["pnl"])) <= 0]
    win_rate = (len(wins) / len(trades)) if trades else 0.0
    avg_win = (sum(wins) / len(wins)) if wins else Decimal("0")
    avg_loss = (sum(losses) / len(losses)) if losses else Decimal("0")
    cost = Decimal(str((fee_bps + slip_bps) / 10000.0))
    ev = win_rate * (avg_win * (1 - cost)) - (1 - win_rate) * (avg_loss * (1 + cost))
    return float(ev)


def in_allowed_session(cfg) -> bool:
    sess = cfg.get("session_filter", {})
    if not sess.get("enabled", False):
        return True
    now = datetime.now(TIMEZONE).strftime("%H:%M")
    for w in sess.get("utc_allowed", []):
        if w[0] <= now <= w[1]:
            return True
    return False


def adapt_exit_params(pt: PerformanceTracker, cfg: dict) -> tuple[Decimal, Decimal]:
    tp_mult = Decimal(str(cfg["trade_management"]["take_profit_atr_multiple"]))
    sl_mult = Decimal(str(cfg["trade_management"]["stop_loss_atr_multiple"]))
    recent = pt.trades[-100:]
    if not recent or len(recent) < 20:
        return tp_mult, sl_mult
    wins = [t for t in recent if Decimal(str(t.get("pnl", "0"))) > 0]
    losses = [t for t in recent if Decimal(str(t.get("pnl", "0"))) <= 0]
    if wins and losses:
        avg_win, avg_loss = (
            sum(Decimal(str(t["pnl"])) for t in wins) / len(wins),
            -sum(Decimal(str(t["pnl"])) for t in losses) / len(losses),
        )
        rr = (avg_win / avg_loss) if avg_loss > 0 else Decimal("1")
        tilt = Decimal(min(0.5, max(-0.5, float(rr - 1.0))))
        return (tp_mult + tilt, max(Decimal("1.0"), sl_mult - tilt / 2))
    return tp_mult, sl_mult


def random_tune_weights(cfg_path="config.json", k=50, jitter=0.2):
    print("Running random weight tuning...")
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    base = cfg["weight_sets"]["default_scalping"]
    best_cfg, best_score = base, -1e9
    for _ in range(k):
        trial = {
            key: max(0.0, v * (1 + random.uniform(-jitter, jitter)))
            for key, v in base.items()
        }
        proxy = sum(
            trial.get(x, 0)
            for x in [
                "ema_alignment",
                "ehlers_supertrend_alignment",
                "macd_alignment",
                "adx_strength",
            ]
        )
        if proxy > best_score:
            best_cfg, best_score = trial, proxy
    cfg["weight_sets"]["default_scalping"] = best_cfg
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4)
    print(f"New weights saved to {cfg_path}")
    return best_cfg


# --- Main Execution Logic ---
def main() -> None:
    logger = setup_logger("wgwhalex_bot")
    config = load_config(CONFIG_FILE, logger)
    alert_system = AlertSystem(logger)

    logger.info(f"{NEON_GREEN}--- Wgwhalex Trading Bot Initialized ---{RESET}")
    logger.info(f"Symbol: {config['symbol']}, Interval: {config['interval']}")

    pybit_client = PybitTradingClient(config, logger)
    position_manager = PositionManager(config, logger, config["symbol"], pybit_client)
    performance_tracker = PerformanceTracker(logger)
    exec_sync = (
        ExchangeExecutionSync(
            config["symbol"],
            pybit_client,
            logger,
            config,
            position_manager,
            performance_tracker,
        )
        if config["execution"]["live_sync"]["enabled"]
        else None
    )
    heartbeat = (
        PositionHeartbeat(
            config["symbol"],
            pybit_client,
            logger,
            config,
            position_manager,
        )
        if config["execution"]["live_sync"]["heartbeat"]["enabled"]
        else None
    )

    while True:
        try:
            logger.info(
                f"{NEON_PURPLE}--- New Loop ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}) ---{RESET}",
            )

            guard = config.get("risk_guardrails", {})
            if guard.get("enabled", False):
                equity = (
                    Decimal(str(config["trade_management"]["account_balance"]))
                    + performance_tracker.total_pnl
                )
                day_loss = performance_tracker.day_pnl()
                max_day_loss = (
                    Decimal(str(guard.get("max_day_loss_pct", 3.0))) / 100
                ) * equity
                max_dd = (
                    Decimal(str(guard.get("max_drawdown_pct", 8.0))) / 100
                ) * equity
                if (max_day_loss > 0 and day_loss <= -max_day_loss) or (
                    performance_tracker.max_drawdown >= max_dd
                ):
                    logger.error(
                        f"{NEON_RED}KILL SWITCH: Risk limits hit. Cooling down.{RESET}",
                    )
                    time.sleep(int(guard.get("cooldown_after_kill_min", 120)) * 60)
                    continue

            if not in_allowed_session(config):
                logger.info(f"{NEON_BLUE}Outside allowed session. Holding.{RESET}")
                time.sleep(config["loop_delay"])
                continue

            current_price = pybit_client.fetch_current_price(config["symbol"])
            if current_price is None:
                time.sleep(config["loop_delay"])
                continue

            df = pybit_client.fetch_klines(config["symbol"], config["interval"], 1000)
            if df is None or df.empty:
                time.sleep(config["loop_delay"])
                continue

            orderbook_data = (
                pybit_client.fetch_orderbook(
                    config["symbol"],
                    config["orderbook_limit"],
                )
                if config["indicators"].get("orderbook_imbalance")
                else None
            )

            if guard.get("enabled", False) and orderbook_data:
                spread_bps = get_spread_bps(orderbook_data)
                if spread_bps > float(guard.get("spread_filter_bps", 5.0)):
                    logger.warning(
                        f"{NEON_YELLOW}Spread too high ({spread_bps:.1f} bps). Holding.{RESET}",
                    )
                    time.sleep(config["loop_delay"])
                    continue

            if (
                guard.get("ev_filter_enabled", True)
                and expected_value(performance_tracker) <= 0
            ):
                logger.warning(f"{NEON_YELLOW}Negative EV detected. Holding.{RESET}")
                time.sleep(config["loop_delay"])
                continue

            tp_mult, sl_mult = adapt_exit_params(performance_tracker, config)
            config["trade_management"]["take_profit_atr_multiple"] = float(tp_mult)
            config["trade_management"]["stop_loss_atr_multiple"] = float(sl_mult)

            mtf_trends: dict[str, str] = {}
            if config["mtf_analysis"]["enabled"]:
                for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
                    htf_df = pybit_client.fetch_klines(
                        config["symbol"],
                        htf_interval,
                        1000,
                    )
                    if htf_df is not None and not htf_df.empty:
                        for trend_ind in config["mtf_analysis"]["trend_indicators"]:
                            trend = indicators._get_mtf_trend(
                                htf_df,
                                config,
                                logger,
                                config["symbol"],
                                trend_ind,
                            )
                            mtf_trends[f"{htf_interval}_{trend_ind}"] = trend
                    time.sleep(config["mtf_analysis"]["mtf_request_delay_seconds"])

            analyzer = TradingAnalyzer(df, config, logger, config["symbol"])
            if analyzer.df.empty:
                time.sleep(config["loop_delay"])
                continue

            atr_value = Decimal(
                str(analyzer._get_indicator_value("ATR", Decimal("0.1"))),
            )
            config["_last_atr"] = str(atr_value)
            trading_signal, signal_score = analyzer.generate_trading_signal(
                current_price,
                orderbook_data,
                mtf_trends,
            )

            for pos in position_manager.get_open_positions():
                position_manager.trail_stop(pos, current_price, atr_value)
            position_manager.manage_positions(current_price, performance_tracker)
            position_manager.try_pyramid(current_price, atr_value)

            if trading_signal in ("BUY", "SELL"):
                conviction = float(
                    min(
                        2.0,
                        max(
                            0.0,
                            abs(signal_score)
                            / max(config["signal_score_threshold"], 1.0),
                        ),
                    ),
                )
                position_manager.open_position(
                    trading_signal,
                    current_price,
                    atr_value,
                    conviction,
                )
            else:
                logger.info(
                    f"{NEON_BLUE}No strong signal. Holding. Score: {signal_score:.2f}{RESET}",
                )

            config["_last_price"] = str(current_price)  # Store last price
            config["_last_signal"] = trading_signal  # Store last signal

            if exec_sync:
                exec_sync.poll()
            if heartbeat:
                heartbeat.tick()

            logger.info(
                f"{NEON_YELLOW}Performance: {performance_tracker.get_summary()}{RESET}",
            )
            logger.info(
                f"{NEON_PURPLE}--- Loop Finished. Waiting {config['loop_delay']}s ---{RESET}",
            )

            save_bot_state(
                config,
                position_manager,
                performance_tracker,
                logger,
            )  # Save bot state
            time.sleep(config["loop_delay"])

        except Exception as e:
            alert_system.send_alert(f"Unhandled error in main loop: {e}", "ERROR")
            logger.exception(f"{NEON_RED}Unhandled exception in main loop:{RESET}")
            time.sleep(config["loop_delay"] * 2)


if __name__ == "__main__":
    # random_tune_weights(CONFIG_FILE)
    main()
