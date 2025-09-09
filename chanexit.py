import os
import sys
import time
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union

import pandas as pd
import numpy as np
import pandas_ta as pta  # Using pandas_ta for technical indicators
from bybit import BybitV5
from dotenv import load_dotenv
from colorama import init, Fore, Back, Style
from dataclasses import dataclass, field
from enum import Enum

# --- Initialize Colorama ---
init(autoreset=True) # Automatically reset style after each print

# --- Load environment variables from .env file ---
load_dotenv()

# --- Configure Logging ---
# Logs to both a file and the console for comprehensive tracking.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bybit_scalping_bot.log'), # Log to file
        logging.StreamHandler(sys.stdout)             # Log to console
    ]
)
logger = logging.getLogger(__name__)

# --- Neon-themed Colors for Console Output ---
NEON_GREEN = Fore.GREEN + Style.BRIGHT
NEON_BLUE = Fore.CYAN + Style.BRIGHT
NEON_YELLOW = Fore.YELLOW + Style.BRIGHT
NEON_MAGENTA = Fore.MAGENTA + Style.BRIGHT
NEON_PINK = Fore.LIGHTMAGENTA_EX + Style.BRIGHT
ERROR_RED = Fore.RED + Style.BRIGHT + Back.BLACK
INFO_TEXT = Fore.WHITE + Style.BRIGHT
WARNING_ORANGE = Fore.YELLOW + Style.BRIGHT
SUCCESS_GREEN = Fore.GREEN + Style.BRIGHT # For positive PnL

class PositionSide(Enum):
    """Enum to represent the side of a trading position."""
    NONE = "NONE"
    BUY = "Buy"
    SELL = "Sell"

@dataclass
class Position:
    """Represents an open trading position managed by the bot."""
    side: PositionSide
    entry_price: float
    quantity: float
    timestamp: datetime # Timestamp of when the position was opened
    take_profit: float
    stop_loss: float
    order_id: str = "" # Bybit's order ID for the entry trade
    
    def unrealized_pnl(self, current_price: float) -> float:
        """Calculates the unrealized Profit or Loss based on the current market price."""
        if self.side == PositionSide.BUY:
            return (current_price - self.entry_price) * self.quantity
        else:  # SELL
            return (self.entry_price - current_price) * self.quantity
    
    def pnl_percentage(self, current_price: float) -> float:
        """Calculates the unrealized PnL as a percentage of the entry price."""
        if self.entry_price == 0: # Prevent division by zero
            return 0.0 
        if self.side == PositionSide.BUY:
            return ((current_price - self.entry_price) / self.entry_price) * 100
        else:  # SELL
            return ((self.entry_price - current_price) / self.entry_price) * 100

@dataclass
class Signal:
    """Data structure to hold all information related to a generated trading signal."""
    timestamp: datetime
    action: str  # 'BUY', 'SELL', 'CLOSE', 'HOLD'
    price: float # The market price at which the signal was generated
    ha_color: str # Heikin Ashi candle color ('green' or 'red')
    zlsma_value: float # Value of the ZLSMA indicator at the time of the signal
    ce_long: float # Value of the Chandelier Exit Long line
    ce_short: float # Value of the Chandelier Exit Short line
    strength: float  # Numerical strength of the signal (0.0 to 1.0)
    reason: str # A textual explanation for why the signal was generated

class BybitScalpingBot:
    def __init__(self,
                 api_key: str = None,
                 api_secret: str = None,
                 testnet: bool = True,
                 symbol: str = 'BTCUSDT',
                 interval: str = '15',  # Candlestick interval (e.g., '1', '5', '15', '30', '60', '240', 'D', 'W')
                 klines_limit: int = 200, # Number of historical candles to fetch for indicator calculations
                 take_profit_percent: float = 0.015,  # Take Profit target as a percentage (e.g., 1.5%)
                 stop_loss_percent: float = 0.01,     # Stop Loss limit as a percentage (e.g., 1%)
                 position_size_usd: float = 100.0,    # Target USD value for each trade. Bot calculates crypto quantity.
                 max_positions: int = 1, # Maximum number of concurrent open positions (typically 1 for scalping).
                 loop_delay_seconds: int = 60 * 15,   # Delay between market checks (seconds). Recommended to match `interval`.
                 use_trailing_stop: bool = True,      # Enable/disable the trailing stop-loss feature.
                 trailing_stop_percent: float = 0.005 # Percentage deviation for trailing stop adjustment (e.g., 0.5%).
                 ):
        
        # --- API Configuration ---
        self.api_key = api_key or os.getenv('BYBIT_API_KEY')
        self.api_secret = api_secret or os.getenv('BYBIT_API_SECRET')
        self.testnet = testnet
        
        # --- Trading Parameters ---
        self.symbol = symbol
        self.interval = interval
        self.klines_limit = klines_limit
        self.take_profit_percent = take_profit_percent
        self.stop_loss_percent = stop_loss_percent
        self.position_size_usd = position_size_usd
        self.max_positions = max_positions
        self.loop_delay_seconds = loop_delay_seconds
        self.use_trailing_stop = use_trailing_stop
        self.trailing_stop_percent = trailing_stop_percent
        
        # --- Indicator Settings (as per the video strategy) ---
        self.ce_atr_period = 1 # ATR period for Chandelier Exit
        self.ce_atr_multiplier = 1.85 # ATR multiplier for Chandelier Exit
        self.zlsma_length = 75 # Length for ZLSMA
        
        # --- Bot State & Tracking ---
        self.client = self._initialize_bybit_client() # Initialize Bybit API client and test connection
        self.current_position: Optional[Position] = None # Stores details of the currently open position
        self.trade_history: List[Dict] = [] # Accumulates records of closed trades
        self.last_signal: Optional[Signal] = None # Stores the last generated signal for context
        self.symbol_info: Dict = {} # Caches exchange trading rules for the symbol (min_qty, precision, etc.)
        self.last_saved_trade_history_count = 0 # Tracks how many trades were saved last time to avoid redundant saves
        
        # --- Performance & Risk Management ---
        self.total_trades = 0 # Total trades executed in the session
        self.winning_trades = 0 # Number of profitable trades
        self.total_pnl = 0.0 # Total Profit/Loss for the session
        self.consecutive_losses = 0 # Counts consecutive losing trades
        self.max_consecutive_losses = 3  # Emergency circuit breaker: halt new entries after this many losses
        
        self._print_banner() # Display bot's startup banner with configuration details
    
    def _print_banner(self):
        """Prints a stylish and informative banner with bot's configuration."""
        banner = f"""
{NEON_PINK}╔═══════════════════════════════════════════════════════════╗
║                  BYBIT SCALPING BOT v2.0                  ║
║                  Heikin Ashi + ZLSMA + CE                 ║
╚═══════════════════════════════════════════════════════════╝{Style.RESET_ALL}
"""
        print(banner)
        print(f"{INFO_TEXT}Symbol: {NEON_YELLOW}{self.symbol}{Style.RESET_ALL}")
        print(f"{INFO_TEXT}Interval: {NEON_YELLOW}{self.interval} minutes{Style.RESET_ALL}")
        print(f"{INFO_TEXT}Environment: {NEON_MAGENTA}{'TESTNET' if self.testnet else 'LIVE'}{Style.RESET_ALL}")
        print(f"{INFO_TEXT}Base Position Size (USD): {NEON_GREEN}${self.position_size_usd:.2f}{Style.RESET_ALL}")
        print(f"{INFO_TEXT}TP/SL: {NEON_GREEN}{self.take_profit_percent*100:.1f}%{Style.RESET_ALL}/{ERROR_RED}{self.stop_loss_percent*100:.1f}%{Style.RESET_ALL}")
        print(f"{INFO_TEXT}Trailing Stop: {NEON_YELLOW}{'Enabled' if self.use_trailing_stop else 'Disabled'}{Style.RESET_ALL} ({self.trailing_stop_percent*100:.1f}%)")
        print("─" * 60)
    
    def _initialize_bybit_client(self):
        """Initializes the Bybit API client and validates connectivity by fetching account balance."""
        if not self.api_key or not self.api_secret:
            logger.error(f"{ERROR_RED}Bybit API keys not provided in .env or arguments. Exiting.{Style.RESET_ALL}")
            raise ValueError("Bybit API keys (BYBIT_API_KEY, BYBIT_API_SECRET) are required. Set them in .env file.")
        
        logger.info(f"{INFO_TEXT}Initializing Bybit client (testnet={self.testnet}){Style.RESET_ALL}")
        
        try:
            client = BybitV5(
                testnet=self.testnet,
                api_key=self.api_key,
                api_secret=self.api_secret
            )
            
            # Test connectivity by fetching wallet balance for Unified account type (Bybit V5)
            response = client.get_wallet_balance(accountType='UNIFIED')
            
            if response and response['retCode'] == 0:
                balance_info = self._parse_balance_info(response)
                print(f"{SUCCESS_GREEN}✓ Successfully connected to Bybit {'TESTNET' if self.testnet else 'LIVE'}!{Style.RESET_ALL}")
                print(f"{INFO_TEXT}Total Equity: {NEON_GREEN}${balance_info['total_equity']:.2f}{Style.RESET_ALL}")
                print(f"{INFO_TEXT}Available Balance: {NEON_GREEN}${balance_info['available_balance']:.2f}{Style.RESET_ALL}")
                return client
            else:
                # If retCode is not 0, API connection failed or returned an error message.
                raise Exception(f"API Error during connectivity test: {response.get('retMsg', 'Unknown error')}")
                
        except Exception as e:
            logger.error(f"{ERROR_RED}Failed to initialize Bybit client. Ensure API keys are correct and IP whitelist is configured: {e}{Style.RESET_ALL}")
            raise
    
    def _parse_balance_info(self, response: Dict) -> Dict:
        """Parses and extracts relevant balance information from the Bybit API response for the Unified account."""
        balance_info = {
            'total_equity': 0.0,
            'available_balance': 0.0,
            'used_margin': 0.0
        }
        
        # The 'result' field contains a list of accounts
        for account in response.get('result', {}).get('list', []):
            if account['accountType'] == 'UNIFIED': # Focusing on Unified account type as per init
                balance_info['total_equity'] = float(account.get('totalEquity', 0))
                balance_info['available_balance'] = float(account.get('totalAvailableBalance', 0))
                balance_info['used_margin'] = float(account.get('totalMarginBalance', 0))
                break # Assuming one Unified account
        
        return balance_info
    
    def fetch_klines(self) -> pd.DataFrame:
        """Fetches historical klines (candlestick data) from Bybit for the configured symbol and interval."""
        try:
            response = self.client.get_kline(
                category="linear", # Category for USDT Perpetual and USDC Perpetual futures (linear futures)
                symbol=self.symbol,
                interval=self.interval, # e.g., '15' for 15 minutes
                limit=self.klines_limit # Number of candles to retrieve
            )
            
            if response and response['retCode'] == 0:
                klines = response['result']['list']
                
                # Convert to DataFrame
                df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
                
                # Convert timestamp to datetime objects and OHLCV columns to numeric
                df['timestamp'] = pd.to_datetime(pd.to_numeric(df['timestamp']), unit='ms')
                for col in ['open', 'high', 'low', 'close', 'volume', 'turnover']:
                    df[col] = pd.to_numeric(df[col], errors='coerce') # 'coerce' converts invalid parsing into NaN
                
                # Sort by timestamp ascending to ensure correct order for indicator calculations
                df = df.sort_values('timestamp').reset_index(drop=True)
                
                logger.info(f"{INFO_TEXT}Fetched {len(df)} candles for {self.symbol}.{Style.RESET_ALL}")
                return df
                
            else:
                raise Exception(f"API Error fetching klines: {response.get('retMsg', 'Unknown error')}")
                
        except Exception as e:
            logger.error(f"{ERROR_RED}Error fetching klines: {e}{Style.RESET_ALL}")
            raise
    
    def calculate_heikin_ashi(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculates Heikin Ashi candles from a standard OHLCV DataFrame."""
        ha_df = df.copy()
        
        # Calculate HA Close: (Open + High + Low + Close) / 4 of the current regular candle
        ha_df['ha_close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
        
        # Calculate HA Open: (Previous HA Open + Previous HA Close) / 2
        # For the first HA candle, HA_Open = (Open + Close) / 2 of the first regular candle
        ha_df.loc[0, 'ha_open'] = (df.loc[0, 'open'] + df.loc[0, 'close']) / 2
        for i in range(1, len(ha_df)):
            ha_df.loc[i, 'ha_open'] = (ha_df.loc[i-1, 'ha_open'] + ha_df.loc[i-1, 'ha_close']) / 2
        
        # Calculate HA High: Max of current HA_Open, HA_Close, and regular High
        ha_df['ha_high'] = ha_df[['ha_open', 'ha_close', 'high']].max(axis=1)
        # Calculate HA Low: Min of current HA_Open, HA_Close, and regular Low
        ha_df['ha_low'] = ha_df[['ha_open', 'ha_close', 'low']].min(axis=1)
        
        # Determine HA candle color based on HA Open and HA Close
        ha_df['ha_color'] = 'green' # Default to green
        ha_df.loc[ha_df['ha_close'] < ha_df['ha_open'], 'ha_color'] = 'red' # Set to red if close < open
        
        # Calculate HA body and wick sizes for signal strength analysis
        ha_df['ha_body_size'] = abs(ha_df['ha_close'] - ha_df['ha_open'])
        ha_df['ha_upper_wick'] = ha_df['ha_high'] - ha_df[['ha_open', 'ha_close']].max(axis=1)
        ha_df['ha_lower_wick'] = ha_df[['ha_open', 'ha_close']].min(axis=1) - ha_df['ha_low']
        
        return ha_df
    
    def calculate_zlsma(self, series: pd.Series, length: int) -> pd.Series:
        """Calculates the Zero Lag Simple Moving Average (ZLSMA) using pandas_ta."""
        # pandas_ta has a direct implementation of ZLSMA.
        # It's an approximation of zero-lag based on EMA.
        # Ensure sufficient data points for calculation.
        if len(series) < length * 2: # ZLSMA needs roughly 2x length for initial stabilization.
            logger.warning(f"{WARNING_ORANGE}Not enough data for ZLSMA calculation (needed: {length*2}, got: {len(series)}). Results may be NaN.{Style.RESET_ALL}")
            return pd.Series([np.nan] * len(series), index=series.index)
            
        zlsma = pta.zlsma(series, length=length, append=False) # append=False returns a Series
        return zlsma
    
    def calculate_chandelier_exit(self, ha_df: pd.DataFrame, period: int, multiplier: float) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """Calculates the Chandelier Exit (CE) indicator based on Heikin Ashi data using pandas_ta."""
        # Ensure sufficient data points for ATR and rolling calculations.
        if len(ha_df) < period + 1: # ATR needs at least 'period' + 1 data points.
             logger.warning(f"{WARNING_ORANGE}Not enough data for Chandelier Exit calculation (needed: {period+1}, got: {len(ha_df)}). Results may be NaN.{Style.RESET_ALL}")
             return (pd.Series([np.nan]*len(ha_df)), pd.Series([np.nan]*len(ha_df)), pd.Series([np.nan]*len(ha_df)))

        # Calculate ATR using pandas_ta's True Range and SMA smoothing.
        # This mimics the common implementation where ATR is smoothed by SMA.
        true_range_series = pta.true_range(ha_df['ha_high'], ha_df['ha_low'], ha_df['ha_close'])
        atr = pta.sma(true_range_series, length=period) # Smooth ATR with SMA
        
        # Calculate Highest HA High and Lowest HA Low over the specified period using pandas_ta
        highest_ha_high = pta.highest(ha_df['ha_high'], length=period)
        lowest_ha_low = pta.lowest(ha_df['ha_low'], length=period)
        
        # Chandelier Exit Long: Highest High - (ATR * Multiplier)
        ce_long = highest_ha_high - (atr * multiplier)
        # Chandelier Exit Short: Lowest Low + (ATR * Multiplier)
        ce_short = lowest_ha_low + (atr * multiplier)
        
        return ce_long, ce_short, atr # Return ATR as it might be useful for other analyses
    
    def _get_symbol_exchange_info(self, symbol: str) -> dict:
        """Fetches and caches exchange trading rules for a specific symbol (e.g., min_order_qty, price/qty precision)."""
        # This information is crucial for correctly formatting orders for Bybit's API.
        # Caching this data prevents repeated API calls, improving performance.
        if symbol not in self.symbol_info:
            try:
                response = self.client.get_instruments_info(category='linear', symbol=symbol)
                if response and response['retCode'] == 0:
                    instrument = response['result']['list'][0] # Get the first instrument matching the symbol
                    
                    # Extract relevant filters from the instrument details
                    lot_size_filter = instrument.get('lotSizeFilter', {})
                    price_filter = instrument.get('priceFilter', {})
                    
                    # Convert filter values from strings to floats and calculate precision
                    min_order_qty = float(lot_size_filter.get('minOrderQty', '0.001')) # Default if not found
                    qty_step = float(lot_size_filter.get('qtyStep', '0.001')) # Step for quantity rounding
                    tick_size = float(price_filter.get('tickSize', '0.01')) # Tick size for price rounding
    
                    # Calculate the number of decimal places for rounding based on step/tick sizes
                    # This is a common way to determine precision for Bybit's API.
                    qty_precision = len(str(qty_step).split('.')[1]) if '.' in str(qty_step) and float(qty_step) < 1 else 0
                    price_precision = len(str(tick_size).split('.')[1]) if '.' in str(tick_size) and float(tick_size) < 1 else 0
    
                    self.symbol_info[symbol] = {
                        'min_order_qty': min_order_qty,
                        'qty_precision': qty_precision,
                        'price_precision': price_precision,
                    }
                    logger.info(f"{INFO_TEXT}Symbol trading info cached for {symbol}: MinQty={min_order_qty}, QtyPrecision={qty_precision}, PricePrecision={price_precision}{Style.RESET_ALL}")
                else:
                    logger.error(f"{ERROR_RED}Failed to get instrument info for {symbol}: {response.get('retMsg', 'Unknown error')}. Using fallback values.{Style.RESET_ALL}")
                    # Fallback to safe, common default values if API call fails
                    self.symbol_info[symbol] = {'min_order_qty': 0.001, 'qty_precision': 3, 'price_precision': 2}
            except Exception as e:
                logger.error(f"{ERROR_RED}Exception while fetching instrument info for {symbol}: {e}. Using fallback values.{Style.RESET_ALL}")
                # Provide even more generic fallback values in case of parsing or network errors
                self.symbol_info[symbol] = {'min_order_qty': 0.001, 'qty_precision': 3, 'price_precision': 2}
        
        return self.symbol_info[symbol]
            
    def analyze_market_conditions(self, df: pd.DataFrame) -> Dict:
        """Analyzes general market trend, volatility, and volume using raw candlestick data for context."""
        latest_raw = df.iloc[-1]
        
        # Trend analysis: Simple Moving Average (SMA) crossover (20-period vs 50-period)
        # Using pandas_ta for SMA calculation
        sma_20 = pta.sma(df['close'], length=20).iloc[-1]
        sma_50 = pta.sma(df['close'], length=50).iloc[-1]
        trend = "bullish" if sma_20 > sma_50 else "bearish" # Basic trend direction
        
        # Volatility analysis: Annualized standard deviation of log returns (using last 20 periods)
        returns = np.log(df['close'] / df['close'].shift(1))
        # Ensure enough non-NaN data points for std calculation (need at least 20 for 20-period std)
        if len(returns.dropna()) > 19: 
            volatility_annual_pct = returns.rolling(window=20).std().iloc[-1] * np.sqrt(252) * 100 # Annualize
        else:
            volatility_annual_pct = 0.0 # Default if insufficient data
        
        # Volume analysis: Compare current volume to average volume over the last 20 periods
        avg_volume_20 = pta.sma(df['volume'], length=20).iloc[-1]
        volume_ratio_to_avg = latest_raw['volume'] / avg_volume_20 if avg_volume_20 > 0 else 1.0 # Avoid division by zero
        
        # Last candle's percentage change in close price for immediate momentum indication
        prev_close = df.iloc[-2]['close']
        last_candle_change_pct = ((latest_raw['close'] - prev_close) / prev_close) * 100 if prev_close != 0 else 0
        
        return {
            'trend': trend,
            'volatility_annual_pct': round(volatility_annual_pct, 2),
            'volume_ratio_to_avg': round(volume_ratio_to_avg, 2),
            'last_candle_change_pct': round(last_candle_change_pct, 2),
            'sma_20': round(sma_20, 2),
            'sma_50': round(sma_50, 2)
        }
    
    def calculate_signal_strength(self, ha_df: pd.DataFrame, signal_type: str) -> float:
        """Calculates a numerical strength for a trading signal based on Heikin Ashi candle characteristics.
        The strength value ranges from 0.0 (weakest) to 1.0 (strongest), derived from multiple factors.
        """
        strength = 0.0
        latest_ha = ha_df.iloc[-1]
        
        # Factor 1: HA candle body size (larger body implies stronger momentum, max contribution 0.4)
        avg_ha_body_size = pta.sma(ha_df['ha_body_size'], length=20).iloc[-1]
        if avg_ha_body_size > 0:
            # Body size contribution, capped to prevent extreme values from distorting strength.
            body_factor_contrib = min(latest_ha['ha_body_size'] / avg_ha_body_size, 2.0) * 0.4 
        else:
            body_factor_contrib = 0.2 # Default moderate strength if average body size is not calculable
        strength += body_factor_contrib
        
        # Factor 2: ZLSMA divergence (price trending away from ZLSMA in signal direction, max contribution 0.3)
        zlsma_factor_contrib = 0.0
        if signal_type == 'BUY' and latest_ha['ha_close'] > latest_ha['zlsma']:
            zlsma_divergence = (latest_ha['ha_close'] - latest_ha['zlsma']) / latest_ha['zlsma']
            # Scale divergence: e.g., 0.5% divergence gives max factor of 1.0
            zlsma_factor_contrib = min(zlsma_divergence / 0.005, 1.0) * 0.3 
        elif signal_type == 'SELL' and latest_ha['ha_close'] < latest_ha['zlsma']:
            zlsma_divergence = (latest_ha['zlsma'] - latest_ha['ha_close']) / latest_ha['zlsma']
            zlsma_factor_contrib = min(zlsma_divergence / 0.005, 1.0) * 0.3
        strength += zlsma_factor_contrib
            
        # Factor 3: Lack of opposing wicks (small/no wicks against the trend direction, max contribution 0.2)
        # Strong HA candles in a trend direction typically have small or no wicks on the opposing side.
        wick_factor_contrib = 0.0
        if signal_type == 'BUY' and latest_ha['ha_lower_wick'] < (latest_ha['ha_body_size'] * 0.1): # Small lower wick is bullish confirmation
            wick_factor_contrib = 0.2
        elif signal_type == 'SELL' and latest_ha['ha_upper_wick'] < (latest_ha['ha_body_size'] * 0.1): # Small upper wick is bearish confirmation
            wick_factor_contrib = 0.2
        strength += wick_factor_contrib
            
        return round(min(strength, 1.0), 2) # Ensure final strength is capped at 1.0
    
    def generate_trading_signals(self, ha_df: pd.DataFrame, raw_df: pd.DataFrame) -> Signal:
        """Generates trading signals ('BUY', 'SELL', 'CLOSE', 'HOLD') based on the strategy rules.
        Combines Heikin Ashi patterns, ZLSMA for trend filtering, and Chandelier Exit for entry/exit boundaries.
        """
        # Ensure enough data points for signal generation (need current and previous HA candle)
        if len(ha_df) < 2: 
            logger.warning(f"{WARNING_ORANGE}Not enough HA data ({len(ha_df)} candles) to generate signals. Returning HOLD.{Style.RESET_ALL}")
            return Signal(
                timestamp=datetime.now(), action='HOLD', price=raw_df.iloc[-1]['close'], 
                ha_color='N/A', zlsma_value=np.nan, ce_long=np.nan, ce_short=np.nan,
                strength=0.0, reason="Insufficient HA data"
            )

        latest_ha = ha_df.iloc[-1]
        prev_ha = ha_df.iloc[-2] # Access previous Heikin Ashi candle for trend reversal detection
        
        # Initialize default signal to HOLD
        signal = Signal(
            timestamp=latest_ha['timestamp'],
            action='HOLD',
            price=raw_df.iloc[-1]['close'], # Use raw market price for decision context
            ha_color=latest_ha['ha_color'],
            zlsma_value=latest_ha['zlsma'],
            ce_long=latest_ha['ce_long'],
            ce_short=latest_ha['ce_short'],
            strength=0.0,
            reason="Market analysis pending or conditions not met"
        )
        
        # --- Emergency Circuit Breaker: Halt new entries if max_consecutive_losses reached ---
        if self.consecutive_losses >= self.max_consecutive_losses:
            signal.reason = f"Circuit breaker active: {self.consecutive_losses} consecutive losses. Halting new entries."
            logger.warning(f"{WARNING_ORANGE}!!! {signal.reason} !!!{Style.RESET_ALL}")
            # If there's an open position, the bot might still decide to CLOSE it based on its own exit logic.
            # If no position is open, then strictly HOLD.
            if not self.current_position:
                signal.action = 'HOLD' 
                return signal

        # --- Logic for exiting an existing position (strategic exits) ---
        if self.current_position:
            # Assume HOLD unless a strategic exit condition is met.
            # Note: TP/SL hits are handled by Bybit's order system and detected via check_position_status.
            
            # Strategic exit for BUY position
            if self.current_position.side == PositionSide.BUY:
                # Exit Long if:
                # 1. HA candle color flips to red (strong short-term bearish reversal signal)
                # 2. HA Close drops below ZLSMA (long-term trend shows signs of breaking down)
                # 3. HA Close drops below CE Short (bearish momentum gaining, breaking CE Short as support)
                if (latest_ha['ha_color'] == 'red' and latest_ha['ha_open'] >= latest_ha['ha_close']) or \
                   (latest_ha['ha_close'] < latest_ha['zlsma']) or \
                   (latest_ha['ha_close'] < latest_ha['ce_short']):
                    
                    signal.action = 'CLOSE'
                    # Calculate strength of the potential reversal signal
                    signal.strength = self.calculate_signal_strength(ha_df, 'SELL') 
                    signal.reason = "Exit Long: HA flip to Red OR Price < ZLSMA OR Price < CE_Short."
            
            # Strategic exit for SELL position
            elif self.current_position.side == PositionSide.SELL:
                # Exit Short if:
                # 1. HA candle color flips to green (strong short-term bullish reversal signal)
                # 2. HA Close rises above ZLSMA (long-term trend shows signs of breaking up)
                # 3. HA Close rises above CE Long (bullish momentum gaining, breaking CE Long as resistance)
                if (latest_ha['ha_color'] == 'green' and latest_ha['ha_open'] <= latest_ha['ha_close']) or \
                   (latest_ha['ha_close'] > latest_ha['zlsma']) or \
                   (latest_ha['ha_close'] > latest_ha['ce_long']):
                    
                    signal.action = 'CLOSE'
                    # Calculate strength of the potential reversal signal
                    signal.strength = self.calculate_signal_strength(ha_df, 'BUY') 
                    signal.reason = "Exit Short: HA flip to Green OR Price > ZLSMA OR Price > CE_Long."

        # --- Logic for entering a new position (only if no current position is open) ---
        else: # No open position
            # Long Entry conditions (all must be met for a BUY signal):
            # 1. HA candle color flips from red to green (indicates bullish momentum shift).
            # 2. Latest HA Close is ABOVE ZLSMA (confirms price is in an upward trend relative to the MA).
            # 3. Latest HA Close is ABOVE CE_Long (CE_Long acts as a dynamic support level, confirming bullish continuation).
            if (latest_ha['ha_color'] == 'green' and prev_ha['ha_color'] == 'red' and
                latest_ha['ha_close'] > latest_ha['zlsma'] and
                latest_ha['ha_close'] > latest_ha['ce_long']): # Price crossing above CE_Long
                
                signal.action = 'BUY'
                signal.strength = self.calculate_signal_strength(ha_df, 'BUY')
                signal.reason = "Long Entry: HA flip (Red->Green), Price > ZLSMA & > CE_Long."
            
            # Short Entry conditions (all must be met for a SELL signal):
            # 1. HA candle color flips from green to red (indicates bearish momentum shift).
            # 2. Latest HA Close is BELOW ZLSMA (confirms price is in a downward trend relative to the MA).
            # 3. Latest HA Close is BELOW CE_Short (CE_Short acts as dynamic resistance, confirming bearish continuation).
            elif (latest_ha['ha_color'] == 'red' and prev_ha['ha_color'] == 'green' and
                  latest_ha['ha_close'] < latest_ha['zlsma'] and
                  latest_ha['ha_close'] < latest_ha['ce_short']): # Price crossing below CE_Short
                
                signal.action = 'SELL'
                signal.strength = self.calculate_signal_strength(ha_df, 'SELL')
                signal.reason = "Short Entry: HA flip (Green->Red), Price < ZLSMA & < CE_Short."
                
        return signal
    
    def calculate_position_size(self, current_price: float) -> float:
        """Calculates the cryptocurrency quantity for a trade, considering account equity, risk per trade,
        and Bybit's symbol-specific trading rules (minimum order quantity, price/quantity precision).
        """
        # Ensure current_price is valid to prevent division by zero or errors
        if current_price <= 0:
            logger.error(f"{ERROR_RED}Current price is invalid ({current_price}). Cannot calculate position quantity. Returning 0.{Style.RESET_ALL}")
            return 0.0

        try:
            # Fetch current account balance info for risk-based sizing
            response = self.client.get_wallet_balance(accountType='UNIFIED')
            balance_info = self._parse_balance_info(response)
            
            if balance_info['total_equity'] <= 0:
                logger.error(f"{ERROR_RED}Account total equity is zero or negative. Cannot calculate position quantity. Exiting bot.{Style.RESET_ALL}")
                raise ValueError("Account has no equity. Cannot proceed with trading.")

            # Step 1: Determine the absolute USD amount of risk per trade (e.g., 1% of total equity)
            risk_amount_usd_per_trade = balance_info['total_equity'] * 0.01 
            
            # Step 2: Calculate the maximum quantity of cryptocurrency that can be traded given the risk amount and stop-loss percentage.
            # Formula: (risk_amount_usd / (entry_price * stop_loss_percentage))
            if self.stop_loss_percent <= 0: # Ensure SL% is positive for risk calculation.
                logger.warning(f"{WARNING_ORANGE}Configured stop_loss_percent is zero or negative. This is HIGHLY risky and may lead to unexpected behavior. Using a default risk size.{Style.RESET_ALL}")
                qty_from_risk = self.position_size_usd / current_price # Fallback to base USD limit if SL% is invalid.
            else:
                qty_from_risk = risk_amount_usd_per_trade / (current_price * self.stop_loss_percent)

            # Step 3: Combine various quantity limits to find the smallest, safest quantity:
            # A) The quantity derived from risk-management (qty_from_risk)
            # B) The quantity derived from the user-configured 'position_size_usd' limit.
            # C) A safety margin to avoid using all available balance (e.g., 95% of available balance).
            qty_from_base_usd_limit = self.position_size_usd / current_price
            qty_from_available_balance_safety = balance_info['available_balance'] * 0.95 / current_price 

            final_quantity_unrounded = min(qty_from_risk, qty_from_base_usd_limit, qty_from_available_balance_safety)
            
            # Step 4: Adjust final quantity to comply with exchange rules (precision and minimums)
            symbol_rules = self.symbol_info # Use cached symbol info
            
            # Round quantity to the exchange's required decimal places
            final_quantity_rounded = round(final_quantity_unrounded, symbol_rules['qty_precision'])
            
            # Ensure final quantity is not below the exchange's minimum order quantity
            if final_quantity_rounded < symbol_rules['min_order_qty']:
                final_quantity_rounded = symbol_rules['min_order_qty']
                logger.warning(f"{WARNING_ORANGE}Calculated quantity ({final_quantity_unrounded:.{symbol_rules['qty_precision']}f}) was below exchange min order qty ({symbol_rules['min_order_qty']}). Adjusted to min quantity.{Style.RESET_ALL}")
            
            # Final check: Ensure the calculated quantity is positive.
            if final_quantity_rounded <= 0:
                logger.error(f"{ERROR_RED}Calculated position quantity is zero or negative ({final_quantity_rounded}). Cannot place trade. Aborting.{Style.RESET_ALL}")
                return 0.0
            
            logger.info(f"{INFO_TEXT}Calculated position quantity: {NEON_GREEN}{final_quantity_rounded:.{symbol_rules['qty_precision']}f} {self.symbol} (~${final_quantity_rounded * current_price:.2f}){Style.RESET_ALL}")
            return final_quantity_rounded
            
        except Exception as e:
            logger.error(f"{ERROR_RED}Error calculating risk-adjusted position quantity: {e}. Falling back to conservative base quantity.{Style.RESET_ALL}")
            # Fallback to the configured base USD size converted to crypto quantity, ensuring it meets min_order_qty.
            symbol_rules = self.symbol_info
            fallback_qty = max(self.position_size_usd / current_price, symbol_rules.get('min_order_qty', 0.001))
            return round(fallback_qty, symbol_rules.get('qty_precision', 3))
    
    def place_order(self, side: str, quantity: float, take_profit: float, stop_loss: float, current_price: float) -> Optional[str]:
        """Places a market order on Bybit for trade entry, including Take Profit and Stop Loss levels."""
        try:
            # Validate quantity against bot and exchange rules before attempting to place order.
            if quantity <= 0:
                logger.warning(f"{WARNING_ORANGE}Cannot place order with zero or negative quantity: {quantity:.{self.symbol_info['qty_precision']}f}. Aborting.{Style.RESET_ALL}")
                return None
            symbol_rules = self.symbol_info
            if quantity < symbol_rules.get('min_order_qty', 0.001):
                logger.warning(f"{WARNING_ORANGE}Calculated quantity ({quantity:.{symbol_rules['qty_precision']}f}) is below exchange's min order qty ({symbol_rules['min_order_qty']}). Aborting order placement.{Style.RESET_ALL}")
                return None
            
            # Format quantity, take_profit, and stop_loss to match exchange's required precision.
            str_qty = f"{quantity:.{symbol_rules['qty_precision']}f}"
            str_tp = f"{take_profit:.{symbol_rules['price_precision']}f}"
            str_sl = f"{stop_loss:.{symbol_rules['price_precision']}f}"

            logger.info(f"{INFO_TEXT}Attempting to place {NEON_YELLOW}{side}{Style.RESET_ALL} order for {NEON_MAGENTA}{str_qty} {self.symbol}{Style.RESET_ALL} at Market Price.")
            logger.info(f"{INFO_TEXT}TP: {NEON_GREEN}${str_tp}{Style.RESET_ALL}, SL: {ERROR_RED}${str_sl}{Style.RESET_ALL}")

            order_response = self.client.place_order(
                category="linear",      # Category for USDT Perpetual contracts on Bybit V5
                symbol=self.symbol,
                side=side,              # "Buy" or "Sell"
                orderType="Market",     # Execute immediately at current market price
                qty=str_qty,
                takeProfit=str_tp,
                stopLoss=str_sl,
                tpTriggerBy="LastPrice", # TP/SL orders triggered by last traded price
                slTriggerBy="LastPrice", # Consider "IndexPrice" or "MarkPrice" for different strategies
                isLeverage=1,           # Indicate using leverage (required for futures trading in V5)
                timeInForce='GTC',      # Good-Till-Cancel: order remains active until filled or canceled
                positionIdx=0           # 0 for One-Way Mode (standard for most bots). Use 1 for long, 2 for short in Hedge Mode.
            )
            
            if order_response and order_response['retCode'] == 0:
                order_id = order_response['result']['orderId']
                logger.info(f"{SUCCESS_GREEN}Entry order placed successfully. Order ID: {order_id}{Style.RESET_ALL}")
                
                # Update local bot state with the new position details immediately
                self.current_position = Position(
                    side=PositionSide.BUY if side == "Buy" else PositionSide.SELL,
                    entry_price=current_price, # Market orders fill close to `current_price` (optimistic assumption)
                    quantity=quantity,
                    timestamp=datetime.now(), # Use current time as entry time
                    take_profit=take_profit,
                    stop_loss=stop_loss,
                    order_id=order_id # Store Bybit's actual order ID for tracking
                )
                self._log_trade_entry() # Log this new position entry to console/file
                return order_id
            else:
                error_msg = order_response.get('retMsg', 'Unknown API Error')
                logger.error(f"{ERROR_RED}Order placement failed: {error_msg}. Please check balance, order parameters, and API permissions.{Style.RESET_ALL}")
                # Specific error handling could be added here based on common Bybit API error codes.
                return None
                
        except Exception as e:
            logger.error(f"{ERROR_RED}An unexpected exception occurred while placing order: {e}{Style.RESET_ALL}")
            return None
    
    def close_position(self) -> bool:
        """Closes the currently active position using a market order. This is for strategic exits, not TP/SL hits."""
        if not self.current_position:
            logger.warning(f"{WARNING_ORANGE}Attempted to execute strategic 'CLOSE' but no active position found. No action taken.{Style.RESET_ALL}")
            return False
        
        try:
            # Determine the opposite side needed to close the current position
            side_to_close = "Sell" if self.current_position.side == PositionSide.BUY else "Buy"
            
            logger.info(f"{INFO_TEXT}Executing strategic 'CLOSE' order for {self.current_position.side.value} position (Qty: {self.current_position.quantity:.{self.symbol_info['qty_precision']}f} {self.symbol}){Style.RESET_ALL}")
            
            # Place a market order to close the full quantity of the existing position
            response = self.client.place_order(
                category="linear",
                symbol=self.symbol,
                side=side_to_close,
                orderType="Market",
                qty=f"{self.current_position.quantity:.{self.symbol_info['qty_precision']}f}", # Close the full current quantity
                positionIdx=0 # Target the one-way mode position
            )
            
            if response and response['retCode'] == 0:
                logger.info(f"{SUCCESS_GREEN}Strategic position closing order sent successfully. Order ID: {response['result']['orderId']}{Style.RESET_ALL}")
                # The actual logging of trade exit stats and clearing of local position state
                # will be handled by check_position_status upon the next API sync.
                return True
            else:
                logger.error(f"{ERROR_RED}Failed to send strategic close order: {response.get('retMsg', 'Unknown error')}. Position might still be open on Bybit.{Style.RESET_ALL}")
                return False
                
        except Exception as e:
            logger.error(f"{ERROR_RED}An exception occurred while attempting to close position strategically: {e}{Style.RESET_ALL}")
            return False
    
    def update_trailing_stop(self, current_price: float):
        """Dynamically adjusts the stop-loss level for an open position to 'trail' the market price,
        moving it in the favorable direction to lock in profits or reduce risk.
        """
        if not self.use_trailing_stop or not self.current_position:
            return # Trailing stop is not enabled or no position is currently open.
        if current_price <= 0: # Ensure current_price is valid for calculations.
            logger.warning(f"{WARNING_ORANGE}Invalid current_price ({current_price}) for trailing stop update. Aborting update.{Style.RESET_ALL}")
            return

        try:
            original_stop_loss = self.current_position.stop_loss
            new_stop_loss = original_stop_loss # Initialize new_stop_loss, it will only be updated if it improves.

            # For BUY positions: Stop-loss should only move upwards (to protect profit or reduce risk).
            if self.current_position.side == PositionSide.BUY:
                # Calculate potential new stop-loss: current price minus a trailing deviation.
                # This new stop must be higher than the current stop-loss to be an improvement.
                potential_new_stop = current_price * (1 - self.trailing_stop_percent)
                
                # Update SL only if it's higher than the current SL AND also past the original entry price
                # (to ensure it doesn't trail below the entry price initially).
                if potential_new_stop > original_stop_loss and potential_new_stop > self.current_position.entry_price:
                    new_stop_loss = potential_new_stop
            
            # For SELL positions: Stop-loss should only move downwards (to protect profit or reduce risk).
            else: # PositionSide.SELL
                # Calculate potential new stop-loss: current price plus a trailing deviation.
                # This new stop must be lower than the current stop-loss to be an improvement.
                potential_new_stop = current_price * (1 + self.trailing_stop_percent)
                
                if potential_new_stop < original_stop_loss and potential_new_stop < self.current_position.entry_price:
                    new_stop_loss = potential_new_stop
            
            # If the calculated stop-loss has indeed changed to a more favorable level:
            if new_stop_loss != original_stop_loss:
                # Round the new stop-loss price to the exchange's required precision.
                new_stop_loss_rounded = round(new_stop_loss, self.symbol_info['price_precision']) 
                
                logger.info(f"{INFO_TEXT}Attempting to update Trailing Stop for {self.current_position.side.value} position: from ${original_stop_loss:.2f} to ${new_stop_loss_rounded:.2f}.{Style.RESET_ALL}")
                
                # Send the stop-loss update request to Bybit.
                response = self.client.set_trading_stop(
                    category="linear",
                    symbol=self.symbol,
                    stopLoss=str(new_stop_loss_rounded),
                    # Use the same trigger types as the initial order for consistency.
                    tpTriggerBy="LastPrice", 
                    slTriggerBy="LastPrice",
                    positionIdx=0 # Target the one-way mode position
                )
                
                if response and response['retCode'] == 0:
                    self.current_position.stop_loss = new_stop_loss_rounded # Update local bot state
                    logger.info(f"{NEON_BLUE}Trailing stop successfully updated to ${new_stop_loss_rounded:.2f}.{Style.RESET_ALL}")
                else:
                    logger.error(f"{ERROR_RED}Failed to update trailing stop on Bybit: {response.get('retMsg', 'Unknown error')}{Style.RESET_ALL}")
                        
        except Exception as e:
            logger.error(f"{ERROR_RED}An exception occurred while updating trailing stop: {e}{Style.RESET_ALL}")
    
    def _log_trade_entry(self):
        """Internal helper function to format and log new position details clearly after a successful entry order."""
        if not self.current_position:
            return
        
        entry_msg = f"""
{NEON_GREEN}{'═' * 60}
📈 NEW POSITION OPENED (ID: {NEON_YELLOW}{self.current_position.order_id}{Style.RESET_ALL})
{'═' * 60}{Style.RESET_ALL}
{INFO_TEXT}Side: {NEON_YELLOW}{self.current_position.side.value}{Style.RESET_ALL}
{INFO_TEXT}Entry Price: {NEON_BLUE}${self.current_position.entry_price:.{self.symbol_info['price_precision']}f}{Style.RESET_ALL}
{INFO_TEXT}Quantity: {NEON_MAGENTA}{self.current_position.quantity:.{self.symbol_info['qty_precision']}f}{Style.RESET_ALL}
{INFO_TEXT}Take Profit: {NEON_GREEN}${self.current_position.take_profit:.{self.symbol_info['price_precision']}f} ({self.take_profit_percent*100:.1f}%){Style.RESET_ALL}
{INFO_TEXT}Stop Loss: {ERROR_RED}${self.current_position.stop_loss:.{self.symbol_info['price_precision']}f} ({self.stop_loss_percent*100:.1f}%){Style.RESET_ALL}
{INFO_TEXT}Time: {NEON_PINK}{self.current_position.timestamp.strftime('%Y-%m-%d %H:%M:%S')}{Style.RESET_ALL}
{NEON_GREEN}{'═' * 60}{Style.RESET_ALL}
"""
        logger.info(entry_msg)
        # self.total_trades is incremented where the entry order is *sent* (in place_order).
        # Consecutive losses logic is handled when a trade is logged as 'closed'.
    
    def _log_trade_exit_stats(self, closed_position_data: Position, final_exit_price: float):
        """Internal helper function to calculate and log comprehensive statistics for a trade that has just closed.
        This function is called after a position is confirmed as closed (either by TP/SL hit or strategic close).
        It accepts the 'Position' object representing the trade before its closure and the final market price.
        """
        try:
            # Calculate PnL based on the original entry details and the final confirmed exit price
            pnl_usd = closed_position_data.unrealized_pnl(final_exit_price)
            pnl_pct = closed_position_data.pnl_percentage(final_exit_price)
            
            # Update overall session statistics
            self.total_pnl += pnl_usd
            if pnl_usd >= 0: # A profitable or break-even trade
                self.winning_trades += 1
                self.consecutive_losses = 0 # Reset consecutive losses on a win/breakeven
            else: # A losing trade
                self.consecutive_losses += 1 # Increment consecutive losses on a loss
            
            win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0.0 # Avoid division by zero
            
            exit_msg = f"""
{NEON_MAGENTA}{'═' * 60}
📊 POSITION CLOSED (Trade ID: {NEON_YELLOW}{closed_position_data.order_id}{Style.RESET_ALL})
{'═' * 60}{Style.RESET_ALL}
{INFO_TEXT}Side: {NEON_YELLOW}{closed_position_data.side.value}{Style.RESET_ALL}
{INFO_TEXT}Entry Price: {NEON_BLUE}${closed_position_data.entry_price:.{self.symbol_info['price_precision']}f}{Style.RESET_ALL}
{INFO_TEXT}Exit Price: {NEON_BLUE}${final_exit_price:.{self.symbol_info['price_precision']}f}{Style.RESET_ALL}
{INFO_TEXT}PnL: {SUCCESS_GREEN if pnl_usd >= 0 else ERROR_RED}${pnl_usd:.2f} ({pnl_pct:+.2f}%){Style.RESET_ALL}
{INFO_TEXT}Duration: {NEON_PINK}{datetime.now() - closed_position_data.timestamp}{Style.RESET_ALL}
{INFO_TEXT}{'─' * 60}{Style.RESET_ALL}
{INFO_TEXT}Total Trades (Session): {NEON_YELLOW}{self.total_trades}{Style.RESET_ALL}
{INFO_TEXT}Winning Trades (Session): {NEON_GREEN}{self.winning_trades}{Style.RESET_ALL}
{INFO_TEXT}Win Rate (Session): {NEON_GREEN if win_rate >= 50 else ERROR_RED}{win_rate:.1f}%{Style.RESET_ALL}
{INFO_TEXT}Total PnL (Session): {SUCCESS_GREEN if self.total_pnl >= 0 else ERROR_RED}${self.total_pnl:.2f}{Style.RESET_ALL}
{NEON_MAGENTA}{'═' * 60}{Style.RESET_ALL}
"""
            logger.info(exit_msg) # Use logger.info for both console and file output
            
            # Add this comprehensive trade record to the history list (making a copy to preserve state at closure)
            self.trade_history.append({
                'timestamp_exit': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'side': closed_position_data.side.value,
                'entry_price': round(closed_position_data.entry_price, self.symbol_info['price_precision']),
                'exit_price': round(final_exit_price, self.symbol_info['price_precision']),
                'quantity': round(closed_position_data.quantity, self.symbol_info['qty_precision']),
                'pnl_usd': round(pnl_usd, 2),
                'pnl_pct': round(pnl_pct, 2),
                'duration_seconds': (datetime.now() - closed_position_data.timestamp).total_seconds(),
                'order_id_entry': closed_position_data.order_id
            })
            
        except Exception as e:
            logger.error(f"{ERROR_RED}Error during trade exit statistics logging: {e}. Trade data for {closed_position_data.order_id} might be incomplete.{Style.RESET_ALL}")
        
    def display_market_status(self, raw_df: pd.DataFrame, ha_df: pd.DataFrame, signal: Signal, market_conditions: Dict):
        """Displays current market data, indicator values, trading signals, and bot's position status
        in a structured, colorful, and easy-to-read format to the console.
        """
        latest_ha = ha_df.iloc[-1]
        latest_raw = raw_df.iloc[-1]
        
        status_msg = f"""
{NEON_BLUE}╔═══════════════════════════════════════════════════════════╗
║                    MARKET STATUS UPDATE                   ║
╚═══════════════════════════════════════════════════════════╝{Style.RESET_ALL}
Timestamp: {NEON_PINK}{latest_raw['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}{Style.RESET_ALL}

📊 {INFO_TEXT}Current Price (Raw): {NEON_YELLOW}${latest_raw['close']:.2f}{Style.RESET_ALL}
📊 {INFO_TEXT}HA Close: {NEON_YELLOW}${latest_ha['ha_close']:.2f}{Style.RESET_ALL}
📊 {INFO_TEXT}HA Color: {NEON_GREEN if latest_ha['ha_color'] == 'green' else ERROR_RED}{latest_ha['ha_color'].upper()}{Style.RESET_ALL}
📊 {INFO_TEXT}ZLSMA ({self.zlsma_length}): {NEON_BLUE}${latest_ha['zlsma']:.2f}{Style.RESET_ALL}
📊 {INFO_TEXT}CE Long: {NEON_GREEN}${latest_ha['ce_long']:.2f}{Style.RESET_ALL} / {INFO_TEXT}CE Short: {ERROR_RED}${latest_ha['ce_short']:.2f}{Style.RESET_ALL}

📈 {INFO_TEXT}Market Trend (SMA): {NEON_GREEN if market_conditions['trend'] == 'bullish' else ERROR_RED}{market_conditions['trend'].upper()}{Style.RESET_ALL}
📈 {INFO_TEXT}Volatility (Annual): {NEON_MAGENTA}{market_conditions['volatility_annual_pct']:.2f}%{Style.RESET_ALL}
📈 {INFO_TEXT}Volume Ratio (20MA): {NEON_YELLOW}{market_conditions['volume_ratio_to_avg']:.2f}x{Style.RESET_ALL}
📈 {INFO_TEXT}Last Candle Change: {SUCCESS_GREEN if market_conditions['last_candle_change_pct'] >= 0 else ERROR_RED}{market_conditions['last_candle_change_pct']:.2f}%{Style.RESET_ALL}

🎯 {INFO_TEXT}Generated Signal: {self._format_signal_action(signal.action)} 
🎯 {INFO_TEXT}Signal Strength: {self._format_signal_strength(signal.strength)}
🎯 {INFO_TEXT}Reason: {NEON_PINK}{signal.reason}{Style.RESET_ALL}

💼 {INFO_TEXT}Current Bot Position: {self._format_position_status()}
{INFO_TEXT}Session PnL: {SUCCESS_GREEN if self.total_pnl >= 0 else ERROR_RED}${self.total_pnl:.2f}{Style.RESET_ALL}

{NEON_BLUE}{'─' * 60}{Style.RESET_ALL}
"""
        logger.info(status_msg) # Using logger.info means it will go to file and console via StreamHandler
    
    def _format_signal_action(self, action: str) -> str:
        """Helper function to format signal action with color codes for console display."""
        if action == 'BUY':
            return f"{NEON_GREEN}▲ {action}{Style.RESET_ALL}"
        elif action == 'SELL':
            return f"{ERROR_RED}▼ {action}{Style.RESET_ALL}"
        elif action == 'CLOSE':
            return f"{NEON_MAGENTA}✖ {action}{Style.RESET_ALL}"
        else: # HOLD
            return f"{NEON_YELLOW}━ {action}{Style.RESET_ALL}"
    
    def _format_signal_strength(self, strength: float) -> str:
        """Helper function to create a visual strength bar with corresponding colors for console display."""
        bars = int(strength * 10) # 10 characters for the bar
        strength_bar_chars = f"{'█' * bars}{'░' * (10 - bars)}" # Full block '█', empty block '░'
        
        if strength >= 0.7: # Strong signal (high confidence)
            color = NEON_GREEN
        elif strength >= 0.4: # Moderate signal
            color = NEON_YELLOW
        else: # Weak signal
            color = ERROR_RED
        
        return f"{color}{strength_bar_chars} {strength:.0%}{Style.RESET_ALL}"
    
    def _format_position_status(self) -> str:
        """Helper function to format and colorize the current trading position status, including live unrealized PnL."""
        if not self.current_position:
            return f"{NEON_YELLOW}No Position Open{Style.RESET_ALL}"
        
        try:
            # Fetch current live price to calculate unrealized PnL
            ticker_response = self.client.get_tickers(category="linear", symbol=self.symbol)
            if ticker_response and ticker_response['retCode'] == 0:
                current_price = float(ticker_response['result']['list'][0]['lastPrice'])
            else:
                logger.warning(f"{WARNING_ORANGE}Could not fetch live price for position status display. Displaying stale PnL.{Style.RESET_ALL}")
                current_price = self.current_position.entry_price # Fallback for PnL calculation if price fetching fails

            # Calculate unrealized PnL for display
            pnl_usd = self.current_position.unrealized_pnl(current_price)
            pnl_pct = self.current_position.pnl_percentage(current_price)
            
            position_type_str = "Long" if self.current_position.side == PositionSide.BUY else "Short"
            pnl_color = SUCCESS_GREEN if pnl_usd >= 0 else ERROR_RED # Green for profit/breakeven, red for loss
            
            # Format according to symbol's price precision
            return f"{NEON_MAGENTA}{position_type_str}{Style.RESET_ALL} | {pnl_color}{pnl_pct:+.2f}% (${pnl_usd:+.2f}){Style.RESET_ALL} @ Entry: {NEON_BLUE}${self.current_position.entry_price:.{self.symbol_info['price_precision']}f}{Style.RESET_ALL}"
            
        except Exception as e:
            logger.error(f"{ERROR_RED}Error getting live position status for display: {e}{Style.RESET_ALL}")
            return f"{NEON_MAGENTA}Position Open (Error retrieving PnL){Style.RESET_ALL}"
    
    def check_position_status(self):
        """Periodically queries Bybit for active positions and synchronizes local bot state.
        This is critical for bot resilience and accurate PnL tracking even after restarts or API issues.
        """
        try:
            response = self.client.get_positions(
                category="linear",
                symbol=self.symbol
            )
            
            if response and response['retCode'] == 0:
                # Filter for positions where quantity > 0 (active open positions)
                active_positions_on_exchange = [p for p in response['result']['list'] if float(p.get('size', 0)) > 0]
                
                if active_positions_on_exchange:
                    # Case 1: An active position exists on the exchange.
                    exchange_position = active_positions_on_exchange[0] # Assume only one position per symbol due to `max_positions = 1`
                    
                    if not self.current_position:
                        # Local bot state is None, but exchange has a position: bot likely restarted or reconnected.
                        # Re-sync local state from the exchange's data.
                        logger.warning(f"{WARNING_ORANGE}Bot re-synced! Local state empty, but Bybit has {exchange_position['side']} position (ID: {exchange_position.get('orderId', 'N/A')}). Syncing.{Style.RESET_ALL}")
                        self.current_position = Position(
                            side=PositionSide.BUY if exchange_position['side'] == "Buy" else PositionSide.SELL,
                            entry_price=float(exchange_position.get('avgPrice', 0)),
                            quantity=float(exchange_position.get('size', 0)),
                            timestamp=datetime.now(), # Use current time as entry time, original entry time is not directly available here
                            take_profit=float(exchange_position.get('takeProfit', 0)) if exchange_position.get('takeProfit') else 0.0,
                            stop_loss=float(exchange_position.get('stopLoss', 0)) if exchange_position.get('stopLoss') else 0.0,
                            order_id=exchange_position.get('orderId', 'N/A')
                        )
                        logger.info(f"{INFO_TEXT}Local bot state successfully synchronized with Bybit position ID: {self.current_position.order_id}.{Style.RESET_ALL}")
                    else:
                        # Case 2: Both local and exchange have a position. Verify consistency.
                        # Check if key parameters (entry price, quantity, TP, SL, order ID) match.
                        is_synced = (self.current_position.quantity == float(exchange_position.get('size', 0)) and
                                     self.current_position.entry_price == float(exchange_position.get('avgPrice', 0)) and
                                     self.current_position.take_profit == (float(exchange_position.get('takeProfit', 0)) if exchange_position.get('takeProfit') else 0.0) and
                                     self.current_position.stop_loss == (float(exchange_position.get('stopLoss', 0)) if exchange_position.get('stopLoss') else 0.0) and
                                     self.current_position.order_id == exchange_position.get('orderId', 'N/A'))
                        
                        if not is_synced:
                            logger.warning(f"{WARNING_ORANGE}Local position details differ from Bybit's! Updating local state from exchange to ensure consistency.{Style.RESET_ALL}")
                            # Update local state with the latest details from the exchange.
                            self.current_position.entry_price = float(exchange_position.get('avgPrice', 0))
                            self.current_position.quantity = float(exchange_position.get('size', 0))
                            self.current_position.take_profit = float(exchange_position.get('takeProfit', 0)) if exchange_position.get('takeProfit') else 0.0
                            self.current_position.stop_loss = float(exchange_position.get('stopLoss', 0)) if exchange_position.get('stopLoss') else 0.0
                            self.current_position.order_id = exchange_position.get('orderId', 'N/A')
                        
                else: # Case 3: No active positions found on the exchange.
                    if self.current_position:
                        # Local bot state indicated an open position, but Bybit reports none.
                        # This means the position was closed on the exchange (e.g., TP/SL hit or manually closed).
                        logger.info(f"{NEON_MAGENTA}Detected position closure on Bybit (ID: {self.current_position.order_id}). Logging trade stats.{Style.RESET_ALL}")
                        
                        # Capture the closed position data before clearing local state.
                        closed_pos_data_temp = self.current_position 
                        # Get the current market price for accurate PnL calculation of the *just closed* trade.
                        current_market_price_response = self.client.get_tickers(category="linear", symbol=self.symbol)
                        if current_market_price_response and current_market_price_response['retCode'] == 0:
                            final_exit_price = float(current_market_price_response['result']['list'][0]['lastPrice'])
                        else:
                            logger.warning(f"{WARNING_ORANGE}Could not fetch current price for final PnL calculation. Using entry price for PnL calculation (will be 0).{Style.RESET_ALL}")
                            final_exit_price = closed_pos_data_temp.entry_price # Fallback if price fetching fails
                        
                        self._log_trade_exit_stats(closed_pos_data_temp, final_exit_price) # Log statistics for this closed trade.
                        self.current_position = None # Clear local state as position is confirmed closed on exchange.
                        
            else:
                logger.error(f"{ERROR_RED}API Error during position status check: {response.get('retMsg', 'Unknown error')}. Position data might be stale.{Style.RESET_ALL}")
                
        except Exception as e:
            logger.error(f"{ERROR_RED}An exception occurred while checking and syncing position status: {e}{Style.RESET_ALL}")
    
    def save_trade_history(self):
        """Saves the accumulated trade history to a CSV file. This is called periodically and on shutdown."""
        if not self.trade_history:
            logger.info(f"{INFO_TEXT}No trade history recorded to save yet.{Style.RESET_ALL}")
            return
        
        try:
            df_history = pd.DataFrame(self.trade_history)
            # Create a unique filename with timestamp to avoid overwriting and for easy identification.
            filename = f"trade_history_{self.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            df_history.to_csv(filename, index=False)
            logger.info(f"{SUCCESS_GREEN}Trade history saved to {filename}{Style.RESET_ALL}")
            # Update the count of saved trades to prevent redundant saves in the same loop cycle.
            self.last_saved_trade_history_count = len(self.trade_history)
        except Exception as e:
            logger.error(f"{ERROR_RED}Error saving trade history to file: {e}{Style.RESET_ALL}")
    
    def run_bot(self):
        """The main execution loop for the scalping bot. It continuously fetches data, analyzes market conditions,
        generates trading signals, manages positions, and executes trades based on the defined strategy.
        """
        print(f"\n{NEON_GREEN}🚀 Bot started successfully!{Style.RESET_ALL}")
        print(f"{INFO_TEXT}Monitoring {self.symbol} on {self.interval}m timeframe. Loop delay: {self.loop_delay_seconds} seconds.{Style.RESET_ALL}\n")
        
        # Load symbol trading info once at startup for order parameter validation.
        self.symbol_info = self._get_symbol_exchange_info(self.symbol)
        if not self.symbol_info: # Critical failure if symbol info cannot be retrieved.
            logger.critical(f"{ERROR_RED}Failed to retrieve essential symbol trading information from Bybit. Bot cannot proceed.{Style.RESET_ALL}")
            sys.exit(1) # Exit the bot process with an error code.
        
        # Initialize trade history save counter
        self.last_saved_trade_history_count = 0
        
        while True:
            try:
                # --- Step 1: Synchronize local bot position state with Bybit's actual position status ---
                # This is crucial for resilience against restarts and ensures the bot knows its true state.
                self.check_position_status()
                
                # --- Step 2: Fetch raw candlestick data from Bybit ---
                raw_df = self.fetch_klines()
                if raw_df is None or raw_df.empty:
                    logger.warning(f"{WARNING_ORANGE}No klines data received from Bybit. Retrying in {self.loop_delay_seconds}s.{Style.RESET_ALL}")
                    time.sleep(self.loop_delay_seconds)
                    continue

                # --- Step 3: Check for sufficient data for indicator calculations ---
                # ZLSMA needs roughly 2*length for initial calculation stabilization, and CE needs its period + buffer.
                min_data_required = max(self.zlsma_length * 2, self.ce_atr_period) + 2 # Add buffer for prev candle and initial NaNs
                if len(raw_df) < min_data_required:
                    logger.warning(f"{WARNING_ORANGE}Not enough data ({len(raw_df)} candles) for indicators. Need approx {min_data_required} candles. Waiting for more data...{Style.RESET_ALL}")
                    time.sleep(self.loop_delay_seconds) # Wait for more data to accumulate
                    continue
                
                # Calculate Heikin Ashi candles from the raw data
                ha_df = self.calculate_heikin_ashi(raw_df.copy())
                
                # --- Step 4: Calculate technical indicators and append them to the HA DataFrame ---
                # ZLSMA based on Heikin Ashi Close prices
                ha_df['zlsma'] = self.calculate_zlsma(ha_df['ha_close'], self.zlsma_length)
                
                # Chandelier Exit (Long and Short lines) based on Heikin Ashi data
                ha_df['ce_long'], ha_df['ce_short'], _ = self.calculate_chandelier_exit( # ATR is not used directly in signal logic here
                    ha_df, self.ce_atr_period, self.ce_atr_multiplier
                )
                
                # Drop any rows with NaN values that result from indicator calculations (especially at the beginning)
                ha_df = ha_df.dropna().reset_index(drop=True)
                # Align raw_df indices with ha_df to ensure data consistency for analysis
                raw_df_aligned = raw_df.loc[ha_df.index].reset_index(drop=True) 
                
                if ha_df.empty or len(ha_df) < 2: # Need at least current and previous HA candle for signal generation
                    logger.warning(f"{WARNING_ORANGE}HA DataFrame is too short or empty after dropping NaNs. Cannot generate signals. Retrying.{Style.RESET_ALL}")
                    time.sleep(self.loop_delay_seconds)
                    continue

                # --- Step 5: Analyze overall market conditions and generate trading signals ---
                market_conditions = self.analyze_market_conditions(raw_df_aligned) # General market context from raw data
                signal = self.generate_trading_signals(ha_df, raw_df_aligned) # Trading signals derived from HA data and indicators
                self.last_signal = signal # Store the most recent signal for logging and state consistency
                
                # --- Step 6: Display current market status and bot's decisions ---
                self.display_market_status(raw_df_aligned, ha_df, signal, market_conditions)
                
                # --- Step 7: Execute trading logic based on generated signals and risk controls ---
                current_price_for_execution = raw_df_aligned.iloc[-1]['close'] # Use the latest raw close price for order execution
                
                # Only attempt trade entry if the circuit breaker is NOT active AND signal strength is adequate (>= 0.5)
                if self.consecutive_losses < self.max_consecutive_losses and signal.strength >= 0.5:
                    
                    if signal.action == 'BUY' and not self.current_position: # If BUY signal and no position is open
                        qty_to_trade = self.calculate_position_size(current_price_for_execution)
                        # Calculate TP and SL prices based on entry price and configured percentages
                        take_profit_price = current_price_for_execution * (1 + self.take_profit_percent)
                        stop_loss_price = current_price_for_execution * (1 - self.stop_loss_percent)
                        
                        self.place_order("Buy", qty_to_trade, take_profit_price, stop_loss_price, current_price_for_execution)
                    
                    elif signal.action == 'SELL' and not self.current_position: # If SELL signal and no position is open
                        qty_to_trade = self.calculate_position_size(current_price_for_execution)
                        take_profit_price = current_price_for_execution * (1 - self.take_profit_percent)
                        stop_loss_price = current_price_for_execution * (1 + self.stop_loss_percent)
                        
                        self.place_order("Sell", qty_to_trade, take_profit_price, stop_loss_price, current_price_for_execution)
                    
                    elif signal.action == 'CLOSE' and self.current_position:
                        # If a strategic CLOSE signal is generated and a position is open
                        self.close_position() 
                
                # --- Step 8: Update trailing stop for any open positions (if feature is enabled) ---
                if self.current_position and self.use_trailing_stop:
                    self.update_trailing_stop(current_price_for_execution)
                
                # --- Step 9: Perform periodic actions like saving trade history ---
                # Save history if new trades have been logged and it hasn't been saved recently.
                if len(self.trade_history) > 0 and len(self.trade_history) % 10 == 0 and len(self.trade_history) != self.last_saved_trade_history_count:
                    self.save_trade_history()
                
                # --- Step 10: Wait for the next loop iteration ---
                logger.info(f"{INFO_TEXT}Next market check in {self.loop_delay_seconds} seconds...{Style.RESET_ALL}")
                time.sleep(self.loop_delay_seconds)
                
            except KeyboardInterrupt:
                logger.warning(f"{WARNING_ORANGE}Bot manually stopped by user (KeyboardInterrupt)! Initiating graceful shutdown.{Style.RESET_ALL}")
                break # Exit the main while loop gracefully
            except Exception as e:
                # Catch any unexpected errors in the main loop to prevent bot crash
                logger.exception(f"{ERROR_RED}CRITICAL ERROR IN MAIN BOT LOOP: {e}. Bot will attempt to resume after a short pause.{Style.RESET_ALL}")
                # Pause before retrying to avoid rapid error loops and allow for potential recovery
                time.sleep(self.loop_delay_seconds // 2) 
        
        # --- Bot Shutdown Procedures ---
        # Final cleanup actions when the bot gracefully stops.
        if self.current_position:
            logger.warning(f"{WARNING_ORANGE}Bot is shutting down with an open position (ID: {self.current_position.order_id}). Please monitor and manage this position manually on Bybit to prevent unintended losses.{Style.RESET_ALL}")
        
        self.save_trade_history() # Ensure any remaining trade history is saved at shutdown
        logger.info(f"{NEON_GREEN}Bot process terminated. Session Total PnL: ${self.total_pnl:.2f}. Goodbye!{Style.RESET_ALL}")


if __name__ == "__main__":
    # --- Bot Configuration ---
    # !!! IMPORTANT: Review and adjust these parameters for your trading strategy and risk tolerance. !!!
    config = {
        'testnet': True,  # !!! Set to False for LIVE trading with real money !!!
        'symbol': 'BTCUSDT', # The cryptocurrency trading pair (e.g., 'BTCUSDT', 'ETHUSDT').
        'interval': '15',  # Candlestick interval: '1', '5', '15', '30', '60' (minutes), '240' (4 hours), 'D' (daily), 'W' (weekly).
        'klines_limit': 200, # Number of historical candles to fetch (must be sufficient for all indicators to calculate).
        'position_size_usd': 100.0, # Target USD value for each trade. The bot calculates the crypto quantity dynamically.
        'take_profit_percent': 0.015,  # Take Profit target: 1.5% profit.
        'stop_loss_percent': 0.01,     # Stop Loss limit: 1% maximum loss per trade.
        'max_positions': 1,            # Maximum number of concurrent open positions. Typically 1 for scalping strategies.
        'loop_delay_seconds': 60 * 15, # Delay between market checks in seconds. Recommend matching `interval` (e.g., 15 mins = 60*15).
        'use_trailing_stop': True,     # Enable the trailing stop-loss feature to potentially lock in more profits.
        'trailing_stop_percent': 0.005 # Trailing deviation (0.5% deviation from price peak/trough for SL adjustment).
    }
    
    try:
        # Create an instance of the BybitScalpingBot with the defined configuration
        bybit_bot = BybitScalpingBot(**config)
        # Run the main bot loop
        bybit_bot.run_bot()
    except Exception as e:
        # Catch any critical errors during bot initialization or startup
        logger.exception(f"{ERROR_RED}!!! UNHANDLED BOT EXCEPTION !!! Bot process terminated prematurely due to an unrecoverable error: {e}{Style.RESET_ALL}")
        # Ensure the process exits with an error code to signal failure
        sys.exit(1)
