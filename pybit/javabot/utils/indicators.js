
// --- Numeric Helpers ---
/** Safely formats a number to a fixed number of decimal places, returning 'N/A' for invalid numbers. */
function nfmt(n, digits = 4) {
    return Number.isFinite(n) ? n.toFixed(digits) : 'N/A';
}

/** Calculates Simple Moving Average for an array of numbers. */
function sma(values, period) {
    if (!Array.isArray(values) || values.length < period) return null;
    const slice = values.slice(-period);
    const sum = slice.reduce((a, b) => a + b, 0);
    return sum / period;
}

/** Calculates Exponential Moving Average for an array of numbers. */
function ema(values, period) {
    if (!Array.isArray(values) || values.length < period) return null;
    const k = 2 / (period + 1);
    let prev = sma(values.slice(0, period), period);
    if (prev == null) return null;
    for (let i = period; i < values.length; i++) {
        prev = (values[i] - prev) * k + prev;
    }
    return prev;
}

// --- Indicator Calculation Functions ---

/** Calculates SMA using numeric array helper. */
function calculateSMA(data, period, priceType = 'close') {
    if (!data || data.length < period) return null;
    const values = data.slice(-period).map(d => Number(d[priceType]));
    return sma(values, period);
}

/** Calculates EMA using numeric array helper. */
function calculateEMA(data, period, priceType = 'close') {
    if (!data || data.length < period) return null;
    const values = data.map(d => Number(d[priceType]));
    return ema(values, period);
}

/** Calculates MACD with optimized EMA series and signal line calculation. */
function calculateMACD(data, fastPeriod, slowPeriod, signalPeriod) {
    if (!data || data.length < slowPeriod + signalPeriod - 1) return null;
    const closes = data.map(d => Number(d.close));

    const emaSeries = (period) => {
        if (!closes || closes.length < period) return null;
        const out = new Array(closes.length).fill(null);
        let prev = sma(closes.slice(0, period), period);
        if (prev == null) return null;
        out[period - 1] = prev;
        const k = 2 / (period + 1);
        for (let i = period; i < closes.length; i++) {
            prev = (closes[i] - prev) * k + prev;
            out[i] = prev;
        }
        return out;
    };

    const emaFast = emaSeries(fastPeriod);
    const emaSlow = emaSeries(slowPeriod);
    if (!emaFast || !emaSlow) return null;

    const macd = closes.map((_, i) => (emaFast[i] != null && emaSlow[i] != null) ? (emaFast[i] - emaSlow[i]) : null);
    const macdVals = macd.filter(v => v != null);
    if (macdVals.length < signalPeriod) return null;

    const signalAll = new Array(macd.length).fill(null);
    let prevSignal = sma(macdVals.slice(0, signalPeriod), signalPeriod);
    if (prevSignal == null) return null;

    let firstSignalAt = macd.findIndex(v => v != null) + signalPeriod - 1;
    if (firstSignalAt >= macd.length) return null;
    signalAll[firstSignalAt] = prevSignal;

    const k = 2 / (signalPeriod + 1);
    for (let i = firstSignalAt + 1; i < macd.length; i++) {
        if (macd[i] == null) continue;
        prevSignal = (macd[i] - prevSignal) * k + prevSignal;
        signalAll[i] = prevSignal;
    }

    const last = macd.length - 1;
    if (macd[last] == null || signalAll[last] == null) return null;
    return {
        macdLine: macd[last],
        signalLine: signalAll[last],
        histogram: macd[last] - signalAll[last],
    };
}

/** Calculates RSI with Wilder's smoothing. */
function calculateRSI(data, period) {
    if (!data || data.length < period + 1) return null;
    const closes = data.map(d => Number(d.close));
    let gain = 0, loss = 0;

    for (let i = 1; i <= period; i++) {
        const change = closes[closes.length - i] - closes[closes.length - i - 1];
        if (change > 0) gain += change; else loss -= change;
    }
    let avgGain = gain / period;
    let avgLoss = loss / period;

    for (let i = period + 1; i < closes.length; i++) {
        const change = closes[closes.length - i] - closes[closes.length - i - 1];
        const g = change > 0 ? change : 0;
        const l = change < 0 ? -change : 0;
        avgGain = (avgGain * (period - 1) + g) / period;
        avgLoss = (avgLoss * (period - 1) + l) / period;
    }

    if (avgLoss === 0) return 100;
    const rs = avgGain / avgLoss;
    return 100 - 100 / (1 + rs);
}

/** Calculates Stochastic Oscillator (%K and %D). */
function calculateStochastic(data, kPeriod, dPeriod) {
    if (!data || data.length < kPeriod || data.length < dPeriod) return null;
    const prices = data.map(d => Number(d.close));
    const highs = data.map(d => Number(d.high));
    const lows = data.map(d => Number(d.low));

    const relevantPricesK = prices.slice(prices.length - kPeriod);
    const relevantHighsK = highs.slice(prices.length - kPeriod);
    const relevantLowsK = lows.slice(lows.length - kPeriod);

    const highestHighK = Math.max(...relevantHighsK);
    const lowestLowK = Math.min(...relevantLowsK);
    const currentCloseK = relevantPricesK[relevantPricesK.length - 1];

    let kValue = 0;
    if (highestHighK !== lowestLowK) {
        kValue = ((currentCloseK - lowestLowK) / (highestHighK - lowestLowK)) * 100;
    } else {
        kValue = 50;
    }

    const kValues = [];
    for (let i = 0; i < prices.length; i++) {
        const currentSlice = data.slice(0, i + 1);
        if (currentSlice.length >= kPeriod) {
            const currentPrices = currentSlice.map(d => Number(d.close));
            const currentHighs = currentSlice.map(d => Number(d.high));
            const currentLows = currentSlice.map(d => Number(d.low));

            const currentHighestHigh = Math.max(...currentHighs.slice(-kPeriod));
            const currentLowestLow = Math.min(...currentLows.slice(-kPeriod));
            const currentClose = currentPrices[currentPrices.length - 1];

            let currentK = 0;
            if (currentHighestHigh !== currentLowestLow) {
                currentK = ((currentClose - currentLowestLow) / (currentHighestHigh - currentLowestLow)) * 100;
            } else {
                currentK = 50;
            }
            kValues.push(currentK);
        } else {
            kValues.push(null);
        }
    }
    const validKValues = kValues.filter(val => val !== null);
    const dValue = sma(validKValues, dPeriod);

    return { k: kValue, d: dValue };
}

/** Calculates ATR. */
function calculateATR(data, period) {
    if (!data || data.length < period + 1) return null;
    const highs = data.map(d => Number(d.high));
    const lows = data.map(d => Number(d.low));
    const closes = data.map(d => Number(d.close));

    const trueRanges = [];
    for (let i = 1; i < highs.length; i++) {
        const tr1 = highs[i] - lows[i];
        const tr2 = Math.abs(highs[i] - closes[i - 1]);
        const tr3 = Math.abs(lows[i] - closes[i - 1]);
        trueRanges.push(Math.max(tr1, tr2, tr3));
    }

    const initialATR = sma(trueRanges.slice(0, period), period);
    if (initialATR === null) return null;

    let atr = initialATR;
    const multiplier = 1 / period;

    for (let i = period; i < trueRanges.length; i++) {
        atr = (trueRanges[i] - atr) * multiplier + atr;
    }
    return atr;
}

/** Calculates Bollinger Bands. */
function calculateBollingerBands(data, period, stdDev) {
    if (!data || data.length < period) return null;
    const prices = data.map(d => Number(d.close));

    const middleBand = calculateSMA(data, period, 'close');
    if (middleBand === null) return null;

    const relevantPrices = prices.slice(prices.length - period);
    const mean = middleBand;
    const squaredDifferences = relevantPrices.map(p => Math.pow(p - mean, 2));
    const variance = squaredDifferences.reduce((a, b) => a + b, 0) / period;
    const standardDeviation = Math.sqrt(variance);

    const upperBand = middleBand + (standardDeviation * stdDev);
    const lowerBand = middleBand - (standardDeviation * stdDev);

    return { middleBand, upperBand, lowerBand };
}

/** Calculates OBV. */
function calculateOBV(data) {
    if (!data || data.length < 2) return null;
    const prices = data.map(d => Number(d.close));
    const volumes = data.map(d => Number(d.volume));

    let obv = 0;
    for (let i = 0; i < prices.length; i++) {
        if (i === 0) {
            obv = volumes[i];
        } else {
            if (prices[i] > prices[i - 1]) {
                obv += volumes[i];
            } else if (prices[i] < prices[i - 1]) {
                obv -= volumes[i];
            }
        }
    }
    return obv;
}

/** Calculates Williams %R. */
function calculateWilliamsR(data, period) {
    if (!data || data.length < period) return null;
    const prices = data.map(d => Number(d.close));
    const highs = data.map(d => Number(d.high));
    const lows = data.map(d => Number(d.low));

    const relevantPrices = prices.slice(prices.length - period);
    const relevantHighs = highs.slice(prices.length - period);
    const relevantLows = lows.slice(prices.length - period);

    const highestHigh = Math.max(...relevantHighs);
    const lowestLow = Math.min(...relevantLows);
    const currentClose = relevantPrices[relevantPrices.length - 1];

    if (highestHigh === lowestLow) return 0;

    const williamsR = ((highestHigh - currentClose) / (highestHigh - lowestLow)) * -100;
    return williamsR;
}

/** Calculates CMF using the last N bars. */
function calculateCMF(data, period) {
    if (!data || data.length < period) return null;
    const slice = data.slice(-period);
    let mfvSum = 0, volSum = 0;

    for (const d of slice) {
        const high = Number(d.high), low = Number(d.low), close = Number(d.close), vol = Number(d.volume);
        const range = high - low;
        if (range === 0 || !Number.isFinite(range) || !Number.isFinite(vol)) continue;

        const mfMultiplier = ((close - low) - (high - close)) / range;
        const mfv = mfMultiplier * vol;
        mfvSum += mfv;
        volSum += vol;
    }

    if (volSum === 0) return 0;
    return mfvSum / volSum;
}

/** Calculates Elder-Ray. */
function calculateElderRay(data, period) {
    if (!data || data.length < period) return null;
    const highs = data.map(d => Number(d.high));
    const lows = data.map(d => Number(d.low));

    const ema = calculateEMA(data, period, 'close');
    if (ema === null) return null;

    const currentHigh = highs[highs.length - 1];
    const currentLow = lows[lows.length - 1];

    const bullishPower = currentHigh - ema;
    const bearishPower = currentLow - ema;

    return { bullishPower, bearishPower };
}

/** Calculates Keltner Channels. */
function calculateKeltnerChannels(data, period, atrMultiplier) {
    if (!data || data.length < period) return null;
    const middleBand = calculateEMA(data, period, 'close');
    if (middleBand === null) return null;

    const atr = calculateATR(data, period);
    if (atr === null) return null;

    const upperChannel = middleBand + (atr * atrMultiplier);
    const lowerChannel = middleBand - (atr * atrMultiplier);

    return { middleBand, upperChannel, lowerChannel };
}

/** Calculates Aroon Indicator (fixed recency). */
function calculateAroon(data, period) {
    if (!data || data.length < period) return null;
    const highs = data.map(d => Number(d.high));
    const lows = data.map(d => Number(d.low));

    const windowHighs = highs.slice(-period);
    const windowLows = lows.slice(-period);

    const highestHigh = Math.max(...windowHighs);
    const lowestLow = Math.min(...windowLows);

    const hhIdx = windowHighs.lastIndexOf(highestHigh);
    const llIdx = windowLows.lastIndexOf(lowestLow);

    const periodsSinceHH = (period - 1) - hhIdx;
    const periodsSinceLL = (period - 1) - llIdx;

    const aroonUp = ((period - periodsSinceHH) / period) * 100;
    const aroonDown = ((period - periodsSinceLL) / period) * 100;

    return { aroonUp, aroonDown };
}

module.exports = {
    nfmt,
    calculateSMA,
    calculateEMA,
    calculateMACD,
    calculateRSI,
    calculateStochastic,
    calculateATR,
    calculateBollingerBands,
    calculateOBV,
    calculateWilliamsR,
    calculateCMF,
    calculateElderRay,
    calculateKeltnerChannels,
    calculateAroon
};