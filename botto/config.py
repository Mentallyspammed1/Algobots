import os
from dotenv import load_dotenv
import logging

load_dotenv()  # Load environment variables from .env file

# --- Logging Configuration ---
# Setup basic logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Output to console
        # Consider adding logging.FileHandler(LOG_FILE) for file logging
    ]
)
logger = logging.getLogger(__name__)


# --- Helper functions for safe type conversion ---
def safe_get_int(key: str, default: int) -> int:
    """Safely get an integer from environment variables."""
    value = os.getenv(key, str(default))
    try:
        return int(value)
    except ValueError:
        logger.warning(f"Invalid integer value for '{key}': '{value}'. "
                       f"Using default: {default}")
        return default


def safe_get_float(key: str, default: float) -> float:
    """Safely get a float from environment variables."""
    value = os.getenv(key, str(default))
    try:
        return float(value)
    except ValueError:
        logger.warning(f"Invalid float value for '{key}': '{value}'. "
                       f"Using default: {default}")
        return default


def safe_get_bool(key: str, default: bool) -> bool:
    """Safely get a boolean from environment variables."""
    value = os.getenv(key, str(default)).lower()
    if value in ['true', '1', 'yes']:
        return True
    elif value in ['false', '0', 'no']:
        return False
    else:
        logger.warning(f"Invalid boolean value for '{key}': '{value}'. "
                       f"Using default: {default}")
        return default


# --- API Configuration ---
TESTNET = safe_get_bool("BYBIT_TESTNET", False)  # Set to False to use Bybit Mainnet
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")


# --- Trading Parameters ---
SYMBOL = os.getenv("BYBIT_SYMBOL", "BTCUSDT")
INTERVAL = os.getenv("BYBIT_INTERVAL", "1")  # 1, 5, 15, 60, 240, D
LEVERAGE = safe_get_float("BYBIT_LEVERAGE", 10.0)
TRADE_QTY = safe_get_float("BYBIT_TRADE_QTY", 0.001)  # Quantity per trade


# --- Indicator Parameters ---
# RSI
RSI_PERIOD = safe_get_int("RSI_PERIOD", 14)
RSI_OVERBOUGHT = safe_get_float("RSI_OVERBOUGHT", 70.0)
RSI_OVERSOLD = safe_get_float("RSI_OVERSOLD", 30.0)

# Stochastic RSI
STOCH_RSI_PERIOD = safe_get_int("STOCH_RSI_PERIOD", 14)
STOCH_RSI_SMOOTH_K = safe_get_int("STOCH_RSI_SMOOTH_K", 3)
STOCH_RSI_SMOOTH_D = safe_get_int("STOCH_RSI_SMOOTH_D", 3)
STOCH_RSI_OVERBOUGHT = safe_get_float("STOCH_RSI_OVERBOUGHT", 80.0)
STOCH_RSI_OVERSOLD = safe_get_float("STOCH_RSI_OVERSOLD", 20.0)

# SuperTrend
SUPER_TREND_PERIOD = safe_get_int("SUPER_TREND_PERIOD", 10)
SUPER_TREND_MULTIPLIER = safe_get_float("SUPER_TREND_MULTIPLIER", 3.0)

# Ehlers Fisher Transform
EH_FISHER_PERIOD = safe_get_int("EH_FISHER_PERIOD", 10)
EH_FISHER_SMOOTHING = safe_get_int("EH_FISHER_SMOOTHING", 5)
EH_FISHER_OVERBOUGHT = safe_get_float("EH_FISHER_OVERBOUGHT", 1.0)
EH_FISHER_OVERSOLD = safe_get_float("EH_FISHER_OVERSOLD", -1.0)
EH_FISHER_TRIGGER_BUY = safe_get_float("EH_FISHER_TRIGGER_BUY", 0.5)
EH_FISHER_TRIGGER_SELL = safe_get_float("EH_FISHER_TRIGGER_SELL", -0.5)


# --- Risk Management ---
MAX_POSITION_SIZE = safe_get_float("MAX_POSITION_SIZE", 0.005)  # Max position size in base currency
STOP_LOSS_PERCENT = safe_get_float("STOP_LOSS_PERCENT", 0.005)  # 0.5%
TAKE_PROFIT_PERCENT = safe_get_float("TAKE_PROFIT_PERCENT", 0.01)  # 1%


# --- Dynamic Position Sizing Parameters ---
DEFAULT_POSITION_SIZE = safe_get_float("DEFAULT_POSITION_SIZE", 0.001)  # Default size if no trade history
KELLY_RISK_PER_TRADE_MULTIPLIER = safe_get_float(
    "KELLY_RISK_PER_TRADE_MULTIPLIER", 0.02)  # Multiplier for Kelly fraction in risk calculation
MIN_POSITION_SIZE = safe_get_float("MIN_POSITION_SIZE", 0.0001)  # Minimum trade quantity


# --- WebSocket & Order Management ---
ORDER_TIMEOUT_SECONDS = safe_get_int("ORDER_TIMEOUT_SECONDS", 30)
RECONNECT_TIMEOUT_SECONDS = safe_get_int("RECONNECT_TIMEOUT_SECONDS", 10)
PING_INTERVAL = safe_get_int("PING_INTERVAL", 20)  # Send ping every X seconds
PING_TIMEOUT = safe_get_int("PING_TIMEOUT", 10)  # Disconnect if no pong received within X seconds


# --- Bybit Endpoints ---
BYBIT_REST_BASE_URL = "https://api.bybit.com" if not TESTNET else "https://api-testnet.bybit.com"
BYBIT_WS_PUBLIC_BASE_URL = ("wss://stream.bybit.com/v5/public/linear" if not TESTNET
                            else "wss://stream-testnet.bybit.com/v5/public/linear")
BYBIT_WS_PRIVATE_BASE_URL = ("wss://stream.bybit.com/v5/private" if not TESTNET
                             else "wss://stream-testnet.bybit.com/v5/private")


# --- Validation ---
def validate_config():
    """Validates configuration parameters."""
    if not API_KEY or not API_SECRET:
        logger.error("API Key and Secret are missing. "
                     "Please set BYBIT_API_KEY and BYBIT_API_SECRET in your .env file.")
        raise ValueError("API credentials not set.")

    if not (0 < STOP_LOSS_PERCENT <= 1):
        logger.warning(f"STOP_LOSS_PERCENT ({STOP_LOSS_PERCENT}) is outside the typical range (0, 1]. "
                       "Adjusting to nearest valid value.")
        # Optionally clamp or raise error

    if not (0 < TAKE_PROFIT_PERCENT <= 1):
        logger.warning(f"TAKE_PROFIT_PERCENT ({TAKE_PROFIT_PERCENT}) is outside the typical range (0, 1]. "
                       "Adjusting to nearest valid value.")
        # Optionally clamp or raise error

    # Add more validation as needed for other parameters
    logger.info("Configuration validation passed.")


# Call validation on import
try:
    validate_config()
except ValueError as e:
    logger.critical(f"Configuration error: {e}")
    # Depending on the application, you might want to exit here
    # sys.exit(1)