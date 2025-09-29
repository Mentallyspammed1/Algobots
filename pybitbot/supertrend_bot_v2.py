#!/usr/bin/env python3
"""Bybit Supertrend Trading Bot - Streamlined Version (v2.0)

This script is a self-contained, asynchronous trading bot for Bybit that
implements a Supertrend strategy. It is designed for clarity and ease of
understanding while maintaining robust, high-performance operation.

Key Features:
1.  **Fully Asynchronous:** Built on asyncio for non-blocking performance.
2.  **Self-Contained:** All logic is contained within a single class for simplicity.
3.  **Supertrend Strategy:** Implements the Supertrend indicator to generate
    BUY and SELL signals based on trend direction.
4.  **Risk Management:** Includes basic fixed-percentage risk management to
    calculate position sizes.
5.  **Real-time WebSocket Feeds:** Uses WebSockets for live kline and account data.
6.  **Dynamic Precision Handling:** Automatically fetches and applies the correct
    price and quantity precision for the chosen symbol.

Instructions for Use:
1.  Install dependencies:
    `pip install pybit pandas numpy python-dotenv`
2.  Create a `.env` file in the same directory with your credentials:
    BYBIT_API_KEY="YOUR_API_KEY"
    BYBIT_API_SECRET="YOUR_API_SECRET"
3.  Configure the `Config` class below.
4.  Run the bot:
    `python3 supertrend_bot_v2.py`
"""

import asyncio
import logging
import os
import sys
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal, getcontext
from enum import Enum

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket

# --- INITIAL SETUP ---
getcontext().prec = 28
load_dotenv()

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("supertrend_bot_v2.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


# --- ENUMS AND DATA STRUCTURES ---
class OrderSide(Enum):
    BUY = "Buy"
    SELL = "Sell"


@dataclass
class Config:
    """Trading bot configuration."""

    api_key: str = field(default_factory=lambda: os.getenv("BYBIT_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("BYBIT_API_SECRET", ""))
    testnet: bool = True
    symbol: str = "BTCUSDT"
    category: str = "linear"
    leverage: int = 5
    risk_per_trade: float = 0.02  # 2% of equity
    timeframe: str = "15"
    supertrend_period: int = 10
    supertrend_multiplier: float = 3.0
    lookback_periods: int = 200


# --- SUPER TREND BOT ---
class SupertrendBot:
    def __init__(self, config: Config):
        self.config = config
        self.session = HTTP(
            testnet=config.testnet, api_key=config.api_key, api_secret=config.api_secret
        )
        self.ws = WebSocket(
            testnet=config.testnet,
            channel_type=config.category,
            api_key=config.api_key,
            api_secret=config.api_secret,
        )

        self.market_info = None
        self.market_data = pd.DataFrame()
        self.position = None
        self.balance = Decimal("0")
        self.is_running = False
        self.is_processing_signal = False

    async def initialize(self):
        """Load market info, historical data, and initial balance."""
        logger.info("Initializing bot...")
        await self._load_market_info()
        await self._load_historical_data()
        await self.update_account_balance()
        await self.get_position()
        logger.info("Bot initialization complete.")

    async def _load_market_info(self):
        """Load and store market information for the symbol."""
        try:
            resp = self.session.get_instruments_info(
                category=self.config.category, symbol=self.config.symbol
            )
            if resp["retCode"] == 0:
                instrument = resp["result"]["list"][0]
                self.market_info = {
                    "tick_size": Decimal(instrument["priceFilter"]["tickSize"]),
                    "lot_size": Decimal(instrument["lotSizeFilter"]["qtyStep"]),
                }
                logger.info(
                    f"Market info loaded for {self.config.symbol}: {self.market_info}"
                )
            else:
                raise Exception(f"Failed to get instrument info: {resp['retMsg']}")
        except Exception as e:
            logger.error(f"Error loading market info: {e}", exc_info=True)
            sys.exit(1)

    async def _load_historical_data(self):
        """Load historical kline data to warm up the strategy."""
        logger.info(f"Loading historical data for {self.config.symbol}...")
        try:
            resp = self.session.get_kline(
                category=self.config.category,
                symbol=self.config.symbol,
                interval=self.config.timeframe,
                limit=self.config.lookback_periods,
            )
            if resp["retCode"] == 0:
                data = resp["result"]["list"]
                df = pd.DataFrame(
                    data,
                    columns=[
                        "time",
                        "open",
                        "high",
                        "low",
                        "close",
                        "volume",
                        "turnover",
                    ],
                )
                df["time"] = pd.to_datetime(df["time"], unit="ms")
                df.set_index("time", inplace=True)
                df = df.astype(float).sort_index()
                self.market_data = df
                logger.info(f"Loaded {len(df)} historical candles.")
            else:
                raise Exception(f"Failed to get kline data: {resp['retMsg']}")
        except Exception as e:
            logger.error(f"Error loading historical data: {e}", exc_info=True)
            sys.exit(1)

    def _calculate_supertrend(self):
        """Calculates ATR and Supertrend and adds them to the market_data DataFrame."""
        df = self.market_data
        if df.empty or len(df) < self.config.supertrend_period:
            return

        high_low = df["high"] - df["low"]
        high_close = np.abs(df["high"] - df["close"].shift())
        low_close = np.abs(df["low"] - df["close"].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = tr.ewm(alpha=1 / self.config.supertrend_period, adjust=False).mean()

        hl2 = (df["high"] + df["low"]) / 2
        df["upperband"] = hl2 + (self.config.supertrend_multiplier * df["atr"])
        df["lowerband"] = hl2 - (self.config.supertrend_multiplier * df["atr"])
        df["in_uptrend"] = True

        for current in range(1, len(df.index)):
            previous = current - 1
            if df.iloc[current]["close"] > df.iloc[previous]["upperband"]:
                df.iloc[current, df.columns.get_loc("in_uptrend")] = True
            elif df.iloc[current]["close"] < df.iloc[previous]["lowerband"]:
                df.iloc[current, df.columns.get_loc("in_uptrend")] = False
            else:
                df.iloc[current, df.columns.get_loc("in_uptrend")] = df.iloc[previous][
                    "in_uptrend"
                ]
                if (
                    df.iloc[current]["in_uptrend"]
                    and df.iloc[current]["lowerband"] < df.iloc[previous]["lowerband"]
                ):
                    df.iloc[current, df.columns.get_loc("lowerband")] = df.iloc[
                        previous
                    ]["lowerband"]
                if (
                    not df.iloc[current]["in_uptrend"]
                    and df.iloc[current]["upperband"] > df.iloc[previous]["upperband"]
                ):
                    df.iloc[current, df.columns.get_loc("upperband")] = df.iloc[
                        previous
                    ]["upperband"]

        df["supertrend"] = np.where(df["in_uptrend"], df["lowerband"], df["upperband"])

    async def place_order(
        self, side: OrderSide, quantity: float, stop_loss: float | None = None
    ):
        """Places a market order."""
        try:
            qty_str = str(
                Decimal(str(quantity)).quantize(
                    self.market_info["lot_size"], rounding=ROUND_DOWN
                )
            )
            params = {
                "category": self.config.category,
                "symbol": self.config.symbol,
                "side": side.value,
                "orderType": "Market",
                "qty": qty_str,
            }
            if stop_loss:
                params["stopLoss"] = str(
                    Decimal(str(stop_loss)).quantize(
                        self.market_info["tick_size"], rounding=ROUND_DOWN
                    )
                )
                params["slTriggerBy"] = "LastPrice"

            logger.info(f"Placing order: {params}")
            resp = self.session.place_order(**params)
            if resp["retCode"] == 0:
                logger.info(
                    f"TRADE: Order placed successfully: {resp['result']['orderId']}"
                )
            else:
                logger.error(f"Failed to place order: {resp['retMsg']}")
        except Exception as e:
            logger.error(f"Error placing order: {e}", exc_info=True)

    async def get_position(self):
        """Get current position for the symbol."""
        try:
            resp = self.session.get_positions(
                category=self.config.category, symbol=self.config.symbol
            )
            if resp["retCode"] == 0 and resp["result"]["list"]:
                pos_data = resp["result"]["list"][0]
                self.position = (
                    {"side": pos_data["side"], "size": Decimal(pos_data["size"])}
                    if Decimal(pos_data["size"]) > 0
                    else None
                )
            else:
                self.position = None
        except Exception as e:
            logger.error(f"Error getting position: {e}", exc_info=True)

    async def update_account_balance(self):
        """Update account balance."""
        try:
            resp = self.session.get_wallet_balance(accountType="UNIFIED")
            if resp["retCode"] == 0:
                self.balance = Decimal(resp["result"]["list"][0]["totalEquity"])
                logger.info(f"Account balance updated: {self.balance:.2f} USDT")
        except Exception as e:
            logger.error(f"Error updating balance: {e}", exc_info=True)

    def _calculate_position_size(self, current_price: float) -> float:
        """Calculates position size based on fixed risk percentage."""
        risk_amount_usd = float(self.balance) * self.config.risk_per_trade
        position_size_asset = risk_amount_usd / current_price
        return position_size_asset * self.config.leverage

    async def run_strategy_cycle(self):
        """Calculates indicators and processes signals."""
        if self.is_processing_signal:
            return
        self.is_processing_signal = True

        try:
            self._calculate_supertrend()
            if len(self.market_data) < 2:
                return

            current = self.market_data.iloc[-1]
            previous = self.market_data.iloc[-2]

            signal_action = None
            stop_loss = None

            if not previous["in_uptrend"] and current["in_uptrend"]:
                signal_action = OrderSide.BUY
                stop_loss = float(current["supertrend"])
            elif previous["in_uptrend"] and not current["in_uptrend"]:
                signal_action = OrderSide.SELL
                stop_loss = float(current["supertrend"])

            if signal_action:
                logger.info(f"Signal received: {signal_action.value}")
                current_price = float(current["close"])
                position_size = self._calculate_position_size(current_price)

                if self.position:
                    if (
                        signal_action == OrderSide.BUY
                        and self.position["side"] == "Sell"
                    ) or (
                        signal_action == OrderSide.SELL
                        and self.position["side"] == "Buy"
                    ):
                        logger.info(
                            f"Closing existing {self.position['side']} position."
                        )
                        close_side = (
                            OrderSide.BUY
                            if self.position["side"] == "Sell"
                            else OrderSide.SELL
                        )
                        await self.place_order(close_side, float(self.position["size"]))
                        await asyncio.sleep(3)  # Wait for position to close

                if (
                    signal_action == OrderSide.BUY
                    and (not self.position or self.position["side"] != "Buy")
                ) or (
                    signal_action == OrderSide.SELL
                    and (not self.position or self.position["side"] != "Sell")
                ):
                    await self.place_order(
                        signal_action, position_size, stop_loss=stop_loss
                    )
                else:
                    logger.info(
                        f"Signal to {signal_action.value} ignored, already in a position on that side."
                    )
        finally:
            self.is_processing_signal = False

    def _handle_kline(self, message):
        try:
            data = message["data"][0]
            new_candle = pd.DataFrame(
                [
                    {
                        "time": pd.to_datetime(int(data["start"]), unit="ms"),
                        "open": float(data["open"]),
                        "high": float(data["high"]),
                        "low": float(data["low"]),
                        "close": float(data["close"]),
                        "volume": float(data["volume"]),
                        "turnover": float(data["turnover"]),
                    }
                ]
            ).set_index("time")

            if new_candle.index[0] in self.market_data.index:
                self.market_data.loc[new_candle.index[0]] = new_candle.iloc[0]
            else:
                self.market_data = pd.concat([self.market_data, new_candle]).iloc[
                    -self.config.lookback_periods :
                ]

            if data["confirm"]:  # Only run on confirmed candles
                asyncio.create_task(self.run_strategy_cycle())
        except Exception as e:
            logger.error(f"Error handling kline: {e}", exc_info=True)

    def _handle_private(self, message):
        topic = message.get("topic")
        if topic == "position":
            asyncio.create_task(self.get_position())
        elif topic == "wallet":
            asyncio.create_task(self.update_account_balance())

    async def start(self):
        """Start the trading bot."""
        self.is_running = True
        await self.initialize()

        self.ws.kline_stream(
            callback=self._handle_kline,
            symbol=self.config.symbol,
            interval=self.config.timeframe,
        )
        self.ws.position_stream(callback=self._handle_private)
        self.ws.wallet_stream(callback=self._handle_private)

        logger.info("Bot started. Waiting for signals...")
        while self.is_running:
            await asyncio.sleep(1)

    async def stop(self):
        self.is_running = False
        self.ws.exit()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    if not os.getenv("BYBIT_API_KEY") or not os.getenv("BYBIT_API_SECRET"):
        logger.critical("API keys not set in .env file. Exiting.")
        sys.exit(1)

    bot = SupertrendBot(config=Config())
    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
        asyncio.run(bot.stop())
    except Exception as e:
        logger.critical(f"Unhandled exception: {e}", exc_info=True)
        asyncio.run(bot.stop())
