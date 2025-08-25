"""
Logger setup for the Bybit Trading Bot.

This module provides a centralized logging configuration.
"""
import logging
import sys

from config import LOG_FILE, LOG_LEVEL


def setup_logger():
    """Configures and returns a logger instance."""
    logger = logging.getLogger("BybitTradingBot")
    logger.setLevel(LOG_LEVEL)

    # Create handlers
    stream_handler = logging.StreamHandler(sys.stdout)
    file_handler = logging.FileHandler(LOG_FILE)

    # Create formatters and add it to handlers
    log_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    stream_handler.setFormatter(log_format)
    file_handler.setFormatter(log_format)

    # Add handlers to the logger
    if not logger.handlers:
        logger.addHandler(stream_handler)
        logger.addHandler(file_handler)

    return logger

# Initialize and export the logger
logger = setup_logger()
