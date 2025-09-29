# bybit_trading_bot.py

import asyncio
import importlib
import logging

from logger_setup import setup_logger
from pybit.unified_trading import HTTP
from strategy_interface import BaseStrategy
from utilities import InMemoryCache, KlineDataFetcher

from config import Config


class BybitTradingBot:
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger("TradingBot")
        self.http_session = HTTP(
            testnet=self.config.TESTNET,
            api_key=self.config.BYBIT_API_KEY,
            api_secret=self.config.BYBIT_API_SECRET,
        )
        self.kline_data_fetcher = KlineDataFetcher(
            self.http_session, self.logger, self.config
        )
        self.kline_cache = InMemoryCache(
            ttl_seconds=self.config.TRADING_LOGIC_LOOP_INTERVAL_SECONDS * 0.8,
            max_size=5,
        )
        self.strategy: BaseStrategy | None = None
        self._load_strategy()
        self.is_running = True

    def _load_strategy(self):
        try:
            strategy_module_name = self.config.ACTIVE_STRATEGY_MODULE
            strategy_class_name = self.config.ACTIVE_STRATEGY_CLASS
            module = importlib.import_module(strategy_module_name)
            strategy_class = getattr(module, strategy_class_name)
            strategy_params = {
                "STRATEGY_EMA_FAST_PERIOD": self.config.STRATEGY_EMA_FAST_PERIOD,
                "STRATEGY_EMA_SLOW_PERIOD": self.config.STRATEGY_EMA_SLOW_PERIOD,
                "STRATEGY_RSI_PERIOD": self.config.STRATEGY_RSI_PERIOD,
                "STRATEGY_RSI_OVERSOLD": self.config.STRATEGY_RSI_OVERSOLD,
                "STRATEGY_RSI_OVERBOUGHT": self.config.STRATEGY_RSI_OVERBOUGHT,
                "STRATEGY_MACD_FAST_PERIOD": self.config.STRATEGY_MACD_FAST_PERIOD,
                "STRATEGY_MACD_SLOW_PERIOD": self.config.STRATEGY_MACD_SLOW_PERIOD,
                "STRATEGY_MACD_SIGNAL_PERIOD": self.config.STRATEGY_MACD_SIGNAL_PERIOD,
                "STRATEGY_BB_PERIOD": self.config.STRATEGY_BB_PERIOD,
                "STRATEGY_BB_STD": self.config.STRATEGY_BB_STD,
                "STRATEGY_ATR_PERIOD": self.config.STRATEGY_ATR_PERIOD,
                "STRATEGY_ADX_PERIOD": self.config.STRATEGY_ADX_PERIOD,
                "STRATEGY_BUY_SCORE_THRESHOLD": self.config.STRATEGY_BUY_SCORE_THRESHOLD,
                "STRATEGY_SELL_SCORE_THRESHOLD": self.config.STRATEGY_SELL_SCORE_THRESHOLD,
            }
            self.strategy = strategy_class(self.logger, **strategy_params)
            self.logger.info(
                f"Successfully loaded strategy: {self.strategy.strategy_name}"
            )
        except Exception as e:
            self.logger.critical(f"Failed to load trading strategy: {e}", exc_info=True)
            self.is_running = False

    async def trading_logic(self):
        # This is a simplified version of the trading logic from your other files.
        # It demonstrates how the new structure works.
        self.logger.info("Running trading logic...")
        kline_cache_key = self.kline_cache.generate_kline_cache_key(
            self.config.SYMBOL,
            self.config.CATEGORY,
            self.config.KLINES_INTERVAL,
            self.config.KLINES_LOOKBACK_LIMIT,
            self.config.KLINES_HISTORY_WINDOW_MINUTES,
        )
        current_kline_data = self.kline_cache.get(kline_cache_key)

        if current_kline_data is None:
            current_kline_data = await self.kline_data_fetcher.fetch_klines(
                self.config.SYMBOL,
                self.config.CATEGORY,
                self.config.KLINES_INTERVAL,
                self.config.KLINES_LOOKBACK_LIMIT,
                self.config.KLINES_HISTORY_WINDOW_MINUTES,
            )
            if not current_kline_data.empty:
                self.kline_cache.set(kline_cache_key, current_kline_data)

        if current_kline_data.empty:
            self.logger.warning("No kline data available. Skipping trading logic.")
            return

        if self.strategy:
            current_kline_data = self.strategy.calculate_indicators(current_kline_data)
            # In a real scenario, you would get the current price from a live feed.
            current_price = float(current_kline_data.iloc[-1]["close"])
            signal = self.strategy.generate_signal(
                current_kline_data, current_price, {}
            )
            self.logger.info(f"Generated Signal: {signal.type}, Score: {signal.score}")
        else:
            self.logger.critical("No strategy loaded.")

    async def start(self):
        self.logger.info("Starting bot...")
        while self.is_running:
            await self.trading_logic()
            await asyncio.sleep(self.config.TRADING_LOGIC_LOOP_INTERVAL_SECONDS)

    async def shutdown(self):
        self.logger.info("Shutting down bot...")
        self.is_running = False


async def main():
    config = Config()
    logger = setup_logger(config)
    bot = BybitTradingBot(config)
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    finally:
        await bot.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
