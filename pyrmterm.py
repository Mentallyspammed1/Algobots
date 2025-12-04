import asyncio
import decimal
import json
import os
import smtplib
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from threading import Thread

import ccxt
import joblib
import numpy as np
import requests
import websockets
from colorama import Back, Fore, Style, init
from dotenv import load_dotenv
from sklearn.ensemble import RandomForestClassifier

init(autoreset=True)
decimal.getcontext().prec = 30

load_dotenv()
print(f"{Fore.CYAN}{Style.DIM}# Loading ancient scrolls (.env)...{Style.RESET_ALL}")

CONFIG = {
    "API_KEY": os.environ.get("BYBIT_API_KEY"),
    "API_SECRET": os.environ.get("BYBIT_API_SECRET"),
    "SYMBOL": os.environ.get("BYBIT_SYMBOL", "BTCUSDT").upper(),
    "EXCHANGE_TYPE": os.environ.get("BYBIT_EXCHANGE_TYPE", "linear"),
    "VOLUME_THRESHOLDS": {
        "high": decimal.Decimal(os.environ.get("VOLUME_THRESHOLD_HIGH", "10")),
        "medium": decimal.Decimal(os.environ.get("VOLUME_THRESHOLD_MEDIUM", "2")),
    },
    "REFRESH_INTERVAL": int(os.environ.get("REFRESH_INTERVAL", "9")),
    "MAX_ORDERBOOK_DEPTH_DISPLAY": int(
        os.environ.get("MAX_ORDERBOOK_DEPTH_DISPLAY", "50"),
    ),
    "ORDER_FETCH_LIMIT": int(os.environ.get("ORDER_FETCH_LIMIT", "200")),
    "DEFAULT_EXCHANGE_TYPE": "linear",
    "CONNECT_TIMEOUT": int(os.environ.get("CONNECT_TIMEOUT", "30000")),
    "RETRY_DELAY_NETWORK_ERROR": int(os.environ.get("RETRY_DELAY_NETWORK_ERROR", "10")),
    "RETRY_DELAY_RATE_LIMIT": int(os.environ.get("RETRY_DELAY_RATE_LIMIT", "60")),
    "INDICATOR_TIMEFRAME": os.environ.get("INDICATOR_TIMEFRAME", "15m"),
    "SMA_PERIOD": int(os.environ.get("SMA_PERIOD", "9")),
    "SMA2_PERIOD": int(os.environ.get("SMA2_PERIOD", "20")),
    "EMA1_PERIOD": int(os.environ.get("EMA1_PERIOD", "12")),
    "EMA2_PERIOD": int(os.environ.get("EMA2_PERIOD", "34")),
    "MOMENTUM_PERIOD": int(os.environ.get("MOMENTUM_PERIOD", "10")),
    "RSI_PERIOD": int(os.environ.get("RSI_PERIOD", "14")),
    "STOCH_K_PERIOD": int(os.environ.get("STOCH_K_PERIOD", "14")),
    "STOCH_D_PERIOD": int(os.environ.get("STOCH_D_PERIOD", "3")),
    "STOCH_RSI_OVERSOLD": decimal.Decimal(os.environ.get("STOCH_RSI_OVERSOLD", "20")),
    "STOCH_RSI_OVERBOUGHT": decimal.Decimal(
        os.environ.get("STOCH_RSI_OVERBOUGHT", "80"),
    ),
    "PIVOT_TIMEFRAME": os.environ.get("PIVOT_TIMEFRAME", "30m"),
    "PNL_PRECISION": int(os.environ.get("PNL_PRECISION", "2")),
    "MIN_PRICE_DISPLAY_PRECISION": int(
        os.environ.get("MIN_PRICE_DISPLAY_PRECISION", "3"),
    ),
    "STOCH_RSI_DISPLAY_PRECISION": int(
        os.environ.get("STOCH_RSI_DISPLAY_PRECISION", "3"),
    ),
    "VOLUME_DISPLAY_PRECISION": int(os.environ.get("VOLUME_DISPLAY_PRECISION", "0")),
    "BALANCE_DISPLAY_PRECISION": int(os.environ.get("BALANCE_DISPLAY_PRECISION", "2")),
    "FETCH_BALANCE_ASSET": os.environ.get("FETCH_BALANCE_ASSET", "USDT"),
    "DEFAULT_ORDER_TYPE": os.environ.get("DEFAULT_ORDER_TYPE", "market").lower(),
    "LIMIT_ORDER_SELECTION_TYPE": os.environ.get(
        "LIMIT_ORDER_SELECTION_TYPE", "interactive",
    ).lower(),
    "BYBIT_LEVERAGE_DEFAULT": int(os.environ.get("BYBIT_LEVERAGE_DEFAULT", "10")),
    "EMAIL_ALERTS": os.environ.get("EMAIL_ALERTS", "False").lower() == "true",
    "TELEGRAM_ALERTS": os.environ.get("TELEGRAM_ALERTS", "False").lower() == "true",
    "WEBHOOK_ALERTS": os.environ.get("WEBHOOK_ALERTS", "False").lower() == "true",
    "SMTP_SERVER": os.environ.get("SMTP_SERVER"),
    "SMTP_PORT": int(os.environ.get("SMTP_PORT", 587)),
    "SENDER_EMAIL": os.environ.get("SENDER_EMAIL"),
    "SENDER_PASSWORD": os.environ.get("SENDER_PASSWORD"),
    "RECIPIENT_EMAIL": os.environ.get("RECIPIENT_EMAIL"),
    "TELEGRAM_BOT_TOKEN": os.environ.get("TELEGRAM_BOT_TOKEN"),
    "TELEGRAM_CHAT_ID": os.environ.get("TELEGRAM_CHAT_ID"),
    "WEBHOOK_URL": os.environ.get("WEBHOOK_URL"),
}

FIB_RATIOS = {
    "r3": decimal.Decimal("1.000"),
    "r2": decimal.Decimal("0.618"),
    "r1": decimal.Decimal("0.382"),
    "s1": decimal.Decimal("0.382"),
    "s2": decimal.Decimal("0.618"),
    "s3": decimal.Decimal("1.000"),
}


def print_color(text, color=Fore.WHITE, style=Style.NORMAL, end="\n", **kwargs):
    print(f"{style}{color}{text}{Style.RESET_ALL}", end=end, **kwargs)


def termux_toast(message, duration="short"):
    try:
        safe_message = "".join(
            c for c in str(message) if c.isalnum() or c in " .,!?-:"
        )[:100]
        subprocess.run(
            ["termux-toast", "-d", duration, safe_message],
            check=True,
            capture_output=True,
            timeout=5,
        )
    except FileNotFoundError:
        print_color(
            "# termux-toast not found. Install termux-api?",
            color=Fore.YELLOW,
            style=Style.DIM,
        )
    except Exception as e:
        print_color(f"# Toast error: {e}", color=Fore.YELLOW, style=Style.DIM)


def format_decimal(value, reported_precision, min_display_precision=None):
    if value is None:
        return "N/A"
    if not isinstance(value, decimal.Decimal):
        try:
            value = decimal.Decimal(str(value))
        except:
            return str(value)
    try:
        display_precision = int(reported_precision)
        if min_display_precision is not None:
            display_precision = max(display_precision, int(min_display_precision))
        display_precision = max(display_precision, 0)

        quantizer = decimal.Decimal("1") / (decimal.Decimal("10") ** display_precision)
        rounded_value = value.quantize(quantizer, rounding=decimal.ROUND_HALF_UP)
        formatted_str = str(rounded_value.normalize())

        if "." not in formatted_str and display_precision > 0:
            formatted_str += "." + "0" * display_precision
        elif "." in formatted_str:
            integer_part, decimal_part = formatted_str.split(".")
            if len(decimal_part) < display_precision:
                formatted_str += "0" * (display_precision - len(decimal_part))
        return formatted_str
    except Exception as e:
        print_color(
            f"# FormatDecimal Error ({value}, P:{reported_precision}): {e}",
            color=Fore.YELLOW,
            style=Style.DIM,
        )
        return str(value)


def get_market_info(exchange, symbol):
    try:
        print_color(
            f"{Fore.CYAN}# Querying market runes for {symbol}...",
            style=Style.DIM,
            end="\r",
        )
        if not exchange.markets or symbol not in exchange.markets:
            print_color(
                f"{Fore.CYAN}# Summoning market list...", style=Style.DIM, end="\r",
            )
            exchange.load_markets(True)
        sys.stdout.write("\033[K")
        market = exchange.market(symbol)
        sys.stdout.write("\033[K")

        price_prec_raw = market.get("precision", {}).get("price")
        amount_prec_raw = market.get("precision", {}).get("amount")
        min_amount_raw = market.get("limits", {}).get("amount", {}).get("min")

        price_prec = (
            int(decimal.Decimal(str(price_prec_raw)).log10() * -1)
            if price_prec_raw is not None
            else 8
        )
        amount_prec = (
            int(decimal.Decimal(str(amount_prec_raw)).log10() * -1)
            if amount_prec_raw is not None
            else 8
        )
        min_amount = (
            decimal.Decimal(str(min_amount_raw))
            if min_amount_raw is not None
            else decimal.Decimal("0")
        )

        price_tick_size = (
            decimal.Decimal("1") / (decimal.Decimal("10") ** price_prec)
            if price_prec >= 0
            else decimal.Decimal("1")
        )
        amount_step = (
            decimal.Decimal("1") / (decimal.Decimal("10") ** amount_prec)
            if amount_prec >= 0
            else decimal.Decimal("1")
        )

        return {
            "price_precision": price_prec,
            "amount_precision": amount_prec,
            "min_amount": min_amount,
            "price_tick_size": price_tick_size,
            "amount_step": amount_step,
            "symbol": symbol,
        }
    except ccxt.BadSymbol:
        sys.stdout.write("\033[K")
        print_color(
            f"Symbol '{symbol}' is not found on the exchange.",
            color=Fore.RED,
            style=Style.BRIGHT,
        )
        return None
    except ccxt.NetworkError as e:
        sys.stdout.write("\033[K")
        print_color(f"Network error fetching market info: {e}", color=Fore.YELLOW)
        return None
    except Exception as e:
        sys.stdout.write("\033[K")
        print_color(f"Error fetching market info for {symbol}: {e}", color=Fore.RED)
        return None


def calculate_sma(closes, period):
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def calculate_ema(closes, period):
    if len(closes) < period:
        return None
    ema = closes
    multiplier = decimal.Decimal(2) / (period + 1)
    for i in range(1, len(closes)):
        ema = (closes * multiplier) + (ema * (1 - multiplier))
    return ema


def calculate_momentum(closes, period):
    if len(closes) <= period:
        return None
    return (closes[-1] - closes[-period]).quantize(decimal.Decimal("0.00"))


def calculate_rsi(closes, period):
    if len(closes) < period + 1:
        return None
    gains = [
        max(decimal.Decimal("0"), closes[i] - closes[i - 1])
        for i in range(1, len(closes))
    ]
    losses = [
        max(decimal.Decimal("0"), closes[i - 1] - closes[i])
        for i in range(1, len(closes))
    ]

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return decimal.Decimal("100")
    rs = avg_gain / avg_loss
    rsi = decimal.Decimal("100") - (
        decimal.Decimal("100") / (decimal.Decimal("1") + rs)
    )
    return rsi.quantize(decimal.Decimal("0.00"))


def calculate_stoch_rsi(rsi_values, k_period, d_period):
    if len(rsi_values) < max(k_period, d_period):
        return None
    lowest_rsi = min(rsi_values[-k_period:])
    highest_rsi = max(rsi_values[-k_period:])

    if (highest_rsi - lowest_rsi) == 0:
        return decimal.Decimal("0")

    stoch_rsi_k = (
        (rsi_values[-1] - lowest_rsi) / (highest_rsi - lowest_rsi)
    ) * decimal.Decimal("100")

    stoch_rsi_d = stoch_rsi_k
    stoch_rsi_d_list = []

    for i in range(k_period - 1, len(rsi_values)):
        lowest = min(rsi_values[i - k_period + 1 : i + 1])
        highest = max(rsi_values[i - k_period + 1 : i + 1])
        if highest - lowest == 0:
            stoch_rsi_d_list.append(decimal.Decimal("0"))
        else:
            stoch_rsi_d_list.append(
                ((rsi_values[i] - lowest) / (highest - lowest)) * decimal.Decimal("100"),
            )

    if len(stoch_rsi_d_list) < d_period:
        return None, None
    stoch_rsi_d = sum(stoch_rsi_d_list[-d_period:]) / d_period

    return stoch_rsi_k.quantize(decimal.Decimal("0.00")), stoch_rsi_d.quantize(
        decimal.Decimal("0.00"),
    )


def calculate_fibonacci_pivots(high, low, close, timeframe):
    pivot = (high + low + close) / decimal.Decimal("3")
    r1 = (pivot * decimal.Decimal("2")) - low
    s1 = (pivot * decimal.Decimal("2")) - high
    r2 = pivot + (high - low)
    s2 = pivot - (high - low)
    r3 = r1 + (high - low)
    s3 = s1 - (high - low)
    return {"pivot": pivot, "r1": r1, "s1": s1, "r2": r2, "s2": s2, "r3": r3, "s3": s3}


def fetch_market_data(exchange, symbol, config):
    results = {
        "ticker": None,
        "indicator_ohlcv": None,
        "pivot_ohlcv": None,
        "positions": [],
        "balance": None,
        "open_orders": [],
        "account": None,
    }
    error_occurred = False
    rate_limit_wait = config["RETRY_DELAY_RATE_LIMIT"]
    network_wait = config["RETRY_DELAY_NETWORK_ERROR"]

    indicator_history_needed = (
        max(
            config["SMA_PERIOD"],
            config["SMA2_PERIOD"],
            config["EMA1_PERIOD"],
            config["EMA2_PERIOD"],
            config["MOMENTUM_PERIOD"] + 1,
            config["RSI_PERIOD"] + config["STOCH_K_PERIOD"] + config["STOCH_D_PERIOD"],
        )
        + 5
    )

    api_calls = [
        {"func": exchange.fetch_ticker, "args": [symbol], "desc": "ticker"},
        {
            "func": exchange.fetch_ohlcv,
            "args": [
                symbol,
                config["INDICATOR_TIMEFRAME"],
                None,
                indicator_history_needed,
            ],
            "desc": "Indicator OHLCV",
        },
        {
            "func": exchange.fetch_ohlcv,
            "args": [symbol, config["PIVOT_TIMEFRAME"], None, 2],
            "desc": "Pivot OHLCV",
        },
        {"func": exchange.fetch_positions, "args": [[symbol]], "desc": "positions"},
        {"func": exchange.fetch_balance, "args": [], "desc": "balance"},
        {"func": exchange.fetch_open_orders, "args": [symbol], "desc": "open_orders"},
        {"func": exchange.fetch_account_configuration, "args": [], "desc": "account"},
    ]

    print_color(
        f"{Fore.CYAN}# Contacting exchange spirits...", style=Style.DIM, end="\r",
    )
    for call in api_calls:
        try:
            data = call["func"](*call["args"])
            if call["desc"] == "positions":
                results[call["desc"]] = [
                    p
                    for p in data
                    if p.get("symbol") == symbol
                    and decimal.Decimal(str(p.get("contracts", "0"))) != 0
                ]
            elif call["desc"] == "balance":
                results[call["desc"]] = data.get("total", {}).get(
                    config["FETCH_BALANCE_ASSET"],
                )
            elif call["desc"] == "open_orders" or call["desc"] == "account":
                results[call["desc"]] = data
            else:
                results[call["desc"]] = data
            time.sleep(exchange.rateLimit / 1000)

        except ccxt.RateLimitExceeded:
            print_color(
                f"Rate Limit ({call['desc']}). Pausing {rate_limit_wait}s.",
                color=Fore.YELLOW,
                style=Style.DIM,
            )
            time.sleep(rate_limit_wait)
            error_occurred = True
            break
        except ccxt.NetworkError:
            print_color(
                f"Network Error ({call['desc']}). Pausing {network_wait}s.",
                color=Fore.YELLOW,
                style=Style.DIM,
            )
            time.sleep(network_wait)
            error_occurred = True
        except ccxt.AuthenticationError as e:
            print_color(
                f"Authentication Error ({call['desc']}). Check API Keys!",
                color=Fore.RED,
                style=Style.BRIGHT,
            )
            error_occurred = True
            raise e
        except Exception as e:
            print_color(
                f"Error fetching {call['desc']}: {e}", color=Fore.RED, style=Style.DIM,
            )
            error_occurred = True

    sys.stdout.write("\033[K")
    return results, error_occurred


def analyze_orderbook_volume(exchange, symbol, market_info, config):
    try:
        orderbook = exchange.fetch_order_book(
            symbol, limit=config["MAX_ORDERBOOK_DEPTH_DISPLAY"],
        )
        bids = orderbook["bids"]
        asks = orderbook["asks"]

        bid_map = []
        ask_map = []
        total_bid_vol = decimal.Decimal("0")
        total_ask_vol = decimal.Decimal("0")

        for price, amount in bids:
            price_d = decimal.Decimal(str(price))
            amount_d = decimal.Decimal(str(amount))
            total_bid_vol += amount_d
            bid_map.append(
                {"price": price_d, "amount": amount_d, "cumulative_vol": total_bid_vol},
            )

        for price, amount in asks:
            price_d = decimal.Decimal(str(price))
            amount_d = decimal.Decimal(str(amount))
            total_ask_vol += amount_d
            ask_map.append(
                {"price": price_d, "amount": amount_d, "cumulative_vol": total_ask_vol},
            )

        return {
            "bids": bid_map,
            "asks": ask_map,
            "timestamp": exchange.iso8601(exchange.milliseconds()),
        }, False
    except Exception as e:
        print_color(f"Error fetching order book: {e}", color=Fore.RED)
        return {"bids": [], "asks": [], "timestamp": None}, True


def display_header(symbol, timestamp, balance, config):
    print(
        f"{Fore.CYAN}{Style.BRIGHT}╔═══════════════════════════════════════════════════════════════════════════════════╗",
    )
    print(
        f"║ {Style.BRIGHT}{symbol.upper():<20}{Style.RESET_ALL}{Fore.CYAN}{Style.BRIGHT}│ {timestamp:<40} {Style.RESET_ALL}{Fore.CYAN}{Style.BRIGHT}│ Balance ({config['FETCH_BALANCE_ASSET']}): {Fore.GREEN}{format_decimal(balance, config['BALANCE_DISPLAY_PRECISION']):<10}{Style.RESET_ALL}{Fore.CYAN}{Style.BRIGHT} ║",
    )
    print(
        f"╚═══════════════════════════════════════════════════════════════════════════════════╝{Style.RESET_ALL}",
    )


def display_ticker_and_trend(ticker_info, indicators_info, config, market_info):
    price_prec = market_info["price_precision"]
    min_disp_prec = config["MIN_PRICE_DISPLAY_PRECISION"]

    last_price = (
        decimal.Decimal(str(ticker_info["last"]))
        if ticker_info
        else decimal.Decimal("0")
    )
    price_change = (
        decimal.Decimal(str(ticker_info["percentage"]))
        if ticker_info and "percentage" in ticker_info
        else decimal.Decimal("0")
    )

    price_color = (
        Fore.GREEN if price_change > 0 else Fore.RED if price_change < 0 else Fore.WHITE
    )

    trend_color = Fore.WHITE
    if (
        indicators_info["sma9"]
        and indicators_info["sma20"]
        and indicators_info["ema12"]
        and indicators_info["ema34"]
    ):
        if last_price > indicators_info["ema12"] > indicators_info["ema34"]:
            trend_color = Fore.GREEN
        elif last_price < indicators_info["ema12"] < indicators_info["ema34"]:
            trend_color = Fore.RED

    print_color(
        f"  Last: {price_color}{format_decimal(last_price, price_prec, min_disp_prec)}{Style.RESET_ALL} | 24h Change: {price_color}{price_change:+.2f}%{Style.RESET_ALL}",
        end="",
    )
    print_color(
        f" | Trend: {trend_color}{'Up' if trend_color == Fore.GREEN else 'Down' if trend_color == Fore.RED else 'Neutral'}{Style.RESET_ALL}",
    )
    return last_price


def display_indicators(indicators_info, config, market_info, last_price):
    price_prec = market_info["price_precision"]
    min_disp_prec = config["MIN_PRICE_DISPLAY_PRECISION"]
    stoch_rsi_prec = config["STOCH_RSI_DISPLAY_PRECISION"]

    print_color(
        "  SMA9: {} | SMA20: {}".format(
            format_decimal(indicators_info["sma9"], price_prec, min_disp_prec),
            format_decimal(indicators_info["sma20"], price_prec, min_disp_prec),
        ),
        end=" ",
    )
    print_color(
        " | EMA12: {} | EMA34: {}".format(
            format_decimal(indicators_info["ema12"], price_prec, min_disp_prec),
            format_decimal(indicators_info["ema34"], price_prec, min_disp_prec),
        ),
    )

    print_color(
        "  Momentum: {} | RSI: {}".format(
            format_decimal(indicators_info["momentum"], 2),
            format_decimal(indicators_info["rsi"], 2),
        ),
        end=" ",
    )

    stoch_rsi_k = indicators_info["stoch_rsi_k"]
    stoch_rsi_d = indicators_info["stoch_rsi_d"]

    stoch_k_color = Fore.WHITE
    if stoch_rsi_k is not None:
        if stoch_rsi_k < CONFIG["STOCH_RSI_OVERSOLD"]:
            stoch_k_color = Fore.GREEN
        elif stoch_rsi_k > CONFIG["STOCH_RSI_OVERBOUGHT"]:
            stoch_k_color = Fore.RED

    stoch_d_color = Fore.WHITE
    if stoch_rsi_d is not None:
        if stoch_rsi_d < CONFIG["STOCH_RSI_OVERSOLD"]:
            stoch_d_color = Fore.GREEN
        elif stoch_rsi_d > CONFIG["STOCH_RSI_OVERBOUGHT"]:
            stoch_d_color = Fore.RED

    print_color(
        f" | Stoch-RSI: {stoch_k_color}{format_decimal(stoch_rsi_k, stoch_rsi_prec)}{Style.RESET_ALL} / {stoch_d_color}{format_decimal(stoch_rsi_d, stoch_rsi_prec)}{Style.RESET_ALL}",
    )


def display_position(position_info, ticker_info, market_info, config):
    pnl_prec = config["PNL_PRECISION"]
    price_prec = market_info["price_precision"]
    amount_prec = market_info["amount_precision"]
    min_disp_prec = config["MIN_PRICE_DISPLAY_PRECISION"]
    pnl_str = f"{Fore.LIGHTBLACK_EX}Position: None or Fetch Failed{Style.RESET_ALL}"

    if position_info.get("has_position"):
        pos = position_info["position"]
        side = pos.get("side", "N/A").capitalize()
        size_str = pos.get("contracts", "0")
        entry_price_str = pos.get("entryPrice", "0")
        liq_price = format_decimal(
            pos.get("liquidationPrice", "N/A"), price_prec, min_disp_prec,
        )
        mark_price = format_decimal(
            pos.get("markPrice", "N/A"), price_prec, min_disp_prec,
        )
        leverage = pos.get("leverage", "N/A")
        quote_asset = pos.get("quoteAsset", config["FETCH_BALANCE_ASSET"])
        pnl_val = position_info.get("unrealizedPnl")

        try:
            size = decimal.Decimal(size_str)
            entry_price = decimal.Decimal(entry_price_str)
            size_fmt = format_decimal(size, amount_prec)
            entry_fmt = format_decimal(entry_price, price_prec, min_disp_prec)
            side_color = (
                Fore.GREEN
                if side.lower() == "long"
                else Fore.RED
                if side.lower() == "short"
                else Fore.WHITE
            )

            if pnl_val is None and ticker_info and ticker_info.get("last") is not None:
                last_price_for_pnl = decimal.Decimal(str(ticker_info["last"]))
                if side.lower() == "long":
                    pnl_val = (last_price_for_pnl - entry_price) * size
                else:
                    pnl_val = (entry_price - last_price_for_pnl) * size

            pnl_val_str, pnl_color = "N/A", Fore.WHITE
            if pnl_val is not None:
                pnl_val_str = format_decimal(pnl_val, pnl_prec)
                pnl_color = (
                    Fore.GREEN
                    if pnl_val > 0
                    else Fore.RED
                    if pnl_val < 0
                    else Fore.WHITE
                )

            pnl_str = (
                f"Position: {side_color}{side} {size_fmt}{Style.RESET_ALL} | "
                f"Entry: {Fore.YELLOW}{entry_fmt}{Style.RESET_ALL} | "
                f"Liq: {Fore.YELLOW}{liq_price}{Style.RESET_ALL} | Mark: {Fore.YELLOW}{mark_price}{Style.RESET_ALL} | "
                f"Leverage: {Fore.YELLOW}{leverage}x{Style.RESET_ALL} | "
                f"uPNL: {pnl_color}{pnl_val_str} {quote_asset}{Style.RESET_ALL}"
            )

        except Exception as e:
            pnl_str = (
                f"{Fore.YELLOW}Position: Error parsing data ({e}){Style.RESET_ALL}"
            )

    print_color(f"  {pnl_str}")


def display_pivots(pivots_info, current_price, market_info, config):
    price_prec = market_info["price_precision"]
    min_disp_prec = config["MIN_PRICE_DISPLAY_PRECISION"]

    if not pivots_info:
        print_color("  Pivots: N/A", color=Fore.LIGHTBLACK_EX)
        return

    print_color("  Pivots: ", end="")
    for level_key in ["r3", "r2", "r1", "pivot", "s1", "s2", "s3"]:
        level_value = pivots_info.get(level_key)
        if level_value is None:
            continue

        level_color = Fore.LIGHTBLACK_EX
        if level_key.startswith("r"):
            level_color = Fore.LIGHTRED_EX
        elif level_key.startswith("s"):
            level_color = Fore.LIGHTGREEN_EX
        else:
            level_color = Fore.CYAN

        if current_price and abs(
            current_price - level_value,
        ) < current_price * decimal.Decimal("0.0005"):
            level_color = Fore.MAGENTA + Style.BRIGHT

        print_color(
            f"{level_key.upper()}: {level_color}{format_decimal(level_value, price_prec, min_disp_prec)}{Style.RESET_ALL}",
            end=" | ",
        )
    print()


def display_orderbook(analyzed_orderbook, market_info, config):
    price_prec = market_info["price_precision"]
    volume_prec = config["VOLUME_DISPLAY_PRECISION"]
    min_disp_prec = config["MIN_PRICE_DISPLAY_PRECISION"]

    bids = analyzed_orderbook["bids"]
    asks = analyzed_orderbook["asks"]

    max_vol = decimal.Decimal("0")
    for order in bids + asks:
        max_vol = max(max_vol, order["amount"])

    print_color(
        "\n╔═══════════════════════════════════════════════════════════════════════════════════╗",
        color=Fore.BLUE,
    )
    print_color(
        "║                           Order Book Depth & Heatmap                              ║",
        color=Fore.BLUE,
    )
    print_color(
        "╠═══════════════════════════════════════════════════════════════════════════════════╣",
        color=Fore.BLUE,
    )
    print_color(
        "║   Price (ASK)      Volume (ASK)      Cum. Vol. (ASK)   │   Price (BID)      Volume (BID)      Cum. Vol. (BID)   ║",
        color=Fore.BLUE,
    )
    print_color(
        "╠═══════════════════════════════════════════════════════════════════════════════════╣",
        color=Fore.BLUE,
    )

    ask_map = {}
    bid_map = {}

    for i in range(min(len(asks), len(bids), config["MAX_ORDERBOOK_DEPTH_DISPLAY"])):
        ask = asks[i]
        bid = bids[i]

        ask_price_str = format_decimal(ask["price"], price_prec, min_disp_prec)
        ask_vol_str = format_decimal(ask["amount"], volume_prec)
        ask_cum_vol_str = format_decimal(ask["cumulative_vol"], volume_prec)

        bid_price_str = format_decimal(bid["price"], price_prec, min_disp_prec)
        bid_vol_str = format_decimal(bid["amount"], volume_prec)
        bid_cum_vol_str = format_decimal(bid["cumulative_vol"], volume_prec)

        ask_color = Fore.RED + Back.BLACK
        if ask["amount"] >= max_vol * CONFIG["VOLUME_THRESHOLDS"]["high"]:
            ask_color = Fore.BLACK + Back.RED + Style.BRIGHT
        elif ask["amount"] >= max_vol * CONFIG["VOLUME_THRESHOLDS"]["medium"]:
            ask_color = Fore.RED + Back.LIGHTBLACK_EX

        bid_color = Fore.GREEN + Back.BLACK
        if bid["amount"] >= max_vol * CONFIG["VOLUME_THRESHOLDS"]["high"]:
            bid_color = Fore.BLACK + Back.GREEN + Style.BRIGHT
        elif bid["amount"] >= max_vol * CONFIG["VOLUME_THRESHOLDS"]["medium"]:
            bid_color = Fore.GREEN + Back.LIGHTBLACK_EX

        print_color(
            f"║ {ask_color}{ask_price_str:<15}{Style.RESET_ALL}{Fore.RED}{ask_vol_str:<18}{Style.RESET_ALL}{Fore.LIGHTRED_EX}{ask_cum_vol_str:<18}{Style.RESET_ALL}{Fore.BLUE}│{Style.RESET_ALL} {bid_color}{bid_price_str:<15}{Style.RESET_ALL}{Fore.GREEN}{bid_vol_str:<18}{Style.RESET_ALL}{Fore.LIGHTGREEN_EX}{bid_cum_vol_str:<18}{Style.RESET_ALL}{Fore.BLUE}║",
        )

        ask_map[f"A{i + 1}"] = ask["price"]
        bid_map[f"B{i + 1}"] = bid["price"]

    print_color(
        "╚═══════════════════════════════════════════════════════════════════════════════════╝",
        color=Fore.BLUE,
    )
    return ask_map, bid_map


def display_volume_analysis(analyzed_orderbook, market_info, config):
    bids = analyzed_orderbook["bids"]
    asks = analyzed_orderbook["asks"]

    total_bid_vol = decimal.Decimal("0")
    total_ask_vol = decimal.Decimal("0")

    if bids:
        total_bid_vol = bids[-1]["cumulative_vol"]
    if asks:
        total_ask_vol = asks[-1]["cumulative_vol"]

    total_market_vol = total_bid_vol + total_ask_vol

    if total_market_vol == 0:
        print_color("  Volume Analysis: N/A", color=Fore.LIGHTBLACK_EX)
        return

    bid_percentage = (total_bid_vol / total_market_vol) * 100
    ask_percentage = (total_ask_vol / total_market_vol) * 100

    vol_diff = bid_percentage - ask_percentage

    vol_color = (
        Fore.GREEN if vol_diff > 0 else Fore.RED if vol_diff < 0 else Fore.YELLOW
    )

    print_color(
        f"  Volume Analysis: Bid {Fore.GREEN}{bid_percentage:.1f}%{Style.RESET_ALL} | Ask {Fore.RED}{ask_percentage:.1f}%{Style.RESET_ALL} | Bias: {vol_color}{vol_diff:.1f}%{Style.RESET_ALL}",
    )


def display_open_orders(open_orders):
    print_color("\n--- Open Orders ---", color=Fore.BLUE)
    if not open_orders:
        print_color("  No open orders.", color=Fore.YELLOW)
        return
    for idx, order in enumerate(open_orders, 1):
        order_id = order.get("id", "N/A")
        side = order.get("side", "N/A").upper()
        side_color = Fore.GREEN if side == "BUY" else Fore.RED
        amount = format_decimal(order.get("amount", 0), 4)
        price = format_decimal(order.get("price", 0), 4)
        print_color(
            f"  [{idx}] ID: {order_id} | {side_color}{side}{Style.RESET_ALL} {amount} @ {price} | Type: {order.get('type')}",
        )


def display_account_info(account_data, balance_info, config):
    print_color("\n--- Account Info ---", color=Fore.BLUE)
    equity = format_decimal(
        account_data.get("equity", "N/A"), config["BALANCE_DISPLAY_PRECISION"],
    )
    margin = format_decimal(
        account_data.get("availableMargin", "N/A"), config["BALANCE_DISPLAY_PRECISION"],
    )
    risk_rate = format_decimal(account_data.get("riskRate", "N/A"), 2)
    leverage = account_data.get("leverage", "N/A")
    print_color(
        f"  Equity: {Fore.GREEN}{equity}{Style.RESET_ALL} | Available Margin: {Fore.GREEN}{margin}{Style.RESET_ALL}",
    )
    print_color(
        f"  Risk Rate: {Fore.YELLOW}{risk_rate}{Style.RESET_ALL} | Leverage: {Fore.YELLOW}{leverage}x{Style.RESET_ALL}",
    )
    balance_str = (
        format_decimal(balance_info, config["BALANCE_DISPLAY_PRECISION"])
        if balance_info
        else "N/A"
    )
    print_color(
        f"  Wallet Balance ({config['FETCH_BALANCE_ASSET']}): {Fore.GREEN}{balance_str}{Style.RESET_ALL}",
    )


def display_combined_analysis(analysis_data, market_info, config):
    analyzed_orderbook = analysis_data["orderbook"]
    ticker_info = analysis_data["ticker"]
    indicators_info = analysis_data["indicators"]
    position_info = analysis_data["position"]
    pivots_info = analysis_data["pivots"]
    balance_info = analysis_data["balance"]
    open_orders = analysis_data.get("open_orders", [])
    account_info = analysis_data.get("account", {})
    timestamp = analysis_data.get(
        "timestamp", exchange.iso8601(exchange.milliseconds()),
    )

    symbol = market_info["symbol"]

    sys.stdout.write("\033[H\033[J")

    display_header(symbol, timestamp, balance_info, config)
    last_price = display_ticker_and_trend(
        ticker_info, indicators_info, config, market_info,
    )
    display_indicators(indicators_info, config, market_info, last_price)
    display_position(position_info, ticker_info, market_info, config)
    display_pivots(pivots_info, last_price, market_info, config)
    ask_map, bid_map = display_orderbook(analyzed_orderbook, market_info, config)
    display_volume_analysis(analyzed_orderbook, market_info, config)
    display_open_orders(open_orders)
    display_account_info(account_info, balance_info, config)

    return ask_map, bid_map


def place_market_order(exchange, symbol, side, amount_str, market_info):
    try:
        amount_d = decimal.Decimal(amount_str)
        if amount_d < market_info["min_amount"]:
            print_color(
                f"Error: Amount {amount_d} is below minimum {market_info['min_amount']}",
                color=Fore.RED,
            )
            return

        amount_d = (amount_d // market_info["amount_step"]) * market_info["amount_step"]

        confirm = (
            input(
                f"Confirm {side.upper()} market order for {amount_d} {symbol}? (y/n): ",
            )
            .strip()
            .lower()
        )
        if confirm != "y":
            print_color("Order cancelled.", color=Fore.YELLOW)
            return

        order = exchange.create_market_order(
            symbol, side, float(amount_d), params={"positionIdx": 0},
        )
        print_color(f"Order placed: {order['id']}", color=Fore.GREEN)
        termux_toast(f"Market {side.upper()} {amount_d} on {symbol}", duration="short")
    except Exception as e:
        print_color(f"Error placing market order: {e}", color=Fore.RED)


def place_limit_order(exchange, symbol, side, amount_str, price_str, market_info):
    try:
        amount_d = decimal.Decimal(amount_str)
        price_d = decimal.Decimal(price_str)

        if amount_d < market_info["min_amount"]:
            print_color(
                f"Error: Amount {amount_d} is below minimum {market_info['min_amount']}",
                color=Fore.RED,
            )
            return
        if price_d <= 0:
            print_color("Error: Price must be positive.", color=Fore.RED)
            return

        amount_d = (amount_d // market_info["amount_step"]) * market_info["amount_step"]
        price_d = (price_d // market_info["price_tick_size"]) * market_info[
            "price_tick_size"
        ]

        confirm = (
            input(
                f"Confirm {side.upper()} limit order for {amount_d} {symbol} @ {price_d}? (y/n): ",
            )
            .strip()
            .lower()
        )
        if confirm != "y":
            print_color("Order cancelled.", color=Fore.YELLOW)
            return

        order = exchange.create_limit_order(
            symbol, side, float(amount_d), float(price_d), params={"positionIdx": 0},
        )
        print_color(f"Order placed: {order['id']}", color=Fore.GREEN)
        termux_toast(
            f"Limit {side.upper()} {amount_d} @ {price_d} on {symbol}", duration="short",
        )
    except Exception as e:
        print_color(f"Error placing limit order: {e}", color=Fore.RED)


def close_position(
    exchange, symbol, side, amount_str, market_info, is_market=True, price_str=None,
):
    opposite_side = "sell" if side == "long" else "buy"
    if is_market:
        place_market_order(exchange, symbol, opposite_side, amount_str, market_info)
    else:
        place_limit_order(
            exchange, symbol, opposite_side, amount_str, price_str, market_info,
        )


def manage_close_position(exchange, symbol, positions, market_info):
    if not positions:
        print_color("No positions to close.", color=Fore.YELLOW)
        return
    print_color("\n--- Close Position ---", color=Fore.BLUE)
    for idx, pos in enumerate(positions, 1):
        side = pos.get("side")
        size = format_decimal(pos.get("contracts"), market_info["amount_precision"])
        entry = format_decimal(pos.get("entryPrice"), market_info["price_precision"])
        print_color(f"  [{idx}] {side.upper()} {size} @ {entry}")

    choice = input("Enter index to close (or 'all'): ").strip().lower()
    if choice == "all":
        confirm = (
            input(
                "Are you sure you want to close ALL positions for this symbol? (y/n): ",
            )
            .strip()
            .lower()
        )
        if confirm != "y":
            print_color("Close all cancelled.", color=Fore.YELLOW)
            return
        for pos in positions:
            close_position(
                exchange, symbol, pos["side"], str(pos["contracts"]), market_info,
            )
        print_color("All positions closed.", color=Fore.GREEN)
    else:
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(positions):
                pos = positions[idx]
                available_amount = decimal.Decimal(str(pos["contracts"]))
                amount_input = input(
                    f"Amount to close ({available_amount} available, or 'all'): ",
                ).strip()
                amount_to_close = (
                    available_amount
                    if amount_input.lower() == "all"
                    else decimal.Decimal(amount_input)
                )

                if amount_to_close <= 0 or amount_to_close > available_amount:
                    print_color("Invalid amount.", color=Fore.RED)
                    return

                order_type_input = input("Market or Limit? (m/l): ").strip().lower()

                if order_type_input == "l":
                    price_input = input("Price for limit close: ").strip()
                    close_position(
                        exchange,
                        symbol,
                        pos["side"],
                        str(amount_to_close),
                        market_info,
                        is_market=False,
                        price_str=price_input,
                    )
                elif order_type_input == "m":
                    close_position(
                        exchange,
                        symbol,
                        pos["side"],
                        str(amount_to_close),
                        market_info,
                        is_market=True,
                    )
                else:
                    print_color("Invalid order type.", color=Fore.RED)
            else:
                print_color("Invalid index.", color=Fore.YELLOW)
        except decimal.InvalidOperation:
            print_color("Invalid amount. Enter a number or 'all'.", color=Fore.YELLOW)
        except ValueError:
            print_color("Invalid choice.", color=Fore.YELLOW)
        except Exception as e:
            print_color(f"Error closing position: {e}", color=Fore.RED)


def manage_cancel_order(exchange, symbol, open_orders):
    if not open_orders:
        print_color("No open orders to cancel.", color=Fore.YELLOW)
        return
    print_color("\n--- Cancel Orders ---", color=Fore.BLUE)
    for idx, order in enumerate(open_orders, 1):
        side = order.get("side", "N/A").upper()
        amount = format_decimal(order.get("amount", 0), 4)
        price = format_decimal(order.get("price", 0), 4)
        print_color(f"  [{idx}] ID: {order['id']} | {side} {amount} @ {price}")

    choice = input("Enter index to cancel (or 'all'): ").strip().lower()
    if choice == "all":
        confirm = (
            input(
                "Are you sure you want to cancel ALL open orders for this symbol? (y/n): ",
            )
            .strip()
            .lower()
        )
        if confirm != "y":
            print_color("Cancellation cancelled.", color=Fore.YELLOW)
            return
        try:
            exchange.cancel_all_orders(symbol)
            print_color("All orders cancelled.", color=Fore.GREEN)
            termux_toast(f"All orders on {symbol} cancelled", duration="short")
        except Exception as e:
            print_color(f"Error cancelling all orders: {e}", color=Fore.RED)
    else:
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(open_orders):
                order_id = open_orders[idx]["id"]
                confirm = (
                    input(f"Confirm cancel order {order_id}? (y/n): ").strip().lower()
                )
                if confirm != "y":
                    print_color("Cancellation cancelled.", color=Fore.YELLOW)
                    return
                exchange.cancel_order(order_id, symbol)
                print_color(f"Order {order_id} cancelled.", color=Fore.GREEN)
                termux_toast(f"Order {order_id} cancelled", duration="short")
            else:
                print_color("Invalid index.", color=Fore.YELLOW)
        except ValueError:
            print_color("Invalid choice.", color=Fore.YELLOW)
        except Exception as e:
            print_color(f"Error cancelling order: {e}", color=Fore.RED)


def set_leverage(exchange, symbol, leverage):
    try:
        leverage_int = int(leverage)
        if not 1 <= leverage_int <= 100:  # Example range, check Bybit for actual limits
            print_color(
                "Invalid leverage value. Must be between 1 and 100.", color=Fore.RED,
            )
            return

        confirm = (
            input(f"Confirm set leverage to {leverage_int}x for {symbol}? (y/n): ")
            .strip()
            .lower()
        )
        if confirm != "y":
            print_color("Leverage change cancelled.", color=Fore.YELLOW)
            return

        exchange.set_leverage(leverage_int, symbol)
        print_color(f"Leverage set to {leverage_int}x for {symbol}.", color=Fore.GREEN)
        termux_toast(f"Leverage {leverage_int}x on {symbol}", duration="short")
    except ValueError:
        print_color("Invalid leverage input. Please enter a number.", color=Fore.RED)
    except Exception as e:
        print_color(f"Error setting leverage: {e}", color=Fore.RED)


class RiskManager:
    def __init__(self, max_risk_percent=2, max_positions=3):
        self.max_risk_percent = decimal.Decimal(str(max_risk_percent))
        self.max_positions = max_positions
        self.active_positions = {}

    def calculate_position_size(self, account_balance, entry_price, stop_loss_price):
        risk_amount = account_balance * (self.max_risk_percent / 100)
        price_difference = abs(entry_price - stop_loss_price)

        if price_difference == 0:
            return decimal.Decimal("0")

        position_size = risk_amount / price_difference
        return position_size.quantize(decimal.Decimal("0.001"))

    def auto_stop_loss(self, exchange, symbol, position, atr_multiplier=2):
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, "1h", limit=14)
            atr = self.calculate_atr(ohlcv)

            stop_distance = atr * decimal.Decimal(str(atr_multiplier))

            if position["side"] == "long":
                stop_price = (
                    decimal.Decimal(str(position["entryPrice"])) - stop_distance
                )
                order_side = "sell"
            else:
                stop_price = (
                    decimal.Decimal(str(position["entryPrice"])) + stop_distance
                )
                order_side = "buy"

            order = exchange.create_order(
                symbol=symbol,
                type="stop",
                side=order_side,
                amount=float(position["contracts"]),
                stopPrice=float(stop_price),
                params={"reduceOnly": True},
            )

            return order

        except Exception as e:
            print_color(f"Failed to set stop-loss: {e}", color=Fore.RED)
            return None

    def calculate_atr(self, ohlcv, period=14):
        if len(ohlcv) < period:
            return decimal.Decimal("0")

        tr_values = []
        for i in range(1, len(ohlcv)):
            high = decimal.Decimal(str(ohlcv[i]))
            low = decimal.Decimal(str(ohlcv[i]))
            prev_close = decimal.Decimal(str(ohlcv[i - 1]))

            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_values.append(tr)

        return sum(tr_values[-period:]) / period


class BybitWebSocketManager:
    def __init__(self, symbol, callbacks=None):
        self.symbol = symbol
        self.ws_url = "wss://stream.bybit.com/v5/public/linear"
        self.callbacks = callbacks or {}
        self.running = False
        self.last_price = None
        self.orderbook = {"bids": [], "asks": []}

    async def connect(self):
        async with websockets.connect(self.ws_url) as websocket:
            subscribe_msg = {
                "op": "subscribe",
                "args": [
                    f"orderbook.50.{self.symbol}",
                    f"publicTrade.{self.symbol}",
                    f"tickers.{self.symbol}",
                ],
            }

            await websocket.send(json.dumps(subscribe_msg))
            self.running = True

            while self.running:
                try:
                    message = await websocket.recv()
                    data = json.loads(message)

                    if "topic" in data:
                        await self.handle_message(data)

                except websockets.exceptions.ConnectionClosed:
                    print_color("WebSocket connection closed", color=Fore.YELLOW)
                    break
                except Exception as e:
                    print_color(f"WebSocket error: {e}", color=Fore.RED)

    async def handle_message(self, data):
        topic = data["topic"]

        if "orderbook" in topic:
            self.update_orderbook(data["data"])
            if "orderbook" in self.callbacks:
                self.callbacks["orderbook"](self.orderbook)

        elif "publicTrade" in topic:
            trades = data["data"]
            if trades and "trade" in self.callbacks:
                self.callbacks["trade"](trades)

        elif "tickers" in topic:
            ticker = data["data"]
            if ticker:
                self.last_price = decimal.Decimal(ticker["lastPrice"])
                if "ticker" in self.callbacks:
                    self.callbacks["ticker"](ticker)

    def update_orderbook(self, data):
        if "b" in data:
            self.orderbook["bids"] = [
                {"price": decimal.Decimal(b[0]), "amount": decimal.Decimal(b[1])}
                for b in data["b"][:50]
            ]
        if "a" in data:
            self.orderbook["asks"] = [
                {"price": decimal.Decimal(a[0]), "amount": decimal.Decimal(a[1])}
                for a in data["a"][:50]
            ]

    def start(self):
        def run_async():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.connect())

        thread = Thread(target=run_async, daemon=True)
        thread.start()

    def stop(self):
        self.running = False


class SmartOrderExecutor:
    def __init__(self, exchange, symbol, market_info):
        self.exchange = exchange
        self.symbol = symbol
        self.market_info = market_info

    async def execute_twap(self, side, total_amount, duration_minutes, num_slices=10):
        slice_amount = decimal.Decimal(str(total_amount)) / num_slices
        interval_seconds = (duration_minutes * 60) / num_slices

        executed_orders = []
        total_executed = decimal.Decimal("0")

        print_color(
            f"Starting TWAP execution: {total_amount} over {duration_minutes} minutes",
            color=Fore.CYAN,
        )

        for i in range(num_slices):
            try:
                order = self.exchange.create_order(
                    symbol=self.symbol,
                    type="market",
                    side=side,
                    amount=float(slice_amount),
                )

                executed_orders.append(order)
                total_executed += slice_amount

                print_color(
                    f"TWAP slice {i + 1}/{num_slices} executed: {slice_amount}",
                    color=Fore.GREEN,
                )

                if i < num_slices - 1:
                    await asyncio.sleep(interval_seconds)

            except Exception as e:
                print_color(f"TWAP slice {i + 1} failed: {e}", color=Fore.RED)
                break

        if executed_orders:
            avg_price = (
                sum(
                    decimal.Decimal(str(o["price"])) * decimal.Decimal(str(o["amount"]))
                    for o in executed_orders
                )
                / total_executed
            )

            print_color(
                f"TWAP complete. Avg price: {avg_price}, Total: {total_executed}",
                color=Fore.GREEN,
            )

        return executed_orders

    def create_iceberg_order(self, side, total_amount, visible_amount, price=None):
        remaining = decimal.Decimal(str(total_amount))
        visible = decimal.Decimal(str(visible_amount))
        orders = []

        while remaining > 0:
            current_amount = min(visible, remaining)

            try:
                if price:
                    order = self.exchange.create_limit_order(
                        self.symbol, side, float(current_amount), float(price),
                    )
                else:
                    order = self.exchange.create_market_order(
                        self.symbol, side, float(current_amount),
                    )

                orders.append(order)
                remaining -= current_amount

                time.sleep(self.exchange.rateLimit / 1000)

            except Exception as e:
                print_color(f"Iceberg slice failed: {e}", color=Fore.RED)
                break

        return orders

    def create_conditional_order(self, condition_type, trigger_price, order_params):
        try:
            order = None
            if condition_type == "stop_limit":
                order = self.exchange.create_order(
                    symbol=self.symbol,
                    type="stop_limit",
                    side=order_params["side"],
                    amount=float(order_params["amount"]),
                    price=float(order_params["limit_price"]),
                    stopPrice=float(trigger_price),
                    params={"timeInForce": "GTC"},
                )

            elif condition_type == "take_profit":
                order = self.exchange.create_order(
                    symbol=self.symbol,
                    type="limit",
                    side=order_params["side"],
                    amount=float(order_params["amount"]),
                    price=float(trigger_price),
                    params={"reduceOnly": True},
                )

            return order

        except Exception as e:
            print_color(f"Conditional order failed: {e}", color=Fore.RED)
            return None


class TradingAnalytics:
    def __init__(self):
        self.trades = []
        self.daily_pnl = {}
        self.metrics = {}

    def add_trade(self, trade):
        self.trades.append(
            {
                "timestamp": trade.get("timestamp"),
                "symbol": trade.get("symbol"),
                "side": trade.get("side"),
                "amount": decimal.Decimal(str(trade.get("amount", 0))),
                "entry_price": decimal.Decimal(str(trade.get("price", 0))),
                "exit_price": decimal.Decimal(str(trade.get("exit_price", 0))),
                "pnl": decimal.Decimal(str(trade.get("pnl", 0))),
                "fees": decimal.Decimal(str(trade.get("fee", {}).get("cost", 0))),
            },
        )

    def calculate_metrics(self):
        if not self.trades:
            return None

        total_pnl = sum(t["pnl"] - t["fees"] for t in self.trades)
        winning_trades = [t for t in self.trades if t["pnl"] > 0]
        losing_trades = [t for t in self.trades if t["pnl"] <= 0]

        win_rate = len(winning_trades) / len(self.trades) * 100 if self.trades else 0

        avg_win = (
            sum(t["pnl"] for t in winning_trades) / len(winning_trades)
            if winning_trades
            else 0
        )
        avg_loss = (
            sum(t["pnl"] for t in losing_trades) / len(losing_trades)
            if losing_trades and len(losing_trades) != 0
            else 0
        )

        profit_factor = (
            abs(
                sum(t["pnl"] for t in winning_trades)
                / sum(t["pnl"] for t in losing_trades),
            )
            if losing_trades and sum(t["pnl"] for t in losing_trades) != 0
            else 0
        )

        returns = [float(t["pnl"]) for t in self.trades]
        if len(returns) > 1:
            avg_return = np.mean(returns)
            std_dev = np.std(returns)
            sharpe_ratio = (avg_return / std_dev) * (252**0.5) if std_dev != 0 else 0
        else:
            sharpe_ratio = 0

        self.metrics = {
            "total_trades": len(self.trades),
            "total_pnl": total_pnl,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": self.calculate_max_drawdown(),
        }

        return self.metrics

    def calculate_max_drawdown(self):
        if not self.trades:
            return decimal.Decimal("0")

        cumulative_pnl = []
        running_total = decimal.Decimal("0")

        for trade in self.trades:
            running_total += trade["pnl"] - trade["fees"]
            cumulative_pnl.append(running_total)

        peak = cumulative_pnl[0]
        max_dd = decimal.Decimal("0")

        for value in cumulative_pnl:
            peak = max(peak, value)
            dd = (peak - value) / peak * 100 if peak != 0 else 0
            max_dd = max(max_dd, dd)

        return max_dd

    def display_analytics(self):
        metrics = self.calculate_metrics()
        if not metrics:
            print_color("No trading data available", color=Fore.YELLOW)
            return

        print_color("\n╔══════════════════════════════════════╗", color=Fore.CYAN)
        print_color("║     TRADING PERFORMANCE ANALYTICS    ║", color=Fore.CYAN)
        print_color("╚══════════════════════════════════════╝", color=Fore.CYAN)

        print_color(f"Total Trades: {metrics['total_trades']}", color=Fore.WHITE)

        pnl_color = Fore.GREEN if metrics["total_pnl"] > 0 else Fore.RED
        print_color(
            f"Total P&L: {pnl_color}{metrics['total_pnl']:.2f}{Style.RESET_ALL}",
        )

        print_color(
            f"Win Rate: {Fore.GREEN if metrics['win_rate'] > 50 else Fore.RED}{metrics['win_rate']:.1f}%{Style.RESET_ALL}",
        )
        print_color(f"Profit Factor: {metrics['profit_factor']:.2f}")
        print_color(f"Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
        print_color(
            f"Max Drawdown: {Fore.YELLOW}{metrics['max_drawdown']:.1f}%{Style.RESET_ALL}",
        )


class MultiTimeframeAnalyzer:
    def __init__(self, exchange, symbol):
        self.exchange = exchange
        self.symbol = symbol
        self.timeframes = ["5m", "15m", "1h", "4h", "1d"]
        self.analysis = {}

    def analyze_all_timeframes(self):
        for tf in self.timeframes:
            self.analysis[tf] = self.analyze_timeframe(tf)

        return self.get_confluence_signal()

    def analyze_timeframe(self, timeframe):
        try:
            ohlcv_data = self.exchange.fetch_ohlcv(self.symbol, timeframe, limit=100)

            if len(ohlcv_data) < 50:
                return None

            closes = [decimal.Decimal(str(c[4])) for c in ohlcv_data]

            sma_20 = sum(closes[-20:]) / 20
            sma_50 = sum(closes[-50:]) / 50

            current_price = closes[-1]

            trend = (
                "bullish"
                if current_price > sma_20 > sma_50
                else "bearish"
                if current_price < sma_20 < sma_50
                else "neutral"
            )

            rsi = calculate_rsi(closes, 14)

            return {
                "trend": trend,
                "rsi": rsi,
                "price_vs_sma20": ((current_price - sma_20) / sma_20 * 100),
            }

        except Exception as e:
            print_color(f"Error analyzing {timeframe}: {e}", color=Fore.RED)
            return None

    def get_confluence_signal(self):
        bullish_count = 0
        bearish_count = 0

        weights = {"5m": 1, "15m": 2, "1h": 3, "4h": 4, "1d": 5}

        for tf, analysis in self.analysis.items():
            if analysis and analysis["trend"] == "bullish":
                bullish_count += weights.get(tf, 1)
            elif analysis and analysis["trend"] == "bearish":
                bearish_count += weights.get(tf, 1)

        total_weight = sum(weights.values())
        bullish_percentage = (bullish_count / total_weight) * 100
        bearish_percentage = (bearish_count / total_weight) * 100

        signal = "NEUTRAL"
        confidence = 50
        if bullish_percentage > 60:
            signal = "STRONG BUY"
            confidence = bullish_percentage
        elif bullish_percentage > 40:
            signal = "BUY"
            confidence = bullish_percentage
        elif bearish_percentage > 60:
            signal = "STRONG SELL"
            confidence = bearish_percentage
        elif bearish_percentage > 40:
            signal = "SELL"
            confidence = bearish_percentage

        return {
            "signal": signal,
            "confidence": confidence,
            "bullish_score": bullish_percentage,
            "bearish_score": bearish_percentage,
            "details": self.analysis,
        }

    def display_mtf_analysis(self):
        result = self.analyze_all_timeframes()

        print_color(
            "\n═══ Multi-Timeframe Analysis ═══", color=Fore.BLUE, style=Style.BRIGHT,
        )

        for tf in self.timeframes:
            if self.analysis.get(tf):
                data = self.analysis[tf]
                trend_color = (
                    Fore.GREEN
                    if data["trend"] == "bullish"
                    else Fore.RED
                    if data["trend"] == "bearish"
                    else Fore.YELLOW
                )

                print_color(
                    f"{tf:>3}: {trend_color}{data['trend']:>8}{Style.RESET_ALL} | "
                    f"RSI: {data['rsi']:.1f}",
                )

        signal_color = (
            Fore.GREEN
            if "BUY" in result["signal"]
            else Fore.RED
            if "SELL" in result["signal"]
            else Fore.YELLOW
        )

        print_color(
            f"\n{signal_color}═══ {result['signal']} ═══{Style.RESET_ALL}",
            style=Style.BRIGHT,
        )
        print_color(f"Confidence: {result['confidence']:.1f}%")


class AlertSystem:
    def __init__(self, config):
        self.email_enabled = config.get("EMAIL_ALERTS", False)
        self.telegram_enabled = config.get("TELEGRAM_ALERTS", False)
        self.webhook_enabled = config.get("WEBHOOK_ALERTS", False)

        self.email_config = {
            "smtp_server": config.get("SMTP_SERVER"),
            "smtp_port": config.get("SMTP_PORT", 587),
            "sender_email": config.get("SENDER_EMAIL"),
            "sender_password": config.get("SENDER_PASSWORD"),
            "recipient_email": config.get("RECIPIENT_EMAIL"),
        }

        self.telegram_config = {
            "bot_token": config.get("TELEGRAM_BOT_TOKEN"),
            "chat_id": config.get("TELEGRAM_CHAT_ID"),
        }

        self.webhook_url = config.get("WEBHOOK_URL")
        self.alert_conditions = {}

    def setup_price_alert(self, symbol, condition, price_level, alert_type="once"):
        alert_id = f"{symbol}_{condition}_{price_level}"

        self.alert_conditions[alert_id] = {
            "symbol": symbol,
            "condition": condition,
            "price_level": decimal.Decimal(str(price_level)),
            "alert_type": alert_type,
            "triggered": False,
            "last_price": None,
            "enabled": True,
        }

        return alert_id

    def check_alerts(self, current_prices):
        triggered_alerts = []

        for alert_id, alert in list(self.alert_conditions.items()):
            if not alert["enabled"]:
                continue

            symbol = alert["symbol"]

            if symbol not in current_prices:
                continue

            current_price = decimal.Decimal(str(current_prices[symbol]))
            last_price = alert["last_price"]

            triggered = False
            message = ""

            if alert["condition"] == "above" and current_price > alert["price_level"]:
                triggered = True
                message = f"Price Alert: {symbol} is above {alert['price_level']} at {current_price}"

            elif alert["condition"] == "below" and current_price < alert["price_level"]:
                triggered = True
                message = f"Price Alert: {symbol} is below {alert['price_level']} at {current_price}"

            elif alert["condition"] == "crosses":
                if last_price is not None:
                    if (last_price <= alert["price_level"] < current_price) or (
                        last_price >= alert["price_level"] > current_price
                    ):
                        triggered = True
                        message = f"Price Alert: {symbol} crossed {alert['price_level']} at {current_price}"

            alert["last_price"] = current_price

            if triggered and (
                not alert["triggered"] or alert["alert_type"] == "continuous"
            ):
                alert["triggered"] = True
                triggered_alerts.append(message)
                self.send_alert(message, priority="high")

                if alert["alert_type"] == "once":
                    alert["enabled"] = False

        return triggered_alerts

    def send_alert(self, message, priority="normal"):
        print_color(f"⚠️ ALERT: {message}", color=Fore.YELLOW, style=Style.BRIGHT)

        if self.email_enabled:
            self.send_email_alert(message, priority)

        if self.telegram_enabled:
            self.send_telegram_alert(message)

        if self.webhook_enabled:
            self.send_webhook_alert(message, priority)

        termux_toast(message, duration="long")

    def send_telegram_alert(self, message):
        try:
            url = f"https://api.telegram.org/bot{self.telegram_config['bot_token']}/sendMessage"
            payload = {
                "chat_id": self.telegram_config["chat_id"],
                "text": message,
                "parse_mode": "HTML",
            }

            response = requests.post(url, json=payload, timeout=5)

            if response.status_code == 200:
                print_color("Telegram alert sent", color=Fore.GREEN, style=Style.DIM)
            else:
                print_color(
                    f"Telegram alert failed: {response.status_code}", color=Fore.RED,
                )

        except Exception as e:
            print_color(f"Telegram error: {e}", color=Fore.RED)

    def send_email_alert(self, message, priority):
        try:
            msg = MIMEMultipart()
            msg["From"] = self.email_config["sender_email"]
            msg["To"] = self.email_config["recipient_email"]
            msg["Subject"] = f"Trading Alert - {priority.upper()}"

            msg.attach(MIMEText(message, "plain"))

            with smtplib.SMTP(
                self.email_config["smtp_server"], self.email_config["smtp_port"],
            ) as server:
                server.starttls()
                server.login(
                    self.email_config["sender_email"],
                    self.email_config["sender_password"],
                )
                server.send_message(msg)

            print_color("Email alert sent", color=Fore.GREEN, style=Style.DIM)

        except Exception as e:
            print_color(f"Email error: {e}", color=Fore.RED)

    def send_webhook_alert(self, message, priority):
        try:
            payload = {
                "content": f"**Bybit Terminal Alert ({priority.upper()})**: {message}",
            }
            response = requests.post(self.webhook_url, json=payload, timeout=5)
            if response.status_code == 204:  # Discord webhook success
                print_color("Webhook alert sent", color=Fore.GREEN, style=Style.DIM)
            else:
                print_color(
                    f"Webhook alert failed: {response.status_code}", color=Fore.RED,
                )
        except Exception as e:
            print_color(f"Webhook error: {e}", color=Fore.RED)


class TradingDatabase:
    def __init__(self, db_path="bybit_trading.db"):
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self.initialize_tables()

    def initialize_tables(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                amount REAL NOT NULL,
                price REAL NOT NULL,
                fee REAL,
                pnl REAL,
                order_id TEXT UNIQUE,
                strategy TEXT
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_data (
                timestamp DATETIME,
                symbol TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                PRIMARY KEY (timestamp, symbol)
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                opened_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                closed_at DATETIME,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL,
                size REAL NOT NULL,
                realized_pnl REAL,
                status TEXT DEFAULT 'open'
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_performance (
                date DATE PRIMARY KEY,
                total_trades INTEGER,
                winning_trades INTEGER,
                losing_trades INTEGER,
                gross_pnl REAL,
                fees REAL,
                net_pnl REAL,
                win_rate REAL,
                average_win REAL,
                average_loss REAL
            )
        """)

        self.conn.commit()

    def record_trade(self, trade_data):
        self.cursor.execute(
            """
            INSERT INTO trades (symbol, side, amount, price, fee, pnl, order_id, strategy)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                trade_data["symbol"],
                float(trade_data["side"]),
                float(trade_data["amount"]),
                float(trade_data["price"]),
                float(trade_data.get("fee", 0)),
                float(trade_data.get("pnl", 0)),
                trade_data.get("order_id"),
                trade_data.get("strategy", "manual"),
            ),
        )
        self.conn.commit()

    def get_historical_performance(self, days=30):
        date_limit = datetime.now() - timedelta(days=days)

        self.cursor.execute(
            """
            SELECT 
                DATE(timestamp) as trading_date,
                COUNT(*) as total_trades,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN pnl <= 0 THEN 1 ELSE 0 END) as losses,
                SUM(pnl) as total_pnl,
                SUM(fee) as total_fees,
                AVG(CASE WHEN pnl > 0 THEN pnl ELSE NULL END) as avg_win,
                AVG(CASE WHEN pnl < 0 THEN pnl ELSE NULL END) as avg_loss
            FROM trades
            WHERE timestamp >= ?
            GROUP BY DATE(timestamp)
            ORDER BY trading_date DESC
        """,
            (date_limit.strftime("%Y-%m-%d %H:%M:%S"),),
        )

        return self.cursor.fetchall()

    def get_best_worst_trades(self, limit=5):
        self.cursor.execute(
            """
            SELECT * FROM trades
            ORDER BY pnl DESC
            LIMIT ?
        """,
            (limit,),
        )
        best_trades = self.cursor.fetchall()

        self.cursor.execute(
            """
            SELECT * FROM trades
            ORDER BY pnl ASC
            LIMIT ?
        """,
            (limit,),
        )
        worst_trades = self.cursor.fetchall()

        return {"best": best_trades, "worst": worst_trades}

    def calculate_monthly_summary(self):
        self.cursor.execute("""
            SELECT 
                strftime('%Y-%m', timestamp) as month,
                COUNT(*) as total_trades,
                SUM(pnl) as total_pnl,
                SUM(fee) as total_fees,
                AVG(pnl) as avg_pnl,
                MAX(pnl) as best_trade,
                MIN(pnl) as worst_trade
            FROM trades
            GROUP BY strftime('%Y-%m', timestamp)
            ORDER BY month DESC
        """)

        return self.cursor.fetchall()


class BacktestEngine:
    def __init__(self, exchange, symbol, strategy_instance):
        self.exchange = exchange
        self.symbol = symbol
        self.strategy = strategy_instance
        self.results = []
        self.initial_balance = decimal.Decimal("10000")

    def run_backtest(self, start_date, end_date, timeframe="1h"):
        print_color(
            f"Starting backtest from {start_date} to {end_date}", color=Fore.CYAN,
        )

        since = self.exchange.parse8601(start_date)
        historical_data = []

        while since < self.exchange.parse8601(end_date):
            try:
                ohlcv_batch = self.exchange.fetch_ohlcv(
                    self.symbol, timeframe, since=since, limit=1000,
                )

                if not ohlcv_batch:
                    break

                historical_data.extend(ohlcv_batch)
                since = ohlcv_batch[-1][0] + 1
                time.sleep(self.exchange.rateLimit / 1000)

            except Exception as e:
                print_color(f"Error fetching historical data: {e}", color=Fore.RED)
                break

        balance = self.initial_balance
        position = None
        trades = []
        equity_curve = [float(self.initial_balance)]

        for i in range(len(historical_data)):
            current_candle = historical_data[i]

            lookback = min(i, 100)
            recent_data = historical_data[max(0, i - lookback) : i + 1]

            signal = self.strategy.generate_signal(recent_data)

            if signal["action"] == "buy" and position is None:
                position = {
                    "entry_price": decimal.Decimal(
                        str(current_candle[4]),
                    ),  # close price
                    "size": balance
                    * decimal.Decimal("0.95")
                    / decimal.Decimal(str(current_candle[4])),
                    "entry_time": current_candle[0],
                }

            elif signal["action"] == "sell" and position is not None:
                exit_price = decimal.Decimal(str(current_candle[4]))
                pnl = (exit_price - position["entry_price"]) * position["size"]
                balance += pnl

                trades.append(
                    {
                        "entry_time": position["entry_time"],
                        "exit_time": current_candle[0],
                        "entry_price": float(position["entry_price"]),
                        "exit_price": float(exit_price),
                        "pnl": float(pnl),
                        "balance": float(balance),
                    },
                )

                position = None

            current_equity = float(balance)
            if position:
                current_equity += float(
                    (decimal.Decimal(str(current_candle[4])) - position["entry_price"])
                    * position["size"],
                )
            equity_curve.append(current_equity)

        if position:
            exit_price = decimal.Decimal(str(historical_data[-1][4]))
            pnl = (exit_price - position["entry_price"]) * position["size"]
            balance += pnl
            trades.append(
                {
                    "entry_time": position["entry_time"],
                    "exit_time": historical_data[-1][0],
                    "entry_price": float(position["entry_price"]),
                    "exit_price": float(exit_price),
                    "pnl": float(pnl),
                    "balance": float(balance),
                },
            )

        self.results = self.calculate_backtest_metrics(trades, balance, equity_curve)
        return self.results

    def calculate_backtest_metrics(self, trades, final_balance, equity_curve):
        if not trades:
            return {
                "total_return": 0,
                "num_trades": 0,
                "win_rate": 0,
                "sharpe_ratio": 0,
                "max_drawdown": 0,
                "final_balance": float(final_balance),
            }

        total_return = (
            (final_balance - self.initial_balance) / self.initial_balance
        ) * 100
        winning_trades = [t for t in trades if t["pnl"] > 0]

        returns = [t["pnl"] / t["entry_price"] for t in trades]

        if len(returns) > 1:
            avg_return = np.mean(returns)
            std_return = np.std(returns)
            sharpe = (avg_return / std_return * (252**0.5)) if std_return > 0 else 0
        else:
            sharpe = 0

        peak_balance = equity_curve[0]
        max_dd = 0

        for bal in equity_curve:
            peak_balance = max(peak_balance, bal)
            dd = ((peak_balance - bal) / peak_balance) * 100
            max_dd = max(max_dd, float(dd))

        return {
            "total_return": float(total_return),
            "final_balance": float(final_balance),
            "num_trades": len(trades),
            "winning_trades": len(winning_trades),
            "win_rate": (len(winning_trades) / len(trades) * 100) if trades else 0,
            "sharpe_ratio": sharpe,
            "max_drawdown": max_dd,
            "trades": trades,
        }

    def display_backtest_results(self):
        if not self.results:
            print_color("No backtest results available", color=Fore.YELLOW)
            return

        print_color("\n╔════════════════════════════════════╗", color=Fore.BLUE)
        print_color("║      BACKTEST RESULTS              ║", color=Fore.BLUE)
        print_color("╚════════════════════════════════════╝", color=Fore.BLUE)

        print_color(f"Initial Balance: ${self.initial_balance}", color=Fore.WHITE)
        print_color(
            f"Final Balance: ${self.results['final_balance']:.2f}", color=Fore.WHITE,
        )

        return_color = Fore.GREEN if self.results["total_return"] > 0 else Fore.RED
        print_color(
            f"Total Return: {return_color}{self.results['total_return']:.2f}%{Style.RESET_ALL}",
        )

        print_color(f"Total Trades: {self.results['num_trades']}")
        print_color(f"Win Rate: {self.results['win_rate']:.1f}%")
        print_color(f"Sharpe Ratio: {self.results['sharpe_ratio']:.2f}")
        print_color(
            f"Max Drawdown: {Fore.YELLOW}{self.results['max_drawdown']:.1f}%{Style.RESET_ALL}",
        )


class OrderBookAnalyzer:
    def __init__(self, depth_levels=20):
        self.depth_levels = depth_levels
        self.historical_imbalances = []

    def calculate_order_flow_imbalance(self, orderbook):
        bids_raw = orderbook.get("bids", [])[: self.depth_levels]
        asks_raw = orderbook.get("asks", [])[: self.depth_levels]

        if not bids_raw or not asks_raw:
            return None

        bids = [
            {"price": decimal.Decimal(str(b[0])), "amount": decimal.Decimal(str(b[1]))}
            for b in bids_raw
        ]
        asks = [
            {"price": decimal.Decimal(str(a[0])), "amount": decimal.Decimal(str(a[1]))}
            for a in asks_raw
        ]

        bid_volume = sum(b["amount"] for b in bids)
        ask_volume = sum(a["amount"] for a in asks)

        total_volume = bid_volume + ask_volume

        if total_volume == 0:
            return None

        imbalance = ((bid_volume - ask_volume) / total_volume) * 100

        best_bid = bids[0]["price"]
        best_ask = asks[0]["price"]
        spread = ((best_ask - best_bid) / best_ask) * 100

        large_orders = self.detect_large_orders(bids, asks)

        support_levels = self.find_support_resistance(bids, "support")
        resistance_levels = self.find_support_resistance(asks, "resistance")

        result = {
            "imbalance": float(imbalance),
            "bid_volume": float(bid_volume),
            "ask_volume": float(ask_volume),
            "spread_percentage": float(spread),
            "large_orders": large_orders,
            "support_levels": support_levels,
            "resistance_levels": resistance_levels,
            "timestamp": time.time(),
        }

        self.historical_imbalances.append(result)

        if len(self.historical_imbalances) > 100:
            self.historical_imbalances.pop(0)

        return result

    def detect_large_orders(self, bids, asks, threshold_multiplier=3):
        all_orders = [(b["price"], b["amount"], "bid") for b in bids] + [
            (a["price"], a["amount"], "ask") for a in asks
        ]

        amounts = [o[1] for o in all_orders]

        if not amounts:
            return []

        avg_amount = sum(amounts) / len(amounts)
        threshold = avg_amount * threshold_multiplier

        large_orders = []
        for price, amount, side in all_orders:
            if amount > threshold:
                large_orders.append(
                    {
                        "price": float(price),
                        "amount": float(amount),
                        "side": side,
                        "size_ratio": float(amount / avg_amount),
                    },
                )

        return sorted(large_orders, key=lambda x: x["amount"], reverse=True)[:5]

    def find_support_resistance(self, orders, level_type, min_cluster_size=3):
        if len(orders) < min_cluster_size:
            return []

        clusters = []
        cluster_threshold = decimal.Decimal("0.001")

        for order in orders:
            price = order["price"]
            amount = order["amount"]

            added_to_cluster = False
            for cluster in clusters:
                cluster_price = cluster["price"]
                if abs(price - cluster_price) / cluster_price < cluster_threshold:
                    cluster["total_amount"] += amount
                    cluster["order_count"] += 1
                    added_to_cluster = True
                    break

            if not added_to_cluster:
                clusters.append(
                    {
                        "price": price,
                        "total_amount": amount,
                        "order_count": 1,
                        "type": level_type,
                    },
                )

        significant_clusters = [
            c for c in clusters if c["order_count"] >= min_cluster_size
        ]

        significant_clusters.sort(key=lambda x: x["total_amount"], reverse=True)

        return [
            {
                "price": float(c["price"]),
                "strength": float(c["total_amount"]),
                "orders": c["order_count"],
            }
            for c in significant_clusters[:3]
        ]

    def get_market_microstructure(self):
        if len(self.historical_imbalances) < 10:
            return None

        recent_imbalances = [h["imbalance"] for h in self.historical_imbalances[-10:]]

        imbalance_trend = (
            "buying"
            if sum(recent_imbalances) > 20
            else "selling"
            if sum(recent_imbalances) < -20
            else "neutral"
        )

        avg_imbalance = sum(recent_imbalances) / len(recent_imbalances)
        imbalance_volatility = sum(
            abs(i - avg_imbalance) for i in recent_imbalances
        ) / len(recent_imbalances)

        return {
            "trend": imbalance_trend,
            "average_imbalance": avg_imbalance,
            "volatility": imbalance_volatility,
        }


class SimpleStrategy:
    def __init__(self, config):
        self.config = config

    def generate_signal(self, ohlcv_data):
        if len(ohlcv_data) < 30:
            return {"action": "hold", "confidence": 0}

        closes = [decimal.Decimal(str(c[4])) for c in ohlcv_data]

        # Simple SMA Crossover
        sma_fast_period = self.config.get("SMA_PERIOD", 9)
        sma_slow_period = self.config.get("SMA2_PERIOD", 20)

        if len(closes) < sma_slow_period:
            return {"action": "hold", "confidence": 0}

        sma_fast = sum(closes[-sma_fast_period:]) / sma_fast_period
        sma_slow = sum(closes[-sma_slow_period:]) / sma_slow_period

        if sma_fast > sma_slow and closes[-1] > sma_fast:
            return {"action": "buy", "confidence": 0.7}
        if sma_fast < sma_slow and closes[-1] < sma_fast:
            return {"action": "sell", "confidence": 0.7}

        return {"action": "hold", "confidence": 0}


class MLTradingBot:
    def __init__(self, exchange, symbol, model_path="ml_model.joblib"):
        self.exchange = exchange
        self.symbol = symbol
        self.model = self._load_model(model_path)
        self.feature_columns = [
            "sma_fast",
            "sma_slow",
            "rsi",
            "momentum",
        ]  # Example features

    def _load_model(self, path):
        try:
            return joblib.load(path)
        except FileNotFoundError:
            print_color(
                f"ML Model not found at {path}. Please train and save a model.",
                color=Fore.RED,
            )
            return None

    def _prepare_features(self, ohlcv_data):
        if len(ohlcv_data) < 30:
            return None

        closes = [decimal.Decimal(str(c[4])) for c in ohlcv_data]

        # Calculate features (example)
        sma_fast = calculate_sma(closes, CONFIG["SMA_PERIOD"])
        sma_slow = calculate_sma(closes, CONFIG["SMA2_PERIOD"])
        rsi = calculate_rsi(closes, CONFIG["RSI_PERIOD"])
        momentum = calculate_momentum(closes, CONFIG["MOMENTUM_PERIOD"])

        if any(f is None for f in [sma_fast, sma_slow, rsi, momentum]):
            return None

        features = np.array(
            [float(sma_fast), float(sma_slow), float(rsi), float(momentum)],
        ).reshape(1, -1)
        return features

    def generate_ml_signal(self, ohlcv_data):
        if not self.model:
            return {"action": "hold", "confidence": 0, "reason": "No ML model loaded"}

        features = self._prepare_features(ohlcv_data)
        if features is None:
            return {
                "action": "hold",
                "confidence": 0,
                "reason": "Insufficient data for ML features",
            }

        prediction = self.model.predict(features)[0]
        proba = self.model.predict_proba(features)[0]

        if prediction == 1:  # Assuming 1 = buy, 0 = hold, -1 = sell
            return {"action": "buy", "confidence": proba[1], "reason": "ML Buy Signal"}
        if prediction == -1:
            return {
                "action": "sell",
                "confidence": proba[-1],
                "reason": "ML Sell Signal",
            }
        return {"action": "hold", "confidence": proba[0], "reason": "ML Hold Signal"}

    def train_model(self, historical_data_labeled, model_path="ml_model.joblib"):
        print_color(
            "Training ML model (this is a placeholder and requires actual labeled data)...",
            color=Fore.YELLOW,
        )

        X = []
        y = []

        for i in range(len(historical_data_labeled)):
            ohlcv_data = historical_data_labeled[i]["ohlcv"]
            label = historical_data_labeled[i][
                "label"
            ]  # e.g., 1 for buy, -1 for sell, 0 for hold

            features = self._prepare_features(ohlcv_data)
            if features is not None:
                X.append(features.flatten())
                y.append(label)

        if not X:
            print_color("Not enough data to train the model.", color=Fore.RED)
            return

        model = RandomForestClassifier(n_estimators=100, random_state=42)
        model.fit(X, y)
        joblib.dump(model, model_path)
        self.model = model
        print_color(f"ML Model trained and saved to {model_path}", color=Fore.GREEN)


def run_analysis_cycle(exchange, symbol, market_info, config, alert_system=None):
    fetched_data, data_error = fetch_market_data(exchange, symbol, config)
    analyzed_orderbook, orderbook_error = analyze_orderbook_volume(
        exchange, symbol, market_info, config,
    )

    ohlcv_data_indicator = fetched_data.get("indicator_ohlcv")
    ohlcv_data_pivot = fetched_data.get("pivot_ohlcv")

    indicators_info = {
        "sma9": None,
        "sma20": None,
        "ema12": None,
        "ema34": None,
        "momentum": None,
        "rsi": None,
        "stoch_rsi_k": None,
        "stoch_rsi_d": None,
    }
    pivot_info = None

    if ohlcv_data_indicator and len(ohlcv_data_indicator) > max(
        CONFIG["SMA2_PERIOD"], CONFIG["EMA2_PERIOD"],
    ):
        closes = [decimal.Decimal(str(o[4])) for o in ohlcv_data_indicator]
        all_rsi_values = []
        for i in range(len(closes)):
            rsi_val = calculate_rsi(closes[: i + 1], CONFIG["RSI_PERIOD"])
            if rsi_val is not None:
                all_rsi_values.append(rsi_val)

        indicators_info["sma9"] = calculate_sma(closes, CONFIG["SMA_PERIOD"])
        indicators_info["sma20"] = calculate_sma(closes, CONFIG["SMA2_PERIOD"])
        indicators_info["ema12"] = calculate_ema(closes, CONFIG["EMA1_PERIOD"])
        indicators_info["ema34"] = calculate_ema(closes, CONFIG["EMA2_PERIOD"])
        indicators_info["momentum"] = calculate_momentum(
            closes, CONFIG["MOMENTUM_PERIOD"],
        )
        indicators_info["rsi"] = calculate_rsi(closes, CONFIG["RSI_PERIOD"])

        stoch_k, stoch_d = calculate_stoch_rsi(
            all_rsi_values, CONFIG["STOCH_K_PERIOD"], CONFIG["STOCH_D_PERIOD"],
        )
        indicators_info["stoch_rsi_k"] = stoch_k
        indicators_info["stoch_rsi_d"] = stoch_d

    if ohlcv_data_pivot and len(ohlcv_data_pivot) >= 2:
        prev_day_candle = ohlcv_data_pivot[-2]
        pivot_info = calculate_fibonacci_pivots(
            decimal.Decimal(str(prev_day_candle)),
            decimal.Decimal(str(prev_day_candle)),
            decimal.Decimal(str(prev_day_candle)),
            config["PIVOT_TIMEFRAME"],
        )

    position_info = {"has_position": False, "position": None, "unrealizedPnl": None}
    if fetched_data["positions"]:
        position_info["has_position"] = True
        position_info["position"] = fetched_data["positions"]

        # Calculate PnL for display if not provided by exchange
        if fetched_data["ticker"] and fetched_data["ticker"].get("last"):
            current_last_price = decimal.Decimal(str(fetched_data["ticker"]["last"]))
            position = fetched_data["positions"]
            entry_price = decimal.Decimal(str(position.get("entryPrice", "0")))
            contracts = decimal.Decimal(str(position.get("contracts", "0")))

            if position.get("side") == "long":
                position_info["unrealizedPnl"] = (
                    current_last_price - entry_price
                ) * contracts
            elif position.get("side") == "short":
                position_info["unrealizedPnl"] = (
                    entry_price - current_last_price
                ) * contracts

    analysis_data = {
        "ticker": fetched_data.get("ticker"),
        "indicators": indicators_info,
        "pivots": pivot_info,
        "position": position_info,
        "balance": fetched_data.get("balance"),
        "orderbook": analyzed_orderbook,
        "open_orders": fetched_data.get("open_orders"),
        "account": fetched_data.get("account"),
        "timestamp": analyzed_orderbook["timestamp"]
        if analyzed_orderbook
        else exchange.iso8601(exchange.milliseconds()),
    }

    ask_map, bid_map = display_combined_analysis(analysis_data, market_info, config)

    if alert_system and fetched_data["ticker"] and fetched_data["ticker"].get("last"):
        current_prices = {symbol: fetched_data["ticker"]["last"]}
        alert_system.check_alerts(current_prices)

    return (
        not data_error,
        ask_map,
        bid_map,
        fetched_data["positions"],
        fetched_data["open_orders"],
        fetched_data,
    )


def main():
    if not CONFIG["API_KEY"] or not CONFIG["API_SECRET"]:
        print_color(
            "API Key or Secret not found in .env. Exiting.",
            color=Fore.RED,
            style=Style.BRIGHT,
        )
        sys.exit(1)

    exchange_config = {
        "apiKey": CONFIG["API_KEY"],
        "secret": CONFIG["API_SECRET"],
        "enableRateLimit": True,
        "options": {
            "defaultType": CONFIG["DEFAULT_EXCHANGE_TYPE"],
            "recvWindow": 10000,
            "warnOnFetchOHLCVLimitArgument": False,
        },
    }

    # Enable testnet if specific variable is set (e.g. BYBIT_TESTNET=true in .env)
    if os.environ.get("BYBIT_TESTNET", "false").lower() == "true":
        print_color(f"{Fore.YELLOW}Connecting to Bybit Testnet...{Style.RESET_ALL}")
        exchange_config["options"]["defaultType"] = (
            "future"  # Testnet might need 'future'
        )
        exchange_config["urls"] = {
            "api": {
                "public": "https://api-testnet.bybit.com",
                "private": "https://api-testnet.bybit.com",
            },
        }

    exchange = ccxt.bybit(exchange_config)

    symbol = CONFIG["SYMBOL"]
    market_info = get_market_info(exchange, symbol)
    if not market_info:
        while True:
            new_symbol = input("Enter a valid symbol (e.g., BTCUSDT): ").strip().upper()
            market_info = get_market_info(exchange, new_symbol)
            if market_info:
                symbol = new_symbol
                CONFIG["SYMBOL"] = new_symbol
                break
            print_color(f"Symbol {new_symbol} not found. Try again.", color=Fore.YELLOW)

    alert_system = AlertSystem(CONFIG)

    # Example: Set up an alert
    # alert_system.setup_price_alert(symbol, 'above', 70000, 'once')
    # alert_system.setup_price_alert(symbol, 'below', 60000, 'once')
    # alert_system.setup_price_alert(symbol, 'crosses', 65000, 'continuous')

    # Initialize components for new features
    # risk_manager = RiskManager()
    # ws_manager = BybitWebSocketManager(symbol)
    # ws_manager.start() # Start WebSocket in a new thread
    # smart_executor = SmartOrderExecutor(exchange, symbol, market_info)
    # analytics = TradingAnalytics()
    # mtf_analyzer = MultiTimeframeAnalyzer(exchange, symbol)
    # orderbook_analyzer = OrderBookAnalyzer()
    # backtest_strategy = SimpleStrategy(CONFIG) # or MLTradingBot
    # backtest_engine = BacktestEngine(exchange, symbol, backtest_strategy)
    # ml_bot = MLTradingBot(exchange, symbol)

    while True:
        cycle_successful, ask_map, bid_map, positions, open_orders, fetched_data = (
            run_analysis_cycle(exchange, symbol, market_info, CONFIG, alert_system)
        )

        if cycle_successful:
            action = (
                input(
                    f"\n{Style.BRIGHT}{Fore.BLUE}Action (refresh/buy/sell/close/orders/cancel/account/leverage/alert/backtest/exit): {Style.RESET_ALL}",
                )
                .strip()
                .lower()
            )

            if action in ["buy", "sell"]:
                side = action
                order_type = CONFIG["DEFAULT_ORDER_TYPE"]

                amount_str = input(f"Enter quantity to {side}: ").strip()

                if order_type == "market":
                    place_market_order(exchange, symbol, side, amount_str, market_info)
                elif CONFIG["LIMIT_ORDER_SELECTION_TYPE"] == "interactive":
                    print_color(
                        f"\nSelect a price level for {side.upper()}:", color=Fore.CYAN,
                    )
                    if side == "buy":
                        price_choice = (
                            input(
                                "Choose BID level (e.g., B1, B5) or type price manually: ",
                            )
                            .strip()
                            .upper()
                        )
                        price_val = bid_map.get(price_choice)
                    else:
                        price_choice = (
                            input(
                                "Choose ASK level (e.g., A1, A5) or type price manually: ",
                            )
                            .strip()
                            .upper()
                        )
                        price_val = ask_map.get(price_choice)

                    if price_val:
                        place_limit_order(
                            exchange,
                            symbol,
                            side,
                            amount_str,
                            str(price_val),
                            market_info,
                        )
                    else:
                        price_str = (
                            price_choice  # Assume it's a manual price if not a map key
                        )
                        try:
                            decimal.Decimal(price_str)  # Validate it's a number
                            place_limit_order(
                                exchange,
                                symbol,
                                side,
                                amount_str,
                                price_str,
                                market_info,
                            )
                        except decimal.InvalidOperation:
                            print_color(
                                "Invalid price selection. Please enter A1/B1 or a numerical price.",
                                color=Fore.RED,
                            )
                else:  # manual limit entry
                    price_str = input(f"Enter limit price for {side}: ").strip()
                    place_limit_order(
                        exchange, symbol, side, amount_str, price_str, market_info,
                    )

            elif action == "close":
                manage_close_position(exchange, symbol, positions, market_info)
            elif action == "orders":
                display_open_orders(open_orders)
            elif action == "cancel":
                manage_cancel_order(exchange, symbol, open_orders)
            elif action == "account":
                display_account_info(
                    fetched_data["account"], fetched_data["balance"], CONFIG,
                )
            elif action == "leverage":
                lev = input("Enter leverage (e.g., 10): ").strip()
                set_leverage(exchange, symbol, lev)
            elif action == "alert":
                price_level = input("Enter price for alert: ").strip()
                condition = input("Condition (above/below/crosses): ").strip().lower()
                alert_system.setup_price_alert(symbol, condition, price_level)
                print_color(
                    f"Alert set for {symbol} {condition} {price_level}",
                    color=Fore.GREEN,
                )
            elif action == "backtest":
                start_date = input("Enter start date (YYYY-MM-DD): ").strip()
                end_date = input("Enter end date (YYYY-MM-DD): ").strip()
                # backtest_engine.run_backtest(start_date, end_date)
                # backtest_engine.display_backtest_results()
                print_color(
                    "Backtesting feature is currently commented out. Uncomment to use.",
                    color=Fore.YELLOW,
                )
            elif action == "refresh" or action == "":
                pass
            elif action == "exit":
                break
            else:
                print_color("Unknown command.", color=Fore.YELLOW)

        time.sleep(CONFIG["REFRESH_INTERVAL"])


if __name__ == "__main__":
    main()
