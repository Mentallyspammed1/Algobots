# main.py

import asyncio
import logging
import os
import random
import smtplib
import sys
import time
import traceback
from collections.abc import Callable
from decimal import Decimal, getcontext
from email.mime.text import MIMEText
from typing import Any

import yaml
from pybit.unified_trading import HTTP, WebSocket

# Set decimal precision for financial calculations
getcontext().prec = 28

# --- Configuration ---
def load_config():
    try:
        with open("bot_config.yaml") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.warning("bot_config.yaml not found. Relying on environment variables.")
        return {}
    except Exception as e:
        logging.error(f"Error loading bot_config.yaml: {e}")
        return {}

config = load_config()

# --- Logging Setup ---
log_level = logging.DEBUG if os.getenv("DEBUG_LOG", "false").lower() == "true" else logging.INFO
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bybit_bot.log")
    ]
)
logger = logging.getLogger(__name__)

API_KEY = os.getenv("BYBIT_API_KEY") or config.get("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET") or config.get("BYBIT_API_SECRET")
USE_TESTNET = (os.getenv("BYBIT_USE_TESTNET", "false") or config.get("BYBIT_USE_TESTNET", "false")).lower() == "true"
EMAIL_ALERTS = config.get("EMAIL_ALERTS", False)
EMAIL_SERVER = config.get("EMAIL_SERVER", {})
MAX_RETRIES = int(config.get("MAX_RETRIES", 5))

def send_email_alert(subject: str, body: str):
    if not EMAIL_ALERTS:
        return
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = EMAIL_SERVER.get('from')
        msg['To'] = EMAIL_SERVER.get('to')

        if not all([EMAIL_SERVER.get('host'), EMAIL_SERVER.get('port'), EMAIL_SERVER.get('user'), EMAIL_SERVER.get('pass')]):
            logger.error("Email server configuration is incomplete. Cannot send alert.")
            return

        with smtplib.SMTP(EMAIL_SERVER.get('host'), EMAIL_SERVER.get('port')) as server:
            server.starttls()
            server.login(EMAIL_SERVER.get('user'), EMAIL_SERVER.get('pass'))
            server.send_message(msg)
        logger.info("Email alert sent successfully.")
    except Exception as e:
        logger.error(f"Failed to send email alert: {e}", exc_info=True)

# --- WebSocket Manager ---
class BybitWebSocketManager:
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True, category: str = "linear"):
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.category = category
        self.ws: WebSocket | None = None
        self.market_data: dict[str, Any] = {}
        self.positions: dict[str, Any] = {}
        self.orders: dict[str, Any] = {}
        self.reconnect_attempts: int = 0

    def _get_ws(self):
        if not self.ws or not self.ws.is_connected():
            self.ws = WebSocket(
                testnet=self.testnet,
                channel_type=self.category,
                api_key=self.api_key,
                api_secret=self.api_secret,
            )
        return self.ws

    def handle_message(self, message: dict):
        topic = message.get("topic", "")
        if "orderbook" in topic:
            self.handle_orderbook(message)
        elif "publicTrade" in topic:
            self.handle_trades(message)
        elif "tickers" in topic:
            self.handle_ticker(message)
        elif "kline" in topic:
            self.handle_kline(message)
        elif "position" in topic:
            self.handle_position(message)
        elif "order" in topic:
            self.handle_order(message)
        elif "execution" in topic:
            self.handle_execution(message)
        elif "wallet" in topic:
            self.handle_wallet(message)

    def handle_orderbook(self, message: dict):
        data = message.get("data", {})
        symbol = data.get("s")
        if symbol:
            self.market_data.setdefault(symbol, {})["orderbook"] = data
            self.market_data[symbol]["timestamp"] = message.get("ts")

    def handle_trades(self, message: dict):
        data = message.get("data", [])
        for trade in data:
            symbol = trade.get("s")
            if symbol:
                self.market_data.setdefault(symbol, {})["last_trade"] = trade

    def handle_ticker(self, message: dict):
        data = message.get("data", {})
        symbol = data.get("s")
        if symbol:
            self.market_data.setdefault(symbol, {})["ticker"] = data

    def handle_position(self, message: dict):
        data = message.get("data", [])
        for position in data:
            symbol = position.get("symbol")
            if symbol:
                self.positions[symbol] = position

    def handle_order(self, message: dict):
        data = message.get("data", [])
        for order in data:
            order_id = order.get("orderId")
            if order_id:
                self.orders[order_id] = order

    def handle_execution(self, message: dict):
        data = message.get("data", [])
        for execution in data:
            order_id = execution.get("orderId")
            if order_id:
                logger.info(f"Execution for {order_id}: Price: {execution.get('execPrice')}, Qty: {execution.get('execQty')}, Side: {execution.get('side')}")

    def handle_wallet(self, message: dict):
        data = message.get("data", [])
        for wallet_data in data:
            coin = wallet_data.get("coin")
            if coin:
                logger.info(f"Wallet update for {coin}: Available: {wallet_data.get('availableToWithdraw')}, Total: {wallet_data.get('walletBalance')}")

    def handle_kline(self, message: dict):
        data = message.get("data", [])
        symbol = None
        if "topic" in message:
            parts = message["topic"].split(".")
            if len(parts) >= 3 and parts[0] == "kline":
                symbol = parts[-1]
        if symbol and data:
            self.market_data.setdefault(symbol, {})["kline"] = data

    async def subscribe(self, symbols: list[str]):
        ws = self._get_ws()
        public_channels = [f"orderbook.1.{symbol}" for symbol in symbols] + \
                          [f"publicTrade.{symbol}" for symbol in symbols] + \
                          [f"tickers.{symbol}" for symbol in symbols] + \
                          [f"kline.1m.{symbol}" for symbol in symbols]
        private_channels = ["position", "order", "execution", "wallet"]

        try:
            ws.subscribe(public_channels, callback=self.handle_message)
            ws.subscribe(private_channels, callback=self.handle_message)
            logger.info("Subscribed to WebSocket channels.")
        except Exception as e:
            logger.error(f"Error subscribing to WebSocket channels: {e}", exc_info=True)
            send_email_alert("WS Subscription Error", f"Failed to subscribe to WebSocket channels: {e}")

    def stop(self):
        if self.ws:
            self.ws.exit()
            logger.info("WebSocket connection closed.")

    async def reconnect(self, symbols: list[str]):
        self.reconnect_attempts += 1
        if self.reconnect_attempts > MAX_RETRIES:
            logger.critical("Max reconnect attempts reached. Shutting down.")
            send_email_alert("Critical: Max Reconnects", "Bot shutting down due to persistent connection issues.")
            sys.exit(1)
        backoff = min(2 ** self.reconnect_attempts + random.uniform(0, 1), 60)
        logger.warning(f"Reconnecting WebSocket after {backoff:.2f} seconds (Attempt {self.reconnect_attempts}/{MAX_RETRIES})")
        await asyncio.sleep(backoff)
        try:
            await self.subscribe(symbols)
            self.reconnect_attempts = 0
            logger.info("WebSocket reconnected successfully.")
        except Exception as e:
            logger.error(f"Error during WebSocket reconnection: {e}", exc_info=True)
            send_email_alert("WS Reconnect Error", f"Error during reconnection attempt: {e}")

# --- Trading Bot Core ---
class BybitTradingBot:
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        self.session = HTTP(
            testnet=testnet,
            api_key=api_key,
            api_secret=api_secret,
            recv_window=10000
        )
        self.category: str = config.get("CATEGORY", "linear")
        self.ws_manager = BybitWebSocketManager(api_key, api_secret, testnet, category=self.category)
        self.strategy: Callable[[dict, dict, HTTP, Any, list[str]], None] | None = None
        self.symbol_info: dict[str, Any] = {}
        self.max_open_positions: int = config.get("MAX_OPEN_POSITIONS", 5)
        self.base_currency: str = config.get("BASE_CURRENCY", "USDT")

        logger.info(f"Bybit Trading Bot initialized. Testnet: {testnet}, Category: {self.category}, Base Currency: {self.base_currency}")

    async def fetch_symbol_info(self, symbols: list[str]):
        logger.info(f"Fetching instrument info for symbols: {symbols}")
        try:
            for symbol in symbols:
                for attempt in range(MAX_RETRIES):
                    try:
                        response = await asyncio.to_thread(self.session.get_instruments_info, category=self.category, symbol=symbol)
                        if response and response.get('retCode') == 0:
                            instrument_list = response.get('result', {}).get('list', [])
                            found = False
                            for item in instrument_list:
                                if item.get('symbol') == symbol:
                                    self.symbol_info[symbol] = {
                                        "minOrderQty": Decimal(item.get('lotSizeFilter', {}).get('minOrderQty', '0')),
                                        "qtyStep": Decimal(item.get('lotSizeFilter', {}).get('qtyStep', '1')),
                                        "tickSize": Decimal(item.get('priceFilter', {}).get('tickSize', '0.000001')),
                                        "minPrice": Decimal(item.get('priceFilter', {}).get('minPrice', '0')),
                                        "maxPrice": Decimal(item.get('priceFilter', {}).get('maxPrice', '1000000')),
                                        "leverageFilter": item.get('leverageFilter', {}),
                                        "riskLimit": item.get('riskLimit', {})
                                    }
                                    logger.info(f"Successfully fetched instrument info for {symbol}.")
                                    found = True
                                    break
                            if not found:
                                logger.warning(f"Symbol {symbol} not found in instruments list response.")
                            break
                        else:
                            logger.warning(f"Attempt {attempt+1}/{MAX_RETRIES} for {symbol}: API returned error code {response.get('retCode')}: {response.get('retMsg')}")
                            await asyncio.sleep(2 ** attempt)
                    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, urllib3.exceptions.MaxRetryError, urllib3.exceptions.NewConnectionError, socket.gaierror) as e:
                        logger.warning(f"Attempt {attempt+1}/{MAX_RETRIES} for {symbol}: Network/Connection error occurred: {e}")
                        await asyncio.sleep(2 ** attempt)
                else:
                    logger.error(f"Failed to fetch instrument info for {symbol} after {MAX_RETRIES} retries.")
                    send_email_alert("Symbol Info Failure", f"Failed to fetch instrument info for {symbol} after retries.")
        except Exception as e:
            logger.error(f"An unexpected error occurred during fetch_symbol_info: {e}", exc_info=True)

    def set_strategy(self, strategy_func: Callable[[dict, dict, HTTP, Any, list[str]], None]):
        self.strategy = strategy_func
        logger.info("Trading strategy set.")

    def _round_to_qty_step(self, symbol: str, quantity: Decimal) -> Decimal:
        if symbol not in self.symbol_info:
            logger.warning(f"Symbol info not available for {symbol}. Cannot round quantity.")
            return quantity
        qty_step = self.symbol_info[symbol]["qtyStep"]
        return (quantity // qty_step) * qty_step

    def _round_to_tick_size(self, symbol: str, price: Decimal) -> Decimal:
        if symbol not in self.symbol_info:
            logger.warning(f"Symbol info not available for {symbol}. Cannot round price.")
            return price
        tick_size = self.symbol_info[symbol]["tickSize"]
        return price.quantize(tick_size)

    async def get_market_data(self, symbol: str) -> dict | None:
        ws_data = self.ws_manager.market_data.get(symbol)
        if ws_data and ws_data.get("orderbook") and ws_data.get("ticker") and (time.time() * 1000 - ws_data.get("timestamp", 0)) < 2000:
            return ws_data
        logger.debug(f"WebSocket data for {symbol} not fresh or complete. Falling back to REST API.")
        try:
            orderbook_resp = await asyncio.to_thread(self.session.get_orderbook, category=self.category, symbol=symbol)
            ticker_resp = await asyncio.to_thread(self.session.get_tickers, category=self.category, symbol=symbol)
            if orderbook_resp.get('retCode') == 0 and ticker_resp.get('retCode') == 0:
                ticker_list = ticker_resp.get('result', {}).get('list', [])
                ticker_data = ticker_list[0] if ticker_list else {}
                return {
                    "orderbook": orderbook_resp.get('result', {}),
                    "ticker": ticker_data,
                    "last_trade": ws_data.get("last_trade") if ws_data else [],
                    "timestamp": time.time() * 1000
                }
            else:
                logger.warning(f"Failed to get market data for {symbol} via REST. Orderbook: {orderbook_resp.get('retMsg')}, Ticker: {ticker_resp.get('retMsg')}")
                return None
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, urllib3.exceptions.MaxRetryError, urllib3.exceptions.NewConnectionError, socket.gaierror) as e:
            logger.error(f"Error fetching market data for {symbol} via REST: {e}", exc_info=True)
            return None

    async def get_account_info(self, account_type: str = "UNIFIED") -> dict | None:
        try:
            balance_response = await asyncio.to_thread(self.session.get_wallet_balance, accountType=account_type)
            if balance_response.get('retCode') == 0:
                return balance_response.get('result', {})
            else:
                logger.warning(f"Failed to get account balance. API Response: {balance_response.get('retMsg')}")
                return None
        except Exception as e:
            logger.error(f"Error fetching account balance: {e}", exc_info=True)
            return None

    async def calculate_position_size(self, symbol: str, capital_percentage: float, price: Decimal, account_info: dict) -> Decimal:
        if symbol not in self.symbol_info:
            logger.warning(f"Symbol info not available for {symbol}. Cannot calculate position size.")
            return Decimal(0)
        try:
            available_balance = Decimal(0)
            for wallet_entry in account_info.get('list', []):
                for coin_info in wallet_entry.get('coin', []):
                    if coin_info.get('coin') == self.base_currency:
                        try:
                            available_balance = Decimal(str(coin_info.get('availableToWithdraw', '0')))
                        except decimal.InvalidOperation:
                            available_balance = Decimal('0')
                        break
                if available_balance > 0:
                    break
            if available_balance <= 0:
                logger.warning(f"No available balance for {self.base_currency} to calculate position size.")
                return Decimal(0)
            if price <= 0:
                logger.warning(f"Invalid price ({price}) for {symbol}. Cannot calculate position size.")
                return Decimal(0)
            target_capital = available_balance * Decimal(str(capital_percentage))
            raw_qty = target_capital / price
            rounded_qty = self._round_to_qty_step(symbol, raw_qty)
            min_order_qty = self.symbol_info[symbol]["minOrderQty"]
            if rounded_qty < min_order_qty:
                logger.info(f"Calculated quantity {rounded_qty} for {symbol} is below minimum order quantity {min_order_qty}. Skipping.")
                return Decimal(0)
            return rounded_qty
        except Exception as e:
            logger.error(f"Error calculating position size for {symbol}: {e}", exc_info=True)
            return Decimal(0)

    async def get_historical_klines(self, symbol: str, interval: str, limit: int = 200) -> dict | None:
        try:
            klines_response = await asyncio.to_thread(self.session.get_kline,
                                             category=self.category,
                                             symbol=symbol,
                                             interval=interval,
                                             limit=limit)
            if klines_response.get('retCode') == 0:
                return klines_response
            else:
                logger.warning(f"Failed to get historical klines for {symbol}. API Response: {klines_response.get('retMsg')}")
                return None
        except Exception as e:
            logger.error(f"Error fetching historical klines for {symbol}: {e}", exc_info=True)
            return None

    def get_open_positions_count(self) -> int:
        return sum(1 for position_data in self.ws_manager.positions.values() if Decimal(position_data.get('size', '0')) != Decimal('0'))

    async def place_order(self, symbol: str, side: str, order_type: str, qty: Decimal, price: Decimal | None = None, **kwargs) -> dict | None:
        if qty <= 0:
            logger.warning(f"Order quantity for {symbol} is zero or negative. Skipping order placement.")
            return None
        if order_type == "Limit" and (price is None or price <= 0):
            logger.warning(f"Limit order for {symbol} requires a valid price. Skipping order placement.")
            return None
        if self.get_open_positions_count() >= self.max_open_positions:
            logger.warning(f"Max open positions ({self.max_open_positions}) reached. Cannot place new order for {symbol}.")
            return None

        qty = self._round_to_qty_step(symbol, qty)
        if qty <= 0:
            logger.warning(f"Rounded quantity for {symbol} is zero. Skipping order placement.")
            return None
        if price:
            price = self._round_to_tick_size(symbol, price)

        try:
            params = {
                "category": self.category,
                "symbol": symbol,
                "side": side,
                "orderType": order_type,
                "qty": str(qty),
                **kwargs
            }
            if price:
                params["price"] = str(price)

            order_response = await asyncio.to_thread(self.session.place_order, **params)

            if order_response.get('retCode') == 0:
                order_result = order_response.get('result', {})
                logger.info(f"Order placed successfully for {symbol}: OrderID={order_result.get('orderId')}")
                return order_result
            else:
                error_msg = order_response.get('retMsg', 'Unknown error')
                logger.error(f"Failed to place order for {symbol}: {error_msg}")
                send_email_alert("Order Placement Failure", f"For {symbol} ({order_type} {side} {qty}): {error_msg}")
                return None
        except Exception as e:
            logger.error(f"Exception occurred while placing order for {symbol}: {e}", exc_info=True)
            return None

    async def cancel_all_orders(self, symbol: str) -> bool:
        try:
            response = await asyncio.to_thread(self.session.cancel_all_orders, category=self.category, symbol=symbol)
            if response.get('retCode') == 0:
                logger.info(f"All open orders cancelled for {symbol}.")
                return True
            else:
                error_msg = response.get('retMsg', 'Unknown error')
                logger.error(f"Failed to cancel all orders for {symbol}: {error_msg}")
                return False
        except Exception as e:
            logger.error(f"Exception occurred while cancelling all orders for {symbol}: {e}", exc_info=True)
            return False

    async def close_all_positions(self, symbols: list[str]):
        logger.info("Closing all open positions...")
        for symbol in symbols:
            position = self.ws_manager.positions.get(symbol, {})
            size = Decimal(position.get('size', '0'))
            side = position.get('side')
            if size > 0:
                close_side = "Sell" if side == "Buy" else "Buy"
                logger.info(f"Closing {side} position for {symbol} with size {size}...")
                await self.place_order(symbol, close_side, "Market", size.abs())
                await asyncio.sleep(0.5)
        logger.info("Finished closing all open positions.")

    async def run(self, symbols: list[str], interval: int):
        if not self.strategy:
            logger.error("No trading strategy set. Bot cannot run.")
            return

        await self.fetch_symbol_info(symbols)
        await self.ws_manager.subscribe_public_channels(symbols)
        await self.ws_manager.subscribe_private_channels()

        logger.info("Bot starting main loop...")
        try:
            while True:
                if not self.ws_manager.ws.is_connected():
                    await self.ws_manager.reconnect(symbols)

                current_market_data: dict[str, Any] = {}
                for symbol in symbols:
                    market_data_for_symbol = await self.get_market_data(symbol)
                    if market_data_for_symbol:
                        current_market_data[symbol] = market_data_for_symbol

                account_info = await self.get_account_info()

                if current_market_data and account_info:
                    await self.strategy(current_market_data, account_info, self.session, self, symbols, config)

                await asyncio.sleep(interval)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user.")
        except Exception as e:
            logger.critical(f"Unhandled critical error in main loop: {e}", exc_info=True)
            send_email_alert("Critical Bot Error", f"An unhandled critical error occurred:\n{traceback.format_exc()}")
        finally:
            logger.info("Initiating shutdown sequence...")
            await self.close_all_positions(symbols)
            self.ws_manager.stop()
            logger.info("Bot gracefully shut down.")

async def main():
    if not API_KEY or not API_SECRET:
        logger.error("API credentials are missing.")
        return

    bot = BybitTradingBot(api_key=API_KEY, api_secret=API_SECRET, testnet=USE_TESTNET)

    symbols_to_trade = config.get("SYMBOLS", ["BTCUSDT", "ETHUSDT"])
    if not symbols_to_trade:
        logger.error("No trading symbols configured.")
        return

    try:
        from market_making_strategy import market_making_strategy
        bot.set_strategy(market_making_strategy)
    except ImportError:
        logger.error("Failed to import 'market_making_strategy'.")
        return
    except Exception as e:
        logger.error(f"An error occurred during strategy import: {e}", exc_info=True)
        return

    interval = config.get("INTERVAL", 5)
    await bot.run(symbols=symbols_to_trade, interval=interval)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot terminated by user.")
    except Exception as e:
        logger.critical(f"Unhandled error during asyncio run: {e}", exc_info=True)
