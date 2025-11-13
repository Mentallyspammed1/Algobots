"""Configuration for Advanced Market Maker
Use at your own risk.
"""

# Authentication
# Authentication
# API_KEY and PRIVATE_KEY should be set as environment variables for security.

# Trading Settings
SYMBOL = "TRUMPUSD"  # Trading symbol
CATEGORY = "linear"  # Market category (linear, inverse, spot)
SETTLE_ASSET = "USDT"  # Settle asset for derivatives
ACCOUNT_TYPE = "UNIFIED"  # Account type (UNIFIED, CONTRACT, SPOT)
POSITION_IDX = 0  # Position index for hedge mode

# Exchange Settings
TESTNET = False  # Use testnet for development
DEBUG_WS = False  # Enable WebSocket debugging

# Risk Management
LEVERAGE = 5  # Leverage to use
MARGIN_MODE = "CROSS"  # Margin mode (CROSS, ISOLATED)
EQUITY = 0.1  # Equity to use (0.1 = 10% of balance)
QTY_SCALING_FACTOR = 1.0  # Scaling factor for order quantities
BASE_SPREAD = 0.001  # Base spread as decimal (0.001 = 0.1%)
RANGE = 0.04  # Price range as decimal (0.04 = 4%)
NUM_ORDERS = 10  # Number of orders on each side
TP_DIST = 0.003  # Take-profit distance as decimal (0.003 = 0.3%)
STOP_DIST = 0.025  # Stop-loss distance as decimal (0.025 = 2.5%)
MAX_SPREAD_MULTIPLIER = 3.0  # Maximum spread multiplier during high volatility

# API Settings
LOGGING_LEVEL = 50  # Python logging level
RETRY_CODES = {10002, 10006}  # Error codes to retry on
IGNORE_CODES = {20001, 30034}  # Error codes to ignore
FORCE_RETRY = True  # Force retry on errors
RETRY_DELAY = 3  # Delay between retries in seconds
TIME_WINDOW = 10000  # Time window in ms for requests
RECV_WINDOW = 10000  # Receive window in ms for requests

# Performance Settings
POLLING_RATE = 2  # Polling rate in Hz (requests per second)
ORDERBOOK_DEPTH = 50  # Orderbook depth to track
QTY_PRECISION = 6  # Quantity precision for orders
PRICE_PRECISION = 2  # Price precision for orders
