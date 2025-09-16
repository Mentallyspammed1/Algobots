You've created a fantastic set of pybit helper modules! To use them effectively, you'll generally follow these steps:

Save the modules: Save each improved code block into its own .py file (e.g., bybit_account_helper.py, bybit_trade_helper.py, etc.).

Install pybit: If you haven't already, install the pybit library: pip install pybit

Obtain API Credentials: Get your API Key and API Secret from your Bybit account. For testing, you can use the testnet.

Import and Initialize: Import the specific helper module(s) you need and initialize their classes with your credentials.

Call Functions: Use the methods provided by the helper classes to interact with the Bybit API.

Let's walk through a comprehensive example demonstrating how to use multiple helpers together in a single script.

Example: A Simple Trading Script Using Multiple Helpers

This script will:

Fetch market data (current price).

Check account balance.

Place a limit order.

Monitor its status using a WebSocket private stream.

Cancel the order if it's not filled within a certain time.

my_trading_bot.py

code
Python
download
content_copy
expand_less

# my_trading_bot.py
import os
import time
import logging
import threading
from typing import Dict, Any, Optional

# Import your helper modules
from bybit_account_helper import BybitAccountHelper
from bybit_trade_helper import BybitTradeHelper
from bybit_market_data_helper import BybitMarketDataHelper
from bybit_ws_private_helper import BybitWsPrivateHelper
from bybit_orderbook_helper import BybitOrderbookHelper, PriceLevel # Assuming PriceLevel is useful

# Configure logging for the main script
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(filename)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Configuration ---
# IMPORTANT: Replace with your actual API key and secret, or use environment variables.
# For security, environment variables are highly recommended.
API_KEY = os.getenv("BYBIT_API_KEY", "YOUR_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET", "YOUR_API_SECRET")
USE_TESTNET = True # Set to False for mainnet trading

SYMBOL = "BTCUSDT"
CATEGORY = "linear" # Or 'spot', 'inverse', 'option'
ORDER_QTY = "0.001" # Quantity for the order
PRICE_OFFSET_PCT = 0.001 # Place order 0.1% away from current market price
ORDER_TIMEOUT_SECONDS = 60 # Cancel order if not filled within this time

# Global variable to store order status from WebSocket callback
current_order_status: Dict[str, Any] = {}
order_filled_event = threading.Event() # Event to signal when an order is filled/cancelled

# --- WebSocket Callback Functions ---
def handle_private_order_update(message: Dict[str, Any]) -> None:
    """
    Callback function to process private order updates from WebSocket.
    """
    global current_order_status
    data = message.get('data')
    if data:
        for order in data:
            order_id = order.get('orderId')
            symbol = order.get('symbol')
            status = order.get('orderStatus')
            
            # Only update if it's for our monitored order and status has changed
            if order_id == current_order_status.get('orderId') and status != current_order_status.get('orderStatus'):
                logger.info(f"Order Update (WS): Order ID {order_id}, Symbol {symbol}, Status {status}")
                current_order_status = order # Update the global status
                
                if status in ["Filled", "PartiallyFilled", "Cancelled", "Deactivated"]:
                    order_filled_event.set() # Signal that the order is no longer active

def run_ws_private_helper(ws_helper: BybitWsPrivateHelper):
    """Function to run the private WebSocket helper in a separate thread."""
    try:
        if ws_helper.connect(wait_for_connection=True, timeout=15):
            logger.info("Private WS helper connected. Subscribing to order stream...")
            ws_helper.subscribe_to_order_stream(handle_private_order_update)
            # Keep the thread alive while the main script runs
            while ws_helper.is_connected() and not order_filled_event.is_set():
                time.sleep(1) 
        else:
            logger.error("Failed to connect private WS helper.")
    except Exception as e:
        logger.exception("Error in private WS helper thread.")
    finally:
        ws_helper.disconnect()
        logger.info("Private WS helper thread finished.")


def main():
    if API_KEY == "YOUR_API_KEY" or API_SECRET == "YOUR_API_SECRET":
        logger.critical("API Key and Secret are not set. Exiting.")
        return

    # --- Initialize Helpers ---
    account_helper = BybitAccountHelper(API_KEY, API_SECRET, testnet=USE_TESTNET)
    trade_helper = BybitTradeHelper(API_KEY, API_SECRET, testnet=USE_TESTNET)
    market_data_helper = BybitMarketDataHelper(testnet=USE_TESTNET)
    orderbook_helper = BybitOrderbookHelper(
        symbol=SYMBOL, category=CATEGORY, api_key=API_KEY, api_secret=API_SECRET,
        testnet=USE_TESTNET, orderbook_stream_depth=25
    )
    ws_private_helper = BybitWsPrivateHelper(API_KEY, API_SECRET, testnet=USE_TESTNET)

    # --- Start Orderbook Helper (in background) ---
    logger.info("Starting Orderbook Helper...")
    orderbook_helper.start_orderbook_stream()
    if not orderbook_helper.is_orderbook_ready():
        logger.critical("Orderbook helper failed to sync. Exiting.")
        return
    logger.info("Orderbook Helper ready.")

    # --- Start Private WebSocket Helper (in background thread) ---
    logger.info("Starting Private WebSocket Helper thread...")
    ws_private_thread = threading.Thread(target=run_ws_private_helper, args=(ws_private_helper,), daemon=True)
    ws_private_thread.start()
    time.sleep(3) # Give WS thread time to connect and subscribe
    if not ws_private_helper.is_connected():
        logger.critical("Private WS helper thread failed to connect. Exiting.")
        orderbook_helper.stop_orderbook_stream()
        return

    try:
        # 1. Get Current Market Price
        logger.info(f"\n--- Getting current market price for {SYMBOL} ---")
        best_bid, best_ask = orderbook_helper.get_best_bid_ask()
        if not best_bid or not best_ask:
            logger.error(f"Could not get best bid/ask for {SYMBOL}. Aborting.")
            return

        mid_price = (best_bid.price + best_ask.price) / 2
        buy_price = round(mid_price * (1 - PRICE_OFFSET_PCT), 5) # Buy slightly below mid
        sell_price = round(mid_price * (1 + PRICE_OFFSET_PCT), 5) # Sell slightly above mid

        logger.info(f"Current Mid Price: {mid_price:.5f}, Calculated Buy Price: {buy_price:.5f}, Sell Price: {sell_price:.5f}")

        # 2. Check Account Balance
        logger.info("\n--- Checking account balance ---")
        wallet_balance = account_helper.get_wallet_balance(account_type="UNIFIED")
        if wallet_balance and wallet_balance.get('list'):
            usdt_balance = 0
            for account in wallet_balance['list']:
                if account.get('accountType') == 'UNIFIED':
                    for coin_info in account.get('coin', []):
                        if coin_info.get('coin') == 'USDT':
                            usdt_balance = float(coin_info.get('availableToWithdraw', 0))
                            break
            logger.info(f"Available USDT Balance: {usdt_balance:.2f}")
            if usdt_balance < float(ORDER_QTY) * buy_price:
                logger.warning("Insufficient USDT balance to place buy order. Aborting.")
                return
        else:
            logger.error("Failed to retrieve wallet balance. Aborting.")
            return

        # 3. Place a Limit Order (e.g., Buy order)
        logger.info(f"\n--- Placing a BUY Limit Order for {ORDER_QTY} {SYMBOL} at {buy_price} ---")
        client_order_id = f"my-bot-buy-{int(time.time())}"
        place_order_response = trade_helper.place_order(
            category=CATEGORY,
            symbol=SYMBOL,
            side="Buy",
            order_type="Limit",
            qty=ORDER_QTY,
            price=str(buy_price),
            timeInForce="GTC",
            orderLinkId=client_order_id
        )

        if place_order_response:
            order_id = place_order_response.get('orderId')
            logger.info(f"Order placed successfully. Order ID: {order_id}, Client Order ID: {client_order_id}")
            global current_order_status
            current_order_status = {
                'orderId': order_id,
                'orderLinkId': client_order_id,
                'symbol': SYMBOL,
                'orderStatus': 'New' # Initial status
            }

            # 4. Monitor Order Status via WebSocket
            logger.info(f"\n--- Monitoring order {order_id} via WebSocket for {ORDER_TIMEOUT_SECONDS} seconds ---")
            
            # Wait for the order to be filled or timeout
            order_filled_event.wait(timeout=ORDER_TIMEOUT_SECONDS)

            if order_filled_event.is_set():
                logger.info(f"Order {order_id} status changed: {current_order_status.get('orderStatus')}")
                if current_order_status.get('orderStatus') == "Filled":
                    logger.info(f"Order {order_id} was FILLED!")
                elif current_order_status.get('orderStatus') == "PartiallyFilled":
                    logger.info(f"Order {order_id} was PARTIALLY FILLED. Remaining to be decided.")
                else:
                    logger.info(f"Order {order_id} was CANCELLED or DEACTIVATED by exchange.")
            else:
                logger.warning(f"Order {order_id} timed out after {ORDER_TIMEOUT_SECONDS} seconds. Current status: {current_order_status.get('orderStatus')}")
                # 5. Cancel the Order if Timed Out
                if current_order_status.get('orderStatus') not in ["Filled", "PartiallyFilled", "Cancelled", "Deactivated"]:
                    logger.info(f"Attempting to cancel timed-out order {order_id}...")
                    cancel_response = trade_helper.cancel_order(
                        category=CATEGORY,
                        symbol=SYMBOL,
                        order_id=order_id
                    )
                    if cancel_response:
                        logger.info(f"Order {order_id} cancellation initiated: {cancel_response}")
                    else:
                        logger.error(f"Failed to cancel order {order_id}.")
        else:
            logger.error("Failed to place order. Aborting.")

    except Exception as e:
        logger.exception("An unhandled error occurred in the main trading bot loop.")
    finally:
        logger.info("\n--- Cleaning up and stopping helpers ---")
        orderbook_helper.stop_orderbook_stream()
        ws_private_helper.disconnect()
        logger.info("All helpers stopped. Script finished.")

if __name__ == "__main__":
    main()
How to Use This Example:

Save Helper Modules: Ensure you have the following files in the same directory as my_trading_bot.py:

bybit_account_helper.py

bybit_trade_helper.py

bybit_market_data_helper.py

bybit_ws_private_helper.py

bybit_orderbook_helper.py (which includes PriceLevel, OptimizedSkipList, EnhancedHeap, AdvancedOrderbookManager)

Set API Credentials:

Open my_trading_bot.py.

Strongly Recommended: Set your BYBIT_API_KEY and BYBIT_API_SECRET as environment variables.

On Linux/macOS: export BYBIT_API_KEY="your_key" and export BYBIT_API_SECRET="your_secret"

On Windows (Command Prompt): set BYBIT_API_KEY="your_key" and set BYBIT_API_SECRET="your_secret"

Then run your script from that terminal.

Alternatively (less secure for production), directly replace "YOUR_API_KEY" and "YOUR_API_SECRET" in the script.

Set USE_TESTNET = True for testing to avoid real money risks.

Run the Script:

code
Bash
download
content_copy
expand_less
IGNORE_WHEN_COPYING_START
IGNORE_WHEN_COPYING_END
python my_trading_bot.py

What the script does:

Initialization: Creates instances of all necessary helper classes.

Orderbook Stream: Starts the BybitOrderbookHelper in the background to continuously maintain an accurate orderbook. This is crucial for getting reliable prices.

Private WS Stream: Starts the BybitWsPrivateHelper in a separate thread to listen for real-time updates on your orders.

Get Price: Fetches the current best bid/ask from the OrderbookHelper to calculate a mid-price.

Check Balance: Uses BybitAccountHelper to verify you have enough USDT to place a buy order.

Place Order: Uses BybitTradeHelper to place a limit buy order slightly below the current mid-price.

Monitor Order: Waits for ORDER_TIMEOUT_SECONDS. During this time, the handle_private_order_update callback (from BybitWsPrivateHelper) will update the current_order_status if the order's status changes (e.g., to Filled, Cancelled).

Timeout/Cancellation: If the order isn't filled by the timeout, it attempts to cancel the order using BybitTradeHelper.

Cleanup: Ensures all WebSocket connections and background threads are properly shut down.

This example demonstrates a basic but robust workflow, showing how to leverage the specialized functions provided by each helper module. You can expand upon this by adding more complex logic, risk management, multiple symbols, and different order strategies.
