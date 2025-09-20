97c97
< TIMEZONE = timezone.utc  # Changed from ZoneInfo("America/Chicago")
---
> TIMEZONE = timezone.utc
203a204,206
>             # ADX thresholds moved to indicator_settings for better config management
>             "ADX_STRONG_TREND_THRESHOLD": 25,
>             "ADX_WEAK_TREND_THRESHOLD": 20,
265a269
>             # Fallback to default config even if file creation fails
271a276
>         # Save the merged config to ensure consistency and add any new default keys
293a299,303
>         # If config[key] exists but is not a dict, and default_value is a dict,
>         # it means the config file has a non-dict value where a dict is expected.
>         # This case is handled by overwriting with the default dict structure.
>         elif isinstance(default_value, dict) and not isinstance(config.get(key), dict):
>              config[key] = default_value
453c463
<     logger.warning(f"{NEON_YELLOW}Could not fetch current price for {symbol}.{RESET}")
---
>     logger.warning(f"{NEON_YELLOW}[{symbol}] Could not fetch current price.{RESET}")
492c502
<                 f"{NEON_YELLOW}Fetched klines for {symbol} {interval} but DataFrame is empty after processing. Raw response: {response}{RESET}"
---
>                 f"{NEON_YELLOW}[{symbol}] Fetched klines for {interval} but DataFrame is empty after processing. Raw response: {response}{RESET}"
499c509
<         f"{NEON_YELLOW}Could not fetch klines for {symbol} {interval}. API response might be empty or invalid. Raw response: {response}{RESET}"
---
>         f"{NEON_YELLOW}[{symbol}] Could not fetch klines for {interval}. API response might be empty or invalid. Raw response: {response}{RESET}"
512c522
<     logger.warning(f"{NEON_YELLOW}Could not fetch orderbook for {symbol}.{RESET}")
---
>     logger.warning(f"{NEON_YELLOW}[{symbol}] Could not fetch orderbook.{RESET}")
566c576
<                 f"{NEON_YELLOW}Calculated stop loss distance is zero or negative. Cannot determine order size.{RESET}"
---
>                 f"{NEON_YELLOW}[{self.symbol}] Calculated stop loss distance is zero or negative ({stop_loss_distance}). Cannot determine order size.{RESET}"
576c586,588
<         precision_str = "0." + "0" * (self.order_precision - 1) + "1"
---
>         # Ensure precision is at least 1 (e.g., 0.1, 0.01, etc.)
>         precision_exponent = max(0, self.order_precision - 1)
>         precision_str = "0." + "0" * precision_exponent + "1"
606c618
<                 f"{NEON_YELLOW}[{self.symbol}] Order quantity is zero or negative. Cannot open position.{RESET}"
---
>                 f"{NEON_YELLOW}[{self.symbol}] Order quantity is zero or negative ({order_qty}). Cannot open position.{RESET}"
616a629,632
>         # Ensure price precision is at least 1 (e.g., 0.1, 0.01, etc.)
>         price_precision_exponent = max(0, self.price_precision - 1)
>         price_precision_str = "0." + "0" * price_precision_exponent + "1"
> 
624,625d639
<         price_precision_str = "0." + "0" * (self.price_precision - 1) + "1"
< 
656c670,673
<         positions_to_close = []
---
>         positions_to_close_indices = [] # Store indices of positions to close
>         price_precision_exponent = max(0, self.price_precision - 1)
>         price_precision_str = "0." + "0" * price_precision_exponent + "1"
> 
675c692
<                 elif side == "SELL":  # Added explicit check for SELL
---
>                 elif side == "SELL":
687,688c704
<                         Decimal("0." + "0" * (self.price_precision - 1) + "1"),
<                         rounding=ROUND_DOWN,
---
>                         Decimal(price_precision_str), rounding=ROUND_DOWN
691c707
<                     positions_to_close.append(i)
---
>                     positions_to_close_indices.append(i)
703c719
<         # Remove closed positions
---
>         # Remove closed positions by creating a new list
705,707c721
<             pos
<             for i, pos in enumerate(self.open_positions)
<             if i not in positions_to_close
---
>             pos for i, pos in enumerate(self.open_positions) if i not in positions_to_close_indices
802c816,817
<         self.weights = config["weight_sets"]["default_scalping"]
---
>         # Use .get for safer access to weights, providing an empty dict if not found
>         self.weights = config["weight_sets"].get("default_scalping", {})
809c824
<                 f"{NEON_YELLOW}TradingAnalyzer initialized with an empty DataFrame. Indicators will not be calculated.{RESET}"
---
>                 f"{NEON_YELLOW}[{self.symbol}] TradingAnalyzer initialized with an empty DataFrame. Indicators will not be calculated.{RESET}"
1095c1110
<                 min_data_points=isd["ehlers_fast_period"] * 3,
---
>                 min_data_points=isd["ehlers_fast_period"] * 3, # Heuristic for sufficient data
1112c1127
<                 min_data_points=isd["ehlers_slow_period"] * 3,
---
>                 min_data_points=isd["ehlers_slow_period"] * 3, # Heuristic for sufficient data
1154c1169
<                 min_data_points=isd["adx_period"] * 2,
---
>                 min_data_points=isd["adx_period"] * 2, # ADX requires at least 2*period for smoothing
1208,1209c1223,1227
<         self.df.dropna(subset=["close"], inplace=True)
<         self.df.fillna(0, inplace=True)  # Fill any remaining NaNs in indicator columns
---
>         self.df.dropna(subset=["close"], inplace=True) # Ensure close price is valid
>         # Fill remaining NaNs in indicator columns with 0 or a sensible default if appropriate.
>         # For signal generation, NaNs might be better handled as 'no signal contribution'.
>         # However, for simplicity in this refactor, we'll fill with 0 for now, and scoring methods handle NaNs.
>         self.df.fillna(0, inplace=True)
1213c1231
<                 f"Dropped {initial_len - len(self.df)} rows with NaNs after indicator calculations."
---
>                 f"[{self.symbol}] Dropped {initial_len - len(self.df)} rows with NaNs after indicator calculations."
1269c1287,1289
<         if len(self.df) < period * 3:
---
>         # Ensure enough data points for calculation
>         min_bars_required = period * 3 # A common heuristic
>         if len(self.df) < min_bars_required:
1271c1291
<                 f"[{self.symbol}] Not enough data for Ehlers SuperTrend (period={period}). Need at least {period*3} bars."
---
>                 f"[{self.symbol}] Not enough data for Ehlers SuperTrend (period={period}). Need at least {min_bars_required} bars."
1438,1439c1458,1459
<         plus_di = (plus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100
<         minus_di = (minus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100
---
>         plus_di = (plus_dm_final.ewm(span=period, adjust=False).mean() / atr.replace(0, np.nan)) * 100
>         minus_di = (minus_dm_final.ewm(span=period, adjust=False).mean() / atr.replace(0, np.nan)) * 100
1476c1496
<         vwap = cumulative_tp_vol / cumulative_vol
---
>         vwap = cumulative_tp_vol / cumulative_vol.replace(0, np.nan) # Handle division by zero
1511,1515c1531,1536
<         if (
<             len(self.df)
<             < max(tenkan_period, kijun_period, senkou_span_b_period)
<             + chikou_span_offset
<         ):
---
>         # Ensure enough data points for all components and the shift
>         required_len = max(tenkan_period, kijun_period, senkou_span_b_period) + chikou_span_offset
>         if len(self.df) < required_len:
>             self.logger.debug(
>                 f"[{self.symbol}] Not enough data for Ichimoku Cloud. Need {required_len}, have {len(self.df)}."
>             )
1533a1555
>         # Senkou Span A is calculated based on Tenkan and Kijun, then shifted forward
1535a1558
>         # Senkou Span B is calculated based on highest high and lowest low over its period, then shifted forward
1559d1581
<         # Use vectorized operations where possible
1578a1601
>         # Calculate OBV direction change and cumulative sum
1621a1645
>         # Initialize EP based on the direction of the first two bars
1624c1648
<             if self.df["close"].iloc[0] < self.df["close"].iloc[1]
---
>             if len(self.df) > 1 and self.df["close"].iloc[0] < self.df["close"].iloc[1]
1626c1650
<         )  # Initial EP depends on first two bars' direction
---
>         )
1687a1712
>         # Use the last 'window' number of bars for calculation
1699,1716c1724,1731
<         self.fib_levels = {
<             "0.0%": Decimal(str(recent_high)),
<             "23.6%": Decimal(str(recent_high - 0.236 * diff)).quantize(
<                 Decimal("0.00001"), rounding=ROUND_DOWN
<             ),
<             "38.2%": Decimal(str(recent_high - 0.382 * diff)).quantize(
<                 Decimal("0.00001"), rounding=ROUND_DOWN
<             ),
<             "50.0%": Decimal(str(recent_high - 0.500 * diff)).quantize(
<                 Decimal("0.00001"), rounding=ROUND_DOWN
<             ),
<             "61.8%": Decimal(str(recent_high - 0.618 * diff)).quantize(
<                 Decimal("0.00001"), rounding=ROUND_DOWN
<             ),
<             "78.6%": Decimal(str(recent_high - 0.786 * diff)).quantize(
<                 Decimal("0.00001"), rounding=ROUND_DOWN
<             ),
<             "100.0%": Decimal(str(recent_low)),
---
>         # Use Decimal for precision
>         diff_dec = Decimal(str(diff))
>         recent_high_dec = Decimal(str(recent_high))
> 
>         # Define Fibonacci ratios
>         fib_ratios = {
>             "0.0%": 0.0, "23.6%": 0.236, "38.2%": 0.382, "50.0%": 0.500,
>             "61.8%": 0.618, "78.6%": 0.786, "100.0%": 1.0
1717a1733,1743
> 
>         self.fib_levels = {}
>         # Define precision for quantization, e.g., 5 decimal places for crypto
>         price_precision_exponent = max(0, self.config["trade_management"]["price_precision"] - 1)
>         quantize_str = "0." + "0" * price_precision_exponent + "1"
>         quantize_dec = Decimal(quantize_str)
> 
>         for level_name, ratio in fib_ratios.items():
>             level_price = recent_high_dec - (diff_dec * Decimal(str(ratio)))
>             self.fib_levels[level_name] = level_price.quantize(quantize_dec, rounding=ROUND_DOWN)
> 
1722c1748,1749
<         if len(self.df) < period or "ATR" not in self.df.columns:
---
>         if len(self.df) < period or "ATR" not in self.df.columns or self.df["ATR"].isnull().all():
>             self.logger.debug(f"[{self.symbol}] Not enough data or ATR missing for Volatility Index.")
1726c1753,1755
<         normalized_atr = self.df["ATR"] / self.df["close"]
---
>         # Normalize ATR by closing price to get a relative measure of volatility
>         normalized_atr = self.df["ATR"] / self.df["close"].replace(0, np.nan)
>         # Calculate a moving average of the normalized ATR
1735c1764
<         # Ensure volume is numeric and not zero
---
>         # Ensure volume is numeric and not zero for calculation
1737,1740c1766,1771
<         pv = self.df["close"] * valid_volume
<         vwma = pv.rolling(window=period).sum() / valid_volume.rolling(
<             window=period
<         ).sum()
---
>         pv = self.df["close"] * valid_volume # Price * Volume
>         # Sum of (Price * Volume) over the period
>         sum_pv = pv.rolling(window=period).sum()
>         # Sum of Volume over the period
>         sum_vol = valid_volume.rolling(window=period).sum()
>         vwma = sum_pv / sum_vol.replace(0, np.nan) # Handle division by zero
1748a1780
>         # If close > open, it's considered buying pressure (bullish candle)
1749a1782
>         # If close < open, it's considered selling pressure (bearish candle)
1752c1785
<         # Rolling sum of buy/sell volume
---
>         # Rolling sum of buy/sell volume over the specified period
1757c1790,1791
<         # Avoid division by zero
---
>         # Calculate delta: (Buy Volume - Sell Volume) / Total Volume
>         # This gives a ratio indicating net buying or selling pressure
1764c1798
<         """Safely retrieve an indicator value."""
---
>         """Safely retrieve an indicator value from the stored dictionary."""
1768c1802,1804
<         """Analyze orderbook imbalance."""
---
>         """Analyze orderbook imbalance.
>         Returns imbalance score between -1 (all asks) and +1 (all bids).
>         """
1775c1811,1812
<         if bid_volume + ask_volume == 0:
---
>         total_volume = bid_volume + ask_volume
>         if total_volume == 0:
1778c1815,1816
<         imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
---
>         # Imbalance: (Bid Volume - Ask Volume) / Total Volume
>         imbalance = (bid_volume - ask_volume) / total_volume
1789c1827
<         last_close = higher_tf_df["close"].iloc[-1]
---
>         # Ensure we have enough data for the indicator's period
1790a1829,1835
>         if len(higher_tf_df) < period:
>             self.logger.debug(
>                 f"[{self.symbol}] MTF Trend ({indicator_type}): Not enough data. Need {period}, have {len(higher_tf_df)}."
>             )
>             return "UNKNOWN"
> 
>         last_close = Decimal(str(higher_tf_df["close"].iloc[-1]))
1793,1797d1837
<             if len(higher_tf_df) < period:
<                 self.logger.debug(
<                     f"[{self.symbol}] MTF SMA: Not enough data for {period} period. Have {len(higher_tf_df)}."
<                 )
<                 return "UNKNOWN"
1809,1814c1849
<         if indicator_type == "ema":
<             if len(higher_tf_df) < period:
<                 self.logger.debug(
<                     f"[{self.symbol}] MTF EMA: Not enough data for {period} period. Have {len(higher_tf_df)}."
<                 )
<                 return "UNKNOWN"
---
>         elif indicator_type == "ema":
1826c1861,1864
<         if indicator_type == "ehlers_supertrend":
---
>         elif indicator_type == "ehlers_supertrend":
>             # This is inefficient as it recalculates the indicator.
>             # A better approach would be to pass pre-calculated indicator values or a pre-instantiated analyzer.
>             # For now, keeping it as is but noting the inefficiency.
1829a1868,1875
>             # Use the slow SuperTrend for MTF trend determination as per common practice
>             st_period = self.indicator_settings["ehlers_slow_period"]
>             st_multiplier = self.indicator_settings["ehlers_slow_multiplier"]
>             # Ensure enough data for ST calculation
>             if len(higher_tf_df) < st_period * 3: # Heuristic for sufficient data
>                  self.logger.debug(f"[{self.symbol}] MTF Ehlers SuperTrend: Not enough data for ST calculation (period={st_period}).")
>                  return "UNKNOWN"
> 
1831,1832c1877,1878
<                 period=self.indicator_settings["ehlers_slow_period"],
<                 multiplier=self.indicator_settings["ehlers_slow_multiplier"],
---
>                 period=st_period,
>                 multiplier=st_multiplier,
1843,2100c1889,1908
<     def generate_trading_signal(
<         self,
<         current_price: Decimal,
<         orderbook_data: dict | None,
<         mtf_trends: dict[str, str],
<     ) -> tuple[str, float, dict]:
<         """Generate a signal using confluence of indicators, including Ehlers SuperTrend.
<         Returns the final signal, the aggregated signal score, and a breakdown of contributions.
<         """
<         signal_score = 0.0
<         signal_breakdown: dict[str, float] = {} # Initialize breakdown dictionary
<         active_indicators = self.config["indicators"]
<         weights = self.weights
<         isd = self.indicator_settings
< 
<         if self.df.empty:
<             self.logger.warning(
<                 f"{NEON_YELLOW}[{self.symbol}] DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}"
<             )
<             return "HOLD", 0.0, {}
< 
<         current_close = Decimal(str(self.df["close"].iloc[-1]))
<         prev_close = Decimal(
<             str(self.df["close"].iloc[-2]) if len(self.df) > 1 else current_close
<         )
< 
<         # EMA Alignment
<         if active_indicators.get("ema_alignment", False):
<             ema_short = self._get_indicator_value("EMA_Short")
<             ema_long = self._get_indicator_value("EMA_Long")
<             if not pd.isna(ema_short) and not pd.isna(ema_long):
<                 contrib = 0.0
<                 if ema_short > ema_long:
<                     contrib = weights.get("ema_alignment", 0)
<                 elif ema_short < ema_long:
<                     contrib = -weights.get("ema_alignment", 0)
<                 signal_score += contrib
<                 signal_breakdown["EMA_Alignment"] = contrib
< 
<         # SMA Trend Filter
<         if active_indicators.get("sma_trend_filter", False):
<             sma_long = self._get_indicator_value("SMA_Long")
<             if not pd.isna(sma_long):
<                 contrib = 0.0
<                 if current_close > sma_long:
<                     contrib = weights.get("sma_trend_filter", 0)
<                 elif current_close < sma_long:
<                     contrib = -weights.get("sma_trend_filter", 0)
<                 signal_score += contrib
<                 signal_breakdown["SMA_Trend_Filter"] = contrib
< 
<         # Momentum Indicators (RSI, StochRSI, CCI, WR, MFI)
<         if active_indicators.get("momentum", False):
<             momentum_weight = weights.get("momentum_rsi_stoch_cci_wr_mfi", 0)
< 
<             # RSI
<             if active_indicators.get("rsi", False):
<                 rsi = self._get_indicator_value("RSI")
<                 if not pd.isna(rsi):
<                     # Normalize RSI to a -1 to +1 scale
<                     normalized_rsi = (float(rsi) - 50) / 50
<                     contrib = normalized_rsi * momentum_weight * 0.5
<                     signal_score += contrib
<                     signal_breakdown["RSI_Signal"] = contrib
< 
<             # StochRSI Crossover
<             if active_indicators.get("stoch_rsi", False):
<                 stoch_k = self._get_indicator_value("StochRSI_K")
<                 stoch_d = self._get_indicator_value("StochRSI_D")
<                 if not pd.isna(stoch_k) and not pd.isna(stoch_d) and len(self.df) > 1:
<                     prev_stoch_k = self.df["StochRSI_K"].iloc[-2]
<                     prev_stoch_d = self.df["StochRSI_D"].iloc[-2]
<                     contrib = 0.0
<                     if (
<                         stoch_k > stoch_d
<                         and prev_stoch_k <= prev_stoch_d
<                         and stoch_k < isd["stoch_rsi_oversold"]
<                     ):
<                         contrib = momentum_weight * 0.6
<                         self.logger.debug(f"[{self.symbol}] StochRSI: Bullish crossover from oversold.")
<                     elif (
<                         stoch_k < stoch_d
<                         and prev_stoch_k >= prev_stoch_d
<                         and stoch_k > isd["stoch_rsi_overbought"]
<                     ):
<                         contrib = -momentum_weight * 0.6
<                         self.logger.debug(f"[{self.symbol}] StochRSI: Bearish crossover from overbought.")
<                     elif stoch_k > stoch_d and stoch_k < 50: # General bullish momentum
<                         contrib = momentum_weight * 0.2
<                     elif stoch_k < stoch_d and stoch_k > 50: # General bearish momentum
<                         contrib = -momentum_weight * 0.2
<                     signal_score += contrib
<                     signal_breakdown["StochRSI_Signal"] = contrib
< 
<             # CCI
<             if active_indicators.get("cci", False):
<                 cci = self._get_indicator_value("CCI")
<                 if not pd.isna(cci):
<                     # Normalize CCI (e.g., -200 to +200 range, normalize to -1 to +1)
<                     normalized_cci = float(cci) / 200 # Assuming typical range of -200 to 200
<                     contrib = 0.0
<                     if cci < isd["cci_oversold"]:
<                         contrib = momentum_weight * 0.4
<                     elif cci > isd["cci_overbought"]:
<                         contrib = -momentum_weight * 0.4
<                     signal_score += contrib
<                     signal_breakdown["CCI_Signal"] = contrib
< 
<             # Williams %R
<             if active_indicators.get("wr", False):
<                 wr = self._get_indicator_value("WR")
<                 if not pd.isna(wr):
<                     # Normalize WR to -1 to +1 scale (-100 to 0, so (WR + 50) / 50)
<                     normalized_wr = (float(wr) + 50) / 50 # Assuming typical range of -100 to 0
<                     contrib = 0.0
<                     if wr < isd["williams_r_oversold"]:
<                         contrib = momentum_weight * 0.4
<                     elif wr > isd["williams_r_overbought"]:
<                         contrib = -momentum_weight * 0.4
<                     signal_score += contrib
<                     signal_breakdown["WR_Signal"] = contrib
< 
<             # MFI
<             if active_indicators.get("mfi", False):
<                 mfi = self._get_indicator_value("MFI")
<                 if not pd.isna(mfi):
<                     # Normalize MFI to -1 to +1 scale (0 to 100, so (MFI - 50) / 50)
<                     normalized_mfi = (float(mfi) - 50) / 50
<                     contrib = 0.0
<                     if mfi < isd["mfi_oversold"]:
<                         contrib = momentum_weight * 0.4
<                     elif mfi > isd["mfi_overbought"]:
<                         contrib = -momentum_weight * 0.4
<                     signal_score += contrib
<                     signal_breakdown["MFI_Signal"] = contrib
< 
<         # Bollinger Bands
<         if active_indicators.get("bollinger_bands", False):
<             bb_upper = self._get_indicator_value("BB_Upper")
<             bb_lower = self._get_indicator_value("BB_Lower")
<             if not pd.isna(bb_upper) and not pd.isna(bb_lower):
<                 contrib = 0.0
<                 if current_close < bb_lower:
<                     contrib = weights.get("bollinger_bands", 0) * 0.5
<                 elif current_close > bb_upper:
<                     contrib = -weights.get("bollinger_bands", 0) * 0.5
<                 signal_score += contrib
<                 signal_breakdown["Bollinger_Bands_Signal"] = contrib
< 
<         # VWAP
<         if active_indicators.get("vwap", False):
<             vwap = self._get_indicator_value("VWAP")
<             if not pd.isna(vwap):
<                 contrib = 0.0
<                 if current_close > vwap:
<                     contrib = weights.get("vwap", 0) * 0.2
<                 elif current_close < vwap:
<                     contrib = -weights.get("vwap", 0) * 0.2
< 
<                 if len(self.df) > 1:
<                     prev_vwap = Decimal(str(self.df["VWAP"].iloc[-2]))
<                     if (current_close > vwap and prev_close <= prev_vwap):
<                         contrib += weights.get("vwap", 0) * 0.3
<                         self.logger.debug(f"[{self.symbol}] VWAP: Bullish crossover detected.")
<                     elif (current_close < vwap and prev_close >= prev_vwap):
<                         contrib -= weights.get("vwap", 0) * 0.3
<                         self.logger.debug(f"[{self.symbol}] VWAP: Bearish crossover detected.")
<                 signal_score += contrib
<                 signal_breakdown["VWAP_Signal"] = contrib
< 
<         # PSAR
<         if active_indicators.get("psar", False):
<             psar_val = self._get_indicator_value("PSAR_Val")
<             psar_dir = self._get_indicator_value("PSAR_Dir")
<             if not pd.isna(psar_val) and not pd.isna(psar_dir):
<                 contrib = 0.0
<                 # PSAR direction change is a strong signal
<                 if psar_dir == 1: # Bullish PSAR
<                     contrib = weights.get("psar", 0) * 0.5
<                 elif psar_dir == -1: # Bearish PSAR
<                     contrib = -weights.get("psar", 0) * 0.5
< 
<                 # PSAR crossover with price
<                 if len(self.df) > 1:
<                     prev_psar_val = Decimal(str(self.df["PSAR_Val"].iloc[-2]))
<                     if (current_close > psar_val and prev_close <= prev_psar_val):
<                         contrib += weights.get("psar", 0) * 0.4 # Additional bullish weight on crossover
<                         self.logger.debug("PSAR: Bullish reversal detected.")
<                     elif (current_close < psar_val and prev_close >= prev_psar_val):
<                         contrib -= weights.get("psar", 0) * 0.4 # Additional bearish weight on crossover
<                         self.logger.debug("PSAR: Bearish reversal detected.")
<                 signal_score += contrib
<                 signal_breakdown["PSAR_Signal"] = contrib
< 
<         # SMA_10 (short-term trend confirmation)
<         if active_indicators.get("sma_10", False):
<             sma_10 = self._get_indicator_value("SMA_10")
<             if not pd.isna(sma_10):
<                 contrib = 0.0
<                 if current_close > sma_10:
<                     contrib = weights.get("sma_10", 0) * 0.5
<                 elif current_close < sma_10:
<                     contrib = -weights.get("sma_10", 0) * 0.5
<                 signal_score += contrib
<                 signal_breakdown["SMA_10_Signal"] = contrib
< 
<         # Orderbook Imbalance
<         if active_indicators.get("orderbook_imbalance", False) and orderbook_data:
<             imbalance = self._check_orderbook(current_price, orderbook_data)
<             contrib = imbalance * weights.get("orderbook_imbalance", 0)
<             signal_score += contrib
<             signal_breakdown["Orderbook_Imbalance"] = contrib
< 
<         # Fibonacci Levels (confluence with price action)
<         if active_indicators.get("fibonacci_levels", False) and self.fib_levels:
<             for level_name, level_price in self.fib_levels.items():
<                 # Check if price is near a Fibonacci level
<                 if (level_name not in ["0.0%", "100.0%"] and
<                     abs(current_close - level_price) / current_close < Decimal("0.001")): # Within 0.1% of the level
<                         self.logger.debug(
<                             f"Price near Fibonacci level {level_name}: {level_price}"
<                         )
<                         contrib = 0.0
<                         # If price crosses the level, it can act as support/resistance
<                         if len(self.df) > 1:
<                             if (current_close > prev_close and current_close > level_price): # Bullish breakout
<                                 contrib = weights.get("fibonacci_levels", 0) * 0.1
<                             elif (current_close < prev_close and current_close < level_price): # Bearish breakdown
<                                 contrib = -weights.get("fibonacci_levels", 0) * 0.1
<                         signal_score += contrib
<                         signal_breakdown["Fibonacci_Levels_Signal"] = contrib
< 
<         # --- Ehlers SuperTrend Alignment Scoring ---
<         if active_indicators.get("ehlers_supertrend", False):
<             st_fast_dir = self._get_indicator_value("ST_Fast_Dir")
<             st_slow_dir = self._get_indicator_value("ST_Slow_Dir")
<             prev_st_fast_dir = (
<                 self.df["st_fast_dir"].iloc[-2]
<                 if "st_fast_dir" in self.df.columns and len(self.df) > 1
<                 else np.nan
<             )
<             weight = weights.get("ehlers_supertrend_alignment", 0.0)
< 
<             if (
<                 not pd.isna(st_fast_dir)
<                 and not pd.isna(st_slow_dir)
<                 and not pd.isna(prev_st_fast_dir)
<             ):
<                 contrib = 0.0
<                 # Strong buy signal: fast ST flips up and aligns with slow ST (which is also up)
<                 if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1:
<                     contrib = weight
<                     self.logger.debug(
<                         "Ehlers SuperTrend: Strong BUY signal (fast flip aligned with slow trend)."
<                     )
<                 # Strong sell signal: fast ST flips down and aligns with slow ST (which is also down)
<                 elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1:
<                     contrib = -weight
---
>     def _fetch_and_analyze_mtf(self) -> dict[str, str]:
>         """Fetches data for higher timeframes and determines trends."""
>         mtf_trends: dict[str, str] = {}
>         if not self.config["mtf_analysis"]["enabled"]:
>             return mtf_trends
> 
>         higher_timeframes = self.config["mtf_analysis"]["higher_timeframes"]
>         trend_indicators = self.config["mtf_analysis"]["trend_indicators"]
>         mtf_request_delay = self.config["mtf_analysis"]["mtf_request_delay_seconds"]
> 
>         for htf_interval in higher_timeframes:
>             self.logger.debug(f"[{self.symbol}] Fetching klines for MTF interval: {htf_interval}")
>             # Fetch enough data for the longest indicator period on MTF
>             # Fetching a larger number (e.g., 1000) is good practice
>             htf_df = fetch_klines(self.symbol, htf_interval, 1000, self.logger)
> 
>             if htf_df is not None and not htf_df.empty:
>                 for trend_ind in trend_indicators:
>                     trend = self._get_mtf_trend(htf_df, trend_ind)
>                     mtf_trends[f"{htf_interval}_{trend_ind}"] = trend
2102c1910
<                         "Ehlers SuperTrend: Strong SELL signal (fast flip aligned with slow trend)."
---
>                         f"[{self.symbol}] MTF Trend ({htf_interval}, {trend_ind}): {trend}"
2104,2110c1912,1917
<                 # General alignment: both fast and slow ST are in the same direction
<                 elif st_slow_dir == 1 and st_fast_dir == 1:
<                     contrib = weight * 0.3
<                 elif st_slow_dir == -1 and st_fast_dir == -1:
<                     contrib = -weight * 0.3
<                 signal_score += contrib
<                 signal_breakdown["Ehlers_SuperTrend_Alignment"] = contrib
---
>             else:
>                 self.logger.warning(
>                     f"{NEON_YELLOW}[{self.symbol}] Could not fetch klines for higher timeframe {htf_interval} or it was empty. Skipping MTF trend for this TF.{RESET}"
>                 )
>             time.sleep(mtf_request_delay) # Delay between MTF requests
>         return mtf_trends
2112,2117c1919
<         # --- MACD Alignment Scoring ---
<         if active_indicators.get("macd", False):
<             macd_line = self._get_indicator_value("MACD_Line")
<             signal_line = self._get_indicator_value("MACD_Signal")
<             histogram = self._get_indicator_value("MACD_Hist")
<             weight = weights.get("macd_alignment", 0.0)
---
>     # --- Signal Scoring Helper Methods ---
2119,2150c1921,1924
<             if (
<                 not pd.isna(macd_line)
<                 and not pd.isna(signal_line)
<                 and not pd.isna(histogram)
<                 and len(self.df) > 1
<             ):
<                 contrib = 0.0
<                 # Bullish crossover: MACD line crosses above Signal line
<                 if (
<                     macd_line > signal_line
<                     and self.df["MACD_Line"].iloc[-2] <= self.df["MACD_Signal"].iloc[-2]
<                 ):
<                     contrib = weight
<                     self.logger.debug(
<                         "MACD: BUY signal (MACD line crossed above Signal line)."
<                     )
<                 # Bearish crossover: MACD line crosses below Signal line
<                 elif (
<                     macd_line < signal_line
<                     and self.df["MACD_Line"].iloc[-2] >= self.df["MACD_Signal"].iloc[-2]
<                 ):
<                     contrib = -weight
<                     self.logger.debug(
<                         "MACD: SELL signal (MACD line crossed below Signal line)."
<                     )
<                 # Histogram turning positive/negative from zero line
<                 elif histogram > 0 and self.df["MACD_Hist"].iloc[-2] < 0:
<                     contrib = weight * 0.2
<                 elif histogram < 0 and self.df["MACD_Hist"].iloc[-2] > 0:
<                     contrib = -weight * 0.2
<                 signal_score += contrib
<                 signal_breakdown["MACD_Alignment"] = contrib
---
>     def _score_ema_alignment(self, signal_score: float, signal_breakdown: dict) -> tuple[float, dict]:
>         """Scores EMA alignment."""
>         if not self.config["indicators"].get("ema_alignment", False):
>             return signal_score, signal_breakdown
2152,2157c1926,1928
<         # --- ADX Alignment Scoring ---
<         if active_indicators.get("adx", False):
<             adx_val = self._get_indicator_value("ADX")
<             plus_di = self._get_indicator_value("PlusDI")
<             minus_di = self._get_indicator_value("MinusDI")
<             weight = weights.get("adx_strength", 0.0)
---
>         ema_short = self._get_indicator_value("EMA_Short")
>         ema_long = self._get_indicator_value("EMA_Long")
>         weight = self.weights.get("ema_alignment", 0)
2159,2177c1930,1938
<             if not pd.isna(adx_val) and not pd.isna(plus_di) and not pd.isna(minus_di):
<                 contrib = 0.0
<                 # Strong trend confirmation
<                 if adx_val > ADX_STRONG_TREND_THRESHOLD:
<                     if plus_di > minus_di: # Bullish trend
<                         contrib = weight
<                         self.logger.debug(
<                             "ADX: Strong BUY trend (ADX > 25, +DI > -DI)."
<                         )
<                     elif minus_di > plus_di: # Bearish trend
<                         contrib = -weight
<                         self.logger.debug(
<                             "ADX: Strong SELL trend (ADX > 25, -DI > +DI)."
<                         )
<                 elif adx_val < ADX_WEAK_TREND_THRESHOLD:
<                     contrib = 0 # Neutral signal, no contribution from ADX
<                     self.logger.debug("ADX: Weak trend (ADX < 20). Neutral signal.")
<                 signal_score += contrib
<                 signal_breakdown["ADX_Strength"] = contrib
---
>         if not pd.isna(ema_short) and not pd.isna(ema_long) and weight > 0:
>             contrib = 0.0
>             if ema_short > ema_long:
>                 contrib = weight
>             elif ema_short < ema_long:
>                 contrib = -weight
>             signal_score += contrib
>             signal_breakdown["EMA_Alignment"] = contrib
>         return signal_score, signal_breakdown
2179,2186c1940,1943
<         # --- Ichimoku Cloud Alignment Scoring ---
<         if active_indicators.get("ichimoku_cloud", False):
<             tenkan_sen = self._get_indicator_value("Tenkan_Sen")
<             kijun_sen = self._get_indicator_value("Kijun_Sen")
<             senkou_span_a = self._get_indicator_value("Senkou_Span_A")
<             senkou_span_b = self._get_indicator_value("Senkou_Span_B")
<             chikou_span = self._get_indicator_value("Chikou_Span")
<             weight = weights.get("ichimoku_confluence", 0.0)
---
>     def _score_sma_trend_filter(self, signal_score: float, signal_breakdown: dict, current_close: Decimal) -> tuple[float, dict]:
>         """Scores SMA trend filter."""
>         if not self.config["indicators"].get("sma_trend_filter", False):
>             return signal_score, signal_breakdown
2188,2213c1945,1946
<             if (
<                 not pd.isna(tenkan_sen)
<                 and not pd.isna(kijun_sen)
<                 and not pd.isna(senkou_span_a)
<                 and not pd.isna(senkou_span_b)
<                 and not pd.isna(chikou_span)
<                 and len(self.df) > 1
<             ):
<                 contrib = 0.0
<                 # Tenkan-sen / Kijun-sen crossover
<                 if (
<                     tenkan_sen > kijun_sen
<                     and self.df["Tenkan_Sen"].iloc[-2] <= self.df["Kijun_Sen"].iloc[-2]
<                 ):
<                     contrib += weight * 0.5 # Bullish crossover
<                     self.logger.debug(
<                         "Ichimoku: Tenkan-sen crossed above Kijun-sen (bullish)."
<                     )
<                 elif (
<                     tenkan_sen < kijun_sen
<                     and self.df["Tenkan_Sen"].iloc[-2] >= self.df["Kijun_Sen"].iloc[-2]
<                 ):
<                     contrib -= weight * 0.5 # Bearish crossover
<                     self.logger.debug(
<                         "Ichimoku: Tenkan-sen crossed below Kijun-sen (bearish)."
<                     )
---
>         sma_long = self._get_indicator_value("SMA_Long")
>         weight = self.weights.get("sma_trend_filter", 0)
2215,2253c1948,1956
<                 # Price breaking above/below Kumo (cloud)
<                 if current_close > max(senkou_span_a, senkou_span_b) and self.df[
<                     "close"
<                 ].iloc[-2] <= max(
<                     self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]
<                 ):
<                     contrib += weight * 0.7 # Strong bullish breakout
<                     self.logger.debug(
<                         "Ichimoku: Price broke above Kumo (strong bullish)."
<                     )
<                 elif current_close < min(senkou_span_a, senkou_span_b) and self.df[
<                     "close"
<                 ].iloc[-2] >= min(
<                     self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]
<                 ):
<                     contrib -= weight * 0.7 # Strong bearish breakdown
<                     self.logger.debug(
<                         "Ichimoku: Price broke below Kumo (strong bearish)."
<                     )
< 
<                 # Chikou Span crossover with price
<                 if (
<                     chikou_span > current_close
<                     and self.df["Chikou_Span"].iloc[-2] <= self.df["close"].iloc[-2]
<                 ):
<                     contrib += weight * 0.3 # Bullish confirmation
<                     self.logger.debug(
<                         "Ichimoku: Chikou Span crossed above price (bullish confirmation)."
<                     )
<                 elif (
<                     chikou_span < current_close
<                     and self.df["Chikou_Span"].iloc[-2] >= self.df["close"].iloc[-2]
<                 ):
<                     contrib -= weight * 0.3 # Bearish confirmation
<                     self.logger.debug(
<                         "Ichimoku: Chikou Span crossed below price (bearish confirmation)."
<                     )
<                 signal_score += contrib
<                 signal_breakdown["Ichimoku_Confluence"] = contrib
---
>         if not pd.isna(sma_long) and weight > 0:
>             contrib = 0.0
>             if current_close > sma_long:
>                 contrib = weight
>             elif current_close < sma_long:
>                 contrib = -weight
>             signal_score += contrib
>             signal_breakdown["SMA_Trend_Filter"] = contrib
>         return signal_score, signal_breakdown
2255,2259c1958,1961
<         # --- OBV Alignment Scoring ---
<         if active_indicators.get("obv", False):
<             obv_val = self._get_indicator_value("OBV")
<             obv_ema = self._get_indicator_value("OBV_EMA")
<             weight = weights.get("obv_momentum", 0.0)
---
>     def _score_momentum(self, signal_score: float, signal_breakdown: dict, current_close: Decimal, prev_close: Decimal) -> tuple[float, dict]:
>         """Scores momentum indicators (RSI, StochRSI, CCI, WR, MFI)."""
>         if not self.config["indicators"].get("momentum", False):
>             return signal_score, signal_breakdown
2261,2290c1963,1964
<             if not pd.isna(obv_val) and not pd.isna(obv_ema) and len(self.df) > 1:
<                 contrib = 0.0
<                 # OBV crossing its EMA
<                 if (
<                     obv_val > obv_ema
<                     and self.df["OBV"].iloc[-2] <= self.df["OBV_EMA"].iloc[-2]
<                 ):
<                     contrib = weight * 0.5 # Bullish crossover
<                     self.logger.debug("OBV: Bullish crossover detected.")
<                 elif (
<                     obv_val < obv_ema
<                     and self.df["OBV"].iloc[-2] >= self.df["OBV_EMA"].iloc[-2]
<                 ):
<                     contrib = -weight * 0.5 # Bearish crossover
<                     self.logger.debug("OBV: Bearish crossover detected.")
< 
<                 # OBV trend confirmation (e.g., higher highs/lower lows)
<                 if len(self.df) > 2:
<                     if (
<                         obv_val > self.df["OBV"].iloc[-2]
<                         and obv_val > self.df["OBV"].iloc[-3]
<                     ):
<                         contrib += weight * 0.2 # OBV making higher highs
<                     elif (
<                         obv_val < self.df["OBV"].iloc[-2]
<                         and obv_val < self.df["OBV"].iloc[-3]
<                     ):
<                         contrib -= weight * 0.2 # OBV making lower lows
<                 signal_score += contrib
<                 signal_breakdown["OBV_Momentum"] = contrib
---
>         momentum_weight = self.weights.get("momentum_rsi_stoch_cci_wr_mfi", 0)
>         if momentum_weight == 0: return signal_score, signal_breakdown
2292,2295c1966
<         # --- CMF Alignment Scoring ---
<         if active_indicators.get("cmf", False):
<             cmf_val = self._get_indicator_value("CMF")
<             weight = weights.get("cmf_flow", 0.0)
---
>         isd = self.indicator_settings
2297,2316c1968,1998
<             if not pd.isna(cmf_val):
<                 contrib = 0.0
<                 # CMF above/below zero line
<                 if cmf_val > 0:
<                     contrib = weight * 0.5 # Bullish money flow
<                 elif cmf_val < 0:
<                     contrib = -weight * 0.5 # Bearish money flow
< 
<                 # CMF trend confirmation
<                 if len(self.df) > 2:
<                     if (
<                         cmf_val > self.df["CMF"].iloc[-2]
<                         and cmf_val > self.df["CMF"].iloc[-3]
<                     ):
<                         contrib += weight * 0.3 # CMF making higher highs
<                     elif (
<                         cmf_val < self.df["CMF"].iloc[-2]
<                         and cmf_val < self.df["CMF"].iloc[-3]
<                     ):
<                         contrib -= weight * 0.3 # CMF making lower lows
---
>         # RSI
>         if self.config["indicators"].get("rsi", False):
>             rsi = self._get_indicator_value("RSI")
>             if not pd.isna(rsi):
>                 # Normalize RSI to a -1 to +1 scale (50 is neutral)
>                 normalized_rsi = (float(rsi) - 50) / 50
>                 contrib = normalized_rsi * momentum_weight * 0.5 # Assign a portion of momentum weight
>                 signal_score += contrib
>                 signal_breakdown["RSI_Signal"] = contrib
> 
>         # StochRSI Crossover
>         if self.config["indicators"].get("stoch_rsi", False):
>             stoch_k = self._get_indicator_value("StochRSI_K")
>             stoch_d = self._get_indicator_value("StochRSI_D")
>             if not pd.isna(stoch_k) and not pd.isna(stoch_d) and len(self.df) > 1:
>                 prev_stoch_k = self.df["StochRSI_K"].iloc[-2]
>                 prev_stoch_d = self.df["StochRSI_D"].iloc[-2]
>                 contrib = 0.0
>                 # Bullish crossover from oversold
>                 if (stoch_k > stoch_d and prev_stoch_k <= prev_stoch_d and stoch_k < isd["stoch_rsi_oversold"]):
>                     contrib = momentum_weight * 0.6
>                     self.logger.debug(f"[{self.symbol}] StochRSI: Bullish crossover from oversold.")
>                 # Bearish crossover from overbought
>                 elif (stoch_k < stoch_d and prev_stoch_k >= prev_stoch_d and stoch_k > isd["stoch_rsi_overbought"]):
>                     contrib = -momentum_weight * 0.6
>                     self.logger.debug(f"[{self.symbol}] StochRSI: Bearish crossover from overbought.")
>                 # General momentum based on K line position relative to D line and midpoint
>                 elif stoch_k > stoch_d and stoch_k < 50: # General bullish momentum
>                     contrib = momentum_weight * 0.2
>                 elif stoch_k < stoch_d and stoch_k > 50: # General bearish momentum
>                     contrib = -momentum_weight * 0.2
2318c2000
<                 signal_breakdown["CMF_Flow"] = contrib
---
>                 signal_breakdown["StochRSI_Signal"] = contrib
2320,2341c2002,2012
<         # --- Volatility Index Scoring ---
<         if active_indicators.get("volatility_index", False):
<             vol_idx = self._get_indicator_value("Volatility_Index")
<             weight = weights.get("volatility_index_signal", 0.0)
<             if not pd.isna(vol_idx):
<                 contrib = 0.0
<                 if len(self.df) > 2 and "Volatility_Index" in self.df.columns:
<                     prev_vol_idx = self.df["Volatility_Index"].iloc[-2]
<                     prev_prev_vol_idx = self.df["Volatility_Index"].iloc[-3]
< 
<                     if vol_idx > prev_vol_idx > prev_prev_vol_idx:  # Increasing volatility
<                         # Increasing volatility can amplify existing signals
<                         if signal_score > 0:
<                             contrib = weight * 0.2
<                         elif signal_score < 0:
<                             contrib = -weight * 0.2
<                         self.logger.debug("Volatility Index: Increasing volatility.")
<                     elif vol_idx < prev_vol_idx < prev_prev_vol_idx: # Decreasing volatility
<                         # Decreasing volatility might reduce confidence in strong signals
<                         if abs(signal_score) > 0: # If there's an existing signal, slightly reduce it
<                              contrib = signal_score * -0.2 # Reduce score by 20% (example)
<                         self.logger.debug("Volatility Index: Decreasing volatility.")
---
>         # CCI
>         if self.config["indicators"].get("cci", False):
>             cci = self._get_indicator_value("CCI")
>             if not pd.isna(cci):
>                 # Normalize CCI (assuming typical range of -200 to 200, normalize to -1 to +1)
>                 normalized_cci = float(cci) / 200
>                 contrib = 0.0
>                 if cci < isd["cci_oversold"]:
>                     contrib = momentum_weight * 0.4
>                 elif cci > isd["cci_overbought"]:
>                     contrib = -momentum_weight * 0.4
2343c2014
<                 signal_breakdown["Volatility_Index_Signal"] = contrib
---
>                 signal_breakdown["CCI_Signal"] = contrib
2345,2358c2016,2026
<         # --- VWMA Cross Scoring ---
<         if active_indicators.get("vwma", False):
<             vwma = self._get_indicator_value("VWMA")
<             weight = weights.get("vwma_cross", 0.0)
<             if not pd.isna(vwma) and len(self.df) > 1:
<                 prev_vwma = self.df["VWMA"].iloc[-2]
<                 contrib = 0.0
<                 # Price crossing VWMA
<                 if current_close > vwma and prev_close <= prev_vwma:
<                     contrib = weight # Bullish crossover
<                     self.logger.debug("VWMA: Bullish crossover (price above VWMA).")
<                 elif current_close < vwma and prev_close >= prev_vwma:
<                     contrib = -weight # Bearish crossover
<                     self.logger.debug("VWMA: Bearish crossover (price below VWMA).")
---
>         # Williams %R
>         if self.config["indicators"].get("wr", False):
>             wr = self._get_indicator_value("WR")
>             if not pd.isna(wr):
>                 # Normalize WR to -1 to +1 scale (-100 to 0, so (WR + 50) / 50)
>                 normalized_wr = (float(wr) + 50) / 50
>                 contrib = 0.0
>                 if wr < isd["williams_r_oversold"]:
>                     contrib = momentum_weight * 0.4
>                 elif wr > isd["williams_r_overbought"]:
>                     contrib = -momentum_weight * 0.4
2360c2028
<                 signal_breakdown["VWMA_Cross"] = contrib
---
>                 signal_breakdown["WR_Signal"] = contrib
2362,2366c2030,2053
<         # --- Volume Delta Scoring ---
<         if active_indicators.get("volume_delta", False):
<             volume_delta = self._get_indicator_value("Volume_Delta")
<             volume_delta_threshold = isd["volume_delta_threshold"]
<             weight = weights.get("volume_delta_signal", 0.0)
---
>         # MFI
>         if self.config["indicators"].get("mfi", False):
>             mfi = self._get_indicator_value("MFI")
>             if not pd.isna(mfi):
>                 # Normalize MFI to -1 to +1 scale (0 to 100, so (MFI - 50) / 50)
>                 normalized_mfi = (float(mfi) - 50) / 50
>                 contrib = 0.0
>                 if mfi < isd["mfi_oversold"]:
>                     contrib = momentum_weight * 0.4
>                 elif mfi > isd["mfi_overbought"]:
>                     contrib = -momentum_weight * 0.4
>                 signal_score += contrib
>                 signal_breakdown["MFI_Signal"] = contrib
> 
>         return signal_score, signal_breakdown
> 
>     def _score_bollinger_bands(self, signal_score: float, signal_breakdown: dict, current_close: Decimal) -> tuple[float, dict]:
>         """Scores Bollinger Bands."""
>         if not self.config["indicators"].get("bollinger_bands", False):
>             return signal_score, signal_breakdown
> 
>         bb_upper = self._get_indicator_value("BB_Upper")
>         bb_lower = self._get_indicator_value("BB_Lower")
>         weight = self.weights.get("bollinger_bands", 0)
2368,2382c2055,2063
<             if not pd.isna(volume_delta):
<                 contrib = 0.0
<                 if volume_delta > volume_delta_threshold:  # Strong buying pressure
<                     contrib = weight
<                     self.logger.debug("Volume Delta: Strong buying pressure detected.")
<                 elif volume_delta < -volume_delta_threshold:  # Strong selling pressure
<                     contrib = -weight
<                     self.logger.debug("Volume Delta: Strong selling pressure detected.")
<                 # Weaker signals for moderate delta
<                 elif volume_delta > 0:
<                     contrib = weight * 0.3
<                 elif volume_delta < 0:
<                     contrib = -weight * 0.3
<                 signal_score += contrib
<                 signal_breakdown["Volume_Delta_Signal"] = contrib
---
>         if not pd.isna(bb_upper) and not pd.isna(bb_lower) and weight > 0:
>             contrib = 0.0
>             if current_close < bb_lower: # Price below lower band - potential buy signal
>                 contrib = weight * 0.5
>             elif current_close > bb_upper: # Price above upper band - potential sell signal
>                 contrib = -weight * 0.5
>             signal_score += contrib
>             signal_breakdown["Bollinger_Bands_Signal"] = contrib
>         return signal_score, signal_breakdown
2383a2065,2068
>     def _score_vwap(self, signal_score: float, signal_breakdown: dict, current_close: Decimal, prev_close: Decimal) -> tuple[float, dict]:
>         """Scores VWAP."""
>         if not self.config["indicators"].get("vwap", False):
>             return signal_score, signal_breakdown
2385,2393c2070,2071
<         # --- Multi-Timeframe Trend Confluence Scoring ---
<         if self.config["mtf_analysis"]["enabled"] and mtf_trends:
<             mtf_buy_score = 0
<             mtf_sell_score = 0
<             for _tf_indicator, trend in mtf_trends.items():
<                 if trend == "UP":
<                     mtf_buy_score += 1
<                 elif trend == "DOWN":
<                     mtf_sell_score += 1
---
>         vwap = self._get_indicator_value("VWAP")
>         weight = self.weights.get("vwap", 0)
2395c2073
<             mtf_weight = weights.get("mtf_trend_confluence", 0.0)
---
>         if not pd.isna(vwap) and weight > 0:
2397,2405c2075,2090
<             if mtf_trends:
<                 # Calculate a normalized score based on the balance of buy/sell trends
<                 normalized_mtf_score = (mtf_buy_score - mtf_sell_score) / len(
<                     mtf_trends
<                 )
<                 contrib = mtf_weight * normalized_mtf_score
<                 self.logger.debug(
<                     f"MTF Confluence: Score {normalized_mtf_score:.2f} (Buy: {mtf_buy_score}, Sell: {mtf_sell_score}). Total MTF contribution: {mtf_weight * normalized_mtf_score:.2f}"
<                 )
---
>             # Basic score based on price relative to VWAP
>             if current_close > vwap:
>                 contrib = weight * 0.2
>             elif current_close < vwap:
>                 contrib = -weight * 0.2
> 
>             # Add score for VWAP crossover if available
>             if len(self.df) > 1:
>                 prev_vwap = Decimal(str(self.df["VWAP"].iloc[-2]))
>                 # VWAP crossover
>                 if (current_close > vwap and prev_close <= prev_vwap):
>                     contrib += weight * 0.3
>                     self.logger.debug(f"[{self.symbol}] VWAP: Bullish crossover detected.")
>                 elif (current_close < vwap and prev_close >= prev_vwap):
>                     contrib -= weight * 0.3
>                     self.logger.debug(f"[{self.symbol}] VWAP: Bearish crossover detected.")
2407,2412c2092,2093
<             signal_breakdown["MTF_Trend_Confluence"] = contrib
< 
<         # --- Final Signal Determination with Hysteresis and Cooldown ---
<         threshold = self.config["signal_score_threshold"]
<         cooldown_sec = self.config["cooldown_sec"]
<         hysteresis_ratio = self.config["hysteresis_ratio"]
---
>             signal_breakdown["VWAP_Signal"] = contrib
>         return signal_score, signal_breakdown
2414,2415c2095,2102
<         final_signal = "HOLD"
<         now_ts = int(time.time())
---
>     def _score_psar(self, signal_score: float, signal_breakdown: dict, current_close: Decimal, prev_close: Decimal) -> tuple[float, dict]:
>         """Scores PSAR."""
>         if not self.config["indicators"].get("psar", False):
>             return signal_score, signal_breakdown
> 
>         psar_val = self._get_indicator_value("PSAR_Val")
>         psar_dir = self._get_indicator_value("PSAR_Dir")
>         weight = self.weights.get("psar", 0)
2417,2418c2104,2123
<         is_strong_buy = signal_score >= threshold
<         is_strong_sell = signal_score <= -threshold
---
>         if not pd.isna(psar_val) and not pd.isna(psar_dir) and weight > 0:
>             contrib = 0.0
>             # PSAR direction is a primary signal
>             if psar_dir == 1: # Bullish PSAR
>                 contrib = weight * 0.5
>             elif psar_dir == -1: # Bearish PSAR
>                 contrib = -weight * 0.5
> 
>             # PSAR crossover with price adds confirmation
>             if len(self.df) > 1:
>                 prev_psar_val = Decimal(str(self.df["PSAR_Val"].iloc[-2]))
>                 if (current_close > psar_val and prev_close <= prev_psar_val):
>                     contrib += weight * 0.4 # Additional bullish weight on crossover
>                     self.logger.debug(f"[{self.symbol}] PSAR: Bullish reversal detected.")
>                 elif (current_close < psar_val and prev_close >= prev_psar_val):
>                     contrib -= weight * 0.4 # Additional bearish weight on crossover
>                     self.logger.debug(f"[{self.symbol}] PSAR: Bearish reversal detected.")
>             signal_score += contrib
>             signal_breakdown["PSAR_Signal"] = contrib
>         return signal_score, signal_breakdown
2420,2431c2125,2128
<         # Apply hysteresis to prevent immediate flip-flops
<         # If the bot previously issued a BUY signal and the current score is not a strong SELL, and not a strong BUY, it holds the BUY signal.
<         # This prevents it from flipping to HOLD or SELL too quickly if the score dips slightly.
<         if self._last_signal_score > 0 and signal_score > -threshold * hysteresis_ratio and not is_strong_buy:
<             final_signal = "BUY"
<         # If the bot previously issued a SELL signal and the current score is not a strong BUY, and not a strong SELL, it holds the SELL signal.
<         elif self._last_signal_score < 0 and signal_score < threshold * hysteresis_ratio and not is_strong_sell:
<             final_signal = "SELL"
<         elif is_strong_buy:
<             final_signal = "BUY"
<         elif is_strong_sell:
<             final_signal = "SELL"
---
>     def _score_orderbook_imbalance(self, signal_score: float, signal_breakdown: dict, orderbook_data: dict | None) -> tuple[float, dict]:
>         """Scores orderbook imbalance."""
>         if not self.config["indicators"].get("orderbook_imbalance", False) or not orderbook_data:
>             return signal_score, signal_breakdown
2433,2439c2130,2131
<         # Apply cooldown period
<         if final_signal != "HOLD":
<             if now_ts - self._last_signal_ts < cooldown_sec:
<                 self.logger.info(f"{NEON_YELLOW}Signal '{final_signal}' ignored due to cooldown ({cooldown_sec - (now_ts - self._last_signal_ts)}s remaining).{RESET}")
<                 final_signal = "HOLD"
<             else:
<                 self._last_signal_ts = now_ts # Update timestamp only if signal is issued
---
>         imbalance = self._check_orderbook(Decimal(0), orderbook_data) # Price not used in imbalance calculation here
>         weight = self.weights.get("orderbook_imbalance", 0)
2441,2442c2133,2137
<         # Update last signal score for next iteration's hysteresis
<         self._last_signal_score = signal_score
---
>         if weight > 0:
>             contrib = imbalance * weight
>             signal_score += contrib
>             signal_breakdown["Orderbook_Imbalance"] = contrib
>         return signal_score, signal_breakdown
2444,2445c2139,2177
<         self.logger.info(
<             f"{NEON_YELLOW}Raw Signal Score: {signal_score:.2f}, Final Signal: {final_signal}{RESET}"
---
>     def _score_fibonacci_levels(self, signal_score: float, signal_breakdown: dict, current_close: Decimal, prev_close: Decimal) -> tuple[float, dict]:
>         """Scores Fibonacci levels confluence."""
>         if not self.config["indicators"].get("fibonacci_levels", False) or not self.fib_levels:
>             return signal_score, signal_breakdown
> 
>         weight = self.weights.get("fibonacci_levels", 0)
>         if weight == 0: return signal_score, signal_breakdown
> 
>         contrib = 0.0
>         for level_name, level_price in self.fib_levels.items():
>             # Check if price is near a Fibonacci level (within 0.1% of current price)
>             # Ensure current_close is not zero to avoid division by zero
>             if current_close != 0 and \
>                level_name not in ["0.0%", "100.0%"] and \
>                abs(current_close - level_price) / current_close < Decimal("0.001"):
>                     self.logger.debug(
>                         f"[{self.symbol}] Price near Fibonacci level {level_name}: {level_price}. Current close: {current_close}"
>                     )
>                     # Price crossing the level can act as support/resistance
>                     if len(self.df) > 1:
>                         if (current_close > prev_close and current_close > level_price): # Bullish breakout above level
>                             contrib += weight * 0.1
>                         elif (current_close < prev_close and current_close < level_price): # Bearish breakdown below level
>                             contrib -= weight * 0.1
>         signal_score += contrib
>         signal_breakdown["Fibonacci_Levels_Signal"] = contrib
>         return signal_score, signal_breakdown
> 
>     def _score_ehlers_supertrend(self, signal_score: float, signal_breakdown: dict) -> tuple[float, dict]:
>         """Scores Ehlers SuperTrend alignment."""
>         if not self.config["indicators"].get("ehlers_supertrend", False):
>             return signal_score, signal_breakdown
> 
>         st_fast_dir = self._get_indicator_value("ST_Fast_Dir")
>         st_slow_dir = self._get_indicator_value("ST_Slow_Dir")
>         prev_st_fast_dir = (
>             self.df["st_fast_dir"].iloc[-2]
>             if "st_fast_dir" in self.df.columns and len(self.df) > 1
>             else np.nan
2447c2179
<         return final_signal, signal_score, signal_breakdown
---
>         weight = self.weights.get("ehlers_supertrend_alignment", 0)
2449,2469c2181,2208
<         # PSAR
<         if active_indicators.get("psar", False):
<             psar_val = self._get_indicator_value("PSAR_Val")
<             psar_dir = self._get_indicator_value("PSAR_Dir")
<             if not pd.isna(psar_val) and not pd.isna(psar_dir):
<                 contrib = 0.0
<                 if psar_dir == 1:
<                     contrib = weights.get("psar", 0) * 0.5
<                 elif psar_dir == -1:
<                     contrib = -weights.get("psar", 0) * 0.5
< 
<                 if len(self.df) > 1:
<                     prev_psar_val = Decimal(str(self.df["PSAR_Val"].iloc[-2]))
<                     if (current_close > psar_val and prev_close <= prev_psar_val):
<                         contrib += weights.get("psar", 0) * 0.4
<                         self.logger.debug("PSAR: Bullish reversal detected.")
<                     elif (current_close < psar_val and prev_close >= prev_psar_val):
<                         contrib -= weights.get("psar", 0) * 0.4
<                         self.logger.debug("PSAR: Bearish reversal detected.")
<                 signal_score += contrib
<                 signal_breakdown["PSAR_Signal"] = contrib
---
>         if not pd.isna(st_fast_dir) and not pd.isna(st_slow_dir) and not pd.isna(prev_st_fast_dir) and weight > 0:
>             contrib = 0.0
>             # Strong buy signal: fast ST flips up and aligns with slow ST (which is also up)
>             if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1:
>                 contrib = weight
>                 self.logger.debug(f"[{self.symbol}] Ehlers SuperTrend: Strong BUY signal (fast flip aligned with slow trend).")
>             # Strong sell signal: fast ST flips down and aligns with slow ST (which is also down)
>             elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1:
>                 contrib = -weight
>                 self.logger.debug(f"[{self.symbol}] Ehlers SuperTrend: Strong SELL signal (fast flip aligned with slow trend).")
>             # General alignment: both fast and slow ST are in the same direction
>             elif st_slow_dir == 1 and st_fast_dir == 1:
>                 contrib = weight * 0.3
>             elif st_slow_dir == -1 and st_fast_dir == -1:
>                 contrib = -weight * 0.3
>             signal_score += contrib
>             signal_breakdown["Ehlers_SuperTrend_Alignment"] = contrib
>         return signal_score, signal_breakdown
> 
>     def _score_macd(self, signal_score: float, signal_breakdown: dict) -> tuple[float, dict]:
>         """Scores MACD alignment."""
>         if not self.config["indicators"].get("macd", False):
>             return signal_score, signal_breakdown
> 
>         macd_line = self._get_indicator_value("MACD_Line")
>         signal_line = self._get_indicator_value("MACD_Signal")
>         histogram = self._get_indicator_value("MACD_Hist")
>         weight = self.weights.get("macd_alignment", 0)
2471,2474c2210,2224
<         # Orderbook Imbalance
<         if active_indicators.get("orderbook_imbalance", False) and orderbook_data:
<             imbalance = self._check_orderbook(current_price, orderbook_data)
<             contrib = imbalance * weights.get("orderbook_imbalance", 0)
---
>         if (not pd.isna(macd_line) and not pd.isna(signal_line) and not pd.isna(histogram) and len(self.df) > 1 and weight > 0):
>             contrib = 0.0
>             # Bullish crossover: MACD line crosses above Signal line
>             if (macd_line > signal_line and self.df["MACD_Line"].iloc[-2] <= self.df["MACD_Signal"].iloc[-2]):
>                 contrib = weight
>                 self.logger.debug(f"[{self.symbol}] MACD: BUY signal (MACD line crossed above Signal line).")
>             # Bearish crossover: MACD line crosses below Signal line
>             elif (macd_line < signal_line and self.df["MACD_Line"].iloc[-2] >= self.df["MACD_Signal"].iloc[-2]):
>                 contrib = -weight
>                 self.logger.debug(f"[{self.symbol}] MACD: SELL signal (MACD line crossed below Signal line).")
>             # Histogram turning positive/negative from zero line
>             elif histogram > 0 and self.df["MACD_Hist"].iloc[-2] < 0:
>                 contrib = weight * 0.2
>             elif histogram < 0 and self.df["MACD_Hist"].iloc[-2] > 0:
>                 contrib = -weight * 0.2
2476c2226,2227
<             signal_breakdown["Orderbook_Imbalance"] = contrib
---
>             signal_breakdown["MACD_Alignment"] = contrib
>         return signal_score, signal_breakdown
2478,2504c2229,2240
<         # Fibonacci Levels (confluence with price action)
<         if active_indicators.get("fibonacci_levels", False) and self.fib_levels:
<             for level_name, level_price in self.fib_levels.items():
<                 if (level_name not in ["0.0%", "100.0%"] and
<                     abs(current_price - level_price) / current_price < Decimal("0.001")):
<                         self.logger.debug(
<                             f"Price near Fibonacci level {level_name}: {level_price}"
<                         )
<                         contrib = 0.0
<                         if len(self.df) > 1:
<                             if (current_close > prev_close and current_close > level_price):
<                                 contrib = weights.get("fibonacci_levels", 0) * 0.1
<                             elif (current_close < prev_close and current_close < level_price):
<                                 contrib = -weights.get("fibonacci_levels", 0) * 0.1
<                         signal_score += contrib
<                         signal_breakdown["Fibonacci_Levels_Signal"] = contrib
< 
<         # --- Ehlers SuperTrend Alignment Scoring ---
<         if active_indicators.get("ehlers_supertrend", False):
<             st_fast_dir = self._get_indicator_value("ST_Fast_Dir")
<             st_slow_dir = self._get_indicator_value("ST_Slow_Dir")
<             prev_st_fast_dir = (
<                 self.df["st_fast_dir"].iloc[-2]
<                 if "st_fast_dir" in self.df.columns and len(self.df) > 1
<                 else np.nan
<             )
<             weight = weights.get("ehlers_supertrend_alignment", 0.0)
---
>     def _score_adx(self, signal_score: float, signal_breakdown: dict) -> tuple[float, dict]:
>         """Scores ADX strength."""
>         if not self.config["indicators"].get("adx", False):
>             return signal_score, signal_breakdown
> 
>         adx_val = self._get_indicator_value("ADX")
>         plus_di = self._get_indicator_value("PlusDI")
>         minus_di = self._get_indicator_value("MinusDI")
>         weight = self.weights.get("adx_strength", 0)
>         # Retrieve thresholds from indicator_settings for better configuration
>         ADX_STRONG_TREND_THRESHOLD = self.indicator_settings.get("ADX_STRONG_TREND_THRESHOLD", 25)
>         ADX_WEAK_TREND_THRESHOLD = self.indicator_settings.get("ADX_WEAK_TREND_THRESHOLD", 20)
2506,2512c2242,2246
<             if (
<                 not pd.isna(st_fast_dir)
<                 and not pd.isna(st_slow_dir)
<                 and not pd.isna(prev_st_fast_dir)
<             ):
<                 contrib = 0.0
<                 if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1:
---
>         if not pd.isna(adx_val) and not pd.isna(plus_di) and not pd.isna(minus_di) and weight > 0:
>             contrib = 0.0
>             # Strong trend confirmation
>             if adx_val > ADX_STRONG_TREND_THRESHOLD:
>                 if plus_di > minus_di: # Bullish trend
2514,2517c2248,2249
<                     self.logger.debug(
<                         "Ehlers SuperTrend: Strong BUY signal (fast flip aligned with slow trend)."
<                     )
<                 elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1:
---
>                     self.logger.debug(f"[{self.symbol}] ADX: Strong BUY trend (ADX > {ADX_STRONG_TREND_THRESHOLD}, +DI > -DI).")
>                 elif minus_di > plus_di: # Bearish trend
2519,2527c2251,2257
<                     self.logger.debug(
<                         "Ehlers SuperTrend: Strong SELL signal (fast flip aligned with slow trend)."
<                     )
<                 elif st_slow_dir == 1 and st_fast_dir == 1:
<                     contrib = weight * 0.3
<                 elif st_slow_dir == -1 and st_fast_dir == -1:
<                     contrib = -weight * 0.3
<                 signal_score += contrib
<                 signal_breakdown["Ehlers_SuperTrend_Alignment"] = contrib
---
>                     self.logger.debug(f"[{self.symbol}] ADX: Strong SELL trend (ADX > {ADX_STRONG_TREND_THRESHOLD}, -DI > +DI).")
>             elif adx_val < ADX_WEAK_TREND_THRESHOLD:
>                 contrib = 0 # Neutral signal, no contribution from ADX
>                 self.logger.debug(f"[{self.symbol}] ADX: Weak trend (ADX < {ADX_WEAK_TREND_THRESHOLD}). Neutral signal.")
>             signal_score += contrib
>             signal_breakdown["ADX_Strength"] = contrib
>         return signal_score, signal_breakdown
2529,2534c2259,2306
<         # --- MACD Alignment Scoring ---
<         if active_indicators.get("macd", False):
<             macd_line = self._get_indicator_value("MACD_Line")
<             signal_line = self._get_indicator_value("MACD_Signal")
<             histogram = self._get_indicator_value("MACD_Hist")
<             weight = weights.get("macd_alignment", 0.0)
---
>     def _score_ichimoku_cloud(self, signal_score: float, signal_breakdown: dict, current_close: Decimal, prev_close: Decimal) -> tuple[float, dict]:
>         """Scores Ichimoku Cloud confluence."""
>         if not self.config["indicators"].get("ichimoku_cloud", False):
>             return signal_score, signal_breakdown
> 
>         tenkan_sen = self._get_indicator_value("Tenkan_Sen")
>         kijun_sen = self._get_indicator_value("Kijun_Sen")
>         senkou_span_a = self._get_indicator_value("Senkou_Span_A")
>         senkou_span_b = self._get_indicator_value("Senkou_Span_B")
>         chikou_span = self._get_indicator_value("Chikou_Span")
>         weight = self.weights.get("ichimoku_confluence", 0)
> 
>         if (not pd.isna(tenkan_sen) and not pd.isna(kijun_sen) and
>             not pd.isna(senkou_span_a) and not pd.isna(senkou_span_b) and
>             not pd.isna(chikou_span) and len(self.df) > 1 and weight > 0):
>             contrib = 0.0
>             # Tenkan-sen / Kijun-sen crossover
>             if (tenkan_sen > kijun_sen and self.df["Tenkan_Sen"].iloc[-2] <= self.df["Kijun_Sen"].iloc[-2]):
>                 contrib += weight * 0.5 # Bullish crossover
>                 self.logger.debug(f"[{self.symbol}] Ichimoku: Tenkan-sen crossed above Kijun-sen (bullish).")
>             elif (tenkan_sen < kijun_sen and self.df["Tenkan_Sen"].iloc[-2] >= self.df["Kijun_Sen"].iloc[-2]):
>                 contrib -= weight * 0.5 # Bearish crossover
>                 self.logger.debug(f"[{self.symbol}] Ichimoku: Tenkan-sen crossed below Kijun-sen (bearish).")
> 
>             # Price breaking above/below Kumo (cloud)
>             kumo_high = max(senkou_span_a, senkou_span_b)
>             kumo_low = min(senkou_span_a, senkou_span_b)
>             # Get previous kumo values, handle potential NaNs if data is sparse
>             prev_kumo_high = max(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]) if len(self.df) > 1 else kumo_high
>             prev_kumo_low = min(self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]) if len(self.df) > 1 else kumo_low
> 
>             if (current_close > kumo_high and self.df["close"].iloc[-2] <= prev_kumo_high):
>                 contrib += weight * 0.7 # Strong bullish breakout
>                 self.logger.debug(f"[{self.symbol}] Ichimoku: Price broke above Kumo (strong bullish).")
>             elif (current_close < kumo_low and self.df["close"].iloc[-2] >= prev_kumo_low):
>                 contrib -= weight * 0.7 # Strong bearish breakdown
>                 self.logger.debug(f"[{self.symbol}] Ichimoku: Price broke below Kumo (strong bearish).")
> 
>             # Chikou Span crossover with price
>             if (chikou_span > current_close and self.df["Chikou_Span"].iloc[-2] <= self.df["close"].iloc[-2]):
>                 contrib += weight * 0.3 # Bullish confirmation
>                 self.logger.debug(f"[{self.symbol}] Ichimoku: Chikou Span crossed above price (bullish confirmation).")
>             elif (chikou_span < current_close and self.df["Chikou_Span"].iloc[-2] >= self.df["close"].iloc[-2]):
>                 contrib -= weight * 0.3 # Bearish confirmation
>                 self.logger.debug(f"[{self.symbol}] Ichimoku: Chikou Span crossed below price (bearish confirmation).")
>             signal_score += contrib
>             signal_breakdown["Ichimoku_Confluence"] = contrib
>         return signal_score, signal_breakdown
2536,2564c2308,2315
<             if (
<                 not pd.isna(macd_line)
<                 and not pd.isna(signal_line)
<                 and not pd.isna(histogram)
<                 and len(self.df) > 1
<             ):
<                 contrib = 0.0
<                 if (
<                     macd_line > signal_line
<                     and self.df["MACD_Line"].iloc[-2] <= self.df["MACD_Signal"].iloc[-2]
<                 ):
<                     contrib = weight
<                     self.logger.debug(
<                         "MACD: BUY signal (MACD line crossed above Signal line)."
<                     )
<                 elif (
<                     macd_line < signal_line
<                     and self.df["MACD_Line"].iloc[-2] >= self.df["MACD_Signal"].iloc[-2]
<                 ):
<                     contrib = -weight
<                     self.logger.debug(
<                         "MACD: SELL signal (MACD line crossed below Signal line)."
<                     )
<                 elif histogram > 0 and self.df["MACD_Hist"].iloc[-2] < 0:
<                     contrib = weight * 0.2
<                 elif histogram < 0 and self.df["MACD_Hist"].iloc[-2] > 0:
<                     contrib = -weight * 0.2
<                 signal_score += contrib
<                 signal_breakdown["MACD_Alignment"] = contrib
---
>     def _score_obv(self, signal_score: float, signal_breakdown: dict) -> tuple[float, dict]:
>         """Scores OBV momentum."""
>         if not self.config["indicators"].get("obv", False):
>             return signal_score, signal_breakdown
> 
>         obv_val = self._get_indicator_value("OBV")
>         obv_ema = self._get_indicator_value("OBV_EMA")
>         weight = self.weights.get("obv_momentum", 0)
2566,2571c2317,2335
<         # --- ADX Alignment Scoring ---
<         if active_indicators.get("adx", False):
<             adx_val = self._get_indicator_value("ADX")
<             plus_di = self._get_indicator_value("PlusDI")
<             minus_di = self._get_indicator_value("MinusDI")
<             weight = weights.get("adx_strength", 0.0)
---
>         if not pd.isna(obv_val) and not pd.isna(obv_ema) and len(self.df) > 1 and weight > 0:
>             contrib = 0.0
>             # OBV crossing its EMA
>             if (obv_val > obv_ema and self.df["OBV"].iloc[-2] <= self.df["OBV_EMA"].iloc[-2]):
>                 contrib = weight * 0.5 # Bullish crossover
>                 self.logger.debug(f"[{self.symbol}] OBV: Bullish crossover detected.")
>             elif (obv_val < obv_ema and self.df["OBV"].iloc[-2] >= self.df["OBV_EMA"].iloc[-2]):
>                 contrib = -weight * 0.5 # Bearish crossover
>                 self.logger.debug(f"[{self.symbol}] OBV: Bearish crossover detected.")
> 
>             # OBV trend confirmation (simplified: check if current OBV is higher/lower than previous two)
>             if len(self.df) > 2:
>                 if (obv_val > self.df["OBV"].iloc[-2] and obv_val > self.df["OBV"].iloc[-3]):
>                     contrib += weight * 0.2 # OBV making higher highs
>                 elif (obv_val < self.df["OBV"].iloc[-2] and obv_val < self.df["OBV"].iloc[-3]):
>                     contrib -= weight * 0.2 # OBV making lower lows
>             signal_score += contrib
>             signal_breakdown["OBV_Momentum"] = contrib
>         return signal_score, signal_breakdown
2573,2590c2337,2340
<             if not pd.isna(adx_val) and not pd.isna(plus_di) and not pd.isna(minus_di):
<                 contrib = 0.0
<                 if adx_val > ADX_STRONG_TREND_THRESHOLD:
<                     if plus_di > minus_di:
<                         contrib = weight
<                         self.logger.debug(
<                             "ADX: Strong BUY trend (ADX > 25, +DI > -DI)."
<                         )
<                     elif minus_di > plus_di:
<                         contrib = -weight
<                         self.logger.debug(
<                             "ADX: Strong SELL trend (ADX > 25, -DI > +DI)."
<                         )
<                 elif adx_val < ADX_WEAK_TREND_THRESHOLD:
<                     contrib = 0 # Neutral signal, no contribution
<                     self.logger.debug("ADX: Weak trend (ADX < 20). Neutral signal.")
<                 signal_score += contrib
<                 signal_breakdown["ADX_Strength"] = contrib
---
>     def _score_cmf(self, signal_score: float, signal_breakdown: dict) -> tuple[float, dict]:
>         """Scores CMF flow."""
>         if not self.config["indicators"].get("cmf", False):
>             return signal_score, signal_breakdown
2592,2599c2342,2343
<         # --- Ichimoku Cloud Alignment Scoring ---
<         if active_indicators.get("ichimoku_cloud", False):
<             tenkan_sen = self._get_indicator_value("Tenkan_Sen")
<             kijun_sen = self._get_indicator_value("Kijun_Sen")
<             senkou_span_a = self._get_indicator_value("Senkou_Span_A")
<             senkou_span_b = self._get_indicator_value("Senkou_Span_B")
<             chikou_span = self._get_indicator_value("Chikou_Span")
<             weight = weights.get("ichimoku_confluence", 0.0)
---
>         cmf_val = self._get_indicator_value("CMF")
>         weight = self.weights.get("cmf_flow", 0)
2601,2625c2345,2361
<             if (
<                 not pd.isna(tenkan_sen)
<                 and not pd.isna(kijun_sen)
<                 and not pd.isna(senkou_span_a)
<                 and not pd.isna(senkou_span_b)
<                 and not pd.isna(chikou_span)
<                 and len(self.df) > 1
<             ):
<                 contrib = 0.0
<                 if (
<                     tenkan_sen > kijun_sen
<                     and self.df["Tenkan_Sen"].iloc[-2] <= self.df["Kijun_Sen"].iloc[-2]
<                 ):
<                     contrib += weight * 0.5
<                     self.logger.debug(
<                         "Ichimoku: Tenkan-sen crossed above Kijun-sen (bullish)."
<                     )
<                 elif (
<                     tenkan_sen < kijun_sen
<                     and self.df["Tenkan_Sen"].iloc[-2] >= self.df["Kijun_Sen"].iloc[-2]
<                 ):
<                     contrib -= weight * 0.5
<                     self.logger.debug(
<                         "Ichimoku: Tenkan-sen crossed below Kijun-sen (bearish)."
<                     )
---
>         if not pd.isna(cmf_val) and weight > 0:
>             contrib = 0.0
>             # CMF above/below zero line
>             if cmf_val > 0:
>                 contrib = weight * 0.5 # Bullish money flow
>             elif cmf_val < 0:
>                 contrib = -weight * 0.5 # Bearish money flow
> 
>             # CMF trend confirmation (simplified: check if current CMF is higher/lower than previous two)
>             if len(self.df) > 2:
>                 if (cmf_val > self.df["CMF"].iloc[-2] and cmf_val > self.df["CMF"].iloc[-3]):
>                     contrib += weight * 0.3 # CMF making higher highs
>                 elif (cmf_val < self.df["CMF"].iloc[-2] and cmf_val < self.df["CMF"].iloc[-3]):
>                     contrib -= weight * 0.3 # CMF making lower lows
>             signal_score += contrib
>             signal_breakdown["CMF_Flow"] = contrib
>         return signal_score, signal_breakdown
2627,2644c2363,2366
<                 if current_close > max(senkou_span_a, senkou_span_b) and self.df[
<                     "close"
<                 ].iloc[-2] <= max(
<                     self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]
<                 ):
<                     contrib += weight * 0.7
<                     self.logger.debug(
<                         "Ichimoku: Price broke above Kumo (strong bullish)."
<                     )
<                 elif current_close < min(senkou_span_a, senkou_span_b) and self.df[
<                     "close"
<                 ].iloc[-2] >= min(
<                     self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]
<                 ):
<                     contrib -= weight * 0.7
<                     self.logger.debug(
<                         "Ichimoku: Price broke below Kumo (strong bearish)."
<                     )
---
>     def _score_volatility_index(self, signal_score: float, signal_breakdown: dict) -> tuple[float, dict]:
>         """Scores Volatility Index."""
>         if not self.config["indicators"].get("volatility_index", False):
>             return signal_score, signal_breakdown
2646,2663c2368,2369
<                 if (
<                     chikou_span > current_close
<                     and self.df["Chikou_Span"].iloc[-2] <= self.df["close"].iloc[-2]
<                 ):
<                     contrib += weight * 0.3
<                     self.logger.debug(
<                         "Ichimoku: Chikou Span crossed above price (bullish confirmation)."
<                     )
<                 elif (
<                     chikou_span < current_close
<                     and self.df["Chikou_Span"].iloc[-2] >= self.df["close"].iloc[-2]
<                 ):
<                     contrib -= weight * 0.3
<                     self.logger.debug(
<                         "Ichimoku: Chikou Span crossed below price (bearish confirmation)."
<                     )
<                 signal_score += contrib
<                 signal_breakdown["Ichimoku_Confluence"] = contrib
---
>         vol_idx = self._get_indicator_value("Volatility_Index")
>         weight = self.weights.get("volatility_index_signal", 0)
2665,2669c2371,2391
<         # --- OBV Alignment Scoring ---
<         if active_indicators.get("obv", False):
<             obv_val = self._get_indicator_value("OBV")
<             obv_ema = self._get_indicator_value("OBV_EMA")
<             weight = weights.get("obv_momentum", 0.0)
---
>         if not pd.isna(vol_idx) and weight > 0:
>             contrib = 0.0
>             if len(self.df) > 2 and "Volatility_Index" in self.df.columns:
>                 prev_vol_idx = self.df["Volatility_Index"].iloc[-2]
>                 prev_prev_vol_idx = self.df["Volatility_Index"].iloc[-3]
> 
>                 if vol_idx > prev_vol_idx > prev_prev_vol_idx:  # Increasing volatility
>                     # Increasing volatility can amplify existing signals
>                     if signal_score > 0: # If current score is bullish, amplify it
>                         contrib = weight * 0.2
>                     elif signal_score < 0: # If current score is bearish, amplify it
>                         contrib = -weight * 0.2
>                     self.logger.debug(f"[{self.symbol}] Volatility Index: Increasing volatility.")
>                 elif vol_idx < prev_vol_idx < prev_prev_vol_idx: # Decreasing volatility
>                     # Decreasing volatility might reduce confidence in strong signals
>                     if abs(signal_score) > 0: # If there's an existing signal, slightly reduce its confidence
>                          contrib = signal_score * -0.2 # Reduce score by 20% (example)
>                     self.logger.debug(f"[{self.symbol}] Volatility Index: Decreasing volatility.")
>             signal_score += contrib
>             signal_breakdown["Volatility_Index_Signal"] = contrib
>         return signal_score, signal_breakdown
2671,2698c2393,2396
<             if not pd.isna(obv_val) and not pd.isna(obv_ema) and len(self.df) > 1:
<                 contrib = 0.0
<                 if (
<                     obv_val > obv_ema
<                     and self.df["OBV"].iloc[-2] <= self.df["OBV_EMA"].iloc[-2]
<                 ):
<                     contrib = weight * 0.5
<                     self.logger.debug("OBV: Bullish crossover detected.")
<                 elif (
<                     obv_val < obv_ema
<                     and self.df["OBV"].iloc[-2] >= self.df["OBV_EMA"].iloc[-2]
<                 ):
<                     contrib = -weight * 0.5
<                     self.logger.debug("OBV: Bearish crossover detected.")
< 
<                 if len(self.df) > 2:
<                     if (
<                         obv_val > self.df["OBV"].iloc[-2]
<                         and obv_val > self.df["OBV"].iloc[-3]
<                     ):
<                         contrib += weight * 0.2
<                     elif (
<                         obv_val < self.df["OBV"].iloc[-2]
<                         and obv_val < self.df["OBV"].iloc[-3]
<                     ):
<                         contrib -= weight * 0.2
<                 signal_score += contrib
<                 signal_breakdown["OBV_Momentum"] = contrib
---
>     def _score_vwma(self, signal_score: float, signal_breakdown: dict, current_close: Decimal, prev_close: Decimal) -> tuple[float, dict]:
>         """Scores VWMA cross."""
>         if not self.config["indicators"].get("vwma", False):
>             return signal_score, signal_breakdown
2700,2703c2398,2399
<         # --- CMF Alignment Scoring ---
<         if active_indicators.get("cmf", False):
<             cmf_val = self._get_indicator_value("CMF")
<             weight = weights.get("cmf_flow", 0.0)
---
>         vwma = self._get_indicator_value("VWMA")
>         weight = self.weights.get("vwma_cross", 0)
2705,2724c2401,2413
<             if not pd.isna(cmf_val):
<                 contrib = 0.0
<                 if cmf_val > 0:
<                     contrib = weight * 0.5
<                 elif cmf_val < 0:
<                     contrib = -weight * 0.5
< 
<                 if len(self.df) > 2:
<                     if (
<                         cmf_val > self.df["CMF"].iloc[-2]
<                         and cmf_val > self.df["CMF"].iloc[-3]
<                     ):
<                         contrib += weight * 0.3
<                     elif (
<                         cmf_val < self.df["CMF"].iloc[-2]
<                         and cmf_val < self.df["CMF"].iloc[-3]
<                     ):
<                         contrib -= weight * 0.3
<                 signal_score += contrib
<                 signal_breakdown["CMF_Flow"] = contrib
---
>         if not pd.isna(vwma) and len(self.df) > 1 and weight > 0:
>             prev_vwma = self.df["VWMA"].iloc[-2]
>             contrib = 0.0
>             # Price crossing VWMA
>             if current_close > vwma and prev_close <= prev_vwma:
>                 contrib = weight # Bullish crossover
>                 self.logger.debug(f"[{self.symbol}] VWMA: Bullish crossover (price above VWMA).")
>             elif current_close < vwma and prev_close >= prev_vwma:
>                 contrib = -weight # Bearish crossover
>                 self.logger.debug(f"[{self.symbol}] VWMA: Bearish crossover (price below VWMA).")
>             signal_score += contrib
>             signal_breakdown["VWMA_Cross"] = contrib
>         return signal_score, signal_breakdown
2726,2747c2415,2422
<         # --- Volatility Index Scoring ---
<         if active_indicators.get("volatility_index", False):
<             vol_idx = self._get_indicator_value("Volatility_Index")
<             weight = weights.get("volatility_index_signal", 0.0)
<             if not pd.isna(vol_idx):
<                 contrib = 0.0
<                 if len(self.df) > 2 and "Volatility_Index" in self.df.columns:
<                     prev_vol_idx = self.df["Volatility_Index"].iloc[-2]
<                     prev_prev_vol_idx = self.df["Volatility_Index"].iloc[-3]
< 
<                     if vol_idx > prev_vol_idx > prev_prev_vol_idx:  # Increasing volatility
<                         if signal_score > 0:
<                             contrib = weight * 0.2
<                         elif signal_score < 0:
<                             contrib = -weight * 0.2
<                         self.logger.debug("Volatility Index: Increasing volatility.")
<                     elif vol_idx < prev_vol_idx < prev_prev_vol_idx: # Decreasing volatility
<                         if abs(signal_score) > 0: # If there's an existing signal, slightly reduce it
<                              contrib = signal_score * -0.2 # Reduce score by 20% (example)
<                         self.logger.debug("Volatility Index: Decreasing volatility.")
<                 signal_score += contrib
<                 signal_breakdown["Volatility_Index_Signal"] = contrib
---
>     def _score_volume_delta(self, signal_score: float, signal_breakdown: dict) -> tuple[float, dict]:
>         """Scores Volume Delta."""
>         if not self.config["indicators"].get("volume_delta", False):
>             return signal_score, signal_breakdown
> 
>         volume_delta = self._get_indicator_value("Volume_Delta")
>         volume_delta_threshold = self.indicator_settings.get("volume_delta_threshold", 0.2)
>         weight = self.weights.get("volume_delta_signal", 0)
2749,2763c2424,2439
<         # --- VWMA Cross Scoring ---
<         if active_indicators.get("vwma", False):
<             vwma = self._get_indicator_value("VWMA")
<             weight = weights.get("vwma_cross", 0.0)
<             if not pd.isna(vwma) and len(self.df) > 1:
<                 prev_vwma = self.df["VWMA"].iloc[-2]
<                 contrib = 0.0
<                 if current_close > vwma and prev_close <= prev_vwma:
<                     contrib = weight
<                     self.logger.debug("VWMA: Bullish crossover (price above VWMA).")
<                 elif current_close < vwma and prev_close >= prev_vwma:
<                     contrib = -weight
<                     self.logger.debug("VWMA: Bearish crossover (price below VWMA).")
<                 signal_score += contrib
<                 signal_breakdown["VWMA_Cross"] = contrib
---
>         if not pd.isna(volume_delta) and weight > 0:
>             contrib = 0.0
>             if volume_delta > volume_delta_threshold:  # Strong buying pressure
>                 contrib = weight
>                 self.logger.debug(f"[{self.symbol}] Volume Delta: Strong buying pressure detected ({volume_delta:.2f}).")
>             elif volume_delta < -volume_delta_threshold:  # Strong selling pressure
>                 contrib = -weight
>                 self.logger.debug(f"[{self.symbol}] Volume Delta: Strong selling pressure detected ({volume_delta:.2f}).")
>             # Weaker signals for moderate delta
>             elif volume_delta > 0:
>                 contrib = weight * 0.3
>             elif volume_delta < 0:
>                 contrib = -weight * 0.3
>             signal_score += contrib
>             signal_breakdown["Volume_Delta_Signal"] = contrib
>         return signal_score, signal_breakdown
2765,2769c2441,2468
<         # --- Volume Delta Scoring ---
<         if active_indicators.get("volume_delta", False):
<             volume_delta = self._get_indicator_value("Volume_Delta")
<             volume_delta_threshold = isd["volume_delta_threshold"]
<             weight = weights.get("volume_delta_signal", 0.0)
---
>     def _score_mtf_confluence(self, signal_score: float, signal_breakdown: dict, mtf_trends: dict[str, str]) -> tuple[float, dict]:
>         """Scores Multi-Timeframe trend confluence."""
>         if not self.config["mtf_analysis"]["enabled"] or not mtf_trends:
>             return signal_score, signal_breakdown
> 
>         mtf_buy_score = 0
>         mtf_sell_score = 0
>         for _tf_indicator, trend in mtf_trends.items():
>             if trend == "UP":
>                 mtf_buy_score += 1
>             elif trend == "DOWN":
>                 mtf_sell_score += 1
> 
>         weight = self.weights.get("mtf_trend_confluence", 0)
>         if weight == 0: return signal_score, signal_breakdown
> 
>         contrib = 0.0
>         if mtf_trends:
>             # Calculate a normalized score based on the balance of buy/sell trends
>             # Max possible score is 1 (all UP), min is -1 (all DOWN)
>             normalized_mtf_score = (mtf_buy_score - mtf_sell_score) / len(mtf_trends)
>             contrib = weight * normalized_mtf_score
>             self.logger.debug(
>                 f"[{self.symbol}] MTF Confluence: Score {normalized_mtf_score:.2f} (Buy: {mtf_buy_score}, Sell: {mtf_sell_score}). Total MTF contribution: {contrib:.2f}"
>             )
>         signal_score += contrib
>         signal_breakdown["MTF_Trend_Confluence"] = contrib
>         return signal_score, signal_breakdown
2771,2785d2469
<             if not pd.isna(volume_delta):
<                 contrib = 0.0
<                 if volume_delta > volume_delta_threshold:  # Strong buying pressure
<                     contrib = weight
<                     self.logger.debug("Volume Delta: Strong buying pressure detected.")
<                 elif volume_delta < -volume_delta_threshold:  # Strong selling pressure
<                     contrib = -weight
<                     self.logger.debug("Volume Delta: Strong selling pressure detected.")
<                 # Weaker signals for moderate delta
<                 elif volume_delta > 0:
<                     contrib = weight * 0.3
<                 elif volume_delta < 0:
<                     contrib = -weight * 0.3
<                 signal_score += contrib
<                 signal_breakdown["Volume_Delta_Signal"] = contrib
2786a2471,2487
>     def generate_trading_signal(
>         self,
>         current_price: Decimal,
>         orderbook_data: dict | None,
>         mtf_trends: dict[str, str],
>     ) -> tuple[str, float, dict]:
>         """Generate a signal using confluence of indicators, including Ehlers SuperTrend.
>         Returns the final signal, the aggregated signal score, and a breakdown of contributions.
>         """
>         signal_score = 0.0
>         signal_breakdown: dict[str, float] = {} # Initialize breakdown dictionary
> 
>         if self.df.empty:
>             self.logger.warning(
>                 f"{NEON_YELLOW}[{self.symbol}] DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}"
>             )
>             return "HOLD", 0.0, {}
2788,2796c2489,2511
<         # --- Multi-Timeframe Trend Confluence Scoring ---
<         if self.config["mtf_analysis"]["enabled"] and mtf_trends:
<             mtf_buy_score = 0
<             mtf_sell_score = 0
<             for _tf_indicator, trend in mtf_trends.items():
<                 if trend == "UP":
<                     mtf_buy_score += 1
<                 elif trend == "DOWN":
<                     mtf_sell_score += 1
---
>         current_close = Decimal(str(self.df["close"].iloc[-1]))
>         # Get previous close price, handle case with only one data point
>         prev_close = Decimal(str(self.df["close"].iloc[-2])) if len(self.df) > 1 else current_close
> 
>         # --- Apply Scoring for Each Indicator Group ---
>         signal_score, signal_breakdown = self._score_ema_alignment(signal_score, signal_breakdown)
>         signal_score, signal_breakdown = self._score_sma_trend_filter(signal_score, signal_breakdown, current_close)
>         signal_score, signal_breakdown = self._score_momentum(signal_score, signal_breakdown, current_close, prev_close)
>         signal_score, signal_breakdown = self._score_bollinger_bands(signal_score, signal_breakdown, current_close)
>         signal_score, signal_breakdown = self._score_vwap(signal_score, signal_breakdown, current_close, prev_close)
>         signal_score, signal_breakdown = self._score_psar(signal_score, signal_breakdown, current_close, prev_close)
>         signal_score, signal_breakdown = self._score_orderbook_imbalance(signal_score, signal_breakdown, orderbook_data)
>         signal_score, signal_breakdown = self._score_fibonacci_levels(signal_score, signal_breakdown, current_close, prev_close)
>         signal_score, signal_breakdown = self._score_ehlers_supertrend(signal_score, signal_breakdown)
>         signal_score, signal_breakdown = self._score_macd(signal_score, signal_breakdown)
>         signal_score, signal_breakdown = self._score_adx(signal_score, signal_breakdown)
>         signal_score, signal_breakdown = self._score_ichimoku_cloud(signal_score, signal_breakdown, current_close, prev_close)
>         signal_score, signal_breakdown = self._score_obv(signal_score, signal_breakdown)
>         signal_score, signal_breakdown = self._score_cmf(signal_score, signal_breakdown)
>         signal_score, signal_breakdown = self._score_volatility_index(signal_score, signal_breakdown)
>         signal_score, signal_breakdown = self._score_vwma(signal_score, signal_breakdown, current_close, prev_close)
>         signal_score, signal_breakdown = self._score_volume_delta(signal_score, signal_breakdown)
>         signal_score, signal_breakdown = self._score_mtf_confluence(signal_score, signal_breakdown, mtf_trends)
2798,2810d2512
<             mtf_weight = weights.get("mtf_trend_confluence", 0.0)
<             contrib = 0.0
<             if mtf_trends:
<                 # Calculate a normalized score based on the balance of buy/sell trends
<                 normalized_mtf_score = (mtf_buy_score - mtf_sell_score) / len(
<                     mtf_trends
<                 )
<                 contrib = mtf_weight * normalized_mtf_score
<                 self.logger.debug(
<                     f"MTF Confluence: Score {normalized_mtf_score:.2f} (Buy: {mtf_buy_score}, Sell: {mtf_sell_score}). Total MTF contribution: {mtf_weight * normalized_mtf_score:.2f}"
<                 )
<             signal_score += contrib
<             signal_breakdown["MTF_Trend_Confluence"] = contrib
2839c2541
<                 self.logger.info(f"{NEON_YELLOW}Signal '{final_signal}' ignored due to cooldown ({cooldown_sec - (now_ts - self._last_signal_ts)}s remaining).{RESET}")
---
>                 self.logger.info(f"{NEON_YELLOW}[{self.symbol}] Signal '{final_signal}' ignored due to cooldown ({cooldown_sec - (now_ts - self._last_signal_ts)}s remaining).{RESET}")
2848c2550
<             f"{NEON_YELLOW}Raw Signal Score: {signal_score:.2f}, Final Signal: {final_signal}{RESET}"
---
>             f"{NEON_YELLOW}[{self.symbol}] Raw Signal Score: {signal_score:.2f}, Final Signal: {final_signal}{RESET}"
2862,2863c2564,2567
<         price_precision_str = "0." + "0" * (self.config["trade_management"]["price_precision"] - 1) + "1"
< 
---
>         # Ensure price precision is at least 1 (e.g., 0.1, 0.01, etc.)
>         price_precision_exponent = max(0, self.config["trade_management"]["price_precision"] - 1)
>         price_precision_str = "0." + "0" * price_precision_exponent + "1"
>         quantize_dec = Decimal(price_precision_str)
2871,2872c2575,2576
<         else:
<             return Decimal("0"), Decimal("0")  # Should not happen for valid signals
---
>         else: # Should not happen for valid signals
>             return Decimal("0"), Decimal("0")
2875,2876c2579,2580
<             Decimal(price_precision_str), rounding=ROUND_DOWN
<         ), stop_loss.quantize(Decimal(price_precision_str), rounding=ROUND_DOWN)
---
>             quantize_dec, rounding=ROUND_DOWN
>         ), stop_loss.quantize(quantize_dec, rounding=ROUND_DOWN)
2886c2590
<     signal_breakdown: dict | None = None # New parameter
---
>     signal_breakdown: dict | None = None # New parameter for displaying breakdown
2891a2596,2597
>     # Re-initialize TradingAnalyzer to get the latest indicator values for display
>     # This might be slightly redundant if called after signal generation, but ensures display is up-to-date.
2901c2607,2609
<     for indicator_name, value in analyzer.indicator_values.items():
---
>     # Sort indicators alphabetically for consistent display
>     sorted_indicator_items = sorted(analyzer.indicator_values.items())
>     for indicator_name, value in sorted_indicator_items:
2907c2615
<             logger.info(f"  {color}{indicator_name}: {value:.8f}{RESET}")
---
>             logger.info(f"  {color}{indicator_name}: {value:.8f}{RESET}") # Use higher precision for floats
2914c2622,2624
<         for level_name, level_price in analyzer.fib_levels.items():
---
>         # Sort Fibonacci levels by ratio for consistent display
>         sorted_fib_levels = sorted(analyzer.fib_levels.items(), key=lambda item: float(item[0].replace('%',''))/100)
>         for level_name, level_price in sorted_fib_levels:
2920c2630,2632
<         for tf_indicator, trend in mtf_trends.items():
---
>         # Sort MTF trends by timeframe for consistent display
>         sorted_mtf_trends = sorted(mtf_trends.items())
>         for tf_indicator, trend in sorted_mtf_trends:
2941c2653
<     # Validate interval format at startup
---
>     # These are standard Bybit intervals. It's good practice to keep them consistent.
2943,2955c2655
<         "1",
<         "3",
<         "5",
<         "15",
<         "30",
<         "60",
<         "120",
<         "240",
<         "360",
<         "720",
<         "D",
<         "W",
<         "M",
---
>         "1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D", "W", "M"
2971c2671
<     logger.info(f"{NEON_GREEN}--- Wgwhalex Trading Bot Initialized ---{RESET}")
---
>     logger.info(f"{NEON_GREEN}--- Whalebot Trading Bot Initialized ---{RESET}")
2988a2689,2690
>             # Fetch primary klines. Fetching a larger number (e.g., 1000) is good practice
>             # to ensure indicators with long periods have enough data.
3003a2706
>             # Fetch MTF trends
3006,3027c2709,2712
<                 for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
<                     logger.debug(f"Fetching klines for MTF interval: {htf_interval}")
<                     htf_df = fetch_klines(config["symbol"], htf_interval, 1000, logger)
<                     if htf_df is not None and not htf_df.empty:
<                         for trend_ind in config["mtf_analysis"]["trend_indicators"]:
<                             temp_htf_analyzer = TradingAnalyzer(
<                                 htf_df, config, logger, config["symbol"]
<                             )
<                             trend = temp_htf_analyzer._get_mtf_trend(
<                                 temp_htf_analyzer.df, trend_ind
<                             )
<                             mtf_trends[f"{htf_interval}_{trend_ind}"] = trend
<                             logger.debug(
<                                 f"MTF Trend ({htf_interval}, {trend_ind}): {trend}"
<                             )
<                     else:
<                         logger.warning(
<                             f"{NEON_YELLOW}Could not fetch klines for higher timeframe {htf_interval} or it was empty. Skipping MTF trend for this TF.{RESET}"
<                         )
<                     time.sleep(
<                         config["mtf_analysis"]["mtf_request_delay_seconds"]
<                     )  # Delay between MTF requests
---
>                 # Create a temporary analyzer instance to call the MTF analysis method
>                 # This avoids re-calculating all indicators on the primary DF just for MTF analysis
>                 temp_analyzer_for_mtf = TradingAnalyzer(df, config, logger, config["symbol"])
>                 mtf_trends = temp_analyzer_for_mtf._fetch_and_analyze_mtf()
3028a2714
>             # Display current market data and indicators before signal generation
3032a2719
>             # Initialize TradingAnalyzer with the primary DataFrame for signal generation
3042a2730
>             # Generate trading signal
3046,3048d2733
<             atr_value = Decimal(
<                 str(analyzer._get_indicator_value("ATR", Decimal("0.01")))
<             ) # Default to a small positive value if ATR is missing
3049a2735,2742
>             # Get ATR for position sizing and SL/TP calculation
>             # Provide a default small positive ATR value if it's missing or invalid to prevent errors
>             # Ensure the default is a Decimal
>             atr_value = Decimal(str(analyzer._get_indicator_value("ATR", Decimal("0.0001"))))
>             if atr_value <= 0: # Ensure ATR is positive for calculations
>                 atr_value = Decimal("0.0001")
> 
>             # Manage open positions (check for SL/TP hits)
3052c2745
<             # Display current state after analysis and signal generation
---
>             # Display current state after analysis and signal generation, including breakdown
3056a2750,2751
>             # Execute trades based on strong signals
>             signal_threshold = config["signal_score_threshold"]
3059c2754
<                 and signal_score >= config["signal_score_threshold"]
---
>                 and signal_score >= signal_threshold
3062c2757
<                     f"{NEON_GREEN}Strong BUY signal detected! Score: {signal_score:.2f}{RESET}"
---
>                     f"{NEON_GREEN}[{config['symbol']}] Strong BUY signal detected! Score: {signal_score:.2f}{RESET}"
3067c2762
<                 and signal_score <= -config["signal_score_threshold"]
---
>                 and signal_score <= -signal_threshold
3070c2765
<                     f"{NEON_RED}Strong SELL signal detected! Score: {signal_score:.2f}{RESET}"
---
>                     f"{NEON_RED}[{config['symbol']}] Strong SELL signal detected! Score: {signal_score:.2f}{RESET}"
3075c2770
<                     f"{NEON_BLUE}No strong trading signal. Holding. Score: {signal_score:.2f}{RESET}"
---
>                     f"{NEON_BLUE}[{config['symbol']}] No strong trading signal. Holding. Score: {signal_score:.2f}{RESET}"
3077a2773
>             # Log current open positions and performance summary
3080c2776
<                 logger.info(f"{NEON_CYAN}Open Positions: {len(open_positions)}{RESET}")
---
>                 logger.info(f"{NEON_CYAN}[{config['symbol']}] Open Positions: {len(open_positions)}{RESET}")
3086c2782
<                 logger.info(f"{NEON_CYAN}No open positions.{RESET}")
---
>                 logger.info(f"{NEON_CYAN}[{config['symbol']}] No open positions.{RESET}")
3090c2786
<                 f"{NEON_YELLOW}Performance Summary: Total PnL: {perf_summary['total_pnl'].normalize():.2f}, Wins: {perf_summary['wins']}, Losses: {perf_summary['losses']}, Win Rate: {perf_summary['win_rate']}{RESET}"
---
>                 f"{NEON_YELLOW}[{config['symbol']}] Performance Summary: Total PnL: {perf_summary['total_pnl'].normalize():.2f}, Wins: {perf_summary['wins']}, Losses: {perf_summary['losses']}, Win Rate: {perf_summary['win_rate']}{RESET}"
3102,3103c2798,2799
<             logger.exception(f"{NEON_RED}Unhandled exception in main loop:{RESET}")
<             time.sleep(config["loop_delay"] * 2)
---
>             logger.exception(f"{NEON_RED}[{config['symbol']}] Unhandled exception in main loop:{RESET}")
>             time.sleep(config["loop_delay"] * 2) # Longer sleep after an error
3109d2804
<     main()
