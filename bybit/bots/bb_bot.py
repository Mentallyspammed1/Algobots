# bybit_bot.py

import asyncio
import logging
import os
import random
import threading
import time
from collections.abc import Callable
from decimal import ROUND_DOWN, Decimal, InvalidOperation, getcontext
from typing import Any

from pybit.unified_trading import HTTP, WebSocket

# Set decimal precision for financial calculations
getcontext().prec = 18  # Increased precision for safer financial math


# --- Helpers / Configuration ---
def env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "t", "yes", "y", "on")


def to_decimal(val: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        if isinstance(val, Decimal):
            return val
        if val is None:
            return default
        return Decimal(str(val))
    except (InvalidOperation, ValueError, TypeError):
        return default


# Load API credentials from environment variables
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
USE_TESTNET = env_bool("BYBIT_USE_TESTNET", False)

# --- Logging Setup ---
LOG_LEVEL = os.getenv("BYBIT_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# --- WebSocket Manager ---
class BybitWebSocketManager:
    """Manages WebSocket connections for Bybit public and private streams.
    Stores real-time market data, positions, and orders.
    """

    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        self.ws_public: WebSocket | None = None
        self.ws_private: WebSocket | None = None
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet

        self.market_data: dict[str, Any] = {}  # Stores orderbook, ticker, last_trade
        self.positions: dict[str, Any] = {}  # Stores open positions
        self.orders: dict[str, Any] = {}  # Stores open/recent orders

        self._public_subscriptions: list[str] = []
        self._private_subscriptions: list[str] = []
        self._lock = threading.Lock()  # Thread-safety for WS callbacks

    def _init_public_ws(self):
        """Initializes the public WebSocket connection if not already active."""
        try:
            if not self.ws_public or not self.is_public_connected():
                self.ws_public = WebSocket(
                    testnet=self.testnet,
                    channel_type="linear",  # Or "spot", "inverse" based on needs
                )
                logger.info("Public WebSocket initialized.")
        except Exception as e:
            logger.error(f"Error initializing public WebSocket: {e}", exc_info=True)

    def _init_private_ws(self):
        """Initializes the private WebSocket connection if not already active."""
        try:
            if not self.ws_private or not self.is_private_connected():
                self.ws_private = WebSocket(
                    testnet=self.testnet,
                    channel_type="private",
                    api_key=self.api_key,
                    api_secret=self.api_secret,
                    recv_window=10000,
                )
                logger.info("Private WebSocket initialized.")
        except Exception as e:
            logger.error(f"Error initializing private WebSocket: {e}", exc_info=True)

    def handle_orderbook(self, message: dict):
        """Processes orderbook updates and stores the data."""
        try:
            data = message.get("data", {})
            symbol = data.get("s") or data.get("symbol")
            ts = data.get("ts") or message.get("ts") or message.get("time")
            if symbol:
                with self._lock:
                    entry = self.market_data.setdefault(symbol, {})
                    # Store orderbook in a normalized dict with 'b' and 'a'
                    if isinstance(data, dict):
                        book = {
                            "s": symbol,
                            "b": data.get("b", []),
                            "a": data.get("a", []),
                            "ts": ts,
                        }
                        entry["orderbook"] = book
                        entry["timestamp"] = ts
        except Exception as e:
            logger.error(f"Error handling orderbook: {e}", exc_info=True)

    def handle_trades(self, message: dict):
        """Processes trade updates and stores the latest trade."""
        try:
            data = message.get("data", [])
            for trade in data:
                symbol = trade.get("s") or trade.get("symbol")
                if symbol:
                    with self._lock:
                        self.market_data.setdefault(symbol, {})["last_trade"] = trade
        except Exception as e:
            logger.error(f"Error handling trades: {e}", exc_info=True)

    def handle_ticker(self, message: dict):
        """Processes ticker updates and stores the data."""
        try:
            data = message.get("data", {})
            symbol = data.get("s") or data.get("symbol")
            if symbol:
                with self._lock:
                    self.market_data.setdefault(symbol, {})["ticker"] = data
        except Exception as e:
            logger.error(f"Error handling ticker: {e}", exc_info=True)

    def handle_position(self, message: dict):
        """Processes position updates and stores them by symbol."""
        try:
            data = message.get("data", [])
            for position in data:
                symbol = position.get("symbol")
                if symbol:
                    with self._lock:
                        self.positions[symbol] = position
        except Exception as e:
            logger.error(f"Error handling position: {e}", exc_info=True)

    def handle_order(self, message: dict):
        """Processes order updates and stores them by orderId."""
        try:
            data = message.get("data", [])
            for order in data:
                order_id = order.get("orderId")
                if order_id:
                    with self._lock:
                        self.orders[order_id] = order
        except Exception as e:
            logger.error(f"Error handling order: {e}", exc_info=True)

    def handle_execution(self, message: dict):
        """Processes execution/fill updates."""
        try:
            data = message.get("data", [])
            for execution in data:
                order_id = execution.get("orderId")
                if order_id:
                    logger.info(
                        f"Execution for {order_id}: Price: {execution.get('execPrice')}, Qty: {execution.get('execQty')}, Side: {execution.get('side')}"
                    )
        except Exception as e:
            logger.error(f"Error handling execution: {e}", exc_info=True)

    def handle_wallet(self, message: dict):
        """Processes wallet updates."""
        try:
            data = message.get("data", [])
            for wallet_data in data:
                coin = wallet_data.get("coin")
                if coin:
                    logger.info(
                        f"Wallet update for {coin}: Available: {wallet_data.get('availableToWithdraw')}, Total: {wallet_data.get('walletBalance')}"
                    )
        except Exception as e:
            logger.error(f"Error handling wallet: {e}", exc_info=True)

    async def subscribe_public_channels(
        self,
        symbols: list[str],
        channels: list[str] = ["orderbook", "publicTrade", "tickers"],
    ):
        """Subscribes to public market data channels for specified symbols."""
        self._init_public_ws()
        if not self.ws_public:
            logger.error("Public WebSocket not initialized for subscription.")
            return

        # Add a small delay to allow WebSocket to fully establish before subscribing
        await asyncio.sleep(0.5)

        for symbol in symbols:
            if (
                "orderbook" in channels
                and f"orderbook.1.{symbol}" not in self._public_subscriptions
            ):
                try:
                    self.ws_public.orderbook_stream(
                        depth=1,  # Small depth for quick updates
                        symbol=symbol,
                        callback=self.handle_orderbook,
                    )
                    self._public_subscriptions.append(f"orderbook.1.{symbol}")
                    logger.info(f"Subscribed to orderbook.1.{symbol}")
                except Exception as e:
                    logger.error(
                        f"Error subscribing to orderbook for {symbol}: {e}",
                        exc_info=True,
                    )
            if (
                "publicTrade" in channels
                and f"publicTrade.{symbol}" not in self._public_subscriptions
            ):
                try:
                    self.ws_public.trade_stream(
                        symbol=symbol, callback=self.handle_trades
                    )
                    self._public_subscriptions.append(f"publicTrade.{symbol}")
                    logger.info(f"Subscribed to publicTrade.{symbol}")
                except Exception as e:
                    logger.error(
                        f"Error subscribing to publicTrade for {symbol}: {e}",
                        exc_info=True,
                    )
            if (
                "tickers" in channels
                and f"tickers.{symbol}" not in self._public_subscriptions
            ):
                try:
                    self.ws_public.ticker_stream(
                        symbol=symbol, callback=self.handle_ticker
                    )
                    self._public_subscriptions.append(f"tickers.{symbol}")
                    logger.info(f"Subscribed to tickers.{symbol}")
                except Exception as e:
                    logger.error(
                        f"Error subscribing to tickers for {symbol}: {e}", exc_info=True
                    )

    async def subscribe_private_channels(
        self, channels: list[str] = ["position", "order", "execution", "wallet"]
    ):
        """Subscribes to private account channels."""
        self._init_private_ws()
        if not self.ws_private:
            logger.error("Private WebSocket not initialized for subscription.")
            return

        # Add a small delay to allow WebSocket to fully establish before subscribing
        await asyncio.sleep(0.5)

        if "position" in channels and "position" not in self._private_subscriptions:
            try:
                self.ws_private.position_stream(callback=self.handle_position)
                self._private_subscriptions.append("position")
                logger.info("Subscribed to position stream.")
            except Exception as e:
                logger.error(
                    f"Error subscribing to position stream: {e}", exc_info=True
                )
        if "order" in channels and "order" not in self._private_subscriptions:
            try:
                self.ws_private.order_stream(callback=self.handle_order)
                self._private_subscriptions.append("order")
                logger.info("Subscribed to order stream.")
            except Exception as e:
                logger.error(f"Error subscribing to order stream: {e}", exc_info=True)
        if "execution" in channels and "execution" not in self._private_subscriptions:
            try:
                self.ws_private.execution_stream(callback=self.handle_execution)
                self._private_subscriptions.append("execution")
                logger.info("Subscribed to execution stream.")
            except Exception as e:
                logger.error(
                    f"Error subscribing to execution stream: {e}", exc_info=True
                )
        if "wallet" in channels and "wallet" not in self._private_subscriptions:
            try:
                self.ws_private.wallet_stream(callback=self.handle_wallet)
                self._private_subscriptions.append("wallet")
                logger.info("Subscribed to wallet stream.")
            except Exception as e:
                logger.error(f"Error subscribing to wallet stream: {e}", exc_info=True)

    def start(self):
        """Starts the WebSocket connections."""
        logger.info("WebSocket Manager started.")

    def stop(self):
        """Stops and closes all WebSocket connections."""
        try:
            if self.ws_public:
                try:
                    self.ws_public.exit()
                    logger.info("Public WebSocket connection closed.")
                except Exception as e:
                    logger.warning(f"Error closing public WebSocket: {e}")
        finally:
            self.ws_public = None
        try:
            if self.ws_private:
                try:
                    self.ws_private.exit()
                    logger.info("Private WebSocket connection closed.")
                except Exception as e:
                    logger.warning(f"Error closing private WebSocket: {e}")
        finally:
            self.ws_private = None
        logger.info("WebSocket Manager stopped.")

    def is_public_connected(self) -> bool:
        """Checks if the public WebSocket is connected."""
        try:
            return self.ws_public is not None and bool(self.ws_public.is_connected())
        except Exception:
            return self.ws_public is not None

    def is_private_connected(self) -> bool:
        """Checks if the private WebSocket is connected."""
        try:
            return self.ws_private is not None and bool(self.ws_private.is_connected())
        except Exception:
            return self.ws_private is not None


# --- Trading Bot Core ---
class BybitTradingBot:
    """Core Bybit trading bot functionality, integrating HTTP API and WebSocket data."""

    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        self.session = HTTP(
            testnet=testnet, api_key=api_key, api_secret=api_secret, recv_window=10000
        )
        self.ws_manager = BybitWebSocketManager(api_key, api_secret, testnet)
        self.strategy: Callable[[dict, dict, HTTP, Any, list[str]], None] | None = (
            None  # Strategy now accepts bot_instance and symbols
        )
        self.symbol_info: dict[
            str, Any
        ] = {}  # Stores instrument details for position sizing and precision
        self.max_open_positions: int = int(
            os.getenv("BOT_MAX_OPEN_POSITIONS", "5")
        )  # Max number of open positions for risk management
        self.category: str = os.getenv(
            "BYBIT_CATEGORY", "linear"
        )  # Default trading category
        self.data_freshness_ms: int = int(os.getenv("BYBIT_MD_FRESH_MS", "5000"))

        logger.info(
            f"Bybit Trading Bot initialized. Testnet: {testnet}, Category: {self.category}"
        )

    async def _http_call(
        self,
        method: Callable,
        max_retries: int = 3,
        initial_delay: float = 0.5,
        **kwargs,
    ) -> dict | None:
        """Runs a blocking pybit HTTP call in a thread and retries on failure."""
        for attempt in range(1, max_retries + 1):
            try:
                resp = await asyncio.to_thread(method, **kwargs)
                if resp is None:
                    raise RuntimeError("Empty response from HTTP call")
                return resp
            except Exception as e:
                if attempt >= max_retries:
                    logger.error(
                        f"HTTP call {getattr(method, '__name__', str(method))} failed after {attempt} attempts: {e}",
                        exc_info=True,
                    )
                    return None
                backoff = initial_delay * (2 ** (attempt - 1)) + random.random() * 0.1
                logger.warning(
                    f"HTTP call {getattr(method, '__name__', str(method))} failed (attempt {attempt}/{max_retries}): {e}. Retrying in {backoff:.2f}s"
                )
                await asyncio.sleep(backoff)

    async def fetch_symbol_info(self, symbols: list[str]):
        """Fetches and stores instrument details for given symbols."""
        logger.info(f"Fetching instrument info for symbols: {symbols}")
        try:
            for symbol in symbols:
                response = await self._http_call(
                    self.session.get_instruments_info,
                    category=self.category,
                    symbol=symbol,
                )
                if response and response.get("retCode") == 0:
                    for item in response.get("result", {}).get("list", []):
                        if (
                            item.get("symbol") == symbol
                        ):  # Ensure it's the correct symbol
                            lot = item.get("lotSizeFilter", {}) or {}
                            pricef = item.get("priceFilter", {}) or {}
                            self.symbol_info[symbol] = {
                                "minOrderQty": to_decimal(lot.get("minOrderQty", "0")),
                                "qtyStep": to_decimal(lot.get("qtyStep", "1")),
                                "tickSize": to_decimal(pricef.get("tickSize", "0.01")),
                                "minPrice": to_decimal(pricef.get("minPrice", "0")),
                                "maxPrice": to_decimal(pricef.get("maxPrice", "0")),
                                "leverageFilter": item.get(
                                    "leverageFilter", {}
                                ),  # Store leverage info
                            }
                            logger.info(
                                f"Successfully fetched instrument info for {symbol}."
                            )
                            break
                else:
                    logger.error(
                        f"Failed to fetch instrument info for {symbol}: {response.get('retMsg') if response else 'No response'}"
                    )
        except Exception as e:
            logger.error(f"Error fetching instrument info: {e}", exc_info=True)

    def set_strategy(
        self, strategy_func: Callable[[dict, dict, HTTP, Any, list[str]], None]
    ):
        """Sets the trading strategy function.
        The strategy function should accept (market_data, account_info, http_client, bot_instance, symbols) as arguments.
        """
        self.strategy = strategy_func
        logger.info("Trading strategy set.")

    def _round_to_qty_step(self, symbol: str, quantity: Decimal) -> Decimal:
        """Rounds a quantity down to the nearest valid step for a given symbol."""
        if symbol not in self.symbol_info:
            logger.warning(
                f"Symbol info not available for {symbol}. Cannot round quantity."
            )
            return quantity
        qty_step = self.symbol_info[symbol]["qtyStep"]
        if qty_step <= 0:
            return quantity
        steps = (quantity / qty_step).to_integral_value(rounding=ROUND_DOWN)
        return steps * qty_step

    def _round_to_tick_size(self, symbol: str, price: Decimal) -> Decimal:
        """Rounds a price to the nearest valid tick size for a given symbol."""
        if symbol not in self.symbol_info:
            logger.warning(
                f"Symbol info not available for {symbol}. Cannot round price."
            )
            return price
        tick_size = self.symbol_info[symbol]["tickSize"]
        if tick_size <= 0:
            return price
        # Use quantize with tick size exponent; safe for decimals like 0.5, 0.01, etc.
        return (price / tick_size).to_integral_value(rounding=ROUND_DOWN) * tick_size

    async def get_market_data(self, symbol: str) -> dict | None:
        """Retrieve current market data for a symbol.
        Prioritizes WebSocket data if available and fresh, falls back to REST API.
        """
        # Check WebSocket data first
        ws_data = self.ws_manager.market_data.get(symbol)
        if ws_data and ws_data.get("orderbook") and ws_data.get("ticker"):
            ts = ws_data.get("timestamp") or ws_data.get("orderbook", {}).get("ts") or 0
            try:
                now_ms = int(time.time() * 1000)
                if ts and (now_ms - int(ts)) < self.data_freshness_ms:
                    return ws_data
            except Exception:
                # If timestamp parsing fails, still fall back to REST
                pass

        logger.warning(
            f"WebSocket data for {symbol} not fresh or complete. Falling back to REST API."
        )

        # Fallback to REST API (normalize shapes to match WS for strategy compatibility)
        try:
            orderbook_resp, ticker_resp = await asyncio.gather(
                self._http_call(
                    self.session.get_orderbook, category=self.category, symbol=symbol
                ),
                self._http_call(
                    self.session.get_tickers, category=self.category, symbol=symbol
                ),
            )

            if (
                orderbook_resp
                and orderbook_resp.get("retCode") == 0
                and ticker_resp
                and ticker_resp.get("retCode") == 0
            ):
                ob_list = (orderbook_resp.get("result", {}) or {}).get("list", []) or []
                ob = ob_list[0] if ob_list else {}
                normalized_ob = {
                    "s": ob.get("s") or symbol,
                    "b": ob.get("b", []),
                    "a": ob.get("a", []),
                    "ts": ob.get("ts") or int(time.time() * 1000),
                }

                tk_list = (ticker_resp.get("result", {}) or {}).get("list", []) or []
                tk = tk_list[0] if tk_list else {}
                normalized_tk = tk

                return {
                    "orderbook": normalized_ob,
                    "ticker": normalized_tk,
                    "last_trade": [],  # Placeholder if not fetched via REST
                }
            logger.warning(
                f"Failed to get market data for {symbol} via REST. Orderbook ret: {orderbook_resp.get('retMsg') if orderbook_resp else 'None'}, Ticker ret: {ticker_resp.get('retMsg') if ticker_resp else 'None'}"
            )
            return None
        except Exception as e:
            logger.error(
                f"Error fetching market data for {symbol} via REST: {e}", exc_info=True
            )
            return None

    async def get_account_info(self, account_type: str = "UNIFIED") -> dict | None:
        """Retrieve account balance information.
        Prioritizes WebSocket data if available, falls back to REST API.
        """
        try:
            balance = await self._http_call(
                self.session.get_wallet_balance, accountType=account_type
            )
            if balance and balance.get("retCode") == 0:
                return balance.get("result", {})
            logger.warning(
                f"Failed to get account balance. Response: {balance.get('retMsg') if balance else 'No response'}"
            )
            return None
        except Exception as e:
            logger.error(f"Error fetching account balance: {e}", exc_info=True)
            return None

    async def calculate_position_size(
        self, symbol: str, capital_percentage: float, price: Decimal, account_info: dict
    ) -> Decimal:
        """Calculates the position size based on a percentage of available capital.
        Returns the quantity as a Decimal, rounded to the symbol's qtyStep.
        """
        if symbol not in self.symbol_info:
            logger.warning(
                f"Symbol info not available for {symbol}. Cannot calculate position size."
            )
            return Decimal(0)

        try:
            available_balance_usd = Decimal(0)
            # UNIFIED account result example: result.list -> [ { accountType, coin: [ {coin:'USDT', availableToWithdraw:...}, ... ] } ]
            for acct in account_info.get("list", []):
                coins = acct.get("coin", [])
                if isinstance(coins, list):
                    for c in coins:
                        if c.get("coin") in ("USDT", "USD"):
                            available_balance_usd = to_decimal(
                                c.get("availableToWithdraw", "0")
                            )
                            break
                elif isinstance(coins, dict) and coins.get("coin") in ("USDT", "USD"):
                    available_balance_usd = to_decimal(
                        coins.get("availableToWithdraw", "0")
                    )
                if available_balance_usd > 0:
                    break

            if available_balance_usd <= 0:
                logger.warning("No available balance to calculate position size.")
                return Decimal(0)

            if price <= 0:
                logger.warning("Price must be positive to calculate position size.")
                return Decimal(0)

            target_capital = available_balance_usd * Decimal(str(capital_percentage))
            raw_qty = target_capital / price

            # Round quantity to the nearest qtyStep and ensure it meets minOrderQty
            rounded_qty = self._round_to_qty_step(symbol, raw_qty)
            min_order_qty = self.symbol_info[symbol]["minOrderQty"]

            if rounded_qty < min_order_qty:
                logger.warning(
                    f"Calculated quantity {rounded_qty} is less than min order qty {min_order_qty} for {symbol}. Returning 0."
                )
                return Decimal(0)

            logger.info(
                f"Calculated position size for {symbol}: {rounded_qty} (Target Capital: {target_capital.quantize(Decimal('0.01'))} USDT, Price: {price})"
            )
            return rounded_qty

        except Exception as e:
            logger.error(
                f"Error calculating position size for {symbol}: {e}", exc_info=True
            )
            return Decimal(0)

    async def get_historical_klines(
        self, symbol: str, interval: str, limit: int = 200
    ) -> dict | None:
        """Retrieve historical candlestick data (Klines)."""
        try:
            klines = await self._http_call(
                self.session.get_kline,
                category=self.category,
                symbol=symbol,
                interval=interval,
                limit=limit,
            )
            if klines and klines.get("retCode") == 0:
                return klines
            logger.warning(
                f"Failed to get historical klines for {symbol} ({interval}). Response: {klines.get('retMsg') if klines else 'No response'}"
            )
            return None
        except Exception as e:
            logger.error(
                f"Error fetching historical klines for {symbol} ({interval}): {e}",
                exc_info=True,
            )
            return None

    def get_open_positions_count(self) -> int:
        """Returns the current number of open positions across all symbols."""
        count = 0
        for symbol, position_data in list(self.ws_manager.positions.items()):
            # A position is considered open if size is not zero
            if to_decimal(position_data.get("size", "0")) != Decimal("0"):
                count += 1
        return count

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        qty: Decimal,
        price: Decimal | None = None,
        stop_loss_price: Decimal | None = None,
        take_profit_price: Decimal | None = None,
        trigger_by: str = "LastPrice",
        time_in_force: str = "GTC",
        **kwargs,
    ) -> dict | None:
        """Place an order on Bybit.

        Args:
            symbol (str): Trading pair (e.g., "BTCUSDT").
            side (str): "Buy" or "Sell".
            order_type (str): "Limit", "Market", "PostOnly", etc.
            qty (Decimal): Quantity to trade.
            price (Optional[Decimal]): Price for Limit orders.
            stop_loss_price (Optional[Decimal]): Stop Loss price.
            take_profit_price (Optional[Decimal]): Take Profit price.
            trigger_by (str): Trigger type for stop/take profit orders ("LastPrice", "IndexPrice", "MarkPrice").
            time_in_force (str): "GTC", "IOC", "FOK".
            **kwargs: Additional parameters for the order (e.g., "orderLinkId").

        Returns:
            Optional[Dict]: The order response from Bybit if successful, else None.

        """
        if qty <= 0:
            logger.warning(
                f"Invalid quantity ({qty}) for order on {symbol}. Must be positive."
            )
            return None
        if order_type == "Limit" and (price is None or price <= 0):
            logger.warning(f"Price must be positive for Limit order on {symbol}.")
            return None

        # Risk management: Check max open positions for new entries
        current_position = to_decimal(
            self.ws_manager.positions.get(symbol, {}).get("size", "0")
        )
        if (
            current_position == Decimal("0")
            and self.get_open_positions_count() >= self.max_open_positions
        ):
            logger.warning(
                f"Max open positions ({self.max_open_positions}) reached. Not placing new entry order for {symbol}."
            )
            return None

        # Round quantity and price to symbol's precision
        qty = self._round_to_qty_step(symbol, to_decimal(qty))
        if price is not None:
            price = self._round_to_tick_size(symbol, to_decimal(price))
        if stop_loss_price:
            stop_loss_price = self._round_to_tick_size(
                symbol, to_decimal(stop_loss_price)
            )
        if take_profit_price:
            take_profit_price = self._round_to_tick_size(
                symbol, to_decimal(take_profit_price)
            )

        # Enforce min/max price if available
        si = self.symbol_info.get(symbol, {})
        min_p, max_p = (
            si.get("minPrice", Decimal("0")),
            si.get("maxPrice", Decimal("0")),
        )
        if price is not None and (min_p is not None and max_p is not None):
            try:
                if max_p > 0:
                    price = min(price, max_p)
                if min_p > 0:
                    price = max(price, min_p)
                # Re-round to tick after clamping
                price = self._round_to_tick_size(symbol, price)
            except Exception:
                pass

        try:
            params = {
                "category": self.category,
                "symbol": symbol,
                "side": side,
                "orderType": order_type,
                "qty": str(qty),  # Convert Decimal to string for API
                "timeInForce": time_in_force,
                **kwargs,
            }
            if price is not None:
                params["price"] = str(price)  # Convert Decimal to string for API
            if stop_loss_price is not None:
                params["stopLoss"] = str(
                    stop_loss_price
                )  # Convert Decimal to string for API
                params["triggerBy"] = trigger_by  # Apply triggerBy if SL is set
            if take_profit_price is not None:
                params["takeProfit"] = str(
                    take_profit_price
                )  # Convert Decimal to string for API

            order_response = await self._http_call(self.session.place_order, **params)

            if order_response and order_response.get("retCode") == 0:
                result = order_response.get("result", {})
                logger.info(
                    f"Order placed successfully for {symbol} ({side} {order_type}) Qty={qty}, Price={params.get('price')} -> {result}"
                )
                return result
            logger.error(
                f"Failed to place order for {symbol}: {order_response.get('retMsg') if order_response else 'No response'}"
            )
            return None
        except Exception as e:
            logger.error(f"Error placing order for {symbol}: {e}", exc_info=True)
            return None

    async def cancel_order(
        self, symbol: str, order_id: str | None = None, order_link_id: str | None = None
    ) -> bool:
        """Cancel an order by orderId or orderLinkId."""
        try:
            params = {"category": self.category, "symbol": symbol}
            if order_id:
                params["orderId"] = order_id
            elif order_link_id:
                params["orderLinkId"] = order_link_id
            else:
                logger.warning(
                    "Either order_id or order_link_id must be provided to cancel an order."
                )
                return False

            cancel_response = await self._http_call(self.session.cancel_order, **params)
            if cancel_response and cancel_response.get("retCode") == 0:
                logger.info(
                    f"Order cancelled successfully for {symbol}: {cancel_response.get('result')}"
                )
                return True
            logger.error(
                f"Failed to cancel order for {symbol}: {cancel_response.get('retMsg') if cancel_response else 'No response'}"
            )
            return False
        except Exception as e:
            logger.error(f"Error cancelling order for {symbol}: {e}", exc_info=True)
            return False

    async def log_current_pnl(self):
        """Logs the current unrealized PnL from all open positions."""
        total_unrealized_pnl = Decimal("0")
        has_pnl = False
        for symbol, position_data in list(self.ws_manager.positions.items()):
            unrealized_pnl = to_decimal(position_data.get("unrealisedPnl", "0"))
            if unrealized_pnl != Decimal("0"):
                total_unrealized_pnl += unrealized_pnl
                logger.info(
                    f"Unrealized PnL for {symbol} ({position_data.get('side')} {position_data.get('size')}): {unrealized_pnl}"
                )
                has_pnl = True
        if has_pnl:
            logger.info(f"Total Unrealized PnL: {total_unrealized_pnl}")

    async def _check_ws_connection(self, symbols: list[str]):
        """Periodically checks WebSocket connection status and attempts re-subscription."""
        if not self.ws_manager.is_public_connected():
            logger.warning(
                "Public WebSocket disconnected. Attempting re-subscription..."
            )
            await self.ws_manager.subscribe_public_channels(symbols)
        if not self.ws_manager.is_private_connected():
            logger.warning(
                "Private WebSocket disconnected. Attempting re-subscription..."
            )
            await self.ws_manager.subscribe_private_channels()

    async def run(self, symbols: list[str], interval: int = 5):
        """Main bot execution loop."""
        if not self.strategy:
            logger.error(
                "No trading strategy set. Please call set_strategy() before running the bot."
            )
            return

        self.ws_manager.start()

        # Subscribe to WebSocket streams
        await self.ws_manager.subscribe_public_channels(symbols)
        await self.ws_manager.subscribe_private_channels()

        # Fetch symbol information for position sizing and precision
        await self.fetch_symbol_info(symbols)

        logger.info("Bot starting main loop...")
        try:
            while True:
                await self._check_ws_connection(
                    symbols
                )  # Ensure WS connections are alive

                # Fetch latest market data and account info
                current_market_data: dict[str, Any] = {}
                for symbol in symbols:
                    ws_md = self.ws_manager.market_data.get(symbol)
                    if ws_md and ws_md.get("orderbook") and ws_md.get("ticker"):
                        ts = (
                            ws_md.get("timestamp")
                            or ws_md.get("orderbook", {}).get("ts")
                            or 0
                        )
                        try:
                            now_ms = int(time.time() * 1000)
                            if ts and (now_ms - int(ts)) < self.data_freshness_ms:
                                current_market_data[symbol] = ws_md
                                continue
                        except Exception:
                            pass
                    rest_md = await self.get_market_data(symbol)
                    if rest_md:
                        current_market_data[symbol] = rest_md
                    else:
                        logger.warning(
                            f"Could not get market data for {symbol} from WS or REST."
                        )

                account_info = await self.get_account_info()

                if not current_market_data or not account_info:
                    logger.warning(
                        "Skipping strategy execution due to missing market or account data. Retrying in next interval."
                    )
                    await asyncio.sleep(interval)
                    continue

                # Execute the plugged-in strategy
                await self.strategy(
                    current_market_data, account_info, self.session, self, symbols
                )

                # Log current PnL
                await self.log_current_pnl()

                await asyncio.sleep(interval)

        except KeyboardInterrupt:
            logger.info("Bot stopped by user (KeyboardInterrupt).")
        except Exception as e:
            logger.critical(
                f"An unhandled error occurred in main bot loop: {e}", exc_info=True
            )
        finally:
            self.ws_manager.stop()
            logger.info("Bot gracefully shut down.")


# --- Main Execution ---
async def main():
    # Ensure API_KEY and API_SECRET are set
    if not API_KEY or not API_SECRET:
        logger.error(
            "BYBIT_API_KEY and BYBIT_API_SECRET environment variables must be set."
        )
        logger.error(
            "Please set them: export BYBIT_API_KEY='your_key' && export BYBIT_API_SECRET='your_secret'"
        )
        return

    bot = BybitTradingBot(api_key=API_KEY, api_secret=API_SECRET, testnet=USE_TESTNET)

    # Define symbols to trade
    # IMPORTANT: Ensure these symbols are available on Bybit for the 'linear' category
    symbols_to_trade = ["BTCUSDT", "ETHUSDT"]  # Example symbols

    # Plug in your strategy here
    # You need to create a market_making_strategy.py file (see Step 2)
    try:
        from market_making_strategy import market_making_strategy

        bot.set_strategy(market_making_strategy)
    except ImportError:
        logger.error(
            "Could not import 'market_making_strategy'. Please ensure 'market_making_strategy.py' is in the same directory."
        )
        logger.error("The bot will run but no strategy will be executed.")
        return

    # Run the bot
    await bot.run(symbols=symbols_to_trade, interval=5)  # Check every 5 seconds


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot process terminated by user.")
    except Exception as e:
        logger.critical(
            f"An unhandled error occurred during bot startup or execution: {e}",
            exc_info=True,
        )
