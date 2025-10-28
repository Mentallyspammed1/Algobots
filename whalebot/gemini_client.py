import json
import logging  # Import logging
import re
from decimal import Decimal
from typing import Any

import requests
from colorama import Fore, Style

NEON_RED = Fore.LIGHTRED_EX
NEON_YELLOW = Fore.YELLOW
RESET = Style.RESET_ALL


class GeminiClient:
    """A client for interacting with the Google Gemini API to get trading signals."""

    def __init__(
        self,
        api_key: str,
        logger: logging.Logger,
        model: str = "gemini-1.5-flash",
    ):
        """Initializes the GeminiClient.

        Args:
            api_key: The Google Gemini API key.
            logger: The logger instance for logging messages.
            model: The specific Gemini model to use.

        """
        if not api_key:
            raise ValueError("Gemini API key is required.")
        self.api_key = api_key
        self.logger = logger
        self.model = model
        self.api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

    def _prepare_prompt(self, indicator_data: dict[str, Any]) -> str:
        formatted_indicators = {
            key: str(value.normalize() if isinstance(value, Decimal) else value)
            for key, value in indicator_data.items()
        }
        prompt = f"""
        You are an expert trading analyst AI. Your task is to analyze the provided live market data and technical indicators for a cryptocurrency pair and provide a clear trading signal.

        **Market Data:**
        {json.dumps(formatted_indicators, indent=2)}

        **Analysis Task:**
        Based on the data above, please determine the most probable market direction.

        **Response Format:**
        Your response MUST be a valid JSON object with the following structure:
        {{
          "signal": "BUY", "SELL", or "HOLD",
          "confidence": A float between 0.0 and 1.0 representing your confidence in the signal,
          "reasoning": "A brief, one-sentence explanation for your decision."
        }}

        Provide only the JSON object in your response.
        """
        return prompt

    def get_trading_signal(
        self,
        indicator_data: dict[str, Any],
    ) -> dict[str, Any] | None:
        prompt = self._prepare_prompt(indicator_data)
        headers = {"Content-Type": "application/json"}
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        text_content = ""
        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()

            response_json = response.json()
            text_content = (
                response_json.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )

            json_match = re.search(r"```json\s*({.*?})\s*```", text_content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = text_content.strip()

            signal_data = json.loads(json_str)

            if (
                "signal" in signal_data
                and "confidence" in signal_data
                and "reasoning" in signal_data
            ):
                return signal_data
            self.logger.warning(
                f"{NEON_YELLOW}Gemini API response is missing required keys.{RESET}",
            )
            return None

        except requests.exceptions.Timeout:
            self.logger.error(f"{NEON_RED}Error: Gemini API request timed out.{RESET}")
        except requests.exceptions.HTTPError as e:
            self.logger.error(
                f"{NEON_RED}Error: Gemini API HTTP error: {e.response.status_code} - {e.response.text}{RESET}",
            )
        except requests.exceptions.RequestException as e:
            self.logger.error(
                f"{NEON_RED}Error: An unexpected error occurred during Gemini API request: {e}{RESET}",
                exc_info=True,
            )
        except json.JSONDecodeError:
            self.logger.error(
                f"{NEON_RED}Error: Failed to decode JSON response from Gemini API. Raw text was: {text_content}{RESET}",
            )

        return None
