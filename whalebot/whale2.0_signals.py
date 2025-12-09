Here is the complete, self-contained external module for integrating Gemini AI to generate scalping signals.

Save this code as gemini_scalp_signals.py.

This module provides the GeminiScalpSignalProvider class which:

Initializes the Gemini API using your GEMINI_API_KEY environment variable.

Constructs a detailed, structured prompt using the data provided by your main bot.

Requests a JSON response from the Gemini model.

Parses the JSON to return a clear signal, confidence level, and reasoning.

gemini_scalp_signals.py
code
Python
download
content_copy
expand_less
# gemini_scalp_signals.py

import json
import logging
import os
import time
from decimal import Decimal
from typing import Any, Dict, Literal, Optional, Tuple

try:
    # Attempt to import Google GenAI library
    import google.generativeai as genai
    from google.generativeai.types import HarmCategory, HarmBlockThreshold
    GEMINI_AVAILABLE = True
except ImportError:
    # Handle case where the library is not installed
    genai = None
    HarmCategory = None
    HarmBlockThreshold = None
    GEMINI_AVAILABLE = False

# --- Color Constants for Logging ---
NEON_BLUE = "\033[94m"
NEON_YELLOW = "\033[93m"
NEON_RED = "\033[91m"
RESET = "\033[0m"

# --- Core Class ---

class GeminiScalpSignalProvider:
    """
    Leverages the Gemini API to provide scalping signals based on market data.
    
    The output signal is qualitative (BUY/SELL/HOLD) with confidence and reasoning,
    as LLMs are not reliable for precise price prediction (Entry/TP/SL).
    """
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model = None
        
        if not GEMINI_AVAILABLE:
            self.logger.warning(f"{NEON_YELLOW}Gemini library not imported. Module is disabled.{RESET}")
            return

        if not self.api_key:
            self.logger.error(f"{NEON_RED}GEMINI_API_KEY not found in environment variables. Gemini module disabled.{RESET}")
            return

        try:
            genai.configure(api_key=self.api_key)
            
            # Configure safety settings to allow for more direct analysis
            safety_settings = [
                HarmBlockThreshold(HarmCategory.HARM_CATEGORY_HATE_SPEECH, HarmBlockThreshold.BLOCK_NONE),
                HarmBlockThreshold(HarmCategory.HARM_CATEGORY_HARASSMENT, HarmBlockThreshold.BLOCK_NONE),
                HarmBlockThreshold(HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, HarmBlockThreshold.BLOCK_NONE),
                HarmBlockThreshold(HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, HarmBlockThreshold.BLOCK_NONE),
            ]
            
            # Use a fast and capable model for quick analysis
            self.model = genai.GenerativeModel(
                model_name='gemini-2.5-flash', # Fast and capable for structured output
                safety_settings=safety_settings
            )
            self.logger.info(f"{NEON_BLUE}GeminiScalpSignalProvider initialized successfully.{RESET}")
            
        except Exception as e:
            self.logger.error(f"{NEON_RED}Failed to initialize Gemini API: {e}{RESET}")
            self.model = None

    def _prepare_prompt(
        self, 
        symbol: str, 
        interval: str, 
        current_price: Decimal, 
        indicator_values: Dict[str, Any], 
        mtf_trends: Dict[str, str],
        orderbook_imbalance: float
    ) -> str:
        """Formats the analysis data into a concise prompt for Gemini."""
        
        # Format indicator values concisely, focusing on momentum/short-term
        indicator_str = "\n".join([
            f"  - {k}: {v:.4f}" for k, v in indicator_values.items() 
            if not isinstance(v, (str, type(None))) and abs(v) < 1e6 and 
               any(key in k for key in ['RSI', 'StochRSI', 'MACD', 'ATR', 'DEMA', 'ROC', 'BB_Width', 'VWMA'])
        ])
        
        # Format MTF trends
        mtf_str = "\n".join([f"  - {k}: {v}" for k, v in mtf_trends.items()])
        
        prompt = f"""
        You are an expert, fast-acting HFT scalping analyst for the {symbol} market on a {interval} minute timeframe.
        Your entire focus is on predicting the next 1-3 candles based on current momentum, order book pressure, and short-term indicators.
        
        **CURRENT PRICE**: {current_price.normalize()}
        **ORDER FLOW IMBALANCE (Bid-Ask)**: {orderbook_imbalance:.4f} (Positive means more BUY pressure)
        
        **LATEST SHORT-TERM INDICATOR VALUES**:
        {indicator_str if indicator_str.strip() else '  - No key momentum indicators available.'}
        
        **HIGHER TIME FRAME CONTEXT**:
        {mtf_str if mtf_str else '  - None'}
        
        **TASK**: Analyze this data and provide a scalping signal.
        **OUTPUT FORMAT**: Respond ONLY with a single, valid JSON object. Do NOT include any other text or explanation outside of the JSON block.
        **JSON SCHEMA**: {{ "signal": "BUY" | "SELL" | "HOLD", "confidence": float (0.0 to 1.0), "reason": "string" }}
        """
        return prompt

    def generate_signal(
        self,
        symbol: str,
        interval: str,
        current_price: Decimal,
        indicator_values: Dict[str, Any],
        mtf_trends: Dict[str, str],
        orderbook_imbalance: float,
    ) -> Tuple[Literal["HOLD", "BUY", "SELL"], float, str, None, None, None]:
        """
        Generates a qualitative signal using the Gemini API.
        Returns: (signal, confidence, reason, entry_price, take_profit, stop_loss)
        Note: Entry/TP/SL are returned as None because LLMs cannot reliably predict precise prices.
        """
        
        if not self.model:
            return "HOLD", 0.0, "Gemini model not initialized or API key missing.", None, None, None

        prompt = self._prepare_prompt(
            symbol, interval, current_price, indicator_values, mtf_trends, orderbook_imbalance
        )
        
        try:
            # Set temperature low for deterministic, actionable signals
            response = self.model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json", "temperature": 0.1}
            )
            
            # Attempt to parse the JSON response
            try:
                signal_data = json.loads(response.text)
                signal = signal_data.get("signal", "HOLD").upper()
                confidence = float(signal_data.get("confidence", 0.0))
                reason = signal_data.get("reason", "No reason provided by Gemini.")
                
                if signal not in ["BUY", "SELL", "HOLD"]:
                    signal = "HOLD"
                    confidence = 0.0
                    reason = f"Gemini returned invalid signal '{signal}'. Defaulting to HOLD. Raw: {response.text}"
                    
                self.logger.info(f"{NEON_BLUE}Gemini Signal Received: {signal} (Conf: {confidence:.2f}) - {reason}{RESET}")
                
                # Return None for prices as they are determined by the main bot's risk engine
                return signal, confidence, reason, None, None, None
                
            except json.JSONDecodeError:
                self.logger.error(f"{NEON_RED}Gemini returned non-JSON response: {response.text}{RESET}")
                return "HOLD", 0.0, "Gemini failed to return valid JSON.", None, None, None

        except Exception as e:
            self.logger.error(f"{NEON_RED}Error calling Gemini API: {e}{RESET}")
            return "HOLD", 0.0, f"API Call Error: {e}", None, None, None