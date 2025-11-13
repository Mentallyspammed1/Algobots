"""Pscalp: A High-Frequency Trading Bot for Bybit

This script is the main entry point for the pscalp trading bot. It handles
configuration, API connections, trading logic, and real-time data processing.

High-Level Structure:
- Configuration Loading: Loads settings from `config.json`.
- API Integration: Connects to Bybit via REST and WebSocket APIs.
- Technical Analysis: Uses a custom TA library to calculate indicators.
- Trading Strategy: Implements a scalping strategy based on a scoring system.
- Position Management: Manages entry, exit, stop-loss, and take-profit.
- UI: Displays real-time information in the terminal.

Refactoring Suggestions:
This file is very large and handles many responsibilities. For better
maintainability and readability, consider refactoring it into smaller,
specialized modules:
- `config.py`: For loading, validating, and managing configuration.
- `api.py`: For all exchange-specific API interactions.
- `trading_logic.py`: For the core signal generation and strategy.
- `position_manager.py`: For handling trade lifecycle (entry, exit, SL/TP).
- `ui.py`: For all terminal display functions.
- `models.py`: For data classes like `TradeRecord`.
- `scalper.py`: To act as the main orchestrator.
"""

import hashlib
import hmac
import json
import logging
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timedelta
from decimal import ROUND_DOWN
from decimal import ROUND_HALF_EVEN
from decimal import ROUND_UP
from decimal import Decimal
from decimal import InvalidOperation
from decimal import getcontext
from functools import wraps
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from typing import Final

# --- System Path Setup ---
# Add project root and 'p' directory to the system path for module resolution.
# This allows for absolute imports from the project's modules.
p_directory = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(p_directory, ".."))

if p_directory not in sys.path:
    sys.path.insert(0, p_directory)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# --- Core Dependencies ---
import ccxt
import pandas as pd
import requests

# --- Project-Specific Imports ---
from bybit_v5_plugin import BybitV5Plugin
from colorama import Fore
from colorama import Style
from colorama import init
from ind import RuneWeaver as IndicatorCalculator  # Adjusted import

# from websocket_manager import BybitWebSocket # Removed to use local class definition
from scalper_core.constants import CFP
from scalper_core.constants import DIP
from scalper_core.constants import LD
from scalper_core.constants import LDS
from scalper_core.constants import MAR
from scalper_core.constants import NB
from scalper_core.constants import NC
from scalper_core.constants import NG
from scalper_core.constants import NP
from scalper_core.constants import NR
from scalper_core.constants import NY
from scalper_core.constants import PCDS
from scalper_core.constants import RDS
from scalper_core.constants import RST
from scalper_core.constants import TRP
from scalper_core.constants import VI
from scalper_core.models import TradeRecord

# Ensure python-dotenv is installed for load_dotenv
try:
    from dotenv import load_dotenv
except ImportError:
    print(
        f"{Fore.YELLOW}Warning: 'python-dotenv' not found. "
        f"Please install it: pip install python-dotenv{Style.RESET_ALL}"
    )
    print(
        f"{Fore.YELLOW}Environment variables will not be loaded from .env file."
        f"{Style.RESET_ALL}"
    )

    def load_dotenv():
        """Dummy function if python-dotenv is not installed."""
        # Dummy function if not installed


# Initialize Colorama for beautiful terminal output, resetting colors
# automatically.
init(autoreset=True)


def handle_exceptions(default_return: Any = None, message: str = "An error occurred"):
    """Decorator for handling exceptions in functions, logging them, and returning a default value."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = kwargs.get("logger", logging.getLogger(func.__module__))
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(
                    f"{NR}{message} in {func.__name__}: {e}. "
                    f"Returning default value.{RST}",
                    exc_info=True,
                )
                return default_return

        return wrapper

    return decorator


from time_utils import TZ

# Set global precision for Decimal operations.
getcontext().prec = 38
# Load environment variables from .env file.
load_dotenv()


# Retrieve API keys from environment variables.


@handle_exceptions(default_return=(None, None), message="Error validating API keys")
def _validate_api_keys(logger: logging.Logger) -> tuple[str | None, str | None]:
    """Validates that BYBIT_API_KEY and BYBIT_API_SECRET environment variables are set.
    Logs a critical error and exits if they are not.
    """
    if os.getenv("JULES_TEST_MODE") == "true":
        logger.warning(
            f"{NY}JULES_TEST_MODE active: Using dummy API keys for testing.{RST}"
        )
        return "NRrb4Biggi3sO7rKZ1", "TXztLxhYdHIcyzmN6QR2zSc2Dxj0UuQRiMzQ"

    ak_env = os.getenv("BYBIT_API_KEY")
    as_env = os.getenv("BYBIT_API_SECRET")

    if not ak_env or not as_env:
        logger.critical(
            f"{NR}FATAL ERROR: BYBIT_API_KEY and BYBIT_API_SECRET must be set "
            f"in your .env file. These are the keys to the exchange's "
            f"digital gates! The bot cannot proceed without them.{RST}"
        )
        return None, None  # Return None for both keys
    return ak_env, as_env


# Create a temporary logger for initial API key validation
# The full logger will be set up later by slg()
_temp_logger = logging.getLogger(__name__ + "_api_key_validator")  # Use a unique name
_temp_logger.propagate = False  # Prevent messages from going to root logger
if not _temp_logger.handlers:
    _temp_logger.setLevel(logging.INFO)
    _handler = logging.StreamHandler(sys.stdout)
    _formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    _handler.setFormatter(_formatter)
    _temp_logger.addHandler(_handler)

AK: Final[str | None]
AS: Final[str | None]
AK, AS = _validate_api_keys(_temp_logger)

# Create log directory if it doesn't exist.
LD.mkdir(parents=True, exist_ok=True)

# --- Neon UI Helper Functions ---


def print_neon_header(text: str, color: str = NP, length: int = 60) -> None:
    """Prints a centered header with a neon-like border."""
    border_char = "✨"
    # Ensure text is not longer than length - (2 * border_char_len + 2 *
    # spaces + 2 * dashes)
    max_text_len = length - (len(border_char) * 2 + 4)  # Adjusted for " -- "
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
            f"{display_name:<{width}}"
        )  # Left align header text within cell
    print(f"{header_color}{' '.join(header_parts)}{RST}")
    # Print separator based on total width
    total_width = sum(width for _, width in columns) + len(columns) - 1
    print_neon_separator(length=total_width, char="═", color=header_color)


def print_table_row(
    row_data: list[Any],
    column_widths: list[int],
    cell_colors: list[str] | None = None,
    default_color: str = NC,
    decimal_precision: int = 2,
    pnl_columns: list[int] | None = None,
) -> None:
    """Prints a formatted table row."""
    if pnl_columns is None:
        pnl_columns = []

    formatted_cells = []
    for i, cell_value in enumerate(row_data):
        width = column_widths[i] if i < len(column_widths) else 10
        color = default_color
        if cell_colors and i < len(cell_colors) and cell_colors[i]:
            color = cell_colors[i]

        cell_str = ""
        is_cell_pnl = i in pnl_columns

        if isinstance(cell_value, (Decimal, float)):
            if is_cell_pnl:
                color = NG if cell_value >= 0 else NR
                sign = "+" if value > 0 else ""
                cell_str = f"{sign}{cell_value:,.{decimal_precision}f}"
            else:
                cell_str = f"{cell_value:,.{decimal_precision}f}"
        elif isinstance(cell_value, int) and is_cell_pnl:
            color = NG if cell_value >= 0 else NR
            sign = "+" if value > 0 else ""
            cell_str = f"{sign}{cell_value:,}"
        else:
            cell_str = str(cell_value)

        if len(cell_str) > width:
            cell_str = cell_str[: width - 1] + "…"

        formatted_cells.append(f"{color}{cell_str:<{width}}{RST}")

    print(" ".join(formatted_cells))


# --- End Neon UI Helper Functions ---


# Module-level helper for Bybit V5 API requests
@handle_exceptions(default_return=None, message="Error in Bybit V5 API request")
def _bybit_v5_request(
    method: str,
    path: str,
    params: dict,
    api_key: str,
    api_secret: str,
    base_url: str,
    logger: logging.Logger,
) -> dict | None:
    """Helper function to make authenticated requests to Bybit V5 API."""
    if not api_key or not api_secret:
        logger.error(
            f"{NR}_bybit_v5_request: API key or secret is missing. "
            f"Cannot make request.{RST}"
        )
        return None

    full_url = base_url + path
    timestamp_ms = str(int(time.time() * 1000))
    recv_window_str = "5000"

    json_payload_str = ""
    if method.upper() == "POST" and params:
        json_payload_str = json.dumps(params, separators=(",", ":"))

    signature_string = timestamp_ms + api_key + recv_window_str + json_payload_str
    signature = hmac.new(
        api_secret.encode("utf-8"), signature_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-TIMESTAMP": timestamp_ms,
        "X-BAPI-SIGN": signature,
        "X-BAPI-RECV-WINDOW": recv_window_str,
    }

    sanitized_headers = headers.copy()
    if api_key:
        sanitized_headers["X-BAPI-API-KEY"] = (
            f"{api_key[:5]}...{api_key[-4:]}" if len(api_key) > 9 else "***"
        )
    sanitized_headers["X-BAPI-SIGN"] = (
        f"{signature[:5]}...{signature[-4:]}"
        if signature and len(signature) > 9
        else "***"
    )

    logger.debug(f"_bybit_v5_request: Preparing {method} request to {full_url}")
    logger.debug(f"_bybit_v5_request: Headers: {sanitized_headers}")
    logger.debug(
        f"_bybit_v5_request: Payload: {json_payload_str if params else 'No body'}"
    )

    response_json: dict | None = None
    _response_obj = None
    try:
        if method.upper() == "POST":
            _response_obj = requests.post(
                full_url, headers=headers, data=json_payload_str, timeout=10
            )
        else:
            logger.error(
                f"{NR}_bybit_v5_request: Unsupported HTTP method '{method}'.{RST}"
            )
            return None

        _response_obj.raise_for_status()
        response_json = _response_obj.json()
        logger.debug(
            f"_bybit_v5_request: Response received: "
            f"{json.dumps(response_json, indent=2)}"
        )

    except requests.exceptions.HTTPError as http_err:
        err_resp_text = (
            http_err.response.text if http_err.response else "No response text"
        )
        logger.error(
            f"{NR}_bybit_v5_request: HTTP error: {http_err} - "
            f"Response: {err_resp_text}{RST}"
        )
        if http_err.response is not None:
            try:
                response_json = http_err.response.json()
            except json.JSONDecodeError:
                response_json = {"error": "HTTPError", "message": err_resp_text}
    except requests.exceptions.RequestException as req_err:
        logger.error(f"{NR}_bybit_v5_request: Request exception: {req_err}{RST}")
        response_json = {"error": "RequestException", "message": str(req_err)}
    except json.JSONDecodeError as json_err:
        resp_text = (
            _response_obj.text
            if _response_obj and hasattr(_response_obj, "text")
            else "N/A"
        )
        logger.error(
            f"{NR}_bybit_v5_request: Failed to parse JSON: {json_err} - "
            f"Response text: {resp_text}{RST}"
        )
        response_json = {"error": "JSONDecodeError", "message": str(json_err)}
    except Exception as e:
        logger.error(
            f"{NR}_bybit_v5_request: Unexpected error: {e}{RST}", exc_info=True
        )
        response_json = {"error": "UnexpectedException", "message": str(e)}

    return response_json


def clear_screen() -> None:
    """Clears the terminal screen using ANSI escape codes."""
    print("\033[H\033[J", end="")


def display_open_positions(
    open_trades: dict[str, "Tr"],
    market_infos: dict[str, dict],
    current_prices: dict[str, Decimal | None],
    quote_currency: str,
    logger: logging.Logger,
) -> None:
    """Displays currently open positions in a neon-themed table."""
    table_length = 160
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
        ("SL Info", 26),
        ("TP Info", 14),
        ("Dist SL%", 10),
        ("Dist TP%", 10),
    ]
    column_widths = [width for _, width in columns]
    print_table_header(columns, header_color=NB)

    for trade_record in open_trades.values():
        symbol_short = trade_record.symbol
        market_info = market_infos.get(symbol_short)

        if not market_info:
            logger.warning(
                f"{NY}Market info for open trade on {symbol_short} unavailable. "
                f"Cannot display full details.{RST}"
            )
            row_data = [
                symbol_short,
                trade_record.side.upper(),
                str(trade_record.size),
                str(trade_record.entry_price),
                "N/A",
                "N/A",
                "N/A",
                "N/A",
                "N/A",
                "N/A",
                "N/A",
            ]
            cell_colors = [NC, NG if trade_record.side == "long" else NR] + [NC] * 9
            print_table_row(row_data, column_widths, cell_colors)
            continue

        bybit_symbol_id = market_info.get("id")
        current_price = current_prices.get(bybit_symbol_id)
        price_prec = IndicatorCalculator.gpp(market_info, logger)
        size_prec = IndicatorCalculator.gpp(market_info, logger)

        if current_price is not None:
            trade_record.upnl(current_price, market_info, logger)

        side_color = NG if trade_record.side == "long" else NR

        sl_info_str = "N/A"
        if trade_record.trailing_stop_active:
            act_p_str = (
                f"{trade_record.tsl_activation_price:.{price_prec}f}"
                if trade_record.tsl_activation_price
                else "N/A"
            )
            dist_s_str = (
                f"{trade_record.trailing_stop_distance:.{price_prec}f}"
                if trade_record.trailing_stop_distance
                else "N/A"
            )
            sl_info_str = f"TSL Act:{act_p_str} / Trl:{dist_s_str}"
        elif trade_record.stop_loss_price:
            sl_info_str = f"{trade_record.stop_loss_price:.{price_prec}f}"

        tp_info_str = (
            f"{trade_record.take_profit_price:.{price_prec}f}"
            if trade_record.take_profit_price
            else "N/A"
        )

        dist_sl_pct_str, dist_tp_pct_str = "N/A", "N/A"
        dist_sl_color, dist_tp_color = NB, NB

        if current_price and trade_record.entry_price and trade_record.entry_price != 0:
            sl_target = None
            if trade_record.trailing_stop_active and trade_record.tsl_activation_price:
                sl_target = trade_record.tsl_activation_price
            elif not trade_record.trailing_stop_active and trade_record.stop_loss_price:
                sl_target = trade_record.stop_loss_price

            if sl_target:
                dist_sl_val = (
                    current_price - sl_target
                    if trade_record.side == "long"
                    else sl_target - current_price
                )
                dist_sl_pct = (dist_sl_val / trade_record.entry_price) * 100
                dist_sl_pct_str = f"{dist_sl_pct:.2f}%"
                if dist_sl_pct < 0.5:
                    dist_sl_color = NR

            if trade_record.take_profit_price:
                dist_tp_val = (
                    trade_record.take_profit_price - current_price
                    if trade_record.side == "long"
                    else current_price - trade_record.take_profit_price
                )
                dist_tp_pct = (dist_tp_val / trade_record.entry_price) * 100
                dist_tp_pct_str = f"{dist_tp_pct:.2f}%"
                if 0 < dist_tp_pct < 0.5:
                    dist_tp_color = NG

        row_data_list = [
            trade_record.symbol,
            trade_record.side.upper(),
            f"{trade_record.size:.{size_prec}f}",
            f"{trade_record.entry_price:.{price_prec}f}",
            (f"{current_price:.{price_prec}f}" if current_price is not None else "N/A"),
            (trade_record.pnl_quote if trade_record.pnl_quote is not None else "N/A"),
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
            NC,
            side_color,
            NC,
            NC,
            NB,
            None,
            None,
            NR,
            NG,
            dist_sl_color,
            dist_tp_color,
        ]
        print_table_row(
            row_data_list,
            column_widths,
            cell_colors=cell_custom_colors,
            default_color=NC,
            pnl_columns=[5, 6],
            decimal_precision=2,
        )

    print_neon_separator(length=table_length, color=NP)
    print("")


def display_recent_closed_trades(
    closed_trades: list["Tr"],
    market_infos: dict[str, dict],
    quote_currency: str,
    logger: logging.Logger,
    num_to_display: int = 5,
) -> None:
    """Displays recently closed positions in a neon-themed table."""
    print_neon_header(
        f"Recent Closed Trades (Last {num_to_display})", color=NP, length=130
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

    recent_trades_to_show = closed_trades[-num_to_display:]

    for trade_record in recent_trades_to_show:
        symbol_short = trade_record.symbol
        market_info = market_infos.get(symbol_short)

        price_prec, size_prec = 2, 4  # Defaults
        if market_info:
            price_prec = IndicatorCalculator.gpp(market_info, logger)
            size_prec = market_info.get("amountPrecision", 4)
        else:
            logger.warning(
                f"{NY}Market info not found for closed trade on {symbol_short}. "
                f"Using default precision.{RST}"
            )

        side_color = NG if trade_record.side == "long" else NR
        status_text = trade_record.status.replace("CLOSED_", "")
        status_color = (
            NG if "WIN" in status_text else NR if "LOSS" in status_text else NC
        )

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

        cell_custom_colors = [NC, side_color, NC, NC, NC, None, None, status_color]

        print_table_row(
            row_data_list,
            column_widths,
            cell_colors=cell_custom_colors,
            default_color=NC,
            pnl_columns=[5, 6],
            decimal_precision=(4 if quote_currency != "USDT" else 2),
        )

    print_neon_separator(length=130, color=NP)
    print("")


# --- SMS Alert Function ---
@handle_exceptions(default_return=False, message="Error sending SMS alert")
def send_sms_alert(
    message: str, recipient_number: str, logger: logging.Logger, config: dict[str, Any]
) -> bool:
    """Sends an SMS alert using Termux API if enabled in config.
    Returns True if SMS was sent or alerts are disabled, False if sending failed.
    """
    if not config.get("enable_sms_alerts", False):
        logger.debug("SMS alerts are disabled in config. Skipping.")
        return True

    if not recipient_number or not isinstance(recipient_number, str):
        logger.error(
            f"{NR}SMS recipient number is not configured or invalid. "
            f"Cannot send SMS.{RST}"
        )
        return False

    if not message or not isinstance(message, str):
        logger.error(f"{NR}SMS message is empty or invalid. Cannot send SMS.{RST}")
        return False

    sanitized_message = message.replace("`", "'").replace('"', "'")
    max_sms_length = 1500
    if len(sanitized_message) > max_sms_length:
        sanitized_message = sanitized_message[: max_sms_length - 3] + "..."
        logger.warning(
            f"{NY}SMS message truncated to {max_sms_length} characters.{RST}"
        )

    try:
        command = ["termux-sms-send", "-n", recipient_number, sanitized_message]
        logger.debug(f"Executing Termux SMS command: {' '.join(command)}")

        result = subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=30
        )

        if result.returncode == 0:
            logger.info(
                f"{NG}SMS alert sent successfully to {recipient_number}. "
                f"Message: '{sanitized_message}'{RST}"
            )
            return True
        error_output = result.stderr or result.stdout or "No output"
        logger.error(
            f"{NR}Failed to send SMS alert via Termux. Return code: "
            f"{result.returncode}. Error: {error_output.strip()}{RST}"
        )
        return False
    except FileNotFoundError:
        logger.error(
            f"{NR}Termux API command 'termux-sms-send' not found. "
            f"Is Termux API installed and configured?{RST}"
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
    """Sensitive Formatter for logging."""

    # Redact API keys from log messages for security.
    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        if AK:
            msg = msg.replace(AK, "***API_KEY_REDACTED***")
        if AS:
            msg = msg.replace(AS, "***API_SECRET_REDACTED***")
        return msg


@handle_exceptions(default_return={}, message="Error extending config")
def _extend_config_keys(
    current_config: dict[str, Any], default_config: dict[str, Any]
) -> dict[str, Any]:
    """Extend Current Config: Recursively adds missing keys."""
    updated_config = current_config.copy()
    for key, def_val in default_config.items():
        if key not in updated_config:
            updated_config[key] = def_val
        elif isinstance(def_val, dict) and isinstance(updated_config.get(key), dict):
            updated_config[key] = _extend_config_keys(updated_config[key], def_val)
    return updated_config


@handle_exceptions(
    default_return=None, message="Error converting config data recursively"
)
def _convert_data_recursively(obj: Any, default_obj: Any) -> Any:
    """Convert Data Recursively: Matches types with default_obj."""
    if obj is None:
        return default_obj
    if isinstance(default_obj, Decimal):
        try:
            return Decimal(str(obj))
        except (InvalidOperation, TypeError, ValueError):
            return default_obj
    elif isinstance(default_obj, dict) and isinstance(obj, dict):
        new_obj = {}
        for k_obj, v_obj in obj.items():
            new_obj[k_obj] = _convert_data_recursively(v_obj, default_obj.get(k_obj))
        for k_def, v_def in default_obj.items():
            if k_def not in obj:
                new_obj[k_def] = v_def
        return new_obj
    elif isinstance(default_obj, list) and isinstance(obj, list):
        if default_obj:
            return [_convert_data_recursively(item, default_obj[0]) for item in obj]
        return obj
    return obj


@handle_exceptions(
    default_return=False, message="Error validating numeric config value"
)
def _validate_numeric_config_value(
    config_data: dict[str, Any],
    key: str,
    default_value: int | float | Decimal | None,
    min_val: int | float | Decimal | None = None,
    max_val: int | float | Decimal | None = None,
    is_int: bool = False,
    allow_none: bool = False,
    logger: logging.Logger = logging.getLogger(__name__),
) -> bool:
    """Validate Numeric Config Value, correcting type/range."""
    value = config_data.get(key)
    original_value = value
    corrected = False

    if allow_none and value is None:
        return False

    if isinstance(value, bool):
        logger.warning(
            f"{NR}Config '{key}' ({value}) is bool, expected numeric. Defaulting.{RST}"
        )
        value = default_value
        corrected = True
    elif not isinstance(value, (int, float, Decimal)):
        logger.warning(
            f"{NR}Config '{key}' ({value}) type {type(value).__name__} "
            f"invalid. Defaulting.{RST}"
        )
        value = default_value
        corrected = True

    if isinstance(value, (int, float, Decimal)):
        try:
            dec_val = Decimal(str(value))
        except InvalidOperation:
            logger.warning(
                f"{NR}Config '{key}' ({value}) cannot be number. Defaulting.{RST}"
            )
            value = default_value
            corrected = True
            dec_val = Decimal(str(value))

        if is_int and not isinstance(value, int):
            if not dec_val == dec_val.to_integral_value():
                logger.warning(
                    f"{NR}Config '{key}' ({value}) must be int. Defaulting.{RST}"
                )
                value = default_value
                corrected = True
                dec_val = Decimal(str(value))

        if (min_val is not None and dec_val < Decimal(str(min_val))) or (
            max_val is not None and dec_val > Decimal(str(max_val))
        ):
            rng_str = ""
            if min_val is not None:
                rng_str += f" >= {min_val}"
            if max_val is not None:
                rng_str += f" <= {max_val}"
            logger.warning(
                f"{NR}Config '{key}' ({value}) out of range ({rng_str.strip()}). "
                f"Defaulting.{RST}"
            )
            value = default_value
            corrected = True

    if corrected:
        logger.warning(f"{NY}Corrected '{key}': {original_value} -> {value}{RST}")
        config_data[key] = value
        return True
    return False


def load_config(file_path: Path) -> dict[str, Any]:
    """Load Config: Loads and validates the configuration from `config.json`.
    If the file doesn't exist or is invalid, it creates a default one.
    """
    # Default configuration values
    default_config: Final[dict[str, Any]] = {
        "symbols_to_trade": ["BTC/USDT:USDT"],
        "exchange_id": "bybit",
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
        "psar_af": Decimal("0.02"),
        "psar_max_af": Decimal("0.2"),
        "sma_10_window": 10,
        "momentum_period": 7,
        "volume_ma_period": 15,
        "fib_window": 50,
        "orderbook_limit": 25,
        "enable_dynamic_signal_threshold": False,
        "dynamic_signal_threshold_atr_multiplier": Decimal("5.0"),
        "dynamic_signal_threshold_min_atr_leverage_on_baseline": Decimal("0.8"),
        "enable_confirmation_candle": False,
        "confirmation_candle_logic_type": "close_gt_signal_price",
        "enable_fib_based_tp": False,
        "enable_fib_based_sl": False,
        "fib_level_significance_percentage": Decimal("0.25"),
        "ehlers_fisher_length": DIP["ehlers_fisher_length"],
        "stoch_rsi_oversold_threshold": 25,
        "stoch_rsi_overbought_threshold": 75,
        "stop_loss_multiple": Decimal("1.8"),
        "take_profit_multiple": Decimal("0.7"),
        "atr_sl_period": 14,
        "atr_sl_multiplier": Decimal("1.5"),
        "atr_tp_period": 14,
        "atr_tp_multiplier": Decimal("1.0"),
        "volume_confirmation_multiplier": Decimal("1.5"),
        "volume_high_spike_multiplier": Decimal("2.5"),
        "volume_medium_spike_multiplier": Decimal("1.5"),
        "volume_low_spike_multiplier": Decimal("0.7"),
        "volume_negative_score": Decimal("-0.4"),
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
        "time_based_exit_minutes": None,
        "baseline_signal_score_threshold": Decimal("1.5"),
        "active_weight_set": "default",
        "indicator_thresholds": {
            "momentum_positive_threshold": Decimal("0.001"),
            "momentum_strong_positive_threshold": Decimal("0.005"),
            "stoch_rsi_crossover_strength": 5,
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
            "ehlers_fisher_buy_threshold": Decimal("0.5"),
            "ehlers_fisher_sell_threshold": Decimal("-0.5"),
            "ehlers_fisher_trend_confirmation_threshold": Decimal("0.1"),
            "sma10_score": Decimal("0.6"),
            "vwap_score": Decimal("0.7"),
            "bollinger_bands_extreme_score": Decimal("1.0"),
            "bollinger_bands_mid_score_multiplier": Decimal("0.7"),
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
                "ehlers_fisher": Decimal("0.2"),
                "confidence_score_weight": Decimal("0.5"),
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
                "ehlers_fisher": Decimal("0.2"),
                "confidence_score_weight": Decimal("0.4"),
            },
        },
        "indicators": {
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
            "ehlers_fisher": True,
        },
        "enable_orderbook_depth_analysis": False,
        "orderbook_depth_change_sensitivity": Decimal("0.1"),
        "orderbook_obi_weight": Decimal("0.7"),
        "orderbook_depth_change_weight": Decimal("0.3"),
        "enable_sms_alerts": False,
        "sms_recipient_number": "",
        "sms_report_interval_minutes": 60,
        "exit_confirmation_filters": {
            "enable_indicator_reversal_exit": True,
            "enable_dynamic_profit_target": True,
            "profit_target_atr_multiple": "2.0",
        },
        "main_loop_sleep_seconds": 5,
        "signal_processing": {
            "confidence_default_value": Decimal("0.75"),
            "confidence_ema_spread_threshold": Decimal("0.005"),
            "confidence_rsi_extreme_threshold": Decimal("15"),
            "confidence_rsi_mid_range_boost": Decimal("0.1"),
            "confidence_stochrsi_extreme_threshold": Decimal("10"),
            "confidence_stochrsi_neutral_threshold": Decimal("40"),
            "confidence_cci_extreme_threshold_multiplier": Decimal("1.5"),
            "confidence_willr_extreme_threshold_offset": Decimal("10"),
            "confidence_psar_proximity_threshold_atr_multiple": Decimal("0.5"),
            "confidence_sma_deviation_threshold": Decimal("0.002"),
            "confidence_vwap_deviation_threshold": Decimal("0.003"),
            "confidence_mfi_extreme_threshold": Decimal("10"),
            "confidence_bb_middle_zone_threshold": Decimal("0.2"),
            "confidence_obi_strong_threshold": Decimal("0.5"),
            "confidence_obi_weak_threshold": Decimal("0.1"),
            "confidence_fisher_crossover_min_diff": Decimal("0.1"),
            "confidence_fisher_trend_min_abs": Decimal("0.3"),
            "minimum_indicator_participation_threshold": Decimal("0.60"),
            "ema_smoothing_alpha_signal_score": Decimal("0.3"),
            "ema_smoothing_alpha_confidence": Decimal("0.2"),
            "enable_confidence_based_threshold_scaling": True,
            "confidence_threshold_scaling_factor": Decimal("0.5"),
            "min_confidence_for_threshold_scaling": Decimal("0.4"),
            "max_confidence_for_threshold_scaling": Decimal("0.8"),
            "min_signal_threshold_after_confidence_scaling_pct_of_baseline": Decimal(
                "0.5"
            ),
            "signal_neutral_zone_threshold": Decimal("0.15"),
        },
        "symbol_signal_cooldown_candles": 3,
        "account_position_mode": "one_way",
    }
    logger = logging.getLogger("config_loader")
    user_config = default_config.copy()

    if not file_path.exists():
        try:
            s_cfg = json.loads(json.dumps(default_config, default=str))
            file_path.write_text(json.dumps(s_cfg, indent=4), encoding="utf-8")
            log_msg = (
                f"{NY}Created default config file: {file_path}. "
                f"A new scroll of destiny has been penned!{RST}"
            )
            logger.info(log_msg)
            return default_config
        except OSError as e:
            logger.error(
                f"{NR}Error creating default config file "
                f"{file_path}: {e}. The quill broke!{RST}"
            )
            return default_config

    try:
        cfg_file = json.loads(file_path.read_text(encoding="utf-8"))
        user_config = _convert_data_recursively(cfg_file, default_config)
        user_config = _extend_config_keys(user_config, default_config)

        save_needed = False

        if user_config.get("interval") not in VI:
            log_msg = (
                f"{NR}Invalid interval "
                f"'{user_config.get('interval')}' found in config. "
                f"Using default '{default_config['interval']}'. "
                f"The temporal flow is disrupted!{RST}"
            )
            logger.warning(log_msg)
            user_config["interval"] = default_config["interval"]
            save_needed = True
        if user_config.get("entry_order_type") not in ["market", "limit"]:
            log_msg = (
                f"{NR}Invalid entry_order_type "
                f"'{user_config.get('entry_order_type')}' in config. "
                f"Using default 'market'. The entry spell is "
                f"unclear!{RST}"
            )
            logger.warning(log_msg)
            user_config["entry_order_type"] = "market"
            save_needed = True

        num_params_validate = {
            "retry_delay": {"min": 0, "is_int": True},
            "risk_per_trade": {"min": Decimal("0"), "max": Decimal("1")},
            "leverage": {"min": 1, "is_int": True},
            "max_concurrent_positions": {"min": 1, "is_int": True},
            "baseline_signal_score_threshold": {"min": Decimal("0")},
            "dynamic_signal_threshold_atr_multiplier": {"min": Decimal("0.0")},
            "dynamic_signal_threshold_min_atr_leverage_on_baseline": {
                "min": Decimal("0.1"),
                "max": Decimal("2.0"),
            },
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
            "volume_high_spike_multiplier": {"min": Decimal("0.01")},
            "volume_medium_spike_multiplier": {"min": Decimal("0.01")},
            "volume_low_spike_multiplier": {"min": Decimal("0.01")},
            "volume_negative_score": {},
            "orderbook_depth_change_sensitivity": {
                "min": Decimal("0.01"),
                "max": Decimal("0.5"),
            },
            "orderbook_obi_weight": {"min": Decimal("0.0"), "max": Decimal("1.0")},
            "orderbook_depth_change_weight": {
                "min": Decimal("0.0"),
                "max": Decimal("1.0"),
            },
            "fib_level_significance_percentage": {
                "min": Decimal("0.05"),
                "max": Decimal("1.0"),
            },
            "sms_report_interval_minutes": {
                "min": 1,
                "is_int": True,
                "allow_none": False,
            },
            # Signal Processing Numerics
            "confidence_default_value": {"min": Decimal("0.0"), "max": Decimal("1.0")},
            "confidence_ema_spread_threshold": {"min": Decimal("0.0")},
            "confidence_rsi_extreme_threshold": {
                "min": Decimal("0"),
                "max": Decimal("50"),
            },
            "confidence_rsi_mid_range_boost": {
                "min": Decimal("0.0"),
                "max": Decimal("0.5"),
            },
            "confidence_stochrsi_extreme_threshold": {
                "min": Decimal("0"),
                "max": Decimal("50"),
            },
            "confidence_stochrsi_neutral_threshold": {
                "min": Decimal("0"),
                "max": Decimal("100"),
            },
            "confidence_cci_extreme_threshold_multiplier": {"min": Decimal("1.0")},
            "confidence_willr_extreme_threshold_offset": {
                "min": Decimal("0"),
                "max": Decimal("50"),
            },
            "confidence_psar_proximity_threshold_atr_multiple": {"min": Decimal("0.0")},
            "confidence_sma_deviation_threshold": {"min": Decimal("0.0")},
            "confidence_vwap_deviation_threshold": {"min": Decimal("0.0")},
            "confidence_mfi_extreme_threshold": {
                "min": Decimal("0"),
                "max": Decimal("50"),
            },
            "confidence_bb_middle_zone_threshold": {
                "min": Decimal("0.0"),
                "max": Decimal("0.5"),
            },
            "confidence_obi_strong_threshold": {
                "min": Decimal("0.0"),
                "max": Decimal("1.0"),
            },
            "confidence_obi_weak_threshold": {
                "min": Decimal("0.0"),
                "max": Decimal("1.0"),
            },
            "confidence_fisher_crossover_min_diff": {"min": Decimal("0.0")},
            "confidence_fisher_trend_min_abs": {"min": Decimal("0.0")},
            "minimum_indicator_participation_threshold": {
                "min": Decimal("0.0"),
                "max": Decimal("1.0"),
            },
            "ema_smoothing_alpha_signal_score": {
                "min": Decimal("0.01"),
                "max": Decimal("1.0"),
            },
            "ema_smoothing_alpha_confidence": {
                "min": Decimal("0.01"),
                "max": Decimal("1.0"),
            },
            "confidence_threshold_scaling_factor": {
                "min": Decimal("0.0"),
                "max": Decimal("2.0"),
            },
            "min_confidence_for_threshold_scaling": {
                "min": Decimal("0.0"),
                "max": Decimal("1.0"),
            },
            "max_confidence_for_threshold_scaling": {
                "min": Decimal("0.0"),
                "max": Decimal("1.0"),
            },
            "min_signal_threshold_after_confidence_scaling_pct_of_baseline": {
                "min": Decimal("0.1"),
                "max": Decimal("1.0"),
            },
        }
        top_level_num_params = {
            "symbol_signal_cooldown_candles": {"min": 0, "is_int": True},
            "main_loop_sleep_seconds": {"min": 1, "is_int": True},
        }
        params_to_validate = {**top_level_num_params}
        # Merge num_params_validate into params_to_validate, ensuring no
        # conflicts with top_level_num_params
        for k, v in num_params_validate.items():
            if k not in params_to_validate:
                params_to_validate[k] = v
            # else: # Key conflict, decide on precedence or merge rules if
            # needed. Here, top_level takes precedence if defined.

        for param_key, rules in params_to_validate.items():
            is_sig_proc_param = param_key in default_config.get("signal_processing", {})
            dict_to_val = (
                user_config.get("signal_processing", {})
                if is_sig_proc_param
                else user_config
            )
            def_val_src = (
                default_config.get("signal_processing", {})
                if is_sig_proc_param
                else default_config
            )

            # Ensure param_key exists in def_val_src before using it
            if param_key not in def_val_src:
                logger.warning(
                    f"{NY}Config key '{param_key}' not in default config "
                    f"source. Skipping validation.{RST}"
                )
                continue

            if _validate_numeric_config_value(
                dict_to_val,
                param_key,
                def_val_src[param_key],
                min_val=rules.get("min"),
                max_val=rules.get("max"),
                is_int=rules.get("is_int", False),
                allow_none=rules.get("allow_none", False),
                logger=logger,
            ):
                save_needed = True
                if is_sig_proc_param:
                    user_config["signal_processing"] = dict_to_val

        boolean_params = [
            "enable_orderbook_depth_analysis",
            "enable_dynamic_signal_threshold",
            "enable_confirmation_candle",
            "enable_fib_based_tp",
            "enable_fib_based_sl",
            "enable_sms_alerts",
            "enable_trading",
            "use_sandbox",
            "enable_trailing_stop",
            "enable_break_even",
        ]
        sig_proc_bool_params = [
            "enable_confidence_based_threshold_scaling",
        ]

        for param_key in boolean_params:
            if not isinstance(user_config.get(param_key), bool):
                log_msg = (
                    f"{NR}Invalid type for '{param_key}' "
                    f"({user_config.get(param_key)}). Must be boolean. "
                    f"Setting to default "
                    f"'{default_config[param_key]}'.{RST}"
                )
                logger.warning(log_msg)
                user_config[param_key] = default_config[param_key]
                save_needed = True

        sig_proc_cfg = user_config.get("signal_processing", {})
        def_sig_proc = default_config.get("signal_processing", {})
        for param_key in sig_proc_bool_params:
            if not isinstance(sig_proc_cfg.get(param_key), bool):
                log_msg = (
                    f"{NR}Invalid type for 'signal_processing.{param_key}' ({sig_proc_cfg.get(param_key)}). "
                    f"{param_key}' ({sig_proc_cfg.get(param_key)}). "
                    f"Must be boolean. Setting to default "
                    f"'{def_sig_proc.get(param_key)}'.{RST}"
                )
                logger.warning(log_msg)
                sig_proc_cfg[param_key] = def_sig_proc.get(param_key)
                save_needed = True
        if save_needed:  # If signal_processing sub-dict was modified
            user_config["signal_processing"] = sig_proc_cfg

        valid_confirm_types = [
            "close_gt_signal_price",
            "close_gt_signal_high",
            "confirm_candle_bullish_bearish",
        ]
        confirm_type = user_config.get("confirmation_candle_logic_type")
        if confirm_type not in valid_confirm_types:
            def_confirm = default_config["confirmation_candle_logic_type"]
            log_msg = (
                f"{NR}Invalid 'confirmation_candle_logic_type' "
                f"({confirm_type}). Must be one of "
                f"{valid_confirm_types}. Setting to default "
                f"'{def_confirm}'. Unknown spell!{RST}"
            )
            logger.warning(log_msg)
            user_config["confirmation_candle_logic_type"] = def_confirm
            save_needed = True

        sms_recipient = user_config.get("sms_recipient_number")
        if not isinstance(sms_recipient, str):
            def_sms_num = default_config["sms_recipient_number"]
            log_msg = (
                f"{NR}Invalid type for 'sms_recipient_number' "
                f"({sms_recipient}). Must be string. Setting to "
                f"default '{def_sms_num}'. Unclear address!{RST}"
            )
            logger.warning(log_msg)
            user_config["sms_recipient_number"] = def_sms_num
            save_needed = True
        if sms_recipient and not all(
            c.isdigit() or c in ["+", "-", "(", ")", " "] for c in sms_recipient
        ):
            log_msg = (
                f"{NY}Config 'sms_recipient_number' ('{sms_recipient}')"
                f" has unusual chars. Ensure correctness. Odd "
                f"address!{RST}"
            )
            logger.warning(log_msg)

        exit_filters = user_config.get("exit_confirmation_filters", {})
        def_exit_filters = default_config["exit_confirmation_filters"]
        exit_bool_params = [
            "enable_indicator_reversal_exit",
            "enable_dynamic_profit_target",
        ]
        for pk in exit_bool_params:
            if not isinstance(exit_filters.get(pk), bool):
                log_msg = (
                    f"{NR}Invalid type for 'exit_confirmation_filters.{pk}'."
                    f"{pk}'. Must be boolean. Setting to default "
                    f"'{def_exit_filters.get(pk)}'.{RST}"
                )
                logger.warning(log_msg)
                exit_filters[pk] = def_exit_filters.get(pk)
                save_needed = True
        if _validate_numeric_config_value(
            exit_filters,
            "profit_target_atr_multiple",
            def_exit_filters["profit_target_atr_multiple"],
            min_val=Decimal("0.1"),
            logger=logger,
        ):
            save_needed = True
        user_config["exit_confirmation_filters"] = exit_filters

        symbols = user_config.get("symbols_to_trade")
        if not (
            isinstance(symbols, list)
            and symbols
            and all(isinstance(s, str) for s in symbols)
        ):
            log_msg = (
                f"{NR}Invalid 'symbols_to_trade' format. Must be non-"
                f"empty list of strings. Unreadable scroll!{RST}"
            )
            logger.warning(log_msg)
            user_config["symbols_to_trade"] = default_config["symbols_to_trade"]
            logger.warning(
                f"{NY}Using default 'symbols_to_trade': "
                f"{user_config['symbols_to_trade']}{RST}"
            )
            save_needed = True

        active_set = user_config.get("active_weight_set")
        if active_set not in user_config.get("weight_sets", {}):
            log_msg = (
                f"{NR}Active weight set '{active_set}' not in "
                f"'weight_sets'. Using 'default'. Skewed balance!{RST}"
            )
            logger.warning(log_msg)
            user_config["active_weight_set"] = "default"
            save_needed = True

        valid_pos_modes = ["one_way", "hedge"]
        pos_mode = user_config.get("account_position_mode")
        if pos_mode not in valid_pos_modes:
            def_pos_mode = default_config["account_position_mode"]
            log_msg = (
                f"{NR}Invalid 'account_position_mode' ('{pos_mode}'). "
                f"Must be one of {valid_pos_modes}. Setting to "
                f"default '{def_pos_mode}'. Unclear mode!{RST}"
            )
            logger.warning(log_msg)
            user_config["account_position_mode"] = def_pos_mode
            save_needed = True

        for pk, def_val in DIP.items():
            min_v = Decimal("0.0") if "psar" in pk else 1
            max_v = Decimal("1.0") if "psar" in pk else None
            is_int = isinstance(def_val, int) and "psar" not in pk
            if _validate_numeric_config_value(
                user_config,
                pk,
                def_val,
                min_val=min_v,
                max_val=max_v,
                is_int=is_int,
                logger=logger,
            ):
                save_needed = True

        active_weights = user_config.get("weight_sets", {}).get(
            user_config.get("active_weight_set", "default"), {}
        )
        for ind_key, w_val in active_weights.items():
            if _validate_numeric_config_value(
                active_weights,
                ind_key,
                Decimal("0.0"),
                min_val=Decimal("0.0"),
                logger=logger,
            ):
                save_needed = True
                user_config["weight_sets"][user_config["active_weight_set"]][
                    ind_key
                ] = w_val

        ind_thresh = user_config.get("indicator_thresholds", {})
        def_thresh = default_config.get("indicator_thresholds", {})
        for thresh_key, def_val_t in def_thresh.items():
            is_int_t = isinstance(def_val_t, int)
            if _validate_numeric_config_value(
                ind_thresh, thresh_key, def_val_t, is_int=is_int_t, logger=logger
            ):
                save_needed = True
                user_config["indicator_thresholds"][thresh_key] = ind_thresh[thresh_key]

        if save_needed:
            try:
                s_cfg = json.loads(json.dumps(user_config, default=str))
                file_path.write_text(json.dumps(s_cfg, indent=4), encoding="utf-8")
                log_msg = (
                    f"{NY}Corrected invalid values and saved updated "
                    f"config file: {file_path}. Runes aligned!{RST}"
                )
                logger.info(log_msg)
            except OSError as e:
                logger.error(
                    f"{NR}Error writing corrected config file "
                    f"{file_path}: {e}. Quill broke!{RST}"
                )
        return user_config
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(
            f"{NR}Error loading config file {file_path}: {e}. Using "
            f"default. Corrupted text!{RST}"
        )
        try:
            s_cfg = json.loads(json.dumps(default_config, default=str))
            file_path.write_text(json.dumps(s_cfg, indent=4), encoding="utf-8")
            log_msg = (
                f"{NY}Created default config file: {file_path}. New scroll forged!{RST}"
            )
            logger.info(log_msg)
        except OSError as e_create:
            logger.error(
                f"{NR}Error creating default config file after load error: "
                f"{e_create}. Forge cold!{RST}"
            )
        return default_config


_initial_config_from_file = load_config(CFP)
QC: Final[str] = _initial_config_from_file.get("quote_currency", "USDT")


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
        log_file_path = LD / f"{logger_name}.log"
        file_handler = RotatingFileHandler(
            log_file_path, maxBytes=LDS, backupCount=5, encoding="utf-8"
        )
        file_fmt_str = (
            "%(asctime)s - %(levelname)s - [%(name)s:%(lineno)d] - %(message)s"
        )
        file_formatter = SF(file_fmt_str)
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)
    except Exception as e:
        print(
            f"{NR}Error setting up file logger for {log_file_path}: {e}. "
            f"Log scroll sealed!{RST}"
        )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_fmt_str = "%(asctime)s - %(levelname)-8s - [%(name)s] - %(message)s"
    stream_formatter = SF(
        stream_fmt_str,
        datefmt="%Y-%m-%d %H:%M:%S %Z",
    )
    stream_formatter.converter = lambda *args: datetime.now(TZ).timetuple()
    stream_handler.setFormatter(stream_formatter)
    stream_handler.setLevel(logging.INFO)
    logger.addHandler(stream_handler)

    logger.propagate = False
    return logger


def retry_api_call(
    max_retries: int = MAR,
    retry_delay_s: int = RDS,  # Renamed for clarity
    catch_exceptions: tuple = (
        ccxt.NetworkError,
        ccxt.RequestTimeout,
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        ccxt.RateLimitExceeded,
    ),
):
    """Decorator for retrying API calls."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = kwargs.get("logger", logging.getLogger(func.__module__))
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except catch_exceptions as e:
                    retries += 1
                    logger.warning(
                        f"{NY}API call {func.__name__} failed (Attempt {retries}/{max_retries}): {e}. "
                        f"Retrying in {retry_delay_s} seconds...{RST}"
                    )
                    time.sleep(retry_delay_s)
                except Exception as e:
                    logger.error(
                        f"{NR}An unexpected error occurred in {func.__name__}: {e}. Aborting retries.{RST}",
                        exc_info=True,
                    )
                    break
            logger.error(
                f"{NR}API call {func.__name__} failed after {max_retries} attempts. "
                f"The connection to the digital realm is severed!{RST}"
            )
            return None  # Or raise a custom exception

        return wrapper

    return decorator


# --- New Exit Signal Management Class ---


class TradeManager:
    """Manages active and closed trades, including persistence."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.logger = slg("TradeManager")
        self.open_trades: dict[str, TradeRecord] = {}
        self.closed_trades: list[TradeRecord] = []
        self.total_pnl: Decimal = Decimal("0")
        self.current_balance: Decimal = Decimal("0")
        self.exchange_ref: ccxt.Exchange | None = None
        self.market_info_cache: dict[str, dict] = {}  # Cache for market info
        self._initialized = True

    def set_exchange_reference(self, exchange: ccxt.Exchange):
        self.exchange_ref = exchange

    def _load_trades(self):
        """Loads trade records from file."""
        self.logger.info(f"DEBUG: _load_trades: TRP path is {TRP.resolve()}")
        if TRP.exists():
            self.logger.info(f"DEBUG: _load_trades: {TRP} exists. Attempting to load.")
            try:
                with open(TRP, encoding="utf-8") as f:
                    content = f.read()
                    self.logger.info(
                        f"DEBUG: _load_trades: Content of {TRP}: {content[:500]}"
                    )  # Log first 500 chars
                    data = json.loads(
                        content
                    )  # Use content to ensure full read before parse
                    self.logger.info(
                        f"DEBUG: _load_trades: Loaded data type: {type(data)}"
                    )
                    if isinstance(data, dict):
                        open_trades_data = data.get("open_trades", {})
                        self.logger.info(
                            f"DEBUG: _load_trades: 'open_trades' field type: {type(open_trades_data)}"
                        )
                        if isinstance(open_trades_data, list):
                            self.logger.error(
                                f"{NR}_load_trades: 'open_trades' in {TRP} is a LIST, expected a DICT. File content: {content[:500]}{RST}"
                            )
                            # Handle error or convert if possible, for now, reset to avoid crash
                            self.open_trades = {}
                            self.logger.warning(
                                f"{NY}_load_trades: Resetting open_trades to empty dict due to list format.{RST}"
                            )
                        else:
                            self.open_trades = {
                                k: TradeRecord.from_dict(v)
                                for k, v in open_trades_data.items()
                            }
                    else:
                        self.logger.error(
                            f"{NR}_load_trades: Data loaded from {TRP} is not a dictionary. Type: {type(data)}. Content: {content[:500]}{RST}"
                        )
                        # Reset to defaults if overall data is not a dict
                        self.open_trades = {}
                        self.closed_trades = []
                        self.total_pnl = Decimal("0")
                        self.current_balance = Decimal("0")
                        return

                    self.closed_trades = [
                        TradeRecord.from_dict(v) for v in data.get("closed_trades", [])
                    ]
                    self.total_pnl = Decimal(str(data.get("total_pnl", "0")))
                    self.current_balance = Decimal(
                        str(data.get("current_balance", "0"))
                    )
                self.logger.info(
                    f"{NG}Trade records loaded successfully from {TRP}. Ledger restored!{RST}"
                )
            except (json.JSONDecodeError, InvalidOperation, FileNotFoundError) as e:
                self.logger.error(
                    f"{NR}Error loading trade records from {TRP}: {e}. Starting with empty ledger.{RST}"
                )
                self.open_trades = {}
                self.closed_trades = []
                self.total_pnl = Decimal("0")
                self.current_balance = Decimal("0")
        else:
            self.logger.info(
                f"{NY}No trade records file found at {TRP}. Starting with a fresh ledger.{RST}"
            )

    def _save_trades(self):
        """Saves trade records to file."""
        data = {
            "open_trades": {k: v.to_dict() for k, v in self.open_trades.items()},
            "closed_trades": [v.to_dict() for v in self.closed_trades],
            "total_pnl": str(self.total_pnl),
            "current_balance": str(self.current_balance),
        }
        try:
            with open(TRP, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            self.logger.debug(f"{NB}Trade records saved to {TRP}. Ledger updated!{RST}")
        except OSError as e:
            self.logger.error(
                f"{NR}Error saving trade records to {TRP}: {e}. Ledger not updated!{RST}"
            )

    def add_open_trade(self, trade: TradeRecord):
        """Adds a new open trade to the tracker."""
        if trade.symbol in self.open_trades:
            self.logger.warning(
                f"{NY}Trade for {trade.symbol} already exists in open trades. Overwriting.{RST}"
            )
        self.open_trades[trade.symbol] = trade
        self._save_trades()
        self.logger.info(
            f"{NG}Added open trade: {trade.symbol} ({trade.side} {trade.size}) at {trade.entry_price}. A new pact with the market!{RST}"
        )

    def close_trade(
        self,
        symbol: str,
        exit_price: Decimal,
        exit_time: datetime,
        current_balance: Decimal,
        exit_reason: str = "UNKNOWN",
    ):
        """Closes an open trade, calculates PnL, and moves it to closed trades."""
        trade = self.open_trades.pop(symbol, None)
        if trade:
            trade.exit_price = exit_price
            trade.exit_time = exit_time
            trade.trade_duration_seconds = int(
                (exit_time - trade.entry_time).total_seconds()
            )
            trade.exit_reason = exit_reason

            # Fetch market info for accurate PnL calculation
            market_info = self.market_info_cache.get(symbol)
            if not market_info and self.exchange_ref:
                try:
                    market_info = IndicatorCalculator.get_market_info(
                        symbol, self.exchange_ref, self.logger
                    )
                    self.market_info_cache[symbol] = market_info
                except Exception as e:
                    self.logger.error(
                        f"{NR}Failed to fetch market info for {symbol} during trade closure: {e}. PnL calculation might be inaccurate.{RST}"
                    )
                    market_info = {"contractSizeDecimal": Decimal("1")}  # Fallback

            contract_size = market_info.get("contractSizeDecimal", Decimal("1"))
            if not isinstance(contract_size, Decimal) or contract_size <= 0:
                self.logger.error(
                    f"{NR}Invalid contractSizeDecimal for {symbol} during closure: {contract_size}. Cannot calculate accurate PnL.{RST}"
                )
                contract_size = Decimal("1")

            if trade.side == "long":
                trade.realized_pnl_quote = (
                    (trade.exit_price - trade.entry_price) * trade.size * contract_size
                )
            else:  # short
                trade.realized_pnl_quote = (
                    (trade.entry_price - trade.exit_price) * trade.size * contract_size
                )

            # Calculate percentage PnL based on initial capital
            if trade.initial_capital and trade.initial_capital > 0:
                trade.realized_pnl_percentage = (
                    trade.realized_pnl_quote / trade.initial_capital
                ) * 100
            # Fallback for percentage PnL if initial_capital is not set or zero
            # This is a simplified calculation and might not reflect true ROI
            elif trade.entry_price > 0:
                trade.realized_pnl_percentage = (
                    trade.realized_pnl_quote
                    / (trade.size * trade.entry_price * contract_size / trade.leverage)
                ) * 100
            else:
                trade.realized_pnl_percentage = Decimal("0")

            self.total_pnl += trade.realized_pnl_quote
            self.current_balance = current_balance

            if trade.realized_pnl_quote >= 0:
                trade.status = "CLOSED_WIN"
                self.logger.info(
                    f"{NG}Closed trade for {symbol} at {trade.exit_price} (Reason: {exit_reason}). "
                    f"PnL: {trade.realized_pnl_quote:.4f} {QC} ({trade.realized_pnl_percentage:.2f}%). "
                    f"A successful alchemical transmutation!{RST}"
                )
            else:
                trade.status = "CLOSED_LOSS"
                self.logger.info(
                    f"{NR}Closed trade for {symbol} at {trade.exit_price} (Reason: {exit_reason}). "
                    f"PnL: {trade.realized_pnl_quote:.4f} {QC} ({trade.realized_pnl_percentage:.2f}%). "
                    f"A minor tremor in the market's flow.{RST}"
                )
            self.closed_trades.append(trade)
            self._save_trades()
        else:
            self.logger.warning(
                f"{NY}Attempted to close non-existent trade for {symbol}. The trade was already a phantom.{RST}"
            )

    def get_open_trade(self, symbol: str) -> TradeRecord | None:
        """Retrieves an open trade record by symbol."""
        return self.open_trades.get(symbol)

    def get_all_open_trades(self) -> dict[str, TradeRecord]:
        """Returns all open trade records."""
        return self.open_trades

    def get_all_closed_trades(self) -> list[TradeRecord]:
        """Returns all closed trade records."""
        return self.closed_trades

    def display_metrics(self):
        """Displays key trading metrics in a neon-themed summary."""
        clear_screen()
        print_neon_header("XR Scalper Bot Metrics", color=NP)
        print_neon_separator(length=60, color=NP)

        total_wins = sum(1 for t in self.closed_trades if t.status == "CLOSED_WIN")
        total_losses = sum(1 for t in self.closed_trades if t.status == "CLOSED_LOSS")
        total_trades = len(self.closed_trades)
        win_rate = (
            (total_wins / total_trades) * 100 if total_trades > 0 else Decimal("0")
        )

        print(format_metric("Total PnL", self.total_pnl, NB, is_pnl=True))
        print(
            format_metric(
                "Current Balance",
                self.current_balance,
                NB,
                value_precision=2,
                unit=f" {QC}",
            )
        )
        print(format_metric("Open Positions", len(self.open_trades), NB))
        print(format_metric("Closed Trades", total_trades, NB))
        print(format_metric("Wins", total_wins, NG))
        print(format_metric("Losses", total_losses, NR))
        print(
            format_metric(
                "Win Rate",
                win_rate,
                NG if win_rate >= 50 else NR,
                value_precision=2,
                unit="%",
            )
        )

        # Calculate average PnL per trade
        avg_pnl_per_trade = Decimal("0")
        if total_trades > 0:
            avg_pnl_per_trade = self.total_pnl / total_trades
        print(format_metric("Avg PnL/Trade", avg_pnl_per_trade, NB, is_pnl=True))

        avg_win = Decimal("0")
        if total_wins > 0:
            total_win_pnl = sum(
                t.realized_pnl_quote
                for t in self.closed_trades
                if t.status == "CLOSED_WIN" and t.realized_pnl_quote is not None
            )
            avg_win = total_win_pnl / total_wins
        print(format_metric("Avg Win", avg_win, NG, is_pnl=True))

        avg_loss = Decimal("0")
        if total_losses > 0:
            total_loss_pnl = sum(
                t.realized_pnl_quote
                for t in self.closed_trades
                if t.status == "CLOSED_LOSS" and t.realized_pnl_quote is not None
            )
            avg_loss = total_loss_pnl / total_losses
        print(format_metric("Avg Loss", avg_loss, NR, is_pnl=True))

        print_neon_separator(length=60, color=NP)
        print("")


# Global instance of TradeManager
TradeTracker = TradeManager()


# --- Exchange Initialization ---
@retry_api_call()
@handle_exceptions(default_return=None, message="Error initializing exchange")
def initialize_exchange(
    config: dict[str, Any], logger: logging.Logger
) -> ccxt.Exchange | None:
    """Initializes the CCXT exchange client based on configuration."""
    exchange_id = config.get("exchange_id", "bybit").lower()

    # Common CCXT options
    exchange_options = {
        "apiKey": AK,
        "secret": AS,
        "enableRateLimit": True,
        "options": {
            "defaultType": "future",  # Default to futures for Bybit
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
        logger.critical(
            f"{NR}Exchange ID '{exchange_id}' not found in CCXT. Check config.json. Chosen realm unknown!{RST}"
        )
        return None

    exchange_class = getattr(ccxt, exchange_id)
    exchange = exchange_class(exchange_options)

    if config.get("use_sandbox"):
        logger.warning(
            f"{NY}USING SANDBOX MODE (Testnet) for {exchange.id}. Tread lightly, training ground!{RST}"
        )
        if hasattr(exchange, "set_sandbox_mode"):
            exchange.set_sandbox_mode(True)
        else:
            logger.warning(
                f"{NY}{exchange.id} lacks set_sandbox_mode. Ensure Testnet API keys manually.{RST}"
            )
            # Manual override for Bybit testnet URL if not set by set_sandbox_mode
            if exchange.id == "bybit" and "testnet" not in exchange.urls["api"]:
                exchange.urls["api"] = "https://api-testnet.bybit.com"
                logger.warning(
                    f"{NY}Manually set Bybit Testnet API URL: {exchange.urls['api']}. Hidden path!{RST}"
                )

    logger.info(
        f"{NB}Loading markets for {exchange.id}... Unveiling trade scrolls.{RST}"
    )
    try:
        logger.info(
            f"{NB}Loading markets for {exchange.id}... Unveiling trade scrolls.{RST}"
        )
        exchange.load_markets()
        logger.info(f"{NB}Markets loaded for {exchange.id}.{RST}")
    except ccxt.RateLimitExceeded as e_rl:
        if (
            "CloudFront" in str(e_rl)
            or "block access from your country" in str(e_rl).lower()
        ):
            logger.warning(
                f"{NY}Geo-blocking error during load_markets for {exchange.id}: {e_rl}{RST}"
            )
            if config.get("use_sandbox") or os.getenv("JULES_TEST_MODE") == "true":
                logger.warning(
                    f"{NY}Sandbox/Test mode: Proceeding without loaded markets. Bot functionality will be limited.{RST}"
                )
            else:
                logger.critical(
                    f"{NR}Geo-blocking error during load_markets for {exchange.id}. Cannot proceed.{RST}"
                )
                return None
        else:  # Other RateLimitExceeded error
            logger.critical(
                f"{NR}RateLimitExceeded during load_markets for {exchange.id}: {e_rl}. Cannot proceed.{RST}"
            )
            return None  # Or re-raise depending on desired handling
    except (
        ccxt.ExchangeError
    ) as e_ex:  # Catch other exchange errors during load_markets
        logger.critical(
            f"{NR}ExchangeError during load_markets for {exchange.id}: {e_ex}. Cannot proceed.{RST}"
        )
        return None
    except Exception as e_gen:  # Catch any other unexpected error
        logger.critical(
            f"{NR}Unexpected error during load_markets for {exchange.id}: {e_gen}. Cannot proceed.{RST}"
        )
        return None

    logger.info(
        f"{NB}CCXT exchange initialized ({exchange.id}). Sandbox: {config.get('use_sandbox')}. Connection forged!{RST}"
    )

    # Attempt initial balance fetch to confirm connection (only if markets loaded or if we want to try anyway)
    # For now, let's only attempt if markets were successfully loaded, or adjust logic if needed.
    # If markets did not load due to geo-blocking, this will also likely fail.
    account_type = "UNIFIED"  # For Bybit V5 unified account
    logger.info(
        f"{NB}Attempting initial balance fetch (Account: {account_type}) for {QC}... Probing holdings.{RST}"
    )
    try:
        params = {"accountType": account_type} if exchange.id == "bybit" else {}
        balance = exchange.fetch_balance(params=params)
        balance_value = balance.get(QC, {}).get("free", Decimal("0"))
        logger.info(
            f"{NG}Connected & fetched initial balance. Coffers open! (Example: {QC} available: {balance_value}){RST}"
        )
        TradeTracker.current_balance = balance_value  # Update global tracker
    except ccxt.ExchangeError as err:
        logger.warning(
            f"{NY}Exchange error on initial balance fetch ({account_type}): {err}. Trying default... Minor tremor.{RST}"
        )
        try:
            balance = exchange.fetch_balance()
            balance_value = balance.get(QC, {}).get("free", Decimal("0"))
            logger.info(
                f"{NG}Fetched balance with default params. Path clearer! (Example: {QC} available: {balance_value}){RST}"
            )
            TradeTracker.current_balance = balance_value  # Update global tracker
        except (
            ccxt.RateLimitExceeded
        ) as e_rl_fb:  # Specifically catch geo-blocking on fallback too
            if (
                "CloudFront" in str(e_rl_fb)
                or "block access from your country" in str(e_rl_fb).lower()
            ):
                logger.warning(
                    f"{NY}Geo-blocking error during fallback fetch_balance: {e_rl_fb}{RST}"
                )
                if config.get("use_sandbox") or os.getenv("JULES_TEST_MODE") == "true":
                    logger.warning(
                        f"{NY}Sandbox/Test mode: Proceeding with default balance (0).{RST}"
                    )
                    TradeTracker.current_balance = Decimal("0")  # Set a default
                else:
                    logger.error(
                        f"{NR}Geo-blocking error during fallback fetch_balance. Cannot confirm connection.{RST}"
                    )
                    return None
            else:  # Other RateLimitExceeded
                logger.error(
                    f"{NR}RateLimitExceeded during fallback fetch_balance: {e_rl_fb}. Cannot confirm connection.{RST}"
                )
                return None
        except Exception as e:  # Catch other general exceptions for the fallback
            logger.error(
                f"{NR}Failed to fetch balance even with default params: {e}. Cannot confirm connection.{RST}"
            )
            if config.get("use_sandbox") or os.getenv("JULES_TEST_MODE") == "true":
                logger.warning(
                    f"{NY}Sandbox/Test mode: Proceeding with default balance (0) despite error.{RST}"
                )
                TradeTracker.current_balance = Decimal("0")  # Set a default
            else:
                return None
    except ccxt.RateLimitExceeded as e_rl_main:  # Geo-blocking on primary fetch_balance
        if (
            "CloudFront" in str(e_rl_main)
            or "block access from your country" in str(e_rl_main).lower()
        ):
            logger.warning(
                f"{NY}Geo-blocking error during primary fetch_balance ({account_type}): {e_rl_main}{RST}"
            )
            if config.get("use_sandbox") or os.getenv("JULES_TEST_MODE") == "true":
                logger.warning(
                    f"{NY}Sandbox/Test mode: Proceeding with default balance (0).{RST}"
                )
                TradeTracker.current_balance = Decimal("0")  # Set a default
            else:
                logger.error(
                    f"{NR}Geo-blocking error during primary fetch_balance. Cannot confirm connection.{RST}"
                )
                return None
        else:  # Other RateLimitExceeded
            logger.error(
                f"{NR}RateLimitExceeded during primary fetch_balance ({account_type}): {e_rl_main}. Cannot confirm connection.{RST}"
            )
            return None
    except Exception as e_initial_balance:  # Catch other general exceptions for the primary fetch_balance
        logger.error(
            f"{NR}Error on initial balance fetch ({account_type}): {e_initial_balance}. Cannot confirm connection.{RST}"
        )
        if config.get("use_sandbox") or os.getenv("JULES_TEST_MODE") == "true":
            logger.warning(
                f"{NY}Sandbox/Test mode: Proceeding with default balance (0) despite error.{RST}"
            )
            TradeTracker.current_balance = Decimal("0")  # Set a default
        else:
            return None  # This makes initialize_exchange return None only if not in test/sandbox

    return exchange


# --- Data Fetching ---
@retry_api_call()
@handle_exceptions(default_return=None, message="Error fetching current price")
def fetch_current_price(
    exchange: ccxt.Exchange, symbol: str, logger: logging.Logger
) -> Decimal | None:
    """Fetches the current ticker price for a given symbol."""
    logger.debug(f"Fetching ticker for {symbol}. Probing market pulse.")
    ticker = exchange.fetch_ticker(symbol)
    logger.debug(f"Raw ticker for {symbol}: {ticker}. Market heartbeat.")

    price = None
    # Prefer 'last' price, then midpoint of bid/ask, then 'ask', then 'bid'
    if ticker.get("last") is not None and Decimal(str(ticker["last"])) > 0:
        price = Decimal(str(ticker["last"]))
        logger.debug(f"Using 'last' price: {price}. Clear echo.")
    elif (
        ticker.get("bid") is not None
        and ticker.get("ask") is not None
        and Decimal(str(ticker["bid"])) > 0
        and Decimal(str(ticker["ask"])) > 0
        and Decimal(str(ticker["ask"])) >= Decimal(str(ticker["bid"]))
    ):
        price = (Decimal(str(ticker["bid"])) + Decimal(str(ticker["ask"]))) / 2
        logger.debug(f"Using bid/ask midpoint: {price}. Equilibrium.")
    elif ticker.get("ask") is not None and Decimal(str(ticker["ask"])) > 0:
        price = Decimal(str(ticker["ask"]))
        logger.warning(f"{NY}Using 'ask' price: {price}. Seller's decree.{RST}")
    elif ticker.get("bid") is not None and Decimal(str(ticker["bid"])) > 0:
        price = Decimal(str(ticker["bid"]))
        logger.warning(f"{NY}Using 'bid' price: {price}. Buyer's plea.{RST}")

    if price is not None and price > 0:
        return price
    error_msg = f"Failed to get valid price from ticker. Ticker: {ticker}. Scrying mirror clouded."
    raise ccxt.ExchangeError(error_msg)


@retry_api_call()
@handle_exceptions(default_return=pd.DataFrame(), message="Error fetching OHLCV data")
def fetch_ohlcv_data(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str,
    limit: int = 250,
    logger: logging.Logger | None = None,
) -> pd.DataFrame:
    """Fetches historical OHLCV data and returns it as a pandas DataFrame."""
    logger = logger or slg(__name__)
    if not exchange.has["fetchOHLCV"]:
        logger.error(
            f"{NR}Exchange {exchange.id} does not support fetchOHLCV. No historical records!{RST}"
        )
        return pd.DataFrame()

    logger.debug(
        f"Fetching klines for {symbol}, {timeframe}, limit={limit}. Unfurling time scrolls."
    )
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    if not ohlcv or not isinstance(ohlcv, list):
        raise ccxt.ExchangeError(
            f"fetch_ohlcv returned empty/invalid data for {symbol}."
        )

    df = pd.DataFrame(
        ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    df["timestamp"] = pd.to_datetime(
        df["timestamp"], unit="ms", errors="coerce", utc=True
    )
    df.dropna(
        subset=["timestamp"], inplace=True
    )  # Drop rows where timestamp conversion failed
    df.set_index("timestamp", inplace=True)

    # Convert numeric columns, coercing errors to NaN
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    original_rows = len(df)
    df.dropna(
        subset=["open", "high", "low", "close"], inplace=True
    )  # Drop rows with NaN in critical price columns
    df = df[df["volume"] > 0]  # Filter out rows with zero or negative volume

    dropped_rows = original_rows - len(df)
    if dropped_rows > 0:
        logger.debug(
            f"Dropped {dropped_rows} rows with NaN/invalid price/volume for {symbol}. Cleansing dataset."
        )

    if df.empty:
        raise ccxt.ExchangeError(
            f"Kline data for {symbol} {timeframe} empty after cleaning. Cleansed tapestry bare."
        )

    df.sort_index(inplace=True)  # Ensure chronological order

    logger.info(
        f"{NB}Successfully fetched {len(df)} klines for {symbol} {timeframe}. Market history revealed!{RST}"
    )
    return df


@retry_api_call()
@handle_exceptions(default_return=None, message="Error fetching order book")
def fetch_order_book(
    exchange: ccxt.Exchange, symbol: str, limit: int, logger: logging.Logger
) -> dict[str, Any] | None:
    """Fetches the order book for a given symbol."""
    if not exchange.has["fetchOrderBook"]:
        logger.error(
            f"{NR}Exchange {exchange.id} does not support fetchOrderBook. No glimpse into desires!{RST}"
        )
        return None

    logger.debug(
        f"Fetching order book for {symbol}, limit={limit}. Listening to market whispers."
    )
    orderbook = exchange.fetch_order_book(symbol, limit=limit)

    if not orderbook:
        raise ccxt.ExchangeError(
            f"fetch_order_book returned None/empty for {symbol}. Whispers silent."
        )

    if not isinstance(orderbook, dict):
        error_msg = f"Invalid orderbook type for {symbol}. Expected dict, got {type(orderbook).__name__}. Message garbled."
        raise ccxt.ExchangeError(error_msg)

    if "bids" not in orderbook or "asks" not in orderbook:
        error_msg = f"Invalid orderbook structure for {symbol}: missing 'bids' or 'asks'. Keys: {list(orderbook.keys())}. Intentions unclear."
        raise ccxt.ExchangeError(error_msg)

    if not isinstance(orderbook["bids"], list) or not isinstance(
        orderbook["asks"], list
    ):
        error_msg = f"Invalid orderbook structure for {symbol}: 'bids' or 'asks' not lists. bids: {type(orderbook['bids']).__name__}, asks: {type(orderbook['asks']).__name__}. Desires broken."
        raise ccxt.ExchangeError(error_msg)

    logger.debug(
        f"Fetched orderbook for {symbol} with {len(orderbook['bids'])} bids, {len(orderbook['asks'])} asks. Intentions revealed!{RST}"
    )
    return orderbook


# --- Contract Info and Leverage ---
@handle_exceptions(default_return=None, message="Error fetching contract info")
def get_market_info(
    symbol: str, exchange: ccxt.Exchange, logger: logging.Logger
) -> dict[str, Any] | None:
    """Fetches and returns market info for a symbol, handling potential errors and reloading."""
    if not exchange.markets or symbol not in exchange.markets:
        logger.info(
            f"{NB}Market info for {symbol} not loaded or symbol not found, reloading markets... Unfurling the market scrolls anew.{RST}"
        )
        exchange.load_markets(reload=True)

    if symbol not in exchange.markets:
        logger.error(
            f"{NR}Market {symbol} still not found after reloading. The symbol rune is unknown in this realm!{RST}"
        )
        # Provide suggestions for common Bybit symbol formats if it's a Bybit exchange
        if "/USDT" in symbol:
            base, quote = symbol.split("/USDT", 1)
            usdt_pair = f"{base}/USDT:USDT"
            perp_pair = f"{base}-PERP"
            matches = [
                m
                for m in exchange.markets
                if m.startswith(base) and ("PERP" in m or ":USDT" in m or "USD" in m)
            ]
            if usdt_pair in exchange.markets:
                logger.warning(
                    f"{NY}Did you mean '{usdt_pair}'? A common variant.{RST}"
                )
            elif perp_pair in exchange.markets:
                logger.warning(
                    f"{NY}Did you mean '{perp_pair}'? Another possible form.{RST}"
                )
            elif matches:
                logger.warning(
                    f"{NY}Possible matches found: {matches[:5]}. Perhaps one of these is the true rune?{RST}"
                )
        raise ccxt.BadSymbol(f"Market {symbol} not found after reloading.")

    market_info = exchange.market(symbol)

    if market_info:
        # Add 'is_contract' and 'contractSizeDecimal' for easier access
        market_type = market_info.get("type", "unknown")
        is_contract = market_info.get("contract", False) or market_type in [
            "swap",
            "future",
        ]
        market_info["is_contract"] = is_contract

        contract_type = ""
        if is_contract:
            if market_info.get("linear"):
                contract_type = "Linear"
            elif market_info.get("inverse"):
                contract_type = "Inverse"
            else:
                contract_type = "Unknown Contract"

            contract_size = market_info.get("contractSize")
            if contract_size is None:
                # Try to get from info dict if direct key is missing (common in Bybit V5)
                contract_size = market_info.get("info", {}).get("contractSize")

            if contract_size is not None:
                try:
                    contract_size_dec = Decimal(str(contract_size))
                    if contract_size_dec > 0:
                        market_info["contractSizeDecimal"] = contract_size_dec
                    else:
                        logger.critical(
                            f"{NR}get_market_info: CRITICAL - contractSize for {symbol} is non-positive ('{contract_size}'). Market may be untradeable.{RST}"
                        )
                except InvalidOperation:
                    logger.critical(
                        f"{NR}get_market_info: CRITICAL - contractSize for {symbol} is invalid ('{contract_size}'). Cannot convert to Decimal. Market may be untradeable.{RST}"
                    )
            else:
                logger.critical(
                    f"{NR}get_market_info: CRITICAL - contractSize is MISSING for contract market {symbol}. Market is likely untradeable.{RST}"
                )
        else:
            market_info["contractSizeDecimal"] = Decimal(
                "1"
            )  # For spot, 1 unit of base currency

        logger.debug(
            f"Market Info for {symbol}: ID={market_info.get('id')}, Base={market_info.get('base')}, Quote={market_info.get('quote')}, "
            f"Type={market_type}, IsContract={is_contract}, ContractType={contract_type}, "
            f"ContractSizeDecimal={market_info.get('contractSizeDecimal', 'N/A')}, "
            f"Precision(Price/Amount): {market_info.get('precision', {}).get('price')}/{market_info.get('precision', {}).get('amount')}, "
            f"Limits(Amount Min/Max): {market_info.get('limits', {}).get('amount', {}).get('min')}/{market_info.get('limits', {}).get('amount', {}).get('max')}, "
            f"Limits(Cost Min/Max): {market_info.get('limits', {}).get('cost', {}).get('min')}/{market_info.get('limits', {}).get('cost', {}).get('max')}. "
            f"The market's essence revealed.{RST}"
        )
        return market_info
    raise ccxt.ExchangeError(
        f"Market dictionary unexpectedly not found for validated symbol {symbol}. A void in the market's records!"
    )


@handle_exceptions(default_return=False, message="Error setting leverage")
def set_leverage(
    exchange: ccxt.Exchange,
    symbol: str,
    leverage: int,
    market_info: dict[str, Any],
    logger: logging.Logger,
) -> bool:
    """Sets the leverage for a given symbol, handling Bybit's specific requirements."""
    retmsg_prefix = '"retmsg":"'  # For parsing Bybit error messages

    is_contract = market_info.get("is_contract", False)
    if not is_contract:
        logger.info(
            f"{NB}Leverage setting skipped for {symbol} (Not a contract market). Leverage only applies to amplified contracts.{RST}"
        )
        return True

    if not isinstance(leverage, int) or leverage <= 0:
        logger.error(
            f"{NR}Leverage setting skipped for {symbol}: Invalid leverage value ({leverage}). Must be a positive integer. The amplification rune is malformed!{RST}"
        )
        return False

    # Bybit specific logic for category (linear/inverse)
    if exchange.id == "bybit":
        is_linear = isinstance(market_info.get("linear"), bool)
        is_inverse = isinstance(market_info.get("inverse"), bool)

        if not (is_linear or is_inverse):  # If flags are missing or invalid
            logger.warning(
                f"{NY}set_leverage: market_info for Bybit symbol {symbol} is missing or has invalid 'linear'/'inverse' flags. Linear valid: {is_linear} (value: {market_info.get('linear')}), Inverse valid: {is_inverse} (value: {market_info.get('inverse')}). Attempting to refresh market_info...{RST}"
            )
            refreshed_market = get_market_info(symbol, exchange, logger)
            if not refreshed_market:
                logger.error(
                    f"{NR}set_leverage: Critical - Failed to refresh market_info for {symbol}. Cannot safely determine category for leverage setting.{RST}"
                )
                return False

            is_linear = isinstance(refreshed_market.get("linear"), bool)
            is_inverse = isinstance(refreshed_market.get("inverse"), bool)
            if not (is_linear or is_inverse):
                logger.error(
                    f"{NR}set_leverage: Critical - Refreshed market_info still lacks definitive linear/inverse flags for {symbol}. Linear valid: {is_linear} (value: {refreshed_market.get('linear')}), Inverse valid: {is_inverse} (value: {refreshed_market.get('inverse')}). Cannot safely set leverage.{RST}"
                )
                return False
            market_info = refreshed_market  # Use the refreshed info
            logger.info(
                f"{NB}set_leverage: Successfully refreshed market_info for {symbol} with definitive linear/inverse flags.{RST}"
            )
        else:
            logger.debug(
                f"set_leverage: market_info for {symbol} has valid linear/inverse flags. Linear: {market_info.get('linear')}, Inverse: {market_info.get('inverse')}"
            )

    if not exchange.has.get("setLeverage") and not exchange.has.get("setMarginMode"):
        logger.error(
            f"{NR}Exchange {exchange.id} does not support setLeverage or setMarginMode via CCXT. Cannot set leverage. The exchange offers no amplification!{RST}"
        )
        return False

    logger.info(
        f"{NB}Attempting to set leverage for {symbol} to {leverage}x... Amplifying market power!{RST}"
    )
    params = {}
    if exchange.id == "bybit":
        leverage_str = str(leverage)
        category = (
            "linear" if market_info.get("linear") else "inverse"
        )  # Determine category for Bybit V5
        params = {
            "buyLeverage": leverage_str,
            "sellLeverage": leverage_str,
            "category": category,
        }
        logger.debug(
            f"Using Bybit V5 params for set_leverage: {params}. Specific incantations for Bybit.{RST}"
        )

    success = False
    try:
        response = exchange.set_leverage(
            leverage=leverage, symbol=symbol, params=params
        )
        logger.debug(
            f"Set leverage raw response for {symbol}: {response}. The echo of the amplification spell.{RST}"
        )
        success = True
        logger.info(
            f"{NG}Leverage for {symbol} successfully requested/reported as set to {leverage}x by exchange (or was already set).{RST}"
        )
    except ccxt.BadRequest as err:
        err_msg_lower = str(err).lower()
        err_msg_clean = err_msg_lower.replace(
            " ", ""
        )  # Remove spaces for easier matching
        # Bybit specific error codes/messages for "leverage not modified"
        err_code_110043 = '"retcode":110043' in err_msg_clean
        err_msg_not_modified = '"retmsg":"leveragenotmodified"' in err_msg_clean
        err_msg_contains_not_modified = (
            "leveragenotmodified" in err_msg_clean
            or "leverage not modified" in err_msg_lower
        )

        if exchange.id == "bybit" and (
            err_code_110043 or err_msg_not_modified or err_msg_contains_not_modified
        ):
            # Extract the actual message if possible
            msg_extracted = "Leverage not modified"
            try:
                if retmsg_prefix in err_msg_lower:
                    msg_extracted = err_msg_lower.split(retmsg_prefix)[1].split('"')[0]
            except IndexError:
                pass  # Fallback to default message
            logger.info(
                f"{NY}Leverage for {symbol} is already set to {leverage}x (Exchange confirmed: '{msg_extracted}'). No modification needed. This is treated as success.{RST}"
            )
            success = True
        else:
            logger.warning(
                f"{NY}Unhandled ccxt.BadRequest in set_leverage for {symbol}: {err}. Leverage setting failed. This might be retryable or indicate an issue.{RST}"
            )
            raise  # Re-raise if it's not the "not modified" error
    except Exception as err:
        logger.error(
            f"{NR}Error setting leverage for {symbol}: {err}.{RST}", exc_info=True
        )
        raise  # Re-raise other exceptions

    if success:
        # Attempt to confirm leverage from position data
        try:
            logger.debug(
                f"Fetching position data for {symbol} to confirm active leverage after setLeverage call..."
            )
            position_info = fetch_position_info(exchange, symbol, market_info, logger)
            active_leverage_str = None
            if position_info:
                # Try to get leverage from top level or 'info' dict for Bybit V5
                leverage_raw = position_info.get("leverage")
                if leverage_raw is None and isinstance(position_info.get("info"), dict):
                    leverage_raw = position_info["info"].get("leverage")

                if leverage_raw is not None and str(leverage_raw).strip():
                    active_leverage_str = str(leverage_raw)
                else:
                    logger.debug(
                        f"set_leverage: Leverage field in position_data for {symbol} is None or empty string. Raw value: '{leverage_raw}'"
                    )

            if active_leverage_str:
                try:
                    active_leverage_dec = Decimal(active_leverage_str)
                    logger.info(
                        f"{NG}Confirmed active leverage for {symbol} from position data: {active_leverage_dec}x. (Requested: {leverage}x){RST}"
                    )
                    if active_leverage_dec != Decimal(str(leverage)):
                        logger.warning(
                            f"{NY}Active leverage {active_leverage_dec}x for {symbol} differs from requested {leverage}x, despite exchange confirmation or 'not modified' report. The amplification might be different than intended.{RST}"
                        )
                except InvalidOperation:
                    logger.warning(
                        f"{NY}Could not convert active leverage '{active_leverage_str}' from position data to Decimal for {symbol}. Unable to numerically confirm leverage.{RST}"
                    )
            else:
                logger.warning(
                    f"{NY}Could not confirm active leverage for {symbol} from position data (leverage field missing, None, or empty string). Position data was {'present but lacked a valid leverage field' if position_info else 'not available/empty'}. The exact current amplification is unknown.{RST}"
                )
        except Exception as err:
            logger.warning(
                f"{NY}Failed to fetch or parse position data to confirm leverage for {symbol} after set_leverage call: {err}.{RST}"
            )
    return success


@handle_exceptions(default_return=None, message="Error fetching position info")
def fetch_position_info(
    exchange: ccxt.Exchange,
    symbol: str,
    market_info: dict[str, Any],
    logger: logging.Logger,
) -> dict[str, Any] | None:
    """Fetches current position information for a symbol."""
    if not exchange.has["fetchPosition"] and not exchange.has["fetchPositions"]:
        logger.error(
            f"{NR}Exchange {exchange.id} does not support fetching positions. Cannot manage positions!{RST}"
        )
        return None

    try:
        # Bybit V5 requires category for fetchPositions
        params = {}
        if exchange.id == "bybit":
            category = "linear" if market_info.get("linear") else "inverse"
            params = {
                "category": category,
                "symbol": market_info.get("id"),
            }  # Use Bybit's internal symbol ID

        positions = exchange.fetch_positions(symbols=[symbol], params=params)

        if not positions:
            logger.debug(f"No open position found for {symbol}.")
            return None

        # Filter for the specific symbol and ensure it's an open position
        for pos in positions:
            if pos.get("symbol") == symbol and pos.get("contracts", 0) != 0:
                # Standardize some fields for easier access
                pos["contractsDecimal"] = Decimal(str(pos.get("contracts", "0")))
                pos["entryPriceDecimal"] = Decimal(str(pos.get("entryPrice", "0")))
                pos["unrealisedPnlDecimal"] = Decimal(
                    str(pos.get("unrealizedPnl", "0"))
                )
                pos["liquidationPriceDecimal"] = Decimal(
                    str(pos.get("liquidationPrice", "0"))
                )
                pos["stopLossDecimal"] = (
                    Decimal(str(pos.get("stopLoss", "0")))
                    if pos.get("stopLoss") is not None
                    else None
                )
                pos["takeProfitDecimal"] = (
                    Decimal(str(pos.get("takeProfit", "0")))
                    if pos.get("takeProfit") is not None
                    else None
                )
                pos["trailingStopDecimal"] = (
                    Decimal(str(pos.get("trailingStop", "0")))
                    if pos.get("trailingStop") is not None
                    else None
                )
                pos["positionSide"] = pos.get("side")  # 'long' or 'short'

                # For Bybit V5, trailingStop and tslActivationPrice are in 'info'
                if exchange.id == "bybit" and isinstance(pos.get("info"), dict):
                    info = pos["info"]
                    pos["trailingStopDecimal"] = (
                        Decimal(str(info.get("trailingStop", "0")))
                        if info.get("trailingStop") is not None
                        else pos["trailingStopDecimal"]
                    )
                    pos["tslActivationPriceDecimal"] = (
                        Decimal(str(info.get("tpslTriggerPrice", "0")))
                        if info.get("tpslTriggerPrice") is not None
                        else None
                    )  # Bybit V5 uses tpslTriggerPrice for TSL activation

                logger.debug(f"Found open position for {symbol}: {pos}")
                return pos

        logger.debug(f"No open position found for {symbol} after filtering.")
        return None

    except ccxt.NetworkError as e:
        logger.warning(
            f"{NY}Network error fetching positions for {symbol}: {e}. Retrying...{RST}"
        )
        raise  # Re-raise to trigger retry_api_call decorator
    except Exception as e:
        logger.error(
            f"{NR}Error fetching positions for {symbol}: {e}.{RST}", exc_info=True
        )
        return None


@handle_exceptions(
    default_return=False, message="Error setting/managing trade protections"
)
def set_trade_stop_loss_take_profit(
    exchange: ccxt.Exchange,
    symbol: str,
    market_info: dict[str, Any],
    position_info: dict[str, Any],
    config: dict[str, Any],
    logger: logging.Logger,
    fixed_stop_loss_price: Decimal | None = None,
    take_profit_price_target: Decimal | None = None,
    attempt_tsl: bool = True,
) -> bool:
    """Manages stop loss, take profit, and trailing stop loss protections for a position."""
    result_key = "result"
    tp_size_key = "tpSize"
    last_price_key = "LastPrice"
    na_cfg_raw = "N/A_cfg_raw"  # Placeholder for raw config values not found

    trade_record = TradeTracker.open_trades.get(symbol)
    if not trade_record:
        logger.error(
            f"{NR}set_trade_stop_loss_take_profit: No open trade record found for {symbol}. Cannot set protections.{RST}"
        )
        return False

    # Get position size from position_info, fallback to trade_record if needed
    position_size_raw = position_info.get("contractsDecimal")
    position_size_dec = None
    if position_size_raw is not None:
        try:
            position_size_dec = Decimal(str(position_size_raw))
            if position_size_dec.is_zero():
                logger.warning(
                    f"{NY}set_trade_stop_loss_take_profit: Position size for {symbol} is zero ({position_size_raw}). Cannot set protections if position is effectively closed.{RST}"
                )
                return False
        except InvalidOperation:
            logger.error(
                f"{NR}set_trade_stop_loss_take_profit: Invalid position size '{position_size_raw}' in position_info for {symbol}. Cannot set protections.{RST}"
            )
            return False
    else:
        position_size_dec = trade_record.size  # Fallback to size from trade record

    if position_size_dec is None or position_size_dec.is_zero():
        logger.error(
            f"{NR}set_trade_stop_loss_take_profit: Valid non-zero position size could not be determined for {symbol}. Cannot set protections.{RST}"
        )
        return False

    qty_str = str(position_size_dec)  # Quantity as string for API call

    use_sandbox = config.get("use_sandbox", True)
    base_url = (
        "https://api-testnet.bybit.com" if use_sandbox else "https://api.bybit.com"
    )
    path = "/v5/position/trading-stop"

    # Bybit V5 positionIdx is usually 0 for one-way mode, 1 or 2 for hedge mode
    position_idx_raw = position_info.get("info", {}).get("positionIdx")
    position_idx = 0  # Default for one-way mode
    if position_idx_raw is None:
        logger.debug(
            f"set_trade_stop_loss_take_profit: positionIdx not found in position_info for {symbol}. Defaulting to 0."
        )
    else:
        try:
            position_idx = int(position_idx_raw)
            logger.debug(
                f"set_trade_stop_loss_take_profit: Successfully converted positionIdx '{position_idx_raw}' to integer {position_idx} for {symbol}."
            )
        except ValueError:
            logger.error(
                f"{NR}set_trade_stop_loss_take_profit: Invalid positionIdx '{position_idx_raw}' for symbol {symbol}. Cannot set protections.{RST}"
            )
            return False

    price_precision = IndicatorCalculator.gpp(market_info, logger)
    min_trade_size = IndicatorCalculator.gmts(market_info, logger)  # qtyStep

    tp_price = None
    if take_profit_price_target and take_profit_price_target > 0:
        tp_price = take_profit_price_target.quantize(
            min_trade_size if min_trade_size > 0 else Decimal(f"1e-{price_precision}"),
            rounding=ROUND_HALF_EVEN,
        )

    sl_price = None
    if fixed_stop_loss_price and fixed_stop_loss_price > 0:
        sl_price = fixed_stop_loss_price.quantize(
            min_trade_size if min_trade_size > 0 else Decimal(f"1e-{price_precision}"),
            rounding=ROUND_HALF_EVEN,
        )

    tsl_distance = None
    tsl_activation_price = None
    attempt_tsl_calc = False  # Flag to indicate if TSL calculation should proceed

    tsl_rate_cfg_raw = na_cfg_raw
    tsl_activation_pct_cfg_raw = na_cfg_raw
    tsl_rate_dec = Decimal(0)
    tsl_activation_pct_dec = Decimal(0)

    if attempt_tsl and config.get("enable_trailing_stop", False):
        tsl_rate_cfg = config.get(
            "trailing_stop_callback_rate", DIP["trailing_stop_callback_rate"]
        )
        tsl_activation_pct_cfg = config.get(
            "trailing_stop_activation_percentage",
            DIP["trailing_stop_activation_percentage"],
        )

        tsl_rate_cfg_raw = str(tsl_rate_cfg)
        tsl_activation_pct_cfg_raw = str(tsl_activation_pct_cfg)

        try:
            tsl_rate_dec = Decimal(tsl_rate_cfg_raw)
            tsl_activation_pct_dec = Decimal(tsl_activation_pct_cfg_raw)
            logger.debug(
                f"set_trade_stop_loss_take_profit: TSL Configs for {symbol} - RateRaw='{tsl_rate_cfg_raw}', ActivRaw='{tsl_activation_pct_cfg_raw}' -> RateDec={tsl_rate_dec}, ActivDec={tsl_activation_pct_dec}"
            )

            if not (
                isinstance(tsl_rate_dec, Decimal)
                and isinstance(tsl_activation_pct_dec, Decimal)
                and tsl_rate_dec > 0
                and tsl_activation_pct_dec >= 0
            ):
                logger.error(
                    f"{NR}set_trade_stop_loss_take_profit: Invalid TSL config types/values for {symbol}. RateRaw='{tsl_rate_cfg_raw}', ActivRaw='{tsl_activation_pct_cfg_raw}' -> RateDec={tsl_rate_dec}, ActivDec={tsl_activation_pct_dec}.{RST}"
                )
            else:
                attempt_tsl_calc = True  # Proceed with TSL calculation
        except InvalidOperation:
            logger.error(
                f"{NR}set_trade_stop_loss_take_profit: Error during TSL param calculation for {symbol}: InvalidOperation. The TSL parameters are malformed!{RST}"
            )
            attempt_tsl_calc = False  # Do not attempt TSL calculation

        if attempt_tsl_calc:
            # Use position_info's entryPrice if available, otherwise fallback to trade_record
            entry_price_for_tsl = position_info.get(
                "entryPriceDecimal", trade_record.entry_price
            )
            position_side = position_info.get("positionSide", trade_record.side)
            position_side_lower = str(position_side).lower() if position_side else None

            if (
                not entry_price_for_tsl
                or entry_price_for_tsl <= 0
                or not position_side_lower
            ):
                logger.error(
                    f"{NR}set_trade_stop_loss_take_profit: Missing entry price/side for TSL calc. Entry: {entry_price_for_tsl}, Side: {position_side_lower}.{RST}"
                )
                attempt_tsl_calc = False
            else:
                # Calculate TSL activation price and distance
                activation_price_raw = entry_price_for_tsl * (
                    Decimal("1")
                    + (
                        tsl_activation_pct_dec
                        if position_side_lower == "long"
                        else -tsl_activation_pct_dec
                    )
                )
                activation_price_quantized = activation_price_raw.quantize(
                    min_trade_size
                    if min_trade_size > 0
                    else Decimal(f"1e-{price_precision}"),
                    rounding=ROUND_DOWN,
                )

                tsl_distance_raw = entry_price_for_tsl * tsl_rate_dec
                tsl_distance_quantized = tsl_distance_raw.quantize(
                    min_trade_size
                    if min_trade_size > 0
                    else Decimal(f"1e-{price_precision}"),
                    rounding=ROUND_DOWN,
                )

                # Ensure TSL distance is not too small (e.g., less than one tick size)
                if tsl_distance_quantized <= (
                    min_trade_size
                    if min_trade_size > 0
                    else Decimal(f"1e-{price_precision}")
                ):
                    tsl_distance = (
                        min_trade_size
                        if min_trade_size > 0
                        else Decimal(f"1e-{price_precision}")
                    )
                    logger.warning(
                        f"{NY}set_trade_stop_loss_take_profit: TSL distance from rate ({tsl_rate_dec}) resulted in {tsl_distance_raw}, quantized to {tsl_distance_quantized}, which is too small. Adjusted to {tsl_distance}.{RST}"
                    )
                else:
                    tsl_distance = tsl_distance_quantized

                tsl_activation_price = activation_price_quantized

                if tsl_distance > 0 and tsl_activation_price > 0:
                    attempt_tsl_calc = True  # Final confirmation to proceed
                else:
                    logger.error(
                        f"{NR}set_trade_stop_loss_take_profit: Final TSL distance ({tsl_distance}) or activation price ({tsl_activation_price}) is invalid.{RST}"
                    )
                    attempt_tsl_calc = False  # Do not attempt TSL calculation

    has_tp = isinstance(tp_price, Decimal) and tp_price > 0
    has_sl = isinstance(sl_price, Decimal) and sl_price > 0

    # Construct payload for Bybit V5 trading-stop endpoint
    payload = {
        "category": "linear"
        if market_info.get("linear", True)
        else "inverse",  # Category (linear/inverse)
        "symbol": market_info.get("id"),  # Bybit's internal symbol ID
        "positionIdx": position_idx,  # Position Index
        "slTriggerBy": config.get("sl_trigger_by", last_price_key),  # SL Trigger By
        "tpTriggerBy": config.get("tp_trigger_by", last_price_key),  # TP Trigger By
        "tpslMode": "Partial",  # Always use Partial mode for flexibility
    }

    tsl_applied_in_payload = False
    if attempt_tsl_calc:
        # Calculate the actual SL price that the TSL implies at activation
        sl_for_tsl = None
        sl_calc_base = None
        if position_side_lower == "long":
            sl_calc_base = tsl_activation_price - tsl_distance
            sl_for_tsl = sl_calc_base.quantize(
                min_trade_size
                if min_trade_size > 0
                else Decimal(f"1e-{price_precision}"),
                rounding=ROUND_DOWN,
            )
            # Ensure SL is strictly below activation price for long
            if sl_for_tsl >= tsl_activation_price:
                sl_for_tsl = tsl_activation_price - (
                    min_trade_size
                    if min_trade_size > 0
                    else Decimal(f"1e-{price_precision}")
                )
        elif position_side_lower == "short":
            sl_calc_base = tsl_activation_price + tsl_distance
            sl_for_tsl = sl_calc_base.quantize(
                min_trade_size
                if min_trade_size > 0
                else Decimal(f"1e-{price_precision}"),
                rounding=ROUND_UP,
            )
            # Ensure SL is strictly above activation price for short
            if sl_for_tsl <= tsl_activation_price:
                sl_for_tsl = tsl_activation_price + (
                    min_trade_size
                    if min_trade_size > 0
                    else Decimal(f"1e-{price_precision}")
                )

        if sl_for_tsl and sl_for_tsl > 0:
            payload["stopLoss"] = str(sl_for_tsl)
            payload["slSize"] = qty_str  # Apply SL to full position size
            payload["trailingStop"] = str(tsl_distance)
            payload["tpslTriggerPrice"] = str(tsl_activation_price)  # Bybit V5 specific
            tsl_applied_in_payload = True
            logger.info(
                f"{NB}set_trade_stop_loss_take_profit: Planning to set TSL (Partial mode) for {symbol}. Initial SL: {sl_for_tsl}, Dist: {tsl_distance}, Act: {tsl_activation_price}.{RST}"
            )
        else:
            logger.error(
                f"{NR}set_trade_stop_loss_take_profit: Final TSL distance ({tsl_distance}) or activation price ({tsl_activation_price}) is invalid.{RST}"
            )
            # If TSL calculation failed, do not apply TSL, proceed to fixed SL/TP logic
            attempt_tsl_calc = False

    if not tsl_applied_in_payload:  # If TSL is not being applied, manage fixed SL
        if has_sl:
            payload["stopLoss"] = str(sl_price)
            payload["slSize"] = qty_str  # Apply SL to full position size
            payload["trailingStop"] = ""  # Clear TSL if fixed SL is set
            payload.pop("tpslTriggerPrice", None)  # Clear TSL activation price
            logger.info(
                f"{NB}set_trade_stop_loss_take_profit: Planning to set Fixed SL (Partial mode) for {symbol} to {sl_price}. TSL not applied.{RST}"
            )
        else:  # No fixed SL, no TSL -> clear all SL protections
            payload["stopLoss"] = ""
            payload["slSize"] = ""
            payload["trailingStop"] = ""
            payload.pop("tpslTriggerPrice", None)
            logger.info(
                f"{NB}set_trade_stop_loss_take_profit: Planning to clear SL protections (Partial mode) for {symbol}.{RST}"
            )

    # Always manage TP if a target is provided
    if has_tp:
        payload["takeProfit"] = str(tp_price)
        payload["tpSize"] = qty_str  # Apply TP to full position size
    else:  # Clear TP if no target is provided
        payload["takeProfit"] = ""
        payload["tpSize"] = ""

    # Check if any actual changes are being made to avoid unnecessary API calls
    # This would require fetching current trading stop settings from the exchange first
    # For simplicity, we'll assume the API call is always needed if any TP/SL/TSL is set or cleared.

    logger.debug(
        f"set_trade_stop_loss_take_profit: Preparing to call Bybit API. URL: {base_url}{path}, Payload: {json.dumps(payload, default=str)}"
    )
    logger.info(
        f"{NB}set_trade_stop_loss_take_profit: Attempting to set protections for {symbol} via direct API call. Params Summary: TP={payload.get('takeProfit')}, SL={payload.get('stopLoss')}, TSL={payload.get('trailingStop')}{RST}"
    )
    logger.info(
        f"{NB}set_trade_stop_loss_take_profit: Sending payload to Bybit API /v5/position/trading-stop: {json.dumps(payload, default=str)}{RST}"
    )

    api_response = _bybit_v5_request(
        method="POST",
        path=path,
        params=payload,
        api_key=AK,
        api_secret=AS,
        base_url=base_url,
        logger=logger,
    )

    if api_response is None:
        logger.error(
            f"{NR}set_trade_stop_loss_take_profit: _bybit_v5_request returned None for {symbol}. Protection setup failed critically before/during request.{RST}"
        )
        return False

    logger.info(
        f"{NB}set_trade_stop_loss_take_profit: Raw response from Bybit {path} for {symbol}: {json.dumps(api_response, default=str)}{RST}"
    )

    if api_response.get("retCode") == 0:
        logger.info(
            f"{NG}set_trade_stop_loss_take_profit: Successfully set protections for {symbol} via direct API. Msg: {api_response.get('retMsg')}{RST}"
        )
        logger.debug(
            f"set_trade_stop_loss_take_profit: Successful protection set for {symbol}. Original params sent: {json.dumps(payload, default=str)}"
        )

        # Update trade record with the new protection settings
        if tsl_applied_in_payload and tsl_distance and tsl_activation_price:
            trade_record.trailing_stop_active = True
            trade_record.trailing_stop_distance = tsl_distance
            trade_record.tsl_activation_price = tsl_activation_price
            trade_record.stop_loss_price = None  # TSL overrides fixed SL
        else:
            trade_record.trailing_stop_active = False
            trade_record.trailing_stop_distance = None
            trade_record.tsl_activation_price = None
            if payload.get("stopLoss") and payload["stopLoss"] != "":
                trade_record.stop_loss_price = Decimal(payload["stopLoss"])
            else:
                trade_record.stop_loss_price = None

        if payload.get("takeProfit") and payload["takeProfit"] != "":
            trade_record.take_profit_price = Decimal(payload["takeProfit"])
        else:
            trade_record.take_profit_price = None

        TradeTracker._save_trades()
        logger.info(
            f"{NG}set_trade_stop_loss_take_profit: TradeRecord for {symbol} updated. SL: {trade_record.stop_loss_price}, TP: {trade_record.take_profit_price}, TSL Active: {trade_record.trailing_stop_active}, TSL Dist: {trade_record.trailing_stop_distance}, TSL Act: {trade_record.tsl_activation_price}.{RST}"
        )
        return True
    error_msg = api_response.get("retMsg", "Unknown error")
    error_code = api_response.get("retCode", -1)
    logger.debug(
        f"set_trade_stop_loss_take_profit: Failed protection set for {symbol}. Original params sent: {json.dumps(payload, default=str)}"
    )

    if error_code == 110061:  # Bybit specific error for SL/TP order limit exceeded
        logger.error(
            f"{NR}set_trade_stop_loss_take_profit: Failed to set protections for {symbol} due to SL/TP order limit exceeded (Error 110061). Msg: {error_msg}. Attempting to cancel existing StopOrders for the symbol as a corrective measure.{RST}"
        )
        try:
            # Attempt to cancel all StopOrders for the symbol
            cancel_params = {
                "category": payload["category"],
                "symbol": payload["symbol"],
                "orderFilter": "StopOrder",
            }
            cancel_path = (
                "/v5/order/cancel-all"  # Corrected path for cancelling all orders
            )
            logger.info(
                f"{NB}set_trade_stop_loss_take_profit: Attempting to cancel all StopOrders for {symbol} with params: {json.dumps(cancel_params, default=str)} via {cancel_path}{RST}"
            )

            cancel_response = _bybit_v5_request(
                method="POST",
                path=cancel_path,
                params=cancel_params,
                api_key=AK,
                api_secret=AS,
                base_url=base_url,
                logger=logger,
            )

            if cancel_response and cancel_response.get("retCode") == 0:
                cancelled_count = 0
                if isinstance(cancel_response.get(result_key, {}).get("list"), list):
                    cancelled_count = len(cancel_response[result_key]["list"])
                logger.info(
                    f"{NG}set_trade_stop_loss_take_profit: Successfully sent request to cancel all StopOrders for {symbol}. Orders cancelled/affected: {cancelled_count}. This is a corrective action for the next cycle. Msg: {cancel_response.get('retMsg')}{RST}"
                )
            else:
                cancel_msg = (
                    cancel_response.get("retMsg", "Unknown cancel error")
                    if cancel_response
                    else "No response from cancel call"
                )
                cancel_code = (
                    cancel_response.get("retCode", -1) if cancel_response else -1
                )
                logger.error(
                    f"{NR}set_trade_stop_loss_take_profit: Failed to cancel all StopOrders for {symbol}. Code: {cancel_code}, Msg: {cancel_msg}. Full Cancel Response: {json.dumps(cancel_response, default=str)}{RST}"
                )
        except Exception as cancel_err:
            logger.error(
                f"{NR}set_trade_stop_loss_take_profit: Exception occurred while attempting to cancel all StopOrders for {symbol}: {cancel_err}{RST}"
            )
        return False  # Return False as protection setting failed
    logger.error(
        f"{NR}set_trade_stop_loss_take_profit: Failed to set protections for {symbol} via direct API. Code: {error_code}, Msg: {error_msg}. Full Response: {json.dumps(api_response, default=str)}{RST}"
    )
    return False


# --- Per-Symbol Bot Logic ---
@dataclass
class PerSymbolBot:
    symbol: str
    exchange: ccxt.Exchange
    config: dict[str, Any]
    logger: logging.Logger
    ws_client: "BybitWebSocket"  # Use string literal for forward reference
    market_info: dict[str, Any] = field(init=False)
    ta_analyzer: IndicatorCalculator = field(init=False)
    exit_signal_manager: "ExitSignalManager" = field(init=False)
    last_signal: str = "HOLD"
    last_signal_time: datetime | None = None
    bybit_symbol_id: str = field(init=False)

    def __post_init__(self):
        self.market_info = get_market_info(self.symbol, self.exchange, self.logger)
        if not self.market_info:
            raise ValueError(
                f"Could not retrieve market info for {self.symbol}. Aborting bot initialization for this symbol."
            )

        self.bybit_symbol_id = self.market_info.get("id")
        if not self.bybit_symbol_id:
            raise ValueError(
                f"Could not retrieve Bybit symbol ID for {self.symbol}. Aborting bot initialization for this symbol."
            )

        self.ta_analyzer = IndicatorCalculator(self.logger, self.config)
        self.ta_analyzer.s = self.symbol  # Set symbol in TA analyzer
        self.ta_analyzer.cfg = self.config  # Pass full config
        self.ta_analyzer.mi = self.market_info  # Pass market info
        self.ta_analyzer.indicator_thresholds = self.config.get(
            "indicator_thresholds", {}
        )  # Pass thresholds

        self.exit_signal_manager = ExitSignalManager(
            self.logger, self.config, self.ta_analyzer, TradeTracker
        )

        # Set leverage once per symbol bot initialization
        if self.market_info.get("is_contract", False):
            leverage_setting = self.config.get("leverage", 1)
            if not set_leverage(
                self.exchange,
                self.symbol,
                leverage_setting,
                self.market_info,
                self.logger,
            ):
                self.logger.error(
                    f"{NR}Failed to set leverage for {self.symbol}. Trading might not proceed as expected.{RST}"
                )
        else:
            self.logger.info(
                f"{NB}Symbol {self.symbol} is not a contract market. Skipping leverage setting.{RST}"
            )

    @handle_exceptions(default_return=False, message="Error executing symbol logic")
    def run_symbol_logic(self) -> bool:
        """Main logic for a single symbol bot."""
        self.logger.info(f"{NB}--- Running logic for {self.symbol} ---{RST}")

        # 1. Fetch OHLCV data
        ohlcv_df = fetch_ohlcv_data(
            self.exchange,
            self.symbol,
            self.config.get("interval", "5m"),
            250,
            self.logger,
        )
        if ohlcv_df.empty:
            self.logger.warning(
                f"{NY}No OHLCV data for {self.symbol}. Skipping signal generation.{RST}"
            )
            return False

        self.ta_analyzer.set_data(ohlcv_df)
        self.ta_analyzer.compute_all()  # Compute all indicators

        # 2. Get current price
        current_price = self.ws_client.get_last_price(self.bybit_symbol_id)
        if current_price is None:
            self.logger.warning(
                f"{NY}WebSocket price not available for {self.symbol}. Falling back to REST.{RST}"
            )
            current_price = fetch_current_price(self.exchange, self.symbol, self.logger)
            if current_price is None:
                self.logger.error(
                    f"{NR}Could not get current price for {self.symbol}. Skipping.{RST}"
                )
                return False

        # Update TradeTracker's market info cache
        TradeTracker.market_info_cache[self.symbol] = self.market_info

        # 3. Manage existing position (if any)
        if self.symbol in TradeTracker.open_trades:
            self.logger.info(f"{NB}Managing open position for {self.symbol}.{RST}")
            # This will also update PnL and check for SL/TP/BE
            if not self._manage_position(current_price):
                self.logger.warning(
                    f"{NY}Position management for {self.symbol} failed or position closed unexpectedly.{RST}"
                )
                # If position management indicates closure, ensure it's removed from open_trades
                if (
                    self.symbol in TradeTracker.open_trades
                    and TradeTracker.open_trades[self.symbol].status != "OPEN"
                ):
                    TradeTracker.open_trades.pop(self.symbol)
                return False  # Stop further logic for this symbol if position is closed/managed
            # If position is still open after management, skip new signal generation
            self.logger.info(
                f"{NB}Position for {self.symbol} is still open. Skipping new signal generation.{RST}"
            )
            return True  # Successfully managed existing position

        # 4. Check for signal cooldown
        cooldown_candles = self.config.get("symbol_signal_cooldown_candles", 0)
        if self.last_signal_time and cooldown_candles > 0:
            last_candle_time = ohlcv_df.index[-1].to_pydatetime().replace(tzinfo=TZ)
            # Calculate the time of the candle when the last signal was generated
            # Assuming interval is in minutes for simplicity, adjust if other timeframes are used
            interval_minutes = int(self.config.get("interval", "5"))
            cooldown_duration = timedelta(minutes=cooldown_candles * interval_minutes)

            if datetime.now(TZ) - self.last_signal_time < cooldown_duration:
                self.logger.info(
                    f"{NB}Signal cooldown active for {self.symbol}. Skipping new signal generation. "
                    f"Last signal at {self.last_signal_time.strftime('%H:%M:%S')}, cooldown ends in "
                    f"{(self.last_signal_time + cooldown_duration - datetime.now(TZ)).total_seconds():.0f}s.{RST}"
                )
                return False

        # 5. Fetch order book data if enabled
        orderbook_data = None
        if self.config.get("indicators", {}).get(
            "orderbook", False
        ) and self.config.get("enable_orderbook_depth_analysis", False):
            orderbook_data = fetch_order_book(
                self.exchange,
                self.symbol,
                self.config.get("orderbook_limit", 25),
                self.logger,
            )
            if orderbook_data is None:
                self.logger.warning(
                    f"{NY}Order book data not available for {self.symbol}. Orderbook indicator will be skipped.{RST}"
                )

        # 6. Generate trade signal
        signal = self.ta_analyzer.generate_trade_signal(current_price, orderbook_data)
        self.last_signal = signal
        self.last_signal_time = datetime.now(TZ)

        # 7. Execute trade if enabled and signal is BUY/SELL
        if self.config.get("enable_trading", False) and signal in ["BUY", "SELL"]:
            self.logger.info(
                f"{NG}Trading enabled and {signal} signal received for {self.symbol}. Initiating trade sequence!{RST}"
            )
            if not self._execute_trade(signal, current_price):
                self.logger.error(
                    f"{NR}Trade execution failed for {self.symbol} on {signal} signal.{RST}"
                )
                return False
        elif not self.config.get("enable_trading", False):
            self.logger.info(
                f"{NY}Trading is disabled. Signal '{signal}' for {self.symbol} will not be executed.{RST}"
            )
        else:
            self.logger.info(
                f"{NB}No trade signal for {self.symbol} (Signal: {signal}). Holding position.{RST}"
            )

        return True

    @handle_exceptions(default_return=False, message="Error executing trade")
    def _execute_trade(self, signal: str, current_price: Decimal) -> bool:
        """Executes a trade based on the signal."""
        if signal not in ["BUY", "SELL"]:
            self.logger.error(
                f"{NR}Invalid signal '{signal}' for trade execution.{RST}"
            )
            return False

        # Check max concurrent positions
        max_concurrent = self.config.get("max_concurrent_positions", 1)
        if len(TradeTracker.open_trades) >= max_concurrent:
            self.logger.warning(
                f"{NY}Max concurrent positions ({max_concurrent}) reached. Cannot open new trade for {self.symbol}.{RST}"
            )
            return False

        # Calculate position size based on risk per trade
        risk_per_trade_pct = Decimal(str(self.config.get("risk_per_trade", "0.01")))
        leverage = Decimal(str(self.config.get("leverage", "1")))

        if TradeTracker.current_balance <= 0:
            self.logger.error(
                f"{NR}Current balance is zero or negative ({TradeTracker.current_balance}). Cannot calculate position size.{RST}"
            )
            return False

        # Calculate TP/SL prices first to determine risk amount
        entry_price_estimate, tp_price, sl_price = (
            self.ta_analyzer.calculate_entry_take_profit_stop_loss(
                entry_price_estimate=current_price, signal=signal
            )
        )

        if sl_price is None:
            self.logger.warning(
                f"{NY}Stop Loss price could not be determined for {self.symbol}. Cannot calculate risk-based position size. Aborting trade.{RST}"
            )
            return False

        # Risk amount in quote currency
        risk_amount_quote = TradeTracker.current_balance * risk_per_trade_pct

        # Price difference between entry and stop loss
        price_diff_to_sl = abs(entry_price_estimate - sl_price)

        if price_diff_to_sl.is_zero():
            self.logger.error(
                f"{NR}Calculated SL price is too close to entry price ({entry_price_estimate} vs {sl_price}). Risk is zero, cannot determine position size. Aborting trade.{RST}"
            )
            return False

        # Position size in base currency (contracts)
        # For linear contracts, size is in base currency, value is size * price
        # risk_amount_quote = (entry_price - sl_price) * size * contract_size
        # size = risk_amount_quote / ((entry_price - sl_price) * contract_size)

        contract_size = self.market_info.get("contractSizeDecimal", Decimal("1"))
        if not isinstance(contract_size, Decimal) or contract_size <= 0:
            self.logger.error(
                f"{NR}Invalid contractSizeDecimal for {self.symbol}: {contract_size}. Cannot calculate position size.{RST}"
            )
            return False

        # Calculate desired position size (contracts)
        # This formula is for linear contracts where PnL is in quote currency
        position_size_contracts = (
            risk_amount_quote / (price_diff_to_sl * contract_size)
        ).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)

        # Ensure position size meets minimum requirements
        min_qty = Decimal(
            str(self.market_info.get("limits", {}).get("amount", {}).get("min", "0"))
        )
        qty_step = Decimal(
            str(
                self.market_info.get("limits", {})
                .get("amount", {})
                .get("step", "0.0001")
            )
        )  # Smallest increment

        if position_size_contracts < min_qty:
            self.logger.warning(
                f"{NY}Calculated position size ({position_size_contracts}) is less than minimum allowed ({min_qty}). Adjusting to minimum.{RST}"
            )
            position_size_contracts = min_qty

        # Quantize to the nearest qty_step
        if qty_step > 0:
            position_size_contracts = (position_size_contracts / qty_step).quantize(
                Decimal("1"), rounding=ROUND_DOWN
            ) * qty_step

        if position_size_contracts.is_zero():
            self.logger.error(
                f"{NR}Calculated position size is zero after quantization. Aborting trade.{RST}"
            )
            return False

        # Ensure sufficient margin
        # Estimated margin required: (position_size_contracts * entry_price_estimate * contract_size) / leverage
        estimated_cost = position_size_contracts * entry_price_estimate * contract_size
        margin_required = estimated_cost / leverage

        if TradeTracker.current_balance < margin_required:
            self.logger.error(
                f"{NR}Insufficient balance for trade. Required: {margin_required:.2f} {QC}, Available: {TradeTracker.current_balance:.2f} {QC}. Aborting trade.{RST}"
            )
            return False

        self.logger.info(
            f"{NB}Calculated trade details for {self.symbol} ({signal}): "
            f"Size={position_size_contracts:.4f} contracts, "
            f"Entry={entry_price_estimate:.{self.market_info.get('precision', {}).get('price', 2)}f}, "
            f"TP={tp_price}, SL={sl_price}, "
            f"Risk={risk_amount_quote:.2f} {QC}, Margin={margin_required:.2f} {QC}.{RST}"
        )

        order_params = {
            "symbol": self.symbol,
            "side": "buy" if signal == "BUY" else "sell",
            "amount": float(position_size_contracts),  # CCXT expects float for amount
            "params": {},
        }

        order_type = self.config.get("entry_order_type", "market").lower()
        if order_type == "limit":
            order_params["type"] = "limit"
            if signal == "BUY":
                order_params["price"] = float(
                    current_price
                    * (
                        Decimal("1")
                        - self.config.get("limit_order_offset_buy", Decimal("0.0005"))
                    )
                )
            else:  # SELL
                order_params["price"] = float(
                    current_price
                    * (
                        Decimal("1")
                        + self.config.get("limit_order_offset_sell", Decimal("0.0005"))
                    )
                )
            self.logger.info(
                f"{NB}Placing LIMIT order for {self.symbol} at {order_params['price']:.{self.market_info.get('precision', {}).get('price', 2)}f}.{RST}"
            )
        else:  # Default to market
            order_params["type"] = "market"
            self.logger.info(f"{NB}Placing MARKET order for {self.symbol}.{RST}")

        order = None
        try:
            # Use BybitV5Plugin for order placement
            bybit_plugin = (
                BybitV5Plugin()
            )  # Assuming plugin is initialized elsewhere or can be here
            if order_params["type"] == "market":
                order = bybit_plugin.place_market_order(
                    symbol=self.bybit_symbol_id,  # Use Bybit internal ID
                    side=order_params["side"].capitalize(),
                    qty=position_size_contracts,
                    category="linear" if self.market_info.get("linear") else "inverse",
                )
            elif order_params["type"] == "limit":
                order = bybit_plugin.place_limit_order(
                    symbol=self.bybit_symbol_id,
                    side=order_params["side"].capitalize(),
                    qty=position_size_contracts,
                    price=Decimal(str(order_params["price"])),
                    category="linear" if self.market_info.get("linear") else "inverse",
                )

            if order and order.get("orderId"):
                self.logger.info(
                    f"{NG}Order placed successfully for {self.symbol}. Order ID: {order['orderId']}. Status: {order.get('orderStatus', 'UNKNOWN')}. The spell is cast!{RST}"
                )

                # Create a new TradeRecord
                new_trade = TradeRecord(
                    symbol=self.symbol,
                    side=order_params["side"],
                    entry_price=Decimal(
                        str(order.get("price", current_price))
                    ),  # Use order price if available, else current
                    entry_time=datetime.now(TZ),
                    size=position_size_contracts,
                    leverage=leverage,
                    initial_capital=margin_required,  # Store margin required as initial capital
                    order_id=order["orderId"],
                    entry_order_status=order.get("orderStatus", "NEW"),
                    stop_loss_price=sl_price,
                    take_profit_price=tp_price,
                    margin_mode=self.market_info.get("marginMode"),  # Store margin mode
                )
                TradeTracker.add_open_trade(new_trade)

                # Confirm position after a short delay
                confirm_delay = self.config.get("position_confirm_delay_seconds", PCDS)
                self.logger.info(
                    f"{NB}Waiting {confirm_delay} seconds to confirm position for {self.symbol}.{RST}"
                )
                time.sleep(confirm_delay)

                # Fetch actual position info to update trade record
                position_info = fetch_position_info(
                    self.exchange, self.symbol, self.market_info, self.logger
                )
                if (
                    position_info
                    and position_info.get("contractsDecimal", Decimal("0")) > 0
                ):
                    actual_entry_price = position_info.get(
                        "entryPriceDecimal", new_trade.entry_price
                    )
                    actual_size = position_info.get("contractsDecimal", new_trade.size)

                    # Update the trade record with actual filled details
                    updated_trade = TradeTracker.get_open_trade(self.symbol)
                    if updated_trade:
                        updated_trade.entry_price = actual_entry_price
                        updated_trade.size = actual_size
                        updated_trade.entry_order_status = (
                            "FILLED"  # Assuming filled if position exists
                        )
                        updated_trade.position_id = position_info.get("positionId")
                        updated_trade.liquidation_price = position_info.get(
                            "liquidationPriceDecimal"
                        )
                        updated_trade.stop_loss_price = position_info.get(
                            "stopLossDecimal", sl_price
                        )  # Update with exchange's SL if set
                        updated_trade.take_profit_price = position_info.get(
                            "takeProfitDecimal", tp_price
                        )  # Update with exchange's TP if set
                        updated_trade.trailing_stop_active = (
                            position_info.get("trailingStopDecimal") is not None
                            and position_info["trailingStopDecimal"] > 0
                        )
                        updated_trade.trailing_stop_distance = position_info.get(
                            "trailingStopDecimal"
                        )
                        updated_trade.tsl_activation_price = position_info.get(
                            "tslActivationPriceDecimal"
                        )
                        TradeTracker._save_trades()
                        self.logger.info(
                            f"{NG}Position for {self.symbol} confirmed and trade record updated with actual entry {actual_entry_price} and size {actual_size}.{RST}"
                        )

                        # Set SL/TP/TSL after position is confirmed
                        self.logger.info(
                            f"{NB}Attempting to set SL/TP/TSL for confirmed position {self.symbol}.{RST}"
                        )
                        set_trade_stop_loss_take_profit(
                            exchange=self.exchange,
                            symbol=self.symbol,
                            market_info=self.market_info,
                            position_info=position_info,
                            config=self.config,
                            logger=self.logger,
                            fixed_stop_loss_price=sl_price,
                            take_profit_price_target=tp_price,
                            attempt_tsl=self.config.get("enable_trailing_stop", False),
                        )
                        return True
                    self.logger.error(
                        f"{NR}Trade record for {self.symbol} not found after order placement. This is unexpected.{RST}"
                    )
                    return False
                self.logger.error(
                    f"{NR}Position for {self.symbol} not confirmed after {confirm_delay}s. Order might not have filled or an issue occurred.{RST}"
                )
                # Mark trade as cancelled/failed if not confirmed
                updated_trade = TradeTracker.get_open_trade(self.symbol)
                if updated_trade:
                    updated_trade.status = "CLOSED_CANCELLED"
                    updated_trade.exit_reason = "ORDER_NOT_FILLED"
                    TradeTracker.close_trade(
                        self.symbol,
                        current_price,
                        datetime.now(TZ),
                        TradeTracker.current_balance,
                        "ORDER_NOT_FILLED",
                    )
                return False
            self.logger.error(
                f"{NR}Order placement failed for {self.symbol}. No order ID returned.{RST}"
            )
            return False
        except Exception as e:
            self.logger.error(
                f"{NR}Error placing order for {self.symbol}: {e}. The market rejected the spell!{RST}",
                exc_info=True,
            )
            return False

    @handle_exceptions(default_return=False, message="Error managing position")
    def _manage_position(self, current_price: Decimal) -> bool:
        """Manages an existing open position, including PnL updates, SL/TP/TSL, and break-even."""
        open_trade = TradeTracker.get_open_trade(self.symbol)
        if not open_trade or open_trade.status != "OPEN":
            self.logger.debug(
                f"_manage_position: No open trade found for {self.symbol} or status is not OPEN. Skipping management.{RST}"
            )
            return False  # No open position to manage

        # 1. Fetch latest position info from exchange (more reliable than WS for critical checks)
        position_info = fetch_position_info(
            self.exchange, self.symbol, self.market_info, self.logger
        )

        # If position is no longer open on exchange, close it in tracker
        if (
            not position_info
            or position_info.get("contractsDecimal", Decimal("0")).is_zero()
        ):
            if self.symbol in TradeTracker.open_trades:
                self.logger.warning(
                    f"{NY}Trade tracker shows open trade for {self.symbol}, but exchange reports no open position. Forcing closure in tracker. The ledger is out of sync!{RST}"
                )
                current_balance = (
                    fetch_balance(self.exchange, QC, self.logger)
                    or TradeTracker.current_balance
                )
                TradeTracker.close_trade(
                    self.symbol,
                    exit_price=current_price,
                    exit_time=datetime.now(TZ),
                    current_balance=current_balance,
                    exit_reason="EXCHANGE_CLOSED",
                )
            return False  # Position is closed, no further management needed

        # Update trade record with latest info from exchange
        open_trade.stop_loss_price = position_info.get(
            "stopLossDecimal", open_trade.stop_loss_price
        )
        open_trade.take_profit_price = position_info.get(
            "takeProfitDecimal", open_trade.take_profit_price
        )
        open_trade.trailing_stop_active = (
            position_info.get("trailingStopDecimal") is not None
            and position_info["trailingStopDecimal"] > 0
        )
        open_trade.trailing_stop_distance = position_info.get(
            "trailingStopDecimal", open_trade.trailing_stop_distance
        )
        open_trade.tsl_activation_price = position_info.get(
            "tslActivationPriceDecimal", open_trade.tsl_activation_price
        )
        open_trade.liquidation_price = position_info.get(
            "liquidationPriceDecimal", open_trade.liquidation_price
        )
        open_trade.unrealized_pnl_quote = position_info.get(
            "unrealisedPnlDecimal", open_trade.unrealized_pnl_quote
        )
        # Recalculate percentage PnL based on updated quote PnL
        if (
            open_trade.initial_capital
            and open_trade.initial_capital > 0
            and open_trade.unrealized_pnl_quote is not None
        ):
            open_trade.unrealized_pnl_percentage = (
                open_trade.unrealized_pnl_quote / open_trade.initial_capital
            ) * 100

        # 2. Check for exit signals from ExitSignalManager
        if self.exit_signal_manager:
            # Ensure TA analyzer has the latest data for exit conditions
            self.exit_signal_manager.ta_analyzer.set_data(
                self.ta_analyzer.data
            )  # Pass the latest OHLCV data
            exit_reason = self.exit_signal_manager.check_exit_conditions(
                open_trade_symbol=self.symbol,
                current_price=current_price,
                historical_data_for_ta=self.ta_analyzer.data,  # Pass the DataFrame
            )
            if exit_reason:
                self.logger.info(
                    f"{NY}Exit signal triggered for {self.symbol} by ExitSignalManager (Reason: {exit_reason}). Closing trade.{RST}"
                )
                if self._close_trade_execution(exit_reason.lower(), current_price):
                    return False  # Position closed

        # 3. Check for time-based exit
        if (
            self.config.get("time_based_exit_minutes") is not None
            and self.config.get("time_based_exit_minutes") > 0
        ):
            if self._check_time_based_exit(open_trade):
                self.logger.info(
                    f"{NY}Time-based exit triggered for {self.symbol}. Closing trade.{RST}"
                )
                if self._close_trade_execution("time_based_exit", current_price):
                    return False  # Position closed

        # 4. Check for break-even adjustment
        if self.config.get("enable_break_even", False):
            if self._check_break_even(current_price, position_info):
                self.logger.debug(
                    f"_manage_position: Break-even logic processed for {self.symbol}. Re-fetching position info to get updated SL/TP from exchange."
                )
                # Re-fetch position info after BE adjustment to get latest SL/TP values from exchange
                position_info = fetch_position_info(
                    self.exchange, self.symbol, self.market_info, self.logger
                )
                if (
                    not position_info
                    or position_info.get("contractsDecimal", Decimal("0")).is_zero()
                ):
                    self.logger.warning(
                        f"{NY}_manage_position: Position for {self.symbol} disappeared after BE adjustment. Assuming closed.{RST}"
                    )
                    if self.symbol in TradeTracker.open_trades:
                        current_balance = (
                            fetch_balance(self.exchange, QC, self.logger)
                            or TradeTracker.current_balance
                        )
                        TradeTracker.close_trade(
                            self.symbol,
                            exit_price=current_price,
                            exit_time=datetime.now(TZ),
                            current_balance=current_balance,
                            exit_reason="BREAK_EVEN_CLOSED",
                        )
                    return False  # Position closed

        # Re-fetch the trade record as it might have been updated by break-even logic
        open_trade = TradeTracker.get_open_trade(self.symbol)
        if not open_trade:
            self.logger.error(
                f"{NR}_manage_position: Critical - Position info exists for {self.symbol}, but no corresponding trade record in Trade Tracker (after all initial checks). Cannot manage position.{RST}"
            )
            return False

        # 5. Recalculate desired TP/SL based on current entry price from trade record
        # This ensures TP/SL are always relative to the actual entry price of the trade
        entry_price_from_record, desired_tp, desired_sl = (
            self.ta_analyzer.calculate_entry_take_profit_stop_loss(
                entry_price_estimate=open_trade.entry_price,
                signal=open_trade.side.upper(),
            )
        )
        min_trade_size = IndicatorCalculator.gmts(self.market_info, self.logger)

        # Check if TSL is active on exchange (from fetched position_info)
        tsl_active_on_exchange = (
            position_info.get("trailingStopDecimal") is not None
            and position_info["trailingStopDecimal"] > 0
        )

        # 6. Set/Update SL/TP/TSL on the exchange
        if self.config.get(
            "enable_trailing_stop", False
        ):  # Trailing Stop is ENABLED in config
            self.logger.info(
                f"{NB}_manage_position: Trailing Stop is ENABLED for {self.symbol}. Calling set_trade_stop_loss_take_profit to manage TSL and TP. Desired TP (from TA): {desired_tp}. Position Info being passed to set_trade_stop_loss_take_profit: SL={position_info.get('stopLossDecimal')}, TP={position_info.get('takeProfitDecimal')}, TSL_Dist={position_info.get('trailingStopDecimal')}{RST}"
            )
            stsl_success = set_trade_stop_loss_take_profit(
                exchange=self.exchange,
                symbol=self.symbol,
                market_info=self.market_info,
                position_info=position_info,
                config=self.config,
                logger=self.logger,
                fixed_stop_loss_price=None,  # TSL takes precedence, so fixed SL is None
                take_profit_price_target=desired_tp,
                attempt_tsl=True,
            )
            if not stsl_success:
                self.logger.warning(
                    f"{NY}_manage_position: set_trade_stop_loss_take_profit call (for TSL management) for {self.symbol} failed. Position may not have desired protections.{RST}"
                )
        else:  # Trailing Stop is DISABLED in config
            self.logger.info(
                f"{NB}_manage_position: Trailing Stop is DISABLED for {self.symbol}. Calling set_trade_stop_loss_take_profit to manage fixed SL and TP. Desired SL: {desired_sl}, Desired TP: {desired_tp}. TSL active on exchange: {tsl_active_on_exchange}. Position Info being passed to set_trade_stop_loss_take_profit: SL={position_info.get('stopLossDecimal')}, TP={position_info.get('takeProfitDecimal')}, TSL_Dist={position_info.get('trailingStopDecimal')}{RST}"
            )

            # Check if an update is actually needed to avoid unnecessary API calls
            current_sl_exchange_raw = position_info.get("stopLossDecimal")
            current_tp_exchange_raw = position_info.get("takeProfitDecimal")

            sl_update_needed = False
            if desired_sl is not None:
                if (
                    current_sl_exchange_raw is None
                    or abs(current_sl_exchange_raw - desired_sl) > min_trade_size
                ):
                    sl_update_needed = True
            elif (
                current_sl_exchange_raw is not None and current_sl_exchange_raw > 0
            ):  # If desired SL is None but exchange has one
                sl_update_needed = True

            tp_update_needed = False
            if desired_tp is not None:
                if (
                    current_tp_exchange_raw is None
                    or abs(current_tp_exchange_raw - desired_tp) > min_trade_size
                ):
                    tp_update_needed = True
            elif (
                current_tp_exchange_raw is not None and current_tp_exchange_raw > 0
            ):  # If desired TP is None but exchange has one
                tp_update_needed = True

            if tsl_active_on_exchange or sl_update_needed or tp_update_needed:
                self.logger.info(
                    f"{NB}_manage_position: Conditions for updating fixed protections met for {self.symbol} (TSL active on ex: {tsl_active_on_exchange}, SL update needed: {sl_update_needed}, TP update needed: {tp_update_needed}). Calling set_trade_stop_loss_take_profit with fixed SL: {desired_sl}, fixed TP: {desired_tp}.{RST}"
                )
                stsl_success = set_trade_stop_loss_take_profit(
                    exchange=self.exchange,
                    symbol=self.symbol,
                    market_info=self.market_info,
                    position_info=position_info,
                    config=self.config,
                    logger=self.logger,
                    fixed_stop_loss_price=desired_sl,
                    take_profit_price_target=desired_tp,
                    attempt_tsl=False,  # Explicitly disable TSL
                )
                if not stsl_success:
                    self.logger.warning(
                        f"{NY}_manage_position: set_trade_stop_loss_take_profit call (for fixed SL/TP management) for {self.symbol} failed. Position may not have desired protections.{RST}"
                    )
            else:
                self.logger.debug(
                    f"{NB}_manage_position: No mismatch in fixed SL/TP for {self.symbol}, and TSL is disabled and not active on exchange. No protection update needed via set_trade_stop_loss_take_profit.{RST}"
                )

        # Final check for trade closure by SL/TP hit (based on trade record's stored values)
        # The trade record's SL/TP values should have been updated by set_trade_stop_loss_take_profit
        open_trade = TradeTracker.get_open_trade(self.symbol)
        if not open_trade:
            self.logger.warning(
                f"{NY}_manage_position: Trade record for {self.symbol} disappeared after protection setting. Assuming position closed.{RST}"
            )
            return False  # Position is now closed

        sl_from_record = open_trade.stop_loss_price
        tp_from_record = open_trade.take_profit_price

        if open_trade and open_trade.status == "OPEN":
            if open_trade.side == "long":
                if tp_from_record and current_price >= tp_from_record:
                    self.logger.info(
                        f"{NG}Take Profit hit for {self.symbol} (Long)! Current: {current_price:.4f}, TP: {tp_from_record:.4f}{RST}"
                    )
                    if self._close_trade_execution("TP", current_price):
                        return False  # Position closed
                if sl_from_record and current_price <= sl_from_record:
                    self.logger.info(
                        f"{NR}Stop Loss hit for {self.symbol} (Long)! Current: {current_price:.4f}, SL: {sl_from_record:.4f}{RST}"
                    )
                    if self._close_trade_execution("SL", current_price):
                        return False  # Position closed
            elif open_trade.side == "short":
                if tp_from_record and current_price <= tp_from_record:
                    self.logger.info(
                        f"{NG}Take Profit hit for {self.symbol} (Short)! Current: {current_price:.4f}, TP: {tp_from_record:.4f}{RST}"
                    )
                    if self._close_trade_execution("TP", current_price):
                        return False  # Position closed
                if sl_from_record and current_price >= sl_from_record:
                    self.logger.info(
                        f"{NR}Stop Loss hit for {self.symbol} (Short)! Current: {current_price:.4f}, SL: {sl_from_record:.4f}{RST}"
                    )
                    if self._close_trade_execution("SL", current_price):
                        return False  # Position closed

        return True  # Position managed successfully for this cycle

    @handle_exceptions(default_return=False, message="Error closing trade execution")
    def _close_trade_execution(self, exit_reason: str, current_price: Decimal) -> bool:
        """Executes the trade closure on the exchange."""
        open_trade = TradeTracker.get_open_trade(self.symbol)
        if not open_trade:
            self.logger.warning(
                f"{NY}_close_trade_execution: No open trade record found for {self.symbol}. Cannot close.{RST}"
            )
            return False

        self.logger.info(
            f"{NB}Attempting to close {self.symbol} position due to {exit_reason}. Current price: {current_price:.4f}.{RST}"
        )

        # Use BybitV5Plugin for order placement
        bybit_plugin = (
            BybitV5Plugin()
        )  # Assuming plugin is initialized elsewhere or can be here

        # Determine side for closing order
        close_side = "SELL" if open_trade.side == "long" else "BUY"

        # Place a market order to close the position
        order = bybit_plugin.place_market_order(
            symbol=self.bybit_symbol_id,
            side=close_side,
            qty=open_trade.size,
            category="linear" if self.market_info.get("linear") else "inverse",
            reduce_only=True,  # Ensure this order only reduces position
        )

        if order and order.get("orderId"):
            self.logger.info(
                f"{NG}Close order placed for {self.symbol}. Order ID: {order['orderId']}. Status: {order.get('orderStatus', 'UNKNOWN')}.{RST}"
            )
            open_trade.exit_order_id = order["orderId"]
            open_trade.exit_order_status = order.get("orderStatus", "NEW")
            TradeTracker._save_trades()

            # Confirm position closure after a short delay
            confirm_delay = self.config.get("position_confirm_delay_seconds", PCDS)
            self.logger.info(
                f"{NB}Waiting {confirm_delay} seconds to confirm position closure for {self.symbol}.{RST}"
            )
            time.sleep(confirm_delay)

            position_info = fetch_position_info(
                self.exchange, self.symbol, self.market_info, self.logger
            )
            if (
                not position_info
                or position_info.get("contractsDecimal", Decimal("0")).is_zero()
            ):
                # Position successfully closed on exchange
                current_balance = (
                    fetch_balance(self.exchange, QC, self.logger)
                    or TradeTracker.current_balance
                )
                TradeTracker.close_trade(
                    self.symbol,
                    current_price,
                    datetime.now(TZ),
                    current_balance,
                    exit_reason,
                )
                self.logger.info(
                    f"{NG}Position for {self.symbol} successfully closed on exchange and tracker updated.{RST}"
                )
                return True
            self.logger.error(
                f"{NR}Position for {self.symbol} still open on exchange after close order. Size: {position_info.get('contractsDecimal')}. Manual intervention may be required!{RST}"
            )
            open_trade.exit_order_status = "FAILED_TO_CLOSE"
            TradeTracker._save_trades()
            return False
        self.logger.error(
            f"{NR}Failed to place close order for {self.symbol}. No order ID returned.{RST}"
        )
        return False

    @handle_exceptions(default_return=False, message="Error checking break-even")
    def _check_break_even(
        self, current_price: Decimal, position_info: dict[str, Any]
    ) -> bool:
        """Manages break-even stop loss adjustments."""
        if not self.config.get("enable_break_even", False):
            self.logger.debug(
                f"Break-Even feature is disabled for {self.symbol}. Skipping check.{RST}"
            )
            return False

        atr_value = self.ta_analyzer.get_indicator("atr")
        if atr_value is None or atr_value.values is None or atr_value.values.empty:
            self.logger.warning(
                f"{NY}Break-Even check skipped for {self.symbol}: Invalid or missing ATR. Cannot calculate break-even trigger.{RST}"
            )
            return False

        latest_atr_val = atr_value.values.iloc[-1]
        if pd.isna(latest_atr_val) or Decimal(str(latest_atr_val)) <= 0:
            self.logger.warning(
                f"{NY}Break-Even check skipped for {self.symbol}: Invalid or missing ATR ({latest_atr_val}). Cannot calculate break-even trigger.{RST}"
            )
            return False
        atr_value_dec = Decimal(str(latest_atr_val))

        entry_price = position_info.get("entryPriceDecimal")
        position_side = position_info.get("positionSide")

        if not isinstance(entry_price, Decimal) or entry_price <= 0:
            self.logger.warning(
                f"{NY}Break-Even check skipped for {self.symbol}: Invalid entry price ({entry_price}).{RST}"
            )
            return False
        if position_side not in ["long", "short"]:
            self.logger.warning(
                f"{NY}Break-Even check skipped for {self.symbol}: Invalid position side ('{position_side}').{RST}"
            )
            return False

        current_sl_raw = position_info.get("stopLossDecimal")
        current_sl_dec = None
        if current_sl_raw is not None and str(current_sl_raw).strip() != "":
            try:
                sl_dec = Decimal(str(current_sl_raw))
                if sl_dec > 0:  # Only consider positive SL as active
                    current_sl_dec = sl_dec
                else:
                    self.logger.debug(
                        f"_check_break_even: Raw stop loss '{current_sl_raw}' is zero or negative, treating as no SL for {self.symbol}."
                    )
            except (InvalidOperation, ValueError, TypeError):
                self.logger.warning(
                    f"{NY}_check_break_even: Could not convert current_sl_raw '{current_sl_raw}' to Decimal for {self.symbol}. Treating as no SL set.{RST}"
                )
                current_sl_dec = None
        else:
            self.logger.debug(
                f"_check_break_even: No active stop loss (current_sl_raw: '{current_sl_raw}') found for {self.symbol} for break-even check."
            )

        atr_multiplier = Decimal(
            str(self.config.get("break_even_trigger_atr_multiple", "1.0"))
        )
        price_precision = IndicatorCalculator.gpp(self.market_info, self.logger)
        min_trade_size = IndicatorCalculator.gmts(self.market_info, self.logger)
        offset_ticks = self.config.get("break_even_offset_ticks", 2)
        offset_amount = min_trade_size * Decimal(str(offset_ticks))

        new_sl_price = None
        trigger_price = None

        if position_side == "long":
            trigger_price = entry_price + atr_value_dec * atr_multiplier
            if current_price >= trigger_price:
                new_sl_price = entry_price + offset_amount
                # Quantize new SL price
                if min_trade_size > 0:
                    new_sl_price = (new_sl_price / min_trade_size).quantize(
                        Decimal("1"), rounding=ROUND_UP
                    ) * min_trade_size
                else:
                    new_sl_price = new_sl_price.quantize(
                        Decimal("1e-" + str(price_precision)), rounding=ROUND_UP
                    )

                if current_sl_dec is None or new_sl_price > current_sl_dec:
                    self.logger.info(
                        f"{NG}Break-Even triggered for {self.symbol} (Long). Current Price: {current_price:.{price_precision}f} >= Trigger: {trigger_price:.{price_precision}f}. Preparing to set SL to {new_sl_price:.{price_precision}f}. Securing the gains!{RST}"
                    )

                    # Get current TP from position_info to maintain it
                    current_tp_raw = position_info.get("takeProfitDecimal")
                    current_tp_dec = None
                    if current_tp_raw is not None and str(current_tp_raw).strip() != "":
                        try:
                            current_tp_dec = Decimal(str(current_tp_raw))
                        except InvalidOperation:
                            self.logger.warning(
                                f"_check_break_even: Could not convert existing TP '{current_tp_raw}' to Decimal. Setting TP to None for set_trade_stop_loss_take_profit call."
                            )

                    self.logger.info(
                        f"{NB}_check_break_even: Attempting to set Break-Even SL for {self.symbol} (Long) to {new_sl_price:.{price_precision}f}. Maintaining TP: {current_tp_dec}. TSL will be disabled.{RST}"
                    )
                    success = set_trade_stop_loss_take_profit(
                        exchange=self.exchange,
                        symbol=self.symbol,
                        market_info=self.market_info,
                        position_info=position_info,
                        config=self.config,
                        logger=self.logger,
                        fixed_stop_loss_price=new_sl_price,
                        take_profit_price_target=current_tp_dec,
                        attempt_tsl=False,  # Disable TSL when BE is active
                    )
                    if success:
                        self.logger.info(
                            f"{NG}_check_break_even: Break-Even SL for {self.symbol} (Long) successfully set via set_trade_stop_loss_take_profit.{RST}"
                        )
                        return True
                    self.logger.warning(
                        f"{NY}_check_break_even: Break-Even SL setting failed for {self.symbol} (Long) via set_trade_stop_loss_take_profit.{RST}"
                    )
                else:
                    self.logger.debug(
                        f"Break-Even for {self.symbol} (Long) triggered, but new SL {new_sl_price:.{price_precision}f} is not higher than current SL {current_sl_dec:.{price_precision}f}. No update needed. The shield is already advanced.{RST}"
                    )
        elif position_side == "short":
            trigger_price = entry_price - atr_value_dec * atr_multiplier
            if current_price <= trigger_price:
                new_sl_price = entry_price - offset_amount
                # Quantize new SL price
                if min_trade_size > 0:
                    new_sl_price = (new_sl_price / min_trade_size).quantize(
                        Decimal("1"), rounding=ROUND_DOWN
                    ) * min_trade_size
                else:
                    new_sl_price = new_sl_price.quantize(
                        Decimal("1e-" + str(price_precision)), rounding=ROUND_DOWN
                    )

                if current_sl_dec is None or new_sl_price < current_sl_dec:
                    self.logger.info(
                        f"{NG}Break-Even triggered for {self.symbol} (Short). Current Price: {current_price:.{price_precision}f} <= Trigger: {trigger_price:.{price_precision}f}. Preparing to set SL to {new_sl_price:.{price_precision}f}. Securing the gains!{RST}"
                    )

                    # Get current TP from position_info to maintain it
                    current_tp_raw = position_info.get("takeProfitDecimal")
                    current_tp_dec = None
                    if current_tp_raw is not None and str(current_tp_raw).strip() != "":
                        try:
                            current_tp_dec = Decimal(str(current_tp_raw))
                        except InvalidOperation:
                            self.logger.warning(
                                f"_check_break_even: Could not convert existing TP '{current_tp_raw}' to Decimal. Setting TP to None for set_trade_stop_loss_take_profit call."
                            )

                    self.logger.info(
                        f"{NB}_check_break_even: Attempting to set Break-Even SL for {self.symbol} (Short) to {new_sl_price:.{price_precision}f}. Maintaining TP: {current_tp_dec}. TSL will be disabled.{RST}"
                    )
                    success = set_trade_stop_loss_take_profit(
                        exchange=self.exchange,
                        symbol=self.symbol,
                        market_info=self.market_info,
                        position_info=position_info,
                        config=self.config,
                        logger=self.logger,
                        fixed_stop_loss_price=new_sl_price,
                        take_profit_price_target=current_tp_dec,
                        attempt_tsl=False,  # Disable TSL when BE is active
                    )
                    if success:
                        self.logger.info(
                            f"{NG}_check_break_even: Break-Even SL for {self.symbol} (Short) successfully set via set_trade_stop_loss_take_profit.{RST}"
                        )
                        return True
                    self.logger.warning(
                        f"{NY}_check_break_even: Break-Even SL setting failed for {self.symbol} (Short) via set_trade_stop_loss_take_profit.{RST}"
                    )
                else:
                    self.logger.debug(
                        f"Break-Even for {self.symbol} (Short) triggered, but new SL {new_sl_price:.{price_precision}f} is not lower than current SL {current_sl_dec:.{price_precision}f}. No update needed. The shield is already advanced.{RST}"
                    )

        self.logger.debug(
            f"Break-Even not triggered for {self.symbol}. Current Price: {current_price:.{price_precision}f}, Trigger: {trigger_price:.{price_precision}f}. Still awaiting the threshold.{RST}"
        )
        return False

    @handle_exceptions(default_return=False, message="Error checking time-based exit")
    def _check_time_based_exit(self, open_trade: TradeRecord) -> bool:
        """Manages time-based exits."""
        time_based_exit_minutes = self.config.get("time_based_exit_minutes")
        if time_based_exit_minutes is None or time_based_exit_minutes <= 0:
            self.logger.debug(
                f"Time-based exit is disabled or configured for 0 minutes for {self.symbol}. Skipping check.{RST}"
            )
            return False

        if not open_trade:
            self.logger.debug(
                f"No open trade for {self.symbol} to check for time-based exit. The position is already clear.{RST}"
            )
            return False

        trade_duration = datetime.now(TZ) - open_trade.entry_time
        if trade_duration.total_seconds() / 60 >= time_based_exit_minutes:
            self.logger.info(
                f"Time-based exit triggered for {self.symbol}. Trade open for {trade_duration.total_seconds() / 60:.2f} minutes (Threshold: {time_based_exit_minutes} minutes). The temporal limit has been reached!{RST}"
            )
            return True
        return False

    @handle_exceptions(default_return=False, message="Error cancelling all open orders")
    def _cancel_all_open_orders(self) -> bool:
        """Cancels all open orders for the symbol."""
        self.logger.info(
            f"{NB}Attempting to cancel all open orders for {self.symbol}.{RST}"
        )
        try:
            bybit_plugin = BybitV5Plugin()
            category = "linear" if self.market_info.get("linear") else "inverse"
            result = bybit_plugin.cancel_all_orders(
                category=category, symbol=self.bybit_symbol_id
            )
            if result and result.get("list") is not None:
                self.logger.info(
                    f"{NG}Successfully cancelled {len(result['list'])} orders for {self.symbol}.{RST}"
                )
                return True
            self.logger.warning(
                f"{NY}No orders to cancel or cancellation response was unexpected for {self.symbol}. Result: {result}{RST}"
            )
            return False
        except Exception as e:
            self.logger.error(
                f"{NR}Error cancelling all orders for {self.symbol}: {e}.{RST}",
                exc_info=True,
            )
            return False


# --- Main Bot Class ---
class ScalperBot:
    """The Orchestrator: Manages the overall bot lifecycle, including initialization, running, and stopping."""

    def __init__(self, config: dict[str, Any]):
        self.logger = slg("main")
        self.config = config
        self.exchange: ccxt.Exchange | None = None
        self.per_symbol_bots: dict[str, PerSymbolBot] = {}
        self.websocket_client: BybitWebSocket | None = None
        self.is_running = False
        self.last_sms_report_time = 0.0

    def initialize(self) -> None:
        """Initializes the exchange, WebSocket client, and individual symbol bots."""
        self.logger.info(f"{NB}--- Initializing XR Scalper Bot ---{RST}")
        self.exchange = initialize_exchange(self.config, self.logger)
        if not self.exchange:
            self.logger.critical(
                f"{NR}Exchange initialization failed. Exiting. The trading realm remains inaccessible!{RST}"
            )
            sys.exit(1)

        TradeTracker.set_exchange_reference(self.exchange)
        TradeTracker._load_trades()  # Load trade history after exchange is set

        self.websocket_client = BybitWebSocket(
            api_key=AK,
            api_secret=AS,
            use_testnet=self.config.get("use_sandbox", True),
            logger=slg("websocket"),
        )

        public_topics = []
        for symbol in self.config.get("symbols_to_trade", []):
            try:
                symbol_bot = PerSymbolBot(
                    symbol,
                    self.exchange,
                    self.config,
                    slg(symbol.replace("/", "_").replace(":", "_")),
                    self.websocket_client,
                )
                self.per_symbol_bots[symbol] = symbol_bot
                bybit_symbol_id = symbol_bot.market_info.get("id")
                if bybit_symbol_id:
                    public_topics.append(f"tickers.{bybit_symbol_id}")
                    if self.config.get("indicators", {}).get(
                        "orderbook", False
                    ) and self.config.get("enable_orderbook_depth_analysis", False):
                        public_topics.append(
                            f"orderbook.{self.config.get('orderbook_limit', 50)}.{bybit_symbol_id}"
                        )
                else:
                    self.logger.warning(
                        f"{NY}Could not get Bybit symbol ID for {symbol}, skipping public WebSocket topic subscriptions for it.{RST}"
                    )
            except ValueError as err:
                self.logger.error(
                    f"{NR}Failed to initialize bot for symbol {symbol}: {err}. Skipping this symbol. A specific enchantment failed!{RST}"
                )
            except Exception as err:
                self.logger.error(
                    f"{NR}Unexpected error initializing bot for symbol {symbol}: {err}. Skipping this symbol. A cosmic interference!{RST}",
                    exc_info=True,
                )

        if not self.per_symbol_bots:
            self.logger.critical(
                f"{NR}No symbols successfully initialized. Exiting. The bot has no markets to observe!{RST}"
            )
            sys.exit(1)

        self.websocket_client.start_streams(public_topics=list(set(public_topics)))
        self.logger.info(
            f"{NG}XR Scalper Bot initialized successfully with WebSocket client. Public topics: {self.websocket_client.public_subscriptions}. The trading journey is ready to begin!{RST}"
        )
        self.is_running = True

    def run(self) -> None:
        """The main execution loop of the bot."""
        self.logger.info(f"{NB}--- Starting XR Scalper Bot Main Loop ---{RST}")
        last_run_times: dict[str, float] = {}
        interval_seconds = int(self.config.get("interval", "5")) * 60

        while self.is_running:
            try:
                enable_sms = self.config.get("enable_sms_alerts", False)
                sms_recipient = self.config.get("sms_recipient_number")
                sms_interval_minutes = self.config.get("sms_report_interval_minutes")

                if (
                    enable_sms
                    and sms_recipient
                    and sms_interval_minutes
                    and sms_interval_minutes > 0
                ):
                    current_time = time.time()
                    if (
                        current_time - self.last_sms_report_time
                        >= sms_interval_minutes * 60
                    ):
                        self.logger.info(
                            f"{NB}SMS report interval reached. Generating summary...{RST}"
                        )
                        try:
                            current_balance = fetch_balance(
                                self.exchange, QC, self.logger
                            )
                            formatted_balance = (
                                f"{current_balance:.2f} {QC}"
                                if current_balance is not None
                                else "N/A"
                            )

                            open_pos_summary = []
                            if TradeTracker.open_trades:
                                for symbol, trade in TradeTracker.open_trades.items():
                                    pnl_str = (
                                        f"{trade.unrealized_pnl_quote:.2f}"
                                        if trade.unrealized_pnl_quote is not None
                                        else "N/A"
                                    )
                                    open_pos_summary.append(
                                        f"{symbol.split('/')[0]}:{trade.side[:1].upper()}({pnl_str})"
                                    )
                            open_pos_str = (
                                ", ".join(open_pos_summary)
                                if open_pos_summary
                                else "None"
                            )
                            if len(open_pos_str) > 100:
                                open_pos_str = open_pos_str[:97] + "..."

                            closed_trade_summary = []
                            if TradeTracker.closed_trades:
                                last_closed = TradeTracker.closed_trades[-1]
                                pnl_str = (
                                    f"{last_closed.realized_pnl_quote:.2f}"
                                    if last_closed.realized_pnl_quote is not None
                                    else "N/A"
                                )
                                closed_trade_summary.append(
                                    f"Last Closed: {last_closed.symbol.split('/')[0]} PnL:{pnl_str}"
                                )
                            closed_str = (
                                ", ".join(closed_trade_summary)
                                if closed_trade_summary
                                else "None"
                            )

                            total_pnl_str = (
                                f"{TradeTracker.total_pnl:.2f} {QC}"
                                if TradeTracker.total_pnl is not None
                                else "N/A"
                            )
                            sms_message = f"XR Scalper Update:\nBalance: {formatted_balance}\nTotal PnL: {total_pnl_str}\nOpen Pos: {open_pos_str}\n{closed_str}"
                            send_sms_alert(
                                sms_message, sms_recipient, self.logger, self.config
                            )
                            self.last_sms_report_time = current_time
                        except Exception as err:
                            self.logger.error(
                                f"{NR}Error generating periodic SMS summary: {err}{RST}",
                                exc_info=True,
                            )

                loop_start_time = time.time()
                for symbol, bot_instance in self.per_symbol_bots.items():
                    if (
                        symbol not in last_run_times
                        or loop_start_time - last_run_times[symbol] >= interval_seconds
                    ):
                        bot_instance.run_symbol_logic()
                        last_run_times[symbol] = loop_start_time
                    else:
                        self.logger.debug(
                            f"Waiting for next interval for {symbol}. Next run in {interval_seconds - (loop_start_time - last_run_times[symbol]):.1f}s.{RST}"
                        )

                clear_screen()
                TradeTracker.display_metrics()

                if self.websocket_client:
                    display_open_positions(
                        open_trades=TradeTracker.open_trades,
                        market_infos=TradeTracker.market_info_cache,
                        current_prices=self.websocket_client.prices,
                        quote_currency=QC,
                        logger=self.logger,
                    )
                    display_recent_closed_trades(
                        closed_trades=TradeTracker.closed_trades,
                        market_infos=TradeTracker.market_info_cache,
                        quote_currency=QC,
                        logger=self.logger,
                        num_to_display=5,
                    )
                else:
                    self.logger.warning(
                        f"{NY}WebSocket client not available, cannot display open positions or current prices.{RST}"
                    )

                time.sleep(self.config.get("main_loop_sleep_seconds", RDS))
            except KeyboardInterrupt:
                self.logger.info(
                    f"{NY}KeyboardInterrupt detected. Stopping bot... The user has commanded a halt!{RST}"
                )
                self.stop()
            except Exception as err:
                self.logger.error(
                    f"{NR}An unexpected error occurred in the main loop: {err}. A cosmic interference in the bot's operation!{RST}",
                    exc_info=True,
                )
                time.sleep(self.config.get("main_loop_sleep_seconds", RDS) * 2)

    def stop(self) -> None:
        """Stops the bot's execution gracefully."""
        self.is_running = False
        self.logger.info(f"{NB}--- Stopping XR Scalper Bot ---{RST}")
        if self.websocket_client:
            self.websocket_client.stop_streams()
        for symbol, bot_instance in self.per_symbol_bots.items():
            self.logger.info(
                f"{NB}Attempting to cancel all open orders for {symbol} before shutdown...{RST}"
            )
            bot_instance._cancel_all_open_orders()
        self.logger.info(f"{NG}Bot stopped. The trading session has concluded!{RST}")
        TradeTracker.display_metrics()  # Final display of metrics


# --- Entry Point ---
if __name__ == "__main__":
    # Initialize TradeTracker globally
    TradeTracker = TradeManager()

    bot = ScalperBot(config=_initial_config_from_file)
    try:
        bot.initialize()
        bot.run()
    except Exception as err:
        bot.logger.critical(
            f"{NR}Bot encountered a critical error during initialization or main loop execution: {err}. Aborting!{RST}",
            exc_info=True,
        )
    finally:
        if bot.is_running:
            bot.stop()
        bot.logger.info(f"{NB}--- XR Scalper Bot process finished ---{RST}")
