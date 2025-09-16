To change the order sizing to be a percentage of available balance, we'll introduce a new configuration parameter `order_size_percent_of_balance` and an `order_sizing_strategy` to allow switching between risk-based and percentage-of-balance methods.

Here are the code modifications:

1.  **Update `config.json` default structure:** Add the new sizing parameters to the `trade_management` section in the `load_config` function.
2.  **Modify `PositionManager._calculate_order_size`:** Implement conditional logic to calculate the order quantity based on the chosen strategy.

---

```python
# ============ FILE: wb2.0.py ============

# ... (rest of the imports and initial code) ...

# --- Configuration Management ---
def load_config(filepath: str, logger: logging.Logger) -> dict[str, Any]:
    """Load configuration from JSON file, creating a default if not found."""
    default_config = {
        # Core Settings
        "symbol": "BTCUSDT",
        "interval": "15",
        "loop_delay": LOOP_DELAY_SECONDS,
        "orderbook_limit": 50,
        "testnet": True,
        "timezone": "America/Chicago",
        # Signal Generation
        "signal_score_threshold": 2.0,
        "volume_confirmation_multiplier": 1.5,
        # Position & Risk Management
        "trade_management": {
            "enabled": True,
            "account_balance": 1000.0,  # Simulated balance if not using real API
            "risk_per_trade_percent": 1.0,  # Percentage of account_balance to risk (used in RISK_BASED strategy)
            "order_size_percent_of_balance": 5.0, # NEW: Percentage of available balance to use as collateral for a trade
            "order_sizing_strategy": "PERCENTAGE_OF_BALANCE", # NEW: "RISK_BASED" or "PERCENTAGE_OF_BALANCE"
            "stop_loss_atr_multiple": 1.5,  # Stop loss distance as multiple of ATR
            "take_profit_atr_multiple": 2.0,  # Take profit distance as multiple of ATR
            "trailing_stop_atr_multiple": 0.3,  # Trailing stop distance as multiple of ATR
            "max_open_positions": 1,
            "order_precision": 4,  # Decimal places for order quantity
            "price_precision": 2,  # Decimal places for price
            "leverage": 10,  # Leverage for perpetual contracts
            "order_mode": "MARKET",  # MARKET or LIMIT for entry orders
            "take_profit_type": "MARKET",  # MARKET or LIMIT for TP
            "stop_loss_type": "MARKET",  # MARKET or LIMIT for SL
            "trailing_stop_activation_percent": 0.5,  # % profit to activate trailing stop
        },
        # ... (rest of the default_config) ...
    }
    if not Path(filepath).exists():
        try:
            with Path(filepath).open("w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)
            logger.warning(
                f"{NEON_YELLOW}Configuration file not found. "
                f"Created default config at {filepath} for symbol "
                f"{default_config['symbol']}{RESET}"
            )
            return default_config
        except OSError as e:
            logger.error(f"{NEON_RED}Error creating default config file: {e}{RESET}")
            return default_config

    try:
        with Path(filepath).open(encoding="utf-8") as f:
            config = json.load(f)
        _ensure_config_keys(config, default_config)
        # Save updated config to include any newly added default keys
        with Path(filepath).open("w", encoding="utf-8") as f_write:
            json.dump(config, f_write, indent=4)
        return config
    except (OSError, FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(
            f"{NEON_RED}Error loading config: {e}. Using default and attempting to save.{RESET}"
        )
        try:
            with Path(filepath).open("w", encoding="utf-8") as f_default:
                json.dump(default_config, f_default, indent=4)
        except OSError as e_save:
            logger.error(f"{NEON_RED}Could not save default config: {e_save}{RESET}")
        return default_config


def _ensure_config_keys(config: dict[str, Any], default_config: dict[str, Any]) -> None:
    """Recursively ensure all keys from default_config are in config."""
    for key, default_value in default_config.items():
        if key not in config:
            config[key] = default_value
        elif isinstance(default_value, dict) and isinstance(config.get(key), dict):
            _ensure_config_keys(config[key], default_value)

# ... (rest of the API interaction and PrecisionManager classes) ...


# --- Position Management ---
class PositionManager:
    """Manages open positions, stop-loss, and take-profit levels."""

    def __init__(self, config: dict[str, Any], logger: logging.Logger, symbol: str):
        """Initializes the PositionManager."""
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.open_positions: dict[str, dict] = (
            {}
        )  # Tracks positions opened by the bot locally
        self.trade_management_enabled = config["trade_management"]["enabled"]
        self.precision_manager = PrecisionManager(symbol, logger, config)
        self.max_open_positions = config["trade_management"]["max_open_positions"]
        self.leverage = config["trade_management"]["leverage"]
        self.order_mode = config["trade_management"]["order_mode"]
        self.tp_sl_mode = "Full"  # Default to full for simplicity, can be configured
        self.trailing_stop_activation_percent = (
            Decimal(str(config["trade_management"]["trailing_stop_activation_percent"]))
            / 100
        )

        # Set leverage (only once or when changed)
        if self.trade_management_enabled:
            self._set_leverage()

    def _set_leverage(self) -> None:
        """Set leverage for the trading pair."""
        endpoint = "/v5/position/set-leverage"
        params = {
            "category": "linear",
            "symbol": self.symbol,
            "buyLeverage": str(self.leverage),
            "sellLeverage": str(self.leverage),
        }
        response = bybit_request(
            "POST", endpoint, params, signed=True, logger=self.logger
        )
        if response and response["retCode"] == 0:
            self.logger.info(
                f"{NEON_GREEN}[{self.symbol}] Leverage set to {self.leverage}x.{RESET}"
            )
        else:
            self.logger.error(
                f"{NEON_RED}[{self.symbol}] Failed to set leverage to {self.leverage}x. Error: {response.get('retMsg') if response else 'Unknown'}{RESET}"
            )

    def _get_available_balance(self) -> Decimal:
        """Fetch current available account balance for order sizing."""
        if not self.trade_management_enabled:
            return Decimal(str(self.config["trade_management"]["account_balance"]))

        balance = get_wallet_balance(
            account_type="UNIFIED", coin="USDT", logger=self.logger
        )  # Assuming USDT for linear contracts
        if balance is None:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Failed to fetch actual balance. Using simulated balance for calculation.{RESET}"
            )
            return Decimal(str(self.config["trade_management"]["account_balance"]))
        return balance

    def _calculate_order_size(
        self, current_price: Decimal, atr_value: Decimal
    ) -> Decimal:
        """Calculate order size (quantity of base asset) based on the configured strategy."""
        if not self.trade_management_enabled:
            return Decimal("0")

        account_balance = self._get_available_balance()
        order_qty_base_asset: Decimal  # The final quantity in the base asset (e.g., BTC)

        order_sizing_strategy = self.config["trade_management"].get("order_sizing_strategy", "RISK_BASED") # Default for safety

        if current_price <= Decimal("0"):
            self.logger.error(f"{NEON_RED}[{self.symbol}] Current price is zero or negative. Cannot calculate order quantity.{RESET}")
            return Decimal("0")

        if order_sizing_strategy == "PERCENTAGE_OF_BALANCE":
            order_size_percent = Decimal(str(self.config["trade_management"]["order_size_percent_of_balance"])) / 100
            
            # The capital to be used as margin (collateral) for the trade
            collateral_to_use = account_balance * order_size_percent

            # The notional value of the trade is collateral * leverage
            notional_value = collateral_to_use * self.leverage

            # Calculate the quantity of the base asset
            order_qty_base_asset = notional_value / current_price

            self.logger.info(
                f"[{self.symbol}] Using PERCENTAGE_OF_BALANCE sizing. "
                f"Available balance: {account_balance.normalize():.2f} USDT. "
                f"Order percentage: {order_size_percent * 100}%. "
                f"Collateral: {collateral_to_use.normalize():.2f} USDT. "
                f"Leverage: {self.leverage}x. "
                f"Notional Value: {notional_value.normalize():.2f} USDT. "
                f"Calculated base asset quantity (pre-precision): {order_qty_base_asset.normalize():.8f}"
            )
        elif order_sizing_strategy == "RISK_BASED":
            risk_per_trade_percent = (
                Decimal(str(self.config["trade_management"]["risk_per_trade_percent"]))
                / 100
            )
            stop_loss_atr_multiple = Decimal(
                str(self.config["trade_management"]["stop_loss_atr_multiple"])
            )

            if atr_value <= Decimal("0"):
                self.logger.warning(
                    f"{NEON_YELLOW}[{self.symbol}] ATR value is zero or negative ({atr_value}). Cannot determine stop loss distance for RISK_BASED strategy.{RESET}"
                )
                return Decimal("0")

            # Max capital to risk on this trade (e.g., if SL is hit, this is the max loss in USDT)
            max_risk_amount_usdt = account_balance * risk_per_trade_percent
            
            # The stop loss distance in USD per unit of the base asset (e.g., $ per BTC)
            stop_loss_distance_per_unit_usdt = atr_value * stop_loss_atr_multiple

            if stop_loss_distance_per_unit_usdt <= Decimal("0"):
                self.logger.warning(
                    f"{NEON_YELLOW}[{self.symbol}] Calculated stop loss distance per unit is zero or negative ({stop_loss_distance_per_unit_usdt}). Cannot determine order size for RISK_BASED strategy.{RESET}"
                )
                return Decimal("0")

            # Calculate the quantity of base asset directly:
            # How many units can we trade such that if the SL is hit, the loss does not exceed `max_risk_amount_usdt`?
            # Quantity = Total Risk / (Loss per unit)
            order_qty_base_asset = max_risk_amount_usdt / stop_loss_distance_per_unit_usdt

            self.logger.info(
                f"[{self.symbol}] Using RISK_BASED sizing. "
                f"Max Risk: {max_risk_amount_usdt.normalize():.2f} USDT. "
                f"SL distance per unit: {stop_loss_distance_per_unit_usdt.normalize():.4f} USDT/unit. "
                f"Calculated base asset quantity (pre-precision): {order_qty_base_asset.normalize():.8f}"
            )
        else:
            self.logger.error(f"{NEON_RED}[{self.symbol}] Invalid order_sizing_strategy '{order_sizing_strategy}'. Defaulting to zero order size.{RESET}")
            return Decimal("0")

        # Round order_qty_base_asset to appropriate precision for the symbol
        order_qty_base_asset = self.precision_manager.format_quantity(order_qty_base_asset)

        # Check against min order quantity
        if (
            self.precision_manager.min_order_qty is not None
            and order_qty_base_asset < self.precision_manager.min_order_qty
        ):
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Calculated order quantity ({order_qty_base_asset.normalize()}) is below the minimum "
                f"({self.precision_manager.min_order_qty.normalize()}). Cannot open position.{RESET}"
            )
            return Decimal("0")

        if order_qty_base_asset <= Decimal("0"):
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Calculated order quantity ({order_qty_base_asset.normalize()}) is too small or zero. Cannot open position.{RESET}"
            )
            return Decimal("0")

        self.logger.info(
            f"[{self.symbol}] Final order size: {order_qty_base_asset.normalize()}"
        )
        return order_qty_base_asset

    def open_position(
        self, signal: Literal["BUY", "SELL"], current_price: Decimal, atr_value: Decimal
    ) -> dict | None:
        """Open a new position if conditions allow by placing an order on the exchange."""
        if not self.trade_management_enabled:
            self.logger.info(
                f"{NEON_YELLOW}[{self.symbol}] Trade management is disabled. Skipping opening position.{RESET}"
            )
            return None

        # Check if we already have an open position for this symbol
        if (
            self.symbol in self.open_positions
            and self.open_positions[self.symbol]["status"] == "OPEN"
        ):
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Already have an open position. Max open positions ({self.max_open_positions}) reached. Cannot open new position.{RESET}"
            )
            return None

        # Check against max_open_positions from config
        if (
            self.max_open_positions > 0
            and len(self.open_positions) >= self.max_open_positions
        ):
            self.logger.info(
                f"{NEON_YELLOW}[{self.symbol}] Max open positions ({self.max_open_positions}) reached. Cannot open new position.{RESET}"
            )
            return None

        if signal not in ["BUY", "SELL"]:
            self.logger.debug(f"Invalid signal '{signal}' for opening position.")
            return None

        order_qty = self._calculate_order_size(current_price, atr_value)
        if order_qty <= Decimal("0"):
            return None

        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"])
        )
        take_profit_atr_multiple = Decimal(
            str(self.config["trade_management"]["take_profit_atr_multiple"])
        )

        side = "Buy" if signal == "BUY" else "Sell"
        # For Hedge Mode: 1 for long (Buy), 2 for short (Sell)
        # For One-Way Mode: 0 for both
        # Assuming Hedge Mode based on the error "position idx not match position mode"
        position_idx = 1 if side == "Buy" else 2

        entry_price = (
            current_price  # For Market orders, entry price is roughly current price
        )

        if signal == "BUY":
            stop_loss_price = current_price - (atr_value * stop_loss_atr_multiple)
            take_profit_price = current_price + (atr_value * take_profit_atr_multiple)
        else:  # SELL
            stop_loss_price = current_price + (atr_value * stop_loss_atr_multiple)
            take_profit_price = current_price - (atr_value * take_profit_atr_multiple)

        entry_price = self.precision_manager.format_price(entry_price)
        stop_loss_price = self.precision_manager.format_price(stop_loss_price)
        take_profit_price = self.precision_manager.format_price(take_profit_price)

        self.logger.info(
            f"[{self.symbol}] Attempting to place {side} order: Qty={order_qty.normalize()}, SL={stop_loss_price.normalize()}, TP={take_profit_price.normalize()}"
        )

        placed_order = place_order(
            symbol=self.symbol,
            side=side,
            order_type=self.order_mode,
            qty=order_qty,
            price=entry_price if self.order_mode == "Limit" else None,
            take_profit=take_profit_price,
            stop_loss=stop_loss_price,
            tp_sl_mode=self.tp_sl_mode,
            logger=self.logger,
            position_idx=position_idx,  # Pass position_idx
        )

        if placed_order:
            self.logger.info(
                f"{NEON_GREEN}[{self.symbol}] Successfully initiated {signal} trade with order ID: {placed_order.get('orderId')}{RESET}"
            )
            # For logging/tracking purposes, return a simplified representation
            position_info = {
                "entry_time": datetime.now(TIMEZONE),
                "symbol": self.symbol,
                "side": signal,
                # This might be different from actual fill price for market orders
                "entry_price": entry_price,
                "qty": order_qty,
                "stop_loss": stop_loss_price,
                "take_profit": take_profit_price,
                "status": "OPEN",
                "order_id": placed_order.get("orderId"),
                "is_trailing_activated": False,
                "current_trailing_sl": stop_loss_price,  # Initialize trailing SL to initial SL
            }
            self.open_positions[self.symbol] = (
                position_info  # Track the position locally
            )
            return position_info
        else:
            self.logger.error(
                f"{NEON_RED}[{self.symbol}] Failed to place {signal} order. Check API logs for details.{RESET}"
            )
            return None

    # ... (rest of the PositionManager class) ...

# ... (rest of the file) ...
```

---

**Explanation of Changes:**

1.  **`load_config` (Default Configuration):**
    *   `"order_size_percent_of_balance": 5.0`: This new key is added under `"trade_management"`. It defines what percentage of your available balance you want to allocate as *collateral* for a trade.
    *   `"order_sizing_strategy": "PERCENTAGE_OF_BALANCE"`: This new key specifies which order sizing method to use. It can be `"RISK_BASED"` (the previous method) or `"PERCENTAGE_OF_BALANCE"`. It defaults to `PERCENTAGE_OF_BALANCE` to fulfill the request.

2.  **`PositionManager._calculate_order_size` (Core Logic):**
    *   The function now retrieves the `order_sizing_strategy` from the configuration.
    *   **If `order_sizing_strategy` is `"PERCENTAGE_OF_BALANCE"`:**
        *   It calculates `collateral_to_use` as a direct percentage of the `account_balance`.
        *   Then, it determines the `notional_value` of the trade by multiplying `collateral_to_use` by the configured `leverage`.
        *   Finally, the `order_qty_base_asset` (the number of units of the cryptocurrency to trade) is calculated by dividing the `notional_value` by the `current_price`.
        *   Detailed logging is added to show the steps of this calculation.
    *   **If `order_sizing_strategy` is `"RISK_BASED"` (the original logic):**
        *   It calculates `max_risk_amount_usdt` based on `risk_per_trade_percent` of the `account_balance`.
        *   It then determines `stop_loss_distance_per_unit_usdt` using `atr_value` and `stop_loss_atr_multiple`.
        *   The `order_qty_base_asset` is calculated as `max_risk_amount_usdt / stop_loss_distance_per_unit_usdt`. This formula directly yields the quantity of the asset to trade such that the loss, if the stop-loss is hit, matches the `max_risk_amount_usdt`.
        *   Logging for this strategy is also updated for clarity.
    *   Error handling for `current_price <= Decimal("0")` and `atr_value <= Decimal("0")` is improved for both strategies.
    *   The final calculated `order_qty_base_asset` is then formatted for precision and checked against minimum order quantity, regardless of the strategy used.

**To switch between strategies:**

Edit your `config.json` file and change the value of `"order_sizing_strategy"` under `"trade_management"` to either `"PERCENTAGE_OF_BALANCE"` or `"RISK_BASED"`. You can also adjust `"order_size_percent_of_balance"` (e.g., `5.0` for 5%) for the new strategy.
