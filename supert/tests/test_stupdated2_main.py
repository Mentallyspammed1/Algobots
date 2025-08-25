import unittest
from unittest.mock import patch, MagicMock, call
import sys
import os
from decimal import Decimal

# Add the script's directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the bot and its components
from stupdated2_1 import EhlersSuperTrendBot, Config

class TestEhlersSuperTrendBotMain(unittest.TestCase):

    @patch('stupdated2_1.setup_logger')
    @patch('stupdated2_1.BybitClient')
    @patch('stupdated2_1.PrecisionManager')
    @patch('stupdated2_1.OrderSizingCalculator')
    @patch('stupdated2_1.TrailingStopManager')
    @patch('stupdated2_1.NewsCalendarManager')
    @patch('stupdated2_1.CandlestickPatternDetector')
    @patch('stupdated2_1.TermuxSMSNotifier')
    @patch('stupdated2_1.BotUI')
    def setUp(self, MockBotUI, MockSMSNotifier, MockCandlestickDetector, MockNewsManager, MockTSManager, MockOrderSizer, MockPrecisionManager, MockBybitClient, MockSetupLogger):
        """Set up a mock environment for testing the bot's main logic."""
        self.mock_logger = MockSetupLogger.return_value
        self.mock_bybit_client = MockBybitClient.return_value
        self.mock_precision_manager = MockPrecisionManager.return_value
        self.mock_precision_manager.get_decimal_places.return_value = (2, 3) # (price, qty)

        # Mock methods called during bot initialization
        self.mock_bybit_client.get_server_time.return_value = {'retCode': 0, 'result': {'timeNano': '1672531200000000000'}}
        self.mock_bybit_client.get_instruments_info.return_value = {'retCode': 0, 'result': {'list': [{'symbol': 'TRUMPUSDT'}]}}
        self.mock_bybit_client.get_wallet_balance.return_value = {'retCode': 0, 'result': {'list': [{'coin': [{'coin': 'USDT', 'equity': '1000'}]}]}}
        self.mock_bybit_client.set_leverage.return_value = {'retCode': 0}
        self.mock_bybit_client.switch_margin_mode.return_value = {'retCode': 0}


        self.config = Config()
        # Patch the bot's internal validation and setup methods to avoid complex mocking
        with patch.object(EhlersSuperTrendBot, '_validate_api_credentials', return_value=None), \
             patch.object(EhlersSuperTrendBot, '_validate_symbol_timeframe', return_value=None), \
             patch.object(EhlersSuperTrendBot, '_capture_initial_equity', return_value=None), \
             patch.object(EhlersSuperTrendBot, '_configure_trading_parameters', return_value=None):
            self.bot = EhlersSuperTrendBot(self.config)
            # Replace manager instances with mocks after init
            self.bot.logger = self.mock_logger
            self.bot.bybit_client = self.mock_bybit_client
            self.bot.precision_manager = self.mock_precision_manager
            self.bot.sms_notifier = MockSMSNotifier.return_value


    def test_bot_initialization(self):
        """Test that the bot initializes correctly."""
        self.assertIsNotNone(self.bot)
        self.assertEqual(self.bot.config.SYMBOL, "TRUMPUSDT")
        self.mock_logger.info.assert_any_call("Initializing Ehlers SuperTrend Trading Bot...")
        # Check if setup methods were called
        self.bot._validate_api_credentials.assert_called_once()
        self.bot._validate_symbol_timeframe.assert_called_once()
        self.bot._capture_initial_equity.assert_called_once()
        self.bot._configure_trading_parameters.assert_called_once()

    @patch.object(EhlersSuperTrendBot, '_start_websockets')
    @patch.object(EhlersSuperTrendBot, '_main_loop')
    @patch.object(EhlersSuperTrendBot, '_cleanup')
    def test_run_method_flow(self, mock_cleanup, mock_main_loop, mock_start_websockets):
        """Test the main run method's execution flow."""
        # Mock the stop_event to be set after one loop iteration to prevent infinite loop
        def stop_loop():
            self.bot.stop_event.set()
        mock_main_loop.side_effect = stop_loop

        self.bot.run()

        mock_start_websockets.assert_called_once()
        mock_main_loop.assert_called_once()
        mock_cleanup.assert_called_once()
        self.mock_logger.info.assert_any_call("Starting Ehlers SuperTrend Bot main loop...")

    @patch('stupdated2_1.subprocess.run')
    def test_cleanup_with_autoclose_enabled(self, mock_subprocess):
        """Test the cleanup method with auto-close enabled."""
        self.bot.config.AUTO_CLOSE_ON_SHUTDOWN = True
        self.bot.position_active = True
        with patch.object(self.bot, 'close_open_positions') as mock_close_positions:
            self.bot._cleanup()
            mock_close_positions.assert_called_once()
            self.bot.sms_notifier.send_sms.assert_called_once()
            mock_subprocess.assert_called_with(["termux-toast", f"Ehlers SuperTrend Bot for {self.config.SYMBOL} has ceased operations."])

    @patch('stupdated2_1.subprocess.run')
    def test_cleanup_with_autoclose_disabled(self, mock_subprocess):
        """Test the cleanup method with auto-close disabled."""
        self.bot.config.AUTO_CLOSE_ON_SHUTDOWN = False
        self.bot.position_active = True
        with patch.object(self.bot, 'close_open_positions') as mock_close_positions:
            self.bot._cleanup()
            mock_close_positions.assert_not_called() # Should not be called
            self.bot.sms_notifier.send_sms.assert_called_once()
            mock_subprocess.assert_called_with(["termux-toast", f"Ehlers SuperTrend Bot for {self.config.SYMBOL} has ceased operations."])

if __name__ == '__main__':
    # This allows the test to be run from the command line
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
