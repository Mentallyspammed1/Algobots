import asyncio
import logging
import os
from collections.abc import Callable
from decimal import Decimal, getcontext
from typing import Any

from pybit.unified_trading import HTTP, WebSocket

# Set decimal precision for financial calculations
getcontext().prec = 10
from decimal import getcontext

# Set decimal precision for financial calculations
getcontext().prec = 10
from decimal import getcontext

# Set decimal precision for financial calculations
getcontext().prec = 10
from decimal import getcontext

# Set decimal precision for financial calculations
getcontext().prec = 10

# --- Configuration ---
# Load API credentials from environment variables
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
USE_TESTNET = os.getenv("BYBIT_USE_TESTNET", "false").lower() == "true"

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- WebSocket Manager (adapted from pybithelp.md) ---
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
            self.ws_public = WebSocket(
                testnet=self.testnet,
                channel_type="linear"
            )
            logger.info("Public WebSocket initialized.")

    def _init_private_ws(self):
        if not self.ws_private:
            self.ws_private = WebSocket(
                testnet=self.testnet,
                channel_type="private",
                api_key=self.api_key,
                api_secret=self.api_secret,
                recv_window=10000
            )
            logger.info("Private WebSocket initialized.")

    def handle_orderbook(self, message: dict):
        """Process orderbook updates"""
        try:
            data = message.get("data", {})
            symbol = data.get("s")
            if symbol:
                self.market_data[symbol] = self.market_data.get(symbol, {})
                self.market_data[symbol]["orderbook"] = data
                self.market_data[symbol]["timestamp"] = message.get("ts")
                # logger.debug(f"Orderbook for {symbol}: Bids: {data.get('b', [])[:1]}, Asks: {data.get('a', [])[:1]}")
        except Exception as e:
            logger.error(f"Error handling orderbook: {e}")

    def handle_trades(self, message: dict):
        """Process trade updates"""
        try:
            data = message.get("data", [])
            for trade in data:
                symbol = trade.get("s")
                if symbol:
                    self.market_data[symbol] = self.market_data.get(symbol, {})
                    self.market_data[symbol]["last_trade"] = trade
                    # logger.debug(f"Trade for {symbol}: Price: {trade.get('p')}, Size: {trade.get('v')}")
        except Exception as e:
            logger.error(f"Error handling trades: {e}")

    def handle_ticker(self, message: dict):
        """Process ticker updates"""
        try:
            data = message.get("data", {})
            symbol = data.get("s")
            if symbol:
                self.market_data[symbol] = self.market_data.get(symbol, {})
                self.market_data[symbol]["ticker"] = data
                logger.debug(f"Raw Ticker Data for {symbol}: {data}") # Added for debugging
        except Exception as e:
            logger.error(f"Error handling ticker: {e}")

    def handle_position(self, message: dict):
        """Process position updates"""
        try:
            data = message.get("data", [])
            for position in data:
                symbol = position.get("symbol")
                if symbol:
                    self.positions[symbol] = position
                    # logger.debug(f"Position for {symbol}: Side: {position.get('side')}, Size: {position.get('size')}")
        except Exception as e:
            logger.error(f"Error handling position: {e}")

    def handle_order(self, message: dict):
        """Process order updates"""
        try:
            data = message.get("data", [])
            for order in data:
                order_id = order.get("orderId")
                if order_id:
                    self.orders[order_id] = order
                    # logger.debug(f"Order update for {order_id}: Status: {order.get('orderStatus')}")
        except Exception as e:
            logger.error(f"Error handling order: {e}")

    def handle_execution(self, message: dict):
        """Process execution/fill updates"""
        try:
            data = message.get("data", [])
            for execution in data:
                order_id = execution.get("orderId")
                if order_id:
                    # This is where you'd typically process fills, update PnL, etc.
                    logger.info(f"Execution for {order_id}: Price: {execution.get('execPrice')}, Qty: {execution.get('execQty')}")
        except Exception as e:
            logger.error(f"Error handling execution: {e}")

    def handle_wallet(self, message: dict):
        """Process wallet updates"""
        try:
            data = message.get("data", [])
            for wallet_data in data:
                coin = wallet_data.get("coin")
                if coin:
                    logger.info(f"Wallet update for {coin}: Available: {wallet_data.get('availableToWithdraw')}")
        except Exception as e:
            logger.error(f"Error handling wallet: {e}")

    async def subscribe_public_channels(self, symbols: list[str], channels: list[str] = ["orderbook", "publicTrade", "tickers"]):
        """Subscribe to public market data channels."""
        self._init_public_ws()
        if not self.ws_public:
            logger.error("Public WebSocket not initialized for subscription.")
            return

        # Add a small delay to allow WebSocket to fully establish before subscribing
        await asyncio.sleep(1) # Add a small blocking delay to allow WebSocket to fully establish

        for symbol in symbols:
            if "orderbook" in channels:
                try:
                    self.ws_public.orderbook_stream(
                        depth=1, # Changed depth to 1 for debugging
                        symbol=symbol,
                        callback=self.handle_orderbook
                    )
                    logger.info(f"Subscribed to orderbook.1.{symbol}")
                except Exception as e:
                    logger.error(f"Error subscribing to orderbook for {symbol}: {e}")
            if "publicTrade" in channels:
                try:
                    self.ws_public.trade_stream(
                        symbol=symbol,
                        callback=self.handle_trades
                    )
                    logger.info(f"Subscribed to publicTrade.{symbol}")
                except Exception as e:
                    logger.error(f"Error subscribing to publicTrade for {symbol}: {e}")
            if "tickers" in channels:
                try:
                    self.ws_public.ticker_stream(
                        symbol=symbol,
                        callback=self.handle_ticker
                    )
                    logger.info(f"Subscribed to tickers.{symbol}")
                except Exception as e:
                    logger.error(f"Error subscribing to tickers for {symbol}: {e}")

    async def subscribe_private_channels(self, channels: list[str] = ["position", "order", "execution", "wallet"]):
        """Subscribe to private account channels."""
        self._init_private_ws()
        if not self.ws_private:
            logger.error("Private WebSocket not initialized for subscription.")
            return

        # Add a small delay to allow WebSocket to fully establish before subscribing
        await asyncio.sleep(1) # Add a small blocking delay to allow WebSocket to fully establish

        if "position" in channels:
            self.ws_private.position_stream(callback=self.handle_position)
            logger.info("Subscribed to position stream.")
        if "order" in channels:
            self.ws_private.order_stream(callback=self.handle_order)
            logger.info("Subscribed to order stream.")
        if "execution" in channels:
            self.ws_private.execution_stream(callback=self.handle_execution)
            logger.info("Subscribed to execution stream.")
        if "wallet" in channels:
            self.ws_private.wallet_stream(callback=self.handle_wallet)
            logger.info("Subscribed to wallet stream.")

# --- Trading Bot Core ---
class BybitTradingBot:
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        self.session = HTTP(
            testnet=testnet,
            api_key=api_key,
            api_secret=api_secret,
            recv_window=10000
        )
        self.ws_manager = BybitWebSocketManager(api_key, api_secret, testnet)
        self.strategy: Callable[[dict, dict, HTTP, Any], None] | None = None # Strategy now accepts bot_instance
        self.symbol_info: dict[str, Any] = {} # Stores instrument details for position sizing
        self.max_open_positions: int = 5 # Max number of open positions for risk management

        logger.info(f"Bybit Trading Bot initialized. Testnet: {testnet}")

    async def fetch_symbol_info(self, symbols: list[str], category: str = "linear"):
        """Fetches and stores instrument details for given symbols."""
        logger.info(f"Fetching instrument info for symbols: {symbols}")
        try:
            for symbol in symbols:
                response = self.session.get_instruments_info(category=category, symbol=symbol)
                if response and response['retCode'] == 0:
                    for item in response.get('result', {}).get('list', []):
                        if item.get('symbol') == symbol: # Ensure it's the correct symbol
                            self.symbol_info[symbol] = {
                                "minOrderQty": Decimal(item['lotSizeFilter']['minOrderQty']),
                                "qtyStep": Decimal(item['lotSizeFilter']['qtyStep']),
                                "tickSize": Decimal(item['priceFilter']['tickSize']),
                                "minPrice": Decimal(item['priceFilter']['minPrice']),
                                "maxPrice": Decimal(item['priceFilter']['maxPrice']),
                            }
                            logger.info(f"Successfully fetched instrument info for {symbol}.")
                            break # Move to next symbol after finding it
                else:
                    logger.error(f"Failed to fetch instrument info for {symbol}: {response.get('retMsg')}")
        except Exception as e:
            logger.error(f"Error fetching instrument info: {e}")

    async def fetch_symbol_info(self, symbols: list[str], category: str = "linear"):
        """Fetches and stores instrument details for given symbols."""
        logger.info(f"Fetching instrument info for symbols: {symbols}")
        try:
            for symbol in symbols:
                response = self.session.get_instruments_info(category=category, symbol=symbol)
                if response and response['retCode'] == 0:
                    for item in response.get('result', {}).get('list', []):
                        if item.get('symbol') == symbol: # Ensure it's the correct symbol
                            self.symbol_info[symbol] = {
                                "minOrderQty": Decimal(item['lotSizeFilter']['minOrderQty']),
                                "qtyStep": Decimal(item['lotSizeFilter']['qtyStep']),
                                "tickSize": Decimal(item['priceFilter']['tickSize']),
                                "minPrice": Decimal(item['priceFilter']['minPrice']),
                                "maxPrice": Decimal(item['priceFilter']['maxPrice']),
                            }
                            logger.info(f"Successfully fetched instrument info for {symbol}.")
                            break # Move to next symbol after finding it
                else:
                    logger.error(f"Failed to fetch instrument info for {symbol}: {response.get('retMsg')}")
        except Exception as e:
            logger.error(f"Error fetching instrument info: {e}")

    async def fetch_symbol_info(self, symbols: list[str], category: str = "linear"):
        """Fetches and stores instrument details for given symbols."""
        logger.info(f"Fetching instrument info for symbols: {symbols}")
        try:
            for symbol in symbols:
                response = self.session.get_instruments_info(category=category, symbol=symbol)
                if response and response['retCode'] == 0:
                    for item in response.get('result', {}).get('list', []):
                        if item.get('symbol') == symbol: # Ensure it's the correct symbol
                            self.symbol_info[symbol] = {
                                "minOrderQty": Decimal(item['lotSizeFilter']['minOrderQty']),
                                "qtyStep": Decimal(item['lotSizeFilter']['qtyStep']),
                                "tickSize": Decimal(item['priceFilter']['tickSize']),
                                "minPrice": Decimal(item['priceFilter']['minPrice']),
                                "maxPrice": Decimal(item['priceFilter']['maxPrice']),
                            }
                            logger.info(f"Successfully fetched instrument info for {symbol}.")
                            break # Move to next symbol after finding it
                else:
                    logger.error(f"Failed to fetch instrument info for {symbol}: {response.get('retMsg')}")
        except Exception as e:
            logger.error(f"Error fetching instrument info: {e}")

    def set_strategy(self, strategy_func: Callable[[dict, dict, HTTP, Any], None]):
        """Sets the trading strategy function.
        The strategy function should accept (market_data, account_info, http_client, bot_instance) as arguments.
        """
        self.strategy = strategy_func
        logger.info("Trading strategy set.")

    async def get_market_data(self, symbol: str, category: str = "linear") -> dict | None:
        """Retrieve current market data for a symbol using REST API."""
        try:
            orderbook = self.session.get_orderbook(category=category, symbol=symbol)
            ticker = self.session.get_tickers(category=category, symbol=symbol)
            # trades = self.session.get_public_trading_records(category=category, symbol=symbol, limit=1) # Get latest trade - Temporarily commented out due to AttributeError

            if orderbook and ticker and orderbook['retCode'] == 0 and ticker['retCode'] == 0: # Removed 'trades' from condition
                trades = {"result": {"list": []}} # Provide an empty trades object to avoid errors later
                return {
                    "orderbook": orderbook.get('result', {}).get('list', []),
                    "ticker": ticker.get('result', {}).get('list', []),
                    "last_trade": trades.get('result', {}).get('list', [])
                }
            logger.warning(f"Failed to get market data for {symbol}. Orderbook: {orderbook}, Ticker: {ticker}, Trades: {trades}")
            return None
        except Exception as e:
            logger.error(f"Error fetching market data for {symbol}: {e}")
            return None

    async def get_account_info(self, account_type: str = "UNIFIED") -> dict | None:
        """Retrieve account balance information."""
        try:
            balance = self.session.get_wallet_balance(accountType=account_type)
            if balance and balance['retCode'] == 0:
                return balance.get('result', {}).get('list', [])
            logger.warning(f"Failed to get account balance. Response: {balance}")
            return None
        except Exception as e:
            logger.error(f"Error fetching account balance: {e}")
            return None

    async def calculate_position_size(self, symbol: str, capital_percentage: float, price: float, account_info: dict) -> Decimal:
        """Calculates the position size based on a percentage of available capital.
        Returns the quantity as a Decimal, rounded to the symbol's qtyStep.
        """
        if symbol not in self.symbol_info:
            logger.warning(f"Symbol info not available for {symbol}. Cannot calculate position size.")
            return Decimal(0)

        try:
            # Get available balance (assuming USDT for simplicity, adjust as needed)
            available_balance_usd = Decimal(0)
            for wallet in account_info.get('list', []):
                if wallet.get('coin') == 'USDT': # Adjust coin as per your base currency
                    available_balance_usd = Decimal(wallet.get('availableToWithdraw', '0'))
                    break

            if available_balance_usd <= 0:
                logger.warning("No available balance to calculate position size.")
                return Decimal(0)

            # Convert price to Decimal
            price_dec = Decimal(str(price))
            if price_dec <= 0:
                logger.warning("Price must be positive to calculate position size.")
                return Decimal(0)

            # Calculate target capital for this trade
            target_capital = available_balance_usd * Decimal(str(capital_percentage))

            # Calculate raw quantity
            raw_qty = target_capital / price_dec

            # Get symbol trading rules
            min_order_qty = self.symbol_info[symbol]["minOrderQty"]
            qty_step = self.symbol_info[symbol]["qtyStep"]

            # Round quantity to the nearest qtyStep
            # This is a common way to round to a step: (value / step).quantize(Decimal(1)).normalize() * step
            # Or, for rounding down to the nearest step:
            rounded_qty = (raw_qty // qty_step) * qty_step

            # Ensure quantity meets minimum order requirements
            if rounded_qty < min_order_qty:
                logger.warning(f"Calculated quantity {rounded_qty} is less than min order qty {min_order_qty} for {symbol}.")
                return Decimal(0)

            logger.info(f"Calculated position size for {symbol}: {rounded_qty} (Capital: {target_capital}, Price: {price_dec})")
            return rounded_qty

        except Exception as e:
            logger.error(f"Error calculating position size for {symbol}: {e}")
            return Decimal(0)

    async def get_historical_klines(self, symbol: str, interval: str, limit: int = 200, category: str = "linear") -> dict | None:
        """Retrieve historical candlestick data (Klines)."""
        try:
            klines = self.session.get_kline(
                category=category,
                symbol=symbol,
                interval=interval,
                limit=limit
            )
            if klines and klines['retCode'] == 0:
                return klines
            logger.warning(f"Failed to get historical klines for {symbol} ({interval}). Response: {klines}")
            return None
        except Exception as e:
            logger.error(f"Error fetching historical klines for {symbol} ({interval}): {e}")
            return None

    def get_open_positions_count(self) -> int:
        """Returns the current number of open positions.
        Assumes self.positions is kept up-to-date by the WebSocket manager.
        """
        count = 0
        for symbol, position_data in self.positions.items():
            # A position is considered open if size is not zero
            if Decimal(position_data.get('size', '0')) != Decimal('0'):
                count += 1
        return count

    async def place_order(self, category: str, symbol: str, side: str, order_type: str, qty: float, price: float | None = None, stop_loss_price: float | None = None, take_profit_price: float | None = None, trigger_by: str = "LastPrice", **kwargs) -> dict | None:
        """Place an order."""
        try:
            # Risk management: Check max open positions
            if self.get_open_positions_count() >= self.max_open_positions:
                logger.warning(f"Max open positions ({self.max_open_positions}) reached. Not placing new order for {symbol}.")
                return None

            params = {
                "category": category,
                "symbol": symbol,
                "side": side,
                "orderType": order_type,
                "qty": str(qty),
                **kwargs
            }
            if price is not None:
                params["price"] = str(price)
            if stop_loss_price is not None:
                params["stopLoss"] = str(stop_loss_price)
                params["triggerBy"] = trigger_by # Apply triggerBy if SL is set
            if take_profit_price is not None:
                params["takeProfit"] = str(take_profit_price)

            order_response = await self.session.place_order(**params)
            if order_response and order_response['retCode'] == 0:
                logger.info(f"Order placed successfully: {order_response.get('result')}")
                return order_response.get('result')
            logger.error(f"Failed to place order: {order_response.get('retMsg')}")
            return None
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None

    async def cancel_order(self, category: str, symbol: str, order_id: str | None = None, order_link_id: str | None = None) -> bool:
        """Cancel an order by orderId or orderLinkId."""
        try:
            params = {"category": category, "symbol": symbol}
            if order_id:
                params["orderId"] = order_id
            elif order_link_id:
                params["orderLinkId"] = order_link_id
            else:
                logger.warning("Either order_id or order_link_id must be provided to cancel an order.")
                return False

            cancel_response = self.session.cancel_order(**params)
            if cancel_response and cancel_response['retCode'] == 0:
                logger.info(f"Order cancelled successfully: {cancel_response.get('result')}")
                return True
            logger.error(f"Failed to cancel order: {cancel_response.get('retMsg')}")
            return False
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return False

    async def log_current_pnl(self):
        """Logs the current unrealized PnL from all open positions."""
        total_unrealized_pnl = Decimal('0')
        for symbol, position_data in self.ws_manager.positions.items():
            unrealized_pnl = Decimal(position_data.get('unrealisedPnl', '0'))
            total_unrealized_pnl += unrealized_pnl
            if unrealized_pnl != Decimal('0'):
                logger.info(f"Unrealized PnL for {symbol}: {unrealized_pnl}")
        if total_unrealized_pnl != Decimal('0'):
            logger.info(f"Total Unrealized PnL: {total_unrealized_pnl}")

    async def run(self, symbols: list[str], interval: int = 5):
        """Main bot execution loop."""
        if not self.strategy:
            logger.error("No trading strategy set. Please call set_strategy() before running the bot.")
            return

        # Subscribe to WebSocket streams
        await self.ws_manager.subscribe_public_channels(symbols)
        await self.ws_manager.subscribe_private_channels()

        # Fetch symbol information for position sizing
        await self.fetch_symbol_info(symbols)

        logger.info("Bot starting main loop...")
        while True:
            try:
                # Fetch latest market data and account info
                current_market_data: dict[str, Any] = {}
                for symbol in symbols:
                    data = await self.get_market_data(symbol)
                    if data:
                        current_market_data[symbol] = data
                        # Also update WS manager's market data for consistency if needed
                        # self.ws_manager.market_data[symbol] = data # This would overwrite WS data, be careful

                account_info = await self.get_account_info()

                if not current_market_data or not account_info:
                    logger.warning("Skipping strategy execution due to missing market or account data.")
                    await asyncio.sleep(interval)
                    continue

                # Execute the plugged-in strategy
                # The strategy function will receive live data, account info, the HTTP client, and the bot instance
                await self.strategy(current_market_data, account_info, self.session, self, symbols)

                # Log current PnL
                await self.log_current_pnl()

            except KeyboardInterrupt:
                logger.info("Bot stopped by user (KeyboardInterrupt).")
                break
            except Exception as e:
                logger.error(f"Error in main bot loop: {e}", exc_info=True)

            await asyncio.sleep(interval)

# --- Main Execution ---

async def main():
    # Ensure API_KEY and API_SECRET are set
    if not API_KEY or not API_SECRET:
        logger.error("BYBIT_API_KEY and BYBIT_API_SECRET environment variables must be set.")
        return

    bot = BybitTradingBot(api_key=API_KEY, api_secret=API_SECRET, testnet=USE_TESTNET)

    from strategy import market_making_strategy  # Import the new strategy
    # Plug in your strategy here
    bot.set_strategy(market_making_strategy) # Set the Market Making strategy

    # Example of how to use the new functionalities within your strategy:
    # Inside your strategy function (e.g., ehlers_ma_cross_strategy):
    # async def ehlers_ma_cross_strategy(market_data, account_info, http_client, bot_instance):
    #     symbol = "BTCUSDT" # Or iterate through symbols
    #     # Ensure you get the price as a Decimal for calculations
    #     current_price = Decimal(market_data[symbol]["ticker"][0]["lastPrice"])
    #
    #     # Example: Calculate position size for 0.5% of capital
    #     position_qty = await bot_instance.calculate_position_size(
    #         symbol=symbol,
    #         capital_percentage=0.005, # 0.5% of capital
    #         price=current_price,
    #         account_info=account_info
    #     )
    #
    #     if position_qty > 0:
    #         # Example: Place a limit buy order with Stop Loss and Take Profit
    #         # Calculate limit price, ensuring it's rounded to the symbol's tickSize
    #         tick_size = bot_instance.symbol_info[symbol]["tickSize"]
    #         limit_price = (current_price * Decimal("0.99")).quantize(tick_size) # 1% below current price, rounded
    #         stop_loss = (current_price * Decimal("0.98")).quantize(tick_size) # 2% below current price, rounded
    #         take_profit = (current_price * Decimal("1.02")).quantize(tick_size) # 2% above current price, rounded
    #
    #         order_response = await bot_instance.place_order(
    #             category="linear", # or "spot", "inverse", etc.
    #             symbol=symbol,
    #             side="Buy",
    #             order_type="Limit", # Specify Limit order
    #             qty=float(position_qty), # Convert Decimal to float for place_order (will be converted to str internally)
    #             price=float(limit_price), # Convert Decimal to float for place_order (will be converted to str internally)
    #             stop_loss_price=float(stop_loss), # New: Stop Loss price
    #             take_profit_price=float(take_profit), # New: Take Profit price
    #             trigger_by="LastPrice", # New: Trigger type for stop orders
    #             timeInForce="GTC" # Good-Till-Canceled
    #         )
    #         if order_response:
    #             logger.info(f"Placed limit buy order for {position_qty} {symbol} at {limit_price} with SL {stop_loss} and TP {take_profit}")
    #         else:
    #             logger.error(f"Failed to place limit buy order for {symbol}")

    # Define symbols to trade
    symbols_to_trade = ["LINKUSDT", "TRUMPUSDT"]

    # Run the bot
    await bot.run(symbols=symbols_to_trade, interval=5) # Check every 5 seconds

if __name__ == "__main__":
    # For running asyncio applications
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped manually.")
    except Exception as e:
        logger.critical(f"An unhandled error occurred: {e}", exc_info=True)


