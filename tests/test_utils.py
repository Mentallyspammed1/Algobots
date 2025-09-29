import logging
import os  # Import os module
import sys
import unittest
from decimal import Decimal, getcontext
from unittest.mock import MagicMock, patch

# Ensure the root directory is in the Python path for imports
sys.path.insert(0, "/data/data/com.termux/files/home/Algobots")

# Mock setup_logging to prevent actual log file creation during tests
with patch("bot_logger.setup_logging"):
    from utils import (
        FallbackZoneInfo,  # Import TIMEZONE
        OrderBook,
        calculate_order_quantity,
        get_min_tick_size,
        get_price_precision,
        get_timezone,
        round_decimal,
        set_timezone,
    )  # Import color constants
    from utils import (
        _module_logger as utils_logger,  # Access the module-level logger
    )

# Set Decimal precision for tests
getcontext().prec = 38


class TestOrderBook(unittest.TestCase):
    def setUp(self):
        self.mock_logger = MagicMock(spec=logging.Logger)
        self.order_book = OrderBook(self.mock_logger)

    def test_handle_snapshot(self):
        snapshot_data = {
            "b": [["100.0", "10"], ["99.9", "5"]],
            "a": [["100.1", "8"], ["100.2", "7"]],
            "seq": 12345,
        }
        self.order_book.handle_snapshot(snapshot_data)
        self.assertEqual(
            self.order_book.bids,
            {Decimal("100.0"): Decimal("10"), Decimal("99.9"): Decimal("5")},
        )
        self.assertEqual(
            self.order_book.asks,
            {Decimal("100.1"): Decimal("8"), Decimal("100.2"): Decimal("7")},
        )
        self.assertEqual(self.order_book.last_seq, 12345)

    def test_apply_delta_update_existing(self):
        self.order_book.bids = {Decimal("100.0"): Decimal("10")}
        self.order_book.asks = {Decimal("100.1"): Decimal("8")}
        self.order_book.last_seq = 100

        delta_data = {
            "b": [["100.0", "12"]],  # Update existing bid
            "a": [],
            "seq": 101,
        }
        self.order_book.apply_delta(delta_data)
        self.assertEqual(self.order_book.bids, {Decimal("100.0"): Decimal("12")})
        self.assertEqual(self.order_book.asks, {Decimal("100.1"): Decimal("8")})
        self.assertEqual(self.order_book.last_seq, 101)

    def test_apply_delta_add_new(self):
        self.order_book.bids = {Decimal("100.0"): Decimal("10")}
        self.order_book.asks = {Decimal("100.1"): Decimal("8")}
        self.order_book.last_seq = 100

        delta_data = {
            "b": [["99.8", "7"]],  # Add new bid
            "a": [],
            "seq": 101,
        }
        self.order_book.apply_delta(delta_data)
        self.assertEqual(
            self.order_book.bids,
            {Decimal("100.0"): Decimal("10"), Decimal("99.8"): Decimal("7")},
        )
        self.assertEqual(self.order_book.asks, {Decimal("100.1"): Decimal("8")})
        self.assertEqual(self.order_book.last_seq, 101)

    def test_apply_delta_remove_entry(self):
        self.order_book.bids = {Decimal("100.0"): Decimal("10")}
        self.order_book.asks = {Decimal("100.1"): Decimal("8")}
        self.order_book.last_seq = 100

        delta_data = {
            "b": [["100.0", "0"]],  # Remove bid
            "a": [],
            "seq": 101,
        }
        self.order_book.apply_delta(delta_data)
        self.assertEqual(self.order_book.bids, {})
        self.assertEqual(self.order_book.asks, {Decimal("100.1"): Decimal("8")})
        self.assertEqual(self.order_book.last_seq, 101)

    def test_apply_delta_stale_seq(self):
        self.order_book.last_seq = 100
        delta_data = {"b": [], "a": [], "seq": 99}
        self.order_book.apply_delta(delta_data)
        self.assertEqual(self.order_book.last_seq, 100)  # Should not update
        self.mock_logger.debug.assert_called_with(
            "Stale or out-of-order order book update (current seq: 99, last seq: 100). Skipping."
        )

    def test_get_imbalance(self):
        self.order_book.bids = {
            Decimal("100"): Decimal("10"),
            Decimal("99"): Decimal("5"),
        }
        self.order_book.asks = {
            Decimal("101"): Decimal("8"),
            Decimal("102"): Decimal("7"),
        }
        # bid_volume = 100*10 + 99*5 = 1000 + 495 = 1495
        # ask_volume = 101*8 + 102*7 = 808 + 714 = 1522
        # total_volume = 1495 + 1522 = 3017
        # imbalance = (1495 - 1522) / 3017 = -27 / 3017 = -0.008949287371561153
        imbalance = self.order_book.get_imbalance()
        self.assertAlmostEqual(float(imbalance), -0.008949287371561153, places=5)

    def test_get_imbalance_empty(self):
        imbalance = self.order_book.get_imbalance()
        self.assertEqual(imbalance, Decimal("0"))


class TestCalculateOrderQuantity(unittest.TestCase):
    def setUp(self):
        self.mock_logger = MagicMock(spec=logging.Logger)
        self.usdt_amount = Decimal("100")
        self.current_price = Decimal("50000")
        self.min_qty = Decimal("0.001")
        self.qty_step = Decimal("0.0001")
        self.min_order_value = Decimal("10")

    def test_basic_calculation(self):
        qty = calculate_order_quantity(
            self.usdt_amount,
            self.current_price,
            self.min_qty,
            self.qty_step,
            self.min_order_value,
            self.mock_logger,
        )
        # 100 USDT / 50000 = 0.002 BTC
        # 0.002 // 0.0001 = 20 steps -> 20 * 0.0001 = 0.002
        self.assertEqual(qty, Decimal("0.002"))

    def test_below_min_qty_adjust_up(self):
        usdt_amount = Decimal("0.01")  # Results in 0.0000002 BTC
        qty = calculate_order_quantity(
            usdt_amount,
            self.current_price,
            self.min_qty,
            self.qty_step,
            self.min_order_value,
            self.mock_logger,
        )
        self.assertEqual(qty, self.min_qty)  # Should adjust to min_qty
        self.mock_logger.warning.assert_called_with(
            f"{utils_logger.NEON_YELLOW}Initial quantity {Decimal('0.0000002'):.8f} was below min_qty {self.min_qty}. Adjusting to min_qty.{utils_logger.RESET_ALL_STYLE}"
        )

    def test_below_min_order_value_adjust_up(self):
        usdt_amount = Decimal(
            "5"
        )  # Results in 0.0001 BTC, value 5, below min_order_value 10
        qty = calculate_order_quantity(
            usdt_amount,
            self.current_price,
            self.min_qty,
            self.qty_step,
            self.min_order_value,
            self.mock_logger,
        )
        # Required qty for min_order_value = 10 / 50000 = 0.0002
        # Adjusted to step: (0.0002 // 0.0001) * 0.0001 = 0.0002
        self.assertEqual(qty, Decimal("0.0002"))
        self.mock_logger.warning.assert_called_with(
            f"{utils_logger.NEON_YELLOW}Order value {Decimal('5.0000'):.4f} is below min_order_value {self.min_order_value}. Recalculating quantity.{utils_logger.RESET_ALL_STYLE}"
        )
        self.mock_logger.info.assert_called_with(
            f"{utils_logger.NEON_BLUE}Quantity adjusted to {Decimal('0.0002'):.8f} to meet minimum order value.{utils_logger.RESET_ALL_STYLE}"
        )

    def test_zero_usdt_amount(self):
        qty = calculate_order_quantity(
            Decimal("0"),
            self.current_price,
            self.min_qty,
            self.qty_step,
            self.min_order_value,
            self.mock_logger,
        )
        self.assertEqual(qty, Decimal("0"))
        self.mock_logger.error.assert_called_with(
            f"{utils_logger.NEON_RED}USDT amount and current price must be positive for order calculation.{utils_logger.RESET_ALL_STYLE}"
        )

    def test_zero_current_price(self):
        qty = calculate_order_quantity(
            self.usdt_amount,
            Decimal("0"),
            self.min_qty,
            self.qty_step,
            self.min_order_value,
            self.mock_logger,
        )
        self.assertEqual(qty, Decimal("0"))
        self.mock_logger.error.assert_called_with(
            f"{utils_logger.NEON_RED}USDT amount and current price must be positive for order calculation.{utils_logger.RESET_ALL_STYLE}"
        )

    def test_final_qty_zero_after_adjustments(self):
        # Simulate a scenario where min_order_value is extremely high, leading to 0 qty
        qty = calculate_order_quantity(
            Decimal("1"),
            Decimal("1"),
            Decimal("1"),
            Decimal("1"),
            Decimal("100000"),
            self.mock_logger,
        )
        self.assertEqual(qty, Decimal("0"))
        self.mock_logger.error.assert_called_with(
            f"{utils_logger.NEON_RED}Final calculated quantity is zero or negative. Aborting order calculation.{utils_logger.RESET_ALL_STYLE}"
        )


class TestRoundDecimal(unittest.TestCase):
    def test_basic_rounding(self):
        self.assertEqual(round_decimal(10.12345, 2), Decimal("10.12"))
        self.assertEqual(round_decimal(10.125, 2), Decimal("10.13"))  # ROUND_HALF_UP
        self.assertEqual(round_decimal(10.123, 0), Decimal("10"))

    def test_zero_precision(self):
        self.assertEqual(round_decimal(123.456, 0), Decimal("123"))
        self.assertEqual(round_decimal(123.5, 0), Decimal("124"))

    def test_negative_value(self):
        self.assertEqual(round_decimal(-10.125, 2), Decimal("-10.13"))
        self.assertEqual(round_decimal(-10.123, 2), Decimal("-10.12"))

    def test_type_errors(self):
        with self.assertRaises(TypeError):
            round_decimal("10.123", 2)

    def test_value_errors(self):
        with self.assertRaises(ValueError):
            round_decimal(10.123, -1)
        with self.assertRaises(ValueError):
            round_decimal(10.123, 2.5)


class TestPrecisionFunctions(unittest.TestCase):
    def setUp(self):
        self.mock_logger = MagicMock(spec=logging.Logger)

    def test_get_price_precision_int_precision(self):
        market_info = {"precision": {"price": 4}, "symbol": "BTCUSDT"}
        self.assertEqual(get_price_precision(market_info, self.mock_logger), 4)

    def test_get_price_precision_float_tick_size(self):
        market_info = {"precision": {"price": 0.0001}, "symbol": "BTCUSDT"}
        self.assertEqual(get_price_precision(market_info, self.mock_logger), 4)

    def test_get_price_precision_str_tick_size(self):
        market_info = {"precision": {"price": "0.00001"}, "symbol": "ETHUSDT"}
        self.assertEqual(get_price_precision(market_info, self.mock_logger), 5)

    def test_get_price_precision_from_limits_min(self):
        market_info = {"limits": {"price": {"min": "0.001"}}, "symbol": "XRPUSDT"}
        self.assertEqual(get_price_precision(market_info, self.mock_logger), 3)

    def test_get_price_precision_default_fallback(self):
        market_info = {"symbol": "UNKNOWN"}
        self.assertEqual(get_price_precision(market_info, self.mock_logger), 4)
        self.mock_logger.warning.assert_called_with(
            "Could not determine price precision for UNKNOWN from market_info. Using default: 4."
        )

    def test_get_min_tick_size_from_precision_float(self):
        market_info = {"precision": {"price": 0.0001}, "symbol": "BTCUSDT"}
        self.assertEqual(
            get_min_tick_size(market_info, self.mock_logger), Decimal("0.0001")
        )

    def test_get_min_tick_size_from_precision_int(self):
        market_info = {"precision": {"price": 3}, "symbol": "ETHUSDT"}
        self.assertEqual(
            get_min_tick_size(market_info, self.mock_logger), Decimal("0.001")
        )

    def test_get_min_tick_size_from_limits_min(self):
        market_info = {"limits": {"price": {"min": "0.005"}}, "symbol": "XRPUSDT"}
        self.assertEqual(
            get_min_tick_size(market_info, self.mock_logger), Decimal("0.005")
        )

    def test_get_min_tick_size_default_fallback(self):
        market_info = {"symbol": "UNKNOWN"}
        self.assertEqual(
            get_min_tick_size(market_info, self.mock_logger), Decimal("0.0001")
        )
        self.mock_logger.warning.assert_called_with(
            "Could not determine specific min_tick_size for UNKNOWN from market_info. Using fallback based on derived price precision (4 places): 0.0001"
        )


class TestTimezoneFunctions(unittest.TestCase):
    def setUp(self):
        # Reset TIMEZONE to None before each test to ensure fresh initialization
        self._original_timezone = None
        if hasattr(sys.modules["utils"], "TIMEZONE"):
            self._original_timezone = sys.modules["utils"].TIMEZONE
            sys.modules["utils"].TIMEZONE = None
        self.mock_logger = MagicMock(spec=logging.Logger)
        # Patch the module-level logger in utils.py
        patcher = patch("utils._module_logger", self.mock_logger)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        # Restore original TIMEZONE after each test
        if self._original_timezone is not None:
            sys.modules["utils"].TIMEZONE = self._original_timezone
        elif hasattr(sys.modules["utils"], "TIMEZONE"):
            del sys.modules["utils"].TIMEZONE

    def test_set_timezone_utc(self):
        set_timezone("UTC")
        tz = get_timezone()
        self.assertIsNotNone(tz)
        self.assertEqual(str(tz), "UTC")
        self.mock_logger.info.assert_any_call("Timezone successfully set to: UTC")

    @patch("utils._ActualZoneInfo", side_effect=ImportError("zoneinfo not found"))
    def test_set_timezone_fallback_non_utc(self, mock_zoneinfo):
        # Simulate zoneinfo not being available and requesting a non-UTC timezone
        set_timezone("America/New_York")
        tz = get_timezone()
        self.assertIsNotNone(tz)
        self.assertEqual(str(tz), "UTC")  # Should fall back to UTC
        self.assertIsInstance(tz, FallbackZoneInfo)
        self.mock_logger.warning.assert_any_call(
            "Module 'zoneinfo' not found (requires Python 3.9+ and possibly 'tzdata' package). "
            "Using a basic UTC-only fallback for timezone handling. "
            "For full timezone support on older Python, consider installing 'pytz'."
        )
        self.mock_logger.warning.assert_any_call(
            "FallbackZoneInfo initialized with key 'America/New_York' which is not 'UTC'. "
            "This fallback only supports UTC. Effective timezone will be UTC."
        )

    def test_get_timezone_from_env(self):
        with patch.dict(os.environ, {"TIMEZONE": "Europe/London"}):
            # Clear TIMEZONE global to force re-initialization from env
            if hasattr(sys.modules["utils"], "TIMEZONE"):
                del sys.modules["utils"].TIMEZONE

            # Mock ZoneInfo to avoid actual import issues if tzdata is not installed
            with patch("utils._ActualZoneInfo") as MockZoneInfo:
                mock_london_tz = MagicMock()
                mock_london_tz.__str__.return_value = "Europe/London"
                MockZoneInfo.return_value = mock_london_tz

                tz = get_timezone()
                self.assertIsNotNone(tz)
                self.assertEqual(str(tz), "Europe/London")
                self.mock_logger.info.assert_any_call(
                    "TIMEZONE environment variable found: 'Europe/London'. Attempting to use it."
                )
                MockZoneInfo.assert_called_with("Europe/London")

    def test_get_timezone_default(self):
        with patch.dict(os.environ, {}, clear=True):  # Ensure no TIMEZONE env var
            # Clear TIMEZONE global to force re-initialization from default
            if hasattr(sys.modules["utils"], "TIMEZONE"):
                del sys.modules["utils"].TIMEZONE

            # Mock ZoneInfo to avoid actual import issues if tzdata is not installed
            with patch("utils._ActualZoneInfo") as MockZoneInfo:
                mock_chicago_tz = MagicMock()
                mock_chicago_tz.__str__.return_value = "America/Chicago"
                MockZoneInfo.return_value = mock_chicago_tz

                tz = get_timezone()
                self.assertIsNotNone(tz)
                self.assertEqual(str(tz), "America/Chicago")
                self.mock_logger.info.assert_any_call(
                    "TIMEZONE environment variable not set. Using default timezone: 'America/Chicago'."
                )
                MockZoneInfo.assert_called_with("America/Chicago")


if __name__ == "__main__":
    unittest.main()
