import logging
import os
import sys
from pathlib import Path

from colorama import Fore
from colorama import Style

# Neon Color Scheme
NEON_GREEN = Fore.LIGHTGREEN_EX
NEON_BLUE = Fore.CYAN
NEON_PURPLE = Fore.MAGENTA
NEON_YELLOW = Fore.YELLOW
NEON_RED = Fore.LIGHTRED_EX
NEON_CYAN = Fore.CYAN
RESET = Style.RESET_ALL

LOG_DIRECTORY = "bot_logs/trading-bot/logs"
Path(LOG_DIRECTORY).mkdir(parents=True, exist_ok=True)


# A simple class to adapt the config dict to what setup_logger expects
class UnanimousLoggerConfig:
    def __init__(self, config_dict):
        # Extract log level from config, default to INFO
        self.LOG_LEVEL = config_dict.get("log_level", "INFO").upper()

        # Construct log file path from constants defined in the script
        log_filename = config_dict.get("log_filename", "wb.log")
        self.LOG_FILE_PATH = os.path.join(LOG_DIRECTORY, log_filename)

        # Pass color codes
        self.NEON_BLUE = NEON_BLUE
        self.RESET = RESET


def setup_logging(config):
    # Determine if unanimous_logger is available and set up the logger
    try:
        from unanimous_logger import setup_logger

        logger_config = UnanimousLoggerConfig(config)
        logger = setup_logger(logger_config, log_name="wb", json_log_file="wb.json.log")
        return logger
    except ImportError:
        print("unanimous_logger not found, using basic logging setup.")

        class BasicLoggerConfig:
            def __init__(self, config_dict):
                self.LOG_LEVEL = config_dict.get("log_level", "INFO").upper()
                log_filename = config_dict.get("log_filename", "wb.log")
                self.LOG_FILE_PATH = os.path.join(LOG_DIRECTORY, log_filename)

        def setup_basic_logger(config_obj, log_name="default", json_log_file=None):
            logger = logging.getLogger(log_name)
            logger.setLevel(getattr(logging, config_obj.LOG_LEVEL))

            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            )

            # Stream handler
            if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
                ch = logging.StreamHandler(sys.stdout)
                ch.setLevel(getattr(logging, config_obj.LOG_LEVEL))
                ch.setFormatter(formatter)
                logger.addHandler(ch)

            # File handler
            if not any(
                isinstance(h, logging.FileHandler)
                and h.baseFilename == config_obj.LOG_FILE_PATH
                for h in logger.handlers
            ):
                fh = logging.FileHandler(config_obj.LOG_FILE_PATH)
                fh.setLevel(getattr(logging, config_obj.LOG_LEVEL))
                fh.setFormatter(formatter)
                logger.addHandler(fh)

            # Optional JSON file handler
            if json_log_file:
                json_log_path = os.path.join(LOG_DIRECTORY, json_log_file)
                if not any(
                    isinstance(h, logging.FileHandler)
                    and h.baseFilename == json_log_path
                    for h in logger.handlers
                ):
                    json_formatter = logging.Formatter(
                        """{"time": "%(asctime)s", "name": "%(name)s", "level": "%(levelname)s", "message": "%(message)s"}""",
                    )
                    json_fh = logging.FileHandler(json_log_path)
                    json_fh.setLevel(getattr(logging, config_obj.LOG_LEVEL))
                    json_fh.setFormatter(json_formatter)
                    logger.addHandler(json_fh)
            return logger

        logger_config = BasicLoggerConfig(config)
        logger = setup_basic_logger(
            logger_config,
            log_name="wb",
            json_log_file="wb.json.log",
        )
        return logger


# Create a temporary basic logger for the initial config loading
temp_logger = logging.getLogger("config_loader")
temp_logger.setLevel(logging.INFO)
if not temp_logger.handlers:
    temp_logger.addHandler(logging.StreamHandler(sys.stdout))
