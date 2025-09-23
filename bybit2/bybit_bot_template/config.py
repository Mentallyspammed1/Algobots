# Configuration for the Bybit Trading Bot Template

# General Bot Settings
BOT_NAME = "BybitTemplateBot"
LOG_LEVEL = "INFO"  # Options: DEBUG, INFO, WARNING, ERROR, CRITICAL

# API Settings
# These should ideally be loaded from .env, but can be overridden here if needed
# BYBIT_API_KEY = "your_api_key_here"
# BYBIT_API_SECRET = "your_api_secret_here"
# BYBIT_TESTNET = True # Set to False for mainnet

# Trading Strategy Settings
STRATEGY_NAME = "ExampleStrategy" # The name of the strategy to load from strategies/

# Strategy-specific parameters (example for a moving average strategy)
STRATEGY_PARAMS = {
    "symbol": "BTCUSDT",
    "interval": "1",  # Kline interval (e.g., "1", "5", "15", "60", "D")
    "qty": "0.001",   # Order quantity
    "leverage": 10,   # Leverage for perpetual trading
    "stop_loss_pct": 0.01, # Stop loss percentage (e.g., 1%)
    "take_profit_pct": 0.02, # Take profit percentage (e.g., 2%)
    "sma_short_period": 10,
    "sma_long_period": 30,
}

# WebSocket Settings
WEBSOCKET_RECONNECT_DELAY = 5 # Seconds to wait before attempting to reconnect WebSocket

# Logging Settings
LOG_FILE = "bot.log"
LOG_FORMAT = "{time} {level} {message}"

# Other settings
# ...
