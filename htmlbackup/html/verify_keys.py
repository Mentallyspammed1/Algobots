import os

from dotenv import load_dotenv
from pybit.unified_trading import HTTP

load_dotenv()

BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")

if not BYBIT_API_KEY or not BYBIT_API_SECRET:
    print("Error: BYBIT_API_KEY or BYBIT_API_SECRET not found in .env file.")
    exit(1)

session = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

try:
    print("Attempting to fetch wallet balance...")
    balance_res = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")

    if balance_res.get("retCode") == 0:
        print("API Keys are VALID. Wallet Balance Check Successful.")
        if balance_res.get("result") and balance_res["result"].get("list"):
            for item in balance_res["result"]["list"]:
                print(
                    f"  Account Type: {item.get('accountType')}, Total Wallet Balance: {item.get('totalWalletBalance')} {item.get('coin')}"
                )
        else:
            print("  No balance information found.")
    else:
        print(
            f"API Keys are INVALID or connection failed. Error Code: {balance_res.get('retCode')}, Message: {balance_res.get('retMsg')}"
        )
        if balance_res.get("retCode") == 10001:
            print(
                "  (Error 10001 usually means your Bybit account is not a Unified Trading Account (UTA). Please upgrade your account on Bybit.)"
            )

except Exception as e:
    print(f"An unexpected error occurred: {e}")
