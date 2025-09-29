import decimal  # Import the decimal module itself for exception handling
from decimal import (  # Import Decimal and InvalidOperation for safety
    Decimal,
)
from typing import Any

import pandas as pd

# --- Pyrmethus's Color Codex ---
# Assuming color_codex.py provides these constants.
# If not, define them here or ensure the file is accessible.
try:
    from color_codex import (
        COLOR_BLUE,
        COLOR_BOLD,
        COLOR_CYAN,
        COLOR_DIM,
        COLOR_GREEN,
        COLOR_MAGENTA,
        COLOR_RED,
        COLOR_RESET,
        COLOR_YELLOW,
        PYRMETHUS_BLUE,
        PYRMETHUS_GREEN,
        PYRMETHUS_GREY,
        PYRMETHUS_ORANGE,
        PYRMETHUS_PURPLE,
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
    """Helper function to format indicator values, handling Decimal, None, NaN,
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


def _get_latest(df: pd.DataFrame, col: str, precision: int) -> str:
    if col not in df or df[col].empty:
        return "N/A"
    return _format_indicator(df[col].iloc[-1], precision=precision)


def display_market_info(
    klines_df: pd.DataFrame | None,
    current_price: Decimal,
    symbol: str,
    pivot_resistance_levels: dict[str, Decimal],
    pivot_support_levels: dict[str, Decimal],
    bot_logger: Any,  # Assuming bot_logger is passed for warnings
    order_book_imbalance: Decimal | None = None,
    last_signal: dict[str, Any] | None = None,  # New parameter for last signal
):
    """Prints current market information to the console with enhanced formatting and clarity.
    Improvements:
    - Uses a helper function for consistent indicator formatting.
    - Sorts and formats pivot levels for better readability.
    - Ensures consistent price formatting and handles potential data issues gracefully.
    - Displays the last generated trading signal.
    """
    lines = []
    try:
        # Initial check for klines_df validity
        if klines_df is None or len(klines_df) < 2:
            bot_logger.warning(
                "No klines_df available or not enough data to display full market info."
            )
            if current_price > Decimal("0"):
                lines.append(
                    f"\n{PYRMETHUS_BLUE}📊 Current Price ({symbol}): {COLOR_CYAN}{current_price:.4f}{COLOR_RESET}"
                )
            print("\n".join(lines))
            return

        # Determine price color based on the last two closing prices
        try:
            previous_close = klines_df["close"].iloc[-2]
            if current_price > previous_close:
                price_color = PYRMETHUS_GREEN
            elif current_price < previous_close:
                price_color = COLOR_RED
            else:
                price_color = COLOR_CYAN
        except IndexError:
            price_color = COLOR_CYAN
            bot_logger.debug(
                "Could not compare current price to previous close due to insufficient data."
            )

        # Get the latest timestamp, ensuring it's available
        try:
            timestamp_str = klines_df.index[-1].strftime("%Y-%m-%d %H:%M:%S")
        except IndexError:
            timestamp_str = "N/A"
            bot_logger.debug("Timestamp unavailable due to empty klines_df.")

        # header
        lines.append(
            f"\n{PYRMETHUS_BLUE}📊 Current Price ({symbol}): {price_color}{current_price:.4f}{COLOR_RESET} @ {timestamp_str}"
        )

        # indicators
        lines.append(f"{COLOR_CYAN}--- Indicators ---{COLOR_RESET}")
        indicators_to_display = [
            ("StochRSI K", "stoch_k", 2, "📈"),
            ("StochRSI D", "stoch_d", 2, ""),
            ("ATR", "atr", 4, "🌊"),
            ("SMA", "sma", 4, "📊"),
            ("Fisher", "ehlers_fisher", 4, "🎣"),
            ("Fisher Sig", "ehlers_signal", 4, ""),
            ("Supersmth", "ehlers_supersmoother", 4, "✨"),
            ("Supertrend", "supertrend", 4, "📈"),
            ("SupertrendDir", "supertrend_direction", 0, "🧭"),
            ("Imbalance", None, 4, "⚖️"),  # None for column as it's a direct value
        ]

        for name, col, prec, icon in indicators_to_display:
            if col is None:  # For direct values like imbalance
                val = _format_indicator(order_book_imbalance, precision=prec)
            else:
                val = _get_latest(klines_df, col, prec)
            lines.append(f"{PYRMETHUS_BLUE}{icon} {name}: {val}{COLOR_RESET}")

        # pivot levels
        if pivot_resistance_levels or pivot_support_levels:
            lines.append(f"{COLOR_CYAN}--- Pivot Levels ---{COLOR_RESET}")
            all_levels = []
            for dct, is_res in (
                (pivot_resistance_levels, True),
                (pivot_support_levels, False),
            ):
                for lvl, price in dct.items():
                    all_levels.append((lvl, price, is_res))
            all_levels.sort(key=lambda x: abs(x[1] - current_price))
            for lvl, price, is_res in all_levels:
                colr = PYRMETHUS_GREEN if is_res else PYRMETHUS_PURPLE
                label = "R" if is_res else "S"
                price_str = _format_indicator(price, precision=4)
                lines.append(f"  {colr}{label}{COLOR_RESET}: {price_str} ({lvl})")

        # Last Signal Display
        if last_signal:
            lines.append(f"{COLOR_CYAN}--- Last Signal ---{COLOR_RESET}")
            signal_type = last_signal.get("type", "N/A")
            signal_price = _format_indicator(last_signal.get("price"), precision=4)
            signal_info = last_signal.get("info", {})

            signal_color = (
                PYRMETHUS_GREEN if "BUY" in signal_type.upper() else COLOR_RED
            )
            lines.append(
                f"{signal_color}💡 {signal_type.upper()} @ {signal_price}{COLOR_RESET}"
            )
            for key, value in signal_info.items():
                if key not in ["stop_loss_percentage", "take_profit_percentage"]:
                    lines.append(
                        f"  {PYRMETHUS_GREY}{key.replace('_', ' ').title()}: {value}{COLOR_RESET}"
                    )

    except Exception as e:
        bot_logger.error(f"Error displaying market info: {e}")
        lines.append(
            f"{COLOR_RED}Error displaying market info. Check logs for details.{COLOR_RESET}"
        )
    finally:
        print("\n".join(lines))
