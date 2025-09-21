from dataclasses import dataclass
import os
from decimal import Decimal

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
    SYMBOL: str = "TRUMPUSDT"  # The trading pair (e.g., "BTCUSDT", "ETHUSDT")
    CATEGORY: str = "linear"  # Options: 'linear', 'inverse', 'spot'
    INTERVAL: str = "1"        # Kline interval (e.g., "1", "5", "60", "D"). "1" for 1-minute.
    HEDGE_MODE: bool = True # Set to True if your Bybit account is in Hedge Mode.

<<<<<<< HEAD
    # Strategy Parameters
    STRATEGY_NAME: str = "Supertrend"
    RISK_PER_TRADE_PERCENT: float = 0.5
=======
    # Logging Settings
    LOG_LEVEL: str = "INFO"  # Options: "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
    LOG_FILE: str = "psg_bot.log"
>>>>>>> d9c9e718 (moto)

    # Strategy Selection
    STRATEGY_NAME: str = "EhlersSupertrendStrategy"

    # General Indicator Periods
    SMA_LENGTH: int = 20
    ATR_PERIOD: int = 10
    EHLERS_SUPERSMOOTHER_LENGTH: int = 10

    # Strategy Parameters: EhlersSupertrendStrategy
    EHLERS_PERIOD: int = 10
    SUPERTREND_PERIOD: int = 10
    SUPERTREND_MULTIPLIER: float = 3.0

    # Strategy Parameters: StochRSI_Fib_OB_Strategy
    STOCHRSI_K_PERIOD: int = 12
    STOCHRSI_D_PERIOD: int = 3
    STOCHRSI_OVERBOUGHT_LEVEL: int = 80
    STOCHRSI_OVERSOLD_LEVEL: int = 20
    USE_STOCHRSI_CROSSOVER: bool = True
    ENABLE_FIB_PIVOT_ACTIONS: bool = False
    PIVOT_TIMEFRAME: str = "1d"
    PIVOT_LEFT_BARS: int = 5
    PIVOT_RIGHT_BARS: int = 5
    MAX_ACTIVE_OBS: int = 10

<<<<<<< HEAD
    # Timeframes
    TF_1M: str = "1"
    TF_15M: str = "15"

    # Data Management
    MAX_DATAFRAME_SIZE: int = 5000  # Maximum rows to keep in DataFrame to prevent memory issues
=======
    # Risk Management
    STOP_LOSS_PCT: Decimal = Decimal('0.005')
    TAKE_PROFIT_PCT: Decimal = Decimal('0.01')
    ATR_MULTIPLIER_SL: Decimal = Decimal('1.5')
    ATR_MULTIPLIER_TP: Decimal = Decimal('2.0')

    # Bot Operational Settings
    CANDLE_FETCH_LIMIT: int = 500
    WARMUP_PERIOD: int = 50
    POLLING_INTERVAL_SECONDS: int = 5
    API_REQUEST_RETRIES: int = 3
    API_BACKOFF_FACTOR: float = 0.2
>>>>>>> d9c9e718 (moto)
