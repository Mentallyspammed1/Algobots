# app.py
import os
import json
import time
import google.generativeai as genai
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import logging

# --- Configuration ---
load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Gemini API Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logging.error("GEMINI_API_KEY not found. Please set it in your .env file.")
    raise ValueError("GEMINI_API_KEY not found. Please set it in your .env file.")
genai.configure(api_key=GEMINI_API_KEY)

# Choose a suitable Gemini model
# 'gemini-1.5-flash' is generally faster and cheaper for this task
# 'gemini-1.5-pro' or 'gemini-1.0-pro' might offer deeper analysis
MODEL_NAME = 'gemini-1.5-flash' 
try:
    model = genai.GenerativeModel(MODEL_NAME)
    logging.info(f"Successfully configured Gemini model: {MODEL_NAME}")
except Exception as e:
    logging.error(f"Failed to load Gemini model '{MODEL_NAME}': {e}")
    raise

# Bybit API Base URL from environment
BYBIT_API_BASE = os.getenv("BYBIT_API_BASE_URL", 'https://api.bybit.com/v5/market/')
if not BYBIT_API_BASE:
    logging.warning("BYBIT_API_BASE_URL not found in .env, using default.")

# --- Caching (Simple In-Memory Cache for Bybit API calls) ---
# In a production environment, consider Redis or Memcached for better scalability
BYBIT_CACHE = {}
CACHE_TTL_SECONDS = 300  # Cache Bybit API responses for 5 minutes

def get_from_bybit_cache(key):
    if key in BYBIT_CACHE:
        if time.time() < BYBIT_CACHE[key]['expiry']:
            logging.debug(f"Cache hit for {key}")
            return BYBIT_CACHE[key]['data']
        else:
            logging.debug(f"Cache expired for {key}")
            del BYBIT_CACHE[key]
    logging.debug(f"Cache miss for {key}")
    return None

def set_to_bybit_cache(key, data):
    BYBIT_CACHE[key] = {'data': data, 'expiry': time.time() + CACHE_TTL_SECONDS}

# --- Helper Functions ---
def format_klines_for_gemini(klines_raw):
    """
    Formats kline data for clarity in Gemini prompt.
    Expects raw kline data from Bybit API: [timestamp, open, high, low, close, volume, ...] 
    """
    formatted = []
    if not klines_raw:
        return formatted

    # Ensure klines_raw is a list of lists/tuples
    if not isinstance(klines_raw, list) or (len(klines_raw) > 0 and not isinstance(klines_raw[0], (list, tuple))):
        logging.error("Invalid klines format provided to format_klines_for_gemini")
        return []
        
    for kline in klines_raw:
        if len(kline) >= 6:
            try:
                # Bybit kline format: [timestamp, open, high, low, close, volume, turnover]
                timestamp_ms = int(kline[0])
                # Convert ms to seconds for easier Python datetime handling, or keep as ms if frontend uses it
                # Assuming frontend uses milliseconds for Date objects, so keep as ms
                formatted.append({
                    "time": timestamp_ms,
                    "open": float(kline[1]),
                    "high": float(kline[2]),
                    "low": float(kline[3]),
                    "close": float(kline[4]),
                    "volume": float(kline[5])
                })
            except (ValueError, TypeError) as e:
                logging.warning(f"Skipping invalid kline data: {kline} - {e}")
    return formatted

def format_indicators_for_gemini(indicators_raw):
    """
    Formats indicator data for Gemini.
    Expects a dictionary of indicator arrays. Only sends the last value.
    Handles complex structures like MACD, Bollinger Bands, Supertrend, Ichimoku.
    """
    formatted = {}
    if not indicators_raw:
        return formatted

    for indicator_name, values in indicators_raw.items():
        if not isinstance(values, (list, dict)) or len(values) == 0:
            continue

        last_value = values[-1] if isinstance(values, list) else None
        
        if isinstance(last_value, (int, float)):
            formatted[indicator_name] = f"{last_value:.6f}" # Use sufficient precision
        elif isinstance(last_value, dict): # For complex objects like Ichimoku, MACD, BB, ST
            if indicator_name == 'macd':
                if 'macdLine' in last_value and 'signalLine' in last_value and 'histogram' in last_value:
                    formatted[indicator_name] = {
                        "macdLine": f"{last_value['macdLine']:.6f}" if last_value['macdLine'] is not None else "N/A",
                        "signalLine": f"{last_value['signalLine']:.6f}" if last_value['signalLine'] is not None else "N/A",
                        "histogram": f"{last_value['histogram']:.6f}" if last_value['histogram'] is not None else "N/A"
                    }
            elif indicator_name == 'bollinger':
                if 'upper' in last_value and 'middle' in last_value and 'lower' in last_value:
                    formatted[indicator_name] = {
                        "upper": f"{last_value['upper']:.6f}" if last_value['upper'] is not None else "N/A",
                        "middle": f"{last_value['middle']:.6f}" if last_value['middle'] is not None else "N/A",
                        "lower": f"{last_value['lower']:.6f}" if last_value['lower'] is not None else "N/A"
                    }
            elif indicator_name == 'supertrend':
                if 'line' in last_value and 'trend' in last_value:
                    formatted[indicator_name] = {
                        "line": f"{last_value['line']:.6f}" if last_value['line'] is not None else "N/A",
                        "trend": "Up" if last_value['trend'] else "Down"
                    }
            elif indicator_name == 'ichimoku':
                if 'tenkan' in last_value and 'kijun' in last_value and 'senkouA' in last_value and 'senkouB' in last_value and 'chikou' in last_value:
                     formatted[indicator_name] = {
                        "tenkan": f"{last_value['tenkan']:.6f}" if last_value['tenkan'] is not None else "N/A",
                        "kijun": f"{last_value['kijun']:.6f}" if last_value['kijun'] is not None else "N/A",
                        "senkouA": f"{last_value['senkouA']:.6f}" if last_value['senkouA'] is not None else "N/A",
                        "senkouB": f"{last_value['senkouB']:.6f}" if last_value['senkouB'] is not None else "N/A",
                        "chikou": f"{last_value['chikou']:.6f}" if last_value['chikou'] is not None else "N/A"
                    }
            # Add other complex indicator formatting here if needed
        elif isinstance(last_value, (str, bool)): # e.g., Supertrend trend boolean
             formatted[indicator_name] = str(last_value)
        else:
            formatted[indicator_name] = str(last_value)
            
    return formatted

def format_signals_for_gemini(signals_raw):
    """
    Formats generated signals for Gemini.
    Expects a list of signal objects.
    """
    formatted = []
    if not signals_raw:
        return formatted

    for signal in signals_raw:
        try:
            formatted.append({
                "type": signal.get("type", "N/A"),
                "strength": signal.get("strength", 0),
                "direction": signal.get("direction", "neutral")
            })
        except Exception as e:
            logging.warning(f"Skipping invalid signal data: {signal} - {e}")
    return formatted

def construct_gemini_prompt(symbol, interval, klines_data, indicators_data, signals_data):
    """
    Constructs a detailed and structured prompt for the Gemini API.
    """
    # Convert klines to a more readable format for the prompt
    readable_klines = []
    for k in klines_data:
        try:
            readable_klines.append(f"- Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(k['time'] / 1000))}, "
                                   f"Open: {k['open']:.4f}, High: {k['high']:.4f}, Low: {k['low']:.4f}, "
                                   f"Close: {k['close']:.4f}, Volume: {k['volume']:.0f}")
        except (ValueError, TypeError) as e:
            logging.warning(f"Could not format kline for prompt: {k} - {e}")

    # Format indicators clearly
    readable_indicators = []
    for name, value in indicators_data.items():
        if isinstance(value, dict):
            # Handle nested dictionaries (e.g., MACD, Bollinger, Ichimoku)
            details = ", ".join([f"{k.replace('_', ' ').title()}: {v}" for k, v in value.items()])
            readable_indicators.append(f"- {name.replace('_', ' ').title()}: {details}")
        else:
            readable_indicators.append(f"- {name.replace('_', ' ').title()}: {value}")
            
    # Format signals clearly
    readable_signals = []
    if signals_data:
        for signal in signals_data:
            readable_signals.append(f"- Type: {signal.get('type', 'N/A')}, "
                                    f"Strength: {signal.get('strength', 'N/A')}, "
                                    f"Direction: {signal.get('direction', 'N/A')}")
    else:
        readable_signals.append("No specific trading signals detected.")

    prompt_parts = [
        f"**Trading Analysis Request:**",
        f"Symbol: `{symbol}`",
        f"Interval: `{interval}`",
        f"\n**Latest Market Data (Last 5 Candles):**",
        "\n".join(readable_klines[-5:]), # Show last 5 for context
        f"\n**Calculated Technical Indicators (Latest Values):**",
        "\n".join(readable_indicators),
        f"\n**Generated Trading Signals:**",
        "\n".join(readable_signals),
        f"\n**Gemini AI Analysis and Recommendation:**",
        "Please provide a concise trading analysis based on the provided data.",
        "Include potential reasons for the current market sentiment, key levels (support/resistance if inferable),",
        "potential risks, and a brief recommendation (e.g., 'Consider a long position', 'Cautious approach advised', 'Potential breakout ahead').",
        "Focus on how the indicators and signals collectively suggest a trading strategy.",
        "Avoid making definitive predictions; emphasize probabilities and risk management.",
        "Format the output as a clear, readable text."
    ]
    
    return "\n".join(prompt_parts)

# --- API Endpoints ---

@app.route('/')
def index():
    """Health check endpoint."""
    return "Bybit Trading Terminal Backend is running!"

@app.route('/analyze', methods=['POST'])
def analyze_signal_with_gemini():
    """
    Receives trading data from the frontend, processes it with Gemini, and returns analysis.
    """
    start_time = time.time()
    try:
        data = request.get_json()
        if not data or not isinstance(data, dict):
            logging.warning("Received invalid JSON payload for /analyze")
            return jsonify({"error": "Invalid JSON payload"}), 400

        # --- Data Validation ---
        symbol = data.get('symbol')
        interval = data.get('interval')
        klines_raw = data.get('klines') # Array of raw kline objects from Bybit API
        indicators_raw_from_frontend = data.get('indicators') # Last values of indicators
        signals_raw_from_frontend = data.get('signals') # Processed signals

        if not symbol:
            logging.warning("Missing 'symbol' in request payload")
            return jsonify({"error": "Missing required data: symbol"}), 400
        if not interval:
            logging.warning("Missing 'interval' in request payload")
            return jsonify({"error": "Missing required data: interval"}), 400
        if not klines_raw or not isinstance(klines_raw, list) or len(klines_raw) == 0:
            logging.warning(f"Missing or empty 'klines' data for {symbol}")
            return jsonify({"error": "Missing or empty required data: klines"}), 400
        # Allow empty indicators/signals if they are not the primary focus of Gemini analysis
        if indicators_raw_from_frontend is None: indicators_raw_from_frontend = {}
        if signals_raw_from_frontend is None: signals_raw_from_frontend = []
        
        logging.info(f"Received analysis request for {symbol} ({interval}) with {len(klines_raw)} klines.")

        # --- Data Formatting for Gemini ---
        # Re-format indicators to ensure consistent structure and precision
        formatted_indicators = format_indicators_for_gemini(indicators_raw_from_frontend)
        formatted_signals = format_signals_for_gemini(signals_raw_from_frontend)
        
        # Gemini needs more than just the last few klines for context, so we might need to fetch more data here if frontend sends too little.
        # However, for now, we trust the frontend sends enough (e.g., last 10-20 klines for context).
        # If klines_raw is too short, Gemini might struggle.
        if len(klines_raw) < 5:
            logging.warning(f"Received only {len(klines_raw)} klines for {symbol}. Gemini analysis might be limited.")

        # --- Gemini API Call ---
        prompt = construct_gemini_prompt(symbol, interval, klines_raw, formatted_indicators, formatted_signals)
        logging.debug(f"Constructed Gemini prompt:\n{prompt[:500]}...") # Log first 500 chars for debugging

        try:
            gemini_response = model.generate_content(prompt)
            analysis_text = gemini_response.text
            
            if not analysis_text or analysis_text.strip().lower().startswith("i cannot fulfill this request"):
                logging.warning(f"Gemini returned an empty or refusal response for {symbol}.")
                analysis_text = "Gemini could not provide an analysis for this data. Please try again later or with different parameters."

        except Exception as e:
            logging.error(f"Error calling Gemini API for {symbol}: {e}")
            return jsonify({"error": f"Failed to get analysis from Gemini API: {str(e)}"}), 500

        end_time = time.time()
        logging.info(f"Gemini analysis for {symbol} completed in {end_time - start_time:.2f} seconds.")
        return jsonify({"analysis": analysis_text})

    except Exception as e:
        logging.exception(f"An unexpected error occurred in /analyze: {e}") # Log full traceback
        return jsonify({"error": f"An unexpected server error occurred: {str(e)}"}), 500

# --- Bybit Data Fetching (Optional: if backend should fetch data too) ---
# This example assumes frontend fetches data from Bybit directly.
# If backend were to fetch, add routes for 'kline', 'tickers', 'instruments-info'
# and implement caching here.

# --- Error Handling Middleware ---
@app.errorhandler(404)
def not_found_error(error):
    return jsonify({"error": "Resource not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    logging.exception("An unhandled exception occurred.")
    return jsonify({"error": "An internal server error occurred"}), 500

# --- Main Execution ---
if __name__ == '__main__':
    logging.info("Starting Bybit Trading Terminal Backend...")
    # Use a production-ready WSGI server like Gunicorn for deployment
    # Example: gunicorn -w 4 -b 0.0.0.0:5000 app:app
    app.run(host='0.0.0.0', port=5000, debug=False) # Set debug=False for production