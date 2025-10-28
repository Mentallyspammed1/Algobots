import logging
import sys
from unittest.mock import MagicMock, patch

import pytest
from whalebot_pro.utils.logger_setup import LOG_DIRECTORY, setup_logging


# Mock the Path.mkdir call
@pytest.fixture(autouse=True)
def mock_path_mkdir():
    with patch("pathlib.Path.mkdir") as mock_mkdir:
        yield mock_mkdir


# Mock os.path.join for consistent file paths in tests
@pytest.fixture(autouse=True)
def mock_os_path_join():
    with patch("os.path.join", side_effect=lambda *args: "/".join(args)) as mock_join:
        yield mock_join


# Test basic logging setup (when unanimous_logger is not available)
def test_basic_logging_setup(mock_path_mkdir, mock_os_path_join):
    with patch.dict(
        sys.modules,
        {"unanimous_logger": None},
    ):  # Simulate unanimous_logger not found
        config_dict = {"log_level": "DEBUG", "log_filename": "test_basic.log"}
        logger = setup_logging(config_dict)

        assert logger.name == "wb"
        assert logger.level == logging.DEBUG

        # Check if stream handler is added
        assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)
        # Check if file handler is added
        assert any(
            isinstance(h, logging.FileHandler)
            and h.baseFilename == f"{LOG_DIRECTORY}/test_basic.log"
            for h in logger.handlers
        )

        # Test logging output (optional, requires capturing stdout/file content)
        # For simplicity, we just check handlers are configured.


# Test unanimous_logger setup (when available)
def test_unanimous_logger_setup(mock_path_mkdir, mock_os_path_join):
    # Mock unanimous_logger module
    mock_unanimous_logger = MagicMock()
    sys.modules["unanimous_logger"] = mock_unanimous_logger

    config_dict = {"log_level": "INFO", "log_filename": "test_unanimous.log"}
    logger = setup_logging(config_dict)

    mock_unanimous_logger.setup_logger.assert_called_once_with(
        mock_unanimous_logger.UnanimousLoggerConfig(config_dict),
        log_name="wb",
        json_log_file="wb.json.log",
    )
    assert logger == mock_unanimous_logger.setup_logger.return_value

    # Clean up mock module
    del sys.modules["unanimous_logger"]


# Test that handlers are not duplicated on subsequent calls
def test_logging_handlers_not_duplicated(mock_path_mkdir, mock_os_path_join):
    with patch.dict(sys.modules, {"unanimous_logger": None}):
        config_dict = {"log_level": "INFO", "log_filename": "test_dedup.log"}
        logger = setup_logging(config_dict)
        initial_handler_count = len(logger.handlers)

        # Call setup_logging again with the same config
        logger2 = setup_logging(config_dict)

        assert logger is logger2  # Should return the same logger instance
        assert (
            len(logger.handlers) == initial_handler_count
        )  # Handlers should not increase
