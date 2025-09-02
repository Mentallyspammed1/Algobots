# alert_system.py

import logging
import time
from typing import Dict, Any, Optional
import requests
import asyncio
import hashlib # For alert_type hashing

from config import Config

class AlertSystem:
    """
    Handles sending alerts for critical bot events.
    Can be extended to integrate with Telegram, Discord, etc.
    """

    def __init__(self, config: Config, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.last_alert_times: Dict[str, float] = {} # {alert_message_hash: last_sent_timestamp}
        self.alert_cooldown_seconds = config['alert_system']['ALERT_COOLDOWN_SECONDS']

        if self.config['alert_system']['ALERT_TELEGRAM_ENABLED']:
            if not self.config['alert_system']['ALERT_TELEGRAM_BOT_TOKEN'] or not self.config['alert_system']['ALERT_TELEGRAM_CHAT_ID']:
                self.logger.error("Telegram alerting enabled but BOT_TOKEN or CHAT_ID are missing. Disabling Telegram alerts.")
                self.config.ALERT_TELEGRAM_ENABLED = False
            else:
                self.logger.info("Telegram alerting is enabled.")

    async def send_alert(self, message: str, level: str = "INFO", alert_type: str = "GENERIC") -> bool:
        """
        Sends an alert if the level is sufficient and cooldown allows.
        Uses asyncio.to_thread to send Telegram messages without blocking the event loop.

        Args:
            message: The alert message.
            level: The severity level (e.g., "INFO", "WARNING", "ERROR", "CRITICAL").
            alert_type: A category for the alert (e.g., "ERROR", "POSITION_CHANGE", "SIGNAL").
                        Used for cooldown tracking to prevent spamming similar alerts.
                        A hash of the message can be used as alert_type if unique messages need individual cooldowns.

        Returns:
            True if the alert was sent, False otherwise.
        """
        # Convert level string to logging level integer for comparison
        log_level_int = getattr(logging, level.upper(), logging.INFO)
        config_alert_level_int = getattr(logging, self.config['alert_system']['ALERT_CRITICAL_LEVEL'].upper(), logging.WARNING)

        # Log the alert internally regardless of external sending
        if log_level_int >= logging.CRITICAL:
            self.logger.critical(f"ALERT: {message}")
        elif log_level_int >= logging.ERROR:
            self.logger.error(f"ALERT: {message}")
        elif log_level_int >= logging.WARNING:
            self.logger.warning(f"ALERT: {message}")
        else:
            self.logger.info(f"ALERT: {message}")
        
        # Check if external alert should be sent based on level and cooldown
        if log_level_int < config_alert_level_int:
            return False # Level not critical enough for external alert

        # Generate a unique key for cooldown tracking
        cooldown_key = hashlib.md5(f"{alert_type}-{message}".encode('utf-8')).hexdigest()
        
        current_time = time.time()
        if cooldown_key in self.last_alert_times and \
           (current_time - self.last_alert_times[cooldown_key]) < self.alert_cooldown_seconds:
            self.logger.debug(f"Alert of type '{alert_type}' (key: {cooldown_key[:8]}) on cooldown. Skipping external send.")
            return False

        # Try sending to Telegram
        if self.config['alert_system']['ALERT_TELEGRAM_ENABLED']:
            # Use asyncio.to_thread to run the blocking requests.post call in a separate thread
            # This prevents blocking the main asyncio event loop.
            success = await asyncio.to_thread(self._send_telegram_message_sync, message, level)
            if success:
                self.last_alert_times[cooldown_key] = current_time
                return True
            return False
        
        return False # No external alert sent (e.g., Telegram disabled or failed)

    def _send_telegram_message_sync(self, message: str, level: str = "INFO") -> bool:
        """Synchronous helper to send a message to a Telegram chat using requests.post."""
        if not self.config['ALERT_TELEGRAM_BOT_TOKEN'] or not self.config['ALERT_TELEGRAM_CHAT_ID']:
            self.logger.error("Telegram bot token or chat ID is not set for sending message.")
            return False

        telegram_url = f"https://api.telegram.org/bot{self.config['ALERT_TELEGRAM_BOT_TOKEN']}/sendMessage"
        
        emoji = "ℹ️"
        if level.upper() == "WARNING": emoji = "⚠️"
        elif level.upper() == "ERROR": emoji = "❌"
        elif level.upper() == "CRITICAL": emoji = "🔥"

        full_message = f"{emoji} {level.upper()}: {message}"

        payload = {
            'chat_id': self.config['ALERT_TELEGRAM_CHAT_ID'],
            'text': full_message,
            'parse_mode': 'HTML'
        }
        
        try:
            response = requests.post(telegram_url, data=payload, timeout=10) # Increased timeout
            response.raise_for_status() 
            self.logger.debug(f"Telegram alert sent (sync): {response.json()}")
            return True
        except requests.exceptions.Timeout:
            self.logger.error("Telegram API request timed out (sync).")
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error sending Telegram alert (sync): {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error in Telegram alert (sync): {e}")
        return False