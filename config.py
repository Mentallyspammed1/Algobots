"""
Configuration for the Bybit Trading Bot.

This file stores API credentials, trading parameters, and other settings.
It is recommended to use environment variables for sensitive data like API keys.
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- API Configuration ---
API_KEY = os.getenv("BYBIT_API_KEY", "YOUR_API_KEY_HERE")
API_SECRET = os.getenv("BYBIT_API_SECRET", "YOUR_API_SECRET_HERE")
TESTNET = os.getenv("BYBIT_TESTNET", "True").lower() in ('true', '1', 't')

# --- Trading Parameters ---
SYMBOL = "BTCUSDT"
CATEGORY = "linear"
TRADE_QTY_USD = 10  # Desired trade size in USD
MAX_ACTIVE_POSITIONS = 1

# --- Strategy Configuration ---
STRATEGY_NAME = "MyAwesomeStrategy"
STRATEGY_FILE = "strategies/strategy_template.py"

# --- WebSocket Configuration ---
WS_HEARTBEAT = 20  # seconds

# --- Logging Configuration ---
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FILE = "logs/trading_bot.log"