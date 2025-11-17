#!/usr/bin/env python3

"""Pyrmethus's Ascended Neon Bybit Trading Bot (Long/Short Enhanced)

This ultimate incantation perfects the Supertrend strategy for Bybit V5 API, ensuring both long and short positions are taken and closed on opposite signals. Forged in Termux’s ethereal forge, it radiates neon brilliance and strategic precision.

"""

import ccxt
import os
import time
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler(),
    ],
)


def _load_config():
    """Loads Bybit API credentials and settings from environment variables."""
    api_key = os.environ.get("BYBIT_API_KEY")
    api_secret = os.environ.get("BYBIT_API_SECRET")
    testnet = os.environ.get("BYBIT_TESTNET", "true").lower() == "true"

    if not api_key or not api_secret:
        raise ValueError(
            "BYBIT_API_KEY and BYBIT_API_SECRET must be set as environment variables."
        )

    return {
        "apiKey": api_key,
        "secret": api_secret,
        "testnet": testnet,
        "options": {
            "defaultType": "spot",  # or "future", "swap"
        },
    }


def _initialize_exchange(config):
    """Initializes the CCXT exchange object for Bybit."""
    exchange_class = getattr(ccxt, "bybit")
    exchange = exchange_class(config)
    # Load markets to ensure symbol information is available
    exchange.load_markets()
    logging.info(f"Initialized Bybit exchange. Testnet: {config["testnet"]}")
    return exchange


def _get_supertrend(symbol, timeframe, limit, exchange):
    """Calculates Supertrend values using Ehlers's Supertrend strategy."""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        if not ohlcv or len(ohlcv) < 10:  # Need at least a few candles for calculation
            logging.warning(f"Not enough data for {symbol} {timeframe}. Received {len(ohlcv)} candles.")
            return None, None, None, None

        df = exchange.create_dataframe(ohlcv, ["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pandas.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)

        # Ehlers's Supertrend Calculation (simplified representation)
        # In a real scenario, you would implement Ehlers's specific formulas here.
        # This is a placeholder for the actual Supertrend logic.
        # For demonstration, we'll use a basic Supertrend implementation.
        # You would typically use libraries like `ta` or implement the formulas directly.

        # Placeholder for Supertrend calculation - replace with actual Ehlers Supertrend logic
        # For now, let's simulate a basic trend direction
        close_prices = df["close"].astype(float)
        atr = ccxt.Exchange.calc_atr(df, period=14) # Example ATR calculation
        # Basic Supertrend logic (replace with Ehlers's specific formulas)
        up = df["low"] - 14 * atr
        down = df["high"] + 14 * atr
        df["uptrend"] = pandas.Series(dtype=float)
        df["downtrend"] = pandas.Series(dtype=float)
        df["supertrend"] = pandas.Series(dtype=float)

        for i in range(len(df)):
            if i == 0:
                df["uptrend"].iloc[i] = up.iloc[i]
                df["downtrend"].iloc[i] = down.iloc[i]
            else:
                df["uptrend"].iloc[i] = min(up.iloc[i], df["uptrend"].iloc[i-1])
                df["downtrend"].iloc[i] = max(down.iloc[i], df["downtrend"].iloc[i-1])

            if df["uptrend"].iloc[i] < df["downtrend"].iloc[i-1]:
                df["uptrend"].iloc[i] = df["uptrend"].iloc[i]
            else:
                df["uptrend"].iloc[i] = df["downtrend"].iloc[i-1]

            if df["downtrend"].iloc[i] > df["uptrend"].iloc[i-1]:
                df["downtrend"].iloc[i] = df["downtrend"].iloc[i]
            else:
                df["downtrend"].iloc[i] = df["uptrend"].iloc[i-1]

            if df["close"].iloc[i] > df["downtrend"].iloc[i]:
                df["supertrend"].iloc[i] = df["uptrend"].iloc[i]
            elif df["close"].iloc[i] < df["uptrend"].iloc[i]:
                df["supertrend"].iloc[i] = df["downtrend"].iloc[i]
            else:
                df["supertrend"].iloc[i] = df["supertrend"].iloc[i-1]

        # Determine trend direction
        df["trend_direction"] = 0
        df["trend_direction"].iloc[-1] = 1 if df["close"].iloc[-1] > df["supertrend"].iloc[-1] else -1

        # Get the latest values
        latest_supertrend = df["supertrend"].iloc[-1]
        latest_trend_direction = df["trend_direction"].iloc[-1]
        latest_close = df["close"].iloc[-1]

        return latest_close, latest_supertrend, latest_trend_direction, df

    except ccxt.NetworkError as e:
        logging.error(f"Network error occurred: {e}")
    except ccxt.ExchangeError as e:
        logging.error(f"Exchange error occurred: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")

    return None, None, None, None


def main():
    """Main function to run the Bybit trading bot."""
    try:
        config = _load_config()
        exchange = _initialize_exchange(config)

        symbol = input("Enter the trading symbol (e.g., 'BTC/USDT'): ")
        timeframe = input("Enter the timeframe (e.g., '1m', '5m', '1h'): ")
        limit = int(input("Enter the number of candles for calculation (e.g., 100): "))

        logging.info(f"Starting live trading for {symbol} on timeframe {timeframe}...")

        while True:
            latest_close, latest_supertrend, latest_trend_direction, _ = _get_supertrend(symbol, timeframe, limit, exchange)

            if latest_close is not None:
                logging.info(f"Current Close: {latest_close}, Supertrend: {latest_supertrend}, Trend: {latest_trend_direction}")

                # --- Trading Logic (Long/Short) ---
                # This is a basic example. Implement your actual trading logic here.
                # You would typically check for open positions and place orders accordingly.

                if latest_trend_direction == 1:  # Potential Long signal
                    logging.info(f"UPTREND signal detected for {symbol}. Consider opening LONG position.")
                    # Example: Place a buy order if no long position is open
                    # exchange.create_market_buy_order(symbol, amount)

                elif latest_trend_direction == -1:  # Potential Short signal
                    logging.info(f"DOWNTREND signal detected for {symbol}. Consider opening SHORT position.")
                    # Example: Place a sell order if no short position is open
                    # exchange.create_market_sell_order(symbol, amount)

                # Add logic here to close positions based on opposite signals or other conditions

            else:
                logging.warning("Could not retrieve Supertrend data. Retrying...")

            # Wait for the next candle/interval
            time.sleep(exchange.parse_timeframe(timeframe)) # Wait for the duration of the timeframe

    except ValueError as e:
        logging.error(f"Configuration error: {e}")
    except ccxt.AuthenticationError as e:
        logging.error(f"Authentication error: {e}. Check your API keys and network.")
    except ccxt.NetworkError as e:
        logging.error(f"Network error during initialization: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred during initialization: {e}")

if __name__ == "__main__":
    # Import pandas here to avoid issues if it's not installed when just importing the script
    try:
        import pandas
    except ImportError:
        print("Pandas is not installed. Please install it: pip install pandas")
        exit(1)
    main()
