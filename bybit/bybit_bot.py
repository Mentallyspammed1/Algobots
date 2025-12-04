import asyncio
import decimal
import logging
import os
from collections.abc import Callable
from decimal import Decimal, getcontext
from typing import Any

from pybit.unified_trading import HTTP, WebSocket

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Set decimal precision for financial calculations
getcontext().prec = 10

# --- Enhanced Strategy Configuration ---
RISK_PER_TRADE_PERCENT = decimal.Decimal("0.02")  # Risk 2% of account balance per trade
STOP_LOSS_PERCENT = decimal.Decimal("0.01")  # Set a 1% stop-loss from the entry price
PROFIT_LOCK_PERCENT = decimal.Decimal("0.015")  # Lock in profit at 1.5%
TRAILING_STOP_PERCENT = decimal.Decimal("0.005")  # Trail the stop by 0.5%


async def manage_positions(
    http_client: HTTP, bot_instance: Any, symbols_to_trade: list[str],
):
    """Manages existing positions to lock in profits and trail stop losses."""
    for symbol in symbols_to_trade:
        position_data = bot_instance.ws_manager.positions.get(symbol)
        if not position_data or decimal.Decimal(position_data.get("size", "0")) == 0:
            continue

        position_size = decimal.Decimal(position_data["size"])
        entry_price = decimal.Decimal(position_data["avgPrice"])
        position_side = position_data["side"]

        ticker_data = bot_instance.ws_manager.market_data.get(symbol, {}).get("ticker")
        if not ticker_data or not ticker_data.get("lastPrice"):
            logger.warning(f"[{symbol}] No ticker data to manage position. Skipping.")
            continue

        current_price = decimal.Decimal(ticker_data["lastPrice"])
        tick_size = bot_instance.symbol_info[symbol]["tickSize"]

        # Calculate profit percentage
        if position_side == "Buy":
            profit_percent = (current_price - entry_price) / entry_price
        else:  # Sell
            profit_percent = (entry_price - current_price) / entry_price

        # Check if profit lock threshold is met
        if profit_percent >= PROFIT_LOCK_PERCENT:
            logger.info(
                f"[{symbol}] Profit lock threshold reached ({profit_percent:.4f}%). Adjusting stop-loss.",
            )

            new_stop_loss_price = decimal.Decimal("0")
            if position_side == "Buy":
                # Move stop loss to entry price or trail it
                trailing_stop_price = (
                    current_price * (1 - TRAILING_STOP_PERCENT)
                ).quantize(tick_size)
                # We need the current SL to avoid sending the same request repeatedly
                # For now, we'll just set it to the higher of entry or trailing stop
                new_stop_loss_price = max(entry_price, trailing_stop_price)
            else:  # Sell
                trailing_stop_price = (
                    current_price * (1 + TRAILING_STOP_PERCENT)
                ).quantize(tick_size)
                new_stop_loss_price = min(entry_price, trailing_stop_price)

            try:
                # Modify the existing position's stop loss
                await http_client.set_trading_stop(
                    category="linear",
                    symbol=symbol,
                    stop_loss=str(new_stop_loss_price),
                    position_idx=0,
                )
                logger.info(
                    f"[{symbol}] Adjusted stop-loss to {new_stop_loss_price} to lock in profit.",
                )
            except Exception as e:
                logger.error(f"Error adjusting stop-loss for {symbol}: {e}")


async def market_making_strategy(
    market_data: dict,
    account_info: dict,
    http_client: HTTP,
    bot_instance: Any,
    symbols_to_trade: list[str],
):
    """An enhanced market-making strategy with risk management and profit-locking."""
    logger.info("Executing Enhanced Market Making Strategy...")

    # --- 1. Get Available Balance ---
    available_balance_usd = decimal.Decimal("0")
    if account_info:
        for wallet in account_info:
            if wallet.get("coin") == "USDT":
                available_balance_usd = decimal.Decimal(
                    wallet.get("walletBalance", "0"),
                )
                break

    if available_balance_usd <= 0:
        logger.warning("No available USDT balance. Skipping strategy execution.")
        return

    for symbol in symbols_to_trade:
        logger.info(f"Applying strategy for {symbol}...")

        # --- 2. Get Market Data ---
        orderbook_data = bot_instance.ws_manager.market_data.get(symbol, {}).get(
            "orderbook",
        )
        if (
            not orderbook_data
            or not orderbook_data.get("b")
            or not orderbook_data.get("a")
        ):
            logger.warning(f"Incomplete orderbook data for {symbol}. Skipping.")
            continue

        best_bid = decimal.Decimal(orderbook_data["b"][0][0])
        best_ask = decimal.Decimal(orderbook_data["a"][0][0])
        mid_price = (best_bid + best_ask) / 2

        # --- 3. Smarter Spread Calculation ---
        # Use a blend of the current bid-ask spread and a minimum percentage
        live_spread_percent = (best_ask - best_bid) / mid_price
        min_spread_percent = decimal.Decimal("0.001")  # Minimum 0.1% spread
        desired_spread_percentage = max(live_spread_percent, min_spread_percent)
        desired_spread = mid_price * desired_spread_percentage

        logger.info(
            f"[{symbol}] Live Spread: {live_spread_percent:.4f}%, Desired Spread: {desired_spread_percentage:.4f}%",
        )

        # --- 4. Determine Prices ---
        tick_size = bot_instance.symbol_info[symbol]["tickSize"]
        bot_bid_price = (mid_price - desired_spread / 2).quantize(tick_size)
        bot_ask_price = (mid_price + desired_spread / 2).quantize(tick_size)

        # --- 5. Risk-Managed Quantity Calculation ---
        capital_to_risk = available_balance_usd * RISK_PER_TRADE_PERCENT
        # The quantity is determined by how much we can buy/sell so that a STOP_LOSS_PERCENT move equals our capital_to_risk
        qty_step = bot_instance.symbol_info[symbol]["qtyStep"]
        order_quantity = (capital_to_risk / (mid_price * STOP_LOSS_PERCENT)).quantize(
            qty_step,
        )

        min_order_qty = bot_instance.symbol_info[symbol]["minOrderQty"]
        if order_quantity < min_order_qty:
            order_quantity = min_order_qty
            logger.warning(
                f"[{symbol}] Calculated quantity too small. Using minimum: {order_quantity}",
            )

        logger.info(
            f"[{symbol}] Mid: {mid_price:.4f}, Bid: {bot_bid_price:.4f}, Ask: {bot_ask_price:.4f}, Qty: {order_quantity}",
        )

        # --- 6. Order Management ---
        # Only place new orders if there is no existing position for the symbol
        if (
            not bot_instance.ws_manager.positions.get(symbol)
            or decimal.Decimal(
                bot_instance.ws_manager.positions[symbol].get("size", "0"),
            )
            == 0
        ):
            try:
                await http_client.cancel_all_orders(category="linear", symbol=symbol)
                logger.info(
                    f"[{symbol}] No position found. Placing new buy and sell limit orders.",
                )

                # Place Buy Order with Stop-Loss
                stop_loss_buy_price = (
                    bot_bid_price * (1 - STOP_LOSS_PERCENT)
                ).quantize(tick_size)
                await http_client.place_order(
                    category="linear",
                    symbol=symbol,
                    side="Buy",
                    order_type="Limit",
                    qty=str(order_quantity),
                    price=str(bot_bid_price),
                    time_in_force="GTC",
                    position_idx=0,
                    stop_loss=str(stop_loss_buy_price),
                )
                logger.info(
                    f"Placed BUY order for {order_quantity} {symbol} at {bot_bid_price} with SL at {stop_loss_buy_price}",
                )

                # Place Sell Order with Stop-Loss
                stop_loss_sell_price = (
                    bot_ask_price * (1 + STOP_LOSS_PERCENT)
                ).quantize(tick_size)
                await http_client.place_order(
                    category="linear",
                    symbol=symbol,
                    side="Sell",
                    order_type="Limit",
                    qty=str(order_quantity),
                    price=str(bot_ask_price),
                    time_in_force="GTC",
                    position_idx=0,
                    stop_loss=str(stop_loss_sell_price),
                )
                logger.info(
                    f"Placed SELL order for {order_quantity} {symbol} at {bot_ask_price} with SL at {stop_loss_sell_price}",
                )

            except Exception as e:
                logger.error(f"Error during initial order placement for {symbol}: {e}")
        else:
            logger.info(
                f"[{symbol}] Position already exists. Skipping new order placement.",
            )

    # --- 7. Manage Existing Positions (Profit Locking & Trailing Stop) ---
    await manage_positions(http_client, bot_instance, symbols_to_trade)


# --- WebSocket Manager ---
class BybitWebSocketManager:
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        self.ws_public: WebSocket | None = None
        self.ws_private: WebSocket | None = None
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet

        self.market_data: dict[str, Any] = {}
        self.positions: dict[str, Any] = {}
        self.orders: dict[str, Any] = {}

    def _init_public_ws(self):
        if not self.ws_public:
            self.ws_public = WebSocket(testnet=self.testnet, channel_type="linear")
            logger.info("Public WebSocket initialized.")

    def _init_private_ws(self):
        if not self.ws_private:
            self.ws_private = WebSocket(
                testnet=self.testnet,
                channel_type="private",
                api_key=self.api_key,
                api_secret=self.api_secret,
                recv_window=10000,
            )
            logger.info("Private WebSocket initialized.")

    def handle_orderbook(self, message: dict):
        try:
            data = message.get("data", {})
            symbol = data.get("s")
            if symbol:
                self.market_data[symbol] = self.market_data.get(symbol, {})
                self.market_data[symbol]["orderbook"] = data
        except Exception as e:
            logger.error(f"Error handling orderbook: {e}")

    def handle_ticker(self, message: dict):
        try:
            data = message.get("data", {})
            symbol = data.get("s")
            if symbol:
                self.market_data[symbol] = self.market_data.get(symbol, {})
                self.market_data[symbol]["ticker"] = data
        except Exception as e:
            logger.error(f"Error handling ticker: {e}")

    def handle_position(self, message: dict):
        try:
            data = message.get("data", [])
            for position in data:
                symbol = position.get("symbol")
                if symbol:
                    self.positions[symbol] = position
        except Exception as e:
            logger.error(f"Error handling position: {e}")

    async def subscribe_public_channels(self, symbols: list[str]):
        self._init_public_ws()
        if not self.ws_public:
            return
        for symbol in symbols:
            self.ws_public.orderbook_stream(
                depth=1, symbol=symbol, callback=self.handle_orderbook,
            )
            self.ws_public.ticker_stream(symbol=symbol, callback=self.handle_ticker)
        logger.info(f"Subscribed to public channels for: {symbols}")

    async def subscribe_private_channels(self):
        self._init_private_ws()
        if not self.ws_private:
            return
        self.ws_private.position_stream(callback=self.handle_position)
        logger.info("Subscribed to private channels.")


# --- Trading Bot Core ---
class BybitTradingBot:
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        self.session = HTTP(
            testnet=testnet, api_key=api_key, api_secret=api_secret, recv_window=10000,
        )
        self.ws_manager = BybitWebSocketManager(api_key, api_secret, testnet)
        self.strategy: Callable | None = None
        self.symbol_info: dict[str, Any] = {}

        logger.info(f"Bybit Trading Bot initialized. Testnet: {testnet}")

    async def fetch_symbol_info(self, symbols: list[str]):
        logger.info(f"Fetching instrument info for symbols: {symbols}")
        try:
            response = self.session.get_instruments_info(
                category="linear", symbol=",".join(symbols),
            )
            if response and response["retCode"] == 0:
                for item in response.get("result", {}).get("list", []):
                    symbol = item.get("symbol")
                    self.symbol_info[symbol] = {
                        "minOrderQty": Decimal(item["lotSizeFilter"]["minOrderQty"]),
                        "qtyStep": Decimal(item["lotSizeFilter"]["qtyStep"]),
                        "tickSize": Decimal(item["priceFilter"]["tickSize"]),
                    }
                    logger.info(f"Successfully fetched instrument info for {symbol}.")
            else:
                logger.error(
                    f"Failed to fetch instrument info: {response.get('retMsg')}",
                )
        except Exception as e:
            logger.error(f"Error fetching instrument info: {e}")

    def set_strategy(self, strategy_func: Callable):
        self.strategy = strategy_func
        logger.info("Trading strategy set.")

    async def run(self, symbols: list[str], interval: int = 5):
        if not self.strategy:
            logger.error("No trading strategy set.")
            return

        await self.fetch_symbol_info(symbols)
        await self.ws_manager.subscribe_public_channels(symbols)
        await self.ws_manager.subscribe_private_channels()

        logger.info("Bot starting main loop...")
        while True:
            try:
                account_info = await self.session.get_wallet_balance(
                    accountType="UNIFIED",
                )
                if not account_info or account_info.get("retCode") != 0:
                    logger.warning("Skipping strategy due to missing account data.")
                    await asyncio.sleep(interval)
                    continue

                await self.strategy(
                    account_info["result"]["list"], self.session, self, symbols,
                )

            except KeyboardInterrupt:
                logger.info("Bot stopped by user.")
                break
            except Exception as e:
                logger.error(f"Error in main bot loop: {e}", exc_info=True)

            await asyncio.sleep(interval)


# --- Main Execution ---
async def main():
    API_KEY = os.getenv("BYBIT_API_KEY")
    API_SECRET = os.getenv("BYBIT_API_SECRET")
    USE_TESTNET = os.getenv("BYBIT_USE_TESTNET", "false").lower() == "true"

    if not API_KEY or not API_SECRET:
        logger.error(
            "BYBIT_API_KEY and BYBIT_API_SECRET environment variables must be set.",
        )
        return

    bot = BybitTradingBot(api_key=API_KEY, api_secret=API_SECRET, testnet=USE_TESTNET)
    bot.set_strategy(market_making_strategy)

    symbols_to_trade = ["LINKUSDT", "TRUMPUSDT"]
    await bot.run(symbols=symbols_to_trade, interval=10)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped manually.")
    except Exception as e:
        logger.critical(f"An unhandled error occurred: {e}", exc_info=True)
