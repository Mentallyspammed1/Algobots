# default_strategy.py

import logging
from typing import Any

import pandas as pd
from strategy_interface import BaseStrategy, Signal


class DefaultStrategy(BaseStrategy):
    """A default trading strategy using a combination of EMA crossover, RSI, and MACD.
    Inherits from BaseStrategy.
    """

    def __init__(self, logger: logging.Logger, **kwargs):
        super().__init__("DefaultStrategy", logger, **kwargs)

        # Default indicator parameters (can be overridden via kwargs)
        self.ema_fast_period: int = kwargs.get('STRATEGY_EMA_FAST_PERIOD', 9)
        self.ema_slow_period: int = kwargs.get('STRATEGY_EMA_SLOW_PERIOD', 21)
        self.rsi_period: int = kwargs.get('STRATEGY_RSI_PERIOD', 14)
        self.rsi_oversold: float = kwargs.get('STRATEGY_RSI_OVERSOLD', 30)
        self.rsi_overbought: float = kwargs.get('STRATEGY_RSI_OVERBOUGHT', 70)
        self.macd_fast_period: int = kwargs.get('STRATEGY_MACD_FAST_PERIOD', 12)
        self.macd_slow_period: int = kwargs.get('STRATEGY_MACD_SLOW_PERIOD', 26)
        self.macd_signal_period: int = kwargs.get('STRATEGY_MACD_SIGNAL_PERIOD', 9)
        self.bb_period: int = kwargs.get('STRATEGY_BB_PERIOD', 20)
        self.bb_std: float = kwargs.get('STRATEGY_BB_STD', 2.0)
        self.atr_period: int = kwargs.get('STRATEGY_ATR_PERIOD', 14)
        self.adx_period: int = kwargs.get('STRATEGY_ADX_PERIOD', 14)

        # Signal aggregation thresholds
        self.buy_score_threshold: float = kwargs.get('STRATEGY_BUY_SCORE_THRESHOLD', 1.0)
        self.sell_score_threshold: float = kwargs.get('STRATEGY_SELL_SCORE_THRESHOLD', -1.0)

        self.logger.info(f"DefaultStrategy initialized with params: EMA({self.ema_fast_period},{self.ema_slow_period}), RSI({self.rsi_period}), MACD({self.macd_fast_period},{self.macd_slow_period},{self.macd_signal_period}), BB({self.bb_period},{self.bb_std}), ATR({self.atr_period}), ADX({self.adx_period})")


    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculates and adds all necessary technical indicators to the DataFrame.
        Uses pandas_ta for indicator calculations.
        """
        if df.empty:
            self.logger.warning("Empty DataFrame provided for indicator calculation.")
            return df

        # Ensure numeric types
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.dropna(subset=['close']).copy() # Drop NaNs introduced by to_numeric

        if df.empty:
            self.logger.warning("DataFrame became empty after dropping NaN 'close' values.")
            return df

        # EMA
        df.ta.ema(length=self.ema_fast_period, append=True, col_names=(f'EMA_{self.ema_fast_period}',))
        df.ta.ema(length=self.ema_slow_period, append=True, col_names=(f'EMA_{self.ema_slow_period}',))

        # RSI
        df.ta.rsi(length=self.rsi_period, append=True, col_names=(f'RSI_{self.rsi_period}',))

        # MACD
        df.ta.macd(fast=self.macd_fast_period, slow=self.macd_slow_period, signal=self.macd_signal_period, append=True)

        # Bollinger Bands
        df.ta.bbands(length=self.bb_period, std=self.bb_std, append=True)

        # ATR
        df.ta.atr(length=self.atr_period, append=True, col_names=(f'ATR_{self.atr_period}',))

        # ADX (for market conditions and strategy)
        df.ta.adx(length=self.adx_period, append=True)

        # Clean up columns for easier access (rename complex pandas_ta names)
        df.rename(columns={
            f'EMA_{self.ema_fast_period}': 'EMA_Fast',
            f'EMA_{self.ema_slow_period}': 'EMA_Slow',
            f'RSI_{self.rsi_period}': 'RSI',
            f'MACD_{self.macd_fast_period}_{self.macd_slow_period}_{self.macd_signal_period}': 'MACD_Line',
            f'MACDh_{self.macd_fast_period}_{self.macd_slow_period}_{self.macd_signal_period}': 'MACD_Hist',
            f'MACDs_{self.macd_fast_period}_{self.macd_slow_period}_{self.macd_signal_period}': 'MACD_Signal',
            f'BBL_{self.bb_period}_{self.bb_std}': 'BB_Lower',
            f'BBM_{self.bb_period}_{self.bb_std}': 'BB_Middle',
            f'BBU_{self.bb_period}_{self.bb_std}': 'BB_Upper',
            f'ATR_{self.atr_period}': 'ATR',
            f'ADX_{self.adx_period}': 'ADX',
            f'DMP_{self.adx_period}': 'PlusDI', # +DI
            f'DMN_{self.adx_period}': 'MinusDI' # -DI
        }, inplace=True)

        # Forward fill any remaining NaNs (e.g., at start of series for indicators)
        df.fillna(method='ffill', inplace=True)
        df.fillna(0, inplace=True) # Fill any remaining with 0

        self.logger.debug("Indicators calculated for DefaultStrategy.")
        return df

    def generate_signal(self, df: pd.DataFrame, current_market_price: float, market_conditions: dict[str, Any]) -> Signal:
        """Generates a trading signal based on calculated indicators and market conditions.
        
        Args:
            df: DataFrame containing OHLCV data and calculated indicators.
            current_market_price: The latest market price.
            market_conditions: Dictionary of current market conditions (e.g., 'trend', 'volatility').

        Returns:
            A Signal object (dict-like) indicating 'BUY', 'SELL', or 'HOLD', along with a score and reasons.
        """
        # Ensure sufficient data for indicator lookback periods
        min_data_points = max(self.ema_slow_period, self.rsi_period, self.macd_slow_period, self.bb_period, self.atr_period, self.adx_period) + 2
        if df.empty or len(df) < min_data_points:
            self.logger.warning("Insufficient data for indicators in DefaultStrategy, returning HOLD.")
            return Signal(type='HOLD', score=0, reasons=['Insufficient data for indicators'])

        latest = df.iloc[-1]
        previous = df.iloc[-2] # For crossover detection

        signal_score = 0.0
        reasons = []

        # --- Market Condition Adjustment (Dynamic Strategy Adaptation) ---
        # Adjust weights based on market conditions
        market_phase = market_conditions.get('market_phase', 'UNKNOWN')
        market_volatility = market_conditions.get('volatility', 'NORMAL')

        ema_weight = 1.0
        rsi_weight = 1.0
        macd_weight = 1.0
        bb_weight = 1.0

        if market_phase == 'RANGING':
            # In ranging markets, mean-reversion (BBands, RSI overbought/oversold) might work better
            bb_weight *= 1.5
            rsi_weight *= 1.2
            ema_weight *= 0.5 # EMAs can be choppy
            macd_weight *= 0.7 # MACD might give false signals
            reasons.append("Adjusting weights for RANGING market.")
        elif market_phase in ['TRENDING_UP', 'TRENDING_DOWN']:
            # In trending markets, trend-following (EMAs, MACD) might work better
            ema_weight *= 1.5
            macd_weight *= 1.2
            bb_weight *= 0.5 # BBands can be less reliable
            reasons.append(f"Adjusting weights for {market_phase} market.")

        if market_volatility == 'HIGH':
            # High volatility: signals might be more exaggerated, but also riskier.
            # Could require wider stops or stronger confirmation.
            # Here, we might demand stronger signals.
            signal_score_multiplier = 1.2
            reasons.append("High volatility detected, demanding stronger signals.")
        else:
            signal_score_multiplier = 1.0

        # --- Indicator-based Signal Scoring ---

        # 1. EMA Crossover
        if latest['EMA_Fast'] > latest['EMA_Slow'] and previous['EMA_Fast'] <= previous['EMA_Slow']:
            signal_score += ema_weight * 2.0 # Strong bullish cross
            reasons.append(f"EMA Bullish Crossover ({latest['EMA_Fast']:.2f} > {latest['EMA_Slow']:.2f})")
        elif latest['EMA_Fast'] < latest['EMA_Slow'] and previous['EMA_Fast'] >= previous['EMA_Slow']:
            signal_score -= ema_weight * 2.0 # Strong bearish cross
            reasons.append(f"EMA Bearish Crossover ({latest['EMA_Fast']:.2f} < {latest['EMA_Slow']:.2f})")
        elif latest['EMA_Fast'] > latest['EMA_Slow']:
            signal_score += ema_weight * 0.5 # Bullish trend continuation
            reasons.append(f"EMA Bullish Trend Continuation ({latest['EMA_Fast']:.2f} > {latest['EMA_Slow']:.2f})")
        elif latest['EMA_Fast'] < latest['EMA_Slow']:
            signal_score -= ema_weight * 0.5 # Bearish trend continuation
            reasons.append(f"EMA Bearish Trend Continuation ({latest['EMA_Fast']:.2f} < {latest['EMA_Slow']:.2f})")

        # 2. RSI Overbought/Oversold (Mean Reversion)
        if latest['RSI'] < self.rsi_oversold and previous['RSI'] >= self.rsi_oversold:
            signal_score += rsi_weight * 1.5 # RSI entering oversold
            reasons.append(f"RSI Entering Oversold ({latest['RSI']:.2f})")
        elif latest['RSI'] > self.rsi_overbought and previous['RSI'] <= self.rsi_overbought:
            signal_score -= rsi_weight * 1.5 # RSI entering overbought
            reasons.append(f"RSI Entering Overbought ({latest['RSI']:.2f})")

        # 3. MACD Crossover
        if latest['MACD_Line'] > latest['MACD_Signal'] and previous['MACD_Line'] <= previous['MACD_Signal']:
            signal_score += macd_weight * 1.5 # MACD bullish cross
            reasons.append("MACD Bullish Crossover")
        elif latest['MACD_Line'] < latest['MACD_Signal'] and previous['MACD_Line'] >= previous['MACD_Signal']:
            signal_score -= macd_weight * 1.5 # MACD bearish cross
            reasons.append("MACD Bearish Crossover")

        # 4. Bollinger Bands (Breakout / Mean Reversion)
        if current_market_price < latest['BB_Lower'] and previous['close'] >= previous['BB_Lower']:
            signal_score += bb_weight * 1.0 # Price breaking below lower band (oversold/potential bounce)
            reasons.append(f"Price Break Below BB_Lower ({current_market_price:.2f})")
        elif current_market_price > latest['BB_Upper'] and previous['close'] <= previous['BB_Upper']:
            signal_score -= bb_weight * 1.0 # Price breaking above upper band (overbought/potential drop)
            reasons.append(f"Price Break Above BB_Upper ({current_market_price:.2f})")
        elif current_market_price < latest['BB_Middle'] and latest['BB_Middle'] > previous['BB_Middle']: # Below middle, but middle band rising (weak bullish)
             signal_score += bb_weight * 0.2
             reasons.append("Price Below BB_Middle, Middle Rising")
        elif current_market_price > latest['BB_Middle'] and latest['BB_Middle'] < previous['BB_Middle']: # Above middle, but middle band falling (weak bearish)
             signal_score -= bb_weight * 0.2
             reasons.append("Price Above BB_Middle, Middle Falling")


        # Apply volatility multiplier
        signal_score *= signal_score_multiplier

        # --- Final Signal Decision ---
        if signal_score >= self.buy_score_threshold:
            signal_type = 'BUY'
        elif signal_score <= self.sell_score_threshold:
            signal_type = 'SELL'
        else:
            signal_type = 'HOLD'

        self.logger.debug(f"DefaultStrategy Score: {signal_score:.2f}, Type: {signal_type}, Reasons: {reasons}")
        return Signal(type=signal_type, score=signal_score, reasons=reasons)

    def get_indicator_values(self, df: pd.DataFrame) -> dict[str, float]:
        """Extracts the latest values of key indicators after calculation.
        These values are passed to other modules (e.g., TrailingStopManager).
        """
        if df.empty:
            return {}

        latest_row = df.iloc[-1]
        indicators = {}

        # Ensure indicator columns exist and are not NaN
        for col in [
            'close', 'open', 'high', 'low', 'volume', 'ATR', 'RSI',
            'MACD_Line', 'MACD_Hist', 'MACD_Signal',
            'BB_Lower', 'BB_Middle', 'BB_Upper', 'ADX', 'PlusDI', 'MinusDI' # Added ADX components
        ]:
            if col in latest_row and pd.notna(latest_row[col]):
                indicators[col] = float(latest_row[col])
            else:
                indicators[col] = 0.0 # Default if NaN or not present
        return indicators
