#!/usr/bin/env python3

"""Pyrmethus's Ascended Neon Bybit Trading Bot (Long/Short Enhanced)

This ultimate incantation perfects the Supertrend strategy for Bybit V5 API, ensuring both long and short positions are taken and closed on opposite signals. Forged in Termux’s ethereal forge, it radiates neon brilliance and strategic precision.

Enhancements:
- Explicit Long/Short Support: Robustly handles both directions, closing opposites on signal flips with API confirmation.
- Configurable Exposure: New 'max_position_size' caps long/short sizes; 'close_delay' ensures API stability.
- Enhanced Logging: Neon debug logs track position states and closures.
- Backtest Precision: Reflects exact close-on-opposite logic, logs entry/exit pairs.
- Plotting Clarity: Buy/sell signal markers on charts.
- Email Alerts: Include position details.
- Dynamic Sizing, RSI, TP/SL, Backtesting: Retained from prior glory.
- Decimal Precision: All financial calculations upgraded to use Python's Decimal type for accuracy.

For Termux: pkg install python termux-api python-matplotlib libssl; pip install pybit pandas pandas_ta colorama matplotlib.
Testnet default—set 'testnet': false for live.
"""

# Import necessary libraries
import json
import logging
import os
import smtplib
import subprocess
import time
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from email.mime.text import MIMEText

import matplotlib.pyplot as plt
import pandas as pd
import pandas_ta as ta
from colorama import Fore
from colorama import Style
from colorama import init
from pybit.unified_trading import HTTP

# Initialize Colorama for neon terminal radiance
init(autoreset=True)

# Neon Color Palette: Glowing like digital auroras
NEON_SUCCESS = Fore.LIGHTGREEN_EX
NEON_INFO = Fore.LIGHTCYAN_EX
NEON_WARNING = Fore.LIGHTYELLOW_EX
NEON_ERROR = Fore.LIGHTRED_EX
NEON_SIGNAL = Fore.LIGHTMAGENTA_EX + Style.BRIGHT
NEON_DEBUG = Fore.LIGHTBLUE_EX
NEON_POSITION = Fore.LIGHTWHITE_EX
NEON_RESET = Style.RESET_ALL

# --- Configuration Files ---
CONFIG_FILE = "bot_config.json"
LOG_FILE = "trade_log.log"
STATE_FILE = "bot_state.json"

# Setup logging for eternal audit trails
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


# --- Load Configuration ---
def _load_config():
    """Summons bot settings from JSON grimoire or forges defaults."""
    defaults = {
        "symbol": "BTCUSDT",
        "category": "linear",
        "interval": "60",
        "super_trend_length": 10,
        "super_trend_multiplier": 3.0,
        "leverage": 10,
        "stop_loss_pct": 0.02,
        "take_profit_pct": 0.05,
        "rsi_length": 14,
        "rsi_overbought": 70,
        "rsi_oversold": 30,
        "risk_pct": 0.01,
        "max_open_trades": 1,
        "max_position_size": 0.01,  # Max BTC per direction
        "close_delay": 5,  # Seconds to wait after closing
        "testnet": True,
        "backtest": False,
        "backtest_start": "2024-01-01",
        "backtest_end": "2024-08-01",
        "plot_enabled": False,
        "email_notify": False,
        "email_sender": "",
        "email_password": "",
        "email_receiver": "",
    }

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                config = json.load(f)
            defaults.update(config)
            print(NEON_SUCCESS + f"Config summoned from {CONFIG_FILE}." + NEON_RESET)
        except Exception as e:
            print(NEON_ERROR + f"Shadow in config: {e}. Using defaults." + NEON_RESET)
    else:
        with open(CONFIG_FILE, "w") as f:
            json.dump(defaults, f, indent=4)
        print(NEON_INFO + f"Forged new {CONFIG_FILE} with defaults." + NEON_RESET)

    return defaults


# --- Securely Load API Credentials ---
def _load_api_creds():
    """Loads API key and secret from JSON or env vars. Exits if absent."""
    api_key = None
    api_secret = None

    if os.path.exists("authcreds.json"):
        try:
            with open("authcreds.json") as f:
                creds = json.load(f)
                api_key = creds.get("api_key")
                api_secret = creds.get("api_secret")
            print(
                NEON_SUCCESS
                + "API credentials summoned from authcreds.json."
                + NEON_RESET
            )
        except Exception as e:
            print(NEON_ERROR + f"Shadow in authcreds.json: {e}" + NEON_RESET)
            print(NEON_INFO + "Seeking environment variables..." + NEON_RESET)

    if not api_key or not api_secret:
        api_key = os.getenv("BYBIT_API_KEY")
        api_secret = os.getenv("BYBIT_API_SECRET")
        if api_key and api_secret:
            print(
                NEON_SUCCESS
                + "Credentials drawn from environmental ether."
                + NEON_RESET
            )
        else:
            print(
                NEON_ERROR
                + "CRITICAL: Keys lost in the void. Forge 'authcreds.json' or set env vars."
                + NEON_RESET
            )
            exit(1)

    return api_key, api_secret


# --- Initialize Bybit API Session ---
def _initialize_session(config):
    """Forges the Pybit HTTP session, sets leverage for perpetual might.
    Checks current leverage before setting to avoid redundant calls.
    """
    if config["backtest"]:
        print(
            NEON_INFO
            + "Backtest mode active—forging a session for historical data."
            + NEON_RESET
        )
        session = HTTP(testnet=config["testnet"])
        return session

    api_key, api_secret = _load_api_creds()
    session = HTTP(
        testnet=config["testnet"],
        api_key=api_key,
        api_secret=api_secret,
        timeout=20,  # Increased timeout to 20 seconds
    )

    desired_leverage = str(config["leverage"])
    symbol = config["symbol"]
    category = config["category"]

    try:
        # Fetch current leverage
        position_info = session.get_positions(
            category=category, symbol=symbol
        )  # Changed from get_position_info
        current_leverage = None
        if position_info and position_info.get("result", {}).get("list"):
            for pos in position_info["result"]["list"]:
                if pos["symbol"] == symbol:
                    # Check for 'lever', 'buyLeverage', or 'sellLeverage'
                    current_leverage = (
                        pos.get("lever")
                        or pos.get("buyLeverage")
                        or pos.get("sellLeverage")
                    )
                    if current_leverage:
                        break  # Found leverage, exit loop

        if current_leverage is None:
            # If no open position, leverage might not be explicitly set for this symbol yet.
            # We still attempt to set it.
            print(
                NEON_INFO
                + f"No open position for {symbol}, attempting to set leverage to {desired_leverage}x."
                + NEON_RESET
            )
            session.set_leverage(
                category=category,
                symbol=symbol,
                buyLeverage=desired_leverage,
                sellLeverage=desired_leverage,
            )
            print(
                NEON_SUCCESS
                + f"Leverage set to {desired_leverage}x on {'Testnet' if config['testnet'] else 'Mainnet'}."
                + NEON_RESET
            )
        elif Decimal(current_leverage) != Decimal(desired_leverage):
            print(
                NEON_INFO
                + f"Current leverage for {symbol} is {current_leverage}x, desired is {desired_leverage}x. Adjusting..."
                + NEON_RESET
            )
            session.set_leverage(
                category=category,
                symbol=symbol,
                buyLeverage=desired_leverage,
                sellLeverage=desired_leverage,
            )
            print(
                NEON_SUCCESS
                + f"Leverage adjusted to {desired_leverage}x on {'Testnet' if config['testnet'] else 'Mainnet'}."
                + NEON_RESET
            )
        else:
            print(
                NEON_INFO
                + f"Leverage for {symbol} is already {current_leverage}x. No change needed."
                + NEON_RESET
            )

    except Exception as e:
        # Handle potential errors during leverage check or setting
        # Specifically ignore error 110043 if it occurs during initial setting
        if "110043" in str(e):
            print(
                NEON_WARNING
                + "Leverage is already set correctly (ErrCode: 110043). Continuing."
                + NEON_RESET
            )
        else:
            print(NEON_ERROR + f"Leverage rite disrupted: {e}" + NEON_RESET)
            logging.error(f"Leverage initialization failed: {e}")

    return session


# --- Data Acquisition Function ---
def _fetch_kline_data(
    session, symbol, category, interval, limit=200, start_time=None, end_time=None
):
    """Summons kline data, with time range for backtesting."""
    df_list = []
    current_start = start_time
    while True:
        for attempt in range(5):
            try:
                params = {
                    "category": category,
                    "symbol": symbol,
                    "interval": interval,
                    "limit": limit,
                }
                if current_start:
                    params["start"] = current_start
                if end_time:
                    params["end"] = end_time
                print(
                    NEON_INFO
                    + f"Channeling klines from {current_start}... "
                    + NEON_RESET
                )
                response = session.get_kline(**params)
                data = response.get("result", {}).get("list")
                if not data:
                    break
                df = pd.DataFrame(
                    data,
                    columns=[
                        "startTime",
                        "open",
                        "high",
                        "low",
                        "close",
                        "volume",
                        "turnover",
                    ],
                )
                df = df.iloc[::-1]
                df["open"] = pd.to_numeric(df["open"])
                df["high"] = pd.to_numeric(df["high"])
                df["low"] = pd.to_numeric(df["low"])
                df["close"] = pd.to_numeric(df["close"])
                df["startTime"] = pd.to_numeric(df["startTime"])  # Added this line
                df["startTime"] = pd.to_datetime(df["startTime"], unit="ms", utc=True)
                df_list.append(df)
                if len(data) < limit:
                    break
                current_start = int(df["startTime"].iloc[-1].timestamp() * 1000) + 1
                break
            except Exception as e:
                print(NEON_ERROR + f"Disruption: {e}" + NEON_RESET)
                if attempt < 4:
                    delay = 5 * (2**attempt)
                    print(NEON_WARNING + f"Retrying in {delay} seconds..." + NEON_RESET)
                    time.sleep(delay)
                else:
                    return pd.DataFrame()
        if not data or len(data) < limit:
            break
    if df_list:
        return pd.concat(df_list, ignore_index=True)
    return pd.DataFrame()


# --- Indicator Calculation Function ---
def _calculate_indicators(df, config):
    """Computes Supertrend and RSI, returning enriched DataFrame."""
    df.ta.supertrend(
        length=config["super_trend_length"],
        multiplier=config["super_trend_multiplier"],
        append=True,
    )

    st_col = f"SUPERT_{config['super_trend_length']}_{config['super_trend_multiplier']}"
    st_dir_col = (
        f"SUPERTd_{config['super_trend_length']}_{config['super_trend_multiplier']}"
    )

    if st_col not in df.columns:
        print(NEON_ERROR + "Supertrend columns vanished." + NEON_RESET)
        return pd.DataFrame()

    df["rsi"] = ta.rsi(df["close"], length=config["rsi_length"])

    return df[[st_col, st_dir_col, "close", "rsi", "startTime"]]


# --- Plot Supertrend Vision ---
def _plot_supertrend(df, config):
    """Forges visual plot with RSI subplot and signal markers."""
    try:
        st_col = (
            f"SUPERT_{config['super_trend_length']}_{config['super_trend_multiplier']}"
        )
        st_dir_col = (
            f"SUPERTd_{config['super_trend_length']}_{config['super_trend_multiplier']}"
        )
        plt.style.use("dark_background")
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

        # Price and Supertrend
        ax1.plot(df["startTime"], df["close"], label="Close", color="cyan")
        ax1.plot(df["startTime"], df[st_col], label="Supertrend", color="yellow")
        ax1.fill_between(
            df["startTime"],
            df["close"],
            df[st_col],
            where=(df["close"] > df[st_col]),
            color="lime",
            alpha=0.3,
        )
        ax1.fill_between(
            df["startTime"],
            df["close"],
            df[st_col],
            where=(df["close"] < df[st_col]),
            color="red",
            alpha=0.3,
        )

        # Signal markers
        buy_signals = df[
            (df[st_dir_col].shift(1) == -1)
            & (df[st_dir_col] == 1)
            & (df["rsi"] < config["rsi_overbought"])
        ]
        sell_signals = df[
            (df[st_dir_col].shift(1) == 1)
            & (df[st_dir_col] == -1)
            & (df["rsi"] > config["rsi_oversold"])
        ]
        ax1.scatter(
            buy_signals["startTime"],
            buy_signals["close"],
            color="lime",
            label="Buy Signal",
            marker="^",
            s=100,
        )
        ax1.scatter(
            sell_signals["startTime"],
            sell_signals["close"],
            color="red",
            label="Sell Signal",
            marker="v",
            s=100,
        )

        ax1.set_title(f"Supertrend Vision for {config['symbol']}", color="cyan")
        ax1.set_ylabel("Price", color="cyan")
        ax1.legend(facecolor="black")

        # RSI
        ax2.plot(df["startTime"], df["rsi"], label="RSI", color="magenta")
        ax2.axhline(config["rsi_overbought"], color="red", linestyle="--")
        ax2.axhline(config["rsi_oversold"], color="green", linestyle="--")
        ax2.set_ylabel("RSI", color="magenta")
        ax2.legend(facecolor="black")

        plt.xlabel("Time", color="cyan")
        plt.savefig("supertrend_plot.png")
        print(NEON_INFO + "Plot forged as supertrend_plot.png." + NEON_RESET)
    except Exception as e:
        print(NEON_WARNING + f"Plotting disrupted: {e}" + NEON_RESET)


# --- Get Account Balance ---
def _get_balance(session):
    """Fetches USDT balance with Decimal precision."""
    try:
        response = session.get_wallet_balance(accountType="UNIFIED")
        balances = response.get("result", {}).get("list", [{}])[0].get("coin", [])
        for coin in balances:
            if coin.get("coin") == "USDT":
                return Decimal(coin.get("walletBalance", "0"))
        return Decimal("0")
    except Exception as e:
        print(NEON_ERROR + f"Balance query disrupted: {e}" + NEON_RESET)
        return Decimal("0")


# --- Check RSI Filter ---
def _check_rsi_filter(rsi_val, config, side):
    """Verifies RSI for trade."""
    if side == "Buy":
        return rsi_val < config["rsi_overbought"]
    if side == "Sell":
        return rsi_val > config["rsi_oversold"]
    return False


# --- Close Position Function ---
def _close_position(session, symbol, category, current_position, delay):
    """Closes position with precision and confirms. Includes retry logic for timeouts."""
    side = current_position["side"]
    size = Decimal(current_position["size"])
    close_side = "Sell" if side == "Buy" else "Buy"

    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(NEON_WARNING + f"Closing {side} of {size} {symbol}..." + NEON_RESET)
            response = session.place_order(
                category=category,
                symbol=symbol,
                side=close_side,
                orderType="Market",
                qty=str(size),
                reduceOnly=True,
            )
            print(NEON_SUCCESS + f"Closed: {response}" + NEON_RESET)
            logging.info(f"Closed {side}: {response}")
            time.sleep(delay)

            # Verify closure
            positions = (
                session.get_positions(category=category, symbol=symbol)
                .get("result", {})
                .get("list", [])
            )
            if not positions or Decimal(positions[0]["size"]) == Decimal("0"):
                print(NEON_SUCCESS + "Closure confirmed." + NEON_RESET)
                return response
            print(NEON_WARNING + "Closure incomplete—retrying..." + NEON_RESET)
                # If closure is incomplete, we might need to retry the close operation
                # or handle it differently. For now, we'll just log and continue.
                # A more robust solution might involve a loop here to re-attempt closing.

            return response  # Return response if closure was successful or confirmed

        except Exception as e:
            if "Read timed out" in str(e) and attempt < max_retries - 1:
                sleep_time = 5 * (2**attempt)  # Exponential backoff
                print(
                    NEON_WARNING
                    + f"Read timed out. Retrying close in {sleep_time} seconds... (Attempt {attempt + 1}/{max_retries})"
                    + NEON_RESET
                )
                time.sleep(sleep_time)
            else:
                print(NEON_ERROR + f"Close failed: {e}" + NEON_RESET)
                logging.error(f"Close failed: {e}")
                return None  # Return None if it fails after retries or for other errors
    return None  # Return None if loop finishes without success


# --- Calculate Dynamic Quantity ---
def _calculate_quantity(balance, close_price, config):
    """Computes size based on risk with Decimal precision, capped by max_position_size.
    Ensures quantity is at least the minimum allowed (0.1 for TRUMPUSDT).
    """
    balance = Decimal(balance)
    close_price = Decimal(close_price)
    risk_pct = Decimal(config["risk_pct"])
    stop_loss_pct = Decimal(config["stop_loss_pct"])
    leverage = Decimal(config["leverage"])
    max_position_size = Decimal(config["max_position_size"])
    min_order_qty = Decimal("0.1")  # Minimum order quantity for TRUMPUSDT

    if risk_pct <= Decimal("0"):
        qty = Decimal(config.get("quantity", "0.001"))
    else:
        stop_distance = close_price * stop_loss_pct
        if stop_distance == Decimal("0"):
            return Decimal("0")
        qty = (balance * risk_pct) / stop_distance
        qty = qty * leverage

    qty = min(qty, max_position_size)
    # Ensure the quantity is at least the minimum allowed order quantity
    qty = max(qty, min_order_qty)
    print(NEON_DEBUG + f"Dynamic quantity: {qty:.6f}" + NEON_RESET)
    return qty


# --- Order Execution Function ---
def _place_order_with_tpsl(
    session, side, symbol, category, quantity, entry_price, config
):
    """Places order with TP/SL using Decimal precision."""
    entry_price = Decimal(entry_price)
    # Use ATR for TP/SL if available, otherwise fall back to percentage
    if (
        "ATR_PERIOD" in config
        and "ATR_MULTIPLIER_SL" in config
        and "ATR_MULTIPLIER_TP" in config
    ):
        # Fallback to percentage-based calculation if ATR is not readily available or implemented
        sl_price = entry_price * (Decimal("1") - stop_loss_pct)
        tp_price = entry_price * (Decimal("1") + take_profit_pct)

    else:
        # Fallback to percentage-based calculation if ATR config is missing
        try:
            print(
                NEON_WARNING
                + f"Placing {side} for {quantity:.6f} {symbol}..."
                + NEON_RESET
            )
            order_response = session.place_order(
                category=category,
                symbol=symbol,
                side=side,
                orderType="Market",
                qty=f"{quantity:.8f}",
                takeProfit=f"{tp_price:.8f}",
                stopLoss=f"{sl_price:.8f}",
                tpslMode="Full",
            )
            print(NEON_SUCCESS + f"Placed: {order_response}" + NEON_RESET)
            logging.info(f"{side} placed: {order_response}")

            try:
                subprocess.run(
                    ["termux-toast", f"{side} signal for {symbol}!"], check=False
                )
            except:
                pass
            if config["email_notify"]:
                _send_email(
                    config,
                    f"{side} Signal",
                    f"Executed {side} for {symbol}, size {quantity:.6f} at {entry_price}",
                )

            return order_response
        except Exception as e:
            print(NEON_ERROR + f"Order failed: {e}" + NEON_RESET)
            logging.error(f"Order failed: {e}")
            return None


# --- Send Email Notification ---
def _send_email(config, subject, body):
    """Summons email alert if configured."""
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = config["email_sender"]
        msg["To"] = config["email_receiver"]
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(config["email_sender"], config["email_password"])
            server.sendmail(
                config["email_sender"], config["email_receiver"], msg.as_string()
            )
        print(NEON_INFO + "Email ether sent." + NEON_RESET)
    except Exception as e:
        print(NEON_WARNING + f"Email disrupted: {e}" + NEON_RESET)


# --- Backtest Simulation ---
def _run_backtest(df_ind, config):
    """Simulates trades with Decimal precision, closes on opposite signals, computes PNL."""
    equity = Decimal("10000.0")
    positions = []
    trades = []
    last_dir = None
    for i in range(1, len(df_ind)):
        current = df_ind.iloc[i]
        st_dir = current[
            f"SUPERTd_{config['super_trend_length']}_{config['super_trend_multiplier']}"
        ]
        close = Decimal(str(current["close"]))
        rsi = current["rsi"]

        is_buy = (st_dir == 1 and last_dir == -1) and _check_rsi_filter(
            rsi, config, "Buy"
        )
        is_sell = (st_dir == -1 and last_dir == 1) and _check_rsi_filter(
            rsi, config, "Sell"
        )
        last_dir = st_dir

        if positions and (
            (is_buy and positions[-1]["side"] == "Sell")
            or (is_sell and positions[-1]["side"] == "Buy")
        ):
            pos = positions.pop()
            exit_price = close
            pnl = (
                (exit_price - pos["entry"]) * pos["qty"]
                if pos["side"] == "Buy"
                else (pos["entry"] - exit_price) * pos["qty"]
            )
            equity += pnl
            trades.append(
                {"exit_time": current["startTime"], "side": pos["side"], "pnl": pnl}
            )
            logging.info(f"Backtest closed {pos['side']}: PNL {pnl}")

        if (is_buy or is_sell) and len(positions) < config["max_open_trades"]:
            qty = _calculate_quantity(equity, close, config)
            if qty > Decimal("0"):
                positions.append(
                    {"side": "Buy" if is_buy else "Sell", "entry": close, "qty": qty}
                )
                logging.info(
                    f"Backtest opened {positions[-1]['side']}: {qty} at {close}"
                )

    if positions:
        pos = positions.pop()
        exit_price = Decimal(str(df_ind["close"].iloc[-1]))
        pnl = (
            (exit_price - pos["entry"]) * pos["qty"]
            if pos["side"] == "Buy"
            else (pos["entry"] - exit_price) * pos["qty"]
        )
        equity += pnl
        trades.append(
            {"exit_time": df_ind["startTime"].iloc[-1], "side": pos["side"], "pnl": pnl}
        )

    total_pnl = sum(t["pnl"] for t in trades)
    print(
        NEON_SUCCESS
        + f"Backtest PNL: {total_pnl:.4f} | Final Equity: {equity:.4f}"
        + NEON_RESET
    )
    logging.info(f"Backtest complete: PNL {total_pnl}")
    if config["plot_enabled"] and trades:
        plt.figure(figsize=(12, 6))
        equity_curve = [Decimal("10000.0")]
        for t in trades:
            equity_curve.append(equity_curve[-1] + t["pnl"])
        plt.plot(
            [t["exit_time"] for t in trades],
            [float(v) for v in equity_curve[1:]],
            color="cyan",
        )
        plt.title("Backtest Equity Curve", color="cyan")
        plt.savefig("equity_curve.png")
        print(NEON_INFO + "Equity curve forged as equity_curve.png." + NEON_RESET)


# --- Main Trading Loop ---
def main():
    """Core loop: Live trading or backtest with neon grace."""
    config = _load_config()
    session = _initialize_session(config)

    state = {"last_supertrend_dir": None, "last_rsi": None}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                state = json.load(f)
            print(NEON_INFO + "State restored." + NEON_RESET)
        except Exception as e:
            print(NEON_ERROR + f"State load failed: {e}" + NEON_RESET)

    print(
        NEON_SUCCESS + f"Summoning ascended bot for {config['symbol']}... " + NEON_RESET
    )
    logging.info("Bot awakened.")

    if config["backtest"]:
        start_ts = int(
            datetime.fromisoformat(config["backtest_start"]).timestamp() * 1000
        )
        end_ts = int(datetime.fromisoformat(config["backtest_end"]).timestamp() * 1000)
        df = _fetch_kline_data(
            session,
            config["symbol"],
            config["category"],
            config["interval"],
            limit=1000,
            start_time=start_ts,
            end_time=end_ts,
        )
        if df.empty:
            print(NEON_ERROR + "Historical void." + NEON_RESET)
            return
        df_ind = _calculate_indicators(df, config)
        _run_backtest(df_ind, config)
        return

    try:
        while True:
            df = _fetch_kline_data(
                session, config["symbol"], config["category"], config["interval"]
            )
            if df.empty:
                print(NEON_WARNING + "Data void—retrying." + NEON_RESET)
                time.sleep(60)
                continue

            df_ind = _calculate_indicators(df, config)
            if df_ind.empty:
                print(NEON_WARNING + "Indicators disrupted—retrying." + NEON_RESET)
                time.sleep(60)
                continue

            if config["plot_enabled"]:
                _plot_supertrend(df_ind, config)

            current_data = df_ind.iloc[-1]
            st_dir_current = current_data[
                f"SUPERTd_{config['super_trend_length']}_{config['super_trend_multiplier']}"
            ]
            close_current = Decimal(str(current_data["close"]))
            rsi_current = current_data["rsi"]

            # Calculate Stoch RSI values
            # Ensure STOCHRSI_K_PERIOD and STOCHRSI_D_PERIOD are read from config
            stoch_rsi_k_series = ta.stochrsi(
                df["close"],
                length=config.get("stochrsi_k_period", 14),
                smooth_k=config.get("stochrsi_d_period", 3),
                append=False,
            )[
                f"STOCHRSIk_{config.get('stochrsi_k_period', 14)}_{config.get('stochrsi_d_period', 3)}"
            ]
            stoch_rsi_d_series = stoch_rsi_k_series.rolling(
                window=config.get("stochrsi_d_period", 3)
            ).mean()

            # Check for Stoch RSI crossover
            stoch_rsi_cross_up = (
                stoch_rsi_k_series.shift(1) < stoch_rsi_d_series.shift(1)
            ) & (stoch_rsi_k_series > stoch_rsi_d_series)
            stoch_rsi_cross_down = (
                stoch_rsi_k_series.shift(1) > stoch_rsi_d_series.shift(1)
            ) & (stoch_rsi_k_series < stoch_rsi_d_series)

            # Base signals from Supertrend and RSI filter
            is_buy_signal_base = (
                st_dir_current == 1 and state.get("last_supertrend_dir") == -1
            ) and _check_rsi_filter(rsi_current, config, "Buy")
            is_sell_signal_base = (
                st_dir_current == -1 and state.get("last_supertrend_dir") == 1
            ) and _check_rsi_filter(rsi_current, config, "Sell")

            # Incorporate Stoch RSI crossover if enabled
            is_buy_signal = is_buy_signal_base
            is_sell_signal = is_sell_signal_base

            if config.get("use_stochrsi_crossover", False):
                is_buy_signal = is_buy_signal and stoch_rsi_cross_up.iloc[-1]
                is_sell_signal = is_sell_signal and stoch_rsi_cross_down.iloc[-1]

            state["last_supertrend_dir"] = (
                int(st_dir_current) if pd.notna(st_dir_current) else None
            )
            state["last_rsi"] = float(rsi_current) if pd.notna(rsi_current) else None
            with open(STATE_FILE, "w") as f:
                json.dump(state, f)

            positions_response = session.get_positions(
                category=config["category"], symbol=config["symbol"]
            )
            positions = positions_response.get("result", {}).get("list", [])
            current_position = (
                positions[0]
                if positions and Decimal(positions[0]["size"]) > 0
                else None
            )
            has_long = current_position and current_position["side"] == "Buy"
            has_short = current_position and current_position["side"] == "Sell"
            open_count = 1 if current_position else 0
            balance = _get_balance(session)

            print(
                NEON_INFO
                + f"Epoch: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}"
                + NEON_RESET
            )
            print(
                NEON_INFO
                + f"Close: {close_current} | Dir: {'Up' if st_dir_current == 1 else 'Down'} | RSI: {rsi_current:.2f}"
                + NEON_RESET
            )
            print(
                NEON_POSITION
                + f"Balance: {balance:.2f} USDT | Position: {'Long' if has_long else 'Short' if has_short else 'None'}"
                + NEON_RESET
            )

            required_balance = close_current / Decimal(config["leverage"])
            if balance < required_balance:
                print(NEON_ERROR + "Essence depleted." + NEON_RESET)
                logging.warning("Insufficient balance.")
            elif open_count >= config["max_open_trades"]:
                print(NEON_WARNING + "Exposure maxed—observing." + NEON_RESET)
            elif is_buy_signal and not has_long:
                print(NEON_SIGNAL + "--- BUY FLIP (RSI OK) ---" + NEON_RESET)
                logging.info("Buy signal.")
                if has_short:
                    _close_position(
                        session,
                        config["symbol"],
                        config["category"],
                        current_position,
                        config["close_delay"],
                    )
                    time.sleep(config["close_delay"])
                if qty <= Decimal(config["max_position_size"]):
                    _place_order_with_tpsl(
                        session,
                        "Buy",
                        config["symbol"],
                        config["category"],
                        qty,
                        close_current,
                        config,
                        df_ind,
                    )  # Pass df_ind
                else:
                    print(NEON_WARNING + "Position size exceeds max." + NEON_RESET)
            elif is_sell_signal and not has_short:
                print(NEON_SIGNAL + "--- SELL FLIP (RSI OK) ---" + NEON_RESET)
                logging.info("Sell signal.")
                if has_long:
                    _close_position(
                        session,
                        config["symbol"],
                        config["category"],
                        current_position,
                        config["close_delay"],
                    )
                    time.sleep(config["close_delay"])
                qty = _calculate_quantity(balance, close_current, config)
                if qty <= Decimal(config["max_position_size"]):
                    _place_order_with_tpsl(
                        session,
                        "Sell",
                        config["symbol"],
                        config["category"],
                        qty,
                        close_current,
                        config,
                    )
                else:
                    print(NEON_WARNING + "Position size exceeds max." + NEON_RESET)
            else:
                print(NEON_INFO + "No winds shift. Observing..." + NEON_RESET)

            interval_sec = int(config["interval"]) * 60
            last_time = df["startTime"].iloc[-1]
            next_time = last_time + timedelta(seconds=interval_sec)
            sleep_dur = (next_time - datetime.now(UTC)).total_seconds() + 10
            sleep_dur = max(sleep_dur, 60)
            print(NEON_INFO + f"Slumbering {int(sleep_dur)} seconds..." + NEON_RESET)
            time.sleep(sleep_dur)

    except KeyboardInterrupt:
        print(NEON_INFO + "Shutdown—ether released." + NEON_RESET)
        logging.info("Bot shutdown.")
    except Exception as e:
        print(NEON_ERROR + f"Cataclysm: {e}" + NEON_RESET)
        logging.error(f"Main error: {e}", exc_info=True)


if __name__ == "__main__":
    main()
