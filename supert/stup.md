```json
{
  "file_name": "stupdated2.py",
  "snippets": [
    {
      "id": 1,
      "name": "Signal Strength Scoring",
      "description": "Enhances signal generation by assigning a score based on the confluence of multiple indicators. A trade is only considered if the signal strength exceeds a configurable threshold, improving signal quality and reducing false positives.",
      "config_changes": [
        {"key": "MIN_SIGNAL_STRENGTH", "type": "int", "default": 3, "description": "Minimum required signal strength score (out of max possible confirming indicators) to execute a trade."}
      ],
      "code_changes": [
        {
          "file_section": "Config class",
          "change_type": "add_field",
          "code": "    MIN_SIGNAL_STRENGTH: int = field(default=3)"
        },
        {
          "file_section": "Config.__post_init__",
          "change_type": "add_load_env",
          "code": "        self.MIN_SIGNAL_STRENGTH = int(os.getenv(\"MIN_SIGNAL_STRENGTH\", self.MIN_SIGNAL_STRENGTH))"
        },
        {
          "file_section": "EhlersSuperTrendBot.__init__",
          "change_type": "add_log",
          "code": "        self.logger.info(f\"  Min Signal Strength: {config.MIN_SIGNAL_STRENGTH}\")"
        },
        {
          "file_section": "EhlersSuperTrendBot.generate_signal",
          "change_type": "modify_function",
          "description": "Modify generate_signal to calculate and return a signal strength score, and integrate VWAP confirmation logic.",
          "code": """
    def generate_signal(self, df: pd.DataFrame) -> tuple[str | None, str, int]:
        \"\"\"
        Generates a potent trading signal by harmonizing the whispers of multiple indicators,
        seeking confluence for optimal entry and exit points, with optional bar confirmation.
        Returns the signal ('BUY'/'SELL'/None), a detailed reason string, and a signal strength score.
        \"\"\"
        if len(df) < 2:
            return None, "Insufficient data for signal generation.", 0

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        # Initialize signal strength score
        signal_strength = 0

        # --- Primary Scalping Signal: Supertrend Flip ---
        st_flipped_up = latest['supertrend_direction'] == 1 and prev['supertrend_direction'] == -1
        st_flipped_down = latest['supertrend_direction'] == -1 and prev['supertrend_direction'] == 1

        # --- Base Confirmation Filters ---
        price_above_filter = latest['close'] > latest['ehlers_filter']
        price_below_filter = latest['close'] < latest['ehlers_filter']

        rsi_bullish = latest['rsi'] > 52
        rsi_bearish = latest['rsi'] < 48

        macd_bullish = latest['macd_diff'] > 0
        macd_bearish = latest['macd_diff'] < 0

        # --- VWAP Confirmation (Snippet 3) ---
        vwap_bullish = False
        vwap_bearish = False
        if self.config.VWAP_CONFIRMATION_ENABLED and 'vwap' in df.columns and not pd.isna(latest['vwap']):
            if latest['close'] > latest['vwap']:
                vwap_bullish = True
            elif latest['close'] < latest['vwap']:
                vwap_bearish = True

        # --- ADX Trend Filter (Existing Feature) ---
        adx_filter_passed = True
        adx_reason = ""
        if self.config.ADX_TREND_FILTER_ENABLED:
            if latest['adx'] < self.config.ADX_MIN_THRESHOLD:
                adx_filter_passed = False
                adx_reason = f"ADX ({latest['adx']:.1f}) below min threshold ({self.config.ADX_MIN_THRESHOLD})."
            elif self.config.ADX_TREND_DIRECTION_CONFIRMATION:
                if st_flipped_up and latest['adx_plus_di'] < latest['adx_minus_di']:
                    adx_filter_passed = False
                    adx_reason = f"ADX Plus DI ({latest['adx_plus_di']:.1f}) not confirming BUY signal."
                elif st_flipped_down and latest['adx_minus_di'] < latest['adx_plus_di']:
                    adx_filter_passed = False
                    adx_reason = f"ADX Minus DI ({latest['adx_minus_di']:.1f}) not confirming SELL signal."
            if not adx_filter_passed:
                return None, f"ADX filter rejected signal. {adx_reason}", 0
            # If ADX filter passes, it contributes to signal strength
            signal_strength += 1

        # --- Multi-Timeframe Confluence Filter (Existing Feature & Snippet 8) ---
        mtf_confluence = True
        mtf_reason = ""
        if self.config.MULTI_TIMEFRAME_CONFIRMATION_ENABLED and not self.higher_timeframe_data.empty:
            htf_latest = self.higher_timeframe_data.iloc[-1]
            htf_confluence_score = 0
            
            # Check primary HTF indicator
            if self.config.HIGHER_TIMEFRAME_INDICATOR == "EHLERS_SUPERTR_DIRECTION":
                htf_st_direction = htf_latest.get('supertrend_direction')
                if (st_flipped_up and htf_st_direction == 1) or (st_flipped_down and htf_st_direction == -1):
                    htf_confluence_score += 1
                    mtf_reason = f"HTF {self.config.HIGHER_TIMEFRAME} Ehlers ST confirms."
                else:
                    mtf_reason = f"HTF {self.config.HIGHER_TIMEFRAME} Ehlers ST is not confirming primary timeframe."
            
            # Check additional HTF indicators (Snippet 8)
            if self.config.MULTI_TIMEFRAME_ADDITIONAL_INDICATORS:
                for additional_indicator in self.config.MULTI_TIMEFRAME_ADDITIONAL_INDICATORS:
                    if additional_indicator == "ADX_TREND":
                        htf_adx = htf_latest.get('adx', 0)
                        if htf_adx >= self.config.ADX_MIN_THRESHOLD: # Only consider if ADX is strong enough
                            if (st_flipped_up and htf_latest.get('adx_plus_di', 0) > htf_latest.get('adx_minus_di', 0)) or \
                               (st_flipped_down and htf_latest.get('adx_minus_di', 0) > htf_latest.get('adx_plus_di', 0)):
                                htf_confluence_score += 1
                                mtf_reason += f" HTF ADX trend confirms."
                            else:
                                mtf_reason += f" HTF ADX trend not confirming."
                    # Add more HTF indicator checks here (e.g., RSI, MACD)
                    # elif additional_indicator == "RSI_STATE":
                    #    htf_rsi = htf_latest.get('rsi', 50)
                    #    if (st_flipped_up and htf_rsi > 50) or (st_flipped_down and htf_rsi < 50):
                    #        htf_confluence_score += 1
                    #        mtf_reason += f" HTF RSI confirms."

            if self.config.REQUIRED_CONFLUENCE and htf_confluence_score == 0: # If any required confluence is missed
                mtf_confluence = False
                return None, f"Multi-timeframe filter rejected signal. {mtf_reason}", 0
            elif htf_confluence_score > 0:
                signal_strength += htf_confluence_score # Add confluence score to total
                self.logger.debug(f"Multi-timeframe confluence confirmed: {mtf_reason}")

        # --- Price Action Confirmation (Candlestick Patterns) (Existing Feature & Snippet 7) ---
        pattern_confirmed = True
        pattern_name = None
        if self.config.PRICE_ACTION_CONFIRMATION_ENABLED:
            if st_flipped_up: # Look for bullish patterns
                pattern_name = self.candlestick_detector.detect_pattern(df, self.config.REQUIRED_BULLISH_PATTERNS)
                if not pattern_name:
                    pattern_confirmed = False
            elif st_flipped_down: # Look for bearish patterns
                pattern_name = self.candlestick_detector.detect_pattern(df, self.config.REQUIRED_BEARISH_PATTERNS)
                if not pattern_name:
                    pattern_confirmed = False

            if not pattern_confirmed:
                return None, "Candlestick pattern filter rejected signal.", 0
            else:
                # Apply pattern strength multiplier to signal strength (Snippet 7)
                signal_strength += int(round(1 * self.config.PATTERN_STRENGTH_MULTIPLIER))
                self.logger.debug(f"Candlestick pattern '{pattern_name}' confirmed signal with strength multiplier.")


        # --- Signal Generation & Scoring ---
        if st_flipped_up:
            reason_parts = ["BUY: Supertrend flipped UP"]
            if price_above_filter:
                signal_strength += 1
                reason_parts.append("Price > Ehlers Filter")
            if rsi_bullish:
                signal_strength += 1
                reason_parts.append(f"RSI({latest['rsi']:.1f}) > 52")
            if macd_bullish:
                signal_strength += 1
                reason_parts.append("MACD Hist > 0")
            if vwap_bullish: # Snippet 3
                signal_strength += 1
                reason_parts.append("Price > VWAP")
            
            if signal_strength >= self.config.MIN_SIGNAL_STRENGTH:
                return 'BUY', ", ".join(reason_parts), signal_strength

        if st_flipped_down:
            reason_parts = ["SELL: Supertrend flipped DOWN"]
            if price_below_filter:
                signal_strength += 1
                reason_parts.append("Price < Ehlers Filter")
            if rsi_bearish:
                signal_strength += 1
                reason_parts.append(f"RSI({latest['rsi']:.1f}) < 48")
            if macd_bearish:
                signal_strength += 1
                reason_parts.append("MACD Hist < 0")
            if vwap_bearish: # Snippet 3
                signal_strength += 1
                reason_parts.append("Price < VWAP")

            if signal_strength >= self.config.MIN_SIGNAL_STRENGTH:
                return 'SELL', ", ".join(reason_parts), signal_strength

        return None, "No clear scalping signal with sufficient strength.", signal_strength
"""
        },
        {
          "file_section": "EhlersSuperTrendBot.execute_trade_based_on_signal",
          "change_type": "modify_function",
          "description": "Adjust call to generate_signal and add check for MIN_SIGNAL_STRENGTH.",
          "code": """
    def execute_trade_based_on_signal(self, signal_type: str | None, reason: str, signal_strength: int):
        \"\"\"
        Execute trades based on the generated signal and current position state.
        Manages opening new positions, closing existing ones based on signal reversal,
        and updating stop losses (including trailing stops).
        
        Includes checks for:
        - Cumulative Loss Guard
        - Time-Based Trading Window
        - Max Concurrent Positions Limit
        - Funding Rate Avoidance
        - News Event Trading Pause
        - Signal Retracement Entry (initial placement)
        - Breakeven Stop Loss (monitoring)
        - Partial Take Profit (monitoring)
        \"\"\"
        # Global checks before any trade action
        if not self._cumulative_loss_guard():
            self.logger.warning("Cumulative loss limit reached. Skipping trade execution for this cycle.")
            return

        if not self._is_time_to_trade():
            self.logger.info("Outside allowed trading window. Skipping trade execution for this cycle.")
            return

        if self.config.NEWS_PAUSE_ENABLED:
            paused, pause_reason = self.news_calendar_manager.is_trading_paused()
            if paused:
                self.logger.info(f"Trading paused: {pause_reason}")
                return # Skip all trading actions

        # Fetch current market data (ticker for price)
        current_market_price = Decimal(str(self.market_data['close'].iloc[-1])) if not self.market_data.empty else Decimal('0.0')
        if current_market_price <= Decimal('0'):
            self.logger.warning("Could not retrieve current market price from kline data. Cannot execute trade based on signal.")
            return

        # Ensure we have valid instrument specifications for precision rounding
        specs = self.precision_manager.get_specs(self.config.SYMBOL)
        if not specs:
            self.logger.error(f"Instrument specifications not found for {self.config.SYMBOL}. Cannot execute trade.")
            return

        # FEATURE: Session-Based Volatility Filter (Snippet 7)
        current_atr_for_session_filter = Decimal(str(self.market_data['atr'].iloc[-1])) if 'atr' in self.market_data.columns else None
        session_ok, session_reason = self._is_session_active_and_volatile(current_market_price, current_atr_for_session_filter)
        if not session_ok:
            self.logger.info(f"Session filter rejected trade: {session_reason}")
            return


        # --- Trade Cooldown Check ---
        now_ts = time.time()
        effective_cooldown_sec = Decimal(str(self.config.SIGNAL_COOLDOWN_SEC)) # Base cooldown

        # FEATURE: Dynamic Signal Cooldown based on Volatility (Snippet 8)
        if self.config.DYNAMIC_COOLDOWN_ENABLED and not self.market_data.empty and 'atr' in self.market_data.columns:
            # Use the same volatility measure as adaptive indicators
            current_atr = Decimal(str(self.market_data['atr'].iloc[-1]))
            current_price = Decimal(str(self.market_data['close'].iloc[-1]))

            if current_price > Decimal('0'):
                avg_range_pct = current_atr / current_price
                if avg_range_pct >= Decimal(str(self.config.VOLATILITY_THRESHOLD_HIGH)):
                    effective_cooldown_sec *= Decimal(str(self.config.COOLDOWN_VOLATILITY_FACTOR_HIGH))
                    self.logger.debug(f"High volatility detected ({avg_range_pct*100:.2f}%). Reducing cooldown by {self.config.COOLDOWN_VOLATILITY_FACTOR_HIGH}x.")
                elif avg_range_pct <= Decimal(str(self.config.VOLATILITY_THRESHOLD_LOW)):
                    effective_cooldown_sec *= Decimal(str(self.config.COOLDOWN_VOLATILITY_FACTOR_LOW))
                    self.logger.debug(f"Low volatility detected ({avg_range_pct*100:.2f}%). Increasing cooldown by {self.config.COOLDOWN_VOLATILITY_FACTOR_LOW}x.")
                else:
                    self.logger.debug(f"Normal volatility ({avg_range_pct*100:.2f}%). Using default cooldown.")
            
            effective_cooldown_sec = max(Decimal('5'), effective_cooldown_sec) # Ensure a minimum cooldown

        if now_ts - self.last_trade_time < float(effective_cooldown_sec):
            self.logger.info(Fore.LIGHTBLACK_EX + f"Trade cooldown active ({effective_cooldown_sec:.1f}s). Skipping trade execution." + Style.RESET_ALL)
            return

        # --- Manage pending retracement orders ---
        # This handles cancelling old orders, actual fill is handled in `_process_websocket_message`
        self._manage_retracement_order(self.last_kline_ts)
        # If there's a pending retracement order, don't try to open new positions
        if self.pending_retracement_order:
            self.logger.info("A retracement order is pending. Not opening new positions until it's filled or cancelled.")
            return

        # --- State Management & Trade Execution ---
        latest_st_direction = self.market_data['supertrend_direction'].iloc[-1]

        # 1. Handle Closing Existing Positions on Reversal
        if self.position_active:
            perform_close = False
            if self.current_position_side == "Buy" and latest_st_direction == -1:
                self.logger.info("Exit Signal: Supertrend flipped DOWN while in a LONG position. Closing position.")
                perform_close = True
            elif self.current_position_side == "Sell" and latest_st_direction == 1:
                self.logger.info("Exit Signal: Supertrend flipped UP while in a SHORT position. Closing position.")
                perform_close = True

            # FEATURE: Proactive Funding Rate Exit (Snippet 9)
            if self.config.FUNDING_RATE_AVOIDANCE_ENABLED and self.config.FUNDING_RATE_PROACTIVE_EXIT_ENABLED:
                current_unrealized_pnl_pct = self.bot_state.unrealized_pnl_pct
                funding_is_punitive, funding_reason = self._is_funding_rate_avoidance_active(proactive_check=True)
                if funding_is_punitive and abs(current_unrealized_pnl_pct) < Decimal(str(self.config.FUNDING_RATE_PROACTIVE_EXIT_MIN_PROFIT_PCT)) * Decimal('100'):
                    self.logger.warning(Fore.YELLOW + f"Proactive Funding Rate Exit: {funding_reason}. Position not significantly profitable ({current_unrealized_pnl_pct:.2f}%). Closing position before funding." + Style.RESET_ALL)
                    perform_close = True


            # FEATURE: Time-Based Exit for Unprofitable Trades (Snippet 6) - Moved to _process_websocket_message for per-candle check.

            if perform_close:
                if self.close_position():
                    self.last_trade_time = now_ts
                return # Exit after closing, wait for next candle

            # If not closing, apply other position management features
            if not perform_close:
                # FEATURE: Multi-Tier Breakeven Stop Loss Activation (Snippet 10)
                self._manage_breakeven_stop_loss()

                # FEATURE: Partial Take Profit (Scaling Out)
                self._manage_partial_take_profit()

                # FEATURE: Trailing Stop Loss Updates (Dynamic Trailing or Ehlers ST Trailing)
                if self.config.TRAILING_STOP_PCT > 0 or self.config.EHLERS_ST_TRAILING_ENABLED:
                    # `get_positions` already fetches markPrice and updates internal state for trailing stop manager
                    # So we just need to ensure the trailing stop is set/active.
                    ehlers_st_line = Decimal(str(self.market_data['supertrend_line_value'].iloc[-1])) if not self.market_data.empty else None
                    self.trailing_stop_manager.update_trailing_stop(
                        symbol=self.config.SYMBOL,
                        current_price=current_market_price, # Pass latest market price
                        current_unrealized_pnl_pct=self.bot_state.unrealized_pnl_pct, # Pass for dynamic trailing
                        ehlers_st_line_value=ehlers_st_line, # Pass Ehlers ST line for Snippet 4
                        update_exchange=True
                    )
        # 2. Handle Opening New Positions
        if not self.position_active and signal_type in ['BUY', 'SELL']:
            if signal_strength < self.config.MIN_SIGNAL_STRENGTH: # Check signal strength (Snippet 1)
                self.logger.info(f"Signal strength ({signal_strength}) is below minimum required ({self.config.MIN_SIGNAL_STRENGTH}). Skipping trade.")
                return

            # FEATURE: Max Concurrent Positions Limit Check
            if len(self.all_open_positions) >= self.config.MAX_CONCURRENT_POSITIONS:
                self.logger.warning(f"Max concurrent positions limit ({self.config.MAX_CONCURRENT_POSITIONS}) reached. Cannot open new position for {self.config.SYMBOL}.")
                return

            # FEATURE: Funding Rate Avoidance (Perpetuals)
            if self._is_funding_rate_avoidance_active():
                self.logger.warning("Funding rate avoidance active. Skipping new position opening.")
                return

            trade_side = signal_type
            self.logger.info(f"Received {trade_side} signal. Reason: {reason}. Attempting to open {trade_side.lower()} position.")
            subprocess.run(["termux-toast", f"Signal: {trade_side} {self.config.SYMBOL}. Reason: {reason}"])

            # Calculate Stop Loss and Take Profit prices (with DTP)
            stop_loss_price, take_profit_price = self.calculate_trade_sl_tp(trade_side, current_market_price, self.market_data)

            # FEATURE: Volatility-Adjusted Position Sizing - pass current ATR (Snippet 5 robustness check)
            current_atr_for_sizing = Decimal(str(self.market_data['atr'].iloc[-1])) if 'atr' in self.market_data.columns else None

            # Calculate position size in base currency units
            position_qty = self.order_sizer.calculate_position_size_usd(
                symbol=self.config.SYMBOL,
                account_balance_usdt=self.account_balance_usdt,
                risk_percent=Decimal(str(self.config.RISK_PER_TRADE_PCT / 100)),
                entry_price=current_market_price,
                stop_loss_price=stop_loss_price,
                leverage=Decimal(str(self.config.LEVERAGE)),
                current_atr=current_atr_for_sizing # Pass ATR
            )

            if position_qty is not None and position_qty > Decimal('0'):
                order_type_to_place = self.config.ORDER_TYPE_ENUM
                entry_price_to_place = current_market_price # Default for market or if retracement not enabled

                # FEATURE: Signal Retracement Entry
                if self.config.RETRACEMENT_ENTRY_ENABLED:
                    order_type_to_place = OrderType[self.config.RETRACEMENT_ORDER_TYPE.upper()]
                    if trade_side == 'Buy':
                        entry_price_to_place = current_market_price * (Decimal('1') - Decimal(str(self.config.RETRACEMENT_PCT_FROM_CLOSE)))
                    else: # Sell
                        entry_price_to_place = current_market_price * (Decimal('1') + Decimal(str(self.config.RETRACEMENT_PCT_FROM_CLOSE)))

                    entry_price_to_place = self.precision_manager.round_price(self.config.SYMBOL, entry_price_to_place)
                    self.logger.info(f"Placing {order_type_to_place.value} order for retracement at {entry_price_to_place:.{self.bot_state.price_precision}f}.")

                order_result = self.place_order(
                    side=trade_side,
                    qty=position_qty,
                    order_type=order_type_to_place,
                    entry_price=entry_price_to_place if order_type_to_place == OrderType.LIMIT else None, # Only pass price for limit orders
                    stopLoss=stop_loss_price,
                    takeProfit=take_profit_price
                )

                if order_result:
                    if order_result.get('orderStatus') == 'Filled' or self.config.DRY_RUN:
                        # Update internal state based on order result (especially the filled price)
                        filled_price = Decimal(order_result.get('avgPrice', str(current_market_price)))
                        filled_qty = Decimal(order_result.get('cumExecQty', str(position_qty)))

                        self.position_active = True
                        self.current_position_side = trade_side
                        self.current_position_entry_price = filled_price
                        self.current_position_size = filled_qty
                        self.initial_position_qty = filled_qty # Store initial quantity for partial TP
                        self.last_trade_time = now_ts
                        self.last_signal = trade_side
                        self.breakeven_activated[self.config.SYMBOL] = False # Reset single-tier breakeven status for new position
                        self.breakeven_tier_activated[self.config.SYMBOL] = -1 # Reset multi-tier breakeven status for new position (Snippet 10)
                        self.partial_tp_targets_hit[self.config.SYMBOL] = dict.fromkeys(range(len(self.config.PARTIAL_TP_TARGETS)), False) # Reset partial TP status
                        self.pending_retracement_order = None # Clear pending retracement order
                        self.open_trade_kline_ts = self.last_kline_ts # Set timestamp for time-based exit (Snippet 6)

                        self.logger.info(f"{trade_side} order placed and confirmed filled. Entry: {filled_price}, Qty: {filled_qty}.")

                        # Update BotState with new position
                        with self.bot_state.lock:
                            self.bot_state.open_position_qty = filled_qty
                            self.bot_state.open_position_side = trade_side
                            self.bot_state.open_position_entry_price = filled_price
                            self.bot_state.unrealized_pnl = Decimal('0.0') # Start with 0 PnL
                            self.bot_state.unrealized_pnl_pct = Decimal('0.0')

                        # Initialize Ehlers ST trailing stop if enabled (Snippet 4)
                        if self.config.EHLERS_ST_TRAILING_ENABLED:
                            ehlers_st_line = Decimal(str(self.market_data['supertrend_line_value'].iloc[-1]))
                            self.trailing_stop_manager.initialize_trailing_stop(
                                symbol=self.config.SYMBOL,
                                position_side=trade_side,
                                entry_price=filled_price,
                                current_price=current_market_price,
                                trail_percent=0.0, # Not used for Ehlers ST trailing
                                activation_percent=0.0,
                                ehlers_st_trailing_enabled=True,
                                ehlers_st_line_value=ehlers_st_line
                            )

                    elif order_result.get('orderStatus') in ('New', 'Created') and self.config.RETRACEMENT_ENTRY_ENABLED:
                        # If retracement order is pending, store its details
                        self.pending_retracement_order = {
                            'orderId': order_result['orderId'],
                            'side': trade_side,
                            'qty': position_qty,
                            'price': entry_price_to_place,
                            'time_placed_kline_ts': self.last_kline_ts
                        }
                        self.logger.info(f"Retracement limit order {order_result['orderId']} placed and pending fill.")
                    else:
                        self.logger.error(f"Failed to place {trade_side} order.")
                else:
                    self.logger.error(f"Failed to place {trade_side} order.")
            else:
                self.logger.warning(f"Could not calculate a valid position size for the {trade_side} signal. Skipping order placement.")
        else:
            self.logger.info(Fore.WHITE + "No active position and no new signal to act on." + Style.RESET_ALL)
"""
        },
        {
          "file_section": "EhlersSuperTrendBot._process_websocket_message",
          "change_type": "modify_function",
          "description": "Adjust call to generate_signal and execute_trade_based_on_signal to pass signal strength.",
          "code": """
    def _process_websocket_message(self, msg: dict[str, Any]):
        \"\"\"
        The core incantation, triggered by each new confirmed k-line,
        where market data is transformed into signals and actions.
        \"\"\"
        if self.stop_event.is_set():
            return

        if "topic" in msg and str(msg["topic"]).startswith(f"kline.{self.config.TIMEFRAME}.{self.config.SYMBOL}"):
            kline = msg['data'][0]
            if not kline['confirm']:
                return # Only process confirmed (closed) candles

            ts = int(kline['start'])
            if ts <= self.last_kline_ts:
                return # Skip duplicate or old candle data
            self.last_kline_ts = ts

            self.logger.info(Fore.LIGHTMAGENTA_EX + f"--- New Confirmed Candle [{datetime.fromtimestamp(ts/1000)}] ---" + Style.RESET_ALL)

            # Update data and state
            self._update_market_data_and_state()

            # Manage time-based exit for unprofitable trades (Snippet 6)
            self._manage_time_based_exit(ts)

            # After updating, generate signal and execute trade
            if not self.market_data.empty:
                signal, reason, signal_strength = self.generate_signal(self.market_data) # Updated call signature for Snippet 1
                self.logger.info(Fore.WHITE + f"Signal: {signal or 'NONE'} (Strength: {signal_strength}) | Reason: {reason}" + Style.RESET_ALL)
                self.get_positions() # Refresh position state before trading
                self.execute_trade_based_on_signal(signal, reason, signal_strength) # Updated call signature for Snippet 1
"""
        }
      ]
    },
    {
      "id": 2,
      "name": "Dynamic Take Profit with ATR Quality Check",
      "description": "Enhances the existing Dynamic Take Profit by adding a minimum ATR threshold. If the ATR is too low, indicating very low volatility, the bot falls back to a fixed Take Profit percentage to prevent excessively small and unprofitable TP targets.",
      "config_changes": [
        {"key": "MIN_ATR_TP_THRESHOLD_PCT", "type": "float", "default": 0.0005, "description": "Minimum ATR (as a percentage of price) required for dynamic TP. Below this, fixed TP is used."}
      ],
      "code_changes": [
        {
          "file_section": "Config class",
          "change_type": "add_field",
          "code": "    MIN_ATR_TP_THRESHOLD_PCT: float = field(default=0.0005) # 0.05%"
        },
        {
          "file_section": "Config.__post_init__",
          "change_type": "add_load_env",
          "code": "        self.MIN_ATR_TP_THRESHOLD_PCT = float(os.getenv(\"MIN_ATR_TP_THRESHOLD_PCT\", self.MIN_ATR_TP_THRESHOLD_PCT))"
        },
        {
          "file_section": "EhlersSuperTrendBot.__init__",
          "change_type": "add_log",
          "code": "        self.logger.info(f\"  Min ATR for Dynamic TP: {config.MIN_ATR_TP_THRESHOLD_PCT*100:.2f}%\")"
        },
        {
          "file_section": "EhlersSuperTrendBot.calculate_trade_sl_tp",
          "change_type": "modify_function",
          "description": "Add ATR quality check before applying dynamic TP.",
          "code": """
    def calculate_trade_sl_tp(self, side: str, entry_price: Decimal, df: pd.DataFrame) -> tuple[Decimal, Decimal]:
        \"\"\"
        Calculates Stop Loss and Take Profit levels based on fixed percentages,
        or dynamically using ATR if enabled, with an ATR quality check.
        Returns (stop_loss_price, take_profit_price).
        \"\"\"
        sl_pct_decimal = Decimal(str(self.config.STOP_LOSS_PCT))
        tp_pct_decimal = Decimal(str(self.config.TAKE_PROFIT_PCT)) # Default to fixed

        # FEATURE: Dynamic Take Profit (DTP) via ATR with quality check (Snippet 2)
        if self.config.DYNAMIC_TP_ENABLED and not df.empty and 'atr' in df.columns:
            atr_value = Decimal(str(df['atr'].iloc[-1])) # Use ATR from current timeframe
            
            # ATR Quality Check: If ATR is too low, use fixed TP (Snippet 2)
            if entry_price > Decimal('0') and (atr_value / entry_price) < Decimal(str(self.config.MIN_ATR_TP_THRESHOLD_PCT)):
                self.logger.warning(f"Current ATR ({atr_value:.4f}) is too low relative to price for Dynamic TP (below {self.config.MIN_ATR_TP_THRESHOLD_PCT*100:.2f}%). Falling back to fixed TP {self.config.TAKE_PROFIT_PCT*100:.2f}%.")
                tp_pct_decimal = Decimal(str(self.config.TAKE_PROFIT_PCT))
            elif atr_value > Decimal('0'):
                # Calculate TP in price units based on ATR
                dynamic_tp_price_units = atr_value * Decimal(str(self.config.ATR_TP_MULTIPLIER))

                # Convert to percentage relative to entry price
                dynamic_tp_pct = dynamic_tp_price_units / entry_price

                # Clamp between min and max TP percentages
                tp_pct_decimal = max(Decimal(str(self.config.MIN_TAKE_PROFIT_PCT)),
                                     min(dynamic_tp_pct, Decimal(str(self.config.MAX_TAKE_PROFIT_PCT))))
                self.logger.debug(f"Dynamic TP calculated: ATR={atr_value:.4f}, Price Units={dynamic_tp_price_units:.4f}, Raw PCT={dynamic_tp_pct:.4f}, Final PCT={tp_pct_decimal:.4f}")
            else:
                self.logger.warning("ATR value is zero or not available for Dynamic TP. Using fixed TP percentage.")
                tp_pct_decimal = Decimal(str(self.config.TAKE_PROFIT_PCT))

        if side == 'Buy':
            stop_loss = entry_price * (Decimal('1') - sl_pct_decimal)
            take_profit = entry_price * (Decimal('1') + tp_pct_decimal)
        else: # Sell
            stop_loss = entry_price * (Decimal('1') + sl_pct_decimal)
            take_profit = entry_price * (Decimal('1') - tp_pct_decimal)

        # Round to appropriate price precision
        stop_loss = self.precision_manager.round_price(self.config.SYMBOL, stop_loss)
        take_profit = self.precision_manager.round_price(self.config.SYMBOL, take_profit)

        self.logger.info(Fore.LIGHTMAGENTA_EX + f"Calculated SL/TP: SL=${stop_loss:.{self.bot_state.price_precision}f}, TP=${take_profit:.{self.bot_state.price_precision}f}" + Style.RESET_ALL)
        return stop_loss, take_profit
"""
        }
      ]
    },
    {
      "id": 3,
      "name": "VWAP as Additional Entry Confirmation",
      "description": "Integrates Volume-Weighted Average Price (VWAP) as an additional filter for signal confirmation. For buy signals, price should be above VWAP; for sell signals, price should be below VWAP, indicating alignment with institutional flow.",
      "config_changes": [
        {"key": "VWAP_CONFIRMATION_ENABLED", "type": "bool", "default": false, "description": "Enable/disable VWAP confirmation for signals."},
        {"key": "VWAP_WINDOW", "type": "int", "default": 20, "description": "Number of periods to calculate VWAP over."}
      ],
      "code_changes": [
        {
          "file_section": "Config class",
          "change_type": "add_field",
          "code": """    VWAP_CONFIRMATION_ENABLED: bool = field(default=False)
    VWAP_WINDOW: int = field(default=20)"""
        },
        {
          "file_section": "Config.__post_init__",
          "change_type": "add_load_env",
          "code": """        self.VWAP_CONFIRMATION_ENABLED = os.getenv("VWAP_CONFIRMATION_ENABLED", str(self.VWAP_CONFIRMATION_ENABLED)).lower() in ['true', '1', 't']
        self.VWAP_WINDOW = int(os.getenv("VWAP_WINDOW", self.VWAP_WINDOW))"""
        },
        {
          "file_section": "EhlersSuperTrendBot.__init__",
          "change_type": "add_log",
          "code": """        self.logger.info(f"  VWAP Confirmation: {config.VWAP_CONFIRMATION_ENABLED}, Window: {config.VWAP_WINDOW}")"""
        },
        {
          "file_section": "EhlersSuperTrendBot.calculate_indicators",
          "change_type": "modify_function",
          "description": "Add VWAP calculation to the DataFrame.",
          "code": """
    def calculate_indicators(self, df: pd.DataFrame, is_higher_timeframe: bool = False) -> pd.DataFrame:
        \"\"\"
        Applies all required indicators to the DataFrame,
        weaving complex patterns from the raw market energies with enhanced robustness.
        FEATURE: Adaptive Indicator Parameters (Volatility-Based)
        \"\"\"

        # Determine indicator parameters dynamically if enabled
        ehlers_length = self.config.EHLERS_LENGTH
        rsi_window = self.config.RSI_WINDOW

        # FEATURE: Adaptive Indicator Parameter Smoothing (Snippet 10)
        # Apply smoothing to the volatility measure before adjusting indicator parameters
        volatility_measure_window = self.config.VOLATILITY_MEASURE_WINDOW
        if self.config.ADAPTIVE_INDICATORS_ENABLED and not is_higher_timeframe:
            if len(df) >= volatility_measure_window:
                # Calculate raw volatility using ATR as a percentage of price
                atr_series_raw = ta.volatility.AverageTrueRange(
                    high=df['high'],
                    low=df['low'],
                    close=df['close'],
                    window=volatility_measure_window,
                    fillna=True
                ).average_true_range()
                
                # Smooth the ATR to reduce whipsaws in adaptive parameters (Snippet 10)
                smoothed_atr = atr_series_raw.ewm(span=self.config.ADAPTIVE_PARAM_SMOOTHING_WINDOW, adjust=False).mean()
                
                current_volatility = smoothed_atr.iloc[-1] / df['close'].iloc[-1] if df['close'].iloc[-1] > 0 else 0

                if current_volatility >= Decimal(str(self.config.VOLATILITY_THRESHOLD_HIGH)):
                    ehlers_length = self.config.EHLERS_LENGTH_HIGH_VOL
                    rsi_window = self.config.RSI_WINDOW_HIGH_VOL
                    self.logger.debug(f"High volatility detected ({current_volatility:.4f}%). Adapting Ehlers Length to {ehlers_length}, RSI Window to {rsi_window}.")
                elif current_volatility <= Decimal(str(self.config.VOLATILITY_THRESHOLD_LOW)):
                    ehlers_length = self.config.EHLERS_LENGTH_LOW_VOL
                    rsi_window = self.config.RSI_WINDOW_LOW_VOL
                    self.logger.debug(f"Low volatility detected ({current_volatility:.4f}%). Adapting Ehlers Length to {ehlers_length}, RSI Window to {rsi_window}.")
                else:
                    self.logger.debug(f"Normal volatility ({current_volatility:.4f}%). Using default Ehlers Length {ehlers_length}, RSI Window {rsi_window}.")
            else:
                self.logger.warning(f"Not enough data for adaptive indicators (need {volatility_measure_window} periods). Using default parameters.")

        # Update bot_state with adaptive parameters
        if not is_higher_timeframe:
            with self.bot_state.lock:
                self.bot_state.adaptive_ehlers_length = ehlers_length
                self.bot_state.adaptive_rsi_window = rsi_window
            self.current_ehlers_length = ehlers_length
            self.current_rsi_window = rsi_window


        # Ensure sufficient data for all indicators
        min_len = max(ehlers_length + self.config.SMOOTHING_LENGTH + 5,
                      self.config.EHLERS_ST_LENGTH + 5,
                      self.config.MACD_SLOW + self.config.MACD_SIGNAL + 5,
                      rsi_window + 5,
                      self.config.ADX_WINDOW + 5,
                      self.config.ATR_TP_WINDOW + 5, # For Dynamic TP
                      self.config.VWAP_WINDOW + 5 if self.config.VWAP_CONFIRMATION_ENABLED else 0, # For VWAP (Snippet 3)
                      self.config.ADAPTIVE_PARAM_SMOOTHING_WINDOW + 5 if self.config.ADAPTIVE_INDICATORS_ENABLED else 0, # For adaptive smoothing (Snippet 10)
                      60) # A reasonable minimum for most TA indicators

        if len(df) < min_len:
            self.logger.warning(Fore.YELLOW + f"Not enough data for indicators (have {len(df)}, need {min_len}). Returning DataFrame with NaNs for indicators." + Style.RESET_ALL)
            # Ensure indicator columns exist and are filled with NaN if data is insufficient
            for col in ["ehlers_trend", "ehlers_filter", "supertrend_line_value", "supertrend_direction", "rsi", "macd", "macd_signal", "macd_diff", "adx", "adx_plus_di", "adx_minus_di", "atr", "vwap"]: # Added vwap
                if col not in df.columns:
                    df[col] = np.nan
            return df

        # Ensure numeric types for calculations
        close = df['close'].astype(float).values
        high = df['high'].astype(float).values
        low = df['low'].astype(float).values
        volume = df['volume'].astype(float).values # Need volume for VWAP (Snippet 3)

        # Ehlers Adaptive Trend: Sensing the hidden currents (custom filter from original bot)
        a1 = np.exp(-np.pi * np.sqrt(2) / float(self.config.SMOOTHING_LENGTH))
        b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / float(self.config.SMOOTHING_LENGTH))
        c2, c3, c1 = b1, -a1 * a1, 1 - b1 + a1 * a1

        filt = np.zeros(len(close), dtype=float)
        # Handle initial values for filt to avoid index errors or NaN propagation
        if len(close) > 0:
            filt[0] = close[0]
        if len(close) > 1:
            filt[1] = (c1 * (close[1] + close[0]) / 2.0) + (c2 * filt[0])
        for i in range(2, len(close)): # Start from 2 as 0 and 1 are handled
            filt[i] = c1 * (close[i] + close[i-1]) / 2.0 + c2 * filt[i-1] + c3 * filt[i-2]
        df['ehlers_filter'] = pd.Series(filt, index=df.index) # Store Ehlers filter for UI

        vol_series = pd.Series(high - low, index=df.index)
        # Use min_periods to allow calculation with less than full window at start
        volatility = vol_series.rolling(ehlers_length, min_periods=max(1, ehlers_length//2)).std().ewm(span=self.config.SMOOTHING_LENGTH, adjust=False).mean()

        raw_trend = np.where(df['close'] > (filt + (volatility * self.config.SENSITIVITY)), 1,\
                             np.where(df['close'] < (filt - (volatility * self.config.SENSITIVITY)), -1, np.nan))
        df['ehlers_trend'] = pd.Series(raw_trend, index=df.index).ffill() # Fill NaNs forward

        # --- SuperTrend (Manual Implementation) ---
        atr = ta.volatility.AverageTrueRange(
            high=df['high'],
            low=df['low'],
            close=df['close'],
            window=self.config.EHLERS_ST_LENGTH,
            fillna=True
        ).average_true_range()

        basic_upper = (df['high'] + df['low']) / 2 + self.config.EHLERS_ST_MULTIPLIER * atr
        basic_lower = (df['high'] + df['low']) / 2 - self.config.EHLERS_ST_MULTIPLIER * atr

        final_upper = pd.Series(np.nan, index=df.index)
        final_lower = pd.Series(np.nan, index=df.index)
        supertrend_line = pd.Series(np.nan, index=df.index)

        if not df.empty:
            final_upper.iloc[0] = basic_upper.iloc[0]
            final_lower.iloc[0] = basic_lower.iloc[0]
            supertrend_line.iloc[0] = final_lower.iloc[0]

            for i in range(1, len(df)):
                if basic_upper.iloc[i] < final_upper.iloc[i-1] or df['close'].iloc[i-1] > final_upper.iloc[i-1]:
                    final_upper.iloc[i] = basic_upper.iloc[i]
                else:
                    final_upper.iloc[i] = final_upper.iloc[i-1]

                if basic_lower.iloc[i] > final_lower.iloc[i-1] or df['close'].iloc[i-1] < final_lower.iloc[i-1]:
                    final_lower.iloc[i] = basic_lower.iloc[i]
                else:
                    final_lower.iloc[i] = final_lower.iloc[i-1]

                if supertrend_line.iloc[i-1] == final_upper.iloc[i-1] and df['close'].iloc[i] > final_upper.iloc[i]:
                    supertrend_line.iloc[i] = final_lower.iloc[i]
                elif (supertrend_line.iloc[i-1] == final_upper.iloc[i-1] and df['close'].iloc[i] <= final_upper.iloc[i]) or (supertrend_line.iloc[i-1] == final_lower.iloc[i-1] and df['close'].iloc[i] < final_lower.iloc[i]):
                    supertrend_line.iloc[i] = final_upper.iloc[i]
                elif supertrend_line.iloc[i-1] == final_lower.iloc[i-1] and df['close'].iloc[i] >= final_lower.iloc[i]:
                    supertrend_line.iloc[i] = final_lower.iloc[i]

        df['supertrend_line_value'] = supertrend_line
        df['supertrend_direction'] = np.where(df['close'] > df['supertrend_line_value'], 1, -1)

        # Additional Filters - RSI: Measuring the momentum's fervor
        rsi = ta.momentum.RSIIndicator(df['close'], window=rsi_window, fillna=True)
        df['rsi'] = rsi.rsi()

        # Additional Filters - MACD: Unveiling the convergence and divergence of forces
        macd = ta.trend.MACD(df['close'], window_fast=self.config.MACD_FAST, window_slow=self.config.MACD_SLOW, window_sign=self.config.MACD_SIGNAL, fillna=True)
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['macd_diff'] = macd.macd_diff()

        # ADX: Trend Strength and Direction
        adx_indicator = ta.trend.ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=self.config.ADX_WINDOW, fillna=True)
        df['adx'] = adx_indicator.adx()
        df['adx_plus_di'] = adx_indicator.adx_pos()
        df['adx_minus_di'] = adx_indicator.adx_neg()

        # FEATURE: ATR for Dynamic TP and Volatility Sizing
        df['atr'] = ta.volatility.AverageTrueRange(
            high=df['high'],
            low=df['low'],
            close=df['close'],
            window=self.config.ATR_TP_WINDOW if not is_higher_timeframe else self.config.VOLATILITY_WINDOW, # Use ATR_TP_WINDOW for primary, VOLATILITY_WINDOW for sizing
            fillna=True
        ).average_true_range()

        # FEATURE: VWAP as Additional Entry Confirmation (Snippet 3)
        if self.config.VWAP_CONFIRMATION_ENABLED:
            if len(df) >= self.config.VWAP_WINDOW:
                # Calculate typical price (H+L+C)/3
                typical_price = (df['high'] + df['low'] + df['close']) / 3
                # Calculate VWAP
                df['vwap'] = (typical_price * df['volume']).rolling(self.config.VWAP_WINDOW, min_periods=max(1, self.config.VWAP_WINDOW//2)).sum() / df['volume'].rolling(self.config.VWAP_WINDOW, min_periods=max(1, self.config.VWAP_WINDOW//2)).sum()
                df['vwap'].fillna(method='ffill', inplace=True) # Fill initial NaNs
            else:
                df['vwap'] = np.nan
                self.logger.warning(f"Not enough data for VWAP (need {self.config.VWAP_WINDOW} periods). VWAP column will contain NaNs.")


        # Drop rows where indicators are NaN (remove initial NaN rows, after fillna)
        required_indicator_cols = ['ehlers_trend', 'ehlers_filter', 'supertrend_direction', 'supertrend_line_value', 'rsi', 'macd', 'macd_signal', 'macd_diff', 'adx', 'adx_plus_di', 'adx_minus_di', 'atr']
        if self.config.VWAP_CONFIRMATION_ENABLED:
            required_indicator_cols.append('vwap') # Add VWAP to required for dropna
        df.dropna(subset=required_indicator_cols, inplace=True)

        if df.empty:
            self.logger.warning("All rows dropped due to NaN indicators. Cannot proceed.")
            return pd.DataFrame()

        self.logger.debug(f"Ehlers indicators calculated. DataFrame shape: {df.shape}")
        return df
"""
        }
      ]
    },
    {
      "id": 4,
      "name": "Trailing Stop based on Ehlers Supertrend Line",
      "description": "Instead of a fixed percentage, the stop loss dynamically trails the Ehlers Supertrend line. This makes the trailing stop more adaptive to market structure and volatility, potentially locking in profits more effectively during strong trends.",
      "config_changes": [
        {"key": "EHLERS_ST_TRAILING_ENABLED", "type": "bool", "default": false, "description": "Enable/disable trailing stop based on Ehlers Supertrend line. Overrides fixed TRAILING_STOP_PCT."},
        {"key": "EHLERS_ST_TRAILING_OFFSET_PCT", "type": "float", "default": 0.001, "description": "Small buffer percentage from the Ehlers Supertrend line for the trailing stop."}
      ],
      "code_changes": [
        {
          "file_section": "Config class",
          "change_type": "add_field",
          "code": """    EHLERS_ST_TRAILING_ENABLED: bool = field(default=False)
    EHLERS_ST_TRAILING_OFFSET_PCT: float = field(default=0.001)"""
        },
        {
          "file_section": "Config.__post_init__",
          "change_type": "add_load_env",
          "code": """        self.EHLERS_ST_TRAILING_ENABLED = os.getenv("EHLERS_ST_TRAILING_ENABLED", str(self.EHLERS_ST_TRAILING_ENABLED)).lower() in ['true', '1', 't']
        self.EHLERS_ST_TRAILING_OFFSET_PCT = float(os.getenv("EHLERS_ST_TRAILING_OFFSET_PCT", self.EHLERS_ST_TRAILING_OFFSET_PCT))"""
        },
        {
          "file_section": "EhlersSuperTrendBot.__init__",
          "change_type": "add_log",
          "code": """        self.logger.info(f"  Ehlers ST Trailing: {config.EHLERS_ST_TRAILING_ENABLED}, Offset: {config.EHLERS_ST_TRAILING_OFFSET_PCT*100:.2f}%")"""
        },
        {
          "file_section": "TrailingStopManager.__init__",
          "change_type": "modify_function",
          "description": "Adjust TrailingStopManager to store a flag for Ehlers ST trailing.",
          "code": """
class TrailingStopManager:
    \"\"\"
    Manage trailing stop losses by setting Bybit's native trailing stop (`callbackRate`)
    or by dynamically updating a fixed stop loss based on indicators.
    \"\"\"
    def __init__(self, bybit_session: HTTP, precision_manager: PrecisionManager, logger: logging.Logger, api_call_wrapper: Any, config: Config):
        self.session = bybit_session
        self.precision = precision_manager
        self.logger = logger
        self.api_call = api_call_wrapper # Reference to the bot's api_call method
        self.config = config # Added config for dynamic trailing
        # Stores active trailing stop info: {symbol: {'side': 'Buy'/'Sell', 'trail_percent': Decimal, 'ehlers_st_trailing': bool, 'current_sl': Decimal}}
        self.active_trailing_stops: dict[str, dict] = {}
        # Store current PnL for dynamic trailing stop logic
        self.current_unrealized_pnl_pct: dict[str, Decimal] = {}
"""
        },
        {
          "file_section": "TrailingStopManager.initialize_trailing_stop",
          "change_type": "modify_function",
          "description": "Modify initialize_trailing_stop to handle Ehlers ST trailing.",
          "code": """
    def initialize_trailing_stop(
        self,
        symbol: str,
        position_side: str,
        entry_price: Decimal,
        current_price: Decimal,
        trail_percent: float, # Pass as percentage (e.g., 0.5 for 0.5%)
        activation_percent: float, # Not directly used by Bybit's callbackRate, but kept for consistency
        ehlers_st_trailing_enabled: bool = False, # New parameter for Snippet 4
        ehlers_st_line_value: Decimal | None = None # New parameter for Snippet 4
    ) -> bool:
        \"\"\"
        Initialize trailing stop for a position using Bybit's callbackRate or
        set an initial fixed SL if Ehlers ST trailing is enabled.
        Returns True if successful, False otherwise.
        \"\"\"
        specs = self.precision.get_specs(symbol)
        if not specs:
            self.logger.error(f"Cannot initialize trailing stop for {symbol}: Specs not found.")
            return False

        if specs.category == 'spot':
            self.logger.debug(f"Trailing stops are not applicable for spot category {symbol}. Skipping initialization.")
            return False

        if ehlers_st_trailing_enabled and ehlers_st_line_value is not None:
            # For Ehlers ST trailing, we set a fixed SL first, then update it.
            # Bybit's callbackRate is not suitable for dynamic indicator trailing without manual updates.
            # We will set the initial SL based on the Ehlers ST line.
            stop_loss_price = Decimal('0')
            offset_value = ehlers_st_line_value * Decimal(str(self.config.EHLERS_ST_TRAILING_OFFSET_PCT))

            if position_side == 'Buy':
                stop_loss_price = ehlers_st_line_value - offset_value
            else: # Sell
                stop_loss_price = ehlers_st_line_value + offset_value
            
            stop_loss_price = self.precision.round_price(symbol, stop_loss_price)

            self.logger.info(f"Setting initial Ehlers ST trailing SL for {symbol} ({position_side}) at: ${stop_loss_price:.{self.precision.get_decimal_places(symbol)[0]}f}")
            try:
                response = self.api_call(
                    self.session.set_trading_stop,
                    category=specs.category,
                    symbol=symbol,
                    side=position_side,
                    stopLoss=str(stop_loss_price),
                    tpslMode='Full' # Setting SL will override callbackRate if already present
                )
                if response is not None:
                    self.active_trailing_stops[symbol] = {
                        'side': position_side,
                        'trail_percent': Decimal('0'), # Not using callbackRate in this mode
                        'ehlers_st_trailing': True,
                        'current_sl': stop_loss_price # Store current SL
                    }
                    self.logger.info(f"Successfully set initial Ehlers ST trailing SL for {symbol} at ${stop_loss_price:.{self.precision.get_decimal_places(symbol)[0]}f}.")
                    return True
                else:
                    self.logger.error(f"Failed to set initial Ehlers ST trailing SL for {symbol}: API call wrapper returned None.")
                    return False
            except Exception as e:
                self.logger.error(f"Exception setting initial Ehlers ST trailing SL for {symbol}: {e}", exc_info=True)
                return False
        else:
            # Original logic for Bybit's callbackRate
            trail_rate_str = str(trail_percent)

            try:
                response = self.api_call(
                    self.session.set_trading_stop,
                    category=specs.category,
                    symbol=symbol,
                    side=position_side, # Required for unified account
                    callbackRate=trail_rate_str
                )

                if response is not None:
                    self.active_trailing_stops[symbol] = {
                        'side': position_side,
                        'trail_percent': Decimal(str(trail_percent)),
                        'ehlers_st_trailing': False,
                        'current_sl': Decimal('0') # Not applicable for callbackRate
                    }
                    self.logger.info(f"Successfully set trailing stop for {symbol} ({position_side}) with callbackRate: {trail_rate_str}%")
                    return True
                else:
                    self.logger.error(f"Failed to set trailing stop for {symbol}: API call wrapper returned None.")
                    return False

            except Exception as e:
                self.logger.error(f"Exception setting trailing stop for {symbol}: {e}", exc_info=True)
                return False
"""
        },
        {
          "file_section": "TrailingStopManager.update_trailing_stop",
          "change_type": "modify_function",
          "description": "Modify update_trailing_stop to handle Ehlers ST trailing.",
          "code": """
    def update_trailing_stop(
        self,
        symbol: str,
        current_price: Decimal,
        current_unrealized_pnl_pct: Decimal,
        ehlers_st_line_value: Decimal | None = None, # New parameter for Snippet 4
        update_exchange: bool = True
    ) -> bool:
        \"\"\"
        Re-confirms or re-sets the trailing stop on the exchange if `update_exchange` is True.
        For Bybit's native `callbackRate`, this usually means ensuring it's still active.
        If Ehlers ST trailing is enabled, it updates the fixed stop loss.
        \"\"\"
        if symbol not in self.active_trailing_stops:
            return False # No active trailing stop to update

        self.current_unrealized_pnl_pct[symbol] = current_unrealized_pnl_pct

        if not update_exchange:
            self.logger.debug(f"Internal trailing stop check for {symbol}: current price {current_price}.")
            return False # No exchange update requested

        ts_info = self.active_trailing_stops[symbol]
        specs = self.precision.get_specs(symbol)
        if not specs:
            self.logger.error(f"Cannot update trailing stop for {symbol}: Specs not found.")
            return False

        if ts_info.get('ehlers_st_trailing', False) and ehlers_st_line_value is not None:
            # Ehlers Supertrend Trailing Logic (Snippet 4)
            stop_loss_price = Decimal('0')
            offset_value = ehlers_st_line_value * Decimal(str(self.config.EHLERS_ST_TRAILING_OFFSET_PCT))

            if ts_info['side'] == 'Buy':
                # For a long position, SL should be below price and below ST line
                stop_loss_price = ehlers_st_line_value - offset_value
                # Ensure SL never moves down once in profit (optional, but good practice)
                if ts_info['current_sl'] > stop_loss_price: # If current SL is higher (worse for Buy), don't move it down
                    stop_loss_price = ts_info['current_sl']
            else: # Sell
                # For a short position, SL should be above price and above ST line
                stop_loss_price = ehlers_st_line_value + offset_value
                # Ensure SL never moves up once in profit
                if ts_info['current_sl'] < stop_loss_price: # If current SL is lower (worse for Sell), don't move it up
                    stop_loss_price = ts_info['current_sl']
            
            stop_loss_price = self.precision.round_price(symbol, stop_loss_price)

            # Only update if the calculated SL is better (tighter) than the current one
            current_exchange_sl = self.active_trailing_stops[symbol].get('current_sl', Decimal('0'))

            should_update = False
            if ts_info['side'] == 'Buy' and stop_loss_price > current_exchange_sl: # SL should move up
                should_update = True
            elif ts_info['side'] == 'Sell' and stop_loss_price < current_exchange_sl: # SL should move down
                should_update = True
            elif current_exchange_sl == Decimal('0'): # No SL currently set, or first update
                should_update = True

            if should_update:
                try:
                    self.logger.info(f"Updating Ehlers ST trailing SL for {symbol} ({ts_info['side']}) from ${current_exchange_sl:.{self.precision.get_decimal_places(symbol)[0]}f} to ${stop_loss_price:.{self.precision.get_decimal_places(symbol)[0]}f}.")
                    response = self.api_call(
                        self.session.set_trading_stop,
                        category=specs.category,
                        symbol=symbol,
                        side=ts_info['side'],
                        stopLoss=str(stop_loss_price),
                        tpslMode='Partial' # Allow other TP to remain
                    )
                    if response is not None:
                        self.active_trailing_stops[symbol]['current_sl'] = stop_loss_price
                        return True
                    else:
                        self.logger.error(f"Failed to update Ehlers ST trailing SL for {symbol}: API call wrapper returned None.")
                        return False
                except Exception as e:
                    self.logger.error(f"Exception updating Ehlers ST trailing SL for {symbol}: {e}", exc_info=True)
                    return False
            else:
                self.logger.debug(f"Ehlers ST trailing SL for {symbol} not improved. Current: ${current_exchange_sl:.{self.precision.get_decimal_places(symbol)[0]}f}, Calculated: ${stop_loss_price:.{self.precision.get_decimal_places(symbol)[0]}f}.")
                return True # Considered successful if no update needed
        else:
            # Original logic for Bybit's callbackRate and Dynamic Trailing (Existing Feature)
            effective_trail_pct = Decimal(str(self.config.TRAILING_STOP_PCT)) * Decimal('100') # Default from config

            if self.config.DYNAMIC_TRAILING_ENABLED:
                sorted_tiers = sorted(self.config.TRAILING_PROFIT_TIERS, key=lambda x: x['profit_pct_trigger'], reverse=True)
                for tier in sorted_tiers:
                    if current_unrealized_pnl_pct >= Decimal(str(tier['profit_pct_trigger'])) * Decimal('100'):
                        effective_trail_pct = Decimal(str(tier['new_trail_pct'])) * Decimal('100')
                        self.logger.debug(f"Dynamic Trailing: PnL {current_unrealized_pnl_pct:.2f}% reached tier {tier['profit_pct_trigger']*100:.2f}%. New trail: {effective_trail_pct:.2f}%")
                        break

            current_ts_info = self.active_trailing_stops.get(symbol)
            if current_ts_info and effective_trail_pct == current_ts_info['trail_percent']:
                self.logger.debug(f"Trailing stop for {symbol} already at desired effective rate ({effective_trail_pct:.2f}%). No update needed.")
                return True

            ts_info['trail_percent'] = effective_trail_pct
            return self.initialize_trailing_stop(
                symbol=symbol,
                position_side=ts_info['side'],
                entry_price=Decimal('0'),
                current_price=current_price,
                trail_percent=float(effective_trail_pct),
                activation_percent=float(effective_trail_pct),
                ehlers_st_trailing_enabled=False # Explicitly false for callbackRate mode
            )
"""
        },
        {
          "file_section": "EhlersSuperTrendBot.execute_trade_based_on_signal",
          "change_type": "modify_function",
          "description": "Adjust call to TrailingStopManager.initialize_trailing_stop and update_trailing_stop.",
          "code": """
    def execute_trade_based_on_signal(self, signal_type: str | None, reason: str, signal_strength: int):
        # ... (existing code for global checks, cooldown, session filter) ...

        # 1. Handle Closing Existing Positions on Reversal
        if self.position_active:
            perform_close = False
            if self.current_position_side == "Buy" and latest_st_direction == -1:
                self.logger.info("Exit Signal: Supertrend flipped DOWN while in a LONG position. Closing position.")
                perform_close = True
            elif self.current_position_side == "Sell" and latest_st_direction == 1:
                self.logger.info("Exit Signal: Supertrend flipped UP while in a SHORT position. Closing position.")
                perform_close = True

            # FEATURE: Proactive Funding Rate Exit (Snippet 9)
            if self.config.FUNDING_RATE_AVOIDANCE_ENABLED and self.config.FUNDING_RATE_PROACTIVE_EXIT_ENABLED:
                current_unrealized_pnl_pct = self.bot_state.unrealized_pnl_pct
                funding_is_punitive, funding_reason = self._is_funding_rate_avoidance_active(proactive_check=True)
                if funding_is_punitive and abs(current_unrealized_pnl_pct) < Decimal(str(self.config.FUNDING_RATE_PROACTIVE_EXIT_MIN_PROFIT_PCT)) * Decimal('100'):
                    self.logger.warning(Fore.YELLOW + f"Proactive Funding Rate Exit: {funding_reason}. Position not significantly profitable ({current_unrealized_pnl_pct:.2f}%). Closing position before funding." + Style.RESET_ALL)
                    perform_close = True

            if perform_close:
                if self.close_position():
                    self.last_trade_time = now_ts
                return # Exit after closing, wait for next candle

            # If not closing, apply other position management features
            if not perform_close:
                # FEATURE: Multi-Tier Breakeven Stop Loss Activation (Snippet 10)
                self._manage_breakeven_stop_loss()

                # FEATURE: Partial Take Profit (Scaling Out)
                self._manage_partial_take_profit()

                # FEATURE: Trailing Stop Loss Updates (Dynamic Trailing or Ehlers ST Trailing)
                if self.config.TRAILING_STOP_PCT > 0 or self.config.EHLERS_ST_TRAILING_ENABLED:
                    ehlers_st_line = Decimal(str(self.market_data['supertrend_line_value'].iloc[-1])) if not self.market_data.empty else None
                    self.trailing_stop_manager.update_trailing_stop(
                        symbol=self.config.SYMBOL,
                        current_price=current_market_price, # Pass latest market price
                        current_unrealized_pnl_pct=self.bot_state.unrealized_pnl_pct, # Pass for dynamic trailing
                        ehlers_st_line_value=ehlers_st_line, # Pass Ehlers ST line for Snippet 4
                        update_exchange=True
                    )
        # 2. Handle Opening New Positions
        if not self.position_active and signal_type in ['BUY', 'SELL']:
            if signal_strength < self.config.MIN_SIGNAL_STRENGTH: # Check signal strength (Snippet 1)
                self.logger.info(f"Signal strength ({signal_strength}) is below minimum required ({self.config.MIN_SIGNAL_STRENGTH}). Skipping trade.")
                return

            # FEATURE: Max Concurrent Positions Limit Check
            if len(self.all_open_positions) >= self.config.MAX_CONCURRENT_POSITIONS:
                self.logger.warning(f"Max concurrent positions limit ({self.config.MAX_CONCURRENT_POSITIONS}) reached. Cannot open new position for {self.config.SYMBOL}.")
                return

            # FEATURE: Funding Rate Avoidance (Perpetuals)
            if self._is_funding_rate_avoidance_active():
                self.logger.warning("Funding rate avoidance active. Skipping new position opening.")
                return

            trade_side = signal_type
            self.logger.info(f"Received {trade_side} signal. Reason: {reason}. Attempting to open {trade_side.lower()} position.")
            subprocess.run(["termux-toast", f"Signal: {trade_side} {self.config.SYMBOL}. Reason: {reason}"])

            # Calculate Stop Loss and Take Profit prices (with DTP)
            stop_loss_price, take_profit_price = self.calculate_trade_sl_tp(trade_side, current_market_price, self.market_data)

            # FEATURE: Volatility-Adjusted Position Sizing - pass current ATR (Snippet 5 robustness check)
            current_atr_for_sizing = Decimal(str(self.market_data['atr'].iloc[-1])) if 'atr' in self.market_data.columns else None

            # Calculate position size in base currency units
            position_qty = self.order_sizer.calculate_position_size_usd(
                symbol=self.config.SYMBOL,
                account_balance_usdt=self.account_balance_usdt,
                risk_percent=Decimal(str(self.config.RISK_PER_TRADE_PCT / 100)),
                entry_price=current_market_price,
                stop_loss_price=stop_loss_price,
                leverage=Decimal(str(self.config.LEVERAGE)),
                current_atr=current_atr_for_sizing # Pass ATR
            )

            if position_qty is not None and position_qty > Decimal('0'):
                order_type_to_place = self.config.ORDER_TYPE_ENUM
                entry_price_to_place = current_market_price # Default for market or if retracement not enabled

                # FEATURE: Signal Retracement Entry
                if self.config.RETRACEMENT_ENTRY_ENABLED:
                    order_type_to_place = OrderType[self.config.RETRACEMENT_ORDER_TYPE.upper()]
                    if trade_side == 'Buy':
                        entry_price_to_place = current_market_price * (Decimal('1') - Decimal(str(self.config.RETRACEMENT_PCT_FROM_CLOSE)))
                    else: # Sell
                        entry_price_to_place = current_market_price * (Decimal('1') + Decimal(str(self.config.RETRACEMENT_PCT_FROM_CLOSE)))

                    entry_price_to_place = self.precision_manager.round_price(self.config.SYMBOL, entry_price_to_place)
                    self.logger.info(f"Placing {order_type_to_place.value} order for retracement at {entry_price_to_place:.{self.bot_state.price_precision}f}.")

                order_result = self.place_order(
                    side=trade_side,
                    qty=position_qty,
                    order_type=order_type_to_place,
                    entry_price=entry_price_to_place if order_type_to_place == OrderType.LIMIT else None, # Only pass price for limit orders
                    stopLoss=stop_loss_price,
                    takeProfit=take_profit_price
                )

                if order_result:
                    if order_result.get('orderStatus') == 'Filled' or self.config.DRY_RUN:
                        # Update internal state based on order result (especially the filled price)
                        filled_price = Decimal(order_result.get('avgPrice', str(current_market_price)))
                        filled_qty = Decimal(order_result.get('cumExecQty', str(position_qty)))

                        self.position_active = True
                        self.current_position_side = trade_side
                        self.current_position_entry_price = filled_price
                        self.current_position_size = filled_qty
                        self.initial_position_qty = filled_qty # Store initial quantity for partial TP
                        self.last_trade_time = now_ts
                        self.last_signal = trade_side
                        self.breakeven_activated[self.config.SYMBOL] = False # Reset single-tier breakeven status for new position
                        self.breakeven_tier_activated[self.config.SYMBOL] = -1 # Reset multi-tier breakeven status for new position (Snippet 10)
                        self.partial_tp_targets_hit[self.config.SYMBOL] = dict.fromkeys(range(len(self.config.PARTIAL_TP_TARGETS)), False) # Reset partial TP status
                        self.pending_retracement_order = None # Clear pending retracement order
                        self.open_trade_kline_ts = self.last_kline_ts # Set timestamp for time-based exit (Snippet 6)

                        self.logger.info(f"{trade_side} order placed and confirmed filled. Entry: {filled_price}, Qty: {filled_qty}.")

                        # Update BotState with new position
                        with self.bot_state.lock:
                            self.bot_state.open_position_qty = filled_qty
                            self.bot_state.open_position_side = trade_side
                            self.bot_state.open_position_entry_price = filled_price
                            self.bot_state.unrealized_pnl = Decimal('0.0') # Start with 0 PnL
                            self.bot_state.unrealized_pnl_pct = Decimal('0.0')

                        # Initialize Ehlers ST trailing stop if enabled (Snippet 4)
                        if self.config.EHLERS_ST_TRAILING_ENABLED:
                            ehlers_st_line = Decimal(str(self.market_data['supertrend_line_value'].iloc[-1]))
                            self.trailing_stop_manager.initialize_trailing_stop(
                                symbol=self.config.SYMBOL,
                                position_side=trade_side,
                                entry_price=filled_price,
                                current_price=current_market_price,
                                trail_percent=0.0, # Not used for Ehlers ST trailing
                                activation_percent=0.0,
                                ehlers_st_trailing_enabled=True,
                                ehlers_st_line_value=ehlers_st_line
                            )

                    elif order_result.get('orderStatus') in ('New', 'Created') and self.config.RETRACEMENT_ENTRY_ENABLED:
                        # If retracement order is pending, store its details
                        self.pending_retracement_order = {
                            'orderId': order_result['orderId'],
                            'side': trade_side,
                            'qty': position_qty,
                            'price': entry_price_to_place,
                            'time_placed_kline_ts': self.last_kline_ts
                        }
                        self.logger.info(f"Retracement limit order {order_result['orderId']} placed and pending fill.")
                    else:
                        self.logger.error(f"Failed to place {trade_side} order.")
                else:
                    self.logger.error(f"Failed to place {trade_side} order.")
            else:
                self.logger.warning(f"Could not calculate a valid position size for the {trade_side} signal. Skipping order placement.")
        else:
            self.logger.info(Fore.WHITE + "No active position and no new signal to act on." + Style.RESET_ALL)
"""
        }
      ]
    },
    {
      "id": 5,
      "name": "Volatility-Adjusted Position Sizing Robustness",
      "description": "Ensures the volatility-adjusted position sizing is robust by adding a minimum ATR threshold. If the ATR is too low, it can lead to excessively large position sizes due to a very tight calculated stop loss, which might not be realistic. This snippet falls back to a maximum risk percentage if ATR is below threshold.",
      "config_changes": [
        {"key": "MIN_ATR_FOR_SIZING_PCT", "type": "float", "default": 0.001, "description": "Minimum ATR (as a percentage of entry price) required for volatility-adjusted sizing. Below this, sizing defaults to MAX_RISK_PER_TRADE_BALANCE_PCT."}
      ],
      "code_changes": [
        {
          "file_section": "Config class",
          "change_type": "add_field",
          "code": "    MIN_ATR_FOR_SIZING_PCT: float = field(default=0.001) # 0.1%"
        },
        {
          "file_section": "Config.__post_init__",
          "change_type": "add_load_env",
          "code": "        self.MIN_ATR_FOR_SIZING_PCT = float(os.getenv(\"MIN_ATR_FOR_SIZING_PCT\", self.MIN_ATR_FOR_SIZING_PCT))"
        },
        {
          "file_section": "EhlersSuperTrendBot.__init__",
          "change_type": "add_log",
          "code": "        self.logger.info(f\"  Min ATR for Vol Sizing: {config.MIN_ATR_FOR_SIZING_PCT*100:.2f}%\")"
        },
        {
          "file_section": "OrderSizingCalculator.calculate_position_size_usd",
          "change_type": "modify_function",
          "description": "Add ATR quality check for volatility-adjusted sizing.",
          "code": """
    def calculate_position_size_usd(
        self,
        symbol: str,
        account_balance_usdt: Decimal,
        risk_percent: Decimal,
        entry_price: Decimal,
        stop_loss_price: Decimal,
        leverage: Decimal,
        current_atr: Decimal | None = None
    ) -> Decimal | None:
        \"\"\"
        Calculate position size in base currency units based on fixed risk percentage, leverage,
        entry price, and stop loss price. Returns None if calculation is not possible.
        \"\"\"
        specs = self.precision.get_specs(symbol)
        if not specs:
            self.logger.error(f"Cannot calculate position size for {symbol}: Symbol specifications not found.")
            return None

        # --- Input Validation ---
        if account_balance_usdt <= Decimal('0'):
            self.logger.warning(f"Account balance is zero or negative ({account_balance_usdt}). Cannot calculate position size.")
            return None
        if entry_price <= Decimal('0'):
            self.logger.warning(f"Entry price is zero or negative ({entry_price}). Cannot calculate position size.")
            return None
        if leverage <= Decimal('0'):
            self.logger.warning(f"Leverage is zero or negative ({leverage}). Cannot calculate position size.")
            return None

        stop_distance_price = abs(entry_price - stop_loss_price)
        if stop_distance_price <= Decimal('0'):
            self.logger.warning(f"Stop loss distance is zero or negative ({stop_distance_price}). Cannot calculate position size.")
            return None

        # --- Calculations ---
        position_value_usd_unadjusted: Decimal

        # FEATURE: Volatility-Adjusted Position Sizing with robustness (Snippet 5)
        if self.config.VOLATILITY_ADJUSTED_SIZING_ENABLED and current_atr is not None and current_atr > Decimal('0'):
            # Check if ATR is too small, which could lead to excessively large positions
            if entry_price > Decimal('0') and (current_atr / entry_price) < Decimal(str(self.config.MIN_ATR_FOR_SIZING_PCT)):
                self.logger.warning(f"Current ATR ({current_atr:.4f}) is too low relative to price for volatility-adjusted sizing (below {self.config.MIN_ATR_FOR_SIZING_PCT*100:.2f}%). Falling back to fixed risk percentage: {self.config.MAX_RISK_PER_TRADE_BALANCE_PCT*100:.2f}%.")
                risk_amount_usdt = account_balance_usdt * Decimal(str(self.config.MAX_RISK_PER_TRADE_BALANCE_PCT))
                stop_distance_pct = abs(entry_price - stop_loss_price) / entry_price
                if stop_distance_pct > Decimal('0'):
                    position_value_usd_unadjusted = risk_amount_usdt / stop_distance_pct
                else:
                    self.logger.warning("Stop distance percentage is zero. Cannot calculate required position value.")
                    return None
            else:
                self.logger.debug(f"Using Volatility-Adjusted Sizing with ATR: {current_atr:.4f}")
                risk_amount_usdt = account_balance_usdt * Decimal(str(self.config.MAX_RISK_PER_TRADE_BALANCE_PCT))
                stop_distance_price = abs(entry_price - stop_loss_price)
                if stop_distance_price <= Decimal('0'): # Re-check if stop_distance_price became zero after any adjustments
                    self.logger.warning("Stop loss distance is zero or negative after adjustments. Cannot calculate position size.")
                    return None
                position_value_usd_unadjusted = risk_amount_usdt / (stop_distance_price / entry_price)

        else: # Original logic or if volatility-adjusted sizing is disabled
            # Calculate risk amount in USDT
            risk_amount_usdt = account_balance_usdt * risk_percent
            # Calculate stop loss distance in percentage terms
            stop_distance_pct = stop_distance_price / entry_price
            if stop_distance_pct > Decimal('0'):
                position_value_usd_unadjusted = risk_amount_usdt / stop_distance_pct
            else:
                self.logger.warning("Stop distance percentage is zero. Cannot calculate required position value.")
                return None

        # Apply leverage to determine the maximum tradeable position value based on account balance
        max_tradeable_value_usd = account_balance_usdt * leverage

        # Cap the needed position value by maximum tradeable value and Bybit's max position value limits
        position_value_usd = min(
            position_value_usd_unadjusted,
            max_tradeable_value_usd,
            specs.max_position_value # Apply Bybit's specific max order value if available
        )

        # FEATURE: Max Position Size USD from config
        position_value_usd = min(position_value_usd, Decimal(str(self.config.MAX_POSITION_SIZE_USD)))


        # Ensure minimum position value is met
        if position_value_usd < specs.min_position_value:
            self.logger.warning(f"Calculated position value ({position_value_usd:.{self.precision.get_decimal_places(symbol)[0]}f} USD) is below minimum ({specs.min_position_value:.{self.precision.get_decimal_places(symbol)[0]}f} USD). Using minimum.")
            position_value_usd = specs.min_position_value

        # FEATURE: Min Position Size USD from config
        if position_value_usd < Decimal(str(self.config.MIN_POSITION_SIZE_USD)):
            self.logger.warning(f"Calculated position value ({position_value_usd:.{self.precision.get_decimal_places(symbol)[0]}f} USD) is below configured MIN_POSITION_SIZE_USD ({self.config.MIN_POSITION_SIZE_USD:.{self.precision.get_decimal_places(symbol)[0]}f} USD). Using configured minimum.")
            position_value_usd = Decimal(str(self.config.MIN_POSITION_SIZE_USD))


        # Convert position value to quantity in base currency units (category-specific)
        # For linear and spot: Value (Quote) = Quantity (Base) * Price (Quote/Base)
        quantity_base = position_value_usd / entry_price

        # Round the quantity to the nearest valid step
        calculated_quantity = self.precision.round_quantity(symbol, quantity_base)

        # Final check on calculated quantity against min/max order quantity
        if calculated_quantity < specs.min_order_qty:
            self.logger.warning(f"Calculated quantity ({calculated_quantity} {specs.base_currency}) is below minimum order quantity ({specs.min_order_qty}). Setting to minimum.")
            final_quantity = specs.min_order_qty
        elif calculated_quantity > specs.max_order_qty:
            self.logger.warning(f"Calculated quantity ({calculated_quantity} {specs.base_currency}) exceeds maximum order quantity ({specs.max_order_qty}). Setting to maximum.")
            final_quantity = specs.max_order_qty
        else:
            final_quantity = calculated_quantity

        # Ensure final quantity is positive
        if final_quantity <= Decimal('0'):
            self.logger.warning(f"Calculated final quantity is zero or negative ({final_quantity}). Cannot proceed with order.")
            return None

        # Recalculate actual risk based on final quantity and compare against allowed risk
        actual_position_value_usd = final_quantity * entry_price
        actual_risk_amount_usdt = actual_position_value_usd * stop_distance_pct
        actual_risk_percent = (actual_risk_amount_usdt / account_balance_usdt) * Decimal('100') if account_balance_usdt > Decimal('0') else Decimal('0')

        self.logger.debug(f"Order Sizing for {symbol}: Entry={entry_price}, SL={stop_loss_price}, Risk%={risk_percent:.4f}, Balance={account_balance_usdt:.4f} USDT")
        self.logger.debug(f"  Calculated Qty={quantity_base:.8f} {specs.base_currency}, Rounded Qty={final_quantity:.8f}")
        self.logger.debug(f"  Position Value={position_value_usd:.4f} USD, Actual Risk={actual_risk_amount_usdt:.4f} USDT ({actual_risk_percent:.4f}%)")

        # Optional: Check if actual risk exceeds the allowed risk percentage
        if actual_risk_percent > risk_percent * Decimal('1.01'): # Allow for slight rounding discrepancies
            self.logger.warning(f"Calculated risk ({actual_risk_percent:.4f}%) slightly exceeds allowed risk ({risk_percent:.4f}%). Review parameters.")

        return final_quantity
"""
        }
      ]
    },
    {
      "id": 6,
      "name": "Time-Based Exit for Unprofitable Trades",
      "description": "Automatically closes trades that have been open for a specified number of candles and are still unprofitable. This helps to prevent 'stuck' trades from tying up capital and incurring further losses, promoting faster capital rotation.",
      "config_changes": [
        {"key": "TIME_BASED_EXIT_ENABLED", "type": "bool", "default": false, "description": "Enable/disable time-based exit for unprofitable trades."},
        {"key": "UNPROFITABLE_TRADE_MAX_BARS", "type": "int", "default": 10, "description": "Maximum number of bars an unprofitable trade can remain open before being closed automatically."}
      ],
      "code_changes": [
        {
          "file_section": "Config class",
          "change_type": "add_field",
          "code": """    TIME_BASED_EXIT_ENABLED: bool = field(default=False)
    UNPROFITABLE_TRADE_MAX_BARS: int = field(default=10)"""
        },
        {
          "file_section": "Config.__post_init__",
          "change_type": "add_load_env",
          "code": """        self.TIME_BASED_EXIT_ENABLED = os.getenv("TIME_BASED_EXIT_ENABLED", str(self.TIME_BASED_EXIT_ENABLED)).lower() in ['true', '1', 't']
        self.UNPROFITABLE_TRADE_MAX_BARS = int(os.getenv("UNPROFITABLE_TRADE_MAX_BARS", self.UNPROFITABLE_TRADE_MAX_BARS))"""
        },
        {
          "file_section": "EhlersSuperTrendBot.__init__",
          "change_type": "add_field",
          "code": "        self.open_trade_kline_ts: int = 0 # Unix timestamp of the kline when the current trade was opened (Snippet 6)"
        },
        {
          "file_section": "EhlersSuperTrendBot.__init__",
          "change_type": "add_log",
          "code": """        self.logger.info(f"  Time-Based Exit: {config.TIME_BASED_EXIT_ENABLED}, Max Unprofitable Bars: {config.UNPROFITABLE_TRADE_MAX_BARS}")"""
        },
        {
          "file_section": "EhlersSuperTrendBot._manage_time_based_exit",
          "change_type": "add_function",
          "code": """
    def _manage_time_based_exit(self, current_kline_ts: int):
        \"\"\"FEATURE: Time-Based Exit for Unprofitable Trades (Snippet 6).\"\"\"
        if not self.config.TIME_BASED_EXIT_ENABLED or not self.position_active or self.open_trade_kline_ts == 0:
            return

        # Check if the trade is unprofitable
        if self.bot_state.unrealized_pnl >= Decimal('0'):
            return # Only close if unprofitable

        # Calculate how many bars the trade has been open
        timeframe_ms = self._get_timeframe_in_ms()
        if timeframe_ms == 0:
            self.logger.error("Timeframe in milliseconds is 0, cannot calculate bars for time-based exit.")
            return

        bars_open = (current_kline_ts - self.open_trade_kline_ts) / timeframe_ms
        if bars_open >= self.config.UNPROFITABLE_TRADE_MAX_BARS:
            self.logger.warning(Fore.YELLOW + f"Trade for {self.config.SYMBOL} has been unprofitable for {bars_open:.0f} bars (max {self.config.UNPROFITABLE_TRADE_MAX_BARS}). Initiating time-based exit." + Style.RESET_ALL)
            if self.close_position():
                self.logger.info(f"Position for {self.config.SYMBOL} closed due to time-based exit.")
                self.last_trade_time = time.time()
            else:
                self.logger.error(f"Failed to close position for {self.config.SYMBOL} during time-based exit.")
"""
        },
        {
          "file_section": "EhlersSuperTrendBot.execute_trade_based_on_signal",
          "change_type": "modify_function",
          "description": "Set `open_trade_kline_ts` when a new position is opened.",
          "code": """
    def execute_trade_based_on_signal(self, signal_type: str | None, reason: str, signal_strength: int):
        # ... (existing code) ...
                if order_result:
                    if order_result.get('orderStatus') == 'Filled' or self.config.DRY_RUN:
                        # ... (existing state updates) ...
                        self.open_trade_kline_ts = self.last_kline_ts # Set timestamp for time-based exit (Snippet 6)
                        # ... (rest of function) ...
"""
        },
        {
          "file_section": "EhlersSuperTrendBot._process_websocket_message",
          "change_type": "modify_function",
          "description": "Call `_manage_time_based_exit` for active positions.",
          "code": """
    def _process_websocket_message(self, msg: dict[str, Any]):
        \"\"\"
        The core incantation, triggered by each new confirmed k-line,
        where market data is transformed into signals and actions.
        \"\"\"
        if self.stop_event.is_set():
            return

        if "topic" in msg and str(msg["topic"]).startswith(f"kline.{self.config.TIMEFRAME}.{self.config.SYMBOL}"):
            kline = msg['data'][0]
            if not kline['confirm']:
                return # Only process confirmed (closed) candles

            ts = int(kline['start'])
            if ts <= self.last_kline_ts:
                return # Skip duplicate or old candle data
            self.last_kline_ts = ts

            self.logger.info(Fore.LIGHTMAGENTA_EX + f"--- New Confirmed Candle [{datetime.fromtimestamp(ts/1000)}] ---" + Style.RESET_ALL)

            # Update data and state
            self._update_market_data_and_state()

            # Manage time-based exit for unprofitable trades (Snippet 6)
            self._manage_time_based_exit(ts)

            # After updating, generate signal and execute trade
            if not self.market_data.empty:
                signal, reason, signal_strength = self.generate_signal(self.market_data) # Updated call signature for Snippet 1
                self.logger.info(Fore.WHITE + f"Signal: {signal or 'NONE'} (Strength: {signal_strength}) | Reason: {reason}" + Style.RESET_ALL)
                self.get_positions() # Refresh position state before trading
                self.execute_trade_based_on_signal(signal, reason, signal_strength) # Updated call signature for Snippet 1
"""
        }
      ]
    },
    {
      "id": 7,
      "name": "Session-Based Volatility Filter",
      "description": "Introduces a market session filter that allows trading only during specified UTC hours and days, and further requires a minimum level of volatility (measured by ATR) during those sessions. This helps to focus trading on periods with higher expected activity and better profit potential, avoiding choppy markets.",
      "config_changes": [
        {"key": "SESSION_FILTER_ENABLED", "type": "bool", "default": false, "description": "Enable/disable session-based volatility filter."},
        {"key": "SESSION_START_HOUR_UTC", "type": "int", "default": 8, "description": "Start hour (UTC) for the active trading session."},
        {"key": "SESSION_END_HOUR_UTC", "type": "int", "default": 20, "description": "End hour (UTC) for the active trading session."},
        {"key": "SESSION_MIN_VOLATILITY_FACTOR", "type": "float", "default": 0.0005, "description": "Minimum ATR (as a percentage of current price) required during active session for trading."}
      ],
      "code_changes": [
        {
          "file_section": "Config class",
          "change_type": "add_field",
          "code": """    SESSION_FILTER_ENABLED: bool = field(default=False)
    SESSION_START_HOUR_UTC: int = field(default=8)
    SESSION_END_HOUR_UTC: int = field(default=20)
    SESSION_MIN_VOLATILITY_FACTOR: float = field(default=0.0005) # 0.05% of price"""
        },
        {
          "file_section": "Config.__post_init__",
          "change_type": "add_load_env",
          "code": """        self.SESSION_FILTER_ENABLED = os.getenv("SESSION_FILTER_ENABLED", str(self.SESSION_FILTER_ENABLED)).lower() in ['true', '1', 't']
        self.SESSION_START_HOUR_UTC = int(os.getenv("SESSION_START_HOUR_UTC", self.SESSION_START_HOUR_UTC))
        self.SESSION_END_HOUR_UTC = int(os.getenv("SESSION_END_HOUR_UTC", self.SESSION_END_HOUR_UTC))
        self.SESSION_MIN_VOLATILITY_FACTOR = float(os.getenv("SESSION_MIN_VOLATILITY_FACTOR", self.SESSION_MIN_VOLATILITY_FACTOR))"""
        },
        {
          "file_section": "EhlersSuperTrendBot.__init__",
          "change_type": "add_log",
          "code": """        self.logger.info(f"  Session Filter: {config.SESSION_FILTER_ENABLED}, Hours: {config.SESSION_START_HOUR_UTC}-{config.SESSION_END_HOUR_UTC} UTC, Min Vol: {config.SESSION_MIN_VOLATILITY_FACTOR*100:.2f}%")"""
        },
        {
          "file_section": "EhlersSuperTrendBot._is_session_active_and_volatile",
          "change_type": "add_function",
          "code": """
    def _is_session_active_and_volatile(self, current_price: Decimal, current_atr: Decimal | None) -> tuple[bool, str]:
        \"\"\"FEATURE: Session-Based Volatility Filter (Snippet 7).\"\"\"
        if not self.config.SESSION_FILTER_ENABLED:
            return True, "Session filter disabled."

        now_utc = datetime.now(dateutil.tz.UTC)
        current_hour_utc = now_utc.hour
        current_weekday = now_utc.strftime('%A')

        # Check trading days (re-use existing Time-Based Trading Window logic for days)
        if current_weekday not in self.config.TRADE_DAYS_OF_WEEK:
            return False, f"Not an allowed trading day ({current_weekday})."

        # Check trading hours
        if not (self.config.SESSION_START_HOUR_UTC <= current_hour_utc < self.config.SESSION_END_HOUR_UTC):
            return False, f"Outside active session hours ({self.config.SESSION_START_HOUR_UTC}-{self.config.SESSION_END_HOUR_UTC} UTC). Current: {current_hour_utc} UTC."

        # Check for minimum volatility during the session
        if current_atr is None or current_atr <= Decimal('0') or current_price <= Decimal('0'):
            return False, "ATR or current price not available/valid for volatility check."

        volatility_pct = (current_atr / current_price)
        if volatility_pct < Decimal(str(self.config.SESSION_MIN_VOLATILITY_FACTOR)):
            return False, f"Current session volatility ({volatility_pct*100:.2f}%) below minimum required ({self.config.SESSION_MIN_VOLATILITY_FACTOR*100:.2f}%)."

        return True, "Session active and sufficiently volatile."
"""
        },
        {
          "file_section": "EhlersSuperTrendBot.execute_trade_based_on_signal",
          "change_type": "modify_function",
          "description": "Integrate session-based volatility filter.",
          "code": """
    def execute_trade_based_on_signal(self, signal_type: str | None, reason: str, signal_strength: int):
        \"\"\"
        Execute trades based on the generated signal and current position state.
        Manages opening new positions, closing existing ones based on signal reversal,
        and updating stop losses (including trailing stops).
        
        Includes checks for:
        - Cumulative Loss Guard
        - Time-Based Trading Window
        - Max Concurrent Positions Limit
        - Funding Rate Avoidance
        - News Event Trading Pause
        - Signal Retracement Entry (initial placement)
        - Breakeven Stop Loss (monitoring)
        - Partial Take Profit (monitoring)
        \"\"\"
        # Global checks before any trade action
        if not self._cumulative_loss_guard():
            self.logger.warning("Cumulative loss limit reached. Skipping trade execution for this cycle.")
            return

        if not self._is_time_to_trade():
            self.logger.info("Outside allowed trading window. Skipping trade execution for this cycle.")
            return

        if self.config.NEWS_PAUSE_ENABLED:
            paused, pause_reason = self.news_calendar_manager.is_trading_paused()
            if paused:
                self.logger.info(f"Trading paused: {pause_reason}")
                return # Skip all trading actions

        # Fetch current market data (ticker for price)
        current_market_price = Decimal(str(self.market_data['close'].iloc[-1])) if not self.market_data.empty else Decimal('0.0')
        if current_market_price <= Decimal('0'):
            self.logger.warning("Could not retrieve current market price from kline data. Cannot execute trade based on signal.")
            return

        # Ensure we have valid instrument specifications for precision rounding
        specs = self.precision_manager.get_specs(self.config.SYMBOL)
        if not specs:
            self.logger.error(f"Instrument specifications not found for {self.config.SYMBOL}. Cannot execute trade.")
            return

        # FEATURE: Session-Based Volatility Filter (Snippet 7)
        current_atr_for_session_filter = Decimal(str(self.market_data['atr'].iloc[-1])) if 'atr' in self.market_data.columns else None
        session_ok, session_reason = self._is_session_active_and_volatile(current_market_price, current_atr_for_session_filter)
        if not session_ok:
            self.logger.info(f"Session filter rejected trade: {session_reason}")
            return


        # --- Trade Cooldown Check ---
        now_ts = time.time()
        effective_cooldown_sec = Decimal(str(self.config.SIGNAL_COOLDOWN_SEC)) # Base cooldown

        # FEATURE: Dynamic Signal Cooldown based on Volatility (Snippet 8)
        if self.config.DYNAMIC_COOLDOWN_ENABLED and not self.market_data.empty and 'atr' in self.market_data.columns:
            # Use the same volatility measure as adaptive indicators
            current_atr = Decimal(str(self.market_data['atr'].iloc[-1]))
            current_price = Decimal(str(self.market_data['close'].iloc[-1]))

            if current_price > Decimal('0'):
                avg_range_pct = current_atr / current_price
                if avg_range_pct >= Decimal(str(self.config.VOLATILITY_THRESHOLD_HIGH)):
                    effective_cooldown_sec *= Decimal(str(self.config.COOLDOWN_VOLATILITY_FACTOR_HIGH))
                    self.logger.debug(f"High volatility detected ({avg_range_pct*100:.2f}%). Reducing cooldown by {self.config.COOLDOWN_VOLATILITY_FACTOR_HIGH}x.")
                elif avg_range_pct <= Decimal(str(self.config.VOLATILITY_THRESHOLD_LOW)):
                    effective_cooldown_sec *= Decimal(str(self.config.COOLDOWN_VOLATILITY_FACTOR_LOW))
                    self.logger.debug(f"Low volatility detected ({avg_range_pct*100:.2f}%). Increasing cooldown by {self.config.COOLDOWN_VOLATILITY_FACTOR_LOW}x.")
                else:
                    self.logger.debug(f"Normal volatility ({avg_range_pct*100:.2f}%). Using default cooldown.")
            
            effective_cooldown_sec = max(Decimal('5'), effective_cooldown_sec) # Ensure a minimum cooldown

        if now_ts - self.last_trade_time < float(effective_cooldown_sec):
            self.logger.info(Fore.LIGHTBLACK_EX + f"Trade cooldown active ({effective_cooldown_sec:.1f}s). Skipping trade execution." + Style.RESET_ALL)
            return

        # --- Manage pending retracement orders ---
        # This handles cancelling old orders, actual fill is handled in `_process_websocket_message`
        self._manage_retracement_order(self.last_kline_ts)
        # If there's a pending retracement order, don't try to open new positions
        if self.pending_retracement_order:
            self.logger.info("A retracement order is pending. Not opening new positions until it's filled or cancelled.")
            return

        # --- State Management & Trade Execution ---
        latest_st_direction = self.market_data['supertrend_direction'].iloc[-1]

        # 1. Handle Closing Existing Positions on Reversal
        if self.position_active:
            perform_close = False
            if self.current_position_side == "Buy" and latest_st_direction == -1:
                self.logger.info("Exit Signal: Supertrend flipped DOWN while in a LONG position. Closing position.")
                perform_close = True
            elif self.current_position_side == "Sell" and latest_st_direction == 1:
                self.logger.info("Exit Signal: Supertrend flipped UP while in a SHORT position. Closing position.")
                perform_close = True

            # FEATURE: Proactive Funding Rate Exit (Snippet 9)
            if self.config.FUNDING_RATE_AVOIDANCE_ENABLED and self.config.FUNDING_RATE_PROACTIVE_EXIT_ENABLED:
                current_unrealized_pnl_pct = self.bot_state.unrealized_pnl_pct
                funding_is_punitive, funding_reason = self._is_funding_rate_avoidance_active(proactive_check=True)
                if funding_is_punitive and abs(current_unrealized_pnl_pct) < Decimal(str(self.config.FUNDING_RATE_PROACTIVE_EXIT_MIN_PROFIT_PCT)) * Decimal('100'):
                    self.logger.warning(Fore.YELLOW + f"Proactive Funding Rate Exit: {funding_reason}. Position not significantly profitable ({current_unrealized_pnl_pct:.2f}%). Closing position before funding." + Style.RESET_ALL)
                    perform_close = True

            if perform_close:
                if self.close_position():
                    self.last_trade_time = now_ts
                return # Exit after closing, wait for next candle

            # If not closing, apply other position management features
            if not perform_close:
                # FEATURE: Multi-Tier Breakeven Stop Loss Activation (Snippet 10)
                self._manage_breakeven_stop_loss()

                # FEATURE: Partial Take Profit (Scaling Out)
                self._manage_partial_take_profit()

                # FEATURE: Trailing Stop Loss Updates (Dynamic Trailing or Ehlers ST Trailing)
                if self.config.TRAILING_STOP_PCT > 0 or self.config.EHLERS_ST_TRAILING_ENABLED:
                    ehlers_st_line = Decimal(str(self.market_data['supertrend_line_value'].iloc[-1])) if not self.market_data.empty else None
                    self.trailing_stop_manager.update_trailing_stop(
                        symbol=self.config.SYMBOL,
                        current_price=current_market_price, # Pass latest market price
                        current_unrealized_pnl_pct=self.bot_state.unrealized_pnl_pct, # Pass for dynamic trailing
                        ehlers_st_line_value=ehlers_st_line, # Pass Ehlers ST line for Snippet 4
                        update_exchange=True
                    )
        # 2. Handle Opening New Positions
        if not self.position_active and signal_type in ['BUY', 'SELL']:
            if signal_strength < self.config.MIN_SIGNAL_STRENGTH: # Check signal strength (Snippet 1)
                self.logger.info(f"Signal strength ({signal_strength}) is below minimum required ({self.config.MIN_SIGNAL_STRENGTH}). Skipping trade.")
                return

            # FEATURE: Max Concurrent Positions Limit Check
            if len(self.all_open_positions) >= self.config.MAX_CONCURRENT_POSITIONS:
                self.logger.warning(f"Max concurrent positions limit ({self.config.MAX_CONCURRENT_POSITIONS}) reached. Cannot open new position for {self.config.SYMBOL}.")
                return

            # FEATURE: Funding Rate Avoidance (Perpetuals)
            if self._is_funding_rate_avoidance_active():
                self.logger.warning("Funding rate avoidance active. Skipping new position opening.")
                return

            trade_side = signal_type
            self.logger.info(f"Received {trade_side} signal. Reason: {reason}. Attempting to open {trade_side.lower()} position.")
            subprocess.run(["termux-toast", f"Signal: {trade_side} {self.config.SYMBOL}. Reason: {reason}"])

            # Calculate Stop Loss and Take Profit prices (with DTP)
            stop_loss_price, take_profit_price = self.calculate_trade_sl_tp(trade_side, current_market_price, self.market_data)

            # FEATURE: Volatility-Adjusted Position Sizing - pass current ATR (Snippet 5 robustness check)
            current_atr_for_sizing = Decimal(str(self.market_data['atr'].iloc[-1])) if 'atr' in self.market_data.columns else None

            # Calculate position size in base currency units
            position_qty = self.order_sizer.calculate_position_size_usd(
                symbol=self.config.SYMBOL,
                account_balance_usdt=self.account_balance_usdt,
                risk_percent=Decimal(str(self.config.RISK_PER_TRADE_PCT / 100)),
                entry_price=current_market_price,
                stop_loss_price=stop_loss_price,
                leverage=Decimal(str(self.config.LEVERAGE)),
                current_atr=current_atr_for_sizing # Pass ATR
            )

            if position_qty is not None and position_qty > Decimal('0'):
                order_type_to_place = self.config.ORDER_TYPE_ENUM
                entry_price_to_place = current_market_price # Default for market or if retracement not enabled

                # FEATURE: Signal Retracement Entry
                if self.config.RETRACEMENT_ENTRY_ENABLED:
                    order_type_to_place = OrderType[self.config.RETRACEMENT_ORDER_TYPE.upper()]
                    if trade_side == 'Buy':
                        entry_price_to_place = current_market_price * (Decimal('1') - Decimal(str(self.config.RETRACEMENT_PCT_FROM_CLOSE)))
                    else: # Sell
                        entry_price_to_place = current_market_price * (Decimal('1') + Decimal(str(self.config.RETRACEMENT_PCT_FROM_CLOSE)))

                    entry_price_to_place = self.precision_manager.round_price(self.config.SYMBOL, entry_price_to_place)
                    self.logger.info(f"Placing {order_type_to_place.value} order for retracement at {entry_price_to_place:.{self.bot_state.price_precision}f}.")

                order_result = self.place_order(
                    side=trade_side,
                    qty=position_qty,
                    order_type=order_type_to_place,
                    entry_price=entry_price_to_place if order_type_to_place == OrderType.LIMIT else None, # Only pass price for limit orders
                    stopLoss=stop_loss_price,
                    takeProfit=take_profit_price
                )

                if order_result:
                    if order_result.get('orderStatus') == 'Filled' or self.config.DRY_RUN:
                        # Update internal state based on order result (especially the filled price)
                        filled_price = Decimal(order_result.get('avgPrice', str(current_market_price)))
                        filled_qty = Decimal(order_result.get('cumExecQty', str(position_qty)))

                        self.position_active = True
                        self.current_position_side = trade_side
                        self.current_position_entry_price = filled_price
                        self.current_position_size = filled_qty
                        self.initial_position_qty = filled_qty # Store initial quantity for partial TP
                        self.last_trade_time = now_ts
                        self.last_signal = trade_side
                        self.breakeven_activated[self.config.SYMBOL] = False # Reset single-tier breakeven status for new position
                        self.breakeven_tier_activated[self.config.SYMBOL] = -1 # Reset multi-tier breakeven status for new position (Snippet 10)
                        self.partial_tp_targets_hit[self.config.SYMBOL] = dict.fromkeys(range(len(self.config.PARTIAL_TP_TARGETS)), False) # Reset partial TP status
                        self.pending_retracement_order = None # Clear pending retracement order
                        self.open_trade_kline_ts = self.last_kline_ts # Set timestamp for time-based exit (Snippet 6)

                        self.logger.info(f"{trade_side} order placed and confirmed filled. Entry: {filled_price}, Qty: {filled_qty}.")

                        # Update BotState with new position
                        with self.bot_state.lock:
                            self.bot_state.open_position_qty = filled_qty
                            self.bot_state.open_position_side = trade_side
                            self.bot_state.open_position_entry_price = filled_price
                            self.bot_state.unrealized_pnl = Decimal('0.0') # Start with 0 PnL
                            self.bot_state.unrealized_pnl_pct = Decimal('0.0')

                        # Initialize Ehlers ST trailing stop if enabled (Snippet 4)
                        if self.config.EHLERS_ST_TRAILING_ENABLED:
                            ehlers_st_line = Decimal(str(self.market_data['supertrend_line_value'].iloc[-1]))
                            self.trailing_stop_manager.initialize_trailing_stop(
                                symbol=self.config.SYMBOL,
                                position_side=trade_side,
                                entry_price=filled_price,
                                current_price=current_market_price,
                                trail_percent=0.0, # Not used for Ehlers ST trailing
                                activation_percent=0.0,
                                ehlers_st_trailing_enabled=True,
                                ehlers_st_line_value=ehlers_st_line
                            )

                    elif order_result.get('orderStatus') in ('New', 'Created') and self.config.RETRACEMENT_ENTRY_ENABLED:
                        # If retracement order is pending, store its details
                        self.pending_retracement_order = {
                            'orderId': order_result['orderId'],
                            'side': trade_side,
                            'qty': position_qty,
                            'price': entry_price_to_place,
                            'time_placed_kline_ts': self.last_kline_ts
                        }
                        self.logger.info(f"Retracement limit order {order_result['orderId']} placed and pending fill.")
                    else:
                        self.logger.error(f"Failed to place {trade_side} order.")
                else:
                    self.logger.error(f"Failed to place {trade_side} order.")
            else:
                self.logger.warning(f"Could not calculate a valid position size for the {trade_side} signal. Skipping order placement.")
        else:
            self.logger.info(Fore.WHITE + "No active position and no new signal to act on." + Style.RESET_ALL)
"""
        }
      ]
    },
    {
      "id": 8,
      "name": "Dynamic Signal Cooldown based on Volatility",
      "description": "Adjusts the signal cooldown period dynamically based on current market volatility. In high-volatility environments, the cooldown is reduced to allow for faster re-entry or reaction to new signals. In low-volatility, it's increased to avoid overtrading in choppy conditions.",
      "config_changes": [
        {"key": "DYNAMIC_COOLDOWN_ENABLED", "type": "bool", "default": false, "description": "Enable/disable dynamic signal cooldown based on volatility."},
        {"key": "COOLDOWN_VOLATILITY_FACTOR_HIGH", "type": "float", "default": 0.5, "description": "Multiplier for cooldown in high volatility (e.g., 0.5 for half cooldown)."},
        {"key": "COOLDOWN_VOLATILITY_FACTOR_LOW", "type": "float", "default": 1.5, "description": "Multiplier for cooldown in low volatility (e.g., 1.5 for 1.5x cooldown)."}
      ],
      "code_changes": [
        {
          "file_section": "Config class",
          "change_type": "add_field",
          "code": """    DYNAMIC_COOLDOWN_ENABLED: bool = field(default=False)
    COOLDOWN_VOLATILITY_FACTOR_HIGH: float = field(default=0.5)
    COOLDOWN_VOLATILITY_FACTOR_LOW: float = field(default=1.5)"""
        },
        {
          "file_section": "Config.__post_init__",
          "change_type": "add_load_env",
          "code": """        self.DYNAMIC_COOLDOWN_ENABLED = os.getenv("DYNAMIC_COOLDOWN_ENABLED", str(self.DYNAMIC_COOLDOWN_ENABLED)).lower() in ['true', '1', 't']
        self.COOLDOWN_VOLATILITY_FACTOR_HIGH = float(os.getenv("COOLDOWN_VOLATILITY_FACTOR_HIGH", self.COOLDOWN_VOLATILITY_FACTOR_HIGH))
        self.COOLDOWN_VOLATILITY_FACTOR_LOW = float(os.getenv("COOLDOWN_VOLATILITY_FACTOR_LOW", self.COOLDOWN_VOLATILITY_FACTOR_LOW))"""
        },
        {
          "file_section": "EhlersSuperTrendBot.__init__",
          "change_type": "add_log",
          "code": """        self.logger.info(f"  Dynamic Cooldown: {config.DYNAMIC_COOLDOWN_ENABLED}, High Vol Factor: {config.COOLDOWN_VOLATILITY_FACTOR_HIGH}x, Low Vol Factor: {config.COOLDOWN_VOLATILITY_FACTOR_LOW}x")"""
        },
        {
          "file_section": "EhlersSuperTrendBot.execute_trade_based_on_signal",
          "change_type": "modify_function",
          "description": "Implement dynamic cooldown calculation.",
          "code": """
    def execute_trade_based_on_signal(self, signal_type: str | None, reason: str, signal_strength: int):
        \"\"\"
        Execute trades based on the generated signal and current position state.
        Manages opening new positions, closing existing ones based on signal reversal,
        and updating stop losses (including trailing stops).
        
        Includes checks for:
        - Cumulative Loss Guard
        - Time-Based Trading Window
        - Max Concurrent Positions Limit
        - Funding Rate Avoidance
        - News Event Trading Pause
        - Signal Retracement Entry (initial placement)
        - Breakeven Stop Loss (monitoring)
        - Partial Take Profit (monitoring)
        \"\"\"
        # Global checks before any trade action
        if not self._cumulative_loss_guard():
            self.logger.warning("Cumulative loss limit reached. Skipping trade execution for this cycle.")
            return

        if not self._is_time_to_trade():
            self.logger.info("Outside allowed trading window. Skipping trade execution for this cycle.")
            return

        if self.config.NEWS_PAUSE_ENABLED:
            paused, pause_reason = self.news_calendar_manager.is_trading_paused()
            if paused:
                self.logger.info(f"Trading paused: {pause_reason}")
                return # Skip all trading actions

        # Fetch current market data (ticker for price)
        current_market_price = Decimal(str(self.market_data['close'].iloc[-1])) if not self.market_data.empty else Decimal('0.0')
        if current_market_price <= Decimal('0'):
            self.logger.warning("Could not retrieve current market price from kline data. Cannot execute trade based on signal.")
            return

        # Ensure we have valid instrument specifications for precision rounding
        specs = self.precision_manager.get_specs(self.config.SYMBOL)
        if not specs:
            self.logger.error(f"Instrument specifications not found for {self.config.SYMBOL}. Cannot execute trade.")
            return

        # FEATURE: Session-Based Volatility Filter (Snippet 7)
        current_atr_for_session_filter = Decimal(str(self.market_data['atr'].iloc[-1])) if 'atr' in self.market_data.columns else None
        session_ok, session_reason = self._is_session_active_and_volatile(current_market_price, current_atr_for_session_filter)
        if not session_ok:
            self.logger.info(f"Session filter rejected trade: {session_reason}")
            return


        # --- Trade Cooldown Check ---
        now_ts = time.time()
        effective_cooldown_sec = Decimal(str(self.config.SIGNAL_COOLDOWN_SEC)) # Base cooldown

        # FEATURE: Dynamic Signal Cooldown based on Volatility (Snippet 8)
        if self.config.DYNAMIC_COOLDOWN_ENABLED and not self.market_data.empty and 'atr' in self.market_data.columns:
            # Use the same volatility measure as adaptive indicators
            current_atr = Decimal(str(self.market_data['atr'].iloc[-1]))
            current_price = Decimal(str(self.market_data['close'].iloc[-1]))

            if current_price > Decimal('0'):
                avg_range_pct = current_atr / current_price
                if avg_range_pct >= Decimal(str(self.config.VOLATILITY_THRESHOLD_HIGH)):
                    effective_cooldown_sec *= Decimal(str(self.config.COOLDOWN_VOLATILITY_FACTOR_HIGH))
                    self.logger.debug(f"High volatility detected ({avg_range_pct*100:.2f}%). Reducing cooldown by {self.config.COOLDOWN_VOLATILITY_FACTOR_HIGH}x.")
                elif avg_range_pct <= Decimal(str(self.config.VOLATILITY_THRESHOLD_LOW)):
                    effective_cooldown_sec *= Decimal(str(self.config.COOLDOWN_VOLATILITY_FACTOR_LOW))
                    self.logger.debug(f"Low volatility detected ({avg_range_pct*100:.2f}%). Increasing cooldown by {self.config.COOLDOWN_VOLATILITY_FACTOR_LOW}x.")
                else:
                    self.logger.debug(f"Normal volatility ({avg_range_pct*100:.2f}%). Using default cooldown.")
            
            effective_cooldown_sec = max(Decimal('5'), effective_cooldown_sec) # Ensure a minimum cooldown

        if now_ts - self.last_trade_time < float(effective_cooldown_sec):
            self.logger.info(Fore.LIGHTBLACK_EX + f"Trade cooldown active ({effective_cooldown_sec:.1f}s). Skipping trade execution." + Style.RESET_ALL)
            return

        # --- Manage pending retracement orders ---
        # This handles cancelling old orders, actual fill is handled in `_process_websocket_message`
        self._manage_retracement_order(self.last_kline_ts)
        # If there's a pending retracement order, don't try to open new positions
        if self.pending_retracement_order:
            self.logger.info("A retracement order is pending. Not opening new positions until it's filled or cancelled.")
            return

        # --- State Management & Trade Execution ---
        latest_st_direction = self.market_data['supertrend_direction'].iloc[-1]

        # 1. Handle Closing Existing Positions on Reversal
        if self.position_active:
            perform_close = False
            if self.current_position_side == "Buy" and latest_st_direction == -1:
                self.logger.info("Exit Signal: Supertrend flipped DOWN while in a LONG position. Closing position.")
                perform_close = True
            elif self.current_position_side == "Sell" and latest_st_direction == 1:
                self.logger.info("Exit Signal: Supertrend flipped UP while in a SHORT position. Closing position.")
                perform_close = True

            # FEATURE: Proactive Funding Rate Exit (Snippet 9)
            if self.config.FUNDING_RATE_AVOIDANCE_ENABLED and self.config.FUNDING_RATE_PROACTIVE_EXIT_ENABLED:
                current_unrealized_pnl_pct = self.bot_state.unrealized_pnl_pct
                funding_is_punitive, funding_reason = self._is_funding_rate_avoidance_active(proactive_check=True)
                if funding_is_punitive and abs(current_unrealized_pnl_pct) < Decimal(str(self.config.FUNDING_RATE_PROACTIVE_EXIT_MIN_PROFIT_PCT)) * Decimal('100'):
                    self.logger.warning(Fore.YELLOW + f"Proactive Funding Rate Exit: {funding_reason}. Position not significantly profitable ({current_unrealized_pnl_pct:.2f}%). Closing position before funding." + Style.RESET_ALL)
                    perform_close = True

            if perform_close:
                if self.close_position():
                    self.last_trade_time = now_ts
                return # Exit after closing, wait for next candle

            # If not closing, apply other position management features
            if not perform_close:
                # FEATURE: Multi-Tier Breakeven Stop Loss Activation (Snippet 10)
                self._manage_breakeven_stop_loss()

                # FEATURE: Partial Take Profit (Scaling Out)
                self._manage_partial_take_profit()

                # FEATURE: Trailing Stop Loss Updates (Dynamic Trailing or Ehlers ST Trailing)
                if self.config.TRAILING_STOP_PCT > 0 or self.config.EHLERS_ST_TRAILING_ENABLED:
                    ehlers_st_line = Decimal(str(self.market_data['supertrend_line_value'].iloc[-1])) if not self.market_data.empty else None
                    self.trailing_stop_manager.update_trailing_stop(
                        symbol=self.config.SYMBOL,
                        current_price=current_market_price, # Pass latest market price
                        current_unrealized_pnl_pct=self.bot_state.unrealized_pnl_pct, # Pass for dynamic trailing
                        ehlers_st_line_value=ehlers_st_line, # Pass Ehlers ST line for Snippet 4
                        update_exchange=True
                    )
        # 2. Handle Opening New Positions
        if not self.position_active and signal_type in ['BUY', 'SELL']:
            if signal_strength < self.config.MIN_SIGNAL_STRENGTH: # Check signal strength (Snippet 1)
                self.logger.info(f"Signal strength ({signal_strength}) is below minimum required ({self.config.MIN_SIGNAL_STRENGTH}). Skipping trade.")
                return

            # FEATURE: Max Concurrent Positions Limit Check
            if len(self.all_open_positions) >= self.config.MAX_CONCURRENT_POSITIONS:
                self.logger.warning(f"Max concurrent positions limit ({self.config.MAX_CONCURRENT_POSITIONS}) reached. Cannot open new position for {self.config.SYMBOL}.")
                return

            # FEATURE: Funding Rate Avoidance (Perpetuals)
            if self._is_funding_rate_avoidance_active():
                self.logger.warning("Funding rate avoidance active. Skipping new position opening.")
                return

            trade_side = signal_type
            self.logger.info(f"Received {trade_side} signal. Reason: {reason}. Attempting to open {trade_side.lower()} position.")
            subprocess.run(["termux-toast", f"Signal: {trade_side} {self.config.SYMBOL}. Reason: {reason}"])

            # Calculate Stop Loss and Take Profit prices (with DTP)
            stop_loss_price, take_profit_price = self.calculate_trade_sl_tp(trade_side, current_market_price, self.market_data)

            # FEATURE: Volatility-Adjusted Position Sizing - pass current ATR (Snippet 5 robustness check)
            current_atr_for_sizing = Decimal(str(self.market_data['atr'].iloc[-1])) if 'atr' in self.market_data.columns else None

            # Calculate position size in base currency units
            position_qty = self.order_sizer.calculate_position_size_usd(
                symbol=self.config.SYMBOL,
                account_balance_usdt=self.account_balance_usdt,
                risk_percent=Decimal(str(self.config.RISK_PER_TRADE_PCT / 100)),
                entry_price=current_market_price,
                stop_loss_price=stop_loss_price,
                leverage=Decimal(str(self.config.LEVERAGE)),
                current_atr=current_atr_for_sizing # Pass ATR
            )

            if position_qty is not None and position_qty > Decimal('0'):
                order_type_to_place = self.config.ORDER_TYPE_ENUM
                entry_price_to_place = current_market_price # Default for market or if retracement not enabled

                # FEATURE: Signal Retracement Entry
                if self.config.RETRACEMENT_ENTRY_ENABLED:
                    order_type_to_place = OrderType[self.config.RETRACEMENT_ORDER_TYPE.upper()]
                    if trade_side == 'Buy':
                        entry_price_to_place = current_market_price * (Decimal('1') - Decimal(str(self.config.RETRACEMENT_PCT_FROM_CLOSE)))
                    else: # Sell
                        entry_price_to_place = current_market_price * (Decimal('1') + Decimal(str(self.config.RETRACEMENT_PCT_FROM_CLOSE)))

                    entry_price_to_place = self.precision_manager.round_price(self.config.SYMBOL, entry_price_to_place)
                    self.logger.info(f"Placing {order_type_to_place.value} order for retracement at {entry_price_to_place:.{self.bot_state.price_precision}f}.")

                order_result = self.place_order(
                    side=trade_side,
                    qty=position_qty,
                    order_type=order_type_to_place,
                    entry_price=entry_price_to_place if order_type_to_place == OrderType.LIMIT else None, # Only pass price for limit orders
                    stopLoss=stop_loss_price,
                    takeProfit=take_profit_price
                )

                if order_result:
                    if order_result.get('orderStatus') == 'Filled' or self.config.DRY_RUN:
                        # Update internal state based on order result (especially the filled price)
                        filled_price = Decimal(order_result.get('avgPrice', str(current_market_price)))
                        filled_qty = Decimal(order_result.get('cumExecQty', str(position_qty)))

                        self.position_active = True
                        self.current_position_side = trade_side
                        self.current_position_entry_price = filled_price
                        self.current_position_size = filled_qty
                        self.initial_position_qty = filled_qty # Store initial quantity for partial TP
                        self.last_trade_time = now_ts
                        self.last_signal = trade_side
                        self.breakeven_activated[self.config.SYMBOL] = False # Reset single-tier breakeven status for new position
                        self.breakeven_tier_activated[self.config.SYMBOL] = -1 # Reset multi-tier breakeven status for new position (Snippet 10)
                        self.partial_tp_targets_hit[self.config.SYMBOL] = dict.fromkeys(range(len(self.config.PARTIAL_TP_TARGETS)), False) # Reset partial TP status
                        self.pending_retracement_order = None # Clear pending retracement order
                        self.open_trade_kline_ts = self.last_kline_ts # Set timestamp for time-based exit (Snippet 6)

                        self.logger.info(f"{trade_side} order placed and confirmed filled. Entry: {filled_price}, Qty: {filled_qty}.")

                        # Update BotState with new position
                        with self.bot_state.lock:
                            self.bot_state.open_position_qty = filled_qty
                            self.bot_state.open_position_side = trade_side
                            self.bot_state.open_position_entry_price = filled_price
                            self.bot_state.unrealized_pnl = Decimal('0.0') # Start with 0 PnL
                            self.bot_state.unrealized_pnl_pct = Decimal('0.0')

                        # Initialize Ehlers ST trailing stop if enabled (Snippet 4)
                        if self.config.EHLERS_ST_TRAILING_ENABLED:
                            ehlers_st_line = Decimal(str(self.market_data['supertrend_line_value'].iloc[-1]))
                            self.trailing_stop_manager.initialize_trailing_stop(
                                symbol=self.config.SYMBOL,
                                position_side=trade_side,
                                entry_price=filled_price,
                                current_price=current_market_price,
                                trail_percent=0.0, # Not used for Ehlers ST trailing
                                activation_percent=0.0,
                                ehlers_st_trailing_enabled=True,
                                ehlers_st_line_value=ehlers_st_line
                            )

                    elif order_result.get('orderStatus') in ('New', 'Created') and self.config.RETRACEMENT_ENTRY_ENABLED:
                        # If retracement order is pending, store its details
                        self.pending_retracement_order = {
                            'orderId': order_result['orderId'],
                            'side': trade_side,
                            'qty': position_qty,
                            'price': entry_price_to_place,
                            'time_placed_kline_ts': self.last_kline_ts
                        }
                        self.logger.info(f"Retracement limit order {order_result['orderId']} placed and pending fill.")
                    else:
                        self.logger.error(f"Failed to place {trade_side} order.")
                else:
                    self.logger.error(f"Failed to place {trade_side} order.")
            else:
                self.logger.warning(f"Could not calculate a valid position size for the {trade_side} signal. Skipping order placement.")
        else:
            self.logger.info(Fore.WHITE + "No active position and no new signal to act on." + Style.RESET_ALL)
"""
        }
      ]
    },
    {
      "id": 9,
      "name": "Order Book Depth Check for Limit Orders",
      "description": "Before placing a limit order (especially for retracement entries), the bot checks the order book depth at the desired price. This ensures there's sufficient liquidity to fill the order, reducing the chance of partial fills or missed entries in thin markets.",
      "config_changes": [
        {"key": "ORDER_BOOK_DEPTH_CHECK_ENABLED", "type": "bool", "default": false, "description": "Enable/disable order book depth check for limit orders."},
        {"key": "MIN_LIQUIDITY_DEPTH_USD", "type": "float", "default": 50.0, "description": "Minimum liquidity (in USD) required at the limit order price level."}
      ],
      "code_changes": [
        {
          "file_section": "Config class",
          "change_type": "add_field",
          "code": """    ORDER_BOOK_DEPTH_CHECK_ENABLED: bool = field(default=False)
    MIN_LIQUIDITY_DEPTH_USD: float = field(default=50.0)"""
        },
        {
          "file_section": "Config.__post_init__",
          "change_type": "add_load_env",
          "code": """        self.ORDER_BOOK_DEPTH_CHECK_ENABLED = os.getenv("ORDER_BOOK_DEPTH_CHECK_ENABLED", str(self.ORDER_BOOK_DEPTH_CHECK_ENABLED)).lower() in ['true', '1', 't']
        self.MIN_LIQUIDITY_DEPTH_USD = float(os.getenv("MIN_LIQUIDITY_DEPTH_USD", self.MIN_LIQUIDITY_DEPTH_USD))"""
        },
        {
          "file_section": "EhlersSuperTrendBot.__init__",
          "change_type": "add_log",
          "code": """        self.logger.info(f"  Order Book Depth Check: {config.ORDER_BOOK_DEPTH_CHECK_ENABLED}, Min Liquidity: ${config.MIN_LIQUIDITY_DEPTH_USD:.2f}")"""
        },
        {
          "file_section": "BybitClient class",
          "change_type": "add_method",
          "code": """
    def get_orderbook(self, category: str, symbol: str, limit: int = 1) -> dict[str, Any]:
        \"\"\"Fetches order book data.\"\"\"
        return self.session.get_orderbook(category=category, symbol=symbol, limit=limit)
"""
        },
        {
          "file_section": "EhlersSuperTrendBot.place_order",
          "change_type": "modify_function",
          "description": "Add order book depth check for limit orders.",
          "code": """
    def place_order(self, side: str, qty: Decimal, order_type: OrderType,
                   entry_price: Decimal | None = None, stopLoss: Decimal | None = None,
                   takeProfit: Decimal | None = None, reduce_only: bool = False) -> dict | None:
        \"\"\"
        Place an order on Bybit, handling precision and Bybit V5 API parameters.
        Includes verification if the order was actually filled.
        Returns the filled order details on success, None otherwise.
        
        FEATURE: Slippage Tolerance for Market Orders
        Checks for excessive slippage for market orders and logs a warning.
        \"\"\"
        specs = self.precision_manager.get_specs(self.config.SYMBOL)
        if not specs:
            self.logger.error(f"Cannot place order for {self.config.SYMBOL}: Specs not found.")
            return None

        rounded_qty = self.precision_manager.round_quantity(self.config.SYMBOL, qty)
        if rounded_qty <= Decimal('0'):
            self.logger.warning(f"Invalid quantity ({qty} rounded to {rounded_qty}) for order placement in {self.config.SYMBOL}. Aborting order.")
            return None

        # Determine the intended price for market orders for slippage check
        intended_price = entry_price
        if order_type == OrderType.MARKET and intended_price is None:
            intended_price = Decimal(str(self.market_data['close'].iloc[-1])) if not self.market_data.empty else Decimal('0.0')
        if intended_price <= Decimal('0'):
            self.logger.warning("Intended price for market order is zero or not available. Slippage check will be skipped.")

        # FEATURE: Order Book Depth Check for Limit Orders (Snippet 9)
        if self.config.ORDER_BOOK_DEPTH_CHECK_ENABLED and order_type == OrderType.LIMIT and entry_price is not None:
            try:
                # Fetch more depth to account for multiple levels if needed
                orderbook_data = self.api_call(self.bybit_client.get_orderbook, category=specs.category, symbol=self.config.SYMBOL, limit=50) # Increased limit
                if orderbook_data and orderbook_data.get('s', self.config.SYMBOL) == self.config.SYMBOL: # Check symbol match
                    # Bids are for buy orders (asks for sell orders)
                    # For Buy: we are placing a BUY LIMIT order, so we need to check ASK liquidity (sellers)
                    # For Sell: we are placing a SELL LIMIT order, so we need to check BID liquidity (buyers)
                    target_book = orderbook_data.get('a') if side == 'Buy' else orderbook_data.get('b')
                    
                    liquidity_at_price = Decimal('0')
                    for price_level in target_book:
                        level_price = Decimal(price_level[0])
                        level_qty = Decimal(price_level[1])
                        
                        # Check if the price level is at or better than our desired entry price
                        # For Buy Limit: We want an ask at or below our limit price (to get filled)
                        # For Sell Limit: We want a bid at or above our limit price (to get filled)
                        is_at_or_better_price = False
                        if side == 'Buy' and level_price <= entry_price:
                            is_at_or_better_price = True
                        elif side == 'Sell' and level_price >= entry_price:
                            is_at_or_better_price = True

                        if is_at_or_better_price:
                            # Accumulate liquidity for all levels at or better than our price
                            liquidity_at_price += level_qty * level_price # Value in quote currency
                    
                    if liquidity_at_price < Decimal(str(self.config.MIN_LIQUIDITY_DEPTH_USD)):
                        self.logger.warning(Fore.YELLOW + f"Order book depth check failed for {side} limit order at ${entry_price:.{self.bot_state.price_precision}f}. Available liquidity: ${liquidity_at_price:.2f} USD, required: ${self.config.MIN_LIQUIDITY_DEPTH_USD:.2f} USD. Skipping order." + Style.RESET_ALL)
                        return None
                    else:
                        self.logger.info(f"Order book depth check passed for {side} limit order at ${entry_price:.{self.bot_state.price_precision}f}. Available liquidity: ${liquidity_at_price:.2f} USD.")
                else:
                    self.logger.warning("Failed to get valid order book data for depth check.")
            except Exception as e:
                self.logger.error(f"Error during order book depth check: {e}", exc_info=True)
                # Decide whether to proceed or abort on error. For now, proceed with warning.
                self.logger.warning("Proceeding with order placement despite order book depth check error.")

        # Convert Decimal values to string for API
        str_qty = str(rounded_qty)
        str_price = str(self.precision_manager.round_price(self.config.SYMBOL, entry_price)) if entry_price else None
        str_stopLoss = str(self.precision_manager.round_price(self.config.SYMBOL, stopLoss)) if stopLoss else None
        str_takeProfit = str(self.precision_manager.round_price(self.config.SYMBOL, takeProfit)) if takeProfit else None

        self.logger.info(f"Placing order for {self.config.SYMBOL}: Side={side}, Qty={str_qty}, Type={order_type.value}, "
                         f"Price={str_price}, SL={str_stopLoss}, TP={str_takeProfit}, ReduceOnly={reduce_only}")

        if self.config.DRY_RUN:
            self.logger.info(Fore.YELLOW + f"[DRY RUN] Would place {side} order of {str_qty} {self.config.SYMBOL} ({order_type.value})" + Style.RESET_ALL)
            # Simulate a successful order placement for dry run
            simulated_price = entry_price or Decimal(self.market_data['close'].iloc[-1])
            return {'orderId': 'DRY_RUN_ORDER_ID_' + str(int(time.time())), 'orderStatus': 'Filled', 'avgPrice': str(simulated_price), 'cumExecQty': str_qty}

        try:
            order_response = self.api_call(
                self.bybit_client.place_order,
                symbol=self.config.SYMBOL,
                side=side,
                orderType=order_type.value,
                qty=str_qty,
                price=str_price,
                stopLoss=str_stopLoss,
                takeProfit=str_takeProfit,
                reduceOnly=reduce_only,
                category=specs.category,
                timeInForce=self.config.TIME_IN_FORCE,
                closeOnTrigger=False, # Not using this for primary orders
                positionIdx=self.config.POSITION_IDX if self.config.HEDGE_MODE else 0,
                slOrderType='Market', # Always market for SL
                tpOrderType='Limit', # Usually limit for TP
                tpslMode='Full' if (stopLoss is not None or takeProfit is not None) else None
            )

            if order_response and order_response.get('orderId'):
                order_id = order_response['orderId']
                self.logger.info(Fore.GREEN + f"Order spell cast with ID: {order_id}. Awaiting the market's response..." + Style.RESET_ALL)

                # --- VERIFY ORDER EXECUTION ---
                # Poll for order status to confirm fill
                max_retries = 5
                retry_delay = 1 # seconds
                for i in range(max_retries):
                    time.sleep(retry_delay)
                    order_details = self.api_call(self.bybit_client.get_order_history, symbol=self.config.SYMBOL, orderId=order_id, category=specs.category)

                    if order_details and order_details.get('list') and order_details['list']:
                        filled_order = order_details['list'][0]
                        order_status = filled_order.get('orderStatus')

                        if order_status in ('Filled', 'PartiallyFilled'):
                            avg_price_str = filled_order.get('avgPrice')
                            filled_price = Decimal(avg_price_str) if avg_price_str and Decimal(avg_price_str) > Decimal('0') else (entry_price or Decimal(self.market_data['close'].iloc[-1])) # Fallback
                            filled_qty = Decimal(filled_order.get('cumExecQty', '0'))

                            # FEATURE: Slippage Tolerance for Market Orders
                            if order_type == OrderType.MARKET and intended_price is not None and intended_price > Decimal('0'):
                                actual_slippage_pct = abs(filled_price - intended_price) / intended_price
                                if actual_slippage_pct > Decimal(str(self.config.SLIPPAGE_TOLERANCE_PCT)):
                                    self.logger.warning(Fore.YELLOW + f"⚠️ High Slippage Detected for Market Order {order_id}: {actual_slippage_pct*100:.2f}% (Intended: ${intended_price:.{self.bot_state.price_precision}f}, Filled: ${filled_price:.{self.bot_state.price_precision}f}). Tolerance: {self.config.SLIPPAGE_TOLERANCE_PCT*100:.2f}%" + Style.RESET_ALL)
                                    # Depending on policy, might raise an error or just log. For now, log and proceed.
                                else:
                                    self.logger.info(f"Slippage for market order {order_id}: {actual_slippage_pct*100:.2f}% (within tolerance).")


                            self.logger.info(Fore.GREEN + f"✅ Order FILLED: {side} {filled_qty:.{self.bot_state.qty_precision}f} {self.config.SYMBOL} at avg ${filled_price:.{self.bot_state.price_precision}f} (Order ID: {order_id})" + Style.RESET_ALL)
                            subprocess.run(["termux-toast", f"Order FILLED: {side} {self.config.SYMBOL} at {filled_price:.{self.bot_state.price_precision}f}"])
                            if self.sms_notifier.is_enabled:
                                self.sms_notifier.send_trade_alert(side, self.config.SYMBOL, float(filled_price), float(stopLoss or Decimal('0')), float(takeProfit or Decimal('0')), "Order Filled")
                            return filled_order # Return the filled order details
                        elif order_status in ('New', 'Created'):
                            self.logger.debug(f"Order {order_id} still pending, status: {order_status}. Retrying...")
                        else: # Cancelled, Rejected, etc.
                            self.logger.error(Fore.RED + f"Order {order_id} not filled, final status: {order_status}. Manual intervention may be required." + Style.RESET_ALL)
                            subprocess.run(["termux-toast", f"Order NOT FILLED: {self.config.SYMBOL} (ID: {order_id})"])
                            if self.sms_notifier.is_enabled:
                                self.sms_notifier.send_sms(f"CRITICAL: Order {order_id} for {self.config.SYMBOL} NOT FILLED! Status: {order_status}.")
                            # Attempt to cancel if it's still open and not filled
                            self.cancel_order(order_id)
                            return None
                    else:
                        self.logger.debug(f"No order history for {order_id} yet. Retrying...")

                self.logger.error(Fore.RED + f"Order {order_id} not confirmed filled after {max_retries} retries. Manual check needed." + Style.RESET_ALL)
                subprocess.run(["termux-toast", f"Order NOT FILLED: {self.config.SYMBOL} (ID: {order_id})"])
                if self.sms_notifier.is_enabled:
                    self.sms_notifier.send_sms(f"CRITICAL: Order {order_id} for {self.config.SYMBOL} NOT FILLED after retries.")
                return None
            else:
                self.logger.error(Fore.RED + f"Order placement failed: API call returned no order ID or data for {self.config.SYMBOL}." + Style.RESET_ALL)
                if self.sms_notifier.is_enabled:
                    self.sms_notifier.send_sms(f"Order placement failed for {self.config.SYMBOL}: No order ID returned.")
                return None
        except Exception as e:
            self.logger.error(Fore.RED + f"An unforeseen exception occurred during order placement for {self.config.SYMBOL}: {e}" + Style.RESET_ALL)
            if self.sms_notifier.is_enabled:
                self.sms_notifier.send_sms(f"Order exception for {self.config.SYMBOL}: {e}")
            return None
"""
        }
      ]
    },
    {
      "id": 10,
      "name": "Multi-Tier Breakeven Stop Loss",
      "description": "Extends the existing breakeven stop loss to multiple profit tiers. As the position's profit increases and hits predefined thresholds, the stop loss is progressively moved to breakeven plus a small profit offset for each tier, ensuring more robust profit protection.",
      "config_changes": [
        {"key": "MULTI_TIER_BREAKEVEN_ENABLED", "type": "bool", "default": false, "description": "Enable/disable multi-tier breakeven stop loss. Overrides single BREAKEVEN_ENABLED."},
        {"key": "BREAKEVEN_PROFIT_TIERS", "type": "list[dict[str, float]]", "default": [{"profit_pct": 0.005, "offset_pct": 0.0001}, {"profit_pct": 0.01, "offset_pct": 0.0005}], "description": "List of profit tiers (as % of entry price) and their corresponding breakeven offset (as % of entry price)."}
      ],
      "code_changes": [
        {
          "file_section": "Config class",
          "change_type": "add_field",
          "code": """    MULTI_TIER_BREAKEVEN_ENABLED: bool = field(default=False)
    BREAKEVEN_PROFIT_TIERS: list[dict[str, float]] = field(default_factory=lambda: [
        {"profit_pct": 0.005, "offset_pct": 0.0001},
        {"profit_pct": 0.01, "offset_pct": 0.0005}
    ])"""
        },
        {
          "file_section": "Config.__post_init__",
          "change_type": "add_load_env",
          "code": """        self.MULTI_TIER_BREAKEVEN_ENABLED = os.getenv("MULTI_TIER_BREAKEVEN_ENABLED", str(self.MULTI_TIER_BREAKEVEN_ENABLED)).lower() in ['true', '1', 't']
        multi_tier_breakeven_str = os.getenv("BREAKEVEN_PROFIT_TIERS")
        if multi_tier_breakeven_str:
            try:
                self.BREAKEVEN_PROFIT_TIERS = json.loads(multi_tier_breakeven_str)
            except json.JSONDecodeError:
                print(f"Warning: Could not decode BREAKEVEN_PROFIT_TIERS from environment variable: {multi_tier_breakeven_str}. Using default.")
"""
        },
        {
          "file_section": "EhlersSuperTrendBot.__init__",
          "change_type": "add_field",
          "code": "        self.breakeven_tier_activated: dict[str, int] = {} # {symbol: highest_tier_index_activated} (Snippet 10)"
        },
        {
          "file_section": "EhlersSuperTrendBot.__init__",
          "change_type": "add_log",
          "code": """        self.logger.info(f"  Multi-Tier Breakeven: {config.MULTI_TIER_BREAKEVEN_ENABLED}, Tiers: {config.BREAKEVEN_PROFIT_TIERS}")"""
        },
        {
          "file_section": "EhlersSuperTrendBot._manage_breakeven_stop_
