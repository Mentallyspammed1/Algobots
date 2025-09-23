import logging
from datetime import datetime

import numpy as np
import pandas as pd
import pandas_ta as pta
import ta
from pybit.unified_trading import HTTP

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class BybitTrendAnalyzer:
    """A module for fetching Bybit v5 kline data and performing trend analysis using
    various common technical indicators.
    """

    def __init__(self, api_key: str = "", api_secret: str = "", testnet: bool = False):
        """Initializes the BybitTrendAnalyzer with API credentials.

        Args:
            api_key (str): Your Bybit API key.
            api_secret (str): Your Bybit API secret.
            testnet (bool): Set to True to connect to Bybit Testnet, False for Mainnet.
        """
        self.client = HTTP(testnet=testnet, api_key=api_key, api_secret=api_secret)
        self.testnet = testnet
        logging.info(f"BybitTrendAnalyzer initialized. Connected to {'Testnet' if testnet else 'Mainnet'}.")

    def _get_interval_ms(self, interval: str) -> int:
        """Converts interval string to milliseconds.

        Args:
            interval (str): The interval string (e.g., "1", "5", "60", "D", "W", "M").

        Returns:
            int: Interval in milliseconds.
        """
        if interval.isdigit():
            return int(interval) * 60 * 1000  # Convert minutes to milliseconds
        if interval == 'D':
            return 24 * 60 * 60 * 1000
        if interval == 'W':
            return 7 * 24 * 60 * 60 * 1000
        if interval == 'M':
            # Approximate a month as 30 days for simplicity, or could be more precise if needed
            return 30 * 24 * 60 * 60 * 1000
        raise ValueError(f"Unsupported interval: {interval}")

    def fetch_klines(self,
                     category: str,
                     symbol: str,
                     interval: str,
                     num_candles: int = 200,
                     end_time: int = None) -> pd.DataFrame:
        """Fetches kline data from Bybit API and returns it as a Pandas DataFrame.

        Args:
            category (str): Product category (e.g., "linear", "inverse", "spot").
            symbol (str): Trading pair (e.g., "BTCUSDT", "ETHUSDT").
            interval (str): Klines interval (e.g., "1", "5", "15", "60", "D", "W", "M").
            num_candles (int): Number of candles to fetch (max 5000 per request).
            end_time (int, optional): End timestamp in milliseconds. Defaults to current time.

        Returns:
            pd.DataFrame: DataFrame with kline data, or empty DataFrame on error.
        """
        if num_candles > 5000: # Increased limit to 5000
            logging.warning("num_candles exceeds maximum (5000). Only fetching 5000 candles.")
            num_candles = 5000

        if end_time is None:
            end_time = int(datetime.now().timestamp() * 1000)

        start_time = end_time - (num_candles * self._get_interval_ms(interval))

        try:
            response = self.client.get_kline(
                category=category,
                symbol=symbol,
                interval=interval,
                start=start_time,
                end=end_time,
                limit=num_candles
            )

            if response and response['retCode'] == 0 and response['result']['list']:
                df = pd.DataFrame(response['result']['list'], columns=[
                    'open_time', 'open', 'high', 'low', 'close', 'volume', 'turnover'
                ])
                df['open_time'] = pd.to_datetime(df['open_time'].astype(int), unit='ms')
                # Convert numeric columns
                numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'turnover']
                df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors='coerce')
                df.set_index('open_time', inplace=True)
                df.sort_index(inplace=True) # Ensure chronological order

                logging.info(f"Successfully fetched {len(df)} {interval} candles for {symbol} ({category}).")
                return df
            logging.error(f"Failed to fetch klines for {symbol}: {response.get('retMsg', 'Unknown error')}")
            return pd.DataFrame()
        except Exception as e:
            logging.error(f"An error occurred while fetching klines: {e}")
            return pd.DataFrame()

    def _identify_order_blocks(self, df: pd.DataFrame, ob_percentage_threshold: float = 0.01) -> pd.DataFrame:
        """Identifies bullish and bearish order blocks in the DataFrame.

        Args:
            df (pd.DataFrame): DataFrame with 'open', 'high', 'low', 'close' columns.
            ob_percentage_threshold (float): Percentage threshold for a 'strong move' to confirm an order block.

        Returns:
            pd.DataFrame: DataFrame with 'bullish_ob', 'bearish_ob', 'ob_high', 'ob_low' columns.
        """
        df['bullish_ob'] = False
        df['bearish_ob'] = False
        df['ob_high'] = np.nan
        df['ob_low'] = np.nan

        for i in range(1, len(df) - 1): # Iterate from the second candle to the second to last
            prev_candle = df.iloc[i-1]
            current_candle = df.iloc[i]

            # Bullish Order Block: Last bearish candle before a strong upward move
            # Criteria:
            # 1. Previous candle is bearish (close < open)
            # 2. Current candle is bullish (close > open)
            # 3. Price moves significantly up after the previous candle's low
            if prev_candle['close'] < prev_candle['open']: # Previous candle is bearish
                # Check for a strong bullish move after the bearish candle
                # A strong move could be defined as price moving up by a certain percentage
                # from the low of the bearish candle.
                # For simplicity, let's check if the current close is significantly higher than the previous close
                price_increase = (current_candle['close'] - prev_candle['close']) / prev_candle['close']
                if price_increase > ob_percentage_threshold:
                    df.loc[df.index[i-1], 'bullish_ob'] = True
                    df.loc[df.index[i-1], 'ob_high'] = prev_candle['high']
                    df.loc[df.index[i-1], 'ob_low'] = prev_candle['low']
                    logging.debug(f"Bullish OB identified at {df.index[i-1]}")

            # Bearish Order Block: Last bullish candle before a strong downward move
            # Criteria:
            # 1. Previous candle is bullish (close > open)
            # 2. Current candle is bearish (close < open)
            # 3. Price moves significantly down after the previous candle's high
            if prev_candle['close'] > prev_candle['open']: # Previous candle is bullish
                # Check for a strong bearish move after the bullish candle
                price_decrease = (prev_candle['close'] - current_candle['close']) / prev_candle['close']
                if price_decrease > ob_percentage_threshold:
                    df.loc[df.index[i-1], 'bearish_ob'] = True
                    df.loc[df.index[i-1], 'ob_high'] = prev_candle['high']
                    df.loc[df.index[i-1], 'ob_low'] = prev_candle['low']
                    logging.debug(f"Bearish OB identified at {df.index[i-1]}")
        logging.info("Order blocks identified.")
        return df

    def calculate_indicators(self, df: pd.DataFrame,
                             sma_fast_period: int = 20,
                             sma_slow_period: int = 50,
                             ema_fast_period: int = 12,
                             ema_slow_period: int = 26,
                             rsi_period: int = 14,
                             adx_period: int = 14,
                             bb_window: int = 20,
                             bb_std: int = 2,
                             macd_fast_period: int = 12,
                             macd_slow_period: int = 26,
                             macd_signal_period: int = 9,
                             ichimoku_tenkan: int = 9,
                             ichimoku_kijun: int = 26,
                             ichimoku_senkou: int = 52,
                             ehlers_fisher_period: int = 10,
                             ehlers_ssf_period: int = 10,
                             ob_percentage_threshold: float = 0.01) -> pd.DataFrame:
        """Calculates various technical indicators and adds them to the DataFrame.

        Args:
            df (pd.DataFrame): DataFrame with 'open', 'high', 'low', 'close' columns.
            sma_fast_period (int): Period for the fast Simple Moving Average.
            sma_slow_period (int): Period for the slow Simple Moving Average.
            ema_fast_period (int): Period for the fast Exponential Moving Average.
            ema_slow_period (int): Period for the slow Exponential Moving Average.
            rsi_period (int): Period for the Relative Strength Index.
            adx_period (int): Period for the Average Directional Index.
            bb_window (int): Window for Bollinger Bands.
            bb_std (int): Standard deviation for Bollinger Bands.
            macd_fast_period (int): Fast period for MACD.
            macd_slow_period (int): Slow period for MACD.
            macd_signal_period (int): Signal period for MACD.
            ichimoku_tenkan (int): Tenkan-sen period for Ichimoku.
            ichimoku_kijun (int): Kijun-sen period for Ichimoku.
            ichimoku_senkou (int): Senkou Span B period for Ichimoku.
            ehlers_fisher_period (int): Period for Ehlers Fisher Transform.
            ehlers_ssf_period (int): Period for Ehlers Super Smoother Filter.
            ob_percentage_threshold (float): Percentage threshold for a 'strong move' to confirm an order block.

        Returns:
            pd.DataFrame: DataFrame with added indicator columns.
        """
        if df.empty:
            logging.warning("DataFrame is empty, cannot calculate indicators.")
            return df

        # Simple Moving Averages
        df[f'SMA_{sma_fast_period}'] = ta.trend.sma_indicator(df['close'], window=sma_fast_period)
        df[f'SMA_{sma_slow_period}'] = ta.trend.sma_indicator(df['close'], window=sma_slow_period)

        # Exponential Moving Averages
        df[f'EMA_{ema_fast_period}'] = ta.trend.ema_indicator(df['close'], window=ema_fast_period)
        df[f'EMA_{ema_slow_period}'] = ta.trend.ema_indicator(df['close'], window=ema_slow_period)

        # Relative Strength Index (RSI)
        df[f'RSI_{rsi_period}'] = ta.momentum.rsi(df['close'], window=rsi_period)

        # Average Directional Index (ADX)
        df[f'ADX_{adx_period}'] = ta.trend.adx(df['high'], df['low'], df['close'], window=adx_period)
        df[f'ADX_POS_{adx_period}'] = ta.trend.adx_pos(df['high'], df['low'], df['close'], window=adx_period)
        df[f'ADX_NEG_{adx_period}'] = ta.trend.adx_neg(df['high'], df['low'], df['close'], window=adx_period)

        # Bollinger Bands
        bollinger = ta.volatility.BollingerBands(df['close'], window=bb_window, window_dev=bb_std)
        df['BB_upper'] = bollinger.bollinger_hband()
        df['BB_lower'] = bollinger.bollinger_lband()
        df['BB_middle'] = bollinger.bollinger_mavg()
        df['BB_width'] = bollinger.bollinger_wband()
        df['BB_percent'] = bollinger.bollinger_pband()

        # MACD
        macd = ta.trend.MACD(df['close'], window_fast=macd_fast_period, window_slow=macd_slow_period, window_sign=macd_signal_period)
        df['MACD'] = macd.macd()
        df['MACD_signal'] = macd.macd_signal()
        df['MACD_diff'] = macd.macd_diff()

        # Ichimoku Cloud
        ichimoku = ta.trend.IchimokuIndicator(df['high'], df['low'],
                                              window1=ichimoku_tenkan,
                                              window2=ichimoku_kijun,
                                              window3=ichimoku_senkou)
        df['Ichimoku_conversion_line'] = ichimoku.ichimoku_conversion_line()
        df['Ichimoku_base_line'] = ichimoku.ichimoku_base_line()
        df['Ichimoku_leading_span_a'] = ichimoku.ichimoku_a()
        df['Ichimoku_leading_span_b'] = ichimoku.ichimoku_b()
        df['Ichimoku_lagging_span'] = df['close'].shift(-ichimoku_kijun) # Chikou Span is current close shifted back

        # Ehlers Fisher Transform
        # Using a simplified implementation as pandas_ta does not have it directly
        # This is a common approximation, for more robust implementation, consider specialized libraries
        if len(df) >= ehlers_fisher_period:
            min_low = df['low'].rolling(window=ehlers_fisher_period).min()
            max_high = df['high'].rolling(window=ehlers_fisher_period).max()

            # Avoid division by zero
            range_val = max_high - min_low
            range_val[range_val == 0] = 1e-9 # Small epsilon to prevent division by zero

            # Normalize price to be between -1 and 1
            # This is a simplified normalization. Ehlers' original formula uses a slightly different approach
            # involving previous values and alpha smoothing.
            normalized_price = 2 * ((df['close'] - min_low) / range_val) - 1

            # Apply Fisher Transform formula
            # Limit values to avoid log(0) or log(negative)
            v = np.clip(normalized_price, -0.999, 0.999)
            df['Ehlers_Fisher_Transform'] = 0.5 * np.log((1 + v) / (1 - v))
        else:
            df['Ehlers_Fisher_Transform'] = np.nan
            logging.warning(f"Not enough data for Ehlers Fisher Transform with period {ehlers_fisher_period}.")


        # Ehlers Super Smoother Filter (using pandas_ta)
        if len(df) >= ehlers_ssf_period:
            df['Ehlers_SSF'] = pta.ssf(df['close'], length=ehlers_ssf_period, poles=2)
        else:
            df['Ehlers_SSF'] = np.nan
            logging.warning(f"Not enough data for Ehlers Super Smoother Filter with period {ehlers_ssf_period}.")

        # Identify Order Blocks
        df = self._identify_order_blocks(df, ob_percentage_threshold)

        logging.info("Technical indicators and order blocks calculated.")
        return df

    def analyze_trend(self, df: pd.DataFrame,
                      sma_fast_period: int = 20,
                      sma_slow_period: int = 50,
                      rsi_period: int = 14,
                      adx_period: int = 14,
                      bb_window: int = 20,
                      macd_fast_period: int = 12,
                      macd_slow_period: int = 26,
                      macd_signal_period: int = 9,
                      ichimoku_tenkan: int = 9,
                      ichimoku_kijun: int = 26,
                      ichimoku_senkou: int = 52,
                      ehlers_fisher_period: int = 10,
                      ehlers_ssf_period: int = 10,
                      ob_percentage_threshold: float = 0.01) -> dict:
        """Analyzes the trend based on the latest indicator values.

        Args:
            df (pd.DataFrame): DataFrame with calculated indicators.
            sma_fast_period (int): Period for the fast Simple Moving Average.
            sma_slow_period (int): Period for the slow Simple Moving Average.
            rsi_period (int): Period for the Relative Strength Index.
            adx_period (int): Period for the Average Directional Index.
            bb_window (int): Window for Bollinger Bands.
            macd_fast_period (int): Fast period for MACD.
            macd_slow_period (int): Slow period for MACD.
            ichimoku_tenkan (int): Tenkan-sen period for Ichimoku.
            ichimoku_kijun (int): Kijun-sen period for Ichimoku.
            ehlers_fisher_period (int): Period for Ehlers Fisher Transform.
            ehlers_ssf_period (int): Period for Ehlers Super Smoother Filter.
            ob_percentage_threshold (float): Percentage threshold for a 'strong move' to confirm an order block.

        Returns:
            dict: A dictionary containing the trend analysis results.
        """
        # Determine the maximum lookback period required by all indicators
        max_lookback = max(sma_slow_period, rsi_period, adx_period, bb_window, macd_slow_period + macd_signal_period, ichimoku_senkou, ehlers_fisher_period, ehlers_ssf_period) # ichimoku_senkou is 52 by default

        if df.empty or len(df) < max_lookback:
            logging.warning("Not enough data to perform comprehensive trend analysis.")
            return {"overall_trend": "Insufficient Data", "details": {}}

        latest_data = df.iloc[-1]
        analysis = {
            "overall_trend": "Neutral",
            "details": {
                "price": latest_data['close'],
                "timestamp": latest_data.name.isoformat(),
                "sma_crossover": "N/A",
                "rsi_status": "N/A",
                "adx_strength": "N/A",
                "adx_direction": "N/A",
                "bollinger_bands_status": "N/A",
                "macd_crossover": "N/A",
                "ichimoku_status": "N/A",
                "ehlers_fisher_status": "N/A",
                "ehlers_ssf_status": "N/A",
                "order_block_status": "N/A"
            }
        }

        # --- SMA Crossover Analysis ---
        sma_fast = latest_data.get(f'SMA_{sma_fast_period}')
        sma_slow = latest_data.get(f'SMA_{sma_slow_period}')

        if pd.notna(sma_fast) and pd.notna(sma_slow):
            if sma_fast > sma_slow:
                analysis["details"]["sma_crossover"] = "Bullish (Fast SMA > Slow SMA)"
                analysis["overall_trend"] = "Uptrend" # Tentative
            elif sma_fast < sma_slow:
                analysis["details"]["sma_crossover"] = "Bearish (Fast SMA < Slow SMA)"
                analysis["overall_trend"] = "Downtrend" # Tentative
            else:
                analysis["details"]["sma_crossover"] = "Consolidation (SMAs converging)"
        else:
            logging.warning("SMA values are NaN, skipping SMA crossover analysis.")

        # --- RSI Analysis ---
        rsi_val = latest_data.get(f'RSI_{rsi_period}')
        if pd.notna(rsi_val):
            if rsi_val > 70:
                analysis["details"]["rsi_status"] = f"Overbought ({rsi_val:.2f})"
            elif rsi_val < 30:
                analysis["details"]["rsi_status"] = f"Oversold ({rsi_val:.2f})"
            else:
                analysis["details"]["rsi_status"] = f"Neutral ({rsi_val:.2f})"
        else:
            logging.warning("RSI value is NaN, skipping RSI analysis.")

        # --- ADX Analysis ---
        adx_val = latest_data.get(f'ADX_{adx_period}')
        adx_pos = latest_data.get(f'ADX_POS_{adx_period}')
        adx_neg = latest_data.get(f'ADX_NEG_{adx_period}')

        if pd.notna(adx_val) and pd.notna(adx_pos) and pd.notna(adx_neg):
            # Trend Strength
            if adx_val > 25:
                analysis["details"]["adx_strength"] = f"Strong Trend ({adx_val:.2f})"
            elif adx_val > 20:
                analysis["details"]["adx_strength"] = f"Developing Trend ({adx_val:.2f})"
            else:
                analysis["details"]["adx_strength"] = f"Weak/No Trend ({adx_val:.2f})"

            # Trend Direction
            if adx_pos > adx_neg:
                analysis["details"]["adx_direction"] = f"Positive (DI+ {adx_pos:.2f} > DI- {adx_neg:.2f})"
                # Refine overall trend based on ADX
                if analysis["overall_trend"] == "Uptrend" and adx_val > 20:
                    analysis["overall_trend"] = "Strong Uptrend"
                elif analysis["overall_trend"] == "Neutral" and adx_val > 20:
                    analysis["overall_trend"] = "Emerging Uptrend"
            elif adx_neg > adx_pos:
                analysis["details"]["adx_direction"] = f"Negative (DI- {adx_neg:.2f} > DI+ {adx_pos:.2f})"
                # Refine overall trend based on ADX
                if analysis["overall_trend"] == "Downtrend" and adx_val > 20:
                    analysis["overall_trend"] = "Strong Downtrend"
                elif analysis["overall_trend"] == "Neutral" and adx_val > 20:
                    analysis["overall_trend"] = "Emerging Downtrend"
            else:
                analysis["details"]["adx_direction"] = "Unclear"
        else:
            logging.warning("ADX values are NaN, skipping ADX analysis.")

        # --- Bollinger Bands Analysis ---
        bb_upper = latest_data.get('BB_upper')
        bb_lower = latest_data.get('BB_lower')
        bb_middle = latest_data.get('BB_middle')
        close_price = latest_data['close']

        if pd.notna(bb_upper) and pd.notna(bb_lower) and pd.notna(bb_middle):
            if close_price > bb_upper:
                analysis["details"]["bollinger_bands_status"] = "Price above Upper Band (Overbought/Strong Uptrend)"
            elif close_price < bb_lower:
                analysis["details"]["bollinger_bands_status"] = "Price below Lower Band (Oversold/Strong Downtrend)"
            elif close_price > bb_middle:
                analysis["details"]["bollinger_bands_status"] = "Price above Middle Band (Bullish Bias)"
            elif close_price < bb_middle:
                analysis["details"]["bollinger_bands_status"] = "Price below Middle Band (Bearish Bias)"
            else:
                analysis["details"]["bollinger_bands_status"] = "Price near Middle Band (Neutral)"
        else:
            logging.warning("Bollinger Bands values are NaN, skipping BB analysis.")

        # --- MACD Analysis ---
        macd_val = latest_data.get('MACD')
        macd_signal = latest_data.get('MACD_signal')
        macd_diff = latest_data.get('MACD_diff')

        if pd.notna(macd_val) and pd.notna(macd_signal) and pd.notna(macd_diff):
            if macd_val > macd_signal and macd_diff > 0:
                analysis["details"]["macd_crossover"] = "Bullish Crossover (MACD above Signal, Histogram positive)"
            elif macd_val < macd_signal and macd_diff < 0:
                analysis["details"]["macd_crossover"] = "Bearish Crossover (MACD below Signal, Histogram negative)"
            else:
                analysis["details"]["macd_crossover"] = "No clear crossover"
        else:
            logging.warning("MACD values are NaN, skipping MACD analysis.")

        # --- Ichimoku Cloud Analysis ---
        conversion_line = latest_data.get('Ichimoku_conversion_line')
        base_line = latest_data.get('Ichimoku_base_line')
        leading_span_a = latest_data.get('Ichimoku_leading_span_a')
        leading_span_b = latest_data.get('Ichimoku_leading_span_b')
        lagging_span = latest_data.get('Ichimoku_lagging_span')

        if all(pd.notna([conversion_line, base_line, leading_span_a, leading_span_b, lagging_span])):
            # Price vs Cloud
            if close_price > max(leading_span_a, leading_span_b):
                cloud_status = "Price above Cloud (Bullish)"
            elif close_price < min(leading_span_a, leading_span_b):
                cloud_status = "Price below Cloud (Bearish)"
            else:
                cloud_status = "Price inside Cloud (Neutral/Choppy)"

            # Conversion Line vs Base Line
            if conversion_line > base_line:
                tenkan_kijun_crossover = "Conversion Line above Base Line (Bullish)"
            elif conversion_line < base_line:
                tenkan_kijun_crossover = "Conversion Line below Base Line (Bearish)"
            else:
                tenkan_kijun_crossover = "Conversion Line and Base Line are flat (Sideways)"

            # Lagging Span vs Price
            if lagging_span > close_price:
                chikou_span_status = "Lagging Span above Price (Bullish)"
            elif lagging_span < close_price:
                chikou_span_status = "Lagging Span below Price (Bearish)"
            else:
                chikou_span_status = "Lagging Span near Price (Neutral)"

            analysis["details"]["ichimoku_status"] = {
                "cloud_status": cloud_status,
                "tenkan_kijun_crossover": tenkan_kijun_crossover,
                "chikou_span_status": chikou_span_status
            }
        else:
            logging.warning("Ichimoku values are NaN, skipping Ichimoku analysis.")

        # --- Ehlers Fisher Transform Analysis ---
        ehlers_fisher_val = latest_data.get('Ehlers_Fisher_Transform')
        if pd.notna(ehlers_fisher_val):
            if ehlers_fisher_val > 0.5: # Thresholds can be adjusted
                analysis["details"]["ehlers_fisher_status"] = f"Bullish ({ehlers_fisher_val:.2f})"
            elif ehlers_fisher_val < -0.5:
                analysis["details"]["ehlers_fisher_status"] = f"Bearish ({ehlers_fisher_val:.2f})"
            else:
                analysis["details"]["ehlers_fisher_status"] = f"Neutral ({ehlers_fisher_val:.2f})"
        else:
            logging.warning("Ehlers Fisher Transform value is NaN, skipping analysis.")

        # --- Ehlers Super Smoother Filter Analysis ---
        ehlers_ssf_val = latest_data.get('Ehlers_SSF')
        if pd.notna(ehlers_ssf_val):
            if close_price > ehlers_ssf_val:
                analysis["details"]["ehlers_ssf_status"] = f"Price above SSF (Bullish) ({ehlers_ssf_val:.2f})"
            elif close_price < ehlers_ssf_val:
                analysis["details"]["ehlers_ssf_status"] = f"Price below SSF (Bearish) ({ehlers_ssf_val:.2f})"
            else:
                analysis["details"]["ehlers_ssf_status"] = f"Price at SSF (Neutral) ({ehlers_ssf_val:.2f})"
        else:
            logging.warning("Ehlers Super Smoother Filter value is NaN, skipping analysis.")

        # --- Order Block Analysis ---
        # Look back a few candles to see if there's an active OB
        # For simplicity, let's check the last 5 candles for an OB
        recent_candles = df.iloc[-5:]
        bullish_obs = recent_candles[recent_candles['bullish_ob'] == True]
        bearish_obs = recent_candles[recent_candles['bearish_ob'] == True]

        if not bullish_obs.empty:
            # Consider the most recent bullish OB
            latest_bullish_ob = bullish_obs.iloc[-1]
            ob_high = latest_bullish_ob['ob_high']
            ob_low = latest_bullish_ob['ob_low']
            analysis["details"]["order_block_status"] = f"Recent Bullish OB detected (High: {ob_high:.2f}, Low: {ob_low:.2f}). "
            if latest_data['close'] > ob_high:
                analysis["details"]["order_block_status"] += "Price is above OB."
            elif latest_data['close'] < ob_low:
                analysis["details"]["order_block_status"] += "Price is below OB."
            else:
                analysis["details"]["order_block_status"] += "Price is within OB."
            analysis["overall_trend"] = "Potential Reversal Up (Bullish OB)" # Tentative

        if not bearish_obs.empty:
            # Consider the most recent bearish OB
            latest_bearish_ob = bearish_obs.iloc[-1]
            ob_high = latest_bearish_ob['ob_high']
            ob_low = latest_bearish_ob['ob_low']
            analysis["details"]["order_block_status"] = f"Recent Bearish OB detected (High: {ob_high:.2f}, Low: {ob_low:.2f}). "
            if latest_data['close'] < ob_low:
                analysis["details"]["order_block_status"] += "Price is below OB."
            elif latest_data['close'] > ob_high:
                analysis["details"]["order_block_status"] += "Price is above OB."
            else:
                analysis["details"]["order_block_status"] += "Price is within OB."
            analysis["overall_trend"] = "Potential Reversal Down (Bearish OB)" # Tentative


        # Final overall trend decision (can be customized further based on combined signals)
        # This is a simplified example, real-world analysis would be more complex
        bullish_signals = 0
        bearish_signals = 0

        if "Bullish" in analysis["details"]["sma_crossover"]:
            bullish_signals += 1
        elif "Bearish" in analysis["details"]["sma_crossover"]:
            bearish_signals += 1

        if "Overbought" in analysis["details"]["rsi_status"]:
            bearish_signals += 0.5 # Partial signal
        elif "Oversold" in analysis["details"]["rsi_status"]:
            bullish_signals += 0.5 # Partial signal

        if "Strong Uptrend" in analysis["overall_trend"] or "Emerging Uptrend" in analysis["overall_trend"]:
            bullish_signals += 1
        elif "Strong Downtrend" in analysis["overall_trend"] or "Emerging Downtrend" in analysis["overall_trend"]:
            bearish_signals += 1

        if "Price above Upper Band" in analysis["details"]["bollinger_bands_status"] or \
           "Price above Middle Band" in analysis["details"]["bollinger_bands_status"]:
            bullish_signals += 1
        elif "Price below Lower Band" in analysis["details"]["bollinger_bands_status"] or \
             "Price below Middle Band" in analysis["details"]["bollinger_bands_status"]:
            bearish_signals += 1

        if "Bullish Crossover" in analysis["details"]["macd_crossover"]:
            bullish_signals += 1
        elif "Bearish Crossover" in analysis["details"]["macd_crossover"]:
            bearish_signals += 1

        if isinstance(analysis["details"]["ichimoku_status"], dict):
            if "Price above Cloud" in analysis["details"]["ichimoku_status"]["cloud_status"] and \
               "Conversion Line above Base Line" in analysis["details"]["ichimoku_status"]["tenkan_kijun_crossover"] and \
               "Lagging Span above Price" in analysis["details"]["ichimoku_status"]["chikou_span_status"]:
                bullish_signals += 1.5 # Strong Ichimoku bullish signal
            elif "Price below Cloud" in analysis["details"]["ichimoku_status"]["cloud_status"] and \
                 "Conversion Line below Base Line" in analysis["details"]["ichimoku_status"]["tenkan_kijun_crossover"] and \
                 "Lagging Span below Price" in analysis["details"]["ichimoku_status"]["chikou_span_status"]:
                bearish_signals += 1.5 # Strong Ichimoku bearish signal

        if "Bullish" in analysis["details"]["ehlers_fisher_status"]:
            bullish_signals += 1
        elif "Bearish" in analysis["details"]["ehlers_fisher_status"]:
            bearish_signals += 1

        if "Price above SSF" in analysis["details"]["ehlers_ssf_status"]:
            bullish_signals += 1
        elif "Price below SSF" in analysis["details"]["ehlers_ssf_status"]:
            bearish_signals += 1

        if "Bullish OB detected" in analysis["details"]["order_block_status"]:
            bullish_signals += 1
        elif "Bearish OB detected" in analysis["details"]["order_block_status"]:
            bearish_signals += 1


        if bullish_signals > bearish_signals + 1: # +1 for a clearer signal
            analysis["overall_trend"] = "Strong Bullish"
        elif bearish_signals > bullish_signals + 1:
            analysis["overall_trend"] = "Strong Bearish"
        elif bullish_signals > bearish_signals:
            analysis["overall_trend"] = "Slightly Bullish"
        elif bearish_signals > bullish_signals:
            analysis["overall_trend"] = "Slightly Bearish"
        else:
            analysis["overall_trend"] = "Neutral/Consolidation"


        logging.info("Trend analysis complete.")
        return analysis

    def get_trend_summary(self,
                          category: str,
                          symbol: str,
                          interval: str,
                          num_candles: int = 200,
                          sma_fast_period: int = 20,
                          sma_slow_period: int = 50,
                          ema_fast_period: int = 12,
                          ema_slow_period: int = 26,
                          rsi_period: int = 14,
                          adx_period: int = 14,
                          bb_window: int = 20,
                          bb_std: int = 2,
                          macd_fast_period: int = 12,
                          macd_slow_period: int = 26,
                          macd_signal_period: int = 9,
                          ichimoku_tenkan: int = 9,
                          ichimoku_kijun: int = 26,
                          ichimoku_senkou: int = 52,
                          ehlers_fisher_period: int = 10,
                          ehlers_ssf_period: int = 10,
                          ob_percentage_threshold: float = 0.01) -> dict:
        """Orchestrates the process of fetching data, calculating indicators, and analyzing the trend.

        Args:
            category (str): Product category (e.g., "linear", "inverse", "spot").
            symbol (str): Trading pair (e.g., "BTCUSDT", "ETHUSDT").
            interval (str): Klines interval (e.g., "1", "5", "15", "60", "D", "W", "M").
            num_candles (int): Number of candles to fetch.
            sma_fast_period (int): Period for the fast Simple Moving Average.
            sma_slow_period (int): Period for the slow Simple Moving Average.
            ema_fast_period (int): Period for the fast Exponential Moving Average.
            ema_slow_period (int): Period for the slow Exponential Moving Average.
            rsi_period (int): Period for the Relative Strength Index.
            adx_period (int): Period for the Average Directional Index.
            bb_window (int): Window for Bollinger Bands.
            bb_std (int): Standard deviation for Bollinger Bands.
            macd_fast_period (int): Fast period for MACD.
            macd_slow_period (int): Slow period for MACD.
            macd_signal_period (int): Signal period for MACD.
            ichimoku_tenkan (int): Tenkan-sen period for Ichimoku.
            ichimoku_kijun (int): Kijun-sen period for Ichimoku.
            ichimoku_senkou (int): Senkou Span B period for Ichimoku.
            ehlers_fisher_period (int): Period for Ehlers Fisher Transform.
            ehlers_ssf_period (int): Period for Ehlers Super Smoother Filter.
            ob_percentage_threshold (float): Percentage threshold for a 'strong move' to confirm an order block.

        Returns:
            dict: A dictionary containing the comprehensive trend analysis summary.
        """
        logging.info(f"Starting trend analysis for {symbol} ({category}) on {interval} interval...")
        df = self.fetch_klines(category, symbol, interval, num_candles)

        if df.empty:
            return {"status": "error", "message": "Could not fetch enough kline data."}

        df = self.calculate_indicators(df,
                                       sma_fast_period, sma_slow_period,
                                       ema_fast_period, ema_slow_period,
                                       rsi_period, adx_period,
                                       bb_window, bb_std,
                                       macd_fast_period, macd_slow_period, macd_signal_period,
                                       ichimoku_tenkan, ichimoku_kijun, ichimoku_senkou,
                                       ehlers_fisher_period, ehlers_ssf_period,
                                       ob_percentage_threshold)

        # Determine the maximum lookback period required by all indicators
        max_lookback = max(sma_slow_period, rsi_period, adx_period, bb_window, macd_slow_period + macd_signal_period, ichimoku_senkou, ehlers_fisher_period, ehlers_ssf_period) # ichimoku_senkou is 52 by default

        # Drop rows with NaN values introduced by indicators to ensure latest_data is valid
        # This is important if num_candles is very low, not providing enough data for all indicator periods
        df_cleaned = df.dropna()

        if df_cleaned.empty or len(df_cleaned) < max_lookback:
            logging.error("DataFrame is empty or has insufficient data after dropping NaN values from indicators. "
                          "Increase num_candles or reduce indicator periods.")
            return {"status": "error", "message": "Not enough valid data after indicator calculation."}


        trend_analysis = self.analyze_trend(df_cleaned,
                                            sma_fast_period, sma_slow_period,
                                            rsi_period, adx_period,
                                            bb_window,
                                            macd_fast_period, macd_slow_period,
                                            ichimoku_tenkan, ichimoku_kijun,
                                            ehlers_fisher_period, ehlers_ssf_period,
                                            ob_percentage_threshold)

        trend_analysis["status"] = "success"
        trend_analysis["symbol"] = symbol
        trend_analysis["category"] = category
        trend_analysis["interval"] = interval
        trend_analysis["num_candles_fetched"] = len(df)
        trend_analysis["num_candles_analyzed"] = len(df_cleaned)

        return trend_analysis