# config.py

import os
from dotenv import load_dotenv

load_dotenv() # Load environment variables from .env file

# --- API Configuration ---
TESTNET = False # Set to False to use Bybit Mainnet
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")

# --- Trading Parameters ---
SYMBOL = os.getenv("BYBIT_SYMBOL", "BTCUSDT")
INTERVAL = os.getenv("BYBIT_INTERVAL", "1") # 1, 5, 15, 60, 240, D
LEVERAGE = float(os.getenv("BYBIT_LEVERAGE", "10"))
TRADE_QTY = float(os.getenv("BYBIT_TRADE_QTY", "0.001")) # Quantity per trade

# --- Indicator Parameters ---
# RSI
RSI_PERIOD = int(os.getenv("RSI_PERIOD", "14"))
RSI_OVERBOUGHT = float(os.getenv("RSI_OVERBOUGHT", "70"))
RSI_OVERSOLD = float(os.getenv("RSI_OVERSOLD", "30"))

# Stochastic RSI
STOCH_RSI_PERIOD = int(os.getenv("STOCH_RSI_PERIOD", "14"))
STOCH_RSI_SMOOTH_K = int(os.getenv("STOCH_RSI_SMOOTH_K", "3"))
STOCH_RSI_SMOOTH_D = int(os.getenv("STOCH_RSI_SMOOTH_D", "3"))
STOCH_RSI_OVERBOUGHT = float(os.getenv("STOCH_RSI_OVERBOUGHT", "80"))
STOCH_RSI_OVERSOLD = float(os.getenv("STOCH_RSI_OVERSOLD", "20"))

# SuperTrend
SUPER_TREND_PERIOD = int(os.getenv("SUPER_TREND_PERIOD", "10"))
SUPER_TREND_MULTIPLIER = float(os.getenv("SUPER_TREND_MULTIPLIER", "3.0"))

# Ehlers Fisher Transform
EH_FISHER_PERIOD = int(os.getenv("EH_FISHER_PERIOD", "10"))
EH_FISHER_SMOOTHING = int(os.getenv("EH_FISHER_SMOOTHING", "5"))
EH_FISHER_OVERBOUGHT = float(os.getenv("EH_FISHER_OVERBOUGHT", "1.0"))
EH_FISHER_OVERSOLD = float(os.getenv("EH_FISHER_OVERSOLD", "-1.0"))
EH_FISHER_TRIGGER_BUY = float(os.getenv("EH_FISHER_TRIGGER_BUY", "0.5"))
EH_FISHER_TRIGGER_SELL = float(os.getenv("EH_FISHER_TRIGGER_SELL", "-0.5"))

# --- Risk Management ---
MAX_POSITION_SIZE = float(os.getenv("MAX_POSITION_SIZE", "0.005")) # Max position size in base currency
STOP_LOSS_PERCENT = float(os.getenv("STOP_LOSS_PERCENT", "0.005")) # 0.5%
TAKE_PROFIT_PERCENT = float(os.getenv("TAKE_PROFIT_PERCENT", "0.01")) # 1%

# --- WebSocket & Order Management ---
ORDER_TIMEOUT_SECONDS = int(os.getenv("ORDER_TIMEOUT_SECONDS", "30"))
RECONNECT_TIMEOUT_SECONDS = int(os.getenv("RECONNECT_TIMEOUT_SECONDS", "10"))
PING_INTERVAL = int(os.getenv("PING_INTERVAL", "20")) # Send ping every X seconds
PING_TIMEOUT = int(os.getenv("PING_TIMEOUT", "10")) # Disconnect if no pong received within X seconds

# --- Logging ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper() # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FILE = os.getenv("LOG_FILE", "trading_bot.log")

# --- Bybit Endpoints ---
BYBIT_REST_BASE_URL = "https://api.bybit.com" if not TESTNET else "https://api-testnet.bybit.com"
BYBIT_WS_PUBLIC_BASE_URL = "wss://stream.bybit.com/v5/public/linear" if not TESTNET else "wss://stream-testnet.bybit.com/v5/public/linear"
BYBIT_WS_PRIVATE_BASE_URL = "wss://stream.bybit.com/v5/private" if not TESTNET else "wss://stream-testnet.bybit.com/v5/private"