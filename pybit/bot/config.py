import os

# --- CORE BOT SETTINGS ---
BOT_CONFIG = {
    "API_KEY": os.environ.get("BYBIT_API_KEY", "YOUR_API_KEY_HERE"),
    "API_SECRET": os.environ.get("BYBIT_API_SECRET", "YOUR_API_SECRET_HERE"),
    "TESTNET": False,
    "DRY_RUN": True,
    "LOG_LEVEL": "INFO", # DEBUG, INFO, WARNING, ERROR, CRITICAL
    "TIMEZONE": "America/Chicago",
    "MARKET_OPEN_HOUR": 0,  # 00:00 local time
    "MARKET_CLOSE_HOUR": 24, # 24:00 (i.e., always open)
    "LOOP_WAIT_TIME_SECONDS": 30, # How long to wait between main loop cycles
    "POSITION_RECONCILIATION_INTERVAL_MINUTES": 5, # How often to reconcile DB with exchange positions

    # --- TRADING PARAMETERS ---
    "TRADING_SYMBOLS": ["BTCUSDT", "ETHUSDT"], # Symbols to trade
    "TIMEFRAME": 15, # Trading timeframe in minutes (e.g., 1, 5, 15, 60)
    "MIN_KLINES_FOR_STRATEGY": 100, # Minimum klines required for indicator calculation

    # --- RISK MANAGEMENT ---
    "MAX_POSITIONS": 4, # Max number of concurrent open positions across all symbols
    "MAX_OPEN_ORDERS_PER_SYMBOL": 2, # Max open entry orders per symbol
    "EMERGENCY_STOP_IF_DOWN_PCT": 15, # Stop bot if equity drops by this percentage
    "RISK_PER_TRADE_PCT": 0.01, # % of capital to risk per trade (e.g., 0.01 = 1%)
    "MAX_NOTIONAL_PER_TRADE_USDT": 20, # Max USD value per trade to cap position size

    # --- TRADE MANAGEMENT & EXIT STRATEGIES ---
    "REWARD_RISK_RATIO": 2.5, # Target Take Profit / Stop Loss ratio for initial orders
    "MIN_BARS_BETWEEN_TRADES": 2, # Cooldown period (e.g., 4 * 15min = 1 hour)
    "MAX_HOLDING_CANDLES": 20, # Max candles to hold a position (e.g., 40 * 15min = 10 hours)
    "TRAILING_STOP_ACTIVE": True, # If True, chandelier exit will be used as a dynamic trailing stop
    "FIXED_PROFIT_TARGET_PCT": 0.03, # Percentage gain to trigger an early exit (e.g., 0.03 = 3%)

    # --- INDICATOR SETTINGS ---
    # Chandelier Exit (used for initial SL and trailing stop)
    "ATR_PERIOD": 14,
    "CHANDELIER_MULTIPLIER": 2.2, # Base multiplier for Chandelier Exit
    "MIN_ATR_MULTIPLIER": 1.5, # Min dynamic ATR multiplier for Chandelier
    "MAX_ATR_MULTIPLIER": 3.0, # Max dynamic ATR multiplier for Chandelier
    "VOLATILITY_LOOKBACK": 20, # Period for calculating price volatility for dynamic multiplier

    # EMA Crossover
    "TREND_EMA_PERIOD": 50, # Long-term EMA for overall trend filtering
    "EMA_SHORT_PERIOD": 9, # Short-term EMA for crossover
    "EMA_LONG_PERIOD": 21, # Long-term EMA for crossover

    # RSI
    "RSI_PERIOD": 14,
    "RSI_OVERBOUGHT": 70,
    "RSI_OVERSOLD": 30,

    # Volume Filter
    "VOLUME_MA_PERIOD": 20, # Moving average period for volume
    "VOLUME_THRESHOLD_MULTIPLIER": 1.5, # Volume above MA threshold for signal confirmation

    # Higher Timeframe Confirmation
    "HIGHER_TF_TIMEFRAME": 60, # Higher timeframe in minutes (e.g., 60 for 1-hour)
    "H_TF_EMA_SHORT_PERIOD": 8,
    "H_TF_EMA_LONG_PERIOD": 21,

    # Ehlers Supertrend & Fisher Transform
    "USE_EST_SLOW_FILTER": True, # Use Ehlers Supertrend as a slow trend filter for entry
    "EST_SLOW_LENGTH": 10,
    "EST_SLOW_MULTIPLIER": 2.0,
    "EHLERS_FISHER_PERIOD": 10,
    "USE_FISHER_EXIT": True, # Exit trade early if Fisher Transform flips against position

    # Stochastic Oscillator (New)
    "USE_STOCH_FILTER": False, # Enable/Disable Stochastic filter for entry
    "STOCH_K_PERIOD": 14,
    "STOCH_D_PERIOD": 3,
    "STOCH_SMOOTHING": 3,
    "STOCH_OVERBOUGHT": 80,
    "STOCH_OVERSOLD": 20,

    # MACD (New)
    "USE_MACD_FILTER": False, # Enable/Disable MACD filter for entry
    "MACD_FAST_PERIOD": 12,
    "MACD_SLOW_PERIOD": 26,
    "MACD_SIGNAL_PERIOD": 9,

    # ADX (New)
    "USE_ADX_FILTER": False, # Enable/Disable ADX filter for entry
    "ADX_PERIOD": 14,
    "ADX_THRESHOLD": 25, # Minimum ADX value for a strong trend confirmation

    # --- ORDER EXECUTION ---
    "MARGIN_MODE": 1, # 1 for isolated, 0 for cross
    "LEVERAGE": 15, # Leverage to use for trades
    "ORDER_TYPE": "Market", # "Market", "Limit", "Conditional"
    "POST_ONLY": True, # For Limit orders: ensure order is added to order book, not immediately executed
    "PRICE_DETECTION_THRESHOLD_PCT": 0.0005, # 0.05% proximity for limit orders near bid/ask
    "BREAKOUT_TRIGGER_PERCENT": 0.001, # 0.1% for conditional orders (e.g., trigger above market price)
    "ORDER_RETRY_ATTEMPTS": 3, # How many times to retry an order if API fails
    "ORDER_RETRY_DELAY_SECONDS": 2, # Delay between order retries
}
