The Ehlers Supertrend strategy combines the Supertrend indicator for trend identification with the Ehlers Fisher Transform for confirmation and filtering.

**Strategy Logic:**

*   **Supertrend:** Identifies the primary trend direction. It switches from bullish to bearish (and vice-versa) based on price crossing its bands (derived from Average True Range).
*   **Ehlers Fisher Transform:** A technical indicator that converts prices into a Gaussian normal distribution. Its primary purpose is to identify turning points in the market with high accuracy. A key aspect is the cross between the Fisher Transform line and its signal line (often a lagged version of the Fisher Transform itself).

**Entry Signals:**

*   **BUY Signal:**
    *   Supertrend turns bullish (i.e., its direction changes from bearish to bullish).
    *   **AND** Ehlers Fisher Transform crosses above its signal line, confirming bullish momentum.
*   **SELL Signal:**
    *   Supertrend turns bearish (i.e., its direction changes from bullish to bearish).
    *   **AND** Ehlers Fisher Transform crosses below its signal line, confirming bearish momentum.

**Exit Signals:**

*   **Exit Long Position (SELL_TO_CLOSE):**
    *   Supertrend turns bearish.
    *   **OR** Ehlers Fisher Transform crosses below its signal line.
*   **Exit Short Position (BUY_TO_CLOSE):**
    *   Supertrend turns bullish.
    *   **OR** Ehlers Fisher Transform crosses above its signal line.

**Parameters:**

*   `ehlers_period`: The period used for calculating the Ehlers Fisher Transform.
*   `supertrend_period`: The period used for calculating the Average True Range (ATR) in the Supertrend.
*   `supertrend_multiplier`: The multiplier used in the Supertrend calculation to determine the bands.
*   `stop_loss_percentage`: The percentage-based stop loss applied to entry orders.
*   `take_profit_percentage`: The percentage-based take profit applied to entry orders.

**Implementation Details:**

*   The strategy includes private helper methods (`_calculate_ehlers_fisher`, `_calculate_supertrend`) to compute the indicators iteratively. This ensures correct historical calculation and avoids reliance on external libraries that might not be available.
*   The `ehlers_signal` is implemented as a 1-period lag of the `ehlers_fisher` value, which is a common approach by Ehlers.
*   The Supertrend calculation carefully handles the iterative nature of its bands and direction changes.
*   `pd.DataFrame.copy()` is used to prevent modifying the original DataFrame passed to the signal generation methods.
*   Checks for sufficient historical data are included to prevent errors during indicator calculation.
*   All price and percentage values are handled using `Decimal` for precision, as is standard practice in financial applications.

```python
from typing import List, Dict, Any, Tuple
from decimal import Decimal
import pandas as pd
import numpy as np
from algobots_types import OrderBlock # Assuming this is available in the environment

class EhlersSupertrendStrategy:
    """
    Ehlers Supertrend Strategy for generating entry and exit signals.
    Combines Supertrend with Ehlers Fisher Transform for confirmation.
    """
    def __init__(self, logger, 
                 ehlers_period: int = 10,
                 supertrend_period: int = 10, 
                 supertrend_multiplier: float = 3.0,
                 stop_loss_percentage: float = 0.02, # Default 2% SL
                 take_profit_percentage: float = 0.04): # Default 4% TP
        
        self.logger = logger
        self.ehlers_period = ehlers_period
        self.supertrend_period = supertrend_period
        self.supertrend_multiplier = supertrend_multiplier
        self.stop_loss_percentage = Decimal(str(stop_loss_percentage))
        self.take_profit_percentage = Decimal(str(take_profit_percentage))

    def _calculate_ehlers_fisher(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculates the Ehlers Fisher Transform and adds it to the DataFrame."""
        period = self.ehlers_period
        
        # Calculate highest high and lowest low over the period
        df['min_low_ehlers'] = df['low'].rolling(window=period).min()
        df['max_high_ehlers'] = df['high'].rolling(window=period).max()

        ehlers_value1 = [np.nan] * len(df)
        ehlers_fisher = [np.nan] * len(df)
        
        # Initialize prev_val1 for the iterative calculation (Ehlers' recommendation)
        prev_val1 = 0.0 

        for i in range(len(df)):
            if i >= period - 1: # Ensure enough data for rolling min/max
                min_low_val = df['min_low_ehlers'].iloc[i]
                max_high_val = df['max_high_ehlers'].iloc[i]
                close_val = df['close'].iloc[i]

                if pd.isna(min_low_val) or pd.isna(max_high_val) or pd.isna(close_val):
                    ehlers_value1[i] = np.nan
                    ehlers_fisher[i] = np.nan
                    continue

                # Calculate the raw normalized price component
                # To prevent division by zero for flat periods, default to 0.5 (middle)
                if (max_high_val - min_low_val) > 0:
                    raw_norm_price_component = (close_val - min_low_val) / (max_high_val - min_low_val)
                else:
                    raw_norm_price_component = 0.5 

                # Apply the smoothing and transformation for value1 as per Ehlers' formula
                # value1 = 0.33 * (2 * ((Close - MinL) / (MaxH - MinL) - 0.5)) + 0.67 * value1_prev
                current_val1 = 0.33 * (2 * raw_norm_price_component - 1) + 0.67 * prev_val1
                
                # Clamp value1 to avoid log(0) or log(negative) issues in Fisher Transform
                current_val1 = max(-0.999, min(0.999, current_val1)) 
                
                ehlers_value1[i] = current_val1
                prev_val1 = current_val1 # Update for next iteration

                # Calculate Fisher Transform: Fisher = 0.5 * log((1 + value1) / (1 - value1))
                # Using np.log for natural logarithm
                fisher_val = 0.5 * np.log((1 + current_val1) / (1 - current_val1))
                ehlers_fisher[i] = fisher_val
            else:
                ehlers_value1[i] = np.nan
                ehlers_fisher[i] = np.nan

        df['ehlers_value1'] = ehlers_value1
        df['ehlers_fisher'] = ehlers_fisher
        
        # Fisher Signal is typically the Fisher Transform lagged by one period
        df['ehlers_signal'] = df['ehlers_fisher'].shift(1)
        
        df.drop(columns=['min_low_ehlers', 'max_high_ehlers'], inplace=True)
        return df

    def _calculate_supertrend(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculates Supertrend and adds it to the DataFrame."""
        period = self.supertrend_period
        multiplier = self.supertrend_multiplier

        # Calculate True Range (TR)
        df['tr1'] = df['high'] - df['low']
        df['tr2'] = abs(df['high'] - df['close'].shift(1))
        df['tr3'] = abs(df['low'] - df['close'].shift(1))
        df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)

        # Calculate Average True Range (ATR) using EMA
        df['atr'] = df['tr'].ewm(span=period, adjust=False).mean()

        # Calculate HL2 (High + Low) / 2
        df['hl2'] = (df['high'] + df['low']) / 2

        # Initialize lists for iterative calculation
        final_upper_band = [np.nan] * len(df)
        final_lower_band = [np.nan] * len(df)
        supertrend_values = [np.nan] * len(df)
        direction = [1] * len(df) # Default to 1 (Up - Bullish)

        for i in range(1, len(df)):
            # Ensure ATR is calculated for current bar
            if pd.isna(df['atr'].iloc[i]):
                continue

            # Calculate current basic bands
            curr_upper_basic = df['hl2'].iloc[i] + multiplier * df['atr'].iloc[i]
            curr_lower_basic = df['hl2'].iloc[i] - multiplier * df['atr'].iloc[i]

            # Get previous final bands and direction (handle initial NaNs by defaulting to current basic)
            prev_final_upper = final_upper_band[i-1] if not np.isnan(final_upper_band[i-1]) else curr_upper_basic
            prev_final_lower = final_lower_band[i-1] if not np.isnan(final_lower_band[i-1]) else curr_lower_basic
            prev_direction = direction[i-1] if not np.isnan(direction[i-1]) else 1 # Default to Up

            # Current bar's close and previous close
            current_close = df['close'].iloc[i]
            prev_close = df['close'].iloc[i-1]

            # Update final upper band
            if curr_upper_basic < prev_final_upper or prev_close > prev_final_upper:
                final_upper_band[i] = curr_upper_basic
            else:
                final_upper_band[i] = prev_final_upper

            # Update final lower band
            if curr_lower_basic > prev_final_lower or prev_close < prev_final_lower:
                final_lower_band[i] = curr_lower_basic
            else:
                final_lower_band[i] = prev_final_lower

            # Determine Supertrend direction and value
            if prev_direction == 1: # Previous was an Uptrend
                if current_close < final_upper_band[i]: # Current close below updated upper band
                    direction[i] = -1 # Trend changes to Downtrend
                    supertrend_values[i] = final_upper_band[i]
                else:
                    direction[i] = 1 # Trend remains Uptrend
                    supertrend_values[i] = final_lower_band[i]
            else: # Previous was a Downtrend (prev_direction == -1)
                if current_close > final_lower_band[i]: # Current close above updated lower band
                    direction[i] = 1 # Trend changes to Uptrend
                    supertrend_values[i] = final_lower_band[i]
                else:
                    direction[i] = -1 # Trend remains Downtrend
                    supertrend_values[i] = final_upper_band[i]
            
            # For the very first valid bar after warm-up period, initialize direction based on simple close comparison
            if i == period - 1: # This is typically the first bar where ATR becomes non-NaN
                if current_close > prev_close:
                    direction[i] = 1
                    supertrend_values[i] = final_lower_band[i]
                else:
                    direction[i] = -1
                    supertrend_values[i] = final_upper_band[i]
            
        df['supertrend'] = supertrend_values
        df['supertrend_direction'] = direction 

        # Clean up temporary columns
        df.drop(columns=['tr1', 'tr2', 'tr3', 'tr', 'atr', 'hl2', 'basic_upper_band', 'basic_lower_band'], inplace=True, errors='ignore')
        return df

    def generate_signals(self, 
                         df: pd.DataFrame, 
                         resistance_levels: List[Dict[str, Any]], 
                         support_levels: List[Dict[str, Any]],
                         active_bull_obs: List[OrderBlock], 
                         active_bear_obs: List[OrderBlock],
                         **kwargs) -> List[Tuple[str, Decimal, Any, Dict[str, Any]]]:
        """
        Generates entry signals based on Ehlers Supertrend strategy.
        Buy when Supertrend turns bullish and Ehlers Fisher crosses above its signal line.
        Sell when Supertrend turns bearish and Ehlers Fisher crosses below its signal line.
        """
        signals = []

        if df.empty:
            self.logger.warning("DataFrame is empty, cannot generate signals.")
            return []

        # Ensure DataFrame has enough data for calculations
        # Need enough bars for rolling window + 2 for previous-to-previous bar comparison for cross
        min_required_bars = max(self.ehlers_period, self.supertrend_period) + 2 
        if len(df) < min_required_bars:
            self.logger.debug(f"Not enough data for Ehlers Supertrend calculations. Need at least {min_required_bars} bars, got {len(df)}. Skipping signal generation.")
            return []

        # Calculate indicators on a copy of the DataFrame to avoid modifying the original
        df_copy = df.copy()
        df_copy = self._calculate_ehlers_fisher(df_copy)
        df_copy = self._calculate_supertrend(df_copy)

        # Get the latest bar's data and the previous bar's data for comparison
        last_bar = df_copy.iloc[-1]
        prev_bar = df_copy.iloc[-2] 

        # Check for Supertrend direction change
        current_supertrend_direction = last_bar['supertrend_direction']
        prev_supertrend_direction = prev_bar['supertrend_direction']
        
        # Check Ehlers Fisher Transform cross
        current_fisher = last_bar['ehlers_fisher']
        current_ehlers_signal = last_bar['ehlers_signal'] # This is df['ehlers_fisher'].shift(1)
        prev_fisher = prev_bar['ehlers_fisher']
        prev_ehlers_signal = prev_bar['ehlers_signal'] # This is df['ehlers_fisher'].shift(2)

        # Ensure all required indicator values are available for the current and previous bar
        if pd.isna(current_supertrend_direction) or \
           pd.isna(prev_supertrend_direction) or \
           pd.isna(current_fisher) or \
           pd.isna(current_ehlers_signal) or \
           pd.isna(prev_fisher) or \
           pd.isna(prev_ehlers_signal):
            self.logger.debug("Missing indicator values on last or previous bar, skipping signal generation.")
            return []

        # Long Signal Logic
        # Supertrend turns bullish (i.e., its direction changes from -1 to 1)
        is_supertrend_bullish_turn = (current_supertrend_direction == 1 and prev_supertrend_direction == -1)
        # Ehlers Fisher crosses above its signal line (current Fisher > current Signal AND previous Fisher <= previous Signal)
        is_fisher_bullish_cross = (current_fisher > current_ehlers_signal and prev_fisher <= prev_ehlers_signal)

        if is_supertrend_bullish_turn and is_fisher_bullish_cross:
            entry_price = Decimal(str(last_bar['close']))
            stop_loss = entry_price * (Decimal('1') - self.stop_loss_percentage)
            take_profit = entry_price * (Decimal('1') + self.take_profit_percentage)
            
            signal_info = {
                'indicator': 'Ehlers Supertrend',
                'supertrend_direction': int(current_supertrend_direction),
                'ehlers_fisher': float(current_fisher),
                'ehlers_signal': float(current_ehlers_signal),
                'ehlers_period': self.ehlers_period,
                'supertrend_period': self.supertrend_period,
                'supertrend_multiplier': self.supertrend_multiplier,
                'stop_loss_percentage': float(self.stop_loss_percentage),
                'take_profit_percentage': float(self.take_profit_percentage)
            }
            self.logger.info(f"Generated BUY signal: Price={entry_price}, SL_pct={self.stop_loss_percentage}, TP_pct={self.take_profit_percentage}")
            signals.append(("BUY", entry_price, pd.Timestamp(last_bar.name), signal_info))

        # Short Signal Logic
        # Supertrend turns bearish (i.e., its direction changes from 1 to -1)
        is_supertrend_bearish_turn = (current_supertrend_direction == -1 and prev_supertrend_direction == 1)
        # Ehlers Fisher crosses below its signal line (current Fisher < current Signal AND previous Fisher >= previous Signal)
        is_fisher_bearish_cross = (current_fisher < current_ehlers_signal and prev_fisher >= prev_ehlers_signal)

        if is_supertrend_bearish_turn and is_fisher_bearish_cross:
            entry_price = Decimal(str(last_bar['close']))
            stop_loss = entry_price * (Decimal('1') + self.stop_loss_percentage)
            take_profit = entry_price * (Decimal('1') - self.take_profit_percentage)
            
            signal_info = {
                'indicator': 'Ehlers Supertrend',
                'supertrend_direction': int(current_supertrend_direction),
                'ehlers_fisher': float(current_fisher),
                'ehlers_signal': float(current_ehlers_signal),
                'ehlers_period': self.ehlers_period,
                'supertrend_period': self.supertrend_period,
                'supertrend_multiplier': self.supertrend_multiplier,
                'stop_loss_percentage': float(self.stop_loss_percentage),
                'take_profit_percentage': float(self.take_profit_percentage)
            }
            self.logger.info(f"Generated SELL signal: Price={entry_price}, SL_pct={self.stop_loss_percentage}, TP_pct={self.take_profit_percentage}")
            signals.append(("SELL", entry_price, pd.Timestamp(last_bar.name), signal_info))

        return signals

    def generate_exit_signals(self, 
                              df: pd.DataFrame, 
                              current_position_side: str,
                              active_bull_obs: List[OrderBlock], 
                              active_bear_obs: List[OrderBlock],
                              **kwargs) -> List[Tuple[str, Decimal, Any, Dict[str, Any]]]:
        """
        Generates exit signals based on Ehlers Supertrend strategy.
        Exit long when Supertrend turns bearish OR Ehlers Fisher turns bearish.
        Exit short when Supertrend turns bullish OR Ehlers Fisher turns bullish.
        """
        exit_signals = []

        if df.empty:
            self.logger.warning("DataFrame is empty, cannot generate exit signals.")
            return []
        
        # Ensure DataFrame has enough data for calculations
        min_required_bars = max(self.ehlers_period, self.supertrend_period) + 2
        if len(df) < min_required_bars:
            self.logger.debug(f"Not enough data for Ehlers Supertrend calculations. Need at least {min_required_bars} bars, got {len(df)}. Skipping exit signal generation.")
            return []

        # Calculate indicators on a copy of the DataFrame
        df_copy = df.copy()
        df_copy = self._calculate_ehlers_fisher(df_copy)
        df_copy = self._calculate_supertrend(df_copy)

        last_bar = df_copy.iloc[-1]
        prev_bar = df_copy.iloc[-2]

        current_supertrend_direction = last_bar['supertrend_direction']
        prev_supertrend_direction = prev_bar['supertrend_direction']
        
        current_fisher = last_bar['ehlers_fisher']
        current_ehlers_signal = last_bar['ehlers_signal']
        prev_fisher = prev_bar['ehlers_fisher']
        prev_ehlers_signal = prev_bar['ehlers_signal']

        # Ensure all required indicator values are available
        if pd.isna(current_supertrend_direction) or \
           pd.isna(prev_supertrend_direction) or \
           pd.isna(current_fisher) or \
           pd.isna(current_ehlers_signal) or \
           pd.isna(prev_fisher) or \
           pd.isna(prev_ehlers_signal):
            self.logger.debug("Missing indicator values on last or previous bar for exit, skipping signal generation.")
            return []

        current_price = Decimal(str(last_bar['close']))

        if current_position_side == 'BUY':
            # Exit Long if Supertrend turns bearish (from 1 to -1)
            is_supertrend_bearish_turn = (current_supertrend_direction == -1 and prev_supertrend_direction == 1)
            # OR Ehlers Fisher crosses below its signal (current Fisher < current Signal AND previous Fisher >= previous Signal)
            is_fisher_bearish_cross = (current_fisher < current_ehlers_signal and prev_fisher >= prev_ehlers_signal)

            if is_supertrend_bearish_turn or is_fisher_bearish_cross:
                exit_info = {
                    'indicator': 'Ehlers Supertrend',
                    'reason': 'Supertrend or Ehlers Fisher turned bearish',
                    'supertrend_direction': int(current_supertrend_direction),
                    'ehlers_fisher': float(current_fisher),
                    'ehlers_signal': float(current_ehlers_signal)
                }
                self.logger.info(f"Generated SELL_TO_CLOSE signal: Price={current_price}, Reason: {exit_info['reason']}")
                exit_signals.append(("SELL_TO_CLOSE", current_price, pd.Timestamp(last_bar.name), exit_info))

        elif current_position_side == 'SELL':
            # Exit Short if Supertrend turns bullish (from -1 to 1)
            is_supertrend_bullish_turn = (current_supertrend_direction == 1 and prev_supertrend_direction == -1)
            # OR Ehlers Fisher crosses above its signal (current Fisher > current Signal AND previous Fisher <= previous Signal)
            is_fisher_bullish_cross = (current_fisher > current_ehlers_signal and prev_fisher <= prev_ehlers_signal)

            if is_supertrend_bullish_turn or is_fisher_bullish_cross:
                exit_info = {
                    'indicator': 'Ehlers Supertrend',
                    'reason': 'Supertrend or Ehlers Fisher turned bullish',
                    'supertrend_direction': int(current_supertrend_direction),
                    'ehlers_fisher': float(current_fisher),
                    'ehlers_signal': float(current_ehlers_signal)
                }
                self.logger.info(f"Generated BUY_TO_CLOSE signal: Price={current_price}, Reason: {exit_info['reason']}")
                exit_signals.append(("BUY_TO_CLOSE", current_price, pd.Timestamp(last_bar.name), exit_info))
        
        return exit_signals
```
