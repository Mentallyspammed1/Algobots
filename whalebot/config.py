# config.py

import os
from dataclasses import dataclass, field


@dataclass
class Config:
    """Bot configuration parameters."""

    # --- API Credentials ---
    BYBIT_API_KEY: str = os.getenv("BYBIT_API_KEY", "")
    BYBIT_API_SECRET: str = os.getenv("BYBIT_API_SECRET", "")
    TESTNET: bool = os.getenv("BYBIT_TESTNET", "True").lower() == "true"

    # --- Trading Parameters ---
    SYMBOL: str = "BTCUSDT"
    CATEGORY: str = "linear"
    LEVERAGE: float = 10.0
    ORDER_SIZE_USD_VALUE: float = 100.0
    SPREAD_PERCENTAGE: float = 0.0005

    # --- Risk Management ---
    RISK_PER_TRADE_PERCENT: float = 1.0
    MAX_POSITION_SIZE_QUOTE_VALUE: float = 5000.0
    MAX_OPEN_ORDERS_PER_SIDE: int = 1
    ORDER_REPRICE_THRESHOLD_PCT: float = 0.0002
    MIN_STOP_LOSS_DISTANCE_RATIO: float = 0.0005
    MAX_DAILY_DRAWDOWN_PERCENT: float = 10.0

    # --- Trailing Stop Loss (TSL) ---
    TRAILING_STOP_ENABLED: bool = True
    TSL_ACTIVATION_PROFIT_PERCENT: float = 0.5
    TSL_TRAIL_PERCENT: float = 0.5
    TSL_TYPE: str = "PERCENTAGE"
    TSL_ATR_MULTIPLIER: float = 2.0
    TSL_CHANDELIER_MULTIPLIER: float = 3.0
    TSL_CHANDELIER_PERIOD: int = 22

    # --- Strategy & Loop Control ---
    TRADING_LOGIC_LOOP_INTERVAL_SECONDS: float = 5.0
    API_RETRY_DELAY_SECONDS: float = 3
    RECONNECT_DELAY_SECONDS: float = 5
    ORDERBOOK_DEPTH_LIMIT: int = 25
    BYBIT_TIMEZONE: str = "America/Chicago"

    # --- Market Data Fetching (Historical) ---
    KLINES_LOOKBACK_LIMIT: int = 500
    KLINES_INTERVAL: str = "15"
    KLINES_HISTORY_WINDOW_MINUTES: int = 60 * 24 * 7

    # --- Strategy Selection ---
    ACTIVE_STRATEGY_MODULE: str = "default_strategy"
    ACTIVE_STRATEGY_CLASS: str = "DefaultStrategy"

    # --- Market Analyzer Settings ---
    MARKET_ANALYZER_ENABLED: bool = True
    TREND_DETECTION_PERIOD: int = 50
    VOLATILITY_DETECTION_ATR_PERIOD: int = 14
    VOLATILITY_THRESHOLD_HIGH: float = 1.5
    VOLATILITY_THRESHOLD_LOW: float = 0.5
    ADX_PERIOD: int = 14
    ADX_TREND_STRONG_THRESHOLD: int = 25
    ADX_TREND_WEAK_THRESHOLD: int = 20
    ANOMALY_DETECTOR_ROLLING_WINDOW: int = 50
    ANOMALY_DETECTOR_THRESHOLD_STD: float = 3.0

    # --- Logger Settings ---
    LOG_LEVEL: str = "INFO"
    LOG_FILE_PATH: str = "bot_logs/trading_bot.log"

    # --- Advanced Data Structures ---
    USE_SKIP_LIST_FOR_ORDERBOOK: bool = True

    # --- Internal State Tracking (can be persisted) ---
    INITIAL_ACCOUNT_BALANCE: float = 1000.0

    # --- Performance Metrics Export ---
    TRADE_HISTORY_CSV: str = "bot_logs/trade_history.csv"
    DAILY_METRICS_CSV: str = "bot_logs/daily_metrics.csv"

    # --- UI/Colorama Settings ---
    NEON_GREEN: str = "\033[92m"
    NEON_BLUE: str = "\033[96m"
    NEON_PURPLE: str = "\033[95m"
    NEON_YELLOW: str = "\033[93m"
    NEON_RED: str = "\033[91m"
    NEON_CYAN: str = "\033[96m"
    RESET: str = "\033[0m"
    INDICATOR_COLORS: dict[str, str] = field(
        default_factory=lambda: {
            "SMA_10": "\033[94m",
            "SMA_Long": "\033[34m",
            "EMA_Short": "\033[95m",
            "EMA_Long": "\033[35m",
            "ATR": "\033[93m",
            "RSI": "\033[92m",
            "StochRSI_K": "\033[96m",
            "StochRSI_D": "\033[36m",
            "BB_Upper": "\033[91m",
            "BB_Middle": "\033[97m",
            "BB_Lower": "\033[91m",
            "CCI": "\033[92m",
            "WR": "\033[91m",
            "MFI": "\033[92m",
            "OBV": "\033[94m",
            "OBV_EMA": "\033[96m",
            "CMF": "\033[95m",
            "Tenkan_Sen": "\033[96m",
            "Kijun_Sen": "\033[36m",
            "Senkou_Span_A": "\033[92m",
            "Senkou_Span_B": "\033[91m",
            "Chikou_Span": "\033[93m",
            "PSAR_Val": "\033[95m",
            "PSAR_Dir": "\033[35m",
            "VWAP": "\033[97m",
            "ST_Fast_Dir": "\033[94m",
            "ST_Fast_Val": "\033[96m",
            "ST_Slow_Dir": "\033[95m",
            "ST_Slow_Val": "\033[35m",
            "MACD_Line": "\033[92m",
            "MACD_Signal": "\033[92m",
            "MACD_Hist": "\033[93m",
            "ADX": "\033[96m",
            "PlusDI": "\033[36m",
            "MinusDI": "\033[91m",
        },
    )

    # --- Gemini AI Configuration ---
    GEMINI_AI_ENABLED: bool = os.getenv("GEMINI_AI_ENABLED", "False").lower() == "true"
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = "gemini-1.5-flash-latest"
    GEMINI_MIN_CONFIDENCE_FOR_OVERRIDE: int = 60
    GEMINI_RATE_LIMIT_DELAY_SECONDS: float = 1.0
    GEMINI_CACHE_TTL_SECONDS: int = 300
    GEMINI_DAILY_API_LIMIT: int = 1000
    GEMINI_SIGNAL_WEIGHTS: dict[str, float] = field(
        default_factory=lambda: {"technical": 0.6, "ai": 0.4},
    )
    GEMINI_LOW_AI_CONFIDENCE_THRESHOLD: int = 20
    GEMINI_CHART_IMAGE_ANALYSIS_ENABLED: bool = False
    GEMINI_CHART_IMAGE_FREQUENCY_LOOPS: int = 100
    GEMINI_CHART_IMAGE_DATA_POINTS: int = 100

    # --- Alert System Settings ---
    ALERT_TELEGRAM_ENABLED: bool = (
        os.getenv("ALERT_TELEGRAM_ENABLED", "False").lower() == "true"
    )
    ALERT_TELEGRAM_BOT_TOKEN: str = os.getenv("ALERT_TELEGRAM_BOT_TOKEN", "")
    ALERT_TELEGRAM_CHAT_ID: str = os.getenv("ALERT_TELEGRAM_CHAT_ID", "")
    ALERT_CRITICAL_LEVEL: str = "WARNING"
    ALERT_COOLDOWN_SECONDS: int = 300

    # --- Dynamic Configuration Reloading ---
    CONFIG_RELOAD_INTERVAL_SECONDS: int = 3600
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
