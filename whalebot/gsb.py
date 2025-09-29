import base64
import hashlib
import hmac
import io
import json
import logging
import os
import sys
import time
import urllib.parse
from datetime import date, datetime
from decimal import ROUND_DOWN, Decimal, getcontext
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, ClassVar
from zoneinfo import ZoneInfo

import google.generativeai as genai
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from colorama import Fore, Style, init
from dotenv import load_dotenv
from google.generativeai.types import GenerateContentResponse, Part
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Scikit-learn is explicitly excluded as per user request.
SKLEARN_AVAILABLE = False

# Initialize colorama and set decimal precision
getcontext().prec = 28
init(autoreset=True)
load_dotenv()

# Neon Color Scheme
NEON_GREEN = Fore.LIGHTGREEN_EX
NEON_BLUE = Fore.CYAN
NEON_PURPLE = Fore.MAGENTA
NEON_YELLOW = Fore.YELLOW
NEON_RED = Fore.LIGHTRED_EX
NEON_CYAN = Fore.CYAN
RESET = Style.RESET_ALL

# Indicator specific colors
INDICATOR_COLORS = {
    "SMA_10": Fore.LIGHTBLUE_EX,
    "SMA_Long": Fore.BLUE,
    "EMA_Short": Fore.LIGHTMAGENTA_EX,
    "EMA_Long": Fore.MAGENTA,
    "ATR": Fore.YELLOW,
    "RSI": Fore.GREEN,
    "StochRSI_K": Fore.CYAN,
    "StochRSI_D": Fore.LIGHTCYAN_EX,
    "BB_Upper": Fore.RED,
    "BB_Middle": Fore.WHITE,
    "BB_Lower": Fore.RED,
    "CCI": Fore.LIGHTGREEN_EX,
    "WR": Fore.LIGHTRED_EX,
    "MFI": Fore.GREEN,
    "OBV": Fore.BLUE,
    "OBV_EMA": Fore.LIGHTBLUE_EX,
    "CMF": Fore.MAGENTA,
    "Tenkan_Sen": Fore.CYAN,
    "Kijun_Sen": Fore.LIGHTCYAN_EX,
    "Senkou_Span_A": Fore.GREEN,
    "Senkou_Span_B": Fore.RED,
    "Chikou_Span": Fore.YELLOW,
    "PSAR_Val": Fore.MAGENTA,
    "PSAR_Dir": Fore.LIGHTMAGENTA_EX,
    "VWAP": Fore.WHITE,
    "ST_Fast_Dir": Fore.BLUE,
    "ST_Fast_Val": Fore.LIGHTBLUE_EX,
    "ST_Slow_Dir": Fore.MAGENTA,
    "ST_Slow_Val": Fore.LIGHTMAGENTA_EX,
    "MACD_Line": Fore.GREEN,
    "MACD_Signal": Fore.LIGHTGREEN_EX,
    "MACD_Hist": Fore.YELLOW,
    "ADX": Fore.CYAN,
    "PlusDI": Fore.LIGHTCYAN_EX,
    "MinusDI": Fore.RED,
}

# --- Constants ---
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
BASE_URL = os.getenv("BYBIT_BASE_URL", "https://api.bybit.com")
CONFIG_FILE = "config.json"
LOG_DIRECTORY = "bot_logs"
Path(LOG_DIRECTORY).mkdir(parents=True, exist_ok=True)

TIMEZONE = ZoneInfo("America/Chicago")
MAX_API_RETRIES = 5
RETRY_DELAY_SECONDS = 7
REQUEST_TIMEOUT = 20
LOOP_DELAY_SECONDS = 15

# Magic Numbers as Constants
MIN_DATA_POINTS_TR = 2
MIN_DATA_POINTS_SMOOTHER = 2
MIN_DATA_POINTS_OBV = 2
MIN_DATA_POINTS_PSAR = 2
ADX_STRONG_TREND_THRESHOLD = 25
ADX_WEAK_TREND_THRESHOLD = 20


class GeminiSignalAnalyzer:
    """Advanced signal analysis using Google's Gemini AI."""

    def __init__(
        self,
        api_key: str,
        logger: logging.Logger,
        model: str = "gemini-1.5-flash-latest",
        config: dict[str, Any] = None,
    ):
        """Initialize the Gemini Signal Analyzer."""
        self.logger = logger
        self.model = model
        self.config = config if config is not None else {}

        # Initialize Gemini client
        try:
            genai.configure(api_key=api_key)
            self.client = genai.GenerativeModel(model_name=self.model)
            self.logger.info(f"Gemini API initialized with model: {model}")
        except Exception as e:
            self.logger.error(f"Failed to initialize Gemini API: {e}")
            raise

        # --- Caching ---
        self._analysis_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._cache_ttl = self.config.get("cache_ttl_seconds", 300)  # Default 5 minutes

        # --- Performance Metrics Tracking ---
        self.performance_metrics = {
            "total_analyses": 0,
            "successful_analyses": 0,
            "api_errors": 0,
            "avg_response_time_ms": 0.0,
            "signal_accuracy": {},  # {signal_type: {'correct': X, 'total': Y}}
            "cache_hits": 0,
        }

        # --- API Safety Checks and Limits ---
        self.daily_api_calls = 0
        self.daily_limit = self.config.get(
            "daily_api_limit", 1000
        )  # Default 1000 calls
        self.last_reset = date.today()

    def _check_api_limits(self) -> bool:
        """Check if API calls are within limits for the current day."""
        current_date = date.today()
        if current_date > self.last_reset:
            self.daily_api_calls = 0
            self.last_reset = current_date
            self.logger.info("Daily API call count reset.")

        if self.daily_api_calls >= self.daily_limit:
            self.logger.warning(
                f"Daily Gemini API limit ({self.daily_limit}) reached. Skipping AI analysis for today."
            )
            return False

        self.daily_api_calls += 1
        return True

    def _get_cache_key(self, market_summary: dict[str, Any]) -> str:
        """Generate a stable cache key from relevant market data."""
        # Use a subset of the summary for the cache key to allow for slight variations
        # without invalidating cache too frequently (e.g., ignore timestamp)
        key_data = {
            "symbol": market_summary.get("symbol"),
            "price_rounded": round(
                market_summary.get("price_statistics", {}).get("current", 0.0), 2
            ),
            "indicators_summary": {
                k: round(float(v), 2) if isinstance(v, (Decimal, float)) else v
                for k, v in market_summary.get("technical_indicators", {}).items()
                if k in ["RSI", "MACD_Hist", "ADX"]
            },  # Example subset
            "mtf_trends": str(
                sorted(market_summary.get("multi_timeframe_trends", {}).items())
            ),
        }
        return hashlib.md5(
            json.dumps(key_data, sort_keys=True).encode("utf-8")
        ).hexdigest()

    def analyze_market_context(
        self,
        df: pd.DataFrame,
        indicator_values: dict[str, Any],
        current_price: Decimal,
        symbol: str,
        mtf_trends: dict[str, str],
    ) -> dict[str, Any]:
        """Analyze market context using Gemini AI for comprehensive signal generation, with caching."""
        if not self._check_api_limits():
            self.performance_metrics["api_errors"] += 1
            return {
                "signal": "HOLD",
                "confidence": 0,
                "analysis": "API daily limit reached.",
                "risk_level": "HIGH",
                "market_sentiment": "NEUTRAL",
            }

        market_summary = self._prepare_market_summary(
            df, indicator_values, current_price, symbol, mtf_trends
        )
        if (
            not market_summary
        ):  # Handle case where _prepare_market_summary returns empty
            return {
                "signal": "HOLD",
                "confidence": 0,
                "analysis": "Insufficient data for market summary.",
                "risk_level": "HIGH",
                "market_sentiment": "NEUTRAL",
            }

        cache_key = self._get_cache_key(market_summary)

        # Check cache
        if cache_key in self._analysis_cache:
            cached_time, cached_result = self._analysis_cache[cache_key]
            if time.time() - cached_time < self._cache_ttl:
                self.logger.debug(f"Using cached Gemini analysis for key: {cache_key}")
                self.performance_metrics["cache_hits"] += 1
                return cached_result

        start_time = time.perf_counter()
        result = {}
        try:
            # Generate AI analysis prompt
            prompt_content = self._create_analysis_prompt(market_summary)
            contents_parts = [prompt_content]

            response: GenerateContentResponse = self.client.generate_content(
                contents_parts,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3, response_mime_type="application/json"
                ),
            )

            if response.candidates and response.candidates[0].content.parts:
                json_string = response.candidates[0].content.parts[0].text
                result = json.loads(json_string)
                self.logger.debug(f"Gemini Analysis Raw Result: {result}")
                self.logger.info(
                    f"Gemini Analysis Complete: Signal={result.get('signal')}, Confidence={result.get('confidence')}%"
                )
                self.performance_metrics["successful_analyses"] += 1
            else:
                self.logger.warning("Gemini API returned no content or candidates.")
                result = {
                    "signal": "HOLD",
                    "confidence": 0,
                    "analysis": "Gemini returned no content.",
                    "risk_level": "MEDIUM",
                    "market_sentiment": "NEUTRAL",
                }
                self.performance_metrics["api_errors"] += 1

        except json.JSONDecodeError as e:
            self.logger.error(
                f"Error decoding JSON from Gemini response: {e}. Response: {response.text if 'response' in locals() else 'N/A'}"
            )
            result = {
                "signal": "HOLD",
                "confidence": 0,
                "analysis": f"JSON decoding error: {e}",
                "risk_level": "HIGH",
                "market_sentiment": "NEUTRAL",
            }
            self.performance_metrics["api_errors"] += 1
        except Exception as e:
            self.logger.error(f"Error in Gemini market analysis: {e}")
            result = {
                "signal": "HOLD",
                "confidence": 0,
                "analysis": f"General error during AI analysis: {e}",
                "risk_level": "HIGH",
                "market_sentiment": "NEUTRAL",
            }
            self.performance_metrics["api_errors"] += 1
        finally:
            end_time = time.perf_counter()
            response_time_ms = (end_time - start_time) * 1000
            # Update average response time
            self.performance_metrics["avg_response_time_ms"] = (
                (
                    (
                        self.performance_metrics["avg_response_time_ms"]
                        * (
                            self.performance_metrics["total_analyses"]
                            - self.performance_metrics["cache_hits"]
                        )
                    )
                    + response_time_ms
                )
                / (
                    self.performance_metrics["total_analyses"]
                    - self.performance_metrics["cache_hits"]
                    + 1e-9
                )
                if (
                    self.performance_metrics["total_analyses"]
                    - self.performance_metrics["cache_hits"]
                )
                > 0
                else response_time_ms
            )

            self.performance_metrics["total_analyses"] += 1

        # Cache the result
        if result and (
            result.get("signal") != "HOLD" or result.get("confidence", 0) > 0
        ):  # Only cache valid results
            self._analysis_cache[cache_key] = (time.time(), result)
        return result

    def _prepare_market_summary(
        self,
        df: pd.DataFrame,
        indicator_values: dict[str, Any],
        current_price: Decimal,
        symbol: str,
        mtf_trends: dict[str, str],
    ) -> dict[str, Any]:
        """Prepare a comprehensive market summary for AI analysis."""
        safe_df = df.copy()
        if safe_df.empty:
            self.logger.warning("DataFrame is empty, cannot prepare market summary.")
            return {}

        # Calculate price statistics
        price_stats = {
            "current": float(current_price),
            "24h_high": float(safe_df["high"].tail(96).max())
            if len(safe_df) >= 96
            else float(safe_df["high"].max()),
            "24h_low": float(safe_df["low"].tail(96).min())
            if len(safe_df) >= 96
            else float(safe_df["low"].min()),
            "24h_change_pct": float(
                (current_price - Decimal(str(safe_df["close"].iloc[-96])))
                / Decimal(str(safe_df["close"].iloc[-96]))
                * 100
            )
            if len(safe_df) >= 96
            else 0.0,
            "volume_24h": float(safe_df["volume"].tail(96).sum())
            if len(safe_df) >= 96
            else float(safe_df["volume"].sum()),
            "avg_volume": float(safe_df["volume"].tail(96).mean())
            if len(safe_df) >= 96
            else float(safe_df["volume"].mean()),
        }

        # Format indicator values
        formatted_indicators = {}
        for key, value in indicator_values.items():
            if isinstance(value, (Decimal, float, int, np.floating, np.integer)):
                formatted_indicators[key] = float(value)
            elif pd.isna(value):
                formatted_indicators[key] = None
            else:
                formatted_indicators[key] = str(value)

        # Recent price action (last 5 candles, newest first)
        recent_candles = []
        for i in range(min(5, len(safe_df))):
            idx = -(i + 1)
            recent_candles.append(
                {
                    "open": float(safe_df["open"].iloc[idx]),
                    "high": float(safe_df["high"].iloc[idx]),
                    "low": float(safe_df["low"].iloc[idx]),
                    "close": float(safe_df["close"].iloc[idx]),
                    "volume": float(safe_df["volume"].iloc[idx]),
                }
            )

        return {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "price_statistics": price_stats,
            "technical_indicators": formatted_indicators,
            "multi_timeframe_trends": mtf_trends,
            "recent_candles": recent_candles,
            "market_conditions": self._detect_market_conditions(
                safe_df, formatted_indicators
            ),
        }

    def _detect_market_conditions(
        self, df: pd.DataFrame, indicator_values: dict[str, Any]
    ) -> dict[str, Any]:
        """Detect specific market conditions based on indicators."""
        conditions = {
            "volatility": "NORMAL",
            "trend_strength": "NEUTRAL",
            "volume_profile": "AVERAGE",
        }

        if df.empty:
            return conditions

        if "ATR" in indicator_values and indicator_values["ATR"] is not None:
            atr = float(indicator_values["ATR"])
            if "ATR" in df.columns and len(df) >= 20 and not df["ATR"].isnull().all():
                recent_atr_mean = float(df["ATR"].tail(20).mean())
                if atr > recent_atr_mean * 1.5:
                    conditions["volatility"] = "HIGH"
                elif atr < recent_atr_mean * 0.5:
                    conditions["volatility"] = "LOW"
            elif atr > (float(df["high"].iloc[-1]) - float(df["low"].iloc[-1])) * 0.5:
                conditions["volatility"] = "HIGH"
        else:
            conditions["volatility"] = "UNKNOWN"

        if "ADX" in indicator_values and indicator_values["ADX"] is not None:
            adx = float(indicator_values["ADX"])
            if adx > 40:
                conditions["trend_strength"] = "STRONG"
            elif adx > 25:
                conditions["trend_strength"] = "MODERATE"
            elif adx < 20:
                conditions["trend_strength"] = "WEAK"
        else:
            conditions["trend_strength"] = "UNKNOWN"

        if len(df) >= 20:
            recent_volume = df["volume"].tail(5).mean()
            avg_volume = df["volume"].tail(20).mean()
            if recent_volume > avg_volume * 1.5:
                conditions["volume_profile"] = "HIGH"
            elif recent_volume < avg_volume * 0.5:
                conditions["volume_profile"] = "LOW"
        else:
            conditions["volume_profile"] = "UNKNOWN"

        return conditions

    def _format_market_data(self, market_summary: dict[str, Any]) -> str:
        """Helper to format market data for the prompt."""
        data_str = f"""
        Symbol: {market_summary.get("symbol", "N/A")}
        Current Price: ${market_summary.get("price_statistics", {}).get("current", 0.0):.2f}
        24h High: ${market_summary.get("price_statistics", {}).get("24h_high", 0.0):.2f}
        24h Low: ${market_summary.get("price_statistics", {}).get("24h_low", 0.0):.2f}
        24h Change: {market_summary.get("price_statistics", {}).get("24h_change_pct", 0.0):.2f}%
        Volume (24h): {market_summary.get("price_statistics", {}).get("volume_24h", 0.0):.2f}
        
        Technical Indicators (latest values):
        {json.dumps(market_summary.get("technical_indicators", {}), indent=2)}
        
        Multi-Timeframe Trends:
        {json.dumps(market_summary.get("multi_timeframe_trends", {}), indent=2)}
        
        Market Conditions:
        {json.dumps(market_summary.get("market_conditions", {}), indent=2)}
        
        Recent Price Action (Last {len(market_summary.get("recent_candles", []))} candles, newest first):
        {json.dumps(market_summary.get("recent_candles", [])[:5], indent=2)}
        """
        return data_str

    def _create_analysis_prompt(self, market_summary: dict[str, Any]) -> str:
        """Create a detailed prompt for Gemini analysis with few-shot examples."""
        # Few-shot examples for better consistency
        few_shot_examples = """
        Example 1:
        MARKET DATA:
        Symbol: BTCUSDT
        Current Price: $65000.00
        24h Change: 1.50%
        Technical Indicators: {"RSI": 72.0, "MACD_Hist": 150.0, "ADX": 35.0, "EMA_Short": 64500.0, "EMA_Long": 63000.0}
        Multi-Timeframe Trends: {"1h_ema": "UP", "4h_ema": "UP"}
        Market Conditions: {"volatility": "MODERATE", "trend_strength": "STRONG", "volume_profile": "HIGH"}
        
        JSON OUTPUT:
        {"signal": "HOLD", "confidence": 65, "analysis": "Price is overbought per RSI but showing strong momentum and trend alignment across higher timeframes. MACD histogram is positive but may be peaking. Volume is high. Await clear reversal or breakout confirmation.", "key_factors": ["RSI overbought", "Strong uptrend", "High volume", "MTF alignment"], "risk_level": "MEDIUM", "market_sentiment": "BULLISH", "pattern_detected": "None", "suggested_entry": null, "suggested_stop_loss": null, "suggested_take_profit": null}
        
        Example 2:
        MARKET DATA:
        Symbol: ETHUSDT
        Current Price: $3200.00
        24h Change: -2.80%
        Technical Indicators: {"RSI": 28.0, "MACD_Hist": -80.0, "ADX": 20.0, "EMA_Short": 3250.0, "EMA_Long": 3300.0}
        Multi-Timeframe Trends: {"1h_ema": "DOWN", "4h_ema": "SIDEWAYS"}
        Market Conditions: {"volatility": "HIGH", "trend_strength": "WEAK", "volume_profile": "LOW"}
        
        JSON OUTPUT:
        {"signal": "BUY", "confidence": 70, "analysis": "RSI indicates oversold conditions, potentially signaling a bounce. Price is below EMAs, but ADX suggests weak trend. Volume is low, which could lead to sharp reversals. High volatility suggests careful entry. Looking for a bounce off recent support.", "key_factors": ["RSI oversold", "Weak trend", "High volatility", "Low volume"], "risk_level": "HIGH", "market_sentiment": "BEARISH", "pattern_detected": "Potential Double Bottom", "suggested_entry": 3180.00, "suggested_stop_loss": 3100.00, "suggested_take_profit": 3350.00}
        """

        prompt = f"""
        You are an expert cryptocurrency trading bot. Analyze the following real-time market data and provide a trading signal (BUY, SELL, HOLD) and comprehensive analysis.

        **Your output MUST be a JSON object conforming to the following schema:**
        ```json
        {{
            "signal": {{ "type": "string", "enum": ["BUY", "SELL", "HOLD"] }},
            "confidence": {{ "type": "number", "minimum": 0, "maximum": 100, "description": "Confidence level in percentage for the signal." }},
            "analysis": {{ "type": "string", "description": "Detailed explanation of the reasoning behind the signal." }},
            "key_factors": {{ "type": "array", "items": {{ "type": "string" }}, "description": "Top influencing factors for the decision." }},
            "risk_level": {{ "type": "string", "enum": ["LOW", "MEDIUM", "HIGH"], "description": "Assessed risk level for taking this trade." }},
            "suggested_entry": {{ "type": "number", "optional": true, "description": "Suggested entry price." }},
            "suggested_stop_loss": {{ "type": "number", "optional": true, "description": "Suggested stop loss price." }},
            "suggested_take_profit": {{ "type": "number", "optional": true, "description": "Suggested take profit price." }},
            "market_sentiment": {{ "type": "string", "enum": ["BULLISH", "BEARISH", "NEUTRAL"], "description": "Overall market sentiment." }},
            "pattern_detected": {{ "type": "string", "optional": true, "description": "Notable chart pattern detected (e.g., 'Head and Shoulders', 'Double Bottom', 'Bull Flag')." }}
        }}
        ```
        
        {few_shot_examples}

        **Now, analyze the following MARKET DATA FOR ANALYSIS:**
        {self._format_market_data(market_summary)}

        **Based on the provided data, provide your expert trading analysis and signal in the specified JSON format.**
        Consider all aspects: price action, indicator confluence/divergence, volume, multi-timeframe trends, and market conditions.
        If a pattern or suggested levels are not applicable or too uncertain, set them to `null`.
        """
        return prompt

    def generate_advanced_signal(
        self,
        df: pd.DataFrame,
        indicator_values: dict[str, Any],
        current_price: Decimal,
        symbol: str,
        mtf_trends: dict[str, str],
        existing_signal: str,
        existing_score: float,
    ) -> tuple[str, float, dict[str, Any]]:
        """Generate an advanced signal combining AI analysis with existing technical signals."""
        ai_analysis = self.analyze_market_context(
            df, indicator_values, current_price, symbol, mtf_trends
        )

        combined_signal, combined_score = self._combine_signals(
            existing_signal, existing_score, ai_analysis
        )

        signal_details = {
            "final_signal": combined_signal,
            "final_score": combined_score,
            "technical_signal": existing_signal,
            "technical_score": existing_score,
            "ai_signal": ai_analysis.get("signal", "HOLD"),
            "ai_confidence": ai_analysis.get("confidence", 0),
            "ai_analysis": ai_analysis.get("analysis", ""),
            "key_factors": ai_analysis.get("key_factors", []),
            "risk_level": ai_analysis.get("risk_level", "MEDIUM"),
            "market_sentiment": ai_analysis.get("market_sentiment", "NEUTRAL"),
            "pattern_detected": ai_analysis.get("pattern_detected", "None"),
            "suggested_levels": {
                "entry": ai_analysis.get("suggested_entry"),
                "stop_loss": ai_analysis.get("suggested_stop_loss"),
                "take_profit": ai_analysis.get("suggested_take_profit"),
            },
        }

        self._log_signal_details(signal_details)

        return combined_signal, combined_score, signal_details

    def _combine_signals(
        self, technical_signal: str, technical_score: float, ai_analysis: dict[str, Any]
    ) -> tuple[str, float]:
        """Combine technical and AI signals with weighted scoring."""
        TECHNICAL_WEIGHT = self.config.get("signal_weights", {}).get("technical", 0.6)
        AI_WEIGHT = self.config.get("signal_weights", {}).get("ai", 0.4)
        SIGNAL_THRESHOLD = self.config.get("signal_score_threshold", 2.0)
        LOW_AI_CONFIDENCE_THRESHOLD = self.config.get(
            "low_ai_confidence_threshold", 20
        )  # For overriding conflict

        ai_score_component = 0.0
        ai_confidence = ai_analysis.get("confidence", 0) / 100.0

        if ai_analysis.get("signal") == "BUY":
            ai_score_component = ai_confidence * 5.0  # Scale to match technical range
        elif ai_analysis.get("signal") == "SELL":
            ai_score_component = -(ai_confidence * 5.0)

        combined_score = (technical_score * TECHNICAL_WEIGHT) + (
            ai_score_component * AI_WEIGHT
        )

        final_signal = "HOLD"
        if combined_score >= SIGNAL_THRESHOLD:
            final_signal = "BUY"
        elif combined_score <= -SIGNAL_THRESHOLD:
            final_signal = "SELL"

        # Special handling for strong disagreements or very low AI confidence
        if ai_confidence * 100 < LOW_AI_CONFIDENCE_THRESHOLD:
            self.logger.debug(
                f"AI confidence very low ({ai_confidence * 100:.0f}% < {LOW_AI_CONFIDENCE_THRESHOLD}%). Technical signal will dominate."
            )
            if technical_score >= SIGNAL_THRESHOLD:
                final_signal = "BUY"
            elif technical_score <= -SIGNAL_THRESHOLD:
                final_signal = "SELL"
            else:
                final_signal = "HOLD"
            combined_score = (
                technical_score  # Revert to technical score or a heavy lean
            )

        elif (
            technical_signal == "BUY"
            and ai_analysis.get("signal") == "SELL"
            and ai_confidence > 0.5
        ) or (
            technical_signal == "SELL"
            and ai_analysis.get("signal") == "BUY"
            and ai_confidence > 0.5
        ):
            self.logger.warning(
                "Strong signal conflict detected between Technical and AI (moderate/high AI confidence). Defaulting to HOLD."
            )
            final_signal = "HOLD"
            combined_score = 0.0  # Neutralize score on conflict

        return final_signal, combined_score

    def _log_signal_details(self, signal_details: dict[str, Any]) -> None:
        """Log detailed signal information."""
        self.logger.info(f"{NEON_PURPLE}=== GEMINI AI SIGNAL ANALYSIS ==={RESET}")
        self.logger.info(
            f"{NEON_CYAN}Final Signal: {signal_details['final_signal']} (Score: {signal_details['final_score']:.2f}){RESET}"
        )
        self.logger.info(
            f"Technical: {signal_details['technical_signal']} ({signal_details['technical_score']:.2f}){RESET}"
        )
        self.logger.info(
            f"AI: {signal_details['ai_signal']} (Confidence: {signal_details['ai_confidence']}%){RESET}"
        )
        self.logger.info(f"Risk Level: {signal_details['risk_level']}{RESET}")
        self.logger.info(
            f"Market Sentiment: {signal_details['market_sentiment']}{RESET}"
        )
        if (
            signal_details.get("pattern_detected")
            and signal_details["pattern_detected"] != "None"
        ):
            self.logger.info(
                f"{NEON_YELLOW}Pattern Detected: {signal_details['pattern_detected']}{RESET}"
            )
        if signal_details["key_factors"]:
            self.logger.info(
                f"{NEON_YELLOW}Key Factors: {', '.join(signal_details['key_factors'][:3])}{RESET}"
            )
        if signal_details.get("suggested_levels"):
            levels = signal_details["suggested_levels"]
            if levels.get("entry") is not None:
                self.logger.info(
                    f"  {NEON_GREEN}Suggested Entry: {levels['entry']:.2f}{RESET}"
                )
            if levels.get("stop_loss") is not None:
                self.logger.info(
                    f"  {NEON_RED}Suggested SL: {levels['stop_loss']:.2f}{RESET}"
                )
            if levels.get("take_profit") is not None:
                self.logger.info(
                    f"  {NEON_GREEN}Suggested TP: {levels['take_profit']:.2f}{RESET}"
                )
        self.logger.info(f"{NEON_PURPLE}----------------------------------{RESET}")

    def track_signal_performance(self, signal: str, actual_outcome: str | None = None):
        """Track AI signal performance. 'actual_outcome' should be 'WIN', 'LOSS', 'BREAKEVEN'."""
        if signal not in self.performance_metrics["signal_accuracy"]:
            self.performance_metrics["signal_accuracy"][signal] = {
                "WIN": 0,
                "LOSS": 0,
                "BREAKEVEN": 0,
                "total": 0,
            }

        self.performance_metrics["signal_accuracy"][signal]["total"] += 1
        if actual_outcome:
            if actual_outcome in self.performance_metrics["signal_accuracy"][signal]:
                self.performance_metrics["signal_accuracy"][signal][actual_outcome] += 1
            else:
                self.performance_metrics["signal_accuracy"][signal]["total"] -= (
                    1  # Don't count unknown outcomes
                )
                self.logger.warning(
                    f"Unknown actual_outcome '{actual_outcome}' for signal performance tracking."
                )

    def calculate_position_sizing(
        self,
        ai_analysis: dict[str, Any],
        account_balance: Decimal,
        risk_per_trade_percent: Decimal,  # From bot config
        min_stop_loss_distance: Decimal,  # To prevent division by zero or too small stops
    ) -> dict[str, Decimal] | None:
        """Calculate optimal position size based on AI risk assessment and suggested levels."""
        risk_multipliers = {
            "LOW": Decimal("1.0"),
            "MEDIUM": Decimal("0.7"),
            "HIGH": Decimal("0.4"),
        }

        risk_level = ai_analysis.get("risk_level", "MEDIUM").upper()
        confidence = Decimal(str(ai_analysis.get("confidence", 50))) / 100

        # Adjust risk based on AI confidence and risk assessment
        adjusted_risk_ratio = (
            risk_per_trade_percent
            * risk_multipliers.get(risk_level, Decimal("0.7"))
            * confidence
        )

        suggested_entry = ai_analysis.get("suggested_levels", {}).get("entry")
        suggested_stop_loss = ai_analysis.get("suggested_levels", {}).get("stop_loss")

        if suggested_entry is None or suggested_stop_loss is None:
            self.logger.debug(
                "AI did not provide suggested entry or stop-loss for position sizing."
            )
            return None

        entry = Decimal(str(suggested_entry))
        stop_loss = Decimal(str(suggested_stop_loss))

        stop_distance = abs(entry - stop_loss)
        if (
            stop_distance < min_stop_loss_distance
        ):  # Prevent tiny or zero stop loss leading to huge positions
            self.logger.warning(
                f"AI suggested stop loss distance ({stop_distance:.8f}) is too small. Using default ATR-based sizing."
            )
            return None

        risk_amount = account_balance * adjusted_risk_ratio

        self.logger.debug(
            f"AI-adjusted position sizing: Risk Ratio={adjusted_risk_ratio * 100:.2f}%, Risk Amount=${risk_amount:.2f}, "
            f"Stop Distance={stop_distance:.8f}. Suggested Entry={entry:.2f}, SL={stop_loss:.2f}"
        )

        return {
            "risk_amount": risk_amount,
            "stop_distance": stop_distance,
            "suggested_entry": entry,
            "suggested_stop_loss": stop_loss,
            "suggested_take_profit": Decimal(
                str(ai_analysis.get("suggested_levels", {}).get("take_profit"))
            )
            if ai_analysis.get("suggested_levels", {}).get("take_profit")
            else None,
            "adjusted_risk_percentage": adjusted_risk_ratio * 100,
        }

    def _generate_chart_for_analysis(self, df: pd.DataFrame) -> str | None:
        """Generate a chart image (base64 encoded PNG) for Gemini Vision analysis."""
        if df.empty or len(df) < 50:  # Need enough data to make a meaningful chart
            self.logger.warning("Not enough data to generate chart for AI Vision.")
            return None

        # Take last N candles for a clear view
        df_plot = df.tail(
            self.config.get("chart_image_data_points", 100)
        )  # Default 100 candles for chart

        # Basic plot: Price, Volume, RSI
        fig, axes = plt.subplots(
            3, 1, figsize=(12, 8), sharex=True, gridspec_kw={"height_ratios": [3, 1, 1]}
        )
        ax1, ax2, ax3 = axes

        # Price
        ax1.plot(df_plot.index, df_plot["close"], label="Close Price", color="blue")
        # Add a couple of EMAs for context if available
        if "EMA_Short" in df_plot.columns and not df_plot["EMA_Short"].isnull().all():
            ax1.plot(
                df_plot.index,
                df_plot["EMA_Short"],
                label="EMA Short",
                color="orange",
                alpha=0.7,
            )
        if "EMA_Long" in df_plot.columns and not df_plot["EMA_Long"].isnull().all():
            ax1.plot(
                df_plot.index,
                df_plot["EMA_Long"],
                label="EMA Long",
                color="purple",
                alpha=0.7,
            )

        ax1.set_ylabel("Price")
        ax1.legend(loc="upper left")
        ax1.grid(True, linestyle="--", alpha=0.6)
        ax1.set_title(
            f"{self.config.get('symbol', 'N/A')} {self.config.get('interval', 'N/A')} Chart for AI Analysis"
        )

        # Volume
        ax2.bar(df_plot.index, df_plot["volume"], color="gray", alpha=0.7)
        ax2.set_ylabel("Volume")
        ax2.grid(True, linestyle="--", alpha=0.6)

        # RSI
        if "RSI" in df_plot.columns and not df_plot["RSI"].isnull().all():
            ax3.plot(df_plot.index, df_plot["RSI"], color="green")
            ax3.axhline(
                y=70, color="red", linestyle="--", alpha=0.5, label="Overbought (70)"
            )
            ax3.axhline(
                y=30, color="green", linestyle="--", alpha=0.5, label="Oversold (30)"
            )
            ax3.set_ylabel("RSI")
            ax3.set_ylim(0, 100)
            ax3.grid(True, linestyle="--", alpha=0.6)
            ax3.legend(loc="upper left")

        plt.xlabel("Time")
        plt.tight_layout()

        # Convert plot to base64 image
        buffer = io.BytesIO()
        plt.savefig(buffer, format="png", bbox_inches="tight", pad_inches=0.1)
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode("utf-8")
        plt.close(fig)  # Close the figure to free memory

        self.logger.debug("Chart image generated successfully for AI Vision.")
        return image_base64

    def analyze_chart_image(self, df: pd.DataFrame, timeframe: str) -> dict[str, Any]:
        """Analyze a chart image using Gemini's multimodal capabilities (Vision model)."""
        if not self._check_api_limits():
            self.performance_metrics["api_errors"] += 1
            return {"analysis": "API daily limit reached.", "status": "error"}

        base64_image = self._generate_chart_for_analysis(df)
        if not base64_image:
            return {"analysis": "Failed to generate chart image.", "status": "error"}

        start_time = time.perf_counter()
        result = {}
        try:
            image_part = Part.from_data(
                data=base64.b64decode(base64_image), mime_type="image/png"
            )

            prompt_parts = [
                f"Analyze this {timeframe} cryptocurrency chart and provide:",
                "1. Identified chart patterns (e.g., Head and Shoulders, Triangles, Flags, Double Top/Bottom).",
                "2. Key visual support and resistance levels.",
                "3. Trend analysis (strong, weak, sideways, reversal potential).",
                "4. Volume analysis in relation to price action.",
                "5. Overall trading recommendation based on visual analysis.",
                "Provide the response as a clear, structured text summary.",
                image_part,
            ]

            response = self.client.generate_content(
                prompt_parts,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.4,
                    response_mime_type="text/plain",  # Request plain text for image analysis
                ),
            )

            if response.candidates and response.candidates[0].content.parts:
                result = {
                    "analysis": response.candidates[0].content.parts[0].text,
                    "status": "success",
                }
                self.logger.info("Gemini Vision analysis successful.")
            else:
                self.logger.warning(
                    "Gemini Vision analysis returned no content or candidates."
                )
                result = {
                    "analysis": "No content from AI.",
                    "status": "error",
                    "error": "No content",
                }
            self.performance_metrics["successful_analyses"] += 1

        except Exception as e:
            self.logger.error(f"Error analyzing chart image with Gemini Vision: {e}")
            result = {"analysis": f"Vision analysis failed: {e}", "status": "error"}
            self.performance_metrics["api_errors"] += 1
        finally:
            end_time = time.perf_counter()
            response_time_ms = (end_time - start_time) * 1000
            self.performance_metrics["avg_response_time_ms"] = (
                (
                    (
                        self.performance_metrics["avg_response_time_ms"]
                        * (
                            self.performance_metrics["total_analyses"]
                            - self.performance_metrics["cache_hits"]
                        )
                    )
                    + response_time_ms
                )
                / (
                    self.performance_metrics["total_analyses"]
                    - self.performance_metrics["cache_hits"]
                    + 1e-9
                )
                if (
                    self.performance_metrics["total_analyses"]
                    - self.performance_metrics["cache_hits"]
                )
                > 0
                else response_time_ms
            )

            self.performance_metrics["total_analyses"] += 1

        return result


def load_config(filepath: str, logger: logging.Logger) -> dict[str, Any]:
    """Load configuration from JSON file, creating a default if not found."""
    default_config = {
        # Core Settings
        "symbol": "BTCUSDT",
        "interval": "15m",
        "loop_delay": LOOP_DELAY_SECONDS,
        "orderbook_limit": 50,
        # Signal Generation
        "signal_score_threshold": 2.0,
        "volume_confirmation_multiplier": 1.5,
        # Position & Risk Management
        "trade_management": {
            "enabled": True,
            "account_balance": 1000.0,
            "risk_per_trade_percent": 1.0,
            "stop_loss_atr_multiple": 1.5,
            "take_profit_atr_multiple": 2.0,
            "max_open_positions": 1,
            "min_stop_loss_distance_ratio": 0.001,  # 0.1% of price, to prevent too small SL
        },
        # Multi-Timeframe Analysis
        "mtf_analysis": {
            "enabled": True,
            "higher_timeframes": ["1h", "4h"],
            "trend_indicators": ["ema", "ehlers_supertrend"],
            "trend_period": 50,
            "mtf_request_delay_seconds": 0.5,
        },
        # Machine Learning Enhancement (Explicitly disabled)
        "ml_enhancement": {
            "enabled": False,  # ML explicitly disabled
            "model_path": "ml_model.pkl",
            "retrain_on_startup": False,
            "training_data_limit": 5000,
            "prediction_lookahead": 12,
            "profit_target_percent": 0.5,
            "feature_lags": [1, 2, 3, 5],
            "cross_validation_folds": 5,
        },
        # Gemini AI Configuration
        "gemini_ai": {
            "enabled": True,
            "api_key_env": "GEMINI_API_KEY",
            "model": "gemini-1.5-flash-latest",
            "min_confidence_for_override": 60,  # Minimum AI confidence (0-100) to consider its signal for override
            "rate_limit_delay_seconds": 1.0,
            "cache_ttl_seconds": 300,  # Cache duration for AI analysis
            "daily_api_limit": 1000,  # Max calls per 24 hours
            "signal_weights": {  # Weights for combining technical and AI scores
                "technical": 0.6,
                "ai": 0.4,
            },
            "low_ai_confidence_threshold": 20,  # If AI confidence below this, technical signal dominates
            "chart_image_analysis": {
                "enabled": False,  # Set to True to enable chart image analysis with Gemini Vision (requires matplotlib)
                "frequency_loops": 0,  # Analyze chart image every N loops (0 to disable)
                "data_points_for_chart": 100,  # Number of candles to plot for vision analysis
            },
        },
        # Indicator Periods & Thresholds
        "indicator_settings": {
            "atr_period": 14,
            "ema_short_period": 9,
            "ema_long_period": 21,
            "rsi_period": 14,
            "stoch_rsi_period": 14,
            "stoch_k_period": 3,
            "stoch_d_period": 3,
            "bollinger_bands_period": 20,
            "bollinger_bands_std_dev": 2.0,
            "cci_period": 20,
            "williams_r_period": 14,
            "mfi_period": 14,
            "psar_acceleration": 0.02,
            "psar_max_acceleration": 0.2,
            "sma_short_period": 10,
            "sma_long_period": 50,
            "fibonacci_window": 60,
            "ehlers_fast_period": 10,
            "ehlers_fast_multiplier": 2.0,
            "ehlers_slow_period": 20,
            "ehlers_slow_multiplier": 3.0,
            "macd_fast_period": 12,
            "macd_slow_period": 26,
            "macd_signal_period": 9,
            "adx_period": 14,
            "ichimoku_tenkan_period": 9,
            "ichimoku_kijun_period": 26,
            "ichimoku_senkou_span_b_period": 52,
            "ichimoku_chikou_span_offset": 26,
            "obv_ema_period": 20,  # For OBV EMA signal line
            "cmf_period": 20,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "stoch_rsi_oversold": 20,
            "stoch_rsi_overbought": 80,
            "cci_oversold": -100,
            "cci_overbought": 100,
            "williams_r_oversold": -80,
            "williams_r_overbought": -20,
            "mfi_oversold": 20,
            "mfi_overbought": 80,
        },
        # Active Indicators & Weights
        "indicators": {
            "ema_alignment": True,
            "sma_trend_filter": True,
            "momentum": True,
            "volume_confirmation": True,
            "stoch_rsi": True,
            "rsi": True,
            "bollinger_bands": True,
            "vwap": True,
            "cci": True,
            "wr": True,
            "psar": True,
            "sma_10": True,
            "mfi": True,
            "orderbook_imbalance": True,
            "fibonacci_levels": True,
            "ehlers_supertrend": True,
            "macd": True,
            "adx": True,
            "ichimoku_cloud": True,
            "obv": True,
            "cmf": True,
        },
        "weight_sets": {
            "default_scalping": {
                "ema_alignment": 0.22,
                "sma_trend_filter": 0.28,
                "momentum": 0.18,
                "volume_confirmation": 0.12,
                "stoch_rsi": 0.30,
                "rsi": 0.12,
                "bollinger_bands": 0.22,
                "vwap": 0.22,
                "cci": 0.08,
                "wr": 0.08,
                "psar": 0.22,
                "sma_10": 0.07,
                "mfi": 0.12,
                "orderbook_imbalance": 0.07,
                "ehlers_supertrend_alignment": 0.55,
                "macd_alignment": 0.28,
                "adx_strength": 0.18,
                "ichimoku_confluence": 0.38,
                "obv_momentum": 0.18,
                "cmf_flow": 0.12,
                "mtf_trend_confluence": 0.32,
            }
        },
    }
    if not Path(filepath).exists():
        try:
            with Path(filepath).open("w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)
            logger.warning(
                f"{NEON_YELLOW}Configuration file not found. Created default config at {filepath}{RESET}"
            )
            return default_config
        except OSError as e:
            logger.error(f"{NEON_RED}Error creating default config file: {e}{RESET}")
            return default_config

    try:
        with Path(filepath).open(encoding="utf-8") as f:
            config = json.load(f)
        _ensure_config_keys(config, default_config)
        with Path(filepath).open("w", encoding="utf-8") as f_write:
            json.dump(config, f_write, indent=4)
        return config
    except (OSError, FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(
            f"{NEON_RED}Error loading config: {e}. Using default and attempting to save.{RESET}"
        )
        try:
            with Path(filepath).open("w", encoding="utf-8") as f_default:
                json.dump(default_config, f_default, indent=4)
        except OSError as e_save:
            logger.error(f"{NEON_RED}Could not save default config: {e_save}{RESET}")
        return default_config


def _ensure_config_keys(config: dict[str, Any], default_config: dict[str, Any]) -> None:
    """Recursively ensure all keys from default_config are in config."""
    for key, default_value in default_config.items():
        if key not in config:
            config[key] = default_value
        elif isinstance(default_value, dict) and isinstance(config.get(key), dict):
            _ensure_config_keys(config[key], default_value)


class SensitiveFormatter(logging.Formatter):
    """Formatter that redacts API keys from log records."""

    SENSITIVE_WORDS: ClassVar[list[str]] = [
        "API_KEY",
        "API_SECRET",
        "GEMINI_API_KEY",
    ]  # Added GEMINI_API_KEY

    def __init__(self, fmt=None, datefmt=None, style="%"):
        """Initializes the SensitiveFormatter."""
        super().__init__(fmt, datefmt, style)
        self._fmt = fmt if fmt else self.default_fmt()

    def default_fmt(self):
        """Returns the default log format string."""
        return "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    def format(self, record):
        """Formats the log record, redacting sensitive words."""
        original_message = super().format(record)
        redacted_message = original_message
        for word in self.SENSITIVE_WORDS:
            # Simple replacement, can be made more robust for different cases
            redacted_message = redacted_message.replace(word, "*" * len(word))
            redacted_message = redacted_message.replace(
                os.getenv(word, "NO_KEY_FOUND"),
                "*" * len(os.getenv(word, "NO_KEY_FOUND")),
            )  # Redact actual key if present
        return redacted_message


def setup_logger(log_name: str, level=logging.INFO) -> logging.Logger:
    """Configure and return a logger with file and console handlers."""
    logger = logging.getLogger(log_name)
    logger.setLevel(level)
    logger.propagate = False

    # Ensure handlers are not duplicated
    if not logger.handlers:
        # Console Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(
            SensitiveFormatter(
                f"{NEON_BLUE}%(asctime)s - %(levelname)s - %(message)s{RESET}"
            )
        )
        logger.addHandler(console_handler)

        # File Handler
        log_file = Path(LOG_DIRECTORY) / f"{log_name}.log"
        file_handler = RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5
        )
        file_handler.setFormatter(
            SensitiveFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(file_handler)

    return logger


def create_session() -> requests.Session:
    """Create a requests session with retry logic."""
    session = requests.Session()
    retries = Retry(
        total=MAX_API_RETRIES,
        backoff_factor=RETRY_DELAY_SECONDS,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET", "POST"]),
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session


def generate_signature(payload: str, api_secret: str) -> str:
    """Generate a Bybit API signature."""
    return hmac.new(api_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def bybit_request(
    method: str,
    endpoint: str,
    params: dict | None = None,
    signed: bool = False,
    logger: logging.Logger | None = None,
) -> dict | None:
    """Send a request to the Bybit API."""
    if logger is None:
        logger = setup_logger("bybit_api")
    session = create_session()
    url = f"{BASE_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}

    if signed:
        if not API_KEY or not API_SECRET:
            logger.error(
                f"{NEON_RED}API_KEY or API_SECRET not set for signed request.{RESET}"
            )
            return None

        timestamp = str(int(time.time() * 1000))
        if method == "GET":
            query_string = urllib.parse.urlencode(params) if params else ""
            recv_window = "20000"
            param_str = timestamp + API_KEY + recv_window + query_string
            signature = generate_signature(param_str, API_SECRET)
            headers.update(
                {
                    "X-BAPI-API-KEY": API_KEY,
                    "X-BAPI-TIMESTAMP": timestamp,
                    "X-BAPI-SIGN": signature,
                    "X-BAPI-RECV-WINDOW": recv_window,
                }
            )
            logger.debug(f"GET Request: {url}?{query_string}")
            response = session.get(
                url, params=params, headers=headers, timeout=REQUEST_TIMEOUT
            )
        else:  # POST
            json_params = json.dumps(params) if params else ""
            recv_window = "20000"
            param_str = timestamp + API_KEY + recv_window + json_params
            signature = generate_signature(param_str, API_SECRET)
            headers.update(
                {
                    "X-BAPI-API-KEY": API_KEY,
                    "X-BAPI-TIMESTAMP": timestamp,
                    "X-BAPI-SIGN": signature,
                    "X-BAPI-RECV-WINDOW": recv_window,
                }
            )
            logger.debug(f"POST Request: {url} with payload {json_params}")
            response = session.post(
                url, json=params, headers=headers, timeout=REQUEST_TIMEOUT
            )
    else:
        logger.debug(f"Public Request: {url} with params {params}")
        response = session.get(
            url, params=params, headers=headers, timeout=REQUEST_TIMEOUT
        )

    try:
        response.raise_for_status()
        data = response.json()
        if data.get("retCode") != 0:
            logger.error(
                f"{NEON_RED}Bybit API Error: {data.get('retMsg')} (Code: {data.get('retCode')}){RESET}"
            )
            return None
        return data
    except requests.exceptions.HTTPError as e:
        logger.error(
            f"{NEON_RED}HTTP Error: {e.response.status_code} - {e.response.text}{RESET}"
        )
    except requests.exceptions.ConnectionError as e:
        logger.error(f"{NEON_RED}Connection Error: {e}{RESET}")
    except requests.exceptions.Timeout:
        logger.error(
            f"{NEON_RED}Request timed out after {REQUEST_TIMEOUT} seconds.{RESET}"
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"{NEON_RED}Request Exception: {e}{RESET}")
    except json.JSONDecodeError:
        logger.error(
            f"{NEON_RED}Failed to decode JSON response: {response.text}{RESET}"
        )
    return None


def fetch_current_price(symbol: str, logger: logging.Logger) -> Decimal | None:
    """Fetch the current market price for a symbol."""
    endpoint = "/v5/market/tickers"
    params = {"category": "linear", "symbol": symbol}
    response = bybit_request("GET", endpoint, params, logger=logger)
    if response and response["result"] and response["result"]["list"]:
        price = Decimal(response["result"]["list"][0]["lastPrice"])
        logger.debug(f"Fetched current price for {symbol}: {price}")
        return price
    logger.warning(f"{NEON_YELLOW}Could not fetch current price for {symbol}.{RESET}")
    return None


def fetch_klines(
    symbol: str, interval: str, limit: int, logger: logging.Logger
) -> pd.DataFrame | None:
    """Fetch kline data for a symbol and interval."""
    endpoint = "/v5/market/kline"
    params = {
        "category": "linear",
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }
    response = bybit_request("GET", endpoint, params, logger=logger)
    if response and response["result"] and response["result"]["list"]:
        df = pd.DataFrame(
            response["result"]["list"],
            columns=[
                "start_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "turnover",
            ],
        )
        df["start_time"] = pd.to_datetime(
            df["start_time"].astype(int), unit="ms", utc=True
        ).dt.tz_convert(TIMEZONE)
        for col in ["open", "high", "low", "close", "volume", "turnover"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df.set_index("start_time", inplace=True)
        df.sort_index(inplace=True)

        if df.empty:
            logger.warning(
                f"{NEON_YELLOW}Fetched klines for {symbol} {interval} but DataFrame is empty after processing. Raw response: {response}{RESET}"
            )
            return None

        logger.debug(f"Fetched {len(df)} {interval} klines for {symbol}.")
        return df
    logger.warning(
        f"{NEON_YELLOW}Could not fetch klines for {symbol} {interval}. API response might be empty or invalid. Raw response: {response}{RESET}"
    )
    return None


def fetch_orderbook(symbol: str, limit: int, logger: logging.Logger) -> dict | None:
    """Fetch orderbook data for a symbol."""
    endpoint = "/v5/market/orderbook"
    params = {"category": "linear", "symbol": symbol, "limit": limit}
    response = bybit_request("GET", endpoint, params, logger=logger)
    if response and response["result"]:
        logger.debug(f"Fetched orderbook for {symbol} with limit {limit}.")
        return response["result"]
    logger.warning(f"{NEON_YELLOW}Could not fetch orderbook for {symbol}.{RESET}")
    return None


class PositionManager:
    """Manages open positions, stop-loss, and take-profit levels."""

    def __init__(self, config: dict[str, Any], logger: logging.Logger, symbol: str):
        """Initializes the PositionManager."""
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.open_positions: list[dict] = []  # Stores active positions
        self.trade_management_enabled = config["trade_management"]["enabled"]
        self.max_open_positions = config["trade_management"]["max_open_positions"]
        self.min_stop_loss_distance_ratio = Decimal(
            str(config["trade_management"]["min_stop_loss_distance_ratio"])
        )

    def _get_current_balance(self) -> Decimal:
        """Fetch current account balance (simplified for simulation)."""
        # In a real bot, this would query the exchange.
        # For simulation, use configured account balance.
        return Decimal(str(self.config["trade_management"]["account_balance"]))

    def _calculate_order_size(
        self,
        current_price: Decimal,
        atr_value: Decimal,
        signal: str,
        ai_position_sizing_info: dict[str, Decimal] | None = None,
    ) -> Decimal:
        """Calculate order size based on risk per trade and ATR, or AI suggestions."""
        if not self.trade_management_enabled:
            return Decimal("0")

        account_balance = self._get_current_balance()
        risk_per_trade_percent = (
            Decimal(str(self.config["trade_management"]["risk_per_trade_percent"]))
            / 100
        )
        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"])
        )

        risk_amount = account_balance * risk_per_trade_percent
        stop_loss_distance = Decimal("0")

        # Use AI-suggested stop-loss distance if provided and valid
        if ai_position_sizing_info:
            ai_stop_distance = ai_position_sizing_info.get("stop_distance")
            ai_risk_amount = ai_position_sizing_info.get("risk_amount")
            if ai_stop_distance and ai_risk_amount and ai_stop_distance > Decimal("0"):
                # Use AI calculated risk amount and stop distance directly if available
                risk_amount = ai_risk_amount
                stop_loss_distance = ai_stop_distance
                self.logger.debug("Using AI-suggested stop distance and risk amount.")
            else:
                self.logger.warning(
                    "AI position sizing info invalid, falling back to ATR-based calculation."
                )

        if (
            stop_loss_distance <= 0
        ):  # Fallback to ATR if AI didn't provide or was invalid
            stop_loss_distance = atr_value * stop_loss_atr_multiple
            self.logger.debug(
                f"Using ATR-based stop distance: {stop_loss_distance:.8f}"
            )

        # Ensure stop loss distance is not too small relative to price
        min_abs_stop_distance = current_price * self.min_stop_loss_distance_ratio
        if stop_loss_distance < min_abs_stop_distance:
            stop_loss_distance = min_abs_stop_distance
            self.logger.warning(
                f"{NEON_YELLOW}Calculated stop loss distance ({stop_loss_distance:.8f}) is too small. "
                f"Adjusted to minimum ({min_abs_stop_distance:.8f}).{RESET}"
            )

        if stop_loss_distance <= 0:
            self.logger.warning(
                f"{NEON_YELLOW}Final stop loss distance is zero or negative. Cannot determine order size.{RESET}"
            )
            return Decimal("0")

        order_value = risk_amount / stop_loss_distance
        order_qty = order_value / current_price

        # Round order_qty to appropriate precision for the symbol (e.g., BTCUSDT might be 0.0001)
        # This requires knowing the symbol's lot size filter, which is exchange-specific.
        # For simulation, we'll use a generic rounding.
        order_qty = order_qty.quantize(
            Decimal("0.0001"), rounding=ROUND_DOWN
        )  # Example precision

        self.logger.info(
            f"Calculated order size: {order_qty} {self.symbol} (Risk: {risk_amount:.2f} USD)"
        )
        return order_qty

    def open_position(
        self,
        signal: str,
        current_price: Decimal,
        atr_value: Decimal,
        ai_suggested_levels: dict[str, Decimal] | None = None,
    ) -> dict | None:
        """Open a new position if conditions allow.

        Returns the new position details or None.
        """
        if not self.trade_management_enabled:
            self.logger.info(
                f"{NEON_YELLOW}Trade management is disabled. Skipping opening position.{RESET}"
            )
            return None

        if len(self.open_positions) >= self.max_open_positions:
            self.logger.info(
                f"{NEON_YELLOW}Max open positions ({self.max_open_positions}) reached. Cannot open new position.{RESET}"
            )
            return None

        if signal not in ["BUY", "SELL"]:
            self.logger.debug(f"Invalid signal '{signal}' for opening position.")
            return None

        # Determine order quantity (could use AI info for risk_amount and stop_distance)
        ai_position_sizing_info = None
        if ai_suggested_levels and all(
            k in ai_suggested_levels for k in ["entry", "stop_loss"]
        ):
            # This is a simplified example. In a real scenario, calculate_position_sizing
            # should provide the 'risk_amount' and 'stop_distance' directly.
            # For now, let's derive them here if AI levels are provided.
            entry = Decimal(str(ai_suggested_levels["entry"]))
            stop_loss = Decimal(str(ai_suggested_levels["stop_loss"]))
            stop_distance = abs(entry - stop_loss)

            # Re-calculate risk_amount based on bot's risk_per_trade and AI's risk_level
            account_balance = self._get_current_balance()
            risk_per_trade_percent = (
                Decimal(str(self.config["trade_management"]["risk_per_trade_percent"]))
                / 100
            )
            risk_amount = (
                account_balance * risk_per_trade_percent
            )  # Start with bot's base risk

            # If AI had a specific adjusted_risk_percentage, use that for risk_amount
            if "adjusted_risk_percentage" in ai_suggested_levels:
                risk_amount = account_balance * (
                    ai_suggested_levels["adjusted_risk_percentage"] / 100
                )

            if stop_distance > Decimal("0"):
                ai_position_sizing_info = {
                    "risk_amount": risk_amount,
                    "stop_distance": stop_distance,
                }

        order_qty = self._calculate_order_size(
            current_price, atr_value, signal, ai_position_sizing_info
        )

        if order_qty <= 0:
            self.logger.warning(
                f"{NEON_YELLOW}Order quantity is zero or negative. Cannot open position.{RESET}"
            )
            return None

        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"])
        )
        take_profit_atr_multiple = Decimal(
            str(self.config["trade_management"]["take_profit_atr_multiple"])
        )

        stop_loss = Decimal("0")
        take_profit = Decimal("0")

        # Use AI suggested levels if provided and valid
        if ai_suggested_levels:
            suggested_entry = ai_suggested_levels.get("entry")
            suggested_sl = ai_suggested_levels.get("stop_loss")
            suggested_tp = ai_suggested_levels.get("take_profit")

            if suggested_sl is not None:
                stop_loss = Decimal(str(suggested_sl))
            if suggested_tp is not None:
                take_profit = Decimal(str(suggested_tp))
            if suggested_entry is not None:
                # If AI provides entry, it might be different from current_price.
                # For this simple bot, we'll still use current_price as the actual entry.
                # A more advanced bot would try to place a limit order at suggested_entry.
                self.logger.debug(
                    f"AI suggested entry: {suggested_entry}. Using current market price {current_price} as actual entry."
                )

        # If AI didn't provide or invalid, fallback to ATR calculation
        if stop_loss == Decimal("0") or take_profit == Decimal("0"):
            if signal == "BUY":
                stop_loss = current_price - (atr_value * stop_loss_atr_multiple)
                take_profit = current_price + (atr_value * take_profit_atr_multiple)
            else:  # SELL
                stop_loss = current_price + (atr_value * stop_loss_atr_multiple)
                take_profit = current_price - (atr_value * take_profit_atr_multiple)

        position = {
            "entry_time": datetime.now(TIMEZONE),
            "symbol": self.symbol,
            "side": signal,
            "entry_price": current_price,
            "qty": order_qty,
            "stop_loss": stop_loss.quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "take_profit": take_profit.quantize(
                Decimal("0.00001"), rounding=ROUND_DOWN
            ),
            "status": "OPEN",
        }
        self.open_positions.append(position)
        self.logger.info(f"{NEON_GREEN}Opened {signal} position: {position}{RESET}")
        return position

    def manage_positions(
        self,
        current_price: Decimal,
        performance_tracker: Any,
        gemini_analyzer: Any | None = None,
    ) -> None:
        """Check and manage all open positions (SL/TP).

        In a real bot, this would interact with exchange orders.
        """
        if not self.trade_management_enabled or not self.open_positions:
            return

        positions_to_close = []
        for i, position in enumerate(self.open_positions):
            if position["status"] == "OPEN":
                side = position["side"]
                entry_price = position["entry_price"]
                stop_loss = position["stop_loss"]
                take_profit = position["take_profit"]
                qty = position["qty"]

                closed_by = ""
                close_price = Decimal("0")

                if side == "BUY":
                    if current_price <= stop_loss:
                        closed_by = "STOP_LOSS"
                        close_price = current_price
                    elif current_price >= take_profit:
                        closed_by = "TAKE_PROFIT"
                        close_price = current_price
                elif side == "SELL":  # Corrected logic for SELL
                    if (
                        current_price >= stop_loss
                    ):  # Price went up, hit stop loss for short
                        closed_by = "STOP_LOSS"
                        close_price = current_price
                    elif (
                        current_price <= take_profit
                    ):  # Price went down, hit take profit for short
                        closed_by = "TAKE_PROFIT"
                        close_price = current_price

                if closed_by:
                    position["status"] = "CLOSED"
                    position["exit_time"] = datetime.now(TIMEZONE)
                    position["exit_price"] = close_price
                    position["closed_by"] = closed_by
                    positions_to_close.append(i)

                    pnl = (
                        (close_price - entry_price) * qty
                        if side == "BUY"
                        else (entry_price - close_price) * qty
                    )
                    performance_tracker.record_trade(position, pnl)

                    log_color = NEON_GREEN if pnl >= 0 else NEON_RED
                    self.logger.info(
                        f"{NEON_PURPLE}Closed {side} position by {closed_by}: {position}. {log_color}PnL: {pnl:.2f}{RESET}"
                    )

                    # Track AI performance for the closed trade
                    if gemini_analyzer and position.get(
                        "ai_signal"
                    ):  # Assuming 'ai_signal' was stored at open
                        actual_outcome = (
                            "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "BREAKEVEN")
                        )
                        gemini_analyzer.track_signal_performance(
                            position["ai_signal"], actual_outcome
                        )

        # Remove closed positions
        self.open_positions = [
            pos
            for i, pos in enumerate(self.open_positions)
            if i not in positions_to_close
        ]

    def get_open_positions(self) -> list[dict]:
        """Return a list of currently open positions."""
        return [pos for pos in self.open_positions if pos["status"] == "OPEN"]


class PerformanceTracker:
    """Tracks and reports trading performance."""

    def __init__(self, logger: logging.Logger):
        """Initializes the PerformanceTracker."""
        self.logger = logger
        self.trades: list[dict] = []
        self.total_pnl = Decimal("0")
        self.wins = 0
        self.losses = 0

    def record_trade(self, position: dict, pnl: Decimal) -> None:
        """Record a completed trade."""
        trade_record = {
            "entry_time": position["entry_time"],
            "exit_time": position["exit_time"],
            "symbol": position["symbol"],
            "side": position["side"],
            "entry_price": position["entry_price"],
            "exit_price": position["exit_price"],
            "qty": position["qty"],
            "pnl": pnl,
            "closed_by": position["closed_by"],
            # Optionally record AI signal that led to this trade
            "ai_signal_at_entry": position.get("ai_signal"),
        }
        self.trades.append(trade_record)
        self.total_pnl += pnl
        if pnl > 0:
            self.wins += 1
        else:
            self.losses += 1
        self.logger.info(
            f"{NEON_CYAN}Trade recorded. Current Total PnL: {self.total_pnl:.2f}, Wins: {self.wins}, Losses: {self.losses}{RESET}"
        )

    def get_summary(self) -> dict:
        """Return a summary of all recorded trades."""
        total_trades = len(self.trades)
        win_rate = (self.wins / total_trades) * 100 if total_trades > 0 else 0

        return {
            "total_trades": total_trades,
            "total_pnl": self.total_pnl,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": f"{win_rate:.2f}%",
        }


class AlertSystem:
    """Handles sending alerts for critical events."""

    def __init__(self, logger: logging.Logger):
        """Initializes the AlertSystem."""
        self.logger = logger

    def send_alert(self, message: str, level: str = "INFO") -> None:
        """Send an alert (currently logs it)."""
        if level == "INFO":
            self.logger.info(f"{NEON_BLUE}ALERT: {message}{RESET}")
        elif level == "WARNING":
            self.logger.warning(f"{NEON_YELLOW}ALERT: {message}{RESET}")
        elif level == "ERROR":
            self.logger.error(f"{NEON_RED}ALERT: {message}{RESET}")


class TradingAnalyzer:
    """Analyzes trading data and generates signals with MTF and Ehlers SuperTrend."""

    def __init__(
        self,
        df: pd.DataFrame,
        config: dict[str, Any],
        logger: logging.Logger,
        symbol: str,
    ):
        """Initializes the TradingAnalyzer."""
        self.df = df.copy()
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.indicator_values: dict[str, float | str | Decimal] = {}
        self.fib_levels: dict[str, Decimal] = {}
        self.weights = config["weight_sets"]["default_scalping"]
        self.indicator_settings = config["indicator_settings"]

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}TradingAnalyzer initialized with an empty DataFrame. Indicators will not be calculated.{RESET}"
            )
            return

        self._calculate_all_indicators()
        if self.config["indicators"].get("fibonacci_levels", False):
            self.calculate_fibonacci_levels()

    def _safe_calculate(
        self, func: callable, name: str, min_data_points: int = 0, *args, **kwargs
    ) -> Any | None:
        """Safely calculate indicators and log errors, with min_data_points check."""
        if len(self.df) < min_data_points:
            self.logger.debug(
                f"Skipping indicator '{name}': Not enough data. Need {min_data_points}, have {len(self.df)}."
            )
            return None
        try:
            result = func(*args, **kwargs)
            if (
                result is None
                or (isinstance(result, pd.Series) and result.empty)
                or (
                    isinstance(result, tuple)
                    and all(
                        r is None or (isinstance(r, pd.Series) and r.empty)
                        for r in result
                    )
                )
            ):
                self.logger.warning(
                    f"{NEON_YELLOW}Indicator '{name}' returned empty or None after calculation. Not enough valid data?{RESET}"
                )
                return None
            return result
        except Exception as e:
            self.logger.error(
                f"{NEON_RED}Error calculating indicator '{name}': {e}{RESET}"
            )
            return None

    def _calculate_all_indicators(self) -> None:
        """Calculate all enabled technical indicators, including Ehlers SuperTrend."""
        self.logger.debug("Calculating technical indicators...")
        cfg = self.config
        isd = self.indicator_settings

        # SMA
        if cfg["indicators"].get("sma_10", False):
            self.df["SMA_10"] = self._safe_calculate(
                lambda: self.df["close"].rolling(window=isd["sma_short_period"]).mean(),
                "SMA_10",
                min_data_points=isd["sma_short_period"],
            )
            if self.df["SMA_10"] is not None:
                self.indicator_values["SMA_10"] = self.df["SMA_10"].iloc[-1]
        if cfg["indicators"].get("sma_trend_filter", False):
            self.df["SMA_Long"] = self._safe_calculate(
                lambda: self.df["close"].rolling(window=isd["sma_long_period"]).mean(),
                "SMA_Long",
                min_data_points=isd["sma_long_period"],
            )
            if self.df["SMA_Long"] is not None:
                self.indicator_values["SMA_Long"] = self.df["SMA_Long"].iloc[-1]

        # EMA
        if cfg["indicators"].get("ema_alignment", False):
            self.df["EMA_Short"] = self._safe_calculate(
                lambda: self.df["close"]
                .ewm(span=isd["ema_short_period"], adjust=False)
                .mean(),
                "EMA_Short",
                min_data_points=isd["ema_short_period"],
            )
            self.df["EMA_Long"] = self._safe_calculate(
                lambda: self.df["close"]
                .ewm(span=isd["ema_long_period"], adjust=False)
                .mean(),
                "EMA_Long",
                min_data_points=isd["ema_long_period"],
            )
            if self.df["EMA_Short"] is not None:
                self.indicator_values["EMA_Short"] = self.df["EMA_Short"].iloc[-1]
            if self.df["EMA_Long"] is not None:
                self.indicator_values["EMA_Long"] = self.df["EMA_Long"].iloc[-1]

        # ATR
        self.df["TR"] = self._safe_calculate(
            self.calculate_true_range, "TR", min_data_points=2
        )
        self.df["ATR"] = self._safe_calculate(
            lambda: self.df["TR"].ewm(span=isd["atr_period"], adjust=False).mean(),
            "ATR",
            min_data_points=isd["atr_period"],
        )
        if self.df["ATR"] is not None:
            self.indicator_values["ATR"] = self.df["ATR"].iloc[-1]

        # RSI
        if cfg["indicators"].get("rsi", False):
            self.df["RSI"] = self._safe_calculate(
                self.calculate_rsi,
                "RSI",
                min_data_points=isd["rsi_period"] + 1,
                period=isd["rsi_period"],
            )
            if self.df["RSI"] is not None:
                self.indicator_values["RSI"] = self.df["RSI"].iloc[-1]

        # Stochastic RSI
        if cfg["indicators"].get("stoch_rsi", False):
            stoch_rsi_k, stoch_rsi_d = self._safe_calculate(
                self.calculate_stoch_rsi,
                "StochRSI",
                min_data_points=isd["stoch_rsi_period"]
                + isd["stoch_d_period"]
                + isd["stoch_k_period"],
                period=isd["stoch_rsi_period"],
                k_period=isd["stoch_k_period"],
                d_period=isd["stoch_d_period"],
            )
            if stoch_rsi_k is not None:
                self.df["StochRSI_K"] = stoch_rsi_k
            if stoch_rsi_d is not None:
                self.df["StochRSI_D"] = stoch_rsi_d
            if stoch_rsi_k is not None:
                self.indicator_values["StochRSI_K"] = stoch_rsi_k.iloc[-1]
            if stoch_rsi_d is not None:
                self.indicator_values["StochRSI_D"] = stoch_rsi_d.iloc[-1]

        # Bollinger Bands
        if cfg["indicators"].get("bollinger_bands", False):
            bb_upper, bb_middle, bb_lower = self._safe_calculate(
                self.calculate_bollinger_bands,
                "BollingerBands",
                min_data_points=isd["bollinger_bands_period"],
                period=isd["bollinger_bands_period"],
                std_dev=isd["bollinger_bands_std_dev"],
            )
            if bb_upper is not None:
                self.df["BB_Upper"] = bb_upper
            if bb_middle is not None:
                self.df["BB_Middle"] = bb_middle
            if bb_lower is not None:
                self.df["BB_Lower"] = bb_lower
            if bb_upper is not None:
                self.indicator_values["BB_Upper"] = bb_upper.iloc[-1]
            if bb_middle is not None:
                self.indicator_values["BB_Middle"] = bb_middle.iloc[-1]
            if bb_lower is not None:
                self.indicator_values["BB_Lower"] = bb_lower.iloc[-1]

        # CCI
        if cfg["indicators"].get("cci", False):
            self.df["CCI"] = self._safe_calculate(
                self.calculate_cci,
                "CCI",
                min_data_points=isd["cci_period"],
                period=isd["cci_period"],
            )
            if self.df["CCI"] is not None:
                self.indicator_values["CCI"] = self.df["CCI"].iloc[-1]

        if cfg["indicators"].get("wr", False):
            self.df["WR"] = self._safe_calculate(
                self.calculate_williams_r,
                "WR",
                min_data_points=isd["williams_r_period"],
                period=isd["williams_r_period"],
            )
            if self.df["WR"] is not None:
                self.indicator_values["WR"] = self.df["WR"].iloc[-1]

        # MFI
        if cfg["indicators"].get("mfi", False):
            self.df["MFI"] = self._safe_calculate(
                self.calculate_mfi,
                "MFI",
                min_data_points=isd["mfi_period"] + 1,
                period=isd["mfi_period"],
            )
            if self.df["MFI"] is not None:
                self.indicator_values["MFI"] = self.df["MFI"].iloc[-1]

        # OBV
        if cfg["indicators"].get("obv", False):
            obv_val, obv_ema = self._safe_calculate(
                self.calculate_obv,
                "OBV",
                min_data_points=isd["obv_ema_period"],
                ema_period=isd["obv_ema_period"],
            )
            if obv_val is not None:
                self.df["OBV"] = obv_val
            if obv_ema is not None:
                self.df["OBV_EMA"] = obv_ema
            if obv_val is not None:
                self.indicator_values["OBV"] = obv_val.iloc[-1]
            if obv_ema is not None:
                self.indicator_values["OBV_EMA"] = obv_ema.iloc[-1]

        # CMF
        if cfg["indicators"].get("cmf", False):
            cmf_val = self._safe_calculate(
                self.calculate_cmf,
                "CMF",
                min_data_points=isd["cmf_period"],
                period=isd["cmf_period"],
            )
            if cmf_val is not None:
                self.df["CMF"] = cmf_val
            if cmf_val is not None:
                self.indicator_values["CMF"] = cmf_val.iloc[-1]

        # Ichimoku Cloud
        if cfg["indicators"].get("ichimoku_cloud", False):
            tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span = (
                self._safe_calculate(
                    self.calculate_ichimoku_cloud,
                    "IchimokuCloud",
                    min_data_points=max(
                        isd["ichimoku_tenkan_period"],
                        isd["ichimoku_kijun_period"],
                        isd["ichimoku_senkou_span_b_period"],
                    )
                    + isd["ichimoku_chikou_span_offset"],
                    tenkan_period=isd["ichimoku_tenkan_period"],
                    kijun_period=isd["ichimoku_kijun_period"],
                    senkou_span_b_period=isd["ichimoku_senkou_span_b_period"],
                    chikou_span_offset=isd["ichimoku_chikou_span_offset"],
                )
            )
            if tenkan_sen is not None:
                self.df["Tenkan_Sen"] = tenkan_sen
            if kijun_sen is not None:
                self.df["Kijun_Sen"] = kijun_sen
            if senkou_span_a is not None:
                self.df["Senkou_Span_A"] = senkou_span_a
            if senkou_span_b is not None:
                self.df["Senkou_Span_B"] = senkou_span_b
            if chikou_span is not None:
                self.df["Chikou_Span"] = chikou_span

            if tenkan_sen is not None:
                self.indicator_values["Tenkan_Sen"] = tenkan_sen.iloc[-1]
            if kijun_sen is not None:
                self.indicator_values["Kijun_Sen"] = kijun_sen.iloc[-1]
            if senkou_span_a is not None:
                self.indicator_values["Senkou_Span_A"] = senkou_span_a.iloc[-1]
            if senkou_span_b is not None:
                self.indicator_values["Senkou_Span_B"] = senkou_span_b.iloc[-1]
            if chikou_span is not None:
                self.indicator_values["Chikou_Span"] = chikou_span.fillna(0).iloc[-1]

        # PSAR
        if cfg["indicators"].get("psar", False):
            psar_val, psar_dir = self._safe_calculate(
                self.calculate_psar,
                "PSAR",
                min_data_points=2,
                acceleration=isd["psar_acceleration"],
                max_acceleration=isd["psar_max_acceleration"],
            )
            if psar_val is not None:
                self.df["PSAR_Val"] = psar_val
            if psar_dir is not None:
                self.df["PSAR_Dir"] = psar_dir
            if psar_val is not None:
                self.indicator_values["PSAR_Val"] = psar_val.iloc[-1]
            if psar_dir is not None:
                self.indicator_values["PSAR_Dir"] = psar_dir.iloc[-1]

        # VWAP (requires volume and turnover, which are in df)
        if cfg["indicators"].get("vwap", False):
            self.df["VWAP"] = self._safe_calculate(
                self.calculate_vwap, "VWAP", min_data_points=1
            )
            if self.df["VWAP"] is not None:
                self.indicator_values["VWAP"] = self.df["VWAP"].iloc[-1]

        # --- Ehlers SuperTrend Calculation ---
        if cfg["indicators"].get("ehlers_supertrend", False):
            st_fast = self._safe_calculate(
                self.calculate_ehlers_supertrend,
                "EhlersSuperTrendFast",
                min_data_points=isd["ehlers_fast_period"] * 3,
                period=isd["ehlers_fast_period"],
                multiplier=isd["ehlers_fast_multiplier"],
            )
            if st_fast is not None and not st_fast.empty:
                self.df["st_fast_dir"] = st_fast["direction"]
                self.df["st_fast_val"] = st_fast["supertrend"]
                self.indicator_values["ST_Fast_Dir"] = st_fast["direction"].iloc[-1]
                self.indicator_values["ST_Fast_Val"] = st_fast["supertrend"].iloc[-1]

            st_slow = self._safe_calculate(
                self.calculate_ehlers_supertrend,
                "EhlersSuperTrendSlow",
                min_data_points=isd["ehlers_slow_period"] * 3,
                period=isd["ehlers_slow_period"],
                multiplier=isd["ehlers_slow_multiplier"],
            )
            if st_slow is not None and not st_slow.empty:
                self.df["st_slow_dir"] = st_slow["direction"]
                self.df["st_slow_val"] = st_slow["supertrend"]
                self.indicator_values["ST_Slow_Dir"] = st_slow["direction"].iloc[-1]
                self.indicator_values["ST_Slow_Val"] = st_slow["supertrend"].iloc[-1]

        # MACD
        if cfg["indicators"].get("macd", False):
            macd_line, signal_line, histogram = self._safe_calculate(
                self.calculate_macd,
                "MACD",
                min_data_points=isd["macd_slow_period"] + isd["macd_signal_period"],
                fast_period=isd["macd_fast_period"],
                slow_period=isd["macd_slow_period"],
                signal_period=isd["macd_signal_period"],
            )
            if macd_line is not None:
                self.df["MACD_Line"] = macd_line
            if signal_line is not None:
                self.df["MACD_Signal"] = signal_line
            if histogram is not None:
                self.df["MACD_Hist"] = histogram
            if macd_line is not None:
                self.indicator_values["MACD_Line"] = macd_line.iloc[-1]
            if signal_line is not None:
                self.indicator_values["MACD_Signal"] = signal_line.iloc[-1]
            if histogram is not None:
                self.indicator_values["MACD_Hist"] = histogram.iloc[-1]

        # ADX
        if cfg["indicators"].get("adx", False):
            adx_val, plus_di, minus_di = self._safe_calculate(
                self.calculate_adx,
                "ADX",
                min_data_points=isd["adx_period"] * 2,
                period=isd["adx_period"],
            )
            if adx_val is not None:
                self.df["ADX"] = adx_val
            if plus_di is not None:
                self.df["PlusDI"] = plus_di
            if minus_di is not None:
                self.df["MinusDI"] = minus_di
            if adx_val is not None:
                self.indicator_values["ADX"] = adx_val.iloc[-1]
            if plus_di is not None:
                self.indicator_values["PlusDI"] = plus_di.iloc[-1]
            if minus_di is not None:
                self.indicator_values["MinusDI"] = minus_di.iloc[-1]

        # Final dropna after all indicators are calculated
        initial_len = len(self.df)
        self.df.dropna(subset=["close"], inplace=True)
        self.df.fillna(0, inplace=True)

        if len(self.df) < initial_len:
            self.logger.debug(
                f"Dropped {initial_len - len(self.df)} rows with NaNs after indicator calculations."
            )

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}DataFrame is empty after calculating all indicators and dropping NaNs.{RESET}"
            )
        else:
            self.logger.debug(
                f"Indicators calculated. Final DataFrame size: {len(self.df)}"
            )

    def calculate_true_range(self) -> pd.Series:
        """Calculate True Range (TR)."""
        if len(self.df) < MIN_DATA_POINTS_TR:
            return pd.Series(np.nan, index=self.df.index)
        high_low = self.df["high"] - self.df["low"]
        high_prev_close = (self.df["high"] - self.df["close"].shift()).abs()
        low_prev_close = (self.df["low"] - self.df["close"].shift()).abs()
        return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(
            axis=1
        )

    def calculate_super_smoother(self, series: pd.Series, period: int) -> pd.Series:
        """Apply Ehlers SuperSmoother filter to reduce lag and noise."""
        if period <= 0 or len(series) < MIN_DATA_POINTS_SMOOTHER:
            return pd.Series(np.nan, index=series.index)

        series = pd.to_numeric(series, errors="coerce").dropna()
        if len(series) < MIN_DATA_POINTS_SMOOTHER:
            return pd.Series(np.nan, index=series.index)

        a1 = np.exp(-np.sqrt(2) * np.pi / period)
        b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / period)
        c1 = 1 - b1 + a1**2
        c2 = b1 - 2 * a1**2
        c3 = a1**2

        filt = pd.Series(0.0, index=series.index)
        if len(series) >= 1:
            filt.iloc[0] = series.iloc[0]
        if len(series) >= 2:
            filt.iloc[1] = (series.iloc[0] + series.iloc[1]) / 2

        for i in range(2, len(series)):
            filt.iloc[i] = (
                (c1 / 2) * (series.iloc[i] + series.iloc[i - 1])
                + c2 * filt.iloc[i - 1]
                - c3 * filt.iloc[i - 2]
            )
        return filt.reindex(self.df.index)

    def calculate_ehlers_supertrend(
        self, period: int, multiplier: float
    ) -> pd.DataFrame | None:
        """Calculate SuperTrend using Ehlers SuperSmoother for price and volatility."""
        if len(self.df) < period * 3:
            self.logger.debug(
                f"Not enough data for Ehlers SuperTrend (period={period}). Need at least {period * 3} bars."
            )
            return None

        df_copy = self.df.copy()

        hl2 = (df_copy["high"] + df_copy["low"]) / 2
        smoothed_price = self.calculate_super_smoother(hl2, period)

        tr = self.calculate_true_range()
        smoothed_atr = self.calculate_super_smoother(tr, period)

        df_copy["smoothed_price"] = smoothed_price
        df_copy["smoothed_atr"] = smoothed_atr

        if df_copy.empty:
            self.logger.debug(
                "Ehlers SuperTrend: DataFrame empty after smoothing. Returning None."
            )
            return None

        upper_band = df_copy["smoothed_price"] + multiplier * df_copy["smoothed_atr"]
        lower_band = df_copy["smoothed_price"] - multiplier * df_copy["smoothed_atr"]

        direction = pd.Series(0, index=df_copy.index, dtype=int)
        supertrend = pd.Series(np.nan, index=df_copy.index)

        # Find the first valid index after smoothing
        first_valid_idx_val = df_copy["smoothed_price"].first_valid_index()
        if first_valid_idx_val is None:
            return None

        supertrend.loc[first_valid_idx_val] = lower_band.loc[first_valid_idx_val]

        for i in range(df_copy.index.get_loc(first_valid_idx_val) + 1, len(df_copy)):
            current_idx = df_copy.index[i]
            prev_idx = df_copy.index[i - 1]

            prev_direction = direction.loc[prev_idx]
            prev_supertrend = supertrend.loc[prev_idx]
            curr_close = df_copy["close"].loc[current_idx]

            if prev_direction == 1:  # Previously uptrend
                supertrend.loc[current_idx] = max(
                    lower_band.loc[current_idx], prev_supertrend
                )
                if curr_close < supertrend.loc[current_idx]:
                    direction.loc[current_idx] = -1  # Trend reversal to downtrend
                    supertrend.loc[current_idx] = upper_band.loc[current_idx]
                else:
                    direction.loc[current_idx] = 1
            elif prev_direction == -1:  # Previously downtrend
                supertrend.loc[current_idx] = min(
                    upper_band.loc[current_idx], prev_supertrend
                )
                if curr_close > supertrend.loc[current_idx]:
                    direction.loc[current_idx] = 1  # Trend reversal to uptrend
                    supertrend.loc[current_idx] = lower_band.loc[current_idx]
                else:
                    direction.loc[current_idx] = -1
            elif (
                curr_close > prev_supertrend
            ):  # Assuming price above prev_ST means uptrend start
                direction.loc[current_idx] = 1
                supertrend.loc[current_idx] = max(
                    lower_band.loc[current_idx], prev_supertrend
                )
            else:  # Assuming price below prev_ST means downtrend start
                direction.loc[current_idx] = -1
                supertrend.loc[current_idx] = min(
                    upper_band.loc[current_idx], prev_supertrend
                )

        result = pd.DataFrame({"supertrend": supertrend, "direction": direction})
        return result.reindex(self.df.index)

    def calculate_macd(
        self, fast_period: int, slow_period: int, signal_period: int
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Moving Average Convergence Divergence (MACD)."""
        if len(self.df) < slow_period + signal_period:
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        ema_fast = self.df["close"].ewm(span=fast_period, adjust=False).mean()
        ema_slow = self.df["close"].ewm(span=slow_period, adjust=False).mean()

        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        histogram = macd_line - signal_line

        return macd_line, signal_line, histogram

    def calculate_rsi(self, period: int) -> pd.Series:
        """Calculate Relative Strength Index (RSI)."""
        if len(self.df) <= period:
            return pd.Series(np.nan, index=self.df.index)
        delta = self.df["close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.ewm(span=period, adjust=False, min_periods=period).mean()
        avg_loss = loss.ewm(span=period, adjust=False, min_periods=period).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_stoch_rsi(
        self, period: int, k_period: int, d_period: int
    ) -> tuple[pd.Series, pd.Series]:
        """Calculate Stochastic RSI."""
        if len(self.df) <= period:
            return pd.Series(np.nan, index=self.df.index), pd.Series(
                np.nan, index=self.df.index
            )
        rsi = self.calculate_rsi(period)

        lowest_rsi = rsi.rolling(window=period, min_periods=period).min()
        highest_rsi = rsi.rolling(window=period, min_periods=period).max()

        stoch_rsi_k_raw = (rsi - lowest_rsi) / (highest_rsi - lowest_rsi)
        stoch_rsi_k_raw = (
            stoch_rsi_k_raw.replace([np.inf, -np.inf], np.nan).fillna(0) * 100
        )  # Handle inf values, then fillnan

        stoch_rsi_k = stoch_rsi_k_raw.rolling(
            window=k_period, min_periods=k_period
        ).mean()
        stoch_rsi_d = stoch_rsi_k.rolling(window=d_period, min_periods=d_period).mean()

        return stoch_rsi_k, stoch_rsi_d

    def calculate_adx(self, period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Average Directional Index (ADX)."""
        if len(self.df) < period * 2:
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        # True Range
        tr = self.calculate_true_range()

        # Directional Movement
        plus_dm = self.df["high"].diff().clip(lower=0)
        minus_dm = -self.df["low"].diff().clip(lower=0)

        # Corrected DM calculation logic:
        # If +DM > -DM, then -DM = 0. If -DM > +DM, then +DM = 0.
        # This part requires conditional logic across the series
        plus_dm_final = plus_dm.copy()
        minus_dm_final = minus_dm.copy()

        # Identify where +DM > -DM but -DM is not zero (false positive for +DM)
        condition_plus_wins = plus_dm_final > minus_dm_final
        # Identify where -DM > +DM but +DM is not zero (false positive for -DM)
        condition_minus_wins = minus_dm_final > plus_dm_final

        plus_dm_final[condition_minus_wins] = 0
        minus_dm_final[condition_plus_wins] = 0

        # Smoothed True Range, +DM, -DM
        atr = tr.ewm(span=period, adjust=False).mean()
        plus_di = (plus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100
        minus_di = (minus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100

        # DX
        # Avoid division by zero, especially when atr is 0. Handle potential inf/nan.
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)).replace(
            [np.inf, -np.inf], np.nan
        ).fillna(0) * 100

        # ADX
        adx = dx.ewm(span=period, adjust=False).mean()

        return adx, plus_di, minus_di

    def calculate_bollinger_bands(
        self, period: int, std_dev: float
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands."""
        if len(self.df) < period:
            return (
                pd.Series(np.nan, index=self.df.index),
                pd.Series(np.nan, index=self.df.index),
                pd.Series(np.nan, index=self.df.index),
            )
        middle_band = self.df["close"].rolling(window=period, min_periods=period).mean()
        std = self.df["close"].rolling(window=period, min_periods=period).std()
        upper_band = middle_band + (std * std_dev)
        lower_band = middle_band - (std * std_dev)
        return upper_band, middle_band, lower_band

    def calculate_vwap(self) -> pd.Series:
        """Calculate Volume Weighted Average Price (VWAP)."""
        if self.df.empty:
            return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        cumulative_tp_vol = (typical_price * self.df["volume"]).cumsum()
        cumulative_vol = self.df["volume"].cumsum()
        vwap = cumulative_tp_vol / cumulative_vol
        return vwap

    def calculate_cci(self, period: int) -> pd.Series:
        """Calculate Commodity Channel Index (CCI)."""
        if len(self.df) < period:
            return pd.Series(np.nan, index=self.df.index)
        tp = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        sma_tp = tp.rolling(window=period, min_periods=period).mean()
        mad = tp.rolling(window=period, min_periods=period).apply(
            lambda x: np.abs(x - x.mean()).mean(), raw=False
        )
        cci = (tp - sma_tp) / (0.015 * mad)
        cci = cci.replace([np.inf, -np.inf], np.nan).fillna(
            0
        )  # Handle potential inf/nan from division by zero
        return cci

    def calculate_williams_r(self, period: int) -> pd.Series:
        """Calculate Williams %R."""
        if len(self.df) < period:
            return pd.Series(np.nan, index=self.df.index)
        highest_high = self.df["high"].rolling(window=period, min_periods=period).max()
        lowest_low = self.df["low"].rolling(window=period, min_periods=period).min()
        wr = -100 * ((highest_high - self.df["close"]) / (highest_high - lowest_low))
        wr = wr.replace([np.inf, -np.inf], np.nan).fillna(
            -50
        )  # Fill with neutral if division by zero
        return wr

    def calculate_ichimoku_cloud(
        self,
        tenkan_period: int,
        kijun_period: int,
        senkou_span_b_period: int,
        chikou_span_offset: int,
    ) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
        """Calculate Ichimoku Cloud components."""
        if (
            len(self.df)
            < max(tenkan_period, kijun_period, senkou_span_b_period)
            + chikou_span_offset
        ):
            return (
                pd.Series(np.nan),
                pd.Series(np.nan),
                pd.Series(np.nan),
                pd.Series(np.nan),
                pd.Series(np.nan),
            )

        tenkan_sen = (
            self.df["high"].rolling(window=tenkan_period).max()
            + self.df["low"].rolling(window=tenkan_period).min()
        ) / 2

        kijun_sen = (
            self.df["high"].rolling(window=kijun_period).max()
            + self.df["low"].rolling(window=kijun_period).min()
        ) / 2

        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun_period)

        senkou_span_b = (
            (
                self.df["high"].rolling(window=senkou_span_b_period).max()
                + self.df["low"].rolling(window=senkou_span_b_period).min()
            )
            / 2
        ).shift(kijun_period)

        chikou_span = self.df["close"].shift(-chikou_span_offset)

        return tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span

    def calculate_mfi(self, period: int) -> pd.Series:
        """Calculate Money Flow Index (MFI)."""
        if len(self.df) <= period:
            return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        money_flow = typical_price * self.df["volume"]

        positive_flow = pd.Series(0.0, index=self.df.index)
        negative_flow = pd.Series(0.0, index=self.df.index)

        for i in range(1, len(self.df)):
            if typical_price.iloc[i] > typical_price.iloc[i - 1]:
                positive_flow.iloc[i] = money_flow.iloc[i]
            elif typical_price.iloc[i] < typical_price.iloc[i - 1]:
                negative_flow.iloc[i] = money_flow.iloc[i]

        positive_mf_sum = positive_flow.rolling(window=period, min_periods=period).sum()
        negative_mf_sum = negative_flow.rolling(window=period, min_periods=period).sum()

        mf_ratio = positive_mf_sum / negative_mf_sum
        mfi = 100 - (100 / (1 + mf_ratio))
        mfi = mfi.replace([np.inf, -np.inf], np.nan).fillna(
            50
        )  # Fill with neutral if division by zero
        return mfi

    def calculate_obv(self, ema_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate On-Balance Volume (OBV) and its EMA."""
        if len(self.df) < MIN_DATA_POINTS_OBV:
            return pd.Series(np.nan), pd.Series(np.nan)

        obv = pd.Series(0.0, index=self.df.index)
        obv.iloc[0] = 0

        for i in range(1, len(self.df)):
            if self.df["close"].iloc[i] > self.df["close"].iloc[i - 1]:
                obv.iloc[i] = obv.iloc[i - 1] + self.df["volume"].iloc[i]
            elif self.df["close"].iloc[i] < self.df["close"].iloc[i - 1]:
                obv.iloc[i] = obv.iloc[i - 1] - self.df["volume"].iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i - 1]

        obv_ema = obv.ewm(span=ema_period, adjust=False).mean()

        return obv, obv_ema

    def calculate_cmf(self, period: int) -> pd.Series:
        """Calculate Chaikin Money Flow (CMF)."""
        if len(self.df) < period:
            return pd.Series(np.nan)

        mfm = (
            (self.df["close"] - self.df["low"]) - (self.df["high"] - self.df["close"])
        ) / (self.df["high"] - self.df["low"])
        mfm = mfm.replace([np.inf, -np.inf], np.nan).fillna(
            0
        )  # Handle division by zero if high == low

        mfv = mfm * self.df["volume"]

        cmf = (
            mfv.rolling(window=period).sum()
            / self.df["volume"].rolling(window=period).sum()
        )
        cmf = cmf.replace([np.inf, -np.inf], np.nan).fillna(
            0
        )  # Handle division by zero if volume sum is zero

        return cmf

    def calculate_psar(
        self, acceleration: float, max_acceleration: float
    ) -> tuple[pd.Series, pd.Series]:
        """Calculate Parabolic SAR."""
        if len(self.df) < MIN_DATA_POINTS_PSAR:
            return pd.Series(np.nan, index=self.df.index), pd.Series(
                np.nan, index=self.df.index
            )

        psar = self.df["close"].copy()
        bull = pd.Series(True, index=self.df.index)
        af = acceleration
        ep = (
            self.df["low"].iloc[0]
            if self.df["close"].iloc[0] < self.df["close"].iloc[1]
            else self.df["high"].iloc[0]
        )

        for i in range(1, len(self.df)):
            if bull.iloc[i - 1]:
                psar.iloc[i] = psar.iloc[i - 1] + af * (ep - psar.iloc[i - 1])
            else:
                psar.iloc[i] = psar.iloc[i - 1] - af * (psar.iloc[i - 1] - ep)

            reverse = False
            if bull.iloc[i - 1] and self.df["low"].iloc[i] < psar.iloc[i]:
                bull.iloc[i] = False
                reverse = True
            elif not bull.iloc[i - 1] and self.df["high"].iloc[i] > psar.iloc[i]:
                bull.iloc[i] = True
                reverse = True
            else:
                bull.iloc[i] = bull.iloc[i - 1]

            if reverse:
                af = acceleration
                ep = self.df["high"].iloc[i] if bull.iloc[i] else self.df["low"].iloc[i]
            elif bull.iloc[i]:
                if self.df["high"].iloc[i] > ep:
                    ep = self.df["high"].iloc[i]
                    af = min(af + acceleration, max_acceleration)
            elif self.df["low"].iloc[i] < ep:
                ep = self.df["low"].iloc[i]
                af = min(af + acceleration, max_acceleration)

        direction = pd.Series(0, index=self.df.index, dtype=int)
        direction[psar < self.df["close"]] = 1
        direction[psar > self.df["close"]] = -1

        return psar, direction

    def calculate_fibonacci_levels(self) -> None:
        """Calculate Fibonacci retracement levels based on a recent high-low swing."""
        window = self.config["indicator_settings"]["fibonacci_window"]
        if len(self.df) < window:
            self.logger.warning(
                f"{NEON_YELLOW}Not enough data for Fibonacci levels (need {window} bars).{RESET}"
            )
            return

        recent_high = self.df["high"].iloc[-window:].max()
        recent_low = self.df["low"].iloc[-window:].min()

        diff = recent_high - recent_low

        self.fib_levels = {
            "0.0%": Decimal(str(recent_high)),
            "23.6%": Decimal(str(recent_high - 0.236 * diff)).quantize(
                Decimal("0.00001"), rounding=ROUND_DOWN
            ),
            "38.2%": Decimal(str(recent_high - 0.382 * diff)).quantize(
                Decimal("0.00001"), rounding=ROUND_DOWN
            ),
            "50.0%": Decimal(str(recent_high - 0.500 * diff)).quantize(
                Decimal("0.00001"), rounding=ROUND_DOWN
            ),
            "61.8%": Decimal(str(recent_high - 0.618 * diff)).quantize(
                Decimal("0.00001"), rounding=ROUND_DOWN
            ),
            "78.6%": Decimal(str(recent_high - 0.786 * diff)).quantize(
                Decimal("0.00001"), rounding=ROUND_DOWN
            ),
            "100.0%": Decimal(str(recent_low)),
        }
        self.logger.debug(f"Calculated Fibonacci levels: {self.fib_levels}")

    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        """Safely retrieve an indicator value."""
        return self.indicator_values.get(key, default)

    def _check_orderbook(self, current_price: Decimal, orderbook_data: dict) -> float:
        """Analyze orderbook imbalance."""
        bids = orderbook_data.get("b", [])
        asks = orderbook_data.get("a", [])

        bid_volume = sum(Decimal(b[1]) for b in bids)
        ask_volume = sum(Decimal(a[1]) for a in asks)

        if bid_volume + ask_volume == 0:
            return 0.0

        imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
        self.logger.debug(
            f"Orderbook Imbalance: {imbalance:.4f} (Bids: {bid_volume}, Asks: {ask_volume})"
        )
        return float(imbalance)

    def _get_mtf_trend(self, higher_tf_df: pd.DataFrame, indicator_type: str) -> str:
        """Determine trend from higher timeframe using specified indicator."""
        if higher_tf_df.empty:
            return "UNKNOWN"

        last_close = higher_tf_df["close"].iloc[-1]

        if indicator_type == "sma":
            period = self.config["mtf_analysis"]["trend_period"]
            if len(higher_tf_df) < period:
                self.logger.debug(
                    f"MTF SMA: Not enough data for {period} period. Have {len(higher_tf_df)}."
                )
                return "UNKNOWN"
            sma = (
                higher_tf_df["close"]
                .rolling(window=period, min_periods=period)
                .mean()
                .iloc[-1]
            )
            if last_close > sma:
                return "UP"
            if last_close < sma:
                return "DOWN"
            return "SIDEWAYS"
        if indicator_type == "ema":
            period = self.config["mtf_analysis"]["trend_period"]
            if len(higher_tf_df) < period:
                self.logger.debug(
                    f"MTF EMA: Not enough data for {period} period. Have {len(higher_tf_df)}."
                )
                return "UNKNOWN"
            ema = (
                higher_tf_df["close"]
                .ewm(span=period, adjust=False, min_periods=period)
                .mean()
                .iloc[-1]
            )
            if last_close > ema:
                return "UP"
            if last_close < ema:
                return "DOWN"
            return "SIDEWAYS"
        if indicator_type == "ehlers_supertrend":
            temp_analyzer = TradingAnalyzer(
                higher_tf_df, self.config, self.logger, self.symbol
            )
            st_result = temp_analyzer.calculate_ehlers_supertrend(
                period=self.indicator_settings["ehlers_slow_period"],
                multiplier=self.indicator_settings["ehlers_slow_multiplier"],
            )
            if st_result is not None and not st_result.empty:
                st_dir = st_result["direction"].iloc[-1]
                if st_dir == 1:
                    return "UP"
                if st_dir == -1:
                    return "DOWN"
            return "UNKNOWN"
        return "UNKNOWN"

    def generate_trading_signal(
        self,
        current_price: Decimal,
        orderbook_data: dict | None,
        mtf_trends: dict[str, str],
    ) -> tuple[str, float]:
        """Generate a signal using confluence of indicators, including Ehlers SuperTrend."""
        signal_score = 0.0
        active_indicators = self.config["indicators"]
        weights = self.weights

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}"
            )
            return "HOLD", 0.0

        current_close = Decimal(str(self.df["close"].iloc[-1]))

        # EMA Alignment
        if active_indicators.get("ema_alignment", False):
            ema_short = self._get_indicator_value("EMA_Short")
            ema_long = self._get_indicator_value("EMA_Long")
            if not pd.isna(ema_short) and not pd.isna(ema_long):
                if ema_short > ema_long:
                    signal_score += weights.get("ema_alignment", 0)
                elif ema_short < ema_long:
                    signal_score -= weights.get("ema_alignment", 0)

        # SMA Trend Filter
        if active_indicators.get("sma_trend_filter", False):
            sma_long = self._get_indicator_value("SMA_Long")
            if not pd.isna(sma_long):
                if current_close > sma_long:
                    signal_score += weights.get("sma_trend_filter", 0)
                elif current_close < sma_long:
                    signal_score -= weights.get("sma_trend_filter", 0)

        if active_indicators.get("momentum", False):
            rsi = self._get_indicator_value("RSI")
            stoch_k = self._get_indicator_value("StochRSI_K")
            stoch_d = self._get_indicator_value("StochRSI_D")
            cci = self._get_indicator_value("CCI")
            wr = self._get_indicator_value("WR")
            mfi = self._get_indicator_value("MFI")

            isd = self.indicator_settings

            # RSI
            if not pd.isna(rsi):
                if rsi < isd["rsi_oversold"]:
                    signal_score += weights.get("rsi", 0) * 0.5
                elif rsi > isd["rsi_overbought"]:
                    signal_score -= weights.get("rsi", 0) * 0.5

            # StochRSI Crossover
            if not pd.isna(stoch_k) and not pd.isna(stoch_d):
                if stoch_k > stoch_d and stoch_k < isd["stoch_rsi_oversold"]:
                    signal_score += weights.get("stoch_rsi", 0) * 0.5
                elif stoch_k < stoch_d and stoch_k > isd["stoch_rsi_overbought"]:
                    signal_score -= weights.get("stoch_rsi", 0) * 0.5

            # CCI
            if not pd.isna(cci):
                if cci < isd["cci_oversold"]:
                    signal_score += weights.get("cci", 0) * 0.5
                elif cci > isd["cci_overbought"]:
                    signal_score -= weights.get("cci", 0) * 0.5

            if not pd.isna(wr):
                if wr < isd["williams_r_oversold"]:
                    signal_score += weights.get("wr", 0) * 0.5
                elif wr > isd["williams_r_overbought"]:
                    signal_score -= weights.get("wr", 0) * 0.5

            # MFI
            if not pd.isna(mfi):
                if mfi < isd["mfi_oversold"]:
                    signal_score += weights.get("mfi", 0) * 0.5
                elif mfi > isd["mfi_overbought"]:
                    signal_score -= weights.get("mfi", 0) * 0.5

        # Bollinger Bands
        if active_indicators.get("bollinger_bands", False):
            bb_upper = self._get_indicator_value("BB_Upper")
            bb_lower = self._get_indicator_value("BB_Lower")
            if not pd.isna(bb_upper) and not pd.isna(bb_lower):
                if current_close < bb_lower:
                    signal_score += weights.get("bollinger_bands", 0) * 0.5
                elif current_close > bb_upper:
                    signal_score -= weights.get("bollinger_bands", 0) * 0.5

        # VWAP
        if active_indicators.get("vwap", False):
            vwap = self._get_indicator_value("VWAP")
            if not pd.isna(vwap):
                if current_close > vwap:
                    signal_score += weights.get("vwap", 0) * 0.2
                elif current_close < vwap:
                    signal_score -= weights.get("vwap", 0) * 0.2

                if len(self.df) > 1:
                    prev_close = Decimal(str(self.df["close"].iloc[-2]))
                    prev_vwap = Decimal(str(self.df["VWAP"].iloc[-2]))
                    if current_close > vwap and prev_close <= prev_vwap:
                        signal_score += weights.get("vwap", 0) * 0.3
                        self.logger.debug("VWAP: Bullish crossover detected.")
                    elif current_close < vwap and prev_close >= prev_vwap:
                        signal_score -= weights.get("vwap", 0) * 0.3
                        self.logger.debug("VWAP: Bearish crossover detected.")

        # PSAR
        if active_indicators.get("psar", False):
            psar_val = self._get_indicator_value("PSAR_Val")
            psar_dir = self._get_indicator_value("PSAR_Dir")
            if not pd.isna(psar_val) and not pd.isna(psar_dir):
                if psar_dir == 1:
                    signal_score += weights.get("psar", 0) * 0.5
                elif psar_dir == -1:
                    signal_score -= weights.get("psar", 0) * 0.5

                if len(self.df) > 1:
                    prev_close = Decimal(str(self.df["close"].iloc[-2]))
                    prev_psar_val = Decimal(str(self.df["PSAR_Val"].iloc[-2]))
                    if current_close > psar_val and prev_close <= prev_psar_val:
                        signal_score += weights.get("psar", 0) * 0.4
                        self.logger.debug("PSAR: Bullish reversal detected.")
                    elif current_close < psar_val and prev_close >= prev_psar_val:
                        signal_score -= weights.get("psar", 0) * 0.4
                        self.logger.debug("PSAR: Bearish reversal detected.")

        # Orderbook Imbalance
        if active_indicators.get("orderbook_imbalance", False) and orderbook_data:
            imbalance = self._check_orderbook(current_price, orderbook_data)
            signal_score += imbalance * weights.get("orderbook_imbalance", 0)

        # Fibonacci Levels (confluence with price action)
        if active_indicators.get("fibonacci_levels", False) and self.fib_levels:
            for level_name, level_price in self.fib_levels.items():
                if level_name not in ["0.0%", "100.0%"] and abs(
                    current_price - level_price
                ) / current_price < Decimal("0.001"):
                    self.logger.debug(
                        f"Price near Fibonacci level {level_name}: {level_price}"
                    )
                    if len(self.df) > 1:
                        prev_close = Decimal(str(self.df["close"].iloc[-2]))
                        if current_close > prev_close and current_close > level_price:
                            signal_score += weights.get("fibonacci_levels", 0) * 0.1
                        elif current_close < prev_close and current_close < level_price:
                            signal_score -= weights.get("fibonacci_levels", 0) * 0.1

        # --- Ehlers SuperTrend Alignment Scoring ---
        if active_indicators.get("ehlers_supertrend", False):
            st_fast_dir = self._get_indicator_value("ST_Fast_Dir")
            st_slow_dir = self._get_indicator_value("ST_Slow_Dir")

            prev_st_fast_dir = (
                self.df["st_fast_dir"].iloc[-2]
                if "st_fast_dir" in self.df.columns and len(self.df) > 1
                else np.nan
            )

            weight = weights.get("ehlers_supertrend_alignment", 0.0)

            if (
                not pd.isna(st_fast_dir)
                and not pd.isna(st_slow_dir)
                and not pd.isna(prev_st_fast_dir)
            ):
                if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1:
                    signal_score += weight
                    self.logger.debug(
                        "Ehlers SuperTrend: Strong BUY signal (fast flip aligned with slow trend)."
                    )
                elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1:
                    signal_score -= weight
                    self.logger.debug(
                        "Ehlers SuperTrend: Strong SELL signal (fast flip aligned with slow trend)."
                    )
                elif st_slow_dir == 1 and st_fast_dir == 1:
                    signal_score += weight * 0.3
                elif st_slow_dir == -1 and st_fast_dir == -1:
                    signal_score -= weight * 0.3

        # --- MACD Alignment Scoring ---
        if active_indicators.get("macd", False):
            macd_line = self._get_indicator_value("MACD_Line")
            signal_line = self._get_indicator_value("MACD_Signal")
            histogram = self._get_indicator_value("MACD_Hist")

            weight = weights.get("macd_alignment", 0.0)

            if (
                not pd.isna(macd_line)
                and not pd.isna(signal_line)
                and not pd.isna(histogram)
            ):
                if (
                    macd_line > signal_line
                    and self.df["MACD_Line"].iloc[-2] <= self.df["MACD_Signal"].iloc[-2]
                ):
                    signal_score += weight
                    self.logger.debug(
                        "MACD: BUY signal (MACD line crossed above Signal line)."
                    )
                elif (
                    macd_line < signal_line
                    and self.df["MACD_Line"].iloc[-2] >= self.df["MACD_Signal"].iloc[-2]
                ):
                    signal_score -= weight
                    self.logger.debug(
                        "MACD: SELL signal (MACD line crossed below Signal line)."
                    )
                elif histogram > 0 and self.df["MACD_Hist"].iloc[-2] < 0:
                    signal_score += weight * 0.2
                elif histogram < 0 and self.df["MACD_Hist"].iloc[-2] > 0:
                    signal_score -= weight * 0.2

        # --- ADX Alignment Scoring ---
        if active_indicators.get("adx", False):
            adx_val = self._get_indicator_value("ADX")
            plus_di = self._get_indicator_value("PlusDI")
            minus_di = self._get_indicator_value("MinusDI")

            weight = weights.get("adx_strength", 0.0)

            if not pd.isna(adx_val) and not pd.isna(plus_di) and not pd.isna(minus_di):
                if adx_val > ADX_STRONG_TREND_THRESHOLD:
                    if plus_di > minus_di:
                        signal_score += weight
                        self.logger.debug(
                            "ADX: Strong BUY trend (ADX > 25, +DI > -DI)."
                        )
                    elif minus_di > plus_di:
                        signal_score -= weight
                        self.logger.debug(
                            "ADX: Strong SELL trend (ADX > 25, -DI > +DI)."
                        )
                elif adx_val < ADX_WEAK_TREND_THRESHOLD:
                    signal_score += 0
                    self.logger.debug("ADX: Weak trend (ADX < 20). Neutral signal.")

        # --- Ichimoku Cloud Alignment Scoring ---
        if active_indicators.get("ichimoku_cloud", False):
            tenkan_sen = self._get_indicator_value("Tenkan_Sen")
            kijun_sen = self._get_indicator_value("Kijun_Sen")
            senkou_span_a = self._get_indicator_value("Senkou_Span_A")
            senkou_span_b = self._get_indicator_value("Senkou_Span_B")
            chikou_span = self._get_indicator_value("Chikou_Span")

            weight = weights.get("ichimoku_confluence", 0.0)

            if (
                not pd.isna(tenkan_sen)
                and not pd.isna(kijun_sen)
                and not pd.isna(senkou_span_a)
                and not pd.isna(senkou_span_b)
                and not pd.isna(chikou_span)
            ):
                if (
                    tenkan_sen > kijun_sen
                    and self.df["Tenkan_Sen"].iloc[-2] <= self.df["Kijun_Sen"].iloc[-2]
                ):
                    signal_score += weight * 0.5
                    self.logger.debug(
                        "Ichimoku: Tenkan-sen crossed above Kijun-sen (bullish)."
                    )
                elif (
                    tenkan_sen < kijun_sen
                    and self.df["Tenkan_Sen"].iloc[-2] >= self.df["Kijun_Sen"].iloc[-2]
                ):
                    signal_score -= weight * 0.5
                    self.logger.debug(
                        "Ichimoku: Tenkan-sen crossed below Kijun-sen (bearish)."
                    )

                if current_close > max(senkou_span_a, senkou_span_b) and self.df[
                    "close"
                ].iloc[-2] <= max(
                    self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]
                ):
                    signal_score += weight * 0.7
                    self.logger.debug(
                        "Ichimoku: Price broke above Kumo (strong bullish)."
                    )
                elif current_close < min(senkou_span_a, senkou_span_b) and self.df[
                    "close"
                ].iloc[-2] >= min(
                    self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]
                ):
                    signal_score -= weight * 0.7
                    self.logger.debug(
                        "Ichimoku: Price broke below Kumo (strong bearish)."
                    )

                if (
                    chikou_span > current_close
                    and self.df["Chikou_Span"].iloc[-2] <= self.df["close"].iloc[-2]
                ):
                    signal_score += weight * 0.3
                    self.logger.debug(
                        "Ichimoku: Chikou Span crossed above price (bullish confirmation)."
                    )
                elif (
                    chikou_span < current_close
                    and self.df["Chikou_Span"].iloc[-2] >= self.df["close"].iloc[-2]
                ):
                    signal_score -= weight * 0.3
                    self.logger.debug(
                        "Ichimoku: Chikou Span crossed below price (bearish confirmation)."
                    )

        # --- OBV Alignment Scoring ---
        if active_indicators.get("obv", False):
            obv_val = self._get_indicator_value("OBV")
            obv_ema = self._get_indicator_value("OBV_EMA")

            weight = weights.get("obv_momentum", 0.0)

            if not pd.isna(obv_val) and not pd.isna(obv_ema):
                if (
                    obv_val > obv_ema
                    and self.df["OBV"].iloc[-2] <= self.df["OBV_EMA"].iloc[-2]
                ):
                    signal_score += weight * 0.5
                    self.logger.debug("OBV: Bullish crossover detected.")
                elif (
                    obv_val < obv_ema
                    and self.df["OBV"].iloc[-2] >= self.df["OBV_EMA"].iloc[-2]
                ):
                    signal_score -= weight * 0.5
                    self.logger.debug("OBV: Bearish crossover detected.")

                if len(self.df) > 2:
                    if (
                        obv_val > self.df["OBV"].iloc[-2]
                        and obv_val > self.df["OBV"].iloc[-3]
                    ):
                        signal_score += weight * 0.2
                    elif (
                        obv_val < self.df["OBV"].iloc[-2]
                        and obv_val < self.df["OBV"].iloc[-3]
                    ):
                        signal_score -= weight * 0.2

        # --- CMF Alignment Scoring ---
        if active_indicators.get("cmf", False):
            cmf_val = self._get_indicator_value("CMF")

            weight = weights.get("cmf_flow", 0.0)

            if not pd.isna(cmf_val):
                if cmf_val > 0:
                    signal_score += weight * 0.5
                elif cmf_val < 0:
                    signal_score -= weight * 0.5

                if len(self.df) > 2:
                    if (
                        cmf_val > self.df["CMF"].iloc[-2]
                        and cmf_val > self.df["CMF"].iloc[-3]
                    ):
                        signal_score += weight * 0.3
                    elif (
                        cmf_val < self.df["CMF"].iloc[-2]
                        and cmf_val < self.df["CMF"].iloc[-3]
                    ):
                        signal_score -= weight * 0.3

        # --- Multi-Timeframe Trend Confluence Scoring ---
        if self.config["mtf_analysis"]["enabled"] and mtf_trends:
            mtf_buy_score = 0
            mtf_sell_score = 0
            for _tf, trend in mtf_trends.items():
                if trend == "UP":
                    mtf_buy_score += 1
                elif trend == "DOWN":
                    mtf_sell_score -= 1
            if mtf_trends:
                normalized_mtf_score = (mtf_buy_score + mtf_sell_score) / len(
                    mtf_trends
                )
                signal_score += (
                    weights.get("mtf_trend_confluence", 0.0) * normalized_mtf_score
                )
                self.logger.debug(
                    f"MTF Confluence: Score {normalized_mtf_score:.2f} (Buy: {mtf_buy_score}, Sell: {abs(mtf_sell_score)}). Total MTF contribution: {weights.get('mtf_trend_confluence', 0.0) * normalized_mtf_score:.2f}"
                )

        # --- Final Signal Determination ---
        threshold = self.config["signal_score_threshold"]
        final_signal = "HOLD"
        if signal_score >= threshold:
            final_signal = "BUY"
        elif signal_score <= -threshold:
            final_signal = "SELL"

        self.logger.info(
            f"{NEON_YELLOW}Raw Technical Signal Score: {signal_score:.2f}, Final Technical Signal: {final_signal}{RESET}"
        )
        return final_signal, signal_score


def display_indicator_values_and_price(
    config: dict[str, Any],
    logger: logging.Logger,
    current_price: Decimal,
    df: pd.DataFrame,
    orderbook_data: dict | None,
    mtf_trends: dict[str, str],
) -> None:
    """Display current price and calculated indicator values."""
    logger.info(f"{NEON_BLUE}--- Current Market Data & Indicators ---{RESET}")
    logger.info(f"{NEON_GREEN}Current Price: {current_price}{RESET}")

    analyzer = TradingAnalyzer(df, config, logger, config["symbol"])

    if analyzer.df.empty:
        logger.warning(
            f"{NEON_YELLOW}Cannot display indicators: DataFrame is empty after calculations.{RESET}"
        )
        return

    logger.info(f"{NEON_CYAN}--- Indicator Values ---{RESET}")
    for indicator_name, value in analyzer.indicator_values.items():
        color = INDICATOR_COLORS.get(indicator_name, NEON_YELLOW)
        if isinstance(value, Decimal) or isinstance(value, float):
            logger.info(f"  {color}{indicator_name}: {value:.8f}{RESET}")
        else:
            logger.info(f"  {color}{indicator_name}: {value}{RESET}")

    if analyzer.fib_levels:
        logger.info(f"{NEON_CYAN}--- Fibonacci Levels ---{RESET}")
        logger.info("")
        for level_name, level_price in analyzer.fib_levels.items():
            logger.info(f"  {NEON_YELLOW}{level_name}: {level_price:.8f}{RESET}")

    if mtf_trends:
        logger.info(f"{NEON_CYAN}--- Multi-Timeframe Trends ---{RESET}")
        logger.info("")
        for tf_indicator, trend in mtf_trends.items():
            logger.info(f"  {NEON_YELLOW}{tf_indicator}: {trend}{RESET}")

    logger.info(f"{NEON_BLUE}--------------------------------------{RESET}")


def main() -> None:
    """Orchestrate the bot's operation."""
    logger = setup_logger("wgwhalex_bot")
    config = load_config(CONFIG_FILE, logger)
    alert_system = AlertSystem(logger)

    # Validate interval format at startup
    valid_bybit_intervals = [
        "1",
        "3",
        "5",
        "15",
        "30",
        "60",
        "120",
        "240",
        "360",
        "720",
        "D",
        "W",
        "M",
        "1h",
        "4h",  # Also check for common aliases
    ]
    # Standardize intervals if aliases used in config
    interval_mapping = {"1h": "60", "4h": "240"}

    # Check primary interval
    if config["interval"] not in valid_bybit_intervals:
        logger.error(
            f"{NEON_RED}Invalid primary interval '{config['interval']}' in config.json. Please use Bybit's valid string formats (e.g., '15', '60', 'D'). Exiting.{RESET}"
        )
        sys.exit(1)
    if config["interval"] in interval_mapping:
        config["interval"] = interval_mapping[config["interval"]]
        logger.info(f"Normalized primary interval to: {config['interval']}")

    # Check higher timeframes intervals
    for i, htf_interval in enumerate(config["mtf_analysis"]["higher_timeframes"]):
        if htf_interval not in valid_bybit_intervals:
            logger.error(
                f"{NEON_RED}Invalid higher timeframe interval '{htf_interval}' in config.json. Please use Bybit's valid string formats (e.g., '1h' should be '60', '4h' should be '240'). Exiting.{RESET}"
            )
            sys.exit(1)
        if htf_interval in interval_mapping:
            config["mtf_analysis"]["higher_timeframes"][i] = interval_mapping[
                htf_interval
            ]
            logger.info(
                f"Normalized MTF interval {htf_interval} to: {config['mtf_analysis']['higher_timeframes'][i]}"
            )

    logger.info(f"{NEON_GREEN}--- Wgwhalex Trading Bot Initialized ---{RESET}")
    logger.info(f"Symbol: {config['symbol']}, Interval: {config['interval']}")
    logger.info(f"Trade Management Enabled: {config['trade_management']['enabled']}")

    position_manager = PositionManager(config, logger, config["symbol"])
    performance_tracker = PerformanceTracker(logger)

    # --- Initialize Gemini AI if enabled ---
    gemini_analyzer: GeminiSignalAnalyzer | None = None
    if config["gemini_ai"]["enabled"]:
        gemini_api_key = os.getenv(config["gemini_ai"]["api_key_env"])
        if gemini_api_key:
            try:
                gemini_analyzer = GeminiSignalAnalyzer(
                    api_key=gemini_api_key,
                    logger=logger,
                    model=config["gemini_ai"]["model"],
                    config={
                        "cache_ttl_seconds": config["gemini_ai"]["cache_ttl_seconds"],
                        "daily_api_limit": config["gemini_ai"]["daily_api_limit"],
                        "signal_score_threshold": config["signal_score_threshold"],
                        "signal_weights": config["gemini_ai"]["signal_weights"],
                        "low_ai_confidence_threshold": config["gemini_ai"][
                            "low_ai_confidence_threshold"
                        ],
                        "symbol": config["symbol"],  # Pass symbol for chart titles
                        "interval": config[
                            "interval"
                        ],  # Pass interval for chart titles
                        "chart_image_data_points": config["gemini_ai"][
                            "chart_image_analysis"
                        ]["data_points_for_chart"],
                    },
                )
                logger.info(
                    f"{NEON_GREEN}Gemini AI Signal Analyzer initialized successfully.{RESET}"
                )
            except Exception as e:
                logger.error(
                    f"{NEON_RED}Failed to initialize Gemini AI: {e}. AI analysis will be disabled.{RESET}"
                )
                config["gemini_ai"]["enabled"] = False
        else:
            logger.warning(
                f"{NEON_YELLOW}Gemini API key not found in environment variable '{config['gemini_ai']['api_key_env']}'. AI analysis disabled.{RESET}"
            )
            config["gemini_ai"]["enabled"] = False

    loop_count = 0  # For chart image analysis frequency
    while True:
        loop_count += 1
        try:
            logger.info(
                f"{NEON_PURPLE}--- New Analysis Loop Started (Loop: {loop_count}) ---{RESET}"
            )
            current_price = fetch_current_price(config["symbol"], logger)
            if current_price is None:
                alert_system.send_alert(
                    "Failed to fetch current price. Skipping loop.", "WARNING"
                )
                time.sleep(config["loop_delay"])
                continue

            df = fetch_klines(config["symbol"], config["interval"], 1000, logger)
            if df is None or df.empty:
                alert_system.send_alert(
                    "Failed to fetch primary klines or DataFrame is empty. Skipping loop.",
                    "WARNING",
                )
                time.sleep(config["loop_delay"])
                continue

            orderbook_data = None
            if config["indicators"].get("orderbook_imbalance", False):
                orderbook_data = fetch_orderbook(
                    config["symbol"], config["orderbook_limit"], logger
                )

            mtf_trends: dict[str, str] = {}
            if config["mtf_analysis"]["enabled"]:
                for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
                    logger.debug(f"Fetching klines for MTF interval: {htf_interval}")
                    htf_df = fetch_klines(config["symbol"], htf_interval, 1000, logger)
                    if htf_df is not None and not htf_df.empty:
                        for trend_ind in config["mtf_analysis"]["trend_indicators"]:
                            temp_htf_analyzer = TradingAnalyzer(
                                htf_df, config, logger, config["symbol"]
                            )
                            trend = temp_htf_analyzer._get_mtf_trend(
                                temp_htf_analyzer.df, trend_ind
                            )
                            mtf_trends[f"{htf_interval}_{trend_ind}"] = trend
                            logger.debug(
                                f"MTF Trend ({htf_interval}, {trend_ind}): {trend}"
                            )
                    else:
                        logger.warning(
                            f"{NEON_YELLOW}Could not fetch klines for higher timeframe {htf_interval} or it was empty. Skipping MTF trend for this TF.{RESET}"
                        )

                    time.sleep(config["mtf_analysis"]["mtf_request_delay_seconds"])

            display_indicator_values_and_price(
                config, logger, current_price, df, orderbook_data, mtf_trends
            )

            analyzer = TradingAnalyzer(df, config, logger, config["symbol"])

            if analyzer.df.empty:
                alert_system.send_alert(
                    "TradingAnalyzer DataFrame is empty after indicator calculations. Cannot generate signal.",
                    "WARNING",
                )
                time.sleep(config["loop_delay"])
                continue

            # --- Technical Signal Generation ---
            technical_signal, technical_score = analyzer.generate_trading_signal(
                current_price, orderbook_data, mtf_trends
            )

            final_trading_signal = technical_signal
            final_signal_score = technical_score
            ai_signal_details: dict[str, Any] | None = None
            ai_position_sizing_info: dict[str, Decimal] | None = None

            # --- Enhance with Gemini AI if available and enabled ---
            if gemini_analyzer and config["gemini_ai"]["enabled"]:
                try:
                    time.sleep(config["gemini_ai"]["rate_limit_delay_seconds"])

                    # Call Gemini for advanced text analysis
                    ai_enhanced_signal, ai_combined_score, ai_details = (
                        gemini_analyzer.generate_advanced_signal(
                            df=analyzer.df,
                            indicator_values=analyzer.indicator_values,
                            current_price=current_price,
                            symbol=config["symbol"],
                            mtf_trends=mtf_trends,
                            existing_signal=technical_signal,
                            existing_score=technical_score,
                        )
                    )

                    # Apply AI-enhanced signal if confidence is sufficient
                    if (
                        ai_details.get("ai_confidence", 0)
                        >= config["gemini_ai"]["min_confidence_for_override"]
                    ):
                        final_trading_signal = ai_enhanced_signal
                        final_signal_score = ai_combined_score
                        ai_signal_details = ai_details

                        logger.info(
                            f"{NEON_PURPLE}AI-Enhanced Signal applied: {final_trading_signal} (Score: {final_signal_score:.2f}){RESET}"
                        )

                        # Calculate AI-driven position sizing
                        ai_position_sizing_info = (
                            gemini_analyzer.calculate_position_sizing(
                                ai_analysis=ai_details,
                                account_balance=Decimal(
                                    str(config["trade_management"]["account_balance"])
                                ),
                                risk_per_trade_percent=Decimal(
                                    str(
                                        config["trade_management"][
                                            "risk_per_trade_percent"
                                        ]
                                        / 100
                                    )
                                ),
                                min_stop_loss_distance=current_price
                                * Decimal(
                                    str(
                                        config["trade_management"][
                                            "min_stop_loss_distance_ratio"
                                        ]
                                    )
                                ),
                            )
                        )
                        if ai_position_sizing_info:
                            logger.info(
                                f"{NEON_CYAN}AI Suggested Position Sizing: Risk Amount=${ai_position_sizing_info['risk_amount']:.2f}, Stop Dist={ai_position_sizing_info['stop_distance']:.8f}{RESET}"
                            )
                    else:
                        logger.info(
                            f"{NEON_YELLOW}Gemini AI confidence ({ai_details.get('ai_confidence', 0)}%) too low for override ({config['gemini_ai']['min_confidence_for_override']}% required). Using technical signal.{RESET}"
                        )
                        ai_signal_details = (
                            ai_details  # Still keep details for logging/debugging
                        )

                    # --- Gemini Vision for Chart Analysis (Optional, performance intensive) ---
                    if (
                        config["gemini_ai"]["chart_image_analysis"]["enabled"]
                        and config["gemini_ai"]["chart_image_analysis"][
                            "frequency_loops"
                        ]
                        > 0
                        and loop_count
                        % config["gemini_ai"]["chart_image_analysis"]["frequency_loops"]
                        == 0
                    ):
                        logger.info(
                            f"{NEON_BLUE}Performing Gemini Vision chart analysis...{RESET}"
                        )
                        vision_analysis_result = gemini_analyzer.analyze_chart_image(
                            df, config["interval"]
                        )
                        if vision_analysis_result.get("status") == "success":
                            logger.info(
                                f"{NEON_CYAN}Gemini Vision Chart Analysis: {vision_analysis_result['analysis'][:300]}...{RESET}"
                            )
                        else:
                            logger.warning(
                                f"{NEON_YELLOW}Gemini Vision Chart Analysis Failed: {vision_analysis_result.get('error', 'Unknown error')}{RESET}"
                            )

                except Exception as e:
                    logger.error(
                        f"{NEON_RED}Error during Gemini AI analysis. Falling back to technical signal: {e}{RESET}"
                    )
            # --- End Gemini AI Enhancement ---

            atr_value = Decimal(
                str(analyzer._get_indicator_value("ATR", Decimal("0.01")))
            )

            # --- Position Management ---
            # Pass ai_signal_details to PositionManager to store if a trade is opened
            # and for future performance tracking
            ai_signal_at_open = (
                ai_signal_details.get("ai_signal") if ai_signal_details else None
            )

            # Pass gemini_analyzer to manage_positions for performance tracking after trade close
            position_manager.manage_positions(
                current_price, performance_tracker, gemini_analyzer
            )

            # Determine if we have a BUY/SELL signal from the final (technical or AI-enhanced) signal
            if (
                final_trading_signal == "BUY"
                and final_signal_score >= config["signal_score_threshold"]
            ):
                logger.info(
                    f"{NEON_GREEN}Strong BUY signal detected! Score: {final_signal_score:.2f}{RESET}"
                )
                new_pos = position_manager.open_position(
                    "BUY",
                    current_price,
                    atr_value,
                    ai_suggested_levels=ai_signal_details.get("suggested_levels")
                    if ai_signal_details
                    else None,
                )
                if new_pos and ai_signal_at_open:
                    new_pos["ai_signal"] = (
                        ai_signal_at_open  # Store AI signal for tracking
                    )

            elif (
                final_trading_signal == "SELL"
                and final_signal_score <= -config["signal_score_threshold"]
            ):
                logger.info(
                    f"{NEON_RED}Strong SELL signal detected! Score: {final_signal_score:.2f}{RESET}"
                )
                new_pos = position_manager.open_position(
                    "SELL",
                    current_price,
                    atr_value,
                    ai_suggested_levels=ai_signal_details.get("suggested_levels")
                    if ai_signal_details
                    else None,
                )
                if new_pos and ai_signal_at_open:
                    new_pos["ai_signal"] = (
                        ai_signal_at_open  # Store AI signal for tracking
                    )
            else:
                logger.info(
                    f"{NEON_BLUE}No strong trading signal. Holding. Score: {final_signal_score:.2f}{RESET}"
                )

            # Log current open positions
            open_positions = position_manager.get_open_positions()
            if open_positions:
                logger.info(f"{NEON_CYAN}Open Positions: {len(open_positions)}{RESET}")
                for pos in open_positions:
                    logger.info(
                        f"  - {pos['side']} @ {pos['entry_price']} (SL: {pos['stop_loss']}, TP: {pos['take_profit']}){RESET}"
                    )
            else:
                logger.info(f"{NEON_CYAN}No open positions.{RESET}")

            # Log performance summary
            perf_summary = performance_tracker.get_summary()
            logger.info(
                f"{NEON_YELLOW}Performance Summary: Total PnL: {perf_summary['total_pnl']:.2f}, Wins: {perf_summary['wins']}, Losses: {perf_summary['losses']}, Win Rate: {perf_summary['win_rate']}{RESET}"
            )

            # Log Gemini AI performance metrics
            if gemini_analyzer and config["gemini_ai"]["enabled"]:
                gm_perf = gemini_analyzer.performance_metrics
                logger.info(f"{NEON_PURPLE}Gemini AI Performance:{RESET}")
                logger.info(
                    f"  Total Analyses: {gm_perf['total_analyses']}, Successful: {gm_perf['successful_analyses']}, Errors: {gm_perf['api_errors']}, Cache Hits: {gm_perf['cache_hits']}{RESET}"
                )
                if gm_perf["avg_response_time_ms"] > 0:
                    logger.info(
                        f"  Avg. Response Time: {gm_perf['avg_response_time_ms']:.2f} ms (non-cached){RESET}"
                    )

                if gm_perf["signal_accuracy"]:
                    logger.info(f"{NEON_CYAN}  AI Signal Accuracy (by outcome):{RESET}")
                    for sig_type, stats in gm_perf["signal_accuracy"].items():
                        win_rate = (
                            (stats["WIN"] / stats["total"] * 100)
                            if stats["total"] > 0
                            else 0
                        )
                        logger.info(
                            f"    {sig_type}: Total: {stats['total']}, Wins: {stats['WIN']}, Losses: {stats['LOSS']}, BreakEvens: {stats['BREAKEVEN']} (Win Rate: {win_rate:.2f}%) {RESET}"
                        )

            logger.info(
                f"{NEON_PURPLE}--- Analysis Loop Finished. Waiting {config['loop_delay']}s ---{RESET}"
            )
            time.sleep(config["loop_delay"])

        except Exception as e:
            alert_system.send_alert(
                f"An unhandled error occurred in the main loop: {e}", "ERROR"
            )
            logger.exception(f"{NEON_RED}Unhandled exception in main loop:{RESET}")
            time.sleep(config["loop_delay"] * 2)  # Longer delay on error


if __name__ == "__main__":
    main()
