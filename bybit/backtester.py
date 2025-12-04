import csv
import json
import os
from decimal import Decimal, getcontext

# Set decimal precision
getcontext().prec = 10


class Backtester:
    """Simulates the market-making strategy on historical data."""

    def __init__(self, config, initial_balance=Decimal("1000")):
        """Initialize the backtester with strategy parameters."""
        self.config = config
        self.initial_balance = initial_balance
        self.current_balance = initial_balance

        # Strategy parameters
        self.spread = Decimal(config.get("SPREAD_PERCENTAGE", "0.0005"))
        self.quantity = Decimal(config.get("QUANTITY", "0.1"))
        self.stop_loss_pct = Decimal(config.get("STOP_LOSS_PERCENTAGE", "0.005"))
        self.profit_take_pct = Decimal(config.get("PROFIT_PERCENTAGE", "0.001"))

        # Simulation state
        self.position_size = Decimal("0")
        self.avg_entry_price = Decimal("0")
        self.trade_history = []
        self.fee_rate = Decimal("0.00055")  # Bybit's taker fee for non-VIPs is 0.055%

    def _record_trade(self, timestamp, side, qty, price, fee, pnl=Decimal("0")):
        """Records a single trade event."""
        self.trade_history.append(
            {
                "timestamp": timestamp,
                "side": side,
                "quantity": qty,
                "price": price,
                "fee": fee,
                "pnl": pnl,
            },
        )

    def _update_position(self, side, qty, price):
        """Updates the current position based on a new fill."""
        total_cost_before = self.position_size * self.avg_entry_price

        if self.position_size == 0:
            self.position_size = qty if side == "Buy" else -qty
            self.avg_entry_price = price
            return None

        if (self.position_size > 0 and side == "Buy") or (
            self.position_size < 0 and side == "Sell"
        ):
            # Increasing position size
            new_total_cost = total_cost_before + (qty * price)
            self.position_size += qty if side == "Buy" else -qty
            self.avg_entry_price = new_total_cost / abs(self.position_size)
        else:
            # Reducing position size (realizing PnL)
            realized_pnl = Decimal("0")
            qty_to_close = min(abs(self.position_size), qty)

            if self.position_size > 0:  # Closing a long
                realized_pnl = (price - self.avg_entry_price) * qty_to_close
            else:  # Closing a short
                realized_pnl = (self.avg_entry_price - price) * qty_to_close

            self.position_size -= qty_to_close if side == "Sell" else -qty_to_close
            if self.position_size == 0:
                self.avg_entry_price = Decimal("0")

            return realized_pnl

    def run_simulation(self, historical_data):
        """Main simulation loop."""
        print("Starting backtest simulation...")
        if not historical_data:
            print("Historical data is empty. Cannot run simulation.")
            return

        for i, row in enumerate(historical_data):
            if i == 0:
                continue  # Skip header or first row to have a previous price

            # Extract OHLC data for the current time step
            timestamp = row["timestamp"]
            open_price = Decimal(row["open"])
            high_price = Decimal(row["high"])
            low_price = Decimal(row["low"])
            close_price = Decimal(row["close"])

            # Use close of previous candle as reference mid-price
            prev_close = Decimal(historical_data[i - 1]["close"])
            mid_price = prev_close

            # --- 1. Check for Stop-Loss or Profit-Take on existing position ---
            if self.position_size != 0:
                unrealized_pnl_pct = (
                    (close_price - self.avg_entry_price) / self.avg_entry_price
                    if self.position_size > 0
                    else (self.avg_entry_price - close_price) / self.avg_entry_price
                )

                should_close = False
                if unrealized_pnl_pct >= self.profit_take_pct:
                    side = "Sell" if self.position_size > 0 else "Buy"
                    print(
                        f"{timestamp}: Profit-take triggered at {unrealized_pnl_pct:.2%}. Closing position.",
                    )
                    should_close = True
                elif unrealized_pnl_pct <= -self.stop_loss_pct:
                    side = "Sell" if self.position_size > 0 else "Buy"
                    print(
                        f"{timestamp}: Stop-loss triggered at {unrealized_pnl_pct:.2%}. Closing position.",
                    )
                    should_close = True

                if should_close:
                    fee = abs(self.position_size) * close_price * self.fee_rate
                    pnl = self._update_position(
                        side, abs(self.position_size), close_price,
                    )
                    self.current_balance += pnl - fee
                    self._record_trade(
                        timestamp, side, abs(self.position_size), close_price, fee, pnl,
                    )
                    continue  # Move to next candle after closing position

            # --- 2. Simulate the market making logic ---
            buy_price = mid_price * (Decimal("1") - self.spread)
            sell_price = mid_price * (Decimal("1") + self.spread)

            # Check for fills based on the candle's high/low
            # In this simple model, we assume if the price touches, our order fills.
            buy_filled = low_price <= buy_price
            sell_filled = high_price >= sell_price

            # Handle fills
            if buy_filled:
                fee = self.quantity * buy_price * self.fee_rate
                self.current_balance -= fee
                pnl = self._update_position("Buy", self.quantity, buy_price)
                if pnl:
                    self.current_balance += pnl
                self._record_trade(
                    timestamp, "Buy", self.quantity, buy_price, fee, pnl or Decimal("0"),
                )

            if sell_filled:
                fee = self.quantity * sell_price * self.fee_rate
                self.current_balance -= fee
                pnl = self._update_position("Sell", self.quantity, sell_price)
                if pnl:
                    self.current_balance += pnl
                self._record_trade(
                    timestamp,
                    "Sell",
                    self.quantity,
                    sell_price,
                    fee,
                    pnl or Decimal("0"),
                )

        print("Backtest simulation finished.")

    def print_results(self):
        """Prints a summary of the backtest performance."""
        print("\n--- Backtest Results ---")
        total_pnl = self.current_balance - self.initial_balance
        total_trades = len(self.trade_history)
        total_fees = sum(trade["fee"] for trade in self.trade_history)

        if total_trades == 0:
            print("No trades were executed.")
            return

        winning_trades = sum(1 for trade in self.trade_history if trade["pnl"] > 0)
        losing_trades = sum(1 for trade in self.trade_history if trade["pnl"] < 0)
        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0

        print(f"Initial Balance: {self.initial_balance:.2f} USDT")
        print(f"Final Balance  : {self.current_balance:.2f} USDT")
        print(f"Total PnL      : {total_pnl:.2f} USDT")
        print(f"Total Trades   : {total_trades}")
        print(f"Win Rate       : {win_rate:.2f}%")
        print(f"Total Fees Paid: {total_fees:.4f} USDT")
        print("------------------------")


def load_historical_data(filepath="historical_data.csv"):
    """Loads historical data from a CSV file."""
    if not os.path.exists(filepath):
        print(f"Error: Historical data file not found at '{filepath}'")
        return []

    with open(filepath, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        data = [row for row in reader]
        # Convert numeric strings to Decimals
        for row in data:
            for key in ["open", "high", "low", "close"]:
                if key in row:
                    row[key] = Decimal(row[key])
    return data


def load_config(filepath="config.json"):
    """Loads strategy configuration from a JSON file."""
    if not os.path.exists(filepath):
        print(f"Error: Configuration file not found at '{filepath}'")
        return None

    with open(filepath) as f:
        return json.load(f)


if __name__ == "__main__":
    config = load_config()
    if not config:
        exit()

    historical_data = load_historical_data()
    if not historical_data:
        exit()

    backtester = Backtester(config)
    backtester.run_simulation(historical_data)
    backtester.print_results()
