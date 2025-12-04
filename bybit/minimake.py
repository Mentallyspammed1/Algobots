# minimaker.py (Corrected Version)

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import threading
import time
from collections.abc import Callable
from decimal import ROUND_DOWN, Decimal, InvalidOperation, getcontext
from typing import Any

from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket

# Load environment variables from .env file
load_dotenv()

# --- Configuration & Helpers ---
# Set decimal precision for financial calculations
getcontext().prec = 18


def to_decimal(val: Any, default: Decimal = Decimal("0")) -> Decimal:
    """Converts a value to Decimal, robustly handling various input types."""
    try:
        return Decimal(str(val)) if val is not None else default
    except (InvalidOperation, ValueError, TypeError):
        return default


# Load from environment variables
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
USE_TESTNET = str(os.getenv("BYBIT_USE_TESTNET", "true")).lower() in ("true", "1", "t")
LOG_LEVEL = os.getenv("BYBIT_LOG_LEVEL", "INFO").upper()

# --- Logging Setup ---
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# --- Order Manager for State Tracking ---
class OrderManager:
    """A simple in-memory manager to track orders placed by this bot instance."""

    def __init__(self):
        self._orders: dict[str, dict] = {}  # {orderLinkId: {symbol, orderId, ...}}
        self._lock = threading.Lock()

    def add(self, order_response: dict):
        """Adds or updates an order using its orderLinkId."""
        order_link_id = order_response.get("orderLinkId")
        if not order_link_id:
            return
        with self._lock:
            self._orders[order_link_id] = order_response

    def remove(self, order_link_id: str) -> dict | None:
        """Removes an order by its orderLinkId."""
        with self._lock:
            return self._orders.pop(order_link_id, None)

    def get_all_orders(self) -> list[dict]:
        """Returns a list of all tracked orders."""
        with self._lock:
            return list(self._orders.values())

    def get_orders_for_symbol(self, symbol: str) -> list[dict]:
        """Returns all tracked orders for a specific symbol."""
        with self._lock:
            return [o for o in self._orders.values() if o.get("symbol") == symbol]


# --- WebSocket Manager ---
class BybitWebSocketManager:
    """Manages WebSocket connections for Bybit public and private streams."""

    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        self.ws_public: WebSocket | None = None
        self.ws_private: WebSocket | None = None
        self.api_key, self.api_secret, self.testnet = api_key, api_secret, testnet
        self.market_data: dict[str, Any] = {}
        self.positions: dict[str, Any] = {}
        self._lock = threading.Lock()

    def _init_ws(self, private: bool):
        ws_type = "private" if private else "linear"
        ws_obj = WebSocket(
            testnet=self.testnet,
            channel_type=ws_type,
            api_key=self.api_key if private else None,
            api_secret=self.api_secret if private else None,
        )
        if private:
            self.ws_private = ws_obj
            logger.info("Private WebSocket initialized.")
        else:
            self.ws_public = ws_obj
            logger.info("Public WebSocket initialized.")

    def handle_orderbook(self, msg: dict):
        try:
            data = msg.get("data", {})
            symbol = data.get("s")
            if symbol:
                with self._lock:
                    entry = self.market_data.setdefault(symbol, {})
                    entry["orderbook"] = data
                    entry["timestamp"] = msg.get("ts")
        except Exception as e:
            logger.error(f"Error handling orderbook: {e}", exc_info=True)

    def handle_position(self, msg: dict):
        try:
            data = msg.get("data", [])
            for position in data:
                symbol = position.get("symbol")
                if symbol:
                    with self._lock:
                        self.positions[symbol] = position
        except Exception as e:
            logger.error(f"Error handling position: {e}", exc_info=True)

    async def subscribe_public(self, symbols: list[str]):
        if not self.ws_public or not self.is_public_connected():
            self._init_ws(private=False)
        await asyncio.sleep(0.5)
        for symbol in symbols:
            self.ws_public.orderbook_stream(
                depth=1, symbol=symbol, callback=self.handle_orderbook,
            )
            logger.info(f"Subscribed to orderbook.1.{symbol}")

    async def subscribe_private(self):
        if not self.ws_private or not self.is_private_connected():
            self._init_ws(private=True)
        await asyncio.sleep(0.5)
        self.ws_private.position_stream(callback=self.handle_position)
        logger.info("Subscribed to position stream.")

    def stop(self):
        if self.ws_public:
            self.ws_public.exit()
        if self.ws_private:
            self.ws_private.exit()
        logger.info("WebSockets stopped.")

    def is_public_connected(self) -> bool:
        return self.ws_public is not None and self.ws_public.is_connected()

    def is_private_connected(self) -> bool:
        return self.ws_private is not None and self.ws_private.is_connected()


# --- Trading Bot Core ---
class BybitTradingBot:
    """Core Bybit trading bot functionality, integrating HTTP API and WebSocket data."""

    def __init__(self, api_key: str, api_secret: str, testnet: bool, dry_run: bool):
        self.dry_run = dry_run
        self.session = HTTP(testnet=testnet, api_key=api_key, api_secret=api_secret)
        self.ws_manager = BybitWebSocketManager(api_key, api_secret, testnet)
        self.order_manager = OrderManager()
        self.strategy: (
            Callable[[BybitTradingBot, dict, dict, list[str]], None] | None
        ) = None
        self.symbol_info: dict[str, Any] = {}

        # Config from environment
        self.max_open_positions = int(os.getenv("BOT_MAX_OPEN_POSITIONS", 5))
        self.category = os.getenv("BYBIT_CATEGORY", "linear")
        self.min_notional_usd = to_decimal(os.getenv("BOT_MIN_NOTIONAL_USD", "5"))
        self.api_timeout_s = 10

    async def _http_call(self, method: Callable, **kwargs):
        for attempt in range(3):
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(method, **kwargs), timeout=self.api_timeout_s,
                )
            except TimeoutError:
                logger.warning(f"HTTP call {method.__name__} timed out.")
            except Exception as e:
                logger.error(
                    f"HTTP call {method.__name__} failed (attempt {attempt + 1}): {e}",
                )
            await asyncio.sleep(1 * (2**attempt))
        return None

    async def fetch_symbol_info(self, symbols: list[str]):
        logger.info(f"Fetching instrument info for: {symbols}")
        for symbol in symbols:
            response = await self._http_call(
                self.session.get_instruments_info, category=self.category, symbol=symbol,
            )
            if response and response.get("retCode") == 0:
                item = response["result"]["list"][0]
                self.symbol_info[symbol] = {
                    "minOrderQty": to_decimal(item["lotSizeFilter"]["minOrderQty"]),
                    "qtyStep": to_decimal(item["lotSizeFilter"]["qtyStep"]),
                    "tickSize": to_decimal(item["priceFilter"]["tickSize"]),
                }
                logger.info(f"Fetched info for {symbol}: {self.symbol_info[symbol]}")

    def set_strategy(self, strategy_func: Callable):
        self.strategy = strategy_func
        logger.info(f"Strategy '{strategy_func.__name__}' has been set.")

    def _round_qty(self, symbol: str, quantity: Decimal) -> Decimal:
        info = self.symbol_info.get(symbol)
        if not info or info["qtyStep"] <= 0:
            return quantity
        return (quantity / info["qtyStep"]).to_integral_value(
            rounding=ROUND_DOWN,
        ) * info["qtyStep"]

    def _round_price(self, symbol: str, price: Decimal) -> Decimal:
        info = self.symbol_info.get(symbol)
        if not info or info["tickSize"] <= 0:
            return price
        return price.quantize(info["tickSize"], rounding=ROUND_DOWN)

    async def calculate_position_size(
        self, symbol: str, capital_percentage: float, price: Decimal, account_info: dict,
    ) -> Decimal:
        available_balance = to_decimal(
            next(
                (
                    c.get("availableToWithdraw", "0")
                    for acct in account_info.get("list", [])
                    for c in acct.get("coin", [])
                    if c.get("coin") == "USDT"
                ),
                "0",
            ),
        )
        if available_balance <= 0 or price <= 0:
            return Decimal("0")

        target_capital = available_balance * to_decimal(str(capital_percentage))
        qty = self._round_qty(symbol, target_capital / price)

        if qty < self.symbol_info[symbol]["minOrderQty"]:
            return Decimal("0")
        if (qty * price) < self.min_notional_usd:
            return Decimal("0")
        return qty

    async def place_order(self, **kwargs) -> dict | None:
        """Places an order, tracks it, and respects dry-run mode."""
        if self.dry_run:
            mock_response = {"orderId": f"dry_{int(time.time() * 1000)}", **kwargs}
            logger.info(f"[DRY RUN] Would place order: {kwargs}")
            self.order_manager.add(mock_response)
            return mock_response

        order_response = await self._http_call(
            self.session.place_order, category=self.category, **kwargs,
        )
        if order_response and order_response.get("retCode") == 0:
            result = order_response["result"]
            logger.info(f"Order placed successfully: {result}")
            self.order_manager.add({**result, "symbol": kwargs.get("symbol")})
            return result
        logger.error(
            f"Failed to place order: {order_response.get('retMsg') if order_response else 'No response'}",
        )
        return None

    async def cancel_order(self, symbol: str, order_link_id: str) -> bool:
        """Cancels an order, removes it from tracking, respects dry-run mode."""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would cancel order: {order_link_id}")
            self.order_manager.remove(order_link_id)
            return True

        response = await self._http_call(
            self.session.cancel_order,
            category=self.category,
            symbol=symbol,
            orderLinkId=order_link_id,
        )
        if response and response.get("retCode") == 0:
            logger.info(f"Order cancelled successfully: {response['result']}")
            self.order_manager.remove(order_link_id)
            return True
        logger.error(
            f"Failed to cancel order {order_link_id}: {response.get('retMsg') if response else 'No response'}",
        )
        return False

    async def cancel_all_tracked_orders(self):
        logger.info("Cancelling all tracked open orders on shutdown...")
        orders_to_cancel = self.order_manager.get_all_orders()
        if not orders_to_cancel:
            logger.info("No tracked orders to cancel.")
            return

        cancel_tasks = [
            self.cancel_order(o["symbol"], o["orderLinkId"]) for o in orders_to_cancel
        ]
        await asyncio.gather(*cancel_tasks)
        logger.info("Finished cancelling tracked orders.")

    async def run(self, symbols: list[str], interval: int):
        await self.fetch_symbol_info(symbols)
        await self.ws_manager.subscribe_public(symbols)
        await self.ws_manager.subscribe_private()

        logger.info("Bot starting main loop...")
        loop_count = 0
        total_loop_time = 0
        try:
            while True:
                loop_start_time = time.monotonic()

                market_data_tasks = [self._get_market_data(s) for s in symbols]
                all_market_data_list = await asyncio.gather(*market_data_tasks)
                all_market_data = {
                    s: md
                    for s, md in zip(symbols, all_market_data_list, strict=False)
                    if md
                }

                account_info = await self._http_call(
                    self.session.get_wallet_balance, accountType="UNIFIED",
                )

                if self.strategy and all_market_data and account_info:
                    await self.strategy(self, all_market_data, account_info, symbols)
                else:
                    logger.warning("Skipping strategy due to missing data.")

                loop_count += 1
                elapsed = time.monotonic() - loop_start_time
                total_loop_time += elapsed
                if loop_count % 10 == 0:
                    avg_time = total_loop_time / loop_count
                    logger.info(
                        f"Heartbeat | Loop: {loop_count} | Last Duration: {elapsed:.2f}s | Avg Duration: {avg_time:.2f}s",
                    )

                await asyncio.sleep(max(0, interval - elapsed))
        except KeyboardInterrupt:
            logger.info("Shutdown signal received.")
        finally:
            await self.cancel_all_tracked_orders()
            self.ws_manager.stop()
            logger.info("Bot gracefully shut down.")

    async def _get_market_data(self, symbol: str) -> dict | None:
        """Prioritizes fresh WebSocket data, falls back to REST."""
        ws_data = self.ws_manager.market_data.get(symbol)
        now_ms = int(time.time() * 1000)
        data_freshness_ms = int(os.getenv("DATA_FRESH_MS", "5000"))
        if ws_data and (now_ms - ws_data.get("timestamp", 0)) < data_freshness_ms:
            return ws_data

        # Fallback to REST
        response = await self._http_call(
            self.session.get_orderbook, category=self.category, symbol=symbol, limit=1,
        )
        if response and response.get("retCode") == 0:
            ob = response["result"]["list"][0]
            # Normalize to a consistent format
            return {
                "orderbook": {
                    "b": ob.get("b", []),
                    "a": ob.get("a", []),
                    "ts": ob.get("ts", now_ms),
                },
            }
        return None


# --- Market Making Strategy ---
async def market_making_strategy(
    bot: BybitTradingBot,
    market_data: dict[str, Any],
    account_info: dict[str, Any],
    symbols: list[str],
):
    """A stateful market-making strategy that cancels old orders before placing new ones."""
    logger.info("-" * 20 + " Executing Strategy " + "-" * 20)

    # Strategy-specific configuration from environment
    capital_pct = float(os.getenv("STRATEGY_CAPITAL_PERCENT", "0.001"))
    spread_pct = float(os.getenv("STRATEGY_SPREAD_PERCENT", "0.001"))
    tif = os.getenv("STRATEGY_TIME_IN_FORCE", "GTC")

    for symbol in symbols:
        # --- 1. Cancel existing orders for this symbol first ---
        orders_to_cancel = bot.order_manager.get_orders_for_symbol(symbol)
        if orders_to_cancel:
            logger.info(
                f"Found {len(orders_to_cancel)} old orders for {symbol}. Cancelling them.",
            )
            cancel_tasks = [
                bot.cancel_order(o["symbol"], o["orderLinkId"])
                for o in orders_to_cancel
            ]
            await asyncio.gather(*cancel_tasks)

        # --- 2. Check market data and risk ---
        md = market_data.get(symbol, {})
        if not md.get("orderbook", {}).get("b"):
            logger.warning(f"No valid orderbook data for {symbol}. Skipping.")
            continue

        open_positions = sum(
            1
            for p in bot.ws_manager.positions.values()
            if to_decimal(p.get("size", "0")) > 0
        )
        if open_positions >= bot.max_open_positions:
            logger.warning(
                f"Max open positions ({bot.max_open_positions}) reached. Halting new entries.",
            )
            continue

        # --- 3. Calculate and place new bid and ask orders ---
        best_bid = to_decimal(md["orderbook"]["b"][0][0])
        best_ask = to_decimal(md["orderbook"]["a"][0][0])

        buy_qty = await bot.calculate_position_size(
            symbol, capital_pct, best_bid, account_info,
        )
        sell_qty = await bot.calculate_position_size(
            symbol, capital_pct, best_ask, account_info,
        )

        place_tasks = []
        if buy_qty > 0:
            limit_buy_price = bot._round_price(
                symbol, best_bid * (Decimal("1") - to_decimal(str(spread_pct))),
            )
            place_tasks.append(
                bot.place_order(
                    symbol=symbol,
                    side="Buy",
                    order_type="Limit",
                    qty=str(buy_qty),
                    price=str(limit_buy_price),
                    timeInForce=tif,
                    orderLinkId=f"mm_buy_{symbol}_{int(time.time() * 1000)}",
                ),
            )

        if sell_qty > 0:
            limit_sell_price = bot._round_price(
                symbol, best_ask * (Decimal("1") + to_decimal(str(spread_pct))),
            )
            place_tasks.append(
                bot.place_order(
                    symbol=symbol,
                    side="Sell",
                    order_type="Limit",
                    qty=str(sell_qty),
                    price=str(limit_sell_price),
                    timeInForce=tif,
                    orderLinkId=f"mm_sell_{symbol}_{int(time.time() * 1000)}",
                ),
            )

        if place_tasks:
            logger.info(f"Placing {len(place_tasks)} new orders for {symbol}.")
            await asyncio.gather(*place_tasks)


# --- Main Execution ---
async def main():
    parser = argparse.ArgumentParser(description="Bybit Trading Bot")
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["BTCUSDT", "ETHUSDT"],
        help="List of symbols to trade.",
    )
    parser.add_argument(
        "--interval", type=int, default=10, help="Bot execution interval in seconds.",
    )
    # FIX: Added --dry-run argument
    parser.add_argument(
        "--dry-run", action="store_true", help="Run bot without executing trades.",
    )
    args = parser.parse_args()

    if not API_KEY or not API_SECRET:
        logger.critical(
            "BYBIT_API_KEY and BYBIT_API_SECRET must be set in your .env file.",
        )
        return

    logger.info(
        "Pausing for 5 seconds before starting to avoid rate-limiting issues...",
    )
    await asyncio.sleep(5)

    # FIX: Pass args.dry_run to the bot constructor
    bot = BybitTradingBot(
        api_key=API_KEY,
        api_secret=API_SECRET,
        testnet=USE_TESTNET,
        dry_run=args.dry_run,
    )
    bot.set_strategy(market_making_strategy)
    await bot.run(symbols=args.symbols, interval=args.interval)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot process terminated by user.")
