# bot_logger.py
import logging
import os
import json
from logging.handlers import RotatingFileHandler
from color_codex import (
    COLOR_RESET, COLOR_BOLD, COLOR_RED, COLOR_GREEN, COLOR_YELLOW,
    COLOR_BLUE, COLOR_MAGENTA, COLOR_CYAN, PYRMETHUS_ORANGE, PYRMETHUS_GREY
)

# Define custom log levels
TRADE_LEVEL = 25
METRICS_LEVEL = 26

class TradeLogFilter(logging.Filter):
    """This filter allows only logs with TRADE_LEVEL to pass."""
    def filter(self, record):
        return record.levelno == TRADE_LEVEL

def setup_logging():
    """
    Sets up a more advanced logging configuration with multiple handlers and formatters.
    - A console handler for real-time, colorful output.
    - A rotating file handler for general bot logs (`bot.log`).
    - A dedicated file handler for trade-specific logs (`trades.log`).
    """
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Register custom levels
    if not hasattr(logging, 'TRADE'):
        logging.addLevelName(TRADE_LEVEL, 'TRADE')
        setattr(logging, 'TRADE', TRADE_LEVEL)
    if not hasattr(logging, 'METRICS'):
        logging.addLevelName(METRICS_LEVEL, 'METRICS')
        setattr(logging, 'METRICS', METRICS_LEVEL)

    bot_logger = logging.getLogger('PyrmethusBot')
    bot_logger.setLevel(logging.DEBUG) # Set logger to lowest level to capture all messages

    # Prevent duplicate handlers if this function is called multiple times
    if bot_logger.hasHandlers():
        bot_logger.handlers.clear()

    # --- Console Handler ---
    console_formatter = logging.Formatter(
        f'{PYRMETHUS_ORANGE}[%(asctime)s]{COLOR_RESET} {PYRMETHUS_GREY}[%(levelname)-7s]{COLOR_RESET} %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.INFO) # Only show INFO and above on console

    # --- General File Handler ---
    log_file_path = os.path.join(log_dir, 'bot.log')
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler = RotatingFileHandler(log_file_path, maxBytes=5*1024*1024, backupCount=2)
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(logging.DEBUG) # Log everything to the general log file

    # --- Trade File Handler ---
    trade_log_path = os.path.join(log_dir, 'trades.log')
    trade_formatter = logging.Formatter('%(asctime)s - %(message)s')
    trade_handler = logging.FileHandler(trade_log_path)
    trade_handler.setFormatter(trade_formatter)
    trade_handler.setLevel(TRADE_LEVEL)
    trade_handler.addFilter(TradeLogFilter()) # Only log TRADE messages

    # Add handlers to the logger
    bot_logger.addHandler(console_handler)
    bot_logger.addHandler(file_handler)
    bot_logger.addHandler(trade_handler)

    # Also configure root logger for libraries if needed
    logging.getLogger().setLevel(logging.INFO)

    return bot_logger

def log_trade(logger: logging.Logger, message: str, trade_data: dict):
    """Logs a trade event with structured data to the TRADE level."""
    # Use a custom method on the logger if it exists, otherwise use default
    if hasattr(logger, 'trade'):
        logger.trade(f"{message} - {json.dumps(trade_data)}")
    else:
        logger.log(TRADE_LEVEL, f"{message} - {json.dumps(trade_data)}")

def log_metrics(logger: logging.Logger, message: str, metrics_data: dict):
    """Logs trade metrics with structured data."""
    if hasattr(logger, 'metrics'):
        logger.metrics(f"{message} - {json.dumps(metrics_data)}")
    else:
        logger.log(METRICS_LEVEL, f"{message} - {json.dumps(metrics_data)}")

def log_exception(logger: logging.Logger, message: str, exc: Exception):
    """Logs an exception with traceback."""
    logger.error(message, exc_info=exc)
