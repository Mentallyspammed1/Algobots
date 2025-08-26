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
BYBIT_API_ENDPOINT = "https://api-testnet.bybit.com" if TESTNET else "https://api.bybit.com"
API_RATE_LIMIT_CALLS = 10
API_RATE_LIMIT_PERIOD = 1  # in seconds
API_REQUEST_RETRIES = 3
API_BACKOFF_FACTOR = 2

# --- Trading Parameters ---
SYMBOL = "BTCUSDT"
BYBIT_CATEGORY = "linear"  # Renamed from CATEGORY for PSG.py compatibility
USDT_AMOUNT_PER_TRADE = 10  # Renamed from TRADE_QTY_USD
MAX_ACTIVE_POSITIONS = 1
INTERVAL = '15'  # Kline interval for the bot
CANDLE_FETCH_LIMIT = 200
POLLING_INTERVAL_SECONDS = 5

# --- Strategy: Stochastic RSI + Ehlers Fisher ---
STOCHRSI_K_PERIOD = 3
STOCHRSI_D_PERIOD = 3
STOCHRSI_OVERBOUGHT_LEVEL = 80
STOCHRSI_OVERSOLD_LEVEL = 20
USE_STOCHRSI_CROSSOVER = True
EHLERS_FISHER_LENGTH = 10
EHLERS_SUPERSMOOTHER_LENGTH = 10
SMA_LENGTH = 50

# --- Strategy: Pivot Points & Order Blocks ---
ENABLE_FIB_PIVOT_ACTIONS = True
PIVOT_TIMEFRAME = '60'  # Timeframe for pivot calculations (e.g., '60' for 1-hour)
PIVOT_LEFT_BARS = 10
PIVOT_RIGHT_BARS = 10
MAX_ACTIVE_OBS = 5  # Max active Bullish/Bearish Order Blocks to track
FIB_ENTRY_CONFIRM_PERCENT = 0.01  # % price must be within fib level for entry
FIB_EXIT_WARN_PERCENT = 0.01  # % price must be within fib level for exit warning
FIB_EXIT_ACTION = 'close'  # 'close' or 'warn'

# --- Risk Management ---
TAKE_PROFIT_PCT = 0.02  # 2%
STOP_LOSS_PCT = 0.01  # 1%
ATR_PERIOD = 14
ATR_MULTIPLIER_TP = 3.0
ATR_MULTIPLIER_SL = 1.5

# --- WebSocket Configuration ---
WS_HEARTBEAT = 20  # seconds

# --- Logging Configuration ---
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FILE = "logs/trading_bot.log"

# --- Deprecated / To be reviewed ---
STRATEGY_NAME = "MyAwesomeStrategy"
STRATEGY_FILE = "strategies/strategy_template.py"