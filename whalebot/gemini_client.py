import json
import logging
import os
import requests
from typing import Any, Dict
from colorama import Fore, Style, init

init(autoreset=True)

NEON_RED = Fore.LIGHTRED_EX
NEON_YELLOW = Fore.YELLOW
NEON_GREEN = Fore.LIGHTGREEN_EX
NEON_BLUE = Fore.CYAN
NEON_PURPLE = Fore.MAGENTA
RESET = Style.RESET_ALL

class GeminiClient:
    def __init__(self, api_key: str, model_name: str, temperature: float, top_p: float, logger: logging.Logger):
        self.api_key = api_key
        self.model_name = model_name
        self.temperature = temperature
        self.top_p = top_p
        self.logger = logger
        self.base_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"

    def analyze_market_data(self, prompt: str) -> Dict[str, Any] | None:
        headers = {
            "Content-Type": "application/json",
        }
        data = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": self.temperature,
                "topP": self.top_p,
            }
        }

        try:
            self.logger.debug(f"{NEON_BLUE}Sending prompt to Gemini: {prompt[:200]}...{RESET}")
            response = requests.post(self.base_url, headers=headers, json=data, timeout=30)
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            
            response_json = response.json()
            self.logger.debug(f"{NEON_BLUE}Received response from Gemini: {json.dumps(response_json)[:200]}...{RESET}")

            if "candidates" in response_json and response_json["candidates"]:
                # Assuming the first candidate's text is the relevant part
                gemini_text = response_json["candidates"][0]["content"]["parts"][0]["text"]
                
                # Attempt to parse the text as JSON
                try:
                    analysis = json.loads(gemini_text)
                    return analysis
                except json.JSONDecodeError:
                    self.logger.error(f"{NEON_RED}Gemini response is not valid JSON: {gemini_text}{RESET}")
                    return None
            else:
                self.logger.warning(f"{NEON_YELLOW}Gemini response did not contain candidates: {response_json}{RESET}")
                return None

        except requests.exceptions.HTTPError as e:
            self.logger.error(f"{NEON_RED}HTTP Error during Gemini API call: {e.response.status_code} - {e.response.text}{RESET}")
            return None
        except requests.exceptions.ConnectionError as e:
            self.logger.error(f"{NEON_RED}Connection Error during Gemini API call: {e}{RESET}")
            return None
        except requests.exceptions.Timeout:
            self.logger.error(f"{NEON_RED}Gemini API call timed out.{RESET}")
            return None
        except Exception as e:
            self.logger.error(f"{NEON_RED}Unexpected error during Gemini API call: {e}{RESET}", exc_info=True)
            return None

if __name__ == "__main__":
    # Example Usage (for testing purposes)
    from dotenv import load_dotenv
    import sys

    # Setup a basic logger for testing
    logging.basicConfig(level=logging.DEBUG, stream=sys.stdout, format='%(asctime)s - %(levelname)s - %(message)s')
    test_logger = logging.getLogger(__name__)

    # Load API key from .env file for testing
    load_dotenv()
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

    if not GEMINI_API_KEY:
        test_logger.error("GEMINI_API_KEY not found in .env. Please set it.")
        sys.exit(1)

    gemini_client = GeminiClient(
        api_key=GEMINI_API_KEY,
        model_name="gemini-pro",
        temperature=0.7,
        top_p=0.9,
        logger=test_logger
    )

    test_prompt = """Analyze the following market data and provide a trading recommendation in JSON format.
Current Price: 100.50
RSI: 75 (Overbought)
MACD: MACD Line 2.5, Signal Line 2.0 (Bullish Crossover)
Volume: 12345.67
Bollinger Bands: Upper 102.00, Middle 99.00, Lower 96.00 (Price near Upper Band)
Recommendation should include: "entry", "exit", "take_profit", "stop_loss", "confidence_level" (0-100).
Example JSON: {"entry": "BUY", "exit": "N/A", "take_profit": 103.00, "stop_loss": 98.00, "confidence_level": 85}
"""
    
    test_logger.info("Running Gemini API test...")
    analysis_result = gemini_client.analyze_market_data(test_prompt)

    if analysis_result:
        test_logger.info(f"{NEON_GREEN}Gemini Analysis Result: {json.dumps(analysis_result, indent=2)}{RESET}")
    else:
        test_logger.error(f"{NEON_RED}Gemini Analysis Failed.{RESET}")
