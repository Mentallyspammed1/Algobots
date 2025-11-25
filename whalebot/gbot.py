import os
import sys
import time
import json
import hmac
import hashlib
import logging
import urllib.parse
import numpy as np
import pandas as pd
import requests
import google.generativeai as genai
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN, getcontext
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Literal
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from colorama import Fore, Style, init

# --- Global Setup ---
getcontext().prec = 28
init(autoreset=True)
load_dotenv()

# --- Constants & Colors ---
NEON_GREEN = Fore.LIGHTGREEN_EX
NEON_RED = Fore.LIGHTRED_EX
NEON_BLUE = Fore.CYAN
NEON_YELLOW = Fore.YELLOW
NEON_PURPLE = Fore.MAGENTA
RESET = Style.RESET_ALL

LOG_DIR = Path("bot_logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = "config.json"

# --- Data Structures ---

@dataclass
class SignalResult:
    """Standardized result from the Strategy Engine"""
    action: Literal["BUY", "SELL", "HOLD"]
    total_score: float
    tech_score: float
    ai_score: float
    ai_reasoning: str
    atr: Decimal
    breakdown: Dict[str, float]

@dataclass
class Position:
    """Tracks an active trade"""
    symbol: str
    side: str
    entry_price: Decimal
    qty: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    entry_time: datetime

# --- Configuration Manager ---

class ConfigManager:
    """Singleton-like class to manage and validate configuration"""
    DEFAULT = {
        "symbol": "BTCUSDT",
        "interval": "15",
        "loop_delay": 15,
        "gemini_enabled": True,
        "gemini_model": "gemini-1.5-flash",
        "weights": {
            "technical": 0.7,
            "ai": 0.3
        },
        "trade_management": {
            "account_balance": 1000.0,
            "risk_per_trade": 1.0,
            "sl_atr_mult": 1.5,
            "tp_atr_mult": 2.0,
            "max_positions": 1,
            "leverage": 1
        },
        "indicators": {
            "rsi_period": 14,
            "ema_short": 9,
            "ema_long": 21,
            "atr_period": 14,
            "bb_period": 20,
            "bb_std": 2.0
        }
    }

    def __init__(self):
        self.data = self._load()
        self._validate_env()

    def _load(self) -> Dict:
        """Loads config from file or creates default"""
        if not os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.DEFAULT, f, indent=4)
            return self.DEFAULT
        try:
            with open(CONFIG_FILE, 'r') as f:
                user_config = json.load(f)
                return {**self.DEFAULT, **user_config}
        except Exception:
            return self.DEFAULT

    def _validate_env(self):
        """Checks for API keys"""
        if not os.getenv("BYBIT_API_KEY") or not os.getenv("BYBIT_API_SECRET"):
            logging.warning(f"{NEON_RED}Bybit API Keys missing in .env{RESET}")
        
        if self.data["gemini_enabled"] and not os.getenv("GEMINI_API_KEY"):
            logging.error(f"{NEON_RED}Gemini API Key missing. Disabling AI.{RESET}")
            self.data["gemini_enabled"] = False

    def get(self, key, default=None):
        return self.data.get(key, default)

# --- Logger Setup ---

def setup_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    if not logger.handlers:
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        
        # Console Handler
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        logger.addHandler(ch)
        
        # File Handler
        fh = RotatingFileHandler(LOG_DIR / f"{name}.log", maxBytes=5*1024*1024, backupCount=3)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    
    return logger

logger = setup_logger("WhaleBot")

# --- API Clients ---

class BybitClient:
    """Handles connection to Bybit V5 API"""
    def __init__(self, api_key, api_secret, base_url="https://api.bybit.com"):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.session = self._init_session()
        
    def _init_session(self):
        s = requests.Session()
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        s.mount('https://', HTTPAdapter(max_retries=retries))
        return s

    def fetch_klines(self, symbol, interval, limit=200) -> pd.DataFrame:
        try:
            url = f"{self.base_url}/v5/market/kline"
            params = {"category": "linear", "symbol": symbol, "interval": interval, "limit": limit}
            resp = self.session.get(url, params=params, timeout=10)
            data = resp.json()
            
            if data.get('retCode') != 0:
                logger.error(f"Bybit API Error: {data.get('retMsg')}")
                return pd.DataFrame()

            df = pd.DataFrame(data['result']['list'], columns=['startTime', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
            # Convert types
            df['startTime'] = pd.to_datetime(pd.to_numeric(df['startTime']), unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col])
            
            df = df.sort_values('startTime').set_index('startTime')
            return df
        except Exception as e:
            logger.error(f"Error fetching klines: {e}")
            return pd.DataFrame()

    def fetch_price(self, symbol) -> Decimal:
        try:
            url = f"{self.base_url}/v5/market/tickers"
            resp = self.session.get(url, params={"category": "linear", "symbol": symbol}, timeout=5)
            data = resp.json()
            return Decimal(data['result']['list'][0]['lastPrice'])
        except Exception:
            return Decimal(0)

class GeminiAgent:
    """Handles interaction with Google Gemini API"""
    def __init__(self, model_name="gemini-1.5-flash"):
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(model_name)
            self.enabled = True
        else:
            self.enabled = False

    def analyze(self, symbol: str, current_price: float, indicators: Dict[str, float]) -> Tuple[float, str]:
        """
        Returns a tuple (score, reasoning). Score is between -1.0 (Strong Sell) and 1.0 (Strong Buy).
        """
        if not self.enabled:
            return 0.0, "AI Disabled"

        prompt = f"""
        You are an expert crypto trading bot. Analyze the following technical data for {symbol}.
        
        Current Price: {current_price}
        Technical Indicators:
        {json.dumps(indicators, indent=2)}
        
        Task:
        1. Analyze the market structure and indicator confluence.
        2. Provide a sentiment score between -1.0 (Strong Sell) and 1.0 (Strong Buy).
        3. Provide a short reasoning (max 1 sentence).
        
        Output Format (JSON only):
        {{
            "score": float,
            "reasoning": "string"
        }}
        """

        try:
            response = self.model.generate_content(prompt)
            # Clean response to ensure valid JSON
            text = response.text.replace("```json", "").replace("```", "").strip()
            data = json.loads(text)
            return float(data.get("score", 0.0)), data.get("reasoning", "No reasoning provided")
        except Exception as e:
            logger.error(f"{NEON_RED}Gemini Error: {e}{RESET}")
            return 0.0, "AI Error"

# --- Indicator Engine ---

class IndicatorEngine:
    """Pure mathematical calculations using Vectorized Pandas/Numpy"""
    @staticmethod
    def calculate_all(df: pd.DataFrame, cfg: Dict) -> pd.DataFrame:
        df = df.copy()
        c = df['close']
        h = df['high']
        l = df['low']
        
        # EMA
        df['EMA_S'] = c.ewm(span=cfg['ema_short'], adjust=False).mean()
        df['EMA_L'] = c.ewm(span=cfg['ema_long'], adjust=False).mean()
        
        # RSI
        delta = c.diff()
        gain = (delta.where(delta > 0, 0)).ewm(alpha=1/cfg['rsi_period'], adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/cfg['rsi_period'], adjust=False).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # ATR
        tr1 = h - l
        tr2 = (h - c.shift()).abs()
        tr3 = (l - c.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df['ATR'] = tr.ewm(alpha=1/cfg['atr_period'], adjust=False).mean()
        
        # Bollinger Bands
        sma = c.rolling(cfg['bb_period']).mean()
        std = c.rolling(cfg['bb_period']).std()
        df['BB_Upper'] = sma + (std * cfg['bb_std'])
        df['BB_Lower'] = sma - (std * cfg['bb_std'])
        
        # Volume Delta (Simple approximation)
        df['Vol_Delta'] = np.where(c > df['open'], df['volume'], -df['volume'])
        df['CVD'] = df['Vol_Delta'].rolling(20).sum()

        return df

# --- Strategy Engine ---

class StrategyEngine:
    """Combines Technical Analysis and AI to generate signals"""
    def __init__(self, config: ConfigManager, gemini: GeminiAgent):
        self.cfg = config
        self.gemini = gemini

    def generate_signal(self, df: pd.DataFrame) -> SignalResult:
        if df.empty:
            return SignalResult("HOLD", 0, 0, 0, "No Data", Decimal(0), {})

        last = df.iloc[-1]
        
        # 1. Technical Score Calculation
        tech_score = 0.0
        breakdown = {}
        
        # EMA Trend
        if last['EMA_S'] > last['EMA_L']:
            tech_score += 1.0
            breakdown['Trend'] = 1.0
        else:
            tech_score -= 1.0
            breakdown['Trend'] = -1.0
            
        # RSI
        if last['RSI'] < 30:
            tech_score += 0.5
            breakdown['RSI'] = 0.5
        elif last['RSI'] > 70:
            tech_score -= 0.5
            breakdown['RSI'] = -0.5
            
        # Bollinger Bands Reversion
        if last['close'] < last['BB_Lower']:
            tech_score += 0.5
            breakdown['BB'] = 0.5
        elif last['close'] > last['BB_Upper']:
            tech_score -= 0.5
            breakdown['BB'] = -0.5
            
        # Normalize Tech Score (-2 to 2 -> -1 to 1)
        tech_score = max(min(tech_score / 2.0, 1.0), -1.0)
        
        # 2. AI Analysis
        ai_score = 0.0
        ai_reasoning = "Disabled"
        
        if self.cfg.get("gemini_enabled"):
            # Prepare context for AI
            indicators = {
                "RSI": round(last['RSI'], 2),
                "EMA_Spread": round(last['EMA_S'] - last['EMA_L'], 4),
                "Price_vs_BB": "Above Upper" if last['close'] > last['BB_Upper'] else "Below Lower" if last['close'] < last['BB_Lower'] else "Inside",
                "ATR": round(last['ATR'], 2),
                "Recent_Volume_Trend": "Up" if last['CVD'] > 0 else "Down"
            }
            ai_score, ai_reasoning = self.gemini.analyze(
                self.cfg.get("symbol"), 
                float(last['close']), 
                indicators
            )
            
        # 3. Weighted Combination
        w_tech = self.cfg.get("weights")['technical']
        w_ai = self.cfg.get("weights")['ai']
        
        total_score = (tech_score * w_tech) + (ai_score * w_ai)
        
        action = "HOLD"
        threshold = 0.5
        if total_score >= threshold: action = "BUY"
        elif total_score <= -threshold: action = "SELL"
        
        return SignalResult(
            action=action,
            total_score=total_score,
            tech_score=tech_score,
            ai_score=ai_score,
            ai_reasoning=ai_reasoning,
            atr=Decimal(str(last['ATR'])),
            breakdown=breakdown
        )

# --- Position Manager ---

class PositionManager:
    """Handles Paper Trading Logic (Entry, Exit, PnL)"""
    def __init__(self, config: ConfigManager):
        self.cfg = config
        self.positions: List[Position] = []
        self.balance = Decimal(str(config.get("trade_management")['account_balance']))

    def calculate_size(self, price: Decimal, atr: Decimal) -> Decimal:
        tm = self.cfg.get("trade_management")
        risk_amt = self.balance * (Decimal(str(tm['risk_per_trade'])) / 100)
        sl_dist = atr * Decimal(str(tm['sl_atr_mult']))
        
        if sl_dist == 0: return Decimal(0)
        
        qty = risk_amt / sl_dist
        # Convert USD value to Asset Qty
        qty = qty / price
        return qty.quantize(Decimal("0.001"), rounding=ROUND_DOWN)

    def open_position(self, signal: SignalResult, price: Decimal):
        tm = self.cfg.get("trade_management")
        if len(self.positions) >= tm['max_positions']:
            return

        qty = self.calculate_size(price, signal.atr)
        if qty <= 0: return

        sl_dist = signal.atr * Decimal(str(tm['sl_atr_mult']))
        tp_dist = signal.atr * Decimal(str(tm['tp_atr_mult']))

        if signal.action == "BUY":
            sl = price - sl_dist
            tp = price + tp_dist
        else:
            sl = price + sl_dist
            tp = price - tp_dist

        pos = Position(
            symbol=self.cfg.get("symbol"),
            side=signal.action,
            entry_price=price,
            qty=qty,
            stop_loss=sl,
            take_profit=tp,
            entry_time=datetime.now(timezone.utc)
        )
        self.positions.append(pos)
        logger.info(f"{NEON_GREEN}OPEN {pos.side} | Price: {price} | Size: {qty} | AI Score: {signal.ai_score:.2f}{RESET}")

    def update(self, current_price: Decimal):
        # Check Stops
        for pos in self.positions[:]:
            pnl = Decimal(0)
            closed = False
            reason = ""

            if pos.side == "BUY":
                if current_price <= pos.stop_loss:
                    pnl = (pos.stop_loss - pos.entry_price) * pos.qty
                    closed = True; reason = "SL"
                elif current_price >= pos.take_profit:
                    pnl = (pos.take_profit - pos.entry_price) * pos.qty
                    closed = True; reason = "TP"
            else:
                if current_price >= pos.stop_loss:
                    pnl = (pos.entry_price - pos.stop_loss) * pos.qty
                    closed = True; reason = "SL"
                elif current_price <= pos.take_profit:
                    pnl = (pos.entry_price - pos.take_profit) * pos.qty
                    closed = True; reason = "TP"

            if closed:
                self.balance += pnl
                self.positions.remove(pos)
                color = NEON_GREEN if pnl > 0 else NEON_RED
                logger.info(f"{color}CLOSE {pos.side} ({reason}) | PnL: {pnl:.2f} | Bal: {self.balance:.2f}{RESET}")

# --- Main Execution Loop ---

def main():
    config = ConfigManager()
    symbol = config.get("symbol")
    interval = config.get("interval")
    
    bybit = BybitClient(os.getenv("BYBIT_API_KEY"), os.getenv("BYBIT_API_SECRET"))
    gemini = GeminiAgent(config.get("gemini_model"))
    strategy = StrategyEngine(config, gemini)
    pm = PositionManager(config)

    logger.info(f"{NEON_PURPLE}=== WhaleBot Started ({symbol}) ==={RESET}")
    logger.info(f"AI Enabled: {config.get('gemini_enabled')}")

    while True:
        try:
            # 1. Get Data
            current_price = bybit.fetch_price(symbol)
            if current_price == 0:
                logger.warning("Failed to fetch price")
                time.sleep(5)
                continue

            df = bybit.fetch_klines(symbol, interval)
            if df.empty:
                time.sleep(5)
                continue

            # 2. Calculate Indicators
            df = IndicatorEngine.calculate_all(df, config.get("indicators"))

            # 3. Generate Signal (Tech + AI)
            signal = strategy.generate_signal(df)

            # 4. Output Status
            logger.info(f"Price: {current_price} | Score: {signal.total_score:.2f} (Tech: {signal.tech_score:.2f}, AI: {signal.ai_score:.2f})")
            if signal.ai_reasoning != "Disabled":
                logger.info(f"{NEON_BLUE}AI Thought: {signal.ai_reasoning}{RESET}")

            # 5. Execute
            pm.update(current_price)
            if signal.action != "HOLD":
                pm.open_position(signal, current_price)

            # 6. Wait
            time.sleep(config.get("loop_delay"))

        except KeyboardInterrupt:
            logger.info("Stopping Bot...")
            break
        except Exception as e:
            logger.error(f"Critical Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
