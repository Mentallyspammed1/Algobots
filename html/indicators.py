import math

# --- Numerically Stable Helper Functions ---


def _calculate_wilder_rma(data: list[float], period: int) -> list[float]:
    """Calculates Wilder's Recursive Moving Average (RMA)."""
    if not data or len(data) < period:
        return [0.0] * len(data)

    rma_values = [0.0] * len(data)
    alpha = 1.0 / period

    # Initial SMA
    rma_values[period - 1] = sum(data[:period]) / period

    # Recursive calculation
    for i in range(period, len(data)):
        rma_values[i] = alpha * data[i] + (1 - alpha) * rma_values[i - 1]

    return rma_values


def _calculate_ema(data: list[float], period: int) -> list[float]:
    """Calculates Exponential Moving Average (EMA)."""
    if not data or len(data) < period:
        return [0.0] * len(data)

    ema_values = [0.0] * len(data)
    smoothing_factor = 2.0 / (period + 1)

    # Initial SMA
    ema_values[period - 1] = sum(data[:period]) / period

    # Exponential calculation
    for i in range(period, len(data)):
        ema_values[i] = (data[i] - ema_values[i - 1]) * smoothing_factor + ema_values[
            i - 1
        ]

    return ema_values


def _calculate_sma(data: list[float], period: int) -> list[float]:
    """Calculates Simple Moving Average (SMA)."""
    if not data or len(data) < period:
        return [0.0] * len(data)

    sma_values = [0.0] * len(data)
    current_sum = sum(data[:period])
    sma_values[period - 1] = current_sum / period

    for i in range(period, len(data)):
        current_sum += data[i] - data[i - period]
        sma_values[i] = current_sum / period

    return sma_values


# --- Indicator Calculation Functions ---


def _calculate_atr(klines: list[dict], period: int) -> list[float]:
    """Calculates Average True Range (ATR)."""
    trs = [0.0] * len(klines)
    for i in range(1, len(klines)):
        kline = klines[i]
        prev_kline = klines[i - 1]
        tr = max(
            kline["high"] - kline["low"],
            abs(kline["high"] - prev_kline["close"]),
            abs(kline["low"] - prev_kline["close"]),
        )
        trs[i] = tr
    return _calculate_wilder_rma(trs, period)


def _calculate_supertrend(klines: list[dict], length: int, multiplier: float) -> dict:
    """Calculates Supertrend indicator."""
    closes = [k["close"] for k in klines]
    atr_values = _calculate_atr(klines, length)

    upper_band = [0.0] * len(klines)
    lower_band = [0.0] * len(klines)
    supertrend = [0.0] * len(klines)
    direction = [1] * len(klines)

    for i in range(length, len(klines)):
        hl2 = (klines[i]["high"] + klines[i]["low"]) / 2
        upper_band[i] = hl2 + multiplier * atr_values[i]
        lower_band[i] = hl2 - multiplier * atr_values[i]

        # Adjust bands based on previous close
        if closes[i - 1] > upper_band[i - 1]:
            upper_band[i] = min(upper_band[i], upper_band[i - 1])
        if closes[i - 1] < lower_band[i - 1]:
            lower_band[i] = max(lower_band[i], lower_band[i - 1])

        # Determine direction and final supertrend value
        if closes[i] > upper_band[i - 1]:
            direction[i] = 1
        elif closes[i] < lower_band[i - 1]:
            direction[i] = -1
        else:
            direction[i] = direction[i - 1]

        supertrend[i] = lower_band[i] if direction[i] == 1 else upper_band[i]

    return {"supertrend": supertrend[-1], "direction": direction[-1]}


def _calculate_rsi(closes: list[float], length: int) -> float:
    """Calculates Relative Strength Index (RSI) using Wilder's smoothing."""
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]

    avg_gain = _calculate_wilder_rma(gains, length)[-1]
    avg_loss = _calculate_wilder_rma(losses, length)[-1]

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _calculate_ehlers_fisher(klines: list[dict], period: int) -> float:
    """Calculates Ehlers-Fisher Transform."""
    values = [0.0] * len(klines)
    fishers = [0.0] * len(klines)

    for i in range(period, len(klines)):
        period_klines = klines[i - period + 1 : i + 1]
        hh = max(k["high"] for k in period_klines)
        ll = min(k["low"] for k in period_klines)

        price = (klines[i]["high"] + klines[i]["low"]) / 2

        # Normalize price from -1 to 1
        val = 0.0
        if hh - ll != 0:
            val = 2 * ((price - ll) / (hh - ll)) - 1

        # Apply smoothing
        values[i] = 0.33 * val + 0.67 * values[i - 1]

        # Clamp values to avoid math domain errors
        clamped_val = max(min(values[i], 0.999), -0.999)

        # Fisher Transform
        fishers[i] = (
            0.5 * math.log((1 + clamped_val) / (1 - clamped_val)) + 0.5 * fishers[i - 1]
        )

    return fishers[-1]


def _calculate_macd(
    closes: list[float], fast_period: int, slow_period: int, signal_period: int,
) -> dict:
    """Calculates Moving Average Convergence Divergence (MACD)."""
    fast_ema = _calculate_ema(closes, fast_period)
    slow_ema = _calculate_ema(closes, slow_period)

    macd_line = [f - s for f, s in zip(fast_ema, slow_ema, strict=False)]
    signal_line = _calculate_ema(macd_line, signal_period)
    histogram = [m - s for m, s in zip(macd_line, signal_line, strict=False)]

    return {
        "macd_line": macd_line[-1],
        "signal_line": signal_line[-1],
        "histogram": histogram[-1],
    }


def _calculate_bollinger_bands(
    closes: list[float], period: int, std_dev: float,
) -> dict:
    """Calculates Bollinger Bands."""
    middle_band = _calculate_sma(closes, period)

    # Calculate standard deviation
    std_dev_values = [0.0] * len(closes)
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1 : i + 1]
        mean = middle_band[i]
        variance = sum([(x - mean) ** 2 for x in window]) / period
        std_dev_values[i] = math.sqrt(variance)

    upper_band = [
        m + (s * std_dev) for m, s in zip(middle_band, std_dev_values, strict=False)
    ]
    lower_band = [
        m - (s * std_dev) for m, s in zip(middle_band, std_dev_values, strict=False)
    ]

    return {
        "middle_band": middle_band[-1],
        "upper_band": upper_band[-1],
        "lower_band": lower_band[-1],
    }


# --- Main Public Function ---


def calculate_indicators(klines: list[dict], config: dict) -> dict | None:
    """Calculates all trading indicators from a list of kline data.
    Returns a dictionary of indicator values or None if data is insufficient.
    """
    max_lookback = max(
        config.get("supertrend_length", 10),
        config.get("rsi_length", 14) + 1,  # RSI needs one more for deltas
        config.get("ef_period", 10),
        config.get("macd_slow_period", 26),
        config.get("bb_period", 20),
    )

    if not klines or len(klines) < max_lookback:
        return None

    closes = [float(k["close"]) for k in klines]

    return {
        "supertrend": _calculate_supertrend(
            klines, config["supertrend_length"], config["supertrend_multiplier"],
        ),
        "rsi": _calculate_rsi(closes, config["rsi_length"]),
        "fisher": _calculate_ehlers_fisher(klines, config["ef_period"]),
        "macd": _calculate_macd(
            closes,
            config["macd_fast_period"],
            config["macd_slow_period"],
            config["macd_signal_period"],
        ),
        "bollinger_bands": _calculate_bollinger_bands(
            closes, config["bb_period"], config["bb_std_dev"],
        ),
    }
