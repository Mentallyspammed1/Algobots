import os
import sys
import unittest
from decimal import Decimal
from unittest.mock import Mock, patch

import requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gemini_client import GeminiClient


class TestGeminiClient(unittest.TestCase):
    def setUp(self):
        self.api_key = "test_api_key"
        self.client = GeminiClient(api_key=self.api_key)
        self.indicator_data = {
            "RSI": Decimal("35.5"),
            "MACD_Line": Decimal("-10.2"),
            "current_price": Decimal("45000.00"),
        }

    @patch("requests.post")
    def test_get_trading_signal_success(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        # Corrected the mock response to be a compact JSON string
        api_response_content = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": '```json\n{"signal": "BUY", "confidence": 0.85, "reasoning": "RSI is oversold and MACD is showing bullish momentum."}\n```'
                            }
                        ]
                    }
                }
            ]
        }
        mock_response.json.return_value = api_response_content
        mock_post.return_value = mock_response

        signal = self.client.get_trading_signal(self.indicator_data)

        self.assertIsNotNone(signal)
        self.assertEqual(signal["signal"], "BUY")
        self.assertEqual(signal["confidence"], 0.85)

    @patch("requests.post")
    def test_get_trading_signal_http_error(self, mock_post):
        error_response = Mock()
        error_response.status_code = 500
        error_response.text = "Internal Server Error"

        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=error_response
        )
        mock_post.return_value = mock_response

        signal = self.client.get_trading_signal(self.indicator_data)
        self.assertIsNone(signal)

    @patch("requests.post")
    def test_get_trading_signal_json_decode_error(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        api_response_content = {
            "candidates": [{"content": {"parts": [{"text": "This is not valid JSON"}]}}]
        }
        mock_response.json.return_value = api_response_content
        mock_post.return_value = mock_response

        signal = self.client.get_trading_signal(self.indicator_data)
        self.assertIsNone(signal)

    def test_init_no_api_key(self):
        with self.assertRaises(ValueError):
            GeminiClient(api_key="")


if __name__ == "__main__":
    unittest.main()
