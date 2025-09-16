# alert_system.py

import logging
import subprocess

from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

NEON_RED = Fore.LIGHTRED_EX
NEON_YELLOW = Fore.YELLOW

class AlertSystem:
    """Handles sending alerts for critical bot events using Termux toast notifications.
    """

    def __init__(self, logger: logging.Logger):
        """Initializes the AlertSystem.

        Args:
            logger: The logger instance to use for logging.
        """
        self.logger = logger

    def send_alert(self, message: str, level: str = "INFO"):
        """Sends an alert using termux-toast.

        Args:
            message: The alert message to display.
            level: The severity level (e.g., "INFO", "WARNING", "ERROR").
                   This can be used to colorize the toast in future versions.
        """
        self.logger.info(f"Attempting to send {level} alert: {message}")
        try:
            # Using subprocess.run to send a toast notification
            # The '-s' flag allows the toast to be shown for a shorter duration
            subprocess.run(
                ['termux-toast', message],
                check=True,
                capture_output=True,
                text=True
            )
            self.logger.info("Termux toast alert sent successfully.")
        except FileNotFoundError:
            self.logger.error(
                f"{NEON_RED}The 'termux-toast' command was not found. "
                f"Please ensure the Termux:API app is installed and that you have run 'pkg install termux-api'.{Style.RESET_ALL}"
            )
        except subprocess.CalledProcessError as e:
            self.logger.error(
                f"{NEON_RED}Failed to send Termux toast notification.{Style.RESET_ALL}\n"
                f"{NEON_YELLOW}Stderr: {e.stderr}{Style.RESET_ALL}"
            )
        except Exception as e:
            self.logger.error(f"{NEON_RED}An unexpected error occurred while sending a toast: {e}{Style.RESET_ALL}")
