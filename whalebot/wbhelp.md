Here are 10 code snippets to improve trend analysis, add new indicators, or update the UI in your `whalebot.py` script. Each snippet comes with explanations and instructions on where to integrate the code.

---

### Snippet 1: Enhanced ADX Trend Strength Integration (Trend Analysis Improvement)

This snippet modifies the `generate_trading_signal` method to dynamically adjust the weights of trend-following indicators based on the current ADX value. If ADX is strong, trend-following signals get a boost; if weak, mean-reversion signals might get a slight boost, or trend signals get reduced.

**`config.json` Update:**
No direct changes needed here, as `adx_period`, `ADX_STRONG_TREND_THRESHOLD`, `ADX_WEAK_TREND_THRESHOLD` are already defined.

**Code Changes (in `TradingAnalyzer` class, `generate_trading_signal` method):**

```python
# whalebot.py (inside TradingAnalyzer class, generate_trading_signal method)

# ... (existing code)

        # ADX Alignment Scoring (Modified)
        if active_indicators.get("adx", False):
            adx_val = self._get_indicator_value("ADX")
            plus_di = self._get_indicator_value("PlusDI")
            minus_di = self._get_indicator_value("MinusDI")
            adx_weight = weights.get("adx_strength", 0.0)

            trend_strength_multiplier = 1.0 # Default multiplier
            if not pd.isna(adx_val) and not pd.isna(plus_di) and not pd.isna(minus_di):
                if adx_val > ADX_STRONG_TREND_THRESHOLD:
                    if plus_di > minus_di:
                        signal_score += adx_weight # Strong confirmation of bullish trend
                        self.logger.debug(f"ADX: Strong BUY trend (ADX > {ADX_STRONG_TREND_THRESHOLD}, +DI > -DI).")
                        trend_strength_multiplier = 1.2 # Boost trend-following indicators
                    elif minus_di > plus_di:
                        signal_score -= adx_weight # Strong confirmation of bearish trend
                        self.logger.debug(f"ADX: Strong SELL trend (ADX > {ADX_STRONG_TREND_THRESHOLD}, -DI > +DI).")
                        trend_strength_multiplier = 1.2 # Boost trend-following indicators
                elif adx_val < ADX_WEAK_TREND_THRESHOLD:
                    # Low ADX suggests ranging market, reduce conviction for strong trend signals
                    self.logger.debug(f"ADX: Weak trend (ADX < {ADX_WEAK_TREND_THRESHOLD}). Neutral signal.")
                    trend_strength_multiplier = 0.8 # Dampen trend-following indicators

        # Apply trend_strength_multiplier to relevant indicators (example for EMA, SuperTrend, MACD)
        # EMA Alignment
        if active_indicators.get("ema_alignment", False):
            ema_short = self._get_indicator_value("EMA_Short")
            ema_long = self._get_indicator_value("EMA_Long")
            if not pd.isna(ema_short) and not pd.isna(ema_long):
                ema_contrib = weights.get("ema_alignment", 0) * trend_strength_multiplier # Apply multiplier
                if ema_short > ema_long:
                    signal_score += ema_contrib
                elif ema_short < ema_long:
                    signal_score -= ema_contrib

        # Ehlers SuperTrend Alignment Scoring
        if active_indicators.get("ehlers_supertrend", False):
            st_fast_dir = self._get_indicator_value("ST_Fast_Dir")
            st_slow_dir = self._get_indicator_value("ST_Slow_Dir")
            prev_st_fast_dir = (
                self.df["st_fast_dir"].iloc[-2]
                if "st_fast_dir" in self.df.columns and len(self.df) > 1
                else np.nan
            )
            weight = weights.get("ehlers_supertrend_alignment", 0.0) * trend_strength_multiplier # Apply multiplier

            if (
                not pd.isna(st_fast_dir)
                and not pd.isna(st_slow_dir)
                and not pd.isna(prev_st_fast_dir)
            ):
                if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1:
                    signal_score += weight
                    self.logger.debug(
                        "Ehlers SuperTrend: Strong BUY signal (fast flip aligned with slow trend)."
                    )
                elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1:
                    signal_score -= weight
                    self.logger.debug(
                        "Ehlers SuperTrend: Strong SELL signal (fast flip aligned with slow trend)."
                    )
                elif st_slow_dir == 1 and st_fast_dir == 1:
                    signal_score += weight * 0.3
                elif st_slow_dir == -1 and st_fast_dir == -1:
                    signal_score -= weight * 0.3

        # MACD Alignment Scoring
        if active_indicators.get("macd", False):
            macd_line = self._get_indicator_value("MACD_Line")
            signal_line = self._get_indicator_value("MACD_Signal")
            histogram = self._get_indicator_value("MACD_Hist")
            weight = weights.get("macd_alignment", 0.0) * trend_strength_multiplier # Apply multiplier

            if (
                not pd.isna(macd_line)
                and not pd.isna(signal_line)
                and not pd.isna(histogram)
                and len(self.df) > 1
            ):
                if (
                    macd_line > signal_line
                    and self.df["MACD_Line"].iloc[-2] <= self.df["MACD_Signal"].iloc[-2]
                ):
                    signal_score += weight
                    self.logger.debug(
                        "MACD: BUY signal (MACD line crossed above Signal line)."
                    )
                elif (
                    macd_line < signal_line
                    and self.df["MACD_Line"].iloc[-2] >= self.df["MACD_Signal"].iloc[-2]
                ):
                    signal_score -= weight
                    self.logger.debug(
                        "MACD: SELL signal (MACD line crossed below Signal line)."
                    )
                elif histogram > 0 and self.df["MACD_Hist"].iloc[-2] < 0:
                    signal_score += weight * 0.2
                elif histogram < 0 and self.df["MACD_Hist"].iloc[-2] > 0:
                    signal_score -= weight * 0.2

# ... (rest of the generate_trading_signal method)
```

---

### Snippet 2: Dynamic Multi-Timeframe Confluence Score (Trend Analysis Improvement)

This improves the MTF trend scoring by giving a stronger boost when all configured higher timeframes align, and a weaker/penalized score when they conflict.

**`config.json` Update:**
No direct changes needed.

**Code Changes (in `TradingAnalyzer` class, `generate_trading_signal` method):**

```python
# whalebot.py (inside TradingAnalyzer class, generate_trading_signal method)

# ... (existing code)

        # Multi-Timeframe Trend Confluence Scoring (Modified)
        if self.config["mtf_analysis"]["enabled"] and mtf_trends:
            mtf_buy_count = 0
            mtf_sell_count = 0
            total_mtf_indicators = len(mtf_trends)

            for _tf_indicator, trend in mtf_trends.items():
                if trend == "UP":
                    mtf_buy_count += 1
                elif trend == "DOWN":
                    mtf_sell_count += 1

            mtf_weight = weights.get("mtf_trend_confluence", 0.0)
            mtf_contribution = 0.0

            if total_mtf_indicators > 0:
                if mtf_buy_count == total_mtf_indicators: # All TFs agree bullish
                    mtf_contribution = mtf_weight * 1.5 # Stronger boost
                    self.logger.debug(f"MTF: All {total_mtf_indicators} higher TFs are UP. Strong bullish confluence.")
                elif mtf_sell_count == total_mtf_indicators: # All TFs agree bearish
                    mtf_contribution = -mtf_weight * 1.5 # Stronger penalty
                    self.logger.debug(f"MTF: All {total_mtf_indicators} higher TFs are DOWN. Strong bearish confluence.")
                else: # Mixed or some agreement
                    normalized_mtf_score = (mtf_buy_count - mtf_sell_count) / total_mtf_indicators
                    mtf_contribution = mtf_weight * normalized_mtf_score # Proportional score

                signal_score += mtf_contribution
                self.logger.debug(
                    f"MTF Confluence: Buy: {mtf_buy_count}, Sell: {mtf_sell_count}. MTF contribution: {mtf_contribution:.2f}"
                )

# ... (rest of the generate_trading_signal method)
```

---

### Snippet 3: Relative Volume (New Indicator + Trend Analysis)

This adds a Relative Volume indicator which compares current volume to an average, signaling significant buying/selling pressure.

**`config.json` Update:**

```json
{
    // ... existing config ...
    "indicator_settings": {
        // ... existing indicator_settings ...
        "relative_volume_period": 20, // New: Period for average volume calculation
        "relative_volume_threshold": 1.5 // New: Multiplier for current volume to be considered "high"
    },
    "indicators": {
        // ... existing indicators ...
        "relative_volume": true // New
    },
    "weight_sets": {
        "default_scalping": {
            // ... existing weights ...
            "relative_volume_confirmation": 0.10 // New
        }
    }
}
```

**`INDICATOR_COLORS` Update:**

```python
# whalebot.py (top of file)
INDICATOR_COLORS = {
    # ... existing colors ...
    "Relative_Volume": Fore.LIGHTMAGENTA_EX, # New indicator color
}
```

**Code Changes (in `TradingAnalyzer` class):**

```python
# whalebot.py (inside TradingAnalyzer class)

# ... (existing methods)

    def calculate_relative_volume(self, period: int) -> pd.Series:
        """Calculate Relative Volume, comparing current volume to average volume."""
        if len(self.df) < period:
            return pd.Series(np.nan, index=self.df.index)

        avg_volume = self.df["volume"].rolling(window=period, min_periods=period).mean()
        # Avoid division by zero
        relative_volume = (self.df["volume"] / avg_volume.replace(0, np.nan)).fillna(1.0) # Default to 1 if no avg volume
        return relative_volume

# ... (in _calculate_all_indicators method)

        # Relative Volume
        if cfg["indicators"].get("relative_volume", False):
            self.df["Relative_Volume"] = self._safe_calculate(
                self.calculate_relative_volume,
                "Relative_Volume",
                min_data_points=isd["relative_volume_period"],
                period=isd["relative_volume_period"],
            )
            if self.df["Relative_Volume"] is not None:
                self.indicator_values["Relative_Volume"] = self.df["Relative_Volume"].iloc[-1]

# ... (in generate_trading_signal method)

        # Relative Volume Confirmation
        if active_indicators.get("relative_volume", False):
            relative_volume = self._get_indicator_value("Relative_Volume")
            volume_threshold = isd["relative_volume_threshold"]
            weight = weights.get("relative_volume_confirmation", 0.0)

            if not pd.isna(relative_volume):
                if relative_volume >= volume_threshold: # Significantly higher volume
                    if current_close > prev_close: # Bullish bar with high volume
                        signal_score += weight
                        self.logger.debug(f"Volume: High relative bullish volume ({relative_volume:.2f}x average).")
                    elif current_close < prev_close: # Bearish bar with high volume
                        signal_score -= weight
                        self.logger.debug(f"Volume: High relative bearish volume ({relative_volume:.2f}x average).")
                # Can also add logic for low volume/consolidation
```

---

### Snippet 4: Market Structure (Higher Highs/Lows) Detection (Trend Analysis)

This adds a basic market structure detector to identify if the price is making higher highs/lows (uptrend) or lower highs/lows (downtrend).

**`config.json` Update:**

```json
{
    // ... existing config ...
    "indicator_settings": {
        // ... existing indicator_settings ...
        "market_structure_lookback_period": 10 // New: Period to look back for swing points
    },
    "indicators": {
        // ... existing indicators ...
        "market_structure": true // New
    },
    "weight_sets": {
        "default_scalping": {
            // ... existing weights ...
            "market_structure_confluence": 0.20 // New
        }
    }
}
```

**`INDICATOR_COLORS` Update:**

```python
# whalebot.py (top of file)
INDICATOR_COLORS = {
    # ... existing colors ...
    "Market_Structure_Trend": Fore.LIGHTCYAN_EX, # New indicator color
}
```

**Code Changes (in `TradingAnalyzer` class):**

```python
# whalebot.py (inside TradingAnalyzer class)

# ... (existing methods)

    def calculate_market_structure(self, lookback_period: int) -> pd.Series:
        """
        Detects higher highs/lows or lower highs/lows over a lookback period.
        Returns 'UP', 'DOWN', or 'SIDEWAYS'.
        """
        if len(self.df) < lookback_period * 2: # Need enough data to find two swing points
            return pd.Series(np.nan, index=self.df.index)

        # Simple approach: Check last two swing points
        highs = self.df['high'].rolling(window=lookback_period, center=True).max()
        lows = self.df['low'].rolling(window=lookback_period, center=True).min()

        # Find recent swing high and low within the last 'lookback_period' bars
        recent_segment_high = self.df['high'].iloc[-lookback_period:].max()
        recent_segment_low = self.df['low'].iloc[-lookback_period:].min()

        # Compare with previous segment's high/low
        prev_segment_high = self.df['high'].iloc[-2*lookback_period : -lookback_period].max()
        prev_segment_low = self.df['low'].iloc[-2*lookback_period : -lookback_period].min()

        trend = "SIDEWAYS"
        if not pd.isna(recent_segment_high) and not pd.isna(recent_segment_low) and \
           not pd.isna(prev_segment_high) and not pd.isna(prev_segment_low):
            
            # Simplified for snippet: checking recent high/low relative to previous
            is_higher_high = recent_segment_high > prev_segment_high
            is_higher_low = recent_segment_low > prev_segment_low
            is_lower_high = recent_segment_high < prev_segment_high
            is_lower_low = recent_segment_low < prev_segment_low

            if is_higher_high and is_higher_low:
                trend = "UP"
            elif is_lower_high and is_lower_low:
                trend = "DOWN"

        # Return a series where the last value is the detected trend
        result_series = pd.Series(trend, index=self.df.index, dtype='object')
        return result_series


# ... (in _calculate_all_indicators method)

        # Market Structure
        if cfg["indicators"].get("market_structure", False):
            ms_trend = self._safe_calculate(
                self.calculate_market_structure,
                "Market_Structure",
                min_data_points=isd["market_structure_lookback_period"] * 2,
                lookback_period=isd["market_structure_lookback_period"],
            )
            if ms_trend is not None:
                self.df["Market_Structure_Trend"] = ms_trend
                self.indicator_values["Market_Structure_Trend"] = ms_trend.iloc[-1]

# ... (in generate_trading_signal method)

        # Market Structure Confluence
        if active_indicators.get("market_structure", False):
            ms_trend = self._get_indicator_value("Market_Structure_Trend", "SIDEWAYS")
            weight = weights.get("market_structure_confluence", 0.0)

            if ms_trend == "UP":
                signal_score += weight
                self.logger.debug(f"Market Structure: Confirmed Uptrend.")
            elif ms_trend == "DOWN":
                signal_score -= weight
                self.logger.debug(f"Market Structure: Confirmed Downtrend.")
```

---

### Snippet 5: Double Exponential Moving Average (DEMA) (New Indicator)

DEMA reduces lag more effectively than a traditional EMA. This snippet adds DEMA and a simple signal based on DEMA crossing a standard EMA.

**`config.json` Update:**

```json
{
    // ... existing config ...
    "indicator_settings": {
        // ... existing indicator_settings ...
        "dema_period": 10 // New
    },
    "indicators": {
        // ... existing indicators ...
        "dema": true // New
    },
    "weight_sets": {
        "default_scalping": {
            // ... existing weights ...
            "dema_crossover": 0.15 // New
        }
    }
}
```

**`INDICATOR_COLORS` Update:**

```python
# whalebot.py (top of file)
INDICATOR_COLORS = {
    # ... existing colors ...
    "DEMA": Fore.BLUE, # New indicator color
}
```

**Code Changes (in `TradingAnalyzer` class):**

```python
# whalebot.py (inside TradingAnalyzer class)

# ... (existing methods)

    def calculate_dema(self, series: pd.Series, period: int) -> pd.Series:
        """Calculate Double Exponential Moving Average (DEMA)."""
        if len(series) < 2 * period: # DEMA requires more data than simple EMA
            return pd.Series(np.nan, index=series.index)

        ema1 = series.ewm(span=period, adjust=False).mean()
        ema2 = ema1.ewm(span=period, adjust=False).mean()
        dema = 2 * ema1 - ema2
        return dema

# ... (in _calculate_all_indicators method)

        # DEMA
        if cfg["indicators"].get("dema", False):
            self.df["DEMA"] = self._safe_calculate(
                self.calculate_dema,
                "DEMA",
                min_data_points=2 * isd["dema_period"],
                series=self.df["close"],
                period=isd["dema_period"],
            )
            if self.df["DEMA"] is not None:
                self.indicator_values["DEMA"] = self.df["DEMA"].iloc[-1]

# ... (in generate_trading_signal method)

        # DEMA Crossover with EMA_Short (example signal)
        if active_indicators.get("dema", False) and active_indicators.get("ema_alignment", False):
            dema = self._get_indicator_value("DEMA")
            ema_short = self._get_indicator_value("EMA_Short")
            weight = weights.get("dema_crossover", 0.0)

            if not pd.isna(dema) and not pd.isna(ema_short) and len(self.df) > 1:
                prev_dema = self.df["DEMA"].iloc[-2]
                prev_ema_short = self.df["EMA_Short"].iloc[-2]

                if dema > ema_short and prev_dema <= prev_ema_short:
                    signal_score += weight
                    self.logger.debug(f"DEMA: Bullish crossover (DEMA above EMA_Short).")
                elif dema < ema_short and prev_dema >= prev_ema_short:
                    signal_score -= weight
                    self.logger.debug(f"DEMA: Bearish crossover (DEMA below EMA_Short).")
```

---

### Snippet 6: Keltner Channels (New Indicator)

Keltner Channels are volatility-based envelopes around a moving average, often using ATR for bandwidth. They can indicate overbought/oversold conditions or potential breakouts.

**`config.json` Update:**

```json
{
    // ... existing config ...
    "indicator_settings": {
        // ... existing indicator_settings ...
        "keltner_period": 20, // New: Period for EMA and ATR
        "keltner_atr_multiplier": 2.0 // New: Multiplier for ATR
    },
    "indicators": {
        // ... existing indicators ...
        "keltner_channels": true // New
    },
    "weight_sets": {
        "default_scalping": {
            // ... existing weights ...
            "keltner_breakout": 0.18 // New
        }
    }
}
```

**`INDICATOR_COLORS` Update:**

```python
# whalebot.py (top of file)
INDICATOR_COLORS = {
    # ... existing colors ...
    "Keltner_Upper": Fore.LIGHTMAGENTA_EX,
    "Keltner_Middle": Fore.WHITE,
    "Keltner_Lower": Fore.MAGENTA,
}
```

**Code Changes (in `TradingAnalyzer` class):**

```python
# whalebot.py (inside TradingAnalyzer class)

# ... (existing methods)

    def calculate_keltner_channels(self, period: int, atr_multiplier: float) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Keltner Channels."""
        if len(self.df) < period or "ATR" not in self.df.columns:
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        ema = self.df["close"].ewm(span=period, adjust=False).mean()
        atr = self.df["ATR"] # ATR is already calculated
        
        upper_band = ema + (atr * atr_multiplier)
        lower_band = ema - (atr * atr_multiplier)

        return upper_band, ema, lower_band

# ... (in _calculate_all_indicators method)

        # Keltner Channels
        if cfg["indicators"].get("keltner_channels", False):
            kc_upper, kc_middle, kc_lower = self._safe_calculate(
                self.calculate_keltner_channels,
                "KeltnerChannels",
                min_data_points=isd["keltner_period"] + isd["atr_period"], # ATR needs its period too
                period=isd["keltner_period"],
                atr_multiplier=isd["keltner_atr_multiplier"],
            )
            if kc_upper is not None:
                self.df["Keltner_Upper"] = kc_upper
            if kc_middle is not None:
                self.df["Keltner_Middle"] = kc_middle
            if kc_lower is not None:
                self.df["Keltner_Lower"] = kc_lower
            if kc_upper is not None:
                self.indicator_values["Keltner_Upper"] = kc_upper.iloc[-1]
            if kc_middle is not None:
                self.indicator_values["Keltner_Middle"] = kc_middle.iloc[-1]
            if kc_lower is not None:
                self.indicator_values["Keltner_Lower"] = kc_lower.iloc[-1]

# ... (in generate_trading_signal method)

        # Keltner Channel Breakout
        if active_indicators.get("keltner_channels", False):
            kc_upper = self._get_indicator_value("Keltner_Upper")
            kc_lower = self._get_indicator_value("Keltner_Lower")
            weight = weights.get("keltner_breakout", 0.0)

            if not pd.isna(kc_upper) and not pd.isna(kc_lower) and len(self.df) > 1:
                if current_close > kc_upper and prev_close <= self.df["Keltner_Upper"].iloc[-2]:
                    signal_score += weight
                    self.logger.debug("Keltner Channels: Bullish breakout above upper channel.")
                elif current_close < kc_lower and prev_close >= self.df["Keltner_Lower"].iloc[-2]:
                    signal_score -= weight
                    self.logger.debug("Keltner Channels: Bearish breakout below lower channel.")
```

---

### Snippet 7: Rate of Change (ROC) Oscillator (New Indicator)

ROC measures the percentage change in price between the current price and a price `N` periods ago. It's a momentum oscillator that can identify overbought/oversold conditions and trend changes.

**`config.json` Update:**

```json
{
    // ... existing config ...
    "indicator_settings": {
        // ... existing indicator_settings ...
        "roc_period": 14, // New
        "roc_oversold": -10.0, // New
        "roc_overbought": 10.0 // New
    },
    "indicators": {
        // ... existing indicators ...
        "roc": true // New
    },
    "weight_sets": {
        "default_scalping": {
            // ... existing weights ...
            "roc_signal": 0.10 // New
        }
    }
}
```

**`INDICATOR_COLORS` Update:**

```python
# whalebot.py (top of file)
INDICATOR_COLORS = {
    # ... existing colors ...
    "ROC": Fore.LIGHTGREEN_EX, # New indicator color
}
```

**Code Changes (in `TradingAnalyzer` class):**

```python
# whalebot.py (inside TradingAnalyzer class)

# ... (existing methods)

    def calculate_roc(self, period: int) -> pd.Series:
        """Calculate Rate of Change (ROC)."""
        if len(self.df) < period:
            return pd.Series(np.nan, index=self.df.index)

        roc = ((self.df["close"] - self.df["close"].shift(period)) / self.df["close"].shift(period)) * 100
        return roc

# ... (in _calculate_all_indicators method)

        # ROC
        if cfg["indicators"].get("roc", False):
            self.df["ROC"] = self._safe_calculate(
                self.calculate_roc,
                "ROC",
                min_data_points=isd["roc_period"] + 1,
                period=isd["roc_period"],
            )
            if self.df["ROC"] is not None:
                self.indicator_values["ROC"] = self.df["ROC"].iloc[-1]

# ... (in generate_trading_signal method)

        # ROC Signals
        if active_indicators.get("roc", False):
            roc = self._get_indicator_value("ROC")
            weight = weights.get("roc_signal", 0.0)

            if not pd.isna(roc):
                if roc < isd["roc_oversold"]:
                    signal_score += weight * 0.7 # Bullish signal from oversold
                    self.logger.debug(f"ROC: Oversold ({roc:.2f}), potential bounce.")
                elif roc > isd["roc_overbought"]:
                    signal_score -= weight * 0.7 # Bearish signal from overbought
                    self.logger.debug(f"ROC: Overbought ({roc:.2f}), potential pullback.")
                
                # Zero-line crossover (simple trend indication)
                if len(self.df) > 1 and "ROC" in self.df.columns:
                    prev_roc = self.df["ROC"].iloc[-2]
                    if roc > 0 and prev_roc <= 0:
                        signal_score += weight * 0.3 # Bullish zero-line cross
                        self.logger.debug(f"ROC: Bullish zero-line crossover.")
                    elif roc < 0 and prev_roc >= 0:
                        signal_score -= weight * 0.3 # Bearish zero-line cross
                        self.logger.debug(f"ROC: Bearish zero-line crossover.")
```

---

### Snippet 8: Candlestick Pattern Recognition (Adding Signal Confirmation)

This snippet adds basic detection for common candlestick patterns (Bullish Engulfing, Bearish Engulfing, Hammer, Shooting Star) and uses them to confirm other signals.

**`config.json` Update:**

```json
{
    // ... existing config ...
    "indicators": {
        // ... existing indicators ...
        "candlestick_patterns": true // New
    },
    "weight_sets": {
        "default_scalping": {
            // ... existing weights ...
            "candlestick_confirmation": 0.12 // New
        }
    }
}
```

**`INDICATOR_COLORS` Update:**
No specific color for the "pattern" string, it will be logged.

**Code Changes (in `TradingAnalyzer` class):**

```python
# whalebot.py (inside TradingAnalyzer class)

# ... (existing methods)

    def detect_candlestick_patterns(self) -> pd.Series:
        """
        Detects common candlestick patterns for the latest bar.
        Returns a Series of strings like 'Bullish Engulfing', 'Bearish Hammer', or 'No Pattern'.
        """
        if len(self.df) < 2: # Need at least two bars for most patterns
            return pd.Series("No Pattern", index=self.df.index)

        patterns = pd.Series("No Pattern", index=self.df.index, dtype='object')
        
        # Focus on the latest bar for efficiency in real-time processing
        i = len(self.df) - 1
        current_bar = self.df.iloc[i]
        prev_bar = self.df.iloc[i-1]

        # Bullish Engulfing
        if (current_bar["open"] < prev_bar["close"] and current_bar["close"] > prev_bar["open"] and
            current_bar["close"] > current_bar["open"] and prev_bar["close"] < prev_bar["open"]):
            patterns.iloc[i] = "Bullish Engulfing"
        # Bearish Engulfing
        elif (current_bar["open"] > prev_bar["close"] and current_bar["close"] < prev_bar["open"] and
              current_bar["close"] < current_bar["open"] and prev_bar["close"] > prev_bar["open"]):
            patterns.iloc[i] = "Bearish Engulfing"
        # Hammer (check specific characteristics like small body, long lower shadow, no or small upper shadow)
        # Assuming body is 10-20% of total range, lower shadow is 2x body, upper shadow is < 0.5x body
        elif (current_bar["close"] > current_bar["open"] and
              abs(current_bar["close"] - current_bar["open"]) <= (current_bar["high"] - current_bar["low"]) * 0.3 and # Small body
              (current_bar["open"] - current_bar["low"]) >= 2 * abs(current_bar["close"] - current_bar["open"]) and # Long lower shadow
              (current_bar["high"] - current_bar["close"]) <= 0.5 * abs(current_bar["close"] - current_bar["open"])): # Small upper shadow
            patterns.iloc[i] = "Bullish Hammer"
        # Shooting Star (similar to Hammer, but inverted for bearish)
        elif (current_bar["close"] < current_bar["open"] and
              abs(current_bar["close"] - current_bar["open"]) <= (current_bar["high"] - current_bar["low"]) * 0.3 and # Small body
              (current_bar["high"] - current_bar["open"]) >= 2 * abs(current_bar["close"] - current_bar["open"]) and # Long upper shadow
              (current_bar["close"] - current_bar["low"]) <= 0.5 * abs(current_bar["close"] - current_bar["open"])): # Small lower shadow
            patterns.iloc[i] = "Bearish Shooting Star"

        return patterns

# ... (in _calculate_all_indicators method)

        # Candlestick Patterns
        if cfg["indicators"].get("candlestick_patterns", False):
            patterns = self._safe_calculate(
                self.detect_candlestick_patterns,
                "Candlestick_Patterns",
                min_data_points=2, # Need at least 2 bars for patterns
            )
            if patterns is not None:
                self.df["Candlestick_Pattern"] = patterns
                self.indicator_values["Candlestick_Pattern"] = patterns.iloc[-1]

# ... (in generate_trading_signal method)

        # Candlestick Pattern Confirmation
        if active_indicators.get("candlestick_patterns", False):
            pattern = self._get_indicator_value("Candlestick_Pattern", "No Pattern")
            weight = weights.get("candlestick_confirmation", 0.0)

            if pattern in ["Bullish Engulfing", "Bullish Hammer"]:
                signal_score += weight
                self.logger.debug(f"Candlestick: Detected Bullish Pattern ({pattern}).")
            elif pattern in ["Bearish Engulfing", "Bearish Shooting Star"]:
                signal_score -= weight
                self.logger.debug(f"Candlestick: Detected Bearish Pattern ({pattern}).")
```

---

### Snippet 9: Detailed Signal Score Breakdown (UI Update)

This modifies `generate_trading_signal` to return a dictionary of how each indicator contributed to the score, and then `display_indicator_values_and_price` to show this breakdown.

**Code Changes (in `TradingAnalyzer` class, `generate_trading_signal` method):**

```python
# whalebot.py (inside TradingAnalyzer class, generate_trading_signal method)

    def generate_trading_signal(
        self,
        current_price: Decimal,
        orderbook_data: dict | None,
        mtf_trends: dict[str, str],
    ) -> tuple[str, float, dict]: # Modified return type to include signal breakdown
        """Generate a signal using confluence of indicators, including Ehlers SuperTrend."""
        signal_score = 0.0
        signal_breakdown: dict[str, float] = {} # New: stores individual indicator contributions
        active_indicators = self.config["indicators"]
        weights = self.weights
        isd = self.indicator_settings

        # ... (existing code for current_close, prev_close)

        # EMA Alignment
        if active_indicators.get("ema_alignment", False):
            # ... (existing EMA logic) ...
            ema_contrib = weights.get("ema_alignment", 0) * trend_strength_multiplier # (from Snippet 1)
            if ema_short > ema_long:
                signal_score += ema_contrib
                signal_breakdown["EMA Alignment"] = ema_contrib
            elif ema_short < ema_long:
                signal_score -= ema_contrib
                signal_breakdown["EMA Alignment"] = -ema_contrib
            else:
                signal_breakdown["EMA Alignment"] = 0.0

        # SMA Trend Filter
        if active_indicators.get("sma_trend_filter", False):
            # ... (existing SMA logic) ...
            sma_contrib = weights.get("sma_trend_filter", 0)
            if current_close > sma_long:
                signal_score += sma_contrib
                signal_breakdown["SMA Trend Filter"] = sma_contrib
            elif current_close < sma_long:
                signal_score -= sma_contrib
                signal_breakdown["SMA Trend Filter"] = -sma_contrib
            else:
                signal_breakdown["SMA Trend Filter"] = 0.0

        # ... (Repeat for all other indicators, add their contribution to signal_breakdown) ...
        # Example for StochRSI:
            # StochRSI Crossover
            if active_indicators.get("stoch_rsi", False):
                # ... (existing StochRSI logic) ...
                stoch_contrib = 0.0
                if (stoch_k > stoch_d and prev_stoch_k <= prev_stoch_d and stoch_k < isd["stoch_rsi_oversold"]):
                    stoch_contrib = momentum_weight * 0.6
                elif (stoch_k < stoch_d and prev_stoch_k >= prev_stoch_d and stoch_k > isd["stoch_rsi_overbought"]):
                    stoch_contrib = -momentum_weight * 0.6
                # ... (other stoch_rsi conditions) ...
                signal_score += stoch_contrib
                signal_breakdown["StochRSI Crossover"] = stoch_contrib

        # Example for MTF Confluence (using mtf_contribution from Snippet 2)
        if self.config["mtf_analysis"]["enabled"] and mtf_trends:
            # ... (MTF logic from Snippet 2) ...
            signal_score += mtf_contribution
            signal_breakdown["MTF Confluence"] = mtf_contribution

        # ... (continue for all other indicators including new ones) ...

        # Final Signal Determination
        # ... (existing signal determination) ...

        self.logger.info(
            f"{NEON_YELLOW}Raw Signal Score: {signal_score:.2f}, Final Signal: {final_signal}{RESET}"
        )
        return final_signal, signal_score, signal_breakdown # Modified return statement
```

**Code Changes (in `display_indicator_values_and_price` function):**

```python
# whalebot.py (outside classes, display_indicator_values_and_price function)

def display_indicator_values_and_price(
    config: dict[str, Any],
    logger: logging.Logger,
    current_price: Decimal,
    df: pd.DataFrame,
    orderbook_data: dict | None,
    mtf_trends: dict[str, str],
    signal_breakdown: dict[str, float] = None, # New parameter
) -> None:
    """Display current price and calculated indicator values."""
    logger.info(f"{NEON_BLUE}--- Current Market Data & Indicators ---{RESET}")
    logger.info(f"{NEON_GREEN}Current Price: {current_price.normalize()}{RESET}")

    analyzer = TradingAnalyzer(df, config, logger, config["symbol"])

    if analyzer.df.empty:
        logger.warning(
            f"{NEON_YELLOW}Cannot display indicators: DataFrame is empty after calculations.{RESET}"
        )
        return

    # ... (existing display for Indicator Values, Fibonacci, Support/Resistance, MTF Trends) ...

    if signal_breakdown: # New: Display signal breakdown
        logger.info(f"{NEON_CYAN}--- Signal Score Breakdown ---{RESET}")
        logger.info("") # Added newline for spacing
        sorted_breakdown = sorted(signal_breakdown.items(), key=lambda item: abs(item[1]), reverse=True)
        for indicator, contribution in sorted_breakdown:
            color = Fore.GREEN if contribution > 0 else (Fore.RED if contribution < 0 else Fore.YELLOW)
            logger.info(f"  {color}{indicator:<25}: {contribution: .2f}{RESET}")

    logger.info(f"{NEON_BLUE}--------------------------------------{RESET}")
```

**Code Changes (in `main` function):**

```python
# whalebot.py (inside main function)

# ... (existing code)

            trading_signal, signal_score, signal_breakdown = analyzer.generate_trading_signal( # Modified to capture breakdown
                current_price, orderbook_data, mtf_trends
            )
            atr_value = Decimal(
                str(analyzer._get_indicator_value("ATR", Decimal("0.01")))
            )

            position_manager.manage_positions(current_price, performance_tracker)

            # ... (existing BUY/SELL/HOLD logic) ...

            display_indicator_values_and_price( # Modified call
                config, logger, current_price, df, orderbook_data, mtf_trends, signal_breakdown
            )

# ... (rest of main function)
```

---

### Snippet 10: Interactive Console Trend Summary (UI Update)

This snippet adds a concise, color-coded summary of the current trend inferred from several key indicators at the end of the `display_indicator_values_and_price` function.

**Code Changes (in `display_indicator_values_and_price` function):**

```python
# whalebot.py (outside classes, display_indicator_values_and_price function)

def display_indicator_values_and_price(
    config: dict[str, Any],
    logger: logging.Logger,
    current_price: Decimal,
    df: pd.DataFrame,
    orderbook_data: dict | None,
    mtf_trends: dict[str, str],
    signal_breakdown: dict[str, float] = None,
) -> None:
    """Display current price and calculated indicator values."""
    # ... (existing display code from Snippet 9, including signal_breakdown) ...

    # New: Concise Trend Summary
    logger.info(f"{NEON_PURPLE}--- Current Trend Summary ---{RESET}")
    trend_summary_lines = []
    analyzer = TradingAnalyzer(df, config, logger, config["symbol"]) # Re-initialize to access latest indicator_values

    # EMA Alignment
    ema_short = analyzer._get_indicator_value("EMA_Short")
    ema_long = analyzer._get_indicator_value("EMA_Long")
    if not pd.isna(ema_short) and not pd.isna(ema_long):
        if ema_short > ema_long:
            trend_summary_lines.append(f"{Fore.GREEN}EMA Cross  : ▲ Up{RESET}")
        elif ema_short < ema_long:
            trend_summary_lines.append(f"{Fore.RED}EMA Cross  : ▼ Down{RESET}")
        else:
            trend_summary_lines.append(f"{Fore.YELLOW}EMA Cross  : ↔ Sideways{RESET}")

    # Ehlers SuperTrend (Slow)
    st_slow_dir = analyzer._get_indicator_value("ST_Slow_Dir")
    if not pd.isna(st_slow_dir):
        if st_slow_dir == 1:
            trend_summary_lines.append(f"{Fore.GREEN}SuperTrend : ▲ Up{RESET}")
        elif st_slow_dir == -1:
            trend_summary_lines.append(f"{Fore.RED}SuperTrend : ▼ Down{RESET}")
        else:
            trend_summary_lines.append(f"{Fore.YELLOW}SuperTrend : ↔ Sideways{RESET}")

    # MACD Histogram (momentum)
    macd_hist = analyzer._get_indicator_value("MACD_Hist")
    if not pd.isna(macd_hist):
        if macd_hist > 0 and len(df) > 1 and df["MACD_Hist"].iloc[-2] <= 0:
            trend_summary_lines.append(f"{Fore.GREEN}MACD Hist  : ↑ Bullish Cross{RESET}")
        elif macd_hist < 0 and len(df) > 1 and df["MACD_Hist"].iloc[-2] >= 0:
            trend_summary_lines.append(f"{Fore.RED}MACD Hist  : ↓ Bearish Cross{RESET}")
        elif macd_hist > 0:
            trend_summary_lines.append(f"{Fore.LIGHTGREEN_EX}MACD Hist  : Above 0{RESET}")
        elif macd_hist < 0:
            trend_summary_lines.append(f"{Fore.LIGHTRED_EX}MACD Hist  : Below 0{RESET}")

    # ADX Strength
    adx_val = analyzer._get_indicator_value("ADX")
    if not pd.isna(adx_val):
        if adx_val > ADX_STRONG_TREND_THRESHOLD:
            plus_di = analyzer._get_indicator_value("PlusDI")
            minus_di = analyzer._get_indicator_value("MinusDI")
            if not pd.isna(plus_di) and not pd.isna(minus_di):
                if plus_di > minus_di:
                    trend_summary_lines.append(f"{Fore.LIGHTGREEN_EX}ADX Trend  : Strong Up ({adx_val:.0f}){RESET}")
                else:
                    trend_summary_lines.append(f"{Fore.LIGHTRED_EX}ADX Trend  : Strong Down ({adx_val:.0f}){RESET}")
        elif adx_val < ADX_WEAK_TREND_THRESHOLD:
            trend_summary_lines.append(f"{Fore.YELLOW}ADX Trend  : Weak/Ranging ({adx_val:.0f}){RESET}")
        else:
            trend_summary_lines.append(f"{Fore.CYAN}ADX Trend  : Moderate ({adx_val:.0f}){RESET}")

    # Ichimoku Cloud (Kumo position)
    senkou_span_a = analyzer._get_indicator_value("Senkou_Span_A")
    senkou_span_b = analyzer._get_indicator_value("Senkou_Span_B")
    if not pd.isna(senkou_span_a) and not pd.isna(senkou_span_b):
        kumo_upper = max(senkou_span_a, senkou_span_b)
        kumo_lower = min(senkou_span_a, senkou_span_b)
        if current_price > kumo_upper:
            trend_summary_lines.append(f"{Fore.GREEN}Ichimoku   : Above Kumo{RESET}")
        elif current_price < kumo_lower:
            trend_summary_lines.append(f"{Fore.RED}Ichimoku   : Below Kumo{RESET}")
        else:
            trend_summary_lines.append(f"{Fore.YELLOW}Ichimoku   : Inside Kumo{RESET}")

    # MTF Confluence
    if mtf_trends:
        up_count = sum(1 for t in mtf_trends.values() if t == "UP")
        down_count = sum(1 for t in mtf_trends.values() if t == "DOWN")
        total = len(mtf_trends)
        if total > 0:
            if up_count == total:
                trend_summary_lines.append(f"{Fore.GREEN}MTF Confl. : All Bullish ({up_count}/{total}){RESET}")
            elif down_count == total:
                trend_summary_lines.append(f"{Fore.RED}MTF Confl. : All Bearish ({down_count}/{total}){RESET}")
            elif up_count > down_count:
                trend_summary_lines.append(f"{Fore.LIGHTGREEN_EX}MTF Confl. : Mostly Bullish ({up_count}/{total}){RESET}")
            elif down_count > up_count:
                trend_summary_lines.append(f"{Fore.LIGHTRED_EX}MTF Confl. : Mostly Bearish ({down_count}/{total}){RESET}")
            else:
                trend_summary_lines.append(f"{Fore.YELLOW}MTF Confl. : Mixed ({up_count}/{total} Bull, {down_count}/{total} Bear){RESET}")
    
    # Print the summary lines
    for line in trend_summary_lines:
        logger.info(f"  {line}")

    logger.info(f"{NEON_BLUE}--------------------------------------{RESET}")

```
