# config.py

# --- Trading Parameters ---
SYMBOL = "TRUMPUSDT"  # The trading pair (e.g., "BTCUSDT", "ETHUSDT")
INTERVAL = "1"      # Kline interval (e.g., "1", "5", "15", "60", "D"). "1" for 1-minute.
USDT_AMOUNT_PER_TRADE = 5.0 # Desired USDT amount to trade per order (e.g., 10 USDT).
                             # IMPORTANT: Adjust this based on your capital and risk tolerance.

# --- Strategy Parameters (Pivot Points) ---
# Defines the number of bars to the left and right to detect a pivot point.
# A higher number means a more significant (but less frequent) pivot.
PIVOT_LEFT_BARS = 5
PIVOT_RIGHT_BARS = 5
# Price tolerance percentage for detecting if current price is "near" a pivot level.
# E.g., 0.001 means 0.1% deviation is considered "near".
PIVOT_TOLERANCE_PCT = 0.002

# --- Strategy Parameters (StochRSI) ---
# Standard StochRSI calculation periods and overbought/oversold levels.
STOCHRSI_K_PERIOD = 12 # This is the period for RSI calculation within StochRSI
STOCHRSI_D_PERIOD = 3  # This is the smoothing period for both %K and %D lines of StochRSI
STOCHRSI_OVERBOUGHT_LEVEL = 80  # StochRSI value indicating overbought conditions
STOCHRSI_OVERSOLD_LEVEL = 20    # StochRSI value indicating oversold conditions
# Set to True for K/D line crossover signals, False for K line crossing overbought/oversold levels.
USE_STOCHRSI_CROSSOVER = True

# --- Strategy Parameters (StochRSI) ---
# Standard StochRSI calculation periods and overbought/oversold levels.
STOCHRSI_K_PERIOD = 12 # This is the period for RSI calculation within StochRSI
STOCHRSI_D_PERIOD = 3  # This is the smoothing period for both %K and %D lines of StochRSI
STOCHRSI_OVERBOUGHT_LEVEL = 80  # StochRSI value indicating overbought conditions
STOCHRSI_OVERSOLD_LEVEL = 20    # StochRSI value indicating oversold conditions
# Set to True for K/D line crossover signals, False for K line crossing overbought/oversold levels.
USE_STOCHRSI_CROSSOVER = True

# --- Strategy Parameters (Fibonacci Pivots) ---
ENABLE_FIB_PIVOT_ACTIONS = False # Master switch for Fib pivots
PIVOT_TIMEFRAME = "1d" # Timeframe for Pivot calculation (e.g., '1d', '1W')
FIB_LEVELS_TO_CALC = [0.382, 0.618, 1.0] # Fibonacci levels (based on H-L range)
FIB_NEAREST_COUNT = 5 # How many nearest levels to track
FIB_ENTRY_CONFIRM_PERCENT = 0.002 # Price must be within X% of a Fib support(long)/resistance(short)
FIB_EXIT_WARN_PERCENT = 0.0015 # Warn/Exit if price within Y% of Fib resistance(long)/support(short)
FIB_EXIT_ACTION = "warn" # Action on exit warning: "warn", "exit"

# --- Risk Management ---
# Stop Loss and Take Profit percentages relative to the entry price.
# E.g., 0.005 means 0.5%
STOP_LOSS_PCT = 0.005
TAKE_PROFIT_PCT = 0.01

# --- Risk Management (Dynamic) ---
ATR_MULTIPLIER_SL = 1.5 # Multiplier for ATR to set Stop Loss
ATR_MULTIPLIER_TP = 2.0 # Multiplier for ATR to set Take Profit

# --- Strategy Parameters (Trend Filter) ---
SMA_PERIOD = 8 # Period for Simple Moving Average (SMA) trend filter
ATR_PERIOD = 10 # Period for Average True Range (ATR) calculation

# --- API Configuration ---
# Bybit API endpoint and category.
# For live trading: "https://api.bybit.com"
# For testnet: "https://api-testnet.bybit.com"
BYBIT_API_ENDPOINT = "https://api.bybit.com" # <<< CHANGE TO LIVE API FOR REAL TRADING
BYBIT_CATEGORY = "linear" # Options: 'linear', 'inverse', 'spot'

# IMPORTANT: API_KEY and API_SECRET should NOT be hardcoded here.
# Store them in environment variables or a .env file (e.g., `BYBIT_API_KEY="your_key"`).
# The bybit_api.py script will load them from os.getenv().

# --- Bot Operational Settings ---
# Number of historical candles to fetch for indicator calculations.
# Ensure this is sufficient for your longest indicator period (e.g., StochRSI K period + pivot bars).
CANDLE_FETCH_LIMIT = 500

# How often the bot fetches new data and checks for signals (in seconds).
# Be mindful of Bybit's rate limits and your strategy's interval.
POLLING_INTERVAL_SECONDS = 5 # Poll every 5 seconds

# API request retry settings
API_REQUEST_RETRIES = 3
API_BACKOFF_FACTOR = 0.5
    
