import hashlib
import hmac
import json
import logging
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import (
    ROUND_DOWN,
    ROUND_HALF_EVEN,
    ROUND_UP,
    Decimal,
    InvalidOperation,
    getcontext,
)
from functools import wraps
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Final

import ccxt
import numpy as np
import pandas as pd
import pandas_ta as ta
import requests
import websocket  # pip install websocket-client
from colorama import Fore, Style, init

# Ensure python-dotenv is installed for load_dotenv
try:
    from dotenv import load_dotenv
except ImportError:
    print(
        f"{Fore.YELLOW}Warning: 'python-dotenv' not found. Please install it: pip install python-dotenv{Style.RESET_ALL}",
    )
    print(
        f"{Fore.YELLOW}Environment variables will not be loaded from .env file.{Style.RESET_ALL}",
    )

    def load_dotenv():
        pass  # Dummy function if not installed


# Initialize Colorama for beautiful terminal output, resetting colors automatically.
init(autoreset=True)

# Define a placeholder ZoneInfo class for fallback if zoneinfo/tzdata is not available.


class _FallbackZoneInfo:
    """A fallback implementation for `zoneinfo.ZoneInfo` for environments
    where `zoneinfo` (Python 3.9+) or `tzdata` is not available.
    It defaults to UTC and issues a warning upon first instantiation.
    """

    _warning_printed = False

    def __init__(self, key: str):
        if not _FallbackZoneInfo._warning_printed:
            print(
                f"{Fore.YELLOW}Warning: 'zoneinfo' or 'tzdata' module (for full timezone support) could not be imported. For full timezone support, please install 'tzdata': {Style.BRIGHT}pip install tzdata{Style.RESET_ALL}",
            )
            print(
                f"{Fore.YELLOW}Falling back to a basic UTC timezone handler. This may affect timestamp accuracy for non-UTC timezones.{Style.RESET_ALL}",
            )
            _FallbackZoneInfo._warning_printed = True

        self._offset = timedelta(0)  # UTC offset
        self._key = key
        # Only print specific timezone warning if not UTC and general warning already printed
        if key.lower() != "utc":
            print(
                f"{Fore.YELLOW}Warning: Timezone '{key}' not fully supported by fallback ZoneInfo. Using UTC.{Style.RESET_ALL}",
            )

    def __call__(self, dt: datetime = None) -> timezone:
        """Returns a timezone object for the given datetime, or a UTC timezone if dt is None."""
        return timezone(self._offset)

    def fromutc(self, dt: datetime) -> datetime:
        """Converts a UTC datetime to a timezone-aware datetime in this timezone."""
        return dt.replace(tzinfo=timezone(self._offset))

    def utcoffset(self, dt: datetime) -> timedelta:
        """Returns the UTC offset for the given datetime in this timezone."""
        return self._offset

    def dst(self, dt: datetime) -> timedelta:
        """Returns the daylight saving time (DST) adjustment for the given datetime."""
        return timedelta(0)

    def tzname(self, dt: datetime) -> str:
        """Returns the timezone name for the given datetime."""
        return self._key if self._key.lower() == "utc" else "UTC"


# Attempt to import ZoneInfo from standard library (Python 3.9+) or tzdata, otherwise use fallback.
try:
    if sys.version_info >= (3, 9):
        from zoneinfo import ZoneInfo
    else:
        try:
            from tzdata import ZoneInfo
        except ImportError:
            ZoneInfo = _FallbackZoneInfo
except ImportError as e:
    print(
        f"{Fore.YELLOW}Warning: 'zoneinfo' module (for full timezone support) could not be imported: {e}{Style.RESET_ALL}",
    )
    print(
        f"{Fore.YELLOW}If you are on Python 3.9+ and encounter issues, please install 'tzdata': {Style.BRIGHT}pip install tzdata{Style.RESET_ALL}",
    )
    print(
        f"{Fore.YELLOW}Falling back to a basic UTC timezone handler. For full timezone support, consider installing 'tzdata' or using Python 3.9+.{Style.RESET_ALL}",
    )
    ZoneInfo = _FallbackZoneInfo


# Set global precision for Decimal operations.
getcontext().prec = 38
# Load environment variables from .env file.
load_dotenv()

# Define chromatic constants for logging.
NG: Final[str] = Fore.LIGHTGREEN_EX + Style.BRIGHT  # Success, positive outcomes
# Information, process updates
NB: Final[str] = Fore.CYAN + Style.BRIGHT
# Headers, important messages, prompts
NP: Final[str] = Fore.MAGENTA + Style.BRIGHT
# Warnings, cautions, user input prompts
NY: Final[str] = Fore.YELLOW + Style.BRIGHT
# Errors, critical failures, alerts
NR: Final[str] = Fore.LIGHTRED_EX + Style.BRIGHT
# General neutral information
NC: Final[str] = Fore.CYAN + Style.BRIGHT
RST: Final[str] = Style.RESET_ALL  # Reset all styles

# Retrieve API keys from environment variables.
AK: Final[str | None] = os.getenv("BYBIT_API_KEY")
AS: Final[str | None] = os.getenv("BYBIT_API_SECRET")
if not AK or not AS:
    raise ValueError(
        f"{NR}BYBIT_API_KEY and BYBIT_API_SECRET must be set in your .env file. These are the keys to the exchange's digital gates!{RST}",
    )

# Define constant paths and default values.
CFP: Final[Path] = Path("config.json")  # Configuration file path
LD: Final[Path] = Path("bot_logs")  # Log directory path
# Trade records persistence path
TRP: Final[Path] = Path("trade_records.json")
DDTZ: Final[str] = "America/Chicago"  # Default timezone string
try:
    TZ: Final[ZoneInfo] = ZoneInfo(os.getenv("TIMEZONE", DDTZ))
except Exception as tz_err:
    print(
        f"{NY}Warning: Could not load timezone '{os.getenv('TIMEZONE', DDTZ)}'. Using UTC. Error: {tz_err}{RST}",
    )
    TZ = ZoneInfo("UTC")

MAR: Final[int] = 3  # Max API retry attempts
RDS: Final[int] = 5  # Retry delay in seconds
VI: Final[list[str]] = [
    "1",
    "3",
    "5",
    "15",
    "30",
    "60",
    "120",
    "240",
    "D",
    "W",
    "M",
]  # Valid intervals
CIM: Final[dict[str, str]] = {
    "1": "1m",
    "3": "3m",
    "5": "5m",
    "15": "15m",
    "30": "30m",
    "60": "1h",
    "120": "2h",
    "240": "4h",
    "D": "1d",
    "W": "1w",
    "M": "1M",
}
# HTTP response codes for retries
REC: Final[list[int]] = [429, 500, 502, 503, 504]

# Default Indicator Parameters (DIP) - using Decimal for precision
DIP: Final[dict[str, int | Decimal]] = {
    "atr_period": 14,
    "cci_window": 20,
    "williams_r_window": 14,
    "mfi_window": 14,
    "rsi_window": 14,
    "bollinger_bands_period": 20,
    "bollinger_bands_std_dev": Decimal("2.0"),
    "sma_10_window": 10,
    "ema_short_period": 9,
    "ema_long_period": 21,
    "momentum_period": 7,
    "volume_ma_period": 15,
    "fib_window": 50,
    "psar_af": Decimal("0.02"),
    "psar_max_af": Decimal("0.2"),
    # Removed: "stoch_rsi_window": 14, "stoch_window": 12, "k_window": 3, "d_window": 3
}
FL: Final[list[Decimal]] = [
    Decimal("0.0"),
    Decimal("0.236"),
    Decimal("0.382"),
    Decimal(
        # Fibonacci Levels
        "0.5",
    ),
    Decimal("0.618"),
    Decimal("0.786"),
    Decimal("1.0"),
]
LDS: Final[int] = 10 * 1024 * 1024  # Log file size in bytes (10 MB)
PCDS: Final[int] = 8  # Position Confirmation Delay Seconds

# Create log directory if it doesn't exist.
LD.mkdir(parents=True, exist_ok=True)

# --- Neon UI Helper Functions ---


def print_neon_header(text: str, color: str = NP, length: int = 60) -> None:
    """Prints a centered header with a neon-like border."""
    border_char = "✨"
    # Ensure text is not longer than length - (2 * border_char_len + 2 * spaces + 2 * dashes)
    max_text_len = length - (len(border_char) * 2 + 2 + 4)
    if len(text) > max_text_len:
        text = text[: max_text_len - 3] + "..."  # Truncate if too long

    header_text = f" {border_char}-- {text} --{border_char} "
    padding_total = length - len(header_text)
    padding_left = padding_total // 2
    padding_right = padding_total - padding_left

    full_header = f"{' ' * padding_left}{color}{header_text}{RST}{' ' * padding_right}"
    print(full_header)


def print_neon_separator(length: int = 60, char: str = "─", color: str = NC) -> None:
    """Prints a separator line."""
    print(f"{color}{char * length}{RST}")


def format_metric(
    label: str,
    value: Any,
    label_color: str,
    value_color: str | None = None,  # If None, uses label_color
    label_width: int = 22,
    value_precision: int = 2,
    unit: str = "",
    is_pnl: bool = False,
) -> str:
    """Formats a label and its value for neon display."""
    formatted_label = f"{label_color}{label:<{label_width}}{RST}"

    actual_value_color = value_color if value_color else label_color
    formatted_value = ""

    if isinstance(value, (Decimal, float)):
        if is_pnl:
            actual_value_color = NG if value >= 0 else NR
            sign = "+" if value > 0 else ""
            formatted_value = (
                f"{actual_value_color}{sign}{value:,.{value_precision}f}{unit}{RST}"
            )
        else:
            formatted_value = (
                f"{actual_value_color}{value:,.{value_precision}f}{unit}{RST}"
            )
    elif isinstance(value, int):
        if is_pnl:
            actual_value_color = NG if value >= 0 else NR
            sign = "+" if value > 0 else ""
            formatted_value = f"{actual_value_color}{sign}{value:,}{unit}{RST}"
        else:
            formatted_value = f"{actual_value_color}{value:,}{unit}{RST}"
    else:
        formatted_value = f"{actual_value_color}{value!s}{unit}{RST}"

    return f"{formatted_label}: {formatted_value}"


def print_table_header(columns: list[tuple[str, int]], header_color: str = NB) -> None:
    """Prints a formatted table header. columns is a list of (name, width) tuples."""
    header_parts = []
    for name, width in columns:
        # Ensure name is not longer than width - 2 for padding
        max_name_len = width - 2
        display_name = name
        if len(name) > max_name_len:
            display_name = name[: max_name_len - 1] + "."  # Truncate with a dot
        # Left align header text within cell
        header_parts.append(f"{display_name:<{width}}")
    print(f"{header_color}{' '.join(header_parts)}{RST}")
    # Print separator based on total width
    total_width = sum(width for _, width in columns) + len(columns) - 1
    print_neon_separator(length=total_width, char="═", color=header_color)


def print_table_row(
    row_data: list[Any],  # Can be any type, will be str() converted
    column_widths: list[int],
    cell_colors: list[str] | None = None,
    default_color: str = NC,
    decimal_precision: int = 2,  # For formatting Decimals/floats in rows
    # Indices of columns to treat as PnL
    pnl_columns: list[int] | None = None,
) -> None:
    """Prints a formatted table row."""
    if pnl_columns is None:
        pnl_columns = []

    formatted_cells = []
    for i, cell_value in enumerate(row_data):
        width = column_widths[i] if i < len(column_widths) else 10  # Default width
        color = default_color
        if cell_colors and i < len(cell_colors) and cell_colors[i]:
            color = cell_colors[i]

        cell_str = ""
        is_cell_pnl = i in pnl_columns

        if isinstance(cell_value, (Decimal, float)):
            if is_cell_pnl:
                color = NG if cell_value >= 0 else NR
                sign = "+" if cell_value > 0 else ""
                cell_str = f"{sign}{cell_value:,.{decimal_precision}f}"
            else:
                cell_str = f"{cell_value:,.{decimal_precision}f}"
        elif isinstance(cell_value, int) and is_cell_pnl:
            color = NG if cell_value >= 0 else NR
            sign = "+" if cell_value > 0 else ""
            cell_str = f"{sign}{cell_value:,}"
        else:
            cell_str = str(cell_value)

        # Truncate if too long for the cell width
        if len(cell_str) > width:
            cell_str = cell_str[: width - 1] + "…"

        formatted_cells.append(f"{color}{cell_str:<{width}}{RST}")

    print(" ".join(formatted_cells))


# --- End Neon UI Helper Functions ---


def clear_screen() -> None:
    """Clears the terminal screen using ANSI escape codes."""
    print("\033[H\033[J", end="")


def display_open_positions(
    open_trades: dict[str, TZ],
    market_infos: dict[str, dict],
    # Keyed by Bybit Symbol ID (e.g., BTCUSDT)
    current_prices: dict[str, Decimal | None],
    quote_currency: str,
    logger: logging.Logger,  # Pass a logger instance for uPnL calculation
) -> None:
    """Displays currently open positions in a neon-themed table."""
    table_length = 160  # Increased length to accommodate new columns
    print_neon_header("Open Positions", color=NP, length=table_length)

    if not open_trades:
        print(f"{NY}No open positions.{RST}")
        print_neon_separator(length=table_length, color=NP)
        print("")
        return

    columns = [
        ("Symbol", 18),
        ("Side", 6),
        ("Size", 12),
        ("Entry", 14),
        ("Current", 14),
        (f"uPnL ({quote_currency})", 18),
        ("uPnL (%)", 10),
        ("SL Info", 26),  # Increased width for TSL display
        ("TP Info", 14),
        ("Dist SL%", 10),
        ("Dist TP%", 10),
    ]
    column_widths = [width for _, width in columns]
    print_table_header(columns, header_color=NB)

    for trade_record in open_trades.values():
        symbol = trade_record.symbol
        market_info = market_infos.get(symbol)

        if not market_info:
            logger.warning(
                f"{NY}Market info for open trade on {symbol} is unavailable (possibly an unmanaged trade from a previous session or symbol data could not be fetched). Cannot display full details.{RST}",
            )
            # Print minimal info if market_info is missing
            row_data = [
                symbol,
                trade_record.side.upper(),
                str(trade_record.size),
                str(trade_record.entry_price),
                "N/A",
                "N/A",
                "N/A",
                "N/A",
                "N/A",
                "N/A",
                "N/A",  # For new columns
            ]
            cell_colors = [NC, NG if trade_record.side == "long" else NR] + [NC] * 9
            print_table_row(row_data, column_widths, cell_colors)
            continue

        bybit_symbol_id = market_info.get("id")
        current_price = current_prices.get(bybit_symbol_id)
        price_prec = TA.gpp(market_info, logger)
        size_prec = TA.gpp(market_info, logger)  # Or use amount precision

        # Update PnL for display
        if current_price is not None:
            trade_record.upnl(current_price, market_info, logger)
        else:  # If current price is not available, set PnL to None for display
            trade_record.pnl_quote = None
            trade_record.pnl_percentage = None

        side_color = NG if trade_record.side == "long" else NR

        # SL Info column
        sl_info_str = "N/A"
        if trade_record.trailing_stop_active:
            act_price_str = (
                f"{trade_record.tsl_activation_price:.{price_prec}f}"
                if trade_record.tsl_activation_price
                else "N/A"
            )
            # Assuming distance is price units
            dist_str = (
                f"{trade_record.trailing_stop_distance:.{price_prec}f}"
                if trade_record.trailing_stop_distance
                else "N/A"
            )
            sl_info_str = f"TSL Act:{act_price_str} / Trl:{dist_str}"
        elif trade_record.stop_loss_price:
            sl_info_str = f"{trade_record.stop_loss_price:.{price_prec}f}"

        # TP Info column
        tp_info_str = (
            f"{trade_record.take_profit_price:.{price_prec}f}"
            if trade_record.take_profit_price
            else "N/A"
        )

        # Distance to SL/TP %
        dist_sl_pct_str = "N/A"
        dist_tp_pct_str = "N/A"
        dist_sl_color = NB  # Default color for distances
        dist_tp_color = NB

        if current_price and trade_record.entry_price and trade_record.entry_price != 0:
            # Distance to SL %
            sl_target_for_dist_calc = None
            if trade_record.trailing_stop_active and trade_record.tsl_activation_price:
                sl_target_for_dist_calc = trade_record.tsl_activation_price
                # Note: This is distance to TSL *activation* price.
                # Actual TSL trails current price once active, so this % will become less relevant.
            elif not trade_record.trailing_stop_active and trade_record.stop_loss_price:
                sl_target_for_dist_calc = trade_record.stop_loss_price

            if sl_target_for_dist_calc:
                if trade_record.side == "long":
                    dist_sl_pct = (
                        (current_price - sl_target_for_dist_calc)
                        / trade_record.entry_price
                    ) * 100
                else:  # Short
                    dist_sl_pct = (
                        (sl_target_for_dist_calc - current_price)
                        / trade_record.entry_price
                    ) * 100
                dist_sl_pct_str = f"{dist_sl_pct:.2f}%"
                # Example: If distance is less than 0.5% (closer to SL)
                if dist_sl_pct < 0.5:
                    dist_sl_color = NR

            # Distance to TP %
            if trade_record.take_profit_price:
                if trade_record.side == "long":
                    dist_tp_pct = (
                        (trade_record.take_profit_price - current_price)
                        / trade_record.entry_price
                    ) * 100
                else:  # Short
                    dist_tp_pct = (
                        (current_price - trade_record.take_profit_price)
                        / trade_record.entry_price
                    ) * 100
                dist_tp_pct_str = f"{dist_tp_pct:.2f}%"
                # Example: If positive and distance is less than 0.5% (closer to TP)
                if 0 < dist_tp_pct < 0.5:
                    dist_tp_color = NG

        row_data_list = [
            trade_record.symbol,
            trade_record.side.upper(),
            f"{trade_record.size:.{size_prec}f}",
            f"{trade_record.entry_price:.{price_prec}f}",
            f"{current_price:.{price_prec}f}" if current_price is not None else "N/A",
            trade_record.pnl_quote if trade_record.pnl_quote is not None else "N/A",
            trade_record.pnl_percentage
            if trade_record.pnl_percentage is not None
            else "N/A",
            sl_info_str,
            tp_info_str,
            dist_sl_pct_str,
            dist_tp_pct_str,
        ]

        cell_custom_colors = [
            NC,  # Symbol
            side_color,  # Side
            NC,  # Size
            NC,  # Entry
            NB,  # Current Price
            None,  # uPnL Quote (handled by pnl_columns)
            None,  # uPnL % (handled by pnl_columns)
            NY,  # SL Info (Changed from NR to NY for less aggressive warning unless critically close)
            NG,  # TP Info
            dist_sl_color,  # Dist SL% (already handles NR for critical)
            dist_tp_color,  # Dist TP% (already handles NG for critical)
        ]
        # PnL columns are now 5 and 6 (0-indexed)
        print_table_row(
            row_data_list,
            column_widths,
            cell_colors=cell_custom_colors,
            default_color=NC,
            pnl_columns=[5, 6],
            decimal_precision=2,
        )  # Default precision for percentages

    print_neon_separator(length=table_length, color=NP)
    print("")


def display_recent_closed_trades(
    closed_trades: list[TZ],
    market_infos: dict[str, dict],
    quote_currency: str,
    logger: logging.Logger,  # For TA.gpp
    num_to_display: int = 5,
) -> None:
    """Displays recently closed positions in a neon-themed table."""
    # Adjusted table length: 130 (original) + 8 * (10+1 for new columns and spaces) = 130 + 88 = 218. Let's use 220.
    table_length = 220
    print_neon_header(
        f"Recent Closed Trades (Last {num_to_display})", color=NP, length=table_length,
    )

    if not closed_trades:
        print(f"{NY}No closed trades yet.{RST}")
        print_neon_separator(length=table_length, color=NP)
        print("")
        return

    columns = [
        ("Symbol", 18),
        ("Side", 6),
        ("Size", 12),
        ("Entry", 14),
        ("Exit", 14),
        (f"rPnL ({quote_currency})", 18),
        ("rPnL (%)", 10),
        ("Status", 12),
        ("E:RSI", 8),  # Entry RSI
        ("E:EMA_S", 10),  # Entry EMA Short
        ("E:EMA_L", 10),  # Entry EMA Long
        ("E:BBL", 10),  # Entry Bollinger Band Lower
        ("E:BBM", 10),  # Entry Bollinger Band Middle
        ("E:BBU", 10),  # Entry Bollinger Band Upper
        ("E:MOM", 10),  # Entry Momentum
        ("E:PSAR", 10),  # Entry PSAR
    ]
    column_widths = [width for _, width in columns]
    print_table_header(columns, header_color=NB)

    # Display the most recent trades
    recent_trades_to_show = closed_trades[-num_to_display:]

    for trade_record in recent_trades_to_show:
        symbol = trade_record.symbol
        market_info = market_infos.get(symbol)

        if not market_info:
            logger.warning(
                f"{NY}Market info not found for closed trade on {symbol}. Cannot display full price precision.{RST}",
            )
            price_prec = 2  # Default precision
            size_prec = 4  # Default precision
        else:
            price_prec = TA.gpp(market_info, logger)
            # Or use a specific amount precision if available
            size_prec = TA.gpp(market_info, logger)

        side_color = NG if trade_record.side == "long" else NR
        status_text = trade_record.status.replace("CLOSED_", "")  # Shorten status
        status_color = NC
        if "WIN" in status_text:
            status_color = NG
        elif "LOSS" in status_text:
            status_color = NR

        row_data_list = [
            trade_record.symbol,
            trade_record.side.upper(),
            f"{trade_record.size:.{size_prec}f}",
            f"{trade_record.entry_price:.{price_prec}f}"
            if trade_record.entry_price
            else "N/A",
            f"{trade_record.exit_price:.{price_prec}f}"
            if trade_record.exit_price
            else "N/A",
            trade_record.realized_pnl_quote
            if trade_record.realized_pnl_quote is not None
            else "N/A",
            trade_record.pnl_percentage
            if trade_record.pnl_percentage is not None
            else "N/A",
            status_text,
            f"{trade_record.entry_rsi:.2f}"
            if trade_record.entry_rsi is not None
            else "N/A",
            f"{trade_record.entry_ema_short:.{price_prec}f}"
            if trade_record.entry_ema_short is not None
            else "N/A",
            f"{trade_record.entry_ema_long:.{price_prec}f}"
            if trade_record.entry_ema_long is not None
            else "N/A",
            f"{trade_record.entry_bbl:.{price_prec}f}"
            if trade_record.entry_bbl is not None
            else "N/A",
            f"{trade_record.entry_bbm:.{price_prec}f}"
            if trade_record.entry_bbm is not None
            else "N/A",
            f"{trade_record.entry_bbu:.{price_prec}f}"
            if trade_record.entry_bbu is not None
            else "N/A",
            f"{trade_record.entry_momentum:.4f}"
            if trade_record.entry_momentum is not None
            else "N/A",
            f"{trade_record.entry_psar:.{price_prec}f}"
            if trade_record.entry_psar is not None
            else "N/A",
        ]

        cell_custom_colors = [
            NC,  # Symbol
            side_color,  # Side
            NC,  # Size
            NC,  # Entry
            NC,  # Exit
            None,  # rPnL Quote (handled by pnl_columns)
            None,  # rPnL % (handled by pnl_columns)
            status_color,  # Status
            NC,
            NC,
            NC,
            NC,
            NC,
            NC,
            NC,
            NC,  # Colors for new indicator columns
        ]

        print_table_row(
            row_data_list,
            column_widths,
            cell_colors=cell_custom_colors,
            default_color=NC,
            pnl_columns=[5, 6],  # Indices for rPnL (Quote) and rPnL (%)
            decimal_precision=4
            if quote_currency != "USDT"
            else 2,  # PnL quote precision
        )

    print_neon_separator(length=table_length, color=NP)
    print("")


class SF(logging.Formatter):
    """Sensitive Formatter: A custom logging formatter that redacts API keys
    from log messages for security.
    """

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        if AK:
            message = message.replace(AK, "***API_KEY_REDACTED***")
        if AS:
            message = message.replace(AS, "***API_SECRET_REDACTED***")
        return message


def _eck(
    current_config: dict[str, Any], default_config: dict[str, Any],
) -> dict[str, Any]:
    """Extend Current Config: Recursively adds missing keys from default_config
    to current_config, preserving existing values.
    """
    updated_config = current_config.copy()
    for key, default_value in default_config.items():
        if key not in updated_config:
            updated_config[key] = default_value
        elif isinstance(default_value, dict) and isinstance(
            updated_config.get(key), dict,
        ):
            updated_config[key] = _eck(updated_config[key], default_value)
    return updated_config


def _cdr(obj: Any, default_obj: Any) -> Any:
    """Convert Data Recursively: Attempts to convert data types in `obj` to match `default_obj`'s types,
    especially for Decimal, dict, and list, to ensure consistency with default config.
    """
    if isinstance(default_obj, Decimal):
        try:
            return Decimal(str(obj))
        except (InvalidOperation, TypeError, ValueError):
            return default_obj
    elif isinstance(default_obj, dict) and isinstance(obj, dict):
        new_obj = {}
        for k, v in obj.items():
            new_obj[k] = _cdr(v, default_obj.get(k))
        # Add keys from default_obj that are missing in obj
        for k, v in default_obj.items():
            if k not in obj:
                new_obj[k] = v
        return new_obj
    elif isinstance(default_obj, list) and isinstance(obj, list):
        if default_obj:
            # If default list has elements, try to convert elements to match the type of the first default element.
            # This assumes a homogeneous list type.
            return [_cdr(item, default_obj[0]) for item in obj]
        return obj  # Return original list if default is empty
    return obj


def _vncv(
    config_data: dict[str, Any],
    key: str,
    default_value: int | float | Decimal | None,
    min_value: int | float | Decimal | None = None,
    max_value: int | float | Decimal | None = None,
    is_integer: bool = False,
    allow_none: bool = False,
    logger: logging.Logger = logging.getLogger(__name__),
) -> bool:
    """Validate Numeric Config Value: Validates a numeric configuration value,
    correcting its type or range if necessary, and logs warnings.
    Returns True if a correction was made, False otherwise.
    """
    value = config_data.get(key)
    original_value = value
    corrected = False

    if allow_none and value is None:
        return False  # No correction needed if None is allowed and value is None

    # Handle boolean values which might be incorrectly parsed as numbers
    if isinstance(value, bool):
        logger.warning(
            f"{NR}Config value '{key}' ({value}) has an invalid type (boolean). Expected numeric. Setting to default.{RST}",
        )
        value = default_value
        corrected = True
    elif not isinstance(value, (int, float, Decimal)):
        logger.warning(
            f"{NR}Config value '{key}' ({value}) has invalid type {type(value).__name__}. Expected numeric. Setting to default.{RST}",
        )
        value = default_value
        corrected = True

    # Convert to Decimal for robust comparison and type checking
    if isinstance(value, (int, float, Decimal)):
        try:
            decimal_value = Decimal(str(value))
        except InvalidOperation:
            logger.warning(
                f"{NR}Config value '{key}' ({value}) cannot be converted to a number for range check. Using default.{RST}",
            )
            value = default_value
            corrected = True
            # Re-evaluate decimal_value from default
            decimal_value = Decimal(str(value))

        if is_integer and not isinstance(value, int):
            # Check if it's an integer after conversion to Decimal, or if it was initially a float that is an integer
            if not decimal_value == decimal_value.to_integral_value():
                logger.warning(
                    f"{NR}Config value '{key}' ({value}) must be an integer. Found non-integer numeric. Setting to default.{RST}",
                )
                value = default_value
                corrected = True
                # Re-evaluate decimal_value from default
                decimal_value = Decimal(str(value))

        # Range check
        if (min_value is not None and decimal_value < Decimal(str(min_value))) or (
            max_value is not None and decimal_value > Decimal(str(max_value))
        ):
            range_string = ""
            if min_value is not None:
                range_string += f" >= {min_value}"
            if max_value is not None:
                range_string += f" <= {max_value}"
            logger.warning(
                f"{NR}Config value '{key}' ({value}) out of range ({range_string.strip()}). Setting to default.{RST}",
            )
            value = default_value
            corrected = True

    if corrected:
        logger.warning(
            f"{NY}Corrected value for '{key}': {original_value} -> {value}{RST}",
        )
        config_data[key] = value
        return True
    return False


def lc(file_path: Path) -> dict[str, Any]:
    """Load Config: Loads and validates the configuration from `config.json`.
    If the file doesn't exist or is invalid, it creates a default one.
    """
    # Default configuration values
    default_config: Final[dict[str, Any]] = {
        "symbols_to_trade": ["BTC/USDT:USDT"],
        "interval": "5",
        "retry_delay": RDS,
        "enable_sms_alerts": False,
        "sms_recipient_number": "",
        "sms_alert_on_order_placement": True,
        "sms_alert_on_trade_close": True,
        "enable_periodic_pnl_sms": False,
        "periodic_pnl_sms_interval_minutes": 60,
        "atr_period": DIP["atr_period"],
        "ema_short_period": DIP["ema_short_period"],
        "ema_long_period": DIP["ema_long_period"],
        "rsi_period": DIP["rsi_window"],
        "bollinger_bands_period": DIP["bollinger_bands_period"],
        "bollinger_bands_std_dev": DIP["bollinger_bands_std_dev"],
        "cci_window": DIP["cci_window"],
        "williams_r_window": DIP["williams_r_window"],
        "mfi_window": DIP["mfi_window"],
        "fisher_period": 12,
        "psar_af": DIP["psar_af"],
        "psar_max_af": DIP["psar_max_af"],
        "sma_10_window": DIP["sma_10_window"],
        "momentum_period": DIP["momentum_period"],
        "volume_ma_period": DIP["volume_ma_period"],
        "adaptive_stoch_atr_period": 14,
        "adaptive_stoch_atr_smoothing_period": 50,
        "adaptive_stoch_min_lookback": 5,
        "adaptive_stoch_max_lookback": 20,
        "adaptive_stoch_smooth_k_period": 3,
        "adaptive_stoch_d_period": 3,
        "orderbook_limit": 25,
        "signal_score_threshold": Decimal("1.5"),
        "stop_loss_multiple": Decimal("1.8"),
        "take_profit_multiple": Decimal("0.7"),
        "use_atr_volume_tp_sl": False,
        "tp_atr_multiplier_dynamic": Decimal("1.5"),
        "sl_atr_multiplier_dynamic": Decimal("1.2"),
        "volume_tp_threshold_multiplier": Decimal("2.0"),
        "volume_sl_threshold_multiplier": Decimal("2.0"),
        "tp_atr_boost_on_high_volume": Decimal("0.0"),
        "sl_atr_widening_on_high_volume": Decimal("0.0"),
        "volume_confirmation_multiplier": Decimal("1.5"),
        "scalping_signal_threshold": Decimal("2.5"),
        "fibonacci_window": DIP["fib_window"],
        "enable_trading": False,
        "use_sandbox": True,
        "risk_per_trade": Decimal("0.01"),
        "leverage": 20,
        "max_concurrent_positions": 1,
        "quote_currency": "USDT",
        "entry_order_type": "market",
        "limit_order_offset_buy": Decimal("0.0005"),
        "limit_order_offset_sell": Decimal("0.0005"),
        "trailing_stop_profit_threshold_percentage": Decimal("0.001"),
        "trailing_stop_percentage": Decimal("0.005"),
        "position_confirm_delay_seconds": PCDS,
        "time_based_exit_minutes": None,
        "active_weight_set": "default",
        "indicator_thresholds": {  # New section for configurable indicator thresholds
            "momentum_positive_threshold": Decimal("0.001"),
            "momentum_strong_positive_threshold": Decimal("0.005"),
            "rsi_oversold_threshold": 30,
            "rsi_overbought_threshold": 70,
            "rsi_approaching_oversold_threshold": 40,
            "rsi_approaching_overbought_threshold": 60,
            "cci_extreme_oversold_threshold": -150,
            "cci_extreme_overbought_threshold": 150,
            "cci_oversold_threshold": -80,
            "cci_overbought_threshold": 80,
            "willr_oversold_threshold": -80,
            "willr_overbought_threshold": -20,
            "mfi_oversold_threshold": 20,
            "mfi_overbought_threshold": 80,
            "sma10_score": Decimal("0.6"),
            "vwap_score": Decimal("0.7"),
            "bollinger_bands_extreme_score": Decimal("1.0"),
            "bollinger_bands_mid_score_multiplier": Decimal("0.7"),
            "fisher_buy_threshold": Decimal("0.0"),
            "fisher_sell_threshold": Decimal("0.0"),
            "fisher_extreme_buy_threshold": Decimal("-2.0"),
            "fisher_extreme_sell_threshold": Decimal("2.0"),
            "rsi_extreme_buy_threshold": Decimal("20.0"),
            "rsi_extreme_sell_threshold": Decimal("80.0"),
            "mfi_extreme_buy_threshold": Decimal("10.0"),
            "mfi_extreme_sell_threshold": Decimal("90.0"),
            "adaptive_stoch_oversold_threshold": Decimal("20"),
            "adaptive_stoch_overbought_threshold": Decimal("80"),
            "adaptive_stoch_crossover_strength": Decimal("5"),
            "adaptive_stoch_extreme_buy_threshold": Decimal("10.0"),
            "adaptive_stoch_extreme_sell_threshold": Decimal("90.0"),
        },
        "weight_sets": {
            "scalping": {
                "ema_alignment": Decimal("0.2"),
                "momentum": Decimal("0.3"),
                "volume_confirmation": Decimal("0.2"),
                "rsi": Decimal("0.2"),
                "bollinger_bands": Decimal("0.3"),
                "vwap": Decimal("0.4"),
                "cci": Decimal("0.3"),
                "wr": Decimal("0.3"),
                "psar": Decimal("0.2"),
                "sma_10": Decimal("0.1"),
                "mfi": Decimal("0.2"),
                "orderbook": Decimal("0.15"),
                "fisher": Decimal("0.15"),
                "adaptive_stoch": Decimal("0.4"),
            },
            "default": {
                "ema_alignment": Decimal("0.3"),
                "momentum": Decimal("0.2"),
                "volume_confirmation": Decimal("0.1"),
                "rsi": Decimal("0.3"),
                "bollinger_bands": Decimal("0.2"),
                "vwap": Decimal("0.3"),
                "cci": Decimal("0.2"),
                "wr": Decimal("0.2"),
                "psar": Decimal("0.3"),
                "sma_10": Decimal("0.1"),
                "mfi": Decimal("0.2"),
                "orderbook": Decimal("0.1"),
                "fisher": Decimal("0.15"),
                "adaptive_stoch": Decimal("0.4"),
            },
        },
        "indicators": {  # Enable/disable individual indicators
            "atr": True,
            "ema_alignment": True,
            "momentum": True,
            "volume_confirmation": True,
            "rsi": True,
            "bollinger_bands": True,
            "vwap": True,
            "cci": True,
            "wr": True,
            "psar": True,
            "sma_10": True,
            "mfi": True,
            "orderbook": True,
            "fisher": {"enabled": True, "period": 12},
            "adaptive_stoch": True,
        },
        "exit_strategies": {
            "opposing_signal_enabled": True,
            "opposing_signal_threshold": Decimal("0.5"),
            "extreme_oscillator_enabled": True,
            "min_profit_percentage_for_advanced_exits": Decimal("0.25"),
        },
    }
    logger = logging.getLogger("config_loader")
    user_config = default_config.copy()

    if not file_path.exists():
        try:
            serialized_config = json.loads(json.dumps(default_config, default=str))
            file_path.write_text(
                json.dumps(serialized_config, indent=4), encoding="utf-8",
            )
            logger.info(
                f"{NY}Created default config file: {file_path}. A new scroll of destiny has been penned!{RST}",
            )
            return default_config
        except OSError as e:
            logger.error(
                f"{NR}Error creating default config file {file_path}: {e}. The quill broke!{RST}",
            )
            return default_config

    try:
        config_from_file = json.loads(file_path.read_text(encoding="utf-8"))
        user_config = _cdr(config_from_file, default_config)
        user_config = _eck(user_config, default_config)

        save_needed = False

        if user_config.get("interval") not in VI:
            logger.warning(
                f"{NR}Invalid interval '{user_config.get('interval')}' found in config. Using default '{default_config['interval']}'. The temporal flow is disrupted!{RST}",
            )
            user_config["interval"] = default_config["interval"]
            save_needed = True
        if user_config.get("entry_order_type") not in ["market", "limit"]:
            logger.warning(
                f"{NR}Invalid entry_order_type '{user_config.get('entry_order_type')}' in config. Using default 'market'. The entry spell is unclear!{RST}",
            )
            user_config["entry_order_type"] = "market"
            save_needed = True

        # Validate numeric parameters using _vncv
        numeric_params_to_validate = {
            "retry_delay": {"min": 0, "is_int": True},
            "risk_per_trade": {"min": Decimal("0"), "max": Decimal("1")},
            "leverage": {"min": 1, "is_int": True},
            "max_concurrent_positions": {"min": 1, "is_int": True},
            "signal_score_threshold": {"min": Decimal("0")},
            "stop_loss_multiple": {"min": Decimal("0")},
            "take_profit_multiple": {"min": Decimal("0")},
            "trailing_stop_profit_threshold_percentage": {
                "min": Decimal("0"),
                "max": Decimal("1"),
            },
            "trailing_stop_percentage": {"min": Decimal("1e-9"), "max": Decimal("1")},
            "position_confirm_delay_seconds": {"min": 0, "is_int": True},
            "time_based_exit_minutes": {"min": 1, "is_int": True, "allow_none": True},
            "limit_order_offset_buy": {"min": Decimal("0")},
            "limit_order_offset_sell": {"min": Decimal("0")},
            "orderbook_limit": {"min": 1, "is_int": True},
            "tp_atr_multiplier_dynamic": {"min": Decimal("0")},
            "sl_atr_multiplier_dynamic": {"min": Decimal("0")},
            "volume_tp_threshold_multiplier": {"min": Decimal("0")},
            "volume_sl_threshold_multiplier": {"min": Decimal("0")},
            "tp_atr_boost_on_high_volume": {"min": Decimal("0")},
            "sl_atr_widening_on_high_volume": {"min": Decimal("0")},
            "periodic_pnl_sms_interval_minutes": {"min": 1, "is_int": True},
            # fisher_period is validated by the specific block added previously for user_config["indicators"]["fisher"]["period"]
            # No need to add "fisher_period" here as it's not a top-level key in user_config for this validation loop.
            "adaptive_stoch_atr_period": {"min": 1, "is_int": True},
            # Min value changed from 5 to 1 for flexibility
            "adaptive_stoch_atr_smoothing_period": {"min": 1, "is_int": True},
            "adaptive_stoch_min_lookback": {"min": 1, "is_int": True},
            # Consider max_lookback >= min_lookback validation elsewhere if needed
            "adaptive_stoch_max_lookback": {"min": 2, "is_int": True},
            "adaptive_stoch_smooth_k_period": {"min": 1, "is_int": True},
            "adaptive_stoch_d_period": {"min": 1, "is_int": True},
        }

        # Validation for min_lookback <= max_lookback for adaptive_stoch
        min_lb = user_config.get(
            "adaptive_stoch_min_lookback", default_config["adaptive_stoch_min_lookback"],
        )
        max_lb = user_config.get(
            "adaptive_stoch_max_lookback", default_config["adaptive_stoch_max_lookback"],
        )
        if min_lb > max_lb:
            logger.warning(
                f"{NY}adaptive_stoch_min_lookback ({min_lb}) cannot be greater than adaptive_stoch_max_lookback ({max_lb}). Setting max_lookback to min_lookback ({min_lb}).{RST}",
            )
            user_config["adaptive_stoch_max_lookback"] = min_lb
            # No save_needed = True here as _vncv for max_lookback will handle it if it was also out of its own direct range.
            # This specific cross-validation is a soft correction.

        for param_key, validation_rules in numeric_params_to_validate.items():
            if _vncv(
                user_config,
                param_key,
                default_config[param_key],
                min_value=validation_rules.get("min"),
                max_value=validation_rules.get("max"),
                is_integer=validation_rules.get("is_int", False),
                allow_none=validation_rules.get("allow_none", False),
                logger=logger,
            ):
                save_needed = True

        symbols = user_config.get("symbols_to_trade")
        if (
            not isinstance(symbols, list)
            or not symbols
            or not all(isinstance(s, str) for s in symbols)
        ):
            logger.warning(
                f"{NR}Invalid 'symbols_to_trade' format in config. Must be a non-empty list of strings. The market scroll is unreadable!{RST}",
            )
            user_config["symbols_to_trade"] = default_config["symbols_to_trade"]
            logger.warning(
                f"{NY}Using default value for 'symbols_to_trade': {user_config['symbols_to_trade']}{RST}",
            )
            save_needed = True

        active_set_name = user_config.get("active_weight_set")
        if active_set_name not in user_config.get("weight_sets", {}):
            logger.warning(
                f"{NR}Active weight set '{active_set_name}' not found in 'weight_sets'. Using default 'default'. The balance of indicators is skewed!{RST}",
            )
            user_config["active_weight_set"] = "default"
            save_needed = True

        # Validate indicator parameters that are stored as DIP but used in config
        for param_key, default_val in DIP.items():
            # Special handling for psar_af and psar_max_af as they are floats and have specific ranges
            if param_key in ["psar_af", "psar_max_af"]:
                # For PSAR, the min_value should be 0, not 1, as they are acceleration factors
                # The max_value is typically 0.2 for psar_max_af
                min_val_for_psar = Decimal("0.0")
                # psar_af can go up to 1.0 in theory, but usually small
                max_val_for_psar_af = Decimal("1.0")
                # psar_max_af can also go up to 1.0, but typically 0.2
                max_val_for_psar_max_af = Decimal("1.0")

                if param_key == "psar_af":
                    if _vncv(
                        user_config,
                        param_key,
                        default_val,
                        min_value=min_val_for_psar,
                        max_value=max_val_for_psar_af,
                        is_integer=False,
                        logger=logger,
                    ):
                        save_needed = True
                elif param_key == "psar_max_af":
                    if _vncv(
                        user_config,
                        param_key,
                        default_val,
                        min_value=min_val_for_psar,
                        max_value=max_val_for_psar_max_af,
                        is_integer=False,
                        logger=logger,
                    ):
                        save_needed = True
            elif _vncv(
                user_config,
                param_key,
                default_val,
                min_value=1,
                is_integer=isinstance(default_val, int),
                logger=logger,
            ):
                save_needed = True

        # Validate weights within active_weight_set
        current_active_weights = user_config.get("weight_sets", {}).get(
            user_config.get("active_weight_set", "default"), {},
        )
        for indicator_key, weight_value in current_active_weights.items():
            if _vncv(
                current_active_weights,
                indicator_key,
                Decimal("0.0"),
                min_value=Decimal("0.0"),
                logger=logger,
            ):
                save_needed = True
                user_config["weight_sets"][user_config["active_weight_set"]][
                    indicator_key
                ] = weight_value

        # Validate indicator_thresholds
        indicator_thresholds = user_config.get("indicator_thresholds", {})
        default_thresholds = default_config.get("indicator_thresholds", {})
        for threshold_key, default_val in default_thresholds.items():
            is_int = isinstance(default_val, int)
            if _vncv(
                indicator_thresholds,
                threshold_key,
                default_val,
                min_value=None,
                max_value=None,
                is_integer=is_int,
                logger=logger,
            ):
                save_needed = True
                user_config["indicator_thresholds"][threshold_key] = (
                    indicator_thresholds[threshold_key]
                )

        # Validate Fisher specific period
        fisher_indicator_config = user_config.get("indicators", {}).get("fisher", {})
        if isinstance(fisher_indicator_config, dict):  # Ensure fisher config is a dict
            if _vncv(
                fisher_indicator_config,
                "period",
                default_config.get("indicators", {})
                .get("fisher", {})
                .get("period", 12),
                min_value=2,
                is_integer=True,
                logger=logger,
            ):
                save_needed = True
                # Ensure the corrected value is propagated back to user_config
                # Should not happen if _eck works
                if "fisher" not in user_config.get("indicators", {}):
                    user_config.setdefault("indicators", {})["fisher"] = {}
                user_config["indicators"]["fisher"]["period"] = fisher_indicator_config[
                    "period"
                ]
        # If fisher exists but is not a dict (e.g. old format True/False)
        elif "fisher" in user_config.get("indicators", {}):
            logger.warning(
                f"{NY}Invalid 'fisher' configuration in 'indicators'. Expected a dictionary. Reverting to default.{RST}",
            )
            user_config["indicators"]["fisher"] = default_config.get(
                "indicators", {},
            ).get("fisher", {"enabled": True, "period": 12})
            save_needed = True

        # Validate exit_strategies
        exit_strategies_config = user_config.get("exit_strategies", {})
        default_exit_strategies = default_config.get("exit_strategies", {})

        if not isinstance(exit_strategies_config.get("opposing_signal_enabled"), bool):
            logger.warning(
                f"{NY}Invalid type for 'opposing_signal_enabled' in 'exit_strategies'. Setting to default.{RST}",
            )
            exit_strategies_config["opposing_signal_enabled"] = (
                default_exit_strategies.get("opposing_signal_enabled", True)
            )
            save_needed = True

        if not isinstance(
            exit_strategies_config.get("extreme_oscillator_enabled"), bool,
        ):
            logger.warning(
                f"{NY}Invalid type for 'extreme_oscillator_enabled' in 'exit_strategies'. Setting to default.{RST}",
            )
            exit_strategies_config["extreme_oscillator_enabled"] = (
                default_exit_strategies.get("extreme_oscillator_enabled", True)
            )
            save_needed = True

        if _vncv(
            exit_strategies_config,
            "opposing_signal_threshold",
            default_exit_strategies.get("opposing_signal_threshold", Decimal("0.5")),
            min_value=Decimal("0.1"),
            max_value=Decimal("1.0"),
            logger=logger,
        ):
            save_needed = True

        if _vncv(
            exit_strategies_config,
            "min_profit_percentage_for_advanced_exits",
            default_exit_strategies.get(
                "min_profit_percentage_for_advanced_exits", Decimal("0.25"),
            ),
            min_value=Decimal("0.0"),
            logger=logger,
        ):
            save_needed = True

        # Ensure the sub-dictionary is updated in user_config
        user_config["exit_strategies"] = exit_strategies_config

        if save_needed:
            try:
                serialized_config = json.loads(json.dumps(user_config, default=str))
                file_path.write_text(
                    json.dumps(serialized_config, indent=4), encoding="utf-8",
                )
                logger.info(
                    f"{NY}Corrected invalid values and saved updated config file: {file_path}. The runes are now perfectly aligned!{RST}",
                )
            except OSError as e:
                logger.error(
                    f"{NR}Error writing corrected config file {file_path}: {e}. The quill broke!{RST}",
                )
        return user_config
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(
            f"{NR}Error loading config file {file_path}: {e}. Using default config. The ancient text is corrupted!{RST}",
        )
        try:
            serialized_config = json.loads(json.dumps(default_config, default=str))
            file_path.write_text(
                json.dumps(serialized_config, indent=4), encoding="utf-8",
            )
            logger.info(
                f"{NY}Created default config file: {file_path}. A new scroll, untainted, has been forged!{RST}",
            )
        except OSError as e_create:
            logger.error(
                f"{NR}Error creating default config file after load error: {e_create}. The forge is cold!{RST}",
            )
        return default_config


_icfs = lc(CFP)
QC: Final[str] = _icfs.get("quote_currency", "USDT")


def slg(name_suffix: str) -> logging.Logger:
    """Setup Logger: Configures and returns a logger with file and stream handlers.
    File handler rotates logs, stream handler prints to console with custom formatter.
    """
    base_name = "xrscalper_bot"
    logger_name = f"{base_name}_{name_suffix}"
    logger = logging.getLogger(logger_name)

    if logger.hasHandlers():
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()

    logger.setLevel(logging.DEBUG)

    try:
        file_handler = RotatingFileHandler(
            LD / f"{logger_name}.log", maxBytes=LDS, backupCount=5, encoding="utf-8",
        )
        file_formatter = SF(
            "%(asctime)s - %(levelname)s - [%(name)s:%(lineno)d] - %(message)s",
        )
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)
    except Exception as e:
        print(
            f"{NR}Error setting up file logger for {LD / f'{logger_name}.log'}: {e}. The log scroll is sealed!{RST}",
        )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_formatter = SF(
        "%(asctime)s - %(levelname)-8s - [%(name)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S %Z",
    )
    stream_formatter.converter = lambda *args: datetime.now(TZ).timetuple()
    stream_handler.setFormatter(stream_formatter)
    stream_handler.setLevel(logging.INFO)  # Default console to INFO
    logger.addHandler(stream_handler)

    logger.propagate = False
    return logger


def retry_api_call(
    max_retries: int = MAR,
    retry_delay: int = RDS,
    catch_exceptions: tuple = (
        ccxt.NetworkError,
        ccxt.RequestTimeout,
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        ccxt.RateLimitExceeded,
    ),
):  # Removed ccxt.ExchangeError from default
    """Decorator for retrying API calls."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = kwargs.get("logger", logging.getLogger(func.__module__))
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except ccxt.RateLimitExceeded as e:
                    delay = retry_delay * (2**attempt)  # Exponential backoff
                    logger.warning(
                        f"{NY}Rate limit exceeded in {func.__name__}: {e}. Retrying in {delay}s (Attempt {attempt + 1}/{max_retries + 1}). The gatekeeper demands patience.{RST}",
                    )
                    time.sleep(delay)
                except ccxt.AuthenticationError as e:
                    logger.error(
                        f"{NR}Authentication error in {func.__name__}: {e}. Aborting retries. The keys do not fit the lock!{RST}",
                    )
                    raise  # Re-raise authentication errors immediately
                except catch_exceptions as e:
                    if attempt < max_retries:
                        logger.warning(
                            f"{NY}Transient error in {func.__name__}: {e}. Retrying in {retry_delay}s (Attempt {attempt + 1}/{max_retries + 1}). A minor tremor in the realm.{RST}",
                        )
                        time.sleep(retry_delay)
                    else:
                        logger.error(
                            f"{NR}Max retries reached for {func.__name__}: {e}. Aborting. The spell failed repeatedly!{RST}",
                        )
                        raise
                except Exception as e:
                    logger.error(
                        f"{NR}Unexpected error in {func.__name__}: {e}. Aborting. A cosmic interference!{RST}",
                        exc_info=True,
                    )
                    raise
            return None  # Should not be reached if exceptions are re-raised

        return wrapper

    return decorator


@retry_api_call()
def ie(config: dict[str, Any], logger: logging.Logger) -> ccxt.Exchange | None:
    """Initialize Exchange: Connects to the cryptocurrency exchange using CCXT.
    Handles sandbox mode, market loading, and initial balance fetch to confirm connection.
    """
    exchange_options = {
        "apiKey": AK,
        "secret": AS,
        "enableRateLimit": True,
        "options": {
            "defaultType": "linear",
            "adjustForTimeDifference": True,
            "fetchTickerTimeout": 10000,
            "fetchBalanceTimeout": 15000,
            "createOrderTimeout": 20000,
            "cancelOrderTimeout": 15000,
            "fetchPositionsTimeout": 15000,
            "fetchOHLCVTimeout": 15000,
        },
    }
    exchange_id = config.get("exchange_id", "bybit").lower()

    if not hasattr(ccxt, exchange_id):
        logger.error(
            f"{NR}Exchange ID '{exchange_id}' not found in CCXT library. Please check config.json. The chosen realm does not exist!{RST}",
        )
        return None
    exchange_class = getattr(ccxt, exchange_id)
    exchange = exchange_class(exchange_options)

    if config.get("use_sandbox"):
        logger.warning(
            f"{NY}USING SANDBOX MODE (Testnet) for {exchange.id}. Tread lightly, for this is a training ground!{RST}",
        )
        if hasattr(exchange, "set_sandbox_mode"):
            exchange.set_sandbox_mode(True)
        else:
            logger.warning(
                f"{NY}{exchange.id} does not support set_sandbox_mode via ccxt. Ensure API keys are configured for Testnet manually.{RST}",
            )
            # For Bybit, manually set the testnet URL if set_sandbox_mode is not available or doesn't work as expected
            if exchange.id == "bybit" and "testnet" not in exchange.urls["api"]:
                exchange.urls["api"] = "https://api-testnet.bybit.com"
                logger.warning(
                    f"{NY}Manually set Bybit Testnet API URL: {exchange.urls['api']}. A hidden path revealed!{RST}",
                )

    logger.info(
        f"{NB}Loading markets for {exchange.id}... Unveiling the available trade scrolls.{RST}",
    )
    exchange.load_markets()
    logger.info(
        f"{NB}CCXT exchange initialized ({exchange.id}). Sandbox: {config.get('use_sandbox')}. The connection is forged!{RST}",
    )

    account_type = "CONTRACT"
    logger.info(
        f"{NB}Attempting initial balance fetch (Account Type: {account_type}) for {QC}... Probing the essence of your holdings.{RST}",
    )
    try:
        params = {"type": account_type} if exchange.id == "bybit" else {}
        balance = exchange.fetch_balance(params=params)
        available_quote = balance.get(QC, {}).get("free", "N/A")
        logger.info(
            f"{NG}Successfully connected and fetched initial balance. The coffers reveal their bounty!{RST} (Example: {QC} available: {available_quote})",
        )
    except ccxt.ExchangeError as be:
        logger.warning(
            f"{NY}Exchange error during initial balance fetch ({account_type}): {be}. Trying default fetch... A minor tremor in the realm.{RST}",
        )
        balance = exchange.fetch_balance()
        available_quote = balance.get(QC, {}).get("free", "N/A")
        logger.info(
            f"{NG}Successfully fetched balance using default parameters. The path is clearer now!{RST} (Example: {QC} available: {available_quote})",
        )
    return exchange


@retry_api_call()
def fcp(exchange: ccxt.Exchange, symbol: str, logger: logging.Logger) -> Decimal | None:
    """Fetch Current Price: Retrieves the current price for a given symbol,
    with retries and robust fallback logic for different price types (last, bid/ask midpoint).
    """
    logger.debug(f"Fetching ticker for {symbol}. Probing the market's pulse.")
    ticker = exchange.fetch_ticker(symbol)
    logger.debug(
        f"Raw ticker data for {symbol}: {ticker}. The market's heartbeat revealed.",
    )

    price: Decimal | None = None
    last_price = (
        Decimal(str(ticker.get("last"))) if ticker.get("last") is not None else None
    )
    bid_price = (
        Decimal(str(ticker.get("bid"))) if ticker.get("bid") is not None else None
    )
    ask_price = (
        Decimal(str(ticker.get("ask"))) if ticker.get("ask") is not None else None
    )

    if last_price is not None and last_price > 0:
        price = last_price
        logger.debug(f"Using 'last' price: {price}. A clear echo from the market.")
    elif (
        bid_price is not None
        and ask_price is not None
        and bid_price > 0
        and ask_price > 0
        and ask_price >= bid_price
    ):
        price = (bid_price + ask_price) / 2
        logger.debug(f"Using bid/ask midpoint: {price}. The equilibrium revealed.")
    elif ask_price is not None and ask_price > 0:
        price = ask_price
        logger.warning(
            f"{NY}Using 'ask' price fallback: {price}. Accepting the seller's decree.{RST}",
        )
    elif bid_price is not None and bid_price > 0:
        price = bid_price
        logger.warning(
            f"{NY}Using 'bid' price fallback: {price}. Yielding to the buyer's plea.{RST}",
        )

    if price is not None and price > 0:
        return price
    raise ccxt.ExchangeError(
        f"Failed to get a valid price from ticker data. Ticker: {ticker}. The scrying mirror is clouded.",
    )


@retry_api_call()
def fkc(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str,
    limit: int = 250,
    logger: logging.Logger = None,
) -> pd.DataFrame:
    """Fetch Klines/Candles: Retrieves OHLCV data for a given symbol and timeframe.
    Handles retries, rate limits, and robust data processing.
    """
    logger = logger or logging.getLogger(__name__)
    if not exchange.has["fetchOHLCV"]:
        logger.error(
            f"{NR}Exchange {exchange.id} does not support fetchOHLCV. This realm holds no historical records!{RST}",
        )
        return pd.DataFrame()

    logger.debug(
        f"Fetching klines for {symbol}, {timeframe}, limit={limit}. Unfurling the scrolls of time.",
    )
    ohlcv_data = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    if not ohlcv_data or not isinstance(ohlcv_data, list) or not ohlcv_data:
        raise ccxt.ExchangeError(
            f"fetch_ohlcv returned empty or invalid data for {symbol}.",
        )

    data_frame = pd.DataFrame(
        ohlcv_data, columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    data_frame["timestamp"] = pd.to_datetime(
        data_frame["timestamp"], unit="ms", errors="coerce", utc=True,
    )
    data_frame.dropna(subset=["timestamp"], inplace=True)
    data_frame.set_index("timestamp", inplace=True)

    for col in ["open", "high", "low", "close", "volume"]:
        data_frame[col] = pd.to_numeric(data_frame[col], errors="coerce")

    initial_length = len(data_frame)
    data_frame.dropna(subset=["open", "high", "low", "close"], inplace=True)
    data_frame = data_frame[data_frame["close"] > 0]
    rows_dropped = initial_length - len(data_frame)
    if rows_dropped > 0:
        logger.debug(
            f"Dropped {rows_dropped} rows with NaN/invalid price data for {symbol}. Cleansing the dataset.",
        )

    if data_frame.empty:
        raise ccxt.ExchangeError(
            f"Kline data for {symbol} {timeframe} empty after cleaning. The cleansed tapestry is bare.",
        )

    data_frame.sort_index(inplace=True)
    logger.info(
        f"{NB}Successfully fetched and processed {len(data_frame)} klines for {symbol} {timeframe}. The market's history is now revealed!{RST}",
    )
    return data_frame


@retry_api_call()
def fobc(
    exchange: ccxt.Exchange, symbol: str, limit: int, logger: logging.Logger,
) -> dict | None:
    """Fetch Order Book: Retrieves the order book for a given symbol.
    Handles retries and validates the structure of the returned data.
    """
    if not exchange.has["fetchOrderBook"]:
        logger.error(
            f"{NR}Exchange {exchange.id} does not support fetchOrderBook. This realm offers no glimpse into its immediate desires!{RST}",
        )
        return None

    logger.debug(
        f"Fetching order book for {symbol}, limit={limit}. Listening to the market's whispers.",
    )
    order_book = exchange.fetch_order_book(symbol, limit=limit)

    if not order_book:
        raise ccxt.ExchangeError(
            f"fetch_order_book returned None/empty for {symbol}. The market's whispers are silent.",
        )
    if not isinstance(order_book, dict):
        raise ccxt.ExchangeError(
            f"Invalid orderbook type received for {symbol}. Expected dict, got {type(order_book).__name__}. The message is garbled.",
        )
    if "bids" not in order_book or "asks" not in order_book:
        raise ccxt.ExchangeError(
            f"Invalid orderbook structure for {symbol}: missing 'bids' or 'asks'. Response keys: {list(order_book.keys())}. The market's intentions are unclear.",
        )
    if not isinstance(order_book["bids"], list) or not isinstance(
        order_book["asks"], list,
    ):
        raise ccxt.ExchangeError(
            f"Invalid orderbook structure for {symbol}: 'bids' or 'asks' are not lists. bids type: {type(order_book['bids']).__name__}, asks type: {type(order_book['asks']).__name__}. The structure of desires is broken.",
        )

    logger.debug(
        f"Successfully fetched orderbook for {symbol} with {len(order_book['bids'])} bids, {len(order_book['asks'])} asks. The market's intentions are revealed!{RST}",
    )
    return order_book


class TA:
    """Technical Analysis: Manages indicator calculations and signal generation
    for a given symbol's DataFrame.
    """

    def __init__(
        self,
        data_frame: pd.DataFrame,
        logger: logging.Logger,
        config: dict[str, Any],
        market_info: dict[str, Any],
    ):
        self.d = data_frame
        self.lg = logger
        self.cfg = config
        self.mi = market_info
        self.s = market_info.get("symbol", "UNKNOWN_SYMBOL")
        self.i = config.get("interval", "5")
        self.ci = CIM.get(self.i)
        if not self.ci:
            self.lg.error(
                f"{NR}Invalid interval '{self.i}' in config for {self.s}, cannot map to CCXT timeframe. Indicator calculations may be affected. The temporal alignment is off!{RST}",
            )
        # Store all indicator values as Decimal
        self.iv: dict[str, Decimal] = {}
        self.sig: dict[str, int] = {"BUY": 0, "SELL": 0, "HOLD": 1}
        self.aw_name = config.get("active_weight_set", "default")
        self.ws = config.get("weight_sets", {}).get(self.aw_name, {})
        self.fld: dict[str, Decimal] = {}
        self.tcn: dict[str, str | None] = {}
        self.indicator_thresholds = self.cfg.get("indicator_thresholds", {})
        self.dynamic_stoch_k: int | None = None

        if not self.ws:
            self.lg.error(
                f"{NR}Active weight set '{self.aw_name}' not found or empty in config for {self.s}. Signal generation will be impacted. The weighting scales are unbalanced!{RST}",
            )

        self._cai()
        self._uliv()
        self.cfl()

    def _gtcn(self, base_name: str, processed_df: pd.DataFrame) -> str | None:
        """Get Technical Column Name: Helper to find the actual column name generated by pandas_ta
        for a given indicator base name, considering various naming conventions.
        """
        params_config = {
            "ATR": self.cfg.get("atr_period", DIP["atr_period"]),
            "EMA_Short": self.cfg.get("ema_short_period", DIP["ema_short_period"]),
            "EMA_Long": self.cfg.get("ema_long_period", DIP["ema_long_period"]),
            "Momentum": self.cfg.get("momentum_period", DIP["momentum_period"]),
            "CCI": self.cfg.get("cci_window", DIP["cci_window"]),
            "Williams_R": self.cfg.get("williams_r_window", DIP["williams_r_window"]),
            "MFI": self.cfg.get("mfi_window", DIP["mfi_window"]),
            "SMA10": self.cfg.get("sma_10_window", DIP["sma_10_window"]),
            "RSI": self.cfg.get("rsi_period", DIP["rsi_window"]),
            "BB_Period": self.cfg.get(
                "bollinger_bands_period", DIP["bollinger_bands_period"],
            ),
            "BB_StdDev": float(
                self.cfg.get("bollinger_bands_std_dev", DIP["bollinger_bands_std_dev"]),
            ),
            # Removed StochRSI_Len and StochRSI_RSI_Len
            "PSAR_AF": float(self.cfg.get("psar_af", DIP["psar_af"])),
            "PSAR_MaxAF": float(self.cfg.get("psar_max_af", DIP["psar_max_af"])),
            "Volume_MA_Period": self.cfg.get(
                "volume_ma_period", DIP["volume_ma_period"],
            ),
            "Fisher_Period": self.cfg.get("indicators", {})
            .get("fisher", {})
            .get("period", 12),
            # Adaptive_Stoch_K will use self.dynamic_stoch_k directly in the pattern generation
            "Adaptive_Stoch_Smooth_K": self.cfg.get(
                "adaptive_stoch_smooth_k_period", 3,
            ),
            "Adaptive_Stoch_D": self.cfg.get("adaptive_stoch_d_period", 3),
        }

        psar_af_str = (
            f"{Decimal(str(params_config['PSAR_AF'])).normalize():.2f}".rstrip(
                "0",
            ).rstrip(".")
        )
        psar_max_af_str = (
            f"{Decimal(str(params_config['PSAR_MaxAF'])).normalize():.1f}".rstrip(
                "0",
            ).rstrip(".")
        )

        # Define a list of possible column name patterns for each indicator
        # This makes the mapping more robust to minor pandas_ta naming variations.
        column_name_patterns = {
            "ATR": [f"ATRr_{params_config['ATR']}"],
            "EMA_Short": [f"EMA_{params_config['EMA_Short']}"],
            "EMA_Long": [f"EMA_{params_config['EMA_Long']}"],
            "Momentum": [f"MOM_{params_config['Momentum']}"],
            # CCI can have different constants
            "CCI": [f"CCI_{params_config['CCI']}", f"CCI_{params_config['CCI']}_0.015"],
            "Williams_R": [f"WILLR_{params_config['Williams_R']}"],
            "MFI": [f"MFI_{params_config['MFI']}"],
            "VWAP": ["VWAP_D", "VWAP"],  # VWAP can be daily or general
            "PSAR_long": [f"PSARl_{psar_af_str}_{psar_max_af_str}", "PSARl"],
            "PSAR_short": [f"PSARs_{psar_af_str}_{psar_max_af_str}", "PSARs"],
            "SMA10": [f"SMA_{params_config['SMA10']}"],
            "RSI": [f"RSI_{params_config['RSI']}"],
            "BB_Lower": [
                f"BBL_{params_config['BB_Period']}_{params_config['BB_StdDev']:.1f}".replace(
                    ".0", "",
                ),
                f"BBL_{params_config['BB_Period']}",
            ],
            "BB_Middle": [
                f"BBM_{params_config['BB_Period']}_{params_config['BB_StdDev']:.1f}".replace(
                    ".0", "",
                ),
                f"BBM_{params_config['BB_Period']}",
            ],
            "BB_Upper": [
                f"BBU_{params_config['BB_Period']}_{params_config['BB_StdDev']:.1f}".replace(
                    ".0", "",
                ),
                f"BBU_{params_config['BB_Period']}",
            ],
            # Custom name for volume SMA
            "Volume_MA": [f"VOL_SMA_{params_config['Volume_MA_Period']}"],
            "FISHERT": [f"FISHERT_{params_config['Fisher_Period']}"],
            # Adaptive_STOCHk and Adaptive_STOCHd patterns are handled dynamically below
        }

        if base_name == "Adaptive_STOCHk":
            k_val = (
                self.dynamic_stoch_k
                if self.dynamic_stoch_k is not None
                else self.cfg.get("adaptive_stoch_min_lookback", 5)
            )
            d_val = params_config["Adaptive_Stoch_D"]
            smooth_k_val = params_config["Adaptive_Stoch_Smooth_K"]
            column_name_patterns["Adaptive_STOCHk"] = [
                f"STOCHk_{k_val}_{d_val}_{smooth_k_val}",
            ]
        elif base_name == "Adaptive_STOCHd":
            k_val = (
                self.dynamic_stoch_k
                if self.dynamic_stoch_k is not None
                else self.cfg.get("adaptive_stoch_min_lookback", 5)
            )
            d_val = params_config["Adaptive_Stoch_D"]
            smooth_k_val = params_config["Adaptive_Stoch_Smooth_K"]
            column_name_patterns["Adaptive_STOCHd"] = [
                f"STOCHd_{k_val}_{d_val}_{smooth_k_val}",
            ]

        possible_patterns = column_name_patterns.get(base_name, [])

        for col in processed_df.columns:
            for pattern in possible_patterns:
                if col.startswith(pattern):
                    self.lg.debug(
                        f"Mapped '{base_name}' to column '{col}'. The rune's variant is found!",
                    )
                    return col

        self.lg.warning(
            f"{NY}Could not find column name for indicator '{base_name}' in DataFrame columns: {processed_df.columns.tolist()}. The rune's form is elusive!{RST}",
        )
        return None

    def _cai(self):
        """Calculate All Indicators: Computes various technical indicators using pandas_ta
        and stores the generated column names.
        """
        if self.d.empty:
            self.lg.warning(
                f"{NY}DataFrame is empty, cannot calculate indicators for {self.s}. The canvas is blank!{RST}",
            )
            return

        required_periods = []
        indicators_config = self.cfg.get("indicators", {})
        params_config = {
            "ATR": self.cfg.get("atr_period", DIP["atr_period"]),
            "EMA_Short": self.cfg.get("ema_short_period", DIP["ema_short_period"]),
            "EMA_Long": self.cfg.get("ema_long_period", DIP["ema_long_period"]),
            "Momentum": self.cfg.get("momentum_period", DIP["momentum_period"]),
            "CCI": self.cfg.get("cci_window", DIP["cci_window"]),
            "Williams_R": self.cfg.get("williams_r_window", DIP["williams_r_window"]),
            "MFI": self.cfg.get("mfi_window", DIP["mfi_window"]),
            "SMA10": self.cfg.get("sma_10_window", DIP["sma_10_window"]),
            "RSI": self.cfg.get("rsi_period", DIP["rsi_window"]),
            "BB_Period": self.cfg.get(
                "bollinger_bands_period", DIP["bollinger_bands_period"],
            ),
            "BB_StdDev": float(
                self.cfg.get("bollinger_bands_std_dev", DIP["bollinger_bands_std_dev"]),
            ),
            "PSAR_AF": float(self.cfg.get("psar_af", DIP["psar_af"])),
            "PSAR_MaxAF": float(self.cfg.get("psar_max_af", DIP["psar_max_af"])),
            "Volume_MA_Period": self.cfg.get(
                "volume_ma_period", DIP["volume_ma_period"],
            ),
            # Corrected Fisher_Period access
            "Fisher_Period": self.cfg.get("indicators", {})
            .get("fisher", {})
            .get("period", 12),
            "Adaptive_Stoch_ATR_Period": self.cfg.get("adaptive_stoch_atr_period", 14),
            "Adaptive_Stoch_ATR_Smoothing_Period": self.cfg.get(
                "adaptive_stoch_atr_smoothing_period", 50,
            ),
            "Adaptive_Stoch_Min_Lookback": self.cfg.get(
                "adaptive_stoch_min_lookback", 5,
            ),
            "Adaptive_Stoch_Max_Lookback": self.cfg.get(
                "adaptive_stoch_max_lookback", 20,
            ),
            "Adaptive_Stoch_Smooth_K_Period": self.cfg.get(
                "adaptive_stoch_smooth_k_period", 3,
            ),
            "Adaptive_Stoch_D_Period": self.cfg.get("adaptive_stoch_d_period", 3),
        }

        if indicators_config.get("atr", False):
            required_periods.append(params_config["ATR"])
        if indicators_config.get("ema_alignment", False):
            required_periods.extend(
                [params_config["EMA_Short"], params_config["EMA_Long"]],
            )
        if indicators_config.get("momentum", False):
            required_periods.append(params_config["Momentum"])
        if indicators_config.get("cci", False):
            required_periods.append(params_config["CCI"])
        if indicators_config.get("wr", False):
            required_periods.append(params_config["Williams_R"])
        if indicators_config.get("mfi", False):
            required_periods.append(params_config["MFI"])
        if indicators_config.get("sma_10", False):
            required_periods.append(params_config["SMA10"])
        # Note: Old StochRSI period dependencies removed, Adaptive Stoch will use its own.
        if indicators_config.get("rsi", False):
            required_periods.append(params_config["RSI"])
        if indicators_config.get("bollinger_bands", False):
            required_periods.append(params_config["BB_Period"])
        if indicators_config.get("volume_confirmation", False):
            required_periods.append(params_config["Volume_MA_Period"])
        required_periods.append(self.cfg.get("fibonacci_window", DIP["fib_window"]))

        min_recommended_data = max(required_periods) + 20 if required_periods else 50
        min_recommended_data = max(min_recommended_data, 2)

        if len(self.d) < min_recommended_data:
            self.lg.warning(
                f"{NY}Insufficient data ({len(self.d)} points) for {self.s} to calculate all indicators reliably (min recommended: {min_recommended_data}). Results may contain NaNs. The data tapestry is too short!{RST}",
            )

        try:
            data_copy = self.d.copy()

            atr_period = params_config["ATR"]
            atr_results = data_copy.ta.atr(length=atr_period, append=False)
            if atr_results is not None and not atr_results.empty:
                data_copy = pd.concat([data_copy, atr_results], axis=1)
            self.tcn["ATR"] = self._gtcn("ATR", data_copy)

            if indicators_config.get("ema_alignment", False):
                ema_short_period = params_config["EMA_Short"]
                ema_long_period = params_config["EMA_Long"]
                ema_short_results = data_copy.ta.ema(
                    length=ema_short_period, append=False,
                )
                if ema_short_results is not None and not ema_short_results.empty:
                    data_copy = pd.concat([data_copy, ema_short_results], axis=1)
                self.tcn["EMA_Short"] = self._gtcn("EMA_Short", data_copy)
                ema_long_results = data_copy.ta.ema(
                    length=ema_long_period, append=False,
                )
                if ema_long_results is not None and not ema_long_results.empty:
                    data_copy = pd.concat([data_copy, ema_long_results], axis=1)
                self.tcn["EMA_Long"] = self._gtcn("EMA_Long", data_copy)

            if indicators_config.get("momentum", False):
                momentum_period = params_config["Momentum"]
                mom_results = data_copy.ta.mom(length=momentum_period, append=False)
                if mom_results is not None and not mom_results.empty:
                    data_copy = pd.concat([data_copy, mom_results], axis=1)
                self.tcn["Momentum"] = self._gtcn("Momentum", data_copy)

            if indicators_config.get("cci", False):
                cci_period = params_config["CCI"]
                cci_results = data_copy.ta.cci(length=cci_period, append=False)
                if cci_results is not None and not cci_results.empty:
                    data_copy = pd.concat([data_copy, cci_results], axis=1)
                self.tcn["CCI"] = self._gtcn("CCI", data_copy)

            if indicators_config.get("wr", False):
                willr_period = params_config["Williams_R"]
                willr_results = data_copy.ta.willr(length=willr_period, append=False)
                if willr_results is not None and not willr_results.empty:
                    data_copy = pd.concat([data_copy, willr_results], axis=1)
                self.tcn["Williams_R"] = self._gtcn("Williams_R", data_copy)

            if indicators_config.get("mfi", False):
                mfi_period = params_config["MFI"]
                try:
                    # Explicit type casting for MFI calculation
                    self.lg.debug(
                        f"MFI Pre-Cast ({self.s}): dtypes: H={data_copy['high'].dtype}, L={data_copy['low'].dtype}, C={data_copy['close'].dtype}, V={data_copy['volume'].dtype}",
                    )
                    data_copy["high"] = data_copy["high"].astype("float64")
                    data_copy["low"] = data_copy["low"].astype("float64")
                    data_copy["close"] = data_copy["close"].astype("float64")
                    data_copy["volume"] = data_copy["volume"].astype("float64")
                    self.lg.debug(
                        f"MFI Post-Cast ({self.s}): dtypes: H={data_copy['high'].dtype}, L={data_copy['low'].dtype}, C={data_copy['close'].dtype}, V={data_copy['volume'].dtype}",
                    )

                    mfi_results = data_copy.ta.mfi(length=mfi_period, append=False)
                    if mfi_results is not None and not mfi_results.empty:
                        data_copy = pd.concat([data_copy, mfi_results], axis=1)
                    self.tcn["MFI"] = self._gtcn("MFI", data_copy)
                except Exception as e:
                    self.lg.error(
                        f"{NR}MFI calculation failed for {self.s}: {e}. Skipping MFI. The money flow is obscured!{RST}",
                        exc_info=True,
                    )

            if indicators_config.get("vwap", False):
                # Ensure types are float64 for VWAP as well, though it might be less sensitive than MFI
                self.lg.debug(
                    f"VWAP Pre-Cast ({self.s}): dtypes: H={data_copy['high'].dtype}, L={data_copy['low'].dtype}, C={data_copy['close'].dtype}, V={data_copy['volume'].dtype}",
                )
                data_copy["high"] = data_copy["high"].astype("float64")
                data_copy["low"] = data_copy["low"].astype("float64")
                data_copy["close"] = data_copy["close"].astype("float64")
                data_copy["volume"] = data_copy["volume"].astype("float64")
                if data_copy.index.tz is not None:
                    data_copy.index = data_copy.index.tz_localize(None)
                vwap_results = data_copy.ta.vwap(append=False)
                if vwap_results is not None and not vwap_results.empty:
                    data_copy = pd.concat([data_copy, vwap_results], axis=1)
                self.tcn["VWAP"] = self._gtcn("VWAP", data_copy)

            if indicators_config.get("psar", False):
                psar_af = params_config["PSAR_AF"]
                psar_max_af = params_config["PSAR_MaxAF"]
                psar_results = data_copy.ta.psar(
                    af=psar_af, max_af=psar_max_af, append=False,
                )
                if psar_results is not None and not psar_results.empty:
                    data_copy = pd.concat([data_copy, psar_results], axis=1)
                self.tcn["PSAR_long"] = self._gtcn("PSAR_long", data_copy)
                self.tcn["PSAR_short"] = self._gtcn("PSAR_short", data_copy)

            if indicators_config.get("sma_10", False):
                sma10_period = params_config["SMA10"]
                sma_results = data_copy.ta.sma(length=sma10_period, append=False)
                if sma_results is not None and not sma_results.empty:
                    data_copy = pd.concat([data_copy, sma_results], axis=1)
                self.tcn["SMA10"] = self._gtcn("SMA10", data_copy)

            # Removed StochRSI calculation block entirely

            # Ensure we check the boolean value if it's not a dict
            if indicators_config.get("adaptive_stoch", False):
                atr_col_name_for_stoch = self.tcn.get("ATR")
                if (
                    not atr_col_name_for_stoch
                    or atr_col_name_for_stoch not in data_copy.columns
                ):
                    self.lg.warning(
                        f"{NY}ATR column not found for Adaptive Stochastic on {self.s}. Calculating ATR with period {params_config['Adaptive_Stoch_ATR_Period']}. Ensure ATR is enabled or this may fail.{RST}",
                    )
                    atr_results_temp = data_copy.ta.atr(
                        length=params_config["Adaptive_Stoch_ATR_Period"], append=False,
                    )
                    if atr_results_temp is not None and not atr_results_temp.empty:
                        data_copy = pd.concat([data_copy, atr_results_temp], axis=1)
                        atr_col_name_for_stoch = self._gtcn("ATR", data_copy)
                    if (
                        not atr_col_name_for_stoch
                        or atr_col_name_for_stoch not in data_copy.columns
                    ):
                        self.lg.error(
                            f"{NR}Failed to obtain ATR for Adaptive Stochastic on {self.s}. Skipping Adaptive Stochastic.{RST}",
                        )
                        self.dynamic_stoch_k = params_config[
                            "Adaptive_Stoch_Min_Lookback"
                        ]

                if (
                    atr_col_name_for_stoch
                    and atr_col_name_for_stoch in data_copy.columns
                ):
                    atr_series = data_copy[atr_col_name_for_stoch].dropna()
                    if not atr_series.empty:
                        smoothing_window = params_config[
                            "Adaptive_Stoch_ATR_Smoothing_Period"
                        ]
                        atr_window = atr_series.tail(smoothing_window)
                        min_atr = atr_window.min()
                        max_atr = atr_window.max()
                        latest_atr = atr_series.iloc[-1]

                        normalized_atr = Decimal("0.5")
                        if (max_atr - min_atr) > Decimal("1e-9"):
                            normalized_atr = (
                                Decimal(str(latest_atr)) - Decimal(str(min_atr))
                            ) / (
                                Decimal(str(max_atr))
                                - Decimal(str(min_atr))
                                + Decimal("1e-10")
                            )

                        normalized_atr = max(
                            Decimal("0.0"), min(Decimal("1.0"), normalized_atr),
                        )

                        min_lb = Decimal(
                            str(params_config["Adaptive_Stoch_Min_Lookback"]),
                        )
                        max_lb = Decimal(
                            str(params_config["Adaptive_Stoch_Max_Lookback"]),
                        )
                        self.dynamic_stoch_k = int(
                            min_lb + (max_lb - min_lb) * normalized_atr,
                        )
                        self.dynamic_stoch_k = max(
                            int(min_lb), min(int(max_lb), self.dynamic_stoch_k),
                        )
                        self.lg.debug(
                            f"Adaptive Stochastic for {self.s}: Latest ATR={latest_atr:.4f}, NormATR={normalized_atr:.4f}, Dynamic K={self.dynamic_stoch_k}",
                        )
                    else:
                        self.lg.warning(
                            f"{NY}ATR series is empty for Adaptive Stochastic on {self.s}. Using min lookback.{RST}",
                        )
                        self.dynamic_stoch_k = params_config[
                            "Adaptive_Stoch_Min_Lookback"
                        ]
                else:
                    self.lg.warning(
                        f"{NY}ATR not available for Adaptive Stochastic on {self.s}. Using min lookback.{RST}",
                    )
                    self.dynamic_stoch_k = params_config["Adaptive_Stoch_Min_Lookback"]

                stoch_k_val = self.dynamic_stoch_k
                stoch_d_val = params_config["Adaptive_Stoch_D_Period"]
                stoch_smooth_k_val = params_config["Adaptive_Stoch_Smooth_K_Period"]

                stoch_results = data_copy.ta.stoch(
                    k=stoch_k_val,
                    d=stoch_d_val,
                    smooth_k=stoch_smooth_k_val,
                    append=False,
                )
                if stoch_results is not None and not stoch_results.empty:
                    data_copy = pd.concat([data_copy, stoch_results], axis=1)

                expected_stochk_col = (
                    f"STOCHk_{stoch_k_val}_{stoch_d_val}_{stoch_smooth_k_val}"
                )
                expected_stochd_col = (
                    f"STOCHd_{stoch_k_val}_{stoch_d_val}_{stoch_smooth_k_val}"
                )

                self.tcn["Adaptive_STOCHk"] = (
                    expected_stochk_col
                    if expected_stochk_col in data_copy.columns
                    else self._gtcn("Adaptive_STOCHk", data_copy)
                )
                self.tcn["Adaptive_STOCHd"] = (
                    expected_stochd_col
                    if expected_stochd_col in data_copy.columns
                    else self._gtcn("Adaptive_STOCHd", data_copy)
                )

                if not self.tcn["Adaptive_STOCHk"]:
                    self.lg.warning(
                        f"{NY}Could not find column for Adaptive_STOCHk (tried: {expected_stochk_col}). Check pandas-ta naming.{RST}",
                    )
                if not self.tcn["Adaptive_STOCHd"]:
                    self.lg.warning(
                        f"{NY}Could not find column for Adaptive_STOCHd (tried: {expected_stochd_col}). Check pandas-ta naming.{RST}",
                    )

            if indicators_config.get("rsi", False):
                rsi_period = params_config["RSI"]
                rsi_results = data_copy.ta.rsi(length=rsi_period, append=False)
                if rsi_results is not None and not rsi_results.empty:
                    data_copy = pd.concat([data_copy, rsi_results], axis=1)
                self.tcn["RSI"] = self._gtcn("RSI", data_copy)

            if indicators_config.get("bollinger_bands", False):
                bb_period = params_config["BB_Period"]
                bb_std_dev = params_config["BB_StdDev"]
                bb_results = data_copy.ta.bbands(
                    length=bb_period, std=bb_std_dev, append=False,
                )
                if bb_results is not None and not bb_results.empty:
                    data_copy = pd.concat([data_copy, bb_results], axis=1)
                self.tcn["BB_Lower"] = self._gtcn("BB_Lower", data_copy)
                self.tcn["BB_Middle"] = self._gtcn("BB_Middle", data_copy)
                self.tcn["BB_Upper"] = self._gtcn("BB_Upper", data_copy)

            if indicators_config.get("volume_confirmation", False):
                volume_ma_period = params_config["Volume_MA_Period"]
                volume_ma_col_name = f"VOL_SMA_{volume_ma_period}"
                data_copy["volume"] = data_copy["volume"].astype(float)
                data_copy[volume_ma_col_name] = ta.sma(
                    data_copy["volume"].fillna(0), length=volume_ma_period,
                )
                self.tcn["Volume_MA"] = volume_ma_col_name

            # Correctly check for Fisher indicator enablement from nested structure
            fisher_config = indicators_config.get("fisher", {})
            if isinstance(fisher_config, dict) and fisher_config.get("enabled", False):
                # Already correctly sourced due to _gtcn update
                fisher_period = params_config["Fisher_Period"]
                fisher_results_df = data_copy.ta.fisher(
                    length=fisher_period, append=False,
                )
                if fisher_results_df is not None and not fisher_results_df.empty:
                    data_copy = pd.concat([data_copy, fisher_results_df], axis=1)
                self.tcn["FISHERT"] = self._gtcn("FISHERT", data_copy)

            self.d = data_copy
            self.lg.debug(
                f"Finished indicator calculations for {self.s}. Final DF columns: {self.d.columns.tolist()}. The indicator spirits have blessed the data.",
            )
        except AttributeError as e:
            self.lg.error(
                f"{NR}AttributeError calculating indicators for {self.s}: {e}. Check pandas_ta usage and data. A missing thread in the weave!{RST}",
                exc_info=True,
            )
        except Exception as e:
            self.lg.error(
                f"{NR}Error calculating indicators with pandas_ta for {self.s}: {e}. The indicator spells faltered!{RST}",
                exc_info=True,
            )

    def _uliv(self):
        """Update Latest Indicator Values: Extracts the most recent calculated indicator
        values and core OHLCV data from the DataFrame.
        """
        if self.d.empty:
            self.lg.warning(
                f"{NY}Cannot update latest values: DataFrame empty for {self.s}. Initializing with NaNs. The well of data is dry!{RST}",
            )
            self.iv = {
                k: Decimal(np.nan)
                for k in list(self.tcn.keys())
                + ["Close", "Volume", "High", "Low", "Open"]
            }
            return

        if self.d.iloc[-1].isnull().all():
            self.lg.warning(
                f"{NY}Cannot update latest values: Last row contains all NaNs for {self.s}. Initializing with NaNs. The latest whispers are unintelligible!{RST}",
            )
            self.iv = {
                k: Decimal(np.nan)
                for k in list(self.tcn.keys())
                + ["Close", "Volume", "High", "Low", "Open"]
            }
            return

        try:
            latest_row = self.d.iloc[-1]
            updated_values = {}

            for key, col_name in self.tcn.items():
                if col_name and col_name in latest_row.index:
                    value = latest_row[col_name]
                    if pd.notna(value):
                        try:
                            updated_values[key] = Decimal(str(value))
                        except (
                            ValueError,
                            TypeError,
                            InvalidOperation,
                        ) as conversion_error:
                            self.lg.warning(
                                f"{NY}Could not convert value for {key} ('{col_name}': {value}) for {self.s}. Storing NaN. Error: {conversion_error}. A numerical anomaly!{RST}",
                            )
                            updated_values[key] = Decimal(np.nan)
                    else:
                        updated_values[key] = Decimal(np.nan)
                else:
                    if key in self.tcn:
                        self.lg.debug(
                            f"Indicator column '{col_name}' for key '{key}' not found in latest data row for {self.s}. Storing NaN. The expected rune is missing.",
                        )
                    updated_values[key] = Decimal(np.nan)

            for base_col in ["open", "high", "low", "close", "volume"]:
                capitalized_key = base_col.capitalize()
                value = latest_row.get(base_col)
                if pd.notna(value):
                    try:
                        updated_values[capitalized_key] = Decimal(str(value))
                    except (
                        ValueError,
                        TypeError,
                        InvalidOperation,
                    ) as conversion_error:
                        self.lg.warning(
                            f"{NY}Could not convert base value for '{base_col}' ({value}) to Decimal for {self.s}. Storing NaN. Error: {conversion_error}. The core values shimmer!{RST}",
                        )
                        updated_values[capitalized_key] = Decimal(np.nan)
                else:
                    updated_values[capitalized_key] = Decimal(np.nan)

            self.iv = updated_values

            verbose_values_log = {}
            price_precision = TA.gpp(self.mi, self.lg)
            for k, v in self.iv.items():
                if pd.notna(v):
                    if isinstance(v, Decimal):
                        precision_for_log = (
                            price_precision
                            if k in ["Open", "High", "Low", "Close", "ATR"]
                            else 6
                        )
                        verbose_values_log[k] = f"{v:.{precision_for_log}f}"
                    else:  # Should ideally not happen if all are Decimal
                        verbose_values_log[k] = str(v)
                else:
                    verbose_values_log[k] = "NaN"
            self.lg.debug(
                f"Latest indicator values updated for {self.s}: {verbose_values_log}. The market's current state is revealed.",
            )
        except IndexError:
            self.lg.error(
                f"{NR}Error accessing latest row (iloc[-1]) for {self.s}. DataFrame might be empty or too short after cleaning. Resetting indicator values to NaN. The temporal stream is too shallow!{RST}",
            )
            self.iv = {
                k: Decimal(np.nan)
                for k in list(self.tcn.keys())
                + ["Close", "Volume", "High", "Low", "Open"]
            }
        except Exception as e:
            self.lg.error(
                f"{NR}Unexpected error updating latest indicator values for {self.s}: {e}. A glitch in the scrying mirror!{RST}",
                exc_info=True,
            )
            self.iv = {
                k: Decimal(np.nan)
                for k in list(self.tcn.keys())
                + ["Close", "Volume", "High", "Low", "Open"]
            }

    def cfl(self, window: int | None = None) -> dict[str, Decimal]:
        """Calculate Fibonacci Levels: Computes Fibonacci retracement/extension levels
        based on the high and low prices within a specified window.
        """
        window = window or self.cfg.get("fibonacci_window", DIP["fib_window"])
        if len(self.d) < window:
            self.lg.debug(
                f"Not enough data ({len(self.d)} points) for Fibonacci window ({window}) on {self.s}. Skipping calculation. The pattern is too short to discern!{RST}",
            )
            self.fld = {}
            return {}

        data_slice = self.d.tail(window)
        try:
            highest_price = Decimal(str(data_slice["high"].dropna().max()))
            lowest_price = Decimal(str(data_slice["low"].dropna().min()))

            if pd.isna(highest_price) or pd.isna(lowest_price):
                self.lg.warning(
                    f"{NY}Could not find valid high/low prices within the last {window} periods for Fibonacci calculation on {self.s}. Skipping. The extremes are veiled!{RST}",
                )
                self.fld = {}
                return {}

            price_difference = highest_price - lowest_price

            levels = {}
            price_precision = TA.gpp(self.mi, self.lg)
            min_tick_size = TA.gmts(self.mi, self.lg)

            if price_difference > 0:
                for level_percent in FL:
                    level_name = f"Fib_{level_percent * 100:.1f}%"
                    calculated_level = highest_price - (
                        price_difference * level_percent
                    )
                    if min_tick_size > 0:
                        quantized_level = (calculated_level / min_tick_size).quantize(
                            Decimal("1"), rounding=ROUND_HALF_EVEN,
                        ) * min_tick_size
                    else:
                        quantized_level = calculated_level.quantize(
                            Decimal("1e-" + str(price_precision)),
                            rounding=ROUND_HALF_EVEN,
                        )
                    levels[level_name] = quantized_level
            else:
                self.lg.debug(
                    f"Fibonacci range is zero or negative (High={highest_price}, Low={lowest_price}) for {self.s} over last {window} periods. All levels set to High/Low. The market's range is too narrow!{RST}",
                )
                quantized_level_zero_range = highest_price.quantize(
                    min_tick_size
                    if min_tick_size > 0
                    else Decimal("1e-" + str(price_precision)),
                    rounding=ROUND_HALF_EVEN,
                )
                for level_percent in FL:
                    levels[f"Fib_{level_percent * 100:.1f}%"] = (
                        quantized_level_zero_range
                    )

            self.fld = levels
            log_levels = {k: str(v) for k, v in levels.items()}
            self.lg.debug(
                f"Calculated Fibonacci levels for {self.s} (Window: {window}): {log_levels}. The golden threads are spun!{RST}",
            )
            return levels
        except KeyError as e:
            self.lg.error(
                f"{NR}Fibonacci calculation error for {self.s}: Missing column '{e}'. Ensure 'high' and 'low' columns exist in DataFrame. A vital thread is missing!{RST}",
            )
            self.fld = {}
            return {}
        except Exception as e:
            self.lg.error(
                f"{NR}Unexpected Fibonacci calculation error for {self.s}: {e}. A cosmic disturbance in the patterns!{RST}",
                exc_info=True,
            )
            self.fld = {}
            return {}

    @staticmethod
    def gpp(market_info: dict[str, Any], logger: logging.Logger) -> int:
        """Get Price Precision: Determines the number of decimal places for price
        based on market information provided by the exchange.
        """
        symbol_name = market_info.get("symbol", "UNKNOWN")
        try:
            precision_info = market_info.get("precision", {})
            price_precision_value = precision_info.get("price")

            if price_precision_value is not None:
                if (
                    isinstance(price_precision_value, int)
                    and price_precision_value >= 0
                ):
                    logger.debug(
                        f"Using price precision (decimal places) from market_info.precision.price: {price_precision_value} for {symbol_name}. A clear decree from the market.{RST}",
                    )
                    return price_precision_value
                if isinstance(price_precision_value, (float, str)):
                    try:
                        tick_size = Decimal(str(price_precision_value))
                        if tick_size > 0:
                            precision_decimal_places = abs(
                                tick_size.normalize().as_tuple().exponent,
                            )
                            logger.debug(
                                f"Calculated price precision from market_info.precision.price (tick size {tick_size}): {precision_decimal_places} for {symbol_name}. Deciphering the smallest increment.{RST}",
                            )
                            return precision_decimal_places
                    except (InvalidOperation, ValueError, TypeError) as e:
                        logger.warning(
                            f"{NY}Could not parse precision.price '{price_precision_value}' as tick size for {symbol_name}: {e}. The precision rune is unclear.{RST}",
                        )

            limits_info = market_info.get("limits", {})
            price_limits = limits_info.get("price", {})
            min_price_value = price_limits.get("min")
            if min_price_value is not None:
                try:
                    min_price_tick = Decimal(str(min_price_value))
                    if min_price_tick > 0 and min_price_tick < Decimal("0.1"):
                        precision_decimal_places = abs(
                            min_price_tick.normalize().as_tuple().exponent,
                        )
                        logger.debug(
                            f"Inferred price precision from limits.price.min ({min_price_tick}): {precision_decimal_places} for {symbol_name}. A subtle hint from the market's boundaries.{RST}",
                        )
                        return precision_decimal_places
                    logger.debug(
                        f"limits.price.min ({min_price_tick}) for {symbol_name} seems too large for tick size, likely minimum order price. Ignoring for precision. This is not the tick we seek.{RST}",
                    )
                except (InvalidOperation, ValueError, TypeError) as e:
                    logger.warning(
                        f"{NY}Could not parse limits.price.min '{min_price_value}' for precision inference for {symbol_name}: {e}. The limit rune is ambiguous.{RST}",
                    )
        except Exception as e:
            logger.warning(
                f"{NY}Error determining price precision for {symbol_name} from market info: {e}. Falling back. The market's exactitude is obscured.{RST}",
            )

        default_precision = 4
        logger.warning(
            f"{NY}Could not determine price precision for {symbol_name}. Using default: {default_precision}. A general understanding will suffice.{RST}",
        )
        return default_precision

    @staticmethod
    def gmts(market_info: dict[str, Any], logger: logging.Logger) -> Decimal:
        """Get Minimum Tick Size: Determines the smallest price increment allowed by the exchange."""
        symbol_name = market_info.get("symbol", "UNKNOWN")
        try:
            precision_info = market_info.get("precision", {})
            price_precision_value = precision_info.get("price")

            if price_precision_value is not None:
                if isinstance(price_precision_value, (float, str)):
                    try:
                        tick_size = Decimal(str(price_precision_value))
                        if tick_size > 0:
                            logger.debug(
                                f"Using tick size from precision.price: {tick_size} for {symbol_name}. The market's smallest increment.{RST}",
                            )
                            return tick_size
                    except (InvalidOperation, ValueError, TypeError) as e:
                        logger.warning(
                            f"{NY}Could not parse precision.price '{price_precision_value}' as tick size for {symbol_name}: {e}. The precision rune is malformed.{RST}",
                        )
                elif (
                    isinstance(price_precision_value, int)
                    and price_precision_value >= 0
                ):
                    tick_size = Decimal("1e-" + str(price_precision_value))
                    logger.debug(
                        f"Calculated tick size from precision.price (decimal places {price_precision_value}): {tick_size} for {symbol_name}. Derived from decimal places.{RST}",
                    )
                    return tick_size

            limits_info = market_info.get("limits", {})
            price_limits = limits_info.get("price", {})
            min_price_value = price_limits.get("min")
            if min_price_value is not None:
                try:
                    min_tick_from_limits = Decimal(str(min_price_value))
                    if min_tick_from_limits > 0 and min_tick_from_limits < Decimal(
                        "0.1",
                    ):
                        logger.debug(
                            f"Using tick size from limits.price.min: {min_tick_from_limits} for {symbol_name}. A subtle clue from the market's bounds.{RST}",
                        )
                        return min_tick_from_limits
                except (InvalidOperation, ValueError, TypeError) as e:
                    logger.warning(
                        f"{NY}Could not parse limits.price.min '{min_price_value}' for precision inference for {symbol_name}: {e}. The limit's whisper is unclear.{RST}",
                    )

        except Exception as e:
            logger.warning(
                f"{NY}Error determining minimum tick size for {symbol_name} from market info: {e}. Falling back. The market's granularity is obscured.{RST}",
            )

        fallback_price_precision = TA.gpp(market_info, logger)
        fallback_tick = Decimal("1e-" + str(fallback_price_precision))
        logger.debug(
            f"Using fallback tick size based on derived precision places ({fallback_price_precision}): {fallback_tick} for {symbol_name}. A last resort, but reliable.{RST}",
        )
        return fallback_tick

    def gnfl(
        self, current_price: Decimal, num_levels: int = 5,
    ) -> list[tuple[str, Decimal]]:
        """Get Nearest Fibonacci Levels: Finds the closest Fibonacci levels to the current price."""
        if not self.fld:
            self.lg.debug(
                f"Fibonacci levels not calculated yet for {self.s}. Cannot find nearest. The golden spirals are not yet formed.{RST}",
            )
            return []
        if not isinstance(current_price, Decimal) or current_price <= 0:
            self.lg.warning(
                f"{NY}Invalid current price ({current_price}) provided for Fibonacci comparison on {self.s}. The current point in the pattern is unclear.{RST}",
            )
            return []
        try:
            levels_with_distance = []
            for name, level_price in self.fld.items():
                if isinstance(level_price, Decimal) and level_price > 0:
                    levels_with_distance.append(
                        {
                            "name": name,
                            "level": level_price,
                            "distance": abs(current_price - level_price),
                        },
                    )
                else:
                    self.lg.warning(
                        f"{NY}Invalid or non-decimal value found in fib_levels_data: {name}={level_price}. Skipping. A flawed thread in the pattern.{RST}",
                    )

            levels_with_distance.sort(key=lambda x: x["distance"])
            return [
                (item["name"], item["level"])
                for item in levels_with_distance[:num_levels]
            ]
        except Exception as e:
            self.lg.error(
                f"{NR}Error finding nearest Fibonacci levels for {self.s}: {e}. The pattern's proximity is obscured!{RST}",
                exc_info=True,
            )
            return []

    def _cea(self) -> Decimal:
        """Check EMA Alignment Score: Calculates a score based on the alignment of short,
        long EMAs, and the current closing price.
        """
        ema_short = self.iv.get("EMA_Short")
        ema_long = self.iv.get("EMA_Long")
        close_price = self.iv.get("Close")

        if pd.isna(ema_short) or pd.isna(ema_long) or pd.isna(close_price):
            self.lg.debug(
                f"EMA Alignment check skipped for {self.s}: Missing required values (EMA_Short={ema_short}, EMA_Long={ema_long}, or Close={close_price}). The moving currents are not clear enough.{RST}",
            )
            return Decimal(np.nan)

        if close_price > ema_short > ema_long:
            return Decimal("1.0")
        if close_price < ema_short < ema_long:
            return Decimal("-1.0")
        return Decimal("0.0")

    def _cm(self) -> Decimal:
        """Check Momentum Score: Calculates a score based on the Momentum indicator,
        scaled relative to the closing price.
        """
        momentum_value = self.iv.get("Momentum")
        if pd.isna(momentum_value):
            self.lg.debug(
                f"Momentum check skipped for {self.s}: Missing Momentum value ({momentum_value}). The market's impulse is unclear.{RST}",
            )
            return Decimal(np.nan)

        last_close_decimal = self.iv.get("Close")
        if pd.isna(last_close_decimal) or last_close_decimal <= 0:
            self.lg.debug(
                f"Momentum check skipped for {self.s}: Invalid 'Close' price ({last_close_decimal}) for scaling. Cannot gauge relative strength.{RST}",
            )
            return Decimal("0.0")

        try:
            momentum_percentage = momentum_value / last_close_decimal

            threshold_positive = self.indicator_thresholds.get(
                "momentum_positive_threshold", DIP["psar_af"],
            )
            threshold_strong_positive = self.indicator_thresholds.get(
                "momentum_strong_positive_threshold", DIP["psar_max_af"],
            )

            if momentum_percentage > threshold_positive:
                score = min(
                    Decimal("1.0"),
                    (momentum_percentage - threshold_positive)
                    / (threshold_strong_positive - threshold_positive),
                )
                return score if score > 0 else Decimal("0.0")
            if momentum_percentage < -threshold_positive:
                score = max(
                    Decimal("-1.0"),
                    (momentum_percentage + threshold_positive)
                    / (threshold_strong_positive - threshold_positive),
                )
                return score if score < 0 else Decimal("0.0")
            return Decimal("0.0")
        except (InvalidOperation, ValueError, TypeError) as e:
            self.lg.warning(
                f"{NY}Error during momentum check calculation for {self.s}: {e}. A numerical ripple!{RST}",
            )
            return Decimal(np.nan)

    def _cvc(self) -> Decimal:
        """Check Volume Confirmation Score: Assesses if current volume confirms price movement
        by comparing it to a moving average of volume.
        """
        current_volume = self.iv.get("Volume")
        volume_ma = self.iv.get("Volume_MA")
        multiplier = self.cfg.get("volume_confirmation_multiplier", Decimal("1.5"))

        if (
            pd.isna(current_volume)
            or current_volume < 0
            or pd.isna(volume_ma)
            or volume_ma <= 0
        ):
            self.lg.debug(
                f"Volume confirmation check skipped for {self.s}: Missing required values (Volume={current_volume} or Volume_MA={volume_ma}). The market's breath is shallow.{RST}",
            )
            return Decimal(np.nan)

        try:
            volume_ratio = current_volume / volume_ma

            if volume_ratio > multiplier:
                score = min(
                    Decimal("1.0"),
                    Decimal("0.5")
                    + ((volume_ratio - multiplier) / (multiplier * Decimal("2"))),
                )
                return score
            if volume_ratio < (Decimal(1) / multiplier):
                return Decimal("-0.4")
            return Decimal("0.0")
        except (InvalidOperation, ValueError, TypeError) as e:
            self.lg.warning(
                f"{NY}Error during volume confirmation check for {self.s}: {e}. A volumetric distortion!{RST}",
            )
            return Decimal(np.nan)

    def _cadstoch(self) -> Decimal:
        """Check Adaptive Stochastic Score: Evaluates K and D lines for overbought/oversold
        conditions and crossovers.
        """
        k_line = self.iv.get("Adaptive_STOCHk")
        d_line = self.iv.get("Adaptive_STOCHd")

        if pd.isna(k_line) or pd.isna(d_line):
            self.lg.debug(
                f"Adaptive Stochastic check skipped for {self.s}: Missing K ({k_line}) or D ({d_line}) values. The oscillations are unclear.{RST}",
            )
            return Decimal(np.nan)

        oversold_threshold = Decimal(
            str(self.indicator_thresholds.get("adaptive_stoch_oversold_threshold", 20)),
        )
        overbought_threshold = Decimal(
            str(
                self.indicator_thresholds.get("adaptive_stoch_overbought_threshold", 80),
            ),
        )
        crossover_strength = Decimal(
            str(self.indicator_thresholds.get("adaptive_stoch_crossover_strength", 5)),
        )

        score = Decimal("0.0")

        if k_line < oversold_threshold and d_line < oversold_threshold:
            score = Decimal("1.0")  # Buy signal
        elif k_line > overbought_threshold and d_line > overbought_threshold:
            score = Decimal("-1.0")  # Sell signal

        # Crossover logic
        difference = k_line - d_line
        if abs(difference) > crossover_strength:  # Significant crossover
            if difference > 0:  # K crosses above D
                score = max(score, Decimal("0.6"))  # Stronger buy influence
            else:  # K crosses below D
                score = min(score, Decimal("-0.6"))  # Stronger sell influence
        elif k_line > d_line:  # K is above D (but not strong crossover)
            score = max(score, Decimal("0.2"))  # Weaker buy influence
        elif k_line < d_line:  # K is below D (but not strong crossover)
            score = min(score, Decimal("-0.2"))  # Weaker sell influence

        # Reduce score if in neutral zone (e.g., between 40 and 60)
        if Decimal("40") < k_line < Decimal("60"):
            score *= Decimal("0.5")

        return score

    def _cr(self) -> Decimal:
        """Check RSI Score: Assesses RSI for overbought/oversold conditions and trend strength."""
        rsi_value = self.iv.get("RSI")
        if pd.isna(rsi_value):
            self.lg.debug(
                f"RSI check skipped for {self.s}: Missing RSI value ({rsi_value}). The relative strength is unknown.{RST}",
            )
            return Decimal(np.nan)

        rsi_oversold = Decimal(
            str(self.indicator_thresholds.get("rsi_oversold_threshold", 30)),
        )
        rsi_overbought = Decimal(
            str(self.indicator_thresholds.get("rsi_overbought_threshold", 70)),
        )
        rsi_approaching_oversold = Decimal(
            str(self.indicator_thresholds.get("rsi_approaching_oversold_threshold", 40)),
        )
        rsi_approaching_overbought = Decimal(
            str(
                self.indicator_thresholds.get(
                    "rsi_approaching_overbought_threshold", 60,
                ),
            ),
        )

        if rsi_value <= rsi_oversold:
            return Decimal("1.0")
        if rsi_value >= rsi_overbought:
            return Decimal("-1.0")
        if rsi_value < rsi_approaching_oversold:
            return Decimal("0.5")
        if rsi_value > rsi_approaching_overbought:
            return Decimal("-0.5")

        if rsi_approaching_oversold <= rsi_value <= rsi_approaching_overbought:
            return (rsi_value - Decimal("50")) / Decimal("50.0")

        return Decimal("0.0")

    def _cc(self) -> Decimal:
        """Check CCI Score: Evaluates CCI for overbought/oversold conditions and trend direction."""
        cci_value = self.iv.get("CCI")
        if pd.isna(cci_value):
            self.lg.debug(
                f"CCI check skipped for {self.s}: Missing CCI value ({cci_value}). The commodity channel is obscured.{RST}",
            )
            return Decimal(np.nan)

        cci_extreme_oversold = Decimal(
            str(self.indicator_thresholds.get("cci_extreme_oversold_threshold", -150)),
        )
        cci_extreme_overbought = Decimal(
            str(self.indicator_thresholds.get("cci_extreme_overbought_threshold", 150)),
        )
        cci_oversold = Decimal(
            str(self.indicator_thresholds.get("cci_oversold_threshold", -80)),
        )
        cci_overbought = Decimal(
            str(self.indicator_thresholds.get("cci_overbought_threshold", 80)),
        )

        if cci_value <= cci_extreme_oversold:
            return Decimal("1.0")
        if cci_value >= cci_extreme_overbought:
            return Decimal("-1.0")
        if cci_value < cci_oversold:
            return Decimal("0.6")
        if cci_value > cci_overbought:
            return Decimal("-0.6")

        if cci_oversold <= cci_value < Decimal("0"):
            return Decimal("0.1")
        if Decimal("0") < cci_value <= cci_overbought:
            return Decimal("-0.1")

        return Decimal("0.0")

    def _cwr(self) -> Decimal:
        """Check Williams %R Score: Assesses Williams %R for overbought/oversold conditions."""
        wr_value = self.iv.get("Williams_R")
        if pd.isna(wr_value):
            self.lg.debug(
                f"Williams %R check skipped for {self.s}: Missing value ({wr_value}). The percentage range is unknown.{RST}",
            )
            return Decimal(np.nan)

        willr_oversold = Decimal(
            str(self.indicator_thresholds.get("willr_oversold_threshold", -80)),
        )
        willr_overbought = Decimal(
            str(self.indicator_thresholds.get("willr_overbought_threshold", -20)),
        )

        if wr_value <= willr_oversold:
            return Decimal("1.0")
        if wr_value >= willr_overbought:
            return Decimal("-1.0")
        # These are hardcoded, could be configurable
        if willr_oversold < wr_value < Decimal("-50"):
            return Decimal("0.4")
        # These are hardcoded, could be configurable
        if Decimal("-50") < wr_value < willr_overbought:
            return Decimal("-0.4")

        return Decimal("0.0")

    def _cpsar(self) -> Decimal:
        """Check PSAR Score: Determines trend direction based on Parabolic SAR."""
        psar_long_active = self.iv.get("PSAR_long")
        psar_short_active = self.iv.get("PSAR_short")

        is_long_active = pd.notna(psar_long_active)
        is_short_active = pd.notna(psar_short_active)

        if is_long_active and not is_short_active:
            return Decimal("1.0")
        if is_short_active and not is_long_active:
            return Decimal("-1.0")
        if not is_long_active and not is_short_active:
            self.lg.debug(
                f"PSAR check skipped for {self.s}: No active PSAR signal (both NaN). The parabolic path is undefined.{RST}",
            )
            return Decimal(np.nan)
        self.lg.warning(
            f"{NY}PSAR check encountered unexpected state for {self.s}: Long={psar_long_active}, Short={psar_short_active}. Returning neutral. The paths diverge!{RST}",
        )
        return Decimal("0.0")

    def _csma(self) -> Decimal:
        """Check SMA10 Score: Compares current closing price to a 10-period Simple Moving Average."""
        sma10_value = self.iv.get("SMA10")
        last_close_decimal = self.iv.get("Close")

        if pd.isna(sma10_value) or pd.isna(last_close_decimal):
            self.lg.debug(
                f"SMA10 check skipped for {self.s}: Missing SMA10 ({sma10_value}) or Close ({last_close_decimal}) value. The short-term average is elusive.{RST}",
            )
            return Decimal(np.nan)

        sma10_score = self.indicator_thresholds.get("sma10_score", Decimal("0.6"))

        if last_close_decimal > sma10_value:
            return sma10_score
        if last_close_decimal < sma10_value:
            return -sma10_score
        return Decimal("0.0")

    def _cv(self) -> Decimal:
        """Check VWAP Score: Compares current closing price to the Volume Weighted Average Price."""
        vwap_value = self.iv.get("VWAP")
        last_close_decimal = self.iv.get("Close")

        if pd.isna(vwap_value) or pd.isna(last_close_decimal):
            self.lg.debug(
                f"VWAP check skipped for {self.s}: Missing VWAP ({vwap_value}) or Close ({last_close_decimal}) value. The volume's average is hidden.{RST}",
            )
            return Decimal(np.nan)

        vwap_score = self.indicator_thresholds.get("vwap_score", Decimal("0.7"))

        if last_close_decimal > vwap_value:
            return vwap_score
        if last_close_decimal < vwap_value:
            return -vwap_score
        return Decimal("0.0")

    def _cmfi(self) -> Decimal:
        """Check MFI Score: Evaluates Money Flow Index for overbought/oversold conditions."""
        mfi_value = self.iv.get("MFI")
        if pd.isna(mfi_value):
            self.lg.debug(
                f"MFI check skipped for {self.s}: Missing MFI value ({mfi_value}). The flow of money is obscured.{RST}",
            )
            return Decimal(np.nan)

        mfi_oversold = Decimal(
            str(self.indicator_thresholds.get("mfi_oversold_threshold", 20)),
        )
        mfi_overbought = Decimal(
            str(self.indicator_thresholds.get("mfi_overbought_threshold", 80)),
        )

        if mfi_value <= mfi_oversold:
            return Decimal("1.0")
        if mfi_value >= mfi_overbought:
            return Decimal("-1.0")
        if mfi_value < Decimal("40"):  # These are hardcoded, could be configurable
            return Decimal("0.4")
        if mfi_value > Decimal("60"):  # These are hardcoded, could be configurable
            return Decimal("-0.4")

        return Decimal("0.0")

    def _cbb(self) -> Decimal:
        """Check Bollinger Bands Score: Assesses price position relative to Bollinger Bands."""
        bb_lower = self.iv.get("BB_Lower")
        bb_middle = self.iv.get("BB_Middle")
        bb_upper = self.iv.get("BB_Upper")
        last_close_decimal = self.iv.get("Close")

        if (
            pd.isna(bb_lower)
            or pd.isna(bb_middle)
            or pd.isna(bb_upper)
            or pd.isna(last_close_decimal)
        ):
            self.lg.debug(
                f"Bollinger Bands check skipped for {self.s}: Missing BB ({bb_lower}/{bb_middle}/{bb_upper}) or Close ({last_close_decimal}) values. The volatility envelope is unclear.{RST}",
            )
            return Decimal(np.nan)

        bb_extreme_score = self.indicator_thresholds.get(
            "bollinger_bands_extreme_score", Decimal("1.0"),
        )
        bb_mid_score_multiplier = self.indicator_thresholds.get(
            "bollinger_bands_mid_score_multiplier", Decimal("0.7"),
        )

        if last_close_decimal <= bb_lower:
            return bb_extreme_score
        if last_close_decimal >= bb_upper:
            return -bb_extreme_score

        # Corrected to be from middle to upper/lower band
        band_width = bb_upper - bb_middle
        if band_width > 0:
            relative_position = (last_close_decimal - bb_middle) / band_width
            score = max(Decimal("-1.0"), min(Decimal("1.0"), relative_position))
            return score * bb_mid_score_multiplier
            return Decimal("0.0")

    def _cfisher(self) -> Decimal:
        """Check Ehlers Fisher Transform Score: Evaluates the Fisher Transform value
        against configured thresholds.
        """
        fisher_value = self.iv.get("FISHERT")  # Using "FISHERT" as the key from self.iv
        if pd.isna(fisher_value):
            self.lg.debug(
                f"Fisher Transform check skipped for {self.s}: Missing FISHERT value. The transform is undefined.{RST}",
            )
            return Decimal("0.0")

        buy_threshold = self.indicator_thresholds.get(
            "fisher_buy_threshold", Decimal("-1.0"),
        )
        sell_threshold = self.indicator_thresholds.get(
            "fisher_sell_threshold", Decimal("1.0"),
        )
        extreme_buy_threshold = self.indicator_thresholds.get(
            "fisher_extreme_buy_threshold", Decimal("-2.0"),
        )
        extreme_sell_threshold = self.indicator_thresholds.get(
            "fisher_extreme_sell_threshold", Decimal("2.0"),
        )

        if fisher_value <= extreme_buy_threshold:
            return Decimal("1.0")  # Strong buy
        if fisher_value <= buy_threshold:
            return Decimal("0.5")  # Buy
        if fisher_value >= extreme_sell_threshold:
            return Decimal("-1.0")  # Strong sell
        if fisher_value >= sell_threshold:
            return Decimal("-0.5")  # Sell
        # Optional: Could scale score between thresholds, e.g., if between buy_threshold and 0
        # For now, neutral if between buy and sell thresholds.
        return Decimal("0.0")

    def _cob(self, orderbook_data: dict | None, current_price: Decimal) -> Decimal:
        """Check Orderbook Score: Analyzes the imbalance between bids and asks in the order book."""
        if not orderbook_data:
            self.lg.debug(
                f"Orderbook check skipped for {self.s}: No data provided. The whispers are silent.{RST}",
            )
            return Decimal(np.nan)

        try:
            bids = orderbook_data.get("bids", [])
            asks = orderbook_data.get("asks", [])

            if not bids or not asks:
                self.lg.debug(
                    f"Orderbook check skipped for {self.s}: Missing bids or asks in orderbook data. The market's desires are not fully formed.{RST}",
                )
                return Decimal(np.nan)

            num_levels_to_consider = self.cfg.get("orderbook_limit", 25)
            top_bids = bids[:num_levels_to_consider]
            top_asks = asks[:num_levels_to_consider]

            bid_volumes_sum = sum(
                Decimal(str(bid[1])) for bid in top_bids if len(bid) == 2
            )
            ask_volumes_sum = sum(
                Decimal(str(ask[1])) for ask in top_asks if len(ask) == 2
            )

            total_volume = bid_volumes_sum + ask_volumes_sum

            if total_volume == Decimal("0"):
                self.lg.debug(
                    f"Orderbook check ({self.s}): Zero total volume in top {num_levels_to_consider} levels. Returning neutral. The market's breath is held.{RST}",
                )
                return Decimal("0.0")

            order_book_imbalance_decimal = (
                bid_volumes_sum - ask_volumes_sum
            ) / total_volume
            score = order_book_imbalance_decimal

            self.lg.debug(
                f"Orderbook check ({self.s}): Top {num_levels_to_consider} levels -> BidVol={bid_volumes_sum:.4f}, AskVol={ask_volumes_sum:.4f}, OBI={order_book_imbalance_decimal:.4f} -> Score={score:.4f}. The balance of supply and demand.{RST}",
            )
            return score
        except (InvalidOperation, ValueError, TypeError) as e:
            self.lg.warning(
                f"{NY}Orderbook analysis failed for {self.s} (data conversion error): {e}. A numerical distortion in the market's desires!{RST}",
                exc_info=False,
            )
            return Decimal(np.nan)
        except Exception as e:
            self.lg.warning(
                f"{NY}Orderbook analysis failed for {self.s} (unexpected error): {e}. A cosmic interference in the market's intentions!{RST}",
                exc_info=True,
            )
            return Decimal(np.nan)

    # Note: This is the first definition of _cfisher, which already meets the requirements.
    # The duplicated _cfisher method further down (around line 1600s) was the one that needed changing.
    # This change effectively replaces the second definition with the first.
    def _cfisher(self) -> Decimal:
        """Check Ehlers Fisher Transform Score: Evaluates the Fisher Transform value
        against configured thresholds.
        """
        fisher_value = self.iv.get("FISHERT")  # Using "FISHERT" as the key from self.iv
        if pd.isna(fisher_value):
            self.lg.debug(
                f"Fisher Transform check skipped for {self.s}: Missing FISHERT value. The transform is undefined.{RST}",
            )
            return Decimal("0.0")

        buy_threshold = self.indicator_thresholds.get(
            "fisher_buy_threshold", Decimal("-1.0"),
        )
        sell_threshold = self.indicator_thresholds.get(
            "fisher_sell_threshold", Decimal("1.0"),
        )
        extreme_buy_threshold = self.indicator_thresholds.get(
            "fisher_extreme_buy_threshold", Decimal("-2.0"),
        )
        extreme_sell_threshold = self.indicator_thresholds.get(
            "fisher_extreme_sell_threshold", Decimal("2.0"),
        )

        if fisher_value <= extreme_buy_threshold:
            return Decimal("1.0")  # Strong buy
        if fisher_value <= buy_threshold:
            return Decimal("0.5")  # Buy
        if fisher_value >= extreme_sell_threshold:
            return Decimal("-1.0")  # Strong sell
        if fisher_value >= sell_threshold:
            return Decimal("-0.5")  # Sell
        # Optional: Could scale score between thresholds, e.g., if between buy_threshold and 0
        # For now, neutral if between buy and sell thresholds.
        return Decimal("0.0")

    def gts(self, current_price: Decimal, orderbook_data: dict | None) -> str:
        """Generate Trade Signal: Aggregates scores from various indicators to produce a BUY, SELL, or HOLD signal."""
        self.sig = {"BUY": 0, "SELL": 0, "HOLD": 1}
        final_signal_score = Decimal("0.0")
        total_weighted_active = Decimal("0.0")
        active_indicator_count = 0
        nan_indicator_count = 0
        debug_scores = {}

        if not self.iv:
            self.lg.warning(
                f"{NY}Cannot generate signal for {self.s}: Indicator values dictionary is empty. The scrying pool is dry!{RST}",
            )
            return "HOLD"

        core_indicators_present = any(
            pd.notna(v)
            for k, v in self.iv.items()
            if k not in ["Open", "High", "Low", "Close", "Volume"]
        )
        if not core_indicators_present:
            self.lg.warning(
                f"{NY}Cannot generate signal for {self.s}: All core indicator values are NaN. Skipping signal generation. The market's subtle energies are absent!{RST}",
            )
            return "HOLD"

        if not isinstance(current_price, Decimal) or current_price <= 0:
            self.lg.warning(
                f"{NY}Cannot generate signal for {self.s}: Invalid current price ({current_price}). Skipping signal generation. The market's true value is obscured!{RST}",
            )
            return "HOLD"

        active_weight_set = self.cfg.get("weight_sets", {}).get(self.aw_name)
        if not active_weight_set:
            self.lg.error(
                f"{NR}Active weight set '{self.aw_name}' missing or empty in config for {self.s}. Cannot generate signal. The scales of judgment are missing!{RST}",
            )
            return "HOLD"

        method_map = {
            "ema_alignment": "_cea",
            "momentum": "_cm",
            "volume_confirmation": "_cvc",
            "adaptive_stoch": "_cadstoch",
            "rsi": "_cr",
            "bollinger_bands": "_cbb",
            "vwap": "_cv",
            "cci": "_cc",
            "wr": "_cwr",
            "psar": "_cpsar",
            "sma_10": "_csma",
            "mfi": "_cmfi",
            "orderbook": "_cob",
            "fisher": "_cfisher",
        }

        for indicator_key, ind_config in self.cfg.get("indicators", {}).items():
            enabled = False
            # New structure e.g. "fisher": {"enabled": True, "period": 12}
            if isinstance(ind_config, dict):
                enabled = ind_config.get("enabled", False)
            elif isinstance(ind_config, bool):  # Old structure e.g. "rsi": True
                enabled = ind_config

            if not enabled:
                continue

            weight = active_weight_set.get(indicator_key)
            if weight is None:
                continue

            if not isinstance(weight, Decimal):
                try:
                    weight = Decimal(str(weight))
                except (InvalidOperation, ValueError, TypeError):
                    self.lg.warning(
                        f"{NY}Invalid weight format '{weight}' for indicator '{indicator_key}' in weight set '{self.aw_name}'. Skipping. A flawed weighting rune!{RST}",
                    )
                    continue

            if weight == Decimal("0.0"):
                continue

            method_name = method_map.get(indicator_key)
            if (
                method_name
                and hasattr(self, method_name)
                and callable(getattr(self, method_name))
            ):
                indicator_check_method = getattr(self, method_name)
                indicator_score_decimal = Decimal(np.nan)
                try:
                    if indicator_key == "orderbook":
                        if orderbook_data:
                            indicator_score_decimal = indicator_check_method(
                                orderbook_data, current_price,
                            )
                        elif weight != Decimal("0.0"):
                            self.lg.debug(
                                f"Orderbook check skipped for {self.s}: No orderbook data provided, but indicator is enabled/weighted. The market's immediate desires are not visible.{RST}",
                            )
                    else:
                        indicator_score_decimal = indicator_check_method()
                except Exception as e:
                    self.lg.error(
                        f"{NR}Error executing indicator check method {method_name} for {self.s}: {e}. The indicator's spell fizzled!{RST}",
                        exc_info=True,
                    )

                debug_scores[indicator_key] = (
                    f"{indicator_score_decimal:.3f}"
                    if pd.notna(indicator_score_decimal)
                    else "NaN"
                )

                if pd.notna(indicator_score_decimal):
                    try:
                        clamped_score = max(
                            Decimal("-1.0"),
                            min(Decimal("1.0"), indicator_score_decimal),
                        )
                        final_signal_score += clamped_score * weight
                        total_weighted_active += weight
                        active_indicator_count += 1
                    except (
                        InvalidOperation,
                        ValueError,
                        TypeError,
                    ) as conversion_error:
                        self.lg.error(
                            f"{NR}Error processing score for {indicator_key} (Score: {indicator_score_decimal}, Weight: {weight}): {conversion_error}. A numerical distortion!{RST}",
                        )
                        nan_indicator_count += 1
                else:
                    nan_indicator_count += 1
            elif weight != Decimal("0.0"):
                self.lg.warning(
                    f"{NY}Indicator check method '{method_name}' (for '{indicator_key}') not found or not callable for enabled/weighted indicator: {indicator_key} ({self.s}). A missing incantation!{RST}",
                )

        final_signal = "HOLD"
        if total_weighted_active == Decimal("0.0"):
            self.lg.warning(
                f"{NY}No indicators contributed valid scores to the signal calculation for {self.s}. Defaulting to HOLD. The scales are empty!{RST}",
            )
        else:
            signal_threshold = self.cfg.get("signal_score_threshold", Decimal("1.5"))
            if not isinstance(signal_threshold, Decimal):
                try:
                    signal_threshold = Decimal(str(signal_threshold))
                except (InvalidOperation, ValueError, TypeError):
                    self.lg.warning(
                        f"{NY}Invalid signal_score_threshold '{signal_threshold}'. Using default 1.5. The threshold rune is unreadable!{RST}",
                    )
                    signal_threshold = Decimal("1.5")

            if final_signal_score >= signal_threshold:
                final_signal = "BUY"
            elif final_signal_score <= -signal_threshold:
                final_signal = "SELL"

        price_precision_log = TA.gpp(self.mi, self.lg)
        log_message = (
            f"Signal Summary ({self.s} @ {current_price:.{price_precision_log}f}): "
            f"Set='{self.aw_name}', Indicators=[Active:{active_indicator_count}, NaN:{nan_indicator_count}], "
            f"TotalWeight={total_weighted_active:.2f}, "
            f"FinalScore={final_signal_score:.4f} (Threshold: +/-{signal_threshold:.2f}) "
            f"==> {NG if final_signal == 'BUY' else NR if final_signal == 'SELL' else NY}{final_signal}{RST}"
        )
        self.lg.info(log_message)
        self.lg.debug(
            f"  Individual Indicator Scores ({self.s}): {debug_scores}. The components of the divination.",
        )

        if final_signal == "BUY":
            self.sig = {"BUY": 1, "SELL": 0, "HOLD": 0}
        elif final_signal == "SELL":
            self.sig = {"BUY": 0, "SELL": 1, "HOLD": 0}
        else:
            self.sig = {"BUY": 0, "SELL": 0, "HOLD": 1}

        self.final_signal_score = final_signal_score
        return final_signal

    def cets(
        self, entry_price_estimate: Decimal, signal: str,
    ) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
        """Calculate Entry, Take Profit, and Stop Loss prices based on ATR and signal direction.
        Returns (Entry Price, Take Profit Price, Stop Loss Price).
        """
        if signal not in ["BUY", "SELL"]:
            self.lg.debug(
                f"TP/SL calculation skipped for {self.s}: Signal is '{signal}'. No clear direction for the journey.{RST}",
            )
            return entry_price_estimate, None, None

        atr_value = self.iv.get("ATR")
        # Retrieve new config parameters
        use_atr_volume_tp_sl = self.cfg.get("use_atr_volume_tp_sl", False)
        tp_atr_multiplier_dynamic = self.cfg.get(
            "tp_atr_multiplier_dynamic", Decimal("1.5"),
        )
        sl_atr_multiplier_dynamic = self.cfg.get(
            "sl_atr_multiplier_dynamic", Decimal("1.2"),
        )
        volume_tp_threshold_multiplier = self.cfg.get(
            "volume_tp_threshold_multiplier", Decimal("2.0"),
        )
        volume_sl_threshold_multiplier = self.cfg.get(
            "volume_sl_threshold_multiplier", Decimal("2.0"),
        )
        tp_atr_boost_on_high_volume = self.cfg.get(
            "tp_atr_boost_on_high_volume", Decimal("0.0"),
        )
        sl_atr_widening_on_high_volume = self.cfg.get(
            "sl_atr_widening_on_high_volume", Decimal("0.0"),
        )

        atr_value = self.iv.get("ATR")
        if not isinstance(atr_value, Decimal) or atr_value <= Decimal("0"):
            self.lg.warning(
                f"{NY}Cannot calculate TP/SL for {self.s} {signal}: Invalid or missing ATR ({atr_value}). The volatility compass is broken!{RST}",
            )
            return entry_price_estimate, None, None

        if not isinstance(
            entry_price_estimate, Decimal,
        ) or entry_price_estimate <= Decimal("0"):
            self.lg.warning(
                f"{NY}Cannot calculate TP/SL for {self.s} {signal}: Invalid entry price estimate ({entry_price_estimate}). The starting point is unclear!{RST}",
            )
            return entry_price_estimate, None, None

        price_precision = TA.gpp(self.mi, self.lg)
        min_tick_size = TA.gmts(self.mi, self.lg)

        # Initialize effective multipliers for logging
        log_tp_multiplier_str = "N/A"
        log_sl_multiplier_str = "N/A"

        take_profit_offset: Decimal | None = None
        stop_loss_offset: Decimal | None = None

        try:
            if use_atr_volume_tp_sl:
                self.lg.debug(
                    f"Using DYNAMIC ATR/Volume based TP/SL logic for {self.s} {signal}.",
                )

                current_volume = self.iv.get("Volume")
                volume_ma = self.iv.get("Volume_MA")

                take_profit_offset = atr_value * tp_atr_multiplier_dynamic
                stop_loss_offset = atr_value * sl_atr_multiplier_dynamic

                effective_tp_mult = tp_atr_multiplier_dynamic
                effective_sl_mult = sl_atr_multiplier_dynamic

                log_tp_details = f"Base TP offset (ATR*{tp_atr_multiplier_dynamic:.2f}): {take_profit_offset:.{price_precision}f}"
                log_sl_details = f"Base SL offset (ATR*{sl_atr_multiplier_dynamic:.2f}): {stop_loss_offset:.{price_precision}f}"

                if (
                    isinstance(current_volume, Decimal)
                    and isinstance(volume_ma, Decimal)
                    and volume_ma > Decimal("0")
                ):
                    if current_volume > (
                        volume_ma * volume_tp_threshold_multiplier
                    ) and tp_atr_boost_on_high_volume > Decimal("0"):
                        tp_boost_amount = atr_value * tp_atr_boost_on_high_volume
                        take_profit_offset += tp_boost_amount
                        effective_tp_mult += tp_atr_boost_on_high_volume
                        log_tp_details += f", Vol Boost ({tp_atr_boost_on_high_volume:.2f}*ATR): +{tp_boost_amount:.{price_precision}f}"

                    if current_volume > (
                        volume_ma * volume_sl_threshold_multiplier
                    ) and sl_atr_widening_on_high_volume > Decimal("0"):
                        sl_widening_amount = atr_value * sl_atr_widening_on_high_volume
                        stop_loss_offset += sl_widening_amount
                        effective_sl_mult += sl_atr_widening_on_high_volume
                        log_sl_details += f", Vol Widening ({sl_atr_widening_on_high_volume:.2f}*ATR): +{sl_widening_amount:.{price_precision}f}"
                else:
                    self.lg.debug(
                        f"Volume data for dynamic TP/SL on {self.s} not available or invalid (Volume: {current_volume}, VolMA: {volume_ma}). Using base dynamic multipliers.",
                    )

                self.lg.debug(
                    f"Dynamic TP details for {self.s} {signal}: {log_tp_details}, Final TP Offset: {take_profit_offset:.{price_precision}f}",
                )
                self.lg.debug(
                    f"Dynamic SL details for {self.s} {signal}: {log_sl_details}, Final SL Offset: {stop_loss_offset:.{price_precision}f}",
                )
                log_tp_multiplier_str = f"{effective_tp_mult:.2f} (Dynamic)"
                log_sl_multiplier_str = f"{effective_sl_mult:.2f} (Dynamic)"

            else:  # Fallback to existing fixed multiplier logic
                self.lg.debug(
                    f"Using STANDARD fixed ATR multiplier TP/SL logic for {self.s} {signal}.",
                )
                take_profit_multiplier = self.cfg.get(
                    "take_profit_multiple", Decimal("1.0"),
                )
                stop_loss_multiplier = self.cfg.get(
                    "stop_loss_multiple", Decimal("1.5"),
                )
                take_profit_offset = atr_value * take_profit_multiplier
                stop_loss_offset = atr_value * stop_loss_multiplier
                log_tp_multiplier_str = f"{take_profit_multiplier:.2f} (Fixed)"
                log_sl_multiplier_str = f"{stop_loss_multiplier:.2f} (Fixed)"

            raw_take_profit_price: Decimal | None = None
            raw_stop_loss_price: Decimal | None = None

            if signal == "BUY":
                raw_take_profit_price = entry_price_estimate + take_profit_offset
                raw_stop_loss_price = entry_price_estimate - stop_loss_offset
            elif signal == "SELL":
                raw_take_profit_price = entry_price_estimate - take_profit_offset
                raw_stop_loss_price = entry_price_estimate + stop_loss_offset

            quantized_take_profit_price: Decimal | None = None
            quantized_stop_loss_price: Decimal | None = None

            if raw_take_profit_price is not None:
                rounding_mode_tp = ROUND_UP if signal == "BUY" else ROUND_DOWN
                if min_tick_size > Decimal("0"):
                    quantized_take_profit_price = (
                        raw_take_profit_price / min_tick_size
                    ).quantize(Decimal("1"), rounding=rounding_mode_tp) * min_tick_size
                else:
                    quantized_take_profit_price = raw_take_profit_price.quantize(
                        Decimal("1e-" + str(price_precision)), rounding=rounding_mode_tp,
                    )

            if raw_stop_loss_price is not None:
                rounding_mode_sl = ROUND_DOWN if signal == "BUY" else ROUND_UP
                if min_tick_size > Decimal("0"):
                    quantized_stop_loss_price = (
                        raw_stop_loss_price / min_tick_size
                    ).quantize(Decimal("1"), rounding=rounding_mode_sl) * min_tick_size
                else:
                    quantized_stop_loss_price = raw_stop_loss_price.quantize(
                        Decimal("1e-" + str(price_precision)), rounding=rounding_mode_sl,
                    )

            final_tp = quantized_take_profit_price
            final_sl = quantized_stop_loss_price

            if final_sl is not None and min_tick_size > Decimal("0"):
                if signal == "BUY" and final_sl >= entry_price_estimate:
                    self.lg.debug(
                        f"Adjusting BUY SL {final_sl} to be below entry {entry_price_estimate} by at least one tick. Ensuring a clear boundary.{RST}",
                    )
                    final_sl = (
                        (entry_price_estimate - min_tick_size) / min_tick_size
                    ).quantize(Decimal("1"), rounding=ROUND_DOWN) * min_tick_size
                elif signal == "SELL" and final_sl <= entry_price_estimate:
                    self.lg.debug(
                        f"Adjusting SELL SL {final_sl} to be above entry {entry_price_estimate} by at least one tick. Ensuring a clear boundary.{RST}",
                    )
                    final_sl = (
                        (entry_price_estimate + min_tick_size) / min_tick_size
                    ).quantize(Decimal("1"), rounding=ROUND_UP) * min_tick_size

            if final_tp is not None and min_tick_size > Decimal("0"):
                if signal == "BUY" and final_tp <= entry_price_estimate:
                    self.lg.warning(
                        f"{NY}BUY TP calculation non-profitable (TP {final_tp} <= Entry {entry_price_estimate}). Setting TP to None. The path to gain is blocked!{RST}",
                    )
                    final_tp = None
                elif signal == "SELL" and final_tp >= entry_price_estimate:
                    self.lg.warning(
                        f"{NY}SELL TP calculation non-profitable (TP {final_tp} >= Entry {entry_price_estimate}). Setting TP to None. The path to gain is blocked!{RST}",
                    )
                    final_tp = None

            if final_sl is not None and final_sl <= Decimal("0"):
                self.lg.error(
                    f"{NR}Stop loss calculation resulted in non-positive price ({final_sl}). Setting SL to None. The safety net vanished!{RST}",
                )
                final_sl = None
            if final_tp is not None and final_tp <= Decimal("0"):
                self.lg.warning(
                    f"{NY}Take profit calculation resulted in non-positive price ({final_tp}). Setting TP to None. The treasure turned to dust!{RST}",
                )
                final_tp = None

            tp_string = f"{final_tp:.{price_precision}f}" if final_tp else "None"
            sl_string = f"{final_sl:.{price_precision}f}" if final_sl else "None"
            self.lg.debug(
                f"Calculated TP/SL for {self.s} {signal}: EntryEst={entry_price_estimate:.{price_precision}f}, ATR={atr_value:.{price_precision + 1}f}, "
                f"TP={tp_string} (Mult: {log_tp_multiplier_str}), SL={sl_string} (Mult: {log_sl_multiplier_str}). The boundaries are set.{RST}",
            )

            return entry_price_estimate, final_tp, final_sl
        except (InvalidOperation, ValueError, TypeError) as e:
            self.lg.error(
                f"{NR}Error calculating TP/SL for {self.s} {signal} (Decimal/Type Error): {e}. A numerical distortion in the boundaries!{RST}",
                exc_info=False,
            )
            return entry_price_estimate, None, None
        except Exception as e:
            self.lg.error(
                f"{NR}Unexpected error calculating TP/SL for {self.s} {signal}: {e}. A cosmic interference in setting the path!{RST}",
                exc_info=True,
            )
            return entry_price_estimate, None, None


@retry_api_call()
def fb(
    exchange: ccxt.Exchange, currency: str, logger: logging.Logger,
) -> Decimal | None:
    """Fetch Balance: Retrieves the available balance for a specified currency.
    Handles retries and exchange-specific balance fetching (e.g., Bybit V5).
    """
    balance_info = None
    available_balance_str: str | None = None
    account_types_to_try = []
    if exchange.id == "bybit":
        account_types_to_try = ["CONTRACT", "UNIFIED"]

    # Try specific account types first
    for acct_type in account_types_to_try:
        try:
            logger.debug(
                f"Fetching balance using params={{'type': '{acct_type}'}} for {currency}. Probing a specific vault.",
            )
            balance_info = exchange.fetch_balance(params={"type": acct_type})

            # Bybit V5 specific parsing
            # The 'info' field directly contains the 'result' dict, which has a 'list' of accounts.
            # Each account in the 'list' has a 'coin' key, which can be a list (Unified) or a dict (Contract).
            if (
                "info" in balance_info
                and isinstance(balance_info["info"], dict)
                and isinstance(balance_info["info"].get("list"), list)
            ):
                for account in balance_info["info"]["list"]:
                    if isinstance(account.get("coin"), list):  # Unified account format
                        for coin_data in account["coin"]:
                            if coin_data.get("coin") == currency:
                                found_balance = (
                                    coin_data.get("availableToWithdraw")
                                    or coin_data.get("availableBalance")
                                    or coin_data.get("walletBalance")
                                )
                                if found_balance is not None:
                                    available_balance_str = str(found_balance)
                                    logger.debug(
                                        f"Found balance via Bybit V5 nested ['available...']: {available_balance_str}. Deciphering the intricate Bybit scrolls.{RST}",
                                    )
                                    break
                        if available_balance_str is not None:
                            break
                    # Single coin in list
                    elif (
                        isinstance(account.get("coin"), dict)
                        and account["coin"].get("coin") == currency
                    ):
                        found_balance = (
                            account["coin"].get("availableToWithdraw")
                            or account["coin"].get("availableBalance")
                            or account["coin"].get("walletBalance")
                        )
                        if found_balance is not None:
                            available_balance_str = str(found_balance)
                            logger.debug(
                                f"Found balance via Bybit V5 nested direct 'coin' dict: {available_balance_str}. A direct path within the nested structure.{RST}",
                            )
                        break

            if (
                available_balance_str is not None
            ):  # If found via Bybit V5 parsing, break from account type loop
                break
            # Standard CCXT format
            if (
                currency in balance_info
                and balance_info[currency].get("free") is not None
            ):
                available_balance_str = str(balance_info[currency]["free"])
                logger.debug(
                    f"Found balance via standard ['{currency}']['free']: {available_balance_str}. The most common ledger entry.{RST}",
                )
                break  # Found successfully
        except (ccxt.ExchangeError, ccxt.AuthenticationError) as e:
            logger.debug(
                f"Error fetching balance for type '{acct_type}': {e}. Trying next type/default. A small obstacle.{RST}",
            )
            continue
        except Exception as e:
            logger.warning(
                f"{NY}Unexpected error fetching balance type '{acct_type}': {e}. Trying next. A cosmic interference!{RST}",
            )
            continue

    if (
        available_balance_str is None
    ):  # If not found via specific types, try default fetch
        logger.debug(
            f"Fetching balance using default parameters for {currency}. Trying the common path.",
        )
        balance_info = exchange.fetch_balance()
        if currency in balance_info and balance_info[currency].get("free") is not None:
            available_balance_str = str(balance_info[currency]["free"])
            logger.debug(
                f"Found balance via standard ['{currency}']['free'] (default fetch): {available_balance_str}. The common ledger entry.{RST}",
            )
        elif (
            "free" in balance_info
            and currency in balance_info["free"]
            and balance_info["free"][currency] is not None
        ):
            available_balance_str = str(balance_info["free"][currency])
            logger.debug(
                f"Found balance via top-level 'free' dict (default fetch): {available_balance_str}. A simpler, older path.{RST}",
            )
        else:
            total_balance_fallback = balance_info.get(currency, {}).get("total")
            if total_balance_fallback is not None:
                logger.warning(
                    f"{NY}Using 'total' balance ({total_balance_fallback}) as fallback for available {currency} (default fetch). The free funds are hidden, but total is known.{RST}",
                )
                available_balance_str = str(total_balance_fallback)
            else:
                logger.error(
                    f"{NR}Could not determine any balance ('free' or 'total') for {currency} via default fetch. The wellspring is dry!{RST}",
                )
                logger.debug(
                    f"Full balance_info structure (default fetch): {balance_info}. The full ledger is perplexing.",
                )
                raise ccxt.ExchangeError(
                    "Balance parsing failed or data missing after default fetch",
                )

    if available_balance_str is not None:
        try:
            final_balance = Decimal(available_balance_str)
            if final_balance >= 0:
                logger.info(
                    f"{NC}Available {currency} balance: {final_balance:.4f}. The essence of your holdings is revealed!{RST}",
                )
                return final_balance
            logger.error(
                f"{NR}Parsed balance for {currency} is negative ({final_balance}). A dark omen in the ledger!{RST}",
            )
        except (InvalidOperation, ValueError, TypeError) as e:
            logger.error(
                f"{NR}Failed to convert balance string '{available_balance_str}' to Decimal for {currency}: {e}. The numerical rune is corrupted!{RST}",
            )
    raise ccxt.ExchangeError(
        "Balance parsing failed or data missing after conversion attempt.",
    )


def _gop_decimal_converter(
    value: Any, logger: logging.Logger, symbol: str, field_name: str,
) -> Decimal | None:
    """Converts a value to Decimal for gop function, treating '0', empty strings, or None as None."""
    if value is None or str(value).strip() == "":
        return None
    try:
        decimal_value = Decimal(str(value))
        if decimal_value == Decimal("0"):
            return None  # Treat Decimal('0') as None for these specific fields
        return decimal_value
    except (InvalidOperation, ValueError, TypeError) as e:
        logger.warning(
            f"{NY}gop_converter: Error converting '{field_name}' value '{value}' to Decimal for {symbol}. Error: {e}. Treating as None.{RST}",
        )
        return None


def _generate_bybit_v5_request_headers(
    api_key: str, api_secret: str, payload_str: str, recv_window: int = 10000,
) -> dict[str, str]:
    """Generates the required headers for a Bybit V5 API request."""
    # Generate timestamp in milliseconds
    timestamp_ms = str(int(time.time() * 1000))

    # Construct the pre-hash string: timestamp + api_key + recv_window + payload_str
    pre_hash_string = timestamp_ms + api_key + str(recv_window) + payload_str

    # Calculate HMAC_SHA256 signature
    signature = hmac.new(
        api_secret.encode("utf-8"), pre_hash_string.encode("utf-8"), hashlib.sha256,
    ).hexdigest()

    # Return headers dictionary
    headers = {
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-TIMESTAMP": timestamp_ms,
        "X-BAPI-RECV-WINDOW": str(recv_window),
        "X-BAPI-SIGN": signature,
        "Content-Type": "application/json",
    }
    return headers


def send_termux_sms(recipient: str, message: str, logger: logging.Logger) -> bool:
    """Sends an SMS using Termux:API."""
    if not recipient or not isinstance(recipient, str):
        logger.error(
            f"{NR}SMS sending failed: Invalid recipient number '{recipient}'. Must be a non-empty string.{RST}",
        )
        return False
    if not message or not isinstance(message, str):
        logger.error(f"{NR}SMS sending failed: Message is empty or not a string.{RST}")
        return False

    command = ["termux-sms-send", "-n", recipient, message]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=15, check=False,
        )
        if result.returncode == 0:
            logger.info(
                f'{NG}SMS sending command executed for recipient {recipient}. Message: "{message[:30]}..." (Check Termux for actual send status).{RST}',
            )
            return True
        logger.error(
            f"{NR}SMS sending command failed for recipient {recipient}. Return code: {result.returncode}{RST}",
        )
        if result.stdout:
            logger.error(f"{NR}SMS stdout: {result.stdout.strip()}{RST}")
        if result.stderr:
            logger.error(f"{NR}SMS stderr: {result.stderr.strip()}{RST}")
        return False
    except FileNotFoundError:
        logger.error(
            f"{NR}SMS sending failed: 'termux-sms-send' command not found. Ensure Termux:API is installed and configured correctly on your device.{RST}",
        )
        return False
    except subprocess.TimeoutExpired:
        logger.error(
            f"{NR}SMS sending command timed out for recipient {recipient}.{RST}",
        )
        return False
    except Exception as e:
        logger.error(
            f"{NR}An unexpected error occurred while sending SMS to {recipient}: {e}{RST}",
            exc_info=True,
        )
        return False


@retry_api_call()
def gmi(exchange: ccxt.Exchange, symbol: str, logger: logging.Logger) -> dict | None:
    """Get Market Info: Retrieves detailed market information for a given symbol.
    Reloads markets if needed and provides hints for invalid symbols.
    """
    if not exchange.markets or symbol not in exchange.markets:
        logger.info(
            f"{NB}Market info for {symbol} not loaded or symbol not found, reloading markets... Unfurling the market scrolls anew.{RST}",
        )
        exchange.load_markets(reload=True)

    if symbol not in exchange.markets:
        logger.error(
            f"{NR}Market {symbol} still not found after reloading. The symbol rune is unknown in this realm!{RST}",
        )
        if "/" in symbol:
            base, quote = symbol.split("/", 1)
            possible_usdt_pair = f"{base}/USDT:USDT"
            possible_perp_pair = f"{base}-PERP"
            possible_matches = [
                sym
                for sym in exchange.markets
                if sym.startswith(base)
                and ("PERP" in sym or ":USDT" in sym or "USD" in sym)
            ]
            if possible_usdt_pair in exchange.markets:
                logger.warning(
                    f"{NY}Did you mean '{possible_usdt_pair}'? A common variant.{RST}",
                )
            elif possible_perp_pair in exchange.markets:
                logger.warning(
                    f"{NY}Did you mean '{possible_perp_pair}'? Another possible form.{RST}",
                )
            elif possible_matches:
                logger.warning(
                    f"{NY}Possible matches found: {possible_matches[:5]}. Perhaps one of these is the true rune?{RST}",
                )
        raise ccxt.BadSymbol(f"Market {symbol} not found after reloading.")

    market_data = exchange.market(symbol)
    if market_data:
        market_type = market_data.get("type", "unknown")
        is_contract = market_data.get("contract", False) or market_type in [
            "swap",
            "future",
        ]
        contract_type_detail = "N/A"
        if is_contract:
            if market_data.get("linear"):
                contract_type_detail = "Linear"
            elif market_data.get("inverse"):
                contract_type_detail = "Inverse"
            else:
                contract_type_detail = "Unknown Contract"

        logger.debug(
            f"Market Info for {symbol}: ID={market_data.get('id')}, Base={market_data.get('base')}, Quote={market_data.get('quote')}, Type={market_type}, IsContract={is_contract}, ContractType={contract_type_detail}, Precision(Price/Amount): {market_data.get('precision', {}).get('price')}/{market_data.get('precision', {}).get('amount')}, Limits(Amount Min/Max): {market_data.get('limits', {}).get('amount', {}).get('min')}/{market_data.get('limits', {}).get('amount', {}).get('max')}, Limits(Cost Min/Max): {market_data.get('limits', {}).get('cost', {}).get('min')}/{market_data.get('limits', {}).get('cost', {}).get('max')}, Contract Size: {market_data.get('contractSize', 'N/A')}. The market's essence revealed.{RST}",
        )

        market_data["is_contract"] = is_contract
        return market_data
    raise ccxt.ExchangeError(
        f"Market dictionary unexpectedly not found for validated symbol {symbol}. A void in the market's records!",
    )


@retry_api_call()
def cps(
    balance: Decimal,
    risk_per_trade: Decimal,
    initial_stop_loss_price: Decimal,
    entry_price: Decimal,
    market_info: dict,
    exchange: ccxt.Exchange,
    logger: logging.Logger | None = None,
) -> Decimal | None:
    """Calculate Position Size: Determines the appropriate trade size based on
    available balance, risk per trade, stop loss distance, and market info.
    """
    logger = logger or logging.getLogger(__name__)
    symbol = market_info.get("symbol", "UNKNOWN_SYMBOL")
    quote_currency = market_info.get("quote", QC)
    base_currency = market_info.get("base", "BASE")
    is_contract = market_info.get("is_contract", False)
    size_unit = "Contracts" if is_contract else base_currency

    if not isinstance(balance, Decimal) or balance <= 0:
        raise ValueError(
            f"Position sizing failed ({symbol}): Invalid or zero balance ({balance}). The wellspring is empty!",
        )
    if not isinstance(risk_per_trade, Decimal) or not (
        Decimal("0") < risk_per_trade <= Decimal("1")
    ):
        raise ValueError(
            f"Position sizing failed ({symbol}): Invalid risk_per_trade ({risk_per_trade}). Must be between 0 (exclusive) and 1 (inclusive). The risk rune is malformed!",
        )
    if not isinstance(initial_stop_loss_price, Decimal) or initial_stop_loss_price <= 0:
        raise ValueError(
            f"Position sizing failed ({symbol}): Invalid initial_stop_loss_price ({initial_stop_loss_price}). The safety boundary is illusory!",
        )
    if not isinstance(entry_price, Decimal) or entry_price <= 0:
        raise ValueError(
            f"Position sizing failed ({symbol}): Invalid entry_price ({entry_price}). The entry point is void!",
        )
    if initial_stop_loss_price == entry_price:
        raise ValueError(
            f"Position sizing failed ({symbol}): Stop loss price cannot be equal to entry price. The safety net is too close!",
        )
    if "limits" not in market_info or "precision" not in market_info:
        raise ValueError(
            f"Position sizing failed ({symbol}): Market info missing 'limits' or 'precision'. The market's constraints are unknown!",
        )

    risk_amount_quote = balance * risk_per_trade
    stop_loss_distance = abs(entry_price - initial_stop_loss_price)
    if stop_loss_distance <= 0:
        raise ValueError(
            f"Position sizing failed ({symbol}): Stop loss distance is zero or negative ({stop_loss_distance}). The risk is immeasurable!",
        )

    contract_size = Decimal(str(market_info.get("contractSize", "1")))
    if contract_size <= 0:
        logger.warning(
            f"{NY}Invalid contract size '{market_info.get('contractSize', '1')}' for {symbol}, using 1. The contract's scale is unclear!{RST}",
        )
        contract_size = Decimal("1")

    calculated_size: Decimal | None = None
    if market_info.get("linear", True) or not is_contract:
        denominator = stop_loss_distance * contract_size
        if denominator > 0:
            calculated_size = risk_amount_quote / denominator
        else:
            raise ValueError(
                f"Position sizing failed ({symbol}): Denominator zero/negative in size calculation (SL Dist: {stop_loss_distance}, ContractSize: {contract_size}). A division by zero in the arcane arts!",
            )
    else:
        raise NotImplementedError(
            f"Inverse contract sizing not fully implemented. Aborting sizing for {symbol}. The inverse spell is not yet mastered!",
        )

    if calculated_size is None or calculated_size <= 0:
        raise ValueError(
            f"Initial position size calculation resulted in zero or negative: {calculated_size}. RiskAmt={risk_amount_quote:.4f}, SLDist={stop_loss_distance}, ContractSize={contract_size}. The calculated magnitude is void!",
        )

    logger.info(
        f"{NC}Position Sizing ({symbol}): Balance={balance:.2f} {quote_currency}, Risk={risk_per_trade:.2%}, RiskAmt={risk_amount_quote:.4f} {quote_currency}. Balancing the scales of fortune.{RST}",
    )
    logger.info(
        f"{NC}  Entry={entry_price}, SL={initial_stop_loss_price}, SL Dist={stop_loss_distance}. Defining the journey's parameters.{RST}",
    )
    logger.info(
        f"{NC}  ContractSize={contract_size}, Initial Calculated Size = {calculated_size:.8f} {size_unit}. The raw power of the spell.{RST}",
    )

    limits = market_info.get("limits", {})
    amount_limits = limits.get("amount", {})
    cost_limits = limits.get("cost", {})

    min_amount = (
        Decimal(str(amount_limits.get("min")))
        if amount_limits.get("min") is not None
        else Decimal("0")
    )
    max_amount = (
        Decimal(str(amount_limits.get("max")))
        if amount_limits.get("max") is not None
        else Decimal("inf")
    )
    min_cost = (
        Decimal(str(cost_limits.get("min")))
        if cost_limits.get("min") is not None
        else Decimal("0")
    )
    max_cost = (
        Decimal(str(cost_limits.get("max")))
        if cost_limits.get("max") is not None
        else Decimal("inf")
    )

    adjusted_size = calculated_size

    if adjusted_size < min_amount:
        logger.warning(
            f"{NY}Calculated size {calculated_size:.8f} is below min amount {min_amount}. Adjusting to min amount. The spell's magnitude is too small!{RST}",
        )
        adjusted_size = min_amount
    elif adjusted_size > max_amount:
        logger.warning(
            f"{NY}Calculated size {calculated_size:.8f} exceeds max amount {max_amount}. Adjusting to max amount. The spell's magnitude is too vast!{RST}",
        )
        adjusted_size = max_amount

    estimated_cost: Decimal | None = None
    if market_info.get("linear", True) or not is_contract:
        estimated_cost = adjusted_size * entry_price * contract_size
    elif entry_price > 0:
        estimated_cost = adjusted_size * contract_size / entry_price
    else:
        raise ValueError(
            f"Cannot estimate cost for inverse contract {symbol}: Entry price is zero. The cost is immeasurable!",
        )

    logger.debug(
        f"  Cost Check: Adjusted Size={adjusted_size:.8f}, Estimated Cost={estimated_cost:.4f} {quote_currency}. Verifying the cost of the enchantment.{RST}",
    )

    if min_cost > 0 and estimated_cost < min_cost:
        logger.warning(
            f"{NY}Estimated cost {estimated_cost:.4f} is below min cost {min_cost}. Attempting to increase size. The offering is too small!{RST}",
        )
        required_size_for_min_cost: Decimal | None = None
        if market_info.get("linear", True) or not is_contract:
            denominator = entry_price * contract_size
            if denominator > 0:
                required_size_for_min_cost = min_cost / denominator
        elif contract_size > 0:
            required_size_for_min_cost = min_cost * entry_price / contract_size
        else:
            raise ValueError(
                "Cannot calculate required size for min cost: Contract size is zero.",
            )

        if required_size_for_min_cost is None:
            raise ValueError(
                "Cannot calculate required size for min cost: Calculation failed.",
            )

        logger.info(
            f"{NC}  Required size to meet min cost: {required_size_for_min_cost:.8f} {size_unit}. The new magnitude of the spell.{RST}",
        )

        if required_size_for_min_cost > max_amount:
            raise ValueError(
                f"Cannot meet min cost {min_cost} without exceeding max amount limit {max_amount}. Aborted. The offering is too vast!",
            )

        logger.info(
            f"{NC}  Adjusting size to meet min cost: {adjusted_size:.8f} -> {required_size_for_min_cost:.8f}. Recalibrating the enchantment.{RST}",
        )
        adjusted_size = required_size_for_min_cost

    elif max_cost > 0 and estimated_cost > max_cost:
        logger.warning(
            f"{NY}Estimated cost {estimated_cost:.4f} exceeds max cost {max_cost}. Reducing size. The offering is too grand!{RST}",
        )
        allowed_size_for_max_cost: Decimal | None = None
        if market_info.get("linear", True) or not is_contract:
            denominator = entry_price * contract_size
            if denominator > 0:
                allowed_size_for_max_cost = max_cost / denominator
            else:
                raise ValueError(
                    "Cannot calculate max size for max cost: Denominator zero/negative.",
                )
        elif contract_size > 0:
            allowed_size_for_max_cost = max_cost * entry_price / contract_size
        else:
            raise ValueError(
                "Cannot calculate max size for max cost: Contract size is zero.",
            )

        if allowed_size_for_max_cost is None:
            raise ValueError(
                "Cannot calculate max size for max cost: Calculation failed.",
            )

        logger.info(
            f"{NC}  Reduced size allowed by max cost: {allowed_size_for_max_cost:.8f} {size_unit}. The limited power of the spell.{RST}",
        )

        if allowed_size_for_max_cost < min_amount:
            raise ValueError(
                f"Size reduced for max cost ({allowed_size_for_max_cost:.8f}) is below min amount {min_amount}. Aborted. The reduced offering is too small!",
            )

        logger.info(
            f"{NC}  Adjusting size to meet max cost: {adjusted_size:.8f} -> {allowed_size_for_max_cost:.8f}. Reining in the enchantment.{RST}",
        )
        adjusted_size = allowed_size_for_max_cost

    final_size: Decimal | None = None
    try:
        final_size = _pmap(adjusted_size, market_info, logger)
        if final_size is None:
            raise ValueError("Manual amount precision failed")

        logger.info(
            f"{NC}Applied amount precision/step size: {adjusted_size:.8f} -> {final_size} {size_unit}. Honing the spell's exactness.{RST}",
        )
    except Exception as e:
        raise ValueError(f"Error during size formatting: {e}")

    if final_size is None or final_size <= 0:
        raise ValueError(
            f"Position size became zero or negative ({final_size}) after adjustments. Aborted. The spell's power dissipated!",
        )

    final_cost: Decimal | None = None
    if market_info.get("linear", True) or not is_contract:
        final_cost = final_size * entry_price * contract_size
    elif entry_price > 0:
        final_cost = final_size * contract_size / entry_price
    else:
        final_cost = None

    if final_cost is not None and min_cost > 0 and final_cost < min_cost:
        raise ValueError(
            f"Final size {final_size} results in cost {final_cost:.4f} which is below minimum cost {min_cost}. Exchange limits conflict? Aborted. The final offering is insufficient!",
        )

    logger.info(
        f"{NG}Final calculated position size for {symbol}: {final_size} {size_unit}. The spell's true magnitude is ready!{RST}",
    )
    return final_size


def _pmap(
    amount_decimal: Decimal, market_info: dict, logger: logging.Logger,
) -> Decimal | None:
    """Precision Map (Manual Amount Precision): A fallback function to manually apply
    amount precision rules if CCXT's `amount_to_precision` fails or lacks desired features.
    """
    symbol = market_info.get("symbol", "UNKNOWN_SYMBOL")
    amount_precision_value = market_info.get("precision", {}).get("amount")

    if amount_precision_value is None:
        logger.warning(
            f"{NY}Manual amount precision: amountPrecision is None for {symbol}. Returning original amount. The precision guide is missing!{RST}",
        )
        return amount_decimal

    try:
        if isinstance(amount_precision_value, int):
            rounding_factor = Decimal("1e-" + str(amount_precision_value))
            final_amount = amount_decimal.quantize(rounding_factor, rounding=ROUND_DOWN)
            logger.debug(
                f"Manual amount precision (decimal places): {amount_decimal} -> {final_amount}. Truncating to the exact digit.{RST}",
            )
            return final_amount
        if isinstance(amount_precision_value, (float, str)):
            amount_step_size = Decimal(str(amount_precision_value))
            if amount_step_size > 0:
                # Determine the number of decimal places for the step size
                step_decimal_places = (
                    abs(amount_step_size.normalize().as_tuple().exponent)
                    if amount_step_size.is_normal()
                    else 0
                )

                # Quantize the amount to the step size's precision, then perform floor division
                # This ensures the result is a multiple of the step size and truncated
                quantized_amount = amount_decimal.quantize(
                    Decimal("1e-" + str(step_decimal_places)), rounding=ROUND_DOWN,
                )
                final_amount = (quantized_amount // amount_step_size) * amount_step_size

                logger.debug(
                    f"Manual amount precision (step size): {amount_decimal} -> {final_amount}. Aligning to the market's smallest step.{RST}",
                )
                return final_amount
            logger.warning(
                f"{NY}Manual amount precision: Amount step size is zero or invalid ({amount_step_size}) for {symbol}. Returning original amount. The step is immeasurable!{RST}",
            )
            return amount_decimal
        logger.warning(
            f"{NY}Manual amount precision: Unknown type for amountPrecision '{amount_precision_value}' for {symbol}. Returning original amount. The precision rune is of an unknown script!{RST}",
        )
        return amount_decimal
    except (InvalidOperation, ValueError, TypeError) as e:
        logger.error(
            f"{NR}Error during manual amount precision for {symbol}: {e}. Returning original amount. A numerical distortion in the shaping!{RST}",
            exc_info=True,
        )
        return amount_decimal
    except Exception as e:
        logger.error(
            f"{NR}Unexpected error during manual amount precision for {symbol}: {e}. Returning original amount. A cosmic interference!{RST}",
            exc_info=True,
        )
        return amount_decimal


@retry_api_call()
def gop(
    exchange: ccxt.Exchange, symbol: str, market_info: dict, logger: logging.Logger,
) -> dict | None:
    """Get Open Position: Fetches and processes details of an active open position for a given symbol.
    Includes retry logic.
    """
    logger.debug(
        f"Fetching positions for symbol: {symbol}. Scrying for active stances.",
    )
    positions_list: list[dict] = []

    if not exchange.has.get("fetchPositions"):
        logger.error(
            f"{NR}Exchange {exchange.id} does not support fetchPositions. This realm offers no glimpse into its immediate desires!{RST}",
        )
        return None

    market_id = market_info.get("id")
    if not market_id:
        logger.error(
            f"{NR}Cannot fetch position: Market ID missing for {symbol}. The market's identity is unknown!{RST}",
        )
        return None

    # Bybit V5 requires category for fetch_positions
    category = "linear" if market_info.get("linear") else "inverse"
    params = {"category": category}

    positions_list = exchange.fetch_positions([market_id], params=params)
    logger.debug(
        f"Fetched single symbol position data for {symbol} (ID: {market_id}). Count: {len(positions_list)}. A direct query to the market's memory.{RST}",
    )

    active_position_data = None
    amount_precision_value = market_info.get("precision", {}).get("amount")

    try:
        if isinstance(amount_precision_value, (float, str)):
            amount_step_size = Decimal(str(amount_precision_value))
            size_threshold = (
                amount_step_size / Decimal("2")
                if amount_step_size > 0
                else Decimal("1e-9")
            )
        elif isinstance(amount_precision_value, int):
            size_threshold = Decimal("1e-" + str(amount_precision_value + 1))
        else:
            size_threshold = Decimal("1e-9")
    except:
        size_threshold = Decimal("1e-9")
    logger.debug(
        f"Using position size threshold: {size_threshold} for {symbol}. Defining the minimum significant amount.{RST}",
    )

    for position in positions_list:
        position_size_str = None
        if position.get("contracts") is not None:
            position_size_str = str(position["contracts"])
        elif (
            isinstance(position.get("info"), dict)
            and position["info"].get("size") is not None
        ):
            position_size_str = str(position["info"]["size"])

        if position_size_str is None:
            logger.debug(
                f"Skipping position entry, could not determine size: {position}. An incomplete record.{RST}",
            )
            continue

        try:
            position_size_decimal = Decimal(position_size_str)
            if abs(position_size_decimal) > size_threshold:
                active_position_data = position
                logger.debug(
                    f"Found potential active position entry for {symbol} with size {position_size_decimal}. A significant stance detected.{RST}",
                )
                break
        except (InvalidOperation, ValueError, TypeError) as parse_error:
            logger.warning(
                f"{NY}Could not parse position size '{position_size_str}' for {symbol}: {parse_error}. The size rune is corrupted!{RST}",
            )
            continue

    if active_position_data:
        try:
            size_decimal = Decimal(
                str(
                    active_position_data.get(
                        "contracts",
                        active_position_data.get("info", {}).get("size", "0"),
                    ),
                ),
            )
            active_position_data["contractsDecimal"] = size_decimal

            side = active_position_data.get("side")
            if side not in ["long", "short"]:
                if size_decimal > size_threshold:
                    side = "long"
                elif size_decimal < -size_threshold:
                    side = "short"
                else:
                    logger.warning(
                        f"{NY}Position size {size_decimal} near zero for {symbol}, cannot reliably determine side. Returning None. The stance is ambiguous!{RST}",
                    )
                    return None
                active_position_data["side"] = side
                logger.debug(
                    f"Inferred position side as '{side}' based on size {size_decimal}. Deciphering the direction.{RST}",
                )

            entry_price_raw = active_position_data.get(
                "entryPrice",
            ) or active_position_data.get("info", {}).get("avgPrice")
            active_position_data["entryPriceDecimal"] = (
                Decimal(str(entry_price_raw)) if entry_price_raw else None
            )

            info_dict = active_position_data.get("info", {})

            # Retrieve raw values
            raw_sl = active_position_data.get("stopLossPrice") or info_dict.get(
                "stopLoss",
            )
            raw_tp = active_position_data.get("takeProfitPrice") or info_dict.get(
                "takeProfit",
            )
            raw_tsl_value = info_dict.get("trailingStop")
            raw_tsl_activation = info_dict.get("activePrice")

            # Convert using the helper
            active_position_data["stopLossPrice"] = _gop_decimal_converter(
                raw_sl, logger, symbol, "stopLossPrice",
            )
            active_position_data["takeProfitPrice"] = _gop_decimal_converter(
                raw_tp, logger, symbol, "takeProfitPrice",
            )
            active_position_data["trailingStopLossValue"] = _gop_decimal_converter(
                raw_tsl_value, logger, symbol, "trailingStopLossValue",
            )
            active_position_data["trailingStopActivationPrice"] = (
                _gop_decimal_converter(
                    raw_tsl_activation, logger, symbol, "trailingStopActivationPrice",
                )
            )

            timestamp_ms = active_position_data.get("timestamp") or info_dict.get(
                "updatedTime",
            )
            active_position_data["timestamp_ms"] = timestamp_ms

            def format_log_value(value_raw, is_price=True, is_size=False):
                if (
                    value_raw is None
                    or str(value_raw).strip() == ""
                    or str(value_raw) == "0"
                ):
                    return "N/A"
                try:
                    decimal_value = Decimal(str(value_raw))
                    if is_size:
                        # Use price precision for size display clarity
                        amount_precision_for_log = TA.gpp(market_info, logger)
                        return f"{abs(decimal_value):.{amount_precision_for_log}f}"
                    if is_price:
                        price_prec = TA.gpp(market_info, logger)
                        return f"{decimal_value:.{price_prec}f}"
                    return f"{decimal_value:.4f}"
                except:
                    return str(value_raw)

            entry_price_formatted = format_log_value(
                active_position_data.get("entryPriceDecimal"),
            )
            contract_size_formatted = format_log_value(size_decimal, is_size=True)
            liquidation_price_formatted = format_log_value(
                active_position_data.get("liquidationPrice"),
            )
            leverage_raw = active_position_data.get(
                "leverage", info_dict.get("leverage"),
            )
            leverage_formatted = (
                f"{Decimal(str(leverage_raw)):.1f}x"
                if leverage_raw is not None
                else "N/A"
            )
            unrealized_pnl_formatted = format_log_value(
                active_position_data.get("unrealizedPnl"), is_price=False,
            )
            stop_loss_price_formatted = format_log_value(
                active_position_data.get("stopLossPrice"),
            )
            take_profit_price_formatted = format_log_value(
                active_position_data.get("takeProfitPrice"),
            )
            trailing_sl_distance_formatted = format_log_value(
                active_position_data.get("trailingStopLossValue"), is_price=False,
            )
            trailing_sl_activation_formatted = format_log_value(
                active_position_data.get("trailingStopActivationPrice"),
            )

            logger.info(
                f"{NG}Active {side.upper()} position found ({symbol}):{RST} Size={contract_size_formatted}, Entry={entry_price_formatted}, Liq={liquidation_price_formatted}, Lev={leverage_formatted}, PnL={unrealized_pnl_formatted}, SL={stop_loss_price_formatted}, TP={take_profit_price_formatted}, TSL(Dist/Act): {trailing_sl_distance_formatted}/{trailing_sl_activation_formatted}. The bot's current stance is clear!{RST}",
            )
            logger.debug(
                f"Full position details for {symbol}: {active_position_data}. The complete position rune.{RST}",
            )
            return active_position_data
        except Exception as parse_error:
            raise ccxt.ExchangeError(
                f"Error processing active position details for {symbol}: {parse_error}. The flawed position rune.",
            )
    else:
        logger.info(
            f"{NB}No active open position found for {symbol}. The market holds no open commitments.{RST}",
        )
        return None


# Modified slc to handle "leverage not modified" gracefully
@retry_api_call()
def slc(
    exchange: ccxt.Exchange,
    symbol: str,
    leverage: int,
    market_info: dict,
    logger: logging.Logger,
) -> bool:
    """Set Leverage: Attempts to set the leverage for a given symbol.
    Only applies to contract markets. Handles exchange-specific parameters.
    """
    is_contract = market_info.get("is_contract", False)
    if not is_contract:
        logger.info(
            f"{NB}Leverage setting skipped for {symbol} (Not a contract market). Leverage only applies to amplified contracts.{RST}",
        )
        return True

    if not isinstance(leverage, int) or leverage <= 0:
        raise ValueError(
            f"Leverage setting skipped for {symbol}: Invalid leverage value ({leverage}). Must be a positive integer. The amplification rune is malformed!",
        )

    if not exchange.has.get("setLeverage"):
        if not exchange.has.get("setMarginMode"):
            logger.error(
                f"{NR}Exchange {exchange.id} does not support setLeverage or setMarginMode via CCXT. Cannot set leverage. The exchange offers no amplification!{RST}",
            )
            return False
        logger.warning(
            f"{NY}Exchange {exchange.id} might use setMarginMode for leverage. Proceeding with setLeverage which may internally map. A subtle difference in the amplification spell.{RST}",
        )

    logger.info(
        f"{NB}Attempting to set leverage for {symbol} to {leverage}x... Amplifying market power!{RST}",
    )
    params = {}
    if "bybit" in exchange.id.lower():
        leverage_str = str(leverage)
        params = {
            "buyLeverage": leverage_str,
            "sellLeverage": leverage_str,
            # Add category for Bybit V5
            "category": "linear" if market_info.get("linear") else "inverse",
        }
        logger.debug(
            f"Using Bybit V5 params for set_leverage: {params}. Specific incantations for Bybit.{RST}",
        )

    try:
        response = exchange.set_leverage(
            leverage=leverage, symbol=symbol, params=params,
        )
        logger.debug(
            f"Set leverage raw response for {symbol}: {response}. The echo of the amplification spell.{RST}",
        )
        logger.info(
            f"{NG}Leverage for {symbol} set/requested to {leverage}x (Check position details for confirmation). The market's power is now amplified!{RST}",
        )
        return True
    except (
        ccxt.BadRequest
    ) as e:  # More specific catch for errors that might contain retCode
        error_message = str(e).lower().replace(" ", "")
        # Bybit V5 error code for "leverage not modified" is 110043.
        # The message might also contain "leveragenotmodified" or similar.
        is_leverage_not_modified_error = "bybit" in exchange.id.lower() and (
            '"retcode":110043' in error_message
            or '"retmsg":"leveragenotmodified"' in error_message
            or
            # A simpler check just in case formatting varies
            "leveragenotmodified" in error_message
        )
        if is_leverage_not_modified_error:
            # Attempt to extract the original retMsg if possible, otherwise use generic message
            original_ret_msg = "Leverage not modified"
            try:
                # Example: bybit {"retCode":110043,"retMsg":"Leverage not modified"}
                # This parsing is brittle; a regex might be better but adds complexity.
                if '"retmsg":"' in str(e).lower():
                    original_ret_msg = (
                        str(e).lower().split('"retmsg":"')[1].split('"')[0]
                    )
            except Exception:
                pass  # Stick to generic if parsing fails

            logger.info(
                f"{NY}Leverage for {symbol} is already set to {leverage}x (Exchange confirmed: {original_ret_msg}). No modification needed. The amplification is already active.{RST}",
            )
            return True  # Treat as success
        # For any other BadRequest, re-raise it for the retry_api_call decorator to handle
        logger.warning(
            f"{NY}Unhandled BadRequest in slc for {symbol}: {e}. Re-raising.{RST}",
        )
        raise
    except (
        ccxt.ExchangeError
    ) as e:  # Catch other exchange errors that are not BadRequest
        logger.warning(
            f"{NY}ExchangeError in slc for {symbol} (not BadRequest): {e}. Re-raising.{RST}",
        )
        raise  # Re-raise for retry or general handling


@retry_api_call()
def pt(
    exchange: ccxt.Exchange,
    symbol: str,
    trade_side: str,
    position_size: Decimal,
    market_info: dict,
    logger: logging.Logger | None = None,
    order_type: str = "market",
    limit_price: Decimal | None = None,
    reduce_only: bool = False,
    extra_params: dict | None = None,
) -> dict | None:
    """Place Trade: Executes a trade order (market or limit) on the exchange.
    Handles amount precision, price precision, and various error conditions.
    """
    logger = logger or logging.getLogger(__name__)
    side_lower = "buy" if trade_side == "BUY" else "sell"
    is_contract = market_info.get("is_contract", False)
    size_unit = "Contracts" if is_contract else market_info.get("base", "")
    action_description = "Close/Reduce" if reduce_only else "Open/Increase"

    if not isinstance(position_size, Decimal) or position_size <= 0:
        raise ValueError(
            f"Trade aborted ({symbol} {side_lower} {action_description}): Invalid or non-positive position size ({position_size}). The quantity rune is void!",
        )

    formatted_amount_float: float | None = None
    try:
        final_size_decimal = _pmap(position_size, market_info, logger)
        if final_size_decimal is None:
            raise ValueError("Amount precision formatting failed.")
        formatted_amount_float = float(final_size_decimal)
    except Exception as e:
        raise ValueError(f"Failed to format/convert size {position_size}: {e}")

    if formatted_amount_float is None or formatted_amount_float <= 0:
        raise ValueError(
            f"Trade aborted ({symbol} {side_lower} {action_description}): Position size became zero or negative after precision formatting ({formatted_amount_float}). Original: {position_size}. The quantity rune became void!",
        )

    formatted_price_float: float | None = None
    if order_type == "limit":
        if not isinstance(limit_price, Decimal) or limit_price <= 0:
            raise ValueError(
                f"Trade aborted ({symbol} {side_lower} {action_description}): Limit order requested but invalid limit_price ({limit_price}) provided. The price rune is invalid!",
            )
        try:
            formatted_price_str = exchange.price_to_precision(
                symbol, float(limit_price),
            )
            formatted_price_float = float(Decimal(formatted_price_str))
            if formatted_price_float <= 0:
                raise ValueError("Formatted limit price is non-positive")
        except Exception as e:
            raise ValueError(
                f"Failed to format/validate limit price {limit_price}: {e}",
            )

    order_params = {"reduceOnly": reduce_only}
    if extra_params:
        order_params.update(extra_params)

    if reduce_only and order_type == "market":
        order_params["timeInForce"] = "IOC"

    # Add category for Bybit V5 API
    if "bybit" in exchange.id.lower():
        order_params["category"] = "linear" if market_info.get("linear") else "inverse"

    logger.info(
        f"{NB}Attempting to place {action_description} {side_lower.upper()} {order_type.upper()} order for {symbol}: Casting the trade spell!{RST}",
    )
    logger.info(f"{NB}  Size: {formatted_amount_float} {size_unit}{RST}")
    if order_type == "limit":
        logger.info(f"{NB}  Limit Price: {formatted_price_float}{RST}")
    logger.info(f"{NB}  ReduceOnly: {reduce_only}{RST}")
    logger.info(f"{NB}  Params: {order_params}. The specific incantations.{RST}")

    order_response: dict | None = None
    if order_type == "market":
        order_response = exchange.create_order(
            symbol=symbol,
            type="market",
            side=side_lower,
            amount=formatted_amount_float,
            params=order_params,
        )
    elif order_type == "limit":
        order_response = exchange.create_order(
            symbol=symbol,
            type="limit",
            side=side_lower,
            amount=formatted_amount_float,
            price=formatted_price_float,
            params=order_params,
        )
    else:
        raise ValueError(
            f"Unsupported order type '{order_type}' in place_trade function. The order spell is unknown!",
        )

    if order_response:
        order_id = order_response.get("id", "N/A")
        order_status = order_response.get("status", "N/A")
        filled_amount = order_response.get("filled")
        average_price = order_response.get("average")

        logger.info(
            f"{NG}{action_description} Trade Placed Successfully! The spell was cast!{RST}",
        )
        logger.info(f"{NG}  Order ID: {order_id}, Initial Status: {order_status}{RST}")
        if filled_amount is not None and filled_amount > 0:
            logger.info(f"{NG}  Filled Amount: {filled_amount}{RST}")
        if average_price:
            logger.info(f"{NG}  Average Fill Price: {average_price}{RST}")
        logger.debug(
            f"Raw order response ({symbol} {side_lower} {action_description}): {order_response}. The echo of the completed ritual.{RST}",
        )
        return order_response
    raise ccxt.ExchangeError(
        f"Order placement call returned None without raising an exception for {symbol}. The spell yielded no result!",
    )


@retry_api_call()
def spp(
    exchange: ccxt.Exchange,
    symbol: str,
    market_info: dict,
    position_info: dict,
    logger: logging.Logger,
    stop_loss_price: Decimal | None = None,
    take_profit_price: Decimal | None = None,
    trailing_stop_distance: Decimal | None = None,
    trailing_stop_activation_price: Decimal | None = None,
) -> dict[str, Any]:
    """Revised spp: This function will NO LONGER attempt to set SL/TP orders for Bybit
    if exchange.set_trading_stop() is considered unreliable/unavailable.
    Instead, it primarily acts as a parameter validation and structuring step.
    The actual setting of SL/TP/TSL for Bybit must be done via direct Bybit V5 API calls
    (e.g., using exchange.private_post_position_set_trading_stop), likely from stsl or _mp.
    This function will return the intended parameters for the caller to use.
    """
    protection_result: dict[str, Any] = {
        # Will be set to True if inputs are valid, but no orders placed by this func.
        "success": False,
        "stopLoss": stop_loss_price
        if isinstance(stop_loss_price, Decimal) and stop_loss_price > 0
        else None,
        "takeProfit": take_profit_price
        if isinstance(take_profit_price, Decimal) and take_profit_price > 0
        else None,
        "trailingStopDistance": trailing_stop_distance
        if isinstance(trailing_stop_distance, Decimal) and trailing_stop_distance > 0
        else None,
        "trailingStopActivationPrice": trailing_stop_activation_price
        if isinstance(trailing_stop_activation_price, Decimal)
        and trailing_stop_activation_price > 0
        else None,
        "stopLossOrder": None,  # Explicitly None as this function won't place it
        "takeProfitOrder": None,  # Explicitly None
    }

    logger.info(
        f"{NB}spp: Received request for {symbol}. SL: {stop_loss_price}, TP: {take_profit_price}, TSL Dist: {trailing_stop_distance}, TSL Act: {trailing_stop_activation_price}.{RST}",
    )
    logger.warning(
        f"{NY}spp: This function is now a parameter validator/structurer due to 'set_trading_stop' being bypassed. It will NOT place SL/TP orders itself for Bybit. The caller is responsible for using appropriate Bybit V5 API methods (e.g., private_post_position_set_trading_stop).{RST}",
    )

    if not market_info.get("is_contract", False):
        logger.warning(
            f"{NY}spp: Protections are for contract markets. {symbol} is not a contract.{RST}",
        )
        # Still return success true as no action was expected from this function for non-contracts.
        protection_result["success"] = True
        return protection_result

    if not position_info:
        logger.error(
            f"{NR}spp: Cannot structure protection parameters for {symbol}: Missing position information.{RST}",
        )
        return protection_result  # Success remains False

    position_side = position_info.get("side")
    if position_side not in ["long", "short"]:
        logger.error(
            f"{NR}spp: Invalid or missing position side ('{position_side}') for {symbol}.{RST}",
        )
        return protection_result  # Success remains False

    # Basic validation of inputs
    has_any_protection = any(
        [
            protection_result["stopLoss"],
            protection_result["takeProfit"],
            protection_result["trailingStopDistance"]
            and protection_result["trailingStopActivationPrice"],
        ],
    )

    if not has_any_protection:
        logger.info(
            f"{NB}spp: No valid protection parameters provided for {symbol}. No action indicated.{RST}",
        )
        # No action needed is a form of success here
        protection_result["success"] = True
        return protection_result

    # If we reach here, parameters are present and seem valid enough to pass back.
    # The 'success' flag now means "parameters were valid to pass to a dedicated Bybit API call function".
    protection_result["success"] = True
    logger.info(
        f"{NB}spp: Parameters for {symbol} validated. Caller should use direct Bybit API methods. Result: {protection_result}{RST}",
    )
    return protection_result


@retry_api_call()
def stsl(
    exchange: ccxt.Exchange,
    symbol: str,
    market_info: dict,
    position_info: dict,
    config: dict[str, Any],
    logger: logging.Logger,
    fixed_stop_loss_price: Decimal | None = None,
    take_profit_price_target: Decimal | None = None,
    attempt_tsl: bool = True,
) -> bool:
    """Consolidated protection setter for Bybit using direct HTTP POST request to /v5/position/set-trading-stop.
    Sets TSL, Fixed SL, and/or Fixed TP based on provided parameters.
    - If attempt_tsl is True and TSL is enabled in config, TSL parameters are calculated and sent.
    - If attempt_tsl is False or TSL is disabled, fixed_stop_loss_price is used if provided.
    - take_profit_price_target is always applied if provided.
    """
    trade_record = tt.open_trades.get(symbol)
    if not trade_record:
        logger.error(
            f"{NR}stsl: No open trade record found for {symbol}. Cannot set protections.{RST}",
        )
        return False

    # Determine API Host
    if config.get("use_sandbox", True):
        base_url = "https://api-testnet.bybit.com"
    else:
        base_url = "https://api.bybit.com"
    endpoint_url = f"{base_url}/v5/position/set-trading-stop"

    params_to_set: dict[str, Any] = {
        "category": "linear" if market_info.get("linear", True) else "inverse",
        # Ensure this is the exchange-specific ID like 'BTCUSDT'
        "symbol": market_info.get("id"),
        "positionIdx": position_info.get("info", {}).get("positionIdx", 0),
        # Get from config or default
        "slTriggerBy": config.get("slTriggerBy", "LastPrice"),
        # Get from config or default
        "tpTriggerBy": config.get("tpTriggerBy", "LastPrice"),
        # Defaulting to Partial, consider 'Full' if SL/TP should cover entire position
        "tpslMode": "Partial",
    }

    price_precision = TA.gpp(market_info, logger)
    min_tick_size = TA.gmts(market_info, logger)

    should_set_tsl = False
    calculated_tsl_distance: Decimal | None = None
    calculated_tsl_activation_price: Decimal | None = None

    if attempt_tsl and config.get("enable_trailing_stop", False):
        try:
            callback_rate = config.get("trailing_stop_callback_rate", DIP["psar_af"])
            activation_percentage = config.get(
                "trailing_stop_activation_percentage", DIP["psar_af"],
            )

            if not (
                isinstance(callback_rate, Decimal)
                and isinstance(activation_percentage, Decimal)
                and callback_rate > 0
                and activation_percentage >= 0
            ):
                logger.error(
                    f"{NR}stsl: Invalid TSL config. Callback: {callback_rate}, Activation Pct: {activation_percentage}. Skipping TSL.{RST}",
                )
            else:
                entry_price = position_info.get(
                    "entryPriceDecimal", trade_record.entry_price,
                )  # Prefer live position info
                pos_side = position_info.get("side", trade_record.side)

                if not entry_price or entry_price <= 0 or not pos_side:
                    logger.error(
                        f"{NR}stsl: Missing entry price/side for TSL calc. Entry: {entry_price}, Side: {pos_side}. Skipping TSL.{RST}",
                    )
                else:
                    if pos_side == "long":
                        calculated_tsl_activation_price = entry_price * (
                            Decimal("1") + activation_percentage
                        )
                    else:
                        calculated_tsl_activation_price = entry_price * (
                            Decimal("1") - activation_percentage
                        )

                    if calculated_tsl_activation_price <= 0:
                        logger.error(
                            f"{NR}stsl: Invalid TSL activation price ({calculated_tsl_activation_price}). Skipping TSL.{RST}",
                        )
                    else:
                        calculated_tsl_activation_price = (
                            calculated_tsl_activation_price.quantize(
                                min_tick_size
                                if min_tick_size > 0
                                else Decimal(f"1e-{price_precision}"),
                                rounding=ROUND_HALF_EVEN,
                            )
                        )

                        calculated_tsl_distance = callback_rate
                        if not (
                            isinstance(calculated_tsl_distance, Decimal)
                            and calculated_tsl_distance > 0
                        ):
                            logger.error(
                                f"{NR}stsl: Invalid TSL distance (from callback_rate): {calculated_tsl_distance}. Skipping TSL.{RST}",
                            )
                            calculated_tsl_activation_price = None
                        else:
                            calculated_tsl_distance = calculated_tsl_distance.quantize(
                                min_tick_size
                                if min_tick_size > 0
                                else Decimal(f"1e-{price_precision}"),
                            )
                            if calculated_tsl_distance <= 0:
                                calculated_tsl_distance = min_tick_size
                            should_set_tsl = True
        except Exception as e:
            logger.error(
                f"{NR}stsl: Error during TSL param calculation for {symbol}: {e}. Skipping TSL.{RST}",
                exc_info=True,
            )
            should_set_tsl = False

    current_fixed_sl_on_exchange = position_info.get("stopLossPrice")
    current_tp_on_exchange = position_info.get("takeProfitPrice")
    current_tsl_dist_on_exchange = position_info.get("trailingStopLossValue")
    current_tsl_act_on_exchange = position_info.get("trailingStopActivationPrice")

    if should_set_tsl and calculated_tsl_distance and calculated_tsl_activation_price:
        params_to_set["trailingStop"] = str(calculated_tsl_distance)
        params_to_set["activePrice"] = str(calculated_tsl_activation_price)
        params_to_set["stopLoss"] = "0"
        logger.info(
            f"{NB}stsl: Preparing to set TSL for {symbol}. Activation: {calculated_tsl_activation_price}, Distance: {calculated_tsl_distance}. Fixed SL will be cleared.{RST}",
        )
    elif fixed_stop_loss_price and fixed_stop_loss_price > 0:
        quantized_fixed_sl = fixed_stop_loss_price.quantize(
            min_tick_size if min_tick_size > 0 else Decimal(f"1e-{price_precision}"),
        )
        params_to_set["stopLoss"] = str(quantized_fixed_sl)
        params_to_set["trailingStop"] = "0"
        params_to_set["activePrice"] = "0"
        logger.info(
            f"{NB}stsl: Preparing to set Fixed SL for {symbol} to {quantized_fixed_sl}. TSL will be cleared.{RST}",
        )
    else:
        params_to_set["stopLoss"] = "0"
        params_to_set["trailingStop"] = "0"
        params_to_set["activePrice"] = "0"
        logger.info(
            f"{NB}stsl: Preparing to clear SL and TSL for {symbol} (or no SL/TSL requested).{RST}",
        )

    if take_profit_price_target and take_profit_price_target > 0:
        quantized_tp = take_profit_price_target.quantize(
            min_tick_size if min_tick_size > 0 else Decimal(f"1e-{price_precision}"),
        )
        params_to_set["takeProfit"] = str(quantized_tp)
        logger.info(
            f"{NB}stsl: Preparing to set Take Profit for {symbol} to {quantized_tp}.{RST}",
        )
    else:
        params_to_set["takeProfit"] = "0"
        logger.info(
            f"{NB}stsl: Preparing to clear Take Profit for {symbol} (or no TP requested).{RST}",
        )

    if (
        params_to_set.get("stopLoss", "0") == "0"
        and params_to_set.get("takeProfit", "0") == "0"
        and params_to_set.get("trailingStop", "0") == "0"
        and not current_fixed_sl_on_exchange
        and not current_tp_on_exchange
        and not current_tsl_dist_on_exchange
    ):
        logger.info(
            f"{NB}stsl: No protections to set or clear for {symbol}. Skipping API call.{RST}",
        )
        trade_record.stop_loss_price = None
        trade_record.take_profit_price = None
        trade_record.trailing_stop_active = False
        trade_record.trailing_stop_distance = None
        trade_record.tsl_activation_price = None
        tt._save_trades()
        return True

    payload_json_str = json.dumps(params_to_set)
    headers = _generate_bybit_v5_request_headers(
        api_key=AK, api_secret=AS, payload_str=payload_json_str,
    )

    logger.info(
        f"{NB}stsl: Attempting to set protections for {symbol} via HTTP POST. URL: {endpoint_url}, Payload: {payload_json_str}{RST}",
    )

    http_response = None
    response_data = None
    try:
        http_response = requests.post(
            endpoint_url, headers=headers, data=payload_json_str, timeout=15,
        )
        http_response.raise_for_status()  # Check for HTTP errors like 4xx/5xx
        try:
            response_data = http_response.json()
            logger.info(
                f"{NB}stsl: Raw HTTP response from Bybit set_trading_stop for {symbol}: {json.dumps(response_data, default=str)}{RST}",
            )
        except json.JSONDecodeError:
            logger.error(
                f"{NR}[xrscalper_bot_{symbol}] - stsl: JSONDecodeError setting protections for {symbol}. "
                f"HTTP Status: {http_response.status_code if http_response else 'N/A'}, Response Text: {http_response.text if http_response else 'No response text'}{RST}",
            )
            return False  # Return False on JSON error
    except requests.exceptions.RequestException as e:
        logger.error(
            f"{NR}stsl: HTTP RequestException setting protections for {symbol}: {e}{RST}",
            exc_info=True,
        )
        # Log HTTP status and text if available from the exception's response attribute
        if hasattr(e, "response") and e.response is not None:
            logger.error(
                f"{NR}stsl: Failing HTTP Status: {e.response.status_code}, Response Text: {e.response.text}{RST}",
            )
        return False

    if response_data and response_data.get("retCode") == 0:
        logger.info(
            f"{NG}stsl: Successfully set protections for {symbol} via HTTP POST. Msg: {response_data.get('retMsg')}{RST}",
        )

        if (
            should_set_tsl
            and calculated_tsl_distance
            and calculated_tsl_activation_price
        ):
            trade_record.trailing_stop_active = True
            trade_record.trailing_stop_distance = calculated_tsl_distance
            trade_record.tsl_activation_price = calculated_tsl_activation_price
            trade_record.stop_loss_price = None
        else:
            trade_record.trailing_stop_active = False
            trade_record.trailing_stop_distance = None
            trade_record.tsl_activation_price = None
            if params_to_set.get("stopLoss") and params_to_set["stopLoss"] != "0":
                trade_record.stop_loss_price = Decimal(params_to_set["stopLoss"])
            else:
                trade_record.stop_loss_price = None

        if params_to_set.get("takeProfit") and params_to_set["takeProfit"] != "0":
            trade_record.take_profit_price = Decimal(params_to_set["takeProfit"])
        else:
            trade_record.take_profit_price = None

        tt._save_trades()
        logger.info(
            f"{NG}stsl: TradeRecord for {symbol} updated. SL: {trade_record.stop_loss_price}, TP: {trade_record.take_profit_price}, "
            f"TSL Active: {trade_record.trailing_stop_active}, TSL Dist: {trade_record.trailing_stop_distance}, TSL Act: {trade_record.tsl_activation_price}.{RST}",
        )
        return True
    ret_code = response_data.get("retCode") if response_data else "N/A"
    ret_msg = response_data.get("retMsg") if response_data else "N/A"
    logger.error(
        f"{NR}stsl: Failed to set protections for {symbol} via HTTP POST. retCode: {ret_code}, retMsg: {ret_msg}. Full Response: {json.dumps(response_data, default=str) if response_data else 'No response data'}{RST}",
    )
    return False


@dataclass
class Tr:
    """Trade Record: A dataclass to store details of an individual trade for tracking."""

    symbol: str
    side: str
    entry_price: Decimal
    entry_time: datetime
    size: Decimal
    leverage: Decimal
    # Capital allocated to this trade (e.g., risk_amount * leverage)
    initial_capital: Decimal
    stop_loss_price: Decimal | None = None
    take_profit_price: Decimal | None = None
    trailing_stop_active: bool = False
    trailing_stop_distance: Decimal | None = None
    tsl_activation_price: Decimal | None = None
    exit_price: Decimal | None = None
    exit_time: datetime | None = None
    pnl_quote: Decimal | None = None
    pnl_percentage: Decimal | None = None
    fees_in_quote: Decimal = Decimal("0")  # Track fees for this trade
    realized_pnl_quote: Decimal = Decimal("0")  # Realized PnL after fees
    status: str = "OPEN"
    entry_rsi: Decimal | None = None
    exit_rsi: Decimal | None = None
    entry_ema_short: Decimal | None = None
    exit_ema_short: Decimal | None = None
    entry_ema_long: Decimal | None = None
    exit_ema_long: Decimal | None = None
    entry_bbl: Decimal | None = None
    exit_bbl: Decimal | None = None
    entry_bbm: Decimal | None = None
    exit_bbm: Decimal | None = None
    entry_bbu: Decimal | None = None
    exit_bbu: Decimal | None = None
    entry_momentum: Decimal | None = None
    exit_momentum: Decimal | None = None
    entry_cci: Decimal | None = None
    exit_cci: Decimal | None = None
    entry_willr: Decimal | None = None
    exit_willr: Decimal | None = None
    entry_mfi: Decimal | None = None
    exit_mfi: Decimal | None = None
    entry_vwap: Decimal | None = None
    exit_vwap: Decimal | None = None
    entry_psar: Decimal | None = None
    exit_psar: Decimal | None = None
    entry_fisher: Decimal | None = None
    exit_fisher: Decimal | None = None
    entry_adx: Decimal | None = None
    exit_adx: Decimal | None = None
    highest_price_reached: Decimal | None = None
    lowest_price_reached: Decimal | None = None
    tsl_activated: bool = False

    def to_dict(self):
        """Converts the Trade Record to a dictionary suitable for JSON serialization."""
        data = asdict(self)
        # Convert Decimal to string, datetime to ISO format string
        for key, value in data.items():
            if isinstance(value, Decimal):
                data[key] = str(value)
            elif isinstance(value, datetime):
                data[key] = value.isoformat()
            # trailing_stop_active is already bool, no conversion needed
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]):
        """Creates a Trade Record instance from a dictionary (e.g., from JSON deserialization)."""
        # Convert string back to Decimal, ISO string back to datetime
        # Dataclass defaults will handle missing new fields like trailing_stop_active, etc.
        for key, value in data.items():
            if key in [
                "entry_price",
                "size",
                "leverage",
                "initial_capital",
                "stop_loss_price",
                "take_profit_price",
                "trailing_stop_distance",
                "tsl_activation_price",
                "exit_price",
                "pnl_quote",
                "pnl_percentage",
                "fees_in_quote",
                "realized_pnl_quote",
                "entry_rsi",
                "exit_rsi",
                "entry_ema_short",
                "exit_ema_short",
                "entry_ema_long",
                "exit_ema_long",
                "entry_bbl",
                "exit_bbl",
                "entry_bbm",
                "exit_bbm",
                "entry_bbu",
                "exit_bbu",
                "entry_momentum",
                "exit_momentum",
                "entry_cci",
                "exit_cci",
                "entry_willr",
                "exit_willr",
                "entry_mfi",
                "exit_mfi",
                "entry_vwap",
                "exit_vwap",
                "entry_psar",
                "exit_psar",
                "entry_fisher",
                "exit_fisher",
                "entry_adx",
                "exit_adx",
                "highest_price_reached",
                "lowest_price_reached",
            ]:
                if value is not None:
                    try:
                        data[key] = Decimal(str(value))
                    except InvalidOperation:
                        # If a Decimal field (e.g. an old record had "None" as str) cannot be converted,
                        # set it to None to match Optional[Decimal] type hint.
                        # The dataclass default will take over if the key is entirely missing.
                        data[key] = None
            elif key in ["entry_time", "exit_time"]:
                if value is not None:
                    try:
                        data[key] = datetime.fromisoformat(value).replace(
                            tzinfo=TZ,
                        )  # Ensure timezone-aware
                    except (
                        TypeError,
                        ValueError,
                    ):  # Handles if value is not a valid ISO string
                        data[key] = None
            # trailing_stop_active (bool) should be handled correctly by direct assignment or default

        # Ensure new optional Decimal fields that might be missing or invalid are set to None if not properly converted
        new_decimal_fields = [
            "trailing_stop_distance",
            "tsl_activation_price",
            "entry_rsi",
            "exit_rsi",
            "entry_ema_short",
            "exit_ema_short",
            "entry_ema_long",
            "exit_ema_long",
            "entry_bbl",
            "exit_bbl",
            "entry_bbm",
            "exit_bbm",
            "entry_bbu",
            "exit_bbu",
            "entry_momentum",
            "exit_momentum",
            "entry_cci",
            "exit_cci",
            "entry_willr",
            "exit_willr",
            "entry_mfi",
            "exit_mfi",
            "entry_vwap",
            "exit_vwap",
            "entry_psar",
            "exit_psar",
            "entry_fisher",
            "exit_fisher",
            "entry_adx",
            "exit_adx",
            "highest_price_reached",
            "lowest_price_reached",  # Added new decimal fields
        ]
        for decimal_field in new_decimal_fields:
            if (
                decimal_field in data
                and not isinstance(data[decimal_field], Decimal)
                and data[decimal_field] is not None
            ):
                # This case should be rare if above try-except for Decimal conversion works
                data[decimal_field] = None

        # Handle tsl_activated deserialization
        if "tsl_activated" in data and data["tsl_activated"] is not None:
            data["tsl_activated"] = bool(data["tsl_activated"])
        else:
            # If missing or None, explicitly set to the dataclass default (False)
            data["tsl_activated"] = False

        return cls(**data)

    def upnl(self, current_price: Decimal, market_info: dict, logger: logging.Logger):
        """Update Unrealized PnL: Calculates and updates the unrealized PnL for an open trade."""
        if self.status != "OPEN":
            return

        try:
            if not isinstance(current_price, Decimal) or current_price <= 0:
                logger.warning(
                    f"{NY}Cannot update PnL for {self.symbol}: Invalid current price ({current_price}).{RST}",
                )
                return

            contract_size = Decimal(str(market_info.get("contractSize", "1")))

            if self.side == "long":
                unrealized_pnl = (
                    (current_price - self.entry_price) * self.size * contract_size
                )
            else:
                unrealized_pnl = (
                    (self.entry_price - current_price) * self.size * contract_size
                )

            pnl_percentage = (
                (unrealized_pnl / self.initial_capital) * Decimal("100")
                if self.initial_capital > 0
                else Decimal("0")
            )

            self.pnl_quote = unrealized_pnl
            self.pnl_percentage = pnl_percentage

            price_precision = TA.gpp(market_info, logger)
            color_pnl = NG if unrealized_pnl >= 0 else NR
            logger.debug(
                f"{color_pnl}UNREALIZED PnL for {self.symbol} ({self.side.upper()}): {self.pnl_quote:.4f} {QC} ({self.pnl_percentage:.2f}%){RST}",
            )
        except (InvalidOperation, TypeError, ValueError) as e:
            logger.error(
                f"{NR}Error calculating unrealized PnL for {self.symbol}: {e}. A numerical distortion in PnL calculation!{RST}",
                exc_info=False,
            )
        except Exception as e:
            logger.error(
                f"{NR}Unexpected error updating PnL for {self.symbol}: {e}. A cosmic interference in PnL tracking!{RST}",
                exc_info=True,
            )


class TMT:
    """Trade Management Tracker: Manages a collection of open and closed trade records,
    and calculates overall trading metrics.
    """

    def __init__(
        self,
        quote_currency_symbol: str,
        logger: logging.Logger,
        exchange_ref: ccxt.Exchange | None = None,
    ):
        self.open_trades: dict[str, Tr] = {}
        self.closed_trades: list[Tr] = []
        self.qc = quote_currency_symbol
        self.ex_ref: ccxt.Exchange | None = exchange_ref
        self.lg = logger
        self.total_pnl = Decimal("0")
        self.initial_balance = Decimal("0")
        self.current_balance = Decimal("0")
        self.mi: dict[str, Any] = {}
        self._load_trades()  # Load trades on initialization

    def _load_trades(self):
        """Loads trade records from a JSON file."""
        if TRP.exists():
            try:
                with open(TRP, encoding="utf-8") as f:
                    data = json.load(f)
                    for trade_dict in data.get("closed_trades", []):
                        self.closed_trades.append(Tr.from_dict(trade_dict))
                    for trade_dict in data.get("open_trades", []):
                        trade_record = Tr.from_dict(trade_dict)

                        if trade_record.symbol not in self.mi:
                            self.lg.warning(
                                f"{NY}Unmanaged open trade record loaded for {trade_record.symbol}. Attempting to fetch market info on-the-fly... The ledger speaks of a forgotten quest!{RST}",
                            )

                            if (
                                self.ex_ref
                            ):  # Check if the exchange reference was provided
                                exchange_instance = self.ex_ref
                                market_info_on_the_fly = gmi(
                                    exchange_instance, trade_record.symbol, self.lg,
                                )
                                if market_info_on_the_fly:
                                    self.mi[trade_record.symbol] = (
                                        market_info_on_the_fly
                                    )
                                    self.lg.info(
                                        f"{NG}Successfully fetched market info for unmanaged trade {trade_record.symbol} and updated tracker. The forgotten quest is now known!{RST}",
                                    )
                                else:
                                    self.lg.error(
                                        f"{NR}Failed to fetch market info for unmanaged open trade {trade_record.symbol} using provided exchange reference. It will be displayed with N/A values. The forgotten quest remains shrouded!{RST}",
                                    )
                            else:
                                self.lg.error(
                                    f"{NR}No exchange reference available in TMT to fetch market info for unmanaged trade {trade_record.symbol}.{RST}",
                                )

                        self.open_trades[trade_record.symbol] = trade_record
                    self.total_pnl = Decimal(str(data.get("total_pnl", "0")))
                    self.initial_balance = Decimal(
                        str(data.get("initial_balance", "0")),
                    )
                    self.current_balance = Decimal(
                        str(data.get("current_balance", "0")),
                    )
                self.lg.info(
                    f"{NG}Loaded {len(self.open_trades)} open and {len(self.closed_trades)} closed trade records from {TRP}. The historical ledger is restored!{RST}",
                )
            except (json.JSONDecodeError, InvalidOperation, KeyError) as e:
                self.lg.error(
                    f"{NR}Error loading trade records from {TRP}: {e}. File might be corrupted. Starting fresh. The ancient ledger is unreadable!{RST}",
                )
                self._reset_trades()
            except Exception as e:
                self.lg.error(
                    f"{NR}Unexpected error during trade record loading: {e}. A cosmic interference!{RST}",
                    exc_info=True,
                )
                self._reset_trades()
        else:
            self.lg.info(
                f"{NB}No existing trade records file found at {TRP}. Starting with a fresh ledger.{RST}",
            )

    def _save_trades(self):
        """Saves current trade records to a JSON file."""
        try:
            data = {
                "open_trades": [trade.to_dict() for trade in self.open_trades.values()],
                "closed_trades": [trade.to_dict() for trade in self.closed_trades],
                "total_pnl": str(self.total_pnl),
                "initial_balance": str(self.initial_balance),
                "current_balance": str(self.current_balance),
            }
            with open(TRP, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            self.lg.debug(
                f"{NB}Saved trade records to {TRP}. The ledger is updated.{RST}",
            )
        except OSError as e:
            self.lg.error(
                f"{NR}Error saving trade records to {TRP}: {e}. The quill broke during inscription!{RST}",
            )
        except Exception as e:
            self.lg.error(
                f"{NR}Unexpected error during trade record saving: {e}. A cosmic interference!{RST}",
                exc_info=True,
            )

    def _reset_trades(self):
        """Resets all trade records."""
        self.open_trades = {}
        self.closed_trades = []
        self.total_pnl = Decimal("0")
        self.initial_balance = Decimal("0")
        self.current_balance = Decimal("0")
        self.lg.warning(
            f"{NY}All trade records have been reset. A new chapter begins.{RST}",
        )

    def set_exchange_reference(self, exchange_instance: ccxt.Exchange):
        """Sets the exchange instance reference for the TMT."""
        self.ex_ref = exchange_instance
        self.lg.info(
            f"{NB}Trade Management Tracker has received the exchange reference. Ready for advanced operations!{RST}",
        )
        # Potentially re-process any unmanaged trades if market info was missing
        # For simplicity, we'll assume _load_trades is the primary point this is needed initially.
        # If there's a need to retroactively fetch market info for already loaded trades
        # where ex_ref was missing, that logic could be added here or called separately.

    def sib(self, balance: Decimal):
        """Set Initial Balance: Sets the initial account balance if not already set."""
        if self.initial_balance == Decimal("0") and balance > 0:
            self.initial_balance = balance
            self.current_balance = balance
            self.lg.info(
                f"{NC}Initial account balance set to {self.initial_balance:.4f} {self.qc}. The journey begins!{RST}",
            )
            self._save_trades()

    def ub(self, new_balance: Decimal):
        """Update Balance: Updates the current account balance."""
        if new_balance > 0:
            self.current_balance = new_balance
            self._save_trades()

    def aot(self, trade_record: Tr):
        """Add Open Trade: Adds a new trade record to the open trades dictionary."""
        self.open_trades[trade_record.symbol] = trade_record
        self.lg.info(
            f"{NG}TRADE TRACKER: Added new OPEN trade for {trade_record.symbol} ({trade_record.side}) at {trade_record.entry_price} with size {trade_record.size}. A new quest begins!{RST}",
        )
        self._save_trades()

    def ct(
        self,
        symbol: str,
        exit_price: Decimal,
        exit_time: datetime,
        current_balance: Decimal,
        fees_in_quote: Decimal = Decimal("0"),
    ):
        """Close Trade: Moves an open trade to the closed trades list, calculates its PnL,
        and updates total PnL.
        """
        trade_record = self.open_trades.pop(symbol, None)
        if trade_record:
            trade_record.exit_price = exit_price
            trade_record.exit_time = exit_time

            symbol_market_info = self.mi.get(symbol, {})
            contract_size = Decimal(str(symbol_market_info.get("contractSize", "1")))

            if trade_record.side == "long":
                trade_record.pnl_quote = (
                    (trade_record.exit_price - trade_record.entry_price)
                    * trade_record.size
                    * contract_size
                )
            else:
                trade_record.pnl_quote = (
                    (trade_record.entry_price - trade_record.exit_price)
                    * trade_record.size
                    * contract_size
                )

            trade_record.pnl_percentage = (
                (trade_record.pnl_quote / trade_record.initial_capital) * Decimal("100")
                if trade_record.initial_capital > 0
                else Decimal("0")
            )

            trade_record.fees_in_quote = fees_in_quote
            trade_record.realized_pnl_quote = trade_record.pnl_quote - fees_in_quote

            if trade_record.realized_pnl_quote >= 0:
                trade_record.status = "CLOSED_WIN"
            else:
                trade_record.status = "CLOSED_LOSS"

            self.closed_trades.append(trade_record)
            self.total_pnl += trade_record.realized_pnl_quote
            self.ub(current_balance)

            color_pnl = NG if trade_record.realized_pnl_quote >= 0 else NR
            self.lg.info(
                f"{color_pnl}TRADE TRACKER: Closed {trade_record.symbol} trade. Realized PnL: {trade_record.realized_pnl_quote:.4f} {self.qc} ({trade_record.pnl_percentage:.2f}%). Fees: {trade_record.fees_in_quote:.4f}. The trade's fate is sealed!{RST}",
            )
            self._save_trades()
        else:
            self.lg.warning(
                f"{NY}TRADE TRACKER: Attempted to close non-existent open trade for {symbol}. The trade was already gone!{RST}",
            )

    def dm(self):
        """Display Metrics: Prints a summary of all closed trades and overall performance."""
        total_closed_trades = len(self.closed_trades)
        winning_trades = sum(
            1
            for trade in self.closed_trades
            if trade.realized_pnl_quote is not None and trade.realized_pnl_quote >= 0
        )
        losing_trades = total_closed_trades - winning_trades
        win_rate = (
            (winning_trades / total_closed_trades * 100)
            if total_closed_trades > 0
            else 0
        )

        total_pnl_percentage = Decimal("0")
        if self.initial_balance > 0:
            total_pnl_percentage = (self.total_pnl / self.initial_balance) * Decimal(
                "100",
            )

        avg_pnl_per_trade = (
            (self.total_pnl / total_closed_trades)
            if total_closed_trades > 0
            else Decimal("0")
        )

        winning_scores = [
            trade.realized_pnl_quote
            for trade in self.closed_trades
            if trade.realized_pnl_quote is not None and trade.realized_pnl_quote >= 0
        ]
        losing_scores = [
            trade.realized_pnl_quote
            for trade in self.closed_trades
            if trade.realized_pnl_quote is not None and trade.realized_pnl_quote < 0
        ]

        average_win = (
            sum(winning_scores) / len(winning_scores)
            if winning_scores
            else Decimal("0")
        )
        average_loss = (
            sum(losing_scores) / len(losing_scores) if losing_scores else Decimal("0")
        )

        max_win_amount = max(winning_scores) if winning_scores else Decimal("0")
        max_loss_amount = min(losing_scores) if losing_scores else Decimal("0")

        max_win_percentage = (
            max(
                trade.pnl_percentage
                for trade in self.closed_trades
                if trade.pnl_percentage is not None and trade.pnl_percentage >= 0
            )
            if winning_scores
            else Decimal("0")
        )
        max_loss_percentage = (
            min(
                trade.pnl_percentage
                for trade in self.closed_trades
                if trade.pnl_percentage is not None and trade.pnl_percentage < 0
            )
            if losing_scores
            else Decimal("0")
        )

        metrics_output = (
            f"Total PnL={self.total_pnl:,.2f} {self.qc} | "
            f"Total PnL%={total_pnl_percentage:,.2f}% | "
            f"Trades={total_closed_trades} (Win:{winning_trades}/Loss:{losing_trades}) | "
            f"Win Rate={win_rate:,.2f}% | "
            f"Avg PnL/Trade={avg_pnl_per_trade:,.2f} | "
            f"Avg Win={average_win:,.2f} | "
            f"Avg Loss={average_loss:,.2f} | "
            f"Max Win={max_win_amount:,.2f} ({max_win_percentage:,.2f}%) | "
            f"Max Loss={max_loss_amount:,.2f} ({max_loss_percentage:,.2f}%)"
        )

        print("")  # Add a newline before the header
        print_neon_header("Trade Metrics Summary", color=NP, length=70)

        label_width = 25  # Increased width for better readability

        # Overall PnL
        print(
            format_metric(
                "Total Realized PnL",
                self.total_pnl,
                NG if self.total_pnl >= 0 else NR,  # Changed NP to NG/NR
                label_width=label_width,
                unit=f" {self.qc}",
                is_pnl=True,
                value_precision=4,
            ),
        )
        if self.initial_balance > 0:
            print(
                format_metric(
                    "Total PnL % (on Initial)",
                    total_pnl_percentage,
                    NG if total_pnl_percentage >= 0 else NR,
                    label_width=label_width,
                    unit="%",
                    is_pnl=True,
                ),
            )  # Changed NP to NG/NR

        print_neon_separator(
            length=70, char="·", color=NP,
        )  # Changed NC to NP for section separator

        # Trade Counts & Win Rate
        print(
            format_metric(
                "Total Closed Trades", total_closed_trades, NB, label_width=label_width,
            ),
        )
        print(
            format_metric("Winning Trades", winning_trades, NG, label_width=label_width),
        )
        print(
            format_metric("Losing Trades", losing_trades, NR, label_width=label_width),
        )
        print(
            format_metric(
                "Win Rate",
                win_rate,
                NB,
                label_width=label_width,
                unit="%",
                value_precision=2,
            ),
        )

        print_neon_separator(length=70, char="·", color=NC)

        # Averages
        print(
            format_metric(
                "Avg PnL per Trade",
                avg_pnl_per_trade,
                NG if avg_pnl_per_trade >= 0 else NR,  # Changed NB to NG/NR
                label_width=label_width,
                unit=f" {self.qc}",
                is_pnl=True,
                value_precision=4,
            ),
        )
        print(
            format_metric(
                "Avg Winning Trade",
                average_win,
                NG,
                label_width=label_width,
                unit=f" {self.qc}",
                is_pnl=True,
                value_precision=4,
            ),
        )
        print(
            format_metric(
                "Avg Losing Trade",
                average_loss,
                NR,
                label_width=label_width,
                unit=f" {self.qc}",
                is_pnl=True,
                value_precision=4,
            ),
        )

        print_neon_separator(
            length=70, char="·", color=NP,
        )  # Changed NC to NP for section separator

        # Max Win/Loss
        print(
            format_metric(
                f"Max Win ({self.qc})",
                max_win_amount,
                NG,
                label_width=label_width,
                unit=f" {self.qc}",
                is_pnl=True,
                value_precision=4,
            ),
        )
        print(
            format_metric(
                "Max Win %",
                max_win_percentage,
                NG,
                label_width=label_width,
                unit="%",
                is_pnl=True,
            ),
        )

        print(
            format_metric(
                f"Max Loss ({self.qc})",
                max_loss_amount,
                NR,
                label_width=label_width,
                unit=f" {self.qc}",
                is_pnl=True,
                value_precision=4,
            ),
        )
        print(
            format_metric(
                "Max Loss %",
                max_loss_percentage,
                NR,
                label_width=label_width,
                unit="%",
                is_pnl=True,
            ),
        )

        print_neon_separator(
            length=70, char="·", color=NP,
        )  # Changed NC to NP for section separator

        # --- Profit Factor ---
        gross_profit = sum(
            trade.realized_pnl_quote
            for trade in self.closed_trades
            if trade.realized_pnl_quote is not None and trade.realized_pnl_quote > 0
        )
        gross_loss_abs = abs(
            sum(
                trade.realized_pnl_quote
                for trade in self.closed_trades
                if trade.realized_pnl_quote is not None and trade.realized_pnl_quote < 0
            ),
        )

        profit_factor = Decimal("0.00")
        profit_factor_color = NY  # Default to Yellow for N/A or 0.00
        profit_factor_str = "N/A"

        if gross_loss_abs > 0:
            profit_factor = gross_profit / gross_loss_abs
            profit_factor_str = f"{profit_factor:.2f}"
            if profit_factor > Decimal("1"):
                profit_factor_color = NG
            elif profit_factor < Decimal("1"):
                profit_factor_color = NR
            else:  # Exactly 1
                profit_factor_color = NY
        elif gross_profit > 0:  # Gross loss is 0, but profit is positive
            profit_factor_str = "Inf"
            profit_factor_color = NG  # Infinite profit factor is good
        elif gross_profit == 0 and gross_loss_abs == 0:  # Both are zero
            profit_factor_str = "0.00"
            profit_factor_color = NY

        print(
            format_metric(
                "Gross Profit",
                gross_profit,
                NG,
                label_width=label_width,
                unit=f" {self.qc}",
                value_precision=4,
            ),
        )
        print(
            format_metric(
                "Gross Loss",
                -gross_loss_abs,
                NR,
                label_width=label_width,
                # Display gross loss as negative
                unit=f" {self.qc}",
                value_precision=4,
            ),
        )
        print(
            format_metric(
                "Profit Factor",
                profit_factor_str,
                profit_factor_color,
                label_width=label_width,
            ),
        )

        print_neon_separator(
            length=70, char="·", color=NP,
        )  # Changed NC to NP for section separator

        # --- Trade Durations ---
        total_duration_seconds = 0
        total_win_duration_seconds = 0
        total_loss_duration_seconds = 0

        trades_with_duration = 0
        winning_trades_with_duration = 0
        losing_trades_with_duration = 0

        for trade in self.closed_trades:
            if (
                trade.entry_time
                and trade.exit_time
                and isinstance(trade.entry_time, datetime)
                and isinstance(trade.exit_time, datetime)
            ):
                duration_seconds = (trade.exit_time - trade.entry_time).total_seconds()
                if duration_seconds >= 0:  # Ensure valid duration
                    total_duration_seconds += duration_seconds
                    trades_with_duration += 1
                    if trade.realized_pnl_quote is not None:
                        if trade.realized_pnl_quote >= 0:
                            total_win_duration_seconds += duration_seconds
                            winning_trades_with_duration += 1
                        else:
                            total_loss_duration_seconds += duration_seconds
                            losing_trades_with_duration += 1

        def format_duration(total_seconds: float, count: int) -> str:
            if count == 0 or total_seconds == 0:
                return "N/A"
            avg_seconds = total_seconds / count
            hours = int(avg_seconds // 3600)
            minutes = int((avg_seconds % 3600) // 60)
            seconds = int(avg_seconds % 60)
            if hours > 0:
                return f"{hours}h {minutes}m {seconds}s"
            if minutes > 0:
                return f"{minutes}m {seconds}s"
            return f"{seconds}s"

        avg_duration_str = format_duration(total_duration_seconds, trades_with_duration)
        avg_win_duration_str = format_duration(
            total_win_duration_seconds, winning_trades_with_duration,
        )
        avg_loss_duration_str = format_duration(
            total_loss_duration_seconds, losing_trades_with_duration,
        )

        print(
            format_metric(
                "Avg Trade Duration", avg_duration_str, NB, label_width=label_width,
            ),
        )
        print(
            format_metric(
                "Avg Win Duration", avg_win_duration_str, NG, label_width=label_width,
            ),
        )
        print(
            format_metric(
                "Avg Loss Duration", avg_loss_duration_str, NR, label_width=label_width,
            ),
        )

        print_neon_separator(length=70, color=NP)
        print("")  # Add a newline after the summary


tt: TMT = TMT(QC, slg("trade_tracker"))


class BybitWebSocketClient:
    """Manages WebSocket connections to Bybit for real-time data.
    Supports public (ticker) and private (order, position) streams.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        use_testnet: bool,
        logger: logging.Logger,
        public_base_url: str,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.logger = logger
        self.base_public_url = public_base_url  # Use the passed public_base_url
        self.base_private_url = "wss://stream.bybit.com/v5/private"
        if use_testnet:
            # Dynamically adjust public_base_url for testnet
            self.base_public_url = public_base_url.replace(
                "stream.bybit.com", "stream-testnet.bybit.com",
            )
            self.base_private_url = "wss://stream-testnet.bybit.com/v5/private"
            self.logger.warning(f"{NY}WebSocket client is configured for TESTNET.{RST}")

        self.public_ws: websocket.WebSocketApp | None = None
        self.private_ws: websocket.WebSocketApp | None = None
        self.public_thread: threading.Thread | None = None
        self.private_thread: threading.Thread | None = None

        self.callbacks: dict[str, list[Callable[[dict], None]]] = {
            "ticker": [],
            "order": [],
            "position": [],
        }
        # Stores latest ticker price for each symbol (Bybit ID)
        self.last_prices: dict[str, Decimal] = {}
        # Stores latest position info for each symbol (Bybit ID)
        self.position_updates: dict[str, dict] = {}

        self.public_subscriptions: list[str] = []
        self.private_subscriptions: list[str] = []

        self.is_running = False
        self.auth_success = False

    def _generate_hmac_signature(self, timestamp: str) -> str:
        # Corrected signature generation as per Bybit V5 WS authentication
        # The message format for authentication is "GET/realtime{expires}"
        message = f"GET/realtime{timestamp}"
        signature = hmac.new(
            self.api_secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256,
        ).hexdigest()
        return signature

    def _on_message_public(self, ws, message):
        try:
            data = json.loads(message)
            if data.get("op") == "pong":
                self.logger.debug(f"{NB}WS Public: Pong received.{RST}")
                return
            if data.get("success") is False:
                self.logger.error(
                    f"{NR}WS Public Error: {data.get('ret_msg', 'Unknown error')}. Full: {data}{RST}",
                )
                return

            topic = data.get("topic")
            if topic and topic.startswith("tickers."):
                symbol_id = topic.split(".")[-1]  # e.g., BTCUSDT
                # Check the 'type' of the message to correctly parse 'data'
                message_type = data.get("type")
                raw_ticker_payload = data.get("data")
                ticker_data = None

                if message_type == "snapshot":
                    if isinstance(raw_ticker_payload, list) and raw_ticker_payload:
                        ticker_data = raw_ticker_payload[0]
                    # Handle direct dict for snapshot
                    elif isinstance(raw_ticker_payload, dict):
                        ticker_data = raw_ticker_payload
                    else:
                        self.logger.warning(
                            f"{NY}WS Public: Unexpected snapshot data structure for {symbol_id}. Payload: {raw_ticker_payload}. Skipping.{RST}",
                        )
                elif message_type == "delta":
                    if isinstance(raw_ticker_payload, dict):
                        ticker_data = raw_ticker_payload
                    else:
                        self.logger.warning(
                            f"{NY}WS Public: Unexpected delta data structure for {symbol_id}. Payload: {raw_ticker_payload}. Skipping.{RST}",
                        )
                else:
                    self.logger.warning(
                        f"{NY}WS Public: Unknown ticker message type '{message_type}' for {symbol_id}. Payload: {raw_ticker_payload}. Skipping.{RST}",
                    )

                if ticker_data:
                    last_price = ticker_data.get("lastPrice")
                    if last_price is not None:
                        try:
                            self.last_prices[symbol_id] = Decimal(str(last_price))
                            for callback in self.callbacks["ticker"]:
                                callback(
                                    {
                                        "symbol_id": symbol_id,
                                        "lastPrice": self.last_prices[symbol_id],
                                    },
                                )
                        except InvalidOperation:
                            self.logger.warning(
                                f"{NY}WS Public: Could not convert lastPrice '{last_price}' to Decimal for {symbol_id}.{RST}",
                            )
            # Add other public topic handling here if needed (e.g., orderbook)

        except json.JSONDecodeError:
            self.logger.warning(
                f"{NY}WS Public: Received non-JSON message: {message}{RST}",
            )
        except Exception as e:
            self.logger.error(
                f"{NR}WS Public: Error processing message: {e}. Message: {message}{RST}",
                exc_info=True,
            )

    def _on_message_private(self, ws, message):
        try:
            data = json.loads(message)
            if data.get("op") == "pong":
                self.logger.debug(f"{NB}WS Private: Pong received.{RST}")
                return
            if data.get("op") == "auth":
                if data.get("success"):
                    self.logger.info(f"{NG}WS Private: Authentication successful.{RST}")
                    self.auth_success = True
                else:
                    self.logger.error(
                        f"{NR}WS Private: Authentication failed: {data.get('ret_msg', 'Unknown error')}. Full: {data}{RST}",
                    )
                    self.auth_success = False
                return
            if data.get("success") is False:
                self.logger.error(
                    f"{NR}WS Private Error: {data.get('ret_msg', 'Unknown error')}. Full: {data}{RST}",
                )
                return

            topic = data.get("topic")
            if topic == "order":
                if data.get("data") and len(data["data"]) > 0:
                    for order_data in data["data"]:
                        for callback in self.callbacks["order"]:
                            callback(order_data)
            elif topic == "position":
                if data.get("data") and len(data["data"]) > 0:
                    for pos_data in data["data"]:
                        symbol_id = pos_data.get("symbol")
                        if symbol_id:
                            self.position_updates[symbol_id] = pos_data
                            for callback in self.callbacks["position"]:
                                callback(pos_data)
            # Add other private topic handling here if needed (e.g., execution)

        except json.JSONDecodeError:
            self.logger.warning(
                f"{NY}WS Private: Received non-JSON message: {message}{RST}",
            )
        except Exception as e:
            self.logger.error(
                f"{NR}WS Private: Error processing message: {e}. Message: {message}{RST}",
                exc_info=True,
            )

    def _on_error(self, ws, error):
        self.logger.error(f"{NR}WebSocket Error ({ws.url}): {error}{RST}")

    def _on_close(self, ws, close_status_code, close_msg):
        self.logger.warning(
            f"{NY}WebSocket Closed ({ws.url}): Code={close_status_code}, Msg={close_msg}{RST}",
        )
        if self.is_running:  # Attempt reconnect only if still intended to be running
            self.logger.info(
                f"{NB}Attempting to reconnect WebSocket ({ws.url}) in {RDS}s...{RST}",
            )
            time.sleep(RDS)
            if ws.url == self.base_public_url:
                self._connect_public()
            elif ws.url == self.base_private_url:
                self._connect_private()

    def _on_open_public(self, ws):
        self.logger.info(
            f"{NG}WebSocket Public Connected. Subscribing to topics...{RST}",
        )
        for topic in self.public_subscriptions:
            ws.send(json.dumps({"op": "subscribe", "args": [topic]}))
            self.logger.debug(f"{NB}WS Public: Subscribed to {topic}.{RST}")
        self._start_ping_thread(ws)

    def _on_open_private(self, ws):
        self.logger.info(
            f"{NG}WebSocket Private Connected. Authenticating and subscribing...{RST}",
        )
        # Bybit V5 WS authentication uses 'expires' as timestamp, and 'signature' based on "GET/realtime{expires}"
        # Timestamp in milliseconds, valid for 10 seconds
        expires = int((time.time() + 10) * 1000)
        signature = self._generate_hmac_signature(str(expires))
        auth_msg = {"op": "auth", "args": [self.api_key, expires, signature]}

        self.logger.debug(f"WS Private: Sending auth message: {auth_msg}{RST}")
        ws.send(json.dumps(auth_msg))

        # Wait for authentication response before subscribing to private topics
        start_time = time.time()
        while (
            not self.auth_success and time.time() - start_time < 10
        ):  # 10 second timeout for auth
            time.sleep(0.1)

        if self.auth_success:
            for topic in self.private_subscriptions:
                ws.send(json.dumps({"op": "subscribe", "args": [topic]}))
                self.logger.debug(f"{NB}WS Private: Subscribed to {topic}.{RST}")
        else:
            self.logger.error(
                f"{NR}WS Private: Authentication failed or timed out. Not subscribing to private topics.{RST}",
            )
        self._start_ping_thread(ws)

    def _start_ping_thread(self, ws):
        def ping_loop():
            while ws.sock and ws.sock.connected and self.is_running:
                try:
                    ws.send(json.dumps({"op": "ping"}))
                    time.sleep(20)  # Bybit recommends ping every 20s
                except websocket.WebSocketConnectionClosedException:
                    self.logger.debug(
                        f"{NY}Ping thread: WebSocket connection closed for {ws.url}.{RST}",
                    )
                    break
                except Exception as e:
                    self.logger.error(
                        f"{NR}Ping thread error for {ws.url}: {e}{RST}", exc_info=True,
                    )
                    break

        threading.Thread(target=ping_loop, daemon=True).start()

    def _connect_public(self):
        self.public_ws = websocket.WebSocketApp(
            self.base_public_url,
            on_message=self._on_message_public,
            on_error=self._on_error,
            on_close=self._on_close,
            on_open=self._on_open_public,
        )
        self.public_thread = threading.Thread(
            target=self.public_ws.run_forever, daemon=True,
        )
        self.public_thread.start()
        self.logger.info(f"{NB}Started public WebSocket thread.{RST}")

    def _connect_private(self):
        self.private_ws = websocket.WebSocketApp(
            self.base_private_url,
            on_message=self._on_message_private,
            on_error=self._on_error,
            on_close=self._on_close,
            on_open=self._on_open_private,
        )
        self.private_thread = threading.Thread(
            target=self.private_ws.run_forever, daemon=True,
        )
        self.private_thread.start()
        self.logger.info(f"{NB}Started private WebSocket thread.{RST}")

    def start(self, public_topics: list[str], private_topics: list[str]):
        self.is_running = True
        self.public_subscriptions = public_topics
        self.private_subscriptions = private_topics
        self._connect_public()
        self._connect_private()
        self.logger.info(
            f"{NG}Bybit WebSocket client started. Public topics: {public_topics}, Private topics: {private_topics}{RST}",
        )

    def stop(self):
        self.is_running = False
        if self.public_ws:
            self.public_ws.close()
            self.logger.info(f"{NB}Public WebSocket closed.{RST}")
        if self.private_ws:
            self.private_ws.close()
            self.logger.info(f"{NB}Private WebSocket closed.{RST}")
        self.logger.info(f"{NG}Bybit WebSocket client stopped.{RST}")

    def register_callback(self, stream_type: str, callback: Callable[[dict], None]):
        if stream_type in self.callbacks:
            self.callbacks[stream_type].append(callback)
            self.logger.debug(f"{NB}Registered callback for {stream_type} stream.{RST}")
        else:
            self.logger.warning(
                f"{NY}Attempted to register callback for unknown stream type: {stream_type}{RST}",
            )

    def get_last_price(self, bybit_symbol_id: str) -> Decimal | None:
        """Retrieves the last known price for a Bybit symbol ID from WebSocket cache."""
        return self.last_prices.get(bybit_symbol_id)

    def get_latest_position_update(self, bybit_symbol_id: str) -> dict | None:
        """Retrieves the latest position update for a Bybit symbol ID from WebSocket cache."""
        return self.position_updates.get(bybit_symbol_id)


class PB:
    """Per-Symbol Bot: Manages the trading logic for a single cryptocurrency symbol.
    Handles data fetching, technical analysis, signal generation, and trade execution.
    """

    def __init__(
        self,
        symbol: str,
        exchange: ccxt.Exchange,
        config: dict[str, Any],
        logger: logging.Logger,
        ws_client: BybitWebSocketClient,
    ):
        self.s = symbol
        self.ex = exchange
        self.cfg = config
        self.lg = logger
        self.ws_client = ws_client  # WebSocket client instance
        self.mi: dict | None = None
        self.lct: pd.Timestamp | None = None
        self.ta_analyzer: TA | None = None

        self.mi = gmi(self.ex, self.s, self.lg)
        if not self.mi:
            raise ValueError(
                f"{NR}Initialization failed: Could not retrieve market info for {self.s}. The market's essence is unknown!{RST}",
            )

        tt.mi[self.s] = self.mi

        if self.mi.get("is_contract", False):
            leverage_value = int(self.cfg.get("leverage", 1))
            if leverage_value > 0:
                # slc now handles "leverage not modified" as a success
                if not slc(self.ex, self.s, leverage_value, self.mi, self.lg):
                    self.lg.error(
                        f"{NR}Failed to set leverage for {self.s} during initialization. This may affect trade execution. The amplification ritual is incomplete!{RST}",
                    )
                    # If leverage setting truly fails (not just "not modified"),
                    # it might be better to raise an exception here to prevent trading
                    # with incorrect leverage, or at least log a critical error.
                    # For now, we'll let the initialization continue but log the error.
            else:
                self.lg.info(
                    f"{NB}Leverage setting skipped for {self.s}: Configured leverage is zero or negative ({leverage_value}).{RST}",
                )
        else:
            self.lg.info(
                f"{NB}Leverage setting skipped for {self.s} (Spot market).{RST}",
            )

        # Store symbol ID for WebSocket topics (e.g., BTCUSDT from BTC/USDT:USDT)
        self.bybit_symbol_id = self.mi.get("id")
        if not self.bybit_symbol_id:
            self.lg.error(
                f"{NR}Could not determine Bybit symbol ID for {self.s}. WebSocket subscriptions may fail.{RST}",
            )
            # Fallback to CCXT symbol if Bybit ID is crucial and not found
            self.bybit_symbol_id = self.s.replace("/", "").replace(
                ":", "",
            )  # Best effort conversion

        # Register callbacks for this symbol's specific needs
        self.ws_client.register_callback("ticker", self._handle_ticker_update)
        self.ws_client.register_callback("order", self._handle_order_update)
        self.ws_client.register_callback("position", self._handle_position_update)

    def _get_indicator_value(
        self, primary_key: str, *alternative_keys: str,
    ) -> Decimal | None:
        """Helper to retrieve an indicator value from self.ta_analyzer.iv.
        Checks primary_key first, then any alternative_keys.
        Returns None if the value is NaN or not found.
        """
        if not self.ta_analyzer or not hasattr(self.ta_analyzer, "iv"):
            self.lg.warning(
                f"{NY}_get_indicator_value: ta_analyzer or its 'iv' attribute is not available for {self.s}.{RST}",
            )
            return None

        keys_to_check = [primary_key] + list(alternative_keys)

        val = None
        for key in keys_to_check:
            val = self.ta_analyzer.iv.get(key)
            if val is not None and not val.is_nan():
                break  # Found a valid value
            val = None  # Reset val if it was NaN or None to continue checking alternatives

        if val is None:  # All keys resulted in None or NaN
            # self.lg.debug(f"_get_indicator_value: No valid value found for keys {keys_to_check} in ta_analyzer.iv for {self.s}.")
            return None

        if isinstance(val, Decimal) and val.is_nan():
            # self.lg.debug(f"_get_indicator_value: Value for key '{primary_key}' (or alternatives) is NaN in ta_analyzer.iv for {self.s}. Returning None.")
            return None

        if not isinstance(val, Decimal):
            try:
                # self.lg.debug(f"_get_indicator_value: Converting value '{val}' for key '{primary_key}' to Decimal for {self.s}.")
                return Decimal(str(val))
            except InvalidOperation:
                self.lg.warning(
                    f"{NY}_get_indicator_value: Could not convert value '{val}' for key '{primary_key}' to Decimal for {self.s}. Returning None.{RST}",
                )
                return None

        # self.lg.debug(f"_get_indicator_value: Successfully retrieved value for key '{primary_key}' (or alternatives): {val} for {self.s}.")
        return val

    def _get_psar_value(self) -> Decimal | None:
        """Helper to retrieve PSAR value, checking PSAR_long then PSAR_short."""
        if not self.ta_analyzer or not hasattr(self.ta_analyzer, "iv"):
            self.lg.warning(
                f"{NY}_get_psar_value: ta_analyzer or 'iv' not available for {self.s}.{RST}",
            )
            return None

        psar_l = self.ta_analyzer.iv.get("PSAR_long")
        if psar_l is not None and not psar_l.is_nan():
            return psar_l

        psar_s = self.ta_analyzer.iv.get("PSAR_short")
        if psar_s is not None and not psar_s.is_nan():
            return psar_s

        return None

    def _handle_ticker_update(self, ticker_data: dict):
        """Callback for ticker updates from WebSocket."""
        if ticker_data.get("symbol_id") == self.bybit_symbol_id:
            pass  # Price is cached in ws_client.last_prices

    def _handle_order_update(self, order_data: dict):
        """Callback for order updates from WebSocket."""
        # Bybit WS order topic sends updates for all orders, filter by symbol
        if order_data.get("symbol") == self.bybit_symbol_id:
            self.lg.debug(
                f"WS Order Update for {self.s}: OrderID={order_data.get('orderId')}, Status={order_data.get('orderStatus')}, Side={order_data.get('side')}, Price={order_data.get('price')}, Qty={order_data.get('qty')}",
            )
            # This can be used for immediate reaction to order fills/cancellations
            # For example, if a TP/SL order is filled, you might trigger _cet directly
            # However, for simplicity and to avoid race conditions with main loop,
            # the main loop's position checks (_mp) will still be the primary driver.

    def _handle_position_update(self, position_data: dict):
        """Callback for position updates from WebSocket."""
        # Bybit WS position topic sends updates for all positions, filter by symbol
        if position_data.get("symbol") == self.bybit_symbol_id:
            self.lg.debug(
                f"WS Position Update for {self.s}: Side={position_data.get('side')}, Size={position_data.get('size')}, Entry={position_data.get('avgPrice')}, SL={position_data.get('stopLoss')}, TP={position_data.get('takeProfit')}, TSL={position_data.get('trailingStop')}",
            )
            # This is crucial for real-time TSL and break-even adjustments.
            # The _mp function will use ws_client.get_latest_position_update()
            # which directly accesses the cache updated by this callback.

    def _cfnc(self, kline_data: pd.DataFrame) -> bool:
        """Check For New Closed Candle: Determines if a new closed candle has formed
        since the last check.
        """
        if kline_data.empty:
            return False
        if len(kline_data) < 2:
            self.lg.debug(
                f"Not enough klines ({len(kline_data)}) to determine last closed candle for {self.s}.",
            )
            return False

        current_last_closed_candle_ts = kline_data.index[-2]

        if self.lct is None:
            self.lct = current_last_closed_candle_ts
            self.lg.info(
                f"{NB}Initial last closed candle timestamp set for {self.s}: {self.lct}. Ready to detect new formations.{RST}",
            )
            return True
        if current_last_closed_candle_ts > self.lct:
            self.lg.info(
                f"{NB}New closed candle detected for {self.s}: {current_last_closed_candle_ts}. A new temporal segment has arrived!{RST}",
            )
            self.lct = current_last_closed_candle_ts
            return True
        self.lg.debug(
            f"No new closed candle for {self.s}. Last candle: {self.lct}, Current last closed: {current_last_closed_candle_ts}. Still awaiting the next temporal shift.{RST}",
        )
        return False

    def _cet(self, exit_reason: str, current_price: Decimal) -> bool:
        """Close Existing Trade: Executes the closing of an open position."""
        current_open_trade = tt.open_trades.get(self.s)
        if not current_open_trade:
            self.lg.info(
                f"{NB}No open trade found for {self.s} to close. The position is already clear.{RST}",
            )
            return True

        self.lg.info(
            f"{NP}Attempting to close {current_open_trade.side.upper()} trade for {self.s} ({exit_reason}). Sealing the trade's fate!{RST}",
        )

        # Populate exit indicator fields before closing
        if self.ta_analyzer and hasattr(self.ta_analyzer, "iv"):
            current_open_trade.exit_rsi = self._get_indicator_value("RSI")
            current_open_trade.exit_ema_short = self._get_indicator_value("EMA_Short")
            current_open_trade.exit_ema_long = self._get_indicator_value("EMA_Long")
            current_open_trade.exit_bbl = self._get_indicator_value("BB_Lower")
            current_open_trade.exit_bbm = self._get_indicator_value("BB_Middle")
            current_open_trade.exit_bbu = self._get_indicator_value("BB_Upper")
            current_open_trade.exit_momentum = self._get_indicator_value("Momentum")
            current_open_trade.exit_cci = self._get_indicator_value("CCI")
            current_open_trade.exit_willr = self._get_indicator_value(
                "Williams_R", "WILLR",
            )
            current_open_trade.exit_mfi = self._get_indicator_value("MFI")
            current_open_trade.exit_vwap = self._get_indicator_value("VWAP")
            current_open_trade.exit_psar = self._get_psar_value()
            current_open_trade.exit_fisher = self._get_indicator_value("FISHERT")
            current_open_trade.exit_adx = self._get_indicator_value(
                "ATR",
            )  # Using ATR as per instruction
            self.lg.debug(f"Populated exit indicators for {self.s} in Tr object.")
        else:
            self.lg.warning(
                f"{NY}Could not populate exit indicators for {self.s}: ta_analyzer or iv not available.{RST}",
            )

        try:
            # Prioritize WebSocket's latest position update for immediate check
            refreshed_position = self.ws_client.get_latest_position_update(
                self.bybit_symbol_id,
            )
            if not refreshed_position:
                self.lg.debug(
                    f"No recent WS position update for {self.s}, fetching via REST for close confirmation.",
                )
                refreshed_position = gop(self.ex, self.s, self.mi, self.lg)

            # Check if position is already effectively closed (size near zero)
            # Use 'size' from WS data
            if not refreshed_position or abs(
                Decimal(str(refreshed_position.get("size", "0"))),
            ) <= Decimal("1e-9"):
                self.lg.info(
                    f"{NG}Position for {self.s} already closed or zero size after refresh. The trade was already sealed!{RST}",
                )
                latest_balance = fb(self.ex, QC, self.lg)
                if latest_balance is None:
                    self.lg.warning(
                        f"{NY}Could not fetch latest balance after closing trade for {self.s}. PnL calculation may be based on stale balance. The ledger is momentarily obscured.{RST}",
                    )
                    latest_balance = tt.current_balance

                # Call tt.ct first to populate the trade_record with PnL details
                tt.ct(
                    self.s,
                    exit_price=current_price,
                    exit_time=datetime.now(TZ),
                    current_balance=latest_balance,
                )

                # SMS Alert for trade closure (if already closed by exchange)
                enable_sms_alerts = self.cfg.get("enable_sms_alerts", False)
                sms_recipient_number = self.cfg.get("sms_recipient_number", "")
                sms_alert_on_trade_close = self.cfg.get(
                    "sms_alert_on_trade_close", True,
                )

                if (
                    enable_sms_alerts
                    and sms_recipient_number
                    and sms_alert_on_trade_close
                ):
                    # tt.ct would have moved the trade to closed_trades. Get the last one.
                    if tt.closed_trades and tt.closed_trades[-1].symbol == self.s:
                        closed_trade_record = tt.closed_trades[-1]
                        price_prec = TA.gpp(self.mi, self.lg)
                        sms_message = (
                            f"Pyrmascalp Trade Closed: {closed_trade_record.symbol} {closed_trade_record.side.upper()} "
                            f"exited due to {exit_reason} (already closed on exch). "
                            f"PnL: {closed_trade_record.realized_pnl_quote:.2f} {QC} ({closed_trade_record.pnl_percentage:.2f}%). "
                            f"Exit Price: {closed_trade_record.exit_price:.{price_prec}f}"
                        )
                        if send_termux_sms(sms_recipient_number, sms_message, self.lg):
                            self.lg.info(
                                f"{NB}Trade closure SMS alert sent for {self.s} (already closed).{RST}",
                            )
                        else:
                            self.lg.warning(
                                f"{NY}Failed to send trade closure SMS alert for {self.s} (already closed).{RST}",
                            )
                return True

            # Use 'size' from WS data
            position_size = abs(Decimal(str(refreshed_position.get("size", "0"))))
            trade_side_to_close = "SELL" if current_open_trade.side == "long" else "BUY"

            order_response = pt(
                exchange=self.ex,
                symbol=self.s,
                trade_side=trade_side_to_close,
                position_size=position_size,
                market_info=self.mi,
                logger=self.lg,
                order_type="market",
                reduce_only=True,
            )

            if order_response:
                self.lg.info(
                    f"{NG}Close order placed for {self.s}. Confirming position closure via WebSocket... A brief pause before confirmation.{RST}",
                )

                # Poll WebSocket cache for position closure
                start_time = time.time()
                while (
                    time.time() - start_time < PCDS
                ):  # PCDS seconds timeout for WS confirmation
                    latest_ws_position = self.ws_client.get_latest_position_update(
                        self.bybit_symbol_id,
                    )
                    if latest_ws_position and abs(
                        Decimal(str(latest_ws_position.get("size", "0"))),
                    ) <= Decimal("1e-9"):
                        self.lg.info(
                            f"{NG}Position for {self.s} confirmed CLOSED via WebSocket. The trade is complete!{RST}",
                        )
                        latest_balance = fb(self.ex, QC, self.lg)
                        if latest_balance is None:
                            latest_balance = tt.current_balance

                        # Attempt to get fees from the order response if available
                        fees = Decimal("0")
                        if order_response.get("fees"):
                            for fee_item in order_response["fees"]:
                                if fee_item.get("currency") == QC:
                                    fees += Decimal(str(fee_item.get("cost", "0")))

                        tt.ct(
                            self.s,
                            exit_price=current_price,
                            exit_time=datetime.now(TZ),
                            current_balance=latest_balance,
                            fees_in_quote=fees,
                        )

                        # SMS Alert for trade closure
                        enable_sms_alerts = self.cfg.get("enable_sms_alerts", False)
                        sms_recipient_number = self.cfg.get("sms_recipient_number", "")
                        sms_alert_on_trade_close = self.cfg.get(
                            "sms_alert_on_trade_close", True,
                        )

                        if (
                            enable_sms_alerts
                            and sms_recipient_number
                            and sms_alert_on_trade_close
                        ):
                            # Get the most recently closed trade
                            closed_trade_record = tt.closed_trades[-1]
                            if (
                                closed_trade_record
                                and closed_trade_record.symbol == self.s
                            ):
                                price_prec = TA.gpp(self.mi, self.lg)
                                sms_message = (
                                    f"Pyrmascalp Trade Closed: {closed_trade_record.symbol} {closed_trade_record.side.upper()} "
                                    f"exited due to {exit_reason}. "
                                    f"PnL: {closed_trade_record.realized_pnl_quote:.2f} {QC} ({closed_trade_record.pnl_percentage:.2f}%). "
                                    f"Exit Price: {closed_trade_record.exit_price:.{price_prec}f}"
                                )
                                if send_termux_sms(
                                    sms_recipient_number, sms_message, self.lg,
                                ):
                                    self.lg.info(
                                        f"{NB}Trade closure SMS alert sent for {self.s}.{RST}",
                                    )
                                else:
                                    self.lg.warning(
                                        f"{NY}Failed to send trade closure SMS alert for {self.s}.{RST}",
                                    )
                        return True
                    time.sleep(0.5)  # Check WebSocket data every 0.5 seconds

                self.lg.warning(
                    f"{NY}Position for {self.s} still detected open after close order and WebSocket monitoring timeout. Attempting to cancel lingering orders. The closing spell was incomplete!{RST}",
                )
                self._coo()  # Attempt to cancel any lingering orders
                # Final check via REST after cleanup
                final_position_check_rest = gop(self.ex, self.s, self.mi, self.lg)
                if not final_position_check_rest or abs(
                    final_position_check_rest.get("contractsDecimal", Decimal("0")),
                ) <= Decimal("1e-9"):
                    self.lg.info(
                        f"{NG}Position for {self.s} confirmed CLOSED after cleanup and REST check. The trade is complete!{RST}",
                    )
                    latest_balance = fb(self.ex, QC, self.lg)
                    if latest_balance is None:
                        latest_balance = tt.current_balance
                    # Fees from the initial order response are the best we can do here
                    fees = Decimal("0")
                    if order_response.get("fees"):
                        for fee_item in order_response["fees"]:
                            if fee_item.get("currency") == QC:
                                fees += Decimal(str(fee_item.get("cost", "0")))
                    tt.ct(
                        self.s,
                        exit_price=current_price,
                        exit_time=datetime.now(TZ),
                        current_balance=latest_balance,
                        fees_in_quote=fees,
                    )

                    # SMS Alert for trade closure (after cleanup)
                    enable_sms_alerts = self.cfg.get("enable_sms_alerts", False)
                    sms_recipient_number = self.cfg.get("sms_recipient_number", "")
                    sms_alert_on_trade_close = self.cfg.get(
                        "sms_alert_on_trade_close", True,
                    )

                    if (
                        enable_sms_alerts
                        and sms_recipient_number
                        and sms_alert_on_trade_close
                    ):
                        # Get the most recently closed trade
                        closed_trade_record = tt.closed_trades[-1]
                        if closed_trade_record and closed_trade_record.symbol == self.s:
                            price_prec = TA.gpp(self.mi, self.lg)
                            sms_message = (
                                f"Pyrmascalp Trade Closed: {closed_trade_record.symbol} {closed_trade_record.side.upper()} "
                                f"exited due to {exit_reason}. "
                                f"PnL: {closed_trade_record.realized_pnl_quote:.2f} {QC} ({closed_trade_record.pnl_percentage:.2f}%). "
                                f"Exit Price: {closed_trade_record.exit_price:.{price_prec}f}"
                            )
                            if send_termux_sms(
                                sms_recipient_number, sms_message, self.lg,
                            ):
                                self.lg.info(
                                    f"{NB}Trade closure SMS alert sent for {self.s} (after cleanup).{RST}",
                                )
                            else:
                                self.lg.warning(
                                    f"{NY}Failed to send trade closure SMS alert for {self.s} (after cleanup).{RST}",
                                )
                    return True
                self.lg.error(
                    f"{NR}Position for {self.s} remains open after all attempts to close. Manual intervention may be required!{RST}",
                )
                return False
            self.lg.error(
                f"{NR}Failed to place close order for {self.s}. The closing spell failed to cast!{RST}",
            )
            return False
        except Exception as e:
            self.lg.error(
                f"{NR}An unexpected error occurred while trying to close trade for {self.s}: {e}. A cosmic interference in sealing the trade!{RST}",
                exc_info=True,
            )
            return False

    def _coo(self) -> bool:
        """Cancel Open Orders: Cancels all active orders for the current symbol."""
        try:
            open_orders = self.ex.fetch_open_orders(self.s)
            if not open_orders:
                self.lg.debug(
                    f"No open orders found for {self.s}. The order scrolls are clear.{RST}",
                )
                return True

            self.lg.info(
                f"{NB}Cancelling {len(open_orders)} open orders for {self.s}... Dispelling lingering spells.{RST}",
            )
            for order in open_orders:
                try:
                    self.ex.cancel_order(order["id"], self.s)
                    self.lg.debug(
                        f"Cancelled order ID: {order['id']} for {self.s}. A spell revoked.{RST}",
                    )
                except ccxt.OrderNotFound:
                    self.lg.warning(
                        f"{NY}Order {order['id']} for {self.s} already cancelled or not found. It vanished!{RST}",
                    )
                except Exception as e:
                    self.lg.error(
                        f"{NR}Error cancelling order {order['id']} for {self.s}: {e}. The revocation spell faltered!{RST}",
                        exc_info=True,
                    )
            self.lg.info(
                f"{NG}All open orders for {self.s} attempted cancellation. The order scrolls are now clear.{RST}",
            )
            return True
        except ccxt.ExchangeError as e:
            self.lg.error(
                f"{NR}Exchange error fetching/cancelling open orders for {self.s}: {e}. The market's commands are confused!{RST}",
            )
        except ccxt.NetworkError as e:
            self.lg.error(
                f"{NR}Network error fetching/cancelling open orders for {self.s}: {e}. The digital currents are disrupted!{RST}",
            )
        except Exception as e:
            self.lg.error(
                f"{NR}Unexpected error fetching/cancelling open orders for {self.s}: {e}. A cosmic interference in order management!{RST}",
                exc_info=True,
            )
        return False

    def _tbe(self, position_info: dict) -> bool:
        """Time-Based Exit: Closes a trade if it has been open for longer than the configured duration."""
        time_based_exit_minutes = self.cfg.get("time_based_exit_minutes")
        if time_based_exit_minutes is None or time_based_exit_minutes <= 0:
            self.lg.debug(
                f"Time-based exit is disabled or configured for 0 minutes for {self.s}. Skipping check.{RST}",
            )
            return False

        open_trade = tt.open_trades.get(self.s)
        if not open_trade:
            self.lg.debug(
                f"No open trade for {self.s} to check for time-based exit. The position is already clear.{RST}",
            )
            return False

        time_open = datetime.now(TZ) - open_trade.entry_time
        if time_open.total_seconds() / 60 >= time_based_exit_minutes:
            self.lg.info(
                f"{NY}Time-based exit triggered for {self.s}. Trade open for {time_open.total_seconds() / 60:.2f} minutes (Threshold: {time_based_exit_minutes} minutes). The temporal limit has been reached!{RST}",
            )
            current_price = self.ws_client.get_last_price(self.bybit_symbol_id)
            if current_price is None:
                current_price = fcp(self.ex, self.s, self.lg)
                if current_price is None:
                    self.lg.error(
                        f"{NR}Could not get current price for {self.s} for time-based exit. Aborting exit attempt.{RST}",
                    )
                    return False
            return self._cet("Time-based exit", current_price)
        return False

    def _mp(self, current_price: Decimal) -> bool:
        """Manage Position: Checks for existing positions and applies TP/SL/TSL/Break-Even logic,
        including new exit strategies.
        Returns True if an open position is found and managed (action taken or protections checked), False otherwise.
        """
        # --- 1. Fetch Trade Record and Configuration ---
        current_open_trade = tt.open_trades.get(self.s)
        trade_modified_in_tracker = False  # Flag to save at the end

        # Initial check for live position if no trade record exists in tracker
        if not current_open_trade:
            pos_info_early_check = self.ws_client.get_latest_position_update(
                self.bybit_symbol_id,
            )
            if not pos_info_early_check:
                pos_info_early_check = gop(self.ex, self.s, self.mi, self.lg)

            # If no trade in tracker AND no live position on exchange, nothing to do.
            if not pos_info_early_check or abs(
                Decimal(
                    str(
                        pos_info_early_check.get(
                            "size", pos_info_early_check.get("contracts", "0"),
                        ),
                    ),
                ),
            ) < TA.gmts(self.mi, self.lg):
                self.lg.debug(
                    f"_mp: No open trade in tracker and no live position for {self.s}.",
                )
                return False

        # Fetch TSL configuration, ensuring Decimals
        try:
            tsl_profit_thresh_raw = self.cfg.get(
                "trailing_stop_profit_threshold_percentage", "0.001",
            )
            tsl_percentage_raw = self.cfg.get("trailing_stop_percentage", "0.005")
            tsl_profit_thresh = Decimal(str(tsl_profit_thresh_raw))
            tsl_percentage = Decimal(str(tsl_percentage_raw))
            if tsl_percentage <= Decimal("0"):  # TSL percentage must be positive
                self.lg.warning(
                    f"{NY}TSL percentage is zero or negative ({tsl_percentage}). Using default 0.005.{RST}",
                )
                tsl_percentage = Decimal("0.005")
        except InvalidOperation:
            self.lg.error(
                f"{NR}_mp: Invalid TSL configuration strings. Using default TSL values.{RST}",
            )
            tsl_profit_thresh = Decimal("0.001")
            tsl_percentage = Decimal("0.005")

        # Fetch live position info (pos_info)
        pos_info = self.ws_client.get_latest_position_update(self.bybit_symbol_id)
        if not pos_info:
            self.lg.debug(
                f"_mp: No WebSocket position data for {self.s}, fetching via REST.",
            )
            pos_info = gop(self.ex, self.s, self.mi, self.lg)

        # Handle discrepancy: trade in tracker, but not on exchange (e.g. manual close, SL/TP hit)
        # Use 'size' from WS or 'contractsDecimal' from gop
        live_pos_size_raw = (
            pos_info.get("size")
            if pos_info and "size" in pos_info
            else (pos_info.get("contractsDecimal") if pos_info else None)
        )
        live_pos_size = (
            Decimal(str(live_pos_size_raw))
            if live_pos_size_raw is not None
            else Decimal("0")
        )

        if abs(live_pos_size) < TA.gmts(
            self.mi, self.lg,
        ):  # Position effectively closed
            if current_open_trade:  # But tracker still has it open
                self.lg.warning(
                    f"{NY}_mp: Trade tracker shows open trade for {self.s}, but exchange reports no/zero position. Forcing closure in tracker.{RST}",
                )
                latest_balance = fb(self.ex, QC, self.lg) or tt.current_balance
                exit_price_for_calc = (
                    current_price
                    if current_price and current_price > 0
                    else current_open_trade.entry_price
                )
                tt.ct(self.s, exit_price_for_calc, datetime.now(TZ), latest_balance)
                self._coo()  # Cancel any lingering orders for this symbol
            return False  # No live position to manage

        # Reconstruct trade record if missing in tracker but live on exchange
        if not current_open_trade:
            self.lg.warning(
                f"{NY}_mp: Exchange reports open position for {self.s}, but no trade tracker record. Reconstructing.{RST}",
            )
            entry_price_raw = pos_info.get(
                "entryPriceDecimal",
                pos_info.get("avgPrice", pos_info.get("entryPrice")),
            )
            leverage_raw = pos_info.get("leverage", self.cfg.get("leverage", 1))

            if (
                entry_price_raw is None
                or live_pos_size == Decimal("0")
                or leverage_raw is None
            ):
                self.lg.error(
                    f"{NR}_mp: Cannot reconstruct trade for {self.s} due to missing critical info: entry={entry_price_raw}, size={live_pos_size}, lev={leverage_raw}.{RST}",
                )
                return False  # Cannot proceed with managing this unknown position

            entry_price_dec = Decimal(str(entry_price_raw))
            leverage_dec = Decimal(str(leverage_raw))
            if leverage_dec == Decimal("0"):
                leverage_dec = Decimal("1")  # Avoid division by zero

            initial_capital_est = (entry_price_dec * abs(live_pos_size)) / leverage_dec
            if initial_capital_est <= Decimal("0"):
                initial_capital_est = Decimal("1")

            current_open_trade = Tr(
                symbol=self.s,
                side=pos_info.get(
                    "side", "long" if live_pos_size > 0 else "short",
                ),  # Infer side if missing
                entry_price=entry_price_dec,
                entry_time=datetime.now(TZ) - timedelta(minutes=1),  # Estimate
                size=abs(live_pos_size),
                leverage=leverage_dec,
                initial_capital=initial_capital_est,
                highest_price_reached=entry_price_dec
                if (pos_info.get("side") == "long" or live_pos_size > 0)
                else None,
                lowest_price_reached=entry_price_dec
                if (pos_info.get("side") == "short" or live_pos_size < 0)
                else None,
                tsl_activated=False,  # Default for reconstructed trades
            )
            sl_from_pos = pos_info.get("stopLossPrice") or pos_info.get("stopLoss")
            tp_from_pos = pos_info.get("takeProfitPrice") or pos_info.get("takeProfit")
            current_open_trade.stop_loss_price = (
                Decimal(str(sl_from_pos))
                if sl_from_pos and str(sl_from_pos) != "0"
                else None
            )
            current_open_trade.take_profit_price = (
                Decimal(str(tp_from_pos))
                if tp_from_pos and str(tp_from_pos) != "0"
                else None
            )
            tt.aot(current_open_trade)
            trade_modified_in_tracker = True
            self.lg.info(
                f"{NB}_mp: Reconstructed trade record for {self.s} added to tracker.{RST}",
            )

        # --- 2. Update PnL and Peak Prices ---
        if not isinstance(current_price, Decimal) or current_price <= 0:
            self.lg.error(
                f"{NR}_mp: Invalid current_price ({current_price}) for {self.s}. Cannot manage position.{RST}",
            )
            if trade_modified_in_tracker:
                tt._save_trades()  # Save if reconstruction happened
            return True  # Position exists, but issue with current price

        current_open_trade.upnl(current_price, self.mi, self.lg)

        # Ensure entry_price is Decimal for comparisons
        entry_price = current_open_trade.entry_price
        if not isinstance(
            entry_price, Decimal,
        ):  # Should not happen if Tr is well-managed
            entry_price = Decimal(str(entry_price))
            self.lg.warning(
                f"{NY}_mp: current_open_trade.entry_price was not Decimal. Converted: {entry_price}",
            )

        if current_open_trade.side == "long":
            if current_open_trade.highest_price_reached is None:  # Initialize if None
                current_open_trade.highest_price_reached = entry_price
                trade_modified_in_tracker = True
            if current_price > current_open_trade.highest_price_reached:
                current_open_trade.highest_price_reached = current_price
                trade_modified_in_tracker = True
        else:  # Short trade
            if current_open_trade.lowest_price_reached is None:  # Initialize if None
                current_open_trade.lowest_price_reached = entry_price
                trade_modified_in_tracker = True
            if current_price < current_open_trade.lowest_price_reached:
                current_open_trade.lowest_price_reached = current_price
                trade_modified_in_tracker = True

        # --- 3. TSL Activation Logic ---
        if (
            not current_open_trade.tsl_activated
            and current_open_trade.pnl_percentage is not None
            and current_open_trade.pnl_percentage >= tsl_profit_thresh
        ):
            current_open_trade.tsl_activated = True
            trade_modified_in_tracker = True
            self.lg.info(
                f"{NG}TSL activated for {self.s} at profit {current_open_trade.pnl_percentage:.2f}%.{RST}",
            )

            if current_open_trade.side == "long":
                current_open_trade.highest_price_reached = (
                    current_price  # Reset peak price at TSL activation
                )
            else:
                current_open_trade.lowest_price_reached = (
                    current_price  # Reset peak price at TSL activation
                )

            # Cancel fixed Take Profit if it exists on exchange
            live_tp_raw = pos_info.get("takeProfitPrice") or pos_info.get("takeProfit")
            live_tp_on_exchange = (
                Decimal(str(live_tp_raw))
                if live_tp_raw and str(live_tp_raw) != "0"
                else None
            )

            if live_tp_on_exchange is not None:
                self.lg.info(
                    f"{NB}Cancelling existing Take Profit ({live_tp_on_exchange}) for {self.s} as TSL is now active.{RST}",
                )
                sl_to_preserve_raw = pos_info.get("stopLossPrice") or pos_info.get(
                    "stopLoss",
                )
                sl_to_preserve = (
                    Decimal(str(sl_to_preserve_raw))
                    if sl_to_preserve_raw and str(sl_to_preserve_raw) != "0"
                    else None
                )

                stsl_tp_cancel_success = stsl(
                    exchange=self.ex,
                    symbol=self.s,
                    market_info=self.mi,
                    position_info=pos_info,
                    config=self.cfg,
                    logger=self.lg,
                    take_profit_price_target=Decimal("0"),  # Signal to cancel TP
                    fixed_stop_loss_price=sl_to_preserve,
                    attempt_tsl=False,
                )
                if stsl_tp_cancel_success:
                    current_open_trade.take_profit_price = None
                    trade_modified_in_tracker = True
                else:
                    self.lg.warning(
                        f"{NY}Failed to cancel Take Profit for {self.s} during TSL activation.{RST}",
                    )
            else:
                self.lg.info(
                    f"{NB}No Take Profit found on exchange for {self.s} during TSL activation. No TP cancellation needed.{RST}",
                )

        # --- 4. TSL Price Calculation & Order Placement (if tsl_activated) ---
        if current_open_trade.tsl_activated:
            new_tsl_price: Decimal | None = None
            min_tick_size = TA.gmts(self.mi, self.lg)

            if (
                current_open_trade.side == "long"
                and current_open_trade.highest_price_reached is not None
            ):
                calc_tsl = current_open_trade.highest_price_reached * (
                    Decimal("1") - tsl_percentage
                )
                if min_tick_size > Decimal("0"):
                    new_tsl_price = (calc_tsl / min_tick_size).quantize(
                        Decimal("1"), rounding=ROUND_UP,
                    ) * min_tick_size
                else:
                    price_prec = TA.gpp(self.mi, self.lg)
                    new_tsl_price = calc_tsl.quantize(
                        Decimal("1e-" + str(price_prec)), rounding=ROUND_UP,
                    )

            elif (
                current_open_trade.side == "short"
                and current_open_trade.lowest_price_reached is not None
            ):
                calc_tsl = current_open_trade.lowest_price_reached * (
                    Decimal("1") + tsl_percentage
                )
                if min_tick_size > Decimal("0"):
                    new_tsl_price = (calc_tsl / min_tick_size).quantize(
                        Decimal("1"), rounding=ROUND_DOWN,
                    ) * min_tick_size
                else:
                    price_prec = TA.gpp(self.mi, self.lg)
                    new_tsl_price = calc_tsl.quantize(
                        Decimal("1e-" + str(price_prec)), rounding=ROUND_DOWN,
                    )

            if new_tsl_price is not None and new_tsl_price > Decimal("0"):
                current_sl_on_record = (
                    current_open_trade.stop_loss_price
                )  # From our tracker
                should_update_sl = False

                if current_open_trade.side == "long":
                    if (
                        new_tsl_price > entry_price
                    ):  # Ensure TSL is profitable or at entry
                        if (
                            current_sl_on_record is None
                            or new_tsl_price > current_sl_on_record
                        ):
                            should_update_sl = True
                elif current_open_trade.side == "short":
                    if (
                        new_tsl_price < entry_price
                    ):  # Ensure TSL is profitable or at entry
                        if (
                            current_sl_on_record is None
                            or new_tsl_price < current_sl_on_record
                        ):
                            should_update_sl = True

                significant_change = True
                if current_sl_on_record is not None and min_tick_size > Decimal("0"):
                    significant_change = abs(new_tsl_price - current_sl_on_record) >= (
                        min_tick_size / Decimal("2")
                    )

                if should_update_sl and significant_change:
                    self.lg.info(
                        f"{NG}Updating TSL for {self.s} from {current_sl_on_record} to {new_tsl_price}. Peak: {current_open_trade.highest_price_reached if current_open_trade.side == 'long' else current_open_trade.lowest_price_reached}{RST}",
                    )
                    update_success = stsl(
                        exchange=self.ex,
                        symbol=self.s,
                        market_info=self.mi,
                        position_info=pos_info,
                        config=self.cfg,
                        logger=self.lg,
                        fixed_stop_loss_price=new_tsl_price,
                        take_profit_price_target=Decimal(
                            "0",
                        ),  # TSL implies TP is managed by TSL exit or manual close
                        attempt_tsl=False,
                    )
                    if update_success:
                        current_open_trade.stop_loss_price = new_tsl_price
                        current_open_trade.take_profit_price = (
                            None  # TSL overrides fixed TP
                        )
                        trade_modified_in_tracker = True
                        self.lg.info(
                            f"{NG}TSL for {self.s} successfully updated to {new_tsl_price} on exchange.{RST}",
                        )
                    else:
                        self.lg.warning(
                            f"{NY}Failed to update TSL for {self.s} to {new_tsl_price} on exchange.{RST}",
                        )
                elif new_tsl_price is not None:
                    self.lg.debug(
                        f"TSL for {self.s} ({current_open_trade.side}) calculated to {new_tsl_price}. Current SL: {current_sl_on_record}. No update needed based on conditions (profitable: {new_tsl_price > entry_price if current_open_trade.side == 'long' else new_tsl_price < entry_price}, ratchet: {current_sl_on_record is None or (new_tsl_price > current_sl_on_record if current_open_trade.side == 'long' else new_tsl_price < current_sl_on_record)}, significant: {significant_change}).",
                    )
            elif new_tsl_price is not None and new_tsl_price <= Decimal("0"):
                self.lg.warning(
                    f"{NY}_mp: Calculated TSL price for {self.s} is zero or negative ({new_tsl_price}). Skipping TSL update.{RST}",
                )

        # --- 5. Advanced Exit Strategies (Profit-Taking Biased) ---
        exit_strategies_cfg = self.cfg.get("exit_strategies", {})
        min_profit_req_pct = exit_strategies_cfg.get(
            "min_profit_percentage_for_advanced_exits", Decimal("0.25"),
        )
        pnl_percentage = (
            current_open_trade.pnl_percentage
            if current_open_trade.pnl_percentage is not None
            else Decimal("-100")
        )  # Treat None PnL as not profitable

        is_profitable_enough_for_adv_exit = pnl_percentage >= min_profit_req_pct

        if is_profitable_enough_for_adv_exit:
            self.lg.debug(
                f"_mp: Trade {self.s} is profitable enough ({pnl_percentage:.2f}% >= {min_profit_req_pct:.2f}%) for advanced exits.",
            )
            if exit_strategies_cfg.get("opposing_signal_enabled", False):
                self.lg.debug(f"_mp: Checking opposing signal exit for {self.s}.")
                orderbook_data = None
                if (
                    self.cfg.get("indicators", {}).get("orderbook", False)
                    and self.cfg.get("weight_sets", {})
                    .get(self.ta_analyzer.aw_name, {})
                    .get("orderbook", Decimal(0))
                    > 0
                ):
                    try:
                        orderbook_data = fobc(
                            self.ex,
                            self.s,
                            self.cfg.get("orderbook_limit", 25),
                            self.lg,
                        )
                    except Exception as e_ob:
                        self.lg.warning(
                            f"{NY}_mp: Could not fetch orderbook for {self.s} for opposing signal check: {e_ob}{RST}",
                        )

                _ = self.ta_analyzer.gts(current_price, orderbook_data)
                opposing_signal_score = self.ta_analyzer.final_signal_score
                opp_threshold = exit_strategies_cfg.get(
                    "opposing_signal_threshold", Decimal("0.5"),
                )

                if (
                    current_open_trade.side == "long"
                    and opposing_signal_score <= -opp_threshold
                ):
                    self.lg.info(
                        f"{NY}_mp: Opposing signal (SELL score {opposing_signal_score:.2f} <= -{opp_threshold}) detected for LONG {self.s}. Triggering exit.{RST}",
                    )
                    if self._cet(
                        f"Opposing Signal (Score: {opposing_signal_score:.2f})",
                        current_price,
                    ):
                        if trade_modified_in_tracker:
                            tt._save_trades()
                        return True
                elif (
                    current_open_trade.side == "short"
                    and opposing_signal_score >= opp_threshold
                ):
                    self.lg.info(
                        f"{NY}_mp: Opposing signal (BUY score {opposing_signal_score:.2f} >= {opp_threshold}) detected for SHORT {self.s}. Triggering exit.{RST}",
                    )
                    if self._cet(
                        f"Opposing Signal (Score: {opposing_signal_score:.2f})",
                        current_price,
                    ):
                        if trade_modified_in_tracker:
                            tt._save_trades()
                        return True

            if exit_strategies_cfg.get("extreme_oscillator_enabled", False):
                self.lg.debug(f"_mp: Checking extreme oscillator exit for {self.s}.")
                extreme_count = 0
                iv = self.ta_analyzer.iv
                thresholds = self.cfg.get("indicator_thresholds", {})
                rsi_val, mfi_val, stoch_k_val = (
                    iv.get("RSI"),
                    iv.get("MFI"),
                    iv.get("Adaptive_STOCHk"),
                )

                if current_open_trade.side == "long":
                    if (
                        rsi_val is not None
                        and not rsi_val.is_nan()
                        and rsi_val
                        >= Decimal(
                            str(thresholds.get("rsi_extreme_sell_threshold", "80.0")),
                        )
                    ):
                        extreme_count += 1
                    if (
                        mfi_val is not None
                        and not mfi_val.is_nan()
                        and mfi_val
                        >= Decimal(
                            str(thresholds.get("mfi_extreme_sell_threshold", "90.0")),
                        )
                    ):
                        extreme_count += 1
                    if (
                        stoch_k_val is not None
                        and not stoch_k_val.is_nan()
                        and stoch_k_val
                        >= Decimal(
                            str(
                                thresholds.get(
                                    "adaptive_stoch_extreme_sell_threshold", "90.0",
                                ),
                            ),
                        )
                    ):
                        extreme_count += 1
                elif current_open_trade.side == "short":
                    if (
                        rsi_val is not None
                        and not rsi_val.is_nan()
                        and rsi_val
                        <= Decimal(
                            str(thresholds.get("rsi_extreme_buy_threshold", "20.0")),
                        )
                    ):
                        extreme_count += 1
                    if (
                        mfi_val is not None
                        and not mfi_val.is_nan()
                        and mfi_val
                        <= Decimal(
                            str(thresholds.get("mfi_extreme_buy_threshold", "10.0")),
                        )
                    ):
                        extreme_count += 1
                    if (
                        stoch_k_val is not None
                        and not stoch_k_val.is_nan()
                        and stoch_k_val
                        <= Decimal(
                            str(
                                thresholds.get(
                                    "adaptive_stoch_extreme_buy_threshold", "10.0",
                                ),
                            ),
                        )
                    ):
                        extreme_count += 1

                if extreme_count >= 2:
                    self.lg.info(
                        f"{NY}_mp: Extreme oscillator condition (count: {extreme_count}) met for {self.s}. Triggering exit.{RST}",
                    )
                    if self._cet(
                        f"Extreme Oscillator (Count: {extreme_count})", current_price,
                    ):
                        if trade_modified_in_tracker:
                            tt._save_trades()
                        return True
        else:
            self.lg.debug(
                f"_mp: Trade {self.s} not profitable enough ({pnl_percentage:.2f}% < {min_profit_req_pct:.2f}%) for advanced exits.",
            )

        # --- Standard Fixed Protections (if TSL not active) & Break-Even ---
        if not current_open_trade.tsl_activated:
            self.lg.debug(
                f"_mp: TSL not active for {self.s}. Managing fixed SL/TP and Break-Even.",
            )
            _, tp_target_from_cets, sl_target_from_cets = self.ta_analyzer.cets(
                entry_price, current_open_trade.side.upper(),
            )

            live_tp_raw = pos_info.get("takeProfitPrice") or pos_info.get("takeProfit")
            live_tp_on_exchange = (
                Decimal(str(live_tp_raw))
                if live_tp_raw and str(live_tp_raw) != "0"
                else None
            )

            # Manage Fixed Take Profit (only if TSL is not active)
            if tp_target_from_cets and (
                live_tp_on_exchange is None
                or abs(live_tp_on_exchange - tp_target_from_cets)
                > TA.gmts(self.mi, self.lg)
            ):
                self.lg.info(
                    f"{NB}_mp: Updating fixed Take Profit for {self.s} to {tp_target_from_cets}. Current on exch: {live_tp_on_exchange}{RST}",
                )
                sl_to_use_with_tp = (
                    current_open_trade.stop_loss_price
                    if current_open_trade.stop_loss_price
                    else sl_target_from_cets
                )
                stsl_tp_success = stsl(
                    exchange=self.ex,
                    symbol=self.s,
                    market_info=self.mi,
                    position_info=pos_info,
                    config=self.cfg,
                    logger=self.lg,
                    take_profit_price_target=tp_target_from_cets,
                    fixed_stop_loss_price=sl_to_use_with_tp,
                    attempt_tsl=False,
                )
                if stsl_tp_success:
                    current_open_trade.take_profit_price = tp_target_from_cets
                    trade_modified_in_tracker = True

            # Manage Break-Even (only if TSL is not active, as _cbe sets a fixed SL)
            # if self._cbe(current_price, pos_info): # _cbe call removed
            #     trade_modified_in_tracker = True
            #     # _cbe might have modified SL in trade_record via stsl.
            #     # If BE logic moved SL, we can consider it "managed" for this cycle.
            #     self.lg.info(f"{NB}_mp: Break-even logic executed for {self.s}. Position might have new SL.{RST}")
            #     # Note: _cbe itself calls stsl. If it returns True, an SL update was attempted.
            #     # We might not need to re-evaluate other SL logic in this same pass if BE adjusted it.

        # --- 6. Time-Based Exit ---
        if self._tbe(pos_info):  # _tbe calls _cet if triggered
            if trade_modified_in_tracker:
                tt._save_trades()  # Save if any prior modifications
            return True

        # --- 7. Save Trade Record if modified ---
        if trade_modified_in_tracker:
            tt._save_trades()
            self.lg.debug(
                f"_mp: Trade record for {self.s} saved due to modifications in TSL, peak prices or protections.{RST}",
            )

        return True  # Position exists and was managed

    def _check_and_set_fixed_protections(
        self,
        position_info: dict,
        target_sl_price: Decimal | None,
        target_tp_price: Decimal | None,
        current_trade_record: Tr,
        min_tick_size: Decimal,
    ):
        """Helper function to check and set fixed SL and TP.
        DEPRECATED: Logic moved to stsl and _mp main flow.
        """
        # This function is no longer needed as its logic is integrated into _mp calling stsl.

    def _ot(
        self, signal: str, current_price: Decimal, orderbook_data: dict | None,
    ) -> bool:
        """Open Trade: Executes a new trade based on the generated signal."""
        if not self.cfg.get("enable_trading", False):
            self.lg.info(
                f"{NB}Trading is disabled in config for {self.s}. Skipping trade execution. The market's gates are closed!{RST}",
            )
            return False

        if signal not in ["BUY", "SELL"]:
            self.lg.debug(
                f"No BUY/SELL signal for {self.s}. Skipping trade opening. The market's direction is unclear.{RST}",
            )
            return False

        if self.s in tt.open_trades:
            self.lg.info(
                f"{NB}Already have an open trade for {self.s}. Skipping new trade opening. A journey is already underway!{RST}",
            )
            return False

        if len(tt.open_trades) >= self.cfg.get("max_concurrent_positions", 1):
            self.lg.info(
                f"{NB}Max concurrent positions ({self.cfg.get('max_concurrent_positions', 1)}) reached. Skipping new trade for {self.s}. Too many quests at once!{RST}",
            )
            return False

        if not isinstance(current_price, Decimal) or current_price <= 0:
            self.lg.error(
                f"{NR}Cannot open trade for {self.s}: Invalid current price ({current_price}). The market's value is obscured!{RST}",
            )
            return False

        # Calculate initial TP/SL based on current price and ATR
        entry_price_estimate, take_profit_price, stop_loss_price = (
            self.ta_analyzer.cets(entry_price_estimate=current_price, signal=signal)
        )

        if stop_loss_price is None:
            self.lg.error(
                f"{NR}Cannot open trade for {self.s}: Stop loss price could not be determined. The safety net is missing!{RST}",
            )
            return False

        current_balance = fb(self.ex, QC, self.lg)
        if current_balance is None or current_balance <= 0:
            self.lg.error(
                f"{NR}Cannot open trade for {self.s}: Insufficient or unknown balance ({current_balance} {QC}). The coffers are empty!{RST}",
            )
            return False

        tt.sib(current_balance)  # Set initial balance if not already set

        position_size = cps(
            balance=current_balance,
            risk_per_trade=self.cfg.get("risk_per_trade", Decimal("0.01")),
            initial_stop_loss_price=stop_loss_price,
            entry_price=current_price,
            market_info=self.mi,
            exchange=self.ex,
            logger=self.lg,
        )

        if position_size is None or position_size <= 0:
            self.lg.error(
                f"{NR}Cannot open trade for {self.s}: Position size calculation failed or resulted in zero/negative. The magnitude of the spell is void!{RST}",
            )
            return False

        order_type = self.cfg.get("entry_order_type", "market")
        limit_price: Decimal | None = None
        if order_type == "limit":
            offset_multiplier = self.cfg.get(
                "limit_order_offset_buy"
                if signal == "BUY"
                else "limit_order_offset_sell",
                Decimal("0.0005"),
            )
            if signal == "BUY":
                limit_price = current_price * (Decimal("1.0") - offset_multiplier)
            else:
                limit_price = current_price * (Decimal("1.0") + offset_multiplier)

            # Ensure limit price is quantized to market precision
            price_precision = TA.gpp(self.mi, self.lg)
            min_tick_size = TA.gmts(self.mi, self.lg)
            if min_tick_size > 0:
                limit_price = (limit_price / min_tick_size).quantize(
                    Decimal("1"), rounding=ROUND_HALF_EVEN,
                ) * min_tick_size
            else:
                limit_price = limit_price.quantize(
                    Decimal("1e-" + str(price_precision)), rounding=ROUND_HALF_EVEN,
                )

            self.lg.info(
                f"{NB}Calculated limit price for {self.s} {signal}: {limit_price:.{price_precision}f} (Current: {current_price:.{price_precision}f}, Offset: {offset_multiplier:.4f}). Setting a precise entry point.{RST}",
            )

        order_response = pt(
            exchange=self.ex,
            symbol=self.s,
            trade_side=signal,
            position_size=position_size,
            market_info=self.mi,
            logger=self.lg,
            order_type=order_type,
            limit_price=limit_price,
        )

        if order_response:
            # For market orders, the fill price is the entry price. For limit, it's the limit price or average fill.
            # Robustly determine actual_entry_price
            price_to_convert = None
            avg_price_from_response = order_response.get("average")
            price_from_response = order_response.get("price")

            if avg_price_from_response is not None:
                price_to_convert = avg_price_from_response
            elif price_from_response is not None:
                price_to_convert = price_from_response
            else:
                price_to_convert = current_price  # Fallback to current_price

            if price_to_convert is None:
                self.lg.error(
                    f"{NR}_ot ({self.s}): All price sources (average, price, current_price) for actual_entry_price are None. Cannot determine entry price.{RST}",
                )
                # Depending on desired strictness, could raise an error or return False
                self._coo()  # Attempt to cancel any lingering orders from the failed trade
                return False

            try:
                actual_entry_price = Decimal(str(price_to_convert))
                if actual_entry_price <= 0:
                    self.lg.error(
                        f"{NR}_ot ({self.s}): actual_entry_price is zero or negative ({actual_entry_price}) from source '{price_to_convert}'. Aborting trade.{RST}",
                    )
                    self._coo()
                    return False
            except InvalidOperation as e:
                self.lg.error(
                    f"{NR}_ot ({self.s}): Failed to convert price '{price_to_convert}' to Decimal for actual_entry_price: {e}. Aborting trade.{RST}",
                )
                self._coo()
                return False

            # Re-calculate TP/SL based on actual entry price
            final_entry_price, final_tp_price, final_sl_price = self.ta_analyzer.cets(
                entry_price_estimate=actual_entry_price, signal=signal,
            )

            tt.aot(
                Tr(
                    symbol=self.s,
                    side=signal.lower(),
                    entry_price=final_entry_price,
                    entry_time=datetime.now(TZ),
                    size=position_size,
                    leverage=Decimal(str(self.cfg.get("leverage", 1))),
                    initial_capital=current_balance
                    * self.cfg.get("risk_per_trade", Decimal("0.01")),
                    stop_loss_price=final_sl_price,
                    take_profit_price=final_tp_price,
                    # Populate entry indicator fields directly in the constructor
                    entry_rsi=self._get_indicator_value("RSI"),
                    entry_ema_short=self._get_indicator_value("EMA_Short"),
                    entry_ema_long=self._get_indicator_value("EMA_Long"),
                    entry_bbl=self._get_indicator_value("BB_Lower"),
                    entry_bbm=self._get_indicator_value("BB_Middle"),
                    entry_bbu=self._get_indicator_value("BB_Upper"),
                    entry_momentum=self._get_indicator_value("Momentum"),
                    entry_cci=self._get_indicator_value("CCI"),
                    entry_willr=self._get_indicator_value("Williams_R", "WILLR"),
                    entry_mfi=self._get_indicator_value("MFI"),
                    entry_vwap=self._get_indicator_value("VWAP"),
                    entry_psar=self._get_psar_value(),
                    entry_fisher=self._get_indicator_value("FISHERT"),
                    entry_adx=self._get_indicator_value(
                        "ATR",
                    ),  # Using ATR as per instruction
                ),
            )  # Ensure Tr call and aot call are closed

            # Set TP/SL/TSL on the exchange
            if self.mi.get("is_contract", False):
                trade_to_protect = tt.open_trades.get(self.s)
                if trade_to_protect:  # Ensure trade record exists
                    protection_info_dict = trade_to_protect.to_dict()
                    # Convert Decimal fields back for spp/stsl if they expect Decimals from dict
                    protection_info_dict["entryPriceDecimal"] = (
                        trade_to_protect.entry_price
                    )
                    # Add other necessary Decimal fields if spp/stsl use them from position_info dict.
                    # For now, spp primarily uses passed Decimal args or position_info['info']

                    protection_set_successfully = False
                    # Determine if TSL should be attempted immediately
                    attempt_immediate_tsl = False
                    # position_info for stsl should ideally be fresh from gop after order confirmation,
                    # or use trade_to_protect.to_dict() and ensure stsl can use its fields.
                    # For simplicity, we'll pass the newly created trade_record's data,
                    # assuming stsl can derive necessary info like entry price and side from it if position_info is sparse.
                    # However, stsl expects position_info to have 'entryPriceDecimal' and 'side'.
                    # Let's fetch fresh position_info after order confirmation.

                    self.lg.info(
                        f"{NB}_ot: Confirming position details for {self.s} before setting protections...{RST}",
                    )
                    # Wait a moment for the position to be fully registered on the exchange
                    time.sleep(self.cfg.get("position_confirm_delay_seconds", PCDS))
                    confirmed_position_info = gop(self.ex, self.s, self.mi, self.lg)

                    if (
                        confirmed_position_info
                        and confirmed_position_info.get("contractsDecimal", Decimal(0))
                        > 0
                    ):
                        # Determine if TSL should be attempted immediately
                        attempt_immediate_tsl = False
                        if self.cfg.get("enable_trailing_stop", False):
                            activation_percentage = self.cfg.get(
                                "trailing_stop_activation_percentage", Decimal("0.003"),
                            )
                            # Immediate activation
                            if activation_percentage == Decimal("0"):
                                attempt_immediate_tsl = True

                        if attempt_immediate_tsl:
                            self.lg.info(
                                f"{NB}_ot: Attempting immediate TSL for {self.s} (Entry: {trade_to_protect.entry_price}). TP: {final_tp_price}.{RST}",
                            )
                            stsl(
                                exchange=self.ex,
                                symbol=self.s,
                                market_info=self.mi,
                                position_info=confirmed_position_info,  # Pass live position data
                                config=self.cfg,
                                logger=self.lg,
                                fixed_stop_loss_price=None,
                                take_profit_price_target=final_tp_price,
                                attempt_tsl=True,
                            )
                        else:
                            self.lg.info(
                                f"{NB}_ot: Setting initial fixed SL ({final_sl_price}) and TP ({final_tp_price}) for {self.s}. TSL not immediate or disabled.{RST}",
                            )
                            stsl(
                                exchange=self.ex,
                                symbol=self.s,
                                market_info=self.mi,
                                position_info=confirmed_position_info,  # Pass live position data
                                config=self.cfg,
                                logger=self.lg,
                                fixed_stop_loss_price=final_sl_price,
                                take_profit_price_target=final_tp_price,
                                attempt_tsl=False,
                            )
                    else:
                        self.lg.error(
                            f"{NR}_ot: Position for {self.s} not confirmed or size is zero after opening. Cannot set protections.{RST}",
                        )
                else:
                    self.lg.error(
                        f"{NR}_ot: Trade record for {self.s} not found immediately after creation. Cannot set protections.{RST}",
                    )
            else:
                self.lg.info(
                    f"{NB}TP/SL setting skipped for {self.s} (Spot market). Spot trades do not support TP/SL orders directly on the exchange.{RST}",
                )

            self.lg.info(
                f"{NG}Trade opened successfully for {self.s}! The new quest is underway!{RST}",
            )
            return True
        self.lg.error(
            f"{NR}Failed to open trade for {self.s}. The opening spell failed!{RST}",
        )
        self._coo()  # Attempt to cancel any lingering orders if trade failed
        return False

    def run_symbol_logic(self):
        """Main logic loop for a single symbol. Fetches data, calculates indicators,
        generates signals, and manages trades.
        """
        self.lg.info(
            f"{NP}--- Running logic for {self.s} ({self.cfg.get('interval')}m interval) ---{RST}",
        )

        # 1. Fetch OHLCV data
        kline_data = pd.DataFrame()
        try:
            kline_data = fkc(
                self.ex,
                self.s,
                CIM.get(self.cfg["interval"]),
                limit=self.cfg.get("fibonacci_window", DIP["fib_window"]) + 50,
                logger=self.lg,
            )
        except Exception as e:
            self.lg.error(
                f"{NR}Failed to fetch kline data for {self.s}: {e}. Skipping logic.{RST}",
            )
            return

        if kline_data.empty:
            self.lg.warning(
                f"{NY}Skipping logic for {self.s}: No kline data available. The historical records are missing!{RST}",
            )
            return

        # 2. Check for new closed candle
        if not self._cfnc(kline_data):
            self.lg.debug(
                f"No new closed candle for {self.s}. Skipping indicator recalculation and signal generation.{RST}",
            )
            # If no new candle, we still want to manage existing positions and update PnL
            current_price = self.ws_client.get_last_price(self.bybit_symbol_id)
            if current_price is None:
                current_price = fcp(self.ex, self.s, self.lg)
            if current_price is None:
                self.lg.error(
                    f"{NR}Could not get current price for {self.s} for position management. Skipping.{RST}",
                )
                return
            self._mp(current_price)
            return

        # 3. Initialize/Update TA Analyzer with new kline data
        self.ta_analyzer = TA(kline_data, self.lg, self.cfg, self.mi)
        self.ta_analyzer._uliv()  # Ensure latest values are updated after _cai

        current_price = self.ws_client.get_last_price(self.bybit_symbol_id)
        if current_price is None:
            self.lg.warning(
                f"{NY}WebSocket price for {self.s} not available, falling back to REST fetch.{RST}",
            )
            current_price = fcp(self.ex, self.s, self.lg)

        if current_price is None:
            self.lg.error(
                f"{NR}Skipping logic for {self.s}: Could not get current price. The market's pulse is silent!{RST}",
            )
            return

        # 4. Fetch Order Book data (if enabled)
        orderbook_data = None
        if self.cfg.get("indicators", {}).get("orderbook", False):
            try:
                orderbook_data = fobc(
                    self.ex, self.s, self.cfg.get("orderbook_limit", 25), self.lg,
                )
            except Exception as e:
                self.lg.warning(
                    f"{NY}Orderbook data for {self.s} could not be fetched: {e}. Orderbook indicator will be skipped.{RST}",
                )

        # 5. Manage existing position first
        position_managed = self._mp(current_price)

        # 6. Generate trade signal only if no position is open or if it was just closed
        if not position_managed:
            signal = self.ta_analyzer.gts(current_price, orderbook_data)
            if signal in ["BUY", "SELL"]:
                self.lg.info(
                    f"{NG}TRADE SIGNAL for {self.s}: {signal}! The stars align for a new venture!{RST}",
                )
                self._ot(signal, current_price, orderbook_data)
            else:
                self.lg.info(
                    f"{NB}No strong trade signal for {self.s}. Holding steady. The market's intentions are ambiguous.{RST}",
                )
        else:
            self.lg.info(
                f"{NB}Position for {self.s} is active and being managed. Skipping new signal generation.{RST}",
            )

        self.lg.info(f"{NP}--- Finished logic for {self.s} ---{RST}")


class MainBot:
    """Main Bot orchestrator: Initializes exchanges, manages per-symbol bots,
    and runs the main trading loop.
    """

    def __init__(self):
        self.lg = slg("main")
        self.cfg = _icfs
        self.ex: ccxt.Exchange | None = None
        self.per_symbol_bots: dict[str, PB] = {}
        self.ws_client: BybitWebSocketClient | None = None
        self.is_running = False
        self.last_pnl_sms_time = time.time()

    def initialize(self):
        """Initializes the exchange connection and per-symbol bots."""
        self.lg.info(f"{NP}--- Initializing XR Scalper Bot ---{RST}")
        self.ex = ie(self.cfg, self.lg)
        if not self.ex:
            self.lg.critical(
                f"{NR}Exchange initialization failed. Exiting. The trading realm remains inaccessible!{RST}",
            )
            sys.exit(1)

        if self.ex:  # Ensure ex is initialized
            # Pass the exchange instance to the global tt
            tt.set_exchange_reference(self.ex)

        # Determine the correct public WebSocket endpoint based on market type
        # For Bybit, linear contracts (like USDT perpetuals) use '/linear' endpoint
        # Spot markets use '/spot', inverse contracts use '/inverse'
        # Default to linear for now, but ideally this should be dynamic per symbol's market type
        public_ws_base_url = (
            "wss://stream.bybit.com/v5/public/linear"  # Default to linear
        )
        if self.cfg.get("use_sandbox", True):
            public_ws_base_url = "wss://stream-testnet.bybit.com/v5/public/linear"
            self.lg.warning(f"{NY}WebSocket client is configured for TESTNET.{RST}")

        # Initialize WebSocket client with the correct base URL
        self.ws_client = BybitWebSocketClient(
            api_key=AK,
            api_secret=AS,
            use_testnet=self.cfg.get("use_sandbox", True),
            logger=slg("websocket"),
            public_base_url=public_ws_base_url,  # Pass the determined public base URL
        )

        public_topics = []
        # Always subscribe to order and position updates
        private_topics = ["order", "position"]

        for symbol_str in self.cfg.get("symbols_to_trade", []):
            try:
                per_symbol_bot = PB(
                    symbol_str,
                    self.ex,
                    self.cfg,
                    slg(symbol_str.replace("/", "_").replace(":", "_")),
                    self.ws_client,
                )
                self.per_symbol_bots[symbol_str] = per_symbol_bot

                # Add ticker topic for each symbol
                bybit_symbol_id = per_symbol_bot.mi.get("id")
                if bybit_symbol_id:
                    public_topics.append(f"tickers.{bybit_symbol_id}")
                else:
                    self.lg.warning(
                        f"{NY}Could not get Bybit symbol ID for {symbol_str}, skipping ticker subscription.{RST}",
                    )

            except ValueError as e:
                self.lg.error(
                    f"{NR}Failed to initialize bot for symbol {symbol_str}: {e}. Skipping this symbol. A specific enchantment failed!{RST}",
                )
            except Exception as e:
                self.lg.error(
                    f"{NR}Unexpected error initializing bot for symbol {symbol_str}: {e}. Skipping this symbol. A cosmic interference!{RST}",
                    exc_info=True,
                )

        if not self.per_symbol_bots:
            self.lg.critical(
                f"{NR}No symbols successfully initialized. Exiting. The bot has no markets to observe!{RST}",
            )
            sys.exit(1)

        self.ws_client.start(public_topics, private_topics)
        self.lg.info(
            f"{NG}XR Scalper Bot initialized successfully. The trading journey is ready to begin!{RST}",
        )
        self.is_running = True

        # SMS Alert for Bot Startup
        if self.cfg.get("enable_sms_alerts", False):
            recipient_number = self.cfg.get("sms_recipient_number", "")
            if recipient_number:
                startup_message = "Pyrmascalp Bot Started Successfully."
                if send_termux_sms(recipient_number, startup_message, self.lg):
                    self.lg.info(
                        f"{NB}Bot startup SMS alert sent to {recipient_number}.{RST}",
                    )
                else:
                    self.lg.warning(
                        f"{NY}Failed to send bot startup SMS alert to {recipient_number}.{RST}",
                    )
            else:
                self.lg.info(
                    f"{NB}SMS alerts enabled, but no recipient number configured. Skipping startup SMS.{RST}",
                )
        else:
            self.lg.info(f"{NB}SMS alerts disabled. Skipping startup SMS.{RST}")

    def run(self):
        """Runs the main trading loop."""
        self.lg.info(f"{NP}--- Starting XR Scalper Bot Main Loop ---{RST}")
        last_run_time = {}
        # Convert minutes to seconds
        interval_seconds = int(self.cfg.get("interval", "5")) * 60

        while self.is_running:
            try:
                current_time = time.time()
                for symbol, bot in self.per_symbol_bots.items():
                    # Check if enough time has passed for the symbol's interval
                    if (
                        symbol not in last_run_time
                        or (current_time - last_run_time[symbol]) >= interval_seconds
                    ):
                        bot.run_symbol_logic()
                        last_run_time[symbol] = current_time
                    else:
                        self.lg.debug(
                            f"Waiting for next interval for {symbol}. Next run in {interval_seconds - (current_time - last_run_time[symbol]):.1f}s.{RST}",
                        )

                # --- Update Terminal UI ---
                clear_screen()
                tt.dm()  # Display overall metrics

                # Ensure ws_client is available before accessing its properties
                if self.ws_client:
                    display_open_positions(
                        open_trades=tt.open_trades,
                        market_infos=tt.mi,  # tt.mi is populated by PB instances
                        current_prices=self.ws_client.last_prices,
                        quote_currency=QC,
                        logger=self.lg,
                    )
                    display_recent_closed_trades(
                        closed_trades=tt.closed_trades,
                        market_infos=tt.mi,
                        quote_currency=QC,
                        logger=self.lg,
                        num_to_display=5,
                    )
                else:
                    self.lg.warning(
                        f"{NY}WebSocket client not available, cannot display open positions or current prices.{RST}",
                    )

                # Sleep for a short period to avoid busy-waiting and allow WS updates
                # Periodic PnL SMS Update Logic
                enable_sms_alerts = self.cfg.get("enable_sms_alerts", False)
                sms_recipient_number = self.cfg.get("sms_recipient_number", "")
                enable_periodic_pnl_sms = self.cfg.get("enable_periodic_pnl_sms", False)
                periodic_pnl_sms_interval_minutes = self.cfg.get(
                    "periodic_pnl_sms_interval_minutes", 60,
                )

                if (
                    enable_sms_alerts
                    and sms_recipient_number
                    and enable_periodic_pnl_sms
                ):
                    current_time_for_pnl = time.time()
                    elapsed_time_seconds = current_time_for_pnl - self.last_pnl_sms_time
                    if elapsed_time_seconds >= (periodic_pnl_sms_interval_minutes * 60):
                        total_unrealized_pnl = Decimal("0")
                        num_open_positions = len(tt.open_trades)
                        # display_open_positions called earlier in the loop should have updated individual trade PnLs
                        for trade_record in tt.open_trades.values():
                            if trade_record.pnl_quote is not None:
                                total_unrealized_pnl += trade_record.pnl_quote

                        pnl_summary_message = (
                            f"Pyrmascalp PnL Update: {num_open_positions} open trades. "
                            f"Total Unrealized PnL: {total_unrealized_pnl:.2f} {QC}. "
                            f"Current Balance: {tt.current_balance:.2f} {QC}."
                        )
                        self.lg.info(
                            f"{NB}Attempting to send periodic PnL SMS: {pnl_summary_message}{RST}",
                        )
                        if send_termux_sms(
                            sms_recipient_number, pnl_summary_message, self.lg,
                        ):
                            self.lg.info(
                                f"{NG}Periodic PnL SMS alert sent successfully.{RST}",
                            )
                        else:
                            self.lg.warning(
                                f"{NY}Failed to send periodic PnL SMS alert.{RST}",
                            )
                        self.last_pnl_sms_time = current_time_for_pnl

                time.sleep(self.cfg.get("retry_delay", RDS))

            except KeyboardInterrupt:
                self.lg.info(
                    f"{NY}KeyboardInterrupt detected. Stopping bot... The user has commanded a halt!{RST}",
                )
                self.stop()
            except Exception as e:
                self.lg.error(
                    f"{NR}An unexpected error occurred in the main loop: {e}. A cosmic interference in the bot's operation!{RST}",
                    exc_info=True,
                )
                time.sleep(
                    self.cfg.get("retry_delay", RDS) * 2,
                )  # Longer delay on error

    def stop(self):
        """Stops the bot, closes connections, and displays metrics."""
        self.is_running = False
        self.lg.info(f"{NP}--- Stopping XR Scalper Bot ---{RST}")
        if self.ws_client:
            self.ws_client.stop()

        # Ensure all open orders are cancelled before stopping
        for symbol, bot in self.per_symbol_bots.items():
            self.lg.info(
                f"{NB}Attempting to cancel all open orders for {symbol} before shutdown...{RST}",
            )
            bot._coo()

        self.lg.info(f"{NG}Bot stopped. The trading session has concluded!{RST}")

        # SMS Alert for Bot Shutdown
        if self.cfg.get("enable_sms_alerts", False):
            recipient_number = self.cfg.get("sms_recipient_number", "")
            if recipient_number:
                shutdown_message = "Pyrmascalp Bot Stopping."
                if send_termux_sms(recipient_number, shutdown_message, self.lg):
                    self.lg.info(
                        f"{NB}Bot shutdown SMS alert sent to {recipient_number}.{RST}",
                    )
                else:
                    self.lg.warning(
                        f"{NY}Failed to send bot shutdown SMS alert to {recipient_number}.{RST}",
                    )
            else:
                self.lg.info(
                    f"{NB}SMS alerts enabled, but no recipient number configured. Skipping shutdown SMS.{RST}",
                )
        else:
            self.lg.info(f"{NB}SMS alerts disabled. Skipping shutdown SMS.{RST}")

        tt.dm()  # Display final metrics


if __name__ == "__main__":
    bot = MainBot()
    try:
        bot.initialize()
        bot.run()
    except Exception as final_e:
        bot.lg.critical(
            f"{NR}Bot encountered a critical error during initialization or main loop execution: {final_e}. Aborting!{RST}",
            exc_info=True,
        )
    finally:
        if bot.is_running:  # Ensure stop is called if bot was running but crashed
            bot.stop()
        bot.lg.info(f"{NP}--- XR Scalper Bot process finished ---{RST}")
