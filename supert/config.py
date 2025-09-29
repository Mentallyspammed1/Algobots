# config.py
# Configuration overrides for sb3.2.py

# This file allows you to override default settings used by the bot.
# Uncomment lines and modify values as needed.
# Environment variables (e.g., in .env file) take precedence over these settings
# if the corresponding variable is set in the environment.

# --- API Configuration ---
# BYBIT_API_KEY = "YOUR_API_KEY"
# BYBIT_API_SECRET = "YOUR_API_SECRET"
BYBIT_TESTNET = "false"  # Set to "true" to use Bybit testnet

# --- Trading Configuration ---
# BYBIT_SYMBOL = "BTCUSDT"
# BYBIT_CATEGORY = "linear" # Options: "linear", "spot", "inverse"
# BYBIT_LEVERAGE = "5" # Leverage for linear/inverse accounts

# --- Multi-timeframe Configuration ---
# PRIMARY_TIMEFRAME = "15" # Base timeframe for signals (e.g., "1", "5", "15", "60", "240", "D")
# SECONDARY_TIMEFRAMES = ["5", "60"] # Additional timeframes for confirmation
# LOOKBACK_PERIODS = "200" # Number of candles to fetch for initial indicator calculation

# --- Adaptive SuperTrend Parameters ---
# ST_PERIOD_BASE = "10" # Base period for SuperTrend calculation
# ST_MULTIPLIER_BASE = "3.0" # Base multiplier for SuperTrend
# ADAPTIVE_PARAMS = "true" # Enable adaptive SuperTrend parameters based on volatility

# --- Risk Management ---
# RISK_PER_TRADE_PCT = "1.0" # Percentage of equity to risk per trade (e.g., 1.0 for 1%)
# MAX_POSITION_SIZE_PCT = "30.0" # Maximum position size as a percentage of equity (e.g., 30.0 for 30%)
# STOP_LOSS_PCT = "1.5" # Default stop loss percentage if ATR stops are not used
# TAKE_PROFIT_PCT = "3.0" # Default take profit percentage if ATR stops are not used
# USE_ATR_STOPS = "true" # Use ATR for dynamic stop loss and take profit levels
# ATR_STOP_MULTIPLIER = "1.5" # Multiplier for ATR to determine stop loss distance
# ATR_TP_MULTIPLIER = "3.0" # Multiplier for ATR to determine take profit distance

# --- Daily Limits ---
# MAX_DAILY_LOSS_PCT = "5.0" # Maximum allowed daily loss percentage
# MAX_DAILY_TRADES = "10" # Maximum number of trades allowed per day
# MAX_CONSECUTIVE_LOSSES = "3" # Maximum number of consecutive losing trades before stopping
# MAX_DRAWDOWN_PCT = "10.0" # Maximum allowed drawdown percentage from peak equity

# --- Order Type & Execution ---
# ORDER_TYPE = "Market" # Options: "Market", "Limit"
# LIMIT_ORDER_OFFSET_PCT = "0.01" # Offset for limit orders (e.g., 0.01 for 0.01% better than market)
# POST_ONLY_LIMIT_ORDERS = "true" # Use post-only for limit orders to avoid taker fees

# --- Signal Filters ---
# ADX_TREND_FILTER = "true" # Enable ADX filter for trend confirmation
# ADX_MIN_THRESHOLD = "25" # Minimum ADX value to confirm a trend
# VOLUME_FILTER = "true" # Enable volume filter for signal confirmation
# VOLUME_MULTIPLIER = "1.5" # Volume must be this multiplier times the average volume
# RSI_FILTER = "true" # Enable RSI filter for overbought/oversold confirmation
# RSI_OVERSOLD = "30" # RSI value below which a buy signal might be considered
# RSI_OVERBOUGHT = "70" # RSI value above which a sell signal might be considered

# --- Market Structure ---
# USE_ORDER_BOOK = "true" # Enable order book imbalance analysis
# ORDER_BOOK_IMBALANCE_THRESHOLD = "0.6" # Threshold for order book imbalance (e.g., 0.6 for 60%)
# ORDER_BOOK_DEPTH_LEVELS = "10" # Number of levels to consider in the order book
# USE_VOLUME_PROFILE = "true" # Enable volume profile analysis

# --- Partial Take Profit ---
# PARTIAL_TP_ENABLED = "true" # Enable partial take profit orders
# PARTIAL_TP_TARGETS = [
#     {"profit_pct": "1.0", "close_qty_pct": "0.3"}, # Close 30% at 1% profit
#     {"profit_pct": "2.0", "close_qty_pct": "0.3"}, # Close another 30% at 2% profit
#     {"profit_pct": "3.0", "close_qty_pct": "0.4"}  # Close remaining 40% at 3% profit
# ]

# --- Breakeven & Trailing Stop ---
# BREAKEVEN_PROFIT_PCT = "0.5" # Profit percentage to activate breakeven stop loss
# BREAKEVEN_OFFSET_PCT = "0.01" # Offset from entry price for breakeven stop loss
# TRAILING_SL_ENABLED = "true" # Enable trailing stop loss
# TRAILING_SL_ACTIVATION_PCT = "1.0" # Profit percentage to activate trailing stop loss
# TRAILING_SL_DISTANCE_PCT = "0.5" # Distance (percentage) to trail the stop loss

# --- Performance & Logging ---
# LOG_LEVEL = "INFO" # Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL
# SAVE_TRADES_CSV = "true" # Save trade history to a CSV file
# TRADES_FILE = "trades_history.csv" # Filename for trade history
# STATE_FILE = "bot_state.pkl" # Filename for saving bot state
# SAVE_STATE_INTERVAL = "300" # Interval in seconds to save bot state

# --- Kelly Criterion ---
# USE_KELLY_SIZING = "false" # Use Kelly Criterion for position sizing
# KELLY_FRACTION_CAP = "0.25" # Maximum fraction of Kelly Criterion to use (e.g., 0.25 for 25%)
