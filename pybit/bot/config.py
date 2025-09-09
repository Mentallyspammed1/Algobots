# config.py
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Bot Configuration ---
BOT_CONFIG = {
    "API_KEY": os.getenv("BYBIT_API_KEY"),
    "API_SECRET": os.getenv("BYBIT_API_SECRET"),
    "TESTNET": os.getenv("BYBIT_TESTNET", "False").lower() == "true",
    "DRY_RUN": os.getenv("DRY_RUN", "True").lower() == "true",
    "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO").upper(),
    
    "TRADING_SYMBOLS": ["XLMUSDT", "TRUMPUSDT"], 
    "TIMEFRAME": 1, # in minutes
    "MARGIN_MODE": 1, # 0: Cross, 1: Isolated
    "LEVERAGE": 20,
    "ORDER_QTY_USDT": 10, # Quantity in USDT (e.g., $50 worth of crypto)
    "MAX_POSITIONS": 5,
    "MAX_OPEN_ORDERS_PER_SYMBOL": 2, # Max pending orders per symbol
    "TIMEZONE": 'America/Chicago',
    "MARKET_OPEN_HOUR": "4",
    "MARKET_CLOSE_HOUR": "3",
    "LOOP_WAIT_TIME_SECONDS": 15, # How long to wait between main loop cycles
    "MIN_KLINES_FOR_STRATEGY": 100, # Minimum klines needed for indicator calculation
    "PRICE_DETECTION_THRESHOLD_PCT": 0.005, # 0.5% threshold for current price near support/resistance

    # --- Chandelier Exit Scalping Strategy Parameters ---
    "ATR_PERIOD": 12,
    "CHANDELIER_MULTIPLIER": 1.2,
    "MIN_ATR_MULTIPLIER": 0.8, # For dynamic multiplier
    "MAX_ATR_MULTIPLIER": 2.2, # For dynamic multiplier
    "TREND_EMA_PERIOD": 22, # For overall trend filter
    "EMA_SHORT_PERIOD": 8, # For entry EMA crossover
    "EMA_LONG_PERIOD": 12, # For entry EMA crossover
    "RSI_PERIOD": 8,
    "RSI_OVERBOUGHT": 66,
    "RSI_OVERSOLD": 33,
    "VOLUME_THRESHOLD_MULTIPLIER": 1.2, # Volume spike threshold (e.g., 1.5x 20-period MA)
    "RISK_PER_TRADE_PCT": 0.005, # 0.5% of capital risked per trade (for position sizing)
    "REWARD_RISK_RATIO": 2.2, # Take Profit at 2x Stop Loss distance
    "MAX_HOLDING_CANDLES": 5, # Max candles to hold a trade before considering closing (for live bot, this implies checking and closing if not exited by TP/SL)


    # --- Ehlers Supertrend Parameters ---
    # These parameters define the sensitivity and behavior of the Supertrend indicator.
    # Fast Supertrend: More responsive, used for entry signals.
    "EST_FAST_LENGTH": 5,          # Lookback period for the fast Supertrend's ATR calculation.
    "EST_FAST_MULTIPLIER": 2.2,     # Multiplier for the fast Supertrend's ATR. Higher values reduce sensitivity.

    # Slow Supertrend: Less responsive, used for trend confirmation and as a trailing stop base.
    "EST_SLOW_LENGTH": 8,          # Lookback period for the slow Supertrend's ATR calculation.
    "EST_SLOW_MULTIPLIER": 1.2,     # Multiplier for the slow Supertrend's ATR.

    # --- ATR-based TP/SL Settings ---
    "USE_ATR_FOR_TP_SL": False, # Set to True to use ATR for TP/SL calculation
    "TP_ATR_MULTIPLIER": 1.5,    # Multiplier for ATR to determine Take Profit distance
    "SL_ATR_MULTIPLIER": 1.0,    # Multiplier for ATR to determine Stop Loss distance

    # --- Ehlers Fisher Transform Settings ---
    "EHLERS_FISHER_PERIOD": 8, # Period for Ehlers Fisher Transform (common values: 9, 10)

    # --- RSI Confirmation Thresholds (for new signal logic) ---
    "RSI_CONFIRM_LONG_THRESHOLD": 55, # RSI must be above this for long confirmations (e.g., 55)
    "RSI_CONFIRM_SHORT_THRESHOLD": 45, # RSI must be below this for short confirmations (e.g., 45)
}
