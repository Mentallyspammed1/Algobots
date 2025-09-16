import logging
import os
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

from pybit.unified_trading import HTTP, WebSocket
from utils import round_decimal

# --- Initialize Logging for Bybit API ---
bybit_logger = logging.getLogger('bybit_api')
bybit_logger.setLevel(logging.INFO)
bybit_logger.propagate = False
if not bybit_logger.handlers:
    file_handler = logging.FileHandler('bybit_api.log')
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    bybit_logger.addHandler(file_handler)

class BybitClient:
    """A client for interacting with the Bybit API using the pybit library.
    Handles authentication, requests, and data parsing.
    """

    def __init__(self, api_endpoint: str, category: str,
                 retries: int = 5, backoff_factor: float = 0.5,
                 use_websocket: bool = False, ws_callbacks: dict[str, Callable] | None = None, recv_window: int = 10000):
        """Initializes the BybitClient.
        API Key and Secret are loaded from environment variables for security.

        Args:
            api_endpoint (str): The base URL for the Bybit API (e.g., "https://api.bybit.com").
            category (str): The trading category (e.g., "linear", "inverse", "spot").
            retries (int): Max number of retries for failed API requests.
            backoff_factor (float): Factor for exponential backoff between retries.
            use_websocket (bool): Whether to initialize and use WebSocket client.
            ws_callbacks (Optional[Dict[str, Callable]]): Dictionary of callbacks for WebSocket events.
        """
        self.api_key = os.getenv("BYBIT_API_KEY")
        self.api_secret = os.getenv("BYBIT_API_SECRET")
        self.api_endpoint = api_endpoint
        self.category = category
        self.max_retries = retries
        self.backoff_factor = backoff_factor
        self.use_websocket = use_websocket
        self.ws_callbacks = ws_callbacks if ws_callbacks is not None else {}

        if not self.api_key or not self.api_secret:
            raise ValueError(
                "BYBIT_API_KEY and BYBIT_API_SECRET must be set as environment variables."
                " Create a .env file or set them in your shell."
            )

        # Initialize pybit HTTP client
        self.session = HTTP(
            api_key=self.api_key,
            api_secret=self.api_secret,
            testnet="testnet" in self.api_endpoint,
            recv_window=self.recv_window
        )
        bybit_logger.info("BybitClient initialized with pybit HTTP session.")

        if self.use_websocket:
            self.ws_session = WebSocket(
                testnet="testnet" in self.api_endpoint, # Determine testnet from endpoint
                api_key=self.api_key,
                api_secret=self.api_secret,
                channel_type="private", # Default to private for account data
                recv_window=self.recv_window
            )
            if "on_position_update" in self.ws_callbacks:
                self.ws_session.position_stream(callback=self.ws_callbacks["on_position_update"])
            if "on_order_update" in self.ws_callbacks:
                self.ws_session.order_stream(callback=self.ws_callbacks["on_order_update"])
            if "on_execution_update" in self.ws_callbacks:
                self.ws_session.execution_stream(callback=self.ws_callbacks["on_execution_update"])
            bybit_logger.info("BybitClient initialized with pybit WebSocket session.")

    def subscribe_to_ws_topics(self, topics: list, callback: Callable):
        """Subscribes to a list of WebSocket topics using the new stream methods.

        Args:
            topics (list): List of topics to subscribe to (e.g., ["orderbook.50.BTCUSDT", "kline.5.BTCUSDT"])
            callback (Callable): The callback function to handle incoming messages.
        """
        if self.use_websocket and hasattr(self, 'ws_session'):
            for topic in topics:
                if topic.startswith("orderbook"):
                    symbol = topic.split('.')[-1]
                    self.ws_session.orderbook_stream(symbol=symbol, callback=callback)
                elif topic.startswith("kline"):
                    parts = topic.split('.')
                    interval = parts[1]
                    symbol = parts[2]
                    self.ws_session.kline_stream(symbol=symbol, interval=interval, callback=callback)
                elif topic.startswith("publicTrade"):
                    symbol = topic.split('.')[-1]
                    self.ws_session.trade_stream(symbol=symbol, callback=callback)
                elif topic.startswith("tickers"):
                    symbol = topic.split('.')[-1]
                    self.ws_session.ticker_stream(symbol=symbol, callback=callback)
                else:
                    bybit_logger.warning(f"Unsupported WebSocket topic for direct subscription: {topic}")
            bybit_logger.info(f"Subscribed to WebSocket topics: {topics}")
        else:
            bybit_logger.warning("WebSocket client not initialized. Cannot subscribe to topics.")





    def fetch_klines(self, symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
        """Fetches historical kline data for a given symbol and interval using pybit.

        Args:
            symbol (str): The trading pair (e.g., "BTCUSDT").
            interval (str): The kline interval (e.g., "1", "5", "60", "D").
            limit (int): The number of candles to fetch (max 1000 for Bybit).

        Returns:
            pd.DataFrame: DataFrame with 'open', 'high', 'low', 'close', 'volume', 'timestamp'
                          indexed by datetime, or empty DataFrame on failure.
        """
        try:
            response = self.session.get_kline(
                category=self.category,
                symbol=symbol,
                interval=interval,
                limit=limit
            )
            if response and response['retCode'] == 0 and response['result'] and response['result']['list']:
                data = []
                for kline in response['result']['list']:
                    timestamp_ms = int(kline[0])
                    data.append({
                        'timestamp': datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc),
                        'open': float(kline[1]),
                        'high': float(kline[2]),
                        'low': float(kline[3]),
                        'close': float(kline[4]),
                        'volume': float(kline[5]),
                    })
                df = pd.DataFrame(data).set_index('timestamp').sort_index()
                bybit_logger.info(f"Fetched {len(df)} klines for {symbol}-{interval} using pybit.")
                return df
            bybit_logger.warning(f"Failed to fetch klines for {symbol}-{interval} using pybit: {response}")
            return pd.DataFrame()
        except Exception as e:
            bybit_logger.error(f"Error fetching klines with pybit: {e}")
            return pd.DataFrame()

    def get_positions(self, symbol: str) -> dict[str, Any] | None:
        """Retrieves the open position for a given symbol using pybit.

        Args:
            symbol (str): The trading pair.

        Returns:
            dict: Dictionary containing position details, or None if no open position.
        """
        try:
            response = self.session.get_positions(
                category=self.category,
                symbol=symbol
            )
            if response and response['retCode'] == 0 and response['result'] and response['result']['list']:
                open_positions = [
                    p for p in response['result']['list']
                    if float(p.get('size', 0)) > 0
                ]
                if open_positions:
                    bybit_logger.info(f"Found open position for {symbol}: {open_positions[0].get('side')} {open_positions[0].get('size')} using pybit.")
                    return open_positions[0]
            bybit_logger.info(f"No open position found for {symbol} using pybit.")
            return None
        except Exception as e:
            bybit_logger.error(f"Error getting open positions with pybit: {e}")
            return None

    def get_wallet_balance(self, account_type: str = "UNIFIED", coin: str | None = None) -> dict[str, Any] | None:
        """Retrieves wallet balance for a given account type and optional coin using pybit.

        Args:
            account_type (str): "UNIFIED", "CONTRACT", etc.
            coin (Optional[str]): Specific coin to query (e.g., "USDT", "BTC").

        Returns:
            dict: Dictionary containing wallet balance details, or None on failure.
        """
        try:
            params = {"accountType": account_type}
            if coin:
                params["coin"] = coin
            response = self.session.get_wallet_balance(**params)
            if response and response['retCode'] == 0 and response['result'] and response['result']['list']:
                bybit_logger.info(f"Fetched wallet balance for {account_type} (Coin: {coin}): {response['result']['list']}")
                return response['result']['list'][0] # Assuming first item is relevant
            bybit_logger.warning(f"Failed to fetch wallet balance for {account_type} (Coin: {coin}): {response}")
            return None
        except Exception as e:
            bybit_logger.error(f"Error fetching wallet balance with pybit: {e}")
            return None

    def get_account_info(self) -> dict[str, Any] | None:
        """Fetches account details using pybit.

        Returns:
            dict: Dictionary containing account details, or None on failure.
        """
        try:
            response = self.session.get_account_info()
            if response and response['retCode'] == 0 and response['result']:
                bybit_logger.info(f"Fetched account info: {response['result']}")
                return response['result']
            bybit_logger.warning(f"Failed to fetch account info: {response}")
            return None
        except Exception as e:
            bybit_logger.error(f"Error fetching account info with pybit: {e}")
            return None

    def get_transaction_log(self, coin: str | None = None, limit: int = 50) -> dict[str, Any] | None:
        """Queries transaction history for a Contract account using pybit.

        Args:
            coin (Optional[str]): Optional: Filter by coin.
            limit (int): Optional: Limit the number of records.

        Returns:
            dict: Dictionary containing transaction log details, or None on failure.
        """
        try:
            params = {"category": self.category, "limit": limit}
            if coin:
                params["coin"] = coin
            response = self.session.get_transaction_log(**params)
            if response and response['retCode'] == 0 and response['result']:
                bybit_logger.info(f"Fetched transaction log for {self.category} (Coin: {coin}): {len(response['result'].get('list', []))} records.")
                return response['result']
            bybit_logger.warning(f"Failed to fetch transaction log for {self.category} (Coin: {coin}): {response}")
            return None
        except Exception as e:
            bybit_logger.error(f"Error fetching transaction log with pybit: {e}")
            return None

    def set_leverage(self, symbol: str, buy_leverage: str, sell_leverage: str) -> bool:
        """Sets leverage for a specific contract symbol using pybit.

        Args:
            symbol (str): The trading pair.
            buy_leverage (str): Leverage for buy side (e.g., "10").
            sell_leverage (str): Leverage for sell side (e.g., "10").

        Returns:
            bool: True if leverage was set successfully, False otherwise.
        """
        try:
            response = self.session.set_leverage(
                category=self.category,
                symbol=symbol,
                buyLeverage=buy_leverage,
                sellLeverage=sell_leverage
            )
            if response and response['retCode'] == 0:
                bybit_logger.info(f"Leverage set to Buy: {buy_leverage}, Sell: {sell_leverage} for {symbol}.")
                return True
            bybit_logger.warning(f"Failed to set leverage for {symbol}: {response}")
            return False
        except Exception as e:
            bybit_logger.error(f"Error setting leverage with pybit: {e}")
            return False

    def cancel_order(self, symbol: str, order_id: str | None = None, order_link_id: str | None = None) -> bool:
        """Cancels a specific order by order ID or orderLinkId using pybit.

        Args:
            symbol (str): The trading pair.
            order_id (Optional[str]): The order ID.
            order_link_id (Optional[str]): The client-generated order ID.

        Returns:
            bool: True if the order was canceled successfully, False otherwise.
        """
        try:
            if not order_id and not order_link_id:
                bybit_logger.error("Either order_id or order_link_id must be provided to cancel an order.")
                return False

            params = {"category": self.category, "symbol": symbol}
            if order_id: params["orderId"] = order_id
            if order_link_id: params["orderLinkId"] = order_link_id

            response = self.session.cancel_order(**params)
            if response and response['retCode'] == 0:
                bybit_logger.info(f"Order {order_id or order_link_id} for {symbol} canceled successfully.")
                return True
            bybit_logger.warning(f"Failed to cancel order {order_id or order_link_id} for {symbol}: {response}")
            return False
        except Exception as e:
            bybit_logger.error(f"Error canceling order with pybit: {e}")
            return False

    def cancel_all_orders(self, symbol: str | None = None, settle_coin: str | None = None) -> bool:
        """Cancels all open orders for a specific contract type or symbol using pybit.

        Args:
            symbol (Optional[str]): Optional: Cancel for specific symbol.
            settle_coin (Optional[str]): Optional: Cancel by settlement coin (e.g., "USDT").

        Returns:
            bool: True if orders were canceled successfully, False otherwise.
        """
        try:
            params = {"category": self.category}
            if symbol: params["symbol"] = symbol
            if settle_coin: params["settleCoin"] = settle_coin

            response = self.session.cancel_all_orders(**params)
            if response and response['retCode'] == 0:
                bybit_logger.info(f"All orders for {symbol or self.category} canceled successfully.")
                return True
            bybit_logger.warning(f"Failed to cancel all orders for {symbol or self.category}: {response}")
            return False
        except Exception as e:
            bybit_logger.error(f"Error canceling all orders with pybit: {e}")
            return False

    def get_tickers(self, symbol: str | None = None) -> dict[str, Any] | None:
        """Fetches the latest price, bid/ask, and 24h volume for a Contract using pybit.

        Args:
            symbol (Optional[str]): The trading pair (e.g., "BTCUSDT"). If None, returns all tickers for the category.

        Returns:
            dict: Dictionary containing ticker details, or None on failure.
        """
        try:
            params = {"category": self.category}
            if symbol: params["symbol"] = symbol

            response = self.session.get_tickers(**params)
            if response and response['retCode'] == 0 and response['result']:
                bybit_logger.info(f"Fetched tickers for {symbol or self.category}.")
                return response['result']
            bybit_logger.warning(f"Failed to fetch tickers for {symbol or self.category}: {response}")
            return None
        except Exception as e:
            bybit_logger.error(f"Error fetching tickers with pybit: {e}")
            return None

    def get_orderbook(self, symbol: str, limit: int = 25) -> dict[str, Any] | None:
        """Fetches the current order book depth for a specific contract symbol using pybit.

        Args:
            symbol (str): The trading pair.
            limit (int): The number of order book levels to return (e.g., 1, 25, 50, 100, 200).

        Returns:
            dict: Dictionary containing order book details, or None on failure.
        """
        try:
            response = self.session.get_orderbook(
                category=self.category,
                symbol=symbol,
                limit=limit
            )
            if response and response['retCode'] == 0 and response['result']:
                bybit_logger.info(f"Fetched orderbook for {symbol} with {limit} levels.")
                return response['result']
            bybit_logger.warning(f"Failed to fetch orderbook for {symbol}: {response}")
            return None
        except Exception as e:
            bybit_logger.error(f"Error fetching orderbook with pybit: {e}")
            return None

    def get_active_orders(self, symbol: str | None = None) -> dict[str, Any] | None:
        """Queries open or untriggered orders for a contract using pybit.

        Args:
            symbol (Optional[str]): The trading pair.

        Returns:
            dict: Dictionary containing active order details, or None on failure.
        """
        try:
            params = {"category": self.category}
            if symbol: params["symbol"] = symbol

            response = self.session.get_open_orders(**params)
            if response and response['retCode'] == 0 and response['result']:
                bybit_logger.info(f"Fetched active orders for {symbol or self.category}: {len(response['result'].get('list', []))} records.")
                return response['result']
            bybit_logger.warning(f"Failed to fetch active orders for {symbol or self.category}: {response}")
            return None
        except Exception as e:
            bybit_logger.error(f"Error fetching active orders with pybit: {e}")
            return None

    def get_recent_trade(self, symbol: str, limit: int = 50) -> dict[str, Any] | None:
        """Retrieves recent trade execution data for a contract using pybit.

        Args:
            symbol (str): The trading pair.
            limit (int): The number of records to return.

        Returns:
            dict: Dictionary containing recent trade details, or None on failure.
        """
        try:
            response = self.session.get_public_trading_history(
                category=self.category,
                symbol=symbol,
                limit=limit
            )
            if response and response['retCode'] == 0 and response['result']:
                bybit_logger.info(f"Fetched {len(response['result'].get('list', []))} recent trades for {symbol}.")
                return response['result']
            bybit_logger.warning(f"Failed to fetch recent trades for {symbol}: {response}")
            return None
        except Exception as e:
            bybit_logger.error(f"Error fetching recent trades with pybit: {e}")
            return None

    def get_fee_rate(self, symbol: str) -> dict[str, Any] | None:
        """Retrieves your current trading fee rates for a symbol using pybit.

        Args:
            symbol (str): The trading pair.

        Returns:
            dict: Dictionary containing fee rate details, or None on failure.
        """
        try:
            response = self.session.get_fee_rate(
                category=self.category,
                symbol=symbol
            )
            if response and response['retCode'] == 0 and response['result']:
                bybit_logger.info(f"Fetched fee rate for {symbol}: {response['result']}")
                return response['result']
            bybit_logger.warning(f"Failed to fetch fee rate for {symbol}: {response}")
            return None
        except Exception as e:
            bybit_logger.error(f"Error fetching fee rate with pybit: {e}")
            return None

    def get_transfer_query_account_coins_balance(self, account_type: str, coin: str | None = None) -> dict[str, Any] | None:
        """Checks coin balances across accounts using pybit.

        Args:
            account_type (str): Account type (e.g., "UNIFIED", "CONTRACT").
            coin (Optional[str]): Optional: Specific coin to query.

        Returns:
            dict: Dictionary containing coin balance details, or None on failure.
        """
        try:
            params = {"accountType": account_type}
            if coin: params["coin"] = coin

            response = self.session.get_transfer_query_account_coins_balance(**params)
            if response and response['retCode'] == 0 and response['result']:
                bybit_logger.info(f"Fetched account coin balance for {account_type} (Coin: {coin}).")
                return response['result']
            bybit_logger.warning(f"Failed to fetch account coin balance for {account_type} (Coin: {coin}): {response}")
            return None
        except Exception as e:
            bybit_logger.error(f"Error fetching account coin balance with pybit: {e}")
            return None

    def get_instrument_info(self, symbol: str) -> dict[str, Any] | None:
        """Fetches instrument information for a given symbol.
        """
        try:
            response = self.session.get_instruments_info(
                category=self.category,
                symbol=symbol
            )
            if response and response['retCode'] == 0 and response['result'] and response['result']['list']:
                if response['result']['list']:
                    return response['result']['list'][0]
            bybit_logger.warning(f"Could not fetch instrument info for {symbol}: {response}")
            return None
        except Exception as e:
            bybit_logger.error(f"Error fetching instrument info: {e}")
            return None

    def place_order(self, symbol: str, side: str, usdt_amount: float,
                    order_type: str = "Market", price: float | None = None,
                    stop_loss_pct: float | None = None, take_profit_pct: float | None = None) -> bool:
        """Places an order with Stop Loss and Take Profit using pybit, with proper order sizing.

        Args:
            symbol (str): The trading pair.
            side (str): 'BUY' or 'SELL'.
            usdt_amount (float): The desired amount in USDT to trade.
            order_type (str): "Market" or "Limit".
            price (Optional[float]): Price for Limit orders.
            stop_loss_pct (Optional[float]): Percentage for Stop Loss (e.g., 0.005 for 0.5%).
            take_profit_pct (Optional[float]): Percentage for Take Profit (e.g., 0.01 for 1%).

        Returns:
            bool: True if the order was successfully placed, False otherwise.
        """
        try:
            # Get instrument info for min_qty and qty_step
            instrument_info = self.get_instrument_info(symbol)
            if not instrument_info:
                bybit_logger.error(f"Could not fetch instrument info for {symbol}. Cannot place order.")
                return False

            min_qty = float(instrument_info.get('lotSizeFilter', {}).get('minOrderQty', 0))
            qty_step = float(instrument_info.get('lotSizeFilter', {}).get('qtyStep', 0))

            # Get current price for quantity calculation
            klines_df = self.fetch_klines(symbol, "1", limit=1)
            if klines_df.empty:
                bybit_logger.error(f"Could not fetch current price for {symbol} to calculate quantity.")
                return False
            current_price_for_qty = klines_df['close'].iloc[-1]

            # Calculate order quantity using the new utility function
            calculated_quantity = calculate_order_quantity(usdt_amount, current_price_for_qty, min_qty, qty_step)
            if calculated_quantity <= 0:
                bybit_logger.error(f"Calculated quantity is zero or negative: {calculated_quantity}. Cannot place order.")
                return False

            order_params = {
                "category": self.category,
                "symbol": symbol,
                "side": side.capitalize(),  # pybit expects 'Buy' or 'Sell'
                "orderType": order_type,
                "qty": str(calculated_quantity),
                "timeInForce": "GTC",
            }

            if order_type == "Limit":
                if price is None:
                    bybit_logger.error("Price must be provided for Limit orders.")
                    return False
                order_params["price"] = str(price)

            # Calculate SL/TP prices if percentages are provided
            calculated_stop_loss_price = None
            calculated_take_profit_price = None

            if stop_loss_pct is not None or take_profit_pct is not None:
                # Get current price to calculate SL/TP if not a limit order with explicit price
                current_price_for_sl_tp = price if order_type == "Limit" and price is not None else None
                if current_price_for_sl_tp is None:
                    klines_df = self.fetch_klines(symbol, "1", limit=1)
                    if klines_df.empty:
                        bybit_logger.error(f"Could not fetch current price for {symbol} to calculate SL/TP.")
                        return False
                    current_price_for_sl_tp = klines_df['close'].iloc[-1]

                if stop_loss_pct is not None:
                    if side.upper() == 'BUY':
                        calculated_stop_loss_price = current_price_for_sl_tp * (1 - stop_loss_pct)
                    elif side.upper() == 'SELL':
                        calculated_stop_loss_price = current_price_for_sl_tp * (1 + stop_loss_pct)

                if take_profit_pct is not None:
                    if side.upper() == 'BUY':
                        calculated_take_profit_price = current_price_for_sl_tp * (1 + take_profit_pct)
                    elif side.upper() == 'SELL':
                        calculated_take_profit_price = current_price_for_sl_tp * (1 - take_profit_pct)

            # Use utils.round_decimal for precise formatting
            sl_tp_precision = 2  # Example: 2 decimal places for SL/TP prices

            if calculated_stop_loss_price is not None:
                order_params["stopLoss"] = str(round_decimal(calculated_stop_loss_price, sl_tp_precision))
            if calculated_take_profit_price is not None:
                order_params["takeProfit"] = str(round_decimal(calculated_take_profit_price, sl_tp_precision))

            bybit_logger.info(f"Attempting to place {order_type} {side.upper()} order for {calculated_quantity} {symbol} (USDT: {usdt_amount}) with params: {order_params}")
            response = self.session.place_order(**order_params)

            if response and response.get('retCode') == 0:
                bybit_logger.info(f"Order placed successfully: {response.get('result')} using pybit.")
                return True
            bybit_logger.error(f"Failed to place order using pybit: {response}")
            return False
        except Exception as e:
            bybit_logger.error(f"Error placing order with pybit: {e}")
            return False
