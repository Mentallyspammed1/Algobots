import math


def calculate_indicators(klines: list, config: dict) -> dict | None:
    """Calculates Supertrend, RSI, and Ehlers-Fisher Transform from a list of kline data."""
    if (
        not klines
        or len(klines)
        < max(config["supertrend_length"], config["rsi_length"], config["ef_period"])
        + 1
    ):
        return None

    # Supertrend Calculation
    atr_period = config["supertrend_length"]
    multiplier = config["supertrend_multiplier"]
    supertrend_data = []
    atr_values = []

    for i in range(len(klines)):
        kline = klines[i]
        prev_kline = klines[i - 1] if i > 0 else None
        tr = 0
        if not prev_kline:
            tr = kline["high"] - kline["low"]
        else:
            tr = max(
                kline["high"] - kline["low"],
                abs(kline["high"] - prev_kline["close"]),
                abs(kline["low"] - prev_kline["close"]),
            )
        atr_values.append(tr)

        current_atr = sum(atr_values[-atr_period:]) / len(atr_values[-atr_period:])

        basic_upper_band = (kline["high"] + kline["low"]) / 2 + multiplier * current_atr
        basic_lower_band = (kline["high"] + kline["low"]) / 2 - multiplier * current_atr

        final_upper_band = basic_upper_band
        final_lower_band = basic_lower_band
        supertrend_val = 0
        direction = 0

        if i > 0:
            prev_st_data = supertrend_data[i - 1]
            if (
                basic_upper_band < prev_st_data["finalUpperBand"]
                or prev_kline["close"] > prev_st_data["finalUpperBand"]
            ):
                final_upper_band = basic_upper_band
            else:
                final_upper_band = prev_st_data["finalUpperBand"]

            if (
                basic_lower_band > prev_st_data["finalLowerBand"]
                or prev_kline["close"] < prev_st_data["finalLowerBand"]
            ):
                final_lower_band = basic_lower_band
            else:
                final_lower_band = prev_st_data["finalLowerBand"]

            if (
                prev_st_data["direction"] in [0, 1]
                and kline["close"] <= final_lower_band
            ):
                direction = -1
            elif (
                prev_st_data["direction"] in [0, -1]
                and kline["close"] >= final_upper_band
            ):
                direction = 1
            else:
                direction = prev_st_data["direction"]

            supertrend_val = final_lower_band if direction == 1 else final_upper_band
        else:
            direction = 1  # Default start
            supertrend_val = basic_lower_band

        supertrend_data.append(
            {
                "finalUpperBand": final_upper_band,
                "finalLowerBand": final_lower_band,
                "supertrend": supertrend_val,
                "direction": direction,
            }
        )

    final_supertrend = supertrend_data[-1]

    # RSI Calculation
    changes = [
        klines[i]["close"] - klines[i - 1]["close"] for i in range(1, len(klines))
    ]
    gains = [c if c > 0 else 0 for c in changes]
    losses = [-c if c < 0 else 0 for c in changes]

    avg_gain = sum(gains[: config["rsi_length"]]) / config["rsi_length"]
    avg_loss = sum(losses[: config["rsi_length"]]) / config["rsi_length"]

    for i in range(config["rsi_length"], len(gains)):
        avg_gain = (avg_gain * (config["rsi_length"] - 1) + gains[i]) / config[
            "rsi_length"
        ]
        avg_loss = (avg_loss * (config["rsi_length"] - 1) + losses[i]) / config[
            "rsi_length"
        ]

    rs = avg_gain / avg_loss if avg_loss > 0 else float("inf")
    final_rsi = 100 - (100 / (1 + rs))

    # Ehlers-Fisher Transform Calculation
    ef_period = config["ef_period"]
    fisher_data = []

    for i in range(len(klines)):
        kline = klines[i]

        if i < ef_period - 1:
            fisher_data.append({"value": 0, "fisher": 0})
            continue

        period_klines = klines[i - ef_period + 1 : i + 1]
        hh = max([k["high"] for k in period_klines])
        ll = min([k["low"] for k in period_klines])

        value = 0
        if hh != ll:
            value = 0.33 * ((kline["close"] - ll) / (hh - ll)) + 0.67 * (
                fisher_data[-1]["value"] if i > 0 else 0
            )
        else:
            value = (
                fisher_data[-1]["value"] if i > 0 else 0
            )  # Maintain previous value if no price range

        fisher = 0
        value = min(value, 0.99)
        value = max(value, -0.99)

        fisher = 0.5 * math.log((1 + value) / (1 - value)) + 0.5 * (
            fisher_data[-1]["fisher"] if i > 0 else 0
        )

        fisher_data.append({"value": value, "fisher": fisher})

    final_fisher = fisher_data[-1]["fisher"]

    return {"supertrend": final_supertrend, "rsi": final_rsi, "fisher": final_fisher}
