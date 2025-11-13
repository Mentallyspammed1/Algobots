import logging
from typing import Literal

from colorama import Fore

NEON_BLUE = Fore.CYAN
NEON_YELLOW = Fore.YELLOW
NEON_RED = Fore.LIGHTRED_EX
RESET = Fore.RESET


class AlertSystem:
    """Handles sending alerts for critical events."""

    def __init__(self, logger: logging.Logger):
        """Initializes the AlertSystem."""
        self.logger = logger

    def send_alert(
        self,
        message: str,
        level: Literal["INFO", "WARNING", "ERROR"],
    ) -> None:
        """Send an alert (currently logs it)."""
        if level == "INFO":
            self.logger.info(f"{NEON_BLUE}ALERT: {message}{RESET}")
        elif level == "WARNING":
            self.logger.warning(f"{NEON_YELLOW}ALERT: {message}{RESET}")
        elif level == "ERROR":
            self.logger.error(f"{NEON_RED}ALERT: {message}{RESET}")
        # In a real bot, integrate with Telegram, Discord, Email etc.
