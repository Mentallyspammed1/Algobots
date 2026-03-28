
import os
import sys
from decimal import Decimal
from dotenv import load_dotenv

# Add the directory to sys.path to import local modules
sys.path.append('/data/data/com.termux/files/home/Algobots/12/')

from PyrmethusTrendBot import BybitClient

def main():
    load_dotenv('/data/data/com.termux/files/home/Algobots/12/.env')
    
    API_KEY = os.getenv("BYBIT_API_KEY")
    API_SECRET = os.getenv("BYBIT_API_SECRET")
    
    if not API_KEY or not API_SECRET:
        print("Error: API credentials missing in .env")
        return

    client = BybitClient(API_KEY, API_SECRET)
    
    print("--- Account Status ---")
    balance = client.get_wallet_balance()
    print(f"Total Equity: {balance} USDT")
    
    print("\n--- Open Positions ---")
    # Custom request for positions since it's not in BybitClient
    endpoint = "/v5/position/list"
    params = {"category": "linear", "settleCoin": "USDT"}
    res = client.request("GET", endpoint, params)
    
    if res and "list" in res:
        positions = [p for p in res["list"] if float(p.get("size", 0)) != 0]
        if not positions:
            print("No active positions.")
        for p in positions:
            print(f"Symbol: {p['symbol']} | Side: {p['side']} | Size: {p['size']} | UnPnL: {p['unrealisedPnl']}")
    else:
        print("Failed to fetch positions.")

if __name__ == "__main__":
    main()
