import os

from dotenv import load_dotenv

load_dotenv(dotenv_path='/data/data/com.termux/files/home/Algobots/marketmaker/.env')
print(f"BYBIT_API_KEY: |{os.getenv('BYBIT_API_KEY')}|")
print(f"BYBIT_API_SECRET: |{os.getenv('BYBIT_API_SECRET')}|")
