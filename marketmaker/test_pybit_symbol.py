import os
from pybit.unified_trading import HTTP
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
TESTNET = os.getenv("BYBIT_TESTNET", "True").lower() == "true"

if not API_KEY or not API_SECRET:
    print("Please set BYBIT_API_KEY and BYBIT_API_SECRET in your .env file.")
    exit()

session = HTTP(testnet=TESTNET, api_key=API_KEY, api_secret=API_SECRET)

try:
    print(f"Attempting to get instruments info for BTCUSDT on testnet={TESTNET}...")
    info = session.get_instruments_info(category="linear", symbol="BTCUSDT")
    print("Successfully retrieved instruments info:")
    print(info)
except Exception as e:
    print(f"An error occurred: {e}")
