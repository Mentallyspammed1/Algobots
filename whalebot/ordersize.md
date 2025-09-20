The provided Python code (`wb1.0.1.py`) already contains robust implementations for handling decimals, precision, and order sizing for Bybit, using best practices like the `decimal` module and risk-managed position sizing.

Here are the key snippets and explanations:

---

### Snippet 1: Implementing Decimal and Precision

The `decimal` module is used extensively to avoid floating-point inaccuracies inherent with `float` types, which is critical for financial calculations. Precision settings are configurable and applied through quantization.

**Key Code Areas:**

1.  **Global Decimal Context Setup:**
    ```python
    from decimal import ROUND_DOWN, Decimal, getcontext

    # Initialize colorama and set decimal precision
    getcontext().prec = 28 # Sets global precision for new Decimal objects
    init(autoreset=True)
    load_dotenv()
    ```
    *   `getcontext().prec = 28`: This sets the global precision for `Decimal` operations. `28` is a common choice for high precision in financial applications.
    *   `Decimal`: All sensitive numerical values (prices, quantities, balances, PnL) are converted to and stored as `Decimal` objects.

2.  **Configuration for Precision:**
    The `config.json` (or `default_config` in `load_config`) defines specific precision requirements for orders and prices:
    ```python
    # Inside load_config -> default_config
    "trade_management": {
        "enabled": True,
        "account_balance": 1000.0,
        "risk_per_trade_percent": 1.0,
        "stop_loss_atr_multiple": 1.5,
        "take_profit_atr_multiple": 2.0,
        "max_open_positions": 1,
        "order_precision": 5,  # New: Decimal places for order quantity
        "price_precision": 3,  # New: Decimal places for price
        "enable_trailing_stop": True,
        "trailing_stop_atr_multiple": 0.8,
        "break_even_atr_trigger": 0.5
    },
    ```
    *   `order_precision`: Specifies the desired number of decimal places for the order quantity (e.g., `0.00001 BTC`).
    *   `price_precision`: Specifies the desired number of decimal places for prices (e.g., `123.456 USDT`).

3.  **Applying Precision (Quantization):**
    Quantization is used to round `Decimal` values to a specific number of decimal places, typically using `ROUND_DOWN` (truncation) to be conservative.

    **Example from `PositionManager._calculate_order_size`:**
    ```python
    # ... inside PositionManager._calculate_order_size ...
    order_qty = order_value / current_price

    # Round order_qty to appropriate precision for the symbol
    # Ensure precision is at least 1 (e.g., 0.1, 0.01, etc.)
    precision_exponent = max(0, self.order_precision - 1)
    precision_str = "0." + "0" * precision_exponent + "1"
    order_qty = order_qty.quantize(Decimal(precision_str), rounding=ROUND_DOWN)

    self.logger.info(
        f"[{self.symbol}] Calculated order size: {order_qty.normalize()} (Risk: {risk_amount.normalize():.2f} USD)"
    )
    return order_qty
    ```
    *   `precision_str`: Dynamically creates a quantization string like `"0.00001"` based on `order_precision`.
    *   `order_qty.quantize(Decimal(precision_str), rounding=ROUND_DOWN)`: This is the core method that rounds the `order_qty` down to the specified number of decimal places.

    **Example from `PositionManager.open_position` (for prices):**
    ```python
    # ... inside PositionManager.open_position ...
    price_precision_exponent = max(0, self.price_precision - 1)
    price_precision_str = "0." + "0" * price_precision_exponent + "1"

    position = {
        # ...
        "entry_price": current_price.quantize(
            Decimal(price_precision_str), rounding=ROUND_DOWN
        ),
        "qty": order_qty,
        "stop_loss": initial_stop_loss.quantize(
            Decimal(price_precision_str), rounding=ROUND_DOWN
        ),
        "take_profit": take_profit.quantize(
            Decimal(price_precision_str), rounding=ROUND_DOWN
        ),
        # ...
    }
    ```
    *   Similar logic is used to quantize `entry_price`, `stop_loss`, and `take_profit` using `price_precision`.

4.  **API Data Conversion:**
    When fetching data from Bybit, prices and quantities are typically strings. They are converted to `Decimal` immediately upon receipt to ensure all subsequent calculations are precise.

    **Example from `fetch_current_price`:**
    ```python
    def fetch_current_price(symbol: str, logger: logging.Logger) -> Decimal | None:
        # ... API request ...
        if response and response["result"] and response["result"]["list"]:
            price = Decimal(response["result"]["list"][0]["lastPrice"])
            logger.debug(f"Fetched current price for {symbol}: {price}")
            return price
        # ...
    ```
    *   `Decimal(response["result"]["list"][0]["lastPrice"])`: Converts the string price from the API into a `Decimal` object.

**Best Practice Note for Bybit:**
While the current configuration-based precision is good, for a live trading bot, it's crucial to dynamically fetch the *actual* `minPrice`, `tickSize`, `minOrderQty`, and `qtyStep` for the specific trading symbol from Bybit's `/v5/market/instruments-info` endpoint. These values vary by symbol and ensure orders comply with exchange rules. The `quantize` operations should then use these exchange-provided steps.

---

### Snippet 2: Implementing Order Sizing for Bybit

Order sizing in this bot is based on a risk-per-trade percentage and the Average True Range (ATR) to determine stop-loss distance, making it dynamic and adaptable to market volatility.

**Key Code Area:**

The primary logic resides within the `PositionManager` class, specifically the `_calculate_order_size` method:

```python
class PositionManager:
    # ... initialization ...

    def _get_current_balance(self) -> Decimal:
        """Fetch current account balance (simplified for simulation)."""
        # In a real bot, this would query the exchange.
        # For simulation, use configured account balance.
        # Example API call for real balance (needs authentication):
        # endpoint = "/v5/account/wallet-balance"
        # params = {"accountType": "UNIFIED"}
        # response = bybit_request("GET", endpoint, params, signed=True, logger=self.logger)
        # if response and response["result"] and response["result"]["list"]:
        #     for coin_balance in response["result"]["list"][0]["coin"]:
        #         if coin_balance["coin"] == "USDT":
        #             return Decimal(coin_balance["walletBalance"])
        return Decimal(str(self.config["trade_management"]["account_balance"]))

    def _calculate_order_size(
        self, current_price: Decimal, atr_value: Decimal
    ) -> Decimal:
        """Calculate order size based on risk per trade and ATR."""
        if not self.trade_management_enabled:
            return Decimal("0")

        account_balance = self._get_current_balance() # Fetches simulated or actual balance
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
        precision_exponent = max(0, self.order_precision - 1)
        precision_str = "0." + "0" * precision_exponent + "1"
        order_qty = order_qty.quantize(Decimal(precision_str), rounding=ROUND_DOWN)

        self.logger.info(
            f"[{self.symbol}] Calculated order size: {order_qty.normalize()} (Risk: {risk_amount.normalize():.2f} USD)"
        )
        return order_qty
```

**Explanation:**

1.  **`_get_current_balance()`**:
    *   In a live scenario, this method would make an authenticated API call to Bybit (`/v5/account/wallet-balance`) to fetch the available balance in USDT (or other base currency).
    *   In the provided code, it uses a simulated `account_balance` from the `config.json` for backtesting/simulation purposes.

2.  **Risk-Based Sizing (`_calculate_order_size`)**:
    *   **`risk_amount`**: Calculated as `account_balance * risk_per_trade_percent`. This defines the maximum capital the bot is willing to lose on a single trade.
        *   `risk_per_trade_percent` is configurable in `config["trade_management"]["risk_per_trade_percent"]`.
    *   **`stop_loss_distance`**: Determined by `atr_value * stop_loss_atr_multiple`. This dynamically adjusts the stop-loss distance based on current market volatility (ATR).
        *   `atr_value` is the latest ATR reading from the `TradingAnalyzer`.
        *   `stop_loss_atr_multiple` is a configurable multiplier in `config["trade_management"]["stop_loss_atr_multiple"]`.
    *   **`order_value` (in USD/base currency)**: `risk_amount / stop_loss_distance`. This calculates the total value (e.g., in USDT) of the position that can be taken while adhering to the risk limit.
    *   **`order_qty` (in asset quantity, e.g., BTC)**: `order_value / current_price`. This converts the calculated USD value into the actual quantity of the asset to be traded.
    *   **Precision Application**: Finally, `order_qty` is quantized using `self.order_precision` to ensure it meets Bybit's minimum quantity and step requirements (as per configuration).

This approach ensures that position size is dynamically adjusted based on account balance, risk tolerance, and current market volatility, preventing oversized trades during high volatility.
