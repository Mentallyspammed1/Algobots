# bybit_market_data_helper.py
import logging
import time
from typing import Any

from pybit.exceptions import BybitAPIError, BybitRequestError
from pybit.unified_trading import HTTP

# Configure logging for the module
logging.basicConfig(
    level=logging.INFO,  # Changed to INFO for less verbose default output, DEBUG for full details
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


class BybitMarketDataHelper:
    """A helper class for fetching various public market data points from Bybit
    via the Unified Trading HTTP REST API. This includes kline data, tickers,
    instrument information, and more.
    """

    def __init__(self, testnet: bool = False, api_key: str = "", api_secret: str = ""):
        """Initializes the BybitMarketDataHelper.
        API key and secret are optional for most public market data endpoints,
        but are included in the constructor for consistency and if future
        extensions require authenticated public endpoints.

        :param testnet: Set to True to connect to the Bybit testnet, False for mainnet.
        :param api_key: Optional. Your Bybit API key.
        :param api_secret: Optional. Your Bybit API secret.
        """
        self.testnet = testnet
        # API key/secret are optional for most public market data, but passed for consistency
        self.session = HTTP(
            testnet=self.testnet, api_key=api_key, api_secret=api_secret
        )
        logger.info(
            f"BybitMarketDataHelper initialized for {'testnet' if self.testnet else 'mainnet'}."
        )

    def _make_request(
        self, method: str, endpoint_name: str, **kwargs
    ) -> dict[str, Any] | None:
        """Internal method to make an HTTP request to the Bybit API and handle responses.
        It centralizes error handling and logging for API calls.

        :param method: The name of the method to call on the `self.session` object (e.g., 'get_tickers').
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

    def get_server_time(self) -> dict[str, Any] | None:
        """Retrieves the current Bybit server time.

        :return: A dictionary containing server time information (e.g., 'timeNano', 'timeSecond')
                 or None on failure.
        """
        return self._make_request("get_server_time", "Server Time")

    def get_tickers(
        self, category: str, symbol: str | None = None
    ) -> dict[str, Any] | None:
        """Retrieves 24-hour price statistics and current prices for instruments
        within a specified category, optionally for a specific symbol.

        :param category: The product type (e.g., "spot", "linear", "inverse", "option").
        :param symbol: Optional. The trading symbol (e.g., "BTCUSDT"). If not provided,
                       returns tickers for all symbols in the specified category.
        :return: A dictionary containing a list of ticker information or None on failure.
        """
        # Input validation
        if not isinstance(category, str) or not category:
            logger.error(
                "Invalid or empty string provided for 'category' for get_tickers."
            )
            return None
        if symbol is not None and (not isinstance(symbol, str) or not symbol):
            logger.error("Invalid 'symbol' provided for get_tickers.")
            return None

        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        return self._make_request("get_tickers", "Tickers", **params)

    def get_kline(
        self,
        category: str,
        symbol: str,
        interval: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int | None = None,
    ) -> dict[str, Any] | None:
        """Retrieves candlestick/kline data for a specific symbol and interval.

        :param category: The product type.
        :param symbol: The trading symbol.
        :param interval: The kline interval (e.g., "1", "3", "5", "15", "30", "60" for minutes;
                                        "120", "240", "360", "720" for hours; "D" for daily;
                                        "W" for weekly; "M" for monthly).
        :param start_time: Optional. Start timestamp in milliseconds.
        :param end_time: Optional. End timestamp in milliseconds.
        :param limit: Optional. Number of data points to retrieve (max 1000).
        :return: A dictionary containing a list of kline data (each as [timestamp, open, high, low, close, volume])
                 or None on failure.
        """
        # Input validation
        if not all(
            isinstance(arg, str) and arg for arg in [category, symbol, interval]
        ):
            logger.error(
                "Invalid or empty string provided for category, symbol, or interval for get_kline."
            )
            return None

        # Basic validation for interval (can be expanded)
        allowed_intervals = [
            "1",
            "3",
            "5",
            "15",
            "30",
            "60",
            "120",
            "240",
            "360",
            "720",
            "D",
            "W",
            "M",
        ]
        if interval not in allowed_intervals:
            logger.warning(
                f"Provided interval '{interval}' might not be supported. Allowed: {allowed_intervals}"
            )

        params = {"category": category, "symbol": symbol, "interval": interval}
        if start_time is not None:
            if not isinstance(start_time, int) or start_time < 0:
                logger.error(
                    "Invalid 'start_time' provided for get_kline. Must be a positive integer (ms)."
                )
                return None
            params["start"] = start_time
        if end_time is not None:
            if not isinstance(end_time, int) or end_time < 0:
                logger.error(
                    "Invalid 'end_time' provided for get_kline. Must be a positive integer (ms)."
                )
                return None
            params["end"] = end_time
        if limit is not None:
            if not isinstance(limit, int) or not (1 <= limit <= 1000):
                logger.error(
                    "Invalid 'limit' provided for get_kline. Must be an integer between 1 and 1000."
                )
                return None
            params["limit"] = limit

        return self._make_request("get_kline", "Kline Data", **params)

    def get_instruments_info(
        self, category: str, symbol: str | None = None
    ) -> dict[str, Any] | None:
        """Retrieves trading pair specifications and rules (e.g., min order size, tick size)
        for a given category, optionally for a specific symbol.

        :param category: The product type.
        :param symbol: Optional. The trading symbol.
        :return: A dictionary containing a list of instrument information or None on failure.
        """
        # Input validation
        if not isinstance(category, str) or not category:
            logger.error(
                "Invalid or empty string provided for 'category' for get_instruments_info."
            )
            return None
        if symbol is not None and (not isinstance(symbol, str) or not symbol):
            logger.error("Invalid 'symbol' provided for get_instruments_info.")
            return None

        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        return self._make_request("get_instruments_info", "Instruments Info", **params)

    def get_public_trade_history(
        self, category: str, symbol: str, **kwargs
    ) -> dict[str, Any] | None:
        """Retrieves recent public trades for a specified symbol.

        :param category: The product type.
        :param symbol: The trading symbol.
        :param kwargs: Additional optional parameters (e.g., `limit`).
        :return: A dictionary containing a list of public trade records or None on failure.
        """
        # Input validation
        if not all(isinstance(arg, str) and arg for arg in [category, symbol]):
            logger.error(
                "Invalid or empty string provided for category or symbol for get_public_trade_history."
            )
            return None

        params = {"category": category, "symbol": symbol}
        params.update(kwargs)
        return self._make_request(
            "get_public_trade_history", "Public Trade History", **params
        )

    def get_funding_rate_history(
        self, category: str, symbol: str, **kwargs
    ) -> dict[str, Any] | None:
        """Retrieves historical funding rates for derivatives.

        :param category: The product type (e.g., "linear", "inverse").
        :param symbol: The trading symbol.
        :param kwargs: Additional optional parameters (e.g., `startTime`, `endTime`, `limit`).
        :return: A dictionary containing a list of funding rate records or None on failure.
        """
        # Input validation
        if not all(isinstance(arg, str) and arg for arg in [category, symbol]):
            logger.error(
                "Invalid or empty string provided for category or symbol for get_funding_rate_history."
            )
            return None

        params = {"category": category, "symbol": symbol}
        params.update(kwargs)
        return self._make_request(
            "get_funding_rate_history", "Funding Rate History", **params
        )

    def get_long_short_ratio(
        self, category: str, symbol: str, interval_time: str, **kwargs
    ) -> dict[str, Any] | None:
        """Retrieves long/short ratio data for a specific symbol and interval.

        :param category: The product type.
        :param symbol: The trading symbol.
        :param interval_time: The interval for data points (e.g., "5min", "15min", "30min", "1h", "4h", "12h", "1d").
        :param kwargs: Additional optional parameters (e.g., `startTime`, `endTime`, `limit`).
        :return: A dictionary containing a list of long/short ratio data or None on failure.
        """
        # Input validation
        if not all(
            isinstance(arg, str) and arg for arg in [category, symbol, interval_time]
        ):
            logger.error(
                "Invalid or empty string provided for category, symbol, or interval_time for get_long_short_ratio."
            )
            return None

        allowed_interval_times = ["5min", "15min", "30min", "1h", "4h", "12h", "1d"]
        if interval_time not in allowed_interval_times:
            logger.error(
                f"Invalid 'interval_time' provided for get_long_short_ratio. Allowed: {allowed_interval_times}, got '{interval_time}'."
            )
            return None

        params = {"category": category, "symbol": symbol, "intervalTime": interval_time}
        params.update(kwargs)
        return self._make_request("get_long_short_ratio", "Long/Short Ratio", **params)


# Example Usage
if __name__ == "__main__":
    # For public market data, API key/secret are optional.
    # Set USE_TESTNET to False for production (mainnet).
    API_KEY = ""  # Optional for public market data
    API_SECRET = ""  # Optional for public market data
    USE_TESTNET = True

    market_data_helper = BybitMarketDataHelper(
        testnet=USE_TESTNET, api_key=API_KEY, api_secret=API_SECRET
    )

    SYMBOL = "BTCUSDT"
    CATEGORY = "linear"  # Or 'spot', 'inverse', 'option'

    print("\n--- Getting Server Time ---")
    server_time = market_data_helper.get_server_time()
    if server_time:
        # Bybit returns time in nanoseconds for 'timeNano' and seconds for 'timeSecond'
        print(f"  Bybit Server Time (Nano): {server_time.get('timeNano')}")
        print(f"  Bybit Server Time (Seconds): {server_time.get('timeSecond')}")
        print(
            f"  Local Time (from server seconds): {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(int(server_time.get('timeSecond', 0))))}"
        )
    else:
        print("  Failed to retrieve server time.")

    print(f"\n--- Getting Tickers for {SYMBOL} ({CATEGORY}) ---")
    tickers = market_data_helper.get_tickers(category=CATEGORY, symbol=SYMBOL)
    if tickers and tickers.get("list"):
        ticker = tickers["list"][0]
        print(
            f"  Symbol: {ticker.get('symbol')}, Last Price: {ticker.get('lastPrice')}, 24h Change: {ticker.get('price24hPcnt')}, Volume: {ticker.get('volume24h')}"
        )
    else:
        print(f"  Failed to retrieve tickers for {SYMBOL}.")

    print(f"\n--- Getting 1-hour Kline for {SYMBOL} (last 3 bars) ---")
    end_time_ms = int(time.time() * 1000)
    start_time_ms = end_time_ms - (3 * 60 * 60 * 1000)  # 3 hours ago
    kline_data = market_data_helper.get_kline(
        category=CATEGORY,
        symbol=SYMBOL,
        interval="60",  # 60 minutes = 1 hour
        start_time=start_time_ms,
        end_time=end_time_ms,
        limit=3,
    )
    if kline_data and kline_data.get("list"):
        print("  [Timestamp, Open, High, Low, Close, Volume, Turnover]")
        for bar in kline_data["list"]:
            # Convert timestamp from string to int for readable format
            ts = int(bar[0]) / 1000
            print(
                f"  Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))}, Open: {bar[1]}, High: {bar[2]}, Low: {bar[3]}, Close: {bar[4]}, Volume: {bar[5]}"
            )
    else:
        print(f"  Failed to retrieve kline data for {SYMBOL}.")

    print(f"\n--- Getting Instruments Info for {SYMBOL} ({CATEGORY}) ---")
    instrument_info = market_data_helper.get_instruments_info(
        category=CATEGORY, symbol=SYMBOL
    )
    if instrument_info and instrument_info.get("list"):
        info = instrument_info["list"][0]
        print(
            f"  Symbol: {info.get('symbol')}, Base Coin: {info.get('baseCoin')}, Quote Coin: {info.get('quoteCoin')}"
        )
        print(
            f"  Price Filter (tickSize): {info.get('priceFilter', {}).get('tickSize')}"
        )
        print(
            f"  Lot Size Filter (minOrderQty): {info.get('lotSizeFilter', {}).get('minOrderQty')}"
        )
    else:
        print(f"  Failed to retrieve instrument info for {SYMBOL}.")

    print(f"\n--- Getting Public Trade History for {SYMBOL} (last 3 records) ---")
    public_trades = market_data_helper.get_public_trade_history(
        category=CATEGORY, symbol=SYMBOL, limit=3
    )
    if public_trades and public_trades.get("list"):
        for trade in public_trades["list"]:
            # Convert timestamp from string to int for readable format
            ts = int(trade.get("time")) / 1000
            print(
                f"  Price: {trade.get('price')}, Qty: {trade.get('qty')}, Side: {trade.get('side')}, Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))}"
            )
    else:
        print(f"  Failed to retrieve public trade history for {SYMBOL}.")

    print(f"\n--- Getting Funding Rate History for {SYMBOL} (last 1 record) ---")
    funding_rate_history = market_data_helper.get_funding_rate_history(
        category=CATEGORY, symbol=SYMBOL, limit=1
    )
    if funding_rate_history and funding_rate_history.get("list"):
        rate_record = funding_rate_history["list"][0]
        # Convert timestamp from string to int for readable format
        ts = int(rate_record.get("fundingRateTimestamp")) / 1000
        print(
            f"  Funding Rate: {rate_record.get('fundingRate')}, Funding Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))}"
        )
    else:
        print(f"  Failed to retrieve funding rate history for {SYMBOL}.")

    print(
        f"\n--- Getting Long/Short Ratio for {SYMBOL} (1-hour interval, last 1 record) ---"
    )
    long_short_ratio = market_data_helper.get_long_short_ratio(
        category=CATEGORY, symbol=SYMBOL, interval_time="1h", limit=1
    )
    if long_short_ratio and long_short_ratio.get("list"):
        ratio_record = long_short_ratio["list"][0]
        print(
            f"  Buy Ratio: {ratio_record.get('buyRatio')}, Sell Ratio: {ratio_record.get('sellRatio')}, Timestamp: {ratio_record.get('timestamp')}"
        )
    else:
        print(f"  Failed to retrieve long/short ratio for {SYMBOL}.")
