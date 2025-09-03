// src/indicators/ta.js

function SMA(data, period) {
    if (data.length < period) return [];
    const results = [];
    for (let i = period - 1; i < data.length; i++) {
        const slice = data.slice(i - period + 1, i + 1);
        const sum = slice.reduce((a, b) => a + b, 0);
        results.push(sum / period);
    }
    // Pad with nulls at the beginning to match original data length
    return Array(period - 1).fill(null).concat(results);
}

function EMA(data, period) {
    if (data.length < period) return [];
    const results = [];
    const multiplier = 2 / (period + 1);
    // First EMA is an SMA
    let slice = data.slice(0, period);
    let sum = slice.reduce((a, b) => a + b, 0);
    let prevEma = sum / period;
    results.push(prevEma);

    for (let i = period; i < data.length; i++) {
        const ema = (data[i] - prevEma) * multiplier + prevEma;
        results.push(ema);
        prevEma = ema;
    }
    // Pad with nulls
    return Array(period - 1).fill(null).concat(results);
}

function RSI(data, period) {
    if (data.length < period + 1) return [];
    const results = [];
    let avgGain = 0;
    let avgLoss = 0;

    // Calculate first avgGain and avgLoss
    for (let i = 1; i <= period; i++) {
        const change = data[i] - data[i - 1];
        if (change > 0) {
            avgGain += change;
        } else {
            avgLoss -= change;
        }
    }
    avgGain /= period;
    avgLoss /= period;

    let rs = avgLoss === 0 ? Infinity : avgGain / avgLoss;
    results.push(100 - (100 / (1 + rs)));

    // Calculate subsequent RSI values
    for (let i = period + 1; i < data.length; i++) {
        const change = data[i] - data[i - 1];
        let gain = change > 0 ? change : 0;
        let loss = change < 0 ? -change : 0;

        avgGain = (avgGain * (period - 1) + gain) / period;
        avgLoss = (avgLoss * (period - 1) + loss) / period;

        rs = avgLoss === 0 ? Infinity : avgGain / avgLoss;
        results.push(100 - (100 / (1 + rs)));
    }

    return Array(period).fill(null).concat(results);
}

function MACD(data, fastPeriod, slowPeriod, signalPeriod) {
    const emaFast = EMA(data, fastPeriod);
    const emaSlow = EMA(data, slowPeriod);

    const macdLine = [];
    for (let i = 0; i < data.length; i++) {
        if (emaFast[i] !== null && emaSlow[i] !== null) {
            macdLine.push(emaFast[i] - emaSlow[i]);
        } else {
            macdLine.push(null);
        }
    }

    const firstMacdIndex = macdLine.findIndex(v => v !== null);
    if (firstMacdIndex === -1) return { macd: [], signal: [], histogram: [] };

    const validMacd = macdLine.slice(firstMacdIndex);
    const signalLine = EMA(validMacd, signalPeriod);

    const paddedSignal = Array(firstMacdIndex).fill(null).concat(signalLine);

    const histogram = [];
    for (let i = 0; i < data.length; i++) {
        if (macdLine[i] !== null && paddedSignal[i] !== null) {
            histogram.push(macdLine[i] - paddedSignal[i]);
        } else {
            histogram.push(null);
        }
    }

    return { macd: macdLine, signal: paddedSignal, histogram };
}

function ATR(klines, period) {
    if (klines.length < period + 1) return [];
    const trValues = [];
    // First TR
    trValues.push(klines[0].high - klines[0].low);

    for (let i = 1; i < klines.length; i++) {
        const high = klines[i].high;
        const low = klines[i].low;
        const prevClose = klines[i - 1].close;
        const tr = Math.max(high - low, Math.abs(high - prevClose), Math.abs(low - prevClose));
        trValues.push(tr);
    }

    const atr = [];
    // First ATR is an average of first 'period' TRs
    let sumTr = 0;
    for (let i = 0; i < period; i++) {
        sumTr += trValues[i];
    }
    let prevAtr = sumTr / period;
    atr.push(prevAtr);

    // Subsequent ATRs
    for (let i = period; i < trValues.length; i++) {
        const currentAtr = (prevAtr * (period - 1) + trValues[i]) / period;
        atr.push(currentAtr);
        prevAtr = currentAtr;
    }

    return Array(period - 1).fill(null).concat(atr);
}


export const ta = {
    SMA,
    EMA,
    RSI,
    MACD,
    ATR
};