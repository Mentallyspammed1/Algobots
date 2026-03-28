import numpy as np
import pandas as pd
from typing import Tuple, Dict, Any, Union, List
from decimal import Decimal, getcontext, ROUND_HALF_UP

# Set precision for financial levels
getcontext().prec = 28
getcontext().rounding = ROUND_HALF_UP

class EhlersIndicators:
    """
    Implementation of John Ehlers' advanced technical indicators
    based on Digital Signal Processing (DSP) techniques.
    """

    @staticmethod
    def super_smoother(series: pd.Series, length: int) -> pd.Series:
        """
        Ehlers SuperSmoother Filter.
        Reduces noise with minimal lag.
        """
        a = np.exp(-np.pi * np.sqrt(2) / length)
        b = 2 * a * np.cos(np.sqrt(2) * np.pi / length)
        c2 = b
        c3 = -a * a
        c1 = 1 - c2 - c3

        ss = pd.Series(index=series.index, dtype=float)
        ss.iloc[0] = series.iloc[0]
        if len(series) > 1:
            ss.iloc[1] = series.iloc[1]

        for i in range(2, len(series)):
            ss.iloc[i] = c1 * (series.iloc[i] + series.iloc[i-1]) / 2 + c2 * ss.iloc[i-1] + c3 * ss.iloc[i-2]
        
        return ss

    @staticmethod
    def fisher_transform(series: pd.Series, length: int) -> Tuple[pd.Series, pd.Series]:
        """
        Ehlers Fisher Transform.
        Converts price into a Gaussian normal distribution.
        Returns (Fisher, Signal).
        """
        high = series.rolling(window=length).max()
        low = series.rolling(window=length).min()
        
        value = pd.Series(0.0, index=series.index)
        fisher = pd.Series(0.0, index=series.index)
        
        for i in range(1, len(series)):
            denom = high.iloc[i] - low.iloc[i]
            if denom > 0:
                v = 0.66 * ((series.iloc[i] - low.iloc[i]) / denom - 0.5) + 0.67 * value.iloc[i-1]
            else:
                v = 0
            
            v = max(min(v, 0.99), -0.99)
            value.iloc[i] = v
            fisher.iloc[i] = 0.5 * np.log((1 + v) / (1 - v)) + 0.5 * fisher.iloc[i-1]
            
        signal = fisher.shift(1).fillna(0)
        return fisher, signal

    @staticmethod
    def laguerre_rsi(series: pd.Series, gamma: float = 0.5) -> pd.Series:
        """
        Ehlers Laguerre RSI.
        Very responsive RSI with low lag.
        """
        l0 = np.zeros(len(series))
        l1 = np.zeros(len(series))
        l2 = np.zeros(len(series))
        l3 = np.zeros(len(series))
        lrsi = np.zeros(len(series))

        for i in range(1, len(series)):
            l0[i] = (1 - gamma) * series.iloc[i] + gamma * l0[i-1]
            l1[i] = -gamma * l0[i] + l0[i-1] + gamma * l1[i-1]
            l2[i] = -gamma * l1[i] + l1[i-1] + gamma * l2[i-1]
            l3[i] = -gamma * l2[i] + l2[i-1] + gamma * l3[i-1]

            cu = 0
            cd = 0
            if l0[i] >= l1[i]: cu += l0[i] - l1[i]
            else: cd += l1[i] - l0[i]
            if l1[i] >= l2[i]: cu += l1[i] - l2[i]
            else: cd += l2[i] - l1[i]
            if l2[i] >= l3[i]: cu += l2[i] - l3[i]
            else: cd += l3[i] - l2[i]

            if cu + cd != 0:
                lrsi[i] = cu / (cu + cd)
            else:
                lrsi[i] = 0
        
        return pd.Series(lrsi, index=series.index)

    @staticmethod
    def center_of_gravity(series: pd.Series, length: int) -> Tuple[pd.Series, pd.Series]:
        """
        Ehlers Center of Gravity Oscillator.
        Identifies major turning points with zero lag.
        """
        num = pd.Series(0.0, index=series.index)
        den = pd.Series(0.0, index=series.index)
        
        for i in range(length):
            num += (i + 1) * series.shift(i)
            den += series.shift(i).replace(0, np.nan)
        
        cog = -num / den
        cog = cog.fillna(0)
        signal = cog.shift(1).fillna(0)
        return cog, signal

    @staticmethod
    def instant_trendline(series: pd.Series, alpha: float = 0.07) -> pd.Series:
        """
        Ehlers Instantaneous Trendline.
        Responsive trendline that separates cycle from trend.
        """
        itrend = pd.Series(0.0, index=series.index)
        itrend.iloc[0] = series.iloc[0]
        if len(series) > 1: itrend.iloc[1] = series.iloc[1]
        if len(series) > 2: itrend.iloc[2] = series.iloc[2]

        for i in range(7, len(series)):
            price = (series.iloc[i] + 2*series.iloc[i-1] + 2*series.iloc[i-2] + series.iloc[i-3]) / 6
            itrend.iloc[i] = (alpha - (alpha**2)/4) * price + \
                            0.5 * (alpha**2) * series.iloc[i-1] - \
                            (alpha - 0.75*(alpha**2)) * series.iloc[i-2] + \
                            2*(1 - alpha) * itrend.iloc[i-1] - \
                            ((1 - alpha)**2) * itrend.iloc[i-2]
        
        return itrend

    @staticmethod
    def correlation_trend_indicator(series: pd.Series, length: int = 20) -> pd.Series:
        """
        Ehlers Correlation Trend Indicator (CTI).
        Measures correlation to an ideal trend.
        """
        def spearman_corr(x):
            if len(x) < length: return 0.0
            y = np.arange(length, 0, -1)
            return np.corrcoef(x, y)[0, 1]

        return series.rolling(window=length).apply(spearman_corr, raw=True).fillna(0)

    @staticmethod
    def roofing_filter(series: pd.Series, low_cutoff: int = 10, high_cutoff: int = 48) -> pd.Series:
        """
        Ehlers Roofing Filter.
        Acts as a band-pass filter to remove noise and cycle drift.
        """
        alpha = (np.cos(2 * np.pi / high_cutoff) + np.sin(2 * np.pi / high_cutoff) - 1) / np.cos(2 * np.pi / high_cutoff)
        hp = pd.Series(0.0, index=series.index)
        for i in range(2, len(series)):
            hp.iloc[i] = (1 - alpha/2)**2 * (series.iloc[i] - 2*series.iloc[i-1] + series.iloc[i-2]) + \
                         2*(1 - alpha)*hp.iloc[i-1] - (1 - alpha)**2*hp.iloc[i-2]
        
        return EhlersIndicators.super_smoother(hp, low_cutoff)

    @staticmethod
    def ehlers_stoch_rsi(series: pd.Series, length: int = 14) -> Tuple[pd.Series, pd.Series]:
        """
        Ehlers Stochastic RSI using Roofing Filter.
        """
        filt = EhlersIndicators.roofing_filter(series, 10, 48)
        max_f = filt.rolling(window=length).max()
        min_f = filt.rolling(window=length).min()
        
        diff = max_f - min_f
        stoch = (filt - min_f) / diff.replace(0, np.nan)
        stoch = stoch.fillna(0)
        
        k = EhlersIndicators.super_smoother(stoch, 3)
        d = k.shift(1).fillna(0)
        return k, d

    @staticmethod
    def cyber_cycle(series: pd.Series, alpha: float = 0.07) -> Tuple[pd.Series, pd.Series]:
        """
        Ehlers Cyber Cycle.
        A responsive cycle oscillator.
        """
        smooth = (series + 2*series.shift(1).fillna(series) + 2*series.shift(2).fillna(series) + series.shift(3).fillna(series)) / 6
        cycle = pd.Series(0.0, index=series.index)
        for i in range(2, len(series)):
            cycle.iloc[i] = (1 - 0.5*alpha)**2 * (smooth.iloc[i] - 2*smooth.iloc[i-1] + smooth.iloc[i-2]) + \
                            2*(1 - alpha)*cycle.iloc[i-1] - (1 - alpha)**2*cycle.iloc[i-2]
        
        trigger = cycle.shift(1).fillna(0)
        return cycle, trigger

    @staticmethod
    def mesa_sine_wave(series: pd.Series) -> Tuple[pd.Series, pd.Series]:
        """
        Ehlers MESA Sine Wave.
        Identifies cyclical turning points and trend modes.
        """
        hp = EhlersIndicators.roofing_filter(series, 10, 48)
        period = 20
        q1 = hp.diff().rolling(window=period).mean()
        i1 = hp.rolling(window=period).mean()
        
        phase = np.arctan2(q1.fillna(0), i1.fillna(0))
        sine = np.sin(phase)
        leadsine = np.sin(phase + np.pi/4)
        
        return pd.Series(sine, index=series.index), pd.Series(leadsine, index=series.index)

class LevelsCalculator:
    """Calculates Support, Resistance, Fibonacci, and Pivot levels with high precision."""

    @staticmethod
    def pivot_points(high: float, low: float, close: float) -> Dict[str, float]:
        """Calculates standard, Camarilla, and Woodie Pivot Points."""
        levels = {}
        # Standard
        pp = (high + low + close) / 3
        levels["PP"] = pp
        levels["R1"] = (2 * pp) - low
        levels["S1"] = (2 * pp) - high
        levels["R2"] = pp + (high - low)
        levels["S2"] = pp - (high - low)
        levels["R3"] = high + 2 * (pp - low)
        levels["S3"] = low - 2 * (high - pp)

        # Camarilla
        diff = high - low
        levels["Cam R4"] = close + diff * 1.1 / 2
        levels["Cam R3"] = close + diff * 1.1 / 4
        levels["Cam R1"] = close + diff * 1.1 / 12
        levels["Cam S1"] = close - diff * 1.1 / 12
        levels["Cam S3"] = close - diff * 1.1 / 4
        levels["Cam S4"] = close - diff * 1.1 / 2

        # Woodie
        wpp = (high + low + 2 * close) / 4
        levels["Woodie PP"] = wpp
        levels["Woodie R1"] = (2 * wpp) - low
        levels["Woodie S1"] = (2 * wpp) - high
        levels["Woodie R2"] = wpp + (high - low)
        levels["Woodie S2"] = wpp - (high - low)
        
        return levels

    @staticmethod
    def fibonacci_levels(high: float, low: float) -> Dict[str, float]:
        """Calculates Fibonacci retracement levels."""
        diff = high - low
        return {
            "Fib 0.0": high,
            "Fib 0.236": high - diff * 0.236,
            "Fib 0.382": high - diff * 0.382,
            "Fib 0.5": high - diff * 0.5,
            "Fib 0.618": high - diff * 0.618,
            "Fib 0.786": high - diff * 0.786,
            "Fib 1.0": low,
            "Fib 1.618": high + diff * 0.618,
            "Fib -0.618": low - diff * 0.618
        }

    @staticmethod
    def find_nearest_5(current_price: float, levels: Dict[str, float]) -> List[Tuple[str, float]]:
        """
        Wizard Upgrade: Vectorized level distance calculation.
        Finds the 5 levels closest to the current price.
        """
        # Convert dictionary to lists for vectorization
        names = list(levels.keys())
        values = np.array(list(levels.values()), dtype=float)
        
        # Mask out invalid values
        mask = np.isfinite(values)
        valid_names = [names[i] for i in range(len(names)) if mask[i]]
        valid_values = values[mask]
        
        if len(valid_values) == 0:
            return []
            
        # Calculate absolute distances vectorized
        distances = np.abs(valid_values - current_price)
        
        # Get indices of 5 smallest distances
        nearest_indices = np.argsort(distances)[:5]
        
        return [(valid_names[i], valid_values[i]) for i in nearest_indices]

class VolumeProfiler:
    """Analyzes volume-based support and resistance."""

    @staticmethod
    def volume_at_price(df: pd.DataFrame, bins: int = 20) -> List[Dict[str, Any]]:
        """
        Calculates volume profile (Volume at Price).
        Identifies high volume nodes (HVN) as potential support/resistance.
        """
        if df.empty: return []
        
        price_min = df['low'].min()
        price_max = df['high'].max()
        if price_min == price_max: return []
        
        bin_size = (price_max - price_min) / bins
        profile = []
        
        for i in range(bins):
            b_min = price_min + i * bin_size
            b_max = b_min + bin_size
            # Volume in this price bin
            v = df[(df['close'] >= b_min) & (df['close'] < b_max)]['volume'].sum()
            profile.append({"price": (b_min + b_max)/2, "volume": v})
            
        # Sort by volume to find HVNs
        return sorted(profile, key=lambda x: x['volume'], reverse=True)

    @staticmethod
    def find_nearest_5(current_price: float, profile: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Finds the 5 high volume nodes closest to the current price."""
        if not profile: return []
        # Sort by absolute distance from current price
        sorted_nodes = sorted(profile, key=lambda x: abs(x['price'] - current_price))
        return sorted_nodes[:5]

class OrderBlockCalculator:
    """Identifies Bullish and Bearish Order Blocks (Supply/Demand zones)."""

    @staticmethod
    def identify_blocks(df: pd.DataFrame, atr_mult: float = 2.0) -> List[Dict[str, Any]]:
        """
        Identifies order blocks based on price imbalance.
        An imbalance is a candle with a body much larger than the recent ATR.
        """
        if len(df) < 20: return []
        
        highs = df['high']
        lows = df['low']
        opens = df['open']
        closes = df['close']
        
        # Calculate ATR for imbalance threshold
        tr = pd.concat([highs - lows, abs(highs - closes.shift(1)), abs(lows - closes.shift(1))], axis=1).max(axis=1)
        atr = tr.rolling(window=14).mean()
        
        blocks = []
        
        for i in range(1, len(df) - 1):
            body_size = abs(closes.iloc[i] - opens.iloc[i])
            prev_atr = atr.iloc[i-1]
            
            # Check for imbalance (large candle)
            if pd.isna(prev_atr) or body_size < prev_atr * atr_mult:
                continue
                
            # Previous candle is the potential order block
            block_candle = {
                "type": "Bullish" if closes.iloc[i] > opens.iloc[i] else "Bearish",
                "top": highs.iloc[i-1],
                "bottom": lows.iloc[i-1],
                "price": (highs.iloc[i-1] + lows.iloc[i-1]) / 2,
                "timestamp": df['timestamp'].iloc[i-1] if 'timestamp' in df.columns else i-1
            }
            blocks.append(block_candle)
            
        return blocks

    @staticmethod
    def find_nearest_5(current_price: float, blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Finds the 5 order blocks closest to the current price."""
        if not blocks: return []
        # Sort by absolute distance from current price to the center of the block
        sorted_blocks = sorted(blocks, key=lambda x: abs(x['price'] - current_price))
        return sorted_blocks[:5]

class MomentumIndicators:
    """Standard and advanced momentum indicators."""

    @staticmethod
    def wma(series: pd.Series, period: int) -> pd.Series:
        """Weighted Moving Average."""
        weights = np.arange(1, period + 1)
        return series.rolling(period).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)

    @staticmethod
    def hma(series: pd.Series, period: int) -> pd.Series:
        """Hull Moving Average."""
        half_length = int(period / 2)
        sqrt_length = int(np.sqrt(period))
        
        wma_half = MomentumIndicators.wma(series, half_length)
        wma_full = MomentumIndicators.wma(series, period)
        
        diff = 2 * wma_half - wma_full
        return MomentumIndicators.wma(diff, sqrt_length)

    @staticmethod
    def vwap(df: pd.DataFrame) -> pd.Series:
        """Volume Weighted Average Price."""
        v = df['volume']
        p = (df['high'] + df['low'] + df['close']) / 3
        return (p * v).cumsum() / v.cumsum()

    @staticmethod
    def sma(series: pd.Series, period: int) -> pd.Series:
        """Simple Moving Average."""
        return series.rolling(window=period).mean()

    @staticmethod
    def ema(series: pd.Series, period: int) -> pd.Series:
        """Exponential Moving Average."""
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def rsi(series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss.replace(0, np.nan)
        return (100 - (100 / (1 + rs))).fillna(50)

    @staticmethod
    def mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int = 14) -> pd.Series:
        tp = (high + low + close) / 3
        rmf = tp * volume
        mf_dir = np.where(tp > tp.shift(1), 1, -1)
        pmf = (rmf * (mf_dir == 1)).rolling(window=period).sum()
        nmf = (rmf * (mf_dir == -1)).rolling(window=period).sum()
        mfr = pmf / nmf.replace(0, np.nan)
        return (100 - (100 / (1 + mfr))).fillna(0)

    @staticmethod
    def stoch_rsi(series: pd.Series, period: int = 14, k: int = 3, d: int = 3) -> Tuple[pd.Series, pd.Series]:
        rsi_val = MomentumIndicators.rsi(series, period)
        diff = rsi_val.rolling(window=period).max() - rsi_val.rolling(window=period).min()
        stoch_rsi = (rsi_val - rsi_val.rolling(window=period).min()) / diff.replace(0, np.nan)
        stoch_rsi = stoch_rsi.fillna(0)
        fast_k = stoch_rsi.rolling(window=k).mean() * 100
        slow_d = fast_k.rolling(window=d).mean()
        return fast_k, slow_d

    @staticmethod
    def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
        fast_ema = series.ewm(span=fast, adjust=False).mean()
        slow_ema = series.ewm(span=slow, adjust=False).mean()
        macd_line = fast_ema - slow_ema
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        hist = macd_line - signal_line
        return macd_line, signal_line, hist

    @staticmethod
    def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        tr = pd.concat([high - low, abs(high - close.shift(1)), abs(low - close.shift(1))], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean().replace(0, np.nan)
        
        plus_dm = high.diff().where((high.diff() > low.diff().abs()) & (high.diff() > 0), 0)
        minus_dm = low.diff().abs().where((low.diff().abs() > high.diff()) & (low.diff().abs() > 0), 0)
        
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
        
        total = (plus_di + minus_di).replace(0, np.nan)
        dx = 100 * (abs(plus_di - minus_di) / total)
        return dx.rolling(window=period).mean().fillna(0)

    @staticmethod
    def fve(close: pd.Series, volume: pd.Series, period: int = 22, factor: float = 0.1) -> pd.Series:
        """
        Katsanos Finite Volume Element (FVE).
        Measures money flow with volatility-adjusted volume filtering.
        """
        tp = (close + close.shift(1).fillna(close) + close.shift(2).fillna(close)) / 3
        # Intra-day intensity
        cutoff = factor * close.rolling(period).std().fillna(0)
        
        mf = pd.Series(0.0, index=close.index)
        for i in range(1, len(close)):
            change = close.iloc[i] - close.iloc[i-1]
            if change > cutoff.iloc[i]:
                mf.iloc[i] = volume.iloc[i]
            elif change < -cutoff.iloc[i]:
                mf.iloc[i] = -volume.iloc[i]
            else:
                mf.iloc[i] = 0
                
        fve = (mf.rolling(period).sum() / volume.rolling(period).sum().replace(0, np.nan)) * 100
        return fve.fillna(0)

class VolatilityIndicators:
    """Volatility and range indicators."""

    @staticmethod
    def chandelier_exit(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 22, mult: float = 3.0) -> Tuple[pd.Series, pd.Series]:
        """
        Chandelier Exit.
        Provides dynamic trailing stop levels for long and short positions.
        """
        atr = VolatilityIndicators.atr(high, low, close, period)
        long_stop = high.rolling(window=period).max() - (atr * mult)
        short_stop = low.rolling(window=period).min() + (atr * mult)
        return long_stop.fillna(0), short_stop.fillna(0)

    @staticmethod
    def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period).mean().fillna(0)

    @staticmethod
    def bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
        ma = series.rolling(window=period).mean()
        sd = series.rolling(window=period).std()
        upper = ma + (std_dev * sd)
        lower = ma - (std_dev * sd)
        return upper.fillna(0), ma.fillna(0), lower.fillna(0)

    @staticmethod
    def adaptive_atr(df: pd.DataFrame, base_period: int = 14, regime: str = "sideways") -> pd.Series:
        """
        Wizard Upgrade: Adaptive ATR tuning.
        Adjusts the lookback period based on the market regime.
        """
        # Bullish/Bearish regimes favor longer averages, Sideways/Volatile favor shorter.
        period_map = {
            "bullish": base_period * 1.5,
            "bearish": base_period * 1.5,
            "sideways": base_period * 0.7,
            "volatile": base_period * 0.5,
            "unknown": base_period
        }
        tuned_period = int(period_map.get(regime.lower(), base_period))
        return VolatilityIndicators.atr(df['high'], df['low'], df['close'], tuned_period)

def calculate_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    """Calculates SuperTrend indicator."""
    high = df['high']
    low = df['low']
    close = df['close']
    
    atr = VolatilityIndicators.atr(high, low, close, period)
    
    hl2 = (high + low) / 2
    upperband = hl2 + (multiplier * atr)
    lowerband = hl2 - (multiplier * atr)
    
    supertrend = pd.Series(0.0, index=df.index)
    direction = pd.Series(1, index=df.index)
    
    for i in range(1, len(df)):
        if close.iloc[i-1] > upperband.iloc[i-1]:
            direction.iloc[i] = 1
        elif close.iloc[i-1] < lowerband.iloc[i-1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i-1]
            if direction.iloc[i] == 1 and lowerband.iloc[i] < lowerband.iloc[i-1]:
                lowerband.iloc[i] = lowerband.iloc[i-1]
            if direction.iloc[i] == -1 and upperband.iloc[i] > upperband.iloc[i-1]:
                upperband.iloc[i] = upperband.iloc[i-1]
        
        if direction.iloc[i] == 1:
            supertrend.iloc[i] = lowerband.iloc[i]
        else:
            supertrend.iloc[i] = upperband.iloc[i]
            
    return pd.DataFrame({'supertrend': supertrend, 'direction': direction})