import os
import time
import logging
import json
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
from pybit.unified_trading import HTTP, WebSocket
from decimal import Decimal, getcontext
import asyncio

# Set decimal precision for financial calculations
getcontext().prec = 10
from decimal import Decimal, getcontext

# Set decimal precision for financial calculations
getcontext().prec = 10
from decimal import Decimal, getcontext

# Set decimal precision for financial calculations
getcontext().prec = 10
from decimal import Decimal, getcontext

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
        self.ws_public: Optional[WebSocket] = None
        self.ws_private: Optional[WebSocket] = None
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet

        self.market_data: Dict[str, Any] = {}
        self.positions: Dict[str, Any] = {}
        self.orders: Dict[str, Any] = {}

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
                api_secret=self.api_secret
            )
            logger.info("Private WebSocket initialized.")

    def handle_orderbook(self, message: Dict):
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

    def handle_trades(self, message: Dict):
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

    def handle_ticker(self, message: Dict):
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

    def handle_position(self, message: Dict):
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

    def handle_order(self, message: Dict):
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

    def handle_execution(self, message: Dict):
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

    def handle_wallet(self, message: Dict):
        """Process wallet updates"""
        try:
            data = message.get("data", [])
            for wallet_data in data:
                coin = wallet_data.get("coin")
                if coin:
                    logger.info(f"Wallet update for {coin}: Available: {wallet_data.get('availableToWithdraw')}")
        except Exception as e:
            logger.error(f"Error handling wallet: {e}")

    async def subscribe_public_channels(self, symbols: List[str], channels: List[str] = ["orderbook", "publicTrade", "tickers"]):
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

    async def subscribe_private_channels(self, channels: List[str] = ["position", "order", "execution", "wallet"]):
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
        self.strategy: Optional[Callable[[Dict, Dict, HTTP, Any], None]] = None # Strategy now accepts bot_instance
        self.symbol_info: Dict[str, Any] = {} # Stores instrument details for position sizing
        self.max_open_positions: int = 5 # Max number of open positions for risk management

        logger.info(f"Bybit Trading Bot initialized. Testnet: {testnet}")

    async def fetch_symbol_info(self, symbols: List[str], category: str = "linear"):
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

    async def fetch_symbol_info(self, symbols: List[str], category: str = "linear"):
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

    async def fetch_symbol_info(self, symbols: List[str], category: str = "linear"):
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

    def set_strategy(self, strategy_func: Callable[[Dict, Dict, HTTP, Any], None]):
        """
        Sets the trading strategy function.
        The strategy function should accept (market_data, account_info, http_client, bot_instance) as arguments.
        """
        self.strategy = strategy_func
        logger.info("Trading strategy set.")

    async def get_market_data(self, symbol: str, category: str = "linear") -> Optional[Dict]:
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
            else:
                logger.warning(f"Failed to get market data for {symbol}. Orderbook: {orderbook}, Ticker: {ticker}, Trades: {trades}")
                return None
        except Exception as e:
            logger.error(f"Error fetching market data for {symbol}: {e}")
            return None

    async def get_account_info(self, account_type: str = "UNIFIED") -> Optional[Dict]:
        """Retrieve account balance information."""
        try:
            balance = self.session.get_wallet_balance(accountType=account_type)
            if balance and balance['retCode'] == 0:
                return balance.get('result', {}).get('list', [])
            else:
                logger.warning(f"Failed to get account balance. Response: {balance}")
                return None
        except Exception as e:
            logger.error(f"Error fetching account balance: {e}")
            return None

    async def calculate_position_size(self, symbol: str, capital_percentage: float, price: float, account_info: Dict) -> Decimal:
        """
        Calculates the position size based on a percentage of available capital.
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

    async def get_historical_klines(self, symbol: str, interval: str, limit: int = 200, category: str = "linear") -> Optional[Dict]:
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
            else:
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

    async def place_order(self, category: str, symbol: str, side: str, order_type: str, qty: float, price: Optional[float] = None, stop_loss_price: Optional[float] = None, take_profit_price: Optional[float] = None, trigger_by: str = "LastPrice", **kwargs) -> Optional[Dict]:
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
            else:
                logger.error(f"Failed to place order: {order_response.get('retMsg')}")
                return None
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None

    async def cancel_order(self, category: str, symbol: str, order_id: Optional[str] = None, order_link_id: Optional[str] = None) -> bool:
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
            else:
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

    async def run(self, symbols: List[str], interval: int = 5):
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
                current_market_data: Dict[str, Any] = {}
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
import asyncio
from market_making_strategy import market_making_strategy # Import the new strategy

async def main():
    # Ensure API_KEY and API_SECRET are set
    if not API_KEY or not API_SECRET:
        logger.error("BYBIT_API_KEY and BYBIT_API_SECRET environment variables must be set.")
        return

    bot = BybitTradingBot(api_key=API_KEY, api_secret=API_SECRET, testnet=USE_TESTNET)
    
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


import logging
from typing import Dict, List, Any
import decimal
from pybit.unified_trading import HTTP

logger = logging.getLogger(__name__)

# --- Market Making Strategy ---
async def market_making_strategy(market_data: Dict, account_info: Dict, http_client: HTTP, bot_instance: Any, symbols_to_trade: List[str]):
    """
    A simple market-making strategy that places buy and sell orders around the mid-price.
    """
    logger.info("Executing Market Making Strategy...")

    for symbol in symbols_to_trade:
        logger.info(f"Applying market making strategy for {symbol}...")

        # --- 1. Get Order Book Data ---
        orderbook_data = bot_instance.ws_manager.market_data.get(symbol, {}).get("orderbook")
        if not orderbook_data:
            logger.warning(f"No orderbook data for {symbol}. Skipping.")
            continue

        bids = orderbook_data.get('b', [])
        asks = orderbook_data.get('a', [])

        if not bids or not asks:
            logger.warning(f"Empty bids or asks in orderbook for {symbol}. Skipping.")
            continue

        best_bid = decimal.Decimal(bids[0][0])
        best_ask = decimal.Decimal(asks[0][0])

        # --- 2. Calculate Mid-Price and Spread ---
        mid_price = (best_bid + best_ask) / 2

        # --- Dynamic Spread Calculation ---
        ticker_data = bot_instance.ws_manager.market_data.get(symbol, {}).get("ticker")
        if ticker_data and ticker_data.get("price24hPcnt") is not None:
            price_change_24h_percent = decimal.Decimal(ticker_data.get("price24hPcnt"))
            volatility_24h = abs(price_change_24h_percent)
            
            # Base spread (e.g., 0.05% of mid-price)
            base_spread_bps = decimal.Decimal("5") # 5 basis points = 0.05%
            
            # Volatility factor (how much spread increases per 1% volatility)
            volatility_factor_bps_per_percent = decimal.Decimal("10") # 10 basis points per 1% price change
            
            # Calculate dynamic spread in basis points
            dynamic_spread_bps = base_spread_bps + (volatility_factor_bps_per_percent * volatility_24h * 100) # Multiply by 100 to convert 0.01 to 1%
            
            # Convert basis points to percentage
            desired_spread_percentage = dynamic_spread_bps / decimal.Decimal("10000") # 10000 basis points in 100%
            
            desired_spread = mid_price * desired_spread_percentage
            
            logger.info(f"[{symbol}] Volatility (24h): {volatility_24h:.4f}%, Dynamic Spread: {desired_spread_percentage:.4f}%")
        else:
            # Fallback to fixed spread if volatility data is not available
            desired_spread_percentage = decimal.Decimal("0.001") # 0.1% fixed spread
            desired_spread = mid_price * desired_spread_percentage
            logger.info(f"[{symbol}] Volatility data not available. Using fixed spread: {desired_spread_percentage:.4f}%")

        # --- 3. Determine Buy and Sell Prices ---
        bot_bid_price = mid_price - (desired_spread / 2)
        bot_ask_price = mid_price + (desired_spread / 2)

        # Round prices to the symbol's tick size
        tick_size = bot_instance.symbol_info[symbol]["tickSize"]
        bot_bid_price = bot_bid_price.quantize(tick_size)
        bot_ask_price = bot_ask_price.quantize(tick_size)

        # --- 4. Get Symbol Info for Quantity ---
        min_order_qty = bot_instance.symbol_info[symbol]["minOrderQty"]
        qty_step = bot_instance.symbol_info[symbol]["qtyStep"]
        
        # Assume minimum order value is 5 USDT (common for Bybit)
        min_order_value_usdt = decimal.Decimal("5")

        # Dynamic Quantity based on Order Book Depth
        # Analyze the top N levels of the order book to determine liquidity
        depth_levels_to_consider = 5 # Consider top 5 bid/ask levels
        total_bid_qty = sum(decimal.Decimal(bid[1]) for bid in bids[:depth_levels_to_consider])
        total_ask_qty = sum(decimal.Decimal(ask[1]) for ask in asks[:depth_levels_to_consider])
        
        # Use the smaller of the two sides as a proxy for available liquidity
        available_liquidity_qty = min(total_bid_qty, total_ask_qty)
        
        # Define a maximum order quantity (e.g., 1% of available liquidity, or a fixed max)
        max_order_quantity_factor = decimal.Decimal("0.01") # 1% of available liquidity
        max_order_quantity_fixed = decimal.Decimal("10") # Fixed max quantity, e.g., 10 units
        
        dynamic_order_quantity = available_liquidity_qty * max_order_quantity_factor
        
        # Cap the dynamic quantity by a fixed maximum to prevent excessively large orders
        dynamic_order_quantity = min(dynamic_order_quantity, max_order_quantity_fixed)
        
        # Calculate minimum quantity based on minimum order value
        calculated_qty_from_value = min_order_value_usdt / mid_price

        # Ensure order quantity meets both minOrderQty and minOrderValue requirements
        # Take the maximum of minOrderQty, quantity derived from minOrderValue, and dynamic quantity
        # Then round up to the nearest qtyStep
        
        # First, ensure it's at least minOrderQty
        order_quantity = max(min_order_qty, calculated_qty_from_value, dynamic_order_quantity)
        
        # Then, round up to the nearest qty_step
        # Use ROUND_UP to ensure it meets the step requirement
        order_quantity = order_quantity.quantize(qty_step, rounding=decimal.ROUND_UP)
        
        # Ensure it's not zero if price is very high and min_order_value_usdt is small
        if order_quantity == decimal.Decimal("0"):
            order_quantity = min_order_qty # Fallback to minOrderQty if rounding results in 0

        logger.info(f"[{symbol}] Mid: {mid_price:.4f}, Bid: {bot_bid_price:.4f}, Ask: {bot_ask_price:.4f}, Calculated Qty: {order_quantity}")

        # --- 5. Order Management ---
        try:
            # Cancel all existing orders for the symbol to reset
            http_client.cancel_all_orders(category="linear", symbol=symbol) # Re-enabled
            logger.info(f"Cancelled all existing orders for {symbol}.")

            # Place new buy order
            logger.info(f"Type of http_client.place_order: {type(http_client.place_order)}")
            logger.info(f"Type of http_client.cancel_all_orders: {type(http_client.cancel_all_orders)}")
            http_client.place_order(
                category="linear",
                symbol=symbol,
                side="Buy",
                order_type="Limit",
                qty=str(order_quantity),
                price=str(bot_bid_price),
                time_in_force="GTC"
            )
            logger.info(f"Placed BUY order for {order_quantity} {symbol} at {bot_bid_price:.4f}")

            # Place new sell order
            http_client.place_order(
                category="linear",
                symbol=symbol,
                side="Sell",
                order_type="Limit",
                qty=str(order_quantity),
                price=str(bot_ask_price),
                time_in_force="GTC"
            )
            logger.info(f"Placed SELL order for {order_quantity} {symbol} at {bot_ask_price:.4f}")

        except Exception as e:
            logger.error(f"Error during order management for {symbol}: {e}")

    # --- Manage Profitable Positions ---
    await manage_profitable_positions(account_info, http_client, bot_instance, symbols_to_trade)

async def manage_profitable_positions(account_info: Dict, http_client: HTTP, bot_instance: Any, symbols_to_trade: List[str]):
    """
    Closes positions that are in profit.
    """
    profit_threshold_percentage = decimal.Decimal("0.001") # 0.1% profit threshold

    for symbol in symbols_to_trade:
        position_data = bot_instance.ws_manager.positions.get(symbol)
        if position_data:
            unrealised_pnl = decimal.Decimal(position_data.get("unrealisedPnl", "0"))
            position_size = decimal.Decimal(position_data.get("size", "0"))
            position_side = position_data.get("side")
            entry_price = decimal.Decimal(position_data.get("avgPrice", "0"))

            if position_size > 0 and entry_price > 0: # Only if there's an open position
                # Calculate current profit percentage
                current_price = decimal.Decimal(bot_instance.ws_manager.market_data.get(symbol, {}).get("ticker", {}).get("lastPrice", "0"))
                if current_price == 0:
                    logger.warning(f"Cannot calculate profit percentage for {symbol}: current price is 0.")
                    continue

                profit_percentage = decimal.Decimal("0")
                if position_side == "Buy": # Long position
                    profit_percentage = (current_price - entry_price) / entry_price
                elif position_side == "Sell": # Short position
                    profit_percentage = (entry_price - current_price) / entry_price

                if profit_percentage >= profit_threshold_percentage:
                    logger.info(f"[{symbol}] Position in profit ({profit_percentage:.4f}%). Closing position...")
                    
                    # Determine side to close position
                    close_side = "Sell" if position_side == "Buy" else "Buy"

                    try:
                        # Place a market order to close the position
                        await http_client.place_order(
                            category="linear",
                            symbol=symbol,
                            side=close_side,
                            order_type="Market",
                            qty=str(position_size),
                            reduce_only=True # Ensure this order only reduces position
                        )
                        logger.info(f"[{symbol}] Market order placed to close {position_size} {symbol} ({close_side}).")
                    except Exception as e:
                        logger.error(f"Error closing profitable position for {symbol}: {e}")
