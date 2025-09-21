from dataclasses import dataclass
import os

@dataclass
class BotConfig:
    # API Settings
    API_KEY: str = os.environ.get("BYBIT_API_KEY", "")
    API_SECRET: str = os.environ.get("BYBIT_API_SECRET", "")
    BYBIT_API_ENDPOINT: str = "https://api-testnet.bybit.com"
    API_RATE_LIMIT_CALLS: int = 60  # Number of API calls allowed
    API_RATE_LIMIT_PERIOD: int = 60  # Period in seconds for rate limit
    TESTNET: bool = True  # Set to False for live trading

    # Trading Parameters
    SYMBOL: str = "BTCUSDT"
    CATEGORY: str = "linear"

    # Strategy Parameters
    STRATEGY_NAME: str = "Supertrend"
    RISK_PER_TRADE_PERCENT: float = 0.5

    # Indicator Periods
    SUPER_TREND_PERIOD: int = 7
    SUPER_TREND_MULTIPLIER: float = 1.4
    EMA_SHORT_PERIOD: int = 9
    EMA_LONG_PERIOD: int = 21
    VOLUME_MA_PERIOD: int = 20
    RSI_PERIOD: int = 14
    ATR_PERIOD: int = 14

    # Entry Filters
    VOLUME_SPIKE_MULTIPLIER: float = 1.5
    RSI_CONFIRMATION_LEVEL: int = 50

    # Exit Strategy Parameters
    STOP_LOSS_ATR_MULTIPLIER: float = 0.75
    TAKE_PROFIT_ATR_MULTIPLIER: float = 1.0
    PARTIAL_PROFIT_PERCENT: float = 0.5
    PARTIAL_PROFIT_ATR_MULTIPLIER: float = 1.0

    MAX_TRADE_DURATION_BARS: int = 15
    BREAK_EVEN_PROFIT_ATR: float = 0.5
    TRAILING_STOP_ACTIVATION_BARS: int = 10
    TRAILING_STOP_ATR_MULTIPLIER: float = 0.5

    # Timeframes
    TF_1M: str = "1"
    TF_15M: str = "15"

    # Data Management
    MAX_DATAFRAME_SIZE: int = 5000  # Maximum rows to keep in DataFrame to prevent memory issues