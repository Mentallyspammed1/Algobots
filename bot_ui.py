import pandas as pd
from typing import Any, Dict, List, Optional
from decimal import Decimal, InvalidOperation # Import Decimal and InvalidOperation for safety
import decimal # Import the decimal module itself for exception handling

# --- Pyrmethus's Color Codex ---
# Assuming color_codex.py provides these constants.
# If not, define them here or ensure the file is accessible.
try:
    from color_codex import (
        COLOR_RESET, COLOR_BOLD, COLOR_DIM,
        COLOR_RED, COLOR_GREEN, COLOR_YELLOW, COLOR_BLUE, COLOR_MAGENTA, COLOR_CYAN,
        PYRMETHUS_GREEN, PYRMETHUS_BLUE, PYRMETHUS_PURPLE, PYRMETHUS_ORANGE, PYRMETHUS_GREY
    )
except ImportError:
    # Define fallback colors if color_codex is not available
    COLOR_RESET = "\033[0m"
    COLOR_BOLD = "\033[1m"
    COLOR_DIM = "\033[2m"
    COLOR_RED = "\033[31m"
    COLOR_GREEN = "\033[32m"
    COLOR_YELLOW = "\033[33m"
    COLOR_BLUE = "\033[34m"
    COLOR_MAGENTA = "\033[35m"
    COLOR_CYAN = "\033[36m"
    PYRMETHUS_GREEN = COLOR_GREEN
    PYRMETHUS_BLUE = COLOR_BLUE
    PYRMETHUS_PURPLE = COLOR_MAGENTA
    PYRMETHUS_ORANGE = COLOR_YELLOW
    PYRMETHUS_GREY = COLOR_DIM

def _format_indicator(value: Any, default: str = "N/A", precision: int = 4) -> str:
    """
    Helper function to format indicator values, handling Decimal, None, NaN,
    and potential formatting errors gracefully.
    """
    if value is None or pd.isna(value):
        return default
    try:
        # Attempt to format as Decimal with specified precision
        return f"{Decimal(str(value)):.{precision}f}"
    except (TypeError, ValueError, decimal.InvalidOperation):
        # Fallback for non-Decimal types or formatting errors
        # Log this occurrence if it happens unexpectedly
        # logger.debug(f"Could not format indicator value '{value}' as Decimal with precision {precision}. Returning as string.")
        return str(value)

def display_market_info(
    klines_df: Optional[pd.DataFrame],
    current_price: Decimal,
    symbol: str,
    pivot_resistance_levels: Dict[str, Decimal],
    pivot_support_levels: Dict[str, Decimal],
    order_book_imbalance: Decimal,
    bot_logger: Any # Assuming bot_logger is passed for warnings
):
    """
    Prints current market information to the console with enhanced formatting and clarity.
    Improvements:
    - Uses a helper function for consistent indicator formatting.
    - Sorts and formats pivot levels for better readability.
    - Ensures consistent price formatting and handles potential data issues gracefully.
    """
    # Initial check for klines_df validity
    if klines_df is None or len(klines_df) < 2:
        bot_logger.warning("No klines_df available or not enough data to display full market info.")
        # Still print the current price if available
        if current_price > Decimal('0'):
             print(f"\n{PYRMETHUS_BLUE}📊 Current Price ({symbol}): {COLOR_CYAN}{current_price:.4f}{COLOR_RESET}")
        return

    # Determine price color based on the last two closing prices
    try:
        # Safely access the second to last close price
        previous_close = klines_df['close'].iloc[-2]
        if current_price > previous_close:
            price_color = PYRMETHUS_GREEN
        elif current_price < previous_close:
            price_color = COLOR_RED
        else:
            price_color = COLOR_CYAN
    except IndexError:
        # This case should ideally not be reached due to the len(klines_df) < 2 check,
        # but included for maximum safety.
        price_color = COLOR_CYAN
        bot_logger.debug("Could not compare current price to previous close due to insufficient data.")

    # Fetch latest indicator values using the helper function
    # Use .get() for safer column access in case a column is missing
    latest_stoch_k = _format_indicator(klines_df.get('stoch_k', pd.Series()).iloc[-1] if 'stoch_k' in klines_df else None, precision=2)
    latest_stoch_d = _format_indicator(klines_df.get('stoch_d', pd.Series()).iloc[-1] if 'stoch_d' in klines_df else None, precision=2)
    latest_atr = _format_indicator(klines_df.get('atr', pd.Series()).iloc[-1] if 'atr' in klines_df else None, precision=4)
    latest_sma = _format_indicator(klines_df.get('sma', pd.Series()).iloc[-1] if 'sma' in klines_df else None, precision=4) # Corrected 'klines' to 'klines_df'
    latest_ehlers_fisher = _format_indicator(klines_df.get('ehlers_fisher', pd.Series()).iloc[-1] if 'ehlers_fisher' in klines_df else None, precision=4)
    latest_ehlers_fisher_signal = _format_indicator(klines_df.get('ehlers_fisher_signal', pd.Series()).iloc[-1] if 'ehlers_fisher_signal' in klines_df else None, precision=4)
    latest_ehlers_supersmoother = _format_indicator(klines_df.get('ehlers_supersmoother', pd.Series()).iloc[-1] if 'ehlers_supersmoother' in klines_df else None, precision=4)
    formatted_imbalance = _format_indicator(order_book_imbalance, precision=4)

    # Get the latest timestamp, ensuring it's available
    try:
        timestamp_str = klines_df.index[-1].strftime('%Y-%m-%d %H:%M:%S')
    except IndexError:
        timestamp_str = "N/A"
        bot_logger.debug("Timestamp unavailable due to empty klines_df.")

    # Print the formatted market information
    print(f"\n{PYRMETHUS_BLUE}📊 Current Price ({symbol}): {price_color}{current_price:.4f}{COLOR_RESET} @ {timestamp_str}")
    print(f"{PYRMETHUS_BLUE}📈 StochRSI K: {latest_stoch_k}, D: {latest_stoch_d}{COLOR_RESET}")
    print(f"{PYRMETHUS_BLUE}🌊 ATR: {latest_atr}{COLOR_RESET}")
    print(f"{PYRMETHUS_BLUE}📊 SMA: {latest_sma}{COLOR_RESET}")
    print(f"{PYRMETHUS_BLUE}🎣 Ehlers Fisher: {latest_ehlers_fisher}, Signal: {latest_ehlers_fisher_signal}{COLOR_RESET}")
    print(f"{PYRMETHUS_BLUE}✨ Ehlers Super Smoother: {latest_ehlers_supersmoother}{COLOR_RESET}")
    print(f"{PYRMETHUS_BLUE}⚖️ Order Book Imbalance: {formatted_imbalance}{COLOR_RESET}")

    # Display Pivot Levels, sorted by proximity to current price
    if pivot_resistance_levels or pivot_support_levels:
        all_pivot_levels = []
        # Combine resistance levels
        if pivot_resistance_levels:
            all_pivot_levels.extend([
                {'type': r_type, 'price': r_price, 'is_resistance': True}
                for r_type, r_price in pivot_resistance_levels.items()
            ])
        # Combine support levels
        if pivot_support_levels:
            all_pivot_levels.extend([
                {'type': s_type, 'price': s_price, 'is_resistance': False}
                for s_type, s_price in pivot_support_levels.items()
            ])
        
        # Sort by absolute difference from current price for relevance
        all_pivot_levels.sort(key=lambda x: abs(x['price'] - current_price))

        if all_pivot_levels:
            print(f"{COLOR_CYAN}--- Pivot Levels ---{COLOR_RESET}")
            for level in all_pivot_levels:
                # Format price using the helper function
                price_str = _format_indicator(level['price'], precision=4)
                # Determine color and label for resistance/support
                level_type_color = PYRMETHUS_GREEN if level['is_resistance'] else PYRMETHUS_PURPLE
                level_type_str = f"{level_type_color}R{COLOR_RESET}" if level['is_resistance'] else f"{level_type_color}S{COLOR_RESET}"
                print(f"  {level_type_str}: {price_str} ({level['type']})")

