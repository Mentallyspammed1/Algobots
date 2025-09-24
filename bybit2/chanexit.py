#!/usr/bin/env python3

"""Pyrmethus's Ascended Neon Bybit Trading Bot (Long/Short Enhanced with Chandelier Exit)

This ultimate incantation perfects the Supertrend strategy for Bybit V5 API,
integrating the Chandelier Exit for dynamic trailing stops. It ensures both
long and short positions are taken and closed on signal flips or exit triggers,
with API confirmation. Forged in Termux’s ethereal forge, it radiates neon
brilliance and strategic precision.

Enhancements:
- Explicit Long/Short Support: Robustly handles both directions.
- Chandelier Exit: Dynamic trailing stops based on ATR, integrated as primary exit.
- Supertrend & RSI Integration: Combines trend and momentum for entries.
- Configurable Exposure: 'max_position_size' caps sizes; 'close_delay' ensures API stability.
- Enhanced Logging: Neon debug logs track position states and closures.
- Backtest Precision: Reflects Chandelier Exit logic, logs entry/exit pairs.
- Plotting Clarity: Buy/sell signals, Supertrend, and Chandelier lines on charts.
- Email Alerts: Include position details.
- Dynamic Sizing: Calculates position size based on risk percentage and stop distance.
- Decimal Precision: Uses Python's Decimal type for all financial calculations.
- Robust Error Handling: Improved API error checks and retries.
- Optional Stoch RSI Crossover: Added as an alternative/additional filter.
- Symbol Specific Rules: Incorporates minimum quantity and step size rules.
- Parameter Validation: Basic checks for configuration sanity.
- Improved API Error Handling: More specific hints for common Bybit API errors.

For Termux: pkg install python termux-api python-matplotlib libssl; pip install pybit pandas pandas_ta colorama matplotlib.
Testnet default—set 'testnet': false for live.
"""

# Import necessary libraries
import json
import logging
import os
import smtplib
import subprocess
import time
import random # For random jitter in delays
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN
from email.mime.text import MIMEText

import matplotlib.pyplot as plt
import pandas as pd
import pandas_ta as ta
from colorama import Fore, Style, init
from pybit.unified_trading import HTTP

# Initialize Colorama for neon terminal radiance
init(autoreset=True)

# Neon Color Palette: Glowing like digital auroras
NEON_SUCCESS = Fore.LIGHTGREEN_EX
NEON_INFO = Fore.LIGHTCYAN_EX
NEON_WARNING = Fore.LIGHTYELLOW_EX
NEON_ERROR = Fore.LIGHTRED_EX
NEON_SIGNAL = Fore.LIGHTMAGENTA_EX + Style.BRIGHT
NEON_DEBUG = Fore.LIGHTBLUE_EX
NEON_POSITION = Fore.LIGHTWHITE_EX
NEON_RESET = Style.RESET_ALL

# --- Configuration Files ---
CONFIG_FILE = "bot_config.json"
LOG_FILE = "trade_log.log"
STATE_FILE = "bot_state.json"

# --- Constants ---
MAX_API_RETRIES = 5
INITIAL_RETRY_DELAY = 5 # seconds Base delay for exponential backoff on API errors
API_TIMEOUT = 20 # seconds Increased timeout for API requests
DEFAULT_SLEEP_DURATION = 60 # seconds Default wait time between cycles if calculation fails
MIN_PLOT_CANDLES = 50 # Minimum candles required to attempt plotting

# --- Symbol Specific Configuration ---
# Define trading rules (min quantity, step size) for different symbols. Essential for valid orders.
SYMBOL_INFO = {
    "BTCUSDT": {
        "min_qty": Decimal("0.00001"),  # Minimum order quantity in base currency (e.g., BTC)
        "qty_step": Decimal("0.00001"), # Minimum step for quantity changes
        "price_precision": 2          # Decimal places for price (e.g., 45678.90) - Not directly used here but good info
    },
    "ETHUSDT": {
        "min_qty": Decimal("0.0001"),
        "qty_step": Decimal("0.0001"),
        "price_precision": 2
    },
    # Add other symbols as needed
}

# --- Logging Setup ---
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- Helper Functions ---
def to_decimal(value, precision=8, rounding=ROUND_HALF_UP):
    """Safely converts value to Decimal with specified precision and rounding."""
    if value is None:
        return Decimal('0')
    try:
        # Use ROUND_DOWN for quantities sent to exchange if needed, ROUND_HALF_UP for general calc
        return Decimal(str(value)).quantize(Decimal('1e-' + str(precision)), rounding=rounding)
    except Exception as e:
        logging.warning(f"Could not convert value '{value}' to Decimal with precision {precision}: {e}")
        return Decimal('0')

def get_symbol_info(symbol, key, default=None):
    """Retrieves specific info for a symbol from global SYMBOL_INFO, with a default."""
    return SYMBOL_INFO.get(symbol, {}).get(key, default)

def format_quantity(qty, symbol):
    """Formats quantity according to symbol's step size rules."""
    qty_decimal = to_decimal(qty, precision=10, rounding=ROUND_DOWN) # Use high precision internally before stepping
    step = get_symbol_info(symbol, "qty_step", Decimal('0.00001')) # Default step if not found
    min_qty = get_symbol_info(symbol, "min_qty", Decimal('0.00001')) # Default min_qty if not found

    # Ensure step and min_qty are valid Decimals
    step = to_decimal(step, precision=10)
    min_qty = to_decimal(min_qty, precision=10)

    if qty_decimal < min_qty:
        # If calculated qty is below minimum, return '0' string as per Bybit's likely handling
        print(NEON_WARNING + f"Quantity {qty_decimal:.10f} is below minimum {min_qty:.10f} for {symbol}. Cannot place order." + NEON_RESET)
        return '0.00000000' # Return string '0' with standard precision

    # Adjust quantity to the nearest valid step using floor division
    # Example: qty=0.00015, step=0.0001 => (0.00015 // 0.0001) * 0.0001 = 1 * 0.0001 = 0.0001
    # Ensure step is not zero to avoid division by zero error
    if step > Decimal('0'):
        adjusted_qty = (qty_decimal // step) * step
    else:
        adjusted_qty = qty_decimal # Use original if step is invalid

    # Ensure the adjusted quantity is not zero if the original was valid and above minimum
    # If adjustment results in zero but original was valid, default to the smallest step size
    if adjusted_qty <= Decimal('0') and qty_decimal >= min_qty:
         adjusted_qty = step # Use the minimum step size if adjustment failed but original was valid

    # Final check against min_qty after stepping
    if adjusted_qty < min_qty:
         adjusted_qty = min_qty # Ensure we are at least at the minimum quantity

    # Return formatted string with high precision (e.g., 8 decimal places)
    # Note: Bybit might have its own precision requirements; 8 is generally safe.
    return f"{adjusted_qty:.8f}"


# --- Load Configuration ---
def _load_config():
    """Loads bot settings from JSON or applies defaults and performs basic validation."""
    defaults = {
        # Core Settings
        "symbol": "TRUMPUSDT", # Default symbol, can be overridden by config file
        "category": "linear", # linear or inverse
        "interval": "1", # Kline interval in minutes (e.g., '1', '5', '15', '60', 'D')
        "leverage": 10,
        "max_open_trades": 1, # Max concurrent positions (currently enforces 1 total position: Long OR Short)
        "close_delay": 3,  # Seconds delay after order confirmation for stability

        # Supertrend Settings
        "super_trend_length": 10,
        "super_trend_multiplier": 3.0, # Multiplier for ATR in Supertrend calculation

        # RSI Settings
        "rsi_length": 14,
        "rsi_overbought": 70,
        "rsi_oversold": 30,

        # Chandelier Exit Settings
        "use_chandelier_exit": True, # Enable Chandelier Exit as primary trailing stop
        "chandelier_atr_length": 22,
        "chandelier_atr_multiplier": 1.0, # ATR multiplier for Chandelier Exit calculation

        # Stoch RSI Settings (Optional Filter)
        "use_stochrsi_crossover": False, # Use Stoch RSI %K > %D (up) or %K < %D (down) as confirmation
        "stochrsi_k_period": 14,
        "stochrsi_d_period": 3, # Smoothing period for Stoch RSI

        # Sizing and Risk Management
        "risk_pct": Decimal("0.01"), # Percentage of equity to risk per trade (e.g., 1%)
        "stop_loss_pct": Decimal("0.02"), # Fallback initial stop loss percentage if CE fails or is disabled
        "max_position_size": Decimal("0.01"), # Maximum position size in base currency (e.g., 0.01 BTC)

        # Mode and Output
        "testnet": False, # Use Bybit testnet (True) or mainnet (False)
        "backtest": True, # Enable backtesting mode
        "backtest_start": "2024-07-15", # Start date for backtesting (YYYY-MM-DD)
        "backtest_end": "2024-07-20",   # End date for backtesting (YYYY-MM-DD)
        "plot_enabled": False, # Enable plotting of results (requires matplotlib)

        # Email Notifications
        "email_notify": False, # Enable email alerts
        "email_sender": "", # Sender email address (e.g., your Gmail)
        "email_password": "", # Sender email password or App Password
        "email_receiver": ""  # Recipient email address
    }

    # Load existing config or create default file
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
            # Load and convert Decimal values correctly from JSON strings
            config['risk_pct'] = to_decimal(config.get('risk_pct', defaults['risk_pct']), rounding=ROUND_HALF_UP)
            config['stop_loss_pct'] = to_decimal(config.get('stop_loss_pct', defaults['stop_loss_pct']), rounding=ROUND_HALF_UP)
            config['max_position_size'] = to_decimal(config.get('max_position_size', defaults['max_position_size']), rounding=ROUND_HALF_UP)
            config['super_trend_multiplier'] = to_decimal(config.get('super_trend_multiplier', defaults['super_trend_multiplier']), rounding=ROUND_HALF_UP)
            config['chandelier_atr_multiplier'] = to_decimal(config.get('chandelier_atr_multiplier', defaults['chandelier_atr_multiplier']), rounding=ROUND_HALF_UP)
            defaults.update(config)
            print(NEON_SUCCESS + f"Config summoned from {CONFIG_FILE}." + NEON_RESET)
        except Exception as e:
            print(NEON_ERROR + f"Shadow in config file {CONFIG_FILE}: {e}. Using defaults." + NEON_RESET)
            logging.error(f"Failed to load config from {CONFIG_FILE}: {e}")
    else:
        # Ensure default Decimal values are correctly typed before saving
        defaults['risk_pct'] = to_decimal(defaults['risk_pct'], rounding=ROUND_HALF_UP)
        defaults['stop_loss_pct'] = to_decimal(defaults['stop_loss_pct'], rounding=ROUND_HALF_UP)
        defaults['max_position_size'] = to_decimal(defaults['max_position_size'], rounding=ROUND_HALF_UP)
        defaults['super_trend_multiplier'] = to_decimal(defaults['super_trend_multiplier'], rounding=ROUND_HALF_UP)
        defaults['chandelier_atr_multiplier'] = to_decimal(defaults['chandelier_atr_multiplier'], rounding=ROUND_HALF_UP)
        try:
            # Convert Decimals to strings for JSON serialization
            config_to_save = defaults.copy()
            config_to_save['risk_pct'] = str(config_to_save['risk_pct'])
            config_to_save['stop_loss_pct'] = str(config_to_save['stop_loss_pct'])
            config_to_save['max_position_size'] = str(config_to_save['max_position_size'])
            config_to_save['super_trend_multiplier'] = str(config_to_save['super_trend_multiplier'])
            config_to_save['chandelier_atr_multiplier'] = str(config_to_save['chandelier_atr_multiplier'])

            with open(CONFIG_FILE, 'w') as f:
                json.dump(config_to_save, f, indent=4)
            print(NEON_INFO + f"Forged new {CONFIG_FILE} with defaults." + NEON_RESET)
        except Exception as e:
             print(NEON_ERROR + f"Failed to create default config file {CONFIG_FILE}: {e}" + NEON_RESET)
             logging.error(f"Failed to create default config file {CONFIG_FILE}: {e}")

    # Perform basic validation on critical parameters after loading/defaults
    if defaults['interval'] <= 0:
         print(NEON_ERROR + "Configuration Error: 'interval' must be a positive number. Defaulting to 60 minutes.")
         defaults['interval'] = 60
    if defaults['leverage'] <= 0:
         print(NEON_ERROR + "Configuration Error: 'leverage' must be positive. Defaulting to 10x.")
         defaults['leverage'] = 10
    if defaults['risk_pct'] <= Decimal('0') or defaults['risk_pct'] > Decimal('1'):
         print(NEON_ERROR + f"Configuration Error: 'risk_pct' ({defaults['risk_pct']}) out of range (0 < risk < 1). Defaulting to 1%.")
         defaults['risk_pct'] = Decimal('0.01')
    if defaults['max_position_size'] <= Decimal('0'):
         print(NEON_ERROR + f"Configuration Error: 'max_position_size' ({defaults['max_position_size']}) must be positive. Defaulting to 0.01.")
         defaults['max_position_size'] = Decimal('0.01')
    if defaults['super_trend_length'] <= 0:
         print(NEON_ERROR + f"Configuration Error: 'super_trend_length' ({defaults['super_trend_length']}) must be positive. Defaulting to 10.")
         defaults['super_trend_length'] = 10
    if defaults['super_trend_multiplier'] <= 0:
         print(NEON_ERROR + f"Configuration Error: 'super_trend_multiplier' ({defaults['super_trend_multiplier']}) must be positive. Defaulting to 3.0.")
         defaults['super_trend_multiplier'] = Decimal('3.0')

    # Final check/conversion for critical Decimal values after validation
    defaults['risk_pct'] = to_decimal(defaults['risk_pct'], rounding=ROUND_HALF_UP)
    defaults['stop_loss_pct'] = to_decimal(defaults['stop_loss_pct'], rounding=ROUND_HALF_UP)
    defaults['max_position_size'] = to_decimal(defaults['max_position_size'], rounding=ROUND_HALF_UP)
    defaults['super_trend_multiplier'] = to_decimal(defaults['super_trend_multiplier'], rounding=ROUND_HALF_UP)
    defaults['chandelier_atr_multiplier'] = to_decimal(defaults['chandelier_atr_multiplier'], rounding=ROUND_HALF_UP)

    return defaults

# --- Securely Load API Credentials ---
def _load_api_creds():
    """Loads API key and secret from JSON or env vars. Exits if absent."""
    api_key = None
    api_secret = None

    if os.path.exists("authcreds.json"):
        try:
            with open("authcreds.json") as f:
                creds = json.load(f)
                api_key = creds.get('api_key')
                api_secret = creds.get('api_secret')
            if api_key and api_secret:
                print(NEON_SUCCESS + "API credentials summoned from authcreds.json." + NEON_RESET)
            else:
                 print(NEON_WARNING + "authcreds.json found but incomplete. Seeking environment variables..." + NEON_RESET)
        except Exception as e:
            print(NEON_ERROR + f"Shadow in authcreds.json: {e}" + NEON_RESET)
            print(NEON_INFO + "Seeking environment variables..." + NEON_RESET)

    if not api_key or not api_secret:
        api_key = os.getenv('BYBIT_API_KEY')
        api_secret = os.getenv('BYBIT_API_SECRET')
        if api_key and api_secret:
            print(NEON_SUCCESS + "Credentials drawn from environmental ether." + NEON_RESET)
        else:
            print(NEON_ERROR + "CRITICAL: API keys lost in the void. Forge 'authcreds.json' or set env vars (BYBIT_API_KEY, BYBIT_API_SECRET)." + NEON_RESET)
            logging.critical("API credentials missing.")
            exit(1)

    return api_key, api_secret

# --- Initialize Bybit API Session ---
def _initialize_session(config):
    """Initializes the Pybit HTTP session and sets leverage."""
    if config['backtest']:
        print(NEON_INFO + "Backtest mode active—session forged for historical data simulation." + NEON_RESET)
        # Use a dummy session for backtesting; actual data fetching is handled differently
        session = HTTP(testnet=config['testnet'])
        return session

    api_key, api_secret = _load_api_creds()
    session = HTTP(
        testnet=config['testnet'],
        api_key=api_key,
        api_secret=api_secret,
        timeout=API_TIMEOUT # Use constant for timeout
    )

    # Set leverage if needed
    desired_leverage = str(config['leverage'])
    symbol = config['symbol']
    category = config['category']

    try:
        # Check current leverage first to avoid redundant API calls
        position_info_resp = session.get_positions(category=category, symbol=symbol)
        current_leverage = None
        if position_info_resp and position_info_resp.get("result", {}).get("list"):
            for pos in position_info_resp["result"]["list"]:
                if pos.get("symbol") == symbol:
                    current_leverage = pos.get("lever")
                    break # Found leverage for the symbol

        # Set leverage if not already set correctly
        if current_leverage is None: # No position open, leverage might not be set
            print(NEON_INFO + f"No open position for {symbol}. Attempting to set leverage to {desired_leverage}x." + NEON_RESET)
            session.set_leverage(
                category=category, symbol=symbol,
                buyLeverage=desired_leverage, sellLeverage=desired_leverage
            )
            print(NEON_SUCCESS + f"Leverage set to {desired_leverage}x on {'Testnet' if config['testnet'] else 'Mainnet'}." + NEON_RESET)
        elif Decimal(current_leverage) != Decimal(desired_leverage):
            print(NEON_INFO + f"Current leverage {current_leverage}x differs from desired {desired_leverage}x. Adjusting..." + NEON_RESET)
            session.set_leverage(
                category=category, symbol=symbol,
                buyLeverage=desired_leverage, sellLeverage=desired_leverage
            )
            print(NEON_SUCCESS + f"Leverage adjusted to {desired_leverage}x on {'Testnet' if config['testnet'] else 'Mainnet'}." + NEON_RESET)
        else:
            print(NEON_INFO + f"Leverage for {symbol} is already {current_leverage}x. No change needed." + NEON_RESET)

    except Exception as e:
        # Handle specific Bybit error code 110043 (Leverage already set correctly)
        if isinstance(e, dict) and e.get('ret_code') == 110043:
            print(NEON_WARNING + f"Leverage setting redundant or already correct (Error Code: 110043). Continuing." + NEON_RESET)
        else:
            print(NEON_ERROR + f"Leverage initialization failed: {e}" + NEON_RESET)
            logging.error(f"Leverage initialization failed: {e}", exc_info=True)
            # Optionally exit if leverage is critical
            # exit(1)

    return session

# --- Data Acquisition Function ---
def _fetch_kline_data(session, symbol, category, interval, limit=1000, start_time=None, end_time=None):
    """Fetches kline data, handling time ranges, retries, and data validation."""
    all_data = []
    # Determine the initial fetch time based on whether a start time is provided (backtest) or default to now (live)
    current_fetch_start = start_time if start_time else int(time.time() * 1000)
    fetch_end_time = end_time if end_time else int(time.time() * 1000) # End time for backtesting or approximate current time

    print(NEON_INFO + f"Fetching klines for {symbol} ({interval}m interval)..." + NEON_RESET)

    while True:
        # Adjust fetch end time to avoid requesting data for the current incomplete candle
        # Add a buffer (e.g., 5 minutes worth of candles) if fetching live data
        fetch_buffer_ms = max(int(interval) * 60 * 1000, 300000) # Ensure at least 5 minutes buffer
        effective_end_time = min(fetch_end_time, int(time.time() * 1000) - fetch_buffer_ms) if not end_time else fetch_end_time

        params = {
            "category": category, "symbol": symbol, "interval": interval,
            "limit": limit,
            "start": current_fetch_start,
            "end": effective_end_time
        }

        # For live data fetching (no start_time specified), adjust start time based on last fetched candle to avoid gaps/overlaps
        if not start_time and len(all_data) > 0:
             last_ts = all_data[-1]['startTime'].timestamp() * 1000
             # Start fetching from right after the last fetched candle's timestamp
             current_fetch_start = int(last_ts) + (int(interval) * 60 * 1000)
             params["start"] = current_fetch_start # Update params with new start time

        response = None
        data = None # Initialize data to None for the loop condition check

        for attempt in range(MAX_API_RETRIES):
            try:
                print(NEON_INFO + f"Requesting klines: Start={datetime.fromtimestamp(params['start']/1000).strftime('%Y-%m-%d %H:%M')} "
                                f"End={datetime.fromtimestamp(params['end']/1000).strftime('%Y-%m-%d %H:%M')} Limit={params['limit']}..." + NEON_RESET)

                response = session.get_kline(**params)
                data = response.get('result', {}).get('list')

                # --- Data Validation ---
                if data is None: # Check if 'list' key exists in response
                    if response.get('retMsg', '').lower().startswith('no data'):
                        print(NEON_WARNING + "No kline data found for the specified period or symbol." + NEON_RESET)
                        return pd.DataFrame() # Return empty if no data at all
                    else: # Handle other missing data scenarios
                        raise ValueError(f"Kline data missing or invalid format. Response: {response.get('retMsg', 'Unknown error')}")

                if not data: # Handle empty list explicitly (received valid response but no rows)
                     print(NEON_INFO + "Received empty data list, assuming end of available data or no new data." + NEON_RESET)
                     break # Exit retry loop and outer fetch loop

                # Process data into DataFrame
                df_chunk = pd.DataFrame(data, columns=['startTime', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
                # Convert startTime from ms timestamp to datetime object, handling potential warnings
                try:
                     df_chunk['startTime'] = pd.to_datetime(df_chunk['startTime'], unit='ms', utc=True)
                except Exception as dt_error:
                    # Try converting to numeric first if the direct conversion fails (addresses FutureWarning)
                    try:
                         df_chunk['startTime'] = pd.to_datetime(pd.to_numeric(df_chunk['startTime']), unit='ms', utc=True)
                    except Exception as e:
                         print(NEON_ERROR + f"Failed to convert startTime to datetime: {e}. Skipping chunk." + NEON_RESET)
                         logging.error(f"Failed to convert startTime to datetime: {e}", exc_info=True)
                         continue # Skip this chunk if timestamp conversion fails critically


                # Ensure numeric types for trading data, coercing errors to NaN
                for col in ['open', 'high', 'low', 'close', 'volume', 'turnover']:
                     df_chunk[col] = pd.to_numeric(df_chunk[col], errors='coerce')
                # Drop rows where essential OHLC data is missing after coercion
                df_chunk.dropna(subset=['open', 'high', 'low', 'close'], inplace=True)
                # Sort by startTime and remove duplicates based on timestamp
                df_chunk.sort_values('startTime', inplace=True)
                df_chunk.drop_duplicates('startTime', keep='last', inplace=True)

                all_data.append(df_chunk)

                # --- Update Fetch Parameters for Next Iteration ---
                # Get the timestamp of the very last candle fetched in this chunk
                last_timestamp_ms = df_chunk['startTime'].iloc[-1].timestamp() * 1000
                # Set the start time for the next fetch to be right after the last fetched candle
                current_fetch_start = int(last_timestamp_ms) + (int(interval) * 60 * 1000)

                # Check if we received fewer candles than the requested limit (indicates end of available data)
                if len(df_chunk) < limit:
                    print(NEON_INFO + "Fetched fewer candles than limit, assuming end of available data." + NEON_RESET)
                    break # Exit retry loop and outer fetch loop

                # If backtesting, check if the next fetch start time exceeds the specified end time
                if start_time and end_time and current_fetch_start > end_time:
                    print(NEON_INFO + "Reached backtest end time boundary." + NEON_RESET)
                    break # Exit outer fetch loop

                break # Successful fetch, exit retry loop

            except Exception as e:
                print(NEON_ERROR + f"Kline fetch attempt {attempt + 1}/{MAX_API_RETRIES} failed: {e}" + NEON_RESET)
                logging.error(f"Kline fetch error: {e}", exc_info=True) # Log traceback for debugging
                if attempt < MAX_API_RETRIES - 1:
                    # Exponential backoff for retries with jitter
                    delay = INITIAL_RETRY_DELAY * (2 ** attempt) + random.uniform(0, 2) # Add random jitter
                    print(NEON_WARNING + f"Retrying in {delay:.2f} seconds..." + NEON_RESET)
                    time.sleep(delay)
                else:
                    print(NEON_ERROR + "Max retries reached. Failed to fetch klines for this cycle." + NEON_RESET)
                    # Return empty DataFrame to signal failure for this fetch cycle
                    return pd.DataFrame()

        # Break outer loop if data was empty, insufficient, or backtest boundary reached
        if not data or len(data) < limit or (start_time and end_time and current_fetch_start > end_time):
             break

    # Concatenate all fetched data chunks if any were collected
    if not all_data:
        print(NEON_WARNING + "No kline data collected during fetch sequence." + NEON_RESET)
        return pd.DataFrame()

    df_final = pd.concat(all_data, ignore_index=True)
    # Final cleanup: sort by time and remove any remaining duplicates
    df_final.sort_values('startTime', inplace=True)
    df_final.drop_duplicates('startTime', keep='last', inplace=True)
    df_final.reset_index(drop=True, inplace=True)
    print(NEON_SUCCESS + f"Successfully fetched {len(df_final)} klines." + NEON_RESET)
    return df_final

# --- Indicator Calculation Function ---
def _calculate_indicators(df, config):
    """Computes Supertrend, RSI, ATR, Chandelier Exit, and optionally Stoch RSI."""
    if df.empty:
        print(NEON_WARNING + "Input DataFrame for indicator calculation is empty." + NEON_RESET)
        return pd.DataFrame()

    # Ensure essential OHLC columns are numeric, drop rows with NaN OHLC
    required_cols = ['open', 'high', 'low', 'close']
    for col in required_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df.dropna(subset=required_cols, inplace=True)
    if df.empty:
         print(NEON_ERROR + "DataFrame became empty after ensuring numeric OHLC data."+ NEON_RESET)
         return pd.DataFrame()

    # --- Supertrend Calculation ---
    st_length = config['super_trend_length']
    st_multiplier = config['super_trend_multiplier'] # This is a Decimal value from config.py
    st_col = f"SUPERT_{st_length}_{st_multiplier:.8f}" # Expecting 8 decimal places
    st_dir_col = f"SUPERTd_{st_length}_{st_multiplier:.8f}"
    try:
        # Use pandas_ta to calculate Supertrend and append columns directly to df
        print(NEON_DEBUG + f"Calculating Supertrend with length={st_length}, multiplier={st_multiplier}..." + NEON_RESET)
        df.ta.supertrend(length=st_length, multiplier=st_multiplier, append=True)

        # --- DEBUGGING: Print columns after Supertrend calculation ---
        print(f"Columns after Supertrend calc: {df.columns.tolist()}")
        print(f"Expected Supertrend Columns: '{st_col}', '{st_dir_col}'")
        # --- END DEBUGGING ---

        # Verify calculation success by checking if expected columns exist
        if st_col not in df.columns or st_dir_col not in df.columns:
            # Raise a more informative error if columns are missing
            raise ValueError(f"Supertrend columns '{st_col}' or '{st_dir_col}' not generated. Available columns: {df.columns.tolist()}")
    except Exception as e:
        print(NEON_ERROR + f"Supertrend calculation failed: {e}" + NEON_RESET)
        logging.error(f"Supertrend calculation failed: {e}", exc_info=True)
        return pd.DataFrame() # Critical failure, return empty DataFrame

    # --- RSI Calculation ---
    rsi_length = config['rsi_length']
    rsi_col = 'rsi'
    try:
        df[rsi_col] = ta.rsi(df['close'], length=rsi_length)
    except Exception as e:
        print(NEON_WARNING + f"RSI calculation failed: {e}. RSI signals will be unavailable." + NEON_RESET)
        logging.warning(f"RSI calculation failed: {e}", exc_info=True)
        # Continue without RSI if it fails, but log the issue

    # --- Chandelier Exit Calculation ---
    use_ce = config.get('use_chandelier_exit', False)
    ce_long_col, ce_short_col = None, None # Placeholder names for CE columns
    if use_ce:
        atr_length = config['chandelier_atr_length']
        atr_multiplier = config['chandelier_atr_multiplier'] # Already Decimal
        atr_col = f"ATR_{atr_length}" # pandas_ta column name for ATR
        ce_long_col = 'chandelier_exit_long' # Custom name for long CE level
        ce_short_col = 'chandelier_exit_short' # Custom name for short CE level

        try:
            # Calculate ATR using pandas_ta
            df.ta.atr(length=atr_length, append=True)
            if atr_col not in df.columns:
                 raise ValueError("ATR column was not generated.")
            atr_values = df[atr_col].apply(to_decimal) # Ensure ATR values are Decimals

            # Calculate highest high and lowest low over the ATR window
            # Use rolling window matching ATR length
            highest_high = df['high'].rolling(window=atr_length).max().apply(to_decimal)
            lowest_low = df['low'].rolling(window=atr_length).min().apply(to_decimal)

            # Calculate Chandelier Exit Levels using Decimal arithmetic
            # Use ROUND_DOWN for long stop (must be below price), ROUND_UP for short stop (must be above price)
            df[ce_long_col] = (highest_high - atr_values * atr_multiplier).apply(lambda x: to_decimal(x, rounding=ROUND_DOWN))
            df[ce_short_col] = (lowest_low + atr_values * atr_multiplier).apply(lambda x: to_decimal(x, rounding=ROUND_UP))

            # Ensure columns exist even if calculation resulted in NaNs initially
            if ce_long_col not in df.columns: df[ce_long_col] = pd.NA
            if ce_short_col not in df.columns: df[ce_short_col] = pd.NA

        except Exception as e:
            print(NEON_ERROR + f"Chandelier Exit calculation failed: {e}. Disabling Chandelier Exit feature." + NEON_RESET)
            logging.error(f"Chandelier Exit calculation failed: {e}", exc_info=True)
            config['use_chandelier_exit'] = False # Disable the feature if calculation fails

    # --- Stoch RSI Calculation (Optional Filter) ---
    stoch_rsi_k_name, stoch_rsi_d_name = None, None # Initialize column names
    if config.get('use_stochrsi_crossover', False):
        stoch_k_len = config.get('stochrsi_k_period', 14)
        stoch_d_len = config.get('stochrsi_d_period', 3)
        stoch_rsi_k_name = f'STOCHRSIk_{stoch_k_len}_{stoch_d_len}'
        # pandas_ta names the D line based on K line name + D length
        stoch_rsi_d_name = f'STOCHRSId_{stoch_k_len}_{stoch_d_len}'
        try:
            # Calculate Stochastic RSI using pandas_ta
            stoch_rsi_data = ta.stochrsi(df['close'], length=stoch_k_len, smooth_k=stoch_d_len, append=False)
            if not stoch_rsi_data.empty and len(stoch_rsi_data.columns) >= 2:
                 # Assign calculated columns to DataFrame
                 df[stoch_rsi_k_name] = stoch_rsi_data.iloc[:, 0] # K value
                 df[stoch_rsi_d_name] = stoch_rsi_data.iloc[:, 1] # D value
            else:
                 raise ValueError("Stoch RSI data calculation returned empty or insufficient columns.")
        except Exception as e:
            print(NEON_ERROR + f"Stoch RSI calculation failed: {e}. Disabling Stoch RSI filter." + NEON_RESET)
            logging.error(f"Stoch RSI calculation failed: {e}", exc_info=True)
            config['use_stochrsi_crossover'] = False # Disable the filter if calculation fails

    # --- Prepare Return DataFrame ---
    # Define columns to return, including optional ones if they were successfully calculated
    return_cols = ['startTime', st_col, st_dir_col, 'close']
    if rsi_col in df.columns: return_cols.append(rsi_col)
    if ce_long_col and ce_short_col in df.columns: return_cols.extend([ce_long_col, ce_short_col])
    if stoch_rsi_k_name and stoch_rsi_d_name in df.columns: return_cols.extend([stoch_rsi_k_name, stoch_rsi_d_name])
    # Include ATR column if calculated, useful for debugging/plotting
    if atr_col in df.columns: return_cols.append(atr_col)

    # Ensure all requested return columns exist in the DataFrame, adding them with NA if missing
    for col in return_cols:
        if col not in df.columns:
            df[col] = pd.NA # Add column with placeholder NA value

    # Return only the selected columns
    return df[return_cols]


# --- Plot Supertrend Vision ---
def _plot_supertrend(df, config):
    """Generates a plot visualizing price, Supertrend, Chandelier Exit, and signals."""
    if df.empty or len(df) < MIN_PLOT_CANDLES:
         print(NEON_WARNING + f"Not enough data ({len(df)} candles) to generate plot. Need at least {MIN_PLOT_CANDLES}." + NEON_RESET)
         return

    try:
        # Get column names based on config for dynamic plotting
        st_length = config['super_trend_length']
        st_multiplier = config['super_trend_multiplier']
        st_col = f"SUPERT_{st_length}_{st_multiplier}"
        st_dir_col = f"SUPERTd_{st_length}_{st_multiplier}"

        plt.style.use('dark_background') # Use a dark theme for better visibility
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 9), sharex=True) # Create 2 subplots sharing X-axis

        # --- Plot 1: Price Action, Supertrend, and Chandelier Exit ---
        ax1.plot(df['startTime'], df['close'], label='Close Price', color='cyan', linewidth=1.5)

        # Plot Supertrend line and fill area between price and Supertrend
        if st_col in df.columns and df[st_col].notna().any():
            ax1.plot(df['startTime'], df[st_col], label='Supertrend', color='yellow', linewidth=1.5)
            # Fill between Supertrend and close price based on direction
            ax1.fill_between(df['startTime'], df['close'], df[st_col], where=(df['close'] >= df[st_col]), color='lime', alpha=0.2, interpolate=True)
            ax1.fill_between(df['startTime'], df['close'], df[st_col], where=(df['close'] < df[st_col]), color='red', alpha=0.2, interpolate=True)

        # Plot Chandelier Exit levels if enabled and data exists
        ce_long_col = 'chandelier_exit_long'
        ce_short_col = 'chandelier_exit_short'
        if config.get('use_chandelier_exit', False):
            if ce_long_col in df.columns and df[ce_long_col].notna().any():
                ax1.plot(df['startTime'], df[ce_long_col], label='Chandelier Exit Long', color='lime', linestyle='--', linewidth=1)
            if ce_short_col in df.columns and df[ce_short_col].notna().any():
                ax1.plot(df['startTime'], df[ce_short_col], label='Chandelier Exit Short', color='magenta', linestyle='--', linewidth=1)

        # Plot Buy/Sell signals based on Supertrend direction changes
        if st_dir_col in df.columns and pd.api.types.is_numeric_dtype(df[st_dir_col]):
            # Find transitions: -1 to 1 (Buy Signal), 1 to -1 (Sell Signal)
            buy_signals = df[(df[st_dir_col].shift(1) == -1) & (df[st_dir_col] == 1)]
            sell_signals = df[(df[st_dir_col].shift(1) == 1) & (df[st_dir_col] == -1)]
            # Add markers for signals
            ax1.scatter(buy_signals['startTime'], buy_signals['close'], color='lime', label='Buy Signal (ST Flip)', marker='^', s=100, zorder=5)
            ax1.scatter(sell_signals['startTime'], sell_signals['close'], color='red', label='Sell Signal (ST Flip)', marker='v', s=100, zorder=5)

        # Configure Plot 1 aesthetics
        ax1.set_title(f"Ascended Neon Bot - {config['symbol']} ({config['interval']}m Interval)", color='cyan')
        ax1.set_ylabel('Price', color='cyan')
        ax1.grid(True, linestyle='--', alpha=0.6) # Add subtle grid lines
        ax1.legend(loc='upper left', facecolor='black') # Place legend in upper left corner

        # --- Plot 2: RSI Indicator ---
        rsi_col = 'rsi'
        if rsi_col in df.columns and df[rsi_col].notna().any():
             ax2.plot(df['startTime'], df[rsi_col], label='RSI', color='magenta', linewidth=1.5)
             # Add horizontal lines for overbought and oversold levels
             ax2.axhline(config['rsi_overbought'], color='red', linestyle='--', linewidth=1, label=f'Overbought ({config["rsi_overbought"]})')
             ax2.axhline(config['rsi_oversold'], color='green', linestyle='--', linewidth=1, label=f'Oversold ({config["rsi_oversold"]})')
             ax2.set_ylabel('RSI', color='magenta')
             ax2.grid(True, linestyle='--', alpha=0.6)
             ax2.legend(loc='upper left', facecolor='black')
        else: # Display message if RSI data is unavailable
             ax2.text(0.5, 0.5, 'RSI data not available', ha='center', va='center', transform=ax2.transAxes, color='gray')

        # Configure common X-axis label
        plt.xlabel('Time', color='cyan')
        fig.tight_layout() # Adjust subplot parameters for a tight layout

        # Save the plot to a file
        plot_filename = 'supertrend_plot.png'
        plt.savefig(plot_filename)
        print(NEON_INFO + f"Plot forged as {plot_filename}." + NEON_RESET)
        plt.close(fig) # Close the figure to free up memory

    except Exception as e:
        print(NEON_WARNING + f"Plotting process disrupted: {e}" + NEON_RESET)
        logging.warning(f"Plotting failed: {e}", exc_info=True)


# --- Get Account Balance ---
def _get_balance(session, config):
    """Fetches USDT available balance with Decimal precision."""
    try:
        # Fetch wallet balance for the UNIFIED account type (standard for Bybit V5)
        response = session.get_wallet_balance(accountType="UNIFIED")
        balances = response.get('result', {}).get('list', [])

        if not balances: # Check if balance list is empty
             print(NEON_WARNING + "Could not retrieve wallet balance list from API." + NEON_RESET)
             return to_decimal(0)

        # Access the coin balance list (usually the first element for unified account)
        account_balances = balances[0].get('coin', []) if balances else []

        # Find USDT balance
        for coin_data in account_balances:
            if coin_data.get('coin') == 'USDT':
                # Use 'availableBalance' for tradable funds, fallback to 'walletBalance' if needed
                balance = to_decimal(coin_data.get('availableBalance', '0'))
                print(NEON_INFO + f"USDT Available Balance: {balance:.4f}" + NEON_RESET)
                return balance # Return balance as Decimal

        # USDT not found in balance list
        print(NEON_WARNING + "USDT balance not found in wallet. Assuming 0 USDT." + NEON_RESET)
        return to_decimal(0)
    except Exception as e:
        print(NEON_ERROR + f"Balance query disrupted: {e}" + NEON_RESET)
        logging.error(f"Failed to get balance: {e}", exc_info=True)
        return to_decimal(0) # Return 0 balance on error

# --- Check RSI Filter ---
def _check_rsi_filter(rsi_val, config, side):
    """Checks if RSI is within acceptable limits for the signal side."""
    if pd.isna(rsi_val): return False # Cannot check if RSI is NaN

    if side == "Buy":
        # Allow Buy signal if RSI is below the overbought threshold
        return rsi_val < config['rsi_overbought']
    elif side == "Sell":
        # Allow Sell signal if RSI is above the oversold threshold
        return rsi_val > config['rsi_oversold']
    return False # Should not happen if side is always "Buy" or "Sell"

# --- Execute Trade Function ---
def _execute_trade(session, side, symbol, category, quantity, config, current_price, signal_type, current_position=None):
    """Executes market orders for entry or exit. Handles quantity formatting and validation."""
    order_qty_decimal = Decimal('0')
    order_side = side # Default to the requested side (Buy/Sell) for entries

    # Determine order quantity and side based on whether it's an entry or closing a position
    if current_position:
        # Closing an existing position
        order_side = "Sell" if current_position['side'] == "Buy" else "Buy" # Opposite side for closing
        order_qty_decimal = to_decimal(current_position['size']) # Use the full size of the open position
        is_close_order = True
        log_suffix = f"Closing {current_position['side']} position"
        print(NEON_POSITION + f"Attempting to close {current_position['side']} position, Size: {order_qty_decimal:.10f}..." + NEON_RESET)
    else:
        # Placing an entry order
        order_qty_decimal = to_decimal(quantity, rounding=ROUND_DOWN) # Use ROUND_DOWN for calculations before final formatting
        is_close_order = False
        log_suffix = f"Opening {side} position"
        print(NEON_SIGNAL + f"Attempting to open {side} position, Calculated Size: {order_qty_decimal:.10f}..." + NEON_RESET)

    # --- Quantity Validation and Formatting ---
    if order_qty_decimal <= Decimal('0'):
        print(NEON_WARNING + f"{log_suffix} failed: Quantity is zero or negative ({order_qty_decimal})." + NEON_RESET)
        return False

    # Apply symbol-specific rules for quantity formatting (min_qty, step size)
    formatted_qty_str = format_quantity(order_qty_decimal, symbol)

    # Check if formatting resulted in zero quantity (e.g., below minimum step/qty)
    if formatted_qty_str == '0.00000000':
        print(NEON_WARNING + f"{log_suffix} failed: Formatted quantity is zero after applying {symbol} rules." + NEON_RESET)
        return False

    # Re-check against max position size constraint for entries
    if not is_close_order:
        max_size = config['max_position_size']
        # Convert formatted string back to Decimal for comparison
        entry_qty_decimal = to_decimal(formatted_qty_str)
        if entry_qty_decimal > max_size:
            print(NEON_WARNING + f"Entry position size {formatted_qty_str} exceeds configured max {max_size:.8f}. Clamping to max size." + NEON_RESET)
            # Reformat the clamped quantity
            formatted_qty_str = format_quantity(max_size, symbol)
            # Check if clamping resulted in invalid quantity
            if formatted_qty_str == '0.00000000':
                 print(NEON_ERROR + "Max position size is invalid after formatting. Cannot proceed." + NEON_RESET)
                 return False

    # --- Log Trade Details ---
    log_msg = f"Executing Trade: Side={order_side}, Qty={formatted_qty_str}, Symbol={symbol}, Signal={signal_type} ({log_suffix}) at Price={current_price}"
    print(NEON_INFO + log_msg + NEON_RESET)
    logging.info(log_msg)

    # --- Place Order via API ---
    try:
        response = session.place_order(
            category=category,
            symbol=symbol,
            side=order_side,
            orderType="Market", # Use Market order for immediate execution
            qty=formatted_qty_str,
            reduceOnly=is_close_order, # Important flag for closing orders
            timeInForce="GTC" # Good Till Cancelled (standard for market orders)
        )

        # Check response for success (orderId)
        order_id = response.get('result', {}).get('orderId')
        if order_id:
            print(NEON_SUCCESS + f"Market order placed successfully. Order ID: {order_id}" + NEON_RESET)
            logging.info(f"Market order success: {response}")

            # Send notifications if enabled
            try: # Termux toast notification
                termux_msg = f"{signal_type} executed on {symbol}!"
                subprocess.run(["termux-toast", termux_msg], check=False) # Non-blocking call
            except Exception: pass # Ignore errors if termux-toast is not available
            if config['email_notify']: # Email notification
                subject = f"Trade Executed: {symbol}"
                body = f"Signal Type: {signal_type}\nAction: {order_side}\nQuantity: {formatted_qty_str}\nPrice: {current_price}\nOrder ID: {order_id}\nStatus: {log_suffix}"
                _send_email(config, subject, body)

            time.sleep(config['close_delay']) # Add delay after successful order confirmation
            return True # Trade executed successfully
        else:
            # Order placement failed or response format unexpected
             print(NEON_ERROR + f"Order placement failed, no Order ID received. Response: {response}" + NEON_RESET)
             logging.error(f"Order placement failed, no Order ID. Response: {response}")
             return False

    except Exception as e:
        # Catch API exceptions (e.g., network errors, invalid parameters, specific Bybit errors)
        error_msg = str(e)
        print(NEON_ERROR + f"Trade execution failed during API call: {error_msg}" + NEON_RESET)
        logging.error(f"Trade execution failed: {error_msg}. Details: side={order_side}, qty={formatted_qty_str}, price={current_price}, signal={signal_type}", exc_info=True)

        # Provide user-friendly hints for common issues based on error message
        if "Insufficient margin" in error_msg:
            print(NEON_ERROR + " -> Insufficient margin. Consider reducing position size, leverage, or checking available balance." + NEON_RESET)
        elif "Invalid quantity" in error_msg or "step incorrect" in error_msg or "min_qty" in error_msg:
             print(NEON_ERROR + f" -> Invalid quantity ({formatted_qty_str}). Check minimum quantity, step size, and max position size rules for {symbol} in config." + NEON_RESET)
        elif "symbol does not exist" in error_msg or "invalid symbol" in error_msg:
             print(NEON_ERROR + f" -> Invalid symbol '{symbol}'. Check the 'symbol' configuration and ensure it matches Bybit's format." + NEON_RESET)
        elif "connection timed out" in error_msg or "Read timed out" in error_msg:
             print(NEON_ERROR + " -> API connection timed out. Check network or increase API timeout in config." + NEON_RESET)
        # Add more specific error handling as needed based on Bybit API error codes/messages
        return False # Indicate trade execution failure

# --- Send Email Notification ---
def _send_email(config, subject, body):
    """Sends an email notification if configured."""
    sender = config.get('email_sender')
    password = config.get('email_password')
    receiver = config.get('email_receiver')

    # Check if email configuration is complete
    if not all([sender, password, receiver]):
        print(NEON_WARNING + "Email configuration incomplete (sender, password, receiver). Skipping notification." + NEON_RESET)
        return

    try:
        # Create email message object
        msg = MIMEText(body)
        msg['Subject'] = f"[Bybit Bot] {subject}" # Add prefix to subject line
        msg['From'] = sender
        msg['To'] = receiver

        # Use SMTP_SSL for secure connection (standard for Gmail)
        smtp_server = "smtp.gmail.com" # Assuming Gmail; adjust if using another provider
        smtp_port = 465
        server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        server.login(sender, password) # Login using credentials
        server.sendmail(sender, receiver, msg.as_string()) # Send the email
        server.quit() # Close the connection
        print(NEON_INFO + "Email ether sent successfully." + NEON_RESET)
    except smtplib.SMTPAuthenticationError:
        print(NEON_ERROR + "Email authentication failed. Check sender email/password or ensure 'less secure app access'/'App Password' is enabled in your email account settings." + NEON_RESET)
        logging.error("Email authentication failed.")
    except Exception as e:
        print(NEON_ERROR + f"Email dispatch process disrupted: {e}" + NEON_RESET)
        logging.error(f"Email dispatch failed: {e}", exc_info=True)

# --- Calculate Position Quantity ---
def _calculate_quantity(balance, entry_price, stop_distance_in_usdt, config, symbol):
    """Calculates position size (in base currency, e.g., BTC) based on risk percentage and stop distance."""
    balance = to_decimal(balance)
    entry_price = to_decimal(entry_price)
    stop_distance_in_usdt = to_decimal(stop_distance_in_usdt) # Ensure stop distance is Decimal
    risk_pct = config['risk_pct']
    max_pos_size = config['max_position_size']

    # --- Input Validation ---
    if not all([balance > Decimal('0'), entry_price > Decimal('0'), stop_distance_in_usdt > Decimal('0'), risk_pct > Decimal('0')]):
        print(NEON_WARNING + f"Invalid input for quantity calculation: Balance={balance}, Entry={entry_price}, StopDist={stop_distance_in_usdt}, Risk%={risk_pct}. Returning 0 quantity." + NEON_RESET)
        return Decimal('0')

    # --- Risk-Based Calculation ---
    # Calculate the maximum amount of USDT to risk based on equity and risk percentage
    risk_amount_usdt = balance * risk_pct

    # Calculate the quantity based on risk amount and stop distance
    # Formula: Quantity = Risk Amount (USDT) / Stop Distance (USDT per Base Unit)
    quantity = risk_amount_usdt / stop_distance_in_usdt

    # --- Apply Constraints ---
    # 1. Clamp quantity by maximum position size defined in config
    quantity = min(quantity, max_pos_size)

    # 2. Ensure quantity adheres to symbol-specific rules (min_qty, step size) using format_quantity helper
    formatted_qty_str = format_quantity(quantity, symbol)
    final_quantity = to_decimal(formatted_qty_str) # Convert back to Decimal after formatting

    if final_quantity <= Decimal('0'):
         print(NEON_WARNING + "Calculated quantity became zero after applying symbol rules. No trade possible." + NEON_RESET)
         return Decimal('0')

    print(NEON_DEBUG + f"Calculated Quantity: {final_quantity:.8f} (Input Balance={balance:.4f}, Entry={entry_price}, StopDist={stop_distance_in_usdt}, Risk%={risk_pct:.2%}, MaxSize={max_pos_size:.8f}, SymbolRules applied)" + NEON_RESET)
    return final_quantity


# --- Backtest Simulation ---
def _run_backtest(df_ind, config):
    """Simulates trading strategy performance using historical data."""
    print(NEON_INFO + "Starting backtest simulation..." + NEON_RESET)
    initial_equity = to_decimal(10000.0) # Starting equity for simulation
    equity = initial_equity
    positions = [] # Stores currently open positions: {'side': 'Buy'/'Sell', 'qty': Decimal, 'entry_price': Decimal, 'entry_time': datetime, 'stop_level': Decimal}
    trades = [] # Stores records of closed trades for analysis

    # Define indicator column names dynamically based on config
    st_dir_col = f"SUPERTd_{config['super_trend_length']}_{config['super_trend_multiplier']}"
    rsi_col = 'rsi'
    ce_long_col = 'chandelier_exit_long'
    ce_short_col = 'chandelier_exit_short'
    stoch_rsi_k_name, stoch_rsi_d_name = None, None
    if config.get('use_stochrsi_crossover', False):
        stoch_k_len = config.get('stochrsi_k_period', 14)
        stoch_d_len = config.get('stochrsi_d_period', 3)
        stoch_rsi_k_name = f'STOCHRSIk_{stoch_k_len}_{stoch_d_len}'
        stoch_rsi_d_name = f'STOCHRSId_{stoch_k_len}_{stoch_d_len}'

    use_ce = config.get('use_chandelier_exit', False)
    fallback_stop_pct = config['stop_loss_pct'] # Percentage for fallback stop loss

    last_st_dir = None # Track previous Supertrend direction for signal detection

    # Iterate through each candle in the historical data
    for i in range(len(df_ind)):
        current = df_ind.iloc[i] # Current candle data
        st_dir = current.get(st_dir_col) # Supertrend direction (-1 or 1)
        close = to_decimal(current.get('close')) # Current closing price
        rsi = to_decimal(current.get(rsi_col)) # Current RSI value
        st_time = current['startTime'] # Timestamp of the current candle

        # Safely get optional indicator values (Chandelier Exit, Stoch RSI)
        ce_long = to_decimal(current.get(ce_long_col)) if use_ce and ce_long_col in current else None
        ce_short = to_decimal(current.get(ce_short_col)) if use_ce and ce_short_col in current else None
        stoch_k_curr = to_decimal(current.get(stoch_rsi_k_name)) if stoch_rsi_k_name and stoch_rsi_k_name in current else None
        stoch_d_curr = to_decimal(current.get(stoch_rsi_d_name)) if stoch_rsi_d_name and stoch_rsi_d_name in current else None
        # Get previous candle's Stoch RSI values for crossover detection
        stoch_k_prev, stoch_d_prev = None, None
        if i > 0: # Ensure we have previous candle data
            prev_data = df_ind.iloc[i-1]
            # Check if Stoch RSI columns exist in previous data before accessing
            if stoch_rsi_k_name in prev_data and stoch_rsi_d_name in prev_data:
                 stoch_k_prev = to_decimal(prev_data.get(stoch_rsi_k_name))
                 stoch_d_prev = to_decimal(prev_data.get(stoch_rsi_d_name))

        # Determine Stoch RSI crossover events
        stoch_rsi_cross_up = stoch_k_prev is not None and stoch_d_prev is not None and stoch_k_curr is not None and stoch_d_curr is not None and stoch_k_prev < stoch_d_prev and stoch_k_curr > stoch_d_curr
        stoch_rsi_cross_down = stoch_k_prev is not None and stoch_d_prev is not None and stoch_k_curr is not None and stoch_d_curr is not None and stoch_k_prev > stoch_d_prev and stoch_k_curr < stoch_d_curr

        # --- Determine Exit Conditions ---
        st_flip_up = last_st_dir == -1 and st_dir == 1 # Supertrend flipped up
        st_flip_down = last_st_dir == 1 and st_dir == -1 # Supertrend flipped down
        rsi_extreme_up = rsi > config['rsi_overbought'] # RSI is overbought
        rsi_extreme_down = rsi < config['rsi_oversold'] # RSI is oversold

        exit_reason = None # Reason for closing the position
        should_close_position = False

        # Check if there's an active position to potentially close
        if positions:
            pos = positions[-1] # Assume only one position is open at a time
            current_stop_level = pos.get('stop_level') # Get the active stop level if set

            # 1. Chandelier Exit Condition: Price crosses below Long CE (for Long pos) or above Short CE (for Short pos)
            close_chandelier = False
            if pos['side'] == 'Buy' and use_ce and ce_long is not None and close < ce_long:
                close_chandelier = True
                exit_reason = "Chandelier Exit"
            elif pos['side'] == 'Sell' and use_ce and ce_short is not None and close > ce_short:
                close_chandelier = True
                exit_reason = "Chandelier Exit"

            # 2. Reversal Signal Condition: Supertrend flip combined with RSI or Stoch RSI extremes
            close_reversal = False
            if pos['side'] == 'Buy' and st_flip_down: # Potential exit for Long if ST flips down
                 signal_ok = False
                 if config.get('use_stochrsi_crossover', False): signal_ok = stoch_rsi_cross_down # Use Stoch RSI if enabled
                 elif rsi is not None: signal_ok = rsi_extreme_down # Fallback to RSI extremes
                 if signal_ok:
                      close_reversal = True
                      exit_reason = "Reversal Signal"

            elif pos['side'] == 'Sell' and st_flip_up: # Potential exit for Short if ST flips up
                 signal_ok = False
                 if config.get('use_stochrsi_crossover', False): signal_ok = stoch_rsi_cross_up
                 elif rsi is not None: signal_ok = rsi_extreme_up
                 if signal_ok:
                      close_reversal = True
                      exit_reason = "Reversal Signal"

            # 3. Stop Loss Violation: Price hits the active trailing stop level
            violate_stop = False
            if current_stop_level is not None:
                 if pos['side'] == 'Buy' and close < current_stop_level: violate_stop = True
                 elif pos['side'] == 'Sell' and close > current_stop_level: violate_stop = True
                 if violate_stop:
                      exit_reason = "Stop Loss Hit" # Override reason if stop level is breached

            # Determine if any exit condition is met
            if close_chandelier or close_reversal or violate_stop:
                should_close_position = True

            # If closing the position, calculate PNL and record the trade
            if should_close_position:
                entry_price = pos['entry_price']
                qty = pos['qty']
                pnl = Decimal('0')
                # Calculate Profit/Loss based on position side
                if pos['side'] == 'Buy': pnl = (close - entry_price) * qty
                else: pnl = (entry_price - close) * qty # Sell side
                equity += pnl # Update equity
                # Record the closed trade details
                trades.append({
                    'entry_time': pos['entry_time'], 'exit_time': st_time, 'side': pos['side'],
                    'qty': qty, 'entry': entry_price, 'exit': close, 'pnl': pnl, 'reason': exit_reason
                })
                logging.info(f"Backtest Closed {pos['side']} ({exit_reason}): Qty={qty:.8f}, Entry={entry_price}, Exit={close}, PNL={pnl:.4f}, Equity={equity:.4f}")
                positions.pop() # Remove the closed position from the open list

        # --- Determine Entry Conditions ---
        # Only consider entries if no position is currently open and max trades allow
        if not positions and config['max_open_trades'] > 0:
             stop_distance_usdt = Decimal('0') # Initialize stop distance in USDT
             entry_signal_type = None # Type of entry signal (e.g., CE, Pct)

             # Calculate stop distance for quantity calculation
             # Prefer Chandelier Exit distance if enabled and applicable for the potential entry signal
             if use_ce and ce_long is not None and ce_short is not None:
                  # Potential Long Entry: Requires Supertrend flip up AND RSI/Stoch RSI filters met
                  if st_flip_up and _check_rsi_filter(rsi, config, "Buy"):
                       # Stop distance is the difference between current price and the Chandelier Short level
                       stop_distance_usdt = close - ce_short
                       entry_signal_type = "Entry_Long_CE"
                  # Potential Short Entry: Requires Supertrend flip down AND RSI/Stoch RSI filters met
                  elif st_flip_down and _check_rsi_filter(rsi, config, "Sell"):
                       # Stop distance is the difference between the Chandelier Long level and current price
                       stop_distance_usdt = ce_long - close
                       entry_signal_type = "Entry_Short_CE"

             # Fallback to percentage-based stop distance if Chandelier Exit isn't used or stop distance is invalid
             if stop_distance_usdt <= Decimal('0'):
                  stop_dist_pct = fallback_stop_pct
                  if stop_dist_pct > Decimal('0'):
                       if st_flip_up: # Potential Long Entry
                            stop_price = close * (Decimal('1') - stop_dist_pct) # Calculate approximate stop price
                            stop_distance_usdt = close - stop_price # Distance in USDT
                            entry_signal_type = "Entry_Long_Pct"
                       elif st_flip_down: # Potential Short Entry
                            stop_price = close * (Decimal('1') + stop_dist_pct)
                            stop_distance_usdt = stop_price - close
                            entry_signal_type = "Entry_Short_Pct"

             # Calculate position quantity if a valid stop distance was determined
             if stop_distance_usdt > Decimal('0'):
                 # Use current equity for risk calculation in backtest
                 qty = _calculate_quantity(equity, close, stop_distance_usdt, config, config['symbol'])

                 if qty > Decimal('0'): # Proceed only if calculated quantity is valid
                     # Check full entry conditions: Supertrend flip + RSI filter + (optional) Stoch RSI + (optional) Chandelier confirmation
                     buy_entry_condition = st_flip_up and _check_rsi_filter(rsi, config, "Buy")
                     sell_entry_condition = st_flip_down and _check_rsi_filter(rsi, config, "Sell")

                     # Incorporate Stoch RSI crossover if enabled
                     if config.get('use_stochrsi_crossover', False):
                         stoch_rsi_cross_up = (stoch_k_prev is not None and stoch_d_prev is not None and stoch_k_curr is not None and stoch_d_curr is not None and
                                               stoch_k_prev < stoch_d_prev and stoch_k_curr > stoch_d_curr)
                         stoch_rsi_cross_down = (stoch_k_prev is not None and stoch_d_prev is not None and stoch_k_curr is not None and stoch_d_curr is not None and
                                                 stoch_k_prev > stoch_d_prev and stoch_k_curr < stoch_d_curr)
                         buy_entry_condition = buy_entry_condition and stoch_rsi_cross_up
                         sell_entry_condition = sell_entry_condition and stoch_rsi_cross_down

                     # Add Chandelier confirmation for entries if enabled (price must be 'safe' relative to CE)
                     if use_ce:
                          buy_entry_condition = buy_entry_condition and (ce_short is not None and close > ce_short)
                          sell_entry_condition = sell_entry_condition and (ce_long is not None and close < ce_long)

                     # Execute entry trade if conditions are fully met
                     if buy_entry_condition:
                         # Calculate the initial stop level based on determined stop distance & rounding rules
                         initial_stop_price = close - stop_distance_usdt
                         # Apply rounding rules (e.g., ROUND_DOWN for stops) and ensure it's a valid price
                         stop_level = max(to_decimal(initial_stop_price, rounding=ROUND_DOWN), to_decimal('0.00000001')) # Prevent zero or negative stop

                         positions.append({'side': 'Buy', 'qty': qty, 'entry_price': close, 'entry_time': st_time, 'stop_level': stop_level})
                         logging.info(f"Backtest Opened LONG: Qty={qty:.8f}, Entry={close}, Stop={stop_level}, Equity={equity:.4f}")

                     elif sell_entry_condition:
                          initial_stop_price = close + stop_distance_usdt
                          stop_level = max(to_decimal(initial_stop_price, rounding=ROUND_UP), to_decimal('0.00000001'))

                          positions.append({'side': 'Sell', 'qty': qty, 'entry_price': close, 'entry_time': st_time, 'stop_level': stop_level})
                          logging.info(f"Backtest Opened SHORT: Qty={qty:.8f}, Entry={close}, Stop={stop_level}, Equity={equity:.4f}")

                 else: # Quantity calculated was zero after applying rules
                      print(NEON_INFO + "Calculated quantity is zero after applying symbol rules. No entry signal triggered." + NEON_RESET)
             else: # Stop distance was invalid or zero
                  print(NEON_INFO + "Invalid stop distance calculated. Cannot determine entry quantity. Observing..." + NEON_RESET)

        # --- Update State for Next Iteration ---
        # Update the last Supertrend direction *after* processing current candle's signals
        if pd.notna(st_dir):
            last_st_dir = int(st_dir)

    # --- Finalize Backtest ---
    # Close any remaining open position at the end of the backtest period
    if positions:
        pos = positions.pop() # Get the last open position
        exit_price = to_decimal(df_ind['close'].iloc[-1]) # Use the last closing price as exit
        exit_time = df_ind['startTime'].iloc[-1]
        pnl = Decimal('0')
        # Calculate PNL for the final trade
        if pos['side'] == 'Buy': pnl = (exit_price - pos['entry_price']) * pos['qty']
        else: pnl = (pos['entry_price'] - exit_price) * pos['qty']
        equity += pnl # Update equity
        # Record the final trade
        trades.append({
            'entry_time': pos['entry_time'], 'exit_time': exit_time, 'side': pos['side'],
            'qty': pos['qty'], 'entry': pos['entry_price'], 'exit': exit_price, 'pnl': pnl, 'reason': 'End of Backtest'
        })
        logging.info(f"Backtest Closed remaining {pos['side']} (End of Backtest): Qty={pos['qty']:.8f}, Entry={pos['entry_price']}, Exit={exit_price}, PNL={pnl:.4f}, Equity={equity:.4f}")

    # --- Report Backtest Results ---
    total_pnl = equity - initial_equity # Calculate total profit/loss
    print(NEON_SUCCESS + f"\n--- Backtest Complete ---")
    print(f"Initial Equity: {initial_equity:.4f} | Final Equity: {equity:.4f} | Total PNL: {total_pnl:.4f}")
    print(f"Total Trades Executed: {len(trades)}")
    # Calculate win rate, handle division by zero if no trades occurred
    win_rate = (sum(1 for t in trades if t['pnl'] > 0) / len(trades) * 100) if trades else 0
    print(f"Win Rate: {win_rate:.2f}%")
    print(f"-------------------------" + NEON_RESET)
    logging.info(f"Backtest complete: Final Equity={equity:.4f}, Total PNL={total_pnl:.4f}, Trades={len(trades)}, Win Rate={win_rate:.2f}%")

    # Generate Equity Curve Plot if enabled and data available
    if config['plot_enabled'] and trades:
        try:
            # Prepare data points for the equity curve plot
            equity_curve_points = [(df_ind['startTime'].iloc[0], initial_equity)] # Start point
            cumulative_pnl = Decimal('0')
            for t in trades:
                cumulative_pnl += t['pnl'] # Accumulate PNL from each trade
                # Add equity point at the time of trade exit
                equity_curve_points.append((t['exit_time'], initial_equity + cumulative_pnl))

            # Convert timestamps to Python datetime objects for plotting
            plot_times = [t[0].to_pydatetime() for t in equity_curve_points]
            # Plot absolute equity values
            plot_equities = [float(equity_val) for tpl in equity_curve_points for equity_val in [tpl[1]]] # Correct extraction

            plt.figure(figsize=(14, 7)) # Set figure size
            plt.plot(plot_times, plot_equities, color='cyan', marker='.', linestyle='-') # Plot the curve
            plt.title('Backtest Equity Curve', color='cyan')
            plt.xlabel('Time', color='cyan')
            plt.ylabel('Equity (USDT)', color='cyan')
            plt.grid(True, linestyle='--', alpha=0.6) # Add grid
            plt.tight_layout() # Adjust layout to prevent overlap

            # Save the plot
            plot_filename = 'backtest_equity_curve.png'
            plt.savefig(plot_filename)
            print(NEON_INFO + f"Equity curve forged as {plot_filename}." + NEON_RESET)
            plt.close() # Close the plot figure to free memory
        except Exception as e:
            print(NEON_WARNING + f"Equity curve plotting failed: {e}" + NEON_RESET)
            logging.warning(f"Equity curve plotting failed: {e}", exc_info=True)


# --- Main Trading Loop ---
def main():
    """Main function orchestrating the bot's operation (live trading or backtesting)."""
    config = _load_config() # Load configuration settings
    session = _initialize_session(config) # Initialize Bybit API session

    # Load previous state (last indicator values) if state file exists
    state = {'last_supertrend_dir': None, 'last_rsi': None}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                loaded_state = json.load(f)
                # Restore state values, ensuring keys exist
                state['last_supertrend_dir'] = loaded_state.get('last_supertrend_dir')
                state['last_rsi'] = loaded_state.get('last_rsi')
            print(NEON_SUCCESS + "State restored from " + STATE_FILE + "." + NEON_RESET)
        except Exception as e:
            print(NEON_ERROR + f"State restoration failed: {e}. Starting with fresh state." + NEON_RESET)
            logging.warning(f"Failed to load state file: {e}", exc_info=True)

    print(NEON_SUCCESS + f"\nAscended Neon Bot activated for {config['symbol']} on {'Testnet' if config['testnet'] else 'Mainnet'}!" + NEON_RESET)
    logging.info("Bot application started.")

    # --- Backtest Execution Mode ---
    if config['backtest']:
        print(NEON_INFO + "Running in Backtest Mode..." + NEON_RESET)
        try:
            # Parse backtest start and end dates into UTC timestamps
            start_dt = datetime.strptime(config['backtest_start'], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            # Add 1 day to end date to ensure the entire end day is included
            end_dt = datetime.strptime(config['backtest_end'], "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
            start_ts = int(start_dt.timestamp() * 1000)
            end_ts = int(end_dt.timestamp() * 1000)
        except ValueError as e:
            print(NEON_ERROR + f"Invalid backtest date format: {e}. Please use YYYY-MM-DD." + NEON_RESET)
            return # Exit if dates are invalid

        # Fetch historical data for the specified range
        df_hist = _fetch_kline_data(session, config['symbol'], config['category'], config['interval'], start_time=start_ts, end_time=end_ts)
        if df_hist.empty:
            print(NEON_ERROR + "Failed to fetch historical data for backtesting. Exiting." + NEON_RESET)
            return

        # Calculate indicators on the historical data
        df_ind = _calculate_indicators(df_hist.copy(), config) # Use copy to avoid modifying original fetched data
        if df_ind.empty:
            print(NEON_ERROR + "Indicator calculation failed during backtest setup. Exiting." + NEON_RESET)
            return

        # Run the backtest simulation
        _run_backtest(df_ind, config)
        print(NEON_SUCCESS + "Backtest simulation finished. Results logged and plots saved (if enabled)." + NEON_RESET)
        return # Exit the script after backtesting

    # --- Live Trading Mode ---
    print(NEON_INFO + "Entering Live Trading Loop..." + NEON_RESET)
    last_loop_check_time = time.time() # Track time for potential cycle duration monitoring

    try:
        while True: # Infinite loop for continuous operation
            current_utc_time = datetime.now(timezone.utc)
            print(f"\n--- Cycle Start: {current_utc_time.strftime('%Y-%m-%d %H:%M:%S %Z')} ---")

            # --- Fetch Data & Calculate Indicators ---
            # Determine required lookback period for indicators to ensure sufficient data
            indicator_lookback = max(
                config['super_trend_length'],
                config['rsi_length'],
                config['chandelier_atr_length'] if config.get('use_chandelier_exit', False) else 0,
                config.get('stochrsi_k_period', 14) if config.get('use_stochrsi_crossover', False) else 0
            )
            # Fetch enough candles: min 200, or enough for indicators + buffer (e.g., +10 candles)
            fetch_limit = max(200, indicator_lookback + 10)
            df = _fetch_kline_data(session, config['symbol'], config['category'], config['interval'], limit=fetch_limit)

            # Check if enough data was fetched
            if df.empty or len(df) < indicator_lookback:
                print(NEON_WARNING + f"Insufficient data fetched ({len(df)} rows, need >{indicator_lookback}). Waiting for next interval..." + NEON_RESET)
                time.sleep(DEFAULT_SLEEP_DURATION) # Wait default duration before retrying
                continue

            # Calculate indicators on the fetched data
            df_ind = _calculate_indicators(df.copy(), config) # Use copy to avoid modifying original fetched data
            if df_ind.empty:
                print(NEON_WARNING + "Indicator calculation failed. Waiting for next interval..." + NEON_RESET)
                time.sleep(DEFAULT_SLEEP_DURATION)
                continue

            # Generate plot if enabled
            if config['plot_enabled']:
                _plot_supertrend(df_ind, config)

            # --- Process Latest Candle Data ---
            current_data = df_ind.iloc[-1] # Get the most recent data point

            # Safely extract indicator values as Decimals
            st_dir_current = current_data.get(f"SUPERTd_{config['super_trend_length']}_{config['super_trend_multiplier']}")
            close_current = to_decimal(current_data.get('close'))
            rsi_current = to_decimal(current_data.get('rsi'))
            ce_long_current = to_decimal(current_data.get('chandelier_exit_long')) if config.get('use_chandelier_exit', False) else None
            ce_short_current = to_decimal(current_data.get('chandelier_exit_short')) if config.get('use_chandelier_exit', False) else None

            # Safely extract Stoch RSI values (current and previous candle) if filter is enabled
            stoch_k_curr, stoch_d_curr, stoch_k_prev, stoch_d_prev = None, None, None, None
            if config.get('use_stochrsi_crossover', False):
                stoch_k_len = config.get('stochrsi_k_period', 14)
                stoch_d_len = config.get('stochrsi_d_period', 3)
                stoch_rsi_k_name = f'STOCHRSIk_{stoch_k_len}_{stoch_d_len}'
                stoch_rsi_d_name = f'STOCHRSId_{stoch_k_len}_{stoch_d_len}'
                stoch_k_curr = to_decimal(current_data.get(stoch_rsi_k_name))
                stoch_d_curr = to_decimal(current_data.get(stoch_rsi_d_name))
                if len(df_ind) >= 2: # Ensure previous candle data is available
                    prev_data = df_ind.iloc[-2]
                    # Check if Stoch RSI columns exist in previous data before accessing
                    if stoch_rsi_k_name in prev_data and stoch_rsi_d_name in prev_data:
                         stoch_k_prev = to_decimal(prev_data.get(stoch_rsi_k_name))
                         stoch_d_prev = to_decimal(prev_data.get(stoch_rsi_d_name))

            # --- Update State & Check Signals ---
            # Determine Supertrend flip signals based on the *previous* state's direction
            st_flip_up = state.get('last_supertrend_dir') == -1 and st_dir_current == 1
            st_flip_down = state.get('last_supertrend_dir') == 1 and st_dir_current == -1

            # Update state variables for the *next* cycle *after* using the previous state
            state['last_supertrend_dir'] = int(st_dir_current) if pd.notna(st_dir_current) else None
            state['last_rsi'] = float(rsi_current) if pd.notna(rsi_current) else None
            # Save the updated state to file
            try:
                with open(STATE_FILE, 'w') as f: json.dump(state, f)
            except Exception as e:
                print(NEON_ERROR + f"State save failed: {e}" + NEON_RESET)
                logging.error(f"State save failed: {e}", exc_info=True)

            # --- Position Management ---
            # Fetch current open position details from Bybit API
            positions_response = session.get_positions(category=config['category'], symbol=config['symbol'])
            positions = positions_response.get('result', {}).get('list', [])
            current_position = None
            if positions and to_decimal(positions[0].get('size', '0')) > Decimal('0'):
                 current_position = positions[0]
                 current_position['size'] = to_decimal(current_position['size']) # Ensure size is Decimal
                 # Note: Stop level tracking for live trading is complex across restarts.
                 # Current logic relies on recalculating exits based on current indicators.

            long_pos_active = current_position and current_position['side'] == 'Buy'
            short_pos_active = current_position and current_position['side'] == 'Sell'

            balance = _get_balance(session, config) # Fetch current USDT balance for sizing calculations

            # Check for potential margin issues before placing trades
            if balance > Decimal('0'): # Only check if balance is positive
                 # Estimate margin needed for the maximum possible trade size based on config
                 required_margin_estimate = (close_current / to_decimal(config['leverage'])) * config['max_position_size']
                 # Add a buffer (e.g., 50%) to the estimated margin needed
                 if balance < required_margin_estimate * Decimal('1.5'):
                      print(NEON_WARNING + f"Low balance detected ({balance:.4f} USDT). Estimated margin for max trade ({required_margin_estimate:.4f} USDT) might be insufficient. Consider reducing risk or leverage." + NEON_RESET)

            # Display current status
            print(NEON_POSITION + f"Balance: {balance:.4f} USDT | Current Position: {'Long' if long_pos_active else 'Short' if short_pos_active else 'None'}" + NEON_RESET)
            print(f"Indicators: ST Dir={st_dir_current}, Close={close_current}, RSI={rsi_current:.2f}" + (f", CE Long={ce_long_current:.4f}, CE Short={ce_short_current:.4f}" if config.get('use_chandelier_exit') else ""))

            # --- Exit Logic: Check if an open position needs closing ---
            executed_exit = False # Flag to track if an exit trade was executed in this cycle
            exit_signal_type = None

            # Logic for closing LONG position
            if long_pos_active:
                # Chandelier Exit Condition: Price drops below Long CE level
                close_long_chandelier = config.get('use_chandelier_exit', False) and ce_long_current is not None and close_current < ce_long_current
                # Reversal Signal Condition: ST flips down + RSI filter met (and optionally Stoch RSI confirmation)
                close_long_reversal = st_flip_down and _check_rsi_filter(rsi_current, config, "Sell")
                if config.get('use_stochrsi_crossover', False): # Add Stoch RSI confirmation if enabled
                     stoch_rsi_cross_down = (stoch_k_prev is not None and stoch_d_prev is not None and stoch_k_curr is not None and stoch_d_curr is not None and
                                             stoch_k_prev > stoch_d_prev and stoch_k_curr < stoch_d_curr)
                     close_long_reversal = close_long_reversal and stoch_rsi_cross_down

                # Execute exit trade if Chandelier or Reversal signal is triggered
                if close_long_chandelier:
                    exit_signal_type = "Close_Chandelier"
                    executed_exit = _execute_trade(session, "Sell", config['symbol'], config['category'], 0, config, close_current, exit_signal_type, current_position)
                elif close_long_reversal:
                    exit_signal_type = "Close_Reversal"
                    executed_exit = _execute_trade(session, "Sell", config['symbol'], config['category'], 0, config, close_current, exit_signal_type, current_position)

            # Logic for closing SHORT position
            elif short_pos_active:
                # Chandelier Exit Condition: Price rises above Short CE level
                close_short_chandelier = config.get('use_chandelier_exit', False) and ce_short_current is not None and close_current > ce_short_current
                # Reversal Signal Condition: ST flips up + RSI filter met (and optionally Stoch RSI confirmation)
                close_short_reversal = st_flip_up and _check_rsi_filter(rsi_current, config, "Buy")
                if config.get('use_stochrsi_crossover', False): # Add Stoch RSI confirmation if enabled
                    stoch_rsi_cross_up = (stoch_k_prev is not None and stoch_d_prev is not None and stoch_k_curr is not None and stoch_d_curr is not None and
                                          stoch_k_prev < stoch_d_prev and stoch_k_curr > stoch_d_curr)
                    close_short_reversal = close_short_reversal and stoch_rsi_cross_up

                # Execute exit trade if Chandelier or Reversal signal is triggered
                if close_short_chandelier:
                    exit_signal_type = "Close_Chandelier"
                    executed_exit = _execute_trade(session, "Buy", config['symbol'], config['category'], 0, config, close_current, exit_signal_type, current_position)
                elif close_short_reversal:
                    exit_signal_type = "Close_Reversal"
                    executed_exit = _execute_trade(session, "Buy", config['symbol'], config['category'], 0, config, close_current, exit_signal_type, current_position)

            # If an exit trade was successfully executed, skip entry logic for this candle and proceed to sleep
            if executed_exit:
                 print(NEON_INFO + "Exit trade executed. Waiting for next cycle..." + NEON_RESET)
            else:
                 # --- Entry Logic: Check if a new position can be opened ---
                 if not long_pos_active and not short_pos_active and config['max_open_trades'] > 0 :
                      # Determine stop distance needed for quantity calculation based on potential entry signal
                      stop_distance_usdt = Decimal('0')
                      entry_signal_type = None

                      # Prefer Chandelier Exit distance for stop calculation if enabled and applicable
                      if config.get('use_chandelier_exit', False):
                           # Potential Long Entry Signal: ST flips up + RSI filter met
                           if st_flip_up and _check_rsi_filter(rsi_current, config, "Buy") and ce_short_current is not None:
                                # Stop distance is the difference between current price and the Chandelier Short level
                                stop_distance_usdt = close_current - ce_short_current
                                entry_signal_type = "Entry_Long_CE"
                           # Potential Short Entry Signal: ST flips down + RSI filter met
                           elif st_flip_down and _check_rsi_filter(rsi_current, config, "Sell") and ce_long_current is not None:
                                # Stop distance is the difference between the Chandelier Long level and current price
                                stop_distance_usdt = ce_long_current - close_current
                                entry_signal_type = "Entry_Short_CE"

                      # Fallback to percentage-based stop distance if Chandelier Exit is not used or stop distance is invalid
                      if stop_distance_usdt <= Decimal('0'):
                           stop_dist_pct = fallback_stop_pct
                           if stop_dist_pct > Decimal('0'):
                                if st_flip_up: # Potential Long Entry
                                     stop_price = close_current * (Decimal('1') - stop_dist_pct) # Calculate approximate stop price
                                     stop_distance_usdt = close_current - stop_price # Distance in USDT
                                     entry_signal_type = "Entry_Long_Pct"
                                elif st_flip_down: # Potential Short Entry
                                     stop_price = close_current * (Decimal('1') + stop_dist_pct)
                                     stop_distance_usdt = stop_price - close_current
                                     entry_signal_type = "Entry_Short_Pct"

                      # Calculate position quantity if a valid stop distance was determined
                      if stop_distance_usdt > Decimal('0'):
                          qty = _calculate_quantity(balance, close_current, stop_distance_usdt, config, config['symbol'])

                          if qty > Decimal('0'): # Proceed only if calculated quantity is valid
                               # Verify full entry conditions including optional filters
                               buy_entry_condition = st_flip_up and _check_rsi_filter(rsi_current, config, "Buy")
                               sell_entry_condition = st_flip_down and _check_rsi_filter(rsi_current, config, "Sell")

                               # Incorporate Stoch RSI crossover if enabled
                               if config.get('use_stochrsi_crossover', False):
                                    stoch_rsi_cross_up = (stoch_k_prev is not None and stoch_d_prev is not None and stoch_k_curr is not None and stoch_d_curr is not None and
                                                          stoch_k_prev < stoch_d_prev and stoch_k_curr > stoch_d_curr)
                                    stoch_rsi_cross_down = (stoch_k_prev is not None and stoch_d_prev is not None and stoch_k_curr is not None and stoch_d_curr is not None and
                                                            stoch_k_prev > stoch_d_prev and stoch_k_curr < stoch_d_curr)
                                    buy_entry_condition = buy_entry_condition and stoch_rsi_cross_up
                                    sell_entry_condition = sell_entry_condition and stoch_rsi_cross_down

                               # Add Chandelier confirmation for entries if enabled (price must be 'safe' relative to CE)
                               if config.get('use_chandelier_exit', False):
                                    buy_entry_condition = buy_entry_condition and (ce_short_current is not None and close_current > ce_short_current)
                                    sell_entry_condition = sell_entry_condition and (ce_long_current is not None and close_current < ce_long_current)

                               # Execute entry trade if conditions are fully met
                               if buy_entry_condition:
                                    # Calculate the initial stop level based on determined stop distance & rounding rules
                                    initial_stop_price = close_current - stop_distance_usdt
                                    # Apply rounding rules (e.g., ROUND_DOWN for stops) and ensure it's a valid price
                                    stop_level = max(to_decimal(initial_stop_price, rounding=ROUND_DOWN), to_decimal('0.00000001')) # Prevent zero or negative stop

                                    positions.append({'side': 'Buy', 'qty': qty, 'entry_price': close_current, 'entry_time': st_time, 'stop_level': stop_level})
                                    logging.info(f"Backtest Opened LONG: Qty={qty:.8f}, Entry={close_current}, Stop={stop_level}, Equity={equity:.4f}")

                               elif sell_entry_condition:
                                    initial_stop_price = close_current + stop_distance_usdt
                                    stop_level = max(to_decimal(initial_stop_price, rounding=ROUND_UP), to_decimal('0.00000001'))

                                    positions.append({'side': 'Sell', 'qty': qty, 'entry_price': close_current, 'entry_time': st_time, 'stop_level': stop_level})
                                    logging.info(f"Backtest Opened SHORT: Qty={qty:.8f}, Entry={close_current}, Stop={stop_level}, Equity={equity:.4f}")

                          else: # Quantity calculated was zero after applying rules
                               print(NEON_INFO + "Calculated quantity is zero after applying symbol rules. No entry signal triggered." + NEON_RESET)
                      else: # Stop distance was invalid or zero
                           print(NEON_INFO + "Invalid stop distance calculated. Cannot determine entry quantity. Observing..." + NEON_RESET)

                 # Log if no trade occurred (either exit happened, or no entry conditions met)
                 if not executed_exit and not (long_pos_active or short_pos_active):
                      print(NEON_INFO + "No trade signals met. Observing market..." + NEON_RESET)


            # --- Wait for Next Candle Cycle ---
            try:
                interval_minutes = int(config['interval'])
                interval_seconds = interval_minutes * 60
                # Get the start time of the last completed candle
                last_candle_start_time = df['startTime'].iloc[-1]
                # Calculate the expected start time of the next candle
                next_candle_expected_start = last_candle_start_time + timedelta(seconds=interval_seconds)
                now_utc = datetime.now(timezone.utc) # Current time

                # Calculate sleep duration until the next candle + buffer
                if next_candle_expected_start > now_utc + timedelta(seconds=10): # If next candle is sufficiently in the future
                    sleep_duration = (next_candle_expected_start - now_utc).total_seconds() + 15 # Add buffer (e.g., 15 seconds)
                else: # If we are close to or past the expected start time, wait longer to avoid rapid loops
                    print(NEON_WARNING + "Potential timing drift detected. Increasing wait time to ensure next cycle starts correctly." + NEON_RESET)
                    sleep_duration = interval_seconds + 45 # Longer wait (interval + buffer)

                sleep_duration = max(sleep_duration, 30) # Ensure a minimum sleep duration (e.g., 30 seconds)

                print(NEON_INFO + f"Sleeping for {int(sleep_duration)} seconds until next cycle..." + NEON_RESET)
                time.sleep(sleep_duration)

            except Exception as e: # Handle errors during sleep duration calculation
                 print(NEON_ERROR + f"Error calculating sleep duration: {e}. Defaulting to {DEFAULT_SLEEP_DURATION}s sleep." + NEON_RESET)
                 logging.error(f"Sleep duration calculation error: {e}", exc_info=True)
                 time.sleep(DEFAULT_SLEEP_DURATION)


    except KeyboardInterrupt: # Handle graceful shutdown via Ctrl+C
        print(NEON_INFO + "\nShutdown sequence initiated by user. Releasing ethereal bindings..." + NEON_RESET)
        logging.info("Bot shut down by user.")
    except Exception as e: # Catch any unexpected errors during live trading
        print(NEON_ERROR + f"\nCataclysmic failure in the main loop: {e}" + NEON_RESET)
        logging.critical(f"Main loop error encountered: {e}", exc_info=True) # Log full traceback for critical errors
    finally:
        # Ensure final state is saved before exiting
        print(NEON_INFO + "Saving final state and performing cleanup..." + NEON_RESET)
        try:
            with open(STATE_FILE, 'w') as f: json.dump(state, f)
        except Exception as e:
             print(NEON_ERROR + f"Final state save failed: {e}" + NEON_RESET)
        logging.info("Bot execution finished.")


if __name__ == "__main__":
    main() # Execute the main function when the script is run
