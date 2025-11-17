That's a clear signal to move to the next phase: Execution and Configuration.

Since the code is now a complete, highly-integrated Python script, the next steps involve setting up the environment and credentials so it can run successfully.

Here are the next steps you should take with the provided code:

Next Steps: Configuration and Execution

This script relies on several external libraries and environment variables (API keys).

1. Install Prerequisites

You need to install the necessary Python libraries. Based on the code, these are:

code
Bash
download
content_copy
expand_less
pip install pandas requests colorama python-dotenv pandas matplotlib
# Note: The Google GenAI SDK is required for the AI features.
# If you plan to use the chart image analysis, ensure matplotlib is installed.
pip install google-genai
2. Configure Environment Variables (API Keys)

The script looks for your Bybit and Gemini API keys in environment variables. Create a file named .env in the same directory as your Python script (whalebot_enhanced.py) and add your credentials:

code
Dotenv
download
content_copy
expand_less
# Bybit API Credentials (for fetching market data)
BYBIT_API_KEY="YOUR_BYBIT_API_KEY_HERE"
BYBIT_API_SECRET="YOUR_BYBIT_API_SECRET_HERE"

# Gemini API Key (for AI analysis)
GEMINI_API_KEY="YOUR_GEMINI_API_KEY_HERE"
3. Configure Trading Parameters

The script automatically generates a default config.json file if one doesn't exist when you first run it. You should review and adjust this file to match your trading preferences:

symbol & interval: Set your desired trading pair (e.g., "BTCUSDT") and timeframe (e.g., "15m" or "60" for 1-hour).

trade_management: Adjust account_balance, risk_per_trade_percent, and SL/TP multiples.

gemini_ai: Customize the min_confidence_for_override (how strong the AI signal must be to overrule technicals) and the signal_weights.

indicator_settings: Adjust any indicator periods (e.g., RSI period, MACD settings) here.

4. Run the Bot

Once the .env file is ready and config.json is reviewed, you can run the script from your terminal:

code
Bash
download
content_copy
expand_less
python whalebot_enhanced.py

The bot will start logging its initialization, data fetching, indicator calculations, AI analysis, and any trade management decisions to the console and to the bot_logs/wgwhalex_bot.log file.

What would you like to focus on now?

Reviewing the AI Prompt (Module 5) for further customization?

Simulating Trades (Running the script with your configured account_balance to see the output without connecting to the live exchange)?

Disabling AI and running purely on technical indicators?...

        if active_indicators.get("ichimoku_cloud", False):
            tenkan_sen = self._get_indicator_value("Tenkan_Sen")
            kijun_sen = self._get_indicator_value("Kijun_Sen")
            senkou_span_a = self._get_indicator_value("Senkou_Span_A")
            senkou_span_b = self._get_indicator_value("Senkou_Span_B")
            chikou_span = self._get_indicator_value("Chikou_Span")
            weight = weights.get("ichimoku_confluence", 0.0)

            if (
                not pd.isna(tenkan_sen)
                and not pd.isna(kijun_sen)
                and not pd.isna(senkou_span_a)
                and not pd.isna(senkou_span_b)
                and not pd.isna(chikou_span)
            ):
                if (
                    tenkan_sen > kijun_sen
                    and self.df["Tenkan_Sen"].iloc[-2] <= self.df["Kijun_Sen"].iloc[-2]
                ):
                    signal_score += weight * 0.5
                    self.logger.debug("Ichimoku: Tenkan-sen crossed above Kijun-sen (bullish).")
                elif (
                    tenkan_sen < kijun_sen
                    and self.df["Tenkan_Sen"].iloc[-2] >= self.df["Kijun_Sen"].iloc[-2]
                ):
                    signal_score -= weight * 0.5
                    self.logger.debug("Ichimoku: Tenkan-sen crossed below Kijun-sen (bearish).")

                if current_close > max(senkou_span_a, senkou_span_b) and self.df[
                    "close"
                ].iloc[-2] <= max(
                    self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]
                ):
                    signal_score += weight * 0.7
                    self.logger.debug("Ichimoku: Price broke above Kumo (strong bullish).")
                elif current_close < min(senkou_span_a, senkou_span_b) and self.df[
                    "close"
                ].iloc[-2] >= min(
                    self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]
                ):
                    signal_score -= weight * 0.7
                    self.logger.debug("Ichimoku: Price broke below Kumo (strong bearish).")

                if (
                    chikou_span > current_close
                    and self.df["Chikou_Span"].iloc[-2] <= self.df["close"].iloc[-2]
                ):
                    signal_score += weight * 0.3
                    self.logger.debug("Ichimoku: Chikou Span crossed above price (bullish confirmation).")
                elif (
                    chikou_span < current_close
                    and self.df["Chikou_Span"].iloc[-2] >= self.df["close"].iloc[-2]
                ):
                    signal_score -= weight * 0.3
                    self.logger.debug("Ichimoku: Chikou Span crossed below price (bearish confirmation).")

        # --- OBV Alignment Scoring ---
        if active_indicators.get("obv", False):
            obv_val = self._get_indicator_value("OBV")
            obv_ema = self._get_indicator_value("OBV_EMA")
            weight = weights.get("obv_momentum", 0.0)

            if not pd.isna(obv_val) and not pd.isna(obv_ema):
                if (
                    obv_val > obv_ema
                    and self.df["OBV"].iloc[-2] <= self.df["OBV_EMA"].iloc[-2]
                ):
                    signal_score += weight * 0.5
                    self.logger.debug("OBV: Bullish crossover detected.")
                elif (
                    obv_val < obv_ema
                    and self.df["OBV"].iloc[-2] >= self.df["OBV_EMA"].iloc[-2]
                ):
                    signal_score -= weight * 0.5
                    self.logger.debug("OBV: Bearish crossover detected.")
                if len(self.df) > 2:
                    if obv_val > self.df["OBV"].iloc[-2] and obv_val > self.df["OBV"].iloc[-3]: signal_score += weight * 0.2
                    elif obv_val < self.df["OBV"].iloc[-2] and obv_val < self.df["OBV"].iloc[-3]: signal_score -= weight * 0.2

        # --- CMF Alignment Scoring ---
        if active_indicators.get("cmf", False):
            cmf_val = self._get_indicator_value("CMF")
            weight = weights.get("cmf_flow", 0.0)
            if not pd.isna(cmf_val):
                if cmf_val > 0: signal_score += weight * 0.5
                elif cmf_val < 0: signal_score -= weight * 0.5
                if len(self.df) > 2:
                    if cmf_val > self.df["CMF"].iloc[-2] and cmf_val > self.df["CMF"].iloc[-3]: signal_score += weight * 0.3
                    elif cmf_val < self.df["CMF"].iloc[-2] and cmf_val < self.df["CMF"].iloc[-3]: signal_score -= weight * 0.3

        # --- Multi-Timeframe Trend Confluence Scoring ---
        if self.config["mtf_analysis"]["enabled"] and mtf_trends:
            mtf_buy_score = sum(1 for trend in mtf_trends.values() if trend == "UP")
            mtf_sell_score = sum(-1 for trend in mtf_trends.values() if trend == "DOWN")
            if mtf_trends:
                normalized_mtf_score = (mtf_buy_score + mtf_sell_score) / len(mtf_trends)
                signal_score += weights.get("mtf_trend_confluence", 0.0) * normalized_mtf_score
                self.logger.debug(f"MTF Confluence: Score {normalized_mtf_score:.2f}")

        # --- Final Signal Determination ---
        threshold = self.config["signal_score_threshold"]
        final_signal = "HOLD"
        if signal_score >= threshold:
            final_signal = "BUY"
        elif signal_score <= -threshold:
            final_signal = "SELL"

        self.logger.info(f"{NEON_YELLOW}Raw Technical Signal Score: {signal_score:.2f}, Final Technical Signal: {final_signal}{RESET}")
        return final_signal, signal_score

    # --- Indicator Implementation Details (Simplified/Corrected) ---
    def calculate_true_range(self) -> pd.Series:
        """Calculate True Range (TR)."""
        if len(self.df) < MIN_DATA_POINTS_TR: return pd.Series(np.nan, index=self.df.index)
        high_low = self.df["high"] - self.df["low"]
        high_prev_close = (self.df["high"] - self.df["close"].shift()).abs()
        low_prev_close = (self.df["low"] - self.df["close"].shift()).abs()
        return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)

    def calculate_super_smoother(self, series: pd.Series, period: int) -> pd.Series:
        """Apply Ehlers SuperSmoother filter to reduce lag and noise."""
        if period <= 0 or len(series) < MIN_DATA_POINTS_SMOOTHER: return pd.Series(np.nan, index=series.index)
        series = pd.to_numeric(series, errors="coerce").dropna()
        if len(series) < MIN_DATA_POINTS_SMOOTHER: return pd.Series(np.nan, index=series.index)

        a1 = np.exp(-np.sqrt(2) * np.pi / period)
        b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / period)
        c1 = 1 - b1 + a1**2
        c2 = b1 - 2 * a1**2
        c3 = a1**2

        filt = pd.Series(0.0, index=series.index)
        if len(series) >= 1: filt.iloc = series.iloc
        if len(series) >= 2: filt.iloc = (series.iloc + series.iloc) / 2

        for i in range(2, len(series)):
            filt.iloc[i] = ((c1 / 2) * (series.iloc[i] + series.iloc[i - 1])) + (c2 * filt.iloc[i - 1]) - (c3 * filt.iloc[i - 2])
        return filt.reindex(self.df.index)

    def calculate_ehlers_supertrend(self, period: int, multiplier: float) -> Optional[pd.DataFrame]:
        """Calculate SuperTrend using Ehlers SuperSmoother for price and volatility."""
        if len(self.df) < period * 3: return None
        df_copy = self.df.copy()
        hl2 = (df_copy["high"] + df_copy["low"]) / 2
        smoothed_price = self.calculate_super_smoother(hl2, period)
        tr = self.calculate_true_range()
        smoothed_atr = self.calculate_super_smoother(tr, period)

        if smoothed_price is None or smoothed_atr is None: return None

        df_copy["smoothed_price"] = smoothed_price
        df_copy["smoothed_atr"] = smoothed_atr
        df_copy.dropna(subset=["smoothed_price", "smoothed_atr"], inplace=True)
        if df_copy.empty: return None

        upper_band = df_copy["smoothed_price"] + multiplier * df_copy["smoothed_atr"]
        lower_band = df_copy["smoothed_price"] - multiplier * df_copy["smoothed_atr"]

        direction = pd.Series(0, index=df_copy.index, dtype=int)
        supertrend = pd.Series(np.nan, index=df_copy.index)

        first_valid_idx = df_copy.index
        supertrend.loc[first_valid_idx] = lower_band.loc[first_valid_idx]

        for i in range(1, len(df_copy)):
            current_idx = df_copy.index[i]
            prev_idx = df_copy.index[i - 1]

            prev_direction = direction.loc[prev_idx]
            prev_supertrend = supertrend.loc[prev_idx]
            curr_close = df_copy["close"].loc[current_idx]

            if prev_direction == 1:
                supertrend.loc[current_idx] = max(lower_band.loc[current_idx], prev_supertrend)
                if curr_close < supertrend.loc[current_idx]:
                    direction.loc[current_idx] = -1
                    supertrend.loc[current_idx] = upper_band.loc[current_idx]
                else: direction.loc[current_idx] = 1
            elif prev_direction == -1:
                supertrend.loc[current_idx] = min(upper_band.loc[current_idx], prev_supertrend)
                if curr_close > supertrend.loc[current_idx]:
                    direction.loc[current_idx] = 1
                    supertrend.loc[current_idx] = lower_band.loc[current_idx]
                else: direction.loc[current_idx] = -1
            else:
                if curr_close > lower_band.loc[current_idx]:
                    direction.loc[current_idx] = 1
                    supertrend.loc[current_idx] = lower_band.loc[current_idx]
                else:
                    direction.loc[current_idx] = -1
                    supertrend.loc[current_idx] = upper_band.loc[current_idx]

        result = pd.DataFrame({"supertrend": supertrend, "direction": direction})
        return result.reindex(self.df.index)

    def calculate_macd(self, fast_period: int, slow_period: int, signal_period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Moving Average Convergence Divergence (MACD)."""
        if len(self.df) < slow_period + signal_period:
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        ema_fast = self.df["close"].ewm(span=fast_period, adjust=False).mean()
        ema_slow = self.df["close"].ewm(span=slow_period, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    def calculate_rsi(self, period: int) -> pd.Series:
        """Calculate Relative Strength Index (RSI)."""
        if len(self.df) <= period: return pd.Series(np.nan, index=self.df.index)
        delta = self.df["close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.ewm(span=period, adjust=False, min_periods=period).mean()
        avg_loss = loss.ewm(span=period, adjust=False, min_periods=period).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_stoch_rsi(self, period: int, k_period: int, d_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate Stochastic RSI."""
        if len(self.df) <= period: return pd.Series(np.nan), pd.Series(np.nan)
        rsi = self.calculate_rsi(period)

        lowest_rsi = rsi.rolling(window=period, min_periods=period).min()
        highest_rsi = rsi.rolling(window=period, min_periods=period).max()

        stoch_rsi_k_raw = ((rsi - lowest_rsi) / (highest_rsi - lowest_rsi))
        stoch_rsi_k_raw = stoch_rsi_k_raw.replace([np.inf, -np.inf], np.nan).fillna(0) * 100

        stoch_rsi_k = stoch_rsi_k_raw.rolling(window=k_period, min_periods=k_period).mean()
        stoch_rsi_d = stoch_rsi_k.rolling(window=d_period, min_periods=d_period).mean()

        return stoch_rsi_k, stoch_rsi_d

    def calculate_adx(self, period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Average Directional Index (ADX)."""
        if len(self.df) < period * 2: return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        tr = self.calculate_true_range()
        plus_dm = self.df["high"].diff().clip(lower=0)
        minus_dm = -self.df["low"].diff().clip(lower=0)

        plus_dm_final = plus_dm.copy()
        minus_dm_final = minus_dm.copy()
        condition_plus_wins = (plus_dm_final > minus_dm_final)
        condition_minus_wins = (minus_dm_final > plus_dm_final)

        plus_dm_final[condition_minus_wins] = 0
        minus_dm_final[condition_plus_wins] = 0

        atr = tr.ewm(span=period, adjust=False).mean()
        plus_di = (plus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100
        minus_di = (minus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100

        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)).replace([np.inf, -np.inf], np.nan).fillna(0) * 100
        adx = dx.ewm(span=period, adjust=False).mean()

        return adx, plus_di, minus_di

    def calculate_bollinger_bands(self, period: int, std_dev: float) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands."""
        if len(self.df) < period: return (pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan))
        middle_band = self.df["close"].rolling(window=period, min_periods=period).mean()
        std = self.df["close"].rolling(window=period, min_periods=period).std()
        upper_band = middle_band + (std * std_dev)
        lower_band = middle_band - (std * std_dev)
        return upper_band, middle_band, lower_band

    def calculate_vwap(self) -> pd.Series:
        """Calculate Volume Weighted Average Price (VWAP)."""
        if self.df.empty: return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        cumulative_tp_vol = (typical_price * self.df["volume"]).cumsum()
        cumulative_vol = self.df["volume"].cumsum()
        vwap = cumulative_tp_vol / cumulative_vol
        return vwap

    def calculate_cci(self, period: int) -> pd.Series:
        """Calculate Commodity Channel Index (CCI)."""
        if len(self.df) < period: return pd.Series(np.nan, index=self.df.index)
        tp = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        sma_tp = tp.rolling(window=period, min_periods=period).mean()
        mad = tp.rolling(window=period, min_periods=period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=False)
        cci = (tp - sma_tp) / (0.015 * mad)
        cci = cci.replace([np.inf, -np.inf], np.nan).fillna(0)
        return cci

    def calculate_williams_r(self, period: int) -> pd.Series:
        """Calculate Williams %R."""
        if len(self.df) < period: return pd.Series(np.nan, index=self.df.index)
        highest_high = self.df["high"].rolling(window=period, min_periods=period).max()
        lowest_low = self.df["low"].rolling(window=period, min_periods=period).min()
        wr = -100 * ((highest_high - self.df["close"]) / (highest_high - lowest_low))
        wr = wr.replace([np.inf, -np.inf], np.nan).fillna(-50)
        return wr

    def calculate_ichimoku_cloud(self, tenkan_period: int, kijun_period: int, senkou_span_b_period: int, chikou_span_offset: int) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
        """Calculate Ichimoku Cloud components."""
        if (len(self.df) < max(tenkan_period, kijun_period, senkou_span_b_period) + chikou_span_offset):
            return (pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan))

        tenkan_sen = (self.df["high"].rolling(window=tenkan_period).max() + self.df["low"].rolling(window=tenkan_period).min()) / 2
        kijun_sen = (self.df["high"].rolling(window=kijun_period).max() + self.df["low"].rolling(window=kijun_period).min()) / 2
        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun_period)
        senkou_span_b = ((self.df["high"].rolling(window=senkou_span_b_period).max() + self.df["low"].rolling(window=senkou_span_b_period).min()) / 2).shift(kijun_period)
        chikou_span = self.df["close"].shift(-chikou_span_offset)

        return tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span

    def calculate_mfi(self, period: int) -> pd.Series:
        """Calculate Money Flow Index (MFI)."""
        if len(self.df) <= period: return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        money_flow = typical_price * self.df["volume"]

        positive_flow = pd.Series(0.0, index=self.df.index)
        negative_flow = pd.Series(0.0, index=self.df.index)

        for i in range(1, len(self.df)):
            if typical_price.iloc[i] > typical_price.iloc[i - 1]: positive_flow.iloc[i] = money_flow.iloc[i]
            elif typical_price.iloc[i] < typical_price.iloc[i - 1]: negative_flow.iloc[i] = money_flow.iloc[i]

        positive_mf_sum = positive_flow.rolling(window=period, min_periods=period).sum()
        negative_mf_sum = negative_flow.rolling(window=period, min_periods=period).sum()

        mf_ratio = positive_mf_sum / negative_mf_sum
        mfi = 100 - (100 / (1 + mf_ratio))
        mfi = mfi.replace([np.inf, -np.inf], np.nan).fillna(50)
        return mfi

    def calculate_obv(self, ema_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate On-Balance Volume (OBV) and its EMA."""
        if len(self.df) < MIN_DATA_POINTS_OBV: return pd.Series(np.nan), pd.Series(np.nan)

        obv = pd.Series(0.0, index=self.df.index)
        for i in range(1, len(self.df)):
            if self.df["close"].iloc[i] > self.df["close"].iloc[i - 1]: obv.iloc[i] = obv.iloc[i - 1] + self.df["volume"].iloc[i]
            elif self.df["close"].iloc[i] < self.df["close"].iloc[i - 1]: obv.iloc[i] = obv.iloc[i - 1] - self.df["volume"].iloc[i]
            else: obv.iloc[i] = obv.iloc[i - 1]

        obv_ema = obv.ewm(span=ema_period, adjust=False).mean()
        return obv, obv_ema

    def calculate_cmf(self, period: int) -> pd.Series:
        """Calculate Chaikin Money Flow (CMF)."""
        if len(self.df) < period: return pd.Series(np.nan)

        mfm = ((self.df["close"] - self.df["low"]) - (self.df["high"] - self.df["close"])) / (self.df["high"] - self.df["low"])
        mfm = mfm.replace([np.inf, -np.inf], np.nan).fillna(0)

        mfv = mfm * self.df["volume"]
        cmf = (mfv.rolling(window=period).sum() / self.df["volume"].rolling(window=period).sum())
        cmf = cmf.replace([np.inf, -np.inf], np.nan).fillna(0)

        return cmf

    def calculate_psar(self, acceleration: float, max_acceleration: float) -> tuple[pd.Series, pd.Series]:
        """Calculate Parabolic SAR."""
        if len(self.df) < MIN_DATA_POINTS_PSAR: return pd.Series(np.nan), pd.Series(np.nan)

        psar = self.df["close"].copy()
        bull = pd.Series(True, index=self.df.index)
        af = acceleration
        ep = self.df["low"].iloc if self.df["close"].iloc < self.df["close"].iloc else self.df["high"].iloc

        for i in range(1, len(self.df)):
            if bull.iloc[i - 1]:
                psar.iloc[i] = psar.iloc[i - 1] + af * (ep - psar.iloc[i - 1])
            else:
                psar.iloc[i] = psar.iloc[i - 1] - af * (psar.iloc[i - 1] - ep)

            reverse = False
            if bull.iloc[i - 1] and self.df["low"].iloc[i] < psar.iloc[i]:
                bull.iloc[i] = False; reverse = True
            elif not bull.iloc[i - 1] and self.df["high"].iloc[i] > psar.iloc[i]:
                bull.iloc[i] = True; reverse = True
            else: bull.iloc[i] = bull.iloc[i - 1]

            if reverse:
                af = acceleration
                ep = self.df["high"].iloc[i] if bull.iloc[i] else self.df["low"].iloc[i]
            elif bull.iloc[i]:
                if self.df["high"].iloc[i] > ep: ep = self.df["high"].iloc[i]; af = min(af + acceleration, max_acceleration)
            elif self.df["low"].iloc[i] < ep: ep = self.df["low"].iloc[i]; af = min(af + acceleration, max_acceleration)

            if bull.iloc[i]: psar.iloc[i] = min(psar.iloc[i], self.df["low"].iloc[i], self.df["low"].iloc[i-1])
            else: psar.iloc[i] = max(psar.iloc[i], self.df["high"].iloc[i], self.df["high"].iloc[i-1])

            if bull.iloc[i] and psar.iloc[i] > self.df["low"].iloc[i]: psar.iloc[i] = self.df["low"].iloc[i]
            elif not bull.iloc[i] and psar.iloc[i] < self.df["high"].iloc[i]: psar.iloc[i] = self.df["high"].iloc[i]

        direction = pd.Series(0, index=self.df.index, dtype=int)
        direction[psar < self.df["close"]] = 1
        direction[psar > self.df["close"]] = -1

        return psar, direction

    def calculate_fibonacci_levels(self) -> None:
        """Calculate Fibonacci retracement levels based on a recent high-low swing."""
        window = self.config["indicator_settings"]["fibonacci_window"]
        if len(self.df) < window:
            self.logger.warning(f"{NEON_YELLOW}Not enough data for Fibonacci levels (need {window} bars).{RESET}")
            return

        recent_high = self.df["high"].iloc[-window:].max()
        recent_low = self.df["low"].iloc[-window:].min()
        diff = recent_high - recent_low

        self.fib_levels = {
            "0.0%": Decimal(str(recent_high)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "23.6%": Decimal(str(recent_high - 0.236 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "38.2%": Decimal(str(recent_high - 0.382 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "50.0%": Decimal(str(recent_high - 0.500 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "61.8%": Decimal(str(recent_high - 0.618 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "78.6%": Decimal(str(recent_high - 0.786 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "100.0%": Decimal(str(recent_low)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
        }
        self.logger.debug(f"Calculated Fibonacci levels: {self.fib_levels}")

    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        """Safely retrieve an indicator value."""
        return self.indicator_values.get(key, default)

    def _check_orderbook(self, current_price: Decimal, orderbook_data: dict) -> float:
        """Analyze orderbook imbalance."""
        bids = orderbook_data.get("b", [])
        asks = orderbook_data.get("a", [])

        bid_volume = sum(Decimal(b) for b in bids)
        ask_volume = sum(Decimal(a) for a in asks)

        if bid_volume + ask_volume == 0: return 0.0

        imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
        self.logger.debug(f"Orderbook Imbalance: {imbalance:.4f} (Bids: {bid_volume}, Asks: {ask_volume})")
        return float(imbalance)

    def _get_mtf_trend(self, higher_tf_df: pd.DataFrame, indicator_type: str) -> str:
        """Determine trend from higher timeframe using specified indicator."""
        if higher_tf_df.empty: return "UNKNOWN"

        last_close = higher_tf_df["close"].iloc[-1]
        period = self.config["mtf_analysis"]["trend_period"]

        if indicator_type == "sma":
            if len(higher_tf_df) < period: return "UNKNOWN"
            sma = higher_tf_df["close"].rolling(window=period, min_periods=period).mean().iloc[-1]
            if last_close > sma: return "UP"
            if last_close < sma: return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ema":
            if len(higher_tf_df) < period: return "UNKNOWN"
            ema = higher_tf_df["close"].ewm(span=period, adjust=False, min_periods=period).mean().iloc[-1]
            if last_close > ema: return "UP"
            if last_close < ema: return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ehlers_supertrend":
            temp_analyzer = TradingAnalyzer(higher_tf_df, self.config, self.logger, self.symbol)
            st_result = temp_analyzer.calculate_ehlers_supertrend(
                self.indicator_settings["ehlers_slow_period"],
                self.indicator_settings["ehlers_slow_multiplier"],
            )
            if st_result is not None and not st_result.empty:
                st_dir = st_result["direction"].iloc[-1]
                if st_dir == 1: return "UP"
                if st_dir == -1: return "DOWN"
            return "UNKNOWN"
        return "UNKNOWN"

    def generate_trading_signal(
        self, current_price: Decimal, orderbook_data: dict | None, mtf_trends: dict[str, str]
    ) -> tuple[str, float]:
        """Generate a signal using confluence of indicators, including Ehlers SuperTrend."""
        signal_score = 0.0
        active_indicators = self.config["indicators"]
        weights = self.weights

        if self.df.empty:
            self.logger.warning(f"{NEON_YELLOW}DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}")
            return "HOLD", 0.0

        current_close = Decimal(str(self.df["close"].iloc[-1]))
        prev_close = Decimal(str(self.df["close"].iloc[-2])) if len(self.df) > 1 else current_close
        isd = self.indicator_settings

        # --- Indicator Scoring ---
        if active_indicators.get("ema_alignment", False):
            ema_short = self._get_indicator_value("EMA_Short")
            ema_long = self._get_indicator_value("EMA_Long")
            if not pd.isna(ema_short) and not pd.isna(ema_long):
                if ema_short > ema_long: signal_score += weights.get("ema_alignment", 0)
                elif ema_short < ema_long: signal_score -= weights.get("ema_alignment", 0)

        if active_indicators.get("sma_trend_filter", False):
            sma_long = self._get_indicator_value("SMA_Long")
            if not pd.isna(sma_long):
                if current_close > sma_long: signal_score += weights.get("sma_trend_filter", 0)
                elif current_close < sma_long: signal_score -= weights.get("sma_trend_filter", 0)

        if active_indicators.get("momentum", False):
            rsi = self._get_indicator_value("RSI")
            stoch_k = self._get_indicator_value("StochRSI_K")
            stoch_d = self._get_indicator_value("StochRSI_D")
            cci = self._get_indicator_value("CCI")
            wr = self._get_indicator_value("WR")
            mfi = self._get_indicator_value("MFI")

            if not pd.isna(rsi):
                if rsi < isd["rsi_oversold"]: signal_score += weights.get("rsi", 0) * 0.5
                elif rsi > isd["rsi_overbought"]: signal_score -= weights.get("rsi", 0) * 0.5

            if not pd.isna(stoch_k) and not pd.isna(stoch_d):
                if stoch_k > stoch_d and stoch_k < isd["stoch_rsi_oversold"]: signal_score += weights.get("stoch_rsi", 0) * 0.5
                elif stoch_k < stoch_d and stoch_k > isd["stoch_rsi_overbought"]: signal_score -= weights.get("stoch_rsi", 0) * 0.5

            if not pd.isna(cci):
                if cci < isd["cci_oversold"]: signal_score += weights.get("cci", 0) * 0.5
                elif cci > isd["cci_overbought"]: signal_score -= weights.get("cci", 0) * 0.5

            if not pd.isna(wr):
                if wr < isd["williams_r_oversold"]: signal_score += weights.get("wr", 0) * 0.5
                elif wr > isd["williams_r_overbought"]: signal_score -= weights.get("wr", 0) * 0.5

            if not pd.isna(mfi):
                if mfi < isd["mfi_oversold"]: signal_score += weights.get("mfi", 0) * 0.5
                elif mfi > isd["mfi_overbought"]: signal_score -= weights.get("mfi", 0) * 0.5

        if active_indicators.get("bollinger_bands", False):
            bb_upper = self._get_indicator_value("BB_Upper")
            bb_lower = self._get_indicator_value("BB_Lower")
            if not pd.isna(bb_upper) and not pd.isna(bb_lower):
                if current_close < bb_lower: signal_score += weights.get("bollinger_bands", 0) * 0.5
                elif current_close > bb_upper: signal_score -= weights.get("bollinger_bands", 0) * 0.5

        if active_indicators.get("vwap", False):
            vwap = self._get_indicator_value("VWAP")
            if not pd.isna(vwap):
                if current_close > vwap: signal_score += weights.get("vwap", 0) * 0.2
                elif current_close < vwap: signal_score -= weights.get("vwap", 0) * 0.2

                if len(self.df) > 1:
                    prev_close = Decimal(str(self.df["close"].iloc[-2]))
                    prev_vwap = Decimal(str(self.df["VWAP"].iloc[-2]))
                    if current_close > vwap and prev_close <= prev_vwap: signal_score += weights.get("vwap", 0) * 0.3
                    elif current_close < vwap and prev_close >= prev_vwap: signal_score -= weights.get("vwap", 0) * 0.3

        if active_indicators.get("psar", False):
            psar_val = self._get_indicator_value("PSAR_Val")
            psar_dir = self._get_indicator_value("PSAR_Dir")
            if not pd.isna(psar_val) and not pd.isna(psar_dir):
                if psar_dir == 1: signal_score += weights.get("psar", 0) * 0.5
                elif psar_dir == -1: signal_score -= weights.get("psar", 0) * 0.5

                if len(self.df) > 1:
                    prev_close = Decimal(str(self.df["close"].iloc[-2]))
                    prev_psar_val = Decimal(str(self.df["PSAR_Val"].iloc[-2]))
                    if current_close > psar_val and prev_close <= prev_psar_val: signal_score += weights.get("psar", 0) * 0.4
                    elif current_close < psar_val and prev_close >= prev_psar_val: signal_score -= weights.get("psar", 0) * 0.4

        if active_indicators.get("orderbook_imbalance", False) and orderbook_data:
            imbalance = self._check_orderbook(current_price, orderbook_data)
            signal_score += imbalance * weights.get("orderbook_imbalance", 0)

        if active_indicators.get("fibonacci_levels", False) and self.fib_levels:
            for level_name, level_price in self.fib_levels.items():
                if level_name not in ["0.0%", "100.0%"] and abs(current_price - level_price) / current_price < Decimal("0.001"):
                    if len(self.df) > 1:
                        prev_close = Decimal(str(self.df["close"].iloc[-2]))
                        if current_close > prev_close and current_close > level_price: signal_score += weights.get("fibonacci_levels", 0) * 0.1
                        elif current_close < prev_close and current_close < level_price: signal_score -= weights.get("fibonacci_levels", 0) * 0.1

        if active_indicators.get("ehlers_supertrend", False):
            st_fast_dir = self._get_indicator_value("ST_Fast_Dir")
            st_slow_dir = self._get_indicator_value("ST_Slow_Dir")
            prev_st_fast_dir = self.df["st_fast_dir"].iloc[-2] if "st_fast_dir" in self.df.columns and len(self.df) > 1 else np.nan
            weight = weights.get("ehlers_supertrend_alignment", 0.0)

            if not pd.isna(st_fast_dir) and not pd.isna(st_slow_dir) and not pd.isna(prev_st_fast_dir):
                if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1: signal_score += weight
                elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1: signal_score -= weight
                elif st_slow_dir == 1 and st_fast_dir == 1: signal_score += weight * 0.3
                elif st_slow_dir == -1 and st_fast_dir == -1: signal_score -= weight * 0.3

        if active_indicators.get("macd", False):
            macd_line = self._get_indicator_value("MACD_Line")
            signal_line = self._get_indicator_value("MACD_Signal")
            histogram = self._get_indicator_value("MACD_Hist")
            weight = weights.get("macd_alignment", 0.0)

            if not pd.isna(macd_line) and not pd.isna(signal_line) and not pd.isna(histogram):
                if len(self.df) > 1:
                    prev_macd_line = Decimal(str(self.df["MACD_Line"].iloc[-2]))
                    prev_signal_line = Decimal(str(self.df["MACD_Signal"].iloc[-2]))
                    if macd_line > signal_line and prev_macd_line <= prev_signal_line: signal_score += weight
                    elif macd_line < signal_line and prev_macd_line >= prev_signal_line: signal_score -= weight
                if len(self.df) > 1 and histogram > 0 and self.df["MACD_Hist"].iloc[-2] < 0: signal_score += weight * 0.2
                elif len(self.df) > 1 and histogram < 0 and self.df["MACD_Hist"].iloc[-2] > 0: signal_score -= weight * 0.2

        if active_indicators.get("adx", False):
            adx_val = self._get_indicator_value("ADX")
            plus_di = self._get_indicator_value("PlusDI")
            minus_di = self._get_indicator_value("MinusDI")
            weight = weights.get("adx_strength", 0.0)

            if not pd.isna(adx_val) and not pd.isna(plus_di) and not pd.isna(minus_di):
                if adx_val > ADX_STRONG_TREND_THRESHOLD:
                    if plus_di > minus_di: signal_score += weight
                    elif minus_di > plus_di: signal_score -= weight
                elif adx_val < ADX_WEAK_TREND_THRESHOLD: pass

        if active_indicators.get("ichimoku_cloud", False):
            tenkan_sen = self._get_indicator_value("Tenkan_Sen")
            kijun_sen = self._get_indicator_value("Kijun_Sen")
            senkou_span_a = self._get_indicator_value("Senkou_Span_A")
            senkou_span_b = self._get_indicator_value("Senkou_Span_B")
            chikou_span = self._get_indicator_value("Chikou_Span")
            weight = weights.get("ichimoku_confluence", 0.0)

            if not pd.isna(tenkan_sen) and not pd.isna(kijun_sen) and not pd.isna(senkou_span_a) and not pd.isna(senkou_span_b) and not pd.isna(chikou_span):
                if tenkan_sen > kijun_sen and self.df["Tenkan_Sen"].iloc[-2] <= self.df["Kijun_Sen"].iloc[-2]: signal_score += weight * 0.5
                elif tenkan_sen < kijun_sen and self.df["Tenkan_Sen"].iloc[-2] >= self.df["Kijun_Sen"].iloc[-2]: signal_score -= weight * 0.5

                if current_close > max(senkou_span_a, senkou_span_b) and self.df["close"].iloc[-2] <= max(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]): signal_score += weight * 0.7
                elif current_close < min(senkou_span_a, senkou_span_b) and self.df["close"].iloc[-2] >= min(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]): signal_score -= weight * 0.7

                if chikou_span > current_close and self.df["Chikou_Span"].iloc[-2] <= self.df["close"].iloc[-2]: signal_score += weight * 0.3
                elif chikou_span < current_close and self.df["Chikou_Span"].iloc[-2] >= self.df["close"].iloc[-2]: signal_score -= weight * 0.3

        if active_indicators.get("obv", False):
            obv_val = self._get_indicator_value("OBV")
            obv_ema = self._get_indicator_value("OBV_EMA")
            weight = weights.get("obv_momentum", 0.0)
            if not pd.isna(obv_val) and not pd.isna(obv_ema):
                if obv_val > obv_ema and self.df["OBV"].iloc[-2] <= self.df["OBV_EMA"].iloc[-2]: signal_score += weight * 0.5
                elif obv_val < obv_ema and self.df["OBV"].iloc[-2] >= self.df["OBV_EMA"].iloc[-2]: signal_score -= weight * 0.5
                if len(self.df) > 2:
                    if obv_val > self.df["OBV"].iloc[-2] and obv_val > self.df["OBV"].iloc[-3]: signal_score += weight * 0.2
                    elif obv_val < self.df["OBV"].iloc[-2] and obv_val < self.df["OBV"].iloc[-3]: signal_score -= weight * 0.2

        if active_indicators.get("cmf", False):
            cmf_val = self._get_indicator_value("CMF")
            weight = weights.get("cmf_flow", 0.0)
            if not pd.isna(cmf_val):
                if cmf_val > 0: signal_score += weight * 0.5
                elif cmf_val < 0: signal_score -= weight * 0.5
                if len(self.df) > 2:
                    if cmf_val > self.df["CMF"].iloc[-2] and cmf_val > self.df["CMF"].iloc[-3]: signal_score += weight * 0.3
                    elif cmf_val < self.df["CMF"].iloc[-2] and cmf_val < self.df["CMF"].iloc[-3]: signal_score -= weight * 0.3

        if self.config["mtf_analysis"]["enabled"] and mtf_trends:
            mtf_buy_score = sum(1 for trend in mtf_trends.values() if trend == "UP")
            mtf_sell_score = sum(-1 for trend in mtf_trends.values() if trend == "DOWN")
            if mtf_trends:
                normalized_mtf_score = (mtf_buy_score + mtf_sell_score) / len(mtf_trends)
                signal_score += weights.get("mtf_trend_confluence", 0.0) * normalized_mtf_score
                self.logger.debug(f"MTF Confluence: Score {normalized_mtf_score:.2f}")

        threshold = self.config["signal_score_threshold"]
        final_signal = "HOLD"
        if signal_score >= threshold: final_signal = "BUY"
        elif signal_score <= -threshold: final_signal = "SELL"

        self.logger.info(f"{NEON_YELLOW}Raw Technical Signal Score: {signal_score:.2f}, Final Technical Signal: {final_signal}{RESET}")
        return final_signal, signal_score

    # --- Remaining Indicator Implementations (Simplified for brevity, assuming they follow similar structure) ---
    def calculate_true_range(self) -> pd.Series:
        """Calculate True Range (TR)."""
        if len(self.df) < MIN_DATA_POINTS_TR: return pd.Series(np.nan, index=self.df.index)
        high_low = self.df["high"] - self.df["low"]
        high_prev_close = (self.df["high"] - self.df["close"].shift()).abs()
        low_prev_close = (self.df["low"] - self.df["close"].shift()).abs()
        return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)

    def calculate_super_smoother(self, series: pd.Series, period: int) -> pd.Series:
        """Apply Ehlers SuperSmoother filter to reduce lag and noise."""
        if period <= 0 or len(series) < MIN_DATA_POINTS_SMOOTHER: return pd.Series(np.nan, index=series.index)
        series = pd.to_numeric(series, errors="coerce").dropna()
        if len(series) < MIN_DATA_POINTS_SMOOTHER: return pd.Series(np.nan, index=series.index)

        a1 = np.exp(-np.sqrt(2) * np.pi / period)
        b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / period)
        c1 = 1 - b1 + a1**2
        c2 = b1 - 2 * a1**2
        c3 = a1**2

        filt = pd.Series(0.0, index=series.index)
        if len(series) >= 1: filt.iloc = series.iloc
        if len(series) >= 2: filt.iloc = (series.iloc + series.iloc) / 2

        for i in range(2, len(series)):
            filt.iloc[i] = ((c1 / 2) * (series.iloc[i] + series.iloc[i - 1])) + (c2 * filt.iloc[i - 1]) - (c3 * filt.iloc[i - 2])
        return filt.reindex(self.df.index)

    def calculate_ehlers_supertrend(self, period: int, multiplier: float) -> Optional[pd.DataFrame]:
        """Calculate SuperTrend using Ehlers SuperSmoother for price and volatility."""
        if len(self.df) < period * 3: return None
        df_copy = self.df.copy()
        hl2 = (df_copy["high"] + df_copy["low"]) / 2
        smoothed_price = self.calculate_super_smoother(hl2, period)
        tr = self.calculate_true_range()
        smoothed_atr = self.calculate_super_smoother(tr, period)

        if smoothed_price is None or smoothed_atr is None: return None

        df_copy["smoothed_price"] = smoothed_price
        df_copy["smoothed_atr"] = smoothed_atr
        df_copy.dropna(subset=["smoothed_price", "smoothed_atr"], inplace=True)
        if df_copy.empty: return None

        upper_band = df_copy["smoothed_price"] + multiplier * df_copy["smoothed_atr"]
        lower_band = df_copy["smoothed_price"] - multiplier * df_copy["smoothed_atr"]

        direction = pd.Series(0, index=df_copy.index, dtype=int)
        supertrend = pd.Series(np.nan, index=df_copy.index)

        first_valid_idx = df_copy.index
        supertrend.loc[first_valid_idx] = lower_band.loc[first_valid_idx]

        for i in range(1, len(df_copy)):
            current_idx = df_copy.index[i]
            prev_idx = df_copy.index[i - 1]

            prev_direction = direction.loc[prev_idx]
            prev_supertrend = supertrend.loc[prev_idx]
            curr_close = df_copy["close"].loc[current_idx]

            if prev_direction == 1:
                supertrend.loc[current_idx] = max(lower_band.loc[current_idx], prev_supertrend)
                if curr_close < supertrend.loc[current_idx]:
                    direction.loc[current_idx] = -1
                    supertrend.loc[current_idx] = upper_band.loc[current_idx]
                else: direction.loc[current_idx] = 1
            elif prev_direction == -1:
                supertrend.loc[current_idx] = min(upper_band.loc[current_idx], prev_supertrend)
                if curr_close > supertrend.loc[current_idx]:
                    direction.loc[current_idx] = 1
                    supertrend.loc[current_idx] = lower_band.loc[current_idx]
                else: direction.loc[current_idx] = -1
            else:
                if curr_close > lower_band.loc[current_idx]:
                    direction.loc[current_idx] = 1
                    supertrend.loc[current_idx] = lower_band.loc[current_idx]
                else:
                    direction.loc[current_idx] = -1
                    supertrend.loc[current_idx] = upper_band.loc[current_idx]

        result = pd.DataFrame({"supertrend": supertrend, "direction": direction})
        return result.reindex(self.df.index)

    def calculate_macd(self, fast_period: int, slow_period: int, signal_period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Moving Average Convergence Divergence (MACD)."""
        if len(self.df) < slow_period + signal_period:
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        ema_fast = self.df["close"].ewm(span=fast_period, adjust=False).mean()
        ema_slow = self.df["close"].ewm(span=slow_period, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    def calculate_rsi(self, period: int) -> pd.Series:
        """Calculate Relative Strength Index (RSI)."""
        if len(self.df) <= period: return pd.Series(np.nan, index=self.df.index)
        delta = self.df["close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.ewm(span=period, adjust=False, min_periods=period).mean()
        avg_loss = loss.ewm(span=period, adjust=False, min_periods=period).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_stoch_rsi(self, period: int, k_period: int, d_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate Stochastic RSI."""
        if len(self.df) <= period: return pd.Series(np.nan), pd.Series(np.nan)
        rsi = self.calculate_rsi(period)

        lowest_rsi = rsi.rolling(window=period, min_periods=period).min()
        highest_rsi = rsi.rolling(window=period, min_periods=period).max()

        stoch_rsi_k_raw = ((rsi - lowest_rsi) / (highest_rsi - lowest_rsi))
        stoch_rsi_k_raw = stoch_rsi_k_raw.replace([np.inf, -np.inf], np.nan).fillna(0) * 100

        stoch_rsi_k = stoch_rsi_k_raw.rolling(window=k_period, min_periods=k_period).mean()
        stoch_rsi_d = stoch_rsi_k.rolling(window=d_period, min_periods=d_period).mean()

        return stoch_rsi_k, stoch_rsi_d

    def calculate_adx(self, period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Average Directional Index (ADX)."""
        if len(self.df) < period * 2: return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        tr = self.calculate_true_range()
        plus_dm = self.df["high"].diff().clip(lower=0)
        minus_dm = -self.df["low"].diff().clip(lower=0)

        plus_dm_final = plus_dm.copy()
        minus_dm_final = minus_dm.copy()
        condition_plus_wins = (plus_dm_final > minus_dm_final)
        condition_minus_wins = (minus_dm_final > plus_dm_final)

        plus_dm_final[condition_minus_wins] = 0
        minus_dm_final[condition_plus_wins] = 0

        atr = tr.ewm(span=period, adjust=False).mean()
        plus_di = (plus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100
        minus_di = (minus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100

        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)).replace([np.inf, -np.inf], np.nan).fillna(0) * 100
        adx = dx.ewm(span=period, adjust=False).mean()

        return adx, plus_di, minus_di

    def calculate_bollinger_bands(self, period: int, std_dev: float) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands."""
        if len(self.df) < period: return (pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan))
        middle_band = self.df["close"].rolling(window=period, min_periods=period).mean()
        std = self.df["close"].rolling(window=period, min_periods=period).std()
        upper_band = middle_band + (std * std_dev)
        lower_band = middle_band - (std * std_dev)
        return upper_band, middle_band, lower_band

    def calculate_vwap(self) -> pd.Series:
        """Calculate Volume Weighted Average Price (VWAP)."""
        if self.df.empty: return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        cumulative_tp_vol = (typical_price * self.df["volume"]).cumsum()
        cumulative_vol = self.df["volume"].cumsum()
        vwap = cumulative_tp_vol / cumulative_vol
        return vwap

    def calculate_cci(self, period: int) -> pd.Series:
        """Calculate Commodity Channel Index (CCI)."""
        if len(self.df) < period: return pd.Series(np.nan, index=self.df.index)
        tp = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        sma_tp = tp.rolling(window=period, min_periods=period).mean()
        mad = tp.rolling(window=period, min_periods=period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=False)
        cci = (tp - sma_tp) / (0.015 * mad)
        cci = cci.replace([np.inf, -np.inf], np.nan).fillna(0)
        return cci

    def calculate_williams_r(self, period: int) -> pd.Series:
        """Calculate Williams %R."""
        if len(self.df) < period: return pd.Series(np.nan, index=self.df.index)
        highest_high = self.df["high"].rolling(window=period, min_periods=period).max()
        lowest_low = self.df["low"].rolling(window=period, min_periods=period).min()
        wr = -100 * ((highest_high - self.df["close"]) / (highest_high - lowest_low))
        wr = wr.replace([np.inf, -np.inf], np.nan).fillna(-50)
        return wr

    def calculate_ichimoku_cloud(self, tenkan_period: int, kijun_period: int, senkou_span_b_period: int, chikou_span_offset: int) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
        """Calculate Ichimoku Cloud components."""
        if (len(self.df) < max(tenkan_period, kijun_period, senkou_span_b_period) + chikou_span_offset):
            return (pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan))

        tenkan_sen = (self.df["high"].rolling(window=tenkan_period).max() + self.df["low"].rolling(window=tenkan_period).min()) / 2
        kijun_sen = (self.df["high"].rolling(window=kijun_period).max() + self.df["low"].rolling(window=kijun_period).min()) / 2
        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun_period)
        senkou_span_b = ((self.df["high"].rolling(window=senkou_span_b_period).max() + self.df["low"].rolling(window=senkou_span_b_period).min()) / 2).shift(kijun_period)
        chikou_span = self.df["close"].shift(-chikou_span_offset)

        return tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span

    def calculate_mfi(self, period: int) -> pd.Series:
        """Calculate Money Flow Index (MFI)."""
        if len(self.df) <= period: return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        money_flow = typical_price * self.df["volume"]

        positive_flow = pd.Series(0.0, index=self.df.index)
        negative_flow = pd.Series(0.0, index=self.df.index)

        for i in range(1, len(self.df)):
            if typical_price.iloc[i] > typical_price.iloc[i - 1]: positive_flow.iloc[i] = money_flow.iloc[i]
            elif typical_price.iloc[i] < typical_price.iloc[i - 1]: negative_flow.iloc[i] = money_flow.iloc[i]

        positive_mf_sum = positive_flow.rolling(window=period, min_periods=period).sum()
        negative_mf_sum = negative_flow.rolling(window=period, min_periods=period).sum()

        mf_ratio = positive_mf_sum / negative_mf_sum
        mfi = 100 - (100 / (1 + mf_ratio))
        mfi = mfi.replace([np.inf, -np.inf], np.nan).fillna(50)
        return mfi

    def calculate_obv(self, ema_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate On-Balance Volume (OBV) and its EMA."""
        if len(self.df) < MIN_DATA_POINTS_OBV: return pd.Series(np.nan), pd.Series(np.nan)

        obv = pd.Series(0.0, index=self.df.index)
        for i in range(1, len(self.df)):
            if self.df["close"].iloc[i] > self.df["close"].iloc[i - 1]: obv.iloc[i] = obv.iloc[i - 1] + self.df["volume"].iloc[i]
            elif self.df["close"].iloc[i] < self.df["close"].iloc[i - 1]: obv.iloc[i] = obv.iloc[i - 1] - self.df["volume"].iloc[i]
            else: obv.iloc[i] = obv.iloc[i - 1]

        obv_ema = obv.ewm(span=ema_period, adjust=False).mean()
        return obv, obv_ema

    def calculate_cmf(self, period: int) -> pd.Series:
        """Calculate Chaikin Money Flow (CMF)."""
        if len(self.df) < period: return pd.Series(np.nan)

        mfm = ((self.df["close"] - self.df["low"]) - (self.df["high"] - self.df["close"])) / (self.df["high"] - self.df["low"])
        mfm = mfm.replace([np.inf, -np.inf], np.nan).fillna(0)

        mfv = mfm * self.df["volume"]
        cmf = (mfv.rolling(window=period).sum() / self.df["volume"].rolling(window=period).sum())
        cmf = cmf.replace([np.inf, -np.inf], np.nan).fillna(0)

        return cmf

    def calculate_psar(self, acceleration: float, max_acceleration: float) -> tuple[pd.Series, pd.Series]:
        """Calculate Parabolic SAR."""
        if len(self.df) < MIN_DATA_POINTS_PSAR: return pd.Series(np.nan), pd.Series(np.nan)

        psar = self.df["close"].copy()
        bull = pd.Series(True, index=self.df.index)
        af = acceleration
        ep = self.df["low"].iloc if self.df["close"].iloc < self.df["close"].iloc else self.df["high"].iloc

        for i in range(1, len(self.df)):
            if bull.iloc[i - 1]:
                psar.iloc[i] = psar.iloc[i - 1] + af * (ep - psar.iloc[i - 1])
            else:
                psar.iloc[i] = psar.iloc[i - 1] - af * (psar.iloc[i - 1] - ep)

            reverse = False
            if bull.iloc[i - 1] and self.df["low"].iloc[i] < psar.iloc[i]:
                bull.iloc[i] = False; reverse = True
            elif not bull.iloc[i - 1] and self.df["high"].iloc[i] > psar.iloc[i]:
                bull.iloc[i] = True; reverse = True
            else: bull.iloc[i] = bull.iloc[i - 1]

            if reverse:
                af = acceleration
                ep = self.df["high"].iloc[i] if bull.iloc[i] else self.df["low"].iloc[i]
            elif bull.iloc[i]:
                if self.df["high"].iloc[i] > ep: ep = self.df["high"].iloc[i]; af = min(af + acceleration, max_acceleration)
            elif self.df["low"].iloc[i] < ep: ep = self.df["low"].iloc[i]; af = min(af + acceleration, max_acceleration)

            if bull.iloc[i]: psar.iloc[i] = min(psar.iloc[i], self.df["low"].iloc[i], self.df["low"].iloc[i-1])
            else: psar.iloc[i] = max(psar.iloc[i], self.df["high"].iloc[i], self.df["high"].iloc[i-1])

            if bull.iloc[i] and psar.iloc[i] > self.df["low"].iloc[i]: psar.iloc[i] = self.df["low"].iloc[i]
            elif not bull.iloc[i] and psar.iloc[i] < self.df["high"].iloc[i]: psar.iloc[i] = self.df["high"].iloc[i]

        direction = pd.Series(0, index=self.df.index, dtype=int)
        direction[psar < self.df["close"]] = 1
        direction[psar > self.df["close"]] = -1

        return psar, direction

    def calculate_fibonacci_levels(self) -> None:
        """Calculate Fibonacci retracement levels based on a recent high-low swing."""
        window = self.config["indicator_settings"]["fibonacci_window"]
        if len(self.df) < window:
            self.logger.warning(f"{NEON_YELLOW}Not enough data for Fibonacci levels (need {window} bars).{RESET}")
            return

        recent_high = self.df["high"].iloc[-window:].max()
        recent_low = self.df["low"].iloc[-window:].min()
        diff = recent_high - recent_low

        self.fib_levels = {
            "0.0%": Decimal(str(recent_high)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "23.6%": Decimal(str(recent_high - 0.236 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "38.2%": Decimal(str(recent_high - 0.382 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "50.0%": Decimal(str(recent_high - 0.500 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "61.8%": Decimal(str(recent_high - 0.618 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "78.6%": Decimal(str(recent_high - 0.786 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "100.0%": Decimal(str(recent_low)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
        }
        self.logger.debug(f"Calculated Fibonacci levels: {self.fib_levels}")

    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        """Safely retrieve an indicator value."""
        return self.indicator_values.get(key, default)

    def _check_orderbook(self, current_price: Decimal, orderbook_data: dict) -> float:
        """Analyze orderbook imbalance."""
        bids = orderbook_data.get("b", [])
        asks = orderbook_data.get("a", [])

        bid_volume = sum(Decimal(b) for b in bids)
        ask_volume = sum(Decimal(a) for a in asks)

        if bid_volume + ask_volume == 0: return 0.0

        imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
        self.logger.debug(f"Orderbook Imbalance: {imbalance:.4f} (Bids: {bid_volume}, Asks: {ask_volume})")
        return float(imbalance)

    def _get_mtf_trend(self, higher_tf_df: pd.DataFrame, indicator_type: str) -> str:
        """Determine trend from higher timeframe using specified indicator."""
        if higher_tf_df.empty: return "UNKNOWN"

        last_close = higher_tf_df["close"].iloc[-1]
        period = self.config["mtf_analysis"]["trend_period"]

        if indicator_type == "sma":
            if len(higher_tf_df) < period: return "UNKNOWN"
            sma = higher_tf_df["close"].rolling(window=period, min_periods=period).mean().iloc[-1]
            if last_close > sma: return "UP"
            if last_close < sma: return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ema":
            if len(higher_tf_df) < period: return "UNKNOWN"
            ema = higher_tf_df["close"].ewm(span=period, adjust=False, min_periods=period).mean().iloc[-1]
            if last_close > ema: return "UP"
            if last_close < ema: return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ehlers_supertrend":
            temp_analyzer = TradingAnalyzer(higher_tf_df, self.config, self.logger, self.symbol)
            st_result = temp_analyzer.calculate_ehlers_supertrend(
                self.indicator_settings["ehlers_slow_period"],
                self.indicator_settings["ehlers_slow_multiplier"],
            )
            if st_result is not None and not st_result.empty:
                st_dir = st_result["direction"].iloc[-1]
                if st_dir == 1: return "UP"
                if st_dir == -1: return "DOWN"
            return "UNKNOWN"
        return "UNKNOWN"

    def generate_trading_signal(
        self, current_price: Decimal, orderbook_data: dict | None, mtf_trends: dict[str, str]
    ) -> tuple[str, float]:
        """Generate a signal using confluence of indicators, including Ehlers SuperTrend."""
        signal_score = 0.0
        active_indicators = self.config["indicators"]
        weights = self.weights

        if self.df.empty:
            self.logger.warning(f"{NEON_YELLOW}DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}")
            return "HOLD", 0.0

        current_close = Decimal(str(self.df["close"].iloc[-1]))
        prev_close = Decimal(str(self.df["close"].iloc[-2])) if len(self.df) > 1 else current_close
        isd = self.indicator_settings

        # --- Indicator Scoring ---
        if active_indicators.get("ema_alignment", False):
            ema_short = self._get_indicator_value("EMA_Short")
            ema_long = self._get_indicator_value("EMA_Long")
            if not pd.isna(ema_short) and not pd.isna(ema_long):
                if ema_short > ema_long: signal_score += weights.get("ema_alignment", 0)
                elif ema_short < ema_long: signal_score -= weights.get("ema_alignment", 0)

        if active_indicators.get("sma_trend_filter", False):
            sma_long = self._get_indicator_value("SMA_Long")
            if not pd.isna(sma_long):
                if current_close > sma_long: signal_score += weights.get("sma_trend_filter", 0)
                elif current_close < sma_long: signal_score -= weights.get("sma_trend_filter", 0)

        if active_indicators.get("momentum", False):
            rsi = self._get_indicator_value("RSI")
            stoch_k = self._get_indicator_value("StochRSI_K")
            stoch_d = self._get_indicator_value("StochRSI_D")
            cci = self._get_indicator_value("CCI")
            wr = self._get_indicator_value("WR")
            mfi = self._get_indicator_value("MFI")

            if not pd.isna(rsi):
                if rsi < isd["rsi_oversold"]: signal_score += weights.get("rsi", 0) * 0.5
                elif rsi > isd["rsi_overbought"]: signal_score -= weights.get("rsi", 0) * 0.5

            if not pd.isna(stoch_k) and not pd.isna(stoch_d):
                if stoch_k > stoch_d and stoch_k < isd["stoch_rsi_oversold"]: signal_score += weights.get("stoch_rsi", 0) * 0.5
                elif stoch_k < stoch_d and stoch_k > isd["stoch_rsi_overbought"]: signal_score -= weights.get("stoch_rsi", 0) * 0.5

            if not pd.isna(cci):
                if cci < isd["cci_oversold"]: signal_score += weights.get("cci", 0) * 0.5
                elif cci > isd["cci_overbought"]: signal_score -= weights.get("cci", 0) * 0.5

            if not pd.isna(wr):
                if wr < isd["williams_r_oversold"]: signal_score += weights.get("wr", 0) * 0.5
                elif wr > isd["williams_r_overbought"]: signal_score -= weights.get("wr", 0) * 0.5

            if not pd.isna(mfi):
                if mfi < isd["mfi_oversold"]: signal_score += weights.get("mfi", 0) * 0.5
                elif mfi > isd["mfi_overbought"]: signal_score -= weights.get("mfi", 0) * 0.5

        if active_indicators.get("bollinger_bands", False):
            bb_upper = self._get_indicator_value("BB_Upper")
            bb_lower = self._get_indicator_value("BB_Lower")
            if not pd.isna(bb_upper) and not pd.isna(bb_lower):
                if current_close < bb_lower: signal_score += weights.get("bollinger_bands", 0) * 0.5
                elif current_close > bb_upper: signal_score -= weights.get("bollinger_bands", 0) * 0.5

        if active_indicators.get("vwap", False):
            vwap = self._get_indicator_value("VWAP")
            if not pd.isna(vwap):
                if current_close > vwap: signal_score += weights.get("vwap", 0) * 0.2
                elif current_close < vwap: signal_score -= weights.get("vwap", 0) * 0.2

                if len(self.df) > 1:
                    prev_close = Decimal(str(self.df["close"].iloc[-2]))
                    prev_vwap = Decimal(str(self.df["VWAP"].iloc[-2]))
                    if current_close > vwap and prev_close <= prev_vwap: signal_score += weights.get("vwap", 0) * 0.3
                    elif current_close < vwap and prev_close >= prev_vwap: signal_score -= weights.get("vwap", 0) * 0.3

        if active_indicators.get("psar", False):
            psar_val = self._get_indicator_value("PSAR_Val")
            psar_dir = self._get_indicator_value("PSAR_Dir")
            if not pd.isna(psar_val) and not pd.isna(psar_dir):
                if psar_dir == 1: signal_score += weights.get("psar", 0) * 0.5
                elif psar_dir == -1: signal_score -= weights.get("psar", 0) * 0.5

                if len(self.df) > 1:
                    prev_close = Decimal(str(self.df["close"].iloc[-2]))
                    prev_psar_val = Decimal(str(self.df["PSAR_Val"].iloc[-2]))
                    if current_close > psar_val and prev_close <= prev_psar_val: signal_score += weights.get("psar", 0) * 0.4
                    elif current_close < psar_val and prev_close >= prev_psar_val: signal_score -= weights.get("psar", 0) * 0.4

        if active_indicators.get("orderbook_imbalance", False) and orderbook_data:
            imbalance = self._check_orderbook(current_price, orderbook_data)
            signal_score += imbalance * weights.get("orderbook_imbalance", 0)

        if active_indicators.get("fibonacci_levels", False) and self.fib_levels:
            for level_name, level_price in self.fib_levels.items():
                if level_name not in ["0.0%", "100.0%"] and abs(current_price - level_price) / current_price < Decimal("0.001"):
                    if len(self.df) > 1:
                        prev_close = Decimal(str(self.df["close"].iloc[-2]))
                        if current_close > prev_close and current_close > level_price: signal_score += weights.get("fibonacci_levels", 0) * 0.1
                        elif current_close < prev_close and current_close < level_price: signal_score -= weights.get("fibonacci_levels", 0) * 0.1

        if active_indicators.get("ehlers_supertrend", False):
            st_fast_dir = self._get_indicator_value("ST_Fast_Dir")
            st_slow_dir = self._get_indicator_value("ST_Slow_Dir")
            prev_st_fast_dir = self.df["st_fast_dir"].iloc[-2] if "st_fast_dir" in self.df.columns and len(self.df) > 1 else np.nan
            weight = weights.get("ehlers_supertrend_alignment", 0.0)

            if not pd.isna(st_fast_dir) and not pd.isna(st_slow_dir) and not pd.isna(prev_st_fast_dir):
                if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1: signal_score += weight
                elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1: signal_score -= weight
                elif st_slow_dir == 1 and st_fast_dir == 1: signal_score += weight * 0.3
                elif st_slow_dir == -1 and st_fast_dir == -1: signal_score -= weight * 0.3

        if active_indicators.get("macd", False):
            macd_line = self._get_indicator_value("MACD_Line")
            signal_line = self._get_indicator_value("MACD_Signal")
            histogram = self._get_indicator_value("MACD_Hist")
            weight = weights.get("macd_alignment", 0.0)

            if not pd.isna(macd_line) and not pd.isna(signal_line) and not pd.isna(histogram):
                if len(self.df) > 1:
                    prev_macd_line = Decimal(str(self.df["MACD_Line"].iloc[-2]))
                    prev_signal_line = Decimal(str(self.df["MACD_Signal"].iloc[-2]))
                    if macd_line > signal_line and prev_macd_line <= prev_signal_line: signal_score += weight
                    elif macd_line < signal_line and prev_macd_line >= prev_signal_line: signal_score -= weight
                if len(self.df) > 1 and histogram > 0 and self.df["MACD_Hist"].iloc[-2] < 0: signal_score += weight * 0.2
                elif len(self.df) > 1 and histogram < 0 and self.df["MACD_Hist"].iloc[-2] > 0: signal_score -= weight * 0.2

        if active_indicators.get("adx", False):
            adx_val = self._get_indicator_value("ADX")
            plus_di = self._get_indicator_value("PlusDI")
            minus_di = self._get_indicator_value("MinusDI")
            weight = weights.get("adx_strength", 0.0)

            if not pd.isna(adx_val) and not pd.isna(plus_di) and not pd.isna(minus_di):
                if adx_val > ADX_STRONG_TREND_THRESHOLD:
                    if plus_di > minus_di: signal_score += weight
                    elif minus_di > plus_di: signal_score -= weight
                elif adx_val < ADX_WEAK_TREND_THRESHOLD: pass

        if active_indicators.get("ichimoku_cloud", False):
            tenkan_sen = self._get_indicator_value("Tenkan_Sen")
            kijun_sen = self._get_indicator_value("Kijun_Sen")
            senkou_span_a = self._get_indicator_value("Senkou_Span_A")
            senkou_span_b = self._get_indicator_value("Senkou_Span_B")
            chikou_span = self._get_indicator_value("Chikou_Span")
            weight = weights.get("ichimoku_confluence", 0.0)

            if not pd.isna(tenkan_sen) and not pd.isna(kijun_sen) and not pd.isna(senkou_span_a) and not pd.isna(senkou_span_b) and not pd.isna(chikou_span):
                if tenkan_sen > kijun_sen and self.df["Tenkan_Sen"].iloc[-2] <= self.df["Kijun_Sen"].iloc[-2]: signal_score += weight * 0.5
                elif tenkan_sen < kijun_sen and self.df["Tenkan_Sen"].iloc[-2] >= self.df["Kijun_Sen"].iloc[-2]: signal_score -= weight * 0.5

                if current_close > max(senkou_span_a, senkou_span_b) and self.df["close"].iloc[-2] <= max(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]): signal_score += weight * 0.7
                elif current_close < min(senkou_span_a, senkou_span_b) and self.df["close"].iloc[-2] >= min(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]): signal_score -= weight * 0.7

                if chikou_span > current_close and self.df["Chikou_Span"].iloc[-2] <= self.df["close"].iloc[-2]: signal_score += weight * 0.3
                elif chikou_span < current_close and self.df["Chikou_Span"].iloc[-2] >= self.df["close"].iloc[-2]: signal_score -= weight * 0.3

        if active_indicators.get("obv", False):
            obv_val = self._get_indicator_value("OBV")
            obv_ema = self._get_indicator_value("OBV_EMA")
            weight = weights.get("obv_momentum", 0.0)
            if not pd.isna(obv_val) and not pd.isna(obv_ema):
                if obv_val > obv_ema and self.df["OBV"].iloc[-2] <= self.df["OBV_EMA"].iloc[-2]: signal_score += weight * 0.5
                elif obv_val < obv_ema and self.df["OBV"].iloc[-2] >= self.df["OBV_EMA"].iloc[-2]: signal_score -= weight * 0.5
                if len(self.df) > 2:
                    if obv_val > self.df["OBV"].iloc[-2] and obv_val > self.df["OBV"].iloc[-3]: signal_score += weight * 0.2
                    elif obv_val < self.df["OBV"].iloc[-2] and obv_val < self.df["OBV"].iloc[-3]: signal_score -= weight * 0.2

        if active_indicators.get("cmf", False):
            cmf_val = self._get_indicator_value("CMF")
            weight = weights.get("cmf_flow", 0.0)
            if not pd.isna(cmf_val):
                if cmf_val > 0: signal_score += weight * 0.5
                elif cmf_val < 0: signal_score -= weight * 0.5
                if len(self.df) > 2:
                    if cmf_val > self.df["CMF"].iloc[-2] and cmf_val > self.df["CMF"].iloc[-3]: signal_score += weight * 0.3
                    elif cmf_val < self.df["CMF"].iloc[-2] and cmf_val < self.df["CMF"].iloc[-3]: signal_score -= weight * 0.3

        if self.config["mtf_analysis"]["enabled"] and mtf_trends:
            mtf_buy_score = sum(1 for trend in mtf_trends.values() if trend == "UP")
            mtf_sell_score = sum(-1 for trend in mtf_trends.values() if trend == "DOWN")
            if mtf_trends:
                normalized_mtf_score = (mtf_buy_score + mtf_sell_score) / len(mtf_trends)
                signal_score += weights.get("mtf_trend_confluence", 0.0) * normalized_mtf_score
                self.logger.debug(f"MTF Confluence: Score {normalized_mtf_score:.2f}")

        threshold = self.config["signal_score_threshold"]
        final_signal = "HOLD"
        if signal_score >= threshold: final_signal = "BUY"
        elif signal_score <= -threshold: final_signal = "SELL"

        self.logger.info(f"{NEON_YELLOW}Raw Technical Signal Score: {signal_score:.2f}, Final Technical Signal: {final_signal}{RESET}")
        return final_signal, signal_score


    # --- Remaining Indicator Implementations ---
    def calculate_true_range(self) -> pd.Series:
        """Calculate True Range (TR)."""
        if len(self.df) < MIN_DATA_POINTS_TR: return pd.Series(np.nan, index=self.df.index)
        high_low = self.df["high"] - self.df["low"]
        high_prev_close = (self.df["high"] - self.df["close"].shift()).abs()
        low_prev_close = (self.df["low"] - self.df["close"].shift()).abs()
        return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)

    def calculate_super_smoother(self, series: pd.Series, period: int) -> pd.Series:
        """Apply Ehlers SuperSmoother filter to reduce lag and noise."""
        if period <= 0 or len(series) < MIN_DATA_POINTS_SMOOTHER: return pd.Series(np.nan, index=series.index)
        series = pd.to_numeric(series, errors="coerce").dropna()
        if len(series) < MIN_DATA_POINTS_SMOOTHER: return pd.Series(np.nan, index=series.index)

        a1 = np.exp(-np.sqrt(2) * np.pi / period)
        b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / period)
        c1 = 1 - b1 + a1**2
        c2 = b1 - 2 * a1**2
        c3 = a1**2

        filt = pd.Series(0.0, index=series.index)
        if len(series) >= 1: filt.iloc = series.iloc
        if len(series) >= 2: filt.iloc = (series.iloc + series.iloc) / 2

        for i in range(2, len(series)):
            filt.iloc[i] = ((c1 / 2) * (series.iloc[i] + series.iloc[i - 1])) + (c2 * filt.iloc[i - 1]) - (c3 * filt.iloc[i - 2])
        return filt.reindex(self.df.index)

    def calculate_ehlers_supertrend(self, period: int, multiplier: float) -> Optional[pd.DataFrame]:
        """Calculate SuperTrend using Ehlers SuperSmoother for price and volatility."""
        if len(self.df) < period * 3: return None
        df_copy = self.df.copy()
        hl2 = (df_copy["high"] + df_copy["low"]) / 2
        smoothed_price = self.calculate_super_smoother(hl2, period)
        tr = self.calculate_true_range()
        smoothed_atr = self.calculate_super_smoother(tr, period)

        if smoothed_price is None or smoothed_atr is None: return None

        df_copy["smoothed_price"] = smoothed_price
        df_copy["smoothed_atr"] = smoothed_atr
        df_copy.dropna(subset=["smoothed_price", "smoothed_atr"], inplace=True)
        if df_copy.empty: return None

        upper_band = df_copy["smoothed_price"] + multiplier * df_copy["smoothed_atr"]
        lower_band = df_copy["smoothed_price"] - multiplier * df_copy["smoothed_atr"]

        direction = pd.Series(0, index=df_copy.index, dtype=int)
        supertrend = pd.Series(np.nan, index=df_copy.index)

        first_valid_idx = df_copy.index
        supertrend.loc[first_valid_idx] = lower_band.loc[first_valid_idx]

        for i in range(1, len(df_copy)):
            current_idx = df_copy.index[i]
            prev_idx = df_copy.index[i - 1]

            prev_direction = direction.loc[prev_idx]
            prev_supertrend = supertrend.loc[prev_idx]
            curr_close = df_copy["close"].loc[current_idx]

            if prev_direction == 1:
                supertrend.loc[current_idx] = max(lower_band.loc[current_idx], prev_supertrend)
                if curr_close < supertrend.loc[current_idx]:
                    direction.loc[current_idx] = -1
                    supertrend.loc[current_idx] = upper_band.loc[current_idx]
                else: direction.loc[current_idx] = 1
            elif prev_direction == -1:
                supertrend.loc[current_idx] = min(upper_band.loc[current_idx], prev_supertrend)
                if curr_close > supertrend.loc[current_idx]:
                    direction.loc[current_idx] = 1
                    supertrend.loc[current_idx] = lower_band.loc[current_idx]
                else: direction.loc[current_idx] = -1
            else:
                if curr_close > lower_band.loc[current_idx]:
                    direction.loc[current_idx] = 1
                    supertrend.loc[current_idx] = lower_band.loc[current_idx]
                else:
                    direction.loc[current_idx] = -1
                    supertrend.loc[current_idx] = upper_band.loc[current_idx]

        result = pd.DataFrame({"supertrend": supertrend, "direction": direction})
        return result.reindex(self.df.index)

    def calculate_macd(self, fast_period: int, slow_period: int, signal_period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Moving Average Convergence Divergence (MACD)."""
        if len(self.df) < slow_period + signal_period:
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        ema_fast = self.df["close"].ewm(span=fast_period, adjust=False).mean()
        ema_slow = self.df["close"].ewm(span=slow_period, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    def calculate_rsi(self, period: int) -> pd.Series:
        """Calculate Relative Strength Index (RSI)."""
        if len(self.df) <= period: return pd.Series(np.nan, index=self.df.index)
        delta = self.df["close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.ewm(span=period, adjust=False, min_periods=period).mean()
        avg_loss = loss.ewm(span=period, adjust=False, min_periods=period).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_stoch_rsi(self, period: int, k_period: int, d_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate Stochastic RSI."""
        if len(self.df) <= period: return pd.Series(np.nan), pd.Series(np.nan)
        rsi = self.calculate_rsi(period)

        lowest_rsi = rsi.rolling(window=period, min_periods=period).min()
        highest_rsi = rsi.rolling(window=period, min_periods=period).max()

        stoch_rsi_k_raw = ((rsi - lowest_rsi) / (highest_rsi - lowest_rsi))
        stoch_rsi_k_raw = stoch_rsi_k_raw.replace([np.inf, -np.inf], np.nan).fillna(0) * 100

        stoch_rsi_k = stoch_rsi_k_raw.rolling(window=k_period, min_periods=k_period).mean()
        stoch_rsi_d = stoch_rsi_k.rolling(window=d_period, min_periods=d_period).mean()

        return stoch_rsi_k, stoch_rsi_d

    def calculate_adx(self, period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Average Directional Index (ADX)."""
        if len(self.df) < period * 2: return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        tr = self.calculate_true_range()
        plus_dm = self.df["high"].diff().clip(lower=0)
        minus_dm = -self.df["low"].diff().clip(lower=0)

        plus_dm_final = plus_dm.copy()
        minus_dm_final = minus_dm.copy()
        condition_plus_wins = (plus_dm_final > minus_dm_final)
        condition_minus_wins = (minus_dm_final > plus_dm_final)

        plus_dm_final[condition_minus_wins] = 0
        minus_dm_final[condition_plus_wins] = 0

        atr = tr.ewm(span=period, adjust=False).mean()
        plus_di = (plus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100
        minus_di = (minus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100

        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)).replace([np.inf, -np.inf], np.nan).fillna(0) * 100
        adx = dx.ewm(span=period, adjust=False).mean()

        return adx, plus_di, minus_di

    def calculate_bollinger_bands(self, period: int, std_dev: float) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands."""
        if len(self.df) < period: return (pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan))
        middle_band = self.df["close"].rolling(window=period, min_periods=period).mean()
        std = self.df["close"].rolling(window=period, min_periods=period).std()
        upper_band = middle_band + (std * std_dev)
        lower_band = middle_band - (std * std_dev)
        return upper_band, middle_band, lower_band

    def calculate_vwap(self) -> pd.Series:
        """Calculate Volume Weighted Average Price (VWAP)."""
        if self.df.empty: return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        cumulative_tp_vol = (typical_price * self.df["volume"]).cumsum()
        cumulative_vol = self.df["volume"].cumsum()
        vwap = cumulative_tp_vol / cumulative_vol
        return vwap

    def calculate_cci(self, period: int) -> pd.Series:
        """Calculate Commodity Channel Index (CCI)."""
        if len(self.df) < period: return pd.Series(np.nan, index=self.df.index)
        tp = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        sma_tp = tp.rolling(window=period, min_periods=period).mean()
        mad = tp.rolling(window=period, min_periods=period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=False)
        cci = (tp - sma_tp) / (0.015 * mad)
        cci = cci.replace([np.inf, -np.inf], np.nan).fillna(0)
        return cci

    def calculate_williams_r(self, period: int) -> pd.Series:
        """Calculate Williams %R."""
        if len(self.df) < period: return pd.Series(np.nan, index=self.df.index)
        highest_high = self.df["high"].rolling(window=period, min_periods=period).max()
        lowest_low = self.df["low"].rolling(window=period, min_periods=period).min()
        wr = -100 * ((highest_high - self.df["close"]) / (highest_high - lowest_low))
        wr = wr.replace([np.inf, -np.inf], np.nan).fillna(-50)
        return wr

    def calculate_ichimoku_cloud(self, tenkan_period: int, kijun_period: int, senkou_span_b_period: int, chikou_span_offset: int) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
        """Calculate Ichimoku Cloud components."""
        if (len(self.df) < max(tenkan_period, kijun_period, senkou_span_b_period) + chikou_span_offset):
            return (pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan))

        tenkan_sen = (self.df["high"].rolling(window=tenkan_period).max() + self.df["low"].rolling(window=tenkan_period).min()) / 2
        kijun_sen = (self.df["high"].rolling(window=kijun_period).max() + self.df["low"].rolling(window=kijun_period).min()) / 2
        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun_period)
        senkou_span_b = ((self.df["high"].rolling(window=senkou_span_b_period).max() + self.df["low"].rolling(window=senkou_span_b_period).min()) / 2).shift(kijun_period)
        chikou_span = self.df["close"].shift(-chikou_span_offset)

        return tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span

    def calculate_mfi(self, period: int) -> pd.Series:
        """Calculate Money Flow Index (MFI)."""
        if len(self.df) <= period: return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        money_flow = typical_price * self.df["volume"]

        positive_flow = pd.Series(0.0, index=self.df.index)
        negative_flow = pd.Series(0.0, index=self.df.index)

        for i in range(1, len(self.df)):
            if typical_price.iloc[i] > typical_price.iloc[i - 1]: positive_flow.iloc[i] = money_flow.iloc[i]
            elif typical_price.iloc[i] < typical_price.iloc[i - 1]: negative_flow.iloc[i] = money_flow.iloc[i]

        positive_mf_sum = positive_flow.rolling(window=period, min_periods=period).sum()
        negative_mf_sum = negative_flow.rolling(window=period, min_periods=period).sum()

        mf_ratio = positive_mf_sum / negative_mf_sum
        mfi = 100 - (100 / (1 + mf_ratio))
        mfi = mfi.replace([np.inf, -np.inf], np.nan).fillna(50)
        return mfi

    def calculate_obv(self, ema_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate On-Balance Volume (OBV) and its EMA."""
        if len(self.df) < MIN_DATA_POINTS_OBV: return pd.Series(np.nan), pd.Series(np.nan)

        obv = pd.Series(0.0, index=self.df.index)
        for i in range(1, len(self.df)):
            if self.df["close"].iloc[i] > self.df["close"].iloc[i - 1]: obv.iloc[i] = obv.iloc[i - 1] + self.df["volume"].iloc[i]
            elif self.df["close"].iloc[i] < self.df["close"].iloc[i - 1]: obv.iloc[i] = obv.iloc[i - 1] - self.df["volume"].iloc[i]
            else: obv.iloc[i] = obv.iloc[i - 1]

        obv_ema = obv.ewm(span=ema_period, adjust=False).mean()
        return obv, obv_ema

    def calculate_cmf(self, period: int) -> pd.Series:
        """Calculate Chaikin Money Flow (CMF)."""
        if len(self.df) < period: return pd.Series(np.nan)

        mfm = ((self.df["close"] - self.df["low"]) - (self.df["high"] - self.df["close"])) / (self.df["high"] - self.df["low"])
        mfm = mfm.replace([np.inf, -np.inf], np.nan).fillna(0)

        mfv = mfm * self.df["volume"]
        cmf = (mfv.rolling(window=period).sum() / self.df["volume"].rolling(window=period).sum())
        cmf = cmf.replace([np.inf, -np.inf], np.nan).fillna(0)

        return cmf

    def calculate_psar(self, acceleration: float, max_acceleration: float) -> tuple[pd.Series, pd.Series]:
        """Calculate Parabolic SAR."""
        if len(self.df) < MIN_DATA_POINTS_PSAR: return pd.Series(np.nan), pd.Series(np.nan)

        psar = self.df["close"].copy()
        bull = pd.Series(True, index=self.df.index)
        af = acceleration
        ep = self.df["low"].iloc if self.df["close"].iloc < self.df["close"].iloc else self.df["high"].iloc

        for i in range(1, len(self.df)):
            if bull.iloc[i - 1]:
                psar.iloc[i] = psar.iloc[i - 1] + af * (ep - psar.iloc[i - 1])
            else:
                psar.iloc[i] = psar.iloc[i - 1] - af * (psar.iloc[i - 1] - ep)

            reverse = False
            if bull.iloc[i - 1] and self.df["low"].iloc[i] < psar.iloc[i]:
                bull.iloc[i] = False; reverse = True
            elif not bull.iloc[i - 1] and self.df["high"].iloc[i] > psar.iloc[i]:
                bull.iloc[i] = True; reverse = True
            else: bull.iloc[i] = bull.iloc[i - 1]

            if reverse:
                af = acceleration
                ep = self.df["high"].iloc[i] if bull.iloc[i] else self.df["low"].iloc[i]
            elif bull.iloc[i]:
                if self.df["high"].iloc[i] > ep: ep = self.df["high"].iloc[i]; af = min(af + acceleration, max_acceleration)
            elif self.df["low"].iloc[i] < ep: ep = self.df["low"].iloc[i]; af = min(af + acceleration, max_acceleration)

            if bull.iloc[i]: psar.iloc[i] = min(psar.iloc[i], self.df["low"].iloc[i], self.df["low"].iloc[i-1])
            else: psar.iloc[i] = max(psar.iloc[i], self.df["high"].iloc[i], self.df["high"].iloc[i-1])

            if bull.iloc[i] and psar.iloc[i] > self.df["low"].iloc[i]: psar.iloc[i] = self.df["low"].iloc[i]
            elif not bull.iloc[i] and psar.iloc[i] < self.df["high"].iloc[i]: psar.iloc[i] = self.df["high"].iloc[i]

        direction = pd.Series(0, index=self.df.index, dtype=int)
        direction[psar < self.df["close"]] = 1
        direction[psar > self.df["close"]] = -1

        return psar, direction

    def calculate_fibonacci_levels(self) -> None:
        """Calculate Fibonacci retracement levels based on a recent high-low swing."""
        window = self.config["indicator_settings"]["fibonacci_window"]
        if len(self.df) < window:
            self.logger.warning(f"{NEON_YELLOW}Not enough data for Fibonacci levels (need {window} bars).{RESET}")
            return

        recent_high = self.df["high"].iloc[-window:].max()
        recent_low = self.df["low"].iloc[-window:].min()
        diff = recent_high - recent_low

        self.fib_levels = {
            "0.0%": Decimal(str(recent_high)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "23.6%": Decimal(str(recent_high - 0.236 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "38.2%": Decimal(str(recent_high - 0.382 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "50.0%": Decimal(str(recent_high - 0.500 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "61.8%": Decimal(str(recent_high - 0.618 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "78.6%": Decimal(str(recent_high - 0.786 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "100.0%": Decimal(str(recent_low)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
        }
        self.logger.debug(f"Calculated Fibonacci levels: {self.fib_levels}")

    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        """Safely retrieve an indicator value."""
        return self.indicator_values.get(key, default)

    def _check_orderbook(self, current_price: Decimal, orderbook_data: dict) -> float:
        """Analyze orderbook imbalance."""
        bids = orderbook_data.get("b", [])
        asks = orderbook_data.get("a", [])

        bid_volume = sum(Decimal(b) for b in bids)
        ask_volume = sum(Decimal(a) for a in asks)

        if bid_volume + ask_volume == 0: return 0.0

        imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
        self.logger.debug(f"Orderbook Imbalance: {imbalance:.4f} (Bids: {bid_volume}, Asks: {ask_volume})")
        return float(imbalance)

    def _get_mtf_trend(self, higher_tf_df: pd.DataFrame, indicator_type: str) -> str:
        """Determine trend from higher timeframe using specified indicator."""
        if higher_tf_df.empty: return "UNKNOWN"

        last_close = higher_tf_df["close"].iloc[-1]
        period = self.config["mtf_analysis"]["trend_period"]

        if indicator_type == "sma":
            if len(higher_tf_df) < period: return "UNKNOWN"
            sma = higher_tf_df["close"].rolling(window=period, min_periods=period).mean().iloc[-1]
            if last_close > sma: return "UP"
            if last_close < sma: return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ema":
            if len(higher_tf_df) < period: return "UNKNOWN"
            ema = higher_tf_df["close"].ewm(span=period, adjust=False, min_periods=period).mean().iloc[-1]
            if last_close > ema: return "UP"
            if last_close < ema: return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ehlers_supertrend":
            temp_analyzer = TradingAnalyzer(higher_tf_df, self.config, self.logger, self.symbol)
            st_result = temp_analyzer.calculate_ehlers_supertrend(
                self.indicator_settings["ehlers_slow_period"],
                self.indicator_settings["ehlers_slow_multiplier"],
            )
            if st_result is not None and not st_result.empty:
                st_dir = st_result["direction"].iloc[-1]
                if st_dir == 1: return "UP"
                if st_dir == -1: return "DOWN"
            return "UNKNOWN"
        return "UNKNOWN"

    def generate_trading_signal(
        self, current_price: Decimal, orderbook_data: dict | None, mtf_trends: dict[str, str]
    ) -> tuple[str, float]:
        """Generate a signal using confluence of indicators, including Ehlers SuperTrend."""
        signal_score = 0.0
        active_indicators = self.config["indicators"]
        weights = self.weights

        if self.df.empty:
            self.logger.warning(f"{NEON_YELLOW}DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}")
            return "HOLD", 0.0

        current_close = Decimal(str(self.df["close"].iloc[-1]))
        prev_close = Decimal(str(self.df["close"].iloc[-2])) if len(self.df) > 1 else current_close
        isd = self.indicator_settings

        # --- Indicator Scoring ---
        if active_indicators.get("ema_alignment", False):
            ema_short = self._get_indicator_value("EMA_Short")
            ema_long = self._get_indicator_value("EMA_Long")
            if not pd.isna(ema_short) and not pd.isna(ema_long):
                if ema_short > ema_long: signal_score += weights.get("ema_alignment", 0)
                elif ema_short < ema_long: signal_score -= weights.get("ema_alignment", 0)

        if active_indicators.get("sma_trend_filter", False):
            sma_long = self._get_indicator_value("SMA_Long")
            if not pd.isna(sma_long):
                if current_close > sma_long: signal_score += weights.get("sma_trend_filter", 0)
                elif current_close < sma_long: signal_score -= weights.get("sma_trend_filter", 0)

        if active_indicators.get("momentum", False):
            rsi = self._get_indicator_value("RSI")
            stoch_k = self._get_indicator_value("StochRSI_K")
            stoch_d = self._get_indicator_value("StochRSI_D")
            cci = self._get_indicator_value("CCI")
            wr = self._get_indicator_value("WR")
            mfi = self._get_indicator_value("MFI")

            if not pd.isna(rsi):
                if rsi < isd["rsi_oversold"]: signal_score += weights.get("rsi", 0) * 0.5
                elif rsi > isd["rsi_overbought"]: signal_score -= weights.get("rsi", 0) * 0.5

            if not pd.isna(stoch_k) and not pd.isna(stoch_d):
                if stoch_k > stoch_d and stoch_k < isd["stoch_rsi_oversold"]: signal_score += weights.get("stoch_rsi", 0) * 0.5
                elif stoch_k < stoch_d and stoch_k > isd["stoch_rsi_overbought"]: signal_score -= weights.get("stoch_rsi", 0) * 0.5

            if not pd.isna(cci):
                if cci < isd["cci_oversold"]: signal_score += weights.get("cci", 0) * 0.5
                elif cci > isd["cci_overbought"]: signal_score -= weights.get("cci", 0) * 0.5

            if not pd.isna(wr):
                if wr < isd["williams_r_oversold"]: signal_score += weights.get("wr", 0) * 0.5
                elif wr > isd["williams_r_overbought"]: signal_score -= weights.get("wr", 0) * 0.5

            if not pd.isna(mfi):
                if mfi < isd["mfi_oversold"]: signal_score += weights.get("mfi", 0) * 0.5
                elif mfi > isd["mfi_overbought"]: signal_score -= weights.get("mfi", 0) * 0.5

        if active_indicators.get("bollinger_bands", False):
            bb_upper = self._get_indicator_value("BB_Upper")
            bb_lower = self._get_indicator_value("BB_Lower")
            if not pd.isna(bb_upper) and not pd.isna(bb_lower):
                if current_close < bb_lower: signal_score += weights.get("bollinger_bands", 0) * 0.5
                elif current_close > bb_upper: signal_score -= weights.get("bollinger_bands", 0) * 0.5

        if active_indicators.get("vwap", False):
            vwap = self._get_indicator_value("VWAP")
            if not pd.isna(vwap):
                if current_close > vwap: signal_score += weights.get("vwap", 0) * 0.2
                elif current_close < vwap: signal_score -= weights.get("vwap", 0) * 0.2

                if len(self.df) > 1:
                    prev_close = Decimal(str(self.df["close"].iloc[-2]))
                    prev_vwap = Decimal(str(self.df["VWAP"].iloc[-2]))
                    if current_close > vwap and prev_close <= prev_vwap: signal_score += weights.get("vwap", 0) * 0.3
                    elif current_close < vwap and prev_close >= prev_vwap: signal_score -= weights.get("vwap", 0) * 0.3

        if active_indicators.get("psar", False):
            psar_val = self._get_indicator_value("PSAR_Val")
            psar_dir = self._get_indicator_value("PSAR_Dir")
            if not pd.isna(psar_val) and not pd.isna(psar_dir):
                if psar_dir == 1: signal_score += weights.get("psar", 0) * 0.5
                elif psar_dir == -1: signal_score -= weights.get("psar", 0) * 0.5

                if len(self.df) > 1:
                    prev_close = Decimal(str(self.df["close"].iloc[-2]))
                    prev_psar_val = Decimal(str(self.df["PSAR_Val"].iloc[-2]))
                    if current_close > psar_val and prev_close <= prev_psar_val: signal_score += weights.get("psar", 0) * 0.4
                    elif current_close < psar_val and prev_close >= prev_psar_val: signal_score -= weights.get("psar", 0) * 0.4

        if active_indicators.get("orderbook_imbalance", False) and orderbook_data:
            imbalance = self._check_orderbook(current_price, orderbook_data)
            signal_score += imbalance * weights.get("orderbook_imbalance", 0)

        if active_indicators.get("fibonacci_levels", False) and self.fib_levels:
            for level_name, level_price in self.fib_levels.items():
                if level_name not in ["0.0%", "100.0%"] and abs(current_price - level_price) / current_price < Decimal("0.001"):
                    if len(self.df) > 1:
                        prev_close = Decimal(str(self.df["close"].iloc[-2]))
                        if current_close > prev_close and current_close > level_price: signal_score += weights.get("fibonacci_levels", 0) * 0.1
                        elif current_close < prev_close and current_close < level_price: signal_score -= weights.get("fibonacci_levels", 0) * 0.1

        if active_indicators.get("ehlers_supertrend", False):
            st_fast_dir = self._get_indicator_value("ST_Fast_Dir")
            st_slow_dir = self._get_indicator_value("ST_Slow_Dir")
            prev_st_fast_dir = self.df["st_fast_dir"].iloc[-2] if "st_fast_dir" in self.df.columns and len(self.df) > 1 else np.nan
            weight = weights.get("ehlers_supertrend_alignment", 0.0)

            if not pd.isna(st_fast_dir) and not pd.isna(st_slow_dir) and not pd.isna(prev_st_fast_dir):
                if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1: signal_score += weight
                elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1: signal_score -= weight
                elif st_slow_dir == 1 and st_fast_dir == 1: signal_score += weight * 0.3
                elif st_slow_dir == -1 and st_fast_dir == -1: signal_score -= weight * 0.3

        if active_indicators.get("macd", False):
            macd_line = self._get_indicator_value("MACD_Line")
            signal_line = self._get_indicator_value("MACD_Signal")
            histogram = self._get_indicator_value("MACD_Hist")
            weight = weights.get("macd_alignment", 0.0)

            if not pd.isna(macd_line) and not pd.isna(signal_line) and not pd.isna(histogram):
                if len(self.df) > 1:
                    prev_macd_line = Decimal(str(self.df["MACD_Line"].iloc[-2]))
                    prev_signal_line = Decimal(str(self.df["MACD_Signal"].iloc[-2]))
                    if macd_line > signal_line and prev_macd_line <= prev_signal_line: signal_score += weight
                    elif macd_line < signal_line and prev_macd_line >= prev_signal_line: signal_score -= weight
                if len(self.df) > 1 and histogram > 0 and self.df["MACD_Hist"].iloc[-2] < 0: signal_score += weight * 0.2
                elif len(self.df) > 1 and histogram < 0 and self.df["MACD_Hist"].iloc[-2] > 0: signal_score -= weight * 0.2

        if active_indicators.get("adx", False):
            adx_val = self._get_indicator_value("ADX")
            plus_di = self._get_indicator_value("PlusDI")
            minus_di = self._get_indicator_value("MinusDI")
            weight = weights.get("adx_strength", 0.0)

            if not pd.isna(adx_val) and not pd.isna(plus_di) and not pd.isna(minus_di):
                if adx_val > ADX_STRONG_TREND_THRESHOLD:
                    if plus_di > minus_di: signal_score += weight
                    elif minus_di > plus_di: signal_score -= weight
                elif adx_val < ADX_WEAK_TREND_THRESHOLD: pass

        if active_indicators.get("ichimoku_cloud", False):
            tenkan_sen = self._get_indicator_value("Tenkan_Sen")
            kijun_sen = self._get_indicator_value("Kijun_Sen")
            senkou_span_a = self._get_indicator_value("Senkou_Span_A")
            senkou_span_b = self._get_indicator_value("Senkou_Span_B")
            chikou_span = self._get_indicator_value("Chikou_Span")
            weight = weights.get("ichimoku_confluence", 0.0)

            if not pd.isna(tenkan_sen) and not pd.isna(kijun_sen) and not pd.isna(senkou_span_a) and not pd.isna(senkou_span_b) and not pd.isna(chikou_span):
                if tenkan_sen > kijun_sen and self.df["Tenkan_Sen"].iloc[-2] <= self.df["Kijun_Sen"].iloc[-2]: signal_score += weight * 0.5
                elif tenkan_sen < kijun_sen and self.df["Tenkan_Sen"].iloc[-2] >= self.df["Kijun_Sen"].iloc[-2]: signal_score -= weight * 0.5

                if current_close > max(senkou_span_a, senkou_span_b) and self.df["close"].iloc[-2] <= max(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]): signal_score += weight * 0.7
                elif current_close < min(senkou_span_a, senkou_span_b) and self.df["close"].iloc[-2] >= min(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]): signal_score -= weight * 0.7

                if chikou_span > current_close and self.df["Chikou_Span"].iloc[-2] <= self.df["close"].iloc[-2]: signal_score += weight * 0.3
                elif chikou_span < current_close and self.df["Chikou_Span"].iloc[-2] >= self.df["close"].iloc[-2]: signal_score -= weight * 0.3

        if active_indicators.get("obv", False):
            obv_val = self._get_indicator_value("OBV")
            obv_ema = self._get_indicator_value("OBV_EMA")
            weight = weights.get("obv_momentum", 0.0)
            if not pd.isna(obv_val) and not pd.isna(obv_ema):
                if obv_val > obv_ema and self.df["OBV"].iloc[-2] <= self.df["OBV_EMA"].iloc[-2]: signal_score += weight * 0.5
                elif obv_val < obv_ema and self.df["OBV"].iloc[-2] >= self.df["OBV_EMA"].iloc[-2]: signal_score -= weight * 0.5
                if len(self.df) > 2:
                    if obv_val > self.df["OBV"].iloc[-2] and obv_val > self.df["OBV"].iloc[-3]: signal_score += weight * 0.2
                    elif obv_val < self.df["OBV"].iloc[-2] and obv_val < self.df["OBV"].iloc[-3]: signal_score -= weight * 0.2

        if active_indicators.get("cmf", False):
            cmf_val = self._get_indicator_value("CMF")
            weight = weights.get("cmf_flow", 0.0)
            if not pd.isna(cmf_val):
                if cmf_val > 0: signal_score += weight * 0.5
                elif cmf_val < 0: signal_score -= weight * 0.5
                if len(self.df) > 2:
                    if cmf_val > self.df["CMF"].iloc[-2] and cmf_val > self.df["CMF"].iloc[-3]: signal_score += weight * 0.3
                    elif cmf_val < self.df["CMF"].iloc[-2] and cmf_val < self.df["CMF"].iloc[-3]: signal_score -= weight * 0.3

        if self.config["mtf_analysis"]["enabled"] and mtf_trends:
            mtf_buy_score = sum(1 for trend in mtf_trends.values() if trend == "UP")
            mtf_sell_score = sum(-1 for trend in mtf_trends.values() if trend == "DOWN")
            if mtf_trends:
                normalized_mtf_score = (mtf_buy_score + mtf_sell_score) / len(mtf_trends)
                signal_score += weights.get("mtf_trend_confluence", 0.0) * normalized_mtf_score
                self.logger.debug(f"MTF Confluence: Score {normalized_mtf_score:.2f}")

        threshold = self.config["signal_score_threshold"]
        final_signal = "HOLD"
        if signal_score >= threshold: final_signal = "BUY"
        elif signal_score <= -threshold: final_signal = "SELL"

        self.logger.info(f"{NEON_YELLOW}Raw Technical Signal Score: {signal_score:.2f}, Final Technical Signal: {final_signal}{RESET}")
        return final_signal, signal_score


    # --- Remaining Indicator Implementations ---
    def calculate_true_range(self) -> pd.Series:
        """Calculate True Range (TR)."""
        if len(self.df) < MIN_DATA_POINTS_TR: return pd.Series(np.nan, index=self.df.index)
        high_low = self.df["high"] - self.df["low"]
        high_prev_close = (self.df["high"] - self.df["close"].shift()).abs()
        low_prev_close = (self.df["low"] - self.df["close"].shift()).abs()
        return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)

    def calculate_super_smoother(self, series: pd.Series, period: int) -> pd.Series:
        """Apply Ehlers SuperSmoother filter to reduce lag and noise."""
        if period <= 0 or len(series) < MIN_DATA_POINTS_SMOOTHER: return pd.Series(np.nan, index=series.index)
        series = pd.to_numeric(series, errors="coerce").dropna()
        if len(series) < MIN_DATA_POINTS_SMOOTHER: return pd.Series(np.nan, index=series.index)

        a1 = np.exp(-np.sqrt(2) * np.pi / period)
        b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / period)
        c1 = 1 - b1 + a1**2
        c2 = b1 - 2 * a1**2
        c3 = a1**2

        filt = pd.Series(0.0, index=series.index)
        if len(series) >= 1: filt.iloc = series.iloc
        if len(series) >= 2: filt.iloc = (series.iloc + series.iloc) / 2

        for i in range(2, len(series)):
            filt.iloc[i] = ((c1 / 2) * (series.iloc[i] + series.iloc[i - 1])) + (c2 * filt.iloc[i - 1]) - (c3 * filt.iloc[i - 2])
        return filt.reindex(self.df.index)

    def calculate_ehlers_supertrend(self, period: int, multiplier: float) -> Optional[pd.DataFrame]:
        """Calculate SuperTrend using Ehlers SuperSmoother for price and volatility."""
        if len(self.df) < period * 3: return None
        df_copy = self.df.copy()
        hl2 = (df_copy["high"] + df_copy["low"]) / 2
        smoothed_price = self.calculate_super_smoother(hl2, period)
        tr = self.calculate_true_range()
        smoothed_atr = self.calculate_super_smoother(tr, period)

        if smoothed_price is None or smoothed_atr is None: return None

        df_copy["smoothed_price"] = smoothed_price
        df_copy["smoothed_atr"] = smoothed_atr
        df_copy.dropna(subset=["smoothed_price", "smoothed_atr"], inplace=True)
        if df_copy.empty: return None

        upper_band = df_copy["smoothed_price"] + multiplier * df_copy["smoothed_atr"]
        lower_band = df_copy["smoothed_price"] - multiplier * df_copy["smoothed_atr"]

        direction = pd.Series(0, index=df_copy.index, dtype=int)
        supertrend = pd.Series(np.nan, index=df_copy.index)

        first_valid_idx = df_copy.index
        supertrend.loc[first_valid_idx] = lower_band.loc[first_valid_idx]

        for i in range(1, len(df_copy)):
            current_idx = df_copy.index[i]
            prev_idx = df_copy.index[i - 1]

            prev_direction = direction.loc[prev_idx]
            prev_supertrend = supertrend.loc[prev_idx]
            curr_close = df_copy["close"].loc[current_idx]

            if prev_direction == 1:
                supertrend.loc[current_idx] = max(lower_band.loc[current_idx], prev_supertrend)
                if curr_close < supertrend.loc[current_idx]:
                    direction.loc[current_idx] = -1
                    supertrend.loc[current_idx] = upper_band.loc[current_idx]
                else: direction.loc[current_idx] = 1
            elif prev_direction == -1:
                supertrend.loc[current_idx] = min(upper_band.loc[current_idx], prev_supertrend)
                if curr_close > supertrend.loc[current_idx]:
                    direction.loc[current_idx] = 1
                    supertrend.loc[current_idx] = lower_band.loc[current_idx]
                else: direction.loc[current_idx] = -1
            else:
                if curr_close > lower_band.loc[current_idx]:
                    direction.loc[current_idx] = 1
                    supertrend.loc[current_idx] = lower_band.loc[current_idx]
                else:
                    direction.loc[current_idx] = -1
                    supertrend.loc[current_idx] = upper_band.loc[current_idx]

        result = pd.DataFrame({"supertrend": supertrend, "direction": direction})
        return result.reindex(self.df.index)

    def calculate_macd(self, fast_period: int, slow_period: int, signal_period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Moving Average Convergence Divergence (MACD)."""
        if len(self.df) < slow_period + signal_period:
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        ema_fast = self.df["close"].ewm(span=fast_period, adjust=False).mean()
        ema_slow = self.df["close"].ewm(span=slow_period, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    def calculate_rsi(self, period: int) -> pd.Series:
        """Calculate Relative Strength Index (RSI)."""
        if len(self.df) <= period: return pd.Series(np.nan, index=self.df.index)
        delta = self.df["close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.ewm(span=period, adjust=False, min_periods=period).mean()
        avg_loss = loss.ewm(span=period, adjust=False, min_periods=period).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_stoch_rsi(self, period: int, k_period: int, d_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate Stochastic RSI."""
        if len(self.df) <= period: return pd.Series(np.nan), pd.Series(np.nan)
        rsi = self.calculate_rsi(period)

        lowest_rsi = rsi.rolling(window=period, min_periods=period).min()
        highest_rsi = rsi.rolling(window=period, min_periods=period).max()

        stoch_rsi_k_raw = ((rsi - lowest_rsi) / (highest_rsi - lowest_rsi))
        stoch_rsi_k_raw = stoch_rsi_k_raw.replace([np.inf, -np.inf], np.nan).fillna(0) * 100

        stoch_rsi_k = stoch_rsi_k_raw.rolling(window=k_period, min_periods=k_period).mean()
        stoch_rsi_d = stoch_rsi_k.rolling(window=d_period, min_periods=d_period).mean()

        return stoch_rsi_k, stoch_rsi_d

    def calculate_adx(self, period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Average Directional Index (ADX)."""
        if len(self.df) < period * 2: return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        tr = self.calculate_true_range()
        plus_dm = self.df["high"].diff().clip(lower=0)
        minus_dm = -self.df["low"].diff().clip(lower=0)

        plus_dm_final = plus_dm.copy()
        minus_dm_final = minus_dm.copy()
        condition_plus_wins = (plus_dm_final > minus_dm_final)
        condition_minus_wins = (minus_dm_final > plus_dm_final)

        plus_dm_final[condition_minus_wins] = 0
        minus_dm_final[condition_plus_wins] = 0

        atr = tr.ewm(span=period, adjust=False).mean()
        plus_di = (plus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100
        minus_di = (minus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100

        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)).replace([np.inf, -np.inf], np.nan).fillna(0) * 100
        adx = dx.ewm(span=period, adjust=False).mean()

        return adx, plus_di, minus_di

    def calculate_bollinger_bands(self, period: int, std_dev: float) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands."""
        if len(self.df) < period: return (pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan))
        middle_band = self.df["close"].rolling(window=period, min_periods=period).mean()
        std = self.df["close"].rolling(window=period, min_periods=period).std()
        upper_band = middle_band + (std * std_dev)
        lower_band = middle_band - (std * std_dev)
        return upper_band, middle_band, lower_band

    def calculate_vwap(self) -> pd.Series:
        """Calculate Volume Weighted Average Price (VWAP)."""
        if self.df.empty: return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        cumulative_tp_vol = (typical_price * self.df["volume"]).cumsum()
        cumulative_vol = self.df["volume"].cumsum()
        vwap = cumulative_tp_vol / cumulative_vol
        return vwap

    def calculate_cci(self, period: int) -> pd.Series:
        """Calculate Commodity Channel Index (CCI)."""
        if len(self.df) < period: return pd.Series(np.nan, index=self.df.index)
        tp = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        sma_tp = tp.rolling(window=period, min_periods=period).mean()
        mad = tp.rolling(window=period, min_periods=period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=False)
        cci = (tp - sma_tp) / (0.015 * mad)
        cci = cci.replace([np.inf, -np.inf], np.nan).fillna(0)
        return cci

    def calculate_williams_r(self, period: int) -> pd.Series:
        """Calculate Williams %R."""
        if len(self.df) < period: return pd.Series(np.nan, index=self.df.index)
        highest_high = self.df["high"].rolling(window=period, min_periods=period).max()
        lowest_low = self.df["low"].rolling(window=period, min_periods=period).min()
        wr = -100 * ((highest_high - self.df["close"]) / (highest_high - lowest_low))
        wr = wr.replace([np.inf, -np.inf], np.nan).fillna(-50)
        return wr

    def calculate_ichimoku_cloud(self, tenkan_period: int, kijun_period: int, senkou_span_b_period: int, chikou_span_offset: int) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
        """Calculate Ichimoku Cloud components."""
        if (len(self.df) < max(tenkan_period, kijun_period, senkou_span_b_period) + chikou_span_offset):
            return (pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan))

        tenkan_sen = (self.df["high"].rolling(window=tenkan_period).max() + self.df["low"].rolling(window=tenkan_period).min()) / 2
        kijun_sen = (self.df["high"].rolling(window=kijun_period).max() + self.df["low"].rolling(window=kijun_period).min()) / 2
        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun_period)
        senkou_span_b = ((self.df["high"].rolling(window=senkou_span_b_period).max() + self.df["low"].rolling(window=senkou_span_b_period).min()) / 2).shift(kijun_period)
        chikou_span = self.df["close"].shift(-chikou_span_offset)

        return tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span

    def calculate_mfi(self, period: int) -> pd.Series:
        """Calculate Money Flow Index (MFI)."""
        if len(self.df) <= period: return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        money_flow = typical_price * self.df["volume"]

        positive_flow = pd.Series(0.0, index=self.df.index)
        negative_flow = pd.Series(0.0, index=self.df.index)

        for i in range(1, len(self.df)):
            if typical_price.iloc[i] > typical_price.iloc[i - 1]: positive_flow.iloc[i] = money_flow.iloc[i]
            elif typical_price.iloc[i] < typical_price.iloc[i - 1]: negative_flow.iloc[i] = money_flow.iloc[i]

        positive_mf_sum = positive_flow.rolling(window=period, min_periods=period).sum()
        negative_mf_sum = negative_flow.rolling(window=period, min_periods=period).sum()

        mf_ratio = positive_mf_sum / negative_mf_sum
        mfi = 100 - (100 / (1 + mf_ratio))
        mfi = mfi.replace([np.inf, -np.inf], np.nan).fillna(50)
        return mfi

    def calculate_obv(self, ema_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate On-Balance Volume (OBV) and its EMA."""
        if len(self.df) < MIN_DATA_POINTS_OBV: return pd.Series(np.nan), pd.Series(np.nan)

        obv = pd.Series(0.0, index=self.df.index)
        for i in range(1, len(self.df)):
            if self.df["close"].iloc[i] > self.df["close"].iloc[i - 1]: obv.iloc[i] = obv.iloc[i - 1] + self.df["volume"].iloc[i]
            elif self.df["close"].iloc[i] < self.df["close"].iloc[i - 1]: obv.iloc[i] = obv.iloc[i - 1] - self.df["volume"].iloc[i]
            else: obv.iloc[i] = obv.iloc[i - 1]

        obv_ema = obv.ewm(span=ema_period, adjust=False).mean()
        return obv, obv_ema

    def calculate_cmf(self, period: int) -> pd.Series:
        """Calculate Chaikin Money Flow (CMF)."""
        if len(self.df) < period: return pd.Series(np.nan)

        mfm = ((self.df["close"] - self.df["low"]) - (self.df["high"] - self.df["close"])) / (self.df["high"] - self.df["low"])
        mfm = mfm.replace([np.inf, -np.inf], np.nan).fillna(0)

        mfv = mfm * self.df["volume"]
        cmf = (mfv.rolling(window=period).sum() / self.df["volume"].rolling(window=period).sum())
        cmf = cmf.replace([np.inf, -np.inf], np.nan).fillna(0)

        return cmf

    def calculate_psar(self, acceleration: float, max_acceleration: float) -> tuple[pd.Series, pd.Series]:
        """Calculate Parabolic SAR."""
        if len(self.df) < MIN_DATA_POINTS_PSAR: return pd.Series(np.nan), pd.Series(np.nan)

        psar = self.df["close"].copy()
        bull = pd.Series(True, index=self.df.index)
        af = acceleration
        ep = self.df["low"].iloc if self.df["close"].iloc < self.df["close"].iloc else self.df["high"].iloc

        for i in range(1, len(self.df)):
            if bull.iloc[i - 1]:
                psar.iloc[i] = psar.iloc[i - 1] + af * (ep - psar.iloc[i - 1])
            else:
                psar.iloc[i] = psar.iloc[i - 1] - af * (psar.iloc[i - 1] - ep)

            reverse = False
            if bull.iloc[i - 1] and self.df["low"].iloc[i] < psar.iloc[i]:
                bull.iloc[i] = False; reverse = True
            elif not bull.iloc[i - 1] and self.df["high"].iloc[i] > psar.iloc[i]:
                bull.iloc[i] = True; reverse = True
            else: bull.iloc[i] = bull.iloc[i - 1]

            if reverse:
                af = acceleration
                ep = self.df["high"].iloc[i] if bull.iloc[i] else self.df["low"].iloc[i]
            elif bull.iloc[i]:
                if self.df["high"].iloc[i] > ep: ep = self.df["high"].iloc[i]; af = min(af + acceleration, max_acceleration)
            elif self.df["low"].iloc[i] < ep: ep = self.df["low"].iloc[i]; af = min(af + acceleration, max_acceleration)

            if bull.iloc[i]: psar.iloc[i] = min(psar.iloc[i], self.df["low"].iloc[i], self.df["low"].iloc[i-1])
            else: psar.iloc[i] = max(psar.iloc[i], self.df["high"].iloc[i], self.df["high"].iloc[i-1])

            if bull.iloc[i] and psar.iloc[i] > self.df["low"].iloc[i]: psar.iloc[i] = self.df["low"].iloc[i]
            elif not bull.iloc[i] and psar.iloc[i] < self.df["high"].iloc[i]: psar.iloc[i] = self.df["high"].iloc[i]

        direction = pd.Series(0, index=self.df.index, dtype=int)
        direction[psar < self.df["close"]] = 1
        direction[psar > self.df["close"]] = -1

        return psar, direction

    def calculate_fibonacci_levels(self) -> None:
        """Calculate Fibonacci retracement levels based on a recent high-low swing."""
        window = self.config["indicator_settings"]["fibonacci_window"]
        if len(self.df) < window:
            self.logger.warning(f"{NEON_YELLOW}Not enough data for Fibonacci levels (need {window} bars).{RESET}")
            return

        recent_high = self.df["high"].iloc[-window:].max()
        recent_low = self.df["low"].iloc[-window:].min()
        diff = recent_high - recent_low

        self.fib_levels = {
            "0.0%": Decimal(str(recent_high)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "23.6%": Decimal(str(recent_high - 0.236 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "38.2%": Decimal(str(recent_high - 0.382 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "50.0%": Decimal(str(recent_high - 0.500 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "61.8%": Decimal(str(recent_high - 0.618 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "78.6%": Decimal(str(recent_high - 0.786 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "100.0%": Decimal(str(recent_low)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
        }
        self.logger.debug(f"Calculated Fibonacci levels: {self.fib_levels}")

    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        """Safely retrieve an indicator value."""
        return self.indicator_values.get(key, default)

    def _check_orderbook(self, current_price: Decimal, orderbook_data: dict) -> float:
        """Analyze orderbook imbalance."""
        bids = orderbook_data.get("b", [])
        asks = orderbook_data.get("a", [])

        bid_volume = sum(Decimal(b) for b in bids)
        ask_volume = sum(Decimal(a) for a in asks)

        if bid_volume + ask_volume == 0: return 0.0

        imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
        self.logger.debug(f"Orderbook Imbalance: {imbalance:.4f} (Bids: {bid_volume}, Asks: {ask_volume})")
        return float(imbalance)

    def _get_mtf_trend(self, higher_tf_df: pd.DataFrame, indicator_type: str) -> str:
        """Determine trend from higher timeframe using specified indicator."""
        if higher_tf_df.empty: return "UNKNOWN"

        last_close = higher_tf_df["close"].iloc[-1]
        period = self.config["mtf_analysis"]["trend_period"]

        if indicator_type == "sma":
            if len(higher_tf_df) < period: return "UNKNOWN"
            sma = higher_tf_df["close"].rolling(window=period, min_periods=period).mean().iloc[-1]
            if last_close > sma: return "UP"
            if last_close < sma: return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ema":
            if len(higher_tf_df) < period: return "UNKNOWN"
            ema = higher_tf_df["close"].ewm(span=period, adjust=False, min_periods=period).mean().iloc[-1]
            if last_close > ema: return "UP"
            if last_close < ema: return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ehlers_supertrend":
            temp_analyzer = TradingAnalyzer(higher_tf_df, self.config, self.logger, self.symbol)
            st_result = temp_analyzer.calculate_ehlers_supertrend(
                self.indicator_settings["ehlers_slow_period"],
                self.indicator_settings["ehlers_slow_multiplier"],
            )
            if st_result is not None and not st_result.empty:
                st_dir = st_result["direction"].iloc[-1]
                if st_dir == 1: return "UP"
                if st_dir == -1: return "DOWN"
            return "UNKNOWN"
        return "UNKNOWN"

    def generate_trading_signal(
        self, current_price: Decimal, orderbook_data: dict | None, mtf_trends: dict[str, str]
    ) -> tuple[str, float]:
        """Generate a signal using confluence of indicators, including Ehlers SuperTrend."""
        signal_score = 0.0
        active_indicators = self.config["indicators"]
        weights = self.weights

        if self.df.empty:
            self.logger.warning(f"{NEON_YELLOW}DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}")
            return "HOLD", 0.0

        current_close = Decimal(str(self.df["close"].iloc[-1]))
        prev_close = Decimal(str(self.df["close"].iloc[-2])) if len(self.df) > 1 else current_close
        isd = self.indicator_settings

        # --- Indicator Scoring ---
        if active_indicators.get("ema_alignment", False):
            ema_short = self._get_indicator_value("EMA_Short")
            ema_long = self._get_indicator_value("EMA_Long")
            if not pd.isna(ema_short) and not pd.isna(ema_long):
                if ema_short > ema_long: signal_score += weights.get("ema_alignment", 0)
                elif ema_short < ema_long: signal_score -= weights.get("ema_alignment", 0)

        if active_indicators.get("sma_trend_filter", False):
            sma_long = self._get_indicator_value("SMA_Long")
            if not pd.isna(sma_long):
                if current_close > sma_long: signal_score += weights.get("sma_trend_filter", 0)
                elif current_close < sma_long: signal_score -= weights.get("sma_trend_filter", 0)

        if active_indicators.get("momentum", False):
            rsi = self._get_indicator_value("RSI")
            stoch_k = self._get_indicator_value("StochRSI_K")
            stoch_d = self._get_indicator_value("StochRSI_D")
            cci = self._get_indicator_value("CCI")
            wr = self._get_indicator_value("WR")
            mfi = self._get_indicator_value("MFI")

            if not pd.isna(rsi):
                if rsi < isd["rsi_oversold"]: signal_score += weights.get("rsi", 0) * 0.5
                elif rsi > isd["rsi_overbought"]: signal_score -= weights.get("rsi", 0) * 0.5

            if not pd.isna(stoch_k) and not pd.isna(stoch_d):
                if stoch_k > stoch_d and stoch_k < isd["stoch_rsi_oversold"]: signal_score += weights.get("stoch_rsi", 0) * 0.5
                elif stoch_k < stoch_d and stoch_k > isd["stoch_rsi_overbought"]: signal_score -= weights.get("stoch_rsi", 0) * 0.5

            if not pd.isna(cci):
                if cci < isd["cci_oversold"]: signal_score += weights.get("cci", 0) * 0.5
                elif cci > isd["cci_overbought"]: signal_score -= weights.get("cci", 0) * 0.5

            if not pd.isna(wr):
                if wr < isd["williams_r_oversold"]: signal_score += weights.get("wr", 0) * 0.5
                elif wr > isd["williams_r_overbought"]: signal_score -= weights.get("wr", 0) * 0.5

            if not pd.isna(mfi):
                if mfi < isd["mfi_oversold"]: signal_score += weights.get("mfi", 0) * 0.5
                elif mfi > isd["mfi_overbought"]: signal_score -= weights.get("mfi", 0) * 0.5

        if active_indicators.get("bollinger_bands", False):
            bb_upper = self._get_indicator_value("BB_Upper")
            bb_lower = self._get_indicator_value("BB_Lower")
            if not pd.isna(bb_upper) and not pd.isna(bb_lower):
                if current_close < bb_lower: signal_score += weights.get("bollinger_bands", 0) * 0.5
                elif current_close > bb_upper: signal_score -= weights.get("bollinger_bands", 0) * 0.5

        if active_indicators.get("vwap", False):
            vwap = self._get_indicator_value("VWAP")
            if not pd.isna(vwap):
                if current_close > vwap: signal_score += weights.get("vwap", 0) * 0.2
                elif current_close < vwap: signal_score -= weights.get("vwap", 0) * 0.2

                if len(self.df) > 1:
                    prev_close = Decimal(str(self.df["close"].iloc[-2]))
                    prev_vwap = Decimal(str(self.df["VWAP"].iloc[-2]))
                    if current_close > vwap and prev_close <= prev_vwap: signal_score += weights.get("vwap", 0) * 0.3
                    elif current_close < vwap and prev_close >= prev_vwap: signal_score -= weights.get("vwap", 0) * 0.3

        if active_indicators.get("psar", False):
            psar_val = self._get_indicator_value("PSAR_Val")
            psar_dir = self._get_indicator_value("PSAR_Dir")
            if not pd.isna(psar_val) and not pd.isna(psar_dir):
                if psar_dir == 1: signal_score += weights.get("psar", 0) * 0.5
                elif psar_dir == -1: signal_score -= weights.get("psar", 0) * 0.5

                if len(self.df) > 1:
                    prev_close = Decimal(str(self.df["close"].iloc[-2]))
                    prev_psar_val = Decimal(str(self.df["PSAR_Val"].iloc[-2]))
                    if current_close > psar_val and prev_close <= prev_psar_val: signal_score += weights.get("psar", 0) * 0.4
                    elif current_close < psar_val and prev_close >= prev_psar_val: signal_score -= weights.get("psar", 0) * 0.4

        if active_indicators.get("orderbook_imbalance", False) and orderbook_data:
            imbalance = self._check_orderbook(current_price, orderbook_data)
            signal_score += imbalance * weights.get("orderbook_imbalance", 0)

        if active_indicators.get("fibonacci_levels", False) and self.fib_levels:
            for level_name, level_price in self.fib_levels.items():
                if level_name not in ["0.0%", "100.0%"] and abs(current_price - level_price) / current_price < Decimal("0.001"):
                    if len(self.df) > 1:
                        prev_close = Decimal(str(self.df["close"].iloc[-2]))
                        if current_close > prev_close and current_close > level_price: signal_score += weights.get("fibonacci_levels", 0) * 0.1
                        elif current_close < prev_close and current_close < level_price: signal_score -= weights.get("fibonacci_levels", 0) * 0.1

        if active_indicators.get("ehlers_supertrend", False):
            st_fast_dir = self._get_indicator_value("ST_Fast_Dir")
            st_slow_dir = self._get_indicator_value("ST_Slow_Dir")
            prev_st_fast_dir = self.df["st_fast_dir"].iloc[-2] if "st_fast_dir" in self.df.columns and len(self.df) > 1 else np.nan
            weight = weights.get("ehlers_supertrend_alignment", 0.0)

            if not pd.isna(st_fast_dir) and not pd.isna(st_slow_dir) and not pd.isna(prev_st_fast_dir):
                if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1: signal_score += weight
                elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1: signal_score -= weight
                elif st_slow_dir == 1 and st_fast_dir == 1: signal_score += weight * 0.3
                elif st_slow_dir == -1 and st_fast_dir == -1: signal_score -= weight * 0.3

        if active_indicators.get("macd", False):
            macd_line = self._get_indicator_value("MACD_Line")
            signal_line = self._get_indicator_value("MACD_Signal")
            histogram = self._get_indicator_value("MACD_Hist")
            weight = weights.get("macd_alignment", 0.0)

            if not pd.isna(macd_line) and not pd.isna(signal_line) and not pd.isna(histogram):
                if len(self.df) > 1:
                    prev_macd_line = Decimal(str(self.df["MACD_Line"].iloc[-2]))
                    prev_signal_line = Decimal(str(self.df["MACD_Signal"].iloc[-2]))
                    if macd_line > signal_line and prev_macd_line <= prev_signal_line: signal_score += weight
                    elif macd_line < signal_line and prev_macd_line >= prev_signal_line: signal_score -= weight
                if len(self.df) > 1 and histogram > 0 and self.df["MACD_Hist"].iloc[-2] < 0: signal_score += weight * 0.2
                elif len(self.df) > 1 and histogram < 0 and self.df["MACD_Hist"].iloc[-2] > 0: signal_score -= weight * 0.2

        if active_indicators.get("adx", False):
            adx_val = self._get_indicator_value("ADX")
            plus_di = self._get_indicator_value("PlusDI")
            minus_di = self._get_indicator_value("MinusDI")
            weight = weights.get("adx_strength", 0.0)

            if not pd.isna(adx_val) and not pd.isna(plus_di) and not pd.isna(minus_di):
                if adx_val > ADX_STRONG_TREND_THRESHOLD:
                    if plus_di > minus_di: signal_score += weight
                    elif minus_di > plus_di: signal_score -= weight
                elif adx_val < ADX_WEAK_TREND_THRESHOLD: pass

        if active_indicators.get("ichimoku_cloud", False):
            tenkan_sen = self._get_indicator_value("Tenkan_Sen")
            kijun_sen = self._get_indicator_value("Kijun_Sen")
            senkou_span_a = self._get_indicator_value("Senkou_Span_A")
            senkou_span_b = self._get_indicator_value("Senkou_Span_B")
            chikou_span = self._get_indicator_value("Chikou_Span")
            weight = weights.get("ichimoku_confluence", 0.0)

            if not pd.isna(tenkan_sen) and not pd.isna(kijun_sen) and not pd.isna(senkou_span_a) and not pd.isna(senkou_span_b) and not pd.isna(chikou_span):
                if tenkan_sen > kijun_sen and self.df["Tenkan_Sen"].iloc[-2] <= self.df["Kijun_Sen"].iloc[-2]: signal_score += weight * 0.5
                elif tenkan_sen < kijun_sen and self.df["Tenkan_Sen"].iloc[-2] >= self.df["Kijun_Sen"].iloc[-2]: signal_score -= weight * 0.5

                if current_close > max(senkou_span_a, senkou_span_b) and self.df["close"].iloc[-2] <= max(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]): signal_score += weight * 0.7
                elif current_close < min(senkou_span_a, senkou_span_b) and self.df["close"].iloc[-2] >= min(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]): signal_score -= weight * 0.7

                if chikou_span > current_close and self.df["Chikou_Span"].iloc[-2] <= self.df["close"].iloc[-2]: signal_score += weight * 0.3
                elif chikou_span < current_close and self.df["Chikou_Span"].iloc[-2] >= self.df["close"].iloc[-2]: signal_score -= weight * 0.3

        if active_indicators.get("obv", False):
            obv_val = self._get_indicator_value("OBV")
            obv_ema = self._get_indicator_value("OBV_EMA")
            weight = weights.get("obv_momentum", 0.0)
            if not pd.isna(obv_val) and not pd.isna(obv_ema):
                if obv_val > obv_ema and self.df["OBV"].iloc[-2] <= self.df["OBV_EMA"].iloc[-2]: signal_score += weight * 0.5
                elif obv_val < obv_ema and self.df["OBV"].iloc[-2] >= self.df["OBV_EMA"].iloc[-2]: signal_score -= weight * 0.5
                if len(self.df) > 2:
                    if obv_val > self.df["OBV"].iloc[-2] and obv_val > self.df["OBV"].iloc[-3]: signal_score += weight * 0.2
                    elif obv_val < self.df["OBV"].iloc[-2] and obv_val < self.df["OBV"].iloc[-3]: signal_score -= weight * 0.2

        if active_indicators.get("cmf", False):
            cmf_val = self._get_indicator_value("CMF")
            weight = weights.get("cmf_flow", 0.0)
            if not pd.isna(cmf_val):
                if cmf_val > 0: signal_score += weight * 0.5
                elif cmf_val < 0: signal_score -= weight * 0.5
                if len(self.df) > 2:
                    if cmf_val > self.df["CMF"].iloc[-2] and cmf_val > self.df["CMF"].iloc[-3]: signal_score += weight * 0.3
                    elif cmf_val < self.df["CMF"].iloc[-2] and cmf_val < self.df["CMF"].iloc[-3]: signal_score -= weight * 0.3

        if self.config["mtf_analysis"]["enabled"] and mtf_trends:
            mtf_buy_score = sum(1 for trend in mtf_trends.values() if trend == "UP")
            mtf_sell_score = sum(-1 for trend in mtf_trends.values() if trend == "DOWN")
            if mtf_trends:
                normalized_mtf_score = (mtf_buy_score + mtf_sell_score) / len(mtf_trends)
                signal_score += weights.get("mtf_trend_confluence", 0.0) * normalized_mtf_score
                self.logger.debug(f"MTF Confluence: Score {normalized_mtf_score:.2f}")

        threshold = self.config["signal_score_threshold"]
        final_signal = "HOLD"
        if signal_score >= threshold: final_signal = "BUY"
        elif signal_score <= -threshold: final_signal = "SELL"

        self.logger.info(f"{NEON_YELLOW}Raw Technical Signal Score: {signal_score:.2f}, Final Technical Signal: {final_signal}{RESET}")
        return final_signal, signal_score


    # --- Remaining Indicator Implementations ---
    def calculate_true_range(self) -> pd.Series:
        """Calculate True Range (TR)."""
        if len(self.df) < MIN_DATA_POINTS_TR: return pd.Series(np.nan, index=self.df.index)
        high_low = self.df["high"] - self.df["low"]
        high_prev_close = (self.df["high"] - self.df["close"].shift()).abs()
        low_prev_close = (self.df["low"] - self.df["close"].shift()).abs()
        return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)

    def calculate_super_smoother(self, series: pd.Series, period: int) -> pd.Series:
        """Apply Ehlers SuperSmoother filter to reduce lag and noise."""
        if period <= 0 or len(series) < MIN_DATA_POINTS_SMOOTHER: return pd.Series(np.nan, index=series.index)
        series = pd.to_numeric(series, errors="coerce").dropna()
        if len(series) < MIN_DATA_POINTS_SMOOTHER: return pd.Series(np.nan, index=series.index)

        a1 = np.exp(-np.sqrt(2) * np.pi / period)
        b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / period)
        c1 = 1 - b1 + a1**2
        c2 = b1 - 2 * a1**2
        c3 = a1**2

        filt = pd.Series(0.0, index=series.index)
        if len(series) >= 1: filt.iloc = series.iloc
        if len(series) >= 2: filt.iloc = (series.iloc + series.iloc) / 2

        for i in range(2, len(series)):
            filt.iloc[i] = ((c1 / 2) * (series.iloc[i] + series.iloc[i - 1])) + (c2 * filt.iloc[i - 1]) - (c3 * filt.iloc[i - 2])
        return filt.reindex(self.df.index)

    def calculate_ehlers_supertrend(self, period: int, multiplier: float) -> Optional[pd.DataFrame]:
        """Calculate SuperTrend using Ehlers SuperSmoother for price and volatility."""
        if len(self.df) < period * 3: return None
        df_copy = self.df.copy()
        hl2 = (df_copy["high"] + df_copy["low"]) / 2
        smoothed_price = self.calculate_super_smoother(hl2, period)
        tr = self.calculate_true_range()
        smoothed_atr = self.calculate_super_smoother(tr, period)

        if smoothed_price is None or smoothed_atr is None: return None

        df_copy["smoothed_price"] = smoothed_price
        df_copy["smoothed_atr"] = smoothed_atr
        df_copy.dropna(subset=["smoothed_price", "smoothed_atr"], inplace=True)
        if df_copy.empty: return None

        upper_band = df_copy["smoothed_price"] + multiplier * df_copy["smoothed_atr"]
        lower_band = df_copy["smoothed_price"] - multiplier * df_copy["smoothed_atr"]

        direction = pd.Series(0, index=df_copy.index, dtype=int)
        supertrend = pd.Series(np.nan, index=df_copy.index)

        first_valid_idx = df_copy.index
        supertrend.loc[first_valid_idx] = lower_band.loc[first_valid_idx]

        for i in range(1, len(df_copy)):
            current_idx = df_copy.index[i]
            prev_idx = df_copy.index[i - 1]

            prev_direction = direction.loc[prev_idx]
            prev_supertrend = supertrend.loc[prev_idx]
            curr_close = df_copy["close"].loc[current_idx]

            if prev_direction == 1:
                supertrend.loc[current_idx] = max(lower_band.loc[current_idx], prev_supertrend)
                if curr_close < supertrend.loc[current_idx]:
                    direction.loc[current_idx] = -1
                    supertrend.loc[current_idx] = upper_band.loc[current_idx]
                else: direction.loc[current_idx] = 1
            elif prev_direction == -1:
                supertrend.loc[current_idx] = min(upper_band.loc[current_idx], prev_supertrend)
                if curr_close > supertrend.loc[current_idx]:
                    direction.loc[current_idx] = 1
                    supertrend.loc[current_idx] = lower_band.loc[current_idx]
                else: direction.loc[current_idx] = -1
            else:
                if curr_close > lower_band.loc[current_idx]:
                    direction.loc[current_idx] = 1
                    supertrend.loc[current_idx] = lower_band.loc[current_idx]
                else:
                    direction.loc[current_idx] = -1
                    supertrend.loc[current_idx] = upper_band.loc[current_idx]

        result = pd.DataFrame({"supertrend": supertrend, "direction": direction})
        return result.reindex(self.df.index)

    def calculate_macd(self, fast_period: int, slow_period: int, signal_period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Moving Average Convergence Divergence (MACD)."""
        if len(self.df) < slow_period + signal_period:
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        ema_fast = self.df["close"].ewm(span=fast_period, adjust=False).mean()
        ema_slow = self.df["close"].ewm(span=slow_period, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    def calculate_rsi(self, period: int) -> pd.Series:
        """Calculate Relative Strength Index (RSI)."""
        if len(self.df) <= period: return pd.Series(np.nan, index=self.df.index)
        delta = self.df["close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.ewm(span=period, adjust=False, min_periods=period).mean()
        avg_loss = loss.ewm(span=period, adjust=False, min_periods=period).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_stoch_rsi(self, period: int, k_period: int, d_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate Stochastic RSI."""
        if len(self.df) <= period: return pd.Series(np.nan), pd.Series(np.nan)
        rsi = self.calculate_rsi(period)

        lowest_rsi = rsi.rolling(window=period, min_periods=period).min()
        highest_rsi = rsi.rolling(window=period, min_periods=period).max()

        stoch_rsi_k_raw = ((rsi - lowest_rsi) / (highest_rsi - lowest_rsi))
        stoch_rsi_k_raw = stoch_rsi_k_raw.replace([np.inf, -np.inf], np.nan).fillna(0) * 100

        stoch_rsi_k = stoch_rsi_k_raw.rolling(window=k_period, min_periods=k_period).mean()
        stoch_rsi_d = stoch_rsi_k.rolling(window=d_period, min_periods=d_period).mean()

        return stoch_rsi_k, stoch_rsi_d

    def calculate_adx(self, period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Average Directional Index (ADX)."""
        if len(self.df) < period * 2: return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        tr = self.calculate_true_range()
        plus_dm = self.df["high"].diff().clip(lower=0)
        minus_dm = -self.df["low"].diff().clip(lower=0)

        plus_dm_final = plus_dm.copy()
        minus_dm_final = minus_dm.copy()
        condition_plus_wins = (plus_dm_final > minus_dm_final)
        condition_minus_wins = (minus_dm_final > plus_dm_final)

        plus_dm_final[condition_minus_wins] = 0
        minus_dm_final[condition_plus_wins] = 0

        atr = tr.ewm(span=period, adjust=False).mean()
        plus_di = (plus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100
        minus_di = (minus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100

        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)).replace([np.inf, -np.inf], np.nan).fillna(0) * 100
        adx = dx.ewm(span=period, adjust=False).mean()

        return adx, plus_di, minus_di

    def calculate_bollinger_bands(self, period: int, std_dev: float) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands."""
        if len(self.df) < period: return (pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan))
        middle_band = self.df["close"].rolling(window=period, min_periods=period).mean()
        std = self.df["close"].rolling(window=period, min_periods=period).std()
        upper_band = middle_band + (std * std_dev)
        lower_band = middle_band - (std * std_dev)
        return upper_band, middle_band, lower_band

    def calculate_vwap(self) -> pd.Series:
        """Calculate Volume Weighted Average Price (VWAP)."""
        if self.df.empty: return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        cumulative_tp_vol = (typical_price * self.df["volume"]).cumsum()
        cumulative_vol = self.df["volume"].cumsum()
        vwap = cumulative_tp_vol / cumulative_vol
        return vwap

    def calculate_cci(self, period: int) -> pd.Series:
        """Calculate Commodity Channel Index (CCI)."""
        if len(self.df) < period: return pd.Series(np.nan, index=self.df.index)
        tp = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        sma_tp = tp.rolling(window=period, min_periods=period).mean()
        mad = tp.rolling(window=period, min_periods=period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=False)
        cci = (tp - sma_tp) / (0.015 * mad)
        cci = cci.replace([np.inf, -np.inf], np.nan).fillna(0)
        return cci

    def calculate_williams_r(self, period: int) -> pd.Series:
        """Calculate Williams %R."""
        if len(self.df) < period: return pd.Series(np.nan, index=self.df.index)
        highest_high = self.df["high"].rolling(window=period, min_periods=period).max()
        lowest_low = self.df["low"].rolling(window=period, min_periods=period).min()
        wr = -100 * ((highest_high - self.df["close"]) / (highest_high - lowest_low))
        wr = wr.replace([np.inf, -np.inf], np.nan).fillna(-50)
        return wr

    def calculate_ichimoku_cloud(self, tenkan_period: int, kijun_period: int, senkou_span_b_period: int, chikou_span_offset: int) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
        """Calculate Ichimoku Cloud components."""
        if (len(self.df) < max(tenkan_period, kijun_period, senkou_span_b_period) + chikou_span_offset):
            return (pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan))

        tenkan_sen = (self.df["high"].rolling(window=tenkan_period).max() + self.df["low"].rolling(window=tenkan_period).min()) / 2
        kijun_sen = (self.df["high"].rolling(window=kijun_period).max() + self.df["low"].rolling(window=kijun_period).min()) / 2
        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun_period)
        senkou_span_b = ((self.df["high"].rolling(window=senkou_span_b_period).max() + self.df["low"].rolling(window=senkou_span_b_period).min()) / 2).shift(kijun_period)
        chikou_span = self.df["close"].shift(-chikou_span_offset)

        return tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span

    def calculate_mfi(self, period: int) -> pd.Series:
        """Calculate Money Flow Index (MFI)."""
        if len(self.df) <= period: return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        money_flow = typical_price * self.df["volume"]

        positive_flow = pd.Series(0.0, index=self.df.index)
        negative_flow = pd.Series(0.0, index=self.df.index)

        for i in range(1, len(self.df)):
            if typical_price.iloc[i] > typical_price.iloc[i - 1]: positive_flow.iloc[i] = money_flow.iloc[i]
            elif typical_price.iloc[i] < typical_price.iloc[i - 1]: negative_flow.iloc[i] = money_flow.iloc[i]

        positive_mf_sum = positive_flow.rolling(window=period, min_periods=period).sum()
        negative_mf_sum = negative_flow.rolling(window=period, min_periods=period).sum()

        mf_ratio = positive_mf_sum / negative_mf_sum
        mfi = 100 - (100 / (1 + mf_ratio))
        mfi = mfi.replace([np.inf, -np.inf], np.nan).fillna(50)
        return mfi

    def calculate_obv(self, ema_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate On-Balance Volume (OBV) and its EMA."""
        if len(self.df) < MIN_DATA_POINTS_OBV: return pd.Series(np.nan), pd.Series(np.nan)

        obv = pd.Series(0.0, index=self.df.index)
        for i in range(1, len(self.df)):
            if self.df["close"].iloc[i] > self.df["close"].iloc[i - 1]: obv.iloc[i] = obv.iloc[i - 1] + self.df["volume"].iloc[i]
            elif self.df["close"].iloc[i] < self.df["close"].iloc[i - 1]: obv.iloc[i] = obv.iloc[i - 1] - self.df["volume"].iloc[i]
            else: obv.iloc[i] = obv.iloc[i - 1]

        obv_ema = obv.ewm(span=ema_period, adjust=False).mean()
        return obv, obv_ema

    def calculate_cmf(self, period: int) -> pd.Series:
        """Calculate Chaikin Money Flow (CMF)."""
        if len(self.df) < period: return pd.Series(np.nan)

        mfm = ((self.df["close"] - self.df["low"]) - (self.df["high"] - self.df["close"])) / (self.df["high"] - self.df["low"])
        mfm = mfm.replace([np.inf, -np.inf], np.nan).fillna(0)

        mfv = mfm * self.df["volume"]
        cmf = (mfv.rolling(window=period).sum() / self.df["volume"].rolling(window=period).sum())
        cmf = cmf.replace([np.inf, -np.inf], np.nan).fillna(0)

        return cmf

    def calculate_psar(self, acceleration: float, max_acceleration: float) -> tuple[pd.Series, pd.Series]:
        """Calculate Parabolic SAR."""
        if len(self.df) < MIN_DATA_POINTS_PSAR: return pd.Series(np.nan), pd.Series(np.nan)

        psar = self.df["close"].copy()
        bull = pd.Series(True, index=self.df.index)
        af = acceleration
        ep = self.df["low"].iloc if self.df["close"].iloc < self.df["close"].iloc else self.df["high"].iloc

        for i in range(1, len(self.df)):
            if bull.iloc[i - 1]:
                psar.iloc[i] = psar.iloc[i - 1] + af * (ep - psar.iloc[i - 1])
            else:
                psar.iloc[i] = psar.iloc[i - 1] - af * (psar.iloc[i - 1] - ep)

            reverse = False
            if bull.iloc[i - 1] and self.df["low"].iloc[i] < psar.iloc[i]:
                bull.iloc[i] = False; reverse = True
            elif not bull.iloc[i - 1] and self.df["high"].iloc[i] > psar.iloc[i]:
                bull.iloc[i] = True; reverse = True
            else: bull.iloc[i] = bull.iloc[i - 1]

            if reverse:
                af = acceleration
                ep = self.df["high"].iloc[i] if bull.iloc[i] else self.df["low"].iloc[i]
            elif bull.iloc[i]:
                if self.df["high"].iloc[i] > ep: ep = self.df["high"].iloc[i]; af = min(af + acceleration, max_acceleration)
            elif self.df["low"].iloc[i] < ep: ep = self.df["low"].iloc[i]; af = min(af + acceleration, max_acceleration)

            if bull.iloc[i]: psar.iloc[i] = min(psar.iloc[i], self.df["low"].iloc[i], self.df["low"].iloc[i-1])
            else: psar.iloc[i] = max(psar.iloc[i], self.df["high"].iloc[i], self.df["high"].iloc[i-1])

            if bull.iloc[i] and psar.iloc[i] > self.df["low"].iloc[i]: psar.iloc[i] = self.df["low"].iloc[i]
            elif not bull.iloc[i] and psar.iloc[i] < self.df["high"].iloc[i]: psar.iloc[i] = self.df["high"].iloc[i]

        direction = pd.Series(0, index=self.df.index, dtype=int)
        direction[psar < self.df["close"]] = 1
        direction[psar > self.df["close"]] = -1

        return psar, direction

    def calculate_fibonacci_levels(self) -> None:
        """Calculate Fibonacci retracement levels based on a recent high-low swing."""
        window = self.config["indicator_settings"]["fibonacci_window"]
        if len(self.df) < window:
            self.logger.warning(f"{NEON_YELLOW}Not enough data for Fibonacci levels (need {window} bars).{RESET}")
            return

        recent_high = self.df["high"].iloc[-window:].max()
        recent_low = self.df["low"].iloc[-window:].min()
        diff = recent_high - recent_low

        self.fib_levels = {
            "0.0%": Decimal(str(recent_high)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "23.6%": Decimal(str(recent_high - 0.236 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "38.2%": Decimal(str(recent_high - 0.382 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "50.0%": Decimal(str(recent_high - 0.500 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "61.8%": Decimal(str(recent_high - 0.618 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "78.6%": Decimal(str(recent_high - 0.786 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "100.0%": Decimal(str(recent_low)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
        }
        self.logger.debug(f"Calculated Fibonacci levels: {self.fib_levels}")

    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        """Safely retrieve an indicator value."""
        return self.indicator_values.get(key, default)

    def _check_orderbook(self, current_price: Decimal, orderbook_data: dict) -> float:
        """Analyze orderbook imbalance."""
        bids = orderbook_data.get("b", [])
        asks = orderbook_data.get("a", [])

        bid_volume = sum(Decimal(b) for b in bids)
        ask_volume = sum(Decimal(a) for a in asks)

        if bid_volume + ask_volume == 0: return 0.0

        imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
        self.logger.debug(f"Orderbook Imbalance: {imbalance:.4f} (Bids: {bid_volume}, Asks: {ask_volume})")
        return float(imbalance)

    def _get_mtf_trend(self, higher_tf_df: pd.DataFrame, indicator_type: str) -> str:
        """Determine trend from higher timeframe using specified indicator."""
        if higher_tf_df.empty: return "UNKNOWN"

        last_close = higher_tf_df["close"].iloc[-1]
        period = self.config["mtf_analysis"]["trend_period"]

        if indicator_type == "sma":
            if len(higher_tf_df) < period: return "UNKNOWN"
            sma = higher_tf_df["close"].rolling(window=period, min_periods=period).mean().iloc[-1]
            if last_close > sma: return "UP"
            if last_close < sma: return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ema":
            if len(higher_tf_df) < period: return "UNKNOWN"
            ema = higher_tf_df["close"].ewm(span=period, adjust=False, min_periods=period).mean().iloc[-1]
            if last_close > ema: return "UP"
            if last_close < ema: return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ehlers_supertrend":
            temp_analyzer = TradingAnalyzer(higher_tf_df, self.config, self.logger, self.symbol)
            st_result = temp_analyzer.calculate_ehlers_supertrend(
                self.indicator_settings["ehlers_slow_period"],
                self.indicator_settings["ehlers_slow_multiplier"],
            )
            if st_result is not None and not st_result.empty:
                st_dir = st_result["direction"].iloc[-1]
                if st_dir == 1: return "UP"
                if st_dir == -1: return "DOWN"
            return "UNKNOWN"
        return "UNKNOWN"

    def generate_trading_signal(
        self, current_price: Decimal, orderbook_data: dict | None, mtf_trends: dict[str, str]
    ) -> tuple[str, float]:
        """Generate a signal using confluence of indicators, including Ehlers SuperTrend."""
        signal_score = 0.0
        active_indicators = self.config["indicators"]
        weights = self.weights

        if self.df.empty:
            self.logger.warning(f"{NEON_YELLOW}DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}")
            return "HOLD", 0.0

        current_close = Decimal(str(self.df["close"].iloc[-1]))
        prev_close = Decimal(str(self.df["close"].iloc[-2])) if len(self.df) > 1 else current_close
        isd = self.indicator_settings

        # --- Indicator Scoring ---
        if active_indicators.get("ema_alignment", False):
            ema_short = self._get_indicator_value("EMA_Short")
            ema_long = self._get_indicator_value("EMA_Long")
            if not pd.isna(ema_short) and not pd.isna(ema_long):
                if ema_short > ema_long: signal_score += weights.get("ema_alignment", 0)
                elif ema_short < ema_long: signal_score -= weights.get("ema_alignment", 0)

        if active_indicators.get("sma_trend_filter", False):
            sma_long = self._get_indicator_value("SMA_Long")
            if not pd.isna(sma_long):
                if current_close > sma_long: signal_score += weights.get("sma_trend_filter", 0)
                elif current_close < sma_long: signal_score -= weights.get("sma_trend_filter", 0)

        if active_indicators.get("momentum", False):
            rsi = self._get_indicator_value("RSI")
            stoch_k = self._get_indicator_value("StochRSI_K")
            stoch_d = self._get_indicator_value("StochRSI_D")
            cci = self._get_indicator_value("CCI")
            wr = self._get_indicator_value("WR")
            mfi = self._get_indicator_value("MFI")

            if not pd.isna(rsi):
                if rsi < isd["rsi_oversold"]: signal_score += weights.get("rsi", 0) * 0.5
                elif rsi > isd["rsi_overbought"]: signal_score -= weights.get("rsi", 0) * 0.5

            if not pd.isna(stoch_k) and not pd.isna(stoch_d):
                if stoch_k > stoch_d and stoch_k < isd["stoch_rsi_oversold"]: signal_score += weights.get("stoch_rsi", 0) * 0.5
                elif stoch_k < stoch_d and stoch_k > isd["stoch_rsi_overbought"]: signal_score -= weights.get("stoch_rsi", 0) * 0.5

            if not pd.isna(cci):
                if cci < isd["cci_oversold"]: signal_score += weights.get("cci", 0) * 0.5
                elif cci > isd["cci_overbought"]: signal_score -= weights.get("cci", 0) * 0.5

            if not pd.isna(wr):
                if wr < isd["williams_r_oversold"]: signal_score += weights.get("wr", 0) * 0.5
                elif wr > isd["williams_r_overbought"]: signal_score -= weights.get("wr", 0) * 0.5

            if not pd.isna(mfi):
                if mfi < isd["mfi_oversold"]: signal_score += weights.get("mfi", 0) * 0.5
                elif mfi > isd["mfi_overbought"]: signal_score -= weights.get("mfi", 0) * 0.5

        if active_indicators.get("bollinger_bands", False):
            bb_upper = self._get_indicator_value("BB_Upper")
            bb_lower = self._get_indicator_value("BB_Lower")
            if not pd.isna(bb_upper) and not pd.isna(bb_lower):
                if current_close < bb_lower: signal_score += weights.get("bollinger_bands", 0) * 0.5
                elif current_close > bb_upper: signal_score -= weights.get("bollinger_bands", 0) * 0.5

        if active_indicators.get("vwap", False):
            vwap = self._get_indicator_value("VWAP")
            if not pd.isna(vwap):
                if current_close > vwap: signal_score += weights.get("vwap", 0) * 0.2
                elif current_close < vwap: signal_score -= weights.get("vwap", 0) * 0.2

                if len(self.df) > 1:
                    prev_close = Decimal(str(self.df["close"].iloc[-2]))
                    prev_vwap = Decimal(str(self.df["VWAP"].iloc[-2]))
                    if current_close > vwap and prev_close <= prev_vwap: signal_score += weights.get("vwap", 0) * 0.3
                    elif current_close < vwap and prev_close >= prev_vwap: signal_score -= weights.get("vwap", 0) * 0.3

        if active_indicators.get("psar", False):
            psar_val = self._get_indicator_value("PSAR_Val")
            psar_dir = self._get_indicator_value("PSAR_Dir")
            if not pd.isna(psar_val) and not pd.isna(psar_dir):
                if psar_dir == 1: signal_score += weights.get("psar", 0) * 0.5
                elif psar_dir == -1: signal_score -= weights.get("psar", 0) * 0.5

                if len(self.df) > 1:
                    prev_close = Decimal(str(self.df["close"].iloc[-2]))
                    prev_psar_val = Decimal(str(self.df["PSAR_Val"].iloc[-2]))
                    if current_close > psar_val and prev_close <= prev_psar_val: signal_score += weights.get("psar", 0) * 0.4
                    elif current_close < psar_val and prev_close >= prev_psar_val: signal_score -= weights.get("psar", 0) * 0.4

        if active_indicators.get("orderbook_imbalance", False) and orderbook_data:
            imbalance = self._check_orderbook(current_price, orderbook_data)
            signal_score += imbalance * weights.get("orderbook_imbalance", 0)

        if active_indicators.get("fibonacci_levels", False) and self.fib_levels:
            for level_name, level_price in self.fib_levels.items():
                if level_name not in ["0.0%", "100.0%"] and abs(current_price - level_price) / current_price < Decimal("0.001"):
                    if len(self.df) > 1:
                        prev_close = Decimal(str(self.df["close"].iloc[-2]))
                        if current_close > prev_close and current_close > level_price: signal_score += weights.get("fibonacci_levels", 0) * 0.1
                        elif current_close < prev_close and current_close < level_price: signal_score -= weights.get("fibonacci_levels", 0) * 0.1

        if active_indicators.get("ehlers_supertrend", False):
            st_fast_dir = self._get_indicator_value("ST_Fast_Dir")
            st_slow_dir = self._get_indicator_value("ST_Slow_Dir")
            prev_st_fast_dir = self.df["st_fast_dir"].iloc[-2] if "st_fast_dir" in self.df.columns and len(self.df) > 1 else np.nan
            weight = weights.get("ehlers_supertrend_alignment", 0.0)

            if not pd.isna(st_fast_dir) and not pd.isna(st_slow_dir) and not pd.isna(prev_st_fast_dir):
                if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1: signal_score += weight
                elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1: signal_score -= weight
                elif st_slow_dir == 1 and st_fast_dir == 1: signal_score += weight * 0.3
                elif st_slow_dir == -1 and st_fast_dir == -1: signal_score -= weight * 0.3

        if active_indicators.get("macd", False):
            macd_line = self._get_indicator_value("MACD_Line")
            signal_line = self._get_indicator_value("MACD_Signal")
            histogram = self._get_indicator_value("MACD_Hist")
            weight = weights.get("macd_alignment", 0.0)

            if not pd.isna(macd_line) and not pd.isna(signal_line) and not pd.isna(histogram):
                if len(self.df) > 1:
                    prev_macd_line = Decimal(str(self.df["MACD_Line"].iloc[-2]))
                    prev_signal_line = Decimal(str(self.df["MACD_Signal"].iloc[-2]))
                    if macd_line > signal_line and prev_macd_line <= prev_signal_line: signal_score += weight
                    elif macd_line < signal_line and prev_macd_line >= prev_signal_line: signal_score -= weight
                if len(self.df) > 1 and histogram > 0 and self.df["MACD_Hist"].iloc[-2] < 0: signal_score += weight * 0.2
                elif len(self.df) > 1 and histogram < 0 and self.df["MACD_Hist"].iloc[-2] > 0: signal_score -= weight * 0.2

        if active_indicators.get("adx", False):
            adx_val = self._get_indicator_value("ADX")
            plus_di = self._get_indicator_value("PlusDI")
            minus_di = self._get_indicator_value("MinusDI")
            weight = weights.get("adx_strength", 0.0)

            if not pd.isna(adx_val) and not pd.isna(plus_di) and not pd.isna(minus_di):
                if adx_val > ADX_STRONG_TREND_THRESHOLD:
                    if plus_di > minus_di: signal_score += weight
                    elif minus_di > plus_di: signal_score -= weight
                elif adx_val < ADX_WEAK_TREND_THRESHOLD: pass

        if active_indicators.get("ichimoku_cloud", False):
            tenkan_sen = self._get_indicator_value("Tenkan_Sen")
            kijun_sen = self._get_indicator_value("Kijun_Sen")
            senkou_span_a = self._get_indicator_value("Senkou_Span_A")
            senkou_span_b = self._get_indicator_value("Senkou_Span_B")
            chikou_span = self._get_indicator_value("Chikou_Span")
            weight = weights.get("ichimoku_confluence", 0.0)

            if not pd.isna(tenkan_sen) and not pd.isna(kijun_sen) and not pd.isna(senkou_span_a) and not pd.isna(senkou_span_b) and not pd.isna(chikou_span):
                if tenkan_sen > kijun_sen and self.df["Tenkan_Sen"].iloc[-2] <= self.df["Kijun_Sen"].iloc[-2]: signal_score += weight * 0.5
                elif tenkan_sen < kijun_sen and self.df["Tenkan_Sen"].iloc[-2] >= self.df["Kijun_Sen"].iloc[-2]: signal_score -= weight * 0.5

                if current_close > max(senkou_span_a, senkou_span_b) and self.df["close"].iloc[-2] <= max(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]): signal_score += weight * 0.7
                elif current_close < min(senkou_span_a, senkou_span_b) and self.df["close"].iloc[-2] >= min(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]): signal_score -= weight * 0.7

                if chikou_span > current_close and self.df["Chikou_Span"].iloc[-2] <= self.df["close"].iloc[-2]: signal_score += weight * 0.3
                elif chikou_span < current_close and self.df["Chikou_Span"].iloc[-2] >= self.df["close"].iloc[-2]: signal_score -= weight * 0.3

        if active_indicators.get("obv", False):
            obv_val = self._get_indicator_value("OBV")
            obv_ema = self._get_indicator_value("OBV_EMA")
            weight = weights.get("obv_momentum", 0.0)
            if not pd.isna(obv_val) and not pd.isna(obv_ema):
                if obv_val > obv_ema and self.df["OBV"].iloc[-2] <= self.df["OBV_EMA"].iloc[-2]: signal_score += weight * 0.5
                elif obv_val < obv_ema and self.df["OBV"].iloc[-2] >= self.df["OBV_EMA"].iloc[-2]: signal_score -= weight * 0.5
                if len(self.df) > 2:
                    if obv_val > self.df["OBV"].iloc[-2] and obv_val > self.df["OBV"].iloc[-3]: signal_score += weight * 0.2
                    elif obv_val < self.df["OBV"].iloc[-2] and obv_val < self.df["OBV"].iloc[-3]: signal_score -= weight * 0.2

        if active_indicators.get("cmf", False):
            cmf_val = self._get_indicator_value("CMF")
            weight = weights.get("cmf_flow", 0.0)
            if not pd.isna(cmf_val):
                if cmf_val > 0: signal_score += weight * 0.5
                elif cmf_val < 0: signal_score -= weight * 0.5
                if len(self.df) > 2:
                    if cmf_val > self.df["CMF"].iloc[-2] and cmf_val > self.df["CMF"].iloc[-3]: signal_score += weight * 0.3
                    elif cmf_val < self.df["CMF"].iloc[-2] and cmf_val < self.df["CMF"].iloc[-3]: signal_score -= weight * 0.3

        if self.config["mtf_analysis"]["enabled"] and mtf_trends:
            mtf_buy_score = sum(1 for trend in mtf_trends.values() if trend == "UP")
            mtf_sell_score = sum(-1 for trend in mtf_trends.values() if trend == "DOWN")
            if mtf_trends:
                normalized_mtf_score = (mtf_buy_score + mtf_sell_score) / len(mtf_trends)
                signal_score += weights.get("mtf_trend_confluence", 0.0) * normalized_mtf_score
                self.logger.debug(f"MTF Confluence: Score {normalized_mtf_score:.2f}")

        threshold = self.config["signal_score_threshold"]
        final_signal = "HOLD"
        if signal_score >= threshold: final_signal = "BUY"
        elif signal_score <= -threshold: final_signal = "SELL"

        self.logger.info(f"{NEON_YELLOW}Raw Technical Signal Score: {signal_score:.2f}, Final Technical Signal: {final_signal}{RESET}")
        return final_signal, signal_score


    # --- Remaining Indicator Implementations ---
    def calculate_true_range(self) -> pd.Series:
        """Calculate True Range (TR)."""
        if len(self.df) < MIN_DATA_POINTS_TR: return pd.Series(np.nan, index=self.df.index)
        high_low = self.df["high"] - self.df["low"]
        high_prev_close = (self.df["high"] - self.df["close"].shift()).abs()
        low_prev_close = (self.df["low"] - self.df["close"].shift()).abs()
        return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)

    def calculate_super_smoother(self, series: pd.Series, period: int) -> pd.Series:
        """Apply Ehlers SuperSmoother filter to reduce lag and noise."""
        if period <= 0 or len(series) < MIN_DATA_POINTS_SMOOTHER: return pd.Series(np.nan, index=series.index)
        series = pd.to_numeric(series, errors="coerce").dropna()
        if len(series) < MIN_DATA_POINTS_SMOOTHER: return pd.Series(np.nan, index=series.index)

        a1 = np.exp(-np.sqrt(2) * np.pi / period)
        b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / period)
        c1 = 1 - b1 + a1**2
        c2 = b1 - 2 * a1**2
        c3 = a1**2

        filt = pd.Series(0.0, index=series.index)
        if len(series) >= 1: filt.iloc = series.iloc
        if len(series) >= 2: filt.iloc = (series.iloc + series.iloc) / 2

        for i in range(2, len(series)):
            filt.iloc[i] = ((c1 / 2) * (series.iloc[i] + series.iloc[i - 1])) + (c2 * filt.iloc[i - 1]) - (c3 * filt.iloc[i - 2])
        return filt.reindex(self.df.index)

    def calculate_ehlers_supertrend(self, period: int, multiplier: float) -> Optional[pd.DataFrame]:
        """Calculate SuperTrend using Ehlers SuperSmoother for price and volatility."""
        if len(self.df) < period * 3: return None
        df_copy = self.df.copy()
        hl2 = (df_copy["high"] + df_copy["low"]) / 2
        smoothed_price = self.calculate_super_smoother(hl2, period)
        tr = self.calculate_true_range()
        smoothed_atr = self.calculate_super_smoother(tr, period)

        if smoothed_price is None or smoothed_atr is None: return None

        df_copy["smoothed_price"] = smoothed_price
        df_copy["smoothed_atr"] = smoothed_atr
        df_copy.dropna(subset=["smoothed_price", "smoothed_atr"], inplace=True)
        if df_copy.empty: return None

        upper_band = df_copy["smoothed_price"] + multiplier * df_copy["smoothed_atr"]
        lower_band = df_copy["smoothed_price"] - multiplier * df_copy["smoothed_atr"]

        direction = pd.Series(0, index=df_copy.index, dtype=int)
        supertrend = pd.Series(np.nan, index=df_copy.index)

        first_valid_idx = df_copy.index
        supertrend.loc[first_valid_idx] = lower_band.loc[first_valid_idx]

        for i in range(1, len(df_copy)):
            current_idx = df_copy.index[i]
            prev_idx = df_copy.index[i - 1]

            prev_direction = direction.loc[prev_idx]
            prev_supertrend = supertrend.loc[prev_idx]
            curr_close = df_copy["close"].loc[current_idx]

            if prev_direction == 1:
                supertrend.loc[current_idx] = max(lower_band.loc[current_idx], prev_supertrend)
                if curr_close < supertrend.loc[current_idx]:
                    direction.loc[current_idx] = -1
                    supertrend.loc[current_idx] = upper_band.loc[current_idx]
                else: direction.loc[current_idx] = 1
            elif prev_direction == -1:
                supertrend.loc[current_idx] = min(upper_band.loc[current_idx], prev_supertrend)
                if curr_close > supertrend.loc[current_idx]:
                    direction.loc[current_idx] = 1
                    supertrend.loc[current_idx] = lower_band.loc[current_idx]
                else: direction.loc[current_idx] = -1
            else:
                if curr_close > lower_band.loc[current_idx]:
                    direction.loc[current_idx] = 1
                    supertrend.loc[current_idx] = lower_band.loc[current_idx]
                else:
                    direction.loc[current_idx] = -1
                    supertrend.loc[current_idx] = upper_band.loc[current_idx]

        result = pd.DataFrame({"supertrend": supertrend, "direction": direction})
        return result.reindex(self.df.index)

    def calculate_macd(self, fast_period: int, slow_period: int, signal_period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Moving Average Convergence Divergence (MACD)."""
        if len(self.df) < slow_period + signal_period:
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        ema_fast = self.df["close"].ewm(span=fast_period, adjust=False).mean()
        ema_slow = self.df["close"].ewm(span=slow_period, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    def calculate_rsi(self, period: int) -> pd.Series:
        """Calculate Relative Strength Index (RSI)."""
        if len(self.df) <= period: return pd.Series(np.nan, index=self.df.index)
        delta = self.df["close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.ewm(span=period, adjust=False, min_periods=period).mean()
        avg_loss = loss.ewm(span=period, adjust=False, min_periods=period).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_stoch_rsi(self, period: int, k_period: int, d_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate Stochastic RSI."""
        if len(self.df) <= period: return pd.Series(np.nan), pd.Series(np.nan)
        rsi = self.calculate_rsi(period)

        lowest_rsi = rsi.rolling(window=period, min_periods=period).min()
        highest_rsi = rsi.rolling(window=period, min_periods=period).max()

        stoch_rsi_k_raw = ((rsi - lowest_rsi) / (highest_rsi - lowest_rsi))
        stoch_rsi_k_raw = stoch_rsi_k_raw.replace([np.inf, -np.inf], np.nan).fillna(0) * 100

        stoch_rsi_k = stoch_rsi_k_raw.rolling(window=k_period, min_periods=k_period).mean()
        stoch_rsi_d = stoch_rsi_k.rolling(window=d_period, min_periods=d_period).mean()

        return stoch_rsi_k, stoch_rsi_d

    def calculate_adx(self, period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Average Directional Index (ADX)."""
        if len(self.df) < period * 2: return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        tr = self.calculate_true_range()
        plus_dm = self.df["high"].diff().clip(lower=0)
        minus_dm = -self.df["low"].diff().clip(lower=0)

        plus_dm_final = plus_dm.copy()
        minus_dm_final = minus_dm.copy()
        condition_plus_wins = (plus_dm_final > minus_dm_final)
        condition_minus_wins = (minus_dm_final > plus_dm_final)

        plus_dm_final[condition_minus_wins] = 0
        minus_dm_final[condition_plus_wins] = 0

        atr = tr.ewm(span=period, adjust=False).mean()
        plus_di = (plus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100
        minus_di = (minus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100

        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)).replace([np.inf, -np.inf], np.nan).fillna(0) * 100
        adx = dx.ewm(span=period, adjust=False).mean()

        return adx, plus_di, minus_di

    def calculate_bollinger_bands(self, period: int, std_dev: float) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands."""
        if len(self.df) < period: return (pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan))
        middle_band = self.df["close"].rolling(window=period, min_periods=period).mean()
        std = self.df["close"].rolling(window=period, min_periods=period).std()
        upper_band = middle_band + (std * std_dev)
        lower_band = middle_band - (std * std_dev)
        return upper_band, middle_band, lower_band

    def calculate_vwap(self) -> pd.Series:
        """Calculate Volume Weighted Average Price (VWAP)."""
        if self.df.empty: return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        cumulative_tp_vol = (typical_price * self.df["volume"]).cumsum()
        cumulative_vol = self.df["volume"].cumsum()
        vwap = cumulative_tp_vol / cumulative_vol
        return vwap

    def calculate_cci(self, period: int) -> pd.Series:
        """Calculate Commodity Channel Index (CCI)."""
        if len(self.df) < period: return pd.Series(np.nan, index=self.df.index)
        tp = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        sma_tp = tp.rolling(window=period, min_periods=period).mean()
        mad = tp.rolling(window=period, min_periods=period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=False)
        cci = (tp - sma_tp) / (0.015 * mad)
        cci = cci.replace([np.inf, -np.inf], np.nan).fillna(0)
        return cci

    def calculate_williams_r(self, period: int) -> pd.Series:
        """Calculate Williams %R."""
        if len(self.df) < period: return pd.Series(np.nan, index=self.df.index)
        highest_high = self.df["high"].rolling(window=period, min_periods=period).max()
        lowest_low = self.df["low"].rolling(window=period, min_periods=period).min()
        wr = -100 * ((highest_high - self.df["close"]) / (highest_high - lowest_low))
        wr = wr.replace([np.inf, -np.inf], np.nan).fillna(-50)
        return wr

    def calculate_ichimoku_cloud(self, tenkan_period: int, kijun_period: int, senkou_span_b_period: int, chikou_span_offset: int) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
        """Calculate Ichimoku Cloud components."""
        if (len(self.df) < max(tenkan_period, kijun_period, senkou_span_b_period) + chikou_span_offset):
            return (pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan))

        tenkan_sen = (self.df["high"].rolling(window=tenkan_period).max() + self.df["low"].rolling(window=tenkan_period).min()) / 2
        kijun_sen = (self.df["high"].rolling(window=kijun_period).max() + self.df["low"].rolling(window=kijun_period).min()) / 2
        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun_period)
        senkou_span_b = ((self.df["high"].rolling(window=senkou_span_b_period).max() + self.df["low"].rolling(window=senkou_span_b_period).min()) / 2).shift(kijun_period)
        chikou_span = self.df["close"].shift(-chikou_span_offset)

        return tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span

    def calculate_mfi(self, period: int) -> pd.Series:
        """Calculate Money Flow Index (MFI)."""
        if len(self.df) <= period: return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        money_flow = typical_price * self.df["volume"]

        positive_flow = pd.Series(0.0, index=self.df.index)
        negative_flow = pd.Series(0.0, index=self.df.index)

        for i in range(1, len(self.df)):
            if typical_price.iloc[i] > typical_price.iloc[i - 1]: positive_flow.iloc[i] = money_flow.iloc[i]
            elif typical_price.iloc[i] < typical_price.iloc[i - 1]: negative_flow.iloc[i] = money_flow.iloc[i]

        positive_mf_sum = positive_flow.rolling(window=period, min_periods=period).sum()
        negative_mf_sum = negative_flow.rolling(window=period, min_periods=period).sum()

        mf_ratio = positive_mf_sum / negative_mf_sum
        mfi = 100 - (100 / (1 + mf_ratio))
        mfi = mfi.replace([np.inf, -np.inf], np.nan).fillna(50)
        return mfi

    def calculate_obv(self, ema_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate On-Balance Volume (OBV) and its EMA."""
        if len(self.df) < MIN_DATA_POINTS_OBV: return pd.Series(np.nan), pd.Series(np.nan)

        obv = pd.Series(0.0, index=self.df.index)
        for i in range(1, len(self.df)):
            if self.df["close"].iloc[i] > self.df["close"].iloc[i - 1]: obv.iloc[i] = obv.iloc[i - 1] + self.df["volume"].iloc[i]
            elif self.df["close"].iloc[i] < self.df["close"].iloc[i - 1]: obv.iloc[i] = obv.iloc[i - 1] - self.df["volume"].iloc[i]
            else: obv.iloc[i] = obv.iloc[i - 1]

        obv_ema = obv.ewm(span=ema_period, adjust=False).mean()
        return obv, obv_ema

    def calculate_cmf(self, period: int) -> pd.Series:
        """Calculate Chaikin Money Flow (CMF)."""
        if len(self.df) < period: return pd.Series(np.nan)

        mfm = ((self.df["close"] - self.df["low"]) - (self.df["high"] - self.df["close"])) / (self.df["high"] - self.df["low"])
        mfm = mfm.replace([np.inf, -np.inf], np.nan).fillna(0)

        mfv = mfm * self.df["volume"]
        cmf = (mfv.rolling(window=period).sum() / self.df["volume"].rolling(window=period).sum())
        cmf = cmf.replace([np.inf, -np.inf], np.nan).fillna(0)

        return cmf

    def calculate_psar(self, acceleration: float, max_acceleration: float) -> tuple[pd.Series, pd.Series]:
        """Calculate Parabolic SAR."""
        if len(self.df) < MIN_DATA_POINTS_PSAR: return pd.Series(np.nan), pd.Series(np.nan)

        psar = self.df["close"].copy()
        bull = pd.Series(True, index=self.df.index)
        af = acceleration
        ep = self.df["low"].iloc if self.df["close"].iloc < self.df["close"].iloc else self.df["high"].iloc

        for i in range(1, len(self.df)):
            if bull.iloc[i - 1]:
                psar.iloc[i] = psar.iloc[i - 1] + af * (ep - psar.iloc[i - 1])
            else:
                psar.iloc[i] = psar.iloc[i - 1] - af * (psar.iloc[i - 1] - ep)

            reverse = False
            if bull.iloc[i - 1] and self.df["low"].iloc[i] < psar.iloc[i]:
                bull.iloc[i] = False; reverse = True
            elif not bull.iloc[i - 1] and self.df["high"].iloc[i] > psar.iloc[i]:
                bull.iloc[i] = True; reverse = True
            else: bull.iloc[i] = bull.iloc[i - 1]

            if reverse:
                af = acceleration
                ep = self.df["high"].iloc[i] if bull.iloc[i] else self.df["low"].iloc[i]
            elif bull.iloc[i]:
                if self.df["high"].iloc[i] > ep: ep = self.df["high"].iloc[i]; af = min(af + acceleration, max_acceleration)
            elif self.df["low"].iloc[i] < ep: ep = self.df["low"].iloc[i]; af = min(af + acceleration, max_acceleration)

            if bull.iloc[i]: psar.iloc[i] = min(psar.iloc[i], self.df["low"].iloc[i], self.df["low"].iloc[i-1])
            else: psar.iloc[i] = max(psar.iloc[i], self.df["high"].iloc[i], self.df["high"].iloc[i-1])

            if bull.iloc[i] and psar.iloc[i] > self.df["low"].iloc[i]: psar.iloc[i] = self.df["low"].iloc[i]
            elif not bull.iloc[i] and psar.iloc[i] < self.df["high"].iloc[i]: psar.iloc[i] = self.df["high"].iloc[i]

        direction = pd.Series(0, index=self.df.index, dtype=int)
        direction[psar < self.df["close"]] = 1
        direction[psar > self.df["close"]] = -1

        return psar, direction

    def calculate_fibonacci_levels(self) -> None:
        """Calculate Fibonacci retracement levels based on a recent high-low swing."""
        window = self.config["indicator_settings"]["fibonacci_window"]
        if len(self.df) < window:
            self.logger.warning(f"{NEON_YELLOW}Not enough data for Fibonacci levels (need {window} bars).{RESET}")
            return

        recent_high = self.df["high"].iloc[-window:].max()
        recent_low = self.df["low"].iloc[-window:].min()
        diff = recent_high - recent_low

        self.fib_levels = {
            "0.0%": Decimal(str(recent_high)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "23.6%": Decimal(str(recent_high - 0.236 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "38.2%": Decimal(str(recent_high - 0.382 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "50.0%": Decimal(str(recent_high - 0.500 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "61.8%": Decimal(str(recent_high - 0.618 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "78.6%": Decimal(str(recent_high - 0.786 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "100.0%": Decimal(str(recent_low)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
        }
        self.logger.debug(f"Calculated Fibonacci levels: {self.fib_levels}")

    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        """Safely retrieve an indicator value."""
        return self.indicator_values.get(key, default)

    def _check_orderbook(self, current_price: Decimal, orderbook_data: dict) -> float:
        """Analyze orderbook imbalance."""
        bids = orderbook_data.get("b", [])
        asks = orderbook_data.get("a", [])

        bid_volume = sum(Decimal(b) for b in bids)
        ask_volume = sum(Decimal(a) for a in asks)

        if bid_volume + ask_volume == 0: return 0.0

        imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
        self.logger.debug(f"Orderbook Imbalance: {imbalance:.4f} (Bids: {bid_volume}, Asks: {ask_volume})")
        return float(imbalance)

    def _get_mtf_trend(self, higher_tf_df: pd.DataFrame, indicator_type: str) -> str:
        """Determine trend from higher timeframe using specified indicator."""
        if higher_tf_df.empty: return "UNKNOWN"

        last_close = higher_tf_df["close"].iloc[-1]
        period = self.config["mtf_analysis"]["trend_period"]

        if indicator_type == "sma":
            if len(higher_tf_df) < period: return "UNKNOWN"
            sma = higher_tf_df["close"].rolling(window=period, min_periods=period).mean().iloc[-1]
            if last_close > sma: return "UP"
            if last_close < sma: return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ema":
            if len(higher_tf_df) < period: return "UNKNOWN"
            ema = higher_tf_df["close"].ewm(span=period, adjust=False, min_periods=period).mean().iloc[-1]
            if last_close > ema: return "UP"
            if last_close < ema: return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ehlers_supertrend":
            temp_analyzer = TradingAnalyzer(higher_tf_df, self.config, self.logger, self.symbol)
            st_result = temp_analyzer.calculate_ehlers_supertrend(
                self.indicator_settings["ehlers_slow_period"],
                self.indicator_settings["ehlers_slow_multiplier"],
            )
            if st_result is not None and not st_result.empty:
                st_dir = st_result["direction"].iloc[-1]
                if st_dir == 1: return "UP"
                if st_dir == -1: return "DOWN"
            return "UNKNOWN"
        return "UNKNOWN"

    def generate_trading_signal(
        self, current_price: Decimal, orderbook_data: dict | None, mtf_trends: dict[str, str]
    ) -> tuple[str, float]:
        """Generate a signal using confluence of indicators, including Ehlers SuperTrend."""
        signal_score = 0.0
        active_indicators = self.config["indicators"]
        weights = self.weights

        if self.df.empty:
            self.logger.warning(f"{NEON_YELLOW}DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}")
            return "HOLD", 0.0

        current_close = Decimal(str(self.df["close"].iloc[-1]))
        prev_close = Decimal(str(self.df["close"].iloc[-2])) if len(self.df) > 1 else current_close
        isd = self.indicator_settings

        # --- Indicator Scoring ---
        if active_indicators.get("ema_alignment", False):
            ema_short = self._get_indicator_value("EMA_Short")
            ema_long = self._get_indicator_value("EMA_Long")
            if not pd.isna(ema_short) and not pd.isna(ema_long):
                if ema_short > ema_long: signal_score += weights.get("ema_alignment", 0)
                elif ema_short < ema_long: signal_score -= weights.get("ema_alignment", 0)

        if active_indicators.get("sma_trend_filter", False):
            sma_long = self._get_indicator_value("SMA_Long")
            if not pd.isna(sma_long):
                if current_close > sma_long: signal_score += weights.get("sma_trend_filter", 0)
                elif current_close < sma_long: signal_score -= weights.get("sma_trend_filter", 0)

        if active_indicators.get("momentum", False):
            rsi = self._get_indicator_value("RSI")
            stoch_k = self._get_indicator_value("StochRSI_K")
            stoch_d = self._get_indicator_value("StochRSI_D")
            cci = self._get_indicator_value("CCI")
            wr = self._get_indicator_value("WR")
            mfi = self._get_indicator_value("MFI")

            if not pd.isna(rsi):
                if rsi < isd["rsi_oversold"]: signal_score += weights.get("rsi", 0) * 0.5
                elif rsi > isd["rsi_overbought"]: signal_score -= weights.get("rsi", 0) * 0.5

            if not pd.isna(stoch_k) and not pd.isna(stoch_d):
                if stoch_k > stoch_d and stoch_k < isd["stoch_rsi_oversold"]: signal_score += weights.get("stoch_rsi", 0) * 0.5
                elif stoch_k < stoch_d and stoch_k > isd["stoch_rsi_overbought"]: signal_score -= weights.get("stoch_rsi", 0) * 0.5

            if not pd.isna(cci):
                if cci < isd["cci_oversold"]: signal_score += weights.get("cci", 0) * 0.5
                elif cci > isd["cci_overbought"]: signal_score -= weights.get("cci", 0) * 0.5

            if not pd.isna(wr):
                if wr < isd["williams_r_oversold"]: signal_score += weights.get("wr", 0) * 0.5
                elif wr > isd["williams_r_overbought"]: signal_score -= weights.get("wr", 0) * 0.5

            if not pd.isna(mfi):
                if mfi < isd["mfi_oversold"]: signal_score += weights.get("mfi", 0) * 0.5
                elif mfi > isd["mfi_overbought"]: signal_score -= weights.get("mfi", 0) * 0.5

        if active_indicators.get("bollinger_bands", False):
            bb_upper = self._get_indicator_value("BB_Upper")
            bb_lower = self._get_indicator_value("BB_Lower")
            if not pd.isna(bb_upper) and not pd.isna(bb_lower):
                if current_close < bb_lower: signal_score += weights.get("bollinger_bands", 0) * 0.5
                elif current_close > bb_upper: signal_score -= weights.get("bollinger_bands", 0) * 0.5

        if active_indicators.get("vwap", False):
            vwap = self._get_indicator_value("VWAP")
            if not pd.isna(vwap):
                if current_close > vwap: signal_score += weights.get("vwap", 0) * 0.2
                elif current_close < vwap: signal_score -= weights.get("vwap", 0) * 0.2

                if len(self.df) > 1:
                    prev_close = Decimal(str(self.df["close"].iloc[-2]))
                    prev_vwap = Decimal(str(self.df["VWAP"].iloc[-2]))
                    if current_close > vwap and prev_close <= prev_vwap: signal_score += weights.get("vwap", 0) * 0.3
                    elif current_close < vwap and prev_close >= prev_vwap: signal_score -= weights.get("vwap", 0) * 0.3

        if active_indicators.get("psar", False):
            psar_val = self._get_indicator_value("PSAR_Val")
            psar_dir = self._get_indicator_value("PSAR_Dir")
            if not pd.isna(psar_val) and not pd.isna(psar_dir):
                if psar_dir == 1: signal_score += weights.get("psar", 0) * 0.5
                elif psar_dir == -1: signal_score -= weights.get("psar", 0) * 0.5

                if len(self.df) > 1:
                    prev_close = Decimal(str(self.df["close"].iloc[-2]))
                    prev_psar_val = Decimal(str(self.df["PSAR_Val"].iloc[-2]))
                    if current_close > psar_val and prev_close <= prev_psar_val: signal_score += weights.get("psar", 0) * 0.4
                    elif current_close < psar_val and prev_close >= prev_psar_val: signal_score -= weights.get("psar", 0) * 0.4

        if active_indicators.get("orderbook_imbalance", False) and orderbook_data:
            imbalance = self._check_orderbook(current_price, orderbook_data)
            signal_score += imbalance * weights.get("orderbook_imbalance", 0)

        if active_indicators.get("fibonacci_levels", False) and self.fib_levels:
            for level_name, level_price in self.fib_levels.items():
                if level_name not in ["0.0%", "100.0%"] and abs(current_price - level_price) / current_price < Decimal("0.001"):
                    if len(self.df) > 1:
                        prev_close = Decimal(str(self.df["close"].iloc[-2]))
                        if current_close > prev_close and current_close > level_price: signal_score += weights.get("fibonacci_levels", 0) * 0.1
                        elif current_close < prev_close and current_close < level_price: signal_score -= weights.get("fibonacci_levels", 0) * 0.1

        if active_indicators.get("ehlers_supertrend", False):
            st_fast_dir = self._get_indicator_value("ST_Fast_Dir")
            st_slow_dir = self._get_indicator_value("ST_Slow_Dir")
            prev_st_fast_dir = self.df["st_fast_dir"].iloc[-2] if "st_fast_dir" in self.df.columns and len(self.df) > 1 else np.nan
            weight = weights.get("ehlers_supertrend_alignment", 0.0)

            if not pd.isna(st_fast_dir) and not pd.isna(st_slow_dir) and not pd.isna(prev_st_fast_dir):
                if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1: signal_score += weight
                elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1: signal_score -= weight
                elif st_slow_dir == 1 and st_fast_dir == 1: signal_score += weight * 0.3
                elif st_slow_dir == -1 and st_fast_dir == -1: signal_score -= weight * 0.3

        if active_indicators.get("macd", False):
            macd_line = self._get_indicator_value("MACD_Line")
            signal_line = self._get_indicator_value("MACD_Signal")
            histogram = self._get_indicator_value("MACD_Hist")
            weight = weights.get("macd_alignment", 0.0)

            if not pd.isna(macd_line) and not pd.isna(signal_line) and not pd.isna(histogram):
                if len(self.df) > 1:
                    prev_macd_line = Decimal(str(self.df["MACD_Line"].iloc[-2]))
                    prev_signal_line = Decimal(str(self.df["MACD_Signal"].iloc[-2]))
                    if macd_line > signal_line and prev_macd_line <= prev_signal_line: signal_score += weight
                    elif macd_line < signal_line and prev_macd_line >= prev_signal_line: signal_score -= weight
                if len(self.df) > 1 and histogram > 0 and self.df["MACD_Hist"].iloc[-2] < 0: signal_score += weight * 0.2
                elif len(self.df) > 1 and histogram < 0 and self.df["MACD_Hist"].iloc[-2] > 0: signal_score -= weight * 0.2

        if active_indicators.get("adx", False):
            adx_val = self._get_indicator_value("ADX")
            plus_di = self._get_indicator_value("PlusDI")
            minus_di = self._get_indicator_value("MinusDI")
            weight = weights.get("adx_strength", 0.0)

            if not pd.isna(adx_val) and not pd.isna(plus_di) and not pd.isna(minus_di):
                if adx_val > ADX_STRONG_TREND_THRESHOLD:
                    if plus_di > minus_di: signal_score += weight
                    elif minus_di > plus_di: signal_score -= weight
                elif adx_val < ADX_WEAK_TREND_THRESHOLD: pass

        if active_indicators.get("ichimoku_cloud", False):
            tenkan_sen = self._get_indicator_value("Tenkan_Sen")
            kijun_sen = self._get_indicator_value("Kijun_Sen")
            senkou_span_a = self._get_indicator_value("Senkou_Span_A")
            senkou_span_b = self._get_indicator_value("Senkou_Span_B")
            chikou_span = self._get_indicator_value("Chikou_Span")
            weight = weights.get("ichimoku_confluence", 0.0)

            if not pd.isna(tenkan_sen) and not pd.isna(kijun_sen) and not pd.isna(senkou_span_a) and not pd.isna(senkou_span_b) and not pd.isna(chikou_span):
                if tenkan_sen > kijun_sen and self.df["Tenkan_Sen"].iloc[-2] <= self.df["Kijun_Sen"].iloc[-2]: signal_score += weight * 0.5
                elif tenkan_sen < kijun_sen and self.df["Tenkan_Sen"].iloc[-2] >= self.df["Kijun_Sen"].iloc[-2]: signal_score -= weight * 0.5

                if current_close > max(senkou_span_a, senkou_span_b) and self.df["close"].iloc[-2] <= max(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]): signal_score += weight * 0.7
                elif current_close < min(senkou_span_a, senkou_span_b) and self.df["close"].iloc[-2] >= min(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]): signal_score -= weight * 0.7

                if chikou_span > current_close and self.df["Chikou_Span"].iloc[-2] <= self.df["close"].iloc[-2]: signal_score += weight * 0.3
                elif chikou_span < current_close and self.df["Chikou_Span"].iloc[-2] >= self.df["close"].iloc[-2]: signal_score -= weight * 0.3

        if active_indicators.get("obv", False):
            obv_val = self._get_indicator_value("OBV")
            obv_ema = self._get_indicator_value("OBV_EMA")
            weight = weights.get("obv_momentum", 0.0)
            if not pd.isna(obv_val) and not pd.isna(obv_ema):
                if obv_val > obv_ema and self.df["OBV"].iloc[-2] <= self.df["OBV_EMA"].iloc[-2]: signal_score += weight * 0.5
                elif obv_val < obv_ema and self.df["OBV"].iloc[-2] >= self.df["OBV_EMA"].iloc[-2]: signal_score -= weight * 0.5
                if len(self.df) > 2:
                    if obv_val > self.df["OBV"].iloc[-2] and obv_val > self.df["OBV"].iloc[-3]: signal_score += weight * 0.2
                    elif obv_val < self.df["OBV"].iloc[-2] and obv_val < self.df["OBV"].iloc[-3]: signal_score -= weight * 0.2

        if active_indicators.get("cmf", False):
            cmf_val = self._get_indicator_value("CMF")
            weight = weights.get("cmf_flow", 0.0)
            if not pd.isna(cmf_val):
                if cmf_val > 0: signal_score += weight * 0.5
                elif cmf_val < 0: signal_score -= weight * 0.5
                if len(self.df) > 2:
                    if cmf_val > self.df["CMF"].iloc[-2] and cmf_val > self.df["CMF"].iloc[-3]: signal_score += weight * 0.3
                    elif cmf_val < self.df["CMF"].iloc[-2] and cmf_val < self.df["CMF"].iloc[-3]: signal_score -= weight * 0.3

        if self.config["mtf_analysis"]["enabled"] and mtf_trends:
            mtf_buy_score = sum(1 for trend in mtf_trends.values() if trend == "UP")
            mtf_sell_score = sum(-1 for trend in mtf_trends.values() if trend == "DOWN")
            if mtf_trends:
                normalized_mtf_score = (mtf_buy_score + mtf_sell_score) / len(mtf_trends)
                signal_score += weights.get("mtf_trend_confluence", 0.0) * normalized_mtf_score
                self.logger.debug(f"MTF Confluence: Score {normalized_mtf_score:.2f}")

        threshold = self.config["signal_score_threshold"]
        final_signal = "HOLD"
        if signal_score >= threshold: final_signal = "BUY"
        elif signal_score <= -threshold: final_signal = "SELL"

        self.logger.info(f"{NEON_YELLOW}Raw Technical Signal Score: {signal_score:.2f}, Final Technical Signal: {final_signal}{RESET}")
        return final_signal, signal_score


    # --- Remaining Indicator Implementations ---
    def calculate_true_range(self) -> pd.Series:
        """Calculate True Range (TR)."""
        if len(self.df) < MIN_DATA_POINTS_TR: return pd.Series(np.nan, index=self.df.index)
        high_low = self.df["high"] - self.df["low"]
        high_prev_close = (self.df["high"] - self.df["close"].shift()).abs()
        low_prev_close = (self.df["low"] - self.df["close"].shift()).abs()
        return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)

    def calculate_super_smoother(self, series: pd.Series, period: int) -> pd.Series:
        """Apply Ehlers SuperSmoother filter to reduce lag and noise."""
        if period <= 0 or len(series) < MIN_DATA_POINTS_SMOOTHER: return pd.Series(np.nan, index=series.index)
        series = pd.to_numeric(series, errors="coerce").dropna()
        if len(series) < MIN_DATA_POINTS_SMOOTHER: return pd.Series(np.nan, index=series.index)

        a1 = np.exp(-np.sqrt(2) * np.pi / period)
        b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / period)
        c1 = 1 - b1 + a1**2
        c2 = b1 - 2 * a1**2
        c3 = a1**2

        filt = pd.Series(0.0, index=series.index)
        if len(series) >= 1: filt.iloc = series.iloc
        if len(series) >= 2: filt.iloc = (series.iloc + series.iloc) / 2

        for i in range(2, len(series)):
            filt.iloc[i] = ((c1 / 2) * (series.iloc[i] + series.iloc[i - 1])) + (c2 * filt.iloc[i - 1]) - (c3 * filt.iloc[i - 2])
        return filt.reindex(self.df.index)

    def calculate_ehlers_supertrend(self, period: int, multiplier: float) -> Optional[pd.DataFrame]:
        """Calculate SuperTrend using Ehlers SuperSmoother for price and volatility."""
        if len(self.df) < period * 3: return None
        df_copy = self.df.copy()
        hl2 = (df_copy["high"] + df_copy["low"]) / 2
        smoothed_price = self.calculate_super_smoother(hl2, period)
        tr = self.calculate_true_range()
        smoothed_atr = self.calculate_super_smoother(tr, period)

        if smoothed_price is None or smoothed_atr is None: return None

        df_copy["smoothed_price"] = smoothed_price
        df_copy["smoothed_atr"] = smoothed_atr
        df_copy.dropna(subset=["smoothed_price", "smoothed_atr"], inplace=True)
        if df_copy.empty: return None

        upper_band = df_copy["smoothed_price"] + multiplier * df_copy["smoothed_atr"]
        lower_band = df_copy["smoothed_price"] - multiplier * df_copy["smoothed_atr"]

        direction = pd.Series(0, index=df_copy.index, dtype=int)
        supertrend = pd.Series(np.nan, index=df_copy.index)

        first_valid_idx = df_copy.index
        supertrend.loc[first_valid_idx] = lower_band.loc[first_valid_idx]

        for i in range(1, len(df_copy)):
            current_idx = df_copy.index[i]
            prev_idx = df_copy.index[i - 1]

            prev_direction = direction.loc[prev_idx]
            prev_supertrend = supertrend.loc[prev_idx]
            curr_close = df_copy["close"].loc[current_idx]

            if prev_direction == 1:
                supertrend.loc[current_idx] = max(lower_band.loc[current_idx], prev_supertrend)
                if curr_close < supertrend.loc[current_idx[current_idx] = max(lower_band.loc[current_idx], prev_supertrend)
                if curr_close < supertrend.loc[current_idxThis is a comprehensive request. The code provided in the context is already quite advanced, integrating Bybit data fetching, extensive technical analysis (including Ehlers SuperTrend), and Gemini AI analysis.

My analysis and enhancement plan will focus on:
1.  **Robustness & Precision:** Ensuring all critical financial calculations use the `Decimal` type consistently.
2.  **Gemini Vision Integration:** Fully implementing the chart generation and analysis capabilities hinted at in the JavaScript context snippet, assuming `matplotlib` is available in the environment.
3.  **Logical Structure:** While I must return a single file, I will structure the code into logical blocks/classes that represent the modules you requested for better maintainability.

Here is the complete, upgraded, and enhanced single-file Python script, logically separated into modules.

### Complete Improved Python Code (`whalebot_enhanced.py`)

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Whalebot Enhanced: An automated cryptocurrency trading bot for Bybit.

This bot leverages extensive technical indicators, multi-timeframe analysis,
risk management, and Gemini AI (text and vision) for advanced signal generation.
"""

# --- 1. IMPORTS & GLOBAL SETUP (config_setup Module Simulation) ---
import hashlib
import json
import logging
import os
import sys
import time
import urllib.parse
from datetime import datetime, date
from decimal import ROUND_DOWN, Decimal, getcontext
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
import requests
from colorama import Fore, Style, init
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from zoneinfo import ZoneInfo

# External Libraries (Crucial for AI/Plotting)
try:
    from google import genai
    from google.generativeai.types import GenerateContentResponse, Part
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

# Initialize colorama and set decimal precision
getcontext().prec = 28  # Set high precision for Decimal operations
init(autoreset=True)
load_dotenv()

# Neon Color Scheme
NEON_GREEN = Fore.LIGHTGREEN_EX
NEON_BLUE = Fore.CYAN
NEON_PURPLE = Fore.MAGENTA
NEON_YELLOW = Fore.YELLOW
NEON_RED = Fore.LIGHTRED_EX
NEON_CYAN = Fore.CYAN
RESET = Style.RESET_ALL

# Indicator Color Map (For Display)
INDICATOR_COLORS: Dict[str, str] = {
    "SMA_10": Fore.LIGHTBLUE_EX, "SMA_Long": Fore.BLUE, "EMA_Short": Fore.LIGHTMAGENTA_EX,
    "EMA_Long": Fore.MAGENTA, "ATR": Fore.YELLOW, "RSI": Fore.GREEN, "StochRSI_K": Fore.CYAN,
    "StochRSI_D": Fore.LIGHTCYAN_EX, "BB_Upper": Fore.RED, "BB_Middle": Fore.WHITE, "BB_Lower": Fore.RED,
    "CCI": Fore.LIGHTGREEN_EX, "WR": Fore.LIGHTRED_EX, "MFI": Fore.GREEN, "OBV": Fore.BLUE,
    "OBV_EMA": Fore.LIGHTBLUE_EX, "CMF": Fore.MAGENTA, "Tenkan_Sen": Fore.CYAN, "Kijun_Sen": Fore.LIGHTCYAN_EX,
    "Senkou_Span_A": Fore.GREEN, "Senkou_Span_B": Fore.RED, "Chikou_Span": Fore.YELLOW,
    "PSAR_Val": Fore.MAGENTA, "PSAR_Dir": Fore.LIGHTMAGENTA_EX, "VWAP": Fore.WHITE,
    "ST_Fast_Dir": Fore.BLUE, "ST_Fast_Val": Fore.LIGHTBLUE_EX, "ST_Slow_Dir": Fore.MAGENTA, "ST_Slow_Val": Fore.LIGHTMAGENTA_EX,
    "MACD_Line": Fore.GREEN, "MACD_Signal": Fore.LIGHTGREEN_EX, "MACD_Hist": Fore.YELLOW,
    "ADX": Fore.CYAN, "PlusDI": Fore.LIGHTCYAN_EX, "MinusDI": Fore.RED,
}

# --- Constants ---
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
BASE_URL = os.getenv("BYBIT_BASE_URL", "https://api.bybit.com")
CONFIG_FILE = "config.json"
LOG_DIRECTORY = "bot_logs"
Path(LOG_DIRECTORY).mkdir(parents=True, exist_ok=True)

TIMEZONE = ZoneInfo("America/Chicago")
MAX_API_RETRIES = 5
RETRY_DELAY_SECONDS = 7
REQUEST_TIMEOUT = 20
LOOP_DELAY_SECONDS = 15

# Magic Numbers as Constants
MIN_DATA_POINTS_TR = 2
MIN_DATA_POINTS_SMOOTHER = 2
MIN_DATA_POINTS_PSAR = 2
ADX_STRONG_TREND_THRESHOLD = 25
ADX_WEAK_TREND_THRESHOLD = 20


# --- Configuration Management (config_setup Module Simulation) ---
def _ensure_config_keys(config: Dict[str, Any], default_config: Dict[str, Any]) -> None:
    """Recursively ensure all keys from default_config are in config."""
    for key, default_value in default_config.items():
        if key not in config:
            config[key] = default_value
        elif isinstance(default_value, dict) and isinstance(config.get(key), dict):
            _ensure_config_keys(config[key], default_value)


def load_config(filepath: str, logger: logging.Logger) -> Dict[str, Any]:
    """Load configuration from JSON file, creating a default one if missing."""
    default_config = {
        "symbol": "BTCUSDT", "interval": "15m", "loop_delay": LOOP_DELAY_SECONDS,
        "orderbook_limit": 50, "signal_score_threshold": 2.0, "volume_confirmation_multiplier": 1.5,
        "trade_management": {
            "enabled": True, "account_balance": 1000.0, "risk_per_trade_percent": 1.0,
            "stop_loss_atr_multiple": 1.5, "take_profit_atr_multiple": 2.0, "max_open_positions": 1,
            "min_stop_loss_distance_ratio": 0.001
        },
        "mtf_analysis": {
            "enabled": True, "higher_timeframes": ["1h", "4h"],
            "trend_indicators": ["ema", "ehlers_supertrend"], "trend_period": 50,
            "mtf_request_delay_seconds": 0.5,
        },
        "ml_enhancement": {
            "enabled": False, "model_path": "ml_model.pkl", "retrain_on_startup": False,
            "training_data_limit": 5000, "prediction_lookahead": 12, "profit_target_percent": 0.5,
            "feature_lags": [1, 2, 3, 5], "cross_validation_folds": 5,
        },
        "gemini_ai": {
            "enabled": True, "api_key_env": "GEMINI_API_KEY", "model": "gemini-1.5-flash-latest",
            "min_confidence_for_override": 60, "rate_limit_delay_seconds": 1.0, "cache_ttl_seconds": 300,
            "daily_api_limit": 1000,
            "signal_weights": {"technical": 0.6, "ai": 0.4},
            "low_ai_confidence_threshold": 20,
            "chart_image_analysis": {
                "enabled": False, "frequency_loops": 0, "data_points_for_chart": 100,
            }
        },
        "indicator_settings": {
            "atr_period": 14, "ema_short_period": 9, "ema_long_period": 21, "rsi_period": 14,
            "stoch_rsi_period": 14, "stoch_k_period": 3, "stoch_d_period": 3, "bollinger_bands_period": 20,
            "bollinger_bands_std_dev": 2.0, "cci_period": 20, "williams_r_period": 14, "mfi_period": 14,
            "psar_acceleration": 0.02, "psar_max_acceleration": 0.2, "sma_short_period": 10, "sma_long_period": 50,
            "fibonacci_window": 60, "ehlers_fast_period": 10, "ehlers_fast_multiplier": 2.0,
            "ehlers_slow_period": 20, "ehlers_slow_multiplier": 3.0, "macd_fast_period": 12, "macd_slow_period": 26,
            "macd_signal_period": 9, "adx_period": 14, "ichimoku_tenkan_period": 9, "ichimoku_kijun_period": 26,
            "ichimoku_senkou_span_b_period": 52, "ichimoku_chikou_span_offset": 26, "obv_ema_period": 20,
            "cmf_period": 20, "rsi_oversold": 30, "rsi_overbought": 70, "stoch_rsi_oversold": 20,
            "stoch_rsi_overbought": 80, "cci_oversold": -100, "cci_overbought": 100, "williams_r_oversold": -80,
            "williams_r_overbought": -20, "mfi_oversold": 20, "mfi_overbought": 80,
        },
        "indicators": {
            "ema_alignment": True, "sma_trend_filter": True, "momentum": True, "volume_confirmation": True,
            "stoch_rsi": True, "rsi": True, "bollinger_bands": True, "vwap": True, "cci": True, "wr": True,
            "psar": True, "sma_10": True, "mfi": True, "orderbook_imbalance": True, "fibonacci_levels": True,
            "ehlers_supertrend": True, "macd": True, "adx": True, "ichimoku_cloud": True, "obv": True, "cmf": True,
        },
        "weight_sets": {
            "default_scalping": {
                "ema_alignment": 0.22, "sma_trend_filter": 0.28, "momentum": 0.18, "stoch_rsi": 0.30, "rsi": 0.12,
                "bollinger_bands": 0.22, "vwap": 0.22, "cci": 0.08, "wr": 0.08, "psar": 0.22, "sma_10": 0.07,
                "mfi": 0.12, "orderbook_imbalance": 0.07, "ehlers_supertrend_alignment": 0.55, "macd_alignment": 0.28,
                "adx_strength": 0.18, "ichimoku_confluence": 0.38, "obv_momentum": 0.18, "cmf_flow": 0.12,
                "mtf_trend_confluence": 0.32, "roc_signal": 0.12, "candlestick_confirmation": 0.15,
                "fibonacci_pivot_points_confluence": 0.20, "volume_delta_signal": 0.10, "kaufman_ama_cross": 0.20,
                "relative_volume_confirmation": 0.10, "market_structure_confluence": 0.25, "dema_crossover": 0.18,
                "keltner_breakout": 0.20,
            }
        },
    }
    if not Path(filepath).exists():
        try:
            with Path(filepath).open("w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)
            logger.warning(f"{NEON_YELLOW}Configuration file not found. Created default config at {filepath}{RESET}")
            return default_config
        except OSError as e:
            logger.error(f"{NEON_RED}Error creating default config file: {e}{RESET}")
            return default_config

    try:
        with Path(filepath).open(encoding="utf-8") as f:
            config = json.load(f)
        _ensure_config_keys(config, default_config)
        with Path(filepath).open("w", encoding="utf-8") as f_write:
            json.dump(config, f_write, indent=4)
        return config
    except (OSError, FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"{NEON_RED}Error loading config: {e}. Using default and attempting to save.{RESET}")
        try:
            with Path(filepath).open("w", encoding="utf-8") as f_default:
                json.dump(default_config, f_default, indent=4)
        except OSError as e_save:
            logger.error(f"{NEON_RED}Could not save default config: {e_save}{RESET}")
        return default_config


# --- Logging Setup (config_setup Module Simulation) ---
class SensitiveFormatter(logging.Formatter):
    """Formatter that redacts API keys from log records."""
    SENSITIVE_WORDS: ClassVar[list[str]] = ["API_KEY", "API_SECRET", "GEMINI_API_KEY"]

    def format(self, record: logging.LogRecord) -> str:
        original_message = super().format(record)
        redacted_message = original_message
        for word in self.SENSITIVE_WORDS:
            env_val = os.getenv(word, "")
            if env_val:
                redacted_message = redacted_message.replace(env_val, "*" * len(env_val))
            redacted_message = redacted_message.replace(word, "*" * len(word))
        return redacted_message


def setup_logger(log_name: str, level=logging.INFO) -> logging.Logger:
    """Configure and return a logger with file and console handlers."""
    logger = logging.getLogger(log_name)
    logger.setLevel(level)
    logger.propagate = False

    if not logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(
            SensitiveFormatter(f"{NEON_BLUE}%(asctime)s - %(levelname)s - %(message)s{RESET}")
        )
        logger.addHandler(console_handler)

        file_handler = RotatingFileHandler(
            Path(LOG_DIRECTORY) / f"{log_name}.log", maxBytes=10 * 1024 * 1024, backupCount=5
        )
        file_handler.setFormatter(SensitiveFormatter())
        logger.addHandler(file_handler)

    return logger


# --- 2. API Client Module Simulation (api_client.py) ---
def create_session() -> requests.Session:
    """Create a requests session with retry logic."""
    session = requests.Session()
    retries = Retry(
        total=MAX_API_RETRIES, backoff_factor=RETRY_DELAY_SECONDS,
        status_forcelist=[429, 500, 502, 503, 504], allowed_methods=frozenset(["GET", "POST"]),
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session


def generate_signature(payload: str, api_secret: str) -> str:
    """Generate a Bybit API signature."""
    return hmac.new(api_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def bybit_request(
    method: str, endpoint: str, params: dict | None = None, signed: bool = False, logger: Optional[logging.Logger] = None
) -> dict | None:
    """Send a request to the Bybit API."""
    if logger is None: logger = setup_logger("bybit_api")
    session = create_session()
    url = f"{BASE_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}

    if signed:
        if not API_KEY or not API_SECRET:
            logger.error(f"{NEON_RED}API_KEY or API_SECRET not set for signed request.{RESET}")
            return None

        timestamp = str(int(time.time() * 1000))
        recv_window = "20000"

        if method == "GET":
            query_string = urllib.parse.urlencode(params) if params else ""
            param_str = timestamp + API_KEY + recv_window + query_string
            signature = generate_signature(param_str, API_SECRET)
            headers.update({"X-BAPI-API-KEY": API_KEY, "X-BAPI-TIMESTAMP": timestamp, "X-BAPI-SIGN": signature, "X-BAPI-RECV-WINDOW": recv_window})
            logger.debug(f"GET Request: {url}?{query_string}")
            response = session.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        else:  # POST
            json_params = json.dumps(params) if params else ""
            param_str = timestamp + API_KEY + recv_window + json_params
            signature = generate_signature(param_str, API_SECRET)
            headers.update({"X-BAPI-API-KEY": API_KEY, "X-BAPI-TIMESTAMP": timestamp, "X-BAPI-SIGN": signature, "X-BAPI-RECV-WINDOW": recv_window})
            logger.debug(f"POST Request: {url} with payload {json_params}")
            response = session.post(url, json=params, headers=headers, timeout=REQUEST_TIMEOUT)
    else:
        logger.debug(f"Public Request: {url} with params {params}")
        response = session.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)

    try:
        response.raise_for_status()
        data = response.json()
        if data.get("retCode") != 0:
            logger.error(f"{NEON_RED}Bybit API Error: {data.get('retMsg')} (Code: {data.get('retCode')}){RESET}")
            return None
        return data
    except requests.exceptions.RequestException as e:
        logger.error(f"{NEON_RED}API Request Error: {e}{RESET}")
    except json.JSONDecodeError:
        logger.error(f"{NEON_RED}Failed to decode JSON response: {response.text}{RESET}")
    return None


def fetch_current_price(symbol: str, logger: logging.Logger) -> Optional[Decimal]:
    """Fetch the current market price for a symbol."""
    endpoint = "/v5/market/tickers"
    params = {"category": "linear", "symbol": symbol}
    response = bybit_request("GET", endpoint, params, logger=logger)
    if response and response["result"] and response["result"]["list"]:
        price = Decimal(response["result"]["list"][0]["lastPrice"])
        logger.debug(f"Fetched current price for {symbol}: {price}")
        return price
    logger.warning(f"{NEON_YELLOW}Could not fetch current price for {symbol}.{RESET}")
    return None


def fetch_klines(
    symbol: str, interval: str, limit: int, logger: logging.Logger
) -> Optional[pd.DataFrame]:
    """Fetch kline data for a symbol and interval."""
    endpoint = "/v5/market/kline"
    params = {"category": "linear", "symbol": symbol, "interval": interval, "limit": limit}
    response = bybit_request("GET", endpoint, params, logger=logger)
    if response and response["result"] and response["result"]["list"]:
        df = pd.DataFrame(
            response["result"]["list"],
            columns=["start_time", "open", "high", "low", "close", "volume", "turnover",],
        )
        df["start_time"] = pd.to_datetime(
            df["start_time"].astype(int), unit="ms", utc=True
        ).dt.tz_convert(TIMEZONE)
        for col in ["open", "high", "low", "close", "volume", "turnover"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df.set_index("start_time", inplace=True)
        df.sort_index(inplace=True)

        if df.empty:
            logger.warning(f"{NEON_YELLOW}Fetched klines for {symbol} {interval} but DataFrame is empty after processing.{RESET}")
            return None

        logger.debug(f"Fetched {len(df)} {interval} klines for {symbol}.")
        return df
    logger.warning(f"{NEON_YELLOW}Could not fetch klines for {symbol} {interval}.{RESET}")
    return None


def fetch_orderbook(symbol: str, limit: int, logger: logging.Logger) -> Optional[dict]:
    """Fetch orderbook data for a symbol."""
    endpoint = "/v5/market/orderbook"
    params = {"category": "linear", "symbol": symbol, "limit": limit}
    response = bybit_request("GET", endpoint, params, logger=logger)
    if response and response["result"]:
        logger.debug(f"Fetched orderbook for {symbol} with limit {limit}.")
        return response["result"]
    logger.warning(f"{NEON_YELLOW}Could not fetch orderbook for {symbol}.{RESET}")
    return None


# --- 3. Trade Management Module Simulation (trade_management.py) ---
class PositionManager:
    """Manages open positions, stop-loss, and take-profit levels."""

    def __init__(self, config: Dict[str, Any], logger: logging.Logger, symbol: str):
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.open_positions: List[Dict[str, Any]] = []
        self.trade_management_enabled = config["trade_management"]["enabled"]
        self.max_open_positions = config["trade_management"]["max_open_positions"]
        self.min_stop_loss_distance_ratio = Decimal(str(config["trade_management"]["min_stop_loss_distance_ratio"]))

    def _get_current_balance(self) -> Decimal:
        """Fetch current account balance (simplified)."""
        return Decimal(str(self.config["trade_management"]["account_balance"]))

    def _calculate_order_size(
        self,
        current_price: Decimal,
        atr_value: Decimal,
        signal: str,
        ai_position_sizing_info: Optional[Dict[str, Decimal]] = None,
    ) -> Decimal:
        """Calculate order size based on risk per trade and ATR, or AI suggestions."""
        if not self.trade_management_enabled: return Decimal("0")

        account_balance = self._get_current_balance()
        risk_per_trade_percent = (Decimal(str(self.config["trade_management"]["risk_per_trade_percent"])) / 100)
        stop_loss_atr_multiple = Decimal(str(self.config["trade_management"]["stop_loss_atr_multiple"]))

        risk_amount = account_balance * risk_per_trade_percent
        stop_loss_distance = Decimal("0")

        if ai_position_sizing_info:
            ai_stop_distance = ai_position_sizing_info.get('stop_distance')
            ai_risk_amount = ai_position_sizing_info.get('risk_amount')
            if ai_stop_distance and ai_risk_amount and ai_stop_distance > Decimal("0"):
                risk_amount = ai_risk_amount
                stop_loss_distance = ai_stop_distance
                self.logger.debug("Using AI-suggested stop distance and risk amount.")

        if stop_loss_distance <= 0:
            stop_loss_distance = atr_value * stop_loss_atr_multiple
            self.logger.debug(f"Using ATR-based stop distance: {stop_loss_distance:.8f}")

        min_abs_stop_distance = current_price * self.min_stop_loss_distance_ratio
        if stop_loss_distance < min_abs_stop_distance:
            stop_loss_distance = min_abs_stop_distance
            self.logger.warning(f"{NEON_YELLOW}Calculated stop loss distance ({stop_loss_distance:.8f}) is too small. Adjusted to minimum ({min_abs_stop_distance:.8f}).{RESET}")

        if stop_loss_distance <= 0:
            self.logger.warning(f"{NEON_YELLOW}Final stop loss distance is zero or negative. Cannot determine order size.{RESET}")
            return Decimal("0")

        order_value = risk_amount / stop_loss_distance
        order_qty = order_value / current_price

        order_qty = order_qty.quantize(Decimal("0.0001"), rounding=ROUND_DOWN)

        self.logger.info(f"Calculated order size: {order_qty} {self.symbol} (Risk: {risk_amount:.2f} USD)")
        return order_qty

    def open_position(
        self,
        signal: str,
        current_price: Decimal,
        atr_value: Decimal,
        ai_suggested_levels: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Open a new position if conditions allow. Returns the new position details or None."""
        if not self.trade_management_enabled:
            self.logger.info(f"{NEON_YELLOW}Trade management is disabled. Skipping opening position.{RESET}")
            return None

        if len(self.open_positions) >= self.max_open_positions:
            self.logger.info(f"{NEON_YELLOW}Max open positions ({self.max_open_positions}) reached. Cannot open new position.{RESET}")
            return None

        if signal not in ["BUY", "SELL"]:
            self.logger.debug(f"Invalid signal '{signal}' for opening position.")
            return None

        ai_position_sizing_info = None
        if ai_suggested_levels and 'risk_amount' in ai_suggested_levels and 'stop_distance' in ai_suggested_levels:
             ai_position_sizing_info = {
                'risk_amount': ai_suggested_levels['risk_amount'],
                'stop_distance': ai_suggested_levels['stop_distance']
             }

        order_qty = self._calculate_order_size(current_price, atr_value, signal, ai_position_sizing_info)

        if order_qty <= 0:
            self.logger.warning(f"{NEON_YELLOW}Order quantity is zero or negative. Cannot open position.{RESET}")
            return None

        stop_loss_atr_multiple = Decimal(str(self.config["trade_management"]["stop_loss_atr_multiple"]))
        take_profit_atr_multiple = Decimal(str(self.config["trade_management"]["take_profit_atr_multiple"]))

        stop_loss = Decimal("0")
        take_profit = Decimal("0")

        if ai_suggested_levels:
            suggested_sl = ai_suggested_levels.get("suggested_stop_loss")
            suggested_tp = ai_suggested_levels.get("suggested_take_profit")
            if suggested_sl is not None: stop_loss = Decimal(str(suggested_sl))
            if suggested_tp is not None: take_profit = Decimal(str(suggested_tp))

        if stop_loss <= 0 or take_profit <= 0:
            if signal == "BUY":
                stop_loss = current_price - (atr_value * stop_loss_atr_multiple)
                take_profit = current_price + (atr_value * take_profit_atr_multiple)
            else:  # SELL
                stop_loss = current_price + (atr_value * stop_loss_atr_multiple)
                take_profit = current_price - (atr_value * take_profit_atr_multiple)

        position = {
            "entry_time": datetime.now(TIMEZONE), "symbol": self.symbol, "side": signal,
            "entry_price": current_price, "qty": order_qty,
            "stop_loss": stop_loss.quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "take_profit": take_profit.quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "status": "OPEN",
        }
        self.open_positions.append(position)
        self.logger.info(f"{NEON_GREEN}Opened {signal} position: {position}{RESET}")
        return position

    def manage_positions(
        self, current_price: Decimal, performance_tracker: Any, gemini_analyzer: Optional[Any] = None
    ) -> None:
        """Check and manage all open positions (SL/TP)."""
        if not self.trade_management_enabled or not self.open_positions: return

        positions_to_close = []
        for i, position in enumerate(self.open_positions):
            if position["status"] == "OPEN":
                side, entry_price, stop_loss, take_profit, qty = position["side"], position["entry_price"], position["stop_loss"], position["take_profit"], position["qty"]
                closed_by = ""
                close_price = Decimal("0")

                if side == "BUY":
                    if current_price <= stop_loss: closed_by = "STOP_LOSS"; close_price = current_price
                    elif current_price >= take_profit: closed_by = "TAKE_PROFIT"; close_price = current_price
                elif side == "SELL":
                    if current_price >= stop_loss: closed_by = "STOP_LOSS"; close_price = current_price
                    elif current_price <= take_profit: closed_by = "TAKE_PROFIT"; close_price = current_price

                if closed_by:
                    position["status"] = "CLOSED"
                    position["exit_time"] = datetime.now(TIMEZONE)
                    position["exit_price"] = close_price
                    position["closed_by"] = closed_by
                    positions_to_close.append(i)

                    pnl = (close_price - entry_price) * qty if side == "BUY" else (entry_price - close_price) * qty
                    performance_tracker.record_trade(position, pnl)
                    self.logger.info(f"{NEON_PURPLE}Closed {side} position by {closed_by}: PnL: {pnl:.2f}{RESET}")

                    if gemini_analyzer and position.get('ai_signal'):
                        actual_outcome = "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "BREAKEVEN")
                        gemini_analyzer.track_signal_performance(position['ai_signal'], actual_outcome)

        self.open_positions = [
            pos for i, pos in enumerate(self.open_positions) if i not in positions_to_close
        ]

    def get_open_positions(self) -> List[Dict[str, Any]]:
        """Return a list of currently open positions."""
        return [pos for pos in self.open_positions if pos["status"] == "OPEN"]


class PerformanceTracker:
    """Tracks and reports trading performance."""
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.trades: List[Dict[str, Any]] = []
        self.total_pnl = Decimal("0")
        self.wins = 0
        self.losses = 0

    def record_trade(self, position: Dict[str, Any], pnl: Decimal) -> None:
        """Record a completed trade."""
        trade_record = {
            "entry_time": position["entry_time"], "exit_time": position["exit_time"],
            "symbol": position["symbol"], "side": position["side"],
            "entry_price": position["entry_price"], "exit_price": position["exit_price"],
            "qty": position["qty"], "pnl": pnl, "closed_by": position["closed_by"],
            "ai_signal_at_entry": position.get('ai_signal'),
        }
        self.trades.append(trade_record)
        self.total_pnl += pnl
        if pnl > 0: self.wins += 1
        else: self.losses += 1
        self.logger.info(f"{NEON_CYAN}Trade recorded. Current Total PnL: {self.total_pnl:.2f}, Wins: {self.wins}, Losses: {self.losses}{RESET}")

    def get_summary(self) -> Dict[str, Any]:
        """Return a summary of all recorded trades."""
        total_trades = len(self.trades)
        win_rate = (self.wins / total_trades) * 100 if total_trades > 0 else 0
        return {
            "total_trades": total_trades, "total_pnl": self.total_pnl,
            "wins": self.wins, "losses": self.losses, "win_rate": f"{win_rate:.2f}%",
        }


class AlertSystem:
    """Handles sending alerts for critical events."""
    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def send_alert(self, message: str, level: str = "INFO") -> None:
        """Send an alert (currently logs it)."""
        if level == "INFO": self.logger.info(f"{NEON_BLUE}ALERT: {message}{RESET}")
        elif level == "WARNING": self.logger.warning(f"{NEON_YELLOW}ALERT: {message}{RESET}")
        elif level == "ERROR": self.logger.error(f"{NEON_RED}ALERT: {message}{RESET}")


# --- 4. Indicators & Signals Module Simulation (indicators_signals.py) ---
class TradingAnalyzer:
    """Analyzes trading data and generates signals with MTF and Ehlers SuperTrend."""
    def __init__(self, df: pd.DataFrame, config: Dict[str, Any], logger: logging.Logger, symbol: str):
        self.df = df.copy()
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.indicator_values: Dict[str, Union[float, str, Decimal]] = {}
        self.fib_levels: Dict[str, Decimal] = {}
        self.weights = config["weight_sets"]["default_scalping"]
        self.indicator_settings = config["indicator_settings"]

        if self.df.empty:
            self.logger.warning(f"{NEON_YELLOW}TradingAnalyzer initialized with an empty DataFrame. Indicators will not be calculated.{RESET}")
            return

        self._calculate_all_indicators()
        if self.config["indicators"].get("fibonacci_levels", False):
            self.calculate_fibonacci_levels()

    def _safe_calculate(self, func: callable, name: str, min_data_points: int = 0, *args, **kwargs) -> Any | None:
        """Safely calculate indicators and log errors, with min_data_points check."""
        if len(self.df) < min_data_points:
            self.logger.debug(f"Skipping indicator '{name}': Not enough data. Need {min_data_points}, have {len(self.df)}.")
            return None
        try:
            result = func(*args, **kwargs)
            if result is None or (isinstance(result, pd.Series) and result.empty) or (isinstance(result, tuple) and all(r is None or (isinstance(r, pd.Series) and r.empty) for r in result)):
                self.logger.warning(f"{NEON_YELLOW}Indicator '{name}' returned empty or all NaNs after calculation. Not enough valid data?{RESET}")
                return None
            return result
        except Exception as e:
            self.logger.error(f"{NEON_RED}Error calculating indicator '{name}': {e}{RESET}")
            return None

    def _calculate_all_indicators(self) -> None:
        """Calculate all enabled technical indicators, including Ehlers SuperTrend."""
        self.logger.debug("Calculating technical indicators...")
        cfg = self.config
        isd = self.indicator_settings

        if cfg["indicators"].get("sma_10", False):
            self.df["SMA_10"] = self._safe_calculate(
                lambda: self.df["close"].rolling(window=isd["sma_short_period"]).mean(),
                "SMA_10", min_data_points=isd["sma_short_period"],
            )
            if self.df["SMA_10"] is not None: self.indicator_values["SMA_10"] = self.df["SMA_10"].iloc[-1]
        if cfg["indicators"].get("sma_trend_filter", False):
            self.df["SMA_Long"] = self._safe_calculate(
                lambda: self.df["close"].rolling(window=isd["sma_long_period"]).mean(),
                "SMA_Long", min_data_points=isd["sma_long_period"],
            )
            if self.df["SMA_Long"] is not None: self.indicator_values["SMA_Long"] = self.df["SMA_Long"].iloc[-1]

        if cfg["indicators"].get("ema_alignment", False):
            self.df["EMA_Short"] = self._safe_calculate(
                lambda: self.df["close"].ewm(span=isd["ema_short_period"], adjust=False).mean(),
                "EMA_Short", min_data_points=isd["ema_short_period"],
            )
            self.df["EMA_Long"] = self._safe_calculate(
                lambda: self.df["close"].ewm(span=isd["ema_long_period"], adjust=False).mean(),
                "EMA_Long", min_data_points=isd["ema_long_period"],
            )
            if self.df["EMA_Short"] is not None: self.indicator_values["EMA_Short"] = self.df["EMA_Short"].iloc[-1]
            if self.df["EMA_Long"] is not None: self.indicator_values["EMA_Long"] = self.df["EMA_Long"].iloc[-1]

        self.df["TR"] = self._safe_calculate(self.calculate_true_range, "TR", min_data_points=2)
        self.df["ATR"] = self._safe_calculate(
            lambda: self.df["TR"].ewm(span=isd["atr_period"], adjust=False).mean(),
            "ATR", min_data_points=isd["atr_period"],
        )
        if self.df["ATR"] is not None: self.indicator_values["ATR"] = self.df["ATR"].iloc[-1]

        if cfg["indicators"].get("rsi", False):
            self.df["RSI"] = self._safe_calculate(self.calculate_rsi, "RSI", min_data_points=isd["rsi_period"] + 1, period=isd["rsi_period"])
            if self.df["RSI"] is not None: self.indicator_values["RSI"] = self.df["RSI"].iloc[-1]

        if cfg["indicators"].get("stoch_rsi", False):
            stoch_rsi_k, stoch_rsi_d = self._safe_calculate(
                self.calculate_stoch_rsi, "StochRSI", min_data_points=isd["stoch_rsi_period"] + isd["stoch_d_period"] + isd["stoch_k_period"],
                period=isd["stoch_rsi_period"], k_period=isd["stoch_k_period"], d_period=isd["stoch_d_period"],
            )
            if stoch_rsi_k is not None: self.df["StochRSI_K"] = stoch_rsi_k
            if stoch_rsi_d is not None: self.df["StochRSI_D"] = stoch_rsi_d
            if stoch_rsi_k is not None: self.indicator_values["StochRSI_K"] = stoch_rsi_k.iloc[-1]
            if stoch_rsi_d is not None: self.indicator_values["StochRSI_D"] = stoch_rsi_d.iloc[-1]

        if cfg["indicators"].get("bollinger_bands", False):
            bb_upper, bb_middle, bb_lower = self._safe_calculate(
                self.calculate_bollinger_bands, "BollingerBands", min_data_points=isd["bollinger_bands_period"],
                period=isd["bollinger_bands_period"], std_dev=isd["bollinger_bands_std_dev"],
            )
            if bb_upper is not None: self.df["BB_Upper"] = bb_upper
            if bb_middle is not None: self.df["BB_Middle"] = bb_middle
            if bb_lower is not None: self.df["BB_Lower"] = bb_lower
            if bb_upper is not None: self.indicator_values["BB_Upper"] = bb_upper.iloc[-1]
            if bb_middle is not None: self.indicator_values["BB_Middle"] = bb_middle.iloc[-1]
            if bb_lower is not None: self.indicator_values["BB_Lower"] = bb_lower.iloc[-1]

        if cfg["indicators"].get("cci", False):
            self.df["CCI"] = self._safe_calculate(self.calculate_cci, "CCI", min_data_points=isd["cci_period"], period=isd["cci_period"])
            if self.df["CCI"] is not None: self.indicator_values["CCI"] = self.df["CCI"].iloc[-1]

        if cfg["indicators"].get("wr", False):
            self.df["WR"] = self._safe_calculate(self.calculate_williams_r, "WR", min_data_points=isd["williams_r_period"], period=isd["williams_r_period"])
            if self.df["WR"] is not None: self.indicator_values["WR"] = self.df["WR"].iloc[-1]

        if cfg["indicators"].get("mfi", False):
            self.df["MFI"] = self._safe_calculate(self.calculate_mfi, "MFI", min_data_points=isd["mfi_period"] + 1, period=isd["mfi_period"])
            if self.df["MFI"] is not None: self.indicator_values["MFI"] = self.df["MFI"].iloc[-1]

        if cfg["indicators"].get("obv", False):
            obv_val, obv_ema = self._safe_calculate(self.calculate_obv, "OBV", min_data_points=isd["obv_ema_period"], ema_period=isd["obv_ema_period"])
            if obv_val is not None: self.df["OBV"] = obv_val
            if obv_ema is not None: self.df["OBV_EMA"] = obv_ema
            if obv_val is not None: self.indicator_values["OBV"] = obv_val.iloc[-1]
            if obv_ema is not None: self.indicator_values["OBV_EMA"] = obv_ema.iloc[-1]

        if cfg["indicators"].get("cmf", False):
            cmf_val = self._safe_calculate(self.calculate_cmf, "CMF", min_data_points=isd["cmf_period"], period=isd["cmf_period"])
            if cmf_val is not None: self.df["CMF"] = cmf_val
            if cmf_val is not None: self.indicator_values["CMF"] = cmf_val.iloc[-1]

        if cfg["indicators"].get("ichimoku_cloud", False):
            ichimoku_result = self._safe_calculate(
                self.calculate_ichimoku_cloud, "IchimokuCloud", min_data_points=max(isd["ichimoku_tenkan_period"], isd["ichimoku_kijun_period"], isd["ichimoku_senkou_span_b_period"]) + isd["ichimoku_chikou_span_offset"],
                tenkan_period=isd["ichimoku_tenkan_period"], kijun_period=isd["ichimoku_kijun_period"],
                senkou_span_b_period=isd["ichimoku_senkou_span_b_period"], chikou_span_offset=isd["ichimoku_chikou_span_offset"],
            )
            if ichimoku_result is not None:
                tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span = ichimoku_result
                self.df["Tenkan_Sen"] = tenkan_sen
                self.df["Kijun_Sen"] = kijun_sen
                self.df["Senkou_Span_A"] = senkou_span_a
                self.df["Senkou_Span_B"] = senkou_span_b
                self.df["Chikou_Span"] = chikou_span
                self.indicator_values["Tenkan_Sen"] = tenkan_sen.iloc[-1]
                self.indicator_values["Kijun_Sen"] = kijun_sen.iloc[-1]
                self.indicator_values["Senkou_Span_A"] = senkou_span_a.iloc[-1]
                self.indicator_values["Senkou_Span_B"] = senkou_span_b.iloc[-1]
                self.indicator_values["Chikou_Span"] = chikou_span.fillna(0).iloc[-1]

        if cfg["indicators"].get("psar", False):
            psar_val, psar_dir = self._safe_calculate(self.calculate_psar, "PSAR", min_data_points=2, acceleration=isd["psar_acceleration"], max_acceleration=isd["psar_max_acceleration"])
            if psar_val is not None: self.df["PSAR_Val"] = psar_val
            if psar_dir is not None: self.df["PSAR_Dir"] = psar_dir
            if psar_val is not None: self.indicator_values["PSAR_Val"] = psar_val.iloc[-1]
            if psar_dir is not None: self.indicator_values["PSAR_Dir"] = psar_dir.iloc[-1]

        if cfg["indicators"].get("vwap", False):
            self.df["VWAP"] = self._safe_calculate(self.calculate_vwap, "VWAP", min_data_points=1)
            if self.df["VWAP"] is not None: self.indicator_values["VWAP"] = self.df["VWAP"].iloc[-1]

        if cfg["indicators"].get("ehlers_supertrend", False):
            st_fast = self._safe_calculate(self.calculate_ehlers_supertrend, "EhlersSuperTrendFast", min_data_points=isd["ehlers_fast_period"] * 3, period=isd["ehlers_fast_period"], multiplier=isd["ehlers_fast_multiplier"])
            if st_fast is not None and not st_fast.empty:
                self.df["st_fast_dir"] = st_fast["direction"]
                self.df["st_fast_val"] = st_fast["supertrend"]
                self.indicator_values["ST_Fast_Dir"] = st_fast["direction"].iloc[-1]
                self.indicator_values["ST_Fast_Val"] = st_fast["supertrend"].iloc[-1]

            st_slow = self._safe_calculate(self.calculate_ehlers_supertrend, "EhlersSuperTrendSlow", min_data_points=isd["ehlers_slow_period"] * 3, period=isd["ehlers_slow_period"], multiplier=isd["ehlers_slow_multiplier"])
            if st_slow is not None and not st_slow.empty:
                self.df["st_slow_dir"] = st_slow["direction"]
                self.df["st_slow_val"] = st_slow["supertrend"]
                self.indicator_values["ST_Slow_Dir"] = st_slow["direction"].iloc[-1]
                self.indicator_values["ST_Slow_Val"] = st_slow["supertrend"].iloc[-1]

        if cfg["indicators"].get("macd", False):
            macd_line, signal_line, histogram = self._safe_calculate(self.calculate_macd, "MACD", min_data_points=isd["macd_slow_period"] + isd["macd_signal_period"], fast_period=isd["macd_fast_period"], slow_period=isd["macd_slow_period"], signal_period=isd["macd_signal_period"])
            if macd_line is not None: self.df["MACD_Line"] = macd_line
            if signal_line is not None: self.df["MACD_Signal"] = signal_line
            if histogram is not None: self.df["MACD_Hist"] = histogram
            if macd_line is not None: self.indicator_values["MACD_Line"] = macd_line.iloc[-1]
            if signal_line is not None: self.indicator_values["MACD_Signal"] = signal_line.iloc[-1]
            if histogram is not None: self.indicator_values["MACD_Hist"] = histogram.iloc[-1]

        if cfg["indicators"].get("adx", False):
            adx_val, plus_di, minus_di = self._safe_calculate(self.calculate_adx, "ADX", min_data_points=isd["adx_period"] * 2, period=isd["adx_period"])
            if adx_val is not None: self.df["ADX"] = adx_val
            if plus_di is not None: self.df["PlusDI"] = plus_di
            if minus_di is not None: self.df["MinusDI"] = minus_di
            if adx_val is not None: self.indicator_values["ADX"] = adx_val.iloc[-1]
            if plus_di is not None: self.indicator_values["PlusDI"] = plus_di.iloc[-1]
            if minus_di is not None: self.indicator_values["MinusDI"] = minus_di.iloc[-1]

        # Final cleanup
        initial_len = len(self.df)
        self.df.dropna(subset=["close"], inplace=True)
        self.df.fillna(0, inplace=True)

        if len(self.df) < initial_len:
            self.logger.debug(f"Dropped {initial_len - len(self.df)} rows with NaNs after indicator calculations.")
        if self.df.empty:
            self.logger.warning(f"{NEON_YELLOW}DataFrame is empty after calculating all indicators and dropping NaNs.{RESET}")
        else:
            self.logger.debug(f"Indicators calculated. Final DataFrame size: {len(self.df)}")

    def calculate_true_range(self) -> pd.Series:
        """Calculate True Range (TR)."""
        if len(self.df) < MIN_DATA_POINTS_TR: return pd.Series(np.nan, index=self.df.index)
        high_low = self.df["high"] - self.df["low"]
        high_prev_close = (self.df["high"] - self.df["close"].shift()).abs()
        low_prev_close = (self.df["low"] - self.df["close"].shift()).abs()
        return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)

    def calculate_super_smoother(self, series: pd.Series, period: int) -> pd.Series:
        """Apply Ehlers SuperSmoother filter to reduce lag and noise."""
        if period <= 0 or len(series) < MIN_DATA_POINTS_SMOOTHER: return pd.Series(np.nan, index=series.index)
        series = pd.to_numeric(series, errors="coerce").dropna()
        if len(series) < MIN_DATA_POINTS_SMOOTHER: return pd.Series(np.nan, index=series.index)

        a1 = np.exp(-np.sqrt(2) * np.pi / period)
        b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / period)
        c1 = 1 - b1 + a1**2
        c2 = b1 - 2 * a1**2
        c3 = a1**2

        filt = pd.Series(0.0, index=series.index)
        if len(series) >= 1: filt.iloc = series.iloc
        if len(series) >= 2: filt.iloc = (series.iloc + series.iloc) / 2

        for i in range(2, len(series)):
            filt.iloc[i] = ((c1 / 2) * (series.iloc[i] + series.iloc[i - 1])) + (c2 * filt.iloc[i - 1]) - (c3 * filt.iloc[i - 2])
        return filt.reindex(self.df.index)

    def calculate_ehlers_supertrend(self, period: int, multiplier: float) -> Optional[pd.DataFrame]:
        """Calculate SuperTrend using Ehlers SuperSmoother for price and volatility."""
        if len(self.df) < period * 3: return None
        df_copy = self.df.copy()
        hl2 = (df_copy["high"] + df_copy["low"]) / 2
        smoothed_price = self.calculate_super_smoother(hl2, period)
        tr = self.calculate_true_range()
        smoothed_atr = self.calculate_super_smoother(tr, period)

        if smoothed_price is None or smoothed_atr is None: return None

        df_copy["smoothed_price"] = smoothed_price
        df_copy["smoothed_atr"] = smoothed_atr
        df_copy.dropna(subset=["smoothed_price", "smoothed_atr"], inplace=True)
        if df_copy.empty: return None

        upper_band = df_copy["smoothed_price"] + multiplier * df_copy["smoothed_atr"]
        lower_band = df_copy["smoothed_price"] - multiplier * df_copy["smoothed_atr"]

        direction = pd.Series(0, index=df_copy.index, dtype=int)
        supertrend = pd.Series(np.nan, index=df_copy.index)

        first_valid_idx = df_copy.index
        supertrend.loc[first_valid_idx] = lower_band.loc[first_valid_idx]

        for i in range(1, len(df_copy)):
            current_idx = df_copy.index[i]
            prev_idx = df_copy.index[i - 1]

            prev_direction = direction.loc[prev_idx]
            prev_supertrend = supertrend.loc[prev_idx]
            curr_close = df_copy["close"].loc[current_idx]

            if prev_direction == 1:
                supertrend.loc[current_idx] = max(lower_band.loc[current_idx], prev_supertrend)
                if curr_close < supertrend.loc[current_idx]:
                    direction.loc[current_idx] = -1
                    supertrend.loc[current_idx] = upper_band.loc[current_idx]
                else: direction.loc[current_idx] = 1
            elif prev_direction == -1:
                supertrend.loc[current_idx] = min(upper_band.loc[current_idx], prev_supertrend)
                if curr_close > supertrend.loc[current_idx]:
                    direction.loc[current_idx] = 1
                    supertrend.loc[current_idx] = lower_band.loc[current_idx]
                else: direction.loc[current_idx] = -1
            else:
                if curr_close > lower_band.loc[current_idx]:
                    direction.loc[current_idx] = 1
                    supertrend.loc[current_idx] = lower_band.loc[current_idx]
                else:
                    direction.loc[current_idx] = -1
                    supertrend.loc[current_idx] = upper_band.loc[current_idx]

        result = pd.DataFrame({"supertrend": supertrend, "direction": direction})
        return result.reindex(self.df.index)

    def calculate_macd(self, fast_period: int, slow_period: int, signal_period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Moving Average Convergence Divergence (MACD)."""
        if len(self.df) < slow_period + signal_period:
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        ema_fast = self.df["close"].ewm(span=fast_period, adjust=False).mean()
        ema_slow = self.df["close"].ewm(span=slow_period, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    def calculate_rsi(self, period: int) -> pd.Series:
        """Calculate Relative Strength Index (RSI)."""
        if len(self.df) <= period: return pd.Series(np.nan, index=self.df.index)
        delta = self.df["close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.ewm(span=period, adjust=False, min_periods=period).mean()
        avg_loss = loss.ewm(span=period, adjust=False, min_periods=period).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_stoch_rsi(self, period: int, k_period: int, d_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate Stochastic RSI."""
        if len(self.df) <= period: return pd.Series(np.nan), pd.Series(np.nan)
        rsi = self.calculate_rsi(period)

        lowest_rsi = rsi.rolling(window=period, min_periods=period).min()
        highest_rsi = rsi.rolling(window=period, min_periods=period).max()

        stoch_rsi_k_raw = ((rsi - lowest_rsi) / (highest_rsi - lowest_rsi))
        stoch_rsi_k_raw = stoch_rsi_k_raw.replace([np.inf, -np.inf], np.nan).fillna(0) * 100

        stoch_rsi_k = stoch_rsi_k_raw.rolling(window=k_period, min_periods=k_period).mean()
        stoch_rsi_d = stoch_rsi_k.rolling(window=d_period, min_periods=d_period).mean()

        return stoch_rsi_k, stoch_rsi_d

    def calculate_adx(self, period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Average Directional Index (ADX)."""
        if len(self.df) < period * 2: return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        tr = self.calculate_true_range()
        plus_dm = self.df["high"].diff().clip(lower=0)
        minus_dm = -self.df["low"].diff().clip(lower=0)

        plus_dm_final = plus_dm.copy()
        minus_dm_final = minus_dm.copy()
        condition_plus_wins = (plus_dm_final > minus_dm_final)
        condition_minus_wins = (minus_dm_final > plus_dm_final)

        plus_dm_final[condition_minus_wins] = 0
        minus_dm_final[condition_plus_wins] = 0

        atr = tr.ewm(span=period, adjust=False).mean()
        plus_di = (plus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100
        minus_di = (minus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100

        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)).replace([np.inf, -np.inf], np.nan).fillna(0) * 100
        adx = dx.ewm(span=period, adjust=False).mean()

        return adx, plus_di, minus_di

    def calculate_bollinger_bands(self, period: int, std_dev: float) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands."""
        if len(self.df) < period: return (pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan))
        middle_band = self.df["close"].rolling(window=period, min_periods=period).mean()
        std = self.df["close"].rolling(window=period, min_periods=period).std()
        upper_band = middle_band + (std * std_dev)
        lower_band = middle_band - (std * std_dev)
        return upper_band, middle_band, lower_band

    def calculate_vwap(self) -> pd.Series:
        """Calculate Volume Weighted Average Price (VWAP)."""
        if self.df.empty: return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        cumulative_tp_vol = (typical_price * self.df["volume"]).cumsum()
        cumulative_vol = self.df["volume"].cumsum()
        vwap = cumulative_tp_vol / cumulative_vol
        return vwap

    def calculate_cci(self, period: int) -> pd.Series:
        """Calculate Commodity Channel Index (CCI)."""
        if len(self.df) < period: return pd.Series(np.nan, index=self.df.index)
        tp = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        sma_tp = tp.rolling(window=period, min_periods=period).mean()
        mad = tp.rolling(window=period, min_periods=period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=False)
        cci = (tp - sma_tp) / (0.015 * mad)
        cci = cci.replace([np.inf, -np.inf], np.nan).fillna(0)
        return cci

    def calculate_williams_r(self, period: int) -> pd.Series:
        """Calculate Williams %R."""
        if len(self.df) < period: return pd.Series(np.nan, index=self.df.index)
        highest_high = self.df["high"].rolling(window=period, min_periods=period).max()
        lowest_low = self.df["low"].rolling(window=period, min_periods=period).min()
        wr = -100 * ((highest_high - self.df["close"]) / (highest_high - lowest_low))
        wr = wr.replace([np.inf, -np.inf], np.nan).fillna(-50)
        return wr

    def calculate_ichimoku_cloud(self, tenkan_period: int, kijun_period: int, senkou_span_b_period: int, chikou_span_offset: int) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
        """Calculate Ichimoku Cloud components."""
        if (len(self.df) < max(tenkan_period, kijun_period, senkou_span_b_period) + chikou_span_offset):
            return (pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan))

        tenkan_sen = (self.df["high"].rolling(window=tenkan_period).max() + self.df["low"].rolling(window=tenkan_period).min()) / 2
        kijun_sen = (self.df["high"].rolling(window=kijun_period).max() + self.df["low"].rolling(window=kijun_period).min()) / 2
        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun_period)
        senkou_span_b = ((self.df["high"].rolling(window=senkou_span_b_period).max() + self.df["low"].rolling(window=senkou_span_b_period).min()) / 2).shift(kijun_period)
        chikou_span = self.df["close"].shift(-chikou_span_offset)

        return tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span

    def calculate_mfi(self, period: int) -> pd.Series:
        """Calculate Money Flow Index (MFI)."""
        if len(self.df) <= period: return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        money_flow = typical_price * self.df["volume"]

        positive_flow = pd.Series(0.0, index=self.df.index)
        negative_flow = pd.Series(0.0, index=self.df.index)

        for i in range(1, len(self.df)):
            if typical_price.iloc[i] > typical_price.iloc[i - 1]: positive_flow.iloc[i] = money_flow.iloc[i]
            elif typical_price.iloc[i] < typical_price.iloc[i - 1]: negative_flow.iloc[i] = money_flow.iloc[i]

        positive_mf_sum = positive_flow.rolling(window=period, min_periods=period).sum()
        negative_mf_sum = negative_flow.rolling(window=period, min_periods=period).sum()

        mf_ratio = positive_mf_sum / negative_mf_sum
        mfi = 100 - (100 / (1 + mf_ratio))
        mfi = mfi.replace([np.inf, -np.inf], np.nan).fillna(50)
        return mfi

    def calculate_obv(self, ema_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate On-Balance Volume (OBV) and its EMA."""
        if len(self.df) < MIN_DATA_POINTS_OBV: return pd.Series(np.nan), pd.Series(np.nan)

        obv = pd.Series(0.0, index=self.df.index)
        for i in range(1, len(self.df)):
            if self.df["close"].iloc[i] > self.df["close"].iloc[i - 1]: obv.iloc[i] = obv.iloc[i - 1] + self.df["volume"].iloc[i]
            elif self.df["close"].iloc[i] < self.df["close"].iloc[i - 1]: obv.iloc[i] = obv.iloc[i - 1] - self.df["volume"].iloc[i]
            else: obv.iloc[i] = obv.iloc[i - 1]

        obv_ema = obv.ewm(span=ema_period, adjust=False).mean()
        return obv, obv_ema

    def calculate_cmf(self, period: int) -> pd.Series:
        """Calculate Chaikin Money Flow (CMF)."""
        if len(self.df) < period: return pd.Series(np.nan)

        mfm = ((self.df["close"] - self.df["low"]) - (self.df["high"] - self.df["close"])) / (self.df["high"] - self.df["low"])
        mfm = mfm.replace([np.inf, -np.inf], np.nan).fillna(0)

        mfv = mfm * self.df["volume"]
        cmf = (mfv.rolling(window=period).sum() / self.df["volume"].rolling(window=period).sum())
        cmf = cmf.replace([np.inf, -np.inf], np.nan).fillna(0)

        return cmf

    def calculate_psar(self, acceleration: float, max_acceleration: float) -> tuple[pd.Series, pd.Series]:
        """Calculate Parabolic SAR."""
        if len(self.df) < MIN_DATA_POINTS_PSAR: return pd.Series(np.nan), pd.Series(np.nan)

        psar = self.df["close"].copy()
        bull = pd.Series(True, index=self.df.index)
        af = acceleration
        ep = self.df["low"].iloc if self.df["close"].iloc < self.df["close"].iloc else self.df["high"].iloc

        for i in range(1, len(self.df)):
            if bull.iloc[i - 1]:
                psar.iloc[i] = psar.iloc[i - 1] + af * (ep - psar.iloc[i - 1])
            else:
                psar.iloc[i] = psar.iloc[i - 1] - af * (psar.iloc[i - 1] - ep)

            reverse = False
            if bull.iloc[i - 1] and self.df["low"].iloc[i] < psar.iloc[i]:
                bull.iloc[i] = False; reverse = True
            elif not bull.iloc[i - 1] and self.df["high"].iloc[i] > psar.iloc[i]:
                bull.iloc[i] = True; reverse = True
            else: bull.iloc[i] = bull.iloc[i - 1]

            if reverse:
                af = acceleration
                ep = self.df["high"].iloc[i] if bull.iloc[i] else self.df["low"].iloc[i]
            elif bull.iloc[i]:
                if self.df["high"].iloc[i] > ep: ep = self.df["high"].iloc[i]; af = min(af + acceleration, max_acceleration)
            elif self.df["low"].iloc[i] < ep: ep = self.df["low"].iloc[i]; af = min(af + acceleration, max_acceleration)

            if bull.iloc[i]: psar.iloc[i] = min(psar.iloc[i], self.df["low"].iloc[i], self.df["low"].iloc[i-1])
            else: psar.iloc[i] = max(psar.iloc[i], self.df["high"].iloc[i], self.df["high"].iloc[i-1])

            if bull.iloc[i] and psar.iloc[i] > self.df["low"].iloc[i]: psar.iloc[i] = self.df["low"].iloc[i]
            elif not bull.iloc[i] and psar.iloc[i] < self.df["high"].iloc[i]: psar.iloc[i] = self.df["high"].iloc[i]

        direction = pd.Series(0, index=self.df.index, dtype=int)
        direction[psar < self.df["close"]] = 1
        direction[psar > self.df["close"]] = -1

        return psar, direction

    def calculate_fibonacci_levels(self) -> None:
        """Calculate Fibonacci retracement levels based on a recent high-low swing."""
        window = self.config["indicator_settings"]["fibonacci_window"]
        if len(self.df) < window:
            self.logger.warning(f"{NEON_YELLOW}Not enough data for Fibonacci levels (need {window} bars).{RESET}")
            return

        recent_high = self.df["high"].iloc[-window:].max()
        recent_low = self.df["low"].iloc[-window:].min()
        diff = recent_high - recent_low

        self.fib_levels = {
            "0.0%": Decimal(str(recent_high)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "23.6%": Decimal(str(recent_high - 0.236 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "38.2%": Decimal(str(recent_high - 0.382 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "50.0%": Decimal(str(recent_high - 0.500 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "61.8%": Decimal(str(recent_high - 0.618 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "78.6%": Decimal(str(recent_high - 0.786 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "100.0%": Decimal(str(recent_low)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
        }
        self.logger.debug(f"Calculated Fibonacci levels: {self.fib_levels}")

    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        """Safely retrieve an indicator value."""
        return self.indicator_values.get(key, default)

    def _check_orderbook(self, current_price: Decimal, orderbook_data: dict) -> float:
        """Analyze orderbook imbalance."""
        bids = orderbook_data.get("b", [])
        asks = orderbook_data.get("a", [])

        bid_volume = sum(Decimal(b) for b in bids)
        ask_volume = sum(Decimal(a) for a in asks)

        if bid_volume + ask_volume == 0: return 0.0

        imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
        self.logger.debug(f"Orderbook Imbalance: {imbalance:.4f} (Bids: {bid_volume}, Asks: {ask_volume})")
        return float(imbalance)

    def _get_mtf_trend(self, higher_tf_df: pd.DataFrame, indicator_type: str) -> str:
        """Determine trend from higher timeframe using specified indicator."""
        if higher_tf_df.empty: return "UNKNOWN"

        last_close = higher_tf_df["close"].iloc[-1]
        period = self.config["mtf_analysis"]["trend_period"]

        if indicator_type == "sma":
            if len(higher_tf_df) < period: return "UNKNOWN"
            sma = higher_tf_df["close"].rolling(window=period, min_periods=period).mean().iloc[-1]
            if last_close > sma: return "UP"
            if last_close < sma: return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ema":
            if len(higher_tf_df) < period: return "UNKNOWN"
            ema = higher_tf_df["close"].ewm(span=period, adjust=False, min_periods=period).mean().iloc[-1]
            if last_close > ema: return "UP"
            if last_close < ema: return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ehlers_supertrend":
            temp_analyzer = TradingAnalyzer(higher_tf_df, self.config, self.logger, self.symbol)
            st_result = temp_analyzer.calculate_ehlers_supertrend(
                self.indicator_settings["ehlers_slow_period"],
                self.indicator_settings["ehlers_slow_multiplier"],
            )
            if st_result is not None and not st_result.empty:
                st_dir = st_result["direction"].iloc[-1]
                if st_dir == 1: return "UP"
                if st_dir == -1: return "DOWN"
            return "UNKNOWN"
        return "UNKNOWN"

    def generate_trading_signal(
        self, current_price: Decimal, orderbook_data: dict | None, mtf_trends: dict[str, str]
    ) -> tuple[str, float]:
        """Generate a signal using confluence of indicators, including Ehlers SuperTrend."""
        signal_score = 0.0
        active_indicators = self.config["indicators"]
        weights = self.weights

        if self.df.empty:
            self.logger.warning(f"{NEON_YELLOW}DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}")
            return "HOLD", 0.0

        current_close = Decimal(str(self.df["close"].iloc[-1]))
        prev_close = Decimal(str(self.df["close"].iloc[-2])) if len(self.df) > 1 else current_close
        isd = self.indicator_settings

        # --- Indicator Scoring ---
        if active_indicators.get("ema_alignment", False):
            ema_short = self._get_indicator_value("EMA_Short")
            ema_long = self._get_indicator_value("EMA_Long")
            if not pd.isna(ema_short) and not pd.isna(ema_long):
                if ema_short > ema_long: signal_score += weights.get("ema_alignment", 0)
                elif ema_short < ema_long: signal_score -= weights.get("ema_alignment", 0)

        if active_indicators.get("sma_trend_filter", False):
            sma_long = self._get_indicator_value("SMA_Long")
            if not pd.isna(sma_long):
                if current_close > sma_long: signal_score += weights.get("sma_trend_filter", 0)
                elif current_close < sma_long: signal_score -= weights.get("sma_trend_filter", 0)

        if active_indicators.get("momentum", False):
            rsi = self._get_indicator_value("RSI")
            stoch_k = self._get_indicator_value("StochRSI_K")
            stoch_d = self._get_indicator_value("StochRSI_D")
            cci = self._get_indicator_value("CCI")
            wr = self._get_indicator_value("WR")
            mfi = self._get_indicator_value("MFI")

            if not pd.isna(rsi):
                if rsi < isd["rsi_oversold"]: signal_score += weights.get("rsi", 0) * 0.5
                elif rsi > isd["rsi_overbought"]: signal_score -= weights.get("rsi", 0) * 0.5

            if not pd.isna(stoch_k) and not pd.isna(stoch_d):
                if stoch_k > stoch_d and stoch_k < isd["stoch_rsi_oversold"]: signal_score += weights.get("stoch_rsi", 0) * 0.5
                elif stoch_k < stoch_d and stoch_k > isd["stoch_rsi_overbought"]: signal_score -= weights.get("stoch_rsi", 0) * 0.5

            if not pd.isna(cci):
                if cci < isd["cci_oversold"]: signal_score += weights.get("cci", 0) * 0.5
                elif cci > isd["cci_overbought"]: signal_score -= weights.get("cci", 0) * 0.5

            if not pd.isna(wr):
                if wr < isd["williams_r_oversold"]: signal_score += weights.get("wr", 0) * 0.5
                elif wr > isd["williams_r_overbought"]: signal_score -= weights.get("wr", 0) * 0.5

            if not pd.isna(mfi):
                if mfi < isd["mfi_oversold"]: signal_score += weights.get("mfi", 0) * 0.5
                elif mfi > isd["mfi_overbought"]: signal_score -= weights.get("mfi", 0) * 0.5

        if active_indicators.get("bollinger_bands", False):
            bb_upper = self._get_indicator_value("BB_Upper")
            bb_lower = self._get_indicator_value("BB_Lower")
            if not pd.isna(bb_upper) and not pd.isna(bb_lower):
                if current_close < bb_lower: signal_score += weights.get("bollinger_bands", 0) * 0.5
                elif current_close > bb_upper: signal_score -= weights.get("bollinger_bands", 0) * 0.5

        if active_indicators.get("vwap", False):
            vwap = self._get_indicator_value("VWAP")
            if not pd.isna(vwap):
                if current_close > vwap: signal_score += weights.get("vwap", 0) * 0.2
                elif current_close < vwap: signal_score -= weights.get("vwap", 0) * 0.2

                if len(self.df) > 1:
                    prev_close = Decimal(str(self.df["close"].iloc[-2]))
                    prev_vwap = Decimal(str(self.df["VWAP"].iloc[-2]))
                    if current_close > vwap and prev_close <= prev_vwap: signal_score += weights.get("vwap", 0) * 0.3
                    elif current_close < vwap and prev_close >= prev_vwap: signal_score -= weights.get("vwap", 0) * 0.3

        if active_indicators.get("psar", False):
            psar_val = self._get_indicator_value("PSAR_Val")
            psar_dir = self._get_indicator_value("PSAR_Dir")
            if not pd.isna(psar_val) and not pd.isna(psar_dir):
                if psar_dir == 1: signal_score += weights.get("psar", 0) * 0.5
                elif psar_dir == -1: signal_score -= weights.get("psar", 0) * 0.5

                if len(self.df) > 1:
                    prev_close = Decimal(str(self.df["close"].iloc[-2]))
                    prev_psar_val = Decimal(str(self.df["PSAR_Val"].iloc[-2]))
                    if current_close > psar_val and prev_close <= prev_psar_val: signal_score += weights.get("psar", 0) * 0.4
                    elif current_close < psar_val and prev_close >= prev_psar_val: signal_score -= weights.get("psar", 0) * 0.4

        if active_indicators.get("orderbook_imbalance", False) and orderbook_data:
            imbalance = self._check_orderbook(current_price, orderbook_data)
            signal_score += imbalance * weights.get("orderbook_imbalance", 0)

        if active_indicators.get("fibonacci_levels", False) and self.fib_levels:
            for level_name, level_price in self.fib_levels.items():
                if level_name not in ["0.0%", "100.0%"] and abs(current_price - level_price) / current_price < Decimal("0.001"):
                    if len(self.df) > 1:
                        prev_close = Decimal(str(self.df["close"].iloc[-2]))
                        if current_close > prev_close and current_close > level_price: signal_score += weights.get("fibonacci_levels", 0) * 0.1
                        elif current_close < prev_close and current_close < level_price: signal_score -= weights.get("fibonacci_levels", 0) * 0.1

        if active_indicators.get("ehlers_supertrend", False):
            st_fast_dir = self._get_indicator_value("ST_Fast_Dir")
            st_slow_dir = self._get_indicator_value("ST_Slow_Dir")
            prev_st_fast_dir = self.df["st_fast_dir"].iloc[-2] if "st_fast_dir" in self.df.columns and len(self.df) > 1 else np.nan
            weight = weights.get("ehlers_supertrend_alignment", 0.0)

            if not pd.isna(st_fast_dir) and not pd.isna(st_slow_dir) and not pd.isna(prev_st_fast_dir):
                if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1: signal_score += weight
                elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1: signal_score -= weight
                elif st_slow_dir == 1 and st_fast_dir == 1: signal_score += weight * 0.3
                elif st_slow_dir == -1 and st_fast_dir == -1: signal_score -= weight * 0.3

        if active_indicators.get("macd", False):
            macd_line = self._get_indicator_value("MACD_Line")
            signal_line = self._get_indicator_value("MACD_Signal")
            histogram = self._get_indicator_value("MACD_Hist")
            weight = weights.get("macd_alignment", 0.0)

            if not pd.isna(macd_line) and not pd.isna(signal_line) and not pd.isna(histogram):
                if len(self.df) > 1:
                    prev_macd_line = Decimal(str(self.df["MACD_Line"].iloc[-2]))
                    prev_signal_line = Decimal(str(self.df["MACD_Signal"].iloc[-2]))
                    if macd_line > signal_line and prev_macd_line <= prev_signal_line: signal_score += weight
                    elif macd_line < signal_line and prev_macd_line >= prev_signal_line: signal_score -= weight
                if len(self.df) > 1 and histogram > 0 and self.df["MACD_Hist"].iloc[-2] < 0: signal_score += weight * 0.2
                elif len(self.df) > 1 and histogram < 0 and self.df["MACD_Hist"].iloc[-2] > 0: signal_score -= weight * 0.2

        if active_indicators.get("adx", False):
            adx_val = self._get_indicator_value("ADX")
            plus_di = self._get_indicator_value("PlusDI")
            minus_di = self._get_indicator_value("MinusDI")
            weight = weights.get("adx_strength", 0.0)

            if not pd.isna(adx_val) and not pd.isna(plus_di) and not pd.isna(minus_di):
                if adx_val > ADX_STRONG_TREND_THRESHOLD:
                    if plus_di > minus_di: signal_score += weight
                    elif minus_di > plus_di: signal_score -= weight
                elif adx_val < ADX_WEAK_TREND_THRESHOLD: pass

        if active_indicators.get("ichimoku_cloud", False):
            tenkan_sen = self._get_indicator_value("Tenkan_Sen")
            kijun_sen = self._get_indicator_value("Kijun_Sen")
            senkou_span_a = self._get_indicator_value("Senkou_Span_A")
            senkou_span_b = self._get_indicator_value("Senkou_Span_B")
            chikou_span = self._get_indicator_value("Chikou_Span")
            weight = weights.get("ichimoku_confluence", 0.0)

            if not pd.isna(tenkan_sen) and not pd.isna(kijun_sen) and not pd.isna(senkou_span_a) and not pd.isna(senkou_span_b) and not pd.isna(chikou_span):
                if tenkan_sen > kijun_sen and self.df["Tenkan_Sen"].iloc[-2] <= self.df["Kijun_Sen"].iloc[-2]: signal_score += weight * 0.5
                elif tenkan_sen < kijun_sen and self.df["Tenkan_Sen"].iloc[-2] >= self.df["Kijun_Sen"].iloc[-2]: signal_score -= weight * 0.5

                if current_close > max(senkou_span_a, senkou_span_b) and self.df["close"].iloc[-2] <= max(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]): signal_score += weight * 0.7
                elif current_close < min(senkou_span_a, senkou_span_b) and self.df["close"].iloc[-2] >= min(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]): signal_score -= weight * 0.7

                if chikou_span > current_close and self.df["Chikou_Span"].iloc[-2] <= self.df["close"].iloc[-2]: signal_score += weight * 0.3
                elif chikou_span < current_close and self.df["Chikou_Span"].iloc[-2] >= self.df["close"].iloc[-2]: signal_score -= weight * 0.3

        if active_indicators.get("obv", False):
            obv_val = self._get_indicator_value("OBV")
            obv_ema = self._get_indicator_value("OBV_EMA")
            weight = weights.get("obv_momentum", 0.0)
            if not pd.isna(obv_val) and not pd.isna(obv_ema):
                if obv_val > obv_ema and self.df["OBV"].iloc[-2] <= self.df["OBV_EMA"].iloc[-2]: signal_score += weight * 0.5
                elif obv_val < obv_ema and self.df["OBV"].iloc[-2] >= self.df["OBV_EMA"].iloc[-2]: signal_score -= weight * 0.5
                if len(self.df) > 2:
                    if obv_val > self.df["OBV"].iloc[-2] and obv_val > self.df["OBV"].iloc[-3]: signal_score += weight * 0.2
                    elif obv_val < self.df["OBV"].iloc[-2] and obv_val < self.df["OBV"].iloc[-3]: signal_score -= weight * 0.2

        if active_indicators.get("cmf", False):
            cmf_val = self._get_indicator_value("CMF")
            weight = weights.get("cmf_flow", 0.0)
            if not pd.isna(cmf_val):
                if cmf_val > 0: signal_score += weight * 0.5
                elif cmf_val < 0: signal_score -= weight * 0.5
                if len(self.df) > 2:
                    if cmf_val > self.df["CMF"].iloc[-2] and cmf_val > self.df["CMF"].iloc[-3]: signal_score += weight * 0.3
                    elif cmf_val < self.df["CMF"].iloc[-2] and cmf_val < self.df["CMF"].iloc[-3]: signal_score -= weight * 0.3

        if self.config["mtf_analysis"]["enabled"] and mtf_trends:
            mtf_buy_score = sum(1 for trend in mtf_trends.values() if trend == "UP")
            mtf_sell_score = sum(-1 for trend in mtf_trends.values() if trend == "DOWN")
            if mtf_trends:
                normalized_mtf_score = (mtf_buy_score + mtf_sell_score) / len(mtf_trends)
                signal_score += weights.get("mtf_trend_confluence", 0.0) * normalized_mtf_score
                self.logger.debug(f"MTF Confluence: Score {normalized_mtf_score:.2f}")

        threshold = self.config["signal_score_threshold"]
        final_signal = "HOLD"
        if signal_score >= threshold: final_signal = "BUY"
        elif signal_score <= -threshold: final_signal = "SELL"

        self.logger.info(f"{NEON_YELLOW}Raw Technical Signal Score: {signal_score:.2f}, Final Technical Signal: {final_signal}{RESET}")
        return final_signal, signal_score


    # --- Remaining Indicator Implementations ---
    def calculate_true_range(self) -> pd.Series:
        """Calculate True Range (TR)."""
        if len(self.df) < MIN_DATA_POINTS_TR: return pd.Series(np.nan, index=self.df.index)
        high_low = self.df["high"] - self.df["low"]
        high_prev_close = (self.df["high"] - self.df["close"].shift()).abs()
        low_prev_close = (self.df["low"] - self.df["close"].shift()).abs()
        return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)

    def calculate_super_smoother(self, series: pd.Series, period: int) -> pd.Series:
        """Apply Ehlers SuperSmoother filter to reduce lag and noise."""
        if period <= 0 or len(series) < MIN_DATA_POINTS_SMOOTHER: return pd.Series(np.nan, index=series.index)
        series = pd.to_numeric(series, errors="coerce").dropna()
        if len(series) < MIN_DATA_POINTS_SMOOTHER: return pd.Series(np.nan, index=series.index)

        a1 = np.exp(-np.sqrt(2) * np.pi / period)
        b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / period)
        c1 = 1 - b1 + a1**2
        c2 = b1 - 2 * a1**2
        c3 = a1**2

        filt = pd.Series(0.0, index=series.index)
        if len(series) >= 1: filt.iloc = series.iloc
        if len(series) >= 2: filt.iloc = (series.iloc + series.iloc) / 2

        for i in range(2, len(series)):
            filt.iloc[i] = ((c1 / 2) * (series.iloc[i] + series.iloc[i - 1])) + (c2 * filt.iloc[i - 1]) - (c3 * filt.iloc[i - 2])
        return filt.reindex(self.df.index)

    def calculate_ehlers_supertrend(self, period: int, multiplier: float) -> Optional[pd.DataFrame]:
        """Calculate SuperTrend using Ehlers SuperSmoother for price and volatility."""
        if len(self.df) < period * 3: return None
        df_copy = self.df.copy()
        hl2 = (df_copy["high"] + df_copy["low"]) / 2
        smoothed_price = self.calculate_super_smoother(hl2, period)
        tr = self.calculate_true_range()
        smoothed_atr = self.calculate_super_smoother(tr, period)

        if smoothed_price is None or smoothed_atr is None: return None

        df_copy["smoothed_price"] = smoothed_price
        df_copy["smoothed_atr"] = smoothed_atr
        df_copy.dropna(subset=["smoothed_price", "smoothed_atr"], inplace=True)
        if df_copy.empty: return None

        upper_band = df_copy["smoothed_price"] + multiplier * df_copy["smoothed_atr"]
        lower_band = df_copy["smoothed_price"] - multiplier * df_copy["smoothed_atr"]

        direction = pd.Series(0, index=df_copy.index, dtype=int)
        supertrend = pd.Series(np.nan, index=df_copy.index)

        first_valid_idx = df_copy.index
        supertrend.loc[first_valid_idx] = lower_band.loc[first_valid_idx]

        for i in range(1, len(df_copy)):
            current_idx = df_copy.index[i]
            prev_idx = df_copy.index[i - 1]

            prev_direction = direction.loc[prev_idx]
            prev_supertrend = supertrend.loc[prev_idx]
            curr_close = df_copy["close"].loc[current_idx]

            if prev_direction == 1:
                supertrend.loc[current_idx] = max(lower_band.loc[current_idx], prev_supertrend)
                if curr_close < supertrend.loc[current_idx]:
                    direction.loc[current_idx] = -1
                    supertrend.loc[current_idx] = upper_band.loc[current_idx]
                else: direction.loc[current_idx] = 1
            elif prev_direction == -1:
                supertrend.loc[current_idx] = min(upper_band.loc[current_idx], prev_supertrend)
                if curr_close > supertrend.loc[current_idx]:
                    direction.loc[current_idx] = 1
                    supertrend.loc[current_idx] = lower_band.loc[current_idx]
                else: direction.loc[current_idx] = -1
            else:
                if curr_close > lower_band.loc[current_idx]:
                    direction.loc[current_idx] = 1
                    supertrend.loc[current_idx] = lower_band.loc[current_idx]
                else:
                    direction.loc[current_idx] = -1
                    supertrend.loc[current_idx] = upper_band.loc[current_idx]

        result = pd.DataFrame({"supertrend": supertrend, "direction": direction})
        return result.reindex(self.df.index)

    def calculate_macd(self, fast_period: int, slow_period: int, signal_period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Moving Average Convergence Divergence (MACD)."""
        if len(self.df) < slow_period + signal_period:
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        ema_fast = self.df["close"].ewm(span=fast_period, adjust=False).mean()
        ema_slow = self.df["close"].ewm(span=slow_period, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    def calculate_rsi(self, period: int) -> pd.Series:
        """Calculate Relative Strength Index (RSI)."""
        if len(self.df) <= period: return pd.Series(np.nan, index=self.df.index)
        delta = self.df["close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.ewm(span=period, adjust=False, min_periods=period).mean()
        avg_loss = loss.ewm(span=period, adjust=False, min_periods=period).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_stoch_rsi(self, period: int, k_period: int, d_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate Stochastic RSI."""
        if len(self.df) <= period: return pd.Series(np.nan), pd.Series(np.nan)
        rsi = self.calculate_rsi(period)

        lowest_rsi = rsi.rolling(window=period, min_periods=period).min()
        highest_rsi = rsi.rolling(window=period, min_periods=period).max()

        stoch_rsi_k_raw = ((rsi - lowest_rsi) / (highest_rsi - lowest_rsi))
        stoch_rsi_k_raw = stoch_rsi_k_raw.replace([np.inf, -np.inf], np.nan).fillna(0) * 100

        stoch_rsi_k = stoch_rsi_k_raw.rolling(window=k_period, min_periods=k_period).mean()
        stoch_rsi_d = stoch_rsi_k.rolling(window=d_period, min_periods=d_period).mean()

        return stoch_rsi_k, stoch_rsi_d

    def calculate_adx(self, period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Average Directional Index (ADX)."""
        if len(self.df) < period * 2: return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        tr = self.calculate_true_range()
        plus_dm = self.df["high"].diff().clip(lower=0)
        minus_dm = -self.df["low"].diff().clip(lower=0)

        plus_dm_final = plus_dm.copy()
        minus_dm_final = minus_dm.copy()
        condition_plus_wins = (plus_dm_final > minus_dm_final)
        condition_minus_wins = (minus_dm_final > plus_dm_final)

        plus_dm_final[condition_minus_wins] = 0
        minus_dm_final[condition_plus_wins] = 0

        atr = tr.ewm(span=period, adjust=False).mean()
        plus_di = (plus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100
        minus_di = (minus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100

        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)).replace([np.inf, -np.inf], np.nan).fillna(0) * 100
        adx = dx.ewm(span=period, adjust=False).mean()

        return adx, plus_di, minus_di

    def calculate_bollinger_bands(self, period: int, std_dev: float) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands."""
        if len(self.df) < period: return (pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan))
        middle_band = self.df["close"].rolling(window=period, min_periods=period).mean()
        std = self.df["close"].rolling(window=period, min_periods=period).std()
        upper_band = middle_band + (std * std_dev)
        lower_band = middle_band - (std * std_dev)
        return upper_band, middle_band, lower_band

    def calculate_vwap(self) -> pd.Series:
        """Calculate Volume Weighted Average Price (VWAP)."""
        if self.df.empty: return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        cumulative_tp_vol = (typical_price * self.df["volume"]).cumsum()
        cumulative_vol = self.df["volume"].cumsum()
        vwap = cumulative_tp_vol / cumulative_vol
        return vwap

    def calculate_cci(self, period: int) -> pd.Series:
        """Calculate Commodity Channel Index (CCI)."""
        if len(self.df) < period: return pd.Series(np.nan, index=self.df.index)
        tp = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        sma_tp = tp.rolling(window=period, min_periods=period).mean()
        mad = tp.rolling(window=period, min_periods=period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=False)
        cci = (tp - sma_tp) / (0.015 * mad)
        cci = cci.replace([np.inf, -np.inf], np.nan).fillna(0)
        return cci

    def calculate_williams_r(self, period: int) -> pd.Series:
        """Calculate Williams %R."""
        if len(self.df) < period: return pd.Series(np.nan, index=self.df.index)
        highest_high = self.df["high"].rolling(window=period, min_periods=period).max()
        lowest_low = self.df["low"].rolling(window=period, min_periods=period).min()
        wr = -100 * ((highest_high - self.df["close"]) / (highest_high - lowest_low))
        wr = wr.replace([np.inf, -np.inf], np.nan).fillna(-50)
        return wr

    def calculate_ichimoku_cloud(self, tenkan_period: int, kijun_period: int, senkou_span_b_period: int, chikou_span_offset: int) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
        """Calculate Ichimoku Cloud components."""
        if (len(self.df) < max(tenkan_period, kijun_period, senkou_span_b_period) + chikou_span_offset):
            return (pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan))

        tenkan_sen = (self.df["high"].rolling(window=tenkan_period).max() + self.df["low"].rolling(window=tenkan_period).min()) / 2
        kijun_sen = (self.df["high"].rolling(window=kijun_period).max() + self.df["low"].rolling(window=kijun_period).min()) / 2
        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun_period)
        senkou_span_b = ((self.df["high"].rolling(window=senkou_span_b_period).max() + self.df["low"].rolling(window=senkou_span_b_period).min()) / 2).shift(kijun_period)
        chikou_span = self.df["close"].shift(-chikou_span_offset)

        return tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span

    def calculate_mfi(self, period: int) -> pd.Series:
        """Calculate Money Flow Index (MFI)."""
        if len(self.df) <= period: return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        money_flow = typical_price * self.df["volume"]

        positive_flow = pd.Series(0.0, index=self.df.index)
        negative_flow = pd.Series(0.0, index=self.df.index)

        for i in range(1, len(self.df)):
            if typical_price.iloc[i] > typical_price.iloc[i - 1]: positive_flow.iloc[i] = money_flow.iloc[i]
            elif typical_price.iloc[i] < typical_price.iloc[i - 1]: negative_flow.iloc[i] = money_flow.iloc[i]

        positive_mf_sum = positive_flow.rolling(window=period, min_periods=period).sum()
        negative_mf_sum = negative_flow.rolling(window=period, min_periods=period).sum()

        mf_ratio = positive_mf_sum / negative_mf_sum
        mfi = 100 - (100 / (1 + mf_ratio))
        mfi = mfi.replace([np.inf, -np.inf], np.nan).fillna(50)
        return mfi

    def calculate_obv(self, ema_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate On-Balance Volume (OBV) and its EMA."""
        if len(self.df) < MIN_DATA_POINTS_OBV: return pd.Series(np.nan), pd.Series(np.nan)

        obv = pd.Series(0.0, index=self.df.index)
        for i in range(1, len(self.df)):
            if self.df["close"].iloc[i] > self.df["close"].iloc[i - 1]: obv.iloc[i] = obv.iloc[i - 1] + self.df["volume"].iloc[i]
            elif self.df["close"].iloc[i] < self.df["close"].iloc[i - 1]: obv.iloc[i] = obv.iloc[i - 1] - self.df["volume"].iloc[i]
            else: obv.iloc[i] = obv.iloc[i - 1]

        obv_ema = obv.ewm(span=ema_period, adjust=False).mean()
        return obv, obv_ema

    def calculate_cmf(self, period: int) -> pd.Series:
        """Calculate Chaikin Money Flow (CMF)."""
        if len(self.df) < period: return pd.Series(np.nan)

        mfm = ((self.df["close"] - self.df["low"]) - (self.df["high"] - self.df["close"])) / (self.df["high"] - self.df["low"])
        mfm = mfm.replace([np.inf, -np.inf], np.nan).fillna(0)

        mfv = mfm * self.df["volume"]
        cmf = (mfv.rolling(window=period).sum() / self.df["volume"].rolling(window=period).sum())
        cmf = cmf.replace([np.inf, -np.inf], np.nan).fillna(0)

        return cmf

    def calculate_psar(self, acceleration: float, max_acceleration: float) -> tuple[pd.Series, pd.Series]:
        """Calculate Parabolic SAR."""
        if len(self.df) < MIN_DATA_POINTS_PSAR: return pd.Series(np.nan), pd.Series(np.nan)

        psar = self.df["close"].copy()
        bull = pd.Series(True, index=self.df.index)
        af = acceleration
        ep = self.df["low"].iloc if self.df["close"].iloc < self.df["close"].iloc else self.df["high"].iloc

        for i in range(1, len(self.df)):
            if bull.iloc[i - 1]:
                psar.iloc[i] = psar.iloc[i - 1] + af * (ep - psar.iloc[i - 1])
            else:
                psar.iloc[i] = psar.iloc[i - 1] - af * (psar.iloc[i - 1] - ep)

            reverse = False
            if bull.iloc[i - 1] and self.df["low"].iloc[i] < psar.iloc[i]:
                bull.iloc[i] = False; reverse = True
            elif not bull.iloc[i - 1] and self.df["high"].iloc[i] > psar.iloc[i]:
                bull.iloc[i] = True; reverse = True
            else: bull.iloc[i] = bull.iloc[i - 1]

            if reverse:
                af = acceleration
                ep = self.df["high"].iloc[i] if bull.iloc[i] else self.df["low"].iloc[i]
            elif bull.iloc[i]:
                if self.df["high"].iloc[i] > ep: ep = self.df["high"].iloc[i]; af = min(af + acceleration, max_acceleration)
            elif self.df["low"].iloc[i] < ep: ep = self.df["low"].iloc[i]; af = min(af + acceleration, max_acceleration)

            if bull.iloc[i]: psar.iloc[i] = min(psar.iloc[i], self.df["low"].iloc[i], self.df["low"].iloc[i-1])
            else: psar.iloc[i] = max(psar.iloc[i], self.df["high"].iloc[i], self.df["high"].iloc[i-1])

            if bull.iloc[i] and psar.iloc[i] > self.df["low"].iloc[i]: psar.iloc[i] = self.df["low"].iloc[i]
            elif not bull.iloc[i] and psar.iloc[i] < self.df["high"].iloc[i]: psar.iloc[i] = self.df["high"].iloc[i]

        direction = pd.Series(0, index=self.df.index, dtype=int)
        direction[psar < self.df["close"]] = 1
        direction[psar > self.df["close"]] = -1

        return psar, direction

    def calculate_fibonacci_levels(self) -> None:
        """Calculate Fibonacci retracement levels based on a recent high-low swing."""
        window = self.config["indicator_settings"]["fibonacci_window"]
        if len(self.df) < window:
            self.logger.warning(f"{NEON_YELLOW}Not enough data for Fibonacci levels (need {window} bars).{RESET}")
            return

        recent_high = self.df["high"].iloc[-window:].max()
        recent_low = self.df["low"].iloc[-window:].min()
        diff = recent_high - recent_low

        self.fib_levels = {
            "0.0%": Decimal(str(recent_high)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "23.6%": Decimal(str(recent_high - 0.236 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "38.2%": Decimal(str(recent_high - 0.382 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "50.0%": Decimal(str(recent_high - 0.500 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "61.8%": Decimal(str(recent_high - 0.618 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "78.6%": Decimal(str(recent_high - 0.786 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "100.0%": Decimal(str(recent_low)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
        }
        self.logger.debug(f"Calculated Fibonacci levels: {self.fib_levels}")

    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        """Safely retrieve an indicator value."""
        return self.indicator_values.get(key, default)

    def _check_orderbook(self, current_price: Decimal, orderbook_data: dict) -> float:
        """Analyze orderbook imbalance."""
        bids = orderbook_data.get("b", [])
        asks = orderbook_data.get("a", [])

        bid_volume = sum(Decimal(b) for b in bids)
        ask_volume = sum(Decimal(a) for a in asks)

        if bid_volume + ask_volume == 0: return 0.0

        imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
        self.logger.debug(f"Orderbook Imbalance: {imbalance:.4f} (Bids: {bid_volume}, Asks: {ask_volume})")
        return float(imbalance)

    def _get_mtf_trend(self, higher_tf_df: pd.DataFrame, indicator_type: str) -> str:
        """Determine trend from higher timeframe using specified indicator."""
        if higher_tf_df.empty: return "UNKNOWN"

        last_close = higher_tf_df["close"].iloc[-1]
        period = self.config["mtf_analysis"]["trend_period"]

        if indicator_type == "sma":
            if len(higher_tf_df) < period: return "UNKNOWN"
            sma = higher_tf_df["close"].rolling(window=period, min_periods=period).mean().iloc[-1]
            if last_close > sma: return "UP"
            if last_close < sma: return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ema":
            if len(higher_tf_df) < period: return "UNKNOWN"
            ema = higher_tf_df["close"].ewm(span=period, adjust=False, min_periods=period).mean().iloc[-1]
            if last_close > ema: return "UP"
            if last_close < ema: return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ehlers_supertrend":
            temp_analyzer = TradingAnalyzer(higher_tf_df, self.config, self.logger, self.symbol)
            st_result = temp_analyzer.calculate_ehlers_supertrend(
                self.indicator_settings["ehlers_slow_period"],
                self.indicator_settings["ehlers_slow_multiplier"],
            )
            if st_result is not None and not st_result.empty:
                st_dir = st_result["direction"].iloc[-1]
                if st_dir == 1: return "UP"
                if st_dir == -1: return "DOWN"
            return "UNKNOWN"
        return "UNKNOWN"

    def generate_trading_signal(
        self, current_price: Decimal, orderbook_data: dict | None, mtf_trends: dict[str, str]
    ) -> tuple[str, float]:
        """Generate a signal using confluence of indicators, including Ehlers SuperTrend."""
        signal_score = 0.0
        active_indicators = self.config["indicators"]
        weights = self.weights

        if self.df.empty:
            self.logger.warning(f"{NEON_YELLOW}DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}")
            return "HOLD", 0.0

        current_close = Decimal(str(self.df["close"].iloc[-1]))
        prev_close = Decimal(str(self.df["close"].iloc[-2])) if len(self.df) > 1 else current_close
        isd = self.indicator_settings

        # --- Indicator Scoring ---
        if active_indicators.get("ema_alignment", False):
            ema_short = self._get_indicator_value("EMA_Short")
            ema_long = self._get_indicator_value("EMA_Long")
            if not pd.isna(ema_short) and not pd.isna(ema_long):
                if ema_short > ema_long: signal_score += weights.get("ema_alignment", 0)
                elif ema_short < ema_long: signal_score -= weights.get("ema_alignment", 0)

        if active_indicators.get("sma_trend_filter", False):
            sma_long = self._get_indicator_value("SMA_Long")
            if not pd.isna(sma_long):
                if current_close > sma_long: signal_score += weights.get("sma_trend_filter", 0)
                elif current_close < sma_long: signal_score -= weights.get("sma_trend_filter", 0)

        if active_indicators.get("momentum", False):
            rsi = self._get_indicator_value("RSI")
            stoch_k = self._get_indicator_value("StochRSI_K")
            stoch_d = self._get_indicator_value("StochRSI_D")
            cci = self._get_indicator_value("CCI")
            wr = self._get_indicator_value("WR")
            mfi = self._get_indicator_value("MFI")

            if not pd.isna(rsi):
                if rsi < isd["rsi_oversold"]: signal_score += weights.get("rsi", 0) * 0.5
                elif rsi > isd["rsi_overbought"]: signal_score -= weights.get("rsi", 0) * 0.5

            if not pd.isna(stoch_k) and not pd.isna(stoch_d):
                if stoch_k > stoch_d and stoch_k < isd["stoch_rsi_oversold"]: signal_score += weights.get("stoch_rsi", 0) * 0.5
                elif stoch_k < stoch_d and stoch_k > isd["stoch_rsi_overbought"]: signal_score -= weights.get("stoch_rsi", 0) * 0.5

            if not pd.isna(cci):
                if cci < isd["cci_oversold"]: signal_score += weights.get("cci", 0) * 0.5
                elif cci > isd["cci_overbought"]: signal_score -= weights.get("cci", 0) * 0.5

            if not pd.isna(wr):
                if wr < isd["williams_r_oversold"]: signal_score += weights.get("wr", 0) * 0.5
                elif wr > isd["williams_r_overbought"]: signal_score -= weights.get("wr", 0) * 0.5

            if not pd.isna(mfi):
                if mfi < isd["mfi_oversold"]: signal_score += weights.get("mfi", 0) * 0.5
                elif mfi > isd["mfi_overbought"]: signal_score -= weights.get("mfi", 0) * 0.5

        if active_indicators.get("bollinger_bands", False):
            bb_upper = self._get_indicator_value("BB_Upper")
            bb_lower = self._get_indicator_value("BB_Lower")
            if not pd.isna(bb_upper) and not pd.isna(bb_lower):
                if current_close < bb_lower: signal_score += weights.get("bollinger_bands", 0) * 0.5
                elif current_close > bb_upper: signal_score -= weights.get("bollinger_bands", 0) * 0.5

        if active_indicators.get("vwap", False):
            vwap = self._get_indicator_value("VWAP")
            if not pd.isna(vwap):
                if current_close > vwap: signal_score += weights.get("vwap", 0) * 0.2
                elif current_close < vwap: signal_score -= weights.get("vwap", 0) * 0.2

                if len(self.df) > 1:
                    prev_close = Decimal(str(self.df["close"].iloc[-2]))
                    prev_vwap = Decimal(str(self.df["VWAP"].iloc[-2]))
                    if current_close > vwap and prev_close <= prev_vwap: signal_score += weights.get("vwap", 0) * 0.3
                    elif current_close < vwap and prev_close >= prev_vwap: signal_score -= weights.get("vwap", 0) * 0.3

        if active_indicators.get("psar", False):
            psar_val = self._get_indicator_value("PSAR_Val")
            psar_dir = self._get_indicator_value("PSAR_Dir")
            if not pd.isna(psar_val) and not pd.isna(psar_dir):
                if psar_dir == 1: signal_score += weights.get("psar", 0) * 0.5
                elif psar_dir == -1: signal_score -= weights.get("psar", 0) * 0.5

                if len(self.df) > 1:
                    prev_close = Decimal(str(self.df["close"].iloc[-2]))
                    prev_psar_val = Decimal(str(self.df["PSAR_Val"].iloc[-2]))
                    if current_close > psar_val and prev_close <= prev_psar_val: signal_score += weights.get("psar", 0) * 0.4
                    elif current_close < psar_val and prev_close >= prev_psar_val: signal_score -= weights.get("psar", 0) * 0.4

        if active_indicators.get("orderbook_imbalance", False) and orderbook_data:
            imbalance = self._check_orderbook(current_price, orderbook_data)
            signal_score += imbalance * weights.get("orderbook_imbalance", 0)

        if active_indicators.get("fibonacci_levels", False) and self.fib_levels:
            for level_name, level_price in self.fib_levels.items():
                if level_name not in ["0.0%", "100.0%"] and abs(current_price - level_price) / current_price < Decimal("0.001"):
                    if len(self.df) > 1:
                        prev_close = Decimal(str(self.df["close"].iloc[-2]))
                        if current_close > prev_close and current_close > level_price: signal_score += weights.get("fibonacci_levels", 0) * 0.1
                        elif current_close < prev_close and current_close < level_price: signal_score -= weights.get("fibonacci_levels", 0) * 0.1

        if active_indicators.get("ehlers_supertrend", False):
            st_fast_dir = self._get_indicator_value("ST_Fast_Dir")
            st_slow_dir = self._get_indicator_value("ST_Slow_Dir")
            prev_st_fast_dir = self.df["st_fast_dir"].iloc[-2] if "st_fast_dir" in self.df.columns and len(self.df) > 1 else np.nan
            weight = weights.get("ehlers_supertrend_alignment", 0.0)

            if not pd.isna(st_fast_dir) and not pd.isna(st_slow_dir) and not pd.isna(prev_st_fast_dir):
                if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1: signal_score += weight
                elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1: signal_score -= weight
                elif st_slow_dir == 1 and st_fast_dir == 1: signal_score += weight * 0.3
                elif st_slow_dir == -1 and st_fast_dir == -1: signal_score -= weight * 0.3

        if active_indicators.get("macd", False):
            macd_line = self._get_indicator_value("MACD_Line")
            signal_line = self._get_indicator_value("MACD_Signal")
            histogram = self._get_indicator_value("MACD_Hist")
            weight = weights.get("macd_alignment", 0.0)

            if not pd.isna(macd_line) and not pd.isna(signal_line) and not pd.isna(histogram):
                if len(self.df) > 1:
                    prev_macd_line = Decimal(str(self.df["MACD_Line"].iloc[-2]))
                    prev_signal_line = Decimal(str(self.df["MACD_Signal"].iloc[-2]))
                    if macd_line > signal_line and prev_macd_line <= prev_signal_line: signal_score += weight
                    elif macd_line < signal_line and prev_macd_line >= prev_signal_line: signal_score -= weight
                if len(self.df) > 1 and histogram > 0 and self.df["MACD_Hist"].iloc[-2] < 0: signal_score += weight * 0.2
                elif len(self.df) > 1 and histogram < 0 and self.df["MACD_Hist"].iloc[-2] > 0: signal_score -= weight * 0.2

        if active_indicators.get("adx", False):
            adx_val = self._get_indicator_value("ADX")
            plus_di = self._get_indicator_value("PlusDI")
            minus_di = self._get_indicator_value("MinusDI")
            weight = weights.get("adx_strength", 0.0)

            if not pd.isna(adx_val) and not pd.isna(plus_di) and not pd.isna(minus_di):
                if adx_val > ADX_STRONG_TREND_THRESHOLD:
                    if plus_di > minus_di: signal_score += weight
                    elif minus_di > plus_di: signal_score -= weight
                elif adx_val < ADX_WEAK_TREND_THRESHOLD: pass

        if active_indicators.get("ichimoku_cloud", False):
            tenkan_sen = self._get_indicator_value("Tenkan_Sen")
            kijun_sen = self._get_indicator_value("Kijun_Sen")
            senkou_span_a = self._get_indicator_value("Senkou_Span_A")
            senkou_span_b = self._get_indicator_value("Senkou_Span_B")
            chikou_span = self._get_indicator_value("Chikou_Span")
            weight = weights.get("ichimoku_confluence", 0.0)

            if not pd.isna(tenkan_sen) and not pd.isna(kijun_sen) and not pd.isna(senkou_span_a) and not pd.isna(senkou_span_b) and not pd.isna(chikou_span):
                if tenkan_sen > kijun_sen and self.df["Tenkan_Sen"].iloc[-2] <= self.df["Kijun_Sen"].iloc[-2]: signal_score += weight * 0.5
                elif tenkan_sen < kijun_sen and self.df["Tenkan_Sen"].iloc[-2] >= self.df["Kijun_Sen"].iloc[-2]: signal_score -= weight * 0.5

                if current_close > max(senkou_span_a, senkou_span_b) and self.df["close"].iloc[-2] <= max(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]): signal_score += weight * 0.7
                elif current_close < min(senkou_span_a, senkou_span_b) and self.df["close"].iloc[-2] >= min(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]): signal_score -= weight * 0.7

                if chikou_span > current_close and self.df["Chikou_Span"].iloc[-2] <= self.df["close"].iloc[-2]: signal_score += weight * 0.3
                elif chikou_span < current_close and self.df["Chikou_Span"].iloc[-2] >= self.df["close"].iloc[-2]: signal_score -= weight * 0.3

        if active_indicators.get("obv", False):
            obv_val = self._get_indicator_value("OBV")
            obv_ema = self._get_indicator_value("OBV_EMA")
            weight = weights.get("obv_momentum", 0.0)
            if not pd.isna(obv_val) and not pd.isna(obv_ema):
                if obv_val > obv_ema and self.df["OBV"].iloc[-2] <= self.df["OBV_EMA"].iloc[-2]: signal_score += weight * 0.5
                elif obv_val < obv_ema and self.df["OBV"].iloc[-2] >= self.df["OBV_EMA"].iloc[-2]: signal_score -= weight * 0.5
                if len(self.df) > 2:
                    if obv_val > self.df["OBV"].iloc[-2] and obv_val > self.df["OBV"].iloc[-3]: signal_score += weight * 0.2
                    elif obv_val < self.df["OBV"].iloc[-2] and obv_val < self.df["OBV"].iloc[-3]: signal_score -= weight * 0.2

        if active_indicators.get("cmf", False):
            cmf_val = self._get_indicator_value("CMF")
            weight = weights.get("cmf_flow", 0.0)
            if not pd.isna(cmf_val):
                if cmf_val > 0: signal_score += weight * 0.5
                elif cmf_val < 0: signal_score -= weight * 0.5
                if len(self.df) > 2:
                    if cmf_val > self.df["CMF"].iloc[-2] and cmf_val > self.df["CMF"].iloc[-3]: signal_score += weight * 0.3
                    elif cmf_val < self.df["CMF"].iloc[-2] and cmf_val < self.df["CMF"].iloc[-3]: signal_score -= weight * 0.3

        if self.config["mtf_analysis"]["enabled"] and mtf_trends:
            mtf_buy_score = sum(1 for trend in mtf_trends.values() if trend == "UP")
            mtf_sell_score = sum(-1 for trend in mtf_trends.values() if trend == "DOWN")
            if mtf_trends:
                normalized_mtf_score = (mtf_buy_score + mtf_sell_score) / len(mtf_trends)
                signal_score += weights.get("mtf_trend_confluence", 0.0) * normalized_mtf_score
                self.logger.debug(f"MTF Confluence: Score {normalized_mtf_score:.2f}")

        threshold = self.config["signal_score_threshold"]
        final_signal = "HOLD"
        if signal_score >= threshold: final_signal = "BUY"
        elif signal_score <= -threshold: final_signal = "SELL"

        self.logger.info(f"{NEON_YELLOW}Raw Technical Signal Score: {signal_score:.2f}, Final Technical Signal: {final_signal}{RESET}")
        return final_signal, signal_score


    # --- Remaining Indicator Implementations ---
    def calculate_true_range(self) -> pd.Series:
        """Calculate True Range (TR)."""
        if len(self.df) < MIN_DATA_POINTS_TR: return pd.Series(np.nan, index=self.df.index)
        high_low = self.df["high"] - self.df["low"]
        high_prev_close = (self.df["high"] - self.df["close"].shift()).abs()
        low_prev_close = (self.df["low"] - self.df["close"].shift()).abs()
        return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)

    def calculate_super_smoother(self, series: pd.Series, period: int) -> pd.Series:
        """Apply Ehlers SuperSmoother filter to reduce lag and noise."""
        if period <= 0 or len(series) < MIN_DATA_POINTS_SMOOTHER: return pd.Series(np.nan, index=series.index)
        series = pd.to_numeric(series, errors="coerce").dropna()
        if len(series) < MIN_DATA_POINTS_SMOOTHER: return pd.Series(np.nan, index=series.index)

        a1 = np.exp(-np.sqrt(2) * np.pi / period)
        b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / period)
        c1 = 1 - b1 + a1**2
        c2 = b1 - 2 * a1**2
        c3 = a1**2

        filt = pd.Series(0.0, index=series.index)
        if len(series) >= 1: filt.iloc = series.iloc
        if len(series) >= 2: filt.iloc = (series.iloc + series.iloc) / 2

        for i in range(2, len(series)):
            filt.iloc[i] = ((c1 / 2) * (series.iloc[i] + series.iloc[i - 1])) + (c2 * filt.iloc[i - 1]) - (c3 * filt.iloc[i - 2])
        return filt.reindex(self.df.index)

    def calculate_ehlers_supertrend(self, period: int, multiplier: float) -> Optional[pd.DataFrame]:
        """Calculate SuperTrend using Ehlers SuperSmoother for price and volatility."""
        if len(self.df) < period * 3: return None
        df_copy = self.df.copy()
        hl2 = (df_copy["high"] + df_copy["low"]) / 2
        smoothed_price = self.calculate_super_smoother(hl2, period)
        tr = self.calculate_true_range()
        smoothed_atr = self.calculate_super_smoother(tr, period)

        if smoothed_price is None or smoothed_atr is None: return None

        df_copy["smoothed_price"] = smoothed_price
        df_copy["smoothed_atr"] = smoothed_atr
        df_copy.dropna(subset=["smoothed_price", "smoothed_atr"], inplace=True)
        if df_copy.empty: return None

        upper_band = df_copy["smoothed_price"] + multiplier * df_copy["smoothed_atr"]
        lower_band = df_copy["smoothed_price"] - multiplier * df_copy["smoothed_atr"]

        direction = pd.Series(0, index=df_copy.index, dtype=int)
        supertrend = pd.Series(np.nan, index=df_copy.index)

        first_valid_idx = df_copy.index
        supertrend.loc[first_valid_idx] = lower_band.loc[first_valid_idx]

        for i in range(1, len(df_copy)):
            current_idx = df_copy.index[i]
            prev_idx = df_copy.index[i - 1]

            prev_direction = direction.loc[prev_idx]
            prev_supertrend = supertrend.loc[prev_idx]
            curr_close = df_copy["close"].loc[current_idx]

            if prev_direction == 1:
                supertrend.loc[current_idx] = max(lower_band.loc[current_idx], prev_supertrend)
                if curr_close < supertrend.loc[current_idx]:
                    direction.loc[current_idx] = -1
                    supertrend.loc[current_idx] = upper_band.loc[current_idx]
                else: direction.loc[current_idx] = 1
            elif prev_direction == -1:
                supertrend.loc[current_idx] = min(upper_band.loc[current_idx], prev_supertrend)
                if curr_close > supertrend.loc[current_idx]:
                    direction.loc[current_idx] = 1
                    supertrend.loc[current_idx] = lower_band.loc[current_idx]
                else: direction.loc[current_idx] = -1
            else:
                if curr_close > lower_band.loc[current_idx]:
                    direction.loc[current_idx] = 1
                    supertrend.loc[current_idx] = lower_band.loc[current_idx]
                else:
                    direction.loc[current_idx] = -1
                    supertrend.loc[current_idx] = upper_band.loc[current_idx]

        result = pd.DataFrame({"supertrend": supertrend, "direction": direction})
        return result.reindex(self.df.index)

    def calculate_macd(self, fast_period: int, slow_period: int, signal_period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Moving Average Convergence Divergence (MACD)."""
        if len(self.df) < slow_period + signal_period:
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        ema_fast = self.df["close"].ewm(span=fast_period, adjust=False).mean()
        ema_slow = self.df["close"].ewm(span=slow_period, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    def calculate_rsi(self, period: int) -> pd.Series:
        """Calculate Relative Strength Index (RSI)."""
        if len(self.df) <= period: return pd.Series(np.nan, index=self.df.index)
        delta = self.df["close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.ewm(span=period, adjust=False, min_periods=period).mean()
        avg_loss = loss.ewm(span=period, adjust=False, min_periods=period).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_stoch_rsi(self, period: int, k_period: int, d_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate Stochastic RSI."""
        if len(self.df) <= period: return pd.Series(np.nan), pd.Series(np.nan)
        rsi = self.calculate_rsi(period)

        lowest_rsi = rsi.rolling(window=period, min_periods=period).min()
        highest_rsi = rsi.rolling(window=period, min_periods=period).max()

        stoch_rsi_k_raw = ((rsi - lowest_rsi) / (highest_rsi - lowest_rsi))
        stoch_rsi_k_raw = stoch_rsi_k_raw.replace([np.inf, -np.inf], np.nan).fillna(0) * 100

        stoch_rsi_k = stoch_rsi_k_raw.rolling(window=k_period, min_periods=k_period).mean()
        stoch_rsi_d = stoch_rsi_k.rolling(window=d_period, min_periods=d_period).mean()

        return stoch_rsi_k, stoch_rsi_d

    def calculate_adx(self, period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Average Directional Index (ADX)."""
        if len(self.df) < period * 2: return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        tr = self.calculate_true_range()
        plus_dm = self.df["high"].diff().clip(lower=0)
        minus_dm = -self.df["low"].diff().clip(lower=0)

        plus_dm_final = plus_dm.copy()
        minus_dm_final = minus_dm.copy()
        condition_plus_wins = (plus_dm_final > minus_dm_final)
        condition_minus_wins = (minus_dm_final > plus_dm_final)

        plus_dm_final[condition_minus_wins] = 0
        minus_dm_final[condition_plus_wins] = 0

        atr = tr.ewm(span=period, adjust=False).mean()
        plus_di = (plus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100
        minus_di = (minus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100

        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)).replace([np.inf, -np.inf], np.nan).fillna(0) * 100
        adx = dx.ewm(span=period, adjust=False).mean()

        return adx, plus_di, minus_di

    def calculate_bollinger_bands(self, period: int, std_dev: float) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands."""
        if len(self.df) < period: return (pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan))
        middle_band = self.df["close"].rolling(window=period, min_periods=period).mean()
        std = self.df["close"].rolling(window=period, min_periods=period).std()
        upper_band = middle_band + (std * std_dev)
        lower_band = middle_band - (std * std_dev)
        return upper_band, middle_band, lower_band

    def calculate_vwap(self) -> pd.Series:
        """Calculate Volume Weighted Average Price (VWAP)."""
        if self.df.empty: return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        cumulative_tp_vol = (typical_price * self.df["volume"]).cumsum()
        cumulative_vol = self.df["volume"].cumsum()
        vwap = cumulative_tp_vol / cumulative_vol
        return vwap

    def calculate_cci(self, period: int) -> pd.Series:
        """Calculate Commodity Channel Index (CCI)."""
        if len(self.df) < period: return pd.Series(np.nan, index=self.df.index)
        tp = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        sma_tp = tp.rolling(window=period, min_periods=period).mean()
        mad = tp.rolling(window=period, min_periods=period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=False)
        cci = (tp - sma_tp) / (0.015 * mad)
        cci = cci.replace([np.inf, -np.inf], np.nan).fillna(0)
        return cci

    def calculate_williams_r(self, period: int) -> pd.Series:
        """Calculate Williams %R."""
        if len(self.df) < period: return pd.Series(np.nan, index=self.df.index)
        highest_high = self.df["high"].rolling(window=period, min_periods=period).max()
        lowest_low = self.df["low"].rolling(window=period, min_periods=period).min()
        wr = -100 * ((highest_high - self.df["close"]) / (highest_high - lowest_low))
        wr = wr.replace([np.inf, -np.inf], np.nan).fillna(-50)
        return wr

    def calculate_ichimoku_cloud(self, tenkan_period: int, kijun_period: int, senkou_span_b_period: int, chikou_span_offset: int) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
        """Calculate Ichimoku Cloud components."""
        if (len(self.df) < max(tenkan_period, kijun_period, senkou_span_b_period) + chikou_span_offset):
            return (pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan))

        tenkan_sen = (self.df["high"].rolling(window=tenkan_period).max() + self.df["low"].rolling(window=tenkan_period).min()) / 2
        kijun_sen = (self.df["high"].rolling(window=kijun_period).max() + self.df["low"].rolling(window=kijun_period).min()) / 2
        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun_period)
        senkou_span_b = ((self.df["high"].rolling(window=senkou_span_b_period).max() + self.df["low"].rolling(window=senkou_span_b_period).min()) / 2).shift(kijun_period)
        chikou_span = self.df["close"].shift(-chikou_span_offset)

        return tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span

    def calculate_mfi(self, period: int) -> pd.Series:
        """Calculate Money Flow Index (MFI)."""
        if len(self.df) <= period: return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        money_flow = typical_price * self.df["volume"]

        positive_flow = pd.Series(0.0, index=self.df.index)
        negative_flow = pd.Series(0.0, index=self.df.index)

        for i in range(1, len(self.df)):
            if typical_price.iloc[i] > typical_price.iloc[i - 1]: positive_flow.iloc[i] = money_flow.iloc[i]
            elif typical_price.iloc[i] < typical_price.iloc[i - 1]: negative_flow.iloc[i] = money_flow.iloc[i]

        positive_mf_sum = positive_flow.rolling(window=period, min_periods=period).sum()
        negative_mf_sum = negative_flow.rolling(window=period, min_periods=period).sum()

        mf_ratio = positive_mf_sum / negative_mf_sum
        mfi = 100 - (100 / (1 + mf_ratio))
        mfi = mfi.replace([np.inf, -np.inf], np.nan).fillna(50)
        return mfi

    def calculate_obv(self, ema_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate On-Balance Volume (OBV) and its EMA."""
        if len(self.df) < MIN_DATA_POINTS_OBV: return pd.Series(np.nan), pd.Series(np.nan)

        obv = pd.Series(0.0, index=self.df.index)
        for i in range(1, len(self.df)):
            if self.df["close"].iloc[i] > self.df["close"].iloc[i - 1]: obv.iloc[i] = obv.iloc[i - 1] + self.df["volume"].iloc[i]
            elif self.df["close"].iloc[i] < self.df["close"].iloc[i - 1]: obv.iloc[i] = obv.iloc[i - 1] - self.df["volume"].iloc[i]
            else: obv.iloc[i] = obv.iloc[i - 1]

        obv_ema = obv.ewm(span=ema_period, adjust=False).mean()
        return obv, obv_ema

    def calculate_cmf(self, period: int) -> pd.Series:
        """Calculate Chaikin Money Flow (CMF)."""
        if len(self.df) < period: return pd.Series(np.nan)

        mfm = ((self.df["close"] - self.df["low"]) - (self.df["high"] - self.df["close"])) / (self.df["high"] - self.df["low"])
        mfm = mfm.replace([np.inf, -np.inf], np.nan).fillna(0)

        mfv = mfm * self.df["volume"]
        cmf = (mfv.rolling(window=period).sum() / self.df["volume"].rolling(window=period).sum())
        cmf = cmf.replace([np.inf, -np.inf], np.nan).fillna(0)

        return cmf

    def calculate_psar(self, acceleration: float, max_acceleration: float) -> tuple[pd.Series, pd.Series]:
        """Calculate Parabolic SAR."""
        if len(self.df) < MIN_DATA_POINTS_PSAR: return pd.Series(np.nan), pd.Series(np.nan)

        psar = self.df["close"].copy()
        bull = pd.Series(True, index=self.df.index)
        af = acceleration
        ep = self.df["low"].iloc if self.df["close"].iloc < self.df["close"].iloc else self.df["high"].iloc

        for i in range(1, len(self.df)):
            if bull.iloc[i - 1]:
                psar.iloc[i] = psar.iloc[i - 1] + af * (ep - psar.iloc[i - 1])
            else:
                psar.iloc[i] = psar.iloc[i - 1] - af * (psar.iloc[i - 1] - ep)

            reverse = False
            if bull.iloc[i - 1] and self.df["low"].iloc[i] < psar.iloc[i]:
                bull.iloc[i] = False; reverse = True
            elif not bull.iloc[i - 1] and self.df["high"].iloc[i] > psar.iloc[i]:
                bull.iloc[i] = True; reverse = True
            else: bull.iloc[i] = bull.iloc[i - 1]

            if reverse:
                af = acceleration
                ep = self.df["high"].iloc[i] if bull.iloc[i] else self.df["low"].iloc[i]
            elif bull.iloc[i]:
                if self.df["high"].iloc[i] > ep: ep = self.df["high"].iloc[i]; af = min(af + acceleration, max_acceleration)
            elif self.df["low"].iloc[i] < ep: ep = self.df["low"].iloc[i]; af = min(af + acceleration, max_acceleration)

            if bull.iloc[i]: psar.iloc[i] = min(psar.iloc[i], self.df["low"].iloc[i], self.df["low"].iloc[i-1])
            else: psar.iloc[i] = max(psar.iloc[i], self.df["high"].iloc[i], self.df["high"].iloc[i-1])

            if bull.iloc[i] and psar.iloc[i] > self.df["low"].iloc[i]: psar.iloc[i] = self.df["low"].iloc[i]
            elif not bull.iloc[i] and psar.iloc[i] < self.df["high"].iloc[i]: psar.iloc[i] = self.df["high"].iloc[i]

        direction = pd.Series(0, index=self.df.index, dtype=int)
        direction[psar < self.df["close"]] = 1
        direction[psar > self.df["close"]] = -1

        return psar, direction

    def calculate_fibonacci_levels(self) -> None:
        """Calculate Fibonacci retracement levels based on a recent high-low swing."""
        window = self.config["indicator_settings"]["fibonacci_window"]
        if len(self.df) < window:
            self.logger.warning(f"{NEON_YELLOW}Not enough data for Fibonacci levels (need {window} bars).{RESET}")
            return

        recent_high = self.df["high"].iloc[-window:].max()
        recent_low = self.df["low"].iloc[-window:].min()
        diff = recent_high - recent_low

        self.fib_levels = {
            "0.0%": Decimal(str(recent_high)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "23.6%": Decimal(str(recent_high - 0.236 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "38.2%": Decimal(str(recent_high - 0.382 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "50.0%": Decimal(str(recent_high - 0.500 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "61.8%": Decimal(str(recent_high - 0.618 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "78.6%": Decimal(str(recent_high - 0.786 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "100.0%": Decimal(str(recent_low)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
        }
        self.logger.debug(f"Calculated Fibonacci levels: {self.fib_levels}")

    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        """Safely retrieve an indicator value."""
        return self.indicator_values.get(key, default)

    def _check_orderbook(self, current_price: Decimal, orderbook_data: dict) -> float:
        """Analyze orderbook imbalance."""
        bids = orderbook_data.get("b", [])
        asks = orderbook_data.get("a", [])

        bid_volume = sum(Decimal(b) for b in bids)
        ask_volume = sum(Decimal(a) for a in asks)

        if bid_volume + ask_volume == 0: return 0.0

        imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
        self.logger.debug(f"Orderbook Imbalance: {imbalance:.4f} (Bids: {bid_volume}, Asks: {ask_volume})")
        return float(imbalance)

    def _get_mtf_trend(self, higher_tf_df: pd.DataFrame, indicator_type: str) -> str:
        """Determine trend from higher timeframe using specified indicator."""
        if higher_tf_df.empty: return "UNKNOWN"

        last_close = higher_tf_df["close"].iloc[-1]
        period = self.config["mtf_analysis"]["trend_period"]

        if indicator_type == "sma":
            if len(higher_tf_df) < period: return "UNKNOWN"
            sma = higher_tf_df["close"].rolling(window=period, min_periods=period).mean().iloc[-1]
            if last_close > sma: return "UP"
            if last_close < sma: return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ema":
            if len(higher_tf_df) < period: return "UNKNOWN"
            ema = higher_tf_df["close"].ewm(span=period, adjust=False, min_periods=period).mean().iloc[-1]
            if last_close > ema: return "UP"
            if last_close < ema: return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ehlers_supertrend":
            temp_analyzer = TradingAnalyzer(higher_tf_df, self.config, self.logger, self.symbol)
            st_result = temp_analyzer.calculate_ehlers_supertrend(
                self.indicator_settings["ehlers_slow_period"],
                self.indicator_settings["ehlers_slow_multiplier"],
            )
            if st_result is not None and not st_result.empty:
                st_dir = st_result["direction"].iloc[-1]
                if st_dir == 1: return "UP"
                if st_dir == -1: return "DOWN"
            return "UNKNOWN"
        return "UNKNOWN"

    def generate_trading_signal(
        self, current_price: Decimal, orderbook_data: dict | None, mtf_trends: dict[str, str]
    ) -> tuple[str, float]:
        """Generate a signal using confluence of indicators, including Ehlers SuperTrend."""
        signal_score = 0.0
        active_indicators = self.config["indicators"]
        weights = self.weights

        if self.df.empty:
            self.logger.warning(f"{NEON_YELLOW}DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}")
            return "HOLD", 0.0

        current_close = Decimal(str(self.df["close"].iloc[-1]))
        prev_close = Decimal(str(self.df["close"].iloc[-2])) if len(self.df) > 1 else current_close
        isd = self.indicator_settings

        # --- Indicator Scoring ---
        if active_indicators.get("ema_alignment", False):
            ema_short = self._get_indicator_value("EMA_Short")
            ema_long = self._get_indicator_value("EMA_Long")
            if not pd.isna(ema_short) and not pd.isna(ema_long):
                if ema_short > ema_long: signal_score += weights.get("ema_alignment", 0)
                elif ema_short < ema_long: signal_score -= weights.get("ema_alignment", 0)

        if active_indicators.get("sma_trend_filter", False):
            sma_long = self._get_indicator_value("SMA_Long")
            if not pd.isna(sma_long):
                if current_close > sma_long: signal_score += weights.get("sma_trend_filter", 0)
                elif current_close < sma_long: signal_score -= weights.get("sma_trend_filter", 0)

        if active_indicators.get("momentum", False):
            rsi = self._get_indicator_value("RSI")
            stoch_k = self._get_indicator_value("StochRSI_K")
            stoch_d = self._get_indicator_value("StochRSI_D")
            cci = self._get_indicator_value("CCI")
            wr = self._get_indicator_value("WR")
            mfi = self._get_indicator_value("MFI")

            if not pd.isna(rsi):
                if rsi < isd["rsi_oversold"]: signal_score += weights.get("rsi", 0) * 0.5
                elif rsi > isd["rsi_overbought"]: signal_score -= weights.get("rsi", 0) * 0.5

            if not pd.isna(stoch_k) and not pd.isna(stoch_d):
                if stoch_k > stoch_d and stoch_k < isd["stoch_rsi_oversold"]: signal_score += weights.get("stoch_rsi", 0) * 0.5
                elif stoch_k < stoch_d and stoch_k > isd["stoch_rsi_overbought"]: signal_score -= weights.get("stoch_rsi", 0) * 0.5

            if not pd.isna(cci):
                if cci < isd["cci_oversold"]: signal_score += weights.get("cci", 0) * 0.5
                elif cci > isd["cci_overbought"]: signal_score -= weights.get("cci", 0) * 0.5

            if not pd.isna(wr):
                if wr < isd["williams_r_oversold"]: signal_score += weights.get("wr", 0) * 0.5
                elif wr > isd["williams_r_overbought"]: signal_score -= weights.get("wr", 0) * 0.5

            if not pd.isna(mfi):
                if mfi < isd["mfi_oversold"]: signal_score += weights.get("mfi", 0) * 0.5
                elif mfi > isd["mfi_overbought"]: signal_score -= weights.get("mfi", 0) * 0.5

        if active_indicators.get("bollinger_bands", False):
            bb_upper = self._get_indicator_value("BB_Upper")
            bb_lower = self._get_indicator_value("BB_Lower")
            if not pd.isna(bb_upper) and not pd.isna(bb_lower):
                if current_close < bb_lower: signal_score += weights.get("bollinger_bands", 0) * 0.5
                elif current_close > bb_upper: signal_score -= weights.get("bollinger_bands", 0) * 0.5

        if active_indicators.get("vwap", False):
            vwap = self._get_indicator_value("VWAP")
            if not pd.isna(vwap):
                if current_close > vwap: signal_score += weights.get("vwap", 0) * 0.2
                elif current_close < vwap: signal_score -= weights.get("vwap", 0) * 0.2

                if len(self.df) > 1:
                    prev_close = Decimal(str(self.df["close"].iloc[-2]))
                    prev_vwap = Decimal(str(self.df["VWAP"].iloc[-2]))
                    if current_close > vwap and prev_close <= prev_vwap: signal_score += weights.get("vwap", 0) * 0.3
                    elif current_close < vwap and prev_close >= prev_vwap: signal_score -= weights.get("vwap", 0) * 0.3

        if active_indicators.get("psar", False):
            psar_val = self._get_indicator_value("PSAR_Val")
            psar_dir = self._get_indicator_value("PSAR_Dir")
            if not pd.isna(psar_val) and not pd.isna(psar_dir):
                if psar_dir == 1: signal_score += weights.get("psar", 0) * 0.5
                elif psar_dir == -1: signal_score -= weights.get("psar", 0) * 0.5

                if len(self.df) > 1:
                    prev_close = Decimal(str(self.df["close"].iloc[-2]))
                    prev_psar_val = Decimal(str(self.df["PSAR_Val"].iloc[-2]))
                    if current_close > psar_val and prev_close <= prev_psar_val: signal_score += weights.get("psar", 0) * 0.4
                    elif current_close < psar_val and prev_close >= prev_psar_val: signal_score -= weights.get("psar", 0) * 0.4

        if active_indicators.get("orderbook_imbalance", False) and orderbook_data:
            imbalance = self._check_orderbook(current_price, orderbook_data)
            signal_score += imbalance * weights.get("orderbook_imbalance", 0)

        if active_indicators.get("fibonacci_levels", False) and self.fib_levels:
            for level_name, level_price in self.fib_levels.items():
                if level_name not in ["0.0%", "100.0%"] and abs(current_price - level_price) / current_price < Decimal("0.001"):
                    if len(self.df) > 1:
                        prev_close = Decimal(str(self.df["close"].iloc[-2]))
                        if current_close > prev_close and current_close > level_price: signal_score += weights.get("fibonacci_levels", 0) * 0.1
                        elif current_close < prev_close and current_close < level_price: signal_score -= weights.get("fibonacci_levels", 0) * 0.1

        if active_indicators.get("ehlers_supertrend", False):
            st_fast_dir = self._get_indicator_value("ST_Fast_Dir")
            st_slow_dir = self._get_indicator_value("ST_Slow_Dir")
            prev_st_fast_dir = self.df["st_fast_dir"].iloc[-2] if "st_fast_dir" in self.df.columns and len(self.df) > 1 else np.nan
            weight = weights.get("ehlers_supertrend_alignment", 0.0)

            if not pd.isna(st_fast_dir) and not pd.isna(st_slow_dir) and not pd.isna(prev_st_fast_dir):
                if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1: signal_score += weight
                elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1: signal_score -= weight
                elif st_slow_dir == 1 and st_fast_dir == 1: signal_score += weight * 0.3
                elif st_slow_dir == -1 and st_fast_dir == -1: signal_score -= weight * 0.3

        if active_indicators.get("macd", False):
            macd_line = self._get_indicator_value("MACD_Line")
            signal_line = self._get_indicator_value("MACD_Signal")
            histogram = self._get_indicator_value("MACD_Hist")
            weight = weights.get("macd_alignment", 0.0)

            if not pd.isna(macd_line) and not pd.isna(signal_line) and not pd.isna(histogram):
                if len(self.df) > 1:
                    prev_macd_line = Decimal(str(self.df["MACD_Line"].iloc[-2]))
                    prev_signal_line = Decimal(str(self.df["MACD_Signal"].iloc[-2]))
                    if macd_line > signal_line and prev_macd_line <= prev_signal_line: signal_score += weight
                    elif macd_line < signal_line and prev_macd_line >= prev_signal_line: signal_score -= weight
                if len(self.df) > 1 and histogram > 0 and self.df["MACD_Hist"].iloc[-2] < 0: signal_score += weight * 0.2
                elif len(self.df) > 1 and histogram < 0 and self.df["MACD_Hist"].iloc[-2] > 0: signal_score -= weight * 0.2

        if active_indicators.get("adx", False):
            adx_val = self._get_indicator_value("ADX")
            plus_di = self._get_indicator_value("PlusDI")
            minus_di = self._get_indicator_value("MinusDI")
            weight = weights.get("adx_strength", 0.0)

            if not pd.isna(adx_val) and not pd.isna(plus_di) and not pd.isna(minus_di):
                if adx_val > ADX_STRONG_TREND_THRESHOLD:
                    if plus_di > minus_di: signal_score += weight
                    elif minus_di > plus_di: signal_score -= weight
                elif adx_val < ADX_WEAK_TREND_THRESHOLD: pass

        if active_indicators.get("ichimoku_cloud", False):
            tenkan_sen = self._get_indicator_value("Tenkan_Sen")
            kijun_sen = self._get_indicator_value("Kijun_Sen")
            senkou_span_a = self._get_indicator_value("Senkou_Span_A")
            senkou_span_b = self._get_indicator_value("Senkou_Span_B")
            chikou_span = self._get_indicator_value("Chikou_Span")
            weight = weights.get("ichimoku_confluence", 0.0)

            if not pd.isna(tenkan_sen) and not pd.isna(kijun_sen) and not pd.isna(senkou_span_a) and not pd.isna(senkou_span_b) and not pd.isna(chikou_span):
                if tenkan_sen > kijun_sen and self.df["Tenkan_Sen"].iloc[-2] <= self.df["Kijun_Sen"].iloc[-2]: signal_score += weight * 0.5
                elif tenkan_sen < kijun_sen and self.df["Tenkan_Sen"].iloc[-2] >= self.df["Kijun_Sen"].iloc[-2]: signal_score -= weight * 0.5

                if current_close > max(senkou_span_a, senkou_span_b) and self.df["close"].iloc[-2] <= max(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]): signal_score += weight * 0.7
                elif current_close < min(senkou_span_a, senkou_span_b) and self.df["close"].iloc[-2] >= min(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]): signal_score -= weight * 0.7

                if chikou_span > current_close and self.df["Chikou_Span"].iloc[-2] <= self.df["close"].iloc[-2]: signal_score += weight * 0.3
                elif chikou_span < current_close and self.df["Chikou_Span"].iloc[-2] >= self.df["close"].iloc[-2]: signal_score -= weight * 0.3

        if active_indicators.get("obv", False):
            obv_val = self._get_indicator_value("OBV")
            obv_ema = self._get_indicator_value("OBV_EMA")
            weight = weights.get("obv_momentum", 0.0)
            if not pd.isna(obv_val) and not pd.isna(obv_ema):
                if obv_val > obv_ema and self.df["OBV"].iloc[-2] <= self.df["OBV_EMA"].iloc[-2]: signal_score += weight * 0.5
                elif obv_val < obv_ema and self.df["OBV"].iloc[-2] >= self.df["OBV_EMA"].iloc[-2]: signal_score -= weight * 0.5
                if len(self.df) > 2:
                    if obv_val > self.df["OBV"].iloc[-2] and obv_val > self.df["OBV"].iloc[-3]: signal_score += weight * 0.2
                    elif obv_val < self.df["OBV"].iloc[-2] and obv_val < self.df["OBV"].iloc[-3]: signal_score -= weight * 0.2

        if active_indicators.get("cmf", False):
            cmf_val = self._get_indicator_value("CMF")
            weight = weights.get("cmf_flow", 0.0)
            if not pd.isna(cmf_val):
                if cmf_val > 0: signal_score += weight * 0.5
                elif cmf_val < 0: signal_score -= weight * 0.5
                if len(self.df) > 2:
                    if cmf_val > self.df["CMF"].iloc[-2] and cmf_val > self.df["CMF"].iloc[-3]: signal_score += weight * 0.3
                    elif cmf_val < self.df["CMF"].iloc[-2] and cmf_val < self.df["CMF"].iloc[-3]: signal_score -= weight * 0.3

        if self.config["mtf_analysis"]["enabled"] and mtf_trends:
            mtf_buy_score = sum(1 for trend in mtf_trends.values() if trend == "UP")
            mtf_sell_score = sum(-1 for trend in mtf_trends.values() if trend == "DOWN")
            if mtf_trends:
                normalized_mtf_score = (mtf_buy_score + mtf_sell_score) / len(mtf_trends)
                signal_score += weights.get("mtf_trend_confluence", 0.0) * normalized_mtf_score
                self.logger.debug(f"MTF Confluence: Score {normalized_mtf_score:.2f}")

        threshold = self.config["signal_score_threshold"]
        final_signal = "HOLD"
        if signal_score >= threshold: final_signal = "BUY"
        elif signal_score <= -threshold: final_signal = "SELL"

        self.logger.info(f"{NEON_YELLOW}Raw Technical Signal Score: {signal_score:.2f}, Final Technical Signal: {final_signal}{RESET}")
        return final_signal, signal_score


    # --- Remaining Indicator Implementations ---
    def calculate_true_range(self) -> pd.Series:
        """Calculate True Range (TR)."""
        if len(self.df) < MIN_DATA_POINTS_TR: return pd.Series(np.nan, index=self.df.index)
        high_low = self.df["high"] - self.df["low"]
        high_prev_close = (self.df["high"] - self.df["close"].shift()).abs()
        low_prev_close = (self.df["low"] - self.df["close"].shift()).abs()
        return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)

    def calculate_super_smoother(self, series: pd.Series, period: int) -> pd.Series:
        """Apply Ehlers SuperSmoother filter to reduce lag and noise."""
        if period <= 0 or len(series) < MIN_DATA_POINTS_SMOOTHER: return pd.Series(np.nan, index=series.index)
        series = pd.to_numeric(series, errors="coerce").dropna()
        if len(series) < MIN_DATA_POINTS_SMOOTHER: return pd.Series(np.nan, index=series.index)

        a1 = np.exp(-np.sqrt(2) * np.pi / period)
        b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / period)
        c1 = 1 - b1 + a1**2
        c2 = b1 - 2 * a1**2
        c3 = a1**2

        filt = pd.Series(0.0, index=series.index)
        if len(series) >= 1: filt.iloc = series.iloc
        if len(series) >= 2: filt.iloc = (series.iloc + series.iloc) / 2

        for i in range(2, len(series)):
            filt.iloc[i] = ((c1 / 2) * (series.iloc[i] + series.iloc[i - 1])) + (c2 * filt.iloc[i - 1]) - (c3 * filt.iloc[i - 2])
        return filt.reindex(self.df.index)

    def calculate_ehlers_supertrend(self, period: int, multiplier: float) -> Optional[pd.DataFrame]:
        """Calculate SuperTrend using Ehlers SuperSmoother for price and volatility."""
        if len(self.df) < period * 3: return None
        df_copy = self.df.copy()
        hl2 = (df_copy["high"] + df_copy["low"]) / 2
        smoothed_price = self.calculate_super_smoother(hl2, period)
        tr = self.calculate_true_range()
        smoothed_atr = self.calculate_super_smoother(tr, period)

        if smoothed_price is None or smoothed_atr is None: return None

        df_copy["smoothed_price"] = smoothed_price
        df_copy["smoothed_atr"] = smoothed_atr
        df_copy.dropna(subset=["smoothed_price", "smoothed_atr"], inplace=True)
        if df_copy.empty: return None

        upper_band = df_copy["smoothed_price"] + multiplier * df_copy["smoothed_atr"]
        lower_band = df_copy["smoothed_price"] - multiplier * df_copy["smoothed_atr"]

        direction = pd.Series(0, index=df_copy.index, dtype=int)
        supertrend = pd.Series(np.nan, index=df_copy.index)

        first_valid_idx = df_copy.index
        supertrend.loc[first_valid_idx] = lower_band.loc[first_valid_idx]

        for i in range(1, len(df_copy)):
            current_idx = df_copy.index[i]
            prev_idx = df_copy.index[i - 1]

            prev_direction = direction.loc[prev_idx]
            prev_supertrend = supertrend.loc[prev_idx]
            curr_close = df_copy["close"].loc[current_idx]

            if prev_direction == 1:
                supertrend.loc[current_idx] = max(lower_band.loc[current_idx], prev_supertrend)
                if curr_close < supertrend.loc[current_idx]:
                    direction.loc[current_idx] = -1
                    supertrend.loc[current_idx] = upper_band.loc[current_idx]
                else: direction.loc[current_idx] = 1
            elif prev_direction == -1:
                supertrend.loc[current_idx] = min(upper_band.loc[current_idx], prev_supertrend)
                if curr_close > supertrend.loc[current_idx]:
                    direction.loc[current_idx] = 1
                    supertrend.loc[current_idx] = lower_band.loc[current_idx]
                else: direction.loc[current_idx] = -1
            else:
                if curr_close > lower_band.loc[current_idx]:
                    direction.loc[current_idx] = 1
                    supertrend.loc[current_idx] = lower_band.loc[current_idx]
                else:
                    direction.loc[current_idx] = -1
                    supertrend.loc[current_idx] = upper_band.loc[current_idx]

        result = pd.DataFrame({"supertrend": supertrend, "direction": direction})
        return result.reindex(self.df.index)

    def calculate_macd(self, fast_period: int, slow_period: int, signal_period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Moving Average Convergence Divergence (MACD)."""
        if len(self.df) < slow_period + signal_period:
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        ema_fast = self.df["close"].ewm(span=fast_period, adjust=False).mean()
        ema_slow = self.df["close"].ewm(span=slow_period, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    def calculate_rsi(self, period: int) -> pd.Series:
        """Calculate Relative Strength Index (RSI)."""
        if len(self.df) <= period: return pd.Series(np.nan, index=self.df.index)
        delta = self.df["close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.ewm(span=period, adjust=False, min_periods=period).mean()
        avg_loss = loss.ewm(span=period, adjust=False, min_periods=period).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_stoch_rsi(self, period: int, k_period: int, d_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate Stochastic RSI."""
        if len(self.df) <= period: return pd.Series(np.nan), pd.Series(np.nan)
        rsi = self.calculate_rsi(period)

        lowest_rsi = rsi.rolling(window=period, min_periods=period).min()
        highest_rsi = rsi.rolling(window=period, min_periods=period).max()

        stoch_rsi_k_raw = ((rsi - lowest_rsi) / (highest_rsi - lowest_rsi))
        stoch_rsi_k_raw = stoch_rsi_k_raw.replace([np.inf, -np.inf], np.nan).fillna(0) * 100

        stoch_rsi_k = stoch_rsi_k_raw.rolling(window=k_period, min_periods=k_period).mean()
        stoch_rsi_d = stoch_rsi_k.rolling(window=d_period, min_periods=d_period).mean()

        return stoch_rsi_k, stoch_rsi_d

    def calculate_adx(self, period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Average Directional Index (ADX)."""
        if len(self.df) < period * 2: return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        tr = self.calculate_true_range()
        plus_dm = self.df["high"].diff().clip(lower=0)
        minus_dm = -self.df["low"].diff().clip(lower=0)

        plus_dm_final = plus_dm.copy()
        minus_dm_final = minus_dm.copy()
        condition_plus_wins = (plus_dm_final > minus_dm_final)
        condition_minus_wins = (minus_dm_final > plus_dm_final)

        plus_dm_final[condition_minus_wins] = 0
        minus_dm_final[condition_plus_wins] = 0

        atr = tr.ewm(span=period, adjust=False).mean()
        plus_di = (plus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100
        minus_di = (minus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100

        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)).replace([np.inf, -np.inf], np.nan).fillna(0) * 100
        adx = dx.ewm(span=period, adjust=False).mean()

        return adx, plus_di, minus_di

    def calculate_bollinger_bands(self, period: int, std_dev: float) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands."""
        if len(self.df) < period: return (pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan))
        middle_band = self.df["close"].rolling(window=period, min_periods=period).mean()
        std = self.df["close"].rolling(window=period, min_periods=period).std()
        upper_band = middle_band + (std * std_dev)
        lower_band = middle_band - (std * std_dev)
        return upper_band, middle_band, lower_band

    def calculate_vwap(self) -> pd.Series:
        """Calculate Volume Weighted Average Price (VWAP)."""
        if self.df.empty: return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        cumulative_tp_vol = (typical_price * self.df["volume"]).cumsum()
        cumulative_vol = self.df["volume"].cumsum()
        vwap = cumulative_tp_vol / cumulative_vol
        return vwap

    def calculate_cci(self, period: int) -> pd.Series:
        """Calculate Commodity Channel Index (CCI)."""
        if len(self.df) < period: return pd.Series(np.nan, index=self.df.index)
        tp = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        sma_tp = tp.rolling(window=period, min_periods=period).mean()
        mad = tp.rolling(window=period, min_periods=period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=False)
        cci = (tp - sma_tp) / (0.015 * mad)
        cci = cci.replace([np.inf, -np.inf], np.nan).fillna(0)
        return cci

    def calculate_williams_r(self, period: int) -> pd.Series:
        """Calculate Williams %R."""
        if len(self.df) < period: return pd.Series(np.nan, index=self.df.index)
        highest_high = self.df["high"].rolling(window=period, min_periods=period).max()
        lowest_low = self.df["low"].rolling(window=period, min_periods=period).min()
        wr = -100 * ((highest_high - self.df["close"]) / (highest_high - lowest_low))
        wr = wr.replace([np.inf, -np.inf], np.nan).fillna(-50)
        return wr

    def calculate_ichimoku_cloud(self, tenkan_period: int, kijun_period: int, senkou_span_b_period: int, chikou_span_offset: int) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
        """Calculate Ichimoku Cloud components."""
        if (len(self.df) < max(tenkan_period, kijun_period, senkou_span_b_period) + chikou_span_offset):
            return (pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan))

        tenkan_sen = (self.df["high"].rolling(window=tenkan_period).max() + self.df["low"].rolling(window=tenkan_period).min()) / 2
        kijun_sen = (self.df["high"].rolling(window=kijun_period).max() + self.df["low"].rolling(window=kijun_period).min()) / 2
        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun_period)
        senkou_span_b = ((self.df["high"].rolling(window=senkou_span_b_period).max() + self.df["low"].rolling(window=senkou_span_b_period).min()) / 2).shift(kijun_period)
        chikou_span = self.df["close"].shift(-chikou_span_offset)

        return tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span

    def calculate_mfi(self, period: int) -> pd.Series:
        """Calculate Money Flow Index (MFI)."""
        if len(self.df) <= period: return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        money_flow = typical_price * self.df["volume"]

        positive_flow = pd.Series(0.0, index=self.df.index)
        negative_flow = pd.Series(0.0, index=self.df.index)

        for i in range(1, len(self.df)):
            if typical_price.iloc[i] > typical_price.iloc[i - 1]: positive_flow.iloc[i] = money_flow.iloc[i]
            elif typical_price.iloc[i] < typical_price.iloc[i - 1]: negative_flow.iloc[i] = money_flow.iloc[i]

        positive_mf_sum = positive_flow.rolling(window=period, min_periods=period).sum()
        negative_mf_sum = negative_flow.rolling(window=period, min_periods=period).sum()

        mf_ratio = positive_mf_sum / negative_mf_sum
        mfi = 100 - (100 / (1 + mf_ratio))
        mfi = mfi.replace([np.inf, -np.inf], np.nan).fillna(50)
        return mfi

    def calculate_obv(self, ema_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate On-Balance Volume (OBV) and its EMA."""
        if len(self.df) < MIN_DATA_POINTS_OBV: return pd.Series(np.nan), pd.Series(np.nan)

        obv = pd.Series(0.0, index=self.df.index)
        for i in range(1, len(self.df)):
            if self.df["close"].iloc[i] > self.df["close"].iloc[i - 1]: obv.iloc[i] = obv.iloc[i - 1] + self.df["volume"].iloc[i]
            elif self.df["close"].iloc[i] < self.df["close"].iloc[i - 1]: obv.iloc[i] = obv.iloc[i - 1] - self.df["volume"].iloc[i]
            else: obv.iloc[i] = obv.iloc[i - 1]

        obv_ema = obv.ewm(span=ema_period, adjust=False).mean()
        return obv, obv_ema

    def calculate_cmf(self, period: int) -> pd.Series:
        """Calculate Chaikin Money Flow (CMF)."""
        if len(self.df) < period: return pd.Series(np.nan)

        mfm = ((self.df["close"] - self.df["low"]) - (self.df["high"] - self.df["close"])) / (self.df["high"] - self.df["low"])
        mfm = mfm.replace([np.inf, -np.inf], np.nan).fillna(0)

        mfv = mfm * self.df["volume"]
        cmf = (mfv.rolling(window=period).sum() / self.df["volume"].rolling(window=period).sum())
        cmf = cmf.replace([np.inf, -np.inf], np.nan).fillna(0)

        return cmf

    def calculate_psar(self, acceleration: float, max_acceleration: float) -> tuple[pd.Series, pd.Series]:
        """Calculate Parabolic SAR."""
        if len(self.df) < MIN_DATA_POINTS_PSAR: return pd.Series(np.nan), pd.Series(np.nan)

        psar = self.df["close"].copy()
        bull = pd.Series(True, index=self.df.index)
        af = acceleration
        ep = self.df["low"].iloc if self.df["close"].iloc < self.df["close"].iloc else self.df["high"].iloc

        for i in range(1, len(self.df)):
            if bull.iloc[i - 1]:
                psar.iloc[i] = psar.iloc[i - 1] + af * (ep - psar.iloc[i - 1])
            else:
                psar.iloc[i] = psar.iloc[i - 1] - af * (psar.iloc[i - 1] - ep)

            reverse = False
            if bull.iloc[i - 1] and self.df["low"].iloc[i] < psar.iloc[i]:
                bull.iloc[i] = False; reverse = True
            elif not bull.iloc[i - 1] and self.df["high"].iloc[i] > psar.iloc[i]:
                bull.iloc[i] = True; reverse = True
            else: bull.iloc[i] = bull.iloc[i - 1]

            if reverse:
                af = acceleration
                ep = self.df["high"].iloc[i] if bull.iloc[i] else self.df["low"].iloc[i]
            elif bull.iloc[i]:
                if self.df["high"].iloc[i] > ep: ep = self.df["high"].iloc[i]; af = min(af + acceleration, max_acceleration)
            elif self.df["low"].iloc[i] < ep: ep = self.df["low"].iloc[i]; af = min(af + acceleration, max_acceleration)

            if bull.iloc[i]: psar.iloc[i] = min(psar.iloc[i], self.df["low"].iloc[i], self.df["low"].iloc[i-1])
            else: psar.iloc[i] = max(psar.iloc[i], self.df["high"].iloc[i], self.df["high"].iloc[i-1])

            if bull.iloc[i] and psar.iloc[i] > self.df["low"].iloc[i]: psar.iloc[i] = self.df["low"].iloc[i]
            elif not bull.iloc[i] and psar.iloc[i] < self.df["high"].iloc[i]: psar.iloc[i] = self.df["high"].iloc[i]

        direction = pd.Series(0, index=self.df.index, dtype=int)
        direction[psar < self.df["close"]] = 1
        direction[psar > self.df["close"]] = -1

        return psar, direction

    def calculate_fibonacci_levels(self) -> None:
        """Calculate Fibonacci retracement levels based on a recent high-low swing."""
        window = self.config["indicator_settings"]["fibonacci_window"]
        if len(self.df) < window:
            self.logger.warning(f"{NEON_YELLOW}Not enough data for Fibonacci levels (need {window} bars).{RESET}")
            return

        recent_high = self.df["high"].iloc[-window:].max()
        recent_low = self.df["low"].iloc[-window:].min()
        diff = recent_high - recent_low

        self.fib_levels = {
            "0.0%": Decimal(str(recent_high)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "23.6%": Decimal(str(recent_high - 0.236 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "38.2%": Decimal(str(recent_high - 0.382 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "50.0%": Decimal(str(recent_high - 0.500 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "61.8%": Decimal(str(recent_high - 0.618 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "78.6%": Decimal(str(recent_high - 0.786 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "100.0%": Decimal(str(recent_low)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
        }
        self.logger.debug(f"Calculated Fibonacci levels: {self.fib_levels}")

    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        """Safely retrieve an indicator value."""
        return self.indicator_values.get(key, default)

    def _check_orderbook(self, current_price: Decimal, orderbook_data: dict) -> float:
        """Analyze orderbook imbalance."""
        bids = orderbook_data.get("b", [])
        asks = orderbook_data.get("a", [])

        bid_volume = sum(Decimal(b) for b in bids)
        ask_volume = sum(Decimal(a) for a in asks)

        if bid_volume + ask_volume == 0: return 0.0

        imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
        self.logger.debug(f"Orderbook Imbalance: {imbalance:.4f} (Bids: {bid_volume}, Asks: {ask_volume})")
        return float(imbalance)

    def _get_mtf_trend(self, higher_tf_df: pd.DataFrame, indicator_type: str) -> str:
        """Determine trend from higher timeframe using specified indicator."""
        if higher_tf_df.empty: return "UNKNOWN"

        last_close = higher_tf_df["close"].iloc[-1]
        period = self.config["mtf_analysis"]["trend_period"]

        if indicator_type == "sma":
            if len(higher_tf_df) < period: return "UNKNOWN"
            sma = higher_tf_df["close"].rolling(window=period, min_periods=period).mean().iloc[-1]
            if last_close > sma: return "UP"
            if last_close < sma: return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ema":
            if len(higher_tf_df) < period: return "UNKNOWN"
            ema = higher_tf_df["close"].ewm(span=period, adjust=False, min_periods=period).mean().iloc[-1]
            if last_close > ema: return "UP"
            if last_close < ema: return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ehlers_supertrend":
            temp_analyzer = TradingAnalyzer(higher_tf_df, self.config, self.logger, self.symbol)
            st_result = temp_analyzer.calculate_ehlers_supertrend(
                self.indicator_settings["ehlers_slow_period"],
                self.indicator_settings["ehlers_slow_multiplier"],
            )
            if st_result is not None and not st_result.empty:
                st_dir = st_result["direction"].iloc[-1]
                if st_dir == 1: return "UP"
                if st_dir == -1: return "DOWN"
            return "UNKNOWN"
        return "UNKNOWN"

    def generate_trading_signal(
        self, current_price: Decimal, orderbook_data: dict | None, mtf_trends: dict[str, str]
    ) -> tuple[str, float]:
        """Generate a signal using confluence of indicators, including Ehlers SuperTrend."""
        signal_score = 0.0
        active_indicators = self.config["indicators"]
        weights = self.weights

        if self.df.empty:
            self.logger.warning(f"{NEON_YELLOW}DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}")
            return "HOLD", 0.0

        current_close = Decimal(str(self.df["close"].iloc[-1]))
        prev_close = Decimal(str(self.df["close"].iloc[-2])) if len(self.df) > 1 else current_close
        isd = self.indicator_settings

        # --- Indicator Scoring ---
        if active_indicators.get("ema_alignment", False):
            ema_short = self._get_indicator_value("EMA_Short")
            ema_long = self._get_indicator_value("EMA_Long")
            if not pd.isna(ema_short) and not pd.isna(ema_long):
                if ema_short > ema_long: signal_score += weights.get("ema_alignment", 0)
                elif ema_short < ema_long: signal_score -= weights.get("ema_alignment", 0)

        if active_indicators.get("sma_trend_filter", False):
            sma_long = self._get_indicator_value("SMA_Long")
            if not pd.isna(sma_long):
                if current_close > sma_long: signal_score += weights.get("sma_trend_filter", 0)
                elif current_close < sma_long: signal_score -= weights.get("sma_trend_filter", 0)

        if active_indicators.get("momentum", False):
            rsi = self._get_indicator_value("RSI")
            stoch_k = self._get_indicator_value("StochRSI_K")
            stoch_d = self._get_indicator_value("StochRSI_D")
            cci = self._get_indicator_value("CCI")
            wr = self._get_indicator_value("WR")
            mfi = self._get_indicator_value("MFI")

            if not pd.isna(rsi):
                if rsi < isd["rsi_oversold"]: signal_score += weights.get("rsi", 0) * 0.5
                elif rsi > isd["rsi_overbought"]: signal_score -= weights.get("rsi", 0) * 0.5

            if not pd.isna(stoch_k) and not pd.isna(stoch_d):
                if stoch_k > stoch_d and stoch_k < isd["stoch_rsi_oversold"]: signal_score += weights.get("stoch_rsi", 0) * 0.5
                elif stoch_k < stoch_d and stoch_k > isd["stoch_rsi_overbought"]: signal_score -= weights.get("stoch_rsi", 0) * 0.5

            if not pd.isna(cci):
                if cci < isd["cci_oversold"]: signal_score += weights.get("cci", 0) * 0.5
                elif cci > isd["cci_overbought"]: signal_score -= weights.get("cci", 0) * 0.5

            if not pd.isna(wr):
                if wr < isd["williams_r_oversold"]: signal_score += weights.get("wr", 0) * 0.5
                elif wr > isd["williams_r_overbought"]: signal_score -= weights.get("wr", 0) * 0.5

            if not pd.isna(mfi):
                if mfi < isd["mfi_oversold"]: signal_score += weights.get("mfi", 0) * 0.5
                elif mfi > isd["mfi_overbought"]: signal_score -= weights.get("mfi", 0) * 0.5

        if active_indicators.get("bollinger_bands", False):
            bb_upper = self._get_indicator_value("BB_Upper")
            bb_lower = self._get_indicator_value("BB_Lower")
            if not pd.isna(bb_upper) and not pd.isna(bb_lower):
                if current_close < bb_lower: signal_score += weights.get("bollinger_bands", 0) * 0.5
                elif current_close > bb_upper: signal_score -= weights.get("bollinger_bands", 0) * 0.5

        if active_indicators.get("vwap", False):
            vwap = self._get_indicator_value("VWAP")
            if not pd.isna(vwap):
                if current_close > vwap: signal_score += weights.get("vwap", 0) * 0.2
                elif current_close < vwap: signal_score -= weights.get("vwap", 0) * 0.2

                if len(self.df) > 1:
                    prev_close = Decimal(str(self.df["close"].iloc[-2]))
                    prev_vwap = Decimal(str(self.df["VWAP"].iloc[-2]))
                    if current_close > vwap and prev_close <= prev_vwap: signal_score += weights.get("vwap", 0) * 0.3
                    elif current_close < vwap and prev_close >= prev_vwap: signal_score -= weights.get("vwap", 0) * 0.3

        if active_indicators.get("psar", False):
            psar_val = self._get_indicator_value("PSAR_Val")
            psar_dir = self._get_indicator_value("PSAR_Dir")
            if not pd.isna(psar_val) and not pd.isna(psar_dir):
                if psar_dir == 1: signal_score += weights.get("psar", 0) * 0.5
                elif psar_dir == -1: signal_score -= weights.get("psar", 0) * 0.5

                if len(self.df) > 1:
                    prev_close = Decimal(str(self.df["close"].iloc[-2]))
                    prev_psar_val = Decimal(str(self.df["PSAR_Val"].iloc[-2]))
                    if current_close > psar_val and prev_close <= prev_psar_val: signal_score += weights.get("psar", 0) * 0.4
                    elif current_close < psar_val and prev_close >= prev_psar_val: signal_score -= weights.get("psar", 0) * 0.4

        if active_indicators.get("orderbook_imbalance", False) and orderbook_data:
            imbalance = self._check_orderbook(current_price, orderbook_data)
            signal_score += imbalance * weights.get("orderbook_imbalance", 0)

        if active_indicators.get("fibonacci_levels", False) and self.fib_levels:
            for level_name, level_price in self.fib_levels.items():
                if level_name not in ["0.0%", "100.0%"] and abs(current_price - level_price) / current_price < Decimal("0.001"):
                    if len(self.df) > 1:
                        prev_close = Decimal(str(self.df["close"].iloc[-2]))
                        if current_close > prev_close and current_close > level_price: signal_score += weights.get("fibonacci_levels", 0) * 0.1
                        elif current_close < prev_close and current_close < level_price: signal_score -= weights.get("fibonacci_levels", 0) * 0.1

        if active_indicators.get("ehlers_supertrend", False):
            st_fast_dir = self._get_indicator_value("ST_Fast_Dir")
            st_slow_dir = self._get_indicator_value("ST_Slow_Dir")
            prev_st_fast_dir = self.df["st_fast_dir"].iloc[-2] if "st_fast_dir" in self.df.columns and len(self.df) > 1 else np.nan
            weight = weights.get("ehlers_supertrend_alignment", 0.0)

            if not pd.isna(st_fast_dir) and not pd.isna(st_slow_dir) and not pd.isna(prev_st_fast_dir):
                if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1: signal_score += weight
                elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1: signal_score -= weight
                elif st_slow_dir == 1 and st_fast_dir == 1: signal_score += weight * 0.3
                elif st_slow_dir == -1 and st_fast_dir == -1: signal_score -= weight * 0.3

        if active_indicators.get("macd", False):
            macd_line = self._get_indicator_value("MACD_Line")
            signal_line = self._get_indicator_value("MACD_Signal")
            histogram = self._get_indicator_value("MACD_Hist")
            weight = weights.get("macd_alignment", 0.0)

            if not pd.isna(macd_line) and not pd.isna(signal_line) and not pd.isna(histogram):
                if len(self.df) > 1:
                    prev_macd_line = Decimal(str(self.df["MACD_Line"].iloc[-2]))
                    prev_signal_line = Decimal(str(self.df["MACD_Signal"].iloc[-2]))
                    if macd_line > signal_line and prev_macd_line <= prev_signal_line: signal_score += weight
                    elif macd_line < signal_line and prev_macd_line >= prev_signal_line: signal_score -= weight
                if len(self.df) > 1 and histogram > 0 and self.df["MACD_Hist"].iloc[-2] < 0: signal_score += weight * 0.2
                elif len(self.df) > 1 and histogram < 0 and self.df["MACD_Hist"].iloc[-2] > 0: signal_score -= weight * 0.2

        if active_indicators.get("adx", False):
            adx_val = self._get_indicator_value("ADX")
            plus_di = self._get_indicator_value("PlusDI")
            minus_di = self._get_indicator_value("MinusDI")
            weight = weights.get("adx_strength", 0.0)

            if not pd.isna(adx_val) and not pd.isna(plus_di) and not pd.isna(minus_di):
                if adx_val > ADX_STRONG_TREND_THRESHOLD:
                    if plus_di > minus_di: signal_score += weight
                    elif minus_di > plus_di: signal_score -= weight
                elif adx_val < ADX_WEAK_TREND_THRESHOLD: pass

        if active_indicators.get("ichimoku_cloud", False):
            tenkan_sen = self._get_indicator_value("Tenkan_Sen")
            kijun_sen = self._get_indicator_value("Kijun_Sen")
            senkou_span_a = self._get_indicator_value("Senkou_Span_A")
            senkou_span_b = self._get_indicator_value("Senkou_Span_B")
            chikou_span = self._get_indicator_value("Chikou_Span")
            weight = weights.get("ichimoku_confluence", 0.0)

            if not pd.isna(tenkan_sen) and not pd.isna(kijun_sen) and not pd.isna(senkou_span_a) and not pd.isna(senkou_span_b) and not pd.isna(chikou_span):
                if tenkan_sen > kijun_sen and self.df["Tenkan_Sen"].iloc[-2] <= self.df["Kijun_Sen"].iloc[-2]: signal_score += weight * 0.5
                elif tenkan_sen < kijun_sen and self.df["Tenkan_Sen"].iloc[-2] >= self.df["Kijun_Sen"].iloc[-2]: signal_score -= weight * 0.5

                if current_close > max(senkou_span_a, senkou_span_b) and self.df["close"].iloc[-2] <= max(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]): signal_score += weight * 0.7
                elif current_close < min(senkou_span_a, senkou_span_b) and self.df["close"].iloc[-2] >= min(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]): signal_score -= weight * 0.7

                if chikou_span > current_close and self.df["Chikou_Span"].iloc[-2] <= self.df["close"].iloc[-2]: signal_score += weight * 0.3
                elif chikou_span < current_close and self.df["Chikou_Span"].iloc[-2] >= self.df["close"].iloc[-2]: signal_score -= weight * 0.3

        if active_indicators.get("obv", False):
            obv_val = self._get_indicator_value("OBV")
            obv_ema = self._get_indicator_value("OBV_EMA")
            weight = weights.get("obv_momentum", 0.0)
            if not pd.isna(obv_val) and not pd.isna(obv_ema):
                if obv_val > obv_ema and self.df["OBV"].iloc[-2] <= self.df["OBV_EMA"].iloc[-2]: signal_score += weight * 0.5
                elif obv_val < obv_ema and self.df["OBV"].iloc[-2] >= self.df["OBV_EMA"].iloc[-2]: signal_score -= weight * 0.5
                if len(self.df) > 2:
                    if obv_val > self.df["OBV"].iloc[-2] and obv_val > self.df["OBV"].iloc[-3]: signal_score += weight * 0.2
                    elif obv_val < self.df["OBV"].iloc[-2] and obv_val < self.df["OBV"].iloc[-3]: signal_score -= weight * 0.2

        if active_indicators.get("cmf", False):
            cmf_val = self._get_indicator_value("CMF")
            weight = weights.get("cmf_flow", 0.0)
            if not pd.isna(cmf_val):
                if cmf_val > 0: signal_score += weight * 0.5
                elif cmf_val < 0: signal_score -= weight * 0.5
                if len(self.df) > 2:
                    if cmf_val > self.df["CMF"].iloc[-2] and cmf_val > self.df["CMF"].iloc[-3]: signal_score += weight * 0.3
                    elif cmf_val < self.df["CMF"].iloc[-2] and cmf_val < self.df["CMF"].iloc[-3]: signal_score -= weight * 0.3

        if self.config["mtf_analysis"]["enabled"] and mtf_trends:
            mtf_buy_score = sum(1 for trend in mtf_trends.values() if trend == "UP")
            mtf_sell_score = sum(-1 for trend in mtf_trends.values() if trend == "DOWN")
            if mtf_trends:
                normalized_mtf_score = (mtf_buy_score + mtf_sell_score) / len(mtf_trends)
                signal_score += weights.get("mtf_trend_confluence", 0.0) * normalized_mtf_score
                self.logger.debug(f"MTF Confluence: Score {normalized_mtf_score:.2f}")

        threshold = self.config["signal_score_threshold"]
        final_signal = "HOLD"
        if signal_score >= threshold: final_signal = "BUY"
        elif signal_score <= -threshold: final_signal = "SELL"

        self.logger.info(f"{NEON_YELLOW}Raw Technical Signal Score: {signal_score:.2f}, Final Technical Signal: {final_signal}{RESET}")
        return final_signal, signal_score


    # --- Remaining Indicator Implementations ---
    def calculate_true_range(self) -> pd.Series:
        """Calculate True Range (TR)."""
        if len(self.df) < MIN_DATA_POINTS_TR: return pd.Series(np.nan, index=self.df.index)
        high_low = self.df["high"] - self.df["low"]
        high_prev_close = (self.df["high"] - self.df["close"].shift()).abs()
        low_prev_close = (self.df["low"] - self.df["close"].shift()).abs()
        return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)

    def calculate_super_smoother(self, series: pd.Series, period: int) -> pd.Series:
        """Apply Ehlers SuperSmoother filter to reduce lag and noise."""
        if period <= 0 or len(series) < MIN_DATA_POINTS_SMOOTHER: return pd.Series(np.nan, index=series.index)
        series = pd.to_numeric(series, errors="coerce").dropna()
        if len(series) < MIN_DATA_POINTS_SMOOTHER: return pd.Series(np.nan, index=series.index)

        a1 = np.exp(-np.sqrt(2) * np.pi / period)
        b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / period)
        c1 = 1 - b1 + a1**2
        c2 = b1 - 2 * a1**2
        c3 = a1**2

        filt = pd.Series(0.0, index=series.index)
        if len(series) >= 1: filt.iloc = series.iloc
        if len(series) >= 2: filt.iloc = (series.iloc + series.iloc) / 2

        for i in range(2, len(series)):
            filt.iloc[i] = ((c1 / 2) * (series.iloc[i] + series.iloc[i - 1])) + (c2 * filt.iloc[i - 1]) - (c3 * filt.iloc[i - 2])
        return filt.reindex(self.df.index)

    def calculate_ehlers_supertrend(self, period: int, multiplier: float) -> Optional[pd.DataFrame]:
        """Calculate SuperTrend using Ehlers SuperSmoother for price and volatility."""
        if len(self.df) < period * 3: return None
        df_copy = self.df.copy()
        hl2 = (df_copy["high"] + df_copy["low"]) / 2
        smoothed_price = self.calculate_super_smoother(hl2, period)
        tr = self.calculate_true_range()
        smoothed_atr = self.calculate_super_smoother(tr, period)

        if smoothed_price is None or smoothed_atr is None: return None

        df_copy["smoothed_price"] = smoothed_price
        df_copy["smoothed_atr"] = smoothed_atr
        df_copy.dropna(subset=["smoothed_price", "smoothed_atr"], inplace=True)
        if df_copy.empty: return None

        upper_band = df_copy["smoothed_price"] + multiplier * df_copy["smoothed_atr"]
        lower_band = df_copy["smoothed_price"] - multiplier * df_copy["smoothed_atr"]

        direction = pd.Series(0, index=df_copy.index, dtype=int)
        supertrend = pd.Series(np.nan, index=df_copy.index)

        first_valid_idx = df_copy.index
        supertrend.loc[first_valid_idx] = lower_band.loc[first_valid_idx]

        for i in range(1, len(df_copy)):
            current_idx = df_copy.index[i]
            prev_idx = df_copy.index[i - 1]

            prev_direction = direction.loc[prev_idx]
            prev_supertrend = supertrend.loc[prev_idx]
            curr_close = df_copy["close"].loc[current_idx]

            if prev_direction == 1:
                supertrend.loc[current_idx] = max(lower_band.loc[current_idx], prev_supertrend)
                if curr_close < supertrend.loc[current_idx]:
                    direction.loc[current_idx] = -1
                    supertrend.loc[current_idx] = upper_band.loc[current_idx]
                else: direction.loc[current_idx] = 1
            elif prev_direction == -1:
                supertrend.loc[current_idx] = min(upper_band.loc[current_idx], prev_supertrend)
                if curr_close > supertrend.loc[current_idx]:
                    direction.loc[current_idx] = 1
                    supertrend.loc[current_idx] = lower_band.loc[current_idx]
                else: direction.loc[current_idx] = -1
            else:
                if curr_close > lower_band.loc[current_idx]:
                    direction.loc[current_idx] = 1
                    supertrend.loc[current_idx] = lower_band.loc[current_idx]
                else:
                    direction.loc[current_idx] = -1
                    supertrend.loc[current_idx] = upper_band.loc[current_idx]

        result = pd.DataFrame({"supertrend": supertrend, "direction": direction})
        return result.reindex(self.df.index)

    def calculate_macd(self, fast_period: int, slow_period: int, signal_period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Moving Average Convergence Divergence (MACD)."""
        if len(self.df) < slow_period + signal_period:
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        ema_fast = self.df["close"].ewm(span=fast_period, adjust=False).mean()
        ema_slow = self.df["close"].ewm(span=slow_period, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    def calculate_rsi(self, period: int) -> pd.Series:
        """Calculate Relative Strength Index (RSI)."""
        if len(self.df) <= period: return pd.Series(np.nan, index=self.df.index)
        delta = self.df["close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.ewm(span=period, adjust=False, min_periods=period).mean()
        avg_loss = loss.ewm(span=period, adjust=False, min_periods=period).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_stoch_rsi(self, period: int, k_period: int, d_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate Stochastic RSI."""
        if len(self.df) <= period: return pd.Series(np.nan), pd.Series(np.nan)
        rsi = self.calculate_rsi(period)

        lowest_rsi = rsi.rolling(window=period, min_periods=period).min()
        highest_rsi = rsi.rolling(window=period, min_periods=period).max()

        stoch_rsi_k_raw = ((rsi - lowest_rsi) / (highest_rsi - lowest_rsi))
        stoch_rsi_k_raw = stoch_rsi_k_raw.replace([np.inf, -np.inf], np.nan).fillna(0) * 100

        stoch_rsi_k = stoch_rsi_k_raw.rolling(window=k_period, min_periods=k_period).mean()
        stoch_rsi_d = stoch_rsi_k.rolling(window=d_period, min_periods=d_period).mean()

        return stoch_rsi_k, stoch_rsi_d

    def calculate_adx(self, period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Average Directional Index (ADX)."""
        if len(self.df) < period * 2: return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        tr = self.calculate_true_range()
        plus_dm = self.df["high"].diff().clip(lower=0)
        minus_dm = -self.df["low"].diff().clip(lower=0)

        plus_dm_final = plus_dm.copy()
        minus_dm_final = minus_dm.copy()
        condition_plus_wins = (plus_dm_final > minus_dm_final)
        condition_minus_wins = (minus_dm_final > plus_dm_final)

        plus_dm_final[condition_minus_wins] = 0
        minus_dm_final[condition_plus_wins] = 0

        atr = tr.ewm(span=period, adjust=False).mean()
        plus_di = (plus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100
        minus_di = (minus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100

        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)).replace([np.inf, -np.inf], np.nan).fillna(0) * 100
        adx = dx.ewm(span=period, adjust=False).mean()

        return adx, plus_di, minus_di

    def calculate_bollinger_bands(self, period: int, std_dev: float) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands."""
        if len(self.df) < period: return (pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan))
        middle_band = self.df["close"].rolling(window=period, min_periods=period).mean()
        std = self.df["close"].rolling(window=period, min_periods=period).std()
        upper_band = middle_band + (std * std_dev)
        lower_band = middle_band - (std * std_dev)
        return upper_band, middle_band, lower_band

    def calculate_vwap(self) -> pd.Series:
        """Calculate Volume Weighted Average Price (VWAP)."""
        if self.df.empty: return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        cumulative_tp_vol = (typical_price * self.df["volume"]).cumsum()
        cumulative_vol = self.df["volume"].cumsum()
        vwap = cumulative_tp_vol / cumulative_vol
        return vwap

    def calculate_cci(self, period: int) -> pd.Series:
        """Calculate Commodity Channel Index (CCI)."""
        if len(self.df) < period: return pd.Series(np.nan, index=self.df.index)
        tp = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        sma_tp = tp.rolling(window=period, min_periods=period).mean()
        mad = tp.rolling(window=period, min_periods=period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=False)
        cci = (tp - sma_tp) / (0.015 * mad)
        cci = cci.replace([np.inf, -np.inf], np.nan).fillna(0)
        return cci

    def calculate_williams_r(self, period: int) -> pd.Series:
        """Calculate Williams %R."""
        if len(self.df) < period: return pd.Series(np.nan, index=self.df.index)
        highest_high = self.df["high"].rolling(window=period, min_periods=period).max()
        lowest_low = self.df["low"].rolling(window=period, min_periods=period).min()
        wr = -100 * ((highest_high - self.df["close"]) / (highest_high - lowest_low))
        wr = wr.replace([np.inf, -np.inf], np.nan).fillna(-50)
        return wr

    def calculate_ichimoku_cloud(self, tenkan_period: int, kijun_period: int, senkou_span_b_period: int, chikou_span_offset: int) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
        """Calculate Ichimoku Cloud components."""
        if (len(self.df) < max(tenkan_period, kijun_period, senkou_span_b_period) + chikou_span_offset):
            return (pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan))

        tenkan_sen = (self.df["high"].rolling(window=tenkan_period).max() + self.df["low"].rolling(window=tenkan_period).min()) / 2
        kijun_sen = (self.df["high"].rolling(window=kijun_period).max() + self.df["low"].rolling(window=kijun_period).min()) / 2
        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun_period)
        senkou_span_b = ((self.df["high"].rolling(window=senkou_span_b_period).max() + self.df["low"].rolling(window=senkou_span_b_period).min()) / 2).shift(kijun_period)
        chikou_span = self.df["close"].shift(-chikou_span_offset)

        return tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span

    def calculate_mfi(self, period: int) -> pd.Series:
        """Calculate Money Flow Index (MFI)."""
        if len(self.df) <= period: return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        money_flow = typical_price * self.df["volume"]

        positive_flow = pd.Series(0.0, index=self.df.index)
        negative_flow = pd.Series(0.0, index=self.df.index)

        for i in range(1, len(self.df)):
            if typical_price.iloc[i] > typical_price.iloc[i - 1]: positive_flow.iloc[i] = money_flow.iloc[i]
            elif typical_price.iloc[i] < typical_price.iloc[i - 1]: negative_flow.iloc[i] = money_flow.iloc[i]

        positive_mf_sum = positive_flow.rolling(window=period, min_periods=period).sum()
        negative_mf_sum = negative_flow.rolling(window=period, min_periods=period).sum()

        mf_ratio = positive_mf_sum / negative_mf_sum
        mfi = 100 - (100 / (1 + mf_ratio))
        mfi = mfi.replace([np.inf, -np.inf], np.nan).fillna(50)
        return mfi

    def calculate_obv(self, ema_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate On-Balance Volume (OBV) and its EMA."""
        if len(self.df) < MIN_DATA_POINTS_OBV: return pd.Series(np.nan), pd.Series(np.nan)

        obv = pd.Series(0.0, index=self.df.index)
        for i in range(1, len(self.df)):
            if self.df["close"].iloc[i] > self.df["close"].iloc[i - 1]: obv.iloc[i] = obv.iloc[i - 1] + self.df["volume"].iloc[i]
            elif self.df["close"].iloc[i] < self.df["close"].iloc[i - 1]: obv.iloc[i] = obv.iloc[i - 1] - self.df["volume"].iloc[i]
            else: obv.iloc[i] = obv.iloc[i - 1]

        obv_ema = obv.ewm(span=ema_period, adjust=False).mean()
        return obv, obv_ema

    def calculate_cmf(self, period: int) -> pd.Series:
        """Calculate Chaikin Money Flow (CMF)."""
        if len(self.df) < period: return pd.Series(np.nan)

        mfm = ((self.df["close"] - self.df["low"]) - (self.df["high"] - self.df["close"])) / (self.df["high"] - self.df["low"])
        mfm = mfm.replace([np.inf, -np.inf], np.nan).fillna(0)

        mfv = mfm * self.df["volume"]
        cmf = (mfv.rolling(window=period).sum() / self.df["volume"].rolling(window=period).sum())
        cmf = cmf.replace([np.inf, -np.inf], np.nan).fillna(0)

        return cmf

    def calculate_psar(self, acceleration: float, max_acceleration: float) -> tuple[pd.Series, pd.Series]:
        """Calculate Parabolic SAR."""
        if len(self.df) < MIN_DATA_POINTS_PSAR: return pd.Series(np.nan), pd.Series(np.nan)

        psar = self.df["close"].copy()
        bull = pd.Series(True, index=self.df.index)
        af = acceleration
        ep = self.df["low"].iloc if self.df["close"].iloc < self.df["close"].iloc else self.df["high"].iloc

        for i in range(1, len(self.df)):
            if bull.iloc[i - 1]:
                psar.iloc[i] = psar.iloc[i - 1] + af * (ep - psar.iloc[i - 1])
            else:
                psar.iloc[i] = psar.iloc[i - 1] - af * (psar.iloc[i - 1] - ep)

            reverse = False
            if bull.iloc[i - 1] and self.df["low"].iloc[i] < psar.iloc[i]:
                bull.iloc[i] = False; reverse = True
            elif not bull.iloc[i - 1] and self.df["high"].iloc[i] > psar.iloc[i]:
                bull.iloc[i] = True; reverse = True
            else: bull.iloc[i] = bull.iloc[i - 1]

            if reverse:
                af = acceleration
                ep = self.df["high"].iloc[i] if bull.iloc[i] else self.df["low"].iloc[i]
            elif bull.iloc[i]:
                if self.df["high"].iloc[i] > ep: ep = self.df["high"].iloc[i]; af = min(af + acceleration, max_acceleration)
            elif self.df["low"].iloc[i] < ep: ep = self.df["low"].iloc[i]; af = min(af + acceleration, max_acceleration)

            if bull.iloc[i]: psar.iloc[i] = min(psar.iloc[i], self.df["low"].iloc[i], self.df["low"].iloc[i-1])
            else: psar.iloc[i] = max(psar.iloc[i], self.df["high"].iloc[i], self.df["high"].iloc[i-1])

            if bull.iloc[i] and psar.iloc[i] > self.df["low"].iloc[i]: psar.iloc[i] = self.df["low"].iloc[i]
            elif not bull.iloc[i] and psar.iloc[i] < self.df["high"].iloc[i]: psar.iloc[i] = self.df["high"].iloc[i]

        direction = pd.Series(0, index=self.df.index, dtype=int)
        direction[psar < self.df["close"]] = 1
        direction[psar > self.df["close"]] = -1

        return psar, direction

    def calculate_fibonacci_levels(self) -> None:
        """Calculate Fibonacci retracement levels based on a recent high-low swing."""
        window = self.config["indicator_settings"]["fibonacci_window"]
        if len(self.df) < window:
            self.logger.warning(f"{NEON_YELLOW}Not enough data for Fibonacci levels (need {window} bars).{RESET}")
            return

        recent_high = self.df["high"].iloc[-window:].max()
        recent_low = self.df["low"].iloc[-window:].min()
        diff = recent_high - recent_low

        self.fib_levels = {
            "0.0%": Decimal(str(recent_high)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "23.6%": Decimal(str(recent_high - 0.236 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "38.2%": Decimal(str(recent_high - 0.382 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "50.0%": Decimal(str(recent_high - 0.500 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "61.8%": Decimal(str(recent_high - 0.618 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "78.6%": Decimal(str(recent_high - 0.786 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "100.0%": Decimal(str(recent_low)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
        }
        self.logger.debug(f"Calculated Fibonacci levels: {self.fib_levels}")

    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        """Safely retrieve an indicator value."""
        return self.indicator_values.get(key, default)

    def _check_orderbook(self, current_price: Decimal, orderbook_data: dict) -> float:
        """Analyze orderbook imbalance."""
        bids = orderbook_data.get("b", [])
        asks = orderbook_data.get("a", [])

        bid_volume = sum(Decimal(b) for b in bids)
        ask_volume = sum(Decimal(a) for a in asks)

        if bid_volume + ask_volume == 0: return 0.0

        imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
        self.logger.debug(f"Orderbook Imbalance: {imbalance:.4f} (Bids: {bid_volume}, Asks: {ask_volume})")
        return float(imbalance)

    def _get_mtf_trend(self, higher_tf_df: pd.DataFrame, indicator_type: str) -> str:
        """Determine trend from higher timeframe using specified indicator."""
        if higher_tf_df.empty: return "UNKNOWN"

        last_close = higher_tf_df["close"].iloc[-1]
        period = self.config["mtf_analysis"]["trend_period"]

        if indicator_type == "sma":
            if len(higher_tf_df) < period: return "UNKNOWN"
            sma = higher_tf_df["close"].rolling(window=period, min_periods=period).mean().iloc[-1]
            if last_close > sma: return "UP"
            if last_close < sma: return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ema":
            if len(higher_tf_df) < period: return "UNKNOWN"
            ema = higher_tf_df["close"].ewm(span=period, adjust=False, min_periods=period).mean().iloc[-1]
            if last_close > ema: return "UP"
            if last_close < ema: return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ehlers_supertrend":
            temp_analyzer = TradingAnalyzer(higher_tf_df, self.config, self.logger, self.symbol)
            st_result = temp_analyzer.calculate_ehlers_supertrend(
                self.indicator_settings["ehlers_slow_period"],
                self.indicator_settings["ehlers_slow_multiplier"],
            )
            if st_result is not None and not st_result.empty:
                st_dir = st_result["direction"].iloc[-1]
                if st_dir == 1: return "UP"
                if st_dir == -1: return "DOWN"
            return "UNKNOWN"
        return "UNKNOWN"

    def generate_trading_signal(
        self, current_price: Decimal, orderbook_data: dict | None, mtf_trends: dict[str, str]
    ) -> tuple[str, float]:
        """Generate a signal using confluence of indicators, including Ehlers SuperTrend."""
        signal_score = 0.0
        active_indicators = self.config["indicators"]
        weights = self.weights

        if self.df.empty:
            self.logger.warning(f"{NEON_YELLOW}DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}")
            return "HOLD", 0.0

        current_close = Decimal(str(self.df["close"].iloc[-1]))
        prev_close = Decimal(str(self.df["close"].iloc[-2])) if len(self.df) > 1 else current_close
        isd = self.indicator_settings

        # --- Indicator Scoring ---
        if active_indicators.get("ema_alignment", False):
            ema_short = self._get_indicator_value("EMA_Short")
            ema_long = self._get_indicator_value("EMA_Long")
            if not pd.isna(ema_short) and not pd.isna(ema_long):
                if ema_short > ema_long: signal_score += weights.get("ema_alignment", 0)
                elif ema_short < ema_long: signal_score -= weights.get("ema_alignment", 0)

        if active_indicators.get("sma_trend_filter", False):
            sma_long = self._get_indicator_value("SMA_Long")
            if not pd.isna(sma_long):
                if current_close > sma_long: signal_score += weights.get("sma_trend_filter", 0)
                elif current_close < sma_long: signal_score -= weights.get("sma_trend_filter", 0)

        if active_indicators.get("momentum", False):
            rsi = self._get_indicator_value("RSI")
            stoch_k = self._get_indicator_value("StochRSI_K")
            stoch_d = self._get_indicator_value("StochRSI_D")
            cci = self._get_indicator_value("CCI")
            wr = self._get_indicator_value("WR")
            mfi = self._get_indicator_value("MFI")

            if not pd.isna(rsi):
                if rsi < isd["rsi_oversold"]: signal_score += weights.get("rsi", 0) * 0.5
                elif rsi > isd["rsi_overbought"]: signal_score -= weights.get("rsi", 0) * 0.5

            if not pd.isna(stoch_k) and not pd.isna(stoch_d):
                if stoch_k > stoch_d and stoch_k < isd["stoch_rsi_oversold"]: signal_score += weights.get("stoch_rsi", 0) * 0.5
                elif stoch_k < stoch_d and stoch_k > isd["stoch_rsi_overbought"]: signal_score -= weights.get("stoch_rsi", 0) * 0.5

            if not pd.isna(cci):
                if cci < isd["cci_oversold"]: signal_score += weights.get("cci", 0) * 0.5
                elif cci > isd["cci_overbought"]: signal_score -= weights.get("cci", 0) * 0.5

            if not pd.isna(wr):
                if wr < isd["williams_r_oversold"]: signal_score += weights.get("wr", 0) * 0.5
                elif wr > isd["williams_r_overbought"]: signal_score -= weights.get("wr", 0) * 0.5

            if not pd.isna(mfi):
                if mfi < isd["mfi_oversold"]: signal_score += weights.get("mfi", 0) * 0.5
                elif mfi > isd["mfi_overbought"]: signal_score -= weights.get("mfi", 0) * 0.5

        if active_indicators.get("bollinger_bands", False):
            bb_upper = self._get_indicator_value("BB_Upper")
            bb_lower = self._get_indicator_value("BB_Lower")
            if not pd.isna(bb_upper) and not pd.isna(bb_lower):
                if current_close < bb_lower: signal_score += weights.get("bollinger_bands", 0) * 0.5
                elif current_close > bb_upper: signal_score -= weights.get("bollinger_bands", 0) * 0.5

        if active_indicators.get("vwap", False):
            vwap = self._get_indicator_value("VWAP")
            if not pd.isna(vwap):
                if current_close > vwap: signal_score += weights.get("vwap", 0) * 0.2
                elif current_close < vwap: signal_score -= weights.get("vwap", 0) * 0.2

                if len(self.df) > 1:
                    prev_close = Decimal(str(self.df["close"].iloc[-2]))
                    prev_vwap = Decimal(str(self.df["VWAP"].iloc[-2]))
                    if current_close > vwap and prev_close <= prev_vwap: signal_score += weights.get("vwap", 0) * 0.3
                    elif current_close < vwap and prev_close >= prev_vwap: signal_score -= weights.get("vwap", 0) * 0.3

        if active_indicators.get("psar", False):
            psar_val = self._get_indicator_value("PSAR_Val")
            psar_dir = self._get_indicator_value("PSAR_Dir")
            if not pd.isna(psar_val) and not pd.isna(psar_dir):
                if psar_dir == 1: signal_score += weights.get("psar", 0) * 0.5
                elif psar_dir == -1: signal_score -= weights.get("psar", 0) * 0.5

                if len(self.df) > 1:
                    prev_close = Decimal(str(self.df["close"].iloc[-2]))
                    prev_psar_val = Decimal(str(self.df["PSAR_Val"].iloc[-2]))
                    if current_close > psar_val and prev_close <= prev_psar_val: signal_score += weights.get("psar", 0) * 0.4
                    elif current_close < psar_val and prev_close >= prev_psar_val: signal_score -= weights.get("psar", 0) * 0.4

        if active_indicators.get("orderbook_imbalance", False) and orderbook_data:
            imbalance = self._check_orderbook(current_price, orderbook_data)
            signal_score += imbalance * weights.get("orderbook_imbalance", 0)

        if active_indicators.get("fibonacci_levels", False) and self.fib_levels:
            for level_name, level_price in self.fib_levels.items():
                if level_name not in ["0.0%", "100.0%"] and abs(current_price - level_price) / current_price < Decimal("0.001"):
                    if len(self.df) > 1:
                        prev_close = Decimal(str(self.df["close"].iloc[-2]))
                        if current_close > prev_close and current_close > level_price: signal_score += weights.get("fibonacci_levels", 0) * 0.1
                        elif current_close < prev_close and current_close < level_price: signal_score -= weights.get("fibonacci_levels", 0) * 0.1

        if active_indicators.get("ehlers_supertrend", False):
            st_fast_dir = self._get_indicator_value("ST_Fast_Dir")
            st_slow_dir = self._get_indicator_value("ST_Slow_Dir")
            prev_st_fast_dir = self.df["st_fast_dir"].iloc[-2] if "st_fast_dir" in self.df.columns and len(self.df) > 1 else np.nan
            weight = weights.get("ehlers_supertrend_alignment", 0.0)

            if not pd.isna(st_fast_dir) and not pd.isna(st_slow_dir) and not pd.isna(prev_st_fast_dir):
                if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1: signal_score += weight
                elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1: signal_score -= weight
                elif st_slow_dir == 1 and st_fast_dir == 1: signal_score += weight * 0.3
                elif st_slow_dir == -1 and st_fast_dir == -1: signal_score -= weight * 0.3

        if active_indicators.get("macd", False):
            macd_line = self._get_indicator_value("MACD_Line")
            signal_line = self._get_indicator_value("MACD_Signal")
            histogram = self._get_indicator_value("MACD_Hist")
            weight = weights.get("macd_alignment", 0.0)

            if not pd.isna(macd_line) and not pd.isna(signal_line) and not pd.isna(histogram):
                if len(self.df) > 1:
                    prev_macd_line = Decimal(str(self.df["MACD_Line"].iloc[-2]))
                    prev_signal_line = Decimal(str(self.df["MACD_Signal"].iloc[-2]))
                    if macd_line > signal_line and prev_macd_line <= prev_signal_line: signal_score += weight
                    elif macd_line < signal_line and prev_macd_line >= prev_signal_line: signal_score -= weight
                if len(self.df) > 1 and histogram > 0 and self.df["MACD_Hist"].iloc[-2] < 0: signal_score += weight * 0.2
                elif len(self.df) > 1 and histogram < 0 and self.df["MACD_Hist"].iloc[-2] > 0: signal_score -= weight * 0.2

        if active_indicators.get("adx", False):
            adx_val = self._get_indicator_value("ADX")
            plus_di = self._get_indicator_value("PlusDI")
            minus_di = self._get_indicator_value("MinusDI")
            weight = weights.get("adx_strength", 0.0)

            if not pd.isna(adx_val) and not pd.isna(plus_di) and not pd.isna(minus_di):
                if adx_val > ADX_STRONG_TREND_THRESHOLD:
                    if plus_di > minus_di: signal_score += weight
                    elif minus_di > plus_di: signal_score -= weight
                elif adx_val < ADX_WEAK_TREND_THRESHOLD: pass

        if active_indicators.get("ichimoku_cloud", False):
            tenkan_sen = self._get_indicator_value("Tenkan_Sen")
            kijun_sen = self._get_indicator_value("Kijun_Sen")
            senkou_span_a = self._get_indicator_value("Senkou_Span_A")
            senkou_span_b = self._get_indicator_value("Senkou_Span_B")
            chikou_span = self._get_indicator_value("Chikou_Span")
            weight = weights.get("ichimoku_confluence", 0.0)

            if not pd.isna(tenkan_sen) and not pd.isna(kijun_sen) and not pd.isna(senkou_span_a) and not pd.isna(senkou_span_b) and not pd.isna(chikou_span):
                if tenkan_sen > kijun_sen and self.df["Tenkan_Sen"].iloc[-2] <= self.df["Kijun_Sen"].iloc[-2]: signal_score += weight * 0.5
                elif tenkan_sen < kijun_sen and self.df["Tenkan_Sen"].iloc[-2] >= self.df["Kijun_Sen"].iloc[-2]: signal_score -= weight * 0.5

                if current_close > max(senkou_span_a, senkou_span_b) and self.df["close"].iloc[-2] <= max(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]): signal_score += weight * 0.7
                elif current_close < min(senkou_span_a, senkou_span_b) and self.df["close"].iloc[-2] >= min(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]): signal_score -= weight * 0.7

                if chikou_span > current_close and self.df["Chikou_Span"].iloc[-2] <= self.df["close"].iloc[-2]: signal_score += weight * 0.3
                elif chikou_span < current_close and self.df["Chikou_Span"].iloc[-2] >= self.df["close"].iloc[-2]: signal_score -= weight * 0.3

        if active_indicators.get("obv", False):
            obv_val = self._get_indicator_value("OBV")
            obv_ema = self._get_indicator_value("OBV_EMA")
            weight = weights.get("obv_momentum", 0.0)
            if not pd.isna(obv_val) and not pd.isna(obv_ema):
                if obv_val > obv_ema and self.df["OBV"].iloc[-2] <= self.df["OBV_EMA"].iloc[-2]: signal_score += weight * 0.5
                elif obv_val < obv_ema and self.df["OBV"].iloc[-2] >= self.df["OBV_EMA"].iloc[-2]: signal_score -= weight * 0.5
                if len(self.df) > 2:
                    if obv_val > self.df["OBV"].iloc[-2] and obv_val > self.df["OBV"].iloc[-3]: signal_score += weight * 0.2
                    elif obv_val < self.df["OBV"].iloc[-2] and obv_val < self.df["OBV"].iloc[-3]: signal_score -= weight * 0.2

        if active_indicators.get("cmf", False):
            cmf_val = self._get_indicator_value("CMF")
            weight = weights.get("cmf_flow", 0.0)
            if not pd.isna(cmf_val):
                if cmf_val > 0: signal_score += weight * 0.5
                elif cmf_val < 0: signal_score -= weight * 0.5
                if len(self.df) > 2:
                    if cmf_val > self.df["CMF"].iloc[-2] and cmf_val > self.df["CMF"].iloc[-3]: signal_score += weight * 0.3
                    elif cmf_val < self.df["CMF"].iloc[-2] and cmf_val < self.df["CMF"].iloc[-3]: signal_score -= weight * 0.3

        if self.config["mtf_analysis"]["enabled"] and mtf_trends:
            mtf_buy_score = sum(1 for trend in mtf_trends.values() if trend == "UP")
            mtf_sell_score = sum(-1 for trend in mtf_trends.values() if trend == "DOWN")
            if mtf_trends:
                normalized_mtf_score = (mtf_buy_score + mtf_sell_score) / len(mtf_trends)
                signal_score += weights.get("mtf_trend_confluence", 0.0) * normalized_mtf_score
                self.logger.debug(f"MTF Confluence: Score {normalized_mtf_score:.2f}")

        threshold = self.config["signal_score_threshold"]
        final_signal = "HOLD"
        if signal_score >= threshold: final_signal = "BUY"
        elif signal_score <= -threshold: final_signal = "SELL"

        self.logger.info(f"{NEON_YELLOW}Raw Technical Signal Score: {signal_score:.2f}, Final Technical Signal: {final_signal}{RESET}")
        return final_signal, signal_score


    # --- Remaining Indicator Implementations ---
    def calculate_true_range(self) -> pd.Series:
        """Calculate True Range (TR)."""
        if len(self.df) < MIN_DATA_POINTS_TR: return pd.Series(np.nan, index=self.df.index)
        high_low = self.df["high"] - self.df["low"]
        high_prev_close = (self.df["high"] - self.df["close"].shift()).abs()
        low_prev_close = (self.df["low"] - self.df["close"].shift()).abs()
        return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)

    def calculate_super_smoother(self, series: pd.Series, period: int) -> pd.Series:
        """Apply Ehlers SuperSmoother filter to reduce lag and noise."""
        if period <= 0 or len(series) < MIN_DATA_POINTS_SMOOTHER: return pd.Series(np.nan, index=series.index)
        series = pd.to_numeric(series, errors="coerce").dropna()
        if len(series) < MIN_DATA_POINTS_SMOOTHER: return pd.Series(np.nan, index=series.index)

        a1 = np.exp(-np.sqrt(2) * np.pi / period)
        b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / period)
        c1 = 1 - b1 + a1**2
        c2 = b1 - 2 * a1**2
        c3 = a1**2

        filt = pd.Series(0.0, index=series.index)
        if len(series) >= 1: filt.iloc = series.iloc
        if len(series) >= 2: filt.iloc = (series.iloc + series.iloc) / 2

        for i in range(2, len(series)):
            filt.iloc[i] = ((c1 / 2) * (series.iloc[i] + series.iloc[i - 1])) + (c2 * filt.iloc[i - 1]) - (c3 * filt.iloc[i - 2])
        return filt.reindex(self.df.index)

    def calculate_ehlers_supertrend(self, period: int, multiplier: float) -> Optional[pd.DataFrame]:
        """Calculate SuperTrend using Ehlers SuperSmoother for price and volatility."""
        if len(self.df) < period * 3: return None
        df_copy = self.df.copy()
        hl2 = (df_copy["high"] + df_copyThis is a blueprint for the enhanced, integrated trading bot, structured logically based on the final Python code.

code
Markdown
download
content_copy
expand_less
# Project Blueprint: AI-Enhanced Multi-Indicator Trading Bot (WhaleBot)

## 1. Project Overview

This project implements a sophisticated, real-time cryptocurrency trading bot designed to operate against the **Bybit** exchange. The bot's core strength lies in its **hybrid signal generation**, combining an extensive suite of **technical indicators** (including advanced indicators like Ehlers SuperTrend) with **Generative AI analysis** from Google's Gemini model.

The system prioritizes **financial precision** by utilizing Python's `Decimal` type for all critical calculations and features an **AI Vision capability** to analyze generated price charts.

---

## 2. High-Level Architecture

The bot operates in a continuous loop, following a five-stage process:

**Data Acquisition $\rightarrow$ Technical Analysis $\rightarrow$ AI Analysis $\rightarrow$ Signal Aggregation $\rightarrow$ Trade Management**

```mermaid
graph TD
    A[External: Bybit Exchange] --> B{Data Acquisition};
    B --> C[Technical Analysis Module];
    C --> D[AI Analysis Module];
    D --> E[Signal Aggregation & Decision];
    E --> F[Trade Management Module];
    F --> G[Execution / Position Check];
    G --> H[Logging / Performance Tracking];
    H --> I(Console / Log Files);
    G --> A; % Feedback loop for order placement (simulated here)
3. Key Modules & Responsibilities

The code is logically separated into the following functional components:

Module 1: Configuration & Setup

Responsibility: Handles environment setup, configuration loading, and logging.

Key Features:

Loads API keys and settings from a .env file.

Loads/validates config.json for all trading parameters and indicator weights.

Sets up colorized console logging and rotating file logging with a SensitiveFormatter to redact API keys.

Module 2: API Client

Responsibility: Manages all secure and public communication with the Bybit exchange.

Key Features:

Uses requests.Session with urllib3.util.retry.Retry for robust handling of network errors and rate limits (429, 5xx).

Implements Bybit Signed Request logic (HMAC-SHA256).

Functions to fetch klines, current_price, and orderbook.

Module 3: Trade Management

Responsibility: Manages the lifecycle of trades and tracks overall performance.

Key Features:

PositionManager: Calculates order size using Decimal precision, factoring in AI-suggested risk or ATR multiples for SL/TP. Manages open positions and checks for SL/TP hits.

PerformanceTracker: Records trade outcomes (PnL, Win/Loss) and calculates aggregate metrics.

AlertSystem: Centralized point for sending critical notifications.

Module 4: Technical Signal Analysis

Responsibility: The core quantitative engine. Calculates all configured technical indicators.

Key Features:

Implements 40+ indicators, including complex ones like Ehlers SuperTrend, MACD, Ichimoku, CMF, and VWAP.

Uses Pandas/NumPy vectorization for performance.

Applies indicator-specific weights to generate a raw signal_score.

Includes logic for Multi-Timeframe (MTF) Trend Confluence.

Module 5: AI Signal Analysis

Responsibility: Interfaces with the Gemini API for advanced, contextual analysis.

Key Features:

GeminiSignalAnalyzer: Manages API key, caching, and daily call limits.

Text Analysis: Sends market context (indicators, price) to Gemini for a structured JSON signal, confidence score, and suggested levels.

Vision Analysis (Enhanced): If enabled, it uses matplotlib to generate a chart image, encodes it in Base64, and sends it to the Gemini Vision model for pattern/trend detection.

Signal Combination: Implements logic to blend the technical score and AI score via configurable weights, with conflict resolution for opposing signals.

Module 6: Main Execution Loop

Responsibility: Orchestrates the entire process.

Key Features:

Initializes all components (Config, Logger, BybitClient, Analyzer, PositionManager, GeminiAnalyzer).

Runs the main loop, fetching data, calling analyzers, and executing trade management decisions based on the final, combined signal score.

4. Core Technologies & Dependencies
Category	Technology/Library	Purpose
Language/Core	Python 3.x, Decimal	High-precision financial math.
Data Handling	pandas, numpy	Fast data manipulation and indicator calculation.
API Interaction	requests, hmac, hashlib	Bybit API communication and request signing.
Configuration	python-dotenv, json	Loading secrets and parameters.
AI Integration	google-genai	Interfacing with Gemini Pro (text) and Gemini Vision.
Visualization	matplotlib (Optional)	Generating charts for Gemini Vision analysis.
Utility	colorama, zoneinfo	Console coloring and timezone handling (UTC/Chicago).
5. Operational Logic Flow

Initialization: Load config, set up logging, initialize API clients and AI analyzer.

Loop Start: Fetch current price, primary timeframe Klines, and MTF Klines (if enabled).

Data Processing: Create TradingAnalyzer instance to calculate all technical indicators on the primary timeframe data.

Signal Generation (Technical): TradingAnalyzer.generate_trading_signal() calculates the raw technical score.

Signal Generation (AI): If enabled, GeminiSignalAnalyzer analyzes the market context and potentially a chart image, returning an enhanced signal and suggested levels.

Signal Aggregation: The main loop combines the technical and AI scores based on weights and confidence thresholds to determine the final_trading_signal.

Position Management: PositionManager checks for existing positions that hit SL/TP (closing them and recording performance) and then attempts to open a new position based on the final_trading_signal and AI-suggested sizing/levels.

Logging & Wait: Log the results and wait for the configured loop_delay.

code
Code
download
content_copy
expand_less
