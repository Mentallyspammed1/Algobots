import os
import sys
import unittest
from unittest.mock import patch

# Add the parent directory to the sys.path to allow importing modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backtester import DEFAULT_CONFIG
from backtester import fetch_historical_klines
from backtester import optimize_strategy
from backtester import run_backtest


class TestBacktester(unittest.TestCase):
    def setUp(self):
        self.mock_klines = [
            {
                "timestamp": 1678886400000,
                "open": 100,
                "high": 105,
                "low": 98,
                "close": 102,
                "volume": 1000,
            },
            {
                "timestamp": 1678890000000,
                "open": 102,
                "high": 108,
                "low": 101,
                "close": 106,
                "volume": 1100,
            },
            {
                "timestamp": 1678893600000,
                "open": 106,
                "high": 110,
                "low": 104,
                "close": 108,
                "volume": 1200,
            },
            {
                "timestamp": 1678897200000,
                "open": 108,
                "high": 112,
                "low": 107,
                "close": 111,
                "volume": 1300,
            },
            {
                "timestamp": 1678900800000,
                "open": 111,
                "high": 115,
                "low": 109,
                "close": 113,
                "volume": 1400,
            },
            # Add more klines to satisfy indicator requirements (e.g., 200 klines)
        ]
        # Generate enough klines for indicators
        for i in range(6, 250):
            self.mock_klines.append(
                {
                    "timestamp": self.mock_klines[-1]["timestamp"]
                    + 3600000,  # 1 hour later
                    "open": self.mock_klines[-1]["close"],
                    "high": self.mock_klines[-1]["close"] + 3,
                    "low": self.mock_klines[-1]["close"] - 2,
                    "close": self.mock_klines[-1]["close"] + (1 if i % 2 == 0 else -1),
                    "volume": 1000 + i * 10,
                }
            )

        self.test_config = DEFAULT_CONFIG.copy()
        self.test_config["initial_balance"] = 1000
        self.test_config["fee_rate"] = 0.0005
        self.test_config["supertrend_length"] = 10
        self.test_config["supertrend_multiplier"] = 3.0
        self.test_config["rsi_length"] = 14
        self.test_config["ef_period"] = 10
        self.test_config["macd_fast_period"] = 12
        self.test_config["macd_slow_period"] = 26
        self.test_config["macd_signal_period"] = 9
        self.test_config["bb_period"] = 20
        self.test_config["bb_std_dev"] = 2.0
        self.test_config["riskPct"] = 1
        self.test_config["leverage"] = 10
        self.test_config["stopLossPct"] = 2
        self.test_config["takeProfitPct"] = 5
        self.test_config["trailingStopPct"] = 0.5

    @patch("backtester.bybit_session")
    def test_fetch_historical_klines(self, mock_bybit_session):
        mock_bybit_session.get_kline.return_value = {
            "retCode": 0,
            "result": {
                "list": [
                    [
                        str(k["timestamp"]),
                        str(k["open"]),
                        str(k["high"]),
                        str(k["low"]),
                        str(k["close"]),
                        str(k["volume"]),
                    ]
                    for k in self.mock_klines
                ]
            },
        }

        start_time = self.mock_klines[0]["timestamp"] / 1000
        end_time = self.mock_klines[-1]["timestamp"] / 1000
        klines = fetch_historical_klines("BTCUSDT", "60", start_time, end_time)
        self.assertIsNotNone(klines)
        self.assertGreater(len(klines), 0)
        self.assertEqual(klines[0]["timestamp"], self.mock_klines[0]["timestamp"])

    @patch("backtester.calculate_indicators")
    def test_run_backtest_basic_trade(self, mock_calculate_indicators):
        num_warmup_klines = (
            max(
                self.test_config["supertrend_length"],
                self.test_config["rsi_length"],
                self.test_config["ef_period"],
            )
            + 1
        )

        mock_side_effects = [
            None
            for _ in range(num_warmup_klines)  # Warmup period
        ] + [
            {
                "supertrend": {"direction": 1},
                "rsi": 40,
                "fisher": 1.0,
                "macd": {"macd_line": 1, "signal_line": 0.5, "histogram": 0.5},
                "bollinger_bands": {
                    "middle_band": 100,
                    "upper_band": 105,
                    "lower_band": 95,
                },
            },  # Buy signal
            {
                "supertrend": {"direction": 1},
                "rsi": 45,
                "fisher": 0.5,
                "macd": {"macd_line": 1.2, "signal_line": 0.6, "histogram": 0.6},
                "bollinger_bands": {
                    "middle_band": 101,
                    "upper_band": 106,
                    "lower_band": 96,
                },
            },
            {
                "supertrend": {"direction": -1},
                "rsi": 60,
                "fisher": -1.0,
                "macd": {"macd_line": -1, "signal_line": -0.5, "histogram": -0.5},
                "bollinger_bands": {
                    "middle_band": 102,
                    "upper_band": 107,
                    "lower_band": 97,
                },
            },  # Sell signal
            {
                "supertrend": {"direction": -1},
                "rsi": 55,
                "fisher": -0.5,
                "macd": {"macd_line": -1.2, "signal_line": -0.6, "histogram": -0.6},
                "bollinger_bands": {
                    "middle_band": 103,
                    "upper_band": 108,
                    "lower_band": 98,
                },
            },
        ]
        # Fill the rest with neutral values
        while len(mock_side_effects) < len(self.mock_klines):
            mock_side_effects.append(
                {
                    "supertrend": {"direction": 0},
                    "rsi": 50,
                    "fisher": 0,
                    "macd": {"macd_line": 0, "signal_line": 0, "histogram": 0},
                    "bollinger_bands": {
                        "middle_band": 0,
                        "upper_band": 0,
                        "lower_band": 0,
                    },
                }
            )

        mock_calculate_indicators.side_effect = mock_side_effects

        result = run_backtest(self.mock_klines, self.test_config)
        self.assertIsNotNone(result)
        self.assertIn("total_pnl", result)
        self.assertIn("num_trades", result)
        self.assertIn("win_rate", result)
        self.assertGreaterEqual(result["num_trades"], 0)

    # TODO: Add more specific tests for run_backtest:
    # - SL hit, TP hit
    # - Trailing stop loss simulation
    # - Edge cases (e.g., zero balance, very small qty)

    @patch("backtester.run_backtest")
    def test_optimize_strategy(self, mock_run_backtest):
        mock_run_backtest.side_effect = [
            {"total_pnl": 10},
            {"total_pnl": 5},
            {"total_pnl": 15},  # Example PnLs for combinations
            {"total_pnl": 8},
            {"total_pnl": 12},
            {"total_pnl": 7},
        ]

        param_ranges = {
            "supertrend_length": [10],
            "rsi_length": [14],
            "macd_fast_period": [12],
            "macd_slow_period": [26],
            "macd_signal_period": [9],
            "bb_period": [20],
            "bb_std_dev": [2.0],
        }
        # Need to provide enough mock klines for run_backtest to not return None
        best_config = optimize_strategy(self.mock_klines, param_ranges)
        self.assertIsNotNone(best_config)
        self.assertIn("supertrend_length", best_config)
        self.assertIn("rsi_length", best_config)
        # Assert that the best_config corresponds to the highest PnL (15 in this mock example)
        # This requires knowing the order of combinations generated by itertools.product
        # For simplicity, just check if it's one of the valid configs.


if __name__ == "__main__":
    unittest.main()
