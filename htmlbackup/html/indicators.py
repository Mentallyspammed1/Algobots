import math


def calculate_indicators(klines: list, config: dict) -> dict | None:
    """Calculates Supertrend, RSI, Ehlers-Fisher Transform, MACD, and Bollinger Bands from a list of kline data.
    """
    # Determine the maximum lookback period required by any indicator
    max_lookback = max(
        config['supertrend_length'],
        config['rsi_length'],
        config['ef_period'],
        config.get('macd_slow_period', 26), # Default for MACD
        config.get('bb_period', 20) # Default for Bollinger Bands
    )

    if not klines or len(klines) < max_lookback + 1:
        return None

    closes = [k['close'] for k in klines]

    # --- Helper Functions for Moving Averages ---
    def calculate_ema(data, period):
        if not data or len(data) < period: return [0] * len(data)
        ema_values = []
        smoothing_factor = 2 / (period + 1)

        # Initial SMA for first EMA value
        initial_ema = sum(data[:period]) / period
        ema_values.append(initial_ema)

        for i in range(period, len(data)):
            current_ema = (data[i] - ema_values[-1]) * smoothing_factor + ema_values[-1]
            ema_values.append(current_ema)
        return [0] * (period - 1) + ema_values # Pad with zeros for initial period

    def calculate_sma(data, period):
        if not data or len(data) < period: return [0] * len(data)
        sma_values = []
        for i in range(len(data) - period + 1):
            sma_values.append(sum(data[i:i+period]) / period)
        return [0] * (period - 1) + sma_values # Pad with zeros for initial period

    # --- Supertrend Calculation ---
    atr_period = config['supertrend_length']
    multiplier = config['supertrend_multiplier']
    supertrend_data = []
    atr_values = []

    for i in range(len(klines)):
        kline = klines[i]
        prev_kline = klines[i-1] if i > 0 else None
        tr = 0
        if not prev_kline:
            tr = kline['high'] - kline['low']
        else:
            tr = max(kline['high'] - kline['low'], abs(kline['high'] - prev_kline['close']), abs(kline['low'] - prev_kline['close']))
        atr_values.append(tr)

        current_atr = sum(atr_values[-atr_period:]) / len(atr_values[-atr_period:])

        basic_upper_band = (kline['high'] + kline['low']) / 2 + multiplier * current_atr
        basic_lower_band = (kline['high'] + kline['low']) / 2 - multiplier * current_atr

        final_upper_band = basic_upper_band
        final_lower_band = basic_lower_band
        supertrend_val = 0
        direction = 0

        if i > 0:
            prev_st_data = supertrend_data[i-1]
            if basic_upper_band < prev_st_data['finalUpperBand'] or prev_kline['close'] > prev_st_data['finalUpperBand']:
                final_upper_band = basic_upper_band
            else:
                final_upper_band = prev_st_data['finalUpperBand']

            if basic_lower_band > prev_st_data['finalLowerBand'] or prev_kline['close'] < prev_st_data['finalLowerBand']:
                final_lower_band = basic_lower_band
            else:
                final_lower_band = prev_st_data['finalLowerBand']

            if prev_st_data['direction'] in [0, 1] and kline['close'] <= final_lower_band: # Changed from final_upper_band to final_lower_band
                direction = -1
            elif prev_st_data['direction'] in [0, -1] and kline['close'] >= final_upper_band: # Changed from final_lower_band to final_upper_band
                direction = 1
            else:
                direction = prev_st_data['direction']

            supertrend_val = final_lower_band if direction == 1 else final_upper_band
        else:
            direction = 1 # Default start
            supertrend_val = basic_lower_band

        supertrend_data.append({
            'finalUpperBand': final_upper_band,
            'finalLowerBand': final_lower_band,
            'supertrend': supertrend_val,
            'direction': direction
        })

    final_supertrend = supertrend_data[-1]

    # --- RSI Calculation ---
    changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [c if c > 0 else 0 for c in changes]
    losses = [-c if c < 0 else 0 for c in changes]

    avg_gain = sum(gains[:config['rsi_length']]) / config['rsi_length']
    avg_loss = sum(losses[:config['rsi_length']]) / config['rsi_length']

    for i in range(config['rsi_length'], len(gains)):
        avg_gain = (avg_gain * (config['rsi_length'] - 1) + gains[i]) / config['rsi_length']
        avg_loss = (avg_loss * (config['rsi_length'] - 1) + losses[i]) / config['rsi_length']

    rs = avg_gain / avg_loss if avg_loss > 0 else float('inf')
    final_rsi = 100 - (100 / (1 + rs))

    # --- Ehlers-Fisher Transform Calculation ---
    ef_period = config['ef_period']
    fisher_data = []

    for i in range(len(klines)):
        kline = klines[i]

        if i < ef_period - 1:
            fisher_data.append({'value': 0, 'fisher': 0})
            continue

        period_klines = klines[i - ef_period + 1 : i + 1]
        hh = max([k['high'] for k in period_klines])
        ll = min([k['low'] for k in period_klines])

        value = 0
        if hh != ll:
            value = 0.33 * ((kline['close'] - ll) / (hh - ll)) + 0.67 * (fisher_data[-1]['value'] if i > 0 else 0)
        else:
            value = fisher_data[-1]['value'] if i > 0 else 0 # Maintain previous value if no price range

        fisher = 0
        if value > 0.99: value = 0.99
        if value < -0.99: value = -0.99

        fisher = 0.5 * math.log((1 + value) / (1 - value)) + 0.5 * (fisher_data[-1]['fisher'] if i > 0 else 0)

        fisher_data.append({'value': value, 'fisher': fisher})

    final_fisher = fisher_data[-1]['fisher']

    # --- MACD Calculation ---
    macd_fast_period = config.get('macd_fast_period', 12)
    macd_slow_period = config.get('macd_slow_period', 26)
    macd_signal_period = config.get('macd_signal_period', 9)

    fast_ema = calculate_ema(closes, macd_fast_period)
    slow_ema = calculate_ema(closes, macd_slow_period)

    macd_line = [f - s for f, s in zip(fast_ema, slow_ema, strict=False)]
    signal_line = calculate_ema(macd_line, macd_signal_period)

    # MACD Histogram
    macd_histogram = [m - s for m, s in zip(macd_line, signal_line, strict=False)]

    final_macd = {
        'macd_line': macd_line[-1],
        'signal_line': signal_line[-1],
        'histogram': macd_histogram[-1]
    }

    # --- Bollinger Bands Calculation ---
    bb_period = config.get('bb_period', 20)
    bb_std_dev = config.get('bb_std_dev', 2.0)

    sma_bb = calculate_sma(closes, bb_period)

    # Calculate standard deviation for each window
    std_dev_values = []
    for i in range(len(closes) - bb_period + 1):
        window = closes[i:i+bb_period]
        mean = sum(window) / bb_period
        variance = sum([(x - mean) ** 2 for x in window]) / bb_period
        std_dev_values.append(math.sqrt(variance))

    # Pad std_dev_values to match closes length
    std_dev_values = [0] * (bb_period - 1) + std_dev_values

    upper_band = [s + (std * bb_std_dev) for s, std in zip(sma_bb, std_dev_values, strict=False)]
    lower_band = [s - (std * bb_std_dev) for s, std in zip(sma_bb, std_dev_values, strict=False)]

    final_bollinger_bands = {
        'middle_band': sma_bb[-1],
        'upper_band': upper_band[-1],
        'lower_band': lower_band[-1]
    }

    return {"supertrend": final_supertrend, "rsi": final_rsi, "fisher": final_fisher, "macd": final_macd, "bollinger_bands": final_bollinger_bands}
