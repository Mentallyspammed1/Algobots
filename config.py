from decimal import Decimal

# =====================================================================================
# Pyrmethus's Ultra Scalper Bot (PSG) - Configuration File
#
# Note: For any settings related to API keys (e.g., BYBIT_API_KEY), please use
# a .env file in the root directory. The bot is designed to load these securely.
# Example .env file:
# BYBIT_API_KEY="YOUR_API_KEY"
# BYBIT_API_SECRET="YOUR_API_SECRET"
# =====================================================================================


# -------------------------------------------------------------------------------------
# [SECTION 1: CORE EXCHANGE & TRADING SETTINGS]
# -------------------------------------------------------------------------------------

# --- Exchange API Settings ---
# For live trading: "https://api.bybit.com"
# For testnet: "https://api-testnet.bybit.com"
BYBIT_API_ENDPOINT = "https://api.bybit.com"
BYBIT_CATEGORY = "linear"  # Options: 'linear', 'inverse', 'spot'

# --- Position Mode (CRITICAL) ---
# Set to True if your Bybit account is in Hedge Mode.
# If False, the bot assumes One-Way Mode.
HEDGE_MODE = True

# --- Trading Pair and Interval ---
SYMBOL = "TRUMPUSDT"  # The trading pair (e.g., "BTCUSDT", "ETHUSDT")
INTERVAL = "1"        # Kline interval (e.g., "1", "5", "60", "D"). "1" for 1-minute.


# -------------------------------------------------------------------------------------
# [SECTION 2: ORDER SIZING & RISK MANAGEMENT]
# -------------------------------------------------------------------------------------

# --- Order Sizing Strategy ---
# Set to True to use a percentage of your balance for each trade.
# If False, it will use the fixed USDT_AMOUNT_PER_TRADE below.
USE_PERCENTAGE_ORDER_SIZING = True

# The percentage of your available balance to use for each trade (if above is True).
# E.g., 1.0 means 1% of your available USDT balance.
ORDER_SIZE_PERCENT_OF_BALANCE = Decimal('3.0')

# Fixed USDT amount for trading (if USE_PERCENTAGE_ORDER_SIZING is False).
USDT_AMOUNT_PER_TRADE = Decimal('100.0')

# --- General Risk Management ---
# Default Stop Loss and Take Profit percentages (can be overridden by strategy).
# E.g., 0.005 means 0.5%
STOP_LOSS_PCT = Decimal('0.005')
TAKE_PROFIT_PCT = Decimal('0.01')

# --- Dynamic Risk Management (ATR-based) ---
# Multipliers for ATR to dynamically set Stop Loss and Take Profit.
ATR_MULTIPLIER_SL = Decimal('1.5')
ATR_MULTIPLIER_TP = Decimal('2.0')


# -------------------------------------------------------------------------------------
# [SECTION 3: STRATEGY SELECTION & PARAMETERS]
# -------------------------------------------------------------------------------------

# --- Active Strategy Selection ---
# Choose which strategy the bot will run.
# Make sure the corresponding parameters below are configured correctly.
STRATEGY_NAME = "EhlersSupertrendStrategy"
# Available Options:
# "EhlersSupertrendStrategy", "StochRSI_Fib_OB_Strategy", "SMA_Crossover_Strategy",
# "MarketMakingStrategy", "DUAL_SUPERTREND", "STOCHRSI_MOMENTUM", "EHLERS_FISHER", "EHLERS_MA_CROSS"


# --- General Indicator Periods ---
# These are used by multiple strategies or as general filters.
SMA_LENGTH = 20  # General purpose SMA length
ATR_PERIOD = 10  # General purpose ATR period
EHLERS_SUPERSMOOTHER_LENGTH = 10 # For Ehlers Super Smoother filter


# --- Strategy Parameters: EhlersSupertrendStrategy ---
EHLERS_PERIOD = 10
SUPERTREND_PERIOD = 10
SUPERTREND_MULTIPLIER = 3.0
# This strategy also uses SMA_LENGTH as a trend filter.


# --- Strategy Parameters: StochRSI_Fib_OB_Strategy ---
STOCHRSI_K_PERIOD = 12
STOCHRSI_D_PERIOD = 3
STOCHRSI_OVERBOUGHT_LEVEL = 80
STOCHRSI_OVERSOLD_LEVEL = 20
USE_STOCHRSI_CROSSOVER = True

ENABLE_FIB_PIVOT_ACTIONS = False
PIVOT_TIMEFRAME = "1d"
FIB_LEVELS_TO_CALC = [0.382, 0.618, 1.0]
FIB_NEAREST_COUNT = 5
FIB_ENTRY_CONFIRM_PERCENT = 0.002
FIB_EXIT_WARN_PERCENT = 0.0015
FIB_EXIT_ACTION = "warn"

PIVOT_LEFT_BARS = 5
PIVOT_RIGHT_BARS = 5
PIVOT_TOLERANCE_PCT = 0.002

MAX_ACTIVE_OBS = 10
OB_TOLERANCE_PCT = 0.001


# --- Strategy Parameters: MarketMakingStrategy ---
SPREAD_BPS = 22
USE_VOLATILITY_ADJUSTED_SIZE = True
BASE_ORDER_QUANTITY = "0.01"
VOLATILITY_SENSITIVITY = "0.5"
MAX_POSITION_SIZE = "0.05"
MAX_ORDER_QUANTITY = "0.1"
USE_DYNAMIC_SPREAD = True
ATR_SPREAD_MULTIPLIER = "0.5"
INVENTORY_SKEW_INTENSITY = "5.0"
USE_TREND_FILTER = True
SR_LEVEL_AVOIDANCE_BPS = 2
USE_ORDER_BLOCK_LOGIC = True
OB_AVOIDANCE_BPS = 1
REBALANCE_THRESHOLD = "0.05"
REBALANCE_AGGRESSIVENESS = 'MARKET'
USE_DYNAMIC_STOP_LOSS = True
STOP_LOSS_ATR_MULTIPLIER = "2.5"
HEDGE_RATIO = "0.2"
MAX_SPREAD_BPS = 50
MIN_ORDER_QUANTITY = "0.005"


# --- Strategy Parameters: DUAL_SUPERTREND ---
ST_ATR_LENGTH = 7
ST_MULTIPLIER = 2.5
CONFIRM_ST_ATR_LENGTH = 5
CONFIRM_ST_MULTIPLIER = 2.0


# --- Strategy Parameters: EHLERS_FISHER ---
EHLERS_FISHER_LENGTH = 10
EHLERS_FISHER_SIGNAL_PERIOD = 1


# --- Strategy Parameters: EHLERS_MA_CROSS ---
EHLERS_FAST_PERIOD = 10
# EHLERS_PERIOD is shared, defined in EhlersSupertrend section
EHLERS_SLOW_PERIOD = 30


# -------------------------------------------------------------------------------------
# [SECTION 4: BOT OPERATIONAL SETTINGS]
# -------------------------------------------------------------------------------------

# --- Data Fetching & Warmup ---
# Number of historical candles to fetch on startup.
CANDLE_FETCH_LIMIT = 500
# Number of candles to wait for before the bot starts trading.
WARMUP_PERIOD = 50

# --- Polling and API ---
# How often the bot checks for signals (in seconds).
POLLING_INTERVAL_SECONDS = 5
# API request retry settings.
API_REQUEST_RETRIES = 3
API_BACKOFF_FACTOR = 0.2

# --- Rate Limiting ---
# Internal rate limiter to avoid spamming the API.
API_RATE_LIMIT_CALLS = 10
API_RATE_LIMIT_PERIOD = 1
