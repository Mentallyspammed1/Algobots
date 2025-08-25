import collections
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add the parent directory to the sys.path to allow importing modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock os.getenv before importing backbone to prevent actual env var loading
with patch.dict(os.environ, {
    'BYBIT_API_KEY': 'test_bybit_key',
    'BYBIT_API_SECRET': 'test_bybit_secret',
    'GEMINI_API_KEY': 'test_gemini_key'
}):
    from backbone import BOT_STATE, app, log_message

class TestBackbone(unittest.TestCase):

    def setUp(self):
        # Set up a test client for the Flask app
        self.app = app.test_client()
        self.app.testing = True

        # Reset BOT_STATE before each test to ensure isolation
        BOT_STATE["running"] = False
        BOT_STATE["thread"] = None
        BOT_STATE["config"] = {}
        BOT_STATE["bybit_session"] = None
        BOT_STATE["logs"] = collections.deque(maxlen=200)
        BOT_STATE["trade_history"] = {"wins": 0, "losses": 0, "history": []}
        BOT_STATE["dashboard"] = {
            "currentPrice": "---", "priceChange": "---", "stDirection": "---",
            "stValue": "---", "rsiValue": "---", "rsiStatus": "---",
            "currentPosition": "None", "positionPnL": "---", "accountBalance": "---",
            "totalTrades": 0, "winRate": "0%", "botStatus": "Idle",
        }
        BOT_STATE["last_supertrend"] = {"direction": 0, "value": 0}
        BOT_STATE["previous_close"] = 0
        BOT_STATE["current_position_info"] = {"order_id": None, "entry_price": None, "side": None, "peak_price": None}

    def test_log_message(self):
        log_message("Test info message", "info")
        self.assertEqual(len(BOT_STATE["logs"]), 1)
        self.assertEqual(BOT_STATE["logs"][0]["message"], "Test info message")
        self.assertEqual(BOT_STATE["logs"][0]["level"], "info")

        log_message("Test error message", "error")
        self.assertEqual(len(BOT_STATE["logs"]), 2)
        self.assertEqual(BOT_STATE["logs"][1]["level"], "error")

    @patch('backbone.HTTP')
    @patch('backbone.log_message')
    def test_start_bot_success(self, mock_log_message, mock_http):
        # Mock the Bybit HTTP session and its methods
        mock_session_instance = MagicMock()
        mock_http.return_value = mock_session_instance
        mock_session_instance.get_wallet_balance.return_value = {'retCode': 0, 'result': {'list': [{'totalWalletBalance': '1000'}]}}
        mock_session_instance.get_instruments_info.return_value = {'retCode': 0, 'result': {'list': [{'priceFilter': {'tickSize': '0.01'}, 'lotFilter': {'qtyStep': '0.001'}}]}}
        mock_session_instance.set_leverage.return_value = {'retCode': 0}

        config_data = {
            "apiKey": "test_key", "apiSecret": "test_secret", "symbol": "BTCUSDT",
            "interval": "60", "leverage": 10, "riskPct": 1, "stopLossPct": 2,
            "takeProfitPct": 5, "efPeriod": 10,
            "macdFastPeriod": 12, "macdSlowPeriod": 26, "macdSignalPeriod": 9,
            "bbPeriod": 20, "bbStdDev": 2.0
        }
        response = self.app.post('/api/start', data=json.dumps(config_data), content_type='application/json')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'success')
        self.assertTrue(BOT_STATE["running"])
        self.assertIsNotNone(BOT_STATE["thread"])
        mock_log_message.assert_any_call("API connection successful.", "success")
        self.assertEqual(BOT_STATE["config"]["price_precision"], 2)
        self.assertEqual(BOT_STATE["config"]["qty_precision"], 3)
        self.assertEqual(BOT_STATE["config"]["macd_fast_period"], 12)
        self.assertEqual(BOT_STATE["config"]["macd_slow_period"], 26)
        self.assertEqual(BOT_STATE["config"]["macd_signal_period"], 9)
        self.assertEqual(BOT_STATE["config"]["bb_period"], 20)
        self.assertEqual(BOT_STATE["config"]["bb_std_dev"], 2.0)

    @patch('backbone.HTTP')
    @patch('backbone.log_message')
    def test_start_bot_api_failure(self, mock_log_message, mock_http):
        mock_session_instance = MagicMock()
        mock_http.return_value = mock_session_instance
        mock_session_instance.get_wallet_balance.return_value = {'retCode': 10001, 'retMsg': 'API Error'}

        config_data = {
            "apiKey": "test_key", "apiSecret": "test_secret", "symbol": "BTCUSDT",
            "interval": "60", "leverage": 10, "riskPct": 1, "stopLossPct": 2,
            "takeProfitPct": 5, "efPeriod": 10
        }
        response = self.app.post('/api/start', data=json.dumps(config_data), content_type='application/json')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(data['status'], 'error')
        self.assertFalse(BOT_STATE["running"])
        mock_log_message.assert_any_call(unittest.mock.ANY, "error") # Check for any error message

    def test_stop_bot(self):
        BOT_STATE["running"] = True
        BOT_STATE["thread"] = MagicMock() # Mock the thread
        response = self.app.post('/api/stop')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'success')
        self.assertFalse(BOT_STATE["running"])
        self.assertIsNone(BOT_STATE["thread"])
        self.assertEqual(BOT_STATE["dashboard"]["botStatus"], "Idle")
        self.assertIsNone(BOT_STATE["current_position_info"]["order_id"])

    def test_get_status(self):
        BOT_STATE["running"] = True
        BOT_STATE["dashboard"]["currentPrice"] = "$50000"
        BOT_STATE["logs"].append({"timestamp": "12:00:00", "level": "info", "message": "Test log"})

        response = self.app.get('/api/status')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['running'])
        self.assertEqual(data['dashboard']['currentPrice'], "$50000")
        self.assertIn('macdLine', data['dashboard'])
        self.assertIn('macdSignal', data['dashboard'])
        self.assertIn('macdHistogram', data['dashboard'])
        self.assertIn('bbMiddle', data['dashboard'])
        self.assertIn('bbUpper', data['dashboard'])
        self.assertIn('bbLower', data['dashboard'])
        self.assertEqual(len(data['logs']), 1)
        self.assertEqual(data['logs'][0]['message'], "Test log")

    @patch('backbone.genai.GenerativeModel')
    @patch('backbone.log_message')
    def test_gemini_insight_success(self, mock_log_message, mock_generative_model):
        mock_model_instance = MagicMock()
        mock_generative_model.return_value = mock_model_instance
        mock_model_instance.generate_content.return_value.text = "Mocked Gemini Insight"

        prompt_data = {"prompt": "Analyze market"}
        response = self.app.post('/api/gemini-insight', data=json.dumps(prompt_data), content_type='application/json')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['insight'], 'Mocked Gemini Insight')

    @patch('backbone.genai.GenerativeModel')
    @patch('backbone.log_message')
    def test_gemini_insight_api_error(self, mock_log_message, mock_generative_model):
        mock_model_instance = MagicMock()
        mock_generative_model.return_value = mock_model_instance
        mock_model_instance.generate_content.side_effect = Exception("Gemini API Error")

        prompt_data = {"prompt": "Analyze market"}
        response = self.app.post('/api/gemini-insight', data=json.dumps(prompt_data), content_type='application/json')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(data['status'], 'error')
        self.assertIn('Gemini API Error', data['message'])
        mock_log_message.assert_any_call(unittest.mock.ANY, "error") # Check for any error message

    # TODO: Add tests for trading_bot_loop logic (requires extensive mocking of session.get_kline, session.get_positions, session.place_order, session.amend_order)
    # This would involve setting up complex side_effects for mock objects to simulate market conditions and bot actions.

if __name__ == '__main__':
    unittest.main()
