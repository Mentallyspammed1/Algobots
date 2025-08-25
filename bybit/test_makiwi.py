import importlib
import os
import sys
import unittest
from decimal import Decimal
from unittest.mock import patch

# Add the parent directory to the sys.path to allow importing makiwi
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

# Import functions and global states from makiwi.py
# We need to be careful with imports due to global state in makiwi.py
# For testing, we'll mock external dependencies and global state where necessary.
import makiwi

importlib.reload(makiwi) # Force reload the module

class TestHelperFunctions(unittest.TestCase):

    def test_calculate_decimal_precision(self):
        test_values = {
            Decimal("100"): 0,
            Decimal("100.0"): 0,
            Decimal("100.1"): 1,
            Decimal("100.12345"): 5,
            Decimal("0.00000001"): 8,
            Decimal("0"): 0,
            Decimal("-12.34"): 2,
        }
        for value, expected_precision in test_values.items():
            calculated_precision = makiwi._calculate_decimal_precision(value)
            self.assertEqual(calculated_precision, expected_precision, f"Failed for value {value}")
        self.assertEqual(makiwi._calculate_decimal_precision(123), 0) # Non-Decimal input

    # def test_is_valid_price(self):
    #     # Instantiate MarketMakingStrategy to call its instance method
    #     strategy_instance = makiwi.MarketMakingStrategy(client=None) # client is not used in _is_valid_price

    #     # Test case for Decimal("0")
    #     self.assertFalse(strategy_instance._is_valid_price(Decimal("0")))

    #     # Test case for negative Decimal
    #     self.assertFalse(strategy_instance._is_valid_price(Decimal("-10")))
    #     # Test case for valid Decimal
    #     self.assertTrue(strategy_instance._is_valid_price(Decimal("100")))
    #     # Test case for multiple valid Decimals
    #     self.assertTrue(strategy_instance._is_valid_price(Decimal("100.5"), Decimal("101.5"), Decimal("102.5")))
    #     # Test case for mixed valid and invalid Decimals
    #     self.assertFalse(strategy_instance._is_valid_price(Decimal("100"), Decimal("0"), Decimal("102")))

    @patch('makiwi.logger')
    def test_set_bot_state(self, mock_logger):
        # Test initial state change
        original_bot_state = makiwi.BOT_STATE # Store original state
        makiwi.BOT_STATE = "INITIALIZING" # Reset global state for test
        makiwi.set_bot_state("ACTIVE")
        self.assertEqual(makiwi.BOT_STATE, "ACTIVE")
        mock_logger.info.assert_called_with(f"{makiwi.Fore.CYAN}Bot State Change: INITIALIZING -> ACTIVE{makiwi.NC}")

        # Test no state change if already in target state
        mock_logger.info.reset_mock() # Clear previous calls
        makiwi.set_bot_state("ACTIVE")
        self.assertEqual(makiwi.BOT_STATE, "ACTIVE")
        mock_logger.info.assert_not_called()

        # Test another state change
        mock_logger.info.reset_mock()
        makiwi.set_bot_state("SHUTTING_DOWN")
        self.assertEqual(makiwi.BOT_STATE, "SHUTTING_DOWN")
        mock_logger.info.assert_called_with(f"{makiwi.Fore.CYAN}Bot State Change: ACTIVE -> SHUTTING_DOWN{makiwi.NC}")

        makiwi.BOT_STATE = original_bot_state # Restore original state

if __name__ == '__main__':
    unittest.main()
