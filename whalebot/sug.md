Here are 5 suggestions to enhance the provided Whalebot script, along with code snippets to implement them. These suggestions focus on improving real-time data handling, robustness, and performance, building upon the `BybitWebSocketManager` already present in your code.

---

### Suggestion 1: Fully Integrate Bybit WebSocket Manager for Real-time Data

**Problem:** The `BybitWebSocketManager` class is defined but not actively used in the `main` execution loop for fetching real-time data. The bot currently relies on REST API calls for `fetch_current_price`, `fetch_klines`, and `fetch_orderbook` in each loop iteration. This leads to higher latency, rate limit concerns, and misses out on the benefits of real-time streaming data.

**Solution:** Instantiate the `BybitWebSocketManager` at the start of the `main` function, initiate its public and private streams, and then pass this manager instance to the existing `fetch_...` functions. These functions are already designed to prioritize WebSocket data if a `ws_manager` is provided. This will ensure the bot uses the most up-to-date data with minimal latency.

**Code Snippet (Modifications in `main` function):**

```python
# Add this import at the top if not already present
# import threading
# import queue
# import websocket # You might need to install this: pip install websocket-client
# import ssl # For secure WebSocket connections
# from collections import deque # For storing recent kline data efficiently

# ... (rest of imports and global constants)

def main() -> None:
    """Orchestrate the bot's operation."""
    config = load_config(CONFIG_FILE, logger)
    alert_system = AlertSystem(logger)

    # --- NEW: Initialize WebSocket Manager ---
    ws_manager = BybitWebSocketManager(config, logger)
    ws_manager.start_public_stream()
    ws_manager.start_private_stream()
    ws_manager.wait_for_initial_data() # Wait for initial data to populate

    # These are standard Bybit intervals. It's good practice to keep them consistent.
    valid_bybit_intervals = [
        "1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D", "W", "M"
    ]

    if config["interval"] not in valid_bybit_intervals:
        logger.error(
            f"{NEON_RED}Invalid primary interval '{config['interval']}' in config.json. Please use Bybit's valid string formats (e.g., '15', '60', 'D'). Exiting.{RESET}"
        )
        # --- NEW: Stop WS streams before exiting ---
        ws_manager.stop_all_streams()
        sys.exit(1)

    for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
        if htf_interval not in valid_bybit_intervals:
            logger.error(
                f"{NEON_RED}Invalid higher timeframe interval '{htf_interval}' in config.json. Please use Bybit's valid string formats (e.g., '60', '240'). Exiting.{RESET}"
            )
            # --- NEW: Stop WS streams before exiting ---
            ws_manager.stop_all_streams()
            sys.exit(1)

    logger.info(f"{NEON_GREEN}--- Whalebot Trading Bot Initialized ---{RESET}")
    logger.info(f"Symbol: {config['symbol']}, Interval: {config['interval']}")
    logger.info(f"Trade Management Enabled: {config['trade_management']['enabled']}")

    # --- NEW: Pass ws_manager to PositionManager ---
    position_manager = PositionManager(config, logger, config["symbol"], ws_manager)
    performance_tracker = PerformanceTracker(logger)

    try: # --- NEW: Add try-finally block for graceful shutdown ---
        while True:
            try:
                logger.info(f"{NEON_PURPLE}--- New Analysis Loop Started ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}) ---{RESET}")
                
                # --- MODIFIED: Pass ws_manager to fetch functions ---
                current_price = fetch_current_price(config["symbol"], logger, ws_manager=ws_manager)
                if current_price is None:
                    alert_system.send_alert(
                        f"[{config['symbol']}] Failed to fetch current price. Skipping loop.", "WARNING"
                    )
                    time.sleep(config["loop_delay"])
                    continue

                # Fetch primary klines.
                # --- MODIFIED: Pass ws_manager to fetch klines ---
                df = fetch_klines(config["symbol"], config["interval"], 1000, logger, ws_manager=ws_manager)
                if df is None or df.empty:
                    alert_system.send_alert(
                        f"[{config['symbol']}] Failed to fetch primary klines or DataFrame is empty. Skipping loop.",
                        "WARNING",
                    )
                    time.sleep(config["loop_delay"])
                    continue

                orderbook_data = None
                if config["indicators"].get("orderbook_imbalance", False):
                    # --- MODIFIED: Pass ws_manager to fetch orderbook ---
                    orderbook_data = fetch_orderbook(
                        config["symbol"], config["orderbook_limit"], logger, ws_manager=ws_manager
                    )

                # Fetch MTF trends (temp_analyzer_for_mtf also needs ws_manager if it calls fetch_klines internally)
                mtf_trends: dict[str, str] = {}
                if config["mtf_analysis"]["enabled"]:
                    # Create a temporary analyzer instance to call the MTF analysis method
                    temp_analyzer_for_mtf = TradingAnalyzer(df, config, logger, config["symbol"], ws_manager=ws_manager)
                    mtf_trends = temp_analyzer_for_mtf._fetch_and_analyze_mtf()

                # Display current market data and indicators before signal generation
                display_indicator_values_and_price(
                    config, logger, current_price, df, orderbook_data, mtf_trends
                )

                # Initialize TradingAnalyzer with the primary DataFrame for signal generation
                analyzer = TradingAnalyzer(df, config, logger, config["symbol"], ws_manager=ws_manager) # Pass ws_manager here too

                if analyzer.df.empty:
                    alert_system.send_alert(
                        f"[{config['symbol']}] TradingAnalyzer DataFrame is empty after indicator calculations. Cannot generate signal.",
                        "WARNING",
                    )
                    time.sleep(config["loop_delay"])
                    continue

                # Get ATR for position sizing and SL/TP calculation
                atr_value = Decimal(str(analyzer._get_indicator_value("ATR", Decimal("0.0001"))))
                if atr_value <= 0: # Ensure ATR is positive for calculations
                    atr_value = Decimal("0.0001")
                    logger.warning(f"{NEON_YELLOW}[{config['symbol']}] ATR value was zero or negative, defaulting to {atr_value}.{RESET}")

                # Generate trading signal
                trading_signal, signal_score, signal_breakdown = analyzer.generate_trading_signal(
                    current_price, orderbook_data, mtf_trends
                )

                # Manage open positions (sync with exchange, check/update TSL)
                position_manager.manage_positions(current_price, performance_tracker, atr_value)

                # Display current state after analysis and signal generation, including breakdown
                display_indicator_values_and_price(
                    config, logger, current_price, df, orderbook_data, mtf_trends, signal_breakdown
                )

                # Execute trades based on strong signals
                signal_threshold = config["signal_score_threshold"]
                
                has_buy_position = any(p["side"] == "Buy" for p in position_manager.get_open_positions())
                has_sell_position = any(p["side"] == "Sell" for p in position_manager.get_open_positions())


                if (
                    trading_signal == "BUY"
                    and signal_score >= signal_threshold
                    and not has_buy_position # Prevent opening multiple BUY positions
                ):
                    logger.info(
                        f"{NEON_GREEN}[{config['symbol']}] Strong BUY signal detected! Score: {signal_score:.2f}{RESET}"
                    )
                    position_manager.open_position("Buy", current_price, atr_value)
                elif (
                    trading_signal == "SELL"
                    and signal_score <= -signal_threshold
                    and not has_sell_position # Prevent opening multiple SELL positions
                ):
                    logger.info(
                        f"{NEON_RED}[{config['symbol']}] Strong SELL signal detected! Score: {signal_score:.2f}{RESET}"
                    )
                    position_manager.open_position("Sell", current_price, atr_value)
                else:
                    logger.info(
                        f"{NEON_BLUE}[{config['symbol']}] No strong trading signal. Holding. Score: {signal_score:.2f}{RESET}"
                    )

                # Log current open positions and performance summary
                open_positions = position_manager.get_open_positions()
                if open_positions:
                    logger.info(f"{NEON_CYAN}[{config['symbol']}] Open Positions: {len(open_positions)}{RESET}")
                    for pos in open_positions:
                        logger.info(
                            f"  - {pos['side']} @ {pos['entry_price'].normalize()} (SL: {pos['stop_loss'].normalize()}, TP: {pos['take_profit'].normalize()}, TSL Active: {pos['trailing_stop_activated'] if pos.get('trailing_stop_activated') else False}){RESET}"
                        )
                else:
                    logger.info(f"{NEON_CYAN}[{config['symbol']}] No open positions.{RESET}")

                perf_summary = performance_tracker.get_summary()
                logger.info(
                    f"{NEON_YELLOW}[{config['symbol']}] Performance Summary: Total PnL: {perf_summary['total_pnl'].normalize():.2f}, Wins: {perf_summary['wins']}, Losses: {perf_summary['losses']}, Win Rate: {perf_summary['win_rate']}{RESET}"
                )

                logger.info(
                    f"{NEON_PURPLE}--- Analysis Loop Finished. Waiting {config['loop_delay']}s ---{RESET}"
                )
                time.sleep(config["loop_delay"])

            except Exception as e:
                alert_system.send_alert(
                    f"[{config['symbol']}] An unhandled error occurred in the main loop: {e}", "ERROR"
                )
                logger.exception(f"{NEON_RED}[{config['symbol']}] Unhandled exception in main loop:{RESET}")
                time.sleep(config["loop_delay"] * 2) # Longer sleep after an error
    finally: # --- NEW: Ensure WebSocket streams are stopped on exit ---
        ws_manager.stop_all_streams()
        logger.info(f"{NEON_BLUE}Whalebot has shut down.{RESET}")
```

---

### Suggestion 2: Enhance PositionManager with Private WebSocket Updates

**Problem:** The `PositionManager` currently relies on periodic REST API calls (`get_open_positions_from_exchange`) to sync its internal state with the exchange. This polling approach can introduce latency in recognizing position closures (e.g., due to stop-loss or take-profit hits) or new position entries, impacting the accuracy of trailing stop calculations and overall responsiveness.

**Solution:** Leverage the `BybitWebSocketManager`'s private stream `private_updates_queue` to receive real-time updates for orders, positions, and wallet. The `PositionManager` can then process these events to maintain a near real-time and more accurate view of open positions. The REST polling can be kept as an initial sync or a periodic fallback for reconciliation.

**Code Snippet (Modifications in `PositionManager`):**

```python
# Modify PositionManager.__init__ and manage_positions

class PositionManager:
    """Manages open positions, stop-loss, and take-profit levels."""

    def __init__(self, config: dict[str, Any], logger: logging.Logger, symbol: str, ws_manager: 'BybitWebSocketManager' | None = None):
        """Initializes the PositionManager."""
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.ws_manager = ws_manager # Store WS manager instance
        # ... (rest of existing __init__ code)

        # Initial sync of open positions from exchange (can still be useful for initial state)
        self.sync_positions_from_exchange()

    def _process_ws_private_updates(self, performance_tracker: Any):
        """Processes private WebSocket updates (orders, positions, wallet) to update internal state."""
        updates = self.ws_manager.get_private_updates() if self.ws_manager else []
        for update_data in updates:
            topic = update_data.get("topic")
            data_list = update_data.get("data", [])

            for item in data_list:
                if topic == "position":
                    self.logger.debug(f"{NEON_BLUE}[WS Position Update] {item}{RESET}")
                    self._update_position_from_ws(item, performance_tracker)
                elif topic == "order":
                    # You can add more detailed order tracking here if needed
                    # For now, position updates are more critical for `PositionManager`
                    self.logger.debug(f"{NEON_BLUE}[WS Order Update] {item}{RESET}")
                elif topic == "wallet":
                    self.logger.debug(f"{NEON_BLUE}[WS Wallet Update] {item}{RESET}")
                    # Update internal balance if tracking
                else:
                    self.logger.debug(f"{NEON_BLUE}[WS Private] Unhandled topic: {topic} - {item}{RESET}")

    def _update_position_from_ws(self, ws_position_data: dict, performance_tracker: Any):
        """Updates internal open_positions based on a single WebSocket position update."""
        side = ws_position_data.get("side")
        qty = Decimal(ws_position_data.get("size", "0"))
        entry_price = Decimal(ws_position_data.get("avgPrice", "0"))
        # Bybit's WS uses 'stopLoss' directly, which is the price
        stop_loss_price = Decimal(ws_position_data.get("stopLoss", "0")) if ws_position_data.get("stopLoss") else Decimal("0")
        take_profit_price = Decimal(ws_position_data.get("takeProfit", "0")) if ws_position_data.get("takeProfit") else Decimal("0")
        trailing_stop_activation_price = Decimal(ws_position_data.get("trailingStop", "0")) if ws_position_data.get("trailingStop") else Decimal("0")

        # Identify unique key for the position (assuming 'positionIdx' and 'side' are sufficient for one-way mode)
        position_id_key = ws_position_data.get("positionIdx") # Typically 0 for one-way mode
        
        # Ensure Decimal values are normalized for consistent comparison/storage
        qty_norm = qty.quantize(self.qty_quantize_dec, rounding=ROUND_DOWN)
        entry_price_norm = entry_price.quantize(self.price_quantize_dec, rounding=ROUND_DOWN)
        stop_loss_norm = stop_loss_price.quantize(self.price_quantize_dec, rounding=ROUND_DOWN)
        take_profit_norm = take_profit_price.quantize(self.price_quantize_dec, rounding=ROUND_DOWN)
        trailing_stop_activation_price_norm = trailing_stop_activation_price.quantize(self.price_quantize_dec, rounding=ROUND_DOWN)

        existing_pos = next(
            (p for p in self.open_positions if p["positionIdx"] == position_id_key and p["side"] == side),
            None,
        )

        if qty_norm > 0: # Position is open or updated
            if existing_pos:
                # Update existing position
                existing_pos.update({
                    "entry_price": entry_price_norm,
                    "qty": qty_norm,
                    "stop_loss": stop_loss_norm,
                    "take_profit": take_profit_norm,
                    "trailing_stop_activated": trailing_stop_activation_price_norm > 0 if self.enable_trailing_stop else False,
                    "trailing_stop_price": trailing_stop_activation_price_norm if trailing_stop_activation_price_norm > 0 else None
                })
                self.logger.debug(f"{NEON_BLUE}[{self.symbol}] Position updated from WS: {side} {qty_norm} @ {entry_price_norm}{RESET}")
            else:
                # New position opened on exchange (e.g., from manual trade or a different bot)
                self.logger.warning(f"{NEON_YELLOW}[{self.symbol}] New position detected via WS: {side} {qty_norm} @ {entry_price_norm}. Adding to tracking.{RESET}")
                self.open_positions.append({
                    "positionIdx": position_id_key,
                    "symbol": self.symbol,
                    "side": side,
                    "entry_price": entry_price_norm,
                    "qty": qty_norm,
                    "stop_loss": stop_loss_norm,
                    "take_profit": take_profit_norm,
                    "position_id": position_id_key, # Using positionIdx as ID for one-way mode
                    "order_id": "UNKNOWN_WS", # WS update doesn't usually provide initial order ID
                    "entry_time": datetime.now(TIMEZONE), # Estimate
                    "initial_stop_loss": stop_loss_norm, # Assume this is initial if not tracked
                    "trailing_stop_activated": trailing_stop_activation_price_norm > 0 if self.enable_trailing_stop else False,
                    "trailing_stop_price": trailing_stop_activation_price_norm if trailing_stop_activation_price_norm > 0 else None
                })
        elif qty_norm == 0 and existing_pos:
            # Position closed
            self.open_positions.remove(existing_pos)
            self.logger.info(f"{NEON_GREEN}[{self.symbol}] Position {side} (ID: {position_id_key}) closed via WS. Recording trade.{RESET}")
            
            # Record trade (need to get exit price which might not be directly in 'position' update for closure)
            # A more robust system would get the final PnL from a 'order' topic update for the closing order.
            # For simplicity here, we assume the entry price and zero size implies a closure.
            # You'd typically need to fetch historical orders or rely on an 'order' webhook that specifies `execType = Trade`.
            # For now, this is a placeholder to record the closure.
            close_price = self.ws_manager.get_latest_ticker().get("lastPrice", existing_pos["entry_price"])
            pnl = (
                (close_price - existing_pos["entry_price"]) * existing_pos["qty"]
                if existing_pos["side"] == "Buy"
                else (existing_pos["entry_price"] - close_price) * existing_pos["qty"]
            )
            performance_tracker.record_trade(
                {**existing_pos, "exit_price": close_price, "exit_time": datetime.now(TIMEZONE), "closed_by": "EXCHANGE_WS_UPDATE"},
                pnl
            )


    def sync_positions_from_exchange(self):
        """Fetches current open positions from the exchange and updates the internal list."""
        # This can still be called periodically or as a fallback/initial sync
        # The _process_ws_private_updates provides real-time updates.
        exchange_positions = get_open_positions_from_exchange(self.symbol, self.logger)
        
        # Convert to a dictionary for easier lookup by a unique identifier
        exchange_positions_map = {}
        for ex_pos in exchange_positions:
            position_id_key = ex_pos["positionIdx"] # Assuming one-way mode, positionIdx is 0
            side = ex_pos["side"]
            exchange_positions_map[f"{position_id_key}_{side}"] = ex_pos

        new_tracked_positions = []
        for tracked_pos in self.open_positions:
            key = f"{tracked_pos['positionIdx']}_{tracked_pos['side']}"
            if key in exchange_positions_map:
                # Position still exists on exchange, update its details
                ex_pos = exchange_positions_map.pop(key) # Remove from map once processed
                
                # Update existing_pos with latest details from exchange REST API
                tracked_pos.update({
                    "entry_price": Decimal(ex_pos["avgPrice"]).quantize(self.price_quantize_dec),
                    "qty": Decimal(ex_pos["size"]).quantize(self.qty_quantize_dec),
                    "stop_loss": Decimal(ex_pos.get("stopLoss", "0")).quantize(self.price_quantize_dec),
                    "take_profit": Decimal(ex_pos.get("takeProfit", "0")).quantize(self.price_quantize_dec),
                    "trailing_stop_activated": Decimal(ex_pos.get("trailingStop", "0")) > 0 if self.enable_trailing_stop else False,
                    "trailing_stop_price": Decimal(ex_pos.get("trailingStop", "0")).quantize(self.price_quantize_dec) if Decimal(ex_pos.get("trailingStop", "0")) > 0 else None,
                })
                new_tracked_positions.append(tracked_pos)
            else:
                # Position no longer on exchange, means it was closed. Record it if not already.
                self.logger.info(f"{NEON_BLUE}[{self.symbol}] Position {tracked_pos['side']} (ID: {tracked_pos.get('position_id', 'N/A')}) no longer open on exchange (REST sync). Marking as closed.{RESET}")
                # Record this closure. The _process_ws_private_updates should ideally catch this first.
                # This block would act as a fallback.
                close_price = self.ws_manager.get_latest_ticker().get("lastPrice", tracked_pos["entry_price"]) if self.ws_manager else tracked_pos["entry_price"]
                pnl = (
                    (close_price - tracked_pos["entry_price"]) * tracked_pos["qty"]
                    if tracked_pos["side"] == "Buy"
                    else (tracked_pos["entry_price"] - close_price) * tracked_pos["qty"]
                )
                performance_tracker.record_trade(
                    {**tracked_pos, "exit_price": close_price.quantize(self.price_quantize_dec), "exit_time": datetime.now(timezone.utc), "closed_by": "REST_SYNC_CLOSE_FALLBACK"},
                    pnl
                )

        # Any remaining items in exchange_positions_map are new positions detected on exchange
        for key, ex_pos in exchange_positions_map.items():
            side = ex_pos["side"]
            qty = Decimal(ex_pos["size"])
            entry_price = Decimal(ex_pos["avgPrice"])
            self.logger.warning(f"{NEON_YELLOW}[{self.symbol}] Detected new untracked position on exchange via REST sync. Side: {side}, Qty: {qty}, Entry: {entry_price}. Adding to internal tracking.{RESET}")
            new_tracked_positions.append({
                "positionIdx": ex_pos["positionIdx"],
                "symbol": self.symbol,
                "side": side,
                "entry_price": entry_price.quantize(self.price_quantize_dec),
                "qty": qty.quantize(self.qty_quantize_dec),
                "stop_loss": Decimal(ex_pos.get("stopLoss", "0")).quantize(self.price_quantize_dec),
                "take_profit": Decimal(ex_pos.get("takeProfit", "0")).quantize(self.price_quantize_dec),
                "position_id": ex_pos.get("positionId", str(ex_pos["positionIdx"])),
                "order_id": "UNKNOWN",
                "entry_time": datetime.now(TIMEZONE),
                "initial_stop_loss": Decimal(ex_pos.get("stopLoss", "0")).quantize(self.price_quantize_dec),
                "trailing_stop_activated": Decimal(ex_pos.get("trailingStop", "0")) > 0 if self.enable_trailing_stop else False,
                "trailing_stop_price": Decimal(ex_pos.get("trailingStop", "0")).quantize(self.price_quantize_dec) if Decimal(ex_pos.get("trailingStop", "0")) > 0 else None,
            })
        
        self.open_positions = new_tracked_positions
        if not self.open_positions:
            self.logger.debug(f"[{self.symbol}] No active positions being tracked internally after REST sync.")

    def manage_positions(
        self, current_price: Decimal, performance_tracker: Any, atr_value: Decimal
    ) -> None:
        """
        Processes WS private updates, then optionally syncs open positions from the exchange,
        and applies trailing stop logic. Records closed positions based on exchange updates.
        """
        if not self.trade_management_enabled:
            return

        # 1. NEW: Process real-time updates from WebSocket private stream first
        if self.ws_manager:
            self._process_ws_private_updates(performance_tracker)
        else:
            self.logger.warning(f"{NEON_YELLOW}[{self.symbol}] WebSocket Manager not provided to PositionManager. Relying solely on REST sync.{RESET}")

        # 2. Reconcile with REST API periodically (or if no WS manager)
        # This acts as a fallback or to catch anything missed by WS, but should not be the primary source for real-time changes
        # For demonstration, we'll keep it for now. In a production system, you might reduce its frequency.
        self.sync_positions_from_exchange()


        # Create a copy to iterate, allowing modification of original list if positions are closed.
        # Note: _process_ws_private_updates and sync_positions_from_exchange will modify self.open_positions directly.
        # This loop should now iterate over the *current* self.open_positions after updates.
        
        # Iterate through the internally tracked positions to apply trailing stop logic
        for position in list(self.open_positions): # Iterate on a copy to avoid modification issues
            # We assume `position` object is up-to-date from WS or REST sync
            side = position["side"]
            entry_price = position["entry_price"]
            current_stop_loss_on_exchange = position["stop_loss"] # This is what Bybit has for SL
            
            # --- Trailing Stop Loss Logic ---
            if self.enable_trailing_stop and atr_value > 0:
                profit_trigger_level = entry_price + (atr_value * self.break_even_atr_trigger) if side == "Buy" \
                                       else entry_price - (atr_value * self.break_even_atr_trigger)

                # Check if price has moved sufficiently into profit to activate/adjust TSL
                if (side == "Buy" and current_price >= profit_trigger_level) or \
                   (side == "Sell" and current_price <= profit_trigger_level):
                    
                    position["trailing_stop_activated"] = True
                    
                    # Calculate new potential trailing stop based on current price and ATR multiple
                    new_trailing_stop_candidate = (current_price - (atr_value * self.trailing_stop_atr_multiple)).quantize(self.price_quantize_dec, rounding=ROUND_DOWN) if side == "Buy" \
                                                else (current_price + (atr_value * self.trailing_stop_atr_multiple)).quantize(self.price_quantize_dec, rounding=ROUND_DOWN)
                    
                    # Ensure TSL does not move against the position or below initial stop loss (for BUY) / above initial stop loss (for SELL)
                    # For BUY: new_tsl > current_sl_on_exchange AND new_tsl > initial_sl (if not already passed initial_sl)
                    # For SELL: new_tsl < current_sl_on_exchange AND new_tsl < initial_sl (if not already passed initial_sl)
                    
                    should_update_sl = False
                    updated_sl_value = current_stop_loss_on_exchange

                    if side == "Buy":
                        # Move SL up, but not below its initial entry value
                        if new_trailing_stop_candidate > current_stop_loss_on_exchange:
                             updated_sl_value = max(new_trailing_stop_candidate, position["initial_stop_loss"]).quantize(self.price_quantize_dec)
                             if updated_sl_value > current_stop_loss_on_exchange: # Only update if it actually moves further into profit
                                should_update_sl = True

                    elif side == "Sell":
                        # Move SL down, but not above its initial entry value
                        if new_trailing_stop_candidate < current_stop_loss_on_exchange:
                             updated_sl_value = min(new_trailing_stop_candidate, position["initial_stop_loss"]).quantize(self.price_quantize_dec)
                             if updated_sl_value < current_stop_loss_on_exchange: # Only update if it actually moves further into profit
                                should_update_sl = True

                    if should_update_sl:
                        # Call Bybit API to update the stop loss
                        tpsl_update_result = set_position_tpsl(
                            self.symbol,
                            take_profit=position["take_profit"], # Keep TP the same
                            stop_loss=updated_sl_value,
                            logger=self.logger,
                            position_idx=position["positionIdx"]
                        )
                        if tpsl_update_result:
                            # Update internal tracking immediately after successful API call
                            position["stop_loss"] = updated_sl_value
                            position["trailing_stop_price"] = updated_sl_value # Store the TSL value
                            self.logger.info(
                                f"{NEON_GREEN}[{self.symbol}] TSL Updated for {side} position (ID: {position['position_id']}): Entry: {entry_price.normalize()}, Current Price: {current_price.normalize()}, New SL: {updated_sl_value.normalize()}{RESET}"
                            )
                        else:
                            self.logger.error(f"{NEON_RED}[{self.symbol}] Failed to update TSL for {side} position (ID: {position['position_id']}).{RESET}")
            
```

---

### Suggestion 3: Robust Error Handling for Multi-Timeframe Data Fetching

**Problem:** The `TradingAnalyzer._fetch_and_analyze_mtf` method relies on `fetch_klines` which can return `None` or an empty DataFrame. The current implementation only logs a warning and continues. If subsequent logic in `_get_mtf_trend` or `generate_trading_signal` blindly assumes MTF data, it might lead to further errors or unreliable signals. Moreover, repeated REST calls for MTF can be rate-limited.

**Solution:** Improve error handling in `_fetch_and_analyze_mtf` by ensuring `fetch_klines` is passed the `ws_manager` for efficiency. Then, if MTF data is unavailable or insufficient, explicitly return 'UNKNOWN' for the trend or skip the specific indicator, and provide clear logging. The `TradingAnalyzer` itself should be initialized with the `ws_manager` so its internal `_fetch_and_analyze_mtf` can use it.

**Code Snippet (Modifications in `TradingAnalyzer`):**

```python
# Modify TradingAnalyzer.__init__ and _fetch_and_analyze_mtf

class TradingAnalyzer:
    """Analyzes trading data and generates signals with MTF, Ehlers SuperTrend, and other new indicators."""

    def __init__(
        self,
        df: pd.DataFrame,
        config: dict[str, Any],
        logger: logging.Logger,
        symbol: str,
        ws_manager: 'BybitWebSocketManager' | None = None # NEW: Accept ws_manager
    ):
        """Initializes the TradingAnalyzer."""
        self.df = df.copy()
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.ws_manager = ws_manager # NEW: Store ws_manager
        self.indicator_values: dict[str, float | str | Decimal] = {}
        self.fib_levels: dict[str, Decimal] = {}
        self.weights = config.get("active_weights", {})
        self.indicator_settings = config["indicator_settings"]
        self._last_signal_ts = 0
        self._last_signal_score = 0.0

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] TradingAnalyzer initialized with an empty DataFrame. Indicators will not be calculated.{RESET}"
            )
            return

        self._calculate_all_indicators()
        if self.config["indicators"].get("fibonacci_levels", False):
            self.calculate_fibonacci_levels()


    def _fetch_and_analyze_mtf(self) -> dict[str, str]:
        """Fetches data for higher timeframes and determines trends."""
        mtf_trends: dict[str, str] = {}
        if not self.config["mtf_analysis"]["enabled"]:
            return mtf_trends

        higher_timeframes = self.config["mtf_analysis"]["higher_timeframes"]
        trend_indicators = self.config["mtf_analysis"]["trend_indicators"]
        mtf_request_delay = self.config["mtf_analysis"]["mtf_request_delay_seconds"]

        for htf_interval in higher_timeframes:
            self.logger.debug(f"[{self.symbol}] Fetching klines for MTF interval: {htf_interval}")
            
            # --- MODIFIED: Pass ws_manager to fetch_klines for MTF ---
            # Use the same limit as primary klines or slightly higher if long MTF periods are used.
            htf_df = fetch_klines(self.symbol, htf_interval, 1000, self.logger, ws_manager=self.ws_manager)

            if htf_df is not None and not htf_df.empty:
                # Ensure the MTF DataFrame is sorted by time
                htf_df.sort_index(inplace=True)

                for trend_ind in trend_indicators:
                    # To calculate MTF indicators, we need a *temporary* analyzer with the MTF dataframe.
                    # This analyzer should also have access to the main config and logger.
                    # Don't pass the ws_manager to this temporary analyzer, as it's already getting data.
                    temp_mtf_analyzer = TradingAnalyzer(htf_df.copy(), self.config, self.logger, self.symbol) 
                    
                    # Ensure ATR is calculated first if needed by SuperTrend for MTF
                    if trend_ind == "ehlers_supertrend":
                        # Recalculate indicators necessary for Ehlers SuperTrend on the MTF DF
                        # ATR is a prerequisite for Ehlers SuperTrend, ensure it's calculated
                        # If ATR calculation failed, _calculate_all_indicators would mark it as None/NaN.
                        temp_mtf_analyzer._calculate_all_indicators() # This will ensure TR/ATR for this temp df
                        
                        # Now, check if ATR is actually available for this MTF DF
                        if pd.isna(temp_mtf_analyzer._get_indicator_value("ATR", np.nan)):
                            self.logger.warning(
                                f"{NEON_YELLOW}[{self.symbol}] MTF Ehlers SuperTrend ({htf_interval}): ATR not available after recalculation. Skipping.{RESET}"
                            )
                            mtf_trends[f"{htf_interval}_{trend_ind}"] = "UNKNOWN"
                            continue
                            
                    trend = self._get_mtf_trend(temp_mtf_analyzer.df, trend_ind) # Pass the processed DF
                    mtf_trends[f"{htf_interval}_{trend_ind}"] = trend
                    self.logger.debug(
                        f"[{self.symbol}] MTF Trend ({htf_interval}, {trend_ind}): {trend}"
                    )
            else:
                self.logger.warning(
                    f"{NEON_YELLOW}[{self.symbol}] Could not fetch klines for higher timeframe {htf_interval} or it was empty. Skipping MTF trend for this TF.{RESET}"
                )
            time.sleep(mtf_request_delay) # Delay between MTF requests
        return mtf_trends

    # Modify _get_mtf_trend to accept a DataFrame and the indicator type
    def _get_mtf_trend(self, df_mtf: pd.DataFrame, indicator_type: str) -> str:
        """Determine trend from higher timeframe using specified indicator."""
        if df_mtf.empty:
            return "UNKNOWN"

        # Ensure we have enough data for the indicator's period
        period = self.config["mtf_analysis"]["trend_period"]
        if len(df_mtf) < period:
            self.logger.debug(
                f"[{self.symbol}] MTF Trend ({indicator_type}): Not enough data. Need {period}, have {len(df_mtf)}."
            )
            return "UNKNOWN"

        last_close = Decimal(str(df_mtf["close"].iloc[-1]))

        if indicator_type == "sma":
            sma = (
                df_mtf["close"]
                .rolling(window=period, min_periods=period)
                .mean()
                .iloc[-1]
            )
            if pd.isna(sma): return "UNKNOWN"
            if last_close > sma:
                return "UP"
            if last_close < sma:
                return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ema":
            ema = (
                df_mtf["close"]
                .ewm(span=period, adjust=False, min_periods=period)
                .mean()
                .iloc[-1]
            )
            if pd.isna(ema): return "UNKNOWN"
            if last_close > ema:
                return "UP"
            if last_close < ema:
                return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ehlers_supertrend":
            # Pass the MTF dataframe to the SuperTrend calculation
            st_period = self.indicator_settings["ehlers_slow_period"]
            st_multiplier = self.indicator_settings["ehlers_slow_multiplier"]
            
            # Use a temporary TradingAnalyzer just to calculate Ehlers SuperTrend for this MTF
            # This is already handled by `_fetch_and_analyze_mtf` by creating `temp_mtf_analyzer`
            # We just need to ensure `temp_mtf_analyzer.df` has "TR" and "ATR" calculated.
            
            # The `_calculate_all_indicators` on `temp_mtf_analyzer` (done in _fetch_and_analyze_mtf)
            # would have populated st_slow_dir on `temp_mtf_analyzer.df`.
            
            # Retrieve the ST direction from the temporary analyzer's dataframe
            if "st_slow_dir" not in df_mtf.columns or df_mtf["st_slow_dir"].empty:
                 self.logger.debug(f"[{self.symbol}] MTF Ehlers SuperTrend ({self.config['interval']}): 'st_slow_dir' not found or empty.")
                 return "UNKNOWN"

            st_dir = df_mtf["st_slow_dir"].iloc[-1]
            if st_dir == 1:
                return "UP"
            if st_dir == -1:
                return "DOWN"
            return "UNKNOWN" # Or SIDEWAYS if 0
        return "UNKNOWN"
```

---

### Suggestion 4: Implement Volume Confirmation for Trading Signals

**Problem:** The configuration includes `volume_confirmation_multiplier`, but this feature is not actively used in the `generate_trading_signal` method. Volume confirmation can add robustness to signals by ensuring that price movements are backed by significant market participation, reducing false signals.

**Solution:** Integrate a volume confirmation step into `generate_trading_signal`. This check will ensure that a potential BUY or SELL signal is only strengthened (or allowed) if the recent volume (or `Volume_Delta` indicator, if enabled) confirms the price direction, using the configured multiplier as a threshold.

**Code Snippet (Modification in `TradingAnalyzer.generate_trading_signal`):**

```python
# Modify TradingAnalyzer.generate_trading_signal

class TradingAnalyzer:
    # ... (rest of class)

    def generate_trading_signal(
        self,
        current_price: Decimal,
        orderbook_data: dict | None,
        mtf_trends: dict[str, str],
    ) -> tuple[str, float, dict]:
        """Generate a signal using confluence of indicators, including Ehlers SuperTrend.
        Returns the final signal, the aggregated signal score, and a breakdown of contributions.
        """
        signal_score = 0.0
        signal_breakdown: dict[str, float] = {}

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}"
            )
            return "HOLD", 0.0, {}

        current_close = Decimal(str(self.df["close"].iloc[-1]))
        prev_close = Decimal(str(self.df["close"].iloc[-2])) if len(self.df) > 1 else current_close

        # --- Apply Scoring for Each Indicator Group ---
        signal_score, signal_breakdown = self._score_ema_alignment(signal_score, signal_breakdown)
        signal_score, signal_breakdown = self._score_sma_trend_filter(signal_score, signal_breakdown, current_close)
        signal_score, signal_breakdown = self._score_momentum(signal_score, signal_breakdown, current_close, prev_close)
        signal_score, signal_breakdown = self._score_bollinger_bands(signal_score, signal_breakdown, current_close)
        signal_score, signal_breakdown = self._score_vwap(signal_score, signal_breakdown, current_close, prev_close)
        signal_score, signal_breakdown = self._score_psar(signal_score, signal_breakdown, current_close, prev_close)
        signal_score, signal_breakdown = self._score_orderbook_imbalance(signal_score, signal_breakdown, orderbook_data)
        signal_score, signal_breakdown = self._score_fibonacci_levels(signal_score, signal_breakdown, current_close, prev_close)
        signal_score, signal_breakdown = self._score_ehlers_supertrend(signal_score, signal_breakdown)
        signal_score, signal_breakdown = self._score_macd(signal_score, signal_breakdown)
        signal_score, signal_breakdown = self._score_adx(signal_score, signal_breakdown)
        signal_score, signal_breakdown = self._score_ichimoku_cloud(signal_score, signal_breakdown, current_close, prev_close)
        signal_score, signal_breakdown = self._score_obv(signal_score, signal_breakdown)
        signal_score, signal_breakdown = self._score_cmf(signal_score, signal_breakdown)
        signal_score, signal_breakdown = self._score_volatility_index(signal_score, signal_breakdown)
        signal_score, signal_breakdown = self._score_vwma(signal_score, signal_breakdown, current_close, prev_close)
        signal_score, signal_breakdown = self._score_volume_delta(signal_score, signal_breakdown) # Volume Delta is now a scoring indicator
        signal_score, signal_breakdown = self._score_mtf_confluence(signal_score, signal_breakdown, mtf_trends)


        # --- NEW: Volume Confirmation Filter ---
        volume_confirmation_multiplier = Decimal(str(self.config.get("volume_confirmation_multiplier", 1.0)))
        
        # Only apply if the multiplier is greater than 1 (meaning it's actively configured to confirm)
        if volume_confirmation_multiplier > 1.0 and len(self.df) > 2:
            current_volume = self.df["volume"].iloc[-1]
            average_volume = self.df["volume"].iloc[:-1].mean() # Average of previous bars

            is_volume_confirmed_buy = False
            is_volume_confirmed_sell = False

            if current_volume > average_volume * volume_confirmation_multiplier:
                if current_close > prev_close: # Current candle is bullish
                    is_volume_confirmed_buy = True
                elif current_close < prev_close: # Current candle is bearish
                    is_volume_confirmed_sell = True
            
            # Integrate Volume Delta for more sophisticated confirmation
            volume_delta = self._get_indicator_value("Volume_Delta")
            volume_delta_threshold = self.indicator_settings.get("volume_delta_threshold", 0.2)

            if not pd.isna(volume_delta):
                if volume_delta > volume_delta_threshold: # Strong buying pressure
                    is_volume_confirmed_buy = True
                elif volume_delta < -volume_delta_threshold: # Strong selling pressure
                    is_volume_confirmed_sell = True

            # Adjust signal score based on volume confirmation
            if signal_score > 0 and not is_volume_confirmed_buy:
                signal_score *= 0.5 # Reduce bullish signal strength if not volume confirmed
                signal_breakdown["Volume_Confirmation_Filter"] = -signal_score * 0.5
                self.logger.debug(f"{NEON_YELLOW}[{self.symbol}] Bullish signal reduced due to lack of volume confirmation.{RESET}")
            elif signal_score < 0 and not is_volume_confirmed_sell:
                signal_score *= 0.5 # Reduce bearish signal strength if not volume confirmed
                signal_breakdown["Volume_Confirmation_Filter"] = -signal_score * 0.5
                self.logger.debug(f"{NEON_YELLOW}[{self.symbol}] Bearish signal reduced due to lack of volume confirmation.{RESET}")


        # --- Final Signal Determination with Hysteresis and Cooldown ---
        threshold = self.config["signal_score_threshold"]
        cooldown_sec = self.config["cooldown_sec"]
        hysteresis_ratio = self.config["hysteresis_ratio"]

        final_signal = "HOLD"
        now_ts = int(time.time())

        is_strong_buy = signal_score >= threshold
        is_strong_sell = signal_score <= -threshold

        # Apply hysteresis to prevent immediate flip-flops
        if self._last_signal_score > 0 and signal_score > -threshold * hysteresis_ratio and not is_strong_buy:
            final_signal = "BUY"
        elif self._last_signal_score < 0 and signal_score < threshold * hysteresis_ratio and not is_strong_sell:
            final_signal = "SELL"
        elif is_strong_buy:
            final_signal = "BUY"
        elif is_strong_sell:
            final_signal = "SELL"

        # Apply cooldown period
        if final_signal != "HOLD":
            if now_ts - self._last_signal_ts < cooldown_sec:
                self.logger.info(f"{NEON_YELLOW}[{self.symbol}] Signal '{final_signal}' ignored due to cooldown ({cooldown_sec - (now_ts - self._last_signal_ts)}s remaining).{RESET}")
                final_signal = "HOLD"
            else:
                self._last_signal_ts = now_ts

        self._last_signal_score = signal_score

        self.logger.info(
            f"{NEON_YELLOW}[{self.symbol}] Raw Signal Score: {signal_score:.2f}, Final Signal: {final_signal}{RESET}"
        )
        return final_signal, signal_score, signal_breakdown
```

---

### Suggestion 5: Persistent Trade History and Performance Tracking

**Problem:** The `PerformanceTracker` stores all trade history in memory (`self.trades`). If the bot restarts, all previous trade data and performance metrics (total PnL, wins, losses) are lost. This makes it impossible to track long-term performance without a continuous uptime.

**Solution:** Implement methods within the `PerformanceTracker` to load trade history from a persistent storage (e.g., a JSON file) upon initialization and save it after each trade is recorded. This ensures that performance data is retained across bot restarts.

**Code Snippet (Modifications in `PerformanceTracker`):**

```python
# Create a new constant for the trade file
# Add this near other constants like CONFIG_FILE, LOG_DIRECTORY
TRADE_HISTORY_FILE = "trade_history.json"


class PerformanceTracker:
    """Tracks and reports trading performance."""

    def __init__(self, logger: logging.Logger):
        """Initializes the PerformanceTracker."""
        self.logger = logger
        self.trades: list[dict] = []
        self.total_pnl = Decimal("0")
        self.wins = 0
        self.losses = 0
        # NEW: Load previous trades on startup
        self._load_trades()

    def _load_trades(self) -> None:
        """Loads trade history from a JSON file."""
        trade_filepath = Path(LOG_DIRECTORY) / TRADE_HISTORY_FILE
        if trade_filepath.exists():
            try:
                with trade_filepath.open("r", encoding="utf-8") as f:
                    loaded_trades = json.load(f)
                    for trade in loaded_trades:
                        # Convert Decimal strings back to Decimal objects and datetime strings to datetime objects
                        trade["entry_time"] = datetime.fromisoformat(trade["entry_time"]).replace(tzinfo=TIMEZONE)
                        trade["exit_time"] = datetime.fromisoformat(trade["exit_time"]).replace(tzinfo=TIMEZONE)
                        trade["entry_price"] = Decimal(trade["entry_price"])
                        trade["exit_price"] = Decimal(trade["exit_price"])
                        trade["qty"] = Decimal(trade["qty"])
                        trade["pnl"] = Decimal(trade["pnl"])
                        
                        self.trades.append(trade)
                        self.total_pnl += trade["pnl"]
                        if trade["pnl"] > 0:
                            self.wins += 1
                        else:
                            self.losses += 1
                self.logger.info(f"{NEON_GREEN}Loaded {len(self.trades)} previous trades from {trade_filepath}.{RESET}")
            except (OSError, json.JSONDecodeError, ValueError) as e:
                self.logger.error(f"{NEON_RED}Error loading trade history from {trade_filepath}: {e}{RESET}")
        else:
            self.logger.info(f"{NEON_BLUE}No existing trade history file found at {trade_filepath}. Starting fresh.{RESET}")


    def _save_trades(self) -> None:
        """Saves current trade history to a JSON file."""
        trade_filepath = Path(LOG_DIRECTORY) / TRADE_HISTORY_FILE
        try:
            # Prepare trades for JSON serialization (convert Decimals to strings, datetimes to ISO format)
            serializable_trades = []
            for trade in self.trades:
                serializable_trade = trade.copy()
                serializable_trade["entry_time"] = trade["entry_time"].isoformat()
                serializable_trade["exit_time"] = trade["exit_time"].isoformat()
                serializable_trade["entry_price"] = str(trade["entry_price"].normalize())
                serializable_trade["exit_price"] = str(trade["exit_price"].normalize())
                serializable_trade["qty"] = str(trade["qty"].normalize())
                serializable_trade["pnl"] = str(trade["pnl"].normalize())
                serializable_trades.append(serializable_trade)

            with trade_filepath.open("w", encoding="utf-8") as f:
                json.dump(serializable_trades, f, indent=4)
            self.logger.debug(f"{NEON_BLUE}Trade history saved to {trade_filepath}.{RESET}")
        except OSError as e:
            self.logger.error(f"{NEON_RED}Error saving trade history to {trade_filepath}: {e}{RESET}")

    def record_trade(self, position: dict, pnl: Decimal) -> None:
        """Record a completed trade."""
        trade_record = {
            "entry_time": position["entry_time"],
            "exit_time": position["exit_time"],
            "symbol": position["symbol"],
            "side": position["side"],
            "entry_price": position["entry_price"],
            "exit_price": position["exit_price"],
            "qty": position["qty"],
            "pnl": pnl,
            "closed_by": position["closed_by"],
        }
        self.trades.append(trade_record)
        self.total_pnl += pnl
        if pnl > 0:
            self.wins += 1
        else:
            self.losses += 1
        self.logger.info(
            f"{NEON_CYAN}[{position['symbol']}] Trade recorded. PnL: {pnl.normalize():.2f}. Current Total PnL: {self.total_pnl.normalize():.2f}, Wins: {self.wins}, Losses: {self.losses}{RESET}"
        )
        self.logger.info("Trade recorded", extra=trade_record)
        # NEW: Save trades after each record
        self._save_trades()

    def get_summary(self) -> dict:
        """Return a summary of all recorded trades."""
        total_trades = len(self.trades)
        win_rate = (self.wins / total_trades) * 100 if total_trades > 0 else 0

        return {
            "total_trades": total_trades,
            "total_pnl": self.total_pnl,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": f"{win_rate:.2f}%",
        }

```
