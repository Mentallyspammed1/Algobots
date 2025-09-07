import os
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

load_dotenv(dotenv_path='/data/data/com.termux/files/home/Algobots/marketmaker/.env', override=True)

api_key = os.getenv("BYBIT_API_KEY")
api_secret = os.getenv("BYBIT_API_SECRET")

if not api_key or not api_secret:
    print("API key or secret not found in environment variables.")
    exit()

print("Attempting to connect to Bybit with the following keys:")
print(f"API Key: {api_key}")
print(f"API Secret: {'*' * len(api_secret)}") # Mask the secret

session = HTTP(
    testnet=True,
    api_key=api_key,
    api_secret=api_secret,
)

try:
    response = session.get_wallet_balance(accountType="UNIFIED")
    if response['retCode'] == 0:
        print("\nConnection successful!")
        print("Wallet balance:")
        print(response['result']['list'][0])
    else:
        print("\nConnection failed.")
        print(f"Error code: {response['retCode']}")
        print(f"Error message: {response['retMsg']}")
except Exception as e:
    print(f"\nAn exception occurred: {e}")
