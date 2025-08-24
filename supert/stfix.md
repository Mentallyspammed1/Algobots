```json
[
  {
    "snippet_id": "fix_1_decimal_consistency",
    "description": "Ensure consistent use of `Decimal` for all financial calculations to prevent floating-point precision errors. The `SupertrendBot.calculate_position_size_usd` method currently converts `current_price` and `stop_loss_price` to `float` before passing them to `OrderSizingCalculator.calculate_position_size_usd`, which then re-converts them to `Decimal`.",
    "file": "st2.1.py",
    "line_start": 986,
    "line_end": 990,
    "suggested_fix": "Modify `SupertrendBot.calculate_position_size_usd` to pass `Decimal` objects directly to `order_sizer.calculate_position_size_usd`. The `current_price` and `stop_loss_price` should be `Decimal` throughout the calculation chain.",
    "code_change": "```python\n                # Calculate position size in base currency units\n                position_qty = self.calculate_position_size_usd(\n                    entry_price=current_price, # Pass Decimal directly\n                    stop_loss_price=stop_loss_price # Pass Decimal directly\n                )\n```\nAnd similarly for the SELL signal block."
  },
  {
    "snippet_id": "fix_2_trailing_stop_activation_logic",
    "description": "The `TrailingStopManager.initialize_trailing_stop` method uses the same `trail_percent` for both the actual trailing distance and the `activation_percent`. This means the trailing stop activates as soon as the price moves `TRAILING_STOP_PCT` in profit, which might be too aggressive or not align with typical trailing stop strategies where activation is a higher profit threshold.",
    "file": "st2.1.py",
    "line_start": 447,
    "line_end": 448,
    "suggested_fix": "Introduce a separate configuration parameter for `TRAILING_STOP_ACTIVATION_PCT` in the `Config` class. Then, pass this distinct value to `initialize_trailing_stop` for `activation_percent`.",
    "code_change": "```python\n# In Config class:\nTRAILING_STOP_ACTIVATION_PCT: float = field(default=0.01) # e.g., 1% activation profit\n\n# In SupertrendBot.execute_trade_based_on_signal (and initialize_trailing_stop method signature):\n                                        trail_percent=self.config.TRAILING_STOP_PCT * 100,\n                                        activation_percent=self.config.TRAILING_STOP_ACTIVATION_PCT * 100\n```"
  },
  {
    "snippet_id": "fix_3_place_order_spot_tpsl",
    "description": "Bybit's `place-order` endpoint for `Category.SPOT` does not directly support `stopLoss` or `takeProfit` parameters. Including them in the `params` dictionary for spot orders will result in an API error.",
    "file": "st2.1.py",
    "line_start": 709,
    "line_end": 724,
    "suggested_fix": "Conditionally add `stopLoss` and `takeProfit` parameters only if the trading category is not `SPOT`. For spot, TP/SL typically need to be placed as separate conditional orders.",
    "code_change": "```python\n            # Add stop loss if provided (only for derivatives)\n            if specs.category != 'spot' and stop_loss_price is not None:\n                rounded_sl = self.precision_manager.round_price(self.config.SYMBOL, stop_loss_price)\n                if rounded_sl > 0:\n                    params[\"stopLoss\"] = str(rounded_sl)\n                    params[\"slOrderType\"] = \"Market\"\n\n            # Add take profit if provided (only for derivatives)\n            if specs.category != 'spot' and take_profit_price is not None:\n                rounded_tp = self.precision_manager.round_price(self.config.SYMBOL, take_profit_price)\n                if rounded_tp > 0:\n                    params[\"takeProfit\"] = str(rounded_tp)\n                    params[\"tpOrderType\"] = \"Limit\"\n\n            # Set TPSL mode if either SL or TP is provided (only for derivatives)\n            if specs.category != 'spot' and (\"stopLoss\" in params or \"takeProfit\" in params):\n                params[\"tpslMode\"] = \"Full\"\n```"
  },
  {
    "snippet_id": "fix_4_leverage_logging_for_spot",
    "description": "The `Config.__post_init__` method correctly forces `LEVERAGE` to 1 for `Category.SPOT`. However, the `SupertrendBot.__init__` method logs `config.LEVERAGE` which might still reflect the original configured value (e.g., 5x) before it was overridden, leading to misleading log messages.",
    "file": "st2.1.py",
    "line_start": 506,
    "line_end": 506,
    "suggested_fix": "Modify the `SupertrendBot.__init__` log message to explicitly state the leverage for spot trading if the category is spot, or ensure `config.LEVERAGE` is updated and reflects the actual value after `__post_init__`.",
    "code_change": "```python\n        self.logger.info(f\"  Leverage: {config.LEVERAGE}x {'(forced to 1x for SPOT)' if config.CATEGORY_ENUM == Category.SPOT else ''}\")\n```"
  },
  {
    "snippet_id": "fix_5_indicator_fallback_robustness",
    "description": "If `pandas_ta.supertrend` fails or returns an empty DataFrame in `calculate_indicators`, the method falls back to setting `supertrend` to `df['close']` and `supertrend_direction` to 0. This can lead to misleading `NEUTRAL` signals or incorrect calculations rather than indicating a data issue.",
    "file": "st2.1.py",
    "line_start": 612,
    "line_end": 618,
    "suggested_fix": "Instead of a potentially misleading fallback, if indicator calculation fails or returns empty, return an empty DataFrame or raise an exception to signal a critical data issue, allowing the calling function (`run_strategy`) to handle it more explicitly (e.g., skip the current loop or log a critical error).",
    "code_change": "```python\n            if st_results is None or st_results.empty:\n                self.logger.error(\"Supertrend calculation failed or returned empty DataFrame. Returning empty DataFrame.\")\n                return pd.DataFrame() # Return empty DataFrame to signal failure\n            # ... rest of the logic ...\n\n            # If any required indicator columns are still missing after calculation and dropna\n            required_indicator_cols = ['supertrend', 'supertrend_direction', 'atr']\n            if not all(col in df.columns for col in required_indicator_cols):\n                self.logger.error(\"Missing essential indicator columns after calculation. Returning empty DataFrame.\")\n                return pd.DataFrame()\n```"
  },
  {
    "snippet_id": "fix_6_sl_tp_rounding_strategy",
    "description": "The `PrecisionManager._round_decimal` uses `ROUND_DOWN` universally. For stop-loss and take-profit prices, the rounding direction should be carefully chosen to ensure safety and optimal execution. For example, a long position's stop-loss should ideally be rounded *up* (towards the entry price, making it a 'tighter' stop) to minimize potential loss, while a short position's stop-loss should be rounded *down*.",
    "file": "st2.1.py",
    "line_start": 361,
    "line_end": 379,
    "suggested_fix": "Introduce a specific `round_stop_loss` and `round_take_profit` method in `PrecisionManager` that takes the position `side` into account for rounding. For a long position, `stopLoss` should be rounded up (towards entry) and `takeProfit` rounded down (towards entry). For a short, `stopLoss` rounded down and `takeProfit` rounded up. This ensures the stop is safer and the take profit is more conservative.",
    "code_change": "```python\n# In PrecisionManager class:\n    def round_stop_loss(self, symbol: str, price: float | Decimal, side: str) -> Decimal:\n        specs = self.get_specs(symbol)\n        if not specs: return Decimal(str(price))\n        price_decimal = Decimal(str(price))\n        tick_size = specs.tick_size\n        if side == 'Buy': # Long position, SL should be rounded UP (towards entry/less loss)\n            return price_decimal.quantize(tick_size, rounding=ROUND_UP)\n        else: # Sell position, SL should be rounded DOWN (towards entry/less loss)\n            return price_decimal.quantize(tick_size, rounding=ROUND_DOWN)\n\n    def round_take_profit(self, symbol: str, price: float | Decimal, side: str) -> Decimal:\n        specs = self.get_specs(symbol)\n        if not specs: return Decimal(str(price))\n        price_decimal = Decimal(str(price))\n        tick_size = specs.tick_size\n        if side == 'Buy': # Long position, TP should be rounded DOWN (towards entry/more likely to hit)\n            return price_decimal.quantize(tick_size, rounding=ROUND_DOWN)\n        else: # Sell position, TP should be rounded UP (towards entry/more likely to hit)\n            return price_decimal.quantize(tick_size, rounding=ROUND_UP)\n\n# Then, in place_order and update_stop_loss, use these specific methods:\n# Example in place_order:\n            if stop_loss_price is not None:\n                rounded_sl = self.precision_manager.round_stop_loss(self.config.SYMBOL, stop_loss_price, side)\n            if take_profit_price is not None:\n                rounded_tp = self.precision_manager.round_take_profit(self.config.SYMBOL, take_profit_price, side)\n```"
  },
  {
    "snippet_id": "fix_7_daily_loss_limit_initialization",
    "description": "If `start_balance_usdt` is zero or not initialized correctly, the `check_daily_loss_limit` method logs a warning and returns `True`, effectively bypassing the daily loss check. This means the bot could continue trading without this crucial safety mechanism if the initial balance fetch fails.",
    "file": "st2.1.py",
    "line_start": 670,
    "line_end": 672,
    "suggested_fix": "Modify `check_daily_loss_limit` to return `False` (indicating the limit is effectively 'hit' or cannot be verified) if `start_balance_usdt` is invalid, and ensure the `run_strategy` method halts if `start_balance_usdt` cannot be determined.",
    "code_change": "```python\n    def check_daily_loss_limit(self) -> bool:\n        if self.start_balance_usdt <= 0: # If start balance is not set or invalid, cannot check limit\n            self.logger.critical(\"Start balance not initialized or zero. Daily loss limit cannot be checked. Halting trading.\")\n            return False # Critical failure, assume limit hit or cannot trade\n        # ... rest of the logic ...\n\n# In run_strategy, after initial balance fetch:\n            if initial_balance <= 0:\n                self.logger.critical(\"Failed to get initial account balance or balance is zero. Bot cannot proceed.\")\n                return # Halt bot if initial balance is invalid\n```"
  },
  {
    "snippet_id": "fix_8_trailing_stop_reinitialization",
    "description": "In `get_positions`, the trailing stop is initialized only if `current_stop == 0`. If the bot restarts with an active position that already has an initial stop-loss (even if not a trailing one), the `current_stop` might not be zero, preventing the trailing stop from being correctly initialized or updated based on the current market price.",
    "file": "st2.1.py",
    "line_start": 822,
    "line_end": 829,
    "suggested_fix": "Modify the trailing stop initialization logic in `get_positions` to check if a trailing stop *should* be active for the current position, regardless of the `current_stop` value. If a position is active and trailing stops are enabled, always ensure the `TrailingStopManager` has the latest position data and can update its state.",
    "code_change": "```python\n                            # Initialize or update trailing stop if active and configured\n                            if self.config.TRAILING_STOP_PCT > 0 and self.config.ORDER_TYPE_ENUM == OrderType.MARKET:\n                                mark_price_str = pos.get('markPrice')\n                                if mark_price_str:\n                                    current_mark_price = Decimal(mark_price_str)\n                                    # Always ensure trailing stop is initialized/updated for an active position\n                                    # This will re-initialize if not present or update if conditions are met.\n                                    self.logger.info(f\"Ensuring trailing stop for {self.config.SYMBOL} at entry {self.current_position_entry_price:.4f}\")\n                                    self.trailing_stop_manager.initialize_trailing_stop(\n                                        symbol=self.config.SYMBOL,\n                                        position_side=pos['side'],\n                                        entry_price=self.current_position_entry_price,\n                                        current_price=current_mark_price,\n                                        trail_percent=self.config.TRAILING_STOP_PCT * 100,\n                                        activation_percent=self.config.TRAILING_STOP_ACTIVATION_PCT * 100 # Assuming fix_2 is applied\n                                    )\n                                else:\n                                    self.logger.warning(f\"Mark price not available for {self.config.SYMBOL} position, cannot manage trailing stop.\")\n```"
  },
  {
    "snippet_id": "fix_9_config_max_min_position_enforcement",
    "description": "The `Config.MAX_POSITION_SIZE_USD` and `Config.MIN_POSITION_SIZE_USD` are defined but not actively enforced in `OrderSizingCalculator`. The calculator primarily relies on `InstrumentSpecs` values (`max_position_value`, `min_order_qty`, `max_order_qty`), which might be different from the bot's configured risk limits. This means the bot's own configured max/min position size might not be respected.",
    "file": "st2.1.py",
    "line_start": 418,
    "line_end": 422,
    "suggested_fix": "Modify `OrderSizingCalculator.calculate_position_size_usd` to also consider and enforce the bot's configured `MAX_POSITION_SIZE_USD` and `MIN_POSITION_SIZE_USD` values, in addition to the exchange's instrument specifications.",
    "code_change": "```python\n    def calculate_position_size_usd(\n        self,\n        symbol: str,\n        account_balance_usdt: Decimal,\n        risk_percent: Decimal,\n        entry_price: Decimal,\n        stop_loss_price: Decimal,\n        leverage: Decimal,\n        bot_max_position_usd: Decimal, # Add bot-level max/min as parameters\n        bot_min_position_usd: Decimal\n    ) -> Optional[Decimal]:\n        # ... existing logic ...\n\n        # Cap the needed position value by maximum tradeable value, Bybit's limits, AND bot's configured limits\n        position_value_usd = min(\n            position_value_needed_usd,\n            max_tradeable_value_usd,\n            specs.max_position_value, # Bybit's specific max order value\n            bot_max_position_usd # Bot's configured max position value\n        )\n\n        # Ensure minimum position value is met (considering both Bybit's and bot's min)\n        min_allowed_position_value = max(specs.min_position_value, bot_min_position_usd)\n        if position_value_usd < min_allowed_position_value:\n            self.logger.warning(f\"Calculated position value ({position_value_usd:.4f} USD) is below minimum ({min_allowed_position_value:.4f} USD). Using minimum.\")\n            position_value_usd = min_allowed_position_value\n\n        # ... rest of the logic ...\n\n# Then update the call in SupertrendBot.calculate_position_size_usd:\n            quantity = self.order_sizer.calculate_position_size_usd(\n                symbol=self.config.SYMBOL,\n                account_balance_usdt=current_balance,\n                risk_percent=risk_pct,\n                entry_price=entry_price_dec,\n                stop_loss_price=stop_loss_price_dec,\n                leverage=leverage_dec,\n                bot_max_position_usd=Decimal(str(self.config.MAX_POSITION_SIZE_USD)),\n                bot_min_position_usd=Decimal(str(self.config.MIN_POSITION_SIZE_USD))\n            )\n```"
  },
  {
    "snippet_id": "fix_10_get_ticker_robustness",
    "description": "In `execute_trade_based_on_signal`, if `get_ticker` returns a ticker dictionary but `lastPrice` is missing or empty, the bot will log a warning and return. While the check `if not current_price_str` handles this, it's good practice to ensure the `ticker` object itself is valid and contains essential data before attempting to extract specific keys, or to handle the `KeyError` more explicitly if `get('lastPrice')` was not used.",
    "file": "st2.1.py",
    "line_start": 940,
    "line_end": 944,
    "suggested_fix": "Enhance the `get_ticker` method to return `None` if the `list` of tickers is empty or if the first ticker in the list does not contain a `lastPrice`, making the check in `execute_trade_based_on_signal` more robust.",
    "code_change": "```python\n    def get_ticker(self) -> Optional[dict]:\n        # ... existing code ...\n            if tickers:\n                # Ensure 'lastPrice' exists in the first ticker\n                if 'lastPrice' in tickers[0]:\n                    return tickers[0] # Expecting a single ticker for the specified symbol\n                else:\n                    self.logger.warning(f\"Ticker data for {self.config.SYMBOL} is missing 'lastPrice'.\")\n                    return None\n            else:\n                self.logger.warning(f\"Ticker data list is empty for {self.config.SYMBOL}.\")\n                return None\n        # ... rest of the code ...\n\n# No change needed in execute_trade_based_on_signal as `if not ticker:` and `if not current_price_str:` already cover this, \n# but the fix makes the `get_ticker` method itself more self-contained in its validation.\n```"
  }
]
```
