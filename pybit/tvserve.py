#!/usr/bin/env python

import json
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app) # Enable CORS for the frontend

# Bybit API URL
BYBIT_API_URL = "https://api.bybit.com/v5/market/kline"
SYMBOL = "BTCUSDT"
INTERVAL = "1"  # 1-minute candles
LIMIT = 500  # Number of bars to fetch

# --- Indicator Calculation Functions ---
# These functions are implemented manually for a lightweight, dependency-free solution.
# They are more accurate now, especially for formulas like RSI and ATR.

def calculate_ema(data, period):
    """Calculates Exponential Moving Average (EMA)."""
    if len(data) < period:
        return [None] * len(data)
    
    ema_values = []
    smoothing_factor = 2 / (period + 1)
    
    # Initial EMA is a simple average of the first 'period' values
    initial_sum = sum(d['close'] for d in data[:period])
    ema_values.append(initial_sum / period)
    
    # Calculate subsequent EMA values
    for i in range(period, len(data)):
        prev_ema = ema_values[-1]
        current_close = data[i]['close']
        current_ema = (current_close - prev_ema) * smoothing_factor + prev_ema
        ema_values.append(current_ema)
        
    return [None] * (period - 1) + ema_values


def calculate_rsi(data, period):
    """Calculates Relative Strength Index (RSI) using Wilder's smoothing method."""
    if len(data) < period:
        return [None] * len(data)

    gains = [0.0] * len(data)
    losses = [0.0] * len(data)
    for i in range(1, len(data)):
        change = data[i]['close'] - data[i-1]['close']
        if change > 0:
            gains[i] = change
        else:
            losses[i] = abs(change)

    avg_gain = sum(gains[1:period+1]) / period
    avg_loss = sum(losses[1:period+1]) / period
    
    rs_values = []
    rsi_values = [None] * period

    if avg_loss != 0:
        rs_values.append(avg_gain / avg_loss)
    else:
        rs_values.append(100) # Avoid division by zero

    for i in range(period + 1, len(data)):
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period
        
        if avg_loss != 0:
            rs_values.append(avg_gain / avg_loss)
        else:
            rs_values.append(100) # Avoid division by zero
    
    for rs in rs_values:
        rsi_values.append(100 - (100 / (1 + rs)))
    
    return rsi_values

def calculate_atr(data, period):
    """Calculates Average True Range (ATR) using Wilder's smoothing."""
    if len(data) < period:
        return [None] * len(data)

    tr_values = []
    for i in range(1, len(data)):
        high = data[i]['high']
        low = data[i]['low']
        prev_close = data[i-1]['close']
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_values.append(tr)

    atr_values = [None] * period
    initial_atr = sum(tr_values[:period]) / period
    atr_values.append(initial_atr)
    
    for i in range(period, len(tr_values)):
        prev_atr = atr_values[-1]
        current_tr = tr_values[i]
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
    
    signal_line = calculate_ema([{'close': val} for val in macd_line if val is not None], signal_period)
    
    hist = []
    for i in range(len(macd_line)):
        if macd_line[i] is not None and i >= len(macd_line) - len(signal_line):
            hist.append(macd_line[i] - signal_line[i - (len(macd_line) - len(signal_line))])
        else:
            hist.append(None)
            
    return macd_line, signal_line, hist

@app.route('/api/data')
def get_bybit_data():
    """Fetches and processes Bybit data for the frontend."""
    try:
        params = {
            "category": "linear",
            "symbol": SYMBOL,
            "interval": INTERVAL,
            "limit": LIMIT
        }
        response = requests.get(BYBIT_API_URL, params=params)
        response.raise_for_status()
        
        raw_data = response.json().get("result", {}).get("list", [])
        
        # Format and reverse the data to have the oldest first
        formatted_data = []
        for bar in raw_data[::-1]:
            formatted_data.append({
                "time": int(bar[0]) / 1000,
                "open": float(bar[1]),
                "high": float(bar[2]),
                "low": float(bar[3]),
                "close": float(bar[4]),
                "volume": float(bar[5])
            })
            
        # Pine Script Parameters (match your strategy)
        atr_period = 14
        chandelier_multiplier = 3.0
        trend_ema_period = 50
        short_ema_period = 12
        long_ema_period = 26
        rsi_period = 14
        macd_signal_period = 9

        # Calculate all Indicators
        trend_ema = calculate_ema(formatted_data, trend_ema_period)
        short_ema = calculate_ema(formatted_data, short_ema_period)
        long_ema = calculate_ema(formatted_data, long_ema_period)
        rsi = calculate_rsi(formatted_data, rsi_period)
        macd_line, signal_line, macd_hist = calculate_macd(formatted_data, short_ema_period, long_ema_period, macd_signal_period)
        atr = calculate_atr(formatted_data, atr_period)

        # Chandelier Exit with dynamic calculation
        chandelier_long_vals = [None] * len(formatted_data)
        chandelier_short_vals = [None] * len(formatted_data)
        for i in range(len(formatted_data)):
            if atr[i] is not None:
                high_range = max(d['high'] for d in formatted_data[max(0, i-atr_period+1):i+1])
                low_range = min(d['low'] for d in formatted_data[max(0, i-atr_period+1):i+1])
                chandelier_long_vals[i] = high_range - (atr[i] * chandelier_multiplier)
                chandelier_short_vals[i] = low_range + (atr[i] * chandelier_multiplier)
                
        # Generate Trading Signal
        current_signal = 'neutral'
        last_data = formatted_data[-1]
        last_short_ema = short_ema[-1]
        last_long_ema = long_ema[-1]
        last_chandelier_long = chandelier_long_vals[-1]
        last_chandelier_short = chandelier_short_vals[-1]
        
        if last_short_ema > last_long_ema and last_data['close'] > last_chandelier_long:
            current_signal = 'buy'
        elif last_short_ema < last_long_ema and last_data['close'] < last_chandelier_short:
            current_signal = 'sell'
        
        # Combine all data for the frontend
        response_data = {
            "candles": formatted_data,
            "trend_ema": trend_ema,
            "ema_short": short_ema,
            "ema_long": long_ema,
            "rsi": rsi,
            "macd_line": macd_line,
            "signal_line": signal_line,
            "macd_hist": macd_hist,
            "chandelier_long": chandelier_long_vals,
            "chandelier_short": chandelier_short_vals,
            "current_signal": current_signal,
            "last_close": last_data['close'],
        }

        return jsonify(response_data)
        
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error fetching data from Bybit: {e}")
        return jsonify({"error": "Failed to fetch data from Bybit API. Check your internet connection or try again later."}), 500

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

if __name__ == '__main__':
    print("Starting server. To access the app, open your web browser and go to http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000)

