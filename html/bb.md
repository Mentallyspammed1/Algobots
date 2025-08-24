```python
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
from dataclasses import dataclass, field
from typing import Dict, Union, Tuple, Optional, Any

import google.generativeai as genai

# =====================================================================
# CONFIGURATION & UTILITIES
# =====================================================================

# --- Environment Variables ---
load_dotenv()
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Flask App Setup ---
app = Flask(__name__)
CORS(app)

# --- Global Bot State ---
@dataclass
class BotState:
    """Centralized state for the trading bot."""
    running: bool = False
    thread: Optional[threading.Thread] = None
    config: Dict[str, Any] = field(default_factory=dict)
    bybit_session: Optional[HTTP] = None
    precision_manager: Optional['PrecisionManager'] = None
    logs: collections.deque = field(default_factory=lambda: collections.deque(maxlen=200))
    trade_history: Dict[str, Union[int, list]] = field(default_factory=lambda: {"wins": 0, "losses": 0, "history": []})
    dashboard: Dict[str, Any] = field(default_factory=lambda: {
        "currentPrice": "---",
        "priceChange": "---",
        "stDirection": "---",
        "stValue": "---",
        "rsiValue": "---",
        "rsiStatus": "---",
        "fisherValue": "---",
        "macdLine": "---",
        "macdSignal": "---",
        "macdHistogram": "---",
        "bbMiddle": "---",
        "bbUpper": "---",
        "bbLower": "---",
        "currentPosition": "None",
        "positionPnL": "---",
        "accountBalance": "---",
        "totalTrades": 0,
        "winRate": "0%",
        "botStatus": "Idle",
    })
    last_supertrend: Dict[str, Union[int, float]] = field(default_factory=lambda: {"direction": 0, "value": 0})
    current_position_info: Dict[str, Optional[Union[str, float, int]]] = field(default_factory=lambda: {"order_id": None, "entry_price": None, "side": None, "peak_price": None})

BOT_STATE = BotState()

# --- Logging Utility ---
def log_message(message: str, level: str = 'info'):
    """Adds a message to the in-memory log and logs to the console."""
    timestamp = time.strftime("%H:%M:%S")
    BOT_STATE.logs.append({"timestamp": timestamp, "level": level, "message": message})
    
    if level == 'error':
        logger.error(message)
    elif level == 'warning':
        logger.warning(message)
    elif level == 'success':
        logger.info(f"SUCCESS: {message}") # Use INFO for success to distinguish
    else:
        logger.info(message)

# --- Instrument Specifications & Precision Management ---
@dataclass
class InstrumentSpecs:
    """Store instrument specifications from Bybit"""
    symbol: str
    category: str
    base_currency: str
    quote_currency: str
    status: str
    
    min_price: Decimal
    max_price: Decimal
    tick_size: Decimal  # Price precision
    
    min_order_qty: Decimal
    max_order_qty: Decimal
    qty_step: Decimal  # Quantity precision
    
    min_leverage: Decimal
    max_leverage: Decimal
    leverage_step: Decimal
    
    max_position_value: Decimal
    min_position_value: Decimal
    
    contract_value: Decimal = Decimal('1')
    is_inverse: bool = False
    
    maker_fee: Decimal = Decimal('0.0001')
    taker_fee: Decimal = Decimal('0.0006')

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
                response = self._make_api_call('get', 'get_instruments_info', params={'category': category})
                
                if response and response['retCode'] == 0:
                    for inst in response['result']['list']:
                        symbol = inst['symbol']
                        try:
                            if category in ['linear', 'inverse']:
                                specs = self._parse_derivatives_specs(inst, category)
                            elif category == 'spot':
                                specs = self._parse_spot_specs(inst, category)
                            else:  # option
                                specs = self._parse_option_specs(inst, category)
                            
                            self.instruments[symbol] = specs
                        except Exception as parse_e:
                            self.logger.warning(f"Could not parse specs for {symbol} ({category}): {parse_e}")
                            
            except Exception as e:
                self.logger.error(f"Error loading {category} instruments: {e}")
    
    def _make_api_call(self, method: str, endpoint: str, params: Optional[Dict] = None, max_retries: int = 3, initial_delay: int = 1) -> Optional[Dict]:
        """Internal helper for API calls with retry logic."""
        for attempt in range(max_retries):
            try:
                if method == 'get':
                    response = getattr(self.session, endpoint)(**params) if params else getattr(self.session, endpoint)()
                elif method == 'post':
                    response = getattr(self.session, endpoint)(**params)
                elif method == 'amend': # For amend_order
                    response = getattr(self.session, endpoint)(**params)
                else:
                    self.logger.error(f"Invalid method '{method}' for API call.")
                    return {"retCode": 1, "retMsg": "Invalid method"}

                if response.get('retCode') == 0:
                    return response
                else:
                    ret_code = response.get('retCode')
                    ret_msg = response.get('retMsg', 'Unknown Error')
                    self.logger.warning(f"Bybit API Error ({ret_code}): {ret_msg} for {endpoint}. Retrying in {initial_delay * (2**attempt)}s... (Attempt {attempt + 1})")
                    time.sleep(initial_delay * (2**attempt))
            except Exception as e:
                self.logger.error(f"API call error for {endpoint}: {e}. Retrying in {initial_delay * (2**attempt)}s... (Attempt {attempt + 1})")
                time.sleep(initial_delay * (2**attempt))
        
        self.logger.error(f"Failed to complete API call to {endpoint} after {max_retries} attempts.")
        return None

    def _parse_derivatives_specs(self, inst: Dict, category: str) -> InstrumentSpecs:
        """Parse derivatives instrument specifications"""
        lot_size = inst.get('lotSizeFilter', {})
        price_filter = inst.get('priceFilter', {})
        leverage = inst.get('leverageFilter', {})
        
        return InstrumentSpecs(
            symbol=inst['symbol'],
            category=category,
            base_currency=inst['baseCoin'],
            quote_currency=inst['quoteCoin'],
            status=inst['status'],
            min_price=Decimal(price_filter.get('minPrice', '0')),
            max_price=Decimal(price_filter.get('maxPrice', '100000000')),
            tick_size=Decimal(price_filter.get('tickSize', '0.00000001')),
            min_order_qty=Decimal(lot_size.get('minOrderQty', '0.001')),
            max_order_qty=Decimal(lot_size.get('maxOrderQty', '1000000')),
            qty_step=Decimal(lot_size.get('qtyStep', '0.001')),
            min_leverage=Decimal(leverage.get('minLeverage', '1')),
            max_leverage=Decimal(leverage.get('maxLeverage', '10')),
            leverage_step=Decimal(leverage.get('leverageStep', '0.01')),
            max_position_value=Decimal(lot_size.get('maxMktOrderQty', '1000000')),
            min_position_value=Decimal(lot_size.get('minOrderQty', '1')),
            contract_value=Decimal(inst.get('contractValue', '1')),
            is_inverse=(category == 'inverse')
        )
    
    def _parse_spot_specs(self, inst: Dict, category: str) -> InstrumentSpecs:
        """Parse spot instrument specifications"""
        lot_size = inst.get('lotSizeFilter', {})
        price_filter = inst.get('priceFilter', {})
        
        return InstrumentSpecs(
            symbol=inst['symbol'],
            category=category,
            base_currency=inst['baseCoin'],
            quote_currency=inst['quoteCoin'],
            status=inst['status'],
            min_price=Decimal(price_filter.get('minPrice', '0')),
            max_price=Decimal(price_filter.get('maxPrice', '100000000')),
            tick_size=Decimal(price_filter.get('tickSize', '0.001')),
            min_order_qty=Decimal(lot_size.get('minOrderQty', '0.001')),
            max_order_qty=Decimal(lot_size.get('maxOrderQty', '1000000')),
            qty_step=Decimal(lot_size.get('qtyStep', '0.001')),
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
        lot_size = inst.get('lotSizeFilter', {})
        price_filter = inst.get('priceFilter', {})
        
        return InstrumentSpecs(
            symbol=inst['symbol'],
            category=category,
            base_currency=inst['baseCoin'],
            quote_currency=inst['quoteCoin'],
            status=inst['status'],
            min_price=Decimal(price_filter.get('minPrice', '0')),
            max_price=Decimal(price_filter.get('maxPrice', '100000000')),
            tick_size=Decimal(price_filter.get('tickSize', '0.0001')),
            min_order_qty=Decimal(lot_size.get('minOrderQty', '0.001')),
            max_order_qty=Decimal(lot_size.get('maxOrderQty', '1000000')),
            qty_step=Decimal(lot_size.get('qtyStep', '0.001')),
            min_leverage=Decimal('1'),
            max_leverage=Decimal('1'),
            leverage_step=Decimal('1'),
            max_position_value=Decimal(lot_size.get('maxOrderQty', '1000000')),
            min_position_value=Decimal(lot_size.get('minOrderQty', '1')),
            contract_value=Decimal('1'),
            is_inverse=False
        )
    
    def round_price(self, symbol: str, price: Union[float, Decimal]) -> Decimal:
        """Round price to correct tick size and within bounds."""
        if symbol not in self.instruments:
            self.logger.warning(f"Symbol {symbol} not found, using default price precision (0.01).")
            return Decimal(str(price)).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
        
        specs = self.instruments[symbol]
        price_decimal = Decimal(str(price))
        tick_size = specs.tick_size
        
        # Round down to nearest tick
        rounded = (price_decimal / tick_size).quantize(Decimal('1'), rounding=ROUND_DOWN) * tick_size
        
        # Ensure within min/max bounds
        rounded = max(specs.min_price, min(rounded, specs.max_price))
        
        return rounded
    
    def round_quantity(self, symbol: str, quantity: Union[float, Decimal]) -> Decimal:
        """Round quantity to correct step size and within bounds."""
        if symbol not in self.instruments:
            self.logger.warning(f"Symbol {symbol} not found, using default quantity precision (0.001).")
            return Decimal(str(quantity)).quantize(Decimal('0.001'), rounding=ROUND_DOWN)
        
        specs = self.instruments[symbol]
        qty_decimal = Decimal(str(quantity))
        qty_step = specs.qty_step
        
        # Round down to nearest step
        rounded = (qty_decimal / qty_step).quantize(Decimal('1'), rounding=ROUND_DOWN) * qty_step
        
        # Ensure within min/max bounds
        rounded = max(specs.min_order_qty, min(rounded, specs.max_order_qty))
        
        return rounded
    
    def get_decimal_places(self, symbol: str) -> Tuple[int, int]:
        """Get decimal places for price and quantity."""
        if symbol not in self.instruments:
            self.logger.warning(f"Symbol {symbol} not found for decimal places, returning defaults (2, 3).")
            return 2, 3
        
        specs = self.instruments[symbol]
        
        price_decimals = abs(specs.tick_size.as_tuple().exponent) if specs.tick_size != 0 else 2
        qty_decimals = abs(specs.qty_step.as_tuple().exponent) if specs.qty_step != 0 else 3
        
        return price_decimals, qty_decimals

# --- Indicator Calculation (Assuming 'indicators.py' exists and has this function) ---
try:
    from indicators import calculate_indicators
except ImportError:
    logger.error("Could not import 'calculate_indicators' from 'indicators.py'. Please ensure the file exists and contains the function.")
    # Provide a dummy function if import fails to allow the rest of the code to load
    def calculate_indicators(klines, config):
        logger.warning("Using dummy calculate_indicators function due to import error.")
        # Simulate basic indicator structure
        return {
            'supertrend': {'direction': 1, 'supertrend': klines[-1]['close'] * 0.99} if klines else {'direction': 0, 'supertrend': 0},
            'rsi': 50,
            'fisher': 0,
            'macd': {'macd_line': 0, 'signal_line': 0, 'histogram': 0},
            'bollinger_bands': {'middle_band': klines[-1]['close'] if klines else 0, 'upper_band': 0, 'lower_band': 0}
        }


# =====================================================================
# TRADING BOT LOGIC
# =====================================================================
def trading_bot_loop():
    """The main loop for the trading bot, running in a separate thread."""
    log_message("Trading bot thread started.", "success")
    
    while BOT_STATE.running:
        try:
            config = BOT_STATE.config
            session = BOT_STATE.bybit_session
            precision_mgr = BOT_STATE.precision_manager
            dashboard = BOT_STATE.dashboard

            if not session or not precision_mgr:
                log_message("Session or Precision Manager not initialized. Stopping bot thread.", "error")
                BOT_STATE.running = False
                break

            dashboard["botStatus"] = "Scanning"
            
            # 1. Fetch Kline Data
            # Ensure we fetch enough klines for indicators (e.g., 200 for Supertrend, MACD etc.)
            klines_res = _make_api_call(session, 'get', 'get_kline', params={
                "category": "linear", 
                "symbol": config["symbol"], 
                "interval": config["interval"], 
                "limit": 200 # Fetch more data for robust indicator calculation
            })
            if not klines_res or klines_res.get('retCode') != 0:
                log_message(f"Failed to fetch klines: {klines_res.get('retMsg', 'Unknown API error')}", "error")
                dashboard["botStatus"] = "API Error"
                time.sleep(config.get('api_error_retry_delay', 60))
                continue

            klines = sorted([{
                "timestamp": int(k[0]), "open": float(k[1]), "high": float(k[2]), 
                "low": float(k[3]), "close": float(k[4]), "volume": float(k[5])
            } for k in klines_res['result']['list']], key=lambda x: x['timestamp'])

            if not klines:
                log_message("No kline data received. Waiting for data.", "warning")
                dashboard["botStatus"] = "Waiting for Data"
                time.sleep(config.get('indicator_wait_delay', 60))
                continue

            current_price = klines[-1]['close']
            
            # 2. Calculate Indicators
            indicators = calculate_indicators(klines, config)
            if not indicators:
                log_message("Indicator calculation failed or returned no data. Waiting.", "warning")
                dashboard["botStatus"] = "Indicator Error"
                time.sleep(config.get('indicator_wait_delay', 60))
                continue

            # 3. Fetch Position and Balance
            position_res = _make_api_call(session, 'get', 'get_positions', params={"category": "linear", "symbol": config["symbol"]})
            balance_res = _make_api_call(session, 'get', 'get_wallet_balance', params={"accountType": "UNIFIED", "coin": "USDT"})

            current_position = None
            open_position_size = 0
            if position_res and position_res.get('retCode') == 0:
                # Filter for open positions with size > 0
                pos_list = [p for p in position_res['result']['list'] if float(p.get('size', 0)) > 0]
                if pos_list:
                    current_position = pos_list[0]
                    open_position_size = float(current_position.get('size', 0))
            else:
                log_message(f"Failed to fetch positions: {position_res.get('retMsg', 'Unknown API error')}", "error")
            
            account_balance = 0.0
            if balance_res and balance_res.get('retCode') == 0 and balance_res['result']['list']:
                # Find the USDT balance entry
                usdt_balance_entry = next((item for item in balance_res['result']['list'] if item["coin"] == "USDT"), None)
                if usdt_balance_entry:
                    account_balance = float(usdt_balance_entry.get('totalWalletBalance', 0))
            else:
                log_message(f"Failed to fetch balance: {balance_res.get('retMsg', 'Unknown API error')}", "error")

            # 4. Update Dashboard
            dashboard['currentPrice'] = f"${current_price:.{config['price_precision']}f}"
            st = indicators['supertrend']
            dashboard['stDirection'] = "UP" if st['direction'] == 1 else "DOWN" if st['direction'] == -1 else "SIDEWAYS"
            dashboard['stValue'] = f"{st['supertrend']:.{config['price_precision']}f}" if st['supertrend'] else "---"
            dashboard['rsiValue'] = f"{indicators['rsi']:.2f}" if 'rsi' in indicators else "---"
            dashboard['accountBalance'] = f"${account_balance:.2f}"
            dashboard['fisherValue'] = f"{indicators['fisher']:.2f}" if 'fisher' in indicators else "---"
            dashboard['macdLine'] = f"{indicators['macd']['macd_line']:.2f}" if 'macd' in indicators and 'macd_line' in indicators['macd'] else "---"
            dashboard['macdSignal'] = f"{indicators['macd']['signal_line']:.2f}" if 'macd' in indicators and 'signal_line' in indicators['macd'] else "---"
            dashboard['macdHistogram'] = f"{indicators['macd']['histogram']:.2f}" if 'macd' in indicators and 'histogram' in indicators['macd'] else "---"
            dashboard['bbMiddle'] = f"{indicators['bollinger_bands']['middle_band']:.{config['price_precision']}f}" if 'bollinger_bands' in indicators and 'middle_band' in indicators['bollinger_bands'] else "---"
            dashboard['bbUpper'] = f"{indicators['bollinger_bands']['upper_band']:.{config['price_precision']}f}" if 'bollinger_bands' in indicators and 'upper_band' in indicators['bollinger_bands'] else "---"
            dashboard['bbLower'] = f"{indicators['bollinger_bands']['lower_band']:.{config['price_precision']}f}" if 'bollinger_bands' in indicators and 'lower_band' in indicators['bollinger_bands'] else "---"
            
            if current_position:
                dashboard['currentPosition'] = f"{current_position['side']} {current_position['size']} @ {current_position['avgPrice']}"
                entry_price = float(current_position['avgPrice'])
                pnl = (current_price - entry_price) * open_position_size if current_position['side'] == 'Buy' else (entry_price - current_price) * open_position_size
                dashboard['positionPnL'] = f"{pnl:.2f} USDT"
            else:
                dashboard['currentPosition'] = "None"
                dashboard['positionPnL'] = "---"

            # 5. Trailing Stop Loss Logic
            if BOT_STATE.current_position_info["order_id"] and current_position:
                pos_info = BOT_STATE.current_position_info
                
                # Update peak price
                if pos_info["side"] == "Buy":
                    pos_info["peak_price"] = max(pos_info.get("peak_price", current_price), current_price)
                else: # Sell
                    pos_info["peak_price"] = min(pos_info.get("peak_price", current_price), current_price)

                # Calculate new trailing stop price
                trailing_stop_pct = config.get('trailingStopPct', 0.5) / 100
                new_trailing_stop_price = 0.0
                if pos_info["side"] == "Buy":
                    new_trailing_stop_price = pos_info["peak_price"] * (1 - trailing_stop_pct)
                else: # Sell
                    new_trailing_stop_price = pos_info["peak_price"] * (1 + trailing_stop_pct)
                
                # Round the new trailing stop price
                new_trailing_stop_price = float(precision_mgr.round_price(config["symbol"], new_trailing_stop_price))

                # Get current stop loss from the actual position
                current_sl_on_exchange = float(current_position.get('stopLoss', 0)) if current_position.get('stopLoss') else 0.0

                # Check if new trailing stop is more favorable and valid
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
                    if amend_res and amend_res.get('retCode') == 0:
                        log_message("Trailing stop amended successfully.", "success")
                    else:
                        log_message(f"Failed to amend trailing stop: {amend_res.get('retMsg', 'Unknown API error')}", "error")

            # 6. Core Trading Logic
            fisher = indicators.get('fisher', 0)
            rsi = indicators.get('rsi', 50)
            st = indicators.get('supertrend', {})
            
            # Buy signal: Supertrend uptrend starts, RSI not overbought, Fisher positive
            buy_signal = (st.get('direction') == 1 and 
                          BOT_STATE.last_supertrend.get('direction', 0) == -1 and 
                          rsi < config.get('rsi_overbought', 70) and 
                          fisher > config.get('fisher_threshold', 0))
            
            # Sell signal: Supertrend downtrend starts, RSI not oversold, Fisher negative
            sell_signal = (st.get('direction') == -1 and 
                           BOT_STATE.last_supertrend.get('direction', 0) == 1 and 
                           rsi > config.get('rsi_oversold', 30) and 
                           fisher < -config.get('fisher_threshold', 0))

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
                    if close_res and close_res.get('retCode') == 0:
                        log_message("Opposite position closed successfully.", "success")
                        time.sleep(2) # Give time for position to close
                        BOT_STATE.current_position_info = {"order_id": None, "entry_price": None, "side": None, "peak_price": None} # Reset position info
                        # Refresh balance after closing position
                        balance_res = _make_api_call(session, 'get', 'get_wallet_balance', params={"accountType": "UNIFIED", "coin": "USDT"})
                        if balance_res and balance_res.get('retCode') == 0 and balance_res['result']['list']:
                            usdt_balance_entry = next((item for item in balance_res['result']['list'] if item["coin"] == "USDT"), None)
                            if usdt_balance_entry:
                                account_balance = float(usdt_balance_entry.get('totalWalletBalance', 0))
                    else:
                        log_message(f"Failed to close opposite position: {close_res.get('retMsg', 'Unknown API error')}", "error")
                        continue # Skip placing new order if closing failed

                # --- Place New Order ---
                sl_pct = config.get('stopLossPct', 1.0) / 100
                tp_pct = config.get('takeProfitPct', 2.0) / 100
                
                sl_price = current_price * (1 - sl_pct) if side == 'Buy' else current_price * (1 + sl_pct)
                tp_price = current_price * (1 + tp_pct) if side == 'Buy' else current_price * (1 - tp_pct)
                
                sl_price = float(precision_mgr.round_price(config["symbol"], sl_price))
                tp_price = float(precision_mgr.round_price(config["symbol"], tp_price))
                
                stop_distance = abs(current_price - sl_price)
                if stop_distance <= 0:
                    log_message("Stop loss distance is zero or negative. Cannot place order.", "error")
                    continue

                # --- Position Sizing ---
                risk_pct = config.get('riskPct', 1.0) / 100
                position_value_usdt = (account_balance * risk_pct) / (abs(current_price - sl_price) / current_price)

                MIN_ORDER_VALUE_USDT = 10 # Minimum order value in USDT
                if position_value_usdt < MIN_ORDER_VALUE_USDT:
                    log_message(f"Calculated position value {position_value_usdt:.2f} USDT is less than minimum {MIN_ORDER_VALUE_USDT} USDT. Order not placed.", "warning")
                    continue

                # Convert USDT value to base currency quantity
                if current_price <= 0:
                    log_message(f"Invalid current_price ({current_price}) for quantity calculation.", "error")
                    continue
                    
                qty_in_base_currency = position_value_usdt / current_price
                rounded_qty = precision_mgr.round_quantity(config["symbol"], qty_in_base_currency)
                
                log_message(f"Calculated position: {position_value_usdt:.2f} USDT -> {rounded_qty:.{config['qty_precision']}f} {config['symbol']}", "info")
                
                order_res = _make_api_call(session, 'post', 'place_order', params={
                    "category": "linear",
                    "symbol": config["symbol"],
                    "side": side,
                    "orderType": "Market",
                    "qty": f"{rounded_qty:.{config['qty_precision']}f}",
                    "takeProfit": f"{tp_price:.{config['price_precision']}f}",
                    "stopLoss": f"{sl_price:.{config['price_precision']}f}",
                    "tpslMode": "Full"
                })
                
                if order_res and order_res.get('retCode') == 0:
                    log_message("Order placed successfully.", "success")
                    # Store position info for trailing stop
                    BOT_STATE.current_position_info = {
                        "order_id": order_res['result']['orderId'],
                        "entry_price": current_price, # Use current price as initial entry for calculation
                        "side": side,
                        "peak_price": current_price # Initialize peak price
                    }
                    dashboard["totalTrades"] += 1
                else:
                    log_message(f"Order failed: {order_res.get('retMsg', 'Unknown API error')}", "error")

            # Update last Supertrend state after processing signals
            if st:
                BOT_STATE.last_supertrend = st

            dashboard["botStatus"] = "Idle"

        except Exception as e: 
            log_message(f"An unexpected error occurred in the trading loop: {e}", "error")
            dashboard["botStatus"] = "Error"
            # Consider adding a longer sleep here if errors are persistent
            time.sleep(30) 
        
        # --- Interval Sleep Logic ---
        # Calculate sleep time to align with the start of the next candle.
        now = time.time()
        
        last_kline_ts_sec = klines[-1]['timestamp'] / 1000 if klines else now # Use current time if no klines
        
        interval_str = BOT_STATE.config.get("interval", "60")
        interval_seconds = 60 # Default to 1 minute
        if interval_str.isdigit():
            interval_seconds = int(interval_str) * 60
        elif interval_str == 'D':
            interval_seconds = 86400
        # Add more interval mappings if needed (e.g., '15', '30', '12h', '1w')
        elif interval_str == '15': interval_seconds = 15 * 60
        elif interval_str == '30': interval_seconds = 30 * 60
        elif interval_str == '12h': interval_seconds = 12 * 3600
        elif interval_str == '1h': interval_seconds = 3600
        else:
            log_message(f"Unsupported interval format: '{interval_str}'. Defaulting to 60s.", "warning")
            interval_seconds = 60

        # Calculate the timestamp of the next kline's start
        next_kline_start_ts = (last_kline_ts_sec // interval_seconds + 1) * interval_seconds
        
        sleep_duration = next_kline_start_ts - now
        
        if sleep_duration > 0:
            log_message(f"Waiting for {sleep_duration:.2f} seconds until next candle.", "info")
            time.sleep(sleep_duration)
        else:
            # If we are already past the next candle's start time, log it and continue.
            log_message(f"Processing took longer than interval ({abs(sleep_duration):.2f}s over). Continuing immediately.", "warning")
            time.sleep(1) # Brief pause to prevent high-CPU loop on errors

    log_message("Trading bot thread stopped.", "warning")


# --- Helper for API Calls (used by endpoints) ---
def _make_api_call(api_client: HTTP, method: str, endpoint: str, params: Optional[Dict] = None, max_retries: int = 3, initial_delay: int = 1) -> Optional[Dict]:
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
                ret_msg = response.get('retMsg', 'Unknown Error')
                log_message(f"Bybit API Error ({ret_code}): {ret_msg}. Retrying {endpoint} in {initial_delay * (2**attempt)}s... (Attempt {attempt + 1})", "warning")
                time.sleep(initial_delay * (2**attempt)) # Exponential backoff
        except Exception as e: # Catch any Pybit-related exceptions or other unexpected errors
            log_message(f"API call error for {endpoint}: {e}. Retrying in {initial_delay * (2**attempt)}s... (Attempt {attempt + 1})", "error")
            time.sleep(initial_delay * (2**attempt)) # Exponential backoff
    
    log_message(f"Failed to complete API call to {endpoint} after {max_retries} attempts.", "error")
    return {"retCode": 1, "retMsg": f"Failed after {max_retries} attempts: {endpoint}"}


# =====================================================================
# FLASK API ENDPOINTS
# =====================================================================
@app.route('/api/start', methods=['POST'])
def start_bot():
    """Starts the trading bot."""
    if BOT_STATE.running:
        return jsonify({"status": "error", "message": "Bot is already running."}), 400

    config = request.json
    
    # Validate essential config parameters
    required_params = ['symbol', 'interval', 'leverage', 'riskPct', 'stopLossPct', 'takeProfitPct', 'rsi_overbought', 'rsi_oversold', 'trailingStopPct', 'api_error_retry_delay', 'indicator_wait_delay']
    if not all(param in config for param in required_params):
        missing = [param for param in required_params if param not in config]
        return jsonify({"status": "error", "message": f"Missing required configuration parameters: {', '.join(missing)}"}), 400

    # API keys are loaded from .env file on the backend for security
    if not BYBIT_API_KEY or not BYBIT_API_SECRET:
        log_message("CRITICAL: Bybit API Key or Secret not found in backend .env file.", "error")
        return jsonify({"status": "error", "message": "Bybit API Key or Secret not found in backend .env file."}), 500

    BOT_STATE.config = config
    # Set default values for indicator parameters if not provided
    BOT_STATE.config['ef_period'] = config.get('ef_period', 10)
    BOT_STATE.config['fisher_threshold'] = config.get('fisher_threshold', 0.5) # Add Fisher threshold
    BOT_STATE.config['macd_fast_period'] = config.get('macd_fast_period', 12)
    BOT_STATE.config['macd_slow_period'] = config.get('macd_slow_period', 26)
    BOT_STATE.config['macd_signal_period'] = config.get('macd_signal_period', 9)
    BOT_STATE.config['bb_period'] = config.get('bb_period', 20)
    BOT_STATE.config['bb_std_dev'] = config.get('bb_std_dev', 2.0)
    
    try:
        BOT_STATE.bybit_session = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET) # LIVE TRADING
        BOT_STATE.precision_manager = PrecisionManager(BOT_STATE.bybit_session, logger)

        # Verify API connection by fetching balance
        balance_check = _make_api_call(BOT_STATE.bybit_session, 'get', 'get_wallet_balance', params={"accountType": "UNIFIED", "coin": "USDT"})
        if not balance_check or balance_check.get("retCode") != 0:
            log_message(f"API connection failed: {balance_check.get('retMsg', 'Unknown API error')}", "error")
            BOT_STATE.bybit_session = None # Clear session if connection fails
            return jsonify({"status": "error", "message": f"API connection failed: {balance_check.get('retMsg', 'Unknown API error')}"}), 400
        
        log_message("API connection successful.", "success")

        # Fetch instrument info for precision using PrecisionManager
        precision_mgr = BOT_STATE.precision_manager
        price_precision, qty_precision = precision_mgr.get_decimal_places(config['symbol'])

        BOT_STATE.config["price_precision"] = price_precision
        BOT_STATE.config["qty_precision"] = qty_precision
        log_message(f"Fetched instrument info: Price Precision={price_precision}, Quantity Precision={qty_precision}", "info")

        # Set leverage
        leverage = config.get('leverage', 10)
        
        # Check current leverage before setting to avoid unnecessary API calls
        position_info_res = _make_api_call(BOT_STATE.bybit_session, 'get', 'get_positions', params={"category": "linear", "symbol": config['symbol']})
        
        should_set_leverage = True
        if position_info_res and position_info_res.get('retCode') == 0 and position_info_res['result']['list']:
            # Find the position for the specific symbol
            symbol_pos = next((p for p in position_info_res['result']['list'] if p.get('symbol') == config['symbol']), None)
            if symbol_pos:
                current_leverage = float(symbol_pos.get('leverage', 0))
                if current_leverage == leverage:
                    log_message(f"Leverage is already set to {leverage}x for {config['symbol']}. Skipping.", "info")
                    should_set_leverage = False
        elif position_info_res and position_info_res.get('retCode') != 0:
             log_message(f"Could not fetch positions to check leverage: {position_info_res.get('retMsg', 'Unknown API error')}", "warning")


        if should_set_leverage:
            # Ensure leverage is within bounds defined by Bybit specs
            symbol_specs = precision_mgr.instruments.get(config['symbol'])
            if symbol_specs:
                min_lev = int(symbol_specs.min_leverage)
                max_lev = int(symbol_specs.max_leverage)
                leverage = max(min_lev, min(leverage, max_lev)) # Clamp leverage
                log_message(f"Adjusted leverage to {leverage}x based on instrument specs.", "info")
            
            lev_res = _make_api_call(BOT_STATE.bybit_session, 'post', 'set_leverage', params={
                "category": "linear",
                "symbol": config['symbol'],
                "buyLeverage": str(leverage),
                "sellLeverage": str(leverage)
            })
            if lev_res and lev_res.get('retCode') == 0:
                log_message(f"Leverage set to {leverage}x for {config['symbol']}", "success")
            else:
                log_message(f"Failed to set leverage: {lev_res.get('retMsg', 'Unknown API error')}", "warning")

        BOT_STATE.running = True
        BOT_STATE.thread = threading.Thread(target=trading_bot_loop, daemon=True)
        BOT_STATE.thread.start()

        return jsonify({"status": "success", "message": "Bot started successfully."})

    except Exception as e:
        log_message(f"Error starting bot: {e}", "error")
        # Clean up potentially created resources
        BOT_STATE.bybit_session = None
        BOT_STATE.precision_manager = None
        return jsonify({"status": "error", "message": f"Failed to start bot: {str(e)}"}), 500


@app.route('/api/stop', methods=['POST'])
def stop_bot():
    """Stops the trading bot."""
    if not BOT_STATE.running:
        return jsonify({"status": "error", "message": "Bot is not running."}), 400

    BOT_STATE.running = False
    if BOT_STATE.thread and BOT_STATE.thread.is_alive():
        BOT_STATE.thread.join(timeout=5) # Wait for thread to finish gracefully

    BOT_STATE.thread = None
    BOT_STATE.bybit_session = None # Close the session
    BOT_STATE.precision_manager = None
    BOT_STATE.dashboard["botStatus"] = "Idle"
    BOT_STATE.current_position_info = {"order_id": None, "entry_price": None, "side": None, "peak_price": None} # Reset position info on stop
    log_message("Bot has been stopped by user.", "warning")
    
    return jsonify({"status": "success", "message": "Bot stopped."})

@app.route('/api/status', methods=['GET'])
def get_status():
    """Returns the current status of the bot."""
    return jsonify({
        "running": BOT_STATE.running,
        "dashboard": BOT_STATE.dashboard,
        "config": BOT_STATE.config if BOT_STATE.running else {}, # Only show config if running
        "logs": list(BOT_STATE.logs)
    })

@app.route('/api/gemini-insight', methods=['POST'])
def get_gemini_insight():
    """Fetches insights from Gemini AI."""
    if not GEMINI_API_KEY:
        log_message("Gemini API key not configured on server.", "error")
        return jsonify({"status": "error", "message": "Gemini API key not configured on server."}), 503
    
    data = request.json
    prompt = data.get('prompt')
    if not prompt:
        return jsonify({"status": "error", "message": "Prompt is required."}), 400

    try:
        # Use Gemini 1.5 Flash for faster responses
        model = genai.GenerativeModel('gemini-1.5-flash-latest', system_instruction="You are a helpful trading assistant. Provide concise and actionable insights.")
        response = model.generate_content(prompt)
        
        # Handle potential empty or blocked responses
        if not response.text:
             return jsonify({"status": "error", "message": "Gemini returned an empty response. Please try again or rephrase your prompt."}), 500

        return jsonify({"status": "success", "insight": response.text})
    except Exception as e:
        log_message(f"Gemini API error: {e}", "error")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/symbols', methods=['GET'])
def get_symbols():
    """Fetches available trading symbols from Bybit."""
    try:
        # Initialize PrecisionManager if not already done (e.g., before bot start)
        if not BOT_STATE.precision_manager:
            if not BYBIT_API_KEY or not BYBIT_API_SECRET:
                 return jsonify({"status": "error", "message": "Bybit API Key/Secret not configured. Cannot fetch symbols."}), 500
            session = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)
            BOT_STATE.precision_manager = PrecisionManager(session, logger)
            
        precision_mgr = BOT_STATE.precision_manager
        
        # Filter for linear category and 'trading' status
        linear_symbols = sorted([
            s for s, specs in precision_mgr.instruments.items() 
            if specs.category == 'linear' and specs.status == 'trading'
        ])
        return jsonify({"status": "success", "symbols": linear_symbols})
    except Exception as e:
        log_message(f"Error fetching symbols: {e}", "error")
        return jsonify({"status": "error", "message": str(e)}), 500

# --- Main Execution ---
if __name__ == '__main__':
    # Basic checks on startup
    if not BYBIT_API_KEY or not BYBIT_API_SECRET:
        logger.critical("CRITICAL: Bybit API Key or Secret not found. Please check your .env file.")
    if not GEMINI_API_KEY:
        logger.warning("Gemini API Key not found. The insight feature will be disabled.")
    else:
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            logger.info("Gemini API configured.")
        except Exception as e:
            logger.error(f"Failed to configure Gemini API: {e}")

    # Run the Flask app
    logger.info("Starting Flask server on port 5000...")
    app.run(debug=False, host='0.0.0.0', port=5000)
```
