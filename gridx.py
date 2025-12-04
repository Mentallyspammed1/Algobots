#!/usr/bin/env python3
# Bybit V5 Dynamic Grid Executor - ULTIMATE ENHANCED EDITION
# Features: Dynamic Position Sizing (Risk-Based), Real-Time Sync, ATR, TA Filters, Robust Balance Fetching
# IMPORTANT: This version includes a critical time synchronization check at startup.

import argparse
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone  # Added timezone and timedelta
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from typing import Any

import numpy as np
import pandas as pd
import requests
from colorama import Fore, Style, init
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Initialize Colorama
init(autoreset=True)

# --- NEON COLOR DEFINITIONS ---
NEON_BLUE = Fore.CYAN + Style.BRIGHT
NEON_GREEN = Fore.GREEN + Style.BRIGHT
NEON_YELLOW = Fore.YELLOW + Style.BRIGHT
NEON_RED = Fore.RED + Style.BRIGHT
NEON_MAGENTA = Fore.MAGENTA + Style.BRIGHT
NEON_WHITE = Fore.WHITE + Style.BRIGHT
NEON_RESET = Style.RESET_ALL

# Load environment variables
load_dotenv()

# --- Configuration Dataclass ---
@dataclass
class BotConfig:
    """Centralized configuration for the grid bot."""
    api_key: str
    secret: str
    base_url: str
    symbol: str
    category: str
    grid_count: int = 10
    atr_length: int = 14
    atr_multiplier: float = 1.5
    test_mode: bool = False
    initial_market_buy: bool = False # Intentionally left for potential initial position
    ob_analysis: bool = True
    max_orders: int = 50
    min_profit_percent: float = 0.0015  # 0.15% minimum profit per trade
    risk_percent: float = 0.02  # Max 2% of balance per grid (Now a percentage of TOTAL available balance)
    enable_smart_filters: bool = True
    rsi_oversold: int = 30
    rsi_overbought: int = 70
    save_orders_log: bool = True
    log_file: str = "grid_bot_orders.json"

    # Cached precision and market data
    qty_precision: int = 4
    price_precision: int = 2
    min_order_qty: float = 0.0
    min_order_value: float = 0.0

    # Dynamic values
    available_balance: float = 0.0
    current_price: float = 0.0

# --- Enhanced Logging Setup ---
def setup_logging(log_to_file: bool = True):
    """Configures structured logging."""
    log_format = "%(asctime)s | %(levelname)-8s | %(message)s"
    handlers = [logging.StreamHandler()]

    if log_to_file:
        handlers.append(logging.FileHandler("grid_bot.log", mode="a"))

    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )

def log_neon(message: str, color=NEON_BLUE, level="INFO"):
    """Enhanced logging with both color output and file logging."""
    print(f"{NEON_MAGENTA}[GRID BOT]{NEON_RESET} {color}{message}{NEON_RESET}")

    # Prevent color codes in the log file
    clean_message = Style.RESET_ALL.join(message.split(Style.RESET_ALL))
    clean_message = Fore.RESET.join(clean_message.split(Fore.RESET))
    clean_message = Style.BRIGHT.join(clean_message.split(Style.BRIGHT))

    if level == "INFO":
        logging.info(clean_message)
    elif level == "WARNING":
        logging.warning(clean_message)
    elif level == "ERROR":
        logging.error(clean_message)
    elif level == "CRITICAL":
        logging.critical(clean_message)

# --- Session with Retry Logic ---
def create_session_with_retry() -> requests.Session:
    """Creates a requests session with automatic retry logic."""
    session = requests.Session()

    retry_strategy = Retry(
        total=5,  # Increased total retries
        backoff_factor=1.5, # Exponential backoff factor
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )

    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=20)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session

# Global session
API_SESSION = create_session_with_retry()

# --- Enhanced API Functions ---

def generate_signature(timestamp: str, api_key: str, recv_window: str, params: str, secret: str) -> str:
    """Generates the V5 API signature."""
    param_string = timestamp + api_key + recv_window + params
    return hmac.new(secret.encode("utf-8"), param_string.encode("utf-8"), hashlib.sha256).hexdigest()

def make_v5_request(
    endpoint: str,
    method: str,
    params: dict[str, Any],
    config: BotConfig,
    retry_count: int = 5, # Increased retry attempts
    is_public: bool = False, # Flag for truly public endpoints
) -> dict[str, Any]:
    """
    Enhanced V5 API request handler.
    For public endpoints, API key and signature are generally optional, but Bybit's API might still
    validate a provided signature if present. For private endpoints, they are mandatory.
    """
    timestamp = str(int(time.time() * 1000)) # Use local system time for API timestamp
    recv_window = "5000" # 5 seconds

    headers = {
        "Content-Type": "application/json" if method == "POST" else "application/x-www-form-urlencoded",
    }

    if not is_public: # Only add authentication headers for private endpoints
        # Determine the string to sign based on method
        if method == "GET":
            query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
            sign_body = query_string
        elif method == "POST":
            json_body = json.dumps(params)
            sign_body = json_body
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        signature = generate_signature(timestamp, config.api_key, recv_window, sign_body, config.secret)

        headers["X-BAPI-API-KEY"] = config.api_key
        headers["X-BAPI-TIMESTAMP"] = timestamp
        headers["X-BAPI-RECV-WINDOW"] = recv_window
        headers["X-BAPI-SIGN"] = signature

    for attempt in range(retry_count):
        try:
            if method == "GET":
                response = API_SESSION.get(
                    f"{config.base_url}{endpoint}",
                    params=params,
                    headers=headers,
                    timeout=15, # Increased timeout
                )
            elif method == "POST":
                response = API_SESSION.post(
                    f"{config.base_url}{endpoint}",
                    json=params,
                    headers=headers,
                    timeout=15,
                )

            response.raise_for_status()
            result = response.json()

            # Check for API-specific rate limit (retCode 10006)
            if result.get("retCode") == 10006:
                wait_time = 2 ** attempt
                log_neon(f"API Rate limited. Waiting {wait_time}s before retry...", NEON_YELLOW, "WARNING")
                time.sleep(wait_time)
                continue # Retry loop

            return result

        except requests.exceptions.HTTPError as e:
            if response.status_code == 429: # HTTP Rate limit
                wait_time = 2 ** attempt
                log_neon(f"HTTP Rate limited (429). Waiting {wait_time}s before retry...", NEON_YELLOW, "WARNING")
                time.sleep(wait_time)
                continue # Retry loop

            wait_time = 2 ** attempt
            log_neon(f"Request failed (attempt {attempt+1}/{retry_count}, Status: {response.status_code}): {e}", NEON_RED, "ERROR")

            if attempt < retry_count - 1:
                log_neon(f"Retrying in {wait_time}s...", NEON_YELLOW, "WARNING")
                time.sleep(wait_time)
            else:
                return {"retCode": -1, "retMsg": f"Max retries exceeded: {e}. Last response: {response.text}"}

        except requests.exceptions.RequestException as e:
            # Handle connection errors, timeouts etc.
            wait_time = 2 ** attempt
            log_neon(f"Connection error (attempt {attempt+1}/{retry_count}): {e}", NEON_RED, "ERROR")

            if attempt < retry_count - 1:
                log_neon(f"Retrying in {wait_time}s...", NEON_YELLOW, "WARNING")
                time.sleep(wait_time)
            else:
                return {"retCode": -1, "retMsg": f"Max retries exceeded (Connection): {e}"}

        except Exception as e:
            log_neon(f"Unexpected error in API request: {e}", NEON_RED, "ERROR")
            return {"retCode": -1, "retMsg": f"Unexpected error: {e}"}

    return {"retCode": -1, "retMsg": "Request failed after all retries"}


# --- Market Data & Account Functions ---

def get_category(symbol: str) -> str:
    """Determines trading category from symbol."""
    if symbol.endswith("USDT") or symbol.endswith("USDC"):
        return "linear"
    if symbol.endswith("USD"): # Inverse contracts
        return "inverse"
    # Spot market by default if no clear suffix
    return "spot"

def get_quote_coin(symbol: str) -> str:
    """Infer quote coin from symbol suffix."""
    quotes = [
        "USDT", "USDC", "USD", "BTC", "ETH", "EUR",
        "DAI", "BUSD", "TUSD", "FDUSD", "USDD",
    ]
    for q in quotes:
        if symbol.endswith(q):
            return q
    return "USDT"  # sensible default

def get_bybit_server_time(config: BotConfig) -> int | None:
    """Fetches Bybit's server time in milliseconds."""
    endpoint = "/v5/market/time"
    # This is a truly public endpoint, no API key or signature needed at all
    response = make_v5_request(endpoint, "GET", {}, config, is_public=True)
    if response.get("retCode") == 0 and "result" in response and "timeNano" in response["result"]:
        try:
            # FIX: timeNano is a string, cast to int before division
            time_nano_str = response["result"]["timeNano"]
            return int(time_nano_str) // 1_000_000 # Use integer division for milliseconds
        except (ValueError, TypeError) as e:
            log_neon(f"Failed to parse server time from response: {response['result']}. Error: {e}", NEON_RED, "ERROR")
            return None

    log_neon(f"Failed to fetch Bybit server time: {response.get('retMsg', 'Unknown error')}", NEON_RED, "ERROR")
    return None

def check_time_synchronization(config: BotConfig, max_drift_ms: int = 5000) -> bool:
    """
    Compares local system time with Bybit server time.
    Returns True if synchronized, False otherwise.
    Increased max_drift_ms to 5000ms to match recv_window.
    """
    log_neon("Checking time synchronization with Bybit server...", NEON_BLUE)
    bybit_time_ms = get_bybit_server_time(config)

    if bybit_time_ms is None:
        log_neon("Failed to get Bybit server time. Cannot verify synchronization. Please check internet connection.", NEON_RED, "CRITICAL")
        return False

    local_time_ms = int(time.time() * 1000)

    time_drift = abs(local_time_ms - bybit_time_ms)

    if time_drift > max_drift_ms:
        log_neon(
            f"{NEON_RED}[CRITICAL ERROR]{NEON_RESET} "
            f"Your LOCAL SYSTEM CLOCK is out of sync with Bybit server! Drift: {time_drift / 1000:.2f} seconds. "
            f"Local: {datetime.fromtimestamp(local_time_ms / 1000, tz=timezone.utc).isoformat()}Z | "
            f"Bybit: {datetime.fromtimestamp(bybit_time_ms / 1000, tz=timezone.utc).isoformat()}Z\n"
            f"{NEON_RED}Please synchronize your system clock and restart the bot. For Termux, ensure Android's 'Automatic date & time' is ON. "
            f"Trading will be unreliable or impossible with incorrect time.{NEON_RESET}",
            NEON_RED, "CRITICAL",
        )
        return False

    log_neon(f"✓ Time synchronized. Drift: {time_drift / 1000:.2f} seconds (acceptable).", NEON_GREEN)
    return True


def fetch_kline_data(symbol: str, category: str, interval: str, config: BotConfig, limit: int = 500) -> pd.DataFrame:
    """
    Fetches historical kline data.
    """
    log_neon(f"Fetching {limit} candles for {symbol} ({interval}min interval)...")
    endpoint = "/v5/market/kline"
    params = {"category": category, "symbol": symbol, "interval": interval, "limit": limit}
    response = make_v5_request(endpoint, "GET", params, config, is_public=True) # Explicitly public
    if response.get("retCode") != 0 or not response.get("result", {}).get("list"):
        log_neon(f"Kline fetch failed: {response.get('retMsg', 'Unknown error')}", NEON_RED, "ERROR")
        return pd.DataFrame()
    data_list = response["result"]["list"]
    data_list.reverse() # Oldest first
    df = pd.DataFrame(data_list, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
    # Convert to UTC-aware datetime objects
    df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].astype(float)
    df["timestamp"] = pd.to_datetime(df["timestamp"].astype(float), unit="ms", utc=True) # Make timestamps UTC-aware
    log_neon(f"✓ Loaded {len(df)} candles (from {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]})", NEON_GREEN)
    return df

def fetch_current_price(symbol: str, category: str, config: BotConfig) -> float:
    """
    Fetches current market price.
    """
    endpoint = "/v5/market/tickers"
    params = {"category": category, "symbol": symbol}
    response = make_v5_request(endpoint, "GET", params, config, is_public=True) # Explicitly public
    if response.get("retCode") == 0 and response.get("result", {}).get("list"):
        try:
            price = float(response["result"]["list"][0]["lastPrice"])
            log_neon(f"Current Price: {price:,.{config.price_precision}f}", NEON_GREEN)
            return price
        except (TypeError, ValueError, KeyError) as e:
            log_neon(f"Price parse error: {e}", NEON_RED, "ERROR")
    log_neon(f"Failed to fetch current price: {response.get('retMsg', 'Unknown error')}", NEON_RED, "ERROR")
    return 0.0

def fetch_orderbook(symbol: str, category: str, config: BotConfig, limit: int = 50) -> dict[str, list[list[str]]]:
    """
    Fetches L2 order book snapshot.
    """
    log_neon(f"Fetching Order Book for {symbol}...", NEON_BLUE)
    endpoint = "/v5/market/orderbook"
    params = {"category": category, "symbol": symbol, "limit": limit}
    response = make_v5_request(endpoint, "GET", params, config, is_public=True) # Explicitly public
    if response.get("retCode") == 0 and response.get("result"):
        result = response["result"]
        return {"bids": result["b"], "asks": result["a"]}
    log_neon(f"Order book fetch failed: {response.get('retMsg')}", NEON_RED, "ERROR")
    return {"bids": [], "asks": []}

def get_precision_info(config: BotConfig) -> bool:
    """
    Fetches official precision and minimum order requirements and updates config.
    """
    log_neon(f"Fetching instrument info for {config.symbol}...", NEON_BLUE)
    endpoint = "/v5/market/instruments-info"
    params = {"category": config.category, "symbol": config.symbol}
    response = make_v5_request(endpoint, "GET", params, config, is_public=True) # Explicitly public

    if response.get("retCode") == 0 and response.get("result", {}).get("list"):
        info = response["result"]["list"][0]
        try:
            tick_size = float(info["priceFilter"]["tickSize"])
            qty_step = float(info["lotSizeFilter"]["qtyStep"])

            config.price_precision = max(0, int(-np.log10(tick_size)))
            config.qty_precision = max(0, int(-np.log10(qty_step)))
            config.min_order_qty = float(info["lotSizeFilter"]["minOrderQty"])
            config.min_order_value = float(info["lotSizeFilter"].get("minNotionalValue", 5.0)) # Default to $5.0

            log_neon(
                f"✓ Precision updated: Qty={config.qty_precision} Price={config.price_precision} | "
                f"Min Qty={config.min_order_qty} Min Value=${config.min_order_value:,.2f}",
                NEON_GREEN,
            )
            return True
        except (KeyError, ValueError, TypeError, InvalidOperation) as e:
            log_neon(f"Failed to parse instrument info: {e}", NEON_RED, "ERROR")
            return False

    log_neon("Instrument info fetch failed. Using default precision (4, 2) and min orders (0.001, $5).", NEON_YELLOW, "WARNING")
    return False

def get_account_balance(config: BotConfig, coin: str | None = None) -> float:
    """
    Fetch available balance using V5 /v5/account/wallet-balance.
    - Tries appropriate account types in order.
    - Filters by coin for smaller responses and accuracy.
    - Uses field precedence to find the most usable 'available' value.
    NOTE: This is a private endpoint and requires proper API key permissions (Account/Wallet Read).
    """
    if coin is None:
        coin = get_quote_coin(config.symbol)

    # Priority by category
    if config.category == "spot":
        account_type_priority = ["UNIFIED", "SPOT"]
    else: # linear or inverse
        account_type_priority = ["UNIFIED", "CONTRACT"]

    for account_type in account_type_priority:
        log_neon(f"Attempting to fetch {coin} balance from {account_type} account...", NEON_BLUE)
        params = {"accountType": account_type, "coin": coin}
        resp = make_v5_request("/v5/account/wallet-balance", "GET", params, config, is_public=False) # Explicitly private

        if resp.get("retCode") != 0:
            ret_msg = resp.get("retMsg", "Unknown error")
            log_msg = f"Wallet balance query failed for accountType={account_type}: {ret_msg}"
            if "error sign" in ret_msg:
                log_msg += (
                    f"\n{NEON_RED}This is a signature error. Please check the following:\n"
                    f"1. Is your BYBIT_API_KEY and BYBIT_SECRET in the .env file correct? (Check for typos/whitespace)\n"
                    f"2. Does your API key have 'Read-Only' or 'Read/Write' permissions for Wallet/Account?\n"
                    f"3. Is your BYBIT_BASE_URL correct for your API key (Testnet vs. Mainnet)?{NEON_RESET}"
                )
            log_neon(log_msg, NEON_YELLOW, "WARNING")
            continue

        lists = resp.get("result", {}).get("list", [])
        if not lists:
            log_neon(f"No balance records found for accountType={account_type}.", NEON_YELLOW, "WARNING")
            continue

        coins_data = lists[0].get("coin", [])
        if not coins_data:
            log_neon(f"No coin data returned for accountType={account_type}.", NEON_YELLOW, "WARNING")
            continue

        target = None
        for c in coins_data:
            if c.get("coin") == coin:
                target = c
                break

        if target is None:
             log_neon(f"Coin {coin} not found in {account_type} account.", NEON_YELLOW, "WARNING")
             continue


        # Field precedence: prefer truly available for trading/withdrawal
        # availableToWithdraw is the most reliable for usable balance
        for field_name in ("availableToWithdraw", "availableBalance", "walletBalance", "equity"):
            val = target.get(field_name)
            if val is not None:
                try:
                    value = float(val)
                    if value > 0: # Only return if positive and valid
                        log_neon(
                            f"✓ Balance {coin} ({account_type}): {value:,.4f} [field={field_name}]",
                            NEON_GREEN,
                        )
                        return value
                except (TypeError, ValueError):
                    pass # Continue to next field if conversion fails

    log_neon(f"Failed to fetch a usable {coin} balance across all account types.", NEON_RED, "ERROR")
    return 0.0

# --- Advanced Technical Analysis ---

def calculate_market_indicators(df: pd.DataFrame) -> dict[str, float]:
    """Calculates multiple technical indicators for smart filtering."""
    if len(df) < 50:
        log_neon("Not enough data for full indicator calculation (need at least 50 candles).", NEON_YELLOW, "WARNING")
        return {}

    # RSI
    df.ta.rsi(length=14, append=True)
    # MACD
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    # Trend strength (ADX)
    df.ta.adx(length=14, append=True)
    # Volatility (Bollinger Bands width)
    df.ta.bbands(length=20, std=2, append=True)

    indicators = {}
    if "RSI_14" in df.columns: indicators["rsi"] = df["RSI_14"].iloc[-1]
    if "MACD_12_26_9" in df.columns: indicators["macd"] = df["MACD_12_26_9"].iloc[-1]
    if "MACDs_12_26_9" in df.columns: indicators["macd_signal"] = df["MACDs_12_26_9"].iloc[-1]
    if "MACDh_12_26_9" in df.columns: indicators["macd_histogram"] = df["MACDh_12_26_9"].iloc[-1]
    if "ADX_14" in df.columns: indicators["adx"] = df["ADX_14"].iloc[-1]

    if all(k in indicators for k in ["macd", "macd_signal"]):
        indicators["trend"] = "bullish" if indicators["macd"] > indicators["macd_signal"] else "bearish"

    if all(k in df.columns for k in ["BBU_20_2.0", "BBL_20_2.0", "BBM_20_2.0"]):
        bb_upper = df["BBU_20_2.0"].iloc[-1]
        bb_lower = df["BBL_20_2.0"].iloc[-1]
        bb_mid = df["BBM_20_2.0"].iloc[-1]
        if bb_mid != 0:
            indicators["bb_width"] = ((bb_upper - bb_lower) / bb_mid) * 100
        else:
            indicators["bb_width"] = 0.0 # Handle division by zero

    return indicators

def analyze_orderbook_sr(
    orderbook: dict[str, list[list[str]]],
    price_precision: int,
    threshold_multiplier: float = 0.5,
) -> tuple[Decimal, Decimal, float, float]:
    """Enhanced order book analysis with volume aggregation."""
    bids = orderbook.get("bids", [])
    asks = orderbook.get("asks", [])
    if not bids or not asks:
        log_neon("Order book is empty for S/R analysis.", NEON_YELLOW, "WARNING")
        return Decimal(0), Decimal(0), 0.0, 0.0

    bids_data = [(float(p[0]), float(p[1])) for p in bids]
    asks_data = [(float(p[0]), float(p[1])) for p in asks]
    all_volumes = [v for _, v in bids_data + asks_data]
    if not all_volumes: return Decimal(0), Decimal(0), 0.0, 0.0

    volume_threshold = np.percentile(all_volumes, 70) # Top 30% volumes

    max_bid_volume = 0.0
    support_price = Decimal(0)
    for price, volume in bids_data:
        if volume >= volume_threshold and volume > max_bid_volume:
            max_bid_volume = volume
            support_price = quantize_value(price, price_precision)

    max_ask_volume = 0.0
    resistance_price = Decimal(0)
    for price, volume in asks_data:
        if volume >= volume_threshold and volume > max_ask_volume:
            max_ask_volume = volume
            resistance_price = quantize_value(price, price_precision)

    return support_price, resistance_price, max_bid_volume, max_ask_volume

# --- Grid Calculation with Dynamic Sizing ---

def quantize_value(value: float, precision: int) -> Decimal:
    """Rounds value to specified precision."""
    quantizer = Decimal(10) ** (-precision)
    try:
        # Use Decimal for high precision arithmetic
        return Decimal(str(value)).quantize(quantizer, rounding=ROUND_DOWN)
    except InvalidOperation:
        return Decimal(0)

def calculate_dynamic_grid(
    df: pd.DataFrame,
    config: BotConfig,
    indicators: dict[str, float],
) -> tuple[list[Decimal], list[Decimal], Decimal, Decimal, dict[str, Any], Decimal]:
    """
    Enhanced grid calculation with:
    1. ATR-based dynamic range and asymmetry.
    2. Dynamic lot sizing based on risk_percent and available_balance.
    """
    current_price = config.current_price
    current_price_dec = quantize_value(current_price, config.price_precision)

    atr_col = f"ATR_{config.atr_length}"
    if atr_col not in df.columns:
        df.ta.atr(length=config.atr_length, append=True)

    if atr_col not in df.columns or df[atr_col].iloc[-1] == 0:
        log_neon("ATR calculation failed or returned zero. Cannot build dynamic grid.", NEON_RED, "ERROR")
        return [], [], Decimal(0), Decimal(0), {}, Decimal(0)

    latest_atr = df[atr_col].iloc[-1]

    # --- Range & Asymmetry Calculation ---
    range_multiplier = config.atr_multiplier
    buy_bias = 0.5

    if config.enable_smart_filters and indicators:
        rsi = indicators.get("rsi", 50)
        adx = indicators.get("adx", 0)
        if adx > 25:
            range_multiplier *= 1.3
            log_neon(f"Strong trend detected (ADX={adx:.1f}). Widening grid range.", NEON_YELLOW)
        if rsi < config.rsi_oversold:
            buy_bias = 0.6
            log_neon(f"Oversold condition (RSI={rsi:.1f}). Bias toward buy orders.", NEON_GREEN)
        elif rsi > config.rsi_overbought:
            buy_bias = 0.4
            log_neon(f"Overbought condition (RSI={rsi:.1f}). Bias toward sell orders.", NEON_RED)

    range_width = latest_atr * range_multiplier
    lower_range = range_width * buy_bias
    upper_range = range_width * (1 - buy_bias)
    upper_limit = current_price + upper_range
    lower_limit = current_price - lower_range

    # --- Grid Price Generation ---
    min_step = current_price * config.min_profit_percent
    total_range = upper_limit - lower_limit
    max_possible_grids = int(total_range / min_step)
    actual_grid_count = min(config.grid_count, max_possible_grids)

    if actual_grid_count < 2:
        log_neon("Calculated range too narrow or grid count too small for profitable grid.", NEON_RED, "ERROR")
        return [], [], Decimal(0), Decimal(0), {}, Decimal(0)

    grid_prices = np.linspace(lower_limit, upper_limit, actual_grid_count + 1)
    quantized_prices = [quantize_value(p, config.price_precision) for p in grid_prices]

    buy_levels = sorted([p for p in quantized_prices if p < current_price_dec], reverse=True)
    sell_levels = sorted([p for p in quantized_prices if p > current_price_dec], reverse=False) # Ensure sell levels are ascending

    # --- Dynamic Grid Order Sizing ---
    total_grid_capital = config.available_balance * config.risk_percent

    # Ensure there's at least one grid side to consider for sizing
    num_grids_to_place = max(1, len(buy_levels) + len(sell_levels))

    # Calculate average investment per grid order
    # This ensures total capital used does not exceed total_grid_capital across all new orders
    # We estimate based on total number of grid lines.
    order_value_per_trade = total_grid_capital / num_grids_to_place

    # Enforce minimum notional value
    if order_value_per_trade < config.min_order_value:
        order_value_per_trade = config.min_order_value
        log_neon(f"Calculated trade value per grid below minimum. Using min notional: ${order_value_per_trade:,.2f}", NEON_YELLOW, "WARNING")

    # Calculate quantity for the order size using the current price as a rough estimate
    order_qty_float = order_value_per_trade / current_price
    order_qty_dec = quantize_value(order_qty_float, config.qty_precision)

    # Enforce minimum order quantity
    if order_qty_dec < quantize_value(config.min_order_qty, config.qty_precision):
        order_qty_dec = quantize_value(config.min_order_qty, config.qty_precision)
        log_neon(f"Calculated quantity per grid below minimum. Using min order qty: {order_qty_dec}", NEON_YELLOW, "WARNING")

    log_neon(
        f"Dynamic Sizing: Balance=${config.available_balance:,.2f} | "
        f"Grid Capital=${total_grid_capital:,.2f} | "
        f"Order Value/Grid=${order_value_per_trade:,.2f} | "
        f"Order Qty/Grid={order_qty_dec}",
        NEON_BLUE,
    )

    grid_info = {
        "actual_count": actual_grid_count,
        "atr": latest_atr,
        "range_width": range_width,
        "buy_bias": buy_bias,
        "avg_spacing": float(total_range / actual_grid_count) if actual_grid_count > 0 else 0,
        "order_qty": order_qty_dec,
    }

    return (
        buy_levels,
        sell_levels,
        quantize_value(upper_limit, config.price_precision),
        quantize_value(lower_limit, config.price_precision),
        grid_info,
        order_qty_dec,
    )

# --- Order Management ---

@dataclass
class OrderRecord:
    """Tracks placed orders for monitoring."""
    order_id: str
    order_link_id: str
    symbol: str
    side: str
    price: Decimal
    qty: Decimal
    timestamp: datetime # This will be UTC-aware
    status: str = "submitted" # submitted, filled, cancelled, sync_error

class OrderManager:
    """Manages order placement, tracking, and synchronization."""

    def __init__(self, config: BotConfig):
        self.config = config
        self.orders: dict[str, OrderRecord] = self._load_orders_from_file() # Use dict for faster lookup

    def _load_orders_from_file(self) -> dict[str, OrderRecord]:
        """Loads order history from JSON file."""
        if not self.config.save_orders_log or not os.path.exists(self.config.log_file):
            return {}

        try:
            with open(self.config.log_file) as f:
                orders_data = json.load(f)

            loaded_orders = {}
            for data in orders_data:
                # Ensure loaded timestamps are UTC-aware if fromisoformat returns naive
                ts = datetime.fromisoformat(data["timestamp"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                record = OrderRecord(
                    order_id=data["order_id"],
                    order_link_id=data["order_link_id"],
                    symbol=data["symbol"],
                    side=data["side"],
                    price=Decimal(data["price"]),
                    qty=Decimal(data["qty"]),
                    timestamp=ts,
                    status=data["status"],
                )
                loaded_orders[record.order_link_id] = record

            log_neon(f"✓ Loaded {len(loaded_orders)} orders from {self.config.log_file}", NEON_GREEN)
            return loaded_orders
        except Exception as e:
            log_neon(f"Failed to load orders log: {e}. Starting fresh.", NEON_RED, "ERROR")
            return {}

    def save_orders_to_file(self):
        """Saves order history to JSON file."""
        if not self.config.save_orders_log:
            return

        orders_data = []
        for order in self.orders.values():
            orders_data.append({
                "order_id": order.order_id,
                "order_link_id": order.order_link_id,
                "symbol": order.symbol,
                "side": order.side,
                "price": str(order.price),
                "qty": str(order.qty),
                "timestamp": order.timestamp.isoformat(), # isoformat handles UTC correctly
                "status": order.status,
            })

        try:
            with open(self.config.log_file, "w") as f:
                json.dump(orders_data, f, indent=2)
        except Exception as e:
            log_neon(f"Failed to save orders: {e}", NEON_RED, "ERROR")

    def _track_order(self, order_id: str, side: str, price: Decimal, qty: Decimal, order_link_id: str, status: str = "submitted"):
        """Internal helper to record a newly placed order."""
        record = OrderRecord(
            order_id=order_id,
            order_link_id=order_link_id,
            symbol=self.config.symbol,
            side=side,
            price=price,
            qty=qty,
            timestamp=datetime.now(timezone.utc), # Store as UTC
            status=status,
        )
        self.orders[order_link_id] = record

    def place_limit_order(
        self,
        side: str,
        price: Decimal,
        qty: Decimal,
        order_link_id: str,
    ) -> dict[str, Any]:
        """Places a limit order with validation and tracking."""

        # Validation checks (min qty, min value)
        if qty <= 0: # Ensure positive quantity
            log_neon(f"Order quantity is zero or negative ({qty}). Skipping.", NEON_YELLOW, "WARNING")
            return {"retCode": -2, "retMsg": "Order quantity too small"}

        if qty < quantize_value(self.config.min_order_qty, self.config.qty_precision):
            log_neon(
                f"Order qty {qty} below minimum {self.config.min_order_qty}. Skipping.",
                NEON_YELLOW,
                "WARNING",
            )
            return {"retCode": -2, "retMsg": "Below minimum order quantity"}

        notional_value = float(price * qty)
        if notional_value < self.config.min_order_value:
            log_neon(
                f"Order value ${notional_value:.2f} below minimum ${self.config.min_order_value}. Skipping.",
                NEON_YELLOW,
                "WARNING",
            )
            return {"retCode": -2, "retMsg": "Below minimum order value"}

        order_params = {
            "category": self.config.category,
            "symbol": self.config.symbol,
            "side": side,
            "orderType": "Limit",
            "qty": str(qty),
            "price": str(price),
            "timeInForce": "GTC",
            "orderLinkId": order_link_id,
            "positionIdx": 0, # One-way mode
        }

        if self.config.test_mode:
            color = NEON_GREEN if side == "Buy" else NEON_RED
            log_neon(f"[TEST] {side} Limit @ {price} | Qty: {qty} | Link ID: {order_link_id}", color)
            self._track_order(
                order_id=f"TEST_{uuid.uuid4().hex[:12]}",
                side=side,
                price=price,
                qty=qty,
                order_link_id=order_link_id,
                status="TEST",
            )
            return {"retCode": 0, "result": {"orderId": self.orders[order_link_id].order_id}}

        response = make_v5_request("/v5/order/create", "POST", order_params, self.config, is_public=False) # Explicitly private

        if response.get("retCode") == 0:
            order_id = response["result"]["orderId"]
            self._track_order(order_id, side, price, qty, order_link_id)
            color = NEON_GREEN if side == "Buy" else NEON_RED
            log_neon(f"✓ {side} Limit @ {price} | Qty: {qty} | ID: {order_id[:8]}... | Link ID: {order_link_id}", color)
        else:
            log_neon(f"✗ {side} order failed: {response.get('retMsg')} | Link ID: {order_link_id}", NEON_RED, "ERROR")

        return response

    def place_market_buy(self, qty: Decimal) -> dict[str, Any]:
        """Places an initial market buy order."""

        if qty <= 0:
            log_neon(f"Market buy quantity is zero or negative ({qty}). Skipping.", NEON_YELLOW, "WARNING")
            return {"retCode": -2, "retMsg": "Order quantity too small"}

        if qty < quantize_value(self.config.min_order_qty, self.config.qty_precision):
            log_neon(
                f"Market buy qty {qty} below minimum {self.config.min_order_qty}. Skipping.",
                NEON_YELLOW,
                "WARNING",
            )
            return {"retCode": -2, "retMsg": "Below minimum order quantity"}

        order_params = {
            "category": self.config.category,
            "symbol": self.config.symbol,
            "side": "Buy",
            "orderType": "Market",
            "qty": str(qty),
            "orderLinkId": f"GRID_MKT_BUY_{int(datetime.now(timezone.utc).timestamp()*1000)}", # UTC timestamp
            "positionIdx": 0,
        }

        if self.config.test_mode:
            log_neon(f"[TEST] Market Buy | Qty: {qty}", NEON_YELLOW)
            # No actual order ID for market in test mode if not tracking fills immediately
            return {"retCode": 0, "retMsg": "Test mode - market buy simulated"}

        response = make_v5_request("/v5/order/create", "POST", order_params, self.config, is_public=False) # Explicitly private

        if response.get("retCode") == 0:
            log_neon(f"✓ Market Buy executed | Qty: {qty}", NEON_GREEN)
        else:
            log_neon(f"✗ Market Buy failed: {response.get('retMsg')}", NEON_RED, "ERROR")

        return response

    def cancel_all_open_orders(self) -> dict[str, Any]:
        """Cancels all active orders for the symbol."""
        log_neon(f"Attempting to cancel all open orders for {self.config.symbol}...", NEON_YELLOW)

        params = {
            "category": self.config.category,
            "symbol": self.config.symbol,
        }

        if self.config.test_mode:
            log_neon(f"[TEST] Simulated cancellation of all open orders for {self.config.symbol}.", NEON_YELLOW)
            # Mark all tracked orders as cancelled in local memory
            for order in self.orders.values():
                if order.status in ["submitted", "TEST"]:
                    order.status = "cancelled"
            return {"retCode": 0, "retMsg": "Test mode - cancel simulated"}

        response = make_v5_request("/v5/order/cancel-all", "POST", params, self.config, is_public=False) # Explicitly private

        if response.get("retCode") == 0:
            log_neon(f"✓ Successfully cancelled all open orders for {self.config.symbol}.", NEON_GREEN)
            # Mark all tracked orders as cancelled in local memory
            for order in self.orders.values():
                if order.status in ["submitted"]:
                    order.status = "cancelled"
            return response
        log_neon(f"✗ Failed to cancel orders: {response.get('retMsg')}", NEON_RED, "ERROR")
        return response

    def sync_open_orders(self):
        """
        Synchronizes the local order list with actual open orders on the exchange.
        This is CRITICAL for persistent grid state.
        """
        log_neon("Synchronizing local order list with exchange...", NEON_MAGENTA)

        params = {
            "category": self.config.category,
            "symbol": self.config.symbol,
            "openOnly": 1, # Only fetch open (New, PartiallyFilled) orders
        }

        response = make_v5_request("/v5/order/realtime", "GET", params, self.config, is_public=False) # Explicitly private

        if response.get("retCode") != 0:
            log_neon(f"Order sync failed: {response.get('retMsg')}", NEON_RED, "ERROR")
            return

        exchange_open_orders = {
            o["orderLinkId"]: o for o in response.get("result", {}).get("list", [])
        }

        new_local_orders = {}
        filled_or_cancelled_count = 0

        for link_id, local_order in self.orders.items():
            if link_id in exchange_open_orders:
                # Order is still open on exchange (good)
                new_local_orders[link_id] = local_order
            else:
                # Order not on exchange - it's either filled, cancelled, or expired
                if local_order.status not in ["filled", "cancelled", "TEST"]: # Don't mark test orders as filled/cancelled
                    local_order.status = "filled/cancelled" # Update status for logging
                    filled_or_cancelled_count += 1
                log_neon(f"Order {link_id} no longer open on exchange. Marking as '{local_order.status}'.", NEON_BLUE)

        self.orders = new_local_orders
        log_neon(f"✓ Sync complete. {len(self.orders)} active orders remain. {filled_or_cancelled_count} local orders cleared.", NEON_GREEN)

        # Add any valid GRID_ orders from exchange that are not in local cache (e.g. bot restart)
        for link_id, exchange_order in exchange_open_orders.items():
            if link_id not in self.orders and link_id.startswith("GRID_"):
                self._track_order(
                    order_id=exchange_order["orderId"],
                    side=exchange_order["side"],
                    price=quantize_value(float(exchange_order["price"]), self.config.price_precision),
                    qty=quantize_value(float(exchange_order["qty"]), self.config.qty_precision),
                    order_link_id=link_id,
                    status=exchange_order["orderStatus"], # Use exchange's current status
                )
                log_neon(f"⚠ Recovered and tracking open order from exchange: {link_id}", NEON_YELLOW, "WARNING")

# --- Main Logic and Execution ---

def execute_grid_cycle(config: BotConfig, manager: OrderManager):
    """Executes a single, complete grid creation and placement cycle."""

    log_neon("\n--- STARTING GRID CYCLE ---", NEON_MAGENTA)

    # 1. Fetch Market Data & Balance
    config.current_price = fetch_current_price(config.symbol, config.category, config)
    if config.current_price == 0.0:
        log_neon("Failed to get current price. Skipping cycle.", NEON_RED, "ERROR")
        return

    # Define current_price_dec for consistent Decimal operations
    current_price_dec = quantize_value(config.current_price, config.price_precision)

    quote_coin = get_quote_coin(config.symbol)
    config.available_balance = get_account_balance(config, coin=quote_coin)
    if config.available_balance == 0.0 and not config.test_mode:
        log_neon("Zero available balance (or failed to fetch). Skipping real order placement.", NEON_RED, "ERROR")
        return

    # 2. Technical Analysis & Precision
    df = fetch_kline_data(config.symbol, config.category, "15", config)
    if df.empty:
        log_neon("Failed to get historical kline data. Skipping cycle.", NEON_RED, "ERROR")
        return

    indicators = calculate_market_indicators(df)
    if config.enable_smart_filters:
        print_market_analysis(indicators, config)

    # 3. Calculate Grid Levels and Order Quantity
    buy_levels, sell_levels, upper_limit, lower_limit, grid_info, order_qty_dec = calculate_dynamic_grid(
        df, config, indicators,
    )

    if not buy_levels and not sell_levels:
        log_neon("No valid buy or sell levels generated. Skipping order placement.", NEON_RED, "ERROR")
        return

    # 4. Order Book Analysis for Display
    ob_support, ob_resistance, bid_vol, ask_vol = Decimal(0), Decimal(0), 0.0, 0.0
    if config.ob_analysis:
        orderbook = fetch_orderbook(config.symbol, config.category, config)
        ob_support, ob_resistance, bid_vol, ask_vol = analyze_orderbook_sr(
            orderbook, config.price_precision,
        )

    # 5. Print Summary
    print_grid_summary(
        buy_levels, sell_levels, upper_limit, lower_limit,
        current_price_dec,
        grid_info, config, ob_support, ob_resistance, bid_vol, ask_vol,
    )

    # 6. Synchronization & Cleanup
    manager.sync_open_orders()

    # 7. Cancel all existing orders before placing new ones to refresh the grid
    log_neon("Cancelling all existing grid orders to refresh the grid...", NEON_YELLOW)
    manager.cancel_all_open_orders()

    # 8. Place Buy and Sell Limit Orders (Dynamic Grid Refresh Strategy)

    # Place Buy Orders
    log_neon(f"\n{NEON_GREEN}--- PLACING BUY ORDERS ---{NEON_RESET}")
    for i, price in enumerate(buy_levels):
        # Create a unique link ID for each order to handle refreshes correctly
        # Using UUID for high uniqueness, combined with price for easier identification
        link_id = f"GRID_BUY_{str(price).replace('.', '_')}_{uuid.uuid4().hex[:8]}"
        manager.place_limit_order("Buy", price, order_qty_dec, link_id)
        time.sleep(0.1) # Small delay to avoid aggressive rate limits

    # Place Sell Orders
    log_neon(f"\n{NEON_RED}--- PLACING SELL ORDERS ---{NEON_RESET}")
    for i, price in enumerate(sell_levels):
        # Create a unique link ID for each order to handle refreshes correctly
        link_id = f"GRID_SELL_{str(price).replace('.', '_')}_{uuid.uuid4().hex[:8]}"
        manager.place_limit_order("Sell", price, order_qty_dec, link_id)
        time.sleep(0.1) # Small delay

    log_neon("--- GRID CYCLE COMPLETE ---", NEON_MAGENTA)
    manager.save_orders_to_file()


# --- Display Functions ---

def print_market_analysis(indicators: dict[str, float], config: BotConfig):
    """Displays comprehensive market analysis."""
    if not indicators: return

    print(f"\n{NEON_MAGENTA}{'='*70}{NEON_RESET}")
    print(f"{NEON_BLUE}--- MARKET ANALYSIS ---{NEON_RESET}")

    rsi = indicators.get("rsi", 50)
    rsi_color = NEON_GREEN if rsi < 40 else NEON_RED if rsi > 60 else NEON_YELLOW
    print(f"{NEON_WHITE}RSI(14):{NEON_RESET} {rsi_color}{rsi:.2f}{NEON_RESET}", end="")

    if rsi < config.rsi_oversold: print(f" {NEON_GREEN}[OVERSOLD - Bullish Signal]{NEON_RESET}")
    elif rsi > config.rsi_overbought: print(f" {NEON_RED}[OVERBOUGHT - Bearish Signal]{NEON_RESET}")
    else: print(f" {NEON_YELLOW}[NEUTRAL]{NEON_RESET}")

    macd = indicators.get("macd", 0)
    macd_signal = indicators.get("macd_signal", 0)
    macd_hist = indicators.get("macd_histogram", 0)
    macd_color = NEON_GREEN if macd > macd_signal else NEON_RED

    print(f"{NEON_WHITE}MACD:{NEON_RESET} {macd_color}{macd:.4f}{NEON_RESET} | Signal: {macd_signal:.4f} | Hist: {macd_hist:.4f}")

    trend = indicators.get("trend", "neutral")
    trend_color = NEON_GREEN if trend == "bullish" else NEON_RED
    adx = indicators.get("adx", 0)

    print(f"{NEON_WHITE}Trend:{NEON_RESET} {trend_color}{trend.upper()}{NEON_RESET} | ADX: {adx:.2f}", end="")

    if adx > 25: print(f" {NEON_GREEN}[STRONG]{NEON_RESET}")
    elif adx > 15: print(f" {NEON_YELLOW}[MODERATE]{NEON_RESET}")
    else: print(f" {NEON_RED}[WEAK]{NEON_RESET}")

    bb_width = indicators.get("bb_width", 0)
    vol_color = NEON_RED if bb_width > 5 else NEON_YELLOW if bb_width > 3 else NEON_GREEN
    print(f"{NEON_WHITE}Volatility (BB Width):{NEON_RESET} {vol_color}{bb_width:.2f}%{NEON_RESET}")

    print(f"{NEON_MAGENTA}{'='*70}{NEON_RESET}\n")

def print_grid_summary(
    buy_levels: list[Decimal],
    sell_levels: list[Decimal],
    upper_limit: Decimal,
    lower_limit: Decimal,
    current_price: Decimal,
    grid_info: dict[str, Any],
    config: BotConfig,
    ob_support: Decimal = Decimal(0),
    ob_resistance: Decimal = Decimal(0),
    bid_vol: float = 0.0,
    ask_vol: float = 0.0,
):
    """Enhanced grid summary display."""

    print(f"\n{NEON_MAGENTA}{'='*70}{NEON_RESET}")
    print(f"{NEON_BLUE}--- DYNAMIC GRID CONFIGURATION ---{NEON_RESET}\n")

    print(f"{NEON_WHITE}Symbol:{NEON_RESET} {NEON_YELLOW}{config.symbol}{NEON_RESET} | "
          f"{NEON_WHITE}Category:{NEON_RESET} {config.category}")

    print(f"{NEON_WHITE}Current Price:{NEON_RESET} {NEON_GREEN}${current_price:,.{config.price_precision}f}{NEON_RESET}")

    print(f"\n{NEON_WHITE}Grid Range:{NEON_RESET}")
    print(f"  Upper Limit: {NEON_RED}${upper_limit:,.{config.price_precision}f}{NEON_RESET}")
    print(f"  Lower Limit: {NEON_GREEN}${lower_limit:,.{config.price_precision}f}{NEON_RESET}")

    print(f"\n{NEON_WHITE}Grid Details:{NEON_RESET}")
    print(f"  Total Grids: {NEON_BLUE}{grid_info['actual_count']}{NEON_RESET}")
    print(f"  Buy Levels: {NEON_GREEN}{len(buy_levels)}{NEON_RESET} | Sell Levels: {NEON_RED}{len(sell_levels)}{NEON_RESET}")
    print(f"  Avg Spacing: {NEON_YELLOW}${grid_info['avg_spacing']:,.{config.price_precision}f}{NEON_RESET}")

    # Dynamic Sizing Summary
    order_qty_dec = grid_info.get("order_qty", Decimal(0))
    total_capital_at_risk = config.available_balance * config.risk_percent

    print(f"\n{NEON_WHITE}Risk & Sizing Metrics:{NEON_RESET}")
    print(f"  Total Available Capital: {NEON_GREEN}${config.available_balance:,.2f}{NEON_RESET}")
    print(f"  Max Grid Capital (Risk %): {NEON_YELLOW}${total_capital_at_risk:,.2f} ({config.risk_percent*100:.2f}%) {NEON_RESET}")
    print(f"  Order Qty/Grid (Dynamic): {NEON_BLUE}{order_qty_dec}{NEON_RESET}")

    # Order Book Analysis
    if ob_support > 0 or ob_resistance > 0:
        print(f"\n{NEON_WHITE}Order Book Levels:{NEON_RESET}")
        if ob_resistance > 0:
            print(f"  Resistance: {NEON_RED}${ob_resistance:,.{config.price_precision}f}{NEON_RESET}")
        if ob_support > 0:
            print(f"  Support: {NEON_GREEN}${ob_support:,.{config.price_precision}f}{NEON_RESET}")

    print(f"\n{NEON_MAGENTA}{'='*70}{NEON_RESET}")


# --- Main Execution ---

def parse_arguments() -> argparse.Namespace:
    """Enhanced argument parser."""
    parser = argparse.ArgumentParser(
        description=f"{NEON_BLUE}Bybit V5 Dynamic Grid Bot - Ultimate Enhanced Edition{NEON_RESET}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("symbol", type=str, help="Trading symbol (e.g., BTCUSDT)")
    parser.add_argument("--grids", type=int, default=10, help="Number of grid levels (default: 10)")
    parser.add_argument("--atr-mult", type=float, default=1.5, help="ATR multiplier for range (default: 1.5)")
    parser.add_argument("--test", action="store_true", help="Test mode - no real orders")
    parser.add_argument("--initial-market-buy", action="store_true", help="Place initial market buy (Warning: Executes once at startup)")
    parser.add_argument("--ob-analysis", action="store_true", default=True, help="Enable order book analysis (default: True)")
    parser.add_argument("--no-smart-filters", action="store_true", help="Disable RSI/MACD filters")
    parser.add_argument("--risk-percent", type=float, default=2.0, help="Max % of available balance to allocate to the grid (default: 2.0)")

    return parser.parse_args()


def main():
    """Main bot execution loop."""

    setup_logging()
    args = parse_arguments()

    # Initialize configuration
    # Add .strip() for API_KEY and SECRET to remove potential whitespace from .env
    api_key = os.getenv("BYBIT_API_KEY", "").strip()
    secret = os.getenv("BYBIT_SECRET", "").strip()

    config = BotConfig(
        api_key=api_key,
        secret=secret,
        base_url=os.getenv("BYBIT_BASE_URL", "https://api.bybit.com"), # Default to live API
        symbol=args.symbol.upper(),
        category=get_category(args.symbol.upper()), # get_category is called once here
        grid_count=args.grids,
        atr_multiplier=args.atr_mult,
        test_mode=args.test,
        initial_market_buy=args.initial_market_buy, # This flag will be set to False after first execution
        ob_analysis=args.ob_analysis,
        enable_smart_filters=not args.no_smart_filters,
        risk_percent=args.risk_percent / 100.0,
    )

    if not config.api_key or not config.secret:
        log_neon("API credentials not found in .env file! Please check BYBIT_API_KEY and BYBIT_SECRET. Ensure no extra spaces or newlines.", NEON_RED, "CRITICAL")
        return

    if len(config.api_key) < 10 or len(config.secret) < 10:
        log_neon("API Key or Secret appears to be very short. Please verify they are correct.", NEON_YELLOW, "WARNING")

    # Header
    print(f"\n{NEON_MAGENTA}{'='*70}{NEON_RESET}")
    print(f"{NEON_BLUE}🤖 BYBIT V5 DYNAMIC GRID BOT - ULTIMATE ENHANCED EDITION 🤖{NEON_RESET}")
    print(f"{NEON_MAGENTA}{'='*70}{NEON_RESET}\n")
    log_neon(f"Initializing bot for {config.symbol} ({config.category})", NEON_BLUE)

    if config.test_mode:
        log_neon("⚠ TEST MODE ENABLED - NO REAL ORDERS WILL BE PLACED ⚠", NEON_YELLOW, "WARNING")

    # --- CRITICAL TIME SYNCHRONIZATION CHECK ---
    # This check is vital. If your system clock is off, API signatures will fail.
    if not config.test_mode and not check_time_synchronization(config):
        log_neon("Bot will not proceed due to time synchronization error. Please fix your system clock and restart.", NEON_RED, "CRITICAL")
        return # Exit if time is not synced

    # Pre-flight checks: Get precision info (critical for all calculations)
    if not get_precision_info(config):
        log_neon("FATAL: Could not retrieve symbol precision info. Exiting.", NEON_RED, "CRITICAL")
        return

    # Initialize Order Manager
    order_manager = OrderManager(config)

    # Initial Market Buy (Optional, one-time execution at startup)
    if config.initial_market_buy:
        log_neon("Initial Market Buy requested. Executing one-time trade to seed position.", NEON_YELLOW)
        # Fetch current price specifically for this initial market buy
        current_price_for_initial_buy = fetch_current_price(config.symbol, config.category, config)
        if current_price_for_initial_buy == 0.0:
            log_neon("Could not get current price for initial market buy. Skipping.", NEON_RED, "ERROR")
        else:
            quote_coin = get_quote_coin(config.symbol)
            temp_balance = get_account_balance(config, coin=quote_coin) # Get fresh balance

            if temp_balance == 0.0 and not config.test_mode:
                log_neon("Cannot perform initial market buy with zero available balance (or failed to fetch).", NEON_RED, "ERROR")
            else:
                # Calculate initial buy quantity based on risk_percent, or min_order_value if too small
                temp_total_grid_capital = temp_balance * config.risk_percent
                # Use max(1, config.grid_count) to avoid division by zero if grids is 0 (though it defaults to 10)
                temp_order_value_per_trade = max(config.min_order_value, temp_total_grid_capital / max(1, config.grid_count))

                initial_qty_float = temp_order_value_per_trade / current_price_for_initial_buy
                initial_qty_dec = quantize_value(initial_qty_float, config.qty_precision)

                # Ensure initial qty meets minimums
                initial_qty_dec = max(initial_qty_dec, quantize_value(config.min_order_qty, config.qty_precision))

                if initial_qty_dec == Decimal(0):
                    log_neon("Calculated initial market buy quantity is zero. Skipping.", NEON_RED, "ERROR")
                else:
                    order_manager.place_market_buy(initial_qty_dec)

        config.initial_market_buy = False # Disable after first attempt, so it doesn't re-run in loop
        time.sleep(1) # Small pause after initial action

    # Main loop
    while True:
        try:
            execute_grid_cycle(config, order_manager)
            log_neon("Cycle complete. Sleeping for 5 minutes...", NEON_BLUE)
            time.sleep(300) # Sleep for 5 minutes (300 seconds)

        except KeyboardInterrupt:
            log_neon("\nBot stopped by user. Cancelling all open orders...", NEON_YELLOW)
            order_manager.cancel_all_open_orders()
            order_manager.save_orders_to_file()
            break
        except Exception as e:
            log_neon(f"A major error occurred: {e}", NEON_RED, "CRITICAL")
            logging.exception("Unhandled exception in main loop:") # Log full traceback
            time.sleep(60) # Wait a minute before retrying

if __name__ == "__main__":
    main()
