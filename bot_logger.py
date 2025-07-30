# bot_logger.py
import logging
import os
import json
from color_codex import COLOR_RESET, COLOR_BOLD, COLOR_RED, COLOR_GREEN, COLOR_YELLOW, COLOR_BLUE, COLOR_MAGENTA, COLOR_CYAN, PYRMETHUS_BLUE, PYRMETHUS_ORANGE, PYRMETHUS_GREY

def setup_logging():
    """
    Sets up the bot's logging configuration with file and console handlers.
    """
    log_file = 'scalper_bot.log'

    # Create a custom logger
    bot_logger = logging.getLogger('scalper_bot')
    bot_logger.setLevel(logging.INFO) # Overall minimum level

    # Prevent adding multiple handlers if already configured (e.g., during hot reload)
    if not bot_logger.handlers:
        # File Handler
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO) # File logs all INFO and above
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        bot_logger.addHandler(file_handler)

        # Console Handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO) # Console logs INFO and above

        # Custom formatter for console with colors
        class ColorFormatter(logging.Formatter):
            FORMAT = f"{PYRMETHUS_BLUE}%(asctime)s{COLOR_RESET} - %(levelname)s - %(message)s"

            LOG_COLORS = {
                logging.DEBUG: COLOR_CYAN,
                logging.INFO: COLOR_GREEN,
                logging.WARNING: COLOR_YELLOW,
                logging.ERROR: COLOR_RED,
                logging.CRITICAL: COLOR_BOLD + COLOR_RED,
                # Custom levels for trade events
                500: PYRMETHUS_ORANGE, # For trade execution
                501: PYRMETHUS_GREY, # For trade metrics
            }

            def format(self, record):
                log_fmt = self.FORMAT
                # Add color based on level
                log_fmt = self.LOG_COLORS.get(record.levelno, COLOR_RESET) + log_fmt + COLOR_RESET
                formatter = logging.Formatter(log_fmt)
                return formatter.format(record)

        console_handler.setFormatter(ColorFormatter())
        bot_logger.addHandler(console_handler)

    bot_logger.info("Bot logging initialized.")
    return bot_logger

def log_trade(logger: logging.Logger, message: str, trade_data: dict):
    """
    Logs a trade event with structured data.
    """
    # Define a custom log level for trade events (e.g., 500)
    TRADE_LEVEL = 500
    logging.addLevelName(TRADE_LEVEL, 'TRADE')
    logger.log(TRADE_LEVEL, f"{message} - {json.dumps(trade_data)}")

def log_metrics(logger: logging.Logger, message: str, metrics_data: dict):
    """
    Logs trade metrics with structured data.
    """
    # Define a custom log level for metrics (e.g., 501)
    METRICS_LEVEL = 501
    logging.addLevelName(METRICS_LEVEL, 'METRICS')
    logger.log(METRICS_LEVEL, f"{message} - {json.dumps(metrics_data)}")

def log_exception(logger: logging.Logger, message: str, exc: Exception):
    """
    Logs an exception with traceback.
    """
    logger.error(message, exc_info=exc)