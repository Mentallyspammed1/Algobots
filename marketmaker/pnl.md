
mm) make sure pnl is correctly tracked .file marketmaker1.0.py               0
Okay, let's create a `marketmaker1.0.py` file that includes robust PnL (Profit
and Loss) tracking.

This example will focus on a simple market maker strategy that tries to buy
low and sell high, always maintaining a long position, and will meticulously
track its capital, asset holdings, average entry price, realized PnL, and
unrealized PnL.

**Key PnL Tracking Components:**

1.  **Initial Capital:** The starting amount of cash.
2.  **Current Capital:** The cash available after trades and fees.
3.  **Asset Holdings:** The quantity of the asset currently owned.
4.  **Average Entry Price:** The weighted average price at which the current
asset holdings were acquired. This is crucial for calculating PnL correctly.
5.  **Realized PnL:** Profit or loss from positions that have been completely
closed (sold).
6.  **Unrealized PnL:** Profit or loss on open positions (asset holdings)
based on the current market price.
7.  **Total PnL:** Realized PnL + Unrealized PnL.
8.  **Fees:** Transaction costs that impact PnL.
9.  **Trade History:** A log of all transactions for auditing.

---

```python
# marketmaker1.0.py

import uuid
from datetime import datetime
from enum import Enum

class OrderType(Enum):
    BUY = "BUY"
    SELL = "SELL"

class MarketMaker:
    def __init__(self, initial_capital: float, transaction_fee_rate: float = 0.001):
        """
        Initializes the MarketMaker with starting capital and fee rate.

        Args:
            initial_capital (float): The starting amount of cash.
            transaction_fee_rate (float): Percentage fee per trade (e.g., 0.001 for 0.1%).
        """
        if initial_capital <= 0:
            raise ValueError("Initial capital must be positive.")
        if not (0 <= transaction_fee_rate < 1):
            raise ValueError("Transaction fee rate must be between 0 and 1 (exclusive of 1).")

        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.asset_holdings = 0.0  # Quantity of the asset held
        self.average_entry_price = 0.0  # Weighted average price of current asset_holdings
        self.realized_pnl = 0.0    # PnL from closed positions
        self.transaction_fee_rate = transaction_fee_rate
        self.trade_history = []    # List of dictionaries to store trade details

        print(f"MarketMaker initialized with Capital: ${self.capital:,.2f}, Fee Rate: {self.transaction_fee_rate*100:.2f}%")

    def _record_trade(self, order_type: OrderType, quantity: float, price: float, fee: float,
                      executed_capital_change: float, description: str):
        """Internal method to record trade details."""
        self.trade_history.append({
            "trade_id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "order_type": order_type.value,
            "quantity": quantity,
            "price": price,
            "fee": fee,
            "executed_capital_change": executed_capital_change, # How much capital changed due to this trade (incl. fees)
            "current_capital": self.capital,
            "current_asset_holdings": self.asset_holdings,
            "current_avg_entry_price": self.average_entry_price,
            "current_realized_pnl": self.realized_pnl,
            "description": description
        })

    def place_order(self, order_type: OrderType, quantity: float, price: float):
        """
        Executes a buy or sell order and updates PnL tracking.

        Args:
            order_type (OrderType): BUY or SELL.
            quantity (float): The amount of asset to trade.
            price (float): The price per unit of the asset.
        """
        if quantity <= 0 or price <= 0:
            print(f"[{datetime.now().isoformat()}] Invalid order: Quantity and price must be positive.")
            return

        order_value = quantity * price
        fee = order_value * self.transaction_fee_rate
        executed_capital_change = 0

        if order_type == OrderType.BUY:
            total_cost = order_value + fee
            if self.capital < total_cost:
                print(f"[{datetime.now().isoformat()}] Insufficient capital to BUY {quantity:.4f} @ ${price:,.2f} "
                      f"(Cost: ${total_cost:,.2f}, Available: ${self.capital:,.2f})")
                self._record_trade(order_type, quantity, price, fee, -total_cost, "Failed: Insufficient Capital")
                return

            # Update capital and holdings
            self.capital -= total_cost
            executed_capital_change = -total_cost

            # Update average entry price for existing holdings
            if self.asset_holdings > 0:
                self.average_entry_price = (
                    (self.average_entry_price * self.asset_holdings) + (price * quantity)
                ) / (self.asset_holdings + quantity)
            else:
                # First buy, or buying after all holdings were sold
                self.average_entry_price = price

            self.asset_holdings += quantity

            print(f"[{datetime.now().isoformat()}] BOUGHT {quantity:.4f} @ ${price:,.2f} (Fee: ${fee:,.2f}). "
                  f"New Capital: ${self.capital:,.2f}, Holdings: {self.asset_holdings:.4f}, "
                  f"Avg Entry Price: ${self.average_entry_price:,.2f}")
            self._record_trade(order_type, quantity, price, fee, executed_capital_change, "Executed Buy Order")

        elif order_type == OrderType.SELL:
            if self.asset_holdings < quantity:
                print(f"[{datetime.now().isoformat()}] Insufficient holdings to SELL {quantity:.4f} @ ${price:,.2f} "
                      f"(Holdings: {self.asset_holdings:.4f})")
                self._record_trade(order_type, quantity, price, fee, 0, "Failed: Insufficient Holdings")
                return

            # Calculate PnL for the portion being sold
            profit_loss_on_sale = (price - self.average_entry_price) * quantity
            self.realized_pnl += profit_loss_on_sale

            # Update capital and holdings
            revenue_after_fee = order_value - fee
            self.capital += revenue_after_fee
            executed_capital_change = revenue_after_fee

            self.asset_holdings -= quantity

            # If all holdings are sold, reset average entry price
            if self.asset_holdings == 0:
                self.average_entry_price = 0.0
            # If only part of holdings are sold, average entry price remains the same for remaining
            # (as we are selling from the existing pool at its average cost)

            print(f"[{datetime.now().isoformat()}] SOLD {quantity:.4f} @ ${price:,.2f} (Fee: ${fee:,.2f}). "
                  f"Realized PnL from sale: ${profit_loss_on_sale:,.2f}. "
                  f"New Capital: ${self.capital:,.2f}, Holdings: {self.asset_holdings:.4f}, "
                  f"Avg Entry Price: ${self.average_entry_price:,.2f}")
            self._record_trade(order_type, quantity, price, fee, executed_capital_change, "Executed Sell Order")
        else:
            print(f"[{datetime.now().isoformat()}] Invalid order type: {order_type}")

    def calculate_unrealized_pnl(self, current_price: float) -> float:
        """
        Calculates the unrealized PnL based on current asset holdings and market price.
        """
        if self.asset_holdings > 0 and self.average_entry_price > 0:
            return (current_price - self.average_entry_price) * self.asset_holdings
        return 0.0

    def get_account_summary(self, current_market_price: float):
        """
        Prints a summary of the market maker's financial status, including PnL.
        """
        unrealized_pnl = self.calculate_unrealized_pnl(current_market_price)
        total_pnl = self.realized_pnl + unrealized_pnl
        current_equity = self.capital + (self.asset_holdings * current_market_price)

        print("\n" + "="*50)
        print(f"ACCOUNT SUMMARY (at Market Price: ${current_market_price:,.2f})")
        print("="*50)
        print(f"Initial Capital:          ${self.initial_capital:,.2f}")
        print(f"Current Capital (Cash):   ${self.capital:,.2f}")
        print(f"Asset Holdings:           {self.asset_holdings:.4f} units")
        if self.asset_holdings > 0:
            print(f"  - Average Entry Price:  ${self.average_entry_price:,.2f}")
            print(f"  - Value of Holdings:    ${self.asset_holdings * current_market_price:,.2f}")
        else:
            print(f"  - Average Entry Price:  $0.00")
            print(f"  - Value of Holdings:    $0.00")
        print("-" * 50)
        print(f"Realized PnL:             ${self.realized_pnl:,.2f}")
        print(f"Unrealized PnL:           ${unrealized_pnl:,.2f}")
        print(f"TOTAL PnL:                ${total_pnl:,.2f}")
        print("-" * 50)
        print(f"Current Equity:           ${current_equity:,.2f}")
        print(f"Net Change (vs. initial): ${current_equity - self.initial_capital:,.2f}")
        print("="*50 + "\n")

    def get_trade_history(self):
        """Returns the complete trade history."""
        return self.trade_history

# --- Simulation Example ---
if __name__ == "__main__":
    mm = MarketMaker(initial_capital=100000.0, transaction_fee_rate=0.0005) # 0.05% fee

    # --- Market Simulation ---
    print("\n--- Market Simulation Starts ---")

    # 1. Initial Buy
    current_price = 100.0
    mm.place_order(OrderType.BUY, 10.0, current_price) # Buy 10 units at $100
    mm.get_account_summary(current_price)

    # 2. Price drops, buy more to average down
    current_price = 95.0
    mm.place_order(OrderType.BUY, 15.0, current_price) # Buy 15 units at $95
    mm.get_account_summary(current_price)

    # 3. Price recovers, sell a portion for profit
    current_price = 102.0
    mm.place_order(OrderType.SELL, 5.0, current_price) # Sell 5 units at $102
    mm.get_account_summary(current_price)

    # 4. Price drops again, but we hold
    current_price = 98.0
    print(f"[{datetime.now().isoformat()}] Market price dropped to ${current_price:,.2f}. Holding position.")
    mm.get_account_summary(current_price)

    # 5. Price rallies, sell remaining for profit
    current_price = 105.0
    mm.place_order(OrderType.SELL, mm.asset_holdings, current_price) # Sell all remaining holdings
    mm.get_account_summary(current_price)

    # 6. Try to sell more than held (should fail)
    current_price = 106.0
    mm.place_order(OrderType.SELL, 1.0, current_price) # Try to sell 1 unit, but we have 0
    mm.get_account_summary(current_price)

    # 7. Try to buy with insufficient funds (should fail)
    current_price = 1000000.0 # Exaggerated price
    mm.place_order(OrderType.BUY, 10.0, current_price) # Try to buy 10 units
    mm.get_account_summary(current_price)

    print("\n--- Market Simulation Ends ---")

    # You can also inspect the trade history
    # print("\n--- Trade History ---")
    # for trade in mm.get_trade_history():
    #     print(trade)
```

---

### How PnL is tracked:

1.  **`initial_capital`**: Stored at the start.
2.  **`capital`**: Your current cash balance.
    *   Decreases by `(quantity * price) + fee` on a BUY.
    *   Increases by `(quantity * price) - fee` on a SELL.
3.  **`asset_holdings`**: The number of units of the asset you own.
    *   Increases on a BUY.
    *   Decreases on a SELL.
4.  **`average_entry_price`**: This is the most crucial part for accurate PnL.
    *   **On BUY:** If you have existing holdings, the new
`average_entry_price` is calculated as a weighted average: `((old_avg_price *
old_qty) + (new_price * new_qty)) / (old_qty + new_qty)`. If you have no
holdings, it simply becomes the `new_price`.
    *   **On SELL:** The `average_entry_price` of the *remaining* holdings
does **not** change. You are selling units that were acquired at the current
`average_entry_price`. If all holdings are sold, `average_entry_price` is
reset to `0`.
5.  **`realized_pnl`**:
    *   Only updated on a **SELL** order.
    *   Calculated as `(sell_price - average_entry_price_at_time_of_sale) *
quantity_sold`. This profit or loss is "realized" because the position (or
part of it) is now closed.
6.  **`unrealized_pnl`**:
    *   Calculated *on demand* using
`calculate_unrealized_pnl(current_price)`.
    *   It's `(current_market_price - average_entry_price) * asset_holdings`.
This is the floating profit/loss on your open position.
7.  **`total_pnl`**: `realized_pnl + unrealized_pnl`. This gives you the
overall performance.
8.  **`current_equity`**: `capital + (asset_holdings * current_market_price)`.
This is your total wealth if you were to liquidate everything at the current
market price.

This `MarketMaker` class provides a solid foundation for tracking PnL
accurately for a single asset, handling varying trade prices, quantities, and
transaction fees. You can extend it to include more complex features like
short-selling, multiple assets, different order types (limit, market), etc.
