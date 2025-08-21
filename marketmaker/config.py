from dataclasses import dataclass
from dataclasses import dataclass
from dataclasses import dataclass
from dataclasses import dataclass
import os
from dotenv import load_dotenv
from decimal import Decimal # Import Decimal for precise financial calculations

load_dotenv()

@dataclass
class Config:
    # API Settings
    API_KEY = os.getenv('BYBIT_API_KEY')
    API_SECRET = os.getenv('BYBIT_API_SECRET')
    TESTNET = os.getenv('BYBIT_TESTNET', 'True').lower() == 'true'
    
    # Trading Parameters
    SYMBOL = 'TRUMPUSDT'
    CATEGORY = 'linear'  # 'linear' for USDT perpetual, 'inverse' for inverse contracts
    
    # Market Making Parameters (aligned with mm_bybit_batch_trailing.py)
    BASE_SPREAD_BPS = 20 # 0.2% base spread (20 bps each side => 40 bps wide) - converted from 0.002
    MIN_SPREAD_TICKS = 1
    QUOTE_SIZE = Decimal("0.001")  # contract size or base asset units for spot
    REPLACE_THRESHOLD_TICKS = 1
    REFRESH_MS = 400 # Minimum ms between quote checks (formerly UPDATE_INTERVAL)
    POST_ONLY = True

    # Inventory/Risk (aligned with mm_bybit_batch_trailing.py)
    MAX_POSITION = Decimal("0.02") # Max net position in units (e.g., BTC amount)
    MAX_NOTIONAL = Decimal("3000") # Max notional value for a single order
    RISK_PER_TRADE_PCT: float = 0.005 # 0.5% risk per trade for dynamic sizing
    LEVERAGE: int = 5 # Leverage for dynamic sizing (if applicable)
    
    # Protection mode: "trailing", "breakeven", or "off"
    PROTECT_MODE = "trailing"
    # Trailing stop config (price distance; same currency as symbol)
    TRAILING_DISTANCE = Decimal("50") # e.g., $50 for BTCUSDT (absolute price distance)
    # Activate the trailing stop only when in profit by this many bps from entry (0 = always on)
    TRAILING_ACTIVATE_PROFIT_BPS = Decimal("30") # 30 bps = 0.30%
    # Break-even config
    BE_TRIGGER_BPS = Decimal("15") # Move SL to BE when in profit >= 15 bps
    BE_OFFSET_TICKS = 1 # Add 1 tick beyond BE to cover fees

    # Logging
    LOG_EVERY_SECS = 10
    WS_PING_SECS = 20

    # Original parameters that are now redundant or replaced:
    # BASE_SPREAD (replaced by BASE_SPREAD_BPS)
    # MIN_SPREAD (replaced by MIN_SPREAD_TICKS)
    # MAX_SPREAD (no direct equivalent in new quoting)
    # ORDER_QTY (replaced by QUOTE_SIZE)
    # MAX_POSITION (redefined for units, not notional)
    # INVENTORY_EXTREME (no direct equivalent)
    # STOP_LOSS_PCT (replaced by protection modes)
    # TAKE_PROFIT_PCT (replaced by protection modes)
    # UPDATE_INTERVAL (replaced by REFRESH_MS)
    # VOLATILITY_WINDOW (no direct equivalent in new quoting)
    # VOLATILITY_STD (no direct equivalent in new quoting)
    # ORDER_LEVELS (not directly used by current Quoter, but kept for future layered quoting)
    # MIN_ORDER_SIZE (replaced by QUOTE_SIZE)
    # MAX_ORDER_SIZE (not directly used by current Quoter)
    # ORDER_SIZE_INCREMENT (not directly used by current Quoter)

    # Backtester Settings (original parameters - keep as is)
    INITIAL_CAPITAL: float = 10000.0
    START_DATE: str = "2025-08-20"
    END_DATE: str = "2025-08-21"
    INTERVAL: str = "1"  # 1, 3, 5, 15, 30, 60, 120, 240, 360, 720 minutes
    MAKER_FEE: float = 0.0002  # 0.02%
    TAKER_FEE: float = 0.0005  # 0.05%
    SLIPPAGE: float = 0.0001  # 0.01%
    USE_ORDERBOOK: bool = True
    ORDERBOOK_DEPTH: int = 50
    USE_WEBSOCKET: bool = True # Set to True for live trading with WebSocket
