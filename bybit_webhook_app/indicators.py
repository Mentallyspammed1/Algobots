import numpy as np
import pandas as pd


def calculate_atr(high, low, close, period=14):
    tr = pd.DataFrame(
        {
            "tr1": high - low,
            "tr2": abs(high - close.shift()),
            "tr3": abs(low - close.shift()),
        },
    ).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    return atr


def calculate_supertrend(df, period=10, multiplier=3):
    # Ensure DataFrame has required columns
    if not all(col in df.columns for col in ["high", "low", "close"]):
        raise ValueError("DataFrame must contain 'high', 'low', and 'close' columns.")

    # Calculate ATR
    atr = calculate_atr(df["high"], df["low"], df["close"], period)

    # Calculate Basic Upper and Lower Band
    basic_upper_band = ((df["high"] + df["low"]) / 2) + (multiplier * atr)
    basic_lower_band = ((df["high"] + df["low"]) / 2) - (multiplier * atr)

    # Calculate Final Upper and Lower Band
    final_upper_band = basic_upper_band.copy()
    final_lower_band = basic_lower_band.copy()

    for i in range(1, len(df)):
        if df["close"].iloc[i] > final_upper_band.iloc[i - 1]:
            final_upper_band.iloc[i] = max(
                basic_upper_band.iloc[i], final_upper_band.iloc[i - 1],
            )
        else:
            final_upper_band.iloc[i] = basic_upper_band.iloc[i]

        if df["close"].iloc[i] < final_lower_band.iloc[i - 1]:
            final_lower_band.iloc[i] = min(
                basic_lower_band.iloc[i], final_lower_band.iloc[i - 1],
            )
        else:
            final_lower_band.iloc[i] = basic_lower_band.iloc[i]

    # Calculate Supertrend
    supertrend = pd.Series(np.nan, index=df.index)
    trend = pd.Series(np.nan, index=df.index)

    for i in range(len(df)):
        if i == 0:
            trend.iloc[i] = True  # True for uptrend, False for downtrend
            supertrend.iloc[i] = final_upper_band.iloc[i]
        else:
            if (
                df["close"].iloc[i] > supertrend.iloc[i - 1]
                and df["close"].iloc[i - 1] <= supertrend.iloc[i - 1]
            ):
                trend.iloc[i] = True
            elif (
                df["close"].iloc[i] < supertrend.iloc[i - 1]
                and df["close"].iloc[i - 1] >= supertrend.iloc[i - 1]
            ):
                trend.iloc[i] = False
            else:
                trend.iloc[i] = trend.iloc[i - 1]

            if trend.iloc[i] == True:
                supertrend.iloc[i] = final_lower_band.iloc[i]
            else:
                supertrend.iloc[i] = final_upper_band.iloc[i]

            # Handle crossovers
            if (
                trend.iloc[i] == True
                and supertrend.iloc[i - 1] > final_lower_band.iloc[i]
            ):
                supertrend.iloc[i] = final_lower_band.iloc[i]
            elif (
                trend.iloc[i] == False
                and supertrend.iloc[i - 1] < final_upper_band.iloc[i]
            ):
                supertrend.iloc[i] = final_upper_band.iloc[i]

    return supertrend, trend
