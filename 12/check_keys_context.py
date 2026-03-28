
import os
import time
import hmac
import hashlib
import requests
import json
from decimal import Decimal

# Using keys from context
API_KEY = "NRrb4Biggi3sO7rKZ1"
API_SECRET = "TXztLxhYdHIcyzmN6QR2zSc2Dxj0UuQRiMzQ"

def request_bybit(method, endpoint, params=None):
    timestamp = str(int(time.time() * 1000))
    params = params or {}
    headers = {
        "Content-Type": "application/json",
        "X-BAPI-API-KEY": API_KEY,
        "X-BAPI-RECV-WINDOW": "5000",
        "X-BAPI-TIMESTAMP": timestamp,
    }
    
    # Signature for GET/POST
    if method == "GET":
        sorted_params = sorted(params.items())
        query_string = "&".join([f"{k}={v}" for k, v in sorted_params])
        raw_str = timestamp + API_KEY + "5000" + query_string
        headers["X-BAPI-SIGN"] = hmac.new(API_SECRET.encode(), raw_str.encode(), hashlib.sha256).hexdigest()
    else:
        param_json = json.dumps(params) if params else ""
        raw_str = timestamp + API_KEY + "5000" + param_json
        headers["X-BAPI-SIGN"] = hmac.new(API_SECRET.encode(), raw_str.encode(), hashlib.sha256).hexdigest()

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

# 1. Get Wallet Balance
balance = request_bybit("GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED", "coin": "USDT"})
print("--- WALLET BALANCE ---")
print(json.dumps(balance, indent=2))
