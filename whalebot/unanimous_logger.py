# unanimous_logger.py

import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import ClassVar

from config import Config


class SensitiveFormatter(logging.Formatter):
    """Formatter that redacts API keys from log records."""

    SENSITIVE_WORDS: ClassVar[list[str]] = ["BYBIT_API_KEY", "BYBIT_API_SECRET", "GEMINI_API_KEY", "ALERT_TELEGRAM_BOT_TOKEN"]

    def __init__(self, fmt=None, datefmt=None, style="%"):
        """Initializes the SensitiveFormatter."""
        super().__init__(fmt, datefmt, style)
        self._fmt = fmt if fmt else self.default_fmt()

    def default_fmt(self):
        """Returns the default log format string."""
        return "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    def format(self, record):
        """Formats the log record, redacting sensitive words."""
        original_message = super().format(record)
        redacted_message = original_message
        for word in self.SENSITIVE_WORDS:
            key_value = os.getenv(word, '')
            if key_value:
                redacted_message = redacted_message.replace(key_value, "*" * len(key_value))
            redacted_message = redacted_message.replace(word, "*" * len(word))

        return redacted_message

class JSONFormatter(logging.Formatter):
    """Formatter that outputs log records as a JSON string.
    """
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "name": record.name,
            "level": record.levelname,
            "message": record.getMessage(),
        }
        if isinstance(record.args, dict):
            log_record.update(record.args)
        return json.dumps(log_record)

class TradingBotFormatter(logging.Formatter):
    """Formatter that outputs log records in a format that the trading-bot can parse.
    """
    def format(self, record):
        message = record.getMessage()
        if record.args and isinstance(record.args, dict):
            message += " " + json.dumps(record.args)
        return f"{self.formatTime(record, self.datefmt)} - {record.name} - {record.levelname} - {message}"

def setup_logger(config: Config, log_name: str = "TradingBot", json_log_file: str = None, trading_bot_log_file: str = None) -> logging.Logger:
    """Configure and return a logger with file, console, and optional JSON handlers."""
    logger = logging.getLogger(log_name)
    logger.setLevel(getattr(logging, config.LOG_LEVEL.upper()))
    logger.propagate = False

    if not logger.handlers:
        log_dir = Path(config.LOG_FILE_PATH).parent
        log_dir.mkdir(parents=True, exist_ok=True)

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(
            SensitiveFormatter(
                f"{config.NEON_BLUE}%(asctime)s - %(levelname)s - %(message)s{config.RESET}"
            )
        )
        logger.addHandler(console_handler)

        file_handler = RotatingFileHandler(
            config.LOG_FILE_PATH, maxBytes=10 * 1024 * 1024, backupCount=5
        )
        file_handler.setFormatter(
            SensitiveFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(file_handler)

        if json_log_file:
            json_log_path = log_dir / json_log_file
            json_handler = RotatingFileHandler(
                json_log_path, maxBytes=10 * 1024 * 1024, backupCount=5
            )
            json_handler.setFormatter(JSONFormatter())
            logger.addHandler(json_handler)

        if trading_bot_log_file:
            trading_bot_log_path = log_dir / trading_bot_log_file
            trading_bot_handler = RotatingFileHandler(
                trading_bot_log_path, maxBytes=10 * 1024 * 1024, backupCount=5
            )
            trading_bot_handler.setFormatter(TradingBotFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
            logger.addHandler(trading_bot_handler)

    return logger
