import os
import time
import json
import logging
import threading
import collections
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from pybit.unified_trading import HTTP
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from dataclasses import dataclass
from typing import Dict, Union, Tuple

import google.generativeai as genai

# =====================================================================
# INSTRUMENT SPECIFICATIONS & PRECISION MANAGEMENT
# =====================================================================

@dataclass
class InstrumentSpecs:
    """Store instrument specifications from Bybit"""
    symbol: str
    category: str
    base_currency: str
    quote_currency: str
    status: str
    
    # Price specifications
    min_price: Decimal
    max_price: Decimal
    tick_size: Decimal  # Price precision
    
    # Quantity specifications
    min_order_qty: Decimal
    max_order_qty: Decimal
    qty_step: Decimal  # Quantity precision
    
    # Leverage specifications
    min_leverage: Decimal
    max_leverage: Decimal
    leverage_step: Decimal
    
    # Position limits
    max_position_value: Decimal
    min_position_value: Decimal
    
    # Contract specifications (for derivatives)
    contract_value: Decimal = Decimal('1')
    is_inverse: bool = False
    
    # Fee rates
    maker_fee: Decimal = Decimal('0.0001')  # 0.01%
    taker_fee: Decimal = Decimal('0.0006')  # 0.06% # 0.06%

class PrecisionManager:
    """Manage decimal precision for different trading pairs"""
    
    def __init__(self, session: HTTP, logger: logging.Logger):
        self.session = session
        self.logger = logger
        self.instruments: Dict[str, InstrumentSpecs] = {}
        self.load_all_instruments()
    
    def load_all_instruments(self):
        """Load all instrument specifications from Bybit"""
        categories = ['linear', 'inverse', 'spot', 'option']
        
        for category in categories:
            try:
                response = self.session.get_instruments_info(category=category)
                
                if response['retCode'] == 0:
                    for inst in response['result']['list']:
                        symbol = inst['symbol']
                        
                        # Parse specifications based on category
                        if category in ['linear', 'inverse']:
                            specs = self._parse_derivatives_specs(inst, category)
                        elif category == 'spot':
                            specs = self._parse_spot_specs(inst, category)
                        else:  # option
                            specs = self._parse_option_specs(inst, category)
                        
                        self.instruments[symbol] = specs
                        
            except Exception as e:
                self.logger.error(f"Error loading {category} instruments: {e}")
    
    def _parse_derivatives_specs(self, inst: Dict, category: str) -> InstrumentSpecs:
        """Parse derivatives instrument specifications"""
        lot_size = inst['lotSizeFilter']
        price_filter = inst['priceFilter']
        leverage = inst['leverageFilter']
        
        return InstrumentSpecs(
            symbol=inst['symbol'],
            category=category,
            base_currency=inst['baseCoin'],
            quote_currency=inst['quoteCoin'],
            status=inst['status'],
            min_price=Decimal(price_filter['minPrice']),
            max_price=Decimal(price_filter['maxPrice']),
            tick_size=Decimal(price_filter['tickSize']),
            min_order_qty=Decimal(lot_size['minOrderQty']),
            max_order_qty=Decimal(lot_size['maxOrderQty']),
            qty_step=Decimal(lot_size['qtyStep']),
            min_leverage=Decimal(leverage['minLeverage']),
            max_leverage=Decimal(leverage['maxLeverage']),
            leverage_step=Decimal(leverage['leverageStep']),
            max_position_value=Decimal(lot_size.get('maxMktOrderQty', '1000000')),
            min_position_value=Decimal(lot_size.get('minOrderQty', '1')),
            contract_value=Decimal(inst.get('contractValue', '1')),
            is_inverse=(category == 'inverse')
        )
    
    def _parse_spot_specs(self, inst: Dict, category: str) -> InstrumentSpecs:
        """Parse spot instrument specifications"""
        lot_size = inst['lotSizeFilter']
        price_filter = inst['priceFilter']
        
        return InstrumentSpecs(
            symbol=inst['symbol'],
            category=category,
            base_currency=inst['baseCoin'],
            quote_currency=inst['quoteCoin'],
            status=inst['status'],
            min_price=Decimal(price_filter['minPrice']),
            max_price=Decimal(price_filter['maxPrice']),
            tick_size=Decimal(price_filter['tickSize']),
            min_order_qty=Decimal(lot_size['basePrecision']),
            max_order_qty=Decimal(lot_size['maxOrderQty']),
            qty_step=Decimal(lot_size['basePrecision']),
            min_leverage=Decimal('1'),
            max_leverage=Decimal('1'),
            leverage_step=Decimal('1'),
            max_position_value=Decimal(lot_size.get('maxOrderAmt', '1000000')),
            min_position_value=Decimal(lot_size.get('minOrderAmt', '1')),
            contract_value=Decimal('1'),
            is_inverse=False
        )
    
    def _parse_option_specs(self, inst: Dict, category: str) -> InstrumentSpecs:
        """Parse option instrument specifications"""
        lot_size = inst['lotSizeFilter']
        price_filter = inst['priceFilter']
        
        return InstrumentSpecs(
            symbol=inst['symbol'],
            category=category,
            base_currency=inst['baseCoin'],
            quote_currency=inst['quoteCoin'],
            status=inst['status'],
            min_price=Decimal(price_filter['minPrice']),
            max_price=Decimal(price_filter['maxPrice']),
            tick_size=Decimal(price_filter['tickSize']),
            min_order_qty=Decimal(lot_size['minOrderQty']),
            max_order_qty=Decimal(lot_size['maxOrderQty']),
            qty_step=Decimal(lot_size['qtyStep']),
            min_leverage=Decimal('1'),
            max_leverage=Decimal('1'),
            leverage_step=Decimal('1'),
            max_position_value=Decimal(lot_size.get('maxOrderQty', '1000000')),
            min_position_value=Decimal(lot_size.get('minOrderQty', '1')),
            contract_value=Decimal('1'),
            is_inverse=False
        )
    
    def round_price(self, symbol: str, price: Union[float, Decimal]) -> Decimal:
        """Round price to correct tick size"""
        if symbol not in self.instruments:
            self.logger.warning(f"Symbol {symbol} not found, using default price precision")
            return Decimal(str(price)).quantize(Decimal('0.01'))
        
        specs = self.instruments[symbol]
        price_decimal = Decimal(str(price))
        tick_size = specs.tick_size
        
        # Round to nearest tick
        rounded = (price_decimal / tick_size).quantize(Decimal('1'), rounding=ROUND_DOWN) * tick_size
        
        # Ensure within min/max bounds
        rounded = max(specs.min_price, min(rounded, specs.max_price))
        
        return rounded
    
    def round_quantity(self, symbol: str, quantity: Union[float, Decimal]) -> Decimal:
        """Round quantity to correct step size"""
        if symbol not in self.instruments:
            self.logger.warning(f"Symbol {symbol} not found, using default quantity precision")
            return Decimal(str(quantity)).quantize(Decimal('0.001'))
        
        specs = self.instruments[symbol]
        qty_decimal = Decimal(str(quantity))
        qty_step = specs.qty_step
        
        # Round down to nearest step
        rounded = (qty_decimal / qty_step).quantize(Decimal('1'), rounding=ROUND_DOWN) * qty_step
        
        # Ensure within min/max bounds
        rounded = max(specs.min_order_qty, min(rounded, specs.max_order_qty))
        
        return rounded
    
    def get_decimal_places(self, symbol: str) -> Tuple[int, int]:
        """Get decimal places for price and quantity"""
        if symbol not in self.instruments:
            return 2, 3  # Default values
        
        specs = self.instruments[symbol]
        
        # Calculate decimal places from tick size and qty step
        price_decimals = abs(specs.tick_size.as_tuple().exponent)
        qty_decimals = abs(specs.qty_step.as_tuple().exponent)
        
        return price_decimals, qty_decimals

from indicators import calculate_indicators

# --- Basic Setup ---
load_dotenv()
app = Flask(__name__)
CORS(app)

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- API Key Configuration ---
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not BYBIT_API_KEY or not BYBIT_API_SECRET:
    logging.error("CRITICAL: Bybit API Key or Secret not found. Please check your .env file.")
if not GEMINI_API_KEY:
    logging.warning("Gemini API Key not found. The insight feature will be disabled.")
else:
    genai.configure(api_key=GEMINI_API_KEY)

# --- Global Bot State ---
# This dictionary will hold the state of our trading bot.
# It's a simple way to manage state in a single-threaded Flask app with a background worker.
BOT_STATE = {
    "running": False,
    "thread": None,
    "config": {},
    "bybit_session": None,
    "logs": collections.deque(maxlen=200),
    "trade_history": {"wins": 0, "losses": 0, "history": []},
    "dashboard": {
        "currentPrice": "---",
        "priceChange": "---",
        "stDirection": "---",
        "stValue": "---",
        "rsiValue": "---",
        "rsiStatus": "---",
        "currentPosition": "None",
        "positionPnL": "---",
        "accountBalance": "---",
        "totalTrades": 0,
        "winRate": "0%",
        "botStatus": "Idle",
    },
    "last_supertrend": {"direction": 0, "value": 0},
    "previous_close": 0,
    "current_position_info": {"order_id": None, "entry_price": None, "side": None, "peak_price": None}
}

# --- Logging ---
def log_message(message, level='info'):
    """Adds a message to the in-memory log."""
    timestamp = time.strftime("%H:%M:%S")
    BOT_STATE["logs"].append({"timestamp": timestamp, "level": level, "message": message})
    
    # Also log to console
    if level == 'error':
        logging.error(message)
    elif level == 'warning':
        logging.warning(message)
    else:
        logging.info(message)

# --- Helper for API Calls with Retry and Specific Error Handling ---
def _make_api_call(api_client, method, endpoint, params=None, max_retries=3, initial_delay=1):
    """
    Generic function to make Bybit API calls with retry logic and specific error handling.
    Handles general Exceptions.
    """
    for attempt in range(max_retries):
        try:
            if method == 'get':
                response = getattr(api_client, endpoint)(**params) if params else getattr(api_client, endpoint)()
            elif method == 'post':
                response = getattr(api_client, endpoint)(**params)
            elif method == 'amend': # For amend_order
                response = getattr(api_client, endpoint)(**params)
            else:
                log_message(f"Invalid method '{method}' for API call.", "error")
                return {"retCode": 1, "retMsg": "Invalid method"}

            if response.get('retCode') == 0:
                return response
            else:
                ret_code = response.get('retCode')
                ret_msg = response.get('retMsg')
                log_message(f"Bybit API Error ({ret_code}): {ret_msg}. Retrying {endpoint} in {initial_delay * (2**attempt)}s... (Attempt {attempt + 1})", "warning")
                time.sleep(initial_delay * (2**attempt)) # Exponential backoff
        except Exception as e: # Catch any Pybit-related exceptions or other unexpected errors
            log_message(f"API call error for {endpoint}: {e}. Retrying in {initial_delay * (2**attempt)}s... (Attempt {attempt + 1})", "error")
            time.sleep(initial_delay * (2**attempt)) # Exponential backoff
        except Exception as e:
            log_message(f"Network/Client error for {endpoint}: {e}. Retrying in {initial_delay * (2**attempt)}s... (Attempt {attempt + 1})", "error")
            time.sleep(initial_delay * (2**attempt)) # Exponential backoff
    
    log_message(f"Failed to complete API call to {endpoint} after {max_retries} attempts.", "error")
    return {"retCode": 1, "retMsg": f"Failed after {max_retries} attempts: {endpoint}"}

# --- Trading Logic ---
def trading_bot_loop():
    """The main loop for the trading bot, running in a separate thread."""
    log_message("Trading bot thread started.", "success")
    
    while BOT_STATE.get("running"):
        try:
            config = BOT_STATE["config"]
            session = BOT_STATE["bybit_session"]
            dashboard = BOT_STATE["dashboard"]

            dashboard["botStatus"] = "Scanning"
            
            # 1. Fetch Kline Data
            klines_res = _make_api_call(session, 'get', 'get_kline', params={"category": "linear", "symbol": config["symbol"], "interval": config["interval"], "limit": 200})
            if klines_res.get('retCode') != 0:
                log_message(f"Failed to fetch klines: {klines_res.get('retMsg')}", "error")
                time.sleep(config.get('api_error_retry_delay', 60)) # Use configurable delay
                continue

            klines = sorted([{
                "timestamp": int(k[0]), "open": float(k[1]), "high": float(k[2]), 
                "low": float(k[3]), "close": float(k[4]), "volume": float(k[5])
            } for k in klines_res['result']['list']], key=lambda x: x['timestamp'])

            current_price = klines[-1]['close']
            
            # 2. Calculate Indicators
            indicators = calculate_indicators(klines, config)
            if not indicators:
                log_message("Insufficient data for indicators. Waiting for more klines.", "warning")
                dashboard["botStatus"] = "Waiting"
                time.sleep(config.get('indicator_wait_delay', 60)) # Use configurable delay
                continue

            # 3. Fetch Position and Balance
            position_res = _make_api_call(session, 'get', 'get_positions', params={"category": "linear", "symbol": config["symbol"]})
            balance_res = _make_api_call(session, 'get', 'get_wallet_balance', params={"accountType": "UNIFIED", "coin": "USDT"})

            current_position = None
            if position_res.get('retCode') == 0:
                pos_list = [p for p in position_res['result']['list'] if float(p.get('size', 0)) > 0]
                if pos_list:
                    current_position = pos_list[0]
            else:
                log_message(f"Failed to fetch positions: {position_res.get('retMsg')}", "error")
            
            balance = 0
            if balance_res.get('retCode') == 0 and balance_res['result']['list']:
                balance = float(balance_res['result']['list'][0]['totalWalletBalance'])
            else:
                log_message(f"Failed to fetch balance: {balance_res.get('retMsg')}", "error")

            # 4. Update Dashboard
            dashboard['currentPrice'] = f"${current_price:.{config['price_precision']}f}"
            st = indicators['supertrend']
            dashboard['stDirection'] = "UPTREND" if st['direction'] == 1 else "DOWNTREND"
            dashboard['stValue'] = f"{st['supertrend']:.{config['price_precision']}f}"
            dashboard['rsiValue'] = f"{indicators['rsi']:.2f}"
            dashboard['accountBalance'] = f"${balance:.2f}"
            dashboard['fisherValue'] = f"{indicators['fisher']:.2f}"
            dashboard['macdLine'] = f"{indicators['macd']['macd_line']:.2f}"
            dashboard['macdSignal'] = f"{indicators['macd']['signal_line']:.2f}"
            dashboard['macdHistogram'] = f"{indicators['macd']['histogram']:.2f}"
            dashboard['bbMiddle'] = f"{indicators['bollinger_bands']['middle_band']:.2f}"
            dashboard['bbUpper'] = f"{indicators['bollinger_bands']['upper_band']:.2f}"
            dashboard['bbLower'] = f"{indicators['bollinger_bands']['lower_band']:.2f}"
            if current_position:
                dashboard['currentPosition'] = f"{current_position['side']} {current_position['size']}"
                pnl = (current_price - float(current_position['avgPrice'])) * float(current_position['size']) if current_position['side'] == 'Buy' else (float(current_position['avgPrice']) - current_price) * float(current_position['size'])
                dashboard['positionPnL'] = f"{pnl:.2f} USDT"
            else:
                dashboard['currentPosition'] = "None"
                dashboard['positionPnL'] = "---"

            # 5. Trailing Stop Loss Logic
            if BOT_STATE["current_position_info"]["order_id"] and current_position:
                pos_info = BOT_STATE["current_position_info"]
                
                # Update peak price
                if pos_info["side"] == "Buy":
                    pos_info["peak_price"] = max(pos_info.get("peak_price", current_price), current_price)
                else: # Sell
                    pos_info["peak_price"] = min(pos_info.get("peak_price", current_price), current_price)

                # Calculate new trailing stop price
                trailing_stop_pct = config['trailingStopPct'] / 100
                new_trailing_stop_price = 0
                if pos_info["side"] == "Buy":
                    new_trailing_stop_price = pos_info["peak_price"] * (1 - trailing_stop_pct)
                else: # Sell
                    new_trailing_stop_price = pos_info["peak_price"] * (1 + trailing_stop_pct)
                
                # Round the new trailing stop price
                precision_mgr = BOT_STATE["precision_manager"]
                new_trailing_stop_price = float(precision_mgr.round_price(config["symbol"], new_trailing_stop_price))

                # Get current stop loss from the actual position (if available)
                # Ensure current_position.get('stopLoss') is a valid number before comparison
                current_sl_on_exchange = float(current_position.get('stopLoss', 0)) if current_position.get('stopLoss') else 0.0

                # Check if new trailing stop is more favorable and in profit
                amend_sl = False
                if pos_info["side"] == "Buy" and new_trailing_stop_price > current_sl_on_exchange and new_trailing_stop_price > pos_info["entry_price"]:
                    amend_sl = True
                elif pos_info["side"] == "Sell" and new_trailing_stop_price < current_sl_on_exchange and new_trailing_stop_price < pos_info["entry_price"]:
                    amend_sl = True
                
                if amend_sl:
                    log_message(f"Amending trailing stop for {pos_info['side']} position from {current_sl_on_exchange:.{config['price_precision']}f} to {new_trailing_stop_price:.{config['price_precision']}f}", "info")
                    amend_res = _make_api_call(session, 'post', 'amend_order', params={
                        "category": "linear",
                        "symbol": config["symbol"],
                        "orderId": pos_info["order_id"],
                        "stopLoss": f"{new_trailing_stop_price:.{config['price_precision']}f}"
                    })
                    if amend_res.get('retCode') == 0:
                        log_message("Trailing stop amended successfully.", "success")
                    else:
                        log_message(f"Failed to amend trailing stop: {amend_res.get('retMsg')}", "error")

            # 6. Core Trading Logic
            fisher = indicators['fisher']
            buy_signal = st['direction'] == 1 and BOT_STATE["last_supertrend"]['direction'] == -1 and indicators['rsi'] < config['rsi_overbought'] and fisher > 0 # Ehlers-Fisher confirmation
            sell_signal = st['direction'] == -1 and BOT_STATE["last_supertrend"]['direction'] == 1 and indicators['rsi'] > config['rsi_oversold'] and fisher < 0 # Ehlers-Fisher confirmation

            if buy_signal or sell_signal:
                side = "Buy" if buy_signal else "Sell"
                log_message(f"{side.upper()} SIGNAL DETECTED!", "signal")
                
                # Close existing position if it's opposite
                if current_position and current_position['side'] != side:
                    log_message(f"Closing opposite {current_position['side']} position.", "warning")
                    close_res = _make_api_call(session, 'post', 'place_order', params={
                        "category": "linear",
                        "symbol": config["symbol"],
                        "side": "Sell" if current_position['side'] == "Buy" else "Buy",
                        "orderType": "Market",
                        "qty": current_position['size'],
                        "reduceOnly": True,
                        "tpslMode": "Full" # Ensure existing TP/SL are cancelled
                    })
                    if close_res.get('retCode') == 0:
                        log_message("Opposite position closed successfully.", "success")
                        time.sleep(2) # Give time for position to close
                        BOT_STATE["current_position_info"] = {"order_id": None, "entry_price": None, "side": None, "peak_price": None} # Reset position info
                        balance_res = _make_api_call(session, 'get', 'get_wallet_balance', params={"accountType": "UNIFIED", "coin": "USDT"}) # Refresh balance
                        if balance_res.get('retCode') == 0 and balance_res['result']['list']:
                            balance = float(balance_res['result']['list'][0]['totalWalletBalance'])
                        else:
                            log_message(f"Failed to refresh balance after closing position: {balance_res.get('retMsg')}", "error")
                    else:
                        log_message(f"Failed to close opposite position: {close_res.get('retMsg')}", "error")
                        # If closing fails, do not proceed with new order to avoid conflicting positions
                        continue

                # Place new order
                precision_mgr = BOT_STATE["precision_manager"]
                sl_price = current_price * (1 - config['stopLossPct'] / 100) if side == 'Buy' else current_price * (1 + config['stopLossPct'] / 100)
                tp_price = current_price * (1 + config['takeProfitPct'] / 100) if side == 'Buy' else current_price * (1 - config['takeProfitPct'] / 100)
                
                sl_price = float(precision_mgr.round_price(config["symbol"], sl_price))
                tp_price = float(precision_mgr.round_price(config["symbol"], tp_price))
                
                stop_distance = abs(current_price - sl_price)
                if stop_distance > 0:
                    # --- Position Sizing ---
                    # Calculate the position size in USDT based on risk percentage and stop loss percentage.
                    position_value_usdt = (balance * (config['riskPct'] / 100)) / (config['stopLossPct'] / 100)

                    MIN_ORDER_VALUE = 5 # Default minimum order value in USDT
                    if position_value_usdt < MIN_ORDER_VALUE:
                        log_message(f"Calculated position value {position_value_usdt:.2f} USDT is less than minimum {MIN_ORDER_VALUE} USDT. Order not placed.", "warning")
                        continue

                    # Convert USDT value to base currency quantity (e.g., BTC for BTCUSDT)
                    if current_price <= 0:
                        log_message(f"Invalid current_price ({current_price}) for quantity calculation.", "error")
                        continue
                        
                    qty_in_base_currency = position_value_usdt / current_price
                    qty_in_base_currency = float(precision_mgr.round_quantity(config["symbol"], qty_in_base_currency))
                    
                    log_message(f"Calculated position: {position_value_usdt:.2f} USDT -> {qty_in_base_currency:.{config['qty_precision']}f} {config['symbol']}", "info")
                    log_message(f"Placing {side} order for {qty_in_base_currency:.{config['qty_precision']}f} {config['symbol']}", "info")
                    
                    order_res = _make_api_call(session, 'post', 'place_order', params={
                        "category": "linear",
                        "symbol": config["symbol"],
                        "side": side,
                        "orderType": "Market",
                        "qty": f"{qty_in_base_currency:.{config['qty_precision']}f}",
                        "takeProfit": f"{tp_price:.{config['price_precision']}f}",
                        "stopLoss": f"{sl_price:.{config['price_precision']}f}",
                        "tpslMode": "Full"
                    })
                    if order_res.get('retCode') == 0:
                        log_message("Order placed successfully.", "success")
                        # Store position info for trailing stop
                        BOT_STATE["current_position_info"] = {
                            "order_id": order_res['result']['orderId'],
                            "entry_price": current_price,
                            "side": side,
                            "peak_price": current_price # Initialize peak price
                        }
                    else:
                        log_message(f"Order failed: {order_res.get('retMsg')}", "error")

            BOT_STATE["last_supertrend"] = indicators['supertrend']
            dashboard["botStatus"] = "Idle"

        except Exception as e: # Catch any remaining unexpected errors
            log_message(f"An unexpected error occurred in the trading loop: {e}", "error")
            dashboard["botStatus"] = "Error"
        
        # --- Interval Sleep Logic ---
        # Calculate sleep time to align with the start of the next candle.
        now = time.time()
        
        # Get the timestamp of the most recent kline
        # Ensure klines is not empty before accessing its last element
        if klines:
            last_kline_ts_ms = klines[-1]['timestamp']
        else:
            log_message("Kline data is empty, cannot determine next candle time. Sleeping for default interval.", "warning")
            time.sleep(config.get('api_error_retry_delay', 60))
            continue # Skip to next iteration

        # Determine interval in seconds
        interval_str = str(BOT_STATE["config"].get("interval", "60"))
        if interval_str.isdigit():
            interval_seconds = int(interval_str) * 60
        elif interval_str == 'D':
            interval_seconds = 86400
        else:
            log_message(f"Invalid interval format: {interval_str}. Defaulting to 60s.", "warning")
            interval_seconds = 60 # Default to 1 minute if format is unexpected

        # Calculate the timestamp of the next kline
        next_kline_ts_sec = (last_kline_ts_ms / 1000) + interval_seconds
        
        # Calculate how long to sleep
        sleep_duration = next_kline_ts_sec - now
        
        if sleep_duration > 0:
            log_message(f"Waiting for {sleep_duration:.2f} seconds until next candle.", "info")
            time.sleep(sleep_duration)
        else:
            # If we are already past the next candle's start time, log it and continue.
            log_message(f"Processing took longer than interval ({abs(sleep_duration):.2f}s over). Continuing immediately.", "warning")
            time.sleep(1) # Brief pause to prevent high-CPU loop on errors

    log_message("Trading bot thread stopped.", "warning")


# --- Flask API Endpoints ---
@app.route('/api/start', methods=['POST'])
def start_bot():
    if BOT_STATE["running"]:
        return jsonify({"status": "error", "message": "Bot is already running."}), 400

    config = request.json

    # API keys are loaded from .env file on the backend for security
    # Directly use global BYBIT_API_KEY and BYBIT_API_SECRET
    if not BYBIT_API_KEY or not BYBIT_API_SECRET:
        return jsonify({"status": "error", "message": "Bybit API Key or Secret not found in backend .env file."}), 400

    BOT_STATE["config"] = config
    # Set default values for new config parameters if not provided by frontend
    BOT_STATE["config"]['ef_period'] = config.get('ef_period', 10)
    BOT_STATE["config"]['trailingStopPct'] = config.get('trailingStopPct', 0.5)
    BOT_STATE["config"]['macd_fast_period'] = config.get('macd_fast_period', 12)
    BOT_STATE["config"]['macd_slow_period'] = config.get('macd_slow_period', 26)
    BOT_STATE["config"]['macd_signal_period'] = config.get('macd_signal_period', 9)
    BOT_STATE["config"]['bb_period'] = config.get('bb_period', 20)
    BOT_STATE["config"]['bb_std_dev'] = config.get('bb_std_dev', 2.0)
    BOT_STATE["config"]['api_error_retry_delay'] = config.get('api_error_retry_delay', 60) # New configurable delay
    BOT_STATE["config"]['indicator_wait_delay'] = config.get('indicator_wait_delay', 60) # New configurable delay

    BOT_STATE["bybit_session"] = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET) # LIVE TRADING
    BOT_STATE["precision_manager"] = PrecisionManager(BOT_STATE["bybit_session"], logging)

    # Verify API connection
    balance_check = _make_api_call(BOT_STATE["bybit_session"], 'get', 'get_wallet_balance', params={"accountType": "UNIFIED", "coin": "USDT"})
    if balance_check.get("retCode") != 0:
        log_message(f"API connection failed: {balance_check.get('retMsg')}", "error")
        return jsonify({"status": "error", "message": f"API connection failed: {balance_check.get('retMsg')}"}), 400
    
    log_message("API connection successful.", "success")

    # Fetch instrument info for precision using PrecisionManager
    precision_mgr = BOT_STATE["precision_manager"]
    price_precision, qty_precision = precision_mgr.get_decimal_places(config['symbol'])

    BOT_STATE["config"]["price_precision"] = price_precision
    BOT_STATE["config"]["qty_precision"] = qty_precision
    log_message(f"Fetched instrument info: Price Precision={price_precision}, Quantity Precision={qty_precision}", "info")

    # Set leverage
    leverage = config.get('leverage', 10)
    lev_res = _make_api_call(BOT_STATE["bybit_session"], 'post', 'set_leverage', params={
        "category": "linear",
        "symbol": config['symbol'],
        "buyLeverage": str(leverage),
        "sellLeverage": str(leverage)
    })
    if lev_res.get('retCode') == 0:
        log_message(f"Leverage set to {leverage}x for {config['symbol']}", "success")
    else:
        log_message(f"Failed to set leverage: {lev_res.get('retMsg')}", "warning")


    BOT_STATE["running"] = True
    BOT_STATE["thread"] = threading.Thread(target=trading_bot_loop, daemon=True)
    BOT_STATE["thread"].start()

    return jsonify({"status": "success", "message": "Bot started successfully."})

@app.route('/api/stop', methods=['POST'])
def stop_bot():
    if not BOT_STATE["running"]:
        return jsonify({"status": "error", "message": "Bot is not running."}), 400

    BOT_STATE["running"] = False
    if BOT_STATE["thread"] and BOT_STATE["thread"].is_alive():
        BOT_STATE["thread"].join(timeout=5) # Wait for thread to finish

    BOT_STATE["thread"] = None
    BOT_STATE["bybit_session"] = None
    BOT_STATE["dashboard"]["botStatus"] = "Idle"
    BOT_STATE["current_position_info"] = {"order_id": None, "entry_price": None, "side": None, "peak_price": None} # Reset position info on stop
    log_message("Bot has been stopped by user.", "warning")
    
    return jsonify({"status": "success", "message": "Bot stopped."})

@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify({
        "running": BOT_STATE["running"],
        "dashboard": BOT_STATE["dashboard"],
        "logs": list(BOT_STATE["logs"])
    })

@app.route('/api/gemini-insight', methods=['POST'])
def get_gemini_insight():
    if not GEMINI_API_KEY:
        return jsonify({"status": "error", "message": "Gemini API key not configured on server."}), 503
    
    data = request.json
    prompt = data.get('prompt')
    if not prompt:
        return jsonify({"status": "error", "message": "Prompt is required."}), 400

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        return jsonify({"status": "success", "insight": response.text})
    except Exception as e:
        log_message(f"Gemini API error: {e}", "error")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/symbols', methods=['GET'])
def get_symbols():
    try:
        precision_mgr = BOT_STATE.get("precision_manager")
        if not precision_mgr:
            return jsonify({"status": "error", "message": "Precision manager not initialized."}), 500
        
        linear_symbols = sorted([
            s for s, specs in precision_mgr.instruments.items() 
            if specs.category == 'linear' and specs.status == 'trading'
        ])
        return jsonify({"status": "success", "symbols": linear_symbols})
    except Exception as e:
        log_message(f"Error fetching symbols: {e}", "error")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)