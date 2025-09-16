"""Main entry point for the Bybit Trading Bot.

This script initializes the BybitTrader and starts the bot.
"""
from bot_logger import logger
from bybit_trader import BybitTrader
from config import STRATEGY_FILE


def main():
    """Initializes and runs the trading bot.
    """
    logger.info("Initializing trading bot...")
    try:
        trader = BybitTrader(strategy_path=STRATEGY_FILE)
        trader.start()
    except Exception as e:
        logger.critical(f"Failed to start the bot: {e}", exc_info=True)

if __name__ == "__main__":
    main()
