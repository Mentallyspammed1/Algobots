#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Pyrmethus's Ascended Neon Bybit Trading Bot (Finalized with all enchantments)

This ultimate incantation of the Supertrend strategy for Bybit V5 API is fortified with
the wisdom of Pyrmethus. It features luminous neon colors, flexible JSON configurations,
and advanced risk-management enchantments.

Key Upgrades and Fixes:
-   Simplified Supertrend: The custom Ehlers Supertrend has been replaced with a more
    robust and widely-tested pandas_ta.supertrend implementation. All of the original
    RSI, ATR, and ADX filters remain to maintain the strategy's core logic.
-   Atomic Order Placement: The `_place_order` function now uses a single, atomic
    API call to place the market order with its stop-loss and take-profit attached.
    This is the safest and most reliable method to ensure TP/SL are active upon fill.
-   Precise Position Closure: `_close_position` now correctly queries the API for
    the actual position size, ensuring accurate closure.
-   Enhanced Backtesting: The backtesting engine has been refined for improved PnL
    calculation accuracy, including fees and slippage, and now correctly handles
    trailing stop-loss updates.
-   State Persistence: The bot state is now handled more robustly, ensuring it can
    recover gracefully from interruptions.
-   API Health Monitoring: The circuit breaker logic is now part of the main loop,
    ensuring continuous monitoring of the bot's health.

For Termux: `pkg install python python-matplotlib libssl termux-api; pip install pybit pandas pandas_ta colorama matplotlib ta-lib cryptography`
Testnet is default—for live trading, set 'testnet': false in your config.
"""

import json
import os
import time
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, InvalidOperation
import pandas as pd
import pandas_ta as ta
import numpy as np
from pybit.unified_trading import HTTP
from colorama import init, Fore, Style
import logging
import matplotlib.pyplot as plt
from typing import Dict, List, Optional, Any
from cryptography.fernet import Fernet
import getpass

# --- Initialization ---
init(autoreset=True)

# Neon Color Palette
NEON_SUCCESS, NEON_INFO, NEON_WARNING, NEON_ERROR, NEON_SIGNAL, NEON_DEBUG, NEON_POSITION, NEON_RESET = (
    Fore.LIGHTGREEN_EX, Fore.LIGHTCYAN_EX, Fore.LIGHTYELLOW_EX, Fore.LIGHTRED_EX,
    Fore.LIGHTMAGENTA_EX + Style.BRIGHT, Fore.LIGHTBLUE_EX, Fore.LIGHTWHITE_EX, Style.RESET_ALL
)

# --- Constants ---
CONFIG_FILE = "bot_config.json"
LOG_FILE = "trade_log.log"
STATE_FILE = "bot_state.json"
CREDS_FILE = "authcreds.json"
SMS_LOG_FILE = "sms_log.log"
DEFAULT_QTY_STEP = Decimal('0.001')
DEFAULT_PRICE_PRECISION = Decimal('0.01')
DEFAULT_MIN_ORDER_QTY = Decimal('0.001')
MAX_SMS_LENGTH = 160
KLINE_CACHE_SIZE = 200
API_MAX_RETRIES = 3
API_RETRY_DELAY = 2
SMS_COOLDOWN = 300  # 5 minutes
HEALTH_CHECK_INTERVAL = 1800  # 30 minutes
CIRCUIT_BREAKER_THRESHOLD = 5
CIRCUIT_BREAKER_PAUSE = 900  # 15 minutes
TAKER_FEE = Decimal('0.00075')
SLIPPAGE = Decimal('0.001')
ENCRYPTION_KEY_FILE = "encryption_key.key"

# --- Logging Setup ---
def setup_logging():
    """Configures logging to file and console."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    if not any(isinstance(handler, logging.FileHandler) for handler in logging.getLogger().handlers):
        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(file_handler)
    if not any(isinstance(handler, logging.FileHandler) and handler.baseFilename.endswith(SMS_LOG_FILE) for handler in logging.getLogger().handlers):
        sms_handler = logging.FileHandler(SMS_LOG_FILE)
        sms_handler.setLevel(logging.INFO)
        sms_handler.setFormatter(logging.Formatter('%(asctime)s - SMS - %(message)s'))
        logging.getLogger().addHandler(sms_handler)

# --- Encryption for Credentials ---
def _generate_encryption_key():
    """Generates and saves an encryption key."""
    key = Fernet.generate_key()
    with open(ENCRYPTION_KEY_FILE, 'wb') as f:
        f.write(key)
    _log_and_print("info", "Encryption key generated and saved.", NEON_SUCCESS)

def _load_encryption_key() -> bytes:
    """Loads encryption key or generates a new one."""
    if os.path.exists(ENCRYPTION_KEY_FILE):
        with open(ENCRYPTION_KEY_FILE, 'rb') as f:
            return f.read()
    _generate_encryption_key()
    return _load_encryption_key()

def _encrypt_credentials(api_key: str, api_secret: str) -> Dict:
    """Encrypts API credentials."""
    fernet = Fernet(_load_encryption_key())
    return {
        'api_key': fernet.encrypt(api_key.encode()).decode(),
        'api_secret': fernet.encrypt(api_secret.encode()).decode()
    }

def _decrypt_credentials(creds: Dict) -> tuple[str, str]:
    """Decrypts API credentials."""
    try:
        fernet = Fernet(_load_encryption_key())
        return (
            fernet.decrypt(creds['api_key'].encode()).decode(),
            fernet.decrypt(creds['api_secret'].encode()).decode()
        )
    except Exception as e:
        _log_and_print("error", f"Failed to decrypt credentials: {e}", NEON_ERROR)
        sys.exit(1)

# --- Helper Functions ---
def _log_and_print(level: str, message: str, color: str):
    """Logs and prints with neon colors."""
    print(f"{color}{message}{NEON_RESET}")
    getattr(logging, level)(message)

def _send_sms(subject: str, body: str, config: Dict, state: Dict, priority: str = 'normal'):
    """Sends SMS with priority-based rate limiting."""
    if not config.get("sms_notifications", False) or not config.get("sms_recipient"):
        return
    sms_state = state.setdefault('sms_timestamps', {})
    event_key = f"{subject}_{priority}"
    last_sent = sms_state.get(event_key, 0)
    current_time = int(time.time())
    if priority != 'critical' and current_time - last_sent < SMS_COOLDOWN:
        _log_and_print("debug", f"SMS for '{event_key}' skipped due to cooldown.", NEON_DEBUG)
        return
    try:
        recipient = config["sms_recipient"]
        message = f"{subject}\n{body}"[:MAX_SMS_LENGTH]
        subprocess.run(["termux-sms-send", "-n", recipient, message], check=True, capture_output=True)
        sms_state[event_key] = current_time
        _log_and_print("info", f"SMS sent to {recipient}: {subject}", NEON_SUCCESS)
        logging.info(f"SMS Sent: {subject} | Body: {body[:50]}...")
    except FileNotFoundError:
        _log_and_print("error", "Termux-sms-send not found. Install termux-api.", NEON_ERROR)
    except Exception as e:
        _log_and_print("error", f"SMS failed: {e}", NEON_ERROR)
        logging.error(f"SMS Failed: {subject} | Error: {e}")

def _validate_config(config: Dict) -> bool:
    """Validates configuration with extended checks."""
    required_keys = ['symbol', 'interval', 'leverage', 'risk_pct', 'max_position_size', 'max_open_trades']
    numeric_keys = ['leverage', 'risk_pct', 'max_position_size', 'stop_loss_pct', 'take_profit_pct', 'trailing_stop_pct',
                    'super_trend_length', 'super_trend_multiplier', 'rsi_length', 'rsi_overbought', 'rsi_oversold',
                    'adx_length', 'adx_threshold', 'atr_length', 'atr_multiplier', 'close_delay', 'risk_reward_ratio']
    try:
        for key in required_keys:
            if key not in config or config[key] is None:
                _log_and_print("error", f"Missing configuration key: {key}", NEON_ERROR)
                return False
        for key in numeric_keys:
            if key in config and (not isinstance(config[key], (int, float)) or config[key] <= 0):
                _log_and_print("error", f"Invalid {key}: must be positive number", NEON_ERROR)
                return False
        if config.get('sms_notifications') and not config.get('sms_recipient'):
            _log_and_print("error", "SMS enabled but no recipient specified.", NEON_ERROR)
            return False
        if not isinstance(config['symbol'], str) or not config['symbol'].endswith('USDT'):
            _log_and_print("error", f"Invalid symbol: {config['symbol']}. Must be a USDT pair.", NEON_ERROR)
            return False
        valid_intervals = ['1', '3', '5', '15', '30', '60', '120', '240', '360', '720', 'D', 'W', 'M']
        if str(config['interval']) not in valid_intervals:
            _log_and_print("error", f"Invalid interval: {config['interval']}. Must be one of {valid_intervals}.", NEON_ERROR)
            return False
        if config['backtest']:
            try:
                datetime.fromisoformat(config['backtest_start'])
                datetime.fromisoformat(config['backtest_end'])
            except ValueError:
                _log_and_print("error", "Invalid backtest date format. Use YYYY-MM-DD.", NEON_ERROR)
                return False
        if 'trailing_stop_pct' in config and config['trailing_stop_pct'] > config['stop_loss_pct']:
            _log_and_print("warning", "Trailing stop % is larger than stop loss %. This may result in unexpected behavior.", NEON_WARNING)
        return True
    except Exception as e:
        _log_and_print("error", f"Config validation failed: {e}", NEON_ERROR)
        return False

def _setup_config_wizard() -> Dict:
    """Interactive configuration setup for first-time use."""
    _log_and_print("info", "No config file found. Initiating configuration wizard...", NEON_INFO)
    try:
        config = {
            "symbol": input(f"{NEON_INFO}Enter trading symbol (e.g., BTCUSDT): {NEON_RESET}").strip().upper(),
            "interval": input(f"{NEON_INFO}Enter kline interval (e.g., 60 for 1h): {NEON_RESET}").strip(),
            "leverage": int(input(f"{NEON_INFO}Enter leverage (e.g., 10): {NEON_RESET}")),
            "risk_pct": float(input(f"{NEON_INFO}Enter risk per trade (e.g., 0.01 for 1%): {NEON_RESET}")),
            "max_position_size": float(input(f"{NEON_INFO}Enter max position size (e.g., 0.01): {NEON_RESET}")),
            "max_open_trades": int(input(f"{NEON_INFO}Enter max open trades (e.g., 1): {NEON_RESET}")),
            "stop_loss_pct": float(input(f"{NEON_INFO}Enter stop loss % (e.g., 0.02): {NEON_RESET}")),
            "take_profit_pct": float(input(f"{NEON_INFO}Enter take profit % (e.g., 0.05): {NEON_RESET}")),
            "trailing_stop_pct": float(input(f"{NEON_INFO}Enter trailing stop % (e.g., 0.01): {NEON_RESET}")),
            "risk_reward_ratio": float(input(f"{NEON_INFO}Enter risk/reward ratio (e.g., 2.0): {NEON_RESET}")),
            "sizing_mode": input(f"{NEON_INFO}Enter sizing mode (atr or percentage): {NEON_RESET}").strip().lower(),
            "super_trend_length": int(input(f"{NEON_INFO}Enter Supertrend length (e.g., 10): {NEON_RESET}")),
            "super_trend_multiplier": float(input(f"{NEON_INFO}Enter Supertrend multiplier (e.g., 2.0): {NEON_RESET}")),
            "rsi_length": int(input(f"{NEON_INFO}Enter RSI length (e.g., 14): {NEON_RESET}")),
            "rsi_overbought": float(input(f"{NEON_INFO}Enter RSI overbought threshold (e.g., 70): {NEON_RESET}")),
            "rsi_oversold": float(input(f"{NEON_INFO}Enter RSI oversold threshold (e.g., 30): {NEON_RESET}")),
            "adx_length": int(input(f"{NEON_INFO}Enter ADX length (e.g., 14): {NEON_RESET}")),
            "adx_threshold": float(input(f"{NEON_INFO}Enter ADX threshold (e.g., 25): {NEON_RESET}")),
            "atr_length": int(input(f"{NEON_INFO}Enter ATR length (e.g., 14): {NEON_RESET}")),
            "atr_multiplier": float(input(f"{NEON_INFO}Enter ATR multiplier (e.g., 2.0): {NEON_RESET}")),
            "close_delay": int(input(f"{NEON_INFO}Enter close delay seconds (e.g., 5): {NEON_RESET}")),
            "testnet": input(f"{NEON_INFO}Use testnet? (yes/no): {NEON_RESET}").strip().lower() == 'yes',
            "backtest": input(f"{NEON_INFO}Run backtest? (yes/no): {NEON_RESET}").strip().lower() == 'yes',
            "backtest_start": input(f"{NEON_INFO}Enter backtest start date (YYYY-MM-DD): {NEON_RESET}").strip(),
            "backtest_end": input(f"{NEON_INFO}Enter backtest end date (YYYY-MM-DD): {NEON_RESET}").strip(),
            "plot_enabled": input(f"{NEON_INFO}Enable backtest plots? (yes/no): {NEON_RESET}").strip().lower() == 'yes',
            "sms_notifications": input(f"{NEON_INFO}Enable SMS notifications? (yes/no): {NEON_RESET}").strip().lower() == 'yes',
            "sms_recipient": input(f"{NEON_INFO}Enter SMS recipient number: {NEON_RESET}").strip(),
            "display_mode": input(f"{NEON_INFO}Display mode (compact/detailed): {NEON_RESET}").strip().lower(),
        }
        config.update({
            "min_order_qty": str(DEFAULT_MIN_ORDER_QTY),
            "qty_step": str(DEFAULT_QTY_STEP),
            "price_precision": str(DEFAULT_PRICE_PRECISION)
        })
        if _validate_config(config):
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
            _log_and_print("info", f"Configuration saved to {CONFIG_FILE}.", NEON_SUCCESS)
            return {k: Decimal(v) if isinstance(v, str) and k in ['min_order_qty', 'qty_step', 'price_precision'] else v for k, v in config.items()}
    except Exception as e:
        _log_and_print("error", f"Config wizard failed: {e}. Exiting.", NEON_ERROR)
        sys.exit(1)
    _log_and_print("error", "Invalid configuration. Exiting.", NEON_ERROR)
    sys.exit(1)

def _load_config() -> Dict:
    """Loads and validates configuration."""
    defaults = {
        "symbol": "BTCUSDT", "category": "linear", "interval": "60", "leverage": 10,
        "super_trend_length": 10, "super_trend_multiplier": 3.0,
        "stop_loss_pct": 0.02, "take_profit_pct": 0.05, "trailing_stop_pct": 0.01,
        "risk_reward_ratio": 2.5,
        "rsi_length": 14, "rsi_overbought": 70, "rsi_oversold": 30,
        "adx_length": 14, "adx_threshold": 25,
        "risk_pct": 0.01, "max_open_trades": 1, "max_position_size": 0.01,
        "sizing_mode": "atr", "atr_length": 14, "atr_multiplier": 2.0,
        "close_delay": 5, "testnet": True, "backtest": False,
        "backtest_start": "2024-01-01", "backtest_end": "2024-08-01", "plot_enabled": False,
        "sms_notifications": False, "sms_recipient": "", "display_mode": "detailed",
        "min_order_qty": str(DEFAULT_MIN_ORDER_QTY), "qty_step": str(DEFAULT_QTY_STEP), "price_precision": str(DEFAULT_PRICE_PRECISION)
    }
    if not os.path.exists(CONFIG_FILE):
        return _setup_config_wizard()
    try:
        with open(CONFIG_FILE, 'r') as f:
            config_from_file = json.load(f)
        defaults.update(config_from_file)
        if not _validate_config(defaults):
            _log_and_print("error", "Invalid configuration. Run wizard? (yes/no): ", NEON_ERROR)
            if input().strip().lower() == 'yes':
                return _setup_config_wizard()
            sys.exit(1)
        _log_and_print("info", f"Configuration summoned from {CONFIG_FILE}.", NEON_SUCCESS)
        # Convert Decimal values from strings
        for key in ['min_order_qty', 'qty_step', 'price_precision']:
            if key in defaults and isinstance(defaults[key], str):
                defaults[key] = Decimal(defaults[key])
        return defaults
    except Exception as e:
        _log_and_print("error", f"Config load failed: {e}. Starting wizard.", NEON_ERROR)
        return _setup_config_wizard()

def _load_api_creds() -> tuple[str, str]:
    """Loads and decrypts API credentials."""
    if not os.path.exists(CREDS_FILE):
        _log_and_print("info", "No credentials file found. Enter API credentials:", NEON_INFO)
        api_key = getpass.getpass(f"{NEON_INFO}Enter Bybit API Key: {NEON_RESET}")
        api_secret = getpass.getpass(f"{NEON_INFO}Enter Bybit API Secret: {NEON_RESET}")
        creds = _encrypt_credentials(api_key, api_secret)
        with open(CREDS_FILE, 'w') as f:
            json.dump(creds, f, indent=2)
        _log_and_print("info", f"Credentials saved to {CREDS_FILE}.", NEON_SUCCESS)
    try:
        with open(CREDS_FILE) as f:
            creds = json.load(f)
        return _decrypt_credentials(creds)
    except Exception as e:
        _log_and_print("error", f"Error loading credentials: {e}", NEON_ERROR)
        _send_sms("Bybit Bot Critical Error", "API credentials not found.", _load_config(), _load_state(), priority='critical')
        sys.exit(1)

def _validate_api_permissions(session: HTTP, config: Dict) -> bool:
    """Validates API key permissions."""
    try:
        response = session.get_account_info()
        if response['retCode'] == 0:
            session.set_leverage(category=config['category'], symbol=config['symbol'], buyLeverage=str(config['leverage']), sellLeverage=str(config['leverage']))
            _log_and_print("info", "API permissions validated.", NEON_SUCCESS)
            return True
        _log_and_print("error", f"API permission check failed: {response}", NEON_ERROR)
        return False
    except Exception as e:
        _log_and_print("error", f"API permission validation failed: {e}", NEON_ERROR)
        return False

def _initialize_session(config: Dict) -> Optional[HTTP]:
    """Initializes Bybit API session."""
    try:
        api_key, api_secret = _load_api_creds()
        session = HTTP(testnet=config['testnet'], api_key=api_key, api_secret=api_secret)
        if not _validate_api_permissions(session, config):
            _send_sms("Bybit Bot Connection Error", "API permissions invalid.", config, _load_state(), priority='critical')
            return None
        _log_and_print("info", f"Connected to Bybit {'testnet' if config['testnet'] else 'mainnet'}.", NEON_SUCCESS)
        return session
    except Exception as e:
        _log_and_print("error", f"Session initialization failed: {e}", NEON_ERROR)
        _send_sms("Bybit Bot Connection Error", f"Session failed: {e}", config, _load_state(), priority='critical')
        return None

def _fetch_instrument_rules(session: HTTP, config: Dict):
    """Fetches instrument trading rules."""
    try:
        response = session.get_instruments_info(category=config['category'], symbol=config['symbol'])
        if response['retCode'] == 0 and response['result']['list']:
            info = response['result']['list'][0]
            config['min_order_qty'] = Decimal(info['lotSizeFilter']['minOrderQty']).normalize()
            config['qty_step'] = Decimal(info['lotSizeFilter']['qtyStep']).normalize()
            config['price_precision'] = Decimal(info['priceFilter']['tickSize']).normalize()
            _log_and_print("info", f"Instrument rules: Min Qty: {config['min_order_qty']}, Step: {config['qty_step']}, Precision: {config['price_precision']}", NEON_SUCCESS)
        else:
            raise ValueError("No instrument info.")
    except Exception as e:
        _log_and_print("error", f"Instrument rules fetch failed: {e}. Using defaults.", NEON_ERROR)
        config['min_order_qty'] = DEFAULT_MIN_ORDER_QTY
        config['qty_step'] = DEFAULT_QTY_STEP
        config['price_precision'] = DEFAULT_PRICE_PRECISION

def _fetch_kline_data(session: HTTP, config: Dict, last_timestamp: Optional[int] = None) -> pd.DataFrame:
    """Fetches kline data with timestamp continuity."""
    df_list = []
    limit = 1000
    interval_ms = int(config['interval']) * 60 * 1000
    if config['backtest']:
        start_dt = datetime.fromisoformat(config['backtest_start']).replace(tzinfo=timezone.utc)
        end_dt = datetime.fromisoformat(config['backtest_end']).replace(tzinfo=timezone.utc)
        current_time_ms = int(start_dt.timestamp() * 1000)
        end_time_ms = int(end_dt.timestamp() * 1000)
    else:
        now = datetime.now(timezone.utc)
        lookback_ms = interval_ms * KLINE_CACHE_SIZE
        current_time_ms = last_timestamp or int((now - timedelta(milliseconds=lookback_ms)).timestamp() * 1000)
        end_time_ms = None
    last_received_ts = None
    for attempt in range(API_MAX_RETRIES):
        try:
            params = {"category": config['category'], "symbol": config['symbol'], "interval": config['interval'], "limit": limit}
            if current_time_ms:
                params["start"] = current_time_ms
            if end_time_ms:
                params["end"] = end_time_ms
            response = session.get_kline(**params)
            if response['retCode'] == 0 and response['result']['list']:
                data = response['result']['list']
                df = pd.DataFrame(data, columns=['startTime', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
                df[['open', 'high', 'low', 'close', 'volume', 'turnover']] = df[['open', 'high', 'low', 'close', 'volume', 'turnover']].apply(pd.to_numeric, errors='coerce')
                df['startTime'] = pd.to_datetime(df['startTime'], unit='ms', utc=True)
                df = df.sort_values('startTime').reset_index(drop=True)
                df_list.append(df)
                last_received_ts = df['startTime'].iloc[-1].timestamp() * 1000
                current_time_ms = int(last_received_ts) + interval_ms
                if (config['backtest'] and (current_time_ms >= end_time_ms or len(data) < limit)) or (not config['backtest'] and len(data) < limit):
                    break
            else:
                _log_and_print("error", f"Kline fetch failed: {response}", NEON_ERROR)
                break
        except Exception as e:
            _log_and_print("error", f"Kline fetch attempt {attempt + 1} failed: {e}", NEON_ERROR)
            if attempt < API_MAX_RETRIES - 1:
                time.sleep(API_RETRY_DELAY ** (attempt + 1))
            else:
                break
    return pd.concat(df_list, ignore_index=True)[['startTime', 'open', 'high', 'low', 'close', 'volume']] if df_list else pd.DataFrame()

def _get_balance(session: HTTP, config: Dict) -> Decimal:
    """Fetches USDT balance."""
    try:
        response = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
        if response['retCode'] == 0 and response['result']['list']:
            return Decimal(response['result']['list'][0]['totalWalletBalance'])
        _log_and_print("error", f"Balance fetch failed: {response}", NEON_ERROR)
        return Decimal('0')
    except Exception as e:
        _log_and_print("error", f"Balance fetch failed: {e}", NEON_ERROR)
        return Decimal('0')

def _place_order(session: HTTP, side: str, qty: Decimal, sl_price: Decimal, tp_price: Decimal, config: Dict, state: Dict):
    """Places a market order with retry logic and attached TP/SL."""
    for attempt in range(API_MAX_RETRIES):
        try:
            order_qty = qty
            if attempt > 0:
                order_qty *= Decimal('0.9')
                order_qty = (order_qty // config['qty_step']) * config['qty_step']
            if order_qty < config['min_order_qty']:
                _log_and_print("error", f"Quantity {order_qty} below minimum {config['min_order_qty']}.", NEON_ERROR)
                return None
            order_params = {
                "category": config['category'], "symbol": config['symbol'], "side": side,
                "orderType": "Market", "qty": f"{order_qty:.8f}", "takeProfit": f"{tp_price:.8f}",
                "stopLoss": f"{sl_price:.8f}", "tpslMode": "Full"
            }
            response = session.place_order(**order_params)
            if response['retCode'] == 0:
                order_id = response['result']['orderId']
                _log_and_print("info", f"{side} order placed: Qty: {order_qty}, SL: {sl_price}, TP: {tp_price}, ID: {order_id}", NEON_SUCCESS)
                _send_sms(f"Bybit Bot: {side} Order", f"Qty: {order_qty}\nSL: {sl_price}\nTP: {tp_price}", config, state)
                return {'order_id': order_id, 'qty': order_qty, 'sl': sl_price, 'tp': tp_price}
            _log_and_print("error", f"Order failed: {response.get('retMsg', 'Unknown')}", NEON_ERROR)
            if attempt < API_MAX_RETRIES - 1:
                time.sleep(API_RETRY_DELAY ** (attempt + 1))
        except Exception as e:
            _log_and_print("error", f"Order attempt {attempt + 1} failed: {e}", NEON_ERROR)
            if attempt < API_MAX_RETRIES - 1:
                time.sleep(API_RETRY_DELAY ** (attempt + 1))
            else:
                _send_sms(f"Bybit Bot Order Failed", f"Side: {side}\nError: {e}", config, state, priority='critical')
    return None

def _close_position(session: HTTP, position: Dict, config: Dict, state: Dict):
    """Closes a position."""
    try:
        side_to_close = "Sell" if position['side'] == 'Buy' else "Buy"
        qty = Decimal(position['size']).quantize(config['qty_step'], rounding=ROUND_DOWN)
        if qty <= 0:
            _log_and_print("warning", f"Zero quantity to close: {position}", NEON_WARNING)
            return
        response = session.place_order(
            category=config['category'], symbol=config['symbol'], side=side_to_close,
            orderType="Market", qty=f"{qty:.8f}", reduceOnly=True
        )
        if response['retCode'] == 0:
            order_id = response['result']['orderId']
            _log_and_print("info", f"Closed {position['side']} position: Qty: {qty}, ID: {order_id}", NEON_SUCCESS)
            _send_sms(f"Bybit Bot: Position Closed", f"Side: {position['side']}\nQty: {qty}", config, state)
        else:
            _log_and_print("error", f"Close failed: {response.get('retMsg', 'Unknown')}", NEON_ERROR)
            _send_sms(f"Bybit Bot Close Failed", f"Side: {position['side']}\nError: {response.get('retMsg', 'Unknown')}", config, state, priority='critical')
    except Exception as e:
        _log_and_print("error", f"Close failed: {e}", NEON_ERROR)
        _send_sms(f"Bybit Bot Close Failed", f"Side: {position['side']}\nError: {e}", config, state, priority='critical')

def _get_open_positions(session: HTTP, config: Dict) -> List[Dict]:
    """Fetches open positions."""
    try:
        response = session.get_positions(category=config['category'], symbol=config['symbol'])
        if response['retCode'] == 0 and response['result']['list']:
            return [p for p in response['result']['list'] if Decimal(p.get('size', '0')) > 0]
        return []
    except Exception as e:
        _log_and_print("error", f"Position fetch failed: {e}", NEON_ERROR)
        return []

def _save_state(state: Dict):
    """Saves bot state."""
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2, default=str)
        _log_and_print("info", f"State saved to {STATE_FILE}.", NEON_SUCCESS)
    except Exception as e:
        _log_and_print("error", f"State save failed: {e}", NEON_ERROR)

def _load_state() -> Dict:
    """Loads bot state."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
            if 'last_timestamp' in state and state['last_timestamp'] is not None:
                state['last_timestamp'] = int(state['last_timestamp'])
            for key in ['positions', 'backtest_trades']:
                if key in state and isinstance(state[key], list):
                    for item in state[key]:
                        for d_key in ['qty', 'entry_price', 'sl', 'tp', 'size', 'stopLoss', 'pnl', 'exit_price']:
                            if d_key in item and isinstance(item[d_key], str):
                                try: item[d_key] = Decimal(item[d_key])
                                except InvalidOperation: pass
            return state
        except Exception as e:
            _log_and_print("error", f"State load failed: {e}. Using empty state.", NEON_ERROR)
    return {'last_timestamp': None, 'positions': [], 'sms_timestamps': {}, 'last_heartbeat': 0, 'backtest_trades': []}

def _check_consistency(session: HTTP, config: Dict, state: Dict) -> bool:
    """Checks balance and position consistency."""
    try:
        balance = _get_balance(session, config)
        positions = _get_open_positions(session, config)
        if len(positions) != len(state.get('positions', [])):
            _log_and_print("warning", f"Position mismatch: API reports {len(positions)}, state has {len(state.get('positions', []))}", NEON_WARNING)
            state['positions'] = [{'side': p['side'], 'qty': Decimal(p['size']), 'entry_price': Decimal(p['entryPrice']),
                                   'sl': Decimal(p.get('stopLoss', '0')), 'tp': Decimal(p.get('takeProfit', '0')),
                                   'symbol': p['symbol'], 'stopLoss': p.get('stopLoss', '0')} for p in positions]
            _save_state(state)
        if balance <= 0:
            _log_and_print("warning", "Zero or negative balance detected.", NEON_WARNING)
            _send_sms("Bybit Bot Warning", "Zero or negative balance detected.", config, state, priority='critical')
            return False
        return True
    except Exception as e:
        _log_and_print("error", f"Consistency check failed: {e}", NEON_ERROR)
        return False

def _send_heartbeat(config: Dict, state: Dict):
    """Sends periodic heartbeat SMS."""
    current_time = int(time.time())
    if current_time - state['last_heartbeat'] >= HEALTH_CHECK_INTERVAL:
        _send_sms("Bybit Bot Heartbeat", f"Bot running for {config['symbol']} on {config['interval']}m interval.", config, state)
        state['last_heartbeat'] = current_time
        _save_state(state)

def _run_monte_carlo(equity_curve: pd.DataFrame, num_simulations: int = 100) -> float:
    """Runs Monte Carlo simulation for robustness."""
    try:
        returns = equity_curve['Equity'].pct_change().dropna()
        if returns.empty or returns.std() == 0:
            return 0.0
        mean_return = returns.mean()
        std_return = returns.std()
        simulations = []
        for _ in range(num_simulations):
            sim_returns = np.random.normal(mean_return, std_return, len(equity_curve))
            sim_equity = [equity_curve['Equity'].iloc[0]]
            for ret in sim_returns:
                sim_equity.append(sim_equity[-1] * (1 + ret))
            simulations.append(sim_equity[-1])
        return float(np.mean(simulations) / equity_curve['Equity'].iloc[0] - 1)
    except Exception as e:
        _log_and_print("error", f"Monte Carlo simulation failed: {e}", NEON_ERROR)
        return 0.0

def _plot_backtest_results(df: pd.DataFrame, equity_curve: pd.DataFrame, config: Dict, metrics: Dict):
    """Plots backtest results."""
    if not config.get('plot_enabled', False):
        return
    try:
        plt.style.use('dark_background')
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
        fig.suptitle(f"Backtest: {config['symbol']} ({config['interval']}m) | Final Equity: {equity_curve['Equity'].iloc[-1]:.2f} | Sharpe: {metrics['sharpe_ratio']:.2f} | Max DD: {metrics['max_drawdown']:.2%}", color=NEON_INFO, fontsize=16)
        
        ax1.plot(df['startTime'], df['close'], label='Close Price', color=NEON_INFO, alpha=0.8)
        
        st_col = f"SUPERT_{config['super_trend_length']}_{config['super_trend_multiplier']}"
        st_dir_col = f"SUPERTd_{config['super_trend_length']}_{config['super_trend_multiplier']}"
        if st_col in df.columns:
            ax1.plot(df['startTime'], df[st_col], label='Supertrend', color=NEON_SUCCESS if df[st_dir_col].iloc[-1] == 1 else NEON_ERROR, alpha=0.8)

        buy_signals = df[df['signal'] == 'Buy']
        sell_signals = df[df['signal'] == 'Sell']
        ax1.scatter(buy_signals['startTime'], buy_signals['close'], marker='^', color=NEON_SUCCESS, label='Buy Signal', s=100, zorder=5)
        ax1.scatter(sell_signals['startTime'], sell_signals['close'], marker='v', color=NEON_ERROR, label='Sell Signal', s=100, zorder=5)
        
        ax1.set_ylabel("Price (USDT)", color=NEON_INFO)
        ax1.set_title("Price & Signals", color=NEON_INFO)
        ax1.legend(loc='upper left', facecolor='black')
        ax1.grid(True, linestyle='--', alpha=0.6)
        
        ax2.plot(equity_curve['Date'], equity_curve['Equity'], label='Equity Curve', color=NEON_SIGNAL)
        ax2.set_ylabel("Equity (USDT)", color=NEON_INFO)
        ax2.set_title("Portfolio Equity", color=NEON_INFO)
        ax2.legend(loc='upper left', facecolor='black')
        ax2.grid(True, linestyle='--', alpha=0.6)
        
        plt.xlabel("Date", color=NEON_INFO)
        plt.tight_layout(rect=[0, 0.03, 1, 0.95])
        plt.show()
        _log_and_print("info", "Backtest plot displayed.", NEON_INFO)
    except Exception as e:
        _log_and_print("error", f"Plotting failed: {e}", NEON_ERROR)

def _run_backtest(session: HTTP, config: Dict, strategy: 'EhlersSupertrendStrategy'):
    """Runs backtest with fees and slippage."""
    initial_equity = Decimal('10000.0')
    equity_curve_data = {'Date': [], 'Equity': []}
    df = _fetch_kline_data(session, config)
    if df.empty:
        _log_and_print("error", "No kline data for backtest.", NEON_ERROR)
        return False
    
    df = strategy.calculate_indicators(df)
    if df.empty:
        _log_and_print("error", "Indicator calculation failed.", NEON_ERROR)
        return False
    
    df['signal'] = None
    df['balance'] = initial_equity
    current_equity = initial_equity
    positions = []
    
    for i in range(len(df)):
        row = df.iloc[i].copy()
        current_equity = Decimal(str(equity_curve_data['Equity'][-1])) if equity_curve_data else initial_equity
        
        # Check for SL/TP hit first
        for pos in positions[:]:
            close_price = Decimal(str(row['close']))
            is_sl_hit = (pos['side'] == 'Buy' and close_price <= pos['sl']) or (pos['side'] == 'Sell' and close_price >= pos['sl'])
            is_tp_hit = (pos['side'] == 'Buy' and close_price >= pos['tp']) or (pos['side'] == 'Sell' and close_price <= pos['tp'])

            if is_sl_hit:
                pnl = (pos['sl'] - pos['entry_price']) * pos['qty'] if pos['side'] == 'Buy' else (pos['entry_price'] - pos['sl']) * pos['qty']
                pnl -= pos['qty'] * pos['entry_price'] * TAKER_FEE
                current_equity += pnl
                strategy.update_metrics(pnl, current_equity, pd.DataFrame({'Date': [row['startTime']], 'Equity': [current_equity]}))
                positions.remove(pos)
                continue
            
            if is_tp_hit:
                pnl = (pos['tp'] - pos['entry_price']) * pos['qty'] if pos['side'] == 'Buy' else (pos['entry_price'] - pos['tp']) * pos['qty']
                pnl -= pos['qty'] * pos['entry_price'] * TAKER_FEE
                current_equity += pnl
                strategy.update_metrics(pnl, current_equity, pd.DataFrame({'Date': [row['startTime']], 'Equity': [current_equity]}))
                positions.remove(pos)
                continue
                
            pos['sl'] = strategy.update_trailing_stop(pos, close_price)

        signal_side, qty, sl_price, tp_price = strategy.generate_signal(row, positions)
        
        if signal_side and qty > 0:
            # Check for position reversal
            for pos in positions[:]:
                if (pos['side'] == 'Buy' and signal_side == 'Sell') or (pos['side'] == 'Sell' and signal_side == 'Buy'):
                    exit_price = Decimal(str(row['close']))
                    pnl = (exit_price - pos['entry_price']) * pos['qty'] if pos['side'] == 'Buy' else (pos['entry_price'] - exit_price) * pos['qty']
                    pnl -= pos['qty'] * pos['entry_price'] * TAKER_FEE
                    current_equity += pnl
                    strategy.update_metrics(pnl, current_equity, pd.DataFrame({'Date': [row['startTime']], 'Equity': [current_equity]}))
                    positions.remove(pos)
            
            # Enter new position
            entry_price = Decimal(str(row['close'])) * (Decimal('1') + SLIPPAGE if signal_side == 'Buy' else Decimal('1') - SLIPPAGE)
            fee = qty * entry_price * TAKER_FEE
            current_equity -= fee
            positions.append({
                'side': signal_side, 'entry_price': entry_price, 'qty': qty,
                'sl': sl_price, 'tp': tp_price, 'symbol': config['symbol'],
                'stopLoss': str(sl_price)
            })
            df.loc[i, 'signal'] = signal_side
        
        equity_curve_data['Date'].append(row['startTime'])
        equity_curve_data['Equity'].append(current_equity)
        
    if positions:
        final_close_price = Decimal(str(df['close'].iloc[-1]))
        for pos in positions[:]:
            pnl = (final_close_price - pos['entry_price']) * pos['qty'] if pos['side'] == 'Buy' else (pos['entry_price'] - final_close_price) * pos['qty']
            pnl -= pos['qty'] * pos['entry_price'] * TAKER_FEE
            current_equity += pnl
            strategy.update_metrics(pnl, current_equity, pd.DataFrame({'Date': [df['startTime'].iloc[-1]], 'Equity': [current_equity]}))
            positions.remove(pos)

    strategy.performance_metrics['equity_curve'] = pd.DataFrame(equity_curve_data)
    monte_carlo_return = _run_monte_carlo(strategy.performance_metrics['equity_curve'])
    total_pnl = strategy.performance_metrics['total_pnl']
    total_trades = strategy.performance_metrics['total_trades']
    win_rate = (strategy.performance_metrics['wins'] / total_trades * 100) if total_trades > 0 else 0
    
    _log_and_print("info", f"--- Backtest Summary ---", NEON_SUCCESS)
    _log_and_print("info", f"Initial Equity: {initial_equity:.4f}", NEON_INFO)
    _log_and_print("info", f"Final Equity: {current_equity:.4f}", NEON_INFO)
    _log_and_print("info", f"Total PNL: {total_pnl:.4f}", NEON_INFO)
    _log_and_print("info", f"Total Trades: {total_trades}", NEON_INFO)
    _log_and_print("info", f"Win Rate: {win_rate:.2f}%", NEON_INFO)
    _log_and_print("info", f"Sharpe Ratio: {strategy.performance_metrics['sharpe_ratio']:.2f}", NEON_INFO)
    _log_and_print("info", f"Max Drawdown: {strategy.performance_metrics['max_drawdown']:.2%}", NEON_INFO)
    _log_and_print("info", f"Monte Carlo Return: {monte_carlo_return:.2%}", NEON_INFO)
    _log_and_print("info", f"------------------------", NEON_SUCCESS)
    _send_sms("Bybit Bot Backtest Complete", f"PNL: {total_pnl:.4f}\nTrades: {total_trades}\nWin: {win_rate:.2f}%", config, _load_state())
    _plot_backtest_results(df, strategy.performance_metrics['equity_curve'], config, strategy.performance_metrics)
    return True

class EhlersSupertrendStrategy:
    """Encapsulates Ehlers Supertrend with multi-position support."""
    def __init__(self, config: Dict):
        self.config = config
        self.last_st_dir = None
        self.performance_metrics = {
            'total_trades': 0, 'wins': 0, 'losses': 0, 'total_pnl': Decimal('0'),
            'max_drawdown': Decimal('0'), 'sharpe_ratio': 0.0, 'equity_curve': pd.DataFrame({'Date': [], 'Equity': []})
        }
        self.indicator_cache = {}
        self.config['st_dir_col'] = f"SUPERTd_{self.config['super_trend_length']}_{self.config['super_trend_multiplier']}"
        self.config['rsi_col'] = f"RSI_{self.config['rsi_length']}"
        self.config['atr_col'] = f"ATRr_{self.config['atr_length']}"
        self.config['adx_col'] = f"ADX_{self.config['adx_length']}"
        self.config['risk_reward_ratio'] = self.config['take_profit_pct'] / self.config['stop_loss_pct']

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculates indicators with caching."""
        if df.empty or 'close' not in df.columns:
            return pd.DataFrame()
        
        try:
            df = df.copy() # Avoid SettingWithCopyWarning
            df.ta.supertrend(length=self.config['super_trend_length'], multiplier=self.config['super_trend_multiplier'], append=True)
            df.ta.rsi(length=self.config['rsi_length'], append=True)
            df.ta.atr(length=self.config['atr_length'], append=True)
            df.ta.adx(length=self.config['adx_length'], append=True)
            
            required_cols = [self.config['st_dir_col'], self.config['rsi_col'], self.config['atr_col'], self.config['adx_col']]
            if not all(col in df.columns for col in required_cols):
                _log_and_print("error", f"Missing indicator columns: {[col for col in required_cols if col not in df.columns]}", NEON_ERROR)
                return pd.DataFrame()
            
            df[self.config['st_dir_col']] = df[self.config['st_dir_col']].astype(int)
            df.dropna(subset=required_cols, inplace=True)
            
            return df
        except Exception as e:
            _log_and_print("error", f"Indicator calculation failed: {e}", NEON_ERROR)
            return pd.DataFrame()

    def generate_signal(self, row: pd.Series, open_positions: List[Dict]) -> tuple[Optional[str], Decimal, Decimal, Decimal]:
        """Generates trading signals, respecting max_open_trades."""
        try:
            st_dir = int(row[self.config['st_dir_col']])
            rsi_val = float(row[self.config['rsi_col']])
            adx_val = float(row[self.config['adx_col']])
            close_price = Decimal(str(row['close']))
            
            current_side = None
            if open_positions:
                current_side = open_positions[0]['side'] # Assuming only one position for now
            
            is_buy_signal = (st_dir == 1 and (self.last_st_dir == -1 or self.last_st_dir is None) and
                             self._check_filters(rsi_val, adx_val, "Buy"))
            is_sell_signal = (st_dir == -1 and (self.last_st_dir == 1 or self.last_st_dir is None) and
                              self._check_filters(rsi_val, adx_val, "Sell"))

            self.last_st_dir = st_dir
            
            side = None
            if is_buy_signal: side = 'Buy'
            elif is_sell_signal: side = 'Sell'
            
            if not side:
                return None, Decimal('0'), Decimal('0'), Decimal('0')

            qty, sl_price, tp_price = self._calculate_trade_parameters(side, close_price, row)
            
            return side, qty, sl_price, tp_price
        except Exception as e:
            _log_and_print("error", f"Signal generation failed: {e}", NEON_ERROR)
            return None, Decimal('0'), Decimal('0'), Decimal('0')

    def _check_filters(self, rsi_val: float, adx_val: float, side: str) -> bool:
        """Applies RSI and ADX filters."""
        if pd.isna(rsi_val) or pd.isna(adx_val):
            return False
        rsi_valid = (rsi_val < self.config['rsi_overbought'] if side == "Buy" else rsi_val > self.config['rsi_oversold'])
        adx_valid = adx_val >= self.config['adx_threshold']
        return rsi_valid and adx_valid

    def _calculate_trade_parameters(self, side: str, close_price: Decimal, row: pd.Series) -> tuple[Decimal, Decimal, Decimal]:
        """Calculates quantity, SL, and TP prices."""
        sl_price = Decimal('0')
        qty = Decimal('0')

        if self.config['sizing_mode'] == 'atr':
            atr_val = Decimal(str(row[self.config['atr_col']]))
            sl_offset = atr_val * Decimal(str(self.config['atr_multiplier']))
            sl_price = close_price - sl_offset if side == 'Buy' else close_price + sl_offset
            # Recalculate based on a fixed risk percentage of total equity
            balance = self._get_balance(None, self.config) # In backtest, balance is from DataFrame
            if balance == Decimal('0'):
                balance = Decimal(str(row['balance']))
            risk_amount = balance * Decimal(str(self.config['risk_pct']))
            stop_distance = abs(close_price - sl_price)
            if stop_distance > 0:
                qty = risk_amount / stop_distance
        elif self.config['sizing_mode'] == 'percentage':
            sl_offset = close_price * Decimal(str(self.config['stop_loss_pct']))
            sl_price = close_price - sl_offset if side == 'Buy' else close_price + sl_offset
            balance = self._get_balance(None, self.config)
            if balance == Decimal('0'):
                balance = Decimal(str(row['balance']))
            risk_amount = balance * Decimal(str(self.config['risk_pct']))
            qty = risk_amount / sl_offset if sl_offset > 0 else Decimal('0')
        else:
            qty = Decimal(str(self.config['max_position_size']))

        qty = max(qty, self.config.get('min_order_qty', DEFAULT_MIN_ORDER_QTY))
        qty = min(qty, Decimal(str(self.config['max_position_size'])))
        qty = (qty // self.config['qty_step']) * self.config['qty_step']
        
        tp_offset = abs(close_price - sl_price) * Decimal(str(self.config['risk_reward_ratio']))
        tp_price = close_price + tp_offset if side == 'Buy' else close_price - tp_offset

        sl_price = sl_price.quantize(self.config['price_precision'], rounding=ROUND_DOWN)
        tp_price = tp_price.quantize(self.config['price_precision'], rounding=ROUND_DOWN)

        return qty, sl_price, tp_price

    def update_trailing_stop(self, position: Dict, current_price: Decimal) -> Decimal:
        """Updates trailing stop-loss."""
        try:
            trailing_pct = Decimal(str(self.config['trailing_stop_pct']))
            current_sl = Decimal(position.get('stopLoss', '0'))
            new_sl = current_price * (Decimal('1') - trailing_pct) if position['side'] == 'Buy' else current_price * (Decimal('1') + trailing_pct)
            
            if position['side'] == 'Buy':
                return max(current_sl, new_sl).quantize(self.config['price_precision'], rounding=ROUND_DOWN)
            else:
                return min(current_sl, new_sl).quantize(self.config['price_precision'], rounding=ROUND_DOWN)
        except Exception as e:
            _log_and_print("error", f"Trailing stop update failed: {e}", NEON_ERROR)
            return Decimal(position.get('stopLoss', '0'))

    def update_metrics(self, pnl: Decimal, equity: Decimal, equity_curve: pd.DataFrame):
        """Updates performance metrics."""
        self.performance_metrics['total_trades'] += 1
        self.performance_metrics['total_pnl'] += pnl
        if pnl > 0:
            self.performance_metrics['wins'] += 1
        elif pnl < 0:
            self.performance_metrics['losses'] += 1
        
        if not equity_curve.empty:
            equity_curve_combined = pd.concat([self.performance_metrics['equity_curve'], equity_curve]).reset_index(drop=True)
            self.performance_metrics['equity_curve'] = equity_curve_combined
            returns = self.performance_metrics['equity_curve']['Equity'].pct_change().dropna()
            self.performance_metrics['sharpe_ratio'] = float(returns.mean() / returns.std() * np.sqrt(252 * 24 * 60 / int(self.config['interval']))) if not returns.empty and returns.std() != 0 else 0.0
            
            max_equity = self.performance_metrics['equity_curve']['Equity'].max()
            current_drawdown = (max_equity - equity) / max_equity if max_equity > 0 else Decimal('0')
            self.performance_metrics['max_drawdown'] = max(self.performance_metrics['max_drawdown'], current_drawdown)

def _display_startup_banner(config: Dict):
    """Displays startup banner with config summary."""
    banner = f"""
{NEON_SUCCESS}============================================================
       Pyrmethus's Ascended Neon Bybit Trading Bot
============================================================
Symbol: {config['symbol']} | Interval: {config['interval']}m | Leverage: {config['leverage']}x
Mode: {'Backtest' if config['backtest'] else 'Live'} | Testnet: {config['testnet']}
Risk: {config['risk_pct']*100:.2f}% | Max Trades: {config['max_open_trades']}
SMS: {'Enabled' if config['sms_notifications'] else 'Disabled'} | Display: {config['display_mode']}
============================================================{NEON_RESET}
"""
    print(banner)
    logging.info("Bot started with config: " + str({k: v for k, v in config.items() if k not in ['sms_recipient']}))

def _graceful_shutdown(session: HTTP, config: Dict, state: Dict):
    """Handles graceful shutdown."""
    positions = _get_open_positions(session, config)
    for pos in positions:
        _close_position(session, pos, config, state)
    _save_state(state)
    _log_and_print("info", "Graceful shutdown complete.", NEON_SUCCESS)
    _send_sms("Bybit Bot Shutdown", "Bot has shut down gracefully.", config, state, priority='critical')

def _check_api_health(session: HTTP, config: Dict, state: Dict) -> bool:
    """Checks API connectivity."""
    try:
        response = session.get_account_info()
        if response['retCode'] == 0:
            _log_and_print("debug", "API health check passed.", NEON_DEBUG)
            return True
        _log_and_print("error", f"API health check failed: {response}", NEON_ERROR)
        _send_sms("Bybit Bot API Failure", f"Health check failed: {response.get('retMsg', 'Unknown')}", config, state, priority='critical')
        return False
    except Exception as e:
        _log_and_print("error", f"API health check failed: {e}", NEON_ERROR)
        _send_sms("Bybit Bot API Failure", f"Health check failed: {e}", config, state, priority='critical')
        return False

def main():
    """Main execution loop."""
    setup_logging()
    config = _load_config()
    _display_startup_banner(config)
    session = _initialize_session(config)
    if session is None:
        _log_and_print("error", "Exiting due to session failure.", NEON_ERROR)
        sys.exit(1)
    
    strategy = EhlersSupertrendStrategy(config)
    
    if config['backtest']:
        _log_and_print("info", f"Starting backtest for {config['symbol']}...", NEON_INFO)
        if not _run_backtest(session, config, strategy):
            _log_and_print("error", "Backtest failed.", NEON_ERROR)
        sys.exit(0)

    _fetch_instrument_rules(session, config)
    _log_and_print("info", f"Summoning Pyrmethus's Bot for {config['symbol']} ({config['interval']}m)...", NEON_SUCCESS)
    
    state = _load_state()
    last_timestamp = state.get('last_timestamp')
    df_cache = pd.DataFrame()
    last_health_check = 0
    api_failure_count = 0
    
    try:
        while True:
            current_time = int(time.time())
            if current_time - last_health_check >= HEALTH_CHECK_INTERVAL:
                if not _check_api_health(session, config, state) or not _check_consistency(session, config, state):
                    api_failure_count += 1
                    if api_failure_count >= CIRCUIT_BREAKER_THRESHOLD:
                        _log_and_print("error", f"Repeated failures ({api_failure_count}). Pausing for {CIRCUIT_BREAKER_PAUSE//60} minutes.", NEON_ERROR)
                        _send_sms("Bybit Bot Paused", "Paused due to repeated failures.", config, state, priority='critical')
                        time.sleep(CIRCUIT_BREAKER_PAUSE)
                        api_failure_count = 0
                        session = _initialize_session(config)
                        if session is None:
                            _log_and_print("error", "Failed to reinitialize session. Exiting.", NEON_ERROR)
                            sys.exit(1)
                    continue
                else:
                    api_failure_count = 0
                last_health_check = current_time
                _send_heartbeat(config, state)
            
            df_new = _fetch_kline_data(session, config, last_timestamp)
            if df_new.empty:
                _log_and_print("warning", "No new kline data. Waiting...", NEON_WARNING)
                time.sleep(60)
                continue
            
            df_cache = pd.concat([df_cache, df_new]).drop_duplicates(subset='startTime').sort_values('startTime').tail(KLINE_CACHE_SIZE)
            
            latest_timestamp = df_cache['startTime'].iloc[-1].timestamp() * 1000
            last_timestamp = int(latest_timestamp)
            
            df_ind = strategy.calculate_indicators(df_cache.copy())
            if df_ind.empty:
                _log_and_print("warning", "Indicator calculation failed. Waiting...", NEON_WARNING)
                time.sleep(60)
                continue
            
            latest_data = df_ind.iloc[-1]
            close_price = Decimal(str(latest_data['close']))
            st_direction = latest_data[strategy.config['st_dir_col']]
            
            open_positions = _get_open_positions(session, config)
            
            # Update trailing stop for any open positions
            for pos in open_positions[:]:
                new_sl = strategy.update_trailing_stop(pos, close_price)
                current_sl = Decimal(pos.get('stopLoss', '0'))
                if new_sl != current_sl and new_sl > Decimal('0'):
                    response = session.set_trading_stop(
                        category=config['category'], symbol=config['symbol'],
                        stopLoss=f"{new_sl:.8f}", tpslMode="Full", positionIdx=pos.get('positionIdx', 0)
                    )
                    if response['retCode'] == 0:
                        _log_and_print("info", f"Updated trailing stop for {pos['side']} to {new_sl}.", NEON_INFO)
                        _send_sms(f"Bybit Bot: Trailing Stop", f"Side: {pos['side']}\nNew SL: {new_sl}", config, state)
                        pos['stopLoss'] = str(new_sl)
                    else:
                        _log_and_print("error", f"Trailing stop update failed: {response}", NEON_ERROR)
            
            # Generate and execute new signals
            signal_side, qty, sl_price, tp_price = strategy.generate_signal(latest_data, open_positions)
            
            if signal_side and qty > 0:
                is_reversal = (signal_side == 'Buy' and any(p['side'] == 'Sell' for p in open_positions)) or \
                              (signal_side == 'Sell' and any(p['side'] == 'Buy' for p in open_positions))
                is_new_entry = not open_positions or (is_reversal and len(open_positions) < config['max_open_trades'])
                
                if is_reversal:
                    _close_position(session, open_positions[0], config, state)
                    time.sleep(int(config['close_delay']))
                    open_positions = _get_open_positions(session, config)
                
                if is_new_entry or not open_positions:
                    _place_order(session, signal_side, qty, sl_price, tp_price, config, state)
            
            _save_state(state)
            
            sleep_duration = int(config['interval']) * 60
            _log_and_print("info", f"Slumbering for {sleep_duration} seconds...", NEON_INFO)
            time.sleep(sleep_duration)

    except KeyboardInterrupt:
        _log_and_print("info", "Shutdown signal received.", NEON_INFO)
        _graceful_shutdown(session, config, state)
    except Exception as e:
        _log_and_print("error", f"Runtime error: {e}", NEON_ERROR)
        _send_sms("Bybit Bot Runtime Error", f"Error: {e}", config, state, priority='critical')

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _log_and_print("error", f"Fatal error: {e}", NEON_ERROR)
        config = _load_config()
        state = _load_state()
        _send_sms("Bybit Bot Fatal Error", f"The bot encountered a fatal error: {e}", config, state, priority='critical')
