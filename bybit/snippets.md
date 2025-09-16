

  File "/data/data/com.termux/files/home/bybit/mmx.py", line 1981
    'Uses symbol_info's estimate_slippage for accuracy.'
                                                       ^
SyntaxError: unterminated string literal (detected at line 1981)
                                                     u0_a334 in ~/bybit …
➜ cat mmx.md websockets.md | aichat upgrade and enhance > mmx.py
Here are 10 fix or improvement snippets to make the MMXCEL bot more profitable and UI enhanced, along with explanations and where they would fit in your `mmx.py` file.

---

### Profitability Enhancements

**1. Adaptive Rebalance Price Offset (More Profitable Rebalancing)**

*   **Problem:** The `REBALANCE_PRICE_OFFSET_PERCENTAGE` is a static configuration. A fixed offset might be too aggressive in tight markets (leading to taker fees) or too passive in volatile markets (leading to non-fills or missed opportunities).
*   **Improvement:** Make the rebalance price offset dynamic, adjusting it based on current market spread or recent volatility. This ensures rebalances are executed more efficiently, minimizing slippage and maximizing the chance of getting a better fill price.
*   **Location:** `EnhancedMarketMakingStrategy.manage_positions`
*   **Snippet:**

    ```python
    # In EnhancedMarketMakingStrategy.manage_positions method:
    async def manage_positions(self):
        # ... (existing code) ...

        if abs(net_position) > self.config.REBALANCE_THRESHOLD_QTY:
            # ... (existing cooldown check) ...

            rebalance_side = "Sell" if net_position > 0 else "Buy"
            rebalance_qty = abs(net_position).quantize(self.symbol_info.qty_precision, rounding=ROUND_DOWN)

            if rebalance_qty > 0:
                self.log.info(f"Cancelling all open orders before rebalancing to avoid interference.")
                await self.client.cancel_all_orders()
                await asyncio.sleep(1)

                # --- NEW: Dynamic Rebalance Price Offset ---
                # Base offset from config, then adjust based on current market spread
                # If spread is wide, we can be more aggressive with offset to ensure fill.
                # If spread is tight, we can be less aggressive to save on price.
                current_spread_pct = (self.market_state.best_ask - self.market_state.best_bid) / self.market_state.mid_price if self.market_state.mid_price > 0 else Decimal("0")
                
                # Example: Adjust offset based on how wide the current spread is compared to target spread
                # If current_spread_pct is much wider than config.SPREAD_PERCENTAGE, increase offset slightly.
                # If current_spread_pct is very tight, decrease offset.
                dynamic_offset_factor = Decimal("1.0")
                if self.config.SPREAD_PERCENTAGE > 0:
                    spread_ratio = current_spread_pct / self.config.SPREAD_PERCENTAGE
                    if spread_ratio > Decimal("1.5"): # Market is wider than our target
                        dynamic_offset_factor = Decimal("1.2") # Be slightly more aggressive
                    elif spread_ratio < Decimal("0.5"): # Market is very tight
                        dynamic_offset_factor = Decimal("0.8") # Be slightly less aggressive
                
                rebalance_price_offset = self.config.REBALANCE_PRICE_OFFSET_PERCENTAGE * dynamic_offset_factor
                # --- END NEW ---

                result = None
                if self.config.REBALANCE_ORDER_TYPE.lower() == "market":
                    result = await self.client.place_order(rebalance_side, "Market", rebalance_qty)
                else: # Limit order with price improvement logic
                    price = Decimal("0")
                    if rebalance_side == "Buy" and self.market_state.best_ask > 0:
                        price = self.market_state.best_ask * (Decimal("1") + rebalance_price_offset) # Use dynamic offset
                    elif rebalance_side == "Sell" and self.market_state.best_bid > 0:
                        price = self.market_state.best_bid * (Decimal("1") - rebalance_price_offset) # Use dynamic offset
                    
                    # ... (rest of the rebalance logic) ...
    ```

**2. Smart Order Amendment (Reduced Latency & API Calls)**

*   **Problem:** The current `cancel_and_reprice_stale_orders` cancels an order and then relies on the `place_market_making_orders` to place a new one. This is two API calls and introduces a small time window where the bot has no orders. Bybit's `amend_order` can update price/quantity with a single call.
*   **Improvement:** Implement `amend_order` in `EnhancedBybitClient` and use it in `cancel_and_reprice_stale_orders` when an order is only slightly out of market, rather than completely cancelling and replacing.
*   **Location:** `EnhancedBybitClient.amend_order` (new method) and `EnhancedMarketMakingStrategy.cancel_and_reprice_stale_orders`
*   **Snippet:**

    ```python
    # In EnhancedBybitClient class:
    async def amend_order(self, order_id: str, new_price: Optional[Decimal] = None, new_qty: Optional[Decimal] = None) -> bool:
        """Amends an existing order, prioritizing WS then HTTP."""
        amend_params = {
            "category": self.config.CATEGORY,
            "symbol": self.config.SYMBOL,
            "orderId": order_id,
        }
        if new_price is not None:
            amend_params["price"] = str(new_price.quantize(self.symbol_info.price_precision))
        if new_qty is not None:
            amend_params["qty"] = str(new_qty.quantize(self.symbol_info.qty_precision))

        if not amend_params.get("price") and not amend_params.get("qty"):
            self.log.warning(f"No new price or quantity provided for amendment of order {order_id}.")
            return False

        # --- Attempt WS amendment first ---
        response = await self._send_ws_command("order.amend", [amend_params])

        if response and response.get('retCode') == 0:
            self.log.info(f"✏️ Order amended successfully via WS", order_id=order_id, new_price=new_price, new_qty=new_qty)
            # Update local state immediately, WS will confirm later
            if order_id in self.market_state.open_orders:
                if new_price is not None: self.market_state.open_orders[order_id]['price'] = new_price
                if new_qty is not None: self.market_state.open_orders[order_id]['qty'] = new_qty
                self.market_state.open_orders[order_id]['timestamp'] = time.time() # Reset age
            return True
        elif response and response.get('retCode') == 110001: # Order does not exist (already cancelled or filled)
            self.log.info(f"Order {order_id} already non-existent/cancelled. Treating as successful amendment (WS).", order_id=order_id)
            self.market_state.open_orders.pop(order_id, None)
            return True

        # --- Fallback to HTTP if WS fails ---
        self.log.warning(f"WS order.amend failed ({response.get('retMsg', 'Unknown')}), attempting HTTP fallback.")
        http_response = await self.api_call_with_retry(self.http.amend_order, **amend_params)

        if http_response and http_response.get('retCode') == 0:
            self.log.info(f"✏️ Order amended successfully via HTTP (WS fallback)", order_id=order_id, new_price=new_price, new_qty=new_qty)
            if order_id in self.market_state.open_orders:
                if new_price is not None: self.market_state.open_orders[order_id]['price'] = new_price
                if new_qty is not None: self.market_state.open_orders[order_id]['qty'] = new_qty
                self.market_state.open_orders[order_id]['timestamp'] = time.time()
            return True
        elif http_response and http_response.get('retCode') == 110001:
            self.log.info(f"Order {order_id} already non-existent/cancelled. Treating as successful amendment (HTTP).", order_id=order_id)
            self.market_state.open_orders.pop(order_id, None)
            return True

        self.log.error(f"Order amendment failed via both WS and HTTP.", order_id=order_id, response=response, http_response=http_response)
        return False

    # In EnhancedMarketMakingStrategy.cancel_and_reprice_stale_orders:
    async def cancel_and_reprice_stale_orders(self):
        current_time = time.time()
        orders_to_amend_or_cancel = [] # Store (order_id, new_price_if_amend, reason)

        for order_id, order_data in list(self.market_state.open_orders.items()):
            order_age = current_time - order_data.get('timestamp', current_time)
            
            is_stale = order_age > self.config.ORDER_LIFESPAN_SECONDS
            
            is_out_of_market = False
            price_deviation = Decimal("0")
            if self.market_state.mid_price > 0 and order_data.get('price', Decimal('0')) > 0 and self.config.PRICE_THRESHOLD > 0:
                price_deviation = abs(order_data['price'] - self.market_state.mid_price) / self.market_state.mid_price
                if price_deviation > self.config.PRICE_THRESHOLD:
                    is_out_of_market = True
            
            if is_stale or is_out_of_market:
                # --- NEW: Try to amend if only slightly out of market, otherwise cancel ---
                if is_out_of_market and price_deviation <= (self.config.PRICE_THRESHOLD * Decimal("1.5")): # Amend if not too far
                    new_price = self.market_state.mid_price * (Decimal("1") + self.config.SPREAD_PERCENTAGE) if order_data['side'] == 'Sell' else \
                                self.market_state.mid_price * (Decimal("1") - self.config.SPREAD_PERCENTAGE)
                    orders_to_amend_or_cancel.append((order_id, new_price.quantize(self.symbol_info.price_precision), "Amend (Out of Market)"))
                    self.log.info(f"Order marked for amendment", order_id=order_id, reason="Out of Market",
                                  old_price=float(order_data['price']), new_price=float(new_price))
                else: # Too stale or too far out of market, just cancel
                    orders_to_amend_or_cancel.append((order_id, None, "Cancel (Stale/Too Far)"))
                    self.log.info(f"Order marked for cancellation", order_id=order_id, reason="Stale" if is_stale else "Too Far Out of Market",
                                  age=f"{order_age:.1f}s", price_deviation=f"{float(price_deviation):.4f}" if is_out_of_market else "N/A")

        if orders_to_amend_or_cancel:
            self.log.info(f"Processing {len(orders_to_amend_or_cancel)} orders for amendment/cancellation.")
            for order_id, new_price, action_reason in orders_to_amend_or_cancel:
                try:
                    if new_price is not None:
                        await self.client.amend_order(order_id, new_price=new_price)
                    else:
                        await self.client.cancel_order(order_id)
                except Exception as e:
                    self.log.error(f"Error processing order {order_id} ({action_reason}): {e}", exc_info=True)
                    if sentry_sdk: sentry_sdk.capture_exception(e)
    ```

**3. Tiered Order Placement (Increased Fill Probability & Liquidity Provision)**

*   **Problem:** `MAX_OPEN_ORDERS` being 2 means only one bid and one ask. This is basic market making. A more advanced strategy places multiple orders at different price levels to capture more opportunities and provide deeper liquidity.
*   **Improvement:** Allow the bot to place multiple buy and sell orders at incrementally different prices within the defined spread, up to `MAX_OPEN_ORDERS`.
*   **Location:** `EnhancedMarketMakingStrategy.place_market_making_orders`
*   **Snippet:**

    ```python
    # In EnhancedMarketMakingStrategy.place_market_making_orders:
    async def place_market_making_orders(self):
        # ... (existing checks) ...

        spread = self.calculate_dynamic_spread()
        position_size = self.calculate_position_size()
        tick_size = self.symbol_info.price_precision # Use tick size for granular steps

        if position_size <= 0:
            self.log.warning("⚠️ Calculated position size is zero or too small, skipping orders.")
            return

        # --- NEW: Tiered Order Placement ---
        orders_to_place = []
        current_buy_orders = [o for o in self.market_state.open_orders.values() if o['side'] == 'Buy']
        current_sell_orders = [o for o in self.market_state.open_orders.values() if o['side'] == 'Sell']

        # Determine how many buy/sell orders we can place
        max_orders_per_side = self.config.MAX_OPEN_ORDERS // 2 # Integer division

        # Place Buy orders
        for i in range(max_orders_per_side - len(current_buy_orders)):
            # Calculate price for this tier: best_bid - (i * tick_size)
            # Or, for more aggressive, mid_price * (1 - spread) - (i * tick_size)
            target_buy_price = self.market_state.mid_price * (Decimal("1") - spread) - (i * tick_size * Decimal("2")) # Example: 2 ticks away
            target_buy_price = target_buy_price.quantize(tick_size, rounding=ROUND_DOWN)
            
            # Ensure price is not too low or crosses existing orders
            if self.market_state.best_bid > 0:
                target_buy_price = min(target_buy_price, self.market_state.best_bid - tick_size) # Place slightly below best bid
            
            if target_buy_price > 0:
                orders_to_place.append({"side": "Buy", "price": target_buy_price, "qty": position_size})

        # Place Sell orders
        for i in range(max_orders_per_side - len(current_sell_orders)):
            # Calculate price for this tier: best_ask + (i * tick_size)
            # Or, for more aggressive, mid_price * (1 + spread) + (i * tick_size)
            target_sell_price = self.market_state.mid_price * (Decimal("1") + spread) + (i * tick_size * Decimal("2")) # Example: 2 ticks away
            target_sell_price = target_sell_price.quantize(tick_size, rounding=ROUND_UP)

            # Ensure price is not too high or crosses existing orders
            if self.market_state.best_ask > 0:
                target_sell_price = max(target_sell_price, self.market_state.best_ask + tick_size) # Place slightly above best ask

            if target_sell_price > 0:
                orders_to_place.append({"side": "Sell", "price": target_sell_price, "qty": position_size})

        orders_placed_count = 0
        for order_data in orders_to_place:
            # Check if we still have slots available
            if len(self.market_state.open_orders) >= self.config.MAX_OPEN_ORDERS:
                self.log.debug(f"Max open orders ({self.config.MAX_OPEN_ORDERS}) reached during tiered placement, stopping.")
                break

            result = await self.client.place_order(order_data["side"], "Limit", order_data["qty"], order_data["price"])
            success = result is not None
            self.order_success_rate.append(1 if success else 0)
            if success:
                orders_placed_count += 1
        
        if orders_placed_count > 0:
            self.log.info(f"📝 Placed {orders_placed_count} tiered market making orders",
                          spread_pct=f"{float(spread*100):.4f}%",
                          size=float(position_size),
                          adaptive_spread_mult=f"{float(self.adaptive_spread_multiplier):.2f}x",
                          adaptive_qty_mult=f"{float(self.adaptive_quantity_multiplier):.2f}x")
    ```

**4. Fee-Aware Order Placement (Optimize for Maker Fees)**

*   **Problem:** The bot places limit orders, but doesn't explicitly try to ensure they are `PostOnly` to guarantee maker fees, which are typically lower.
*   **Improvement:** Add a `postOnly` parameter to `place_order` and set it to `True` for market-making limit orders. This ensures the order is only placed if it adds liquidity to the order book, guaranteeing maker rebates/lower fees.
*   **Location:** `EnhancedBybitClient.place_order` and `EnhancedMarketMakingStrategy.place_market_making_orders`
*   **Snippet:**

    ```python
    # In EnhancedBybitClient.place_order:
    async def place_order(self, side: str, order_type: str, qty: Decimal, price: Optional[Decimal] = None, post_only: bool = False) -> Optional[Dict]:
        # ... (existing validation and order_params setup) ...

        if order_type == "Limit":
            # ... (existing price validation) ...
            order_params["price"] = str(quantized_price)
            if post_only: # --- NEW: Add postOnly parameter ---
                order_params["postOnly"] = "true" # Bybit API expects "true" or "false" string

        # ... (rest of place_order logic) ...

    # In EnhancedMarketMakingStrategy.place_market_making_orders:
    async def place_market_making_orders(self):
        # ... (existing code) ...

        # In the loop for placing orders:
        for order_data in orders_to_place:
            # ... (existing checks) ...
            result = await self.client.place_order(
                order_data["side"], 
                "Limit", 
                order_data["qty"], 
                order_data["price"], 
                post_only=True # --- NEW: Set post_only to True ---
            )
            # ... (rest of the loop) ...
    ```

**5. Volatility-Adjusted Stop Loss/Take Profit (Dynamic Risk Management)**

*   **Problem:** Fixed `STOP_LOSS_PERCENTAGE` and `PROFIT_PERCENTAGE` don't adapt to market conditions. In low volatility, they might be too wide; in high volatility, too tight.
*   **Improvement:** Adjust the stop loss and take profit percentages dynamically based on recent market volatility (e.g., using the standard deviation of price changes).
*   **Location:** `EnhancedMarketMakingStrategy.monitor_pnl` and potentially `BotConfig` for base values.
*   **Snippet:**

    ```python
    # In EnhancedMarketMakingStrategy.monitor_pnl:
    async def monitor_pnl(self):
        while self.running and not _SHUTDOWN_REQUESTED:
            try:
                # ... (existing data freshness check) ...

                # --- NEW: Calculate dynamic SL/TP thresholds ---
                dynamic_sl_pct = self.config.STOP_LOSS_PERCENTAGE
                dynamic_tp_pct = self.config.PROFIT_PERCENTAGE

                if len(self.market_state.price_history) >= 50: # Need enough data for volatility
                    recent_prices = [p['price'] for p in list(self.market_state.price_history)[-50:] if p['price'] > 0]
                    if len(recent_prices) > 1:
                        price_changes = [recent_prices[i] - recent_prices[i-1] for i in range(1, len(recent_prices))]
                        if price_changes:
                            avg_change = sum(price_changes) / len(price_changes)
                            variance = sum([(x - avg_change)**2 for x in price_changes]) / len(price_changes)
                            std_dev = Decimal(str(variance)).sqrt() if variance >= 0 else Decimal("0")

                            if self.market_state.mid_price > 0:
                                relative_volatility = std_dev / self.market_state.mid_price
                                # Adjust SL/TP based on volatility. Higher volatility -> wider SL/TP.
                                volatility_factor = Decimal("1.0") + (relative_volatility * Decimal("100")) # Tune this factor
                                volatility_factor = max(Decimal("0.5"), min(Decimal("2.0"), volatility_factor)) # Clamp factor

                                dynamic_sl_pct = self.config.STOP_LOSS_PERCENTAGE * volatility_factor
                                dynamic_tp_pct = self.config.PROFIT_PERCENTAGE * volatility_factor
                                self.log.debug(f"Dynamic SL/TP: SL={float(dynamic_sl_pct):.2%}, TP={float(dynamic_tp_pct):.2%}",
                                             volatility_factor=float(volatility_factor))
                # --- END NEW ---

                for side, position in list(self.market_state.positions.items()):
                    # ... (existing PnL calculation) ...

                    # Stop loss logic (use dynamic_sl_pct)
                    if pnl_pct <= -dynamic_sl_pct: # --- MODIFIED ---
                        self.log.error(f"🛑 {side} position stop loss triggered (Dynamic SL: {dynamic_sl_pct:.2%})",
                                   pnl_pct=f"{pnl_pct:.2%}", ...)
                        # ... (rest of stop loss logic) ...

                    # Take profit logic (use dynamic_tp_pct)
                    elif pnl_pct >= dynamic_tp_pct: # --- MODIFIED ---
                        self.log.info(f"🎯 {side} position take profit triggered (Dynamic TP: {dynamic_tp_pct:.2%})",
                                  pnl_pct=f"{pnl_pct:.2%}", ...)
                        # ... (rest of take profit logic) ...

                await asyncio.sleep(5)
            # ... (rest of the method) ...
    ```

---

### UI Enhancements

**6. Enhanced Dashboard Alerts & Recommendations**

*   **Problem:** The dashboard displays metrics but doesn't always provide immediate actionable insights or warnings beyond the health score.
*   **Improvement:** Add specific, human-readable alerts and recommendations to the dashboard based on critical metrics (e.g., high memory, low API success, stale data).
*   **Location:** `display_dashboard`
*   **Snippet:**

    ```python
    # In display_dashboard function:
    async def display_dashboard():
        while not _SHUTDOWN_REQUESTED:
            try:
                # ... (existing dashboard header and main metrics) ...

                print_neon_separator(color=NEON_PURPLE)
                print(f"{NEON_BLUE}{BOLD}🔔 Alerts & Recommendations:{NC}")
                
                alerts_present = False

                # Memory Alert
                memory_usage = system_monitor.get_memory_usage()
                if memory_usage > config.CB_HIGH_MEMORY_MB * 0.8: # 80% of CB threshold
                    print(f"  {RED}🚨 HIGH MEMORY: {memory_usage:.1f}MB. Consider manual cleanup ('m') or restarting bot.{NC}")
                    alerts_present = True
                
                # Data Freshness Alert
                data_age = time.time() - market_state.last_update_time
                if data_age > config.CB_STALE_DATA_TIMEOUT_SEC * 0.7: # 70% of stale timeout
                    print(f"  {YELLOW}⚠️ STALE MARKET DATA: {data_age:.1f}s old. Check WS connection.{NC}")
                    alerts_present = True

                # API Success Rate Alert
                overall_api_success_rate = sum(rate_limiter.success_rate) / len(rate_limiter.success_rate) if rate_limiter.success_rate else 1.0
                if overall_api_success_rate < 0.7: # Below 70%
                    print(f"  {ORANGE}📉 LOW API SUCCESS: {overall_api_success_rate:.1%}. May impact order execution. Check Bybit status.{NC}")
                    alerts_present = True
                
                # Rebalance Needed Alert
                long_size = market_state.positions.get('Long', {}).get('size', Decimal('0'))
                short_size = market_state.positions.get('Short', {}).get('size', Decimal('0'))
                net_position = long_size - short_size
                if abs(net_position) > config.REBALANCE_THRESHOLD_QTY:
                    print(f"  {NEON_ORANGE}⚖️ REBALANCE NEEDED: Net position {net_position:.{qty_precision}f}. Type 'r' to force.{NC}")
                    alerts_present = True

                if not alerts_present:
                    print(f"  {NEON_GREEN}✅ All systems nominal. No active alerts.{NC}")

                print_neon_separator(color=NEON_PURPLE)
                # ... (rest of the dashboard) ...
    ```

**7. Cross-Platform Desktop Notifications (Beyond Termux)**

*   **Problem:** `termux-toast` is great for Android, but the bot might run on other OS where desktop notifications are preferred.
*   **Improvement:** Integrate `plyer` (a cross-platform Python library) for desktop notifications as a fallback or alternative.
*   **Location:** Global `send_toast` function.
*   **Snippet:**

    ```python
    # At the top of mmx.py, add:
    try:
        from plyer import notification
        _HAS_PLYER_NOTIFICATION = True
    except ImportError:
        _HAS_PLYER_NOTIFICATION = False
        notification = None # Ensure notification is None if plyer isn't found

    # Modify send_toast function:
    def send_toast(message: str, color: str = "#336699", text_color: str = "white") -> None:
        """Send toast notification (Termux or Desktop)."""
        if _HAS_TERMUX_TOAST_CMD:
            try:
                os.system(f"termux-toast -b '{color}' -c '{text_color}' '{message}'")
            except Exception as e:
                log.warning(f"Failed to send Termux toast: {e}")
        elif _HAS_PLYER_NOTIFICATION: # --- NEW: Plyer notification ---
            try:
                notification.notify(
                    title="MMXCEL Bot Alert",
                    message=message,
                    app_name="MMXCEL",
                    timeout=5 # seconds
                )
            except Exception as e:
                log.warning(f"Failed to send Plyer notification: {e}")
        else:
            log.debug(f"Toast notification: {message}")
    ```

**8. More Generic Runtime Config Adjustment (Enhanced User Control)**

*   **Problem:** The current runtime config adjustments (`s` for spread, `z` for quantity) are hardcoded. Users might want to adjust other parameters on the fly.
*   **Improvement:** Add a generic command that allows users to specify any `BotConfig` parameter name and its new value.
*   **Location:** `handle_user_input`
*   **Snippet:**

    ```python
    # In handle_user_input function:
    async def handle_user_input(strategy: EnhancedMarketMakingStrategy):
        # ... (existing commands) ...

                    elif key == 'p': # 'p' for parameter
                        sys.stdout.write(f"\n{NEON_PINK}Enter config parameter name (e.g., ORDER_LIFESPAN_SECONDS): {NC}")
                        sys.stdout.flush()
                        param_name = sys.stdin.readline().strip().upper()

                        if not hasattr(config, param_name):
                            log.warning(f"Config parameter '{param_name}' not found.")
                            send_toast(f"❌ Param '{param_name}' not found", "red", "white")
                            continue

                        sys.stdout.write(f"{NEON_PINK}Enter new value for {param_name} (current: {getattr(config, param_name)}): {NC}")
                        sys.stdout.flush()
                        new_value_str = sys.stdin.readline().strip()

                        try:
                            # Attempt to convert to appropriate type based on current config value
                            current_type = type(getattr(config, param_name))
                            if current_type is Decimal:
                                new_value = Decimal(new_value_str)
                            elif current_type is int:
                                new_value = int(new_value_str)
                            elif current_type is float:
                                new_value = float(new_value_str)
                            elif current_type is bool:
                                new_value = new_value_str.lower() in ('true', '1', 't', 'y', 'yes')
                            else: # Assume string
                                new_value = new_value_str

                            setattr(config, param_name, new_value) # Update the global config object
                            # Trigger config update callback if necessary (ConfigManager already handles this via check_for_updates)
                            log.info(f"Updated config parameter '{param_name}'", new_value=new_value)
                            send_toast(f"⚙️ {param_name} updated to {new_value}", "blue", "white")

                        except ValueError:
                            log.warning(f"Invalid value type for parameter '{param_name}'.")
                            send_toast(f"❌ Invalid value for {param_name}", "red", "white")
                        except DecimalException:
                            log.warning(f"Invalid decimal value for parameter '{param_name}'.")
                            send_toast(f"❌ Invalid decimal for {param_name}", "red", "white")
    ```

**9. Simple ASCII Price Trend Graph (Visual UI Enhancement)**

*   **Problem:** Price history is stored but not visualized, making it harder to quickly grasp recent market movement.
*   **Improvement:** Display a simple ASCII line graph of recent mid-prices on the dashboard.
*   **Location:** `display_dashboard`
*   **Snippet:**

    ```python
    # In display_dashboard function:
    async def display_dashboard():
        while not _SHUTDOWN_REQUESTED:
            try:
                # ... (existing dashboard sections) ...

                print_neon_separator(color=NEON_PURPLE)
                print(f"{NEON_BLUE}{BOLD}📈 Price Trend (Last 20 updates):{NC}")
                
                if len(market_state.price_history) >= 2:
                    prices = [p['price'] for p in market_state.price_history if p['price'] > 0]
                    if prices:
                        min_price = min(prices)
                        max_price = max(prices)
                        price_range = max_price - min_price
                        
                        graph_height = 5
                        graph_width = 40 # Adjust as needed

                        if price_range == 0: # Flat line
                            for _ in range(graph_height):
                                print(f"  {NEON_CYAN}{'-' * graph_width}{NC}")
                        else:
                            # Normalize prices to graph height
                            normalized_prices = [int(((p - min_price) / price_range) * (graph_height - 1)) for p in prices]
                            
                            # Create a grid for the graph
                            grid = [[' ' for _ in range(graph_width)] for _ in range(graph_height)]

                            # Map normalized prices to graph positions
                            for i, norm_price in enumerate(normalized_prices[-graph_width:]): # Take last `graph_width` prices
                                col = graph_width - (len(normalized_prices) - i)
                                if 0 <= col < graph_width:
                                    grid[graph_height - 1 - norm_price][col] = '*' # Place '*' at calculated position

                            # Print the grid
                            for row in grid:
                                print(f"  {NEON_CYAN}{''.join(row)}{NC}")
                        
                        print(f"  {NEON_CYAN}Min: {float(min_price):.{price_precision}f} Max: {float(max_price):.{price_precision}f}{NC}")
                    else:
                        print(f"  {NEON_ORANGE}No valid price history to display.{NC}")
                else:
                    print(f"  {NEON_ORANGE}Not enough price history for graph.{NC}")
                
                print_neon_separator(color=NEON_PURPLE)
                # ... (rest of the dashboard) ...
    ```

**10. Dedicated Trade Journal File (Better Analytics & Auditing)**

*   **Problem:** Trade logs are mixed with general bot logs, making it hard to extract and analyze trade performance.
*   **Improvement:** Implement a separate, rotating log file specifically for filled trades. This makes auditing and post-trade analysis much easier.
*   **Location:** `EnhancedLogger` class and `EnhancedBybitClient._on_private_ws_message`
*   **Snippet:**

    ```python
    # In EnhancedLogger class:
    class EnhancedLogger:
        def __init__(self, name: str):
            self.logger = logging.getLogger(name)
            self.logger.setLevel(logging.INFO)
            self.setup_logging() # Call setup in init

        def setup_logging(self):
            # Clear existing handlers to prevent duplicates on config reload
            if self.logger.handlers:
                for handler in self.logger.handlers[:]:
                    self.logger.removeHandler(handler)
                    handler.close()

            # ... (existing console handler setup) ...

            # File handler for general logs
            log_file_path = "mmxcel.log"
            file_handler = logging.handlers.RotatingFileHandler(
                log_file_path,
                maxBytes=config.MAX_LOG_FILE_SIZE, # Use config value
                backupCount=5
            )
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

            # --- NEW: Dedicated Trade Journal File Handler ---
            trade_journal_path = "mmxcel_trades.log"
            trade_formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s' if not LOG_AS_JSON else
                '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "event": "trade_journal", "data": %(message)s}'
            )
            trade_file_handler = logging.handlers.RotatingFileHandler(
                trade_journal_path,
                maxBytes=config.TRADE_JOURNAL_FILE_SIZE, # Use config value
                backupCount=3
            )
            trade_file_handler.setFormatter(trade_formatter)
            self.trade_logger = logging.getLogger(f"{name}.trades") # Separate logger for trades
            self.trade_logger.setLevel(logging.INFO)
            # Clear existing handlers for trade logger too
            if self.trade_logger.handlers:
                for handler in self.trade_logger.handlers[:]:
                    self.trade_logger.removeHandler(handler)
                    handler.close()
            self.trade_logger.addHandler(trade_file_handler)
            # --- END NEW ---

        # Add a new method for journaling trades
        def journal_trade(self, trade_data: Dict):
            """Logs a trade event to the dedicated trade journal."""
            if LOG_AS_JSON:
                self.trade_logger.info(json.dumps(trade_data))
            else:
                self.trade_logger.info(f"TRADE: Side={trade_data.get('side')}, Price={trade_data.get('price')}, "
                                     f"Qty={trade_data.get('quantity')}, OrderID={trade_data.get('order_id')}, "
                                     f"Slippage={trade_data.get('slippage_pct'):.4f}, Latency={trade_data.get('latency'):.3f}s")

    # In EnhancedBybitClient._on_private_ws_message:
    def _on_private_ws_message(self, msg: Dict[str, Any]) -> None:
        # ... (inside the "Filled" order_status block) ...
        
                            trade_data = {
                                'timestamp': time.time(),
                                'order_id': order_id,
                                'client_order_id': order_details.get("client_order_id", "N/A"),
                                'symbol': self.config.SYMBOL,
                                'side': side,
                                'price': actual_price,
                                'quantity': filled_qty,
                                'slippage_pct': slippage,
                                'latency': (time.time() - order_details.get("timestamp", message_start_time)), # Already in seconds
                                'type': 'Filled'
                            }
                            self.market_state.add_trade(trade_data)
                            self.log.journal_trade(trade_data) # --- MODIFIED: Call new journal_trade method ---
        # ... (rest of the method) ...
    ```
