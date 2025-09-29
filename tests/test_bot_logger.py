# tests/test_bot_logger.py
import logging
import sys

import pytest

sys.path.insert(0, "/data/data/com.termux/files/home/Algobots")
from bot_logger import log_exception, log_metrics, log_trade, setup_logging


@pytest.fixture
def caplog_for_test(caplog):
    """Fixture to capture logs for testing."""
    caplog.set_level(logging.DEBUG)  # Capture all levels
    return caplog


def test_setup_logging(caplog_for_test):
    logger = setup_logging()
    assert isinstance(logger, logging.Logger)
    assert logger.name == "PyrmethusBot"
    assert len(logger.handlers) == 4  # File and Console
    logger.info("Test log message")
    assert "Test log message" in caplog_for_test.text


def test_log_trade(caplog_for_test):
    logger = setup_logging()
    trade_data = {"symbol": "BTCUSDT", "price": 20000, "qty": 0.001}
    log_trade(logger, "New trade", trade_data)
    assert '"symbol": "BTCUSDT"' in caplog_for_test.text
    assert "TRADE" in caplog_for_test.text


def test_log_metrics(caplog_for_test):
    logger = setup_logging()
    metrics_data = {"total_pnl": 100.5, "win_rate": 0.6}
    log_metrics(logger, "Daily metrics", metrics_data)
    assert '"total_pnl": 100.5' in caplog_for_test.text
    assert "METRICS" in caplog_for_test.text


def test_log_exception(caplog_for_test):
    logger = setup_logging()
    try:
        raise ValueError("Test exception")
    except ValueError as e:
        log_exception(logger, "An error occurred", e)
    assert "An error occurred" in caplog_for_test.text
    assert "ValueError: Test exception" in caplog_for_test.text
    assert "ERROR" in caplog_for_test.text
