# bot_logger.py
import logging
import os
import json
from color_codex import COLOR_RESET, COLOR_BOLD, COLOR_RED, COLOR_GREEN, COLOR_YELLOW, COLOR_BLUE, COLOR_MAGENTA, COLOR_CYAN, PYRMETHUS_BLUE, PYRMETHUS_ORANGE, PYRMETHUS_GREY

# Define custom log levels
TRADE_LEVEL = 25  # Between INFO (20) and WARNING (30)
METRICS_LEVEL = 26 # Between INFO (20) and WARNING (30)

def setup_logging():
    """
    Sets up the bot's logging configuration with file and console handlers.
    """
    log_file = 'scalper_bot.log'

    # Register custom levels if not already registered
    if not hasattr(logging, 'TRADE'):
        logging.addLevelName(TRADE_LEVEL, 'TRADE')
    if not hasattr(logging, 'METRICS'):
        logging.addLevelName(METRICS_LEVEL, 'METRICS')

    # Create a custom logger
    bot_logger = logging.getLogger('scalper_bot')
    bot_logger.setLevel(logging.DEBUG) # Overall minimum level

    # Ensure root logger also processes DEBUG messages
    logging.getLogger().setLevel(logging.DEBUG)
    return bot_logger
    return bot_logger

def log_trade(logger: logging.Logger, message: str, trade_data: dict):
    """
    Logs a trade event with structured data.
    """
    logger.log(TRADE_LEVEL, f"{message} - {json.dumps(trade_data)}")

def log_metrics(logger: logging.Logger, message: str, metrics_data: dict):
    """
    Logs trade metrics with structured data.
    """
    logger.log(METRICS_LEVEL, f"{message} - {json.dumps(metrics_data)}")

def log_exception(logger: logging.Logger, message: str, exc: Exception):
    """
    Logs an exception with traceback.
    """
    logger.error(message, exc_info=exc)