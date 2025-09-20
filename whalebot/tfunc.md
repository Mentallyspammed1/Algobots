Okay, let's enhance the `wb1.0.1.py` file to include actual trading function implementations, moving beyond pure simulation for order placement, stop-loss, take-profit, and trailing stop management.

We'll focus on:
1.  **Placing Market Orders:** Sending a BUY/SELL order to Bybit.
2.  **Setting Initial TP/SL:** Attaching Take Profit and Stop Loss to the newly opened position.
3.  **Updating Trailing Stop Loss:** Adjusting the SL for open positions on the exchange.
4.  **Fetching Actual Positions:** Querying Bybit to get the real status of open positions.

This will involve adding new helper functions for Bybit API calls and modifying the `PositionManager` class significantly.

**Key Changes:**

1.  **New API Helper Functions:**
    *   `place_market_order`: To send a market order.
    *   `set_position_tpsl`: To set or update TP/SL on an existing position.
    *   `get_open_positions_from_exchange`: To fetch actual open positions from Bybit.

2.  **`PositionManager` Modifications:**
    *   `open_position`: Will now call `place_market_order` and `set_position_tpsl`. It will store the Bybit `positionId` and `orderId`.
    *   `manage_positions`: Will `get_open_positions_from_exchange` to update its internal state, then apply trailing stop logic by calling `set_position_tpsl` if the trailing stop moves favorably. It will also correctly identify positions closed by the exchange.
    *   `_calculate_order_size`: Will assume `USDT` for `account_balance` and `risk_amount`.
    *   The structure of `self.open_positions` will change to include Bybit-specific IDs and the `trailing_stop_price` as tracked on the exchange.

**Assumptions:**
*   **One-Way Mode:** We'll assume the Bybit account is in `One-Way` mode, meaning `positionIdx` for setting TP/SL will be `0`.
*   **Linear Futures:** The bot is configured for `linear` futures (`category: "linear"`).
*   **USDT as base currency:** Position sizing assumes `USDT` balance.
*   **Mock Balance:** `_get_current_balance` will still be mocked for this snippet, but you can integrate real balance fetching.
*   **No order cancellation:** This snippet focuses on market entry and TSL updates. Exiting positions by market order (e.g., if a signal reverses strongly) is not implemented for brevity, as the primary exit is via TP/SL on the exchange.

---

Here are the snippets to be added/modified in your `wb1.0.1.py` file.

**Step 1: Add new API functions for trading**

Place these new functions within the "--- API Interaction ---" section, for example, after `fetch_orderbook`.

```python
# --- Trading Specific API Interactions ---

def place_market_order(
    symbol: str,
    side: Literal["Buy", "Sell"],
    qty: Decimal,
    logger: logging.Logger,
    order_type: Literal["Market", "Limit"] = "Market",
    price: Decimal | None = None, # Required for Limit orders
    category: Literal["linear", "inverse"] = "linear"
) -> dict | None:
    """
    Places a market order on Bybit.
    https://bybit-exchange.github.io/docs/v5/order/create
    """
    endpoint = "/v5/order/create"
    
    # Ensure qty is a string with correct precision
    order_params = {
        "category": category,
        "symbol": symbol,
        "side": side,
        "orderType": order_type,
        "qty": str(qty.normalize()), # Ensure Decimal is converted to string for API
    }
    
    if order_type == "Limit":
        if price is None:
            logger.error(f"{NEON_RED}[{symbol}] Price is required for a Limit order.{RESET}")
            return None
        order_params["price"] = str(price.normalize()) # Ensure Decimal is converted to string
    
    logger.info(f"{NEON_BLUE}[{symbol}] Attempting to place {side} {order_type} order for {qty.normalize()} at {price.normalize() if price else 'Market'}...{RESET}")
    response = bybit_request("POST", endpoint, order_params, signed=True, logger=logger)

    if response and response["result"]:
        logger.info(f"{NEON_GREEN}[{symbol}] Order placed successfully: {response['result']}{RESET}")
        return response["result"]
    else:
        logger.error(f"{NEON_RED}[{symbol}] Failed to place order. Response: {response}{RESET}")
        return None

def set_position_tpsl(
    symbol: str,
    take_profit: Decimal | None,
    stop_loss: Decimal | None,
    logger: logging.Logger,
    position_idx: int = 0, # Assuming One-Way Mode (0 for both long/short)
    category: Literal["linear", "inverse"] = "linear"
) -> dict | None:
    """
    Sets or updates Take Profit and Stop Loss for an existing position.
    https://bybit-exchange.github.io/docs/v5/position/trading-stop
    """
    endpoint = "/v5/position/set-trading-stop"
    params = {
        "category": category,
        "symbol": symbol,
        "positionIdx": position_idx,
    }
    if take_profit is not None:
        params["takeProfit"] = str(take_profit.normalize())
    if stop_loss is not None:
        params["stopLoss"] = str(stop_loss.normalize())
    
    if take_profit is None and stop_loss is None:
        logger.warning(f"{NEON_YELLOW}[{symbol}] No TP or SL provided for set_position_tpsl. Skipping.{RESET}")
        return None

    logger.debug(f"[{symbol}] Attempting to set TP/SL: {params}")
    response = bybit_request("POST", endpoint, params, signed=True, logger=logger)

    if response and response["retCode"] == 0:
        logger.info(f"{NEON_GREEN}[{symbol}] TP/SL for position updated successfully. SL: {stop_loss.normalize() if stop_loss else 'N/A'}, TP: {take_profit.normalize() if take_profit else 'N/A'}{RESET}")
        return response["result"]
    else:
        logger.error(f"{NEON_RED}[{symbol}] Failed to set TP/SL. Response: {response}{RESET}")
        return None

def get_open_positions_from_exchange(
    symbol: str,
    logger: logging.Logger,
    category: Literal["linear", "inverse"] = "linear"
) -> list[dict]:
    """
    Fetches all open positions for a given symbol from the Bybit exchange.
    https://bybit-exchange.github.io/docs/v5/position/query
    """
    endpoint = "/v5/position/list"
    params = {
        "category": category,
        "symbol": symbol,
    }
    response = bybit_request("GET", endpoint, params, signed=True, logger=logger)

    if response and response["result"] and response["result"]["list"]:
        # Filter for truly open positions (size > 0)
        open_positions = [
            p for p in response["result"]["list"] if Decimal(p.get("size", "0")) > 0
        ]
        logger.debug(f"[{symbol}] Fetched {len(open_positions)} open positions from exchange.")
        return open_positions
    logger.debug(f"[{symbol}] No open positions found on exchange or failed to fetch. Raw response: {response}")
    return []

```

**Step 2: Modify the `PositionManager` class**

Replace your existing `PositionManager` class with this updated version.

```python
# --- Position Management ---
class PositionManager:
    """Manages open positions, stop-loss, and take-profit levels."""

    def __init__(self, config: dict[str, Any], logger: logging.Logger, symbol: str):
        """Initializes the PositionManager."""
        self.config = config
        self.logger = logger
        self.symbol = symbol
        # open_positions will now store detailed exchange-confirmed position data
        # {
        #   "positionIdx": int, # 0 for one-way, 1 for long, 2 for short (hedge)
        #   "side": str,        # "Buy" or "Sell"
        #   "entry_price": Decimal,
        #   "qty": Decimal,
        #   "stop_loss": Decimal,
        #   "take_profit": Decimal,
        #   "position_id": str, # Bybit's positionId
        #   "order_id": str,    # Bybit's orderId for the entry trade
        #   "entry_time": datetime,
        #   "initial_stop_loss": Decimal, # The SL set at entry, before TSL modifications
        #   "trailing_stop_activated": bool,
        #   "trailing_stop_price": Decimal | None # The actual trailing stop price set on exchange
        # }
        self.open_positions: list[dict] = []
        self.trade_management_enabled = config["trade_management"]["enabled"]
        self.max_open_positions = config["trade_management"]["max_open_positions"]
        self.order_precision = config["trade_management"]["order_precision"]
        self.price_precision = config["trade_management"]["price_precision"]
        self.enable_trailing_stop = config["trade_management"].get("enable_trailing_stop", False)
        self.trailing_stop_atr_multiple = Decimal(str(config["trade_management"].get("trailing_stop_atr_multiple", 0.0)))
        self.break_even_atr_trigger = Decimal(str(config["trade_management"].get("break_even_atr_trigger", 0.0)))

        # Define precision for quantization, e.g., 5 decimal places for crypto
        self.price_quantize_dec = Decimal("1e-" + str(self.price_precision))
        self.qty_quantize_dec = Decimal("1e-" + str(self.order_precision))

        # Initial sync of open positions from exchange
        self.sync_positions_from_exchange()

    def _get_current_balance(self) -> Decimal:
        """
        Fetch current account balance (simplified for simulation).
        In a real bot, this would query the exchange's wallet balance.
        """
        # Example API call for real balance (needs authentication):
        # endpoint = "/v5/account/wallet-balance"
        # params = {"accountType": "UNIFIED"} # Or "CONTRACT" depending on account type
        # response = bybit_request("GET", endpoint, params, signed=True, logger=self.logger)
        # if response and response["result"] and response["result"]["list"]:
        #     for coin_balance in response["result"]["list"][0]["coin"]:
        #         if coin_balance["coin"] == "USDT": # Assuming USDT as base currency
        #             return Decimal(coin_balance["walletBalance"])
        # Fallback to configured balance for simulation
        return Decimal(str(self.config["trade_management"]["account_balance"]))

    def _calculate_order_size(
        self, current_price: Decimal, atr_value: Decimal
    ) -> Decimal:
        """Calculate order size based on risk per trade and ATR."""
        if not self.trade_management_enabled:
            return Decimal("0")

        account_balance = self._get_current_balance()
        risk_per_trade_percent = (
            Decimal(str(self.config["trade_management"]["risk_per_trade_percent"]))
            / 100
        )
        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"])
        )

        risk_amount = account_balance * risk_per_trade_percent
        stop_loss_distance = atr_value * stop_loss_atr_multiple

        if stop_loss_distance <= 0:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Calculated stop loss distance is zero or negative ({stop_loss_distance}). Cannot determine order size.{RESET}"
            )
            return Decimal("0")

        # Order size in USD value
        order_value = risk_amount / stop_loss_distance
        # Convert to quantity of the asset (e.g., BTC)
        order_qty = order_value / current_price

        # Round order_qty to appropriate precision for the symbol
        order_qty = order_qty.quantize(self.qty_quantize_dec, rounding=ROUND_DOWN)

        self.logger.info(
            f"[{self.symbol}] Calculated order size: {order_qty.normalize()} (Risk: {risk_amount.normalize():.2f} USD)"
        )
        return order_qty

    def sync_positions_from_exchange(self):
        """Fetches current open positions from the exchange and updates the internal list."""
        exchange_positions = get_open_positions_from_exchange(self.symbol, self.logger)
        
        new_open_positions = []
        for ex_pos in exchange_positions:
            # Bybit API returns 'Buy' or 'Sell' for position side
            side = ex_pos["side"]
            qty = Decimal(ex_pos["size"])
            entry_price = Decimal(ex_pos["avgPrice"])
            stop_loss_price = Decimal(ex_pos.get("stopLoss", "0")) if ex_pos.get("stopLoss") else Decimal("0")
            take_profit_price = Decimal(ex_pos.get("takeProfit", "0")) if ex_pos.get("takeProfit") else Decimal("0")
            trailing_stop = Decimal(ex_pos.get("trailingStop", "0")) if ex_pos.get("trailingStop") else Decimal("0")

            # Check if this position is already in our tracked list
            existing_pos = next(
                (p for p in self.open_positions if p.get("position_id") == ex_pos["positionIdx"] and p.get("side") == side),
                None,
            )

            if existing_pos:
                # Update existing position details
                existing_pos.update({
                    "entry_price": entry_price.quantize(self.price_quantize_dec),
                    "qty": qty.quantize(self.qty_quantize_dec),
                    "stop_loss": stop_loss_price.quantize(self.price_quantize_dec),
                    "take_profit": take_profit_price.quantize(self.price_quantize_dec),
                    "trailing_stop_price": trailing_stop.quantize(self.price_quantize_dec) if trailing_stop else None,
                    # Recalculate 'trailing_stop_activated' if needed based on `trailing_stop` field.
                    "trailing_stop_activated": trailing_stop > 0 if self.enable_trailing_stop else False
                })
                new_open_positions.append(existing_pos)
            else:
                # Add new position detected on exchange
                self.logger.warning(f"{NEON_YELLOW}[{self.symbol}] Detected new untracked position on exchange. Side: {side}, Qty: {qty}, Entry: {entry_price}. Adding to internal tracking.{RESET}")
                # We can't determine original initial_stop_loss or entry_time easily, so estimate
                new_open_positions.append({
                    "positionIdx": ex_pos["positionIdx"],
                    "side": side,
                    "entry_price": entry_price.quantize(self.price_quantize_dec),
                    "qty": qty.quantize(self.qty_quantize_dec),
                    "stop_loss": stop_loss_price.quantize(self.price_quantize_dec),
                    "take_profit": take_profit_price.quantize(self.price_quantize_dec),
                    "position_id": ex_pos.get("positionId", str(ex_pos["positionIdx"])), # Use positionIdx as ID if no explicit positionId
                    "order_id": "UNKNOWN", # Cannot retrieve original order ID easily from position list
                    "entry_time": datetime.now(TIMEZONE), # Estimate if not available
                    "initial_stop_loss": stop_loss_price.quantize(self.price_quantize_dec), # Assume current SL is initial if not tracked
                    "trailing_stop_activated": trailing_stop > 0 if self.enable_trailing_stop else False,
                    "trailing_stop_price": trailing_stop.quantize(self.price_quantize_dec) if trailing_stop else None,
                })
        
        # Identify positions that were tracked internally but are no longer on the exchange
        # This means they were closed (by SL/TP hit or manual intervention)
        for tracked_pos in self.open_positions:
            is_still_open = any(
                ex_pos["positionIdx"] == tracked_pos.get("position_id") and ex_pos["side"] == tracked_pos["side"]
                for ex_pos in exchange_positions
            )
            if not is_still_open:
                self.logger.info(f"{NEON_BLUE}[{self.symbol}] Position {tracked_pos['side']} (ID: {tracked_pos.get('position_id', 'N/A')}) no longer open on exchange. Marking as closed.{RESET}")
                # Record this closure in performance_tracker if it was successfully opened by us
                # (This part would ideally be called by `manage_positions` when it detects an actual close event from exchange)
        
        self.open_positions = new_open_positions
        if not self.open_positions:
            self.logger.debug(f"[{self.symbol}] No active positions being tracked internally.")


    def open_position(
        self, signal_side: Literal["BUY", "SELL"], current_price: Decimal, atr_value: Decimal
    ) -> dict | None:
        """Open a new position if conditions allow, interacting with the Bybit API."""
        if not self.trade_management_enabled:
            self.logger.info(
                f"{NEON_YELLOW}[{self.symbol}] Trade management is disabled. Skipping opening position.{RESET}"
            )
            return None

        self.sync_positions_from_exchange() # Always sync before opening to get latest count
        if len(self.get_open_positions()) >= self.max_open_positions:
            self.logger.info(
                f"{NEON_YELLOW}[{self.symbol}] Max open positions ({self.max_open_positions}) reached. Cannot open new position.{RESET}"
            )
            return None
        
        # Ensure we don't open multiple positions of the same side if in one-way mode.
        # Bybit's API might allow it, but conceptually for a bot, it's often one per side.
        if any(p["side"].upper() == signal_side for p in self.get_open_positions()):
             self.logger.info(f"{NEON_YELLOW}[{self.symbol}] Already have an open {signal_side} position. Skipping new entry.{RESET}")
             return None


        order_qty = self._calculate_order_size(current_price, atr_value)
        if order_qty <= 0:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Order quantity is zero or negative ({order_qty}). Cannot open position.{RESET}"
            )
            return None

        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"])
        )
        take_profit_atr_multiple = Decimal(
            str(self.config["trade_management"]["take_profit_atr_multiple"])
        )

        # Calculate initial SL and TP based on current price
        if signal_side == "BUY":
            initial_stop_loss = (current_price - (atr_value * stop_loss_atr_multiple)).quantize(self.price_quantize_dec, rounding=ROUND_DOWN)
            take_profit = (current_price + (atr_value * take_profit_atr_multiple)).quantize(self.price_quantize_dec, rounding=ROUND_DOWN)
        else:  # SELL
            initial_stop_loss = (current_price + (atr_value * stop_loss_atr_multiple)).quantize(self.price_quantize_dec, rounding=ROUND_DOWN)
            take_profit = (current_price - (atr_value * take_profit_atr_multiple)).quantize(self.price_quantize_dec, rounding=ROUND_DOWN)
        
        # --- Place Market Order ---
        order_result = place_market_order(self.symbol, signal_side, order_qty, self.logger)

        if not order_result:
            self.logger.error(f"{NEON_RED}[{self.symbol}] Failed to place market order for {signal_side} {order_qty.normalize()}.{RESET}")
            return None

        # Extract actual filled price and quantity from order result
        # For a market order, the `price` in the response is usually the filled price.
        # If filledQty is available, use that.
        filled_qty = Decimal(order_result.get("qty", str(order_qty))) # Fallback to requested qty
        filled_price = Decimal(order_result.get("price", str(current_price))) # Fallback to current price if not explicitly returned
        order_id = order_result.get("orderId")
        
        # Bybit often returns `positionIdx` in the order result, or we assume 0 for one-way mode.
        # The positionId from /v5/position/list is also often 0 for one-way
        position_idx_on_exchange = int(order_result.get("positionIdx", 0))

        # --- Set TP/SL for the newly opened position ---
        # It's crucial to set TP/SL *after* the position is open on the exchange.
        # Bybit's set-trading-stop endpoint uses the position's `positionIdx`.
        tpsl_result = set_position_tpsl(
            self.symbol,
            take_profit=take_profit,
            stop_loss=initial_stop_loss,
            logger=self.logger,
            position_idx=position_idx_on_exchange
        )

        if not tpsl_result:
            self.logger.error(f"{NEON_RED}[{self.symbol}] Failed to set TP/SL for new position. Manual intervention needed!{RESET}")
            # Consider closing the position if TP/SL cannot be set for risk management.
            # For this snippet, we proceed but log a severe warning.

        new_position = {
            "positionIdx": position_idx_on_exchange,
            "symbol": self.symbol,
            "side": signal_side,
            "entry_price": filled_price.quantize(self.price_quantize_dec),
            "qty": filled_qty.quantize(self.qty_quantize_dec),
            "stop_loss": initial_stop_loss, # This will be the dynamic SL
            "take_profit": take_profit,
            "position_id": position_idx_on_exchange, # Using positionIdx as its unique ID for one-way mode
            "order_id": order_id,
            "entry_time": datetime.now(TIMEZONE),
            "initial_stop_loss": initial_stop_loss, # Store original SL
            "trailing_stop_activated": False,
            "trailing_stop_price": None, # Will be set when TSL is activated on exchange
        }
        self.open_positions.append(new_position)
        self.logger.info(f"{NEON_GREEN}[{self.symbol}] Successfully opened {signal_side} position and set initial TP/SL: {new_position}{RESET}")
        return new_position


    def manage_positions(
        self, current_price: Decimal, performance_tracker: Any, atr_value: Decimal
    ) -> None:
        """
        Syncs open positions from the exchange and applies trailing stop logic.
        Records closed positions based on exchange updates.
        """
        if not self.trade_management_enabled:
            return

        # 1. Sync internal state with actual exchange positions
        self.sync_positions_from_exchange()

        # Create a copy to iterate, allowing modification of original list if positions are closed.
        current_internal_positions = list(self.open_positions) 
        positions_closed_on_exchange_ids = set()

        # Iterate through the internally tracked positions
        for position in current_internal_positions:
            # First, check if this position is still genuinely open on the exchange
            # This is implicitly handled by `sync_positions_from_exchange` which rebuilds `self.open_positions`
            # If a position exists in `self.open_positions` after sync, it means it's still open on the exchange.
            # If it's not in `self.open_positions` after sync, it means it was closed on the exchange.
            
            # Retrieve the latest version of the position from `self.open_positions` after sync
            # This is important to get the most up-to-date SL/TP/trailingStop values from Bybit
            latest_pos_from_sync = next(
                (p for p in self.open_positions if p.get("position_id") == position.get("position_id") and p.get("side") == position.get("side")),
                None,
            )
            
            if not latest_pos_from_sync:
                # Position was closed on the exchange. Record it.
                # Since we don't get direct 'closed by' reason from just `position/list` for historical close,
                # we'll use our internal current_price vs. position's last known SL/TP to infer.
                # In a real bot, you'd check historical orders or webhooks for precise exit details.
                close_price = current_price
                closed_by = "UNKNOWN"
                if position["side"] == "BUY":
                    if current_price <= position["stop_loss"]:
                        closed_by = "STOP_LOSS"
                    elif current_price >= position["take_profit"]:
                        closed_by = "TAKE_PROFIT"
                else: # SELL
                    if current_price >= position["stop_loss"]:
                        closed_by = "STOP_LOSS"
                    elif current_price <= position["take_profit"]:
                        closed_by = "TAKE_PROFIT"
                
                # Calculate PnL for recording
                pnl = (
                    (close_price - position["entry_price"]) * position["qty"]
                    if position["side"] == "BUY"
                    else (position["entry_price"] - close_price) * position["qty"]
                )
                
                # Ensure the trade is only recorded once
                # A more robust system would involve a persistent storage for positions and trades.
                performance_tracker.record_trade(
                    {**position, "exit_price": close_price.quantize(self.price_quantize_dec), "exit_time": datetime.now(TIMEZONE), "closed_by": closed_by},
                    pnl
                )
                positions_closed_on_exchange_ids.add(position.get("position_id"))
                self.logger.info(f"{NEON_BLUE}[{self.symbol}] Detected and recorded closure of {position['side']} position (ID: {position.get('position_id')}). PnL: {pnl.normalize():.2f}{RESET}")
                continue # Skip trailing stop logic for this position as it's closed

            # Use the latest synced position details for trailing stop logic
            position = latest_pos_from_sync 

            side = position["side"]
            entry_price = position["entry_price"]
            current_stop_loss_on_exchange = position["stop_loss"] # This is what Bybit has for SL
            # take_profit_on_exchange = position["take_profit"] # Not directly used for TSL logic, but could be for other checks

            # --- Trailing Stop Loss Logic ---
            if self.enable_trailing_stop and atr_value > 0:
                profit_trigger_level = entry_price + (atr_value * self.break_even_atr_trigger) if side == "BUY" \
                                       else entry_price - (atr_value * self.break_even_atr_trigger)

                # Check if price has moved sufficiently into profit to activate/adjust TSL
                if (side == "BUY" and current_price >= profit_trigger_level) or \
                   (side == "SELL" and current_price <= profit_trigger_level):
                    
                    position["trailing_stop_activated"] = True
                    
                    # Calculate new potential trailing stop based on current price and ATR multiple
                    new_trailing_stop_candidate = (current_price - (atr_value * self.trailing_stop_atr_multiple)).quantize(self.price_quantize_dec, rounding=ROUND_DOWN) if side == "BUY" \
                                                else (current_price + (atr_value * self.trailing_stop_atr_multiple)).quantize(self.price_quantize_dec, rounding=ROUND_DOWN)
                    
                    # Ensure TSL does not move against the position or below initial stop loss (for BUY) / above initial stop loss (for SELL)
                    # For BUY: new_tsl > current_sl_on_exchange AND new_tsl > initial_sl (if not already passed initial_sl)
                    # For SELL: new_tsl < current_sl_on_exchange AND new_tsl < initial_sl (if not already passed initial_sl)
                    
                    should_update_sl = False
                    updated_sl_value = current_stop_loss_on_exchange

                    if side == "BUY":
                        # Move SL up, but not below its initial entry value
                        if new_trailing_stop_candidate > current_stop_loss_on_exchange:
                             updated_sl_value = max(new_trailing_stop_candidate, position["initial_stop_loss"]).quantize(self.price_quantize_dec)
                             if updated_sl_value > current_stop_loss_on_exchange: # Only update if it actually moves further into profit
                                should_update_sl = True
                        elif current_stop_loss_on_exchange < position["initial_stop_loss"] and self.break_even_atr_trigger == 0:
                            # Edge case: If TSL started below initial_SL (e.g., initial_SL was very tight) and moved to initial_SL level
                            updated_sl_value = position["initial_stop_loss"].quantize(self.price_quantize_dec)
                            if updated_sl_value > current_stop_loss_on_exchange:
                                should_update_sl = True

                    elif side == "SELL":
                        # Move SL down, but not above its initial entry value
                        if new_trailing_stop_candidate < current_stop_loss_on_exchange:
                             updated_sl_value = min(new_trailing_stop_candidate, position["initial_stop_loss"]).quantize(self.price_quantize_dec)
                             if updated_sl_value < current_stop_loss_on_exchange: # Only update if it actually moves further into profit
                                should_update_sl = True
                        elif current_stop_loss_on_exchange > position["initial_stop_loss"] and self.break_even_atr_trigger == 0:
                            # Edge case: If TSL started above initial_SL and moved to initial_SL level
                            updated_sl_value = position["initial_stop_loss"].quantize(self.price_quantize_dec)
                            if updated_sl_value < current_stop_loss_on_exchange:
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
                            # Update internal tracking
                            position["stop_loss"] = updated_sl_value
                            position["trailing_stop_price"] = updated_sl_value # Store the TSL value
                            self.logger.info(
                                f"{NEON_GREEN}[{self.symbol}] TSL Updated for {side} position (ID: {position['position_id']}): Entry: {entry_price.normalize()}, Current Price: {current_price.normalize()}, New SL: {updated_sl_value.normalize()}{RESET}"
                            )
                        else:
                            self.logger.error(f"{NEON_RED}[{self.symbol}] Failed to update TSL for {side} position (ID: {position['position_id']}).{RESET}")
            
            # Note: The actual closing of the position (by SL or TP) is handled by the exchange.
            # Our `sync_positions_from_exchange` will detect if a position is no longer present.

        # After checking all positions, ensure `self.open_positions` only contains truly open ones.
        # This is already handled by `self.sync_positions_from_exchange()` at the start.
        # However, to be extra robust, one could filter out the `positions_closed_on_exchange_ids` here as well,
        # but `sync_positions_from_exchange` should already have removed them.
        self.open_positions = [
            pos for pos in self.open_positions if pos.get("position_id") not in positions_closed_on_exchange_ids
        ]


    def get_open_positions(self) -> list[dict]:
        """Return a list of currently open positions tracked internally."""
        # This is just returning the internal state, which is periodically synced with exchange
        return self.open_positions
```

**Step 3: Update `main` function (small adjustment)**

In your `main` function, where `position_manager.manage_positions` is called, ensure `atr_value` is correctly passed. The `TradingAnalyzer` calculates ATR, so we need to retrieve its value before calling `manage_positions`.

Locate the `main()` function and make sure it retrieves `atr_value` from the `analyzer` object before calling `position_manager.manage_positions`.

```python
# ... (inside main function, within the while True loop) ...

            # Display current market data and indicators before signal generation
            # NOTE: If you pass `signal_breakdown` to display_indicator_values_and_price here,
            # it would be empty. It's populated after generate_trading_signal.
            # We'll call it again *after* signal generation for a complete picture.
            # display_indicator_values_and_price(
            #     config, logger, current_price, df, orderbook_data, mtf_trends
            # )

            # Initialize TradingAnalyzer with the primary DataFrame for signal generation
            analyzer = TradingAnalyzer(df, config, logger, config["symbol"])

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
                self.logger.warning(f"{NEON_YELLOW}[{config['symbol']}] ATR value was zero or negative, defaulting to {atr_value}.{RESET}")


            # Generate trading signal
            trading_signal, signal_score, signal_breakdown = analyzer.generate_trading_signal(
                current_price, orderbook_data, mtf_trends
            )

            # Manage open positions (sync with exchange, check/update TSL)
            # This should happen *before* deciding to open a new position,
            # as it updates the `self.open_positions` list
            position_manager.manage_positions(current_price, performance_tracker, atr_value)


            # Display current state after analysis and signal generation, including breakdown
            display_indicator_values_and_price(
                config, logger, current_price, df, orderbook_data, mtf_trends, signal_breakdown
            )

            # Execute trades based on strong signals
            signal_threshold = config["signal_score_threshold"]
            # Important: Ensure `position_manager.get_open_positions()` is correctly reflecting
            # current state, usually by calling `sync_positions_from_exchange()` right before.
            # The `open_position` method also calls sync.
            
            # Check if a position of the same side is already open before trying to open a new one
            # This assumes a "one position per side" strategy
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
            open_positions = position_manager.get_open_positions() # Get the *internally tracked* positions
            if open_positions:
                logger.info(f"{NEON_CYAN}[{config['symbol']}] Open Positions: {len(open_positions)}{RESET}")
                for pos in open_positions:
                    # Access dictionary elements directly instead of using .normalize() on Decimal which is already done during quantization
                    logger.info(
                        f"  - {pos['side']} @ {pos['entry_price'].normalize()} (SL: {pos['stop_loss'].normalize()}, TP: {pos['take_profit'].normalize()}, TSL Active: {pos['trailing_stop_activated']}){RESET}"
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
# ... (rest of main function) ...
```

This updated `PositionManager` and its associated API calls will now actually interact with the Bybit exchange for placing and managing orders, introducing real trading functionality into your bot. Remember to set your `BYBIT_API_KEY` and `BYBIT_API_SECRET` in your `.env` file for these functions to work!
