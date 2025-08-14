from decimal import Decimal

# config.py

# --- Exchange Settings ---
# For live trading: "https://api.bybit.com"
# For testnet: "https://api-testnet.bybit.com"
BYBIT_API_ENDPOINT = "https://api.bybit.com"
BYBIT_CATEGORY = "linear"  # Options: 'linear', 'inverse', 'spot'

# --- Position Mode (IMPORTANT) ---
# Set to True if your Bybit account is in Hedge Mode for the selected category.
# If True, the bot automatically uses positionIdx=1 for buys and positionIdx=2 for sells.
# If False (default), the bot assumes One-Way Mode.
HEDGE_MODE = True

# --- Trading Parameters ---
SYMBOL = "TRUMPUSDT"  # The trading pair (e.g., "BTCUSDT", "ETHUSDT")
INTERVAL = "1"      # Kline interval (e.g., "1", "5", "15", "60", "D"). "1" for 1-minute.

# --- Order Sizing Configuration ---
# Set to True to use a percentage of your balance for each trade.
# If False, it will use the fixed USDT_AMOUNT_PER_TRADE below.
USE_PERCENTAGE_ORDER_SIZING = True
# The percentage of your available balance to use for each trade.
# E.g., 1.0 means 1% of your available USDT balance.
# This is only used if USE_PERCENTAGE_ORDER_SIZING is True.
ORDER_SIZE_PERCENT_OF_BALANCE = Decimal('3.0')

# Fixed USDT amount for trading. Only used if USE_PERCENTAGE_ORDER_SIZING is False.
USDT_AMOUNT_PER_TRADE = Decimal('100.0')

# --- Strategy Selection ---
STRATEGY_NAME = "EhlersSupertrendStrategy" # Options: "StochRSI_Fib_OB_Strategy", "SMA_Crossover_Strategy", "DUAL_SUPERTREND", "STOCHRSI_MOMENTUM", "EHLERS_FISHER", "EHLERS_MA_CROSS"

# --- Strategy Parameters (Market Making) ---
# Base spread in BPS (Basis Points). 10 BPS = 0.1%.
SPREAD_BPS = 22
# Use order size adjusted for volatility
USE_VOLATILITY_ADJUSTED_SIZE = True
# Base quantity for orders (e.g., 0.01 BTC)
BASE_ORDER_QUANTITY = "0.01" # Keep as string for Decimal conversion in strategy
# How sensitive order size is to volatility (higher value = smaller orders in volatile markets)
VOLATILITY_SENSITIVITY = "0.5" # Keep as string for Decimal conversion in strategy
# Maximum total position size the bot should hold
MAX_POSITION_SIZE = "0.05" # Keep as string for Decimal conversion in strategy
# Maximum quantity for a single order
MAX_ORDER_QUANTITY = "0.1" # Keep as string for Decimal conversion in strategy
# Use dynamic spread adjustment based on ATR
USE_DYNAMIC_SPREAD = True
# Multiplier for ATR when calculating dynamic spread (higher = wider spread)
ATR_SPREAD_MULTIPLIER = "0.5" # Keep as string for Decimal conversion in strategy
# Intensity of inventory skewing (higher = more aggressive skew to rebalance)
INVENTORY_SKEW_INTENSITY = "5.0" # Keep as string for Decimal conversion in strategy
# Use trend filter to skew prices
USE_TREND_FILTER = True
# Avoidance zone around S/R levels in BPS (e.g., 2 BPS = 0.02%)
SR_LEVEL_AVOIDANCE_BPS = 2
# Use Order Block avoidance logic
USE_ORDER_BLOCK_LOGIC = True
# Avoidance zone around Order Blocks in BPS (e.g., 1 BPS = 0.01%)
OB_AVOIDANCE_BPS = 1
# Position size threshold to trigger rebalancing
REBALANCE_THRESHOLD = "0.05" # Keep as string for Decimal conversion in strategy
# Aggressiveness of rebalancing orders: 'MARKET' or 'AGGRESSIVE_LIMIT'
REBALANCE_AGGRESSIVENESS = 'MARKET'
# Use dynamic stop loss based on ATR
USE_DYNAMIC_STOP_LOSS = True
# Multiplier for ATR when calculating dynamic stop loss
STOP_LOSS_ATR_MULTIPLIER = "2.5" # Keep as string for Decimal conversion in strategy
# Ratio of position to hedge (e.g., 0.2 means hedge 20% of position)
HEDGE_RATIO = "0.2" # Keep as string for Decimal conversion in strategy
# Maximum allowed dynamic spread in BPS
MAX_SPREAD_BPS = 50
# Minimum order quantity allowed
MIN_ORDER_QUANTITY = "0.005" # Keep as string for Decimal conversion in strategy


# --- Strategy Parameters (Dual Supertrend) ---
ST_ATR_LENGTH = 7
ST_MULTIPLIER = 2.5
CONFIRM_ST_ATR_LENGTH = 5
CONFIRM_ST_MULTIPLIER = 2.0

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

# --- Strategy Parameters (Ehlers Fisher Transform) ---
EHLERS_FISHER_LENGTH = 10
EHLERS_FISHER_SIGNAL_PERIOD = 1

# --- Strategy Parameters (Fibonacci Pivots) ---
ENABLE_FIB_PIVOT_ACTIONS = False # Master switch for Fib pivots
PIVOT_TIMEFRAME = "1d" # Timeframe for Pivot calculation (e.g., '1d', '1W')
FIB_LEVELS_TO_CALC = [0.382, 0.618, 1.0] # Fibonacci levels (based on H-L range)
FIB_NEAREST_COUNT = 5 # How many nearest levels to track
FIB_ENTRY_CONFIRM_PERCENT = 0.002 # Price must be within X% of a Fib support(long)/resistance(short)
FIB_EXIT_WARN_PERCENT = 0.0015 # Warn/Exit if price within Y% of Fib resistance(long)/support(short)
FIB_EXIT_ACTION = "warn" # Action on exit warning: "warn", "exit"

# --- Strategy Parameters (Ehlers MA Cross) ---
EHLERS_FAST_PERIOD = 10
EHLERS_PERIOD = 10
EHLERS_SLOW_PERIOD = 30

# --- Strategy Parameters (Ehlers Supertrend) ---
EHLERS_PERIOD = 10
SUPERTREND_PERIOD = 10
SUPERTREND_MULTIPLIER = 3.0

# --- Risk Management (General - may be overridden by strategy specifics) ---
# Stop Loss and Take Profit percentages relative to the entry price.
# E.g., 0.005 means 0.5%
STOP_LOSS_PCT = Decimal('0.005')
TAKE_PROFIT_PCT = Decimal('0.01')

# --- Risk Management (Dynamic - may be overridden by strategy specifics) ---
ATR_MULTIPLIER_SL = Decimal('1.5') # Multiplier for ATR to set Stop Loss (for general use)
ATR_MULTIPLIER_TP = Decimal('2.0') # Multiplier for ATR to set Take Profit (for general use)

# --- Strategy Parameters (Trend Filter) ---
SMA_PERIOD = 8 # Period for Simple Moving Average (SMA) trend filter
SMA_LENGTH = 20 # Period for Simple Moving Average (SMA) calculation
ATR_PERIOD = 10 # Period for Average True Range (ATR) calculation

# --- Strategy Parameters (Ehlers Super Smoother) ---
EHLERS_SUPERSMOOTHER_LENGTH = 10 # Period for Ehlers Super Smoother

# --- Order Block Settings ---
MAX_ACTIVE_OBS = 10 # Maximum number of active Order Blocks to track
OB_TOLERANCE_PCT = 0.001 # Percentage tolerance for price proximity to Order Blocks


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

# Number of candles to wait for before the bot starts trading.
# This ensures that indicators like ATR have enough data to be accurate.
WARMUP_PERIOD = 50

# How often the bot fetches new data and checks for signals (in seconds).
# Be mindful of Bybit's rate limits and your strategy's interval.
POLLING_INTERVAL_SECONDS = 5 # Poll every 5 seconds

# API request retry settings
API_REQUEST_RETRIES = 3
API_BACKOFF_FACTOR = 0.2

# --- Rate Limiting ---
API_RATE_LIMIT_CALLS = 10  # Max API calls per period
API_RATE_LIMIT_PERIOD = 1  # Period in seconds for rate limiting

# Receive window for API requests (in milliseconds).
# Per Bybit's error message, this should be 5000.
RECV_WINDOW = 5000
