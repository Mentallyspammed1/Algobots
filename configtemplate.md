import os

# --- General Bot Configuration ---

# Set to True for testing on Bybit Testnet, False for Mainnet trading.
# IMPORTANT: Use separate API keys for Testnet and Mainnet.
TESTNET = True

# Logging Level: Adjust for verbosity.
# Options: logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL
LOG_LEVEL = logging.INFO 

# --- API Credentials ---
# IMPORTANT: Load API keys from environment variables for security.
# DO NOT hardcode them directly in this file for production use.
# Example: export BYBIT_API_KEY="YOUR_API_KEY"
#          export BYBIT_API_SECRET="YOUR_API_SECRET"
API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')

# --- Trading Pair & Account Type ---
SYMBOL = 'BTCUSDT'              # The trading pair (e.g., 'BTCUSDT', 'ETHUSDT')
CATEGORY = 'linear'             # Account category: 'spot', 'linear', 'inverse', 'option'

# --- Order & Position Sizing ---
LEVERAGE = 10                   # Desired leverage for derivatives (e.g., 5, 10, 25)
ORDER_SIZE = 0.001              # Quantity for each entry/exit order in base currency (e.g., 0.001 BTC)

# --- Ehlers Supertrend Cross Strategy Parameters ---
KLINE_INTERVAL = '15'           # Kline interval (e.g., '1', '5', '15', '60', 'D')
KLINE_LIMIT = 200               # Number of historical klines to fetch (must be > ATR_PERIOD)
ATR_PERIOD = 14                 # Period for Average True Range (ATR) calculation
SUPERTREND_MULTIPLIER = 3       # Multiplier for ATR in Supertrend calculation

# --- Risk Management & Order Parameters ---
MAX_POSITION_SIZE = 0.01        # Max allowed absolute position size. Bot will try to reduce if exceeded.
MAX_OPEN_ENTRY_ORDERS_PER_SIDE = 1 # Max number of active limit orders on one side (Buy/Sell) for entry.
                                   # Set to 0 to only close/rebalance positions without placing new entries.
ORDER_REPRICE_THRESHOLD_PCT = 0.0002 # Percentage price change to trigger order repricing (0.02% = 0.0002)

# --- Delays & Retry Settings ---
RECONNECT_DELAY_SECONDS = 5     # Delay before attempting WebSocket reconnection
API_RETRY_DELAY_SECONDS = 3     # Delay before retrying failed HTTP API calls

# --- Advanced Orderbook Manager Settings ---
USE_SKIP_LIST_FOR_ORDERBOOK = True # True for OptimizedSkipList, False for EnhancedHeap
# --- Top of your bot script (e.g., `bybit_bot.py`) ---
import os
import asyncio
import json
import logging
import time
import uuid
import random
from collections import deque
from typing import Dict, List, Any, Optional, Tuple, Generic, TypeVar
from dataclasses import dataclass
from contextlib import asynccontextmanager

# Import pybit clients
from pybit.unified_trading import HTTP, WebSocket

# Import configuration settings
import config # <--- NEW LINE

# Configure logging
logging.basicConfig(
    level=config.LOG_LEVEL, # Use LOG_LEVEL from config
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- (Rest of your data structures and indicator classes remain the same) ---

# --- Main Trading Bot Class (updated __init__) ---
class BybitTradingBot:
    def __init__(self): # Simplified __init__
        # Assign configuration parameters directly from the config module
        self.symbol = config.SYMBOL
        self.category = config.CATEGORY
        self.leverage = config.LEVERAGE
        self.order_size = config.ORDER_SIZE
        self.kline_interval = config.KLINE_INTERVAL
        self.kline_limit = config.KLINE_LIMIT
        self.atr_period = config.ATR_PERIOD
        self.supertrend_multiplier = config.SUPERTREND_MULTIPLIER
        self.max_position_size = config.MAX_POSITION_SIZE
        self.max_open_entry_orders_per_side = config.MAX_OPEN_ENTRY_ORDERS_PER_SIDE
        self.order_reprice_threshold_pct = config.ORDER_REPRICE_THRESHOLD_PCT
        self.testnet = config.TESTNET

        # Validate API keys (still from environment variables for security)
        if not config.API_KEY or not config.API_SECRET: # Use config.API_KEY
            logger.critical("API_KEY or API_SECRET environment variables not set. Exiting.")
            raise ValueError("API credentials missing.")

        # Initialize pybit HTTP client
        self.http_session = HTTP(testnet=self.testnet, api_key=config.API_KEY, api_secret=config.API_SECRET)
        
        # Initialize pybit Public WebSocket client
        self.ws_public = WebSocket(channel_type=self.category, testnet=self.testnet)
        
        # Initialize pybit Private WebSocket client
        self.ws_private = WebSocket(channel_type='private', testnet=self.testnet, api_key=config.API_KEY, api_secret=config.API_SECRET)

        self.orderbook_manager = AdvancedOrderbookManager(self.symbol, use_skip_list=config.USE_SKIP_LIST_FOR_ORDERBOOK) # Use from config
        
        # ... rest of __init__ and bot logic ...

    # --- In other parts of your code, use config.XYZ for global parameters ---
    # e.g., in _start_websocket_listener:
    # await asyncio.sleep(config.RECONNECT_DELAY_SECONDS)
    
    # e.g., in setup_initial_state:
    # await asyncio.sleep(config.API_RETRY_DELAY_SECONDS)

# --- Main Execution Block (updated) ---
if __name__ == "__main__":
    if not config.API_KEY or not config.API_SECRET:
        logger.critical("BYBIT_API_KEY or BYBIT_API_SECRET environment variables are NOT set. Please set them before running the bot.")
        exit(1)

    bot = BybitTradingBot() # No more parameters needed here!

    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt detected. Stopping bot gracefully...")
    except Exception as e:
        logger.critical(f"An unhandled exception occurred during bot execution: {e}", exc_info=True)
