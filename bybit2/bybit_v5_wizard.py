import hashlib
import hmac
import json
import logging
import threading
import time

import requests
import websocket
from colorama import Fore
from colorama import Style
from colorama import init

# Initialize Colorama for vibrant terminal output
init()

# Setup logging to Termux home directory
logging.basicConfig(
    filename="/data/data/com.termux/files/home/.bybit_logs.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


class BybitV5Wizard:
    """A mystical class to wield Bybit's V5 API for trading sorcery."""

    def __init__(
        self, config_path: str = "/data/data/com.termux/files/home/.bybit_config"
    ):
        """Initialize the Bybit V5 Wizard with sacred credentials from config file.

        Args:
            config_path (str): Path to JSON config file with api_key, api_secret, and testnet flag.

        """
        try:
            with open(config_path) as f:
                config = json.load(f)
                self.api_key = config["api_key"]
                self.api_secret = config["api_secret"]
                self.testnet = config.get("testnet", False)
        except Exception as e:
            logging.error(f"Failed to load config: {e!s}")
            raise ValueError(
                Fore.RED + f"# Failed to load config: {e!s}" + Style.RESET_ALL
            )

        self.base_url = (
            "https://api-testnet.bybit.com" if self.testnet else "https://api.bybit.com"
        )
        self.ws_url = (
            "wss://stream-testnet.bybit.com/v5/private"
            if self.testnet
            else "wss://stream.bybit.com/v5/private"
        )
        self.ws_public_url = (
            "wss://stream-testnet.bybit.com/v5/public/linear"
            if self.testnet
            else "wss://stream.bybit.com/v5/public/linear"
        )
        self.ws_trade_url = (
            "wss://stream-testnet.bybit.com/v5/trade"
            if self.testnet
            else "wss://stream.bybit.com/v5/trade"
        )
        self.session = requests.Session()
        self.ws = None
        self.ws_public = None
        self.ws_trade = None
        self.ws_thread = None
        self.ws_public_thread = None
        self.ws_trade_thread = None
        self.lock = threading.Lock()
        self.positions = {}  # Track positions: {symbol: {entry_price, break_even_enabled, tsl_enabled, tsl_distance, profit_target, profit_action, close_percentage}}
        self.retry_attempts = 3
        self.retry_delay = 1
        self.rate_limit = 120 / 60  # 120 requests per minute
        self.last_request_time = 0
        print(
            Fore.CYAN
            + "# Bybit V5 Wizard awakened with ethereal power..."
            + Style.RESET_ALL
        )

    def _generate_signature(self, params: dict, timestamp: str) -> str:
        """Forge an HMAC SHA256 signature for the API's sacred gate."""
        param_str = (
            timestamp
            + self.api_key
            + "5000"
            + json.dumps(params, separators=(",", ":"))
        )
        return hmac.new(
            self.api_secret.encode("utf-8"), param_str.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def _enforce_rate_limit(self):
        """Ensure requests respect Bybit's rate limits."""
        with self.lock:
            elapsed = time.time() - self.last_request_time
            if elapsed < (1 / self.rate_limit):
                time.sleep((1 / self.rate_limit) - elapsed)
            self.last_request_time = time.time()

    def _send_request(
        self, method: str, endpoint: str, params: dict = None, retries: int = 3
    ) -> dict:
        """Cast an HTTP spell to commune with Bybit's API with retry logic and rate limiting.

        Args:
            method (str): HTTP method (GET/POST).
            endpoint (str): API endpoint path.
            params (Dict): Request parameters.
            retries (int): Number of retry attempts.

        Returns:
            Dict: API response result or empty dict on failure.

        """
        if params is None:
            params = {}
        self._enforce_rate_limit()
        for attempt in range(retries):
            timestamp = str(int(time.time() * 1000))
            headers = {
                "X-BAPI-API-KEY": self.api_key,
                "X-BAPI-TIMESTAMP": timestamp,
                "X-BAPI-RECV-WINDOW": "5000",
                "X-BAPI-SIGN": self._generate_signature(params, timestamp),
                "Content-Type": "application/json",
            }
            url = f"{self.base_url}{endpoint}"
            try:
                if method == "GET":
                    response = self.session.get(url, headers=headers, params=params)
                elif method == "POST":
                    response = self.session.post(url, headers=headers, json=params)
                else:
                    raise ValueError(
                        Fore.RED + "Invalid method invoked!" + Style.RESET_ALL
                    )
                response.raise_for_status()
                result = response.json()
                logging.info(
                    f"Request: {method} {endpoint} - Params: {params} - Response: {result}"
                )
                if result.get("retCode") == 0:
                    print(
                        Fore.GREEN
                        + f"# Spell cast successfully: {endpoint}"
                        + Style.RESET_ALL
                    )
                    return result.get("result", {})
                print(
                    Fore.RED
                    + f"# Spell failed: {result.get('retMsg')}"
                    + Style.RESET_ALL
                )
                logging.error(
                    f"API error: {result.get('retMsg')} for endpoint {endpoint}"
                )
                return {}
            except Exception as e:
                print(
                    Fore.RED
                    + f"# Attempt {attempt + 1}/{retries}: The ether rejects the call: {e!s}"
                    + Style.RESET_ALL
                )
                logging.error(
                    f"Request failed: {e!s} for endpoint {endpoint} (attempt {attempt + 1})"
                )
                if attempt < retries - 1:
                    time.sleep(self.retry_delay * (2**attempt))  # Exponential backoff
                else:
                    return {}

    # --- Market Data Endpoints ---

    def get_kline(
        self,
        category: str,
        symbol: str,
        interval: str,
        start: int | None = None,
        end: int | None = None,
        limit: int = 200,
    ) -> dict:
        """Retrieve kline/candlestick data.

        Endpoint: GET /v5/market/kline
        """
        endpoint = "/v5/market/kline"
        params = {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        print(
            Fore.CYAN
            + f"# Fetching kline for {symbol} ({interval})..."
            + Style.RESET_ALL
        )
        return self._send_request("GET", endpoint, params)

    def get_mark_price_kline(
        self,
        category: str,
        symbol: str,
        interval: str,
        start: int | None = None,
        end: int | None = None,
        limit: int = 200,
    ) -> dict:
        """Retrieve mark price kline data.

        Endpoint: GET /v5/market/mark-price-kline
        """
        endpoint = "/v5/market/mark-price-kline"
        params = {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        print(
            Fore.CYAN
            + f"# Fetching mark price kline for {symbol} ({interval})..."
            + Style.RESET_ALL
        )
        return self._send_request("GET", endpoint, params)

    def get_index_price_kline(
        self,
        category: str,
        symbol: str,
        interval: str,
        start: int | None = None,
        end: int | None = None,
        limit: int = 200,
    ) -> dict:
        """Retrieve index price kline data.

        Endpoint: GET /v5/market/index-price-kline
        """
        endpoint = "/v5/market/index-price-kline"
        params = {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        print(
            Fore.CYAN
            + f"# Fetching index price kline for {symbol} ({interval})..."
            + Style.RESET_ALL
        )
        return self._send_request("GET", endpoint, params)

    def get_premium_index_price_kline(
        self,
        category: str,
        symbol: str,
        interval: str,
        start: int | None = None,
        end: int | None = None,
        limit: int = 200,
    ) -> dict:
        """Retrieve premium index price kline data.

        Endpoint: GET /v5/market/premium-index-price-kline
        """
        endpoint = "/v5/market/premium-index-price-kline"
        params = {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        print(
            Fore.CYAN
            + f"# Fetching premium index price kline for {symbol} ({interval})..."
            + Style.RESET_ALL
        )
        return self._send_request("GET", endpoint, params)

    def get_instruments_info(
        self,
        category: str,
        symbol: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> dict:
        """Retrieve instrument information.

        Endpoint: GET /v5/market/instruments-info
        """
        endpoint = "/v5/market/instruments-info"
        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        if status:
            params["status"] = status
        if limit:
            params["limit"] = limit
        print(
            Fore.CYAN
            + f"# Fetching instruments info for {category}..."
            + Style.RESET_ALL
        )
        return self._send_request("GET", endpoint, params)

    def get_orderbook(self, category: str, symbol: str, limit: int = 50) -> dict:
        """Retrieve order book data.

        Endpoint: GET /v5/market/orderbook
        """
        endpoint = "/v5/market/orderbook"
        params = {"category": category, "symbol": symbol, "limit": limit}
        print(Fore.CYAN + f"# Fetching order book for {symbol}..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_tickers(
        self,
        category: str,
        symbol: str | None = None,
        base_coin: str | None = None,
        exp_date: str | None = None,
    ) -> dict:
        """Retrieve ticker information.

        Endpoint: GET /v5/market/tickers
        """
        endpoint = "/v5/market/tickers"
        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        if base_coin:
            params["baseCoin"] = base_coin
        if exp_date:
            params["expDate"] = exp_date
        print(Fore.CYAN + f"# Fetching tickers for {category}..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_funding_rate(self, category: str, symbol: str) -> dict:
        """Retrieve funding rate history.

        Endpoint: GET /v5/market/funding/history
        """
        endpoint = "/v5/market/funding/history"
        params = {"category": category, "symbol": symbol}
        print(Fore.CYAN + f"# Fetching funding rate for {symbol}..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_public_trade(
        self,
        category: str,
        symbol: str,
        base_coin: str | None = None,
        option_type: str | None = None,
        limit: int = 500,
    ) -> dict:
        """Retrieve recent public trades.

        Endpoint: GET /v5/market/recent-trade
        """
        endpoint = "/v5/market/recent-trade"
        params = {"category": category, "symbol": symbol, "limit": limit}
        if base_coin:
            params["baseCoin"] = base_coin
        if option_type:
            params["optionType"] = option_type
        print(Fore.CYAN + f"# Fetching recent trades for {symbol}..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_open_interest(
        self,
        category: str,
        symbol: str,
        interval: str = "5min",
        start: int | None = None,
        end: int | None = None,
        limit: int = 200,
    ) -> dict:
        """Retrieve open interest data.

        Endpoint: GET /v5/market/open-interest
        """
        endpoint = "/v5/market/open-interest"
        params = {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        print(Fore.CYAN + f"# Fetching open interest for {symbol}..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_historical_volatility(
        self,
        category: str = "option",
        base_coin: str | None = None,
        period: int | None = None,
    ) -> dict:
        """Retrieve historical volatility data.

        Endpoint: GET /v5/market/historical-volatility
        """
        endpoint = "/v5/market/historical-volatility"
        params = {"category": category}
        if base_coin:
            params["baseCoin"] = base_coin
        if period:
            params["period"] = period
        print(
            Fore.CYAN
            + f"# Fetching historical volatility for {category}..."
            + Style.RESET_ALL
        )
        return self._send_request("GET", endpoint, params)

    def get_insurance(self, coin: str | None = None) -> dict:
        """Retrieve insurance fund data.

        Endpoint: GET /v5/market/insurance
        """
        endpoint = "/v5/market/insurance"
        params = {}
        if coin:
            params["coin"] = coin
        print(Fore.CYAN + "# Fetching insurance fund data..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_risk_limit(self, category: str, symbol: str | None = None) -> dict:
        """Retrieve risk limit data.

        Endpoint: GET /v5/market/risk-limit
        """
        endpoint = "/v5/market/risk-limit"
        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        print(Fore.CYAN + f"# Fetching risk limit for {category}..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_delivery_price(
        self,
        category: str,
        symbol: str | None = None,
        base_coin: str | None = None,
        limit: int = 200,
    ) -> dict:
        """Retrieve delivery price data.

        Endpoint: GET /v5/market/delivery-price
        """
        endpoint = "/v5/market/delivery-price"
        params = {"category": category, "limit": limit}
        if symbol:
            params["symbol"] = symbol
        if base_coin:
            params["baseCoin"] = base_coin
        print(
            Fore.CYAN + f"# Fetching delivery price for {category}..." + Style.RESET_ALL
        )
        return self._send_request("GET", endpoint, params)

    def get_server_time(self) -> dict:
        """Retrieve server time.

        Endpoint: GET /v5/market/time
        """
        endpoint = "/v5/market/time"
        print(Fore.CYAN + "# Fetching server time..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, {})

    # --- Trade Endpoints ---

    def place_market_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        category: str = "linear",
        break_even: bool = False,
        tsl: bool = False,
        tsl_distance: float | None = None,
        profit_target: float | None = None,
    ) -> dict:
        """Summon a market order with optional enchantments.

        Endpoint: POST /v5/order/create
        """
        endpoint = "/v5/order/create"
        params = {
            "category": category,
            "symbol": symbol,
            "side": side.capitalize(),
            "orderType": "Market",
            "qty": str(qty),
        }
        print(
            Fore.CYAN
            + f"# Casting market order for {symbol} ({side})..."
            + Style.RESET_ALL
        )
        result = self._send_request("POST", endpoint, params)
        if result and (break_even or tsl or profit_target):
            self.positions[symbol] = {
                "entry_price": None,
                "break_even_enabled": break_even,
                "tsl_enabled": tsl,
                "tsl_distance": tsl_distance,
                "profit_target": profit_target,
                "profit_action": "partial_close",
                "close_percentage": 50,
            }
        return result

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        category: str = "linear",
        break_even: bool = False,
        tsl: bool = False,
        tsl_distance: float | None = None,
        profit_target: float | None = None,
    ) -> dict:
        """Forge a limit order with precision and optional enchantments.

        Endpoint: POST /v5/order/create
        """
        endpoint = "/v5/order/create"
        params = {
            "category": category,
            "symbol": symbol,
            "side": side.capitalize(),
            "orderType": "Limit",
            "qty": str(qty),
            "price": str(price),
        }
        print(
            Fore.CYAN
            + f"# Forging limit order for {symbol} at {price}..."
            + Style.RESET_ALL
        )
        result = self._send_request("POST", endpoint, params)
        if result and (break_even or tsl or profit_target):
            self.positions[symbol] = {
                "entry_price": None,
                "break_even_enabled": break_even,
                "tsl_enabled": tsl,
                "tsl_distance": tsl_distance,
                "profit_target": profit_target,
                "profit_action": "partial_close",
                "close_percentage": 50,
            }
        return result

    def place_conditional_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        trigger_price: float,
        order_type: str = "Limit",
        price: float | None = None,
        category: str = "linear",
    ) -> dict:
        """Invoke a conditional order, triggered by the market's pulse.

        Endpoint: POST /v5/order/create
        """
        endpoint = "/v5/order/create"
        params = {
            "category": category,
            "symbol": symbol,
            "side": side.capitalize(),
            "orderType": order_type,
            "qty": str(qty),
            "triggerPrice": str(trigger_price),
            "triggerDirection": 1 if side.lower() == "buy" else 2,
        }
        if price:
            params["price"] = str(price)
        print(
            Fore.CYAN
            + f"# Summoning conditional order for {symbol} at trigger {trigger_price}..."
            + Style.RESET_ALL
        )
        return self._send_request("POST", endpoint, params)

    def place_tpsl_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        take_profit: float | None = None,
        stop_loss: float | None = None,
        category: str = "linear",
    ) -> dict:
        """Enchant an order with take-profit and stop-loss wards.

        Endpoint: POST /v5/order/create
        """
        endpoint = "/v5/order/create"
        params = {
            "category": category,
            "symbol": symbol,
            "side": side.capitalize(),
            "orderType": "Market",
            "qty": str(qty),
        }
        if take_profit:
            params["takeProfit"] = str(take_profit)
        if stop_loss:
            params["stopLoss"] = str(stop_loss)
        print(
            Fore.CYAN + f"# Enchanting {symbol} order with TP/SL..." + Style.RESET_ALL
        )
        return self._send_request("POST", endpoint, params)

    def place_batch_orders(
        self, symbol: str, orders: list[dict], category: str = "linear"
    ) -> dict:
        """Unleash a flurry of orders in a single incantation.

        Endpoint: POST /v5/order/create-batch
        """
        endpoint = "/v5/order/create-batch"
        params = {
            "category": category,
            "symbol": symbol,
            "request": [
                {
                    "symbol": symbol,
                    "side": order["side"].capitalize(),
                    "orderType": order.get("orderType", "Market"),
                    "qty": str(order["qty"]),
                    **({"price": str(order["price"])} if order.get("price") else {}),
                    **(
                        {"takeProfit": str(order["takeProfit"])}
                        if order.get("takeProfit")
                        else {}
                    ),
                    **(
                        {"stopLoss": str(order["stopLoss"])}
                        if order.get("stopLoss")
                        else {}
                    ),
                }
                for order in orders
            ],
        }
        print(
            Fore.CYAN
            + f"# Casting {len(orders)} batch orders for {symbol}..."
            + Style.RESET_ALL
        )
        return self._send_request("POST", endpoint, params)

    def amend_order(
        self,
        symbol: str,
        order_id: str,
        category: str = "linear",
        qty: float | None = None,
        price: float | None = None,
        trigger_price: float | None = None,
    ) -> dict:
        """Amend an existing order.

        Endpoint: POST /v5/order/amend
        """
        endpoint = "/v5/order/amend"
        params = {"category": category, "symbol": symbol, "orderId": order_id}
        if qty:
            params["qty"] = str(qty)
        if price:
            params["price"] = str(price)
        if trigger_price:
            params["triggerPrice"] = str(trigger_price)
        print(
            Fore.CYAN + f"# Amending order {order_id} for {symbol}..." + Style.RESET_ALL
        )
        return self._send_request("POST", endpoint, params)

    def amend_batch_orders(
        self, symbol: str, orders: list[dict], category: str = "linear"
    ) -> dict:
        """Amend multiple orders in a single incantation.

        Endpoint: POST /v5/order/amend-batch
        """
        endpoint = "/v5/order/amend-batch"
        params = {
            "category": category,
            "symbol": symbol,
            "request": [
                {
                    "symbol": symbol,
                    "orderId": order["orderId"],
                    **({"qty": str(order["qty"])} if order.get("qty") else {}),
                    **({"price": str(order["price"])} if order.get("price") else {}),
                    **(
                        {"triggerPrice": str(order["triggerPrice"])}
                        if order.get("triggerPrice")
                        else {}
                    ),
                }
                for order in orders
            ],
        }
        print(
            Fore.CYAN
            + f"# Amending {len(orders)} batch orders for {symbol}..."
            + Style.RESET_ALL
        )
        return self._send_request("POST", endpoint, params)

    def cancel_order(
        self, symbol: str, order_id: str, category: str = "linear"
    ) -> dict:
        """Banish an order back to the void.

        Endpoint: POST /v5/order/cancel
        """
        endpoint = "/v5/order/cancel"
        params = {"category": category, "symbol": symbol, "orderId": order_id}
        print(
            Fore.CYAN
            + f"# Banishing order {order_id} for {symbol}..."
            + Style.RESET_ALL
        )
        return self._send_request("POST", endpoint, params)

    def cancel_all_orders(
        self, category: str = "linear", symbol: str | None = None
    ) -> dict:
        """Obliterate all orders in a cataclysmic sweep.

        Endpoint: POST /v5/order/cancel-all
        """
        endpoint = "/v5/order/cancel-all"
        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        print(
            Fore.CYAN
            + f"#发展和# Obliterating all {category} orders..."
            + Style.RESET_ALL
        )
        return self._send_request("POST", endpoint, params)

    def close_position(
        self,
        symbol: str,
        category: str = "linear",
        order_type: str = "Market",
        price: float | None = None,
    ) -> dict:
        """Close a position with market or limit order.

        Endpoint: POST /v5/order/create
        """
        endpoint = "/v5/order/create"
        position = self.get_positions(category, symbol)
        if not position.get("list"):
            print(Fore.RED + f"# No position found for {symbol}!" + Style.RESET_ALL)
            return {}
        pos = position["list"][0]
        side = "Sell" if pos["side"] == "Buy" else "Buy"
        qty = pos["size"]
        params = {
            "category": category,
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": str(qty),
        }
        if price and order_type == "Limit":
            params["price"] = str(price)
        print(
            Fore.CYAN + f"# Closing position for {symbol} ({side})..." + Style.RESET_ALL
        )
        return self._send_request("POST", endpoint, params)

    def get_open_orders(
        self, category: str = "linear", symbol: str | None = None
    ) -> dict:
        """Reveal the active orders lingering in the ether.

        Endpoint: GET /v5/order/realtime
        """
        endpoint = "/v5/order/realtime"
        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        print(Fore.CYAN + f"# Unveiling open {category} orders..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_order_history(
        self, category: str = "linear", symbol: str | None = None, limit: int = 50
    ) -> dict:
        """Seek the chronicles of past trades.

        Endpoint: GET /v5/order/history
        """
        endpoint = "/v5/order/history"
        params = {"category": category, "limit": limit}
        if symbol:
            params["symbol"] = symbol
        print(
            Fore.CYAN + f"# Seeking order history for {category}..." + Style.RESET_ALL
        )
        return self._send_request("GET", endpoint, params)

    # --- Position Endpoints ---

    def get_positions(
        self, category: str = "linear", symbol: str | None = None
    ) -> dict:
        """Summon the spirits of your active positions.

        Endpoint: GET /v5/position/list
        """
        endpoint = "/v5/position/list"
        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        print(Fore.CYAN + f"# Summoning {category} positions..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def set_leverage(
        self,
        symbol: str,
        buy_leverage: float,
        sell_leverage: float,
        category: str = "linear",
    ) -> dict:
        """Adjust the leverage, bending the market's force.

        Endpoint: POST /v5/position/set-leverage
        """
        endpoint = "/v5/position/set-leverage"
        params = {
            "category": category,
            "symbol": symbol,
            "buyLeverage": str(buy_leverage),
            "sellLeverage": str(sell_leverage),
        }
        print(
            Fore.CYAN
            + f"# Bending leverage for {symbol} to {buy_leverage}x..."
            + Style.RESET_ALL
        )
        return self._send_request("POST", endpoint, params)

    def set_trading_stop(
        self,
        symbol: str,
        category: str = "linear",
        take_profit: float | None = None,
        stop_loss: float | None = None,
        trailing_stop: float | None = None,
        active_price: float | None = None,
        tpsl_mode: str = "Full",
    ) -> dict:
        """Enchant a position with protective TP/SL or TSL wards.

        Endpoint: POST /v5/position/trading-stop
        """
        endpoint = "/v5/position/trading-stop"
        params = {"category": category, "symbol": symbol, "tpslMode": tpsl_mode}
        if take_profit:
            params["takeProfit"] = str(take_profit)
        if stop_loss:
            params["stopLoss"] = str(stop_loss)
        if trailing_stop:
            params["trailingStop"] = str(trailing_stop)
        if active_price:
            params["activePrice"] = str(active_price)
        print(
            Fore.CYAN
            + f"# Enchanting {symbol} with TP/SL/TSL wards..."
            + Style.RESET_ALL
        )
        return self._send_request("POST", endpoint, params)

    def set_risk_limit(
        self, symbol: str, risk_id: int, category: str = "linear"
    ) -> dict:
        """Set the risk limit for a position.

        Endpoint: POST /v5/position/set-risk-limit
        """
        endpoint = "/v5/position/set-risk-limit"
        params = {"category": category, "symbol": symbol, "riskId": risk_id}
        print(Fore.CYAN + f"# Setting risk limit for {symbol}..." + Style.RESET_ALL)
        return self._send_request("POST", endpoint, params)

    def switch_position_mode(self, category: str, mode: str = "BothSide") -> dict:
        """Switch position mode (One-Way or Hedge).

        Endpoint: POST /v5/position/switch-mode
        """
        endpoint = "/v5/position/switch-mode"
        params = {"category": category, "mode": mode}
        print(Fore.CYAN + f"# Switching position mode to {mode}..." + Style.RESET_ALL)
        return self._send_request("POST", endpoint, params)

    def set_auto_add_margin(
        self, symbol: str, auto_add_margin: bool, category: str = "linear"
    ) -> dict:
        """Enable or disable auto-add margin.

        Endpoint: POST /v5/position/set-auto-add-margin
        """
        endpoint = "/v5/position/set-auto-add-margin"
        params = {
            "category": category,
            "symbol": symbol,
            "autoAddMargin": 1 if auto_add_margin else 0,
        }
        print(
            Fore.CYAN
            + f"# Setting auto-add margin for {symbol} to {auto_add_margin}..."
            + Style.RESET_ALL
        )
        return self._send_request("POST", endpoint, params)

    # --- Account Endpoints ---

    def get_account_balance(self, account_type: str = "UNIFIED") -> dict:
        """Gaze into the vault of your account's wealth.

        Endpoint: GET /v5/account/wallet-balance
        """
        endpoint = "/v5/account/wallet-balance"
        params = {"accountType": account_type}
        print(Fore.CYAN + "# Peering into the vault of wealth..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_account_info(self) -> dict:
        """Seek the sacred knowledge of your account's state.

        Endpoint: GET /v5/account/info
        """
        endpoint = "/v5/account/info"
        params = {}
        print(Fore.CYAN + "# Seeking account's sacred knowledge..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def set_margin_mode(
        self, symbol: str, mode: str = "ISOLATED", category: str = "linear"
    ) -> dict:
        """Toggle between isolated and cross margin modes.

        Endpoint: POST /v5/account/set-margin-mode
        """
        endpoint = "/v5/account/set-margin-mode"
        params = {"category": category, "symbol": symbol, "marginMode": mode.upper()}
        print(
            Fore.CYAN + f"# Setting {symbol} to {mode} margin mode..." + Style.RESET_ALL
        )
        return self._send_request("POST", endpoint, params)

    def set_collateral_coin(self, coin: str) -> dict:
        """Set collateral coin for the account.

        Endpoint: POST /v5/account/set-collateral
        """
        endpoint = "/v5/account/set-collateral"
        params = {"coin": coin}
        print(Fore.CYAN + f"# Setting collateral coin to {coin}..." + Style.RESET_ALL)
        return self._send_request("POST", endpoint, params)

    def get_collateral_info(self, coin: str | None = None) -> dict:
        """Retrieve collateral information.

        Endpoint: GET /v5/account/collateral-info
        """
        endpoint = "/v5/account/collateral-info"
        params = {}
        if coin:
            params["coin"] = coin
        print(Fore.CYAN + "# Fetching collateral info..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_coin_greeks(self, base_coin: str) -> dict:
        """Retrieve coin Greeks data.

        Endpoint: GET /v5/asset/coin-greeks
        """
        endpoint = "/v5/asset/coin-greeks"
        params = {"baseCoin": base_coin}
        print(Fore.CYAN + f"# Fetching Greeks for {base_coin}..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    # --- Pre-upgrade Endpoints ---

    def get_pre_upgrade_order_history(
        self, category: str, base_coin: str | None = None, limit: int = 50
    ) -> dict:
        """Retrieve pre-upgrade order history.

        Endpoint: GET /v5/pre-upgrade/order/history
        """
        endpoint = "/v5/pre-upgrade/order/history"
        params = {"category": category, "limit": limit}
        if base_coin:
            params["baseCoin"] = base_coin
        print(
            Fore.CYAN
            + f"# Fetching pre-upgrade order history for {category}..."
            + Style.RESET_ALL
        )
        return self._send_request("GET", endpoint, params)

    def get_pre_upgrade_trade_history(
        self, category: str, base_coin: str | None = None, limit: int = 50
    ) -> dict:
        """Retrieve pre-upgrade trade history.

        Endpoint: GET /v5/pre-upgrade/execution/list
        """
        endpoint = "/v5/pre-upgrade/execution/list"
        params = {"category": category, "limit": limit}
        if base_coin:
            params["baseCoin"] = base_coin
        print(
            Fore.CYAN
            + f"# Fetching pre-upgrade trade history for {category}..."
            + Style.RESET_ALL
        )
        return self._send_request("GET", endpoint, params)

    def get_pre_upgrade_closed_pnl(
        self,
        category: str,
        symbol: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 50,
    ) -> dict:
        """Retrieve pre-upgrade closed PNL.

        Endpoint: GET /v5/pre-upgrade/position/closed-pnl
        """
        endpoint = "/v5/pre-upgrade/position/closed-pnl"
        params = {"category": category, "limit": limit}
        if symbol:
            params["symbol"] = symbol
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        print(
            Fore.CYAN
            + f"# Fetching pre-upgrade closed PNL for {category}..."
            + Style.RESET_ALL
        )
        return self._send_request("GET", endpoint, params)

    def get_pre_upgrade_transaction_log(
        self,
        category: str | None = None,
        base_coin: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 50,
    ) -> dict:
        """Retrieve pre-upgrade transaction log.

        Endpoint: GET /v5/pre-upgrade/account/transaction-log
        """
        endpoint = "/v5/pre-upgrade/account/transaction-log"
        params = {"limit": limit}
        if category:
            params["category"] = category
        if base_coin:
            params["baseCoin"] = base_coin
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        print(Fore.CYAN + "# Fetching pre-upgrade transaction log..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_pre_upgrade_option_delivery_record(
        self,
        category: str = "option",
        symbol: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict:
        """Retrieve pre-upgrade option delivery record.

        Endpoint: GET /v5/pre-upgrade/option/delivery-record
        """
        endpoint = "/v5/pre-upgrade/option/delivery-record"
        params = {"category": category, "limit": limit}
        if symbol:
            params["symbol"] = symbol
        if cursor:
            params["cursor"] = cursor
        print(
            Fore.CYAN
            + "# Fetching pre-upgrade option delivery record..."
            + Style.RESET_ALL
        )
        return self._send_request("GET", endpoint, params)

    def get_pre_upgrade_settlement_record(
        self,
        category: str,
        symbol: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict:
        """Retrieve pre-upgrade settlement record.

        Endpoint: GET /v5/pre-upgrade/spot/settlement-record
        """
        endpoint = "/v5/pre-upgrade/spot/settlement-record"
        params = {"category": category, "limit": limit}
        if symbol:
            params["symbol"] = symbol
        if cursor:
            params["cursor"] = cursor
        print(
            Fore.CYAN + "# Fetching pre-upgrade settlement record..." + Style.RESET_ALL
        )
        return self._send_request("GET", endpoint, params)

    def get_pre_upgrade_account_info(self) -> dict:
        """Retrieve pre-upgrade account information.

        Endpoint: GET /v5/pre-upgrade/account/info
        """
        endpoint = "/v5/pre-upgrade/account/info"
        params = {}
        print(Fore.CYAN + "# Fetching pre-upgrade account info..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    # --- Asset Endpoints ---

    def get_coin_exchange_records(
        self,
        from_coin: str | None = None,
        to_coin: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict:
        """Retrieve coin exchange records.

        Endpoint: GET /v5/asset/exchange/order-record
        """
        endpoint = "/v5/asset/exchange/order-record"
        params = {"limit": limit}
        if from_coin:
            params["fromCoin"] = from_coin
        if to_coin:
            params["toCoin"] = to_coin
        if cursor:
            params["cursor"] = cursor
        print(Fore.CYAN + "# Fetching coin exchange records..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_delivery_record(
        self,
        category: str,
        symbol: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict:
        """Retrieve delivery record.

        Endpoint: GET /v5/asset/delivery-record
        """
        endpoint = "/v5/asset/delivery-record"
        params = {"category": category, "limit": limit}
        if symbol:
            params["symbol"] = symbol
        if cursor:
            params["cursor"] = cursor
        print(
            Fore.CYAN
            + f"# Fetching delivery record for {category}..."
            + Style.RESET_ALL
        )
        return self._send_request("GET", endpoint, params)

    def get_usdc_settlement(
        self, category: str = "option", cursor: str | None = None
    ) -> dict:
        """Retrieve USDC settlement history.

        Endpoint: GET /v5/asset/settlement-record
        """
        endpoint = "/v5/asset/settlement-record"
        params = {"category": category}
        if cursor:
            params["cursor"] = cursor
        print(Fore.CYAN + "# Fetching USDC settlement history..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_asset_info(self, account_type: str, coin: str | None = None) -> dict:
        """Retrieve asset information.

        Endpoint: GET /v5/asset/transfer/query-asset-info
        """
        endpoint = "/v5/asset/transfer/query-asset-info"
        params = {"accountType": account_type}
        if coin:
            params["coin"] = coin
        print(
            Fore.CYAN + f"# Fetching asset info for {account_type}..." + Style.RESET_ALL
        )
        return self._send_request("GET", endpoint, params)

    def get_all_coins_balance(
        self,
        account_type: str,
        member_id: str | None = None,
        coin: str | None = None,
        with_bonus: int | None = None,
    ) -> dict:
        """Retrieve balance of all coins.

        Endpoint: GET /v5/asset/transfer/query-account-coins-balance
        """
        endpoint = "/v5/asset/transfer/query-account-coins-balance"
        params = {"accountType": account_type}
        if member_id:
            params["memberId"] = member_id
        if coin:
            params["coin"] = coin
        if with_bonus is not None:
            params["withBonus"] = with_bonus
        print(
            Fore.CYAN
            + f"# Fetching all coins balance for {account_type}..."
            + Style.RESET_ALL
        )
        return self._send_request("GET", endpoint, params)

    def get_single_coin_balance(
        self,
        account_type: str,
        member_id: str | None = None,
        coin: str | None = None,
        with_bonus: int | None = None,
    ) -> dict:
        """Retrieve balance of a single coin.

        Endpoint: GET /v5/asset/transfer/query-account-coin-balance
        """
        endpoint = "/v5/asset/transfer/query-account-coin-balance"
        params = {"accountType": account_type}
        if member_id:
            params["memberId"] = member_id
        if coin:
            params["coin"] = coin
        if with_bonus is not None:
            params["withBonus"] = with_bonus
        print(
            Fore.CYAN
            + f"# Fetching single coin balance for {account_type}..."
            + Style.RESET_ALL
        )
        return self._send_request("GET", endpoint, params)

    def get_transferable_coin(
        self, from_account_type: str, to_account_type: str
    ) -> dict:
        """Retrieve transferable coins between account types.

        Endpoint: GET /v5/asset/transfer/query-transfer-coin-list
        """
        endpoint = "/v5/asset/transfer/query-transfer-coin-list"
        params = {
            "fromAccountType": from_account_type,
            "toAccountType": to_account_type,
        }
        print(
            Fore.CYAN
            + f"# FetchSix transferable coins from {from_account_type} to {to_account_type}..."
            + Style.RESET_ALL
        )
        return self._send_request("GET", endpoint, params)

    def create_internal_transfer(
        self,
        transfer_id: str,
        coin: str,
        amount: str,
        from_account_type: str,
        to_account_type: str,
    ) -> dict:
        """Create an internal transfer.

        Endpoint: POST /v5/asset/transfer/inter-transfer
        """
        endpoint = "/v5/asset/transfer/inter-transfer"
        params = {
            "transferId": transfer_id,
            "coin": coin,
            "amount": amount,
            "fromAccountType": from_account_type,
            "toAccountType": to_account_type,
        }
        print(
            Fore.CYAN
            + f"# Creating internal transfer of {amount} {coin}..."
            + Style.RESET_ALL
        )
        return self._send_request("POST", endpoint, params)

    def get_internal_transfer_records(
        self,
        transfer_id: str | None = None,
        coin: str | None = None,
        status: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        direction: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict:
        """Retrieve internal transfer records.

        Endpoint: GET /v5/asset/transfer/query-inter-transfer-list
        """
        endpoint = "/v5/asset/transfer/query-inter-transfer-list"
        params = {"limit": limit}
        if transfer_id:
            params["transferId"] = transfer_id
        if coin:
            params["coin"] = coin
        if status:
            params["status"] = status
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        if direction:
            params["direction"] = direction
        if cursor:
            params["cursor"] = cursor
        print(Fore.CYAN + "# Fetching internal transfer records..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_sub_account_transfer_records(
        self,
        transfer_id: str | None = None,
        coin: str | None = None,
        status: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        direction: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict:
        """Retrieve sub-account transfer records.

        Endpoint: GET /v5/asset/transfer/query-sub-member-transfer-list
        """
        endpoint = "/v5/asset/transfer/query-sub-member-transfer-list"
        params = {"limit": limit}
        if transfer_id:
            params["transferId"] = transfer_id
        if coin:
            params["coin"] = coin
        if status:
            params["status"] = status
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        if direction:
            params["direction"] = direction
        if cursor:
            params["cursor"] = cursor
        print(
            Fore.CYAN + "# Fetching sub-account transfer records..." + Style.RESET_ALL
        )
        return self._send_request("GET", endpoint, params)

    def get_universal_transfer_records(
        self,
        transfer_id: str | None = None,
        coin: str | None = None,
        status: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict:
        """Retrieve universal transfer records.

        Endpoint: GET /v5/asset/transfer/query-universal-transfer-list
        """
        endpoint = "/v5/asset/transfer/query-universal-transfer-list"
        params = {"limit": limit}
        if transfer_id:
            params["transferId"] = transfer_id
        if coin:
            params["coin"] = coin
        if status:
            params["status"] = status
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        if cursor:
            params["cursor"] = cursor
        print(Fore.CYAN + "# Fetching universal transfer records..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def create_universal_transfer(
        self,
        transfer_id: str,
        coin: str,
        amount: str,
        from_member_id: str,
        to_member_id: str,
        from_account_type: str,
        to_account_type: str,
    ) -> dict:
        """Create a universal transfer.

        Endpoint: POST /v5/asset/transfer/universal-transfer
        """
        endpoint = "/v5/asset/transfer/universal-transfer"
        params = {
            "transferId": transfer_id,
            "coin": coin,
            "amount": amount,
            "fromMemberId": from_member_id,
            "toMemberId": to_member_id,
            "fromAccountType": from_account_type,
            "toAccountType": to_account_type,
        }
        print(
            Fore.CYAN
            + f"# Creating universal transfer of {amount} {coin}..."
            + Style.RESET_ALL
        )
        return self._send_request("POST", endpoint, params)

    def get_allowed_deposit_coin_info(
        self,
        coin: str | None = None,
        chain: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict:
        """Retrieve allowed deposit coin information.

        Endpoint: GET /v5/asset/deposit/query-allowed-list
        """
        endpoint = "/v5/asset/deposit/query-allowed-list"
        params = {"limit": limit}
        if coin:
            params["coin"] = coin
        if chain:
            params["chain"] = chain
        if cursor:
            params["cursor"] = cursor
        print(Fore.CYAN + "# Fetching allowed deposit coin info..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_deposit_records(
        self,
        coin: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict:
        """Retrieve deposit records.

        Endpoint: GET /v5/asset/deposit/query-record
        """
        endpoint = "/v5/asset/deposit/query-record"
        params = {"limit": limit}
        if coin:
            params["coin"] = coin
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        if cursor:
            params["cursor"] = cursor
        print(Fore.CYAN + "# Fetching deposit records..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_sub_deposit_records(
        self,
        sub_member_id: str,
        coin: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict:
        """Retrieve sub-account deposit records.

        Endpoint: GET /v5/asset/deposit/query-sub-member-record
        """
        endpoint = "/v5/asset/deposit/query-sub-member-record"
        params = {"subMemberId": sub_member_id, "limit": limit}
        if coin:
            params["coin"] = coin
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        if cursor:
            params["cursor"] = cursor
        print(Fore.CYAN + "# Fetching sub-account deposit records..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_internal_deposit_records(
        self,
        coin: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict:
        """Retrieve internal deposit records.

        Endpoint: GET /v5/asset/deposit/query-internal-record
        """
        endpoint = "/v5/asset/deposit/query-internal-record"
        params = {"limit": limit}
        if coin:
            params["coin"] = coin
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        if cursor:
            params["cursor"] = cursor
        print(Fore.CYAN + "# Fetching internal deposit records..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_master_deposit_address(self, coin: str, chain_type: str) -> dict:
        """Retrieve master deposit address.

        Endpoint: GET /v5/asset/deposit/query-address
        """
        endpoint = "/v5/asset/deposit/query-address"
        params = {"coin": coin, "chainType": chain_type}
        print(
            Fore.CYAN
            + f"# Fetching master deposit address for {coin}..."
            + Style.RESET_ALL
        )
        return self._send_request("GET", endpoint, params)

    def get_sub_deposit_address(
        self, sub_member_id: str, coin: str, chain_type: str
    ) -> dict:
        """Retrieve sub-account deposit address.

        Endpoint: GET /v5/asset/deposit/query-sub-member-address
        """
        endpoint = "/v5/asset/deposit/query-sub-member-address"
        params = {"subMemberId": sub_member_id, "coin": coin, "chainType": chain_type}
        print(
            Fore.CYAN
            + f"# Fetching sub-account deposit address for {coin}..."
            + Style.RESET_ALL
        )
        return self._send_request("GET", endpoint, params)

    def get_coin_info(self, coin: str | None = None) -> dict:
        """Retrieve coin information.

        Endpoint: GET /v5/asset/coin/query-info
        """
        endpoint = "/v5/asset/coin/query-info"
        params = {}
        if coin:
            params["coin"] = coin
        print(Fore.CYAN + "# Fetching coin info..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_withdrawal_records(
        self,
        coin: str | None = None,
        withdraw_id: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        withdraw_type: int | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict:
        """Retrieve withdrawal records.

        Endpoint: GET /v5/asset/withdraw/query-record
        """
        endpoint = "/v5/asset/withdraw/query-record"
        params = {"limit": limit}
        if coin:
            params["coin"] = coin
        if withdraw_id:
            params["withdrawId"] = withdraw_id
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        if withdraw_type is not None:
            params["withdrawType"] = withdraw_type
        if cursor:
            params["cursor"] = cursor
        print(Fore.CYAN + "# Fetching withdrawal records..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def withdraw(
        self,
        coin: str,
        chain: str,
        address: str,
        amount: str,
        tag: str | None = None,
        force_chain: int | None = None,
        account_type: str = "SPOT",
        fee_type: int | None = None,
    ) -> dict:
        """Create a withdrawal request.

        Endpoint: POST /v5/asset/withdraw/create
        """
        endpoint = "/v5/asset/withdraw/create"
        params = {
            "coin": coin,
            "chain": chain,
            "address": address,
            "amount": amount,
            "accountType": account_type,
        }
        if tag:
            params["tag"] = tag
        if force_chain is not None:
            params["forceChain"] = force_chain
        if fee_type is not None:
            params["feeType"] = fee_type
        print(
            Fore.CYAN + f"# Creating withdrawal of {amount} {coin}..." + Style.RESET_ALL
        )
        return self._send_request("POST", endpoint, params)

    def cancel_withdrawal(self, withdraw_id: str) -> dict:
        """Cancel a withdrawal request.

        Endpoint: POST /v5/asset/withdraw/cancel
        """
        endpoint = "/v5/asset/withdraw/cancel"
        params = {"withdrawId": withdraw_id}
        print(Fore.CYAN + f"# Cancelling withdrawal {withdraw_id}..." + Style.RESET_ALL)
        return self._send_request("POST", endpoint, params)

    # --- Risk Management and Profit Checks ---

    def calculate_position_size(
        self,
        symbol: str,
        risk_percentage: float,
        stop_loss_distance: float,
        account_type: str = "UNIFIED",
        leverage: float = 1.0,
    ) -> float:
        """Calculate position size based on risk percentage and account balance."""
        balance = self.get_account_balance(account_type)
        if not balance.get("list"):
            print(Fore.RED + "# No balance found!" + Style.RESET_ALL)
            return 0.0
        total_equity = float(balance["list"][0]["totalEquity"])
        risk_amount = total_equity * (risk_percentage / 100)
        position_size = (risk_amount * leverage) / stop_loss_distance
        print(
            Fore.CYAN
            + f"# Calculated position size for {symbol}: {position_size} units"
            + Style.RESET_ALL
        )
        return position_size

    def monitor_profit(
        self,
        symbol: str,
        profit_target: float,
        action: str = "partial_close",
        close_percentage: float = 50,
    ):
        """Monitor profit and trigger actions when target is reached."""
        if symbol in self.positions:
            self.positions[symbol]["profit_target"] = profit_target
            self.positions[symbol]["profit_action"] = action
            self.positions[symbol]["close_percentage"] = close_percentage
            print(
                Fore.CYAN
                + f"# Monitoring {symbol} for {profit_target}% profit with action {action}..."
                + Style.RESET_ALL
            )
        else:
            print(Fore.RED + f"# No position found for {symbol}!" + Style.RESET_ALL)

    def enable_break_even(self, symbol: str, enable: bool = True):
        """Enable or disable break-even enchantment for a position."""
        if symbol in self.positions:
            self.positions[symbol]["break_even_enabled"] = enable
            print(
                Fore.CYAN
                + f"# Break-even {'enabled' if enable else 'disabled'} for {symbol}..."
                + Style.RESET_ALL
            )
        else:
            print(Fore.RED + f"# No position found for {symbol}!" + Style.RESET_ALL)

    def enable_trailing_stop(
        self, symbol: str, enable: bool = True, distance: float | None = None
    ):
        """Enable or disable trailing stop-loss enchantment for a position."""
        if symbol in self.positions:
            self.positions[symbol]["tsl_enabled"] = enable
            if distance:
                self.positions[symbol]["tsl_distance"] = distance
            print(
                Fore.CYAN
                + f"# Trailing stop {'enabled' if enable else 'disabled'} for {symbol}..."
                + Style.RESET_ALL
            )
        else:
            print(Fore.RED + f"# No position found for {symbol}!" + Style.RESET_ALL)

    # --- WebSocket Functions ---

    def start_websocket(
        self, symbols: list[str] = None, public_streams: list[str] = None
    ):
        """Summon WebSocket spirits for private and public streams."""
        private_topics = (
            [f"position.{symbol}" for symbol in symbols]
            + [f"order.{symbol}" for symbol in symbols]
            if symbols
            else ["position", "order"]
        )
        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_open=lambda ws: self._on_open(ws, private_topics),
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self.ws_thread = threading.Thread(
            target=self._ws_run_with_reconnect, args=(self.ws, self.ws_url)
        )
        self.ws_thread.daemon = True
        self.ws_thread.start()
        print(Fore.CYAN + "# Private WebSocket thread summoned..." + Style.RESET_ALL)

        if public_streams:
            self.ws_public = websocket.WebSocketApp(
                self.ws_public_url,
                on_open=lambda ws: self._on_open_public(ws, public_streams),
                on_message=self._on_message_public,
                on_error=self._on_error,
                on_close=self._on_close,
            )
            self.ws_public_thread = threading.Thread(
                target=self._ws_run_with_reconnect,
                args=(self.ws_public, self.ws_public_url),
            )
            self.ws_public_thread.daemon = True
            self.ws_public_thread.start()
            print(Fore.CYAN + "# Public WebSocket thread summoned..." + Style.RESET_ALL)

        self.ws_trade = websocket.WebSocketApp(
            self.ws_trade_url,
            on_open=self._on_open_trade,
            on_message=self._on_message_trade,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self.ws_trade_thread = threading.Thread(
            target=self._ws_run_with_reconnect, args=(self.ws_trade, self.ws_trade_url)
        )
        self.ws_trade_thread.daemon = True
        self.ws_trade_thread.start()
        print(Fore.CYAN + "# Trade WebSocket thread summoned..." + Style.RESET_ALL)

    def _ws_run_with_reconnect(self, ws: websocket.WebSocketApp, url: str):
        """Run WebSocket with reconnection logic."""
        attempt = 0
        while True:
            try:
                ws.run_forever()
            except Exception as e:
                print(Fore.RED + f"# WebSocket crashed: {e!s}" + Style.RESET_ALL)
                logging.error(f"WebSocket crashed: {e!s} for {url}")
            attempt += 1
            delay = min(2**attempt, 60)
            print(
                Fore.YELLOW
                + f"# Reconnecting WebSocket in {delay}s (attempt {attempt})..."
                + Style.RESET_ALL
            )
            time.sleep(delay)
            ws.url = url
            if attempt >= 5:
                print(
                    Fore.RED + "# Max reconnection attempts reached!" + Style.RESET_ALL
                )
                break

    def _on_open(self, ws, topics: list[str]):
        """Authenticate and subscribe to private streams."""
        print(
            Fore.CYAN
            + "# Private WebSocket connected, channeling the ether..."
            + Style.RESET_ALL
        )
        expires = int((time.time() + 1) * 1000)
        signature = hmac.new(
            bytes(self.api_secret, "utf-8"),
            bytes(f"GET/realtime{expires}", "utf-8"),
            hashlib.sha256,
        ).hexdigest()
        auth_message = {"op": "auth", "args": [self.api_key, expires, signature]}
        ws.send(json.dumps(auth_message))
        subscribe_message = {"op": "subscribe", "args": topics}
        ws.send(json.dumps(subscribe_message))

        def ping():
            while ws.sock and ws.sock.connected:
                ws.send(json.dumps({"op": "ping"}))
                time.sleep(20)

        threading.Thread(target=ping, daemon=True).start()

    def _on_open_public(self, ws, topics: list[str]):
        """Subscribe to public streams."""
        print(
            Fore.CYAN
            + "# Public WebSocket connected, channeling market whispers..."
            + Style.RESET_ALL
        )
        subscribe_message = {"op": "subscribe", "args": topics}
        ws.send(json.dumps(subscribe_message))

        def ping():
            while ws.sock and ws.sock.connected:
                ws.send(json.dumps({"op": "ping"}))
                time.sleep(20)

        threading.Thread(target=ping, daemon=True).start()

    def _on_open_trade(self, ws):
        """Authenticate trade WebSocket."""
        print(
            Fore.CYAN
            + "# Trade WebSocket connected, ready to cast orders..."
            + Style.RESET_ALL
        )
        expires = int((time.time() + 1) * 1000)
        signature = hmac.new(
            bytes(self.api_secret, "utf-8"),
            bytes(f"GET/realtime{expires}", "utf-8"),
            hashlib.sha256,
        ).hexdigest()
        auth_message = {"op": "auth", "args": [self.api_key, expires, signature]}
        ws.send(json.dumps(auth_message))

    def _on_message(self, ws, message):
        """Interpret private WebSocket messages."""
        data = json.loads(message)
        if data.get("op") == "pong":
            return
        print(
            Fore.YELLOW
            + f"# Received private message: {json.dumps(data, indent=2)}"
            + Style.RESET_ALL
        )
        if data.get("topic", "").startswith("position"):
            self._handle_position_update(data)
        elif data.get("topic", "").startswith("order"):
            self._handle_order_update(data)

    def _on_message_public(self, ws, message):
        """Interpret public WebSocket messages."""
        data = json.loads(message)
        if data.get("op") == "pong":
            return
        print(
            Fore.YELLOW
            + f"# Received market whisper: {json.dumps(data, indent=2)}"
            + Style.RESET_ALL
        )
        if data.get("topic", "").startswith("tickers"):
            self._handle_ticker_update(data)

    def _on_message_trade(self, ws, message):
        """Interpret trade WebSocket messages."""
        data = json.loads(message)
        if data.get("op") == "pong":
            return
        print(
            Fore.YELLOW
            + f"# Received trade message: {json.dumps(data, indent=2)}"
            + Style.RESET_ALL
        )

    def _on_error(self, ws, error):
        """Handle disruptions in the ethereal connection."""
        print(Fore.RED + f"# WebSocket error: {error}" + Style.RESET_ALL)
        logging.error(f"WebSocket error: {error!s}")

    def _on_close(self, ws, close_status_code, close_msg):
        """Mourn the closure of the WebSocket portal."""
        print(Fore.RED + f"# WebSocket closed: {close_msg}" + Style.RESET_ALL)
        logging.error(f"WebSocket closed: {close_msg} (status: {close_status_code})")

    def _handle_position_update(self, data: dict):
        """Process position updates and apply break-even/TSL/profit logic."""
        for position in data.get("data", []):
            symbol = position.get("symbol")
            entry_price = float(position.get("entryPrice", 0))
            unrealised_pnl = float(position.get("unrealisedPnl", 0))
            stop_loss = float(position.get("stopLoss", 0))
            mark_price = float(position.get("markPrice", 0))
            size = float(position.get("size", 0))
            side = position.get("side")
            if symbol not in self.positions:
                self.positions[symbol] = {
                    "entry_price": entry_price,
                    "break_even_enabled": False,
                    "tsl_enabled": False,
                    "tsl_distance": None,
                    "profit_target": None,
                    "profit_action": None,
                    "close_percentage": None,
                }
            self.positions[symbol]["entry_price"] = entry_price

            # Break-even logic
            if (
                self.positions[symbol]["break_even_enabled"]
                and unrealised_pnl > 0
                and stop_loss != entry_price
            ):
                self.set_trading_stop(
                    symbol=symbol, category="linear", stop_loss=entry_price
                )
                print(
                    Fore.GREEN
                    + f"# Break-even stop set for {symbol} at {entry_price}"
                    + Style.RESET_ALL
                )

            # Trailing stop-loss logic
            if (
                self.positions[symbol]["tsl_enabled"]
                and self.positions[symbol]["tsl_distance"]
            ):
                if side == "Buy" and mark_price > entry_price:
                    new_stop = mark_price - self.positions[symbol]["tsl_distance"]
                    if new_stop > stop_loss:
                        self.set_trading_stop(
                            symbol=symbol, category="linear", stop_loss=new_stop
                        )
                        print(
                            Fore.GREEN
                            + f"# Trailing stop updated for {symbol} to {new_stop}"
                            + Style.RESET_ALL
                        )
                elif side == "Sell" and mark_price < entry_price:
                    new_stop = mark_price + self.positions[symbol]["tsl_distance"]
                    if new_stop < stop_loss or stop_loss == 0:
                        self.set_trading_stop(
                            symbol=symbol, category="linear", stop_loss=new_stop
                        )
                        print(
                            Fore.GREEN
                            + f"# Trailing stop updated for {symbol} to {new_stop}"
                            + Style.RESET_ALL
                        )

            # Profit check logic
            if self.positions[symbol]["profit_target"]:
                profit_pct = (unrealised_pnl / (entry_price * size)) * 100
                if profit_pct >= self.positions[symbol]["profit_target"]:
                    action = self.positions[symbol]["profit_action"]
                    if action == "partial_close":
                        close_qty = size * (
                            self.positions[symbol]["close_percentage"] / 100
                        )
                        self.place_market_order(
                            symbol, "Sell" if side == "Buy" else "Buy", close_qty
                        )
                        print(
                            Fore.GREEN
                            + f"# Partial close triggered for {symbol}: {close_qty} units"
                            + Style.RESET_ALL
                        )
                    elif action == "set_take_profit":
                        take_profit = mark_price * (
                            1 + 0.01 if side == "Buy" else 1 - 0.01
                        )
                        self.set_trading_stop(
                            symbol=symbol, category="linear", take_profit=take_profit
                        )
                        print(
                            Fore.GREEN
                            + f"# Take-profit set for {symbol} at {take_profit}"
                            + Style.RESET_ALL
                        )
                    elif action == "close":
                        self.close_position(symbol)
                        print(
                            Fore.GREEN
                            + f"# Full position closed for {symbol}"
                            + Style.RESET_ALL
                        )
                    self.positions[symbol]["profit_target"] = None

    def _handle_order_update(self, data: dict):
        """Process order updates to track position entry prices."""
        for order in data.get("data", []):
            symbol = order.get("symbol")
            status = order.get("orderStatus")
            if status == "Filled" and symbol in self.positions:
                self.positions[symbol]["entry_price"] = float(order.get("avgPrice", 0))
                print(
                    Fore.GREEN
                    + f"# Position entry price updated for {symbol}: {self.positions[symbol]['entry_price']}"
                    + Style.RESET_ALL
                )

    def _handle_ticker_update(self, data: dict):
        """Process ticker updates for market insights."""
        symbol = data.get("data", {}).get("symbol")
        last_price = float(data.get("data", {}).get("lastPrice", 0))
        print(
            Fore.YELLOW
            + f"# Market whisper for {symbol}: Last price {last_price}"
            + Style.RESET_ALL
        )

    def send_ws_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        order_type: str = "Market",
        price: float | None = None,
        category: str = "linear",
    ) -> None:
        """Cast an order through the WebSocket trade stream."""
        order_data = {
            "symbol": symbol,
            "side": side.capitalize(),
            "orderType": order_type,
            "qty": str(qty),
            "category": category,
        }
        if price and order_type == "Limit":
            order_data["price"] = str(price)
        timestamp = str(int(time.time() * 1000))
        signature = self._generate_signature(order_data, timestamp)
        order_message = {
            "reqId": f"order-{timestamp}",
            "header": {
                "X-BAPI-TIMESTAMP": timestamp,
                "X-BAPI-API-KEY": self.api_key,
                "X-BAPI-RECV-WINDOW": "5000",
                "X-BAPI-SIGN": signature,
            },
            "op": "order.create",
            "args": [order_data],
        }
        with self.lock:
            if self.ws_trade and self.ws_trade.sock and self.ws_trade.sock.connected:
                self.ws_trade.send(json.dumps(order_message))
                print(
                    Fore.CYAN
                    + f"# Casting WebSocket order for {symbol}..."
                    + Style.RESET_ALL
                )
            else:
                print(Fore.RED + "# Trade WebSocket not connected!" + Style.RESET_ALL)

    def check_health(self) -> bool:
        """Verify the health of API and WebSocket connections."""
        print(Fore.CYAN + "# Checking API connection health..." + Style.RESET_ALL)
        try:
            server_time_response = self.get_server_time()
            if server_time_response and server_time_response.get("timeNano"):
                print(
                    Fore.GREEN
                    + "# API connection healthy. Server time retrieved."
                    + Style.RESET_ALL
                )
                return True
            print(
                Fore.RED
                + "# API connection unhealthy. Could not retrieve server time."
                + Style.RESET_ALL
            )
            return False
        except Exception as e:
            print(Fore.RED + f"# Error checking API health: {e!s}" + Style.RESET_ALL)
            return False

        # WebSocket health check (more complex, as it's asynchronous)
        # For a basic check, we can just see if the threads are alive.
        # A more robust check would involve sending a ping and waiting for a pong.
        print(Fore.CYAN + "# Checking WebSocket connection health..." + Style.RESET_ALL)
        ws_healthy = True
        if self.ws_thread and self.ws_thread.is_alive():
            print(Fore.GREEN + "# Private WebSocket thread is alive." + Style.RESET_ALL)
        else:
            print(
                Fore.RED + "# Private WebSocket thread is not alive." + Style.RESET_ALL
            )
            ws_healthy = False

        if self.ws_public_thread and self.ws_public_thread.is_alive():
            print(Fore.GREEN + "# Public WebSocket thread is alive." + Style.RESET_ALL)
        else:
            print(
                Fore.YELLOW
                + "# Public WebSocket thread not started or not alive."
                + Style.RESET_ALL
            )
            # Not critical for overall health if not explicitly used

        if self.ws_trade_thread and self.ws_trade_thread.is_alive():
            print(Fore.GREEN + "# Trade WebSocket thread is alive." + Style.RESET_ALL)
        else:
            print(Fore.RED + "# Trade WebSocket thread is not alive." + Style.RESET_ALL)
            ws_healthy = False

        return ws_healthy
