#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Advanced Supertrend Trading Bot for Bybit V5 API - Enhanced Edition

This enhanced version includes:
- WebSocket real-time data streaming
- Advanced signal filtering with multiple confirmations
- Trailing stop-loss with breakeven protection
- Partial take-profit system
- Market microstructure analysis
- Performance metrics and statistics
- Adaptive parameter optimization
- Advanced risk management
- Session-based trading filters
- Order book analysis for optimal entries
"""

import asyncio
import logging
import logging.handlers
import os
import signal
import sys
import threading
import time
import json
import pickle
from collections import deque, defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from decimal import ROUND_DOWN, Decimal, getcontext
from enum import Enum
from typing import Any, Deque, Dict, List, Optional, Tuple, Callable
from statistics import mean, stdev

import numpy as np
import pandas as pd
import pandas_ta as ta
from scipy import stats
import colorlog
from colorama import Fore, Style, init
from dotenv import load_dotenv
from pybit.exceptions import InvalidRequestError
from pybit.unified_trading import HTTP, WebSocket

# Advanced imports
import aiohttp
import websockets
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
import joblib

# Initialize
init(autoreset=True)
load_dotenv()
getcontext().prec = 10

# =====================================================================
# CONFIGURATION & ENUMS
# =====================================================================

class Signal(Enum):
    STRONG_BUY = 2
    BUY = 1
    NEUTRAL = 0
    SELL = -1
    STRONG_SELL = -2

class OrderType(Enum):
    MARKET = "Market"
    LIMIT = "Limit"
    LIMIT_MAKER = "Limit"  # Post-only

class MarketCondition(Enum):
    TRENDING_UP = "Trending Up"
    TRENDING_DOWN = "Trending Down"
    RANGING = "Ranging"
    VOLATILE = "Volatile"
    CALM = "Calm"

class TradingSession(Enum):
    ASIAN = "Asian"
    EUROPEAN = "European"
    AMERICAN = "American"
    OVERLAP = "Overlap"

@dataclass
class EnhancedConfig:
    """Enhanced bot configuration with advanced features."""
    # API Configuration
    API_KEY: str = os.getenv("BYBIT_API_KEY", "")
    API_SECRET: str = os.getenv("BYBIT_API_SECRET", "")
    TESTNET: bool = os.getenv("BYBIT_TESTNET", "true").lower() in ['true', '1']
    
    # Trading Configuration
    SYMBOL: str = os.getenv("BYBIT_SYMBOL", "BTCUSDT")
    CATEGORY: str = os.getenv("BYBIT_CATEGORY", "linear")
    LEVERAGE: int = int(os.getenv("BYBIT_LEVERAGE", 10))
    TIMEFRAMES: List[str] = field(default_factory=lambda: ["1", "5", "15", "60"])
    PRIMARY_TIMEFRAME: str = os.getenv("PRIMARY_TIMEFRAME", "15")
    
    # SuperTrend Parameters (Adaptive)
    ST_PERIOD_MIN: int = 7
    ST_PERIOD_MAX: int = 20
    ST_MULTIPLIER_MIN: float = 1.5
    ST_MULTIPLIER_MAX: float = 4.0
    
    # Risk Management
    RISK_PER_TRADE_PCT: float = float(os.getenv("RISK_PER_TRADE_PCT", 1.0))
    MAX_POSITION_SIZE_PCT: float = float(os.getenv("MAX_POSITION_SIZE_PCT", 50.0))
    STOP_LOSS_PCT: float = float(os.getenv("STOP_LOSS_PCT", 1.5))
    TAKE_PROFIT_PCT: float = float(os.getenv("TAKE_PROFIT_PCT", 3.0))
    TRAILING_STOP_ACTIVATION_PCT: float = 1.0
    TRAILING_STOP_DISTANCE_PCT: float = 0.5
    BREAKEVEN_ACTIVATION_PCT: float = 0.5
    MAX_DAILY_LOSS_PCT: float = float(os.getenv("MAX_DAILY_LOSS_PCT", 5.0))
    MAX_DAILY_TRADES: int = int(os.getenv("MAX_DAILY_TRADES", 10))
    MAX_CONSECUTIVE_LOSSES: int = 3
    
    # Partial Take Profit
    PARTIAL_TP_LEVELS: List[Dict] = field(default_factory=lambda: [
        {"profit_pct": 1.0, "close_pct": 30},
        {"profit_pct": 2.0, "close_pct": 30},
        {"profit_pct": 3.0, "close_pct": 40}
    ])
    
    # Signal Filters
    ADX_TREND_FILTER: bool = True
    ADX_MIN_THRESHOLD: float = 25.0
    VOLUME_FILTER: bool = True
    VOLUME_MULTIPLIER: float = 1.5
    RSI_FILTER: bool = True
    RSI_OVERSOLD: float = 30.0
    RSI_OVERBOUGHT: float = 70.0
    
    # Market Structure
    USE_MARKET_STRUCTURE: bool = True
    ORDER_BOOK_DEPTH: int = 20
    IMBALANCE_THRESHOLD: float = 0.6
    
    # Trading Sessions
    TRADE_SESSIONS: List[str] = field(default_factory=lambda: ["EUROPEAN", "AMERICAN"])
    AVOID_NEWS_EVENTS: bool = True
    
    # Machine Learning
    USE_ML_SIGNALS: bool = False
    ML_MODEL_PATH: str = "models/signal_predictor.pkl"
    ML_CONFIDENCE_THRESHOLD: float = 0.7
    
    # Performance
    MIN_WIN_RATE: float = 0.4
    MIN_PROFIT_FACTOR: float = 1.2
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    SAVE_TRADES_CSV: bool = True
    
    # Notifications
    TELEGRAM_ENABLED: bool = False
    TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

# =====================================================================
# ENHANCED STATE MANAGEMENT
# =====================================================================

@dataclass
class MarketData:
    """Real-time market data container."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    bid: float = 0.0
    ask: float = 0.0
    spread: float = 0.0
    order_book_imbalance: float = 0.0
    
@dataclass
class PositionInfo:
    """Detailed position information."""
    symbol: str
    side: str
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float
    stop_loss: float
    take_profit: float
    trailing_activated: bool = False
    breakeven_activated: bool = False
    partial_closes_done: int = 0
    entry_time: datetime = field(default_factory=datetime.now)
    
    @property
    def pnl_percentage(self) -> float:
        if self.entry_price == 0:
            return 0
        return ((self.current_price - self.entry_price) / self.entry_price * 100 
                if self.side == "Buy" else 
                (self.entry_price - self.current_price) / self.entry_price * 100)

@dataclass
class PerformanceMetrics:
    """Track bot performance metrics."""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    total_fees: float = 0.0
    max_drawdown: float = 0.0
    current_drawdown: float = 0.0
    peak_balance: float = 0.0
    sharpe_ratio: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    win_rate: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    avg_trade_duration: timedelta = timedelta()
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    daily_pnl: Dict[str, float] = field(default_factory=dict)
    
    def update_metrics(self, trade_pnl: float, trade_duration: timedelta):
        self.total_trades += 1
        self.total_pnl += trade_pnl
        
        if trade_pnl > 0:
            self.winning_trades += 1
            self.consecutive_wins += 1
            self.consecutive_losses = 0
            self.best_trade = max(self.best_trade, trade_pnl)
        else:
            self.losing_trades += 1
            self.consecutive_losses += 1
            self.consecutive_wins = 0
            self.worst_trade = min(self.worst_trade, trade_pnl)
        
        # Update averages
        if self.winning_trades > 0:
            self.avg_win = sum(1 for t in self.daily_pnl.values() if t > 0) / self.winning_trades
        if self.losing_trades > 0:
            self.avg_loss = sum(1 for t in self.daily_pnl.values() if t < 0) / self.losing_trades
        
        self.win_rate = self.winning_trades / self.total_trades if self.total_trades > 0 else 0
        
        # Update profit factor
        total_wins = sum(t for t in self.daily_pnl.values() if t > 0)
        total_losses = abs(sum(t for t in self.daily_pnl.values() if t < 0))
        self.profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
        
        # Track daily PnL
        today = datetime.now().strftime("%Y-%m-%d")
        self.daily_pnl[today] = self.daily_pnl.get(today, 0) + trade_pnl

@dataclass
class EnhancedBotState:
    """Enhanced thread-safe state manager."""
    # Market State
    symbol: str
    market_condition: MarketCondition = MarketCondition.RANGING
    current_session: TradingSession = TradingSession.ASIAN
    market_data: Dict[str, MarketData] = field(default_factory=dict)
    
    # Indicators
    supertrend_values: Dict[str, float] = field(default_factory=dict)
    indicator_values: Dict[str, float] = field(default_factory=dict)
    signal_strength: float = 0.0
    
    # Position
    position: Optional[PositionInfo] = None
    pending_orders: List[Dict] = field(default_factory=list)
    
    # Performance
    metrics: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    
    # System
    bot_status: str = "Initializing"
    last_signal_time: Optional[datetime] = None
    errors_count: int = 0
    
    # Logs
    log_messages: Deque[str] = field(default_factory=lambda: deque(maxlen=20))
    trade_history: List[Dict] = field(default_factory=list)
    
    # Thread safety
    lock: threading.RLock = field(default_factory=threading.RLock)
    
    def update(self, **kwargs):
        with self.lock:
            for key, value in kwargs.items():
                if hasattr(self, key):
                    setattr(self, key, value)
    
    def add_log(self, message: str, level: str = "INFO"):
        with self.lock:
            timestamp = datetime.now().strftime('%H:%M:%S')
            color = {"INFO": Fore.WHITE, "SUCCESS": Fore.GREEN, 
                    "WARNING": Fore.YELLOW, "ERROR": Fore.RED}.get(level, Fore.WHITE)
            self.log_messages.append(f"{timestamp} [{level}] {message}")

# =====================================================================
# MARKET ANALYSIS
# =====================================================================

class MarketAnalyzer:
    """Advanced market structure and condition analyzer."""
    
    def __init__(self, config: EnhancedConfig):
        self.config = config
        self.volatility_window = 20
        self.trend_window = 50
        
    def analyze_market_condition(self, df: pd.DataFrame) -> MarketCondition:
        """Determine current market condition."""
        if len(df) < self.trend_window:
            return MarketCondition.RANGING
        
        # Calculate trend strength
        close_prices = df['close'].values[-self.trend_window:]
        trend_slope = np.polyfit(range(len(close_prices)), close_prices, 1)[0]
        trend_strength = abs(trend_slope) / np.mean(close_prices) * 100
        
        # Calculate volatility
        returns = df['close'].pct_change().dropna()
        volatility = returns.std() * np.sqrt(252) * 100  # Annualized
        
        # Determine condition
        if volatility > 100:
            return MarketCondition.VOLATILE
        elif volatility < 20:
            return MarketCondition.CALM
        elif trend_strength > 0.5:
            return MarketCondition.TRENDING_UP if trend_slope > 0 else MarketCondition.TRENDING_DOWN
        else:
            return MarketCondition.RANGING
    
    def calculate_market_structure(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze market structure for better entries."""
        structure = {}
        
        # Find support and resistance levels
        highs = df['high'].rolling(window=20).max()
        lows = df['low'].rolling(window=20).min()
        
        structure['resistance'] = highs.iloc[-1]
        structure['support'] = lows.iloc[-1]
        
        # Calculate pivot points
        last_high = df['high'].iloc[-1]
        last_low = df['low'].iloc[-1]
        last_close = df['close'].iloc[-1]
        
        pivot = (last_high + last_low + last_close) / 3
        structure['pivot'] = pivot
        structure['r1'] = 2 * pivot - last_low
        structure['s1'] = 2 * pivot - last_high
        
        # Volume profile
        structure['volume_weighted_price'] = (df['volume'] * df['close']).sum() / df['volume'].sum()
        
        return structure
    
    def get_trading_session(self) -> TradingSession:
        """Determine current trading session based on UTC time."""
        now = datetime.now(timezone.utc)
        hour = now.hour
        
        if 0 <= hour < 7:
            return TradingSession.ASIAN
        elif 7 <= hour < 12:
            return TradingSession.EUROPEAN
        elif 12 <= hour < 16:
            return TradingSession.OVERLAP
        else:
            return TradingSession.AMERICAN

class OrderBookAnalyzer:
    """Analyze order book for optimal entry/exit."""
    
    def __init__(self, session: HTTP):
        self.session = session
        
    def get_order_book_imbalance(self, symbol: str, depth: int = 20) -> Tuple[float, float, float]:
        """Calculate order book imbalance and spread."""
        try:
            res = self.session.get_orderbook(category="linear", symbol=symbol, limit=depth)
            if res['retCode'] == 0:
                bids = [(float(b[0]), float(b[1])) for b in res['result']['b']]
                asks = [(float(a[0]), float(a[1])) for a in res['result']['a']]
                
                bid_volume = sum(b[1] for b in bids)
                ask_volume = sum(a[1] for a in asks)
                
                imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume) if (bid_volume + ask_volume) > 0 else 0
                spread = (asks[0][0] - bids[0][0]) / bids[0][0] * 100 if bids and asks else 0
                
                return imbalance, spread, (bids[0][0] + asks[0][0]) / 2 if bids and asks else 0
        except Exception as e:
            return 0, 0, 0
    
    def find_optimal_entry_price(self, side: str, orderbook_data: Dict) -> float:
        """Find optimal limit order price based on order book."""
        if side == "Buy":
            # Place slightly above best bid for better fill probability
            return orderbook_data['bid'] * 1.0001
        else:
            # Place slightly below best ask
            return orderbook_data['ask'] * 0.9999

# =====================================================================
# ADVANCED INDICATORS
# =====================================================================

class IndicatorEngine:
    """Enhanced indicator calculations with multiple timeframes."""
    
    def __init__(self, config: EnhancedConfig):
        self.config = config
        self.indicators_cache = {}
        
    def calculate_multi_timeframe_indicators(self, dfs: Dict[str, pd.DataFrame]) -> Dict[str, Dict]:
        """Calculate indicators across multiple timeframes."""
        results = {}
        
        for timeframe, df in dfs.items():
            if df is None or len(df) < 50:
                continue
                
            # Adaptive SuperTrend parameters based on volatility
            volatility = df['close'].pct_change().std()
            st_period = self._adaptive_period(volatility)
            st_multiplier = self._adaptive_multiplier(volatility)
            
            # Calculate indicators
            df = self._calculate_supertrend(df, st_period, st_multiplier)
            df = self._calculate_additional_indicators(df)
            
            results[timeframe] = {
                'supertrend_direction': df['st_direction'].iloc[-1],
                'supertrend_line': df['st_line'].iloc[-1],
                'rsi': df['rsi'].iloc[-1],
                'macd_signal': df['macd_signal'].iloc[-1],
                'adx': df['adx'].iloc[-1],
                'volume_ratio': df['volume_ratio'].iloc[-1],
                'bb_position': df['bb_position'].iloc[-1],
                'ema_trend': df['ema_trend'].iloc[-1],
                'atr': df['atr'].iloc[-1]
            }
            
        return results
    
    def _adaptive_period(self, volatility: float) -> int:
        """Adjust SuperTrend period based on volatility."""
        if volatility < 0.01:
            return self.config.ST_PERIOD_MAX
        elif volatility > 0.03:
            return self.config.ST_PERIOD_MIN
        else:
            # Linear interpolation
            ratio = (volatility - 0.01) / 0.02
            return int(self.config.ST_PERIOD_MAX - ratio * (self.config.ST_PERIOD_MAX - self.config.ST_PERIOD_MIN))
    
    def _adaptive_multiplier(self, volatility: float) -> float:
        """Adjust SuperTrend multiplier based on volatility."""
        if volatility < 0.01:
            return self.config.ST_MULTIPLIER_MIN
        elif volatility > 0.03:
            return self.config.ST_MULTIPLIER_MAX
        else:
            ratio = (volatility - 0.01) / 0.02
            return self.config.ST_MULTIPLIER_MIN + ratio * (self.config.ST_MULTIPLIER_MAX - self.config.ST_MULTIPLIER_MIN)
    
    def _calculate_supertrend(self, df: pd.DataFrame, period: int, multiplier: float) -> pd.DataFrame:
        """Enhanced SuperTrend calculation."""
        # ATR
        df['h-l'] = df['high'] - df['low']
        df['h-pc'] = abs(df['high'] - df['close'].shift(1))
        df['l-pc'] = abs(df['low'] - df['close'].shift(1))
        df['tr'] = df[['h-l', 'h-pc', 'l-pc']].max(axis=1)
        df['atr'] = df['tr'].rolling(window=period).mean()
        
        # SuperTrend bands
        hl_avg = (df['high'] + df['low']) / 2
        df['upper_band'] = hl_avg + (multiplier * df['atr'])
        df['lower_band'] = hl_avg - (multiplier * df['atr'])
        
        # SuperTrend calculation with smoothing
        df['st_line'] = 0.0
        df['st_direction'] = 1
        
        for i in range(period, len(df)):
            if i == period:
                df.loc[i, 'st_line'] = df.loc[i, 'upper_band']
                df.loc[i, 'st_direction'] = -1
            else:
                # Previous values
                prev_direction = df.loc[i-1, 'st_direction']
                
                if prev_direction == 1:  # Uptrend
                    if df.loc[i, 'close'] <= df.loc[i, 'lower_band']:
                        df.loc[i, 'st_direction'] = -1
                        df.loc[i, 'st_line'] = df.loc[i, 'upper_band']
                    else:
                        df.loc[i, 'st_direction'] = 1
                        df.loc[i, 'st_line'] = max(df.loc[i, 'lower_band'], df.loc[i-1, 'st_line'])
                else:  # Downtrend
                    if df.loc[i, 'close'] >= df.loc[i, 'upper_band']:
                        df.loc[i, 'st_direction'] = 1
                        df.loc[i, 'st_line'] = df.loc[i, 'lower_band']
                    else:
                        df.loc[i, 'st_direction'] = -1
                        df.loc[i, 'st_line'] = min(df.loc[i, 'upper_band'], df.loc[i-1, 'st_line'])
        
        # Clean up
        df.drop(['h-l', 'h-pc', 'l-pc', 'tr', 'upper_band', 'lower_band'], axis=1, inplace=True, errors='ignore')
        
        return df
    
    def _calculate_additional_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate additional technical indicators."""
        # RSI
        df['rsi'] = ta.rsi(df['close'], length=14)
        
        # MACD
        macd = ta.macd(df['close'])
        df['macd'] = macd['MACD_12_26_9']
        df['macd_signal'] = macd['MACDs_12_26_9']
        df['macd_hist'] = macd['MACDh_12_26_9']
        
        # ADX
        adx = ta.adx(df['high'], df['low'], df['close'])
        df['adx'] = adx['ADX_14']
        
        # Bollinger Bands
        bb = ta.bbands(df['close'])
        df['bb_upper'] = bb['BBU_20_2.0']
        df['bb_middle'] = bb['BBM_20_2.0']
        df['bb_lower'] = bb['BBL_20_2.0']
        df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
        
        # Volume analysis
        df['volume_sma'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_sma']
        
        # EMA trend
        df['ema_9'] = ta.ema(df['close'], length=9)
        df['ema_21'] = ta.ema(df['close'], length=21)
        df['ema_trend'] = np.where(df['ema_9'] > df['ema_21'], 1, -1)
        
        # VWAP
        df['vwap'] = ta.vwap(df['high'], df['low'], df['close'], df['volume'])
        
        # Stochastic RSI
        stoch_rsi = ta.stochrsi(df['close'])
        df['stoch_rsi_k'] = stoch_rsi['STOCHRSIk_14_14_3_3']
        df['stoch_rsi_d'] = stoch_rsi['STOCHRSId_14_14_3_3']
        
        return df

# =====================================================================
# SIGNAL GENERATION
# =====================================================================

class SignalGenerator:
    """Advanced signal generation with multiple confirmations."""
    
    def __init__(self, config: EnhancedConfig, state: EnhancedBotState):
        self.config = config
        self.state = state
        self.ml_model = None
        self.scaler = None
        
        if config.USE_ML_SIGNALS:
            self._load_ml_model()
    
    def generate_signal(self, indicators: Dict[str, Dict], market_condition: MarketCondition, 
                       order_book_imbalance: float) -> Tuple[Signal, float]:
        """Generate trading signal with confidence score."""
        
        # Get primary timeframe indicators
        primary = indicators.get(self.config.PRIMARY_TIMEFRAME, {})
        if not primary:
            return Signal.NEUTRAL, 0.0
        
        # Base SuperTrend signal
        base_signal = self._get_supertrend_signal(primary)
        if base_signal == Signal.NEUTRAL:
            return Signal.NEUTRAL, 0.0
        
        # Calculate signal strength
        confirmations = []
        
        # 1. Multi-timeframe alignment
        mtf_score = self._check_mtf_alignment(indicators, base_signal)
        confirmations.append(mtf_score)
        
        # 2. Indicator confluence
        indicator_score = self._check_indicator_confluence(primary, base_signal)
        confirmations.append(indicator_score)
        
        # 3. Market condition alignment
        market_score = self._check_market_condition(market_condition, base_signal)
        confirmations.append(market_score)
        
        # 4. Order book analysis
        orderbook_score = self._check_orderbook(order_book_imbalance, base_signal)
        confirmations.append(orderbook_score)
        
        # 5. Volume confirmation
        volume_score = self._check_volume(primary)
        confirmations.append(volume_score)
        
        # Calculate final confidence
        confidence = mean(confirmations)
        
        # Apply ML prediction if enabled
        if self.config.USE_ML_SIGNALS and self.ml_model:
            ml_confidence = self._get_ml_prediction(indicators)
            confidence = (confidence + ml_confidence) / 2
        
        # Determine signal strength
        if confidence >= 0.8:
            signal = Signal.STRONG_BUY if base_signal == Signal.BUY else Signal.STRONG_SELL
        elif confidence >= 0.6:
            signal = base_signal
        else:
            signal = Signal.NEUTRAL
        
        return signal, confidence
    
    def _get_supertrend_signal(self, indicators: Dict) -> Signal:
        """Get base signal from SuperTrend."""
        if indicators.get('supertrend_direction') == 1:
            return Signal.BUY
        elif indicators.get('supertrend_direction') == -1:
            return Signal.SELL
        return Signal.NEUTRAL
    
    def _check_mtf_alignment(self, indicators: Dict[str, Dict], base_signal: Signal) -> float:
        """Check multi-timeframe alignment."""
        aligned = 0
        total = 0
        
        for tf, ind in indicators.items():
            if ind.get('supertrend_direction'):
                total += 1
                if (base_signal == Signal.BUY and ind['supertrend_direction'] == 1) or \
                   (base_signal == Signal.SELL and ind['supertrend_direction'] == -1):
                    aligned += 1
        
        return aligned / total if total > 0 else 0.5
    
    def _check_indicator_confluence(self, indicators: Dict, base_signal: Signal) -> float:
        """Check indicator confluence."""
        scores = []
        
        # RSI
        rsi = indicators.get('rsi', 50)
        if base_signal == Signal.BUY:
            scores.append(1.0 if rsi < 70 else 0.5 if rsi < 80 else 0.0)
        else:
            scores.append(1.0 if rsi > 30 else 0.5 if rsi > 20 else 0.0)
        
        # MACD
        macd_signal = indicators.get('macd_signal', 0)
        if (base_signal == Signal.BUY and macd_signal > 0) or \
           (base_signal == Signal.SELL and macd_signal < 0):
            scores.append(1.0)
        else:
            scores.append(0.3)
        
        # ADX (trend strength)
        adx = indicators.get('adx', 0)
        if adx > self.config.ADX_MIN_THRESHOLD:
            scores.append(1.0)
        elif adx > 20:
            scores.append(0.6)
        else:
            scores.append(0.3)
        
        # EMA trend
        ema_trend = indicators.get('ema_trend', 0)
        if (base_signal == Signal.BUY and ema_trend == 1) or \
           (base_signal == Signal.SELL and ema_trend == -1):
            scores.append(1.0)
        else:
            scores.append(0.2)
        
        return mean(scores)
    
    def _check_market_condition(self, condition: MarketCondition, base_signal: Signal) -> float:
        """Check if market condition supports the signal."""
        if condition == MarketCondition.TRENDING_UP and base_signal == Signal.BUY:
            return 1.0
        elif condition == MarketCondition.TRENDING_DOWN and base_signal == Signal.SELL:
            return 1.0
        elif condition == MarketCondition.VOLATILE:
            return 0.3  # Avoid volatile markets
        elif condition == MarketCondition.RANGING:
            return 0.5  # Neutral for ranging markets
        else:
            return 0.6
    
    def _check_orderbook(self, imbalance: float, base_signal: Signal) -> float:
        """Check order book support."""
        if base_signal == Signal.BUY and imbalance > self.config.IMBALANCE_THRESHOLD:
            return 1.0
        elif base_signal == Signal.SELL and imbalance < -self.config.IMBALANCE_THRESHOLD:
            return 1.0
        elif abs(imbalance) < 0.2:
            return 0.5  # Neutral order book
        else:
            return 0.3
    
    def _check_volume(self, indicators: Dict) -> float:
        """Check volume confirmation."""
        volume_ratio = indicators.get('volume_ratio', 1.0)
        if volume_ratio > self.config.VOLUME_MULTIPLIER:
            return 1.0
        elif volume_ratio > 1.0:
            return 0.7
        else:
            return 0.4
    
    def _load_ml_model(self):
        """Load pre-trained ML model for signal prediction."""
        try:
            if os.path.exists(self.config.ML_MODEL_PATH):
                self.ml_model = joblib.load(self.config.ML_MODEL_PATH)
                self.scaler = joblib.load(self.config.ML_MODEL_PATH.replace('.pkl', '_scaler.pkl'))
        except Exception as e:
            print(f"Failed to load ML model: {e}")
    
    def _get_ml_prediction(self, indicators: Dict[str, Dict]) -> float:
        """Get ML model prediction confidence."""
        if not self.ml_model:
            return 0.5
        
        try:
            # Prepare features
            features = []
            for tf, ind in indicators.items():
                features.extend([
                    ind.get('rsi', 50),
                    ind.get('macd_signal', 0),
                    ind.get('adx', 25),
                    ind.get('volume_ratio', 1),
                    ind.get('bb_position', 0.5)
                ])
            
            # Scale and predict
            features_scaled = self.scaler.transform([features])
            prediction_proba = self.ml_model.predict_proba(features_scaled)[0]
            
            return max(prediction_proba)
        except Exception:
            return 0.5

# =====================================================================
# RISK MANAGEMENT
# =====================================================================

class RiskManager:
    """Advanced risk and position management."""
    
    def __init__(self, config: EnhancedConfig, state: EnhancedBotState):
        self.config = config
        self.state = state
        
    def calculate_position_size(self, balance: Decimal, entry_price: Decimal, 
                               stop_loss: Decimal, signal_strength: float) -> Decimal:
        """Calculate position size with Kelly Criterion and signal strength."""
        
        # Base risk amount
        risk_amount = balance * Decimal(str(self.config.RISK_PER_TRADE_PCT / 100))
        
        # Adjust by signal strength
        risk_amount *= Decimal(str(signal_strength))
        
        # Apply Kelly Criterion if we have sufficient history
        if self.state.metrics.total_trades >= 20:
            kelly_fraction = self._calculate_kelly_fraction()
            risk_amount *= Decimal(str(min(kelly_fraction, 0.25)))  # Cap at 25%
        
        # Calculate position size based on stop loss distance
        stop_distance = abs(entry_price - stop_loss) / entry_price
        position_value = risk_amount / stop_distance
        
        # Apply maximum position size limit
        max_position_value = balance * Decimal(str(self.config.MAX_POSITION_SIZE_PCT / 100))
        position_value = min(position_value, max_position_value)
        
        # Convert to quantity
        quantity = position_value / entry_price
        
        return quantity
    
    def _calculate_kelly_fraction(self) -> float:
        """Calculate Kelly fraction for optimal position sizing."""
        win_rate = self.state.metrics.win_rate
        if win_rate == 0 or win_rate == 1:
            return 0.1  # Default conservative fraction
        
        avg_win = abs(self.state.metrics.avg_win) if self.state.metrics.avg_win != 0 else 1
        avg_loss = abs(self.state.metrics.avg_loss) if self.state.metrics.avg_loss != 0 else 1
        
        win_loss_ratio = avg_win / avg_loss
        kelly = (win_rate * win_loss_ratio - (1 - win_rate)) / win_loss_ratio
        
        return max(0, min(kelly, 0.25))  # Limit between 0 and 25%
    
    def should_trade(self) -> Tuple[bool, str]:
        """Check if trading conditions are met."""
        
        # Check daily loss limit
        today_pnl = self.state.metrics.daily_pnl.get(datetime.now().strftime("%Y-%m-%d"), 0)
        if today_pnl <= -self.config.MAX_DAILY_LOSS_PCT:
            return False, "Daily loss limit reached"
        
        # Check consecutive losses
        if self.state.metrics.consecutive_losses >= self.config.MAX_CONSECUTIVE_LOSSES:
            return False, f"Max consecutive losses ({self.config.MAX_CONSECUTIVE_LOSSES}) reached"
        
        # Check daily trade limit
        today = datetime.now().strftime("%Y-%m-%d")
        today_trades = sum(1 for trade in self.state.trade_history 
                          if trade.get('date') == today)
        if today_trades >= self.config.MAX_DAILY_TRADES:
            return False, "Daily trade limit reached"
        
        # Check win rate (after sufficient trades)
        if self.state.metrics.total_trades >= 20:
            if self.state.metrics.win_rate < self.config.MIN_WIN_RATE:
                return False, f"Win rate too low: {self.state.metrics.win_rate:.1%}"
            
            if self.state.metrics.profit_factor < self.config.MIN_PROFIT_FACTOR:
                return False, f"Profit factor too low: {self.state.metrics.profit_factor:.2f}"
        
        # Check trading session
        current_session = MarketAnalyzer(self.config).get_trading_session()
        if current_session.name not in self.config.TRADE_SESSIONS:
            return False, f"Outside trading sessions: {current_session.name}"
        
        return True, "OK"
    
    def calculate_stop_loss(self, entry_price: float, side: str, atr: float) -> float:
        """Calculate dynamic stop loss based on ATR."""
        # Use ATR-based stop loss for better adaptation to volatility
        atr_multiplier = 1.5
        stop_distance = atr * atr_multiplier
        
        if side == "Buy":
            stop_loss = entry_price - stop_distance
        else:
            stop_loss = entry_price + stop_distance
        
        # Apply minimum stop loss percentage
        min_stop_distance = entry_price * (self.config.STOP_LOSS_PCT / 100)
        
        if side == "Buy":
            stop_loss = min(stop_loss, entry_price - min_stop_distance)
        else:
            stop_loss = max(stop_loss, entry_price + min_stop_distance)
        
        return stop_loss
    
    def calculate_take_profit_levels(self, entry_price: float, side: str, atr: float) -> List[Dict]:
        """Calculate multiple take profit levels."""
        levels = []
        
        for tp_config in self.config.PARTIAL_TP_LEVELS:
            if side == "Buy":
                tp_price = entry_price * (1 + tp_config['profit_pct'] / 100)
            else:
                tp_price = entry_price * (1 - tp_config['profit_pct'] / 100)
            
            levels.append({
                'price': tp_price,
                'quantity_pct': tp_config['close_pct']
            })
        
        return levels

# =====================================================================
# WEBSOCKET DATA HANDLER
# =====================================================================

class WebSocketHandler:
    """Handle WebSocket connections for real-time data."""
    
    def __init__(self, config: EnhancedConfig, state: EnhancedBotState, testnet: bool = True):
        self.config = config
        self.state = state
        self.ws = WebSocket(
            testnet=testnet,
            channel_type="linear",
            api_key=config.API_KEY,
            api_secret=config.API_SECRET
        )
        self.subscriptions = []
        
    def start(self):
        """Start WebSocket connection."""
        # Subscribe to multiple data streams
        self.ws.kline_stream(
            interval=1,
            symbol=self.config.SYMBOL,
            callback=self._handle_kline
        )
        
        self.ws.orderbook_stream(
            depth=25,
            symbol=self.config.SYMBOL,
            callback=self._handle_orderbook
        )
        
        self.ws.trade_stream(
            symbol=self.config.SYMBOL,
            callback=self._handle_trades
        )
        
    def _handle_kline(self, message):
        """Handle kline updates."""
        try:
            data = message['data'][0]
            market_data = MarketData(
                timestamp=datetime.fromtimestamp(data['timestamp'] / 1000),
                open=float(data['open']),
                high=float(data['high']),
                low=float(data['low']),
                close=float(data['close']),
                volume=float(data['volume'])
            )
            
            with self.state.lock:
                self.state.market_data[str(data['interval'])] = market_data
                
        except Exception as e:
            print(f"Error handling kline: {e}")
    
    def _handle_orderbook(self, message):
        """Handle orderbook updates."""
        try:
            data = message['data']
            bids = data.get('b', [])
            asks = data.get('a', [])
            
            if bids and asks:
                bid = float(bids[0][0])
                ask = float(asks[0][0])
                spread = (ask - bid) / bid * 100
                
                # Calculate imbalance
                bid_volume = sum(float(b[1]) for b in bids[:10])
                ask_volume = sum(float(a[1]) for a in asks[:10])
                imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
                
                with self.state.lock:
                    if '1' in self.state.market_data:
                        self.state.market_data['1'].bid = bid
                        self.state.market_data['1'].ask = ask
                        self.state.market_data['1'].spread = spread
                        self.state.market_data['1'].order_book_imbalance = imbalance
                        
        except Exception as e:
            print(f"Error handling orderbook: {e}")
    
    def _handle_trades(self, message):
        """Handle trade updates for market sentiment."""
        try:
            # Analyze recent trades for aggressor side
            # This can be used for additional signal confirmation
            pass
        except Exception:
            pass

# =====================================================================
# ENHANCED UI
# =====================================================================

class EnhancedBotUI(threading.Thread):
    """Enhanced real-time terminal UI with more information."""
    
    def __init__(self, state: EnhancedBotState):
        super().__init__(daemon=True)
        self.state = state
        self._stop_event = threading.Event()
        
    def stop(self):
        self._stop_event.set()
    
    def run(self):
        while not self._stop_event.is_set():
            self.display()
            time.sleep(0.5)  # Faster refresh
    
    def display(self):
        with self.state.lock:
            os.system('cls' if os.name == 'nt' else 'clear')
            
            # Header
            print(Style.BRIGHT + Fore.CYAN + "=" * 80 + Style.RESET_ALL)
            print(Style.BRIGHT + Fore.CYAN + f"    ADVANCED SUPERTREND BOT | {self.state.symbol} | {self.state.bot_status}" + Style.RESET_ALL)
            print(Style.BRIGHT + Fore.CYAN + "=" * 80 + Style.RESET_ALL)
            
            # Market Overview
            self._display_market_overview()
            
            # Indicators Dashboard
            self._display_indicators()
            
            # Position Information
            self._display_position()
            
            # Performance Metrics
            self._display_performance()
            
            # Recent Logs
            self._display_logs()
            
            print(Style.BRIGHT + Fore.CYAN + "=" * 80 + Style.RESET_ALL)
            print(Fore.YELLOW + "Press Ctrl+C to exit gracefully" + Style.RESET_ALL)
    
    def _display_market_overview(self):
        """Display market overview section."""
        print(Style.BRIGHT + "\n📊 MARKET OVERVIEW" + Style.RESET_ALL)
        print("-" * 40)
        
        if '1' in self.state.market_data:
            data = self.state.market_data['1']
            
            # Price with direction
            price_color = Fore.GREEN if data.close > data.open else Fore.RED
            arrow = "↑" if data.close > data.open else "↓"
            
            print(f"Price: {price_color}{data.close:.2f} {arrow}{Style.RESET_ALL}")
            print(f"Bid/Ask: {data.bid:.2f} / {data.ask:.2f} (Spread: {data.spread:.3f}%)")
            print(f"24h Volume: {data.volume:,.0f}")
            
            # Order book imbalance
            imb_color = Fore.GREEN if data.order_book_imbalance > 0.2 else Fore.RED if data.order_book_imbalance < -0.2 else Fore.YELLOW
            print(f"Order Book Imbalance: {imb_color}{data.order_book_imbalance:.2%}{Style.RESET_ALL}")
        
        # Market condition
        condition_colors = {
            MarketCondition.TRENDING_UP: Fore.GREEN,
            MarketCondition.TRENDING_DOWN: Fore.RED,
            MarketCondition.RANGING: Fore.YELLOW,
            MarketCondition.VOLATILE: Fore.MAGENTA,
            MarketCondition.CALM: Fore.CYAN
        }
        
        color = condition_colors.get(self.state.market_condition, Fore.WHITE)
        print(f"Market Condition: {color}{self.state.market_condition.value}{Style.RESET_ALL}")
        print(f"Trading Session: {self.state.current_session.value}")
    
    def _display_indicators(self):
        """Display indicators section."""
        print(Style.BRIGHT + "\n📈 INDICATORS" + Style.RESET_ALL)
        print("-" * 40)
        
        indicators = self.state.indicator_values
        
        # SuperTrend
        if 'supertrend_direction' in indicators:
            st_color = Fore.GREEN if indicators['supertrend_direction'] == 1 else Fore.RED
            st_text = "BULLISH" if indicators['supertrend_direction'] == 1 else "BEARISH"
            print(f"SuperTrend: {st_color}{st_text} @ {indicators.get('supertrend_line', 0):.2f}{Style.RESET_ALL}")
        
        # Other indicators in a grid
        if indicators:
            # RSI
            rsi = indicators.get('rsi', 50)
            rsi_color = Fore.RED if rsi > 70 else Fore.GREEN if rsi < 30 else Fore.YELLOW
            
            # ADX
            adx = indicators.get('adx', 0)
            adx_color = Fore.GREEN if adx > 25 else Fore.YELLOW
            
            # MACD
            macd = indicators.get('macd_signal', 0)
            macd_color = Fore.GREEN if macd > 0 else Fore.RED
            
            print(f"RSI: {rsi_color}{rsi:.1f}{Style.RESET_ALL} | "
                  f"ADX: {adx_color}{adx:.1f}{Style.RESET_ALL} | "
                  f"MACD: {macd_color}{macd:.4f}{Style.RESET_ALL}")
            
            # Signal strength
            if self.state.signal_strength > 0:
                strength_color = Fore.GREEN if self.state.signal_strength > 0.7 else Fore.YELLOW if self.state.signal_strength > 0.5 else Fore.RED
                print(f"Signal Strength: {strength_color}{'█' * int(self.state.signal_strength * 10)}{Style.RESET_ALL} {self.state.signal_strength:.1%}")
    
    def _display_position(self):
        """Display position information."""
        print(Style.BRIGHT + "\n💼 POSITION" + Style.RESET_ALL)
        print("-" * 40)
        
        if self.state.position:
            pos = self.state.position
            
            # Position side with color
            side_color = Fore.GREEN if pos.side == "Buy" else Fore.RED
            print(f"Side: {side_color}{pos.side}{Style.RESET_ALL} | Size: {pos.size:.4f}")
            print(f"Entry: ${pos.entry_price:.2f} | Current: ${pos.current_price:.2f}")
            
            # PnL with color
            pnl_color = Fore.GREEN if pos.unrealized_pnl >= 0 else Fore.RED
            pnl_pct_color = Fore.GREEN if pos.pnl_percentage >= 0 else Fore.RED
            print(f"PnL: {pnl_color}${pos.unrealized_pnl:.2f}{Style.RESET_ALL} "
                  f"({pnl_pct_color}{pos.pnl_percentage:+.2f}%{Style.RESET_ALL})")
            
            # Stop loss and take profit
            print(f"SL: ${pos.stop_loss:.2f} | TP: ${pos.take_profit:.2f}")
            
            # Status flags
            flags = []
            if pos.trailing_activated:
                flags.append(f"{Fore.CYAN}TRAILING{Style.RESET_ALL}")
            if pos.breakeven_activated:
                flags.append(f"{Fore.GREEN}BREAKEVEN{Style.RESET_ALL}")
            if pos.partial_closes_done > 0:
                flags.append(f"{Fore.YELLOW}PARTIAL {pos.partial_closes_done}/3{Style.RESET_ALL}")
            
            if flags:
                print(f"Status: {' | '.join(flags)}")
            
            # Time in position
            time_in_position = datetime.now() - pos.entry_time
            print(f"Duration: {time_in_position.total_seconds() // 3600:.0f}h {(time_in_position.total_seconds() % 3600) // 60:.0f}m")
        else:
            print(Fore.YELLOW + "No active position" + Style.RESET_ALL)
    
    def _display_performance(self):
        """Display performance metrics."""
        print(Style.BRIGHT + "\n📊 PERFORMANCE" + Style.RESET_ALL)
        print("-" * 40)
        
        metrics = self.state.metrics
        
        # Win rate with color
        wr_color = Fore.GREEN if metrics.win_rate >= 0.5 else Fore.YELLOW if metrics.win_rate >= 0.4 else Fore.RED
        
        # Today's PnL
        today_pnl = metrics.daily_pnl.get(datetime.now().strftime("%Y-%m-%d"), 0)
        today_color = Fore.GREEN if today_pnl > 0 else Fore.RED if today_pnl < 0 else Fore.WHITE
        
        print(f"Win Rate: {wr_color}{metrics.win_rate:.1%}{Style.RESET_ALL} "
              f"({metrics.winning_trades}W/{metrics.losing_trades}L)")
        print(f"Today's PnL: {today_color}${today_pnl:.2f}{Style.RESET_ALL}")
        print(f"Total PnL: ${metrics.total_pnl:.2f} | Profit Factor: {metrics.profit_factor:.2f}")
        
        # Streak indicator
        if metrics.consecutive_wins > 0:
            print(f"Streak: {Fore.GREEN}↑{metrics.consecutive_wins} wins{Style.RESET_ALL}")
        elif metrics.consecutive_losses > 0:
            print(f"Streak: {Fore.RED}↓{metrics.consecutive_losses} losses{Style.RESET_ALL}")
        
        print(f"Best/Worst: ${metrics.best_trade:.2f} / ${metrics.worst_trade:.2f}")
    
    def _display_logs(self):
        """Display recent log messages."""
        print(Style.BRIGHT + "\n📝 RECENT ACTIVITY" + Style.RESET_ALL)
        print("-" * 40)
        
        for msg in list(self.state.log_messages)[-5:]:  # Show last 5 messages
            print(msg)

# =====================================================================
# MAIN BOT CLASS
# =====================================================================

class EnhancedSupertrendBot:
    """Enhanced main trading bot with all advanced features."""
    
    def __init__(self, config: EnhancedConfig):
        self.config = config
        self.logger = self._setup_logger()
        self.state = EnhancedBotState(symbol=config.SYMBOL)
        
        # Initialize components
        self.session = HTTP(
            testnet=config.TESTNET,
            api_key=config.API_KEY,
            api_secret=config.API_SECRET
        )
        
        self.market_analyzer = MarketAnalyzer(config)
        self.orderbook_analyzer = OrderBookAnalyzer(self.session)
        self.indicator_engine = IndicatorEngine(config)
        self.signal_generator = SignalGenerator(config, self.state)
        self.risk_manager = RiskManager(config, self.state)
        
        # WebSocket handler
        self.ws_handler = WebSocketHandler(config, self.state, config.TESTNET)
        
        # UI
        self.ui = EnhancedBotUI(self.state)
        
        # Control
        self._stop_requested = False
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Performance tracking
        self.trade_start_time = None
        
    def _setup_logger(self) -> logging.Logger:
        """Setup enhanced logger."""
        logger = logging.getLogger('EnhancedSupertrendBot')
        logger.setLevel(self.config.LOG_LEVEL.upper())
        
        # File handler with rotation
        file_handler = logging.handlers.RotatingFileHandler(
            'enhanced_bot.log',
            maxBytes=10*1024*1024,
            backupCount=5
        )
        file_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        )
        logger.addHandler(file_handler)
        
        return logger
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.state.update(bot_status="Shutting down...")
        self._stop_requested = True
    
    async def run(self):
        """Main bot execution loop."""
        self.logger.info("Starting Enhanced Supertrend Bot...")
        self.state.update(bot_status="Running")
        
        # Start UI
        self.ui.start()
        
        # Start WebSocket
        self.ws_handler.start()
        
        # Main loop
        while not self._stop_requested:
            try:
                # Fetch multi-timeframe data
                dfs = {}
                for tf in self.config.TIMEFRAMES:
                    df = self._fetch_klines(tf)
                    if df is not None:
                        dfs[tf] = df
                
                if not dfs:
                    await asyncio.sleep(5)
                    continue
                
                # Calculate indicators
                indicators = self.indicator_engine.calculate_multi_timeframe_indicators(dfs)
                self.state.update(indicator_values=indicators.get(self.config.PRIMARY_TIMEFRAME, {}))
                
                # Analyze market
                primary_df = dfs.get(self.config.PRIMARY_TIMEFRAME)
                if primary_df is not None:
                    market_condition = self.market_analyzer.analyze_market_condition(primary_df)
                    market_structure = self.market_analyzer.calculate_market_structure(primary_df)
                    self.state.update(market_condition=market_condition)
                
                # Get order book data
                imbalance, spread, mid_price = self.orderbook_analyzer.get_order_book_imbalance(
                    self.config.SYMBOL, 
                    self.config.ORDER_BOOK_DEPTH
                )
                
                # Check existing position
                position = self._get_position()
                
                if position:
                    # Manage existing position
                    await self._manage_position(position, indicators)
                else:
                    # Look for new entry
                    can_trade, reason = self.risk_manager.should_trade()
                    
                    if can_trade:
                        # Generate signal
                        signal, confidence = self.signal_generator.generate_signal(
                            indicators, 
                            market_condition,
                            imbalance
                        )
                        
                        self.state.update(signal_strength=confidence)
                        
                        if signal in [Signal.BUY, Signal.STRONG_BUY, Signal.SELL, Signal.STRONG_SELL]:
                            await self._enter_position(signal, confidence, primary_df.iloc[-1])
                    else:
                        self.state.add_log(f"Trading paused: {reason}", "WARNING")
                
                # Update session
                self.state.update(current_session=self.market_analyzer.get_trading_session())
                
                # Sleep based on timeframe
                await asyncio.sleep(10 if self.config.PRIMARY_TIMEFRAME == "1" else 30)
                
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}", exc_info=True)
                self.state.errors_count += 1
                
                if self.state.errors_count > 10:
                    self.logger.critical("Too many errors, shutting down")
                    break
                
                await asyncio.sleep(30)
        
        # Cleanup
        self.ui.stop()
        self.logger.info("Bot shutdown complete")
    
    def _fetch_klines(self, timeframe: str) -> Optional[pd.DataFrame]:
        """Fetch kline data."""
        try:
            res = self.session.get_kline(
                category=self.config.CATEGORY,
                symbol=self.config.SYMBOL,
                interval=timeframe,
                limit=200
            )
            
            if res['retCode'] == 0:
                df = pd.DataFrame(res['result']['list'])
                df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover']
                
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = pd.to_numeric(df[col])
                
                df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float), unit='ms')
                df = df.sort_values('timestamp').reset_index(drop=True)
                
                return df
                
        except Exception as e:
            self.logger.error(f"Error fetching klines: {e}")
            return None
    
    def _get_position(self) -> Optional[PositionInfo]:
        """Get current position."""
        try:
            res = self.session.get_positions(
                category=self.config.CATEGORY,
                symbol=self.config.SYMBOL
            )
            
            if res['retCode'] == 0:
                for pos in res['result']['list']:
                    if float(pos['size']) > 0:
                        position = PositionInfo(
                            symbol=pos['symbol'],
                            side=pos['side'],
                            size=float(pos['size']),
                            entry_price=float
