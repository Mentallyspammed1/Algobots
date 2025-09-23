# Configuration for the Bybit Trading Bot

# General Settings
SYMBOL = "BTCUSDT"
INTERVAL = "60"  # Kline interval (e.g., "60" for 1 hour, "D" for daily)
NUM_CANDLES = 2000  # Number of historical candles to fetch for analysis. Increased to 2000.
STRATEGY_NAME = "StochRSI_Fib_OB_Strategy" # The trading strategy to use.

# Strategy Specific Parameters (StochRSI_Fib_OB_Strategy)

# Stochastic RSI Settings
STOCHRSI_K_PERIOD = 10 # Reduced from 14
STOCHRSI_D_PERIOD = 2 # Reduced from 3
STOCHRSI_OVERBOUGHT_LEVEL = 80
STOCHRSI_OVERSOLD_LEVEL = 20
USE_STOCHRSI_CROSSOVER = True # Whether to require a crossover for signals

# Fibonacci Pivot Points Settings
ENABLE_FIB_PIVOT_ACTIONS = True
FIB_ENTRY_CONFIRM_PERCENT = 0.001 # 0.1% - Confirmation threshold for entry near pivots
FIB_EXIT_WARN_PERCENT = 0.002 # 0.2% - Warning threshold for exit near pivots
FIB_EXIT_ACTION = "close_position" # Action to take when exit warning is triggered

# ATR Settings for TP/SL
ATR_PERIOD = 10 # Reduced from 14
ATR_MULTIPLIER_SL = 1.5 # Multiplier for ATR to set Stop Loss
ATR_MULTIPLIER_TP = 2.0 # Multiplier for ATR to set Take Profit

# Order Settings
ORDER_QUANTITY = "0.1" # Default quantity for trades. Increased to bypass minimum limit.
STOP_LOSS_PERCENT = 0.01 # Default stop loss percentage (if not using ATR)
TAKE_PROFIT_PERCENT = 0.02 # Default take profit percentage (if not using ATR)

# Account Type (Unified or Standard)
# For Unified Trading Account, use "UNIFIED"
# For Standard Account, use "CONTRACT" or "SPOT" depending on your trading product
ACCOUNT_TYPE = "UNIFIED" # Ensure this matches your Bybit account setup

# Other settings
LOG_LEVEL = "INFO" # Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)