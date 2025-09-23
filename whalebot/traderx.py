#!/data/data/com.termux/files/usr/bin/env python
from colorama import init, Fore, Back, Style
import ccxt.async_support as ccxt_async
import asyncio
import numpy as np
import pandas as pd
import termplotlib as tpl
import os
import json
import time
from datetime import datetime
import pandas_ta as ta  # The grimoire of indicators
import argparse

# Awaken Colorama to infuse the terminal with vibrant arcane hues
init(autoreset=True)

class PyrmethusTrader:
    def __init__(self):
        # Forge the gateway to Bybit's market realms
        self.exchange = ccxt_async.bybit() # Configured for public API access
        self.settings_path = '/data/data/com.termux/files/home/trader_settings.json'
        # Initialize default values before loading settings to ensure all attributes exist
        self.symbol = 'BTC/USDT'
        self.timeframe = '1h'
        self.limit = 100
        self.rsi_period = 14
        self.ema_period = 20
        self.backtest_indicators = ['RSI', 'MACD'] # Default indicators for backtest strategy
        self.vp_peak_price = None # Initialize vp_peak_price
        self.recent_high = 0
        self.recent_low = 0
        self.fib_levels = {}
        
        self.load_settings()  # Retrieve persisted wisdom from the ether
        self.data = pd.DataFrame()
        self.portfolio = {'capital': 10000.0, 'positions': {}} # Initial capital for backtesting
        self.trade_log_path = '/data/data/com.termux/files/home/trade_log.json'
        self.live_task = None # To manage the asyncio live task
        print(Fore.CYAN + Style.BRIGHT + "# Awakening Pyrmethus’ Enhanced Trading Terminal..." + Style.RESET_ALL)
        self.check_dependencies()

    def check_dependencies(self):
        """Invoke a spell to ensure Termux-API is present for special features like toasts and wake locks."""
        try:
            import termux_api # This will fail if the termux-api package is not installed for Python
            self.termux_api_available = True
            print(Fore.GREEN + "# Termux-API detected. Enchanted notifications and screen lock available." + Style.RESET_ALL)
        except ImportError:
            self.termux_api_available = False
            print(Fore.YELLOW + "# Termux-API not found. Termux-Toast notifications and wake-lock disabled." + Style.RESET_ALL)

    def load_settings(self):
        """Summon saved seeker preferences from the Termux grimoire (JSON file)."""
        try:
            if os.path.exists(self.settings_path):
                with open(self.settings_path, 'r') as f:
                    settings = json.load(f)
                    # Use .get() with current defaults to ensure compatibility with older settings files
                    self.symbol = settings.get('symbol', self.symbol)
                    self.timeframe = settings.get('timeframe', self.timeframe)
                    self.limit = settings.get('limit', self.limit)
                    self.rsi_period = settings.get('rsi_period', self.rsi_period)
                    self.ema_period = settings.get('ema_period', self.ema_period)
                    self.backtest_indicators = settings.get('backtest_indicators', self.backtest_indicators)
                    print(Fore.GREEN + "# Settings channeled from the grimoire." + Style.RESET_ALL)
            else:
                print(Fore.YELLOW + "# No grimoire found; default essences invoked." + Style.RESET_ALL)
        except Exception as e:
            print(Fore.RED + f"# Grimoire corruption: {str(e)}. Defaults restored." + Style.RESET_ALL)
            # Reset to original defaults on error without recursion
            self.symbol = 'BTC/USDT'
            self.timeframe = '1h'
            self.limit = 100
            self.rsi_period = 14
            self.ema_period = 20
            self.backtest_indicators = ['RSI', 'MACD']


    def save_settings(self):
        """Etch current essences into the Termux grimoire (JSON file)."""
        try:
            settings = {
                'symbol': self.symbol,
                'timeframe': self.timeframe,
                'limit': self.limit,
                'rsi_period': self.rsi_period,
                'ema_period': self.ema_period,
                'backtest_indicators': self.backtest_indicators
            }
            with open(self.settings_path, 'w') as f:
                json.dump(settings, f, indent=4)
            print(Fore.GREEN + "# Settings etched into the grimoire." + Style.RESET_ALL)
        except Exception as e:
            print(Fore.RED + f"# Failed to etch grimoire: {str(e)}" + Style.RESET_ALL)
    
    def log_trade(self, trade_data):
        """Etch a trade record into the sacred journal (JSON file)."""
        # Ensure the directory exists for the trade log
        log_dir = os.path.dirname(self.trade_log_path)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        log_data = []
        if os.path.exists(self.trade_log_path):
            with open(self.trade_log_path, 'r') as f:
                try:
                    log_data = json.load(f)
                except json.JSONDecodeError:
                    log_data = [] # Handle empty or corrupt JSON file gracefully
        
        log_data.append(trade_data)
        
        with open(self.trade_log_path, 'w') as f:
            json.dump(log_data, f, indent=4)
        print(Fore.MAGENTA + f"# Trade logged: {trade_data['type']} {trade_data['symbol']} @ {trade_data['price']:.2f} (Time: {trade_data['timestamp']})" + Style.RESET_ALL)

    async def load_markets(self):
        """Unveil the exchange’s market spirits, with wards against the void."""
        try:
            await self.exchange.load_markets()
            print(Fore.GREEN + "# Markets unveiled from the digital void." + Style.RESET_ALL)
        except Exception as e:
            print(Fore.RED + f"# Ether disruption during market load: {str(e)}" + Style.RESET_ALL)

    async def fetch_klines(self):
        """Summon historical kline essences, shielded from failure and rate limits."""
        print(Fore.CYAN + f"# Channeling {self.symbol} candles (timeframe: {self.timeframe}, limit: {self.limit})..." + Style.RESET_ALL)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                klines = await self.exchange.fetch_ohlcv(self.symbol, self.timeframe, limit=self.limit)
                self.data = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                self.data['timestamp'] = pd.to_datetime(self.data['timestamp'], unit='ms')
                
                # Check for empty data before proceeding
                if self.data.empty:
                    print(Fore.YELLOW + f"# No candles received for {self.symbol} {self.timeframe}. Attempt {attempt + 1}/{max_retries}." + Style.RESET_ALL)
                    if attempt < max_retries - 1:
                        await asyncio.sleep(5) # Wait before retrying
                        continue
                    else:
                        print(Fore.RED + "# Failed to conjure candles after multiple attempts." + Style.RESET_ALL)
                        return # Exit if no data after retries

                print(Fore.GREEN + f"# {len(self.data)} candles conjured." + Style.RESET_ALL)
                self.calculate_indicators()
                return # Success, exit loop
            except ccxt_async.RateLimitExceeded as e:
                print(Fore.RED + f"# Rate limit exceeded: {str(e)}. Waiting 30 seconds before retry {attempt + 1}/{max_retries}..." + Style.RESET_ALL)
                await asyncio.sleep(30)
            except ccxt.ExchangeError as e:
                # Catch specific exchange errors like invalid symbol
                print(Fore.RED + f"# Exchange error during kline summoning: {str(e)}. Attempt {attempt + 1}/{max_retries}." + Style.RESET_ALL)
                if "invalid symbol" in str(e).lower() or "not found" in str(e).lower() or "wrong symbol" in str(e).lower():
                    print(Fore.RED + f"# Invalid symbol '{self.symbol}'. Please check your input." + Style.RESET_ALL)
                    return # Do not retry for an invalid symbol
                await asyncio.sleep(5) # Wait before retrying for other exchange errors
            except Exception as e:
                print(Fore.RED + f"# Kline summoning failed unexpectedly: {str(e)}. Attempt {attempt + 1}/{max_retries}." + Style.RESET_ALL)
                await asyncio.sleep(5) # Wait before retrying
        
        print(Fore.RED + "# Failed to fetch klines after maximum retries." + Style.RESET_ALL)

    def calculate_indicators(self):
        """Forge all indicators with pandas-ta's arcane power, now with Volume Profile and Fibonacci refinement."""
        if self.data.empty:
            print(Fore.RED + "# No essences to enchant, data is empty." + Style.RESET_ALL)
            return
        try:
            # Core indicators
            self.data.ta.rsi(length=self.rsi_period, append=True)
            self.data.ta.ema(length=self.ema_period, append=True)
            self.data.ta.macd(fast=12, slow=26, signal=9, append=True)
            self.data.ta.bbands(length=20, std=2, append=True)
            self.data.ta.supertrend(length=7, multiplier=3, append=True)
            self.data.ta.ichimoku(tenkan=9, kijun=26, senkou=52, append=True)
            self.data.ta.stoch(k=14, d=3, smooth_k=3, append=True)
            self.data.ta.ema(length=50, append=True, col_names=('EMA_50',)) # 50 EMA for crossover
            self.data.ta.ema(length=200, append=True, col_names=('EMA_200',)) # 200 EMA for crossover
            
            # Volume Profile: Extract profile and bins, store peak for signals
            # Ensure sufficient data for volume profile (e.g., at least 10 bars for 10 bins)
            if len(self.data) >= 10:
                vp_result = self.data.ta.vp(bins=10)  # Returns (profile, bins)
                if isinstance(vp_result, tuple) and not vp_result[0].empty:
                    self.vp_peak_price = vp_result[0].idxmax() # Peak volume price
                else:
                    self.vp_peak_price = None
            else:
                self.vp_peak_price = None
                print(Fore.YELLOW + "# Not enough data for Volume Profile calculation." + Style.RESET_ALL)
            
            # Identify recent swing high/low for Fibonacci, ensuring enough data
            # Using last 100 bars for Fibonacci range for robustness
            if len(self.data) >= 100: 
                self.recent_high = self.data['high'].iloc[-100:].max()
                self.recent_low = self.data['low'].iloc[-100:].min()
                self.fib_levels = self.calculate_fibonacci(self.recent_high, self.recent_low)
            elif not self.data.empty: # If less than 100 bars, use available max/min
                self.recent_high = self.data['high'].max()
                self.recent_low = self.data['low'].min()
                self.fib_levels = self.calculate_fibonacci(self.recent_high, self.recent_low)
                print(Fore.YELLOW + "# Not enough data for full Fibonacci calculation based on recent 100 bars." + Style.RESET_ALL)
            else:
                self.recent_high = 0
                self.recent_low = 0
                self.fib_levels = {}
                print(Fore.YELLOW + "# No data for Fibonacci calculation." + Style.RESET_ALL)

            print(Fore.YELLOW + "# Indicators forged: RSI, EMA, MACD, BBands, Supertrend, Ichimoku, Stochastic, Volume Profile, Fibonacci." + Style.RESET_ALL)
        except Exception as e:
            print(Fore.RED + f"# Indicator forging disrupted: {str(e)}" + Style.RESET_ALL)

    def calculate_fibonacci(self, high, low):
        """Calculate the sacred Fibonacci retracement levels."""
        diff = high - low
        # Standard Fibonacci Retracement Levels
        levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1] 
        fib_levels = {f"{int(level*100)}%": high - (diff * level) for level in levels}
        return fib_levels

    def generate_signals(self):
        """Divine enhanced signals, now drawing from Volume Profile depths, EMA Crossovers, and Divergences."""
        signals = []
        # Ensure enough data for all relevant indicators to be calculated
        min_data_for_signals = max(self.rsi_period, self.ema_period, 26, 52, 200, 2) # Ichimoku needs 52, EMAs 200, Divergence 2
        if self.data.empty or len(self.data) < min_data_for_signals: 
            return signals
        
        last_row = self.data.iloc[-1]
        prev_row = self.data.iloc[-2] # For crossovers and divergences

        # RSI signals
        if 'RSI_14' in last_row and not pd.isna(last_row['RSI_14']):
            if last_row['RSI_14'] < 30:
                signals.append((Fore.GREEN + "BUY" + Style.RESET_ALL, f"RSI Oversold ({last_row['RSI_14']:.2f})"))
            elif last_row['RSI_14'] > 70:
                signals.append((Fore.RED + "SELL" + Style.RESET_ALL, f"RSI Overbought ({last_row['RSI_14']:.2f})"))
        
        # MACD signals
        if 'MACD_12_26_9' in last_row and 'MACDs_12_26_9' in last_row and \
           not pd.isna(last_row['MACD_12_26_9']) and not pd.isna(last_row['MACDs_12_26_9']):
            if last_row['MACD_12_26_9'] > last_row['MACDs_12_26_9'] and prev_row['MACD_12_26_9'] <= prev_row['MACDs_12_26_9']:
                signals.append((Fore.GREEN + "BUY" + Style.RESET_ALL, "MACD Bullish Crossover"))
            elif last_row['MACD_12_26_9'] < last_row['MACDs_12_26_9'] and prev_row['MACD_12_26_9'] >= prev_row['MACDs_12_26_9']:
                signals.append((Fore.RED + "SELL" + Style.RESET_ALL, "MACD Bearish Crossover"))
        
        # Bollinger Bands signals
        if 'BBL_20_2.0' in last_row and 'BBU_20_2.0' in last_row and \
           not pd.isna(last_row['BBL_20_2.0']) and not pd.isna(last_row['BBU_20_2.0']):
            if last_row['close'] < last_row['BBL_20_2.0']:
                signals.append((Fore.GREEN + "BUY" + Style.RESET_ALL, "Bollinger Bands Oversold"))
            elif last_row['close'] > last_row['BBU_20_2.0']:
                signals.append((Fore.RED + "SELL" + Style.RESET_ALL, "Bollinger Bands Overbought"))
        
        # Supertrend signals
        if 'SUPERT_7_3.0' in last_row and not pd.isna(last_row['SUPERT_7_3.0']):
            if last_row['close'] > last_row['SUPERT_7_3.0']:
                signals.append((Fore.GREEN + "BUY" + Style.RESET_ALL, "Supertrend Bullish"))
            elif last_row['close'] < last_row['SUPERT_7_3.0']:
                signals.append((Fore.RED + "SELL" + Style.RESET_ALL, "Supertrend Bearish"))
        
        # EMA signals
        if 'EMA_20' in last_row and not pd.isna(last_row['EMA_20']):
            if last_row['close'] > last_row['EMA_20']:
                signals.append((Fore.GREEN + "BUY" + Style.RESET_ALL, "Price above EMA"))
            elif last_row['close'] < last_row['EMA_20']:
                signals.append((Fore.RED + "SELL" + Style.RESET_ALL, "Price below EMA"))
        
        # Ichimoku signals
        if all(x in last_row for x in ['ISA_9', 'ISB_26', 'ICS_26']) and \
           all(not pd.isna(last_row[x]) for x in ['ISA_9', 'ISB_26', 'ICS_26']):
            cloud_top = max(last_row['ISA_9'], last_row['ISB_26'])
            cloud_bottom = min(last_row['ISA_9'], last_row['ISB_26'])
            if last_row['close'] > cloud_top and last_row['ICS_26'] > last_row['close']:
                signals.append((Fore.GREEN + "BUY" + Style.RESET_ALL, "Ichimoku Bullish Cloud Breakout"))
            elif last_row['close'] < cloud_bottom and last_row['ICS_26'] < last_row['close']:
                signals.append((Fore.RED + "SELL" + Style.RESET_ALL, "Ichimoku Bearish Cloud Breakdown"))
        
        # Stochastic signals
        if 'STOCHk_14_3_3' in last_row and 'STOCHd_14_3_3' in last_row and \
           not pd.isna(last_row['STOCHk_14_3_3']) and not pd.isna(last_row['STOCHd_14_3_3']):
            if last_row['STOCHk_14_3_3'] > last_row['STOCHd_14_3_3'] and last_row['STOCHk_14_3_3'] < 20:
                signals.append((Fore.GREEN + "BUY" + Style.RESET_ALL, f"Stochastic Oversold Crossover ({last_row['STOCHk_14_3_3']:.2f})"))
            elif last_row['STOCHk_14_3_3'] < last_row['STOCHd_14_3_3'] and last_row['STOCHk_14_3_3'] > 80:
                signals.append((Fore.RED + "SELL" + Style.RESET_ALL, f"Stochastic Overbought Crossover ({last_row['STOCHk_14_3_3']:.2f})"))
        
        # Volume Profile signals: If price is near the peak volume, suggesting potential support/resistance.
        if self.vp_peak_price is not None and not pd.isna(self.vp_peak_price):
            vp_tolerance = last_row['close'] * 0.005  # 0.5% tolerance
            if abs(last_row['close'] - self.vp_peak_price) < vp_tolerance:
                signals.append((Fore.CYAN + "NEUTRAL" + Style.RESET_ALL, f"Price near High-Volume Node ({self.vp_peak_price:.2f}) - Potential Support/Resistance"))
        
        # EMA Crossover signals (Golden/Death Cross)
        if all(x in last_row for x in ['EMA_50', 'EMA_200']) and \
           all(x in prev_row for x in ['EMA_50', 'EMA_200']) and \
           not pd.isna(last_row['EMA_50']) and not pd.isna(last_row['EMA_200']) and \
           not pd.isna(prev_row['EMA_50']) and not pd.isna(prev_row['EMA_200']):
            if last_row['EMA_50'] > last_row['EMA_200'] and prev_row['EMA_50'] <= prev_row['EMA_200']:
                signals.append((Fore.GREEN + "BUY" + Style.RESET_ALL, "Golden Cross (50/200 EMA)"))
            elif last_row['EMA_50'] < last_row['EMA_200'] and prev_row['EMA_50'] >= prev_row['EMA_200']:
                signals.append((Fore.RED + "SELL" + Style.RESET_ALL, "Death Cross (50/200 EMA)"))

        # Divergence signals (simplified example, more robust logic would involve identifying multiple peaks/troughs)
        if 'RSI_14' in last_row and 'RSI_14' in prev_row and \
           not pd.isna(last_row['RSI_14']) and not pd.isna(prev_row['RSI_14']):
            if last_row['close'] > prev_row['close'] and last_row['RSI_14'] < prev_row['RSI_14']:
                signals.append((Fore.RED + "SELL" + Style.RESET_ALL, "Bearish Divergence (Price Higher, RSI Lower)"))
            if last_row['close'] < prev_row['close'] and last_row['RSI_14'] > prev_row['RSI_14']:
                signals.append((Fore.GREEN + "BUY" + Style.RESET_ALL, "Bullish Divergence (Price Lower, RSI Higher)"))

        return signals

    def render_ascii_chart(self):
        """Weave vibrant ASCII tapestries of market essences, now with toggled layers and improved data checks."""
        if self.data.empty:
            print(Fore.RED + "# No essences to weave for chart." + Style.RESET_ALL)
            return
        
        # Ensure enough data for plotting (e.g., last 30 bars minimum for reasonable chart)
        chart_length = min(len(self.data), 30)
        if chart_length < 2: # Need at least two points to plot a line
            print(Fore.YELLOW + f"# Insufficient data to render an ASCII chart (needs at least 2 bars). Current: {len(self.data)}" + Style.RESET_ALL)
            return

        data_to_plot = self.data.iloc[-chart_length:].copy() # Use a copy to avoid SettingWithCopyWarning
        
        try:
            # Main price chart with EMA and Ichimoku Senkou
            fig = tpl.figure()
            x = data_to_plot['timestamp'].dt.strftime('%m-%d %H:%M').values
            y_price = data_to_plot['close'].values
            
            # Plot only if indicator columns exist and are not all NaN for the current slice
            plots = [(y_price, 'Price')]
            if 'EMA_20' in data_to_plot.columns and not data_to_plot['EMA_20'].isnull().all():
                plots.append((data_to_plot['EMA_20'].values, 'EMA'))
            if 'ISA_9' in data_to_plot.columns and not data_to_plot['ISA_9'].isnull().all():
                plots.append((data_to_plot['ISA_9'].values, 'Senkou A'))
            if 'ISB_26' in data_to_plot.columns and not data_to_plot['ISB_26'].isnull().all():
                plots.append((data_to_plot['ISB_26'].values, 'Senkou B'))

            for y_vals, label in plots:
                fig.plot(x, y_vals, label=label, width=80, height=15)
            
            print(Fore.CYAN + Style.BRIGHT + "\n# Market Chart (Price, EMA, Ichimoku Cloud):" + Style.RESET_ALL)
            print(fig.get_string())
            
            # Stochastic sub-chart
            if 'STOCHk_14_3_3' in data_to_plot.columns and 'STOCHd_14_3_3' in data_to_plot.columns and \
               not data_to_plot['STOCHk_14_3_3'].isnull().all() and not data_to_plot['STOCHd_14_3_3'].isnull().all():
                stoch_fig = tpl.figure()
                y_stoch_k = data_to_plot['STOCHk_14_3_3'].values
                y_stoch_d = data_to_plot['STOCHd_14_3_3'].values
                stoch_fig.plot(x, y_stoch_k, label='%K', width=80, height=10)
                stoch_fig.plot(x, y_stoch_d, label='%D', width=80, height=10)
                print(Fore.CYAN + Style.BRIGHT + "\n# Stochastic Oscillator Chart:" + Style.RESET_ALL)
                print(stoch_fig.get_string())
            else:
                print(Fore.YELLOW + "\n# Stochastic data not available or insufficient for charting." + Style.RESET_ALL)
            
            # Volume Profile horizontal bar (top 5 bins for clarity)
            # Recalculate VP for the plotted subset to ensure it matches the chart view
            if len(data_to_plot) >= 10: # Minimum data points for 10 bins
                vp_result_plot = data_to_plot.ta.vp(bins=10)
                if isinstance(vp_result_plot, tuple) and not vp_result_plot[0].empty:
                    profile_plot, bins_plot = vp_result_plot
                    top_vp = profile_plot.sort_values(ascending=False).head(5)
                    vp_fig = tpl.figure()
                    # Ensure x-axis labels are strings for termplotlib's barh
                    vp_fig.barh([f"{price:.2f}" for price in top_vp.index.tolist()], top_vp.values.tolist(), label='Volume')
                    print(Fore.CYAN + Style.BRIGHT + "\n# Volume Profile (Top Bins for Chart Period):" + Style.RESET_ALL)
                    print(vp_fig.get_string())
                else:
                    print(Fore.YELLOW + "\n# Volume Profile data not available or insufficient for charting." + Style.RESET_ALL)
            else:
                print(Fore.YELLOW + "\n# Not enough data for Volume Profile chart." + Style.RESET_ALL)

        except Exception as e:
            print(Fore.RED + f"# Chart weaving unraveled: {str(e)}" + Style.RESET_ALL)

    async def display_analysis(self):
        """Reveal the market’s secrets in glowing hues, with enhanced depth and Termux-Toast notifications."""
        if self.data.empty:
            print(Fore.RED + "# No secrets to unveil, data is empty." + Style.RESET_ALL)
            return
        
        # Ensure enough data for indicators to be present. Use the maximum lookback period needed.
        min_data_for_display = max(self.rsi_period, self.ema_period, 26, 52, 200, 100) # Ichimoku 52, EMA 200, Fibonacci 100
        if len(self.data) < min_data_for_display:
            print(Fore.YELLOW + f"# Not enough data to generate full indicator analysis (needs at least {min_data_for_display} bars). Current: {len(self.data)}" + Style.RESET_ALL)
            return

        signals = self.generate_signals()
        last_row = self.data.iloc[-1]
        print(Fore.MAGENTA + Style.BRIGHT + "\n# Pyrmethus’ Enhanced Market Divination" + Style.RESET_ALL)
        print(Fore.BLUE + f"Symbol: {self.symbol} | Timeframe: {self.timeframe} | Last Price: {last_row['close']:.2f}" + Style.RESET_ALL)
        
        # Display Fibonacci Levels if calculated
        if self.fib_levels:
            print(Fore.YELLOW + f"Fibonacci Retracements (High: {self.recent_high:.2f}, Low: {self.recent_low:.2f}):" + Style.RESET_ALL)
            for level, price in self.fib_levels.items():
                print(f"  - {level}: {price:.2f}")
        else:
            print(Fore.YELLOW + "# Fibonacci levels not calculated due to insufficient data." + Style.RESET_ALL)

        # Display key indicator values, checking for existence and non-NaN values first
        def print_indicator(label, key, suffix=""):
            if key in last_row and not pd.isna(last_row[key]):
                print(Fore.YELLOW + f"{label}: {last_row[key]:.2f}{suffix}" + Style.RESET_ALL)
            else:
                print(Fore.YELLOW + f"{label}: N/A" + Style.RESET_ALL)

        print_indicator("RSI", 'RSI_14')
        print_indicator(f"EMA-{self.ema_period}", 'EMA_20')
        if all(x in last_row for x in ['MACD_12_26_9', 'MACDs_12_26_9']) and \
           all(not pd.isna(last_row[x]) for x in ['MACD_12_26_9', 'MACDs_12_26_9']):
             print(Fore.YELLOW + f"MACD: {last_row['MACD_12_26_9']:.2f}, Signal: {last_row['MACDs_12_26_9']:.2f}" + Style.RESET_ALL)
        else:
            print(Fore.YELLOW + "MACD: N/A" + Style.RESET_ALL)
        if all(x in last_row for x in ['BBU_20_2.0', 'BBM_20_2.0', 'BBL_20_2.0']) and \
           all(not pd.isna(last_row[x]) for x in ['BBU_20_2.0', 'BBM_20_2.0', 'BBL_20_2.0']):
            print(Fore.YELLOW + f"Bollinger Bands: Upper {last_row['BBU_20_2.0']:.2f}, Middle {last_row['BBM_20_2.0']:.2f}, Lower {last_row['BBL_20_2.0']:.2f}" + Style.RESET_ALL)
        else:
            print(Fore.YELLOW + "Bollinger Bands: N/A" + Style.RESET_ALL)
        print_indicator("Supertrend", 'SUPERT_7_3.0')
        if all(x in last_row for x in ['ITS_9', 'IKS_26', 'ISA_9', 'ISB_26', 'ICS_26']) and \
           all(not pd.isna(last_row[x]) for x in ['ITS_9', 'IKS_26', 'ISA_9', 'ISB_26', 'ICS_26']):
            print(Fore.YELLOW + f"Ichimoku: Tenkan {last_row['ITS_9']:.2f}, Kijun {last_row['IKS_26']:.2f}, Senkou A {last_row['ISA_9']:.2f}, Senkou B {last_row['ISB_26']:.2f}, Chikou {last_row['ICS_26']:.2f}" + Style.RESET_ALL)
        else:
            print(Fore.YELLOW + "Ichimoku: N/A" + Style.RESET_ALL)
        if all(x in last_row for x in ['STOCHk_14_3_3', 'STOCHd_14_3_3']) and \
           all(not pd.isna(last_row[x]) for x in ['STOCHk_14_3_3', 'STOCHd_14_3_3']):
            print(Fore.YELLOW + f"Stochastic: %K {last_row['STOCHk_14_3_3']:.2f}, %D {last_row['STOCHd_14_3_3']:.2f}" + Style.RESET_ALL)
        else:
            print(Fore.YELLOW + "Stochastic: N/A" + Style.RESET_ALL)
                    price_str = f"{self.vp_peak_price:.2f}" if self.vp_peak_price is not None else "None"
            print(Fore.YELLOW + f"Volume Profile Peak: {price_str}" + Style.RESET_ALL)
        
        # Display signals and send Termux-Toast notifications
        if signals:
            print(Fore.GREEN + "# Trading Signals from the Void:" + Style.RESET_ALL)
            for signal_type, reason in signals:
                print(f"  - {signal_type}: {reason}")
                if self.termux_api_available:
                    # Limit toast message length to avoid truncation and ensure clarity
                    toast_msg = f"{signal_type.replace(Style.RESET_ALL, '')}: {reason}"[:100]
                    os.system(f'termux-toast "{toast_msg}"')
        else:
            print(Fore.YELLOW + "# The void whispers silence... for now." + Style.RESET_ALL)

    async def live_updates(self):
        """Stream live essences with resilient wards via WebSocket-like polling and Termux integration."""
        # Note: ccxt's watch_ticker method typically uses polling for most exchanges,
        # which means it fetches new data at intervals rather than true push-based websockets.
        # For true websocket streaming, a dedicated library (e.g., python-bybit) would be more efficient,
        # but the current implementation adheres to maintaining ccxt's async API as requested.
        print(Fore.GREEN + "# Activating live market stream..." + Style.RESET_ALL)
        async with self.exchange:
            while True:
                try:
                    ticker = await self.exchange.watch_ticker(self.symbol)
                    price = ticker['last']
                    timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    # Using '\r' to overwrite the current line, creating a "spinning" effect
                    print(Fore.GREEN + f"# Live Essence: {self.symbol} @ {price:.2f} | {timestamp_str}" + Style.RESET_ALL, end='\r')
                    await asyncio.sleep(self.exchange.rateLimit / 1000) # Respect exchange rate limits
                except asyncio.CancelledError:
                    print(Fore.MAGENTA + "\n# Live stream enchantment cancelled." + Style.RESET_ALL)
                    break # Exit loop if task is cancelled
                except Exception as e:
                    print(Fore.RED + f"\n# Live stream disrupted: {str(e)}. Attempting to rechannel in 5 seconds..." + Style.RESET_ALL)
                    if self.termux_api_available:
                        # Send a toast notification about the disruption
                        os.system(f'termux-toast "Live Stream Disrupted: {str(e)[:50]}..." -b red -c white')
                    await asyncio.sleep(5)

    def backtest_strategy(self):
        """Invoke an enhanced backtest, with fees, slippage, position tracking, and risk divination."""
        if self.data.empty:
            print(Fore.RED + "# No history to divine for backtest." + Style.RESET_ALL)
            return
        
        # Ensure sufficient data for backtesting (e.g., at least 200 bars for 200 EMA and other indicators)
        min_data_needed = max(200, self.rsi_period, self.ema_period, 26, 52) 
        if len(self.data) < min_data_needed:
            print(Fore.YELLOW + f"# Insufficient data for a meaningful backtest (needs at least {min_data_needed} bars). Current: {len(self.data)}" + Style.RESET_ALL)
            return

        try:
            # Create a working copy of the data for backtesting
            backtest_data = self.data.copy()
            
            # Initialize columns for backtesting
            backtest_data['signal'] = 0  # 1: Long entry, -1: Short entry, 0: No new signal
            backtest_data['position'] = 0 # 1: Long, -1: Short, 0: Cash (reflects holding state)
            
            # Portfolio tracking for backtest
            initial_capital = self.portfolio['capital']
            
            # Slippage and fees
            slippage = 0.001    # 0.1% slippage per trade
            fee = 0.00075       # 0.075% fee per trade
            
            print(Fore.CYAN + Style.BRIGHT + "\n# Commencing Backtest Divination..." + Style.RESET_ALL)
            
            # Initialize equity curve (for Sharpe and Max Drawdown)
            equity_curve = pd.Series(index=backtest_data.index)
            equity_curve.iloc[0] = initial_capital
            
            current_shares_held = 0.0 # Number of shares currently held (positive for long, negative for short)
            current_cash = initial_capital # Cash available

            for i in range(1, len(backtest_data)):
                # Ensure we have enough past data to calculate indicators for the current bar 'i'
                # This check ensures that indicators don't produce NaNs that break signal logic
                if i < max(self.rsi_period, self.ema_period, 26, 52, 200): # Min lookback for any indicator
                    equity_curve.iloc[i] = equity_curve.iloc[i-1] # No trading, keep equity
                    continue

                current_bar = backtest_data.iloc[i]
                prev_bar = backtest_data.iloc[i-1]

                buy_signals_count = 0
                sell_signals_count = 0
                
                # --- Dynamic Signal Generation based on self.backtest_indicators ---
                # Check if current_bar has valid data for indicators
                # This part is a simplified signal generation for backtest
                # A more complex backtest would call a stripped-down `generate_signals` for each bar.
                # For this exercise, we will directly check indicator values as per user settings.

                # RSI Logic for Backtest
                if 'RSI' in self.backtest_indicators and 'RSI_14' in current_bar and not pd.isna(current_bar['RSI_14']):
                    if current_bar['RSI_14'] < 30: buy_signals_count += 1
                    elif current_bar['RSI_14'] > 70: sell_signals_count += 1
                
                # MACD Logic for Backtest
                if 'MACD' in self.backtest_indicators and \
                   'MACD_12_26_9' in current_bar and 'MACDs_12_26_9' in current_bar and \
                   'MACD_12_26_9' in prev_bar and 'MACDs_12_26_9' in prev_bar and \
                   not pd.isna(current_bar['MACD_12_26_9']) and not pd.isna(current_bar['MACDs_12_26_9']):
                    if current_bar['MACD_12_26_9'] > current_bar['MACDs_12_26_9'] and prev_bar['MACD_12_26_9'] <= prev_bar['MACDs_12_26_9']: buy_signals_count += 1
                    elif current_bar['MACD_12_26_9'] < current_bar['MACDs_12_26_9'] and prev_bar['MACD_12_26_9'] >= prev_bar['MACDs_12_26_9']: sell_signals_count += 1

                # EMA Crossover Logic (50/200 EMA) for Backtest
                if 'EMA_CROSS' in self.backtest_indicators and \
                   all(col in current_bar for col in ['EMA_50', 'EMA_200']) and \
                   all(col in prev_bar for col in ['EMA_50', 'EMA_200']) and \
                   not pd.isna(current_bar['EMA_50']) and not pd.isna(current_bar['EMA_200']):
                    if current_bar['EMA_50'] > current_bar['EMA_200'] and prev_bar['EMA_50'] <= prev_bar['EMA_200']:
                        buy_signals_count += 1
                    elif current_bar['EMA_50'] < current_bar['EMA_200'] and prev_bar['EMA_50'] >= prev_bar['EMA_200']:
                        sell_signals_count += 1
                
                # --- Trading Logic with Position Tracking and P&L Calculation ---
                
                trade_price = current_bar['close'] # Execute trade at close of the signal bar

                # Update current portfolio value before potential trade for accurate P&L
                # This includes value of cash + value of held shares
                portfolio_value_before_trade = current_cash + (current_shares_held * trade_price)
                
                # Default to no position change
                backtest_data.loc[backtest_data.index[i], 'position'] = backtest_data.loc[backtest_data.index[i-1], 'position']
                
                # BUY Signal (go long or cover short to go long)
                if buy_signals_count > sell_signals_count and backtest_data.loc[backtest_data.index[i-1], 'position'] <= 0:
                    if backtest_data.loc[backtest_data.index[i-1], 'position'] < 0: # Currently short, cover short first
                        # Profit/Loss from covering short
                        profit_loss_from_short_cover = (prev_bar['close'] - trade_price) * abs(current_shares_held)
                        current_cash += profit_loss_from_short_cover - (abs(current_shares_held) * trade_price * (slippage + fee))
                        self.log_trade({'type': 'COVER_SHORT', 'symbol': self.symbol, 'price': trade_price, 
                                        'timestamp': str(current_bar['timestamp']), 'qty_covered': abs(current_shares_held), 
                                        'P/L': profit_loss_from_short_cover, 'cash_after': current_cash, 'signal_reason': 'Backtest'})
                        current_shares_held = 0.0 # No longer short

                    # Open new long position (use all available cash)
                    amount_to_buy = current_cash / (trade_price * (1 + slippage + fee))
                    if amount_to_buy * trade_price > 0.001 * initial_capital : # Only trade if significant amount (e.g., >0.1% of initial capital)
                        current_cash -= amount_to_buy * trade_price * (1 + slippage + fee)
                        current_shares_held += amount_to_buy
                        backtest_data.loc[backtest_data.index[i], 'signal'] = 1
                        backtest_data.loc[backtest_data.index[i], 'position'] = 1 # Mark as long
                        self.log_trade({'type': 'BUY', 'symbol': self.symbol, 'price': trade_price, 
                                        'timestamp': str(current_bar['timestamp']), 'qty': amount_to_buy, 
                                        'cash_after': current_cash, 'signal_reason': 'Backtest'})

                # SELL Signal (go short or sell long to go short)
                elif sell_signals_count > buy_signals_count and backtest_data.loc[backtest_data.index[i-1], 'position'] >= 0:
                    if backtest_data.loc[backtest_data.index[i-1], 'position'] > 0: # Currently long, sell long first
                        # Profit/Loss from selling long
                        profit_loss_from_long_sell = (trade_price - prev_bar['close']) * current_shares_held
                        current_cash += (current_shares_held * trade_price) - (current_shares_held * trade_price * (slippage + fee))
                        self.log_trade({'type': 'SELL_LONG', 'symbol': self.symbol, 'price': trade_price, 
                                        'timestamp': str(current_bar['timestamp']), 'qty_sold': current_shares_held, 
                                        'P/L': profit_loss_from_long_sell, 'cash_after': current_cash, 'signal_reason': 'Backtest'})
                        current_shares_held = 0.0 # No longer long

                    # Open new short position (short an amount equal to initial capital in value)
                    amount_to_short = initial_capital / (trade_price * (1 + slippage + fee))
                    if amount_to_short * trade_price > 0.001 * initial_capital: # Only trade if significant amount
                        current_cash += amount_to_short * trade_price * (1 - slippage - fee) # Funds received from shorting
                        current_shares_held -= amount_to_short # Shares held becomes negative
                        backtest_data.loc[backtest_data.index[i], 'signal'] = -1
                        backtest_data.loc[backtest_data.index[i], 'position'] = -1 # Mark as short
                        self.log_trade({'type': 'SHORT', 'symbol': self.symbol, 'price': trade_price, 
                                        'timestamp': str(current_bar['timestamp']), 'qty': amount_to_short, 
                                        'cash_after': current_cash, 'signal_reason': 'Backtest'})
                
                # Update equity curve at the end of the bar, after any potential trade
                equity_curve.iloc[i] = current_cash + (current_shares_held * trade_price)
            
            # Final close all open positions at the last available price
            last_price = backtest_data.iloc[-1]['close']
            if current_shares_held > 0: # Close long position
                profit_loss_final = (last_price - backtest_data.iloc[-2]['close']) * current_shares_held # P/L for the last held period
                current_cash += (current_shares_held * last_price) - (current_shares_held * last_price * (slippage + fee))
                self.log_trade({'type': 'FINAL_SELL_LONG', 'symbol': self.symbol, 'price': last_price, 
                                'timestamp': str(backtest_data.iloc[-1]['timestamp']), 'qty_sold': current_shares_held, 
                                'P/L': profit_loss_final, 'cash_after': current_cash, 'reason': 'End of Backtest'})
                current_shares_held = 0.0
            elif current_shares_held < 0: # Close short position
                profit_loss_final = (backtest_data.iloc[-2]['close'] - last_price) * abs(current_shares_held) # P/L for the last held period
                current_cash += profit_loss_final - (abs(current_shares_held) * last_price * (slippage + fee)) # Cost to cover short
                self.log_trade({'type': 'FINAL_COVER_SHORT', 'symbol': self.symbol, 'price': last_price, 
                                'timestamp': str(backtest_data.iloc[-1]['timestamp']), 'qty_covered': abs(current_shares_held), 
                                'P/L': profit_loss_final, 'cash_after': current_cash, 'reason': 'End of Backtest'})
                current_shares_held = 0.0
            
            # Final portfolio value after closing all positions
            final_portfolio_value = current_cash

            # Calculate strategy returns from the equity curve for Sharpe and Drawdown
            backtest_data['strategy_returns'] = equity_curve.pct_change().fillna(0) # Fill NaN from first value
            
            cumulative_returns = (final_portfolio_value / initial_capital) - 1
            
            # Sharpe Ratio (assuming a risk-free rate of 0.02 annualized)
            mean_ret = backtest_data['strategy_returns'].mean()
            std_ret = backtest_data['strategy_returns'].std()
            
            # Adjust annualization factor based on timeframe for Sharpe Ratio
            annualization_factor = {
                '1m': 60 * 24 * 365, '5m': 12 * 24 * 365, '15m': 4 * 24 * 365,
                '30m': 2 * 24 * 365, '1h': 24 * 365, '2h': 12 * 365,
                '4h': 6 * 365, '6h': 4 * 365, '8h': 3 * 365,
                '12h': 2 * 365, '1d': 365, '3d': 365/3,
                '1w': 52, '1M': 12
            }.get(self.timeframe, 252) # Default to 252 for daily if timeframe not mapped
            
            risk_free_rate_per_period = (0.02 / annualization_factor) # Annualized 2% risk-free rate
            
            sharpe = (mean_ret - risk_free_rate_per_period) / std_ret * np.sqrt(annualization_factor) if std_ret != 0 else 0
            
            # Max Drawdown
            # Calculate cumulative wealth from the percentage returns of the equity curve
            cumulative_wealth = (1 + backtest_data['strategy_returns']).cumprod()
            peak = cumulative_wealth.cummax()
            drawdown = (cumulative_wealth - peak) / peak
            max_drawdown = drawdown.min() if not drawdown.empty else 0
            
            print(Fore.GREEN + Style.BRIGHT + f"# Backtest Divined:" + Style.RESET_ALL)
            print(Fore.GREEN + f"  - Initial Capital: {initial_capital:.2f}" + Style.RESET_ALL)
            print(Fore.GREEN + f"  - Final Portfolio Value: {final_portfolio_value:.2f}" + Style.RESET_ALL)
            print(Fore.GREEN + f"  - Cumulative Return: {cumulative_returns:.2%}" + Style.RESET_ALL)
            print(Fore.GREEN + f"  - Sharpe Ratio: {sharpe:.2f}" + Style.RESET_ALL)
            print(Fore.GREEN + f"  - Max Drawdown: {abs(max_drawdown):.2%}" + Style.RESET_ALL)
            print(Fore.GREEN + f"  - Total Trades Logged: {len(pd.read_json(self.trade_log_path)) if os.path.exists(self.trade_log_path) else 0}" + Style.RESET_ALL)
            
        except Exception as e:
            print(Fore.RED + f"# Backtest vision clouded: {str(e)}" + Style.RESET_ALL)
            import traceback
            traceback.print_exc() # For detailed debugging information

    async def run(self):
        """Cast the main incantation, now with backtest, save, and enhanced commands."""
        await self.load_markets()
        await self.fetch_klines()
        self.render_ascii_chart()
        await self.display_analysis()

        print(Fore.BLUE + Style.BRIGHT + "\n# Command the Ether (type 'help' for incantations):" + Style.RESET_ALL)
        loop = asyncio.get_event_loop()
        while True:
            cmd = await loop.run_in_executor(None, lambda: input(Fore.BLUE + ">> " + Style.RESET_ALL).strip().lower())
            
            if cmd == 'quit':
                print(Fore.MAGENTA + "# Dissolving the enchantment..." + Style.RESET_ALL)
                if self.live_task:
                    self.live_task.cancel() # Request cancellation of the live task
                    # Await the task to ensure it's properly shut down, suppressing cancellation errors
                    await asyncio.gather(self.live_task, return_exceptions=True) 
                if self.termux_api_available:
                    os.system('termux-wake-unlock') # Release wake-lock on exit
                    print(Fore.YELLOW + "# Termux screen lock released." + Style.RESET_ALL)
                break
            elif cmd == 'live':
                if self.live_task and not self.live_task.done():
                    print(Fore.YELLOW + "# Live stream already active. Type 'refresh' to update analysis or 'quit' to stop all." + Style.RESET_ALL)
                else:
                    print(Fore.GREEN + "# Summoning live stream..." + Style.RESET_ALL)
                    if self.termux_api_available:
                        os.system('termux-wake-lock') # Apply wake-lock for continuous streaming
                        print(Fore.YELLOW + "# Termux screen lock applied for live stream." + Style.RESET_ALL)
                    self.live_task = asyncio.create_task(self.live_updates())
            elif cmd == 'backtest':
                print(Fore.CYAN + "# Divining the past..." + Style.RESET_ALL)
                self.backtest_strategy()
            elif cmd == 'save':
                self.save_settings()
            elif cmd == 'help':
                print(Fore.YELLOW + Style.BRIGHT + "\n# Available Incantations:" + Style.RESET_ALL)
                print(f"  {Fore.CYAN}symbol [SYMBOL]{Style.RESET_ALL} - Change the asset (e.g., 'symbol ETH').")
                print(f"  {Fore.CYAN}timeframe [TF]{Style.RESET_ALL} - Change the candle size (e.g., 'timeframe 4h').")
                print(f"  {Fore.CYAN}limit [NUM]{Style.RESET_ALL} - Set the number of candles to fetch (e.g., 'limit 200', range 50-1000).")
                print(f"  {Fore.CYAN}backtest_indicators [IND1,IND2,...]{Style.RESET_ALL} - Set indicators for backtest logic (e.g., 'backtest_indicators RSI,MACD,EMA_CROSS').")
                print(f"  {Fore.CYAN}live{Style.RESET_ALL} - Begin the live market stream (enables Termux wake-lock).")
                print(f"  {Fore.CYAN}backtest{Style.RESET_ALL} - Divine the past performance of the strategy.")
                print(f"  {Fore.CYAN}save{Style.RESET_ALL} - Etch current settings into the grimoire.")
                print(f"  {Fore.CYAN}clear{Style.RESET_ALL} - Cleanse the terminal display.")
                print(f"  {Fore.CYAN}refresh{Style.RESET_ALL} - Resummon the data and analysis.")
                print(f"  {Fore.CYAN}quit{Style.RESET_ALL} - Banish the spell and exit (releases Termux wake-lock).")
            elif cmd == 'clear':
                os.system('clear')
            elif cmd == 'refresh':
                await self.fetch_klines()
                self.render_ascii_chart()
                await self.display_analysis()
            elif cmd.startswith('symbol '):
                parts = cmd.split(' ')
                if len(parts) == 2 and parts[1]:
                    new_symbol = parts[1].upper() + '/USDT' # Assume USDT pair by default
                    if new_symbol != self.symbol:
                        self.symbol = new_symbol
                        print(Fore.YELLOW + f"# New symbol essence: {self.symbol}" + Style.RESET_ALL)
                        await self.fetch_klines() # Re-fetch data for new symbol
                        self.render_ascii_chart()
                        await self.display_analysis()
                    else:
                        print(Fore.YELLOW + "# Symbol is already set to this value." + Style.RESET_ALL)
                else:
                    print(Fore.RED + "# Invalid symbol format. Use 'symbol BTC'." + Style.RESET_ALL)
            elif cmd.startswith('timeframe '):
                parts = cmd.split(' ')
                if len(parts) == 2 and parts[1]:
                    new_timeframe = parts[1]
                    valid_timeframes = ['1m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w', '1M']
                    if new_timeframe in valid_timeframes:
                        if new_timeframe != self.timeframe:
                            self.timeframe = new_timeframe
                            print(Fore.YELLOW + f"# Timeframe shifted to {self.timeframe}" + Style.RESET_ALL)
                            await self.fetch_klines() # Re-fetch data for new timeframe
                            self.render_ascii_chart()
                            await self.display_analysis()
                        else:
                            print(Fore.YELLOW + "# Timeframe is already set to this value." + Style.RESET_ALL)
                    else:
                        print(Fore.RED + f"# Invalid timeframe. Valid options: {', '.join(valid_timeframes)}" + Style.RESET_ALL)
                else:
                    print(Fore.RED + "# Invalid timeframe format. Use 'timeframe 1h'." + Style.RESET_ALL)
            elif cmd.startswith('limit '):
                parts = cmd.split(' ')
                if len(parts) == 2 and parts[1].isdigit():
                    new_limit = int(parts[1])
                    if 50 <= new_limit <= 1000: # Example reasonable limits for fetching candles
                        if new_limit != self.limit:
                            self.limit = new_limit
                            print(Fore.YELLOW + f"# Candle limit set to {self.limit}" + Style.RESET_ALL)
                            await self.fetch_klines() # Re-fetch data with new limit
                            self.render_ascii_chart()
                            await self.display_analysis()
                        else:
                            print(Fore.YELLOW + "# Limit is already set to this value." + Style.RESET_ALL)
                    else:
                        print(Fore.RED + "# Limit must be between 50 and 1000 candles." + Style.RESET_ALL)
                else:
                    print(Fore.RED + "# Invalid limit format. Use 'limit 200'." + Style.RESET_ALL)
            elif cmd.startswith('backtest_indicators '):
                # Allow user to specify which indicators to use for backtest signal generation
                parts = cmd.split(' ')[1:]
                if parts:
                    new_indicators = [ind.strip().upper() for ind in ','.join(parts).split(',')]
                    # Define a list of indicators that are supported by the backtest logic
                    valid_backtest_indicators = ['RSI', 'MACD', 'EMA_CROSS'] 
                    if all(ind in valid_backtest_indicators for ind in new_indicators):
                        self.backtest_indicators = new_indicators
                        print(Fore.YELLOW + f"# Backtest indicators set to: {', '.join(self.backtest_indicators)}" + Style.RESET_ALL)
                    else:
                        print(Fore.RED + f"# Invalid backtest indicator(s) provided. Valid options: {', '.join(valid_backtest_indicators)}" + Style.RESET_ALL)
                else:
                    print(Fore.RED + "# Please specify at least one indicator. Use 'backtest_indicators RSI,MACD'." + Style.RESET_ALL)
            else:
                print(Fore.RED + "# Unknown incantation. Type 'help' for guidance." + Style.RESET_ALL)

async def main():
    trader = PyrmethusTrader()
    await trader.run()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(Fore.RED + "\n# Seeker’s will banishes the spell." + Style.RESET_ALL)
        # Ensure wake-lock is released on Ctrl+C as well
        # This check is crucial because 'trader' might not be defined if `main()` failed early
        if 'trader' in locals() and trader.termux_api_available:
            os.system('termux-wake-unlock')
            print(Fore.YELLOW + "# Termux screen lock released." + Style.RESET_ALL)
    except Exception as e:
        print(Fore.RED + f"\n# Catastrophic rift: {str(e)}" + Style.RESET_ALL)
        import traceback
        traceback.print_exc() # Print full traceback for unexpected errors
        if 'trader' in locals() and trader.termux_api_available:
            os.system('termux-wake-unlock')
            print(Fore.YELLOW + "# Termux screen lock released." + Style.RESET_ALL)
