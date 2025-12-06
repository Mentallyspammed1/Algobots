"""
Python port of the `OracleBrain` class from `aimm.cjs`.
"""
import os
import json
import numpy as np
import google.generativeai as genai
from typing import Dict, Any, List, Optional

# Assuming technical_analysis.py is in the same src directory
from . import technical_analysis as ta

class OracleBrain:
    """
    Interfaces with the Generative AI model to produce trading signals.
    """
    def __init__(self, model_name: str = 'gemini-2.5-flash-lite'):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set.")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            model_name,
            generation_config={"response_mimetype": "application/json"}
        )
        self.klines: List[Dict[str, float]] = []
        self.mtf_klines: List[Dict[str, float]] = []

    def _klines_to_numpy(self, klines: List[Dict[str, float]]) -> Dict[str, np.ndarray]:
        """Utility to convert a list of kline dicts to a dict of numpy arrays."""
        if not klines:
            return {
                'high': np.array([]), 'low': np.array([]), 
                'close': np.array([]), 'volume': np.array([])
            }
        
        # Convert list of dicts to dict of lists, then to numpy arrays
        return {key: np.array([k[key] for k in klines]) for key in ['high', 'low', 'close', 'volume']}

    def update_kline(self, kline: Dict[str, float]):
        """Adds a new main timeframe kline, maintaining a max length of 500."""
        self.klines.append(kline)
        if len(self.klines) > 500:
            self.klines.pop(0)

    def update_mtf_kline(self, kline: Dict[str, float]):
        """Adds a new multi-timeframe kline, maintaining a max length of 100."""
        self.mtf_klines.append(kline)
        if len(self.mtf_klines) > 100:
            self.mtf_klines.pop(0)

    def build_context(self, book_metrics: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Builds the market context dictionary to be sent to the AI model.
        Uses the vectorized TA functions.
        """
        if len(self.klines) < 100:
            return None

        # Convert to numpy arrays for TA functions
        k_np = self._klines_to_numpy(self.klines)
        h, l, c, v = k_np['high'], k_np['low'], k_np['close'], k_np['volume']

        atr_series = ta.atr(h, l, c, period=14)
        atr_val = atr_series[-1] if atr_series.size > 0 and not np.isnan(atr_series[-1]) else 1.0

        fisher_series = ta.fisher(h, l, period=9)
        fisher_val = fisher_series[-1] if fisher_series.size > 0 and not np.isnan(fisher_series[-1]) else 0.0

        vwap_val = ta.vwap(h, l, c, v)
        if vwap_val is None:
             vwap_val = c[-1] # Fallback to last close price

        # Fast Trend (MTF)
        fast_trend = 'NEUTRAL'
        if len(self.mtf_klines) > 20:
            mtf_c = self._klines_to_numpy(self.mtf_klines)['close']
            sma20 = np.mean(mtf_c[-20:])
            fast_trend = 'BULLISH' if mtf_c[-1] > sma20 else 'BEARISH'

        return {
            "price": c[-1],
            "atr": round(float(atr_val), 2),
            "vwap": round(float(vwap_val), 2),
            "fisher": round(float(np.clip(fisher_val, -5, 5)), 3),
            "fastTrend": fast_trend,
            "book": {
                "skew": round(book_metrics.get('skew', 0.0), 3),
                "wallStatus": book_metrics.get('wall_status', 'N/A')
            }
        }

    def _validate_signal(self, signal: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitizes and validates the signal received from the AI."""
        if not isinstance(signal, dict):
            return {"action": "HOLD", "confidence": 0, "reason": "Invalid JSON response"}

        action = signal.get("action")
        if action not in ["BUY", "SELL", "HOLD"]:
            signal["action"] = "HOLD"

        confidence = signal.get("confidence", 0)
        if not isinstance(confidence, (int, float)) or confidence < 0.89:
            signal["action"] = "HOLD"
            signal["confidence"] = 0
        
        signal["reason"] = str(signal.get("reason", "No reason provided"))[:100]

        if signal["action"] != 'HOLD':
            price = context.get('price', 0)
            atr_val = context.get('atr', 100)
            sl = float(signal.get('sl', price))
            tp = float(signal.get('tp', price))
            max_dist = atr_val * 4

            signal['sl'] = round(np.clip(sl, price - max_dist, price + max_dist), 2)
            signal['tp'] = round(np.clip(tp, price - max_dist, price + max_dist), 2)
        
        return signal

    async def divine(self, book_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Queries the AI model with the current market context to get a trading decision.
        """
        context = self.build_context(book_metrics)
        if not context:
            return {"action": "HOLD", "confidence": 0, "reason": "Warming up"}

        prompt = f"""You are LEVIATHAN v2.9 QUANTUM.
Price: {context['price']} | ATR: {context['atr']} | Fisher: {context['fisher']} | VWAP: {context['vwap']}
Orderbook Skew: {context['book']['skew']}
Wall Status: {context['book']['wallStatus']}
Fast Trend (1m): {context['fastTrend']}

RULES:
1. Signal BUY if Fisher < -1.5 AND Skew > 0.1 AND (Price < VWAP or FastTrend == BULLISH).
2. Signal SELL if Fisher > 1.5 AND Skew < -0.1 AND (Price > VWAP or FastTrend == BEARISH).
3. \"ASK_WALL_BROKEN\" is a strong BUY signal. \"BID_WALL_BROKEN\" is a strong SELL signal.
4. Confidence > 0.89 required.
5. R/R must be > 1.6.

DATA:
{json.dumps(context)}

Output JSON: {{"action":"BUY"|"SELL"|"HOLD","confidence":0.90,"sl":123,"tp":456,"reason":"concise reason"}}"""

        try:
            response = await self.model.generate_content_async(prompt)
            # The API returns a response object, and we need to access the text part.
            # Assuming the response is directly a parsable JSON string in its text property.
            raw_text = response.text
            raw_text = raw_text.replace("```json", "").replace("```", "").strip()
            signal = json.loads(raw_text)

            # Enforce R/R ratio if a trade is signaled
            if signal.get("action") in ["BUY", "SELL"]:
                price = context['price']
                sl = float(signal.get('sl', price))
                tp = float(signal.get('tp', price))
                
                risk = abs(price - sl)
                reward = abs(tp - price)
                
                if risk > 0 and (reward / risk) < 1.6:
                    new_tp = price + (risk * 1.6) if signal["action"] == "BUY" else price - (risk * 1.6)
                    signal['tp'] = round(new_tp, 2)
                    signal['reason'] = signal.get('reason', '') + ' | R/R Enforced'

            return self._validate_signal(signal, context)
            
        except Exception as e:
            # logging.error(f"Oracle Error: {e}\nRaw Response: {getattr(response, 'text', 'N/A')}")
            return {"action": "HOLD", "confidence": 0, "reason": f"Oracle Error: {e}"}
