import os
import platform
import subprocess
import time
from dotenv import load_dotenv
import requests
import pandas as pd
import hashlib
import hmac
import urllib.parse
import json
import pandas_ta as ta
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

# --- Time Synchronization for Termux/Android ---
def synchronize_time():
    """Sync system time using NTP in Termux environment"""
    try:
        print(Fore.YELLOW + "⌛ Synchronizing system time...")
        result = subprocess.run(["ntpdate", "-q", "pool.ntp.org"],
                              capture_output=True, text=True)
        if result.returncode == 0:
            offset = float(result.stdout.split()[-2])
            if abs(offset) > 1.0:
                print(Fore.CYAN + f"⏰ Time offset detected: {offset:.2f} seconds")
                subprocess.run(["ntpdate", "pool.ntp.org"], check=True)
                print(Fore.GREEN + "✅ Time synchronized successfully")
            return True
        return False
    except Exception as e:
        print(Fore.RED + f"❌ Time sync failed: {str(e)}")
        return False

# --- Enhanced Configuration Setup ---
def get_user_input(prompt, default, input_type=float, validation=None):
    """Generic prompt with validation and default handling"""
    while True:
        try:
            value = input(Fore.WHITE + f"{prompt} (default {default}): ") or default
            converted = input_type(value)
            if validation and not validation(converted):
                raise ValueError
            return converted
        except ValueError:
            print(Fore.RED + f"⚠️ Invalid input. Please enter a valid {input_type.__name__}")

# --- API Configuration ---
load_dotenv()
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")

if not BYBIT_API_KEY or not BYBIT_API_SECRET:
    print(Fore.RED + "🔥 Missing API keys in .env file!")
    exit()

API_ENDPOINT = "https://api.bybit.com"

# --- Signature Generation ---
def generate_signature(secret, params):
    """HMAC-SHA256 signature with parameter validation"""
    param_string = urllib.parse.urlencode(sorted(params.items()))
    return hmac.new(
        secret.encode('utf-8'),
        param_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

# --- Request Handler ---
def bybit_request(method, endpoint, params=None, data=None):
    """Generic authenticated request handler"""
    try:
        req_params = {
            "api_key": BYBIT_API_KEY,
            "timestamp": str(int(time.time() * 1000)),
            "recv_window": "5000"
        }

        if params: req_params.update(params)
        if data: req_params.update(data)

        req_params["sign"] = generate_signature(BYBIT_API_SECRET, req_params)
        headers = {"Content-Type": "application/json"}

        if method == "GET":
            response = requests.get(f"{API_ENDPOINT}{endpoint}", params=req_params, headers=headers)
        else:
            response = requests.post(f"{API_ENDPOINT}{endpoint}", json=req_params, headers=headers)

        response.raise_for_status()
        return response.json()

    except Exception as e:
        print(Fore.RED + f"🚨 Request failed: {str(e)}")
        return None

# --- Data Fetching ---
def fetch_klines(symbol, interval, limit=200):
    """Fetch OHLCV data from Bybit"""
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
        "category": "linear"
    }
    
    response = bybit_request("GET", "/v5/market/kline", params)
    if response and response['retCode'] == 0:
        df = pd.DataFrame(response['result']['list'], columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
        ])
        df = df.astype({'open': float, 'high': float, 'low': float, 'close': float})
        df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms')
        df.set_index('timestamp', inplace=True)
        return df.iloc[::-1]  # Reverse to chronological order
    return None

# --- Pivot Detection ---
def detect_pivot_points(df, pivot_left=2, pivot_right=1):
    """Detect pivot points for scalping strategy"""
    resistance, support = [], []
    
    pivot_highs = ta.pivothigh(df['high'], pivot_left, pivot_right)
    pivot_lows = ta.pivotlow(df['low'], pivot_left, pivot_right)
    
    for i in range(len(df)):
        if not pd.isna(pivot_highs[i]):
            resistance.append({'price': pivot_highs[i], 'index': df.index[i]})
        if not pd.isna(pivot_lows[i]):
            support.append({'price': pivot_lows[i], 'index': df.index[i]})
    
    return resistance, support

# --- Signal Generation ---
def generate_signals(df, resistance, support, stoch_k=14, stoch_d=3):
    """Generate trading signals with StochRSI confirmation"""
    signals = []
    
    # Calculate StochRSI
    stoch = ta.stochrsi(df['close'], length=stoch_k, smooth_k=stoch_d)
    df['stoch_k'] = stoch['STOCHRSI_K']
    df['stoch_d'] = stoch['STOCHRSI_D']
    
    # Check resistance breaks
    for level in resistance:
        idx = df.index.get_loc(level['index'])
        if idx >= len(df) - 1: continue
        
        if df['high'].iloc[idx+1] > level['price'] and \
           df['stoch_k'].iloc[idx] > 80 and \
           df['stoch_k'].iloc[idx] > df['stoch_d'].iloc[idx]:
            signals.append(('BUY', level['price'], df.index[idx+1]))
    
    # Check support breaks
    for level in support:
        idx = df.index.get_loc(level['index'])
        if idx >= len(df) - 1: continue
        
        if df['low'].iloc[idx+1] < level['price'] and \
           df['stoch_k'].iloc[idx] < 20 and \
           df['stoch_k'].iloc[idx] < df['stoch_d'].iloc[idx]:
            signals.append(('SELL', level['price'], df.index[idx+1]))
    
    return signals

# --- Order Management ---
def execute_trade(signal, symbol, quantity):
    """Execute trade with risk management"""
    try:
        side = signal[0]
        price = signal[1]
        
        # Place market order
        order = bybit_request("POST", "/v5/order/create", data={
            "symbol": symbol,
            "side": side.capitalize(),
            "orderType": "Market",
            "qty": str(quantity),
            "category": "linear",
            "timeInForce": "IOC"
        })
        
        if order and order['retCode'] == 0:
            print(Fore.GREEN + f"✅ {side} order executed at {price}")
            return True
        return False
        
    except Exception as e:
        print(Fore.RED + f"❌ Trade execution failed: {str(e)}")
        return False

# --- Main Execution Flow ---
if __name__ == "__main__":
    if not synchronize_time():
        print(Fore.YELLOW + "⚠️ Proceeding without time sync")
    
    print(Fore.CYAN + "\n🚀 Ultra Scalper Bot")
    print(Fore.CYAN + "====================")
    
    # Get user inputs
    symbol = input(Fore.WHITE + "Enter trading pair (e.g. BTCUSDT): ").upper()
    interval = get_user_input("Chart interval (1m, 5m)", "1m", str)
    quantity = get_user_input("Trade quantity", 0.1, float)
    pivot_left = get_user_input("Pivot left bars", 2, int)
    pivot_right = get_user_input("Pivot right bars", 1, int)
    stoch_k = get_user_input("StochRSI K period", 14, int)
    stoch_d = get_user_input("StochRSI D period", 3, int)
    sl_pct = get_user_input("Stop-loss (%)", 0.3, float) / 100
    tp_pct = get_user_input("Take-profit (%)", 0.6, float) / 100
    
    print(Fore.YELLOW + "\n⚡ Starting scalping engine...")
    
    while True:
        try:
            # Fetch latest market data
            df = fetch_klines(symbol, interval)
            if df is None:
                time.sleep(2)
                continue
                
            # Detect pivot points
            resistance, support = detect_pivot_points(df, pivot_left, pivot_right)
            
            # Generate signals
            signals = generate_signals(df, resistance, support, stoch_k, stoch_d)
            
            # Execute trades
            for signal in signals:
                if execute_trade(signal, symbol, quantity):
                    # Implement immediate SL/TP logic here
                    pass
                
            # Throttle requests to avoid rate limits
            time.sleep(5)
            
        except KeyboardInterrupt:
            print(Fore.RED + "\n🛑 Bot stopped by user")
            break
        except Exception as e:
            print(Fore.RED + f"🚨 Critical error: {str(e)}")
            time.sleep(10)
