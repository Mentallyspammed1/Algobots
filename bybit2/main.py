import argparse
import importlib.util  # Import for dynamic module loading
import os

from bybit_trend_analyzer import BybitTrendAnalyzer

# --- Configuration Loading ---
# Path to the config.py file
CONFIG_FILE_PATH = "/data/data/com.termux/files/home/Algobots/bybit2/config.py"

# Default values for parameters, to be overridden by config.py if found
NUM_CANDLES = 500
INTERVAL = "60"
SYMBOL = "BTCUSDT"
STRATEGY_NAME = "StochRSI_Fib_OB_Strategy"

# Default indicator periods
SMA_FAST = 20
SMA_SLOW = 50
EMA_FAST = 12
EMA_SLOW = 26
RSI_PERIOD = 14
ADX_PERIOD = 14
BB_WINDOW = 20
BB_STD = 2
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
ICHIMOKU_TENKAN = 9
ICHIMOKU_KIJUN = 26
ICHIMOKU_SENKOU = 52
EHLERS_FISHER_PERIOD = 10
EHLERS_SSF_PERIOD = 10
OB_PERCENTAGE_THRESHOLD = 0.01

# API Keys - prioritize environment variables
API_KEY = os.getenv("BYBIT_API_KEY", "YOUR_BYBIT_API_KEY")
API_SECRET = os.getenv(
    "BYBIT_API_SECRET", "YOUR_BYBIT_API_SECRET"
)  # Replace with your secret or set env var

try:
    # Dynamically load config.py
    spec = importlib.util.spec_from_file_location("config", CONFIG_FILE_PATH)
    config_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config_module)

    # Update variables from config.py if they exist
    NUM_CANDLES = getattr(config_module, "NUM_CANDLES", NUM_CANDLES)
    INTERVAL = getattr(config_module, "INTERVAL", INTERVAL)
    SYMBOL = getattr(config_module, "SYMBOL", SYMBOL)
    STRATEGY_NAME = getattr(config_module, "STRATEGY_NAME", STRATEGY_NAME)

    # Update indicator periods from config.py
    SMA_FAST = getattr(config_module, "SMA_FAST", SMA_FAST)
    SMA_SLOW = getattr(config_module, "SMA_SLOW", SMA_SLOW)
    EMA_FAST = getattr(config_module, "EMA_FAST", EMA_FAST)
    EMA_SLOW = getattr(config_module, "EMA_SLOW", EMA_SLOW)
    RSI_PERIOD = getattr(config_module, "RSI_PERIOD", RSI_PERIOD)
    ADX_PERIOD = getattr(config_module, "ADX_PERIOD", ADX_PERIOD)
    BB_WINDOW = getattr(config_module, "BB_WINDOW", BB_WINDOW)
    BB_STD = getattr(config_module, "BB_STD", BB_STD)
    MACD_FAST = getattr(config_module, "MACD_FAST", MACD_FAST)
    MACD_SLOW = getattr(config_module, "MACD_SLOW", MACD_SLOW)
    MACD_SIGNAL = getattr(config_module, "MACD_SIGNAL", MACD_SIGNAL)
    ICHIMOKU_TENKAN = getattr(config_module, "ICHIMOKU_TENKAN", ICHIMOKU_TENKAN)
    ICHIMOKU_KIJUN = getattr(config_module, "ICHIMOKU_KIJUN", ICHIMOKU_KIJUN)
    ICHIMOKU_SENKOU = getattr(config_module, "ICHIMOKU_SENKOU", ICHIMOKU_SENKOU)
    EHLERS_FISHER_PERIOD = getattr(
        config_module, "EHLERS_FISHER_PERIOD", EHLERS_FISHER_PERIOD
    )
    EHLERS_SSF_PERIOD = getattr(config_module, "EHLERS_SSF_PERIOD", EHLERS_SSF_PERIOD)
    OB_PERCENTAGE_THRESHOLD = getattr(
        config_module, "OB_PERCENTAGE_THRESHOLD", OB_PERCENTAGE_THRESHOLD
    )

    # Update API keys from config.py if environment variables are not set
    if API_KEY == "YOUR_BYBIT_API_KEY":
        API_KEY = getattr(config_module, "API_KEY", API_KEY)
    if API_SECRET == "YOUR_BYBIT_API_SECRET":
        API_SECRET = getattr(config_module, "API_SECRET", API_SECRET)

except FileNotFoundError:
    print(f"Warning: config.py not found at {CONFIG_FILE_PATH}. Using default values.")
except Exception as e:
    print(f"Warning: Error loading config.py: {e}. Using default values.")


def main():
    parser = argparse.ArgumentParser(
        description="Bybit Trend Analyzer: Fetches kline data and performs technical analysis."
    )
    # Use values from config.py (loaded into global variables) as defaults
    parser.add_argument(
        "--symbol",
        type=str,
        default=SYMBOL,
        help="Trading pair (e.g., BTCUSDT, ETHUSDT).",
    )
    parser.add_argument(
        "--category",
        type=str,
        default="linear",
        choices=["linear", "inverse", "spot"],
        help="Product category (linear, inverse, spot).",
    )
    parser.add_argument(
        "--interval",
        type=str,
        default=INTERVAL,
        help="Klines interval (e.g., 1, 5, 15, 60, 240, D, W, M).",
    )
    # Use NUM_CANDLES from config.py as the default for the command-line argument
    parser.add_argument(
        "--num_candles",
        type=int,
        default=NUM_CANDLES,
        help="Number of historical candles to fetch (max 1000).",
    )
    parser.add_argument(
        "--testnet", action="store_true", help="Use Bybit Testnet instead of Mainnet."
    )

    args = parser.parse_args()

    analyzer = BybitTrendAnalyzer(
        api_key=API_KEY, api_secret=API_SECRET, testnet=args.testnet
    )

    print(
        f"\n--- Analyzing Trend for {args.symbol} on {args.interval} interval ({args.category} category) ---"
    )
    trend_summary = analyzer.get_trend_summary(
        category=args.category,
        symbol=args.symbol,
        interval=args.interval,
        num_candles=args.num_candles,  # This will use the value from argparse, which defaults to NUM_CANDLES from config.py
        sma_fast_period=SMA_FAST,
        sma_slow_period=SMA_SLOW,
        ema_fast_period=EMA_FAST,
        ema_slow_period=EMA_SLOW,
        rsi_period=RSI_PERIOD,
        adx_period=ADX_PERIOD,
        bb_window=BB_WINDOW,
        bb_std=BB_STD,
        macd_fast_period=MACD_FAST,
        macd_slow_period=MACD_SLOW,
        macd_signal_period=MACD_SIGNAL,
        ichimoku_tenkan=ICHIMOKU_TENKAN,
        ichimoku_kijun=ICHIMOKU_KIJUN,
        ichimoku_senkou=ICHIMOKU_SENKOU,
        ehlers_fisher_period=EHLERS_FISHER_PERIOD,
        ehlers_ssf_period=EHLERS_SSF_PERIOD,
        ob_percentage_threshold=OB_PERCENTAGE_THRESHOLD,
    )

    if trend_summary.get("status") == "success":
        print("\n--- Trend Analysis Summary ---")
        print(f"Symbol: {trend_summary['symbol']}")
        print(f"Interval: {trend_summary['interval']}")
        print(f"Latest Price: {trend_summary['details']['price']:.2f}")
        print(f"Timestamp: {trend_summary['details']['timestamp']}")
        print(f"Overall Trend: {trend_summary['overall_trend']}")
        print("\n--- Detailed Indicators ---")
        for key, value in trend_summary["details"].items():
            if key not in ["price", "timestamp"]:
                print(f"  {key.replace('_', ' ').title()}: {value}")
        print(f"\nCandles Fetched: {trend_summary['num_candles_fetched']}")
        print(
            f"Candles Analyzed (after cleaning NaNs): {trend_summary['num_candles_analyzed']}"
        )
    else:
        print(
            f"\nError during analysis: {trend_summary.get('message', 'Unknown error')}"
        )

    # Example: Fetch raw kline data and print head
    print(f"\n--- Raw Kline Data (first 5 rows) for {args.symbol} ---")
    df_klines = analyzer.fetch_klines(
        args.category, args.symbol, args.interval, num_candles=10
    )
    if not df_klines.empty:
        print(df_klines.head())
    else:
        print("Could not fetch raw kline data.")

    # Example: Fetch data and calculate indicators, then print tail
    print(f"\n--- Kline Data with Indicators (last 5 rows) for {args.symbol} ---")
    df_with_indicators = analyzer.fetch_klines(
        args.category, args.symbol, args.interval, num_candles=args.num_candles
    )
    if not df_with_indicators.empty:
        df_with_indicators = analyzer.calculate_indicators(
            df_with_indicators,
            sma_fast_period=SMA_FAST,
            sma_slow_period=SMA_SLOW,
            rsi_period=RSI_PERIOD,
            adx_period=ADX_PERIOD,
            bb_window=BB_WINDOW,
            macd_fast_period=MACD_FAST,
            macd_slow_period=MACD_SLOW,
            ichimoku_tenkan=ICHIMOKU_TENKAN,
            ichimoku_kijun=ICHIMOKU_KIJUN,
            ehlers_fisher_period=EHLERS_FISHER_PERIOD,
            ehlers_ssf_period=EHLERS_SSF_PERIOD,
            ob_percentage_threshold=OB_PERCENTAGE_THRESHOLD,
        )
        print(df_with_indicators.tail())
    else:
        print("Could not fetch data for indicator calculation.")


if __name__ == "__main__":
    main()
