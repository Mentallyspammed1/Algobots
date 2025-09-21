import pandas as pd
import numpy as np
from ta.momentum import StochasticOscillator, RSIIndicator
from ta.trend import MACD, ADX, IchimokuIndicator, CCIIndicator, PSARIndicator, TRIXIndicator
from ta.volatility import BollingerBands, KeltnerChannel, DonchianChannel
from ta.volume import AccDistIndex, OnBalanceVolumeIndicator, ChaikinMoneyFlowIndicator, ForceIndexIndicator, VolumeWeightedAveragePrice
from ta.others import DailyReturnIndicator, CumulativeReturnIndicator

class EhlersFilter:
    def __init__(self, period=10, smoothing=5):
        self.period = period
        self.smoothing = smoothing

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        if 'close' not in df.columns:
            raise ValueError("DataFrame must contain a 'close' column for EhlersFilter.")
        if len(df) < self.period + self.smoothing:
            # Not enough data to calculate Ehlers Fisher
            df['eh_fisher'] = np.nan
            df['eh_fisher_signal'] = np.nan
            return df

        # Calculate typical price
        typical_price = (df['high'] + df['low'] + df['close']) / 3

        # Calculate highest high and lowest low over the period
        highest_high = typical_price.rolling(window=self.period).max()
        lowest_low = typical_price.rolling(window=self.period).min()

        # Calculate raw_fisher
        # Avoid division by zero if highest_high == lowest_low
        range_diff = highest_high - lowest_low
        raw_fisher = pd.Series(np.nan, index=df.index)
        valid_indices = range_diff != 0
        raw_fisher[valid_indices] = (typical_price[valid_indices] - lowest_low[valid_indices]) / range_diff[valid_indices]
        raw_fisher = 2 * (raw_fisher - 0.5) # Normalize to -1 to 1

        # Apply smoothing (e.g., EMA)
        alpha = 2 / (self.smoothing + 1)
        fisher = pd.Series(np.nan, index=df.index)
        prev_fisher = 0.0
        for i in range(len(raw_fisher)):
            if pd.isna(raw_fisher.iloc[i]):
                fisher.iloc[i] = np.nan
            else:
                fisher.iloc[i] = alpha * raw_fisher.iloc[i] + (1 - alpha) * prev_fisher
                prev_fisher = fisher.iloc[i]

        # Fisher Transform
        # Ensure values are within (-1, 1) for log calculation
        fisher = fisher.clip(lower=-0.999, upper=0.999)
        df['eh_fisher'] = 0.5 * np.log((1 + fisher) / (1 - fisher))
        df['eh_fisher_signal'] = df['eh_fisher'].shift(1) # Signal line is previous Fisher

        return df

class SuperTrend:
    def __init__(self, period=10, multiplier=3.0):
        self.period = period
        self.multiplier = multiplier

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        if not all(col in df.columns for col in ['high', 'low', 'close']):
            raise ValueError("DataFrame must contain 'high', 'low', 'close' columns for SuperTrend.")
        if len(df) < self.period:
            # Not enough data to calculate SuperTrend
            df['supertrend'] = np.nan
            df['supertrend_direction'] = np.nan
            return df

        # Calculate Average True Range (ATR)
        high_low = df['high'] - df['low']
        high_prev_close = np.abs(df['high'] - df['close'].shift())
        low_prev_close = np.abs(df['low'] - df['close'].shift())
        
        true_range = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
        atr = true_range.ewm(span=self.period, adjust=False).mean()

        # Calculate Basic Upper and Lower Bands
        basic_upper_band = ((df['high'] + df['low']) / 2) + (self.multiplier * atr)
        basic_lower_band = ((df['high'] + df['low']) / 2) - (self.multiplier * atr)

        # Initialize final upper and lower bands
        final_upper_band = pd.Series(np.nan, index=df.index)
        final_lower_band = pd.Series(np.nan, index=df.index)
        supertrend = pd.Series(np.nan, index=df.index)
        supertrend_direction = pd.Series(np.nan, index=df.index) # 1 for uptrend, -1 for downtrend

        for i in range(1, len(df)):
            if pd.isna(basic_upper_band.iloc[i]) or pd.isna(basic_lower_band.iloc[i]):
                continue

            if pd.isna(final_upper_band.iloc[i-1]): # First valid calculation
                final_upper_band.iloc[i] = basic_upper_band.iloc[i]
                final_lower_band.iloc[i] = basic_lower_band.iloc[i]
            else:
                if basic_upper_band.iloc[i] < final_upper_band.iloc[i-1] or df['close'].iloc[i-1] > final_upper_band.iloc[i-1]:
                    final_upper_band.iloc[i] = basic_upper_band.iloc[i]
                else:
                    final_upper_band.iloc[i] = final_upper_band.iloc[i-1]

                if basic_lower_band.iloc[i] > final_lower_band.iloc[i-1] or df['close'].iloc[i-1] < final_lower_band.iloc[i-1]:
                    final_lower_band.iloc[i] = basic_lower_band.iloc[i]
                else:
                    final_lower_band.iloc[i] = final_lower_band.iloc[i-1]

            if pd.isna(supertrend.iloc[i-1]): # First valid calculation
                if df['close'].iloc[i] > final_upper_band.iloc[i]:
                    supertrend.iloc[i] = final_lower_band.iloc[i]
                    supertrend_direction.iloc[i] = 1
                else:
                    supertrend.iloc[i] = final_upper_band.iloc[i]
                    supertrend_direction.iloc[i] = -1
            else:
                if supertrend_direction.iloc[i-1] == 1: # Previous was uptrend
                    if df['close'].iloc[i] < final_lower_band.iloc[i]:
                        supertrend.iloc[i] = final_upper_band.iloc[i]
                        supertrend_direction.iloc[i] = -1 # Downtrend
                    else:
                        supertrend.iloc[i] = final_lower_band.iloc[i]
                        supertrend_direction.iloc[i] = 1 # Uptrend
                else: # Previous was downtrend
                    if df['close'].iloc[i] > final_upper_band.iloc[i]:
                        supertrend.iloc[i] = final_lower_band.iloc[i]
                        supertrend_direction.iloc[i] = 1 # Uptrend
                    else:
                        supertrend.iloc[i] = final_upper_band.iloc[i]
                        supertrend_direction.iloc[i] = -1 # Downtrend

        df['supertrend'] = supertrend
        df['supertrend_direction'] = supertrend_direction
        return df