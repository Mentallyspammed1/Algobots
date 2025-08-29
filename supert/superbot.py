The provided Supertrend Trading Bot code is already quite sophisticated, incorporating many advanced features and best practices. The detailed `sb.md` file effectively outlines the enhancements already implemented.

My review identifies a few areas for further refinement to improve robustness, precision, and adherence to API best practices.

Here's a summary of the additional updates and enhancements:

1.  **Corrected TP/SL Amendment API:** Replaced `session.amend_order` with the more appropriate `session.set_trading_stop` for modifying an existing position's Take Profit and Stop Loss. This ensures the correct Bybit V5 API endpoint is used for position management.
2.  **Robust Decimal Handling with `pandas_ta`:** Refined the process of calculating indicators to ensure `Decimal` precision is maintained throughout the bot. When `pandas_ta` requires `float` inputs, a temporary copy of the relevant columns is converted, and the resulting indicator values are converted back to `Decimal` before being stored in the main `klines_df`.
3.  **Daily PnL Reset:** Implemented logic to automatically reset the daily PnL calculation at the start of each new day, providing more accurate daily performance tracking.
4.  **Configurable Logging Level:** Added `LOG_LEVEL` to the `Config` class, allowing users to easily adjust the verbosity of the bot's logs via environment variables.
5.  **Enhanced `_add_latest_kline` Logic:** Improved the logic for updating existing candles or adding new ones in `_add_latest_kline` to be more explicit and handle `Decimal` types correctly.
6.  **Minor Code Refinements:** Added small improvements for clarity, consistency, and error handling.

---

Here's the updated `superbot.py` code:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enhanced Supertrend Trading Bot for Bybit V5 API.

This script implements a sophisticated trading bot using a Supertrend-based strategy.
It includes advanced features like limit orders, partial take-profits, breakeven stop-loss,
trailing stop-loss, and an ADX trend filter. A real-time, color-coded console UI provides
at-a-glance monitoring of market data, indicator values, and position status.
The bot now uses WebSockets for real-time kline updates and ensures all financial
calculations use Decimal for precision.
"""

import logging
import logging.handlers
import os
import signal
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from enum import Enum
from functools import wraps
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

import colorlog
import pandas as pd
import pandas_ta as ta
from colorama import Fore, Style, init
from dotenv import load_dotenv
from pybit.exceptions import InvalidRequestError, RequestError
from pybit.unified_trading import HTTP, WebSocket
import json

# Initialize Colorama for terminal colors
init(autoreset=True)

# Load environment variables from .env file
load_dotenv()


# =====================================================================
# CONFIGURATION & ENUMS
# =====================================================================

class Signal(Enum):
    BUY = 1
    SELL = -1
    NEUTRAL = 0

class OrderType(Enum):
    MARKET = "Market"
    LIMIT = "Limit"

class Category(Enum):
    LINEAR = "linear"
    SPOT = "spot"
    INVERSE = "inverse"
    OPTION = "option"

    @classmethod
    def from_string(cls, value: str) -> "Category":
        try:
            return cls[value.upper()]
        except KeyError:
            raise ValueError(f"Invalid Category: {value}")

@dataclass
class Config:
    """Bot configuration loaded from environment variables or defaults."""
    API_KEY: str = os.getenv("BYBIT_API_KEY", "YOUR_API_KEY")
    API_SECRET: str = os.getenv("BYBIT_API_SECRET", "YOUR_API_SECRET")
    TESTNET: bool = os.getenv("BYBIT_TESTNET", "true").lower() in ['true', '1', 't']
    SYMBOL: str = os.getenv("BYBIT_SYMBOL", "BTCUSDT")
    CATEGORY: str = os.getenv("BYBIT_CATEGORY", "linear")
    LEVERAGE: Decimal = Decimal(os.getenv("BYBIT_LEVERAGE", "10"))
    TIMEFRAME: str = os.getenv("BYBIT_TIMEFRAME", "15")
    ST_PERIOD: int = int(os.getenv("ST_PERIOD", 10))
    ST_MULTIPLIER: Decimal = Decimal(os.getenv("ST_MULTIPLIER", "3.0"))
    RISK_PER_TRADE_PCT: Decimal = Decimal(os.getenv("RISK_PER_TRADE_PCT", "1.0"))
    STOP_LOSS_PCT: Decimal = Decimal(os.getenv("STOP_LOSS_PCT", "1.5"))
    TAKE_PROFIT_PCT: Decimal = Decimal(os.getenv("TAKE_PROFIT_PCT", "3.0"))
    MAX_DAILY_LOSS_PCT: Decimal = Decimal(os.getenv("MAX_DAILY_LOSS_PCT", "5.0"))
    ORDER_TYPE: str = os.getenv("ORDER_TYPE", "Market")
    ADX_TREND_FILTER_ENABLED: bool = os.getenv("ADX_TREND_FILTER_ENABLED", "true").lower() in ['true', '1', 't']
    ADX_MIN_THRESHOLD: int = int(os.getenv("ADX_MIN_THRESHOLD", 25))
    PARTIAL_TP_ENABLED: bool = os.getenv("PARTIAL_TP_ENABLED", "true").lower() in ['true', '1', 't']
    # Example: '[{"profit_pct": 1.0, "close_qty_pct": 0.5}, {"profit_pct": 2.0, "close_qty_pct": 0.3}]'
    PARTIAL_TP_TARGETS_STR: str = os.getenv("PARTIAL_TP_TARGETS", '[{"profit_pct": 1.0, "close_qty_pct": 0.5}]')
    BREAKEEN_PROFIT_PCT: Decimal = Decimal(os.getenv("BREAKEEN_PROFIT_PCT", "0.5")) # Move SL to entry at this profit
    BREAKEEN_SL_OFFSET_PCT: Decimal = Decimal(os.getenv("BREAKEEN_SL_OFFSET_PCT", "0.01")) # Offset from entry for breakeven SL
    TRAILING_SL_ENABLED: bool = os.getenv("TRAILING_SL_ENABLED", "false").lower() in ['true', '1', 't']
    TRAILING_SL_DISTANCE_PCT: Decimal = Decimal(os.getenv("TRAILING_SL_DISTANCE_PCT", "0.5")) # How far behind price SL trails
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO") # New: Configurable logging level

    PARTIAL_TP_TARGETS: List[Dict[str, Decimal]] = field(init=False)
    CATEGORY_ENUM: Category = field(init=False)
    ORDER_TYPE_ENUM: OrderType = field(init=False)

    def __post_init__(self):
        self.CATEGORY_ENUM = Category.from_string(self.CATEGORY)
        self.ORDER_TYPE_ENUM = OrderType[self.ORDER_TYPE.upper()]
        if self.CATEGORY_ENUM == Category.SPOT:
            self.LEVERAGE = Decimal('1')

        try:
            parsed_targets = json.loads(self.PARTIAL_TP_TARGETS_STR)
            self.PARTIAL_TP_TARGETS = []
            for target in parsed_targets:
                if 'profit_pct' not in target or 'close_qty_pct' not in target:
                    raise ValueError("Each partial TP target must have 'profit_pct' and 'close_qty_pct'")
                self.PARTIAL_TP_TARGETS.append({
                    "profit_pct": Decimal(str(target['profit_pct'])),
                    "close_qty_pct": Decimal(str(target['close_qty_pct']))
                })
            self.PARTIAL_TP_TARGETS.sort(key=lambda x: x['profit_pct']) # Sort by profit_pct ascending
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON for PARTIAL_TP_TARGETS: {e}")
        except Exception as e:
            raise ValueError(f"Error parsing PARTIAL_TP_TARGETS: {e}")

        # Ensure percentages are positive
        for attr in ['RISK_PER_TRADE_PCT', 'STOP_LOSS_PCT', 'TAKE_PROFIT_PCT',
                     'MAX_DAILY_LOSS_PCT', 'BREAKEEN_PROFIT_PCT', 'BREAKEEN_SL_OFFSET_PCT',
                     'TRAILING_SL_DISTANCE_PCT']:
            if getattr(self, attr) < 0:
                raise ValueError(f"{attr} cannot be negative.")
        for target in self.PARTIAL_TP_TARGETS:
            if target['profit_pct'] < 0 or target['close_qty_pct'] < 0 or target['close_qty_pct'] > 1:
                raise ValueError("Partial TP profit_pct must be positive, close_qty_pct must be between 0 and 1.")


# =====================================================================
# LOGGING SETUP
# =====================================================================

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.name,
            "funcName": record.funcName,
            "lineno": record.lineno,
            "threadName": record.threadName,
        }
        return json.dumps(log_record)

def setup_logger(config: Config) -> logging.Logger:
    """Sets up a multi-faceted logger."""
    logger = logging.getLogger('SupertrendBot')
    logger.setLevel(config.LOG_LEVEL.upper())
    logger.handlers.clear()

    # Colored Console Handler
    handler_color = colorlog.StreamHandler()
    handler_color.setFormatter(colorlog.ColoredFormatter(
        '%(log_color)s%(asctime)s - %(levelname)s - %(message)s',
        log_colors={
            'DEBUG': 'cyan', 'INFO': 'green', 'WARNING': 'yellow',
            'ERROR': 'red', 'CRITICAL': 'red,bg_white',
        }
    ))
    logger.addHandler(handler_color)

    # Plain File Handler
    handler_file = logging.handlers.RotatingFileHandler("supertrend_bot.log", maxBytes=5*1024*1024, backupCount=3)
    handler_file.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler_file)

    # JSON File Handler
    handler_json = logging.handlers.RotatingFileHandler("supertrend_bot.json.log", maxBytes=5*1024*1024, backupCount=3)
    handler_json.setFormatter(JsonFormatter())
    logger.addHandler(handler_json)

    return logger

# =====================================================================
# API UTILITIES
# =====================================================================

_MAX_RETRIES = 3
_RETRY_DELAY_SEC = 5

def api_call_with_retries(logger: logging.Logger, method: Callable, *args, **kwargs) -> Optional[Dict[str, Any]]:
    """Decorator to retry API calls on failure."""
    @wraps(method)
    def wrapper(*args, **kwargs):
        for attempt in range(_MAX_RETRIES):
            try:
                res = method(*args, **kwargs)
                if res and res['retCode'] == 0:
                    return res
                else:
                    logger.warning(f"API call failed (attempt {attempt+1}/{_MAX_RETRIES}): {res.get('retMsg', 'Unknown error')}")
            except InvalidRequestError as e:
                logger.error(f"Invalid API request (no retry): {e}. Args: {args}, Kwargs: {kwargs}")
                return None
            except RequestError as e:
                logger.warning(f"API request error (attempt {attempt+1}/{_MAX_RETRIES}): {e}")
            except Exception as e:
                logger.error(f"Unexpected error during API call (attempt {attempt+1}/{_MAX_RETRIES}): {e}", exc_info=True)

            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY_SEC)
        logger.error(f"API call failed after {_MAX_RETRIES} attempts.")
        return None
    return wrapper


# =====================================================================
# BOT STATE & UI
# =====================================================================

@dataclass
class BotState:
    """Thread-safe state manager for the bot."""
    symbol: str
    bot_status: str = "Initializing"
    current_price: Decimal = Decimal('0')
    price_direction: int = 0  # 1 for up, -1 for down, 0 for neutral
    supertrend_line: Optional[Decimal] = None
    supertrend_direction: str = "Calculating..."
    rsi: Optional[Decimal] = None
    macd_hist: Optional[Decimal] = None
    adx: Optional[Decimal] = None
    position_side: str = "None"
    position_size: Decimal = Decimal('0')
    entry_price: Decimal = Decimal('0')
    unrealized_pnl_usd: Decimal = Decimal('0')
    current_pnl_pct: Decimal = Decimal('0')
    stop_loss: Decimal = Decimal('0')
    take_profit: Decimal = Decimal('0')
    breakeven_set: bool = False
    trailing_sl_active: bool = False
    partial_tp_targets_hit: List[bool] = field(default_factory=list)
    daily_pnl_usd: Decimal = Decimal('0')
    daily_pnl_pct: Decimal = Decimal('0')
    log_messages: Deque[str] = field(default_factory=lambda: deque(maxlen=10))
    lock: threading.Lock = field(default_factory=threading.Lock)

    def update(self, **kwargs):
        with self.lock:
            for key, value in kwargs.items():
                if hasattr(self, key):
                    setattr(self, key, value)

    def add_log(self, message: str):
        with self.lock:
            self.log_messages.append(f"{datetime.now().strftime('%H:%M:%S')} - {message}")

class BotUI(threading.Thread):
    """Manages the real-time terminal UI."""
    def __init__(self, state: BotState, config: Config):
        super().__init__(daemon=True)
        self.state = state
        self.config = config
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        while not self._stop_event.is_set():
            self.display()
            time.sleep(1)

    def display(self):
        with self.state.lock:
            os.system('cls' if os.name == 'nt' else 'clear')
            print(Style.BRIGHT + Fore.CYAN + f"=== Supertrend Bot | {self.state.symbol} | Status: {self.state.bot_status} ===" + Style.RESET_ALL)

            price_color = Fore.GREEN if self.state.price_direction == 1 else Fore.RED if self.state.price_direction == -1 else Fore.WHITE
            st_color = Fore.GREEN if self.state.supertrend_direction == "Uptrend" else Fore.RED if self.state.supertrend_direction == "Downtrend" else Fore.WHITE
            print(Style.BRIGHT + "\n--- Market Status ---" + Style.RESET_ALL)
            print(f"Current Price: {price_color}{self.state.current_price:.2f}{Style.RESET_ALL}")

            st_line_str = f"{self.state.supertrend_line:.2f}" if self.state.supertrend_line is not None else "Calculating..."
            print(f"Supertrend: {st_color}{st_line_str} ({self.state.supertrend_direction}){Style.RESET_ALL}")

            rsi_str = f"{self.state.rsi:.2f}" if self.state.rsi is not None else "Calculating..."
            macd_str = f"{self.state.macd_hist:.4f}" if self.state.macd_hist is not None else "Calculating..."
            adx_str = f"{self.state.adx:.2f}" if self.state.adx is not None else "Calculating..."
            rsi_color = Fore.RED if self.state.rsi is not None and self.state.rsi > 70 else Fore.GREEN if self.state.rsi is not None and self.state.rsi < 30 else Fore.WHITE
            macd_color = Fore.GREEN if self.state.macd_hist is not None and self.state.macd_hist > 0 else Fore.RED
            adx_color = Fore.GREEN if self.state.adx is not None and self.state.adx > self.config.ADX_MIN_THRESHOLD else Fore.YELLOW if self.state.adx is not None else Fore.WHITE

            print(Style.BRIGHT + "\n--- Indicator Values ---" + Style.RESET_ALL)
            print(f"RSI: {rsi_color}{rsi_str}{Style.RESET_ALL} | MACD Hist: {macd_color}{macd_str}{Style.RESET_ALL} | ADX: {adx_color}{adx_str}{Style.RESET_ALL}")

            print(Style.BRIGHT + "\n--- Open Position ---" + Style.RESET_ALL)
            if self.state.position_size > 0:
                pos_color = Fore.GREEN if self.state.position_side == 'Buy' else Fore.RED
                pnl_color = Fore.GREEN if self.state.unrealized_pnl_usd >= 0 else Fore.RED
                print(f"Side: {pos_color}{self.state.position_side}{Style.RESET_ALL} | Size: {self.state.position_size} | Entry: {self.state.entry_price:.2f}")
                print(f"Unrealized PnL: {pnl_color}${self.state.unrealized_pnl_usd:.2f} ({self.state.current_pnl_pct:.2f}%) {Style.RESET_ALL}")
                print(f"SL: {self.state.stop_loss:.2f} | TP: {self.state.take_profit:.2f}")
                breakeven_status = f"{Fore.GREEN}Active{Style.RESET_ALL}" if self.state.breakeven_set else f"{Fore.YELLOW}Pending{Style.RESET_ALL}"
                trailing_sl_status = f"{Fore.GREEN}Active{Style.RESET_ALL}" if self.state.trailing_sl_active else f"{Fore.YELLOW}Inactive{Style.RESET_ALL}"
                print(f"Breakeven SL: {breakeven_status} | Trailing SL: {trailing_sl_status}")
                if self.config.PARTIAL_TP_ENABLED and self.state.partial_tp_targets_hit:
                    hit_targets = [f"{t['profit_pct']:.1f}%" for i, t in enumerate(self.config.PARTIAL_TP_TARGETS) if self.state.partial_tp_targets_hit[i]]
                    pending_targets = [f"{t['profit_pct']:.1f}%" for i, t in enumerate(self.config.PARTIAL_TP_TARGETS) if not self.state.partial_tp_targets_hit[i]]
                    print(f"Partial TPs Hit: {', '.join(hit_targets) if hit_targets else 'None'}")
                    print(f"Partial TPs Pending: {', '.join(pending_targets) if pending_targets else 'None'}")
            else:
                print("No active position.")

            daily_pnl_color = Fore.GREEN if self.state.daily_pnl_usd >= 0 else Fore.RED
            print(Style.BRIGHT + "\n--- Daily Performance ---" + Style.RESET_ALL)
            print(f"Daily PnL: {daily_pnl_color}${self.state.daily_pnl_usd:.2f} ({self.state.daily_pnl_pct:.2f}%){Style.RESET_ALL}")

            print(Style.BRIGHT + "\n--- Live Log ---" + Style.RESET_ALL)
            for msg in self.state.log_messages:
                print(msg)

            print("\n" + Fore.CYAN + "="*53 + Style.RESET_ALL)
            print(Fore.YELLOW + "Press Ctrl+C to exit." + Style.RESET_ALL)


# =====================================================================
# PRECISION & ORDER SIZING
# =====================================================================

@dataclass
class InstrumentSpecs:
    tick_size: Decimal; qty_step: Decimal; min_order_qty: Decimal

class PrecisionManager:
    def __init__(self, session: HTTP, logger: logging.Logger):
        self.session = session; self.logger = logger; self.instruments: Dict[str, InstrumentSpecs] = {}

    @api_call_with_retries
    def _get_instruments_info_api(self, category: str, symbol: str) -> Optional[Dict[str, Any]]:
        return self.session.get_instruments_info(category=category, symbol=symbol)

    def get_specs(self, symbol: str, category: str) -> Optional[InstrumentSpecs]:
        if symbol in self.instruments: return self.instruments[symbol]
        res = self._get_instruments_info_api(category=category, symbol=symbol)
        if res and res['retCode'] == 0 and res['result']['list']:
            info = res['result']['list'][0]
            specs = InstrumentSpecs(Decimal(info['priceFilter']['tickSize']), Decimal(info['lotSizeFilter']['qtyStep']), Decimal(info['lotSizeFilter']['minOrderQty']))
            self.instruments[symbol] = specs; return specs
        return None

    def round_price(self, specs: InstrumentSpecs, price: Decimal) -> Decimal:
        return (price / specs.tick_size).quantize(Decimal('1'), rounding=ROUND_DOWN) * specs.tick_size

    def round_quantity(self, specs: InstrumentSpecs, quantity: Decimal) -> Decimal:
        return (quantity / specs.qty_step).quantize(Decimal('1'), rounding=ROUND_DOWN) * specs.qty_step

class OrderSizingCalculator:
    def __init__(self, precision_manager: PrecisionManager):
        self.precision = precision_manager

    def calculate(self, specs: InstrumentSpecs, balance: Decimal, risk_pct: Decimal, entry: Decimal, sl: Decimal, lev: Decimal) -> Optional[Decimal]:
        if balance <= 0 or entry <= 0 or lev <= 0 or abs(entry - sl) == 0:
            return None

        risk_amount = balance * (risk_pct / Decimal('100'))
        sl_dist_pct = abs(entry - sl) / entry

        # Max position value based on risk and leverage
        pos_val_from_risk = risk_amount / sl_dist_pct
        max_pos_val_from_leverage = balance * lev

        # Use the minimum of these two to be conservative
        position_value = min(pos_val_from_risk, max_pos_val_from_leverage)

        qty = position_value / entry
        return self.precision.round_quantity(specs, qty)


# =====================================================================
# MAIN TRADING BOT CLASS
# =====================================================================

class SupertrendBot:
    def __init__(self, config: Config):
        self.config = config
        self.logger = setup_logger(config)
        self.bot_state = BotState(symbol=config.SYMBOL)
        self.session = HTTP(testnet=config.TESTNET, api_key=config.API_KEY, api_secret=config.API_SECRET)
        self.precision_manager = PrecisionManager(self.session, self.logger)
        self.order_sizer = OrderSizingCalculator(self.precision_manager)

        self.position_active = False
        self.current_position: Optional[Dict[str, Any]] = None
        self.start_balance_usd: Decimal = Decimal('0')
        self.last_daily_pnl_reset_date: Optional[datetime.date] = None # New: To track daily PnL reset

        self.klines_df: pd.DataFrame = pd.DataFrame()
        self.last_candle_close_time: Optional[datetime] = None

        self._stop_requested = False
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        self.ws_kline: Optional[WebSocket] = None
        self.ws_ticker: Optional[WebSocket] = None

    def _signal_handler(self, signum, frame):
        self.logger.warning(f"Signal {signum} received, stopping bot...")
        self.bot_state.update(bot_status="Shutting down")
        self._stop_requested = True
        if self.ws_kline: self.ws_kline.exit()
        if self.ws_ticker: self.ws_ticker.exit()

    @api_call_with_retries
    def _get_wallet_balance_api(self, coin="USDT") -> Optional[Dict[str, Any]]:
        return self.session.get_wallet_balance(accountType="UNIFIED", coin=coin)

    def get_account_balance(self, coin="USDT") -> Decimal:
        res = self._get_wallet_balance_api(coin=coin)
        if res and res['retCode'] == 0:
            for item in res['result']['list']:
                if item['accountType'] == "UNIFIED":
                    for c in item['coin']:
                        if c['coin'] == coin: return Decimal(c['walletBalance'])
        self.logger.error("Could not retrieve account balance.")
        return Decimal('0')

    @api_call_with_retries
    def _get_klines_api(self, category: str, symbol: str, interval: str, limit: int) -> Optional[Dict[str, Any]]:
        return self.session.get_kline(category=category, symbol=symbol, interval=interval, limit=limit)

    def fetch_historical_klines(self) -> Optional[pd.DataFrame]:
        res = self._get_klines_api(category=self.config.CATEGORY, symbol=self.config.SYMBOL, interval=self.config.TIMEFRAME, limit=200)
        if res and res['retCode'] == 0 and res['result']['list']:
            df = pd.DataFrame(res['result']['list'], columns=['ts', 'o', 'h', 'l', 'c', 'v', 't'])
            df.rename(columns={'ts': 'timestamp', 'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'}, inplace=True)
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce').apply(lambda x: Decimal(str(x)) if pd.notna(x) else pd.NA)
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df.sort_values('timestamp').reset_index(drop=True)
        return None

    def _add_latest_kline(self, kline_data: Dict[str, Any]):
        """Adds a new kline or updates the last one in the DataFrame."""
        new_row_data = {
            'timestamp': pd.to_datetime(kline_data['start'], unit='ms'),
            'open': Decimal(kline_data['open']),
            'high': Decimal(kline_data['high']),
            'low': Decimal(kline_data['low']),
            'close': Decimal(kline_data['close']),
            'volume': Decimal(kline_data['volume'])
        }
        
        if not self.klines_df.empty and self.klines_df.iloc[-1]['timestamp'] == new_row_data['timestamp']:
            # Update last row if it's the same candle (incomplete candle being updated)
            for key, value in new_row_data.items():
                self.klines_df.loc[self.klines_df.index[-1], key] = value
            self.logger.debug(f"Updated current candle: {new_row_data['timestamp']}")
        else:
            # Add new row, trim if too long
            new_row_df = pd.DataFrame([new_row_data])
            self.klines_df = pd.concat([self.klines_df, new_row_df], ignore_index=True)
            if len(self.klines_df) > 200: # Keep dataframe size reasonable
                self.klines_df = self.klines_df.iloc[1:].reset_index(drop=True)
            self.logger.debug(f"Added new candle: {new_row_data['timestamp']}")

        # Now calculate indicators on the updated self.klines_df
        self.klines_df = self.calculate_indicators(self.klines_df)

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculates technical indicators for the DataFrame."""
        # Create a temporary DataFrame for TA calculations, converting necessary columns to float
        df_for_ta = df.copy()
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df_for_ta[col] = pd.to_numeric(df_for_ta[col], errors='coerce').astype(float)

        # Apply pandas_ta indicators
        df_for_ta.ta.supertrend(length=self.config.ST_PERIOD, multiplier=float(self.config.ST_MULTIPLIER), append=True)
        df_for_ta.ta.adx(length=14, append=True)
        df_for_ta.ta.rsi(length=14, append=True)
        df_for_ta.ta.macd(append=True)
        df_for_ta.rename(columns={
            f'SUPERTd_{self.config.ST_PERIOD}_{float(self.config.ST_MULTIPLIER)}': 'st_dir',
            f'SUPERT_{self.config.ST_PERIOD}_{float(self.config.ST_MULTIPLIER)}': 'st_line',
            'ADX_14': 'adx', 'RSI_14': 'rsi', 'MACDh_12_26_9': 'macd_hist'
        }, inplace=True)

        # Update the original DataFrame with new indicator columns, ensuring they are Decimal
        for col in ['st_dir', 'st_line', 'adx', 'rsi', 'macd_hist']:
            if col in df_for_ta.columns:
                df[col] = df_for_ta[col].apply(lambda x: Decimal(str(x)) if pd.notna(x) else pd.NA)
            else:
                df[col] = pd.NA # If indicator not calculated for some reason
        return df

    def generate_signal(self, df: pd.DataFrame) -> Signal:
        if len(df) < 2: return Signal.NEUTRAL # Need at least two candles for comparison

        # Use the last completed candle (iloc[-2]) for signal generation
        latest_complete = df.iloc[-2]
        prev_complete = df.iloc[-3] if len(df) >= 3 else None

        if pd.isna(latest_complete['st_dir']) or pd.isna(latest_complete['adx']):
            self.bot_state.add_log("Indicators not ready for signal generation.")
            return Signal.NEUTRAL

        self.bot_state.update(
            supertrend_line=latest_complete['st_line'],
            supertrend_direction=("Uptrend" if latest_complete['st_dir'] == 1 else "Downtrend"),
            rsi=latest_complete['rsi'],
            macd_hist=latest_complete['macd_hist'],
            adx=latest_complete['adx']
        )

        if self.config.ADX_TREND_FILTER_ENABLED and latest_complete['adx'] < self.config.ADX_MIN_THRESHOLD:
            self.bot_state.add_log(f"ADX ({latest_complete['adx']:.2f}) below threshold ({self.config.ADX_MIN_THRESHOLD}), no trade.")
            return Signal.NEUTRAL

        if prev_complete is not None:
            if latest_complete['st_dir'] == 1 and prev_complete['st_dir'] == -1:
                self.bot_state.add_log(f"Supertrend BUY signal detected at {latest_complete['close']:.2f}")
                return Signal.BUY
            if latest_complete['st_dir'] == -1 and prev_complete['st_dir'] == 1:
                self.bot_state.add_log(f"Supertrend SELL signal detected at {latest_complete['close']:.2f}")
                return Signal.SELL
        return Signal.NEUTRAL

    @api_call_with_retries
    def _get_positions_api(self, category: str, symbol: str) -> Optional[Dict[str, Any]]:
        return self.session.get_positions(category=category, symbol=symbol)

    def get_positions(self):
        res = self._get_positions_api(category=self.config.CATEGORY, symbol=self.config.SYMBOL)
        if res and res['retCode'] == 0:
            pos_found = False
            for pos in res['result']['list']:
                if Decimal(pos['size']) > 0:
                    self.position_active = True
                    self.current_position = pos
                    current_pnl_pct = Decimal('0')
                    if Decimal(pos['avgPrice']) > 0:
                        current_pnl_pct = (Decimal(pos['unrealisedPnl']) / (Decimal(pos['size']) * Decimal(pos['avgPrice']))) * Decimal('100')

                    self.bot_state.update(
                        position_side=pos['side'],
                        position_size=Decimal(pos['size']),
                        entry_price=Decimal(pos['avgPrice']),
                        unrealized_pnl_usd=Decimal(pos['unrealisedPnl']),
                        current_pnl_pct=current_pnl_pct,
                        stop_loss=Decimal(pos.get('stopLoss', '0')),
                        take_profit=Decimal(pos.get('takeProfit', '0'))
                    )
                    pos_found = True
                    break
            if not pos_found:
                self.position_active = False
                self.current_position = None
                self.bot_state.update(
                    position_side="None", position_size=Decimal('0'), entry_price=Decimal('0'),
                    unrealized_pnl_usd=Decimal('0'), current_pnl_pct=Decimal('0'),
                    stop_loss=Decimal('0'), take_profit=Decimal('0'),
                    breakeven_set=False, trailing_sl_active=False,
                    partial_tp_targets_hit=[False] * len(self.config.PARTIAL_TP_TARGETS)
                )
        else:
            self.logger.error("Failed to retrieve positions.")

    @api_call_with_retries
    def _place_order_api(self, **kwargs) -> Optional[Dict[str, Any]]:
        return self.session.place_order(**kwargs)

    def place_order(self, specs: InstrumentSpecs, side: str, qty: Decimal, o_type: OrderType, price: Optional[Decimal], sl: Decimal, tp: Decimal):
        qty_str = str(self.precision_manager.round_quantity(specs, qty))
        sl_str = str(self.precision_manager.round_price(specs, sl))
        tp_str = str(self.precision_manager.round_price(specs, tp))

        params = {
            "category": self.config.CATEGORY,
            "symbol": self.config.SYMBOL,
            "side": side,
            "orderType": o_type.value,
            "qty": qty_str,
            "stopLoss": sl_str,
            "takeProfit": tp_str,
            "tpslMode": "Full", # Use Full for initial order, then manage with set_trading_stop
            "isLeverage": 1 if self.config.LEVERAGE > 1 else 0
        }
        if o_type == OrderType.LIMIT and price:
            params["price"] = str(self.precision_manager.round_price(specs, price))

        res = self._place_order_api(**params)
        if res and res['retCode'] == 0:
            self.logger.info(f"Order placed: {side} {qty_str} {self.config.SYMBOL} @ {params.get('price', o_type.value)}. SL: {sl_str}, TP: {tp_str}")
            self.bot_state.add_log(f"Order placed: {side} {qty_str} @ {params.get('price', o_type.value)}")
            # Reset breakeven/trailing SL state for new position
            self.bot_state.update(breakeven_set=False, trailing_sl_active=False, partial_tp_targets_hit=[False] * len(self.config.PARTIAL_TP_TARGETS))
        else:
            self.logger.error(f"Order failed: {res.get('retMsg', 'Unknown error')}. Params: {params}")
            self.bot_state.add_log(f"Order failed: {res.get('retMsg', 'Unknown error')}")

    @api_call_with_retries
    def _set_trading_stop_api(self, **kwargs) -> Optional[Dict[str, Any]]:
        """API call to set or amend TP/SL for an active position."""
        return self.session.set_trading_stop(**kwargs)

    def amend_position_tpsl(self, new_sl: Decimal, new_tp: Decimal):
        """Amends the Take Profit and Stop Loss for the current open position."""
        if not self.position_active or not self.current_position:
            self.logger.warning("Attempted to amend TP/SL but no active position.")
            return

        specs = self.precision_manager.get_specs(self.config.SYMBOL, self.config.CATEGORY)
        if not specs: return

        current_sl = Decimal(self.current_position.get('stopLoss', '0'))
        current_tp = Decimal(self.current_position.get('takeProfit', '0'))

        rounded_new_sl = self.precision_manager.round_price(specs, new_sl)
        rounded_new_tp = self.precision_manager.round_price(specs, new_tp)

        # Only amend if SL/TP actually changed significantly
        if rounded_new_sl == current_sl and rounded_new_tp == current_tp:
            self.logger.debug("SL/TP values unchanged, skipping amend.")
            return

        # Get positionIdx from the current position data.
        # For one-way mode, positionIdx is typically 0. For hedge mode, 1 for long, 2 for short.
        # The bot is assumed to be in one-way mode unless specified otherwise.
        position_idx = int(self.current_position.get('positionIdx', '0'))

        params = {
            "category": self.config.CATEGORY,
            "symbol": self.config.SYMBOL,
            "stopLoss": str(rounded_new_sl),
            "takeProfit": str(rounded_new_tp),
            "tpslMode": "Full", # Always manage full position's SL/TP
            "positionIdx": position_idx
        }

        res = self._set_trading_stop_api(**params) # Use the dedicated set_trading_stop endpoint
        if res and res['retCode'] == 0:
            self.logger.info(f"Amended TP/SL for position {self.config.SYMBOL}. New SL: {rounded_new_sl}, New TP: {rounded_new_tp}")
            self.bot_state.add_log(f"Amended TP/SL. SL: {rounded_new_sl}, TP: {rounded_new_tp}")
            self.bot_state.update(stop_loss=rounded_new_sl, take_profit=rounded_new_tp)
        else:
            self.logger.error(f"Failed to amend TP/SL: {res.get('retMsg', 'Unknown error')}. Params: {params}")
            self.bot_state.add_log(f"Failed to amend TP/SL: {res.get('retMsg', 'Unknown error')}")

    @api_call_with_retries
    def _close_position_api(self, **kwargs) -> Optional[Dict[str, Any]]:
        return self.session.place_order(**kwargs)

    def close_partial_position(self, specs: InstrumentSpecs, side: str, qty_to_close: Decimal, current_price: Decimal):
        if not self.position_active or not self.current_position:
            self.logger.warning("Attempted to close partial position but no active position.")
            return

        order_side = "Sell" if side == "Buy" else "Buy" # Opposite of current position side
        qty_str = str(self.precision_manager.round_quantity(specs, qty_to_close))

        params = {
            "category": self.config.CATEGORY,
            "symbol": self.config.SYMBOL,
            "side": order_side,
            "orderType": "Market", # Always market for closing
            "qty": qty_str,
            "reduceOnly": True # Ensure it only reduces existing position
        }

        res = self._close_position_api(**params)
        if res and res['retCode'] == 0:
            self.logger.info(f"Closed {qty_str} of {self.config.SYMBOL} position for partial TP.")
            self.bot_state.add_log(f"Closed {qty_str} for partial TP.")
        else:
            self.logger.error(f"Failed to close partial position: {res.get('retMsg', 'Unknown error')}. Params: {params}")
            self.bot_state.add_log(f"Failed to close partial position: {res.get('retMsg', 'Unknown error')}")

    def _manage_open_position(self):
        if not self.position_active or not self.current_position:
            return

        current_price = self.bot_state.current_price
        side = self.bot_state.position_side
        entry_price = self.bot_state.entry_price
        current_sl = self.bot_state.stop_loss
        current_tp = self.bot_state.take_profit
        current_pnl_pct = self.bot_state.current_pnl_pct

        specs = self.precision_manager.get_specs(self.config.SYMBOL, self.config.CATEGORY)
        if not specs: return

        # 1. Breakeven Stop-Loss
        if not self.bot_state.breakeven_set and self.config.BREAKEEN_PROFIT_PCT > 0:
            if (side == "Buy" and current_pnl_pct >= self.config.BREAKEEN_PROFIT_PCT) or \
               (side == "Sell" and current_pnl_pct >= self.config.BREAKEEN_PROFIT_PCT):
                new_sl = entry_price * (Decimal('1') + self.config.BREAKEEN_SL_OFFSET_PCT/Decimal('100')) if side == "Buy" else \
                         entry_price * (Decimal('1') - self.config.BREAKEEN_SL_OFFSET_PCT/Decimal('100'))
                
                # Ensure new_sl is actually better than current_sl (or at least equal) for safety
                # And only if current_sl is not already set to a better price
                if (side == "Buy" and (current_sl == Decimal('0') or new_sl > current_sl)) or \
                   (side == "Sell" and (current_sl == Decimal('0') or new_sl < current_sl)):
                    self.amend_position_tpsl(new_sl, current_tp)
                    self.bot_state.update(breakeven_set=True)
                    self.bot_state.add_log(f"Breakeven SL set at {new_sl:.2f}")

        # 2. Trailing Stop-Loss
        if self.config.TRAILING_SL_ENABLED and self.bot_state.breakeven_set: # Trailing SL only after breakeven
            # Calculate potential new trailing SL
            if side == "Buy":
                new_trailing_sl = current_price * (Decimal('1') - self.config.TRAILING_SL_DISTANCE_PCT / Decimal('100'))
                # Only update if new_trailing_sl is higher than current SL (to trail up)
                if new_trailing_sl > current_sl:
                    self.amend_position_tpsl(new_trailing_sl, current_tp)
                    self.bot_state.update(trailing_sl_active=True)
                    self.bot_state.add_log(f"Trailing SL updated to {new_trailing_sl:.2f}")
            elif side == "Sell":
                new_trailing_sl = current_price * (Decimal('1') + self.config.TRAILING_SL_DISTANCE_PCT / Decimal('100'))
                # Only update if new_trailing_sl is lower than current SL (to trail down)
                if new_trailing_sl < current_sl:
                    self.amend_position_tpsl(new_trailing_sl, current_tp)
                    self.bot_state.update(trailing_sl_active=True)
                    self.bot_state.add_log(f"Trailing SL updated to {new_trailing_sl:.2f}")

        # 3. Partial Take-Profits
        if self.config.PARTIAL_TP_ENABLED and self.config.PARTIAL_TP_TARGETS and self.bot_state.position_size > 0:
            # Initialize partial_tp_targets_hit if not already done or if targets changed
            if not self.bot_state.partial_tp_targets_hit or len(self.bot_state.partial_tp_targets_hit) != len(self.config.PARTIAL_TP_TARGETS):
                self.bot_state.update(partial_tp_targets_hit=[False] * len(self.config.PARTIAL_TP_TARGETS))

            remaining_qty_for_tp = self.bot_state.position_size
            for i, target in enumerate(self.config.PARTIAL_TP_TARGETS):
                if not self.bot_state.partial_tp_targets_hit[i]:
                    if current_pnl_pct >= target['profit_pct']:
                        qty_to_close = self.bot_state.position_size * target['close_qty_pct']
                        min_qty = specs.min_order_qty
                        rounded_qty_to_close = self.precision_manager.round_quantity(specs, qty_to_close)

                        # Ensure we don't try to close more than is remaining
                        if rounded_qty_to_close > remaining_qty_for_tp:
                            rounded_qty_to_close = self.precision_manager.round_quantity(specs, remaining_qty_for_tp)

                        if rounded_qty_to_close >= min_qty:
                            self.close_partial_position(specs, side, rounded_qty_to_close, current_price)
                            # Mark this target as hit
                            hit_targets = self.bot_state.partial_tp_targets_hit[:]
                            hit_targets[i] = True
                            self.bot_state.update(partial_tp_targets_hit=hit_targets)
                            remaining_qty_for_tp -= rounded_qty_to_close
                            self.logger.info(f"Partial TP hit: {target['profit_pct']:.2f}% (closed {rounded_qty_to_close} qty)")
                        else:
                            self.logger.warning(f"Calculated partial TP quantity {rounded_qty_to_close} is less than min_order_qty {min_qty} or remaining quantity. Skipping.")

    def _check_daily_loss(self):
        # Reset daily PnL at the start of a new day
        today = datetime.now().date()
        if self.last_daily_pnl_reset_date is None or self.last_daily_pnl_reset_date != today:
            self.logger.info(f"Resetting daily PnL for {today}.")
            self.start_balance_usd = self.get_account_balance() # Recalibrate initial balance
            self.last_daily_pnl_reset_date = today
            self.bot_state.update(daily_pnl_usd=Decimal('0'), daily_pnl_pct=Decimal('0')) # Reset UI display
            self.logger.info(f"Daily PnL reset. New starting balance: ${self.start_balance_usd:.2f}")

        if self.config.MAX_DAILY_LOSS_PCT > 0 and self.start_balance_usd > 0:
            current_balance = self.get_account_balance()
            daily_pnl_usd = current_balance - self.start_balance_usd
            daily_pnl_pct = (daily_pnl_usd / self.start_balance_usd) * Decimal('100')

            self.bot_state.update(daily_pnl_usd=daily_pnl_usd, daily_pnl_pct=daily_pnl_pct)

            if daily_pnl_pct <= -self.config.MAX_DAILY_LOSS_PCT:
                self.logger.critical(f"Max daily loss ({self.config.MAX_DAILY_LOSS_PCT:.2f}%) hit! Daily PnL: {daily_pnl_pct:.2f}%. Stopping bot.")
                self.bot_state.add_log(f"CRITICAL: Max daily loss hit! Stopping bot.")
                self._stop_requested = True
                if self.position_active:
                    self.logger.warning("Max daily loss hit, attempting to close open position.")
                    specs = self.precision_manager.get_specs(self.config.SYMBOL, self.config.CATEGORY)
                    if specs and self.bot_state.position_size > 0:
                        self.close_partial_position(specs, self.bot_state.position_side, self.bot_state.position_size, self.bot_state.current_price)
        else:
            # If MAX_DAILY_LOSS_PCT is 0 or start_balance_usd is 0, don't display daily PnL
            self.bot_state.update(daily_pnl_usd=Decimal('0'), daily_pnl_pct=Decimal('0'))


    def _handle_ticker(self, msg):
        if 'data' in msg and 'lastPrice' in msg['data']:
            price = Decimal(msg['data']['lastPrice'])
            if self.bot_state.current_price != Decimal('0'):
                direction = 1 if price > self.bot_state.current_price else -1 if price < self.bot_state.current_price else 0
                self.bot_state.update(current_price=price, price_direction=direction)
            else:
                self.bot_state.update(current_price=price)

            # Update PnL in UI based on real-time price
            if self.position_active and self.bot_state.position_size > 0 and self.bot_state.entry_price > 0:
                pnl_usd = Decimal('0')
                if self.bot_state.position_side == "Buy":
                    pnl_usd = (price - self.bot_state.entry_price) * self.bot_state.position_size
                elif self.bot_state.position_side == "Sell":
                    pnl_usd = (self.bot_state.entry_price - price) * self.bot_state.position_size

                pnl_pct = (pnl_usd / (self.bot_state.entry_price * self.bot_state.position_size)) * Decimal('100')

                self.bot_state.update(unrealized_pnl_usd=pnl_usd, current_pnl_pct=pnl_pct)

                # Manage position based on real-time price updates (for trailing SL, partial TP)
                self._manage_open_position()

    def _handle_kline_update(self, msg):
        if 'data' in msg:
            for kline in msg['data']:
                # Only process if the candle is closed (end of interval)
                if kline['confirm']:
                    self.logger.info(f"New confirmed kline received: {datetime.fromtimestamp(kline['start']/1000)} - Close: {kline['close']}")
                    self._add_latest_kline(kline)
                    self.last_candle_close_time = pd.to_datetime(kline['start'], unit='ms')

    def _initialize_bot(self):
        self.bot_state.update(bot_status="Initializing...")
        
        # Initialize daily PnL reference
        self.last_daily_pnl_reset_date = datetime.now().date()
        self.start_balance_usd = self.get_account_balance()
        if self.start_balance_usd <= 0:
            self.logger.critical("Cannot start bot: Account balance is zero or could not be retrieved.")
            sys.exit(1)
        self.logger.info(f"Bot starting with balance: ${self.start_balance_usd:.2f}")
        self.bot_state.add_log(f"Initial balance: ${self.start_balance_usd:.2f}")


        # Fetch initial historical klines
        self.bot_state.update(bot_status="Fetching historical klines...")
        self.klines_df = self.fetch_historical_klines()
        if self.klines_df is None or self.klines_df.empty:
            self.logger.critical("Could not fetch historical klines. Exiting.")
            sys.exit(1)
        
        # Calculate initial indicators
        self.klines_df = self.calculate_indicators(self.klines_df)
        self.last_candle_close_time = self.klines_df.iloc[-1]['timestamp']

        self.get_positions() # Get current position status
        
        # Initial check for ADX to update UI
        if len(self.klines_df) >= 2:
            latest_complete = self.klines_df.iloc[-2]
            if not pd.isna(latest_complete['st_dir']):
                self.bot_state.update(
                    supertrend_line=latest_complete['st_line'],
                    supertrend_direction=("Uptrend" if latest_complete['st_dir'] == 1 else "Downtrend"),
                    rsi=latest_complete['rsi'],
                    macd_hist=latest_complete['macd_hist'],
                    adx=latest_complete['adx']
                )

    def _start_websocket_listeners(self):
        self.bot_state.update(bot_status="Connecting to WebSockets...")
        self.ws_kline = WebSocket(testnet=self.config.TESTNET, channel_type=self.config.CATEGORY)
        self.ws_kline.kline_stream([self.config.SYMBOL], self.config.TIMEFRAME, self._handle_kline_update)
        self.logger.info(f"Subscribed to kline.{self.config.TIMEFRAME}.{self.config.SYMBOL} via WebSocket.")

        self.ws_ticker = WebSocket(testnet=self.config.TESTNET, channel_type=self.config.CATEGORY)
        self.ws_ticker.ticker_stream([self.config.SYMBOL], self._handle_ticker)
        self.logger.info(f"Subscribed to tickers.{self.config.SYMBOL} via WebSocket.")

    def _process_kline_data(self):
        # Generate signal and place order only if a new candle has closed and we don't have an active position
        if self.last_candle_close_time is not None and not self.position_active:
            # We need at least 3 candles to get prev_complete and latest_complete for the signal
            if len(self.klines_df) >= 3:
                # Use the second to last candle for signal generation (the last *completed* candle)
                signal = self.generate_signal(self.klines_df)
                if signal != Signal.NEUTRAL:
                    specs = self.precision_manager.get_specs(self.config.SYMBOL, self.config.CATEGORY)
                    if specs:
                        # Entry price from the close of the signal candle
                        entry = self.klines_df.iloc[-2]['close']
                        side = "Buy" if signal == Signal.BUY else "Sell"
                        sl = entry * (Decimal('1') - self.config.STOP_LOSS_PCT/Decimal('100')) if side == "Buy" else \
                             entry * (Decimal('1') + self.config.STOP_LOSS_PCT/Decimal('100'))
                        tp = entry * (Decimal('1') + self.config.TAKE_PROFIT_PCT/Decimal('100')) if side == "Buy" else \
                             entry * (Decimal('1') - self.config.TAKE_PROFIT_PCT/Decimal('100'))

                        current_balance = self.get_account_balance()
                        qty = self.order_sizer.calculate(specs, current_balance, self.config.RISK_PER_TRADE_PCT, entry, sl, self.config.LEVERAGE)

                        if qty and qty >= specs.min_order_qty:
                            self.bot_state.add_log(f"Signal: {side}. Placing order for {qty} {self.config.SYMBOL}...")
                            self.place_order(specs, side, qty, self.config.ORDER_TYPE_ENUM, entry,
                                             self.precision_manager.round_price(specs, sl),
                                             self.precision_manager.round_price(specs, tp))
                        else:
                            self.bot_state.add_log(f"Signal: {side}. Calculated quantity ({qty if qty else '0'}) too small or invalid (min: {specs.min_order_qty}).")
                    else:
                        self.logger.error("Could not get instrument specs, cannot place order.")
                else:
                    self.bot_state.add_log("No trade signal.")
            else:
                self.bot_state.add_log("Not enough klines for signal generation.")

    def _main_loop_iteration(self):
        self.bot_state.update(bot_status="Running")

        # Periodically refresh position data from REST API
        # This is important to ensure consistency with exchange, especially after order execution
        self.get_positions()

        # Check for max daily loss (includes daily PnL reset)
        self._check_daily_loss()

        # Process kline data for signals if conditions met
        self._process_kline_data()

        # Position management (breakeven, trailing SL, partial TP) is handled by _handle_ticker on price updates

    def run(self):
        ui_thread = None
        try:
            ui_thread = BotUI(self.bot_state, self.config)
            ui_thread.start()

            self._initialize_bot()
            self._start_websocket_listeners()

            while not self._stop_requested:
                try:
                    self._main_loop_iteration()
                except Exception as e:
                    self.logger.error(f"Error in main loop iteration: {e}", exc_info=True)
                    self.bot_state.add_log(f"Error in main loop: {e}")
                    self.bot_state.update(bot_status="Error")
                time.sleep(5) # Main loop interval, ticker/kline updates are asynchronous

        except Exception as e:
            self.logger.critical(f"Fatal error during bot startup or main execution: {e}", exc_info=True)
            self.bot_state.update(bot_status="Critical Error")
            sys.exit(1)
        finally:
            if self.ws_kline: self.ws_kline.exit()
            if self.ws_ticker: self.ws_ticker.exit()
            if ui_thread:
                ui_thread.stop()
                ui_thread.join()
            self.logger.info("Bot shutdown complete.")

if __name__ == "__main__":
    try:
        config = Config()
        bot = SupertrendBot(config)
        bot.run()
    except ValueError as ve:
        # Configuration errors are critical and should stop the bot
        logging.getLogger('SupertrendBot').critical(f"Configuration Error: {ve}")
        sys.exit(1)
    except Exception as e:
        # Catch any other unexpected errors during initial startup
        logging.getLogger('SupertrendBot').critical(f"Fatal error on startup: {e}", exc_info=True)
        sys.exit(1)
```
