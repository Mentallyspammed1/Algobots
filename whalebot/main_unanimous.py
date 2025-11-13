import asyncio
import logging

from bybit_trading_bot import BybitTradingBot
from config import Config
from unanimous_logger import setup_logger


async def main():
    # Load configuration
    config = Config()

    # Set up the logger to output in the format expected by the trading-bot
    # This will create a unanimous.log file in the bot_logs directory
    setup_logger(config, log_name="TradingBot", trading_bot_log_file="unanimous.log")
    logger = logging.getLogger("TradingBot")

    # Create and run the bot
    bot = BybitTradingBot(config)
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    finally:
        await bot.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
