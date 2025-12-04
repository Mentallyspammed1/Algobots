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
from pybit.unified_trading import HTTP


class PybitAPIException(Exception):
    """Custom exception for Pybit API errors."""


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
NB: Final[str] = Fore.CYAN + Style.BRIGHT  # Information, process updates
NP: Final[str] = Fore.MAGENTA + Style.BRIGHT  # Headers, important messages, prompts
NY: Final[str] = Fore.YELLOW + Style.BRIGHT  # Warnings, cautions, user input prompts
NR: Final[str] = Fore.LIGHTRED_EX + Style.BRIGHT  # Errors, critical failures, alerts
NC: Final[str] = Fore.CYAN + Style.BRIGHT  # General neutral information
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
TRP: Final[Path] = Path("trade_records.json")  # Trade records persistence path
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
REC: Final[list[int]] = [429, 500, 502, 503, 504]  # HTTP response codes for retries

# Default Indicator Parameters (DIP) - using Decimal for precision
DIP: Final[dict[str, int | Decimal]] = {
    "atr_period": 14,
    "cci_window": 20,
    "williams_r_window": 14,
    "mfi_window": 14,
    "stoch_rsi_window": 14,
    "stoch_window": 12,
    "k_window": 3,
    "d_window": 3,
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
    "ehlers_fisher_length": 10,  # Added Ehlers Fisher default length
}
FL: Final[list[Decimal]] = [
    Decimal("0.0"),
    Decimal("0.236"),
    Decimal("0.382"),
    Decimal("0.5"),
    Decimal("0.618"),
    Decimal("0.786"),
    Decimal("1.0"),
]  # Fibonacci Levels
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
        header_parts.append(
            f"{display_name:<{width}}",
        )  # Left align header text within cell
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
    pnl_columns: list[int] | None = None,  # Indices of columns to treat as PnL
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


class BybitUnifiedTrading:
    """Encapsulates Bybit Unified Trading Account API interactions using the pybit library.
    Handles order management, position adjustments, and account queries.
    """

    def __init__(
        self, api_key: str, api_secret: str, testnet: bool, logger: logging.Logger,
    ):
        self.logger = logger
        self.session = HTTP(
            testnet=testnet,
            api_key=api_key,
            api_secret=api_secret,
            # Set a default timeout for all requests
            # This can be overridden per request if needed
            timeout=30,
        )
        self.logger.info(
            f"{NB}BybitUnifiedTrading session initialized. Testnet: {testnet}. The trading conduit is open!{RST}",
        )

    @retry_api_call(
        catch_exceptions=(requests.exceptions.RequestException, PybitAPIException),
    )
    def query_api(self, method_name: str, **kwargs) -> dict[str, Any]:
        """Generic method to call any pybit session method and handle its response."""
        self.logger.debug(
            f"Calling Bybit API method '{method_name}' with params: {kwargs}",
        )
        try:
            method = getattr(self.session, method_name)
            response = method(**kwargs)
            if response and response.get("retCode") == 0:
                self.logger.debug(
                    f"API call '{method_name}' successful. Response: {response}",
                )
                return response
            error_msg = (
                response.get("retMsg", "Unknown error") if response else "No response"
            )
            ret_code = response.get("retCode", "N/A") if response else "N/A"
            self.logger.error(
                f"{NR}Bybit API call '{method_name}' failed. Code: {ret_code}, Message: {error_msg}. Full response: {response}{RST}",
            )
            raise PybitAPIException(f"Bybit API error: {error_msg} (Code: {ret_code})")
        except PybitAPIException:
            raise  # Re-raise custom exception
        except requests.exceptions.RequestException as e:
            self.logger.error(
                f"{NR}Network or request error during Bybit API call '{method_name}': {e}{RST}",
            )
            raise  # Re-raise network errors
        except Exception as e:
            self.logger.error(
                f"{NR}An unexpected error occurred during Bybit API call '{method_name}': {e}{RST}",
                exc_info=True,
            )
            raise

    def place_order(self, **kwargs) -> dict[str, Any]:
        """Place a new order."""
        return self.query_api("place_order", **kwargs)

    def cancel_order(self, **kwargs) -> dict[str, Any]:
        """Cancel an existing order."""
        return self.query_api("cancel_order", **kwargs)

    def amend_order(self, **kwargs) -> dict[str, Any]:
        """Modify an existing order."""
        return self.query_api("amend_order", **kwargs)

    def cancel_all_orders(self, **kwargs) -> dict[str, Any]:
        """Cancel all orders for a category or settleCoin."""
        return self.query_api("cancel_all_orders", **kwargs)

    def set_trading_stop(self, **kwargs) -> dict[str, Any]:
        """Sets or modifies TP/SL for an existing position (Derivatives only)."""
        return self.query_api("set_trading_stop", **kwargs)

    def get_wallet_balance(self, **kwargs) -> dict[str, Any]:
        """Query wallet balance across different coin types."""
        return self.query_api("get_wallet_balance", **kwargs)

    def get_account_info(self, **kwargs) -> dict[str, Any]:
        """Retrieve account information."""
        return self.query_api("get_account_info", **kwargs)

    def get_fee_rates(self, **kwargs) -> dict[str, Any]:
        """Retrieve fee rates."""
        return self.query_api("get_fee_rates", **kwargs)


def clear_screen() -> None:
    """Clears the terminal screen using ANSI escape codes."""
    print("\033[H\033[J", end="")

    """Clears the terminal screen using ANSI escape codes."""
    print("\033[H\033[J", end="")


def display_open_positions(
    open_trades: dict[str, "Tr"],
    market_infos: dict[str, dict],
    current_prices: dict[
        str, Decimal | None,
    ],  # Keyed by Bybit Symbol ID (e.g., BTCUSDT)
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
            dist_str = (
                f"{trade_record.trailing_stop_distance:.{price_prec}f}"
                if trade_record.trailing_stop_distance
                else "N/A"
            )  # Assuming distance is price units
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
                if (
                    dist_sl_pct < 0.5
                ):  # Example: If distance is less than 0.5% (closer to SL)
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
                if (
                    0 < dist_tp_pct < 0.5
                ):  # Example: If positive and distance is less than 0.5% (closer to TP)
                    dist_tp_color = NG

        row_data_list = [
            trade_record.symbol,
            trade_record.side.upper(),
            f"{trade_record.size:.{size_prec}f}",
            f"{trade_record.entry_price:.{price_prec}f}",
            f"{current_price:.{price_prec}f}" if current_price is not None else "N/A",
            trade_record.pnl_quote if trade_record.pnl_quote is not None else "N/A",
            (
                trade_record.pnl_percentage
                if trade_record.pnl_percentage is not None
                else "N/A"
            ),
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
            NR,  # SL Info
            NG,  # TP Info
            dist_sl_color,  # Dist SL%
            dist_tp_color,  # Dist TP%
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
    closed_trades: list["Tr"],
    market_infos: dict[str, dict],
    quote_currency: str,
    logger: logging.Logger,  # For TA.gpp
    num_to_display: int = 5,
) -> None:
    """Displays recently closed positions in a neon-themed table."""
    print_neon_header(
        f"Recent Closed Trades (Last {num_to_display})", color=NP, length=130,
    )

    if not closed_trades:
        print(f"{NY}No closed trades yet.{RST}")
        print_neon_separator(length=130, color=NP)
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
            size_prec = TA.gpp(
                market_info, logger,
            )  # Or use a specific amount precision if available

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
            (
                f"{trade_record.entry_price:.{price_prec}f}"
                if trade_record.entry_price
                else "N/A"
            ),
            (
                f"{trade_record.exit_price:.{price_prec}f}"
                if trade_record.exit_price
                else "N/A"
            ),
            (
                trade_record.realized_pnl_quote
                if trade_record.realized_pnl_quote is not None
                else "N/A"
            ),
            (
                trade_record.pnl_percentage
                if trade_record.pnl_percentage is not None
                else "N/A"
            ),
            status_text,
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
        ]

        print_table_row(
            row_data_list,
            column_widths,
            cell_colors=cell_custom_colors,
            default_color=NC,
            pnl_columns=[5, 6],  # Indices for rPnL (Quote) and rPnL (%)
            decimal_precision=(
                4 if quote_currency != "USDT" else 2
            ),  # PnL quote precision
        )

    print_neon_separator(length=130, color=NP)
    print("")


# --- SMS Alert Function ---
def send_sms_alert(
    message: str, recipient_number: str, logger: logging.Logger, config: dict[str, Any],
) -> bool:
    """Sends an SMS alert using Termux API if enabled in config.
    Returns True if SMS was sent or alerts are disabled, False if sending failed.
    """
    if not config.get("enable_sms_alerts", False):
        logger.debug("SMS alerts are disabled in config. Skipping.")
        return True  # Considered success as no action was needed

    if not recipient_number or not isinstance(recipient_number, str):
        logger.error(
            f"{NR}SMS recipient number is not configured or invalid. Cannot send SMS.{RST}",
        )
        return False

    if not message or not isinstance(message, str):
        logger.error(f"{NR}SMS message is empty or invalid. Cannot send SMS.{RST}")
        return False

    # Sanitize message for shell command
    # Basic sanitization: remove backticks and limit length. More robust sanitization might be needed.
    sanitized_message = message.replace("`", "'").replace('"', "'")
    max_sms_length = 1500  # Generous limit, actual limits vary by carrier/device
    if len(sanitized_message) > max_sms_length:
        sanitized_message = sanitized_message[: max_sms_length - 3] + "..."
        logger.warning(
            f"{NY}SMS message truncated to {max_sms_length} characters.{RST}",
        )

    try:
        # Ensure recipient_number is also sanitized if it comes directly from config without validation elsewhere
        # However, phone numbers usually have a more restricted character set.
        # For the message, enclosing in double quotes is generally safer for shell.
        command = ["termux-sms-send", "-n", recipient_number, sanitized_message]
        logger.debug(f"Executing Termux SMS command: {' '.join(command)}")

        result = subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=30,
        )  # 30s timeout

        if result.returncode == 0:
            logger.info(
                f"{NG}SMS alert sent successfully to {recipient_number}. Message: '{sanitized_message}'{RST}",
            )
            return True
        error_output = result.stderr or result.stdout or "No output"
        logger.error(
            f"{NR}Failed to send SMS alert via Termux. Return code: {result.returncode}. Error: {error_output.strip()}{RST}",
        )
        return False
    except FileNotFoundError:
        logger.error(
            f"{NR}Termux API command 'termux-sms-send' not found. Is Termux API installed and configured?{RST}",
        )
        return False
    except subprocess.TimeoutExpired:
        logger.error(f"{NR}Termux SMS command timed out after 30 seconds.{RST}")
        return False
    except Exception as e:
        logger.error(
            f"{NR}An unexpected error occurred while sending SMS: {e}{RST}",
            exc_info=True,
        )
        return False


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
        "atr_period": DIP["atr_period"],
        "ema_short_period": DIP["ema_short_period"],
        "ema_long_period": DIP["ema_long_period"],
        "rsi_period": DIP["rsi_window"],
        "bollinger_bands_period": DIP["bollinger_bands_period"],
        "bollinger_bands_std_dev": DIP["bollinger_bands_std_dev"],
        "cci_window": DIP["cci_window"],
        "williams_r_window": DIP["williams_r_window"],
        "mfi_window": DIP["mfi_window"],
        "stoch_rsi_window": DIP["stoch_rsi_window"],
        "stoch_rsi_rsi_window": DIP["stoch_window"],
        "stoch_rsi_k": DIP["k_window"],
        "stoch_rsi_d": DIP["d_window"],
        "psar_af": DIP["psar_af"],
        "psar_max_af": DIP["psar_max_af"],
        "sma_10_window": DIP["sma_10_window"],
        "momentum_period": DIP["momentum_period"],
        "volume_ma_period": DIP["volume_ma_period"],
        "orderbook_limit": 25,
        "signal_score_threshold": Decimal("1.5"),
        "ehlers_fisher_length": DIP[
            "ehlers_fisher_length"
        ],  # Added Ehlers Fisher length parameter
        "stoch_rsi_oversold_threshold": 25,
        "stoch_rsi_overbought_threshold": 75,
        "stop_loss_multiple": Decimal("1.8"),
        "take_profit_multiple": Decimal("0.7"),
        "atr_sl_period": 14,
        "atr_sl_multiplier": Decimal("1.5"),  # New ATR SL params
        "atr_tp_period": 14,
        "atr_tp_multiplier": Decimal("1.0"),  # New ATR TP params
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
        "enable_trailing_stop": True,
        "trailing_stop_callback_rate": Decimal("0.005"),
        "trailing_stop_activation_percentage": Decimal("0.003"),
        "enable_break_even": True,
        "break_even_trigger_atr_multiple": Decimal("1.0"),
        "break_even_offset_ticks": 2,
        "position_confirm_delay_seconds": PCDS,
        "time_based_exit_minutes": None,  # Example: 240 for 4 hours
        "active_weight_set": "default",
        "indicator_thresholds": {  # New section for configurable indicator thresholds
            "momentum_positive_threshold": Decimal("0.001"),
            "momentum_strong_positive_threshold": Decimal("0.005"),
            "stoch_rsi_crossover_strength": 5,  # K-D difference for significant crossover
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
            "ehlers_fisher_buy_threshold": Decimal("0.5"),  # Added Fisher buy threshold
            "ehlers_fisher_sell_threshold": Decimal(
                "-0.5",
            ),  # Added Fisher sell threshold
            "ehlers_fisher_trend_confirmation_threshold": Decimal(
                "0.1",
            ),  # Added Fisher trend confirmation
        },
        "weight_sets": {
            "scalping": {
                "ema_alignment": Decimal("0.2"),
                "momentum": Decimal("0.3"),
                "volume_confirmation": Decimal("0.2"),
                "stoch_rsi": Decimal("0.6"),
                "rsi": Decimal("0.2"),
                "bollinger_bands": Decimal("0.3"),
                "vwap": Decimal("0.4"),
                "cci": Decimal("0.3"),
                "wr": Decimal("0.3"),
                "psar": Decimal("0.2"),
                "sma_10": Decimal("0.1"),
                "mfi": Decimal("0.2"),
                "orderbook": Decimal("0.15"),
                "ehlers_fisher": Decimal("0.2"),  # Added Fisher weight
            },
            "default": {
                "ema_alignment": Decimal("0.3"),
                "momentum": Decimal("0.2"),
                "volume_confirmation": Decimal("0.1"),
                "stoch_rsi": Decimal("0.4"),
                "rsi": Decimal("0.3"),
                "bollinger_bands": Decimal("0.2"),
                "vwap": Decimal("0.3"),
                "cci": Decimal("0.2"),
                "wr": Decimal("0.2"),
                "psar": Decimal("0.3"),
                "sma_10": Decimal("0.1"),
                "mfi": Decimal("0.2"),
                "orderbook": Decimal("0.1"),
                "ehlers_fisher": Decimal("0.2"),  # Added Fisher weight
            },
        },
        "indicators": {  # Enable/disable individual indicators
            "atr": True,
            "ema_alignment": True,
            "momentum": True,
            "volume_confirmation": True,
            "stoch_rsi": True,
            "rsi": True,
            "bollinger_bands": True,
            "vwap": True,
            "cci": True,
            "wr": True,
            "psar": True,
            "sma_10": True,
            "mfi": True,
            "orderbook": True,
            "ehlers_fisher": True,  # Added Fisher toggle
        },
        "enable_sms_alerts": False,
        "sms_recipient_number": "",
        "sms_report_interval_minutes": 60,
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
            "trailing_stop_callback_rate": {"min": Decimal("1e-9")},
            "trailing_stop_activation_percentage": {"min": Decimal("0")},
            "break_even_trigger_atr_multiple": {"min": Decimal("0")},
            "break_even_offset_ticks": {"min": 0, "is_int": True},
            "position_confirm_delay_seconds": {"min": 0, "is_int": True},
            "time_based_exit_minutes": {"min": 1, "is_int": True, "allow_none": True},
            "limit_order_offset_buy": {"min": Decimal("0")},
            "limit_order_offset_sell": {"min": Decimal("0")},
            "orderbook_limit": {"min": 1, "is_int": True},
            "stoch_rsi_oversold_threshold": {"min": 0, "max": 100, "is_int": True},
            "stoch_rsi_overbought_threshold": {"min": 0, "max": 100, "is_int": True},
            "atr_sl_period": {"min": 1, "is_int": True},
            "atr_sl_multiplier": {"min": Decimal("0.1")},
            "atr_tp_period": {"min": 1, "is_int": True},
            "atr_tp_multiplier": {"min": Decimal("0.1")},
            "sms_report_interval_minutes": {
                "min": 1,
                "is_int": True,
                "allow_none": False,
            },  # allow_none: False, must have a value
        }

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

        # Validate enable_sms_alerts
        if not isinstance(user_config.get("enable_sms_alerts"), bool):
            logger.warning(
                f"{NR}Invalid type for 'enable_sms_alerts' ({user_config.get('enable_sms_alerts')}). Must be boolean. Setting to default '{default_config['enable_sms_alerts']}'. The alert rune is misshapen!{RST}",
            )
            user_config["enable_sms_alerts"] = default_config["enable_sms_alerts"]
            save_needed = True

        # Validate sms_recipient_number
        sms_recipient = user_config.get("sms_recipient_number")
        if not isinstance(sms_recipient, str):
            logger.warning(
                f"{NR}Invalid type for 'sms_recipient_number' ({sms_recipient}). Must be a string. Setting to default '{default_config['sms_recipient_number']}'. The recipient's address is unclear!{RST}",
            )
            user_config["sms_recipient_number"] = default_config["sms_recipient_number"]
            save_needed = True
        # Basic validation for non-empty string (more complex validation is out of scope)
        # This is a basic check; actual phone number validation is complex.
        # We'll just log a warning if it's not empty and contains characters other than digits, +, -, (, ), space.
        # This is a very lenient check.
        if sms_recipient and not all(
            c.isdigit() or c in ["+", "-", "(", ")", " "] for c in sms_recipient
        ):
            logger.warning(
                f"{NY}Config value 'sms_recipient_number' ('{sms_recipient}') contains characters that might not be valid for a phone number. Ensure it is correct. The recipient's address seems unusual!{RST}",
            )
            # No correction here, just a warning.

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
                max_val_for_psar_af = Decimal(
                    "1.0",
                )  # psar_af can go up to 1.0 in theory, but usually small
                max_val_for_psar_max_af = Decimal(
                    "1.0",
                )  # psar_max_af can also go up to 1.0, but typically 0.2

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
    base_name = "pscalp2"
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
        PybitAPIException,
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
def ie(
    config: dict[str, Any], logger: logging.Logger,
) -> tuple[ccxt.Exchange | None, BybitUnifiedTrading | None]:
    """Initialize Exchange: Connects to the cryptocurrency exchange.
    Handles sandbox mode, market loading, and initial balance fetch to confirm connection.
    Returns a CCXT exchange instance or a BybitUnifiedTrading instance.
    """
    exchange_id = config.get("exchange_id", "bybit").lower()
    use_sandbox = config.get("use_sandbox", False)

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

    if not hasattr(ccxt, exchange_id):
        logger.error(
            f"{NR}Exchange ID '{exchange_id}' not found in CCXT library. Please check config.json. The chosen realm does not exist!{RST}",
        )
        return None, None
    exchange_class = getattr(ccxt, exchange_id)
    ccxt_exchange = exchange_class(exchange_options)

    if use_sandbox:
        logger.warning(
            f"{NY}USING SANDBOX MODE (Testnet) for {ccxt_exchange.id}. Tread lightly, for this is a training ground!{RST}",
        )
        if hasattr(ccxt_exchange, "set_sandbox_mode"):
            ccxt_exchange.set_sandbox_mode(True)
        else:
            logger.warning(
                f"{NY}{ccxt_exchange.id} does not support set_sandbox_mode via ccxt. Ensure API keys are configured for Testnet manually.{RST}",
            )
            # For Bybit, manually set the testnet URL if set_sandbox_mode is not available or doesn't work as expected
            if (
                ccxt_exchange.id == "bybit"
                and "testnet" not in ccxt_exchange.urls["api"]
            ):
                ccxt_exchange.urls["api"] = "https://api-testnet.bybit.com"
                logger.warning(
                    f"{NY}Manually set Bybit Testnet API URL: {ccxt_exchange.urls['api']}. A hidden path revealed!{RST}",
                )

    ccxt_exchange.load_markets()
    logger.info(
        f"{NB}CCXT exchange initialized ({ccxt_exchange.id}). Sandbox: {use_sandbox}. The connection is forged!{RST}",
    )

    bybit_api_instance: BybitUnifiedTrading | None = None
    if exchange_id == "bybit":
        logger.info(
            f"{NB}Initializing Bybit Unified Trading API... Forging the Bybit connection!{RST}",
        )
        try:
            bybit_api_instance = BybitUnifiedTrading(AK, AS, use_sandbox, logger)
            # Test connection by fetching account info
            account_info = bybit_api_instance.get_account_info()
            if account_info and account_info.get("retCode") == 0:
                logger.info(
                    f"{NG}Successfully connected to Bybit Unified Trading API. Account type: {account_info.get('result', {}).get('accountType')}. The Bybit conduit is strong!{RST}",
                )
            else:
                logger.error(
                    f"{NR}Failed to connect to Bybit Unified Trading API. Response: {account_info}{RST}",
                )
                bybit_api_instance = None  # Ensure it's None if connection fails
        except Exception as e:
            logger.error(
                f"{NR}Error initializing BybitUnifiedTrading: {e}{RST}", exc_info=True,
            )
            bybit_api_instance = None  # Ensure it's None if connection fails

    account_type = "CONTRACT"
    logger.info(
        f"{NB}Attempting initial balance fetch (Account Type: {account_type}) for {QC}... Probing the essence of your holdings.{RST}",
    )
    try:
        params = {"type": account_type} if ccxt_exchange.id == "bybit" else {}
        balance = ccxt_exchange.fetch_balance(params=params)
        available_quote = balance.get(QC, {}).get("free", "N/A")
        logger.info(
            f"{NG}Successfully connected and fetched initial balance. The coffers reveal their bounty!{RST} (Example: {QC} available: {available_quote})",
        )
    except ccxt.ExchangeError as be:
        logger.warning(
            f"{NY}Exchange error during initial balance fetch ({account_type}): {be}. Trying default fetch... A minor tremor in the realm.{RST}",
        )
        balance = ccxt_exchange.fetch_balance()
        available_quote = balance.get(QC, {}).get("free", "N/A")
        logger.info(
            f"{NG}Successfully fetched balance using default parameters. The path is clearer now!{RST} (Example: {QC} available: {available_quote})",
        )
    return ccxt_exchange, bybit_api_instance


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
        self.iv: dict[str, Decimal] = {}  # Store all indicator values as Decimal
        self.sig: dict[str, int] = {"BUY": 0, "SELL": 0, "HOLD": 1}
        self.aw_name = config.get("active_weight_set", "default")
        self.ws = config.get("weight_sets", {}).get(self.aw_name, {})
        self.fld: dict[str, Decimal] = {}
        self.tcn: dict[str, str | None] = {}
        self.indicator_thresholds = self.cfg.get("indicator_thresholds", {})

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
            "StochRSI_Len": self.cfg.get("stoch_rsi_window", DIP["stoch_rsi_window"]),
            "StochRSI_RSI_Len": self.cfg.get(
                "stoch_rsi_rsi_window", DIP["stoch_window"],
            ),
            "StochRSI_K": self.cfg.get("stoch_rsi_k", DIP["k_window"]),
            "StochRSI_D": self.cfg.get("stoch_rsi_d", DIP["d_window"]),
            "PSAR_AF": float(self.cfg.get("psar_af", DIP["psar_af"])),
            "PSAR_MaxAF": float(self.cfg.get("psar_max_af", DIP["psar_max_af"])),
            "Volume_MA_Period": self.cfg.get(
                "volume_ma_period", DIP["volume_ma_period"],
            ),
            # Ensure ehlers_fisher_length is sourced correctly for _gtcn's internal params_config
            "ehlers_fisher_length": self.cfg.get(
                "ehlers_fisher_length", DIP.get("ehlers_fisher_length", 10),
            ),
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
            "CCI": [
                f"CCI_{params_config['CCI']}",
                f"CCI_{params_config['CCI']}_0.015",
            ],  # CCI can have different constants
            "Williams_R": [f"WILLR_{params_config['Williams_R']}"],
            "MFI": [f"MFI_{params_config['MFI']}"],
            "VWAP": ["VWAP_D", "VWAP"],  # VWAP can be daily or general
            "PSAR_long": [f"PSARl_{psar_af_str}_{psar_max_af_str}", "PSARl"],
            "PSAR_short": [f"PSARs_{psar_af_str}_{psar_max_af_str}", "PSARs"],
            "SMA10": [f"SMA_{params_config['SMA10']}"],
            "StochRSI_K": [
                f"STOCHRSIk_{params_config['StochRSI_Len']}_{params_config['StochRSI_RSI_Len']}_{params_config['StochRSI_K']}_{params_config['StochRSI_D']}",
                f"STOCHRSIk_{params_config['StochRSI_Len']}_{params_config['StochRSI_RSI_Len']}_{params_config['StochRSI_K']}",
            ],
            "StochRSI_D": [
                f"STOCHRSId_{params_config['StochRSI_Len']}_{params_config['StochRSI_RSI_Len']}_{params_config['StochRSI_K']}_{params_config['StochRSI_D']}",
                f"STOCHRSId_{params_config['StochRSI_Len']}_{params_config['StochRSI_RSI_Len']}_{params_config['StochRSI_K']}",
            ],
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
            "Volume_MA": [
                f"VOL_SMA_{params_config['Volume_MA_Period']}",
            ],  # Custom name for volume SMA
            # Patterns now correctly use the ehlers_fisher_length from the internal params_config of _gtcn
            "FISHERT": [f"FISHERT_{params_config['ehlers_fisher_length']}_1"],
            "FISHERTs": [f"FISHERTs_{params_config['ehlers_fisher_length']}_1"],
        }

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
            "StochRSI_Len": self.cfg.get("stoch_rsi_window", DIP["stoch_rsi_window"]),
            "StochRSI_RSI_Len": self.cfg.get(
                "stoch_rsi_rsi_window", DIP["stoch_window"],
            ),
            "StochRSI_K": self.cfg.get("stoch_rsi_k", DIP["k_window"]),
            "StochRSI_D": self.cfg.get("stoch_rsi_d", DIP["d_window"]),
            "PSAR_AF": float(self.cfg.get("psar_af", DIP["psar_af"])),
            "PSAR_MaxAF": float(self.cfg.get("psar_max_af", DIP["psar_max_af"])),
            "Volume_MA_Period": self.cfg.get(
                "volume_ma_period", DIP["volume_ma_period"],
            ),
            "ehlers_fisher_length": self.cfg.get(
                "ehlers_fisher_length", 10,
            ),  # Default to 10 if not in config/DIP
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
        if indicators_config.get("stoch_rsi", False):
            required_periods.extend(
                [params_config["StochRSI_Len"], params_config["StochRSI_RSI_Len"]],
            )
        if indicators_config.get("rsi", False):
            required_periods.append(params_config["RSI"])
        if indicators_config.get("bollinger_bands", False):
            required_periods.append(params_config["BB_Period"])
        if indicators_config.get("volume_confirmation", False):
            required_periods.append(params_config["Volume_MA_Period"])
        if indicators_config.get("ehlers_fisher", False):
            required_periods.append(params_config["ehlers_fisher_length"])
        required_periods.append(self.cfg.get("fibonacci_window", DIP["fib_window"]))

        min_recommended_data = max(required_periods) + 20 if required_periods else 50
        min_recommended_data = max(min_recommended_data, 2)

        if len(self.d) < min_recommended_data:
            self.lg.warning(
                f"{NY}Insufficient data ({len(self.d)} points) for {self.s} to calculate all indicators reliably (min recommended: {min_recommended_data}). Results may contain NaNs. The data tapestry is too short!{RST}",
            )

        try:
            data_copy = self.d.copy()

            # General pre-casting for OHLCV columns to float64
            # This is done upfront to ensure all subsequent pandas-ta indicators
            # that might use these columns (e.g., mfi, vwap, etc.) receive float64 types.
            self.lg.debug(
                f"Pre-casting OHLCV data to float64 for {self.s}. Current dtypes: "
                f"H={data_copy['high'].dtype}, L={data_copy['low'].dtype}, "
                f"C={data_copy['close'].dtype}, V={data_copy['volume'].dtype}",
            )
            for col in ["high", "low", "close", "volume"]:
                if col in data_copy.columns:
                    data_copy[col] = data_copy[col].astype("float64")
            self.lg.debug(
                f"Post-casting OHLCV data for {self.s}. New dtypes: "
                f"H={data_copy['high'].dtype}, L={data_copy['low'].dtype}, "
                f"C={data_copy['close'].dtype}, V={data_copy['volume'].dtype}",
            )

            atr_period = params_config["ATR"]
            data_copy.ta.atr(length=atr_period, append=True)
            self.tcn["ATR"] = self._gtcn("ATR", data_copy)

            if indicators_config.get("ema_alignment", False):
                ema_short_period = params_config["EMA_Short"]
                ema_long_period = params_config["EMA_Long"]
                data_copy.ta.ema(length=ema_short_period, append=True)
                self.tcn["EMA_Short"] = self._gtcn("EMA_Short", data_copy)
                data_copy.ta.ema(length=ema_long_period, append=True)
                self.tcn["EMA_Long"] = self._gtcn("EMA_Long", data_copy)

            if indicators_config.get("momentum", False):
                momentum_period = params_config["Momentum"]
                data_copy.ta.mom(length=momentum_period, append=True)
                self.tcn["Momentum"] = self._gtcn("Momentum", data_copy)

            if indicators_config.get("cci", False):
                cci_period = params_config["CCI"]
                data_copy.ta.cci(length=cci_period, append=True)
                self.tcn["CCI"] = self._gtcn("CCI", data_copy)

            if indicators_config.get("wr", False):
                willr_period = params_config["Williams_R"]
                data_copy.ta.willr(length=willr_period, append=True)
                self.tcn["Williams_R"] = self._gtcn("Williams_R", data_copy)

            if indicators_config.get("mfi", False):
                mfi_period = params_config["MFI"]
                mfi_col_name = f"MFI_{mfi_period}"

                try:
                    # Explicitly cast required columns to float64 before MFI calculation
                    for col_to_cast in ["high", "low", "close", "volume"]:
                        if col_to_cast in data_copy.columns:
                            # Attempt to convert object/string types to numeric first
                            if pd.api.types.is_object_dtype(
                                data_copy[col_to_cast],
                            ) or pd.api.types.is_string_dtype(data_copy[col_to_cast]):
                                data_copy[col_to_cast] = pd.to_numeric(
                                    data_copy[col_to_cast], errors="coerce",
                                )
                            # Then cast to float64
                            data_copy[col_to_cast] = data_copy[col_to_cast].astype(
                                "float64",
                            )
                        else:
                            self.lg.warning(
                                f"MFI pre-casting: Column '{col_to_cast}' not found in data_copy for {self.s}. Skipping cast for this column.",
                            )

                    # Check for NaNs after conversion, which might indicate original non-numeric data
                    if (
                        data_copy[["high", "low", "close", "volume"]]
                        .isnull()
                        .any()
                        .any()
                    ):
                        self.lg.warning(
                            f"MFI calculation for {self.s}: Found NaN values in OHLCV data after attempting conversion. This might lead to MFI calculation issues.",
                        )

                    mfi_series = data_copy.ta.mfi(
                        length=mfi_period, append=False,
                    )  # Calculate MFI

                    if mfi_series is not None and not mfi_series.empty:
                        mfi_series = mfi_series.astype(
                            "float64", errors="ignore",
                        )  # Ensure MFI series itself is float64
                        data_copy[mfi_col_name] = mfi_series
                        self.tcn["MFI"] = mfi_col_name
                    else:
                        self.lg.warning(
                            f"MFI calculation for {self.s} returned None or empty series. Skipping MFI assignment.",
                        )
                        self.tcn["MFI"] = None
                except (ValueError, TypeError) as e:
                    self.lg.error(
                        f"MFI calculation failed for {self.s} due to {type(e).__name__}: {e}. Proceeding without MFI for this cycle. The money flow is obscured!",
                        exc_info=True,
                    )
                    self.tcn["MFI"] = None
                except Exception as e:  # Catch any other unexpected error during MFI
                    self.lg.error(
                        f"Unexpected error during MFI calculation for {self.s}: {e}. Proceeding without MFI. The money flow is unexpectedly obscured!",
                        exc_info=True,
                    )
                    self.tcn["MFI"] = None

            if indicators_config.get("vwap", False):
                # OHLCV columns are already pre-cast to float64.
                # VWAP calculation in pandas-ta should handle timezone naive conversion if necessary,
                # but it's good practice to ensure index is tz-naive if issues persist.
                if data_copy.index.tz is not None:
                    # This warning is for developer information, not a persistent issue for users.
                    self.lg.debug(
                        f"VWAP Calculation for {self.s}: DataFrame index is timezone-aware. "
                        f"pandas-ta.vwap typically expects a tz-naive index. Localizing to None.",
                    )
                    data_copy.index = data_copy.index.tz_localize(None)
                data_copy.ta.vwap(append=True)
                self.tcn["VWAP"] = self._gtcn("VWAP", data_copy)

            if indicators_config.get("psar", False):
                psar_af = params_config["PSAR_AF"]
                psar_max_af = params_config["PSAR_MaxAF"]
                psar_results = data_copy.ta.psar(af=psar_af, max_af=psar_max_af)
                if psar_results is not None and not psar_results.empty:
                    data_copy = pd.concat([data_copy, psar_results], axis=1)
                    self.tcn["PSAR_long"] = self._gtcn("PSAR_long", data_copy)
                    self.tcn["PSAR_short"] = self._gtcn("PSAR_short", data_copy)

            if indicators_config.get("sma_10", False):
                sma10_period = params_config["SMA10"]
                data_copy.ta.sma(length=sma10_period, append=True)
                self.tcn["SMA10"] = self._gtcn("SMA10", data_copy)

            if indicators_config.get("stoch_rsi", False):
                stochrsi_len = params_config["StochRSI_Len"]
                stochrsi_rsi_len = params_config["StochRSI_RSI_Len"]
                stochrsi_k = params_config["StochRSI_K"]
                stochrsi_d = params_config["StochRSI_D"]
                stochrsi_results = data_copy.ta.stochrsi(
                    length=stochrsi_len,
                    rsi_length=stochrsi_rsi_len,
                    k=stochrsi_k,
                    d=stochrsi_d,
                )
                if stochrsi_results is not None and not stochrsi_results.empty:
                    data_copy = pd.concat([data_copy, stochrsi_results], axis=1)
                    self.tcn["StochRSI_K"] = self._gtcn("StochRSI_K", data_copy)
                    self.tcn["StochRSI_D"] = self._gtcn("StochRSI_D", data_copy)

            if indicators_config.get("rsi", False):
                rsi_period = params_config["RSI"]
                data_copy.ta.rsi(length=rsi_period, append=True)
                self.tcn["RSI"] = self._gtcn("RSI", data_copy)

            if indicators_config.get("bollinger_bands", False):
                bb_period = params_config["BB_Period"]
                bb_std_dev = params_config["BB_StdDev"]
                bb_results = data_copy.ta.bbands(length=bb_period, std=bb_std_dev)
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

            if indicators_config.get("ehlers_fisher", False):
                ehlers_fisher_len = params_config["ehlers_fisher_length"]
                # pandas_ta.fisher uses a hardcoded signal length of 1 for FISHERTs_col
                fisher_results = data_copy.ta.fisher(
                    length=ehlers_fisher_len, append=True,
                )  # append=True might add FISHERT_len_1 and FISHERTs_len_1
                if fisher_results is not None and not fisher_results.empty:
                    # _gtcn will find based on params_config['ehlers_fisher_length'] and hardcoded signal 1
                    self.tcn["FISHERT"] = self._gtcn("FISHERT", data_copy)
                    self.tcn["FISHERTs"] = self._gtcn("FISHERTs", data_copy)
                else:
                    self.lg.warning(
                        f"{NY}Ehlers Fisher Transform calculation did not return results or returned empty for {self.s}.{RST}",
                    )

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

            # Ensure FISHERT and FISHERTs are also processed if their tcn entries exist
            for fisher_key in ["FISHERT", "FISHERTs"]:
                col_name = self.tcn.get(fisher_key)
                if col_name and col_name in latest_row.index:
                    value = latest_row[col_name]
                    if pd.notna(value):
                        try:
                            self.iv[fisher_key] = Decimal(str(value))
                        except (
                            ValueError,
                            TypeError,
                            InvalidOperation,
                        ) as conversion_error:
                            self.lg.warning(
                                f"{NY}Could not convert value for {fisher_key} ('{col_name}': {value}) for {self.s}. Storing NaN. Error: {conversion_error}. A numerical anomaly!{RST}",
                            )
                            self.iv[fisher_key] = Decimal(np.nan)
                    else:
                        self.iv[fisher_key] = Decimal(np.nan)
                elif col_name:  # col_name was in tcn but not in latest_row.index (should be rare after _cai)
                    self.lg.debug(
                        f"Indicator column '{col_name}' for key '{fisher_key}' not found in latest data row for {self.s} during _uliv specific check. Storing NaN.",
                    )
                    self.iv[fisher_key] = Decimal(np.nan)
                # If col_name is None (i.e., tcn[fisher_key] was not set), it means indicator was not calculated, so no value to update.

            verbose_values_log = {}
            price_precision = TA.gpp(self.mi, self.lg)
            for k, v in self.iv.items():
                if pd.notna(v):
                    if isinstance(v, Decimal):
                        # Apply specific precision for price-like indicators, general for others
                        is_price_like = k in [
                            "Open",
                            "High",
                            "Low",
                            "Close",
                            "ATR",
                            "BB_Lower",
                            "BB_Middle",
                            "BB_Upper",
                            "SMA10",
                            "VWAP",
                            "PSAR_long",
                            "PSAR_short",
                            "FISHERT",
                        ]
                        precision_for_log = price_precision if is_price_like else 6
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
                    (
                        min_tick_size
                        if min_tick_size > 0
                        else Decimal("1e-" + str(price_precision))
                    ),
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

    def _csr(self) -> Decimal:
        """Check StochRSI Score: Evaluates StochRSI K and D lines for overbought/oversold
        conditions and crossovers.
        """
        k_line = self.iv.get("StochRSI_K")
        d_line = self.iv.get("StochRSI_D")

        if pd.isna(k_line) or pd.isna(d_line):
            self.lg.debug(
                f"StochRSI check skipped for {self.s}: Missing K ({k_line}) or D ({d_line}) values. The inner oscillations are unclear.{RST}",
            )
            return Decimal(np.nan)

        oversold_threshold = Decimal(
            str(self.cfg.get("stoch_rsi_oversold_threshold", 25)),
        )
        overbought_threshold = Decimal(
            str(self.cfg.get("stoch_rsi_overbought_threshold", 75)),
        )
        crossover_strength = Decimal(
            str(self.indicator_thresholds.get("stoch_rsi_crossover_strength", 5)),
        )

        score = Decimal("0.0")

        if k_line < oversold_threshold and d_line < oversold_threshold:
            score = Decimal("1.0")
        elif k_line > overbought_threshold and d_line > overbought_threshold:
            score = Decimal("-1.0")

        difference = k_line - d_line
        if abs(difference) > crossover_strength:
            if difference > 0:
                score = max(score, Decimal("0.6"))
            else:
                score = min(score, Decimal("-0.6"))
        elif k_line > d_line:
            score = max(score, Decimal("0.2"))
        elif k_line < d_line:
            score = min(score, Decimal("-0.2"))

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
        if (
            willr_oversold < wr_value < Decimal("-50")
        ):  # These are hardcoded, could be configurable
            return Decimal("0.4")
        if (
            Decimal("-50") < wr_value < willr_overbought
        ):  # These are hardcoded, could be configurable
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

        band_width = (
            bb_upper - bb_middle
        )  # Corrected to be from middle to upper/lower band
        if band_width > 0:
            relative_position = (last_close_decimal - bb_middle) / band_width
            score = max(Decimal("-1.0"), min(Decimal("1.0"), relative_position))
            return score * bb_mid_score_multiplier
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

    def _ceft(self) -> Decimal:
        """Check Ehlers Fisher Transform Score: Evaluates Fisher Transform (fisher_t) and its signal line (fisher_s)
        for trading signals based on crossovers and threshold breaches.
        """
        fisher_t = self.iv.get("FISHERT")
        fisher_s = self.iv.get("FISHERTs")

        if pd.isna(fisher_t) or pd.isna(fisher_s):
            self.lg.debug(
                f"Ehlers Fisher Transform check skipped for {self.s}: Missing FISHERT ({fisher_t}) or FISHERTs ({fisher_s}) values. The Fisher lines are unclear.{RST}",
            )
            return Decimal(np.nan)

        buy_thresh = self.indicator_thresholds.get(
            "ehlers_fisher_buy_threshold", Decimal("0.5"),
        )
        sell_thresh = self.indicator_thresholds.get(
            "ehlers_fisher_sell_threshold", Decimal("-0.5"),
        )
        # Ensure trend_confirm_thresh is positive for comparison, actual direction handled by fisher_t vs fisher_s
        trend_confirm_thresh = abs(
            self.indicator_thresholds.get(
                "ehlers_fisher_trend_confirmation_threshold", Decimal("0.1"),
            ),
        )

        score = Decimal("0.0")

        # Bullish conditions: fisher_t crosses above fisher_s
        if fisher_t > fisher_s:
            if (
                fisher_t < sell_thresh
            ):  # fisher_t is very low (oversold) and crossing up
                score = Decimal("1.0")  # Strong buy
            elif (
                fisher_t < -trend_confirm_thresh
            ):  # fisher_t is still negative but crossing up towards zero
                score = Decimal("0.6")  # Moderate buy, recovery from potential oversold
            elif (
                fisher_t < trend_confirm_thresh
            ):  # fisher_t crossed zero and is positive but not yet strongly trending
                score = Decimal("0.4")  # Mild buy, early trend
            else:  # fisher_t is positive and above trend confirmation
                score = Decimal("0.3")  # Sustained bullish
        # Bearish conditions: fisher_t crosses below fisher_s
        elif fisher_t < fisher_s:
            if (
                fisher_t > buy_thresh
            ):  # fisher_t is very high (overbought) and crossing down
                score = Decimal("-1.0")  # Strong sell
            elif (
                fisher_t > trend_confirm_thresh
            ):  # fisher_t is still positive but crossing down towards zero
                score = Decimal(
                    "-0.6",
                )  # Moderate sell, pullback from potential overbought
            elif (
                fisher_t > -trend_confirm_thresh
            ):  # fisher_t crossed zero and is negative but not yet strongly trending
                score = Decimal("-0.4")  # Mild sell, early trend
            else:  # fisher_t is negative and below negative trend confirmation
                score = Decimal("-0.3")  # Sustained bearish

        self.lg.debug(
            f"Ehlers Fisher ({self.s}): T={fisher_t:.2f}, S={fisher_s:.2f} -> Score={score:.2f} (Thresh: Buy={buy_thresh}, Sell={sell_thresh}, TrendConfirm={trend_confirm_thresh})",
        )
        return score

    def gts(self, current_price: Decimal, orderbook_data: dict | None) -> str:
        """Generate Trade Signal: Aggregates scores from various indicators to produce a BUY, SELL, or HOLD signal."""
        signal_threshold = self.cfg.get("signal_score_threshold", Decimal("1.5"))
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
            "stoch_rsi": "_csr",
            "rsi": "_cr",
            "bollinger_bands": "_cbb",
            "vwap": "_cv",
            "cci": "_cc",
            "wr": "_cwr",
            "psar": "_cpsar",
            "sma_10": "_csma",
            "mfi": "_cmfi",
            "orderbook": "_cob",
            "ehlers_fisher": "_ceft",  # Added Ehlers Fisher method
        }

        for indicator_key, enabled in self.cfg.get("indicators", {}).items():
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
            # signal_threshold is already defined at the beginning of the method
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

        if not isinstance(entry_price_estimate, Decimal) or entry_price_estimate <= 0:
            self.lg.warning(
                f"{NY}Cannot calculate TP/SL for {self.s} {signal}: Invalid entry price estimate ({entry_price_estimate}). The starting point is unclear!{RST}",
            )
            return entry_price_estimate, None, None

        # Fetch dedicated ATR parameters
        general_atr_period_config = self.cfg.get("atr_period", DIP["atr_period"])
        atr_sl_period_config = self.cfg.get("atr_sl_period", general_atr_period_config)
        atr_tp_period_config = self.cfg.get("atr_tp_period", general_atr_period_config)
        atr_sl_multiplier_config = self.cfg.get("atr_sl_multiplier", Decimal("1.5"))
        atr_tp_multiplier_config = self.cfg.get("atr_tp_multiplier", Decimal("1.0"))

        # Initialize ATR values with general ATR from self.iv
        atr_value_sl = self.iv.get("ATR")
        atr_value_tp = self.iv.get("ATR")

        # Calculate ATR for Stop Loss if period differs
        if atr_sl_period_config != general_atr_period_config:
            self.lg.debug(
                f"Calculating specific ATR for SL (Period: {atr_sl_period_config}) for {self.s}. The SL shield is custom-forged.",
            )
            try:
                df_sl_atr = self.d.copy()
                df_sl_atr.ta.atr(length=atr_sl_period_config, append=True)
                # pandas-ta typically names the column 'ATRr_length', e.g., 'ATRr_10'
                atr_column_name_sl = f"ATRr_{atr_sl_period_config}"
                if atr_column_name_sl in df_sl_atr.columns and pd.notna(
                    df_sl_atr[atr_column_name_sl].iloc[-1],
                ):
                    atr_value_sl = Decimal(str(df_sl_atr[atr_column_name_sl].iloc[-1]))
                    if atr_value_sl <= 0:
                        self.lg.warning(
                            f"{NY}Calculated SL ATR for period {atr_sl_period_config} is zero or negative ({atr_value_sl}). Falling back to general ATR. The custom SL shield is flawed.",
                        )
                        atr_value_sl = self.iv.get("ATR")  # Fallback
                else:
                    self.lg.warning(
                        f"{NY}Could not find or get valid SL ATR value for column '{atr_column_name_sl}'. Falling back to general ATR. The custom SL shield's runes are unclear.",
                    )
                    atr_value_sl = self.iv.get("ATR")  # Fallback
            except Exception as e:
                self.lg.error(
                    f"{NR}Error calculating specific ATR for SL (Period: {atr_sl_period_config}) for {self.s}: {e}. Falling back to general ATR. The custom SL forging failed.",
                    exc_info=True,
                )
                atr_value_sl = self.iv.get("ATR")  # Fallback

        if not isinstance(atr_value_sl, Decimal) or atr_value_sl <= 0:
            self.lg.error(
                f"{NR}Cannot calculate TP/SL for {self.s} {signal}: Invalid or missing ATR for Stop Loss (ATR_SL: {atr_value_sl}, Period: {atr_sl_period_config}). The volatility compass for SL is broken!{RST}",
            )
            return entry_price_estimate, None, None

        # Calculate ATR for Take Profit if period differs (and not already calculated for SL)
        if atr_tp_period_config != general_atr_period_config:
            if atr_tp_period_config == atr_sl_period_config:
                self.lg.debug(
                    f"Using SL ATR (Period: {atr_sl_period_config}) for TP as periods match for {self.s}. The TP target uses the same map.",
                )
                atr_value_tp = atr_value_sl
            else:
                self.lg.debug(
                    f"Calculating specific ATR for TP (Period: {atr_tp_period_config}) for {self.s}. The TP target is custom-plotted.",
                )
                try:
                    df_tp_atr = self.d.copy()
                    df_tp_atr.ta.atr(length=atr_tp_period_config, append=True)
                    atr_column_name_tp = f"ATRr_{atr_tp_period_config}"
                    if atr_column_name_tp in df_tp_atr.columns and pd.notna(
                        df_tp_atr[atr_column_name_tp].iloc[-1],
                    ):
                        atr_value_tp = Decimal(
                            str(df_tp_atr[atr_column_name_tp].iloc[-1]),
                        )
                        if atr_value_tp <= 0:
                            self.lg.warning(
                                f"{NY}Calculated TP ATR for period {atr_tp_period_config} is zero or negative ({atr_value_tp}). Falling back to general ATR. The custom TP map is flawed.",
                            )
                            atr_value_tp = self.iv.get("ATR")  # Fallback
                    else:
                        self.lg.warning(
                            f"{NY}Could not find or get valid TP ATR value for column '{atr_column_name_tp}'. Falling back to general ATR. The custom TP map's runes are unclear.",
                        )
                        atr_value_tp = self.iv.get("ATR")  # Fallback
                except Exception as e:
                    self.lg.error(
                        f"{NR}Error calculating specific ATR for TP (Period: {atr_tp_period_config}) for {self.s}: {e}. Falling back to general ATR. The custom TP plotting failed.",
                        exc_info=True,
                    )
                    atr_value_tp = self.iv.get("ATR")  # Fallback

        if not isinstance(atr_value_tp, Decimal) or atr_value_tp <= 0:
            self.lg.error(
                f"{NR}Cannot calculate TP/SL for {self.s} {signal}: Invalid or missing ATR for Take Profit (ATR_TP: {atr_value_tp}, Period: {atr_tp_period_config}). The volatility compass for TP is broken!{RST}",
            )
            return entry_price_estimate, None, None

        try:
            price_precision = TA.gpp(self.mi, self.lg)
            min_tick_size = TA.gmts(self.mi, self.lg)

            # Use dedicated ATR values and multipliers
            take_profit_offset = atr_value_tp * atr_tp_multiplier_config
            stop_loss_offset = atr_value_sl * atr_sl_multiplier_config

            self.lg.debug(
                f"Using ATR_SL={atr_value_sl:.{price_precision + 2}f} (P:{atr_sl_period_config}, M:{atr_sl_multiplier_config}) and "
                f"ATR_TP={atr_value_tp:.{price_precision + 2}f} (P:{atr_tp_period_config}, M:{atr_tp_multiplier_config}) for {self.s} {signal}.",
            )

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
                if min_tick_size > 0:
                    rounding_mode_tp = ROUND_UP if signal == "BUY" else ROUND_DOWN
                    quantized_take_profit_price = (
                        raw_take_profit_price / min_tick_size
                    ).quantize(Decimal("1"), rounding=rounding_mode_tp) * min_tick_size
                else:
                    quantized_take_profit_price = raw_take_profit_price.quantize(
                        Decimal("1e-" + str(price_precision)), rounding=ROUND_HALF_EVEN,
                    )

            if raw_stop_loss_price is not None:
                if min_tick_size > 0:
                    rounding_mode_sl = ROUND_DOWN if signal == "BUY" else ROUND_UP
                    quantized_stop_loss_price = (
                        raw_stop_loss_price / min_tick_size
                    ).quantize(Decimal("1"), rounding=rounding_mode_sl) * min_tick_size
                else:
                    quantized_stop_loss_price = raw_stop_loss_price.quantize(
                        Decimal("1e-" + str(price_precision)), rounding=ROUND_HALF_EVEN,
                    )

            final_tp = quantized_take_profit_price
            final_sl = quantized_stop_loss_price

            if final_sl is not None and min_tick_size > 0:
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

            if final_tp is not None and min_tick_size > 0:
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

            if final_sl is not None and final_sl <= 0:
                self.lg.error(
                    f"{NR}Stop loss calculation resulted in non-positive price ({final_sl}). Setting SL to None. The safety net vanished!{RST}",
                )
                final_sl = None
            if final_tp is not None and final_tp <= 0:
                self.lg.warning(
                    f"{NY}Take profit calculation resulted in non-positive price ({final_tp}). Setting TP to None. The treasure turned to dust!{RST}",
                )
                final_tp = None

            tp_string = f"{final_tp:.{price_precision}f}" if final_tp else "None"
            sl_string = f"{final_sl:.{price_precision}f}" if final_sl else "None"
            self.lg.debug(
                f"Calculated TP/SL for {self.s} {signal}: EntryEst={entry_price_estimate:.{price_precision}f}, "
                f"ATR_SL={atr_value_sl:.{price_precision + 2}f} (P:{atr_sl_period_config}, M:{atr_sl_multiplier_config}), "
                f"ATR_TP={atr_value_tp:.{price_precision + 2}f} (P:{atr_tp_period_config}, M:{atr_tp_multiplier_config}), "
                f"TP={tp_string}, SL={sl_string}. The boundaries are set with specific ATRs.{RST}",
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
    ccxt_exchange: ccxt.Exchange,
    bybit_api: BybitUnifiedTrading | None,
    currency: str,
    logger: logging.Logger,
) -> Decimal | None:
    """Fetch Balance: Retrieves the available balance for a specified currency.
    Handles retries and exchange-specific balance fetching (e.g., Bybit V5).
    """
    if bybit_api and ccxt_exchange.id == "bybit":
        logger.debug(f"Fetching balance using BybitUnifiedTrading for {currency}.")
        try:
            # For Bybit, get_wallet_balance is the primary way to get balance
            # It returns a list of coins in the 'list' key under 'result'
            wallet_balance_response = bybit_api.get_wallet_balance(
                accountType="UNIFIED", coin=currency,
            )
            if wallet_balance_response and wallet_balance_response.get("retCode") == 0:
                result_list = wallet_balance_response.get("result", {}).get("list", [])
                if result_list:
                    # Assuming the first item in the list contains the relevant coin data
                    coin_data = result_list[0].get("coin", [])
                    for coin_info in coin_data:
                        if coin_info.get("coin") == currency:
                            available_balance_str = coin_info.get(
                                "availableToWithdraw",
                            ) or coin_info.get("availableBalance")
                            if available_balance_str is not None:
                                final_balance = Decimal(str(available_balance_str))
                                logger.info(
                                    f"{NG}Available {currency} balance via BybitUnifiedTrading: {final_balance:.4f}.{RST}",
                                )
                                return final_balance
            logger.warning(
                f"{NY}Could not fetch balance for {currency} via BybitUnifiedTrading. Falling back to CCXT. The Bybit ledger is elusive!{RST}",
            )
        except PybitAPIException as e:
            logger.warning(
                f"{NY}BybitUnifiedTrading balance fetch failed: {e}. Falling back to CCXT. The Bybit conduit is troubled!{RST}",
            )
        except Exception as e:
            logger.error(
                f"{NR}Unexpected error during BybitUnifiedTrading balance fetch: {e}. Falling back to CCXT. A cosmic interference!{RST}",
                exc_info=True,
            )

    # Fallback to CCXT for other exchanges or if BybitUnifiedTrading fails
    logger.debug(f"Fetching balance using CCXT for {currency}.")
    balance_info = None
    available_balance_str: str | None = None
    account_types_to_try = []
    if ccxt_exchange.id == "bybit":
        account_types_to_try = ["CONTRACT", "UNIFIED"]

    # Try specific account types first
    for acct_type in account_types_to_try:
        try:
            logger.debug(
                f"Fetching balance using params={{'type': '{acct_type}'}} for {currency}. Probing a specific vault.",
            )
            balance_info = ccxt_exchange.fetch_balance(params={"type": acct_type})

            # Bybit V5 specific parsing (for CCXT fallback)
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
                                        f"Found balance via Bybit V5 nested ['available...'] (CCXT fallback): {available_balance_str}. Deciphering the intricate Bybit scrolls.{RST}",
                                    )
                                    break
                        if available_balance_str is not None:
                            break
                    elif (
                        isinstance(account.get("coin"), dict)
                        and account["coin"].get("coin") == currency
                    ):  # Single coin in list
                        found_balance = (
                            account["coin"].get("availableToWithdraw")
                            or account["coin"].get("availableBalance")
                            or account["coin"].get("walletBalance")
                        )
                        if found_balance is not None:
                            available_balance_str = str(found_balance)
                            logger.debug(
                                f"Found balance via Bybit V5 nested direct 'coin' dict (CCXT fallback): {available_balance_str}. A direct path within the nested structure.{RST}",
                            )
                        break

            if (
                available_balance_str is not None
            ):  # If found via Bybit V5 parsing, break from account type loop
                break
            if (
                currency in balance_info
                and balance_info[currency].get("free") is not None
            ):  # Standard CCXT format
                available_balance_str = str(balance_info[currency]["free"])
                logger.debug(
                    f"Found balance via standard ['{currency}']['free'] (CCXT fallback): {available_balance_str}. The most common ledger entry.{RST}",
                )
                break  # Found successfully
        except (ccxt.ExchangeError, ccxt.AuthenticationError) as e:
            logger.debug(
                f"Error fetching balance for type '{acct_type}' (CCXT fallback): {e}. Trying next type/default. A small obstacle.{RST}",
            )
            continue
        except Exception as e:
            logger.warning(
                f"{NY}Unexpected error fetching balance type '{acct_type}' (CCXT fallback): {e}. Trying next. A cosmic interference!{RST}",
            )
            continue

    if (
        available_balance_str is None
    ):  # If not found via specific types, try default fetch
        logger.debug(
            f"Fetching balance using default parameters for {currency} (CCXT fallback). Trying the common path.",
        )
        balance_info = ccxt_exchange.fetch_balance()
        if currency in balance_info and balance_info[currency].get("free") is not None:
            available_balance_str = str(balance_info[currency]["free"])
            logger.debug(
                f"Found balance via standard ['{currency}']['free'] (default CCXT fallback): {available_balance_str}. The common ledger entry.{RST}",
            )
        elif (
            "free" in balance_info
            and currency in balance_info["free"]
            and balance_info["free"][currency] is not None
        ):
            available_balance_str = str(balance_info["free"][currency])
            logger.debug(
                f"Found balance via top-level 'free' dict (default CCXT fallback): {available_balance_str}. A simpler, older path.{RST}",
            )
        else:
            total_balance_fallback = balance_info.get(currency, {}).get("total")
            if total_balance_fallback is not None:
                logger.warning(
                    f"{NY}Using 'total' balance ({total_balance_fallback}) as fallback for available {currency} (default CCXT fallback). The free funds are hidden, but total is known.{RST}",
                )
                available_balance_str = str(total_balance_fallback)
            else:
                logger.error(
                    f"{NR}Could not determine any balance ('free' or 'total') for {currency} via default CCXT fallback. The wellspring is dry!{RST}",
                )
                logger.debug(
                    f"Full balance_info structure (default CCXT fallback): {balance_info}. The full ledger is perplexing.",
                )
                raise ccxt.ExchangeError(
                    "Balance parsing failed or data missing after default CCXT fallback",
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
        if symbol == "RNDR/USDT:USDT":
            logger.warning(
                f"{NY}Market {symbol} is known to be problematic or may be deprecated. Skipping this symbol. The ancient map marker is faded!{RST}",
            )
            return None
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
                        amount_precision_for_log = TA.gpp(
                            market_info, logger,
                        )  # Use price precision for size display clarity
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
            "category": "linear" if market_info.get("linear") else "inverse",
        }  # Add category for Bybit V5
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
            or "leveragenotmodified"
            in error_message  # A simpler check just in case formatting varies
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
    side_lower = "buy" if trade_side == "BUY" else "sell"  # Moved this line up
    is_contract = market_info.get("is_contract", False)
    size_unit = "Contracts" if is_contract else market_info.get("base", "")
    action_description = "Close/Reduce" if reduce_only else "Open/Increase"

    # Example of a logging line that might have caused an issue if side_lower was not defined:
    # logger.debug(f"pt: Function called. trade_side: {trade_side}, side_lower: {side_lower}, symbol: {symbol}")

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
        filled_amount_str = str(
            order_response.get("filled", "0"),
        )  # Ensure it's a string for Decimal
        average_price_str = str(
            order_response.get("average", "N/A"),
        )  # Ensure it's a string

        logger.info(
            f"{NG}{action_description} Trade Placed Successfully! The spell was cast!{RST}",
        )
        logger.info(f"{NG}  Order ID: {order_id}, Initial Status: {order_status}{RST}")
        # Ensure filled_amount_str can be converted for logging if it's not just "0"
        if filled_amount_str != "0" and filled_amount_str is not None:
            try:
                filled_decimal_for_log = Decimal(filled_amount_str)
                if (
                    filled_decimal_for_log > 0
                ):  # Only log if filled amount is greater than 0
                    logger.info(f"{NG}  Filled Amount: {filled_decimal_for_log}{RST}")
            except InvalidOperation:
                logger.info(
                    f"{NG}  Filled Amount: {filled_amount_str} (raw){RST}",
                )  # Log raw if not decimal

        if average_price_str != "N/A":
            logger.info(f"{NG}  Average Fill Price: {average_price_str}{RST}")

        # <<< START NEW SMS ALERT CODE >>>
        if _icfs.get("enable_sms_alerts"):
            recipient_number = _icfs.get("sms_recipient_number")
            if recipient_number:
                # Determine price for SMS message
                sms_price = "N/A"
                if order_type == "limit" and formatted_price_float is not None:
                    sms_price = (
                        f"{formatted_price_float:.{TA.gpp(market_info, logger)}f}"
                    )
                elif average_price_str != "N/A":
                    try:
                        avg_price_dec = Decimal(average_price_str)
                        sms_price = f"{avg_price_dec:.{TA.gpp(market_info, logger)}f}"
                    except InvalidOperation:
                        sms_price = (
                            average_price_str  # Use raw string if conversion fails
                        )

                size_unit_sms = (
                    "Contracts"
                    if market_info.get("is_contract", False)
                    else market_info.get("base", "")
                )

                sms_message = (
                    f"XR Scalper Alert:\n"
                    f"Order {action_description.upper()}D!\n"
                    f"Symbol: {symbol}\n"
                    f"Side: {trade_side.upper()}\n"
                    f"Type: {order_type.upper()}\n"
                    f"Size: {formatted_amount_float} {size_unit_sms}\n"
                    f"Price: {sms_price} {market_info.get('quote', '')}\n"
                    f"Order ID: {order_id}\n"
                    f"Status: {order_status}"
                )
                send_sms_alert(sms_message, recipient_number, logger, _icfs)
            else:
                logger.warning(
                    f"{NY}SMS alerts enabled but no recipient number configured. Cannot send order placement SMS.{RST}",
                )
        # <<< END NEW SMS ALERT CODE >>>

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
        "success": False,  # Will be set to True if inputs are valid, but no orders placed by this func.
        "stopLoss": (
            stop_loss_price
            if isinstance(stop_loss_price, Decimal) and stop_loss_price > 0
            else None
        ),
        "takeProfit": (
            take_profit_price
            if isinstance(take_profit_price, Decimal) and take_profit_price > 0
            else None
        ),
        "trailingStopDistance": (
            trailing_stop_distance
            if isinstance(trailing_stop_distance, Decimal)
            and trailing_stop_distance > 0
            else None
        ),
        "trailingStopActivationPrice": (
            trailing_stop_activation_price
            if isinstance(trailing_stop_activation_price, Decimal)
            and trailing_stop_activation_price > 0
            else None
        ),
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
        protection_result["success"] = (
            True  # No action needed is a form of success here
        )
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
    """Consolidated protection setter for Bybit using direct API call POST /v5/position/trading-stop.
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

    # Fetch Current Position Size
    current_position_size_raw = position_info.get("contractsDecimal")
    current_position_size: Decimal | None = None
    if current_position_size_raw is not None:
        try:
            current_position_size = Decimal(str(current_position_size_raw))
            if current_position_size.is_zero():  # Position exists but size is zero
                logger.warning(
                    f"{NY}stsl: Position size for {symbol} is zero ({current_position_size_raw}). Cannot set protections if position is effectively closed.{RST}",
                )
                # Depending on strictness, could return False or allow clearing of protections.
                # For now, allow proceeding to clear, but new protections might fail or be irrelevant.
                # If an actual position is expected, this should be an error.
                # Let's assume if contractsDecimal is present, it's the authority.
                # If it's truly zero, setting new TP/SL might not make sense.
                # However, the API might require tpSize/slSize even to clear.
        except InvalidOperation:
            logger.error(
                f"{NR}stsl: Invalid position size '{current_position_size_raw}' in position_info for {symbol}. Cannot set protections.{RST}",
            )
            return False
    else:  # Fallback to trade_record.size if live data isn't available or not in expected format
        current_position_size = trade_record.size
        logger.warning(
            f"{NY}stsl: 'contractsDecimal' not found in position_info for {symbol}. Using trade_record.size ({current_position_size}) as fallback. Protections might be based on stale size.{RST}",
        )

    if (
        current_position_size is None or current_position_size.is_zero()
    ):  # Final check after potential fallback
        logger.error(
            f"{NR}stsl: Valid non-zero position size could not be determined for {symbol}. Cannot set protections.{RST}",
        )
        return False

    current_position_size_str = str(
        abs(current_position_size),
    )  # API expects positive size

    # Determine base_url based on sandbox mode
    use_sandbox = config.get("use_sandbox", True)
    base_url = (
        "https://api-testnet.bybit.com" if use_sandbox else "https://api.bybit.com"
    )

    # API path for setting trading stop
    api_path = "/v5/position/trading-stop"

    # Validate positionIdx
    retrieved_position_idx_value = position_info.get("info", {}).get("positionIdx")
    validated_integer_positionIdx: int = 0  # Default to 0

    if retrieved_position_idx_value is None:
        logger.debug(
            f"stsl: positionIdx not found in position_info for {symbol}. Defaulting to 0.",
        )
        validated_integer_positionIdx = 0
    else:
        try:
            validated_integer_positionIdx = int(retrieved_position_idx_value)
            logger.debug(
                f"stsl: Successfully converted positionIdx '{retrieved_position_idx_value}' to integer {validated_integer_positionIdx} for {symbol}.",
            )
        except ValueError:
            logger.error(
                f"{NR}stsl: Invalid positionIdx '{retrieved_position_idx_value}' for symbol {symbol}. Cannot set protections.{RST}",
            )
            return False

    price_precision = TA.gpp(market_info, logger)
    min_tick_size = TA.gmts(market_info, logger)

    # --- Define Quantized Prices ---
    quantized_tp_price: Decimal | None = None
    if take_profit_price_target and take_profit_price_target > 0:
        quantized_tp_price = take_profit_price_target.quantize(
            min_tick_size if min_tick_size > 0 else Decimal(f"1e-{price_precision}"),
            rounding=ROUND_HALF_EVEN,
        )

    quantized_fixed_sl_price: Decimal | None = None
    if fixed_stop_loss_price and fixed_stop_loss_price > 0:
        quantized_fixed_sl_price = fixed_stop_loss_price.quantize(
            min_tick_size if min_tick_size > 0 else Decimal(f"1e-{price_precision}"),
            rounding=ROUND_HALF_EVEN,
        )

    # --- TSL Parameter Calculation ---
    calculated_tsl_distance: Decimal | None = None
    calculated_tsl_activation_price: Decimal | None = None

    # --- Take Profit Handling ---
    if take_profit_price_target and take_profit_price_target > 0:
        quantized_tp = take_profit_price_target.quantize(
            min_tick_size if min_tick_size > 0 else Decimal(f"1e-{price_precision}"),
        )
        params_to_set["takeProfit"] = str(quantized_tp)
        # Ensure tpSize is always set when takeProfit is present
        params_to_set["tpSize"] = current_position_size_str
        logger.info(
            f"{NB}stsl: Setting Take Profit for {symbol} to {quantized_tp} with size {current_position_size_str}.{RST}",
        )
    else:  # Clearing TP or no TP requested
        params_to_set["takeProfit"] = "0"
        # Ensure tpSize is always set, even when clearing takeProfit
        params_to_set["tpSize"] = current_position_size_str
        logger.info(
            f"{NB}stsl: Clearing Take Profit for {symbol} (or no TP requested). tpSize set to {current_position_size_str}.{RST}",
        )

    # --- Stop Loss / Trailing Stop Loss Handling ---
    if attempt_tsl and config.get("enable_trailing_stop", False):
        try:
            tsl_distance_rate_from_config = config.get(
                "trailing_stop_callback_rate", DIP["psar_af"],
            )
            activation_percentage_from_config = config.get(
                "trailing_stop_activation_percentage", DIP["psar_af"],
            )

            if not (
                isinstance(tsl_distance_rate_from_config, Decimal)
                and isinstance(activation_percentage_from_config, Decimal)
                and tsl_distance_rate_from_config > 0
                and activation_percentage_from_config >= 0
            ):
                logger.error(
                    f"{NR}stsl: Invalid TSL config types/values. Rate: {tsl_distance_rate_from_config}, Activation Pct: {activation_percentage_from_config}.{RST}",
                )
            else:
                entry_price = position_info.get(
                    "entryPriceDecimal", trade_record.entry_price,
                )
                pos_side_for_tsl_calc = position_info.get("side", trade_record.side)

                if not entry_price or entry_price <= 0 or not pos_side_for_tsl_calc:
                    logger.error(
                        f"{NR}stsl: Missing entry price/side for TSL calc. Entry: {entry_price}, Side: {pos_side_for_tsl_calc}.{RST}",
                    )
                else:
                    raw_activation_price = entry_price * (
                        Decimal("1")
                        + (
                            activation_percentage_from_config
                            if pos_side_for_tsl_calc == "long"
                            else -activation_percentage_from_config
                        )
                    )
                    quantized_activation_price = raw_activation_price.quantize(
                        min_tick_size
                        if min_tick_size > 0
                        else Decimal(f"1e-{price_precision}"),
                        rounding=ROUND_HALF_EVEN,
                    )

                    actual_distance_value = entry_price * tsl_distance_rate_from_config
                    quantized_distance = actual_distance_value.quantize(
                        min_tick_size
                        if min_tick_size > 0
                        else Decimal(f"1e-{price_precision}"),
                        rounding=ROUND_HALF_EVEN,
                    )

                    if quantized_distance <= (
                        min_tick_size
                        if min_tick_size > 0
                        else Decimal(f"1e-{price_precision}")
                    ):  # Ensure meaningful distance
                        calculated_tsl_distance = (
                            min_tick_size
                            if min_tick_size > 0
                            else Decimal(f"1e-{price_precision}")
                        )
                        logger.warning(
                            f"{NY}stsl: TSL distance from rate ({tsl_distance_rate_from_config}) resulted in {actual_distance_value}, quantized to {quantized_distance}, which is too small. Adjusted to {calculated_tsl_distance}.{RST}",
                        )
                    else:
                        calculated_tsl_distance = quantized_distance

                    calculated_tsl_activation_price = quantized_activation_price

                    if (
                        calculated_tsl_distance > 0
                        and calculated_tsl_activation_price > 0
                    ):
                        initial_tsl_params_valid_for_processing = True
                    else:
                        logger.error(
                            f"{NR}stsl: Final TSL distance ({calculated_tsl_distance}) or activation price ({calculated_tsl_activation_price}) is invalid.{RST}",
                        )
        except Exception as e:
            logger.error(
                f"{NR}stsl: Error during TSL param calculation for {symbol}: {e}.{RST}",
                exc_info=True,
            )
            initial_tsl_params_valid_for_processing = False

    # --- Define Actual Intent Flags (AFTER all calculations) ---
    intent_to_set_tp = bool(quantized_tp_price and quantized_tp_price > 0)
    # intent_to_set_tsl is now effectively initial_tsl_params_valid_for_processing
    intent_to_set_fixed_sl = bool(
        quantized_fixed_sl_price and quantized_fixed_sl_price > 0,
    )

    if should_set_tsl and calculated_tsl_distance and calculated_tsl_activation_price:
        params_to_set["trailingStop"] = str(calculated_tsl_distance)
        params_to_set["activePrice"] = str(calculated_tsl_activation_price)
        params_to_set["stopLoss"] = "0"  # Clear fixed SL when TSL is active
        # Ensure slSize is always set when stopLoss is present (even if "0" due to TSL)
        params_to_set["slSize"] = current_position_size_str
        logger.info(
            f"{NB}stsl: Setting TSL for {symbol}. Activation: {calculated_tsl_activation_price}, Distance: {calculated_tsl_distance}. slSize: {current_position_size_str}. Fixed SL will be cleared.{RST}",
        )
    elif fixed_stop_loss_price and fixed_stop_loss_price > 0:
        quantized_fixed_sl = fixed_stop_loss_price.quantize(
            min_tick_size if min_tick_size > 0 else Decimal(f"1e-{price_precision}"),
        )
        params_to_set["stopLoss"] = str(quantized_fixed_sl)
        params_to_set["trailingStop"] = "0"  # Clear TSL
        params_to_set["activePrice"] = "0"  # Clear TSL activation price
        # Ensure slSize is always set when stopLoss is present
        params_to_set["slSize"] = current_position_size_str
        logger.info(
            f"{NB}stsl: Setting Fixed SL for {symbol} to {quantized_fixed_sl}. slSize: {current_position_size_str}. TSL will be cleared.{RST}",
        )
    else:  # Clearing both fixed SL and TSL, or no SL/TSL desired
        params_to_set["stopLoss"] = "0"
        params_to_set["trailingStop"] = "0"
        params_to_set["activePrice"] = "0"
        # Ensure slSize is always set, even when clearing stopLoss
        params_to_set["slSize"] = current_position_size_str
        logger.info(
            f"{NB}stsl: Clearing SL and TSL for {symbol} (or no SL/TSL requested). slSize set to {current_position_size_str}.{RST}",
        )

    tsl_actually_applied_with_initial_sl = False

    if (
        initial_tsl_params_valid_for_processing
    ):  # If config and inputs for TSL were okay initially
        pos_side = position_info.get("side", trade_record.side)
        quantized_initial_trigger_sl: Decimal | None = None

        if pos_side == "long":
            raw_initial_sl = calculated_tsl_activation_price - calculated_tsl_distance
            quantized_initial_trigger_sl = raw_initial_sl.quantize(
                min_tick_size
                if min_tick_size > 0
                else Decimal(f"1e-{price_precision}"),
                rounding=ROUND_DOWN,
            )
            if (
                quantized_initial_trigger_sl >= calculated_tsl_activation_price
            ):  # Adjust if SL is bad
                quantized_initial_trigger_sl = calculated_tsl_activation_price - (
                    min_tick_size
                    if min_tick_size > 0
                    else Decimal(f"1e-{price_precision}")
                )
        elif pos_side == "short":
            raw_initial_sl = calculated_tsl_activation_price + calculated_tsl_distance
            quantized_initial_trigger_sl = raw_initial_sl.quantize(
                min_tick_size
                if min_tick_size > 0
                else Decimal(f"1e-{price_precision}"),
                rounding=ROUND_UP,
            )
            if (
                quantized_initial_trigger_sl <= calculated_tsl_activation_price
            ):  # Adjust if SL is bad
                quantized_initial_trigger_sl = calculated_tsl_activation_price + (
                    min_tick_size
                    if min_tick_size > 0
                    else Decimal(f"1e-{price_precision}")
                )

        if quantized_initial_trigger_sl and quantized_initial_trigger_sl > 0:
            params_to_set["stopLoss"] = str(quantized_initial_trigger_sl)
            params_to_set["slSize"] = current_position_size_str
            params_to_set["trailingStop"] = str(calculated_tsl_distance)
            params_to_set["activePrice"] = str(calculated_tsl_activation_price)
            tsl_actually_applied_with_initial_sl = True
            logger.info(
                f"{NB}stsl: Planning to set TSL (Partial mode) for {symbol}. Initial SL: {quantized_initial_trigger_sl}, Dist: {calculated_tsl_distance}, Act: {calculated_tsl_activation_price}.{RST}",
            )
        else:
            logger.error(
                f"{NR}stsl: Calculated initial trigger SL for TSL is invalid ({quantized_initial_trigger_sl}). TSL will not be set with this logic.{RST}",
            )
            # Fall through to fixed SL or clearing logic

    if not tsl_actually_applied_with_initial_sl:
        if intent_to_set_fixed_sl:
            params_to_set["stopLoss"] = str(quantized_fixed_sl_price)
            params_to_set["slSize"] = current_position_size_str
            params_to_set["trailingStop"] = "0"
            if "activePrice" in params_to_set:
                del params_to_set["activePrice"]
            logger.info(
                f"{NB}stsl: Planning to set Fixed SL (Partial mode) for {symbol} to {quantized_fixed_sl_price}. TSL not applied.{RST}",
            )
        else:  # Clear SL protections
            params_to_set["stopLoss"] = "0"
            params_to_set["slSize"] = current_position_size_str
            params_to_set["trailingStop"] = "0"
            if "activePrice" in params_to_set:
                del params_to_set["activePrice"]
            logger.info(
                f"{NB}stsl: Planning to clear SL protections (Partial mode) for {symbol}.{RST}",
            )

    if intent_to_set_tp:
        params_to_set["takeProfit"] = str(quantized_tp_price)
        params_to_set["tpSize"] = current_position_size_str
        logger.info(
            f"{NB}stsl: Planning to set Take Profit (Partial mode) for {symbol} to {quantized_tp_price}.{RST}",
        )
    else:
        params_to_set["takeProfit"] = "0"
        params_to_set["tpSize"] = current_position_size_str
        logger.info(
            f"{NB}stsl: Planning to clear Take Profit (Partial mode) for {symbol}.{RST}",
        )

    # --- Skip Logic ---
    # Retrieve current protections from position_info for skip logic
    current_fixed_sl_on_exchange = position_info.get("stopLossPrice")
    current_tp_on_exchange = position_info.get("takeProfitPrice")
    current_tsl_dist_on_exchange = position_info.get("trailingStopLossValue")
    # current_tsl_act_on_exchange = position_info.get("trailingStopActivationPrice") # Not directly used in skip logic here

    # Avoid API call if parameters effectively mean "clear all" and nothing is set on exchange
    # This skip logic might need refinement if slSize/tpSize always need to be sent.
    # For now, assuming if SL/TP are "0", and nothing was set, we can skip.
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

    # Final Parameter Check (Debug Log)
    logger.debug(
        f"stsl: Preparing to call Bybit API. URL: {base_url}{api_path}, Payload: {json.dumps(params_to_set, default=str)}",
    )
    # The existing info log is good and can remain as is, or be merged if preferred.
    # For now, keeping both as the debug has full URL, info has a summary.
    logger.info(
        f"{NB}stsl: Attempting to set protections for {symbol} via direct API call. Params Summary: TP={params_to_set.get('takeProfit')}, SL={params_to_set.get('stopLoss')}, TSL={params_to_set.get('trailingStop')}{RST}",
    )
    logger.info(
        f"{NB}stsl: Sending payload to Bybit API /v5/position/trading-stop: {json.dumps(params_to_set, default=str)}{RST}",
    )
    # Call the _bybit_v5_request helper function
    response = _bybit_v5_request(
        method="POST",
        path=api_path,
        params=params_to_set,  # Already prepared and logged
        api_key=AK,
        api_secret=AS,
        base_url=base_url,
        logger=logger,
    )
    if response is None:
        logger.error(
            f"{NR}stsl: _bybit_v5_request returned None for {symbol}. Protection setup failed critically before/during request.{RST}",
        )
        return False

    logger.info(
        f"{NB}stsl: Raw response from Bybit {api_path} for {symbol}: {json.dumps(response, default=str)}{RST}",
    )

    if response.get("retCode") == 0:
        logger.info(
            f"{NG}stsl: Successfully set protections for {symbol} via direct API. Msg: {response.get('retMsg')}{RST}",
        )
        logger.debug(
            f"stsl: Successful protection set for {symbol}. Original params sent: {json.dumps(params_to_set, default=str)}",
        )
        # Update TradeRecord based on what was successfully sent
        if (
            tsl_actually_applied_with_initial_sl
            and calculated_tsl_distance
            and calculated_tsl_activation_price
        ):
            trade_record.trailing_stop_active = True
            trade_record.trailing_stop_distance = calculated_tsl_distance
            trade_record.tsl_activation_price = calculated_tsl_activation_price
            trade_record.stop_loss_price = None  # TSL overrides fixed SL
        else:  # Fixed SL was set or cleared
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
    ret_msg = response.get("retMsg", "Unknown error")
    ret_code = response.get("retCode", "N/A")
    logger.debug(
        f"stsl: Failed protection set for {symbol}. Original params sent: {json.dumps(params_to_set, default=str)}",
    )  # Added debug log for params

    if ret_code == 110061:  # Specific handling for SL/TP limit exceeded
        logger.error(
            f"{NR}stsl: Failed to set protections for {symbol} due to SL/TP order limit exceeded (Error 110061). Msg: {ret_msg}. Attempting to cancel existing StopOrders for the symbol as a corrective measure.{RST}",
        )
        try:
            cancel_all_sl_tp_params = {
                "category": params_to_set["category"],
                "symbol": params_to_set["symbol"],
                "orderFilter": "StopOrder",
            }
            cancel_api_path = "/v5/order/cancel-all"
            logger.info(
                f"{NB}stsl: Attempting to cancel all StopOrders for {symbol} with params: {json.dumps(cancel_all_sl_tp_params, default=str)} via {cancel_api_path}{RST}",
            )

            cancel_response = _bybit_v5_request(
                method="POST",
                path=cancel_api_path,
                params=cancel_all_sl_tp_params,
                api_key=AK,
                api_secret=AS,
                base_url=base_url,  # base_url is defined earlier in stsl
                logger=logger,
            )
            if cancel_response and cancel_response.get("retCode") == 0:
                cancelled_count = 0
                if isinstance(cancel_response.get("result", {}).get("list"), list):
                    cancelled_count = len(cancel_response["result"]["list"])
                logger.info(
                    f"{NG}stsl: Successfully sent request to cancel all StopOrders for {symbol}. Orders cancelled/affected: {cancelled_count}. This is a corrective action for the next cycle. Msg: {cancel_response.get('retMsg')}{RST}",
                )
            else:
                cancel_err_msg = (
                    cancel_response.get("retMsg", "Unknown cancel error")
                    if cancel_response
                    else "No response from cancel call"
                )
                cancel_err_code = (
                    cancel_response.get("retCode", "N/A") if cancel_response else "N/A"
                )
                logger.error(
                    f"{NR}stsl: Failed to cancel all StopOrders for {symbol}. Code: {cancel_err_code}, Msg: {cancel_err_msg}. Full Cancel Response: {json.dumps(cancel_response, default=str)}{RST}",
                )
        except Exception as e_cancel:
            logger.error(
                f"{NR}stsl: Exception occurred while attempting to cancel all StopOrders for {symbol}: {e_cancel}{RST}",
                exc_info=True,
            )
        # Even after attempting cancellation, the original SL/TP set operation failed.
        return False
    # Handle other errors
    logger.error(
        f"{NR}stsl: Failed to set protections for {symbol} via direct API. Code: {ret_code}, Msg: {ret_msg}. Full Response: {json.dumps(response, default=str)}{RST}",
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
    initial_capital: (
        Decimal  # Capital allocated to this trade (e.g., risk_amount * leverage)
    )
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
                "tsl_activation_price",  # New Decimal fields
                "exit_price",
                "pnl_quote",
                "pnl_percentage",
                "fees_in_quote",
                "realized_pnl_quote",
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
        for decimal_field in ["trailing_stop_distance", "tsl_activation_price"]:
            if (
                decimal_field in data
                and not isinstance(data[decimal_field], Decimal)
                and data[decimal_field] is not None
            ):
                # This case should be rare if above try-except for Decimal conversion works
                data[decimal_field] = None

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

            if self.side == "long" or self.side == "buy":
                unrealized_pnl = (
                    (current_price - self.entry_price) * self.size * contract_size
                )
            elif self.side == "short" or self.side == "sell":
                unrealized_pnl = (
                    (self.entry_price - current_price) * self.size * contract_size
                )
            else:
                logger.error(
                    f"PnL Error for {self.symbol}: Unhandled trade side '{self.side}'. Cannot calculate PnL.",
                )
                # Ensure pnl_quote and pnl_percentage remain None or are reset
                self.pnl_quote = None
                self.pnl_percentage = None
                return  # Exit if side is unhandled

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
        ccxt_exchange_ref: ccxt.Exchange | None = None,
        bybit_api_ref: BybitUnifiedTrading | None = None,
    ):
        self.open_trades: dict[str, Tr] = {}
        self.closed_trades: list[Tr] = []
        self.qc = quote_currency_symbol
        self.ccxt_exchange_ref: ccxt.Exchange | None = ccxt_exchange_ref
        self.bybit_api_ref: BybitUnifiedTrading | None = bybit_api_ref
        self.lg = logger
        self.total_pnl = Decimal("0")
        self.initial_balance = Decimal("0")
        self.current_balance = Decimal("0")
        self.mi: dict[str, Any] = {}
        self._load_trades()

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
                                self.ccxt_exchange_ref
                            ):  # Check if the ccxt exchange reference was provided
                                ccxt_exchange_instance = self.ccxt_exchange_ref
                                market_info_on_the_fly = gmi(
                                    ccxt_exchange_instance, trade_record.symbol, self.lg,
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

    def set_exchange_reference(
        self, exchange_instance: ccxt.Exchange | BybitUnifiedTrading,
    ):
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
                NP,
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
                    NP,
                    label_width=label_width,
                    unit="%",
                    is_pnl=True,
                ),
            )

        print_neon_separator(length=70, char="·", color=NC)

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
                NB,
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

        print_neon_separator(length=70, char="·", color=NC)

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

        print_neon_separator(length=70, char="·", color=NC)

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

        profit_factor_str = "N/A"
        if gross_loss_abs > 0:
            profit_factor = gross_profit / gross_loss_abs
            profit_factor_str = f"{profit_factor:.2f}"
        elif gross_profit > 0:  # Gross loss is 0, but profit is positive
            profit_factor_str = "Inf"
        elif gross_profit == 0 and gross_loss_abs == 0:  # Both are zero
            profit_factor_str = "0.00"

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
                unit=f" {self.qc}",
                value_precision=4,
            ),
        )  # Display gross loss as negative
        print(
            format_metric(
                "Profit Factor", profit_factor_str, NB, label_width=label_width,
            ),
        )

        print_neon_separator(length=70, char="·", color=NC)

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


tt: TMT = TMT(QC, slg("trade_tracker"), ccxt_exchange_ref=None, bybit_api_ref=None)


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
        self.last_prices: dict[
            str, Decimal,
        ] = {}  # Stores latest ticker price for each symbol (Bybit ID)
        self.position_updates: dict[
            str, dict,
        ] = {}  # Stores latest position info for each symbol (Bybit ID)

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
                    elif isinstance(
                        raw_ticker_payload, dict,
                    ):  # Handle direct dict for snapshot
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
        expires = int(
            (time.time() + 10) * 1000,
        )  # Timestamp in milliseconds, valid for 10 seconds
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
        ccxt_exchange: ccxt.Exchange,
        bybit_api: BybitUnifiedTrading | None,
        config: dict[str, Any],
        logger: logging.Logger,
        ws_client: BybitWebSocketClient,
    ):
        self.s = symbol
        self.ex = ccxt_exchange  # CCXT exchange instance for market data
        self.bybit_api = bybit_api  # BybitUnifiedTrading instance for order management
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
            if not refreshed_position or abs(
                Decimal(str(refreshed_position.get("size", "0"))),
            ) <= Decimal("1e-9"):  # Use 'size' from WS data
                self.lg.info(
                    f"{NG}Position for {self.s} already closed or zero size after refresh. The trade was already sealed!{RST}",
                )
                latest_balance = fb(self.ex, QC, self.lg)
                if latest_balance is None:
                    self.lg.warning(
                        f"{NY}Could not fetch latest balance after closing trade for {self.s}. PnL calculation may be based on stale balance. The ledger is momentarily obscured.{RST}",
                    )
                    latest_balance = tt.current_balance
                tt.ct(
                    self.s,
                    exit_price=current_price,
                    exit_time=datetime.now(TZ),
                    current_balance=latest_balance,
                )  # Fees are not available from CCXT close order response directly, so default to 0
                return True

            position_size = abs(
                Decimal(str(refreshed_position.get("size", "0"))),
            )  # Use 'size' from WS data
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

    def _cbe(self, current_price: Decimal, position_info: dict) -> bool:
        """Check Break-Even: Adjusts stop loss to break-even if price moves favorably."""
        if not self.cfg.get("enable_break_even", False):
            self.lg.debug(
                f"Break-Even feature is disabled for {self.s}. Skipping check.{RST}",
            )
            return False

        current_atr = self.ta_analyzer.iv.get("ATR")
        if not isinstance(current_atr, Decimal) or current_atr <= 0:
            self.lg.warning(
                f"{NY}Break-Even check skipped for {self.s}: Invalid or missing ATR ({current_atr}). Cannot calculate break-even trigger.{RST}",
            )
            return False

        entry_price = position_info.get("entryPriceDecimal")
        side = position_info.get("side")

        current_sl_raw = position_info.get(
            "stopLossPrice",
        )  # This might be None, '0', '', or a valid Decimal string
        current_sl: Decimal | None = None

        if (
            current_sl_raw is not None
            and str(current_sl_raw).strip() != ""
            and str(current_sl_raw).strip() != "0"
        ):
            # Bybit often returns "0" as a string for no SL/TP.
            # We also check for empty string just in case.
            try:
                current_sl_decimal_val = Decimal(str(current_sl_raw))
                if current_sl_decimal_val > 0:  # Ensure it's a meaningful SL price
                    current_sl = current_sl_decimal_val
                else:  # If '0' or negative, treat as no SL.
                    self.lg.debug(
                        f"_cbe: Raw stop loss '{current_sl_raw}' is zero or negative, treating as no SL for {self.s}.",
                    )
                    current_sl = None
            except (InvalidOperation, ValueError, TypeError) as e:
                self.lg.warning(
                    f"{NY}_cbe: Could not convert current_sl_raw '{current_sl_raw}' to Decimal for {self.s}. Error: {e}. Treating as no SL set.{RST}",
                )
                current_sl = None
        else:
            self.lg.debug(
                f"_cbe: No active stop loss (current_sl_raw: '{current_sl_raw}') found for {self.s} for break-even check.",
            )
            current_sl = None  # Handles None, '', '0'

        if not isinstance(entry_price, Decimal) or entry_price <= 0:
            self.lg.warning(
                f"{NY}Break-Even check skipped for {self.s}: Invalid entry price ({entry_price}).{RST}",
            )
            return False
        if side not in ["long", "short"]:
            self.lg.warning(
                f"{NY}Break-Even check skipped for {self.s}: Invalid position side ('{side}').{RST}",
            )
            return False

        trigger_atr_multiple = self.cfg.get(
            "break_even_trigger_atr_multiple", Decimal("1.0"),
        )

        price_precision = TA.gpp(self.mi, self.lg)
        min_tick_size = TA.gmts(self.mi, self.lg)

        break_even_offset_ticks = self.cfg.get("break_even_offset_ticks", 2)
        break_even_offset_amount = min_tick_size * Decimal(str(break_even_offset_ticks))

        new_sl_price: Decimal | None = None
        trigger_price: Decimal | None = None

        if side == "long":
            trigger_price = entry_price + (current_atr * trigger_atr_multiple)
            if current_price >= trigger_price:
                new_sl_price = entry_price + break_even_offset_amount
                # Ensure new_sl_price is quantized correctly
                if min_tick_size > 0:
                    new_sl_price = (new_sl_price / min_tick_size).quantize(
                        Decimal("1"), rounding=ROUND_UP,
                    ) * min_tick_size
                else:
                    new_sl_price = new_sl_price.quantize(
                        Decimal("1e-" + str(price_precision)), rounding=ROUND_UP,
                    )

                # Only update if new SL is higher than current SL (and profitable)
                if current_sl is None or new_sl_price > current_sl:
                    self.lg.info(
                        f"{NG}Break-Even triggered for {self.s} (Long). Current Price: {current_price:.{price_precision}f} >= Trigger: {trigger_price:.{price_precision}f}. Setting SL to {new_sl_price:.{price_precision}f}. Securing the gains!{RST}",
                    )
                    protection_result = spp(
                        exchange=self.ex,
                        symbol=self.s,
                        market_info=self.mi,
                        position_info=position_info,
                        logger=self.lg,
                        stop_loss_price=new_sl_price,
                        take_profit_price=(
                            Decimal(str(position_info.get("takeProfitPrice")))
                            if position_info.get("takeProfitPrice")
                            else None
                        ),
                    )
                    # Call stsl to set the new break-even SL, maintain existing TP, and ensure TSL is disabled.
                    # position_info should contain the most recent protection details.
                    existing_tp_on_exchange = position_info.get(
                        "takeProfitPrice",
                    )  # Already Decimal or None

                    self.lg.info(
                        f"{NB}_cbe: Attempting to set Break-Even SL for {self.s} (Long) to {new_sl_price:.{price_precision}f}. Maintaining TP: {existing_tp_on_exchange}. TSL will be disabled.{RST}",
                    )
                    stsl_success = stsl(
                        exchange=self.ex,
                        symbol=self.s,
                        market_info=self.mi,
                        position_info=position_info,  # Pass live position data
                        config=self.cfg,
                        logger=self.lg,
                        fixed_stop_loss_price=new_sl_price,
                        take_profit_price_target=existing_tp_on_exchange,
                        attempt_tsl=False,  # Crucial: Disables TSL, sets fixed SL
                    )
                    if stsl_success:
                        self.lg.info(
                            f"{NG}_cbe: Break-Even SL for {self.s} (Long) successfully set via stsl.{RST}",
                        )
                        return True
                    self.lg.warning(
                        f"{NY}_cbe: Break-Even SL setting failed for {self.s} (Long) via stsl.{RST}",
                    )
                    return False
                self.lg.debug(
                    f"Break-Even for {self.s} (Long) triggered, but new SL {new_sl_price:.{price_precision}f} is not higher than current SL {current_sl:.{price_precision}f}. No update needed. The shield is already advanced.{RST}",
                )
        elif side == "short":
            trigger_price = entry_price - (current_atr * trigger_atr_multiple)
            if current_price <= trigger_price:
                new_sl_price = entry_price - break_even_offset_amount
                # Ensure new_sl_price is quantized correctly
                if min_tick_size > 0:
                    new_sl_price = (new_sl_price / min_tick_size).quantize(
                        Decimal("1"), rounding=ROUND_DOWN,
                    ) * min_tick_size
                else:
                    new_sl_price = new_sl_price.quantize(
                        Decimal("1e-" + str(price_precision)), rounding=ROUND_DOWN,
                    )

                # Only update if new SL is lower than current SL (and profitable)
                if current_sl is None or new_sl_price < current_sl:
                    self.lg.info(
                        f"{NG}Break-Even triggered for {self.s} (Short). Current Price: {current_price:.{price_precision}f} <= Trigger: {trigger_price:.{price_precision}f}. Setting SL to {new_sl_price:.{price_precision}f}. Securing the gains!{RST}",
                    )
                    protection_result = spp(
                        exchange=self.ex,
                        symbol=self.s,
                        market_info=self.mi,
                        position_info=position_info,
                        logger=self.lg,
                        stop_loss_price=new_sl_price,
                        take_profit_price=(
                            Decimal(str(position_info.get("takeProfitPrice")))
                            if position_info.get("takeProfitPrice")
                            else None
                        ),
                    )
                    # Call stsl to set the new break-even SL, maintain existing TP, and ensure TSL is disabled.
                    existing_tp_on_exchange = position_info.get(
                        "takeProfitPrice",
                    )  # Already Decimal or None

                    self.lg.info(
                        f"{NB}_cbe: Attempting to set Break-Even SL for {self.s} (Short) to {new_sl_price:.{price_precision}f}. Maintaining TP: {existing_tp_on_exchange}. TSL will be disabled.{RST}",
                    )
                    stsl_success = stsl(
                        exchange=self.ex,
                        symbol=self.s,
                        market_info=self.mi,
                        position_info=position_info,  # Pass live position data
                        config=self.cfg,
                        logger=self.lg,
                        fixed_stop_loss_price=new_sl_price,
                        take_profit_price_target=existing_tp_on_exchange,
                        attempt_tsl=False,  # Crucial: Disables TSL, sets fixed SL
                    )
                    if stsl_success:
                        self.lg.info(
                            f"{NG}_cbe: Break-Even SL for {self.s} (Short) successfully set via stsl.{RST}",
                        )
                        return True
                    self.lg.warning(
                        f"{NY}_cbe: Break-Even SL setting failed for {self.s} (Short) via stsl.{RST}",
                    )
                    return False
                self.lg.debug(
                    f"Break-Even for {self.s} (Short) triggered, but new SL {new_sl_price:.{price_precision}f} is not lower than current SL {current_sl:.{price_precision}f}. No update needed. The shield is already advanced.{RST}",
                )

        self.lg.debug(
            f"Break-Even not triggered for {self.s}. Current Price: {current_price:.{price_precision}f}, Trigger: {trigger_price:.{price_precision}f}. Still awaiting the threshold.{RST}",
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
        """Manage Position: Checks for existing positions and applies TP/SL/TSL/Break-Even logic.
        Returns True if an open position is found and managed, False otherwise.
        """
        # Prioritize WebSocket's latest position update
        position_info = self.ws_client.get_latest_position_update(self.bybit_symbol_id)
        if position_info:
            # Convert relevant fields to Decimal for consistency
            try:
                # Standardized conversion for all relevant numeric fields from position_info
                # Primarily for data coming from WebSocket which might be strings.
                # gop (REST fetch) already does robust conversion for its direct return.

                raw_data_source = position_info.get(
                    "info", position_info,
                )  # Prioritize 'info' if it exists (common for CCXT)

                def robust_decimal_convert(
                    key_name: str, is_protection_param: bool = False,
                ) -> Decimal | None:
                    raw_val = raw_data_source.get(key_name)
                    if raw_val is None or str(raw_val).strip() == "":
                        return None
                    try:
                        val_dec = Decimal(str(raw_val))
                        # For protection parameters (SL, TP, TSL dist/act), "0" means not set.
                        if is_protection_param and val_dec == Decimal("0"):
                            return None
                        # For other essential fields like size, entry price, a value of 0 might be valid.
                        # Liq price, PnL, leverage could also be 0.
                        return val_dec
                    except (InvalidOperation, ValueError, TypeError):
                        self.lg.warning(
                            f"{NY}_mp: Error converting '{key_name}' value '{raw_val}' to Decimal for {self.s}. Treating as None.{RST}",
                        )
                        return None

                # Standardized conversion for all relevant numeric fields from position_info
                raw_data_source = position_info.get("info", position_info)

                def robust_decimal_convert(
                    key_name: str, source_dict: dict, is_protection_param: bool = False,
                ) -> Decimal | None:
                    raw_val = source_dict.get(key_name)
                    if raw_val is None or str(raw_val).strip() == "":
                        return None
                    try:
                        val_dec = Decimal(str(raw_val))
                        if is_protection_param and val_dec == Decimal("0"):
                            return None
                        return val_dec
                    except (InvalidOperation, ValueError, TypeError):
                        self.lg.warning(
                            f"{NY}_mp: Error converting '{key_name}' value '{raw_val}' to Decimal for {self.s}. Treating as None.{RST}",
                        )
                        return None

                # Convert core fields first, ensuring they exist or falling back.
                position_info["contractsDecimal"] = (
                    robust_decimal_convert("size", raw_data_source)
                    or robust_decimal_convert("contracts", raw_data_source)
                    or Decimal("0")
                )
                position_info["entryPriceDecimal"] = robust_decimal_convert(
                    "avgPrice", raw_data_source,
                ) or robust_decimal_convert("entryPrice", raw_data_source)

                if (
                    position_info["contractsDecimal"] is None
                    or position_info["entryPriceDecimal"] is None
                ):
                    self.lg.warning(
                        f"{NY}_mp: Critical fields (size/entry) are None after WS data conversion attempt for {self.s}. Falling back to REST fetch.{RST}",
                    )
                    position_info = gop(
                        self.ex, self.s, self.mi, self.lg,
                    )  # gop populates these robustly
                else:  # If primary fields from WS are good, convert others
                    position_info["stopLossPrice"] = robust_decimal_convert(
                        "stopLoss", raw_data_source, is_protection_param=True,
                    )
                    position_info["takeProfitPrice"] = robust_decimal_convert(
                        "takeProfit", raw_data_source, is_protection_param=True,
                    )
                    # Explicitly use 'trailingStop' for distance and 'activePrice' for TSL activation as per Bybit V5 via WS
                    position_info["trailingStopLossValue"] = robust_decimal_convert(
                        "trailingStop", raw_data_source, is_protection_param=True,
                    )
                    position_info["trailingStopActivationPrice"] = (
                        robust_decimal_convert(
                            "activePrice", raw_data_source, is_protection_param=True,
                        )
                    )

                    position_info["leverageDecimal"] = robust_decimal_convert(
                        "leverage", raw_data_source,
                    )
                    position_info["liquidationPriceDecimal"] = robust_decimal_convert(
                        "liqPrice", raw_data_source,
                    )
                    position_info["unrealisedPnlDecimal"] = robust_decimal_convert(
                        "unrealisedPnl", raw_data_source,
                    )

            except Exception as e:
                self.lg.error(
                    f"{NR}_mp: Unexpected error during position_info sanitization for {self.s}: {e}. Falling back to REST fetch.{RST}",
                    exc_info=True,
                )
                position_info = gop(self.ex, self.s, self.mi, self.lg)
        else:  # No WS data, fetch via REST
            self.lg.debug(
                f"No recent WS position update for {self.s}, fetching via REST for position management.",
            )
            position_info = gop(self.ex, self.s, self.mi, self.lg)

        if not position_info or (
            position_info.get("contractsDecimal", Decimal("0")) is not None
            and abs(position_info.get("contractsDecimal", Decimal("0")))
            < TA.gmts(self.mi, self.lg)
        ):
            # No active position
            if self.s in tt.open_trades:
                self.lg.warning(
                    f"{NY}Trade tracker shows open trade for {self.s}, but exchange reports no open position. Forcing closure in tracker. The ledger is out of sync!{RST}",
                )
                latest_balance = fb(self.ex, QC, self.lg)
                if latest_balance is None:
                    latest_balance = tt.current_balance
                tt.ct(
                    self.s,
                    exit_price=current_price,
                    exit_time=datetime.now(TZ),
                    current_balance=latest_balance,
                )
            return False

        # Position exists, update tracker if needed
        if self.s not in tt.open_trades:
            self.lg.warning(
                f"{NY}Exchange reports open position for {self.s}, but trade tracker does not. Adding to tracker. Re-aligning the ledger!{RST}",
            )
            # Attempt to fetch initial_capital from balance or estimate
            initial_capital_estimate = (
                tt.current_balance
                * self.cfg.get("risk_per_trade", Decimal("0.01"))
                * self.cfg.get("leverage", 1)
            )
            if initial_capital_estimate <= 0:
                initial_capital_estimate = Decimal(
                    "100",
                )  # Fallback if balance is zero or risk is too low

            tt.aot(
                Tr(
                    symbol=self.s,
                    side=position_info["side"],
                    entry_price=position_info["entryPriceDecimal"],
                    entry_time=datetime.now(
                        TZ,
                    ),  # Use current time as best guess for entry if not available
                    size=position_info["contractsDecimal"],
                    leverage=Decimal(
                        str(position_info.get("leverage", self.cfg.get("leverage", 1))),
                    ),
                    initial_capital=initial_capital_estimate,
                    stop_loss_price=position_info.get("stopLossPrice"),
                    take_profit_price=position_info.get("takeProfitPrice"),
                ),
            )

        # Update unrealized PnL for the open trade
        tt.open_trades[self.s].upnl(current_price, self.mi, self.lg)

        # Check for time-based exit
        if self._tbe(position_info):
            return True  # Trade closed by time-based exit

        # Check for break-even
        if self._cbe(current_price, position_info):
            return True  # Break-even adjusted

        # Check if TP/SL are already set on the exchange and match our records
        # This is important if they were set manually or by a previous bot run
        current_trade_record = tt.open_trades[self.s]

        # Check if current SL/TP on exchange matches what we want to set
        # If not, attempt to set them. This also handles initial setting.
        target_entry_price, target_tp_price, target_sl_price = self.ta_analyzer.cets(
            entry_price_estimate=current_trade_record.entry_price,
            signal=current_trade_record.side.upper(),
        )

        min_tick_size = TA.gmts(self.mi, self.lg)

        min_tick_size = TA.gmts(
            self.mi, self.lg,
        )  # Used for comparing prices with tolerance

        # Determine if TSL is currently active on the exchange from position_info
        # (assuming gop or WS updates these fields based on Bybit's actual TSL info)
        tsl_value_raw = position_info.get("trailingStopLossValue")
        is_tsl_active_on_exchange = False
        if tsl_value_raw is not None and str(tsl_value_raw).strip() != "":
            try:
                tsl_value_decimal = Decimal(str(tsl_value_raw))
                if tsl_value_decimal > Decimal("0"):
                    is_tsl_active_on_exchange = True
            except InvalidOperation:
                self.lg.warning(
                    f"_mp: Could not convert trailingStopLossValue '{tsl_value_raw}' to Decimal for {self.s} when checking TSL status. Type: {type(tsl_value_raw)}",
                )
                # is_tsl_active_on_exchange remains False

        # Consolidate protection setting through stsl
        if self.cfg.get("enable_trailing_stop", False):
            # TSL is enabled in config. stsl will attempt to set TSL.
            # Pass target_tp_price. fixed_stop_loss_price is None because TSL is prioritized.
            self.lg.info(
                f"{NB}_mp: TSL is enabled for {self.s}. Calling stsl to manage TSL and TP.{RST}",
            )
            stsl_success = stsl(
                exchange=self.ex,
                symbol=self.s,
                market_info=self.mi,
                position_info=position_info,
                config=self.cfg,
                logger=self.lg,
                fixed_stop_loss_price=None,  # TSL takes priority
                take_profit_price_target=target_tp_price,
                attempt_tsl=True,
            )
            if not stsl_success:
                self.lg.warning(
                    f"{NY}_mp: stsl call for TSL (and TP) for {self.s} failed. Position may not have desired protections.{RST}",
                )
        else:
            # TSL is disabled in config. Manage fixed SL and TP via stsl.
            # If TSL is somehow active on exchange, this call should attempt to disable it by setting a fixed SL.
            self.lg.info(
                f"{NB}_mp: TSL is disabled for {self.s}. Calling stsl to manage fixed SL and TP.{RST}",
            )

            # Compare desired fixed SL/TP with actual exchange SL/TP
            actual_sl = position_info.get("stopLossPrice")
            actual_tp = position_info.get("takeProfitPrice")

            sl_needs_update = False
            if target_sl_price is not None:
                if (
                    actual_sl is None
                    or abs(actual_sl - target_sl_price) > min_tick_size
                ):
                    sl_needs_update = True
            elif actual_sl is not None and actual_sl != Decimal(
                0,
            ):  # Desired is None, but actual SL exists (and is not 0)
                sl_needs_update = True  # Need to cancel it

            tp_needs_update = False
            if target_tp_price is not None:
                if (
                    actual_tp is None
                    or abs(actual_tp - target_tp_price) > min_tick_size
                ):
                    tp_needs_update = True
            elif actual_tp is not None and actual_tp != Decimal(
                0,
            ):  # Desired is None, but actual TP exists
                tp_needs_update = True  # Need to cancel it

            if is_tsl_active_on_exchange or sl_needs_update or tp_needs_update:
                self.lg.info(
                    f"{NB}_mp: Conditions for updating fixed protections met for {self.s} (TSL active on ex: {is_tsl_active_on_exchange}, SL update needed: {sl_needs_update}, TP update needed: {tp_needs_update}). Calling stsl.{RST}",
                )
                stsl_success = stsl(
                    exchange=self.ex,
                    symbol=self.s,
                    market_info=self.mi,
                    position_info=position_info,
                    config=self.cfg,
                    logger=self.lg,
                    fixed_stop_loss_price=target_sl_price,  # Pass the desired fixed SL
                    take_profit_price_target=target_tp_price,
                    attempt_tsl=False,  # Explicitly do not attempt TSL
                )
                if not stsl_success:
                    self.lg.warning(
                        f"{NY}_mp: stsl call for fixed SL/TP for {self.s} failed. Position may not have desired protections.{RST}",
                    )
            else:
                self.lg.debug(
                    f"{NB}_mp: No mismatch in fixed SL/TP for {self.s}, and TSL is disabled and not active on exchange. No protection update needed.{RST}",
                )

        return True  # Position was found and managed (or attempt was made)

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

        current_balance = fb(self.ex, self.bybit_api, QC, self.lg)
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
                (
                    "limit_order_offset_buy"
                    if signal == "BUY"
                    else "limit_order_offset_sell"
                ),
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
                ),
            )

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
                            if activation_percentage == Decimal(
                                "0",
                            ):  # Immediate activation
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
        self.last_sms_report_time: float = 0.0

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
            tt.set_exchange_reference(
                self.ex,
            )  # Pass the exchange instance to the global tt

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
        private_topics = [
            "order",
            "position",
        ]  # Always subscribe to order and position updates

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

    def run(self):
        """Runs the main trading loop."""
        self.lg.info(f"{NP}--- Starting XR Scalper Bot Main Loop ---{RST}")
        last_run_time = {}
        interval_seconds = (
            int(self.cfg.get("interval", "5")) * 60
        )  # Convert minutes to seconds

        while self.is_running:
            try:
                # --- Periodic SMS Summary Logic ---
                enable_sms = self.cfg.get("enable_sms_alerts", False)
                recipient_number = self.cfg.get("sms_recipient_number")
                sms_interval_minutes = self.cfg.get("sms_report_interval_minutes")

                if (
                    enable_sms
                    and recipient_number
                    and sms_interval_minutes
                    and sms_interval_minutes > 0
                ):
                    current_loop_time = time.time()
                    if (current_loop_time - self.last_sms_report_time) >= (
                        sms_interval_minutes * 60
                    ):
                        self.lg.info(
                            f"{NB}SMS report interval reached. Generating summary...{RST}",
                        )
                        try:
                            # 1. Fetch Balance
                            balance_val = fb(
                                self.ex, QC, self.lg,
                            )  # QC is globally defined quote currency
                            balance_str = (
                                f"{balance_val:.2f} {QC}"
                                if balance_val is not None
                                else "N/A"
                            )

                            # 2. Open Positions Summary
                            open_pos_summary_parts = []
                            if tt.open_trades:
                                for symbol, trade in tt.open_trades.items():
                                    pnl_str = (
                                        f"{trade.pnl_quote:.2f}"
                                        if trade.pnl_quote is not None
                                        else "N/A"
                                    )
                                    open_pos_summary_parts.append(
                                        f"{symbol.split('/')[0]}:{trade.side[:1].upper()}({pnl_str})",
                                    )
                            open_pos_str = (
                                ", ".join(open_pos_summary_parts)
                                if open_pos_summary_parts
                                else "None"
                            )
                            if len(open_pos_str) > 100:  # Truncate if too long for SMS
                                open_pos_str = open_pos_str[:97] + "..."

                            # 3. Recent Closed Trades Summary (Last 1)
                            closed_trades_summary_parts = []
                            if tt.closed_trades:
                                last_closed = tt.closed_trades[-1]
                                closed_pnl_str = (
                                    f"{last_closed.realized_pnl_quote:.2f}"
                                    if last_closed.realized_pnl_quote is not None
                                    else "N/A"
                                )
                                closed_trades_summary_parts.append(
                                    f"Last Closed: {last_closed.symbol.split('/')[0]} PnL:{closed_pnl_str}",
                                )
                            closed_trades_str = (
                                ", ".join(closed_trades_summary_parts)
                                if closed_trades_summary_parts
                                else "None"
                            )

                            # 4. Overall PnL
                            overall_pnl_str = (
                                f"{tt.total_pnl:.2f} {QC}"
                                if tt.total_pnl is not None
                                else "N/A"
                            )

                            # 5. Construct SMS
                            sms_message = (
                                f"XR Scalper Update:\n"
                                f"Balance: {balance_str}\n"
                                f"Total PnL: {overall_pnl_str}\n"
                                f"Open Pos: {open_pos_str}\n"
                                f"{closed_trades_str}"
                            )

                            send_sms_alert(
                                sms_message, recipient_number, self.lg, self.cfg,
                            )
                            self.last_sms_report_time = current_loop_time
                        except Exception as e_sms_report:
                            self.lg.error(
                                f"{NR}Error generating periodic SMS summary: {e_sms_report}{RST}",
                                exc_info=True,
                            )
                # --- End Periodic SMS Summary Logic ---

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
