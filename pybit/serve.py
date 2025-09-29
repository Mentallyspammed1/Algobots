#!/usr/bin/env python

import logging  # Import logging module

import requests
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS for the frontend

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# --- Bybit API Configuration ---
BYBIT_API_URL = "https://api.bybit.com/v5/market/kline"
SYMBOL = "BTCUSDT"
INTERVAL = "1"  # 1-minute candles
LIMIT = 500  # Number of bars to fetch

# --- Indicator Calculation Parameters ---
# These parameters are crucial for the strategy's logic.
# Adjust them based on your testing and strategy requirements.
ATR_PERIOD = 14
CHANDELIER_MULTIPLIER = 3.0
TREND_EMA_PERIOD = 50
SHORT_EMA_PERIOD = 12
LONG_EMA_PERIOD = 26
RSI_PERIOD = 14
MACD_SIGNAL_PERIOD = 9
ADX_PERIOD = 14
ADX_THRESHOLD = 20  # Minimum ADX value to consider a trend strong enough
VOLUME_MA_PERIOD = 20
VOLUME_SPIKE_THRESHOLD = 1.5  # Volume must be X times the MA to confirm a signal


# --- Indicator Calculation Functions ---


def calculate_ema(data, period):
    """Calculates Exponential Moving Average (EMA)."""
    if not data or len(data) < period:
        return [None] * len(data)

    ema_values = [None] * (period - 1)
    smoothing_factor = 2 / (period + 1)

    # Initial EMA is a simple average of the first 'period' values
    try:
        initial_sum = sum(d["close"] for d in data[:period])
        ema_values.append(initial_sum / period)
    except (
        KeyError,
        TypeError,
    ):  # Handle cases where 'close' might be missing or not a number
        logging.warning("Error calculating initial EMA sum. Data might be malformed.")
        return [None] * len(data)  # Return None for all if initial calc fails

    # Calculate subsequent EMA values
    for i in range(period, len(data)):
        prev_ema = ema_values[-1]
        try:
            current_close = data[i]["close"]
            if (
                prev_ema is None or current_close is None
            ):  # Skip if previous EMA or current close is None
                ema_values.append(None)
                continue
            current_ema = (current_close - prev_ema) * smoothing_factor + prev_ema
            ema_values.append(current_ema)
        except (KeyError, TypeError):  # Handle missing 'close' or non-numeric values
            logging.warning(
                f"Skipping EMA calculation for index {i} due to data error."
            )
            ema_values.append(None)

    return ema_values


def calculate_rsi(data, period):
    """Calculates Relative Strength Index (RSI) using Wilder's smoothing method."""
    if not data or len(data) < period + 1:
        return [None] * len(data)

    gains = [0.0] * len(data)
    losses = [0.0] * len(data)
    for i in range(1, len(data)):
        try:
            change = data[i]["close"] - data[i - 1]["close"]
            if change > 0:
                gains[i] = change
            else:
                losses[i] = abs(change)
        except (KeyError, TypeError):  # Handle missing 'close' or non-numeric values
            logging.warning(
                f"Skipping RSI gain/loss calculation for index {i} due to data error."
            )
            # Keep gains/losses as 0 for this iteration if error occurs

    # Initial Average Gain and Loss for the first 'period'
    try:
        avg_gain = sum(gains[1 : period + 1]) / period
        avg_loss = sum(losses[1 : period + 1]) / period
    except (ValueError, TypeError):  # Handle potential empty slices or non-numeric sums
        logging.warning("Error calculating initial average gain/loss for RSI.")
        return [None] * len(data)

    rsi_values = [None] * period  # RSI needs 'period' bars to start calculation

    def calculate_single_rsi(avg_gain, avg_loss):
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    # Calculate first RSI value if possible
    if avg_gain is not None and avg_loss is not None:
        try:
            rsi_values.append(calculate_single_rsi(avg_gain, avg_loss))
        except (
            ValueError,
            TypeError,
        ):  # Catch division by zero if avg_loss somehow is zero again
            rsi_values.append(None)
    else:
        rsi_values.append(None)

    # Calculate subsequent RSI values using Wilder's smoothing
    for i in range(period + 1, len(data)):
        try:
            prev_avg_gain = (
                avg_gain  # Use the last calculated avg_gain/loss for smoothing
            )
            prev_avg_loss = avg_loss

            avg_gain = ((prev_avg_gain * (period - 1)) + gains[i]) / period
            avg_loss = ((prev_avg_loss * (period - 1)) + losses[i]) / period

            if avg_loss == 0:  # Handle division by zero
                rsi_values.append(100.0)
            else:
                rs = avg_gain / avg_loss
                rsi_values.append(100.0 - (100.0 / (1.0 + rs)))
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as e:
            logging.warning(f"Skipping RSI calculation for index {i} due to error: {e}")
            rsi_values.append(None)
            # Reset avg_gain/loss if calculation fails to prevent propagating errors
            avg_gain = None
            avg_loss = None

    return rsi_values


def calculate_atr(data, period):
    """Calculates Average True Range (ATR) using Wilder's smoothing."""
    if not data or len(data) < period + 1:
        return [None] * len(data)

    tr_values = []
    for i in range(1, len(data)):
        try:
            high = data[i]["high"]
            low = data[i]["low"]
            prev_close = data[i - 1]["close"]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_values.append(tr)
        except (KeyError, TypeError):
            logging.warning(
                f"Skipping ATR calculation for index {i} due to data error."
            )
            tr_values.append(None)  # Append None if data is bad

    # Initial ATR calculation
    initial_tr_slice = [v for v in tr_values[:period] if v is not None]
    if not initial_tr_slice or len(initial_tr_slice) < period:
        logging.warning("Not enough valid TR values for initial ATR calculation.")
        return [None] * len(data)

    initial_atr = sum(initial_tr_slice) / period
    atr_values = [None] * period  # ATR needs 'period' bars to start calculation
    atr_values.append(initial_atr)

    # Calculate subsequent ATR values
    for i in range(period, len(tr_values)):
        prev_atr = atr_values[-1]
        current_tr = tr_values[i]

        if (
            prev_atr is None or current_tr is None
        ):  # Skip if previous ATR or current TR is None
            atr_values.append(None)
            continue

        atr = (prev_atr * (period - 1) + current_tr) / period
        atr_values.append(atr)

    return atr_values


def calculate_macd(data, short_period, long_period, signal_period):
    """Calculates MACD, Signal Line, and Histogram."""
    short_ema = calculate_ema(data, short_period)
    long_ema = calculate_ema(data, long_period)

    macd_line = []
    for i in range(len(data)):
        if short_ema[i] is not None and long_ema[i] is not None:
            macd_line.append(short_ema[i] - long_ema[i])
        else:
            macd_line.append(None)

    # Prepare data for signal line calculation (EMA of MACD line)
    macd_data_for_ema = [{"close": val} for val in macd_line if val is not None]

    # Calculate signal line EMA on the MACD line values
    temp_signal_line = calculate_ema(macd_data_for_ema, signal_period)

    # Reconstruct signal_line to match the length of macd_line, padding with None at the beginning
    signal_line = [None] * (len(macd_line) - len(temp_signal_line))
    signal_line.extend(temp_signal_line)

    # Calculate Histogram
    hist = []
    for i in range(len(macd_line)):
        if macd_line[i] is not None and signal_line[i] is not None:
            hist.append(macd_line[i] - signal_line[i])
        else:
            hist.append(None)

    return macd_line, signal_line, hist


def calculate_adx(highs, lows, closes, period):
    """Calculates ADX, +DI, and -DI."""
    if not closes or len(closes) < period:
        return [None] * len(closes), [None] * len(closes), [None] * len(closes)

    plus_dm = [0.0] * len(closes)
    minus_dm = [0.0] * len(closes)

    for i in range(1, len(closes)):
        try:
            up_move = highs[i] - highs[i - 1]
            down_move = lows[i - 1] - lows[i]

            # Ensure moves are non-negative and check conditions
            if up_move > 0 and up_move > down_move:
                plus_dm[i] = up_move

            if down_move > 0 and down_move > up_move:
                minus_dm[i] = down_move
        except (KeyError, TypeError):
            logging.warning(
                f"Skipping ADX DM calculation for index {i} due to data error."
            )
            plus_dm[i] = 0.0  # Default to 0 if error
            minus_dm[i] = 0.0

    # Calculate ATR (required for DI) - needs data in specific format
    atr_data_for_calc = []
    for i in range(len(closes)):
        try:
            atr_data_for_calc.append(
                {"high": highs[i], "low": lows[i], "close": closes[i]}
            )
        except (KeyError, TypeError):
            logging.warning(f"Skipping ATR data prep for index {i} in ADX calc.")
            atr_data_for_calc.append(
                {"high": None, "low": None, "close": None}
            )  # Placeholder

    atr_values = calculate_atr(atr_data_for_calc, period)

    plus_di = [None] * len(closes)
    minus_di = [None] * len(closes)

    # Calculate DI values
    for i in range(period, len(closes)):
        # Sum DM over the period, skipping None values
        sum_plus_dm = sum(v for v in plus_dm[i - period + 1 : i + 1] if v is not None)
        sum_minus_dm = sum(v for v in minus_dm[i - period + 1 : i + 1] if v is not None)

        current_atr = atr_values[i]

        if current_atr is not None and current_atr > 0:
            plus_di[i] = 100.0 * (sum_plus_dm / current_atr)
            minus_di[i] = 100.0 * (sum_minus_dm / current_atr)
        else:
            # If ATR is None or 0, DI cannot be reliably calculated for this point.
            # In some implementations, 0 is used, but None indicates missing data.
            plus_di[i] = None
            minus_di[i] = None

    # Calculate Directional Index (DX)
    dx_values = [None] * len(closes)
    for i in range(len(closes)):
        pdi = plus_di[i]
        mdi = minus_di[i]
        if pdi is not None and mdi is not None:
            sum_di = pdi + mdi
            if sum_di > 0:
                dx = 100.0 * abs(pdi - mdi) / sum_di
                dx_values[i] = dx
            else:
                dx_values[i] = 0.0  # If sum_di is 0, DX is 0

    # Calculate ADX using EMA on DX values
    # Need to wrap dx_values in the format expected by calculate_ema
    dx_data_for_ema = [{"close": val} for val in dx_values if val is not None]
    temp_adx_values = calculate_ema(dx_data_for_ema, period)

    # Reconstruct adx_values to match the length of closes, padding with None at the beginning
    adx_values = [None] * (len(closes) - len(temp_adx_values))
    adx_values.extend(temp_adx_values)

    return adx_values, plus_di, minus_di


def calculate_vwap(data):
    """Calculates Volume Weighted Average Price (VWAP). VWAP is typically reset daily.
    For simplicity here, it's calculated continuously. For a true daily reset,
    logic would need to check for new days.
    """
    vwap_values = []
    cumulative_volume = 0.0
    cumulative_volume_price = 0.0

    for d in data:
        try:
            volume = d["volume"]
            close_price = d["close"]

            if volume is None or close_price is None:
                vwap_values.append(
                    None
                )  # Cannot calculate if volume or price is missing
                continue

            cumulative_volume += volume
            cumulative_volume_price += volume * close_price

            if cumulative_volume > 0:
                vwap_values.append(cumulative_volume_price / cumulative_volume)
            else:
                vwap_values.append(None)  # Avoid division by zero
        except (KeyError, TypeError):
            logging.warning("Skipping VWAP calculation for a data point due to error.")
            vwap_values.append(None)

    return vwap_values


@app.route("/api/data")
def get_bybit_data():
    """Fetches and processes Bybit data for the frontend."""
    try:
        params = {
            "category": "linear",  # Assuming linear perpetual contracts
            "symbol": SYMBOL,
            "interval": INTERVAL,
            "limit": LIMIT,
        }
        logging.info(f"Fetching K-line data from Bybit API: {params}")
        response = requests.get(BYBIT_API_URL, params=params)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

        api_result = response.json()
        raw_data = api_result.get("result", {}).get("list", [])

        if not raw_data:
            logging.warning("No data received from Bybit API.")
            return jsonify(
                {
                    "error": "No data received from Bybit API for the specified symbol and interval."
                }
            ), 404

        # Format and reverse the data to have the oldest first
        formatted_data = []
        for bar in raw_data[::-1]:
            try:
                # Bybit timestamps are often in milliseconds, convert to seconds for JS
                timestamp = int(bar[0]) / 1000
                formatted_data.append(
                    {
                        "time": timestamp,
                        "open": float(bar[1]),
                        "high": float(bar[2]),
                        "low": float(bar[3]),
                        "close": float(bar[4]),
                        "volume": float(bar[5]),
                    }
                )
            except (IndexError, ValueError, TypeError) as e:
                logging.warning(f"Skipping malformed bar data: {bar} - Error: {e}")
                continue  # Skip this bar if data format is unexpected

        if not formatted_data:
            logging.error("All bars processed resulted in malformed data.")
            return jsonify(
                {"error": "Failed to parse any valid bar data from API response."}
            ), 500

        # Extract OHLCV data for calculations
        closes = [d["close"] for d in formatted_data]
        highs = [d["high"] for d in formatted_data]
        lows = [d["low"] for d in formatted_data]
        volumes = [d["volume"] for d in formatted_data]

        # --- Calculate all Indicators ---
        trend_ema = calculate_ema(formatted_data, TREND_EMA_PERIOD)
        short_ema = calculate_ema(formatted_data, SHORT_EMA_PERIOD)
        long_ema = calculate_ema(formatted_data, LONG_EMA_PERIOD)
        rsi = calculate_rsi(formatted_data, RSI_PERIOD)
        macd_line, signal_line, macd_hist = calculate_macd(
            formatted_data, SHORT_EMA_PERIOD, LONG_EMA_PERIOD, MACD_SIGNAL_PERIOD
        )
        adx, plus_di, minus_di = calculate_adx(highs, lows, closes, ADX_PERIOD)
        atr = calculate_atr(formatted_data, ATR_PERIOD)
        volume_ma = calculate_ema([{"close": vol} for vol in volumes], VOLUME_MA_PERIOD)
        vwap = calculate_vwap(formatted_data)  # Added VWAP calculation

        # --- Chandelier Exit Calculation ---
        # This calculation needs access to highs, lows, and ATR over a period.
        chandelier_long_vals = [None] * len(formatted_data)
        chandelier_short_vals = [None] * len(formatted_data)

        # We need to ensure we have enough ATR data before calculating Chandelier
        for i in range(ATR_PERIOD - 1, len(formatted_data)):
            if atr[i] is not None:
                # Get the relevant slice of data for high/low range calculation
                relevant_highs = highs[max(0, i - ATR_PERIOD + 1) : i + 1]
                relevant_lows = lows[max(0, i - ATR_PERIOD + 1) : i + 1]

                if relevant_highs and relevant_lows:
                    highest_high = max(relevant_highs)
                    lowest_low = min(relevant_lows)

                    chandelier_long_vals[i] = highest_high - (
                        atr[i] * CHANDELIER_MULTIPLIER
                    )
                    chandelier_short_vals[i] = lowest_low + (
                        atr[i] * CHANDELIER_MULTIPLIER
                    )

        # --- Generate Trading Signal ---
        current_signal = "neutral"

        # Get the latest valid data point for signal calculation
        last_valid_index = -1
        for i in range(len(formatted_data) - 1, -1, -1):
            if (
                closes[i] is not None
                and volumes[i] is not None
                and short_ema[i] is not None
                and long_ema[i] is not None
                and trend_ema[i] is not None
                and rsi[i] is not None
                and macd_line[i] is not None
                and signal_line[i] is not None
                and adx[i] is not None
                and chandelier_long_vals[i] is not None
                and chandelier_short_vals[i] is not None
                and volume_ma[i] is not None
            ):
                last_valid_index = i
                break

        if last_valid_index != -1:
            last_candle = formatted_data[last_valid_index]
            last_close = closes[last_valid_index]
            last_volume = volumes[last_valid_index]
            last_short_ema = short_ema[last_valid_index]
            last_long_ema = long_ema[last_valid_index]
            last_trend_ema = trend_ema[last_valid_index]
            last_rsi = rsi[last_valid_index]
            last_volume_ma = volume_ma[last_valid_index]
            last_macd = macd_line[last_valid_index]
            last_macd_signal = signal_line[last_valid_index]
            last_adx = adx[last_valid_index]
            last_chandelier_long = chandelier_long_vals[last_valid_index]
            last_chandelier_short = chandelier_short_vals[last_valid_index]

            # --- Buy Entry Condition ---
            buy_entry_condition = (
                last_short_ema > last_long_ema
                and last_close > last_trend_ema
                and last_close > last_chandelier_long  # Price above upper Chandelier
                and last_rsi < 70  # RSI not overbought
                and last_volume
                > (last_volume_ma * VOLUME_SPIKE_THRESHOLD)  # Volume spike confirmation
                and last_macd > last_macd_signal  # MACD crossover confirmation
                and last_adx > ADX_THRESHOLD  # Trend strength confirmation
            )

            # --- Sell Entry Condition ---
            sell_entry_condition = (
                last_short_ema < last_long_ema
                and last_close < last_trend_ema
                and last_close < last_chandelier_short  # Price below lower Chandelier
                and last_rsi > 30  # RSI not oversold
                and last_volume
                > (last_volume_ma * VOLUME_SPIKE_THRESHOLD)  # Volume spike confirmation
                and last_macd < last_macd_signal  # MACD crossover confirmation
                and last_adx > ADX_THRESHOLD  # Trend strength confirmation
            )

            if buy_entry_condition:
                current_signal = "buy"
            elif sell_entry_condition:
                current_signal = "sell"
        else:
            logging.warning("Could not find a valid data point for signal generation.")
            # If no valid data, signal remains 'neutral' and all indicators will show '--'

        # --- Prepare Response Data ---
        # Ensure all lists have the same length as formatted_data by padding with None
        # This is crucial for frontend chart libraries to render correctly
        def pad_list(lst, target_length, default_value=None):
            if len(lst) < target_length:
                return [default_value] * (target_length - len(lst)) + lst
            return lst  # No padding needed if list is already long enough

        response_data = {
            "candles": formatted_data,
            "trend_ema": pad_list(trend_ema, len(formatted_data)),
            "ema_short": pad_list(short_ema, len(formatted_data)),
            "ema_long": pad_list(long_ema, len(formatted_data)),
            "rsi": pad_list(rsi, len(formatted_data)),
            "macd_line": pad_list(macd_line, len(formatted_data)),
            "signal_line": pad_list(signal_line, len(formatted_data)),
            "macd_hist": pad_list(macd_hist, len(formatted_data)),
            "adx": pad_list(adx, len(formatted_data)),
            "plus_di": pad_list(plus_di, len(formatted_data)),
            "minus_di": pad_list(minus_di, len(formatted_data)),
            "chandelier_long": pad_list(chandelier_long_vals, len(formatted_data)),
            "chandelier_short": pad_list(chandelier_short_vals, len(formatted_data)),
            "volume": pad_list(volumes, len(formatted_data)),  # Added volume
            "volume_ma": pad_list(volume_ma, len(formatted_data)),  # Added volume MA
            "vwap": pad_list(vwap, len(formatted_data)),  # Added VWAP
            "current_signal": current_signal,
            "last_close": formatted_data[-1]["close"]
            if formatted_data
            else None,  # Get last close from the latest valid candle
        }

        logging.info(
            f"Successfully processed data. {len(formatted_data)} candles, signal: {current_signal}"
        )
        return jsonify(response_data)

    except requests.exceptions.HTTPError as e:
        logging.error(
            f"HTTP error fetching data from Bybit: {e.response.status_code} - {e.response.text}"
        )
        return jsonify(
            {
                "error": f"HTTP error from Bybit API: {e.response.status_code}. Please check SYMBOL, INTERVAL, and API limits."
            }
        ), 500
    except requests.exceptions.ConnectionError as e:
        logging.error(f"Connection error fetching data from Bybit: {e}")
        return jsonify(
            {
                "error": "Could not connect to Bybit API. Check your internet connection or Bybit server status."
            }
        ), 500
    except requests.exceptions.Timeout as e:
        logging.error(f"Timeout error fetching data from Bybit: {e}")
        return jsonify(
            {"error": "Request to Bybit API timed out. Try again later."}
        ), 500
    except requests.exceptions.RequestException as e:
        logging.error(f"An unexpected error occurred during Bybit API request: {e}")
        return jsonify(
            {"error": "An unexpected error occurred while fetching data from Bybit."}
        ), 500
    except Exception:
        # Catch-all for unexpected errors during data processing
        logging.exception("An unexpected error occurred during data processing.")
        return jsonify(
            {"error": "An internal error occurred while processing data."}
        ), 500


@app.route("/")
def serve_index():
    """Serves the frontend index.html file."""
    try:
        return send_from_directory(".", "index.html")
    except FileNotFoundError:
        logging.error("index.html not found in the current directory.")
        return "Error: index.html not found.", 404


if __name__ == "__main__":
    # Use debug=True for development, but set to False for production
    # app.run(host='0.0.0.0', port=5000, debug=True)
    logging.info("Starting Flask server on http://0.0.0.0:5000")
    print(
        "Starting server. To access the app, open your web browser and go to http://127.0.0.1:5000"
    )
    app.run(host="0.0.0.0", port=5000)
