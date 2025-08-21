"""
Configuration file for the Supertrend Trading Bot.

This file defines the bot's settings, including API keys, trading parameters,
indicator settings, and risk management rules.
"""

import os
from dataclasses import dataclass
from enum import Enum

# =====================================================================
# ENUMS FOR CONFIGURATION
# =====================================================================

class Signal(Enum):
    """Trading signals"""
    STRONG_BUY = 2
    BUY = 1
    NEUTRAL = 0
    SELL = -1
    STRONG_SELL = -2

class OrderType(Enum):
    """Supported order types"""
    MARKET = "Market"
    LIMIT = "Limit"

class Category(Enum):
    """Bybit product categories"""
    LINEAR = "linear"
    SPOT = "spot"
    INVERSE = "inverse"
    OPTION = "option"

# =====================================================================
# CONFIGURATION DATACLASS
# =====================================================================

@dataclass
class Config:
    """
    Bot configuration settings.

    All parameters can be overridden by environment variables with the
    prefix BYBIT_BOT_ (e.g., BYBIT_BOT_SYMBOL).
    """
    # --- API Configuration ---
    # It's highly recommended to use environment variables for security.
    # Set BYBIT_API_KEY, BYBIT_API_SECRET, and BYBIT_TESTNET in your environment.
    API_KEY: str = "pXXkHX8ryNx4tJw4oQ"  # Replace with your Bybit API Key or set BYBIT_API_KEY env var
    API_SECRET: str = "091D2RzNbFwf8IPv6HKaKtjPiTSChLDuhYyn" # Replace with your Bybit API Secret or set BYBIT_API_SECRET env var
    TESTNET: bool = False  # Set BYBIT_TESTNET env var to 'true' or 'false'

    # --- Trading Configuration ---
    SYMBOL: str = "TRUMPUSDT"  # Trading pair (e.g., "BTCUSDT", "ETHUSDT")
    CATEGORY: Category = Category.LINEAR # Market category ('linear', 'spot', 'inverse', 'option')
    LEVERAGE: int = 5  # Leverage to use for derivatives trading

    # --- Position Sizing ---
    RISK_PER_TRADE_PCT: float = 1.0  # Percentage of account balance to risk per trade (e.g., 1.0 for 1%)
    MAX_POSITION_SIZE_USD: float = 20.0  # Maximum allowed position value in USD
    MIN_POSITION_SIZE_USD: float = 5.0  # Minimum allowed position value in USD

    # --- Strategy Parameters ---
    TIMEFRAME: str = "3"  # Kline interval (e.g., '1', '3', '5', '15', '30', '60', 'D')
    LOOKBACK_PERIODS: int = 100  # Number of historical klines to fetch for indicator calculations

    # --- Supertrend Indicator Parameters ---
    ST_PERIOD: int = 10  # ATR period for Supertrend calculation
    ST_MULTIPLIER: float = 3.0  # Multiplier for ATR to determine Supertrend bands

    # --- Risk Management ---
    STOP_LOSS_PCT: float = 0.015  # Stop loss percentage from entry price (e.g., 1.5%)
    TAKE_PROFIT_PCT: float = 0.03  # Take profit percentage from entry price (e.g., 3%)
    TRAILING_STOP_PCT: float = 0.005 # Trailing stop percentage to trail profit (e.g., 0.5%)
    MAX_DAILY_LOSS_PCT: float = 0.05 # Maximum allowed daily loss as a percentage of the starting balance (e.g., 5%)
    MAX_OPEN_POSITIONS: int = 1 # Maximum number of concurrent open positions

    # --- Execution Settings ---
    ORDER_TYPE: OrderType = OrderType.MARKET # Default order type ('Market' or 'Limit')
    TIME_IN_FORCE: str = "GTC"  # Time in force for orders ('GTC', 'IOC', 'FOK', 'PostOnly')
    REDUCE_ONLY: bool = False # Whether orders should only reduce existing positions

    # --- Bot Settings ---
    LOOP_INTERVAL_SEC: int = 60  # How often the bot checks for new signals and updates (in seconds)
    LOG_LEVEL: str = "INFO" # Logging level ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
    LOG_FILE: str = "supertrend_bot.log" # Name of the log file

    def __post_init__(self):
        """
        Post-initialization to load settings from environment variables
        and perform basic validation.
        """
        # Load from environment variables, overriding defaults
        self.API_KEY = os.getenv('BYBIT_API_KEY', self.API_KEY)
        self.API_SECRET = os.getenv('BYBIT_API_SECRET', self.API_SECRET)

        testnet_env = os.getenv('BYBIT_TESTNET', str(self.TESTNET)).lower()
        self.TESTNET = testnet_env == 'true'

        # Override other config parameters using BYBIT_BOT_ prefix
        self.SYMBOL = os.getenv('BYBIT_BOT_SYMBOL', self.SYMBOL)
        self.CATEGORY = Category(os.getenv('BYBIT_BOT_CATEGORY', self.CATEGORY.value))
        self.LEVERAGE = int(os.getenv('BYBIT_BOT_LEVERAGE', self.LEVERAGE))
        self.RISK_PER_TRADE_PCT = float(os.getenv('BYBIT_BOT_RISK_PER_TRADE_PCT', self.RISK_PER_TRADE_PCT))
        self.MAX_POSITION_SIZE_USD = float(os.getenv('BYBIT_BOT_MAX_POSITION_SIZE_USD', self.MAX_POSITION_SIZE_USD))
        self.MIN_POSITION_SIZE_USD = float(os.getenv('BYBIT_BOT_MIN_POSITION_SIZE_USD', self.MIN_POSITION_SIZE_USD))
        self.TIMEFRAME = os.getenv('BYBIT_BOT_TIMEFRAME', self.TIMEFRAME)
        self.LOOKBACK_PERIODS = int(os.getenv('BYBIT_BOT_LOOKBACK_PERIODS', self.LOOKBACK_PERIODS))
        self.ST_PERIOD = int(os.getenv('BYBIT_BOT_ST_PERIOD', self.ST_PERIOD))
        self.ST_MULTIPLIER = float(os.getenv('BYBIT_BOT_ST_MULTIPLIER', self.ST_MULTIPLIER))
        self.STOP_LOSS_PCT = float(os.getenv('BYBIT_BOT_STOP_LOSS_PCT', self.STOP_LOSS_PCT))
        self.TAKE_PROFIT_PCT = float(os.getenv('BYBIT_BOT_TAKE_PROFIT_PCT', self.TAKE_PROFIT_PCT))
        self.TRAILING_STOP_PCT = float(os.getenv('BYBIT_BOT_TRAILING_STOP_PCT', self.TRAILING_STOP_PCT))
        self.MAX_DAILY_LOSS_PCT = float(os.getenv('BYBIT_BOT_MAX_DAILY_LOSS_PCT', self.MAX_DAILY_LOSS_PCT))
        self.MAX_OPEN_POSITIONS = int(os.getenv('BYBIT_BOT_MAX_OPEN_POSITIONS', self.MAX_OPEN_POSITIONS))
        self.ORDER_TYPE = OrderType(os.getenv('BYBIT_BOT_ORDER_TYPE', self.ORDER_TYPE.value))
        self.TIME_IN_FORCE = os.getenv('BYBIT_BOT_TIME_IN_FORCE', self.TIME_IN_FORCE)
        self.REDUCE_ONLY = os.getenv('BYBIT_BOT_REDUCE_ONLY', str(self.REDUCE_ONLY)).lower() == 'true'
        self.LOOP_INTERVAL_SEC = int(os.getenv('BYBIT_BOT_LOOP_INTERVAL_SEC', self.LOOP_INTERVAL_SEC))
        self.LOG_LEVEL = os.getenv('BYBIT_BOT_LOG_LEVEL', self.LOG_LEVEL)
        self.LOG_FILE = os.getenv('BYBIT_BOT_LOG_FILE', self.LOG_FILE)

        # Basic validation for API keys
        if self.API_KEY == "YOUR_BYBIT_API_KEY" or self.API_SECRET == "YOUR_BYBIT_API_SECRET":
            print("\nWARNING: Bybit API Key or Secret not configured.")
            print("Please set BYBIT_API_KEY and BYBIT_API_SECRET environment variables,")
            print("or update the Config class in config.py directly.")
            # In a real application, you might want to exit here if keys are mandatory.
            # For this example, we allow it to proceed but warn the user.
