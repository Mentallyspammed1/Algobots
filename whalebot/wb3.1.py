#!/usr/bin/env python3
"""
🐳 WhaleBot Supreme v3.5 - The Sentinel
Forged by Pyrmethus: Dynamic Precision, Wallet-Aware Sizing, and EMA Confluence.
"""

import json
import logging
import os
import subprocess
import sys
import time
from datetime import timezone
from decimal import Decimal
from decimal import getcontext
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import ClassVar

# --- Ritual Dependencies ---
try:
    from pybit.unified_trading import HTTP as PybitHTTP
    PYBIT_AVAILABLE = True
except ImportError:
    PYBIT_AVAILABLE = False

import pandas as pd
from colorama import Fore
from colorama import Style
from colorama import init
from dotenv import load_dotenv

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
NEON_WHITE = Fore.WHITE
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

# --- Alert Weaver ---
class AlertSystem:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.has_api = self._check_api()
    def _check_api(self) -> bool:
        try: return subprocess.run(['which', 'termux-toast'], check=False, capture_output=True).returncode == 0
        except: return False
    def send_alert(self, message: str, level: str = "INFO"):
        color = NEON_GREEN if level == "INFO" else NEON_RED
        self.logger.info(f"{color}🔮 ALERT: {message}{RESET}")
        if self.has_api: subprocess.run(['termux-toast', f"WhaleBot: {message}"], check=False)

# --- Bybit V5 Mastery Client ---
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

    def api_call(self, func_name: str, **kwargs):
        """A wrapper ward to protect against API flickers."""
        for i in range(3):
            try:
                method = getattr(self.session, func_name)
                res = method(**kwargs)
                if res['retCode'] == 0: return res
                self.logger.error(f"Bybit Error: {res['retMsg']} (Code: {res['retCode']})")
                break
            except Exception as e:
                self.logger.warning(f"Ether flicker (Attempt {i+1}): {e}")
                time.sleep(2)
        return None

    def fetch_klines(self, symbol: str, interval: str, limit: int = 200):
        res = self.api_call("get_kline", category="linear", symbol=symbol, interval=interval, limit=limit)
        if res:
            df = pd.DataFrame(res['result']['list'], columns=['time', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
            df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].apply(pd.to_numeric)
            df['time'] = pd.to_datetime(df['time'].astype(int), unit='ms')
            return df.sort_values('time').reset_index(drop=True)
        return None

# --- Position & Strategy Sentinel ---
class PositionManager:
    def __init__(self, config: dict, logger: logging.Logger, client: PybitTradingClient):
        self.config = config
        self.logger = logger
        self.client = client
        self.price_prec = 2
        self.qty_prec = 3
        self.min_qty = 0.001
        self._divine_instrument_specs()

    def _divine_instrument_specs(self):
        """Learn the rules of the market from the exchange itself."""
        res = self.client.api_call("get_instruments_info", category="linear", symbol=self.config["symbol"])
        if res:
            specs = res['result']['list'][0]
            self.price_prec = abs(Decimal(specs['priceFilter']['tickSize']).normalize().as_tuple().exponent)
            self.qty_prec = abs(Decimal(specs['lotSizeFilter']['qtyStep']).normalize().as_tuple().exponent)
            self.min_qty = float(specs['lotSizeFilter']['minOrderQty'])
            self.logger.info(f"{NEON_BLUE}# Market Wisdom: Price Prec [{self.price_prec}] | Qty Prec [{self.qty_prec}]{RESET}")

    def _round(self, val: float, prec: int) -> str:
        return "{: .{}f}".format(val, prec).strip()

    def calculate_qty(self, price: float, sl_price: float) -> str:
        """Calculate quantity based on wallet risk and SL distance."""
        res = self.client.api_call("get_wallet_balance", accountType="UNIFIED", coin="USDT")
        if not res: return self._round(self.min_qty, self.qty_prec)

        balance = float(res['result']['list'][0]['coin'][0]['walletBalance'])
        risk_per_trade = float(self.config["trade_management"]["risk_per_trade_percent"]) * balance
        sl_dist = abs(price - sl_price)

        if sl_dist == 0: return self._round(self.min_qty, self.qty_prec)

        qty = risk_per_trade / sl_dist
        return self._round(max(qty, self.min_qty), self.qty_prec)

    def open_position(self, side: str, price: float, atr: float):
        sl_mult = float(self.config["trade_management"]["stop_loss_atr_multiple"])
        sl_price = price - (atr * sl_mult) if side == "BUY" else price + (atr * sl_mult)
        qty = self.calculate_qty(price, sl_price)

        self.logger.info(f"{NEON_PURPLE}# Executing {side} Ritual | Qty: {qty} | SL: {sl_price:.2f}{RESET}")

        res = self.client.api_call("place_order",
            category="linear", symbol=self.config["symbol"], side=side.capitalize(),
            orderType="Market", qty=qty, stopLoss=self._round(sl_price, self.price_prec),
            tpTriggerBy="LastPrice", slTriggerBy="LastPrice"
        )
        if res:
            self.logger.info(f"{NEON_GREEN}# Ritual Triumphant! OrderID: {res['result']['orderId']}{RESET}")

# --- The Sentinel Orchestrator ---
class WhaleBot:
    def __init__(self, config: dict):
        self.config = config
        self.logger = setup_logger("whale_bot")
        self.alerts = AlertSystem(self.logger)
        self.client = PybitTradingClient(config, self.logger)
        self.pm = PositionManager(config, self.logger, self.client)
        self.is_running = True

    def analyze(self, df: pd.DataFrame):
        # Indicators
        df['rsi'] = self.calculate_rsi(df)
        df['ema'] = df['close'].rolling(window=50).mean()
        df['atr'] = self.calculate_atr(df)

        last = df.iloc[-1]
        self.logger.info(f"{NEON_YELLOW}🔍 Divination: {last['close']:.2f} | RSI: {last['rsi']:.2f} | EMA: {last['ema']:.2f}{RESET}")

        # Strategy: RSI + EMA Trend Confirmation
        if last['rsi'] < 35 and last['close'] > last['ema']:
            return "BUY", last['close'], last['atr']
        if last['rsi'] > 65 and last['close'] < last['ema']:
            return "SELL", last['close'], last['atr']
        return "HOLD", 0, 0

    def calculate_atr(self, df):
        tr = pd.concat([df['high']-df['low'], (df['high']-df['close'].shift()).abs(), (df['low']-df['close'].shift()).abs()], axis=1).max(axis=1)
        return tr.rolling(14).mean()

    def calculate_rsi(self, df, period=14):
        delta = df['close'].diff()
        up = delta.clip(lower=0); down = -1 * delta.clip(upper=0)
        ema_up = up.ewm(com=period-1, adjust=False).mean()
        ema_down = down.ewm(com=period-1, adjust=False).mean()
        return 100 - (100 / (1 + (ema_up / ema_down)))

    def start(self):
        self.logger.info(f"{NEON_WHITE}# Sentinel active. Monitoring {self.config['symbol']}...{RESET}")
        while self.is_running:
            try:
                df = self.client.fetch_klines(self.config["symbol"], self.config["interval"])
                if df is not None:
                    signal, price, atr = self.analyze(df)
                    if signal != "HOLD":
                        self.pm.open_position(signal, price, atr)
                        self.alerts.send_alert(f"Ritual: {signal} @ {price}")
                time.sleep(self.config["loop_delay"])
            except KeyboardInterrupt: self.is_running = False
            except Exception as e: self.logger.error(f"Chaos: {e}"); time.sleep(5)

# --- Configuration Weaver (Deep Merge Fix) ---
def load_config(filepath: str, logger: logging.Logger) -> dict:
    default_config = {
        "symbol": "BTCUSDT", "interval": "15", "loop_delay": 15,
        "trade_management": {"price_precision": 2, "risk_per_trade_percent": 0.01, "stop_loss_atr_multiple": 1.5, "take_profit_atr_multiple": 2.0},
        "execution": {"testnet": True, "use_pybit": True, "tp_scheme": {"mode": "atr_multiples", "targets": [{"name": "TP1", "atr_multiple": 1.0, "size_pct": 0.4}]}}
    }
    if not Path(filepath).exists():
        with open(filepath, 'w') as f: json.dump(default_config, f, indent=4)
        return default_config
    with open(filepath) as f:
        existing = json.load(f)
        # Repair missing sections
        for k, v in default_config.items():
            if k not in existing: existing[k] = v
            elif isinstance(v, dict):
                for sk, sv in v.items():
                    if sk not in existing[k]: existing[k][sk] = sv
        return existing

def main():
    logger = setup_logger("whale_main")
    config = load_config(CONFIG_FILE, logger)
    if not API_KEY or not API_SECRET:
        logger.critical(f"{NEON_RED}# Fatal: API keys missing in .env!{RESET}"); sys.exit(1)
    if not PYBIT_AVAILABLE:
        logger.critical(f"{NEON_RED}# Fatal: pybit library missing!{RESET}"); sys.exit(1)

    bot = WhaleBot(config)
    bot.start()

if __name__ == "__main__":
    try: main()
    except Exception as e: setup_logger("fatal").critical(f"Abyssal Collapse: {e}", exc_info=True)
