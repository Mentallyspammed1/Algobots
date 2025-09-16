
# config.py

import os
from dataclasses import dataclass, field


@dataclass
class Config:
    """Bot configuration parameters."""

    # --- API Credentials ---
    # It's recommended to load these from environment variables or a secure vault
    BYBIT_API_KEY: str = os.getenv('BYBIT_API_KEY', '')
    BYBIT_API_SECRET: str = os.getenv('BYBIT_API_SECRET', '')
    TESTNET: bool = os.getenv('BYBIT_TESTNET', 'True').lower() == 'true'

    # --- Trading Parameters ---
    SYMBOL: str = 'BTCUSDT'              # The trading pair
    CATEGORY: str = 'linear'             # 'spot', 'linear', 'inverse', 'option'
    LEVERAGE: float = 10.0               # Desired leverage for derivatives
    ORDER_SIZE_USD_VALUE: float = 100.0  # Desired order value in USD (e.g., 100 USDT). Used for market making or fixed size entry.
    SPREAD_PERCENTAGE: float = 0.0005    # 0.05% spread for market making (0.0005 for 0.05%)

    # --- Risk Management ---
    RISK_PER_TRADE_PERCENT: float = 1.0  # 1% of account balance risked per trade
    MAX_POSITION_SIZE_QUOTE_VALUE: float = 5000.0 # Max allowed absolute position size in quote currency value (e.g., USDT)
    MAX_OPEN_ORDERS_PER_SIDE: int = 1    # Max active limit orders on one side
    ORDER_REPRICE_THRESHOLD_PCT: float = 0.0002 # % price change to trigger order repricing (0.02%)
    MIN_STOP_LOSS_DISTANCE_RATIO: float = 0.0005 # 0.05% of price, minimum stop loss distance to prevent too small stops (Decimal('0.0005'))
    MAX_DAILY_DRAWDOWN_PERCENT: float = 10.0 # 10% max drawdown in a single day, bot pauses if hit (Decimal('10.0'))

    # --- Trailing Stop Loss (TSL) ---
    TRAILING_STOP_ENABLED: bool = True
    TSL_ACTIVATION_PROFIT_PERCENT: float = 0.5  # 0.5% profit before TSL activates (percentage of entry price)
    TSL_TRAIL_PERCENT: float = 0.5             # 0.5% distance for trailing (percentage of highest/lowest profit point)
    TSL_TYPE: str = "PERCENTAGE"               # "PERCENTAGE", "ATR", "CHANDELIER"
    TSL_ATR_MULTIPLIER: float = 2.0            # Multiplier for ATR-based TSL (e.g., 2.0 * ATR)
    TSL_CHANDELIER_MULTIPLIER: float = 3.0     # Multiplier for Chandelier Exit
    TSL_CHANDELIER_PERIOD: int = 22            # Period for highest high/lowest low in Chandelier Exit calculation

    # --- Strategy & Loop Control ---
    TRADING_LOGIC_LOOP_INTERVAL_SECONDS: float = 5.0 # Frequency of running trading logic
    API_RETRY_DELAY_SECONDS: float = 3             # Delay before retrying failed HTTP API calls
    RECONNECT_DELAY_SECONDS: float = 5             # Delay before WebSocket reconnection
    ORDERBOOK_DEPTH_LIMIT: int = 25                # Depth for orderbook subscription
    BYBIT_TIMEZONE: str = "America/Chicago"        # Timezone for consistent datetime objects

    # --- Market Data Fetching (Historical) ---
    KLINES_LOOKBACK_LIMIT: int = 500 # Number of klines to fetch for indicators (e.g., last 500 candles)
    KLINES_INTERVAL: str = '15'      # Interval for kline data used in main strategy ('1', '5', '15', '60', etc.)
    KLINES_HISTORY_WINDOW_MINUTES: int = 60 * 24 * 7 # Fetch klines covering 1 week of history (in minutes), to ensure sufficient data for all indicators

    # --- Strategy Selection ---
    ACTIVE_STRATEGY_MODULE: str = "default_strategy" # Name of the strategy module (e.g., 'default_strategy')
    ACTIVE_STRATEGY_CLASS: str = "DefaultStrategy"   # Name of the class within that module

    # --- Market Analyzer Settings ---
    MARKET_ANALYZER_ENABLED: bool = True
    TREND_DETECTION_PERIOD: int = 50                 # Period for moving average in trend detection
    VOLATILITY_DETECTION_ATR_PERIOD: int = 14        # Period for ATR in volatility detection
    VOLATILITY_THRESHOLD_HIGH: float = 1.5           # ATR > 1.5 * recent_ATR_avg => HIGH volatility
    VOLATILITY_THRESHOLD_LOW: float = 0.5            # ATR < 0.5 * recent_ATR_avg => LOW volatility
    ADX_PERIOD: int = 14                             # Period for ADX calculation
    ADX_TREND_STRONG_THRESHOLD: int = 25             # ADX > 25 => Strong trend
    ADX_TREND_WEAK_THRESHOLD: int = 20               # ADX < 20 => Weak/No trend
    ANOMALY_DETECTOR_ROLLING_WINDOW: int = 50        # Rolling window for anomaly detection (e.g., volume spikes)
    ANOMALY_DETECTOR_THRESHOLD_STD: float = 3.0      # Number of standard deviations for anomaly threshold

    # --- Logger Settings ---
    LOG_LEVEL: str = "INFO"                      # DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_FILE_PATH: str = "bot_logs/trading_bot.log"

    # --- Advanced Data Structures ---
    USE_SKIP_LIST_FOR_ORDERBOOK: bool = True # True for OptimizedSkipList, False for EnhancedHeap

    # --- Internal State Tracking (can be persisted) ---
    INITIAL_ACCOUNT_BALANCE: float = 1000.0 # Starting balance for PnL calculations

    # --- Performance Metrics Export ---
    TRADE_HISTORY_CSV: str = "bot_logs/trade_history.csv"
    DAILY_METRICS_CSV: str = "bot_logs/daily_metrics.csv"

    # --- UI/Colorama Settings ---
    NEON_GREEN: str = '\033[92m'
    NEON_BLUE: str = '\033[96m'
    NEON_PURPLE: str = '\033[95m'
    NEON_YELLOW: str = '\033[93m'
    NEON_RED: str = '\033[91m'
    NEON_CYAN: str = '\033[96m'
    RESET: str = '\033[0m'
    INDICATOR_COLORS: dict[str, str] = field(default_factory=lambda: {
        "SMA_10": '\033[94m', "SMA_Long": '\033[34m', "EMA_Short": '\033[95m',
        "EMA_Long": '\033[35m', "ATR": '\033[93m', "RSI": '\033[92m',
        "StochRSI_K": '\033[96m', "StochRSI_D": '\033[36m', "BB_Upper": '\033[91m',
        "BB_Middle": '\033[97m', "BB_Lower": '\033[91m', "CCI": '\033[92m',
        "WR": '\033[91m', "MFI": '\033[92m', "OBV": '\033[94m',
        "OBV_EMA": '\033[96m', "CMF": '\033[95m', "Tenkan_Sen": '\033[96m',
        "Kijun_Sen": '\033[36m', "Senkou_Span_A": '\033[92m', "Senkou_Span_B": '\033[91m',
        "Chikou_Span": '\033[93m', "PSAR_Val": '\033[95m', "PSAR_Dir": '\033[35m',
        "VWAP": '\033[97m', "ST_Fast_Dir": '\033[94m', "ST_Fast_Val": '\033[96m',
        "ST_Slow_Dir": '\033[95m', "ST_Slow_Val": '\033[35m', "MACD_Line": '\033[92m',
        "MACD_Signal": '\033[92m', "MACD_Hist": '\033[93m', "ADX": '\033[96m',
        "PlusDI": '\033[36m', "MinusDI": '\033[91m',
    })

    # --- Gemini AI Configuration ---
    GEMINI_AI_ENABLED: bool = os.getenv('GEMINI_AI_ENABLED', 'False').lower() == 'true'
    GEMINI_API_KEY: str = os.getenv('GEMINI_API_KEY', '')
    GEMINI_MODEL: str = "gemini-1.5-flash-latest" # Using default for now as per no scikit/scipy rule
    GEMINI_MIN_CONFIDENCE_FOR_OVERRIDE: int = 60  # Minimum AI confidence (0-100)
    GEMINI_RATE_LIMIT_DELAY_SECONDS: float = 1.0
    GEMINI_CACHE_TTL_SECONDS: int = 300
    GEMINI_DAILY_API_LIMIT: int = 1000
    GEMINI_SIGNAL_WEIGHTS: dict[str, float] = field(default_factory=lambda: {"technical": 0.6, "ai": 0.4})
    GEMINI_LOW_AI_CONFIDENCE_THRESHOLD: int = 20
    GEMINI_CHART_IMAGE_ANALYSIS_ENABLED: bool = False # Requires matplotlib and can be API intensive
    GEMINI_CHART_IMAGE_FREQUENCY_LOOPS: int = 100 # Analyze every N loops
    GEMINI_CHART_IMAGE_DATA_POINTS: int = 100 # Candles for chart image

    # --- Alert System Settings ---
    ALERT_TELEGRAM_ENABLED: bool = os.getenv('ALERT_TELEGRAM_ENABLED', 'False').lower() == 'true'
    ALERT_TELEGRAM_BOT_TOKEN: str = os.getenv('ALERT_TELEGRAM_BOT_TOKEN', '')
    ALERT_TELEGRAM_CHAT_ID: str = os.getenv('ALERT_TELEGRAM_CHAT_ID', '') # Use @get_id_bot on Telegram
    ALERT_CRITICAL_LEVEL: str = "WARNING" # Minimum level to send external alerts (INFO, WARNING, ERROR, CRITICAL)
    ALERT_COOLDOWN_SECONDS: int = 300 # 5 minutes cooldown between similar alerts

    # --- Dynamic Configuration Reloading ---
    CONFIG_RELOAD_INTERVAL_SECONDS: int = 3600 # Reload config file every hour
    LAST_CONFIG_RELOAD_TIME: float = 0.0

    # --- Strategy-Specific Parameters (example, DefaultStrategy uses these) ---
    STRATEGY_EMA_FAST_PERIOD: int = 9
    STRATEGY_EMA_SLOW_PERIOD: int = 21
    STRATEGY_RSI_PERIOD: int = 14
    STRATEGY_RSI_OVERSOLD: float = 30
    STRATEGY_RSI_OVERBOUGHT: float = 70
    STRATEGY_MACD_FAST_PERIOD: int = 12
    STRATEGY_MACD_SLOW_PERIOD: int = 26
    STRATEGY_MACD_SIGNAL_PERIOD: int = 9
    STRATEGY_BB_PERIOD: int = 20
    STRATEGY_BB_STD: float = 2.0
    STRATEGY_ATR_PERIOD: int = 14
    STRATEGY_ADX_PERIOD: int = 14
    STRATEGY_BUY_SCORE_THRESHOLD: float = 1.0
    STRATEGY_SELL_SCORE_THRESHOLD: float = -1.0


