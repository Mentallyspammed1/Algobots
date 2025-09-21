"""Logger setup for the Bybit Trading Bot.

This module provides a centralized logging configuration.
"""
import logging
import sys
from typing import Any

# Define logging parameters directly in this module
LOG_FILE = "psg_bot.log"
LOG_LEVEL = logging.INFO  # Default to INFO. Options: logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL


def setup_logging():  # Renamed from setup_logger to match import
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

def log_exception(logger_instance: logging.Logger, message: str, exc: Exception):
    """Logs an exception with a custom message and traceback."""
    logger_instance.exception(f"{message}: {exc}")

def log_metrics(logger_instance: logging.Logger, title: str, metrics: dict[str, Any]):
    """Logs a dictionary of metrics with a title."""
    metrics_str = ", ".join([f"{k}={v}" for k, v in metrics.items()])
    logger_instance.info(f"📊 {title}: {metrics_str}")

def log_trade(logger_instance: logging.Logger, title: str, trade_info: dict[str, Any]):
    """Logs trade information."""
    trade_str = ", ".join([f"{k}={v}" for k, v in trade_info.items()])
    logger_instance.info(f"TRADE - {title}: {trade_str}")


# Initialize and export the logger for general use, though PSG.py uses the setup function.
logger = setup_logging()