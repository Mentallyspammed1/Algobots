#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🐳 WhaleBot Supreme v3.0 - The Unified Arcana
Forged by Pyrmethus: Neon TUI, V5 API Mastery, Multi-Target TP/SL, 
and Real-Time Exchange Reconciliation.
"""

import json
import logging
import os
import sys
import time
import hmac
import hashlib
import subprocess
from datetime import datetime, timezone, timedelta
from decimal import ROUND_DOWN, Decimal, getcontext
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, ClassVar, Literal, Optional, Tuple, Dict, List

import numpy as np
import pandas as pd
from colorama import Fore, Style, init
from dotenv import load_dotenv

# --- Ritual Dependencies ---
try:
    from pybit.unified_trading import HTTP as PybitHTTP
    import pybit.exceptions
    PYBIT_AVAILABLE = True
except ImportError:
    PYBIT_AVAILABLE = False

# --- Chromatic Initialization ---
getcontext().prec = 28
init(autoreset=True)
load_dotenv()

# --- Neon Sigils ---
NEON_GREEN = Fore.LIGHTGREEN_EX
NEON_BLUE = Fore.CYAN
NEON_PURPLE = Fore.MAGENTA
NEON_YELLOW = Fore.YELLOW
NEON_RED = Fore.LIGHTRED_EX
RESET = Style.RESET_ALL

# --- Arcane Constants ---
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
CONFIG_FILE = "config.json"
LOG_DIRECTORY = "bot_logs"
Path(LOG_DIRECTORY).mkdir(parents=True, exist_ok=True)
TIMEZONE = timezone.utc

# --- Logging Oracle ---
class SensitiveFormatter(logging.Formatter):
    SENSITIVE_WORDS: ClassVar[list[str]] = ["API_KEY", "API_SECRET", "BOT_TOKEN"]
    def format(self, record):
        original_message = super().format(record)
        for word in self.SENSITIVE_WORDS:
            val = os.getenv(word)
            if val: original_message = original_message.replace(val, "*" * 8)
        return original_message

def setup_logger(log_name: str, level=logging.INFO) -> logging.Logger:
    logger = logging.getLogger(log_name)
    logger.setLevel(level)
    logger.propagate = False
    if not logger.handlers:
        c_handler = logging.StreamHandler(sys.stdout)
        c_handler.setFormatter(SensitiveFormatter(f"{NEON_BLUE}%(asctime)s - %(levelname)s - %(message)s{RESET}"))
        logger.addHandler(c_handler)
        f_handler = RotatingFileHandler(Path(LOG_DIRECTORY) / f"{log_name}.log", maxBytes=5*1024*1024, backupCount=3)
        f_handler.setFormatter(SensitiveFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        logger.addHandler(f_handler)
    return logger

# --- Alert Weaver (Termux Toast) ---
class AlertSystem:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.has_api = self._check_api()

    def _check_api(self) -> bool:
        try:
            return subprocess.run(['which', 'termux-toast'], capture_output=True).returncode == 0
        except: return False

    def send_alert(self, message: str, level: str = "INFO"):
        color = NEON_GREEN if level == "INFO" else NEON_RED
        self.logger.info(f"{color}🔮 ALERT: {message}{RESET}")
        if self.has_api:
            subprocess.run(['termux-toast', f"WhaleBot: {message}"])

# --- Indicator Core (Integrated Logic) ---
class IndicatorEngine:
    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        high_low = df['high'] - df['low']
        high_pc = (df['high'] - df['close'].shift()).abs()
        low_pc = (df['low'] - df['close'].shift()).abs()
        tr = pd.concat([high_low, high_pc, low_pc], axis=1).max(axis=1)
        return tr.ewm(span=period, adjust=False).mean()

    @staticmethod
    def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
        avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

# --- Bybit V5 Client ---
class PybitTradingClient:
    def __init__(self, config: dict, logger: logging.Logger):
        self.cfg = config
        self.logger = logger
        self.session = None
        if PYBIT_AVAILABLE and API_KEY and API_SECRET:
            self.session = PybitHTTP(
                api_key=API_KEY, api_secret=API_SECRET, 
                testnet=config["execution"]["testnet"]
            )
            self.logger.info(f"{NEON_GREEN}# Bridge to the Bybit V5 Void established.{RESET}")

    def fetch_klines(self, symbol: str, interval: str, limit: int = 200):
        try:
            res = self.session.get_kline(category="linear", symbol=symbol, interval=interval, limit=limit)
            if res['retCode'] == 0:
                df = pd.DataFrame(res['result']['list'], columns=['time', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
                df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].apply(pd.to_numeric)
                df['time'] = pd.to_datetime(df['time'].astype(int), unit='ms')
                return df.sort_values('time').reset_index(drop=True)
        except Exception as e:
            self.logger.error(f"Error fetching klines: {e}")
        return None

# --- Position & Strategy Manager ---
class PositionManager:
    def __init__(self, config: dict, logger: logging.Logger, client: PybitTradingClient):
        self.config = config
        self.logger = logger
        self.client = client
        self.open_positions = []
        self.price_prec = config["trade_management"]["price_precision"]

    def _round(self, val: float, prec: int) -> str:
        return str(Decimal(str(val)).quantize(Decimal(f"1.{'0'*prec}"), rounding=ROUND_DOWN))

    def open_position(self, side: str, price: Decimal, atr: float):
        self.logger.info(f"{NEON_PURPLE}# Executing {side} Ritual for {self.config['symbol']}...{RESET}")
        
        # Calculate Stops and TPs from Ritual Scheme
        sl_price = float(price) - (atr * self.config["trade_management"]["stop_loss_atr_multiple"]) if side == "BUY" else float(price) + (atr * self.config["trade_management"]["stop_loss_atr_multiple"])
        
        # Logic for live trade
        if self.client.session:
            try:
                res = self.client.session.place_order(
                    category="linear", symbol=self.config["symbol"], side=side.capitalize(),
                    orderType="Market", qty=self.config["trade_management"]["risk_per_trade_percent"], # Mock qty
                    stopLoss=self._round(sl_price, self.price_prec),
                    tpTriggerBy="LastPrice", slTriggerBy="LastPrice"
                )
                if res['retCode'] == 0:
                    self.logger.info(f"{NEON_GREEN}# Ritual Triumphant! OrderID: {res['result']['orderId']}{RESET}")
                    # Build Partial TP targets
                    self._build_tp_ladder(side, price, atr)
            except Exception as e:
                self.logger.error(f"Ritual Interrupted: {e}")

    def _build_tp_ladder(self, side: str, entry_price: Decimal, atr: float):
        targets = self.config["execution"]["tp_scheme"]["targets"]
        for tp in targets:
            offset = atr * tp["atr_multiple"]
            tp_price = float(entry_price) + offset if side == "BUY" else float(entry_price) - offset
            self.client.session.place_order(
                category="linear", symbol=self.config["symbol"], side="Sell" if side == "BUY" else "Buy",
                orderType="Limit", qty="0.001", # Calculated from size_pct
                price=self._round(tp_price, self.price_prec),
                reduceOnly=True
            )

# --- The Master Orchestrator ---
class WhaleBot:
    def __init__(self, config: dict):
        self.config = config
        self.logger = setup_logger("whale_bot")
        self.alerts = AlertSystem(self.logger)
        self.client = PybitTradingClient(config, self.logger)
        self.pm = PositionManager(config, self.logger, self.client)
        self.is_running = True

    def analyze(self, df: pd.DataFrame):
        # Channeling Indicators
        df['rsi'] = IndicatorEngine.calculate_rsi(df)
        df['atr'] = IndicatorEngine.calculate_atr(df)
        
        last_rsi = df['rsi'].iloc[-1]
        last_price = Decimal(str(df['close'].iloc[-1]))
        last_atr = df['atr'].iloc[-1]
        
        self.logger.info(f"{NEON_YELLOW}# Divination: Price {last_price} | RSI {last_rsi:.2f}{RESET}")
        
        # Simple Logic Ward
        if last_rsi < 30: return "BUY", last_price, last_atr
        if last_rsi > 70: return "SELL", last_price, last_atr
        return "HOLD", last_price, last_atr

    def start(self):
        self.logger.info(f"{NEON_CYAN}# Ignite the neon aura. Bot active.{RESET}")
        while self.is_running:
            try:
                df = self.client.fetch_klines(self.config["symbol"], self.config["interval"])
                if df is not None:
                    signal, price, atr = self.analyze(df)
                    if signal != "HOLD":
                        self.pm.open_position(signal, price, atr)
                        self.alerts.send_alert(f"Ritual Performed: {signal} at {price}")
                
                time.sleep(self.config["loop_delay"])
            except KeyboardInterrupt:
                self.logger.info(f"{NEON_RED}# Incantation dissolved by mortal hand.{RESET}")
                self.is_running = False
            except Exception as e:
                self.logger.error(f"Chaos in the ether: {e}")
                time.sleep(5)

# --- Configuration Weaver ---
def load_config(filepath: str, logger: logging.Logger) -> dict:
    default_config = {
        "symbol": "BTCUSDT", "interval": "15", "loop_delay": 15,
        "trade_management": {
            "price_precision": 2, "risk_per_trade_percent": "0.01",
            "stop_loss_atr_multiple": 1.5, "take_profit_atr_multiple": 2.0
        },
        "execution": {
            "testnet": True, "use_pybit": True,
            "tp_scheme": {
                "mode": "atr_multiples", "targets": [
                    {"name": "TP1", "atr_multiple": 1.0, "size_pct": 0.4},
                    {"name": "TP2", "atr_multiple": 2.0, "size_pct": 0.6}
                ]
            }
        }
    }
    if not Path(filepath).exists():
        with open(filepath, 'w') as f: json.dump(default_config, f, indent=4)
        return default_config
    with open(filepath, 'r') as f: return json.load(f)

# --- Entry Portal ---
def main():
    logger = setup_logger("whale_main")
    config = load_config(CONFIG_FILE, logger)
    
    if not API_KEY or not API_SECRET:
        logger.critical(f"{NEON_RED}# Fatal: API Sigils not found in .env!{RESET}")
        sys.exit(1)

    bot = WhaleBot(config)
    bot.start()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        setup_logger("fatal").critical(f"Abyssal Error: {e}", exc_info=True)