import json
import logging
from unittest.mock import mock_open, patch

import pytest
from whalebot_pro.config import DEFAULT_CONFIG_FILE, Config


# Mock logger for testing Config class
@pytest.fixture
def mock_logger():
    return logging.getLogger(__name__)


# Test default config creation
def test_config_creation_default(tmp_path, mock_logger):
    test_config_path = tmp_path / DEFAULT_CONFIG_FILE
    with patch("whalebot_pro.config.Path") as MockPath:
        MockPath.return_value.exists.return_value = False
        MockPath.return_value.open = mock_open()

        config = Config(mock_logger)

        MockPath.return_value.open.assert_called_once_with("w", encoding="utf-8")
        handle = MockPath.return_value.open()
        handle.write.assert_called_once()  # Check if json.dump was called

        assert config.symbol == "BTCUSDT"
        assert config.interval == "15m"
        assert config.trade_management["enabled"] is True


# Test loading existing config
def test_config_loading_existing(tmp_path, mock_logger):
    test_config_path = tmp_path / DEFAULT_CONFIG_FILE

    # Create a dummy config file
    dummy_config_content = {
        "symbol": "ETHUSDT",
        "interval": "5m",
        "trade_management": {"enabled": False},
    }
    test_config_path.write_text(json.dumps(dummy_config_content))

    with patch("whalebot_pro.config.Path") as MockPath:
        MockPath.return_value = test_config_path
        MockPath.return_value.exists.return_value = True
        MockPath.return_value.open = mock_open(
            read_data=json.dumps(dummy_config_content),
        )

        config = Config(mock_logger)

        assert config.symbol == "ETHUSDT"
        assert config.interval == "5m"
        assert config.trade_management["enabled"] is False


# Test _ensure_config_keys for new defaults
def test_ensure_config_keys_new_defaults(tmp_path, mock_logger):
    test_config_path = tmp_path / DEFAULT_CONFIG_FILE

    # Simulate an old config without new keys
    old_config_content = {
        "symbol": "LTCUSDT",
        "interval": "30m",
        "trade_management": {"enabled": True},
    }
    test_config_path.write_text(json.dumps(old_config_content))

    with patch("whalebot_pro.config.Path") as MockPath:
        MockPath.return_value = test_config_path
        MockPath.return_value.exists.return_value = True
        MockPath.return_value.open = mock_open(read_data=json.dumps(old_config_content))

        config = Config(mock_logger)

        # Check if a new default key is added
        assert hasattr(config, "cooldown_sec")
        assert config.cooldown_sec == 60  # Default value
        assert (
            config.trade_management["slippage_percent"] == 0.001
        )  # New nested default


# Test __getattr__ for config access
def test_config_getattr(mock_logger):
    config_data = {"test_key": "test_value", "nested": {"nested_key": 123}}
    with patch("whalebot_pro.config.Path") as MockPath:
        MockPath.return_value.exists.return_value = False  # Don't create file
        MockPath.return_value.open = mock_open()

        config = Config(mock_logger)
        config._config_data = config_data  # Manually set internal data

        assert config.test_key == "test_value"
        assert config.nested["nested_key"] == 123

        with pytest.raises(AttributeError):
            config.non_existent_key


# Test set_active_strategy_profile
def test_set_active_strategy_profile(tmp_path, mock_logger):
    test_config_path = tmp_path / DEFAULT_CONFIG_FILE

    # Create a dummy config with multiple profiles
    dummy_config_content = {
        "symbol": "BTCUSDT",
        "interval": "15m",
        "current_strategy_profile": "default_scalping",
        "strategy_profiles": {
            "default_scalping": {
                "indicators_enabled": {"ema_alignment": True},
                "weights": {"ema_alignment": 0.5},
            },
            "trend_following": {
                "indicators_enabled": {"macd": True},
                "weights": {"macd_alignment": 0.8},
            },
        },
    }
    test_config_path.write_text(json.dumps(dummy_config_content))

    with patch("whalebot_pro.config.Path") as MockPath:
        MockPath.return_value = test_config_path
        MockPath.return_value.exists.return_value = True
        MockPath.return_value.open = mock_open(
            read_data=json.dumps(dummy_config_content),
        )

        config = Config(mock_logger)

        assert config.current_strategy_profile == "default_scalping"
        assert config.indicators["ema_alignment"] is True
        assert config.active_weights["ema_alignment"] == 0.5

        config.set_active_strategy_profile("trend_following")

        assert config.current_strategy_profile == "trend_following"
        assert config.indicators["macd"] is True
        assert config.active_weights["macd_alignment"] == 0.8
        assert "ema_alignment" not in config.indicators  # Should be overwritten

        # Test setting non-existent profile
        config.set_active_strategy_profile("non_existent")
        assert config.current_strategy_profile == "trend_following"  # Should not change
