# bybit_market_maker_template.py
import logging
import os
import threading
import time
from typing import Any

# Import your helper modules
from bybit_account_helper import BybitAccountHelper
from bybit_market_data_helper import BybitMarketDataHelper
from bybit_orderbook_helper import BybitOrderbookHelper  # PriceLevel for type hinting
from bybit_sizing_helper import BybitSizingHelper
from bybit_unified_order_manager import (  # Using unified manager for orders
    BybitUnifiedOrderManager,
)
from bybit_unified_order_manager import TradingMode  # Using unified manager for orders

# Configure logging for the main script
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
)
logger = logging.getLogger(__name__)

# --- Configuration ---
# IMPORTANT: Replace with your actual API key and secret, or use environment variables.
API_KEY = os.getenv("BYBIT_API_KEY", "YOUR_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET", "YOUR_API_SECRET")
USE_TESTNET = True  # Set to False for mainnet trading

# Trading Parameters
SYMBOL = "BTCUSDT"
CATEGORY = "linear"  # 'linear' for perpetual futures, 'spot' for spot trading
ORDER_QTY_BASE = 0.001  # Base quantity for each side of the market (e.g., 0.001 BTC)
SPREAD_PERCENTAGE = 0.001  # 0.1% spread (0.0005% bid, 0.0005% ask away from mid)
MAX_POSITION_SIZE = 0.005  # Max absolute position (e.g., 0.005 BTC long or short)
ORDER_EXPIRY_SECONDS = 30  # Cancel orders if not filled within this time
ORDER_MODE: TradingMode = (
    "websocket"  # "http" or "websocket" for order placement/amendment/cancellation
)

# --- Global State for Market Maker ---
# Store active orders placed by this bot, keyed by orderId
active_market_maker_orders: dict[str, dict[str, Any]] = {}
# Lock for accessing active_market_maker_orders
active_orders_lock = threading.Lock()


# --- Market Maker Logic ---
class MarketMakerBot:
    def __init__(self, api_key: str, api_secret: str, testnet: bool):
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet

        # Initialize all helper modules
        self.account_helper = BybitAccountHelper(api_key, api_secret, testnet)
        self.market_data_helper = BybitMarketDataHelper(testnet=testnet)
        self.orderbook_helper = BybitOrderbookHelper(
            symbol=SYMBOL,
            category=CATEGORY,
            api_key=api_key,
            api_secret=api_secret,
            testnet=testnet,
            orderbook_stream_depth=25,  # Using a reasonable depth
        )
        self.sizing_helper = BybitSizingHelper(
            testnet=testnet, api_key=api_key, api_secret=api_secret
        )

        # Unified Order Manager handles actual order placement and WS private streams for tracking
        self.order_manager = BybitUnifiedOrderManager(
            api_key=api_key,
            api_secret=api_secret,
            testnet=testnet,
            default_mode=ORDER_MODE,
        )

        self._running = threading.Event()  # Event to control the main bot loop
        self._main_loop_thread: threading.Thread | None = None

    def _get_current_position(self) -> float:
        """Retrieves the current absolute position size for the symbol."""
        positions = self.account_helper.get_positions(category=CATEGORY, symbol=SYMBOL)
        current_size = 0.0
        if positions and positions.get("list"):
            for pos in positions["list"]:
                if pos["symbol"] == SYMBOL:
                    size = float(pos.get("size", 0))
                    if pos.get("side") == "Buy":
                        current_size += size
                    elif pos.get("side") == "Sell":
                        current_size -= size
        return current_size

    def _manage_active_orders(self):
        """Cancels or amends orders that are stale or filled.
        This is a simplified version; a real bot would use WS updates for this.
        """
        with active_orders_lock:
            orders_to_remove = []
            for order_id, order_details in active_market_maker_orders.items():
                if order_details.get("orderStatus") in [
                    "Filled",
                    "Cancelled",
                    "Deactivated",
                    "Rejected",
                ]:
                    logger.info(
                        f"Order {order_id} already in final state: {order_details.get('orderStatus')}. Removing from active tracking."
                    )
                    orders_to_remove.append(order_id)
                    continue

                placed_time = order_details.get("placedTime")
                if (
                    placed_time
                    and (time.time() * 1000 - placed_time) / 1000 > ORDER_EXPIRY_SECONDS
                ):
                    logger.info(f"Order {order_id} timed out. Attempting to cancel.")
                    cancel_response = self.order_manager.cancel_order(
                        category=CATEGORY, symbol=SYMBOL, order_id=order_id
                    )
                    if cancel_response:
                        logger.info(f"Cancelled timed-out order {order_id}.")
                        orders_to_remove.append(order_id)
                    else:
                        logger.error(
                            f"Failed to cancel timed-out order {order_id}. Will retry on next loop."
                        )
                    continue

            for order_id in orders_to_remove:
                del active_market_maker_orders[order_id]

    def _place_market_making_orders(self):
        """Calculates prices and places bid/ask orders, managing existing ones."""
        best_bid_level, best_ask_level = self.orderbook_helper.get_best_bid_ask()
        if not best_bid_level or not best_ask_level:
            logger.warning("Orderbook not ready or empty. Cannot place orders.")
            return

        mid_price = (best_bid_level.price + best_ask_level.price) / 2

        # Calculate target bid/ask prices with spread
        target_bid_price = mid_price * (1 - SPREAD_PERCENTAGE / 2)
        target_ask_price = mid_price * (1 + SPREAD_PERCENTAGE / 2)

        # Round prices to exchange's tick size
        target_bid_price = self.sizing_helper.round_price(
            CATEGORY, SYMBOL, target_bid_price
        )
        target_ask_price = self.sizing_helper.round_price(
            CATEGORY, SYMBOL, target_ask_price
        )

        # Ensure our bid is below current best bid and ask is above current best ask
        # (to avoid immediate fills if we want to provide liquidity)
        # Or, if we want to be aggressive, we place at or slightly inside.
        # For a simple market maker, placing slightly outside is safer to avoid being a taker.
        if target_bid_price >= best_bid_level.price:
            target_bid_price = best_bid_level.price * (
                1 - self.sizing_helper.get_price_tick_size(CATEGORY, SYMBOL)
            )
            target_bid_price = self.sizing_helper.round_price(
                CATEGORY, SYMBOL, target_bid_price
            )
        if target_ask_price <= best_ask_level.price:
            target_ask_price = best_ask_level.price * (
                1 + self.sizing_helper.get_price_tick_size(CATEGORY, SYMBOL)
            )
            target_ask_price = self.sizing_helper.round_price(
                CATEGORY, SYMBOL, target_ask_price
            )

        # Round quantity
        order_qty = self.sizing_helper.round_qty(CATEGORY, SYMBOL, ORDER_QTY_BASE)
        if not self.sizing_helper.is_valid_qty(CATEGORY, SYMBOL, order_qty):
            logger.error(
                f"Calculated order quantity {order_qty} is invalid. Aborting order placement."
            )
            return

        current_position = self._get_current_position()
        logger.debug(f"Current position for {SYMBOL}: {current_position:.4f}")

        # --- Place Bid Order ---
        place_bid = True
        # If we are too long, avoid placing more buy orders
        if current_position >= MAX_POSITION_SIZE:
            logger.warning(
                f"Position ({current_position:.4f}) is at or above MAX_POSITION_SIZE. Skipping bid order."
            )
            place_bid = False

        # Check if there's an existing bid order at the target price
        existing_bid_order = None
        for oid, details in self.order_manager.get_all_tracked_orders().items():
            if (
                details.get("symbol") == SYMBOL
                and details.get("side") == "Buy"
                and details.get("orderStatus") == "New"
                and abs(float(details.get("price", 0)) - target_bid_price)
                < self.sizing_helper.get_price_tick_size(CATEGORY, SYMBOL)
            ):
                existing_bid_order = details
                break

        if place_bid:
            if existing_bid_order:
                # Check if price needs amendment
                if abs(
                    float(existing_bid_order["price"]) - target_bid_price
                ) > self.sizing_helper.get_price_tick_size(CATEGORY, SYMBOL):
                    logger.info(
                        f"Amending existing bid order {existing_bid_order['orderId']} to new price {target_bid_price}."
                    )
                    self.order_manager.amend_order(
                        category=CATEGORY,
                        symbol=SYMBOL,
                        order_id=existing_bid_order["orderId"],
                        new_price=str(target_bid_price),
                    )
            else:
                logger.info(
                    f"Placing new BID order: {order_qty} {SYMBOL} @ {target_bid_price}"
                )
                bid_response = self.order_manager.place_order(
                    category=CATEGORY,
                    symbol=SYMBOL,
                    side="Buy",
                    order_type="Limit",
                    qty=str(order_qty),
                    price=str(target_bid_price),
                    timeInForce="GTC",
                    orderLinkId=f"mm-bid-{int(time.time())}",
                )
                if bid_response:
                    with active_orders_lock:
                        active_market_maker_orders[bid_response["orderId"]] = (
                            self.order_manager.get_tracked_order(
                                bid_response["orderId"]
                            )
                        )
                else:
                    logger.error("Failed to place BID order.")

        # --- Place Ask Order ---
        place_ask = True
        # If we are too short, avoid placing more sell orders
        if current_position <= -MAX_POSITION_SIZE:
            logger.warning(
                f"Position ({current_position:.4f}) is at or below -MAX_POSITION_SIZE. Skipping ask order."
            )
            place_ask = False

        # Check if there's an existing ask order at the target price
        existing_ask_order = None
        for oid, details in self.order_manager.get_all_tracked_orders().items():
            if (
                details.get("symbol") == SYMBOL
                and details.get("side") == "Sell"
                and details.get("orderStatus") == "New"
                and abs(float(details.get("price", 0)) - target_ask_price)
                < self.sizing_helper.get_price_tick_size(CATEGORY, SYMBOL)
            ):
                existing_ask_order = details
                break

        if place_ask:
            if existing_ask_order:
                # Check if price needs amendment
                if abs(
                    float(existing_ask_order["price"]) - target_ask_price
                ) > self.sizing_helper.get_price_tick_size(CATEGORY, SYMBOL):
                    logger.info(
                        f"Amending existing ask order {existing_ask_order['orderId']} to new price {target_ask_price}."
                    )
                    self.order_manager.amend_order(
                        category=CATEGORY,
                        symbol=SYMBOL,
                        order_id=existing_ask_order["orderId"],
                        new_price=str(target_ask_price),
                    )
            else:
                logger.info(
                    f"Placing new ASK order: {order_qty} {SYMBOL} @ {target_ask_price}"
                )
                ask_response = self.order_manager.place_order(
                    category=CATEGORY,
                    symbol=SYMBOL,
                    side="Sell",
                    order_type="Limit",
                    qty=str(order_qty),
                    price=str(target_ask_price),
                    timeInForce="GTC",
                    orderLinkId=f"mm-ask-{int(time.time())}",
                )
                if ask_response:
                    with active_orders_lock:
                        active_market_maker_orders[ask_response["orderId"]] = (
                            self.order_manager.get_tracked_order(
                                ask_response["orderId"]
                            )
                        )
                else:
                    logger.error("Failed to place ASK order.")

    def _market_maker_loop(self):
        """The main loop for the market maker bot."""
        while self._running.is_set():
            try:
                self._manage_active_orders()  # Clean up old orders
                self._place_market_making_orders()  # Place/amend new orders

            except Exception:
                logger.exception("Error in market maker loop.")

            time.sleep(5)  # Run every 5 seconds (adjust frequency as needed)

        logger.info("Market maker loop stopped.")

    def start_bot(self):
        """Starts all necessary helpers and the market maker bot loop."""
        if not self.api_key or not self.api_secret:
            logger.critical("API Key and Secret are not set. Cannot start bot.")
            return

        logger.info("Starting Bybit Market Maker Bot...")

        # Start core services
        self.orderbook_helper.start_orderbook_stream()
        if not self.orderbook_helper.is_orderbook_ready():
            logger.critical("Orderbook helper failed to sync. Aborting bot start.")
            return

        self.order_manager.start()  # This starts its internal WS private listener

        # Give some time for sizing helper to fetch instrument info
        self.sizing_helper._get_instrument_info(CATEGORY, SYMBOL, force_update=True)
        if not self.sizing_helper.get_qty_step(CATEGORY, SYMBOL):
            logger.critical(
                "Sizing helper failed to retrieve instrument info. Aborting bot start."
            )
            return

        self._running.set()
        self._main_loop_thread = threading.Thread(
            target=self._market_maker_loop, daemon=True
        )
        self._main_loop_thread.start()
        logger.info("Market Maker Bot started successfully.")

    def stop_bot(self):
        """Stops the market maker bot and all associated helpers."""
        logger.info("Stopping Bybit Market Maker Bot...")
        self._running.clear()  # Signal the main loop to stop

        if self._main_loop_thread and self._main_loop_thread.is_alive():
            self._main_loop_thread.join(timeout=10)
            if self._main_loop_thread.is_alive():
                logger.warning(
                    "Main market maker loop thread did not terminate gracefully."
                )

        # Cancel any remaining active orders before stopping
        logger.info("Cancelling all remaining active market maker orders...")
        self.order_manager.cancel_all_orders(category=CATEGORY, symbol=SYMBOL)
        time.sleep(2)  # Give time for cancellations to process

        self.orderbook_helper.stop_orderbook_stream()
        self.order_manager.stop()  # This stops its internal WS private listener

        logger.info("Bybit Market Maker Bot stopped.")


# --- Main Execution ---
if __name__ == "__main__":
    if API_KEY == "YOUR_API_KEY" or API_SECRET == "YOUR_API_SECRET":
        logger.critical(
            "Please replace YOUR_API_KEY and YOUR_API_SECRET with your actual credentials in bybit_market_maker_template.py."
        )
        exit()

    bot = MarketMakerBot(API_KEY, API_SECRET, USE_TESTNET)

    try:
        bot.start_bot()
        logger.info("Bot is running. Press Ctrl+C to stop.")
        # Keep the main thread alive indefinitely until Ctrl+C
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Ctrl+C detected. Stopping bot...")
    except Exception:
        logger.exception("An unexpected error occurred in the main program.")
    finally:
        bot.stop_bot()
        logger.info("Program finished.")
