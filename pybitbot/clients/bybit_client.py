import asyncio
import logging
from pybit.unified_trading import HTTP, WebSocket
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from pybitbot.config.config import Config, APIConfig # Assuming config is in parent directory
from pybitbot.utils.logger import get_logger # Assuming logger is in utils

class BybitAPIError(Exception): pass
class BybitRateLimitError(BybitAPIError): pass
class BybitAccountError(BybitAPIError): pass

class BybitClient:
    def __init__(self, config: Config):
        self.config = config
        self.logger = get_logger(__name__, config.LOG_LEVEL)
        self.session = HTTP(testnet=config.api.TESTNET, api_key=config.api.KEY, api_secret=config.api.SECRET)
        self.ws_client = None
        self.klines_data = []
        self.ws_connected = False

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=4, max=60),
           retry=retry_if_exception_type(BybitAPIError))
    async def _make_api_call(self, method_name, *args, **kwargs):
        try:
            response = getattr(self.session, method_name)(*args, **kwargs)
            if response["retCode"] == 0:
                return response
            elif response["retCode"] == 10001: # Account error
                raise BybitAccountError(response["retMsg"])
            elif response["retCode"] == 10006: # Rate limit
                raise BybitRateLimitError(response["retMsg"])
            else:
                raise BybitAPIError(f"Code: {response['retCode']}, Msg: {response['retMsg']}")
        except Exception as e:
            self.logger.error(f"API call {method_name} failed: {e}")
            raise # Re-raise for tenacity

    async def get_klines(self, symbol: str, interval: str, limit: int):
        self.logger.debug(f"Fetching {limit} klines for {symbol} {interval}min")
        response = await self._make_api_call("get_kline", category="linear", symbol=symbol, interval=interval, limit=limit)
        return response["result"]["list"]

    async def place_order(self, **kwargs):
        self.logger.info(f"Placing order: {kwargs}")
        response = await self._make_api_call("place_order", **kwargs)
        return response["result"]

    async def get_wallet_balance(self, coin: str = "USDT"):
        self.logger.debug(f"Fetching wallet balance for {coin}")
        response = await self._make_api_call("get_wallet_balance", accountType="UNIFIED", coin=coin)
        if response["result"] and response["result"]["list"]:
            for item in response["result"]["list"][0]["coin"]:
                if item["coin"] == coin:
                    return float(item["walletBalance"])
        return 0.0

    async def connect_websocket(self, symbol: str, interval: str):
        if self.ws_client and self.ws_connected:
            self.logger.info("WebSocket already connected.")
            return

        self.logger.info(f"Connecting WebSocket for {symbol} {interval}min klines...")
        self.ws_client = WebSocket(testnet=self.config.api.TESTNET)

        def handle_message(message):
            # Simplified handler for kline data
            if "topic" in message and message["topic"] == f"kline.{interval}.{symbol}" and "data" in message:
                for kline_data in message["data"]:
                    if kline_data["confirm"]:
                        formatted_kline = {
                            "time": int(kline_data["start"]),
                            "open": float(kline_data["open"]),
                            "high": float(kline_data["high"]),
                            "low": float(kline_data["low"]),
                            "close": float(kline_data["close"]),
                            "volume": float(kline_data["volume"]),
                        }
                        # Add to klines_data, manage size, etc.
                        self.klines_data.append(formatted_kline)
                        if len(self.klines_data) > self.config.MIN_KLINES_FOR_STRATEGY: # Example limit
                            self.klines_data.pop(0)
                        self.logger.debug(f"Received new kline: {formatted_kline}")

        self.ws_client.kline_v5_stream(interval=interval, symbol=symbol, callback=handle_message)
        self.ws_connected = True
        self.logger.info("WebSocket connection established.")

    async def disconnect_websocket(self):
        if self.ws_client and self.ws_connected:
            self.ws_client.exit()
            self.ws_connected = False
            self.logger.info("WebSocket disconnected.")

