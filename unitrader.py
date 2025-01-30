import os
import time
import logging
import pandas as pd
import requests
import hmac
import hashlib
import urllib.parse
from datetime import datetime
from dotenv import load_dotenv
from colorama import Fore, Style, init
from typing import Dict, List, Optional, Tuple

# Initialize Colorama
init(autoreset=True)

# --- Configuration ---
load_dotenv()
CONFIG = {
    "api_endpoint": "https://api.bybit.com",
    "symbol": os.getenv("TRADING_SYMBOL", "TRUMPUSDT"),
    "interval": "15m",
    "risk_per_trade": 0.01,
    "sl_pct": 0.03,
    "tp_pct": 0.05,
    "max_orders": 5,
    "weights": {
        "high_volatility": {"ema": 1.5, "rsi": 1.2, "macd": 1.3},
        "low_volatility": {"ema": 1.0, "rsi": 1.0, "macd": 1.0}
    }
}

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format=f'{Fore.BLUE}%(asctime)s - {Style.BRIGHT}%(levelname)s{Style.RESET_ALL} - %(message)s'
)
logger = logging.getLogger(__name__)

class UnifiedTrader:
    def __init__(self, paper_mode: bool = False):
        self.paper_mode = paper_mode
        self.api_key = os.getenv("BYBIT_API_KEY")
        self.api_secret = os.getenv("BYBIT_API_SECRET")
        self.position = None
        self.orders = []
        
        if paper_mode:
            self.balance = 10000.0
            logger.info("Running in PAPER TRADING mode")
        else:
            self._validate_api_keys()

    def _validate_api_keys(self):
        if not self.api_key or not self.api_secret:
            logger.error("Missing API keys in .env!")
            raise ValueError("API keys not found")

    # --- Core Trading Components ---
    def generate_signature(self, params: dict) -> str:
        param_string = urllib.parse.urlencode(sorted(params.items()))
        return hmac.new(
            self.api_secret.encode('utf-8'),
            param_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def api_request(self, method: str, endpoint: str, params: dict = None) -> dict:
        try:
            params = params or {}
            params.update({
                "api_key": self.api_key,
                "timestamp": str(int(time.time() * 1000)),
                "recv_window": "5000"
            })
            params["sign"] = self.generate_signature(params)
            
            if method == "GET":
                response = requests.get(f"{CONFIG['api_endpoint']}{endpoint}", params=params)
            else:
                response = requests.post(f"{CONFIG['api_endpoint']}{endpoint}", json=params)
            
            response.raise_for_status()
            return response.json()
        
        except Exception as e:
            logger.error(f"API Request failed: {str(e)}")
            return None

    # --- Technical Indicators ---
    @staticmethod
    def calculate_ema(df: pd.DataFrame, period: int) -> pd.Series:
        return df['close'].ewm(span=period, adjust=False).mean()

    @staticmethod
    def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    # --- Signal Generation ---
    def generate_signal(self, df: pd.DataFrame) -> str:
        # Combined strategy from all components
        signals = []
        
        # EMA Crossover Strategy
        df['ema_fast'] = self.calculate_ema(df, 9)
        df['ema_slow'] = self.calculate_ema(df, 21)
        if df['ema_fast'].iloc[-1] > df['ema_slow'].iloc[-1]:
            signals.append('BUY')
        else:
            signals.append('SELL')

        # RSI Strategy
        rsi = self.calculate_rsi(df)
        if rsi.iloc[-1] < 30:
            signals.append('BUY')
        elif rsi.iloc[-1] > 70:
            signals.append('SELL')

        # Weighted Signal System (from whaler.py)
        signal_score = 0
        for signal in signals:
            signal_score += 1 if signal == 'BUY' else -1
        
        if signal_score >= 2:
            return 'BUY'
        elif signal_score <= -2:
            return 'SELL'
        return 'HOLD'

    # --- Order Management ---
    def execute_trade(self, signal: str, quantity: float):
        if self.paper_mode:
            logger.info(f"PAPER TRADE: {signal} {quantity}")
            return True
            
        endpoint = "/v5/order/create"
        data = {
            "symbol": CONFIG['symbol'],
            "side": "Buy" if signal == 'BUY' else 'Sell',
            "orderType": "Market",
            "qty": str(quantity),
            "category": "linear"
        }
        return self.api_request("POST", endpoint, data)

    # --- Main Loop ---
    def run(self):
        logger.info("Starting Unified Trading Bot")
        
        while True:
            try:
                # Fetch market data
                klines = self.api_request("GET", "/v5/market/kline", {
                    "symbol": CONFIG['symbol'],
                    "interval": CONFIG['interval'],
                    "limit": 100
                })
                
                if not klines or klines['retCode'] != 0:
                    logger.error("Failed to fetch klines")
                    time.sleep(10)
                    continue
                
                # Process data
                df = pd.DataFrame(klines['result']['list'], columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
                ]).astype(float)
                
                # Generate signal
                signal = self.generate_signal(df)
                
                # Execute trade
                if signal in ['BUY', 'SELL']:
                    if len(self.orders) < CONFIG['max_orders']:
                        if self.execute_trade(signal, CONFIG['risk_per_trade']):
                            self.orders.append({
                                "signal": signal,
                                "timestamp": datetime.now().isoformat()
                            })
                
                time.sleep(60)  # Check every minute
                
            except KeyboardInterrupt:
                logger.info("Bot stopped by user")
                break
            except Exception as e:
                logger.error(f"Main loop error: {str(e)}")
                time.sleep(30)

if __name__ == "__main__":
    trader = UnifiedTrader(paper_mode=True)  # Set to False for real trading
    trader.run()
