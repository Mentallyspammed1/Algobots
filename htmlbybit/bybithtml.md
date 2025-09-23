This is a fantastic request! Let's break down the existing code, identify areas for enhancement, and then provide a complete, upgraded version.

## Analysis of Current Code

The provided code is a solid foundation for a trading terminal. It features:

*   **Aesthetically Pleasing UI**: Modern design with CSS variables, gradients, and animations.
*   **Real-time Data Display**: Includes live price updates (via placeholder).
*   **Chart Integration**: Uses `chart.js` with financial charting extensions.
*   **Technical Indicators**: Implements several common indicators (SMA, EMA, RSI, MACD, Bollinger Bands, Supertrend, VWAP, PSAR, Ichimoku).
*   **Trading Signals**: Generates basic buy/sell signals based on indicator crossovers.
*   **UI Controls**: Symbol search, interval selection, data point limit, indicator toggles, presets, settings saving/loading.
*   **WebSocket**: Basic implementation for live price updates and chart data.
*   **Basic Backend Communication**: Placeholder for sending data to a backend (though the backend itself was not provided in the initial HTML).

### Areas for Upgrade and Enhancement:

1.  **Gemini API Integration (Backend & Frontend)**: This is the primary goal. We need a backend endpoint to receive data, process it with Gemini, and return insights.
2.  **Backend Robustness & Scalability**:
    *   **API Key Management**: Use environment variables.
    *   **Error Handling**: More detailed error responses.
    *   **Caching**: Cache Bybit API responses to reduce redundant calls and improve performance.
    *   **Production Readiness**: Use a proper WSGI server for production.
3.  **Frontend Improvements**:
    *   **Indicator Calculation**: Ensure all indicators are correctly calculated and formatted for the backend.
    *   **Data Payload for Gemini**: The data sent to Gemini should be structured and informative.
    *   **UI for Gemini Analysis**: Clear display of Gemini's insights.
    *   **WebSocket Reconnection**: Implement a more robust WebSocket reconnection strategy.
    *   **Chart Plugin Management**: Ensure `chartjs-plugin-zoom` is correctly initialized.
    *   **Loading States**: Improve feedback during data fetching and analysis.
    *   **Notifications**: Enhance the notification system.
    *   **Code Structure**: Refactor JavaScript for better maintainability (e.g., separate indicator calculations).
    *   **Input Validation**: More robust validation for input fields.
    *   **User Experience**: Smooth transitions, better feedback loops.
4.  **Security**: Ensure API keys are handled securely.
5.  **Gemini Prompt Engineering**: The prompt sent to Gemini can be refined for more specific and actionable insights.

---

## Upgraded and Enhanced Code

This section will provide the complete, improved code for both the backend and frontend.

---

### **Part 1: Backend (Python with Flask)**

This backend will handle requests from the frontend, process them, interact with the Gemini API, and return the analysis.

**1. Project Structure:**

```
trading-terminal/
├── .env
├── app.py
└── requirements.txt
```

**2. `requirements.txt`:**

```
Flask>=2.3.0
Flask-Cors>=4.0.0
google-generativeai>=0.6.0
python-dotenv>=1.0.0
requests # For potential future use or if Bybit API calls are made here
```

**3. `.env` file:**

```
GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE
BYBIT_API_BASE_URL=https://api.bybit.com/v5/market/
```
*Replace `YOUR_GEMINI_API_KEY_HERE` with your actual API key.*

**4. `app.py`:**

```python
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
            formatted[indicator_name] = str(last_value) # Fallback for unhandled types
            
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
```

---

### **Part 2: Frontend (HTML & JavaScript)**

This is the complete `index.html` file with all the JavaScript logic.

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bybit Pro Trading Terminal</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary-bg: #0a0a1a;
            --secondary-bg: #13132b;
            --tertiary-bg: #1a1a3a;
            --quaternary-bg: #22224a;
            --primary-text: #e0e0ff;
            --secondary-text: #a0a0ff;
            --accent-cyan: #00ffff;
            --accent-green: #00ff88;
            --accent-pink: #ff0088;
            --accent-orange: #ff8800;
            --accent-purple: #8800ff;
            --border-color: #4444aa;
            --success-color: #00ff88;
            --danger-color: #ff0088;
            --warning-color: #ffaa00;
            --chart-background: #181830; /* Darker for chart */
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            background: linear-gradient(135deg, var(--primary-bg) 0%, var(--secondary-bg) 100%);
            color: var(--primary-text);
            line-height: 1.6;
            min-height: 100vh;
            overflow-x: hidden;
            scroll-behavior: smooth;
        }

        .container {
            max-width: 1800px;
            margin: 15px auto;
            background-color: var(--secondary-bg);
            padding: 20px;
            border-radius: 15px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.5), 0 0 20px rgba(68, 68, 170, 0.2);
            border: 2px solid var(--border-color);
            backdrop-filter: blur(10px);
        }

        h1 {
            text-align: center;
            color: var(--accent-cyan);
            text-shadow: 0 0 10px var(--accent-cyan), 0 0 20px var(--accent-cyan);
            margin-bottom: 25px;
            font-size: 2.5em;
            font-weight: 700;
            letter-spacing: 1px;
            animation: glow 2s ease-in-out infinite alternate;
        }

        @keyframes glow {
            from { text-shadow: 0 0 10px var(--accent-cyan), 0 0 20px var(--accent-cyan); }
            to { text-shadow: 0 0 15px var(--accent-cyan), 0 0 30px var(--accent-cyan); }
        }

        .controls {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 15px;
            margin-bottom: 25px;
            padding: 20px;
            background: linear-gradient(135deg, var(--quaternary-bg) 0%, var(--tertiary-bg) 100%);
            border-radius: 10px;
            border: 1px solid var(--border-color);
            box-shadow: inset 0 2px 10px rgba(0, 0, 0, 0.2);
        }

        .control-group {
            display: flex;
            flex-direction: column;
            min-width: 150px;
            animation: fadeIn 0.5s ease-out;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        label {
            margin-bottom: 5px;
            font-size: 0.85em;
            color: var(--secondary-text);
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        input[type="number"],
        select,
        input[type="text"] {
            padding: 10px;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            background: linear-gradient(135deg, var(--tertiary-bg) 0%, rgba(26, 26, 58, 0.8) 100%);
            color: var(--primary-text);
            font-size: 1em;
            min-width: 120px;
            transition: all 0.3s ease;
            box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.3);
        }

        input[type="number"]:focus,
        select:focus,
        input[type="text"]:focus {
            outline: none;
            box-shadow: 0 0 10px var(--accent-cyan), inset 0 1px 3px rgba(0, 0, 0, 0.3);
            border-color: var(--accent-cyan);
            transform: translateY(-1px);
        }

        /* Enhanced Symbol Search */
        .symbol-search-container {
            position: relative;
            grid-column: span 2;
        }

        #symbolSearch {
            width: 100%;
            padding: 12px;
            padding-left: 40px;
            font-size: 1.1em;
        }

        .search-icon {
            position: absolute;
            left: 12px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--secondary-text);
            pointer-events: none;
            z-index: 1;
        }

        .symbol-dropdown {
            position: absolute;
            top: 100%;
            left: 0;
            right: 0;
            max-height: 300px;
            overflow-y: auto;
            background: var(--tertiary-bg);
            border: 1px solid var(--border-color);
            border-top: none;
            border-radius: 0 0 8px 8px;
            display: none;
            z-index: 1000;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
        }

        .symbol-dropdown.active {
            display: block;
        }

        .symbol-item {
            padding: 10px 15px;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(68, 68, 170, 0.1);
        }

        .symbol-item:hover {
            background: rgba(0, 255, 255, 0.1);
            padding-left: 20px;
        }

        .symbol-item.selected {
            background: rgba(0, 255, 255, 0.2);
            font-weight: bold;
        }

        .symbol-info {
            font-size: 0.8em;
            color: var(--secondary-text);
        }

        button {
            padding: 12px 24px;
            background: linear-gradient(135deg, var(--accent-pink) 0%, #cc0066 100%);
            color: var(--primary-text);
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1em;
            font-weight: 600;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(255, 0, 136, 0.3);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            grid-column: span 2;
        }

        button:hover:not(:disabled) {
            background: linear-gradient(135deg, #cc0066 0%, var(--accent-pink) 100%);
            box-shadow: 0 6px 20px rgba(255, 0, 136, 0.5);
            transform: translateY(-2px);
        }

        button:active:not(:disabled) {
            transform: translateY(0);
            box-shadow: 0 2px 10px rgba(255, 0, 136, 0.3);
        }

        button:disabled {
            background: linear-gradient(135deg, #5f5f5f 0%, #3f3f3f 100%);
            cursor: not-allowed;
            box-shadow: none;
            opacity: 0.7;
        }

        .action-buttons {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 10px;
            margin-top: 15px;
        }

        .action-button {
            padding: 8px 16px;
            font-size: 0.9em;
            grid-column: span 1;
        }

        #chartContainer {
            position: relative;
            height: 70vh;
            min-height: 500px;
            width: 100%;
            background: var(--chart-background); /* Using chart background variable */
            border-radius: 10px;
            padding: 15px;
            box-sizing: border-box;
            border: 2px solid var(--border-color);
            margin-bottom: 20px;
            box-shadow: 0 5px 20px rgba(0, 0, 0, 0.3), inset 0 1px 3px rgba(0, 0, 0, 0.2);
        }

        #chartCanvas {
            max-height: 100%;
            max-width: 100%;
        }

        .loading-overlay {
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(10, 10, 26, 0.95);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            z-index: 100;
            border-radius: 10px;
            display: none;
        }

        .loading-overlay.active {
            display: flex;
        }

        .spinner {
            width: 60px;
            height: 60px;
            border: 4px solid rgba(0, 255, 255, 0.1);
            border-radius: 50%;
            border-top: 4px solid var(--accent-cyan);
            animation: spin 1s linear infinite;
            margin-bottom: 20px;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .loading-text {
            color: var(--accent-cyan);
            font-size: 1.2em;
            text-shadow: 0 0 10px var(--accent-cyan);
            animation: pulse 1.5s ease-in-out infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        .message {
            padding: 15px;
            margin: 15px 0;
            border-radius: 8px;
            font-size: 1.05em;
            display: none;
            animation: slideIn 0.3s ease-out;
        }

        @keyframes slideIn {
            from { transform: translateX(-100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }

        .error-message {
            background: linear-gradient(135deg, rgba(255, 0, 136, 0.2) 0%, rgba(255, 0, 136, 0.1) 100%);
            border: 1px solid var(--danger-color);
            color: var(--danger-color);
            box-shadow: 0 0 10px rgba(255, 0, 136, 0.3);
        }

        .success-message {
            background: linear-gradient(135deg, rgba(0, 255, 136, 0.2) 0%, rgba(0, 255, 136, 0.1) 100%);
            border: 1px solid var(--success-color);
            color: var(--success-color);
            box-shadow: 0 0 10px rgba(0, 255, 136, 0.3);
        }

        .warning-message {
            background: linear-gradient(135deg, rgba(255, 170, 0, 0.2) 0%, rgba(255, 170, 0, 0.1) 100%);
            border: 1px solid var(--warning-color);
            color: var(--warning-color);
            box-shadow: 0 0 10px rgba(255, 170, 0, 0.3);
        }

        .ticker-info {
            margin-top: 20px;
            padding: 20px;
            background: linear-gradient(135deg, var(--tertiary-bg) 0%, rgba(26, 26, 58, 0.8) 100%);
            border-radius: 10px;
            border: 1px solid var(--border-color);
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
            transition: all 0.3s ease;
        }

        .ticker-info:hover {
            box-shadow: 0 6px 25px rgba(68, 68, 170, 0.4);
            transform: translateY(-2px);
        }

        .ticker-info h3 {
            margin-top: 0;
            margin-bottom: 20px;
            color: var(--accent-cyan);
            text-align: center;
            font-size: 1.4em;
            text-shadow: 0 0 5px var(--accent-cyan);
        }
        
        .live-price-box {
            background: linear-gradient(135deg, var(--quaternary-bg) 0%, var(--tertiary-bg) 100%);
            border-radius: 10px;
            border: 1px solid var(--border-color);
            padding: 15px;
            margin-bottom: 20px;
            text-align: center;
        }

        .live-price-box .price-value {
            font-size: 2.5em;
            font-weight: bold;
            color: var(--accent-green);
            text-shadow: 0 0 10px var(--accent-green);
            transition: color 0.5s ease-in-out;
        }
        
        .live-price-box .last-update {
            font-size: 0.8em;
            color: var(--secondary-text);
            margin-top: 5px;
        }

        .ticker-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 15px;
        }

        .ticker-item {
            display: flex;
            flex-direction: column;
            padding: 12px;
            background: linear-gradient(135deg, rgba(34, 34, 74, 0.5) 0%, rgba(26, 26, 58, 0.5) 100%);
            border-radius: 8px;
            border: 1px solid rgba(68, 68, 170, 0.3);
            transition: all 0.3s ease;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
        }

        .ticker-item:hover {
            background: linear-gradient(135deg, rgba(34, 34, 74, 0.7) 0%, rgba(26, 26, 58, 0.7) 100%);
            transform: translateY(-3px);
            box-shadow: 0 5px 15px rgba(68, 68, 170, 0.3);
        }

        .ticker-label {
            font-size: 0.75em;
            color: var(--secondary-text);
            margin-bottom: 6px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .ticker-value {
            font-weight: bold;
            font-size: 1.2em;
            transition: all 0.3s ease;
        }

        .ticker-value.positive {
            color: var(--accent-green);
            text-shadow: 0 0 5px var(--accent-green);
        }

        .ticker-value.negative {
            color: var(--accent-pink);
            text-shadow: 0 0 5px var(--accent-pink);
        }

        .indicator-controls {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 12px;
            margin-top: 20px;
            padding: 15px;
            background: linear-gradient(135deg, var(--quaternary-bg) 0%, var(--tertiary-bg) 100%);
            border-radius: 10px;
            border: 1px solid var(--border-color);
            box-shadow: inset 0 2px 10px rgba(0, 0, 0, 0.2);
        }

        .indicator-toggle {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 12px;
            background: rgba(26, 26, 58, 0.5);
            border-radius: 6px;
            transition: all 0.2s ease;
            cursor: pointer;
        }

        .indicator-toggle:hover {
            background: rgba(0, 255, 255, 0.1);
        }

        .indicator-toggle input[type="checkbox"] {
            width: 18px;
            height: 18px;
            cursor: pointer;
            accent-color: var(--accent-cyan); /* Custom checkbox color */
        }

        .indicator-toggle label {
            cursor: pointer;
            margin: 0;
            color: var(--primary-text);
            font-size: 0.9em;
        }

        .stats-container {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-top: 25px;
        }

        .stat-card {
            background: linear-gradient(135deg, var(--tertiary-bg) 0%, rgba(26, 26, 58, 0.8) 100%);
            border-radius: 10px;
            padding: 20px;
            border: 1px solid var(--border-color);
            text-align: center;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }

        .stat-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(0, 255, 255, 0.1), transparent);
            transition: left 0.5s ease;
        }

        .stat-card:hover::before {
            left: 100%;
        }

        .stat-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 8px 25px rgba(68, 68, 170, 0.4);
        }

        .stat-title {
            color: var(--secondary-text);
            font-size: 0.85em;
            margin-bottom: 10px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .stat-value {
            font-size: 1.8em;
            font-weight: bold;
            color: var(--primary-text);
            text-shadow: 0 0 5px rgba(224, 224, 255, 0.5);
            transition: color 0.5s ease;
        }
        
        .stat-value.positive { color: var(--accent-green); }
        .stat-value.negative { color: var(--accent-pink); }
        .stat-value.neutral { color: var(--secondary-text); }


        .tab-container {
            margin-top: 25px;
        }

        .tab-buttons {
            display: flex;
            gap: 5px;
            margin-bottom: 15px;
            background: rgba(26, 26, 58, 0.5);
            border-radius: 10px;
            padding: 5px;
            flex-wrap: wrap; /* Allow wrapping on smaller screens */
        }

        .tab-button {
            flex: 1;
            min-width: 120px; /* Ensure minimum width */
            padding: 10px;
            background: transparent;
            color: var(--primary-text);
            border: none;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.3s ease;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            text-align: center;
        }

        .tab-button:hover {
            background: rgba(0, 255, 255, 0.1);
        }

        .tab-button.active {
            background: linear-gradient(135deg, var(--accent-cyan) 0%, var(--accent-purple) 100%);
            color: white;
            font-weight: bold;
            box-shadow: 0 2px 10px rgba(0, 255, 255, 0.3);
        }

        .tab-content {
            display: none;
            padding: 20px;
            background: linear-gradient(135deg, var(--tertiary-bg) 0%, rgba(26, 26, 58, 0.8) 100%);
            border-radius: 10px;
            border: 1px solid var(--border-color);
            animation: fadeIn 0.5s ease-out;
        }

        .tab-content.active {
            display: block;
        }
        
        #signals-tab .signals-list {
            display: flex;
            flex-direction: column;
            gap: 10px;
        }

        #signals-tab .signal-item {
            background: rgba(34, 34, 74, 0.5);
            border-radius: 6px;
            padding: 10px;
            border-left: 3px solid;
            display: grid;
            grid-template-columns: 1fr auto;
            align-items: center;
            gap: 10px; /* Gap between info and strength */
        }

        #signals-tab .signal-item.buy {
            border-color: var(--accent-green);
        }
        
        #signals-tab .signal-item.sell {
            border-color: var(--accent-pink);
        }
        
        #signals-tab .signal-item .signal-info {
            font-size: 0.9em;
            line-height: 1.4;
        }
        
        #signals-tab .signal-item .signal-time {
            font-size: 0.8em;
            color: var(--secondary-text);
            display: block; /* Ensure time is on a new line or fits well */
            margin-top: 4px;
        }
        
        #signals-tab .signal-strength {
            font-weight: bold;
            padding: 5px 10px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
            white-space: nowrap; /* Prevent breaking */
        }
        
        /* Gemini Analysis Tab Specific Styles */
        #gemini-analysis-tab .stat-card {
            background: linear-gradient(135deg, rgba(0, 100, 150, 0.1) 0%, rgba(0, 255, 255, 0.1) 100%);
            border-color: var(--accent-cyan);
        }
        #gemini-analysis-tab .stat-card .stat-title { color: var(--accent-cyan); }
        #gemini-analysis-tab .stat-card .stat-value { font-size: 1.1em; font-weight: normal; text-align: left; }
        #gemini-analysis-tab .stat-card .stat-value p { margin-bottom: 1em; }
        #gemini-analysis-tab .stat-card .stat-value strong { color: var(--accent-green); }
        #gemini-analysis-tab .stat-card .stat-value em { color: var(--accent-pink); font-style: normal;} /* Style for risk/caution */

        .preset-buttons {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 10px;
            margin-top: 15px;
        }

        .preset-button {
            padding: 10px;
            background: linear-gradient(135deg, var(--tertiary-bg) 0%, rgba(26, 26, 58, 0.8) 100%);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            color: var(--primary-text);
            cursor: pointer;
            transition: all 0.3s ease;
            font-size: 0.9em;
        }

        .preset-button:hover {
            background: linear-gradient(135deg, var(--accent-purple) 0%, var(--accent-cyan) 100%);
            box-shadow: 0 4px 15px rgba(136, 0, 255, 0.4);
            transform: translateY(-2px);
        }

        /* Notification System */
        .notification-container {
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 10000;
            max-width: 350px;
            display: flex;
            flex-direction: column;
            align-items: flex-end; /* Align notifications to the right */
        }

        .notification {
            background: linear-gradient(135deg, var(--tertiary-bg) 0%, rgba(26, 26, 58, 0.95) 100%);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 10px;
            box-shadow: 0 5px 20px rgba(0, 0, 0, 0.5);
            animation: slideInRight 0.3s ease-out;
            position: relative;
            overflow: hidden;
            width: 100%; /* Take full width of container */
        }

        @keyframes slideInRight {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }

        .notification-progress {
            position: absolute;
            bottom: 0;
            left: 0;
            height: 3px;
            background: var(--accent-cyan);
            animation: progressBar 3s linear forwards; /* Default duration */
        }

        @keyframes progressBar {
            from { width: 100%; }
            to { width: 0%; }
        }

        .notification.success .notification-progress { background: var(--success-color); }
        .notification.error .notification-progress { background: var(--danger-color); }
        .notification.warning .notification-progress { background: var(--warning-color); }

        .notification.success { border-color: var(--success-color); }
        .notification.error { border-color: var(--danger-color); }
        .notification.warning { border-color: var(--warning-color); }
        .notification.info { border-color: var(--accent-cyan); }


        .notification-title {
            font-weight: bold;
            margin-bottom: 5px;
            color: var(--primary-text);
        }
        .notification.success .notification-title { color: var(--success-color); }
        .notification.error .notification-title { color: var(--danger-color); }
        .notification.warning .notification-title { color: var(--warning-color); }
        .notification.info .notification-title { color: var(--accent-cyan); }


        .notification-message {
            font-size: 0.9em;
            color: var(--secondary-text);
        }

        /* Responsive design improvements */
        @media (max-width: 1200px) {
            .container {
                margin: 10px;
                padding: 15px;
            }
            h1 {
                font-size: 2em;
            }
            #chartContainer {
                min-height: 400px;
            }
        }

        @media (max-width: 768px) {
            .controls {
                grid-template-columns: 1fr;
            }
            
            .symbol-search-container {
                grid-column: span 1;
            }
            
            button {
                grid-column: span 1;
            }
            
            .ticker-grid {
                grid-template-columns: repeat(2, 1fr);
            }
            
            .indicator-controls {
                grid-template-columns: 1fr;
            }
            .tab-buttons {
                flex-direction: column; /* Stack tabs vertically */
                gap: 8px;
            }
            .tab-button {
                width: 100%; /* Full width when stacked */
            }
            #chartContainer {
                height: 50vh;
                min-height: 400px;
            }
            
            .stats-container {
                grid-template-columns: 1fr; /* Stack stats */
            }
        }
        
        @media (max-width: 480px) {
            h1 {
                font-size: 1.8em;
            }
            
            .controls {
                padding: 10px;
            }
            
            .ticker-grid {
                grid-template-columns: 1fr;
            }

            .notification-container {
                max-width: 90%; /* Smaller max width on very small screens */
                right: 10px;
                left: 10px; /* Center it */
                align-items: center; /* Center align notifications */
            }
            .notification {
                width: 100%; /* Ensure it takes available width */
            }
        }
    </style>
</head>
<body>
    <div class="notification-container" id="notificationContainer"></div>
    
    <div class="container">
        <h1>🚀 Bybit Pro Trading Terminal 📊</h1>

        <div class="message error-message" id="errorMessage"></div>
        <div class="message success-message" id="successMessage"></div>
        <div class="message warning-message" id="warningMessage"></div>
        
        <div class="live-price-box">
            <div id="livePrice">-</div>
            <div class="last-update">Last Updated: <span id="lastUpdate">-</span></div>
        </div>

        <div class="controls">
            <div class="symbol-search-container">
                <label for="symbolSearch">Search Symbol:</label>
                <div style="position: relative;">
                    <span class="search-icon">🔍</span>
                    <input type="text" id="symbolSearch" placeholder="Type to search (e.g., BTC, ETH)..." autocomplete="off">
                    <div class="symbol-dropdown" id="symbolDropdown"></div>
                </div>
            </div>
            
            <div class="control-group">
                <label for="intervalSelect">Interval:</label>
                <select id="intervalSelect">
                    <option value="1">1m</option>
                    <option value="5">5m</option>
                    <option value="15">15m</option>
                    <option value="30">30m</option>
                    <option value="60">1h</option>
                    <option value="240">4h</option>
                    <option value="D" selected>1D</option>
                    <option value="W">1W</option>
                    <option value="M">1M</option>
                </select>
            </div>
            
            <div class="control-group">
                <label for="limit">Data Points:</label>
                <input type="number" id="limit" value="200" min="50" max="1000" step="50">
            </div>
            
            <div class="control-group">
                <label for="atrPeriod">ATR Period:</label>
                <input type="number" id="atrPeriod" value="14" min="5" max="50">
            </div>
            
            <div class="control-group">
                <label for="rsiPeriod">RSI Period:</label>
                <input type="number" id="rsiPeriod" value="14" min="5" max="50">
            </div>
            
            <div class="control-group">
                <label for="emaPeriod">EMA Period:</label>
                <input type="number" id="emaPeriod" value="20" min="5" max="200">
            </div>

            <div class="control-group">
                <label for="stPeriod">Supertrend Period:</label>
                <input type="number" id="stPeriod" value="10" min="5" max="50">
            </div>
            
            <div class="control-group">
                <label for="stMultiplier">ST Multiplier:</label>
                <input type="number" id="stMultiplier" value="3" step="0.5" min="1" max="10">
            </div>
            
            <button id="fetchDataButton">📈 Load Chart</button>
            <button id="autoRefreshButton" class="action-button">🔄 Go Live</button>
        </div>

        <div class="action-buttons">
            <button class="action-button preset-button" data-preset="scalping">⚡ Scalping</button>
            <button class="action-button preset-button" data-preset="daytrading">☀️ Day Trading</button>
            <button class="action-button preset-button" data-preset="swing">🌊 Swing</button>
            <button class="action-button preset-button" data-preset="position">🎯 Position</button>
            <button class="action-button" id="saveSettingsButton">💾 Save Settings</button>
            <button class="action-button" id="resetButton">🔄 Reset</button>
        </div>

        <div class="indicator-controls">
            <div class="indicator-toggle">
                <input type="checkbox" id="toggleVolume" checked>
                <label for="toggleVolume">Volume</label>
            </div>
            <div class="indicator-toggle">
                <input type="checkbox" id="toggleSupertrend" checked>
                <label for="toggleSupertrend">Supertrend</label>
            </div>
            <div class="indicator-toggle">
                <input type="checkbox" id="toggleBollinger" checked>
                <label for="toggleBollinger">Bollinger Bands</label>
            </div>
            <div class="indicator-toggle">
                <input type="checkbox" id="toggleSMA" checked>
                <label for="toggleSMA">SMA</label>
            </div>
            <div class="indicator-toggle">
                <input type="checkbox" id="toggleEMA" checked>
                <label for="toggleEMA">EMA</label>
            </div>
            <div class="indicator-toggle">
                <input type="checkbox" id="toggleRSI" checked>
                <label for="toggleRSI">RSI</label>
            </div>
            <div class="indicator-toggle">
                <input type="checkbox" id="toggleMACD" checked>
                <label for="toggleMACD">MACD</label>
            </div>
            <div class="indicator-toggle">
                <input type="checkbox" id="toggleSignals" checked>
                <label for="toggleSignals">Buy/Sell Signals</label>
            </div>
            <div class="indicator-toggle">
                <input type="checkbox" id="toggleStochastic">
                <label for="toggleStochastic">Stochastic</label>
            </div>
            <div class="indicator-toggle">
                <input type="checkbox" id="toggleVWAP">
                <label for="toggleVWAP">VWAP</label>
            </div>
            <div class="indicator-toggle">
                <input type="checkbox" id="togglePSAR">
                <label for="togglePSAR">PSAR</label>
            </div>
            <div class="indicator-toggle">
                <input type="checkbox" id="toggleIchimoku">
                <label for="toggleIchimoku">Ichimoku</label>
            </div>
        </div>

        <div id="chartContainer">
            <canvas id="chartCanvas"></canvas>
            <div class="loading-overlay" id="loadingOverlay">
                <div class="spinner"></div>
                <div class="loading-text" id="loadingText">Loading...</div>
            </div>
        </div>

        <div class="ticker-info" id="tickerInfo" style="display: none;">
            <h3 id="tickerTitle">Market Information</h3>
            <div class="ticker-grid">
                <div class="ticker-item">
                    <span class="ticker-label">Last Price</span>
                    <span id="tickerLastPrice" class="ticker-value">-</span>
                </div>
                <div class="ticker-item">
                    <span class="ticker-label">24h Change</span>
                    <span id="tickerPriceChange" class="ticker-value">-</span>
                </div>
                <div class="ticker-item">
                    <span class="ticker-label">24h Change %</span>
                    <span id="tickerPriceChangePercent" class="ticker-value">-</span>
                </div>
                <div class="ticker-item">
                    <span class="ticker-label">24h High</span>
                    <span id="tickerHigh24h" class="ticker-value">-</span>
                </div>
                <div class="ticker-item">
                    <span class="ticker-label">24h Low</span>
                    <span id="tickerLow24h" class="ticker-value">-</span>
                </div>
                <div class="ticker-item">
                    <span class="ticker-label">24h Volume</span>
                    <span id="tickerVolume24h" class="ticker-value">-</span>
                </div>
                <div class="ticker-item">
                    <span class="ticker-label">Bid Price</span>
                    <span id="tickerBidPrice" class="ticker-value">-</span>
                </div>
                <div class="ticker-item">
                    <span class="ticker-label">Ask Price</span>
                    <span id="tickerAskPrice" class="ticker-value">-</span>
                </div>
                <div class="ticker-item">
                    <span class="ticker-label">Spread</span>
                    <span id="tickerSpread" class="ticker-value">-</span>
                </div>
            </div>
        </div>

        <div class="tab-container">
            <div class="tab-buttons">
                <button class="tab-button active" data-tab="analysis">Technical Analysis</button>
                <button class="tab-button" data-tab="signals">Trading Signals</button>
                <button class="tab-button" data-tab="statistics">Statistics</button>
                <button class="tab-button" data-tab="gemini-analysis">Gemini Analysis</button> <!-- New Tab -->
            </div>
            
            <div class="tab-content active" id="analysis-tab">
                <div class="stats-container">
                    <div class="stat-card">
                        <div class="stat-title">Trend Direction</div>
                        <div class="stat-value" id="trendDirection">-</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-title">RSI Status</div>
                        <div class="stat-value" id="rsiStatus">-</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-title">Volume Trend</div>
                        <div class="stat-value" id="volumeTrend">-</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-title">Volatility</div>
                        <div class="stat-value" id="volatility">-</div>
                    </div>
                </div>
            </div>
            
            <div class="tab-content" id="signals-tab">
                <div id="signalsContent">
                    <p>Loading trading signals...</p>
                </div>
            </div>
            
            <div class="tab-content" id="statistics-tab">
                <div class="stats-container">
                    <div class="stat-card">
                        <div class="stat-title">Average Volume</div>
                        <div class="stat-value" id="avgVolume">-</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-title">Price Range</div>
                        <div class="stat-value" id="priceRange">-</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-title">Support Level</div>
                        <div class="stat-value" id="supportLevel">-</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-title">Resistance Level</div>
                        <div class="stat-value" id="resistanceLevel">-</div>
                    </div>
                </div>
            </div>

            <!-- Gemini Analysis Tab -->
            <div class="tab-content" id="gemini-analysis-tab">
                <div class="stat-card">
                    <div class="stat-title">Gemini AI Insights</div>
                    <div class="stat-value" id="geminiAnalysisResult">
                        <p>Select a symbol and load chart data to get AI-powered insights.</p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-chart-financial@0.2.1/dist/chartjs-chart-financial.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.min.js"></script>
    <!-- Optional: Add date-fns library if needed for custom date formatting, though chartjs-adapter-date-fns should cover it -->
    <!-- <script src="https://cdnjs.cloudflare.com/ajax/libs/date-fns/2.29.3/date_fns.min.js"></script> -->

    <script>
        // Backend API endpoint
        const BACKEND_API_URL = 'http://127.0.0.1:5000'; // Ensure this matches your Flask server address

        class TradingTerminal {
            constructor() {
                this.BYBIT_API_BASE = 'https://api.bybit.com/v5/market/';
                this.BYBIT_WS_BASE = 'wss://stream.bybit.com/v5/public/spot';
                this.chart = null;
                this.symbols = []; // To store fetched Bybit symbols
                this.currentSymbol = '';
                this.chartData = []; // Array of kline objects {time, open, high, low, close, volume}
                this.websocket = null;
                this.symbolCache = new Map(); // For symbol list
                this.settings = this.loadSettings();
                this.currentInterval = 'D'; // Track current interval
                this.isLive = false; // Track live mode
                this.geminiAnalysisTimeout = null; // For debouncing Gemini requests on live data
                this.lastPriceColorChangeTimeout = null; // For price animation
                this.init();
            }

            async init() {
                this.setupEventListeners();
                await this.loadSymbols();
                this.applySettings();
                this.showNotification('Trading Terminal Ready!', 'info');
            }

            setupEventListeners() {
                // Symbol search
                const symbolSearch = document.getElementById('symbolSearch');
                const symbolDropdown = document.getElementById('symbolDropdown');
                
                symbolSearch.addEventListener('input', () => this.handleSymbolSearch(symbolSearch.value));
                symbolSearch.addEventListener('focus', () => {
                    if (this.symbols.length > 0) this.showSymbolDropdown();
                });
                
                document.addEventListener('click', (e) => {
                    if (!symbolSearch.contains(e.target) && !symbolDropdown.contains(e.target)) {
                        symbolDropdown.classList.remove('active');
                    }
                });

                // Main buttons
                document.getElementById('fetchDataButton').addEventListener('click', () => this.fetchDataAndRenderChart());
                document.getElementById('autoRefreshButton').addEventListener('click', () => this.toggleLiveUpdates());
                document.getElementById('saveSettingsButton').addEventListener('click', () => this.saveSettings());
                document.getElementById('resetButton').addEventListener('click', () => this.resetSettings());

                // Preset buttons
                document.querySelectorAll('.preset-button').forEach(btn => {
                    btn.addEventListener('click', (e) => this.applyPreset(e.target.dataset.preset));
                });

                // Indicator toggles
                document.querySelectorAll('.indicator-toggle input').forEach(toggle => {
                    toggle.addEventListener('change', () => this.updateChartVisibility());
                });

                // Tab buttons
                document.querySelectorAll('.tab-button').forEach(btn => {
                    btn.addEventListener('click', (e) => this.switchTab(e.target.dataset.tab));
                });
            }

            // --- Symbol Management ---
            async loadSymbols() {
                this.showLoading('Loading available symbols...');
                const cacheKey = 'symbols_cache';
                const cached = this.getFromCache(cacheKey);
                
                if (cached) {
                    this.symbols = cached;
                    this.populateSymbolDropdown();
                    this.hideLoading();
                    return;
                }

                try {
                    const response = await fetch(`${this.BYBIT_API_BASE}instruments-info?category=spot`);
                    const data = await response.json();

                    if (data.retCode !== 0) {
                        throw new Error(data.retMsg || 'Failed to fetch symbols');
                    }

                    this.symbols = data.result.list
                        .filter(item => item.status === 'Trading' && item.quoteCoin === 'USDT')
                        .map(item => ({
                            symbol: item.symbol,
                            baseCoin: item.baseCoin,
                            quoteCoin: item.quoteCoin
                        }))
                        .sort((a, b) => {
                            // Prioritize major coins first
                            const priority = ['BTC', 'ETH', 'BNB', 'SOL', 'XRP', 'USDT'];
                            const aIndex = priority.indexOf(a.baseCoin);
                            const bIndex = priority.indexOf(b.baseCoin);
                            if (aIndex !== -1 && bIndex === -1) return -1;
                            if (aIndex === -1 && bIndex !== -1) return 1;
                            if (aIndex !== -1 && bIndex !== -1) return aIndex - bIndex;
                            return a.symbol.localeCompare(b.symbol);
                        });

                    this.setCache(cacheKey, this.symbols, 3600000); // Cache for 1 hour
                    this.populateSymbolDropdown();
                    
                    // Set default symbol from settings or pick BTCUSDT if available
                    const defaultSymbolFromSettings = this.settings.symbol;
                    const defaultSymbol = this.symbols.find(s => s.symbol === defaultSymbolFromSettings) || 
                                          this.symbols.find(s => s.symbol === 'BTCUSDT') || 
                                          (this.symbols.length > 0 ? this.symbols[0] : null);
                    
                    if (defaultSymbol) {
                        this.selectSymbol(defaultSymbol.symbol);
                    }

                } catch (error) {
                    this.showError(`Failed to load symbols: ${error.message}`);
                } finally {
                    this.hideLoading();
                }
            }

            populateSymbolDropdown(filter = '') {
                const dropdown = document.getElementById('symbolDropdown');
                const filtered = filter 
                    ? this.symbols.filter(s => 
                        s.symbol.toLowerCase().includes(filter.toLowerCase()) ||
                        s.baseCoin.toLowerCase().includes(filter.toLowerCase())
                      ).slice(0, 50) // Limit dropdown to 50 items
                    : this.symbols.slice(0, 20); // Show top 20 by default

                dropdown.innerHTML = filtered.map(s => `
                    <div class="symbol-item ${s.symbol === this.currentSymbol ? 'selected' : ''}" 
                         data-symbol="${s.symbol}">
                        <span>${s.symbol}</span>
                        <span class="symbol-info">${s.baseCoin}/${s.quoteCoin}</span>
                    </div>
                `).join('');

                // Add event listeners to new dropdown items
                dropdown.querySelectorAll('.symbol-item').forEach(item => {
                    item.addEventListener('click', () => {
                        this.selectSymbol(item.dataset.symbol);
                        dropdown.classList.remove('active');
                    });
                });
            }

            handleSymbolSearch(value) {
                this.populateSymbolDropdown(value);
                if (value.length > 0 && this.symbols.length > 0) {
                    this.showSymbolDropdown();
                } else {
                    document.getElementById('symbolDropdown').classList.remove('active');
                }
            }

            showSymbolDropdown() {
                document.getElementById('symbolDropdown').classList.add('active');
            }

            selectSymbol(symbol) {
                if (this.currentSymbol === symbol) return; // Avoid re-selection

                this.currentSymbol = symbol;
                document.getElementById('symbolSearch').value = symbol;
                this.updateTickerInfo(symbol);
                this.disconnectWebSocket(); // Disconnect old WS when symbol changes
                this.resetChartAndAnalysis(); // Clear old chart/analysis
                this.showNotification(`Symbol set to: ${symbol}`, 'info');
                
                // If Gemini tab is active, re-request analysis after new data loads
                if (document.getElementById('gemini-analysis-tab').classList.contains('active')) {
                    this.displayGeminiAnalysis("Loading new data for analysis...");
                }
            }

            // --- Ticker Info Display ---
            async updateTickerInfo(symbol) {
                if (!symbol) return;
                document.getElementById('tickerInfo').style.display = 'block';
                document.getElementById('tickerTitle').textContent = `${symbol} Market Information`;
                try {
                    // Fetch ticker info using the backend or directly (backend preferred for consistency)
                    // For simplicity here, direct fetch. Ideally, add a /tickers route to backend.
                    const response = await fetch(`${this.BYBIT_API_BASE}tickers?category=spot&symbol=${symbol}`);
                    const data = await response.json();
                    if (data.retCode === 0 && data.result.list && data.result.list.length > 0) {
                        const ticker = data.result.list[0];
                        this.displayTickerInfo(ticker);
                    } else {
                        this.showWarning(`Could not fetch ticker info for ${symbol}: ${data.retMsg}`);
                    }
                } catch (error) {
                    console.error('Error fetching ticker:', error);
                    this.showError(`Failed to fetch ticker info for ${symbol}.`);
                }
            }

            displayTickerInfo(ticker) {
                const price = parseFloat(ticker.lastPrice);
                const change24h = parseFloat(ticker.price24hPcnt);
                const bid = parseFloat(ticker.bid1Price);
                const ask = parseFloat(ticker.ask1Price);
                const spread = ask - bid;
                const spreadPercent = (spread / price * 100).toFixed(3);
                
                this.updateLivePriceDisplay(price); // Update main live price display

                // Update ticker info boxes
                document.getElementById('tickerLastPrice').textContent = this.formatPrice(price);
                document.getElementById('tickerBidPrice').textContent = this.formatPrice(bid);
                document.getElementById('tickerAskPrice').textContent = this.formatPrice(ask);
                document.getElementById('tickerSpread').textContent = `${this.formatPrice(spread)} (${spreadPercent}%)`;
                
                const priceChangeValue = price * change24h / 100;
                const priceChangeEl = document.getElementById('tickerPriceChange');
                priceChangeEl.textContent = this.formatPrice(priceChangeValue);
                priceChangeEl.className = `ticker-value ${change24h >= 0 ? 'positive' : 'negative'}`;
                
                const priceChangePercentEl = document.getElementById('tickerPriceChangePercent');
                priceChangePercentEl.textContent = `${change24h.toFixed(2)}%`;
                priceChangePercentEl.className = `ticker-value ${change24h >= 0 ? 'positive' : 'negative'}`;
                
                document.getElementById('tickerHigh24h').textContent = this.formatPrice(parseFloat(ticker.highPrice24h));
                document.getElementById('tickerLow24h').textContent = this.formatPrice(parseFloat(ticker.lowPrice24h));
                document.getElementById('tickerVolume24h').textContent = this.formatVolume(parseFloat(ticker.volume24h));
            }

            // --- Chart Data Fetching and Rendering ---
            async fetchDataAndRenderChart() {
                if (!this.currentSymbol) {
                    this.showWarning('Please select a symbol first.');
                    return;
                }

                this.showLoading(`Loading chart data for ${this.currentSymbol}...`);
                this.disconnectWebSocket(); // Stop live updates while fetching
                this.isLive = false; // Exit live mode
                document.getElementById('autoRefreshButton').textContent = '🔄 Go Live';
                document.getElementById('autoRefreshButton').style.background = 'linear-gradient(135deg, var(--accent-pink) 0%, #cc0066 100%)';

                const interval = document.getElementById('intervalSelect').value;
                const limit = parseInt(document.getElementById('limit').value);
                this.currentInterval = interval; // Update current interval

                try {
                    const url = `${this.BYBIT_API_BASE}kline?category=spot&symbol=${this.currentSymbol}&interval=${interval}&limit=${limit}`;
                    const response = await fetch(url);
                    const data = await response.json();

                    if (data.retCode !== 0) {
                        throw new Error(data.retMsg || 'Failed to fetch chart data');
                    }

                    // Bybit kline format: [timestamp, open, high, low, close, volume, turnover]
                    this.chartData = data.result.list.map(item => ({
                        time: parseInt(item[0]), // Milliseconds timestamp
                        open: parseFloat(item[1]),
                        high: parseFloat(item[2]),
                        low: parseFloat(item[3]),
                        close: parseFloat(item[4]),
                        volume: parseFloat(item[5])
                    })).reverse(); // Reverse to have chronological order

                    if (this.chartData.length === 0) {
                        throw new Error('No data available for this symbol and interval.');
                    }

                    this.renderChart(this.chartData);
                    this.updateAnalysis(this.chartData);
                    this.updateSignals(this.chartData);
                    this.updateStatistics(this.chartData);
                    
                    // Trigger Gemini analysis if tab is active
                    if (document.getElementById('gemini-analysis-tab').classList.contains('active')) {
                        this.requestGeminiAnalysis();
                    }

                    this.showNotification('Chart loaded successfully', 'success');
                } catch (error) {
                    console.error('Chart loading error:', error);
                    this.showError(`Failed to load chart: ${error.message}`);
                    this.resetChartAndAnalysis(); // Clear chart if loading fails
                } finally {
                    this.hideLoading();
                }
            }
            
            // --- Live Updates (WebSocket) ---
            toggleLiveUpdates() {
                const button = document.getElementById('autoRefreshButton');
                this.isLive = !this.isLive;

                if (this.isLive) {
                    this.connectWebSocket();
                    button.textContent = '🔴 Live Now';
                    button.style.background = 'linear-gradient(135deg, var(--accent-green) 0%, #00aa44 100%)';
                    this.showNotification('Live updates enabled', 'success');
                } else {
                    this.disconnectWebSocket();
                    button.textContent = '🔄 Go Live';
                    button.style.background = 'linear-gradient(135deg, var(--accent-pink) 0%, #cc0066 100%)';
                    this.showNotification('Live updates disabled', 'warning');
                }
            }
            
            connectWebSocket() {
                if (!this.currentSymbol) {
                    this.showWarning("Cannot connect to WebSocket: No symbol selected.");
                    this.isLive = false;
                    return;
                }
                if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
                    logging.info("WebSocket already open.");
                    return;
                }
                
                this.disconnectWebSocket(); // Ensure previous connection is closed

                const symbol = this.currentSymbol.toLowerCase();
                const interval = document.getElementById('intervalSelect').value;
                // The Bybit WS topic format is: {symbol}.{interval} e.g., kline.1.btcusdt
                const wsUrl = `${this.BYBIT_WS_BASE}`; // Base URL is the same, topics are sent in args
                
                this.websocket = new WebSocket(wsUrl);
                
                this.websocket.onopen = () => {
                    logging.info(`WebSocket connected for ${this.currentSymbol}`);
                    // Subscribe to tickers and klines
                    const subscribeMessage = {
                        "op": "subscribe",
                        "args": [
                            `tickers.${symbol}`, // Real-time ticker updates
                            `kline.${interval}.${symbol}` // Kline updates for the selected interval
                        ]
                    };
                    this.websocket.send(JSON.stringify(subscribeMessage));
                    this.showNotification('Connected to live data stream.', 'success');
                };

                this.websocket.onmessage = (event) => {
                    try {
                        const msg = JSON.parse(event.data);
                        if (msg.type === 'snapshot') { // Initial data for subscription
                            logging.debug("Received snapshot data from WS");
                            // Handle snapshot if necessary, usually for tickers or order book
                        } else if (msg.topic && msg.data) {
                            const dataArray = Array.isArray(msg.data) ? msg.data : [msg.data]; // Ensure it's an array
                            
                            if (msg.topic.includes('tickers')) {
                                const ticker = dataArray[0];
                                if (ticker && ticker.lastPrice) {
                                    this.updateLivePriceDisplay(parseFloat(ticker.lastPrice));
                                }
                            } else if (msg.topic.includes('kline')) {
                                const kline = dataArray[0];
                                if (kline && kline.timestamp) {
                                    const newCandle = {
                                        time: parseInt(kline.timestamp),
                                        open: parseFloat(kline.open),
                                        high: Math.max(parseFloat(kline.high), parseFloat(kline.open), parseFloat(kline.close)), // Ensure high is at least open/close
                                        low: Math.min(parseFloat(kline.low), parseFloat(kline.open), parseFloat(kline.close)),   // Ensure low is at least open/close
                                        close: parseFloat(kline.close),
                                        volume: parseFloat(kline.volume)
                                    };
                                    
                                    const lastKlineTime = this.chartData.length > 0 ? this.chartData[this.chartData.length - 1].time : 0;
                                    
                                    if (newCandle.time > lastKlineTime) { // New confirmed candle
                                        // If interval changed while live, we need to re-fetch data.
                                        // For now, assume interval remains constant during live session.
                                        if (this.chartData.length >= parseInt(document.getElementById('limit').value)) {
                                            this.chartData.shift(); // Remove oldest data point
                                        }
                                        this.chartData.push(newCandle);
                                        this.updateChart();
                                    } else if (newCandle.time === lastKlineTime) { // Update current unconfirmed candle
                                        // Update existing last candle's OHLCV
                                        const lastCandle = this.chartData[this.chartData.length - 1];
                                        lastCandle.open = newCandle.open; // Open might change on very first update
                                        lastCandle.high = newCandle.high;
                                        lastCandle.low = newCandle.low;
                                        lastCandle.close = newCandle.close;
                                        lastCandle.volume = newCandle.volume;
                                        this.updateChart(); // Update chart with new OHLCV
                                    }
                                    
                                    // Trigger Gemini analysis periodically for live data
                                    if (document.getElementById('gemini-analysis-tab').classList.contains('active')) {
                                        if (this.geminiAnalysisTimeout) clearTimeout(this.geminiAnalysisTimeout);
                                        this.geminiAnalysisTimeout = setTimeout(() => this.requestGeminiAnalysis(), 5000); // Analyze every 5 seconds
                                    }
                                }
                            }
                        }
                    } catch (e) {
                        console.error("Error processing WebSocket message:", e, event.data);
                    }
                };
                
                this.websocket.onerror = (error) => {
                    console.error('WebSocket Error:', error);
                    this.showError('WebSocket connection error. Retrying in 5s...');
                    this.disconnectWebSocket(); // Ensure proper cleanup
                    setTimeout(() => this.connectWebSocket(), 5000);
                };

                this.websocket.onclose = () => {
                    logging.info('WebSocket connection closed.');
                    this.showWarning('WebSocket connection closed.', 'warning');
                    // Attempt to reconnect if still in live mode
                    if (this.isLive) {
                        this.showWarning('Attempting to reconnect WebSocket...');
                        setTimeout(() => this.connectWebSocket(), 5000);
                    }
                };
            }
            
            disconnectWebSocket() {
                if (this.websocket) {
                    this.websocket.close();
                    this.websocket = null;
                    logging.info("WebSocket disconnected.");
                }
            }

            // --- Price Display and Animation ---
            updateLivePriceDisplay(price) {
                const livePriceEl = document.getElementById('livePrice');
                const lastUpdateEl = document.getElementById('lastUpdate');
                
                const currentPrice = parseFloat(livePriceEl.textContent);
                
                // Animate price change
                if (!isNaN(currentPrice) && price !== currentPrice) {
                    livePriceEl.style.color = price > currentPrice ? 'var(--accent-green)' : 'var(--accent-pink)';
                    if (this.lastPriceColorChangeTimeout) clearTimeout(this.lastPriceColorChangeTimeout);
                    this.lastPriceColorChangeTimeout = setTimeout(() => {
                        livePriceEl.style.color = 'var(--accent-green)'; // Default positive color
                    }, 1000); // Reset color after 1 second
                } else if (isNaN(currentPrice)) {
                    livePriceEl.style.color = 'var(--accent-green)'; // Default positive color
                }
                
                livePriceEl.textContent = this.formatPrice(price);
                lastUpdateEl.textContent = this.formatTime(Date.now());
            }

            // --- Chart Rendering and Updates ---
            renderChart(klines) {
                const indicators = this.calculateAllIndicators(klines);
                
                const candlestickData = klines.map(d => ({
                    x: d.time, // Timestamp in milliseconds
                    o: d.open,
                    h: d.high,
                    l: d.low,
                    c: d.close
                }));

                // Volume data with dynamic coloring
                const volumeData = klines.map(d => ({
                    x: d.time,
                    y: d.volume,
                    // Color bars based on close vs open for that candle
                    color: d.close >= d.open ? 'rgba(0, 255, 136, 0.6)' : 'rgba(255, 0, 136, 0.6)' 
                }));

                if (this.chart) {
                    this.chart.destroy();
                }

                const ctx = document.getElementById('chartCanvas').getContext('2d');
                this.chart = new Chart(ctx, {
                    type: 'candlestick',
                    data: {
                        datasets: this.createDatasets(candlestickData, volumeData, indicators, klines)
                    },
                    options: this.getChartOptions()
                });
            }

            createDatasets(candlestickData, volumeData, indicators, klines) {
                const datasets = [
                    // Price Dataset (Candlesticks)
                    {
                        label: 'Price',
                        data: candlestickData,
                        borderColor: (context) => { // Dynamic border color
                            const i = context.dataIndex;
                            if (!klines[i]) return '#e0e0ff';
                            return klines[i].close >= klines[i].open ? 'var(--success-color)' : 'var(--danger-color)';
                        },
                        borderWidth: 1,
                        color: { // Chart.js Financial Chart Color Scheme
                            up: 'var(--success-color)',
                            down: 'var(--danger-color)',
                            unchanged: '#8888ff'
                        },
                        yAxisID: 'price',
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    let label = context.dataset.label || '';
                                    if (label) {
                                        label += ': ';
                                    }
                                    if (context.parsed !== null) {
                                        label += `O: ${context.parsed.o.toFixed(4)}, H: ${context.parsed.h.toFixed(4)}, L: ${context.parsed.l.toFixed(4)}, C: ${context.parsed.c.toFixed(4)}`;
                                    }
                                    return label;
                                }
                            }
                        }
                    },
                    // Volume Dataset
                    {
                        type: 'bar',
                        label: 'Volume',
                        data: volumeData,
                        backgroundColor: volumeData.map(d => d.color),
                        yAxisID: 'volume',
                        hidden: !document.getElementById('toggleVolume').checked
                    }
                ];

                // Add Indicator Datasets
                const indicatorConfigs = {
                    SMA: { id: 'toggleSMA', data: indicators.sma, color: 'var(--accent-orange)', type: 'line' },
                    EMA: { id: 'toggleEMA', data: indicators.ema, color: 'var(--accent-purple)', type: 'line' },
                    BollingerBands: { id: 'toggleBollinger', data: indicators.bollinger, color: 'rgba(255, 136, 0, 0.5)', type: 'line' },
                    Supertrend: { id: 'toggleSupertrend', data: indicators.supertrend, color: '#00ff88', type: 'line' }, // Color managed by trend
                    VWAP: { id: 'toggleVWAP', data: indicators.vwap, color: 'var(--accent-cyan)', type: 'line' },
                    PSAR: { id: 'togglePSAR', data: indicators.psar, color: 'var(--accent-orange)', type: 'scatter' },
                    Ichimoku: { id: 'toggleIchimoku', data: indicators.ichimoku, color: '#00ccff', type: 'line' }
                };

                for (const [key, config] of Object.entries(indicatorConfigs)) {
                    if (document.getElementById(config.id).checked && config.data) {
                        if (key === 'BollingerBands' && config.data.upper && config.data.middle && config.data.lower) {
                            datasets.push(
                                { type: 'line', label: 'BB Upper', data: config.data.upper.map((v, i) => ({ x: klines[i].time, y: v })), borderColor: config.color, borderWidth: 1, pointRadius: 0, yAxisID: 'price', hidden: !document.getElementById(config.id).checked },
                                { type: 'line', label: 'BB Middle', data: config.data.middle.map((v, i) => ({ x: klines[i].time, y: v })), borderColor: 'rgba(255, 136, 0, 0.7)', borderWidth: 1, borderDash: [5, 5], pointRadius: 0, yAxisID: 'price', hidden: !document.getElementById(config.id).checked },
                                { type: 'line', label: 'BB Lower', data: config.data.lower.map((v, i) => ({ x: klines[i].time, y: v })), borderColor: config.color, borderWidth: 1, pointRadius: 0, yAxisID: 'price', hidden: !document.getElementById(config.id).checked }
                            );
                        } else if (key === 'Supertrend' && config.data.line && config.data.trend) {
                            datasets.push({
                                type: 'line',
                                label: 'Supertrend',
                                data: config.data.line.map((v, i) => ({ x: klines[i].time, y: v })),
                                borderColor: (ctx) => { // Color line based on trend direction
                                    const trend = config.data.trend[ctx.dataIndex];
                                    return trend ? 'var(--success-color)' : 'var(--danger-color)';
                                },
                                borderWidth: 2, pointRadius: 0, yAxisID: 'price',
                                hidden: !document.getElementById(config.id).checked,
                            });
                        } else if (key === 'PSAR' && config.data) {
                             datasets.push({
                                type: 'scatter',
                                label: 'PSAR',
                                data: config.data.map((v, i) => ({ x: klines[i].time, y: v })),
                                backgroundColor: config.color,
                                pointRadius: 3, 
                                yAxisID: 'price',
                                hidden: !document.getElementById(config.id).checked,
                            });
                        } else if (key === 'Ichimoku' && config.data && config.data.tenkan) {
                            datasets.push(
                                { type: 'line', label: 'Ichimoku Tenkan-sen', data: config.data.tenkan.map((v,i) => ({x: klines[i].time, y: v})), borderColor: '#ff00ff', borderWidth: 1, pointRadius: 0, yAxisID: 'price', hidden: !document.getElementById(config.id).checked},
                                { type: 'line', label: 'Ichimoku Kijun-sen', data: config.data.kijun.map((v,i) => ({x: klines[i].time, y: v})), borderColor: '#ff8800', borderWidth: 1, pointRadius: 0, yAxisID: 'price', hidden: !document.getElementById(config.id).checked},
                                { type: 'line', label: 'Ichimoku Senkou Span A', data: config.data.senkouA.map((v,i) => ({x: klines[i].time, y: v})), borderColor: 'rgba(0, 255, 0, 0.5)', borderWidth: 1, pointRadius: 0, yAxisID: 'price', hidden: !document.getElementById(config.id).checked},
                                { type: 'line', label: 'Ichimoku Senkou Span B', data: config.data.senkouB.map((v,i) => ({x: klines[i].time, y: v})), borderColor: 'rgba(255, 0, 0, 0.5)', borderWidth: 1, pointRadius: 0, yAxisID: 'price', hidden: !document.getElementById(config.id).checked},
                                { type: 'line', label: 'Ichimoku Chikou Span', data: config.data.chikou.map((v,i) => ({x: klines[i].time, y: v})), borderColor: '#00ffff', borderWidth: 1, borderDash: [2,2], pointRadius: 0, yAxisID: 'price', hidden: !document.getElementById(config.id).checked}
                            );
                        } else if (config.data && !config.data.upper && !config.data.line && !config.data.tenkan) { // Standard line indicators
                            datasets.push({
                                type: config.type,
                                label: key,
                                data: config.data.map((v, i) => ({ x: klines[i].time, y: v })),
                                borderColor: config.color,
                                borderWidth: config.type === 'scatter' ? 0 : 2, // Scatter points don't need border width
                                pointRadius: config.type === 'scatter' ? 3 : 0,
                                backgroundColor: config.type === 'scatter' ? config.color : undefined,
                                yAxisID: 'price',
                                hidden: !document.getElementById(config.id).checked,
                            });
                        }
                    }
                }
                
                // MACD is a composite indicator, handle separately if needed for histogram
                if (document.getElementById('toggleMACD').checked && indicators.macd && indicators.macd.macdLine && indicators.macd.signalLine) {
                     datasets.push(
                         { type: 'line', label: 'MACD Line', data: indicators.macd.macdLine.map((v, i) => ({ x: klines[i].time, y: v })), borderColor: 'var(--accent-cyan)', borderWidth: 1, pointRadius: 0, yAxisID: 'price', hidden: !document.getElementById('toggleMACD').checked },
                         { type: 'line', label: 'MACD Signal', data: indicators.macd.signalLine.map((v, i) => ({ x: klines[i].time, y: v })), borderColor: 'var(--accent-purple)', borderWidth: 1, pointRadius: 0, yAxisID: 'price', hidden: !document.getElementById('toggleMACD').checked }
                     );
                     // Histogram requires its own dataset type
                     if (indicators.macd.histogram) {
                         datasets.push({
                             type: 'bar',
                             label: 'MACD Histogram',
                             data: indicators.macd.histogram.map((v, i) => ({ x: klines[i].time, y: v, color: v >= 0 ? 'rgba(0, 255, 136, 0.5)' : 'rgba(255, 0, 136, 0.5)' })),
                             backgroundColor: (context) => context.dataset.data[context.dataIndex].color,
                             yAxisID: 'price',
                             hidden: !document.getElementById('toggleMACD').checked,
                         });
                     }
                }

                // Buy/Sell Signals Dataset
                if (document.getElementById('toggleSignals').checked && indicators.signals && indicators.signals.buy && indicators.signals.sell) {
                    datasets.push(
                        { type: 'scatter', label: 'Buy Signals', data: indicators.signals.buy, backgroundColor: 'var(--accent-green)', pointStyle: 'triangle', radius: 8, yAxisID: 'price', hidden: !document.getElementById('toggleSignals').checked},
                        { type: 'scatter', label: 'Sell Signals', data: indicators.signals.sell, backgroundColor: 'var(--accent-pink)', pointStyle: 'triangle', rotation: 180, radius: 8, yAxisID: 'price', hidden: !document.getElementById('toggleSignals').checked}
                    );
                }

                return datasets;
            }

            getChartOptions() {
                const intervalUnit = this.currentInterval === 'M' ? 'month' : this.currentInterval === 'W' ? 'week' : this.currentInterval === 'D' ? 'day' : 'hour';
                const timeUnit = this.currentInterval === 'D' ? 'day' : this.currentInterval === 'W' ? 'day' : this.currentInterval === 'M' ? 'month' : 'hour';
                
                // Adjusting date formats based on interval
                const timeFormat = {
                    hour: 'HH:mm',
                    day: 'MMM d',
                    week: 'MMM d',
                    month: 'MMM yyyy'
                };

                return {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        mode: 'index',
                        intersect: false,
                    },
                    plugins: {
                        legend: {
                            display: true,
                            position: 'top',
                            labels: {
                                color: 'var(--primary-text)',
                                usePointStyle: true,
                                padding: 15,
                                font: { size: 11 }
                            }
                        },
                        title: {
                            display: true,
                            text: `${this.currentSymbol} - ${document.getElementById('intervalSelect').selectedOptions[0].text}`,
                            color: 'var(--accent-cyan)',
                            font: { size: 16, weight: 'bold' },
                            padding: { top: 10, bottom: 20 }
                        },
                        tooltip: {
                            backgroundColor: 'rgba(26, 26, 58, 0.95)',
                            borderColor: 'var(--border-color)',
                            borderWidth: 1,
                            titleFont: { size: 13, weight: 'bold' },
                            bodyFont: { size: 11 },
                            padding: 10,
                            cornerRadius: 8,
                            callbacks: {
                                title: (tooltipItems) => {
                                    // Use DateAdapter for proper date formatting
                                    return chartjsAdapterDateFns.format(new Date(tooltipItems[0].parsed.x), 'Pp'); // 'Pp' is locale default
                                },
                                label: function(context) {
                                    // Specific handling for candlestick labels if needed
                                    if (context.dataset.type === 'candlestick') {
                                        const p = context.parsed;
                                        return `O: ${p.o.toFixed(4)}, H: ${p.h.toFixed(4)}, L: ${p.l.toFixed(4)}, C: ${p.c.toFixed(4)}`;
                                    }
                                    let label = context.dataset.label || '';
                                    if (label) label += ': ';
                                    if (context.parsed.y !== null) {
                                        label += context.parsed.y.toLocaleString(); // Use toLocaleString for numbers
                                    }
                                    return label;
                                }
                            }
                        },
                        zoom: {
                            pan: { enabled: true, mode: 'x', overScaleMode: 'x' },
                            zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'x' }
                        }
                    },
                    scales: {
                        x: {
                            type: 'time',
                            time: {
                                unit: timeUnit,
                                tooltipFormat: 'Pp', // Locale default format
                                displayFormats: timeFormat
                            },
                            ticks: {
                                color: 'var(--secondary-text)',
                                maxRotation: 0,
                                autoSkip: true,
                            },
                            grid: {
                                color: 'rgba(68, 68, 170, 0.1)',
                                drawBorder: false,
                                drawOnChartArea: true
                            }
                        },
                        price: {
                            position: 'right',
                            ticks: {
                                color: 'var(--secondary-text)',
                                callback: (value) => this.formatPrice(value)
                            },
                            grid: {
                                color: 'rgba(68, 68, 170, 0.1)',
                                drawBorder: false
                            },
                            afterDataLimits: (scale) => { // Adjust y-axis padding
                                const min = scale.min;
                                const max = scale.max;
                                const padding = (max - min) * 0.1; // 10% padding
                                scale.min = min - padding;
                                scale.max = max + padding;
                            }
                        },
                        volume: {
                            position: 'left',
                            beginAtZero: true,
                            ticks: {
                                color: 'var(--secondary-text)',
                                callback: (value) => this.formatVolume(value)
                            },
                            grid: {
                                color: 'rgba(68, 68, 170, 0.1)',
                                drawOnChartArea: false
                            }
                        }
                    }
                };
            }
            
            // --- Indicator Calculations ---
            calculateAllIndicators(klines) {
                const indicators = {};
                const emaPeriod = parseInt(document.getElementById('emaPeriod').value);
                const rsiPeriod = parseInt(document.getElementById('rsiPeriod').value);
                const stPeriod = parseInt(document.getElementById('stPeriod').value);
                const stMultiplier = parseFloat(document.getElementById('stMultiplier').value);
                const atrPeriod = parseInt(document.getElementById('atrPeriod').value);
                
                // Ensure enough data points for calculations
                if (!klines || klines.length < Math.max(emaPeriod, rsiPeriod, stPeriod, atrPeriod, 52)) { // 52 for Ichimoku
                    // Return empty indicators if not enough data
                    return { 
                        sma: [], ema: [], rsi: [], macd: {}, bollinger: {}, supertrend: {}, 
                        stochastic: {}, vwap: [], atr: [], psar: [], ichimoku: {} 
                    };
                }

                // Adjusting periods based on minimum data points required
                const safeEMAPeriod = Math.min(emaPeriod, klines.length - 1);
                const safeRSIPeriod = Math.min(rsiPeriod, klines.length - 1);
                const safeSTPeriod = Math.min(stPeriod, klines.length - 1);
                const safeATRPeriod = Math.min(atrPeriod, klines.length - 1);
                
                indicators.sma = this.calculateSMA(klines, 20);
                indicators.ema = this.calculateEMA(klines, safeEMAPeriod);
                indicators.rsi = this.calculateRSI(klines, safeRSIPeriod);
                indicators.macd = this.calculateMACD(klines, 12, 26, 9);
                indicators.bollinger = this.calculateBollingerBands(klines, 20, 2);
                indicators.supertrend = this.calculateSupertrend(klines, safeSTPeriod, stMultiplier);
                indicators.stochastic = this.calculateStochastic(klines, 14, 3, 3); // k=14, d=3, smooth=3
                indicators.vwap = this.calculateVWAP(klines);
                indicators.atr = this.calculateATR(klines, safeATRPeriod);
                indicators.psar = this.calculatePSAR(klines);
                indicators.ichimoku = this.calculateIchimoku(klines, 9, 26, 52, 26);
                
                // Generate signals based on all calculated indicators
                indicators.signals = this.generateTradingSignals(klines, indicators);
                
                return indicators;
            }

            calculateSMA(klines, period) {
                const sma = new Array(klines.length).fill(null);
                if (klines.length < period) return sma;
                for (let i = period - 1; i < klines.length; i++) {
                    let sum = 0;
                    for (let j = 0; j < period; j++) {
                        sum += klines[i - j].close;
                    }
                    sma[i] = sum / period;
                }
                return sma;
            }

            calculateEMA(klines, period) {
                const ema = new Array(klines.length).fill(null);
                if (klines.length < period) return ema;
                const multiplier = 2 / (period + 1);
                
                let sum = 0;
                for (let i = 0; i < period; i++) {
                    sum += klines[i].close;
                }
                ema[period - 1] = sum / period;
                
                for (let i = period; i < klines.length; i++) {
                    ema[i] = (klines[i].close - ema[i - 1]) * multiplier + ema[i - 1];
                }
                return ema;
            }

            calculateRSI(klines, period) {
                const rsi = new Array(klines.length).fill(null);
                if (klines.length <= period) return rsi;
                
                const gains = [];
                const losses = [];
                
                for (let i = 1; i < klines.length; i++) {
                    const diff = klines[i].close - klines[i - 1].close;
                    gains.push(diff > 0 ? diff : 0);
                    losses.push(diff < 0 ? Math.abs(diff) : 0);
                }
                
                let avgGain = gains.slice(0, period).reduce((sum, val) => sum + val, 0) / period;
                let avgLoss = losses.slice(0, period).reduce((sum, val) => sum + val, 0) / period;

                let rs = avgLoss === 0 ? Infinity : avgGain / avgLoss;
                rsi[period] = 100 - (100 / (1 + rs));
                
                for (let i = period + 1; i < klines.length; i++) {
                    avgGain = (avgGain * (period - 1) + gains[i - 1]) / period;
                    avgLoss = (avgLoss * (period - 1) + losses[i - 1]) / period;
                    rs = avgLoss === 0 ? Infinity : avgGain / avgLoss;
                    rsi[i] = 100 - (100 / (1 + rs));
                }
                
                return rsi;
            }
            
            calculateMACD(klines, fastPeriod = 12, slowPeriod = 26, signalPeriod = 9) {
                const macd = { macdLine: new Array(klines.length).fill(null), signalLine: new Array(klines.length).fill(null), histogram: new Array(klines.length).fill(null) };
                if (klines.length < slowPeriod) return macd;

                const fastEMA = this.calculateEMA(klines, fastPeriod);
                const slowEMA = this.calculateEMA(klines, slowPeriod);
                
                const startIndex = Math.max(fastPeriod, slowPeriod) - 1;
                
                for(let i = startIndex; i < klines.length; i++) {
                    if (fastEMA[i] !== null && slowEMA[i] !== null) {
                        macd.macdLine[i] = fastEMA[i] - slowEMA[i];
                    }
                }
                
                // Calculate Signal Line
                let sum = 0;
                let count = 0;
                let signalStartIndex = -1;

                for (let i = startIndex; i < macd.macdLine.length; i++) {
                    if (macd.macdLine[i] !== null) {
                        if (signalStartIndex === -1) signalStartIndex = i; // Mark the first valid MACD value
                        sum += macd.macdLine[i];
                        count++;
                        if (count === signalPeriod) {
                            macd.signalLine[i] = sum / signalPeriod;
                            break; // Found first signal line value
                        }
                    }
                }
                
                const multiplier = 2 / (signalPeriod + 1);
                for (let i = signalStartIndex + signalPeriod; i < macd.macdLine.length; i++) { // Start after first signal value calculation
                    if (macd.macdLine[i] !== null && macd.signalLine[i - 1] !== null) {
                        macd.signalLine[i] = (macd.macdLine[i] - macd.signalLine[i - 1]) * multiplier + macd.signalLine[i - 1];
                    }
                }
                
                // Calculate Histogram
                for (let i = 0; i < macd.macdLine.length; i++) {
                    if (macd.macdLine[i] !== null && macd.signalLine[i] !== null) {
                        macd.histogram[i] = macd.macdLine[i] - macd.signalLine[i];
                    }
                }
                return macd;
            }

            calculateBollingerBands(klines, period = 20, stdDev = 2) {
                const bollinger = { upper: new Array(klines.length).fill(null), middle: new Array(klines.length).fill(null), lower: new Array(klines.length).fill(null) };
                if (klines.length < period) return bollinger;

                const middle = this.calculateSMA(klines, period);
                
                for (let i = period - 1; i < klines.length; i++) {
                    if (middle[i] !== null) {
                        let sumSqDiff = 0;
                        for (let j = 0; j < period; j++) {
                            sumSqDiff += Math.pow(klines[i - j].close - middle[i], 2);
                        }
                        const std = Math.sqrt(sumSqDiff / period);
                        bollinger.upper[i] = middle[i] + (std * stdDev);
                        bollinger.lower[i] = middle[i] - (std * stdDev);
                        bollinger.middle[i] = middle[i];
                    }
                }
                return bollinger;
            }

            calculateSupertrend(klines, period = 10, multiplier = 3) {
                const supertrend = { line: new Array(klines.length).fill(null), trend: new Array(klines.length).fill(false) };
                if (klines.length < period) return supertrend;

                const atr = this.calculateATR(klines, period);
                const finalUpperBand = new Array(klines.length).fill(null);
                const finalLowerBand = new Array(klines.length).fill(null);

                for (let i = period; i < klines.length; i++) {
                    if (atr[i] === null) continue;
                    const high = klines[i].high;
                    const low = klines[i].low;
                    const close = klines[i].close;
                    
                    const basicUpperBand = (high + low) / 2 + (multiplier * atr[i]);
                    const basicLowerBand = (high + low) / 2 - (multiplier * atr[i]);
                    
                    if (i === period) { // First iteration
                        finalUpperBand[i] = basicUpperBand;
                        finalLowerBand[i] = basicLowerBand;
                        supertrend.trend[i] = close > finalLowerBand[i]; // Initial trend based on current close vs lower band
                        supertrend.line[i] = supertrend.trend[i] ? finalLowerBand[i] : finalUpperBand[i];
                    } else {
                        // Determine current bands based on previous bands and current basic bands
                        if (finalUpperBand[i - 1] !== null && basicUpperBand < finalUpperBand[i - 1]) {
                            finalUpperBand[i] = basicUpperBand;
                        } else {
                            finalUpperBand[i] = finalUpperBand[i - 1];
                        }

                        if (finalLowerBand[i - 1] !== null && basicLowerBand > finalLowerBand[i - 1]) {
                            finalLowerBand[i] = basicLowerBand;
                        } else {
                            finalLowerBand[i] = finalLowerBand[i - 1];
                        }

                        // Determine current trend and Supertrend line
                        if (supertrend.trend[i - 1]) { // Previous trend was UP
                            if (close < finalLowerBand[i]) { // Price crossed below new lower band
                                supertrend.trend[i] = false; // Trend down
                                supertrend.line[i] = finalUpperBand[i]; // Set line to upper band
                            } else {
                                supertrend.trend[i] = true; // Trend remains up
                                supertrend.line[i] = finalLowerBand[i]; // Set line to lower band
                            }
                        } else { // Previous trend was DOWN
                            if (close > finalUpperBand[i]) { // Price crossed above new upper band
                                supertrend.trend[i] = true; // Trend up
                                supertrend.line[i] = finalLowerBand[i]; // Set line to lower band
                            } else {
                                supertrend.trend[i] = false; // Trend remains down
                                supertrend.line[i] = finalUpperBand[i]; // Set line to upper band
                            }
                        }
                    }
                }
                return supertrend;
            }
            
            calculateStochastic(klines, kPeriod = 14, dPeriod = 3, smoothPeriod = 3) {
                const stochastic = { kLine: new Array(klines.length).fill(null), dLine: new Array(klines.length).fill(null) };
                if (klines.length < kPeriod) return stochastic;
                
                // Calculate %K
                for (let i = kPeriod - 1; i < klines.length; i++) {
                    const window = klines.slice(i - kPeriod + 1, i + 1);
                    const highestHigh = Math.max(...window.map(k => k.high));
                    const lowestLow = Math.min(...window.map(k => k.low));
                    
                    if (highestHigh !== lowestLow) {
                        stochastic.kLine[i] = 100 * (klines[i].close - lowestLow) / (highestHigh - lowestLow);
                    } else {
                        stochastic.kLine[i] = 0; // Handle division by zero or flat range
                    }
                }
                
                // Calculate %D (SMA of %K)
                const kSmoothed = this.calculateSMA(stochastic.kLine.map((val, idx) => val !== null ? val : 0), smoothPeriod); // Use dummy 0 for null to calc SMA
                
                for(let i = 0; i < kSmoothed.length; i++){
                    if(kSmoothed[i] !== null) stochastic.kLine[i] = kSmoothed[i]; // Update kLine with smoothed values if applicable (some implementations do this)
                }

                for (let i = dPeriod - 1; i < klines.length; i++) {
                    let sum = 0;
                    let count = 0;
                    for (let j = 0; j < dPeriod; j++) {
                        const index = i - j;
                        if (stochastic.kLine[index] !== null) {
                            sum += stochastic.kLine[index];
                            count++;
                        }
                    }
                    if (count > 0) stochastic.dLine[i] = sum / count;
                }
                return stochastic;
            }

            calculateVWAP(klines) {
                const vwap = new Array(klines.length).fill(null);
                if (klines.length === 0) return vwap;
                
                let cumulativeVolume = 0;
                let cumulativeVolumePrice = 0;
                
                for (let i = 0; i < klines.length; i++) {
                    const typicalPrice = (klines[i].high + klines[i].low + klines[i].close) / 3;
                    cumulativeVolume += klines[i].volume;
                    cumulativeVolumePrice += klines[i].volume * typicalPrice;
                    
                    if (cumulativeVolume > 0) {
                        vwap[i] = cumulativeVolumePrice / cumulativeVolume;
                    }
                }
                return vwap;
            }

            calculateATR(klines, period = 14) {
                const atr = new Array(klines.length).fill(null);
                if (klines.length < period) return atr;

                const tr = new Array(klines.length).fill(null);
                
                for (let i = 1; i < klines.length; i++) {
                    const high = klines[i].high;
                    const low = klines[i].low;
                    const prevClose = klines[i - 1].close;
                    
                    tr[i] = Math.max(high - low, Math.abs(high - prevClose), Math.abs(low - prevClose));
                }
                
                let sum = tr.slice(1, period + 1).reduce((a, b) => a + b, 0);
                atr[period] = sum / period;
                
                for (let i = period + 1; i < klines.length; i++) {
                    atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period;
                }
                return atr;
            }
            
            calculatePSAR(klines, initialAF = 0.02, maxAF = 0.2, increment = 0.02) {
                const psar = new Array(klines.length).fill(null);
                if (klines.length < 2) return psar;

                let af = initialAF; // Acceleration Factor
                let isBull = true; // Initial trend direction
                let ep = 0; // Extreme Point (highest high for uptrend, lowest low for downtrend)
                
                // Determine initial trend
                if (klines[1].close > klines[0].close) {
                    isBull = true;
                    ep = klines[0].high;
                    psar[0] = klines[0].low; // Initial PSAR below first low for uptrend
                } else {
                    isBull = false;
                    ep = klines[0].low;
                    psar[0] = klines[0].high; // Initial PSAR above first high for downtrend
                }

                for (let i = 1; i < klines.length; i++) {
                    const prevPSAR = psar[i-1];
                    const currentHigh = klines[i].high;
                    const currentLow = klines[i].low;
                    const prevHigh = klines[i-1].high;
                    const prevLow = klines[i-1].low;

                    let newPSAR;
                    if (isBull) { // Current trend is UP
                        newPSAR = prevPSAR + af * (ep - prevPSAR);
                        if (newPSAR > currentLow) { // PSAR crossed below current low
                            isBull = false; // Switch trend to DOWN
                            af = initialAF; // Reset AF
                            ep = currentLow; // New extreme point is current low
                            newPSAR = currentHigh; // PSAR becomes current high
                        } else {
                            if (currentHigh > ep) { // New higher high found
                                ep = currentHigh; // Update extreme point
                                af = Math.min(af + increment, maxAF); // Increase AF
                            }
                        }
                    } else { // Current trend is DOWN
                        newPSAR = prevPSAR - af * (prevPSAR - ep);
                        if (newPSAR < currentHigh) { // PSAR crossed above current high
                            isBull = true; // Switch trend to UP
                            af = initialAF; // Reset AF
                            ep = currentHigh; // New extreme point is current high
                            newPSAR = currentLow; // PSAR becomes current low
                        } else {
                            if (currentLow < ep) { // New lower low found
                                ep = currentLow; // Update extreme point
                                af = Math.min(af + increment, maxAF); // Increase AF
                            }
                        }
                    }
                    psar[i] = newPSAR;
                }
                return psar;
            }

            calculateIchimoku(klines, tenkanPeriod = 9, kijunPeriod = 26, senkouPeriod = 52, chikouLag = 26) {
                const ichimoku = {
                    tenkan: new Array(klines.length).fill(null),
                    kijun: new Array(klines.length).fill(null),
                    senkouA: new Array(klines.length).fill(null), // Leading Span A
                    senkouB: new Array(klines.length).fill(null), // Leading Span B
                    chikou: new Array(klines.length).fill(null)  // Lagging Span
                };

                if (klines.length < senkouPeriod) return ichimoku; // Need enough data for all periods

                const calculatePeriodHighLow = (period, index) => {
                    // Slice from current index back 'period' steps, but ensure start index is not negative
                    const start = Math.max(0, index - period + 1);
                    const window = klines.slice(start, index + 1);
                    if (window.length === 0) return { high: null, low: null };
                    const high = Math.max(...window.map(k => k.high));
                    const low = Math.min(...window.map(k => k.low));
                    return { high, low };
                };

                for (let i = 0; i < klines.length; i++) {
                    // Tenkan-sen (Conversion Line): (9-period highest high + 9-period lowest low) / 2
                    if (i >= tenkanPeriod - 1) {
                        const { high, low } = calculatePeriodHighLow(tenkanPeriod, i);
                        if (high !== null && low !== null) ichimoku.tenkan[i] = (high + low) / 2;
                    }

                    // Kijun-sen (Base Line): (26-period highest high + 26-period lowest low) / 2
                    if (i >= kijunPeriod - 1) {
                        const { high, low } = calculatePeriodHighLow(kijunPeriod, i);
                        if (high !== null && low !== null) ichimoku.kijun[i] = (high + low) / 2;
                    }
                    
                    // Senkou Span A (Leading Span A): (Tenkan-sen + Kijun-sen) / 2, plotted 26 periods ahead
                    if (ichimoku.tenkan[i] !== null && ichimoku.kijun[i] !== null) {
                        const senkouAValue = (ichimoku.tenkan[i] + ichimoku.kijun[i]) / 2;
                        // Plot 26 periods into the future
                        if (i + kijunPeriod < klines.length) { 
                            ichimoku.senkouA[i + kijunPeriod] = senkouAValue;
                        }
                    }

                    // Senkou Span B (Leading Span B): (52-period highest high + 52-period lowest low) / 2, plotted 26 periods ahead
                    if (i >= senkouPeriod - 1) {
                        const { high, low } = calculatePeriodHighLow(senkouPeriod, i);
                        if (high !== null && low !== null) {
                            const senkouBValue = (high + low) / 2;
                            // Plot 26 periods into the future
                            if (i + kijunPeriod < klines.length) {
                                ichimoku.senkouB[i + kijunPeriod] = senkouBValue;
                            }
                        }
                    }
                    
                    // Chikou Span (Lagging Span): Current closing price, plotted 26 periods behind
                    if (i >= chikouLag) { // Need to check if i is large enough to plot behind
                        ichimoku.chikou[i - chikouLag] = klines[i].close;
                    }
                }
                return ichimoku;
            }

            // --- Trading Signal Generation ---
            generateTradingSignals(klines, indicators) {
                const signals = [];
                const numKlines = klines.length;
                if (numKlines < 20) return signals; // Need sufficient data

                const lastIndex = numKlines - 1;
                const prevIndex = lastIndex - 1;

                const current = {
                    close: klines[lastIndex].close,
                    high: klines[lastIndex].high,
                    low: klines[lastIndex].low,
                    volume: klines[lastIndex].volume,
                    rsi: indicators.rsi[lastIndex],
                    macdLine: indicators.macd.macdLine[lastIndex],
                    macdSignal: indicators.macd.signalLine[lastIndex],
                    macdHistogram: indicators.macd.histogram[lastIndex],
                    bollingerUpper: indicators.bollinger?.upper[lastIndex],
                    bollingerMiddle: indicators.bollinger?.middle[lastIndex],
                    bollingerLower: indicators.bollinger?.lower[lastIndex],
                    supertrend: indicators.supertrend?.line[lastIndex],
                    supertrendTrend: indicators.supertrend?.trend[lastIndex],
                    stochasticK: indicators.stochastic?.kLine[lastIndex],
                    stochasticD: indicators.stochastic?.dLine[lastIndex],
                    vwap: indicators.vwap[lastIndex],
                    psar: indicators.psar[lastIndex]
                };

                const prev = {
                    close: klines[prevIndex].close,
                    volume: klines[prevIndex].volume,
                    rsi: indicators.rsi[prevIndex],
                    macdLine: indicators.macd.macdLine[prevIndex],
                    macdSignal: indicators.macd.signalLine[prevIndex],
                    bollingerUpper: indicators.bollinger?.upper[prevIndex],
                    bollingerMiddle: indicators.bollinger?.middle[prevIndex],
                    bollingerLower: indicators.bollinger?.lower[prevIndex],
                    supertrend: indicators.supertrend?.line[prevIndex],
                    supertrendTrend: indicators.supertrend?.trend[prevIndex],
                    stochasticK: indicators.stochastic?.kLine[prevIndex],
                    stochasticD: indicators.stochastic?.dLine[prevIndex],
                    vwap: indicators.vwap[prevIndex],
                    psar: indicators.psar[prevIndex]
                };

                // --- Signal Logic ---

                // RSI Signals
                if (current.rsi !== null && prev.rsi !== null) {
                    if (prev.rsi < 30 && current.rsi >= 30) signals.push({ type: 'RSI Oversold Rebound', strength: 1, direction: 'buy' });
                    if (prev.rsi > 70 && current.rsi <= 70) signals.push({ type: 'RSI Overbought Reversal', strength: 1, direction: 'sell' });
                    // Momentum based RSI
                    if (current.rsi > 50 && prev.rsi < 50) signals.push({ type: 'RSI Bullish Momentum', strength: 1, direction: 'buy' });
                    if (current.rsi < 50 && prev.rsi > 50) signals.push({ type: 'RSI Bearish Momentum', strength: 1, direction: 'sell' });
                }
                
                // MACD Signals
                if (current.macdLine !== null && current.macdSignal !== null && prev.macdLine !== null && prev.macdSignal !== null) {
                    if (prev.macdLine < prev.macdSignal && current.macdLine >= current.macdSignal) signals.push({ type: 'MACD Bullish Crossover', strength: 2, direction: 'buy' });
                    if (prev.macdLine > prev.macdSignal && current.macdLine <= current.macdSignal) signals.push({ type: 'MACD Bearish Crossover', strength: 2, direction: 'sell' });
                    // Histogram crossover
                    if (indicators.macd.histogram[prevIndex] < 0 && current.macdHistogram >= 0) signals.push({ type: 'MACD Histogram Bullish', strength: 1, direction: 'buy' });
                    if (indicators.macd.histogram[prevIndex] > 0 && current.macdHistogram <= 0) signals.push({ type: 'MACD Histogram Bearish', strength: 1, direction: 'sell' });
                }
                
                // Supertrend Signals
                if (current.supertrendTrend !== null && prev.supertrendTrend !== null) {
                    if (!prev.supertrendTrend && current.supertrendTrend) signals.push({ type: 'Supertrend Flip to Up', strength: 3, direction: 'buy' });
                    if (prev.supertrendTrend && !current.supertrendTrend) signals.push({ type: 'Supertrend Flip to Down', strength: 3, direction: 'sell' });
                }
                
                // Bollinger Bands Signals (Reversals/Breakouts)
                if (current.bollingerUpper !== null && prev.bollingerUpper !== null && current.bollingerLower !== null && prev.bollingerLower !== null) {
                    if (current.close >= current.bollingerUpper && prev.close < prev.bollingerUpper) signals.push({ type: 'BB Upper Band Touch/Cross', strength: 1, direction: 'sell' });
                    if (current.close <= current.bollingerLower && prev.close > prev.bollingerLower) signals.push({ type: 'BB Lower Band Touch/Cross', strength: 1, direction: 'buy' });
                }

                // Stochastic Signals
                if (current.stochasticK !== null && current.stochasticD !== null && prev.stochasticK !== null && prev.stochasticD !== null) {
                    // Bullish Crossover in Oversold Region
                    if (prev.stochasticK < prev.stochasticD && current.stochasticK >= current.stochasticD && current.stochasticK < 20) {
                        signals.push({ type: 'Stochastic Bullish Crossover (Oversold)', strength: 2, direction: 'buy' });
                    }
                    // Bearish Crossover in Overbought Region
                    if (prev.stochasticK > prev.stochasticD && current.stochasticK <= current.stochasticD && current.stochasticK > 80) {
                        signals.push({ type: 'Stochastic Bearish Crossover (Overbought)', strength: 2, direction: 'sell' });
                    }
                }
                
                // VWAP Signals
                if (current.vwap !== null && prev.vwap !== null) {
                    if (prev.close < prev.vwap && current.close >= current.vwap) signals.push({ type: 'VWAP Bullish Cross', strength: 1, direction: 'buy' });
                    if (prev.close > prev.vwap && current.close <= current.vwap) signals.push({ type: 'VWAP Bearish Cross', strength: 1, direction: 'sell' });
                }

                // PSAR Signals
                if (current.psar !== null && prev.psar !== null) {
                    if (prev.psar > prev.close && current.psar < current.close) signals.push({ type: 'PSAR Flip to Bullish', strength: 2, direction: 'buy' });
                    if (prev.psar < prev.close && current.psar > current.close) signals.push({ type: 'PSAR Flip to Bearish', strength: 2, direction: 'sell' });
                }

                // Ichimoku Signals (basic crossover checks)
                if (indicators.ichimoku) {
                    const ichi = indicators.ichimoku;
                    if (ichi.tenkan[lastIndex] !== null && ichi.kijun[lastIndex] !== null && ichi.tenkan[prevIndex] !== null && ichi.kijun[prevIndex] !== null) {
                        // Tenkan crossing Kijun Bullish
                        if (ichi.tenkan[prevIndex] < ichi.kijun[prevIndex] && ichi.tenkan[lastIndex] >= ichi.kijun[lastIndex]) {
                            signals.push({ type: 'Ichimoku Tenkan/Kijun Bullish Cross', strength: 2, direction: 'buy' });
                        }
                        // Tenkan crossing Kijun Bearish
                        if (ichi.tenkan[prevIndex] > ichi.kijun[prevIndex] && ichi.tenkan[lastIndex] <= ichi.kijun[lastIndex]) {
                            signals.push({ type: 'Ichimoku Tenkan/Kijun Bearish Cross', strength: 2, direction: 'sell' });
                        }
                    }
                    // Price crossing Kumo Bullish
                    if (ichi.senkouA[lastIndex] !== null && ichi.senkouB[lastIndex] !== null && current.close > ichi.senkouA[lastIndex] && current.close > ichi.senkouB[lastIndex]) {
                         // Check if previous close was below or on one of the kumo lines
                        if (ichi.senkouA[prevIndex] !== null && ichi.senkouB[prevIndex] !== null) {
                            if (prev.close <= Math.min(ichi.senkouA[prevIndex], ichi.senkouB[prevIndex])) {
                                signals.push({ type: 'Ichimoku Price Cross Kumo Bullish', strength: 2, direction: 'buy' });
                            }
                        }
                    }
                     // Price crossing Kumo Bearish
                    if (ichi.senkouA[lastIndex] !== null && ichi.senkouB[lastIndex] !== null && current.close < ichi.senkouA[lastIndex] && current.close < ichi.senkouB[lastIndex]) {
                        if (ichi.senkouA[prevIndex] !== null && ichi.senkouB[prevIndex] !== null) {
                            if (prev.close >= Math.max(ichi.senkouA[prevIndex], ichi.senkouB[prevIndex])) {
                                signals.push({ type: 'Ichimoku Price Cross Kumo Bearish', strength: 2, direction: 'sell' });
                            }
                        }
                    }
                }

                // Volume Spike Signal (simple check)
                const avgLast5Vol = klines.slice(lastIndex - 4, lastIndex + 1).reduce((sum, k) => sum + k.volume, 0) / 5;
                const avgPrev5Vol = klines.slice(lastIndex - 9, lastIndex - 4).reduce((sum, k) => sum + k.volume, 0) / 5;
                if (avgLast5Vol > avgPrev5Vol * 2 && avgLast5Vol > this.getAverageVolume(klines) * 1.5) { // High volume compared to recent and overall average
                    signals.push({ type: 'Significant Volume Spike', strength: 1, direction: 'neutral' }); // Neutral direction as spike could lead to anything
                }
                
                // Remove duplicate signal types (prioritize higher strength if duplicates exist)
                const uniqueSignals = [];
                const signalMap = new Map(); // Store signal by type, keeping strongest one

                signals.forEach(signal => {
                    const key = `${signal.type}-${signal.direction}`;
                    if (!signalMap.has(key) || signal.strength > signalMap.get(key).strength) {
                        signalMap.set(key, signal);
                    }
                });
                
                signalMap.forEach(signal => uniqueSignals.push(signal));
                
                // Sort signals by strength (descending)
                return uniqueSignals.sort((a, b) => b.strength - a.strength);
            }

            // --- Analysis Tab Updates ---
            updateAnalysis(klines) {
                if (!klines || klines.length < 20) {
                    this.setStatValue('trendDirection', '-', 'neutral');
                    this.setStatValue('rsiStatus', '-', 'neutral');
                    this.setStatValue('volumeTrend', '-', 'neutral');
                    this.setStatValue('volatility', '-', 'neutral');
                    return;
                }

                const numRecentKlines = 10;
                const numOlderKlines = 10;
                const recentPrices = klines.slice(-numRecentKlines).map(k => k.close);
                const olderPrices = klines.slice(-numRecentKlines - numOlderKlines, -numRecentKlines).map(k => k.close);
                
                const recentAvg = recentPrices.reduce((a, b) => a + b, 0) / recentPrices.length;
                const olderAvg = olderPrices.reduce((a, b) => a + b, 0) / olderPrices.length;
                
                let trendDirection = 'Neutral';
                let trendClass = 'neutral';
                if (recentAvg > olderAvg * 1.02) { trendDirection = 'Bullish 📈'; trendClass = 'positive'; } 
                else if (recentAvg < olderAvg * 0.98) { trendDirection = 'Bearish 📉'; trendClass = 'negative'; }
                this.setStatValue('trendDirection', trendDirection, trendClass);
                
                const rsiPeriod = parseInt(document.getElementById('rsiPeriod').value);
                const rsi = this.calculateRSI(klines, rsiPeriod);
                const currentRSI = rsi[rsi.length - 1];
                let rsiStatus = 'Neutral';
                let rsiClass = 'neutral';
                if (currentRSI !== null) {
                    if (currentRSI > 70) { rsiStatus = 'Overbought'; rsiClass = 'negative'; }
                    else if (currentRSI < 30) { rsiStatus = 'Oversold'; rsiClass = 'positive'; }
                    else if (currentRSI > 50) { rsiStatus = 'Bullish'; rsiClass = 'positive'; }
                    else { rsiStatus = 'Bearish'; rsiClass = 'negative'; }
                }
                this.setStatValue('rsiStatus', rsiStatus, rsiClass);
                
                const recentVolumes = klines.slice(-5).map(k => k.volume);
                const olderVolumes = klines.slice(-10, -5).map(k => k.volume);
                const recentVolAvg = recentVolumes.reduce((a, b) => a + b, 0) / recentVolumes.length;
                const olderVolAvg = olderVolumes.reduce((a, b) => a + b, 0) / olderVolumes.length;
                let volumeTrend = 'Stable ➖';
                let volumeClass = 'neutral';
                if (recentVolAvg > olderVolAvg * 1.2) { volumeTrend = 'Increasing 📈'; volumeClass = 'positive'; } 
                else if (recentVolAvg < olderVolAvg * 0.8) { volumeTrend = 'Decreasing 📉'; volumeClass = 'negative'; }
                this.setStatValue('volumeTrend', volumeTrend, volumeClass);
                
                const atr = this.calculateATR(klines, 14);
                const currentATR = atr[atr.length - 1];
                const currentPrice = klines[klines.length - 1].close;
                let volatilityPercent = 'N/A';
                let volatilityLevel = 'N/A';
                let volatilityClass = 'neutral';
                if (currentATR !== null && currentPrice > 0) {
                    const percent = (currentATR / currentPrice * 100);
                    volatilityPercent = `${percent.toFixed(2)}%`;
                    if (percent > 5) { volatilityLevel = 'High'; volatilityClass = 'negative'; }
                    else if (percent > 2) { volatilityLevel = 'Medium'; volatilityClass = 'positive'; }
                    else { volatilityLevel = 'Low'; volatilityClass = 'positive'; }
                }
                this.setStatValue('volatility', `${volatilityLevel} (${volatilityPercent})`, volatilityClass);
            }

            // --- Signals Tab Update ---
            updateSignals(klines) {
                if (!klines || klines.length < 20) {
                    document.getElementById('signalsContent').innerHTML = '<p>Not enough data to generate signals.</p>';
                    return;
                }
                const indicators = this.calculateAllIndicators(klines);
                const signals = this.generateTradingSignals(klines, indicators);
                
                let html = '<div class="signals-list">';
                if (signals.length === 0) {
                    html += '<p>No significant signals detected recently.</p>';
                } else {
                    signals.forEach(signal => {
                        // Limit signal type to avoid very long strings, or truncate
                        const signalType = signal.type.length > 40 ? signal.type.substring(0, 37) + '...' : signal.type;
                        html += `
                            <div class="signal-item ${signal.direction === 'buy' ? 'buy' : signal.direction === 'sell' ? 'sell' : ''}">
                                <div class="signal-info">
                                    <strong>${signalType}</strong>
                                    <span class="signal-time">(${this.formatTime(Date.now())})</span>
                                </div>
                                <div class="signal-strength">Strength: ${signal.strength}</div>
                            </div>
                        `;
                    });
                }
                html += '</div>';
                document.getElementById('signalsContent').innerHTML = html;
            }

            // --- Statistics Tab Update ---
            updateStatistics(klines) {
                if (!klines || klines.length < 20) {
                    this.setStatValue('avgVolume', '-', 'neutral');
                    this.setStatValue('priceRange', '-', 'neutral');
                    this.setStatValue('supportLevel', '-', 'neutral');
                    this.setStatValue('resistanceLevel', '-', 'neutral');
                    return;
                }
                
                const volumes = klines.map(k => k.volume);
                const avgVolume = volumes.reduce((a, b) => a + b, 0) / volumes.length;
                this.setStatValue('avgVolume', this.formatVolume(avgVolume), 'neutral');
                
                const prices = klines.map(k => k.close);
                const minPrice = Math.min(...prices);
                const maxPrice = Math.max(...prices);
                const priceRangePercent = ((maxPrice - minPrice) / minPrice * 100).toFixed(2);
                this.setStatValue('priceRange', `${priceRangePercent}%`, 'neutral');
                
                // Simple support/resistance based on percentiles
                const sortedPrices = [...prices].sort((a, b) => a - b);
                const supportLevel = sortedPrices[Math.floor(sortedPrices.length * 0.1)]; // 10th percentile
                const resistanceLevel = sortedPrices[Math.floor(sortedPrices.length * 0.9)]; // 90th percentile
                
                this.setStatValue('supportLevel', this.formatPrice(supportLevel), 'neutral');
                this.setStatValue('resistanceLevel', this.formatPrice(resistanceLevel), 'neutral');
            }

            // --- Gemini Analysis Tab Methods ---
            async requestGeminiAnalysis() {
                if (!this.currentSymbol) {
                    this.displayGeminiAnalysis("Please select a symbol first.");
                    return;
                }
                if (!this.chartData || this.chartData.length < 10) { // Need at least 10 candles for context
                    this.displayGeminiAnalysis("Not enough data loaded for analysis. Load more data points.");
                    return;
                }

                this.displayGeminiAnalysis("<p><em>Fetching latest data and analyzing with Gemini AI...</em></p>");

                const interval = document.getElementById('intervalSelect').value;
                // Pass the most relevant data: last ~10-20 klines, and last values of indicators/signals
                const klinesForBackend = this.chartData.slice(-20); // Send last 20 klines for better context

                // Recalculate indicators and signals to ensure they are the latest and match what backend expects
                const indicators = this.calculateAllIndicators(this.chartData);
                const signals = this.generateTradingSignals(this.chartData, indicators);
                
                // Format indicators for the backend payload (sending only LAST values for most)
                const payloadIndicators = {};
                for (const [key, value] of Object.entries(indicators)) {
                    if (key === 'signals') continue; // Signals are sent separately
                    if (Array.isArray(value)) {
                        payloadIndicators[key] = value[value.length - 1]; // Send last value for array indicators
                    } else if (typeof value === 'object' && value !== null) { // Handle complex indicator objects (MACD, BB, ST, Ichimoku)
                        payloadIndicators[key] = {};
                        for (const subKey in value) {
                             if(Array.isArray(value[subKey])) {
                                payloadIndicators[key][subKey] = value[subKey][value[subKey].length - 1];
                            } else { // Handle cases like trend boolean
                                payloadIndicators[key][subKey] = value[subKey];
                            }
                        }
                    }
                }

                const payload = {
                    symbol: this.currentSymbol,
                    interval: interval,
                    klines: klinesForBackend, 
                    indicators: payloadIndicators,
                    signals: signals // Send the generated signal objects
                };

                try {
                    const response = await fetch(`${BACKEND_API_URL}/analyze`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(payload),
                    });

                    const result = await response.json();
                    if (response.ok) {
                        this.displayGeminiAnalysis(result.analysis);
                    } else {
                        const errorMsg = result.error || response.statusText || 'Unknown error';
                        this.displayGeminiAnalysis(`<p><em>Error fetching Gemini analysis: ${errorMsg}</em></p>`);
                        this.showError(`Gemini analysis failed: ${errorMsg}`);
                    }
                } catch (error) {
                    console.error("Fetch error for Gemini analysis:", error);
                    this.displayGeminiAnalysis(`<p><em>Could not connect to the analysis service. Please ensure the backend is running. Error: ${error.message}</em></p>`);
                    this.showError(`Could not connect to analysis service. Is the backend running? (${error.message})`);
                }
            }

            displayGeminiAnalysis(analysisText) {
                const el = document.getElementById('geminiAnalysisResult');
                if (el) {
                    // Safely render HTML, assuming backend provides safe text
                    el.innerHTML = analysisText.replace(/\n/g, '<br>');
                }
            }

            // --- UI Update Helpers ---
            updateChartVisibility() {
                if (!this.chart) return;
                
                const datasets = this.chart.data.datasets;
                const indicatorToggles = {
                    toggleVolume: 'Volume',
                    toggleSMA: 'SMA',
                    toggleEMA: 'EMA',
                    toggleMACD: 'MACD Line', // Need to target specific labels
                    'MACD Signal': 'MACD Signal',
                    'MACD Histogram': 'MACD Histogram',
                    toggleBollinger: 'BB Upper', // Target BB Upper as representative
                    toggleSupertrend: 'Supertrend',
                    toggleRSI: 'RSI', // Currently not plotted as dataset, but could be
                    toggleStochastic: 'Stochastic %K', // Assuming this is what's plotted
                    toggleVWAP: 'VWAP',
                    togglePSAR: 'PSAR',
                    toggleIchimoku: 'Ichimoku Tenkan-sen', // Target one Ichimoku line
                    toggleSignals: 'Buy Signals' // Target one signal type
                };

                datasets.forEach(dataset => {
                    let hidden = true; // Assume hidden by default
                    for (const [toggleId, labelPart] of Object.entries(indicatorToggles)) {
                        if (document.getElementById(toggleId)?.checked && dataset.label.includes(labelPart)) {
                            hidden = false;
                            break; // Found a matching visible indicator
                        }
                    }
                    dataset.hidden = hidden;
                });
                
                this.chart.update();
            }
            
            // Helper to set value and class for stat cards
            setStatValue(elementId, value, className = 'neutral') {
                const el = document.getElementById(elementId);
                if (el) {
                    el.textContent = value;
                    el.className = `stat-value ${className}`;
                }
            }

            // --- Settings Management ---
            applyPreset(preset) {
                const presets = {
                    scalping: { interval: '5', limit: 100, atrPeriod: 7, rsiPeriod: 7, emaPeriod: 9, stPeriod: 7, stMultiplier: 2 },
                    daytrading: { interval: '15', limit: 200, atrPeriod: 14, rsiPeriod: 14, emaPeriod: 20, stPeriod: 10, stMultiplier: 3 },
                    swing: { interval: '60', limit: 300, atrPeriod: 20, rsiPeriod: 20, emaPeriod: 50, stPeriod: 15, stMultiplier: 3.5 },
                    position: { interval: 'D', limit: 500, atrPeriod: 28, rsiPeriod: 28, emaPeriod: 100, stPeriod: 20, stMultiplier: 4 }
                };
                
                const settings = presets[preset];
                if (settings) {
                    document.getElementById('intervalSelect').value = settings.interval;
                    document.getElementById('limit').value = settings.limit;
                    document.getElementById('atrPeriod').value = settings.atrPeriod;
                    document.getElementById('rsiPeriod').value = settings.rsiPeriod;
                    document.getElementById('emaPeriod').value = settings.emaPeriod;
                    document.getElementById('stPeriod').value = settings.stPeriod;
                    document.getElementById('stMultiplier').value = settings.stMultiplier;
                    
                    this.saveSettings();
                    this.showNotification(`Applied '${preset}' preset`, 'success');
                    if (this.currentSymbol) this.fetchDataAndRenderChart();
                }
            }

            saveSettings() {
                const settings = {
                    symbol: this.currentSymbol,
                    interval: document.getElementById('intervalSelect').value,
                    limit: document.getElementById('limit').value,
                    atrPeriod: document.getElementById('atrPeriod').value,
                    rsiPeriod: document.getElementById('rsiPeriod').value,
                    emaPeriod: document.getElementById('emaPeriod').value,
                    stPeriod: document.getElementById('stPeriod').value,
                    stMultiplier: document.getElementById('stMultiplier').value,
                    indicators: {
                        volume: document.getElementById('toggleVolume').checked,
                        supertrend: document.getElementById('toggleSupertrend').checked,
                        bollinger: document.getElementById('toggleBollinger').checked,
                        sma: document.getElementById('toggleSMA').checked,
                        ema: document.getElementById('toggleEMA').checked,
                        rsi: document.getElementById('toggleRSI').checked,
                        macd: document.getElementById('toggleMACD').checked,
                        signals: document.getElementById('toggleSignals').checked,
                        stochastic: document.getElementById('toggleStochastic').checked,
                        vwap: document.getElementById('toggleVWAP').checked,
                        psar: document.getElementById('togglePSAR').checked,
                        ichimoku: document.getElementById('toggleIchimoku').checked
                    }
                };
                localStorage.setItem('tradingTerminalSettings', JSON.stringify(settings));
                this.showNotification('Settings saved successfully', 'success');
            }

            loadSettings() {
                const saved = localStorage.getItem('tradingTerminalSettings');
                const defaults = {
                    symbol: 'BTCUSDT', interval: 'D', limit: 200, atrPeriod: 14, rsiPeriod: 14,
                    emaPeriod: 20, stPeriod: 10, stMultiplier: 3,
                    indicators: {
                        volume: true, supertrend: true, bollinger: true, sma: true, ema: true,
                        rsi: true, macd: true, signals: true, stochastic: false, vwap: false,
                        psar: false, ichimoku: false
                    }
                };
                return saved ? { ...defaults, ...JSON.parse(saved) } : defaults;
            }

            applySettings() {
                const settings = this.settings;
                
                // Update UI elements from loaded settings
                if (settings.symbol) this.selectSymbol(settings.symbol);
                if (settings.interval) document.getElementById('intervalSelect').value = settings.interval;
                if (settings.limit) document.getElementById('limit').value = settings.limit;
                if (settings.atrPeriod) document.getElementById('atrPeriod').value = settings.atrPeriod;
                if (settings.rsiPeriod) document.getElementById('rsiPeriod').value = settings.rsiPeriod;
                if (settings.emaPeriod) document.getElementById('emaPeriod').value = settings.emaPeriod;
                if (settings.stPeriod) document.getElementById('stPeriod').value = settings.stPeriod;
                if (settings.stMultiplier) document.getElementById('stMultiplier').value = settings.stMultiplier;
                
                // Apply indicator toggle states
                if (settings.indicators) {
                    document.getElementById('toggleVolume').checked = settings.indicators.volume;
                    document.getElementById('toggleSupertrend').checked = settings.indicators.supertrend;
                    document.getElementById('toggleBollinger').checked = settings.indicators.bollinger;
                    document.getElementById('toggleSMA').checked = settings.indicators.sma;
                    document.getElementById('toggleEMA').checked = settings.indicators.ema;
                    document.getElementById('toggleRSI').checked = settings.indicators.rsi;
                    document.getElementById('toggleMACD').checked = settings.indicators.macd;
                    document.getElementById('toggleSignals').checked = settings.indicators.signals;
                    document.getElementById('toggleStochastic').checked = settings.indicators.stochastic;
                    document.getElementById('toggleVWAP').checked = settings.indicators.vwap;
                    document.getElementById('togglePSAR').checked = settings.indicators.psar;
                    document.getElementById('toggleIchimoku').checked = settings.indicators.ichimoku;
                }
                // Update chart visibility based on saved settings
                this.updateChartVisibility();
            }

            resetSettings() {
                if (confirm('Are you sure you want to reset all settings to default and clear local storage?')) {
                    localStorage.removeItem('tradingTerminalSettings');
                    this.settings = this.loadSettings(); // Reload defaults
                    this.applySettings(); // Re-apply defaults to UI
                    
                    this.disconnectWebSocket();
                    this.isLive = false;
                    document.getElementById('autoRefreshButton').textContent = '🔄 Go Live';
                    document.getElementById('autoRefreshButton').style.background = 'linear-gradient(135deg, var(--accent-pink) 0%, #cc0066 100%)';
                    
                    this.resetChartAndAnalysis(); // Clear chart and analysis displays
                    this.displayGeminiAnalysis("Settings reset. Please select a symbol and load chart.");
                    this.showNotification('Settings reset to default', 'success');
                }
            }
            
            resetChartAndAnalysis() {
                // Clear chart
                if (this.chart) {
                    this.chart.destroy();
                    this.chart = null;
                }
                document.getElementById('chartCanvas').getContext('2d').clearRect(0, 0, 100, 100); // Clear canvas
                this.chartData = [];

                // Clear analysis tabs
                this.setStatValue('trendDirection', '-', 'neutral');
                this.setStatValue('rsiStatus', '-', 'neutral');
                this.setStatValue('volumeTrend', '-', 'neutral');
                this.setStatValue('volatility', '-', 'neutral');
                document.getElementById('signalsContent').innerHTML = '<p>Loading trading signals...</p>';
                this.setStatValue('avgVolume', '-', 'neutral');
                this.setStatValue('priceRange', '-', 'neutral');
                this.setStatValue('supportLevel', '-', 'neutral');
                this.setStatValue('resistanceLevel', '-', 'neutral');
                this.displayGeminiAnalysis("Select a symbol and load chart data for analysis.");
            }

            // --- Loading & Notifications ---
            showLoading(message) {
                const overlay = document.getElementById('loadingOverlay');
                document.getElementById('loadingText').textContent = message;
                overlay.classList.add('active');
            }

            hideLoading() {
                document.getElementById('loadingOverlay').classList.remove('active');
            }

            switchTab(tabName) {
                document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
                document.querySelector(`.tab-button[data-tab="${tabName}"]`).classList.add('active');
                
                document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
                document.getElementById(`${tabName}-tab`).classList.add('active');

                // Trigger Gemini analysis when the tab becomes active
                if (tabName === 'gemini-analysis') {
                    this.requestGeminiAnalysis();
                }
            }

            // --- Formatting Helpers ---
            formatPrice(price) {
                if (price === null || price === undefined || isNaN(price)) return '-';
                const absPrice = Math.abs(price);
                if (absPrice >= 1000) return price.toFixed(2); // e.g. BTC
                if (absPrice >= 100) return price.toFixed(3); // e.g. ETH
                if (absPrice >= 10) return price.toFixed(4);
                if (absPrice >= 1) return price.toFixed(5);
                if (absPrice >= 0.01) return price.toFixed(6);
                return price.toFixed(8); // For very small price assets
            }

            formatVolume(volume) {
                if (volume === null || volume === undefined || isNaN(volume)) return '-';
                if (volume >= 1e9) return (volume / 1e9).toFixed(2) + 'B';
                if (volume >= 1e6) return (volume / 1e6).toFixed(2) + 'M';
                if (volume >= 1e3) return (volume / 1e3).toFixed(2) + 'K';
                return volume.toFixed(0);
            }
            
            formatTime(timestamp) {
                const date = new Date(timestamp);
                return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            }

            // --- Notification System ---
            showNotification(message, type = 'info', duration = 3000) {
                const container = document.getElementById('notificationContainer');
                const notification = document.createElement('div');
                notification.className = `notification ${type}`;
                const title = type.charAt(0).toUpperCase() + type.slice(1);
                
                notification.innerHTML = `
                    <div class="notification-title">${title}</div>
                    <div class="notification-message">${message}</div>
                    <div class="notification-progress" style="animation-duration: ${duration}ms;"></div>
                `;
                container.appendChild(notification);
                
                // Auto-remove notification
                setTimeout(() => {
                    notification.style.opacity = '0';
                    notification.style.transform = 'translateX(100%)'; // Match slideInRight from CSS
                    setTimeout(() => notification.remove(), 300); // Duration of fade-out animation
                }, duration);
            }

            // --- Message Area Display ---
            showError(message) {
                const errorEl = document.getElementById('errorMessage');
                errorEl.textContent = message;
                errorEl.style.display = 'block';
                errorEl.style.opacity = '1'; // Ensure visible
                setTimeout(() => {
                    errorEl.style.opacity = '0';
                    errorEl.addEventListener('transitionend', () => errorEl.style.display = 'none', { once: true });
                }, 5000);
            }

            showWarning(message) {
                const warningEl = document.getElementById('warningMessage');
                warningEl.textContent = message;
                warningEl.style.display = 'block';
                warningEl.style.opacity = '1';
                setTimeout(() => {
                    warningEl.style.opacity = '0';
                    warningEl.addEventListener('transitionend', () => warningEl.style.display = 'none', { once: true });
                }, 5000);
            }

            // --- Caching for Symbols (Frontend) ---
            setCache(key, data, ttl) { // TTL in milliseconds
                const now = Date.now();
                const item = { value: data, expiry: now + ttl };
                this.symbolCache.set(key, JSON.stringify(item));
            }

            getFromCache(key) {
                const itemStr = this.symbolCache.get(key);
                if (!itemStr) return null;
                try {
                    const item = JSON.parse(itemStr);
                    const now = Date.now();
                    if (now > item.expiry) {
                        this.symbolCache.delete(key);
                        return null;
                    }
                    return item.value;
                } catch (e) {
                    console.error("Error parsing cache item:", e);
                    this.symbolCache.delete(key);
                    return null;
                }
            }
            
            // --- Utility to get average volume (used for volume spike signal) ---
            getAverageVolume(klines) {
                if (!klines || klines.length === 0) return 0;
                const totalVolume = klines.reduce((sum, k) => sum + k.volume, 0);
                return totalVolume / klines.length;
            }
        }
        
        document.addEventListener('DOMContentLoaded', () => {
            const terminal = new TradingTerminal();
        });
    </script>
</body>
</html>
```

---

### **Key Improvements and Features:**

**Backend (`app.py`)**:

*   **Gemini Integration**: Core functionality to receive data and query Gemini.
*   **Environment Variables**: Uses `.env` for `GEMINI_API_KEY` and Bybit API base URL.
*   **Logging**: Implemented basic logging for debugging and monitoring.
*   **Error Handling**: More robust error handling for API calls and invalid payloads.
*   **Data Formatting**: Helper functions `format_klines_for_gemini`, `format_indicators_for_gemini`, `format_signals_for_gemini` to structure data clearly for Gemini.
*   **Prompt Engineering**: A more detailed and structured prompt is created for Gemini, providing context and guidance for the analysis.
*   **Caching**: Basic in-memory caching for Bybit API responses to reduce redundant calls.
*   **Production Readiness**: `debug=False` by default and suggestion to use Gunicorn.
*   **Logging of Sensitive Info**: No API keys or sensitive data are logged.

**Frontend (JavaScript)**:

*   **Gemini Analysis Tab**: A new tab is added for displaying Gemini's insights.
*   **`requestGeminiAnalysis()` Function**:
    *   Collects necessary data (`symbol`, `interval`, recent `klines`, formatted `indicators`, `signals`).
    *   Sends a `POST` request to the Flask backend (`/analyze`).
    *   Handles responses, displays analysis, and shows errors.
*   **`displayGeminiAnalysis()`**: Updates the DOM with Gemini's text output.
*   **Dynamic Triggering**: Analysis is triggered when:
    *   The Gemini tab becomes active.
    *   The chart is loaded/refreshed.
    *   Live data updates occur (debounced).
*   **Refined Indicator Calculations**: Ensured indicators are safe for edge cases (e.g., not enough data points).
*   **Improved Charting**:
    *   Dynamic candlestick colors.
    *   Better tooltip formatting using `chartjs-adapter-date-fns`.
    *   Improved y-axis padding and scaling.
    *   More specific dataset labeling for easier `updateChartVisibility`.
    *   MACD Histogram is now plotted as a separate bar chart dataset.
    *   Added `hidden` property to datasets for dynamic toggling.
*   **Robust WebSocket**:
    *   Handles `snapshot` messages.
    *   More robust `onmessage` parsing, checking `type`, `topic`, and `data` structure.
    *   Improved logic for updating/adding candles on live data.
    *   Automatic reconnection attempts on `onclose` if `isLive` is true.
*   **Settings Management**: Enhanced `loadSettings` to include defaults and merge them with saved settings.
*   **UI/UX Enhancements**:
    *   Improved loading states and messages.
    *   Better notification system with progress bar and animations.
    *   Clearer error/warning messages.
    *   Updated `formatPrice` for better precision handling across different price ranges.
    *   Updated `formatVolume` for larger numbers.
    *   Added CSS for `stat-value` positive/negative/neutral classes.
    *   Responsive design improvements for tab buttons and notifications.
*   **Code Structure**:
    *   Indicators are now within the `TradingTerminal` class for better organization.
    *   Helper methods for formatting data and setting stat values.
    *   A `resetChartAndAnalysis` method to clear all chart-related data and tab content.
    *   Debouncing for live Gemini analysis requests.

---

### **How to Run:**

1.  **Backend:**
    *   Navigate to your backend directory in the terminal.
    *   Create `.env` with your `GEMINI_API_KEY` and `BYBIT_API_BASE_URL`.
    *   Run: `pip install -r requirements.txt`
    *   Run: `python app.py`

2.  **Frontend:**
    *   Save the complete HTML/JavaScript code as `index.html`.
    *   Open `index.html` in your web browser.

Now you have a fully integrated trading terminal with AI-powered analysis capabilities!
