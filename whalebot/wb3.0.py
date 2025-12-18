#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ultimate Enhanced Whale Bot - Next Generation Trading System
Author: MiniMax Agent
Version: 4.0 Refactored (pandas_ta)
Description: Revolutionary trading bot with AI-powered strategies, advanced risk management,
real-time adaptation, and institutional-grade features for maximum profitability
"""

import time
import json
import logging
import threading
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Union
from pybit.unified_trading import WebSocket, HTTP
from pybit.exceptions import InvalidRequestError
import pandas_ta as ta  # Replaced talib with pandas_ta as ta
from dataclasses import dataclass, asdict
from abc import ABC, abstractmethod
import warnings
warnings.filterwarnings('ignore')

# Setup matplotlib for plotting
def setup_matplotlib_for_plotting():
    """Setup matplotlib for proper chart rendering"""
    import matplotlib.pyplot as plt
    plt.switch_backend("Agg")
    plt.style.use("default")
    plt.rcParams["font.sans-serif"] = ["Noto Sans CJK SC", "WenQuanYi Zen Hei", "PingFang SC", "Arial Unicode MS", "Hiragino Sans GB"]
    plt.rcParams["axes.unicode_minus"] = False

# Configure enhanced logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('whalebot_enhanced.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('EnhancedWhaleBot')

@dataclass
class MarketData:
    """Market data structure"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

@dataclass
class TradeSignal:
    """Trading signal structure"""
    symbol: str
    side: str  # 'long', 'short', 'neutral'
    confidence: float  # 0-1
    strategy: str
    timestamp: datetime
    price: float
    stop_loss: float
    take_profit: float

@dataclass
class Position:
    """Position structure"""
    symbol: str
    side: str
    size: float
    entry_price: float
    entry_time: datetime
    stop_loss: float
    take_profit: float
    strategy: str
    unrealized_pnl: float = 0.0
    trailing_stop: float = 0.0
    max_profit: float = 0.0

class AdvancedTechnicalIndicators:
    """Enhanced Technical Indicators with Additional Calculations using pandas_ta"""

    @staticmethod
    def calculate_ema(prices: np.array, period: int) -> np.array:
        """Exponential Moving Average with error handling using pandas_ta"""
        try:
            if len(prices) < period:
                return np.full(len(prices), np.nan)
            prices_series = pd.Series(prices)
            ema = ta.ema(prices_series, length=period)
            return ema.values
        except Exception as e:
            logger.error(f"Error calculating EMA: {e}")
            return np.full(len(prices), np.nan)

    @staticmethod
    def calculate_sma(prices: np.array, period: int) -> np.array:
        """Simple Moving Average with error handling using pandas_ta"""
        try:
            if len(prices) < period:
                return np.full(len(prices), np.nan)
            prices_series = pd.Series(prices)
            sma = ta.sma(prices_series, length=period)
            return sma.values
        except Exception as e:
            logger.error(f"Error calculating SMA: {e}")
            return np.full(len(prices), np.nan)

    @staticmethod
    def calculate_rsi(prices: np.array, period: int = 14) -> np.array:
        """Relative Strength Index with error handling using pandas_ta"""
        try:
            if len(prices) < period:
                return np.full(len(prices), np.nan)
            prices_series = pd.Series(prices)
            rsi = ta.rsi(prices_series, length=period)
            return rsi.values
        except Exception as e:
            logger.error(f"Error calculating RSI: {e}")
            return np.full(len(prices), np.nan)

    @staticmethod
    def calculate_macd(prices: np.array, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[np.array, np.array, np.array]:
        """MACD with error handling using pandas_ta"""
        try:
            prices_series = pd.Series(prices)
            macd_df = ta.macd(prices_series, fast=fast, slow=slow, signal=signal)

            # Extract relevant columns from pandas_ta output. Column names are dynamic.
            macd_col = f'MACD_{fast}_{slow}_{signal}'
            signal_col = f'MACDs_{fast}_{slow}_{signal}'
            hist_col = f'MACDh_{fast}_{slow}_{signal}'

            if macd_col in macd_df.columns and signal_col in macd_df.columns and hist_col in macd_df.columns:
                return macd_df[macd_col].values, macd_df[signal_col].values, macd_df[hist_col].values
            else:
                raise ValueError("MACD calculation columns not found in output DataFrame.")
        except Exception as e:
            logger.error(f"Error calculating MACD: {e}")
            nan_array = np.full(len(prices), np.nan)
            return nan_array, nan_array, nan_array

    @staticmethod
    def calculate_bollinger_bands(prices: np.array, period: int = 20, std: float = 2.0) -> Tuple[np.array, np.array, np.array]:
        """Bollinger Bands with error handling using pandas_ta"""
        try:
            prices_series = pd.Series(prices)
            bbands_df = ta.bbands(prices_series, length=period, std=std)

            # Extract relevant columns from pandas_ta output. Column names are dynamic.
            upper_col = f'BBU_{period}_{std}'
            middle_col = f'BBM_{period}_{std}'
            lower_col = f'BBL_{period}_{std}'

            if upper_col in bbands_df.columns and middle_col in bbands_df.columns and lower_col in bbands_df.columns:
                return bbands_df[upper_col].values, bbands_df[middle_col].values, bbands_df[lower_col].values
            else:
                raise ValueError("Bollinger Band calculation columns not found in output DataFrame.")
        except Exception as e:
            logger.error(f"Error calculating Bollinger Bands: {e}")
            nan_array = np.full(len(prices), np.nan)
            return nan_array, nan_array, nan_array

    @staticmethod
    def calculate_adx(high: np.array, low: np.array, close: np.array, period: int = 14) -> np.array:
        """Average Directional Index with error handling using pandas_ta"""
        try:
            # pandas_ta ADX requires a DataFrame or separate Series for high, low, close
            adx_series = ta.adx(pd.Series(high), pd.Series(low), pd.Series(close), length=period)
            return adx_series.values
        except Exception as e:
            logger.error(f"Error calculating ADX: {e}")
            return np.full(len(close), np.nan)

    @staticmethod
    def calculate_atr(high: np.array, low: np.array, close: np.array, period: int = 14) -> np.array:
        """Average True Range with error handling using pandas_ta"""
        try:
            atr_series = ta.atr(pd.Series(high), pd.Series(low), pd.Series(close), length=period)
            return atr_series.values
        except Exception as e:
            logger.error(f"Error calculating ATR: {e}")
            return np.full(len(close), np.nan)

    @staticmethod
    def calculate_stochastic(high: np.array, low: np.array, close: np.array, k_period: int = 14, d_period: int = 3) -> Tuple[np.array, np.array]:
        """Stochastic Oscillator with error handling using pandas_ta"""
        try:
            stoch_df = ta.stoch(pd.Series(high), pd.Series(low), pd.Series(close), k=k_period, d=d_period, smooth_k=d_period)

            # Extract relevant columns from pandas_ta output. Column names are dynamic.
            slowk_col = f'STOCHk_{k_period}_{d_period}_{d_period}'
            slowd_col = f'STOCHd_{k_period}_{d_period}_{d_period}'

            if slowk_col in stoch_df.columns and slowd_col in stoch_df.columns:
                return stoch_df[slowk_col].values, stoch_df[slowd_col].values
            else:
                raise ValueError("Stochastic calculation columns not found in output DataFrame.")
        except Exception as e:
            logger.error(f"Error calculating Stochastic: {e}")
            nan_array = np.full(len(close), np.nan)
            return nan_array, nan_array

    @staticmethod
    def calculate_williams_r(high: np.array, low: np.array, close: np.array, period: int = 14) -> np.array:
        """Williams %R with error handling using pandas_ta"""
        try:
            willr_series = ta.willr(pd.Series(high), pd.Series(low), pd.Series(close), length=period)
            return willr_series.values
        except Exception as e:
            logger.error(f"Error calculating Williams %R: {e}")
            return np.full(len(close), np.nan)

    @staticmethod
    def calculate_cci(high: np.array, low: np.array, close: np.array, period: int = 20) -> np.array:
        """Commodity Channel Index with error handling using pandas_ta"""
        try:
            cci_series = ta.cci(pd.Series(high), pd.Series(low), pd.Series(close), length=period)
            return cci_series.values
        except Exception as e:
            logger.error(f"Error calculating CCI: {e}")
            return np.full(len(close), np.nan)

    @staticmethod
    def calculate_obv(close: np.array, volume: np.array) -> np.array:
        """On-Balance Volume with error handling using pandas_ta"""
        try:
            obv_series = ta.obv(pd.Series(close), pd.Series(volume))
            return obv_series.values
        except Exception as e:
            logger.error(f"Error calculating OBV: {e}")
            return np.full(len(close), np.nan)

    @staticmethod
    def calculate_supertrend(high: np.array, low: np.array, close: np.array, period: int = 10, multiplier: float = 3.0) -> Tuple[np.array, np.array]:
        """Super Trend Indicator with error handling"""
        # Note: The original implementation calculates this manually, not using talib.
        # It's kept as-is, but pandas_ta also has a built-in function: ta.supertrend().
        # To refactor to pandas_ta's implementation, replace the manual calculation below with:
        # supertrend_df = ta.supertrend(pd.Series(high), pd.Series(low), pd.Series(close), length=period, multiplier=multiplier)
        # return supertrend_df[f'SUPERT_{period}_{multiplier}'].values, supertrend_df[f'SUPERTd_{period}_{multiplier}'].values
        try:
            if len(close) < period * 2:
                return np.full(len(close), np.nan), np.full(len(close), np.nan)

            atr = AdvancedTechnicalIndicators.calculate_atr(high, low, close, period)
            hl2 = (high + low) / 2

            supertrend = np.zeros_like(close)
            direction = np.ones_like(close)

            supertrend[0] = hl2[0]
            direction[0] = 1

            for i in range(1, len(close)):
                if not np.isnan(atr[i]):
                    upper_band = hl2[i] + (multiplier * atr[i])
                    lower_band = hl2[i] - (multiplier * atr[i])

                    if direction[i-1] == 1 and close[i] <= lower_band[i-1]:
                        direction[i] = -1
                        supertrend[i] = lower_band[i-1]
                    elif direction[i-1] == -1 and close[i] >= upper_band[i-1]:
                        direction[i] = 1
                        supertrend[i] = upper_band[i-1]
                    else:
                        direction[i] = direction[i-1]
                        supertrend[i] = supertrend[i-1]
                else:
                    direction[i] = direction[i-1]
                    supertrend[i] = supertrend[i-1] if i > 0 else hl2[i]

            return supertrend, direction
        except Exception as e:
            logger.error(f"Error calculating Supertrend: {e}")
            return np.full(len(close), np.nan), np.full(len(close), np.nan)

    @staticmethod
    def calculate_vwap(high: np.array, low: np.array, close: np.array, volume: np.array) -> np.array:
        """Volume Weighted Average Price with error handling"""
        # Note: The original implementation calculates this manually, not using talib.
        try:
            if len(close) < 2:
                return np.full(len(close), np.nan)

            typical_price = (high + low + close) / 3
            cumulative_volume = np.cumsum(volume)
            cumulative_pv = np.cumsum(typical_price * volume)

            vwap = cumulative_pv / cumulative_volume
            return vwap
        except Exception as e:
            logger.error(f"Error calculating VWAP: {e}")
            return np.full(len(close), np.nan)

    @staticmethod
    def calculate_ichimoku(high: np.array, low: np.array, close: np.array) -> Dict[str, np.array]:
        """Ichimoku Cloud with error handling using pandas_ta"""
        # Refactored to use pandas_ta.ichimoku for standard calculation.
        # Original code used talib.SMA which is non-standard for Ichimoku.
        try:
            ichimoku_df = ta.ichimoku(pd.Series(high), pd.Series(low), pd.Series(close))

            # Extract relevant columns from pandas_ta output. Column names are dynamic.
            tenkan_col = ichimoku_df.columns[0] # Usually 'tenkan_sen' or similar based on parameters
            kijun_col = ichimoku_df.columns[1] # Usually 'kijun_sen' or similar
            spana_col = ichimoku_df.columns[2] # Usually 'senkou_span_a' or similar
            spanb_col = ichimoku_df.columns[3] # Usually 'senkou_span_b' or similar
            chikou_col = ichimoku_df.columns[4] # Usually 'chikou_span' or similar

            return {
                'tenkan_sen': ichimoku_df[tenkan_col].values,
                'kijun_sen': ichimoku_df[kijun_col].values,
                'senkou_span_a': ichimoku_df[spana_col].values,
                'senkou_span_b': ichimoku_df[spanb_col].values,
                'chikou_span': ichimoku_df[chikou_col].values
            }
        except Exception as e:
            logger.error(f"Error calculating Ichimoku: {e}")
            nan_array = np.full(len(close), np.nan)
            return {key: nan_array for key in ['tenkan_sen', 'kijun_sen', 'senkou_span_a', 'senkou_span_b', 'chikou_span']}

class BaseStrategy(ABC):
    """Abstract base class for trading strategies"""

    def __init__(self, name: str):
        self.name = name
        self.indicators = AdvancedTechnicalIndicators()

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame, symbol: str) -> TradeSignal:
        """Generate trading signals"""
        pass

    def get_required_data_points(self) -> int:
        """Get minimum data points required for strategy"""
        return 50

class MomentumStrategy(BaseStrategy):
    """Enhanced Momentum Strategy"""

    def __init__(self):
        super().__init__("Momentum")
        self.min_confidence = 0.6

    def generate_signals(self, data: pd.DataFrame, symbol: str) -> TradeSignal:
        """Generate momentum-based signals"""
        if len(data) < 100:
            return TradeSignal(symbol, 'neutral', 0.0, self.name, data.index[-1], 0.0, 0.0, 0.0)

        close = data['close'].values
        high = data['high'].values
        low = data['low'].values

        # Calculate indicators
        ema_9 = self.indicators.calculate_ema(close, 9)
        ema_21 = self.indicators.calculate_ema(close, 21)
        ema_50 = self.indicators.calculate_ema(close, 50)
        rsi = self.indicators.calculate_rsi(close, 14)
        macd, macd_signal, macd_hist = self.indicators.calculate_macd(close)
        adx = self.indicators.calculate_adx(high, low, close, 14)
        supertrend, supertrend_dir = self.indicators.calculate_supertrend(high, low, close)

        # Get current values
        current_price = close[-1]
        current_ema_9 = ema_9[-1]
        current_ema_21 = ema_21[-1]
        current_ema_50 = ema_50[-1]
        current_rsi = rsi[-1]
        current_macd = macd[-1]
        current_macd_signal = macd_signal[-1]
        current_supertrend = supertrend[-1]
        current_adx = adx[-1]

        # Momentum score calculation
        momentum_score = 0.0
        factors = []

        # EMA alignment
        if not np.isnan(current_ema_9) and not np.isnan(current_ema_21) and not np.isnan(current_ema_50):
            if current_ema_9 > current_ema_21 > current_ema_50:
                momentum_score += 0.25
                factors.append("Bullish EMA alignment")
            elif current_ema_9 < current_ema_21 < current_ema_50:
                momentum_score -= 0.25
                factors.append("Bearish EMA alignment")

        # MACD
        if not np.isnan(current_macd) and not np.isnan(current_macd_signal):
            if current_macd > current_macd_signal and current_macd > 0:
                momentum_score += 0.25
                factors.append("Bullish MACD")
            elif current_macd < current_macd_signal and current_macd < 0:
                momentum_score -= 0.25
                factors.append("Bearish MACD")

        # Super Trend direction (1 for up, -1 for down in this custom logic)
        if not np.isnan(current_supertrend):
            if supertrend_dir[-1] == 1:
                momentum_score += 0.2
                factors.append("Super Trend bullish")
            elif supertrend_dir[-1] == -1:
                momentum_score -= 0.2
                factors.append("Super Trend bearish")

        # ADX (trend strength)
        if not np.isnan(current_adx):
            if current_adx > 25:
                momentum_score *= 1.2  # Boost signal strength
                factors.append(f"Strong trend (ADX: {current_adx:.1f})")

        # RSI filter (avoid overbought/oversold)
        if not np.isnan(current_rsi):
            if current_rsi > 70:
                momentum_score *= 0.8  # Reduce signal strength
                factors.append("RSI overbought")
            elif current_rsi < 30:
                momentum_score *= 0.8  # Reduce signal strength
                factors.append("RSI oversold")

        # Determine signal
        confidence = abs(momentum_score)

        if confidence >= self.min_confidence:
            if momentum_score > 0:
                side = 'long'
                stop_loss = current_price * 0.98  # 2% stop loss
                take_profit = current_price * 1.06  # 6% take profit
            else:
                side = 'short'
                stop_loss = current_price * 1.02  # 2% stop loss
                take_profit = current_price * 0.94  # 6% take profit
        else:
            side = 'neutral'
            stop_loss = 0.0
            take_profit = 0.0

        return TradeSignal(
            symbol=symbol,
            side=side,
            confidence=confidence,
            strategy=self.name,
            timestamp=data.index[-1],
            price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

class MeanReversionStrategy(BaseStrategy):
    """Enhanced Mean Reversion Strategy"""

    def __init__(self):
        super().__init__("MeanReversion")
        self.min_confidence = 0.65

    def generate_signals(self, data: pd.DataFrame, symbol: str) -> TradeSignal:
        """Generate mean reversion signals"""
        if len(data) < 100:
            return TradeSignal(symbol, 'neutral', 0.0, self.name, data.index[-1], 0.0, 0.0, 0.0)

        close = data['close'].values

        # Calculate indicators
        rsi = self.indicators.calculate_rsi(close, 14)
        bb_upper, bb_middle, bb_lower = self.indicators.calculate_bollinger_bands(close, 20, 2)
        williams_r = self.indicators.calculate_williams_r(data['high'].values, data['low'].values, close)
        cci = self.indicators.calculate_cci(data['high'].values, data['low'].values, close)

        # Get current values
        current_price = close[-1]
        current_rsi = rsi[-1]
        current_bb_upper = bb_upper[-1]
        current_bb_lower = bb_lower[-1]
        current_bb_middle = bb_middle[-1]
        current_williams_r = williams_r[-1]
        current_cci = cci[-1]

        # Mean reversion score calculation
        reversion_score = 0.0
        factors = []

        # Bollinger Bands
        if not np.isnan(current_bb_upper) and not np.isnan(current_bb_lower):
            bb_position = (current_price - current_bb_lower) / (current_bb_upper - current_bb_lower)
            if bb_position < 0.1:  # Near lower band
                reversion_score += 0.3
                factors.append("Price near lower BB")
            elif bb_position > 0.9:  # Near upper band
                reversion_score -= 0.3
                factors.append("Price near upper BB")

        # RSI
        if not np.isnan(current_rsi):
            if current_rsi < 30:
                reversion_score += 0.25
                factors.append(f"RSI oversold ({current_rsi:.1f})")
            elif current_rsi > 70:
                reversion_score -= 0.25
                factors.append(f"RSI overbought ({current_rsi:.1f})")

        # Williams %R
        if not np.isnan(current_williams_r):
            if current_williams_r < -80:
                reversion_score += 0.2
                factors.append("Williams %R oversold")
            elif current_williams_r > -20:
                reversion_score -= 0.2
                factors.append("Williams %R overbought")

        # CCI
        if not np.isnan(current_cci):
            if current_cci < -100:
                reversion_score += 0.15
                factors.append("CCI oversold")
            elif current_cci > 100:
                reversion_score -= 0.15
                factors.append("CCI overbought")

        # Determine signal
        confidence = abs(reversion_score)

        if confidence >= self.min_confidence:
            if reversion_score > 0:
                side = 'long'
                stop_loss = current_price * 0.97  # 3% stop loss
                take_profit = current_bb_middle  # Middle band target
            else:
                side = 'short'
                stop_loss = current_price * 1.03  # 3% stop loss
                take_profit = current_bb_middle  # Middle band target
        else:
            side = 'neutral'
            stop_loss = 0.0
            take_profit = 0.0

        return TradeSignal(
            symbol=symbol,
            side=side,
            confidence=confidence,
            strategy=self.name,
            timestamp=data.index[-1],
            price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

class BreakoutStrategy(BaseStrategy):
    """Enhanced Breakout Strategy"""

    def __init__(self):
        super().__init__("Breakout")
        self.min_confidence = 0.7
        self.lookback_period = 20

    def generate_signals(self, data: pd.DataFrame, symbol: str) -> TradeSignal:
        """Generate breakout signals"""
        if len(data) < 50:
            return TradeSignal(symbol, 'neutral', 0.0, self.name, data.index[-1], 0.0, 0.0, 0.0)

        close = data['close'].values
        high = data['high'].values
        low = data['low'].values

        # Calculate indicators
        adx = self.indicators.calculate_adx(high, low, close, 14)
        volume = data['volume'].values

        # Get current values
        current_price = close[-1]
        current_adx = adx[-1]
        current_volume = volume[-1]

        # Calculate breakout levels
        lookback_high = np.max(high[-self.lookback_period:])
        lookback_low = np.min(low[-self.lookback_period:])
        recent_volume_avg = np.mean(volume[-20:])

        # Breakout score calculation
        breakout_score = 0.0
        factors = []

        # Price near resistance
        resistance_distance = (lookback_high - current_price) / current_price
        if resistance_distance < 0.02:  # Within 2% of resistance
            breakout_score += 0.3
            factors.append("Near resistance level")

        # Price near support
        support_distance = (current_price - lookback_low) / current_price
        if support_distance < 0.02:  # Within 2% of support
            breakout_score -= 0.3
            factors.append("Near support level")

        # Volume confirmation
        if current_volume > recent_volume_avg * 1.5:
            breakout_score *= 1.3  # Boost signal with volume
            factors.append("Volume confirmation")

        # ADX strength
        if not np.isnan(current_adx) and current_adx > 25:
            breakout_score *= 1.2
            factors.append(f"Strong trend (ADX: {current_adx:.1f})")

        # Determine signal
        confidence = abs(breakout_score)

        if confidence >= self.min_confidence:
            if breakout_score > 0:
                side = 'long'
                stop_loss = lookback_low * 0.98  # Below support
                take_profit = lookback_high + (lookback_high - lookback_low) * 1.5  # Extended target
            else:
                side = 'short'
                stop_loss = lookback_high * 1.02  # Above resistance
                take_profit = lookback_low - (lookback_high - lookback_low) * 1.5  # Extended target
        else:
            side = 'neutral'
            stop_loss = 0.0
            take_profit = 0.0

        return TradeSignal(
            symbol=symbol,
            side=side,
            confidence=confidence,
            strategy=self.name,
            timestamp=data.index[-1],
            price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

class AIAdaptiveStrategy:
    """AI-powered adaptive strategy that learns from market conditions"""

    def __init__(self):
        self.strategies = {
            'Momentum': MomentumStrategy(),
            'MeanReversion': MeanReversionStrategy(),
            'Breakout': BreakoutStrategy()
        }
        self.performance_history = {}
        self.market_regimes = ['trending_up', 'trending_down', 'ranging', 'volatile']
        self.current_regime = 2  # Default to ranging
        self.regime_weights = {
            'trending_up': {'Momentum': 0.5, 'MeanReversion': 0.2, 'Breakout': 0.3},
            'trending_down': {'Momentum': 0.4, 'MeanReversion': 0.3, 'Breakout': 0.3},
            'ranging': {'Momentum': 0.2, 'MeanReversion': 0.6, 'Breakout': 0.2},
            'volatile': {'Momentum': 0.3, 'MeanReversion': 0.2, 'Breakout': 0.5}
        }

    def analyze_market_regime(self, data: pd.DataFrame) -> int:
        """Analyze current market regime using multiple indicators"""
        if len(data) < 50:
            return self.current_regime

        close = data['close'].values
        high = data['high'].values
        low = data['low'].values

        # Calculate regime indicators
        ema_20 = AdvancedTechnicalIndicators.calculate_ema(close, 20)
        ema_50 = AdvancedTechnicalIndicators.calculate_ema(close, 50)
        adx = AdvancedTechnicalIndicators.calculate_adx(high, low, close, 14)
        atr = AdvancedTechnicalIndicators.calculate_atr(high, low, close, 14)

        # Trend analysis
        trend_strength = np.nanmean(adx[-10:]) if not np.isnan(adx).all() else 20
        trend_direction = np.nanmean(ema_20[-10:] - ema_50[-10:]) if not np.isnan(ema_20).all() else 0                              
        # Volatility analysis
        volatility = np.std(close[-20:]) / np.mean(close[-20:]) if len(close) >= 20 else 0.02                                       
        # Range analysis
        recent_range = (np.max(close[-20:]) - np.min(close[-20:])) / np.mean(close[-20:]) if len(close) >= 20 else 0.05

        # Regime classification
        if trend_strength > 25 and trend_direction > 0:
            regime = 0  # trending_up
        elif trend_strength > 25 and trend_direction < 0:
            regime = 1  # trending_down
        elif volatility > 0.03 or recent_range > 0.05:
            regime = 3  # volatile
        else:
            regime = 2  # ranging
                                                                          self.current_regime = regime
        return regime

    def get_best_strategy(self, data: pd.DataFrame, symbol: str) -> TradeSignal:
        """Get the best strategy signal based on market regime"""
        # Analyze current regime
        regime = self.analyze_market_regime(data)
        regime_name = self.market_regimes[regime]

        # Get weights for current regime
        weights = self.regime_weights[regime_name]

        # Generate signals from all strategies
        signals = {}                                                      for strategy_name, strategy in self.strategies.items():
            try:
                signal = strategy.generate_signals(data, symbol)
                if signal.confidence > 0.5:  # Only consider signals with reasonable confidence
                    signals[strategy_name] = signal
            except Exception as e:
                logger.warning(f"Strategy {strategy_name} failed: {e}")

        # Select best signal based on regime weights and confidence
        best_signal = None
        best_score = 0

        for strategy_name, signal in signals.items():
            if strategy_name in weights:
                score = signal.confidence * weights[strategy_name]
                if score > best_score:
                    best_score = score
                    best_signal = signal

        # If no good signal found, return neutral
        if best_signal is None:
            return TradeSignal(symbol, 'neutral', 0.0, 'None', data.index[-1], 0.0, 0.0, 0.0)

        return best_signal

class AdvancedRiskManager:
    """Enhanced risk management with dynamic position sizing"""

    def __init__(self, config: Dict):
        self.max_daily_loss = config.get('max_daily_loss', 0.05)
        self.max_drawdown = config.get('max_drawdown', 0.10)
        self.position_size_percent = config.get('position_size_percent', 0.02)
        self.max_positions = config.get('max_positions', 3)

        self.daily_pnl = 0.0
        self.peak_balance = 0.0
        self.current_drawdown = 0.0
        self.daily_start_time = datetime.now().date()                     self.position_tracker = {}

    def reset_daily_stats(self):
        """Reset daily trading statistics"""
        current_date = datetime.now().date()                              if current_date != self.daily_start_time:
            self.daily_pnl = 0.0
            self.daily_start_time = current_date                  
    def calculate_position_size(self, balance: float, entry_price: float, stop_loss: float,
                              confidence: float = 1.0) -> float:          """Calculate position size based on risk management and confidence"""                                                               if stop_loss <= 0 or entry_price <= 0:
            return 0.0
                                                                          # Base risk amount                                                base_risk = balance * self.position_size_percent                                                                                    # Adjust risk based on signal confidence
        adjusted_risk = base_risk * confidence                                                                                              # Calculate price risk                                            price_risk = abs(entry_price - stop_loss)                         if price_risk == 0:
            return 0.0                                                                                                                      position_size = adjusted_risk / price_risk
                                                                          # Apply maximum position limit
        max_position_value = balance * 0.15  # Max 15% of balance per position
        max_size = max_position_value / entry_price               
        return min(position_size, max_size)                       
    def should_stop_trading(self) -> bool:
        """Check if trading should be stopped due to risk limits"""
        return (self.daily_pnl <= -self.max_daily_loss or
                self.current_drawdown >= self.max_drawdown)       
    def update_drawdown(self, current_balance: float):
        """Update current drawdown"""
        if current_balance > self.peak_balance:                               self.peak_balance = current_balance

        if self.peak_balance > 0:
            self.current_drawdown = (self.peak_balance - current_balance) / self.peak_balance

    def can_open_position(self) -> bool:
        """Check if new position can be opened"""
        return len(self.position_tracker) < self.max_positions

class EnhancedPositionManager:
    """Advanced position management with AI-powered trailing stops"""

    def __init__(self):                                                   self.positions = {}
        self.trailing_stops = {}

    def add_position(self, position: Position):
        """Add new position"""
        self.positions[position.symbol] = position

        # Initialize dynamic trailing stop
        if position.side == 'long':
            self.trailing_stops[position.symbol] = {
                'distance': position.entry_price * 0.015,  # 1.5% initial distance
                'activation': position.entry_price * 0.008,  # Activate at 0.8% profit
                'current_stop': position.stop_loss,                               'step_size': position.entry_price * 0.005,  # 0.5% step
                'max_trail': position.entry_price * 0.03   # Max 3% trail
            }
        else:
            self.trailing_stops[position.symbol] = {
                'distance': position.entry_price * 0.015,
                'activation': position.entry_price * 0.008,
                'current_stop': position.stop_loss,
                'step_size': position.entry_price * 0.005,
                'max_trail': position.entry_price * 0.03
            }

    def update_trailing_stop(self, symbol: str, current_price: float):
        """Update trailing stop with AI-like logic"""
        if symbol not in self.positions or symbol not in self.trailing_stops:
            return

        position = self.positions[symbol]
        trail = self.trailing_stops[symbol]

        # Calculate current profit
        if position.side == 'long':
            profit_pct = (current_price - position.entry_price) / position.entry_price
            trail_distance = trail['distance']
        else:
            profit_pct = (position.entry_price - current_price) / position.entry_price
            trail_distance = trail['distance']

        # Update maximum profit
        position.max_profit = max(position.max_profit, profit_pct)

        # Adjust trailing distance based on profit
        if profit_pct > 0.02:  # 2% profit
            trail['distance'] = min(trail['max_trail'], trail['distance'] * 0.9)  # Tighten trail

        # Update trailing stop if profit threshold met                    if profit_pct >= trail['activation']:
            if position.side == 'long':
                new_stop = current_price - trail['distance']
                if new_stop > trail['current_stop']:
                    trail['current_stop'] = new_stop                                  position.stop_loss = new_stop
            else:
                new_stop = current_price + trail['distance']                      if new_stop < trail['current_stop']:
                    trail['current_stop'] = new_stop                                  position.stop_loss = new_stop
                                                                      def should_close_position(self, symbol: str, current_price: float) -> Tuple[bool, str]:                                                 """Check if position should be closed"""
        if symbol not in self.positions:
            return False, ""                                                                                                                position = self.positions[symbol]                                                                                                   # Check stop loss
        if position.side == 'long' and current_price <= position.stop_loss:                                                                     return True, "Stop Loss Hit"                                  elif position.side == 'short' and current_price >= position.stop_loss:
            return True, "Stop Loss Hit"                                                                                                    # Check take profit
        if position.side == 'long' and current_price >= position.take_profit:
            return True, "Take Profit Hit"                                elif position.side == 'short' and current_price <= position.take_profit:                                                                return True, "Take Profit Hit"
                                                                          # Check for profit lock-in (50% of target reached)
        if position.side == 'long':
            profit_pct = (current_price - position.entry_price) / position.entry_price
            target_pct = (position.take_profit - position.entry_price) / position.entry_price
        else:
            profit_pct = (position.entry_price - current_price) / position.entry_price                                                          target_pct = (position.entry_price - position.take_profit) / position.entry_price

        # Only trigger profit lock-in if target_pct is positive and profit reached half target
        if target_pct > 0 and profit_pct >= target_pct * 0.5:
            return True, "Profit Lock-in Triggered"
                                                                          return False, ""

class EnhancedAlertSystem:
    """Multi-channel alert system with smart filtering"""
                                                                      def __init__(self, config: Dict):
        self.config = config                                              self.alert_history = []                                           self.alert_cooldown = {}                                  
    def send_alert(self, message: str, alert_type: str = "INFO", symbol: str = ""):
        """Send alert through configured channels with cooldown"""
        timestamp = datetime.now()                                
        # Check cooldown                                                  alert_key = f"{alert_type}_{symbol}"
        if alert_key in self.alert_cooldown:
            if timestamp - self.alert_cooldown[alert_key] < timedelta(minutes=5):
                return  # Skip alert due to cooldown

        # Add to cooldown
        self.alert_cooldown[alert_key] = timestamp

        formatted_message = f"[{timestamp.strftime('%Y-%m-%d %H:%M:%S')}] [{alert_type}] {message}"

        logger.info(f"ALERT: {formatted_message}")                
        # Send through configured channels
        self._send_telegram(formatted_message)
        self._send_discord(formatted_message)
        self._send_email(formatted_message)
        self._send_sms(formatted_message)

        # Store in history
        self.alert_history.append({
            'timestamp': timestamp,
            'type': alert_type,
            'message': message,
            'symbol': symbol                                              })

        # Keep only last 100 alerts
        if len(self.alert_history) > 100:                                     self.alert_history = self.alert_history[-100:]

    def _send_telegram(self, message: str):
        """Send Telegram message"""
        try:
            telegram_config = self.config.get('alerts', {}).get('telegram', {})
            if not telegram_config.get('enabled', False):
                return

            token = telegram_config.get('bot_token')
            chat_id = telegram_config.get('chat_id')

            if not token or not chat_id:
                return                                            
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = {'chat_id': chat_id, 'text': message}

            response = requests.post(url, data=data, timeout=10)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Telegram alert failed: {e}")

    def _send_discord(self, message: str):
        """Send Discord webhook"""
        try:
            discord_config = self.config.get('alerts', {}).get('discord', {})                                                                   if not discord_config.get('enabled', False):
                return

            webhook_url = discord_config.get('webhook_url')
            if not webhook_url:
                return

            data = {'content': message}

            response = requests.post(webhook_url, json=data, timeout=10)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Discord alert failed: {e}")

    def _send_email(self, message: str):
        """Send email alert"""
        try:
            email_config = self.config.get('alerts', {}).get('email', {})
            if not email_config.get('enabled', False):
                return

            import smtplib
            from email.mime.text import MIMEText

            smtp_server = email_config.get('smtp_server')
            smtp_port = email_config.get('smtp_port', 587)
            username = email_config.get('username')
            password = email_config.get('password')
            to_email = email_config.get('to_email')

            if not all([smtp_server, username, password, to_email]):
                return

            msg = MIMEText(message)
            msg['Subject'] = 'Enhanced WhaleBot Alert'
            msg['From'] = username
            msg['To'] = to_email

            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()                                                 server.login(username, password)
            server.send_message(msg)                                          server.quit()
        except Exception as e:
            logger.error(f"Email alert failed: {e}")              
    def _send_sms(self, message: str):                                    """Send SMS alert"""
        try:                                                                  sms_config = self.config.get('alerts', {}).get('sms', {})                                                                           if not sms_config.get('enabled', False):
                return                                            
            # Implement SMS service (Twilio, AWS SNS, etc.)                   logger.info(f"SMS would be sent: {message}")
        except Exception as e:                                                logger.error(f"SMS alert failed: {e}")

class EnhancedWhaleBot:
    """Next Generation Enhanced Whale Bot"""

    def __init__(self, config_file: str = "config.json"):                 """Initialize the enhanced trading bot"""
        self.config = self.load_config(config_file)               
        # Initialize components
        self.ws_client = None
        self.http_client = None
        self.ai_strategy = AIAdaptiveStrategy()
        self.risk_manager = AdvancedRiskManager(self.config)
        self.position_manager = EnhancedPositionManager()
        self.alert_system = EnhancedAlertSystem(self.config)

        # Trading state
        self.running = False
        self.symbols = self.config.get('symbols', ['BTCUSDT', 'ETHUSDT'])
        self.timeframes = self.config.get('timeframes', ['1m', '5m', '15m'])
        self.current_prices = {}                                  
        # Performance tracking                                            self.daily_stats = {
            'trades': 0,
            'wins': 0,                                                        'losses': 0,
            'total_pnl': 0.0,
            'win_rate': 0.0                                               }                                                         
        logger.info("Enhanced WhaleBot initialized successfully")                                                                       def load_config(self, config_file: str) -> Dict:
        """Load configuration with enhanced defaults"""
        default_config = {                                                    "api_key": "",
            "api_secret": "",
            "testnet": True,
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "timeframes": ["1m", "5m", "15m"],
            "max_daily_loss": 0.05,
            "max_drawdown": 0.10,
            "position_size_percent": 0.02,
            "max_positions": 3,
            "strategies": {
                "momentum": {"enabled": True, "weight": 0.4},
                "mean_reversion": {"enabled": True, "weight": 0.3},
                "breakout": {"enabled": True, "weight": 0.3}                  },
            "indicators": {
                "ema_periods": [9, 21, 50],                                       "rsi_period": 14,
                "bb_period": 20,
                "bb_std": 2.0,                                                    "adx_period": 14,
                "atr_period": 14
            },
            "alerts": {
                "telegram": {"enabled": False, "bot_token": "", "chat_id": ""},                                                                     "discord": {"enabled": False, "webhook_url": ""},
                "email": {"enabled": False, "smtp_server": "", "smtp_port": 587, "username": "", "password": "", "to_email": ""},
                "sms": {"enabled": False, "api_key": "", "phone_number": ""}
            }                                                             }                                                                                                                                   try:                                                                  with open(config_file, 'r') as f:                                     config = json.load(f)                                             # Merge with default config                                       for key, value in default_config.items():                             if key not in config:                                                 config[key] = value
                return config                                             except FileNotFoundError:
            logger.warning(f"Config file {config_file} not found, using defaults")                                                              return default_config
                                                                      def initialize_clients(self) -> bool:
        """Initialize API clients"""                                      try:
            self.http_client = HTTP(                                              testnet=self.config['testnet'],
                api_key=self.config['api_key'],                                   api_secret=self.config['api_secret']                          )                                                     
            logger.info("API clients initialized successfully")               return True
        except Exception as e:                                                logger.error(f"Failed to initialize API clients: {e}")
            return False                                          
    def start_websocket(self) -> bool:                                    """Start WebSocket connection for real-time data"""               try:                                                                  self.ws_client = WebSocket(                                           testnet=self.config['testnet'],
                api_key=self.config['api_key'],                                   api_secret=self.config['api_secret']
            )
                                                                              # Subscribe to market data for all symbols
            for symbol in self.symbols:
                self.ws_client.subscribe_public_trade(symbol, self.handle_trade_data)                                                               self.ws_client.subscribe_public_orderbook(symbol, self.handle_orderbook_data)                                                                                                                     logger.info("WebSocket connection started")                       return True
        except Exception as e:                                                logger.error(f"Failed to start WebSocket: {e}")                   return False                                                                                                                def handle_trade_data(self, data: Dict):                              """Handle real-time trade data"""
        try:                                                                  symbol = data.get('s')
            price = float(data.get('p', 0))
                                                                              if symbol in self.symbols:
                self.current_prices[symbol] = price               
                # Update position trailing stops                                  self.position_manager.update_trailing_stop(symbol, price)
                                                                                  # Check for position exits
                should_close, reason = self.position_manager.should_close_position(symbol, price)                                                   if should_close:
                    self.close_position(symbol, reason)                                                                                     except Exception as e:
            logger.error(f"Error handling trade data: {e}")                                                                             def handle_orderbook_data(self, data: Dict):
        """Handle orderbook data"""                                       # Process orderbook for additional analysis if needed
        pass

    def get_historical_data(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
        """Fetch historical market data with error handling"""
        try:
            interval_map = {
                '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30,
                '1h': 60, '2h': 120, '4h': 240, '6h': 360, '12h': 720, '1d': 1440
            }

            interval = interval_map.get(timeframe, 1)

            response = self.http_client.get_kline(                                category="linear",
                symbol=symbol,
                interval=interval,
                limit=limit,
                end_time=int(time.time() * 1000)
            )                                                     
            if response.get('retCode') == 0:
                klines = response.get('result', {}).get('list', [])

                if not klines:                                                        logger.warning(f"No data returned for {symbol} {timeframe}")                                                                        return pd.DataFrame()

                df = pd.DataFrame(klines, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'turnover', 'confirm', 'timestamp_ms'
                ])

                # Convert data types with error handling
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
                numeric_columns = ['open', 'high', 'low', 'close', 'volume', 'turnover']
                for col in numeric_columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

                # Remove rows with NaN values
                df = df.dropna()
                                                                                  df.set_index('timestamp', inplace=True)
                return df
            else:
                logger.error(f"Failed to get historical data: {response}")
                return pd.DataFrame()

        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol}: {e}")
            return pd.DataFrame()

    def execute_trade(self, signal: TradeSignal) -> bool:
        """Execute trading decision based on AI signal"""
        try:                                                                  if not self.risk_manager.can_open_position():
                self.alert_system.send_alert(f"Cannot open position for {signal.symbol}: Max positions reached", "WARNING")
                return False
                                                                              if self.risk_manager.should_stop_trading():
                self.alert_system.send_alert("Trading stopped due to risk limits", "WARNING")                                                       return False

            # Get current price and account info
            current_price = self.current_prices.get(signal.symbol)
            if not current_price:
                logger.error(f"No current price for {signal.symbol}")
                return False

            # Get account balance
            account_info = self.http_client.get_wallet_balance(accountType="UNIFIED")
            if account_info.get('retCode') != 0:
                logger.error("Failed to get account info")
                return False

            balance = 0.0
            for coin in account_info.get('result', {}).get('list', []):
                if coin.get('coin') == 'USDT':
                    balance = float(coin.get('walletBalance', 0))
                    break

            if balance <= 0:
                logger.error("Insufficient balance")
                return False                                      
            # Calculate position size
            size = self.risk_manager.calculate_position_size(                     balance, signal.price, signal.stop_loss, signal.confidence                                                                      )
                                                                              if size <= 0:
                logger.error("Invalid position size calculated")                  return False

            # Place order
            order_response = self.http_client.place_order(
                category="linear",
                symbol=signal.symbol,                                             side="Buy" if signal.side == 'long' else "Sell",                  orderType="Market",                                               qty=str(size),                                                    timeInForce="GoodTillCancel"                                  )                                                                                                                                   if order_response.get('retCode') == 0:                                # Create position                                                 position = Position(                                                  symbol=signal.symbol,                                             side=signal.side,                                                 size=size,                                                        entry_price=signal.price,                                         entry_time=datetime.now(),                                        stop_loss=signal.stop_loss,                                       take_profit=signal.take_profit,                                   strategy=signal.strategy                                      )                                                                                                                                   # Add to position manager                                         self.position_manager.add_position(position)                      self.risk_manager.position_tracker[signal.symbol] = position

                # Send alert
                self.alert_system.send_alert(
                    f"Trade executed: {signal.side.upper()} {signal.symbol} @ {signal.price:.4f} "
                    f"Size: {size:.4f} Strategy: {signal.strategy} Confidence: {signal.confidence:.2f}",
                    "TRADE",
                    signal.symbol
                )

                logger.info(f"Trade executed: {signal.side.upper()} {signal.symbol} @ {signal.price:.4f}")
                return True
            else:
                logger.error(f"Trade execution failed: {order_response}")
                return False

        except Exception as e:
            logger.error(f"Error executing trade: {e}")
            return False

    def close_position(self, symbol: str, reason: str) -> bool:           """Close existing position"""
        try:
            if symbol not in self.position_manager.positions:
                logger.warning(f"No position found for {symbol}")                 return False

            position = self.position_manager.positions[symbol]
            current_price = self.current_prices.get(symbol)       
            if not current_price:
                logger.error(f"No current price for {symbol}")
                return False
                                                                              # Calculate P&L
            if position.side == 'long':
                pnl = (current_price - position.entry_price) * position.size
            else:
                pnl = (position.entry_price - current_price) * position.size                                                        
            # Place close order
            close_response = self.http_client.place_order(
                category="linear",
                symbol=symbol,
                side="Sell" if position.side == 'long' else "Buy",
                orderType="Market",
                qty=str(position.size),
                timeInForce="GoodTillCancel"
            )                                                     
            if close_response.get('retCode') == 0:                                # Remove from position manager                                    del self.position_manager.positions[symbol]
                if symbol in self.position_manager.trailing_stops:
                    del self.position_manager.trailing_stops[symbol]
                if symbol in self.risk_manager.position_tracker:
                    del self.risk_manager.position_tracker[symbol]

                # Update statistics
                self.risk_manager.daily_pnl += pnl
                self.daily_stats['trades'] += 1
                if pnl > 0:                                                           self.daily_stats['wins'] += 1
                else:
                    self.daily_stats['losses'] += 1
                self.daily_stats['total_pnl'] += pnl              
                # Calculate win rate
                if self.daily_stats['trades'] > 0:
                    self.daily_stats['win_rate'] = self.daily_stats['wins'] / self.daily_stats['trades']
                                                                                  # Send alert
                self.alert_system.send_alert(                                         f"Position closed: {symbol} {reason} P&L: ${pnl:.2f}",                                                                              "CLOSE",
                    symbol                                                        )

                logger.info(f"Position closed: {symbol} {reason} P&L: ${pnl:.2f}")                                                                  return True
            else:
                logger.error(f"Failed to close position: {close_response}")
                return False

        except Exception as e:
            logger.error(f"Error closing position for {symbol}: {e}")
            return False                                          
    def run_strategy_cycle(self):                                         """Enhanced strategy execution cycle with AI adaptation"""
        try:                                                                  self.risk_manager.reset_daily_stats()
                                                                              for symbol in self.symbols:
                # Get multi-timeframe data                                        data_15m = self.get_historical_data(symbol, '15m', 200)                                                                             if data_15m.empty:
                    continue                                      
                # Get AI strategy signal                                          signal = self.ai_strategy.get_best_strategy(data_15m, symbol)                                                       
                # Execute trades based on signals
                if signal.side in ['long', 'short'] and symbol not in self.position_manager.positions:
                    if signal.confidence >= 0.6:  # Minimum confidence threshold
                        if self.execute_trade(signal):                                        logger.info(f"AI Signal executed: {signal.side} {symbol} ({signal.strategy})")                          
                # Update existing positions                                       if symbol in self.position_manager.positions:
                    current_price = self.current_prices.get(symbol)
                    if current_price:                                                     self.position_manager.update_trailing_stop(symbol, current_price)                                           
        except Exception as e:                                                logger.error(f"Error in strategy cycle: {e}")
                                                                      def start(self) -> bool:
        """Start the enhanced trading bot"""                              try:
            logger.info("Starting Enhanced WhaleBot...")          
            # Initialize clients                                              if not self.initialize_clients():
                return False                                      
            # Start WebSocket                                                 if not self.start_websocket():
                return False                                      
            self.running = True                                   
            # Main trading loop                                               while self.running:
                try:                                                                  self.run_strategy_cycle()
                                                                                      # Update account balance and drawdown
                    account_info = self.http_client.get_wallet_balance(accountType="UNIFIED")
                    if account_info.get('retCode') == 0:                                  for coin in account_info.get('result', {}).get('list', []):                                                                             if coin.get('coin') == 'USDT':
                                balance = float(coin.get('walletBalance', 0))
                                self.risk_manager.update_drawdown(balance)
                                break                             
                    # Log performance stats every hour                                if datetime.now().minute == 0:
                        logger.info(f"Daily Stats: {self.daily_stats}")
                        logger.info(f"Active Positions: {len(self.position_manager.positions)}")
                        logger.info(f"Current Regime: {self.ai_strategy.market_regimes[self.ai_strategy.current_regime]}")
                                                                                      time.sleep(60)  # Wait 1 minute between cycles
                                                                                  except KeyboardInterrupt:
                    logger.info("Received interrupt signal")                          break
                except Exception as e:                                                logger.error(f"Error in main loop: {e}")
                    time.sleep(60)                                
            return True                                           
        except Exception as e:                                                logger.error(f"Failed to start bot: {e}")
            return False                                          
        finally:                                                              self.stop()
                                                                      def stop(self):
        """Stop the trading bot"""                                        logger.info("Stopping Enhanced WhaleBot...")
        self.running = False                                      
        if self.ws_client:                                                    self.ws_client.exit()
                                                                          logger.info("Enhanced WhaleBot stopped")
                                                                      def get_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report"""                   return {
            'timestamp': datetime.now().isoformat(),                          'daily_stats': self.daily_stats.copy(),
            'active_positions': len(self.position_manager.positions),
            'current_regime': self.ai_strategy.market_regimes[self.ai_strategy.current_regime],
            'risk_metrics': {                                                     'daily_pnl': self.risk_manager.daily_pnl,
                'current_drawdown': self.risk_manager.current_drawdown,
                'max_positions': self.risk_manager.max_positions,                 'can_open_position': self.risk_manager.can_open_position(),                                                                         'should_stop_trading': self.risk_manager.should_stop_trading()                                                                  },
            'strategy_weights': self.ai_strategy.regime_weights[                  self.ai_strategy.market_regimes[self.ai_strategy.current_regime]                                                                ],
            'alert_summary': {                                                    'total_alerts': len(self.alert_system.alert_history),                                                                               'recent_alerts': self.alert_system.alert_history[-10:] if self.alert_system.alert_history else []                               }
        }                                                         
def main():                                                           """Main entry point for Enhanced WhaleBot"""
    try:                                                                  # Create and start the enhanced bot
        bot = EnhancedWhaleBot()                                  
        # Start the bot                                                   success = bot.start()
                                                                          if success:
            logger.info("Enhanced WhaleBot started successfully")         else:
            logger.error("Failed to start Enhanced WhaleBot")     
    except Exception as e:                                                logger.error(f"Fatal error: {e}")
                                                                      finally:
        # Cleanup                                                         if 'bot' in locals():
            bot.stop()                                            
if __name__ == "__main__":                                            main()