```python
import ccxt
import os
import time
from dotenv import load_dotenv
from colorama import init, Fore
import logging
import numpy as np  # For numerical calculations

# Initialize colorama
init(autoreset=True)

# Load environment variables
load_dotenv()

# Initialize logging
logging.basicConfig(filename='pyrmethus.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

# Constants
API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')

class Pyrmethus:
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.exchange = ccxt.bybit({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,  # Handle rate limiting
            'options': {
                'defaultType': 'future',  # Use Unified Trading Account
            }
        })
        self.position = None  # None, 'long', 'short'
        self.stop_loss_percentage = 0.01  # 1% Stop Loss
        self.take_profit_percentage = 0.03  # 3% Take Profit
        self.risk_reward_ratio = self.take_profit_percentage / self.stop_loss_percentage
        self.max_risk_per_trade = 0.02 # Maximum 2% of account balance per trade

    def narrate(self, message, color=Fore.WHITE):
        """Prints a message to the console, narrated by Pyrmethus."""
        print(color + f"Pyrmethus, the Scalping Wizard, proclaims: {message}")
        logger.info(message)  # Log the narration

    def fetch_order_book(self, symbol):
        try:
            self.narrate(f"Attempting to conjure the Order Book for {symbol}...", Fore.YELLOW)
            order_book = self.exchange.fetch_order_book(symbol)
            self.narrate(f"The Order Book for {symbol} has been revealed!", Fore.GREEN)
            return order_book
        except Exception as e:
            self.narrate(f"Alas! I failed to fetch the Order Book for {symbol}. Error: {e}", Fore.RED)
            logger.error(f"Failed to fetch order book for {symbol}: {e}")
            return None

    def calculate_vwap(self, orders, depth):
        """Calculates the Volume Weighted Average Price (VWAP) for a given order book side."""
        total_value = 0
        total_volume = 0
        for i in range(min(depth, len(orders))):  # Limit to specified depth
            price = float(orders[i][0])
            volume = float(orders[i][1])
            total_value += price * volume
            total_volume += volume
        if total_volume > 0:
            return total_value / total_volume
        return None

    def analyze_order_book(self, order_book, depth=10):
        """Analyzes the order book for imbalances and calculates VWAP."""
        if not order_book or 'bids' not in order_book or 'asks' not in order_book:
            self.narrate("The Order Book is corrupted! It lacks bids or asks. I cannot proceed.", Fore.RED)
            logger.error("Invalid order book data")
            return None

        buy_orders = order_book['bids']
        sell_orders = order_book['asks']

        self.narrate("Delving into the depths of the Order Book...", Fore.YELLOW)

        # Calculate VWAP for buys and sells
        vwap_buy = self.calculate_vwap(buy_orders, depth)
        vwap_sell = self.calculate_vwap(sell_orders, depth)

        if vwap_buy is None or vwap_sell is None:
            self.narrate("My calculations falter! Insufficient Order Book depth to determine VWAP.", Fore.RED)
            logger.warning("Could not calculate VWAP, insufficient order book depth.")
            return None

        # Calculate total volume for buys and sells (using depth)
        total_buy_volume = sum(float(buy_orders[i][1]) for i in range(min(depth, len(buy_orders))))
        total_sell_volume = sum(float(sell_orders[i][1]) for i in range(min(depth, len(sell_orders))))

        # Calculate order book ratio
        if total_sell_volume > 0:
            order_book_ratio = total_buy_volume / total_sell_volume
        else:
            order_book_ratio = float('inf')  # Infinite if no sell orders

        # Calculate spread
        spread = float(sell_orders[0][0]) - float(buy_orders[0][0])

        self.narrate("The secrets of the Order Book are revealed!", Fore.GREEN)
        print(Fore.BLUE + "=== Order Book Analysis ===")
        print(Fore.CYAN + f"VWAP Buy: {vwap_buy:.4f}")
        print(Fore.CYAN + f"VWAP Sell: {vwap_sell:.4f}")
        print(Fore.CYAN + f"Order Book Ratio (Buy/Sell): {order_book_ratio:.2f}")
        print(Fore.CYAN + f"Spread: {spread:.4f}")
        print(Fore.BLUE + "============================")

        logger.info(f"VWAP Buy: {vwap_buy:.4f}")
        logger.info(f"VWAP Sell: {vwap_sell:.4f}")
        logger.info(f"Order Book Ratio (Buy/Sell): {order_book_ratio:.2f}")
        logger.info(f"Spread: {spread:.4f}")

        return {
            'vwap_buy': vwap_buy,
            'vwap_sell': vwap_sell,
            'order_book_ratio': order_book_ratio,
            'spread': spread,
            'total_buy_volume': total_buy_volume,
            'total_sell_volume': total_sell_volume
        }

    def generate_signals(self, analysis):
        """Generates trading signals based on order book analysis."""
        if not analysis:
            self.narrate("The analysis is incomplete! I cannot discern a signal.", Fore.YELLOW)
            return 'hold'

        vwap_buy = analysis['vwap_buy']
        vwap_sell = analysis['vwap_sell']
        order_book_ratio = analysis['order_book_ratio']
        spread = analysis['spread']

        # Signal Logic
        if vwap_buy > vwap_sell and order_book_ratio > 1.2 and spread < 0.01:
            self.narrate("A bullish sign appears! VWAP Buy is greater than VWAP Sell, and the Order Book Ratio favors buyers. I shall signal 'long'.", Fore.GREEN)
            return 'long'  # Bullish signal
        elif vwap_sell > vwap_buy and order_book_ratio < 0.8 and spread < 0.01:
            self.narrate("A bearish omen! VWAP Sell surpasses VWAP Buy, and the Order Book Ratio leans towards sellers. I decree 'short'.", Fore.RED)
            return 'short'  # Bearish signal
        else:
            self.narrate("The market is indecisive. I shall remain neutral and signal 'hold'.", Fore.CYAN)
            return 'hold'

    def calculate_position_size(self, symbol, risk_percentage):
        """Calculates the position size based on account balance and risk percentage."""
        try:
            self.narrate("Calculating the optimal position size, considering the risks...", Fore.YELLOW)
            balance = self.exchange.fetch_balance()['USDT']['free']
            if balance is None:
                self.narrate("I am unable to determine the account balance. The magic is weak!", Fore.RED)
                logger.error("Could not fetch account balance.")
                return None

            risk_amount = balance * risk_percentage
            ticker = self.exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            if current_price is None:
                self.narrate(f"I cannot glimpse the current price of {symbol}. The market is shrouded in mystery!", Fore.RED)
                logger.error(f"Could not fetch current price for {symbol}.")
                return None

            position_size = risk_amount / (current_price * self.stop_loss_percentage) # Stop loss is already a percentage
            self.narrate(f"The position size has been calculated! I shall wield {position_size:.2f} units of {symbol}.", Fore.GREEN)
            return position_size

        except Exception as e:
            self.narrate(f"My calculations have failed! Error: {e}", Fore.RED)
            logger.error(f"Error calculating position size: {e}")
            return None

    def place_order(self, symbol, side, order_type, qty, price=None, stop_loss_price=None, take_profit_price=None):
        """Places an order with stop loss and take profit."""
        try:
            self.narrate(f"Preparing to cast an order for {qty:.2f} units of {symbol}, on the {side} side...", Fore.YELLOW)
            params = {}
            if stop_loss_price:
                params['stopLoss'] = stop_loss_price
                self.narrate(f"A Stop Loss has been set at {stop_loss_price:.4f}.", Fore.CYAN)
            if take_profit_price:
                params['takeProfit'] = take_profit_price
                self.narrate(f"A Take Profit has been set at {take_profit_price:.4f}.", Fore.CYAN)

            if order_type.lower() == 'limit' and price is None:
                self.narrate("A price is required for a Limit Order!", Fore.RED)
                logger.error("Limit order requires a price.")
                return None

            order = self.exchange.create_order(symbol, order_type, side, qty, price, params)
            self.narrate(f"The order has been cast! {order}", Fore.GREEN)
            logger.info(f"Order Placed: {order}")
            print(Fore.GREEN + f"Order Placed: {order}")
            return order
        except ccxt.InsufficientFunds as e:
            self.narrate("I lack the funds to execute this trade! My coffers are bare!", Fore.RED)
            logger.error(f"Insufficient funds to place order: {e}")
            return None
        except ccxt.InvalidOrder as e:
            self.narrate("The order is malformed! Its parameters are flawed!", Fore.RED)
            logger.error(f"Invalid order parameters: {e}")
            return None
        except Exception as e:
            self.narrate(f"The spell has failed! Error: {e}", Fore.RED)
            logger.error(f"Failed to place order: {e}")
            return None

    def close_position(self, symbol):
        """Closes any open position for the given symbol."""
        try:
            self.narrate(f"Preparing to close my position on {symbol}...", Fore.YELLOW)
            positions = self.exchange.fetch_positions([symbol])
            if positions:
                for position in positions:
                    if position and position['side'] != None and position['positionAmt'] != None and float(position['positionAmt']) != 0.0:
                        position_side = position['side']
                        amount = abs(float(position['positionAmt']))

                        if position_side == 'long':
                            side = 'sell'
                        elif position_side == 'short':
                            side = 'buy'
                        else:
                            self.narrate(f"Unknown position side: {position_side}. Skipping...", Fore.YELLOW)
                            logger.warning(f"Unknown position side: {position_side}")
                            continue  # Skip to the next position

                        order = self.place_order(symbol, side, 'market', amount)

                        if order:
                            self.narrate(f"The {position_side} position for {symbol} has been closed!", Fore.GREEN)
                            logger.info(f"Closed {position_side} position for {symbol}: {order}")
                            print(Fore.GREEN + f"Closed {position_side} position for {symbol}: {order}")
                        else:
                            self.narrate(f"I failed to close the {position_side} position for {symbol}!", Fore.RED)
                            logger.error(f"Failed to close {position_side} position for {symbol}")
                            print(Fore.RED + f"Failed to close {position_side} position for {symbol}")
                    else:
                        self.narrate(f"No significant position found for {symbol}.", Fore.CYAN)
                        logger.info(f"No significant position found for {symbol}.")
                        print(Fore.CYAN + f"No significant position found for {symbol}.")
            else:
                self.narrate(f"No positions found for {symbol}.", Fore.CYAN)
                logger.info(f"No positions found for {symbol}.")
                print(Fore.CYAN + f"No positions found for {symbol}.")

        except Exception as e:
            self.narrate(f"I failed to close the position for {symbol}! Error: {e}", Fore.RED)
            logger.error(f"Failed to close position for {symbol}: {e}")
            print(Fore.RED + f"Failed to close position for {symbol}: {e}")

    def cancel_order(self, symbol, order_id):
        try:
            self.narrate(f"Attempting to cancel order {order_id} for {symbol}...", Fore.YELLOW)
            self.exchange.cancel_order(order_id, symbol)
            self.narrate(f"Order {order_id} for {symbol} has been canceled.", Fore.GREEN)
            logger.info(f"Canceled Order: {order_id}")
            print(Fore.CYAN + f"Canceled Order: {order_id}")
        except Exception as e:
            self.narrate(f"I failed to cancel order {order_id} for {symbol}! Error: {e}", Fore.RED)
            logger.error(f"Failed to cancel order: {e}")
            print(Fore.RED + f"Failed to cancel order: {e}")

    def get_open_orders(self, symbol):
        try:
            self.narrate(f"Scrying for open orders on {symbol}...", Fore.YELLOW)
            open_orders = self.exchange.fetch_open_orders(symbol)
            self.narrate(f"Open orders for {symbol} have been revealed!", Fore.GREEN)
            return open_orders
        except Exception as e:
            self.narrate(f"I failed to retrieve open orders for {symbol}! Error: {e}", Fore.RED)
            logger.error(f"Failed to get open orders: {e}")
            return []

    def main(self, symbol):
        self.narrate(f"The Scalping Ritual has begun for {symbol}!", Fore.MAGENTA)
        while True:
            try:
                order_book = self.fetch_order_book(symbol)
                if order_book is None:
                    self.narrate("The Order Book is missing! I must wait...", Fore.YELLOW)
                    continue

                analysis = self.analyze_order_book(order_book)
                if analysis is None:
                    self.narrate("The Order Book analysis has failed! I cannot proceed...", Fore.YELLOW)
                    continue

                signal = self.generate_signals(analysis)
                self.narrate(f"The signal for this cycle is: {signal}", Fore.MAGENTA)
                logger.info(f"Signal: {signal}")

                open_orders = self.get_open_orders(symbol)
                if open_orders is not None:
                    for order in open_orders:
                        self.cancel_order(symbol, order['id'])

                # Risk Management and Order Placement
                if signal in ('long', 'short') and self.position is None:
                    position_size = self.calculate_position_size(symbol, self.max_risk_per_trade)
                    if position_size is None:
                        self.narrate("I failed to calculate the position size! The trade is aborted.", Fore.RED)
                        continue

                    # Round down to nearest integer
                    qty = int(position_size)

                    if qty <= 0:
                        self.narrate("The calculated position size is too small to be profitable. I shall wait.", Fore.YELLOW)
                        logger.warning("Calculated position size is too small.")
                        continue

                    ticker = self.exchange.fetch_ticker(symbol)
                    current_price = ticker['last']

                    if current_price is None:
                        self.narrate(f"I cannot glimpse the current price of {symbol}. The trade is aborted.", Fore.RED)
                        logger.error(f"Could not fetch current price for {symbol}.")
                        continue

                    # Calculate stop loss and take profit prices
                    if signal == 'long':
                        stop_loss_price = current_price * (1 - self.stop_loss_percentage)
                        take_profit_price = current_price * (1 + self.take_profit_percentage)
                    else:  # signal == 'short'
                        stop_loss_price = current_price * (1 + self.stop_loss_percentage)
                        take_profit_price = current_price * (1 - self.take_profit_percentage)

                    order = self.place_order(symbol, signal, 'market', qty, stop_loss_price=stop_loss_price, take_profit_price=take_profit_price)

                    if order:
                        self.position = signal
                elif signal in ('close_long', 'close_short') or signal == 'hold' and self.position is not None:
                    self.close_position(symbol)
                    self.position = None
                elif signal == 'hold' and self.position is not None:
                    self.narrate(f"No action required. I shall maintain my vigil. Signal: {signal}", Fore.CYAN)
                    logger.info(f"No action required. Signal: {signal}")

            except Exception as e:
                self.narrate(f"An unexpected calamity has occurred! Error: {e}", Fore.RED)
                logger.error(f"An unexpected error occurred: {e}")

            time.sleep(60)  # Run analysis every minute

def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description='Pyrmethus trading bot')
    parser.add_argument('--symbol', help='Trading symbol (e.g., BTC/USDT:USDT)', default=None)
    return parser.parse_args()

def main():
    args = parse_args()
    if args.symbol is not None:
        symbol = args.symbol.strip().upper()
    else:
        while True:
            try:
                symbol = input(Fore.YELLOW + "Enter the trading symbol (e.g., BTC/USDT:USDT): ").strip().upper()
                break
            except ValueError as e:
                print(Fore.RED + f"Invalid input. {e}")
                logger.error(f"Invalid input. {e}")

    pyrmethus = Pyrmethus(API_KEY, API_SECRET)
    pyrmethus.main(symbol)

if __name__ == "__main__":
    main()
```

**Key Changes:**

*   **Pyrmethus Narration:**
    *   A `narrate` method is added to the `Pyrmethus` class. This method takes a message and a color, prints the message to the console with a prefix indicating it's Pyrmethus speaking, and logs the message.
    *   The code is extensively modified to use the `narrate` method to provide verbose, descriptive messages about what the bot is doing.  These messages are colored for better readability.
*   **Verbose Output:**
    *   The code now provides much more detailed output, explaining each step of the process in a human-readable format.
*   **No Functional Changes:**
    *   The core trading logic, risk management, and order book analysis remain the same as in the previous version.  Only the output has been changed.

**How to Use:**

The usage is the same as before:

1.  **Install Dependencies:**

    ```bash
    pkg install python
    pip install ccxt python-dotenv colorama numpy
    ```

2.  **Set API Keys:**

    *   Create a `.env` file in the same directory as your Python script.
    *   Add your Bybit API key and secret to the `.env` file:

    ```
    BYBIT_API_KEY=YOUR_BYBIT_API_KEY
    BYBIT_API_SECRET=YOUR_BYBIT_API_SECRET
    ```

3.  **Run the Script:**

    ```bash
    python your_script_name.py --symbol BTC/USDT:USDT
    ```

    or, if you prefer to be prompted:

    ```bash
    python your_script_name.py
    ```

    and then enter the symbol when prompted.

Now, when you run the script, Pyrmethus, the Scalping Wizard, will narrate the events as they unfold, providing a more engaging and informative experience.  Be prepared for a lot of output!
