import os
import sys
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch

import dateutil.tz
import pandas as pd

# Add the script's directory to the Python path to allow imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Now import the classes and functions from the script
from stupdated2_1 import (
    BotState,
    BybitClient,
    CandlestickPatternDetector,
    Category,
    Config,
    EhlersSuperTrendBot,
    InstrumentSpecs,
    NewsCalendarManager,
    OrderSizingCalculator,
    OrderType,
    PrecisionManager,
    Signal,
    TermuxSMSNotifier,
    TrailingStopManager,
    parse_to_utc,
    setup_logger,
)

# A basic logger for testing purposes
test_logger = setup_logger(Config())


class TestConfig(unittest.TestCase):

    @patch.dict(os.environ, {}, clear=True)
    def test_default_config_values(self):
        """Test that the Config class loads default values correctly."""
        config = Config()
        self.assertEqual(config.SYMBOL, "TRUMPUSDT")
        self.assertEqual(config.LEVERAGE, 25)
        self.assertFalse(config.TESTNET)
        self.assertEqual(config.LOG_LEVEL, "INFO")
        self.assertEqual(config.RISK_PER_TRADE_PCT, 1.0)

    @patch.dict(os.environ, {
        "TRADING_SYMBOL": "BTCUSDT",
        "BYBIT_LEVERAGE": "50",
        "BYBIT_TESTNET": "true",
        "BYBIT_LOG_LEVEL": "DEBUG",
        "RISK_PER_TRADE_PCT": "2.5"
    })
    def test_env_variable_override(self):
        """Test that environment variables correctly override default config values."""
        config = Config()
        self.assertEqual(config.SYMBOL, "BTCUSDT")
        self.assertEqual(config.LEVERAGE, 50)
        self.assertTrue(config.TESTNET)
        self.assertEqual(config.LOG_LEVEL, "DEBUG")
        self.assertEqual(config.RISK_PER_TRADE_PCT, 2.5)

    @patch.dict(os.environ, {"BYBIT_API_KEY": "test_key", "BYBIT_API_SECRET": "test_secret"})
    def test_valid_category_and_order_type(self):
        """Test that valid category and order type enums are created."""
        config = Config()
        self.assertEqual(config.CATEGORY_ENUM, Category.LINEAR)
        self.assertEqual(config.ORDER_TYPE_ENUM, OrderType.MARKET)

    @patch.dict(os.environ, {"BYBIT_CATEGORY": "INVALID_CATEGORY"})
    def test_invalid_category_exit(self):
        """Test that the script exits with an invalid category."""
        with self.assertRaises(SystemExit):
            Config()

    @patch.dict(os.environ, {"BYBIT_ORDER_TYPE": "INVALID_ORDER_TYPE"})
    def test_invalid_order_type_exit(self):
        """Test that the script exits with an invalid order type."""
        with self.assertRaises(SystemExit):
            Config()

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_api_keys_exit(self):
        """Test that the script exits if API keys are missing."""
        with self.assertRaises(SystemExit):
            Config()


class TestTemporalUtils(unittest.TestCase):
    def test_parse_to_utc(self):
        """Test the parse_to_utc utility function."""
        self.assertEqual(parse_to_utc("2025-08-25 10:00:00 EDT"), datetime(2025, 8, 25, 14, 0, 0))
        self.assertEqual(parse_to_utc("2025-08-25 10:00:00 PST"), datetime(2025, 8, 25, 17, 0, 0)) # PDT is active in August
        self.assertEqual(parse_to_utc("2025-01-01 10:00:00 PST"), datetime(2025, 1, 1, 18, 0, 0))
        self.assertEqual(parse_to_utc("2025-08-25 10:00:00 GMT"), datetime(2025, 8, 25, 10, 0, 0))
        self.assertIsNone(parse_to_utc("Invalid Date String"))


class TestPrecisionManager(unittest.TestCase):

    def setUp(self):
        """Set up a mock PrecisionManager for testing."""
        self.mock_session = MagicMock()
        self.precision_manager = PrecisionManager(self.mock_session, test_logger)
        # Manually add instrument specs to avoid network calls in tests
        self.precision_manager.instruments = {
            'BTCUSDT': InstrumentSpecs(
                symbol='BTCUSDT', category='linear', base_currency='BTC', quote_currency='USDT', status='Trading',
                min_price=Decimal('0.1'), max_price=Decimal('1000000'), tick_size=Decimal('0.1'),
                min_order_qty=Decimal('0.001'), max_order_qty=Decimal('100'), qty_step=Decimal('0.001'),
                min_leverage=Decimal('1'), max_leverage=Decimal('100'), leverage_step=Decimal('0.01'),
                max_position_value=Decimal('2000000'), min_position_value=Decimal('5')
            ),
            'ETHUSDT': InstrumentSpecs(
                symbol='ETHUSDT', category='linear', base_currency='ETH', quote_currency='USDT', status='Trading',
                min_price=Decimal('0.01'), max_price=Decimal('100000'), tick_size=Decimal('0.01'),
                min_order_qty=Decimal('0.01'), max_order_qty=Decimal('1000'), qty_step=Decimal('0.01'),
                min_leverage=Decimal('1'), max_leverage=Decimal('100'), leverage_step=Decimal('0.01'),
                max_position_value=Decimal('1000000'), min_position_value=Decimal('5')
            )
        }

    def test_get_specs(self):
        """Test retrieving instrument specifications."""
        specs = self.precision_manager.get_specs('BTCUSDT')
        self.assertIsNotNone(specs)
        self.assertEqual(specs.symbol, 'BTCUSDT')
        self.assertIsNone(self.precision_manager.get_specs('UNKNOWN'))

    def test_round_price(self):
        """Test price rounding based on tick size."""
        self.assertEqual(self.precision_manager.round_price('BTCUSDT', 12345.678), Decimal('12345.6'))
        self.assertEqual(self.precision_manager.round_price('ETHUSDT', 3456.789), Decimal('3456.78'))
        # Test clamping
        self.assertEqual(self.precision_manager.round_price('BTCUSDT', 0.05), Decimal('0.1')) # Below min
        self.assertEqual(self.precision_manager.round_price('BTCUSDT', 2000000), Decimal('1000000')) # Above max

    def test_round_quantity(self):
        """Test quantity rounding based on step size."""
        self.assertEqual(self.precision_manager.round_quantity('BTCUSDT', 1.23456), Decimal('1.234'))
        self.assertEqual(self.precision_manager.round_quantity('ETHUSDT', 2.3456), Decimal('2.34'))
        # Test clamping
        self.assertEqual(self.precision_manager.round_quantity('BTCUSDT', 0.0005), Decimal('0.001')) # Below min
        self.assertEqual(self.precision_manager.round_quantity('BTCUSDT', 101), Decimal('100')) # Above max

    def test_get_decimal_places(self):
        """Test getting the correct number of decimal places."""
        price_dp, qty_dp = self.precision_manager.get_decimal_places('BTCUSDT')
        self.assertEqual(price_dp, 1)
        self.assertEqual(qty_dp, 3)
        price_dp, qty_dp = self.precision_manager.get_decimal_places('ETHUSDT')
        self.assertEqual(price_dp, 2)
        self.assertEqual(qty_dp, 2)


class TestOrderSizingCalculator(unittest.TestCase):

    def setUp(self):
        """Set up a mock PrecisionManager and OrderSizingCalculator."""
        self.mock_precision_manager = MagicMock()
        self.mock_precision_manager.get_specs.return_value = InstrumentSpecs(
            symbol='BTCUSDT', category='linear', base_currency='BTC', quote_currency='USDT', status='Trading',
            min_price=Decimal('0.1'), max_price=Decimal('1000000'), tick_size=Decimal('0.1'),
            min_order_qty=Decimal('0.001'), max_order_qty=Decimal('100'), qty_step=Decimal('0.001'),
            min_leverage=Decimal('1'), max_leverage=Decimal('100'), leverage_step=Decimal('0.01'),
            max_position_value=Decimal('2000000'), min_position_value=Decimal('5')
        )
        self.mock_precision_manager.round_quantity.side_effect = lambda symbol, qty: Decimal(str(qty)).quantize(Decimal('0.001'))
        self.config = Config() # Use default config
        self.order_sizer = OrderSizingCalculator(self.mock_precision_manager, test_logger, self.config)

    def test_calculate_position_size_usd(self):
        """Test basic position size calculation."""
        size = self.order_sizer.calculate_position_size_usd(
            symbol='BTCUSDT',
            account_balance_usdt=Decimal('1000'),
            risk_percent=Decimal('0.01'), # 1% risk
            entry_price=Decimal('50000'),
            stop_loss_price=Decimal('49500'), # $500 stop distance
            leverage=Decimal('10')
        )
        # Expected logic:
        # Risk amount = 1000 * 0.01 = $10
        # Stop distance % = 500 / 50000 = 1% = 0.01
        # Position value = 10 / 0.01 = $1000
        # Quantity = 1000 / 50000 = 0.02
        self.assertEqual(size, Decimal('0.020'))

    def test_position_size_clamping(self):
        """Test that position size is clamped by MAX_POSITION_SIZE_USD."""
        self.config.MAX_POSITION_SIZE_USD = 500.0 # Set a lower max
        size = self.order_sizer.calculate_position_size_usd(
            symbol='BTCUSDT',
            account_balance_usdt=Decimal('1000'),
            risk_percent=Decimal('0.01'),
            entry_price=Decimal('50000'),
            stop_loss_price=Decimal('49500'),
            leverage=Decimal('10')
        )
        # Expected logic:
        # Uncapped position value = $1000
        # Capped by config = $500
        # Quantity = 500 / 50000 = 0.01
        self.assertEqual(size, Decimal('0.010'))

    def test_volatility_adjusted_sizing(self):
        """Test volatility-adjusted position sizing."""
        self.config.VOLATILITY_ADJUSTED_SIZING_ENABLED = True
        self.config.MAX_RISK_PER_TRADE_BALANCE_PCT = 0.015 # 1.5%
        size = self.order_sizer.calculate_position_size_usd(
            symbol='BTCUSDT',
            account_balance_usdt=Decimal('1000'),
            risk_percent=Decimal('0.01'), # This is ignored
            entry_price=Decimal('50000'),
            stop_loss_price=Decimal('49500'), # $500 stop distance
            leverage=Decimal('10'),
            current_atr=Decimal('600') # ATR is used for stop distance
        )
        # Expected logic:
        # Risk amount = 1000 * 0.015 = $15
        # Stop distance % = 500 / 50000 = 1% = 0.01
        # Position value = 15 / 0.01 = $1500
        # Quantity = 1500 / 50000 = 0.03
        self.assertEqual(size, Decimal('0.030'))


class TestNewsCalendarManager(unittest.TestCase):
    def setUp(self):
        self.config = Config()
        self.config.NEWS_PAUSE_ENABLED = True
        self.config.NEWS_API_ENDPOINT = None # Force mock
        self.config.IMPACT_LEVELS_TO_PAUSE = ["High"]
        self.config.PAUSE_PRE_EVENT_MINUTES = 15
        self.config.PAUSE_POST_EVENT_MINUTES = 30
        self.news_manager = NewsCalendarManager(self.config, test_logger)

    def test_is_trading_paused(self):
        """Test the logic for pausing trading around news events."""
        # Mock a high-impact event happening in 10 minutes
        now = datetime.now(dateutil.tz.UTC)
        mock_event_time = now + timedelta(minutes=10)
        self.news_manager.news_events = [
            {'event': 'Test CPI', 'time_utc': mock_event_time, 'impact': 'High'}
        ]
        self.news_manager.last_fetch_time = now

        # Should be paused because we are within the 15-minute pre-event window
        paused, reason = self.news_manager.is_trading_paused()
        self.assertTrue(paused)
        self.assertIn("Test CPI", reason)

        # Mock an event that just passed 20 minutes ago
        mock_event_time = now - timedelta(minutes=20)
        self.news_manager.news_events = [
            {'event': 'Test FOMC', 'time_utc': mock_event_time, 'impact': 'High'}
        ]
        # Should be paused because we are within the 30-minute post-event window
        paused, reason = self.news_manager.is_trading_paused()
        self.assertTrue(paused)
        self.assertIn("Test FOMC", reason)

        # Mock an event happening in 1 hour
        mock_event_time = now + timedelta(hours=1)
        self.news_manager.news_events = [
            {'event': 'Test GDP', 'time_utc': mock_event_time, 'impact': 'High'}
        ]
        # Should NOT be paused
        paused, reason = self.news_manager.is_trading_paused()
        self.assertFalse(paused)


class TestCandlestickPatternDetector(unittest.TestCase):
    def setUp(self):
        self.detector = CandlestickPatternDetector(test_logger)

    def test_detect_bullish_engulfing(self):
        """Test detection of a bullish engulfing pattern."""
        df = pd.DataFrame({
            'open':  [105, 100],
            'high':  [106, 108],
            'low':   [102, 99],
            'close': [103, 107] # Bearish candle, then larger bullish candle
        })
        self.assertEqual(self.detector.detect_pattern(df, ["ENGULFING"]), "ENGULFING")

    def test_detect_hammer(self):
        """Test detection of a hammer pattern."""
        df = pd.DataFrame({
            'open':  [102],
            'high':  [103],
            'low':   [95],
            'close': [102.5] # Small body, long lower wick
        })
        self.assertEqual(self.detector.detect_pattern(df, ["HAMMER"]), "HAMMER")

    def test_no_pattern(self):
        """Test that no pattern is detected when none exists."""
        df = pd.DataFrame({
            'open':  [100, 102],
            'high':  [103, 104],
            'low':   [99, 101],
            'close': [102, 103]
        })
        self.assertIsNone(self.detector.detect_pattern(df, ["ENGULFING", "HAMMER"]))


class TestEhlersSuperTrendBotCleanup(unittest.TestCase):

    @patch('stupdated2_1.EhlersSuperTrendBot.close_position')
    @patch('stupdated2_1.subprocess.run')
    @patch('stupdated2_1.TermuxSMSNotifier.send_sms')
    def setUp(self, mock_send_sms, mock_subprocess_run, mock_close_position):
        """Set up a mock EhlersSuperTrendBot for testing the cleanup method."""
        self.mock_close_position = mock_close_position
        self.mock_subprocess_run = mock_subprocess_run
        self.mock_send_sms = mock_send_sms

        # Mock the config object
        self.config = Config()
        self.config.AUTO_CLOSE_ON_SHUTDOWN = False # Default to off

        # Mock the bot instance and its dependencies
        with patch('stupdated2_1.BybitClient'), \
             patch('stupdated2_1.PrecisionManager'), \
             patch('stupdated2_1.OrderSizingCalculator'), \
             patch('stupdated2_1.TrailingStopManager'), \
             patch('stupdated2_1.NewsCalendarManager'), \
             patch('stupdated2_1.CandlestickPatternDetector'), \
             patch('stupdated2_1.setup_logger') as mock_setup_logger:

            # Ensure the logger is a mock that we can inspect
            self.mock_logger = MagicMock()
            mock_setup_logger.return_value = self.mock_logger

            # We need to initialize the bot to have all attributes
            self.bot = EhlersSuperTrendBot(self.config)

            # Now, replace the logger and notifier on the actual instance with mocks
            self.bot.logger = self.mock_logger
            self.bot.sms_notifier = MagicMock()
            self.bot.sms_notifier.is_enabled = True
            self.bot.sms_notifier.send_sms = self.mock_send_sms


    def test_cleanup_with_autoclose_enabled_and_position_active(self):
        """Test cleanup closes position when AUTO_CLOSE_ON_SHUTDOWN is True and a position is active."""
        self.bot.config.AUTO_CLOSE_ON_SHUTDOWN = True
        self.bot.position_active = True
        self.bot.current_position_side = 'Buy'

        self.bot._cleanup()

        # Verify that close_position was called
        self.bot.close_position.assert_called_once_with(
            side='Buy',
            reason="Graceful shutdown with auto-close enabled."
        )

        # Verify final log messages and notifications
        self.mock_logger.info.assert_any_call("Closing active position due to auto-close on shutdown setting...")
        self.mock_subprocess_run.assert_called_with(["termux-toast", f"Ehlers SuperTrend Bot for {self.bot.config.SYMBOL} has ceased operations."])
        self.bot.sms_notifier.send_sms.assert_called_with(f"Ehlers SuperTrend Bot for {self.bot.config.SYMBOL} has ceased operations.")


    def test_cleanup_with_autoclose_disabled(self):
        """Test cleanup does NOT close position when AUTO_CLOSE_ON_SHUTDOWN is False."""
        self.bot.config.AUTO_CLOSE_ON_SHUTDOWN = False
        self.bot.position_active = True

        self.bot._cleanup()

        # Verify that close_position was NOT called
        self.bot.close_position.assert_not_called()

        # Verify final log messages and notifications
        self.mock_logger.info.assert_any_call("Auto-close on shutdown is disabled or no active position. Not closing positions.")
        self.mock_subprocess_run.assert_called_with(["termux-toast", f"Ehlers SuperTrend Bot for {self.bot.config.SYMBOL} has ceased operations."])
        self.bot.sms_notifier.send_sms.assert_called_with(f"Ehlers SuperTrend Bot for {self.bot.config.SYMBOL} has ceased operations.")

    def test_cleanup_with_no_active_position(self):
        """Test cleanup does NOT close position when there is no active position."""
        self.bot.config.AUTO_CLOSE_ON_SHUTDOWN = True
        self.bot.position_active = False

        self.bot._cleanup()

        # Verify that close_position was NOT called
        self.bot.close_position.assert_not_called()

        # Verify final log messages and notifications
        self.mock_logger.info.assert_any_call("Auto-close on shutdown is disabled or no active position. Not closing positions.")
        self.mock_subprocess_run.assert_called_with(["termux-toast", f"Ehlers SuperTrend Bot for {self.bot.config.SYMBOL} has ceased operations."])
        self.bot.sms_notifier.send_sms.assert_called_with(f"Ehlers SuperTrend Bot for {self.bot.config.SYMBOL} has ceased operations.")

if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)

