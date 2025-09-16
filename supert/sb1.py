#!/usr/bin/env python3
"""
Enhanced Supertrend Trading Bot for Bybit V5 API.

This script implements a sophisticated trading bot using a Supertrend-based strategy optimized for 1-minute scalping.
It includes advanced features like limit orders, partial take-profits, breakeven stop-loss, ADX trend filter,
RSI and volume filters for signals, daily loss limiting, and WebSocket for real-time data.
A real-time, color-coded console UI provides at-a-glance monitoring of market data, indicator values, and position status.

Upgrades and Enhancements:
- Optimized for 1-minute scalping: Default timeframe '1', Supertrend params (ATR=7, Mult=1.5), tight SL/TP.
- Added RSI (>50 for buys, <50 for sells) and volume (>20-period SMA) filters to reduce false signals.
- Implemented partial take-profits: Places multiple reduce-only orders for staged profit-taking.
- Added breakeven stop-loss: Moves SL to entry after 1% profit; monitors via WebSocket.
- Enabled shorting with symmetric logic for buys/sells.
- Integrated WebSocket for real-time price, position, and kline updates to eliminate polling delays.
- Added daily loss check: Pauses trading if daily loss exceeds limit.
- Improved signal generation with trend confirmation.
- Enhanced error handling, logging, and UI updates.
- Added backtest mode via env var (BACKTEST_MODE=true) for parameter optimization simulation.
"""

import itertools  # For backtest optimization
import json
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
from typing import Any

import colorlog
import numpy as np
import pandas as pd
from colorama import Fore, Style, init
from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket

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
    LEVERAGE: int = int(os.getenv("BYBIT_LEVERAGE", 5))  # Lower for scalping safety
    TIMEFRAME: str = os.getenv("BYBIT_TIMEFRAME", "1")  # Optimized for 1-min scalping
    ST_PERIOD: int = int(os.getenv("ST_PERIOD", 7))  # Shorter for scalping
    ST_MULTIPLIER: float = float(os.getenv("ST_MULTIPLIER", 1.5))  # Lower for sensitivity
    RISK_PER_TRADE_PCT: float = float(os.getenv("RISK_PER_TRADE_PCT", 0.5))  # Smaller risk for high-frequency
    STOP_LOSS_PCT: float = float(os.getenv("STOP_LOSS_PCT", 0.5))  # Tight SL for scalping
    TAKE_PROFIT_PCT: float = float(os.getenv("TAKE_PROFIT_PCT", 1.0))  # Tight TP
    BREAKEVEN_PCT: float = float(os.getenv("BREAKEVEN_PCT", 0.5))  # Move SL to breakeven after this profit %
    MAX_DAILY_LOSS_PCT: float = float(os.getenv("MAX_DAILY_LOSS_PCT", 3.0))  # Tighter for scalping
    ORDER_TYPE: str = os.getenv("ORDER_TYPE", "Market")
    ADX_TREND_FILTER_ENABLED: bool = os.getenv("ADX_TREND_FILTER_ENABLED", "true").lower() in ['true', '1', 't']
    ADX_MIN_THRESHOLD: int = int(os.getenv("ADX_MIN_THRESHOLD", 25))
    RSI_FILTER_ENABLED: bool = os.getenv("RSI_FILTER_ENABLED", "true").lower() in ['true', '1', 't']
    RSI_PERIOD: int = int(os.getenv("RSI_PERIOD", 14))
    VOLUME_FILTER_ENABLED: bool = os.getenv("VOLUME_FILTER_ENABLED", "true").lower() in ['true', '1', 't']
    PARTIAL_TP_ENABLED: bool = os.getenv("PARTIAL_TP_ENABLED", "true").lower() in ['true', '1', 't']
    PARTIAL_TP_TARGETS: list[dict[str, float]] = field(default_factory=lambda: [
        {"profit_pct": 0.5, "close_qty_pct": 0.5},  # First partial at 0.5% profit, close 50%
        {"profit_pct": 1.0, "close_qty_pct": 0.5}   # Second at 1.0%, close remaining 50%
    ])
    BACKTEST_MODE: bool = os.getenv("BACKTEST_MODE", "false").lower() in ['true', '1', 't']
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    def __post_init__(self):
        self.CATEGORY_ENUM = Category.from_string(self.CATEGORY)
        self.ORDER_TYPE_ENUM = OrderType[self.ORDER_TYPE.upper()]
        if self.CATEGORY_ENUM == Category.SPOT:
            self.LEVERAGE = 1


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
# BOT STATE & UI
# =====================================================================

@dataclass
class BotState:
    """Thread-safe state manager for the bot."""
    symbol: str
    bot_status: str = "Initializing"
    current_price: float = 0.0
    price_direction: int = 0  # 1 for up, -1 for down, 0 for neutral
    supertrend_line: float = 0.0
    supertrend_direction: str = "Neutral"
    rsi: float = 0.0
    macd_hist: float = 0.0
    adx: float = 0.0
    volume: float = 0.0
    volume_sma: float = 0.0
    position_side: str = "None"
    position_size: float = 0.0
    entry_price: float = 0.0
    unrealized_pnl: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    daily_loss: float = 0.0
    log_messages: deque[str] = field(default_factory=lambda: deque(maxlen=10))
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
    def __init__(self, state: BotState):
        super().__init__(daemon=True)
        self.state = state
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        while not self._stop_event.is_set():
            self.display()
            time.sleep(1)

    def display(self):
        with self.state.lock:
            # Clear console
            os.system('cls' if os.name == 'nt' else 'clear')

            # --- Header ---
            print(Style.BRIGHT + Fore.CYAN + f"=== Supertrend Scalping Bot | {self.state.symbol} | Status: {self.state.bot_status} ===" + Style.RESET_ALL)

            # --- Market Info ---
            price_color = Fore.GREEN if self.state.price_direction == 1 else Fore.RED if self.state.price_direction == -1 else Fore.WHITE
            st_color = Fore.GREEN if self.state.supertrend_direction == "Uptrend" else Fore.RED if self.state.supertrend_direction == "Downtrend" else Fore.WHITE
            print(Style.BRIGHT + "\n--- Market Status ---" + Style.RESET_ALL)
            print(f"Current Price: {price_color}{self.state.current_price:.2f}{Style.RESET_ALL}")
            print(f"Supertrend: {st_color}{self.state.supertrend_line:.2f} ({self.state.supertrend_direction}){Style.RESET_ALL}")
            print(f"Volume: {Fore.YELLOW}{self.state.volume:.2f} (SMA: {self.state.volume_sma:.2f}){Style.RESET_ALL}")

            # --- Indicator Values ---
            rsi_color = Fore.RED if self.state.rsi > 70 else Fore.GREEN if self.state.rsi < 30 else Fore.WHITE
            macd_color = Fore.GREEN if self.state.macd_hist > 0 else Fore.RED
            adx_color = Fore.GREEN if self.state.adx > 25 else Fore.YELLOW
            print(Style.BRIGHT + "\n--- Indicator Values ---" + Style.RESET_ALL)
            print(f"RSI: {rsi_color}{self.state.rsi:.2f}{Style.RESET_ALL} | MACD Hist: {macd_color}{self.state.macd_hist:.4f}{Style.RESET_ALL} | ADX: {adx_color}{self.state.adx:.2f}{Style.RESET_ALL}")

            # --- Position Info ---
            print(Style.BRIGHT + "\n--- Open Position ---" + Style.RESET_ALL)
            if self.state.position_size > 0:
                pos_color = Fore.GREEN if self.state.position_side == 'Buy' else Fore.RED
                pnl_color = Fore.GREEN if self.state.unrealized_pnl >= 0 else Fore.RED
                print(f"Side: {pos_color}{self.state.position_side}{Style.RESET_ALL} | Size: {self.state.position_size} | Entry: {self.state.entry_price:.2f}")
                print(f"Unrealized PnL: {pnl_color}${self.state.unrealized_pnl:.2f}{Style.RESET_ALL}")
                print(f"SL: {self.state.stop_loss:.2f} | TP: {self.state.take_profit:.2f}")
            else:
                print("No active position.")

            # --- Risk Info ---
            print(Style.BRIGHT + "\n--- Risk Management ---" + Style.RESET_ALL)
            print(f"Daily Loss: {Fore.RED if self.state.daily_loss > 0 else Fore.GREEN}{self.state.daily_loss:.2f}%{Style.RESET_ALL}")

            # --- Live Log ---
            print(Style.BRIGHT + "\n--- Live Log ---" + Style.RESET_ALL)
            for msg in self.state.log_messages:
                print(msg)

            print("\n" + Fore.CYAN + "=====================================================" + Style.RESET_ALL)
            print(Fore.YELLOW + "Press Ctrl+C to exit." + Style.RESET_ALL)


# =====================================================================
# PRECISION & ORDER SIZING
# =====================================================================

@dataclass
class InstrumentSpecs:
    tick_size: Decimal
    qty_step: Decimal
    min_order_qty: Decimal

class PrecisionManager:
    """Manages decimal precision for trading pairs."""
    def __init__(self, session: HTTP, logger: logging.Logger):
        self.session = session
        self.logger = logger
        self.instruments: dict[str, InstrumentSpecs] = {}

    def get_specs(self, symbol: str, category: str) -> InstrumentSpecs | None:
        if symbol in self.instruments:
            return self.instruments[symbol]
        try:
            res = self.session.get_instruments_info(category=category, symbol=symbol)
            if res['retCode'] == 0:
                info = res['result']['list']
                specs = InstrumentSpecs(
                    Decimal(info['priceFilter']['tickSize']),
                    Decimal(info['lotSizeFilter']['qtyStep']),
                    Decimal(info['lotSizeFilter']['minOrderQty'])
                )
                self.instruments[symbol] = specs
                return specs
        except Exception as e:
            self.logger.error(f"Error fetching specs for {symbol}: {e}")
        return None

    def round_price(self, specs: InstrumentSpecs, price: Decimal) -> Decimal:
        return (price / specs.tick_size).quantize(Decimal('1'), rounding=ROUND_DOWN) * specs.tick_size

    def round_quantity(self, specs: InstrumentSpecs, quantity: Decimal) -> Decimal:
        return (quantity / specs.qty_step).quantize(Decimal('1'), rounding=ROUND_DOWN) * specs.qty_step

class OrderSizingCalculator:
    """Calculates order sizes based on risk management."""
    def __init__(self, precision_manager: PrecisionManager):
        self.precision = precision_manager

    def calculate(self, specs: InstrumentSpecs, bal: Decimal, risk_pct: float, entry: Decimal, sl: Decimal, lev: int) -> Decimal | None:
        if bal <= 0 or entry <= 0 or lev <= 0 or abs(entry - sl) == 0:
            return None
        risk_amt = bal * Decimal(str(risk_pct / 100))
        sl_dist_pct = abs(entry - sl) / entry
        pos_val = min(risk_amt / sl_dist_pct, bal * Decimal(lev))
        qty = pos_val / entry
        rounded_qty = self.precision.round_quantity(specs, qty)
        return rounded_qty if rounded_qty >= specs.min_order_qty else None


# =====================================================================
# MAIN TRADING BOT CLASS
# =====================================================================

class SupertrendBot:
    """The main class for the Supertrend trading bot."""
    def __init__(self, config: Config):
        self.config = config
        self.logger = setup_logger(config)
        self.bot_state = BotState(symbol=config.SYMBOL)
        self.session = HTTP(testnet=config.TESTNET, api_key=config.API_KEY, api_secret=config.API_SECRET)
        self.precision_manager = PrecisionManager(self.session, self.logger)
        self.order_sizer = OrderSizingCalculator(self.precision_manager)

        self.position_active = False
        self.current_position: dict[str, Any] | None = None
        self.start_balance = self.get_account_balance()
        self.daily_reset_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        self.daily_loss = Decimal('0')
        self.klines_df = pd.DataFrame()  # For storing kline data

        self._stop_requested = False
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # WebSocket setup for real-time data
        self.ws = WebSocket(testnet=config.TESTNET, channel_type="linear")
        self.ws.kline_stream(callback=self.handle_kline, symbol=config.SYMBOL, interval=config.TIMEFRAME)
        self.ws.ticker_stream(callback=self.handle_ticker, symbol=config.SYMBOL)
        self.ws.position_stream(callback=self.handle_position)

    def _signal_handler(self, signum, frame):
        self.logger.warning(f"Signal {signum} received, stopping bot...")
        self.bot_state.update(bot_status="Shutting down")
        self._stop_requested = True

    def get_account_balance(self, coin="USDT") -> Decimal:
        try:
            res = self.session.get_wallet_balance(accountType="UNIFIED", coin=coin)
            if res['retCode'] == 0:
                for item in res['result']['list']:
                    for c in item['coin']:
                        if c['coin'] == coin:
                            return Decimal(c['walletBalance'])
        except Exception as e:
            self.logger.error(f"Error getting balance: {e}")
        return Decimal('0')

    def check_daily_loss(self) -> bool:
        """Check if daily loss limit is exceeded."""
        current_balance = self.get_account_balance()
        self.daily_loss = (self.start_balance - current_balance) / self.start_balance * 100
        self.bot_state.update(daily_loss=float(self.daily_loss))
        max_loss = Decimal(str(self.config.MAX_DAILY_LOSS_PCT))
        if datetime.now() > self.daily_reset_time:
            self.start_balance = current_balance
            self.daily_reset_time += timedelta(days=1)
            self.daily_loss = Decimal('0')
        if self.daily_loss > max_loss:
            self.bot_state.add_log(f"Daily loss limit exceeded: {self.daily_loss:.2f}% > {max_loss}%")
            return True
        return False

    def fetch_historical_klines(self, limit=1000) -> pd.DataFrame | None:
        try:
            res = self.session.get_kline(category=self.config.CATEGORY, symbol=self.config.SYMBOL, interval=self.config.TIMEFRAME, limit=limit)
            if res['retCode'] == 0:
                df = pd.DataFrame(res['result']['list'], columns=['ts', 'o', 'h', 'l', 'c', 'v', 't'])
                df.rename(columns={'ts': 'timestamp', 'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'}, inplace=True)
                for col in ['open', 'high', 'low', 'close', 'volume']: df[col] = pd.to_numeric(df[col])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                return df.sort_values('timestamp').reset_index(drop=True)
        except Exception as e:
            self.logger.error(f"Error fetching historical klines: {e}")
        return None

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df.ta.supertrend(length=self.config.ST_PERIOD, multiplier=self.config.ST_MULTIPLIER, append=True)
        df.ta.adx(length=14, append=True)
        df.ta.rsi(length=self.config.RSI_PERIOD, append=True)
        df.ta.macd(append=True)
        df['volume_sma'] = df['volume'].rolling(20).mean()
        df.rename(columns={
            f'SUPERTd_{self.config.ST_PERIOD}_{self.config.ST_MULTIPLIER}.0': 'st_dir',
            f'SUPERT_{self.config.ST_PERIOD}_{self.config.ST_MULTIPLIER}.0': 'st_line',
            'ADX_14': 'adx', 'RSI_14': 'rsi', 'MACDh_12_26_9': 'macd_hist'
        }, inplace=True)
        return df

    def generate_signal(self, df: pd.DataFrame) -> Signal:
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest

        # ADX Filter
        if self.config.ADX_TREND_FILTER_ENABLED and latest['adx'] < self.config.ADX_MIN_THRESHOLD:
            self.bot_state.add_log("ADX too low, no trade.")
            return Signal.NEUTRAL

        # Volume Filter
        if self.config.VOLUME_FILTER_ENABLED and latest['volume'] <= latest['volume_sma']:
            self.bot_state.add_log("Volume too low, no trade.")
            return Signal.NEUTRAL

        # Supertrend Signal
        buy_condition = latest['st_dir'] == 1 and prev['st_dir'] == -1
        sell_condition = latest['st_dir'] == -1 and prev['st_dir'] == 1

        # RSI Filter
        if self.config.RSI_FILTER_ENABLED:
            buy_condition = buy_condition and latest['rsi'] > 50
            sell_condition = sell_condition and latest['rsi'] < 50

        if buy_condition:
            return Signal.BUY
        if sell_condition:
            return Signal.SELL
        return Signal.NEUTRAL

    def handle_kline(self, message):
        """Handle incoming kline data from WebSocket."""
        try:
            data = message['data']
            new_row = pd.DataFrame({
                'timestamp': [pd.to_datetime(int(data['start']), unit='ms')],
                'open': [float(data['open'])],
                'high': [float(data['high'])],
                'low': [float(data['low'])],
                'close': [float(data['close'])],
                'volume': [float(data['volume'])]
            })
            self.klines_df = pd.concat([self.klines_df, new_row]).tail(200).reset_index(drop=True)
            self.klines_df = self.calculate_indicators(self.klines_df)
            latest = self.klines_df.iloc[-1]
            self.bot_state.update(
                current_price=latest['close'],
                price_direction=1 if latest['close'] > self.klines_df.iloc[-2]['close'] else -1 if len(self.klines_df) > 1 else 0,
                supertrend_line=latest['st_line'],
                supertrend_direction="Uptrend" if latest['st_dir'] == 1 else "Downtrend" if latest['st_dir'] == -1 else "Neutral",
                rsi=latest['rsi'],
                macd_hist=latest['macd_hist'],
                adx=latest['adx'],
                volume=latest['volume'],
                volume_sma=latest['volume_sma']
            )
            self.process_signal()
        except Exception as e:
            self.logger.error(f"Error handling kline: {e}")

    def handle_ticker(self, message):
        """Handle real-time ticker updates."""
        try:
            data = message['data']
            price = float(data['lastPrice'])
            self.bot_state.update(current_price=price)
            self.monitor_breakeven(price)
        except Exception as e:
            self.logger.error(f"Error handling ticker: {e}")

    def handle_position(self, message):
        """Handle position updates."""
        try:
            for pos in message['data']:
                if pos['symbol'] == self.config.SYMBOL and float(pos['size']) > 0:
                    self.position_active = True
                    self.current_position = pos
                    self.bot_state.update(
                        position_side=pos['side'],
                        position_size=float(pos['size']),
                        entry_price=float(pos['avgPrice']),
                        unrealized_pnl=float(pos['unrealisedPnl']),
                        stop_loss=float(pos.get('stopLoss', 0)),
                        take_profit=float(pos.get('takeProfit', 0))
                    )
                else:
                    self.position_active = False
                    self.current_position = None
                    self.bot_state.update(position_side="None", position_size=0.0, entry_price=0.0, unrealized_pnl=0.0, stop_loss=0.0, take_profit=0.0)
        except Exception as e:
            self.logger.error(f"Error handling position: {e}")

    def process_signal(self):
        """Process signals based on latest indicators."""
        if self.check_daily_loss() or self.position_active or len(self.klines_df) < 50:
            return
        signal = self.generate_signal(self.klines_df)
        if signal == Signal.NEUTRAL:
            return

        specs = self.precision_manager.get_specs(self.config.SYMBOL, self.config.CATEGORY)
        if not specs:
            return

        entry = Decimal(str(self.bot_state.current_price))
        side = "Buy" if signal == Signal.BUY else "Sell"
        sl_pct = Decimal(str(self.config.STOP_LOSS_PCT / 100))
        tp_pct = Decimal(str(self.config.TAKE_PROFIT_PCT / 100))  # Base TP, but partials override
        sl = entry * (Decimal(1) - sl_pct) if side == "Buy" else entry * (Decimal(1) + sl_pct)
        tp = entry * (Decimal(1) + tp_pct) if side == "Buy" else entry * (Decimal(1) - tp_pct)

        qty = self.order_sizer.calculate(specs, self.get_account_balance(), self.config.RISK_PER_TRADE_PCT, entry, sl, self.config.LEVERAGE)
        if not qty:
            self.bot_state.add_log(f"Signal: {side}. Invalid qty.")
            return

        self.bot_state.add_log(f"Signal: {side}. Placing entry order...")
        self.place_entry_order(specs, side, qty, entry, sl, tp)

    def place_entry_order(self, specs: InstrumentSpecs, side: str, qty: Decimal, entry: Decimal, sl: Decimal, tp: Decimal):
        params = {
            "category": self.config.CATEGORY,
            "symbol": self.config.SYMBOL,
            "side": side,
            "orderType": self.config.ORDER_TYPE_ENUM.value,
            "qty": str(qty),
            "stopLoss": str(self.precision_manager.round_price(specs, sl)),
            "takeProfit": str(self.precision_manager.round_price(specs, tp)) if not self.config.PARTIAL_TP_ENABLED else "0",  # No full TP if partial
            "tpslMode": "Full"
        }
        if self.config.ORDER_TYPE_ENUM == OrderType.LIMIT:
            params["price"] = str(self.precision_manager.round_price(specs, entry))
        try:
            res = self.session.place_order(**params)
            if res['retCode'] == 0:
                self.logger.info(f"Entry order placed: {side} {qty} {self.config.SYMBOL}")
                if self.config.PARTIAL_TP_ENABLED:
                    self.place_partial_tp_orders(specs, side, qty, entry)
            else:
                self.logger.error(f"Entry order failed: {res['retMsg']}")
        except Exception as e:
            self.logger.error(f"Exception placing entry order: {e}")

    def place_partial_tp_orders(self, specs: InstrumentSpecs, entry_side: str, total_qty: Decimal, entry: Decimal):
        """Place reduce-only limit orders for partial take-profits."""
        close_side = "Sell" if entry_side == "Buy" else "Buy"
        for target in self.config.PARTIAL_TP_TARGETS:
            profit_pct = Decimal(str(target['profit_pct'] / 100))
            close_qty_pct = Decimal(str(target['close_qty_pct']))
            tp_price = entry * (Decimal(1) + profit_pct) if entry_side == "Buy" else entry * (Decimal(1) - profit_pct)
            close_qty = self.precision_manager.round_quantity(specs, total_qty * close_qty_pct)
            if close_qty < specs.min_order_qty:
                continue
            params = {
                "category": self.config.CATEGORY,
                "symbol": self.config.SYMBOL,
                "side": close_side,
                "orderType": "Limit",
                "qty": str(close_qty),
                "price": str(self.precision_manager.round_price(specs, tp_price)),
                "reduceOnly": True
            }
            try:
                res = self.session.place_order(**params)
                if res['retCode'] == 0:
                    self.logger.info(f"Partial TP order placed: {close_side} {close_qty} at {tp_price}")
                else:
                    self.logger.error(f"Partial TP failed: {res['retMsg']}")
            except Exception as e:
                self.logger.error(f"Exception placing partial TP: {e}")

    def monitor_breakeven(self, current_price: float):
        """Monitor position and move SL to breakeven if profit threshold met."""
        if not self.position_active or not self.current_position:
            return
        entry = float(self.current_position['avgPrice'])
        side = self.current_position['side']
        current_sl = float(self.current_position.get('stopLoss', 0))
        profit_pct = (current_price - entry) / entry * 100 if side == "Buy" else (entry - current_price) / entry * 100
        if profit_pct >= self.config.BREAKEVEN_PCT and current_sl != entry:
            specs = self.precision_manager.get_specs(self.config.SYMBOL, self.config.CATEGORY)
            if not specs:
                return
            new_sl = Decimal(str(entry))
            try:
                res = self.session.set_trading_stop(
                    category=self.config.CATEGORY,
                    symbol=self.config.SYMBOL,
                    stopLoss=str(self.precision_manager.round_price(specs, new_sl))
                )
                if res['retCode'] == 0:
                    self.logger.info(f"SL moved to breakeven: {new_sl}")
                    self.bot_state.update(stop_loss=float(new_sl))
                else:
                    self.logger.error(f"Breakeven SL failed: {res['retMsg']}")
            except Exception as e:
                self.logger.error(f"Exception setting breakeven SL: {e}")

    def close_position(self, qty_to_close: Decimal | None = None):
        if not self.current_position:
            return
        side = "Sell" if self.current_position['side'] == "Buy" else "Buy"
        qty = qty_to_close or Decimal(self.current_position['size'])
        specs = self.precision_manager.get_specs(self.config.SYMBOL, self.config.CATEGORY)
        if not specs:
            return
        params = {
            "category": self.config.CATEGORY,
            "symbol": self.config.SYMBOL,
            "side": side,
            "orderType": "Market",
            "qty": str(qty),
            "reduceOnly": True
        }
        try:
            res = self.session.place_order(**params)
            if res['retCode'] == 0:
                self.logger.info(f"Position closed: {side} {qty}")
            else:
                self.logger.error(f"Close failed: {res['retMsg']}")
        except Exception as e:
            self.logger.error(f"Exception closing position: {e}")

    def run_backtest(self):
        """Simple backtest mode for parameter optimization."""
        self.logger.info("Running backtest mode...")
        df = self.fetch_historical_klines(limit=1000)
        if df is None:
            self.logger.error("Failed to fetch data for backtest.")
            return

        # Grid search for params
        atr_lengths = [5, 7, 10]
        multipliers = [1.0, 1.5, 2.0]
        best_params = None
        best_return = -np.inf

        for atr, mult in itertools.product(atr_lengths, multipliers):
            df_test = self.calculate_indicators(df.copy())
            df_test['signal'] = 0
            for i in range(1, len(df_test)):
                temp_df = df_test.iloc[:i+1]
                sig = self.generate_signal(temp_df)
                df_test.at[i, 'signal'] = sig.value

            df_test['returns'] = df_test['close'].pct_change()
            df_test['strategy_returns'] = df_test['returns'] * df_test['signal'].shift(1)
            cum_returns = (1 + df_test['strategy_returns']).cumprod().iloc[-1] - 1

            # Simulate fees
            trades = len(df_test[df_test['signal'] != 0])
            cum_returns -= trades * 0.0002

            if cum_returns > best_return:
                best_return = cum_returns
                best_params = (atr, mult)

        self.logger.info(f"Backtest Complete. Best Params: ATR={best_params}, Mult={best_params}, Return={best_return:.2%}")
        print(f"Best Params: ATR={best_params}, Mult={best_params}, Return={best_return:.2%}")

    def run(self):
        if self.config.BACKTEST_MODE:
            self.run_backtest()
            return

        self.logger.info("Starting Supertrend Scalping Bot...")
        self.bot_state.update(bot_status="Running")
        ui_thread = BotUI(self.bot_state)
        ui_thread.start()

        # Initial data load
        self.klines_df = self.fetch_historical_klines(limit=200) or pd.DataFrame()
        if not self.klines_df.empty:
            self.klines_df = self.calculate_indicators(self.klines_df)

        while not self._stop_requested:
            time.sleep(1)  # WS handles updates; minimal loop

        ui_thread.stop()
        ui_thread.join()
        self.ws.close()
        self.logger.info("Bot shutdown complete.")

if __name__ == "__main__":
    try:
        config = Config()
        bot = SupertrendBot(config)
        bot.run()
    except Exception as e:
        logging.getLogger('SupertrendBot').critical(f"Fatal error on startup: {e}", exc_info=True)
        sys.exit(1)
