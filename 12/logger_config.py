# logger_config.py
import logging
import os
from datetime import datetime


def setup_custom_logger(name):
    log_directory = "bot_logs"
    os.makedirs(log_directory, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join(log_directory, f"{name}_{timestamp}.log")

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False # Prevent log messages from being propagated to the root logger

    # File Handler
    file_handler = logging.FileHandler(log_filename)
    file_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Stream Handler (console output)
    stream_handler = logging.StreamHandler()
    stream_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    stream_handler.setFormatter(stream_formatter)
    logger.addHandler(stream_handler)

    return logger
