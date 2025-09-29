import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
from colorama import Fore, Style
from dotenv import load_dotenv

# Import pybit clients
from pybit.unified_trading import HTTP, WebSocket

# Import local modules
from whalebot_pro.core.precision_manager import PrecisionManager
from whalebot_pro.orderbook.advanced_orderbook_manager import (
    AdvancedOrderbookManager,
    PriceLevel,
)

load_dotenv()

# Constants
MAX_API_RETRIES = 5
RETRY_DELAY_SECONDS = 7
REQUEST_TIMEOUT = 20

# Color Scheme
NEON_RED = Fore.LIGHTRED_EX
NEON_YELLOW = Fore.YELLOW
NEON_GREEN = Fore.LIGHTGREEN_EX
NEON_BLUE = Fore.CYAN
RESET = Style.RESET_ALL


class BybitClient:
    """Manages all Bybit API interactions (HTTP & WebSocket) and includes retry logic."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        config: dict[str, Any],
        logger: logging.Logger,
    ):
        self.config = config
        self.logger = logger
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = config["testnet"]
        self.symbol = config["symbol"]
        self.category = "linear"  # Currently hardcoded, could be config['category']
        self.timezone = ZoneInfo(config.get("timezone", "America/Chicago"))

        # Initialize pybit HTTP client
        self.http_session = HTTP(
            testnet=self.testnet, api_key=self.api_key, api_secret=self.api_secret
        )

        # Initialize pybit WebSocket clients
        self.ws_public: WebSocket | None = None
        self.ws_private: WebSocket | None = None
        self.ws_tasks: list[asyncio.Task] = []

        # Data storage for WebSocket updates
        self.latest_klines: pd.DataFrame = pd.DataFrame()
        self.latest_ticker: dict[str, Any] = {}
        self.private_updates_queue: asyncio.Queue = asyncio.Queue()
        self.orderbook_manager = AdvancedOrderbookManager(
            self.symbol, self.logger, use_skip_list=True
        )  # Use SkipList for OB

        # Precision Manager
        self.precision_manager = PrecisionManager(self, self.logger)

        self.logger.info(f"BybitClient initialized (Testnet: {self.testnet})")

    async def initialize(self):
        """Initializes the client, including loading instrument info."""
        await self.precision_manager.load_instrument_info(self.symbol)

    async def _bybit_request_with_retry(
        self, method: str, func: callable, *args, **kwargs
    ) -> dict | None:
        """Helper to execute pybit HTTP calls with retry logic."""
        for attempt in range(MAX_API_RETRIES):
            try:
                response = func(*args, **kwargs)
                if response and response.get("retCode") == 0:
                    return response
                else:
                    error_msg = (
                        response.get("retMsg", "Unknown error")
                        if response
                        else "No response"
                    )
                    ret_code = response.get("retCode", "N/A") if response else "N/A"
                    self.logger.error(
                        f"{NEON_RED}Bybit API Error ({method} attempt {attempt + 1}/{MAX_API_RETRIES}): {error_msg} (Code: {ret_code}){RESET}"
                    )
            except requests.exceptions.HTTPError as e:
                self.logger.error(
                    f"{NEON_RED}HTTP Error during {method} (attempt {attempt + 1}/{MAX_API_RETRIES}): {e.response.status_code} - {e.response.text}{RESET}"
                )
            except requests.exceptions.ConnectionError as e:
                self.logger.error(
                    f"{NEON_RED}Connection Error during {method} (attempt {attempt + 1}/{MAX_API_RETRIES}): {e}{RESET}"
                )
            except requests.exceptions.Timeout:
                self.logger.error(
                    f"{NEON_RED}Request timed out during {method} (attempt {attempt + 1}/{MAX_API_RETRIES}){RESET}"
                )
            except Exception as e:
                self.logger.error(
                    f"{NEON_RED}Unexpected Error during {method} (attempt {attempt + 1}/{MAX_API_RETRIES}): {e}{RESET}"
                )

            if attempt < MAX_API_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY_SECONDS)

        self.logger.critical(
            f"{NEON_RED}Bybit API {method} failed after {MAX_API_RETRIES} attempts.{RESET}"
        )
        return None

    async def fetch_current_price(self) -> Decimal | None:
        """Fetch the current market price for a symbol, preferring WebSocket data."""
        if (
            self.latest_ticker
            and self.latest_ticker.get("symbol") == self.symbol
            and self.latest_ticker.get("lastPrice") is not None
        ):
            price = self.latest_ticker["lastPrice"]
            self.logger.debug(
                f"Fetched current price for {self.symbol} from WS: {price}"
            )
            return price

        response = await self._bybit_request_with_retry(
            "fetch_current_price",
            self.http_session.get_tickers,
            category=self.category,
            symbol=self.symbol,
        )
        if response and response["result"] and response["result"]["list"]:
            price = Decimal(response["result"]["list"][0]["lastPrice"])
            self.logger.debug(
                f"Fetched current price for {self.symbol} from REST: {price}"
            )
            return price
        self.logger.warning(
            f"{NEON_YELLOW}Could not fetch current price for {self.symbol}.{RESET}"
        )
        return None

    async def fetch_klines(self, interval: str, limit: int) -> pd.DataFrame | None:
        """Fetch kline data for a symbol and interval, preferring WebSocket data."""
        if not self.latest_klines.empty and len(self.latest_klines) >= limit:
            self.logger.debug(
                f"Fetched {len(self.latest_klines)} {interval} klines for {self.symbol} from WS."
            )
            return self.latest_klines.tail(limit).copy()

        response = await self._bybit_request_with_retry(
            "fetch_klines",
            self.http_session.get_kline,
            category=self.category,
            symbol=self.symbol,
            interval=interval,
            limit=limit,
        )
        if response and response["result"] and response["result"]["list"]:
            df = pd.DataFrame(
                response["result"]["list"],
                columns=[
                    "start_time",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "turnover",
                ],
            )
            df["start_time"] = pd.to_datetime(
                df["start_time"].astype(int), unit="ms", utc=True
            ).dt.tz_convert(self.timezone)
            for col in ["open", "high", "low", "close", "volume", "turnover"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df.set_index("start_time", inplace=True)
            df.sort_index(inplace=True)

            if df.empty:
                self.logger.warning(
                    f"{NEON_YELLOW}Fetched klines for {self.symbol} {interval} but DataFrame is empty after processing. Raw response: {response}{RESET}"
                )
                return None

            self.logger.debug(
                f"Fetched {len(df)} {interval} klines for {self.symbol} from REST."
            )
            return df
        self.logger.warning(
            f"{NEON_YELLOW}Could not fetch klines for {self.symbol} {interval}. API response might be empty or invalid. Raw response: {response}{RESET}"
        )
        return None

    async def fetch_orderbook(
        self, limit: int
    ) -> tuple[list[PriceLevel], list[PriceLevel]]:
        """Fetch orderbook data for a symbol, preferring WebSocket data."""
        bids, asks = await self.orderbook_manager.get_depth(limit)
        if bids and asks:
            self.logger.debug(f"Fetched orderbook for {self.symbol} from WS.")
            return bids, asks

        response = await self._bybit_request_with_retry(
            "fetch_orderbook",
            self.http_session.get_orderbook,
            category=self.category,
            symbol=self.symbol,
            limit=limit,
        )
        if response and response["result"]:
            self.logger.debug(
                f"Fetched orderbook for {self.symbol} with limit {limit} from REST."
            )
            # Convert REST response to PriceLevel objects
            bids = [
                PriceLevel(float(p), float(q), int(time.time() * 1000))
                for p, q in response["result"].get("b", [])
            ]
            asks = [
                PriceLevel(float(p), float(q), int(time.time() * 1000))
                for p, q in response["result"].get("a", [])
            ]
            return bids, asks
        self.logger.warning(
            f"{NEON_YELLOW}Could not fetch orderbook for {self.symbol}.{RESET}"
        )
        return [], []

    async def place_order(
        self,
        side: str,
        qty: Decimal,
        order_type: str = "Market",
        price: Decimal | None = None,
        reduce_only: bool = False,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
        client_order_id: str | None = None,
    ) -> dict | None:
        """Place an order on Bybit."""
        # Use precision manager to round quantities and prices
        rounded_qty = self.precision_manager.round_qty(qty, self.symbol)
        if price:
            rounded_price = self.precision_manager.round_price(price, self.symbol)
        else:
            rounded_price = None
        if stop_loss:
            rounded_stop_loss = self.precision_manager.round_price(
                stop_loss, self.symbol
            )
        else:
            rounded_stop_loss = None
        if take_profit:
            rounded_take_profit = self.precision_manager.round_price(
                take_profit, self.symbol
            )
        else:
            rounded_take_profit = None

        params = {
            "category": self.category,
            "symbol": self.symbol,
            "side": side,
            "orderType": order_type,
            "qty": str(rounded_qty),
            "reduceOnly": reduce_only,
        }
        if rounded_price:
            params["price"] = str(rounded_price)
        if rounded_stop_loss:
            params["stopLoss"] = str(rounded_stop_loss)
        if rounded_take_profit:
            params["takeProfit"] = str(rounded_take_profit)
        if client_order_id:
            params["orderLinkId"] = client_order_id

        self.logger.info(
            f"{NEON_BLUE}Attempting to place {side} {order_type} order for {rounded_qty} at {rounded_price if rounded_price else 'Market'}...{RESET}"
        )
        response = await self._bybit_request_with_retry(
            "place_order", self.http_session.place_order, **params
        )
        if response and response.get("result"):
            self.logger.info(f"{NEON_GREEN}Order placed: {response['result']}{RESET}")
            return response["result"]
        return None

    async def set_trading_stop(
        self,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
        trailing_stop: Decimal | None = None,
        active_price: Decimal | None = None,
        position_idx: int = 0,
        tp_trigger_by: str = "MarkPrice",
        sl_trigger_by: str = "MarkPrice",
    ) -> bool:
        """Set or amend stop loss, take profit, or trailing stop for an existing position."""
        params = {
            "category": self.category,
            "symbol": self.symbol,
            "positionIdx": position_idx,
            "tpTriggerBy": tp_trigger_by,
            "slTriggerBy": sl_trigger_by,
        }
        if stop_loss:
            params["stopLoss"] = str(
                self.precision_manager.round_price(stop_loss, self.symbol)
            )
        if take_profit:
            params["takeProfit"] = str(
                self.precision_manager.round_price(take_profit, self.symbol)
            )
        if trailing_stop:
            params["trailingStop"] = str(
                self.precision_manager.round_price(trailing_stop, self.symbol)
            )
        if active_price:
            params["activePrice"] = str(
                self.precision_manager.round_price(active_price, self.symbol)
            )

        if not (stop_loss or take_profit or trailing_stop):
            self.logger.warning(
                f"{NEON_YELLOW}No TP, SL, or Trailing Stop provided for set_trading_stop. Skipping.{RESET}"
            )
            return False

        self.logger.debug(f"Attempting to set TP/SL/Trailing Stop: {params}")
        response = await self._bybit_request_with_retry(
            "set_trading_stop", self.http_session.set_trading_stop, **params
        )
        if response:
            self.logger.info(
                f"{NEON_GREEN}Trading stop updated for {self.symbol}: SL={stop_loss}, TP={take_profit}, Trailing={trailing_stop}{RESET}"
            )
            return True
        return False

    async def get_wallet_balance(self) -> Decimal | None:
        """Get current account balance."""
        response = await self._bybit_request_with_retry(
            "get_wallet_balance",
            self.http_session.get_wallet_balance,
            accountType="UNIFIED",
        )
        if response and response["result"] and response["result"]["list"]:
            for coin_data in response["result"]["list"][0]["coin"]:
                if coin_data["coin"] == "USDT":
                    return Decimal(coin_data["walletBalance"])
        self.logger.warning(f"{NEON_YELLOW}Could not fetch wallet balance.{RESET}")
        return None

    async def get_positions(self) -> list[dict[str, Any]]:
        """Get all open positions."""
        response = await self._bybit_request_with_retry(
            "get_positions",
            self.http_session.get_positions,
            category=self.category,
            symbol=self.symbol,
        )
        if response and response["result"] and response["result"]["list"]:
            return response["result"]["list"]
        return []

    # --- WebSocket Callbacks ---
    async def _on_kline_ws_message(self, message):
        """Processes incoming kline data from WebSocket."""
        if not message or "data" not in message:
            return

        new_data = []
        for item in message["data"]:
            new_data.append(
                {
                    "start_time": pd.to_datetime(
                        item["start"], unit="ms", utc=True
                    ).tz_convert(self.timezone),
                    "open": Decimal(item["open"]),
                    "high": Decimal(item["high"]),
                    "low": Decimal(item["low"]),
                    "close": Decimal(item["close"]),
                    "volume": Decimal(item["volume"]),
                    "turnover": Decimal(item["turnover"]),
                }
            )
        df_new = pd.DataFrame(new_data).set_index("start_time")

        # Append new data to existing klines, handle duplicates/out-of-order
        if self.latest_klines.empty:
            self.latest_klines = df_new
        else:
            # Combine and sort to handle updates and new bars
            combined_df = pd.concat([self.latest_klines, df_new]).drop_duplicates(
                subset=df_new.index.name, keep="last"
            )
            self.latest_klines = combined_df.sort_index()

        max_kline_history = 1000  # Keep a reasonable history
        if len(self.latest_klines) > max_kline_history:
            self.latest_klines = self.latest_klines.iloc[-max_kline_history:]

        self.logger.debug(
            f"[WS Klines] Updated. New df size: {len(self.latest_klines)}"
        )

    async def _on_ticker_ws_message(self, message):
        """Processes incoming ticker data from WebSocket."""
        if not message or "data" not in message:
            return
        ticker_data = message["data"]
        self.latest_ticker = {
            "symbol": ticker_data["symbol"],
            "lastPrice": Decimal(ticker_data["lastPrice"]),
            "bidPrice": Decimal(ticker_data["bid1Price"]),
            "askPrice": Decimal(ticker_data["ask1Price"]),
            "timestamp": datetime.now(self.timezone),
        }
        self.logger.debug(
            f"[WS Ticker] Updated. Last Price: {self.latest_ticker['lastPrice']}"
        )

    async def _on_orderbook_ws_message(self, message):
        """Processes incoming orderbook data from WebSocket."""
        if not message or "data" not in message:
            return
        data = message["data"]
        if message["type"] == "snapshot":
            await self.orderbook_manager.update_snapshot(data)
        elif message["type"] == "delta":
            await self.orderbook_manager.update_delta(data)

    async def _on_private_ws_message(self, message):
        """Processes incoming private data (order, position, wallet) from WebSocket."""
        if not message or "data" not in message:
            return
        await self.private_updates_queue.put(message)
        self.logger.debug(f"[WS Private] Received {message.get('topic')} update.")

    # --- WebSocket Management ---
    async def start_public_ws(self):
        """Starts the public WebSocket stream."""
        self.ws_public = WebSocket(channel_type=self.category, testnet=self.testnet)
        self.ws_public.kline_stream(
            interval=self.config["interval"],
            symbol=self.symbol,
            callback=self._on_kline_ws_message,
        )
        self.ws_public.ticker_stream(
            symbol=self.symbol, callback=self._on_ticker_ws_message
        )
        self.ws_public.orderbook_stream(
            depth=self.config["orderbook_limit"],
            symbol=self.symbol,
            callback=self._on_orderbook_ws_message,
        )

        self.ws_tasks.append(
            asyncio.create_task(
                self._monitor_ws_connection(self.ws_public, "Public WS")
            )
        )
        self.logger.info(
            f"{NEON_BLUE}Public WebSocket for {self.symbol} started.{RESET}"
        )

    async def start_private_ws(self):
        """Starts the private WebSocket stream with authentication."""
        if not self.api_key or not self.api_secret:
            self.logger.warning(
                f"{NEON_YELLOW}API_KEY or API_SECRET not set. Skipping private WebSocket stream.{RESET}"
            )
            return
        self.ws_private = WebSocket(
            channel_type="private",
            testnet=self.testnet,
            api_key=self.api_key,
            api_secret=self.api_secret,
        )
        self.ws_private.position_stream(callback=self._on_private_ws_message)
        self.ws_private.order_stream(callback=self._on_private_ws_message)
        self.ws_private.execution_stream(callback=self._on_private_ws_message)
        self.ws_private.wallet_stream(callback=self._on_private_ws_message)

        self.ws_tasks.append(
            asyncio.create_task(
                self._monitor_ws_connection(self.ws_private, "Private WS")
            )
        )
        self.logger.info(f"{NEON_BLUE}Private WebSocket started.{RESET}")

    async def _monitor_ws_connection(self, ws_client: WebSocket, name: str):
        """Monitors WebSocket connection and logs status."""
        while True:
            await asyncio.sleep(5)  # Check every 5 seconds
            if not ws_client.is_connected():
                self.logger.warning(
                    f"{NEON_YELLOW}{name} is not connected. Pybit handles reconnection internally.{RESET}"
                )
            else:
                self.logger.debug(f"{name} is connected.")

    async def stop_ws(self):
        """Stops all WebSocket connections."""
        for task in self.ws_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if self.ws_public:
            await self.ws_public.close()
        if self.ws_private:
            await self.ws_private.close()
        self.logger.info(f"{NEON_BLUE}All WebSockets stopped.{RESET}")

    async def get_private_updates(self) -> list[dict[str, Any]]:
        """Retrieves all accumulated private updates from the queue."""
        updates = []
        while not self.private_updates_queue.empty():
            updates.append(await self.private_updates_queue.get())
        return updates
