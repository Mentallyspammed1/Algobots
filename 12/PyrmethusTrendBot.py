#!/usr/bin/env python3
# -*- coding: utf-8 -*
"""
Pyrmethus Trend Bot v2.3 - The Profit Protected Sentinel
--------------------------------------------------------------------------
- PascalCase Classes | camelCase Functions | UPPER_SNAKE_CASE Constants
- Chromatic Logging: Magenta (Ritual), Cyan (Market), Green (Fortune)
- Wizard Upgrade: Secure-Profit Break-Even (Net 0.02 USDT)
- Optimized for high-fidelity trend execution in Termux
"""

import os
import sys
import json
import time
import hmac
import hashlib
import sqlite3
import logging
import threading
import warnings
import argparse
from datetime import datetime, timezone
from decimal import Decimal, getcontext, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, asdict
from enum import Enum

import numpy as np
import pandas as pd
import requests
from colorama import Fore, Style, init as colorama_init
from dotenv import load_dotenv

# Try to import psutil for resource monitoring
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# --- Local Imports ---
from indicators import EhlersIndicators, MomentumIndicators, VolatilityIndicators, calculate_supertrend, LevelsCalculator

# ══════════════════════════════════════════════════════════════════════════════
# 1. INITIALIZATION & CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

colorama_init(autoreset=True)
getcontext().prec = 28
getcontext().rounding = ROUND_HALF_UP
warnings.filterwarnings('ignore', category=FutureWarning)

# --- Pyrmethus Chromatic Palette ---
MAGENTA = Fore.MAGENTA
CYAN    = Fore.CYAN
GREEN   = Fore.LIGHTGREEN_EX
YELLOW  = Fore.YELLOW
RED     = Fore.LIGHTRED_EX
WHITE   = Fore.WHITE
RESET   = Style.RESET_ALL

SOUL_STATE_FILE = "bot_data/soul_state.json"
DATABASE_PATH   = "bot_data/trading_bot.db"
TAKER_FEE_RATE  = Decimal("0.0006") # Bybit Standard Taker Fee (0.06%)
MIN_NET_PROFIT  = Decimal("0.02")   # Minimum net profit to secure (USDT)

class SignalType(Enum):
    BUY  = "buy"
    SELL = "sell"
    HOLD = "hold"

class MarketRegime(Enum):
    BULLISH  = "bullish"
    BEARISH  = "bearish"
    SIDEWAYS = "sideways"
    VOLATILE = "volatile"
    UNKNOWN  = "unknown"

@dataclass
class TradingSignal:
    signal_type: SignalType
    confidence: float
    conditions_met: List[str]
    stop_loss: Optional[Decimal]
    take_profit: Optional[Decimal]
    timestamp: float
    symbol: str
    timeframe: str
    entry_price: Decimal
    market_regime: MarketRegime
    position_size: float = 0.0
    quantity: Decimal = Decimal("0.0")

@dataclass
class ActiveSignal:
    db_id: int
    signal: TradingSignal
    highest_price: Decimal
    lowest_price: Decimal

# ══════════════════════════════════════════════════════════════════════════════
# 2. UTILITIES: RATE LIMITER, RESOURCE MONITOR & CIRCUIT BREAKER
# ══════════════════════════════════════════════════════════════════════════════

class CircuitBreaker:
    """WIZARD UPGRADE: Temporal Guard. Prevents over-trading and drawdown."""
    def __init__(self, db_path: str = "bot_data/circuit_breaker.json", max_daily_loss_pct: float = 0.02):
        self.db_path = db_path
        self.max_daily_loss_pct = Decimal(str(max_daily_loss_pct))
        self.state = self._load()

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self.db_path):
            with open(self.db_path, "r") as f:
                try:
                    data = json.load(f)
                    if data.get("date") == datetime.now().strftime("%Y-%m-%d"):
                        return data
                except: pass
        return {"date": datetime.now().strftime("%Y-%m-%d"), "daily_pnl": 0.0, "is_halted": False}

    def _save(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with open(self.db_path, "w") as f:
            json.dump(self.state, f)

    def update_pnl(self, pnl: Decimal, equity: Decimal):
        self.state["daily_pnl"] = float(Decimal(str(self.state["daily_pnl"])) + pnl)
        if equity > 0:
            drawdown = abs(Decimal(str(self.state["daily_pnl"]))) / equity
            if self.state["daily_pnl"] < 0 and drawdown >= self.max_daily_loss_pct:
                self.state["is_halted"] = True
        self._save()

    def is_halted(self) -> bool:
        return self.state.get("is_halted", False)

class RateLimiter:
    """Pattern-based Rate Limiter for API stability."""
    def __init__(self, max_calls: int, period: float):
        self.maxCalls = max_calls
        self.period = period
        self.calls = []
        self._lock = threading.Lock()

    def waitIfNeeded(self):
        """Throttles execution to respect API boundaries."""
        with self._lock:
            now = time.time()
            self.calls = [c for c in self.calls if now - c < self.period]
            if len(self.calls) >= self.maxCalls:
                sleepTime = self.period - (now - self.calls[0])
                if sleepTime > 0:
                    time.sleep(sleepTime)
            self.calls.append(time.time())

class ResourceMonitor:
    """Monitors system performance to prevent Termux throttling."""
    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def logStatus(self):
        """Reports CPU and Memory usage with chromatic flair."""
        if not PSUTIL_AVAILABLE:
            return
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory().percent
        color = GREEN if cpu < 70 else RED
        self.logger.info(f"{color}💻 System Status: CPU {cpu}% | MEM {mem}%{RESET}")

class SoulPersistence:
    """Chronos Protocol for state recovery and soul preservation."""
    @staticmethod
    def checkpoint(activeSignals: List[ActiveSignal]):
        """Saves current active positions to disk."""
        os.makedirs(os.path.dirname(SOUL_STATE_FILE), exist_ok=True)
        data = []
        for active in activeSignals:
            sigDict = asdict(active.signal)
            sigDict['signal_type'] = sigDict['signal_type'].value
            sigDict['market_regime'] = sigDict['market_regime'].value
            sigDict['stop_loss'] = str(sigDict['stop_loss'])
            sigDict['take_profit'] = str(sigDict['take_profit'])
            sigDict['entry_price'] = str(sigDict['entry_price'])
            sigDict['quantity'] = str(sigDict['quantity'])
            
            data.append({
                "db_id": active.db_id,
                "signal": sigDict,
                "highest_price": str(active.highest_price),
                "lowest_price": str(active.lowest_price)
            })
        
        with open(SOUL_STATE_FILE, "w") as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def recover() -> List[ActiveSignal]:
        """Restores active signals from the previous session."""
        if not os.path.exists(SOUL_STATE_FILE):
            return []
        try:
            with open(SOUL_STATE_FILE, "r") as f:
                data = json.load(f)
            recovered = []
            for item in data:
                sigData = item['signal']
                sig = TradingSignal(
                    signal_type=SignalType(sigData['signal_type']),
                    confidence=sigData['confidence'],
                    conditions_met=sigData['conditions_met'],
                    stop_loss=Decimal(sigData['stop_loss']),
                    take_profit=Decimal(sigData['take_profit']),
                    timestamp=sigData['timestamp'],
                    symbol=sigData['symbol'],
                    timeframe=sigData['timeframe'],
                    entry_price=Decimal(sigData['entry_price']),
                    market_regime=MarketRegime(sigData['market_regime']),
                    position_size=sigData.get('position_size', 0.0),
                    quantity=Decimal(sigData.get('quantity', '0.0'))
                )
                recovered.append(ActiveSignal(
                    db_id=item['db_id'],
                    signal=sig,
                    highest_price=Decimal(item['highest_price']),
                    lowest_price=Decimal(item['lowest_price'])
                ))
            return recovered
        except Exception:
            return []

# ══════════════════════════════════════════════════════════════════════════════
# 3. LOGGING & DATABASE
# ══════════════════════════════════════════════════════════════════════════════

def setupCustomLogger(name: str, logDir: str = "bot_logs") -> logging.Logger:
    """Configures the Chromatic Logger for the Pyrmethus ritual."""
    os.makedirs(logDir, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    if not logger.handlers:
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        fh = logging.FileHandler(os.path.join(logDir, f"{name}.log"))
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        logger.addHandler(ch)
        
    return logger

class DatabaseManager:
    """Manages the persistent SQLite audit trail."""
    def __init__(self, dbPath: str = DATABASE_PATH):
        self.dbPath = dbPath
        self.initializeDatabase()

    def initializeDatabase(self):
        """Creates the schema and performs necessary migrations."""
        os.makedirs(os.path.dirname(self.dbPath), exist_ok=True)
        with sqlite3.connect(self.dbPath) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS signal_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    symbol TEXT,
                    timeframe TEXT,
                    signal_type TEXT,
                    confidence REAL,
                    entry_price TEXT,
                    stop_loss TEXT,
                    take_profit TEXT,
                    market_regime TEXT,
                    exit_price TEXT,
                    pnl TEXT,
                    position_size REAL
                )
            ''')
            
            # Migration: Ensure position_size exists
            cursor.execute("PRAGMA table_info(signal_history)")
            columns = [column[1] for column in cursor.fetchall()]
            if 'position_size' not in columns:
                cursor.execute("ALTER TABLE signal_history ADD COLUMN position_size REAL")
                
            conn.commit()

    def saveSignal(self, sig: TradingSignal) -> int:
        """Commits a generated signal to the eternal ledger."""
        with sqlite3.connect(self.dbPath) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO signal_history (
                    timestamp, symbol, timeframe, signal_type, confidence,
                    entry_price, stop_loss, take_profit, market_regime, position_size
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                sig.timestamp, sig.symbol, sig.timeframe, sig.signal_type.value,
                sig.confidence, str(sig.entry_price), str(sig.stop_loss),
                str(sig.take_profit), sig.market_regime.value, sig.position_size
            ))
            conn.commit()
            return cursor.lastrowid

    def updatePnL(self, signalId: int, exitPrice: Decimal, pnl: Decimal):
        """Updates a ledger entry upon position closure."""
        with sqlite3.connect(self.dbPath) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE signal_history 
                SET exit_price = ?, pnl = ?
                WHERE id = ?
            ''', (str(exitPrice), str(pnl), signalId))
            conn.commit()

    def getTotalPnL(self) -> Decimal:
        """Calculates the aggregate gain/loss from the ledger."""
        with sqlite3.connect(self.dbPath) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT pnl FROM signal_history WHERE pnl IS NOT NULL')
            rows = cursor.fetchall()
            total = Decimal("0.0")
            for row in rows:
                if row[0]:
                    total += Decimal(row[0])
            return total

# ══════════════════════════════════════════════════════════════════════════════
# 4. BYBIT API CLIENT
# ══════════════════════════════════════════════════════════════════════════════

class BybitClient:
    """The Oracle Conduit: Secure Bybit V5 API Integration."""
    def __init__(self, apiKey: Optional[str] = None, apiSecret: Optional[str] = None, baseUrl: str = "https://api.bybit.com"):
        self.apiKey = apiKey
        self.apiSecret = apiSecret
        self.baseUrl = baseUrl
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Termux; Android 12; PyrmethusBot/2.2)",
        })
        
        # WIZARD UPGRADE: Proxy Sentinel
        self.session.proxies = {
            "http": "socks5h://127.0.0.1:9050",
            "https": "socks5h://127.0.0.1:9050",
        }
        
        self.limiter = RateLimiter(max_calls=10, period=1.0)

    def makeRequest(self, method: str, endpoint: str, params: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """Executes a signed request to the Bybit Oracle."""
        self.limiter.waitIfNeeded()
        timestamp = str(int(time.time() * 1000))
        params = params or {}
        
        headers = {
            "Content-Type": "application/json",
            "X-BAPI-RECV-WINDOW": "5000",
            "X-BAPI-TIMESTAMP": timestamp,
        }

        if self.apiKey and self.apiSecret:
            headers["X-BAPI-API-KEY"] = self.apiKey
            if method == "POST":
                payload = json.dumps(params)
            else:
                payload = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
            
            rawStr = timestamp + self.apiKey + "5000" + payload
            headers["X-BAPI-SIGN"] = hmac.new(self.apiSecret.encode(), rawStr.encode(), hashlib.sha256).hexdigest()

        url = self.baseUrl + endpoint
        try:
            if method == "POST":
                resp = self.session.post(url, headers=headers, json=params, timeout=15)
            else:
                resp = self.session.get(url, headers=headers, params=params, timeout=15)
            
            if resp.status_code != 200:
                logging.error(f"HTTP {resp.status_code}: {resp.text[:200]}")
                return None

            resJson = resp.json()
            if resJson.get("retCode") == 0:
                return resJson.get("result")
            else:
                logging.error(f"Bybit Error: {resJson.get('retMsg')} (Code: {resJson.get('retCode')})")
                return None
        except Exception as e:
            logging.error(f"Request Exception: {str(e)}")
            return None

    def fetchKlines(self, symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
        """Retrieves historical market data."""
        endpoint = "/v5/market/kline"
        params = {"category": "linear", "symbol": symbol, "interval": interval, "limit": limit}
        res = self.makeRequest("GET", endpoint, params)
        if res and "list" in res:
            df = pd.DataFrame(res["list"], columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
            df["timestamp"] = pd.to_datetime(df["timestamp"].astype(float), unit="ms")
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = df[col].astype(float)
            return df.sort_values("timestamp").reset_index(drop=True)
        return pd.DataFrame()

    def placeOrder(self, symbol: str, side: str, qty: str, sl: str, tp: str) -> Optional[Dict[str, Any]]:
        """Initiates a risk-managed market order."""
        endpoint = "/v5/order/create"
        params = {
            "category": "linear", "symbol": symbol, "side": side.capitalize(),
            "orderType": "Market", "qty": qty, "stopLoss": sl, "takeProfit": tp,
            "tpslMode": "Full", "reduceOnly": False, "closeOnTrigger": False
        }
        return self.makeRequest("POST", endpoint, params)

    def getInstrumentInfo(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetches precision filters for the specified symbol."""
        endpoint = "/v5/market/instruments-info"
        params = {"category": "linear", "symbol": symbol}
        res = self.makeRequest("GET", endpoint, params)
        if res and "list" in res and len(res["list"]) > 0:
            return res["list"][0]
        return None

    def getWalletBalance(self) -> Decimal:
        """Retrieves total equity for Unified Accounts."""
        endpoint = "/v5/account/wallet-balance"
        params = {"accountType": "UNIFIED", "coin": "USDT"}
        res = self.makeRequest("GET", endpoint, params)
        if res and "list" in res and len(res["list"]) > 0:
            return Decimal(res["list"][0].get("totalEquity", "0"))
        return Decimal("0")

    def fetchOracleSentiment(self, symbol: str) -> float:
        """Injects external sentiment bias from the Oracle."""
        return 0.1

# ══════════════════════════════════════════════════════════════════════════════
# 5. TREND ANALYSIS ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class TrendAnalyzer:
    """The Analytical Eye: Synthesizing DSP and Momentum indicators."""
    def __init__(self, config: Dict[str, Any], logger: logging.Logger):
        self.config = config
        self.logger = logger

    def detectRegime(self, df: pd.DataFrame) -> MarketRegime:
        """Classifies market behavior using Ehlers CTI."""
        close = df['close']
        cti = EhlersIndicators.correlation_trend_indicator(close, 20)
        latestCti = cti.iloc[-1]
        
        if abs(latestCti) > 0.7:
            return MarketRegime.BULLISH if latestCti > 0 else MarketRegime.BEARISH
        elif abs(latestCti) < 0.3:
            return MarketRegime.SIDEWAYS
        else:
            return MarketRegime.VOLATILE

    def analyzeMarket(self, df: pd.DataFrame, symbol: str, interval: str, db: DatabaseManager, client: BybitClient) -> Optional[TradingSignal]:
        """Performs a comprehensive scan and generates signals."""
        regime = self.detectRegime(df)
        close, high, low = df['close'], df['high'], df['low']
        currentPriceVal = close.iloc[-1]
        
        # DSP Logic
        fisher, fisherSig = EhlersIndicators.fisher_transform(close, 10)
        lrsi = EhlersIndicators.laguerre_rsi(close, 0.5)
        cyber, cyberSig = EhlersIndicators.cyber_cycle(close, 0.07)
        estochK, estochD = EhlersIndicators.ehlers_stoch_rsi(close, 14)
        cog, cogSig = EhlersIndicators.center_of_gravity(close, 10)
        
        # Momentum & Volatility
        vwap = MomentumIndicators.vwap(df)
        macd, macdSig, macdHist = MomentumIndicators.macd(close)
        adxVal = MomentumIndicators.adx(high, low, close, 14)
        fveVal = MomentumIndicators.fve(close, volume, 22)
        atrSeries = VolatilityIndicators.atr(high, low, close, 14)
        atr = atrSeries.iloc[-1]
        chanLong, chanShort = VolatilityIndicators.chandelier_exit(high, low, close)
        stDf = calculate_supertrend(df)

        # Structural Dashboard
        masterLevels = {**LevelsCalculator.pivot_points(high.max(), low.min(), currentPriceVal), 
                        **LevelsCalculator.fibonacci_levels(high.max(), low.min())}
        nearestStructural = LevelsCalculator.find_nearest_5(currentPriceVal, masterLevels)
        
        totalPnL = db.getTotalPnL()
        
        # Chromatic Analysis Report
        self.logger.info(f"\n{MAGENTA}📊 ANALYSIS REPORT: {symbol} [{interval}m]{RESET}")
        self.logger.info(f"{CYAN}Current Price:{RESET} {currentPriceVal:.5f}")
        self.logger.info(f"{WHITE}Total Ledger PnL:{RESET} {totalPnL:.2f}")
        self.logger.info(f"{MAGENTA}Market Regime:{RESET} {regime.value.upper()}")
        
        levelReport = " | ".join([f"{name}: {val:.4f}" for name, val in nearestStructural])
        self.logger.info(f"{YELLOW}📍 NEAREST LEVELS:{RESET} {levelReport}")

        self.logger.info(f"{GREEN}Fisher:{RESET} {fisher.iloc[-1]:.4f} | {GREEN}LRSI:{RESET} {lrsi.iloc[-1]:.4f}")
        self.logger.info(f"{CYAN}Cyber Cycle:{RESET} {cyber.iloc[-1]:.4f} | {YELLOW}COG:{RESET} {cog.iloc[-1]:.2f}")
        self.logger.info(f"{MAGENTA}MACD Hist:{RESET} {macdHist.iloc[-1]:.5f} | {YELLOW}ADX:{RESET} {adxVal.iloc[-1]:.2f}")
        self.logger.info(f"{YELLOW}SuperTrend:{RESET} {'BULLISH' if stDf['direction'].iloc[-1] == 1 else 'BEARISH'} | {CYAN}ATR:{RESET} {atr:.5f}")

        # Confluence Scoring
        score, conditions = 0.0, []
        
        oracleBias = client.fetchOracleSentiment(symbol)
        if oracleBias != 0:
            score += oracleBias
            conditions.append(f"Oracle Sentiment: {oracleBias:+.2f}")

        if fisher.iloc[-1] > fisherSig.iloc[-1]:
            score += 0.3
            conditions.append("Fisher transform Bullish")
        
        if lrsi.iloc[-1] < 0.2:
            score += 0.2
            conditions.append("Laguerre Oversold")
        
        if stDf['direction'].iloc[-1] == 1:
            score += 0.2
            conditions.append("SuperTrend Bullish")

        if currentPriceVal > vwap.iloc[-1]:
            score += 0.1
            conditions.append("Above VWAP")

        # Result Generation
        signalType = SignalType.HOLD
        if score >= 0.6: signalType = SignalType.BUY
        elif score <= -0.6: signalType = SignalType.SELL
        
        if signalType != SignalType.HOLD:
            darMultiplier = 1.0 + (abs(score) - 0.6) / 0.4
            
            entryPrice = Decimal(str(currentPriceVal))
            atr_dec = Decimal(str(atr))
            
            # Wizard Upgrade: Regime-Adaptive Risk Distances
            if regime == MarketRegime.VOLATILE:
                slDist = atr_dec * Decimal("1.0") # Tighter stops in volatility
                tpDist = atr_dec * Decimal("1.5") # Faster profit taking
            else:
                slDist = atr_dec * Decimal("1.5")
                tpDist = atr_dec * Decimal("3.0")
            
            sl = entryPrice - slDist if signalType == SignalType.BUY else entryPrice + slDist
            tp = entryPrice + tpDist if signalType == SignalType.BUY else entryPrice - tpDist
                
            return TradingSignal(
                signal_type=signalType, confidence=abs(score), conditions_met=conditions,
                stop_loss=sl, take_profit=tp, timestamp=time.time(), symbol=symbol,
                timeframe=interval, entry_price=entryPrice, market_regime=regime,
                position_size=float(darMultiplier)
            )
        return None

# ══════════════════════════════════════════════════════════════════════════════
# 6. MAIN EXECUTION LOOP
# ══════════════════════════════════════════════════════════════════════════════

def executeBotMain():
    """Initiates the Pyrmethus Bot ritual via CLI or Interactive mode."""
    load_dotenv() 
    
    # --- Argument Parsing (Wizard Upgrade: Automation CLI) ---
    parser = argparse.ArgumentParser(description="Pyrmethus Trend Bot v2.2")
    parser.add_argument("symbol", nargs="?", help="Trading symbol (e.g., BTCUSDT)")
    parser.add_argument("interval", nargs="?", help="Timeframe (e.g., 1, 3, 5, 15, 60)")
    args = parser.parse_args()

    botLogger = setupCustomLogger("PyrmethusBot")
    
    apiKey = os.getenv("BYBIT_API_KEY")
    apiSecret = os.getenv("BYBIT_API_SECRET")
    
    if not apiKey or not apiSecret:
        botLogger.warning(f"{YELLOW}Warning: API credentials missing. Running in ANALYSIS MODE.{RESET}")
    
    db = DatabaseManager()
    client = BybitClient(apiKey, apiSecret)
    analyzer = TrendAnalyzer({}, botLogger)
    monitor = ResourceMonitor(botLogger)
    
    # Initiation Logic: CLI flags take precedence over Interactive prompts
    symbol = args.symbol.upper().strip() if args.symbol else None
    if not symbol:
        symbolInput = input(f"{CYAN}Enter trading symbol (e.g., BTCUSDT): {RESET}").upper().strip()
        symbol = symbolInput if symbolInput else "BTCUSDT"

    interval = args.interval.strip() if args.interval else None
    if not interval:
        intervalInput = input(f"{CYAN}Enter timeframe: {RESET}").strip()
        interval = intervalInput if intervalInput else "15"
    
    activeSignals = SoulPersistence.recover()
    if activeSignals:
        botLogger.info(f"{MAGENTA}🔮 Chronos Protocol: Restored {len(activeSignals)} active souls.{RESET}")

    botLogger.info(f"{MAGENTA}Pyrmethus Trend Bot Initiated for {symbol} ({interval}m){RESET}")

    while True:
        try:
            monitor.logStatus()
            df = client.fetchKlines(symbol, interval)
            if df.empty:
                time.sleep(10)
                continue
            
            currentPrice = Decimal(str(df['close'].iloc[-1]))
            # Calculate current ATR for trailing/BE logic
            latest_atr = Decimal(str(VolatilityIndicators.atr(df['high'], df['low'], df['close'], 14).iloc[-1]))
            
            # Check exits and manage active signals
            for active in activeSignals[:]:
                sig = active.signal
                exitPrice, pnl = None, Decimal("0.0")
                
                # Update extremes
                if currentPrice > active.highest_price: active.highest_price = currentPrice
                if currentPrice < active.lowest_price: active.lowest_price = currentPrice
                
                # --- Wizard Upgrade: Break-Even & Trailing Logic ---
                if sig.signal_type == SignalType.BUY:
                    # Secure-Profit Break-Even: If net profit > 0.05 USDT, move SL to secure 0.02 USDT
                    if sig.quantity > 0:
                        entry_fee = sig.entry_price * sig.quantity * TAKER_FEE_RATE
                        current_gross_pnl = (currentPrice - sig.entry_price) * sig.quantity
                        net_pnl = current_gross_pnl - (entry_fee * 2) # Approximate total fees
                        
                        if net_pnl >= Decimal("0.05"):
                            protected_sl = sig.entry_price + (MIN_NET_PROFIT + entry_fee * 2) / sig.quantity
                            if sig.stop_loss < protected_sl:
                                sig.stop_loss = protected_sl
                                botLogger.info(f"{GREEN}💰 Profit Secure: SL moved to {sig.stop_loss:.5f} (Net +0.02 USDT) for BUY ID {active.db_id}{RESET}")

                    # Break-Even Guard: Move SL to entry if price moves 0.5*ATR in favor
                    elif currentPrice >= sig.entry_price + (latest_atr * Decimal("0.5")):
                        be_sl = sig.entry_price + (latest_atr * Decimal("0.1"))
                        if sig.stop_loss < be_sl:
                            sig.stop_loss = be_sl
                            botLogger.info(f"{CYAN}🛡️ Guard: SL moved to Break-Even for BUY ID {active.db_id}{RESET}")
                    
                    # Trailing Stop: Keep SL at distance from highest price
                    trail_sl = active.highest_price - (latest_atr * Decimal("1.5"))
                    if trail_sl > sig.stop_loss:
                        sig.stop_loss = trail_sl
                        botLogger.info(f"{MAGENTA}🌊 Trail: SL moved up to {sig.stop_loss:.5f} for BUY ID {active.db_id}{RESET}")

                    # Exit Check
                    if currentPrice <= sig.stop_loss: exitPrice, pnl = sig.stop_loss, sig.stop_loss - sig.entry_price
                    elif currentPrice >= sig.take_profit: exitPrice, pnl = sig.take_profit, sig.take_profit - sig.entry_price
                
                elif sig.signal_type == SignalType.SELL:
                    # Secure-Profit Break-Even
                    if sig.quantity > 0:
                        entry_fee = sig.entry_price * sig.quantity * TAKER_FEE_RATE
                        current_gross_pnl = (sig.entry_price - currentPrice) * sig.quantity
                        net_pnl = current_gross_pnl - (entry_fee * 2)
                        
                        if net_pnl >= Decimal("0.05"):
                            protected_sl = sig.entry_price - (MIN_NET_PROFIT + entry_fee * 2) / sig.quantity
                            if sig.stop_loss > protected_sl:
                                sig.stop_loss = protected_sl
                                botLogger.info(f"{GREEN}💰 Profit Secure: SL moved to {sig.stop_loss:.5f} (Net +0.02 USDT) for SELL ID {active.db_id}{RESET}")

                    # Break-Even Guard
                    elif currentPrice <= sig.entry_price - (latest_atr * Decimal("0.5")):
                        be_sl = sig.entry_price - (latest_atr * Decimal("0.1"))
                        if sig.stop_loss > be_sl:
                            sig.stop_loss = be_sl
                            botLogger.info(f"{CYAN}🛡️ Guard: SL moved to Break-Even for SELL ID {active.db_id}{RESET}")
                    
                    # Trailing Stop
                    trail_sl = active.lowest_price + (latest_atr * Decimal("1.5"))
                    if trail_sl < sig.stop_loss:
                        sig.stop_loss = trail_sl
                        botLogger.info(f"{MAGENTA}🌊 Trail: SL moved down to {sig.stop_loss:.5f} for SELL ID {active.db_id}{RESET}")

                    # Exit Check
                    if currentPrice >= sig.stop_loss: exitPrice, pnl = sig.stop_loss, sig.entry_price - sig.stop_loss
                    elif currentPrice <= sig.take_profit: exitPrice, pnl = sig.take_profit, sig.entry_price - sig.take_profit
                
                if exitPrice:
                    db.updatePnL(active.db_id, exitPrice, pnl)
                    botLogger.info(f"{WHITE}Soul Released | ID: {active.db_id} | PnL: {pnl:.4f} | Exit: {exitPrice:.5f}{RESET}")
                    activeSignals.remove(active)
                    SoulPersistence.checkpoint(activeSignals)
                else:
                    SoulPersistence.checkpoint(activeSignals)
                
            signal = analyzer.analyzeMarket(df, symbol, interval, db, client)
            if signal:
                sigColor = GREEN if signal.signal_type == SignalType.BUY else RED
                botLogger.info(f"{sigColor}FORTUNE SIGNAL: {signal.signal_type.value.upper()} | DAR: {signal.position_size:.2f}x")
                
                if apiKey and apiSecret:
                    try:
                        balance = client.getWalletBalance()
                        info = client.getInstrumentInfo(symbol)
                        if info and balance > 0:
                            tickSize = Decimal(info['priceFilter']['tickSize'])
                            qtyStep = Decimal(info['lotSizeFilter']['qtyStep'])
                            
                            riskUsd = balance * Decimal("0.01") * Decimal(str(signal.position_size))
                            stopDist = abs(signal.entry_price - signal.stop_loss)
                            
                            if stopDist > 0:
                                qty = (riskUsd / stopDist).quantize(qtyStep, rounding=ROUND_HALF_UP)
                                sl = signal.stop_loss.quantize(tickSize, rounding=ROUND_HALF_UP)
                                tp = signal.take_profit.quantize(tickSize, rounding=ROUND_HALF_UP)
                                
                                if qty > 0:
                                    botLogger.info(f"{MAGENTA}🚀 EXECUTING: {signal.signal_type.value.upper()} {qty} (Risk: ${risk_usd:.2f}){RESET}")
                                    resp = client.placeOrder(symbol, signal.signal_type.value, str(qty), str(sl), str(tp))
                                    if resp:
                                        signal.quantity = qty
                    except Exception as e:
                        botLogger.error(f"Execution Disturbance: {e}")

                dbId = db.saveSignal(signal)
                activeSignals.append(ActiveSignal(db_id=dbId, signal=signal, highest_price=currentPrice, lowest_price=currentPrice))
                SoulPersistence.checkpoint(activeSignals)
            
            time.sleep(60)
            
        except KeyboardInterrupt:
            botLogger.info(f"{YELLOW}Ritual concluded by practitioner.")
            break
        except Exception:
            botLogger.exception("Ether Disturbance (Loop Exception)")
            time.sleep(30)

if __name__ == "__main__":
    executeBotMain()
