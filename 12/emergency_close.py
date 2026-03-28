
import os
import time
import hmac
import hashlib
import requests
import json
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")

def generate_signature(api_key, api_secret, params, timestamp):
    param_json = json.dumps(params) if params else ""
    raw_str = timestamp + api_key + "5000" + param_json
    return hmac.new(api_secret.encode(), raw_str.encode(), hashlib.sha256).hexdigest()

def request_bybit(method, endpoint, params=None):
    timestamp = str(int(time.time() * 1000))
    params = params or {}
    headers = {
        "Content-Type": "application/json",
        "X-BAPI-API-KEY": API_KEY,
        "X-BAPI-RECV-WINDOW": "5000",
        "X-BAPI-TIMESTAMP": timestamp,
    }
    
    if method == "GET":
        sorted_params = sorted(params.items())
        query_string = "&".join([f"{k}={v}" for k, v in sorted_params])
        raw_str = timestamp + API_KEY + "5000" + query_string
        headers["X-BAPI-SIGN"] = hmac.new(API_SECRET.encode(), raw_str.encode(), hashlib.sha256).hexdigest()
    else:
        headers["X-BAPI-SIGN"] = generate_signature(API_KEY, API_SECRET, params, timestamp)

    url = f"https://api.bybit.com{endpoint}"
    proxies = {
        "http": "socks5h://127.0.0.1:9050",
        "https": "socks5h://127.0.0.1:9050",
    }
    
    try:
        if method == "POST":
            response = requests.post(url, headers=headers, json=params, proxies=proxies, timeout=10)
        else:
            response = requests.get(url, headers=headers, params=params, proxies=proxies, timeout=10)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

# 1. Get Open Positions
positions_res = request_bybit("GET", "/v5/position/list", {"category": "linear", "settleCoin": "USDT"})

if positions_res.get("retCode") == 0:
    positions = positions_res["result"]["list"]
    for pos in positions:
        size = float(pos["size"])
        if size > 0:
            symbol = pos["symbol"]
            side = "Sell" if pos["side"] == "Buy" else "Buy"
            print(f"Closing {pos['side']} position for {symbol} (Size: {size})")
            
            close_params = {
                "category": "linear",
                "symbol": symbol,
                "side": side,
                "orderType": "Market",
                "qty": pos["size"],
                "reduceOnly": True
            }
            res = request_bybit("POST", "/v5/order/create", close_params)
            print(f"Result: {json.dumps(res, indent=2)}")
else:
    print("Failed to fetch positions.")
