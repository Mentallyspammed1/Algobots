# bot_logger.py
import logging
import os
import json
from logging.handlers import RotatingFileHandler
from color_codex import (
    COLOR_RESET, COLOR_BOLD, COLOR_RED, COLOR_GREEN, COLOR_YELLOW,
    COLOR_BLUE, COLOR_MAGENTA, COLOR_CYAN, PYRMETHUS_ORANGE, PYRMETHUS_GREY
)
from typing import Optional
from utils import json_decimal_default

# Define custom log levels
TRADE_LEVEL = 25
METRICS_LEVEL = 26

# Custom Logger class to add 'trade' and 'metrics' methods
class CustomBotLogger(logging.Logger):
    def trade(self, msg, *args, **kwargs):
        if self.isEnabledFor(TRADE_LEVEL):
            self._log(TRADE_LEVEL, msg, args, **kwargs)

    def metrics(self, msg, *args, **kwargs):
        if self.isEnabledFor(METRICS_LEVEL):
            self._log(METRICS_LEVEL, msg, args, **kwargs)

# Set the custom logger class
logging.setLoggerClass(CustomBotLogger)

class TradeLogFilter(logging.Filter):
    """This filter allows only logs with TRADE_LEVEL to pass."""
    def filter(self, record):
        return record.levelno == TRADE_LEVEL

class MetricsLogFilter(logging.Filter):
    """This filter allows only logs with METRICS_LEVEL to pass."""
    def filter(self, record):
        return record.levelno == METRICS_LEVEL

# Custom JSON formatter
class JsonFormatter(logging.Formatter):
    def __init__(self, fmt: Optional[str] = None, datefmt: Optional[str] = None, style: str = '%', validate: bool = True):
        super().__init__(fmt, datefmt, style, validate)

    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger_name": record.name,
            # Add other useful record attributes
            "filename": record.filename,
            "lineno": record.lineno,
            "funcname": record.funcName,
        }
        # Attempt to parse message as JSON if it seems to contain structured data
        try:
            # If the message starts with { and ends with }, it might be a JSON string from json.dumps
            if log_record["message"].strip().startswith('{') and log_record["message"].strip().endswith('}'):
                # Try to load it as a dictionary and merge
                data_part = json.loads(log_record["message"].strip())
                log_record.update(data_part)
                log_record["message"] = "" # Clear original message if content moved to fields
            elif " - {" in log_record["message"] and log_record["message"].endswith("}"):
                 # Handle "message - {json_string}" format from log_trade/log_metrics
                 parts = log_record["message"].split(' - {', 1)
                 if len(parts) == 2:
                     base_message = parts[0].strip()
                     json_data_str = "{" + parts[1]
                     try:
                         data_part = json.loads(json_data_str)
                         log_record["message"] = base_message # Keep descriptive message
                         log_record.update(data_part) # Add structured data
                     except json.JSONDecodeError:
                         pass # Not valid JSON, keep message as is
        except Exception:
            pass # Keep message as is if not valid JSON

        # Handle exception info
        if record.exc_info:
            log_record['exc_info'] = self.formatException(record.exc_info)
        if record.stack_info:
            log_record['stack_info'] = self.formatStack(record.stack_info)

        return json.dumps(log_record)


def setup_logging(console_log_level: int = logging.INFO):
    """
    Sets up a more advanced logging configuration with multiple handlers and formatters.
    - A console handler for real-time, colorful output.
    - A rotating file handler for general bot logs (`bot.log`).
    - A dedicated file handler for trade-specific logs (`trades.log`).
    - A dedicated file handler for metrics logs (`metrics.log`).

    Args:
        console_log_level (int): The minimum level for messages to be displayed in the console.
                                 Defaults to logging.INFO.
    """
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True) # Use exist_ok=True for robustness

    # Register custom levels if not already registered
    if not hasattr(logging, 'TRADE'):
        logging.addLevelName(TRADE_LEVEL, 'TRADE')
    if not hasattr(logging, 'METRICS'):
        logging.addLevelName(METRICS_LEVEL, 'METRICS')

    # Get the custom logger instance
    bot_logger = logging.getLogger('PyrmethusBot')
    bot_logger.setLevel(logging.DEBUG) # Set logger to lowest level to capture all messages

    # Prevent duplicate handlers if this function is called multiple times
    if bot_logger.hasHandlers():
        bot_logger.handlers.clear()

    # --- Console Handler ---
    console_formatter = logging.Formatter(
        f'{PYRMETHUS_ORANGE}[%(asctime)s]{COLOR_RESET} {PYRMETHUS_GREY}[%(levelname)-7s]{COLOR_RESET} {COLOR_CYAN}[%(name)s]{COLOR_RESET} %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(console_log_level) # Configurable console level

    # --- General File Handler ---
    log_file_path = os.path.join(log_dir, 'bot.log')
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
    file_handler = RotatingFileHandler(log_file_path, maxBytes=5*1024*1024, backupCount=2)
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(logging.DEBUG) # Log everything to the general log file

    # --- Trade File Handler (JSON Format) ---
    trade_log_path = os.path.join(log_dir, 'trades.log')
    trade_handler = logging.FileHandler(trade_log_path)
    trade_handler.setFormatter(JsonFormatter(datefmt='%Y-%m-%d %H:%M:%S,%f')) # Use JSON formatter for trades
    trade_handler.setLevel(TRADE_LEVEL)
    trade_handler.addFilter(TradeLogFilter()) # Only log TRADE messages
    
    # --- Metrics File Handler (JSON Format) ---
    metrics_log_path = os.path.join(log_dir, 'metrics.log')
    metrics_handler = logging.FileHandler(metrics_log_path)
    metrics_handler.setFormatter(JsonFormatter(datefmt='%Y-%m-%d %H:%M:%S,%f')) # Use JSON formatter for metrics
    metrics_handler.setLevel(METRICS_LEVEL)
    metrics_handler.addFilter(MetricsLogFilter()) # Only log METRICS messages


    # Add handlers to the logger
    bot_logger.addHandler(console_handler)
    bot_logger.addHandler(file_handler)
    bot_logger.addHandler(trade_handler)
    bot_logger.addHandler(metrics_handler) # Add metrics handler

    # Also configure root logger to INFO to prevent excessive third-party library logging
    # This is less ideal than configuring specific library loggers, but works as a broad filter.
    logging.getLogger().setLevel(logging.INFO)

    return bot_logger

def log_trade(logger: logging.Logger, message: str, trade_data: dict):
    """Logs a trade event with structured data to the TRADE level."""
    # Directly call the custom method, which now exists on CustomBotLogger instances
    logger.trade(f"{message} - {json.dumps(trade_data, default=json_decimal_default)}")

def log_metrics(logger: logging.Logger, message: str, metrics_data: dict):
    """Logs trade metrics with structured data."""
    # Directly call the custom method
    logger.metrics(f"{message} - {json.dumps(metrics_data, default=json_decimal_default)}")

def log_exception(logger: logging.Logger, message: str, exc: Exception):
    """Logs an exception with traceback."""
    logger.error(message, exc_info=exc) # exc_info=True logs current exception if no exc provided

