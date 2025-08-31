
# logger_setup.py

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import ClassVar

from config import Config

class SensitiveFormatter(logging.Formatter):
    """Formatter that redacts API keys from log records."""

    SENSITIVE_WORDS: ClassVar[list[str]] = ["BYBIT_API_KEY", "BYBIT_API_SECRET", "GEMINI_API_KEY", "ALERT_TELEGRAM_BOT_TOKEN"] # Updated names

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
            # Replace the actual value if it's found in the message
            key_value = os.getenv(word, '')
            if key_value:
                redacted_message = redacted_message.replace(key_value, "*" * len(key_value))
            # Also replace the keyword itself (e.g., "BYBIT_API_KEY")
            redacted_message = redacted_message.replace(word, "*" * len(word))

        return redacted_message


def setup_logger(config: Config, log_name: str = "TradingBot") -> logging.Logger:
    """Configure and return a logger with file and console handlers."""
    logger = logging.getLogger(log_name)
    logger.setLevel(getattr(logging, config.LOG_LEVEL.upper()))
    logger.propagate = False  # Prevent messages from being passed to the root logger

    # Ensure handlers are not duplicated
    if not logger.handlers:
        # Create log directory if it doesn't exist
        log_dir = Path(config.LOG_FILE_PATH).parent
        log_dir.mkdir(parents=True, exist_ok=True)

        # Console Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(
            SensitiveFormatter(
                f"{config.NEON_BLUE}%(asctime)s - %(levelname)s - %(message)s{config.RESET}"
            )
        )
        logger.addHandler(console_handler)

        # File Handler
        file_handler = RotatingFileHandler(
            config.LOG_FILE_PATH, maxBytes=10 * 1024 * 1024, backupCount=5
        )
        file_handler.setFormatter(
            SensitiveFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(file_handler)

    return logger
