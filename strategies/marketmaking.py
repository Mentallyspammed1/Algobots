import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Literal


# --- Configuration ---
@dataclass
class StrategyConfig:
    """Configuration for the Market Making Strategy."""
    symbol: str = "BTC/USD"
    base_currency: str = "BTC"
    quote_currency: str = "USD"
    initial_balance_base: float = 0.5  # Initial BTC
    initial_balance_quote: float = 10000.0 # Initial USD

    # Core Market Making Parameters
    spread_bps: float = 10  # Basis points (0.1% for 10)
    order_size_base: float = 0.01 # Size of each order in base currency (e.g., BTC)
    refresh_interval_sec: int = 5 # How often to refresh orders

    # Inventory Management (Advanced)
    target_inventory_base: float = 0.0 # Desired BTC holdings (e.g., 0 for neutral)
    max_inventory_deviation_base: float = 0.1 # Max BTC deviation before aggressive rebalancing
    inventory_bias_factor: float = 0.5 # How much to adjust prices based on inventory deviation (e.g., 0.1 means 10% of price diff)

    # Risk Management (Advanced)
    max_exposure_usd: float = 20000.0 # Max total value of holdings in USD
    max_loss_per_day_usd: float = 500.0 # Simple daily loss limit (requires PnL tracking)
    min_order_price: float = 1000.0 # Safety floor for order prices
    max_order_price: float = 100000.0 # Safety ceiling for order prices

    # Order Management
    max_open_orders_per_side: int = 1 # How many orders to keep active on each side
    cancel_stale_orders_after_sec: int = 60 # Cancel orders older than this (if not filled)

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("marketmaking.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Mock Exchange Interface (Simulated for testing) ---
# In a real scenario, this would be an actual API client (e.g., ccxt, custom REST/WebSocket)

@dataclass
class Order:
    order_id: str
    symbol: str
    type: Literal['limit']
    side: Literal['buy', 'sell']
    price: float
    amount: float
    filled_amount: float = 0.0
    status: Literal['open', 'filled', 'partial_fill', 'canceled'] = 'open'
    timestamp: float = field(default_factory=time.time)

class MockExchange:
    """A simulated exchange for testing the market making strategy."""
    def __init__(self, initial_balance_base: float, initial_balance_quote: float):
        self._order_book: dict[str, dict[str, float]] = {
            "BTC/USD": {"bid": 30000.0, "ask": 30010.0}
        }
        self._balances: dict[str, float] = {
            "BTC": initial_balance_base,
            "USD": initial_balance_quote,
        }
        self._open_orders: dict[str, Order] = {}
        self._trade_history: list[dict] = []
        self._last_price_update_time = time.time()
        logger.info(f"MockExchange initialized with balances: {self._balances}")

    def get_order_book(self, symbol: str) -> dict[str, float] | None:
        """Returns the current bid and ask prices."""
        if symbol not in self._order_book:
            logger.warning(f"Order book for {symbol} not found.")
            return None

        # Simulate slight price movement over time
        self._simulate_price_movement(symbol)

        return self._order_book[symbol]

    def get_balance(self, currency: str) -> float:
        """Returns the available balance for a given currency."""
        return self._balances.get(currency, 0.0)

    def place_order(self, symbol: str, type: str, side: str, price: float, amount: float) -> Order | None:
        """Simulates placing an order."""
        if type != 'limit':
            logger.error("MockExchange only supports 'limit' orders.")
            return None

        order_id = str(uuid.uuid4())
        order = Order(order_id, symbol, type, side, price, amount)
        self._open_orders[order_id] = order
        logger.info(f"Placed {side} order {order_id} for {amount} {symbol.split('/')[0]} @ {price}")
        self._process_order(order) # Try to fill immediately
        return order

    def cancel_order(self, order_id: str) -> bool:
        """Simulates canceling an order."""
        if order_id in self._open_orders:
            order = self._open_orders[order_id]
            if order.status == 'open' or order.status == 'partial_fill':
                order.status = 'canceled'
                logger.info(f"Canceled order {order_id}")
                del self._open_orders[order_id]
                return True
            else:
                logger.warning(f"Cannot cancel order {order_id} in status: {order.status}")
                return False
        logger.warning(f"Order {order_id} not found for cancellation.")
        return False

    def get_open_orders(self, symbol: str) -> list[Order]:
        """Returns a list of currently open orders for a symbol."""
        return [order for order in self._open_orders.values() if order.symbol == symbol and order.status in ['open', 'partial_fill']]

    def _simulate_price_movement(self, symbol: str):
        """Simulates minor, random price fluctuations."""
        if time.time() - self._last_price_update_time < 1: # Update max once per second
            return

        current_bid = self._order_book[symbol]["bid"]
        current_ask = self._order_book[symbol]["ask"]
        mid = (current_bid + current_ask) / 2

        # Small random walk
        change_percent = (random.random() - 0.5) * 0.0002 # +/- 0.01%
        new_mid = mid * (1 + change_percent)

        # Keep a small, fixed spread for simulation
        sim_spread = 10.0 # $10 spread
        self._order_book[symbol]["bid"] = new_mid - sim_spread / 2
        self._order_book[symbol]["ask"] = new_mid + sim_spread / 2
        self._last_price_update_time = time.time()

    def _process_order(self, order: Order):
        """Internal function to simulate order filling."""
        order_book = self._order_book[order.symbol]

        if order.side == 'buy':
            # Check if order can be filled by current ask
            if order.price >= order_book["ask"]:
                fill_price = order_book["ask"]
                fill_amount = min(order.amount - order.filled_amount, order.amount) # For simplicity, fill fully

                self._balances[order.symbol.split('/')[0]] += fill_amount
                self._balances[order.symbol.split('/')[1]] -= fill_amount * fill_price

                order.filled_amount += fill_amount
                order.status = 'filled' if order.filled_amount == order.amount else 'partial_fill'

                trade = {
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "side": order.side,
                    "price": fill_price,
                    "amount": fill_amount,
                    "timestamp": time.time()
                }
                self._trade_history.append(trade)
                logger.info(f"Filled BUY order {order.order_id}: {fill_amount} @ {fill_price}. New balances: {self._balances}")
                if order.status == 'filled' and order.order_id in self._open_orders:
                    del self._open_orders[order.order_id] # Remove filled order

        elif order.side == 'sell':
            # Check if order can be filled by current bid
            if order.price <= order_book["bid"]:
                fill_price = order_book["bid"]
                fill_amount = min(order.amount - order.filled_amount, order.amount)

                self._balances[order.symbol.split('/')[0]] -= fill_amount
                self._balances[order.symbol.split('/')[1]] += fill_amount * fill_price

                order.filled_amount += fill_amount
                order.status = 'filled' if order.filled_amount == order.amount else 'partial_fill'

                trade = {
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "side": order.side,
                    "price": fill_price,
                    "amount": fill_amount,
                    "timestamp": time.time()
                }
                self._trade_history.append(trade)
                logger.info(f"Filled SELL order {order.order_id}: {fill_amount} @ {fill_price}. New balances: {self._balances}")
                if order.status == 'filled' and order.order_id in self._open_orders:
                    del self._open_orders[order.order_id] # Remove filled order

# --- Market Making Strategy ---
class MarketMakingStrategy:
    def __init__(self, exchange: MockExchange, config: StrategyConfig):
        self.exchange = exchange
        self.config = config
        self.running = False
        self.last_mid_price: float | None = None
        self.current_position_base: float = 0.0
        self.daily_pnl_usd: float = 0.0 # Simplified, real PnL needs more tracking
        self.last_pnl_reset_day: int = time.gmtime().tm_yday

        logger.info(f"MarketMakingStrategy initialized for {config.symbol}")

    def _get_market_data(self) -> tuple[float, float] | None:
        """Fetches bid and ask from the exchange."""
        try:
            order_book = self.exchange.get_order_book(self.config.symbol)
            if order_book:
                bid = order_book["bid"]
                ask = order_book["ask"]
                self.last_mid_price = (bid + ask) / 2
                return bid, ask
            else:
                logger.warning("Could not retrieve order book.")
                return None
        except Exception as e:
            logger.error(f"Error getting market data: {e}")
            return None

    def _update_position(self):
        """Updates the current base currency position from exchange balance."""
        self.current_position_base = self.exchange.get_balance(self.config.base_currency)
        logger.debug(f"Current {self.config.base_currency} position: {self.current_position_base:.4f}")

    def _calculate_target_prices(self, bid: float, ask: float) -> tuple[float, float]:
        """
        Calculates target buy and sell prices based on mid-price, spread,
        and inventory deviation.
        """
        mid_price = (bid + ask) / 2
        spread_abs = mid_price * (self.config.spread_bps / 10000)

        buy_price = mid_price - spread_abs / 2
        sell_price = mid_price + spread_abs / 2

        # --- Inventory Management Logic ---
        # Adjust prices to push inventory towards target
        deviation = self.current_position_base - self.config.target_inventory_base

        if abs(deviation) > self.config.max_inventory_deviation_base:
            logger.warning(f"Inventory deviation high: {deviation:.4f} {self.config.base_currency}. Adjusting prices aggressively.")
            # If we have too much base currency (long), lower sell price, raise buy price (to sell more)
            if deviation > 0: # We are long base currency
                adjustment = deviation * self.config.inventory_bias_factor * mid_price
                buy_price += adjustment # Make buy less attractive
                sell_price -= adjustment # Make sell more attractive
            # If we have too little base currency (short), raise buy price, lower sell price (to buy more)
            elif deviation < 0: # We are short base currency
                adjustment = abs(deviation) * self.config.inventory_bias_factor * mid_price
                buy_price -= adjustment # Make buy more attractive
                sell_price += adjustment # Make sell less attractive

        # Apply safety limits
        buy_price = max(buy_price, self.config.min_order_price)
        sell_price = min(sell_price, self.config.max_order_price)

        return round(buy_price, 2), round(sell_price, 2)

    def _manage_orders(self, target_buy_price: float, target_sell_price: float):
        """
        Cancels stale orders and places new bid/ask orders.
        """
        open_orders = self.exchange.get_open_orders(self.config.symbol)

        # Cancel stale/out-of-range orders
        orders_to_cancel = []
        for order in open_orders:
            if order.status == 'open' and (
                (order.side == 'buy' and order.price > target_buy_price) or
                (order.side == 'sell' and order.price < target_sell_price) or
                (time.time() - order.timestamp > self.config.cancel_stale_orders_after_sec)
            ):
                orders_to_cancel.append(order.order_id)

        for order_id in orders_to_cancel:
            self.exchange.cancel_order(order_id)

        # Re-fetch open orders after cancellation
        open_orders = self.exchange.get_open_orders(self.config.symbol)
        num_buy_orders = sum(1 for o in open_orders if o.side == 'buy')
        num_sell_orders = sum(1 for o in open_orders if o.side == 'sell')

        # Place new buy order if needed
        if num_buy_orders < self.config.max_open_orders_per_side:
            # Check if we have enough quote currency (e.g., USD) to place a buy order
            required_quote = target_buy_price * self.config.order_size_base
            if self.exchange.get_balance(self.config.quote_currency) >= required_quote:
                self.exchange.place_order(
                    self.config.symbol, 'limit', 'buy', target_buy_price, self.config.order_size_base
                )
            else:
                logger.warning(f"Insufficient {self.config.quote_currency} balance ({self.exchange.get_balance(self.config.quote_currency):.2f}) to place buy order for {required_quote:.2f}.")

        # Place new sell order if needed
        if num_sell_orders < self.config.max_open_orders_per_side:
            # Check if we have enough base currency (e.g., BTC) to place a sell order
            if self.exchange.get_balance(self.config.base_currency) >= self.config.order_size_base:
                self.exchange.place_order(
                    self.config.symbol, 'limit', 'sell', target_sell_price, self.config.order_size_base
                )
            else:
                logger.warning(f"Insufficient {self.config.base_currency} balance ({self.exchange.get_balance(self.config.base_currency):.4f}) to place sell order for {self.config.order_size_base:.4f}.")

    def _check_risk_limits(self) -> bool:
        """
        Checks if any risk limits have been breached.
        Returns True if limits are safe, False otherwise.
        """
        # --- Max Exposure Check ---
        current_base_value_usd = self.current_position_base * (self.last_mid_price if self.last_mid_price else 0)
        current_quote_value_usd = self.exchange.get_balance(self.config.quote_currency)
        total_exposure_usd = current_base_value_usd + current_quote_value_usd # Simplified, often includes open orders

        if total_exposure_usd > self.config.max_exposure_usd:
            logger.critical(f"Max exposure limit breached! {total_exposure_usd:.2f} USD > {self.config.max_exposure_usd:.2f} USD. Halting strategy.")
            return False

        # --- Daily PnL Check ---
        # This is very simplified. Real PnL tracking needs to account for average entry/exit prices.
        # For this example, we'll assume a mechanism to update daily_pnl_usd.
        current_day = time.gmtime().tm_yday
        if current_day != self.last_pnl_reset_day:
            logger.info(f"New day, resetting daily PnL (was {self.daily_pnl_usd:.2f} USD).")
            self.daily_pnl_usd = 0.0
            self.last_pnl_reset_day = current_day

        if self.daily_pnl_usd < -self.config.max_loss_per_day_usd:
            logger.critical(f"Daily loss limit breached! PnL: {self.daily_pnl_usd:.2f} USD. Halting strategy.")
            return False

        return True

    def run(self):
        """Main loop for the market making strategy."""
        self.running = True
        logger.info("Market making strategy started.")

        while self.running:
            try:
                # 1. Get Market Data
                market_data = self._get_market_data()
                if not market_data:
                    logger.warning("No market data, skipping cycle.")
                    time.sleep(self.config.refresh_interval_sec)
                    continue
                bid, ask = market_data

                # 2. Update Position (based on actual exchange balance)
                self._update_position()

                # 3. Check Risk Limits
                if not self._check_risk_limits():
                    self.stop() # Stop if risk limits are breached
                    break

                # 4. Calculate Target Prices (with inventory adjustment)
                target_buy_price, target_sell_price = self._calculate_target_prices(bid, ask)

                # 5. Manage Orders (cancel/replace)
                self._manage_orders(target_buy_price, target_sell_price)

                # 6. Log State
                logger.info(
                    f"[{self.config.symbol}] Mid: {self.last_mid_price:.2f}, "
                    f"Target Buy: {target_buy_price:.2f}, Target Sell: {target_sell_price:.2f}, "
                    f"Position: {self.current_position_base:.4f} {self.config.base_currency}, "
                    f"USD Balance: {self.exchange.get_balance(self.config.quote_currency):.2f}"
                )

            except KeyboardInterrupt:
                logger.info("KeyboardInterrupt detected. Stopping strategy.")
                self.stop()
            except Exception as e:
                logger.exception(f"An unhandled error occurred: {e}")
                # Decide whether to stop or just log and continue
                # self.stop() # Uncomment to stop on any unhandled error

            time.sleep(self.config.refresh_interval_sec)

    def stop(self):
        """Stops the strategy and cancels all open orders."""
        self.running = False
        logger.info("Stopping market making strategy. Canceling all open orders...")
        open_orders = self.exchange.get_open_orders(self.config.symbol)
        for order in open_orders:
            self.exchange.cancel_order(order.order_id)
        logger.info("All orders canceled. Strategy stopped.")

# --- Main Execution Block ---
if __name__ == "__main__":
    # Initialize configuration
    config = StrategyConfig()

    # Initialize Mock Exchange
    mock_exchange = MockExchange(
        initial_balance_base=config.initial_balance_base,
        initial_balance_quote=config.initial_balance_quote
    )

    # Initialize and run the strategy
    strategy = MarketMakingStrategy(mock_exchange, config)

    # You can start the strategy in a separate thread if you need a responsive UI
    # or other operations in the main thread. For this example, it runs in main.
    strategy.run()
