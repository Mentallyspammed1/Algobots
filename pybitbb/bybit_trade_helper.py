# bybit_trade_helper.py
import logging
import time
from typing import Any

from pybit.exceptions import BybitAPIError
from pybit.exceptions import BybitRequestError
from pybit.unified_trading import HTTP

# Configure logging for the module
logging.basicConfig(
    level=logging.INFO,  # Changed to INFO for less verbose default output, DEBUG for full details
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


class BybitTradeHelper:
    """A helper class for managing Bybit trading operations, including placing,
    amending, and canceling orders, as well as managing positions via the
    Unified Trading HTTP API.
    """

    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        """Initializes the BybitTradeHelper with API credentials and environment.

        :param api_key: Your Bybit API key.
        :param api_secret: Your Bybit API secret.
        :param testnet: Set to True to connect to the Bybit testnet, False for mainnet.
        """
        if not api_key or not api_secret:
            logger.error("API Key and Secret are required for BybitTradeHelper.")
            raise ValueError("API Key and Secret must be provided.")

        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.session = HTTP(
            testnet=self.testnet, api_key=self.api_key, api_secret=self.api_secret
        )
        logger.info(
            f"BybitTradeHelper initialized for {'testnet' if self.testnet else 'mainnet'}."
        )

    def _make_request(
        self, method: str, endpoint_name: str, **kwargs
    ) -> dict[str, Any] | None:
        """Internal method to make an HTTP request to the Bybit API and handle responses.
        It centralizes error handling and logging for API calls.

        :param method: The name of the method to call on the `self.session` object (e.g., 'place_order').
        :param endpoint_name: A descriptive name for the API endpoint, used in logging.
        :param kwargs: Keyword arguments to pass directly to the `pybit` API method.
        :return: The 'result' dictionary from the API response if the call is successful (retCode == 0),
                 otherwise returns None after logging the error.
        """
        try:
            func = getattr(self.session, method)
            response = func(**kwargs)

            if response and response.get("retCode") == 0:
                logger.debug(
                    f"[{endpoint_name}] Successfully called. Response: {response.get('result')}"
                )
                return response.get("result")
            ret_code = response.get("retCode", "N/A")
            error_msg = response.get("retMsg", "Unknown error")
            logger.error(
                f"[{endpoint_name}] API call failed. Code: {ret_code}, Message: {error_msg}. "
                f"Args: {kwargs}. Full Response: {response}"
            )
            return None
        except (BybitRequestError, BybitAPIError) as e:
            logger.exception(
                f"[{endpoint_name}] Pybit specific error during API call. "
                f"Args: {kwargs}. Error: {e}"
            )
            return None
        except Exception as e:
            logger.exception(
                f"[{endpoint_name}] Unexpected exception during API call. "
                f"Args: {kwargs}. Error: {e}"
            )
            return None

    def place_order(
        self,
        category: str,
        symbol: str,
        side: str,
        order_type: str,
        qty: str,
        price: str | None = None,
        **kwargs,
    ) -> dict[str, Any] | None:
        """Places a new order on Bybit.

        :param category: The product type (e.g., "spot", "linear", "inverse", "option").
        :param symbol: The trading symbol (e.g., "BTCUSDT").
        :param side: The order direction ("Buy" or "Sell").
        :param order_type: The order type ("Limit" or "Market").
        :param qty: The quantity to buy or sell (as a string).
        :param price: Optional. The price for Limit orders (as a string). Required for Limit order.
        :param kwargs: Additional optional parameters (e.g., `timeInForce`, `orderLinkId`, `takeProfit`, `stopLoss`).
        :return: A dictionary containing the order placement response (e.g., orderId, orderLinkId) or None on failure.
        """
        # Input validation
        if not all(
            isinstance(arg, str) and arg
            for arg in [category, symbol, side, order_type, qty]
        ):
            logger.error(
                "Invalid or empty string provided for one of the required parameters: category, symbol, side, order_type, qty."
            )
            return None
        try:
            float(qty)  # Check if qty is convertible to float
            if price is not None:
                float(price)  # Check if price is convertible to float
        except ValueError:
            logger.error(
                f"Invalid numerical format for qty ('{qty}') or price ('{price}')."
            )
            return None

        if order_type == "Limit" and not price:
            logger.error("Price is required for Limit orders.")
            return None
        if order_type == "Market" and price:
            logger.warning("Price is ignored for Market orders but was provided.")

        params = {
            "category": category,
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": qty,
        }
        if price:  # Only add price if it's provided (and valid for Limit order type)
            params["price"] = price
        params.update(kwargs)  # Add any additional kwargs

        return self._make_request("place_order", "Place Order", **params)

    def amend_order(
        self,
        category: str,
        symbol: str,
        order_id: str | None = None,
        order_link_id: str | None = None,
        new_qty: str | None = None,
        new_price: str | None = None,
        **kwargs,
    ) -> dict[str, Any] | None:
        """Amends an existing order on Bybit by its `order_id` or `order_link_id`.
        At least one of `new_qty` or `new_price` must be provided.

        :param category: The product type.
        :param symbol: The trading symbol.
        :param order_id: Optional. The exchange-generated order ID of the order to amend.
        :param order_link_id: Optional. Your client-generated order ID of the order to amend.
        :param new_qty: Optional. The new quantity for the order (as a string).
        :param new_price: Optional. The new price for the order (as a string).
        :param kwargs: Additional optional parameters.
        :return: A dictionary containing the order amendment response or None on failure.
        """
        # Input validation
        if not all(isinstance(arg, str) and arg for arg in [category, symbol]):
            logger.error("Invalid or empty string provided for category or symbol.")
            return None
        if not (order_id or order_link_id):
            logger.error(
                "Either 'order_id' or 'order_link_id' must be provided to amend an order."
            )
            return None
        if not (new_qty or new_price):
            logger.error(
                "Either 'new_qty' or 'new_price' must be provided to amend an order."
            )
            return None

        try:
            if new_qty is not None:
                float(new_qty)
            if new_price is not None:
                float(new_price)
        except ValueError:
            logger.error(
                f"Invalid numerical format for new_qty ('{new_qty}') or new_price ('{new_price}')."
            )
            return None

        params = {
            "category": category,
            "symbol": symbol,
        }
        if order_id:
            params["orderId"] = order_id
        if order_link_id:
            params["orderLinkId"] = order_link_id
        if new_qty:
            params["qty"] = new_qty
        if new_price:
            params["price"] = new_price
        params.update(kwargs)

        return self._make_request("amend_order", "Amend Order", **params)

    def cancel_order(
        self,
        category: str,
        symbol: str,
        order_id: str | None = None,
        order_link_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Cancels an active order on Bybit by its `order_id` or `order_link_id`.

        :param category: The product type.
        :param symbol: The trading symbol.
        :param order_id: Optional. The exchange-generated order ID of the order to cancel.
        :param order_link_id: Optional. Your client-generated order ID of the order to cancel.
        :return: A dictionary containing the order cancellation response or None on failure.
        """
        # Input validation
        if not all(isinstance(arg, str) and arg for arg in [category, symbol]):
            logger.error("Invalid or empty string provided for category or symbol.")
            return None
        if not (order_id or order_link_id):
            logger.error(
                "Either 'order_id' or 'order_link_id' must be provided to cancel an order."
            )
            return None

        params = {
            "category": category,
            "symbol": symbol,
        }
        if order_id:
            params["orderId"] = order_id
        if order_link_id:
            params["orderLinkId"] = order_link_id

        return self._make_request("cancel_order", "Cancel Order", **params)

    def cancel_all_orders(
        self, category: str, symbol: str | None = None, **kwargs
    ) -> dict[str, Any] | None:
        """Cancels all active orders for a specific category and optionally a symbol.
        This is a powerful function, use with caution.

        :param category: The product type.
        :param symbol: Optional. The trading symbol. If not provided, cancels all orders in the category.
        :param kwargs: Additional optional parameters.
        :return: A dictionary containing the cancellation response or None on failure.
        """
        # Input validation
        if not isinstance(category, str) or not category:
            logger.error("Invalid or empty string provided for category.")
            return None
        if symbol is not None and (not isinstance(symbol, str) or not symbol):
            logger.error("Invalid 'symbol' provided for cancel_all_orders.")
            return None

        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        params.update(kwargs)
        return self._make_request("cancel_all_orders", "Cancel All Orders", **params)

    def get_open_orders(
        self, category: str, symbol: str | None = None, **kwargs
    ) -> dict[str, Any] | None:
        """Retrieves active open orders for a specific category and optional symbol.

        :param category: The product type.
        :param symbol: Optional. The trading symbol.
        :param kwargs: Additional optional parameters (e.g., `orderId`, `orderLinkId`, `limit`).
        :return: A dictionary containing a list of open orders or None on failure.
        """
        # Input validation
        if not isinstance(category, str) or not category:
            logger.error("Invalid or empty string provided for category.")
            return None
        if symbol is not None and (not isinstance(symbol, str) or not symbol):
            logger.error("Invalid 'symbol' provided for get_open_orders.")
            return None

        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        params.update(kwargs)
        return self._make_request("get_open_orders", "Get Open Orders", **params)

    def get_order_history(
        self, category: str, symbol: str | None = None, **kwargs
    ) -> dict[str, Any] | None:
        """Retrieves historical orders for a specific category and optional symbol.

        :param category: The product type.
        :param symbol: Optional. The trading symbol.
        :param kwargs: Additional optional parameters (e.g., `orderId`, `orderLinkId`, `startTime`, `endTime`, `limit`).
        :return: A dictionary containing a list of historical orders or None on failure.
        """
        # Input validation
        if not isinstance(category, str) or not category:
            logger.error("Invalid or empty string provided for category.")
            return None
        if symbol is not None and (not isinstance(symbol, str) or not symbol):
            logger.error("Invalid 'symbol' provided for get_order_history.")
            return None

        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        params.update(kwargs)
        return self._make_request("get_order_history", "Get Order History", **params)

    def get_positions(
        self, category: str, symbol: str | None = None, **kwargs
    ) -> dict[str, Any] | None:
        """Retrieves current positions for a specific category and optional symbol.

        :param category: The product type.
        :param symbol: Optional. The trading symbol.
        :param kwargs: Additional optional parameters (e.g., `settleCoin`, `limit`).
        :return: A dictionary containing a list of positions or None on failure.
        """
        # Input validation
        if not isinstance(category, str) or not category:
            logger.error("Invalid or empty string provided for category.")
            return None
        if symbol is not None and (not isinstance(symbol, str) or not symbol):
            logger.error("Invalid 'symbol' provided for get_positions.")
            return None

        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        params.update(kwargs)
        return self._make_request("get_positions", "Get Positions", **params)

    def set_leverage(
        self, category: str, symbol: str, buy_leverage: str, sell_leverage: str
    ) -> dict[str, Any] | None:
        """Sets leverage for a specific symbol.

        :param category: The product type.
        :param symbol: The trading symbol.
        :param buy_leverage: The leverage for the buy side (as a string).
        :param sell_leverage: The leverage for the sell side (as a string).
        :return: A dictionary containing the response indicating success or failure.
        """
        # Input validation
        if not all(
            isinstance(arg, str) and arg
            for arg in [category, symbol, buy_leverage, sell_leverage]
        ):
            logger.error(
                "Invalid or empty string provided for category, symbol, buy_leverage, or sell_leverage."
            )
            return None
        try:
            float(buy_leverage)
            float(sell_leverage)
        except ValueError:
            logger.error(
                f"Invalid numerical format for buy_leverage ('{buy_leverage}') or sell_leverage ('{sell_leverage}')."
            )
            return None

        params = {
            "category": category,
            "symbol": symbol,
            "buyLeverage": buy_leverage,
            "sellLeverage": sell_leverage,
        }
        return self._make_request("set_leverage", "Set Leverage", **params)

    def set_trading_stop(
        self, category: str, symbol: str, **kwargs
    ) -> dict[str, Any] | None:
        """Sets or modifies take profit, stop loss, and/or trailing stop for a position.

        :param category: The product type.
        :param symbol: The trading symbol.
        :param kwargs: Parameters like `tpSlMode`, `takeProfit`, `stopLoss`, `trailingStop`, `activePrice`, `tpslLimitPrice`, `positionIdx`.
                       Note: `tpSlMode` can be "Full" or "Partial".
        :return: A dictionary containing the response indicating success or failure.
        """
        # Input validation
        if not all(isinstance(arg, str) and arg for arg in [category, symbol]):
            logger.error("Invalid or empty string provided for category or symbol.")
            return None

        params = {
            "category": category,
            "symbol": symbol,
        }
        params.update(kwargs)
        return self._make_request("set_trading_stop", "Set Trading Stop", **params)

    def switch_position_mode(self, category: str, mode: str) -> dict[str, Any] | None:
        """Switches the position mode (e.g., One-Way or Hedge Mode) for a given category.
        Mode '0' for One-Way Mode, '3' for Hedge Mode.
        This operation is usually performed once per category.

        :param category: The product type.
        :param mode: The desired position mode ("0" for One-Way, "3" for Hedge Mode).
        :return: A dictionary containing the response indicating success or failure.
        """
        # Input validation
        if not all(isinstance(arg, str) and arg for arg in [category, mode]):
            logger.error("Invalid or empty string provided for category or mode.")
            return None
        if mode not in ["0", "3"]:
            logger.error(
                f"Invalid 'mode' for switch_position_mode. Expected '0' (One-Way) or '3' (Hedge Mode), got '{mode}'."
            )
            return None

        params = {"category": category, "mode": mode}
        return self._make_request(
            "switch_position_mode", "Switch Position Mode", **params
        )


# Example Usage
if __name__ == "__main__":
    # IMPORTANT: Replace with your actual API key and secret.
    # For security, consider using environment variables (e.g., os.getenv("BYBIT_API_KEY")).
    # Set USE_TESTNET to False for production (mainnet).
    API_KEY = "YOUR_API_KEY"
    API_SECRET = "YOUR_API_SECRET"
    USE_TESTNET = True

    if API_KEY == "YOUR_API_KEY" or API_SECRET == "YOUR_API_SECRET":
        logger.error(
            "Please replace YOUR_API_KEY and YOUR_API_SECRET with your actual credentials in bybit_trade_helper.py example."
        )
        # For demonstration, we'll proceed but expect API calls to fail.
        # exit()

    trade_helper = BybitTradeHelper(API_KEY, API_SECRET, testnet=USE_TESTNET)

    SYMBOL = "BTCUSDT"
    CATEGORY = "linear"

    # --- Position Management ---
    print(f"\n--- Getting Positions for {SYMBOL} ---")
    positions = trade_helper.get_positions(category=CATEGORY, symbol=SYMBOL)
    if positions and positions.get("list"):
        for pos in positions["list"]:
            print(
                f"  Symbol: {pos.get('symbol')}, Side: {pos.get('side')}, Size: {pos.get('size')}, PnL: {pos.get('unrealisedPnl')}"
            )
    else:
        print(f"  No open positions for {SYMBOL} or failed to retrieve.")

    print(f"\n--- Setting Leverage for {SYMBOL} to 10x (Buy) and 10x (Sell) ---")
    set_leverage_response = trade_helper.set_leverage(
        category=CATEGORY, symbol=SYMBOL, buy_leverage="10", sell_leverage="10"
    )
    if set_leverage_response:
        print(f"  Leverage set response: {set_leverage_response}")
    else:
        print("  Failed to set leverage.")

    # --- Order Management ---
    # Fetch current ticker to get a realistic price for limit orders
    from pybit.unified_trading import (
        HTTP as MarketHTTP,  # Use a separate HTTP session for market data if needed
    )

    market_session = MarketHTTP(testnet=USE_TESTNET)
    ticker_response = market_session.get_tickers(category=CATEGORY, symbol=SYMBOL)
    current_price = None
    if (
        ticker_response
        and ticker_response["retCode"] == 0
        and ticker_response["result"]["list"]
    ):
        current_price = float(ticker_response["result"]["list"][0]["lastPrice"])
        print(f"\nCurrent market price for {SYMBOL}: {current_price}")
    else:
        logger.warning(
            f"Could not fetch current market price for {SYMBOL}. Using a placeholder price."
        )
        current_price = 40000.0  # Fallback placeholder

    buy_price = str(
        round(current_price * 0.99, 1)
    )  # Place a buy limit order slightly below market
    sell_price = str(
        round(current_price * 1.01, 1)
    )  # Place a sell limit order slightly above market

    print(f"\n--- Placing a BUY Limit Order for {SYMBOL} at {buy_price} ---")
    client_order_id = f"test-buy-{int(time.time())}"  # Unique client order ID
    place_order_response = trade_helper.place_order(
        category=CATEGORY,
        symbol=SYMBOL,
        side="Buy",
        order_type="Limit",
        qty="0.001",
        price=buy_price,
        timeInForce="GTC",
        orderLinkId=client_order_id,
    )
    order_id = None
    if place_order_response:
        order_id = place_order_response.get("orderId")
        print(
            f"  Order placed. Order ID: {order_id}, Client Order ID: {client_order_id}"
        )
    else:
        print("  Failed to place order.")

    if order_id:
        print(
            f"\n--- Amending the Order {order_id} to new price {float(buy_price) * 1.005!s} ---"
        )
        amend_order_response = trade_helper.amend_order(
            category=CATEGORY,
            symbol=SYMBOL,
            order_id=order_id,
            new_price=str(
                round(float(buy_price) * 1.005, 1)
            ),  # New price, adjust as needed
        )
        if amend_order_response:
            print(f"  Order amended: {amend_order_response}")
        else:
            print("  Failed to amend order.")

        print(f"\n--- Cancelling the Order {order_id} ---")
        cancel_order_response = trade_helper.cancel_order(
            category=CATEGORY, symbol=SYMBOL, order_id=order_id
        )
        if cancel_order_response:
            print(f"  Order cancelled: {cancel_order_response}")
        else:
            print("  Failed to cancel order.")

    # Placing another order with orderLinkId for cancellation demonstration
    print(
        f"\n--- Placing a SELL Limit Order with Client ID for {SYMBOL} at {sell_price} ---"
    )
    client_order_id_sell = f"test-sell-{int(time.time())}"
    place_sell_order_response = trade_helper.place_order(
        category=CATEGORY,
        symbol=SYMBOL,
        side="Sell",
        order_type="Limit",
        qty="0.001",
        price=sell_price,  # Example price, adjust as needed
        timeInForce="GTC",
        orderLinkId=client_order_id_sell,
    )
    if place_sell_order_response:
        print(
            f"  Sell order placed. Order ID: {place_sell_order_response.get('orderId')}, Client Order ID: {client_order_id_sell}"
        )
        print(
            f"\n--- Cancelling the Sell Order using Client Order ID {client_order_id_sell} ---"
        )
        cancel_by_client_id_response = trade_helper.cancel_order(
            category=CATEGORY, symbol=SYMBOL, order_link_id=client_order_id_sell
        )
        if cancel_by_client_id_response:
            print(
                f"  Sell order cancelled by client ID: {cancel_by_client_id_response}"
            )
        else:
            print("  Failed to cancel sell order by client ID.")

    print(f"\n--- Getting Open Orders for {SYMBOL} ---")
    open_orders = trade_helper.get_open_orders(category=CATEGORY, symbol=SYMBOL)
    if open_orders and open_orders.get("list"):
        for order in open_orders["list"]:
            print(
                f"  Order ID: {order.get('orderId')}, Side: {order.get('side')}, Price: {order.get('price')}, Qty: {order.get('qty')}, Status: {order.get('orderStatus')}"
            )
    else:
        print(f"  No open orders for {SYMBOL} or failed to retrieve.")

    print(f"\n--- Getting Order History for {SYMBOL} (last 2 records) ---")
    order_history = trade_helper.get_order_history(
        category=CATEGORY, symbol=SYMBOL, limit=2
    )
    if order_history and order_history.get("list"):
        for order in order_history["list"]:
            print(
                f"  Order ID: {order.get('orderId')}, Side: {order.get('side')}, Price: {order.get('price')}, Status: {order.get('orderStatus')}, Created: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(int(order.get('createdTime')) / 1000))}"
            )
    else:
        print(f"  No order history for {SYMBOL} or failed to retrieve.")

    print(f"\n--- Switching Position Mode for {CATEGORY} to One-Way ('0') ---")
    # This might fail if you already have positions in Hedge Mode or vice-versa
    switch_mode_response = trade_helper.switch_position_mode(
        category=CATEGORY, mode="0"
    )
    if switch_mode_response:
        print(f"  Switch position mode response: {switch_mode_response}")
    else:
        print(
            "  Failed to switch position mode (may already be in target mode or have open positions)."
        )
