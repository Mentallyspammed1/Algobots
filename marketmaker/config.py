import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # API Settings
    API_KEY = os.getenv('BYBIT_API_KEY')
    API_SECRET = os.getenv('BYBIT_API_SECRET')
    TESTNET = os.getenv('BYBIT_TESTNET', 'True').lower() == 'true'
    
    # Trading Parameters
    SYMBOL = 'TRUMPUSDT'
    CATEGORY = 'linear'  # 'linear' for USDT perpetual, 'inverse' for inverse contracts
    
    # Market Making Parameters
    BASE_SPREAD = 0.003  # 0.3% base spread (will be converted to bps in market_maker.py)
    MIN_SPREAD = 0.0005  # Minimum spread during low volatility
    MAX_SPREAD = 0.01    # Maximum spread during high volatility
    
    # New parameters for mm_bybit_batch_trailing.py compatibility
    MIN_SPREAD_TICKS = 1
    QUOTE_SIZE = 0.001 # Corresponds to MIN_ORDER_SIZE
    REPLACE_THRESHOLD_TICKS = 1
    REFRESH_MS = 400
    POST_ONLY = True
    MAX_NOTIONAL = 3000.0
    PROTECT_MODE = "trailing" # "trailing", "breakeven", or "off"
    TRAILING_DISTANCE = 50.0 # Absolute price distance for trailing stop
    TRAILING_ACTIVATE_PROFIT_BPS = 30.0
    BE_TRIGGER_BPS = 15.0
    BE_OFFSET_TICKS = 1
    LOG_EVERY_SECS = 10
    WS_PING_SECS = 20

    # Order Management (original parameters)
    ORDER_LEVELS = 5  # Number of bid/ask levels per batch
    MIN_ORDER_SIZE = 0.001  # Minimum order size in BTC
    MAX_ORDER_SIZE = 0.01   # Maximum order size in BTC
    ORDER_SIZE_INCREMENT = 0.002  # Size increment per level
    
    # Risk Management (original parameters)
    MAX_POSITION = 0.1  # Maximum position size
    INVENTORY_EXTREME = 0.8  # Threshold for inventory management
    STOP_LOSS_PCT = 0.02  # 2% stop loss
    TAKE_PROFIT_PCT = 0.01  # 1% take profit
    
    # Timing (original parameters)
    UPDATE_INTERVAL = 1  # Update orders every 1 second
    RECONNECT_DELAY = 5  # Reconnect delay in seconds
    
    # Volatility Settings (original parameters)
    VOLATILITY_WINDOW = 20  # Bollinger band window
    VOLATILITY_STD = 2  # Standard deviations for Bollinger bands

    # Backtester Settings (original parameters)
    INITIAL_CAPITAL: float = 10000.0
    START_DATE: str = "2025-08-20"
    END_DATE: str = "2025-08-21"
    INTERVAL: str = "1"  # 1, 3, 5, 15, 30, 60, 120, 240, 360, 720 minutes
    MAKER_FEE: float = 0.0002  # 0.02%
    TAKER_FEE: float = 0.0005  # 0.05%
    SLIPPAGE: float = 0.0001  # 0.01%
    USE_ORDERBOOK: bool = True
    ORDERBOOK_DEPTH: int = 50
    USE_WEBSOCKET: bool = False # Set to True for live trading with WebSocket