# main.py

import argparse  # For CLI arguments
import asyncio
import os
import sys

# Ensure project root is in PYTHONPATH if running from a subdirectory
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from bybit_trading_bot import BybitTradingBot
from config import Config
from logger_setup import setup_logger


async def main():
    """Main entry point for running the trading bot."""
    # 1. Parse Command Line Arguments
    parser = argparse.ArgumentParser(description="Run Bybit Trading Bot.")
    parser.add_argument(
        "--symbol",
        type=str,
        help=f"Trading symbol (e.g., BTCUSDT). Default: {Config.SYMBOL}",
    )
    parser.add_argument(
        "--category",
        type=str,
        help=f"Trading category (e.g., linear). Default: {Config.CATEGORY}",
    )
    parser.add_argument(
        "--testnet",
        action="store_true",
        help="Use Bybit testnet. Default: True (from config)",
    )
    parser.add_argument(
        "--mainnet",
        action="store_true",
        help="Use Bybit mainnet. Overrides --testnet.",
    )
    parser.add_argument(
        "--log_level",
        type=str,
        help=f"Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL). Default: {Config.LOG_LEVEL}",
    )
    parser.add_argument(
        "--strategy_module",
        type=str,
        help=f"Strategy module name. Default: {Config.ACTIVE_STRATEGY_MODULE}",
    )
    parser.add_argument(
        "--strategy_class",
        type=str,
        help=f"Strategy class name. Default: {Config.ACTIVE_STRATEGY_CLASS}",
    )
    parser.add_argument(
        "--daily_drawdown",
        type=float,
        help=f"Max daily drawdown percentage. Default: {Config.MAX_DAILY_DRAWDOWN_PERCENT}",
    )
    parser.add_argument(
        "--loop_interval",
        type=float,
        help=f"Trading logic loop interval in seconds. Default: {Config.TRADING_LOGIC_LOOP_INTERVAL_SECONDS}",
    )
    parser.add_argument(
        "--leverage",
        type=float,
        help=f"Leverage to use. Default: {Config.LEVERAGE}",
    )
    parser.add_argument(
        "--order_size_usd",
        type=float,
        help=f"Order size in USD value. Default: {Config.ORDER_SIZE_USD_VALUE}",
    )
    parser.add_argument(
        "--risk_per_trade",
        type=float,
        help=f"Risk percentage per trade. Default: {Config.RISK_PER_TRADE_PERCENT}",
    )
    parser.add_argument(
        "--klines_interval",
        type=str,
        help=f"Kline interval for strategy. Default: {Config.KLINES_INTERVAL}",
    )
    parser.add_argument(
        "--klines_lookback",
        type=int,
        help=f"Kline lookback limit. Default: {Config.KLINES_LOOKBACK_LIMIT}",
    )
    parser.add_argument(
        "--klines_offset_minutes",
        type=int,
        help=f"Kline start offset in minutes. Default: {Config.KLINES_HISTORY_WINDOW_MINUTES}",
    )

    args = parser.parse_args()

    # 2. Load Configuration
    config = Config()  # Loads defaults and overrides from environment variables

    # Apply CLI overrides to config
    if args.symbol:
        config.SYMBOL = args.symbol
    if args.category:
        config.CATEGORY = args.category
    if args.mainnet:
        config.TESTNET = False  # Mainnet takes precedence
    elif args.testnet:
        config.TESTNET = True
    if args.log_level:
        config.LOG_LEVEL = args.log_level.upper()
    if args.strategy_module:
        config.ACTIVE_STRATEGY_MODULE = args.strategy_module
    if args.strategy_class:
        config.ACTIVE_STRATEGY_CLASS = args.strategy_class
    if args.daily_drawdown:
        config.MAX_DAILY_DRAWDOWN_PERCENT = args.daily_drawdown
    if args.loop_interval:
        config.TRADING_LOGIC_LOOP_INTERVAL_SECONDS = args.loop_interval
    if args.leverage:
        config.LEVERAGE = args.leverage
    if args.order_size_usd:
        config.ORDER_SIZE_USD_VALUE = args.order_size_usd
    if args.risk_per_trade:
        config.RISK_PER_TRADE_PERCENT = args.risk_per_trade
    if args.klines_interval:
        config.KLINES_INTERVAL = args.klines_interval
    if args.klines_lookback:
        config.KLINES_LOOKBACK_LIMIT = args.klines_lookback
    if args.klines_offset_minutes:
        config.KLINES_HISTORY_WINDOW_MINUTES = args.klines_offset_minutes

    # 3. Setup Logger
    logger = setup_logger(config)

    # 4. Validate API Keys
    if not config.BYBIT_API_KEY:
        logger.critical(
            "BYBIT_API_KEY environment variable is NOT set. Please set it before running the bot.",
        )
        sys.exit(1)
    if not config.BYBIT_API_SECRET:
        logger.critical(
            "BYBIT_API_SECRET environment variable is NOT set. Please set it before running the bot.",
        )
        sys.exit(1)

    if config.GEMINI_AI_ENABLED and not config.GEMINI_API_KEY:
        logger.critical(
            "GEMINI_AI_ENABLED is True, but GEMINI_API_KEY environment variable is NOT set. Please set it or disable AI in config.py.",
        )
        sys.exit(1)

    if config.ALERT_TELEGRAM_ENABLED and (
        not config.ALERT_TELEGRAM_BOT_TOKEN or not config.ALERT_TELEGRAM_CHAT_ID
    ):
        logger.critical(
            "ALERT_TELEGRAM_ENABLED is True, but ALERT_TELEGRAM_BOT_TOKEN or ALERT_TELEGRAM_CHAT_ID are NOT set. Please set them or disable Telegram alerts in config.py.",
        )
        sys.exit(1)

    # 5. Create and Run Bot
    bot = BybitTradingBot(config)

    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt detected. Stopping bot gracefully...")
    except Exception as e:
        logger.critical(
            f"An unhandled exception occurred during bot execution: {e}",
            exc_info=True,
        )
    finally:
        # bot.shutdown() is called in bot.start() after the main loop or on exception
        pass


if __name__ == "__main__":
    asyncio.run(main())
