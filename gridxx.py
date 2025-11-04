#!/usr/bin/env python3
# Bybit V5 Dynamic Grid Executor - ULTIMATE ENHANCED EDITION (V2)
# Enhancements: Robust Position Management, Explicit Hedged Mode Setup, Improved Trade-Pairing

import os
import time
import hmac
import hashlib
import requests
import json
import numpy as np
import pandas as pd
import pandas_ta as ta
import argparse
import logging
import uuid
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_DOWN, InvalidOperation
from dotenv import load_dotenv
from colorama import Fore, Style, init
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Initialize Colorama
init(autoreset=True)

# --- NEON COLOR DEFINITIONS (Based on user preference) ---
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
    initial_market_buy: bool = False 
    ob_analysis: bool = True
    max_orders: int = 50
    min_profit_percent: float = 0.0015  # 0.15% minimum profit per trade
    risk_percent: float = 0.02  # Max 2% of total available balance for the grid
    enable_smart_filters: bool = True
    rsi_oversold: int = 30
    rsi_overbought: int = 70
    save_orders_log: bool = True
    log_file: str = "grid_bot_orders.json"
    
    # Cached precision and market data
    qty_precision: int = field(default=4)
    price_precision: int = field(default=2)
    min_order_qty: float = field(default=0.0)
    min_order_value: float = field(default=5.0) # Default Bybit min notional
    
    # Dynamic values
    available_balance: float = field(default=0.0)
    current_price: float = field(default=0.0)
    long_qty: Decimal = field(default=Decimal(0))
    short_qty: Decimal = field(default=Decimal(0))

# --- Enhanced Logging Setup ---
def setup_logging(log_to_file: bool = True):
    """Configures structured logging."""
    log_format = '%(asctime)s | %(levelname)-8s | %(message)s'
    handlers = [logging.StreamHandler()]
    
    if log_to_file:
        handlers.append(logging.FileHandler('grid_bot.log', mode='a'))
    
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=handlers
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
        allowed_methods=["GET", "POST"]
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
    return hmac.new(secret.encode('utf-8'), param_string.encode('utf-8'), hashlib.sha256).hexdigest()

def make_v5_request(
    endpoint: str,
    method: str,
    params: Dict[str, Any],
    config: BotConfig,
    retry_count: int = 5 
) -> Dict[str, Any]:
    """
    Enhanced V5 API request handler with robust retry and error logging.
    """
    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"
    
    if method == 'GET':
        query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
        sign_body = query_string
        url = f"{config.base_url}{endpoint}"
    elif method == 'POST':
        json_body = json.dumps(params)
        sign_body = json_body
        url = f"{config.base_url}{endpoint}"
    else:
        raise ValueError(f"Unsupported HTTP method: {method}")
        
    signature = generate_signature(timestamp, config.api_key, recv_window, sign_body, config.secret)
    
    headers = {
        'X-BAPI-API-KEY': config.api_key,
        'X-BAPI-TIMESTAMP': timestamp,
        'X-BAPI-RECV-WINDOW': recv_window,
        'X-BAPI-SIGN': signature,
        'Content-Type': 'application/json' if method == 'POST' else 'application/x-www-form-urlencoded'
    }
    
    for attempt in range(retry_count):
        try:
            if method == 'GET':
                response = API_SESSION.get(url, params=params, headers=headers, timeout=15)
            elif method == 'POST':
                response = API_SESSION.post(url, json=params, headers=headers, timeout=15)
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('retCode') != 0:
                # Log API-specific error code
                log_neon(f"API Error (Code {result.get('retCode')}): {result.get('retMsg')}", NEON_RED, "ERROR")
                # Specific check for 403-related issues (e.g., no permissions, wrong category)
                if result.get('retCode') in [10001, 30034]: 
                    log_neon("Potential API Key Permission/Category/IP Whitelist issue.", NEON_RED, "CRITICAL")
                
            return result
        
        except requests.exceptions.HTTPError as e:
            wait_time = 2 ** attempt
            if response.status_code == 429: # HTTP Rate limit
                log_neon(f"HTTP Rate limited (429). Waiting {wait_time}s before retry...", NEON_YELLOW, "WARNING")
            elif response.status_code == 403: # Forbidden (often bad signature/perms)
                log_neon(f"HTTP Forbidden (403). Check API Key, Secret, and Permissions. Waiting {wait_time}s before retry...", NEON_RED, "ERROR")
            else:
                log_neon(f"Request failed (Status: {response.status_code}): {e}", NEON_RED, "ERROR")
            
            if attempt < retry_count - 1:
                time.sleep(wait_time)
                continue
            else:
                return {"retCode": -1, "retMsg": f"Max retries exceeded. Last status: {response.status_code}"}
        
        except requests.exceptions.RequestException as e:
            # Handle connection errors, timeouts etc.
            wait_time = 2 ** attempt
            log_neon(f"Connection error: {e}", NEON_RED, "ERROR")
            
            if attempt < retry_count - 1:
                time.sleep(wait_time)
                continue
            else:
                return {"retCode": -1, "retMsg": f"Max retries exceeded (Connection): {e}"}
        
        except Exception as e:
            log_neon(f"Unexpected error in API request: {e}", NEON_RED, "ERROR")
            return {"retCode": -1, "retMsg": f"Unexpected error: {e}"}
    
    return {"retCode": -1, "retMsg": "Request failed after all retries"}


# --- Market Data & Account Functions ---

def fetch_kline_data(symbol: str, category: str, interval: str, config: BotConfig, limit: int = 500) -> pd.DataFrame:
    """Fetches historical kline data."""
    endpoint = "/v5/market/kline"
    params = {"category": category, "symbol": symbol, "interval": interval, "limit": limit}
    response = make_v5_request(endpoint, "GET", params, config)
    if response.get('retCode') != 0 or not response.get('result', {}).get('list'):
        log_neon(f"Kline fetch failed: {response.get('retMsg', 'Unknown error')}", NEON_RED, "ERROR")
        return pd.DataFrame()
    data_list = response['result']['list']
    data_list.reverse()
    df = pd.DataFrame(data_list, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
    df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
    df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float), unit='ms')
    return df

def fetch_current_price(symbol: str, category: str, config: BotConfig) -> float:
    """Fetches current market price."""
    endpoint = "/v5/market/tickers"
    params = {"category": category, "symbol": symbol}
    response = make_v5_request(endpoint, "GET", params, config)
    if response.get('retCode') == 0 and response.get('result', {}).get('list'):
        try:
            return float(response['result']['list'][0]['lastPrice'])
        except (TypeError, ValueError, KeyError) as e:
            log_neon(f"Price parse error: {e}", NEON_RED, "ERROR")
    return 0.0

def get_precision_info(config: BotConfig) -> bool:
    """Fetches official precision and minimum order requirements and updates config."""
    endpoint = "/v5/market/instruments-info"
    params = {"category": config.category, "symbol": config.symbol}
    response = make_v5_request(endpoint, "GET", params, config)
    
    if response.get('retCode') == 0 and response.get('result', {}).get('list'):
        info = response['result']['list'][0]
        try:
            tick_size = float(info['priceFilter']['tickSize'])
            qty_step = float(info['lotSizeFilter']['qtyStep'])
            
            config.price_precision = max(0, int(-np.log10(tick_size)))
            config.qty_precision = max(0, int(-np.log10(qty_step)))
            config.min_order_qty = float(info['lotSizeFilter']['minOrderQty'])
            config.min_order_value = float(info['lotSizeFilter'].get('minNotionalValue', 5.0))
            
            log_neon(f"✓ Precision updated: Qty={config.qty_precision} Price={config.price_precision}", NEON_GREEN)
            return True
        except (KeyError, ValueError, TypeError, InvalidOperation) as e:
            log_neon(f"Failed to parse instrument info: {e}", NEON_RED, "ERROR")
            return False
    
    log_neon("Instrument info fetch failed. Using defaults.", NEON_YELLOW, "WARNING")
    return False

def get_account_balance(config: BotConfig, coin: str = "USDT") -> float:
    """Fetches available account balance for risk management."""
    endpoint = "/v5/account/wallet-balance"
    params = {"accountType": "UNIFIED"}
    response = make_v5_request(endpoint, "GET", params, config)
    
    if response.get('retCode') == 0:
        try:
            coins = response['result']['list'][0]['coin']
            for c in coins:
                if c['coin'] == coin:
                    available = float(c['availableBalance'])
                    log_neon(f"✓ Available {coin} Balance: {available:,.2f}", NEON_GREEN)
                    return available
        except (KeyError, IndexError, TypeError) as e:
            log_neon(f"Balance parse error: {e}", NEON_RED, "ERROR")
    
    log_neon(f"Could not fetch {coin} balance", NEON_YELLOW, "WARNING")
    return 0.0

# --- NEW: Fetch Position Information (CRITICAL for Grid State) ---
def fetch_positions(config: BotConfig) -> Tuple[Decimal, Decimal]:
    """Fetches long and short position quantities in Hedged Mode."""
    endpoint = "/v5/position/list"
    params = {"category": config.category, "symbol": config.symbol}
    response = make_v5_request(endpoint, "GET", params, config)
    
    long_qty = Decimal(0)
    short_qty = Decimal(0)
    
    if response.get('retCode') == 0:
        for position in response.get('result', {}).get('list', []):
            side = position.get('side', 'None')
            size = Decimal(position.get('size', '0'))
            
            if size > 0:
                if side == 'Buy':
                    long_qty = size
                elif side == 'Sell':
                    short_qty = size
        
        log_neon(f"Current Position: Long={long_qty} | Short={short_qty}", NEON_CYAN)
    
    return long_qty, short_qty

# --- NEW: Trading Setup (Position Mode, Leverage) ---
def setup_trading_parameters(config: BotConfig, leverage: int = 5):
    """Sets position mode (Hedged) and leverage."""
    
    # Set Leverage
    set_leverage_endpoint = "/v5/position/set-leverage"
    params = {
        "category": config.category, 
        "symbol": config.symbol, 
        "buyLeverage": str(leverage), 
        "sellLeverage": str(leverage)
    }
    response = make_v5_request(set_leverage_endpoint, "POST", params, config)
    if response.get('retCode') == 0:
        log_neon(f"✓ Leverage set to {leverage}x.", NEON_GREEN)
    else:
        log_neon(f"✗ Failed to set leverage: {response.get('retMsg')}", NEON_RED, "ERROR")
        
    # Set Position Mode (CRITICAL for Neutral Grid)
    set_mode_endpoint = "/v5/position/switch-mode"
    # Mode 0: Non-Hedge (One-Way); Mode 3: Hedge Mode
    params = {
        "category": config.category, 
        "symbol": config.symbol, 
        "mode": 3 # Hedge Mode
    }
    response = make_v5_request(set_mode_endpoint, "POST", params, config)
    if response.get('retCode') == 0:
        log_neon("✓ Position Mode set to Hedged (Two-Way).", NEON_GREEN)
    else:
        # Code 110027: Cannot switch mode when there are positions or active orders
        if response.get('retCode') == 110027:
            log_neon("Position Mode already Hedged or active positions/orders exist. Skipping switch.", NEON_YELLOW, "WARNING")
        else:
            log_neon(f"✗ Failed to set position mode: {response.get('retMsg')}", NEON_RED, "ERROR")


# --- Utility Functions ---
def quantize_value(value: float, precision: int) -> Decimal:
    """Rounds value to specified precision."""
    quantizer = Decimal(10) ** (-precision)
    try:
        return Decimal(str(value)).quantize(quantizer, rounding=ROUND_DOWN)
    except InvalidOperation:
        return Decimal(0)

# (Re-use calculate_market_indicators, analyze_orderbook_sr, calculate_dynamic_grid from original)

# --- Grid Calculation with Dynamic Sizing (Adapted) ---

def calculate_dynamic_grid(
    df: pd.DataFrame,
    config: BotConfig,
    indicators: Dict[str, float]
) -> Tuple[List[Decimal], List[Decimal], Decimal, Decimal, Dict[str, Any], Decimal]:
    """
    Enhanced grid calculation with ATR-based range and dynamic lot sizing.
    (Body is the same as the original, focusing on calculating price levels and quantity)
    """
    current_price = config.current_price
    current_price_dec = quantize_value(current_price, config.price_precision)
    
    atr_col = f'ATR_{config.atr_length}'
    if atr_col not in df.columns:
        df.ta.atr(length=config.atr_length, append=True)
    
    if atr_col not in df.columns or df[atr_col].iloc[-1] == 0:
        log_neon("ATR calculation failed or returned zero. Cannot build dynamic grid.", NEON_RED, "ERROR")
        return [], [], Decimal(0), Decimal(0), {}, Decimal(0)
        
    latest_atr = df[atr_col].iloc[-1]
    
    # --- Range & Asymmetry Calculation ---
    range_multiplier = config.atr_multiplier
    buy_bias = 0.5
    
    # Smart Filters logic
    # ... (same as original) ...
    
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
        log_neon("Calculated range too narrow or grid count too small.", NEON_RED, "ERROR")
        return [], [], Decimal(0), Decimal(0), {}, Decimal(0)
    
    grid_prices = np.linspace(lower_limit, upper_limit, actual_grid_count + 1)
    quantized_prices = [quantize_value(p, config.price_precision) for p in grid_prices]
    
    buy_levels = sorted([p for p in quantized_prices if p < current_price_dec], reverse=True)
    sell_levels = sorted([p for p in quantized_prices if p > current_price_dec])
    
    # --- Dynamic Grid Order Sizing ---
    total_grid_capital = config.available_balance * config.risk_percent 
    num_grids_to_place = config.grid_count
    
    order_value_per_trade = total_grid_capital / num_grids_to_place
    
    if order_value_per_trade < config.min_order_value:
        order_value_per_trade = config.min_order_value
        log_neon(f"Calculated trade value too small. Using min notional: ${order_value_per_trade:,.2f}", NEON_YELLOW, "WARNING")
        
    order_qty_float = order_value_per_trade / current_price 
    order_qty_dec = quantize_value(order_qty_float, config.qty_precision)
    
    if order_qty_dec < config.min_order_qty:
        order_qty_dec = quantize_value(config.min_order_qty, config.qty_precision)
        log_neon(f"Calculated quantity too small. Using min order qty: {order_qty_dec}", NEON_YELLOW, "WARNING")
    
    log_neon(
        f"Dynamic Sizing: Balance=${config.available_balance:,.2f} | "
        f"Grid Capital=${total_grid_capital:,.2f} | "
        f"Order Qty/Grid={order_qty_dec}",
        NEON_BLUE
    )
    
    grid_info = {
        'actual_count': actual_grid_count,
        'atr': latest_atr,
        'range_width': range_width,
        'buy_bias': buy_bias,
        'avg_spacing': float(total_range / actual_grid_count) if actual_grid_count > 0 else 0,
        'order_qty': order_qty_dec
    }
    
    return (
        buy_levels,
        sell_levels,
        quantize_value(upper_limit, config.price_precision),
        quantize_value(lower_limit, config.price_precision),
        grid_info,
        order_qty_dec
    )


# --- Order Management (Enhanced) ---

@dataclass
class OrderRecord:
    """Tracks placed orders for monitoring."""
    order_id: str
    order_link_id: str
    symbol: str
    side: str
    position_idx: int
    price: Decimal
    qty: Decimal
    timestamp: datetime
    status: str = "submitted" # submitted, filled, cancelled, sync_error

class OrderManager:
    """Manages order placement, tracking, and synchronization."""
    
    def __init__(self, config: BotConfig):
        self.config = config
        self.orders: Dict[str, OrderRecord] = self._load_orders_from_file() 
    
    # (Re-use _load_orders_from_file and save_orders_to_file from original)

    def _load_orders_from_file(self) -> Dict[str, OrderRecord]:
        """Loads order history from JSON file."""
        if not self.config.save_orders_log or not os.path.exists(self.config.log_file):
            return {}
        
        try:
            with open(self.config.log_file, 'r') as f:
                orders_data = json.load(f)
            
            loaded_orders = {}
            for data in orders_data:
                record = OrderRecord(
                    order_id=data['order_id'],
                    order_link_id=data['order_link_id'],
                    symbol=data['symbol'],
                    side=data['side'],
                    position_idx=data.get('position_idx', 0), # Safely load new field
                    price=Decimal(data['price']),
                    qty=Decimal(data['qty']),
                    timestamp=datetime.fromisoformat(data['timestamp']),
                    status=data['status']
                )
                loaded_orders[record.order_link_id] = record
            
            log_neon(f"✓ Loaded {len(loaded_orders)} orders from {self.config.log_file}", NEON_GREEN)
            return loaded_orders
        except Exception as e:
            log_neon(f"Failed to load orders log: {e}. Starting fresh.", NEON_RED, "ERROR")
            return {}
    
    def save_orders_to_file(self):
        """Saves order history to JSON file."""
        if not self.config.save_orders_log: return
        
        orders_data = []
        for order in self.orders.values():
            orders_data.append({
                "order_id": order.order_id,
                "order_link_id": order.order_link_id,
                "symbol": order.symbol,
                "side": order.side,
                "position_idx": order.position_idx,
                "price": str(order.price),
                "qty": str(order.qty),
                "timestamp": order.timestamp.isoformat(),
                "status": order.status
            })
        
        try:
            with open(self.config.log_file, 'w') as f:
                json.dump(orders_data, f, indent=2)
        except Exception as e:
            log_neon(f"Failed to save orders: {e}", NEON_RED, "ERROR")

    def _track_order(self, order_id: str, side: str, price: Decimal, qty: Decimal, order_link_id: str, position_idx: int = 0):
        """Internal helper to record a newly placed order."""
        record = OrderRecord(
            order_id=order_id,
            order_link_id=order_link_id,
            symbol=self.config.symbol,
            side=side,
            position_idx=position_idx,
            price=price,
            qty=qty,
            timestamp=datetime.now(),
            status="submitted"
        )
        self.orders[order_link_id] = record
        
    def place_limit_order(
        self,
        side: str,
        price: Decimal,
        qty: Decimal,
        order_link_id: str,
        position_idx: int,
        is_reduce_only: bool = False
    ) -> Dict[str, Any]:
        """Places a limit order with validation and tracking."""
        
        if qty < self.config.min_order_qty or float(price * qty) < self.config.min_order_value:
            log_neon(
                f"Order failed validation: Qty {qty} < {self.config.min_order_qty} or "
                f"Value ${float(price * qty):.2f} < ${self.config.min_order_value}. Skipping.",
                NEON_YELLOW, "WARNING"
            )
            return {"retCode": -2, "retMsg": "Order failed validation"}
        
        order_params = {
            "category": self.config.category,
            "symbol": self.config.symbol,
            "side": side,
            "orderType": "Limit",
            "qty": str(qty),
            "price": str(price),
            "timeInForce": "GTC",
            "orderLinkId": order_link_id,
            "positionIdx": position_idx, # 1 for Long, 2 for Short in Hedged Mode
            "reduceOnly": is_reduce_only # Ensure no accidental reversal
        }
        
        if self.config.test_mode:
            color = NEON_GREEN if side == 'Buy' else NEON_RED
            log_neon(f"[TEST] {side} Limit @ {price} | Qty: {qty} | R/O: {is_reduce_only}", color)
            self.orders[order_link_id] = OrderRecord(
                order_id=f"TEST_{uuid.uuid4().hex[:12]}",
                order_link_id=order_link_id,
                symbol=self.config.symbol,
                side=side,
                position_idx=position_idx,
                price=price,
                qty=qty,
                timestamp=datetime.now(),
                status="TEST"
            )
            return {"retCode": 0, "result": {"orderId": self.orders[order_link_id].order_id}}

        response = make_v5_request("/v5/order/create", "POST", order_params, self.config)
        
        if response.get('retCode') == 0:
            order_id = response['result']['orderId']
            self._track_order(order_id, side, price, qty, order_link_id, position_idx)
            color = NEON_GREEN if side == 'Buy' else NEON_RED
            log_neon(f"✓ {side} Limit @ {price} | Qty: {qty} | ID: {order_id[:8]}... | R/O: {is_reduce_only}", color)
        else:
            log_neon(f"✗ {side} order failed: {response.get('retMsg')} | Link ID: {order_link_id}", NEON_RED, "ERROR")
            
        return response

    # --- NEW: Place Market Buy (Used for initial entry) ---
    def place_market_buy(self, qty: Decimal) -> Dict[str, Any]:
        """Places a single Market Buy order (positionIdx=1 for Long)."""
        order_params = {
            "category": self.config.category,
            "symbol": self.config.symbol,
            "side": "Buy",
            "orderType": "Market",
            "qty": str(qty),
            "timeInForce": "IOC",
            "orderLinkId": f"INIT_BUY_{uuid.uuid4().hex[:8]}",
            "positionIdx": 1 # Long position
        }
        
        if self.config.test_mode:
            log_neon(f"[TEST] Market Buy | Qty: {qty}", NEON_GREEN)
            return {"retCode": 0, "result": {"orderId": "TEST_MARKET"}}

        response = make_v5_request("/v5/order/create", "POST", order_params, self.config)
        
        if response.get('retCode') == 0:
            log_neon(f"✓ Initial Market Buy executed. Qty: {qty}", NEON_GREEN)
        else:
            log_neon(f"✗ Initial Market Buy failed: {response.get('retMsg')}", NEON_RED, "ERROR")
            
        return response

    def cancel_all_open_orders(self) -> Dict[str, Any]:
        """Cancels all active orders for the symbol."""
        log_neon(f"Attempting to cancel all open orders for {self.config.symbol}...", NEON_YELLOW)
        params = {"category": self.config.category, "symbol": self.config.symbol}
        response = make_v5_request("/v5/order/cancel-all", "POST", params, self.config)
        
        if response.get('retCode') == 0:
            log_neon(f"✓ Successfully cancelled all open orders for {self.config.symbol}.", NEON_GREEN)
            for order in self.orders.values():
                if order.status in ["submitted", "TEST"]:
                    order.status = "cancelled"
            return response
        else:
            log_neon(f"✗ Failed to cancel orders: {response.get('retMsg')}", NEON_RED, "ERROR")
            return response
    
    def sync_open_orders(self):
        """
        Synchronizes the local order list with actual open orders on the exchange.
        Orders not found on the exchange are removed from local tracking (assumed filled/cancelled).
        """
        log_neon("Synchronizing local order list with exchange...", NEON_MAGENTA)
        
        params = {"category": self.config.category, "symbol": self.config.symbol, "openOnly": 1}
        response = make_v5_request("/v5/order/realtime", "GET", params, self.config)
        
        if response.get('retCode') != 0:
            log_neon(f"Order sync failed: {response.get('retMsg')}", NEON_RED, "ERROR")
            return
            
        exchange_open_orders = {
            o['orderLinkId']: o for o in response.get('result', {}).get('list', [])
        }
        
        new_local_orders = {}
        for link_id, local_order in self.orders.items():
            if link_id in exchange_open_orders:
                new_local_orders[link_id] = local_order
            elif local_order.status in ["submitted", "TEST"]:
                local_order.status = "filled/removed" 
        
        self.orders = new_local_orders
        log_neon(f"✓ Sync complete. {len(self.orders)} active orders remain.", NEON_GREEN)
        
# --- Main Logic and Execution ---

def execute_grid_cycle(config: BotConfig, manager: OrderManager):
    """Executes a single, complete grid creation and placement cycle."""
    
    log_neon("\n--- STARTING GRID CYCLE ---", NEON_MAGENTA)
    
    # 1. Fetch Market Data & Balance
    config.current_price = fetch_current_price(config.symbol, config.category, config)
    if config.current_price == 0.0:
        log_neon("Failed to get current price. Skipping cycle.", NEON_RED, "ERROR")
        return
        
    config.available_balance = get_account_balance(config)
    if config.available_balance == 0.0 and not config.test_mode:
        log_neon("Zero available balance. Skipping real order placement.", NEON_RED, "ERROR")
        # return # Allow grid calculation/display even with zero balance

    # 2. Sync Positions & Orders
    config.long_qty, config.short_qty = fetch_positions(config)
    manager.sync_open_orders()
    
    # 3. Technical Analysis
    df = fetch_kline_data(config.symbol, config.category, "15", config)
    indicators = calculate_market_indicators(df)
    print_market_analysis(indicators, config)

    # 4. Calculate Grid Levels and Order Quantity
    buy_levels, sell_levels, upper_limit, lower_limit, grid_info, order_qty_dec = calculate_dynamic_grid(
        df, config, indicators
    )

    # 5. Print Summary (re-use the print_grid_summary function)
    # ...

    # 6. Cancel existing orders to prepare for fresh grid deployment
    manager.cancel_all_open_orders()
    
    # 7. Trade-Pairing Grid Placement (CRITICAL HEDGED MODE LOGIC)
    
    # In Hedged Mode (Mode=3):
    # Long positions are managed with positionIdx=1.
    # Short positions are managed with positionIdx=2.
    
    # Grid Logic: Place alternating Buy (Long Entry) and Sell (Short Entry) orders.
    # For every Buy Entry, a corresponding Sell-to-Close should be placed at the next level up (profit).
    # For every Sell Entry, a corresponding Buy-to-Close should be placed at the next level down (profit).

    # We use buy_levels (prices below current) for Buy Entry/Short Close
    # We use sell_levels (prices above current) for Sell Entry/Long Close

    # --- Buy (Long Entry) Grid & Paired Sell (Long Exit) Grid ---
    for i, buy_price in enumerate(buy_levels): # Prices below current
        # Long Entry: Buy Limit (positionIdx=1)
        long_entry_link_id = f"GRID_LONG_ENTRY_{str(buy_price).replace('.', '_')}"
        if long_entry_link_id not in manager.orders:
            manager.place_limit_order("Buy", buy_price, order_qty_dec, long_entry_link_id, position_idx=1, is_reduce_only=False)
            
        # Long Exit: Sell Limit (positionIdx=1, ReduceOnly=True)
        # Find the next higher price in the grid for profit-taking
        if i > 0: # i=0 is the lowest price, so i-1 is the next step up
            sell_exit_price = buy_levels[i-1]
            long_exit_link_id = f"GRID_LONG_EXIT_{str(buy_price).replace('.', '_')}"
            if long_exit_link_id not in manager.orders:
                manager.place_limit_order("Sell", sell_exit_price, order_qty_dec, long_exit_link_id, position_idx=1, is_reduce_only=True)


    # --- Sell (Short Entry) Grid & Paired Buy (Short Exit) Grid ---
    for i, sell_price in enumerate(sell_levels): # Prices above current
        # Short Entry: Sell Limit (positionIdx=2)
        short_entry_link_id = f"GRID_SHORT_ENTRY_{str(sell_price).replace('.', '_')}"
        if short_entry_link_id not in manager.orders:
            manager.place_limit_order("Sell", sell_price, order_qty_dec, short_entry_link_id, position_idx=2, is_reduce_only=False)

        # Short Exit: Buy Limit (positionIdx=2, ReduceOnly=True)
        # Find the next lower price in the grid for profit-taking
        if i > 0: # i=0 is the lowest price, so i-1 is the next step down
            buy_exit_price = sell_levels[i-1]
            short_exit_link_id = f"GRID_SHORT_EXIT_{str(sell_price).replace('.', '_')}"
            if short_exit_link_id not in manager.orders:
                manager.place_limit_order("Buy", buy_exit_price, order_qty_dec, short_exit_link_id, position_idx=2, is_reduce_only=True)
            
    log_neon("--- GRID CYCLE COMPLETE ---", NEON_MAGENTA)
    manager.save_orders_to_file()


# --- Main Execution ---

def parse_arguments() -> argparse.Namespace:
    """Enhanced argument parser."""
    parser = argparse.ArgumentParser(
        description=f"{NEON_BLUE}Bybit V5 Dynamic Grid Bot - Ultimate Enhanced Edition{NEON_RESET}",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('symbol', type=str, help='Trading symbol (e.g., BTCUSDT)')
    parser.add_argument('--grids', type=int, default=10, help='Number of grid levels (default: 10)')
    parser.add_argument('--atr-mult', type=float, default=1.5, help='ATR multiplier for range (default: 1.5)')
    parser.add_argument('--test', action='store_true', help='Test mode - no real orders')
    parser.add_argument('--initial-market-buy', action='store_true', help='Place initial market buy (Warning: Executes immediately)')
    parser.add_argument('--ob-analysis', action='store_true', default=True, help='Enable order book analysis (default: True)')
    parser.add_argument('--no-smart-filters', action='store_true', help='Disable RSI/MACD filters')
    parser.add_argument('--risk-percent', type=float, default=2.0, help='Max %% of available balance to allocate to the grid (default: 2.0)')
    
    return parser.parse_args()

def get_category(symbol: str) -> str:
    """Determines trading category from symbol."""
    if symbol.endswith('USDT') or symbol.endswith('USDC'):
        return "linear"
    elif symbol.endswith('USD'):
        return "inverse"
    else:
        return "spot"

def main():
    """Main bot execution loop."""
    
    setup_logging()
    args = parse_arguments()
    
    # Initialize configuration
    config = BotConfig(
        api_key=os.getenv("BYBIT_API_KEY", ""),
        secret=os.getenv("BYBIT_SECRET", ""),
        base_url=os.getenv("BYBIT_BASE_URL", "https://api-testnet.bybit.com"),
        symbol=args.symbol.upper(),
        category=get_category(args.symbol.upper()),
        grid_count=args.grids,
        atr_multiplier=args.atr_mult,
        test_mode=args.test,
        initial_market_buy=args.initial_market_buy,
        ob_analysis=args.ob_analysis,
        enable_smart_filters=not args.no_smart_filters,
        risk_percent=args.risk_percent / 100.0
    )
    
    if not config.api_key or not config.secret:
        log_neon("API credentials not found in .env file! Please check BYBIT_API_KEY and BYBIT_SECRET.", NEON_RED, "CRITICAL")
        return
    
    # Header
    print(f"\n{NEON_MAGENTA}{'='*70}{NEON_RESET}")
    print(f"{NEON_BLUE}🤖 BYBIT V5 DYNAMIC GRID BOT - ULTIMATE ENHANCED EDITION (V2) 🤖{NEON_RESET}")
    print(f"{NEON_MAGENTA}{'='*70}{NEON_RESET}\n")
    log_neon(f"Initializing bot for {config.symbol} ({config.category})", NEON_BLUE)

    # Pre-flight checks (Current Price is needed for min notional calc)
    config.current_price = fetch_current_price(config.symbol, config.category, config)
    if config.current_price == 0.0:
        log_neon("FATAL: Could not retrieve current price for initial setup. Exiting.", NEON_RED, "CRITICAL")
        return
        
    if not get_precision_info(config):
        log_neon("FATAL: Could not retrieve symbol precision info. Exiting.", NEON_RED, "CRITICAL")
        return
    
    # Setup Position Mode and Leverage (V2 Enhancement)
    if config.category in ["linear", "inverse"]:
        setup_trading_parameters(config)
    
    # Initialize Order Manager
    order_manager = OrderManager(config)
    
    # Initial Market Buy (Optional - now correctly uses the added method)
    if config.initial_market_buy:
        log_neon("Initial Market Buy requested. Executing one-time trade.", NEON_YELLOW)
        initial_qty = quantize_value(config.min_order_value / config.current_price, config.qty_precision)
        order_manager.place_market_buy(initial_qty)
    
    # Main loop
    while True:
        try:
            execute_grid_cycle(config, order_manager)
            log_neon("Cycle complete. Sleeping for 5 minutes...", NEON_BLUE)
            time.sleep(300) # Sleep for 5 minutes
            
        except KeyboardInterrupt:
            log_neon("\nBot stopped by user. Cancelling all open orders...", NEON_YELLOW)
            order_manager.cancel_all_open_orders()
            order_manager.save_orders_to_file()
            break
        except Exception as e:
            log_neon(f"A major error occurred: {e}", NEON_RED, "CRITICAL")
            time.sleep(60) # Wait a minute before retrying
            
if __name__ == "__main__":
    # Ensure to run the script using the correct filename: python gridx_ultimate.py BTCUSDT --test
    main()
