"""Core Trading Logic for the Bybit Trading Bot.

This module contains the main BybitTrader class that handles:
- API connections (REST and WebSocket)
- Strategy loading and execution
- Order and position management
- Real-time data handling
"""

import importlib.util
import time

import pandas as pd
from bot_logger import logger
from pybit.unified_trading import HTTP, WebSocket
from strategies.base_strategy import BaseStrategy

from config import (
    API_KEY,
    API_SECRET,
    CATEGORY,
    SYMBOL,
    TESTNET,
    TRADE_QTY_USD,
    WS_HEARTBEAT,
)


class BybitTrader:
    """The main class for the trading bot."""

    def __init__(self, strategy_path: str):
        self.strategy: BaseStrategy = self._load_strategy_from_file(strategy_path)
        logger.info(f"Successfully loaded strategy: {self.strategy.name}")

        self.session = HTTP(testnet=TESTNET, api_key=API_KEY, api_secret=API_SECRET)
        self.ws = WebSocket(
            testnet=TESTNET,
            channel_type="private",
            api_key=API_KEY,
            api_secret=API_SECRET,
        )

        self.kline_data = pd.DataFrame(
            columns=["open", "high", "low", "close", "volume", "turnover"]
        )
        self.is_long = False
        self.is_short = False
        self.last_order_time = 0
        self.cooldown_period = 60  # seconds

    def _load_strategy_from_file(self, file_path: str) -> BaseStrategy:
        """Dynamically loads a strategy class from a Python file."""
        try:
            spec = importlib.util.spec_from_file_location("strategy_module", file_path)
            strategy_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(strategy_module)

            for item in dir(strategy_module):
                if not item.startswith("_"):
                    cls = getattr(strategy_module, item)
                    if (
                        isinstance(cls, type)
                        and issubclass(cls, BaseStrategy)
                        and cls is not BaseStrategy
                    ):
                        return cls()
            raise ImportError(f"No strategy class found in {file_path}")
        except Exception as e:
            logger.error(f"Error loading strategy from {file_path}: {e}")
            raise

    def _handle_kline_message(self, message: dict):
        """Callback function to process incoming kline data from WebSocket."""
        kline_list = message.get("data", [])
        for kline in kline_list:
            timestamp = pd.to_datetime(int(kline["start"]), unit="ms")
            new_row = {
                "open": float(kline["open"]),
                "high": float(kline["high"]),
                "low": float(kline["low"]),
                "close": float(kline["close"]),
                "volume": float(kline["volume"]),
                "turnover": float(kline["turnover"]),
            }
            self.kline_data.loc[timestamp] = new_row

        self.kline_data.sort_index(inplace=True)

        # Keep only the last 200 candles to avoid memory issues
        if len(self.kline_data) > 200:
            self.kline_data = self.kline_data.iloc[-200:]

        self.run_strategy()

    def get_historical_klines(self, symbol: str, interval: str = "1"):
        """Fetches historical kline data to bootstrap the bot."""
        try:
            response = self.session.get_kline(
                category=CATEGORY, symbol=symbol, interval=interval, limit=200
            )
            if response["retCode"] == 0:
                klines = response["result"]["list"]
                for kline in klines:
                    timestamp = pd.to_datetime(int(kline[0]), unit="ms")
                    self.kline_data.loc[timestamp] = {
                        "open": float(kline[1]),
                        "high": float(kline[2]),
                        "low": float(kline[3]),
                        "close": float(kline[4]),
                        "volume": float(kline[5]),
                        "turnover": float(kline[6]),
                    }
                self.kline_data.sort_index(inplace=True)
                logger.info(
                    f"Successfully fetched {len(self.kline_data)} historical klines for {symbol}."
                )
            else:
                logger.error(f"Error fetching klines: {response['retMsg']}")
        except Exception as e:
            logger.error(f"Exception fetching klines: {e}")

    def run_strategy(self):
        """Runs the loaded strategy and executes trades based on signals."""
        if len(self.kline_data) < 20:  # Not enough data for indicators
            return

        # Generate signals
        signals_df = self.strategy.generate_signals(self.kline_data)
        signal = signals_df["signal"].iloc[-1]

        logger.info(f"Signal: {signal}")

        # Execute trades
        if signal == "buy" and not self.is_long:
            self.place_order("Buy")
        elif signal == "sell" and not self.is_short:
            self.place_order("Sell")

    def place_order(self, side: str):
        """Places an order on Bybit."""
        current_time = time.time()
        if current_time - self.last_order_time < self.cooldown_period:
            logger.warning("Cooldown period active. Skipping order.")
            return

        try:
            # Close any existing position first
            if self.is_long or self.is_short:
                close_side = "Sell" if self.is_long else "Buy"
                logger.info(f"Closing existing position: {close_side}")
                self.session.place_order(
                    category=CATEGORY,
                    symbol=SYMBOL,
                    side=close_side,
                    orderType="Market",
                    qty=str(TRADE_QTY_USD / float(self.kline_data["close"].iloc[-1])),
                )

            # Place new order
            response = self.session.place_order(
                category=CATEGORY,
                symbol=SYMBOL,
                side=side,
                orderType="Market",
                qty=str(TRADE_QTY_USD / float(self.kline_data["close"].iloc[-1])),
            )
            if response["retCode"] == 0:
                logger.info(f"{side} order placed successfully: {response['result']}")
                self.last_order_time = current_time
                if side == "Buy":
                    self.is_long = True
                    self.is_short = False
                else:
                    self.is_long = False
                    self.is_short = True
            else:
                logger.error(f"Error placing {side} order: {response['retMsg']}")
        except Exception as e:
            logger.error(f"Exception placing order: {e}")

    def start(self):
        """Starts the WebSocket connection and the bot's main loop."""
        logger.info("Starting Bybit Trader...")

        # Fetch initial kline data
        self.get_historical_klines(SYMBOL)

        # Subscribe to kline stream
        self.ws.kline_stream(
            symbol=SYMBOL, interval=1, callback=self._handle_kline_message
        )

        while True:
            time.sleep(WS_HEARTBEAT)
            self.ws.ping()
