
import time

from simulated_exchange import SimulatedExchange
from strategy import Strategy


class MarketMakingBot:
    def __init__(self, exchange, strategy, symbol, initial_balance):
        self.exchange = exchange
        self.strategy = strategy
        self.symbol = symbol
        self.running = False
        self.balance = initial_balance

    def start(self):
        self.running = True
        print(f"Starting market making bot for {self.symbol} on {self.exchange.name}")
        print(f"Initial balance: {self.balance}")
        self.run_loop()

    def stop(self):
        self.running = False
        print("Stopping market making bot.")
        self.exchange.cancel_all_orders(self.symbol)

    def run_loop(self):
        while self.running:
            try:
                # 1. Get market data
                order_book = self.exchange.get_order_book(self.symbol)

                # 2. Calculate new orders based on strategy
                new_orders = self.strategy.calculate_orders(order_book, self.balance)

                # 3. Update orders
                self.update_orders(new_orders)

                # 4. Print status
                self.print_status()

                time.sleep(5) # Wait for 5 seconds before the next iteration

            except Exception as e:
                print(f"An error occurred: {e}")
                self.stop()

    def update_orders(self, new_orders):
        # This is a simplified order update logic.
        # A real implementation would be more sophisticated.
        self.exchange.cancel_all_orders(self.symbol)
        for order in new_orders:
            self.exchange.place_order(
                self.symbol, order['side'], order['price'], order['quantity']
            )

    def print_status(self):
        print("\n----- Bot Status -----")
        print(f"Timestamp: {time.ctime()}")
        print(f"Balance: {self.balance}")
        open_orders = self.exchange.get_open_orders(self.symbol)
        print(f"Open Orders: {len(open_orders)}")
        for order in open_orders:
            print(f"  - {order['side']} {order['quantity']} @ {order['price']}")
        print("----------------------\n")


if __name__ == "__main__":
    # In a real bot, you would get these from a config file
    SYMBOL = "BTC/USD"
    INITIAL_QUOTE_BALANCE = 10000
    SPREAD = 0.01 # 1% spread
    ORDER_AMOUNT = 0.1 # Amount of BTC to trade

    # Initialize the exchange and strategy
    exchange = SimulatedExchange()
    strategy = Strategy(spread=SPREAD, order_amount=ORDER_AMOUNT)

    # Create and start the bot
    bot = MarketMakingBot(
        exchange=exchange,
        strategy=strategy,
        symbol=SYMBOL,
        initial_balance={'USD': INITIAL_QUOTE_BALANCE, 'BTC': 0}
    )

    try:
        bot.start()
    except KeyboardInterrupt:
        bot.stop()

