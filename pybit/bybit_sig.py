#!/usr/bin/env python3

import ccxt
import pandas as pd
import talib as ta
import sys
import datetime
import argparse

# ----- configurable variables -----
DEFAULT_PAIR      = "TRUMPUSDT"
DEFAULT_TIMEFRAME = "1m"
DEFAULT_CANDLES   = 250
# ----------------------------------

FAST, SLOW = 5, 8
RSI_LEN    = 12
MACD_FAST, MACD_SLOW, MACD_SIG = 12, 26, 9

def fetch_df(exchange, pair, tf, limit):
    """
    Fetches OHLCV data from an exchange and returns a pandas DataFrame.
    """
    try:
        ohlcv = exchange.fetch_ohlcv(pair, tf, limit=limit)
        if not ohlcv:
            print("Error: No data fetched. Check pair and timeframe.")
            return pd.DataFrame()
        cols = ["ts", "open", "high", "low", "close", "vol"]
        df = pd.DataFrame(ohlcv, columns=cols)
        df["ts"] = pd.to_datetime(df["ts"], unit="ms")
        return df
    except (ccxt.NetworkError, ccxt.ExchangeError) as e:
        print(f"CCXT Error fetching data: {e}")
        return pd.DataFrame()
    except Exception as e:
        print(f"An unexpected error occurred in fetch_df: {e}")
        return pd.DataFrame()

def compute_indicators(df):
    """
    Computes technical indicators and adds them to the DataFrame.
    """
    if df.empty:
        return df
    
    # Ensure there are enough candles for the calculations
    if len(df) < max(FAST, SLOW, RSI_LEN, MACD_SLOW):
        print("Not enough data to compute all indicators.")
        return df

    df["ema_fast"] = ta.EMA(df["close"], timeperiod=FAST)
    df["ema_slow"] = ta.EMA(df["close"], timeperiod=SLOW)
    df["rsi"]      = ta.RSI(df["close"], timeperiod=RSI_LEN)
    
    macd, macdsig, macdhist = ta.MACD(df["close"], MACD_FAST, MACD_SLOW, MACD_SIG)
    df["macd"]      = macd
    df["macds"]     = macdsig
    df["macdhist"]  = macdhist
    
    return df

def latest_signal(df):
    """
    Analyzes the latest data point to generate a trading signal.
    
    The signal logic is based on:
    1. EMA Crossover (Fast EMA > Slow EMA for Buy, vice-versa for Sell)
    2. RSI value (RSI > 50 for Buy, < 50 for Sell)
    3. MACD Crossover (MACD > Signal line for Buy, vice-versa for Sell)
    4. MACD Histogram (Positive for Buy, Negative for Sell)
    """
    if df.empty or len(df) < 2:
        return "HOLD"
    
    last = df.iloc[-1]
    
    # Check for NaN values in the last row after TA calculation
    if last.isnull().any():
        return "HOLD"
        
    cond_ema_buy  = last.ema_fast > last.ema_slow
    cond_ema_sell = last.ema_fast < last.ema_slow
    
    cond_rsi_buy  = last.rsi > 50
    cond_rsi_sell = last.rsi < 50
    
    cond_macd_buy  = last.macd > last.macds
    cond_macd_sell = last.macd < last.macds
    
    cond_hist_buy  = last.macdhist > 0
    cond_hist_sell = last.macdhist < 0
    
    # Combined conditions for a strong signal
    cond_buy  = cond_ema_buy and cond_rsi_buy and cond_macd_buy and cond_hist_buy
    cond_sell = cond_ema_sell and cond_rsi_sell and cond_macd_sell and cond_hist_sell
    
    if cond_buy:
        return "BUY"
    if cond_sell:
        return "SELL"
    return "HOLD"

def trend(df):
    """
    Determines the overall trend based on EMA crossover.
    """
    if df.empty:
        return "Unknown"
        
    last = df.iloc[-1]
    
    if last.ema_fast > last.ema_slow:
        return "Bullish"
    if last.ema_fast < last.ema_slow:
        return "Bearish"
    return "Consolidating"

def main():
    """
    Main function to run the analysis script.
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Bybit trading signal analyzer.")
    parser.add_argument('--pair', type=str, default=DEFAULT_PAIR, help=f'Trading pair (e.g., BTCUSDT). Default: {DEFAULT_PAIR}')
    parser.add_argument('--tf', type=str, default=DEFAULT_TIMEFRAME, help=f'Timeframe (e.g., 1m, 5m, 1h). Default: {DEFAULT_TIMEFRAME}')
    parser.add_argument('--candles', type=int, default=DEFAULT_CANDLES, help=f'Number of candles to fetch. Default: {DEFAULT_CANDLES}')
    args = parser.parse_args()

    # Create Bybit exchange instance
    bybit = ccxt.bybit({"enableRateLimit": True})

    # Fetch and process data
    df = fetch_df(bybit, args.pair, args.tf, args.candles)
    if df.empty:
        sys.exit("Script terminated due to data fetching error.")
    
    df = compute_indicators(df)
    if df.empty:
        sys.exit("Script terminated due to insufficient data for indicators.")
    
    sig = latest_signal(df)
    trn = trend(df)
    last = df.iloc[-1]

    # Print analysis results
    print(f"{datetime.datetime.utcnow():%Y-%m-%d %H:%M} UTC | {args.pair} {args.tf}")
    print(f"Price: {last.close:.4f}")
    print("-" * 30)
    print(f"EMA({FAST}): {last.ema_fast:.4f}, EMA({SLOW}): {last.ema_slow:.4f}")
    print(f"RSI({RSI_LEN}): {last.rsi:.2f}")
    print(f"MACD: {last.macd:.4f}, Signal: {last.macds:.4f}, Hist: {last.macdhist:.4f}")
    print("-" * 30)
    print(f"Trend: {trn} | Recommendation: {sig}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        sys.exit(f"An unhandled error occurred: {e}")

