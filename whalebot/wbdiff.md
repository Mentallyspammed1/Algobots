1,7d0
< """Whalebot: An automated cryptocurrency trading bot for Bybit.
< 
< This bot leverages various technical indicators and multi-timeframe analysis
< to generate trading signals and manage positions on the Bybit exchange.
< It includes features for risk management, performance tracking, and alerts.
< """
< 
15a9,13
> import threading
> import queue
> import websocket
> import ssl
> from collections import deque
29,36d26
< # Add to existing imports
< import threading
< import queue
< import websocket # You might need to install this: pip install websocket-client
< import ssl # For secure WebSocket connections
< from collections import deque # For storing recent kline data efficiently
< 
< # Scikit-learn is explicitly excluded as per user request.
39d28
< # Initialize colorama and set decimal precision
44d32
< # Neon Color Scheme
53d40
< # Indicator specific colors (enhanced for new indicators)
95d81
< # --- Constants ---
103,104d88
< # Add to Constants section, after existing API_SECRET, BASE_URL etc.
< # --- WebSocket Constants ---
108d91
< # WebSocket reconnection settings
112,113c95
< # Default topics (will be overridden by config later)
< DEFAULT_PUBLIC_TOPICS = [] # Will be dynamically generated
---
> DEFAULT_PUBLIC_TOPICS = []
116d97
< # Using UTC for consistency and to avoid timezone issues with API timestamps
123d103
< # Magic Numbers as Constants (expanded)
134d113
< # --- Configuration Management ---
136d114
<     """Load configuration from JSON file, creating a default if not found."""
138d115
<         # Core Settings
140c117
<         "interval": "15",  # Changed "15m" to "15" to match Bybit API requirement
---
>         "interval": "15",
147d123
<         # Position & Risk Management
155,159c131,135
<             "order_precision": 5,  # New: Decimal places for order quantity
<             "price_precision": 3,  # New: Decimal places for price
<             "enable_trailing_stop": True,         # Enable trailing stop
<             "trailing_stop_atr_multiple": 0.8,    # ATR multiple for trailing stop distance
<             "break_even_atr_trigger": 0.5         # Price must move this much in profit (in ATR multiples) to activate trailing stop
---
>             "order_precision": 5,
>             "price_precision": 3,
>             "enable_trailing_stop": True,
>             "trailing_stop_atr_multiple": 0.8,
>             "break_even_atr_trigger": 0.5,
161d136
<         # Multi-Timeframe Analysis
164c139
<             "higher_timeframes": ["60", "240"],  # Changed "1h", "4h" to "60", "240"
---
>             "higher_timeframes": ["60", "240"],
169d143
<         # Machine Learning Enhancement (Explicitly disabled)
171c145
<             "enabled": False,  # ML explicitly disabled
---
>             "enabled": False,
180,182c154,155
<         # Strategy Profiles
<         "current_strategy_profile": "default_scalping", # New: Specifies the currently active strategy profile
<         "strategy_profiles": { # New section to define various strategy profiles
---
>         "current_strategy_profile": "default_scalping",
>         "strategy_profiles": {
188c161
<                     "momentum": True, # Now a general category, individual momentum indicators are sub-checked
---
>                     "momentum": True,
209c182
<                     "volume_delta": True
---
>                     "volume_delta": True,
230,231c203,204
<                     "volume_delta_signal": 0.10
<                 }
---
>                     "volume_delta_signal": 0.10,
>                 },
242,243c215
<                     "mtf_analysis": True
<                     # ... less volatile indicators
---
>                     "mtf_analysis": True,
252,255c224,226
<                     "mtf_trend_confluence": 0.40
<                     # ... adjusted weights for trend following
<                 }
<             }
---
>                     "mtf_trend_confluence": 0.40,
>                 },
>             },
257d227
<         # Indicator Periods & Thresholds
300,304c270,273
<             "volatility_index_period": 20,  # New: Volatility Index Period
<             "vwma_period": 20,  # New: VWMA Period
<             "volume_delta_period": 5,  # New: Volume Delta Period
<             "volume_delta_threshold": 0.2,  # New: Volume Delta Threshold for signals
<             # ADX thresholds moved to indicator_settings for better config management
---
>             "volatility_index_period": 20,
>             "vwma_period": 20,
>             "volume_delta_period": 5,
>             "volume_delta_threshold": 0.2,
308,310c277,278
<         # Active Indicators & Weights (expanded)
<         "indicators": {}, # These will be overwritten by active profile
<         "weight_sets": {} # These will be overwritten by active profile
---
>         "indicators": {},
>         "active_weights": {},
322d289
<             # Fallback to default config even if file creation fails
330d296
<         # NEW: Logic to load the active strategy profile
334d299
<             # Overwrite global 'indicators' and 'active_weights' with active profile's settings
338c303
<                 config["active_weights"] = active_profile["weights"] # Store active weights here
---
>                 config["active_weights"] = active_profile["weights"]
342,343c307
<             # Fallback to previously existing `indicators` and `weight_sets.default_scalping` if profile not found
<             if "indicators" not in config: # Ensure a default if not found at all
---
>             if "indicators" not in config:
345c309
<             if "active_weights" not in config: # Ensure a default if not found at all
---
>             if "active_weights" not in config:
348d311
<         # Save the merged config to ensure consistency and add any new default keys
365d327
<     """Recursively ensure all keys from default_config are in config."""
371,373d332
<         # If config[key] exists but is not a dict, and default_value is a dict,
<         # it means the config file has a non-dict value where a dict is expected.
<         # This case is handled by overwriting with the default dict structure.
375,378c334
<              config[key] = default_value
< 
< 
< from unanimous_logger import setup_logger
---
>             config[key] = default_value
381,382d336
< # --- Logger Setup ---
< # A simple class to adapt the config dict to what setup_logger expects
385d338
<         # Extract log level from config, default to INFO
387,388d339
< 
<         # Construct log file path from constants defined in the script
391,392d341
< 
<         # Pass color codes
396c345
< # Create a temporary basic logger for the initial config loading
---
> 
402d350
< # Load the main configuration using the temporary logger
405,406c353,379
< # Create the config object for the unanimous logger
< logger_config = UnanimousLoggerConfig(config)
---
> try:
>     from unanimous_logger import setup_logger
> except ImportError:
>     print("unanimous_logger not found, using basic logging setup.")
>     def setup_logger(config_obj, log_name="default", json_log_file=None):
>         logger = logging.getLogger(log_name)
>         logger.setLevel(getattr(logging, config_obj.LOG_LEVEL))
> 
>         formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
> 
>         ch = logging.StreamHandler(sys.stdout)
>         ch.setLevel(getattr(logging, config_obj.LOG_LEVEL))
>         ch.setFormatter(formatter)
>         logger.addHandler(ch)
> 
>         fh = logging.FileHandler(config_obj.LOG_FILE_PATH)
>         fh.setLevel(getattr(logging, config_obj.LOG_LEVEL))
>         fh.setFormatter(formatter)
>         logger.addHandler(fh)
> 
>         if json_log_file:
>             json_formatter = logging.Formatter('{"time": "%(asctime)s", "name": "%(name)s", "level": "%(levelname)s", "message": "%(message)s", "extra": %(extra)s}')
>             json_fh = logging.FileHandler(os.path.join(LOG_DIRECTORY, json_log_file))
>             json_fh.setLevel(getattr(logging, config_obj.LOG_LEVEL))
>             json_fh.setFormatter(json_formatter)
>             logger.addHandler(json_fh)
>         return logger
408c381
< # Set up the main application logger using the loaded configuration
---
> logger_config = UnanimousLoggerConfig(config)
410,411d382
< # --- End Logger Setup ---
< 
414,415d384
< 
< # --- API Interaction ---
417d385
<     """Create a requests session with retry logic."""
430d397
<     """Generate a Bybit API signature."""
433c400
< # Add to API Interaction section, near generate_signature
---
> 
435d401
<     """Generate a Bybit WebSocket authentication signature."""
439a406
> 
447d413
<     """Send a request to the Bybit API."""
462c428
<         recv_window = "20000"  # Standard recommended receive window
---
>         recv_window = "20000"
465d430
<             # For GET, params should be part of the query string and param_str is timestamp + API_KEY + recv_window + query_string
481,482c446
<         else:  # POST
<             # For POST, params should be JSON stringified and param_str is timestamp + API_KEY + recv_window + json_params
---
>         else:
531a496,569
> def fetch_current_price(symbol: str, logger: logging.Logger, ws_manager: Optional['BybitWebSocketManager'] = None) -> Optional[Decimal]:
>     if ws_manager and ws_manager.is_connected_public:
>         latest_ticker = ws_manager.get_latest_ticker()
>         if latest_ticker and latest_ticker.get("symbol") == symbol and latest_ticker.get("lastPrice") is not None:
>             price = latest_ticker.get("lastPrice")
>             logger.debug(f"Fetched current price for {symbol} from WS: {price}")
>             return price
>         else:
>             logger.debug(f"{NEON_YELLOW}WS ticker data not available for {symbol}. Falling back to REST.{RESET}")
> 
>     endpoint = "/v5/market/tickers"
>     params = {"category": "linear", "symbol": symbol}
>     response = bybit_request("GET", endpoint, params, logger=logger)
>     if response and response["result"] and response["result"]["list"]:
>         price = Decimal(response["result"]["list"][0]["lastPrice"])
>         logger.debug(f"Fetched current price for {symbol} from REST: {price}")
>         return price
>     logger.warning(f"{NEON_YELLOW}[{symbol}] Could not fetch current price.{RESET}")
>     return None
> 
> 
> def fetch_klines(
>     symbol: str, interval: str, limit: int, logger: logging.Logger, ws_manager: Optional['BybitWebSocketManager'] = None
> ) -> Optional[pd.DataFrame]:
>     if ws_manager and ws_manager.is_connected_public and ws_manager.config["interval"] == interval and ws_manager.symbol == symbol:
>         ws_df = ws_manager.get_latest_kline_df()
>         if not ws_df.empty:
>             if len(ws_df) >= limit:
>                 logger.debug(f"Fetched {len(ws_df)} {interval} klines for {symbol} from WS.")
>                 return ws_df.tail(limit).copy()
>             else:
>                 logger.debug(f"{NEON_YELLOW}WS kline data has {len(ws_df)} bars, less than requested {limit}. Falling back to REST for full history.{RESET}")
> 
>     endpoint = "/v5/market/kline"
>     params = {
>         "category": "linear",
>         "symbol": symbol,
>         "interval": interval,
>         "limit": limit,
>     }
>     response = bybit_request("GET", endpoint, params, logger=logger)
>     if response and response["result"] and response["result"]["list"]:
>         df = pd.DataFrame(
>             response["result"]["list"],
>             columns=[
>                 "start_time",
>                 "open",
>                 "high",
>                 "low",
>                 "close",
>                 "volume",
>                 "turnover",
>             ],
>         )
>         df["start_time"] = pd.to_datetime(
>             df["start_time"].astype(int), unit="ms", utc=True
>         ).dt.tz_convert(TIMEZONE)
>         for col in ["open", "high", "low", "close", "volume", "turnover"]:
>             df[col] = pd.to_numeric(df[col], errors="coerce")
>         df.set_index("start_time", inplace=True)
>         df.sort_index(inplace=True)
> 
>         if df.empty:
>             logger.warning(
>                 f"{NEON_YELLOW}[{symbol}] Fetched klines for {interval} but DataFrame is empty after processing. Raw response: {response}{RESET}"
>             )
>             return None
> 
>         logger.debug(f"Fetched {len(df)} {interval} klines for {symbol} from REST.")
>         return df
>     logger.warning(
>         f"{NEON_YELLOW}[{symbol}] Could not fetch klines for {interval}. API response might be empty or invalid. Raw response: {response}{RESET}"
>     )
>     return None
533a572,597
> def fetch_orderbook(symbol: str, limit: int, logger: logging.Logger, ws_manager: 'BybitWebSocketManager' | None = None) -> dict | None:
>     if ws_manager and ws_manager.is_connected_public and ws_manager.symbol == symbol:
>         ws_orderbook = ws_manager.get_latest_orderbook_dict()
>         if ws_orderbook and ws_orderbook["bids"] and ws_orderbook["asks"]:
>             logger.debug(f"Fetched orderbook for {symbol} from WS.")
>             return {
>                 "s": symbol,
>                 "b": ws_orderbook["bids"][:limit],
>                 "a": ws_orderbook["asks"][:limit],
>                 "u": None,
>                 "seq": None
>             }
>         else:
>             logger.debug(f"{NEON_YELLOW}WS orderbook data not available for {symbol}. Falling back to REST.{RESET}")
> 
>     endpoint = "/v5/market/orderbook"
>     params = {"category": "linear", "symbol": symbol, "limit": limit}
>     response = bybit_request("GET", endpoint, params, logger=logger)
>     if response and response["result"]:
>         logger.debug(f"Fetched orderbook for {symbol} with limit {limit} from REST.")
>         result = response["result"]
>         result["b"] = [[Decimal(price), Decimal(qty)] for price, qty in result.get("b", [])]
>         result["a"] = [[Decimal(price), Decimal(qty)] for price, qty in result.get("a", [])]
>         return result
>     logger.warning(f"{NEON_YELLOW}[{symbol}] Could not fetch orderbook.{RESET}")
>     return None
535d598
< # --- Trading Specific API Interactions ---
543c606
<     price: Decimal | None = None, # Required for Limit orders
---
>     price: Decimal | None = None,
546,549d608
<     """
<     Places a market order on Bybit.
<     https://bybit-exchange.github.io/docs/v5/order/create
<     """
552d610
<     # Ensure qty is a string with correct precision
558c616
<         "qty": str(qty.normalize()), # Ensure Decimal is converted to string for API
---
>         "qty": str(qty.normalize()),
565c623
<         order_params["price"] = str(price.normalize()) # Ensure Decimal is converted to string
---
>         order_params["price"] = str(price.normalize())
582c640
<     position_idx: int = 0, # Assuming One-Way Mode (0 for both long/short)
---
>     position_idx: int = 0,
585,588d642
<     """
<     Sets or updates Take Profit and Stop Loss for an existing position.
<     https://bybit-exchange.github.io/docs/v5/position/trading-stop
<     """
619,622d672
<     """
<     Fetches all open positions for a given symbol from the Bybit exchange.
<     https://bybit-exchange.github.io/docs/v5/position/query
<     """
631d680
<         # Filter for truly open positions (size > 0)
641d689
< # --- Position Management ---
643,646c691
<     """Manages open positions, stop-loss, and take-profit levels."""
< 
<     def __init__(self, config: dict[str, Any], logger: logging.Logger, symbol: str, ws_manager: Optional['BybitWebSocketManager'] = None):
<         """Initializes the PositionManager."""
---
>     def __init__(self, config: dict[str, Any], logger: logging.Logger, symbol: str, ws_manager: 'BybitWebSocketManager' | None = None):
650,665c695
<         self.ws_manager = ws_manager # Store WS manager
<         # open_positions will now store detailed exchange-confirmed position data
<         # {
<         #   "positionIdx": int, # 0 for one-way, 1 for long, 2 for short (hedge)
<         #   "side": str,        # "Buy" or "Sell"
<         #   "entry_price": Decimal,
<         #   "qty": Decimal,
<         #   "stop_loss": Decimal,
<         #   "take_profit": Decimal,
<         #   "position_id": str, # Bybit's positionId
<         #   "order_id": str,    # Bybit's orderId for the entry trade
<         #   "entry_time": datetime,
<         #   "initial_stop_loss": Decimal, # The SL set at entry, before TSL modifications
<         #   "trailing_stop_activated": bool,
<         #   "trailing_stop_price": Decimal | None # The actual trailing stop price set on exchange
<         # }
---
>         self.ws_manager = ws_manager
675d704
<         # Define precision for quantization, e.g., 5 decimal places for crypto
679d707
<         # Initial sync of open positions from exchange
683,695d710
<         """
<         Fetch current account balance (simplified for simulation).
<         In a real bot, this would query the exchange's wallet balance.
<         """
<         # Example API call for real balance (needs authentication):
<         # endpoint = "/v5/account/wallet-balance"
<         # params = {"accountType": "UNIFIED"} # Or "CONTRACT" depending on account type
<         # response = bybit_request("GET", endpoint, params, signed=True, logger=self.logger)
<         # if response and response["result"] and response["result"]["list"]:
<         #     for coin_balance in response["result"]["list"][0]["coin"]:
<         #         if coin_balance["coin"] == "USDT": # Assuming USDT as base currency
<         #             return Decimal(coin_balance["walletBalance"])
<         # Fallback to configured balance for simulation
701,706d715
<         """
<         Calculate order size based on risk per trade and ATR.
<         The formula uses a fixed risk amount relative to account balance,
<         divided by the stop-loss distance (ATR * multiple) to determine
<         the 'notional' value to trade, then converted to asset quantity.
<         """
728d736
<         # Order size in USD value
730d737
<         # Convert to quantity of the asset (e.g., BTC)
733d739
<         # Round order_qty to appropriate precision for the symbol
742,809d747
<         """Fetches current open positions from the exchange and updates the internal list."""
<         exchange_positions = get_open_positions_from_exchange(self.symbol, self.logger)
<         
<         new_open_positions = []
<         for ex_pos in exchange_positions:
<             # Bybit API returns 'Buy' or 'Sell' for position side
<             side = ex_pos["side"]
<             qty = Decimal(ex_pos["size"])
<             entry_price = Decimal(ex_pos["avgPrice"])
<             stop_loss_price = Decimal(ex_pos.get("stopLoss", "0")) if ex_pos.get("stopLoss") else Decimal("0")
<             take_profit_price = Decimal(ex_pos.get("takeProfit", "0")) if ex_pos.get("takeProfit") else Decimal("0")
<             trailing_stop = Decimal(ex_pos.get("trailingStop", "0")) if ex_pos.get("trailingStop") else Decimal("0")
< 
<             # Check if this position is already in our tracked list
<             existing_pos = next(
<                 (p for p in self.open_positions if p.get("position_id") == ex_pos["positionIdx"] and p.get("side") == side),
<                 None,
<             )
< 
<             if existing_pos:
<                 # Update existing position details
<                 existing_pos.update({
<                     "entry_price": entry_price.quantize(self.price_quantize_dec),
<                     "qty": qty.quantize(self.qty_quantize_dec),
<                     "stop_loss": stop_loss_price.quantize(self.price_quantize_dec),
<                     "take_profit": take_profit_price.quantize(self.price_quantize_dec),
<                     "trailing_stop_price": trailing_stop.quantize(self.price_quantize_dec) if trailing_stop else None,
<                     # Recalculate 'trailing_stop_activated' if needed based on `trailing_stop` field.
<                     "trailing_stop_activated": trailing_stop > 0 if self.enable_trailing_stop else False
<                 })
<                 new_open_positions.append(existing_pos)
<             else:
<                 # Add new position detected on exchange
<                 self.logger.warning(f"{NEON_YELLOW}[{self.symbol}] Detected new untracked position on exchange. Side: {side}, Qty: {qty}, Entry: {entry_price}. Adding to internal tracking.{RESET}")
<                 # We can't determine original initial_stop_loss or entry_time easily, so estimate
<                 new_open_positions.append({
<                     "positionIdx": ex_pos["positionIdx"],
<                     "side": side,
<                     "entry_price": entry_price.quantize(self.price_quantize_dec),
<                     "qty": qty.quantize(self.qty_quantize_dec),
<                     "stop_loss": stop_loss_price.quantize(self.price_quantize_dec),
<                     "take_profit": take_profit_price.quantize(self.price_quantize_dec),
<                     "position_id": ex_pos.get("positionId", str(ex_pos["positionIdx"])), # Use positionIdx as ID if no explicit positionId
<                     "order_id": "UNKNOWN", # Cannot retrieve original order ID easily from position list
<                     "entry_time": datetime.now(TIMEZONE), # Estimate if not available
<                     "initial_stop_loss": stop_loss_price.quantize(self.price_quantize_dec), # Assume current SL is initial if not tracked
<                     "trailing_stop_activated": trailing_stop > 0 if self.enable_trailing_stop else False,
<                     "trailing_stop_price": trailing_stop.quantize(self.price_quantize_dec) if trailing_stop else None,
<                 })
<         
<         # Identify positions that were tracked internally but are no longer on the exchange
<         # This means they were closed (by SL/TP hit or manual intervention)
<         for tracked_pos in self.open_positions:
<             is_still_open = any(
<                 ex_pos["positionIdx"] == tracked_pos.get("position_id") and ex_pos["side"] == tracked_pos["side"]
<                 for ex_pos in exchange_positions
<             )
<             if not is_still_open:
<                 self.logger.info(f"{NEON_BLUE}[{self.symbol}] Position {tracked_pos['side']} (ID: {tracked_pos.get('position_id', 'N/A')}) no longer open on exchange. Marking as closed.{RESET}")
<                 # Record this closure in performance_tracker if it was successfully opened by us
<                 # (This part would ideally be called by `manage_positions` when it detects an actual close event from exchange)
<         
<         self.open_positions = new_open_positions
<         if not self.open_positions:
<             self.logger.debug(f"[{self.symbol}] No active positions being tracked internally.")
< 
<     def sync_positions_from_exchange(self):
<         """Fetches current open positions from the exchange and updates the internal list."""
814d751
<             # Bybit API returns 'Buy' or 'Sell' for position side
822d758
<             # Check if this position is already in our tracked list
824c760
<                 (p for p in self.open_positions if p.get("position_id") == ex_pos["positionIdx"] and p.get("side") == side),
---
>                 (p for p in self.open_positions if str(p.get("position_id")) == str(ex_pos.get("positionIdx", ex_pos.get("positionId"))) and p.get("side") == side),
829d764
<                 # Update existing position details
836d770
<                     # Recalculate 'trailing_stop_activated' if needed based on `trailing_stop` field.
841d774
<                 # Add new position detected on exchange
843d775
<                 # We can't determine original initial_stop_loss or entry_time easily, so estimate
845c777
<                     "positionIdx": ex_pos["positionIdx"],
---
>                     "positionIdx": int(ex_pos.get("positionIdx", 0)),
851,854c783,786
<                     "position_id": ex_pos.get("positionId", str(ex_pos["positionIdx"])), # Use positionIdx as ID if no explicit positionId
<                     "order_id": "UNKNOWN", # Cannot retrieve original order ID easily from position list
<                     "entry_time": datetime.now(TIMEZONE), # Estimate if not available
<                     "initial_stop_loss": stop_loss_price.quantize(self.price_quantize_dec), # Assume current SL is initial if not tracked
---
>                     "position_id": str(ex_pos.get("positionId", ex_pos.get("positionIdx", 0))),
>                     "order_id": "UNKNOWN",
>                     "entry_time": datetime.now(TIMEZONE),
>                     "initial_stop_loss": stop_loss_price.quantize(self.price_quantize_dec),
859,860d790
<         # Identify positions that were tracked internally but are no longer on the exchange
<         # This means they were closed (by SL/TP hit or manual intervention)
863c793
<                 ex_pos["positionIdx"] == tracked_pos.get("position_id") and ex_pos["side"] == tracked_pos["side"]
---
>                 str(ex_pos.get("positionId", ex_pos.get("positionIdx"))) == str(tracked_pos.get("position_id")) and ex_pos["side"] == tracked_pos["side"]
868,869d797
<                 # Record this closure in performance_tracker if it was successfully opened by us
<                 # (This part would ideally be called by `manage_positions` when it detects an actual close event from exchange)
877c805
<         self, signal_side: Literal["BUY", "SELL"], current_price: Decimal, atr_value: Decimal
---
>         self, signal_side: Literal["Buy", "Sell"], current_price: Decimal, atr_value: Decimal
879d806
<         """Open a new position if conditions allow, interacting with the Bybit API."""
886c813
<         self.sync_positions_from_exchange() # Always sync before opening to get latest count
---
>         self.sync_positions_from_exchange()
893,895c820
<         # Ensure we don't open multiple positions of the same side if in one-way mode.
<         # Bybit's API might allow it, but conceptually for a bot, it's often one per side.
<         if any(p["side"].upper() == signal_side for p in self.get_open_positions()):
---
>         if any(p["side"].upper() == signal_side.upper() for p in self.get_open_positions()):
914,915c839
<         # Calculate initial SL and TP based on current price
<         if signal_side == "BUY":
---
>         if signal_side == "Buy":
918c842
<         else:  # SELL
---
>         else:
922d845
<         # --- Place Market Order ---
929,933c852,853
<         # Extract actual filled price and quantity from order result
<         # For a market order, the `price` in the response is usually the filled price.
<         # If filledQty is available, use that.
<         filled_qty = Decimal(order_result.get("qty", str(order_qty))) # Fallback to requested qty
<         filled_price = Decimal(order_result.get("price", str(current_price))) # Fallback to current price if not explicitly returned
---
>         filled_qty = Decimal(order_result.get("qty", str(order_qty)))
>         filled_price = Decimal(order_result.get("price", str(current_price)))
936,937d855
<         # Bybit often returns `positionIdx` in the order result, or we assume 0 for one-way mode.
<         # The positionId from /v5/position/list is also often 0 for one-way
940,942d857
<         # --- Set TP/SL for the newly opened position ---
<         # It's crucial to set TP/SL *after* the position is open on the exchange.
<         # Bybit's set-trading-stop endpoint uses the position's `positionIdx`.
953,954d867
<             # Consider closing the position if TP/SL cannot be set for risk management.
<             # For this snippet, we proceed but log a severe warning.
962c875
<             "stop_loss": initial_stop_loss, # This will be the dynamic SL
---
>             "stop_loss": initial_stop_loss,
964c877
<             "position_id": position_idx_on_exchange, # Using positionIdx as its unique ID for one-way mode
---
>             "position_id": str(position_idx_on_exchange),
967c880
<             "initial_stop_loss": initial_stop_loss, # Store original SL
---
>             "initial_stop_loss": initial_stop_loss,
969c882
<             "trailing_stop_price": None, # Will be set when TSL is activated on exchange
---
>             "trailing_stop_price": None,
979,982d891
<         """
<         Syncs open positions from the exchange and applies trailing stop logic.
<         Records closed positions based on exchange updates.
<         """
986d894
<         # 1. Sync internal state with actual exchange positions
989d896
<         # Create a copy to iterate, allowing modification of original list if positions are closed.
993d899
<         # Iterate through the internally tracked positions
995,1001d900
<             # First, check if this position is still genuinely open on the exchange
<             # This is implicitly handled by `sync_positions_from_exchange` which rebuilds `self.open_positions`
<             # If a position exists in `self.open_positions` after sync, it means it's still open on the exchange.
<             # If it's not in `self.open_positions` after sync, it means it was closed on the exchange.
<             
<             # Retrieve the latest version of the position from `self.open_positions` after sync
<             # This is important to get the most up-to-date SL/TP/trailingStop values from Bybit
1003c902
<                 (p for p in self.open_positions if p.get("position_id") == position.get("position_id") and p.get("side") == position.get("side")),
---
>                 (p for p in self.open_positions if str(p.get("position_id")) == str(position.get("position_id")) and p.get("side") == position.get("side")),
1008,1011d906
<                 # Position was closed on the exchange. Record it.
<                 # Since we don't get direct 'closed by' reason from just `position/list` for historical close,
<                 # we'll use our internal current_price vs. position's last known SL/TP to infer.
<                 # In a real bot, you'd check historical orders or webhooks for precise exit details.
1014c909
<                 if position["side"] == "BUY":
---
>                 if position["side"] == "Buy":
1019c914
<                 else: # SELL
---
>                 else:
1025d919
<                 # Calculate PnL for recording
1028c922
<                     if position["side"] == "BUY"
---
>                     if position["side"] == "Buy"
1032,1033d925
<                 # Ensure the trade is only recorded once
<                 # A more robust system would involve a persistent storage for positions and trades.
1040c932
<                 continue # Skip trailing stop logic for this position as it's closed
---
>                 continue
1042d933
<             # Use the latest synced position details for trailing stop logic
1047,1048c938
<             current_stop_loss_on_exchange = position["stop_loss"] # This is what Bybit has for SL
<             # take_profit_on_exchange = position["take_profit"] # Not directly used for TSL logic, but could be for other checks
---
>             current_stop_loss_on_exchange = position["stop_loss"]
1050d939
<             # --- Trailing Stop Loss Logic ---
1052c941
<                 profit_trigger_level = entry_price + (atr_value * self.break_even_atr_trigger) if side == "BUY" \
---
>                 profit_trigger_level = entry_price + (atr_value * self.break_even_atr_trigger) if side == "Buy" \
1055,1057c944,945
<                 # Check if price has moved sufficiently into profit to activate/adjust TSL
<                 if (side == "BUY" and current_price >= profit_trigger_level) or \
<                    (side == "SELL" and current_price <= profit_trigger_level):
---
>                 if (side == "Buy" and current_price >= profit_trigger_level) or \
>                    (side == "Sell" and current_price <= profit_trigger_level):
1061,1062c949
<                     # Calculate new potential trailing stop based on current price and ATR multiple
<                     new_trailing_stop_candidate = (current_price - (atr_value * self.trailing_stop_atr_multiple)).quantize(self.price_quantize_dec, rounding=ROUND_DOWN) if side == "BUY" \
---
>                     new_trailing_stop_candidate = (current_price - (atr_value * self.trailing_stop_atr_multiple)).quantize(self.price_quantize_dec, rounding=ROUND_DOWN) if side == "Buy" \
1065,1068d951
<                     # Ensure TSL does not move against the position or below initial stop loss (for BUY) / above initial stop loss (for SELL)
<                     # For BUY: new_tsl > current_sl_on_exchange AND new_tsl > initial_sl (if not already passed initial_sl)
<                     # For SELL: new_tsl < current_sl_on_exchange AND new_tsl < initial_sl (if not already passed initial_sl)
<                     
1072,1073c955
<                     if side == "BUY":
<                         # Move SL up, but not below its initial entry value
---
>                     if side == "Buy":
1076c958
<                              if updated_sl_value > current_stop_loss_on_exchange: # Only update if it actually moves further into profit
---
>                              if updated_sl_value > current_stop_loss_on_exchange:
1079d960
<                             # Edge case: If TSL started below initial_SL (e.g., initial_SL was very tight) and moved to initial_SL level
1084,1085c965
<                     elif side == "SELL":
<                         # Move SL down, but not above its initial entry value
---
>                     elif side == "Sell":
1088c968
<                              if updated_sl_value < current_stop_loss_on_exchange: # Only update if it actually moves further into profit
---
>                              if updated_sl_value < current_stop_loss_on_exchange:
1091d970
<                             # Edge case: If TSL started above initial_SL and moved to initial_SL level
1097d975
<                         # Call Bybit API to update the stop loss
1100c978
<                             take_profit=position["take_profit"], # Keep TP the same
---
>                             take_profit=position["take_profit"],
1106d983
<                             # Update internal tracking
1108c985
<                             position["trailing_stop_price"] = updated_sl_value # Store the TSL value
---
>                             position["trailing_stop_price"] = updated_sl_value
1115,1121d991
<             # Note: The actual closing of the position (by SL or TP) is handled by the exchange.
<             # Our `sync_positions_from_exchange` will detect if a position is no longer present.
< 
<         # After checking all positions, ensure `self.open_positions` only contains truly open ones.
<         # This is already handled by `self.sync_positions_from_exchange()` at the start.
<         # However, to be extra robust, one could filter out the `positions_closed_on_exchange_ids` here as well,
<         # but `sync_positions_from_exchange` should already have removed them.
1128,1129d997
<         """Return a list of currently open positions tracked internally."""
<         # This is just returning the internal state, which is periodically synced with exchange
1133d1000
< # --- Performance Tracking ---
1135,1136d1001
<     """Tracks and reports trading performance."""
< 
1138d1002
<         """Initializes the PerformanceTracker."""
1146d1009
<         """Record a completed trade."""
1170d1032
<         """Return a summary of all recorded trades."""
1183d1044
< # --- Alert System ---
1185,1186d1045
<     """Handles sending alerts for critical events."""
< 
1188d1046
<         """Initializes the AlertSystem."""
1192d1049
<         """Send an alert (currently logs it)."""
1199d1055
<         # In a real bot, integrate with Telegram, Discord, Email etc.
1202d1057
< # Place this class after AlertSystem or other utility classes
1204,1205d1058
<     """Manages Bybit WebSocket connections and provides real-time data."""
< 
1218d1070
<         # Shared data structures with locks for thread-safety
1223c1075
<         self.latest_trades: deque = deque(maxlen=config.get("orderbook_limit", 50)) # Stores recent trades
---
>         self.latest_trades: deque = deque(maxlen=config.get("orderbook_limit", 50))
1225c1077
<         self.latest_ticker: dict[str, Any] = {} # For current price, lastPrice
---
>         self.latest_ticker: dict[str, Any] = {}
1228d1079
<         # Real-time updates for position manager
1232d1082
<         # Flags for initial data availability
1237d1086
<         # Topics to subscribe, derived from config
1242c1091
<             f"tickers.{self.symbol}" # For latest price updates
---
>             f"tickers.{self.symbol}"
1244,1245c1093
<         # Private topics are generally fixed for account-related updates
<         self.private_topics = DEFAULT_PRIVATE_TOPICS # ["order", "position", "wallet"]
---
>         self.private_topics = DEFAULT_PRIVATE_TOPICS
1249c1097
<         self._stop_event = threading.Event() # Event to signal threads to stop
---
>         self._stop_event = threading.Event()
1258c1106
<         expires = int(time.time() * 1000) + 10000 # Message expires in 10 seconds
---
>         expires = int(time.time() * 1000) + 10000
1267d1114
<         # Subscribe after a short delay to allow auth to process, or wait for auth success message
1283d1129
<             # Initial kline data, or resync snapshot
1287d1132
<             # Update to the latest kline bar
1297c1142
<             self._update_ticker(data["data"][0]) # Tickers usually come as a list of one item
---
>             self._update_ticker(data["data"][0])
1310d1154
<                 # Trigger a reconnect for private WS if auth fails
1320d1163
<         # Handle private data topics: order, position, wallet
1325d1167
<                 # Put the full raw message into the queue for PositionManager to process
1344d1185
<         # Attempt reconnection unless stop event is set
1347,1348c1188
<             time.sleep(WS_RECONNECT_DELAY_SECONDS) # Wait before reconnecting
<             # Restart the appropriate thread
---
>             time.sleep(WS_RECONNECT_DELAY_SECONDS)
1360d1199
<         """Helper to run a WebSocket connection in a separate thread."""
1376d1214
<                 # Keep the connection alive
1378c1216
<                     ping_interval=20, # Bybit recommends 10-20 seconds
---
>                     ping_interval=20,
1380c1218
<                     sslopt={"cert_reqs": ssl.CERT_NONE} # For some environments, might need to ignore cert validation
---
>                     sslopt={"cert_reqs": ssl.CERT_NONE}
1392d1229
<         """Sends subscription messages to the WebSocket."""
1408,1409c1245
<         """Starts the public WebSocket stream in a new thread."""
<         self._stop_event.clear() # Ensure stop event is clear before starting
---
>         self._stop_event.clear()
1420d1255
<         """Starts the private WebSocket stream in a new thread."""
1424c1259
<         self._stop_event.clear() # Ensure stop event is clear before starting
---
>         self._stop_event.clear()
1435d1269
<         """Signals all WebSocket threads to stop and closes connections."""
1449d1282
<     # --- Data Update Methods ---
1451d1283
<         """Updates the internal klines DataFrame."""
1455,1459d1286
<         # Bybit kline data: [start_time, open, high, low, close, volume, turnover]
<         # Example data format in WS:
<         # { "start": 1672531200000, "open": "16500", "high": "16600", "low": "16450",
<         #   "close": "16550", "volume": "100", "turnover": "1655000" }
< 
1476d1302
<                 # Replace the entire DataFrame if it's a snapshot
1480d1305
<                 # For delta updates (partial bar updates), append or update the last bar
1483d1307
<                         # Update existing bar (it's often the current open bar being updated)
1486,1487d1309
<                         # Append new bar (e.g., when a new bar opens)
<                         # Ensure no duplicate timestamps before appending
1489,1490d1310
<                             # This should not happen if WS sends strict new bar or current bar updates
<                             # but as a safeguard, if we get an old or duplicate, skip.
1493c1313
<                         self.latest_klines = pd.concat([self.latest_klines, df_new]) # Appending just one row more efficient
---
>                         self.latest_klines = pd.concat([self.latest_klines, pd.DataFrame([row])])
1495d1314
<             # Ensure the DataFrame is sorted by index
1497,1498c1316
<             # Trim the DataFrame to a reasonable size to prevent memory issues
<             max_kline_history = 1000 # Keep enough for indicator calculations
---
>             max_kline_history = 1000
1502d1319
<             # Convert numeric columns to Decimal after concat/update for consistency
1508d1324
<         """Updates the internal orderbook data."""
1517,1528c1333
<             else: # Delta updates
<                 # Bybit delta updates require manual merging
<                 # This is a simplified merge. For production, a more robust orderbook reconstruction is needed.
<                 # Example: https://bybit-exchange.github.io/docs/v5/ws/orderbook/linear
<                 
<                 # For simplicity, if it's a delta, and we don't have a snapshot, request a resync.
<                 # Or, if this snippet assumes a simple overwrite for delta, that would be:
<                 
<                 # Append or update bids/asks
<                 # For true deltas, you'd process 'd' (delete), 'u' (update), 'i' (insert)
<                 # For this snippet, let's simplify:
<                 # If a snapshot isn't available, we can't reliably apply deltas.
---
>             else:
1531d1335
<                     # In a real system, you might trigger a full re-subscription or REST call here.
1534,1546d1337
<                 # For Bybit V5, 'delta' usually contains 'u' for updates and 'd' for deletes
<                 # It's not a full diff merge, it's just 'new values'.
<                 # A proper order book merge involves iterating and replacing specific levels.
<                 # For a snippet, and given the bot's current usage (imbalance check),
<                 # receiving frequent 'snapshot' or reconstructing from a full 'update' is more common.
<                 # If 'data' is the full current state (which sometimes happens for 'update' messages),
<                 # replace:
<                 
<                 # Assuming `data` structure is similar to snapshot for updates.
<                 # This means it might be a full 'update' representing the current state rather than a true delta list of changes.
<                 # If it's a list of bids/asks to be merged, a merging logic is needed.
<                 # For simplicity, if this is an "update" message with 'b' and 'a', we'll treat it as latest full view.
<                 
1557d1347
<         """Updates the internal trades deque."""
1560,1563d1349
<                 # Example trade data:
<                 # { "timestamp": 1672531200000, "symbol": "BTCUSDT", "side": "Buy",
<                 #   "size": "0.1", "price": "16550", "tickDirection": "PlusTick",
<                 #   "tradeId": "12345", "isBlockTrade": False }
1573d1358
<         """Updates the latest ticker information."""
1585d1369
<     # --- Data Retrieval Methods for Main Thread ---
1587d1370
<         """Returns the current klines DataFrame, thread-safe."""
1592d1374
<         """Returns the current orderbook dictionary, thread-safe."""
1597d1378
<         """Returns the latest ticker information, thread-safe."""
1602d1382
<         """Returns all accumulated private updates and clears the queue."""
1610d1389
<         """Waits for initial public and private data to be received."""
1613d1391
<         # Wait for klines and orderbook. Ticker will also come through with public.
1616c1394
<         private_ready = self.initial_private_data_received.wait(timeout) # Private might take longer
---
>         private_ready = self.initial_private_data_received.wait(timeout)
1631d1408
< # --- Trading Analysis (Upgraded with Ehlers SuperTrend and more) ---
1633,1634d1409
<     """Analyzes trading data and generates signals with MTF, Ehlers SuperTrend, and other new indicators."""
< 
1642d1416
<         """Initializes the TradingAnalyzer."""
1649,1650c1423
<         # OLD: self.weights = config["weight_sets"].get("default_scalping", {})
<         self.weights = config.get("active_weights", {}) # NEW: Load active weights from the 'active_weights' key
---
>         self.weights = config.get("active_weights", {})
1652,1653c1425,1426
<         self._last_signal_ts = 0 # Initialize last signal timestamp
<         self._last_signal_score = 0.0 # Initialize last signal score
---
>         self._last_signal_ts = 0
>         self._last_signal_score = 0.0
1668d1440
<         """Safely calculate indicators and log errors, with min_data_points check."""
1699d1470
<         """Calculate all enabled technical indicators, including Ehlers SuperTrend."""
1704d1474
<         # SMA
1722d1491
<         # EMA
1743d1511
<         # ATR
1755d1522
<         # RSI
1766d1532
<         # Stochastic RSI
1787d1552
<         # Bollinger Bands
1809d1573
<         # CCI
1820d1583
<         # Williams %R
1831d1593
<         # MFI
1842d1603
<         # OBV
1859d1619
<         # CMF
1872d1631
<         # Ichimoku Cloud
1912d1670
<         # PSAR
1930d1687
<         # VWAP (requires volume and turnover, which are in df)
1938d1694
<         # --- Ehlers SuperTrend Calculation ---
1943c1699
<                 min_data_points=isd["ehlers_fast_period"] * 3, # Heuristic for sufficient data
---
>                 min_data_points=isd["ehlers_fast_period"] * 3,
1960c1716
<                 min_data_points=isd["ehlers_slow_period"] * 3, # Heuristic for sufficient data
---
>                 min_data_points=isd["ehlers_slow_period"] * 3,
1974d1729
<         # MACD
1997d1751
<         # ADX
2002c1756
<                 min_data_points=isd["adx_period"] * 2, # ADX requires at least 2*period for smoothing
---
>                 min_data_points=isd["adx_period"] * 2,
2018,2019d1771
<         # --- New Indicators ---
<         # Volatility Index
2032d1783
<         # VWMA
2043d1793
<         # Volume Delta
2054d1803
<         # Final dropna after all indicators are calculated
2056,2059c1805
<         self.df.dropna(subset=["close"], inplace=True) # Ensure close price is valid
<         # Fill remaining NaNs in indicator columns with 0 or a sensible default if appropriate.
<         # For signal generation, NaNs might be better handled as 'no signal contribution'.
<         # However, for simplicity in this refactor, we'll fill with 0 for now, and scoring methods handle NaNs.
---
>         self.df.dropna(subset=["close"], inplace=True)
2077d1822
<         """Calculate True Range (TR)."""
2088d1832
<         """Apply Ehlers SuperSmoother filter to reduce lag and noise."""
2119,2121c1863
<         """Calculate SuperTrend using Ehlers SuperSmoother for price and volatility."""
<         # Ensure enough data points for calculation
<         min_bars_required = period * 3 # A common heuristic
---
>         min_bars_required = period * 3
2151d1892
<         # Find the first valid index after smoothing
2159d1899
<         # Initialize the first valid supertrend value based on the first valid close price relative to bands
2168c1908
<         else:  # Price is within bands, initialize with lower band, neutral direction
---
>         else:
2177,2178c1917
<             if prev_direction == 1:  # Previous was an UP trend
<                 # If current close drops below the prev_supertrend, flip to DOWN
---
>             if prev_direction == 1:
2181,2182c1920,1921
<                     supertrend.iloc[i] = upper_band.iloc[i]  # New ST is upper band
<                 else:  # Continue UP trend
---
>                     supertrend.iloc[i] = upper_band.iloc[i]
>                 else:
2184d1922
<                     # New ST is max of current lower_band and prev_supertrend
2186,2187c1924
<             elif prev_direction == -1:  # Previous was a DOWN trend
<                 # If current close rises above the prev_supertrend, flip to UP
---
>             elif prev_direction == -1:
2190,2191c1927,1928
<                     supertrend.iloc[i] = lower_band.iloc[i]  # New ST is lower band
<                 else:  # Continue DOWN trend
---
>                     supertrend.iloc[i] = lower_band.iloc[i]
>                 else:
2193d1929
<                     # New ST is min of current upper_band and prev_supertrend
2195c1931
<             else:  # Previous was neutral or initial state (handle explicitly)
---
>             else:
2202,2204c1938,1940
<                 else:  # Still within bands or undecided, stick to previous or default
<                     direction.iloc[i] = prev_direction  # Maintain previous direction
<                     supertrend.iloc[i] = prev_supertrend  # Maintain previous supertrend
---
>                 else:
>                     direction.iloc[i] = prev_direction
>                     supertrend.iloc[i] = prev_supertrend
2212d1947
<         """Calculate Moving Average Convergence Divergence (MACD)."""
2226d1960
<         """Calculate Relative Strength Index (RSI)."""
2236d1969
<         # Handle division by zero for rs where avg_loss is 0
2244d1976
<         """Calculate Stochastic RSI."""
2254d1985
<         # Avoid division by zero if highest_rsi == lowest_rsi
2256c1987
<         denominator[denominator == 0] = np.nan  # Replace 0 with NaN for division
---
>         denominator[denominator == 0] = np.nan
2258c1989
<         stoch_rsi_k_raw = stoch_rsi_k_raw.fillna(0).clip(0, 100) # Clip to [0, 100] and fill remaining NaNs with 0
---
>         stoch_rsi_k_raw = stoch_rsi_k_raw.fillna(0).clip(0, 100)
2268d1998
<         """Calculate Average Directional Index (ADX)."""
2272d2001
<         # True Range
2275d2003
<         # Directional Movement
2282d2009
<         # Apply +DM and -DM logic
2289d2015
<         # Smoothed True Range, +DM, -DM
2294d2019
<         # DX
2297d2021
<         # Handle division by zero
2300d2023
<         # ADX
2308d2030
<         """Calculate Bollinger Bands."""
2322d2043
<         """Calculate Volume Weighted Average Price (VWAP)."""
2326d2046
<         # Ensure cumulative sum starts from valid data, reindex to original df index
2329c2049
<         vwap = cumulative_tp_vol / cumulative_vol.replace(0, np.nan) # Handle division by zero
---
>         vwap = cumulative_tp_vol / cumulative_vol.replace(0, np.nan)
2333d2052
<         """Calculate Commodity Channel Index (CCI)."""
2341,2342c2060
<         # Handle potential division by zero for mad
<         cci = (tp - sma_tp) / (0.015 * mad.replace(0, np.nan))
---
>         cci = (tp - sma_tp) / (Decimal("0.015") * mad.replace(0, np.nan))
2346d2063
<         """Calculate Williams %R."""
2351d2067
<         # Handle division by zero
2363,2364d2078
<         """Calculate Ichimoku Cloud components."""
<         # Ensure enough data points for all components and the shift
2388d2101
<         # Senkou Span A is calculated based on Tenkan and Kijun, then shifted forward
2391d2103
<         # Senkou Span B is calculated based on highest high and lowest low over its period, then shifted forward
2405d2116
<         """Calculate Money Flow Index (MFI)."""
2414d2124
<         # Calculate positive and negative money flow
2419d2128
<         # Rolling sum for period
2423d2131
<         # Avoid division by zero
2429d2136
<         """Calculate On-Balance Volume (OBV) and its EMA."""
2434d2140
<         # Calculate OBV direction change and cumulative sum
2443d2148
<         """Calculate Chaikin Money Flow (CMF)."""
2447d2151
<         # Money Flow Multiplier (MFM)
2449d2152
<         # Handle division by zero for high_low_range
2455d2157
<         # Money Flow Volume (MFV)
2458d2159
<         # CMF
2460d2160
<         # Handle division by zero for volume_sum
2469d2168
<         """Calculate Parabolic SAR."""
2478d2176
<         # Initialize EP based on the direction of the first two bars
2489,2490c2187
<             # Calculate current PSAR value
<             if prev_bull:  # Bullish trend
---
>             if prev_bull:
2492c2189
<             else:  # Bearish trend
---
>             else:
2495d2191
<             # Check for reversal conditions
2498c2194
<                 bull.iloc[i] = False  # Reverse to bearish
---
>                 bull.iloc[i] = False
2501c2197
<                 bull.iloc[i] = True  # Reverse to bullish
---
>                 bull.iloc[i] = True
2504c2200
<                 bull.iloc[i] = prev_bull  # Continue previous trend
---
>                 bull.iloc[i] = prev_bull
2506d2201
<             # Update AF and EP
2510,2511c2205
<                 # Ensure PSAR does not cross price on reversal
<                 if bull.iloc[i]: # if reversing to bullish, PSAR should be below current low
---
>                 if bull.iloc[i]:
2513c2207
<                 else: # if reversing to bearish, PSAR should be above current high
---
>                 else:
2516c2210
<             elif bull.iloc[i]:  # Continuing bullish
---
>             elif bull.iloc[i]:
2520d2213
<                 # Keep PSAR below the lowest low of the last two bars
2522c2215
<             else:  # Continuing bearish
---
>             else:
2526d2218
<                 # Keep PSAR above the highest high of the last two bars
2530,2531c2222,2223
<         direction[psar < self.df["close"]] = 1  # Bullish
<         direction[psar > self.df["close"]] = -1  # Bearish
---
>         direction[psar < self.df["close"]] = 1
>         direction[psar > self.df["close"]] = -1
2537d2228
<         """Calculate Fibonacci retracement levels based on a recent high-low swing."""
2545d2235
<         # Use the last 'window' number of bars for calculation
2551c2241
<         if diff <= 0: # Handle cases where high and low are the same or inverted
---
>         if diff <= 0:
2557d2246
<         # Use Decimal for precision
2561d2249
<         # Define Fibonacci ratios
2563,2564c2251,2252
<             "0.0%": 0.0, "23.6%": 0.236, "38.2%": 0.382, "50.0%": 0.500,
<             "61.8%": 0.618, "78.6%": 0.786, "100.0%": 1.0
---
>             "0.0%": Decimal("0.0"), "23.6%": Decimal("0.236"), "38.2%": Decimal("0.382"), "50.0%": Decimal("0.500"),
>             "61.8%": Decimal("0.618"), "78.6%": Decimal("0.786"), "100.0%": Decimal("1.0")
2568d2255
<         # Define precision for quantization, e.g., 5 decimal places for crypto
2574c2261
<             level_price = recent_high_dec - (diff_dec * Decimal(str(ratio)))
---
>             level_price = recent_high_dec - (diff_dec * ratio)
2580d2266
<         """Calculate a simple Volatility Index based on ATR normalized by price."""
2585,2586d2270
<         # ATR is already calculated in _calculate_all_indicators
<         # Normalize ATR by closing price to get a relative measure of volatility
2588d2271
<         # Calculate a moving average of the normalized ATR
2593d2275
<         """Calculate Volume Weighted Moving Average (VWMA)."""
2597d2278
<         # Ensure volume is numeric and not zero for calculation
2599,2600c2280
<         pv = self.df["close"] * valid_volume # Price * Volume
<         # Sum of (Price * Volume) over the period
---
>         pv = self.df["close"] * valid_volume
2602d2281
<         # Sum of Volume over the period
2604c2283
<         vwma = sum_pv / sum_vol.replace(0, np.nan) # Handle division by zero
---
>         vwma = sum_pv / sum_vol.replace(0, np.nan)
2608d2286
<         """Calculate Volume Delta, indicating buying vs selling pressure."""
2612,2613d2289
<         # Approximate buy/sell volume based on close relative to open
<         # If close > open, it's considered buying pressure (bullish candle)
2615d2290
<         # If close < open, it's considered selling pressure (bearish candle)
2618d2292
<         # Rolling sum of buy/sell volume over the specified period
2623,2624d2296
<         # Calculate delta: (Buy Volume - Sell Volume) / Total Volume
<         # This gives a ratio indicating net buying or selling pressure
2631d2302
<         """Safely retrieve an indicator value from the stored dictionary."""
2635,2637d2305
<         """Analyze orderbook imbalance.
<         Returns imbalance score between -1 (all asks) and +1 (all bids).
<         """
2648d2315
<         # Imbalance: (Bid Volume - Ask Volume) / Total Volume
2656d2322
<         """Determine trend from higher timeframe using specified indicator."""
2660d2325
<         # Ensure we have enough data for the indicator's period
2695,2697d2359
<             # This is inefficient as it recalculates the indicator.
<             # A better approach would be to pass pre-calculated indicator values or a pre-instantiated analyzer.
<             # For now, keeping it as is but noting the inefficiency.
2701d2362
<             # Use the slow SuperTrend for MTF trend determination as per common practice
2704,2705c2365
<             # Ensure enough data for ST calculation
<             if len(higher_tf_df) < st_period * 3: # Heuristic for sufficient data
---
>             if len(higher_tf_df) < st_period * 3:
2723d2382
<         """Fetches data for higher timeframes and determines trends."""
2734,2735d2392
<             # Fetch enough data for the longest indicator period on MTF
<             # Fetching a larger number (e.g., 1000) is good practice
2749c2406
<             time.sleep(mtf_request_delay) # Delay between MTF requests
---
>             time.sleep(mtf_request_delay)
2752,2753d2408
<     # --- Signal Scoring Helper Methods ---
< 
2755d2409
<         """Scores EMA alignment."""
2774d2427
<         """Scores SMA trend filter."""
2792d2444
<         """Scores momentum indicators (RSI, StochRSI, CCI, WR, MFI)."""
2801d2452
<         # RSI
2805d2455
<                 # Normalize RSI to a -1 to +1 scale (50 is neutral)
2807c2457
<                 contrib = normalized_rsi * momentum_weight * 0.5 # Assign a portion of momentum weight
---
>                 contrib = normalized_rsi * momentum_weight * 0.5
2811d2460
<         # StochRSI Crossover
2819d2467
<                 # Bullish crossover from oversold
2823d2470
<                 # Bearish crossover from overbought
2827,2828c2474
<                 # General momentum based on K line position relative to D line and midpoint
<                 elif stoch_k > stoch_d and stoch_k < 50: # General bullish momentum
---
>                 elif stoch_k > stoch_d and stoch_k < 50:
2830c2476
<                 elif stoch_k < stoch_d and stoch_k > 50: # General bearish momentum
---
>                 elif stoch_k < stoch_d and stoch_k > 50:
2835d2480
<         # CCI
2839d2483
<                 # Normalize CCI (assuming typical range of -200 to 200, normalize to -1 to +1)
2849d2492
<         # Williams %R
2853d2495
<                 # Normalize WR to -1 to +1 scale (-100 to 0, so (WR + 50) / 50)
2863d2504
<         # MFI
2867d2507
<                 # Normalize MFI to -1 to +1 scale (0 to 100, so (MFI - 50) / 50)
2880d2519
<         """Scores Bollinger Bands."""
2890c2529
<             if current_close < bb_lower: # Price below lower band - potential buy signal
---
>             if current_close < bb_lower:
2892c2531
<             elif current_close > bb_upper: # Price above upper band - potential sell signal
---
>             elif current_close > bb_upper:
2899d2537
<         """Scores VWAP."""
2908d2545
<             # Basic score based on price relative to VWAP
2914d2550
<             # Add score for VWAP crossover if available
2917d2552
<                 # VWAP crossover
2929d2563
<         """Scores PSAR."""
2939,2940c2573
<             # PSAR direction is a primary signal
<             if psar_dir == 1: # Bullish PSAR
---
>             if psar_dir == 1:
2942c2575
<             elif psar_dir == -1: # Bearish PSAR
---
>             elif psar_dir == -1:
2945d2577
<             # PSAR crossover with price adds confirmation
2949c2581
<                     contrib += weight * 0.4 # Additional bullish weight on crossover
---
>                     contrib += weight * 0.4
2952c2584
<                     contrib -= weight * 0.4 # Additional bearish weight on crossover
---
>                     contrib -= weight * 0.4
2959d2590
<         """Scores orderbook imbalance."""
2963c2594
<         imbalance = self._check_orderbook(Decimal(0), orderbook_data) # Price not used in imbalance calculation here
---
>         imbalance = self._check_orderbook(Decimal(0), orderbook_data)
2973d2603
<         """Scores Fibonacci levels confluence."""
2982,2983d2611
<             # Check if price is near a Fibonacci level (within 0.1% of current price)
<             # Ensure current_close is not zero to avoid division by zero
2990d2617
<                     # Price crossing the level can act as support/resistance
2992c2619
<                         if (current_close > prev_close and current_close > level_price): # Bullish breakout above level
---
>                         if (current_close > prev_close and current_close > level_price):
2994c2621
<                         elif (current_close < prev_close and current_close < level_price): # Bearish breakdown below level
---
>                         elif (current_close < prev_close and current_close < level_price):
3001d2627
<         """Scores Ehlers SuperTrend alignment."""
3016d2641
<             # Strong buy signal: fast ST flips up and aligns with slow ST (which is also up)
3020d2644
<             # Strong sell signal: fast ST flips down and aligns with slow ST (which is also down)
3024d2647
<             # General alignment: both fast and slow ST are in the same direction
3034d2656
<         """Scores MACD alignment."""
3045d2666
<             # Bullish crossover: MACD line crosses above Signal line
3049d2669
<             # Bearish crossover: MACD line crosses below Signal line
3053d2672
<             # Histogram turning positive/negative from zero line
3063d2681
<         """Scores ADX strength."""
3071d2688
<         # Retrieve thresholds from indicator_settings for better configuration
3077d2693
<             # Strong trend confirmation
3079c2695
<                 if plus_di > minus_di: # Bullish trend
---
>                 if plus_di > minus_di:
3082c2698
<                 elif minus_di > plus_di: # Bearish trend
---
>                 elif minus_di > plus_di:
3086c2702
<                 contrib = 0 # Neutral signal, no contribution from ADX
---
>                 contrib = 0
3093d2708
<         """Scores Ichimoku Cloud confluence."""
3108d2722
<             # Tenkan-sen / Kijun-sen crossover
3110c2724
<                 contrib += weight * 0.5 # Bullish crossover
---
>                 contrib += weight * 0.5
3113c2727
<                 contrib -= weight * 0.5 # Bearish crossover
---
>                 contrib -= weight * 0.5
3116d2729
<             # Price breaking above/below Kumo (cloud)
3119d2731
<             # Get previous kumo values, handle potential NaNs if data is sparse
3124c2736
<                 contrib += weight * 0.7 # Strong bullish breakout
---
>                 contrib += weight * 0.7
3127c2739
<                 contrib -= weight * 0.7 # Strong bearish breakdown
---
>                 contrib -= weight * 0.7
3130d2741
<             # Chikou Span crossover with price
3132c2743
<                 contrib += weight * 0.3 # Bullish confirmation
---
>                 contrib += weight * 0.3
3135c2746
<                 contrib -= weight * 0.3 # Bearish confirmation
---
>                 contrib -= weight * 0.3
3142d2752
<         """Scores OBV momentum."""
3152d2761
<             # OBV crossing its EMA
3154c2763
<                 contrib = weight * 0.5 # Bullish crossover
---
>                 contrib = weight * 0.5
3157c2766
<                 contrib = -weight * 0.5 # Bearish crossover
---
>                 contrib = -weight * 0.5
3160d2768
<             # OBV trend confirmation (simplified: check if current OBV is higher/lower than previous two)
3163c2771
<                     contrib += weight * 0.2 # OBV making higher highs
---
>                     contrib += weight * 0.2
3165c2773
<                     contrib -= weight * 0.2 # OBV making lower lows
---
>                     contrib -= weight * 0.2
3171d2778
<         """Scores CMF flow."""
3180d2786
<             # CMF above/below zero line
3182c2788
<                 contrib = weight * 0.5 # Bullish money flow
---
>                 contrib = weight * 0.5
3184c2790
<                 contrib = -weight * 0.5 # Bearish money flow
---
>                 contrib = -weight * 0.5
3186d2791
<             # CMF trend confirmation (simplified: check if current CMF is higher/lower than previous two)
3189c2794
<                     contrib += weight * 0.3 # CMF making higher highs
---
>                     contrib += weight * 0.3
3191c2796
<                     contrib -= weight * 0.3 # CMF making lower lows
---
>                     contrib -= weight * 0.3
3197d2801
<         """Scores Volatility Index."""
3210,3212c2814,2815
<                 if vol_idx > prev_vol_idx > prev_prev_vol_idx:  # Increasing volatility
<                     # Increasing volatility can amplify existing signals
<                     if signal_score > 0: # If current score is bullish, amplify it
---
>                 if vol_idx > prev_vol_idx > prev_prev_vol_idx:
>                     if signal_score > 0:
3214c2817
<                     elif signal_score < 0: # If current score is bearish, amplify it
---
>                     elif signal_score < 0:
3217,3220c2820,2822
<                 elif vol_idx < prev_vol_idx < prev_prev_vol_idx: # Decreasing volatility
<                     # Decreasing volatility might reduce confidence in strong signals
<                     if abs(signal_score) > 0: # If there's an existing signal, slightly reduce its confidence
<                          contrib = signal_score * -0.2 # Reduce score by 20% (example)
---
>                 elif vol_idx < prev_vol_idx < prev_prev_vol_idx:
>                     if abs(signal_score) > 0:
>                          contrib = signal_score * -0.2
3227d2828
<         """Scores VWMA cross."""
3237d2837
<             # Price crossing VWMA
3239c2839
<                 contrib = weight # Bullish crossover
---
>                 contrib = weight
3242c2842
<                 contrib = -weight # Bearish crossover
---
>                 contrib = -weight
3249d2848
<         """Scores Volume Delta."""
3259c2858
<             if volume_delta > volume_delta_threshold:  # Strong buying pressure
---
>             if volume_delta > volume_delta_threshold:
3262c2861
<             elif volume_delta < -volume_delta_threshold:  # Strong selling pressure
---
>             elif volume_delta < -volume_delta_threshold:
3265d2863
<             # Weaker signals for moderate delta
3275d2872
<         """Scores Multi-Timeframe trend confluence."""
3292,3293d2888
<             # Calculate a normalized score based on the balance of buy/sell trends
<             # Max possible score is 1 (all UP), min is -1 (all DOWN)
3310,3312d2904
<         """Generate a signal using confluence of indicators, including Ehlers SuperTrend.
<         Returns the final signal, the aggregated signal score, and a breakdown of contributions.
<         """
3314c2906
<         signal_breakdown: dict[str, float] = {} # Initialize breakdown dictionary
---
>         signal_breakdown: dict[str, float] = {}
3323d2914
<         # Get previous close price, handle case with only one data point
3326d2916
<         # --- Apply Scoring for Each Indicator Group ---
3347d2936
<         # --- Final Signal Determination with Hysteresis and Cooldown ---
3358,3360d2946
<         # Apply hysteresis to prevent immediate flip-flops
<         # If the bot previously issued a BUY signal and the current score is not a strong SELL, and not a strong BUY, it holds the BUY signal.
<         # This prevents it from flipping to HOLD or SELL too quickly if the score dips slightly.
3363d2948
<         # If the bot previously issued a SELL signal and the current score is not a strong BUY, and not a strong SELL, it holds the SELL signal.
3371d2955
<         # Apply cooldown period
3377c2961
<                 self._last_signal_ts = now_ts # Update timestamp only if signal is issued
---
>                 self._last_signal_ts = now_ts
3379d2962
<         # Update last signal score for next iteration's hysteresis
3388c2971
<         self, current_price: Decimal, atr_value: Decimal, signal: Literal["BUY", "SELL"]
---
>         self, current_price: Decimal, atr_value: Decimal, signal: Literal["Buy", "Sell"]
3390d2972
<         """Calculate Take Profit and Stop Loss levels."""
3397d2978
<         # Ensure price precision is at least 1 (e.g., 0.1, 0.01, etc.)
3402c2983
<         if signal == "BUY":
---
>         if signal == "Buy":
3405c2986
<         elif signal == "SELL":
---
>         elif signal == "Sell":
3408c2989
<         else: # Should not happen for valid signals
---
>         else:
3423c3004
<     signal_breakdown: dict | None = None # New parameter for displaying breakdown
---
>     signal_breakdown: dict | None = None
3425d3005
<     """Display current price and calculated indicator values."""
3429,3430d3008
<     # Re-initialize TradingAnalyzer to get the latest indicator values for display
<     # This might be slightly redundant if called after signal generation, but ensures display is up-to-date.
3440d3017
<     # Sort indicators alphabetically for consistent display
3444d3020
<         # Format Decimal values for consistent display
3448c3024
<             logger.info(f"  {color}{indicator_name}: {value:.8f}{RESET}") # Use higher precision for floats
---
>             logger.info(f"  {color}{indicator_name}: {value:.8f}{RESET}")
3454,3455c3030
<         logger.info("")  # Added newline for spacing
<         # Sort Fibonacci levels by ratio for consistent display
---
>         logger.info("")
3462,3463c3037
<         logger.info("")  # Added newline for spacing
<         # Sort MTF trends by timeframe for consistent display
---
>         logger.info("")
3470d3043
<         # Sort by absolute contribution for better readability
3479d3051
< # --- Main Execution Logic ---
3481,3482d3052
<     """Orchestrate the bot's operation."""
<     # The logger is now initialized globally.
3486d3055
<     # These are standard Bybit intervals. It's good practice to keep them consistent.
3508c3077,3082
<     position_manager = PositionManager(config, logger, config["symbol"])
---
>     ws_manager = BybitWebSocketManager(config, logger)
>     ws_manager.start_public_stream()
>     ws_manager.start_private_stream()
>     ws_manager.wait_for_initial_data(timeout=45)
> 
>     position_manager = PositionManager(config, logger, config["symbol"], ws_manager)
3511,3512c3085,3086
<     while True:
<         try:
---
>     try:
>         while True:
3514c3088
<             current_price = fetch_current_price(config["symbol"], logger)
---
>             current_price = fetch_current_price(config["symbol"], logger, ws_manager)
3522,3524c3096
<             # Fetch primary klines. Fetching a larger number (e.g., 1000) is good practice
<             # to ensure indicators with long periods have enough data.
<             df = fetch_klines(config["symbol"], config["interval"], 1000, logger)
---
>             df = fetch_klines(config["symbol"], config["interval"], 1000, logger, ws_manager)
3536c3108
<                     config["symbol"], config["orderbook_limit"], logger
---
>                     config["symbol"], config["orderbook_limit"], logger, ws_manager
3539d3110
<             # Fetch MTF trends
3542,3543d3112
<                 # Create a temporary analyzer instance to call the MTF analysis method
<                 # This avoids re-calculating all indicators on the primary DF just for MTF analysis
3547,3552d3115
<             # Display current market data and indicators before signal generation
<             display_indicator_values_and_price(
<                 config, logger, current_price, df, orderbook_data, mtf_trends
<             )
< 
<             # Initialize TradingAnalyzer with the primary DataFrame for signal generation
3563d3125
<             # Generate trading signal
3568d3129
<             # Get ATR for position sizing and SL/TP calculation
3570c3131
<             if atr_value <= 0: # Ensure ATR is positive for calculations
---
>             if atr_value <= 0:
3572c3133
<                 self.logger.warning(f"{NEON_YELLOW}[{config['symbol']}] ATR value was zero or negative, defaulting to {atr_value}.{RESET}")
---
>                 logger.warning(f"{NEON_YELLOW}[{config['symbol']}] ATR value was zero or negative, defaulting to {atr_value}.{RESET}")
3574,3582d3134
< 
<             # Generate trading signal
<             trading_signal, signal_score, signal_breakdown = analyzer.generate_trading_signal(
<                 current_price, orderbook_data, mtf_trends
<             )
< 
<             # Manage open positions (sync with exchange, check/update TSL)
<             # This should happen *before* deciding to open a new position,
<             # as it updates the `self.open_positions` list
3585,3586d3136
< 
<             # Display current state after analysis and signal generation, including breakdown
3591d3140
<             # Execute trades based on strong signals
3593,3595d3141
<             # Important: Ensure `position_manager.get_open_positions()` is correctly reflecting
<             # current state, usually by calling `sync_positions_from_exchange()` right before.
<             # The `open_position` method also calls sync.
3597,3600c3143,3144
<             # Check if a position of the same side is already open before trying to open a new one
<             # This assumes a "one position per side" strategy
<             has_buy_position = any(p["side"] == "Buy" for p in position_manager.get_open_positions())
<             has_sell_position = any(p["side"] == "Sell" for p in position_manager.get_open_positions())
---
>             has_buy_position = any(p["side"].upper() == "BUY" for p in position_manager.get_open_positions())
>             has_sell_position = any(p["side"].upper() == "SELL" for p in position_manager.get_open_positions())
3606c3150
<                 and not has_buy_position # Prevent opening multiple BUY positions
---
>                 and not has_buy_position
3615c3159
<                 and not has_sell_position # Prevent opening multiple SELL positions
---
>                 and not has_sell_position
3626,3627c3170
<             # Log current open positions and performance summary
<             open_positions = position_manager.get_open_positions() # Get the *internally tracked* positions
---
>             open_positions = position_manager.get_open_positions()
3631d3173
<                     # Access dictionary elements directly instead of using .normalize() on Decimal which is already done during quantization
3648,3653c3190,3200
<         except Exception as e:
<             alert_system.send_alert(
<                 f"[{config['symbol']}] An unhandled error occurred in the main loop: {e}", "ERROR"
<             )
<             logger.exception(f"{NEON_RED}[{config['symbol']}] Unhandled exception in main loop:{RESET}")
<             time.sleep(config["loop_delay"] * 2) # Longer sleep after an error
---
>     except KeyboardInterrupt:
>         logger.info(f"{NEON_YELLOW}Bot stopping due to KeyboardInterrupt.{RESET}")
>     except Exception as e:
>         alert_system.send_alert(
>             f"[{config['symbol']}] An unhandled error occurred in the main loop: {e}", "ERROR"
>         )
>         logger.exception(f"{NEON_RED}[{config['symbol']}] Unhandled exception in main loop:{RESET}")
>         time.sleep(config["loop_delay"] * 2)
>     finally:
>         ws_manager.stop_all_streams()
>         logger.info(f"{NEON_GREEN}--- Whalebot Trading Bot Shut Down ---{RESET}")
3658d3204
< 
