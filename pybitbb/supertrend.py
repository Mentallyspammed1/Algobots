# supertrend_cross_bot.py
import logging
import threading
import time
from typing import Any, Literal

# Import your helper modules
from bybit_account_helper import BybitAccountHelper
from bybit_sizing_helper import BybitSizingHelper
from bybit_unified_order_manager import BybitUnifiedOrderManager
from indicators import BybitIndicators

# Import the configuration
import config

# Configure logging for the bot
logging.basicConfig(
    level=getattr(
        logging, config.LOG_LEVEL.upper(), logging.INFO
    ),  # Set log level from config
    format="%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
)
logger = logging.getLogger(__name__)

# --- Bot State ---
PositionSide = Literal["long", "short", "flat"]
current_bot_position: PositionSide = "flat"
last_supertrend_signal: Literal["long", "short"] | None = None
last_processed_kline_timestamp: int = 0  # To avoid reprocessing the same kline


# --- Bot Implementation ---
class SupertrendCrossBot:
    def __init__(self):  # Removed api_key, api_secret, testnet from __init__
        # Use values from config.py
        self.api_key = config.API_KEY
        self.api_secret = config.API_SECRET
        self.testnet = config.USE_TESTNET

        # Validate API keys early
        if (
            self.api_key == "YOUR_API_KEY_HERE"
            or self.api_secret == "YOUR_API_SECRET_HERE"
        ):
            logger.critical(
                "API Key and Secret are not set in config.py. Please update them."
            )
            raise ValueError("API Key and Secret must be provided in config.py.")

        # Initialize helpers with config values
        self.account_helper = BybitAccountHelper(
            self.api_key, self.api_secret, self.testnet
        )
        self.sizing_helper = BybitSizingHelper(
            testnet=self.testnet, api_key=self.api_key, api_secret=self.api_secret
        )
        self.order_manager = BybitUnifiedOrderManager(
            api_key=self.api_key,
            api_secret=self.api_secret,
            testnet=self.testnet,
            default_mode=config.ORDER_MODE,
            ws_recv_window=config.WS_RECV_WINDOW,
        )
        self.indicators_helper = BybitIndicators(
            testnet=self.testnet, api_key=self.api_key, api_secret=self.api_secret
        )

        self._running = threading.Event()  # Event to control the main bot loop
        self._main_loop_thread: threading.Thread | None = None

        # Ensure sizing info is loaded
        self._load_sizing_info()

    def _load_sizing_info(self):
        """Loads instrument sizing information and validates it."""
        logger.info(
            f"Loading sizing information for {config.SYMBOL} ({config.CATEGORY})..."
        )
        self.sizing_helper._get_instrument_info(
            config.CATEGORY, config.SYMBOL, force_update=True
        )
        if not self.sizing_helper.get_qty_step(config.CATEGORY, config.SYMBOL):
            logger.critical(
                "Sizing helper failed to retrieve instrument info. Cannot proceed."
            )
            raise RuntimeError("Failed to load instrument sizing information.")
        logger.info(
            f"Sizing info loaded. Qty step: {self.sizing_helper.get_qty_step(config.CATEGORY, config.SYMBOL)}, Price tick: {self.sizing_helper.get_price_tick_size(config.CATEGORY, config.SYMBOL)}"
        )

    def _get_current_bybit_position(self) -> tuple[PositionSide, float]:
        """Retrieves the current position from Bybit.
        :return: A tuple of (position_side, position_size).
        """
        positions = self.account_helper.get_positions(
            category=config.CATEGORY, symbol=config.SYMBOL
        )
        if positions and positions.get("list"):
            for pos in positions["list"]:
                if pos["symbol"] == config.SYMBOL:
                    size = float(pos.get("size", 0))
                    if size > 0:
                        return "long" if pos.get("side") == "Buy" else "short", size
                    return "flat", 0.0
        return "flat", 0.0

    def _calculate_order_quantity(self, current_price: float) -> str:
        """Calculates order quantity based on desired USDT value and current price."""
        if current_price <= 0:
            logger.error(
                "Current price is zero or negative, cannot calculate order quantity."
            )
            return "0"

        raw_qty = config.ORDER_QTY_USDT_VALUE / current_price
        rounded_qty = self.sizing_helper.round_qty(
            config.CATEGORY, config.SYMBOL, raw_qty
        )

        if not self.sizing_helper.is_valid_qty(
            config.CATEGORY, config.SYMBOL, rounded_qty
        ):
            logger.error(
                f"Calculated quantity {rounded_qty} is not valid for {config.SYMBOL}. Raw: {raw_qty}"
            )
            return "0"

        return str(rounded_qty)

    def _place_market_order(
        self, side: Literal["Buy", "Sell"], qty: str
    ) -> dict[str, Any] | None:
        """Places a market order and updates internal position."""
        logger.info(
            f"Attempting to place MARKET {side} order for {qty} {config.SYMBOL}..."
        )
        response = self.order_manager.place_order(
            category=config.CATEGORY,
            symbol=config.SYMBOL,
            side=side,
            order_type="Market",
            qty=qty,
            orderLinkId=f"st-cross-{side.lower()}-{int(time.time())}",
        )
        if response and response.get("orderId"):
            logger.info(f"Market {side} order placed (ID: {response['orderId']}).")
            return response
        logger.error(f"Failed to place market {side} order.")
        return None

    def _close_position(self, current_side: PositionSide, current_size: float) -> bool:
        """Closes an existing position."""
        if current_side == "flat" or current_size == 0:
            logger.info("No position to close.")
            return True

        opposite_side = "Sell" if current_side == "long" else "Buy"
        qty_to_close = self.sizing_helper.round_qty(
            config.CATEGORY, config.SYMBOL, current_size
        )

        logger.info(
            f"Attempting to close {current_side} position of {qty_to_close} {config.SYMBOL} with a market {opposite_side} order."
        )
        response = self.order_manager.place_order(
            category=config.CATEGORY,
            symbol=config.SYMBOL,
            side=opposite_side,
            order_type="Market",
            qty=str(qty_to_close),
            orderLinkId=f"st-close-{current_side}-{int(time.time())}",
        )
        if response and response.get("orderId"):
            logger.info(
                f"Position close order placed (ID: {response['orderId']}). Waiting for fill..."
            )
            time.sleep(2)  # Give time for close order to process
            return True
        logger.error(f"Failed to place position close order for {current_side}.")
        return False

    def _main_bot_loop(self):
        """The main execution loop for the Supertrend cross bot."""
        global \
            current_bot_position, \
            last_supertrend_signal, \
            last_processed_kline_timestamp

        while self._running.is_set():
            try:
                # 1. Fetch kline data and calculate Supertrend
                df = self.indicators_helper.get_supertrend(
                    category=config.CATEGORY,
                    symbol=config.SYMBOL,
                    interval=config.INTERVAL,
                    length=config.SUPERTREND_LENGTH,
                    multiplier=config.SUPERTREND_MULTIPLIER,
                    limit=config.KLINES_LIMIT,
                )

                if df is None or df.empty:
                    logger.warning(
                        f"No sufficient data to calculate Supertrend for {config.SYMBOL}. Retrying in 10 seconds."
                    )
                    time.sleep(10)
                    continue

                # Ensure we only process new, closed klines
                latest_kline_timestamp = (
                    df.index[-1].timestamp() * 1000
                )  # Convert to ms
                if latest_kline_timestamp <= last_processed_kline_timestamp:
                    logger.debug(
                        f"No new closed kline to process. Last processed: {last_processed_kline_timestamp}"
                    )
                    time.sleep(5)  # Check more frequently for new kline
                    continue

                last_processed_kline_timestamp = latest_kline_timestamp

                # Get the latest Supertrend values
                supertrend_column = (
                    f"SUPERT_{config.SUPERTREND_LENGTH}_{config.SUPERTREND_MULTIPLIER}"
                )
                supertrend_direction_column = (
                    f"SUPERTd_{config.SUPERTREND_LENGTH}_{config.SUPERTREND_MULTIPLIER}"
                )

                if (
                    supertrend_column not in df.columns
                    or supertrend_direction_column not in df.columns
                ):
                    logger.error(
                        f"Supertrend columns '{supertrend_column}' or '{supertrend_direction_column}' not found in DataFrame. Check pandas_ta version or indicator calculation."
                    )
                    time.sleep(10)
                    continue

                latest_close = df["close"].iloc[-1]
                latest_supertrend = df[supertrend_column].iloc[-1]
                latest_supertrend_direction = df[supertrend_direction_column].iloc[
                    -1
                ]  # 1 for uptrend, -1 for downtrend

                logger.info(
                    f"[{config.SYMBOL}] Latest Close: {latest_close:.2f}, Supertrend: {latest_supertrend:.2f}, Direction: {latest_supertrend_direction}"
                )

                # 2. Generate Signals
                signal: Literal["long", "short"] | None = None
                if (
                    latest_supertrend_direction == 1
                    and latest_close > latest_supertrend
                ):  # Uptrend confirmed
                    signal = "long"
                elif (
                    latest_supertrend_direction == -1
                    and latest_close < latest_supertrend
                ):  # Downtrend confirmed
                    signal = "short"

                if signal is None:
                    logger.debug("No clear Supertrend cross signal detected.")
                    time.sleep(5)
                    continue

                if signal == last_supertrend_signal:
                    logger.debug(
                        f"Signal is '{signal}', same as last signal. No new action."
                    )
                    time.sleep(5)
                    continue

                logger.info(f"NEW SIGNAL DETECTED: {signal.upper()}!")
                last_supertrend_signal = signal

                # 3. Manage Position based on Signal
                bybit_position_side, bybit_position_size = (
                    self._get_current_bybit_position()
                )
                logger.info(
                    f"Current Bybit position: {bybit_position_side.upper()} {bybit_position_size:.4f} {config.SYMBOL}"
                )

                # Calculate order quantity
                order_qty_str = self._calculate_order_quantity(latest_close)
                if order_qty_str == "0":
                    logger.error(
                        "Calculated order quantity is 0 or invalid. Skipping trade action."
                    )
                    time.sleep(10)
                    continue

                # If signal is LONG
                if signal == "long":
                    if bybit_position_side == "flat":
                        self._place_market_order("Buy", order_qty_str)
                        current_bot_position = "long"
                    elif bybit_position_side == "short":
                        logger.info("Closing SHORT position and going LONG.")
                        if self._close_position("short", bybit_position_size):
                            time.sleep(1)  # Give time for close order to process
                            self._place_market_order("Buy", order_qty_str)
                            current_bot_position = "long"
                    elif bybit_position_side == "long":
                        logger.info("Already LONG, no action needed.")

                # If signal is SHORT
                elif signal == "short":
                    if bybit_position_side == "flat":
                        self._place_market_order("Sell", order_qty_str)
                        current_bot_position = "short"
                    elif bybit_position_side == "long":
                        logger.info("Closing LONG position and going SHORT.")
                        if self._close_position("long", bybit_position_size):
                            time.sleep(1)  # Give time for close order to process
                            self._place_market_order("Sell", order_qty_str)
                            current_bot_position = "short"
                    elif bybit_position_side == "short":
                        logger.info("Already SHORT, no action needed.")

                time.sleep(10)  # Wait before next full cycle

            except Exception:
                logger.exception("Error in Supertrend bot main loop.")
                time.sleep(15)  # Longer sleep on error to avoid rapid API calls

        logger.info("Supertrend bot loop stopped.")

    def start_bot(self):
        """Starts all necessary helpers and the Supertrend bot loop."""
        global current_bot_position, last_supertrend_signal

        # API key validation is now done in __init__

        logger.info("Starting Bybit Supertrend Cross Bot...")

        # Start Unified Order Manager (handles its internal WS private listener)
        self.order_manager.start()

        # Initial check of current position on Bybit
        bybit_pos_side, bybit_pos_size = self._get_current_bybit_position()
        current_bot_position = bybit_pos_side
        logger.info(
            f"Bot starting with current Bybit position: {bybit_pos_side.upper()} {bybit_pos_size:.4f} {config.SYMBOL}"
        )

        self._running.set()
        self._main_loop_thread = threading.Thread(
            target=self._main_bot_loop, daemon=True
        )
        self._main_loop_thread.start()
        logger.info("Supertrend Cross Bot started successfully.")

    def stop_bot(self):
        """Stops the bot and all associated helpers."""
        logger.info("Stopping Bybit Supertrend Cross Bot...")
        self._running.clear()  # Signal the main loop to stop

        if self._main_loop_thread and self._main_loop_thread.is_alive():
            self._main_loop_thread.join(timeout=10)
            if self._main_loop_thread.is_alive():
                logger.warning("Main bot loop thread did not terminate gracefully.")

        # Ensure all pending orders are cancelled (if any)
        logger.info("Cancelling any remaining open orders...")
        self.order_manager.cancel_all_orders(
            category=config.CATEGORY, symbol=config.SYMBOL
        )

        # Stop Unified Order Manager
        self.order_manager.stop()

        logger.info("Bybit Supertrend Cross Bot stopped.")


# --- Main Execution ---
if __name__ == "__main__":
    # The bot class now reads config directly, so no need to pass parameters here.
    bot = SupertrendCrossBot()

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
