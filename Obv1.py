import ccxt
import os
import time
from dotenv import load_dotenv
from colorama import init, Fore
import logging
import numpy as np  # For numerical calculations
from datetime import datetime
import yaml  # For configuration file

# Initialize colorama
init(autoreset=True)

# Load environment variables
load_dotenv()

# Initialize logging
logging.basicConfig(filename='pyrmethus.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

# Constants from environment variables
API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')

class Pyrmethus:
    def __init__(self, api_key, api_secret, config_file='config.yaml'):
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
        self.config = self.load_config(config_file) # Load configuration from YAML file
        self.stop_loss_percentage = self.config['stop_loss_percentage']
        self.take_profit_percentage = self.config['take_profit_percentage']
        self.risk_reward_ratio = self.take_profit_percentage / self.stop_loss_percentage
        self.max_risk_per_trade = self.config['max_risk_per_trade']
        self.order_book_depth = self.config['order_book_depth']
        self.vwap_depth = self.config['vwap_depth']
        self.vwap_threshold_scaling_factor = self.config['vwap_threshold_scaling_factor']
        self.ratio_threshold = self.config['ratio_threshold']
        self.spread_threshold_for_market_order = self.config['spread_threshold_for_market_order']
        self.backtesting_timeframe = self.config['backtesting_timeframe']
        self.analysis_interval = self.config['analysis_interval']


    def load_config(self, config_file):
        """Loads configuration from YAML file."""
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
            self.narrate(f"Configuration loaded from {config_file}.", Fore.GREEN)
            return config
        except FileNotFoundError:
            self.narrate(f"Configuration file {config_file} not found. Using default settings.", Fore.YELLOW)
            logger.warning(f"Configuration file not found: {config_file}. Using default settings.")
            # Return default config or raise error - for now, let's raise error if config is crucial
            raise FileNotFoundError(f"Configuration file {config_file} not found.")
        except yaml.YAMLError as e:
            self.narrate(f"Error parsing configuration file {config_file}. Please check YAML syntax. Error: {e}", Fore.RED)
            logger.error(f"YAML parsing error in {config_file}: {e}")
            raise yaml.YAMLError(f"Error parsing configuration file {config_file}: {e}")

    def narrate(self, message, color=Fore.WHITE):
        """Prints a message to the console, narrated by Pyrmethus."""
        print(color + f"Pyrmethus, the Scalping Wizard, proclaims: {message}")
        logger.info(message)  # Log the narration

    def fetch_order_book(self, symbol):
        try:
            self.narrate(f"Attempting to conjure the Order Book for {symbol}...", Fore.YELLOW)
            order_book = self.exchange.fetch_order_book(symbol, limit=self.order_book_depth) # Limit order book depth
            self.narrate(f"The Order Book for {symbol} has been revealed!", Fore.GREEN)
            return order_book
        except ccxt.NetworkError as e:
            self.narrate(f"Network error encountered while fetching order book for {symbol}: {e}", Fore.RED)
            logger.error(f"Network error fetching order book: {e}")
            return None
        except ccxt.ExchangeError as e:
            self.narrate(f"Exchange error encountered while fetching order book for {symbol}: {e}", Fore.RED)
            logger.error(f"Exchange error fetching order book: {e}")
            return None
        except Exception as e:
            self.narrate(f"Alas! I failed to fetch the Order Book for {symbol}. Error: {e}", Fore.RED)
            logger.error(f"Failed to fetch order book for {symbol}: {e}")
            return None

    def calculate_vwap(self, orders, depth):
        """Calculates the Volume Weighted Average Price (VWAP) for a given order book side."""
        total_value = sum(float(order[0]) * float(order[1]) for order in orders[:depth])
        total_volume = sum(float(order[1]) for order in orders[:depth])
        return total_value / total_volume if total_volume > 0 else None

    def analyze_order_book(self, order_book):
        """Analyzes the order book for imbalances and calculates VWAP."""
        if not order_book or 'bids' not in order_book or 'asks' not in order_book:
            self.narrate("The Order Book is corrupted! It lacks bids or asks. I cannot proceed.", Fore.RED)
            logger.error("Invalid order book data")
            return None

        buy_orders = order_book['bids']
        sell_orders = order_book['asks']

        self.narrate("Delving into the depths of the Order Book...", Fore.YELLOW)

        # Calculate VWAP for buys and sells
        vwap_buy = self.calculate_vwap(buy_orders, self.vwap_depth)
        vwap_sell = self.calculate_vwap(sell_orders, self.vwap_depth)

        if vwap_buy is None or vwap_sell is None:
            self.narrate("My calculations falter! Insufficient Order Book depth to determine VWAP.", Fore.RED)
            logger.warning("Could not calculate VWAP, insufficient order book depth.")
            return None

        # Calculate total volume for buys and sells (using depth)
        total_buy_volume = sum(float(order[1]) for order in buy_orders[:self.order_book_depth])
        total_sell_volume = sum(float(order[1]) for order in sell_orders[:self.order_book_depth])

        # Calculate order book ratio
        order_book_ratio = total_buy_volume / total_sell_volume if total_sell_volume > 0 else float('inf')

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

        # Dynamic Signal Thresholds from config
        vwap_threshold = 0.0005 * self.vwap_threshold_scaling_factor # Example of scaling - can be more dynamic later
        ratio_threshold = self.ratio_threshold
        spread_threshold = 0.01 # Still using fixed spread threshold

        # Signal Logic
        if vwap_buy > vwap_sell * (1 + vwap_threshold) and order_book_ratio > ratio_threshold and spread < spread_threshold:
            self.narrate("A bullish sign appears! VWAP Buy is significantly greater than VWAP Sell, and the Order Book Ratio favors buyers. I shall signal 'long'.", Fore.GREEN)
            return 'long'  # Bullish signal
        elif vwap_sell > vwap_buy * (1 + vwap_threshold) and order_book_ratio < (1 / ratio_threshold) and spread < spread_threshold:
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

            # Account for taker fees - IMPORTANT: Using Bybit taker fee
            taker_fee = 0.00075  # Bybit taker fee is 0.075%
            position_size = risk_amount / (current_price * (self.stop_loss_percentage + taker_fee))  # Stop loss is already a percentage
            self.narrate(f"The position size has been calculated! I shall wield {position_size:.2f} units of {symbol}.", Fore.GREEN)
            return position_size

        except ccxt.NetworkError as e:
            self.narrate(f"Network error encountered while calculating position size for {symbol}: {e}", Fore.RED)
            logger.error(f"Network error calculating position size: {e}")
            return None
        except ccxt.ExchangeError as e:
            self.narrate(f"Exchange error encountered while calculating position size for {symbol}: {e}", Fore.RED)
            logger.error(f"Exchange error calculating position size: {e}")
            return None
        except Exception as e:
            self.narrate(f"My calculations have failed! Error: {e}", Fore.RED)
            logger.error(f"Error calculating position size: {e}")
            return None

    def place_order(self, symbol, side, order_type, qty, price=None, stop_loss_price=None, take_profit_price=None):
        """Places an order, dynamically choosing between market and limit based on spread."""
        try:
            self.narrate(f"Preparing to cast an order for {qty:.2f} units of {symbol}, on the {side} side...", Fore.YELLOW)
            params = {}
            if stop_loss_price:
                params['stopLoss'] = stop_loss_price
                self.narrate(f"A Stop Loss has been set at {stop_loss_price:.4f}.", Fore.CYAN)
            if take_profit_price:
                params['takeProfit'] = take_profit_price
                self.narrate(f"A Take Profit has been set at {take_profit_price:.4f}.", Fore.CYAN)

            final_order_type = order_type  # Start with requested order_type

            if order_type.lower() == 'market': # If Market is requested, proceed as market
                final_order_type = 'market'
            elif order_type.lower() == 'limit': # If Limit is requested, proceed as limit (price must be provided)
                if price is None:
                    self.narrate("A price is required for a Limit Order!", Fore.RED)
                    logger.error("Limit order requires a price.")
                    return None
                final_order_type = 'limit'
            elif order_type.lower() == 'dynamic': # Dynamic order type logic
                order_book = self.fetch_order_book(symbol) # Need fresh order book for spread check
                if not order_book or not order_book['bids'] or not order_book['asks']:
                    self.narrate("Order book unavailable for dynamic order type decision. Defaulting to Market Order.", Fore.YELLOW)
                    final_order_type = 'market' # Default to market if order book issue
                else:
                    spread = order_book['asks'][0][0] - order_book['bids'][0][0]
                    if spread <= self.spread_threshold_for_market_order:
                        final_order_type = 'market'
                        self.narrate(f"Spread is low ({spread:.4f} <= {self.spread_threshold_for_market_order}), using Market Order.", Fore.CYAN)
                    else:
                        final_order_type = 'limit'
                        if side == 'buy':
                            price = order_book['asks'][0][0] # Limit buy at ask price
                        else: # side == 'sell'
                            price = order_book['bids'][0][0] # Limit sell at bid price
                        params['price'] = price  # Add price for limit order
                        self.narrate(f"Spread is high ({spread:.4f} > {self.spread_threshold_for_market_order}), using Limit Order at price {price:.4f}.", Fore.CYAN)


            order = self.exchange.create_order(symbol, final_order_type, side, qty, price, params) # Use final_order_type and price (if applicable)
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
        except ccxt.NetworkError as e:
            self.narrate(f"Network error encountered while placing order for {symbol}: {e}", Fore.RED)
            logger.error(f"Network error placing order: {e}")
            return None
        except ccxt.ExchangeError as e:
            self.narrate(f"Exchange error encountered while placing order for {symbol}: {e}", Fore.RED)
            logger.error(f"Exchange error placing order: {e}")
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
                    if position and position['side'] is not None and position['positionAmt'] is not None and float(position['positionAmt']) != 0.0:
                        position_side = position['side']
                        amount = abs(float(position['positionAmt']))

                        side = 'sell' if position_side == 'long' else 'buy'

                        order = self.place_order(symbol, side, 'market', amount) # Close position with market order

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

        except ccxt.NetworkError as e:
            self.narrate(f"Network error encountered while closing position for {symbol}: {e}", Fore.RED)
            logger.error(f"Network error closing position: {e}")
            return None
        except ccxt.ExchangeError as e:
            self.narrate(f"Exchange error encountered while closing position for {symbol}: {e}", Fore.RED)
            logger.error(f"Exchange error closing position: {e}")
            return None
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
        except ccxt.NetworkError as e:
            self.narrate(f"Network error encountered while canceling order for {symbol}: {e}", Fore.RED)
            logger.error(f"Network error canceling order: {e}")
            return None
        except ccxt.ExchangeError as e:
            self.narrate(f"Exchange error encountered while canceling order for {symbol}: {e}", Fore.RED)
            logger.error(f"Exchange error canceling order: {e}")
            return None
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
        except ccxt.NetworkError as e:
            self.narrate(f"Network error encountered while getting open orders for {symbol}: {e}", Fore.RED)
            logger.error(f"Network error getting open orders: {e}")
            return []
        except ccxt.ExchangeError as e:
            self.narrate(f"Exchange error encountered while getting open orders for {symbol}: {e}", Fore.RED)
            logger.error(f"Exchange error getting open orders: {e}")
            return []
        except Exception as e:
            self.narrate(f"I failed to retrieve open orders for {symbol}! Error: {e}", Fore.RED)
            logger
          import ccxt
import os
import time
from dotenv import load_dotenv
from colorama import init, Fore
import logging
import numpy as np  # For numerical calculations
from datetime import datetime
import yaml  # For configuration file

# Initialize colorama
init(autoreset=True)

# Load environment variables
load_dotenv()

# Initialize logging
logging.basicConfig(filename='pyrmethus.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

# Constants from environment variables
API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')

class Pyrmethus:
    def __init__(self, api_key, api_secret, config_file='config.yaml'):
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
        self.config = self.load_config(config_file) # Load configuration from YAML file
        self.stop_loss_percentage = self.config['stop_loss_percentage']
        self.take_profit_percentage = self.config['take_profit_percentage']
        self.risk_reward_ratio = self.take_profit_percentage / self.stop_loss_percentage
        self.max_risk_per_trade = self.config['max_risk_per_trade']
        self.order_book_depth = self.config['order_book_depth']
        self.vwap_depth = self.config['vwap_depth']
        self.vwap_threshold_scaling_factor = self.config['vwap_threshold_scaling_factor']
        self.ratio_threshold = self.config['ratio_threshold']
        self.spread_threshold_for_market_order = self.config['spread_threshold_for_market_order']
        self.backtesting_timeframe = self.config['backtesting_timeframe']
        self.analysis_interval = self.config['analysis_interval']


    def load_config(self, config_file):
        """Loads configuration from YAML file."""
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
            self.narrate(f"Configuration loaded from {config_file}.", Fore.GREEN)
            return config
        except FileNotFoundError:
            self.narrate(f"Configuration file {config_file} not found. Using default settings.", Fore.YELLOW)
            logger.warning(f"Configuration file not found: {config_file}. Using default settings.")
            # Return default config or raise error - for now, let's raise error if config is crucial
            raise FileNotFoundError(f"Configuration file {config_file} not found.")
        except yaml.YAMLError as e:
            self.narrate(f"Error parsing configuration file {config_file}. Please check YAML syntax. Error: {e}", Fore.RED)
            logger.error(f"YAML parsing error in {config_file}: {e}")
            raise yaml.YAMLError(f"Error parsing configuration file {config_file}: {e}")

    def narrate(self, message, color=Fore.WHITE):
        """Prints a message to the console, narrated by Pyrmethus."""
        print(color + f"Pyrmethus, the Scalping Wizard, proclaims: {message}")
        logger.info(message)  # Log the narration

    def fetch_order_book(self, symbol):
        try:
            self.narrate(f"Attempting to conjure the Order Book for {symbol}...", Fore.YELLOW)
            order_book = self.exchange.fetch_order_book(symbol, limit=self.order_book_depth) # Limit order book depth
            self.narrate(f"The Order Book for {symbol} has been revealed!", Fore.GREEN)
            return order_book
        except ccxt.NetworkError as e:
            self.narrate(f"Network error encountered while fetching order book for {symbol}: {e}", Fore.RED)
            logger.error(f"Network error fetching order book: {e}")
            return None
        except ccxt.ExchangeError as e:
            self.narrate(f"Exchange error encountered while fetching order book for {symbol}: {e}", Fore.RED)
            logger.error(f"Exchange error fetching order book: {e}")
            return None
        except Exception as e:
            self.narrate(f"Alas! I failed to fetch the Order Book for {symbol}. Error: {e}", Fore.RED)
            logger.error(f"Failed to fetch order book for {symbol}: {e}")
            return None

    def calculate_vwap(self, orders, depth):
        """Calculates the Volume Weighted Average Price (VWAP) for a given order book side."""
        total_value = sum(float(order[0]) * float(order[1]) for order in orders[:depth])
        total_volume = sum(float(order[1]) for order in orders[:depth])
        return total_value / total_volume if total_volume > 0 else None

    def analyze_order_book(self, order_book):
        """Analyzes the order book for imbalances and calculates VWAP."""
        if not order_book or 'bids' not in order_book or 'asks' not in order_book:
            self.narrate("The Order Book is corrupted! It lacks bids or asks. I cannot proceed.", Fore.RED)
            logger.error("Invalid order book data")
            return None

        buy_orders = order_book['bids']
        sell_orders = order_book['asks']

        self.narrate("Delving into the depths of the Order Book...", Fore.YELLOW)

        # Calculate VWAP for buys and sells
        vwap_buy = self.calculate_vwap(buy_orders, self.vwap_depth)
        vwap_sell = self.calculate_vwap(sell_orders, self.vwap_depth)

        if vwap_buy is None or vwap_sell is None:
            self.narrate("My calculations falter! Insufficient Order Book depth to determine VWAP.", Fore.RED)
            logger.warning("Could not calculate VWAP, insufficient order book depth.")
            return None

        # Calculate total volume for buys and sells (using depth)
        total_buy_volume = sum(float(order[1]) for order in buy_orders[:self.order_book_depth])
        total_sell_volume = sum(float(order[1]) for order in sell_orders[:self.order_book_depth])

        # Calculate order book ratio
        order_book_ratio = total_buy_volume / total_sell_volume if total_sell_volume > 0 else float('inf')

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

        # Dynamic Signal Thresholds from config
        vwap_threshold = 0.0005 * self.vwap_threshold_scaling_factor # Example of scaling - can be more dynamic later
        ratio_threshold = self.ratio_threshold
        spread_threshold = 0.01 # Still using fixed spread threshold

        # Signal Logic
        if vwap_buy > vwap_sell * (1 + vwap_threshold) and order_book_ratio > ratio_threshold and spread < spread_threshold:
            self.narrate("A bullish sign appears! VWAP Buy is significantly greater than VWAP Sell, and the Order Book Ratio favors buyers. I shall signal 'long'.", Fore.GREEN)
            return 'long'  # Bullish signal
        elif vwap_sell > vwap_buy * (1 + vwap_threshold) and order_book_ratio < (1 / ratio_threshold) and spread < spread_threshold:
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

            # Account for taker fees - IMPORTANT: Using Bybit taker fee
            taker_fee = 0.00075  # Bybit taker fee is 0.075%
            position_size = risk_amount / (current_price * (self.stop_loss_percentage + taker_fee))  # Stop loss is already a percentage
            self.narrate(f"The position size has been calculated! I shall wield {position_size:.2f} units of {symbol}.", Fore.GREEN)
            return position_size

        except ccxt.NetworkError as e:
            self.narrate(f"Network error encountered while calculating position size for {symbol}: {e}", Fore.RED)
            logger.error(f"Network error calculating position size: {e}")
            return None
        except ccxt.ExchangeError as e:
            self.narrate(f"Exchange error encountered while calculating position size for {symbol}: {e}", Fore.RED)
            logger.error(f"Exchange error calculating position size: {e}")
            return None
        except Exception as e:
            self.narrate(f"My calculations have failed! Error: {e}", Fore.RED)
            logger.error(f"Error calculating position size: {e}")
            return None

    def place_order(self, symbol, side, order_type, qty, price=None, stop_loss_price=None, take_profit_price=None):
        """Places an order, dynamically choosing between market and limit based on spread."""
        try:
            self.narrate(f"Preparing to cast an order for {qty:.2f} units of {symbol}, on the {side} side...", Fore.YELLOW)
            params = {}
            if stop_loss_price:
                params['stopLoss'] = stop_loss_price
                self.narrate(f"A Stop Loss has been set at {stop_loss_price:.4f}.", Fore.CYAN)
            if take_profit_price:
                params['takeProfit'] = take_profit_price
                self.narrate(f"A Take Profit has been set at {take_profit_price:.4f}.", Fore.CYAN)

            final_order_type = order_type  # Start with requested order_type

            if order_type.lower() == 'market': # If Market is requested, proceed as market
                final_order_type = 'market'
            elif order_type.lower() == 'limit': # If Limit is requested, proceed as limit (price must be provided)
                if price is None:
                    self.narrate("A price is required for a Limit Order!", Fore.RED)
                    logger.error("Limit order requires a price.")
                    return None
                final_order_type = 'limit'
            elif order_type.lower() == 'dynamic': # Dynamic order type logic
                order_book = self.fetch_order_book(symbol) # Need fresh order book for spread check
                if not order_book or not order_book['bids'] or not order_book['asks']:
                    self.narrate("Order book unavailable for dynamic order type decision. Defaulting to Market Order.", Fore.YELLOW)
                    final_order_type = 'market' # Default to market if order book issue
                else:
                    spread = order_book['asks'][0][0] - order_book['bids'][0][0]
                    if spread <= self.spread_threshold_for_market_order:
                        final_order_type = 'market'
                        self.narrate(f"Spread is low ({spread:.4f} <= {self.spread_threshold_for_market_order}), using Market Order.", Fore.CYAN)
                    else:
                        final_order_type = 'limit'
                        if side == 'buy':
                            price = order_book['asks'][0][0] # Limit buy at ask price
                        else: # side == 'sell'
                            price = order_book['bids'][0][0] # Limit sell at bid price
                        params['price'] = price  # Add price for limit order
                        self.narrate(f"Spread is high ({spread:.4f} > {self.spread_threshold_for_market_order}), using Limit Order at price {price:.4f}.", Fore.CYAN)


            order = self.exchange.create_order(symbol, final_order_type, side, qty, price, params) # Use final_order_type and price (if applicable)
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
        except ccxt.NetworkError as e:
            self.narrate(f"Network error encountered while placing order for {symbol}: {e}", Fore.RED)
            logger.error(f"Network error placing order: {e}")
            return None
        except ccxt.ExchangeError as e:
            self.narrate(f"Exchange error encountered while placing order for {symbol}: {e}", Fore.RED)
            logger.error(f"Exchange error placing order: {e}")
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
                    if position and position['side'] is not None and position['positionAmt'] is not None and float(position['positionAmt']) != 0.0:
                        position_side = position['side']
                        amount = abs(float(position['positionAmt']))

                        side = 'sell' if position_side == 'long' else 'buy'

                        order = self.place_order(symbol, side, 'market', amount) # Close position with market order

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

        except ccxt.NetworkError as e:
            self.narrate(f"Network error encountered while closing position for {symbol}: {e}", Fore.RED)
            logger.error(f"Network error closing position: {e}")
            return None
        except ccxt.ExchangeError as e:
            self.narrate(f"Exchange error encountered while closing position for {symbol}: {e}", Fore.RED)
            logger.error(f"Exchange error closing position: {e}")
            return None
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
        except ccxt.NetworkError as e:
            self.narrate(f"Network error encountered while canceling order for {symbol}: {e}", Fore.RED)
            logger.error(f"Network error canceling order: {e}")
            return None
        except ccxt.ExchangeError as e:
            self.narrate(f"Exchange error encountered while canceling order for {symbol}: {e}", Fore.RED)
            logger.error(f"Exchange error canceling order: {e}")
            return None
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
        except ccxt.NetworkError as e:
            self.narrate(f"Network error encountered while getting open orders for {symbol}: {e}", Fore.RED)
            logger.error(f"Network error getting open orders: {e}")
            return []
        except ccxt.ExchangeError as e:
            self.narrate(f"Exchange error encountered while getting open orders for {symbol}: {e}", Fore.RED)
            logger.error(f"Exchange error getting open orders: {e}")
            return []
        except Exception as e:
            self.narrate(f"I failed to retrieve open orders for {symbol}! Error: {e}", Fore.RED)
            logger.error(f"Failed to get open orders: {e}")
            return []

    def backtest(self, symbol, start_date, end_date):
        """Backtests the strategy using historical data and calculates performance metrics."""
        self.narrate(f"Backtesting from {start_date} to {end_date} for {symbol}.", Fore.MAGENTA)
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, self.backtesting_timeframe, since=int(datetime.strptime(start_date, '%Y-%m-%d').timestamp() * 1000), until=int(datetime.strptime(end_date, '%Y-%m-%d').timestamp() * 1000), limit=None) # Fetch all available data
            if not ohlcv:
                self.narrate(f"No OHLCV data found for {symbol} in the specified date range.", Fore.RED)
                return

            balance = 1000  # Initial backtesting balance
            trades = []
            in_position = False
            position_side = None
            entry_price = None
            qty = None

            for candle in ohlcv:
                timestamp, open_price, high_price, low_price, close_price, volume = candle
                datetime_candle = datetime.fromtimestamp(timestamp / 1000) # Convert timestamp to datetime

                # Simplified order book simulation - using OHLC prices for bid/ask approximation
                order_book = {
                    'bids': [[low_price, volume/2]], # Approximate bids and asks using candle data
                    'asks': [[high_price, volume/2]]
                }

                analysis = self.analyze_order_book(order_book)
                if analysis:
                    signal = self.generate_signals(analysis)

                    if not in_position:
                        if signal == 'long' or signal == 'short':
                            position_size = self.calculate_position_size(symbol, self.max_risk_per_trade) # Calculate position size for each trade
                            if position_size is None or position_size <= 0:
                                continue # Skip if position size calculation fails or is too small
                            qty = int(position_size) # Integer quantity for backtesting

                            if signal == 'long':
                                order_type = 'dynamic' # Use dynamic order type for backtesting realism
                                entry_price = order_book['asks'][0][0] # Simulate market buy at ask
                                position_side = 'long'
                            elif signal == 'short':
                                order_type = 'dynamic'
                                entry_price = order_book['bids'][0][0] # Simulate market sell at bid
                                position_side = 'short'

                            if entry_price:
                                in_position = True
                                # No actual order placement in backtest, just track trade info
                                trades.append({
                                    'entry_time': datetime_candle,
                                    'entry_price': entry_price,
                                    'side': position_side,
                                    'qty': qty,
                                    'stop_loss': entry_price * (1 - self.stop_loss_percentage) if position_side == 'long' else entry_price * (1 + self.stop_loss_percentage),
                                    'take_profit': entry_price * (1 + self.take_profit_percentage) if position_side == 'long' else entry_price * (1 - self.take_profit_percentage),
                                    'exit_time': None,
                                    'exit_price': None,
                                    'pnl': 0
                                })
                                self.narrate(f"Backtest - {datetime_candle} - Signal: {signal}, Entered {position_side} position at {entry_price:.4f}, Qty: {qty}", Fore.MAGENTA)

                    elif in_position and trades: # Check if trades is not empty to avoid index error
                        current_trade = trades[-1] # Get the last trade
                        exit_signal = 'hold' # Default exit signal

                        if position_side == 'long':
                            if low_price <= current_trade['stop_loss']:
                                exit_signal = 'stop_loss'
                                current_trade['exit_price'] = current_trade['stop_loss'] # Simulate stop loss exit at stop price
                            elif high_price >= current_trade['take_profit']:
                                exit_signal = 'take_profit'
                                current_trade['exit_price'] = current_trade['take_profit'] # Simulate TP exit at TP price
                            elif signal == 'short' or signal == 'hold': # Consider reversing or closing on opposite signal or hold
                                exit_signal = 'reverse_signal' if signal == 'short' else 'hold_close'
                                current_trade['exit_price'] = close_price # Exit at close price on signal change or hold

                        elif position_side == 'short':
                            if high_price >= current_trade['stop_loss']:
                                exit_signal = 'stop_loss'
                                current_trade['exit_price'] = current_trade['stop_loss']
                            elif low_price <= current_trade['take_profit']:
                                exit_signal = 'take_profit'
                                current_trade['exit_price'] = current_trade['take_profit']
                            elif signal == 'long' or signal == 'hold': # Consider reversing or closing on opposite signal or hold
                                exit_signal = 'reverse_signal' if signal == 'long' else 'hold_close'
                                current_trade['exit_price'] = close_price # Exit at close price on signal change or hold

                        if exit_signal != 'hold':
                            in_position = False
                            current_trade['exit_time'] = datetime_candle
                            current_trade['pnl'] = (current_trade['exit_price'] - current_trade['entry_price']) * current_trade['qty'] if position_side == 'long' else (current_trade['entry_price'] - current_trade['exit_price']) * current_trade['qty']
                            balance += current_trade['pnl']
                            self.narrate(f"Backtest - {datetime_candle} - Exit Signal: {exit_signal}, Exited {position_side} position at {current_trade['exit_price']:.4f}, PnL: {current_trade['pnl']:.2f}, Balance: {balance:.2f}", Fore.MAGENTA)

            # Performance Analysis after backtest
            if trades:
                total_pnl = sum(trade['pnl'] for trade in trades)
                win_trades = sum(1 for trade in trades if trade['pnl'] > 0)
                loss_trades = sum(1 for trade in trades if trade['pnl'] < 0)
                win_rate = (win_trades / len(trades)) * 100 if trades else 0
                profit_factor = sum(trade['pnl'] for trade in trades if trade['pnl'] > 0) / abs(sum(trade['pnl'] for trade in trades if trade['pnl'] < 0)) if loss_trades > 0 else float('inf')
                avg_pnl_per_trade = total_pnl / len(trades) if trades else 0

                returns = np.array([trade['pnl'] for trade in trades]) / balance # Calculate returns based on initial balance
                sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(len(trades)) if np.std(returns) != 0 else 0 # Annualized Sharpe Ratio (assuming trades are roughly independent)
                cumulative_returns = np.cumsum(returns)
                max_drawdown = (np.maximum.accumulate(cumulative_returns) - cumulative_returns).max()

                print(Fore.BLUE + "\n=== Backtesting Performance Metrics ===")
                print(Fore.CYAN + f"Total PnL: {total_pnl:.2f} USDT")
                print(Fore.CYAN + f"Final Balance: {balance:.2f} USDT")
                print(Fore.CYAN + f"Total Trades: {len(trades)}")
                print(Fore.CYAN + f"Win Rate: {win_rate:.2f}%")
                print(Fore.CYAN + f"Profit Factor: {profit_factor:.2f}")
                print(Fore.CYAN + f"Average PnL per Trade: {avg_pnl_per_trade:.2f} USDT")
                print(Fore.CYAN + f"Sharpe Ratio (Annualized, approx): {sharpe_ratio:.2f}")
                print(Fore.CYAN + f"Max Drawdown: {max_drawdown:.2f}") # As fraction of initial balance
                print(Fore.BLUE + "======================================\n")

                logger.info(f"Backtest Performance - Total PnL: {total_pnl:.2f}, Final Balance: {balance:.2f}, Trades: {len(trades)}, Win Rate: {win_rate:.2f}%, Profit Factor: {profit_factor:.2f}, Avg PnL/Trade: {avg_pnl_per_trade:.2f}, Sharpe Ratio: {sharpe_ratio:.2f}, Max Drawdown: {max_drawdown:.2f}")

            else:
                self.narrate("No trades were executed during backtesting.", Fore.YELLOW)

        except ccxt.NetworkError as e:
            self.narrate(f"Network error encountered during backtesting for {symbol}: {e}", Fore.RED)
            logger.error(f"Network error during backtesting: {e}")
        except ccxt.ExchangeError as e:
            self.narrate(f"Exchange error encountered during backtesting for {symbol}: {e}", Fore.RED)
            logger.error(f"Exchange error during backtesting: {e}")
        except Exception as e:
            self.narrate(f"Backtest failed! Error: {e}", Fore.RED)
            logger.error(f"Backtest failed: {e}")

    def main(self, symbol):
        self.narrate(f"The Scalping Ritual has begun for {symbol}!", Fore.MAGENTA)
        while True:
            try:
                order_book = self.fetch_order_book(symbol)
                if order_book is None:
                    self.narrate("The Order Book is missing! I must wait...", Fore.YELLOW)
                    time.sleep(self.analysis_interval) # Wait for analysis interval before next attempt
                    continue

                analysis = self.analyze_order_book(order_book)
                if analysis is None:
                    self.narrate("The Order Book analysis has failed! I cannot proceed...", Fore.YELLOW)
                    time.sleep(self.analysis_interval) # Wait for analysis interval
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

                    order = self.place_order(symbol, signal, 'dynamic', qty, stop_loss_price=stop_loss_price, take_profit_price=take_profit_price) # Use dynamic order type

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

            time.sleep(self.analysis_interval)  # Run analysis at configured interval

def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description='Pyrmethus trading bot')
    parser.add_argument('--symbol', help='Trading symbol (e.g., BTC/USDT:USDT)', default=None)
    parser.add_argument('--backtest', help='Run backtest (YYYY-MM-DD,YYYY-MM-DD)', default=None)
    return parser.parse_args()

def main():
    args = parse_args()
    symbol_cli_arg = args.symbol.strip().upper() if args.symbol else None
    pyrmethus = Pyrmethus(API_KEY, API_SECRET) # Config file is loaded in constructor

    # Determine symbol: command line arg > config file default > prompt user
    symbol = symbol_cli_arg or pyrmethus.config.get('default_symbol') or input(Fore.YELLOW + "Enter the trading symbol (e.g., BTC/USDT:USDT): ").strip().upper()

    if args.backtest:
        start_date, end_date = args.backtest.split(',')
        pyrmethus.backtest(symbol, start_date, end_date)
    else:
        pyrmethus.main(symbol)

if __name__ == "__main__":
    main()
