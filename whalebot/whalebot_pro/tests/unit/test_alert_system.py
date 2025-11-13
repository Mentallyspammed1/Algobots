import logging
from unittest.mock import MagicMock

import pytest
from whalebot_pro.utils.alert_system import AlertSystem


@pytest.fixture
def mock_logger():
    return MagicMock(spec=logging.Logger)


def test_send_alert_info(mock_logger):
    alert_system = AlertSystem(mock_logger)
    message = "Test info message"
    alert_system.send_alert(message, "INFO")
    mock_logger.info.assert_called_once_with(f"\x1b[36mALERT: {message}\x1b[39m")
    mock_logger.warning.assert_not_called()
    mock_logger.error.assert_not_called()


def test_send_alert_warning(mock_logger):
    alert_system = AlertSystem(mock_logger)
    message = "Test warning message"
    alert_system.send_alert(message, "WARNING")
    mock_logger.warning.assert_called_once_with(f"\x1b[33mALERT: {message}\x1b[39m")
    mock_logger.info.assert_not_called()
    mock_logger.error.assert_not_called()


def test_send_alert_error(mock_logger):
    alert_system = AlertSystem(mock_logger)
    message = "Test error message"
    alert_system.send_alert(message, "ERROR")
    mock_logger.error.assert_called_once_with(f"\x1b[91mALERT: {message}\x1b[39m")
    mock_logger.info.assert_not_called()
    mock_logger.warning.assert_not_called()
