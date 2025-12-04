import unittest
from unittest.mock import MagicMock

from bybit_market_maker.risk_manager import RiskManager


class TestRiskManager(unittest.TestCase):
    def setUp(self):
        self.config = {
            "risk_management": {
                "max_drawdown": 0.05,
                "daily_loss_limit": 0.02,
                "position_limit": 10000,
                "stop_loss": 0.02,
                "take_profit": 0.03,
                "max_leverage": 5,
                "risk_per_trade": 0.02,
            },
        }
        self.logger = MagicMock()
        self.risk_manager = RiskManager(self.config, self.logger)

    def test_check_risk_limits(self):
        # Test with no position
        ok, msg = self.risk_manager.check_risk_limits(10000, {})
        self.assertTrue(ok)

        # Test with position within limits
        position = {"size": 1, "mark_price": 5000}
        ok, msg = self.risk_manager.check_risk_limits(10000, position)
        self.assertTrue(ok)

        # Test with position exceeding limit
        position = {"size": 3, "mark_price": 5000}
        ok, msg = self.risk_manager.check_risk_limits(10000, position)
        self.assertFalse(ok)

    def test_calculate_position_size(self):
        size = self.risk_manager.calculate_position_size(10000, 50000, "Buy")
        self.assertIsInstance(size, float)
        self.assertGreater(size, 0)

    def test_should_close_position(self):
        # Test with no position
        should_close, reason = self.risk_manager.should_close_position({}, 100)
        self.assertFalse(should_close)

        # Test with stop loss
        position = {"size": 1, "avg_price": 100, "side": "Buy"}
        should_close, reason = self.risk_manager.should_close_position(position, 97)
        self.assertTrue(should_close)
        self.assertEqual(reason, "stop_loss")

        # Test with take profit
        position = {"size": 1, "avg_price": 100, "side": "Buy"}
        should_close, reason = self.risk_manager.should_close_position(position, 104)
        self.assertTrue(should_close)
        self.assertEqual(reason, "take_profit")


if __name__ == "__main__":
    unittest.main()
